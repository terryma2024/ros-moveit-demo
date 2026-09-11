"""Behavioral regression gates for fallback, attribution and durable admission."""

from dataclasses import asdict, replace
import json
from types import SimpleNamespace

import pytest

from so101_demo.parallel_batch.artifacts import AttemptWorkspace, ValidationWorkspace
from so101_demo.parallel_batch.contracts import (
    AttemptIdentity, ExecutionKind, InferenceRequest, ModelOutcome, RunMode,
    ValidationIdentity,
)


def request(model='yolo', *, validation=False, **changes):
    execution_id = 'validation-1' if validation else 'attempt-1'
    folder = 'validations' if validation else 'attempts'
    values = {
        'request_id': f'{model}-request', 'model_id': model,
        'execution_kind': ExecutionKind.VALIDATION if validation else ExecutionKind.ATTEMPT,
        'batch_id': 'batch-1', 'coordinator_epoch': 1, 'worker_id': 'worker-01',
        'worker_generation': 1, 'point_id': 'point-1', 'lease_generation': 1,
        'reset_epoch': 'reset-1', 'image_timestamp_s': 101.0,
        'input_relative_path': (f'worker-01/{folder}/point-1/{execution_id}'
                                '/working/perception/input/rgb.npy'),
        'input_sha256': 'a' * 64, 'attempt_id': None if validation else execution_id,
        'validation_id': execution_id if validation else None,
    }
    return InferenceRequest(**(values | changes))


def pose(req, **changes):
    from so101_demo.parallel_batch.perception import LocalizedPose
    values = {'request': req, 'broker_generation': 1, 'session_id': 'session-1',
              'depth_timestamp_s': 101.0, 'depth_sha256': 'b' * 64,
              'tf_timestamp_s': 101.0, 'source_frame': 'camera_optical',
              'target_frame': 'base_link', 'position_xyz': (0.2, 0.0, 0.05),
              'orientation_xyzw': (0.0, 0.0, 0.0, 1.0)}
    return LocalizedPose(**(values | changes))


def harness(tmp_path, *, validation=False):
    from so101_demo.parallel_batch.perception import (
        AdmissionContext, PerceptionPolicy, PoseAdmissionLatch,
    )
    req = request(validation=validation)
    identity_values = {name: getattr(req, name) for name in (
        'batch_id', 'coordinator_epoch', 'worker_id', 'worker_generation',
        'point_id', 'lease_generation')}
    if validation:
        identity = ValidationIdentity(**identity_values, validation_id=req.validation_id)
        workspace_type, mode = ValidationWorkspace, RunMode.PLAN_ONLY
    else:
        identity = AttemptIdentity(**identity_values, attempt_id=req.attempt_id)
        workspace_type, mode = AttemptWorkspace, RunMode.EXECUTE
    workspace = workspace_type.create(
        tmp_path / 'workers' / 'worker-01', identity, reset_epoch='reset-1',
        source_stamp={'image_timestamp_s': 101.0}, run_mode=mode)
    control = SimpleNamespace(now=101.1, authorized=True, geometry=True, quality=True)
    context = AdmissionContext('session-1', 100.0, 'camera_optical', 'base_link',
                               1.0, 0.05, 0.05)
    latch = PoseAdmissionLatch(
        workspace, context, broker_generation=1, clock=lambda: control.now,
        authorize=lambda req: control.authorized,
        geometry_gate=lambda req, value: control.geometry,
        quality_gate=lambda req, value: control.quality)
    policy = PerceptionPolicy(latch, yolo_model_id='yolo', grounded_model_id='grounded')
    return SimpleNamespace(req=req, workspace=workspace, latch=latch, policy=policy,
                           control=control, context=context)


def start(h, req=None):
    h.policy.start_request(req or h.req, depth_timestamp_s=101.0, depth_sha256='b' * 64)


def result(h, req, token):
    outcome = ModelOutcome.QUALIFIED if token == 'POSE' else ModelOutcome(token)
    return h.policy.record_result(req, outcome, broker_generation=1,
                                  localized_pose=pose(req) if token == 'POSE' else None)


