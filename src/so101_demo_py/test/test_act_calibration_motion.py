"""Explicit timing calibration cannot grant general motion or data eligibility."""
import copy
import pytest
from so101_demo.adapters.act.calibration_motion import require_motion_manifest,within_calibration_envelope


def test_contact_diagnostic_motion_configuration_is_source_replayed_and_not_collectible():
    from pathlib import Path
    from so101_demo.act.contact_diagnostic import build_contact_diagnostic_manifest
    from so101_demo.adapters.act.calibration_motion import diagnostic_motion_configuration
    package = Path(__file__).resolve().parents[1]
    contact = build_contact_diagnostic_manifest(
        scene_path=package / 'assets/mujoco/act/scene.xml',
        motion_policy_path=package / 'config/policies/light_cup_wall_pick/v1/mujoco.yaml',
        plugin_path=package / 'config/mujoco/act/mujoco_plugins.yaml',
        regime='bilateral_touch', seed=0, session_id='contact-one', attempt_id='attempt-one',
    )
    config = diagnostic_motion_configuration(contact)
    assert config['kind'] == 'ACT_CONTACT_DIAGNOSTIC'
    assert config['model_sha256'] == contact['model_sha256']
    assert config['max_rows'] == 10
    assert config['allowed_pairs']
    assert config['eligible_for_collection'] is False
    tampered = copy.deepcopy(contact)
    tampered['backend'] = 'gazebo'
    with pytest.raises(ValueError):
        diagnostic_motion_configuration(tampered)


def test_contact_diagnostic_guard_uses_single_existing_broker_and_live_physics(tmp_path):
    import threading
    from pathlib import Path
    from types import SimpleNamespace as NS
    from so101_mujoco_support.msg import ScalarJointEvidence
    from so101_demo.act.contact_diagnostic import build_contact_diagnostic_manifest
    from so101_demo.adapters.act.calibration_motion import RosCalibrationMotionGuard
    from so101_demo.act.ownership import Ownership
    package = Path(__file__).resolve().parents[1]
    contact = build_contact_diagnostic_manifest(
        scene_path=package / 'assets/mujoco/act/scene.xml',
        motion_policy_path=package / 'config/policies/light_cup_wall_pick/v1/mujoco.yaml',
        plugin_path=package / 'config/mujoco/act/mujoco_plugins.yaml',
        regime='left_only', seed=0, session_id='contact-one', attempt_id='attempt-one',
    )
    class Node:
        def create_subscription(self,*args):return args
        def create_timer(self,*args):return args
        def destroy_subscription(self,*args):pass
        def destroy_timer(self,*args):pass
        def get_clock(self):return NS(now=lambda:NS(nanoseconds=2_000_000))
    driver=NS(_lock=threading.RLock(),hazard_reason=None)
    ownership=Ownership();broker=NS(ownership=ownership,prefix_executor=None,tick=lambda:None)
    guard=RosCalibrationMotionGuard(Node(),driver,broker,contact,evidence_root=tmp_path)
    assert guard.contact_mode is True
    assert guard.contact_observer.allowed
    reset=ScalarJointEvidence(
        simulation_session_id='contact-one',reset_epoch=1,paused=True,simulation_step=0,
        joint_names=['1','2','3','4','5','6','neck_yaw_joint'],
        positions_rad=contact['joint_start_rad']+[contact['neck_start_rad']],
        velocities_rad_s=[0.]*7,
    )
    guard.accept_reset(reset)
    assert guard.live_observer is not None
    assert (tmp_path/'contact-live-physics.ndjson').exists()
    prefix=dict(session_id=contact['session_id'],attempt_id=contact['attempt_id'],
        sequence=0,observation_time_s=0.,target_times_s=(.1,.2),
        positions=[contact['joint_start_rad']]+contact['target_positions'])
    assert guard._within(prefix,contact['joint_start_rad'],contact['neck_start_rad'])
    altered=copy.deepcopy(prefix);altered['positions']=[row[:] for row in prefix['positions']]
    altered['positions'][0][5]+=.001
    assert not guard._within(altered,contact['joint_start_rad'],contact['neck_start_rad'])
    assert not guard._live_ready()  # reset alone cannot authorize a trajectory
    assert not guard.check_prefix(prefix, {'sim_time_s': 0.})
    import json
    refusals = [json.loads(line) for line in
                (tmp_path/'contact-diagnostic-guard-rejections.jsonl').read_text().splitlines()]
    assert refusals[-1]['boundary'] == 'approve'
    assert refusals[-1]['reason'] == 'LIVE_NOT_READY'
    import mujoco
    driver._reset_initial=NS(simulation_session_id='contact-one',reset_epoch=0)
    driver._reset_target=NS(name=reset.joint_names,position=reset.positions_rad,
                            velocity=reset.velocities_rad_s)
    driver._world_reset_ack=True
    qpos=list(guard.model.qpos0)
    for name,value in zip(reset.joint_names,reset.positions_rad,strict=True):
        joint=mujoco.mj_name2id(guard.model,mujoco.mjtObj.mjOBJ_JOINT,name)
        qpos[guard.model.jnt_qposadr[joint]]=value
    qpos[guard.path.cup_address:guard.path.cup_address+3]=contact['cup_start_m']
    frame=dict(simulation_session_id='contact-one',reset_epoch=1,paused=True,
               qpos=qpos,qvel=[0.]*guard.model.nv)
    assert guard._pending_scene_reset(frame)
    bad=copy.deepcopy(frame);bad['qpos'][guard.path.cup_address+1]+=.001
    assert not guard._pending_scene_reset(bad)
    guard.close()


