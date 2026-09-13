"""Exercise detector execution, immutable inputs and explicit failure boundaries."""

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


def fixture_runtime(tmp_path, monkeypatch, *, validation=False, failure=None):
    from so101_demo.runtime.parallel_perception_runtime import (
        ParallelPerceptionRuntime, Snapshot, frozen_options)
    from so101_demo.adapters.perception import detector_factory
    from so101_demo.core.detection import DetectionBatch, DetectionCandidate
    from so101_demo.parallel_batch.contracts import (
        ExecutionKind, InferenceRequest, NormalizedInferenceResponseIdentity)
    root = tmp_path / 'inputs'
    root.mkdir(mode=0o700)
    branch, eid = ('validations', 'v1') if validation else ('attempts', 'a1')
    relative = f'w1/{branch}/p1/{eid}/working/perception/input/rgb.npy'
    target = root / relative
    target.parent.mkdir(parents=True)
    for parent in target.parents:
        if parent == root:
            break
        parent.chmod(0o700)
    np.save(target, np.zeros((2, 3, 3), dtype=np.uint8))
    target.chmod(0o400)
    req = InferenceRequest(
        request_id='r1', model_id='plastic-cup-yolo11n-seg-v1',
        execution_kind=ExecutionKind.VALIDATION if validation else ExecutionKind.ATTEMPT,
        batch_id='b1', coordinator_epoch=1, worker_id='w1', worker_generation=1,
        point_id='p1', lease_generation=1, reset_epoch='reset1', image_timestamp_s=1.25,
        input_relative_path=relative, input_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        attempt_id=None if validation else eid, validation_id=eid if validation else None)
    snapshot = Snapshot(shape=(2, 3, 3), source_stamp_ns=1250000000,
                        source_frame_id='camera', start_event_id='event1',
                        start_event_type='VALIDATION_STARTED' if validation else 'ATTEMPT_STARTED',
                        start_identity=NormalizedInferenceResponseIdentity.from_request(req))
    calls = []

    class Detector:
        runtime_device = 'cuda'

        def detect(self, frame, query):
            calls.append(('detect', frame.source_stamp_ns, query.class_id))
            if failure:
                raise failure
            candidate = DetectionCandidate(
                '0', 'plastic_cup', .9, (0., 0., 3., 2.),
                np.array([[False, True, True], [False, False, True]]),
                frame.source_stamp_ns, frame.source_frame_id, 3, 2)
            return DetectionBatch('fake', 'a' * 64, 'cuda', 3., 3, 2, (candidate,))

    def build(options):
        calls.append(('build', options.backend))
        return detector_factory.BuiltDetector(Detector(), 2., {'backend': options.backend})

    monkeypatch.setattr(detector_factory, 'build_detector', build)
    ipc = tmp_path / 'ipc'
    ipc.mkdir(mode=0o700)
    runtime = ParallelPerceptionRuntime(
        input_root=root, ready_receipt=ipc / 'ready.json',
        options=frozen_options(Path('/models/yolo/best.pt'), Path('/models/grounded')),
        provenance={'image_id': 'sha256:' + 'b' * 64, 'dockerfile_sha256': 'c' * 64,
                    'lock_sha256': 'd' * 64, 'source_sha256': 'e' * 64},
        authorize=lambda request, snapshot: snapshot.start_event_id == 'event1',
        readonly_mount=lambda root: True)
    return SimpleNamespace(runtime=runtime, req=req, snapshot=snapshot, calls=calls,
                           file=target, root=root, receipt=ipc / 'ready.json')


@pytest.mark.parametrize('validation', [False, True])
def test_both_execution_kinds_normalize_lossless_candidates(tmp_path, monkeypatch, validation):
    from so101_demo.parallel_batch.contracts import ModelOutcome
    f = fixture_runtime(tmp_path, monkeypatch, validation=validation)
    f.runtime.start()
    result = f.runtime.infer(f.req, f.snapshot)
    assert result.outcome is ModelOutcome.QUALIFIED
    wire = json.loads(json.dumps(result.candidate, allow_nan=False))
    assert wire['candidates'][0]['mask_rle'] == {'shape': [2, 3], 'counts': [1, 2, 2, 1]}
    assert wire['source_stamp_ns'] == 1250000000
    assert f.calls[:2] == [('build', 'yolo_seg'), ('build', 'grounded_sam')]
    f.runtime.start()
    assert sum(c[0] == 'build' for c in f.calls) == 2
    assert f.receipt.stat().st_mode & 0o777 == 0o600
    assert f.receipt.stat().st_uid == os.getuid()
    assert json.loads(f.receipt.read_text())['ready'] is True


def test_started_healthy_runtime_replays_ready_to_late_lifecycle_observer(
        tmp_path, monkeypatch):
    f = fixture_runtime(tmp_path, monkeypatch)
    f.runtime.start()
    receipt = f.receipt.read_bytes()
    receipt_mtime_ns = f.receipt.stat().st_mtime_ns
    observed = []
    f.runtime.health_changed = observed.append

    f.runtime.start()

    assert observed == [True]
    assert sum(call[0] == 'build' for call in f.calls) == 2
    assert f.receipt.read_bytes() == receipt
    assert f.receipt.stat().st_mtime_ns == receipt_mtime_ns


