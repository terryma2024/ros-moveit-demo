"""Task 14 CLI: compose a search-to-ACT session and submit only its OperationSpec.

The command builds the composition — which is where the mode gates and the artifact checks live — and then
hands a spec to the unified service. It never touches a controller, a socket or an inference process itself.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from so101_demo.runtime.act_composition import MODES, build_act_session_composition


def _composition_ports():
    """The admitted context and ports the composition needs, from the unified service."""

    from so101_teleop.unified.compose import compose_services  # late import, as the live CLIs do

    services = compose_services()
    context = getattr(services, "act_session_context", None)
    worker_port = getattr(services, "act_worker_port", None)
    inference = getattr(services, "act_inference_client", None)
    if context is None or worker_port is None or inference is None:
        raise ValueError(f"ACT_SESSION_SERVICE_UNAVAILABLE: {services.act_error}")
    return context, worker_port, inference


def main(argv: list[str] | None = None, *, service_factory=None, ports_factory=None) -> int:
    parser = argparse.ArgumentParser(prog="act_session", description=__doc__)
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--activation-receipt", type=Path)
    parser.add_argument("--runtime-config", type=Path)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args(argv)

    context, worker_port, inference = (ports_factory or _composition_ports)()
    composition = build_act_session_composition(
        mode=args.mode, context=context, worker_port=worker_port, inference=inference,
        evidence_root=args.evidence_root, bundle_path=args.bundle,
        calibration_path=args.calibration, policy_path=args.policy,
        activation_receipt=args.activation_receipt, runtime_config=args.runtime_config)
    spec = {"schema_version": 1, "kind": "act_session", "mode": composition["mode"],
            "payload": {"mode": composition["mode"], "evidence_root": composition["evidence_root"],
                        "effects": composition["effects"],
                        "artifacts": dict(composition["artifacts"])}}
    service = (service_factory or (lambda _spec: _composition_service()))(spec)
    result = service.start(spec)
    print(json.dumps({"mode": composition["mode"], "effects": composition["effects"],
                      "result": result}, sort_keys=True))
    return 0


def _composition_service():
    from so101_teleop.unified.compose import compose_services

    services = compose_services()
    if services.act_workload is None or services.bridge is None:
        raise ValueError(f"ACT_SESSION_SERVICE_UNAVAILABLE: {services.act_error}")
    return services.act_workload


if __name__ == "__main__":
    raise SystemExit(main())
