"""The full Task 6 contact probe has one exact source-bound command path."""

import json
import os
import threading
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from so101_demo.act.approach_grasp_contact_diagnostic import (
    build_full_manifest, full_prefix_matches, require_full_sources,
)


PACKAGE = Path(__file__).resolve().parents[1]
SCENE = PACKAGE / "assets/mujoco/act/scene.xml"
PLUGIN = PACKAGE / "config/mujoco/act/task6_route_plugins.yaml"
ROUTE = PACKAGE / "config/mujoco/act/task6_visible_approach_v1.json"
CONTACT = PACKAGE / "config/mujoco/act/task6_contact_transition_v1.json"


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

    result = build_full_manifest(
        scene_path=SCENE, plugin_path=PLUGIN, route_profile_path=ROUTE,
        profile_path=CONTACT, proposal_path=proposal, receipt_path=receipt,
        session_id="full-contact-test", attempt_id="full-contact-attempt",
        pairs_factory=Pairs)
    return result, Pairs


def prefix(value, sequence):
    width = value["segment_rows"]
    start = sequence * width
    prior = value["joint_start_rad"] if sequence == 0 else value["target_positions"][start - 1]
    return dict(session_id=value["session_id"], attempt_id=value["attempt_id"],
                sequence=sequence, observation_time_s=1.,
                target_times_s=[1. + .1 * index for index in range(1, 11)],
                positions=[prior] + value["target_positions"][start:start + width])


def test_full_manifest_preserves_route_bridge_and_exact_contact_phases(tmp_path):
    value, pairs = manifest(tmp_path)
    require_full_sources(value, pairs_factory=pairs)
    assert value["eligible_for_collection"] is False
    assert len(value["segment_phases"]) == 281
    assert value["segment_phases"] == ["APPROACH"] * 248 + ["CONTACT"] * 33
    assert value["route_segment_count"] == 246
    assert value["contact_phase_start"] == 248
    assert value["bridge_rows_sha256"] == (
        "172ee8fe80388093a56045e5eea030f474c7ecd854fc08dd1683a59321ab051a")
    for sequence in (0, 245, 246, 247, 248, 280):
        assert full_prefix_matches(prefix(value, sequence), value)
    assert not full_prefix_matches(dict(prefix(value, 248), sequence=247), value)


def test_full_manifest_refuses_phase_row_and_collection_tamper(tmp_path):
    value, pairs = manifest(tmp_path)
    for key, changed in (
        ("segment_phases", ["APPROACH"] * 281),
        ("target_positions", [[0.] * 6] + value["target_positions"][1:]),
        ("bridge_rows_sha256", "0" * 64),
        ("eligible_for_collection", True),
    ):
        with pytest.raises(ValueError):
            require_full_sources(dict(value, **{key: changed}), pairs_factory=pairs)


def test_full_guard_preserves_no_contact_until_first_contact_prefix(tmp_path, monkeypatch):
    from so101_demo.act import task6_full_contact_diagnostic as full
    from so101_demo.act.ownership import Ownership
    from so101_demo.adapters.act.calibration_motion import (
        RosCalibrationMotionGuard, transition_motion_configuration)
    value, pairs = manifest(tmp_path)
    monkeypatch.setattr(full, "require_full_sources",
                        lambda source: require_full_sources(source, pairs_factory=pairs))
    config = transition_motion_configuration(value)
    assert config["contact_phase_start"] == 248
    assert config["allowed_pairs_by_phase"]["APPROACH"] == frozenset()

    class Node:
        def create_subscription(self, *args):
            return args

        def create_timer(self, *args):
            return args

    driver = NS(_lock=threading.RLock(), hazard_reason=None,
                goal_state=lambda _: dict(accepted=True, status=4,
                                          result={"error_code": 0}),
                stopped=lambda: True)
    broker = NS(ownership=Ownership(),
                prefix_executor=NS(adapter=NS(current_goal_ids=("arm", "gripper"))),
                tick=lambda: None)
    guard = RosCalibrationMotionGuard(Node(), driver, broker, value,
                                      evidence_root=tmp_path / "guard")
    try:
        assert guard.full_mode and guard.transition_mode
        assert guard.contact_observer.allowed == frozenset()
        assert guard._phase(prefix(value, 247)) == "APPROACH"
        assert guard._phase(prefix(value, 248)) == "CONTACT"
        guard._next_segment = 247
        assert guard._within(prefix(value, 247),
                             value["target_positions"][247 * 9 - 1], 0.)
        guard._next_segment = 248
        assert guard._within(prefix(value, 248),
                             value["target_positions"][248 * 9 - 1], 0.)
        assert not guard._within(prefix(value, 249),
                                 value["target_positions"][248 * 9 - 1], 0.)
    finally:
        guard.close()


def test_full_manifest_broker_refuses_tamper_before_domain_authority(tmp_path, monkeypatch):
    from so101_demo.act import task6_full_contact_diagnostic as full
    from so101_demo.adapters.act.domain_authority import DomainAuthority
    from so101_demo.cli.act_command_broker import main
    value, pairs = manifest(tmp_path)
    monkeypatch.setattr(full, "require_full_sources",
                        lambda source: require_full_sources(source, pairs_factory=pairs))
    monkeypatch.setattr(DomainAuthority, "acquire", lambda *_: (_ for _ in ()).throw(
        AssertionError("domain authority reached")))
    value["segment_phases"][248] = "APPROACH"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        main(["--socket", "/tmp/act-full-contact-gate-test.sock",
              "--session-id", value["session_id"], "--parent-pid", str(os.getpid()),
              "--lease-timeout-s", "30", "--calibration-mode",
              "--stop-velocity-rad-s", ".002", "--max-age-s", "1.5",
              "--submit-lead-s", ".05", "--accept-timeout-s", ".02",
              "--stop-timeout-s", "4", "--permit-ttl-s", "1.5",
              "--task6-contact-transition-manifest", str(path)])


def test_full_manifest_launch_preserves_route_speed_and_plugin(tmp_path, monkeypatch):
    from launch import LaunchContext
    from launch.utilities import perform_substitutions
    from launch.actions import DeclareLaunchArgument, OpaqueFunction
    from so101_demo.act import task6_full_contact_diagnostic as full
    from so101_demo.runtime import launch_composition as launch
    value, pairs = manifest(tmp_path)
    monkeypatch.setattr(full, "require_full_sources",
                        lambda source: require_full_sources(source, pairs_factory=pairs))
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
