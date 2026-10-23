"""Catch excess inflight work, premature timeout release and executor replacement."""

import copy
import importlib
import threading
import time

import pytest

from test_config_identity import campaign_fixture
from test_contract import request_document, response_document


class EventExecutor:
    """Replace external model execution, keeping real scheduling and replies."""

    def __init__(self, index, config, gates, started, calls):
        self.index = index
        self._alive = True
        self.gates, self.started, self.calls = gates, started, calls
        self.ready = {"runtime_device": "cuda", "gpu_uuid": "GPU-selected"}
        self.failure = None
        self.batch = None

    def alive(self):
        return self._alive

    def infer(self, request, payload):
        key = request["request_id"]
        self.calls.append((self.index, key, payload))
        self.started.setdefault(key, threading.Event()).set()
        if self.failure is not None:
            raise self.failure
        gate = self.gates.get(key)
        if gate is not None and not gate.wait(3):
            raise RuntimeError("test executor gate not released")
        document = copy.deepcopy(self.batch) if self.batch is not None else response_document()["batch"]
        return document

    def close(self):
        self._alive = False
        return True


def service_fixture(tmp_path, *, instances=1, limit=8, inference_timeout_s=1, classes=None):
    config = campaign_fixture(tmp_path)["teacher_service"]
    config.update(instances=instances, max_inflight_requests=limit,
                  inference_timeout_s=inference_timeout_s, queue_timeout_s=1)
    config["model"]["model_id"] = "cup-model"
    config["model"]["weights"]["sha256"] = "a" * 64
    if classes is not None:
        config["model"]["classes"] = classes
    gates, started, calls, executors = {}, {}, [], []
    def factory(index, config):
        executor = EventExecutor(index, config, gates, started, calls)
        executors.append(executor)
        return executor
    module = importlib.import_module("so101_demo.runtime.inference.service")
    service = module.InferenceService(config=config, executor_factory=factory,
        monotonic_ns=time.monotonic_ns, generation="g1", gpu_uuid="GPU-selected")
    service.start()
    return service, gates, started, calls, executors


def submit(service, request_id, *, deadline_ns=None):
    request = request_document() | {"request_id": request_id,
        "deadline_monotonic_ns": deadline_ns or time.monotonic_ns() + 2_000_000_000}
    return service.submit(request, bytes(range(18)), None)


def read(ticket, *, timeout=2):
    document = ticket.response.result(timeout=timeout)
    ticket.delivery_complete()
    return document


def wait_until(predicate):
    deadline = time.monotonic() + 2
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("condition not reached")
        threading.Event().wait(0.002)


def test_all_three_configured_instances_load_and_single_instance_is_serial(tmp_path):
    service, gates, started, calls, executors = service_fixture(tmp_path, instances=3)
    try:
        ready = service.query({"schema_version": 1, "kind": "service_ready", "request_id": "q"})
        assert (ready["configured_instances"], ready["loaded_instances"], ready["ready"]) == (3, 3, True)
        for key in ("r0", "r1", "r2", "r3"):
            gates[key] = threading.Event()
        tickets = [submit(service, key) for key in gates]
        wait_until(lambda: len(calls) == 3)
        assert len({index for index, _, _ in calls}) == 3
        assert not started.get("r3", threading.Event()).is_set()
        gates["r0"].set()
        wait_until(lambda: len(calls) == 4)
        for gate in gates.values(): gate.set()
        assert all(read(ticket)["outcome"] == "DETECTED" for ticket in tickets)
    finally:
        for gate in gates.values(): gate.set()
        assert service.close()["terminated"] is True


def test_queue_full_duplicate_and_completed_id_release(tmp_path):
    service, gates, started, calls, _ = service_fixture(tmp_path, limit=1)
    gates["r"] = threading.Event()
    try:
        first = submit(service, "r")
        wait_until(lambda: started.get("r", threading.Event()).is_set())
        duplicate = read(submit(service, "r"))
        assert (duplicate["outcome"], duplicate["reason"]) == ("INPUT_INVALID", "DUPLICATE_REQUEST")
        assert read(submit(service, "another"))["outcome"] == "QUEUE_FULL"
        assert len(calls) == 1
        gates["r"].set()
        assert read(first)["outcome"] == "DETECTED"
        wait_until(lambda: service.inflight_count == 0)
        assert read(submit(service, "r"))["outcome"] == "DETECTED"
        assert len(calls) == 2
    finally:
        gates["r"].set()
        service.close()


def test_running_timeout_does_not_release_cuda_slot_until_actual_completion(tmp_path):
    service, gates, started, calls, _ = service_fixture(tmp_path, limit=1, inference_timeout_s=0.05)
    gates["r"] = threading.Event()
    try:
        ticket = submit(service, "r")
        wait_until(lambda: started.get("r", threading.Event()).is_set())
        assert read(ticket)["outcome"] == "INFERENCE_TIMEOUT"
        assert service.inflight_count == 1
        assert read(submit(service, "new"))["outcome"] == "QUEUE_FULL"
        gates["r"].set()
        wait_until(lambda: service.inflight_count == 0)
        assert len(calls) == 1
        assert ticket.response.result()["outcome"] == "INFERENCE_TIMEOUT"
    finally:
        gates["r"].set()
        service.close()


