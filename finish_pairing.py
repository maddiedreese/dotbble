#!/usr/bin/env python3
"""Export only a verified non-expiring pairing after the local runtime stops."""
import json
import os
from pathlib import Path
import pairing

def finish(root):
    work = root / '.private'
    record = json.loads((work / 'runtime.json').read_text())
    if record.get('stopped_at') is None:
        raise ValueError('Stop the launcher with Control-C and wait for its stopped message first.')
    try:
        os.kill(record['pid'], 0)
    except ProcessLookupError:
        pass
    else:
        raise ValueError('The recorded runtime process still exists; verify it has stopped.')
    subs = pairing.active(work / 'state')
    if len(subs) != 1 or subs[0]['expires'] is not None:
        raise ValueError('Expected exactly one non-expiring subscription. Do not edit an expiry manually.')
    output = work / 'MY-PHONE-PAIRING.json'
    if output.exists():
        previous = json.loads(output.read_text())
        expected = subs[0]
        if previous.get('version') != 2 or previous.get('expires') is not None or any(
                previous.get(k) != expected[k] for k in ('id', 'url', 'secret')):
            raise ValueError('An older export exists. Resolve it before exporting another pairing.')
        print('Existing matching private pairing file retained; message identity was not reset.')
    else:
        pairing.export(work / 'state', output)
    print('Ready: .private/MY-PHONE-PAIRING.json — keep its contents private.')

if __name__ == '__main__':
    try:
        finish(Path(__file__).resolve().parent)
    except (ValueError, OSError, KeyError):
        raise SystemExit('Export not ready. Verify the launcher stopped, exactly one non-expiring subscription exists, and no conflicting older export exists. No credentials were printed.')
