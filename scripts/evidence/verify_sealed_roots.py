"""Read back every sealed root against its seal manifest (manifest sha256, then per-file bytes and sha256, symlink targets,
no extra or missing files). Written for the 2026-10-18 evidence partition migration.
Usage: verify_sealed_roots.py [--registry-root DIR] [workers]   (DIR default: $EVIDENCE_ROOT, a host value; workers default 16)"""
import argparse
import hashlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path



def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(8 << 20), b''):
            h.update(c)
    return h.hexdigest()


def check(args):
    root, e = args
    p = Path(root) / e['path']
    if 'symlink' in e:
        return None if p.is_symlink() and os.readlink(p) == e['symlink'] else 'SYMLINK ' + str(p)
    if e.get('special'):
        return None
    if p.is_symlink() or not p.is_file() or p.stat().st_size != e['bytes']:
        return 'SIZE ' + str(p)
    return None if sha256(p) == e['sha256'] else 'SHA ' + str(p)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read back every sealed root against its seal manifest.')
    parser.add_argument('--registry-root', default=os.environ.get('EVIDENCE_ROOT'), help='default: $EVIDENCE_ROOT')
    parser.add_argument('workers', nargs='?', type=int, default=16)
    args = parser.parse_args(argv)
    if not args.registry_root:
        parser.error('--registry-root is required (EVIDENCE_ROOT is not set)')
    REG = Path(args.registry_root)
    workers = args.workers
    bad, total = [], 0
    with ProcessPoolExecutor(workers) as ex:
        for item in json.loads((REG / 'SEALED-ROOTS.json').read_text())['roots']:
            root = Path(item['root'])
            rec = json.loads((root / 'SEALED.json').read_text())
            man = Path(rec['manifest'])
            if sha256(man) != rec['manifest_sha256']:
                bad.append('MANIFEST ' + str(man))
                continue
            entries = [json.loads(line) for line in man.read_text().splitlines()]
            listed = {e['path'] for e in entries}
            present = {str(Path(d, f).relative_to(root)) for d, _, fs in os.walk(root) for f in fs} - {'SEALED.json'}
            extra, missing = present - listed, listed - present
            bad += ['EXTRA %s/%s' % (root, x) for x in sorted(extra)] + ['MISSING %s/%s' % (root, x) for x in sorted(missing)]
            errs = [r for r in ex.map(check, [(str(root), e) for e in entries], chunksize=64) if r]
            bad += errs
            total += len(entries)
            print('%s files=%d bytes=%d errors=%d extra=%d missing=%d' % (root.name, len(entries), rec['bytes'], len(errs),
                                                                         len(extra), len(missing)), flush=True)
    print('TOTAL entries', total, 'problems', len(bad))
    for b in bad[:50]:
        print(b)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
