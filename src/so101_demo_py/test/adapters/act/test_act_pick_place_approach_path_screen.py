"""Independent path checks over a compiled model and a joined physical readback."""

from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading

import mujoco
import numpy as np
import pytest

from so101_demo.act.synchronizer import RgbObservationSynchronizer
from so101_demo.adapters.act.contact_evidence import RobotContactObserver
from so101_demo.adapters.act.scene_state import SceneStateObserver
from so101_demo.adapters.act.physics import MujocoPathChecker
from so101_demo.adapters.act.pick_place_readback import PickPlacePhysicalReadback
from so101_demo.adapters.act.pick_place_approach_goals import build_approach_goals
from so101_demo.adapters.act.pick_place_approach_path_screen import PickPlaceApproachPathScreen
from so101_demo.core.simulation.types import ObjectState, SimulationEvidence, ReceivedSimulationEvidence


@lru_cache(maxsize=1)
def _model_path():
    root = Path(tempfile.mkdtemp(prefix="approach-model-"))
    children = ''.join(
        f'<body name="link{i}" pos="{i} 0 0"><joint name="{i}" axis="0 0 1"/>'
        f'<geom name="link{i}" size=".01" mass=".01"/></body>' for i in range(2, 6))
    path = root / "scene.xml"
    path.write_text(f'''<mujoco><compiler angle="radian"/><option gravity="0 0 0"/><worldbody>
      <body name="base" pos="0 0 3"><joint name="1" axis="0 0 1"/>
        <geom name="base" size=".01" mass=".01"/>{children}
        <body name="gripper" pos="6 0 0"><joint name="6" axis="0 0 1" range="-.1 1.5"/>
          <geom name="gripper" size=".01" mass=".01"/></body>
        <body name="head" pos="7 0 0"><joint name="neck_yaw_joint" axis="0 0 1"/>
          <geom name="head" size=".01" mass=".01"/></body>
      </body>
      <body name="plastic_cup" pos=".1 -.2 .15"><freejoint name="cup_free_joint"/>
        <geom name="cup" size=".01" mass=".01"/></body>
    </worldbody></mujoco>''')
    return path


def physical_inputs():
    checker = MujocoPathChecker(
        _model_path(), protected_roots=("base",), cup_joint="cup_free_joint",
        gripper_body="gripper", path_step_s=.002, path_clearance_m=.01,
        velocity_limit_rad_s=(100.,) * 6, acceleration_limit_rad_s2=(1e6,) * 6,
        allowed_pairs_by_phase={"APPROACH": frozenset()})
    model = checker.model
    scene = SceneStateObserver(model_sha256=checker.model_sha256, nq=model.nq, nv=model.nv,
                               max_age_s=.2, monotonic=lambda: 3.)
    scene.reset("session-1", 2, source_floor_s=1.)
    qpos, qvel = tuple(model.qpos0), (0.,) * model.nv
    assert scene.accept(dict(simulation_session_id="session-1", reset_epoch=2,
                             simulation_step=10, paused=False, simulation_time_s=1.32,
                             model_sha256=checker.model_sha256, qpos=qpos, qvel=qvel,
                             clock_interval_begin_monotonic_ns=2_999_800_000,
                             clock_interval_end_monotonic_ns=2_999_900_000))
    contacts = RobotContactObserver(known_geoms={"base", "cup"}, allowed_pairs=set(),
                                   max_age_s=.2, max_sim_gap_s=.02, monotonic=lambda: 3.)
    contacts.reset("session-1", 2, source_floor_s=1.3)
    for step in range(1, 11):
        contacts.accept(dict(simulation_session_id="session-1", reset_epoch=2,
                             physics_step=step, simulation_time_s=1.3 + step * .002,
                             geom_a=[], geom_b=[], signed_distance_m=[], normal_force_n=[],
                             truncated=False, evidence_loss=False))
    assert contacts.safe()
    rgb = RgbObservationSynchronizer(max_age_s=.2, max_skew_s=.005, monotonic=lambda: 3.)
    rgb.reset("session-1")
    pixels = np.zeros((480, 640, 3), dtype=np.uint8)
    for name, content in (("head", pixels), ("wrist", pixels), ("arm", (0.,) * 6), ("neck", 0.)):
        rgb.push(name, "session-1", 1.32, content)
    state = ObjectState(body_id=1, body="plastic_cup", position_world=(.1, -.2, .15),
                        orientation_xyzw=(0., 0., 0., 1.), linear_velocity_world=(0.,) * 3,
                        angular_velocity_world=(0.,) * 3)
    world = SimulationEvidence(simulation_time_s=1.32, frame_id="world", publisher_sequence=10,
                               simulation_step=10, reset_epoch=2, simulation_session_id="session-1",
                               paused=False, object_state=state, has_contact=False,
                               minimum_signed_distance_m=0., maximum_normal_force_n=0., truncated=False,
                               left_fingertip_contacts=(), right_fingertip_contacts=(), other_object_contacts=())
    broker = SimpleNamespace(reference_state=lambda stamp: dict(
        positions=(0.,) * 6, velocities=(0.,) * 6, accelerations=(0.,) * 6,
        requested_sim_time_s=stamp))
    readback = PickPlacePhysicalReadback(
        SimpleNamespace(recent_with_receipts=lambda: (ReceivedSimulationEvidence(world, 3.),)),
        scene, contacts, rgb, broker, model=mujoco.MjModel.from_xml_path(str(_model_path())),
        expected_model_sha256=checker.model_sha256,
        expected_mujoco_version="3.12.0", max_source_skew_s=.005, max_wall_age_s=.2,
        joint_tolerance_rad=.001, cup_pose_tolerance_m=.001, cup_orientation_tolerance=.001,
        monotonic=lambda: 3.)
    captured = readback.capture("session-1", "attempt-1", 2)

    def capture(attempt_id, **kwargs):
        # Phase fixtures advance this joined baseline through their own simulated I/O.
        result = deepcopy(captured)
        result["observation"]["attempt_id"] = attempt_id
        return result

    sources = SimpleNamespace(
        session_id="session-1", reset_epoch=2, phase="APPROACH", readback=readback, contacts=contacts,
        contact_pairs=SimpleNamespace(model_sha256=checker.model_sha256, for_phase=lambda phase: frozenset()),
        monotonic=lambda: 3., capture=capture)
    screen = PickPlaceApproachPathScreen(
        search_port=SimpleNamespace(validated_search_observation=lambda: None), sources=sources,
        broker=broker, path_checker=checker, cancelled=threading.Event())
    prefix = dict(session_id="session-1", attempt_id="attempt-1", sequence=0,
                  observation_time_s=1.3, target_times_s=(1.4,), positions=((0.,) * 6,))
    goals = build_approach_goals(prefix, (0.,) * 6, header_stamp_s=1.35)
    return screen, prefix, goals, {}, sources, broker, object(), [], qpos, qvel


