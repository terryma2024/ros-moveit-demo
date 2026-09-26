"""A Task 8 series needs fourteen independently retired case transactions."""

import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import time

import pytest

from so101_demo.act.task8 import Task8Runner
from so101_demo.act.task8_manifest import build_task8_live_manifest, write_new_manifest
from so101_teleop.unified.contracts import Domain, OperationSpec
from so101_teleop.unified.task8_full_restart_campaign import run_full_restart_campaign


def _h(value):
    return hashlib.sha256(value).hexdigest()


def _setup(tmp_path, *, duplicate_at=None, fail_at=None, existing_at=None):
    anchors = {name: {"cup_start_m": [0.02, -0.28, 0.165], "neck_start_rad": 0.0}
               for name in ("default", "left", "forward")}
    manifest = build_task8_live_manifest(
        anchors, source_sha256="a" * 64, runtime_config_sha256="b" * 64,
        collection_config_sha256="c" * 64, contact_policy_fingerprint="d" * 64)
    manifest_path = tmp_path / "manifest.json"
    write_new_manifest(manifest_path, manifest)
    journal_root = tmp_path / "task8-live" / "cases"
    journal_root.mkdir(parents=True)
    expected_hash = _h(manifest_path.read_bytes())
    calls = []

    def make_case(case, path):
        index = int(case["case_id"].split("-")[1])
        if case["mode"] == "full":
            index += 9
        identity = 1 if index == duplicate_at else index
        child = {
            "campaign_id": f"campaign-{identity}", "worker_id": "w00",
            "execution_generation": 1, "ros_domain_id": identity,
            "namespace": f"/task8-{identity}", "controller_name": f"arm-{identity}",
            "mujoco_session_id": f"session-{identity}",
            "socket_root": f"/tmp/act389-{identity}",
        }
        spec = OperationSpec(
            f"command-{index}", Domain.VALIDATION, "task8_full",
            {"evidence_root": str(tmp_path), "manifest_path": str(manifest_path),
             "manifest_sha256": expected_hash, "children": [child]},
            f"runtime-{index}", 1, time.monotonic_ns() + 60_000_000_000)
        return spec, SimpleNamespace(case_id=case["case_id"])

    async def execute(spec, case_id, owner, journal_path):
        calls.append(case_id)
        if case_id == fail_at:
            raise RuntimeError("retirement failed")
        phases = list(Task8Runner.PHASES)
        if case_id.startswith("prefix"):
            phase = next(item["stop_after"] for item in manifest["prefix_cases"]
                         if item["case_id"] == case_id)
            phases = phases[:phases.index(phase) + 1]
        row = {"case_id": case_id, "anchor": next(
            item["anchor"] for item in (*manifest["prefix_cases"], *manifest["full_cases"])
            if item["case_id"] == case_id), "status": "PASSED",
            "completed_phases": phases, "full_restart_retired": True,
            "eligible_for_formal_collection": False,
            "campaign_id": spec.payload["children"][0]["campaign_id"],
            "session_id": spec.payload["children"][0]["mujoco_session_id"]}
        journal_path.write_text(json.dumps(row, sort_keys=True) + "\n")
        return row

    if existing_at:
        (journal_root / f"{existing_at}.json").write_text("old evidence\n")
    return manifest_path, journal_root, make_case, execute, calls


def test_fourteen_ordered_cases_each_have_new_resources_and_durable_result(tmp_path):
    manifest, journal_root, make_case, execute, calls = _setup(tmp_path)
    summary = asyncio.run(run_full_restart_campaign(
        manifest, journal_root, make_case, execute_case=execute))
    assert calls == [f"prefix-{n:02d}" for n in range(1, 10)] + [
        f"full-{n:02d}" for n in range(1, 6)]
    assert summary["status"] == "PASSED"
    assert summary["prefix_count"] == 9 and summary["consecutive_full_count"] == 5
    assert len(summary["case_journal_sha256"]) == 14
    assert json.loads((journal_root / "campaign-result.json").read_text()) == summary


def test_duplicate_session_or_domain_refuses_before_second_case(tmp_path):
    manifest, root, make_case, execute, calls = _setup(tmp_path, duplicate_at=2)
    with pytest.raises(ValueError, match="TASK8_CASE_RESOURCE_REUSED"):
        asyncio.run(run_full_restart_campaign(manifest, root, make_case,
                                              execute_case=execute))
    assert calls == ["prefix-01"]
    assert not (root / "campaign-result.json").exists()


def test_failed_retirement_stops_series_and_keeps_prior_case(tmp_path):
    manifest, root, make_case, execute, calls = _setup(tmp_path, fail_at="prefix-03")
    with pytest.raises(RuntimeError, match="retirement failed"):
        asyncio.run(run_full_restart_campaign(manifest, root, make_case,
                                              execute_case=execute))
    assert calls == ["prefix-01", "prefix-02", "prefix-03"]
    assert (root / "prefix-02.json").is_file()
    assert not (root / "campaign-result.json").exists()


def test_existing_case_journal_refuses_without_starting_that_case(tmp_path):
    manifest, root, make_case, execute, calls = _setup(tmp_path, existing_at="prefix-01")
    with pytest.raises(ValueError, match="TASK8_CASE_JOURNAL_INVALID"):
        asyncio.run(run_full_restart_campaign(manifest, root, make_case,
                                              execute_case=execute))
    assert calls == []
    assert not (root / "campaign-result.json").exists()
