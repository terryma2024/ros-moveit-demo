"""Approved sample queue bounds and actual lossless Recorder readback."""

import threading

import pytest

from audited_episode import audit_of
from test_act_recorder import PROVENANCE, audit, observation, outcome

POLICY = {"sample_rate_hz": 10, "queue_capacity_samples": 16,
          "queue_high_watermark_samples": 12, "queue_recovery_watermark_samples": 8,
          "queue_high_watermark_hold_s": .2, "lossless": True}


def test_real_recorder_flushes_copied_original_pixels_before_sealing(tmp_path):
    import numpy as np
    from so101_demo.act.lossless_recorder import LosslessRecorderQueue
    from so101_demo.act.recorder import EpisodeRecorder, verify_episode_seal
    from PIL import Image
    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1", attempt_id="attempt-1",
                               reset_epoch=2, provenance=PROVENANCE)
    queue = LosslessRecorderQueue(recorder, policy=POLICY)
    try:
        for t in (1., 1.1, 1.2):
            value = observation(t)
            expected = value["head"].copy()
            queue.append(value, (0.,) * 6, audit(t))
            value["head"][:] = 99  # producer may reuse its own buffer after accepted ingress
        queue.flush()
        manifest, scope = audit_of(recorder, tmp_path)
        seal = queue.finish(outcome(), audit_manifest=manifest, scope=scope)
        verified = verify_episode_seal(seal, audit_manifest=manifest, scope=scope)
        assert verified["record_count"] == 3
        from so101_demo.act.lossless_recorder import verify_queue_evidence
        verify_queue_evidence(queue.snapshot())
        assert queue.snapshot()["written_samples"] == 3
        assert queue.snapshot()["dropped_samples"] == 0
        with Image.open(recorder.root / "frames/000002-head.png") as image:
            assert np.array_equal(np.asarray(image), expected)
        assert not queue.worker_alive
    finally:
        queue.close()


class BlockedRecorder:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.rows = []
        self.sealed = False

    def append(self, observation, action, audit):
        self.entered.set()
        assert self.release.wait(5), "test must release the actual writer"
        self.rows.append(observation["sim_time_s"])

    def finish(self, *args, **kwargs):
        self.sealed = True


def test_hard_capacity_refuses_without_dropping_accepted_work():
    from so101_demo.act.lossless_recorder import LosslessRecorderQueue
    from so101_demo.act.recorder import RecorderInfraError
    recorder = BlockedRecorder()
    queue = LosslessRecorderQueue(recorder, policy=POLICY, monotonic=lambda: 0.)
    try:
        queue.append(observation(1.), (0.,) * 6, audit(1.))
        assert recorder.entered.wait(2)
        for index in range(1, 15):
            t = 1. + index * .1
            queue.append(observation(t), (0.,) * 6, audit(t))
        with pytest.raises(RecorderInfraError, match="RECORDER_QUEUE_OVERFLOW"):
            queue.append(observation(2.5), (0.,) * 6, audit(2.5))
        recorder.release.set()
        queue.close()
        assert len(recorder.rows) == 16
        assert queue.snapshot()["accepted_samples"] == 16
        assert queue.snapshot()["dropped_samples"] == 0
        with pytest.raises(RecorderInfraError, match="RECORDER_QUEUE_OVERFLOW"):
            queue.finish(outcome())
        assert not recorder.sealed
    finally:
        recorder.release.set()
        queue.close()


def test_sustained_high_watermark_latches_at_frozen_hold_and_cannot_seal():
    from so101_demo.act.lossless_recorder import LosslessRecorderQueue
    from so101_demo.act.recorder import RecorderInfraError
    ticks = {"now": 0.}
    recorder = BlockedRecorder()
    queue = LosslessRecorderQueue(recorder, policy=POLICY, monotonic=lambda: ticks["now"])
    try:
        for index in range(12):
            t = 1. + index * .1
            queue.append(observation(t), (0.,) * 6, audit(t))
        assert recorder.entered.wait(2)
        ticks["now"] = .199
        queue.check()
        ticks["now"] = .2
        with pytest.raises(RecorderInfraError, match="RECORDER_QUEUE_HIGH_WATERMARK"):
            queue.check()
        recorder.release.set()
        queue.close()
        assert len(recorder.rows) == 12
        with pytest.raises(RecorderInfraError, match="RECORDER_QUEUE_HIGH_WATERMARK"):
            queue.finish(outcome())
        assert not recorder.sealed
    finally:
        recorder.release.set()
        queue.close()


