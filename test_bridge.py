import base64
import hashlib
import hmac
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
import bridge

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        bridge.setup(self.directory)
        self.params = {"name": bridge.EVENT, "arguments": {}, "delivery": {
            "mode": "webhook", "url": "https://example.com/callback",
            "secret": "whsec_" + base64.b64encode(b"a" * 32).decode()}}

    def accept(self, url, body, headers):
        payload = json.loads(body)
        expected = hmac.new(b"a" * 32, (headers["webhook-id"] + "." + headers["webhook-timestamp"] + ".").encode() + body, hashlib.sha256).digest()
        self.assertEqual(headers["webhook-signature"], "v1," + base64.b64encode(expected).decode())
        return 200, json.dumps({"challenge": payload.get("challenge")}).encode()

    def subscribe(self):
        return bridge.dispatch(self.directory, "events/subscribe", self.params, self.accept)

    def test_subscribe_persist_and_unsubscribe(self):
        result = self.subscribe()
        self.assertEqual(self.subscribe()["id"], result["id"])
        self.assertEqual(len(bridge.load_subs(self.directory)), 1)
        self.assertEqual((self.directory / "subscriptions.json").stat().st_mode & 0o777, 0o600)
        bridge.dispatch(self.directory, "events/unsubscribe", self.params)
        bridge.dispatch(self.directory, "events/unsubscribe", self.params)
        self.assertEqual(bridge.load_subs(self.directory), {})

    def test_bad_verification_never_persisted(self):
        with self.assertRaises(bridge.CallbackError):
            bridge.dispatch(self.directory, "events/subscribe", self.params, lambda *a: (200, b'{"challenge":"wrong"}'))
        self.assertEqual(bridge.load_subs(self.directory), {})

    def test_callback_rejects_private_and_mixed_dns(self):
        for ip in ["127.0.0.1", "10.0.0.1", "169.254.169.254", "100.64.0.1", "::1", "::ffff:127.0.0.1", "224.0.0.1"]:
            rows = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8",443)), (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip,443))]
            with patch("socket.getaddrinfo", return_value=rows), self.assertRaises(ValueError):
                bridge.callback_target("https://example.com/callback")

    def test_url_constraints(self):
        for url in ["http://example.com", "https://user:pass@example.com", "https://example.com:8443", "https://example.com/#fragment"]:
            with self.assertRaises(ValueError):
                bridge.callback_target(url)



    def test_bad_secret_and_filters(self):
        self.params["delivery"]["secret"] = "whsec_bad"
        with self.assertRaises(ValueError):
            self.subscribe()
        with self.assertRaises(ValueError):
            bridge.dispatch(self.directory, "events/subscribe", {"name": "unknown"})


if __name__ == "__main__":
    unittest.main()