def test_started_unhealthy_runtime_still_requires_new_generation(tmp_path, monkeypatch):
    from so101_demo.adapters.perception.errors import ModelRuntimeInfrastructureError
    f = fixture_runtime(tmp_path, monkeypatch)
    f.runtime.start()
    f.runtime._unhealthy()
    observed = []
    f.runtime.health_changed = observed.append

    with pytest.raises(ModelRuntimeInfrastructureError, match='RESTART_REQUIRED'):
        f.runtime.start()

    assert observed == []
    assert sum(call[0] == 'build' for call in f.calls) == 2


@pytest.mark.parametrize('bad', ['kind_path', 'event_type', 'event_identity', 'ack',
                               'hash', 'shape', 'stamp', 'mode', 'symlink'])
@pytest.mark.parametrize('validation', [False, True])
def test_invalid_snapshot_never_reaches_model(tmp_path, monkeypatch, bad, validation):
    from so101_demo.parallel_batch.contracts import ModelOutcome
    f = fixture_runtime(tmp_path, monkeypatch, validation=validation)
    f.runtime.start()
    if bad == 'kind_path':
        f.req = replace(f.req, input_relative_path=f.req.input_relative_path.replace(
            'validations' if validation else 'attempts', 'attempts' if validation else 'validations'))
    elif bad == 'event_type':
        f.snapshot = replace(f.snapshot, start_event_type='LEASE_GRANTED')
    elif bad == 'event_identity':
        f.snapshot = replace(f.snapshot, start_identity=replace(f.snapshot.start_identity, point_id='p2'))
    elif bad == 'ack':
        f.snapshot = replace(f.snapshot, start_event_id='unacknowledged')
    elif bad == 'hash':
        f.req = replace(f.req, input_sha256='0' * 64)
    elif bad == 'shape':
        f.snapshot = replace(f.snapshot, shape=(3, 2, 3))
    elif bad == 'stamp':
        f.snapshot = replace(f.snapshot, source_stamp_ns=7)
    elif bad == 'mode':
        f.file.chmod(0o600)
    else:
        preserved = f.file.with_name('original.npy')
        f.file.rename(preserved)
        f.file.symlink_to(preserved)
    result = f.runtime.infer(f.req, f.snapshot)
    assert result.outcome is ModelOutcome.INFRA_ERROR
    assert not f.runtime.healthy
    assert not any(c[0] == 'detect' for c in f.calls)


@pytest.mark.parametrize('name', ['oom', 'unknown', 'socket', 'deadline', 'legacy_yolo'])
def test_runtime_errors_are_infrastructure_and_poison_health(tmp_path, monkeypatch, name):
    from so101_demo.adapters.perception.yolo_seg import YoloResultError
    from so101_demo.parallel_batch.contracts import ModelOutcome
    errors = {'oom': RuntimeError('CUDA out of memory'), 'unknown': RuntimeError('unknown'),
              'socket': ConnectionError('closed'), 'deadline': TimeoutError('deadline'),
              'legacy_yolo': YoloResultError('INFERENCE_FAILED: unknown')}
    f = fixture_runtime(tmp_path, monkeypatch, failure=errors[name])
    f.runtime.start()
    assert f.runtime.infer(f.req, f.snapshot).outcome is ModelOutcome.INFRA_ERROR
    assert not f.runtime.healthy


def test_first_runtime_failure_is_durable_and_never_overwritten(tmp_path, monkeypatch):
    from so101_demo.parallel_batch.contracts import ModelOutcome

    f = fixture_runtime(
        tmp_path, monkeypatch, failure=RuntimeError('diagnostic CUDA sentinel'))
    f.runtime.start()

    result = f.runtime.infer(f.req, f.snapshot)

    assert result.outcome is ModelOutcome.INFRA_ERROR
    assert result.reason == 'diagnostic CUDA sentinel'
    failure_receipt = f.receipt.with_name('.failure.json')
    first_payload = failure_receipt.read_bytes()
    first_mtime_ns = failure_receipt.stat().st_mtime_ns
    assert failure_receipt.stat().st_mode & 0o777 == 0o600
    assert json.loads(first_payload) == {
        'schema_version': 1,
        'kind': 'runtime_inference_failure',
        'error_type': 'RuntimeError',
        'reason': 'diagnostic CUDA sentinel',
        'request_id': 'r1',
        'model_id': 'plastic-cup-yolo11n-seg-v1',
        'execution_kind': 'attempt',
        'batch_id': 'b1',
        'worker_id': 'w1',
        'worker_generation': 1,
        'point_id': 'p1',
    }

    second = f.runtime.infer(f.req, f.snapshot)

    assert second.outcome is ModelOutcome.INFRA_ERROR
    assert second.reason == 'BROKER_UNHEALTHY'
    assert failure_receipt.read_bytes() == first_payload
    assert failure_receipt.stat().st_mtime_ns == first_mtime_ns