def test_pending_delivery_and_receiving_both_count_against_limit(tmp_path):
    service, _, _, _, _ = service_fixture(tmp_path, limit=1)
    try:
        reservation = service.reserve_receiving()
        assert service.inflight_count == 1
        assert read(submit(service, "r"))["outcome"] == "QUEUE_FULL"
        reservation.close()
        ticket = submit(service, "r")
        assert ticket.response.result(timeout=2)["outcome"] == "DETECTED"
        assert service.inflight_count == 1
        assert read(submit(service, "new"))["outcome"] == "QUEUE_FULL"
        ticket.delivery_complete()
        wait_until(lambda: service.inflight_count == 0)
    finally:
        service.close()


def test_expired_queued_request_does_not_reach_model(tmp_path):
    service, gates, started, calls, _ = service_fixture(tmp_path, limit=2)
    gates["r"] = threading.Event()
    try:
        first = submit(service, "r")
        wait_until(lambda: started.get("r", threading.Event()).is_set())
        expired = submit(service, "expired", deadline_ns=time.monotonic_ns() - 1)
        assert read(expired)["outcome"] == "QUEUE_TIMEOUT"
        assert [key for _, key, _ in calls] == ["r"]
        gates["r"].set()
        read(first)
    finally:
        gates["r"].set()
        service.close()


def test_executor_death_is_permanent_service_fault_without_replacement(tmp_path):
    service, _, _, _, executors = service_fixture(tmp_path, instances=3)
    try:
        executors[1]._alive = False
        wait_until(lambda: service.query({"schema_version": 1, "kind": "service_health",
                                        "request_id": "q"})["available"] is False)
        response = read(submit(service, "r"))
        assert response["outcome"] == "INFRA_ERROR"
        assert response["reason"] == "INFERENCE_EXECUTOR_EXITED"
        assert len(executors) == 3
    finally:
        service.close()


def test_disconnected_timeout_reply_keeps_running_slot(tmp_path):
    service, gates, started, _, _ = service_fixture(tmp_path, limit=1)
    gates["r"] = threading.Event()
    try:
        ticket = submit(service, "r")
        wait_until(lambda: started.get("r", threading.Event()).is_set())
        ticket.disconnect()
        assert service.inflight_count == 1
        gates["r"].set()
        wait_until(lambda: service.inflight_count == 0)
    finally:
        gates["r"].set()
        service.close()


def test_expired_queued_slot_can_accept_new_work_before_running_job_finishes(tmp_path):
    service, gates, started, calls, _ = service_fixture(tmp_path, limit=2)
    gates["running"] = threading.Event()
    try:
        running = submit(service, "running")
        wait_until(lambda: started.get("running", threading.Event()).is_set())
        expiring = submit(service, "expiring", deadline_ns=time.monotonic_ns() + 30_000_000)
        assert read(expiring)["outcome"] == "QUEUE_TIMEOUT"
        wait_until(lambda: service.inflight_count == 1)
        # Expired queue entries cannot exhaust physical queue capacity after slots release.
        another = submit(service, "another", deadline_ns=time.monotonic_ns() + 30_000_000)
        assert read(another)["outcome"] == "QUEUE_TIMEOUT"
        replacement = submit(service, "replacement")
        gates["running"].set()
        assert read(running)["outcome"] == "DETECTED"
        assert read(replacement)["outcome"] == "DETECTED"
        assert [key for _, key, _ in calls] == ["running", "replacement"]
    finally:
        gates["running"].set()
        service.close()


def test_infrastructure_exception_is_not_a_deterministic_model_failure(tmp_path):
    from so101_demo.adapters.perception.errors import ModelRuntimeInfrastructureError
    service, _, _, _, executors = service_fixture(tmp_path)
    try:
        executors[0].failure = ModelRuntimeInfrastructureError("CUDA_DEVICE_FAILED")
        response = read(submit(service, "r"))
        assert response["outcome"] == "INFRA_ERROR"
        assert "CUDA_DEVICE_FAILED" in response["reason"]
        assert service.query({"schema_version": 1, "kind": "service_health", "request_id": "q"})["available"] is False
        assert len(executors) == 1
    finally:
        service.close()


def test_oversize_result_fails_explicitly_without_truncating_mask_or_candidates(tmp_path):
    service, _, _, _, executors = service_fixture(tmp_path)
    try:
        batch = response_document()["batch"]
        batch["candidates"][0]["instance_id"] = "x" * (2**20)
        executors[0].batch = batch
        response = read(submit(service, "r"))
        assert (response["outcome"], response["reason"], response["batch"]) == (
            "MODEL_ERROR", "RESPONSE_FRAME_TOO_LARGE", None)
    finally:
        service.close()


def test_frame_limit_that_cannot_encode_readiness_rejected_before_model_start(tmp_path):
    module = importlib.import_module("so101_demo.runtime.inference.service")
    config = campaign_fixture(tmp_path)["teacher_service"]
    config["max_frame_bytes"] = 5
    calls = []
    def factory(index, settings):
        calls.append(index)
        raise AssertionError("unusable service must not load models")
    with pytest.raises(ValueError, match="INFERENCE_SERVICE_CONFIG_INVALID"):
        module.InferenceService(config=config, executor_factory=factory,
            monotonic_ns=time.monotonic_ns, generation="g1", gpu_uuid="GPU-selected")
    assert calls == []
