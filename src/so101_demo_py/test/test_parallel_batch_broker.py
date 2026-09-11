"""Behavioral gates for scheduling, backpressure and stale candidate fencing."""

from dataclasses import replace
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from so101_demo.parallel_batch.contracts import (
    ExecutionKind, InferenceRequest, load_parallel_runtime_config, ModelOutcome,
)


YOLO = 'plastic-cup-yolo11n-seg-v1'
GROUNDED = 'grounded-sam'


def req(worker='worker-01', request_id='a', *, model=YOLO, generation=1, **changes):
    values = {'request_id': request_id, 'model_id': model,
              'execution_kind': ExecutionKind.ATTEMPT, 'batch_id': 'batch-1',
              'coordinator_epoch': 1, 'worker_id': worker, 'worker_generation': generation,
              'point_id': 'point-1', 'lease_generation': 1, 'reset_epoch': 'reset-1',
              'image_timestamp_s': 1000.0,
              'input_relative_path': f'{worker}/attempts/point-1/attempt-1/input.npy',
              'input_sha256': 'a' * 64, 'attempt_id': 'attempt-1'}
    return InferenceRequest(**(values | changes))


def model_result(outcome=ModelOutcome.NORMAL_REJECTION):
    from so101_demo.parallel_batch.broker import ModelResult
    return ModelResult(outcome, {'mask': [1, 2]} if outcome == ModelOutcome.QUALIFIED else None)


def harness(*, ready=True, detectors=None, authorize=None):
    from so101_demo.parallel_batch.broker import PerceptionBroker
    control = SimpleNamespace(now=100.0, authorized=True)
    config = load_parallel_runtime_config(
        Path(__file__).resolve().parents[1] / 'config/mujoco/parallel_batch_v1.yaml')
    broker = PerceptionBroker(config, grounded_model_id=GROUNDED,
                              authorize=authorize or (lambda r: control.authorized),
                              clock=lambda: control.now, detectors=detectors)
    if ready:
        broker.set_model_ready(YOLO, True)
        broker.set_model_ready(GROUNDED, True)
    return broker, control


def enqueue(broker, request):
    assert broker.submit(request).accepted is True
    return request


def start(broker, request):
    enqueue(broker, request)
    assert broker.next_ready_request() == request
    return request


def test_round_robin_prevents_one_worker_monopoly():
    broker, _ = harness()
    first = enqueue(broker, req())
    other = enqueue(broker, req('worker-02', 'c'))
    assert broker.next_ready_request() == first
    broker.complete(first, model_result())
    later = enqueue(broker, req(request_id='b'))
    assert broker.next_ready_request() == other
    broker.complete(other, model_result())
    assert broker.next_ready_request() == later


def test_model_round_robin_allows_grounded_before_yolo_refill():
    broker, _ = harness()
    yolo = enqueue(broker, req())
    grounded = enqueue(broker, req('worker-02', 'g', model=GROUNDED))
    assert broker.next_ready_request() == yolo
    broker.complete(yolo, model_result())
    enqueue(broker, req(request_id='b'))
    assert broker.next_ready_request() == grounded


@pytest.mark.parametrize('running', [False, True])
def test_queued_and_running_each_block_same_worker_model(running):
    broker, _ = harness()
    request = enqueue(broker, req())
    if running:
        assert broker.next_ready_request() == request
    rejected = broker.submit(req(request_id='second', generation=2))
    assert rejected.accepted is False
    assert rejected.reason == 'WORKER_MODEL_INFLIGHT'
    assert broker.submit(req(request_id='grounded', model=GROUNDED)).accepted is True


def test_queue_capacity_is_three_per_model_six_total_without_eviction():
    broker, _ = harness()
    queued = []
    for model in (YOLO, GROUNDED):
        for index in range(3):
            queued.append(enqueue(broker, req(f'worker-0{index + 1}', f'{model}-{index}',
                                              model=model)))
        rejected = broker.submit(req('worker-04', f'{model}-overflow', model=model))
        assert rejected.accepted is False
        assert rejected.reason == 'QUEUE_FULL'
    observed = []
    for _ in range(6):
        request = broker.next_ready_request()
        assert request is not None
        observed.append(request)
        broker.complete(request, model_result())
    assert set(observed) == set(queued)


