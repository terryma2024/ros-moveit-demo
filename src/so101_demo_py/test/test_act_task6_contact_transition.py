"""The contact transition stays exact, source pinned and noncollecting."""

import hashlib
import json
import os
import threading
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from so101_demo.act.grasp_contact_transition_diagnostic import (
    build_transition_manifest, build_transition_segments,
    prefix_matches_transition, require_transition_sources,
)


PACKAGE = Path(__file__).resolve().parents[1]
SCENE = PACKAGE / "assets/mujoco/act/scene.xml"
ROUTE_PROFILE = PACKAGE / "config/mujoco/act/task6_visible_approach_v1.json"
PROFILE = PACKAGE / "config/mujoco/act/task6_contact_transition_v1.json"
PLUGIN = PACKAGE / "config/mujoco/act/task6_route_plugins.yaml"


def manifest(tmp_path):
    proposal = tmp_path / "proposal.json"
    receipt = tmp_path / "receipt.json"
    proposal.write_text(json.dumps({"payload": {"thresholds": {
        "maximum_safe_force_n": 3.21}}}))
    receipt.write_text("{}")

    class Pairs:
        model_sha256 = "3c876e7bbf879dbf614abfe8ecf48ca0eb43dc179a4124467f88b7ca755fdd78"
        fingerprint = "0ba8e07f16e448b16efe7b342745af7181678af47ddf45f975434919774dca11"

        def __init__(self, **kwargs):
            pass

        def for_phase(self, phase):
            assert phase == "CLOSE"
            return {("fixed_fingertip_pad_collision_006", "wall_near_collision")}

    value = build_transition_manifest(
        scene_path=SCENE, route_profile_path=ROUTE_PROFILE,
        profile_path=PROFILE, plugin_path=PLUGIN, proposal_path=proposal,
        receipt_path=receipt, session_id="contact-transition-test",
        attempt_id="contact-transition-attempt", pairs_factory=Pairs)
    return value, Pairs


def segments(profile=PROFILE):
    return build_transition_segments(
        scene_path=SCENE, route_profile_path=ROUTE_PROFILE, profile_path=profile)


