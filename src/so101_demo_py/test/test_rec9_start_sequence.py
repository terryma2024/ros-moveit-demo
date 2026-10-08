"""Recorder round 9 (CP-3416): the capture start is deterministic given healthy sources and never depends on Teacher pacing.

L2 on rRQGirke: the Teacher PASSED and the capture never started in 96 s. `start_gate` said why: after the initial association
the seed pair was refused as `seed_expired` on 12605 passes (the pair's stamp had to be >= the NEWEST world record, but a camera
frame is older than the newest world record by its own latency), and the few passes that got through stopped at
`provider_not_ready: physics` (the raw physics sample for the seed stamp arrives with its 100 ms chunk, after the frame). The
`detach` association then failed with RECORDER_SOURCE_ALIGNMENT_TEACHER_EVENT_UNAVAILABLE at job age 0.07 s: the same chunk lag, never retried.
See rec9-start-sequence.md.

Layer A drives the real `RosRecorderSources.try_start` over a seeded model of every source at its real rate.
Layer B drives the real engine, capture, writer, seal and readback with seeded orderings of the Teacher's reset and start
observation against the capture start.
"""
import random
import time
from types import SimpleNamespace

import pytest

from so101_demo.act.episode_assembly import PointEpisode
from so101_demo.act.episode_recorder_process import RC_VALID
from so101_demo.act.synchronizer import RgbObservationSynchronizer
from so101_demo.adapters.act.ros_observation import RosObservationAdapter
from so101_demo.ros.episode_recorder_sources import RosRecorderSources
from test_act_capture_seed_validity import _image
from test_act_continuous_capture import build
from test_act_episode_recorder import STAMPS, readback, result_of, teacher_script
from test_rec2_stall_replay import RealTimeSources, SIM0, run_replay

SEEDS = range(24)
BASE = 10.0   # simulation seconds at the model's t = 0


# ---- layer A: the real start gate over a seeded real-rate model -----------------------------------------------------------

class Model:
    """Every source of the start gate at its real rate, jitter and occasional spikes, from one seed. Times are integer ms."""

    def __init__(self, seed, *, horizon_ms=6000):
        rng = random.Random(seed)
        self.rng = rng
        self.alignment_ms = rng.randint(200, 4000)               # the initial association is built (Teacher's setup scene)
        self.frames = {"head": [], "wrist": []}           # (arrival ms, stamp ms)
        for camera in self.frames:
            stamp = rng.randint(0, 33)
            while stamp < horizon_ms:
                self.frames[camera].append((stamp + rng.randint(2, 25), stamp))
                stamp += 33 + rng.randint(-1, 1)
        self.worlds = []                                  # (arrival ms, stamp ms, publisher sequence)
        for index, stamp in enumerate(range(rng.randint(0, 11), horizon_ms, 12), start=1):
            self.worlds.append((stamp + rng.randint(0, 3), stamp, index))
        self.chunks = []                                  # (arrival ms, newest sample stamp ms)
        for stamp in range(100, horizon_ms, 100):
            late = rng.randint(30, 150) if rng.random() < 0.2 else rng.randint(0, 30)
            self.chunks.append((stamp + late, stamp))
        self.planning = [(stamp + rng.randint(1, 35), stamp) for stamp in range(rng.randint(0, 49), horizon_ms, 50)]
        self.controller = [(stamp + rng.randint(0, 5), stamp) for stamp in range(0, horizon_ms, 20)]
        self.stalls = {}
        at = 0
        while at < horizon_ms:
            at += rng.randint(5, 9)
            self.stalls[at] = rng.randint(50, 200) if rng.random() < 0.03 else 0
        self.raw_ms = -1

    def arrived(self, table, now_ms, stamp_index=1):
        return [row[stamp_index] for row in table if row[0] <= now_ms]


def sim_s(ms):
    return BASE + ms / 1000.0


