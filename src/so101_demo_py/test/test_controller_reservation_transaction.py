"""The broker must own a goal ticket before controller reservation and send."""

import threading

import pytest

from so101_demo.act.ownership import Ownership
from so101_demo.adapters.act.command_broker import CommandBroker


class PreparedDriver:
    def __init__(self):
        self.events = []
        self.broker = None
        self.fail_send = False
        self.change_goal_id = False
        self.discards = []

    def prepare_goal(self, kind, goal):
        self.events.append("prepare")
        return "local-goal", "11111111-1111-1111-1111-111111111111"

    def send_prepared(self, goal_id, kind, goal, goal_uuid):
        assert self.broker._goal_tickets[goal_id] == self.ticket
        assert self.events[-1] == "reserve"
        self.events.append("send")
        if self.fail_send:
            raise RuntimeError("SEND_UNCERTAIN")
        return "other-goal" if self.change_goal_id else goal_id

    def submit(self, kind, goal):
        raise AssertionError("legacy send must not run with a reservation port")

    def discard_prepared(self, goal_id):
        self.discards.append(goal_id)

    def stop_all(self, reason):
        self.events.append("stop")

    def stopped(self):
        return True


class ReservationPort:
    def __init__(self, driver):
        self.driver = driver
        self.fail_reserve = False
        self.fail_arm = False
        self.arm_error = None
        self.fail_close = False
        self.arms = []
        self.closes = []

    def arm_generation(self, ticket):
        self.arms.append(ticket)
        if self.arm_error is not None:
            raise self.arm_error
        return not self.fail_arm

    def reserve(self, ticket, kind, goal, goal_uuid):
        assert self.driver.broker._goal_tickets["local-goal"] == ticket
        assert self.driver.events == ["prepare"]
        assert kind == "arm"
        assert goal == {"trajectory": "fixed"}
        assert goal_uuid == "11111111-1111-1111-1111-111111111111"
        self.driver.events.append("reserve")
        return not self.fail_reserve

    def close_generation(self, generation):
        self.closes.append(generation)
        if getattr(self, "block_close", False):
            self.close_entered.set()
            self.close_release.wait(5.0)
        if self.fail_close:
            raise RuntimeError("CONTROLLER_RESERVATION_CLOSE_UNCONFIRMED")


def acquire_request(token=""):
    return dict(protocol_version=1, request_id="r", owner="act", session_id="session",
                attempt_id="attempt", lease_token=token, operation="acquire")


def prepared_broker():
    driver = PreparedDriver()
    port = ReservationPort(driver)
    ownership = Ownership()
    broker = CommandBroker(driver, ownership=ownership, reservation_port=port)
    driver.broker = broker
    response = broker.handle(acquire_request(), "connection")
    assert response["accepted"]
    token = response["lease_token"]
    ticket = ownership.ticket(token, "act", "session", "attempt")
    driver.ticket = ticket
    return broker, driver, port, ticket


def test_ticket_precedes_reservation_ack_and_native_uuid_send():
    broker, driver, port, ticket = prepared_broker()
    goal_id = broker.dispatch(ticket, "arm", {"trajectory": "fixed"})
    assert goal_id == "local-goal"
    assert driver.events == ["prepare", "reserve", "send"]
    assert broker._goal_tickets[goal_id] == ticket
    assert port.closes == []
    assert port.arms == [ticket]
    assert driver.discards == []


@pytest.mark.parametrize("failure", ["reserve", "send", "goal_id"])
def test_failed_or_uncertain_reservation_transaction_closes_generation(failure):
    broker, driver, port, ticket = prepared_broker()
    port.fail_reserve = failure == "reserve"
    driver.fail_send = failure == "send"
    driver.change_goal_id = failure == "goal_id"
    with pytest.raises((PermissionError, RuntimeError)):
        broker.dispatch(ticket, "arm", {"trajectory": "fixed"})
    assert port.closes == [ticket[0]]
    assert driver.discards == ["local-goal"]
    assert "local-goal" not in broker._goal_tickets
    assert broker.ownership.generation != ticket[0] or broker.ownership.state != "RUNNING"
    assert driver.events[-1] == "stop"
    if failure == "reserve":
        assert "send" not in driver.events


