"""The offline episode engine (Phase A4a, cleanup step 2): a consumer of the Teacher event stream and the sources.

The engine is driven here by a synthetic stream and synthetic sources over a real PointEpisode (real lossless writer,
real audit, real seal and readback). The real physics adapter is used for the source-gap case. The Teacher is never
involved: every defect is a verdict on the data, never an input to control. The live Recorder process (ready file, signals,
sandbox faults, console entry) no longer exists; the helpers below are shared by the other engine and source tests.
"""

import json
import os
import re
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
from so101_demo.act.offline.engine import RC_INVALID, RC_VALID, OfflineEngine
from so101_demo.act.offline.policy import RecorderConfigRefused, check_outputs_absent, load_recorder_policy
from test_act_recorder import PROVENANCE
from test_act_seal_and_downgrade import IDENTITY, SCOPE, recorder_physical_audit
from paths import PACKAGE_ROOT

PACKAGE = PACKAGE_ROOT
POLICY_FILE = PACKAGE / "config/act/episode_recorder.yaml"
STREAM_IDENTITY = StreamIdentity(IDENTITY["session_id"], IDENTITY["reset_epoch"], IDENTITY["attempt_id"])
FRAME = np.zeros((480, 640, 3), dtype=np.uint8)
STAMPS = (1.0, 1.1, 1.2, 1.3, 1.4, 1.5)
START_STEP, END_STEP = 500, 700           # 1.0 s and 1.4 s at 2 ms per physics step
NODE = SimpleNamespace(create_subscription=lambda *args, **kwargs: object(), destroy_subscription=lambda item: None,
                       context=None)
#: the replay node of an engine that is driven by hand: the bag never ends
NOT_EXHAUSTED = SimpleNamespace(exhausted=False)


class EndingNode:
    """A replay node whose bag is exhausted once `ended()` says so."""

    def __init__(self, ended):
        self._ended = ended

    @property
    def exhausted(self):
        return self._ended()


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


class SourcesDefaults:
    """What the engine asks of its sources, with the no-op defaults a synthetic source leaves out."""

    def prepare(self, engine):
        return None

    def collect(self, engine):
        return None

    def on_teacher_event(self, engine, event):
        return None

    def start_gate_summary(self, engine):
        return {}

    def tail_ready(self, engine):
        return True

    def end_time_s(self, engine):
        return engine.episode.capture.window["collection_end_s"]

    def physics_steps(self, engine):
        return []

    def final_issues(self, engine):
        return []

    def source_counts(self, engine):
        return {}

    def close(self):
        return None


class SyntheticSources(SourcesDefaults):
    """One simulated 10 Hz tick per `pump`: RGB, numeric state, one physics chunk and the scripted Teacher events.

    The physics adapter is the real `RosEpisodePhysicsAdapter`, so continuity is the real check. `drop_chunk` is the tick
    (1-based) whose physics chunk never reaches the adapter; `read_only_after_start` makes the episode tree read-only once the
    capture started (a write failure), and `close` gives the owner write access back.
    """

    def __init__(self, engine_box, script, *, skip=(), raise_at=None, drop_chunk=None, read_only_after_start=False):
        self.box, self.script, self.skip = engine_box, script, set(skip)
        self.tick = 0
        self.raise_at = raise_at
        self.drop_chunk = drop_chunk
        self.read_only_after_start = read_only_after_start
        self._modes = {}
        self.counts = {"head": 0, "wrist": 0, "physics": 0, "scene_state": 0, "world": 0, "joint_states": 0}
        self.adapter = None
        self.receipt = [0]
        self.events_seen = []

    def prepare(self, engine):
        from so101_demo.adapters.act.ros_episode_physics import RosEpisodePhysicsAdapter
        self.adapter = RosEpisodePhysicsAdapter(NODE, session_id="session-1", reset_epoch=2, nq=2, nv=1, audit=engine.episode.capture.audit,
                           clock_ns=lambda: self.receipt[0], history_capacity=4096)

    def try_start(self, engine):
        engine.episode.start(STAMPS[0])
        if self.read_only_after_start:
            self._make_read_only(Path(engine.episode.capture.recorder.root))
        return STAMPS[0]

    def _make_read_only(self, root):
        paths = [root]
        for directory, directories, files in os.walk(root):
            paths.extend(Path(directory) / name for name in (*directories, *files))
        for path in paths:
            if not path.is_symlink():
                mode = path.lstat().st_mode & 0o7777
                self._modes[str(path)] = mode
                os.chmod(path, mode & ~0o222)

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
            if self.drop_chunk != self.tick + 1:
                self.adapter.accept_message(chunk)
            self.adapter.drain()
            self.counts["physics"] = self.tick + 1
        except Exception as error:   # ROS callbacks are isolated: the stream keeps flowing after a source failure
            failure = error
        for name in ("scene_state", "world", "joint_states"):
            if name not in self.skip:
                self.counts[name] += 1
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

    def source_counts(self, engine):
        return dict(self.counts)

    def close(self):
        for name in sorted(self._modes, key=len):   # parents before children
            try:
                os.chmod(name, self._modes[name])
            except OSError:
                pass
        self._modes = {}
        if self.adapter is not None:
            self.adapter.close()


