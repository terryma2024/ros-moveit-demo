"""The shard side of the policy service: a socket transport behind the unchanged `ActInferenceProcess` rules.

`ActInferenceProcess` keeps its rules (one request in flight, `request_timeout_s`, a stale or out-of-order reply is refused); only
the transport it sends over changes, from `ThreadInferenceTransport` (an in-process model call) to `SocketInferenceTransport` (a
request to the host's policy service). The transport has the same four methods: `send`, `receive`, `idle`/`quiesce`, `close`.

How a service answer reaches the boundary:

- `OK`: `{"sequence", "actions", "age_s", "service": {...}}`, `age_s` the wall time since `send`, exactly as the thread transport
  measures it, so the frozen `max_reply_age_s` applies unchanged.
- `QUEUE_FULL`, `QUEUE_TIMEOUT`, `INFERENCE_TIMEOUT`: the answer came too late (or not at all) to describe the present. The
  transport reports an infinitely old reply, which the boundary refuses as `INFERENCE_REPLY_STALE`: a late reply, counted, the
  previous goal holds. This is what the same load does to the in-process model call.
- the request deadline passing with no answer: nothing is delivered; the boundary's own deadline raises `INFERENCE_TIMEOUT`.
- a service that cannot be reached, a reply of another bundle, sequence or client, `MODEL_ERROR`, `INPUT_INVALID`, `INFRA_ERROR`:
  a reply without actions, which the boundary refuses as invalid: an infrastructure fault of the attempt.
"""

from __future__ import annotations

import os
from pathlib import Path
import queue
import socket
import stat
import threading
import time

from so101_demo.runtime.act_policy import protocol
from so101_demo.runtime.inference.codec import open_socket_parent
from so101_demo.runtime.parallel_ipc.frames import transport_address

REFUSALS = ("QUEUE_FULL", "QUEUE_TIMEOUT", "INFERENCE_TIMEOUT")


class PolicyClient:
    """One request-response exchange per call against the policy socket (no connection is kept)."""

    def __init__(self, *, socket_path, client_id, bundle_sha256, policy_sha256, cameras, max_frame_bytes,
                 service_generation=None):
        self.socket_path, self.client_id = Path(socket_path), client_id
        self.bundle_sha256, self.policy_sha256 = bundle_sha256, policy_sha256
        self.cameras, self.max_frame_bytes = tuple(cameras), max_frame_bytes
        self.service_generation = service_generation
        self._counter = 0
        self._lock = threading.Lock()

    def _new_request_id(self):
        with self._lock:
            self._counter += 1
            return f"{self.client_id}-r{self._counter}"

    def exchange(self, document, payload, deadline_ns):
        """`payload` is the bytes of the images or a list of buffers (sent in place with `sendmsg`, never joined)."""
        buffers = [payload] if isinstance(payload, (bytes, bytearray, memoryview)) else list(payload)
        head, views = protocol.encode_frame_parts(document, buffers, max_frame_bytes=self.max_frame_bytes)
        directory = open_socket_parent(self.socket_path)
        try:
            info = os.stat(self.socket_path.name, dir_fd=directory, follow_symlinks=False)
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                raise ValueError("POLICY_SOCKET_OWNER_INVALID")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                for step in ("connect", "send"):
                    remaining = (deadline_ns - time.monotonic_ns()) / 1e9
                    if remaining <= 0:
                        raise TimeoutError("POLICY_DEADLINE_EXCEEDED")
                    connection.settimeout(remaining)
                    if step == "connect":
                        connection.connect(transport_address(self.socket_path, directory))
                    else:
                        try:
                            protocol.send_frame_parts(connection, head, views)
                        except (BrokenPipeError, ConnectionResetError):
                            pass        # a full service answers from the header and closes: read its one reply
                response, _ = protocol.receive_frame(connection, deadline_monotonic_ns=deadline_ns,
                                                     max_frame_bytes=self.max_frame_bytes)
        finally:
            os.close(directory)
        if response.get("request_id") != document["request_id"]:
            raise ValueError("POLICY_RESPONSE_IDENTITY_MISMATCH")
        return response

    def infer(self, observation, *, sequence, deadline_ns):
        """The validated `policy_response` for one observation, whatever its outcome."""
        description, payload = protocol.pack_observation_views(observation, cameras=self.cameras)
        request = {"schema_version": protocol.SCHEMA_VERSION, "kind": "policy_request",
                   "request_id": self._new_request_id(), "client_id": self.client_id, "sequence": sequence,
                   "deadline_monotonic_ns": deadline_ns, "observation": description}
        response = self.exchange(request, payload, deadline_ns)
        if (response["kind"] != "policy_response" or response["sequence"] != sequence
                or response["client_id"] != self.client_id
                or response["observation_sim_s"] != description["sim_time_s"]
                or response["bundle_sha256"] != self.bundle_sha256 or response["policy_sha256"] != self.policy_sha256
                or (self.service_generation is not None and response["service_generation"] != self.service_generation)):
            raise ValueError("POLICY_RESPONSE_IDENTITY_MISMATCH")
        return response

    def query(self, kind, *, timeout_s=2.0):
        request = {"schema_version": protocol.SCHEMA_VERSION, "kind": kind, "request_id": self._new_request_id()}
        return self.exchange(request, b"", time.monotonic_ns() + int(timeout_s * 1e9))