def test_reused_local_goal_id_does_not_erase_existing_ticket():
    broker, driver, port, ticket = prepared_broker()
    previous = (ticket[0] - 1, *ticket[1:])
    broker._goal_tickets["local-goal"] = previous
    with pytest.raises(RuntimeError, match="GOAL_ID_REUSED"):
        broker.dispatch(ticket, "arm", {"trajectory": "fixed"})
    assert broker._goal_tickets["local-goal"] == previous
    assert driver.events == ["prepare", "stop"]
    assert port.closes == [ticket[0]]
    assert driver.discards == ["local-goal"]


def test_partial_arm_rejection_closes_generation_before_reporting_lease():
    driver = PreparedDriver()
    port = ReservationPort(driver)
    port.fail_arm = True
    broker = CommandBroker(driver, ownership=Ownership(), reservation_port=port)
    driver.broker = broker
    response = broker.handle(acquire_request(), "connection")
    assert not response["accepted"]
    assert "lease_token" not in response
    assert len(port.arms) == 1
    assert port.closes == [port.arms[0][0]]
    assert driver.events == ["stop"]


def test_arm_timeout_replies_with_rejection_after_close_and_stop():
    driver = PreparedDriver()
    port = ReservationPort(driver)
    port.arm_error = TimeoutError("CONTROLLER_RESERVATION_TIMEOUT")
    broker = CommandBroker(driver, ownership=Ownership(), reservation_port=port)
    driver.broker = broker
    response = broker.handle(acquire_request(), "connection")
    assert not response["accepted"]
    assert response["error"] == "CONTROLLER_RESERVATION_TIMEOUT"
    assert "lease_token" not in response
    assert port.closes == [port.arms[0][0]]
    assert driver.events == ["stop"]


def test_uncertain_close_blocks_the_next_motion_lease():
    broker, driver, port, ticket = prepared_broker()
    invalidations = []
    broker.prefix_executor = type("PrefixInvalidator", (), {
        "invalidate": lambda self, reason: invalidations.append(reason),
    })()
    port.fail_close = True
    broker.disconnect("connection")
    assert port.closes == [ticket[0]]
    assert driver.events == ["stop"]
    assert invalidations == ["CLIENT_DISCONNECTED"]
    response = broker.handle(acquire_request(), "next-connection")
    assert not response["accepted"]
    assert response["error"] == "CONTROLLER_RESERVATION_CLOSE_UNCONFIRMED"


def test_direct_ownership_acquire_cannot_bypass_controller_arm():
    driver = PreparedDriver()
    port = ReservationPort(driver)
    ownership = Ownership()
    broker = CommandBroker(driver, ownership=ownership, reservation_port=port)
    driver.broker = broker
    token = ownership.acquire("act", "session", "attempt")
    ticket = ownership.ticket(token, "act", "session", "attempt")
    driver.ticket = ticket
    with pytest.raises(PermissionError, match="CONTROLLER_GENERATION_NOT_ARMED"):
        broker.dispatch(ticket, "arm", {"trajectory": "fixed"})
    assert "send" not in driver.events


def test_release_closes_armed_generation_before_owner_becomes_idle():
    broker, driver, port, ticket = prepared_broker()
    response = broker.handle(dict(acquire_request(ticket[1]), operation="release"),
                             "connection")
    assert response["accepted"]
    assert port.closes == [ticket[0]]
    assert broker.ownership.state == "IDLE"
    assert driver.events == []


def test_lease_expiry_closes_armed_generation_before_stop():
    now = [0.]
    driver = PreparedDriver()
    port = ReservationPort(driver)
    ownership = Ownership(monotonic=lambda: now[0], lease_timeout_s=1.)
    broker = CommandBroker(driver, ownership=ownership, reservation_port=port)
    driver.broker = broker
    response = broker.handle(acquire_request(), "connection")
    assert response["accepted"]
    ticket = ownership.ticket(response["lease_token"], "act", "session", "attempt")
    now[0] = 1.
    broker.tick()
    assert port.closes == [ticket[0]]
    assert driver.events == ["stop"]


