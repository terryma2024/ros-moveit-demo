"""Candidate-only resource measurement CLI.

It validates a sealed operator authorization, the closed v2 runtime config and the
local measurement capabilities, then binds an owned measurement context. It never
reads an approved budget profile and never writes promotion state. The runner it
composes spawns the frozen copied-install batch entry with the same sealed
authorization bytes, inside the owned cgroup, under the real sampler and deadline.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from so101_demo.parallel_batch.contracts import ContractError, load_parallel_runtime_config_v2
from so101_demo.parallel_batch.measurement_control import ProcessIdentity
from so101_demo.parallel_batch.owned_resources import (
    MeasurementSession, NvmlDevicePort, OwnedCgroupV2, own_cgroup_path)
from so101_demo.parallel_batch.resource_measurement import (
    MeasurementAuthorization,
    build_candidate_plan,
    compose_measurement_admission,
    measurement_child_environment,
    run_candidate_batch,
    verify_measurement_arguments,
)


class MeasurementCliError(RuntimeError):
    """The candidate entry refused to start a measurement."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _local_identity() -> ProcessIdentity:
    fields = Path(f"/proc/{os.getpid()}/stat").read_text().rsplit(")", 1)[1].split()
    return ProcessIdentity(os.getpid(), int(fields[19]), os.getuid(), os.getpgrp())


def require_measurement_capabilities(
    *, cgroup_parent: Path | None = None, device_index: int = 0, observation_source=None,
) -> dict[str, object]:
    """Verify the real capabilities; a missing one fails closed, never with sudo."""

    parent = Path(cgroup_parent) if cgroup_parent else own_cgroup_path()
    probe = OwnedCgroupV2.create(
        parent=parent, name=f"so101-measurement-preflight-{os.getpid()}")
    try:
        probe.require_delegated()
        controllers = sorted(set((probe.path / "cgroup.controllers").read_text().split()))
    finally:
        probe.remove()
    device = NvmlDevicePort(device_index=device_index)
    device.refresh()
    if observation_source is not None:
        observation = observation_source()
    else:
        from so101_demo.parallel_batch.resource_budget import LiveObservationSource

        observation = LiveObservationSource(gpu_device_index=device_index)()
    if not observation.attribution_complete:
        raise MeasurementCliError("MEASUREMENT_CAPABILITY_MISSING: attribution")
    return {
        "cgroup_parent": str(parent),
        "controllers": controllers,
        "gpu": device.name,
        "gpu_total_bytes": device.total_bytes,
        "cpu_core_equivalent": observation.capacity["cpu_core_equivalent"],
    }


def production_runner_factory(plan, *, child_runner=None):
    """Real composition runner: the frozen copied install's fixed batch entry."""

    binding = json.loads(Path(plan.bindings.provenance_binding_path).read_bytes())
    install_prefix = Path(str(binding.get("install_prefix", "")))
    if not install_prefix.is_absolute() or not install_prefix.is_dir():
        raise MeasurementCliError("MEASUREMENT_RUNTIME_UNAVAILABLE: install_prefix")
    launcher = install_prefix / "so101_demo_py/lib/so101_demo_py/so101_parallel_batch"
    if not launcher.is_file():
        raise MeasurementCliError("MEASUREMENT_RUNTIME_UNAVAILABLE: launcher")
    environment = measurement_child_environment(dict(os.environ))
    argv = (str(launcher), *plan.runner_argv())

    def runner(candidate_plan, session):
        if child_runner is not None:
            child = child_runner(session=session, argv=argv, cwd=candidate_plan.batch_root,
                                 environment=environment)
        else:
            child = session.spawn(argv=argv, cwd=candidate_plan.batch_root,
                                  environment=environment)
        code = session.supervise(child)
        if int(code) != 0:
            # A failed workload batch is not a measurement: refuse and seal nothing.
            raise ContractError(f"MEASUREMENT_WORKLOAD_FAILED: launcher_exit {int(code)}")
        return {
            "raw_files": session.raw_files(),
            "coverage_events": session.events_path,
            "result": {"launcher_exit": int(code), "launcher": str(launcher)},
        }

    return runner


