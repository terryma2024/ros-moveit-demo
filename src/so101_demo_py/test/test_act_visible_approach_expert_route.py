"""The expert approach template needs a proved SEARCH source."""

from dataclasses import replace
from pathlib import Path

import pytest

from so101_demo.adapters.act.selected_approach_candidate import SelectedApproachCandidate
from so101_demo.adapters.act.selected_search_source import freeze_selected_search_source
from so101_demo.adapters.act.visible_approach_expert_route import VisibleApproachExpertRoute

from test_act_selected_approach_candidate import selected_observation


PACKAGE = Path(__file__).resolve().parents[1]
CONFIG = PACKAGE / "config/mujoco/act"
POLICY = "0ba8e07f16e448b16efe7b342745af7181678af47ddf45f975434919774dca11"
TICKET = (7, "lease", "act", "session-296", "attempt-296")


@pytest.fixture(scope="module")
def route():
    candidate = SelectedApproachCandidate(
        scene_path=PACKAGE / "assets/mujoco/act/scene.xml",
        plugin_path=CONFIG / "task6_route_plugins.yaml",
        source_profile_path=CONFIG / "task6_visible_approach_v1.json",
        candidate_profile_path=CONFIG / "visible_approach_candidate_v1.json",
        session_id=TICKET[3], attempt_id=TICKET[4],
        max_skew_s=.02, max_source_age_s=.2,
        joint_tolerance_rad=.002, cup_tolerance_m=.002,
        stop_velocity_rad_s=.002, monotonic=lambda: 10.1,
    )
    return VisibleApproachExpertRoute(candidate, policy_fingerprint=POLICY,
                                      monotonic=lambda: 10.1)


def proved_search(route):
    observed = selected_observation(route.candidate)
    marker = {"session_id": TICKET[3], "reset_epoch": 2,
              "marked_physics_step": 1, "command_authority": False}
    observed = replace(observed, physics_step_fence=marker)
    source = freeze_selected_search_source(observed, max_skew_s=.02)
    digest = source["observation_sha256"]
    reference_hash = "a" * 64
    event_hash = "b" * 64
    stop_wall_s = 9.99
    physical = {
        "selected_source_sha256": digest, "selected_physics_step": source["physics_step"],
        "model_qpos": tuple(observed.physical_readback["scene"]["qpos"]),
        "model_qvel": tuple(observed.physical_readback["scene"]["qvel"]),
        "physics_step_fence": marker, "stop_confirmed_wall_s": stop_wall_s,
        "controller_interval_proof_required": True,
        "command_authority": False, "eligible_for_collection": False,
    }
    references = {
        "selected_source_sha256": digest, "reference_window_sha256": reference_hash,
        "selected_sim_time_ns": 1_200_000_000,
        "bridge_sim_time_ns": 1_100_000_000,
        "stop_confirmed_wall_s": stop_wall_s,
        "owner_goal_interval_proof_required": True,
        "command_authority": False, "eligible_for_collection": False,
    }
    owner = {
        "selected_source_sha256": digest, "reference_window_sha256": reference_hash,
        "control_event_window_sha256": event_hash, "owner_generation": TICKET[0],
        "stop_confirmed_wall_s": stop_wall_s,
        "controller_native_ingress_proof_required": True,
        "command_authority": False, "eligible_for_collection": False,
    }
    snapshots = {
        kind: {"role": kind, "owner_generation": TICKET[0],
               "ingress_sequence": index + 1,
               "last_ingress_monotonic_ns": 9_985_000_000,
               "observed_monotonic_ns": 10_010_000_000,
               "received_monotonic_ns": 10_011_000_000,
               "command_authority": False}
        for index, kind in enumerate(("arm", "gripper", "neck"))
    }
    native = {
        "selected_source_sha256": digest,
        "reference_window_sha256": reference_hash,
        "control_event_window_sha256": event_hash,
        "owner_generation": TICKET[0], "stop_confirmed_wall_s": stop_wall_s,
        "latest_source_receipt_monotonic_ns": 10_000_000_000,
        "ingress_sequence_by_controller": {
            kind: snapshot["ingress_sequence"] for kind, snapshot in snapshots.items()},
        "native_snapshots": snapshots, "native_ingress_window_sha256": "c" * 64,
        "commit_window_ingress_recheck_required": True,
        "command_authority": False, "eligible_for_collection": False,
    }
    observed = replace(
        observed, stationary_physics_proof=physical,
        stationary_reference_proof=references,
        local_owner_goal_proof=owner, native_controller_ingress_proof=native)
    return observed, source


def test_expert_template_prepares_first_exact_prefix_without_a_permit(route):
    observed, source = proved_search(route)
    result = route.prepare(observed, selected_source=source,
                           owner_ticket=TICKET, active_policy_fingerprint=POLICY)
    assert route.manifest["kind"] == "VISIBLE_APPROACH_EXPERT_TEMPLATE"
    assert route.manifest["model_sha256"] == route.candidate.manifest["model_sha256"]
    assert route.manifest["path_step_s"] == .002
    assert route.manifest["path_clearance_m"] == .002
    assert result["source_artifact_sha256"] == route.manifest["manifest_sha256"]
    assert result["selected_source"] == source
    assert result["owner_ticket"] == TICKET
    assert result["native_ingress_window_sha256"] == "c" * 64
    assert result["prefix"]["sequence"] == 0
    assert len(result["prefix"]["positions"]) == 600
    assert result["command_authority"] is False
    assert result["eligible_for_collection"] is False
    assert route.candidate.manifest["eligible_for_collection"] is False


@pytest.mark.parametrize("change", [
    "physical_hash", "reference_hash", "owner_hash", "native_hash",
    "generation", "policy", "native_after_stop", "native_before_source",
    "source_changed", "candidate_positive",
])
def test_expert_template_refuses_unbound_search_or_route(route, change):
    observed, source = proved_search(route)
    policy = POLICY
    ticket = TICKET
    if change == "physical_hash":
        observed.stationary_physics_proof["selected_source_sha256"] = "0" * 64
    elif change == "reference_hash":
        observed.stationary_reference_proof["selected_source_sha256"] = "0" * 64
    elif change == "owner_hash":
        observed.local_owner_goal_proof["selected_source_sha256"] = "0" * 64
    elif change == "native_hash":
        observed.native_controller_ingress_proof["selected_source_sha256"] = "0" * 64
    elif change == "generation":
        ticket = (8, *TICKET[1:])
    elif change == "policy":
        policy = "0" * 64
    elif change == "native_after_stop":
        observed.native_controller_ingress_proof["native_snapshots"]["arm"][
            "last_ingress_monotonic_ns"] = 10_001_000_000
    elif change == "native_before_source":
        observed.native_controller_ingress_proof["native_snapshots"]["neck"][
            "observed_monotonic_ns"] = 9_999_000_000
    elif change == "source_changed":
        source = dict(source, physics_step=source["physics_step"] + 1)
    elif change == "candidate_positive":
        route.candidate._manifest["eligible_for_collection"] = True
    try:
        with pytest.raises(ValueError, match="VISIBLE_APPROACH_EXPERT_ROUTE_INVALID"):
            route.prepare(observed, selected_source=source,
                          owner_ticket=ticket, active_policy_fingerprint=policy)
    finally:
        if change == "candidate_positive":
            route.candidate._manifest["eligible_for_collection"] = False
