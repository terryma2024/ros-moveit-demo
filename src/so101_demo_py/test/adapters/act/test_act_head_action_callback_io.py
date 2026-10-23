"""A stalled ROS RPC must not hold Head feedback locks or its executor callback."""

from concurrent.futures import Future
import threading

import pytest

from test_act_head_feedback_freshness import setup_ports, sample


class BlockingHandle:
    accepted = True

    def __init__(self, blocked):
        self.blocked = blocked
        self.entered = threading.Event()
        self.cancel_entered = threading.Event()
        self.release = threading.Event()

    def get_result_async(self):
        if self.blocked == 'result':
            self.entered.set()
            assert self.release.wait(2)
        return Future()

    def cancel_goal_async(self):
        self.cancel_entered.set()
        if self.blocked == 'cancel':
            self.entered.set()
            assert self.release.wait(2)
        return Future()


def record(handle, *, accepted=None, cancel=False):
    return dict(accepted=accepted, handle=handle, result=None,
                cancel_requested=cancel, cancel_ack=False, error=None)


@pytest.mark.parametrize('blocked', ['result', 'cancel'])
def test_head_rpc_stall_leaves_callback_and_original_feedback_available(monkeypatch, blocked):
    _, _, port, _, _, _, _ = setup_ports(monkeypatch)
    message=sample()
    handle = BlockingHandle(blocked)
    port._goals['owned'] = record(handle, accepted=True if blocked == 'cancel' else None)
    response = Future(); response.set_result(handle)
    returned = threading.Event(); feedback_done = threading.Event()

    def invoke():
        try:
            if blocked == 'result':port._accepted('owned', response)
            else:port.cancel('owned')
        finally:returned.set()

    caller = threading.Thread(target=invoke)
    reader = threading.Thread(target=lambda: (port._feedback(message), feedback_done.set()))
    caller.start()
    try:
        assert handle.entered.wait(.2)
        cache_available=port._lock.acquire(timeout=.01)
        if cache_available:port._lock.release()
        assert cache_available, 'SDK RPC held the original feedback cache lock'
        reader.start()
        feedback_available = feedback_done.wait(.01)
        callback_available = returned.wait(.01)
        assert feedback_available, 'SDK RPC held the original feedback cache lock'
        assert callback_available, 'Head callback waited for SDK RPC completion'
    finally:
        handle.release.set()
        caller.join(2)
        if reader.ident is not None:reader.join(2)
        if hasattr(port, 'close_head_io'):port.close_head_io(timeout_s=1.)


def test_pending_cancel_starts_independently_of_a_stalled_result_request(monkeypatch):
    _, _, port, _, _, _, _ = setup_ports(monkeypatch)
    handle = BlockingHandle('result')
    port._goals['owned'] = record(handle, cancel=True)
    response = Future(); response.set_result(handle)
    caller = threading.Thread(target=lambda: port._accepted('owned', response))
    caller.start()
    try:
        assert handle.entered.wait(.2)
        assert handle.cancel_entered.wait(.01), 'Cancellation waited for the stalled result RPC'
    finally:
        handle.release.set();caller.join(2)
        if hasattr(port, 'close_head_io'):port.close_head_io(timeout_s=1.)


def test_sdk_result_failure_preserves_known_acceptance_and_closes_send(monkeypatch):
    _, _, port, _, _, _, _ = setup_ports(monkeypatch)
    failed = threading.Event()
    port._head_fault_callback=lambda reason: failed.set()
    class BadHandle:
        accepted=True
        def get_result_async(self):raise RuntimeError('observed SDK failure')
    handle=BadHandle();port._goals['owned']=record(handle)
    response=Future();response.set_result(handle)
    try:
        port._accepted('owned',response)
        assert failed.wait(.2)
        assert port.accepted('owned') is True
        assert port.result('owned') is None
        with pytest.raises(PermissionError):port.send({})
    finally:port.close_head_io(timeout_s=1.)


def test_full_cancellation_queue_refuses_send_and_cannot_reopen(monkeypatch):
    _, _, port, _, _, _, _ = setup_ports(monkeypatch)
    handle=BlockingHandle('cancel')
    port._goals['running']=record(handle,accepted=True)
    try:
        port.cancel('running');assert handle.entered.wait(.2)
        for index in range(33):
            gid=f'pending-{index}'
            port._goals[gid]=record(handle,accepted=True)
            port.cancel(gid)
        assert port._head_policy_binding_failed is True
        assert 'QUEUE_FULL' in port._goals['pending-32']['error']
        with pytest.raises(PermissionError):port.send({})
        handle.release.set()
        port.cancel('pending-32')
        with pytest.raises(PermissionError):port.send({})
    finally:
        handle.release.set();port.close_head_io(timeout_s=1.)


