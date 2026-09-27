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

    def stop_all(self, reason):
        self.events.append("stop")

    def stopped(self):
        return True


class ReservationPort:
    def __init__(self, driver):
        self.driver = driver
        self.fail_reserve = False
        self.closes = []

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


def prepared_broker():
    driver = PreparedDriver()
    port = ReservationPort(driver)
    ownership = Ownership()
    broker = CommandBroker(driver, ownership=ownership, reservation_port=port)
    driver.broker = broker
    token = ownership.acquire("act", "session", "attempt")
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


@pytest.mark.parametrize("failure", ["reserve", "send", "goal_id"])
def test_failed_or_uncertain_reservation_transaction_closes_generation(failure):
    broker, driver, port, ticket = prepared_broker()
    port.fail_reserve = failure == "reserve"
    driver.fail_send = failure == "send"
    driver.change_goal_id = failure == "goal_id"
    with pytest.raises((PermissionError, RuntimeError)):
        broker.dispatch(ticket, "arm", {"trajectory": "fixed"})
    assert port.closes == [ticket[0]]
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