def test_transition_is_exact_phased_noncollecting_candidate():
    value = segments()
    profile = json.loads(PROFILE.read_text())
    assert profile["eligible_for_collection"] is False
    assert len(value) == 34
    assert value[0][0] == "APPROACH"
    assert all(phase == "CONTACT" for phase, _ in value[1:])
    assert all(len(rows) == 9 for _, rows in value)
    assert value[0][1][0] == profile["joint_start_rad"]
    assert value[-1][1][-1][5] == profile["close_q6_rad"]
    raw = json.dumps(value, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    assert hashlib.sha256(raw).hexdigest() == (
        "0e1be85eca2716ea31101b3fdfdd73bb72e4133067c10c0c9799ec288edb98bd")


def test_transition_profile_drift_refuses_before_target(tmp_path):
    changed = tmp_path / "changed.json"
    content = json.loads(PROFILE.read_text())
    content["eligible_for_collection"] = True
    changed.write_text(json.dumps(content))
    with pytest.raises(ValueError, match="drift"):
        segments(changed)


def test_transition_manifest_replays_sources_and_rejects_phase_or_row_tamper(tmp_path):
    value, pairs = manifest(tmp_path)
    require_transition_sources(value, pairs_factory=pairs)
    assert value["eligible_for_collection"] is False
    assert value["segment_phases"] == ["APPROACH"] + ["CONTACT"] * 33
    assert value["allowed_contact_pairs_by_phase"]["APPROACH"] == []
    first = dict(session_id=value["session_id"], attempt_id=value["attempt_id"],
                 sequence=0, observation_time_s=1.,
                 target_times_s=[1. + .1 * index for index in range(1, 11)],
                 positions=[value["joint_start_rad"]] + value["target_positions"][:9])
    assert prefix_matches_transition(first, value)
    assert not prefix_matches_transition(dict(first, sequence=1), value)
    for key, changed in (("segment_phases", ["CONTACT"] * 34),
                         ("target_positions", [[0.] * 6] + value["target_positions"][1:]),
                         ("eligible_for_collection", True)):
        bad = dict(value, **{key: changed})
        with pytest.raises(ValueError):
            require_transition_sources(bad, pairs_factory=pairs)


def test_transition_guard_configuration_is_phase_specific(tmp_path, monkeypatch):
    from so101_demo.act import task6_contact_transition as transition
    from so101_demo.adapters.act.calibration_motion import transition_motion_configuration
    value, pairs = manifest(tmp_path)
    monkeypatch.setattr(transition, "require_transition_sources",
                        lambda source: require_transition_sources(source, pairs_factory=pairs))
    config = transition_motion_configuration(value)
    assert config["eligible_for_collection"] is False
    assert config["max_rows"] == 10
    assert config["allowed_pairs_by_phase"]["APPROACH"] == frozenset()
    assert config["allowed_pairs_by_phase"]["CONTACT"]
    assert config["stop_max_age_s"] == 1.5


def test_transition_guard_requires_terminal_stop_and_uses_contact_phase(tmp_path, monkeypatch):
    from so101_demo.act import task6_contact_transition as transition
    from so101_demo.adapters.act.calibration_motion import RosCalibrationMotionGuard
    from so101_demo.act.ownership import Ownership
    value, pairs = manifest(tmp_path)
    monkeypatch.setattr(transition, "require_transition_sources",
                        lambda source: require_transition_sources(source, pairs_factory=pairs))

    class Node:
        def create_subscription(self, *args):
            return args

        def create_timer(self, *args):
            return args

    state = {"stopped": False}
    driver = NS(_lock=threading.RLock(), hazard_reason=None,
                goal_state=lambda _: dict(accepted=True, status=4,
                                          result={"error_code": 0}),
                stopped=lambda: state["stopped"])
    pair = NS(adapter=NS(current_goal_ids=("arm", "gripper")))
    broker = NS(ownership=Ownership(), prefix_executor=pair, tick=lambda: None)
    guard = RosCalibrationMotionGuard(Node(), driver, broker, value,
                                      evidence_root=tmp_path / "guard")
    try:
        assert guard.transition_mode
        assert guard.contact_observer.allowed == frozenset()
        assert guard.manifest["allowed_pairs_by_phase"]["APPROACH"] == frozenset()
        assert guard.manifest["allowed_pairs_by_phase"]["CONTACT"]
        first = dict(session_id=value["session_id"], attempt_id=value["attempt_id"],
                     sequence=0, observation_time_s=1.,
                     target_times_s=[1. + .1 * index for index in range(1, 11)],
                     positions=[value["joint_start_rad"]] + value["target_positions"][:9])
        assert guard._phase(first) == "APPROACH"
        assert guard._within(first, value["joint_start_rad"], 0.)
        guard._next_segment = 1
        second = dict(first, sequence=1,
                      positions=[value["target_positions"][8]] +
                                value["target_positions"][9:18])
        assert guard._phase(second) == "CONTACT"
        assert not guard._within(second, value["target_positions"][8], 0.)
        state["stopped"] = True
        assert guard._within(second, value["target_positions"][8], 0.)
        assert not guard._within(dict(second, sequence=2),
                                 value["target_positions"][8], 0.)
        with pytest.raises(ValueError, match="SEQUENCE"):
            guard._phase(dict(second, sequence=34))
    finally:
        guard.close()


@pytest.mark.parametrize("phase_start", [1, 248])
def test_contact_pairs_activate_only_after_exact_contact_goals_pass(phase_start):
    from collections import deque
    from so101_demo.adapters.act.calibration_motion import RosCalibrationMotionGuard
    allowed = frozenset({("cup_collision", "finger_collision")})
    state = {"path_safe": False}
    phases = []
    changes = []
    held = (0.,) * 6
    guard = NS(transition_mode=True, contact_mode=True, _next_segment=phase_start,
               contact_manifest={"segment_phases": ["APPROACH"] * phase_start + ["CONTACT"]},
               manifest={"max_age_s": .2, "contact_phase_start": phase_start,
                         "allowed_pairs_by_phase": {"CONTACT": allowed}},
               node=NS(get_clock=lambda: NS(now=lambda: NS(nanoseconds=1_030_000_000))),
               contact_observer=NS(epoch=1, safe=lambda: True),
               contact_adapter=NS(replace_allowed_pairs=lambda pairs: changes.append(pairs)),
               driver=NS(reference_state=lambda _: dict(positions=held, velocities=held)),
               _joints=((0.,) * 7,), audit=deque(maxlen=8),
               _live_ready=lambda: True, _within=lambda *_: True,
               _snapshot=lambda _base, **kwargs: phases.append(kwargs["phase"]) or {},
               _record_rejection=lambda *_: None,
               path=NS(check_path=lambda *_: state["path_safe"], last_check={"safe": True}))
    prefix = dict(session_id="contact-transition-test", attempt_id="attempt",
                  sequence=phase_start, observation_time_s=1.)
    goals = [dict(header_stamp_s=1.1, time_from_start_s=(.1,),
                  positions=(held[:3],)),
             dict(header_stamp_s=1.1, time_from_start_s=(.1,),
                  positions=(held[3:],))]
    assert not RosCalibrationMotionGuard.check_exact_goals(guard, goals, prefix)
    assert changes == [] and guard._next_segment == phase_start
    state["path_safe"] = True
    assert RosCalibrationMotionGuard.check_exact_goals(guard, goals, prefix)
    assert phases == ["CONTACT", "CONTACT"]
    assert changes == [allowed] and guard._next_segment == phase_start + 1


def test_transition_broker_rejects_phase_tamper_before_domain_authority(tmp_path, monkeypatch):
    from so101_demo.act import task6_contact_transition as transition
    from so101_demo.adapters.act.domain_authority import DomainAuthority
    from so101_demo.cli.act_command_broker import main
    value, pairs = manifest(tmp_path)
    monkeypatch.setattr(transition, "require_transition_sources",
                        lambda source: require_transition_sources(source, pairs_factory=pairs))
    monkeypatch.setattr(DomainAuthority, "acquire", lambda *_: (_ for _ in ()).throw(
        AssertionError("domain authority reached")))
    path = tmp_path / "manifest.json"
    value["segment_phases"][1] = "APPROACH"
    path.write_text(json.dumps(value))
    args = ["--socket", "/tmp/act-transition-gate-test.sock",
            "--session-id", value["session_id"], "--parent-pid", str(os.getpid()),
            "--lease-timeout-s", "30", "--calibration-mode",
            "--stop-velocity-rad-s", ".002", "--max-age-s", "1.5",
            "--submit-lead-s", ".05", "--accept-timeout-s", ".02",
            "--stop-timeout-s", "4", "--permit-ttl-s", "1.5",
            "--task6-contact-transition-manifest", str(path)]
    with pytest.raises(ValueError):
        main(args)


def test_transition_launch_pins_route_speed_and_plugin(tmp_path, monkeypatch):
    from launch import LaunchContext
    from launch.utilities import perform_substitutions
    from launch.actions import DeclareLaunchArgument, OpaqueFunction
    from so101_demo.act import task6_contact_transition as transition
    from so101_demo.runtime import launch_composition as launch
    value, pairs = manifest(tmp_path)
    monkeypatch.setattr(transition, "require_transition_sources",
                        lambda source: require_transition_sources(source, pairs_factory=pairs))
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(value))
    description = launch.build_task_station_launch_description(act_profile=True)
    context = LaunchContext()
    for argument in description.entities:
        if isinstance(argument, DeclareLaunchArgument):
            context.launch_configurations[argument.name] = perform_substitutions(
                context, argument.default_value)
    context.launch_configurations.update(
        session_id=value["session_id"], mujoco_scene=value["scene_path"],
        act_task6_contact_transition_manifest=str(path), act_stop_velocity_rad_s=".002",
        act_max_age_s="1.5", act_submit_lead_s=".05",
        act_accept_timeout_s=".02", act_stop_timeout_s="4", act_permit_ttl_s="1.5")
    captured = []

    class Capture(Exception):
        pass

    def stack(*args, **kwargs):
        captured.append((kwargs["sim_speed_factor"], kwargs["plugin_config_filename"]))
        raise Capture

    monkeypatch.setattr(launch, "_mujoco_stack_actions", stack)
    opaque = next(action for action in description.entities
                  if isinstance(action, OpaqueFunction))
    with pytest.raises(Capture):
        opaque.execute(context)
    assert captured == [(.25, "task6_route_plugins.yaml")]
