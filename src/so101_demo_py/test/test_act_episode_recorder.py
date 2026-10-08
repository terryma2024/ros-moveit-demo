"""The act_episode_recorder process (Phase A4a): an independent consumer of the Teacher event stream and the sources.

The engine is driven here by a synthetic stream and synthetic sources over a real PointEpisode (real lossless writer,
real audit, real seal and readback). The real physics adapter is used for the source-gap fault. The Teacher is never
involved: every fault is a verdict on the data, never an input to control.
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from so101_demo.act import episode_qc
from so101_demo.act.episode_assembly import PointEpisode, episode_audit_pair
from so101_demo.act.episode_audit import verify_audit_manifest
from so101_demo.act.recorder import verify_episode_seal
from so101_demo.act.teacher_event_stream import StreamIdentity, TeacherEventStream
from so101_demo.act.episode_recorder_process import (
    FAULTS, RC_CONFIG, RC_INVALID, RC_VALID, FaultInjector, RecorderConfigRefused, RecorderEngine, RecorderSources,
    check_outputs_absent, load_recorder_policy, require_fault_sandbox)
from test_act_recorder import PROVENANCE
from test_act_seal_and_downgrade import IDENTITY, SCOPE, recorder_physical_audit

PACKAGE = Path(__file__).resolve().parents[1]
POLICY_FILE = PACKAGE / "config/act/episode_recorder_v1.yaml"
STREAM_IDENTITY = StreamIdentity(IDENTITY["session_id"], IDENTITY["reset_epoch"], IDENTITY["attempt_id"])
FRAME = np.zeros((480, 640, 3), dtype=np.uint8)
STAMPS = (1.0, 1.1, 1.2, 1.3, 1.4, 1.5)
START_STEP, END_STEP = 500, 700           # 1.0 s and 1.4 s at 2 ms per physics step
NODE = SimpleNamespace(create_subscription=lambda *args, **kwargs: object(), destroy_subscription=lambda item: None,
                       context=None)


def observation(step, *, session="session-1", epoch=2):
    return {"position": [0.0, 0.0, 0.1], "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
            "simulation_time_s": step * 0.002, "frame_id": "world", "object_id": "plastic_cup",
            "session_id": session, "reset_epoch": epoch, "publisher_sequence": step, "simulation_step": step}


def teacher_script(*, drop=(), repeat=(), result="PASS", with_stop=True, with_terminal=True, identity=STREAM_IDENTITY,
                   leading=(), reset_sim_s=1.0, reset_tick=0):
    """{tick: [event text]}: what the Teacher publishes, tick by tick, with optional defects."""

    published = []
    clock = iter(range(1_000_000_000, 2_000_000_000, 1_000_000))
    stream = TeacherEventStream(identity, clock_ns=lambda: next(clock), publish=published.append, start=False)
    plan = [(-1, kind, payload) for kind, payload in leading] + [
        (reset_tick, "reset_complete", {"session_id": "session-1", "reset_epoch": 2, "simulation_time_s": reset_sim_s,
                               "simulation_step": START_STEP, "publisher_sequence": START_STEP}),
        (0, "teacher_start_observation", {"observation": observation(START_STEP)}),
        (1, "phase_begin", {"state": "PREPARE_OPEN_GRIPPER", "sim_time_ns": 1_050_000_000, "monotonic_ns": 1,
                            "goal_sent": True, "goal_kind": "gripper"}),
        (2, "phase_finish", {"state": "PREPARE_OPEN_GRIPPER", "sim_time_ns": 1_100_000_000, "monotonic_ns": 2,
                             "status": "SUCCEEDED", "code": None}),
    ]
    if with_stop:
        plan.append((3, "normal_stop", {"proof": {"stop_confirmed_wall_s": 1.0}}))
    plan.append((4, "teacher_end_observation", {"observation": observation(END_STEP), "problem": None}))
    if with_terminal:
        plan.append((5, "terminal", {"status": "DONE", "teacher_execution_status": "COMPLETED",
                                     "teacher_task_result": result, "failure": None}))
    script = {}
    for index, (tick, kind, payload) in enumerate(plan, start=1):
        stream.offer(kind, payload)
        stream.pump()
        text = published[-1]
        if index in drop:
            continue
        script.setdefault(tick, []).append(text)
        if index in repeat:
            script[tick].append(text)
    return script


def physics_chunk(sequence, first, count, *, session="session-1", epoch=2):
    from so101_mujoco_support.msg import PhysicsStepEvidence, PhysicsStepEvidenceChunk

    base = 10_000_000_000 + first * 2_000_000
    samples = []
    for offset in range(count):
        step = first + offset
        sample = PhysicsStepEvidence(
            simulation_session_id=session, reset_epoch=epoch, physics_step=step, simulation_time_s=step * 0.002,
            clock_interval_begin_monotonic_ns=base + offset * 2_000_000,
            clock_interval_end_monotonic_ns=base + offset * 2_000_000 + 1_800_000,
            model_qpos=[.1, .2], model_qvel=[.3], has_contact=False, maximum_normal_force_n=0.,
            total_normal_force_n=0., global_max_single_contact_force_n=0.)
        sample.object_pose_world.orientation.w = 1.
        samples.append(sample)
    return PhysicsStepEvidenceChunk(
        chunk_sequence=sequence, simulation_session_id=session, reset_epoch=epoch, first_physics_step=first,
        last_physics_step=first + count - 1, first_simulation_time_s=samples[0].simulation_time_s,
        last_simulation_time_s=samples[-1].simulation_time_s, samples=samples), base + count * 2_000_000


class SyntheticSources(RecorderSources):
    """One simulated 10 Hz tick per `pump`: RGB, numeric state, one physics chunk and the scripted Teacher events.

    The physics adapter is the real `RosEpisodePhysicsAdapter` (fault-injectable), so continuity is the real check.
    """

    def __init__(self, engine_box, script, *, skip=(), raise_at=None, record_ready=None):
        self.box, self.script, self.skip = engine_box, script, set(skip)
        self.tick = 0
        self.raise_at = raise_at
        self.counts = {"head": 0, "wrist": 0, "physics": 0, "scene_state": 0, "world": 0, "joint_states": 0}
        self.delivered_before_ready = []
        self.record_ready = record_ready
        self.adapter = None
        self.receipt = [0]
        self.events_seen = []

    def prepare(self, engine):
        from so101_demo.adapters.act.ros_episode_physics import RosEpisodePhysicsAdapter
        cls = engine.faults.physics_adapter_class(RosEpisodePhysicsAdapter)
        self.adapter = cls(NODE, session_id="session-1", reset_epoch=2, nq=2, nv=1, audit=engine.episode.capture.audit,
                           clock_ns=lambda: self.receipt[0], history_capacity=4096)

    def try_start(self, engine):
        engine.episode.start(STAMPS[0])
        return STAMPS[0]

    def pump(self, engine):
        if self.tick >= len(STAMPS) or not engine.episode.capture.started:
            return   # like the real observation adapter, nothing is forwarded to the capture before it has started
        stamp = STAMPS[self.tick]
        failure = None
        try:
            if self.raise_at == self.tick:
                self.raise_at = None
                raise ValueError("DATA_SOURCE_CALLBACK_FAILED: /so101/simulation/physics_step_chunks: boom")
            for camera in ("head", "wrist"):
                if camera not in self.skip:
                    engine.episode.push(camera, stamp_s=stamp, pixels=FRAME)
                    self.counts[camera] += 1
            engine.episode.push_numeric(stamp_s=stamp, arm=[0.0] * 6, neck=0.0)
            last = round(stamp / 0.002)
            chunk, receipt = physics_chunk(self.tick + 1, last - 49, 50)
            self.receipt[0] = receipt
            self.adapter.accept_message(chunk)   # the fault-injecting class may drop exactly this message
            self.adapter.drain()
            self.counts["physics"] = self.tick + 1
        except Exception as error:   # ROS callbacks are isolated: the stream keeps flowing after a source failure
            failure = error
        for name in ("scene_state", "world", "joint_states"):
            if name not in self.skip:
                self.counts[name] += 1
        if self.record_ready is not None and self.script.get(self.tick):
            self.delivered_before_ready.append(self.record_ready())
        for text in self.script.get(self.tick, ()):
            engine.on_event_text(text)
        self.tick += 1
        if failure is not None:
            raise failure

    def collect(self, engine):
        capture = engine.episode.capture
        now = STAMPS[min(self.tick, len(STAMPS)) - 1] if self.tick else 0.0
        for when in capture.reference_requests(now):
            capture.on_reference({"source": "CONTROLLER_REFERENCE", "requested_sim_time_s": round(when, 6),
                                  "positions": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6], "accepted": True})
        capture.drain()

    def on_teacher_event(self, engine, event):
        self.events_seen.append(event["type"])
        capture = engine.episode.capture
        if event["type"] == "phase_begin" and event["payload"].get("goal_sent") is True:
            capture.on_event({"kind": "first_command", "sim_time_s": 1.05})
        elif event["type"] == "normal_stop":
            now = time.monotonic_ns()
            capture.on_normal_motion_end(dict(sim_time_ns=1_300_000_000, begin_monotonic_ns=now - 1,
                                              end_monotonic_ns=now))

    def tail_ready(self, engine):
        return self.tick >= len(STAMPS)

    def end_time_s(self, engine):
        return 1.3

    def physics_steps(self, engine):
        return self.adapter.original_durable_steps()

    def retained_history_start_s(self, engine):
        return self.adapter.earliest_sample_time_s()

    def source_counts(self, engine):
        return dict(self.counts)

    def close(self):
        if self.adapter is not None:
            self.adapter.close()


def make_episode(root):
    return PointEpisode(
        identity=IDENTITY, provenance=PROVENANCE, inputs={"inputs_sha256": "a" * 64}, episode_root=root / "episode",
        scope=SCOPE, scope_path=str(episode_audit_pair(root / "episode")[1]),
        physical_audit=recorder_physical_audit, monotonic=time.monotonic)


def build(tmp_path, *, script=None, fault="none", skip=(), raise_at=None, policy=None, clock=None, working=None,
          **sources_kwargs):
    working = working or tmp_path / "working"
    working.mkdir(parents=True, exist_ok=True)
    box = {}
    ready, result = working / "recorder-ready.json", working / "recorder-result.json"
    sources = SyntheticSources(box, teacher_script() if script is None else script, skip=skip, raise_at=raise_at,
                               record_ready=lambda: ready.exists(), **sources_kwargs)
    policy = dict(load_recorder_policy(POLICY_FILE), poll_s=0.0, **(policy or {}))
    engine = RecorderEngine(episode=make_episode(working), sources=sources, policy=policy, identity=STREAM_IDENTITY,
                            ready_file=ready, result_file=result, fault=fault,
                            **({} if clock is None else {"clock": clock}))
    box["engine"] = engine
    return engine, sources, working


def result_of(working):
    return json.loads((working / "recorder-result.json").read_bytes())


def readback(working):
    """Everything a fresh reader can verify from the sealed files alone, then the Teacher-reference check."""
    root = working / "episode"
    audit_manifest, scope = episode_audit_pair(root)
    seal = verify_episode_seal(root / "seal.json", audit_manifest=audit_manifest, scope=scope)
    manifest = verify_audit_manifest(audit_manifest)
    events = episode_qc.read_verified_rows(root / "audit", "events.jsonl")
    document = {"schema": "so101-dynamic-mujoco-execute-v2",
                "teacher_start_observation": observation(START_STEP), "teacher_end_observation": observation(END_STEP)}
    references = episode_qc.verify_teacher_references(
        document, identity=manifest["identity"], window=manifest["window"],
        physics_steps=episode_qc._raw_physics_samples(events))
    return seal, manifest, references


# ---- policy and sandbox ------------------------------------------------------------------------------------------

def test_the_frozen_policy_is_a_closed_hashed_document_with_a_bounded_max_duration():
    policy = load_recorder_policy(POLICY_FILE)
    assert 60.0 <= policy["max_duration_s"] <= 900.0 and policy["max_duration_s"] > 180.0
    assert re.fullmatch("[0-9a-f]{64}", policy["policy_sha256"])
    assert load_recorder_policy(POLICY_FILE.read_bytes())["policy_sha256"] == policy["policy_sha256"]


def test_the_frozen_policy_carries_the_orchestrators_bounds_too():
    """One frozen document bounds both processes: the Recorder's own loop and the orchestrator that starts and reaps it."""
    policy = load_recorder_policy(POLICY_FILE)
    assert 0.1 <= policy["ready_timeout_s"] <= 60.0
    assert policy["exit_wait_s"] > policy["finish_budget_s"], "the Recorder must be able to finish within the wait"
    assert 0.1 <= policy["term_grace_s"] <= 30.0


