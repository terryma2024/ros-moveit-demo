"""Real MuJoCo swept collision and held-cup volume tests."""
import hashlib
import math
import numpy as np
import pytest
import mujoco
from so101_demo.adapters.act.physics import MujocoPathChecker,model_sha256


@pytest.fixture
def scene(tmp_path):
    others=''.join(f'<body name="dummy{i}" pos="0 0 {i*.12}"><joint name="{i}" axis="0 0 1"/><geom size=".01" mass=".01" contype="0" conaffinity="0"/></body>' for i in range(2,6))
    xml=f'''<mujoco><option gravity="0 0 0"/><worldbody>
      <body name="base" pos="0 0 1"><joint name="1" axis="0 0 1"/>
        <geom name="arm" type="capsule" fromto=".15 0 0 .6 0 0" size=".03"/>{others}
        <body name="gripper" pos=".8 0 0"><joint name="6" axis="0 0 1"/>
          <geom name="jaw" size=".01" mass=".01" contype="0" conaffinity="0"/></body>
        <body name="head" pos="0 0 .8"><joint name="neck_yaw_joint" axis="0 0 1"/>
          <geom name="camera" size=".02"/></body>
      </body>
      <body name="obstacle_body" pos=".5 0 1"><geom name="obstacle" size=".06"/></body>
      <body name="plastic_cup" pos="4 0 1"><freejoint name="cup_free_joint"/><geom name="cup" size=".09"/></body>
    </worldbody></mujoco>'''
    p=tmp_path/'scene.xml';p.write_text(xml);return p


def checker(scene,allowed=None):
    return MujocoPathChecker(scene,protected_roots=('base',),cup_joint='cup_free_joint',gripper_body='gripper',
        path_step_s=.002,path_clearance_m=.002,velocity_limit_rad_s=(100.,)*6,
        acceleration_limit_rad_s2=(1e6,)*6,allowed_pairs_by_phase=allowed or {})


def inputs(port,holding=False):
    qpos=port.model.qpos0.copy()
    for name,value in zip(('1','2','3','4','5','6'),(-1.,0.,0.,0.,0.,1.),strict=True):
        qpos[port.model.jnt_qposadr[mujoco.mj_name2id(port.model,mujoco.mjtObj.mjOBJ_JOINT,name)]]=value
    snap=dict(model_qpos=tuple(qpos),model_sha256=port.model_sha256,phase='TRANSPORT',holding_state='HOLDING' if holding else 'EMPTY',
        controller_start_time_s=1.04,controller_start_positions=(-1.,0.,0.,0.,0.,1.),controller_start_velocities=(0.,)*6,
        controller_bridge=dict(time_s=1.,point=dict(positions=(-1.,0.,0.,0.,0.,1.),velocities=(),accelerations=())),
        cup_in_gripper_transform=np.eye(4).tolist() if holding else None)
    prefix=dict(session_id='s',attempt_id='a',sequence=0,observation_time_s=1.,target_times_s=(1.1,),positions=((1.,0.,0.,0.,0.,1.),))
    return prefix,snap


def test_clear_goal_endpoints_do_not_hide_interior_arm_collision(scene):
    port=checker(scene);p,s=inputs(port)
    assert not port.check_path(p,s)
    assert port.last_check['reason']=='ROBOT_PATH_CONTACT'
    assert port.last_check['contact_pair']==('arm','obstacle')
    assert 1.04<port.last_check['sample_time_s']<1.1
    assert s['model_qpos']==inputs(port)[1]['model_qpos']


def test_held_cup_volume_moves_with_gripper_and_is_never_deleted(scene):
    scene.write_text(scene.read_text().replace('pos=".5 0 1"','pos=".8 0 1"'))
    port=checker(scene);p,s=inputs(port)
    assert port.check_path(p,s)  # The stationary cup is far from this sweep.
    p,s=inputs(port,holding=True)
    assert not port.check_path(p,s)
    assert port.last_check['reason']=='ROBOT_PATH_CONTACT' and port.last_check['contact_pair']==('cup','obstacle')


def test_allowed_contacts_are_phase_and_exact_pair_scoped(scene):
    port=checker(scene,{'CONTACT':{('arm','obstacle')}});p,s=inputs(port)
    assert not port.check_path(p,s)
    s['phase']='CONTACT';assert port.check_path(p,s)
    with pytest.raises(ValueError):checker(scene,{'CONTACT':{('cup','unknown')}})


def test_foreign_model_or_unknown_holding_and_missing_attachment_fail_closed(scene):
    port=checker(scene)
    for overrides in ({'model_sha256':'0'*64},{'holding_state':'UNKNOWN'},
                      {'holding_state':'HOLDING','cup_in_gripper_transform':None}):
        p,s=inputs(port);s.update(overrides);assert not port.check_path(p,s)


