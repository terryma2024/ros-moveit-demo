"""Directed tests for the local (monitor-free) stopped-observation branch.

The exposure must run its post-settle observation entirely on the local runtime:
freeze the schema-1 request, take the exact local Image/CameraInfo pair and joint
originals, prove root settlement, run the single owned detector once, and record
the outcome with discard semantics that never turn an expired frame into
authority.
"""

import hashlib
import math
import time
from types import SimpleNamespace

import pytest

from so101_demo.act.head_evidence_identity import digest
from so101_demo.adapters.act.head_live_exposure import HeadLiveExposures
from test_act_head_local_observer import CAMERA_FRAME
from test_act_head_local_runtime import (armed_runtime, prime_current_inputs, runtime_setup,
                                         wait_for)
from so101_demo.adapters.act import ros_neck


def payload_bytes():
    return bytes((index * 7 + 11) % 251 for index in range(640 * 480 * 3))


class FakeBuffer:
    def __init__(self):
        self.can_transform_queries = []

    def can_transform(self, target, source, stamp):
        self.can_transform_queries.append((target, source, stamp.nanoseconds))
        return True

    def lookup_transform(self, target, source, stamp):
        return SimpleNamespace(
            header=SimpleNamespace(stamp=SimpleNamespace(sec=stamp.nanoseconds // 10**9,
                                                        nanosec=stamp.nanoseconds % 10**9)),
            transform=SimpleNamespace(
                translation=SimpleNamespace(x=.1, y=.2, z=.3),
                rotation=SimpleNamespace(x=0., y=0., z=0., w=1.)))


class FakeDetector:
    def __init__(self):
        self.calls = []

    def detect(self, pixels, **kwargs):
        self.calls.append((pixels.shape, kwargs))
        return [dict(track_id=1, confidence=.9, bbox=(0., 0., 10., 10.), mask=None)]


def image_record(wall_s, source_ns, payload):
    return dict(source_ns=source_ns, wall_s=wall_s, frame_id=CAMERA_FRAME, valid=True,
                width=640, height=480, step=1920, encoding='rgb8', is_bigendian=0,
                payload_bytes=640 * 480 * 3,
                payload_sha256=hashlib.sha256(payload).hexdigest())


def info_record(wall_s, source_ns):
    return dict(source_ns=source_ns, wall_s=wall_s, frame_id=CAMERA_FRAME, valid=True,
                width=640, height=480)


def feed_joint(row, sim, velocity=0.0, position=.2):
    row.clock.sim = sim
    message = ros_neck.JointState(name=['neck_yaw_joint'], position=[position],
                                  velocity=[velocity])
    message.header.stamp.sec, message.header.stamp.nanosec = divmod(round(sim * 1e9), 10**9)
    row.port._feedback(message)
    row.runtime.executor_progress()
    return message


def exposure_setup(monkeypatch, *, camera_skew_s=.02):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    events = []
    detector = FakeDetector()
    buffer = FakeBuffer()
    exposures = HeadLiveExposures(port=row.port, buffer=buffer, detector=detector,
                                  primary=runtime, monitor=None, camera_skew_s=camera_skew_s,
                                  emit=lambda event, **fields: events.append((event, fields)))
    exposures.activate()
    return SimpleNamespace(row=row, runtime=runtime, exposures=exposures, detector=detector,
                           buffer=buffer, events=events)


def stopped_request(row, *, sequence=1, motion_epoch=0, settled_source_floor_ns=1,
                    settled_wall_s=None, requested_wall_s=None, search_deadline_s=10.):
    policy = row.policy
    now = row.runtime.monotonic()
    scope = row.state.scope
    return dict(epoch=scope['epoch'], generation=scope['generation'], session_id=scope['session_id'],
                policy_sha256=scope['policy_sha256'], schema_version=1,
                simulation_policy_sha256=digest(policy.readback()), motion_epoch=motion_epoch,
                observation_sequence=sequence, settled_source_floor_ns=settled_source_floor_ns,
                settled_wall_s=now - .05 if settled_wall_s is None else settled_wall_s,
                requested_wall_s=now - .02 if requested_wall_s is None else requested_wall_s,
                search_deadline_ns=round((now + search_deadline_s) * 1e9))


def prime_exposure(local, *, final_sim=None, infos=True):
    """Feed three ordered quiet post-settle joint originals plus one exact image pair.

    Sources continue above the primed sample so no duplicate stamp resets the
    settlement run; an optional final sample keeps the current joint fresh
    while the admitted frame ages past the camera source bound.
    """
    row = local.row
    settled_wall = row.runtime.monotonic()
    base = getattr(row, 'prime_sim', 10.0)
    proof_sims = tuple(round(base + .01 * index, 6) for index in (1, 2, 3))
    image_sim = round(base + .04, 6)
    for sim in proof_sims:
        feed_joint(row, sim)
    payload = payload_bytes()
    row.clock.sim = image_sim
    wall = row.runtime.monotonic()
    local.exposures.observe('IMAGE', image_record(wall, round(image_sim * 1e9), payload),
                            payload=payload)
    if infos:
        local.exposures.observe('INFO', info_record(wall, round(image_sim * 1e9)))
    if final_sim is not None:
        feed_joint(row, final_sim)
    return settled_wall, payload


