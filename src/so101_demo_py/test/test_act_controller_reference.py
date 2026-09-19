"""Future references come from the real controller query, never measured q."""
from concurrent.futures import Future
import threading
from types import SimpleNamespace
import pytest
from control_msgs.srv import QueryTrajectoryState
from so101_demo.adapters.act.ros_broker import RosBrokerDriver


def driver():
    port=object.__new__(RosBrokerDriver);port._lock=threading.RLock();port.monotonic=lambda:10.
    port.max_age=.15;port.stop_velocity=.002;port.reference_timeout_s=.03
    port._references={'arm':((.1,)*5,(.5,)*5,10.,1.),'gripper':((1.,),(0.,),10.,1.)}
    port._records={'g':dict(kind='arm',accepted=True,result=None,cancel_requested=False,ros_goal_id='11'*16,accepted_sim_s=.9)}
    port._received=10.;port._positions=(999.,)*6
    port.node=SimpleNamespace(get_clock=lambda:SimpleNamespace(now=lambda:SimpleNamespace(nanoseconds=1000000000)))
    port._query_clients={};return port


class Query:
    def __init__(self,kind,*,success=True):self.kind=kind;self.requests=[];self.success=success
    def service_is_ready(self):return True
    def call_async(self,request):
        self.requests.append(request)
        future=Future();n=5 if self.kind=='arm' else 1
        future.set_result(QueryTrajectoryState.Response(success=self.success,name=[str(i+1) for i in range(n)] if n==5 else ['6'],
            position=[.12]*n,velocity=[.5]*n,acceleration=[0.]*n))
        return future


def test_moving_future_splice_uses_actual_controller_query_with_requested_stamp():
    port=driver();query=Query('arm');port._query_clients={'arm':query,'gripper':Query('gripper')}
    assert port.current_reference(1.04)==(.12,)*5+(1.,)
    assert len(query.requests)==1 and query.requests[0].time.sec==1 and query.requests[0].time.nanosec==40000000


@pytest.mark.parametrize('overrides',({'accepted':None},{'cancel_requested':True},{'result':SimpleNamespace(status=5)}))
def test_unknown_or_cancelled_goal_cannot_supply_moving_reference(overrides):
    port=driver();port._records['g'].update(overrides);port._query_clients={'arm':Query('arm')}
    with pytest.raises(RuntimeError,match='REFERENCE_INTERVAL_INVALID'):port.current_reference(1.04)


def test_controller_query_failure_or_wrong_names_never_falls_back_to_measured_q():
    port=driver();port._query_clients={'arm':Query('arm',success=False)}
    with pytest.raises(RuntimeError,match='REFERENCE_QUERY_INVALID'):port.current_reference(1.04)
    port=driver()
    class Wrong(Query):
        def call_async(self,request):
            f=super().call_async(request);result=f.result();result.name=list(reversed(result.name));return f
    port._query_clients={'arm':Wrong('arm')}
    with pytest.raises(RuntimeError,match='REFERENCE_QUERY_INVALID'):port.current_reference(1.04)


def test_stationary_current_reference_does_not_hide_scheduled_future_motion():
    port=driver();port._references['arm']=((.1,)*5,(0.,)*5,10.,1.)
    query=Query('arm');port._query_clients={'arm':query}
    assert port.current_reference(1.04)==(.12,)*5+(1.,)
    assert len(query.requests)==1


def test_query_wait_leaves_driver_lock_available_to_independent_stop():
    import time
    port=driver();port.monotonic=lambda:10.+time.monotonic()-started
    future=Future()
    class Pending(Query):
        def call_async(self,request):return future
    port._query_clients={'arm':Pending('arm')};result=[];started=time.monotonic()
    def query():
        try:port.current_reference(1.04)
        except RuntimeError as error:result.append(str(error))
    worker=threading.Thread(target=query);worker.start()
    assert port._lock.acquire(timeout=.005)
    try:port._records['g']['cancel_requested']=True
    finally:port._lock.release()
    worker.join(.1)
    assert not worker.is_alive() and result==['REFERENCE_INTERVAL_INVALID']


def test_newer_publication_during_query_does_not_invalidate_same_accepted_interval():
    port=driver();port._references['arm']=((.1,)*5,(.5,)*5,10.,1.002)
    query=Query('arm');port._query_clients={'arm':query}
    assert port.current_reference(1.)==(.12,)*5+(1.,)
    assert query.requests[0].time.sec==1 and query.requests[0].time.nanosec==0


@pytest.mark.parametrize('accepted', [1.001,None])
def test_past_query_without_proven_actual_accepted_interval_is_denied(accepted):
    port=driver();port._references['arm']=((.1,)*5,(.5,)*5,10.,1.002)
    if accepted is None:port._records['g'].pop('accepted_sim_s')
    else:port._records['g']['accepted_sim_s']=accepted
    query=Query('arm');port._query_clients={'arm':query}
    with pytest.raises(RuntimeError,match='REFERENCE_TIME_INVALID'):port.current_reference(1.)
    assert not query.requests


def test_past_stationary_cache_cannot_replace_an_actual_historical_query():
    port=driver();port._references['arm']=((.1,)*5,(0.,)*5,10.,1.002);port._records={}
    with pytest.raises(RuntimeError,match='REFERENCE_TIME_INVALID'):port.current_reference(1.)


def test_faulted_idle_refreshes_real_negative_stop_proof_without_clearing_fault():
    port=driver();events=[];port.hazard_reason='UNKNOWN_ACTIVE_GOAL';port._records={}
    port._read_stop_baseline=lambda:None;port._refresh_paused_audit=lambda:None
    port._stop_confirmed_at=8.
    port._request_stop_baseline=lambda **kw:events.append(kw)
    port.refresh_idle()
    assert events==[dict(allow_existing=False)] and port.hazard_reason=='UNKNOWN_ACTIVE_GOAL'
