"""Verify a public artifact manifest using SHA-256 only; no model/statistical runs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--root', type=Path, required=True, help='Root of the extracted evidence bundle')
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    document = json.loads(args.manifest.read_text(encoding='utf-8'))
    entries = document['frozen_source_files'] + document['evidence_files'] + document.get('packaging_files', [])
    failures = []
    checked = 0
    for entry in entries:
        path = (root / entry['path']).resolve()
        if not path.is_relative_to(root):
            failures.append({'path': entry['path'], 'error': 'unsafe path'})
            continue
        if not path.is_file():
            failures.append({'path': entry['path'], 'error': 'missing'})
            continue
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else None
        if digest is None:
            hasher = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    hasher.update(block)
            digest = hasher.hexdigest()
        if digest != entry['sha256']:
            failures.append({'path': entry['path'], 'error': 'hash mismatch'})
        checked += 1
    omitted_present = [entry['path'] for entry in document['omitted_files'] if (root / entry['path']).is_file()]
    print(json.dumps({'status': 'FAIL' if failures else 'PASS', 'checked_files': checked,
                      'failures': failures, 'listed_omitted_files_present_locally': omitted_present,
                      'scope': 'Byte-integrity check only; no performance recomputation'}, indent=2))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
