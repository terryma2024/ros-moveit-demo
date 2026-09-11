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