def test_deterministic_error_is_model_error_and_empty_is_normal(tmp_path, monkeypatch):
    from so101_demo.adapters.perception.errors import DeterministicModelResultError
    from so101_demo.parallel_batch.contracts import ModelOutcome
    f = fixture_runtime(tmp_path, monkeypatch, failure=DeterministicModelResultError('schema'))
    f.runtime.start()
    assert f.runtime.infer(f.req, f.snapshot).outcome is ModelOutcome.MODEL_ERROR
    assert f.runtime.healthy
    detector = f.runtime.detectors[f.req.model_id].detector
    from so101_demo.core.detection import DetectionBatch
    detector.detect = lambda frame, query: DetectionBatch('fake', 'a' * 64, 'cuda', 0., 3, 2, ())
    assert f.runtime.infer(f.req, f.snapshot).outcome is ModelOutcome.NORMAL_REJECTION


def test_warmup_failure_never_publishes_ready(tmp_path, monkeypatch):
    from so101_demo.adapters.perception import detector_factory
    from so101_demo.adapters.perception.errors import ModelRuntimeInfrastructureError
    f = fixture_runtime(tmp_path, monkeypatch)
    def fail(options):
        raise RuntimeError('CUDA warmup failure')
    monkeypatch.setattr(detector_factory, 'build_detector', fail)
    with pytest.raises(ModelRuntimeInfrastructureError):
        f.runtime.start()
    assert not f.receipt.exists()
    assert not f.runtime.healthy


@pytest.mark.parametrize('failure', ['load', 'warmup'])
def test_second_model_setup_failure_never_publishes_partial_ready(tmp_path, monkeypatch, failure):
    from so101_demo.adapters.perception import detector_factory
    from so101_demo.adapters.perception.errors import ModelRuntimeInfrastructureError
    f = fixture_runtime(tmp_path, monkeypatch)
    build = detector_factory.build_detector
    calls = []
    def build_second(options):
        calls.append(options.backend)
        if len(calls) == 2:
            raise RuntimeError('second model ' + failure + ' failed')
        return build(options)
    monkeypatch.setattr(detector_factory, 'build_detector', build_second)
    with pytest.raises(ModelRuntimeInfrastructureError, match='second model'):
        f.runtime.start()
    assert calls == ['yolo_seg', 'grounded_sam']
    assert not f.receipt.exists()
    assert not f.runtime.healthy


@pytest.mark.parametrize('phase', ['file_fsync', 'directory_fsync', 'readback'])
def test_ready_receipt_io_failure_is_unhealthy_and_retained(tmp_path, monkeypatch, phase):
    from so101_demo.adapters.perception.errors import ModelRuntimeInfrastructureError
    f = fixture_runtime(tmp_path, monkeypatch)
    fsync = os.fsync
    calls = []
    def fail_fsync(fd):
        calls.append(fd)
        if len(calls) == (1 if phase == 'file_fsync' else 2):
            raise OSError('receipt fsync failure')
        return fsync(fd)
    if phase == 'readback':
        monkeypatch.setattr(Path, 'read_bytes', lambda path: b'corrupt')
    else:
        monkeypatch.setattr(os, 'fsync', fail_fsync)
    with pytest.raises(ModelRuntimeInfrastructureError):
        f.runtime.start()
    assert not f.runtime.healthy
    assert f.receipt.exists()  # An uncertain receipt remains auditable.
    assert f.receipt.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('mutation', ['bytes', 'mode'])
def test_actual_input_change_between_path_check_and_open_never_reaches_model(
        tmp_path, monkeypatch, mutation):
    from so101_demo.parallel_batch.contracts import ModelOutcome
    f = fixture_runtime(tmp_path, monkeypatch)
    f.runtime.start()
    original_open = os.open
    changed = []
    def racing_open(path, flags, *args, **kwargs):
        if Path(path) == f.file and not changed:
            changed.append(True)
            f.file.chmod(0o600)
            if mutation == 'bytes':
                data = bytearray(f.file.read_bytes())
                data[-1] ^= 1
                f.file.write_bytes(data)
                f.file.chmod(0o400)
        return original_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, 'open', racing_open)
    assert f.runtime.infer(f.req, f.snapshot).outcome is ModelOutcome.INFRA_ERROR
    assert not f.runtime.healthy
    assert not any(call[0] == 'detect' for call in f.calls)


def test_yolo_predict_oom_has_infrastructure_type():
    from so101_demo.adapters.perception.errors import ModelRuntimeInfrastructureError
    from so101_demo.adapters.perception.yolo_seg import YoloSegDetector
    detector = object.__new__(YoloSegDetector)
    def fail(**kwargs):
        raise RuntimeError('CUDA out of memory')
    detector._model = SimpleNamespace(predict=fail)
    detector._imgsz, detector.runtime_device = 640, 'cuda'
    with pytest.raises(ModelRuntimeInfrastructureError):
        detector._predict(np.zeros((2, 3, 3), dtype=np.uint8))


