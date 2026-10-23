"""The host's ACT policy service: one loaded bundle, requests served first in, first out, one inference at a time.

Design: docs/superpowers/specs/2026-10-22-so101-act-parallel-rollout-design.md (P2, P3). The model is loaded once by the caller and
handed in as `infer(observation) -> chunk`. This module owns the bounded scheduling around it, in the manner of the Teacher
inference service (`runtime/inference/service.py`):

- at most `max_inflight` requests exist at once (being received, queued or running); a request that arrives when all slots are in
  use is answered `QUEUE_FULL` from its header alone, before its images are read;
- the queue is FIFO and there is no batching;
- a request waits at most `queue_timeout_s` (and never past its own deadline); the model call is judged against
  `inference_timeout_s` after it returns (a running CUDA call cannot be interrupted, so it is never abandoned mid-way);
- every reply carries the bundle identity, the sequence, the observation stamp and this request's timing (queue wait, inference ms);
- a model infrastructure fault makes the service unavailable (every later request is answered `INFRA_ERROR`), it does not guess;
- `close()` stops the accept loop, fails what is still queued, joins every thread and returns the stop proof.

The service imports no torch and no lerobot: the caller (`cli/act_policy_service.py`) builds the model.
"""

from __future__ import annotations

from collections import Counter, deque
import json
import os
from pathlib import Path
import socket
import threading
import time

from so101_demo.runtime.act_policy import protocol
from so101_demo.runtime.inference.codec import open_socket_parent
from so101_demo.runtime.parallel_ipc.frames import transport_address


class _Slot:
    """An in-flight slot, taken before any image is buffered and returned when the reply is delivered or the peer is gone."""

    def __init__(self, service):
        self.service, self.closed = service, False

    def close(self):
        with self.service._lock:
            if not self.closed:
                self.closed = True
                self.service._slots.discard(self)


class _Ticket:
    def __init__(self, request, observation, received_ns, inflight):
        self.request, self.observation = request, observation
        self.done = threading.Event()
        self.response = None
        self.state = "QUEUED"
        self.abandoned = False
        self.timing = {"received_monotonic_ns": received_ns, "queued_monotonic_ns": received_ns,
                       "started_monotonic_ns": None, "completed_monotonic_ns": None,
                       "queue_wait_ms": None, "inference_ms": None, "inflight_at_receipt": inflight}


