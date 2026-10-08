"""Recorder round 2 (CP-3403), item 3: a synthetic replay at real rates with an injected 160 ms main-thread stall.

The Teacher script, the real PointEpisode (lossless writer, audit, seal, readback), the real physics adapter and the real
engine are the ones `test_act_episode_recorder` uses. What changes is WHO delivers the sources and WHEN:

* `served_by_receiver=True` (the design): the camera, numeric, chunk, planning-read and controller sources are delivered by
  their own threads at wall-clock rate and stamped at delivery, as the receiver thread, the scene poller and the chunk
  spooler do. The loop only drains and mints. A 160 ms busy pass of the loop (pure Python, GIL-contending) is injected while
  the capture runs. The recording must seal VALID.
* `served_by_receiver=False` (the control, the L2 behaviour): the same sources are produced at the same rate but delivered and
  stamped by the loop's own pass, so the stall ages them. The recording must be INVALID.

Honest limit: this proves the engine, capture, adapter and seal tolerate a stalled loop when sources are stamped outside it. That
the production receiver, poller and spooler do so is proved by `test_rec2_receiver` and `test_rec_chunk_spool` (a real rclpy node and
a real spooler process); the full stack needs the live run.
"""
import threading
import time
from types import SimpleNamespace

import pytest

from so101_demo.act.episode_recorder_process import RC_INVALID, RC_VALID, RecorderEngine, load_recorder_policy
from test_act_episode_recorder import (FRAME, NODE, POLICY_FILE, STAMPS, STREAM_IDENTITY, SyntheticSources,
                                       make_episode, readback, result_of, teacher_script)
from test_act_episode_recorder import PointEpisode, IDENTITY, SCOPE, PROVENANCE, episode_audit_pair
from test_act_seal_and_downgrade import recorder_physical_audit

SIM0 = 0.15          # simulated clock at the replay's start
PRE = tuple(round(0.2 + 0.1 * index, 1) for index in range(8))        # chunks before the first row: the pre-window stream (CP-3409)
CHUNK_STAMPS = PRE + tuple(STAMPS)
STEP_NS = 2_000_000


def busy(seconds):
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        sum(range(200))


class ReadyAudit:
    """The physical half with the real provider's readiness semantics: every source within 100 ms BEFORE the instant."""

    def __init__(self, owner):
        self.owner = owner

    def ready(self, at_s):
        owner, at_ns = self.owner, round(at_s * 1e9)
        with owner.lock:
            reads = any(0 <= at_ns - stamp <= 100_000_000 for stamp in owner.reads)
            controller = any(0 <= at_ns - stamp <= 100_000_000 for stamp in owner.controller)
        return reads and controller and owner.adapter.source_at(at_s) is not None

    def awaiting_arrival(self, at_s):
        """What the live provider reports: the newest physics sample received is older than this instant (in flight)."""
        newest = self.owner.adapter.latest_sample_time_s()
        return newest is not None and newest < at_s

    def __call__(self, at_s):
        if not self.ready(at_s):
            raise ValueError("LIVE_PHYSICAL_SOURCE_UNAVAILABLE")
        # exactly the thirteen values the live provider hands the capture through `PhysicalAuditAdapter` (CP-3407: the
        # earlier replay used the test audit, which also carried session_id and attempt_id, and hid the L2 failure)
        from so101_demo.act.episode_assembly import PhysicalAuditAdapter
        full = recorder_physical_audit(at_s)
        row = {key: full[key] for key in PhysicalAuditAdapter.KEYS}
        # the live controller record embeds the original /joint_states message, NaN effort included (CP-3412): the row must carry it
        from rosidl_runtime_py.convert import message_to_ordereddict
        from so101_demo.act.nonfinite import json_safe
        from sensor_msgs.msg import JointState
        message = JointState()
        message.name, message.position, message.velocity, message.effort = ["1"], [0.1], [0.0], [float("nan")]
        row["controller_state"] = {"stopped": False, "original_message": json_safe(message_to_ordereddict(message))}
        return row