@pytest.mark.parametrize("change", [
    {"max_duration_s": 0}, {"max_duration_s": -1}, {"max_duration_s": float("inf")}, {"max_duration_s": 10_000},
    {"max_duration_s": True}, {"event_inbox_capacity": 0}, {"event_inbox_capacity": 1.5}, {"finish_budget_s": 0},
    {"unknown_key": 1}, {"kind": "OTHER"}, {"schema_version": 2}, {"ready_timeout_s": 0}, {"ready_timeout_s": 61},
    {"exit_wait_s": 0}, {"exit_wait_s": 1000}, {"term_grace_s": -1}, {"term_grace_s": 31}])
def test_a_policy_outside_the_closed_schema_is_refused(change):
    import yaml
    document = yaml.safe_load(POLICY_FILE.read_text())
    document.update(change)
    with pytest.raises(RecorderConfigRefused):
        load_recorder_policy(yaml.safe_dump(document).encode())


def test_a_policy_missing_a_field_or_not_yaml_is_refused():
    import yaml
    document = yaml.safe_load(POLICY_FILE.read_text())
    del document["max_duration_s"]
    for payload in (yaml.safe_dump(document).encode(), b"{{{ not yaml", b"[]"):
        with pytest.raises(RecorderConfigRefused):
            load_recorder_policy(payload)


