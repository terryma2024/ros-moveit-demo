"""A Task 8 source hazard must request physical stop off the ROS callback."""

import queue
import threading
from types import SimpleNamespace

from so101_demo.adapters.act.task8_sources import Task8HazardDispatcher


def test_hazard_enqueue_returns_while_owned_broker_stop_is_blocked():
    hazards = queue.SimpleQueue()
    cancelled = threading.Event()
    entered = threading.Event()
    release = threading.Event()

    class Broker:
        def __init__(self):
            self.reasons = []
            self.refreshes = 0

        def stop_all(self, reason):
            self.reasons.append(reason)
            entered.set()
            assert release.wait(2)

        def refresh_stop(self):
            self.refreshes += 1

        def stopped(self):
            return self.refreshes > 0

    broker = Broker()
    dispatcher = Task8HazardDispatcher(
        SimpleNamespace(take_hazard=lambda: hazards.get_nowait() if not hazards.empty() else None),
        broker, cancelled,
    )
    dispatcher.start()
    try:
        hazards.put_nowait("ROBOT_CONTACT_HAZARD")
        assert entered.wait(1)
        assert cancelled.is_set()
        assert not dispatcher.confirmed
        release.set()
        assert dispatcher.finished.wait(1)
        assert dispatcher.confirmed
        assert dispatcher.reason == "ROBOT_CONTACT_HAZARD"
        assert broker.reasons == ["TASK8_EVIDENCE_HAZARD"]
    finally:
        release.set()
        dispatcher.close()


def test_hazard_stop_error_stays_unconfirmed():
    hazards = queue.SimpleQueue()
    cancelled = threading.Event()

    class Broker:
        def stop_all(self, reason):
            raise RuntimeError("cancel response lost")

    dispatcher = Task8HazardDispatcher(
        SimpleNamespace(take_hazard=lambda: hazards.get_nowait() if not hazards.empty() else None),
        Broker(), cancelled,
    )
    dispatcher.start()
    try:
        hazards.put_nowait("SCENE_STATE_REORDERED")
        assert dispatcher.finished.wait(1)
        assert cancelled.is_set()
        assert not dispatcher.confirmed
        assert dispatcher.reason == "SCENE_STATE_REORDERED"
        assert isinstance(dispatcher.error, RuntimeError)
    finally:
        dispatcher.close()
