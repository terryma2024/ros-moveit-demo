"""The local control history preserves order but grants no goal authority."""

import pytest

from so101_demo.act.control_event_timeline import (
    ControlEventTimeline,
    ControlHistoryUnavailable,
)
from so101_demo.act.ownership import Ownership
from so101_demo.adapters.act.command_broker import CommandBroker


def test_control_history_rejects_evicted_events_instead_of_certifying_a_gap():
    ticks = iter((100, 101, 102))
    timeline = ControlEventTimeline(capacity=2, monotonic_ns=lambda: next(ticks))
    timeline.record('owner_acquired', generation=1, owner='act', session_id='s', attempt_id='a')
    timeline.record('goal_send_enqueued', generation=1, goal_id='g')
    timeline.record('goal_response', generation=1, goal_id='g', detail='accepted')

    with pytest.raises(ControlHistoryUnavailable, match='CONTROL_HISTORY_GAP'):
        timeline.since(0)
    retained = timeline.since(1)
    assert [(item.sequence, item.wall_ns, item.kind) for item in retained] == [
        (2, 101, 'goal_send_enqueued'), (3, 102, 'goal_response')]


def test_control_history_rejects_clock_regression_and_future_cursor():
    ticks = iter((200, 199))
    timeline = ControlEventTimeline(capacity=4, monotonic_ns=lambda: next(ticks))
    timeline.record('owner_acquired', generation=1)
    timeline.record('owner_revoked', generation=2)
    with pytest.raises(ControlHistoryUnavailable, match='CONTROL_HISTORY_CLOCK'):
        timeline.since(0)
    with pytest.raises(ControlHistoryUnavailable, match='CONTROL_HISTORY_CURSOR'):
        timeline.since(3)


def test_control_history_returns_immutable_records_without_lease_token():
    timeline = ControlEventTimeline(capacity=2, monotonic_ns=lambda: 100)
    event = timeline.record('owner_acquired', generation=1, owner='act', session_id='s', attempt_id='a')
    with pytest.raises((AttributeError, TypeError)):
        event.kind = 'other'
    assert 'lease_token' not in vars(event)
    assert timeline.cursor() == 1


def test_ownership_records_generation_changes_and_confirmed_stop_in_order():
    ticks = iter(range(100, 110))
    timeline = ControlEventTimeline(monotonic_ns=lambda: next(ticks))
    owner = Ownership()
    owner.bind_control_events(timeline)
    token = owner.acquire('act', 's', 'a')
    owner.revoke('HAZARD')
    owner.confirm_stopped(True)
    assert [(event.kind, event.generation, event.owner, event.detail)
            for event in timeline.since(0)] == [
                ('owner_acquired', 1, 'act', None),
                ('owner_revoked', 2, 'act', 'HAZARD'),
                ('stop_confirmed', 2, None, None),
            ]
    assert all(token not in repr(event) for event in timeline.since(0))


def test_owner_attached_after_a_lease_marks_prior_history_unknown():
    timeline = ControlEventTimeline(monotonic_ns=iter(range(100, 120)).__next__)
    owner = Ownership()
    token = owner.acquire('act', 's', 'a')
    owner.bind_control_events(timeline)
    assert [(event.kind, event.generation, event.owner) for event in timeline.since(0)] == [
        ('owner_history_late_bind', 1, 'act')]
    owner.release(token, True)
    assert [event.kind for event in timeline.since(1)] == ['owner_released']


def test_broker_orders_submit_enqueue_before_registration_without_claiming_acceptance():
    timeline = ControlEventTimeline(monotonic_ns=iter(range(100, 120)).__next__)

    class Driver:
        def bind_control_events(self, control_events):
            self.events = control_events

        def submit(self, kind, goal):
            self.events.record('goal_send_enqueued', goal_id='g1', detail=kind)
            return 'g1'

    owner = Ownership()
    broker = CommandBroker(Driver(), ownership=owner, control_events=timeline)
    token = owner.acquire('teacher', 's', 'a')
    ticket = owner.ticket(token, 'teacher', 's', 'a')
    assert broker.dispatch(ticket, 'arm', {'trajectory': {}}) == 'g1'
    events = timeline.since(0)
    assert [event.kind for event in events] == [
        'owner_acquired', 'submit_begin', 'goal_send_enqueued', 'submit_registered']
    assert events[-1].goal_id == 'g1'
    assert not any(event.kind == 'goal_response' for event in events)