def test_grounded_oom_has_infrastructure_type():
    from so101_demo.adapters.perception.errors import ModelRuntimeInfrastructureError
    from so101_demo.adapters.perception.grounded_sam import GroundedSamDetector
    detector = object.__new__(GroundedSamDetector)
    detector._monotonic_ns = lambda: 1
    def fail(frame, query):
        raise RuntimeError('CUDA out of memory')
    detector._grounding_proposals = fail
    with pytest.raises(ModelRuntimeInfrastructureError):
        detector.detect(None, None)


def test_service_drives_real_broker_and_fences_late_ack(tmp_path, monkeypatch):
    from so101_demo.runtime.parallel_perception_runtime import PerceptionService, GROUNDED_ID
    from so101_demo.parallel_batch.contracts import ModelOutcome, load_parallel_runtime_config
    config = load_parallel_runtime_config(Path(__file__).parents[1] / 'config/mujoco/parallel_batch_v1.yaml')
    f = fixture_runtime(tmp_path, monkeypatch)
    service = PerceptionService(f.runtime, config, generation=3)
    service.start()
    assert service.submit(f.req, f.snapshot).accepted
    response = service.run_next()
    assert response.outcome is ModelOutcome.QUALIFIED
    assert response.broker_generation == 3
    grounded = replace(f.req, request_id='r2', model_id=GROUNDED_ID)
    snap = replace(f.snapshot, start_identity=replace(f.snapshot.start_identity, request_id='r2'))
    assert service.submit(grounded, snap).accepted
    f.runtime.authorize = lambda request, snapshot: False
    assert service.run_next() is None
    assert service.broker.poll_response(grounded).outcome is ModelOutcome.CANCELLED


def test_service_preserves_initiating_runtime_failure_before_health_fanout(
        tmp_path, monkeypatch):
    from so101_demo.runtime.parallel_perception_runtime import PerceptionService
    from so101_demo.parallel_batch.contracts import ModelOutcome, load_parallel_runtime_config

    config = load_parallel_runtime_config(
        Path(__file__).parents[1] / 'config/mujoco/parallel_batch_v1.yaml')
    f = fixture_runtime(
        tmp_path, monkeypatch, failure=RuntimeError('diagnostic CUDA sentinel'))
    service = PerceptionService(f.runtime, config, generation=1)
    service.start()

    assert service.submit(f.req, f.snapshot).accepted
    response = service.run_next()

    assert response.outcome is ModelOutcome.INFRA_ERROR
    assert response.reason == 'diagnostic CUDA sentinel'
    assert not service.broker.healthy
    assert not f.runtime.healthy


def test_service_never_repolls_a_delivered_qualified_response_past_its_deadline(
        tmp_path, monkeypatch):
    from so101_demo.runtime.parallel_perception_runtime import PerceptionService
    from so101_demo.parallel_batch.contracts import ModelOutcome, load_parallel_runtime_config

    config = load_parallel_runtime_config(
        Path(__file__).parents[1] / 'config/mujoco/parallel_batch_v1.yaml')
    f = fixture_runtime(tmp_path, monkeypatch)
    now = [1.0]
    service = PerceptionService(f.runtime, config, generation=1, clock=lambda: now[0])
    service.start()
    assert service.submit(f.req, f.snapshot).accepted
    assert service.run_next().outcome is ModelOutcome.QUALIFIED

    now[0] += config.yolo_inference_timeout_s + 1.0
    second = replace(f.req, request_id='r2')
    second_snapshot = replace(
        f.snapshot,
        start_identity=replace(f.snapshot.start_identity, request_id='r2'))
    submission = service.submit(second, second_snapshot)

    assert submission.accepted
    assert service.broker.healthy
    assert f.runtime.healthy
    assert not f.receipt.with_name('.failure.json').exists()


def test_input_changed_during_detector_never_returns_candidate(tmp_path, monkeypatch):
    from so101_demo.parallel_batch.contracts import ModelOutcome
    f = fixture_runtime(tmp_path, monkeypatch)
    f.runtime.start()
    detector = f.runtime.detectors[f.req.model_id].detector
    detect = detector.detect
    def changing(frame, query):
        result = detect(frame, query)
        f.file.chmod(0o600)
        return result
    detector.detect = changing
    assert f.runtime.infer(f.req, f.snapshot).outcome is ModelOutcome.INFRA_ERROR


def test_normalized_schema_error_and_rle_roundtrip(tmp_path, monkeypatch):
    from so101_demo.runtime.parallel_perception_runtime import normalize_batch
    from so101_demo.adapters.perception.errors import DeterministicModelResultError
    from so101_demo.core.detection import DetectionFrame, DetectionQuery
    f = fixture_runtime(tmp_path, monkeypatch)
    f.runtime.start()
    frame = DetectionFrame(np.zeros((2, 3, 3), dtype=np.uint8), 1250000000, 'camera')
    batch = f.runtime.detectors[f.req.model_id].detector.detect(frame, DetectionQuery('plastic_cup'))
    mask = normalize_batch(batch, frame)['candidates'][0]['mask_rle']
    decoded = [bool(i % 2) for i, count in enumerate(mask['counts']) for _ in range(count)]
    assert decoded == [False, True, True, False, False, True]
    object.__setattr__(batch.candidates[0], 'confidence', float('nan'))
    with pytest.raises(DeterministicModelResultError):
        normalize_batch(batch, frame)


