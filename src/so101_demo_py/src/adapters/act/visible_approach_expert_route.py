"""Qualify a source-bound visible approach template before any permit."""

import copy
import hashlib
import json
from pathlib import Path
import time

from so101_demo.act.contracts import finite, sha256, validate_action_prefix
from so101_demo.act.execution import prefix_sha256
from so101_demo.act.path_proof import PathProof
from so101_demo.act.prefix_source import PrefixSourceReceipt, SOURCE_KEYS

from .pick_place_search_segment import PickPlaceSearchObservation
from .selected_approach_candidate import SelectedApproachCandidate
from .selected_search_source import freeze_selected_search_source


_ROLES = ("arm", "gripper", "neck")
_BRIDGE_NS = 100_000_000


def _digest(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class VisibleApproachExpertRoute:
    """Freeze the first candidate group under a separate expert identity."""

    def __init__(self, candidate: SelectedApproachCandidate, *,
                 policy_fingerprint: str, monotonic=time.monotonic):
        if not isinstance(candidate, SelectedApproachCandidate) or not callable(monotonic):
            raise ValueError("VISIBLE_APPROACH_EXPERT_CONFIG_INVALID")
        policy = sha256(policy_fingerprint)
        source = candidate.manifest
        first = source["segments"][0]
        if (source.get("eligible_for_collection") is not False
                or source.get("kind") != "ACT_VISIBLE_APPROACH_CANDIDATE"
                or first.get("first_segment") != 0
                or first.get("last_segment") != 11
                or first.get("samples") != 701):
            raise ValueError("VISIBLE_APPROACH_EXPERT_CONFIG_INVALID")
        self.candidate = candidate
        self.monotonic = monotonic
        self._candidate_manifest = source
        manifest = {
            "schema_version": 1,
            "kind": "VISIBLE_APPROACH_EXPERT_TEMPLATE",
            "source_candidate_manifest_sha256": source["manifest_sha256"],
            "source_route_sha256": source["source_route_sha256"],
            "candidate_profile_sha256": source["candidate_profile_sha256"],
            "model_sha256": source["model_sha256"],
            "scene_sha256": source["scene_sha256"],
            "policy_fingerprint": policy,
            "first_segment": 0,
            "last_segment": first["last_segment"],
            "first_prefix_rows_sha256": first["rows_sha256"],
            "path_step_s": .002,
            "path_clearance_m": .002,
            "phase": "APPROACH",
            "holding_state": "EMPTY",
            "contact_scope_sha256": _digest({
                "phase": "APPROACH", "allowed_contact_pairs": []}),
            "checker_sha256": hashlib.sha256(
                Path(__file__).with_name("physics.py").read_bytes()).hexdigest(),
            "expected_samples": 701,
            "eligible_for_collection": False,
            "command_authority": False,
        }
        manifest["manifest_sha256"] = _digest(manifest)
        self._manifest = manifest

    @property
    def manifest(self) -> dict:
        return copy.deepcopy(self._manifest)

    def prepare(self, observed, *, selected_source: dict, owner_ticket: tuple,
                active_policy_fingerprint: str) -> dict:
        """Prepare one exact prefix only when every selected SEARCH fence agrees."""
        try:
            if (not isinstance(observed, PickPlaceSearchObservation)
                    or self.candidate.manifest != self._candidate_manifest
                    or sha256(active_policy_fingerprint) !=
                       self._manifest["policy_fingerprint"]):
                raise ValueError("template")
            source = freeze_selected_search_source(
                observed, max_skew_s=self.candidate.max_skew)
            if (type(selected_source) is not dict or source != selected_source
                    or not isinstance(owner_ticket, tuple) or len(owner_ticket) != 5
                    or type(owner_ticket[0]) is not int or owner_ticket[0] < 1
                    or owner_ticket[2:] != (
                        "act", source["session_id"], source["attempt_id"])):
                raise ValueError("scope")
            physical = observed.stationary_physics_proof
            reference = observed.stationary_reference_proof
            owner = observed.local_owner_goal_proof
            native = observed.native_controller_ingress_proof
            proofs = (physical, reference, owner, native)
            stop = physical["stop_confirmed_wall_s"]
            if (any(type(proof) is not dict
                    or proof.get("selected_source_sha256") != source["observation_sha256"]
                    or proof.get("stop_confirmed_wall_s") != stop
                    or proof.get("command_authority") is not False
                    or proof.get("eligible_for_collection") is not False
                    for proof in proofs)
                    or physical.get("selected_physics_step") != source["physics_step"]
                    or physical.get("physics_step_fence") != observed.physics_step_fence
                    or physical.get("controller_interval_proof_required") is not True
                    or tuple(physical.get("model_qpos", ())) !=
                       tuple(observed.physical_readback["scene"]["qpos"])
                    or tuple(physical.get("model_qvel", ())) !=
                       tuple(observed.physical_readback["scene"]["qvel"])
                    or reference.get("owner_goal_interval_proof_required") is not True
                    or reference.get("selected_sim_time_ns") != round(
                        source["simulation_time_s"] * 1_000_000_000)
                    or reference.get("bridge_sim_time_ns") !=
                       reference["selected_sim_time_ns"] - _BRIDGE_NS
                    or owner.get("owner_generation") != owner_ticket[0]
                    or owner.get("reference_window_sha256") !=
                       reference.get("reference_window_sha256")
                    or owner.get("controller_native_ingress_proof_required") is not True
                    or native.get("owner_generation") != owner_ticket[0]
                    or native.get("reference_window_sha256") !=
                       reference.get("reference_window_sha256")
                    or native.get("control_event_window_sha256") !=
                       owner.get("control_event_window_sha256")
                    or native.get("commit_window_ingress_recheck_required") is not True
                    or sha256(native["native_ingress_window_sha256"]) !=
                       native["native_ingress_window_sha256"]):
                raise ValueError("proofs")
            stop_ns = round(finite(stop, nonnegative=True) * 1_000_000_000)
            latest_receipt_ns = max(round(finite(value, nonnegative=True)
                                          * 1_000_000_000)
                                    for value in source["source_received_wall_s"].values())
            now_ns = round(finite(self.monotonic(), nonnegative=True) * 1_000_000_000)
            snapshots = native["native_snapshots"]
            if (type(snapshots) is not dict or set(snapshots) != set(_ROLES)
                    or native.get("latest_source_receipt_monotonic_ns") != latest_receipt_ns
                    or not stop_ns <= latest_receipt_ns <= now_ns
                    or any(type(snapshots[kind]) is not dict
                           or snapshots[kind].get("role") != kind
                           or snapshots[kind].get("owner_generation") != owner_ticket[0]
                           or snapshots[kind].get("ingress_sequence") !=
                              native["ingress_sequence_by_controller"].get(kind)
                           or not 0 <= snapshots[kind]["last_ingress_monotonic_ns"]
                              <= stop_ns <= latest_receipt_ns
                              <= snapshots[kind]["observed_monotonic_ns"]
                              <= snapshots[kind]["received_monotonic_ns"] <= now_ns
                           for kind in _ROLES)):
                raise ValueError("native")
            candidate = self.candidate.prepare(observed, selected_source=source)
            prefix = validate_action_prefix(candidate["prefix"])
            if (candidate.get("eligible_for_collection") is not False
                    or candidate.get("command_authority") is not False
                    or candidate.get("candidate_manifest_sha256") !=
                       self._candidate_manifest["manifest_sha256"]
                    or _digest(prefix["positions"]) !=
                       self._manifest["first_prefix_rows_sha256"]
                    or prefix["sequence"] != 0
                    or prefix.get("target_interval_s") != .002
                    or len(prefix["positions"]) != 600
                    or freeze_selected_search_source(
                        observed, max_skew_s=self.candidate.max_skew) != source):
                raise ValueError("candidate")
            prepared = {
                "kind": "VISIBLE_APPROACH_EXPERT_PREPARATION",
                "selected_source": copy.deepcopy(source),
                "prefix": copy.deepcopy(prefix),
                "prefix_sha256": prefix_sha256(prefix),
                "owner_ticket": owner_ticket,
                "source_artifact_sha256": self._manifest["manifest_sha256"],
                "policy_fingerprint": self._manifest["policy_fingerprint"],
                "native_ingress_window_sha256": native["native_ingress_window_sha256"],
                "command_authority": False,
                "eligible_for_collection": False,
            }
            prepared["preparation_sha256"] = _digest(prepared)
            return prepared
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as error:
            raise ValueError("VISIBLE_APPROACH_EXPERT_ROUTE_INVALID") from error

    def qualify(self, prepared, proof, *, current_snapshot) -> dict:
        """Accept only one complete broker source-backed proof for the template."""
        try:
            if (type(prepared) is not dict
                    or prepared.get("kind") != "VISIBLE_APPROACH_EXPERT_PREPARATION"
                    or prepared.get("command_authority") is not False
                    or prepared.get("eligible_for_collection") is not False
                    or prepared.get("source_artifact_sha256") !=
                       self._manifest["manifest_sha256"]
                    or prepared.get("policy_fingerprint") !=
                       self._manifest["policy_fingerprint"]
                    or prepared.get("preparation_sha256") != _digest({
                        key: value for key, value in prepared.items()
                        if key != "preparation_sha256"})
                    or not isinstance(proof, PathProof)
                    or proof.status != "SAFE"
                    or proof.sample_count != self._manifest["expected_samples"]
                    or proof.first_violation is not None):
                raise ValueError("route or proof")
            prefix = validate_action_prefix(prepared["prefix"])
            source = prepared["selected_source"]
            ticket = prepared["owner_ticket"]
            request = proof.relative_request
            receipt = request.source_receipt
            if (type(source) is not dict
                    or not isinstance(ticket, tuple) or len(ticket) != 5
                    or type(ticket[0]) is not int or ticket[0] < 1
                    or ticket[2:] != ("act", source["session_id"], source["attempt_id"])
                    or prefix["session_id"] != source["session_id"]
                    or prefix["attempt_id"] != source["attempt_id"]
                    or prefix["observation_time_s"] != source["simulation_time_s"]
                    or prefix["sequence"] != 0
                    or prefix.get("target_interval_s") != .002
                    or len(prefix["positions"]) != 600
                    or _digest(prefix["positions"]) !=
                       self._manifest["first_prefix_rows_sha256"]
                    or prefix_sha256(prefix) != prepared.get("prefix_sha256")
                    or not isinstance(receipt, PrefixSourceReceipt)
                    or receipt.source_kind != "EXPERT_ROUTE"
                    or receipt.command_authority is not False
                    or receipt.source_artifact_sha256 !=
                       self._manifest["manifest_sha256"]
                    or receipt.contact_policy_fingerprint !=
                       self._manifest["policy_fingerprint"]
                    or receipt.observation_sha256 != source["observation_sha256"]
                    or receipt.source_received_wall_s != tuple(
                        (kind, source["source_received_wall_s"][kind])
                        for kind in SOURCE_KEYS)
                    or (receipt.source_phase, receipt.physics_step,
                        receipt.reset_epoch, receipt.owner_ticket, receipt.sequence) != (
                            "SEARCH", source["physics_step"], source["reset_epoch"],
                            ticket, 0)
                    or not request.matches_source(prefix)
                    or proof.owner_ticket != ticket
                    or proof.generation != ticket[0]
                    or proof.reset_epoch != source["reset_epoch"]
                    or proof.prefix_sha256 != prefix_sha256(prefix)
                    or proof.model_sha256 != self._manifest["model_sha256"]
                    or proof.policy_fingerprint != self._manifest["policy_fingerprint"]
                    or proof.profile_sha256 != self._manifest["candidate_profile_sha256"]
                    or proof.contact_scope_sha256 !=
                       self._manifest["contact_scope_sha256"]
                    or proof.checker_sha256 != self._manifest["checker_sha256"]):
                raise ValueError("proof binding")
            now = finite(self.monotonic(), nonnegative=True)
            if (not proof.started_wall_s <= proof.completed_wall_s <= now
                    or not 0 <= now - min(source["source_received_wall_s"].values())
                       < self.candidate.max_age
                    or not 0 <= now - receipt.prefix_issued_wall_s
                       < self.candidate.max_age):
                raise ValueError("source timing")
            if (type(current_snapshot) is not dict
                    or current_snapshot.get("phase") != self._manifest["phase"]
                    or current_snapshot.get("holding_state") !=
                       self._manifest["holding_state"]
                    or current_snapshot.get("cup_in_gripper_transform") is not None
                    or current_snapshot.get("model_sha256") !=
                       self._manifest["model_sha256"]
                    or current_snapshot.get("sim_time_s") !=
                       source["simulation_time_s"]
                    or proof.snapshot_sha256 != _digest(current_snapshot)
                    or proof.matches_state(current_snapshot) is not True
                    or request.source_bridge_ns !=
                       round((source["simulation_time_s"] - .1) * 1_000_000_000)
                    or request.source_start_ns !=
                       round((source["simulation_time_s"] + .05) * 1_000_000_000)):
                raise ValueError("physical state")
            return {
                "kind": "VISIBLE_APPROACH_EXPERT_QUALIFICATION",
                "route_qualified": True,
                "permit_required": True,
                "command_authority": False,
                "source_artifact_sha256": self._manifest["manifest_sha256"],
                "selected_source_sha256": source["observation_sha256"],
                "path_proof_sha256": proof.canonical_input_sha256,
                "owner_generation": ticket[0],
                "reset_epoch": source["reset_epoch"],
                "sample_count": proof.sample_count,
            }
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as error:
            raise ValueError("VISIBLE_APPROACH_EXPERT_PROOF_INVALID") from error
