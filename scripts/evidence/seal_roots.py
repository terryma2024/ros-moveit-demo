"""Seal evidence roots: per-file sha256 manifest, read-only files and directories, SEALED.json in each root, and the registry
REG/SEALED-ROOTS.json that every cleanup script must consult (refuse any path inside or above a sealed root).

Human (2026-10-17): "之前成功的69条封存，避免在清理证据是被误清理".
Usage: seal_roots.py [--registry-root DIR] <reason> <root> [<root> ...]
SEAL_WORKERS (default 16) is the number of threads that hash the files of a root (hashlib and file reads release the GIL); 1 is the serial
loop. The manifest lines are written in the order the serial loop wrote them (directories sorted, files sorted), so the manifest, SEALED.json
(but for `sealed_at`) and the registry do not depend on the thread count.
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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REG = None        # registry root, set by main()
REGISTRY = None   # REG / 'SEALED-ROOTS.json'
WORKERS = 16      # hashing threads, set by main() from SEAL_WORKERS


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
    # the entries in the serial order; regular files are hashed ahead by the pool and consumed in that order
    entries = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            p = Path(dirpath) / name
            rel = str(p.relative_to(root))
            if p.is_symlink():
                entries.append((rel, 'symlink', os.readlink(p), None))
            elif not p.is_file():
                entries.append((rel, 'special', None, None))
            else:
                entries.append((rel, 'file', p, p.stat().st_size))
    with manifest.open('x') as out, ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(sha256, item[2]) if item[1] == 'file' else None for item in entries] if WORKERS > 1 else None
        for index, (rel, kind, target, size) in enumerate(entries):
            if kind == 'symlink':
                out.write(json.dumps(dict(path=rel, symlink=target)) + '\n')
                links += 1
            elif kind == 'special':
                out.write(json.dumps(dict(path=rel, special=True)) + '\n')
            else:
                digest = futures[index].result() if futures is not None else sha256(target)
                out.write(json.dumps(dict(path=rel, bytes=size, sha256=digest)) + '\n')
                files += 1
                total += size
                if futures is not None:
                    futures[index] = None       # release the result as soon as it is written
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
    global REG, REGISTRY, WORKERS
    parser = argparse.ArgumentParser(description='Seal evidence roots under the registry root.')
    parser.add_argument('--registry-root', default=os.environ.get('EVIDENCE_ROOT'), help='default: $EVIDENCE_ROOT')
    parser.add_argument('reason')
    parser.add_argument('roots', nargs='+')
    args = parser.parse_args(argv)
    if not args.registry_root:
        parser.error('--registry-root is required (EVIDENCE_ROOT is not set)')
    try:
        WORKERS = int(os.environ.get('SEAL_WORKERS', '16'))
        if WORKERS < 1:
            raise ValueError
    except ValueError:
        parser.error('SEAL_WORKERS must be a positive integer, got %r' % os.environ.get('SEAL_WORKERS'))
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
