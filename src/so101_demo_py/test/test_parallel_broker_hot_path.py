"""Contract tests for the Coordinator-free stateless perception Broker."""

from contextlib import contextmanager
from pathlib import Path
import threading
import time


YOLO = "plastic-cup-yolo11n-seg-v1"
GROUNDED = "grounded-sam"
MODEL_VERSION = "f" * 64


def _config():
    from so101_demo.parallel_batch.contracts import load_parallel_runtime_config

    return load_parallel_runtime_config(
        Path(__file__).parents[1] / "config/mujoco/parallel_batch_v1.yaml"
    )


def _request(request_id, *, deadline_s=3.0):
    from so101_demo.parallel_batch.contracts import InferenceRequest

    return InferenceRequest(
        request_id=request_id,
        model_id=YOLO,
        image_timestamp_s=1.0,
        input_relative_path="shared/rgb.npy",
        input_sha256="a" * 64,
        deadline_s=deadline_s,
    )


def _snapshot(marker):
    from so101_demo.runtime.parallel_perception_runtime import Snapshot

    return Snapshot(
        shape=(2, 2, 3),
        source_stamp_ns=1_000_000_000,
        source_frame_id="camera",
        query_class_id=marker,
    )


def _message(transport, request, snapshot, index):
    return {
        "schema_version": 1,
        "kind": "broker_call",
        "request_id": f"rpc-{request.request_id}",
        "idempotency_key": f"rpc-{request.request_id}",
        "payload": {
            "operation": "infer",
            "request": transport.serialize_request(request),
            "snapshot": transport.serialize_snapshot(snapshot),
        },
    }


class _FastRuntime:
    executor_counts = {YOLO: 2, GROUNDED: 1}

    def __init__(self):
        self.healthy = False
        self.health_changed = lambda _healthy: None
        self.calls = []
        self.completions = []
        self.active = 0
        self.active_peak = 0
        self._condition = threading.Condition()

    def start(self):
        self.healthy = True
        self.health_changed(True)

    def _authorized(self, *_args, **_kwargs):
        raise AssertionError("Coordinator authorization entered inference lifecycle")

    def infer(self, request, snapshot, *, executor_index):
        marker = snapshot.query_class_id
        with self._condition:
            self.calls.append((request.request_id, marker, executor_index))
            self.active += 1
            self.active_peak = max(self.active_peak, self.active)
            if marker == "marker-01":
                assert self._condition.wait_for(
                    lambda: "marker-02" in self.completions,
                    timeout=2.0,
                )
        if marker.startswith("marker-") and marker not in {
            "marker-01",
            "marker-02",
        }:
            time.sleep((11 - int(marker[-2:])) * 0.002)
        with self._condition:
            self.completions.append(marker)
            self.active -= 1
            self._condition.notify_all()
        from so101_demo.parallel_batch.broker import ModelResult
        from so101_demo.parallel_batch.contracts import ModelOutcome

        return ModelResult(
            ModelOutcome.QUALIFIED,
            candidate={
                "marker": marker,
                "model_id": request.model_id,
                "weights_sha256": MODEL_VERSION,
            },
        )

    def record_failure(self, **_kwargs):
        return None

    def _unhealthy(self):
        self.healthy = False
        self.health_changed(False)


@contextmanager
def _running_broker(root, *, capacity=10, handlers=10, deadline_s=3.0):
    from so101_demo.runtime.parallel_ipc import BrokerTransport
    from so101_demo.runtime.parallel_perception_runtime import PerceptionService

    root.mkdir(mode=0o700)
    runtime = _FastRuntime()
    transport = BrokerTransport(
        ipc_root=root,
        config=_config(),
        generation=1,
        deadline_s=deadline_s,
        runtime_identity={
            "connection_handler_count": handlers,
            "yolo_executor_count": 2,
            "grounded_sam_executor_count": 1,
            "queue_capacity_per_model": capacity,
        },
    )
    service = PerceptionService(
        runtime,
        _config(),
        generation=1,
        queue_capacity_per_model=capacity,
    )
    service.start()
    server = transport.server(service, endpoint=root / "perception.sock")
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield runtime, transport, server
    finally:
        server.close()
        thread.join(timeout=2.0)
        assert not thread.is_alive()
        assert server.wait_handlers(timeout_s=2.0)
        assert service.close(timeout_s=2.0)


def _call(server, transport, request, marker, index):
    from so101_demo.runtime.parallel_ipc import UnixRpcClient

    return UnixRpcClient(server.path, deadline_s=5.0).call(
        _message(transport, request, _snapshot(marker), index)
    )["payload"]