class SocketInferenceTransport:
    """`ActInferenceProcess` transport over one worker thread that exchanges requests with the policy service."""

    def __init__(self, client, *, request_timeout_s, max_reply_age_s=None, monotonic=time.monotonic,
                 monotonic_ns=time.monotonic_ns):
        if not isinstance(client, PolicyClient) and not callable(getattr(client, "infer", None)):
            raise ValueError("INFERENCE_TRANSPORT_INVALID")
        self.client, self.request_timeout_s = client, float(request_timeout_s)
        #: a reply older than this is refused by the boundary, so the client stops waiting then (never later than the request timeout)
        self.reply_window_s = min(self.request_timeout_s, self.request_timeout_s if max_reply_age_s is None else float(max_reply_age_s))
        self.monotonic, self.monotonic_ns = monotonic, monotonic_ns
        self._requests = queue.Queue()
        self._lock = threading.Lock()
        self._latest = self._reply = None
        self._busy = self._closed = False
        self._thread = threading.Thread(target=self._work, name="act-rollout-policy-socket", daemon=True)
        self._thread.start()

    def _service_record(self, response):
        timing = response["timing"]
        return {"outcome": response["outcome"], "reason": response["reason"], "queue_wait_ms": timing["queue_wait_ms"],
                "inference_ms": timing["inference_ms"], "inflight_at_receipt": timing["inflight_at_receipt"],
                "service_generation": response["service_generation"], "bundle_sha256": response["bundle_sha256"],
                "sequence": response["sequence"], "observation_sim_s": response["observation_sim_s"]}

    def _answer(self, request):
        """The reply for one request, or None when nothing is to be delivered (the boundary's own deadline decides)."""
        sequence = request["sequence"]
        deadline_ns = request["sent_ns"] + int(self.reply_window_s * 1e9)
        try:
            response = self.client.infer(request["observation"], sequence=sequence, deadline_ns=deadline_ns)
        except TimeoutError:
            return None
        except (OSError, ValueError) as error:
            return {"sequence": sequence, "error": (str(error) or type(error).__name__)[:300]}
        service = self._service_record(response)
        if response["outcome"] == "OK":
            return {"sequence": sequence, "actions": tuple(tuple(row) for row in response["actions"]), "service": service}
        if response["outcome"] in REFUSALS:
            return {"sequence": sequence, "actions": None, "stale": True, "service": service}
        return {"sequence": sequence, "error": f"{response['outcome']}: {response['reason']}"[:300], "service": service}

    def _work(self):
        while True:
            request = self._requests.get()
            if request is None:
                return
            with self._lock:
                if request["sequence"] != self._latest:
                    continue
                self._busy = True
            try:
                reply = self._answer(request)
            except Exception as error:      # noqa: BLE001 - reported as an invalid reply, never raised in the worker
                reply = {"sequence": request["sequence"], "error": (str(error) or type(error).__name__)[:300]}
            with self._lock:
                self._busy = False
                if reply is not None and request["sequence"] == self._latest:
                    self._reply = (reply, request["sent_s"])

    def send(self, request: dict) -> None:
        if self._closed:
            raise ValueError("INFERENCE_PROCESS_CLOSED")
        job = {"sequence": request["sequence"], "observation": request["observation"], "sent_s": self.monotonic(),
               "sent_ns": self.monotonic_ns()}
        with self._lock:
            self._latest, self._reply = request["sequence"], None
        self._requests.put(job)

    def receive(self):
        with self._lock:
            if self._reply is None:
                return None
            reply, sent_s = self._reply
            self._reply = None
        age = float("inf") if reply.pop("stale", False) else max(0.0, self.monotonic() - sent_s)
        return dict(reply, age_s=age)

    def idle(self) -> bool:
        with self._lock:
            return not self._busy and self._requests.empty()

    def quiesce(self, timeout_s: float, sleep=time.sleep) -> bool:
        deadline = self.monotonic() + timeout_s
        with self._lock:
            self._latest, self._reply = None, None
        while not self.idle():
            if self.monotonic() >= deadline:
                return False
            sleep(0.002)
        return True

    def close(self):
        self._closed = True
        self._requests.put(None)
        self._thread.join(timeout=5.0)
        return not self._thread.is_alive()


class RemotePolicy:
    """What `ActPolicyRunner` is given in place of a model: it never infers (the chunk comes from the service, behind the boundary)
    and a reset has nothing to reset (the service's model call keeps no state between requests)."""

    def infer(self, observation):
        raise AssertionError("the chunk is computed by the policy service behind the inference boundary, never by the runner")

    def reset(self) -> None:
        return None
