"""Recheck the selected SEARCH controller ingress before the first goal pair."""

import hashlib
import json
import time

from so101_demo.act.contracts import finite
from so101_demo.act.execution import prefix_sha256
from so101_demo.act.path_proof import PathProof
from so101_demo.act.prefix_source import PrefixSourceReceipt, SOURCE_KEYS

from .pick_place_search_native_ingress import _SNAPSHOT_KEYS, native_ingress_digest
from .visible_approach_expert_route import _digest


_ROLES = ("arm", "gripper", "neck")


def _ns(value):
    return round(finite(value, nonnegative=True) * 1_000_000_000)


def verify_visible_approach_commit_ingress(
        broker, ticket, prepared, qualification, proof, native_proof,
        *, monotonic=time.monotonic, max_age_s):
    """Return neutral evidence; a caller must still obtain a permit and send."""
    try:
        if not callable(monotonic):
            raise ValueError("clock")
        max_age_ns = _ns(max_age_s)
        now_before_ns = _ns(monotonic())
        if (max_age_ns <= 0 or type(prepared) is not dict
                or prepared.get("kind") != "VISIBLE_APPROACH_EXPERT_PREPARATION"
                or prepared.get("command_authority") is not False
                or prepared.get("eligible_for_collection") is not False
                or prepared.get("preparation_sha256") != _digest({
                    key: value for key, value in prepared.items()
                    if key != "preparation_sha256"})
                or type(qualification) is not dict
                or qualification.get("kind") != "VISIBLE_APPROACH_EXPERT_QUALIFICATION"
                or qualification.get("route_qualified") is not True
                or qualification.get("permit_required") is not True
                or qualification.get("command_authority") is not False
                or not isinstance(proof, PathProof)
                or proof.status != "SAFE" or proof.sample_count != 701
                or proof.first_violation is not None
                or type(native_proof) is not dict
                or native_proof.get("commit_window_ingress_recheck_required") is not True
                or native_proof.get("command_authority") is not False
                or native_proof.get("eligible_for_collection") is not False):
            raise ValueError("preparation")
        source = prepared["selected_source"]
        receipt = proof.relative_request.source_receipt
        if (type(source) is not dict or type(ticket) is not tuple or len(ticket) != 5
                or type(ticket[0]) is not int or ticket[0] < 1
                or ticket != prepared["owner_ticket"]
                or ticket[2:] != ("act", source["session_id"], source["attempt_id"])
                or not isinstance(receipt, PrefixSourceReceipt)
                or receipt.source_kind != "EXPERT_ROUTE"
                or receipt.command_authority is not False
                or receipt.owner_ticket != ticket
                or receipt.source_phase != "SEARCH"
                or (receipt.reset_epoch, receipt.physics_step, receipt.sequence) != (
                    source["reset_epoch"], source["physics_step"], 0)
                or receipt.observation_sha256 != source["observation_sha256"]
                or receipt.source_received_wall_s != tuple(
                    (kind, source["source_received_wall_s"][kind])
                    for kind in SOURCE_KEYS)
                or receipt.source_artifact_sha256 != prepared["source_artifact_sha256"]
                or receipt.contact_policy_fingerprint != prepared["policy_fingerprint"]
                or receipt.prefix_sha256 != prepared["prefix_sha256"]
                or prefix_sha256(prepared["prefix"]) != receipt.prefix_sha256
                or proof.relative_request.matches_source(prepared["prefix"]) is not True
                or proof.owner_ticket != ticket or proof.generation != ticket[0]
                or proof.reset_epoch != source["reset_epoch"]
                or proof.prefix_sha256 != receipt.prefix_sha256
                or proof.policy_fingerprint != prepared["policy_fingerprint"]
                or qualification.get("source_artifact_sha256") !=
                   prepared["source_artifact_sha256"]
                or qualification.get("selected_source_sha256") !=
                   source["observation_sha256"]
                or qualification.get("path_proof_sha256") !=
                   proof.canonical_input_sha256
                or qualification.get("owner_generation") != ticket[0]
                or qualification.get("reset_epoch") != source["reset_epoch"]
                or qualification.get("sample_count") != proof.sample_count
                or native_proof.get("selected_source_sha256") !=
                   source["observation_sha256"]
                or native_proof.get("owner_generation") != ticket[0]
                or native_proof.get("native_ingress_window_sha256") !=
                   prepared["native_ingress_window_sha256"]):
            raise ValueError("source")
        baseline = native_proof["native_snapshots"]
        sequences = native_proof["ingress_sequence_by_controller"]
        stop_ns = _ns(native_proof["stop_confirmed_wall_s"])
        latest_source_ns = max(_ns(value) for value in
                               source["source_received_wall_s"].values())
        if (type(baseline) is not dict or set(baseline) != set(_ROLES)
                or type(sequences) is not dict or set(sequences) != set(_ROLES)
                or native_ingress_digest(baseline) !=
                   prepared["native_ingress_window_sha256"]
                or native_proof.get("latest_source_receipt_monotonic_ns") !=
                   latest_source_ns
                or not stop_ns <= latest_source_ns <= now_before_ns
                or not 0 <= now_before_ns - min(_ns(value) for value in
                    source["source_received_wall_s"].values()) < max_age_ns
                or not 0 <= now_before_ns - _ns(receipt.prefix_issued_wall_s)
                   < max_age_ns
                or any(type(baseline[role]) is not dict
                       or set(baseline[role]) != _SNAPSHOT_KEYS
                       or baseline[role]["role"] != role
                       or baseline[role]["owner_generation"] != ticket[0]
                       or baseline[role]["ingress_sequence"] != sequences[role]
                       or baseline[role]["command_authority"] is not False
                       or not 0 <= baseline[role]["last_ingress_monotonic_ns"]
                          <= stop_ns <= latest_source_ns
                          <= baseline[role]["observed_monotonic_ns"]
                          <= baseline[role]["received_monotonic_ns"]
                          <= now_before_ns
                       for role in _ROLES)):
            raise ValueError("baseline")
        port = broker.reservation_port
        if not callable(getattr(port, "snapshot_generation", None)):
            raise ValueError("port")
        broker.ownership.require_ticket(ticket)
        if broker._armed_generation != ticket[0] or broker.driver.stopped() is not True:
            raise ValueError("broker")
        snapshots = {}
        for role in _ROLES:
            snapshot = port.snapshot_generation(ticket, role)
            old = baseline[role]
            if (type(snapshot) is not dict or set(snapshot) != _SNAPSHOT_KEYS
                    or snapshot["role"] != role
                    or snapshot["owner_generation"] != ticket[0]
                    or type(snapshot["ingress_sequence"]) is not int
                    or snapshot["ingress_sequence"] != old["ingress_sequence"]
                    or type(snapshot["last_ingress_monotonic_ns"]) is not int
                    or snapshot["last_ingress_monotonic_ns"] !=
                       old["last_ingress_monotonic_ns"]
                    or snapshot["command_authority"] is not False
                    or any(type(snapshot[key]) is not int for key in (
                        "observed_monotonic_ns", "received_monotonic_ns"))
                    or not old["received_monotonic_ns"]
                       <= snapshot["observed_monotonic_ns"]
                       <= snapshot["received_monotonic_ns"]):
                raise ValueError("snapshot")
            snapshots[role] = dict(snapshot)
        now_after_ns = _ns(monotonic())
        if (broker.reservation_port is not port
                or broker._armed_generation != ticket[0]
                or broker.driver.stopped() is not True
                or any(not 0 <= now_after_ns - snapshot["received_monotonic_ns"]
                       <= max_age_ns for snapshot in snapshots.values())
                or not 0 <= now_after_ns - latest_source_ns < max_age_ns
                or not 0 <= now_after_ns - _ns(receipt.prefix_issued_wall_s)
                   < max_age_ns):
            raise ValueError("scope changed")
        broker.ownership.require_ticket(ticket)
        encoded = json.dumps(snapshots, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")
        return {
            "owner_generation": ticket[0],
            "selected_source_sha256": source["observation_sha256"],
            "source_artifact_sha256": prepared["source_artifact_sha256"],
            "path_proof_sha256": proof.canonical_input_sha256,
            "ingress_sequence_by_controller": dict(sequences),
            "commit_ingress_window_sha256": hashlib.sha256(
                b"SO101_VISIBLE_APPROACH_COMMIT_INGRESS_V1\0" + encoded).hexdigest(),
            "observed_monotonic_ns": now_after_ns,
            "command_authority": False,
            "eligible_for_collection": False,
        }
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError,
            PermissionError, TimeoutError, OSError, OverflowError) as error:
        raise ValueError("VISIBLE_APPROACH_COMMIT_INGRESS_INVALID") from error