@pytest.mark.parametrize(('yolo', 'grounded', 'disposition', 'reason'), [
    ('POSE', None, 'CONTINUE', None),
    ('NORMAL_REJECTION', 'POSE', 'CONTINUE', None),
    ('MODEL_ERROR', 'POSE', 'CONTINUE', None),
    ('NORMAL_REJECTION', 'NORMAL_REJECTION', 'FAILED', 'PERCEPTION_NO_POSE'),
    ('MODEL_ERROR', 'NORMAL_REJECTION', 'FAILED', 'PERCEPTION_MODEL_ERROR'),
    ('NORMAL_REJECTION', 'MODEL_ERROR', 'FAILED', 'PERCEPTION_MODEL_ERROR'),
    ('MODEL_ERROR', 'MODEL_ERROR', 'FAILED', 'PERCEPTION_MODEL_ERROR'),
    ('INFRA_ERROR', None, 'INVALID', 'PERCEPTION_INFRA_ERROR'),
    ('QUEUE_TIMEOUT', None, 'INVALID', 'PERCEPTION_QUEUE_TIMEOUT'),
    ('INFERENCE_TIMEOUT', None, 'INVALID', 'PERCEPTION_INFERENCE_TIMEOUT'),
    ('CANCELLED', None, 'CANCELLED', 'PERCEPTION_CANCELLED'),
    ('NORMAL_REJECTION', 'INFRA_ERROR', 'INVALID', 'PERCEPTION_INFRA_ERROR'),
    ('NORMAL_REJECTION', 'QUEUE_TIMEOUT', 'INVALID', 'PERCEPTION_QUEUE_TIMEOUT'),
    ('NORMAL_REJECTION', 'INFERENCE_TIMEOUT', 'INVALID', 'PERCEPTION_INFERENCE_TIMEOUT'),
    ('NORMAL_REJECTION', 'CANCELLED', 'CANCELLED', 'PERCEPTION_CANCELLED'),
    ('MODEL_ERROR', 'INFRA_ERROR', 'INVALID', 'PERCEPTION_INFRA_ERROR'),
    ('MODEL_ERROR', 'QUEUE_TIMEOUT', 'INVALID', 'PERCEPTION_QUEUE_TIMEOUT'),
    ('MODEL_ERROR', 'INFERENCE_TIMEOUT', 'INVALID', 'PERCEPTION_INFERENCE_TIMEOUT'),
    ('MODEL_ERROR', 'CANCELLED', 'CANCELLED', 'PERCEPTION_CANCELLED'),
])
def test_yolo_first_matrix(tmp_path, yolo, grounded, disposition, reason):
    h = harness(tmp_path)
    assert h.policy.decision.next_model == 'yolo'
    start(h)
    decision = result(h, h.req, yolo)
    if grounded:
        assert decision.next_model == 'grounded'
        req = request('grounded')
        start(h, req)
        decision = result(h, req, grounded)
    assert (decision.disposition, decision.reason) == (disposition, reason)
    assert decision.next_model is None
    assert decision.attempt_status == (disposition if disposition in ('FAILED', 'INVALID')
                                       else None)
    assert h.latch.accepted is (disposition == 'CONTINUE')


def test_qualified_candidate_and_topic_publish_do_not_open_latch(tmp_path):
    h = harness(tmp_path)
    start(h)
    h.workspace.write_json('perception/cup_pose_topic.json', asdict(pose(h.req)))
    decision = result(h, h.req, 'QUALIFIED')
    assert (decision.disposition, decision.next_model) == ('ADMIT_POSE', None)
    assert not h.latch.accepted
    assert not (h.workspace.path / 'pose_accepted.json').exists()
    assert h.policy.admit_pose(h.req, pose(h.req)).disposition == 'CONTINUE'


@pytest.mark.parametrize('gate', ['geometry', 'quality'])
def test_admission_rejection_falls_back_then_finishes_no_pose(tmp_path, gate):
    h = harness(tmp_path)
    setattr(h.control, gate, False)
    start(h)
    assert result(h, h.req, 'POSE').next_model == 'grounded'
    req = request('grounded')
    start(h, req)
    decision = result(h, req, 'POSE')
    assert (decision.disposition, decision.reason) == ('FAILED', 'PERCEPTION_NO_POSE')
    assert not h.latch.accepted


@pytest.mark.parametrize('event', ['IK_FAILED', 'PLANNING_FAILED', 'EXECUTION_FAILED',
                                   'COLLISION', 'GRASP_FAILED', 'RELEASE_FAILED'])