class RealTimeSources(SyntheticSources):
    def __init__(self, box, script, *, served_by_receiver, stall_at_s=1.15, stall_s=0.16, chunk_stall=None, drop_chunk=None):
        super().__init__(box, script)
        self.served_by_receiver = served_by_receiver
        self.drop_chunk = drop_chunk
        self.chunk_stall = chunk_stall      # (chunk index, seconds): the spooler/producer stalls before this chunk is delivered
        self.stall_at_s, self.stall_s, self.stalled = stall_at_s, stall_s, False
        self.lock = threading.Lock()
        self.reads, self.controller, self.queue = [], [], []
        self.t0 = None
        self.stop = threading.Event()
        self.thread = None
        self.audit = ReadyAudit(self)
        self.delivered_ticks = 0
        self.feeder_error = None
        self.physics_done = set()

    # -- the clock of the replay
    def sim_now(self):
        return SIM0 + (time.monotonic() - self.t0)

    def step_begin_ns(self, step):
        return self.t0_ns + round((step * 0.002 - SIM0) * 1e9)

    # -- production of each source's data
    def make_chunk(self, index):
        from so101_mujoco_support.msg import PhysicsStepEvidence, PhysicsStepEvidenceChunk
        stamp = CHUNK_STAMPS[index]
        last = round(stamp / 0.002)
        first = last - 49
        samples = []
        for offset in range(50):
            step = first + offset
            begin = self.step_begin_ns(step)
            sample = PhysicsStepEvidence(
                simulation_session_id="session-1", reset_epoch=2, physics_step=step, simulation_time_s=step * 0.002,
                clock_interval_begin_monotonic_ns=begin, clock_interval_end_monotonic_ns=begin + 1_800_000,
                model_qpos=[.1, .2], model_qvel=[.3], has_contact=False, maximum_normal_force_n=0.,
                total_normal_force_n=0., global_max_single_contact_force_n=0.)
            sample.object_pose_world.orientation.w = 1.
            samples.append(sample)
        return PhysicsStepEvidenceChunk(
            chunk_sequence=index + 1, simulation_session_id="session-1", reset_epoch=2, first_physics_step=first,
            last_physics_step=last, first_simulation_time_s=samples[0].simulation_time_s,
            last_simulation_time_s=samples[-1].simulation_time_s, samples=samples)

    def prepare(self, engine):
        from so101_demo.adapters.act.ros_episode_physics import RosEpisodePhysicsAdapter
        self.t0, self.t0_ns = time.monotonic(), time.monotonic_ns()
        self.adapter = RosEpisodePhysicsAdapter(NODE, session_id="session-1", reset_epoch=2, nq=2, nv=1,
                                                audit=engine.episode.capture.audit, clock_ns=time.monotonic_ns,
                                                history_capacity=4096)
        self.thread = threading.Thread(target=self.feeder, args=(engine,), daemon=True)
        self.thread.start()

    def due(self, stamp):
        return self.sim_now() >= stamp

    def feeder(self, engine):
        """Stands in for the receiver thread, the scene poller and the chunk spooler: deliver at the rate, stamp at delivery."""
        next_read, next_ctrl, tick, rest = SIM0, SIM0, 0, 0
        self.stall_until = None
        while not self.stop.is_set():
            now = self.sim_now()
            if self.served_by_receiver:
                while next_read <= now:
                    with self.lock:
                        self.reads.append(round(next_read * 1e9))
                    next_read += 0.05
                while next_ctrl <= now:
                    with self.lock:
                        self.controller.append(round(next_ctrl * 1e9))
                    next_ctrl += 0.02
            if not self.served_by_receiver:
                while tick < len(CHUNK_STAMPS) and now >= CHUNK_STAMPS[tick] + 0.005:
                    with self.lock:
                        self.queue.append((tick, self.make_chunk(tick)))     # the old design: the loop delivers and stamps
                    tick += 1
            else:
                # The chunk track and the rest track (frames, numerics, Teacher events) are independent, as the sources are: a
                # stalled spooler delays chunks only, the cameras, the controller and the planning reads keep flowing.
                while tick < len(CHUNK_STAMPS) and now >= CHUNK_STAMPS[tick] + 0.005:
                    if self.chunk_stall is not None and self.chunk_stall[0] == tick and self.stall_until is None:
                        self.stall_until = now + self.chunk_stall[1]
                    if self.stall_until is not None and now < self.stall_until:
                        break                                              # held: this and every later chunk arrive late
                    if self.stall_until is not None:
                        self.stall_until, self.chunk_stall = None, None
                    if self.drop_chunk != tick:                            # a dropped chunk never reaches the Recorder
                        try:
                            self.deliver_physics((tick, self.make_chunk(tick)))
                        except Exception as error:
                            self.feeder_error = repr(error)
                    tick += 1
                while (rest < len(STAMPS) and now >= STAMPS[rest] + 0.005 and engine.episode.capture.started):
                    try:
                        self.deliver_rest(engine, (len(PRE) + rest, None))
                    except Exception as error:      # the capture refused: the engine's verdict says why
                        self.feeder_error = repr(error)
                    rest += 1
            time.sleep(0.002)

    def deliver_physics(self, item):
        self.adapter.accept_message(item[1])

    def deliver_rest(self, engine, item):
        if item[0] < len(PRE):
            return                                              # a pre-roll chunk carries no frames, numerics or events
        tick = item[0] - len(PRE)
        stamp = STAMPS[tick]
        for camera in ("head", "wrist"):
            engine.episode.push(camera, stamp_s=stamp, pixels=FRAME)
        engine.episode.push_numeric(stamp_s=stamp, arm=[0.0] * 6, neck=0.0)
        self.counts["head"] += 1
        self.counts["wrist"] += 1
        self.counts["physics"] = item[0] + 1
        for name in ("scene_state", "world", "joint_states"):
            self.counts[name] += 1
        for text in self.script.get(tick, ()):
            engine.on_event_text(text)
        self.delivered_ticks = tick + 1

    def deliver(self, engine, item):
        """The receiver's side: stamp at delivery; frames wait (in the receiver) for the capture to start."""
        self.deliver_physics(item)
        while item[0] >= len(PRE) and not engine.episode.capture.started and not self.stop.is_set():
            time.sleep(0.002)
        self.deliver_rest(engine, item)

    # -- the loop's side
    def try_start(self, engine):
        if not self.audit.ready(STAMPS[0]):
            return None
        engine.episode.start(STAMPS[0])
        return STAMPS[0]

    def pump(self, engine):
        if not self.served_by_receiver:                      # the old design: the loop is the one that reads and stamps
            now = self.sim_now()
            with self.lock:
                self.reads.append(round(now * 1e9))
                self.controller.append(round(now * 1e9))
                items, self.queue = self.queue, []
            held = []
            for item in items:
                if item[0] not in self.physics_done:
                    self.deliver_physics(item)        # stamped by the loop, now
                    self.physics_done.add(item[0])
                if engine.episode.capture.started:
                    self.deliver_rest(engine, item)
                else:
                    held.append(item)
            with self.lock:
                self.queue = held + self.queue
        if (not self.stalled and engine.episode.capture.started and self.sim_now() >= self.stall_at_s):
            self.stalled = True
            busy(self.stall_s)                                # the injected 160 ms pass
        try:
            self.adapter.drain()
        except ValueError as error:
            raise error

    def collect(self, engine):
        capture = engine.episode.capture
        for when in capture.reference_requests(min(self.sim_now(), STAMPS[-1])):
            capture.on_reference({"source": "CONTROLLER_REFERENCE", "requested_sim_time_s": round(when, 6),
                                  "positions": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6], "accepted": True})
        capture.drain()

    def tail_ready(self, engine):
        # the raw chunks of the end observation are part of the recording: a late chunk is waited for (the real tail waits for the
        # final world source's raw step, bounded by the receiver-lag policy)
        newest = self.adapter.latest_sample_time_s()
        return (self.delivered_ticks >= len(STAMPS) and newest is not None and newest >= STAMPS[-1] - 0.005
                and self.adapter.history_summary()["pending"] == 0)

    def close(self):
        self.stop.set()
        if self.thread is not None:
            self.thread.join(2.0)
        super().close()