def test_yolo_nonfinite_mask_is_deterministic_output_error():
    from so101_demo.adapters.perception.yolo_seg import convert_yolo_result
    from so101_demo.adapters.perception.errors import DeterministicModelResultError
    from so101_demo.core.detection import DetectionFrame
    result = SimpleNamespace(boxes=SimpleNamespace(xyxy=np.array([[0, 0, 2, 2]]),
                                                  cls=np.array([0]), conf=np.array([.9])),
                             masks=SimpleNamespace(data=np.array([[[1., float('nan')], [1., 1.]]])))
    with pytest.raises(DeterministicModelResultError):
        convert_yolo_result(result, DetectionFrame(np.zeros((2, 2, 3), dtype=np.uint8), 1, 'camera'),
                            model_id='yolo', weights_sha256='a' * 64, runtime_device='cuda',
                            inference_latency_ms=0., class_names={0: 'plastic_cup'})


def test_service_preserves_empty_rejection_and_marks_deadline_unhealthy(tmp_path, monkeypatch):
    from so101_demo.runtime.parallel_perception_runtime import PerceptionService
    from so101_demo.parallel_batch.contracts import ModelOutcome, load_parallel_runtime_config
    from so101_demo.core.detection import DetectionBatch
    config = load_parallel_runtime_config(Path(__file__).parents[1] / 'config/mujoco/parallel_batch_v1.yaml')
    f = fixture_runtime(tmp_path, monkeypatch)
    now = [1.]
    service = PerceptionService(f.runtime, config, generation=1, clock=lambda: now[0])
    service.start()
    detector = f.runtime.detectors[f.req.model_id].detector
    detector.detect = lambda frame, query: DetectionBatch('fake', 'a' * 64, 'cuda', 0., 3, 2, ())
    assert service.submit(f.req, f.snapshot).accepted
    assert service.run_next().outcome is ModelOutcome.NORMAL_REJECTION
    late = replace(f.req, request_id='late')
    snapshot = replace(f.snapshot, start_identity=replace(f.snapshot.start_identity, request_id='late'))
    assert service.submit(late, snapshot).accepted
    now[0] = 12.
    assert service.poll_response(late).outcome is ModelOutcome.QUEUE_TIMEOUT
    assert not f.runtime.healthy
    assert not service.broker.healthy
    failure = json.loads(f.receipt.with_name('.failure.json').read_bytes())
    assert failure['kind'] == 'broker_response_failure'
    assert failure['error_type'] == 'BrokerResponse.QUEUE_TIMEOUT'
    assert failure['reason'] == 'QUEUE_DEADLINE_EXCEEDED'
    assert failure['request_id'] == 'late'


def test_yolo_completed_result_count_error_is_model_error(tmp_path, monkeypatch):
    from so101_demo.adapters.perception.yolo_seg import YoloSegDetector
    from so101_demo.parallel_batch.contracts import ModelOutcome
    f = fixture_runtime(tmp_path, monkeypatch)
    f.runtime.start()
    detector = object.__new__(YoloSegDetector)
    detector._model = SimpleNamespace(predict=lambda **kwargs: [])
    detector._imgsz, detector.runtime_device = 640, 'cuda'
    detector._monotonic_ns = lambda: 1
    f.runtime.detectors[f.req.model_id] = replace(f.runtime.detectors[f.req.model_id], detector=detector)
    assert f.runtime.infer(f.req, f.snapshot).outcome is ModelOutcome.MODEL_ERROR
    assert f.runtime.healthy


def test_grounded_completed_candidate_limit_error_is_deterministic():
    from so101_demo.adapters.perception.grounded_sam import GroundedSamDetector
    from so101_demo.adapters.perception.grounded_sam_postprocess import GroundedSamResultError
    from so101_demo.adapters.perception.errors import DeterministicModelResultError
    detector = object.__new__(GroundedSamDetector)
    detector._monotonic_ns = lambda: 1
    def fail(frame, query):
        raise GroundedSamResultError('CANDIDATE_LIMIT_EXCEEDED', '17 > 16')
    detector._grounding_proposals = fail
    with pytest.raises(DeterministicModelResultError):
        detector.detect(None, None)


def test_smoke_records_independent_monotonic_latency_per_model(tmp_path, monkeypatch):
    from so101_demo.cli.parallel_perception_broker import smoke_models
    from so101_demo.core.detection import DetectionFrame
    f = fixture_runtime(tmp_path, monkeypatch)
    f.runtime.start()
    frame = DetectionFrame(np.zeros((2, 3, 3), dtype=np.uint8), 1250000000, 'camera')
    results = smoke_models(f.runtime, frame, clock=iter([10., 10.25, 10.25, 10.75]).__next__)
    assert results['plastic-cup-yolo11n-seg-v1']['latency_ms'] == 250.
    assert results['grounded-sam']['latency_ms'] == 500.
    assert all(item['outcome'] == 'QUALIFIED' for item in results.values())
    assert results['grounded-sam']['model_provenance'] == {'backend': 'grounded_sam'}
    assert json.loads(json.dumps(results, allow_nan=False)) == results