def test_actual_writer_error_latches_and_never_becomes_business_failure():
    from so101_demo.act.lossless_recorder import LosslessRecorderQueue
    from so101_demo.act.recorder import RecorderInfraError
    class Broken(BlockedRecorder):
        def append(self, *args):
            raise OSError("actual disk failure")
    recorder = Broken()
    queue = LosslessRecorderQueue(recorder, policy=POLICY)
    try:
        queue.append(observation(1.), (0.,) * 6, audit(1.))
        with pytest.raises(RecorderInfraError, match="RECORDER_QUEUE_WRITE_FAILED"):
            queue.flush()
        with pytest.raises(RecorderInfraError, match="RECORDER_QUEUE_WRITE_FAILED"):
            queue.finish(outcome("FAILED"))
        assert not recorder.sealed
    finally:
        queue.close()


@pytest.mark.parametrize("field,value", [("queue_capacity_samples", 32),
    ("queue_high_watermark_samples", 13), ("queue_recovery_watermark_samples", 7),
    ("queue_high_watermark_hold_s", .3), ("lossless", False), ("sample_rate_hz", True)])
def test_unapproved_queue_settings_refuse_before_any_writer(field, value):
    from so101_demo.act.lossless_recorder import LosslessRecorderQueue
    with pytest.raises(ValueError, match="COLLECTION_RECORDER_INVALID"):
        LosslessRecorderQueue(BlockedRecorder(), policy={**POLICY, field: value})


def test_queue_hold_is_continuous_above_high_and_recovery_hysteresis_is_separate():
    from so101_demo.act.lossless_recorder import LosslessRecorderQueue, verify_queue_evidence
    ticks = {"now": 0.}
    second_entered = threading.Event()
    tokens = threading.Semaphore(0)
    class Stepped(BlockedRecorder):
        def append(self, observation, action, audit):
            if self.rows:
                second_entered.set()
            assert tokens.acquire(timeout=5)
            self.rows.append(observation["sim_time_s"])
    recorder = Stepped()
    queue = LosslessRecorderQueue(recorder, policy=POLICY, monotonic=lambda: ticks["now"])
    try:
        for index in range(12):
            t = 1. + index * .1
            queue.append(observation(t), (0.,) * 6, audit(t))
        ticks["now"] = .1
        tokens.release()
        assert second_entered.wait(2)
        assert queue.snapshot()["outstanding_samples"] == 11
        ticks["now"] = .4
        queue.check()  # No continuous .2s at >=12; still awaiting recovery to <=8.
        for _ in range(11):
            tokens.release()
        queue.flush()
        queue.close()
        verify_queue_evidence(queue.snapshot())
    finally:
        for _ in range(12):
            tokens.release()
        queue.close()


def test_delayed_high_marker_cannot_retime_original_queue_crossing():
    import copy
    from so101_demo.act.lossless_recorder import LosslessRecorderQueue, verify_queue_evidence
    ticks = {"now": 0.}
    recorder = BlockedRecorder()
    queue = LosslessRecorderQueue(recorder, policy=POLICY, monotonic=lambda: ticks["now"])
    try:
        for index in range(12):
            t = 1. + index * .1
            queue.append(observation(t), (0.,) * 6, audit(t))
        ticks["now"] = .05
        recorder.release.set()
        queue.flush()
        queue.close()
        original = queue.snapshot()
        verify_queue_evidence(original)
        altered = copy.deepcopy(original)
        marker = next(i for i, event in enumerate(altered["events"]) if event["kind"] == "high_watermark")
        for index, event in enumerate(altered["events"][marker:]):
            event["monotonic_s"] = .21 + index * .0001
        with pytest.raises(ValueError, match="RECORDER_QUEUE_EVIDENCE_INVALID"):
            verify_queue_evidence(altered)
        verify_queue_evidence(original)
    finally:
        recorder.release.set()
        queue.close()


