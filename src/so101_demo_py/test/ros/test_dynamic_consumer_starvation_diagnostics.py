"""Observation-only D8 diagnostics: phase timing, chunk receipt delay, callback census."""

import json
from types import SimpleNamespace

import pytest
from so101_mujoco_support.msg import PhysicsStepEvidenceChunk  # noqa: F401  (message package must import)

from test_act_raw_physics_chunks import _chunk
from test_dynamic_scene_sync import RecordingTaskScenePort, _observation, _options, _runtime

TIMING_PREFIX = "DYNAMIC_EXECUTE_PHASE_TIMING "
LATE_PREFIX = "EPISODE_PHYSICS_CHUNK_LATE "

SUCCESS_PHASES = [
    "source.arm.begin", "source.arm.end", "ready",
    "get_one.begin", "get_one.end",
    "truth.observe_initial.begin", "truth.observe_initial.end",
    "bind_scene_source.begin", "bind_scene_source.end",
    "task_scene_port.begin", "task_scene_port.end",
    "prepare_dynamic_cup_scene.begin", "prepare_dynamic_cup_scene.end",
    "validate_cup_scene.1.observe.begin", "validate_cup_scene.1.observe.end",
    "validate_cup_scene.1.check.begin", "validate_cup_scene.1.check.end",
    "validate_cup_scene.2.observe.begin", "validate_cup_scene.2.observe.end",
    "validate_cup_scene.2.check.begin", "validate_cup_scene.2.check.end",
    "resolve_motion_targets.begin", "resolve_motion_targets.end",
    "reachability_preflight.begin", "reachability_preflight.end",
    "execution.construct.begin", "execution.construct.end",
    "build_actions.begin", "build_actions.end", "runner.run.begin",
]


def _observations():
    return tuple(_observation(simulator_x=-0.03, moveit_x=-0.03) for _ in range(3))


def _timing_lines(err):
    return [line for line in err.splitlines() if line.startswith(TIMING_PREFIX)]


def _run(tmp_path, faults=frozenset(), runtime=None):
    from so101_demo.ros.dynamic_runtime import run_dynamic_execute
    events = []
    runtime = runtime or _runtime(events, observations=_observations(),
                                  scene=RecordingTaskScenePort(), faults=faults)
    return run_dynamic_execute(_options(tmp_path), _runtime=runtime)


def test_success_emits_exactly_one_phase_timing_line_in_order(tmp_path, capsys):
    assert _run(tmp_path) == 0
    lines = _timing_lines(capsys.readouterr().err)
    assert len(lines) == 1
    assert len(lines[0]) < 8192
    document = json.loads(lines[0][len(TIMING_PREFIX):])
    assert [name for name, _ in document["phases"]] == SUCCESS_PHASES
    stamps = [ns for _, ns in document["phases"]]
    assert stamps == sorted(stamps) and stamps[0] >= 0
    assert document["outcome"] == "ok"


def test_failure_emits_exactly_one_phase_timing_line_with_failure_outcome(tmp_path, capsys):
    assert _run(tmp_path, faults=frozenset({"runner.run"})) == 1
    lines = _timing_lines(capsys.readouterr().err)
    assert len(lines) == 1
    document = json.loads(lines[0][len(TIMING_PREFIX):])
    assert [name for name, _ in document["phases"]] == SUCCESS_PHASES
    assert document["outcome"] != "ok"


def test_early_phase_failure_records_phases_reached_so_far(tmp_path, capsys):
    events = []
    runtime = _runtime(events, observations=_observations(), scene=RecordingTaskScenePort())
    def broken(_node, _template):
        raise RuntimeError("DYNAMIC_TEST_SOURCE_BROKEN: source create failed")
    runtime.cup_pose_source = broken
    assert _run(tmp_path, runtime=runtime) == 1
    lines = _timing_lines(capsys.readouterr().err)
    assert len(lines) == 1
    document = json.loads(lines[0][len(TIMING_PREFIX):])
    assert document["phases"] == []
    assert document["outcome"] != "ok"


