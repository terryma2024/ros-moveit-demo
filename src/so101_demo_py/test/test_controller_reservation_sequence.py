"""Sequential ACT prefixes keep one owner but need distinct controller admissions."""

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
    token = ownership.acquire("act", "session", "attempt")
    ticket = ownership.ticket(token, "act", "session", "attempt")

    first = broker.dispatch(ticket, "arm", {"sequence": 0})
    assert driver.stopped()
    second = broker.dispatch(ticket, "arm", {"sequence": 1})

    assert first != second
    assert len(controller.reserved) == 2
    assert len(driver.sent) == 2
    assert ownership.ticket(token, "act", "session", "attempt") == ticket
