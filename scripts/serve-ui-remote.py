#!/usr/bin/env python3
"""Serve a CI UI remote read-only with explicit cross-origin script support."""

from __future__ import annotations

import argparse
import base64
import json
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

AUTH_PATH = "/realms/inari/protocol/openid-connect/auth"
TOKEN_PATH = "/realms/inari/protocol/openid-connect/token"


def jwt(payload: dict[str, object]) -> str:
    def encode(value: dict[str, object]) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{encode({'alg': 'none', 'typ': 'JWT'})}.{encode(payload)}."


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        origin = self.headers.get("Origin")
        self.send_header("Access-Control-Allow-Origin", origin or "*")
        if origin:
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Vary", "Origin")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if not getattr(self.server, "oidc_fixture", False) or parsed.path != AUTH_PATH:
            super().do_GET()
            return
        query = parse_qs(parsed.query)
        redirect = query.get("redirect_uri", [""])[0]
        state = query.get("state", [""])[0]
        if not redirect or not state:
            self.send_error(400, "OIDC fixture requires redirect_uri and state")
            return
        callback = urlsplit(redirect)
        self.server.oidc_nonce = query.get("nonce", [""])[0]
        fragment = urlencode({
            "code": "browser-compat-code",
            "state": state,
            "session_state": "browser-compat-session",
        })
        location = urlunsplit((callback.scheme, callback.netloc, callback.path, callback.query, fragment))
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def do_POST(self) -> None:
        if not getattr(self.server, "oidc_fixture", False) or urlsplit(self.path).path != TOKEN_PATH:
            self.send_error(501)
            return
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        now = int(time.time())
        token = jwt({
            "iss": f"http://{self.headers.get('Host', 'localhost')}/realms/inari",
            "aud": "inari-ui",
            "azp": "inari-ui",
            "sub": "browser-compat-user",
            "iat": now,
            "exp": now + 3600,
            "nonce": getattr(self.server, "oidc_nonce", ""),
            "organization": {"acme": {"name": "Acme Corp"}},
        })
        body = json.dumps({
            "access_token": token,
            "id_token": token,
            "refresh_token": token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_expires_in": 3600,
            "scope": "openid organization:*",
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def make_server(directory: Path, port: int, oidc_fixture: bool = False) -> ThreadingHTTPServer:
    directory = directory.resolve()
    handler = lambda *items, **kwargs: Handler(*items, directory=str(directory), **kwargs)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    server.oidc_fixture = oidc_fixture
    server.oidc_nonce = ""
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--oidc-fixture", action="store_true", help="Enable the browser-only local OIDC fixture")
    args = parser.parse_args()
    make_server(args.directory, args.port, args.oidc_fixture).serve_forever()


if __name__ == "__main__":
    main()
