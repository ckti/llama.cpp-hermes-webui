"""Regression tests for the bridge's local SQLite memory backend."""

from __future__ import annotations

import json
import threading
import unittest
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from hermes_bridge import HermesBridgeHandler, LocalMemoryStore


class LocalMemoryStoreTests(unittest.TestCase):
    def test_search_is_scoped_and_content_updates_reindex(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            store = LocalMemoryStore(Path(temporary_directory) / "memory.sqlite3")
            first_scope = store.scope_for("browser-session-a")
            second_scope = store.scope_for("browser-session-b")
            entry = store.create(first_scope, "My preferred editor is Helix.", metadata={"kind": "preference"})
            store.create(second_scope, "My preferred editor is Emacs.")

            self.assertEqual([item["id"] for item in store.search(first_scope, "editor")], [entry["id"]])
            self.assertEqual(store.search(second_scope, "Helix"), [])

            updated = store.update(first_scope, entry["id"], {"content": "My preferred editor is Vim."})

            self.assertEqual(updated["content"], "My preferred editor is Vim.")
            self.assertEqual(store.search(first_scope, "Helix"), [])
            self.assertEqual([item["id"] for item in store.search(first_scope, "Vim")], [entry["id"]])

    def test_create_is_idempotent_for_identical_memory(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            store = LocalMemoryStore(Path(temporary_directory) / "memory.sqlite3")
            scope = store.scope_for("browser-session")

            first = store.create(scope, "Use dark mode.", metadata={"source": "one"})
            second = store.create(scope, "Use dark mode.", metadata={"source": "two"})

            self.assertEqual(first["id"], second["id"])
            self.assertEqual(store.list(scope), [second])


class BridgeMemoryApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        store = LocalMemoryStore(Path(self.temporary_directory.name) / "memory.sqlite3")

        class TestHandler(HermesBridgeHandler):
            memory_store = store

            def log_message(self, _format: str, *_args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.headers = {"Content-Type": "application/json", "X-Hermes-Session-Key": "chat-a"}

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temporary_directory.cleanup()

    def request(self, path: str, method: str = "GET", payload: dict | None = None, headers: dict | None = None):
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode() if payload is not None else None,
            headers=headers or self.headers,
            method=method,
        )
        with urlopen(request) as response:
            return response.status, json.loads(response.read())

    def test_crud_requires_matching_session_key_scope(self) -> None:
        status, created = self.request(
            "/api/local-memory",
            "POST",
            {"content": "The deployment region is London.", "metadata": {"source": "test"}},
        )
        self.assertEqual(status, 201)
        memory_id = created["memory"]["id"]

        status, listed = self.request("/api/local-memory?q=deployment")
        self.assertEqual(status, 200)
        self.assertEqual([item["id"] for item in listed["data"]], [memory_id])

        other_headers = {**self.headers, "X-Hermes-Session-Key": "chat-b"}
        status, other_list = self.request("/api/local-memory?q=deployment", headers=other_headers)
        self.assertEqual(status, 200)
        self.assertEqual(other_list["data"], [])

        status, updated = self.request(
            f"/api/local-memory/{memory_id}",
            "PATCH",
            {"content": "The deployment region is Manchester."},
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated["memory"]["content"], "The deployment region is Manchester.")

        status, deleted = self.request(f"/api/local-memory/{memory_id}", "DELETE")
        self.assertEqual(status, 200)
        self.assertTrue(deleted["deleted"])

        with self.assertRaises(HTTPError) as missing:
            self.request(f"/api/local-memory/{memory_id}")
        self.assertEqual(missing.exception.code, 404)


class BridgeMemoryRecallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.upstream_payloads: list[dict] = []
        payloads = self.upstream_payloads

        class UpstreamHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers["Content-Length"])
                payloads.append(json.loads(self.rfile.read(length)))
                body = b'{"ok":true}'
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                pass

        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
        self.upstream_thread = threading.Thread(target=self.upstream.serve_forever, daemon=True)
        self.upstream_thread.start()

        store = LocalMemoryStore(Path(self.temporary_directory.name) / "memory.sqlite3")
        store.create(store.scope_for("chat-a"), "The preferred deployment region is London.")
        upstream_url = f"http://127.0.0.1:{self.upstream.server_address[1]}"

        class TestHandler(HermesBridgeHandler):
            gateway_url = upstream_url
            memory_store = store
            memory_capture = "explicit"

            def log_message(self, _format: str, *_args: object) -> None:
                pass

        self.bridge = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        self.bridge_thread = threading.Thread(target=self.bridge.serve_forever, daemon=True)
        self.bridge_thread.start()
        self.base_url = f"http://127.0.0.1:{self.bridge.server_address[1]}"
        self.store = store
        self.headers = {"Content-Type": "application/json", "X-Hermes-Session-Key": "chat-a"}

    def tearDown(self) -> None:
        self.bridge.shutdown()
        self.bridge.server_close()
        self.bridge_thread.join()
        self.upstream.shutdown()
        self.upstream.server_close()
        self.upstream_thread.join()
        self.temporary_directory.cleanup()

    def session_chat(self, content: str) -> None:
        request = Request(
            f"{self.base_url}/api/sessions/session-1/chat",
            data=json.dumps({"input": content}).encode(),
            headers=self.headers,
            method="POST",
        )
        with urlopen(request) as response:
            self.assertEqual(response.status, 200)
            response.read()

    def test_recalled_memory_is_marked_untrusted_and_explicit_capture_is_deferred(self) -> None:
        self.session_chat("Which deployment region should I use?")

        forwarded = self.upstream_payloads[-1]
        self.assertIn("<hermes-long-term-memory>", forwarded["system_message"])
        self.assertIn("untrusted user data", forwarded["system_message"])
        self.assertIn("London", forwarded["system_message"])

        self.session_chat("Remember that the deployment owner is Casey.")

        memories = self.store.search(self.store.scope_for("chat-a"), "Casey")
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["source_session_id"], "session-1")
        self.assertEqual(memories[0]["role"], "user")