def test_downstream_failure_never_selects_fallback(tmp_path, event):
    from so101_demo.parallel_batch.perception import PerceptionError
    h = harness(tmp_path)
    start(h)
    assert result(h, h.req, 'POSE').disposition == 'CONTINUE'
    with pytest.raises(PerceptionError):
        h.policy.record_result(h.req, event, broker_generation=1)
    assert h.policy.decision.next_model is None
    assert h.latch.accepted


@pytest.mark.parametrize('first', ['POSE', 'INFRA_ERROR', 'QUEUE_TIMEOUT',
                                   'INFERENCE_TIMEOUT', 'CANCELLED'])
def test_success_or_transport_failure_cannot_start_grounded(tmp_path, first):
    from so101_demo.parallel_batch.perception import PerceptionError
    h = harness(tmp_path)
    start(h)
    result(h, h.req, first)
    with pytest.raises(PerceptionError):
        start(h, request('grounded'))


def test_grounded_cannot_go_first_or_repeat_a_stage(tmp_path):
    from so101_demo.parallel_batch.perception import PerceptionError
    h = harness(tmp_path)
    with pytest.raises(PerceptionError):
        start(h, request('grounded'))
    start(h)
    with pytest.raises(PerceptionError):
        start(h)
    result(h, h.req, 'NORMAL_REJECTION')
    with pytest.raises(PerceptionError):
        start(h)


IDENTITY_MUTATIONS = [
    ('request_id', 'another-request'), ('model_id', 'another-model'),
    ('batch_id', 'another-batch'), ('coordinator_epoch', 2),
    ('worker_id', 'worker-02'), ('worker_generation', 2), ('point_id', 'point-2'),
    ('attempt_id', 'attempt-2'), ('lease_generation', 2), ('reset_epoch', 'reset-2'),
    ('image_timestamp_s', 101.01), ('input_sha256', 'c' * 64),
    ('input_relative_path', 'worker-02/inputs/rgb.npy'),
]


@pytest.mark.parametrize(('field', 'value'), IDENTITY_MUTATIONS)
def test_every_request_identity_field_is_checked_before_model_error(tmp_path, field, value):
    from so101_demo.parallel_batch.perception import PerceptionError
    h = harness(tmp_path)
    start(h)
    with pytest.raises(PerceptionError, match='IDENTITY'):
        result(h, replace(h.req, **{field: value}), 'MODEL_ERROR')
    assert h.policy.decision.next_model is None
    assert not h.latch.accepted


@pytest.mark.parametrize(('field', 'value'), IDENTITY_MUTATIONS)
def test_localized_pose_must_echo_the_complete_expected_request(tmp_path, field, value):
    h = harness(tmp_path)
    start(h)
    altered = replace(h.req, **{field: value})
    assert not h.latch.accept(h.req, pose(altered))
    assert not h.latch.accepted


@pytest.mark.parametrize(('field', 'value'), [
    ('broker_generation', 2), ('session_id', 'another-session'),
    ('depth_timestamp_s', 100.0), ('depth_sha256', 'c' * 64),
    ('tf_timestamp_s', 100.0), ('tf_timestamp_s', 102.0),
    ('source_frame', 'other_camera'), ('target_frame', 'other_base'),
])
def test_pose_source_or_tf_mismatch_never_admits(tmp_path, field, value):
    h = harness(tmp_path)
    start(h)
    assert not h.latch.accept(h.req, pose(h.req, **{field: value}))
    assert not h.latch.accepted


@pytest.mark.parametrize('now', [100.9, 102.1])
def test_future_or_stale_source_is_rejected_at_admission(tmp_path, now):
    h = harness(tmp_path)
    start(h)
    h.control.now = now
    assert not h.latch.accept(h.req, pose(h.req))


@pytest.mark.parametrize('field', ['authorized', 'geometry', 'quality'])
@pytest.mark.parametrize('value', [False, 1, 'true', None])
def test_gate_requires_true_not_truthiness(tmp_path, field, value):
    h = harness(tmp_path)
    start(h)
    setattr(h.control, field, value)
    assert not h.latch.accept(h.req, pose(h.req))


