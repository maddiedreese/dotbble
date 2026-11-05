import base64
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import bridge
import pairing
import finish_pairing

class ExportTests(unittest.TestCase):
    def test_export_is_private_and_repeat_retains_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = root / '.private' / 'state'
            bridge.setup(state)
            params = {'name': 'ring.message', 'arguments': {}, 'delivery': {
                'mode': 'webhook', 'url': 'https://chatgpt.com/test-callback',
                'secret': 'whsec_' + base64.b64encode(b'a' * 32).decode()}}
            def accept(url, body, headers):
                return 200, json.dumps({'challenge': json.loads(body)['challenge']}).encode()
            pairing.rpc(state, 'events/subscribe', params, accept)
            record = root / '.private' / 'runtime.json'
            record.write_text(json.dumps({'pid': 12345, 'stopped_at': None}))
            with self.assertRaises(ValueError):
                finish_pairing.finish(root)
            record.write_text(json.dumps({'pid': 12345, 'stopped_at': 1}))
            with patch('os.kill', side_effect=ProcessLookupError), contextlib.redirect_stdout(io.StringIO()):
                finish_pairing.finish(root)
                output = root / '.private' / 'MY-PHONE-PAIRING.json'
                initial = output.read_bytes()
                finish_pairing.finish(root)
                self.assertEqual(initial, output.read_bytes())
                self.assertEqual(output.stat().st_mode & 0o777, 0o600)
                self.assertIsNone(json.loads(initial)['expires'])
                params['ttlMs'] = 3600000
                pairing.rpc(state, 'events/subscribe', params, accept)
                with self.assertRaises(ValueError):
                    finish_pairing.finish(root)

if __name__ == '__main__':
    unittest.main()
