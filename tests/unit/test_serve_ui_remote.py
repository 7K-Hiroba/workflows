from __future__ import annotations

import base64
import http.client
import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/serve-ui-remote.py"
SPEC = importlib.util.spec_from_file_location("serve_ui_remote", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
make_server = MODULE.make_server


class ServeUiRemoteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        (self.directory / "remoteEntry.js").write_text("remote")
        self.server = make_server(self.directory, 0, oidc_fixture=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, method: str, path: str, headers: dict[str, str] | None = None) -> http.client.HTTPResponse:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        self.addCleanup(connection.close)
        return response

    def test_oidc_authorization_uses_fragment_callback(self) -> None:
        response = self.request(
            "GET",
            "/realms/inari/protocol/openid-connect/auth?redirect_uri=http%3A%2F%2F127.0.0.1%3A5173%2Facme%2Fextensions&state=state-1&nonce=nonce-1",
        )
        self.assertEqual(response.status, 302)
        callback = urlsplit(response.getheader("Location"))
        fragment = parse_qs(callback.fragment)
        self.assertEqual(callback.path, "/acme/extensions")
        self.assertEqual(fragment["code"], ["browser-compat-code"])
        self.assertEqual(fragment["state"], ["state-1"])
        self.assertEqual(fragment["session_state"], ["browser-compat-session"])

    def test_oidc_token_contains_browser_only_organization_claim(self) -> None:
        self.request(
            "GET",
            "/realms/inari/protocol/openid-connect/auth?redirect_uri=http%3A%2F%2F127.0.0.1%3A5173%2Facme%2Fextensions&state=state-1&nonce=nonce-1",
        )
        response = self.request(
            "POST",
            "/realms/inari/protocol/openid-connect/token",
            headers={"Origin": "http://127.0.0.1:5173"},
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Access-Control-Allow-Origin"), "http://127.0.0.1:5173")
        self.assertEqual(response.getheader("Access-Control-Allow-Credentials"), "true")
        payload = json.loads(response.read())
        self.assertEqual(payload["token_type"], "Bearer")
        self.assertEqual(payload["scope"], "openid organization:*")
        parts = payload["access_token"].split(".")
        self.assertEqual(len(parts), 3)
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        self.assertEqual(claims["organization"], {"acme": {"name": "Acme Corp"}})
        self.assertEqual(claims["nonce"], "nonce-1")

    def test_plain_server_keeps_static_remote_behavior(self) -> None:
        response = self.request("GET", "/remoteEntry.js")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.read(), b"remote")


if __name__ == "__main__":
    unittest.main()