def start_gate_run(seed, *, max_age_s=0.2):
    model = Model(seed)
    clock, sim = [time.monotonic()], [BASE]
    capture, _ = build(clock=lambda: clock[0])
    sync = RgbObservationSynchronizer(max_age_s=max_age_s, max_skew_s=0.1, monotonic=lambda: clock[0])
    adapter = RosObservationAdapter(SimpleNamespace(create_subscription=lambda *args: object()), sync, capture=capture,
                                    reset_epoch=3, sim_time=lambda: sim[0])
    adapter.reset("task-5", source_floor_s=0.0, reset_epoch=3)
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
    sources = RosRecorderSources.__new__(RosRecorderSources)
    sources._initial_built = False
    sources.binding = SimpleNamespace(observer=SimpleNamespace(hazard=None), observation_adapter=adapter)
    sources.episode = episode
    state = {"now": 0}

    def worlds():
        return tuple(SimpleNamespace(
            evidence=SimpleNamespace(simulation_time_s=sim_s(stamp), publisher_sequence=sequence,
                                     simulation_session_id="task-5", reset_epoch=3, simulation_step=sequence),
            received_monotonic_s=clock[0])
                     for arrival, stamp, sequence in model.worlds if arrival <= state["now"])

    sources.world = SimpleNamespace(retained_with_receipts=worlds)
    sources.node = SimpleNamespace(get_clock=lambda: SimpleNamespace(
        now=lambda: SimpleNamespace(nanoseconds=round(sim[0] * 1e9))))
    sources.host = SimpleNamespace(_world_record_cursor=None, retain_epoch_boundary=lambda episode, boundary: None)
    sources._raw_lookup = lambda step: {"sample": {"clock_interval_begin_monotonic_ns": round(clock[0] * 1e9) - 3_000_000,
                                                   "clock_interval_end_monotonic_ns": round(clock[0] * 1e9) - 2_000_000}}

    def raw_newest():
        stamps = model.arrived(model.chunks, state["now"])
        return None if not stamps else sim_s(max(stamps))

    def within(table, at_s):
        return any(0 <= at_s - sim_s(stamp) <= 0.1 for stamp in model.arrived(table, state["now"]))

    def cause(at_s):
        newest = raw_newest()
        if newest is None or newest < at_s:
            return "physics"
        return None if within(model.planning, at_s) and within(model.controller, at_s) else (
            "planning_scene" if not within(model.planning, at_s) else "controller_state")

    sources._provider = SimpleNamespace(
        ready=lambda at_s: cause(at_s) is None, unready_cause=cause,
        awaiting_arrival=lambda at_s: raw_newest() is None or raw_newest() < at_s)
    started_ms, started_s, cursor_at_start = None, None, None
    delivered = {camera: 0 for camera in model.frames}
    next_pass = 0
    for ms in range(0, 6000):
        state["now"] = ms
        clock[0] = time.monotonic() + ms / 1000.0
        sim[0] = sim_s(ms)
        for camera, table in model.frames.items():
            while delivered[camera] < len(table) and table[delivered[camera]][0] <= ms:
                arrival, stamp = table[delivered[camera]]
                delivered[camera] += 1
                adapter._image(camera, _image(sim_s(stamp)))
        if ms == model.alignment_ms:
            sources._initial_built = True
        if ms >= next_pass:
            next_pass = ms + model.stalls.get(ms, 0) + 7
            started = sources.try_start(None)
            if started is not None:
                started_ms, started_s, cursor_at_start = ms, started, sources.host._world_record_cursor
                break
    return model, started_ms, started_s, cursor_at_start, sources, model


@pytest.mark.parametrize("seed", SEEDS)
def test_the_real_start_gate_starts_every_healthy_ordering_within_a_bounded_time_of_the_initial_association(seed):
    model, started_ms, started_s, cursor, sources, _ = start_gate_run(seed)
    assert started_ms is not None, ("the capture never started", sources._start_gate)
    # the first instant every source can exist: the first pair after the initial association and the first chunk after it
    assert started_ms - max(model.alignment_ms, 300) <= 700, (started_ms, model.alignment_ms, sources._start_gate)
    # the retained world evidence begins at the predecessor of the seed stamp: never after it
    predecessor = [stamp for _, stamp, sequence in model.worlds if sequence == cursor + 1][0]
    assert sim_s(predecessor) <= started_s and started_s - sim_s(predecessor) < 0.15
    assert "initial_association_not_built" in sources._start_gate or model.alignment_ms == 0


