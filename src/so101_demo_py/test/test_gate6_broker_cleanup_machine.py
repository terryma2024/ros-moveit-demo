"""Phase 3b RED: one cleanup state machine for stop/revoke/release/failure cleanup.

Each test blocks a real controller/ROS call and requires the competing broker
operation to make progress; today the broker lock is held across those calls.
"""

import threading
import time

from so101_demo.act.ownership import Ownership


class _Driver:
    """Driver whose stop_all can be blocked to model a slow ROS stop."""

    def __init__(self, block_stop=False):
        self.stopped_flag = True
        self.stop_all_calls = []
        self.stop_entered = threading.Event()
        self.stop_release = threading.Event()
        self.block_stop = block_stop

    def stopped(self):
        return self.stopped_flag

    def stop_all(self, reason="STOP"):
        self.stop_all_calls.append(reason)
        if self.block_stop:
            self.stop_entered.set()
            self.stop_release.wait(5.0)
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


class _Port:
    """Legacy port whose close can be blocked to model a slow controller close."""

    def __init__(self, block_close=False):
        self.closed = []
        self.close_entered = threading.Event()
        self.close_release = threading.Event()
        self.block_close = block_close

    def arm_generation(self, ticket):
        return True

    def reserve(self, *a, **k):
        return True

    def close_generation(self, generation):
        self.closed.append(generation)
        if self.block_close:
            self.close_entered.set()
            self.close_release.wait(5.0)
        return True


def _request(operation, request_id="r1", token=None):
    return {"protocol_version": 1, "request_id": request_id, "owner": "act",
            "session_id": "session", "attempt_id": "attempt", "lease_token": token,
            "operation": operation}


def _broker(driver, port):
    import so101_demo.adapters.act.command_broker as module

    ownership = Ownership()
    broker = module.CommandBroker(driver, ownership=ownership, reservation_port=port)
    return broker, ownership


def test_release_progresses_while_the_controller_close_is_blocked():
    """RED: release currently closes the generation under the broker/ownership lock."""

    driver, port = _Driver(), _Port(block_close=True)
    broker, ownership = _broker(driver, port)
    acquired = broker.handle(_request("acquire"), "conn-1")
    assert acquired["accepted"] is True
    token = acquired["lease_token"]
    release_done = threading.Event()

    def run_release():
        broker.handle(_request("release", "r2", token), "conn-1")
        release_done.set()

    release_thread = threading.Thread(target=run_release, daemon=True)
    release_thread.start()
    assert port.close_entered.wait(5.0), "the release close was never entered"
    status_done = threading.Event()

    def run_status():
        broker.handle(_request("status", "r3", token), "conn-2")
        status_done.set()

    status_thread = threading.Thread(target=run_status, daemon=True)
    status_thread.start()
    observed = status_done.wait(1.0)
    port.close_release.set()
    release_thread.join(10.0)
    status_thread.join(5.0)
    assert observed, ("status could not be served while the release close was blocked: "
                      "the broker lock is held across the controller close")


def test_stop_attempt_progresses_while_driver_stop_all_is_blocked():
    """RED: revoke currently reaches driver.stop_all under the broker lock."""

    driver, port = _Driver(block_stop=True), _Port()
    broker, ownership = _broker(driver, port)
    acquired = broker.handle(_request("acquire"), "conn-1")
    assert acquired["accepted"] is True
    token = acquired["lease_token"]
    stop_done = threading.Event()

    def run_stop():
        broker.stop_attempt("CONCURRENT_REVOKE")
        stop_done.set()

    stop_thread = threading.Thread(target=run_stop, daemon=True)
    stop_thread.start()
    assert driver.stop_entered.wait(5.0), "driver.stop_all was never entered"
    status_done = threading.Event()

    def run_status():
        broker.handle(_request("status", "r2", token), "conn-2")
        status_done.set()

    status_thread = threading.Thread(target=run_status, daemon=True)
    status_thread.start()
    observed = status_done.wait(1.0)
    driver.stop_release.set()
    stop_thread.join(10.0)
    status_thread.join(5.0)
    assert observed, ("status could not be served while driver.stop_all was blocked: the "
                      "broker lock is held across the ROS stop call")


