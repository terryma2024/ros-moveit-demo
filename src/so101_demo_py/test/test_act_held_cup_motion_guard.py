"""The sole motion guard must prove holding before an isolated lift goal."""

import json
import threading
from pathlib import Path
from types import SimpleNamespace as NS

import mujoco
import pytest

from so101_demo.act.task6_full_contact_diagnostic import build_full_manifest
from so101_demo.act.held_cup_micro_lift_candidate import build_lift_candidate_manifest
from so101_demo.act.held_cup_micro_lift_diagnostic import (
    build_held_cup_diagnostic_manifest, require_held_cup_diagnostic_sources,
)
from so101_demo.adapters.act.calibration_motion import (
    RosCalibrationMotionGuard, held_cup_motion_configuration,
)
from so101_demo.act.ownership import Ownership


PACKAGE = Path(__file__).resolve().parents[1]
SCENE = PACKAGE / "assets/mujoco/act/scene.xml"
PLUGIN = PACKAGE / "config/mujoco/act/task6_route_plugins.yaml"
ROUTE = PACKAGE / "config/mujoco/act/task6_visible_approach_v1.json"
CONTACT = PACKAGE / "config/mujoco/act/task6_contact_transition_v1.json"
LIFT = PACKAGE / "config/mujoco/act/held_cup_micro_lift_candidates_v1.json"


class Pairs:
    model_sha256 = "3c876e7bbf879dbf614abfe8ecf48ca0eb43dc179a4124467f88b7ca755fdd78"
    fingerprint = "0ba8e07f16e448b16efe7b342745af7181678af47ddf45f975434919774dca11"

    def __init__(self, **kwargs):
        pass

    def for_phase(self, phase):
        assert phase in ("CLOSE", "MICRO_LIFT")
        return {("fixed_fingertip_pad_collision_006", "wall_near_collision")}


def manifest(tmp_path):
    proposal = tmp_path / "proposal.json"
    receipt = tmp_path / "receipt.json"
    proposal.write_text(json.dumps({"payload": {"thresholds": {
        "maximum_safe_force_n": 3.21, "minimum_bilateral_force_n": .1,
        "maximum_compression_distance_m": .0001}}}))
    receipt.write_text("{}")
    base = build_full_manifest(scene_path=SCENE, plugin_path=PLUGIN,
        route_profile_path=ROUTE, profile_path=CONTACT,
        proposal_path=proposal, receipt_path=receipt,
        session_id="held-guard", attempt_id="held-guard-attempt", pairs_factory=Pairs)
    candidate = build_lift_candidate_manifest(base, profile_path=LIFT,
                                               pairs_factory=Pairs)
    return build_held_cup_diagnostic_manifest(candidate, pairs_factory=Pairs)


def prefix(value, sequence):
    start = sequence * 9
    prior = value["joint_start_rad"] if start == 0 else value["target_positions"][start - 1]
    return dict(session_id=value["session_id"], attempt_id=value["attempt_id"],
                sequence=sequence, observation_time_s=1.,
                target_times_s=[1. + .1 * index for index in range(1, 11)],
                positions=[prior] + value["target_positions"][start:start + 9])


def test_held_motion_config_replays_source_and_keeps_phase_pairs(tmp_path, monkeypatch):
    from so101_demo.act import held_cup_micro_lift_diagnostic as source
    value = manifest(tmp_path)
    monkeypatch.setattr(source, "require_held_cup_diagnostic_sources",
                        lambda item: require_held_cup_diagnostic_sources(
                            item, pairs_factory=Pairs))
    config = held_cup_motion_configuration(value)
    assert config["kind"] == "ACT_HELD_CUP_MICRO_LIFT_DIAGNOSTIC"
    assert config["contact_phase_start"] == 248
    assert config["lift_phase_start"] == 281
    assert config["held_contact_limits"] == value["held_contact_limits"]
    assert config["allowed_pairs_by_phase"]["APPROACH"] == frozenset()
    assert config["allowed_pairs_by_phase"]["LIFT"]


