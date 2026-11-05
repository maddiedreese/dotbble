import base64
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import bridge
import pairing

class PairingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        bridge.setup(self.directory)
        self.params = {'name': 'ring.message', 'arguments': {}, 'ttlMs': 3600000,
            'delivery': {'mode': 'webhook', 'url': 'https://chatgpt.com/test-callback',
            'secret': 'whsec_' + base64.b64encode(b'a' * 32).decode()}}

    def accept(self, url, body, headers):
        return 200, json.dumps({'challenge': json.loads(body)['challenge']}).encode()

    def test_pair_export_status_and_unsubscribe(self):
        sub = pairing.rpc(self.directory, 'events/subscribe', self.params, self.accept)
        output = self.directory / 'phone.json'
        pairing.export(self.directory, output)
        config = json.loads(output.read_text())
        self.assertEqual(config['id'], sub['id'])
        self.assertEqual(config['event'], 'ring.message')
        self.assertEqual(len(config['device_id']), 32)
        self.assertLessEqual(config['expires'], time.time() * 1000 + 3600000)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        status = pairing.rpc(self.directory, 'tools/call', {'name': 'ring_phone_pairing_status'})
        self.assertEqual(status['structuredContent']['active_subscriptions'], 1)
        self.assertNotIn(config['secret'], json.dumps(status))
        pairing.rpc(self.directory, 'events/unsubscribe', self.params)
        with self.assertRaises(ValueError): pairing.export(self.directory, output)

    def test_rejects_other_hosts_and_second_dot(self):
        for url in ['http://chatgpt.com/a', 'https://chatgpt.com.evil.test/a',
                    'https://me@chatgpt.com/a', 'https://chatgpt.com:444/a']:
            with self.assertRaises(ValueError): pairing.openai_url(url)
        pairing.rpc(self.directory, 'events/subscribe', self.params, self.accept)
        self.params['delivery']['url'] = 'https://chatgpt.com/second-dot'
        with self.assertRaises(ValueError):
            pairing.rpc(self.directory, 'events/subscribe', self.params, self.accept)

    def test_current_protocol_and_no_transcript_ingress(self):
        result = pairing.rpc(self.directory, 'initialize', {})
        self.assertEqual(result['protocolVersion'], '2026-07-28')
        for method in ['phone/send', 'webhook', 'ingest']:
            with self.assertRaises(LookupError): pairing.rpc(self.directory, method, {})

    def test_explicit_nonexpiring_survives_restart_and_time(self):
        omitted = dict(self.params)
        first = pairing.rpc(self.directory, 'events/subscribe', omitted, self.accept)
        self.assertIsNotNone(first['refreshBefore'])
        self.params['ttlMs'] = None
        sub = pairing.rpc(self.directory, 'events/subscribe', self.params, self.accept)
        self.assertIsNone(sub['refreshBefore'])
        self.assertEqual(first['id'], sub['id'])
        self.assertIsNone(bridge.load_subs(self.directory)[sub['id']]['expires'])
        future = time.time() + 90 * 86400
        with patch('time.time', return_value=future):
            output = self.directory / 'durable.json'
            pairing.export(self.directory, output)
            config = json.loads(output.read_text())
            self.assertEqual(config['version'], 2)
            self.assertIsNone(config['expires'])
            status = pairing.rpc(self.directory, 'tools/call', {'name': 'ring_phone_pairing_status'})
            self.assertEqual(status['structuredContent']['nonexpiring_subscriptions'], 1)
            pairing.rpc(self.directory, 'events/unsubscribe', self.params)
            self.assertEqual(pairing.active(self.directory), [])

    def test_omitted_ttl_records_default_without_claiming_explicit_request(self):
        self.params.pop('ttlMs')
        sub = pairing.rpc(self.directory, 'events/subscribe', self.params, self.accept)
        self.assertIsNone(sub['refreshBefore'])
        audit = json.loads((self.directory / 'last_subscription_grant.json').read_text())
        self.assertFalse(audit['ttl_explicit'])
        self.assertEqual(audit['requested_ttl_ms'], 'omitted')
        self.assertTrue(audit['used_nonexpiring_default'])

    def test_failed_verification_does_not_extend_or_replace_existing_subscription(self):
        first = pairing.rpc(self.directory, 'events/subscribe', self.params, self.accept)
        before = bridge.load_subs(self.directory)
        self.params['ttlMs'] = None
        self.params['delivery']['secret'] = 'whsec_' + base64.b64encode(b'b' * 32).decode()
        with self.assertRaises(bridge.CallbackError):
            pairing.rpc(self.directory, 'events/subscribe', self.params, lambda *_: (403, b'{}'))
        self.assertEqual(bridge.load_subs(self.directory), before)
        renewed = pairing.rpc(self.directory, 'events/subscribe', self.params, self.accept)
        self.assertEqual(first['id'], renewed['id'])
        self.assertEqual(len(pairing.active(self.directory)), 1)
        self.assertEqual(pairing.active(self.directory)[0]['secret'], self.params['delivery']['secret'])

    def test_legacy_bridge_keeps_one_hour_limit_for_null(self):
        self.params['ttlMs'] = None
        sub = bridge.dispatch(self.directory, 'events/subscribe', self.params, self.accept, event_name='ring.message')
        self.assertIsNotNone(sub['refreshBefore'])

if __name__ == '__main__': unittest.main()
