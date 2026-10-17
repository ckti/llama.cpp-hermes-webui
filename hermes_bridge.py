#!/usr/bin/env python3
"""Serve the Hermes UI and transparently proxy the native Hermes API."""

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


class HermesBridgeHandler(BaseHTTPRequestHandler):
    """Same-origin static server for the UI and pass-through for Hermes APIs."""

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
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch()

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    def _dispatch(self) -> None:
        path = urlsplit(self.path).path

        # The UI uses only documented Hermes Gateway endpoints. Keeping the
        # proxy scoped prevents static-file requests from being forwarded.
        if (
            path == "/api"
            or path.startswith("/api/")
            or path == "/v1"
            or path.startswith("/v1/")
            or path == "/health"
        ):
            self._proxy_gateway()
            return

        if self.command not in {"GET", "HEAD"}:
            if not self._discard_request_body():
                return
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": {"message": "Endpoint not provided by Hermes Gateway UI"}},
            )
            return

        self._serve_static(path)

    def _proxy_gateway(self) -> None:
        body = self._read_request_body()
        if body is None and self.headers.get("Content-Length"):
            return

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

    def _read_request_body(self) -> bytes | None:
        if self.headers.get("Transfer-Encoding"):
            self._send_json(
                HTTPStatus.NOT_IMPLEMENTED,
                {"error": {"message": "Chunked request bodies are not supported by this bridge."}},
            )
            self.close_connection = True
            return None

        content_length = self.headers.get("Content-Length")
        if not content_length:
            return None

        try:
            size = int(content_length)
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": {"message": "Invalid Content-Length"}})
            self.close_connection = True
            return None

        if size < 0 or size > MAX_REQUEST_BYTES:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": {"message": "Request too large"}})
            self.close_connection = True
            return None

        return self.rfile.read(size)

    def _discard_request_body(self) -> bool:
        """Consume an unknown request so persistent HTTP connections stay aligned."""
        if self.command in {"GET", "HEAD"}:
            return True
        body = self._read_request_body()
        return body is not None or not self.headers.get("Content-Length")

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