def make_episode(root):
    return PointEpisode(
        identity=IDENTITY, provenance=PROVENANCE, inputs={"inputs_sha256": "a" * 64}, episode_root=root / "episode",
        scope=SCOPE, scope_path=str(episode_audit_pair(root / "episode")[1]),
        physical_audit=recorder_physical_audit, monotonic=time.monotonic)


def build(tmp_path, *, script=None, skip=(), raise_at=None, policy=None, clock=None, working=None, **sources_kwargs):
    working = working or tmp_path / "working"
    working.mkdir(parents=True, exist_ok=True)
    box = {}
    result = working / "recorder-result.json"
    sources = SyntheticSources(box, teacher_script() if script is None else script, skip=skip, raise_at=raise_at,
                               **sources_kwargs)
    policy = dict(load_recorder_policy(POLICY_FILE), poll_s=0.0, **(policy or {}))
    engine = OfflineEngine(episode=make_episode(working), sources=sources, policy=policy, identity=STREAM_IDENTITY,
                           result_file=result, clock=time.monotonic if clock is None else clock,
                           sleep=lambda seconds: None)
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
    document = {"schema": "so101-teacher-execute", "schema_version": 1,
                "teacher_start_observation": observation(START_STEP), "teacher_end_observation": observation(END_STEP)}
    references = episode_qc.verify_teacher_references(
        document, identity=manifest["identity"], window=manifest["window"],
        physics_steps=episode_qc._raw_physics_samples(events))
    return seal, manifest, references


# ---- policy -------------------------------------------------------------------------------------------------------

def test_the_frozen_policy_is_a_closed_hashed_document_with_a_bounded_max_duration():
    policy = load_recorder_policy(POLICY_FILE)
    assert 60.0 <= policy["max_duration_s"] <= 900.0 and policy["max_duration_s"] > 180.0
    assert re.fullmatch("[0-9a-f]{64}", policy["policy_sha256"])
    assert load_recorder_policy(POLICY_FILE.read_bytes())["policy_sha256"] == policy["policy_sha256"]


def test_the_frozen_policy_carries_the_orchestrators_bounds_too():
    """The closed policy document still carries the bounds only the retired live Recorder read; they stay validated (frozen manifests)."""
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


def test_an_existing_result_file_is_never_reused_and_no_output_check_trips_on_an_absent_one(tmp_path):
    (tmp_path / "recorder-result.json").write_text("{}")
    with pytest.raises(RecorderConfigRefused, match="RECORDER_OUTPUT_EXISTS"):
        check_outputs_absent(tmp_path / "recorder-result.json")
    check_outputs_absent(tmp_path / "never-written.json")


def test_the_engine_refuses_to_start_over_an_existing_result_file(tmp_path):
    engine, _, working = build(tmp_path)
    (working / "recorder-result.json").write_text("{}")
    with pytest.raises(RecorderConfigRefused, match="RECORDER_OUTPUT_EXISTS"):
        engine.process(NOT_EXHAUSTED)


