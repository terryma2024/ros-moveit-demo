"""Whole-robot hazard evidence is contiguous, fresh and independent of cup filters."""
import math
import pytest
from so101_demo.adapters.act.contact_evidence import contact_hazard,RobotContactObserver


def frame(step=1,**overrides):
    value=dict(simulation_session_id='s',reset_epoch=1,physics_step=step,simulation_time_s=step*.002,
        geom_a=[],geom_b=[],signed_distance_m=[],normal_force_n=[],truncated=False,evidence_loss=False)
    value.update(overrides);return value


@pytest.mark.parametrize('pair',(('arm','table'),('arm','forearm'),('arm','mast')))
def test_non_cup_contact_is_retained_as_hazard(pair):
    value=frame(geom_a=[pair[0]],geom_b=[pair[1]],signed_distance_m=[-.001],normal_force_n=[2.])
    assert contact_hazard(value,set())
    assert not contact_hazard(value,{tuple(sorted(pair))})


@pytest.mark.parametrize('override',({'truncated':True},{'evidence_loss':True},{'normal_force_n':[1.]},
    {'geom_a':['arm'],'geom_b':['table'],'signed_distance_m':[math.nan],'normal_force_n':[1.]},
    {'truncated':1}))
def test_bad_or_lost_contact_evidence_is_hazard(override):assert contact_hazard(frame(**override),set())


def observer(now):
    return RobotContactObserver(known_geoms={'arm','table','mast','forearm'},allowed_pairs=set(),
        max_age_s=.15,max_sim_gap_s=.003,monotonic=lambda:now[0])


def test_step_hole_and_transient_contact_latch_until_new_epoch():
    now=[10.];port=observer(now);port.reset('s',1,source_floor_s=0.)
    port.accept(frame());assert port.safe()
    port.accept(frame(2,geom_a=['arm'],geom_b=['table'],signed_distance_m=[-.001],normal_force_n=[2.]))
    port.accept(frame(3));assert not port.safe()
    with pytest.raises(ValueError):port.reset('s',1,source_floor_s=.006)
    port.reset('s',2,source_floor_s=.006);port.accept(frame(1,reset_epoch=2,simulation_time_s=.008));assert port.safe()
    port.accept(frame(3,reset_epoch=2,simulation_time_s=.012));assert not port.safe()


@pytest.mark.parametrize('override',({'reset_epoch':0},{'simulation_session_id':'other'},{'simulation_time_s':-.1},
    {'geom_a':['unknown'],'geom_b':['table'],'signed_distance_m':[-.001],'normal_force_n':[2.]}))
def test_old_or_unknown_source_never_approves(override):
    now=[10.];port=observer(now);port.reset('s',1,source_floor_s=0.)
    port.accept(frame(**override));assert not port.safe()


def test_wall_freshness_and_backwards_clock_fail_closed():
    now=[10.];port=observer(now);port.reset('s',1,source_floor_s=0.)
    assert not port.safe();port.accept(frame());assert port.safe()
    now[0]=10.16;assert not port.safe()
    now[0]=9.9;assert not port.safe()


def test_ros_contact_adapter_stops_once_and_revokes_permits_for_real_non_cup_frame():
    from so101_demo.adapters.act.contact_evidence import RosRobotContactAdapter
    from so101_mujoco_support.msg import RobotContactEvidence
    from types import SimpleNamespace
    events=[];now=[10.]
    class Node:
        def create_subscription(self,kind,topic,callback,qos):
            assert kind is RobotContactEvidence and topic=='/so101/simulation/robot_contacts'
            self.callback=callback;return None
    node=Node();port=observer(now)
    adapter=RosRobotContactAdapter(node,port,on_hazard=lambda reason:events.extend(('cancel-arm','cancel-gripper','revoke-permits')))
    adapter.arm(SimpleNamespace(simulation_session_id='s',reset_epoch=1,simulation_time_s=0.,paused=True,simulation_step=0))
    node.callback(RobotContactEvidence(**frame()))
    assert port.safe() and events==[]
    node.callback(RobotContactEvidence(**frame(2,geom_a=['arm'],geom_b=['table'],signed_distance_m=[-.001],normal_force_n=[2.])))
    node.callback(RobotContactEvidence(**frame(3)))
    assert events==['cancel-arm','cancel-gripper','revoke-permits'] and not port.safe()


