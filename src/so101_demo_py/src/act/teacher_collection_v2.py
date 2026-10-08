"""Collection facts derived from `SO101_TEACHER_EVENT_V2` events (plan R9.9): no dispatch receipt, no broker stop proof.

* the verified reset is the `reset_complete` event: the first `SimulationEvidence` of the session and new reset epoch
  that the Teacher's own observer received;
* the first command is the first `phase_begin` that sent a goal: it carries the sim stamp at which the goal was sent;
* the normal end is the `normal_stop` event (the successful trajectory result plus the joint-state stop proof) followed
  by the `terminal` event.

Everything here is a pure function over documents; nothing reads a ROS topic or a port.
"""

from __future__ import annotations

from .contracts import fields, identifier, integer
from .native_endpoints import validate_source_clock

SCHEMA = "SO101_TEACHER_EVENT_V2"
EVENT_TYPES = frozenset({
    "reset_complete", "teacher_start_observation", "phase_begin", "phase_finish", "normal_stop",
    "teacher_end_observation", "terminal", "scene_operation"})
# The types the audit retains verbatim; scene operations are retained as scene associations instead.
RETAINED_TYPES = EVENT_TYPES - {"scene_operation"}
ENVELOPE_KEYS = frozenset({"schema", "seq", "type", "session_id", "reset_epoch", "attempt_id", "sim_time_ns",
                           "monotonic_ns", "payload"})
_SUMMARY_KEYS = frozenset({"schema", "accepted", "last_seq", "types"})
_STOPPED_JOINTS = tuple("123456")
STOP_VELOCITY_RAD_S = 0.002


def validate_teacher_event(document, *, identity=None):
    """The closed V2 envelope. A V1 schema, an unknown type or a foreign attempt is refused."""
    fields(document, ENVELOPE_KEYS)
    if document["schema"] != SCHEMA:
        raise ValueError("TEACHER_EVENT_SCHEMA_UNKNOWN")
    if document["type"] not in EVENT_TYPES:
        raise ValueError("TEACHER_EVENT_TYPE_UNKNOWN")
    integer(document["seq"], minimum=1)
    integer(document["reset_epoch"])
    identifier(document["session_id"])
    identifier(document["attempt_id"])
    for key in ("sim_time_ns", "monotonic_ns"):
        integer(document[key])
    if type(document["payload"]) is not dict:
        raise ValueError("TEACHER_EVENT_MALFORMED")
    if identity is not None and (document["session_id"], document["attempt_id"], document["reset_epoch"]) != (
            identity["session_id"], identity["attempt_id"], identity["reset_epoch"]):
        raise ValueError("TEACHER_EVENT_IDENTITY_MISMATCH")
    return document


def validate_event_summary(summary):
    fields(summary, _SUMMARY_KEYS)
    if summary["schema"] != SCHEMA:
        raise ValueError("TEACHER_EVENT_SCHEMA_UNKNOWN")
    integer(summary["accepted"])
    integer(summary["last_seq"])
    if type(summary["types"]) is not dict or any(
            key not in EVENT_TYPES or type(value) is not int or value < 1 for key, value in summary["types"].items()):
        raise ValueError("TEACHER_EVENT_SUMMARY_INVALID")
    return summary


_RESET_PAYLOAD_KEYS = frozenset({"session_id", "reset_epoch", "simulation_time_s", "simulation_step",
                                 "publisher_sequence", "received_monotonic_ns"})


def validate_reset_complete_payload(document) -> dict:
    """The `reset_complete` payload is a closed object that agrees with its own envelope.

    The boundary it names cannot be later than the event that announces it, on either clock.
    """
    import math
    payload = document["payload"]
    fields(payload, _RESET_PAYLOAD_KEYS)
    identifier(payload["session_id"])
    integer(payload["reset_epoch"])
    integer(payload["simulation_step"])
    integer(payload["publisher_sequence"])
    integer(payload["received_monotonic_ns"])
    sim = payload["simulation_time_s"]
    if type(sim) not in (int, float) or not math.isfinite(sim) or sim < 0:
        raise ValueError("TEACHER_RESET_COMPLETE_INVALID")
    if (payload["session_id"] != document["session_id"] or payload["reset_epoch"] != document["reset_epoch"]
            or round(sim * 1e9) > document["sim_time_ns"]
            or payload["received_monotonic_ns"] > document["monotonic_ns"]):
        raise ValueError("TEACHER_RESET_COMPLETE_INVALID")
    return payload


def first_command_clock(document):
    """The clock of the first command, or None when this `phase_begin` sent no goal."""
    if document["type"] != "phase_begin":
        return None
    payload = document["payload"]
    if payload.get("goal_sent") is not True:
        return None
    return validate_source_clock({"sim_time_ns": document["sim_time_ns"], "begin_monotonic_ns": document["monotonic_ns"],
                                  "end_monotonic_ns": document["monotonic_ns"]})


