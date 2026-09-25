"""The Task 8 CLI must use unified admission and always settle owned children."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import json
import time

import pytest

from so101_demo.act.task8 import Task8Runner
from so101_demo.act.task8_manifest import build_task8_live_manifest, write_new_manifest
from so101_demo.cli.act_task8_live import load_spec_file, run_admitted_campaign
from so101_teleop.unified.contracts import Domain, OperationSpec


ANCHORS = {
    "default": {"cup_start_m": [0.02, -0.28, 0.165], "neck_start_rad": 0.1},
    "left": {"cup_start_m": [-0.08, -0.28, 0.165], "neck_start_rad": 0.0},
    "forward": {"cup_start_m": [0.02, -0.36, 0.165], "neck_start_rad": 0.0},
}


@dataclass(frozen=True)
class Context:
    campaign_id: str
    manifest_sha256: str
    source_sha256: str
    runtime_config_sha256: str
    collection_config_sha256: str
    contact_policy_fingerprint: str
    evidence_root: str
    workload_kind: str = "task8_full"
    worker_count: int = 1


class Worker:
    def __init__(self, context, *, bad=False):
        self.context = context
        self.launch = type("Launch", (), {"mujoco_session_id": "session-246"})()
        self.bad = bad
        self.requests = []

    async def task8(self, request):
        self.requests.append(request)
        phases = list(Task8Runner.PHASES)
        if request["mode"] == "phase_prefix":
            phases = phases[:phases.index(request["stop_after"]) + 1]
        if self.bad:
            phases = []
        return {"status": "PASSED", "completed_phases": phases,
                "stopped_confirmed": True,
                "formal_episode_eligible": request["mode"] == "full"}

    async def cancel(self, request):
        return {"stopped_confirmed": True, "reason": request["reason"]}


class Lifecycle:
    def __init__(self, context, worker, *, refuse=False):
        self.context, self.worker, self.refuse = context, worker, refuse
        self.starts = self.finishes = 0

    async def start(self, spec):
        self.starts += 1
        if self.refuse:
            raise ValueError("CALIBRATION_REQUIRED")
        return self.context, (self.worker,)

    async def finish(self, context):
        assert context is self.context
        self.finishes += 1


def prepared(tmp_path):
    manifest = build_task8_live_manifest(
        ANCHORS, source_sha256="a" * 64, runtime_config_sha256="b" * 64,
        collection_config_sha256="c" * 64, contact_policy_fingerprint="d" * 64,
    )
    path = tmp_path / "manifest.json"
    write_new_manifest(path, manifest)
    context = Context("campaign-246", hashlib.sha256(path.read_bytes()).hexdigest(),
                      "a" * 64, "b" * 64, "c" * 64, "d" * 64, str(tmp_path))
    spec = OperationSpec("command-246", Domain.VALIDATION, "task8_full",
                         {"manifest_path": str(path), "evidence_root": str(tmp_path)},
                         "runtime-246", 1, time.monotonic_ns() + 60_000_000_000)
    return spec, context


def test_admitted_campaign_runs_exact_cases_then_settles(tmp_path):
    spec, context = prepared(tmp_path)
    worker = Worker(context)
    lifecycle = Lifecycle(context, worker)
    journal = tmp_path / "task8-live" / "cases.jsonl"
    journal.parent.mkdir()
    result = asyncio.run(run_admitted_campaign(spec, lifecycle, journal))
    assert result["status"] == "PASSED"
    assert len(worker.requests) == 14
    assert lifecycle.starts == lifecycle.finishes == 1
    assert len(journal.read_text().splitlines()) == 14


def test_admission_refusal_creates_no_journal_or_worker_call(tmp_path):
    spec, context = prepared(tmp_path)
    worker = Worker(context)
    lifecycle = Lifecycle(context, worker, refuse=True)
    journal = tmp_path / "cases.jsonl"
    with pytest.raises(ValueError, match="CALIBRATION_REQUIRED"):
        asyncio.run(run_admitted_campaign(spec, lifecycle, journal))
    assert lifecycle.starts == 1 and lifecycle.finishes == 0
    assert worker.requests == [] and not journal.exists()


def test_case_failure_still_settles_and_refuses_next_case(tmp_path):
    spec, context = prepared(tmp_path)
    worker = Worker(context, bad=True)
    lifecycle = Lifecycle(context, worker)
    journal = tmp_path / "cases.jsonl"
    with pytest.raises(RuntimeError, match="TASK8_CASE_RESULT_INVALID"):
        asyncio.run(run_admitted_campaign(spec, lifecycle, journal))
    assert len(worker.requests) == 1
    assert lifecycle.starts == lifecycle.finishes == 1


def test_spec_loader_refuses_extra_fields_and_symlink(tmp_path):
    spec, _ = prepared(tmp_path)
    path = tmp_path / "operation.json"
    data = {**spec.__dict__, "domain": spec.domain.value}
    path.write_text(json.dumps(data))
    assert load_spec_file(path) == spec
    path.write_text(json.dumps({**data, "extra": True}))
    with pytest.raises(ValueError, match="TASK8_SPEC_INVALID"):
        load_spec_file(path)
    link = tmp_path / "operation-link.json"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="TASK8_SPEC_INVALID"):
        load_spec_file(link)