def test_guard_arms_lossless_holding_before_first_lift_goal(tmp_path, monkeypatch):
    from so101_demo.act import held_cup_micro_lift_diagnostic as source
    value = manifest(tmp_path)
    monkeypatch.setattr(source, "require_held_cup_diagnostic_sources",
                        lambda item: require_held_cup_diagnostic_sources(
                            item, pairs_factory=Pairs))

    class Node:
        def create_subscription(self, *args):
            return args

        def create_timer(self, *args):
            return args

        def get_clock(self):
            return NS(now=lambda: NS(nanoseconds=1_000_000_000))

    reference = value["target_positions"][value["lift_phase_start"] * 9 - 1]
    driver = NS(_lock=threading.RLock(), hazard_reason=None,
                reference_state=lambda _: dict(positions=reference, velocities=[0.] * 6),
                goal_state=lambda _: dict(accepted=True, status=4,
                                          result={"error_code": 0}),
                stopped=lambda: True)
    broker = NS(ownership=Ownership(),
                prefix_executor=NS(adapter=NS(current_goal_ids=("arm", "gripper"))),
                tick=lambda: None)
    guard = RosCalibrationMotionGuard(Node(), driver, broker, value,
                                      evidence_root=tmp_path / "guard")
    calls = []
    try:
        assert guard.held_cup_mode and guard.transition_mode
        assert guard._phase(prefix(value, 280)) == "CONTACT"
        assert guard._phase(prefix(value, 281)) == "LIFT"
        guard._next_segment = value["lift_phase_start"]
        guard._joints = (tuple(reference) + (0.,), (0.,) * 7, 1., 0.)
        guard._live_ready = lambda: True
        guard._within = lambda *_: True
        guard._snapshot = lambda *_, **kwargs: calls.append(("snapshot", kwargs["phase"])) or {"holding_proof_physics_step": 77}
        guard.path.check_path = lambda *args: calls.append(("path", None)) or True
        guard.path.last_check = {}
        guard.contact_adapter.replace_allowed_pairs = lambda pairs: calls.append(("pairs", pairs))
        guard.contact_observer.safe = lambda: True
        guard.live_observer = NS(recorder=NS(arm_holding=lambda **kwargs:
            calls.append(("holding", kwargs))))
        goal = dict(header_stamp_s=1.05, time_from_start_s=1.,
                    positions=[reference[:5]])
        jaw = dict(header_stamp_s=1.05, time_from_start_s=1.,
                   positions=[reference[5:]])
        assert guard.check_exact_goals((goal, jaw), prefix(value, 281))
        assert calls[0] == ("snapshot", "LIFT")
        assert ("holding", dict(value["held_contact_limits"], proof_physics_step=77)) in calls
        assert ("pairs", guard.manifest["allowed_pairs_by_phase"]["LIFT"]) in calls
        assert guard._next_segment == 282
    finally:
        guard.live_observer = None
        guard.close()


def test_guard_lift_snapshot_uses_exact_physics_step_or_refuses(monkeypatch):
    from so101_demo.adapters.act import held_cup_state
    from so101_demo.act.joints import ACT_JOINTS

    model = mujoco.MjModel.from_xml_path(str(SCENE))
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_KEY, "task_start"))
    cup_joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "cup_free_joint")
    cup_address = int(model.jnt_qposadr[cup_joint])
    qpos = data.qpos.tolist()
    qpos[cup_address:cup_address + 7] = [.02, -.28, .165, 1., 0., 0., 0.]
    positions = tuple(qpos[int(model.jnt_qposadr[mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, name)])] for name in ACT_JOINTS)
    scene = dict(simulation_session_id="held-guard", reset_epoch=1,
                 simulation_step=77, simulation_time_s=1.048, paused=False,
                 qpos=qpos, qvel=[0.] * model.nv)
    stamp = NS(sec=1, nanosec=48_000_000)
    pose = NS(position=NS(x=.02, y=-.28, z=.165),
              orientation=NS(w=1., x=0., y=0., z=0.))
    cup = NS(simulation_session_id="held-guard", reset_epoch=1, paused=False,
             truncated=False, object_body="plastic_cup", header=NS(stamp=stamp),
             object_pose_world=pose)
    calls = []
    recorder = NS(validated_step=lambda step, **kwargs:
        calls.append(("lookup", step, kwargs)) or {"physics_step": step})
    monkeypatch.setattr(held_cup_state, "held_cup_attachment",
                        lambda *args, **kwargs:
                        calls.append(("proof", args[1]["simulation_step"],
                                      args[2]["physics_step"], kwargs)) or
                        [[1., 0., 0., 0.], [0., 1., 0., 0.],
                         [0., 0., 1., 0.], [0., 0., 0., 1.]])
    guard = NS(contact_mode=True, _cup_reset_verified=True,
               monotonic=lambda: 100.05, _lock=threading.RLock(),
               _joints=(positions, (0.,) * 7, 1.048, 100.),
               driver=NS(_lock=threading.RLock(), _epoch=(cup, 100.),
                         hazard_reason=None),
               contact_observer=NS(_lock=threading.RLock(),
                   last=dict(simulation_time_s=1.048), session="held-guard",
                   epoch=1, safe=lambda: True),
               scene_observer=NS(snapshot_with_receipt=lambda: (scene, 100.)),
               manifest=dict(session_id="held-guard", max_skew_s=.05,
                   max_age_s=.2, stop_velocity_rad_s=.002,
                   held_contact_limits={"minimum_bilateral_force_n": .1}),
               _start_safe=lambda *args: True, model=model,
               path=NS(cup_address=cup_address, model_sha256="a" * 64),
               held_cup_mode=True, live_observer=NS(recorder=recorder))
    result = RosCalibrationMotionGuard._snapshot(
        guard, dict(reset_epoch=1, sim_time_s=1.048), start=1.1,
        reference=positions[:6], reference_velocity=(0.,) * 6, phase="LIFT")
    assert result["holding_state"] == "HOLDING"
    assert result["holding_proof_physics_step"] == 77
    assert result["cup_in_gripper_transform"][3] == [0., 0., 0., 1.]
    assert calls[0][0:2] == ("lookup", 77)
    assert calls[1][0:3] == ("proof", 77, 77)
    recorder.validated_step = lambda *args, **kwargs: (_ for _ in ()).throw(
        ValueError("HELD_CUP_STEP_UNAVAILABLE"))
    with pytest.raises(ValueError, match="HELD_CUP_STEP_UNAVAILABLE"):
        RosCalibrationMotionGuard._snapshot(
            guard, dict(reset_epoch=1, sim_time_s=1.048), start=1.1,
            reference=positions[:6], reference_velocity=(0.,) * 6, phase="LIFT")
