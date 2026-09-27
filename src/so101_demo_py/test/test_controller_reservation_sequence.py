"""Sequential ACT prefixes keep one owner but need distinct controller admissions."""

import pytest

from so101_demo.act.ownership import Ownership
from so101_demo.adapters.act.command_broker import CommandBroker


class SequentialDriver:
    def __init__(self):
        self.prepared = 0
        self.sent = []

    def prepare_goal(self, kind, goal):
        self.prepared += 1
        return f"goal-{self.prepared}", f"00000000-0000-4000-8000-{self.prepared:012x}"

    def send_prepared(self, goal_id, kind, goal, goal_uuid):
        self.sent.append((goal_id, kind, goal, goal_uuid))
        return goal_id

    def discard_prepared(self, goal_id):
        return False

    def stop_all(self, reason):
        pass

    def stopped(self):
        return True


class OneUseGoalPort:
    def __init__(self):
        self.reserved = set()
        self.armed = []

    def arm_generation(self, ticket):
        self.armed.append(ticket)
        return True

    def reserve(self, ticket, kind, goal, goal_uuid):
        key = (kind, ticket[0], goal_uuid)
        if key in self.reserved:
            return False
        self.reserved.add(key)
        return True

    def close_generation(self, generation):
        pass


def test_two_stopped_prefixes_under_one_owner_get_distinct_admissions():
    driver = SequentialDriver()
    controller = OneUseGoalPort()
    ownership = Ownership()
    broker = CommandBroker(driver, ownership=ownership, reservation_port=controller)
    response = broker.handle(dict(protocol_version=1, request_id="r", owner="act",
        session_id="session", attempt_id="attempt", lease_token="", operation="acquire"),
        "connection")
    assert response["accepted"]
    token = response["lease_token"]
    ticket = ownership.ticket(token, "act", "session", "attempt")

    first = broker.dispatch(ticket, "arm", {"sequence": 0})
    assert driver.stopped()
    second = broker.dispatch(ticket, "arm", {"sequence": 1})

    assert first != second
    assert len(controller.reserved) == 2
    assert len(driver.sent) == 2
    assert ownership.ticket(token, "act", "session", "attempt") == ticket
    assert controller.armed == [ticket]


def test_neck_search_goal_is_reserved_before_prepared_send():
    events = []

    class OrderedDriver(SequentialDriver):
        def prepare_goal(self, kind, goal):
            events.append("prepare")
            return super().prepare_goal(kind, goal)

        def send_prepared(self, goal_id, kind, goal, goal_uuid):
            events.append("send")
            return super().send_prepared(goal_id, kind, goal, goal_uuid)

    class OrderedPort(OneUseGoalPort):
        def reserve(self, ticket, kind, goal, goal_uuid):
            events.append("reserve")
            return super().reserve(ticket, kind, goal, goal_uuid)

    driver = OrderedDriver()
    controller = OrderedPort()
    ownership = Ownership()
    broker = CommandBroker(driver, ownership=ownership, reservation_port=controller)
    response = broker.handle(dict(protocol_version=1, request_id="r", owner="act",
        session_id="session", attempt_id="attempt", lease_token="", operation="acquire"),
        "connection")
    assert response["accepted"]
    ticket = ownership.ticket(response["lease_token"], "act", "session", "attempt")
    goal_id = broker.dispatch(ticket, "neck", {"target_rad": .1}, trusted_search_neck=True)
    assert goal_id == "goal-1"
    assert events == ["prepare", "reserve", "send"]
    assert ("neck", ticket[0], driver.sent[0][3]) in controller.reserved


def test_generic_neck_dispatch_refuses_before_goal_preparation():
    driver = SequentialDriver()
    controller = OneUseGoalPort()
    ownership = Ownership()
    broker = CommandBroker(driver, ownership=ownership, reservation_port=controller)
    response = broker.handle(dict(protocol_version=1, request_id="r", owner="act",
        session_id="session", attempt_id="attempt", lease_token="", operation="acquire"),
        "connection")
    assert response["accepted"]
    ticket = ownership.ticket(response["lease_token"], "act", "session", "attempt")
    with pytest.raises(PermissionError, match="NECK_SEARCH_PORT_REQUIRED"):
        broker.dispatch(ticket, "neck", {"target_rad": .1})
    assert driver.prepared == 0
    assert driver.sent == []