@pytest.mark.parametrize('clock_values', [[1., float('nan')], [1., .5],
                                         [True], [float('inf')], [1.], [1., 2., 1.]])
def test_smoke_clock_fault_has_no_valid_timing_receipt(tmp_path, monkeypatch, clock_values):
    from so101_demo.cli.parallel_perception_broker import smoke_models
    from so101_demo.adapters.perception.errors import ModelRuntimeInfrastructureError
    from so101_demo.core.detection import DetectionFrame
    f = fixture_runtime(tmp_path, monkeypatch)
    f.runtime.start()
    frame = DetectionFrame(np.zeros((2, 3, 3), dtype=np.uint8), 1250000000, 'camera')
    with pytest.raises(ModelRuntimeInfrastructureError, match='CLOCK'):
        smoke_models(f.runtime, frame, clock=iter(clock_values).__next__)
    assert not f.runtime.healthy


@pytest.mark.parametrize('kind', ['deterministic', 'infrastructure'])
def test_smoke_exceptions_are_attributed_with_latency(tmp_path, monkeypatch, kind):
    from so101_demo.cli.parallel_perception_broker import smoke_models
    from so101_demo.adapters.perception.errors import DeterministicModelResultError
    from so101_demo.core.detection import DetectionFrame
    failure = DeterministicModelResultError('schema') if kind == 'deterministic' else RuntimeError('CUDA OOM')
    f = fixture_runtime(tmp_path, monkeypatch, failure=failure)
    f.runtime.start()
    frame = DetectionFrame(np.zeros((2, 3, 3), dtype=np.uint8), 1250000000, 'camera')
    results = smoke_models(f.runtime, frame, clock=iter([1., 1.125, 1.25, 1.5]).__next__)
    assert results['plastic-cup-yolo11n-seg-v1']['latency_ms'] == 125.
    assert results['grounded-sam']['latency_ms'] == 250.
    expected = 'MODEL_ERROR' if kind == 'deterministic' else 'INFRA_ERROR'
    assert [v['outcome'] for v in results.values()] == [expected, expected]
    assert f.runtime.healthy is (kind == 'deterministic')
    assert sum(c[0] == 'detect' for c in f.calls) == (2 if kind == 'deterministic' else 1)
    json.dumps(results, allow_nan=False)


def test_second_smoke_model_infra_does_not_hide_behind_first_success(tmp_path, monkeypatch):
    from so101_demo.cli.parallel_perception_broker import smoke_models
    from so101_demo.runtime.parallel_perception_runtime import GROUNDED_ID
    from so101_demo.core.detection import DetectionFrame
    f = fixture_runtime(tmp_path, monkeypatch)
    f.runtime.start()
    def fail(frame, query):
        raise RuntimeError('second model CUDA OOM')
    f.runtime.detectors[GROUNDED_ID].detector.detect = fail
    frame = DetectionFrame(np.zeros((2, 3, 3), dtype=np.uint8), 1250000000, 'camera')
    results = smoke_models(f.runtime, frame, clock=iter([1., 2., 2., 3.]).__next__)
    assert results[f.req.model_id]['outcome'] == 'QUALIFIED'
    assert results[GROUNDED_ID]['outcome'] == 'INFRA_ERROR'
    assert all(item['executed'] and item['latency_ms'] == 1000. for item in results.values())
    assert not f.runtime.healthy


def test_transport_serve_failure_poison_runtime(tmp_path, monkeypatch):
    from so101_demo.cli import parallel_perception_broker as cli
    f = fixture_runtime(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, 'ParallelPerceptionRuntime', lambda **kwargs: f.runtime)
    pins = dict(pin.split('==') for pin in cli.PINS)
    monkeypatch.setattr(cli.importlib.metadata, 'version', pins.__getitem__)
    monkeypatch.setenv('PARALLEL_IMAGE_ID', 'sha256:' + 'b' * 64)
    read_bytes = Path.read_bytes
    provenance = {'source_sha256': 'c' * 64, 'verified_source_sha256': 'c' * 64}
    monkeypatch.setattr(Path, 'read_bytes', lambda path: cli.canonical_json(provenance)
                        if str(path) == '/opt/parallel-provenance.json' else read_bytes(path))
    monkeypatch.setattr(cli, 'verify_source', lambda package, expected: expected)
    def serve(runtime, *, endpoint):
        assert runtime.healthy and endpoint == Path('/runtime/perception.sock')
        raise ConnectionError('transport closed')
    with pytest.raises(ConnectionError, match='transport closed'):
        cli.main(cli.broker_argv(), transport=SimpleNamespace(serve=serve), authorize=lambda *args: True)
    assert not f.runtime.healthy


