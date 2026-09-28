"""Task 11A CLI: build the closed fixed-collection spec and ask the unified service to admit it.

The spec is composed — and every refusal taken — before a service exists, so a bad invocation cannot
spawn, reset or leave a child behind.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from so101_demo.runtime.act_fixed_collection_composition import build_fixed_collection_spec


def _context_from_service():
    """The admitted context the payload needs: epoch, binding, proposal, children and source."""

    from so101_teleop.unified.compose import compose_services  # late import, as the live CLIs do

    services = compose_services()
    context = getattr(services, "act_collection_context", None)
    if context is None:
        raise ValueError(f"ACT_COLLECTION_CONTEXT_UNAVAILABLE: {services.act_error}")
    return context


def _service(payload: dict):
    from so101_teleop.unified.compose import compose_services  # late import, as the live CLIs do

    services = compose_services()
    if services.act_workload is None or services.bridge is None:
        raise ValueError(f"TASK8_UNIFIED_SERVICE_UNAVAILABLE: {services.act_error}")
    return services.act_workload


def main(argv: list[str] | None = None, *, service_factory=None, context_factory=None) -> int:
    parser = argparse.ArgumentParser(prog="act_collect_parallel", description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--activation-receipt", type=Path, required=True)
    parser.add_argument("--collection-config", type=Path, required=True)
    parser.add_argument("--runtime-config", type=Path, required=True)
    parser.add_argument("--qualification-contract", type=Path)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--qualification", action="store_true")
    parser.add_argument("--worker-count", type=int, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)

    spec = build_fixed_collection_spec(
        context=(context_factory or _context_from_service)(),
        manifest=args.manifest, split_manifest=args.split_manifest,
        calibration_report=args.calibration, policy=args.policy,
        activation_receipt=args.activation_receipt, collection_config=args.collection_config,
        runtime_config=args.runtime_config, root=args.root,
        qualification=bool(args.qualification), worker_count=args.worker_count,
        qualification_contract=args.qualification_contract, resume=bool(args.resume))
    service = (service_factory or _service)(spec)
    plane = "qualification" if spec["payload"]["qualification_mode"] else "formal"
    result = service.start(spec, {"plane": plane, "worker_count": spec["payload"]["worker_count"]})
    print(json.dumps({"plane": plane, "result": result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