@pytest.mark.parametrize('operation', ['fence', 'cancel', 'broker_restart'])
def test_fenced_cancelled_and_old_broker_results_are_audit_only(tmp_path, operation):
    h = harness(tmp_path)
    start(h)
    if operation == 'fence':
        h.latch.fence()
    elif operation == 'cancel':
        h.latch.cancel(h.req)
    decision = h.policy.record_result(
        h.req, ModelOutcome.QUALIFIED, broker_generation=2 if operation == 'broker_restart' else 1,
        localized_pose=pose(h.req))
    assert decision.disposition == 'CANCELLED'
    assert decision.attempt_status is None
    assert not h.latch.accept(h.req, pose(h.req))
    assert not h.latch.accepted


def test_acceptance_persists_full_identity_and_is_irreversible(tmp_path):
    h = harness(tmp_path)
    start(h)
    assert result(h, h.req, 'POSE').disposition == 'CONTINUE'
    path = h.workspace.path / 'pose_accepted.json'
    before = path.read_bytes()
    document = json.loads(before)
    assert document['type'] == 'POSE_ACCEPTED'
    assert document['request'] == asdict(h.req)
    assert document['localized_pose'] == json.loads(json.dumps(asdict(pose(h.req))))
    assert h.latch.accept(h.req, pose(h.req))
    assert not h.latch.accept(h.req, pose(h.req, position_xyz=(0.3, 0.0, 0.05)))
    assert path.read_bytes() == before
    with pytest.raises(AttributeError):
        h.latch.accepted = False


def test_persistence_failure_leaves_latch_closed_and_prevents_continue(tmp_path, monkeypatch):
    import so101_demo.runtime.task_artifacts as artifacts
    h = harness(tmp_path)
    start(h)
    real_fsync = artifacts.os.fsync

    def fail_fsync(fd):
        assert not h.latch.accepted
        raise OSError('injected fsync failure')

    monkeypatch.setattr(artifacts.os, 'fsync', fail_fsync)
    with pytest.raises(OSError, match='fsync'):
        result(h, h.req, 'POSE')
    assert not h.latch.accepted
    assert h.policy.decision.disposition != 'CONTINUE'
    monkeypatch.setattr(artifacts.os, 'fsync', real_fsync)


def test_validation_identity_stays_distinct_and_uses_own_workspace(tmp_path):
    h = harness(tmp_path, validation=True)
    start(h)
    assert not h.latch.accept(h.req, pose(request()))
    assert result(h, h.req, 'POSE').disposition == 'CONTINUE'
    document = json.loads((h.workspace.path / 'pose_accepted.json').read_text())
    assert document['request']['validation_id'] == 'validation-1'
    assert document['request']['attempt_id'] is None
    assert document['request']['execution_kind'] == 'validation'
    assert 'validations' in h.workspace.path.parts


def test_pure_decision_requires_persisted_admission(tmp_path):
    from so101_demo.parallel_batch.perception import decide
    h = harness(tmp_path)
    assert decide(ModelOutcome.QUALIFIED, latch=h.latch).disposition == 'ADMIT_POSE'
    start(h)
    result(h, h.req, 'POSE')
    assert decide(ModelOutcome.QUALIFIED, latch=h.latch).disposition == 'CONTINUE'


@pytest.mark.parametrize(('field', 'value'), [
    ('session_id', ''), ('source_frame', ''), ('target_frame', ''),
    ('reset_completed_timestamp_s', float('nan')), ('max_frame_age_s', float('inf')),
    ('max_rgbd_skew_s', -1.0), ('max_tf_skew_s', True),
])
def test_invalid_context_cannot_weaken_admission(tmp_path, field, value):
    from so101_demo.parallel_batch.perception import AdmissionContext
    values = {'session_id': 'session-1', 'reset_completed_timestamp_s': 100.0,
              'source_frame': 'camera_optical', 'target_frame': 'base_link',
              'max_frame_age_s': 1.0, 'max_rgbd_skew_s': 0.05, 'max_tf_skew_s': 0.05}
    with pytest.raises(ValueError):
        AdmissionContext(**(values | {field: value}))


@pytest.mark.parametrize(('field', 'value'), [
    ('broker_generation', True), ('broker_generation', 0),
    ('depth_timestamp_s', float('nan')), ('tf_timestamp_s', float('nan')),
    ('depth_sha256', 'wrong'), ('position_xyz', (float('nan'), 0.0, 0.0)),
    ('position_xyz', (0.2, 0.0)), ('position_xyz', (True, 0.0, 0.0)),
    ('orientation_xyzw', (0.0, 0.0, float('inf'), 1.0)),
    ('orientation_xyzw', (0.0, 0.0, 0.0, 0.0)), ('request', {}),
])
def test_malformed_pose_never_reaches_geometry_gate(field, value):
    with pytest.raises(ValueError):
        pose(request(), **{field: value})