def test_the_fault_option_set_is_exactly_the_recorder_side_set():
    assert FAULTS == ("none", "queue_overflow", "source_gap", "output_write_failure")


@pytest.mark.parametrize("fault", ["queue_overflow", "source_gap", "output_write_failure"])
def test_a_fault_outside_a_fault_sandbox_path_component_is_refused(fault, tmp_path):
    with pytest.raises(RecorderConfigRefused, match="RECORDER_FAULT_OUTSIDE_SANDBOX"):
        require_fault_sandbox(fault, tmp_path / "attempt" / "episode")
    with pytest.raises(RecorderConfigRefused, match="RECORDER_FAULT_OUTSIDE_SANDBOX"):
        require_fault_sandbox(fault, tmp_path / "fault-sandbox")   # the component must be an ancestor, not the leaf
    with pytest.raises(RecorderConfigRefused, match="RECORDER_FAULT_OUTSIDE_SANDBOX"):
        require_fault_sandbox(fault, tmp_path / "x-fault-sandbox-y" / "episode")


def test_the_sandbox_check_covers_every_output_path_and_follows_symlinks(tmp_path):
    sandbox = tmp_path / "run" / "fault-sandbox" / "a"
    sandbox.mkdir(parents=True)
    require_fault_sandbox("source_gap", sandbox / "episode", sandbox / "ready.json", sandbox / "result.json")
    with pytest.raises(RecorderConfigRefused, match="RECORDER_FAULT_OUTSIDE_SANDBOX"):
        require_fault_sandbox("source_gap", sandbox / "episode", tmp_path / "elsewhere" / "result.json")
    outside = tmp_path / "outside"
    outside.mkdir()
    (sandbox / "link").symlink_to(outside)
    with pytest.raises(RecorderConfigRefused, match="RECORDER_FAULT_OUTSIDE_SANDBOX"):
        require_fault_sandbox("source_gap", sandbox / "link" / "episode")


def test_no_fault_needs_no_sandbox_and_an_unknown_fault_is_refused(tmp_path):
    require_fault_sandbox("none", tmp_path / "anywhere" / "episode")
    for fault in ("recorder_absent", "recorder_late", "bogus"):
        with pytest.raises(RecorderConfigRefused, match="RECORDER_FAULT_UNKNOWN"):
            require_fault_sandbox(fault, tmp_path / "fault-sandbox" / "x" / "episode")