def _snapshot(screen, qpos, qvel):
    return dict(model_sha256=screen.path_checker.model_sha256, model_qpos=qpos, model_qvel=qvel,
                phase="APPROACH", holding_state="EMPTY", cup_in_gripper_transform=None,
                controller_start_time_s=1.35, controller_start_positions=(0.,) * 6,
                controller_start_velocities=(0.,) * 6,
                controller_bridge=dict(time_s=1.3, point=dict(
                    positions=(0.,) * 6, velocities=(0.,) * 6, accelerations=(0.,) * 6)))


def test_complete_pair_is_checked_without_mutating_saved_execution_state():
    screen, prefix, goals, _, sources, _, _, _, qpos, qvel = physical_inputs()
    assert sources.capture(prefix["attempt_id"], after_step=0)["world"].simulation_step == 10
    snapshot = _snapshot(screen, qpos, qvel)
    before = deepcopy(snapshot)
    assert screen.inspect(goals, prefix, snapshot=snapshot)["samples"] == 51
    assert snapshot == before


@pytest.mark.parametrize("mutation", ["foreign", "row", "offset", "missing", "extra"])
def test_changed_goal_cannot_pass_as_the_prefix(mutation):
    screen, prefix, goals, _, _, _, _, _, qpos, qvel = physical_inputs()
    goals = list(deepcopy(goals))
    if mutation == "foreign":
        goals[1]["attempt_id"] = "another-attempt"
    elif mutation == "row":
        goals[0]["positions"] = ((0.,) * 5, (.1,) * 5)
    elif mutation == "offset":
        goals[1]["time_from_start_s"] = (0., .1)
    elif mutation == "missing":
        goals[0].pop("sequence")
    else:
        goals[1]["extra"] = True
    with pytest.raises(ValueError, match="PICK_PLACE_APPROACH_GOALS_INVALID"):
        screen.inspect(goals, prefix, snapshot=_snapshot(screen, qpos, qvel))


def test_missing_saved_snapshot_and_cancelled_checks_refuse():
    screen, prefix, goals, _, _, _, _, _, qpos, qvel = physical_inputs()
    with pytest.raises(ValueError, match="SNAPSHOT_REQUIRED"):
        screen.inspect(goals, prefix)
    screen.cancelled.set()
    with pytest.raises(ValueError, match="CANCELLED"):
        screen.inspect(goals, prefix, snapshot=_snapshot(screen, qpos, qvel))


def test_foreign_model_and_changed_start_state_refuse():
    screen, prefix, goals, _, _, _, _, _, qpos, qvel = physical_inputs()
    for changes in ({"model_sha256": "f" * 64}, {"controller_start_positions": (.1,) * 6}):
        with pytest.raises(ValueError, match="PATH_UNSAFE"):
            screen.inspect(goals, prefix, snapshot={**_snapshot(screen, qpos, qvel), **changes})
