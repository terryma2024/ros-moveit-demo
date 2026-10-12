"""Campaign-lifetime inference scheduling with bounded, transient request state."""

from __future__ import annotations

from concurrent.futures import Future
from collections import deque
import copy
import hashlib
import threading
import time
import os
from pathlib import Path
import socket

from so101_demo.adapters.perception.errors import (
    DeterministicModelResultError, ModelRuntimeInfrastructureError,
)
from so101_demo.runtime.inference.codec import (
    encode_inference_frame, open_socket_parent, receive_inference_frame, receive_inference_header, unpack_rgb,
)
from so101_demo.runtime.inference.contract import (
    validate_inference_request, validate_inference_response, validate_service_query,
    validate_service_response,
)
from so101_demo.runtime.parallel_ipc.frames import canonical_json, transport_address


class ReceivingReservation:
    """A transport-owned slot, acquired before any RGB payload is buffered."""

    def __init__(self, service):
        self.service = service
        self.closed = False

    def close(self):
        with self.service._lock:
            if not self.closed:
                self.closed = True
                self.service._slots.discard(self)


class InferenceTicket:
    """Track compute and reply delivery independently until both have finished."""

    def __init__(self, service, request, payload, received):
        self.service, self.request, self.payload = service, request, payload
        self.response = Future()
        self.compute_done = False
        self.delivery_done = False
        self.state = "QUEUED"
        self.timing = {"received_monotonic_ns": received, "queued_monotonic_ns": received,
                       "started_monotonic_ns": None, "completed_monotonic_ns": None}

    def delivery_complete(self):
        with self.service._lock:
            self.delivery_done = True
            self.service._release(self)

    def disconnect(self):
        """A disconnected peer has no pending delivery; CUDA may still be running."""
        with self.service._lock:
            self.delivery_done = True
            if self.state == "QUEUED":
                self.compute_done = True
            self.service._release(self)


