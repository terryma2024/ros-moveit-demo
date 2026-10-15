"""The phase-2 scheduler over controlled doubles: processor containers and their control channel are fakes; the queue, the retry
rules, the journal and the deadline logic are the real ones. Times are real but tiny (milliseconds)."""

import asyncio
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace

import pytest

from so101_demo.act.parallel_collection_contracts import read_document
from so101_demo.runtime.container_campaign.processing_scheduler import ProcessingScheduler
from so101_demo.runtime.container_campaign.task_contracts import InstanceStatus, TaskStatus
from so101_demo.runtime.container_campaign.task_results import reserve_task_output, write_task_result

GIB = 2**30
RUNTIME = SimpleNamespace(heartbeat_interval_s=.005, heartbeat_timeout_s=.08, executing_hard_timeout_s=30.,
                          finalizing_hard_timeout_s=5., worker_recovery_timeout_s=5.)


class World:
    """Scripts what each (scene, attempt) does and records everything the scheduler asked of its processors."""

    def __init__(self, tmp_path, script=None, start_fail=()):
        self.run = tmp_path / "run"
        (self.run / "host").mkdir(parents=True)
        self.script = script or {}
        self.start_fail = set(start_fail)
        self.launches, self.starts, self.terminated, self.assigned, self.admitted = [], [], [], [], []
        self.dead = set()
        self.unreleased = set()
        self.context = SimpleNamespace(campaign_id="campaign", execution_generation=1,
                                       deadline_monotonic_s=time.monotonic() + 600.)

    def behaviour(self, scene, attempt):
        entry = self.script.get((scene, attempt), self.script.get(scene, "VALID"))
        return entry if isinstance(entry, tuple) else (entry, None)

    def launcher(self, *, slot, generation):
        root = self.run / "processing" / slot.worker_id / f"g{generation}"
        for name in ("output", "task-inputs"):
            (root / name).mkdir(parents=True)
        owner = SimpleNamespace(launch=SimpleNamespace(launch_id=f"processing-{slot.worker_id}-g{generation}",
            worker_id=slot.worker_id, launch_generation=generation, owned_root=str(root)))
        self.launches.append((slot.worker_id, generation))
        return owner

    def control_factory(self, owner):
        return FakeControl(self, owner)

    def scheduler(self, config=None, rows=None, available=36 * GIB, case_inputs=None, deadline_s=None, max_processors=None):
        rows = rows if rows is not None else make_rows(self, 5)
        scheduler = ProcessingScheduler(context=self.context, runtime=RUNTIME, config=config or {}, root=self.run,
            launcher=self.launcher, admit_slots=lambda slots: self.admitted.append(slots), case_inputs=case_inputs or inputs_for(rows),
            control_factory=self.control_factory, memory_reader=lambda: available, max_processors=max_processors)
        return scheduler, rows, (deadline_s if deadline_s is not None else time.monotonic() + 30.)

    def journal(self):
        path = self.run / "host/processing-journal.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()]

    def events(self, name):
        return [item for item in self.journal() if item["event"] == name]


def make_rows(world, count):
    rows = []
    for index in range(count):
        scene = f"scene-{index:02d}"
        sealed = world.run / f"wave-0/w00/g1/output/tasks/t{index}/attempts/{scene}/{scene}-lease-1/sealed"
        rows.append(dict(scene_id=scene, location=str(sealed), proof=dict(processing="PENDING", result_sha256=f"{index:064x}")))
    return rows


def inputs_for(rows):
    return {row["scene_id"]: dict(scope=dict(path="/s/" + row["scene_id"], sha256="a" * 64),
                                  inputs_manifest=dict(path="/i/" + row["scene_id"], sha256="b" * 64)) for row in rows}


