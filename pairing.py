#!/usr/bin/env python3
"""Temporary stdio MCP pairing only; never accepts or forwards phone transcripts."""
import argparse
import json
from pathlib import Path
import secrets
import sys
import time
from urllib.parse import urlsplit
import bridge
from event_schema import EVENT_DEF

EVENT = 'ring.message'

def openai_url(url):
    p = urlsplit(url)
    host = p.hostname or ''
    if (p.scheme != 'https' or p.username or p.password or p.fragment
            or p.port not in (None, 443) or not p.path
            or not any(host == d or host.endswith('.' + d) for d in ('openai.com', 'chatgpt.com'))):
        raise ValueError('An OpenAI HTTPS callback is required')

def active(directory):
    return [s for s in bridge.load_subs(directory).values()
            if s.get('name') == EVENT and (s['expires'] is None or s['expires'] > time.time())]

def rpc(directory, method, params, post=bridge.safe_post):
    if not isinstance(params, dict):
        raise ValueError('Expected object params')
    if method == 'events/list':
        event = dict(EVENT_DEF, description='A transcript sent directly by the owner\'s Pebble phone plugin to OpenAI. This setup server does not receive transcripts. Subscriptions default to no expiration; explicit finite TTL requests remain finite. Follow the user\'s subscription instructions.')
        return {'events': [event]}
    if method == 'tools/list':
        return {'tools': [dict(bridge.TOOL, name='ring_phone_pairing_status', title='Ring phone pairing status', description='Read the count of active phone subscriptions. No transcript access or message sending.')]}
    if method == 'tools/call':
        if params.get('name') != 'ring_phone_pairing_status' or params.get('arguments', {}) != {}:
            raise ValueError('Unknown tool or arguments')
        subs = active(directory)
        value = {'event': EVENT, 'active_subscriptions': len(subs),
                 'nonexpiring_subscriptions': sum(s['expires'] is None for s in subs),
                 'phone_delivery_verified': False}
        return {'content': [{'type': 'text', 'text': json.dumps(value)}], 'structuredContent': value}
    if method == 'events/subscribe':
        url = params.get('delivery', {}).get('url', '')
        openai_url(url)
        if any(s['url'] != url for s in active(directory)):
            raise ValueError('Only one dot may pair with this state directory')
    # The working setup uses a non-expiring default when ChatGPT omits ttlMs.
    # Preserve explicit finite requests and record whether a TTL was supplied.
    result = bridge.dispatch(directory, method, params, post, event_name=EVENT,
                             allow_nonexpiring=True, default_ttl_ms=None)
    if method == 'events/subscribe':
        # Proof of the actual negotiated lifetime, without callback credentials.
        bridge.write_private(directory / 'last_subscription_grant.json', {
            'granted_at': bridge.iso(), 'subscription_id': result['id'],
            'ttl_explicit': 'ttlMs' in params,
            'requested_ttl_ms': params.get('ttlMs', 'omitted'),
            'refresh_before': result['refreshBefore'],
            'used_nonexpiring_default': 'ttlMs' not in params and result['refreshBefore'] is None,
            'callback_verified': True,
        })
    if method in ('initialize', 'server/discover'):
        result['serverInfo'] = {'name': 'dotbble-pairing', 'version': '1.0.0'}
        if method == 'initialize':
            result['protocolVersion'] = '2026-07-28'
            result['instructions'] = 'Dotbble phone pairing: default subscription lifetime is non-expiring (refreshBefore: null), including when ttlMs is omitted. Explicit finite TTL requests last at most one hour. The server also supports explicit ttlMs: null requests. After pairing the setup server can stop; events are sent directly by the phone. Event text is governed by the user\'s subscription instructions.'
    return result

def export(directory, output):
    subs = active(directory)
    if len(subs) != 1:
        raise ValueError('Exactly one active dot subscription is required')
    s = subs[0]
    openai_url(s['url'])
    bridge.secret_bytes(s['secret'])
    if s['expires'] is not None and s['expires'] > time.time() + 3600:
        raise ValueError('Subscription exceeds the one-hour test limit')
    bridge.write_private(output, {'version': 2 if s['expires'] is None else 1, 'event': EVENT, 'id': s['id'],
        'url': s['url'], 'secret': s['secret'], 'expires': None if s['expires'] is None else int(s['expires'] * 1000),
        'device_id': secrets.token_hex(16)})

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['serve', 'export'])
    p.add_argument('--state', type=Path, required=True)
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    bridge.setup(args.state)
    if args.mode == 'export':
        if args.output is None:
            p.error('--output is required for export')
        export(args.state, args.output)
        print('Private pairing file saved. Do not paste it into chat.')
        return
    for line in sys.stdin:
        request = {}
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError('Expected request')
            if 'id' not in request:
                continue
            result = rpc(args.state, request.get('method'), request.get('params', {}))
            response = {'jsonrpc': '2.0', 'id': request['id'], 'result': result}
        except Exception:
            # Callback errors may contain private URLs. Do not echo them.
            response = {'jsonrpc': '2.0', 'id': request.get('id') if isinstance(request, dict) else None,
                        'error': {'code': -32602, 'message': 'Pairing request failed; check parameters and callback availability.'}}
        print(json.dumps(response), flush=True)

if __name__ == '__main__':
    main()