def test_second_acquire_is_refused_while_a_cleanup_is_pending():
    """A cleanup token must prevent a new generation until it is confirmed."""

    driver, port = _Driver(), _Port(block_close=True)
    broker, ownership = _broker(driver, port)
    acquired = broker.handle(_request("acquire"), "conn-1")
    assert acquired["accepted"] is True
    token = acquired["lease_token"]

    def run_release():
        broker.handle(_request("release", "r2", token), "conn-1")

    release_thread = threading.Thread(target=run_release, daemon=True)
    release_thread.start()
    assert port.close_entered.wait(5.0), "the release close was never entered"
    second = broker.handle(_request("acquire", "r3"), "conn-3")
    port.close_release.set()
    release_thread.join(10.0)
    assert second["accepted"] is False, (
        "a new acquire was accepted while the previous generation's close was still "
        "unconfirmed")


def test_late_old_close_ack_cannot_clear_a_newer_pending_state():
    """Stale cleanup readback must not finalise state owned by a newer attempt."""

    driver, port = _Driver(), _Port(block_close=True)
    broker, ownership = _broker(driver, port)
    acquired = broker.handle(_request("acquire"), "conn-1")
    assert acquired["accepted"] is True
    token = acquired["lease_token"]

    def run_release():
        broker.handle(_request("release", "r2", token), "conn-1")

    release_thread = threading.Thread(target=run_release, daemon=True)
    release_thread.start()
    assert port.close_entered.wait(5.0)
    port.close_release.set()
    release_thread.join(10.0)
    # after the cleanup is confirmed, control must be unavailable, not silently reused
    status = broker.handle(_request("status", "r4", token), "conn-4")
    assert status.get("state") != "RUNNING"


def test_late_old_close_cannot_clear_a_changed_pending_marker():
    """A cleanup that no longer matches the pending token must not finalize it."""

    driver, port = _Driver(), _Port(block_close=True)
    broker, ownership = _broker(driver, port)
    acquired = broker.handle(_request("acquire"), "conn-1")
    assert acquired["accepted"] is True
    token = acquired["lease_token"]
    release_thread = threading.Thread(
        target=lambda: broker.handle(_request("release", "r2", token), "conn-1"), daemon=True)
    release_thread.start()
    assert port.close_entered.wait(5.0)
    with broker._lock:
        original = broker._release_pending
        assert original is not None, "the pending marker must exist while the close is open"
        # a newer pending marker appears (a different ticket); the old cleanup must not
        # be able to clear it when it returns
        broker._release_pending = ("changed", None)
    port.close_release.set()
    release_thread.join(10.0)
    with broker._lock:
        assert broker._release_pending == ("changed", None), (
            "the stale cleanup cleared a newer pending marker")


def test_close_failure_keeps_the_owner_unavailable_and_latches_fencing():
    """Close failure: no IDLE, no new acquire, fault latched."""

    class _FailingPort(_Port):
        def close_generation(self, generation):
            self.closed.append(generation)
            raise RuntimeError("controller unreachable")

    driver, port = _Driver(), _FailingPort()
    broker, ownership = _broker(driver, port)
    acquired = broker.handle(_request("acquire"), "conn-1")
    assert acquired["accepted"] is True
    token = acquired["lease_token"]
    response = broker.handle(_request("release", "r2", token), "conn-1")
    assert response["accepted"] is False
    assert response.get("error") == "CONTROLLER_RESERVATION_CLOSE_UNCONFIRMED", response
    status = broker.handle(_request("status", "r3", token), "conn-2")
    assert status.get("state") != "RUNNING", status
    second = broker.handle(_request("acquire", "r4"), "conn-3")
    assert second["accepted"] is False, "a new acquire was admitted after a failed close"


def test_dispatch_is_blocked_while_a_release_is_unconfirmed():
    driver, port = _Driver(), _Port(block_close=True)
    broker, ownership = _broker(driver, port)
    acquired = broker.handle(_request("acquire"), "conn-1")
    token = acquired["lease_token"]
    release_thread = threading.Thread(
        target=lambda: broker.handle(_request("release", "r2", token), "conn-1"), daemon=True)
    release_thread.start()
    assert port.close_entered.wait(5.0)
    blocked = broker.handle(_request("renew", "r3", token), "conn-1")
    port.close_release.set()
    release_thread.join(10.0)
    assert blocked["accepted"] is False
    assert blocked.get("error") == "CONTROLLER_RELEASE_PENDING", blocked


