"""One-request Worker client; no resubmission, transport files or completed-ID list."""

from __future__ import annotations

import os
from pathlib import Path
import socket
import stat
import threading
import time
import uuid

from so101_demo.runtime.inference.codec import (
    encode_inference_frame, open_socket_parent, receive_inference_frame,
)
from so101_demo.runtime.inference.contract import validate_inference_request, validate_service_query
from so101_demo.runtime.parallel_ipc.frames import transport_address


class InferenceClient:
    def __init__(self, *, socket_path, service_generation, max_frame_bytes):
        self.socket_path = Path(socket_path)
        self.generation = service_generation
        self.max_frame_bytes = max_frame_bytes
        if type(service_generation) is not str or not service_generation:
            raise ValueError("INFERENCE_CLIENT_CONFIG_INVALID")
        self._prefix = uuid.uuid4().hex
        self._allocated_sequence = 0
        self._consumed_sequence = 0
        self._identity_lock = threading.Lock()
        self._request_lock = threading.Lock()

    def new_request_id(self):
        """The Worker uses this campaign-unique opaque ID before submitting RGB."""
        with self._identity_lock:
            self._allocated_sequence += 1
            return f"{self._prefix}-{self._allocated_sequence}"

    def _consume_id(self, request_id):
        with self._identity_lock:
            try:
                prefix, serial = request_id.rsplit("-", 1)
                sequence = int(serial)
                if (prefix != self._prefix or str(sequence) != serial
                        or not self._consumed_sequence < sequence <= self._allocated_sequence):
                    raise ValueError("sequence")
            except (ValueError, AttributeError) as error:
                raise ValueError("INFERENCE_REQUEST_ID_REUSED_OR_UNOWNED") from error
            # Even a failed send consumes its ID. There is no retry under that ID.
            self._consumed_sequence = sequence

    def _exchange(self, document, payload, deadline):
        frame = encode_inference_frame(document, payload, max_frame_bytes=self.max_frame_bytes)
        fd = open_socket_parent(self.socket_path)
        try:
            metadata = os.stat(self.socket_path.name, dir_fd=fd, follow_symlinks=False)
            if not stat.S_ISSOCK(metadata.st_mode) or metadata.st_uid != os.getuid():
                raise ValueError("INFERENCE_SOCKET_OWNER_INVALID")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                remaining = (deadline - time.monotonic_ns()) / 1e9
                if remaining <= 0:
                    raise TimeoutError("INFERENCE_DEADLINE_EXCEEDED")
                connection.settimeout(remaining)
                connection.connect(transport_address(self.socket_path, fd))
                remaining = (deadline - time.monotonic_ns()) / 1e9
                if remaining <= 0:
                    raise TimeoutError("INFERENCE_DEADLINE_EXCEEDED")
                connection.settimeout(remaining)
                try:
                    connection.sendall(frame)
                except (BrokenPipeError, ConnectionResetError):
                    # An overloaded server may reject after its bounded header.
                    # Read its one response; never retransmit the submitted RGB.
                    pass
                response, _ = receive_inference_frame(connection,
                    deadline_monotonic_ns=deadline, max_frame_bytes=self.max_frame_bytes)
        finally:
            os.close(fd)
        if time.monotonic_ns() >= deadline:
            raise TimeoutError("INFERENCE_DEADLINE_EXCEEDED")
        if (response["request_id"] != document["request_id"]
                or response.get("service_generation") != self.generation):
            raise ValueError("INFERENCE_RESPONSE_IDENTITY_MISMATCH")
        return response

    def infer(self, request, payload):
        request = validate_inference_request(request)
        if not self._request_lock.acquire(blocking=False):
            raise ValueError("INFERENCE_CLIENT_REQUEST_PENDING")
        try:
            self._consume_id(request["request_id"])
            response = self._exchange(request, payload, request["deadline_monotonic_ns"])
            if (response["kind"] != "inference_response"
                    or (response["source_stamp_ns"], response["source_frame_id"]) != (
                        request["image"]["source_stamp_ns"], request["image"]["source_frame_id"])):
                raise ValueError("INFERENCE_RESPONSE_IDENTITY_MISMATCH")
            if response["batch"] is not None:
                if (response["batch"]["shape"] != request["image"]["shape"]
                        or any(candidate["class_id"] != request["query_class_id"]
                               for candidate in response["batch"]["candidates"])):
                    raise ValueError("INFERENCE_RESPONSE_IDENTITY_MISMATCH")
            return response
        finally:
            self._request_lock.release()

    def query(self, kind, request_id, *, timeout_s=1.0):
        if type(timeout_s) not in (float, int) or not 0 < timeout_s < float("inf"):
            raise ValueError("INFERENCE_QUERY_TIMEOUT_INVALID")
        request = validate_service_query({"schema_version": 1, "kind": kind, "request_id": request_id})
        response = self._exchange(request, b"", time.monotonic_ns() + int(timeout_s * 1e9))
        if response["kind"] != kind:
            raise ValueError("INFERENCE_RESPONSE_IDENTITY_MISMATCH")
        return response
