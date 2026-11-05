#!/usr/bin/env python3
"""Interactive, temporary OpenAI tunnel launcher. No API key is saved to disk."""
import getpass
import json
import os
from pathlib import Path
import re
import shlex
import signal
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
WORK = ROOT / '.private'
CLIENT = Path(shutil.which('tunnel-client') or ROOT / 'tools' / 'tunnel-client')

def main():
    if not sys.stdin.isatty():
        raise SystemExit('Run this in your own Terminal so the API-key entry can be hidden.')
    WORK.mkdir(mode=0o700, parents=True, exist_ok=True)
    print('Temporary OpenAI pairing only. Phone transcripts will not pass through this program.')
    tunnel_id = input('Your own OpenAI tunnel ID: ').strip()
    client = CLIENT
    if not client.is_file():
        client = Path(input('Full path to your downloaded tunnel-client executable: ').strip()).expanduser()
    if not client.is_file() or not os.access(client, os.X_OK):
        raise SystemExit('Tunnel client is missing or not executable. Install the official client first.')
    if not re.fullmatch(r'tunnel_[A-Za-z0-9_-]+', tunnel_id):
        raise SystemExit('Invalid tunnel ID.')
    key = getpass.getpass('OpenAI runtime API key (hidden; not saved): ').strip()
    if not key or any(c.isspace() for c in key):
        raise SystemExit('Invalid API key.')
    # Do not inherit unrelated proxy, debug, or tunnel settings.
    env = {k: os.environ[k] for k in ('HOME', 'PATH', 'TMPDIR', 'LANG') if k in os.environ}
    env['CONTROL_PLANE_API_KEY'] = key
    del key
    command = shlex.join([sys.executable, str(Path(__file__).with_name('pairing.py')),
                         'serve', '--state', str(WORK / 'state')])
    flags = ['--control-plane.tunnel-id', tunnel_id,
             '--control-plane.api-key', 'env:CONTROL_PLANE_API_KEY',
             '--control-plane.base-url', 'https://api.openai.com',
             '--mcp.command', 'command=' + command,
             '--health.listen-addr', '127.0.0.1:0',
             '--health.url-file', str(WORK / 'health.url')]
    print('Checking configuration...')
    check = subprocess.run([str(client), 'doctor', *flags, '--explain'], env=env)
    if check.returncode:
        raise SystemExit('Configuration check failed. No pairing runtime was started.')
    print('Starting temporary pairing. Leave this window open; Ctrl+C stops both processes.')
    child = subprocess.Popen([str(client), 'run', *flags], env=env, start_new_session=True)
    env.pop('CONTROL_PLANE_API_KEY', None)
    record = {'tunnel_id': tunnel_id, 'pid': child.pid, 'started_at': time.time(), 'stopped_at': None}
    status_file = WORK / 'runtime.json'
    status_file.write_text(json.dumps(record))
    try:
        child.wait()
    except KeyboardInterrupt:
        os.killpg(child.pid, signal.SIGTERM)
        try: child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
    finally:
        # Also terminate any stdio descendants left after the tunnel exits.
        try: os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError: pass
        record['stopped_at'] = time.time()
        record['exit_code'] = child.returncode
        status_file.write_text(json.dumps(record))
        print('Pairing runtime stopped. Do not restart it for the phone delivery test.')

if __name__ == '__main__': main()