class FakeControl:
    def __init__(self, world, owner):
        self.world, self.owner = world, owner
        self.launch = owner.launch
        self.task = None
        self.state = "STARTING"
        self.polls_left = 0

    async def start(self):
        key = (self.launch.worker_id, self.launch.launch_generation)
        self.world.starts.append(key)
        if key in self.world.start_fail:
            raise ValueError("FAKE_START_FAILED")
        self.state = "READY"

    async def assign_task(self, task):
        document = read_document(Path(task.inputs_ref.path))
        scene, attempt = document["scene_id"], document["proc_attempt"]
        if self.world.behaviour(scene, attempt)[0] == "LOST_ASSIGN":
            self.world.assigned.append(dict(task_id=task.task_id, scene=scene, attempt=attempt, processor=self.launch.worker_id,
                                            generation=self.launch.launch_generation, deadline=task.deadline_monotonic_s,
                                            document=document))
            raise ConnectionError("assign lost")     # the processor never saw the task
        self.world.assigned.append(dict(task_id=task.task_id, scene=scene, attempt=attempt, processor=self.launch.worker_id,
                                        generation=self.launch.launch_generation, deadline=task.deadline_monotonic_s,
                                        document=document))
        kind, reason = self.world.behaviour(scene, attempt)
        self.task = (task.task_id, scene, attempt, kind, reason)
        self.state = "BUSY"
        self.polls_left = 2
        if kind == "DIE":
            self.world.dead.add(self.launch.launch_id)
        if kind in ("VALID", "INVALID", "REFUSED", "INFRA"):
            output = Path(self.launch.owned_root) / "output"
            reserve_task_output(output, task.task_id)
            outcome = {"INFRA": "INFRASTRUCTURE_FAILURE"}.get(kind, kind)
            write_task_result(output, task.task_id, dict(kind="ACT_PROCESSING_TASK_RESULT", schema_version=1, task_id=task.task_id,
                scene_id=scene, proc_attempt=attempt, outcome=outcome, retryable=kind == "INFRA", reason=reason,
                processor_rc=3 if kind == "INVALID" else 0, output_dir=document["output_dir"], processed_result=None, phase1=None))

    async def get_status(self, task_id=None):
        if self.launch.launch_id in self.world.dead:
            raise ConnectionError("processor gone")
        task = None
        state = self.state
        if self.task is not None and (task_id is None or task_id == self.task[0]):
            if self.task[3] == "HANG":
                done = "RUNNING"
            elif self.polls_left > 0:
                self.polls_left -= 1
                done = "RUNNING"
            else:
                done = "FAILED" if self.task[3] == "TASK_FAILS" else "SUCCEEDED"
                if done == "SUCCEEDED" and state == "BUSY":
                    state = self.state = "READY"
            task = TaskStatus(task_id=self.task[0], state=done, fault_reason="boom" if done == "FAILED" else None)
        return InstanceStatus(instance_id=self.launch.launch_id, state=state, task=task)

    async def terminate(self, reason):
        self.world.terminated.append((self.launch.launch_id, reason))
        return InstanceStatus(instance_id=self.launch.launch_id, state="TERMINATED",
                              resources_released=self.launch.launch_id not in self.world.unreleased)


def run(coroutine):
    return asyncio.run(coroutine)


# ---- the queue and the processors -------------------------------------------------------------------------------------------

def test_every_scene_is_dispatched_once_to_the_admitted_slots_and_all_processors_are_stopped(tmp_path):
    world = World(tmp_path)
    scheduler, rows, deadline = world.scheduler(config={"processor_count": 2}, rows=make_rows(world, 5))
    summary = run(scheduler.run(rows, deadline_s=deadline))
    assert [slot.worker_id for slot in world.admitted[0]] == ["p00", "p01"]
    assert all(slot.campaign_id == "campaign" and slot.execution_generation == 1 for slot in world.admitted[0])
    assert sorted(world.launches) == [("p00", 1), ("p01", 1)]
    assert sorted(item["scene"] for item in world.assigned) == [row["scene_id"] for row in rows]
    assert {item["processor"] for item in world.assigned} == {"p00", "p01"}
    assert summary["counts"] == dict(VALID=5, INVALID=0, FAULT=0, MISSING=0) and summary["processors_stopped"] is True
    assert sorted(launch for launch, _ in world.terminated) == ["processing-p00-g1", "processing-p01-g1"]
    first = world.assigned[0]["document"]
    assert first["kind"] == "ACT_PROCESSING_TASK" and first["proc_attempt"] == 1 and first["task_id"].endswith("-proc-1")
    assert first["output_dir"] == str(world.run / "processing" / first["scene_id"] / f"{first['scene_id']}-lease-1-proc-1")
    assert first["phase1_result_sha256"] == "0" * 64 and first["scope"]["sha256"] == "a" * 64


