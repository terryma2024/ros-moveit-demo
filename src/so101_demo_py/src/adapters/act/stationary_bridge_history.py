"""Verify the physical history before a selected SEARCH frame without motion authority.

This checks original observer frames only. A controller publication and ownership
interval is a separate required proof; this result cannot authorize a goal.
"""

from so101_demo.act.contracts import finite, vector
from so101_demo.core.simulation.types import SimulationEvidence
from .contact_evidence import contact_hazard
from .physics import model_sha256 as hash_model
from .selected_search_source import freeze_selected_search_source


_FRAME_COUNT = 51
_STEP_NS = 2_000_000
_SPAN_NS = 100_000_000


def _receipt(value, now, max_age):
    stamp = finite(value, nonnegative=True)
    if not 0 <= now - stamp <= max_age:
        raise ValueError("STATIONARY_BRIDGE_RECEIPT_STALE")
    return stamp


def verify_stationary_physics_history(
    *, observed, selected_source, world_history, scene_history,
    contact_history, model, model_sha256, max_source_skew_s,
    max_wall_age_s, allowed_contact_pairs, stop_velocity_rad_s,
    monotonic,
):
    """Check exactly 51 original 500 Hz frames ending at selected SEARCH.

    The returned state is evidence for a future controller-interval check, not
    a path proof, broker receipt, permit or collection eligibility.
    """
    try:
        now = finite(monotonic(), nonnegative=True)
        max_age = finite(max_wall_age_s)
        skew = finite(max_source_skew_s)
        velocity_limit = finite(stop_velocity_rad_s)
        if min(max_age, skew, velocity_limit) <= 0:
            raise ValueError("STATIONARY_BRIDGE_CONFIG_INVALID")
        if hash_model(model) != model_sha256:
            raise ValueError("STATIONARY_BRIDGE_MODEL_INVALID")
        current_source = freeze_selected_search_source(
            observed, max_skew_s=skew)
        if selected_source != current_source:
            raise ValueError("STATIONARY_BRIDGE_SOURCE_CHANGED")
        for receipt in current_source["source_received_wall_s"].values():
            _receipt(receipt, now, max_age)
        if (not isinstance(allowed_contact_pairs, (set, frozenset))
                or any(len(history) != _FRAME_COUNT for history in (
                    world_history, scene_history, contact_history))):
            raise ValueError("STATIONARY_BRIDGE_HISTORY_INCOMPLETE")
        end_step = current_source["physics_step"]
        if end_step < _FRAME_COUNT:
            raise ValueError("STATIONARY_BRIDGE_HISTORY_INCOMPLETE")
        first_step = end_step - (_FRAME_COUNT - 1)
        end_ns = round(current_source["simulation_time_s"] * 1_000_000_000)
        first_ns = end_ns - _SPAN_NS
        source_identity = (current_source["session_id"],
                           current_source["reset_epoch"])
        selected_raw = observed.physical_readback
        base_qpos = base_qvel = base_object = None
        last_receipts = None
        previous_receipts = None
        for index, (world_item, scene_item, contact_item) in enumerate(zip(
            world_history, scene_history, contact_history, strict=True
        )):
            step = first_step + index
            expected_ns = first_ns + index * _STEP_NS
            world = world_item.evidence
            scene, scene_receipt = scene_item
            contact, contact_receipt = contact_item
            if (not isinstance(world, SimulationEvidence)
                    or type(scene) is not dict or type(contact) is not dict
                    or world.ordering_key != (*source_identity, step)
                    or world.paused is not False or world.truncated is not False
                    or world.has_contact or world.object_state is None
                    or (scene.get("simulation_session_id"),
                        scene.get("reset_epoch"), scene.get("simulation_step"))
                    != (*source_identity, step)
                    or scene.get("paused") is not False
                    or scene.get("model_sha256") != model_sha256
                    or (contact.get("simulation_session_id"),
                        contact.get("reset_epoch"), contact.get("physics_step"))
                    != (*source_identity, step)
                    or contact_hazard(contact, allowed_contact_pairs)):
                raise ValueError("STATIONARY_BRIDGE_FRAME_INVALID")
            times = (world.simulation_time_s, scene.get("simulation_time_s"),
                     contact.get("simulation_time_s"))
            if any(round(finite(t, nonnegative=True) * 1_000_000_000)
                   != expected_ns for t in times):
                raise ValueError("STATIONARY_BRIDGE_TIME_GAP")
            qpos = vector(scene.get("qpos"), model.nq)
            qvel = vector(scene.get("qvel"), model.nv)
            if any(abs(speed) > velocity_limit for speed in qvel):
                raise ValueError("STATIONARY_BRIDGE_MOVING")
            object_state = world.object_state
            if base_qpos is None:
                base_qpos, base_qvel, base_object = qpos, qvel, object_state
            elif (qpos != base_qpos or qvel != base_qvel
                  or object_state != base_object):
                raise ValueError("STATIONARY_BRIDGE_STATE_DRIFT")
            receipts = (
                _receipt(world_item.received_monotonic_s, now, max_age),
                _receipt(scene_receipt, now, max_age),
                _receipt(contact_receipt, now, max_age),
            )
            if (previous_receipts is not None
                    and any(old > new for old, new in zip(
                        previous_receipts, receipts, strict=True))):
                raise ValueError("STATIONARY_BRIDGE_RECEIPT_ORDER")
            previous_receipts = receipts
            if index == _FRAME_COUNT - 1:
                if (world != selected_raw["world"]
                        or scene != selected_raw["scene"]
                        or contact != selected_raw["contact"]):
                    raise ValueError("STATIONARY_BRIDGE_SELECTED_FRAME_CHANGED")
                last_receipts = receipts
        expected_receipts = current_source["source_received_wall_s"]
        if last_receipts != tuple(expected_receipts[key] for key in (
            "world", "scene", "contact"
        )):
            raise ValueError("STATIONARY_BRIDGE_SELECTED_RECEIPT_CHANGED")
        return {
            "first_physics_step": first_step,
            "selected_physics_step": end_step,
            "bridge_sim_time_s": first_ns / 1_000_000_000,
            "selected_sim_time_s": end_ns / 1_000_000_000,
            "interval_ns": _SPAN_NS,
            "model_qpos": base_qpos,
            "model_qvel": base_qvel,
            "selected_source_sha256": current_source["observation_sha256"],
            "controller_interval_proof_required": True,
            "command_authority": False,
            "eligible_for_collection": False,
        }
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as error:
        raise ValueError("STATIONARY_BRIDGE_PHYSICS_INVALID") from error