def test_duplicate_submit_does_not_reset_queue_deadline():
    broker, clock = harness()
    request = enqueue(broker, req())
    clock.now = 109.0
    assert broker.submit(request).accepted is True
    clock.now = 110.0
    assert broker.next_ready_request() is None
    response = broker.poll_response(request)
    assert response.outcome == ModelOutcome.QUEUE_TIMEOUT
    assert response.candidate is None
    assert response.queue_deadline_monotonic_s == 110.0
    assert response.started_monotonic_s is None


@pytest.mark.parametrize(('model', 'timeout'), [(YOLO, 20), (GROUNDED, 60)])
def test_inference_deadline_starts_at_dispatch_and_never_returns_late_candidate(model, timeout):
    broker, clock = harness()
    request = enqueue(broker, req(model=model))
    clock.now = 109.0
    assert broker.next_ready_request() == request
    clock.now = 109.0 + timeout
    response = broker.complete(request, model_result(ModelOutcome.QUALIFIED))
    assert response.outcome == ModelOutcome.INFERENCE_TIMEOUT
    assert response.candidate is None
    assert response.inference_deadline_monotonic_s == 109.0 + timeout
    assert broker.complete(request, model_result()).outcome == ModelOutcome.INFERENCE_TIMEOUT


def test_completion_before_deadline_returns_candidate_once_and_replays_first_result():
    broker, clock = harness()
    request = start(broker, req())
    clock.now = 119.9
    response = broker.complete(request, model_result(ModelOutcome.QUALIFIED))
    assert response.outcome == ModelOutcome.QUALIFIED
    assert response.candidate == {'mask': [1, 2]}
    assert response.request == request
    assert response.identity.worker_id == 'worker-01'
    assert response.broker_generation == 1
    assert broker.complete(request, model_result()) == response
    assert broker.submit(request).response == response
    assert broker.next_ready_request() is None


@pytest.mark.parametrize('running', [False, True])
def test_cancelled_generation_is_permanent_even_for_new_request_ids(running):
    broker, _ = harness()
    request = enqueue(broker, req())
    if running:
        assert broker.next_ready_request() == request
    broker.cancel_generation('worker-01', 1)
    response = broker.complete(request, model_result(ModelOutcome.QUALIFIED))
    assert response is not None
    assert response.outcome == ModelOutcome.CANCELLED
    assert response.candidate is None
    assert broker.submit(req(request_id='fresh-id')).accepted is False
    assert broker.submit(req(request_id='new-generation', generation=2)).accepted is True


def test_cancel_before_first_submit_fences_generation():
    broker, _ = harness()
    broker.cancel_generation('worker-01', 1)
    result = broker.submit(req())
    assert result.accepted is False
    assert result.reason == 'GENERATION_FENCED'


@pytest.mark.parametrize('completed', [False, True])
def test_restart_fences_old_requests_including_cached_candidates(completed):
    broker, _ = harness()
    request = start(broker, req())
    if completed:
        assert broker.complete(request, model_result(ModelOutcome.QUALIFIED)).candidate
    assert broker.restart() == 2
    assert broker.healthy is False
    broker.set_model_ready(YOLO, True)
    broker.set_model_ready(GROUNDED, True)
    response = broker.complete(request, model_result(ModelOutcome.QUALIFIED))
    assert response.outcome == ModelOutcome.CANCELLED
    assert response.candidate is None
    assert response.broker_generation == 1
    assert broker.submit(request).accepted is False
    assert broker.submit(req(request_id='after-restart')).accepted is True