def test_contact_diagnostic_broker_rejects_bad_manifest_before_authority(tmp_path,monkeypatch):
    import json,os
    from pathlib import Path
    from so101_demo.act.contact_diagnostic import build_contact_diagnostic_manifest
    from so101_demo.cli.act_command_broker import main
    from so101_demo.adapters.act.domain_authority import DomainAuthority
    package=Path(__file__).resolve().parents[1]
    value=build_contact_diagnostic_manifest(
        scene_path=package/'assets/mujoco/act/scene.xml',
        motion_policy_path=package/'config/policies/light_cup_wall_pick/v1/mujoco.yaml',
        plugin_path=package/'config/mujoco/act/mujoco_plugins.yaml',
        regime='left_only',seed=0,session_id='contact-one',attempt_id='attempt-one')
    value['backend']='gazebo'
    path=tmp_path/'bad-contact.json';path.write_text(json.dumps(value))
    monkeypatch.setattr(DomainAuthority,'acquire',lambda *_:(_ for _ in ()).throw(
        AssertionError('authority acquired before contact preflight')))
    with pytest.raises(ValueError):
        main(['--socket',str(tmp_path/'broker.sock'),'--session-id','contact-one',
              '--parent-pid',str(os.getpid()),'--lease-timeout-s','30',
              '--calibration-mode','--stop-velocity-rad-s','.002','--max-age-s','.2',
              '--submit-lead-s','.05','--accept-timeout-s','.03',
              '--stop-timeout-s','1','--permit-ttl-s','.1',
              '--contact-diagnostic-manifest',str(path)])


def test_contact_segments_require_prior_terminal_controller_success(tmp_path):
    import threading
    from pathlib import Path
    from types import SimpleNamespace as NS
    from so101_demo.act.contact_diagnostic import build_contact_diagnostic_manifest
    from so101_demo.adapters.act.calibration_motion import RosCalibrationMotionGuard
    from so101_demo.act.ownership import Ownership
    package=Path(__file__).resolve().parents[1]
    contact=build_contact_diagnostic_manifest(
        scene_path=package/'assets/mujoco/act/scene.xml',
        motion_policy_path=package/'config/policies/light_cup_wall_pick/v1/mujoco.yaml',
        plugin_path=package/'config/mujoco/act/mujoco_plugins.yaml',
        regime='bilateral_touch',seed=0,session_id='contact-two',attempt_id='attempt-two')
    class Node:
        def create_subscription(self,*args):return args
        def create_timer(self,*args):return args
    outcome={'status':6}
    baseline={'refreshed':False}
    driver=NS(_lock=threading.RLock(),hazard_reason=None,
              refresh_idle=lambda:baseline.update(refreshed=True),
              stopped=lambda:baseline['refreshed'],
              goal_state=lambda gid:dict(accepted=True,status=outcome['status'],
                                          result={'error_code':0}))
    pair=NS(adapter=NS(current_goal_ids=('arm-goal','gripper-goal')))
    broker=NS(ownership=Ownership(),prefix_executor=pair,tick=lambda:None)
    guard=RosCalibrationMotionGuard(Node(),driver,broker,contact,evidence_root=tmp_path)
    guard._next_segment=1
    prior=contact['target_positions'][8]
    rows=[prior]+contact['target_positions'][9:18]
    prefix=dict(session_id=contact['session_id'],attempt_id=contact['attempt_id'],
                sequence=1,observation_time_s=1.,
                target_times_s=[1.+.1*(i+1) for i in range(len(rows))],positions=rows)
    assert not guard._within(prefix,prior,0.)
    assert baseline['refreshed'] is False
    outcome['status']=4
    assert guard._within(prefix,prior,0.)
    assert baseline['refreshed'] is True
    assert not guard._within(dict(prefix,sequence=2),prior,0.)
    guard.close()