def test_the_default_processor_count_comes_from_available_memory(tmp_path):
    world = World(tmp_path)
    scheduler, rows, deadline = world.scheduler(available=9 * GIB, rows=make_rows(world, 8))
    run(scheduler.run(rows, deadline_s=deadline))
    assert [slot.worker_id for slot in world.admitted[0]] == ["p00", "p01", "p02"]


def test_a_configured_count_overrides_memory_but_launches_no_idle_processor(tmp_path):
    world = World(tmp_path)
    scheduler, rows, deadline = world.scheduler(config={"processor_count": 16}, available=3 * GIB, rows=make_rows(world, 2))
    run(scheduler.run(rows, deadline_s=deadline))
    assert len(world.admitted[0]) == 2 and sorted(world.launches) == [("p00", 1), ("p01", 1)]


@pytest.mark.parametrize("config", [{}, {"processor_count": 4}])
def test_a_native_single_worker_runs_exactly_one_processor_whatever_the_memory_or_the_config_allow(tmp_path, config):
    world = World(tmp_path)
    scheduler, rows, deadline = world.scheduler(config=config, available=36 * GIB, rows=make_rows(world, 5), max_processors=1)
    summary = run(scheduler.run(rows, deadline_s=deadline))
    assert [slot.worker_id for slot in world.admitted[0]] == ["p00"] and sorted(world.launches) == [("p00", 1)]
    assert [item["scene"] for item in world.assigned] == [row["scene_id"] for row in rows]
    assert summary["processors"] == 1 and summary["counts"]["VALID"] == 5
    assert world.events("phase2_start")[0]["processors"] == 1


def test_one_processor_serves_a_queue_in_order(tmp_path):
    world = World(tmp_path)
    scheduler, rows, deadline = world.scheduler(config={"processor_count": 1}, rows=make_rows(world, 3))
    run(scheduler.run(rows, deadline_s=deadline))
    assert [item["scene"] for item in world.assigned] == ["scene-00", "scene-01", "scene-02"]


# ---- classification and retry ----------------------------------------------------------------------------------------------

def test_invalid_data_is_final_and_never_retried(tmp_path):
    world = World(tmp_path, script={"scene-01": ("INVALID", "OFFLINE_PROCESSOR_INVALID: rc=3")})
    scheduler, rows, deadline = world.scheduler(config={"processor_count": 2})
    summary = run(scheduler.run(rows, deadline_s=deadline))
    assert [item["attempt"] for item in world.assigned if item["scene"] == "scene-01"] == [1]
    scene = next(item for item in summary["scenes"] if item["scene_id"] == "scene-01")
    assert (scene["status"], scene["outcome"], scene["attempts"]) == ("FINAL", "INVALID", 1)
    assert summary["counts"]["INVALID"] == 1 and not world.events("retry")


def test_a_refused_task_is_a_fault_without_a_retry(tmp_path):
    world = World(tmp_path, script={"scene-02": ("REFUSED", "PHASE1_RECORD_REFUSED: x")})
    scheduler, rows, deadline = world.scheduler(config={"processor_count": 2})
    summary = run(scheduler.run(rows, deadline_s=deadline))
    assert [item["attempt"] for item in world.assigned if item["scene"] == "scene-02"] == [1]
    scene = next(item for item in summary["scenes"] if item["scene_id"] == "scene-02")
    assert scene["status"] == "FAULT" and scene["fault"] == "PROCESSING_REFUSED" and "PHASE1_RECORD_REFUSED" in scene["reason"]
    assert summary["counts"]["FAULT"] == 1 and summary["counts"]["VALID"] == 4 and not world.events("retry")


