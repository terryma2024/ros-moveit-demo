"""The policy service command with a fake policy factory: records, readiness, serving, signals, the stop proof."""

import json
import os
import threading
import time

import numpy as np
import pytest

from so101_demo.cli import act_policy_service as cli
from so101_demo.runtime.act_policy.client import PolicyClient

BUNDLE_SHA = "1" * 64
POLICY_SHA = "2" * 64


class FakePolicy:
    def __init__(self):
        self.calls, self.resets = [], 0

    def infer(self, observation):
        self.calls.append(observation)
        return tuple(tuple(0.01 * row for _ in range(6)) for row in range(4))

    def reset(self):
        self.resets += 1


def arguments(tmp_path, **changes):
    ipc = tmp_path / "ipc"
    ipc.mkdir(mode=0o700, exist_ok=True)
    bundle = tmp_path / "bundle"
    bundle.mkdir(exist_ok=True)
    (bundle / "bundle.json").write_text("{}")
    values = ["--bundle-dir", str(bundle), "--socket", str(ipc / "policy.sock"), "--record-dir", str(tmp_path / "record"),
              "--generation", "gen-test", "--gpu-uuid", "GPU-00000000-0000-0000-0000-000000000000", "--max-inflight", "2",
              "--warm-up-calls", "2"]
    for name, value in changes.items():
        values += [f"--{name.replace('_', '-')}", str(value)]
    return values


@pytest.fixture
def fake_bundle(monkeypatch):
    identity = {"bundle_sha256": BUNDLE_SHA, "policy_sha256": POLICY_SHA, "cameras": ["head", "wrist"], "state_dim": 8,
                "image_shape": [4, 6, 3], "chunk_size": 4, "device": "cuda"}
    monkeypatch.setattr(cli, "bundle_identity", lambda args: ({"fake": True}, dict(identity)))
    return identity


def run_service(tmp_path, policy, stop, **kwargs):
    outcome = {}

    def target():
        outcome["code"] = cli.main(arguments(tmp_path, **kwargs), policy_factory=lambda *_: policy, stop=stop,
                                   install_signals=False)
    thread = threading.Thread(target=target)
    thread.start()
    ready = tmp_path / "record" / "ready.json"
    for _ in range(500):
        if ready.exists() or not thread.is_alive():
            break
        time.sleep(0.01)
    return thread, outcome


def test_the_service_writes_its_records_serves_a_request_and_proves_its_stop(tmp_path, fake_bundle):
    policy, stop = FakePolicy(), threading.Event()
    thread, outcome = run_service(tmp_path, policy, stop)
    try:
        record = json.loads((tmp_path / "record" / "process-record.json").read_text())
        assert record["pid"] == os.getpid() and record["kind"] == "ACT_POLICY_SERVICE_PROCESS"
        assert record["generation"] == "gen-test" and record["start_ticks"] > 0
        ready = json.loads((tmp_path / "record" / "ready.json").read_text())
        assert ready["ready"] is True and ready["bundle_sha256"] == BUNDLE_SHA and ready["policy_sha256"] == POLICY_SHA
        assert ready["cameras"] == ["head", "wrist"] and len(ready["warm_up_s"]) == 2 and ready["max_inflight"] == 2
        assert ready["socket"] == str(tmp_path / "ipc" / "policy.sock") and ready["socket_inode"] > 0
        assert policy.resets == 1 and len(policy.calls) == 2          # warm-up only, then a reset
        client = PolicyClient(socket_path=tmp_path / "ipc" / "policy.sock", client_id="c0", bundle_sha256=BUNDLE_SHA,
                              policy_sha256=POLICY_SHA, cameras=("head", "wrist"), max_frame_bytes=1 << 22,
                              service_generation="gen-test")
        obs = {"sim_time_s": 1.0, "state": [0.0] * 8, "head": np.zeros((4, 6, 3), np.uint8),
               "wrist": np.zeros((4, 6, 3), np.uint8)}
        reply = client.infer(obs, sequence=1, deadline_ns=time.monotonic_ns() + 5 * 10**9)
        assert reply["outcome"] == "OK" and len(reply["actions"]) == 4
    finally:
        stop.set()
        thread.join(10)
    assert outcome["code"] == 0
    proof = json.loads((tmp_path / "record" / "stop-proof.json").read_text())
    assert proof["terminated"] is True and proof["fault"] is None and proof["pid"] == os.getpid()
    assert proof["service"]["outcomes"] == {"OK": 1} and proof["socket_inode"] == ready["socket_inode"]
    rows = [json.loads(line) for line in (tmp_path / "record" / "requests.jsonl").read_text().splitlines()]
    assert [(row["client_id"], row["sequence"], row["outcome"]) for row in rows] == [("c0", 1, "OK")]
    assert (tmp_path / "ipc" / "policy.sock").exists()


