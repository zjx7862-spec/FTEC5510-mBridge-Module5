"""Verify the pinned upstream hash, apply the patch in isolation and compare bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream-file', type=Path, help='Use an already-downloaded pinned engine.py')
    args = parser.parse_args()
    metadata = json.loads((ROOT/'docs/upstream_engine.json').read_text())
    data = (args.upstream_file.read_bytes() if args.upstream_file else
            urllib.request.urlopen(metadata['url'], timeout=30).read())
    if hashlib.sha256(data).hexdigest() != metadata['sha256']:
        raise ValueError('Upstream SHA256 mismatch; wrong file or commit')
    git = shutil.which('git')
    if not git:
        raise RuntimeError('Git is required for patch verification')
    with tempfile.TemporaryDirectory(prefix='module5-patch-') as directory:
        target = Path(directory)/'module3/m3engine/engine.py'
        target.parent.mkdir(parents=True)
        target.write_bytes(data)
        patch = str(ROOT/'docs/module3.patch')
        subprocess.run([git, 'apply', '--check', patch], cwd=directory, check=True)
        subprocess.run([git, 'apply', patch], cwd=directory, check=True)
        if target.read_bytes() != (ROOT/'vendor/m3engine/engine.py').read_bytes():
            raise ValueError('Applied patch differs from the delivered engine')
    print('Pinned upstream hash verified; git apply --check and apply passed; engine bytes match.')


if __name__ == '__main__':
    main()