def test_an_infrastructure_failure_is_retried_in_a_new_attempt_on_any_processor(tmp_path):
    world = World(tmp_path, script={("scene-00", 1): ("INFRA", "OFFLINE_PROCESSOR_FAILED: rc=4"),
                                    ("scene-00", 2): ("INFRA", "OFFLINE_PROCESSOR_TIMEOUT")})
    scheduler, rows, deadline = world.scheduler(config={"processor_count": 2}, rows=make_rows(world, 3))
    summary = run(scheduler.run(rows, deadline_s=deadline))
    attempts = [item for item in world.assigned if item["scene"] == "scene-00"]
    assert [item["attempt"] for item in attempts] == [1, 2, 3]
    assert [item["task_id"] for item in attempts] == ["scene-00-proc-1", "scene-00-proc-2", "scene-00-proc-3"]
    assert [item["document"]["output_dir"].rsplit("-", 2)[-2:] for item in attempts] == [["proc", str(n)] for n in (1, 2, 3)]
    scene = summary["scenes"][0]
    assert (scene["status"], scene["outcome"], scene["attempts"]) == ("FINAL", "VALID", 3)
    assert [item["next_attempt"] for item in world.events("retry")] == [2, 3]


@pytest.mark.parametrize("limit,expected", [(None, 3), (1, 1), (2, 2), (5, 5)])
def test_retries_stop_at_processing_max_attempts_and_the_last_failure_is_a_fault(tmp_path, limit, expected):
    world = World(tmp_path, script={"scene-00": ("INFRA", "OFFLINE_PROCESSOR_FAILED: rc=4")})
    config = {"processor_count": 2} | ({} if limit is None else {"processing_max_attempts": limit})
    scheduler, rows, deadline = world.scheduler(config=config, rows=make_rows(world, 2))
    summary = run(scheduler.run(rows, deadline_s=deadline))
    assert len([item for item in world.assigned if item["scene"] == "scene-00"]) == expected
    scene = summary["scenes"][0]
    assert (scene["status"], scene["fault"], scene["attempts"]) == ("FAULT", "PROCESSING_RETRIES_EXHAUSTED", expected)
    assert world.events("scene_fault")[0]["fault"] == "PROCESSING_RETRIES_EXHAUSTED"


def test_a_processor_that_dies_costs_its_task_an_attempt_and_is_relaunched_with_the_next_generation(tmp_path):
    world = World(tmp_path, script={("scene-00", 1): "DIE"})
    scheduler, rows, deadline = world.scheduler(config={"processor_count": 1}, rows=make_rows(world, 3))
    summary = run(scheduler.run(rows, deadline_s=deadline))
    assert world.launches == [("p00", 1), ("p00", 2)]
    first, second = [item for item in world.assigned if item["scene"] == "scene-00"]
    assert (first["generation"], first["attempt"], second["generation"], second["attempt"]) == (1, 1, 2, 2)
    assert summary["counts"]["VALID"] == 3 and summary["scenes"][0]["attempts"] == 2
    assert world.events("processor_lost")[0]["scene_id"] == "scene-00"
    assert world.events("processor_relaunch")[0]["launch_generation"] == 2
    assert ("processing-p00-g1", "PROCESSING_END") in world.terminated, "the dead container is stopped before its replacement"
    assert summary["processors_stopped"] is True


def test_processors_stopped_needs_every_generation_of_every_slot_proven(tmp_path):
    world = World(tmp_path, script={("scene-00", 1): "DIE"})
    world.unreleased.add("processing-p00-g1")        # the replaced generation's container cannot be proven stopped
    scheduler, rows, deadline = world.scheduler(config={"processor_count": 1}, rows=make_rows(world, 3))
    summary = run(scheduler.run(rows, deadline_s=deadline))
    assert world.launches == [("p00", 1), ("p00", 2)] and summary["counts"]["VALID"] == 3
    assert summary["processors_stopped"] is False, "generation 1 was never proven stopped, whatever generation 2 did"
    assert world.events("phase2_end")[0]["processors_stopped"] is False


def test_a_lost_assignment_is_detected_by_the_short_acknowledgement_timeout(tmp_path):
    world = World(tmp_path, script={("scene-00", 1): "LOST_ASSIGN"})
    scheduler, rows, deadline = world.scheduler(config={"processor_count": 1}, rows=make_rows(world, 2))
    began = time.monotonic()
    summary = run(scheduler.run(rows, deadline_s=deadline))
    assert time.monotonic() - began < 5., "not the minutes-long task backstop"
    lost, = world.events("processor_lost")
    assert lost["scene_id"] == "scene-00" and "PROCESSOR_ASSIGN_NOT_ACKNOWLEDGED" in lost["reason"]
    assert world.launches == [("p00", 1), ("p00", 2)] and summary["counts"]["VALID"] == 2 and summary["scenes"][0]["attempts"] == 2


