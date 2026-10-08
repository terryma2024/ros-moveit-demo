"""Actual66 K5/D16: a camera seed that passes validation is awaited by the Recorder, never by the Teacher; log seed refusal facts.

The awaiting capture start moved out of the Teacher child (A4c) into `OfflineRosSources.try_start`."""

import json
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest
from sensor_msgs.msg import Image
from so101_demo.act.episode_assembly import PointEpisode
from so101_demo.act.offline.sources import OfflineRosSources
from so101_demo.act.synchronizer import RgbObservationSynchronizer
from so101_demo.adapters.act.ros_observation import RosObservationAdapter
from test_act_continuous_capture import build

FLOOR = 2.075


def _image(stamp_s):
    image = Image(width=640, height=480, step=1920, encoding="rgb8", data=bytes([37]) * (640 * 480 * 3))
    image.header.stamp.sec = int(stamp_s)
    image.header.stamp.nanosec = round((stamp_s - int(stamp_s)) * 1e9)
    return image


def _adapter(*, sim_now, max_age_s=0.1, max_skew_s=0.1, stamps=None):
    clock = [time.monotonic()]
    capture, _ = build(clock=lambda: clock[0])
    sync = RgbObservationSynchronizer(max_age_s=max_age_s, max_skew_s=max_skew_s, monotonic=lambda: clock[0])
    sim = [sim_now]
    adapter = RosObservationAdapter(SimpleNamespace(create_subscription=lambda *args: object()),
        sync, capture=capture, reset_epoch=3, sim_time=lambda: sim[0])
    adapter.reset("task-5", source_floor_s=0.0, reset_epoch=3)
    for camera, stamp in (stamps or {}).items():
        adapter._image(camera, _image(stamp))
    return adapter, capture, sync, clock, sim


def _refusal_lines(capsys):
    return [line for line in capsys.readouterr().err.splitlines()
            if line.startswith("INPUT_COLLECTION_SEED_REFUSAL ")]


# ---- K5: seed_pair_valid and its parity with _validate_capture_seed ----------------------------

_CASES = {
    "fresh": dict(sim_now=2.3, stamps={"head": 2.25, "wrist": 2.25}, floor=FLOOR, advance=0.0),
    "stale_sim": dict(sim_now=2.3, stamps={"head": 2.1, "wrist": 2.1}, floor=FLOOR, advance=0.0),
    "stale_wall": dict(sim_now=2.3, stamps={"head": 2.25, "wrist": 2.25}, floor=FLOOR, advance=0.101),
    "before_floor": dict(sim_now=2.3, stamps={"head": 2.25, "wrist": 2.25}, floor=2.26, advance=0.0),
    "future_stamp": dict(sim_now=2.3, stamps={"head": 2.25, "wrist": 2.25}, floor=FLOOR, advance=0.0, sim_after=2.2),
    "skew": dict(sim_now=2.3, stamps={"head": 2.21, "wrist": 2.3}, floor=FLOOR, advance=0.0, max_skew_s=0.05),
    "one_camera": dict(sim_now=2.3, stamps={"head": 2.25}, floor=FLOOR, advance=0.0),
}


@pytest.mark.parametrize("name", sorted(_CASES))
def test_seed_pair_valid_matches_capture_seed_pair_verdict(name):
    case = _CASES[name]
    adapter, _, _, clock, sim = _adapter(sim_now=case["sim_now"], stamps=case["stamps"],
        max_skew_s=case.get("max_skew_s", 0.1))
    sim[0] = case.get("sim_after", sim[0])
    clock[0] += case["advance"]
    verdict = adapter.seed_pair_valid(case["floor"])
    try:
        adapter.capture_seed_pair(min_stamp_s=case["floor"])
        validated = True
    except ValueError:
        validated = False
    assert verdict is validated
    assert verdict is (name == "fresh")
    assert not adapter._capture_seed_admitted and set(adapter._pre_capture_frames) == set(case["stamps"])


# ---- K5: the causal seed wait ------------------------------------------------------------------

