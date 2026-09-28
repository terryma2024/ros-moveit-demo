"""A Task 8 case is durable only after its own stack and child retire."""

import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import time

import pytest

from so101_demo.act.task8 import Task8Runner
from so101_demo.act.task8_manifest import build_task8_live_manifest, write_new_manifest
from so101_teleop.unified.contracts import OwnerKey
from so101_teleop.unified.pick_place_case_execution import run_pick_place_case


STACK_OWNER = OwnerKey(12345, 12345, 101, "a" * 64, "b" * 64)
CHILD_OWNER = OwnerKey(23456, 23456, 202, "c" * 64, "d" * 64)


def _prepared(tmp_path, *, case_id="prefix-01", result=None, cleanup_fails=False,
              omit_child_receipt=False):
    anchors = {
        name: {"cup_start_m": [0.02, -0.28, 0.165], "neck_start_rad": 0.0}
        for name in ("default", "left", "forward")
    }
    manifest = build_task8_live_manifest(
        anchors, source_sha256="a" * 64, runtime_config_sha256="b" * 64,
        collection_config_sha256="c" * 64,
        contact_policy_fingerprint="d" * 64,
        calibration_report_path="calibration-report.json",
        calibration_report_sha256="e" * 64,
    )
    manifest_path = tmp_path / "manifest.json"
    write_new_manifest(manifest_path, manifest)
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    campaign_id = "case-298"
    stack_root = tmp_path / "task8-live" / campaign_id / "stack"
    child_root = tmp_path / "child"
    stack_root.mkdir(parents=True)
    child_root.mkdir()
    context = SimpleNamespace(
        campaign_id=campaign_id, manifest_sha256=digest,
        workload_kind="task8_full", evidence_root=str(tmp_path),
        source_sha256=manifest["source_sha256"],
        runtime_config_sha256=manifest["runtime_config_sha256"],
        collection_config_sha256=manifest["collection_config_sha256"],
        contact_policy_fingerprint=manifest["contact_policy_fingerprint"],
        worker_count=1,
    )
    spec = SimpleNamespace(
        kind="task8_full",
        deadline_ns=time.monotonic_ns() + 60_000_000_000,
        payload={"evidence_root": str(tmp_path), "manifest_path": str(manifest_path),
                 "manifest_sha256": digest},
    )
    events = []

    class Worker:
        def __init__(self):
            self.context = context
            self.launch = SimpleNamespace(mujoco_session_id="session-298", socket_root=str(child_root),
                                          ros_domain_id=198)

        async def run_pick_place(self, request):
            events.append("execute")
            assert request["attempt_id"] == case_id
            assert request["session_id"] == self.launch.mujoco_session_id
            assert not owner._stack_retired
            assert not journal.exists()
            if result is not None:
                return result
            return {"status": "PASSED", "completed_phases": ["SEARCH"],
                    "live_evidence_artifact": None,
                    "stopped_confirmed": True, "formal_episode_eligible": False}

    class Owner:
        def __init__(self):
            self.context = None
            self.worker = Worker()
            self.stack = SimpleNamespace(launch=SimpleNamespace(evidence_root=str(stack_root)))
            self.child_launch = self.worker.launch
            self.stack_owner_key = STACK_OWNER
            self.child_owner_key = CHILD_OWNER
            self._stack_retired = self._child_retired = self._final_clear = False

        async def start(self, passed):
            events.append("start")
            assert passed is spec
            self.context = context
            return context, self.worker

        async def finish(self, *, attempt_id):
            events.append("finish")
            assert attempt_id == case_id
            assert not journal.exists()
            if cleanup_fails:
                raise RuntimeError("stop unconfirmed")
            (stack_root / "cleanup-receipt.json").write_text(json.dumps({
                "leader_pid": STACK_OWNER.pid, "pgid": STACK_OWNER.pgid,
                "started_ticks": STACK_OWNER.started_ticks,
                "argv_sha256": STACK_OWNER.argv_sha256, "group_clear": True,
                "session_id": "session-298", "ros_domain_id": 198,
                "physical_stop_confirmed": True, "graph_clear": True,
            }))
            if not omit_child_receipt:
                (child_root / "cleanup-receipt.json").write_text(json.dumps({
                    "leader_pid": CHILD_OWNER.pid, "pgid": CHILD_OWNER.pgid,
                    "started_ticks": CHILD_OWNER.started_ticks,
                    "argv_sha256": CHILD_OWNER.argv_sha256, "group_clear": True,
                }))
            self._stack_retired = self._child_retired = self._final_clear = True
            self.context = None

    owner = Owner()
    journal = tmp_path / "result.json"
    return spec, owner, journal, events