def normal_stop_boundary_from_event(document) -> dict:
    """The V2 normal-stop boundary of a `normal_stop` event (its proof is the Teacher's stop proof)."""
    proof = document["payload"]["proof"]
    clock = validate_source_clock(proof["source_clock"])
    return {
        "kind": "ACT_NORMAL_STOP_BOUNDARY", "schema_version": 2,
        "epoch": {"session_id": document["session_id"], "reset_epoch": document["reset_epoch"],
                  "simulation_step": proof["simulation_step"], "publisher_sequence": proof["publisher_sequence"],
                  "simulation_time_s": proof["sim_stamp_s"], "received_wall_s": proof["received_wall_s"]},
        "source_clock": clock, "confirmed_monotonic_ns": clock["end_monotonic_ns"],
        "stop_confirmed_wall_s": proof["stop_confirmed_wall_s"], "trajectory_result": proof["trajectory_result"],
        "joint_positions": dict(proof["joint_positions"]), "joint_velocities": dict(proof["joint_velocities"])}


def validate_reset_complete_matches(document, reset_boundary) -> None:
    """The Teacher's `reset_complete` event is consistent with the retained verified reset (CP-3425).

    The boundary is the Recorder's own first evidence of the epoch; the Teacher names the first evidence of its own observer,
    which cannot be earlier: same session, attempt and epoch, and neither its sequence nor its simulation time precede the
    boundary's.
    """
    payload = validate_reset_complete_payload(document)
    physical = reset_boundary["physical_source"]
    if (reset_boundary["schema_version"] != 3 or reset_boundary["session_id"] != document["session_id"]
            or reset_boundary["attempt_id"] != document["attempt_id"]
            or reset_boundary["reset_epoch"] != document["reset_epoch"]
            or physical["publisher_sequence"] > payload["publisher_sequence"]
            or physical["simulation_time_s"] > payload["simulation_time_s"]):
        raise ValueError("NATIVE_QC_RESET_EVENT_MISMATCH")


CONTINUITY_PERIOD_NS = 2_000_000          # one controller period at update_rate 500
CONTINUITY_STEP_LIMIT = 256               # gap steps kept per controller; the count is always complete
_CONTINUITY_KINDS = ("arm", "gripper", "neck")


def validate_reference_continuity(document):
    """The sealed `controller_state` gap report: per controller its frame count, gap count and the first gap steps."""
    fields(document, {"schema_version", "period_ns", "session_id", "reset_epoch", "kinds"})
    if document["schema_version"] != 2 or type(document["schema_version"]) is not int:
        raise ValueError("REFERENCE_CONTINUITY_VERSION_INVALID")
    if document["period_ns"] != CONTINUITY_PERIOD_NS or type(document["period_ns"]) is not int:
        raise ValueError("REFERENCE_CONTINUITY_PERIOD_INVALID")
    identifier(document["session_id"])
    integer(document["reset_epoch"], minimum=1)
    fields(document["kinds"], _CONTINUITY_KINDS)
    for block in document["kinds"].values():
        fields(block, {"frames", "gaps", "steps"})
        integer(block["frames"])
        integer(block["gaps"])
        if type(block["steps"]) is not list or len(block["steps"]) > CONTINUITY_STEP_LIMIT:
            raise ValueError("REFERENCE_CONTINUITY_STEPS_INVALID")
        for step in block["steps"]:
            if type(step) is not list or len(step) != 2 or any(type(item) is not int or item < 0 for item in step) \
                    or step[1] <= step[0]:
                raise ValueError("REFERENCE_CONTINUITY_STEPS_INVALID")
    return document


def validate_first_command_window(first_clock, window):
    """A current continuous window must agree with the first command's sim stamp (diagnostic windows claim none)."""
    if first_clock is not None and "first_command_s" in window:
        first = window["first_command_s"]
        if type(first) not in (int, float) or first != first_clock["sim_time_ns"] / 1e9:
            raise ValueError("NATIVE_DISPATCH_WINDOW_INVALID")


def validate_normal_end_window(stop_clock, window):
    if stop_clock is None:
        return
    validate_source_clock(stop_clock)
    value = window.get("physics_end_s")
    if type(value) not in (int, float) or value != stop_clock["sim_time_ns"] / 1e9:
        raise ValueError("NATIVE_NORMAL_END_WINDOW_INVALID")


def is_current_episode(inputs, events=()) -> bool:
    """A current (V2) episode: its frozen inputs are manifest schema 2, or it carries a `teacher_event_v2` row.

    The frozen manifest is digest-bound, so stripping every event from a current episode cannot select an older reader.
    """
    from .first_episode_inputs import MANIFEST_SCHEMA_VERSION
    return (isinstance(inputs, dict) and inputs.get("schema_version") == MANIFEST_SCHEMA_VERSION) or any(
        event.get("kind") == "teacher_event_v2" for event in events)