# ---- a normal run seals VALID ------------------------------------------------------------------------------------

def test_a_normal_run_over_the_synthetic_stream_seals_valid_rc0_and_passes_the_readback(tmp_path):
    engine, sources, working = build(tmp_path)
    assert engine.run() == RC_VALID == 0
    result = result_of(working)
    assert result["status"] == "VALID" and result["rc"] == 0 and result["reasons"] == []
    seal, manifest, references = readback(working)
    assert seal["status"] == "PASSED" and seal["record_count"] >= 2
    assert references["status"] == "PASS", references
    assert result["seal"]["sha256"] == __import__("hashlib").sha256((working / "episode/seal.json").read_bytes()).hexdigest()
    # the recording window covers the Teacher's start reference and ends after its end reference
    window = manifest["window"]
    assert window["collection_start_s"] <= 1.0 <= window["first_command_s"] and window["collection_end_s"] >= 1.4
    assert result["event_stream"]["accepted"] == 7 and result["event_stream"]["last_seq"] == 7
    assert result["event_stream"]["terminal"]["teacher_task_result"] == "PASS"
    assert result["policy_sha256"] == engine.policy["policy_sha256"] and result["fault"] == "none"
    assert sources.events_seen[0] == "reset_complete" and sources.events_seen[-1] == "terminal"
    assert list(working.glob("episode/**/*.tmp")) == []


def test_the_ready_file_says_listening_before_the_first_teacher_event_and_the_result_names_the_recording_start(tmp_path):
    engine, sources, working = build(tmp_path)
    engine.run()
    assert sources.delivered_before_ready and all(sources.delivered_before_ready)
    ready = json.loads((working / "recorder-ready.json").read_bytes())
    # LISTENING first, then rewritten as CAPTURING once the capture's initial boundary is committed (CP-3425)
    assert ready["schema"] == "SO101_RECORDER_READY_V1" and ready["state"] == "CAPTURING"
    assert (ready["session_id"], ready["reset_epoch"], ready["attempt_id"]) == ("session-1", 2, "attempt-1")
    assert ready["pid"] == os.getpid() and ready["collection_start_s"] == 1.0
    assert ready["topic"] == "/so101/teacher/events" and ready["fault"] == "none"
    assert ready["policy_sha256"] == engine.policy["policy_sha256"]
    # the result records when the capture started
    result = result_of(working)
    assert result["listening"] is True and result["collection_start_s"] == 1.0
    # an existing ready or result file is never reused: the Recorder refuses it before any recording starts
    with pytest.raises(RecorderConfigRefused, match="RECORDER_OUTPUT_EXISTS"):
        check_outputs_absent(working / "recorder-ready.json", working / "recorder-result.json")
    check_outputs_absent(working / "never-written.json")


def test_a_teacher_that_failed_but_left_complete_data_seals_a_failed_record_without_a_teacher_pass(tmp_path):
    engine, _, working = build(tmp_path, script=teacher_script(result="FAIL"))
    assert engine.run() == RC_VALID
    seal, _, references = readback(working)
    assert seal["status"] == "FAILED" and "TEACHER_TASK_NOT_PASSED" in seal["reason"]
    assert references["status"] == "PASS"
    assert result_of(working)["status"] == "VALID"


def test_the_recorder_keeps_servicing_its_sources_after_the_terminal_event_until_they_reach_the_teachers_end(tmp_path):
    engine, sources, working = build(tmp_path)
    pumps, asked = [], []
    original_pump = sources.pump
    sources.pump = lambda engine_: (pumps.append(sources.tick), original_pump(engine_))[1]
    sources.tail_ready = lambda engine_: (asked.append(len(pumps)), len(asked) >= 4)[1]
    assert engine.run() == RC_VALID
    assert len(asked) == 4 and asked == sorted(asked) and asked[-1] > asked[0], "each ask follows a servicing pass"
    assert result_of(working)["status"] == "VALID"


def test_a_source_that_never_reaches_the_teachers_end_stops_the_wait_at_the_finish_budget_and_is_invalid(tmp_path):
    ticks = iter(range(0, 100_000))
    engine, sources, working = build(tmp_path, clock=lambda: next(ticks) * 1.0)
    sources.tail_ready = lambda engine_: False
    assert engine.run() == RC_INVALID
    result = assert_invalid_retained(working, code="RECORDER_TAIL_NOT_REACHED")
    assert result["event_stream"]["terminal"]["teacher_task_result"] == "PASS"


# ---- INVALID verdicts: retained and sealed, rc 3 ------------------------------------------------------------------

def assert_invalid_retained(working, *, code, sealed=None):
    result = result_of(working)
    assert result["status"] == "INVALID" and result["rc"] == RC_INVALID == 3
    assert any(code in reason["reason"] for reason in result["reasons"]), result["reasons"]
    assert result["export_eligible"] is False
    inventory = result["episode_inventory"]
    assert inventory and all(re.fullmatch("[0-9a-f]{64}", item["sha256"]) for item in inventory.values())
    for relative, item in inventory.items():
        data = (working / "episode" / relative).read_bytes()
        assert len(data) == item["size"] and __import__("hashlib").sha256(data).hexdigest() == item["sha256"]
    # sealed=True: the episode must carry a verified FAILED seal; False: it must not; None: whichever the lost events
    # allowed, but a seal that exists must verify and say FAILED. The result file (digests of every retained file,
    # written durably) is the sealed INVALID record when the episode itself could not be sealed.
    if sealed is not False and (working / "episode/seal.json").exists():
        seal = verify_episode_seal(working / "episode/seal.json", audit_manifest=episode_audit_pair(working / "episode")[0],
                                   scope=episode_audit_pair(working / "episode")[1])
        assert seal["status"] == "FAILED" and "RECORDER_DATA_INVALID" in seal["reason"]
        assert result["seal"] is not None
    elif sealed:
        raise AssertionError("expected a sealed FAILED episode record")
    else:
        assert result["seal"] is None
    return result