def test_ros_driver_records_send_and_real_action_response_as_separate_events():
    from concurrent.futures import Future
    from types import SimpleNamespace
    import threading
    import uuid
    from so101_demo.adapters.act.ros_broker import RosBrokerDriver

    response = Future()
    result = Future()

    class Client:
        def server_is_ready(self):
            return True

        def send_goal_async(self, goal, **options):
            return response

    driver = object.__new__(RosBrokerDriver)
    driver._lock = threading.RLock()
    driver._records = {}
    driver._statuses = {}
    driver._pending_writes = []
    driver.hazard_reason = None
    driver.clients = {'arm': Client()}
    driver.node = SimpleNamespace(get_clock=lambda: SimpleNamespace(
        now=lambda: SimpleNamespace(nanoseconds=1_000_000_000)))
    timeline = ControlEventTimeline(monotonic_ns=iter(range(100, 120)).__next__)
    driver.bind_control_events(timeline)

    native_uuid = str(uuid.uuid4())
    goal_id = driver.submit('arm', {'trajectory': {}}, goal_uuid=native_uuid)
    assert [event.kind for event in timeline.since(0)] == [
        'goal_send_begin', 'goal_send_enqueued']
    response.set_result(SimpleNamespace(accepted=True,
                                        goal_id=SimpleNamespace(uuid=list(uuid.UUID(native_uuid).bytes)),
                                        get_result_async=lambda: result))
    assert [(event.kind, event.goal_id, event.ros_goal_id, event.detail)
            for event in timeline.since(2)] == [
                ('goal_response', goal_id, uuid.UUID(native_uuid).hex, 'accepted')]


def test_ros_driver_retains_unknown_status_transition_even_if_next_status_is_empty():
    from types import SimpleNamespace
    import threading
    from so101_demo.adapters.act.ros_broker import RosBrokerDriver

    driver = object.__new__(RosBrokerDriver)
    driver._lock = threading.RLock()
    driver._records = {}
    driver._statuses = {}
    driver._status_received = {}
    driver.monotonic = lambda: 1.
    driver.unknown_goal_seen = False
    driver.hazard_reason = None
    timeline = ControlEventTimeline(monotonic_ns=iter(range(100, 120)).__next__)
    driver.bind_control_events(timeline)
    native_id = bytes.fromhex('11' * 16)
    active = SimpleNamespace(status_list=[SimpleNamespace(
        goal_info=SimpleNamespace(goal_id=SimpleNamespace(uuid=native_id)), status=2)])
    driver._status('arm', active)
    driver._status('arm', SimpleNamespace(status_list=[]))
    events = timeline.since(0)
    assert [event.kind for event in events] == [
        'action_status', 'unknown_goal', 'action_status']
    assert events[0].detail == 'arm|11111111111111111111111111111111:2'
    assert events[-1].detail == 'arm|'
    assert driver.hazard_reason == 'UNKNOWN_ACTIVE_GOAL'


def test_ros_driver_keeps_a_native_uuid_mismatch_response_in_control_history():
    from concurrent.futures import Future
    from types import SimpleNamespace
    import threading
    from so101_demo.adapters.act.ros_broker import RosBrokerDriver

    driver = object.__new__(RosBrokerDriver)
    driver._lock = threading.RLock()
    driver._records = {}
    driver._statuses = {}
    driver.hazard_reason = None
    driver.node = SimpleNamespace(get_clock=lambda: SimpleNamespace(
        now=lambda: SimpleNamespace(nanoseconds=1_000_000_000)))
    timeline = ControlEventTimeline(monotonic_ns=iter(range(100, 120)).__next__)
    driver.bind_control_events(timeline)
    driver._records['g'] = dict(accepted=None, handle=None, error=None,
                                ros_goal_id='11' * 16)
    response = Future()
    response.set_result(SimpleNamespace(accepted=True,
                                        goal_id=SimpleNamespace(uuid=bytes.fromhex('22' * 16))))
    driver._accepted('g', response)
    assert driver.hazard_reason == 'GOAL_UUID_MISMATCH'
    assert [(event.kind, event.goal_id, event.detail) for event in timeline.since(0)] == [
        ('goal_response', 'g', 'uuid_mismatch')]