def test_timing_emission_never_raises_when_stderr_is_broken(tmp_path, monkeypatch):
    class Broken:
        def write(self, _text):
            raise OSError("stderr closed")
        def flush(self):
            raise OSError("stderr closed")
    monkeypatch.setattr("sys.stderr", Broken())
    assert _run(tmp_path) == 0


def test_census_counts_callbacks_per_subscription_and_is_reported(tmp_path, capsys):
    registered = []
    class CensusNode:
        def create_subscription(self, msg_type, topic, callback, qos_profile, **kwargs):
            registered.append((topic, callback))
            return "sub-" + topic
        def destroy_node(self):
            pass
    events = []
    runtime = _runtime(events, observations=_observations(), scene=RecordingTaskScenePort())
    runtime.rclpy.create_node = lambda _name, *, parameter_overrides: CensusNode()
    original_source = runtime.cup_pose_source
    seen = []
    def source(node, template):
        assert node.create_subscription(object, "/cup_pose", seen.append, 10) == "sub-/cup_pose"
        node.create_subscription(object, "/scene", seen.append, qos_profile=10)
        for topic, callback in registered:
            callback(topic)
            if topic == "/scene":
                callback(topic)
        return original_source(node, template)
    runtime.cup_pose_source = source
    assert _run(tmp_path, runtime=runtime) == 0
    assert seen == ["/cup_pose", "/scene", "/scene"], "callbacks must still be delivered unchanged"
    document = json.loads(_timing_lines(capsys.readouterr().err)[0][len(TIMING_PREFIX):])
    census = document["census"]
    assert census["/cup_pose"]["count"] == 1
    assert census["/scene"]["count"] == 2
    assert isinstance(census["/scene"]["last_receipt_monotonic_ns"], int)


def test_census_install_is_inert_for_nodes_without_subscriptions():
    from so101_demo.ros.dynamic_runtime import _install_callback_census
    assert _install_callback_census(SimpleNamespace()) is None


def _adapter(now, **kwargs):
    from so101_demo.adapters.act.ros_episode_physics import RosEpisodePhysicsAdapter
    node = SimpleNamespace(create_subscription=lambda *args: "owned", destroy_subscription=lambda value: None)
    return RosEpisodePhysicsAdapter(node, session_id="live-source", reset_epoch=2, nq=2, nv=1,
        audit=SimpleNamespace(append_raw_physics=lambda record: None), clock_ns=lambda: now[0], **kwargs)


def _late_lines(err):
    return [json.loads(line[len(LATE_PREFIX):]) for line in err.splitlines() if line.startswith(LATE_PREFIX)]


def test_late_chunks_are_reported_bounded_with_counters_and_unchanged_verification(capsys):
    now = [10_000_000_000]
    adapter = _adapter(now)
    adapter.accept_message(_chunk())
    assert _late_lines(capsys.readouterr().err) == []
    total = 25
    for index in range(total):
        receipt = 10_010_000_000 + index * 10_000_000
        now[0] = receipt + 56_000_000  # newest begin is receipt - 4 ms: 60 ms delay, still fresh
        adapter.accept_message(_chunk(sequence=8 + index, first=106 + index * 5, receipt=receipt))
    assert adapter.hazard is None, "a delay inside max_age must not change verification"
    lines = _late_lines(capsys.readouterr().err)
    assert len(lines) == 20
    first = lines[0]
    assert first["seq"] == 8 and first["delay_ms"] == pytest.approx(60.0)
    assert first["receipt_ns"] == 10_010_000_000 + 56_000_000
    assert first["prev_receipt_ns"] == 10_000_000_000
    assert first["callback_gap_ms"] == pytest.approx(66.0)
    counters = adapter.receipt_diagnostics()
    assert counters["chunk_count"] == total + 1
    assert counters["late_count"] == total
    assert counters["max_delay_ms"] == pytest.approx(60.0)
    assert counters["max_delay_sequence"] == 8


