"""Physical supervision never treats controller success as task completion."""
import copy
import pytest
from so101_demo.act.supervisor import ActSupervisor,release_allowed
from so101_demo.act.deadline import Deadline


def snapshot(**updates):
    value=dict(session_id='s',attempt_id='a',reset_epoch=1,release_epoch=0,sim_time_s=1.,
        source_times_s={key:1. for key in ('joints','cup','contacts','head','wrist')},
        received_wall_s={key:10. for key in ('joints','cup','contacts','head','wrist')},
        arm_positions=(0.,0.,0.,0.,0.,1.),arm_velocities=(0.,)*6,neck_yaw_rad=.2,
        holding_state='EMPTY',phase='APPROACH',target_visible=True,bilateral_contact=False,
        micro_lift_confirmed=False,cup_off_table=False,cup_supported=True,
        robot_contacts_safe=True,released=False,placement_stable=False,retreat_stable=False,
        planning_attached=False,controller_start_time_s=1.04,controller_start_positions=(0.,0.,0.,0.,0.,1.),
        model_qpos=(),cup_in_gripper_transform=None,model_sha256='0'*64,controller_start_velocities=(0.,)*6,
        controller_bridge=dict(time_s=1.,point=dict(positions=(0.,0.,0.,0.,0.,1.),velocities=(),accelerations=())))
    value.update(updates);return value


def prefix(opening=False,rows=1):
    return dict(session_id='s',attempt_id='a',sequence=0,observation_time_s=1.,
        target_times_s=tuple(1.+.1*(i+1) for i in range(rows)),
        positions=tuple((0.,0.,0.,0.,0.,.8 if opening else 1.) for i in range(rows)))


class Pair:
    def __init__(self):self.reasons=[]
    def invalidate(self,reason):self.reasons.append(reason)
    def poll_stop(self):return 'STOPPED'


class Physics:
    def __init__(self):self.safe=True;self.calls=[]
    def check_path(self,p,s):self.calls.append((copy.deepcopy(p),copy.deepcopy(s)));return self.safe


def supervisor():
    pair,physics=Pair(),Physics()
    port=ActSupervisor(pair,physics,deadline=Deadline(10.),initial_snapshot=snapshot(),
        max_age_s=.15,max_skew_s=.12,max_neck_drift_rad=.02,visibility_occlusion_s=.5,
        opening_delta_rad=.02,monotonic=lambda:10.,permit_port=lambda p,s:dict(approved=True))
    return port,pair,physics


def test_cannot_open_unsupported_or_stale_cup():
    assert not release_allowed(True,True,False,True)
    assert not release_allowed(True,True,True,False)
    assert release_allowed(True,True,True,True)
    with pytest.raises(ValueError):release_allowed('UNKNOWN',True,True,True)


@pytest.mark.parametrize('updates,reason',[
    ({'holding_state':'UNKNOWN'},'HOLDING_UNKNOWN'),
    ({'robot_contacts_safe':False},'ROBOT_CONTACT_HAZARD'),
    ({'neck_yaw_rad':.23},'NECK_DRIFT'),
    ({'target_visible':False},'TARGET_LOST'),
    ({'reset_epoch':2},'SUPERVISOR_SCOPE_INVALID'),
    ({'arm_velocities':(float('nan'),)*6},'SUPERVISOR_SNAPSHOT_INVALID'),
    ({'source_times_s':dict(joints=1.1,cup=1.,contacts=1.,head=1.,wrist=1.)},'EVIDENCE_STALE'),
])
def test_bad_physical_evidence_stops_both_and_never_issues_permit(updates,reason):
    port,pair,physics=supervisor()
    assert port.tick(snapshot(**updates),10.)=='STOPPED'
    assert pair.reasons==[reason] and not physics.calls
    with pytest.raises(PermissionError):port.check(prefix(),snapshot())


def test_contact_occlusion_is_bounded_and_deadline_counts_pause():
    port,pair,_=supervisor();assert port.tick(snapshot(),10.)=='EMPTY'
    value=snapshot(phase='CONTACT',target_visible=False)
    value['received_wall_s']={key:10.4 for key in value['received_wall_s']}
    assert port.tick(value,10.4)=='EMPTY'
    value['received_wall_s']={key:10.51 for key in value['received_wall_s']}
    assert port.tick(value,10.51)=='STOPPED' and pair.reasons==['TARGET_LOST']
    port,pair,_=supervisor()
    assert port.tick(snapshot(),130.)=='STOPPED' and pair.reasons==['ACT_TIMEOUT']


def held(**updates):
    return snapshot(holding_state='HOLDING',bilateral_contact=True,micro_lift_confirmed=True,
        cup_off_table=True,phase='TRANSPORT',**updates)


def test_hold_requires_bilateral_micro_lift_and_off_table_confirmation():
    for key in ('bilateral_contact','micro_lift_confirmed','cup_off_table'):
        port,pair,_=supervisor();value=held();value[key]=False
        assert port.tick(value,10.)=='STOPPED' and pair.reasons==['HOLD_NOT_CONFIRMED']


def test_release_prefix_requires_support_detach_and_one_tick_boundary():
    port,_,physics=supervisor()
    for value in (held(cup_supported=False),held(planning_attached=True)):
        with pytest.raises(PermissionError):port.check(prefix(opening=True),value)
    with pytest.raises(PermissionError,match='RELEASE_PREFIX_BOUNDARY'):
        port.check(prefix(opening=True,rows=2),held())
    assert port.check(prefix(opening=True),held())=={'approved':True}
    assert len(physics.calls)==1