def test_a_failed_task_that_stops_its_processor_is_a_lost_processor(tmp_path):
    world = World(tmp_path, script={("scene-00", 1): "TASK_FAILS"})
    scheduler, rows, deadline = world.scheduler(config={"processor_count": 1}, rows=make_rows(world, 2))
    summary = run(scheduler.run(rows, deadline_s=deadline))
    assert world.launches == [("p00", 1), ("p00", 2)] and summary["counts"]["VALID"] == 2


def test_a_processor_lost_on_every_attempt_exhausts_the_scene_but_not_the_campaign(tmp_path):
    world = World(tmp_path, script={"scene-00": "DIE"})
    scheduler, rows, deadline = world.scheduler(config={"processor_count": 1}, rows=make_rows(world, 2))
    summary = run(scheduler.run(rows, deadline_s=deadline))
    assert summary["scenes"][0]["fault"] == "PROCESSING_RETRIES_EXHAUSTED" and summary["scenes"][0]["attempts"] == 3
    assert summary["scenes"][1]["outcome"] == "VALID" and len(world.launches) == 4


def test_a_processor_that_never_starts_is_retried_by_generation_then_given_up(tmp_path):
    world = World(tmp_path, start_fail={("p00", 1), ("p00", 2)})
    scheduler, rows, deadline = world.scheduler(config={"processor_count": 1}, rows=make_rows(world, 2))
    summary = run(scheduler.run(rows, deadline_s=deadline))
    assert world.launches == [("p00", 1), ("p00", 2), ("p00", 3)] and summary["counts"]["VALID"] == 2
    assert len(world.events("processor_start_failed")) == 2

    other = World(tmp_path / "other", start_fail={("p00", n) for n in (1, 2, 3)})
    scheduler, rows, deadline = other.scheduler(config={"processor_count": 1}, rows=make_rows(other, 2))
    summary = run(scheduler.run(rows, deadline_s=deadline))
    assert summary["counts"]["MISSING"] == 2 and {s["reason"] for s in summary["scenes"]} == {"PROCESSOR_UNAVAILABLE"}
    assert other.assigned == [] and summary["processors_stopped"] is True


# ---- the journal ----------------------------------------------------------------------------------------------------------

def test_every_dispatch_result_retry_and_relaunch_is_an_fsynced_journal_line(tmp_path, monkeypatch):
    synced = []
    real = os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: synced.append(fd) or real(fd))
    world = World(tmp_path, script={("scene-00", 1): ("INFRA", "OFFLINE_PROCESSOR_FAILED: rc=4"), ("scene-01", 1): "DIE"})
    scheduler, rows, deadline = world.scheduler(config={"processor_count": 1}, rows=make_rows(world, 2))
    run(scheduler.run(rows, deadline_s=deadline))
    lines = world.journal()
    assert [item["seq"] for item in lines] == list(range(1, len(lines) + 1))
    assert all(item["kind"] == "ACT_PROCESSING_JOURNAL" and item["schema_version"] == 1 for item in lines)
    names = [item["event"] for item in lines]
    assert names[0] == "phase2_start" and names[-1] == "phase2_end"
    for expected in ("processor_started", "dispatch", "result", "retry", "processor_lost", "processor_relaunch"):
        assert expected in names
    dispatch = world.events("dispatch")[0]
    assert {"scene_id", "task_id", "proc_attempt", "processor_id", "launch_generation", "output_dir"} <= set(dispatch)
    result = world.events("result")[0]
    assert (result["outcome"], result["retryable"], result["processor_rc"]) == ("INFRASTRUCTURE_FAILURE", True, 0)
    assert len(synced) >= len(lines), "one fsync per appended line"


# ---- deadlines ------------------------------------------------------------------------------------------------------------