def test_stale_stop_cleanup_cannot_clear_a_newer_pending_token():
    driver, port = _Driver(block_stop=True), _Port()
    broker, ownership = _broker(driver, port)
    acquired = broker.handle(_request("acquire"), "conn-1")
    assert acquired["accepted"] is True
    stop_thread = threading.Thread(target=lambda: broker.stop_attempt("REVOKE_ONE"), daemon=True)
    stop_thread.start()
    assert driver.stop_entered.wait(5.0), "driver.stop_all was never entered"
    with broker._lock:
        assert broker._cleanup_pending is not None, "the exact token must be pending"
        broker._cleanup_pending = ("newer", None, "REVOKE_TWO")
    driver.stop_release.set()
    stop_thread.join(10.0)
    with broker._lock:
        assert broker._cleanup_pending == ("newer", None, "REVOKE_TWO"), (
            "the stale cleanup cleared a newer pending token")


def test_dispatch_is_blocked_while_a_cleanup_is_unconfirmed():
    driver, port = _Driver(block_stop=True), _Port()
    broker, ownership = _broker(driver, port)
    acquired = broker.handle(_request("acquire"), "conn-1")
    token = acquired["lease_token"]
    stop_thread = threading.Thread(target=lambda: broker.stop_attempt("REVOKE"), daemon=True)
    stop_thread.start()
    assert driver.stop_entered.wait(5.0)
    blocked = broker.handle(_request("renew", "r2", token), "conn-1")
    driver.stop_release.set()
    stop_thread.join(10.0)
    assert blocked["accepted"] is False
    assert blocked.get("error") == "CONTROLLER_CLEANUP_PENDING", blocked


def test_logical_revoke_progresses_while_the_cleanup_io_is_blocked():
    driver, port = _Driver(block_stop=True), _Port()
    broker, ownership = _broker(driver, port)
    assert broker.handle(_request("acquire"), "conn-1")["accepted"] is True
    stop_thread = threading.Thread(target=lambda: broker.stop_attempt("REVOKE"), daemon=True)
    stop_thread.start()
    assert driver.stop_entered.wait(5.0)
    status_done = threading.Event()

    def run_status():
        broker.handle(_request("status", "r2"), "conn-2")
        status_done.set()

    status_thread = threading.Thread(target=run_status, daemon=True)
    status_thread.start()
    progressed = status_done.wait(1.0)
    driver.stop_release.set()
    stop_thread.join(10.0)
    status_thread.join(5.0)
    assert progressed, "a logical operation could not progress during cleanup I/O"
    assert ownership.state != "RUNNING"


def test_tick_progresses_logical_work_while_its_cleanup_io_is_blocked():
    """RED: tick() reaches controller close / driver.stop_all while holding the lock."""

    driver, port = _Driver(block_stop=True), _Port()
    broker, ownership = _broker(driver, port)
    assert broker.handle(_request("acquire"), "conn-1")["accepted"] is True
    ownership.revoke("EXTERNAL_REVOKE")          # logical revoke only; cleanup is pending
    tick_thread = threading.Thread(target=broker.tick, daemon=True)
    tick_thread.start()
    assert driver.stop_entered.wait(5.0), "tick never reached driver.stop_all"
    status_done = threading.Event()

    def run_status():
        broker.handle(_request("status", "r2"), "conn-2")
        status_done.set()

    status_thread = threading.Thread(target=run_status, daemon=True)
    status_thread.start()
    progressed = status_done.wait(1.0)
    driver.stop_release.set()
    tick_thread.join(10.0)
    status_thread.join(5.0)
    assert progressed, ("a logical operation could not progress while tick() was blocked in "
                        "cleanup I/O: tick performs socket/ROS calls under the broker lock")


def test_disconnect_progresses_logical_work_while_its_cleanup_io_is_blocked():
    """RED: disconnect() reaches controller close / driver.stop_all under the lock."""

    driver, port = _Driver(block_stop=True), _Port()
    broker, ownership = _broker(driver, port)
    assert broker.handle(_request("acquire"), "conn-1")["accepted"] is True
    disconnect_thread = threading.Thread(
        target=lambda: broker.disconnect("conn-1"), daemon=True)
    disconnect_thread.start()
    assert driver.stop_entered.wait(5.0), "disconnect never reached driver.stop_all"
    status_done = threading.Event()

    def run_status():
        broker.handle(_request("status", "r2"), "conn-2")
        status_done.set()

    status_thread = threading.Thread(target=run_status, daemon=True)
    status_thread.start()
    progressed = status_done.wait(1.0)
    driver.stop_release.set()
    disconnect_thread.join(10.0)
    status_thread.join(5.0)
    assert progressed, ("a logical operation could not progress while disconnect() was "
                        "blocked in cleanup I/O: disconnect performs socket/ROS calls "
                        "under the broker lock")


