"""The expert approach template needs a proved SEARCH source."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from so101_demo.act.path_proof import PathProver, RelativePathRequest
from so101_demo.act.prefix_source import PrefixSourceAuthority
from so101_demo.adapters.act.physics import MujocoPathChecker
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
    clock = [10.1]
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
    expert = VisibleApproachExpertRoute(candidate, policy_fingerprint=POLICY,
                                        monotonic=lambda: clock[0])
    expert._test_clock = clock
    return expert


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


@pytest.fixture(scope="module")
def proven_prefix(route):
    observed, source = proved_search(route)
    prepared = route.prepare(observed, selected_source=source,
                             owner_ticket=TICKET, active_policy_fingerprint=POLICY)
    authority = PrefixSourceAuthority(
        ticket_guard=lambda ticket: None if ticket == TICKET else (_ for _ in ()).throw(
            PermissionError("WRONG_TICKET")),
        max_observation_age_s=.2, max_prefix_age_s=.2,
        monotonic=lambda: 10.1,
    )
    receipt = authority.issue(
        ticket=TICKET, prefix=prepared["prefix"], source=source,
        source_kind="EXPERT_ROUTE",
        source_artifact_sha256=prepared["source_artifact_sha256"],
        contact_policy_fingerprint=POLICY,
    )
    checker = MujocoPathChecker(
        PACKAGE / "assets/mujoco/act/scene.xml",
        protected_roots=("base",), cup_joint="cup_free_joint",
        gripper_body="gripper", path_step_s=.002, path_clearance_m=.002,
        velocity_limit_rad_s=[.25] * 6,
        acceleration_limit_rad_s2=[1.2] * 6,
        allowed_pairs_by_phase={},
    )
    raw = observed.physical_readback
    start = tuple(route.candidate.manifest["segments"][0]["prior"])
    snapshot = {
        "model_qpos": tuple(raw["scene"]["qpos"]),
        "model_qvel": tuple(raw["scene"]["qvel"]),
        "model_sha256": checker.model_sha256,
        "phase": "APPROACH", "holding_state": "EMPTY",
        "sim_time_s": source["simulation_time_s"],
        "controller_bridge": {"time_s": 1.1, "point": {
            "positions": start, "velocities": (0.,) * 6,
            "accelerations": (),
        }},
        "controller_start_time_s": 1.25,
        "controller_start_positions": start,
        "controller_start_velocities": (0.,) * 6,
        "cup_in_gripper_transform": None,
    }
    request = RelativePathRequest.from_source_receipt(
        prepared["prefix"], receipt=receipt,
        bridge_time_s=1.1, start_time_s=1.25,
    )
    calls = [0]
    original = checker.check_path

    def counted(prefix, physical):
        calls[0] += 1
        return original(prefix, physical)

    checker.check_path = counted
    proof = PathProver(checker, monotonic=lambda: 10.11).prove(
        request, snapshot, ticket=TICKET, reset_epoch=source["reset_epoch"],
        policy_fingerprint=POLICY,
        profile_sha256=route.manifest["candidate_profile_sha256"],
        contact_scope_sha256=route.manifest["contact_scope_sha256"],
        checker_sha256=route.manifest["checker_sha256"],
        expected_samples=701,
    )
    assert proof.status == "SAFE" and proof.sample_count == 701
    route._test_clock[0] = 10.12
    return prepared, proof, snapshot, calls


def test_one_complete_path_proof_qualifies_route_without_sending(proven_prefix, route):
    prepared, proof, snapshot, calls = proven_prefix
    qualified = route.qualify(prepared, proof, current_snapshot=snapshot)
    assert calls == [1]
    assert qualified["route_qualified"] is True
    assert qualified["permit_required"] is True
    assert qualified["command_authority"] is False
    assert qualified["path_proof_sha256"] == proof.canonical_input_sha256


@pytest.mark.parametrize("change", [
    "rows", "receipt", "generation", "policy", "state", "sample_count",
    "violation", "source", "profile", "model", "contact_scope", "checker",
    "native_digest", "stale_time",
])
def test_expert_route_refuses_changed_or_incomplete_path_proof(proven_prefix, route, change):
    prepared, proof, snapshot, _ = proven_prefix
    prepared = deepcopy(prepared)
    snapshot = deepcopy(snapshot)
    if change == "rows":
        rows = list(prepared["prefix"]["positions"])
        rows[0] = tuple(value + .001 for value in rows[0])
        prepared["prefix"]["positions"] = tuple(rows)
    elif change == "receipt":
        receipt = replace(proof.relative_request.source_receipt,
                          source_artifact_sha256="0" * 64)
        proof = replace(proof, relative_request=replace(
            proof.relative_request, source_receipt=receipt))
    elif change == "generation":
        proof = replace(proof, generation=TICKET[0] + 1)
    elif change == "policy":
        proof = replace(proof, policy_fingerprint="0" * 64)
    elif change == "state":
        snapshot["model_qvel"] = (.001,) + snapshot["model_qvel"][1:]
    elif change == "sample_count":
        proof = replace(proof, sample_count=700)
    elif change == "violation":
        proof = replace(proof, status="VIOLATION")
    elif change == "source":
        prepared["selected_source"]["observation_sha256"] = "0" * 64
    elif change == "profile":
        proof = replace(proof, profile_sha256="0" * 64)
    elif change == "model":
        proof = replace(proof, model_sha256="0" * 64)
    elif change == "contact_scope":
        proof = replace(proof, contact_scope_sha256="0" * 64)
    elif change == "checker":
        proof = replace(proof, checker_sha256="0" * 64)
    elif change == "native_digest":
        prepared["native_ingress_window_sha256"] = "0" * 64
    elif change == "stale_time":
        route._test_clock[0] = 10.3
    try:
        with pytest.raises(ValueError, match="VISIBLE_APPROACH_EXPERT_PROOF_INVALID"):
            route.qualify(prepared, proof, current_snapshot=snapshot)
    finally:
        route._test_clock[0] = 10.12