def test_health_requires_both_models_and_loss_invalidates_pending_work():
    broker, _ = harness(ready=False)
    assert broker.submit(req()).accepted is False
    broker.set_model_ready(YOLO, True)
    assert broker.healthy is False
    broker.set_model_ready(GROUNDED, True)
    assert broker.healthy is True
    request = start(broker, req(request_id='running'))
    queued = enqueue(broker, req('worker-02', 'queued', model=GROUNDED))
    broker.set_model_ready(GROUNDED, False)
    assert broker.healthy is False
    assert broker.complete(request, model_result(ModelOutcome.QUALIFIED)).outcome == (
        ModelOutcome.INFRA_ERROR)
    assert broker.poll_response(queued).outcome == ModelOutcome.INFRA_ERROR
    broker.set_model_ready(GROUNDED, True)
    assert broker.complete(request, model_result(ModelOutcome.QUALIFIED)).candidate is None


@pytest.mark.parametrize('boundary', ['submit', 'dispatch', 'complete', 'replay'])
def test_lease_is_rechecked_and_loss_permanently_fences_request(boundary):
    broker, clock = harness()
    request = req()
    if boundary != 'submit':
        enqueue(broker, request)
    if boundary in ('complete', 'replay'):
        assert broker.next_ready_request() == request
    if boundary == 'replay':
        assert broker.complete(request, model_result(ModelOutcome.QUALIFIED)).candidate
    clock.authorized = False
    if boundary == 'submit':
        assert broker.submit(request).reason == 'REQUEST_NOT_AUTHORIZED'
    elif boundary == 'dispatch':
        assert broker.next_ready_request() is None
    else:
        assert broker.complete(request, model_result(ModelOutcome.QUALIFIED)).candidate is None
    clock.authorized = True
    assert broker.submit(request).accepted is False


def test_identity_collision_cannot_complete_or_replace_original():
    from so101_demo.parallel_batch.broker import BrokerError
    broker, _ = harness()
    request = start(broker, req())
    forged = replace(request, input_sha256='b' * 64)
    with pytest.raises(BrokerError, match='REQUEST_IDENTITY_MISMATCH'):
        broker.submit(forged)
    with pytest.raises(BrokerError, match='REQUEST_IDENTITY_MISMATCH'):
        broker.complete(forged, model_result(ModelOutcome.QUALIFIED))
    assert broker.complete(request, model_result()).outcome == ModelOutcome.NORMAL_REJECTION


def test_undispatched_result_is_rejected_without_consuming_queue():
    from so101_demo.parallel_batch.broker import BrokerError
    broker, _ = harness()
    request = enqueue(broker, req())
    with pytest.raises(BrokerError, match='REQUEST_NOT_RUNNING'):
        broker.complete(request, model_result(ModelOutcome.QUALIFIED))
    assert broker.next_ready_request() == request


def test_detector_exception_is_infrastructure_failure_and_marks_unhealthy():
    def broken(request):
        raise RuntimeError('CUDA context lost')
    broker, _ = harness(detectors={YOLO: broken, GROUNDED: broken})
    enqueue(broker, req())
    response = broker.run_next()
    assert response is not None
    assert response.outcome == ModelOutcome.INFRA_ERROR
    assert response.candidate is None
    assert broker.healthy is False


def test_injected_detector_result_obeys_same_generation_fence():
    def detector(request):
        broker.restart()
        return model_result(ModelOutcome.QUALIFIED)
    broker, _ = harness(detectors={YOLO: detector, GROUNDED: detector})
    enqueue(broker, req())
    response = broker.run_next()
    assert response.outcome == ModelOutcome.CANCELLED
    assert response.candidate is None


def test_authorization_callback_restart_cannot_let_old_candidate_escape():
    broker, _ = harness()
    request = start(broker, req())

    def authorize(value):
        broker.restart()
        return True
    broker._authorize = authorize
    response = broker.complete(request, model_result(ModelOutcome.QUALIFIED))
    assert response.outcome == ModelOutcome.CANCELLED
    assert response.candidate is None