def test_moveit_teacher_goal_stops_before_goal_preparation_without_proxy():
    broker, driver, port, ticket = prepared_broker()

    with pytest.raises(PermissionError, match="CONTROLLER_RESERVATION_ROUTE_UNAVAILABLE"):
        broker.dispatch(ticket, "execute_trajectory", {"trajectory": "fixed"})

    assert driver.events == ["stop"]
    assert port.closes == [ticket[0]]
    assert driver.discards == []
    assert broker.ownership.state != "RUNNING"


def _status_request(request_id="r2"):
    return dict(protocol_version=1, request_id=request_id, owner="act", session_id="session",
                attempt_id="attempt", lease_token="", operation="status")


def test_direct_dispatch_does_not_hold_the_broker_lock_across_the_close():
    """A reservation failure on the direct dispatch entry must clean up unlocked."""

    broker, driver, port, ticket = prepared_broker()
    port.fail_reserve = True
    port.block_close = True
    port.close_entered = threading.Event()
    port.close_release = threading.Event()
    outcome = {}

    def run_dispatch():
        try:
            broker.dispatch(ticket, "arm", {"trajectory": "fixed"})
        except Exception as failure:                      # noqa: BLE001
            outcome["error"] = failure

    dispatch_thread = threading.Thread(target=run_dispatch, daemon=True)
    dispatch_thread.start()
    assert port.close_entered.wait(5.0), "the dispatch cleanup never reached the close"

    progressed = threading.Event()

    def run_status():
        broker.handle(_status_request(), "connection-2")
        progressed.set()

    status_thread = threading.Thread(target=run_status, daemon=True)
    status_thread.start()
    observed = progressed.wait(1.0)
    port.close_release.set()
    dispatch_thread.join(10.0)
    status_thread.join(5.0)
    assert observed, ("a concurrent operation could not progress while the direct dispatch "
                      "held the broker lock across the controller close")


def _recovery_broker():
    """A broker whose lease belongs to a non-ACT owner, so submit is permitted."""

    driver = PreparedDriver()
    port = ReservationPort(driver)
    ownership = Ownership()
    broker = CommandBroker(driver, ownership=ownership, reservation_port=port)
    driver.broker = broker
    if not hasattr(driver, "validate"):
        driver.validate = lambda kind, goal: {"trajectory": "fixed"}
    request = dict(protocol_version=1, request_id="r1", owner="recovery", session_id="session",
                   attempt_id="attempt", lease_token="", operation="acquire")
    response = broker.handle(request, "connection")
    assert response["accepted"], response
    return broker, driver, port, response["lease_token"]


def test_handle_nested_submit_does_not_hold_the_broker_lock_across_the_close():
    """The handle submit path uses _dispatch_locked; handle's finalization drains unlocked."""

    broker, driver, port, token = _recovery_broker()
    port.fail_reserve = True
    port.block_close = True
    port.close_entered = threading.Event()
    port.close_release = threading.Event()
    submit = dict(protocol_version=1, request_id="r2", owner="recovery", session_id="session",
                  attempt_id="attempt", lease_token=token, operation="submit",
                  action_kind="arm", goal={"trajectory": "fixed"})
    outcome = {}

    def run_submit():
        try:
            broker.handle(submit, "connection")
        except Exception as failure:                      # noqa: BLE001
            outcome["error"] = failure

    submit_thread = threading.Thread(target=run_submit, daemon=True)
    submit_thread.start()
    assert port.close_entered.wait(5.0), "the nested submit cleanup never reached the close"

    progressed = threading.Event()

    def run_status():
        broker.handle(_status_request("r3"), "connection-2")
        progressed.set()

    status_thread = threading.Thread(target=run_status, daemon=True)
    status_thread.start()
    observed = progressed.wait(1.0)
    port.close_release.set()
    submit_thread.join(10.0)
    status_thread.join(5.0)
    assert observed, ("a concurrent operation could not progress while the handle-nested "
                      "dispatch held the broker lock across the controller close")