def test_the_seed_stamp_is_often_older_than_the_newest_world_record_and_the_capture_still_starts():
    """The L2 refusal: a pair older than the newest world record started nothing (seed_expired on every pass)."""
    older = 0
    for seed in SEEDS:
        model, started_ms, started_s, cursor, sources, _ = start_gate_run(seed)
        newest = max(stamp for arrival, stamp, _ in model.worlds if arrival <= started_ms)
        older += started_s < sim_s(newest)
    assert older >= len(SEEDS) // 2, older


def test_a_physics_sample_still_in_flight_does_not_close_the_gate_and_is_counted():
    model, started_ms, started_s, cursor, sources, _ = start_gate_run(5)
    assert started_ms is not None
    gate = sources._start_gate
    assert gate["started"]["passes"] == 1
    assert set(gate) <= {"initial_association_not_built", "seed_unavailable", "seed_expired", "provider_not_ready",
                         "physics_in_flight", "world_snapshot_missing", "world_history_starts_after_seed", "started"}


def test_a_source_other_than_physics_that_is_not_causal_still_closes_the_gate():
    from test_act_capture_seed_validity import _causal, _step_once
    parts = _causal(sim_now=2.3, stamps={"head": 2.25, "wrist": 2.25})
    parts[0]._provider = SimpleNamespace(ready=lambda at_s: False, unready_cause=lambda at_s: "controller_state",
                                         awaiting_arrival=lambda at_s: True)
    assert _step_once(parts) is None and parts[0]._start_gate["provider_not_ready"]["facts"]["source"] == "controller_state"


# ---- the source alignment association whose source arrives with its chunk ---------------------------------------------------------------

def test_a_teacher_named_association_source_that_has_not_arrived_is_retried_then_invalid():
    from so101_demo.act.recorder_scene import SceneAssociationError
    sources = RosRecorderSources.__new__(RosRecorderSources)
    sources.ALIGNMENT_RETRY_S = 1.0
    sources._jobs = [SimpleNamespace(created_monotonic_s=time.monotonic(), operation="detach", apply=None, query=None)]
    sources._admissions, sources._initial_built = [], True
    calls = []

    def build_job(job):
        calls.append(1)
        if len(calls) < 3:
            raise SceneAssociationError("RECORDER_SOURCE_ALIGNMENT_TEACHER_EVENT_UNAVAILABLE")

    sources._build_job = build_job
    sources._retain_alignment_inputs = lambda job, error: None
    for _ in range(4):
        sources._service_associations(SimpleNamespace(telemetry=None))
    assert len(calls) == 3 and sources._jobs == [], "retried while the source may still arrive, then built"
    sources._jobs = [SimpleNamespace(created_monotonic_s=time.monotonic() - 5.0, operation="detach", apply=None, query=None)]
    sources._build_job = lambda job: (_ for _ in ()).throw(SceneAssociationError("RECORDER_SOURCE_ALIGNMENT_TEACHER_EVENT_UNAVAILABLE"))
    with pytest.raises(SceneAssociationError, match="TEACHER_EVENT_UNAVAILABLE"):
        sources._service_associations(SimpleNamespace(telemetry=None))


# ---- layer B: seeded orderings of Recorder-ready, the Teacher's reset and start observation, against the capture start -------

class OrderedSources(RealTimeSources):
    """The Teacher's reset and start observation reach the Recorder at seeded instants: before the capture starts or after it."""

    def __init__(self, box, script, early, *, hold_s, **kwargs):
        super().__init__(box, script, **kwargs)
        self.early = sorted(early)               # (wall seconds since prepare, text)
        self.hold_s = hold_s                     # the capture-start gate stays closed until then (source alignment, raw lag, loop stalls)
        self.order = []

    def pump(self, engine):
        while self.early and time.monotonic() - self.t0 >= self.early[0][0]:
            self.order.append("started" if engine.episode.capture.started else "before_start")
            engine.on_event_text(self.early.pop(0)[1])
        super().pump(engine)

    def try_start(self, engine):
        if time.monotonic() - self.t0 < self.hold_s:
            return None
        return super().try_start(engine)


