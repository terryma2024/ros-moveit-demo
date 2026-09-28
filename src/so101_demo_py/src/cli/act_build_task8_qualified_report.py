"""Derive an immutable `QUALIFIED` calibration report from a completed live campaign.

Read-only with respect to its inputs: the `TASK8_READY` report is never rewritten, and nothing is
published unless every gate passes.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a QUALIFIED Task 8 calibration report from live campaign evidence")
    parser.add_argument("--task8-ready", type=Path, required=True)
    parser.add_argument("--preparation-receipt", type=Path, required=True)
    parser.add_argument("--campaign-result", type=Path, required=True)
    parser.add_argument("--case-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    from so101_demo.act.task8_live_qualification import build_task8_qualified_report

    print(build_task8_qualified_report(args.task8_ready, args.preparation_receipt,
                                       args.campaign_result, args.case_root, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
