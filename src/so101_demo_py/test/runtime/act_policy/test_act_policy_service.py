"""The policy service over a real Unix socket with a fake model: FIFO, one at a time, bounds, timeouts, identity, stop proof."""

import os
import threading
import time

import numpy as np
import pytest

from so101_demo.runtime.act_policy import protocol
from so101_demo.runtime.act_policy.client import PolicyClient
from so101_demo.runtime.act_policy.service import PolicyService, PolicyUnixServer, process_record

BUNDLE = "c" * 64
POLICY = "d" * 64
IDENTITY = {"bundle_sha256": BUNDLE, "policy_sha256": POLICY, "cameras": ["head", "wrist"], "state_dim": 8,
            "image_shape": [4, 6, 3], "chunk_size": 3, "device": "cuda", "warm_up_s": [0.5, 0.1]}


def observation(stamp=1.0, **cameras):
    base = {"sim_time_s": stamp, "state": [0.0] * 8, "head": np.full((4, 6, 3), 1, np.uint8),
            "wrist": np.full((4, 6, 3), 2, np.uint8)}
    base.update(cameras)
    return base


class FakeModel:
    """Records every call; `gate` blocks a call until released, `delay_s` sleeps, `error` raises."""

    def __init__(self):
        self.calls, self.active, self.max_active = [], 0, 0
        self.gate = None
        self.entered = threading.Event()
        self.delay_s, self.error = 0.0, None
        self._lock = threading.Lock()

    def __call__(self, obs):
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.calls.append(obs)
        self.entered.set()
        try:
            if self.gate is not None:
                assert self.gate.wait(10)
            if self.delay_s:
                time.sleep(self.delay_s)
            if self.error is not None:
                raise self.error
            stamp = obs["sim_time_s"]
            return tuple(tuple(stamp + row + column / 10 for column in range(6)) for row in range(3))
        finally:
            with self._lock:
                self.active -= 1


class Rig:
    def __init__(self, tmp_path, *, max_inflight=4, queue_timeout_s=2.0, inference_timeout_s=2.0, model=None):
        directory = tmp_path / "ipc"
        directory.mkdir(mode=0o700)
        self.socket = directory / "policy.sock"
        self.model = model or FakeModel()
        self.audit_rows = []
        self.service = PolicyService(infer=self.model, identity=IDENTITY, generation="gen-1", gpu_uuid="GPU-x",
                                     max_inflight=max_inflight, queue_timeout_s=queue_timeout_s,
                                     inference_timeout_s=inference_timeout_s, max_frame_bytes=1 << 22,
                                     audit=self.audit_rows.append)
        self.server = PolicyUnixServer(service=self.service, socket_path=self.socket, receive_budget_s=2.0)
        self.service.start()
        self.server.start()

    def client(self, name="c0", **changes):
        arguments = dict(socket_path=self.socket, client_id=name, bundle_sha256=BUNDLE, policy_sha256=POLICY,
                         cameras=("head", "wrist"), max_frame_bytes=1 << 22, service_generation="gen-1")
        arguments.update(changes)
        return PolicyClient(**arguments)

    def close(self):
        return self.server.close(), self.service.close()


@pytest.fixture
def rig(tmp_path):
    made = []

    def make(**kwargs):
        made.append(Rig(tmp_path, **kwargs))
        return made[-1]
    yield make
    for item in made:
        item.close()


def deadline(seconds=5.0):
    return time.monotonic_ns() + int(seconds * 1e9)


def test_a_request_is_answered_with_the_chunk_identity_sequence_stamp_and_timing(rig):
    served = rig()
    reply = served.client().infer(observation(stamp=2.5), sequence=7, deadline_ns=deadline())
    assert reply["outcome"] == "OK" and reply["sequence"] == 7 and reply["observation_sim_s"] == 2.5
    assert reply["bundle_sha256"] == BUNDLE and reply["policy_sha256"] == POLICY and reply["service_generation"] == "gen-1"
    assert reply["actions"][0] == pytest.approx([2.5 + 0 + column / 10 for column in range(6)])
    timing = reply["timing"]
    assert timing["queue_wait_ms"] >= 0 and timing["inference_ms"] >= 0 and timing["inflight_at_receipt"] == 1
    assert (timing["received_monotonic_ns"] <= timing["queued_monotonic_ns"] <= timing["started_monotonic_ns"]
            <= timing["completed_monotonic_ns"])
    seen = served.model.calls[0]
    assert seen["sim_time_s"] == 2.5 and np.array_equal(seen["head"], np.full((4, 6, 3), 1, np.uint8))
    assert np.array_equal(seen["wrist"], np.full((4, 6, 3), 2, np.uint8))