def test_at_the_phase_deadline_dispatch_stops_inflight_work_is_terminated_and_the_rest_is_missing(tmp_path):
    world = World(tmp_path, script={"scene-00": "HANG", "scene-01": "HANG"})
    scheduler, rows, _ = world.scheduler(config={"processor_count": 2}, rows=make_rows(world, 6))
    summary = run(scheduler.run(rows, deadline_s=time.monotonic() + .25))
    assert sorted(item["scene"] for item in world.assigned) == ["scene-00", "scene-01"], "nothing new after the hung tasks"
    assert summary["counts"]["MISSING"] == 6 and {s["reason"] for s in summary["scenes"]} == {"PROCESSING_DEADLINE"}
    assert summary["processors_stopped"] is True and len(world.terminated) == 2
    assert world.events("deadline")[0]["unprocessed"]
    assert all(item["deadline"] <= world.assigned[0]["deadline"] + 1e-6 for item in world.assigned)


def test_a_deadline_that_has_already_passed_dispatches_nothing(tmp_path):
    world = World(tmp_path)
    scheduler, rows, _ = world.scheduler(config={"processor_count": 2})
    summary = run(scheduler.run(rows, deadline_s=time.monotonic() - 1.))
    assert world.assigned == [] and summary["counts"]["MISSING"] == 5 and summary["processors_stopped"] is True


def test_a_task_never_outlives_the_phase_deadline(tmp_path):
    world = World(tmp_path)
    scheduler, rows, _ = world.scheduler(config={"processor_count": 1}, rows=make_rows(world, 1))
    deadline = time.monotonic() + 7.
    run(scheduler.run(rows, deadline_s=deadline))
    assert world.assigned[0]["deadline"] <= deadline + 1e-6


def test_a_task_gets_the_dedicated_processing_budget_not_the_teacher_stage_limits(tmp_path):
    world = World(tmp_path)
    world.context.deadline_monotonic_s = time.monotonic() + 5000.
    scheduler, rows, _ = world.scheduler(config={"processor_count": 1, "processing_task_timeout_s": 1500}, rows=make_rows(world, 1))
    began = time.monotonic()
    run(scheduler.run(rows, deadline_s=began + 5000.))
    assert 1499. <= world.assigned[0]["deadline"] - began <= 1502., "the budget is processing_task_timeout_s, not 40 s of Teacher stages"
    other = World(tmp_path / "default")
    other.context.deadline_monotonic_s = time.monotonic() + 5000.
    scheduler, rows, _ = other.scheduler(config={"processor_count": 1}, rows=make_rows(other, 1))
    began = time.monotonic()
    run(scheduler.run(rows, deadline_s=began + 5000.))
    assert 1799. <= other.assigned[0]["deadline"] - began <= 1802., "default 1800 s"


def test_an_infrastructure_failure_after_the_deadline_is_not_retried(tmp_path):
    world = World(tmp_path, script={"scene-00": ("INFRA", "OFFLINE_PROCESSOR_TIMEOUT")})
    scheduler, rows, _ = world.scheduler(config={"processor_count": 1}, rows=make_rows(world, 1))
    original = scheduler._collect

    async def late(worker, task, item):
        result = await original(worker, task, item)
        scheduler.deadline_s = time.monotonic() - 1.   # the deadline passes while the task was finishing
        return result
    scheduler._collect = late
    summary = run(scheduler.run(rows, deadline_s=time.monotonic() + 30.))
    assert len(world.assigned) == 1 and summary["scenes"][0]["status"] == "MISSING"


@pytest.mark.parametrize("problem", ["empty", "duplicate", "long_id"])
def test_a_bad_queue_is_refused_before_any_slot_is_admitted(tmp_path, problem):
    world = World(tmp_path)
    rows = make_rows(world, 2)
    if problem == "empty":
        rows = []
    elif problem == "duplicate":
        rows = [rows[0], rows[0]]
    else:
        rows[0]["scene_id"] = "s" * 125
    scheduler, _, deadline = world.scheduler(rows=rows, case_inputs={"s" * 125: dict(scope={}, inputs_manifest={}),
                                                                      **inputs_for(make_rows(world, 2))})
    with pytest.raises(ValueError, match="PROCESSING_"):
        run(scheduler.run(rows, deadline_s=deadline))
    assert world.admitted == [] and world.launches == []