def test_container_entry_installs_task11_transport_from_exact_runtime_spec(
    tmp_path, monkeypatch
):
    from so101_demo.cli import parallel_perception_broker as cli
    from so101_demo.runtime import parallel_ipc

    f = fixture_runtime(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, 'ParallelPerceptionRuntime', lambda **kwargs: f.runtime)
    pins = dict(pin.split('==') for pin in cli.PINS)
    monkeypatch.setattr(cli.importlib.metadata, 'version', pins.__getitem__)
    monkeypatch.setenv('PARALLEL_IMAGE_ID', 'sha256:' + 'b' * 64)
    read_bytes = Path.read_bytes
    provenance = {'source_sha256': 'c' * 64, 'verified_source_sha256': 'c' * 64}
    monkeypatch.setattr(
        Path,
        'read_bytes',
        lambda path: cli.canonical_json(provenance)
        if str(path) == '/opt/parallel-provenance.json'
        else read_bytes(path),
    )
    monkeypatch.setattr(cli, 'verify_source', lambda package, expected: expected)
    calls = []

    class Transport:
        def authorize(self, request, snapshot):
            calls.append(('authorize', request, snapshot))
            return True

        def serve(self, runtime, *, endpoint):
            calls.append(('serve', runtime, endpoint))
            return 0

    monkeypatch.setattr(
        parallel_ipc,
        'build_broker_transport',
        lambda runtime_spec: calls.append(('build', runtime_spec)) or Transport(),
        raising=False,
    )

    assert cli.main(cli.broker_argv()) == 0
    assert calls[0] == ('build', Path('/runtime/broker-spec.json'))
    assert calls[1] == ('serve', f.runtime, Path('/runtime/perception.sock'))


@pytest.mark.parametrize('phase', ['submit', 'dispatch', 'completion'])
@pytest.mark.parametrize('error_type', [ConnectionError, TimeoutError])
def test_authority_failure_is_infrastructure_at_every_boundary(tmp_path, monkeypatch, phase, error_type):
    from so101_demo.runtime.parallel_perception_runtime import PerceptionService
    from so101_demo.parallel_batch.contracts import ModelOutcome, load_parallel_runtime_config
    f = fixture_runtime(tmp_path, monkeypatch)
    config = load_parallel_runtime_config(Path(__file__).parents[1] / 'config/mujoco/parallel_batch_v1.yaml')
    service = PerceptionService(f.runtime, config, generation=1)
    service.start()
    failed = [phase == 'submit']
    def authorize(request, snapshot):
        if failed[0]:
            raise error_type('authority unavailable')
        return True
    f.runtime.authorize = authorize
    submission = service.submit(f.req, f.snapshot)
    if phase == 'dispatch':
        failed[0] = True
    elif phase == 'completion':
        detector = f.runtime.detectors[f.req.model_id].detector
        detect = detector.detect
        def complete(frame, query):
            batch = detect(frame, query)
            failed[0] = True
            return batch
        detector.detect = complete
    if submission.accepted:
        service.run_next()
    response = service.broker.poll_response(f.req)
    assert response.outcome is ModelOutcome.INFRA_ERROR
    assert not service.broker.healthy
    assert not f.runtime.healthy


@pytest.mark.parametrize('running', [False, True])
def test_dispatch_scan_timeout_poison_health_even_without_returned_result(tmp_path, monkeypatch, running):
    from so101_demo.runtime.parallel_perception_runtime import PerceptionService
    from so101_demo.parallel_batch.contracts import ModelOutcome, load_parallel_runtime_config
    f = fixture_runtime(tmp_path, monkeypatch)
    config = load_parallel_runtime_config(Path(__file__).parents[1] / 'config/mujoco/parallel_batch_v1.yaml')
    now = [1.]
    service = PerceptionService(f.runtime, config, generation=1, clock=lambda: now[0])
    service.start()
    assert service.submit(f.req, f.snapshot).accepted
    if running:
        assert service.broker.next_ready_request() == f.req
    now[0] = 22.
    assert service.run_next() is None
    assert service.broker.poll_response(f.req).outcome is (
        ModelOutcome.INFERENCE_TIMEOUT if running else ModelOutcome.QUEUE_TIMEOUT)
    assert not f.runtime.healthy
    assert not service.broker.healthy
    assert not service.submit(replace(f.req, request_id='next'), f.snapshot).accepted


@pytest.mark.parametrize('outcome', [
    'INFRA_ERROR', 'QUEUE_TIMEOUT', 'INFERENCE_TIMEOUT',
])
def test_health_losing_response_reports_one_exact_event(
        tmp_path, monkeypatch, outcome):
    from so101_demo.parallel_batch.contracts import (
        ModelOutcome, load_parallel_runtime_config,
    )
    from so101_demo.runtime.parallel_perception_runtime import PerceptionService

    f = fixture_runtime(tmp_path, monkeypatch)
    config = load_parallel_runtime_config(
        Path(__file__).parents[1] / 'config/mujoco/parallel_batch_v1.yaml'
    )
    events = []
    service = PerceptionService(
        f.runtime,
        config,
        generation=7,
        health_down=lambda event: events.append(event) or True,
    )
    response = SimpleNamespace(
        request=f.req,
        outcome=ModelOutcome(outcome),
        reason='deterministic failure',
    )

    service._response_health(response)
    service._response_health(response)

    assert events == [{
        'outcome': outcome,
        'request_id': f.req.request_id,
        'reason': 'deterministic failure',
    }]


