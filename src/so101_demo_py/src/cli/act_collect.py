"""Task 11 W1 debug CLI: build the closed collection spec and hand it to the unified service.

The CLI constructs the payload and the scene selection **before** any service exists, so a refusal
(absent input, empty selection, qualification/formal mismatch, Rollout-only manifest) happens with zero
resets, zero actions and zero children. The service is obtained through an injected factory; nothing is
loaded by module or import path.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from so101_demo.act.collection import build_collection_payload, require_collection_selection


def _service(payload: dict):
    from so101_teleop.unified.compose import compose_services  # late import, as the live CLI does

    services = compose_services()
    if services.act_workload is None or services.bridge is None:
        raise ValueError(f"TASK8_UNIFIED_SERVICE_UNAVAILABLE: {services.act_error}")
    return services.act_workload


def main(argv: list[str] | None = None, *, service_factory=None) -> int:
    parser = argparse.ArgumentParser(prog="act_collect", description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--activation-receipt", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--qualification", action="store_true")
    args = parser.parse_args(argv)

    payload = build_collection_payload(
        campaign_id="act-collection", manifest_path=args.manifest,
        calibration_report=args.calibration, policy=args.policy,
        activation_receipt=args.activation_receipt, evidence_root=args.root,
        qualification_mode=bool(args.qualification), limit=args.limit)
    manifest = json.loads(args.manifest.read_bytes())
    selection = require_collection_selection(manifest, qualification_mode=bool(args.qualification))
    planned = selection[: args.limit]
    if not planned:
        raise ValueError("COLLECTION_SELECTION_EMPTY")

    # every check has passed: only now may a service exist, and it is the injected one in tests
    service = (service_factory or _service)(payload)
    result = service.start(payload, planned)
    print(json.dumps({"qualification_mode": bool(args.qualification),
                      "scenes": planned,
                      "result": result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