def _causal(*, sim_now=2.3, stamps, progress=None, max_skew_s=0.1, world_time_s=FLOOR):
    """The Recorder's own start step over a real observation adapter; the world source is at `world_time_s`."""
    adapter, capture, sync, clock, sim = _adapter(sim_now=sim_now, stamps=stamps, max_skew_s=max_skew_s)
    boundaries = []
    capture.audit = SimpleNamespace(inputs={},
        append_collection_boundary=lambda stage, value: boundaries.append((stage, value)))
    now = time.monotonic()
    episode = PointEpisode.__new__(PointEpisode)
    episode.capture, episode._started, episode._start_s = capture, False, 0.0
    episode.synchronizer = sync
    episode.identity = {"session_id": "task-5", "attempt_id": "attempt-1", "reset_epoch": 3, "release_epoch": 0,
        "lease": dict(batch_id="batch", coordinator_epoch=1, worker_id="worker", worker_generation=1,
                      point_id="point", attempt_id="attempt-1", lease_generation=1,
                      lease_issued_monotonic_s=now - 1.0, lease_deadline_monotonic_s=now + 120.0)}
    binding = SimpleNamespace(observer=SimpleNamespace(hazard=None), observation_adapter=adapter)
    sources = OfflineRosSources.__new__(OfflineRosSources)
    sources._initial_built = True
    sources.binding, sources.episode = binding, episode
    record = SimpleNamespace(simulation_time_s=world_time_s, publisher_sequence=7, simulation_session_id="task-5",
                             reset_epoch=3, simulation_step=3)
    sources.world = SimpleNamespace(snapshot=lambda: record,
                                    retained_with_receipts=lambda: (SimpleNamespace(
                                        evidence=record, received_monotonic_s=time.monotonic()),))
    # the verified reset (CP-3425): the Recorder's first retained evidence, on the producer's clock, from its raw step
    sources._raw_lookup = lambda step: {"sample": {"clock_interval_begin_monotonic_ns": time.monotonic_ns() - 3_000_000,
                                                   "clock_interval_end_monotonic_ns": time.monotonic_ns() - 2_000_000}}
    sources.node = SimpleNamespace(get_clock=lambda: SimpleNamespace(
        now=lambda: SimpleNamespace(nanoseconds=2_100_000_000)))
    sources.host = SimpleNamespace(_world_record_cursor=None, retain_epoch_boundary=lambda episode, boundary: None)
    ticks = []

    def step():
        ticks.append(1)
        time.sleep(0.005)
        if progress is not None:
            progress(adapter, ticks)

    return sources, episode, binding, adapter, ticks, step


def _step_once(parts):
    return parts[0].try_start(None)


def _activate(parts, *, passes=400):
    """What the Recorder's engine does: one non-waiting pass per loop until the capture starts or the pass refuses."""
    for _ in range(passes):
        started = _step_once(parts)
        if started is not None:
            return started
        parts[5]()
    return None


def test_seed_wait_skips_stale_backlog_frame_and_activates_on_the_fresh_frame(capsys):
    def progress(adapter, ticks):
        if len(ticks) == 3:
            adapter._image("head", _image(2.25))
            adapter._image("wrist", _image(2.25))

    parts = _causal(stamps={"head": 2.1, "wrist": 2.1}, progress=progress)
    start_s = _activate(parts)
    assert start_s == 2.25
    assert len(parts[4]) == 3, "the wait must continue past the stale frame until the fresh frame"
    assert parts[3]._capture_seed_admitted
    assert _refusal_lines(capsys) == [], "the wait predicate must not print refusal lines"


def test_seed_that_never_becomes_valid_never_starts_the_capture_and_never_raises():
    """The deadline is the engine's (`max_duration_s`, `RECORDER_CAPTURE_NEVER_STARTED`); the step itself only waits."""
    parts = _causal(stamps={"head": 2.0, "wrist": 2.0})
    assert _activate(parts, passes=30) is None
    assert not parts[1].capture.started


def test_hazard_during_the_wait_still_refuses_as_source_lost():
    def progress(adapter, ticks):
        adapter.hazard = "SOURCE_HAZARD"

    parts = _causal(stamps={"head": 2.0, "wrist": 2.0}, progress=progress)
    with pytest.raises(PermissionError, match="RECORDER_CAPTURE_START_SOURCE_LOST"):
        _activate(parts)


def test_frame_that_ages_out_between_the_wait_and_activation_is_still_refused():
    parts = _causal(stamps={"head": 2.25, "wrist": 2.25})
    adapter = parts[3]
    real = adapter.activate_capture

    def activate_after_ageing(**kwargs):
        base = adapter.synchronizer.monotonic
        adapter.synchronizer.monotonic = lambda: base() + 0.101
        return real(**kwargs)

    adapter.activate_capture = activate_after_ageing
    with pytest.raises(ValueError, match="INPUT_COLLECTION_SEED_EXPIRED"):
        _activate(parts)


def test_identity_invalid_pair_ends_the_wait_at_once_and_activation_raises_invalid(capsys):
    parts = _causal(stamps={"head": 2.25, "wrist": 2.25})
    adapter = parts[3]
    frame, pixels = adapter._pre_capture_frames["head"]
    from so101_demo.act.acquisition import canonical_acquisition_id
    adapter._pre_capture_frames["head"] = (replace(frame, session_id="foreign",
        acquisition_id=canonical_acquisition_id("foreign", frame.reset_epoch, "head", frame.sequence)), pixels)
    began = time.monotonic()
    with pytest.raises(ValueError, match="^INPUT_COLLECTION_SEED_INVALID$"):
        _activate(parts)
    assert time.monotonic() - began < 5.0 and len(parts[4]) == 0, "the wait must not spin on an invalid pair"
    assert _refusal_lines(capsys) == []