@pytest.mark.parametrize('bad', ['missing_masks', 'string_mask', 'string_box', 'string_class',
                               'string_conf', 'ragged_box', 'missing_boxes', 'class_mapping',
                               'transfer_oom', 'transfer_type_error'])
def test_yolo_completed_schema_vs_tensor_transfer_boundary(tmp_path, monkeypatch, bad):
    from so101_demo.adapters.perception.yolo_seg import YoloSegDetector
    from so101_demo.parallel_batch.contracts import ModelOutcome
    f = fixture_runtime(tmp_path, monkeypatch)
    f.runtime.start()
    result = SimpleNamespace(boxes=SimpleNamespace(xyxy=np.array([[0., 0., 3., 2.]]),
                                                  cls=np.array([0.]), conf=np.array([.9])),
                             masks=SimpleNamespace(data=np.ones((1, 2, 3))))
    if bad == 'missing_masks': del result.masks
    if bad == 'missing_boxes': del result.boxes
    if bad == 'string_mask': result.masks.data = np.array([[['x'] * 3] * 2])
    if bad == 'string_box': result.boxes.xyxy = np.array([['x', '0', '3', '2']])
    if bad == 'string_class': result.boxes.cls = np.array(['x'])
    if bad == 'string_conf': result.boxes.conf = np.array(['x'])
    if bad == 'ragged_box': result.boxes.xyxy = [[0, 0, 3, 2], [0, 1]]
    if bad.startswith('transfer_'):
        class Transfer:
            def cpu(self):
                if bad == 'transfer_oom': raise RuntimeError('CUDA OOM')
                raise TypeError('tensor transfer failed')
        result.boxes.xyxy = Transfer()
    detector = object.__new__(YoloSegDetector)
    detector._model = SimpleNamespace(predict=lambda **kwargs: [result])
    detector._imgsz, detector.runtime_device = 640, 'cuda'
    detector._monotonic_ns = lambda: 1
    detector._model_id, detector._weights_sha256 = 'yolo', 'a' * 64
    detector._class_names = None if bad == 'class_mapping' else {0: 'plastic_cup'}
    f.runtime.detectors[f.req.model_id] = replace(f.runtime.detectors[f.req.model_id], detector=detector)
    expected = ModelOutcome.INFRA_ERROR if bad.startswith('transfer_') else ModelOutcome.MODEL_ERROR
    assert f.runtime.infer(f.req, f.snapshot).outcome is expected
    assert f.runtime.healthy is (expected is ModelOutcome.MODEL_ERROR)


@pytest.mark.parametrize('phase,expected,calls_expected', [
    ('grounding_pre', 'INFRA_ERROR', {'grounding': 0, 'sam': 0}),
    ('grounding_post', 'MODEL_ERROR', {'grounding': 1, 'sam': 0}),
    ('sam_pre', 'INFRA_ERROR', {'grounding': 1, 'sam': 0}),
    ('sam_post', 'MODEL_ERROR', {'grounding': 1, 'sam': 1}),
])
def test_grounded_preparation_is_not_a_completed_model_result(tmp_path, monkeypatch, phase, expected, calls_expected):
    from contextlib import nullcontext
    from so101_demo.adapters.perception.grounded_sam import GroundedSamDetector
    from so101_demo.adapters.perception.grounded_sam_postprocess import GroundedSamThresholds
    f = fixture_runtime(tmp_path, monkeypatch)
    f.runtime.start()
    calls = {'grounding': 0, 'sam': 0}
    class GroundingProcessor:
        def __call__(self, **kwargs):
            return {} if phase == 'grounding_pre' else {'input_ids': np.array([[1]])}
        def post_process_grounded_object_detection(self, *args, **kwargs):
            return [{}] if phase == 'grounding_post' else [{
                'boxes': np.array([[0., 0., 3., 2.]]), 'scores': np.array([.9]),
                'text_labels': ['plastic cup']}]
    class SamProcessor:
        def __call__(self, **kwargs):
            return {} if phase == 'sam_pre' else {'original_sizes': np.array([[2, 3]])}
        def post_process_masks(self, *args, **kwargs):
            return []
    def grounding_model(**kwargs):
        calls['grounding'] += 1
        return SimpleNamespace()
    def sam_model(**kwargs):
        calls['sam'] += 1
        return SimpleNamespace()
    detector = object.__new__(GroundedSamDetector)
    detector._monotonic_ns = lambda: 1
    detector._torch = SimpleNamespace(inference_mode=nullcontext)
    detector._prompt_profile = {'plastic_cup': 'plastic cup.'}
    detector._thresholds = GroundedSamThresholds.defaults()
    detector._grounding_processor, detector._sam_processor = GroundingProcessor(), SamProcessor()
    detector._grounding_model, detector._sam_model = grounding_model, sam_model
    detector.runtime_device, detector.target_class_id = 'cuda', 'plastic_cup'
    f.runtime.detectors[f.req.model_id] = replace(f.runtime.detectors[f.req.model_id], detector=detector)
    assert f.runtime.infer(f.req, f.snapshot).outcome.value == expected
    assert calls == calls_expected