class PolicyService:
    def __init__(self, *, infer, identity, generation, gpu_uuid, max_inflight, queue_timeout_s, inference_timeout_s,
                 max_frame_bytes, monotonic_ns=time.monotonic_ns, audit=None):
        if not callable(infer):
            raise ValueError("POLICY_SERVICE_CONFIG_INVALID")
        for name in ("bundle_sha256", "policy_sha256", "cameras", "state_dim", "image_shape", "chunk_size", "device"):
            if name not in identity:
                raise ValueError("POLICY_SERVICE_CONFIG_INVALID")
        for value in (max_inflight, max_frame_bytes):
            if type(value) is not int or value <= 0:
                raise ValueError("POLICY_SERVICE_CONFIG_INVALID")
        for value in (queue_timeout_s, inference_timeout_s):
            if type(value) not in (int, float) or not 0 < value < float("inf"):
                raise ValueError("POLICY_SERVICE_CONFIG_INVALID")
        if type(generation) is not str or not generation or type(gpu_uuid) is not str or not gpu_uuid:
            raise ValueError("POLICY_SERVICE_CONFIG_INVALID")
        self.infer, self.identity = infer, dict(identity)
        self.generation, self.gpu_uuid = generation, gpu_uuid
        self.max_inflight, self.queue_timeout_s, self.inference_timeout_s = max_inflight, queue_timeout_s, inference_timeout_s
        self.max_frame_bytes, self.clock, self.audit = max_frame_bytes, monotonic_ns, audit
        self._lock = threading.RLock()
        self._available_cv = threading.Condition(self._lock)
        self._slots, self._queue = set(), deque()
        self._closed = threading.Event()
        self._started = False
        self._available = False
        self._fault_reason = "NOT_STARTED"
        self._worker = None
        self.outcomes = Counter()
        self.consecutive_errors = 0
        self.max_inflight_seen = 0
        self.warm_up_s = list(identity.get("warm_up_s", []))

    # ---- lifecycle ---------------------------------------------------------------------------------------------------------

    def start(self):
        with self._lock:
            if self._started or self._closed.is_set():
                raise ValueError("POLICY_SERVICE_ALREADY_STARTED")
            self._started, self._available, self._fault_reason = True, True, ""
        self._worker = threading.Thread(target=self._run, name="act-policy-worker", daemon=False)
        self._worker.start()

    @property
    def inflight_count(self):
        with self._lock:
            return len(self._slots)

    def reserve(self):
        """A slot for one request, or None when the service is full or unavailable."""
        with self._lock:
            if not self._available or len(self._slots) >= self.max_inflight:
                return None
            slot = _Slot(self)
            self._slots.add(slot)
            self.max_inflight_seen = max(self.max_inflight_seen, len(self._slots))
            return slot

    # ---- replies -----------------------------------------------------------------------------------------------------------

    def _response(self, request, outcome, reason, timing, actions=None):
        return protocol.validate_response({
            "schema_version": protocol.SCHEMA_VERSION, "kind": "policy_response", "request_id": request["request_id"],
            "client_id": request["client_id"], "sequence": request["sequence"],
            "observation_sim_s": request["observation"]["sim_time_s"], "service_generation": self.generation,
            "bundle_sha256": self.identity["bundle_sha256"], "policy_sha256": self.identity["policy_sha256"],
            "outcome": outcome, "reason": reason, "actions": actions, "timing": dict(timing)})

    def immediate(self, request, outcome, reason):
        """A reply that never reached the queue (full, unavailable, invalid input)."""
        now = self.clock()
        timing = {"received_monotonic_ns": now, "queued_monotonic_ns": None, "started_monotonic_ns": None,
                  "completed_monotonic_ns": None, "queue_wait_ms": None, "inference_ms": None,
                  "inflight_at_receipt": self.inflight_count}
        self._count(request, outcome, timing)
        return self._response(request, outcome, reason, timing)

    def _count(self, request, outcome, timing):
        with self._lock:
            self.outcomes[outcome] += 1
            # a run of replies that say the service or the request is wrong; an OK reply ends it, a refusal for load does not count
            if outcome == "OK":
                self.consecutive_errors = 0
            elif outcome in protocol.ERROR_OUTCOMES:
                self.consecutive_errors += 1
        if self.audit is not None:
            try:
                self.audit({"request_id": request["request_id"], "client_id": request["client_id"],
                            "sequence": request["sequence"], "outcome": outcome, "timing": dict(timing)})
            except Exception:       # noqa: BLE001 - an audit failure never changes a reply
                pass

    def _finish(self, ticket, outcome, reason, actions=None):
        with self._lock:
            if ticket.done.is_set():
                return
            if ticket.timing["queued_monotonic_ns"] is not None and ticket.timing["started_monotonic_ns"] is None:
                ticket.timing["queue_wait_ms"] = (self.clock() - ticket.timing["queued_monotonic_ns"]) / 1e6
            ticket.response = self._response(ticket.request, outcome, reason, ticket.timing, actions)
            ticket.state = "DONE"
            ticket.done.set()
        self._count(ticket.request, outcome, ticket.timing)

    # ---- submission --------------------------------------------------------------------------------------------------------

    def _check_observation(self, request):
        observation = request["observation"]
        names = [image["name"] for image in observation["images"]]
        expected = list(self.identity["cameras"])
        if names != expected:
            return "CAMERAS_MISMATCH"
        if len(observation["state"]) != self.identity["state_dim"]:
            return "STATE_DIM_MISMATCH"
        if any(image["shape"] != list(self.identity["image_shape"]) for image in observation["images"]):
            return "IMAGE_SHAPE_MISMATCH"
        return None

    def submit(self, request, payload, slot):
        """Queue one received request; returns its ticket. `slot` is the reservation taken before the payload was read."""
        received = self.clock()
        try:
            request = protocol.validate_request(request)
            problem = self._check_observation(request)
            observation = None if problem else protocol.unpack_observation(request["observation"], payload)
        except ValueError:
            slot.close()
            raise
        with self._lock:
            ticket = _Ticket(request, observation, received, len(self._slots))
            if problem is not None or not self._available:
                slot.close()
                ticket.timing["queued_monotonic_ns"] = None
                ticket.state = "QUEUED"
                self._finish(ticket, "INPUT_INVALID" if problem else "INFRA_ERROR", problem or self._fault_reason)
                return ticket
            if slot.closed or slot not in self._slots:
                raise ValueError("POLICY_RESERVATION_INVALID")
            # the slot becomes the ticket: it is still one in-flight request
            self._slots.discard(slot)
            slot.closed = True
            self._slots.add(ticket)
            if self.clock() >= request["deadline_monotonic_ns"]:
                self._finish(ticket, "QUEUE_TIMEOUT", "REQUEST_DEADLINE_EXCEEDED")
                return ticket
            self._queue.append(ticket)
            self._available_cv.notify()
            return ticket

    def release(self, ticket):
        with self._lock:
            ticket.abandoned = True
            self._slots.discard(ticket)

    # ---- the worker --------------------------------------------------------------------------------------------------------

    def _run(self):
        while not self._closed.is_set():
            with self._lock:
                if not self._queue:
                    self._available_cv.wait(timeout=0.02)
                    continue
                ticket = self._queue.popleft()
                if ticket.done.is_set() or ticket.abandoned:
                    continue
                now = self.clock()
                if not self._available:
                    self._finish(ticket, "INFRA_ERROR", self._fault_reason)
                    continue
                # A request that is too old to describe the present is dropped here, without a model call: its own deadline
                # (the client no longer waits) or the longest wait the service allows.
                if now >= ticket.request["deadline_monotonic_ns"]:
                    self._finish(ticket, "QUEUE_TIMEOUT", "REQUEST_DEADLINE_EXCEEDED")
                    continue
                if now >= ticket.timing["queued_monotonic_ns"] + int(self.queue_timeout_s * 1e9):
                    self._finish(ticket, "QUEUE_TIMEOUT", "QUEUE_DEADLINE_EXCEEDED")
                    continue
                ticket.state = "RUNNING"
                ticket.timing["started_monotonic_ns"] = now
                ticket.timing["queue_wait_ms"] = (now - ticket.timing["queued_monotonic_ns"]) / 1e6
            self._infer(ticket)

    def _infer(self, ticket):
        outcome, reason, actions = "OK", "", None
        try:
            chunk = self.infer(ticket.observation)
            actions = [[float(value) for value in row] for row in chunk]
            if not actions:
                raise ValueError("POLICY_ACTION_INVALID")
        except (RuntimeError, OSError, MemoryError) as error:
            outcome, reason, actions = "INFRA_ERROR", f"{type(error).__name__}: {str(error)[:200]}", None
            self._fault(f"POLICY_MODEL_FAILED: {type(error).__name__}")
        except (ValueError, KeyError, TypeError, IndexError, AttributeError, OverflowError) as error:
            outcome, reason, actions = "MODEL_ERROR", f"{type(error).__name__}: {str(error)[:200]}", None
        except Exception as error:      # noqa: BLE001 - an unknown failure is an infrastructure fault, not a result
            outcome, reason, actions = "INFRA_ERROR", f"{type(error).__name__}: {str(error)[:200]}", None
            self._fault(f"POLICY_MODEL_FAILED: {type(error).__name__}")
        finally:
            completed = self.clock()
            ticket.timing["completed_monotonic_ns"] = completed
            ticket.timing["inference_ms"] = (completed - ticket.timing["started_monotonic_ns"]) / 1e6
        if outcome == "OK" and ticket.timing["inference_ms"] / 1e3 > self.inference_timeout_s:
            outcome, reason, actions = "INFERENCE_TIMEOUT", "INFERENCE_DEADLINE_EXCEEDED", None
        self._finish(ticket, outcome, reason, actions)

    def _fault(self, reason):
        with self._lock:
            self._available, self._fault_reason = False, reason
            queued, self._queue = list(self._queue), deque()
        for ticket in queued:
            self._finish(ticket, "INFRA_ERROR", reason)

    # ---- queries -----------------------------------------------------------------------------------------------------------

    def query(self, request):
        request = protocol.validate_query(request)
        with self._lock:
            base = {"schema_version": protocol.SCHEMA_VERSION, "request_id": request["request_id"],
                    "service_generation": self.generation}
            if request["kind"] == "policy_health_query":
                return protocol.validate_service_reply(base | {
                    "kind": "policy_health", "available": self._available, "reason": self._fault_reason,
                    "inflight": len(self._slots), "served": self.outcomes["OK"],
                    "refused": self.outcomes["QUEUE_FULL"], "consecutive_errors": self.consecutive_errors})
            identity = self.identity
            return protocol.validate_service_reply(base | {
                "kind": "policy_ready", "bundle_sha256": identity["bundle_sha256"], "policy_sha256": identity["policy_sha256"],
                "device": identity["device"], "gpu_uuid": self.gpu_uuid, "cameras": list(identity["cameras"]),
                "state_dim": identity["state_dim"], "image_shape": list(identity["image_shape"]),
                "chunk_size": identity["chunk_size"], "max_inflight": self.max_inflight, "pid": os.getpid(),
                "warm_up_s": list(self.warm_up_s), "ready": self._available})

    # ---- close -------------------------------------------------------------------------------------------------------------

    def close(self):
        self._closed.set()
        with self._lock:
            self._available_cv.notify_all()
        self._fault("SERVICE_CLOSED")
        terminated = True
        if self._worker is not None:
            self._worker.join(timeout=10)
            terminated = not self._worker.is_alive()
        return {"terminated": terminated, "outcomes": dict(self.outcomes), "max_inflight_seen": self.max_inflight_seen}