def test_skew_invalid_pair_ends_the_wait_and_activation_raises_skew_invalid(capsys):
    parts = _causal(stamps={"head": 2.26, "wrist": 2.3}, max_skew_s=0.03)
    with pytest.raises(ValueError, match="^INPUT_COLLECTION_SEED_SKEW_INVALID$"):
        _activate(parts)
    assert len(parts[4]) == 0
    assert [json.loads(line.split(" ", 1)[1])["reason"] for line in _refusal_lines(capsys)] == [
        "INPUT_COLLECTION_SEED_SKEW_INVALID"]


# ---- D16: refusal facts ------------------------------------------------------------------------

def test_expired_seed_logs_exactly_one_refusal_line_and_keeps_the_exception(capsys):
    adapter, *_ = _adapter(sim_now=2.3, stamps={"head": 2.1, "wrist": 2.1})
    with pytest.raises(ValueError, match="^INPUT_COLLECTION_SEED_EXPIRED$"):
        adapter.capture_seed_pair(min_stamp_s=FLOOR)
    (line,) = _refusal_lines(capsys)
    facts = json.loads(line.split(" ", 1)[1])
    assert facts["reason"] == "INPUT_COLLECTION_SEED_EXPIRED"
    assert facts["floor_ns"] == 2_075_000_000 and facts["sim_now_ns"] == 2_300_000_000
    assert facts["age_ns"] == 100_000_000 and facts["max_skew_ns"] == 100_000_000
    assert facts["now_ns"] > 0
    assert set(facts["cameras"]) == {"head", "wrist"}
    for camera in ("head", "wrist"):
        assert facts["cameras"][camera]["stamp_ns"] == 2_100_000_000
        assert facts["cameras"][camera]["received_monotonic_ns"] > 0


def test_skew_seed_logs_exactly_one_refusal_line_and_keeps_the_exception(capsys):
    adapter, *_ = _adapter(sim_now=2.3, stamps={"head": 2.21, "wrist": 2.3}, max_skew_s=0.05)
    with pytest.raises(ValueError, match="^INPUT_COLLECTION_SEED_SKEW_INVALID$"):
        adapter.capture_seed_pair(min_stamp_s=FLOOR)
    (line,) = _refusal_lines(capsys)
    assert json.loads(line.split(" ", 1)[1])["reason"] == "INPUT_COLLECTION_SEED_SKEW_INVALID"


def test_valid_seed_and_predicate_log_nothing(capsys):
    adapter, *_ = _adapter(sim_now=2.3, stamps={"head": 2.25, "wrist": 2.25})
    assert adapter.seed_pair_valid(FLOOR) is True
    adapter.capture_seed_pair(min_stamp_s=FLOOR)
    assert _refusal_lines(capsys) == []


def test_predicate_on_a_refused_seed_logs_nothing(capsys):
    adapter, *_ = _adapter(sim_now=2.3, stamps={"head": 2.1, "wrist": 2.1})
    assert adapter.seed_pair_valid(FLOOR) is False
    assert _refusal_lines(capsys) == []


# ---- K5b: the wait requires activation headroom ------------------------------------------------

def test_seed_wait_skips_a_pair_without_activation_headroom_and_takes_the_next_frame(capsys):
    offset = [0.0]
    sim_offset = [0.0]

    def progress(adapter, ticks):
        if len(ticks) == 2:
            adapter._image("head", _image(2.29))
            adapter._image("wrist", _image(2.29))

    parts = _causal(stamps={"head": 2.205, "wrist": 2.205}, progress=progress)
    adapter = parts[3]
    base_clock, base_sim = adapter.synchronizer.monotonic, adapter.sim_time
    adapter.synchronizer.monotonic = lambda: base_clock() + offset[0]
    adapter.sim_time = lambda: base_sim() + sim_offset[0]
    offset[0] = 0.095
    real = adapter.activate_capture

    def activate_capture(*, min_stamp_s, activate):
        def advancing(start_s):
            offset[0] += 0.010
            sim_offset[0] += 0.010
            return activate(start_s)
        return real(min_stamp_s=min_stamp_s, activate=advancing)

    adapter.activate_capture = activate_capture
    start_s = _activate(parts)
    assert start_s == 2.29, "the wait must skip the 95 ms pair and activate on the fresher frame"
    assert len(parts[4]) == 2 and adapter._capture_seed_admitted
    assert _refusal_lines(capsys) == []