def test_ready_and_health_queries_describe_the_loaded_bundle(rig):
    served = rig()
    ready = served.client().query("policy_ready_query")
    assert ready["kind"] == "policy_ready" and ready["ready"] is True and ready["bundle_sha256"] == BUNDLE
    assert ready["cameras"] == ["head", "wrist"] and ready["chunk_size"] == 3 and ready["warm_up_s"] == [0.5, 0.1]
    assert ready["pid"] == os.getpid() and ready["max_inflight"] == 4
    health = served.client().query("policy_health_query")
    assert health["available"] is True and health["inflight"] == 0


def test_requests_are_served_first_in_first_out_one_at_a_time(rig):
    served = rig(max_inflight=8)
    served.model.gate = threading.Event()
    order, results = [], {}

    def ask(index):
        reply = served.client(f"c{index}").infer(observation(stamp=float(index)), sequence=index, deadline_ns=deadline(20))
        results[index] = reply
        order.append(index)

    threads = []
    for index in range(4):
        thread = threading.Thread(target=ask, args=(index,))
        thread.start()
        threads.append(thread)
        if index == 0:
            assert served.model.entered.wait(5)             # request 0 runs before any other arrives
        else:
            for _ in range(500):                             # request `index` is queued before the next one is sent
                if served.service.inflight_count == index + 1:
                    break
                time.sleep(0.01)
    served.model.gate.set()
    for thread in threads:
        thread.join(10)
    assert [call["sim_time_s"] for call in served.model.calls] == [0.0, 1.0, 2.0, 3.0]
    assert served.model.max_active == 1
    assert all(results[index]["outcome"] == "OK" for index in range(4))
    waits = [results[index]["timing"]["queue_wait_ms"] for index in range(4)]
    assert waits[0] <= waits[3]


def test_a_request_beyond_max_inflight_is_refused_from_its_header_without_running_the_model(rig):
    served = rig(max_inflight=1)
    served.model.gate = threading.Event()
    first = {}
    thread = threading.Thread(target=lambda: first.update(served.client("a").infer(observation(), sequence=1, deadline_ns=deadline(20))))
    thread.start()
    assert served.model.entered.wait(5)
    refused = served.client("b").infer(observation(), sequence=2, deadline_ns=deadline())
    assert refused["outcome"] == "QUEUE_FULL" and refused["reason"] == "MAX_INFLIGHT_REQUESTS" and refused["actions"] is None
    assert refused["sequence"] == 2 and refused["bundle_sha256"] == BUNDLE
    served.model.gate.set()
    thread.join(10)
    assert first["outcome"] == "OK" and len(served.model.calls) == 1
    health = served.client().query("policy_health_query")
    assert health["refused"] == 1 and health["served"] == 1 and health["inflight"] == 0


def test_a_request_that_waits_too_long_in_the_queue_times_out_and_never_runs(rig):
    served = rig(queue_timeout_s=0.1)
    served.model.gate = threading.Event()
    thread = threading.Thread(target=lambda: served.client("a").infer(observation(), sequence=1, deadline_ns=deadline(20)))
    thread.start()
    assert served.model.entered.wait(5)
    late = []
    waiter = threading.Thread(target=lambda: late.append(served.client("b").infer(observation(stamp=9.0), sequence=2,
                                                                                    deadline_ns=deadline(20))))
    waiter.start()
    time.sleep(0.4)
    served.model.gate.set()
    thread.join(10)
    waiter.join(10)
    assert late[0]["outcome"] == "QUEUE_TIMEOUT" and late[0]["actions"] is None
    assert all(call["sim_time_s"] != 9.0 for call in served.model.calls)


def test_a_request_past_its_own_deadline_when_it_arrives_is_not_run(rig):
    served = rig()
    description, payload = protocol.pack_observation(observation(), cameras=("head", "wrist"))
    expired = {"schema_version": 1, "kind": "policy_request", "request_id": "c0-r1", "client_id": "c0", "sequence": 1,
               "deadline_monotonic_ns": 1, "observation": description}
    slot = served.service.reserve()
    ticket = served.service.submit(expired, payload, slot)
    assert ticket.done.is_set() and ticket.response["outcome"] == "QUEUE_TIMEOUT"
    assert ticket.response["reason"] == "REQUEST_DEADLINE_EXCEEDED" and served.model.calls == []
    served.service.release(ticket)
    assert served.service.inflight_count == 0


def test_a_slow_model_call_is_reported_as_an_inference_timeout(rig):
    served = rig(inference_timeout_s=0.05)
    served.model.delay_s = 0.15
    reply = served.client().infer(observation(), sequence=1, deadline_ns=deadline())
    assert reply["outcome"] == "INFERENCE_TIMEOUT" and reply["actions"] is None
    assert reply["timing"]["inference_ms"] >= 100


