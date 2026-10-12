"""Exercise real Unix binary frames, bounded receive slots and response identity."""

import importlib
import os
import socket
import threading
import time

import pytest

from so101_demo.runtime.parallel_ipc.frames import transport_address
from test_contract import request_document
from test_service import service_fixture, wait_until


def client_module():
    return importlib.import_module("so101_demo.runtime.inference.client")


def start_socket(tmp_path, service):
    module = importlib.import_module("so101_demo.runtime.inference.service")
    path = tmp_path / "inference.sock"
    server = module.InferenceUnixServer(service=service, socket_path=path, receive_budget_s=0.5)
    server.start()
    return path, server


def test_real_unix_rgb_infer_query_and_request_id_cannot_be_reused(tmp_path):
    service, _, _, calls, _ = service_fixture(tmp_path, instances=3)
    server = None
    try:
        path, server = start_socket(tmp_path, service)
        client = client_module().InferenceClient(socket_path=path, service_generation="g1", max_frame_bytes=2**20)
        ready = client.query("service_ready", "q")
        assert (ready["ready"], ready["loaded_instances"]) == (True, 3)
        request = request_document() | {"request_id": client.new_request_id(),
            "deadline_monotonic_ns": time.monotonic_ns() + 1_000_000_000}
        response = client.infer(request, bytes(range(18)))
        assert (response["outcome"], response["source_stamp_ns"], response["source_frame_id"]) == ("DETECTED", 7, "head")
        assert calls[0][2] == bytes(range(18))
        with pytest.raises(ValueError, match="INFERENCE_REQUEST_ID_REUSED"):
            client.infer(request, bytes(range(18)))
        assert len(calls) == 1
        assert client.query("service_health", "health")["available"] is True
        wait_until(lambda: service.inflight_count == 0)
    finally:
        if server is not None: server.close()
        service.close()


def test_real_client_rejects_cross_service_generation(tmp_path):
    service, _, _, _, _ = service_fixture(tmp_path)
    server = None
    try:
        path, server = start_socket(tmp_path, service)
        client = client_module().InferenceClient(socket_path=path, service_generation="old", max_frame_bytes=2**20)
        request = request_document() | {"request_id": client.new_request_id(),
            "deadline_monotonic_ns": time.monotonic_ns() + 1_000_000_000}
        with pytest.raises(ValueError, match="INFERENCE_RESPONSE_IDENTITY_MISMATCH"):
            client.infer(request, bytes(range(18)))
    finally:
        if server is not None: server.close()
        service.close()


def test_partial_frame_disconnect_releases_receiving_reservation(tmp_path):
    service, _, _, calls, _ = service_fixture(tmp_path, limit=1)
    server = None
    try:
        path, server = start_socket(tmp_path, service)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.connect(transport_address(path, fd))
                connection.sendall(b"\x00")
                wait_until(lambda: service.inflight_count == 1)
        finally:
            os.close(fd)
        wait_until(lambda: service.inflight_count == 0)
        assert calls == []
    finally:
        if server is not None: server.close()
        service.close()


def test_real_queue_full_never_buffers_or_executes_rejected_rgb(tmp_path):
    service, gates, started, calls, _ = service_fixture(tmp_path, limit=1)
    gates["r"] = threading.Event()
    server = None
    try:
        ticket = service.submit(request_document() | {"request_id": "r",
            "deadline_monotonic_ns": time.monotonic_ns() + 2_000_000_000}, bytes(range(18)), None)
        wait_until(lambda: started.get("r", threading.Event()).is_set())
        path, server = start_socket(tmp_path, service)
        client = client_module().InferenceClient(socket_path=path, service_generation="g1", max_frame_bytes=2**20)
        request = request_document() | {"request_id": client.new_request_id(),
            "deadline_monotonic_ns": time.monotonic_ns() + 1_000_000_000}
        assert client.infer(request, bytes(range(18)))["outcome"] == "QUEUE_FULL"
        assert service.inflight_count == 1
        assert [key for _, key, _ in calls] == ["r"]
        gates["r"].set()
        ticket.response.result(timeout=2)
        ticket.delivery_complete()
    finally:
        gates["r"].set()
        if server is not None: server.close()
        service.close()


@pytest.mark.parametrize("class_id,accepted", [("cup", True), ("plastic_cup", True), ("bottle", False)])
def test_real_client_accepts_only_cup_semantics_for_cup_queries(tmp_path, class_id, accepted):
    from test_contract import response_document
    service, _, _, _, executors = service_fixture(tmp_path, classes={"0": class_id})
    batch = response_document()["batch"]
    batch["candidates"][0]["class_id"] = class_id
    executors[0].batch = batch
    server = None
    try:
        path, server = start_socket(tmp_path, service)
        client = client_module().InferenceClient(socket_path=path, service_generation="g1", max_frame_bytes=2**20)
        request = request_document() | {"request_id": client.new_request_id(),
            "deadline_monotonic_ns": time.monotonic_ns() + 1_000_000_000}
        if accepted:
            assert client.infer(request, bytes(range(18)))["batch"]["candidates"][0]["class_id"] == class_id
        else:
            with pytest.raises(ValueError, match="INFERENCE_RESPONSE_IDENTITY_MISMATCH"):
                client.infer(request, bytes(range(18)))
    finally:
        if server is not None: server.close()
        service.close()