def test_pending_cancel_is_dispatched_once_after_acceptance(monkeypatch):
    _, _, port, _, _, _, _ = setup_ports(monkeypatch)
    calls=[];done=threading.Event()
    class Handle:
        accepted=True
        def get_result_async(self):return Future()
        def cancel_goal_async(self):calls.append('cancel');done.set();return Future()
    handle=Handle();port._goals['owned']=record(None)
    port.cancel('owned')
    response=Future();response.set_result(handle)
    try:
        port._accepted('owned',response);assert done.wait(.2)
        port.cancel('owned');port._cancel_handle('owned')
        assert calls==['cancel']
    finally:port.close_head_io(timeout_s=1.)


def test_raising_worker_error_handler_closes_queue_before_reporting():
    from so101_demo.adapters.act.head_callback_io import HeadCallbackIO
    worker=HeadCallbackIO('head-error-control')
    reported=threading.Event()
    def operation():raise RuntimeError('SDK failure')
    def report(error):
        reported.set()
        raise RuntimeError('fault reporter failure')
    try:
        worker.submit(operation,report)
        assert reported.wait(.2)
        with pytest.raises(PermissionError,match='HEAD_CALLBACK_IO_CLOSED'):
            worker.submit(lambda:None,lambda error:None)
    finally:worker.close(timeout_s=1.)


def test_pending_cancel_survives_result_queue_failure_and_raising_fault_handler(monkeypatch):
    _, _, port, _, _, _, _ = setup_ports(monkeypatch)
    handle=BlockingHandle(None);port._goals['owned']=record(handle,cancel=True)
    response=Future();response.set_result(handle)
    port._head_io['result'].close(timeout_s=1.)
    def broken_report(reason):raise RuntimeError('fault reporter failure')
    port._head_fault_callback=broken_report
    try:
        port._accepted('owned',response)
        assert handle.cancel_entered.wait(.2)
        assert port.accepted('owned') is True
        assert port.result('owned') is None
        assert port._head_policy_binding_failed
        assert 'fault reporter failure' in port._head_fault_handler_error
    finally:port.close_head_io(timeout_s=1.)


@pytest.mark.parametrize('kind',['result','cancel'])
@pytest.mark.parametrize('raising_report',[False,True])
def test_exceptional_async_future_closes_head_admission(monkeypatch,kind,raising_report):
    _, _, port, _, _, _, _ = setup_ports(monkeypatch)
    handle=BlockingHandle(None);port._goals['owned']=record(handle,accepted=True)
    reported=[]
    def report(reason):
        reported.append(reason)
        if raising_report:raise RuntimeError('fault reporter failure')
    port._head_fault_callback=report
    future=Future();future.set_exception(RuntimeError('asynchronous SDK failure'))
    try:
        if kind=='result':port._result('owned',future)
        else:port._cancel_ack('owned',future)
        assert reported==['HEAD_CALLBACK_IO_FAILED']
        assert port._head_policy_binding_failed
        assert port.accepted('owned') is True
        assert port.result('owned') is None
        assert port._goals['owned']['cancel_ack'] is False
        with pytest.raises(PermissionError):port.send({})
        if raising_report:assert 'fault reporter failure' in port._head_fault_handler_error
    finally:port.close_head_io(timeout_s=1.)


@pytest.mark.parametrize('kind',['result','cancel'])
def test_async_failure_closes_before_any_exception_formatter(monkeypatch,kind):
    _,_,port,_,_,_,_=setup_ports(monkeypatch)
    port._goals['owned']=record(None,accepted=True)
    rendered=[];reported=[]
    class DiagnosticError(Exception):
        def __repr__(self):rendered.append(tuple(reported));return 'untrusted diagnostic'
    def fault(reason):
        assert port._head_policy_binding_failed
        assert not port._lock._is_owned()
        reported.append(reason)
        raise DiagnosticError('reporter failure')
    port._head_fault_callback=fault
    future=Future();future.set_exception(DiagnosticError('asynchronous SDK failure'))
    try:
        if kind=='result':port._result('owned',future)
        else:port._cancel_ack('owned',future)
        assert not rendered and reported==['HEAD_CALLBACK_IO_FAILED']
        assert port.accepted('owned') is True and port.result('owned') is None
    finally:port.close_head_io(timeout_s=1.)


def test_worker_error_closes_before_formatting_and_reports_original_exception():
    from so101_demo.adapters.act.head_callback_io import HeadCallbackIO
    worker=HeadCallbackIO('head-diagnostic-control');rendered=[];reported=threading.Event()
    class DiagnosticError(Exception):
        def __repr__(self):rendered.append(reported.is_set());return 'untrusted diagnostic'
    error=DiagnosticError('SDK failure')
    def operation():raise error
    def fault(original):
        assert original is error and worker._closed
        reported.set();raise DiagnosticError('reporter failure')
    try:
        worker.submit(operation,fault)
        assert reported.wait(1.)
        assert worker.close(timeout_s=1.)['retired'] is True
        assert not rendered
    finally:worker.close(timeout_s=1.)