def run_replay(tmp_path, *, served_by_receiver, chunk_stall=None, drop_chunk=None, script=None, sources_cls=None,
               **sources_kwargs):
    working = tmp_path / "working"
    working.mkdir()
    box = {}
    sources = (sources_cls or RealTimeSources)(
        box, teacher_script() if script is None else script, served_by_receiver=served_by_receiver,
        chunk_stall=chunk_stall, drop_chunk=drop_chunk, **sources_kwargs)
    # the live path's recorder: the lossless queue with its writer thread and watermarks, frozen policy of the collection config
    from so101_demo.act.collection_config import validate_recorder_policy
    recorder_policy = validate_recorder_policy({"sample_rate_hz": 10, "queue_capacity_samples": 16,
                                                "queue_high_watermark_samples": 12, "queue_recovery_watermark_samples": 8,
                                                "queue_high_watermark_hold_s": 0.2, "lossless": True})
    episode = PointEpisode(identity=IDENTITY, provenance=PROVENANCE, inputs={"inputs_sha256": "a" * 64},
                           episode_root=working / "episode", scope=SCOPE,
                           scope_path=str(episode_audit_pair(working / "episode")[1]),
                           physical_audit=sources.audit, monotonic=time.monotonic, recorder_policy=recorder_policy)
    policy = dict(load_recorder_policy(POLICY_FILE), poll_s=0.002, max_duration_s=5.0, finish_budget_s=2.0)
    engine = RecorderEngine(episode=episode, sources=sources, policy=policy, identity=STREAM_IDENTITY,
                            ready_file=working / "recorder-ready.json", result_file=working / "recorder-result.json")
    box["engine"] = engine
    return engine, sources, working


