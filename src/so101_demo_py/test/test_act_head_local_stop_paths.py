"""Directed verification of the local stop paths, UNKNOWN reconciliation and worker independence.

This suite adds no behaviour: it verifies that every stop origin closes admission
with one immutable origin, that a blocked evidence sink cannot delay a normal stop,
that independent native-close / cancel / raw-stop work happens in parallel, and
that an UNKNOWN SDK UUID is cancelled by its exact original identity, keeps its
late terminal response, and is never re-sent.
"""

import threading
import time
import uuid

import pytest

from test_act_head_local_runtime import armed_runtime, runtime_setup, wait_for


STOP_ORIGINS = ['success', 'not_found', 'budget', 'camera', 'feedback', 'writer', 'unknown',
                'sigterm']


def unknown_goal(port, gid=None):
    gid = str(uuid.uuid4()) if gid is None else gid
    with port._lock:
        port._goals[gid] = dict(accepted=None, handle=None, result=None, cancel_requested=False,
                                cancel_ack=False, error=None, goal={})
    return gid


def cancel_requests(row):
    return [entry[1] for entry in row.calls if entry[0] == 'cancel_goal']


@pytest.mark.parametrize('origin', STOP_ORIGINS)
def test_every_stop_origin_closes_admission_with_one_immutable_origin(monkeypatch, origin):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    assert runtime.ready is True
    first = runtime.stop(origin)
    origin_wall = first['stop_origin_wall_s']
    assert first['stop_origin_kind'] == origin
    assert first['stop_deadline_wall_s'] == pytest.approx(
        origin_wall + row.policy.stop_confirmation_timeout_s, abs=1e-9)
    assert runtime.ready is False and runtime.stop_requested is True
    assert row.port._stop_epoch is not None
    assert row.port._stop_epoch['fault_wall_s'] == pytest.approx(origin_wall, abs=1e-9)
    with pytest.raises((PermissionError, ValueError)):
        runtime.dispatch_guard()
    time.sleep(.02)
    later = 'not_found' if origin != 'not_found' else 'success'
    runtime.stop(later)
    receipt = runtime.stop_receipt()
    assert receipt['stop_origin_kind'] == origin
    assert receipt['stop_origin_wall_s'] == origin_wall
    assert receipt['stop_deadline_wall_s'] == pytest.approx(
        origin_wall + row.policy.stop_confirmation_timeout_s, abs=1e-9)
    assert wait_for(lambda: row.revoker.closed == 1)
    assert wait_for(lambda: runtime.retirement_snapshot()['cancel_stop']['started_wall_s']
                    is not None)
    runtime.close(timeout_s=1.)


def test_blocked_evidence_sink_cannot_delay_a_normal_stop(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    release = threading.Event()
    row.sink.block = release
    stopped = {}
    thread = threading.Thread(target=lambda: stopped.setdefault('receipt', runtime.stop('camera')))
    thread.start()
    assert wait_for(lambda: row.port._stop_epoch is not None)
    assert wait_for(lambda: row.revoker.closed == 1)
    assert stopped == {}
    release.set()
    thread.join(2.)
    assert stopped['receipt']['stop_origin_kind'] == 'camera'
    assert any(kind == 'STOP_REQUEST' for kind, _, _ in row.sink.rows)
    runtime.close(timeout_s=1.)


def test_unknown_uuids_are_cancelled_by_original_identity_and_never_resent(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    first, second = unknown_goal(row.port), unknown_goal(row.port)
    receipt = runtime.stop('unknown')
    assert wait_for(lambda: len(cancel_requests(row)) == 2)
    sent = cancel_requests(row)
    identities = {bytes(request.goal_info.goal_id.uuid) for request in sent}
    assert identities == {uuid.UUID(first).bytes, uuid.UUID(second).bytes}
    for gid in (first, second):
        assert row.port._goals[gid]['cancel_requested'] is True
    assert not [entry for entry in row.calls if entry[0] == 'send']
    assert row.port._head_policy_binding_failed is False
    assert receipt['stop_origin_kind'] == 'unknown'
    assert receipt['physical_stop_confirmed'] in (True, False)
    row.port.close_head_io(timeout_s=1.)
    runtime.close(timeout_s=1.)


def test_unknown_uuid_keeps_its_late_terminal_response(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    gid = unknown_goal(row.port)
    runtime.stop('unknown')
    assert wait_for(lambda: len(cancel_requests(row)) == 1)
    row.clients['get_result'].statuses = [4]
    row.observer.request_result(gid)
    assert wait_for(lambda: row.port._goals[gid]['result'] is not None)
    record = row.port._goals[gid]
    assert record['accepted'] is True
    assert record['terminal_wall_s'] is not None and record['terminal_source_floor_ns'] is not None
    assert record['cancel_requested'] is True
    assert len(cancel_requests(row)) == 1
    assert row.state.faulted is False
    assert row.observer.snapshot()['action_status'] == {}
    row.port.close_head_io(timeout_s=1.)
    runtime.close(timeout_s=1.)


def test_callback_fault_stop_queries_result_without_acceptance_handle(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    gid = unknown_goal(row.port)
    row.clients['get_result'].statuses = [6]
    try:
        # The actual acceptance callback can fail before the search tick has
        # requested GetResult. Status alone cannot establish terminal Stop.
        row.port._head_io_failed(gid, TimeoutError('acceptance delivery lost'))
        assert wait_for(lambda: row.port._goals[gid]['result'] is not None, timeout_s=.2)
        record = row.port._goals[gid]
        assert record['accepted'] is True and record['handle'] is None
        assert record['result'].status == 6
        requests = [entry[1] for entry in row.calls if entry[0] == 'get_result']
        assert len(requests) == 1
        assert bytes(requests[0].goal_id.uuid) == uuid.UUID(gid).bytes
        assert wait_for(lambda: len(cancel_requests(row)) == 1)
        assert not [entry for entry in row.calls if entry[0] == 'send']
        receipt = runtime.stop_receipt()
        assert receipt['stop_origin_kind'] == 'fault'
        assert receipt['stop_deadline_wall_s'] == pytest.approx(
            receipt['stop_origin_wall_s'] + row.policy.stop_confirmation_timeout_s)
    finally:
        row.port.close_head_io(timeout_s=1.)
        runtime.close(timeout_s=1.)


def test_cancel_worker_progresses_while_the_native_transport_blocks(monkeypatch):
    row = runtime_setup(monkeypatch)
    block = threading.Event()
    row.revoker.block = block
    runtime = armed_runtime(row)
    gid = unknown_goal(row.port)
    runtime.fault('HEAD_LOCAL_TEST_NATIVE_BLOCKED')
    assert wait_for(lambda: len(cancel_requests(row)) == 1)
    assert row.port._goals[gid]['cancel_requested'] is True
    assert runtime.retirement_snapshot()['native_close']['finished'] is False
    # The cancel/raw-stop worker keeps observing the raw stop predicate until
    # the original physical-stop deadline; it is not blocked by the transport.
    assert runtime.retirement_snapshot()['cancel_stop']['started_wall_s'] is not None
    assert runtime.retirement_snapshot()['cancel_stop']['cancel_error'] is None
    block.set()
    assert wait_for(lambda: runtime.retirement_snapshot()['native_close']['ack'])
    runtime.close(timeout_s=1.)
