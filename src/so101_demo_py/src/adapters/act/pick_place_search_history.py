"""Join original SEARCH physics frames to one selected observation."""

from so101_demo.act.contracts import finite

from .selected_search_source import freeze_selected_search_source
from .stationary_bridge_history import verify_stationary_physics_history


_HISTORY_STEPS = 51


def verify_search_stationary_physics(sources, observed, *, model,
                                     stopped_wall_s):
    """Return physical evidence only; controller and ownership fences follow."""
    try:
        stop_wall = finite(stopped_wall_s, nonnegative=True)
        raw = observed.physical_readback
        selected = freeze_selected_search_source(
            observed, max_skew_s=sources.readback.max_skew)
        scope = (selected["session_id"], selected["reset_epoch"])
        if ((sources.session_id, sources.reset_epoch) != scope
                or sources.phase != "SEARCH"):
            raise ValueError("SEARCH_HISTORY_SCOPE_INVALID")
        end_step = selected["physics_step"]
        first_step = end_step - (_HISTORY_STEPS - 1)
        if first_step < 1:
            raise ValueError("SEARCH_HISTORY_TOO_SHORT")
        marker = observed.physics_step_fence
        if (not isinstance(marker, dict)
                or marker.get("session_id") != scope[0]
                or marker.get("reset_epoch") != scope[1]
                or type(marker.get("request_sequence")) is not int
                or marker["request_sequence"] < 1
                or type(marker.get("marked_physics_step")) is not int
                or marker["marked_physics_step"] >= first_step
                or marker.get("command_authority") is not False):
            raise ValueError("SEARCH_HISTORY_FENCE_INVALID")
        sent = finite(marker["request_sent_wall_s"], nonnegative=True)
        received = finite(marker["ack_received_wall_s"], nonnegative=True)
        marked_ns = round(finite(marker["marked_simulation_time_s"], nonnegative=True)
                          * 1_000_000_000)
        if sent < stop_wall or received < sent:
            raise ValueError("SEARCH_HISTORY_FENCE_INVALID")

        def in_scope(frame, step_key):
            return ((frame.get("simulation_session_id"), frame.get("reset_epoch"))
                    == scope and first_step <= frame.get(step_key, -1) <= end_step)

        worlds = tuple(item for item in sources.world.recent_with_receipts()
                       if item.evidence.ordering_key[:2] == scope
                       and first_step <= item.evidence.simulation_step <= end_step)
        scenes = tuple((frame, receipt)
                       for frame, receipt in sources.scene.recent_frames_with_receipts()
                       if in_scope(frame, "simulation_step"))
        contacts = tuple((frame, receipt)
                         for frame, receipt in sources.contacts.recent_frames_with_receipts()
                         if in_scope(frame, "physics_step"))
        if any(len(items) != _HISTORY_STEPS for items in (
                worlds, scenes, contacts)):
            raise ValueError("SEARCH_HISTORY_INCOMPLETE")
        for world, (_, scene_receipt), (_, contact_receipt) in zip(
                worlds, scenes, contacts, strict=True):
            if any(finite(receipt, nonnegative=True) < stop_wall for receipt in (
                    world.received_monotonic_s, scene_receipt, contact_receipt)):
                raise ValueError("SEARCH_HISTORY_BEFORE_STOP")
            if any(finite(receipt, nonnegative=True) < received for receipt in (
                    world.received_monotonic_s, scene_receipt, contact_receipt)):
                raise ValueError("SEARCH_HISTORY_BEFORE_FENCE_ACK")
        if round(finite(worlds[0].evidence.simulation_time_s, nonnegative=True)
                 * 1_000_000_000) <= marked_ns:
            raise ValueError("SEARCH_HISTORY_FENCE_TIME_INVALID")
        proof = verify_stationary_physics_history(
            observed=observed, selected_source=selected,
            world_history=worlds, scene_history=scenes,
            contact_history=contacts, model=model,
            model_sha256=sources.contact_pairs.model_sha256,
            max_source_skew_s=sources.readback.max_skew,
            max_wall_age_s=sources.readback.max_wall_age,
            allowed_contact_pairs=sources.contact_pairs.for_phase("SEARCH"),
            stop_velocity_rad_s=sources.readback.broker.stop_velocity,
            monotonic=sources.readback.monotonic,
        )
        if ((sources.session_id, sources.reset_epoch) != scope
                or sources.phase != "SEARCH"
                or raw["world"].simulation_step != proof["selected_physics_step"]
                or proof["command_authority"] is not False
                or proof["eligible_for_collection"] is not False):
            raise ValueError("SEARCH_HISTORY_SCOPE_CHANGED")
        return {**proof, "stop_confirmed_wall_s": stop_wall,
                "physics_step_fence": dict(marker)}
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError,
            OverflowError) as error:
        raise ValueError("SEARCH_PHYSICS_HISTORY_INVALID") from error