def test_timing_guard_start_stays_inside_manifest_center():
    from types import SimpleNamespace as NS
    from so101_demo.adapters.act.calibration_motion import RosCalibrationMotionGuard
    config=manifest()
    guard=NS(contact_mode=False,manifest=config)
    assert RosCalibrationMotionGuard._start_safe(guard,config['arm_center'],config['neck_center_rad'])
    shifted=list(config['arm_center']);shifted[0]+=.01
    assert not RosCalibrationMotionGuard._start_safe(guard,shifted,config['neck_center_rad'])


def test_live_contact_staleness_waits_while_reset_is_paused():
    import threading
    from types import SimpleNamespace as NS
    from so101_demo.adapters.act.calibration_motion import RosCalibrationMotionGuard
    calls=[]
    guard=NS(live_observer=NS(poll=lambda:calls.append('poll'),
                              suspend=lambda:calls.append('suspend'),
                              start=lambda:calls.append('start')),
             scene_observer=NS(_lock=threading.RLock(),last={'paused':True}),
             broker=NS(prefix_executor=None))
    RosCalibrationMotionGuard.poll(guard)
    assert calls == ['suspend']
    guard.scene_observer.last['paused']=False
    RosCalibrationMotionGuard.poll(guard)
    assert calls == ['suspend', 'start', 'poll']


def test_motion_guard_persists_actual_path_refusal_detail(tmp_path):
    import json
    from collections import deque
    from types import SimpleNamespace as NS
    from so101_demo.adapters.act.calibration_motion import RosCalibrationMotionGuard
    output = (tmp_path/'guard-rejections.jsonl').open('x', encoding='utf-8')
    guard = NS(monotonic=lambda: 10., audit=deque(maxlen=8), _audit_record=output,
               _joints=((0.,)*7,),
               _live_ready=lambda: True, manifest={'submit_lead_s': .05},
               driver=NS(reference_state=lambda _: {'positions': (0.,)*6,
                                                     'velocities': (0.,)*6}),
               _snapshot=lambda *args, **kwargs: {}, _within=lambda *args: True,
               path=NS(check_path=lambda *args: False,
                       last_check={'safe': False, 'reason': 'PATH_CHECK_TIMEOUT'}))
    guard._record_rejection = lambda row: RosCalibrationMotionGuard._record_rejection(guard, row)
    assert not RosCalibrationMotionGuard.check_prefix(guard, {}, {'sim_time_s': 1.})
    output.close()
    row = json.loads((tmp_path/'guard-rejections.jsonl').read_text())
    assert row['boundary'] == 'approve'
    assert row['path']['reason'] == 'PATH_CHECK_TIMEOUT'
    assert row['safe'] is False


def test_contact_exact_goals_use_fresh_sim_time_and_reject_old_observation():
    from collections import deque
    from types import SimpleNamespace as NS
    from so101_demo.adapters.act.calibration_motion import RosCalibrationMotionGuard
    now=[1.03]
    snapshots=[]
    held=(0.,)*6
    guard=NS(contact_mode=True,manifest={'max_age_s':.2},
             node=NS(get_clock=lambda:NS(now=lambda:NS(nanoseconds=round(now[0]*1e9)))),
             contact_observer=NS(epoch=1),driver=NS(reference_state=lambda _:dict(positions=held,velocities=held)),
             _joints=((0.,)*7,),audit=deque(maxlen=8),_next_segment=0,
             _live_ready=lambda:True,_within=lambda *_:True,
             _snapshot=lambda base,**_:snapshots.append(base) or {'sim_time_s':base['sim_time_s']},
             path=NS(check_path=lambda *_:True,last_check={}))
    goals=[{'header_stamp_s':1.08,'time_from_start_s':(0.,.1),
            'positions':(held[:5],)},
           {'header_stamp_s':1.08,'time_from_start_s':(0.,.1),
            'positions':(held[5:],)}]
    prefix={'session_id':'s','attempt_id':'a','observation_time_s':1.0}
    assert RosCalibrationMotionGuard.check_exact_goals(guard,goals,prefix)
    assert snapshots[-1]['sim_time_s']==1.03
    now[0]=1.21
    assert not RosCalibrationMotionGuard.check_exact_goals(guard,goals,prefix)


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
