"""A reserved controller goal keeps its identity until the actual action send."""

from concurrent.futures import Future
from types import SimpleNamespace
import threading
import uuid

import pytest

from so101_demo.adapters.act.ros_broker import RosBrokerDriver


class ActionClient:
    def __init__(self):
        self.sent = []

    def server_is_ready(self):
        return True

    def send_goal_async(self, goal, *, feedback_callback, goal_uuid):
        self.sent.append((goal, bytes(goal_uuid.uuid)))
        return Future()


def driver_fixture():
    driver = object.__new__(RosBrokerDriver)
    driver._lock = threading.RLock()
    driver._records = {}
    driver._pending_writes = []
    driver.hazard_reason = None
    driver.clients = {"arm": ActionClient()}
    driver.node = SimpleNamespace(get_clock=lambda: SimpleNamespace(
        now=lambda: SimpleNamespace(nanoseconds=0)))
    return driver


def test_prepare_has_no_action_side_effect_and_send_uses_exact_identity():
    driver = driver_fixture()
    goal = {"trajectory": [1, 2, 3]}
    goal_id, native_uuid = driver.prepare_goal("arm", goal)
    assert goal_id not in driver._records
    assert driver.clients["arm"].sent == []

    assert driver.send_prepared(goal_id, "arm", goal, native_uuid) == goal_id
    assert driver.clients["arm"].sent == [(goal, uuid.UUID(native_uuid).bytes)]
    assert driver._records[goal_id]["ros_goal_id"] == uuid.UUID(native_uuid).hex
    with pytest.raises(RuntimeError, match="PREPARED_GOAL_INVALID"):
        driver.send_prepared(goal_id, "arm", goal, native_uuid)


@pytest.mark.parametrize("change", ["goal", "kind", "uuid"])
def test_changed_prepared_goal_cannot_reach_action_client(change):
    driver = driver_fixture()
    goal = {"trajectory": [1, 2, 3]}
    goal_id, native_uuid = driver.prepare_goal("arm", goal)
    arguments = [goal_id, "arm", goal, native_uuid]
    arguments[{"kind": 1, "goal": 2, "uuid": 3}[change]] = {
        "kind": "gripper", "goal": {"trajectory": [4, 5, 6]},
        "uuid": str(uuid.uuid4()),
    }[change]
    with pytest.raises(RuntimeError, match="PREPARED_GOAL_INVALID"):
        driver.send_prepared(*arguments)
    assert driver.clients["arm"].sent == []
    assert driver.discard_prepared(goal_id) is True
    assert driver.discard_prepared(goal_id) is False