def test_setup_py_no_longer_declares_the_live_recorder_entry_and_still_installs_the_policy_file(monkeypatch):
    """Same capture pattern as test_src_layout: run setup.py with setuptools.setup replaced by a recorder."""

    import runpy

    import setuptools

    captured = {}
    monkeypatch.setattr(setuptools, "setup", lambda **kwargs: captured.update(kwargs))
    monkeypatch.chdir(PACKAGE)
    runpy.run_path(str(PACKAGE / "setup.py"), run_name="__main__")
    scripts = captured["entry_points"]["console_scripts"]
    assert not any(entry.startswith("act_episode_recorder") for entry in scripts)
    assert "act_offline_episode = so101_demo.cli.act_offline_episode:main" in scripts
    # the frozen policy file is still installed with the other config files: frozen manifests are built from it
    installed = [path for _, paths in captured["data_files"] for path in paths]
    assert "config/act/episode_recorder.yaml" in installed


# ---- a normal run seals VALID ------------------------------------------------------------------------------------

def test_a_normal_run_over_the_synthetic_stream_seals_valid_rc0_and_passes_the_readback(tmp_path):
    engine, sources, working = build(tmp_path)
    assert engine.process(NOT_EXHAUSTED) == RC_VALID == 0
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
    # the document keeps the shape of schema V1: the process-specific fields of a live Recorder are constants
    assert result["pid"] == 0 and result["listening"] is True and result["stall_telemetry"] == {}
    assert result["faults"] == {"fault": "none", "physics_chunks_dropped": 0, "physics_chunks_seen": 0}
    assert result["event_stream"]["deferred_replayed"] == 0 and result["event_stream"]["deferred_first"] is None
    assert sources.events_seen[0] == "reset_complete" and sources.events_seen[-1] == "terminal"
    assert list(working.glob("episode/**/*.tmp")) == []


def test_the_result_names_the_recording_start(tmp_path):
    engine, sources, working = build(tmp_path)
    engine.process(NOT_EXHAUSTED)
    result = result_of(working)
    assert result["schema"] == "SO101_RECORDER_RESULT_V1"
    assert (result["identity"]["session_id"], result["identity"]["reset_epoch"], result["identity"]["attempt_id"]) == (
        "session-1", 2, "attempt-1")
    assert result["listening"] is True and result["collection_start_s"] == 1.0
    assert not (working / "recorder-ready.json").exists(), "there is no ready file any more"


def test_a_teacher_that_failed_but_left_complete_data_seals_a_failed_record_without_a_teacher_pass(tmp_path):
    engine, _, working = build(tmp_path, script=teacher_script(result="FAIL"))
    assert engine.process(NOT_EXHAUSTED) == RC_VALID
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
    assert engine.process(NOT_EXHAUSTED) == RC_VALID
    assert len(asked) == 4 and asked == sorted(asked) and asked[-1] > asked[0], "each ask follows a servicing pass"
    assert result_of(working)["status"] == "VALID"


def test_a_source_that_never_reaches_the_teachers_end_stops_the_wait_at_the_finish_budget_and_is_invalid(tmp_path):
    ticks = iter(range(0, 100_000))
    engine, sources, working = build(tmp_path, clock=lambda: next(ticks) * 1.0)
    sources.tail_ready = lambda engine_: False
    assert engine.process(NOT_EXHAUSTED) == RC_INVALID
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
    assert engine.process(NOT_EXHAUSTED) == RC_INVALID
    assert_invalid_retained(working, code=code)


def test_a_repeated_event_marks_the_data_invalid(tmp_path):
    engine, _, working = build(tmp_path, script=teacher_script(repeat=(3,)))
    assert engine.process(NOT_EXHAUSTED) == RC_INVALID
    assert_invalid_retained(working, code="TEACHER_EVENT_SEQUENCE_REPEATED")


def test_a_malformed_event_text_marks_the_data_invalid(tmp_path):
    script = teacher_script()
    script[2] = ["{not json"] + script.get(2, [])
    engine, _, working = build(tmp_path, script=script)
    assert engine.process(NOT_EXHAUSTED) == RC_INVALID
    assert_invalid_retained(working, code="TEACHER_EVENT_MALFORMED")


def test_events_of_another_attempt_are_ignored_and_a_wrong_epoch_of_this_attempt_is_invalid(tmp_path):
    other = teacher_script(identity=StreamIdentity("session-1", 2, "someone-else"))
    script = teacher_script()
    script[0] = other[0] + script[0]
    engine, _, working = build(tmp_path, script=script)
    assert engine.process(NOT_EXHAUSTED) == RC_VALID
    assert result_of(working)["event_stream"]["foreign"] == 2
    wrong = teacher_script(identity=StreamIdentity("session-1", 9, "attempt-1"))
    engine, _, working = build(tmp_path / "second", script=wrong)
    assert engine.process(NOT_EXHAUSTED) == RC_INVALID
    assert_invalid_retained(working, code="TEACHER_EVENT_IDENTITY_MISMATCH")