def test_pre_reset_frames_are_discarded_only_before_first_current_physics_step():
    from so101_demo.adapters.act.contact_evidence import RosRobotContactAdapter
    from so101_mujoco_support.msg import RobotContactEvidence
    from types import SimpleNamespace
    class Node:
        def create_subscription(self,*args):return None
    now=[10.];port=observer(now);hazards=[]
    adapter=RosRobotContactAdapter(Node(),port,on_hazard=hazards.append)
    adapter.accept_message(RobotContactEvidence(**frame(reset_epoch=0)))
    adapter.arm(SimpleNamespace(simulation_session_id='s',reset_epoch=1,simulation_time_s=0.,paused=True,simulation_step=0))
    assert not port.safe() and not hazards
    adapter.accept_message(RobotContactEvidence(**frame()));assert port.safe()
    adapter.accept_message(RobotContactEvidence(**frame(2,reset_epoch=0)))
    assert not port.safe() and len(hazards)==1


def test_contact_stream_invalidates_actual_pair_and_its_permit_registry():
    from so101_demo.act.execution import ActExecutionAdapter,prefix_sha256
    from so101_demo.adapters.act.contact_evidence import RosRobotContactAdapter
    from so101_mujoco_support.msg import RobotContactEvidence
    from types import SimpleNamespace
    class Port:
        def __init__(self):self.cancelled=[]
        def send(self,goal):return 'real-pair-goal'
        def accepted(self,gid):return True
        def cancel(self,gid):self.cancelled.append(gid)
        def stopped(self):return True
    class Permits:
        revoked=False
        def require(self,*args):assert not self.revoked
        def revoke(self,reason):self.revoked=True
    arm,grip,permits=Port(),Port(),Permits()
    pair=ActExecutionAdapter(arm,grip,permit_port=permits,sim_clock=lambda:1.,monotonic=lambda:10.,
        progress=lambda:None,submit_lead_s=.04,accept_timeout_s=.03,stop_timeout_s=1.,reference_port=lambda when:(0.,)*6)
    pair.begin_attempt('s','a')
    prefix=dict(session_id='s',attempt_id='a',sequence=0,observation_time_s=1.,target_times_s=(1.1,),positions=((.01,)*6,))
    pair.submit(prefix,{'prefix_sha256':prefix_sha256(prefix)})
    port=observer([10.])
    adapter=RosRobotContactAdapter(SimpleNamespace(create_subscription=lambda *args:None),port,on_hazard=pair.invalidate)
    adapter.arm(SimpleNamespace(simulation_session_id='s',reset_epoch=1,simulation_time_s=0.,paused=True,simulation_step=0))
    adapter.accept_message(RobotContactEvidence(**frame(geom_a=['arm'],geom_b=['table'],signed_distance_m=[-.001],normal_force_n=[2.])))
    assert arm.cancelled==grip.cancelled==['real-pair-goal'] and permits.revoked
    assert pair.state=='STOPPING'


@pytest.mark.parametrize('armed', (False, True))
def test_record_backpressure_latches_hazard_and_stops_without_losing_ros_callback(armed):
    from so101_demo.adapters.act.contact_evidence import RosRobotContactAdapter
    from so101_mujoco_support.msg import RobotContactEvidence
    from types import SimpleNamespace
    port=observer([10.]);hazards=[]
    def failed_write(value):raise OSError('disk full or bounded writer queue overflow')
    adapter=RosRobotContactAdapter(SimpleNamespace(create_subscription=lambda *args:None),
        port,on_hazard=hazards.append,record_port=failed_write)
    snapshot=SimpleNamespace(simulation_session_id='s',reset_epoch=1,simulation_time_s=0.,paused=True,simulation_step=0)
    if armed:adapter.arm(snapshot)
    adapter.accept_message(RobotContactEvidence(**frame()))
    if not armed:adapter.arm(snapshot)
    adapter.record_port=lambda value:None
    adapter.accept_message(RobotContactEvidence(**frame(2)))
    assert not port.safe() and port.hazard=='CONTACT_RECORD_FAILED'
    assert hazards and all(reason=='CONTACT_RECORD_FAILED' for reason in hazards)
    count=len(hazards)
    adapter.accept_message(RobotContactEvidence(**frame(3)))
    assert len(hazards)==count
    adapter.arm(SimpleNamespace(simulation_session_id='s',reset_epoch=2,simulation_time_s=.006,paused=True,simulation_step=0))
    adapter.accept_message(RobotContactEvidence(**frame(reset_epoch=2,simulation_time_s=.008)))
    assert port.safe()
