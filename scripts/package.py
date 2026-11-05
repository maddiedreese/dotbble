#!/usr/bin/env python3
"""Build a deterministic plugin-only PBW; no Pebble SDK or ring required."""
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def package():
    metadata = json.loads((ROOT / 'phone/package.json').read_text())
    manifest = dict(metadata['pebble'])
    manifest.update(
        manifestVersion=2, shortName=manifest['displayName'],
        longName=manifest['displayName'], companyName=metadata['author'],
        versionLabel=metadata['version'], resources={'media': []},
        watchapp={'watchface': False},
    )
    files = {
        'appinfo.json': (json.dumps(manifest, indent=2) + '\n').encode(),
        'plugin.js': (ROOT / 'build/plugin.js').read_bytes(),
        'config.html': (ROOT / 'phone/config.html').read_bytes(),
        'LICENSE': (ROOT / 'LICENSE').read_bytes(),
        'LICENSE-noble-hashes.txt': (ROOT / 'phone/LICENSE-noble-hashes.txt').read_bytes(),
    }
    buffer = io.BytesIO()
    # Stored entries avoid platform-dependent compression output. The artifact is small.
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, data in files.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    artifact = buffer.getvalue()
    checksum = (hashlib.sha256(artifact).hexdigest() + '  dotbble.pbw\n').encode()
    outputs = {'dotbble.pbw': artifact, 'SHA256SUMS.txt': checksum}
    directory = ROOT / 'dist'
    if '--check' in sys.argv:
        for name, data in outputs.items():
            if (directory / name).read_bytes() != data:
                raise SystemExit(f'dist/{name} differs from the source build')
        print('Committed PBW and checksum match the source build.')
    else:
        directory.mkdir(exist_ok=True)
        for name, data in outputs.items():
            (directory / name).write_bytes(data)
        print('Packaged dist/dotbble.pbw')


if __name__ == '__main__':
    package()