@pytest.mark.parametrize("skip,name", [(("wrist",), "wrist"), (("scene_state",), "scene_state"),
                                       (("world",), "world"), (("joint_states",), "joint_states")])
def test_a_missing_source_marks_the_data_invalid_naming_it(tmp_path, skip, name):
    engine, _, working = build(tmp_path, skip=skip)
    assert engine.process(NOT_EXHAUSTED) == RC_INVALID
    assert_invalid_retained(working, code=f"RECORDER_SOURCE_MISSING: {name}", sealed=name != "wrist")


def test_a_source_that_raises_marks_the_data_invalid_and_the_run_still_ends_at_the_terminal_event(tmp_path):
    engine, sources, working = build(tmp_path, raise_at=2)
    assert engine.process(NOT_EXHAUSTED) == RC_INVALID
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
    assert engine.process(NOT_EXHAUSTED) == RC_INVALID
    assert_invalid_retained(working, code="RECORDER_CAPTURE_START_FAILED", sealed=False)


def test_a_teacher_with_no_normal_stop_leaves_an_unsealed_but_retained_invalid_record(tmp_path):
    engine, _, working = build(tmp_path, script=teacher_script(with_stop=False))
    assert engine.process(NOT_EXHAUSTED) == RC_INVALID
    assert_invalid_retained(working, code="RECORDER_NORMAL_STOP_MISSING", sealed=False)


def test_a_missing_terminal_event_ends_at_the_frozen_max_duration_with_a_retained_invalid_record(tmp_path):
    ticks = iter(range(0, 10_000))
    engine, _, working = build(tmp_path, script=teacher_script(with_terminal=False), clock=lambda: next(ticks) * 1.0,
                               policy={"max_duration_s": 100.0})
    assert engine.process(NOT_EXHAUSTED) == RC_INVALID
    assert_invalid_retained(working, code="RECORDER_MAX_DURATION_EXCEEDED", sealed=True)


def test_a_bag_that_ends_without_a_terminal_event_is_invalid_with_a_retained_record(tmp_path):
    engine, sources, working = build(tmp_path, script=teacher_script(with_terminal=False))
    node = EndingNode(lambda: sources.tick >= len(STAMPS))
    assert engine.process(node) == RC_INVALID
    assert_invalid_retained(working, code="OFFLINE_BAG_ENDED_WITHOUT_TERMINAL", sealed=True)


def test_reasons_handed_to_the_engine_are_latched_before_the_replay(tmp_path):
    engine, _, working = build(tmp_path)
    assert engine.process(NOT_EXHAUSTED, preset_reasons=["OFFLINE_SOURCE_GAP: arm gaps=1"]) == RC_INVALID
    assert_invalid_retained(working, code="OFFLINE_SOURCE_GAP: arm gaps=1")


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
    assert engine.process(NOT_EXHAUSTED) == RC_VALID
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
    assert engine.process(NOT_EXHAUSTED) == RC_INVALID
    assert_invalid_retained(working, code="RECORDER_NOT_READY_BEFORE_TEACHER_EVENT")


def test_a_teacher_event_before_the_recorder_is_ready_marks_the_data_invalid(tmp_path):
    engine, sources, working = build(tmp_path)
    sources.try_start = lambda engine: None        # the capture has not started when the Teacher begins
    ticks = iter(range(0, 10_000))
    engine.clock = lambda: next(ticks) * 1.0
    engine.policy = dict(engine.policy, max_duration_s=50.0)
    for text in teacher_script()[0]:
        engine.on_event_text(text)
    assert engine.process(NOT_EXHAUSTED) == RC_INVALID
    assert_invalid_retained(working, code="RECORDER_NOT_READY_BEFORE_TEACHER_EVENT", sealed=False)