@pytest.mark.parametrize(('field', 'value'), [
    ('depth_timestamp_s', float('nan')), ('depth_sha256', 'wrong'),
])
def test_expected_depth_provenance_is_validated(tmp_path, field, value):
    h = harness(tmp_path)
    values = {'depth_timestamp_s': 101.0, 'depth_sha256': 'b' * 64}
    with pytest.raises(ValueError):
        h.policy.start_request(h.req, **(values | {field: value}))
    assert h.policy.decision.next_model == 'yolo'


@pytest.mark.parametrize('boundary', ['reset', 'rgbd_skew', 'source_age'])
def test_unfresh_input_cannot_start_inference(tmp_path, boundary):
    h = harness(tmp_path)
    stamp, depth_stamp = 101.0, 101.0
    if boundary == 'reset':
        stamp = depth_stamp = 100.0
    elif boundary == 'rgbd_skew':
        depth_stamp = 100.9
    else:
        h.control.now = 102.1
    with pytest.raises(ValueError):
        h.policy.start_request(replace(h.req, image_timestamp_s=stamp),
                               depth_timestamp_s=depth_stamp, depth_sha256='b' * 64)
    assert h.policy.decision.next_model == 'yolo'


@pytest.mark.parametrize('change', ['lease', 'source_time'])
def test_blocking_validator_rechecks_authorization_and_freshness(tmp_path, change):
    h = harness(tmp_path)
    start(h)

    def blocking_geometry(req, value):
        if change == 'lease':
            h.control.authorized = False
        else:
            h.control.now = 103.0
        return True

    h.latch._geometry_gate = blocking_geometry
    decision = result(h, h.req, 'POSE')
    assert not h.latch.accepted
    assert decision.disposition == ('CANCELLED' if change == 'lease' else 'REQUEST_MODEL')
    if change == 'lease':
        assert decision.next_model is None


def test_visible_event_after_directory_fsync_failure_cannot_be_overwritten(tmp_path, monkeypatch):
    import so101_demo.runtime.task_artifacts as artifacts
    h = harness(tmp_path)
    start(h)
    real_sync = artifacts.fsync_directory

    def fail_directory_sync(path):
        raise OSError('directory fsync failed')

    monkeypatch.setattr(artifacts, 'fsync_directory', fail_directory_sync)
    with pytest.raises(OSError):
        result(h, h.req, 'POSE')
    event_path = h.workspace.path / 'pose_accepted.json'
    prior = event_path.read_bytes()
    assert not h.latch.accepted
    monkeypatch.setattr(artifacts, 'fsync_directory', real_sync)
    with pytest.raises(ValueError):
        h.policy.admit_pose(h.req, pose(h.req, position_xyz=(0.3, 0.0, 0.05)))
    assert event_path.read_bytes() == prior
    assert not h.latch.accepted
    with pytest.raises(ValueError, match='ADJUDICATION'):
        h.policy.admit_pose(h.req, pose(h.req))
    assert not h.latch.accepted


def test_two_workers_never_cross_admit_or_write_each_others_event(tmp_path):
    one, two = harness(tmp_path / 'one'), harness(tmp_path / 'two')
    start(one)
    other = replace(two.req, request_id='other-rgb', input_sha256='c' * 64)
    start(two, other)
    assert not one.latch.accept(other, pose(other))
    assert not two.latch.accept(one.req, pose(one.req))
    assert result(one, one.req, 'POSE').disposition == 'CONTINUE'
    assert not two.latch.accepted
    assert not (two.workspace.path / 'pose_accepted.json').exists()


@pytest.mark.parametrize(('yolo', 'grounded'), [('same', 'same'), ('', 'grounded')])
def test_invalid_model_configuration_cannot_repeat_yolo_as_fallback(tmp_path, yolo, grounded):
    from so101_demo.parallel_batch.perception import PerceptionPolicy
    h = harness(tmp_path)
    with pytest.raises(ValueError):
        PerceptionPolicy(h.latch, yolo_model_id=yolo, grounded_model_id=grounded)