class InferenceService:
    def __init__(self, *, config, executor_factory, monotonic_ns=time.monotonic_ns,
                 generation, gpu_uuid):
        self.config = copy.deepcopy(config)
        for key in ("instances", "max_inflight_requests", "max_frame_bytes"):
            if type(self.config[key]) is not int or self.config[key] <= 0:
                raise ValueError("INFERENCE_SERVICE_CONFIG_INVALID")
        for key in ("queue_timeout_s", "inference_timeout_s"):
            if type(self.config[key]) not in (int, float) or not 0 < self.config[key] < float("inf"):
                raise ValueError("INFERENCE_SERVICE_CONFIG_INVALID")
        if type(generation) is not str or not generation or type(gpu_uuid) is not str or not gpu_uuid:
            raise ValueError("INFERENCE_SERVICE_CONFIG_INVALID")
        self.generation, self.gpu_uuid = generation, gpu_uuid
        self.factory, self.clock = executor_factory, monotonic_ns
        self._lock = threading.RLock()
        self._slots, self._requests = set(), {}
        self._queue = deque()
        self._work_available = threading.Condition(self._lock)
        self._executors, self._threads = [], []
        self._closed = threading.Event()
        self._started = False
        self._available = False
        self._fault_reason = "NOT_STARTED"
        try:
            encode_inference_frame(self.query({"schema_version": 1, "kind": "service_ready", "request_id": "startup"}),
                b"", max_frame_bytes=self.config["max_frame_bytes"])
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError("INFERENCE_SERVICE_CONFIG_INVALID: cannot encode readiness") from error

    @property
    def inflight_count(self):
        with self._lock:
            return len(self._slots)

    def start(self):
        with self._lock:
            if self._started or self._closed.is_set():
                raise ValueError("INFERENCE_SERVICE_ALREADY_STARTED")
            self._started = True
        try:
            for index in range(self.config["instances"]):
                executor = self.factory(index, copy.deepcopy(self.config))
                self._executors.append(executor)
                if (not executor.alive() or executor.ready["runtime_device"] != "cuda"
                        or executor.ready["gpu_uuid"] != self.gpu_uuid):
                    raise RuntimeError("INFERENCE_EXECUTOR_NOT_READY")
            with self._lock:
                self._available, self._fault_reason = True, ""
            for index, executor in enumerate(self._executors):
                thread = threading.Thread(target=self._run_executor, args=(executor,),
                    name=f"inference-dispatch-{index}", daemon=False)
                self._threads.append(thread)
                thread.start()
            self._monitor = threading.Thread(target=self._monitor_requests,
                name="inference-health-deadlines", daemon=False)
            self._threads.append(self._monitor)
            self._monitor.start()
        except BaseException:
            self._fault("INFERENCE_EXECUTOR_START_FAILED")
            self.close()
            raise

    def reserve_receiving(self):
        with self._lock:
            if not self._available or len(self._slots) >= self.config["max_inflight_requests"]:
                return None
            reservation = ReceivingReservation(self)
            self._slots.add(reservation)
            return reservation

    def _release(self, ticket):
        if ticket.compute_done and ticket.delivery_done:
            try:
                self._queue.remove(ticket)
            except ValueError:
                pass
            self._slots.discard(ticket)
            key = ticket.request["request_id"]
            if self._requests.get(key) is ticket:
                del self._requests[key]
            ticket.payload = b""

    def _reply(self, ticket, outcome, reason, batch=None):
        with self._lock:
            if ticket.response.done():
                return
            response = {"schema_version": 1, "kind": "inference_response",
                "request_id": ticket.request["request_id"], "service_generation": self.generation,
                "source_stamp_ns": ticket.request["image"]["source_stamp_ns"],
                "source_frame_id": ticket.request["image"]["source_frame_id"],
                "outcome": outcome, "reason": reason, "batch": batch,
                "timing": dict(ticket.timing)}
            response = validate_inference_response(response)
            try:
                encode_inference_frame(response, b"", max_frame_bytes=self.config["max_frame_bytes"])
            except ValueError:
                response.update(outcome="MODEL_ERROR", reason="RESPONSE_FRAME_TOO_LARGE", batch=None)
                # A too-small configured bound is a fault, never a truncated mask.
                try:
                    encode_inference_frame(response, b"", max_frame_bytes=self.config["max_frame_bytes"])
                except ValueError:
                    ticket.response.set_exception(ValueError("INFERENCE_RESPONSE_FRAME_TOO_LARGE"))
                    return
            ticket.response.set_result(response)

    def _immediate(self, request, outcome, reason):
        ticket = InferenceTicket(self, request, b"", self.clock())
        ticket.timing["queued_monotonic_ns"] = None
        ticket.compute_done = True
        self._reply(ticket, outcome, reason)
        return ticket

    def submit(self, request, payload, connection, *, reservation=None):
        """Return a transport ticket; no authority or retry state enters the wire."""
        del connection
        try:
            request = validate_inference_request(request)
            unpack_rgb(request["image"], payload, limits=self.config)
        except ValueError:
            if reservation is not None:
                reservation.close()
            raise
        with self._lock:
            if request["request_id"] in self._requests:
                if reservation is not None: reservation.close()
                return self._immediate(request, "INPUT_INVALID", "DUPLICATE_REQUEST")
            if not self._available:
                if reservation is not None: reservation.close()
                return self._immediate(request, "INFRA_ERROR", self._fault_reason)
            if reservation is not None:
                if (reservation.service is not self or reservation.closed or reservation not in self._slots):
                    raise ValueError("INFERENCE_RECEIVING_RESERVATION_INVALID")
                reservation.closed = True
                self._slots.remove(reservation)
            elif len(self._slots) >= self.config["max_inflight_requests"]:
                return self._immediate(request, "QUEUE_FULL", "MAX_INFLIGHT_REQUESTS")
            ticket = InferenceTicket(self, request, payload, self.clock())
            self._slots.add(ticket)
            self._requests[request["request_id"]] = ticket
            if self.clock() >= request["deadline_monotonic_ns"]:
                ticket.compute_done = True
                self._reply(ticket, "QUEUE_TIMEOUT", "REQUEST_DEADLINE_EXCEEDED")
            else:
                self._queue.append(ticket)
                self._work_available.notify()
            return ticket

    def _run_executor(self, executor):
        while not self._closed.is_set():
            with self._lock:
                if not self._queue:
                    self._work_available.wait(timeout=0.02)
                    continue
                ticket = self._queue.popleft()
                if ticket.compute_done:
                    continue
                now = self.clock()
                queue_deadline = ticket.timing["queued_monotonic_ns"] + int(self.config["queue_timeout_s"] * 1e9)
                if not self._available or now >= min(queue_deadline, ticket.request["deadline_monotonic_ns"]):
                    ticket.compute_done = True
                    self._reply(ticket, "QUEUE_TIMEOUT" if self._available else "INFRA_ERROR",
                                "QUEUE_DEADLINE_EXCEEDED" if self._available else self._fault_reason)
                    self._release(ticket)
                    continue
                ticket.state = "RUNNING"
                ticket.timing["started_monotonic_ns"] = now
            outcome, reason, batch = "DETECTED", "", None
            try:
                batch = executor.infer(ticket.request, ticket.payload)
                if batch is None or not batch["candidates"]:
                    outcome, reason, batch = "NOT_DETECTED", "NO_CANDIDATES", None
                elif (batch["model_id"] != self.config["model"]["model_id"]
                      or batch["weights_sha256"] != self.config["model"]["weights"]["sha256"]):
                    raise DeterministicModelResultError("MODEL_IDENTITY_MISMATCH")
                else:
                    # Verify the complete result before any response is published.
                    probe = {"schema_version": 1, "kind": "inference_response", "request_id": ticket.request["request_id"],
                        "service_generation": self.generation, "source_stamp_ns": ticket.request["image"]["source_stamp_ns"],
                        "source_frame_id": ticket.request["image"]["source_frame_id"], "outcome": "DETECTED",
                        "reason": "", "batch": batch, "timing": dict(ticket.timing)}
                    validate_inference_response(probe)
            except (ModelRuntimeInfrastructureError, RuntimeError, OSError) as error:
                outcome, reason, batch = "INFRA_ERROR", str(error), None
                self._fault("INFERENCE_EXECUTOR_FAILED")
            except (DeterministicModelResultError, ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
                outcome, reason, batch = "MODEL_ERROR", str(error), None
            except Exception as error:
                outcome, reason, batch = "INFRA_ERROR", str(error), None
                self._fault("INFERENCE_EXECUTOR_FAILED")
            finally:
                with self._lock:
                    ticket.compute_done = True
                    ticket.timing["completed_monotonic_ns"] = self.clock()
                    ticket.state = "RESPONSES_PENDING"
                    if self.clock() >= min(ticket.request["deadline_monotonic_ns"],
                        ticket.timing["started_monotonic_ns"] + int(self.config["inference_timeout_s"] * 1e9)):
                        outcome, reason, batch = "INFERENCE_TIMEOUT", "INFERENCE_DEADLINE_EXCEEDED", None
                    self._reply(ticket, outcome, reason, batch)
                    self._release(ticket)

    def _fault(self, reason):
        with self._lock:
            self._available = False
            self._fault_reason = reason
            for ticket in tuple(self._requests.values()):
                if ticket.state == "QUEUED": ticket.compute_done = True
                self._reply(ticket, "INFRA_ERROR", reason)
                self._release(ticket)

    def _monitor_requests(self):
        while not self._closed.wait(0.005):
            if any(not executor.alive() for executor in self._executors):
                self._fault("INFERENCE_EXECUTOR_EXITED")
            with self._lock:
                now = self.clock()
                for ticket in tuple(self._requests.values()):
                    if ticket.response.done(): continue
                    key = "started_monotonic_ns" if ticket.state == "RUNNING" else "queued_monotonic_ns"
                    budget = self.config["inference_timeout_s" if ticket.state == "RUNNING" else "queue_timeout_s"]
                    if now >= min(ticket.request["deadline_monotonic_ns"], ticket.timing[key] + int(budget * 1e9)):
                        if ticket.state == "QUEUED": ticket.compute_done = True
                        self._reply(ticket, "INFERENCE_TIMEOUT" if ticket.state == "RUNNING" else "QUEUE_TIMEOUT",
                                    "INFERENCE_DEADLINE_EXCEEDED" if ticket.state == "RUNNING" else "QUEUE_DEADLINE_EXCEEDED")
                        self._release(ticket)

    def query(self, request):
        request = validate_service_query(request)
        with self._lock:
            base = dict(request, service_generation=self.generation)
            if request["kind"] == "service_health":
                return validate_service_response(base | {"available": self._available, "reason": self._fault_reason})
            loaded = sum(executor.alive() for executor in self._executors)
            return validate_service_response(base | {"image_digest": self.config["image"]["digest"],
                "package_source_sha256": self.config["image"]["package_source_sha256"],
                "model_id": self.config["model"]["model_id"], "weights_sha256": self.config["model"]["weights"]["sha256"],
                "service_config_sha256": hashlib.sha256(canonical_json(self.config)).hexdigest(),
                "gpu_uuid": self.gpu_uuid, "configured_instances": self.config["instances"],
                "loaded_instances": loaded, "ready": self._available and loaded == self.config["instances"]})

    def close(self):
        self._closed.set()
        with self._lock:
            self._work_available.notify_all()
        self._fault("SERVICE_CLOSED")
        terminated = True
        for executor in self._executors:
            try:
                terminated = bool(executor.close()) and terminated
            except Exception:
                terminated = False
        for thread in self._threads:
            thread.join(timeout=2)
            terminated = not thread.is_alive() and terminated
        return {"terminated": terminated and all(not executor.alive() for executor in self._executors)}


class InferenceUnixServer:
    """Bounded transport for one service; no persistence/takeover protocol.

    Full-capacity arrivals are parsed serially as bounded metadata only. They
    never get a receiving RGB slot or a payload buffer and are rejected before
    submission. This also allows a bounded health query under model saturation.
    """

    def __init__(self, *, service, socket_path, receive_budget_s, audit=lambda event: None):
        if type(receive_budget_s) not in (float, int) or not 0 < receive_budget_s < float("inf"):
            raise ValueError("INFERENCE_RECEIVE_BUDGET_INVALID")
        self.service, self.path = service, Path(socket_path)
        self.receive_budget_s, self.audit = receive_budget_s, audit
        self._closed = threading.Event()
        self._lock = threading.Lock()
        self._handlers, self._connections = set(), set()
        self._listener, self._directory_fd, self._accept_thread = None, None, None

    def start(self):
        if self._listener is not None:
            raise ValueError("INFERENCE_SOCKET_ALREADY_STARTED")
        self._directory_fd = open_socket_parent(self.path)
        try:
            try:
                os.stat(self.path.name, dir_fd=self._directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ValueError("INFERENCE_SOCKET_ALREADY_EXISTS")
            self._listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._listener.bind(transport_address(self.path, self._directory_fd))
            os.chmod(self.path.name, 0o600, dir_fd=self._directory_fd)
            self._listener.listen(self.service.config["max_inflight_requests"])
            self._listener.settimeout(0.05)
            self._accept_thread = threading.Thread(target=self._accept,
                name="inference-unix-accept", daemon=False)
            self._accept_thread.start()
        except BaseException:
            self.close()
            raise

    def _accept(self):
        while not self._closed.is_set():
            try:
                connection, _ = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with self._lock:
                self._connections.add(connection)
            reservation = self.service.reserve_receiving()
            if reservation is None:
                # One serial rejection reader; never spawn an overflow backlog.
                self._handle(connection, None, reject=True)
            else:
                thread = threading.Thread(target=self._handle, args=(connection, reservation),
                    name="inference-unix-frame", daemon=False)
                with self._lock:
                    self._handlers.add(thread)
                thread.start()

    def _handle(self, connection, reservation, reject=False):
        ticket = None
        try:
            deadline = time.monotonic_ns() + int(self.receive_budget_s * 1e9)
            if reject:
                request, _ = receive_inference_header(connection, deadline_monotonic_ns=deadline,
                    max_frame_bytes=self.service.config["max_frame_bytes"])
                if request["kind"] == "inference_request":
                    with self.service._lock:
                        if request["request_id"] in self.service._requests:
                            outcome, reason = "INPUT_INVALID", "DUPLICATE_REQUEST"
                        elif not self.service._available:
                            outcome, reason = "INFRA_ERROR", self.service._fault_reason
                        else:
                            outcome, reason = "QUEUE_FULL", "MAX_INFLIGHT_REQUESTS"
                    response = self.service._immediate(request, outcome, reason).response.result()
                else:
                    response = self.service.query(request)
            else:
                request, payload = receive_inference_frame(connection, deadline_monotonic_ns=deadline,
                    max_frame_bytes=self.service.config["max_frame_bytes"])
                if request["kind"] == "inference_request":
                    ticket = self.service.submit(request, payload, connection, reservation=reservation)
                    # The monitor owns frozen request/queue/inference deadlines.
                    response = ticket.response.result(timeout=max(0.001,
                        (request["deadline_monotonic_ns"] - time.monotonic_ns()) / 1e9))
                    deadline = request["deadline_monotonic_ns"]
                else:
                    response = self.service.query(request)
            remaining = (deadline - time.monotonic_ns()) / 1e9
            if remaining <= 0:
                raise TimeoutError("INFERENCE_RESPONSE_DELIVERY_EXPIRED")
            connection.settimeout(remaining)
            connection.sendall(encode_inference_frame(response, b"",
                max_frame_bytes=self.service.config["max_frame_bytes"]))
            if ticket is not None: ticket.delivery_complete()
        except (OSError, ValueError, TimeoutError) as error:
            self.audit({"event": "CONNECTION_REFUSED_OR_EXPIRED", "reason": str(error),
                        "monotonic_ns": time.monotonic_ns()})
        finally:
            if ticket is not None: ticket.disconnect()
            if reservation is not None: reservation.close()
            connection.close()
            with self._lock:
                self._connections.discard(connection)
                self._handlers.discard(threading.current_thread())

    def close(self):
        self._closed.set()
        if self._listener is not None:
            self._listener.close()
        with self._lock:
            connections = tuple(self._connections)
        for connection in connections:
            try: connection.shutdown(socket.SHUT_RDWR)
            except OSError: pass
        if self._accept_thread is not None:
            self._accept_thread.join(timeout=2)
        with self._lock:
            handlers = tuple(self._handlers)
        for thread in handlers:
            thread.join(timeout=2)
        if self._directory_fd is not None:
            os.close(self._directory_fd)
            self._directory_fd = None
        # Retain the stopped socket inode as evidence; never unlink a reused path.
        return {"terminated": (self._accept_thread is None or not self._accept_thread.is_alive())
                and all(not thread.is_alive() for thread in handlers)}