@pytest.mark.parametrize("drop,code", [((3,), "TEACHER_EVENT_SEQUENCE_GAP"), ((1,), "TEACHER_EVENT_SEQUENCE_GAP"),
                                       ((4,), "TEACHER_EVENT_SEQUENCE_GAP")])
def test_a_gap_in_the_event_seq_marks_the_data_invalid_with_a_retained_sealed_record(tmp_path, drop, code):
    engine, _, working = build(tmp_path, script=teacher_script(drop=drop))
    assert engine.run() == RC_INVALID
    assert_invalid_retained(working, code=code)


def test_a_repeated_event_marks_the_data_invalid(tmp_path):
    engine, _, working = build(tmp_path, script=teacher_script(repeat=(3,)))
    assert engine.run() == RC_INVALID
    assert_invalid_retained(working, code="TEACHER_EVENT_SEQUENCE_REPEATED")


def test_a_malformed_event_text_marks_the_data_invalid(tmp_path):
    script = teacher_script()
    script[2] = ["{not json"] + script.get(2, [])
    engine, _, working = build(tmp_path, script=script)
    assert engine.run() == RC_INVALID
    assert_invalid_retained(working, code="TEACHER_EVENT_MALFORMED")


def test_events_of_another_attempt_are_ignored_and_a_wrong_epoch_of_this_attempt_is_invalid(tmp_path):
    other = teacher_script(identity=StreamIdentity("session-1", 2, "someone-else"))
    script = teacher_script()
    script[0] = other[0] + script[0]
    engine, _, working = build(tmp_path, script=script)
    assert engine.run() == RC_VALID
    assert result_of(working)["event_stream"]["foreign"] == 2
    wrong = teacher_script(identity=StreamIdentity("session-1", 9, "attempt-1"))
    engine, _, working = build(tmp_path / "second", script=wrong)
    assert engine.run() == RC_INVALID
    assert_invalid_retained(working, code="TEACHER_EVENT_IDENTITY_MISMATCH")


@pytest.mark.parametrize("skip,name", [(("wrist",), "wrist"), (("scene_state",), "scene_state"),
                                       (("world",), "world"), (("joint_states",), "joint_states")])
def test_a_missing_source_marks_the_data_invalid_naming_it(tmp_path, skip, name):
    engine, _, working = build(tmp_path, skip=skip)
    assert engine.run() == RC_INVALID
    assert_invalid_retained(working, code=f"RECORDER_SOURCE_MISSING: {name}", sealed=name != "wrist")


def test_a_source_that_raises_marks_the_data_invalid_and_the_run_still_ends_at_the_terminal_event(tmp_path):
    engine, sources, working = build(tmp_path, raise_at=2)
    assert engine.run() == RC_INVALID
    result = assert_invalid_retained(working, code="DATA_SOURCE_CALLBACK_FAILED", sealed=False)
    assert result["event_stream"]["terminal"]["teacher_task_result"] == "PASS"


def test_a_capture_start_that_raises_marks_the_data_invalid_and_the_run_still_ends(tmp_path):
    """REPLACED_BY (A4c): the in-child armed start step latched INVALID without raising; the engine does the same."""
    engine, sources, working = build(tmp_path, script={})

    def refuse(engine_):
        raise PermissionError("RECORDER_CAPTURE_START_SOURCE_LOST")

    sources.try_start = refuse
    ticks = iter(range(0, 10_000))
    engine.clock = lambda: next(ticks) * 1.0
    engine.policy = dict(engine.policy, max_duration_s=20.0)
    assert engine.run() == RC_INVALID
    assert_invalid_retained(working, code="RECORDER_CAPTURE_START_FAILED", sealed=False)


def test_a_teacher_with_no_normal_stop_leaves_an_unsealed_but_retained_invalid_record(tmp_path):
    engine, _, working = build(tmp_path, script=teacher_script(with_stop=False))
    assert engine.run() == RC_INVALID
    assert_invalid_retained(working, code="RECORDER_NORMAL_STOP_MISSING", sealed=False)


def test_a_missing_terminal_event_ends_at_the_frozen_max_duration_with_a_retained_invalid_record(tmp_path):
    ticks = iter(range(0, 10_000))
    engine, _, working = build(tmp_path, script=teacher_script(with_terminal=False), clock=lambda: next(ticks) * 1.0,
                               policy={"max_duration_s": 100.0})
    assert engine.run() == RC_INVALID
    assert_invalid_retained(working, code="RECORDER_MAX_DURATION_EXCEEDED", sealed=True)


def test_sigterm_before_the_terminal_event_leaves_a_retained_invalid_record(tmp_path):
    engine, sources, working = build(tmp_path, script=teacher_script(with_terminal=False))
    assert engine.run(should_stop=lambda: sources.tick >= 2) == RC_INVALID
    assert_invalid_retained(working, code="RECORDER_TERMINATED", sealed=False)


