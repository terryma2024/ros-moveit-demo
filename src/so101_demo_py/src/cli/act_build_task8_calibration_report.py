"""Rebuild the Task 8 calibration outputs from sealed batches. Purely offline.

This entry point never starts ROS, MuJoCo or a model, and it exposes no way to override the
derived status: the report is whatever the sealed evidence supports.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate sealed Task 8 calibration batches into report outputs")
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--identities", type=Path, required=True,
                        help="JSON document with the five frozen identity hashes")
    parser.add_argument("--batch-root", type=Path, action="append", required=True,
                        dest="batch_roots")
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)

    from so101_demo.act.calibration import require_gate
    from so101_demo.act.task8_calibration_aggregator import (
        publish_task8_calibration, render_task8_calibration,
    )
    from so101_demo.act.task8_measurement_contract import load_measurement_contract

    if len(args.batch_roots) != 1:
        raise ValueError("ONE_V2_SEALED_BATCH_REQUIRED: one batch carries exactly three anchors")
    identities = json.loads(args.identities.read_text())
    contract = load_measurement_contract(args.contract, expected_hashes=identities)
    # render against the caller's real output root, so every sample_path is absolute and stable before publishing
    rendered = render_task8_calibration(args.batch_roots[0], contract, args.output_root)
    published = publish_task8_calibration(rendered, args.output_root)
    report = json.loads(rendered["head-search-qualification.json"])
    # the published report must satisfy the production gate: an unqualified dataset fails here rather than
    # producing a quiet artefact, and the runtime binding check belongs with the live producer in Task 7
    require_gate(report, "task8_live")
    print(published)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
