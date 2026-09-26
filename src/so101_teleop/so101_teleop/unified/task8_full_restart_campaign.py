"""Run frozen Task 8 cases as fourteen separately retired owner transactions.

This composes the one-case transaction; it does not bypass calibration, supply a
physical phase port, or itself authorize a live campaign.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from so101_demo.act.task8 import Task8Runner
from so101_demo.act.task8_manifest import require_task8_live_manifest

from .bridge import ActChildLaunch
from .task8_case_execution import (
    _preflight, _publish_new, _regular_bytes, run_task8_case,
)


def _require_paths(manifest_path: Path, journal_root: Path) -> dict:
    if (not manifest_path.is_absolute() or ".." in manifest_path.parts
            or manifest_path.is_symlink() or not journal_root.is_absolute()
            or ".." in journal_root.parts or journal_root.is_symlink()
            or not journal_root.is_dir()
            or journal_root.name != "cases"
            or journal_root.parent.name != "task8-live"
            or journal_root.parent.is_symlink()
            or journal_root.parent.parent.is_symlink()):
        raise ValueError("TASK8_CAMPAIGN_PATH_INVALID")
    return require_task8_live_manifest(json.loads(_regular_bytes(manifest_path)))


def _resource_identity(spec, manifest_path: Path, journal_root: Path,
                       case_id: str, journal_path: Path, seen: dict) -> ActChildLaunch:
    _manifest, case, accepted_path = _preflight(spec, case_id, journal_path)
    if (accepted_path != manifest_path
            or case["case_id"] != case_id
            or Path(spec.payload["evidence_root"]) != journal_root.parent.parent
            or not isinstance(spec.payload.get("children"), list)
            or len(spec.payload["children"]) != 1):
        raise ValueError("TASK8_CASE_SCOPE_INVALID")
    try:
        child = ActChildLaunch(**spec.payload["children"][0])
    except (TypeError, ValueError) as error:
        raise ValueError("TASK8_CASE_SCOPE_INVALID") from error
    values = {
        "campaign_id": child.campaign_id,
        "session_id": child.mujoco_session_id,
        "ros_domain_id": child.ros_domain_id,
        "namespace": child.namespace,
        "controller_name": child.controller_name,
        "socket_root": child.socket_root,
        "command_id": spec.command_id,
        "runtime_id": spec.runtime_id,
    }
    if (type(spec.command_id) is not str or not spec.command_id
            or type(spec.runtime_id) is not str or not spec.runtime_id
            or any(value in seen[name] for name, value in values.items())):
        raise ValueError("TASK8_CASE_RESOURCE_REUSED")
    for name, value in values.items():
        seen[name].add(value)
    return child


def _require_retired_row(row: dict, case: dict, child: ActChildLaunch,
                         journal_path: Path) -> str:
    phases = list(Task8Runner.PHASES)
    if case["mode"] == "phase_prefix":
        phases = phases[:phases.index(case["stop_after"]) + 1]
    if (type(row) is not dict or row.get("case_id") != case["case_id"]
            or row.get("anchor") != case["anchor"]
            or row.get("campaign_id") != child.campaign_id
            or row.get("session_id") != child.mujoco_session_id
            or row.get("status") != "PASSED"
            or row.get("completed_phases") != phases
            or row.get("full_restart_retired") is not True
            or row.get("eligible_for_formal_collection") is not False
            or not journal_path.is_file() or journal_path.is_symlink()):
        raise ValueError("TASK8_CASE_RESULT_INVALID")
    raw = _regular_bytes(journal_path)
    if json.loads(raw) != row:
        raise ValueError("TASK8_CASE_JOURNAL_INVALID")
    return hashlib.sha256(raw).hexdigest()


async def run_full_restart_campaign(
    manifest_path: Path, journal_root: Path, make_case, *,
    execute_case=run_task8_case,
) -> dict:
    """Stop the series at the first failed case; never resume inside its owner."""
    manifest_path, journal_root = Path(manifest_path), Path(journal_root)
    manifest = _require_paths(manifest_path, journal_root)
    summary_path = journal_root / "campaign-result.json"
    if summary_path.exists() or summary_path.is_symlink():
        raise ValueError("TASK8_CAMPAIGN_JOURNAL_EXISTS")
    cases = (*manifest["prefix_cases"], *manifest["full_cases"])
    seen = {name: set() for name in (
        "campaign_id", "session_id", "ros_domain_id", "namespace",
        "controller_name", "socket_root", "command_id", "runtime_id",
    )}
    owners = []  # Keep objects alive while checking that no owner is reused.
    journals = {}
    for case in cases:
        case_id = case["case_id"]
        journal_path = journal_root / f"{case_id}.json"
        if journal_path.exists() or journal_path.is_symlink():
            raise ValueError("TASK8_CASE_JOURNAL_INVALID")
        spec, owner = make_case(dict(case), journal_path)
        if owner is None or any(owner is earlier for earlier in owners):
            raise ValueError("TASK8_CASE_OWNER_REUSED")
        child = _resource_identity(spec, manifest_path, journal_root, case_id,
                                   journal_path, seen)
        owners.append(owner)
        row = await execute_case(spec, case_id, owner, journal_path)
        journals[case_id] = _require_retired_row(row, case, child, journal_path)
    summary = {
        "status": "PASSED", "manifest_sha256": manifest["manifest_sha256"],
        "manifest_file_sha256": hashlib.sha256(_regular_bytes(manifest_path)).hexdigest(),
        "prefix_count": len(manifest["prefix_cases"]),
        "consecutive_full_count": len(manifest["full_cases"]),
        "case_journal_sha256": journals,
    }
    _publish_new(summary_path, summary)
    return summary