def test_sigterm_in_the_same_pass_as_the_terminal_event_does_not_discard_a_complete_recording(tmp_path):
    engine, sources, working = build(tmp_path)
    assert engine.run(should_stop=lambda: sources.tick >= len(STAMPS)) == RC_VALID


def test_the_teachers_setup_scene_operations_may_precede_the_capture_and_start_it(tmp_path):
    script = teacher_script(leading=[("scene_operation", {"operation": "apply", "state": "SETUP"}),
                                     ("scene_operation", {"operation": "readback", "state": "SETUP"})])
    early = script.pop(-1)
    engine, sources, working = build(tmp_path, script=script)
    seen = []
    original = sources.on_teacher_event

    def on_event(engine_, event):
        seen.append(event["type"])
        original(engine_, event)

    sources.on_teacher_event = on_event
    sources.try_start = lambda engine_: (engine_.episode.start(STAMPS[0]), STAMPS[0])[1] if len(
        [kind for kind in seen if kind == "scene_operation"]) >= 2 else None
    for text in early:
        engine.on_event_text(text)
    assert engine.run() == RC_VALID
    assert seen[:2] == ["scene_operation", "scene_operation"] and seen[2] == "reset_complete"
    assert result_of(working)["collection_start_s"] == 1.0
    assert result_of(working)["event_stream"]["accepted"] == 9


def test_a_capture_that_starts_only_after_the_teachers_start_observation_is_invalid(tmp_path):
    script = teacher_script(leading=[("scene_operation", {"operation": "readback", "state": "SETUP"})])
    engine, sources, working = build(tmp_path, script={})
    # the capture only starts once the Teacher is already running, and then at a stamp after the start observation (1.0)
    sources.try_start = lambda engine_: (engine_.episode.start(STAMPS[2]), STAMPS[2])[1] \
        if engine_.start_obs is not None else None
    for tick in sorted(script):
        for text in script[tick]:
            engine.on_event_text(text)
    ticks = iter(range(0, 10_000))
    engine.clock = lambda: next(ticks) * 1.0
    engine.policy = dict(engine.policy, max_duration_s=60.0)
    assert engine.run() == RC_INVALID
    assert_invalid_retained(working, code="RECORDER_TEACHER_EVENT_BEFORE_CAPTURE_START")


def test_a_teacher_event_before_the_recorder_is_ready_marks_the_data_invalid(tmp_path):
    engine, sources, working = build(tmp_path)
    sources.try_start = lambda engine: None        # the capture has not started when the Teacher begins
    ticks = iter(range(0, 10_000))
    engine.clock = lambda: next(ticks) * 1.0
    engine.policy = dict(engine.policy, max_duration_s=50.0)
    for text in teacher_script()[0]:
        engine.on_event_text(text)
    assert engine.run() == RC_INVALID
    assert_invalid_retained(working, code="RECORDER_NOT_READY_BEFORE_TEACHER_EVENT", sealed=False)


def test_a_capture_that_never_starts_is_invalid_though_the_recorder_announced_listening(tmp_path):
    engine, sources, working = build(tmp_path, script={})
    sources.try_start = lambda engine: None
    ticks = iter(range(0, 10_000))
    engine.clock = lambda: next(ticks) * 1.0
    engine.policy = dict(engine.policy, max_duration_s=20.0)
    assert engine.run() == RC_INVALID
    assert (working / "recorder-ready.json").exists(), "listening is announced whether or not the capture ever starts"
    assert result_of(working)["collection_start_s"] is None
    assert_invalid_retained(working, code="RECORDER_CAPTURE_NEVER_STARTED", sealed=False)


# ---- the three sandbox faults ------------------------------------------------------------------------------------

def sandbox_working(tmp_path):
    return tmp_path / "run" / "fault-sandbox" / "case" / "working"


def test_queue_overflow_reduces_only_the_recorder_side_event_queue_and_marks_the_data_invalid(tmp_path):
    engine, _, working = build(tmp_path, fault="queue_overflow", working=sandbox_working(tmp_path))
    assert engine.faults.inbox_capacity(256) == 2 and engine.faults.inbox_capacity(1) == 1
    ticks = iter(range(0, 100_000))
    engine.clock = lambda: next(ticks) * 1.0       # the dropped terminal event ends the run at the max duration
    engine.policy = dict(engine.policy, max_duration_s=60.0)
    assert engine.run() == RC_INVALID
    result = result_of(working)
    assert any(item["reason"].startswith("RECORDER_EVENT_QUEUE_OVERFLOW") for item in result["reasons"])
    assert result["fault"] == "queue_overflow" and result["status"] == "INVALID" and result["episode_inventory"]
    assert result["event_stream"]["inbox_dropped"] >= 1 and result["event_stream"]["inbox_capacity"] == 2


def test_without_the_fault_the_same_stream_never_overflows_the_event_queue(tmp_path):
    engine, _, working = build(tmp_path)
    assert engine.faults.inbox_capacity(256) == 256
    assert engine.run() == RC_VALID
    assert result_of(working)["event_stream"]["inbox_dropped"] == 0


def test_source_gap_drops_exactly_one_physics_chunk_and_the_real_adapter_marks_the_data_invalid(tmp_path):
    engine, sources, working = build(tmp_path, fault="source_gap", working=sandbox_working(tmp_path))
    assert engine.run() == RC_INVALID
    result = assert_invalid_retained(working, code="PHYSICS_RAW_CONTINUITY_INVALID", sealed=False)
    assert engine.faults.snapshot()["physics_chunks_seen"] >= 3 and engine.faults.snapshot()["physics_chunks_dropped"] == 1
    assert result["fault"] == "source_gap"


