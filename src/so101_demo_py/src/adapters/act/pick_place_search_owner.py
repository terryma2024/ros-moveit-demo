"""Join a selected SEARCH interval to local broker owner and goal events."""

from dataclasses import asdict
import hashlib
import json

from so101_demo.act.contracts import finite
from so101_demo.act.control_event_timeline import ControlEventTimeline

from .selected_search_source import freeze_selected_search_source


_QUIET_EVENTS = frozenset(("action_status", "stop_baseline_requested",
                           "stop_baseline_confirmed"))
_CONTROLLERS = frozenset(("arm", "gripper", "neck", "execute_trajectory"))


def verify_search_owner_goal_interval(broker, ticket, sources, observed,
                                      physical_proof, reference_proof, *,
                                      stopped_wall_s):
    """Return local event evidence; native controller ingress remains unproved."""
    try:
        stop_wall = finite(stopped_wall_s, nonnegative=True)
        stop_ns = round(stop_wall * 1_000_000_000)
        selected = freeze_selected_search_source(
            observed, max_skew_s=sources.readback.max_skew)
        now_ns = round(finite(sources.readback.monotonic(), nonnegative=True)
                       * 1_000_000_000)
        max_age_ns = round(finite(sources.readback.max_wall_age)
                           * 1_000_000_000)
        if (not isinstance(ticket, tuple) or len(ticket) != 5
                or ticket[2:] != ("act", selected["session_id"],
                                  selected["attempt_id"])
                or type(ticket[0]) is not int or ticket[0] < 1
                or (sources.session_id, sources.reset_epoch) !=
                   (selected["session_id"], selected["reset_epoch"])
                or sources.phase != "SEARCH"
                or max_age_ns <= 0
                or any(not 0 <= now_ns - round(receipt * 1_000_000_000)
                       <= max_age_ns
                       for receipt in selected["source_received_wall_s"].values())
                or not isinstance(physical_proof, dict)
                or not isinstance(reference_proof, dict)
                or any(proof.get("selected_source_sha256") !=
                       selected["observation_sha256"]
                       for proof in (physical_proof, reference_proof))
                or any(proof.get("stop_confirmed_wall_s") != stop_wall
                       for proof in (physical_proof, reference_proof))
                or physical_proof.get("command_authority") is not False
                or physical_proof.get("selected_physics_step") !=
                   selected["physics_step"]
                or reference_proof.get("command_authority") is not False
                or reference_proof.get("owner_goal_interval_proof_required") is not True
                or reference_proof.get("selected_sim_time_ns") != round(
                    selected["simulation_time_s"] * 1_000_000_000)):
            raise ValueError("SEARCH_OWNER_SOURCE_INVALID")
        broker.ownership.require_ticket(ticket)
        if (not isinstance(broker.control_events, ControlEventTimeline)
                or broker.reservation_port is None
                or broker._armed_generation != ticket[0]
                or broker.driver.stopped() is not True):
            raise ValueError("SEARCH_OWNER_BROKER_INVALID")
        timeline = broker.control_events
        events = timeline.since(0)
        acquisitions = [index for index, event in enumerate(events)
                        if (event.kind == "owner_acquired"
                            and (event.generation, event.owner,
                                 event.session_id, event.attempt_id) ==
                            (ticket[0], *ticket[2:]))]
        if len(acquisitions) != 1:
            raise ValueError("SEARCH_OWNER_ACQUISITION_INVALID")
        anchor = events[acquisitions[0]:]
        if anchor[0].wall_ns > stop_ns:
            raise ValueError("SEARCH_OWNER_ACQUISITION_LATE")
        baselines = [index for index, event in enumerate(anchor)
                     if event.kind == "stop_baseline_confirmed"
                     and event.wall_ns <= stop_ns]
        if not baselines:
            raise ValueError("SEARCH_OWNER_STOP_BASELINE_MISSING")
        baseline_index = baselines[-1]
        if any(event.kind.startswith("owner_") for event in anchor[1:]):
            raise ValueError("SEARCH_OWNER_CHANGED")

        def quiet(rows):
            for event in rows:
                if event.kind not in _QUIET_EVENTS:
                    raise ValueError("SEARCH_OWNER_GOAL_EVENT")
                if event.kind == "action_status":
                    kind, separator, active = (event.detail or "").partition("|")
                    if separator != "|" or kind not in _CONTROLLERS or active:
                        raise ValueError("SEARCH_OWNER_ACTIVE_GOAL")

        quiet(anchor[baseline_index + 1:])
        cursor = events[-1].sequence
        more = timeline.since(cursor)
        quiet(more)
        all_rows = (*anchor, *more)
        if any(not 0 <= event.wall_ns <= now_ns for event in all_rows):
            raise ValueError("SEARCH_OWNER_EVENT_TIME_INVALID")
        if (broker.driver.stopped() is not True
                or broker._armed_generation != ticket[0]
                or broker.reservation_port is None
                or (sources.session_id, sources.reset_epoch) !=
                   (selected["session_id"], selected["reset_epoch"])
                or sources.phase != "SEARCH"
                or freeze_selected_search_source(
                    observed, max_skew_s=sources.readback.max_skew) != selected):
            raise ValueError("SEARCH_OWNER_SCOPE_CHANGED")
        broker.ownership.require_ticket(ticket)
        encoded = json.dumps([asdict(event) for event in all_rows],
                             sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode()
        digest = hashlib.sha256(b"SO101_SEARCH_LOCAL_CONTROL_EVENTS_V1\0"
                                + encoded).hexdigest()
        return {
            "owner_generation": ticket[0],
            "control_event_first_sequence": anchor[0].sequence,
            "control_event_last_sequence": all_rows[-1].sequence,
            "control_event_window_sha256": digest,
            "selected_source_sha256": selected["observation_sha256"],
            "reference_window_sha256": reference_proof["reference_window_sha256"],
            "stop_confirmed_wall_s": stop_wall,
            "controller_native_ingress_proof_required": True,
            "command_authority": False,
            "eligible_for_collection": False,
        }
    except (AttributeError, IndexError, KeyError, TypeError, ValueError,
            PermissionError,
            RuntimeError, OverflowError) as error:
        raise ValueError("SEARCH_OWNER_GOAL_INTERVAL_INVALID") from error