def ordered_replay(tmp_path, seed):
    rng = random.Random(1000 + seed)
    reset_sim = round(rng.uniform(0.3, 0.95), 3)
    script = teacher_script(reset_sim_s=reset_sim, reset_tick=-1)
    reset_text = script.pop(-1)[0]
    start_obs_text = script[0].pop(0)
    start_wall = STAMPS[0] - SIM0                       # the seed pair's own instant, in replay wall seconds (0.85 s)
    reset_wall = max(0.05, reset_sim - SIM0 + rng.uniform(0.0, 0.2))
    observation_wall = max(reset_wall + 0.001, start_wall + rng.uniform(-0.04, 0.09))   # emitted at sim >= the seed stamp
    hold_s = rng.uniform(0.0, 0.05) + start_wall        # source alignment built / loop stalled: the gate may open later than the instant
    return run_replay(tmp_path, served_by_receiver=True, script=script, sources_cls=OrderedSources,
                      early=[(reset_wall, reset_text), (observation_wall, start_obs_text)], hold_s=hold_s)


def run_ordering(tmp_path, seed):
    """One wall-clock replay. A run whose own loop was stalled by the host (a pass of 100 ms or more in its telemetry) is a
    loaded-machine run, not an ordering: it is repeated (at most three times) in a fresh directory; any other failure counts."""
    import json
    for attempt in range(3):
        root = tmp_path / f"attempt{attempt}"
        root.mkdir()
        engine, sources, working = ordered_replay(root, seed)
        code = engine.run()
        result = result_of(working)
        if code == RC_VALID:
            return code, result, sources, working
        telemetry = json.loads((working / "episode" / "recorder-telemetry.json").read_text())
        if telemetry["passes"]["max_ms"] < 100.0:
            break
    return code, result, sources, working


@pytest.mark.parametrize("seed", SEEDS)
def test_every_healthy_ordering_of_reset_and_start_observation_against_the_capture_start_seals_valid(tmp_path, seed):
    code, result, sources, working = run_ordering(tmp_path, seed)
    assert code == RC_VALID and result["status"] == "VALID", (sources.order, result["reasons"])
    seal, manifest, references = readback(working)
    assert seal["status"] == "PASSED" and references["status"] == "PASS"
    # an event offered before the start may still be handled in the pass that starts the capture (then it is not held)
    assert result["event_stream"]["deferred_replayed"] <= sources.order.count("before_start"), sources.order


def test_the_orderings_cover_both_sides_of_the_start_for_the_start_observation(tmp_path):
    seen = set()
    for seed in SEEDS:
        rng = random.Random(1000 + seed)
        reset_sim = round(rng.uniform(0.3, 0.95), 3)
        reset_wall = max(0.05, reset_sim - SIM0 + rng.uniform(0.0, 0.2))
        start_wall = STAMPS[0] - SIM0
        observation_wall = max(reset_wall + 0.001, start_wall + rng.uniform(-0.04, 0.09))
        hold = rng.uniform(0.0, 0.05) + start_wall
        seen.add(observation_wall < hold)
    assert seen == {True, False}


def test_a_capture_that_never_starts_names_the_gate_outcomes_in_its_reason(tmp_path):
    from test_act_episode_recorder import build
    from so101_demo.act.episode_recorder_process import RC_INVALID
    script = teacher_script(reset_sim_s=1.0, reset_tick=-1)
    engine, sources, working = build(tmp_path, script=script)
    for tick in list(script):
        for text in script.pop(tick):
            engine.on_event_text(text)
    sources.try_start = lambda engine_: None
    sources.start_gate_summary = lambda engine_: {"seed_expired": 12605, "provider_not_ready": 41}
    ticks = iter(range(0, 10_000))
    engine.clock = lambda: next(ticks) * 1.0
    assert engine.run() == RC_INVALID
    entry = [item for item in result_of(working)["reasons"] if "NOT_READY" in item["reason"]][0]
    assert '"seed_expired": 12605' in entry["start_gate"]


def test_the_start_gate_summary_counts_passes_by_cause():
    sources = RosRecorderSources.__new__(RosRecorderSources)
    for _ in range(3):
        sources._gate("seed_expired")
    sources._gate("started")
    assert sources.start_gate_summary(None) == {"seed_expired": 3, "started": 1}
