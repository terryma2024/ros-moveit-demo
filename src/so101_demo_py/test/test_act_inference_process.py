"""Task 13: one request in flight, and a late answer is refused rather than applied."""

from pathlib import Path

import pytest
import yaml

from so101_demo.act.runtime_config import load_runtime_config
from so101_demo.adapters.act.inference_process import ActInferenceProcess

PACKAGE = Path(__file__).resolve().parents[1]
RUNTIME = PACKAGE / "config/act/runtime.yaml"


class _Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class _Transport:
    def __init__(self, *, reply=None, closed=True):
        self.sent, self.replies, self._closed = [], [reply], closed

    def send(self, request):
        self.sent.append(request)

    def receive(self):
        return self.replies.pop(0) if self.replies else None

    def close(self):
        return self._closed


def _boundary(*, reply=None, closed=True, clock=None):
    clock = clock or _Clock()
    transport = _Transport(reply=reply, closed=closed)
    return ActInferenceProcess(config=load_runtime_config(RUNTIME), transport=transport, clock=clock), \
        transport, clock


def _observation():
    return {"sim_time_s": 1.0, "state": [0.0] * 8}


def test_the_frozen_runtime_config_is_accepted_and_its_drift_refused(tmp_path):
    document = load_runtime_config(RUNTIME)
    assert document["inference"]["device"] == "cuda"
    assert document["inference"]["queue_depth"] == 1
    for overrides, code in (({"device": "cpu"}, "RUNTIME_DEVICE_NOT_CUDA"),
                            ({"allow_cpu_fallback": True}, "RUNTIME_DEVICE_NOT_CUDA"),
                            ({"queue_depth": 4}, "RUNTIME_QUEUE_DEPTH_INVALID"),
                            ({"request_timeout_s": 0}, "RUNTIME_TIMEOUT_INVALID"),
                            ({"max_reply_age_s": -1}, "RUNTIME_TIMEOUT_INVALID")):
        raw = yaml.safe_load(RUNTIME.read_text())
        raw["inference"].update(overrides)
        path = tmp_path / "runtime.yaml"
        path.write_text(yaml.safe_dump(raw))
        with pytest.raises(ValueError, match=code):
            load_runtime_config(path)
    with pytest.raises(ValueError, match="RUNTIME_CONFIG_MISSING"):
        load_runtime_config(tmp_path / "absent.yaml")


def test_one_request_at_a_time_and_no_stale_or_misordered_reply_is_applied():
    boundary, transport, clock = _boundary(reply={"sequence": 1, "actions": [[0.0] * 6],
                                                   "age_s": 0.1})
    boundary.submit(_observation(), sequence=1)
    with pytest.raises(ValueError, match="INFERENCE_REQUEST_IN_FLIGHT"):
        boundary.submit(_observation(), sequence=2)          # never queued behind the first
    assert len(transport.sent) == 1
    taken = boundary.poll()
    assert taken["sequence"] == 1 and taken["age_s"] == 0.1

    # a reply for another sequence is refused, and so is one older than the configured age
    misordered, _t, _c = _boundary(reply={"sequence": 9, "actions": [], "age_s": 0.0})
    misordered.submit(_observation(), sequence=1)
    with pytest.raises(ValueError, match="INFERENCE_REPLY_OUT_OF_ORDER"):
        misordered.poll()
    stale, _t, _c = _boundary(reply={"sequence": 1, "actions": [], "age_s": 5.0})
    stale.submit(_observation(), sequence=1)
    with pytest.raises(ValueError, match="INFERENCE_REPLY_STALE"):
        stale.poll()


def test_a_timeout_a_bad_reply_and_a_worker_that_will_not_stop_are_all_refused():
    silent, _t, clock = _boundary()
    silent.submit(_observation(), sequence=1)
    assert silent.poll() == {}                               # still inside the window
    clock.now += 10.0
    with pytest.raises(ValueError, match="INFERENCE_TIMEOUT"):
        silent.poll()
    malformed, _t, _c = _boundary(reply={"sequence": 1})
    malformed.submit(_observation(), sequence=1)
    with pytest.raises(ValueError, match="INFERENCE_REPLY_INVALID"):
        malformed.poll()
    orphan, _t, _c = _boundary(closed=False)
    with pytest.raises(ValueError, match="INFERENCE_PROCESS_STILL_RUNNING"):
        orphan.close()
    assert orphan.closed is False                            # it is not marked closed while it runs
    with pytest.raises(ValueError, match="INFERENCE_NO_REQUEST"):
        _boundary()[0].poll()
    good, _t, _c = _boundary()
    good.close()
    with pytest.raises(ValueError, match="INFERENCE_PROCESS_CLOSED"):
        good.submit(_observation(), sequence=1)