def main(argv=None, *, runner_factory=None, capability_probe=None, session_factory=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--authorization-sha256", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--intent", choices=("CALIBRATION_ONLY", "QUALIFICATION"), required=True)
    parser.add_argument("--cgroup-parent", type=Path)
    parser.add_argument("--device-index", type=int, default=0)
    options = parser.parse_args(argv)
    try:
        authorization = MeasurementAuthorization.load(
            options.authorization, expected_sha256=options.authorization_sha256)
        if authorization.intent != options.intent:
            raise MeasurementCliError("AUTHORIZATION_INTENT_MISMATCH")
        if authorization.is_expired(now_ns=time.time_ns()):
            raise MeasurementCliError("AUTHORIZATION_EXPIRED")
        evidence_root = options.evidence_root.resolve()
        if not evidence_root.is_dir():
            raise MeasurementCliError("EVIDENCE_ROOT_UNAVAILABLE")
        if not authorization.batch_root.is_relative_to(evidence_root):
            raise MeasurementCliError("BATCH_ROOT_OUTSIDE_EVIDENCE_ROOT")
        config = load_parallel_runtime_config_v2(options.config)
        if config.deployment.approved_profile_path is not None:
            raise MeasurementCliError("CANDIDATE_CONFIG_MUST_HAVE_NULL_DEPLOYMENT")
        capability = (capability_probe or require_measurement_capabilities)()
        # The composition is determined by the sealed authorization alone: an inherited
        # production authority is refused inside the composer, not accepted as a grant.
        authorization, gate = compose_measurement_admission(
            authorization_path=options.authorization,
            authorization_sha256=options.authorization_sha256,
            config_path=options.config)
        plan = build_candidate_plan(
            authorization=authorization, authorization_path=options.authorization,
            config_path=options.config, evidence_root=evidence_root,
            batch_id=options.batch_id)
        verify_measurement_arguments(
            authorization=authorization, batch_id=plan.batch_id,
            worker_count=plan.worker_count, evidence_root=plan.batch_root,
            points_path=Path(plan.bindings.points_path),
            points_sha256=plan.bindings.points_sha256,
            yolo_weights_path=Path(plan.bindings.yolo_weights_path),
            yolo_weights_sha256=plan.bindings.yolo_weights_sha256,
            grounded_root=Path(plan.bindings.grounded_root),
            grounded_manifest_sha256=plan.bindings.grounded_manifest_sha256,
            broker_image=plan.bindings.broker_image_id, config_path=plan.config_path)
        # One admission for this batch, taken through the measurement context before
        # the owned cgroup is created; the session then caps the run itself.
        from so101_demo.parallel_batch.resource_budget import FixedAdmissionRequest

        decision = gate.admit(FixedAdmissionRequest(
            worker_count=plan.worker_count, batch_id=plan.batch_id, epoch=1,
            execution_identity_sha256=plan.execution_identity_sha256,
            request_kind=gate.request_kind))
        if not decision.admitted:
            raise MeasurementCliError(decision.reason_codes[0])
        session = (session_factory or _session)(
            authorization=authorization, batch_root=plan.batch_root,
            batch_id=plan.batch_id, sampling=config.measurement.sampling,
            safety=config.measurement.safety, owner=_local_identity(),
            cgroup_parent=options.cgroup_parent, device_index=options.device_index)
        factory = runner_factory or production_runner_factory
        summary = run_candidate_batch(plan=plan, runner=factory(plan), session=session)
        summary["capability"] = capability
        print(json.dumps(summary, sort_keys=True))
        return 0
    except (ContractError, MeasurementCliError, OSError, ValueError) as error:
        code = getattr(error, "code", None) or str(error) or type(error).__name__
        print(json.dumps({"status": "REFUSED", "code": code}, sort_keys=True),
              file=sys.stderr)
        return 1


def _session(**kwargs) -> MeasurementSession:
    return MeasurementSession(**kwargs)


if __name__ == "__main__":
    raise SystemExit(main())
