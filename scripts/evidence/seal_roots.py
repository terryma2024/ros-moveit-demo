"""Seal evidence roots: per-file sha256 manifest, read-only files and directories, SEALED.json in each root, and the registry
REG/SEALED-ROOTS.json that every cleanup script must consult (refuse any path inside or above a sealed root).

Human (2026-10-17): "之前成功的69条封存，避免在清理证据是被误清理".
Usage: seal_roots.py [--registry-root DIR] <reason> <root> [<root> ...]
DIR is the evidence root that holds SEALED-ROOTS.json and under which every sealed root must lie; the default is
$EVIDENCE_ROOT (host value, scripts/gate/hosts/<host>.env; load it with scripts/gate/load_host.zsh).
"""
import argparse
import hashlib
import json
import os
import stat
import sys
import time
from pathlib import Path

REG = None        # registry root, set by main()
REGISTRY = None   # REG / 'SEALED-ROOTS.json'


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def seal(root, reason):
    root = Path(root).resolve()
    assert root.is_dir() and REG in root.parents, root
    manifest = root.parent / (root.name + '.seal-manifest.jsonl')
    assert not manifest.exists() and not (root / 'SEALED.json').exists(), 'already sealed: %s' % root
    files = total = links = 0
    with manifest.open('x') as out:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            for name in sorted(filenames):
                p = Path(dirpath) / name
                rel = str(p.relative_to(root))
                if p.is_symlink():
                    out.write(json.dumps(dict(path=rel, symlink=os.readlink(p))) + '\n')
                    links += 1
                    continue
                if not p.is_file():
                    out.write(json.dumps(dict(path=rel, special=True)) + '\n')
                    continue
                size = p.stat().st_size
                out.write(json.dumps(dict(path=rel, bytes=size, sha256=sha256(p))) + '\n')
                files += 1
                total += size
    manifest_sha = sha256(manifest)
    record = dict(kind='SEALED_EVIDENCE_ROOT', root=str(root), reason=reason, sealed_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                  files=files, bytes=total, symlinks=links, manifest=str(manifest), manifest_sha256=manifest_sha)
    (root / 'SEALED.json').write_text(json.dumps(record, indent=1) + '\n')
    # read-only: files first, then directories bottom-up (a directory without write permission refuses unlink of its entries)
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        for name in filenames:
            p = Path(dirpath) / name
            if not p.is_symlink():
                os.chmod(p, p.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        os.chmod(dirpath, os.stat(dirpath).st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    os.chmod(manifest, 0o444)
    return record


def main(argv=None):
    global REG, REGISTRY
    parser = argparse.ArgumentParser(description='Seal evidence roots under the registry root.')
    parser.add_argument('--registry-root', default=os.environ.get('EVIDENCE_ROOT'), help='default: $EVIDENCE_ROOT')
    parser.add_argument('reason')
    parser.add_argument('roots', nargs='+')
    args = parser.parse_args(argv)
    if not args.registry_root:
        parser.error('--registry-root is required (EVIDENCE_ROOT is not set)')
    REG = Path(args.registry_root).resolve()
    REGISTRY = REG / 'SEALED-ROOTS.json'
    reason, roots = args.reason, args.roots
    registry = json.loads(REGISTRY.read_text()) if REGISTRY.exists() else dict(kind='SEALED_ROOTS_REGISTRY', roots=[])
    for root in roots:
        record = seal(root, reason)
        registry['roots'].append(record)
        print(json.dumps({k: record[k] for k in ('root', 'files', 'bytes', 'manifest_sha256')}))
    if REGISTRY.exists():
        os.chmod(REGISTRY, 0o644)
    REGISTRY.write_text(json.dumps(registry, indent=1) + '\n')
    os.chmod(REGISTRY, 0o444)


if __name__ == '__main__':
    main()
