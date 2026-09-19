"""Explicit timing calibration cannot grant general motion or data eligibility."""
import copy
import pytest
from so101_demo.adapters.act.calibration_motion import require_motion_manifest,within_calibration_envelope


def manifest():
    return dict(schema_version=1,kind='ACT_TIMING_CALIBRATION',eligible_for_collection=False,
        session_id='s',model_path='/data/work/model.xml',model_sha256='1'*64,arm_center=(-.25,0.,.6,.8,0.,.8),
        max_delta_rad=(.005,)*6,neck_center_rad=.2,max_neck_drift_rad=.02,max_rows=10,
        path_step_s=.002,path_clearance_m=.002,velocity_limit_rad_s=(.5,)*6,
        acceleration_limit_rad_s2=(20.,)*6,max_age_s=.15,max_skew_s=.12,stop_velocity_rad_s=.002,
        submit_lead_s=.04)


def prefix():
    return dict(session_id='s',attempt_id='a',sequence=0,observation_time_s=1.,target_times_s=(1.1,),
        positions=((-0.2498,0.,.6,.8,0.,.8002),))


def test_calibration_envelope_is_explicit_closed_and_never_formal_eligible():
    value=manifest();require_motion_manifest(value)
    for changes in ({'eligible_for_collection':True},{'max_rows':True},{'max_delta_rad':(.0,)*6},
                    {'extra':'unsafe'}, {'path_step_s':float('nan')}):
        changed=copy.deepcopy(value);changed.update(changes)
        with pytest.raises(ValueError):require_motion_manifest(changed)


def test_bounds_scope_prefix_and_fixed_neck_are_all_checked():
    m=manifest();p=prefix();assert within_calibration_envelope(p,m['arm_center'],.2,m)
    for bad in (dict(p,session_id='other'),dict(p,positions=((.5,)*6,)),dict(p,target_times_s=(1.2,))):
        assert not within_calibration_envelope(bad,m['arm_center'],.2,m)
    assert not within_calibration_envelope(p,m['arm_center'],.23,m)
    assert not within_calibration_envelope(p,(float('nan'),)*6,.2,m)


