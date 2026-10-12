"""CLI: independently verify a container-collection qualification report by recomputing its run, and print the proof.

Nothing the report says is used and nothing is written. Without the identity options the comparison with an externally supplied
controlled identity is skipped; with them it is exactly the one formal admission makes (`--campaign-config`, `--source`,
`--runtime-config`, `--collection-config` and `--contact-policy-fingerprint` are all given or none is).

Exit codes: 0 verified (the proof is the stdout JSON); 3 verification refused (not a report, not QUALIFIED, the recomputation
differs, the identity differs); 2 usage or path refusal; 1 anything unexpected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from so101_demo.act.parallel_qualification_verifier import verify_collection_qualification
from so101_demo.runtime.inference.config import load_campaign_config

_IDENTITY_OPTIONS = ('campaign_config', 'source', 'runtime_config', 'collection_config', 'contact_policy_fingerprint')
_REFUSED = 'COLLECTION_QUALIFICATION_'
_PATH_REFUSED = 'COLLECTION_QUALIFICATION_PATH_INVALID'


def _parser():
    parser = argparse.ArgumentParser(prog='act_verify_parallel_qualification', description=__doc__, allow_abbrev=False,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--report', type=Path, required=True, help='<run>/host/qualification-report.json')
    parser.add_argument('--registered-root', type=Path, required=True, help='the registered evidence root that holds the run')
    parser.add_argument('--campaign-config', type=Path)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--runtime-config', type=Path)
    parser.add_argument('--collection-config', type=Path)
    parser.add_argument('--contact-policy-fingerprint')
    return parser


def _sha(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('IDENTITY_INPUT_UNREADABLE: ' + str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _expected_identity(args):
    """The controlled identity formal admission compares, built by admission's own expression; `None` when no option is given."""
    given = [name for name in _IDENTITY_OPTIONS if getattr(args, name) is not None]
    if not given:
        return None
    if len(given) != len(_IDENTITY_OPTIONS):
        raise ValueError('identity arguments are all or none: missing --' + ', --'.join(
            name.replace('_', '-') for name in _IDENTITY_OPTIONS if name not in given))
    if re.fullmatch(r'[0-9a-f]{64}', args.contact_policy_fingerprint) is None:
        raise ValueError('identity argument --contact-policy-fingerprint is not a sha256 hex digest')
    from so101_teleop.unified.admission import _collection_identity

    config = load_campaign_config(args.campaign_config, roles=('teacher',), expected_sha256=_sha(args.campaign_config))
    payload = dict(source_sha256=_sha(args.source), runtime_config_sha256=_sha(args.runtime_config),
                   collection_config_sha256=_sha(args.collection_config),
                   contact_policy_fingerprint=args.contact_policy_fingerprint)
    return _collection_identity(payload, config)


def _describe(error):
    parts = []
    while error is not None and len(parts) < 5:
        parts.append(str(error) or type(error).__name__)
        error = error.__cause__
    return ' <- '.join(parts)


def _fail(message, code):
    print('act_verify_parallel_qualification: ' + message, file=sys.stderr)
    return code


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        identity = _expected_identity(args)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return _fail('REFUSED: ' + _describe(error), 2)
    try:
        proof = verify_collection_qualification(args.report, registered_root=args.registered_root, expected_identity=identity)
    except ValueError as error:
        message = _describe(error)
        if not str(error).startswith(_REFUSED):
            return _fail('UNEXPECTED: ' + message, 1)
        return _fail('REFUSED: ' + message, 2 if str(error) == _PATH_REFUSED else 3)
    except Exception as error:  # noqa: BLE001 - reported with the exit code for an unexpected failure
        return _fail('UNEXPECTED: ' + _describe(error), 1)
    print(json.dumps(proof, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
