"""Run frozen pick-place validation live cases only through unified campaign admission."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import stat

from so101_demo.act.pick_place_validation_campaign import PickPlaceValidationCampaign


def load_spec_file(path: Path):
    """Read one closed operation spec without following a replaced file link."""
    from so101_teleop.unified.contracts import Domain, OperationSpec

    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("TASK8_SPEC_INVALID")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("TASK8_SPEC_INVALID")
            raw = stream.read((1 << 20) + 1)
        if len(raw) > (1 << 20):
            raise ValueError("TASK8_SPEC_INVALID")
        data = json.loads(raw)
        if (not isinstance(data, dict)
                or set(data) != set(OperationSpec.__dataclass_fields__)
                or data["domain"] != Domain.VALIDATION.value
                or data["kind"] != "task8_full"
                or not isinstance(data["command_id"], str) or not data["command_id"]
                or not isinstance(data["runtime_id"], str) or not data["runtime_id"]
                or type(data["execution_generation"]) is not int
                or data["execution_generation"] < 0
                or type(data["deadline_ns"]) is not int
                or not isinstance(data["payload"], dict)):
            raise ValueError("TASK8_SPEC_INVALID")
        return OperationSpec(**{**data, "domain": Domain.VALIDATION})
    except (OSError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("TASK8_SPEC_INVALID") from error


def _validate_local_paths(spec, journal_path: Path) -> None:
    from so101_teleop.unified.contracts import Domain

    payload = getattr(spec, "payload", None)
    if (getattr(spec, "domain", None) is not Domain.VALIDATION
            or getattr(spec, "kind", None) != "task8_full"
            or not isinstance(payload, dict)):
        raise ValueError("TASK8_SPEC_INVALID")
    try:
        root = Path(payload["evidence_root"])
        manifest = Path(payload["manifest_path"])
    except (KeyError, TypeError) as error:
        raise ValueError("TASK8_SPEC_INVALID") from error
    journal = Path(journal_path)
    if (not root.is_absolute() or ".." in root.parts or not root.is_dir()
            or not manifest.is_absolute() or ".." in manifest.parts
            or not journal.is_absolute() or ".." in journal.parts
            or not journal.parent.is_dir()
            or not journal.parent.resolve().is_relative_to(root.resolve())):
        raise ValueError("TASK8_LOCAL_PATH_INVALID")


#: The static admission proof: only the installed production composition satisfies it.
trusted_full_restart_composition = PickPlaceValidationCampaign.trusted_full_restart_composition


def _readiness_executable(install_prefix: Path) -> Path:
    """Resolve the motion-stack readiness entry in either installed layout."""

    from so101_demo.cli.diagnose_macos_station import READINESS_RELATIVE_PATH

    candidates = (install_prefix / READINESS_RELATIVE_PATH,
                  install_prefix / "so101_demo_py" / READINESS_RELATIVE_PATH)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ValueError("TASK8_READINESS_EXECUTABLE_MISSING")


def _case_owner_factory(lifecycle, spec):
    """Compose the trusted per-case full-restart owner for the admitted campaign."""

    import shutil

    from so101_teleop.unified.act_stack_probes import RosGraphClearProbe, make_pick_place_act_stack
    from so101_teleop.unified.bridge import ActCampaignChildOwner
    from so101_teleop.unified.pick_place_case_owner import PickPlaceCaseOwner

    base_launch = lifecycle.child_owner.base_launch
    installed = lifecycle.child_owner

    def make_case(case, case_journal_path):
        holder: dict = {}

        def stack_factory(context, child):
            # resolved per case, so the fail-closed checks happen at owner start
            ros2 = shutil.which("ros2")
            if ros2 is None or not os.access(ros2, os.X_OK):
                raise ValueError("TASK8_ROS2_EXECUTABLE_UNAVAILABLE")
            readiness = _readiness_executable(Path(base_launch.install_prefix))
            environment = dict(base_launch.environment)
            stack = make_pick_place_act_stack(
                context, child, ros2_executable=Path(ros2),
                readiness_executable=readiness, base_environment=environment,
            )
            holder["launch"] = stack.launch
            return stack

        async def final_clear_probe(domain_id):
            launch = holder.get("launch")
            if launch is None or launch.ros_domain_id != domain_id:
                return False
            return RosGraphClearProbe(launch)()

        owner = PickPlaceCaseOwner(
            lifecycle.workload_service,
            ActCampaignChildOwner(base_launch, installed.arbiter, installed.safety),
            stack_factory=stack_factory, final_clear_probe=final_clear_probe,
        )
        return spec, owner

    return make_case


async def run_admitted_campaign(spec, lifecycle, journal_path: Path) -> dict:
    """Run every frozen case through the production full-restart composition."""
    _validate_local_paths(spec, journal_path)
    composition = trusted_full_restart_composition()
    if composition is None:
        raise ValueError("FULL_RESTART_PROOF_UNAVAILABLE")
    make_case = _case_owner_factory(lifecycle, spec)
    return await composition(Path(spec.payload["manifest_path"]),
                             Path(journal_path).parent, make_case)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run admitted ACT pick-place validation live cases")
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--artifact-bundle", type=Path,
                        help="prepared Task 8 receipt; verified before any resource is acquired")
    parser.add_argument("--journal-run-root", type=Path,
                        help="run root whose fourteen case journals must all be free before the run")
    args = parser.parse_args(argv)
    spec = load_spec_file(args.spec)
    _validate_local_paths(spec, args.journal)
    if args.artifact_bundle is not None:
        # fail closed BEFORE composing services: a bundle that does not verify, or that disagrees
        # with the spec's declared receipt, must stop the run with nothing acquired
        import hashlib

        from so101_demo.act.task8_artifact_bundle import verify_task8_startup_receipt

        receipt = Path(args.artifact_bundle)
        if not receipt.is_file():
            raise ValueError("TASK8_PREPARATION_REQUIRED")
        verify_task8_startup_receipt({
            "preparation_receipt_path": str(receipt),
            "preparation_receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
        })
        declared = spec.payload.get("preparation_receipt_path")
        if declared is not None and Path(declared).resolve() != receipt.resolve():
            raise ValueError("TASK8_BUNDLE_SPEC_MISMATCH")
        if args.journal_run_root is not None:
            # all-or-nothing: either every one of the fourteen journals is free, or nothing starts
            import json

            from so101_demo.act.task8_live_evidence import plan_campaign_journals

            bundle = verify_task8_startup_receipt({
                "preparation_receipt_path": str(receipt),
                "preparation_receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest()})
            manifest = json.loads(Path(bundle.manifest).read_bytes())
            plan = plan_campaign_journals(args.journal_run_root, manifest)
            if len(plan) != 14:
                raise ValueError("TASK8_CAMPAIGN_JOURNAL_PLAN_INCOMPLETE")
    PickPlaceValidationCampaign.require_full_restart_lifecycle()

    from so101_teleop.unified.bridge import ActCampaignChildOwner, ActCampaignLifecycle
    from so101_teleop.unified.compose import compose_services

    services = compose_services()
    if services.act_workload is None or services.bridge is None:
        raise ValueError(f"TASK8_UNIFIED_SERVICE_UNAVAILABLE: {services.act_error}")
    if Path(services.bridge.launch.environment["SO101_UNIFIED_EVIDENCE_ROOT"]).resolve() != Path(
            spec.payload["evidence_root"]).resolve():
        raise ValueError("TASK8_SERVICE_ROOT_MISMATCH")
    owner = ActCampaignChildOwner(services.bridge.launch, services.arbiter, services.safety)
    lifecycle = ActCampaignLifecycle(services.act_workload, owner)
    result = asyncio.run(run_admitted_campaign(spec, lifecycle, args.journal))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