def test_the_gap_fault_class_drops_exactly_once_and_passes_every_other_chunk_through(tmp_path):
    injector = FaultInjector("source_gap")
    passed = [injector.physics_chunk(f"chunk-{index}") for index in range(1, 8)]
    assert passed.count(None) == 1 and passed[2] is None, "the third chunk, after two good ones"
    assert FaultInjector("none").physics_chunk("x") == "x"
    assert FaultInjector("queue_overflow").physics_chunk("x") == "x"


@pytest.mark.skipif(os.geteuid() == 0, reason="a root process ignores directory permissions")
def test_output_write_failure_makes_the_sandbox_episode_read_only_and_marks_the_data_invalid(tmp_path):
    working = sandbox_working(tmp_path)
    engine, _, _ = build(tmp_path, fault="output_write_failure", working=working)
    assert engine.run() == RC_INVALID
    result = assert_invalid_retained(working, code="RECORDER_WRITE_FAILED", sealed=False)
    assert result["fault"] == "output_write_failure"
    # the permission change is undone at the end so the retained evidence can be inspected and later cleaned up
    assert os.access(working / "episode", os.W_OK), "the Recorder restores owner write access to the retained tree"
    assert os.access(working / "episode" / "frames", os.W_OK)


@pytest.mark.skipif(os.geteuid() == 0, reason="a root process ignores directory permissions")
def test_the_write_fault_never_touches_anything_outside_the_episode_tree(tmp_path):
    working = sandbox_working(tmp_path)
    marker = working.parent / "other-file.txt"
    working.mkdir(parents=True)
    marker.write_text("x")
    before = working.stat().st_mode, marker.stat().st_mode
    engine, _, _ = build(tmp_path, fault="output_write_failure", working=working)
    engine.run()
    assert (working.stat().st_mode, marker.stat().st_mode) == before
    assert (working / "recorder-result.json").is_file(), "the result lives beside the episode, outside the fault"


def test_a_recorder_fault_never_reaches_the_teacher_stream_or_control(tmp_path):
    """The engine's only outputs are files; it holds no publisher, client or command connection."""
    engine, _, working = build(tmp_path, fault="queue_overflow", working=sandbox_working(tmp_path))
    ticks = iter(range(0, 100_000))
    engine.clock = lambda: next(ticks) * 1.0
    engine.policy = dict(engine.policy, max_duration_s=60.0)
    engine.run()
    assert not any(hasattr(engine, name) for name in ("publisher", "client", "connection", "revoke", "cancel", "pause"))


# ---- threading ---------------------------------------------------------------------------------------------------

def test_events_may_arrive_from_the_ros_callback_thread_while_the_engine_steps(tmp_path):
    script = teacher_script()
    engine, sources, working = build(tmp_path, script={})
    texts = [text for tick in sorted(script) for text in script[tick]]
    started = threading.Event()

    def deliver():
        started.wait(5)
        for text in texts:
            engine.on_event_text(text)
            time.sleep(0.002)

    thread = threading.Thread(target=deliver)
    thread.start()
    original = sources.pump

    def pump(engine_):
        started.set()
        original(engine_)
        if sources.tick >= len(STAMPS):
            thread.join(10)
    sources.pump = pump
    assert engine.run() == RC_VALID
    assert result_of(working)["event_stream"]["accepted"] == len(texts) == 7


# ---- the entry point -----------------------------------------------------------------------------------------------

def test_setup_py_declares_the_act_episode_recorder_console_entry_and_it_resolves_to_a_callable(monkeypatch):
    """Same capture pattern as test_src_layout: run setup.py with setuptools.setup replaced by a recorder."""

    import importlib
    import runpy

    import setuptools

    captured = {}
    monkeypatch.setattr(setuptools, "setup", lambda **kwargs: captured.update(kwargs))
    monkeypatch.chdir(PACKAGE)
    runpy.run_path(str(PACKAGE / "setup.py"), run_name="__main__")
    scripts = captured["entry_points"]["console_scripts"]
    entry = "act_episode_recorder = so101_demo.cli.act_episode_recorder:main"
    assert entry in scripts and scripts.count(entry) == 1
    module_name, function = entry.split(" = ")[1].split(":")
    assert callable(getattr(importlib.import_module(module_name), function))
    # the new policy file is installed with the other config files, so the entry finds its default
    installed = [path for _, paths in captured["data_files"] for path in paths]
    assert "config/act/episode_recorder_v1.yaml" in installed


def args(tmp_path, *extra, sandbox=False, ready=True):
    base = tmp_path / "run" / ("fault-sandbox/case" if sandbox else "plain") / "working"
    return ["--session-id", "session-1", "--expected-reset-epoch", "2", "--attempt-id", "attempt-1",
            "--episode-root", str(base / "episode"), "--evidence-root", str(base / "dynamic"),
            "--episode-scope", str(tmp_path / "scope.json"), "--episode-inputs-manifest", str(tmp_path / "inputs"),
            "--ready-file", str(base / "recorder-ready.json"), "--result-file", str(base / "recorder-result.json"),
            *extra]


def policy_loader(options):
    """The policy a real run takes from the frozen manifest; these tests give the repository's own file."""
    return load_recorder_policy(POLICY_FILE)