def test_a_capture_that_never_starts_is_invalid(tmp_path):
    engine, sources, working = build(tmp_path, script={})
    sources.try_start = lambda engine: None
    ticks = iter(range(0, 10_000))
    engine.clock = lambda: next(ticks) * 1.0
    engine.policy = dict(engine.policy, max_duration_s=20.0)
    assert engine.process(NOT_EXHAUSTED) == RC_INVALID
    assert result_of(working)["collection_start_s"] is None
    assert_invalid_retained(working, code="RECORDER_CAPTURE_NEVER_STARTED", sealed=False)


def test_a_capture_that_starts_after_an_early_teacher_event_is_still_invalid(tmp_path):
    """Events are no longer held for a late capture start: one that arrived before it makes the data INVALID."""
    engine, sources, working = build(tmp_path)
    started = []
    sources.try_start = lambda engine_: (engine_.episode.start(STAMPS[0]), STAMPS[0])[1] if started else started.append(1)
    for text in teacher_script()[0]:
        engine.on_event_text(text)
    assert engine.process(NOT_EXHAUSTED) == RC_INVALID
    result = assert_invalid_retained(working, code="RECORDER_NOT_READY_BEFORE_TEACHER_EVENT")
    assert result["event_stream"]["deferred_replayed"] == 0 and result["event_stream"]["deferred_first"][0] == "reset_complete"


# ---- source and queue defects ------------------------------------------------------------------------------------

def test_an_event_burst_beyond_the_inbox_capacity_marks_the_data_invalid(tmp_path):
    engine, _, working = build(tmp_path, script={})
    engine._capacity = 2
    for tick, texts in sorted(teacher_script().items()):
        for text in texts:
            engine.on_event_text(text)
    ticks = iter(range(0, 100_000))
    engine.clock = lambda: next(ticks) * 1.0       # the dropped terminal event ends the run at the max duration
    engine.policy = dict(engine.policy, max_duration_s=60.0)
    assert engine.process(NOT_EXHAUSTED) == RC_INVALID
    result = result_of(working)
    assert any(item["reason"].startswith("RECORDER_EVENT_QUEUE_OVERFLOW") for item in result["reasons"])
    assert result["status"] == "INVALID" and result["episode_inventory"]
    assert result["event_stream"]["inbox_dropped"] >= 1 and result["event_stream"]["inbox_capacity"] == 2


def test_without_a_burst_the_same_stream_never_overflows_the_event_queue(tmp_path):
    engine, _, working = build(tmp_path)
    assert engine.process(NOT_EXHAUSTED) == RC_VALID
    assert result_of(working)["event_stream"]["inbox_dropped"] == 0


def test_a_missing_physics_chunk_is_a_gap_and_the_real_adapter_marks_the_data_invalid(tmp_path):
    engine, sources, working = build(tmp_path, drop_chunk=3)
    assert engine.process(NOT_EXHAUSTED) == RC_INVALID
    assert_invalid_retained(working, code="PHYSICS_RAW_CONTINUITY_INVALID", sealed=False)


@pytest.mark.skipif(os.geteuid() == 0, reason="a root process ignores directory permissions")
def test_a_write_failure_marks_the_data_invalid_and_keeps_the_record(tmp_path):
    engine, _, working = build(tmp_path, read_only_after_start=True)
    assert engine.process(NOT_EXHAUSTED) == RC_INVALID
    assert_invalid_retained(working, code="RECORDER_WRITE_FAILED", sealed=False)
    assert os.access(working / "episode", os.W_OK), "the owner write access is given back so the evidence can be cleaned up"


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
    assert engine.process(NOT_EXHAUSTED) == RC_VALID
    assert result_of(working)["event_stream"]["accepted"] == len(texts) == 7


def test_the_not_ready_reason_says_ready_means_listening_and_the_capture_had_not_started(tmp_path):
    engine, sources, working = build(tmp_path)
    sources.try_start = lambda engine: None
    ticks = iter(range(0, 10_000))
    engine.clock = lambda: next(ticks) * 1.0
    engine.policy = dict(engine.policy, max_duration_s=50.0)
    for text in teacher_script()[0]:
        engine.on_event_text(text)
    assert engine.process(NOT_EXHAUSTED) == RC_INVALID
    entries = [item for item in result_of(working)["reasons"]
               if "RECORDER_NOT_READY_BEFORE_TEACHER_EVENT" in item["reason"]]
    assert entries and entries[0]["capture_started"] == "False"
    assert "LISTENING" in entries[0]["ready_means"]