def test_actual_typed_epoch_stream_is_required_and_non_cup_fault_revokes_pair(scene,tmp_path):
    import threading
    from types import SimpleNamespace
    from sensor_msgs.msg import JointState
    from so101_mujoco_support.msg import ScalarJointEvidence,RobotContactEvidence,SimulationEvidence
    from so101_demo.adapters.act.calibration_motion import RosCalibrationMotionGuard
    from so101_demo.adapters.act.physics import model_sha256
    from so101_demo.act.ownership import Ownership
    import mujoco
    now=[10.];events=[];q=(-1.,0.,0.,0.,0.,1.)
    m=manifest();m.update(model_path=str(scene),model_sha256=model_sha256(mujoco.MjModel.from_xml_path(str(scene))),arm_center=q)
    cup=SimulationEvidence(simulation_session_id='s',reset_epoch=1,object_body='plastic_cup')
    cup.header.stamp.sec=1;cup.header.stamp.nanosec=2000000
    cup.object_pose_world.position.x=4.;cup.object_pose_world.position.z=1.;cup.object_pose_world.orientation.w=1.
    driver=SimpleNamespace(_lock=threading.RLock(),_epoch=(cup,10.),hazard_reason=None,
        reference_state=lambda at:dict(positions=q,velocities=(0.,)*6,accelerations=(0.,)*6))
    ownership=Ownership(monotonic=lambda:now[0]);token=ownership.acquire('act','s','a');ticket=ownership.ticket(token,'act','s','a')
    broker=SimpleNamespace(ownership=ownership,prefix_executor=SimpleNamespace(_ticket=ticket),
        tick=lambda:events.extend(('cancel-arm','cancel-gripper','revoke-permits')))
    class Node:
        def create_subscription(self,*args):return None
        def create_timer(self,*args):return None
    guard=RosCalibrationMotionGuard(Node(),driver,broker,m,evidence_root=tmp_path,monotonic=lambda:now[0])
    p=dict(session_id='s',attempt_id='a',sequence=0,observation_time_s=1.002,
        target_times_s=(1.102,),positions=((-.9998,0.,0.,0.,0.,1.0002),))
    snap=dict(session_id='s',attempt_id='a',reset_epoch=1,sim_time_s=1.002,reference=q,positions=q,velocities=(0.,)*6)
    assert not guard.check_prefix(p,snap)
    reset=ScalarJointEvidence(simulation_session_id='s',reset_epoch=1,paused=True,simulation_step=0,
        joint_names=['1','2','3','4','5','6','neck_yaw_joint'],positions_rad=list(q)+[.2],velocities_rad_s=[0.]*7)
    reset.header.stamp.sec=1;guard.accept_reset(reset)
    joints=JointState(name=list(reset.joint_names),position=list(reset.positions_rad),velocity=[0.]*7)
    joints.header.stamp.sec=1;joints.header.stamp.nanosec=2000000;guard.accept_joints(joints)
    frame=RobotContactEvidence(simulation_session_id='s',reset_epoch=1,physics_step=1,simulation_time_s=1.002)
    guard.contact_adapter.accept_message(frame)
    # Named arm/cup/contact evidence cannot stand in for every model qpos.
    assert not guard.check_prefix(p,snap)
    from so101_mujoco_support.msg import SceneStateEvidence
    qpos=guard.model.qpos0.copy()
    for name,value in zip(reset.joint_names,reset.positions_rad,strict=True):
        jid=mujoco.mj_name2id(guard.model,mujoco.mjtObj.mjOBJ_JOINT,name)
        qpos[guard.model.jnt_qposadr[jid]]=value
    qpos[guard.path.cup_address:guard.path.cup_address+7]=(4.,0.,1.,1.,0.,0.,0.)
    scene_message=SceneStateEvidence(simulation_session_id='s',reset_epoch=1,simulation_step=1,
        model_sha256=m['model_sha256'],qpos=list(qpos),qvel=[0.]*guard.model.nv)
    scene_message.header.stamp.sec=1;scene_message.header.stamp.nanosec=2000000
    guard.scene_adapter.accept_message(scene_message)
    assert guard.check_prefix(p,snap)
    # A future scene needs the broker's actual requested target/old epoch and
    # either its retained reset ACK or a still-authorized reset ticket.
    future_scene=dict(guard.scene_observer.snapshot(),reset_epoch=2,paused=True,simulation_step=0)
    driver._reset_initial=SimulationEvidence(simulation_session_id='s',reset_epoch=1)
    driver._reset_target=JointState(name=list(reset.joint_names),position=list(reset.positions_rad),velocity=[0.]*7)
    driver._world_reset_ack=True
    assert guard._pending_scene_reset(future_scene)
    wrong=copy.deepcopy(future_scene);wrong['qpos'][0]+=.001
    assert not guard._pending_scene_reset(wrong)
    assert not guard._pending_scene_reset(dict(future_scene,reset_epoch=3))
    driver._world_reset_ack=False;broker._lock=threading.RLock();broker._reset_ticket=ticket
    assert not guard._pending_scene_reset(future_scene) # ACT cannot authorize reset.
    broker._reset_ticket=None
    assert not guard._pending_scene_reset(future_scene)
    fault=RobotContactEvidence(simulation_session_id='s',reset_epoch=1,physics_step=2,simulation_time_s=1.004,
        geom_a=['arm'],geom_b=['obstacle'],signed_distance_m=[-.001],normal_force_n=[2.])
    guard.contact_adapter.accept_message(fault)
    assert events==['cancel-arm','cancel-gripper','revoke-permits'] and driver.hazard_reason=='ROBOT_CONTACT_HAZARD'
    assert not guard.check_prefix(p,snap)
    guard.close()


from test_act_physics import scene


def test_cli_rejects_formal_eligible_motion_manifest_before_authority_or_ros_init(tmp_path,monkeypatch):
    import json,os
    from so101_demo.cli.act_command_broker import main
    from so101_demo.adapters.act.domain_authority import DomainAuthority
    value=manifest();value['eligible_for_collection']=True
    p=tmp_path/'bad-motion.json';p.write_text(json.dumps(value))
    def forbidden(*args):raise AssertionError('authority acquired before motion preflight')
    monkeypatch.setattr(DomainAuthority,'acquire',forbidden)
    with pytest.raises(ValueError,match='MOTION_CALIBRATION_INVALID'):
        main(['--socket', '/data/work/so101-evidence/act-data/0917a/r/bad-preflight',
            '--session-id','s','--parent-pid',str(os.getpid()),'--lease-timeout-s','30','--calibration-mode',
            '--stop-velocity-rad-s','.002','--max-age-s','1.5','--submit-lead-s','.04','--accept-timeout-s','.03',
            '--stop-timeout-s','1','--permit-ttl-s','.1','--motion-calibration-manifest',str(p)])