def test_a_model_result_error_is_a_model_error_and_the_service_stays_available(rig):
    served = rig()
    served.model.error = ValueError("POLICY_ACTION_INVALID")
    reply = served.client().infer(observation(), sequence=1, deadline_ns=deadline())
    assert reply["outcome"] == "MODEL_ERROR" and "POLICY_ACTION_INVALID" in reply["reason"]
    served.model.error = None
    assert served.client().infer(observation(), sequence=2, deadline_ns=deadline())["outcome"] == "OK"


def test_a_model_infrastructure_fault_makes_the_service_unavailable_and_fails_closed(rig):
    served = rig()
    served.model.error = RuntimeError("CUDA error: device-side assert")
    reply = served.client().infer(observation(), sequence=1, deadline_ns=deadline())
    assert reply["outcome"] == "INFRA_ERROR"
    served.model.error = None
    after = served.client().infer(observation(), sequence=2, deadline_ns=deadline())
    assert after["outcome"] == "INFRA_ERROR" and "POLICY_MODEL_FAILED" in after["reason"]
    assert served.client().query("policy_health_query")["available"] is False
    assert len(served.model.calls) == 1


@pytest.mark.parametrize("changes,reason", [
    ({"cameras": ("wrist", "head")}, "CAMERAS_MISMATCH"),
])
def test_an_observation_that_does_not_fit_the_bundle_is_refused_before_the_model(rig, changes, reason):
    served = rig()
    reply = served.client(**changes).infer(observation(), sequence=1, deadline_ns=deadline())
    assert reply["outcome"] == "INPUT_INVALID" and reply["reason"] == reason and served.model.calls == []


def test_a_state_or_image_of_the_wrong_size_is_refused_before_the_model(rig):
    served = rig()
    short = observation()
    short["state"] = [0.0] * 3
    assert served.client().infer(short, sequence=1, deadline_ns=deadline())["reason"] == "STATE_DIM_MISMATCH"
    small = observation(head=np.zeros((2, 2, 3), np.uint8))
    assert served.client().infer(small, sequence=2, deadline_ns=deadline())["reason"] == "IMAGE_SHAPE_MISMATCH"
    assert served.model.calls == []


def test_a_client_that_expects_another_bundle_refuses_the_reply(rig):
    served = rig()
    with pytest.raises(ValueError, match="POLICY_RESPONSE_IDENTITY_MISMATCH"):
        served.client(bundle_sha256="e" * 64).infer(observation(), sequence=1, deadline_ns=deadline())
    with pytest.raises(ValueError, match="POLICY_RESPONSE_IDENTITY_MISMATCH"):
        served.client(service_generation="other").infer(observation(), sequence=1, deadline_ns=deadline())


def test_every_answer_is_audited_with_its_timing(rig):
    served = rig()
    served.client("a").infer(observation(), sequence=4, deadline_ns=deadline())
    served.client("b").infer(observation(), sequence=5, deadline_ns=deadline())
    rows = served.audit_rows
    assert [(row["client_id"], row["sequence"], row["outcome"]) for row in rows] == [("a", 4, "OK"), ("b", 5, "OK")]
    assert rows[0]["timing"]["inference_ms"] is not None


def test_close_proves_the_stop_and_keeps_the_socket_inode(rig):
    served = rig()
    served.client().infer(observation(), sequence=1, deadline_ns=deadline())
    server_stop, service_stop = served.close()
    assert server_stop["terminated"] is True and service_stop["terminated"] is True
    assert service_stop["outcomes"] == {"OK": 1}
    assert served.socket.exists() and os.stat(served.socket).st_ino == served.server.socket_inode
    with pytest.raises((OSError, ValueError)):
        served.client().infer(observation(), sequence=2, deadline_ns=deadline(1))


def test_a_second_server_will_not_take_over_an_existing_socket(rig, tmp_path):
    served = rig()
    other = PolicyUnixServer(service=served.service, socket_path=served.socket, receive_budget_s=1.0)
    with pytest.raises(ValueError, match="POLICY_SOCKET_ALREADY_EXISTS"):
        other.start()


def test_the_service_refuses_an_invalid_configuration():
    for changes in ({"max_inflight": 0}, {"queue_timeout_s": 0}, {"inference_timeout_s": float("inf")}, {"generation": ""}):
        arguments = dict(infer=lambda obs: ((0.0,),), identity=IDENTITY, generation="g", gpu_uuid="GPU-x", max_inflight=1,
                         queue_timeout_s=1.0, inference_timeout_s=1.0, max_frame_bytes=1 << 20)
        arguments.update(changes)
        with pytest.raises(ValueError, match="POLICY_SERVICE_CONFIG_INVALID"):
            PolicyService(**arguments)


def test_the_process_record_names_this_process():
    record = process_record()
    assert record["pid"] == os.getpid() and record["pgid"] == os.getpgrp()
    assert record["start_ticks"] > 0 and len(record["argv_sha256"]) == 64