def test_case_result_is_written_only_after_own_stack_and_child_retire(tmp_path):
    spec, owner, journal, events = _prepared(tmp_path)
    row = asyncio.run(run_pick_place_case(spec, "prefix-01", owner, journal))
    assert events == ["start", "execute", "finish"]
    assert json.loads(journal.read_text()) == row
    assert row["status"] == "PASSED"
    assert row["completed_phases"] == ["SEARCH"]
    assert row["eligible_for_formal_collection"] is False
    assert len(row["stack_receipt_sha256"]) == len(row["child_receipt_sha256"]) == 64


def test_full_case_stays_ineligible_for_formal_collection(tmp_path):
    full = {"status": "PASSED", "completed_phases": list(Task8Runner.PHASES),
            "live_evidence_artifact": {"path": str(tmp_path / "live.json"), "sha256": "a" * 64,
                                       "schema_version": 1},
            "stopped_confirmed": True, "formal_episode_eligible": True}
    spec, owner, journal, events = _prepared(tmp_path, case_id="full-01", result=full)
    row = asyncio.run(run_pick_place_case(spec, "full-01", owner, journal))
    assert events == ["start", "execute", "finish"]
    assert row["completed_phases"] == list(Task8Runner.PHASES)
    assert row["eligible_for_formal_collection"] is False


def test_case_rejects_forged_phase_result_after_retiring(tmp_path):
    forged = {"status": "PASSED", "completed_phases": ["SEARCH", "APPROACH"],
              "stopped_confirmed": True, "formal_episode_eligible": False}
    spec, owner, journal, events = _prepared(tmp_path, result=forged)
    with pytest.raises(ValueError, match="TASK8_CASE_RESULT_INVALID"):
        asyncio.run(run_pick_place_case(spec, "prefix-01", owner, journal))
    assert events == ["start", "execute", "finish"]
    assert not journal.exists()


def test_case_cleanup_failure_retains_admission_and_refuses_success_record(tmp_path):
    spec, owner, journal, events = _prepared(tmp_path, cleanup_fails=True)
    with pytest.raises(RuntimeError, match="stop unconfirmed"):
        asyncio.run(run_pick_place_case(spec, "prefix-01", owner, journal))
    assert events == ["start", "execute", "finish"]
    assert owner.context is not None and not journal.exists()


def test_missing_child_retirement_receipt_refuses_success_record(tmp_path):
    from so101_teleop.unified.contracts import MutationError

    spec, owner, journal, events = _prepared(tmp_path, omit_child_receipt=True)
    with pytest.raises(MutationError, match="TASK8_RETIREMENT_RECEIPT_INVALID"):
        asyncio.run(run_pick_place_case(spec, "prefix-01", owner, journal))
    assert events == ["start", "execute", "finish"]
    assert not journal.exists()


def test_unknown_case_and_replaced_manifest_refuse_before_admission(tmp_path):
    spec, owner, journal, events = _prepared(tmp_path)
    with pytest.raises(ValueError, match="TASK8_CASE_NOT_FROZEN"):
        asyncio.run(run_pick_place_case(spec, "prefix-99", owner, journal))
    assert events == [] and not journal.exists()
    path = Path(spec.payload["manifest_path"])
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="TASK8_MANIFEST_BINDING_INVALID"):
        asyncio.run(run_pick_place_case(spec, "prefix-01", owner, journal))
    assert events == [] and not journal.exists()


def test_linked_journal_parent_refuses_before_starting_a_stack(tmp_path):
    spec, owner, _journal, events = _prepared(tmp_path)
    real_parent = tmp_path / "real-journal"
    real_parent.mkdir()
    alias = tmp_path / "linked-journal"
    alias.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(ValueError, match="TASK8_MANIFEST_BINDING_INVALID"):
        asyncio.run(run_pick_place_case(spec, "prefix-01", owner, alias / "result.json"))
    assert events == [] and not (real_parent / "result.json").exists()
