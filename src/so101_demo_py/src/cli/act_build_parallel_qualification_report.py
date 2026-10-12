"""CLI: recompute a finished exact-eight qualification run from its originals and write its qualification report.

The report is `<campaign-root>/host/qualification-report.json`, created once and never overwritten; a re-test is a new run id. A run
that does not qualify still gets its report (status NOT_QUALIFIED and the closed reason codes). Stdout is one JSON object with
`status`, `report`, `sha256` and `reasons`.

Exit codes: 0 the report was written and is QUALIFIED; 3 it was written and is NOT_QUALIFIED; 2 refused with nothing written
(arguments, a path outside the registered evidence root, an existing report, an unreadable run or contract); 1 anything unexpected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from so101_demo.act.collection_qualification_recompute import run_layout
from so101_demo.act.parallel_qualification_verifier import build_collection_qualification_report


def _parser():
    parser = argparse.ArgumentParser(prog='act_build_parallel_qualification_report', description=__doc__, allow_abbrev=False,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--contract', type=Path, required=True, help='the gate contract file the run\'s campaign config names')
    parser.add_argument('--campaign-root', type=Path, required=True, help='the finished qualification run directory')
    parser.add_argument('--registered-root', type=Path, required=True, help='the registered evidence root that holds the run')
    return parser


def _canonical(path, *, directory):
    path = Path(path)
    # a path that resolves to itself holds no symbolic link and no `..`
    if not path.is_absolute() or '..' in path.parts or path.resolve(strict=True) != path:
        raise ValueError('PATH_NOT_CANONICAL: ' + str(path))
    if not (path.is_dir() if directory else path.is_file()):
        raise ValueError('PATH_HAS_THE_WRONG_KIND: ' + str(path))
    return path


def _preflight(args):
    """The canonical contract, run and registered root; the run must be a direct child of the root and its layout must name it."""
    registered = _canonical(args.registered_root, directory=True)
    run = _canonical(args.campaign_root, directory=True)
    contract = _canonical(args.contract, directory=False)
    if run.parent != registered:
        raise ValueError('CAMPAIGN_ROOT_NOT_IN_REGISTERED_ROOT: ' + str(run))
    _, layout = run_layout(run)
    if layout['root'] != str(registered) or layout['run_id'] != run.name:
        raise ValueError('CAMPAIGN_LAYOUT_NAMES_ANOTHER_ROOT')
    return run, contract


def _describe(error):
    parts = []
    while error is not None and len(parts) < 5:
        parts.append(str(error) or type(error).__name__)
        error = error.__cause__
    return ' <- '.join(parts)


def _fail(message, code):
    print('act_build_parallel_qualification_report: ' + message, file=sys.stderr)
    return code


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        run, contract = _preflight(args)
    except (OSError, ValueError) as error:
        return _fail('REFUSED: ' + _describe(error), 2)
    try:
        report = build_collection_qualification_report(run, contract=contract)
    except ValueError as error:    # every ValueError of the builder precedes the exclusive create
        return _fail('REFUSED: ' + _describe(error), 2)
    except Exception as error:  # noqa: BLE001 - reported with the exit code for an unexpected failure
        return _fail('UNEXPECTED: ' + _describe(error), 1)
    try:
        raw = report.read_bytes()
        document = json.loads(raw)
    except (OSError, ValueError) as error:
        return _fail('UNEXPECTED: the written report cannot be read back: ' + _describe(error), 1)
    print(json.dumps(dict(status=document['status'], report=str(report), sha256=hashlib.sha256(raw).hexdigest(),
                          reasons=document['reasons']), sort_keys=True))
    return 0 if document['status'] == 'QUALIFIED' else 3


if __name__ == '__main__':
    raise SystemExit(main())