def test_actual_child_queue_seals_and_independent_audit_requires_queue_receipt(tmp_path):
    import hashlib
    import json
    import shutil
    from test_act_child_recorder_binding import frozen_child_inputs, _options
    from so101_demo.act.episode_open import open_recorder_episode
    from so101_demo.act.episode_assembly import episode_audit_pair
    from so101_demo.act.recorder import verify_episode_seal
    from so101_demo.act.episode_audit import verify_audit_manifest

    manifest, _, snapshot = frozen_child_inputs(tmp_path)
    episode = open_recorder_episode(_options(tmp_path, inputs=manifest))
    try:
        assert episode.capture._asynchronous_sources is True
        assert episode.capture.max_skew_s == .1
        episode.start(1.)
        episode.capture.on_event({"kind": "first_command", "sim_time_s": 1.})
        for t in (1., 1.1, 1.2, 1.3):
            value = observation(t)
            physical = audit(t)
            physical.update(session_id="session", attempt_id="attempt")
            episode.set_physical_audit(physical)
            episode.push_numeric(stamp_s=t, arm=[0.] * 6, neck=0.)
            for camera in ("head", "wrist"):
                episode.push(camera, stamp_s=t, pixels=value[camera])
            episode.capture.on_reference({"source": "CONTROLLER_REFERENCE",
                "requested_sim_time_s": round(t + .1, 6), "positions": [0.] * 6, "accepted": True})
            episode.capture.drain()
        from test_act_raw_physics_chunks import _chunk
        from so101_demo.act.raw_physics_chunks import raw_chunk_from_ros
        import time
        now = time.monotonic_ns()
        message = _chunk(receipt=now)
        message.simulation_session_id, message.reset_epoch = "session", 2
        for sample in message.samples:
            sample.simulation_session_id, sample.reset_epoch = "session", 2
            sample.model_qpos, sample.model_qvel = [0.] * snapshot["nq"], [0.] * snapshot["nv"]
        episode.capture.audit.append_raw_physics(raw_chunk_from_ros(message, received_monotonic_ns=now))
        episode.finish(1.3, outcome=outcome())
        root = episode.capture.recorder.root
        audit_manifest, scope = episode_audit_pair(root)
        verified = verify_episode_seal(root / "seal.json", audit_manifest=audit_manifest, scope=scope)
        events = [json.loads(line) for line in (root / "audit/events.jsonl").read_text().splitlines()]
        proof = next(event["payload"]["queue_evidence"] for event in events
                     if event["kind"] == "recorder_queue")
        assert proof["accepted_samples"] == proof["written_samples"] == verified["record_count"]
        assert not episode.capture.recorder.worker_alive
        original = hashlib.sha256(audit_manifest.read_bytes()).hexdigest()
        copy = tmp_path / "isolated-missing-queue"
        shutil.copytree(root, copy)
        target = copy / "audit/events.jsonl"
        target.write_text("")
        copied_manifest = copy / "audit/audit-manifest.json"
        document = json.loads(copied_manifest.read_bytes())
        entry = document["files"]["events.jsonl"]
        entry.update(size=0, sha256=hashlib.sha256(b"").hexdigest())
        copied_manifest.write_text(json.dumps(document))
        with pytest.raises(ValueError, match="AUDIT_RECORDER_QUEUE_INCOMPLETE"):
            verify_audit_manifest(copied_manifest)
        verify_audit_manifest(audit_manifest)
        assert hashlib.sha256(audit_manifest.read_bytes()).hexdigest() == original
    finally:
        episode.close()


