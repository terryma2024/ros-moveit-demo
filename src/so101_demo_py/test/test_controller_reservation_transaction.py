"""The broker must own a goal ticket before controller reservation and send."""

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
