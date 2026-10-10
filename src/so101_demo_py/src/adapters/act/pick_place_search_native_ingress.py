"""Bind selected SEARCH evidence to all three native action ingress cursors."""

import hashlib
import json

from so101_demo.act.contracts import finite

from .selected_search_source import freeze_selected_search_source


_CONTROLLERS = ("arm", "gripper", "neck")
_SNAPSHOT_KEYS = frozenset((
    "role", "owner_generation", "ingress_sequence",
    "last_ingress_monotonic_ns", "observed_monotonic_ns",
    "received_monotonic_ns", "command_authority",
))


def native_ingress_digest(snapshots):
    encoded = json.dumps(snapshots, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(b"SO101_SEARCH_NATIVE_INGRESS_V1\0" + encoded).hexdigest()


def _nanoseconds(value):
    return round(finite(value, nonnegative=True) * 1_000_000_000)


def verify_search_native_controller_ingress(
        broker, ticket, sources, observed, physical_proof, reference_proof,
        owner_proof, *, stopped_wall_s):
    """Return neutral proof that native controllers had no post-stop ingress."""
    try:
        selected = freeze_selected_search_source(
            observed, max_skew_s=sources.readback.max_skew)
        stop_ns = _nanoseconds(stopped_wall_s)
        max_age_ns = _nanoseconds(sources.readback.max_wall_age)
        latest_source_receipt_ns = max(
            _nanoseconds(value)
            for value in selected["source_received_wall_s"].values())
        generation = ticket[0]
        reservation_port = broker.reservation_port
        if (not isinstance(ticket, tuple) or len(ticket) != 5
                or type(generation) is not int or generation < 1
                or ticket[2:] != ("act", selected["session_id"], selected["attempt_id"])
                or (sources.session_id, sources.reset_epoch, sources.phase) !=
                   (selected["session_id"], selected["reset_epoch"], "SEARCH")
                or not 0 < max_age_ns
                or not stop_ns <= latest_source_receipt_ns
                or any(not isinstance(proof, dict)
                       or proof.get("selected_source_sha256") !=
                          selected["observation_sha256"]
                       or proof.get("stop_confirmed_wall_s") != stopped_wall_s
                       or proof.get("command_authority") is not False
                       for proof in (physical_proof, reference_proof, owner_proof))
                or physical_proof.get("selected_physics_step") != selected["physics_step"]
                or physical_proof.get("physics_step_fence") != observed.physics_step_fence
                or reference_proof.get("reference_window_sha256") !=
                   owner_proof.get("reference_window_sha256")
                or owner_proof.get("owner_generation") != generation
                or owner_proof.get("controller_native_ingress_proof_required") is not True
                or not isinstance(owner_proof.get("control_event_window_sha256"), str)
                or len(owner_proof["control_event_window_sha256"]) != 64
                or not callable(getattr(reservation_port, "snapshot_generation", None))):
            raise ValueError("SEARCH_NATIVE_SCOPE_INVALID")
        broker.ownership.require_ticket(ticket)
        if broker._armed_generation != generation or broker.driver.stopped() is not True:
            raise ValueError("SEARCH_NATIVE_BROKER_INVALID")

        snapshots = {}
        for kind in _CONTROLLERS:
            snapshot = reservation_port.snapshot_generation(ticket, kind)
            if type(snapshot) is not dict or set(snapshot) != _SNAPSHOT_KEYS:
                raise ValueError("SEARCH_NATIVE_SNAPSHOT_INVALID")
            sequence = snapshot["ingress_sequence"]
            last_ns = snapshot["last_ingress_monotonic_ns"]
            observed_ns = snapshot["observed_monotonic_ns"]
            received_ns = snapshot["received_monotonic_ns"]
            if (snapshot["role"] != kind
                    or type(snapshot["owner_generation"]) is not int
                    or snapshot["owner_generation"] != generation
                    or type(sequence) is not int or not 0 <= sequence < 2**64
                    or any(type(value) is not int for value in (
                        last_ns, observed_ns, received_ns))
                    or not 0 <= last_ns <= stop_ns <= latest_source_receipt_ns
                    or not latest_source_receipt_ns <= observed_ns <= received_ns
                    or (sequence == 0) != (last_ns == 0)
                    or snapshot["command_authority"] is not False):
                raise ValueError("SEARCH_NATIVE_SNAPSHOT_INVALID")
            snapshots[kind] = dict(snapshot)

        now_ns = _nanoseconds(sources.readback.monotonic())
        if (broker._armed_generation != generation
                or broker.reservation_port is not reservation_port
                or broker.driver.stopped() is not True
                or (sources.session_id, sources.reset_epoch, sources.phase) !=
                   (selected["session_id"], selected["reset_epoch"], "SEARCH")
                or freeze_selected_search_source(
                    observed, max_skew_s=sources.readback.max_skew) != selected
                or any(not 0 <= now_ns - snapshot["received_monotonic_ns"] <= max_age_ns
                       for snapshot in snapshots.values())
                or not 0 <= now_ns - latest_source_receipt_ns <= max_age_ns):
            raise ValueError("SEARCH_NATIVE_SCOPE_CHANGED")
        broker.ownership.require_ticket(ticket)
        digest = native_ingress_digest(snapshots)
        return {
            "owner_generation": generation,
            "selected_source_sha256": selected["observation_sha256"],
            "reference_window_sha256": reference_proof["reference_window_sha256"],
            "control_event_window_sha256": owner_proof["control_event_window_sha256"],
            "stop_confirmed_wall_s": stopped_wall_s,
            "latest_source_receipt_monotonic_ns": latest_source_receipt_ns,
            "ingress_sequence_by_controller": {
                kind: snapshots[kind]["ingress_sequence"] for kind in _CONTROLLERS},
            "native_snapshots": snapshots,
            "native_ingress_window_sha256": digest,
            "commit_window_ingress_recheck_required": True,
            "command_authority": False,
            "eligible_for_collection": False,
        }
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError,
            PermissionError, OSError, OverflowError) as error:
        raise ValueError("SEARCH_NATIVE_CONTROLLER_INGRESS_INVALID") from error