def test_a_160_ms_stalled_loop_still_seals_valid_when_the_sources_are_stamped_outside_it(tmp_path):
    engine, sources, working = run_replay(tmp_path, served_by_receiver=True)
    code = engine.run()
    result = result_of(working)
    assert sources.stalled, "the capture ran and the stall was injected"
    assert code == RC_VALID and result["status"] == "VALID", result["reasons"]
    seal, manifest, references = readback(working)
    assert seal["status"] == "PASSED" and seal["record_count"] >= 2 and references["status"] == "PASS"
    telemetry = __import__("json").loads((working / "episode" / "recorder-telemetry.json").read_text())
    assert telemetry["passes"]["max_ms"] >= 150.0 and telemetry["stalls"], "the stall is in the telemetry"


def test_control_the_same_stall_with_the_loop_serving_the_sources_is_invalid(tmp_path):
    engine, sources, working = run_replay(tmp_path, served_by_receiver=False)
    code = engine.run()
    result = result_of(working)
    assert code == RC_INVALID and result["status"] == "INVALID"
    assert any(("INPUT_STALE" in item["reason"] or "CLOCK_INVALID" in item["reason"] or "NO_NEW" in item["reason"]
                or "SOURCE" in item["reason"]) for item in result["reasons"]), result["reasons"]


FRESH_READBACK = """
import json, sys
from pathlib import Path
from so101_demo.act import episode_qc
from so101_demo.act.episode_assembly import episode_audit_pair
from so101_demo.act.episode_audit import verify_audit_manifest
from so101_demo.act.recorder import verify_episode_seal
root = Path(sys.argv[1]) / "episode"
audit_manifest, scope = episode_audit_pair(root)
seal = verify_episode_seal(root / "seal.json", audit_manifest=audit_manifest, scope=scope)
manifest = verify_audit_manifest(audit_manifest)
from so101_demo.act.nonfinite import restore_non_finite
rows = [json.loads(line) for line in (root / "records.jsonl").read_text().splitlines()]
efforts = [restore_non_finite(row["audit"]["controller_state"]["original_message"])["effort"][0] for row in rows]
print(json.dumps({"status": seal["status"], "records": seal["record_count"], "window": manifest["window"],
                  "nan_efforts_restored": sum(1 for value in efforts if value != value)}))
"""


def test_the_replayed_recording_reads_back_in_a_fresh_process(tmp_path):
    """The seal, the audit manifest and the frames verify in a process that shares nothing with the Recorder (QC path)."""
    import json
    import subprocess
    import sys
    engine, sources, working = run_replay(tmp_path, served_by_receiver=True)
    assert engine.run() == RC_VALID
    done = subprocess.run([sys.executable, "-c", FRESH_READBACK, str(working)], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-800:]
    report = json.loads(done.stdout.strip().splitlines()[-1])
    assert report["status"] == "PASSED" and report["records"] >= 2
    assert report["nan_efforts_restored"] == report["records"], "every row's original joint state survived with its NaN"
    assert len(list((working / "episode" / "frames").glob("*-head.png"))) == report["records"]


def test_a_400_ms_spooler_stall_is_a_valid_recording_wherever_it_falls(tmp_path):
    """CP-3410: a late chunk no longer fails the data. A 400 ms stall before the first row and one inside the recording
    (the L2 case 283 ms and worse) both seal VALID; the lateness is in the receiver's telemetry."""
    for position in (3, len(PRE) + 2):
        sub = tmp_path / f"stall-{position}"
        sub.mkdir()
        engine, sources, working = run_replay(sub, served_by_receiver=True, chunk_stall=(position, 0.4))
        code = engine.run()
        result = result_of(working)
        assert code == RC_VALID and result["status"] == "VALID", (position, result["reasons"])
        diagnostics = sources.adapter.receipt_diagnostics()
        assert diagnostics["late_count"] >= 1 and diagnostics["max_delay_ms"] >= 300.0
        seal, manifest, references = readback(working)
        assert seal["status"] == "PASSED" and references["status"] == "PASS"


def test_a_dropped_chunk_is_still_an_invalid_recording(tmp_path):
    """Continuity is unchanged: one chunk that never arrives fails the data wherever it falls."""
    engine, sources, working = run_replay(tmp_path, served_by_receiver=True, drop_chunk=len(PRE) + 2)
    code = engine.run()
    result = result_of(working)
    assert code == RC_INVALID and any("PHYSICS_RAW_CONTINUITY_INVALID" in item["reason"] for item in result["reasons"]), \
        result["reasons"]
