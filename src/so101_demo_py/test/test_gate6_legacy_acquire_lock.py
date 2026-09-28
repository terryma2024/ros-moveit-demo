"""Phase 3b: the legacy arm path must not hold the broker lock across socket I/O."""

import threading
import time

from so101_demo.act.ownership import Ownership


class _Driver:
    def __init__(self):
        self.stopped_flag = True
        self.stop_all_calls = []

    def stopped(self):
        return self.stopped_flag

    def stop_all(self, reason="STOP"):
        self.stop_all_calls.append(reason)
        self.stopped_flag = True
        return True

    def bind_control_events(self, events):
        return True

    def ready(self):
        return True

    def refresh_stop(self):
        return True

    def validate(self, *a, **k):
        return True

    def prepare_goal(self, *a, **k):
        return "uuid-1"

    def send_prepared(self, *a, **k):
        return True

    def discard_prepared(self, *a, **k):
        return True


class _BlockingPort:
    """Legacy reservation port whose arm blocks, standing in for slow socket I/O."""

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.closed = []

    def arm_generation(self, ticket):
        self.entered.set()
        self.release.wait(5.0)
        return True

    def reserve(self, *a, **k):
        return True

    def close_generation(self, generation):
        self.closed.append(generation)
        return True


def _request(request_id="r1"):
    return {"protocol_version": 1, "request_id": request_id, "owner": "act",
            "session_id": "session", "attempt_id": "attempt", "lease_token": None,
            "operation": "acquire"}


def test_stop_attempt_completes_while_legacy_arm_is_blocked():
    import so101_demo.adapters.act.command_broker as module

    port = _BlockingPort()
    driver, ownership = _Driver(), Ownership()
    broker = module.CommandBroker(driver, ownership=ownership, reservation_port=port)
    outcome = {}

    def run_acquire():
        try:
            outcome["response"] = broker.handle(_request(), "conn-1")
        except Exception as failure:                       # noqa: BLE001
            outcome["error"] = failure

    thread = threading.Thread(target=run_acquire, daemon=True)
    thread.start()
    assert port.entered.wait(5.0), "the legacy arm barrier was never reached"
    stop_done = threading.Event()

    def run_stop():
        broker.stop_attempt("CONCURRENT_REVOKE")
        stop_done.set()

    stop_thread = threading.Thread(target=run_stop, daemon=True)
    stop_thread.start()
    completed_while_io = stop_done.wait(1.0)
    port.release.set()
    thread.join(10.0)
    stop_thread.join(5.0)
    assert completed_while_io, (
        "stop_attempt could not complete while the legacy arm was blocked: the broker "
        "lock is held across the controller arm socket exchange")
    assert (outcome.get("response") or {}).get("lease_token") is None