def test_health_loss_fences_cached_candidate_even_after_recovery():
    broker, _ = harness()
    request = start(broker, req())
    assert broker.complete(request, model_result(ModelOutcome.QUALIFIED)).candidate
    broker.set_model_ready(GROUNDED, False)
    broker.set_model_ready(GROUNDED, True)
    response = broker.poll_response(request)
    assert response.outcome == ModelOutcome.INFRA_ERROR
    assert response.candidate is None


def test_authorization_transport_failure_marks_broker_unhealthy():
    def unavailable(request):
        raise ConnectionError('coordinator unavailable')
    broker, _ = harness(authorize=unavailable)
    response = broker.submit(req())
    assert response.accepted is False
    assert response.response.outcome == ModelOutcome.INFRA_ERROR
    assert broker.healthy is False


def test_timeout_poll_and_cancel_stay_responsive_while_detector_is_blocked():
    entered, release, cancelled = threading.Event(), threading.Event(), threading.Event()
    results = []

    def detector(request):
        entered.set()
        assert release.wait(3)
        return model_result(ModelOutcome.QUALIFIED)
    broker, clock = harness(detectors={YOLO: detector})
    request = enqueue(broker, req())
    runner = threading.Thread(target=lambda: results.append(broker.run_next()))
    runner.start()
    try:
        assert entered.wait(1)
        clock.now = 120
        assert broker.poll_response(request).outcome == ModelOutcome.INFERENCE_TIMEOUT

        def cancel():
            broker.cancel_generation('worker-01', 1)
            cancelled.set()
        canceller = threading.Thread(target=cancel)
        canceller.start()
        assert cancelled.wait(1)
        canceller.join(1)
    finally:
        release.set()
        runner.join(3)
    assert not runner.is_alive()
    assert results[0].outcome == ModelOutcome.CANCELLED
    assert results[0].candidate is None


def test_result_mutation_cannot_change_cached_response():
    broker, _ = harness()
    request = start(broker, req())
    result = model_result(ModelOutcome.QUALIFIED)
    response = broker.complete(request, result)
    result.candidate['mask'].append(3)
    response.candidate['mask'].append(4)
    assert broker.poll_response(request).candidate == {'mask': [1, 2]}


@pytest.mark.parametrize('ready', ['true', 1, None])
def test_ready_requires_literal_boolean(ready):
    from so101_demo.parallel_batch.broker import BrokerError
    broker, _ = harness(ready=False)
    with pytest.raises(BrokerError, match='MODEL_READY_CONTRACT'):
        broker.set_model_ready(YOLO, ready)
    assert broker.healthy is False


def test_authorization_requires_literal_true():
    broker, _ = harness(authorize=lambda request: 'yes')
    assert broker.submit(req()).accepted is False


def test_missing_or_malformed_detector_result_is_infra_not_normal_rejection():
    broker, _ = harness(detectors={YOLO: lambda request: {'outcome': 'QUALIFIED'}})
    enqueue(broker, req())
    assert broker.run_next().outcome == ModelOutcome.INFRA_ERROR
    assert broker.healthy is False


def test_monotonic_clock_regression_cannot_return_candidate():
    from so101_demo.parallel_batch.broker import BrokerError
    broker, clock = harness()
    request = start(broker, req())
    clock.now = 99.0
    with pytest.raises(BrokerError, match='MONOTONIC_CLOCK_REGRESSION'):
        broker.complete(request, model_result(ModelOutcome.QUALIFIED))
    assert broker.healthy is False


def test_completion_crossing_deadline_during_result_copy_has_no_candidate():
    broker, clock = harness()
    request = start(broker, req())

    class SlowCandidate(dict):
        def __deepcopy__(self, memo):
            clock.now = 120.0
            return {'mask': [1, 2]}

    from so101_demo.parallel_batch.broker import ModelResult
    clock.now = 119.0
    response = broker.complete(request, ModelResult(ModelOutcome.QUALIFIED, SlowCandidate()))
    assert response.outcome == ModelOutcome.INFERENCE_TIMEOUT
    assert response.candidate is None