@pytest.mark.parametrize("damage", ["missing_raw", "wrong_raw_dimension", "changed_frozen_dimension"])
def test_execution_bound_audit_requires_raw_physics_and_frozen_dimensions(tmp_path, damage):
    import hashlib
    import json
    import shutil
    from test_act_child_recorder_binding import frozen_child_inputs, _options
    from test_act_raw_physics_chunks import _chunk
    from so101_demo.act.episode_open import open_recorder_episode
    from so101_demo.act.raw_physics_chunks import raw_chunk_from_ros
    from so101_demo.act.episode_assembly import episode_audit_pair
    from so101_demo.act.episode_audit import verify_audit_manifest
    import time

    manifest, _, snapshot = frozen_child_inputs(tmp_path)
    episode = open_recorder_episode(_options(tmp_path, inputs=manifest))
    try:
        episode.start(1.)
        episode.capture.on_event({"kind": "first_command", "sim_time_s": 1.})
        for t in (1., 1.1, 1.2, 1.3):
            value, physical = observation(t), audit(t)
            physical.update(session_id="session", attempt_id="attempt")
            episode.set_physical_audit(physical)
            episode.push_numeric(stamp_s=t, arm=[0.] * 6, neck=0.)
            for camera in ("head", "wrist"):
                episode.push(camera, stamp_s=t, pixels=value[camera])
            episode.capture.on_reference({"source": "CONTROLLER_REFERENCE", "requested_sim_time_s": round(t+.1, 6),
                "positions": [0.] * 6, "accepted": True})
            episode.capture.drain()
        now = time.monotonic_ns()
        message = _chunk(receipt=now)
        message.simulation_session_id, message.reset_epoch = "session", 2
        for sample in message.samples:
            sample.simulation_session_id, sample.reset_epoch = "session", 2
            sample.model_qpos, sample.model_qvel = [0.] * snapshot["nq"], [0.] * snapshot["nv"]
        episode.capture.audit.append_raw_physics(raw_chunk_from_ros(message, received_monotonic_ns=now))
        episode.finish(1.3, outcome=outcome())
        root = episode.capture.recorder.root
        source, _ = episode_audit_pair(root)
        verify_audit_manifest(source)
        original = {item.relative_to(root).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
                    for item in root.rglob("*") if item.is_file()}
        copied = tmp_path / "isolated-raw-negative"
        shutil.copytree(root, copied)
        event_path = copied / "audit/events.jsonl"
        events = [json.loads(line) for line in event_path.read_text().splitlines()]
        if damage == "missing_raw":
            removed = next(event["task_sequence"] for event in events if event["kind"] == "physics_chunk")
            events = [event for event in events if event["kind"] != "physics_chunk"]
            for i, event in enumerate(events, 1):
                event["sequence"] = i
                if event["task_sequence"] > removed:
                    event["task_sequence"] -= 1
        elif damage == "wrong_raw_dimension":
            raw = next(event["payload"]["raw_chunk"] for event in events if event["kind"] == "physics_chunk")
            raw["chunk"]["samples"][0]["model_qpos"].append(9.)
        else:
            path = copied / "audit/inputs.json"
            inputs = json.loads(path.read_bytes())
            inputs["execution_snapshot"].setdefault("model_identity", {})["nq"] = snapshot["nq"] + 1
            path.write_text(json.dumps(inputs))
        event_path.write_text("".join(json.dumps(event, sort_keys=True, separators=(",", ":"))+"\n" for event in events))
        path = copied / "audit/audit-manifest.json"
        document = json.loads(path.read_bytes())
        for name in ("events.jsonl", "inputs.json"):
            payload = (copied / "audit" / name).read_bytes()
            document["files"][name].update(size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
        path.write_text(json.dumps(document))
        expected = {"missing_raw": "AUDIT_PHYSICS_RAW_INCOMPLETE", "wrong_raw_dimension": "PHYSICS_RAW_VECTOR_INVALID",
                    "changed_frozen_dimension": "INPUTS_MANIFEST_INVALID"}[damage]
        with pytest.raises(ValueError, match=expected):
            verify_audit_manifest(path)
        verify_audit_manifest(source)
        assert original == {item.relative_to(root).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
                            for item in root.rglob("*") if item.is_file()}
    finally:
        episode.close()


def test_completed_write_transition_ends_high_hold_before_scheduler_delay():
    from so101_demo.act.lossless_recorder import LosslessRecorderQueue
    ticks = {"now": .201}
    queue = LosslessRecorderQueue(BlockedRecorder(), policy=POLICY, monotonic=lambda: ticks["now"])
    # The preceding high interval ends at the actual recorded write transition, not the later
    # time at which this bookkeeping resumes. No IO worker is started by this boundary control.
    with queue._condition:
        queue._accepted, queue._written = 12, 1
        queue._high_started = 0.
        queue._backpressure_active = True
        queue._events.append({"monotonic_s": .199, "kind": "written"})
        queue._watermark(transition_at=.199)
        queue.check()
        assert queue._failure is None and queue._high_started is None
        assert queue._backpressure_active is True
    queue.close()


@pytest.mark.parametrize("guard", ["end_before_start", "window", "latched_source"])
def test_owned_writer_closes_when_finalization_guard_refuses(tmp_path, guard):
    from test_act_child_recorder_binding import frozen_child_inputs, _options
    from so101_demo.act.episode_open import open_recorder_episode
    manifest, _, _ = frozen_child_inputs(tmp_path)
    episode = open_recorder_episode(_options(tmp_path, inputs=manifest))
    episode.start(1.)
    value = observation(1.)
    value.update(session_id="session", attempt_id="attempt")
    physical = audit(1.)
    physical.update(session_id="session", attempt_id="attempt")
    episode.capture.recorder.append(value, (0.,) * 6, physical)
    if guard == "latched_source":
        with pytest.raises(ValueError, match="SOURCE_FAILED"):
            episode.capture.reject_source("SOURCE_FAILED")
        call = lambda: episode.finish(1.2, outcome=outcome())
    elif guard == "window":
        call = lambda: episode.finish(1.2, outcome=outcome(), window={"wrong": True})
    else:
        call = lambda: episode.finish(.9, outcome=outcome(), window={"start_s": 1., "end_s": .9, "label_cutoff_s": .9})
    with pytest.raises(ValueError):
        call()
    assert not episode.capture.recorder.worker_alive
    assert episode.capture.recorder.snapshot()["closed"] is True
    assert episode.capture.recorder.snapshot()["written_samples"] == 1
    assert not (episode.capture.recorder.root / "seal.json").exists()