def test_a_model_that_cannot_be_built_leaves_a_stop_proof_and_exit_one(tmp_path, fake_bundle):
    def broken(*_):
        raise RuntimeError("POLICY_SERVICE_CUDA_UNAVAILABLE")
    code = cli.main(arguments(tmp_path), policy_factory=broken, stop=threading.Event(), install_signals=False)
    assert code == 1
    proof = json.loads((tmp_path / "record" / "stop-proof.json").read_text())
    assert proof["terminated"] is True and "CUDA_UNAVAILABLE" in proof["fault"]
    assert (tmp_path / "record" / "process-record.json").exists() and not (tmp_path / "record" / "ready.json").exists()


@pytest.mark.parametrize("changes", [{"max_inflight": 0}, {"queue_timeout_s": 0}, {"warm_up_calls": 0}])
def test_invalid_arguments_are_refused_before_anything_is_created(tmp_path, fake_bundle, changes):
    code = cli.main(arguments(tmp_path, **changes), policy_factory=lambda *_: FakePolicy(), stop=threading.Event(),
                    install_signals=False)
    assert code == 2 and not (tmp_path / "record").exists()


def test_an_existing_record_dir_or_a_missing_socket_directory_is_refused(tmp_path, fake_bundle):
    (tmp_path / "record").mkdir()
    assert cli.main(arguments(tmp_path), policy_factory=lambda *_: FakePolicy(), install_signals=False) == 2
    other = tmp_path / "other"
    other.mkdir()
    values = arguments(other)
    values[values.index("--socket") + 1] = str(other / "nowhere" / "policy.sock")
    assert cli.main(values, policy_factory=lambda *_: FakePolicy(), install_signals=False) == 2


def test_a_relative_path_is_refused(tmp_path, fake_bundle):
    values = arguments(tmp_path)
    values[values.index("--record-dir") + 1] = "record"
    assert cli.main(values, policy_factory=lambda *_: FakePolicy(), install_signals=False) == 2


def test_a_second_service_on_the_same_socket_is_refused_and_still_proves_its_stop(tmp_path, fake_bundle):
    policy, stop = FakePolicy(), threading.Event()
    thread, outcome = run_service(tmp_path, policy, stop)
    try:
        second = tmp_path / "second"
        second.mkdir()
        values = arguments(tmp_path)
        values[values.index("--record-dir") + 1] = str(second / "record")
        code = cli.main(values, policy_factory=lambda *_: FakePolicy(), stop=threading.Event(), install_signals=False)
        assert code == 1
        assert "POLICY_SOCKET_ALREADY_EXISTS" in json.loads((second / "record" / "stop-proof.json").read_text())["fault"]
    finally:
        stop.set()
        thread.join(10)
    assert outcome["code"] == 0


def test_the_default_factory_refuses_when_cuda_is_absent(monkeypatch, tmp_path):
    torch = pytest.importorskip("torch")
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(RuntimeError, match="POLICY_SERVICE_CUDA_UNAVAILABLE"):
        cli.default_policy_factory(tmp_path, {}, "GPU-x")