def test_inference_deadline_sets_clears_and_refuses_extension(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    now = runtime.monotonic()
    assert runtime.inference_deadline(now + 1.) is True
    assert runtime.inference_deadline(None) is True
    assert runtime._inference_deadline_wall_s is None
    assert runtime.inference_deadline(runtime.monotonic() + 1.) is True
    with pytest.raises(PermissionError):
        runtime.inference_deadline(runtime.monotonic() + 2.)
    assert runtime.failed is True
    runtime.close(timeout_s=1.)


def test_local_exposure_binds_the_local_runtime_without_a_monitor(monkeypatch):
    local = exposure_setup(monkeypatch)
    assert local.exposures.monitor is None
    assert local.exposures.port is local.row.port
    assert local.exposures.frame == CAMERA_FRAME
    assert local.exposures.age_ns == round(local.row.policy.perception_max_age_s * 1e9)
    assert local.exposures._simulation_policy is local.row.policy
    with pytest.raises(PermissionError):
        local.exposures.infer(observation_request=None)
    local.runtime.close(timeout_s=1.)


def test_local_stopped_observation_completes_with_one_owned_cuda_call(monkeypatch):
    local = exposure_setup(monkeypatch)
    prime_current_inputs(local.row)
    settled_wall, payload = prime_exposure(local)
    request = stopped_request(local.row, settled_wall_s=settled_wall)
    record = local.exposures.infer(observation_request=request)
    assert record is not None, 'the local stopped branch must complete a valid observation'
    assert record['observation_outcome'] == 'VALID'
    assert record['observation_sequence'] == 1 and record['motion_epoch'] == 0
    assert record['inference_performed'] is True
    assert record['detections'] and record['discarded_detections'] == []
    assert record['cuda_started_wall_s'] is not None
    assert record['completion_wall_s'] >= record['cuda_started_wall_s']
    assert record['record_saved_wall_s'] >= record['completion_wall_s']
    assert record['original_info']['source_ns'] == record['source_ns']
    assert record['causal_joint']['source_ns'] <= record['source_ns']
    assert record['root_settled_samples'] and len(record['root_settled_samples']) == 3
    assert len(local.detector.calls) == 1
    assert local.detector.calls[0][0] == (480, 640, 3)
    assert local.detector.calls[0][1]['source_stamp_ns'] == record['source_ns']
    finished = local.exposures.next_completed_observation(0)
    assert finished is not None and finished['observation_sequence'] == 1
    assert local.exposures.next_completed_observation(1) is None
    assert local.runtime._inference_deadline_wall_s is None
    assert local.runtime.failed is False
    local.runtime.close(timeout_s=1.)


def test_local_stopped_observation_discards_an_expired_pair_without_cuda(monkeypatch):
    local = exposure_setup(monkeypatch)
    prime_current_inputs(local.row)
    settled_wall, _ = prime_exposure(local, final_sim=10.35)
    request = stopped_request(local.row, settled_wall_s=settled_wall)
    record = local.exposures.infer(observation_request=request)
    assert record is not None
    assert record['observation_outcome'] == 'EXPIRED'
    assert record['inference_performed'] is False
    assert record['detections'] == [] and record['cuda_started_wall_s'] is None
    assert local.detector.calls == []
    assert local.runtime.failed is False
    local.runtime.close(timeout_s=1.)


def test_local_stopped_observation_returns_none_on_a_moving_root_proof(monkeypatch):
    local = exposure_setup(monkeypatch)
    prime_current_inputs(local.row)
    settled_wall, _ = prime_exposure(local)
    feed_joint(local.row, 10.06, velocity=.5)
    request = stopped_request(local.row, settled_wall_s=settled_wall)
    assert local.exposures.infer(observation_request=request) is None
    assert local.detector.calls == []
    assert local.exposures.records_snapshot() == []
    assert local.runtime.failed is False
    local.runtime.close(timeout_s=1.)


def test_local_stopped_observation_refuses_a_replayed_request(monkeypatch):
    local = exposure_setup(monkeypatch)
    prime_current_inputs(local.row)
    settled_wall, _ = prime_exposure(local)
    request = stopped_request(local.row, settled_wall_s=settled_wall)
    assert local.exposures.infer(observation_request=request) is not None
    with pytest.raises(PermissionError):
        local.exposures.infer(observation_request=request)
    assert len(local.detector.calls) == 1
    assert local.row.state.faulted is True
    local.runtime.close(timeout_s=1.)


def test_local_exposure_missing_simulation_policy_faults_before_detector(monkeypatch):
    local = exposure_setup(monkeypatch)
    try:
        local.exposures._simulation_policy = None
        with pytest.raises(PermissionError, match='HEAD_LIVE_LOCAL_POLICY_REQUIRED'):
            local.exposures.infer()
        assert local.runtime.faulted
        assert local.detector.calls == []
        assert local.exposures.results == []
    finally:
        local.runtime.close(timeout_s=1.)
