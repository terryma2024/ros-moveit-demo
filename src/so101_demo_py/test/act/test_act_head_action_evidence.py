"""Real callback boundaries must retain raw replies, not only cache verdicts."""
from concurrent.futures import Future
from types import SimpleNamespace
import uuid

import pytest

from action_msgs.msg import GoalInfo, GoalStatus, GoalStatusArray
from action_msgs.srv import CancelGoal
from builtin_interfaces.msg import Time
from control_msgs.action import FollowJointTrajectory
from unique_identifier_msgs.msg import UUID

from test_act_head_local_observer import inventory, wait_for
from test_act_head_local_runtime import runtime_setup


def resolved(value):
    future = Future()
    future.set_result(value)
    return future


def test_sdk_acceptance_result_and_cancel_keep_original_reply_and_callback_clock(monkeypatch):
    row = runtime_setup(monkeypatch)
    gid = str(uuid.uuid4())
    goal_id = UUID(uuid=list(uuid.UUID(gid).bytes))
    reply = FollowJointTrajectory.Impl.GetResultService.Response(status=4)
    reply.result.error_string = 'original terminal detail'
    cancel = CancelGoal.Response(return_code=0,
        goals_canceling=[GoalInfo(goal_id=goal_id, stamp=Time(sec=9, nanosec=7))])
    handle = SimpleNamespace(accepted=True, goal_id=goal_id, stamp=Time(sec=9, nanosec=7),
        get_result_async=lambda: resolved(reply), cancel_goal_async=lambda: resolved(cancel))
    inventory(row.port, gid, cancel_requested=True)
    try:
        row.port._accepted(gid, resolved(handle))
        assert wait_for(lambda: row.port._goals[gid]['result'] is not None)
        assert wait_for(lambda: row.port._goals[gid]['cancel_ack'])
        assert wait_for(lambda: len([kind for kind, _, _ in row.sink.rows
                                    if kind.startswith('HEAD_ACTION_')]) == 3)
        records = {kind: record for kind, record, stamp in row.sink.rows
                   if kind.startswith('HEAD_ACTION_')}
        assert set(records) == {'HEAD_ACTION_SDK_ACCEPTANCE', 'HEAD_ACTION_SDK_RESULT',
                                'HEAD_ACTION_SDK_CANCEL'}
        for record in records.values():
            assert record['goal_uuid'] == gid
            assert record['schema_version'] == 1
            assert record['callback_wall_ns'] > 0
            assert record['callback_sim_ns'] == 10_000_000_000
        assert records['HEAD_ACTION_SDK_ACCEPTANCE']['original']['accepted'] is True
        assert records['HEAD_ACTION_SDK_ACCEPTANCE']['original']['stamp'] == {'sec': 9, 'nanosec': 7}
        assert records['HEAD_ACTION_SDK_RESULT']['original']['status'] == 4
        assert records['HEAD_ACTION_SDK_RESULT']['original']['result'] == {
            'error_code': 0, 'error_string': 'original terminal detail'}
        assert records['HEAD_ACTION_SDK_CANCEL']['original']['goals_canceling'][0]['goal_id']['uuid'] == list(uuid.UUID(gid).bytes)
        assert not row.state.faulted
    finally:
        row.runtime.close(timeout_s=1.)


def test_independent_status_unknown_result_and_cancel_are_recorded_before_cache_summary(monkeypatch):
    row = runtime_setup(monkeypatch)
    gid = str(uuid.uuid4())
    goal_id = UUID(uuid=list(uuid.UUID(gid).bytes))
    inventory(row.port, gid)
    status = GoalStatus(goal_info=GoalInfo(goal_id=goal_id, stamp=Time(sec=8, nanosec=3)),
                        status=2)
    message = GoalStatusArray(status_list=[status])
    try:
        row.observer._status(message)
        row.observer._response(gid, 'result', resolved(
            FollowJointTrajectory.Impl.GetResultService.Response(status=0)))
        row.observer._response(gid, 'cancel', resolved(CancelGoal.Response(return_code=3)))
        records = {kind: record for kind, record, stamp in row.sink.rows
                   if kind.startswith('HEAD_ACTION_')}
        assert set(records) == {'HEAD_ACTION_STATUS', 'HEAD_ACTION_GET_RESULT', 'HEAD_ACTION_CANCEL'}
        assert records['HEAD_ACTION_STATUS']['original']['goal_info']['stamp'] == {'sec': 8, 'nanosec': 3}
        assert records['HEAD_ACTION_GET_RESULT']['original']['status'] == 0
        assert records['HEAD_ACTION_CANCEL']['original']['return_code'] == 3
        assert row.port.accepted(gid) is True and row.port.result(gid) is None
        assert row.port._goals[gid]['cancel_ack'] is False
        # Queued records must not change with the original ROS message object.
        status.status = 4
        assert records['HEAD_ACTION_STATUS']['original']['status'] == 2
    finally:
        row.runtime.close(timeout_s=1.)


def test_action_log_failure_does_not_lose_the_independent_terminal_callback(monkeypatch):
    row = runtime_setup(monkeypatch)
    gid = str(uuid.uuid4())
    inventory(row.port, gid)
    row.clients['get_result'].statuses = [6]
    try:
        row.sink.fail = True
        assert row.observer.request_result(gid)
        assert wait_for(lambda: row.port.result(gid) is not None)
        assert row.port.result(gid).status == 6
        assert row.state.faulted and row.runtime._stop_event.is_set()
        with pytest.raises(PermissionError):
            row.port.send({})
    finally:
        row.runtime.close(timeout_s=1.)
