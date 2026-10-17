#!/usr/bin/env python3
"""Serve the standalone UI and proxy its Gateway API requests on the same origin."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
MAX_REQUEST_BYTES = 10_000_000


def hermes_gateway_props() -> dict[str, object]:
    """Return the llama.cpp props shape the vendored UI needs to start."""
    params = {
        "backend_sampling": False,
        "chat_format": "",
        "dry_allowed_length": 2,
        "dry_base": 1.75,
        "dry_multiplier": 0,
        "dry_penalty_last_n": -1,
        "dry_sequence_breakers": [],
        "dynatemp_exponent": 1,
        "dynatemp_range": 0,
        "frequency_penalty": 0,
        "generation_prompt": "",
        "grammar": "",
        "grammar_lazy": False,
        "grammar_triggers": [],
        "ignore_eos": False,
        "logit_bias": [],
        "lora": [],
        "max_tokens": -1,
        "min_keep": 0,
        "min_p": 0,
        "mirostat": 0,
        "mirostat_eta": 0.1,
        "mirostat_tau": 5,
        "n_discard": 0,
        "n_keep": 0,
        "n_predict": -1,
        "n_probs": 0,
        "post_sampling_probs": False,
        "presence_penalty": 0,
        "preserved_tokens": [],
        "reasoning_format": "auto",
        "reasoning_in_content": False,
        "repeat_last_n": 64,
        "repeat_penalty": 1,
        "samplers": [],
        "seed": -1,
        "speculative.n_max": 16,
        "speculative.n_min": 0,
        "speculative.p_min": 0.75,
        "stop": [],
        "stream": True,
        "temperature": 0.8,
        "timings_per_token": False,
        "top_k": 40,
        "top_n_sigma": -1,
        "top_p": 0.95,
        "typ_p": 1,
        "xtc_probability": 0,
        "xtc_threshold": 0.1,
    }
    return {
        "bos_token": "",
        "build_info": "Hermes Gateway compatibility bridge",
        "chat_template": "",
        "default_generation_settings": {
            "id": 0,
            "id_task": 0,
            "is_processing": False,
            "n_ctx": 128000,
            "next_token": {
                "has_new_line": False,
                "has_next_token": False,
                "n_decoded": 0,
                "n_remain": 0,
                "stopping_word": "",
            },
            "params": params,
            "prompt": "",
            "speculative": False,
        },
        "eos_token": "",
        "modalities": {"audio": False, "video": False, "vision": True},
        "model_path": "Hermes Gateway",
        "role": "model",
        "total_slots": 1,
    }


class HermesBridgeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    gateway_url = ""
    static_dir = Path("dist")

    def do_DELETE(self) -> None:
        self._dispatch()

    def do_GET(self) -> None:
        self._dispatch()

    def do_HEAD(self) -> None:
        self._dispatch()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:
        self._dispatch()

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    def _dispatch(self) -> None:
        path = urlsplit(self.path).path

        if self.command == "GET" and path == "/props":
            self._send_json(HTTPStatus.OK, hermes_gateway_props())
            return

        if self.command == "GET" and path in {"/slots", "/tools"}:
            self._send_json(HTTPStatus.OK, [])
            return

        if self.command == "POST" and path == "/v1/streams/lookup":
            self._send_json(HTTPStatus.OK, [])
            return

        if path.startswith("/v1/"):
            self._proxy_gateway()
            return

        if self.command not in {"GET", "HEAD"}:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": {"message": "Endpoint not provided by Hermes Gateway UI"}},
            )
            return

        self._serve_static(path)

    def _proxy_gateway(self) -> None:
        body = None
        content_length = self.headers.get("Content-Length")
        if content_length:
            try:
                size = int(content_length)
            except ValueError:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": {"message": "Invalid Content-Length"}})
                return
            if size < 0 or size > MAX_REQUEST_BYTES:
                self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": {"message": "Request too large"}})
                return
            body = self.rfile.read(size)

        headers = {
            name: value
            for name, value in self.headers.items()
            if name.lower() not in HOP_BY_HOP_HEADERS | {"content-length", "host"}
        }
        request = Request(f"{self.gateway_url}{self.path}", data=body, headers=headers, method=self.command)

        try:
            with urlopen(request, timeout=660) as response:
                self._forward_response(response.status, response.headers, response)
        except HTTPError as error:
            self._forward_response(error.code, error.headers, error)
        except URLError:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"error": {"message": "Hermes Gateway is unavailable. Start it and check the bridge gateway URL."}},
            )

    def _forward_response(self, status: int, headers: object, response: object) -> None:
        self.send_response(status)
        for name, value in headers.items():
            if name.lower() not in HOP_BY_HOP_HEADERS | {"content-length"}:
                self.send_header(name, value)
        self.send_header("Connection", "close")
        self.end_headers()

        if self.command != "HEAD":
            while chunk := response.read(64 * 1024):
                self.wfile.write(chunk)
                self.wfile.flush()
        self.close_connection = True

    def _serve_static(self, path: str) -> None:
        requested = unquote(path).lstrip("/") or "index.html"
        candidate = (self.static_dir / requested).resolve()
        try:
            candidate.relative_to(self.static_dir)
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        if not candidate.is_file():
            candidate = self.static_dir / "index.html"

        if not candidate.is_file():
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": {"message": f"UI build not found at {self.static_dir}. Run npm run build first."}},
            )
            return

        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Length", str(candidate.stat().st_size))
        self.send_header("Content-Type", content_type)
        self.end_headers()
        if self.command != "HEAD":
            with candidate.open("rb") as file:
                while chunk := file.read(64 * 1024):
                    self.wfile.write(chunk)

    def _send_json(self, status: HTTPStatus, payload: object) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve Hermes Gateway UI")
    parser.add_argument("--host", default=os.environ.get("HERMES_UI_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("HERMES_UI_PORT", "8788")))
    parser.add_argument(
        "--gateway-url",
        default=os.environ.get("HERMES_UI_GATEWAY_URL", "http://127.0.0.1:8642"),
        help="Hermes Gateway API Server origin",
    )
    parser.add_argument("--dist", default="dist", help="Static build directory")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    gateway = urlsplit(args.gateway_url)
    if gateway.scheme not in {"http", "https"} or not gateway.netloc:
        raise SystemExit("--gateway-url must be an absolute http(s) URL")

    HermesBridgeHandler.gateway_url = args.gateway_url.rstrip("/")
    HermesBridgeHandler.static_dir = Path(args.dist).resolve()
    server = ThreadingHTTPServer((args.host, args.port), HermesBridgeHandler)
    print(f"Hermes Gateway UI: http://{args.host}:{args.port}")
    print(f"Gateway API: {HermesBridgeHandler.gateway_url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
