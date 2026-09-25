"""The live campaign must consume only the admitted Task 8 case sequence."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
import hashlib
import json
import time

import pytest

from so101_demo.act.task8 import Task8Runner
from so101_demo.act.task8_manifest import build_task8_live_manifest, write_new_manifest
from so101_demo.act.task8_live_campaign import Task8LiveCampaign, Task8LiveError


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
    worker_count: int = 1


class Worker:
    def __init__(self, context):
        self.context = context
        self.launch = type("Launch", (), {"mujoco_session_id": "session-245"})()
        self.requests = []
        self.cancelled = []
        self.bad_case = None

    async def task8(self, request):
        self.requests.append(request)
        phases = list(Task8Runner.PHASES)
        if request["mode"] == "phase_prefix":
            phases = phases[:phases.index(request["stop_after"]) + 1]
        if self.bad_case == request["scenario_id"]:
            phases = phases[:-1]
        return {"status": "PASSED", "completed_phases": phases,
                "stopped_confirmed": True,
                "formal_episode_eligible": request["mode"] == "full"}

    async def cancel(self, request):
        self.cancelled.append(request)
        return {"stopped_confirmed": True, "reason": request["reason"]}


def prepared(tmp_path):
    document = build_task8_live_manifest(
        ANCHORS, source_sha256="a" * 64, runtime_config_sha256="b" * 64,
        collection_config_sha256="c" * 64, contact_policy_fingerprint="d" * 64,
    )
    path = tmp_path / "manifest.json"
    write_new_manifest(path, document)
    context = Context("campaign-245", hashlib.sha256(path.read_bytes()).hexdigest(),
                      "a" * 64, "b" * 64, "c" * 64, "d" * 64)
    return path, context


def test_exact_nine_prefixes_then_five_fresh_full_cases(tmp_path):
    manifest_path, context = prepared(tmp_path)
    worker = Worker(context)
    journal = tmp_path / "case-results.jsonl"
    result = asyncio.run(Task8LiveCampaign(manifest_path, context, worker, journal).run(
        deadline_ns=time.monotonic_ns() + 60_000_000_000))
    assert result["status"] == "PASSED"
    assert result["prefix_passes"] == 9 and result["full_passes"] == 5
    assert [item["scenario_id"] for item in worker.requests] == [
        *(f"prefix-{i:02d}" for i in range(1, 10)),
        *(f"full-{i:02d}" for i in range(1, 6)),
    ]
    assert len({item["attempt_id"] for item in worker.requests}) == 14
    assert all(item["session_id"] == "session-245" and
               item["contact_policy_fingerprint"] == "d" * 64
               for item in worker.requests)
    records = [json.loads(line) for line in journal.read_text().splitlines()]
    assert [item["case_id"] for item in records] == [item["scenario_id"] for item in worker.requests]
    assert all(item["status"] == "PASSED" for item in records)
    assert worker.cancelled == []


def test_wrong_case_result_stops_before_next_case(tmp_path):
    manifest_path, context = prepared(tmp_path)
    worker = Worker(context)
    worker.bad_case = "prefix-02"
    journal = tmp_path / "case-results.jsonl"
    with pytest.raises(Task8LiveError, match="TASK8_CASE_RESULT_INVALID"):
        asyncio.run(Task8LiveCampaign(manifest_path, context, worker, journal).run(
            deadline_ns=time.monotonic_ns() + 60_000_000_000))
    assert [item["scenario_id"] for item in worker.requests] == ["prefix-01", "prefix-02"]
    assert len(worker.cancelled) == 1
    records = [json.loads(line) for line in journal.read_text().splitlines()]
    assert records[-1]["status"] == "FAILED"


def test_hash_drift_or_existing_journal_refuses_before_worker_call(tmp_path):
    manifest_path, context = prepared(tmp_path)
    worker = Worker(context)
    original = manifest_path.read_bytes()
    manifest_path.write_bytes(original + b" ")
    journal = tmp_path / "case-results.jsonl"
    with pytest.raises(Task8LiveError, match="TASK8_MANIFEST_BINDING_INVALID"):
        asyncio.run(Task8LiveCampaign(manifest_path, context, worker, journal).run(
            deadline_ns=time.monotonic_ns() + 60_000_000_000))
    assert worker.requests == [] and not journal.exists()
    manifest_path.write_bytes(original)
    # An existing output is never overwritten, even before a case can run.
    journal.write_text("preserved\n")
    with pytest.raises(Task8LiveError, match="TASK8_JOURNAL_EXISTS"):
        asyncio.run(Task8LiveCampaign(manifest_path, context, worker, journal).run(
            deadline_ns=time.monotonic_ns() + 60_000_000_000))
    assert journal.read_text() == "preserved\n"


def test_policy_binding_drift_refuses_before_journal_or_worker(tmp_path):
    manifest_path, context = prepared(tmp_path)
    wrong = replace(context, contact_policy_fingerprint="e" * 64)
    worker = Worker(wrong)
    journal = tmp_path / "case-results.jsonl"
    with pytest.raises(Task8LiveError, match="TASK8_MANIFEST_BINDING_INVALID"):
        asyncio.run(Task8LiveCampaign(manifest_path, wrong, worker, journal).run(
            deadline_ns=time.monotonic_ns() + 60_000_000_000))
    assert worker.requests == [] and not journal.exists()


def test_unconfirmed_cancel_records_indeterminate_and_stops_sequence(tmp_path):
    manifest_path, context = prepared(tmp_path)

    class UnstoppableWorker(Worker):
        async def cancel(self, request):
            self.cancelled.append(request)
            return {"stopped_confirmed": False}

    worker = UnstoppableWorker(context)
    worker.bad_case = "prefix-02"
    journal = tmp_path / "case-results.jsonl"
    with pytest.raises(Task8LiveError, match="TASK8_STOP_NOT_CONFIRMED"):
        asyncio.run(Task8LiveCampaign(manifest_path, context, worker, journal).run(
            deadline_ns=time.monotonic_ns() + 60_000_000_000))
    assert [item["scenario_id"] for item in worker.requests] == ["prefix-01", "prefix-02"]
    records = [json.loads(line) for line in journal.read_text().splitlines()]
    assert records[-1]["status"] == "INDETERMINATE"