def test_velocity_acceleration_and_late_start_limits_reject_before_physics(scene):
    port=checker(scene);p,s=inputs(port)
    port.velocity_limits=(1.,)*6;assert not port.check_path(p,s)
    assert port.last_check['reason']=='PATH_VELOCITY_LIMIT'
    port.velocity_limits=(100.,)*6;port.acceleration_limits=(1.,)*6
    assert not port.check_path(p,s) and port.last_check['reason']=='PATH_ACCELERATION_LIMIT'
    port.acceleration_limits=(1e6,)*6;s['controller_start_time_s']=1.1
    assert not port.check_path(p,s) and port.last_check['reason']=='PATH_TIMING_INVALID'


def test_full_compiled_model_hash_detects_included_geometry_change(scene):
    a=mujoco.MjModel.from_xml_path(str(scene));scene.write_text(scene.read_text().replace('size=".06"','size=".08"'))
    b=mujoco.MjModel.from_xml_path(str(scene));assert model_sha256(a)!=model_sha256(b)


def test_future_clear_prefix_cannot_hide_collision_before_its_header(scene):
    port=checker(scene);p,s=inputs(port)
    s['controller_start_positions']=(1.,0.,0.,0.,0.,1.)
    # Both future-header and goal endpoints are clear. The new controller
    # trajectory connects current reference -1 to +1 before that header.
    s['controller_bridge']=dict(time_s=1.,point=dict(positions=(-1.,0.,0.,0.,0.,1.),velocities=(),accelerations=()))
    assert not port.check_path(p,s)
    assert port.last_check['reason']=='ROBOT_PATH_CONTACT'
    assert 1.<port.last_check['sample_time_s']<s['controller_start_time_s']


def test_missing_bridge_is_not_proof_of_a_safe_current_to_future_path(scene):
    port=checker(scene);p,s=inputs(port)
    s['controller_start_positions']=p['positions'][0]
    s.pop('controller_bridge',None)
    assert not port.check_path(p,s)
    assert port.last_check['reason']=='PATH_INPUT_INVALID'


@pytest.mark.parametrize('holding,allowed',[(False,{}),(False,{'CONTACT':{('arm','obstacle')}}),(True,{})])
def test_position_stage_collision_decisions_match_full_forward_dynamics(scene,holding,allowed,monkeypatch):
    port=checker(scene,allowed);p,s=inputs(port,holding=holding)
    if allowed:s['phase']='CONTACT'
    fast=port.check_path(p,s);fast_details=dict(port.last_check)
    # Independent engine oracle recomputes all forward dynamics; no forces
    # or integration are needed to decide geometric path contacts.
    monkeypatch.setattr(mujoco,'mj_fwdPosition',mujoco.mj_forward)
    full=checker(scene,allowed);p2,s2=inputs(full,holding=holding)
    if allowed:s2['phase']='CONTACT'
    assert full.check_path(p2,s2)==fast
    assert full.last_check==fast_details


def test_position_stage_contacts_match_full_engine_on_actual_robot_camera_scene():
    from pathlib import Path
    path=Path(__file__).resolve().parents[1]/'assets/mujoco/act/scene.xml'
    model=mujoco.MjModel.from_xml_path(str(path));model.geom_margin[:]=np.maximum(model.geom_margin,.002)
    full,position=mujoco.MjData(model),mujoco.MjData(model)
    rng=np.random.default_rng(317)
    addresses=[int(model.jnt_qposadr[mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_JOINT,n)]) for n in ('1','2','3','4','5','6','neck_yaw_joint')]
    for _ in range(50):
        q=model.key_qpos[0].copy();q[addresses]+=rng.uniform(-.4,.4,7)
        for d in (full,position):mujoco.mj_resetData(model,d);d.qpos[:]=q
        mujoco.mj_forward(model,full);mujoco.mj_fwdPosition(model,position)
        assert full.ncon==position.ncon
        assert [(c.geom1,c.geom2,c.dist) for c in full.contact]==[(c.geom1,c.geom2,c.dist) for c in position.contact]
        assert np.array_equal(full.geom_xpos,position.geom_xpos)
        assert np.array_equal(full.geom_xmat,position.geom_xmat)
def test_aggregate_contact_filter_matches_independent_full_contact_iteration(scene):
    import numpy as np
    port=checker(scene);rng=np.random.default_rng(20260917)
    protected=port.protected;cup=port.cup_geoms
    for i in range(70):
        mujoco.mj_resetData(port.model,port._data)
        port._data.qpos[port.joints[0]]=rng.uniform(-1.,1.)
        mujoco.mj_fwdPosition(port.model,port._data)
        for held in (False,True):
            for allowed in (frozenset(),frozenset((('arm','obstacle'),))):
                expected=None
                for contact in port._data.contact:
                    a,b=int(contact.geom1),int(contact.geom2)
                    if not (a in protected or b in protected or (held and (a in cup or b in cup))):continue
                    pair=tuple(sorted((port.names[a],port.names[b])))
                    if not math.isfinite(contact.dist) or (contact.dist<=port.clearance and pair not in allowed):
                        expected=(pair,float(contact.dist));break
                assert port._contact_violation(held,allowed)==expected
