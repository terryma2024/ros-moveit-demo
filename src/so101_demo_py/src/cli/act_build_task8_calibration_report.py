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

    from so101_demo.act.task8_calibration_aggregator import aggregate_task8_calibration
    from so101_demo.act.task8_measurement_contract import load_measurement_contract

    identities = json.loads(args.identities.read_text())
    contract = load_measurement_contract(args.contract, expected_hashes=identities)
    outputs = aggregate_task8_calibration(tuple(args.batch_roots), contract, args.output_root)
    print(outputs["aggregation_receipt"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