def test_server_close_progresses_logical_work_while_its_cleanup_io_is_blocked():
    """RED: UnixBrokerServer.close revokes + ticks (cleanup I/O) synchronously."""

    import so101_demo.adapters.act.command_broker as module

    driver, port = _Driver(block_stop=True), _Port()
    broker, ownership = _broker(driver, port)
    assert broker.handle(_request("acquire"), "conn-1")["accepted"] is True
    server = module.UnixBrokerServer.__new__(module.UnixBrokerServer)   # no socket needed
    server.broker, server._stop = broker, threading.Event()
    server._listener = None
    server._peers, server._peers_lock, server._threads = set(), threading.Lock(), []
    server._lock_file, server.path, server.parent_pid = None, None, None
    close_thread = threading.Thread(target=server.close, daemon=True)
    close_thread.start()
    assert driver.stop_entered.wait(5.0), "server.close never reached driver.stop_all"
    status_done = threading.Event()

    def run_status():
        broker.handle(_request("status", "r2"), "conn-2")
        status_done.set()

    status_thread = threading.Thread(target=run_status, daemon=True)
    status_thread.start()
    progressed = status_done.wait(1.0)
    driver.stop_release.set()
    close_thread.join(10.0)
    status_thread.join(5.0)
    assert progressed, ("a logical operation could not progress while server.close() was "
                        "blocked in cleanup I/O")


def test_parent_death_revokes_and_cleans_up_without_holding_the_broker_lock():
    """The _serve parent-death path must use the phased cleanup, not in-lock I/O."""

    import os
    import socket as _socket
    import uuid as _uuid
    import so101_demo.adapters.act.command_broker as module

    driver, port = _Driver(block_stop=True), _Port()
    broker, ownership = _broker(driver, port)
    assert broker.handle(_request("acquire"), "conn-1")["accepted"] is True

    path = f"/tmp/so101-debug-act-b3-parent-{_uuid.uuid4().hex[:8]}.sock"
    listener = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    listener.bind(path)
    os.chmod(path, 0o600)
    listener.listen(4)
    listener.settimeout(0.05)
    server = module.UnixBrokerServer.__new__(module.UnixBrokerServer)
    server.broker, server._stop = broker, threading.Event()
    server._listener, server._lock_file = listener, None
    server.path, server.parent_pid = path, 999999        # a pid that does not exist
    server._peers, server._peers_lock, server._threads = set(), threading.Lock(), []
    serve_thread = threading.Thread(target=server._serve, daemon=True)
    serve_thread.start()
    assert driver.stop_entered.wait(5.0), "the parent-death cleanup never reached stop_all"

    status_done = threading.Event()

    def run_status():
        broker.handle(_request("status", "r2"), "conn-2")
        status_done.set()

    status_thread = threading.Thread(target=run_status, daemon=True)
    status_thread.start()
    progressed = status_done.wait(1.0)
    driver.stop_release.set()
    serve_thread.join(10.0)
    status_thread.join(5.0)
    listener.close()
    try:
        os.unlink(path)
    except OSError:
        pass
    assert progressed, ("a logical operation could not progress during the parent-death "
                        "cleanup: the broker lock is held across the stop I/O")
    assert ownership.reason == "PARENT_DIED", ownership.reason
    assert server._stop.is_set(), "the server must stop after parent death"


def test_handle_driven_revoke_does_not_hold_the_broker_lock_across_the_close():
    """RED: a revoke observed inside handle() reaches the controller close in-lock."""

    driver, port = _Driver(), _Port(block_close=True)
    broker, ownership = _broker(driver, port)
    assert broker.handle(_request("acquire"), "conn-1")["accepted"] is True
    ownership.revoke("EXTERNAL_REVOKE")          # logical revoke; cleanup still pending
    status_thread = threading.Thread(
        target=lambda: broker.handle(_request("status", "r2"), "conn-1"), daemon=True)
    status_thread.start()
    assert port.close_entered.wait(5.0), "the handle-driven cleanup never reached the close"
    progressed = threading.Event()

    def run_other():
        broker.handle(_request("status", "r3"), "conn-3")
        progressed.set()

    other = threading.Thread(target=run_other, daemon=True)
    other.start()
    observed = progressed.wait(1.0)
    port.close_release.set()
    status_thread.join(10.0)
    other.join(5.0)
    assert observed, ("a concurrent operation could not progress while a handle-driven revoke "
                      "held the broker lock across the controller close")