@pytest.mark.parametrize("fault", ["queue_overflow", "source_gap", "output_write_failure"])
def test_main_refuses_a_fault_outside_the_sandbox_with_rc2_before_creating_anything(tmp_path, fault, capsys):
    from so101_demo.cli import act_episode_recorder
    opened = []
    code = act_episode_recorder.main(args(tmp_path, "--fault", fault),
                                     episode_factory=lambda options: opened.append(options), policy_loader=policy_loader)
    assert code == RC_CONFIG == 2
    assert opened == [], "no episode is opened for a refused configuration"
    assert not (tmp_path / "run").exists()
    assert "RECORDER_FAULT_OUTSIDE_SANDBOX" in capsys.readouterr().err


@pytest.mark.parametrize("fault", ["recorder_absent", "recorder_late", "nonsense"])
def test_main_refuses_unknown_faults_with_rc2(tmp_path, capsys, fault):
    """`recorder_absent` and `recorder_late` are orchestrator faults: the Recorder process itself does not know them."""
    from so101_demo.cli import act_episode_recorder
    argv = args(tmp_path, "--fault", fault, sandbox=True)
    assert act_episode_recorder.main(argv, episode_factory=lambda options: pytest.fail("opened"),
                                     policy_loader=policy_loader) == RC_CONFIG
    assert "RECORDER_FAULT_UNKNOWN" in capsys.readouterr().err


def test_main_refuses_a_policy_that_was_not_frozen_with_rc2(tmp_path, capsys):
    """The Recorder's bounds come from the frozen inputs, never from a live file: an unfrozen set is refused."""
    from so101_demo.cli import act_episode_recorder
    assert act_episode_recorder.main(args(tmp_path), episode_factory=lambda options: pytest.fail("opened")) == RC_CONFIG
    assert "RECORDER_FROZEN_INPUTS_INVALID" in capsys.readouterr().err


def test_main_refuses_missing_required_arguments_with_rc2_not_an_argparse_exit(tmp_path, capsys):
    from so101_demo.cli import act_episode_recorder
    assert act_episode_recorder.main(["--session-id", "s"]) == RC_CONFIG
    assert capsys.readouterr().err


def test_main_refuses_existing_output_files_with_rc2(tmp_path, capsys):
    from so101_demo.cli import act_episode_recorder
    argv = args(tmp_path)
    ready = Path(argv[argv.index("--ready-file") + 1])
    ready.parent.mkdir(parents=True)
    ready.write_text("{}")
    assert act_episode_recorder.main(argv, episode_factory=lambda options: pytest.fail("opened"),
                                     policy_loader=policy_loader) == RC_CONFIG
    assert "RECORDER_OUTPUT_EXISTS" in capsys.readouterr().err


def test_main_runs_the_engine_over_injected_parts_and_returns_the_verdict_code(tmp_path):
    from so101_demo.cli import act_episode_recorder
    argv = args(tmp_path)
    working = Path(argv[argv.index("--result-file") + 1]).parent
    box = {}

    def episode_factory(options):
        working.mkdir(parents=True, exist_ok=True)
        return make_episode(working)

    def sources_factory(options, episode, policy, faults, node):
        box["sources"] = SyntheticSources(box, teacher_script())
        return box["sources"]

    code = act_episode_recorder.main(argv, episode_factory=episode_factory, sources_factory=sources_factory,
                                     node_factory=lambda options: SimpleNamespace(close=lambda: None),
                                     policy_loader=policy_loader, install_signal_handlers=False)
    assert code == RC_VALID
    assert result_of(working)["status"] == "VALID"


def test_main_returns_3_for_invalid_data_and_keeps_the_record(tmp_path):
    from so101_demo.cli import act_episode_recorder
    argv = args(tmp_path)
    working = Path(argv[argv.index("--result-file") + 1]).parent
    box = {}

    def episode_factory(options):
        working.mkdir(parents=True, exist_ok=True)
        return make_episode(working)

    code = act_episode_recorder.main(
        argv, episode_factory=episode_factory,
        sources_factory=lambda options, episode, policy, faults, node: SyntheticSources(box, teacher_script(drop=(3,))),
        node_factory=lambda options: SimpleNamespace(close=lambda: None), policy_loader=policy_loader,
        install_signal_handlers=False)
    assert code == RC_INVALID
    assert_invalid_retained(working, code="TEACHER_EVENT_SEQUENCE_GAP")


def test_an_episode_that_cannot_be_opened_is_rc2_not_a_crash(tmp_path, capsys):
    from so101_demo.cli import act_episode_recorder

    def refuse(options):
        raise ValueError("EPISODE_LEASE_NOT_CURRENT")

    assert act_episode_recorder.main(args(tmp_path), episode_factory=refuse, policy_loader=policy_loader) == RC_CONFIG
    assert "EPISODE_LEASE_NOT_CURRENT" in capsys.readouterr().err




def test_c3_the_not_ready_reason_says_ready_means_listening_and_the_capture_had_not_started(tmp_path):
    engine, sources, working = build(tmp_path)
    sources.try_start = lambda engine: None
    ticks = iter(range(0, 10_000))
    engine.clock = lambda: next(ticks) * 1.0
    engine.policy = dict(engine.policy, max_duration_s=50.0)
    for text in teacher_script()[0]:
        engine.on_event_text(text)
    assert engine.run() == RC_INVALID
    entries = [item for item in result_of(working)["reasons"]
               if "RECORDER_NOT_READY_BEFORE_TEACHER_EVENT" in item["reason"]]
    assert entries and entries[0]["capture_started"] == "False"
    assert "LISTENING" in entries[0]["ready_means"]
