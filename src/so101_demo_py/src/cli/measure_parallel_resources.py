"""Candidate-only resource measurement CLI.

It validates a sealed operator authorization, the closed v2 runtime config and
the local measurement capabilities, then binds an owned measurement context.
It never reads an approved budget profile and never writes promotion state.
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
from so101_demo.parallel_batch.resource_budget import AllocationScope, issue_measurement_context
from so101_demo.parallel_batch.resource_measurement import (
    MeasurementAuthorization,
    build_candidate_plan,
    run_candidate_batch,
)


class MeasurementCliError(RuntimeError):
    """The candidate entry refused to start a measurement."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _local_identity() -> ProcessIdentity:
    fields = Path(f"/proc/{os.getpid()}/stat").read_text().rsplit(")", 1)[1].split()
    return ProcessIdentity(os.getpid(), int(fields[19]), os.getuid(), os.getpgrp())


def require_measurement_capabilities() -> None:
    """No sudo, no tmpfs, no fabricated delegation: missing capability fails closed."""

    try:
        import pynvml  # noqa: F401
    except ImportError as error:
        raise MeasurementCliError("MEASUREMENT_CAPABILITY_MISSING: nvml") from error
    cpu_controller = Path("/sys/fs/cgroup/cpu.max")
    memory_controller = Path("/sys/fs/cgroup/memory.max")
    if not cpu_controller.is_file() or not memory_controller.is_file():
        raise MeasurementCliError("MEASUREMENT_CAPABILITY_MISSING: delegated_cgroup")


def production_runner_factory(plan):
    """Real composition runner: the frozen copied install's fixed batch entry."""

    import json as _json
    import subprocess

    binding = _json.loads(Path(plan.bindings.provenance_binding_path).read_bytes())
    install_prefix = Path(str(binding.get("install_prefix", "")))
    if not install_prefix.is_absolute() or not install_prefix.is_dir():
        raise MeasurementCliError("MEASUREMENT_RUNTIME_UNAVAILABLE: install_prefix")
    launcher = install_prefix / "so101_demo_py/lib/so101_demo_py/so101_parallel_batch"
    if not launcher.is_file():
        raise MeasurementCliError("MEASUREMENT_RUNTIME_UNAVAILABLE: launcher")

    def runner(candidate_plan):
        completed = subprocess.run(
            [str(launcher), *candidate_plan.runner_argv()],
            check=False, capture_output=True, text=True,
            cwd=str(candidate_plan.batch_root.parent),
        )
        if completed.returncode != 0:
            raise MeasurementCliError(
                f"MEASUREMENT_RUNTIME_UNAVAILABLE: exit {completed.returncode}")
        return {
            "raw_files": (),
            "coverage_events": candidate_plan.batch_root / "coverage-events.json",
            "result": {"launcher_exit": completed.returncode},
        }

    return runner


def main(argv=None, *, runner_factory=None, capability_probe=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--authorization-sha256", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--intent", choices=("CALIBRATION_ONLY", "QUALIFICATION"), required=True)
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
        (capability_probe or require_measurement_capabilities)()
        scope = AllocationScope(
            batch_id=options.batch_id, epoch=1, worker_count=authorization.worker_count,
            request_kind="MEASUREMENT",
            execution_identity_sha256=authorization.execution_identity_sha256)
        owner = _local_identity()
        context = issue_measurement_context(
            provider=None if False else _provider(), scope=scope,
            authorization_path=options.authorization,
            owner_binding={"authorization_sha256": options.authorization_sha256,
                           "owned_scope_sha256": authorization.owned_scope_sha256})
        if context.scope.sha256 != scope.sha256:
            raise MeasurementCliError("MEASUREMENT_CONTEXT_MISMATCH")
        # Compose the real lifecycle from the sealed bindings: plan -> authorized
        # workload -> sampler/seal. Only a genuinely unavailable installed runtime
        # (missing launcher/prefix) refuses before starting anything.
        plan = build_candidate_plan(
            authorization=authorization, config_path=options.config,
            evidence_root=evidence_root, batch_id=options.batch_id)
        factory = runner_factory or production_runner_factory
        runner = factory(plan)
        summary = run_candidate_batch(plan=plan, runner=runner)
        print(json.dumps(summary, sort_keys=True))
        return 0
    except (ContractError, MeasurementCliError, OSError, ValueError) as error:
        code = getattr(error, "code", None) or str(error) or type(error).__name__
        print(json.dumps({"status": "REFUSED", "code": code}, sort_keys=True),
              file=sys.stderr)
        return 1


def _provider():
    from so101_demo.parallel_batch.resource_budget import ResourceBudgetProvider
    return ResourceBudgetProvider()


if __name__ == "__main__":
    raise SystemExit(main())