class PolicyUnixServer:
    """The bounded Unix-socket transport of one `PolicyService`; one request per connection."""

    def __init__(self, *, service, socket_path, receive_budget_s):
        if type(receive_budget_s) not in (int, float) or not 0 < receive_budget_s < float("inf"):
            raise ValueError("POLICY_RECEIVE_BUDGET_INVALID")
        self.service, self.path, self.receive_budget_s = service, Path(socket_path), receive_budget_s
        self._closed = threading.Event()
        self._lock = threading.Lock()
        self._handlers, self._connections = set(), set()
        self._listener = self._directory_fd = self._accept_thread = None
        self.socket_inode = None

    def start(self):
        if self._listener is not None:
            raise ValueError("POLICY_SOCKET_ALREADY_STARTED")
        self._directory_fd = open_socket_parent(self.path)
        try:
            try:
                os.stat(self.path.name, dir_fd=self._directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ValueError("POLICY_SOCKET_ALREADY_EXISTS")
            self._listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._listener.bind(transport_address(self.path, self._directory_fd))
            os.chmod(self.path.name, 0o600, dir_fd=self._directory_fd)
            self.socket_inode = os.stat(self.path.name, dir_fd=self._directory_fd, follow_symlinks=False).st_ino
            self._listener.listen(self.service.max_inflight + 8)
            self._listener.settimeout(0.05)
            self._accept_thread = threading.Thread(target=self._accept, name="act-policy-accept", daemon=False)
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
            thread = threading.Thread(target=self._handle, args=(connection,), name="act-policy-conn", daemon=False)
            with self._lock:
                self._handlers.add(thread)
            thread.start()

    def _send(self, connection, document, deadline_ns):
        remaining = (deadline_ns - time.monotonic_ns()) / 1e9
        if remaining <= 0:
            raise TimeoutError("POLICY_RESPONSE_DELIVERY_EXPIRED")
        connection.settimeout(remaining)
        connection.sendall(protocol.encode_frame(document, b"", max_frame_bytes=self.service.max_frame_bytes))

    def _handle(self, connection):
        service, ticket, slot = self.service, None, None
        try:
            deadline = time.monotonic_ns() + int(self.receive_budget_s * 1e9)
            request, payload_size = protocol.receive_header(connection, deadline_monotonic_ns=deadline,
                                                            max_frame_bytes=service.max_frame_bytes)
            if request["kind"] != "policy_request":
                self._send(connection, service.query(request), deadline)
                return
            slot = service.reserve()
            if slot is None:
                # full or unavailable: answered from the header alone, the images are never read
                with service._lock:
                    outcome, reason = (("QUEUE_FULL", "MAX_INFLIGHT_REQUESTS") if service._available
                                       else ("INFRA_ERROR", service._fault_reason))
                self._send(connection, service.immediate(request, outcome, reason), deadline)
                return
            payload = protocol._receive_exact(connection, payload_size, deadline) if payload_size else b""
            ticket = service.submit(request, payload, slot)
            slot = None
            remaining = max(0.001, (request["deadline_monotonic_ns"] - time.monotonic_ns()) / 1e9)
            if not ticket.done.wait(timeout=remaining):
                ticket.abandoned = True
                with service._lock:
                    if not ticket.done.is_set():
                        service._finish(ticket, "QUEUE_TIMEOUT" if ticket.state == "QUEUED" else "INFERENCE_TIMEOUT",
                                        "REQUEST_DEADLINE_EXCEEDED")
            self._send(connection, ticket.response, max(request["deadline_monotonic_ns"], time.monotonic_ns() + 10_000_000))
        except (OSError, ValueError, TimeoutError):
            pass                        # a malformed or vanished peer gets no reply; its slot is returned below
        finally:
            if slot is not None:
                slot.close()
            if ticket is not None:
                service.release(ticket)
            try:
                connection.close()
            except OSError:
                pass
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
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if self._accept_thread is not None:
            self._accept_thread.join(timeout=2)
        with self._lock:
            handlers = tuple(self._handlers)
        for thread in handlers:
            thread.join(timeout=2)
        if self._directory_fd is not None:
            os.close(self._directory_fd)
            self._directory_fd = None
        return {"terminated": (self._accept_thread is None or not self._accept_thread.is_alive())
                and all(not thread.is_alive() for thread in handlers)}


class ProcessGone(OSError):
    """The process has no readable `/proc/<pid>` entry: it exited (or never existed), or exited between two reads."""


def process_record(pid=None):
    """Who this process is, from /proc alone (the train venv has no `so101_teleop`): pid, process group, start ticks, argv hash.

    A process that is gone, vanishes between the two reads or whose entry cannot be read raises `ProcessGone` (never a raw
    `FileNotFoundError`), so callers can tell "no such process" from a mismatch."""
    import hashlib

    pid = os.getpid() if pid is None else pid
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        fields = stat[stat.rindex(")") + 2:].split()
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
        return {"pid": pid, "pgid": int(fields[2]), "start_ticks": int(fields[19]),
                "argv_sha256": hashlib.sha256(cmdline).hexdigest()}
    except (OSError, ValueError, IndexError) as error:
        raise ProcessGone(f"pid {pid}: /proc entry unreadable: {type(error).__name__}: {error}") from error


def write_json_atomic(path, document):
    """Create `path` (a new file) so that a reader sees all of it or none: written and synced as `<name>.tmp`, then renamed."""
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    write_json(temporary, document)
    os.rename(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return path


def write_json(path, document):
    """Create `path` (new files only), durably."""
    data = json.dumps(document, sort_keys=True, indent=2).encode() + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return path