def test_path_rejection_cannot_be_approved():
    port,_,physics=supervisor();physics.safe=False
    with pytest.raises(PermissionError,match='PATH_REJECTED'):port.check(prefix(),snapshot())


def test_release_epoch_is_non_resumable_and_retreat_plus_placement_required():
    port,pair,_=supervisor();assert port.tick(held(),10.)=='HOLDING'
    release=snapshot(release_epoch=1,released=True,phase='RELEASE',placement_stable=True,sim_time_s=1.1,
        source_times_s={key:1.1 for key in ('joints','cup','contacts','head','wrist')})
    assert port.tick(release,10.)=='RELEASE_CONFIRMED'
    retreat=copy.deepcopy(release);retreat.update(phase='RETREAT',placement_stable=False)
    assert port.tick(retreat,10.)=='ACT_RETREAT'
    retreat.update(retreat_stable=True)
    assert port.tick(retreat,10.)=='VALIDATE_FINAL_PLACEMENT'
    retreat.update(placement_stable=True)
    assert port.tick(retreat,10.)=='DONE' and not pair.reasons
    port,pair,_=supervisor();port.tick(held(),10.);port.tick(release,10.)
    assert port.tick(snapshot(),10.)=='STOPPED' and pair.reasons==['RELEASE_EPOCH_INVALID']


def test_retreat_contact_fault_overrides_final_placement_success():
    port,pair,_=supervisor();port.tick(held(),10.)
    release=snapshot(release_epoch=1,released=True,phase='RELEASE',placement_stable=True,sim_time_s=1.1,
        source_times_s={key:1.1 for key in ('joints','cup','contacts','head','wrist')})
    port.tick(release,10.)
    release.update(phase='RETREAT',retreat_stable=True,robot_contacts_safe=False)
    assert port.tick(release,10.)=='STOPPED' and pair.reasons==['ROBOT_CONTACT_HAZARD']


def test_pre_release_samples_cannot_be_relabelled_with_new_epoch():
    port,pair,_=supervisor();port.tick(held(),10.)
    reused=snapshot(release_epoch=1,released=True,phase='RELEASE',placement_stable=True)
    assert port.tick(reused,10.)=='STOPPED'
    assert pair.reasons==['RELEASE_EPOCH_INVALID']


def test_confirmed_hold_can_lower_to_support_without_forgetting_acquisition():
    port,pair,_=supervisor();assert port.tick(held(),10.)=='HOLDING'
    value=held(cup_supported=True);value['cup_off_table']=False
    assert port.tick(value,10.)=='HOLDING' and not pair.reasons


def test_path_computation_cannot_extend_attempt_deadline_or_issue_late_permit():
    now=[10.];port,pair,physics=supervisor();port.monotonic=lambda:now[0]
    approvals=[];port.permit_port=lambda p,s:approvals.append(p)
    def delayed_check(p,s):now[0]=130.;return True
    physics.check_path=delayed_check
    with pytest.raises(PermissionError,match='ACT_TIMEOUT'):port.check(prefix(),snapshot())
    assert approvals==[] and pair.reasons==['ACT_TIMEOUT']


def test_supervisor_missing_controller_bridge_never_grants_motion_permit():
    port,pair,physics=supervisor();s=snapshot();s.pop('controller_bridge',None)
    with pytest.raises(PermissionError,match='SUPERVISOR_SNAPSHOT_INVALID'):port.check(prefix(),s)
    assert not physics.calls and pair.reasons==['SUPERVISOR_SNAPSHOT_INVALID']


def test_deadline_stop_tick_is_independent_of_a_blocked_path_checker():
    import threading
    port,pair,physics=supervisor();entered=threading.Event();unblock=threading.Event();errors=[]
    def blocked(*args):entered.set();assert unblock.wait(2);return True
    physics.check_path=blocked
    def check():
        try:port.check(prefix(),snapshot())
        except PermissionError as e:errors.append(str(e))
    check_thread=threading.Thread(target=check);check_thread.start();assert entered.wait(1)
    def expire():port.tick(snapshot(),130.)
    stop_thread=threading.Thread(target=expire);stop_thread.start();stop_thread.join(.05)
    was_blocked=stop_thread.is_alive()
    unblock.set();check_thread.join(1);stop_thread.join(1)
    assert not was_blocked,'physics preparation blocked immutable deadline Stop'
    assert pair.reasons==['ACT_TIMEOUT'] and errors==['ACT_TIMEOUT']


def test_deadline_stop_remains_independent_during_permit_approval():
    import threading
    port,pair,physics=supervisor();entered=threading.Event();unblock=threading.Event();errors=[]
    def blocked(*args):entered.set();assert unblock.wait(2);return {'id':'late'}
    port.permit_port=blocked
    def check():
        try:port.check(prefix(),snapshot())
        except PermissionError as e:errors.append(str(e))
    worker=threading.Thread(target=check);worker.start();assert entered.wait(1)
    stop=threading.Thread(target=lambda:port.tick(snapshot(),130.));stop.start();stop.join(.05)
    blocked_stop=stop.is_alive();unblock.set();worker.join(1);stop.join(1)
    assert not blocked_stop,'permit callback blocked timeout Stop'
    assert pair.reasons==['ACT_TIMEOUT'] and errors==['ACT_TIMEOUT']