def test_fresh_pair_ends_the_wait_at_once_despite_the_reserve():
    parts = _causal(stamps={"head": 2.29, "wrist": 2.29})
    assert _activate(parts) == 2.29
    assert len(parts[4]) == 0


def test_pair_that_never_gets_headroom_is_waited_for_and_never_started():
    # 95 ms old (sim): valid for the raising validation, but never inside the reserve.
    parts = _causal(stamps={"head": 2.205, "wrist": 2.205})
    assert parts[3].seed_pair_refusal(FLOOR) is None
    assert _activate(parts, passes=30) is None
    assert not parts[1].capture.started


def test_seed_pair_refusal_reserve_applies_to_sim_age_and_wall_age():
    adapter, _, _, clock, _ = _adapter(sim_now=2.3, stamps={"head": 2.205, "wrist": 2.205})
    assert adapter.seed_pair_refusal(FLOOR) is None
    assert adapter.seed_pair_refusal(FLOOR, reserve_s=0.0) is None
    assert adapter.seed_pair_refusal(FLOOR, reserve_s=0.05) == "INPUT_COLLECTION_SEED_EXPIRED"
    assert adapter.seed_pair_refusal(FLOOR, reserve_s=0.004) is None
    adapter, _, _, clock, _ = _adapter(sim_now=2.3, stamps={"head": 2.29, "wrist": 2.29})
    assert adapter.seed_pair_refusal(FLOOR, reserve_s=0.05) is None
    clock[0] += 0.06
    assert adapter.seed_pair_refusal(FLOOR) is None
    assert adapter.seed_pair_refusal(FLOOR, reserve_s=0.05) == "INPUT_COLLECTION_SEED_EXPIRED"


def test_seed_pair_refusal_reserve_keeps_the_other_verdicts(capsys):
    adapter, *_ = _adapter(sim_now=2.3, stamps={"head": 2.26, "wrist": 2.3}, max_skew_s=0.03)
    assert adapter.seed_pair_refusal(FLOOR, reserve_s=0.05) == "INPUT_COLLECTION_SEED_SKEW_INVALID"
    adapter, *_ = _adapter(sim_now=2.3, stamps={"head": 2.29})
    assert adapter.seed_pair_refusal(FLOOR, reserve_s=0.05) == "INPUT_COLLECTION_SEED_UNAVAILABLE"
    assert _refusal_lines(capsys) == []


@pytest.mark.parametrize("reserve", [-0.001, 0.1, 0.2, float("nan"), float("inf"), float("-inf")])
def test_invalid_reserve_is_rejected(reserve):
    adapter, *_ = _adapter(sim_now=2.3, stamps={"head": 2.29, "wrist": 2.29})
    with pytest.raises(ValueError, match="^INPUT_COLLECTION_SEED_RESERVE_INVALID$"):
        adapter.seed_pair_refusal(FLOOR, reserve_s=reserve)


# ---- A4c: the capture start is the Recorder's non-waiting step, never a motion prerequisite -------------------------

def test_one_pass_returns_none_without_waiting_or_progress_while_the_seed_is_not_yet_valid():
    parts = _causal(stamps={"head": 2.0, "wrist": 2.0})
    began = time.monotonic()
    assert _step_once(parts) is None
    assert time.monotonic() - began < 0.05 and parts[4] == [], "a pass must neither sleep nor call progress"
    assert not parts[1].capture.started


def test_one_pass_on_a_fresh_pair_starts_the_capture_once_and_records_the_start():
    parts = _causal(stamps={"head": 2.25, "wrist": 2.25})
    sources, episode = parts[0], parts[1]
    assert _step_once(parts) == 2.25 and episode.capture.started
    assert sources.host._collection_capture_start_clock["sim_time_ns"] == 2_100_000_000
    assert sources.host._world_record_cursor == 6, "world sources are retained from the evidence current at the start"


def test_the_capture_waits_for_the_initial_association_and_never_refuses_for_its_absence():
    """A4b/A4c: the Recorder derives the initial association from the Teacher's own setup scene operations; until it is
    built there is nothing to start from, which is a wait (the engine's max_duration ends it), never a refusal."""
    parts = _causal(stamps={"head": 2.25, "wrist": 2.25})
    sources, episode = parts[0], parts[1]
    sources._initial_built = False
    assert _step_once(parts) is None and _step_once(parts) is None and not episode.capture.started
    sources._initial_built = True
    assert _step_once(parts) == 2.25


def test_no_world_evidence_yet_is_not_ready_and_not_a_refusal():
    parts = _causal(stamps={"head": 2.25, "wrist": 2.25})
    def no_world():
        raise RuntimeError("no world evidence")
    parts[0].world = SimpleNamespace(snapshot=no_world, retained_with_receipts=no_world)
    assert _step_once(parts) is None and not parts[1].capture.started