def test_latch_restart_does_not_reauthorize_existing_acceptance(tmp_path):
    from so101_demo.parallel_batch.perception import PoseAdmissionLatch
    h = harness(tmp_path)
    start(h)
    result(h, h.req, 'POSE')
    with pytest.raises(ValueError, match='ADJUDICATION'):
        PoseAdmissionLatch(h.workspace, h.context, broker_generation=1,
                           clock=lambda: 101.1, authorize=lambda req: True,
                           geometry_gate=lambda req, value: True,
                           quality_gate=lambda req, value: True)


@pytest.mark.parametrize('window', ['write', 'readback'])
@pytest.mark.parametrize('change', ['authorization', 'source_age', 'broker_generation',
                                    'request', 'session', 'tf_frame', 'clock_reset',
                                    'clock_rewind', 'invalid_clock', 'authorization_error'])
def test_commit_window_invalidation_requires_adjudication(tmp_path, monkeypatch, window, change):
    from pathlib import Path
    import so101_demo.runtime.task_artifacts as artifacts
    from so101_demo.parallel_batch.perception import decide, PerceptionError
    h = harness(tmp_path)
    start(h)
    event_path = h.workspace.path / 'pose_accepted.json'

    def invalidate():
        if change == 'authorization':
            h.control.authorized = False
        elif change == 'source_age':
            h.control.now = 103.0
        elif change == 'broker_generation':
            h.latch.broker_generation = 2
        elif change == 'request':
            h.latch._expected = replace(h.req, request_id='new-request')
        elif change == 'session':
            h.latch.context = replace(h.context, session_id='new-session')
        elif change == 'tf_frame':
            h.latch.context = replace(h.context, target_frame='new-base')
        elif change == 'clock_rewind':
            h.control.now = 101.05
        elif change == 'invalid_clock':
            h.control.now = float('nan')
        elif change == 'authorization_error':
            def unavailable(req):
                raise OSError('authorization endpoint unavailable')
            h.latch._authorize = unavailable
        else:
            h.control.now = 100.5

    if window == 'write':
        real_sync = artifacts.fsync_directory

        def persist_then_invalidate(path):
            real_sync(path)
            invalidate()

        monkeypatch.setattr(artifacts, 'fsync_directory', persist_then_invalidate)
    else:
        real_read = Path.read_text

        def read_then_invalidate(path, *args, **kwargs):
            text = real_read(path, *args, **kwargs)
            if path == event_path:
                invalidate()
            return text

        monkeypatch.setattr(Path, 'read_text', read_then_invalidate)

    with pytest.raises(PerceptionError, match='ADJUDICATION'):
        result(h, h.req, 'POSE')
    assert event_path.exists()
    assert not h.latch.accepted
    assert h.policy.decision.disposition == 'INVALID'
    assert h.policy.decision.next_model is None
    assert h.policy.decision.reason == 'PERCEPTION_INFRA_ERROR'
    assert decide(ModelOutcome.NORMAL_REJECTION, latch=h.latch).disposition == 'INVALID'
    # Even restoring every external input cannot convert the visible event
    # into permission for this latch. Recovery must adjudicate the evidence.
    h.control.authorized, h.control.now = True, 101.1
    h.latch.broker_generation, h.latch.context, h.latch._expected = 1, h.context, h.req
    with pytest.raises(PerceptionError, match='ADJUDICATION'):
        h.latch.accept(h.req, pose(h.req))
    assert not h.latch.accepted


@pytest.mark.parametrize('callback', ['geometry', 'quality', 'authorization'])
def test_broker_generation_change_inside_validator_never_persists(tmp_path, callback):
    h = harness(tmp_path)
    start(h)

    def rotate_generation(*args):
        h.latch.broker_generation = 2
        return True

    if callback == 'authorization':
        def install_authorization_change(*args):
            h.latch._authorize = rotate_generation
            return True
        h.latch._geometry_gate = install_authorization_change
    else:
        setattr(h.latch, f'_{callback}_gate', rotate_generation)
    decision = result(h, h.req, 'POSE')
    assert decision.disposition == 'CANCELLED'
    assert decision.next_model is None
    assert not h.latch.accepted
    assert not (h.workspace.path / 'pose_accepted.json').exists()
