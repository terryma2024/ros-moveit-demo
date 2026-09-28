"""Execute one pick-place validation case and record it only after full owned retirement."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time

from so101_demo.act.pick_place_runner import PickPlaceRunner
from so101_demo.act.pick_place_validation_campaign import PickPlaceValidationCampaign
from so101_demo.act.pick_place_validation_manifest import require_pick_place_validation_manifest

from .pick_place_case_owner import _retirement_receipt


_HASH = re.compile(r"[0-9a-f]{64}\Z")
_CASE = re.compile(r"(?:prefix|full)-[0-9]{2}\Z")
_RESULT_KEYS = frozenset({
    "status", "completed_phases", "stopped_confirmed", "formal_episode_eligible",
    "live_evidence_artifact",
})


def _regular_bytes(path: Path) -> bytes:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("not regular")
            raw = stream.read((1 << 20) + 1)
        if len(raw) > (1 << 20):
            raise ValueError("too large")
        return raw
    except OSError as error:
        raise ValueError("TASK8_MANIFEST_BINDING_INVALID") from error


def _preflight(spec, case_id: str, journal_path: Path) -> tuple[dict, dict, Path]:
    if (getattr(spec, "kind", None) != "task8_full"
            or type(getattr(spec, "deadline_ns", None)) is not int
            or spec.deadline_ns <= time.monotonic_ns()
            or not isinstance(getattr(spec, "payload", None), dict)
            or type(case_id) is not str or _CASE.fullmatch(case_id) is None):
        raise ValueError("TASK8_CASE_NOT_FROZEN")
    payload = spec.payload
    try:
        root = Path(payload["evidence_root"])
        manifest_path = Path(payload["manifest_path"])
        expected_hash = payload["manifest_sha256"]
    except (KeyError, TypeError) as error:
        raise ValueError("TASK8_MANIFEST_BINDING_INVALID") from error
    journal_path = Path(journal_path)
    if (not root.is_absolute() or ".." in root.parts or not root.is_dir()
            or root.is_symlink()
            or not manifest_path.is_absolute() or ".." in manifest_path.parts
            or type(expected_hash) is not str or _HASH.fullmatch(expected_hash) is None
            or not journal_path.is_absolute() or ".." in journal_path.parts
            or not journal_path.parent.is_dir()
            or journal_path.parent.is_symlink()
            or not journal_path.parent.resolve().is_relative_to(root.resolve())
            or journal_path.exists() or journal_path.is_symlink()):
        raise ValueError("TASK8_MANIFEST_BINDING_INVALID")
    raw = _regular_bytes(manifest_path)
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        raise ValueError("TASK8_MANIFEST_BINDING_INVALID")
    try:
        manifest = require_pick_place_validation_manifest(json.loads(raw))
    except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("TASK8_MANIFEST_BINDING_INVALID") from error
    cases = (*manifest["prefix_cases"], *manifest["full_cases"])
    found = tuple(case for case in cases if case["case_id"] == case_id)
    if len(found) != 1:
        raise ValueError("TASK8_CASE_NOT_FROZEN")
    return manifest, found[0], manifest_path


def _require_result(result: dict, case: dict) -> None:
    phases = PickPlaceRunner.PHASES
    expected = (list(phases) if case["mode"] == "full" else
                list(phases[:phases.index(case["stop_after"]) + 1]))
    if (type(result) is not dict or set(result) != _RESULT_KEYS
            or result["status"] != "PASSED"
            or result["completed_phases"] != expected
            or result["stopped_confirmed"] is not True
            or result["formal_episode_eligible"] is not (case["mode"] == "full")):
        raise ValueError("TASK8_CASE_RESULT_INVALID")


def _publish_new(path: Path, row: dict) -> None:
    if (not path.parent.is_dir() or path.parent.is_symlink()
            or path.exists() or path.is_symlink()):
        raise ValueError("TASK8_CASE_JOURNAL_INVALID")
    data = (json.dumps(row, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode()
    fd, staging = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(staging, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.unlink(staging)


async def run_pick_place_case(spec, case_id: str, owner, journal_path: Path) -> dict:
    """Never publish a case PASS until its child, stack and graph are gone."""
    journal_path = Path(journal_path)
    manifest, case, manifest_path = _preflight(spec, case_id, journal_path)
    context, worker = await owner.start(spec)
    try:
        campaign = PickPlaceValidationCampaign(manifest_path, context, worker, journal_path)
        planned = campaign.planned_cases(deadline_ns=spec.deadline_ns)
        if case not in planned:
            raise ValueError("TASK8_CASE_NOT_FROZEN")
        request = {
            "session_id": worker.launch.mujoco_session_id,
            "attempt_id": case_id,
            "scenario_id": case_id,
            "mode": case["mode"], "stop_after": case["stop_after"],
            "contact_policy_fingerprint": manifest["contact_policy_fingerprint"],
            "deadline_ns": spec.deadline_ns,
        }
        result = await worker.run_pick_place(request)
        _require_result(result, case)
    finally:
        # On any uncertain execution outcome, retirement still has to stop the
        # physical controllers. A failed finish keeps the owner admission fenced.
        await owner.finish(attempt_id=case_id)
    if (owner.context is not None or owner._stack_retired is not True
            or owner._child_retired is not True or owner._final_clear is not True):
        raise ValueError("TASK8_CASE_RETIREMENT_UNCONFIRMED")
    stack_root = Path(owner.stack.launch.evidence_root)
    child_root = Path(owner.child_launch.socket_root)
    _retirement_receipt(stack_root, owner.stack_owner_key, stack=True,
                        session_id=worker.launch.mujoco_session_id,
                        ros_domain_id=worker.launch.ros_domain_id)
    _retirement_receipt(child_root, owner.child_owner_key, stack=False)
    row = {
        "case_id": case_id, "anchor": case["anchor"], "mode": case["mode"],
        "stop_after": case["stop_after"], "status": "PASSED",
        "campaign_id": context.campaign_id,
        "session_id": worker.launch.mujoco_session_id,
        "manifest_sha256": context.manifest_sha256,
        "completed_phases": result["completed_phases"],
        "stopped_confirmed": True,
        "full_restart_retired": True,
        "eligible_for_formal_collection": False,
        "stack_receipt_sha256": hashlib.sha256(_regular_bytes(
            stack_root / "cleanup-receipt.json")).hexdigest(),
        "child_receipt_sha256": hashlib.sha256(_regular_bytes(
            child_root / "cleanup-receipt.json")).hexdigest(),
        # the row also names what it can be read back from: this case's live evidence (a prefix
        # case has none, and says so with the zero digest) and both retirement receipts
        "live_evidence_path": (result["live_evidence_artifact"] or {}).get("path", ""),
        "live_evidence_sha256": (result["live_evidence_artifact"] or {}).get("sha256", "0" * 64),
        "stack_retirement_receipt_path": str(stack_root / "cleanup-receipt.json"),
        "child_retirement_receipt_path": str(child_root / "cleanup-receipt.json"),
    }
    _publish_new(journal_path, row)
    return row


# Legacy Python API for version-one pick-place callers.
run_task8_case = run_pick_place_case