def test_a_very_late_chunk_is_admitted_and_its_delay_is_recorded(capsys):
    """CP-3410: this chunk used to be refused (PHYSICS_RAW_CLOCK_INVALID). It is admitted now; the delay is telemetry."""
    now = [10_000_000_000]
    adapter = _adapter(now)
    adapter.accept_message(_chunk())
    now[0] = 10_010_000_000 + 1_766_000_000
    adapter.accept_message(_chunk(sequence=8, first=106, receipt=10_010_000_000))
    assert adapter.hazard is None
    lines = _late_lines(capsys.readouterr().err)
    assert len(lines) == 1 and lines[0]["seq"] == 8
    assert lines[0]["delay_ms"] == pytest.approx(1770.0)
    counters = adapter.receipt_diagnostics()
    assert counters["last_delay_ms"] == pytest.approx(1770.0)
    assert counters["last_sequence"] == 8
    assert counters["max_delay_sequence"] == 8
    adapter.accept_message(_chunk(sequence=9, first=111, receipt=10_020_000_000))
    assert adapter.receipt_diagnostics()["chunk_count"] == counters["chunk_count"] + 1


def test_diagnostics_never_raise_for_malformed_messages(capsys):
    now = [10_000_000_000]
    adapter = _adapter(now)
    adapter.accept_message(SimpleNamespace(samples=[]))
    assert adapter.hazard is not None
    counters = adapter.receipt_diagnostics()
    assert counters["chunk_count"] == 1
    assert counters["max_delay_ms"] is None and counters["late_count"] == 0


STALL_PREFIX = "DYNAMIC_MAIN_STALL "


def _stall_lines(err):
    return [line for line in err.splitlines() if line.startswith(STALL_PREFIX)]


def _sampling_timer(threshold_ms=100, poll_s=0.01, max_lines=None):
    import threading
    from so101_demo.ros.dynamic_runtime import _PhaseTimer
    timer = _PhaseTimer()
    timer.stall_threshold_ns = threshold_ms * 1_000_000
    timer.stall_poll_s = poll_s
    if max_lines is not None:
        timer.stall_max_lines = max_lines
    timer.start_stall_sampler(threading.get_ident())
    return timer


def test_stall_sampler_prints_one_line_with_main_frames_for_a_blocked_phase(capsys):
    import time
    timer = _sampling_timer(threshold_ms=100)
    timer.mark("phase.begin")
    time.sleep(0.5)
    timer.mark("phase.end")
    timer.emit("ok")
    lines = _stall_lines(capsys.readouterr().err)
    assert len(lines) == 1
    document = json.loads(lines[0][len(STALL_PREFIX):])
    assert document["last_phase"] == "phase.begin"
    assert document["stall_ms"] >= 100
    assert 1 <= len(document["frames"]) <= 15
    assert any("test_dynamic_consumer_starvation_diagnostics.py" in frame for frame in document["frames"])


def test_stall_sampler_is_silent_while_progress_is_continuous(capsys):
    import time
    timer = _sampling_timer(threshold_ms=100)
    for _ in range(20):
        time.sleep(0.02)
        timer.mark("tick")
    timer.emit("ok")
    assert _stall_lines(capsys.readouterr().err) == []


def test_stall_sampler_counts_census_callbacks_as_progress(capsys):
    import time
    timer = _sampling_timer(threshold_ms=100)
    timer.census = {"/t": {"count": 1, "last_receipt_monotonic_ns": None}}
    for _ in range(20):
        time.sleep(0.02)
        timer.census["/t"]["last_receipt_monotonic_ns"] = time.monotonic_ns()
    timer.emit("ok")
    assert _stall_lines(capsys.readouterr().err) == []


def test_stall_sampler_line_limit_holds_and_it_stops_after_emit(capsys):
    import threading
    import time
    timer = _sampling_timer(threshold_ms=20, poll_s=0.005)
    for _ in range(14):
        time.sleep(0.06)
        timer.mark("tick")
    timer.emit("ok")
    lines = _stall_lines(capsys.readouterr().err)
    assert len(lines) == 10
    assert not any(t.name == "dynamic-main-stall-sampler" and t.is_alive() for t in threading.enumerate())
    time.sleep(0.1)
    assert _stall_lines(capsys.readouterr().err) == []
