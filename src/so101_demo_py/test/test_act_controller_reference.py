"""Accepted controller goals and published desired state bound future references."""
import threading
from types import SimpleNamespace
import pytest
from control_msgs.action import FollowJointTrajectory
from trajectory_msgs.msg import JointTrajectoryPoint
from so101_demo.act.joints import ARM_JOINTS
from so101_demo.adapters.act.ros_broker import RosBrokerDriver


def driver():
    port=object.__new__(RosBrokerDriver);port._lock=threading.RLock();port.monotonic=lambda:10.
    port.max_age=.15;port.stop_velocity=.002
    port._references={'arm':((.1,)*5,(.5,)*5,10.,1.),'gripper':((1.,),(0.,),10.,1.)}
    port._records={'g':dict(kind='arm',accepted=True,result=None,cancel_requested=False,ros_goal_id='11'*16,accepted_sim_s=.9)}
    port._received=10.;port._positions=(999.,)*6
    port.node=SimpleNamespace(get_clock=lambda:SimpleNamespace(now=lambda:SimpleNamespace(nanoseconds=1000000000)))
    return port


def direct_arm_goal():
    goal = FollowJointTrajectory.Goal()
    goal.trajectory.joint_names = list(ARM_JOINTS[:5])
    goal.trajectory.header.stamp.sec = 1
    goal.trajectory.header.stamp.nanosec = 100_000_000
    first = JointTrajectoryPoint(positions=[.1] * 5)
    last = JointTrajectoryPoint(positions=[.2] * 5)
    last.time_from_start.nanosec = 200_000_000
    goal.trajectory.points = [first, last]
    return goal


def test_direct_accepted_trajectory_reconstructs_out_of_order_without_query():
    port = driver()
    port._records['g']['submitted_goal'] = direct_arm_goal()

    class ForbiddenQuery:
        def call_async(self, _request):
            raise AssertionError('mutable controller query must not run')

    port._query_clients = {'arm': ForbiddenQuery()}
    assert port.current_reference(1.2) == pytest.approx((.15,) * 5 + (1.,))
    assert port.current_reference(1.15) == pytest.approx((.125,) * 5 + (1.,))


def test_published_desired_disagreement_invalidates_reconstructed_interval():
    port = driver()
    port._records['g']['submitted_goal'] = direct_arm_goal()
    port._references['arm'] = ((.9,) * 5, (.5,) * 5, 10., 1.2)
    with pytest.raises(RuntimeError, match='REFERENCE_QUERY_INVALID'):
        port.current_reference(1.25)


def test_live_action_handle_is_not_copied_to_reconstruct_reference():
    port=driver();port._records['g']['submitted_goal']=direct_arm_goal()
    port._records['g']['handle']=threading.Lock()
    assert port.current_reference(1.15)==pytest.approx((.125,)*5+(1.,))


def test_two_live_goals_for_one_controller_are_ambiguous():
    port=driver();port._records['g']['submitted_goal']=direct_arm_goal()
    port._records['second']=dict(port._records['g'],ros_goal_id='22'*16)
    with pytest.raises(RuntimeError,match='REFERENCE_INTERVAL_INVALID'):
        port.current_reference(1.15)


def test_missing_zero_time_goal_anchor_is_not_reconstructed():
    port=driver();goal=direct_arm_goal()
    goal.trajectory.points[0].time_from_start.nanosec=10_000_000
    port._records['g']['submitted_goal']=goal
    with pytest.raises(RuntimeError,match='REFERENCE_RECONSTRUCTION_INVALID'):
        port.current_reference(1.15)


def test_cancelled_previous_goal_does_not_contaminate_new_interval():
    port=driver();port._records['g']['cancel_requested']=True
    port._records['new']=dict(port._records['g'],cancel_requested=False,
                              submitted_goal=direct_arm_goal(),ros_goal_id='22'*16)
    assert port.current_reference(1.15)==pytest.approx((.125,)*5+(1.,))


def test_moving_goal_without_exact_submitted_trajectory_fails_closed():
    port=driver()
    with pytest.raises(RuntimeError,match='REFERENCE_RECONSTRUCTION_UNAVAILABLE'):
        port.current_reference(1.15)


@pytest.mark.parametrize('overrides',({'accepted':None},{'cancel_requested':True},{'result':SimpleNamespace(status=5)}))
def test_unknown_or_cancelled_goal_cannot_supply_moving_reference(overrides):
    port=driver();port._records['g'].update(overrides)
    with pytest.raises(RuntimeError,match='REFERENCE_INTERVAL_INVALID'):port.current_reference(1.04)


def test_wrong_goal_joint_order_never_falls_back_to_measured_q():
    port=driver();goal=direct_arm_goal();goal.trajectory.joint_names.reverse()
    port._records['g']['submitted_goal']=goal
    with pytest.raises(RuntimeError,match='REFERENCE_RECONSTRUCTION_INVALID'):
        port.current_reference(1.15)


def test_stationary_current_reference_does_not_hide_scheduled_future_motion():
    port=driver();port._references['arm']=((.1,)*5,(0.,)*5,10.,1.)
    port._records['g']['submitted_goal']=direct_arm_goal()
    assert port.current_reference(1.15)==pytest.approx((.125,)*5+(1.,))


def test_reconstruction_leaves_driver_lock_available_to_independent_stop(monkeypatch):
    import so101_demo.adapters.act.ros_broker as broker
    port=driver();port._records['g']['submitted_goal']=direct_arm_goal()
    entered=threading.Event();release=threading.Event();result=[]
    actual=broker.direct_goal_reference
    def waiting(record,kind,when):
        entered.set();assert release.wait(1.)
        return actual(record,kind,when)
    monkeypatch.setattr(broker,'direct_goal_reference',waiting)
    def query():
        try:port.current_reference(1.15)
        except RuntimeError as error:result.append(str(error))
    worker=threading.Thread(target=query);worker.start()
    assert entered.wait(.5)
    assert port._lock.acquire(timeout=.005)
    try:port._records['g']['cancel_requested']=True
    finally:port._lock.release()
    release.set()
    worker.join(.1)
    assert not worker.is_alive() and result==['REFERENCE_INTERVAL_INVALID']


def test_newer_published_desired_validates_same_accepted_interval():
    port=driver();port._records['g']['submitted_goal']=direct_arm_goal()
    port._references['arm']=((.13,)*5,(.5,)*5,10.,1.16)
    assert port.current_reference(1.15)==pytest.approx((.125,)*5+(1.,))


@pytest.mark.parametrize('accepted', [1.001,None])
def test_past_query_without_proven_actual_accepted_interval_is_denied(accepted):
    port=driver();port._references['arm']=((.1,)*5,(.5,)*5,10.,1.002)
    if accepted is None:port._records['g'].pop('accepted_sim_s')
    else:port._records['g']['accepted_sim_s']=accepted
    with pytest.raises(RuntimeError,match='REFERENCE_TIME_INVALID'):port.current_reference(1.)


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
