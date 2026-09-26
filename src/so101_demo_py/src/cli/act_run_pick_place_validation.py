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


async def run_admitted_campaign(spec, lifecycle, journal_path: Path) -> dict:
    """Start one admitted child, run exact cases, then settle its owned resources."""
    _validate_local_paths(spec, journal_path)
    PickPlaceValidationCampaign.require_full_restart_lifecycle()
    context, ports = await lifecycle.start(spec)
    try:
        if (context.workload_kind != "task8_full" or context.worker_count != 1
                or context.evidence_root != spec.payload["evidence_root"]
                or len(ports) != 1):
            raise ValueError("TASK8_ADMITTED_CONTEXT_INVALID")
        return await PickPlaceValidationCampaign(
            Path(spec.payload["manifest_path"]), context, ports[0], Path(journal_path),
        ).run(deadline_ns=spec.deadline_ns)
    finally:
        await lifecycle.finish(context)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run admitted ACT pick-place validation live cases")
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    args = parser.parse_args(argv)
    spec = load_spec_file(args.spec)
    _validate_local_paths(spec, args.journal)
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