def test_broker_serves_without_coordinator_authority_or_journal(tmp_path):
    with _running_broker(tmp_path / "broker", handlers=1) as (
        runtime,
        transport,
        server,
    ):
        response = _call(server, transport, _request("request-01"), "single", 1)

    assert response["request_id"] == "request-01"
    assert response["model_id"] == YOLO
    assert response["model_version"] == MODEL_VERSION
    assert response["candidate"]["marker"] == "single"
    assert [call[:2] for call in runtime.calls] == [("request-01", "single")]
    assert runtime.calls[0][2] in {0, 1}
    metrics = transport.metrics_snapshot()
    assert "authority_call_count" not in metrics
    assert "journal_replay_hot_path_count" not in metrics


def test_w10_c2_reordered_completions_keep_exact_request_correlation(tmp_path):
    with _running_broker(tmp_path / "broker") as (runtime, transport, server):
        replies = {}
        errors = []
        lock = threading.Lock()
        start = threading.Barrier(11)

        def invoke(index):
            request_id = f"request-{index:02d}"
            marker = f"marker-{index:02d}"
            try:
                start.wait(timeout=2.0)
                response = _call(
                    server,
                    transport,
                    _request(request_id),
                    marker,
                    index,
                )
                with lock:
                    replies[request_id] = response
            except BaseException as error:
                with lock:
                    errors.append(error)

        clients = [threading.Thread(target=invoke, args=(index,)) for index in range(1, 11)]
        for client in clients:
            client.start()
        start.wait(timeout=2.0)
        for client in clients:
            client.join(timeout=7.0)

        assert all(not client.is_alive() for client in clients)
        assert errors == []
        assert set(replies) == {f"request-{index:02d}" for index in range(1, 11)}
        for request_id, response in replies.items():
            assert response["request_id"] == request_id
            assert response["candidate"]["marker"] == request_id.replace(
                "request", "marker"
            )
        assert runtime.completions.index("marker-02") < runtime.completions.index(
            "marker-01"
        )
        assert runtime.completions != [f"marker-{index:02d}" for index in range(1, 11)]
        assert runtime.active_peak == 2
        metrics = transport.metrics_snapshot()
        assert metrics["model_active_peak"][YOLO] == 2
        assert metrics["logical_inference_count"] == 10
        assert metrics["transport_errors"] == {}


def test_duplicate_semantic_work_with_distinct_request_ids_is_recomputed(tmp_path):
    with _running_broker(tmp_path / "broker", handlers=2) as (
        runtime,
        transport,
        server,
    ):
        first = _call(server, transport, _request("duplicate-01"), "same", 1)
        second = _call(server, transport, _request("duplicate-02"), "same", 2)

    assert first["request_id"] == "duplicate-01"
    assert second["request_id"] == "duplicate-02"
    assert [item[:2] for item in runtime.calls] == [
        ("duplicate-01", "same"),
        ("duplicate-02", "same"),
    ]


def test_queue_full_is_prompt_and_does_not_evict_accepted_work():
    from so101_demo.parallel_batch.broker import PerceptionBroker

    clock = [100.0]
    broker = PerceptionBroker(
        _config(),
        grounded_model_id=GROUNDED,
        clock=lambda: clock[0],
        queue_capacity_per_model=1,
    )
    broker.set_model_ready(YOLO, True)
    broker.set_model_ready(GROUNDED, True)
    accepted = _request("accepted")
    started = time.monotonic()
    assert broker.submit(accepted).accepted is True
    rejected = broker.submit(_request("overflow"))
    elapsed = time.monotonic() - started

    assert elapsed < 0.1
    assert rejected.accepted is False
    assert rejected.reason == "QUEUE_FULL"
    assert broker.next_ready_request(YOLO) == accepted


def test_one_request_deadline_cannot_cancel_or_misroute_another():
    from so101_demo.parallel_batch.broker import ModelResult, PerceptionBroker
    from so101_demo.parallel_batch.contracts import ModelOutcome

    clock = [100.0]
    broker = PerceptionBroker(
        _config(),
        grounded_model_id=GROUNDED,
        clock=lambda: clock[0],
        queue_capacity_per_model=2,
    )
    broker.set_model_ready(YOLO, True)
    broker.set_model_ready(GROUNDED, True)
    expired = _request("expired", deadline_s=0.5)
    survivor = _request("survivor", deadline_s=2.0)
    assert broker.submit(expired).accepted is True
    assert broker.submit(survivor).accepted is True

    clock[0] = 100.6
    assert broker.expire_due() is True
    expired_response = broker.poll_response(expired)
    assert expired_response.request.request_id == "expired"
    assert expired_response.outcome is ModelOutcome.INFERENCE_TIMEOUT
    assert expired_response.reason == "REQUEST_DEADLINE_EXCEEDED"
    assert broker.poll_response(survivor) is None

    assert broker.next_ready_request(YOLO) == survivor
    survivor_response = broker.complete(
        survivor,
        ModelResult(ModelOutcome.NORMAL_REJECTION),
    )
    assert survivor_response.request.request_id == "survivor"
    assert survivor_response.outcome is ModelOutcome.NORMAL_REJECTION
