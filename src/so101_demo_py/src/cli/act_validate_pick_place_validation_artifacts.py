"""Validate a prepared pick-place validation bundle without starting ROS, MuJoCo or a worker.

Read-only by construction: it resolves the receipt, verifies every bundled artifact hash and the
frozen identities, and prints the resolved bundle root. It acquires no lease and starts nothing.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a committed pick-place validation preparation receipt and its bundle")
    parser.add_argument("--preparation-receipt", type=Path, required=True)
    args = parser.parse_args(argv)

    from so101_demo.act.pick_place_validation_artifact_bundle import validate_pick_place_validation_startup_artifacts

    receipt = Path(args.preparation_receipt)
    if not receipt.is_file():
        # fail closed: an absent receipt is never a valid bundle
        raise ValueError("PICK_PLACE_VALIDATION_PREPARATION_REQUIRED")
    payload = {
        "preparation_receipt_path": str(receipt.resolve()),
        "preparation_receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
    }
    verified = validate_pick_place_validation_startup_artifacts(payload)
    print(Path(verified.receipt).parent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
