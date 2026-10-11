"""Event payload schemas and the typed checks of physics observations, frames and capture windows."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

from so101_demo.act.qc_session import cached_lines
from so101_demo.parallel_batch.contracts.common import ContractError
from so101_demo.parallel_batch.contracts.identity import LeaseIdentity


def _reference_target_s(sim_time_s):
    """The instant a row's label belongs to: stamp + 0.1 s, summed in the sources' own nanoseconds (the capture mints its target the
    same way). A stamp one nanosecond off the microsecond grid is a legal camera stamp; rounding the target to microseconds named a
    different instant than the reference the capture had accepted."""
    return (round(sim_time_s * 1_000_000_000) + round(_GRID_S * 1_000_000_000)) / 1_000_000_000


MANIFEST_KIND = "ACT_EPISODE_AUDIT"


_METADATA_FILES = ("source.json", "inputs.json", "episode.json")


_WINDOW_FIELDS = frozenset({"source_schedule", "streams_required", "cadence_s", "permitted_gaps_s",
                            "collection_start_s", "collection_end_s", "first_command_s",
                            "physics_end_s", "label_cutoff_s", "outcome"})


_WINDOW_OUTCOMES = ("complete", "no_command", "no_label", "interrupted_diagnostic")


_SCOPE_FIELDS = frozenset({"kind", "schema_version", "mode", "scene_id", "seed", "inputs_sha256"})


_SCOPE_MODES = ("formal", "preselected_target_diagnostic")


# recorded verbatim because the plan does not fix its key names here
_IDENTITY_REQUIRED = ("session_id", "attempt_id", "reset_epoch", "release_epoch")


# it ran under, and its attempt must be the episode's attempt
_LEASE_FIELDS = frozenset({"batch_id", "coordinator_epoch", "worker_id", "worker_generation",
                           "point_id", "attempt_id", "lease_generation",
                           "lease_issued_monotonic_s", "lease_deadline_monotonic_s"})


_STREAM_NAMES = ("acquisitions.jsonl", "row-bindings.jsonl", "events.jsonl",
                 "references.jsonl", "physics.jsonl")


SOURCE_KINDS = ("events", "references", "physics")


_ACQUISITION_FIELDS = frozenset({"camera", "session_id", "reset_epoch", "sequence", "task_sequence", "acquisition_id",
                                 "stamp_s", "received_monotonic_ns", "shape", "dtype", "pixel_sha256"})


_ROW_FIELDS = frozenset({"row_index", "sim_time_s", "head_acquisition_id",
                         "wrist_acquisition_id", "reference_sequence"})


_REFERENCE_FIELDS = frozenset({"sequence", "task_sequence", "reference_time_s", "source", "positions", "accepted"})


# record preserves all of them or none, so a partial raw history can never look complete
_REFERENCE_RAW_FIELDS = frozenset({"joint_names", "sim_stamp_ns", "received_monotonic_ns",
                                   "velocities"})


# projected action, all-or-nothing like the legacy group
_REFERENCE_FRAME_FIELDS = frozenset({"frames", "projected_positions", "projection_map"})


_FRAME_KINDS = ("arm", "gripper")


_FRAME_SIZES = {"arm": 5, "gripper": 1}


#: fixtures that predate the rule carry them
_FRAME_JOINT_NAMES = {"arm": ("1", "2", "3", "4", "5"), "gripper": ("6",)}


# record's target instant, and the projection map selects the evaluated value
_FRAME_FIELDS = frozenset({"joint_names", "published_positions", "published_velocities",
                           "evaluated_positions", "evaluated_velocities", "evaluation",
                           "sim_stamp_ns", "received_monotonic_ns", "observer_sequence"})


_EVALUATION_FIELDS = frozenset({"requested_sim_time_s", "basis", "goal_id", "accepted_sim_s",
                                "revoked_sim_s"})


_EVALUATION_BASES = ("published", "interval")


_EVENT_FIELDS = frozenset({"sequence", "task_sequence", "kind", "identity", "sim_time_s", "monotonic_ns",
                           "payload"})


# kind may carry, so a success boolean can never stand in for a physical fact
_EVENT_PAYLOADS = {
    "phase_start": frozenset({"phase"}),
    "phase_complete": frozenset({"phase", "physics_step"}),
    "run_complete": frozenset({"reason", "physics_step"}),
    "run_aborted": frozenset({"reason", "physics_step"}),
    "run_incomplete_evidence": frozenset({"reason", "physics_step"}),
    # the remaining kinds the plan requires; each value is typed below so a boolean can never stand in
    # for a physical fact and an unknown key cannot be smuggled into a known kind
    "dispatch": frozenset({"owner", "permit_id"}),
    "accept": frozenset({"permit_id"}),
    "revoke": frozenset({"permit_id", "reason"}),
    "stop": frozenset({"reason", "stopped_confirmed"}),
    "contact": frozenset({"left_contacts", "right_contacts", "table_contact"}),
    "release": frozenset({"release_epoch", "supported", "no_fingertip_contact"}),
    "final_check": frozenset({"placement_stable", "retreat_stable"}),
    # source alignment's record kinds (the passed protocol table, section 3): the key sets its five record types declare
    "alignment_apply": frozenset({"apply_event_id", "applied_at_s", "accepted"}),
    "alignment_query": frozenset({"query_id", "query_at_s", "request_bytes", "response_bytes"}),
    "alignment_receipt": frozenset({"receipt_id", "received_at_s", "clock_source", "uncertainty_s"}),
    "recorder_queue": frozenset({"queue_evidence"}),
    "physics_chunk": frozenset({"raw_chunk"}),
    "source_alignment": frozenset({"association"}),
    "world_source": frozenset({"world_source"}),
    "teacher_event": frozenset({"teacher_event"}),
    "teacher_event_summary": frozenset({"event_summary"}),
    "controller_reference": frozenset({"reference_continuity"}),
    "collection_boundary": frozenset({"collection_boundary"}),
}


_EVENT_STRINGS = {"phase": "phase", "reason": "reason", "owner": "dispatch", "permit_id": "accept",
                  "apply_event_id": "alignment_apply", "query_id": "alignment_query", "receipt_id": "alignment_receipt"}


_EVENT_FLAGS = {"stopped_confirmed", "table_contact", "supported", "no_fingertip_contact",
                "placement_stable", "retreat_stable", "accepted"}


_EVENT_COUNTS = {"left_contacts", "right_contacts", "request_bytes", "response_bytes"}


_PHYSICS_FIELDS = frozenset({"sequence", "task_sequence", "kind", "sim_time_s", "release_epoch", "observation"})


_PHYSICS_KINDS = ("support", "contact", "pose", "retract")


# (backends/mujoco/qualified_phases/release_retreat.py::evidence_dict) plus the verified support boolean
# the runner adds for support rows; another source would extend this set when it exists
_PHYSICS_OBSERVATION_FIELDS = frozenset({
    # the registered live sample (act/contact_live.py) carries the real source records
    "simulation_session_id", "model_qpos", "model_qvel", "cup_position_m", "cup_velocity_m_s",
    "left_contacts", "right_contacts", "other_contacts", "truncated",
    "diagnostic_hazard_breached",
    # the MuJoCo summary fields stay admissible for sources that only publish them; `physics_step` is the name
    # the registered step contract uses (F1), so it is admitted beside `simulation_step`
    "publisher_sequence", "simulation_time_s", "simulation_step", "physics_step", "reset_epoch", "paused",
    "cup_position_world_m", "cup_orientation_world_xyzw",
    "cup_linear_velocity_world_m_s", "cup_angular_velocity_world_rad_s", "left_contact_count",
    "right_contact_count", "table_contact", "other_contact_geoms", "maximum_normal_force_n",
    "supported",
    # the two records the owner ratified defining (Proposal C): what the readback observed, so the
    # gate booleans can be derived instead of asserted
    "planning_scene_observation", "controller_feedback"})


_SCENE_OBSERVATION_FIELDS = frozenset({"scene_revision", "attached_objects", "world_object_ids",
                                       "is_diff", "sim_time_s", "source"})


# from, beside `sim_time_s`, which stays the instant the record is *for* and the join its parent observation uses
_FEEDBACK_FIELDS = frozenset({"controller", "commanded_positions", "measured_positions",
                              "measured_velocities", "joint_names", "status_sequence", "sim_time_s",
                              "source_sim_time_s"})


_FEEDBACK_CONTROLLERS = ("arm", "gripper")


_FEEDBACK_SOURCE_SKEW_S = 0.1


_CONTACT_FIELDS = frozenset({"robot_geom", "object_body", "normal_force_n", "signed_distance_m"})


_CONTACT_LISTS = ("left_contacts", "right_contacts", "other_contacts")


# the required members are the ones the current producers actually publish; the registered live
# sample (left/right/other_contacts, model_qpos/qvel, cup_position_m/cup_velocity_m_s) is admitted and
# validated when present, and becomes required per kind once the port supplies it (Proposal C)
_PHYSICS_REQUIRED = {
    "support": frozenset({"simulation_time_s", "simulation_step", "table_contact", "supported"}),
    "contact": frozenset({"simulation_time_s", "simulation_step", "left_contact_count",
                          "right_contact_count", "table_contact"}),
    "pose": frozenset({"simulation_time_s", "simulation_step", "cup_position_world_m"}),
    "retract": frozenset({"simulation_time_s", "simulation_step", "cup_position_world_m"}),
}


_PHYSICS_REQUIRED_REGISTERED = {
    "support": frozenset({"left_contacts", "right_contacts", "other_contacts", "cup_position_m",
                          "supported"}),
    "contact": frozenset({"left_contacts", "right_contacts", "other_contacts", "cup_position_m",
                          "truncated", "diagnostic_hazard_breached"}),
    "pose": frozenset({"cup_position_m", "model_qpos"}),
    "retract": frozenset({"cup_position_m", "cup_velocity_m_s"}),
}


_PHYSICS_INTEGERS = {"simulation_step", "physics_step", "left_contact_count", "right_contact_count",
                     "publisher_sequence", "reset_epoch"}


_PHYSICS_BOOLEANS = {"table_contact", "supported", "paused"}


_PHYSICS_VECTORS = {"cup_position_world_m": 3, "cup_orientation_world_xyzw": 4,
                    "cup_linear_velocity_world_m_s": 3, "cup_angular_velocity_world_rad_s": 3}


_PHYSICS_STRINGS = {"other_contact_geoms"}


_PHYSICS_VECTOR_LISTS = {"model_qpos", "model_qvel", "cup_position_m", "cup_velocity_m_s"}


# the two cameras are published together
_GRID_S = 0.1


_MAX_SOURCE_AGE_S = 0.1


_MAX_SKEW_S = 0.0


_TOLERANCE_S = 1e-6


_MANIFEST_FIELDS = frozenset({"kind", "schema_version", "scope_sha256", "identity", "window",
                              "files"})


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reference_raw_ok(record, code: str) -> None:
    """Validate the observer's raw frame fields when a reference record carries them."""

    names = record["joint_names"]
    if (not isinstance(names, list) or not names
            or any(not isinstance(name, str) or not name for name in names)):
        raise ValueError(code)
    if type(record["sim_stamp_ns"]) is not int or record["sim_stamp_ns"] < 1:
        raise ValueError(code)
    if type(record["received_monotonic_ns"]) is not int or record["received_monotonic_ns"] < 1:
        raise ValueError(code)
    velocities = record["velocities"]
    if (not isinstance(velocities, list) or len(velocities) != len(names)
            or any(isinstance(value, bool) or not isinstance(value, (int, float))
                   or not math.isfinite(value) for value in velocities)):
        raise ValueError(code)


def _finite_vector(value, *, length: int | None = None) -> bool:
    return (isinstance(value, list) and (length is None or len(value) == length)
            and all(not isinstance(item, bool) and isinstance(item, (int, float))
                    and math.isfinite(item) for item in value))


def _scene_observation_ok(record) -> bool:
    if not isinstance(record, dict) or set(record) != _SCENE_OBSERVATION_FIELDS:
        return False
    ids = (record["attached_objects"], record["world_object_ids"])
    return (type(record["scene_revision"]) is int and record["scene_revision"] >= 0
            and all(isinstance(value, list)
                    and all(isinstance(item, str) and item for item in value) for value in ids)
            and all(value == sorted(value) for value in ids)
            and type(record["is_diff"]) is bool
            and not isinstance(record["sim_time_s"], bool)
            and isinstance(record["sim_time_s"], (int, float))
            and math.isfinite(record["sim_time_s"]) and record["sim_time_s"] >= 0
            and isinstance(record["source"], str) and record["source"])


def _feedback_ok(record) -> bool:
    if not isinstance(record, dict) or set(record) != _FEEDBACK_FIELDS:
        return False
    if record["controller"] not in _FEEDBACK_CONTROLLERS:
        return False
    names = record["joint_names"]
    if (not isinstance(names, list) or not names
            or any(not isinstance(name, str) or not name for name in names)
            # the length alone let any name list through; the registered names and dimensions of the
            # controller that produced the record are what make the vectors comparable to the action
            or tuple(names) != _FRAME_JOINT_NAMES.get(record["controller"])):
        return False
    for key in ("commanded_positions", "measured_positions", "measured_velocities"):
        if not _finite_vector(record[key], length=len(names)):
            return False
    if type(record["status_sequence"]) is not int or record["status_sequence"] < 1:
        return False
    if (isinstance(record["sim_time_s"], bool) or not isinstance(record["sim_time_s"], (int, float))
            or not math.isfinite(record["sim_time_s"]) or record["sim_time_s"] < 0):
        return False
    # the source instant must be a real instant, and it must belong to the instant the record is for: a source
    # stamp far from the join would mean the record claims measurements it did not take then
    source = record["source_sim_time_s"]
    if (isinstance(source, bool) or not isinstance(source, (int, float))
            or not math.isfinite(source) or source < 0):
        return False
    # a hair of slack, so a source stamp exactly at the skew bound is not refused by binary rounding
    return abs(source - record["sim_time_s"]) <= _FEEDBACK_SOURCE_SKEW_S + 1e-9


def controller_feedback_valid(records, sim_time_s) -> bool:
    """Validate the same ratified source records in live gates and sealed readback."""
    return (isinstance(records, (list, tuple)) and len(records) == 2
            and all(_feedback_ok(record) and record["sim_time_s"] == sim_time_s for record in records)
            and sorted(record["controller"] for record in records) == sorted(_FEEDBACK_CONTROLLERS))


def _reference_frames_ok(record, *, history: dict | None = None) -> None:
    """Validate the ratified per-frame raw history and its evaluation, or refuse."""

    frames = record["frames"]
    if not isinstance(frames, dict) or set(frames) != set(_FRAME_KINDS):
        raise ValueError("AUDIT_SCHEMA_INVALID")
    for kind, frame in frames.items():
        if not isinstance(frame, dict) or set(frame) not in (_FRAME_FIELDS, _FRAME_FIELDS | {"original_message"}):
            raise ValueError("AUDIT_SCHEMA_INVALID")
        if "original_message" in frame:
            from so101_demo.act.episode_reference_readback import verify_original_frame
            verify_original_frame(frame, kind)
        names = frame["joint_names"]
        if (not isinstance(names, list) or len(names) != _FRAME_SIZES[kind]
                or any(not isinstance(name, str) or not name for name in names)
                # the count alone let any six-entry map permute dimensions, so the names must be the
                # registered ones in their registered order — the action the projection is supposed to carry
                or tuple(names) != _FRAME_JOINT_NAMES[kind]):
            # the registered source publishes exactly five arm joints and one gripper joint
            raise ValueError("AUDIT_SCHEMA_INVALID")
        # both the publication and the evaluated value keep the order and length of the names
        for key in ("published_positions", "published_velocities", "evaluated_positions",
                    "evaluated_velocities"):
            if not _finite_vector(frame[key], length=len(names)):
                raise ValueError("AUDIT_SCHEMA_INVALID")
        for key in ("sim_stamp_ns", "received_monotonic_ns", "observer_sequence"):
            if type(frame[key]) is not int or frame[key] < 1:
                raise ValueError("AUDIT_SCHEMA_INVALID")
        if history is not None:
            previous = history.get(kind)
            if previous is not None and (frame["sim_stamp_ns"] <= previous["sim_stamp_ns"]
                                        or frame["received_monotonic_ns"]
                                        < previous["received_monotonic_ns"]
                                        or frame["observer_sequence"]
                                        <= previous["observer_sequence"]):
                # each kind's raw history keeps its own ordering across the stream
                raise ValueError("AUDIT_SCHEMA_INVALID")
            history[kind] = frame
    for kind, frame in frames.items():
        evaluation = frame["evaluation"]
        if not isinstance(evaluation, dict) or set(evaluation) != _EVALUATION_FIELDS:
            raise ValueError("AUDIT_SCHEMA_INVALID")
        if (not _finite_vector([evaluation["requested_sim_time_s"]])
                or evaluation["basis"] not in _EVALUATION_BASES):
            raise ValueError("AUDIT_SCHEMA_INVALID")
        target = evaluation["requested_sim_time_s"]
        if abs(target - record["reference_time_s"]) > _TOLERANCE_S:
            # every kind's evaluation must describe the instant the label actually uses
            raise ValueError("AUDIT_SCHEMA_INVALID")
        goal, accepted, revoked = (evaluation["goal_id"], evaluation["accepted_sim_s"],
                                   evaluation["revoked_sim_s"])
        if evaluation["basis"] == "interval":
            # an interval evaluation names the accepted goal it came from, with its acceptance stamp
            if not isinstance(goal, str) or not goal or not _finite_vector([accepted]):
                raise ValueError("AUDIT_SCHEMA_INVALID")
        elif goal is not None or accepted is not None:
            raise ValueError("AUDIT_SCHEMA_INVALID")
        if evaluation["basis"] == "published":
            # A publication is its own value at the target; a different instant/value needs a
            # proven accepted interval rather than an unverified evaluation claim.
            if (abs(frame["sim_stamp_ns"] - round(target * 1e9)) > round(_TOLERANCE_S * 1e9)
                    or frame["evaluated_positions"] != frame["published_positions"]
                    or frame["evaluated_velocities"] != frame["published_velocities"]):
                raise ValueError("AUDIT_SCHEMA_INVALID")
        if revoked is not None and not _finite_vector([revoked]):
            raise ValueError("AUDIT_SCHEMA_INVALID")
        if accepted is not None and accepted > target + _TOLERANCE_S:
            # an acceptance after the instant it is supposed to cover proves nothing
            raise ValueError("AUDIT_SCHEMA_INVALID")
        if revoked is not None and revoked < target - _TOLERANCE_S:
            # a goal revoked before the target instant may not label it
            raise ValueError("AUDIT_SCHEMA_INVALID")
    projected = record["projected_positions"]
    mapping = record["projection_map"]
    if not _finite_vector(projected, length=6) or not isinstance(mapping, list) or len(mapping) != 6:
        raise ValueError("AUDIT_SCHEMA_INVALID")
    seen = set()
    for index, pair in enumerate(mapping):
        if (not isinstance(pair, list) or len(pair) != 2 or pair[0] not in _FRAME_KINDS
                or type(pair[1]) is not int):
            raise ValueError("AUDIT_SCHEMA_INVALID")
        if (pair[0], pair[1]) in seen:
            # six dimensions of one action cannot reuse the same source dimension twice
            raise ValueError("AUDIT_SCHEMA_INVALID")
        seen.add((pair[0], pair[1]))
        # A.1 ratified: the map selects the evaluated value, the publication stays untouched
        source = frames[pair[0]]["evaluated_positions"]
        if pair[1] < 0 or pair[1] >= len(source):
            raise ValueError("AUDIT_SCHEMA_INVALID")
        if source[pair[1]] != projected[index]:
            # the six-dimensional action must be exactly the mapped source values
            raise ValueError("AUDIT_SCHEMA_INVALID")
    if list(record["positions"]) != list(projected):
        raise ValueError("AUDIT_SCHEMA_INVALID")
    # the map must be the canonical six-dimension action — the arm's five in their registered order, then
    # the gripper's one — because a permuted map with a correspondingly permuted projection proved nothing about
    # the order the controller actually receives
    if mapping != ([["arm", index] for index in range(_FRAME_SIZES["arm"])]
                   + [["gripper", index] for index in range(_FRAME_SIZES["gripper"])]):
        raise ValueError("AUDIT_SCHEMA_INVALID")


def _physics_observation_typed(observation, *, kind: str) -> bool:
    """Type the raw physics block the way the source contract declares it."""

    if (not isinstance(observation, dict) or not observation
            or not set(observation) <= _PHYSICS_OBSERVATION_FIELDS):
        return False
    # only the keys unique to the registered live sample identify that shape; `supported` is shared
    registered = set(observation) & {"left_contacts", "right_contacts", "other_contacts",
                                     "model_qpos", "model_qvel", "cup_position_m",
                                     "cup_velocity_m_s"}
    if registered:
        # a registered live sample must carry the measurements its kind is judged on
        if not (_PHYSICS_REQUIRED_REGISTERED[kind] | {"simulation_time_s"} <= set(observation)
                and ({"simulation_step", "physics_step"} & set(observation))):
            # F1: the registered step contract names the step `physics_step`, so a complete registered sample
            # must not be refused for lacking the summary source's name for the same quantity
            return False
    elif not _PHYSICS_REQUIRED[kind] <= set(observation):
        # the summary shape must still carry its own measurements, so a timestamp alone is never enough
        return False
    for key, value in observation.items():
        if key in _CONTACT_LISTS:
            if not isinstance(value, list):
                return False
            for contact in value:
                if not isinstance(contact, dict) or set(contact) != _CONTACT_FIELDS:
                    return False
                if (not isinstance(contact["robot_geom"], str) or not contact["robot_geom"]
                        or not isinstance(contact["object_body"], str) or not contact["object_body"]
                        or isinstance(contact["normal_force_n"], bool)
                        or not isinstance(contact["normal_force_n"], (int, float))
                        or not math.isfinite(contact["normal_force_n"]) or contact["normal_force_n"] < 0
                        or isinstance(contact["signed_distance_m"], bool)
                        or not isinstance(contact["signed_distance_m"], (int, float))
                        or not math.isfinite(contact["signed_distance_m"])):
                    return False
        elif key in _PHYSICS_VECTOR_LISTS:
            if (isinstance(value, bool) or not isinstance(value, list) or not value
                    or any(isinstance(item, bool) or not isinstance(item, (int, float))
                           or not math.isfinite(item) for item in value)):
                return False
        elif key == "planning_scene_observation":
            if (not _scene_observation_ok(value)
                    or value["sim_time_s"] != observation["simulation_time_s"]):
                # the record joins its parent observation by the instant, so no extra field is needed
                return False
        elif key == "controller_feedback":
            if (not isinstance(value, list) or not value
                    or any(not _feedback_ok(entry) for entry in value)
                    or any(entry["sim_time_s"] != observation["simulation_time_s"]
                           for entry in value)
                           # an arm-only collection, or one repeating a kind, was accepted;
                           # the action has two controllers, so exactly one record for each is the coverage required
                           or sorted(entry["controller"] for entry in value)
                           != sorted(_FEEDBACK_CONTROLLERS)):
                return False
        elif key in ("truncated", "diagnostic_hazard_breached"):
            if type(value) is not bool:
                return False
        elif key in _PHYSICS_INTEGERS:
            if type(value) is not int or value < 0:
                return False
        elif key in _PHYSICS_BOOLEANS:
            if type(value) is not bool:
                return False
        elif key in _PHYSICS_VECTORS:
            if (not isinstance(value, list) or len(value) != _PHYSICS_VECTORS[key]
                    or any(isinstance(item, bool) or not isinstance(item, (int, float))
                           or not math.isfinite(item) for item in value)):
                return False
        elif key in _PHYSICS_STRINGS:
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                return False
        elif key == "simulation_session_id":
            if not isinstance(value, str) or not value:
                return False
        elif key == "simulation_time_s":
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value < 0):
                return False
        elif key == "maximum_normal_force_n":
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value < 0):
                return False
        else:
            return False
    if kind == "support" and type(observation.get("supported")) is not bool:
        return False
    return True


def _event_identity_ok(event_identity, episode_identity, *, release_epoch: int | None) -> bool:
    """An event identity must be the episode's, with a legitimate release transition."""

    if not isinstance(event_identity, dict) or not isinstance(episode_identity, dict):
        return False
    if (event_identity.get("session_id") != episode_identity.get("session_id")
            or event_identity.get("attempt_id") != episode_identity.get("attempt_id")
            or event_identity.get("reset_epoch") != episode_identity.get("reset_epoch")):
        return False
    lease = episode_identity.get("lease")
    if lease is not None and event_identity.get("lease") != lease:
        # F3: when the episode names a registered lease, every event identity must carry that same lease, so a
        # foreign or missing lease cannot ride along with an otherwise matching episode identity.
        return False
    epoch = event_identity.get("release_epoch")
    if type(epoch) is not int or epoch < 0:
        return False
    if release_epoch is None:
        # the first event names the episode's own initial release epoch, the field `_IDENTITY_REQUIRED`
        # makes mandatory; the two constants remain only as the fallback for an identity declaring none
        initial = episode_identity.get("release_epoch")
        if type(initial) is int and initial >= 0:
            return epoch == initial
        return epoch in (0, 1)
    if epoch < release_epoch or epoch > release_epoch + 1:
        # the release epoch never goes backwards and advances one release at a time
        return False
    return True


#: source alignment's instants and uncertainties: finite reals, non-negative except an uncertainty
_EVENT_FLOATS = frozenset({"applied_at_s", "query_at_s", "received_at_s", "uncertainty_s"})


_EVENT_NULLABLE_STRINGS = frozenset({"clock_source"})


def _payload_typed(payload) -> bool:
    """Type every payload value the way its key declares, per kind."""

    for key, value in payload.items():
        if key in _EVENT_FLAGS:
            if type(value) is not bool:
                return False
        elif key in _EVENT_COUNTS:
            if type(value) is not int or value < 0:
                return False
        elif key == "physics_step":
            if type(value) is not int or value < 0:
                return False
        elif key == "release_epoch":
            if type(value) is not int or value < 0:
                return False
        elif key in _EVENT_FLOATS:
            # a float may be null: the protocol records no instant when no publication covered the record, and the
            # schema expresses that as null rather than a value promoted from another clock
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return False
            if not math.isfinite(value) or (key != "uncertainty_s" and value < 0):
                return False
        elif key in _EVENT_NULLABLE_STRINGS:
            if value is not None and (not isinstance(value, str) or not value):
                return False
        elif key in _EVENT_STRINGS:
            if not isinstance(value, str) or not value:
                return False
        elif key == "queue_evidence":
            from so101_demo.act.lossless_recorder import verify_queue_evidence
            try:
                verify_queue_evidence(value)
            except (KeyError, TypeError, ValueError):
                return False
        elif key == "raw_chunk":
            from so101_demo.act.raw_physics_chunks import verify_raw_chunk
            try:
                verify_raw_chunk(value)
            except (KeyError, TypeError, ValueError):
                return False
        elif key == "association":
            from so101_demo.act.scene_association import validate_scene_association
            try:
                validate_scene_association(value)
            except (KeyError, TypeError, ValueError):
                return False
        elif key == "world_source":
            from so101_demo.act.native_endpoints import validate_world_source
            try:
                validate_world_source(value, identity={"session_id": value["physics"]["simulation_session_id"],
                    "reset_epoch": value["physics"]["reset_epoch"]})
            except (KeyError, TypeError, ValueError):
                return False
        elif key == "teacher_event":
            from so101_demo.act.teacher_collection import RETAINED_TYPES, validate_teacher_event
            try:
                validate_teacher_event(value)
                if value["type"] not in RETAINED_TYPES:
                    return False
            except (KeyError, TypeError, ValueError):
                return False
        elif key == "event_summary":
            from so101_demo.act.teacher_collection import validate_event_summary
            try:
                validate_event_summary(value)
            except (KeyError, TypeError, ValueError):
                return False
        elif key == "reference_continuity":
            from so101_demo.act.teacher_collection import validate_reference_continuity
            try:
                validate_reference_continuity(value)
            except (KeyError, TypeError, ValueError):
                return False
        elif key == "collection_boundary":
            from so101_demo.act.collection_boundaries import validate_collection_boundary
            try:
                validate_collection_boundary(value)
            except (KeyError, TypeError, ValueError):
                return False
        else:
            return False
    return True


def _number(value) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and value >= 0)


def _window_ok(window, *, mode: str) -> bool:
    """The ratified window contract, including its per-outcome ordering rules."""

    if not isinstance(window, dict) or set(window) != _WINDOW_FIELDS:
        return False
    schedule = window["source_schedule"]
    if (not isinstance(schedule, dict) or not schedule
            or any(not isinstance(name, str) or not name or not isinstance(instants, list)
                   # an empty list satisfied every instant and gap test vacuously, so a schedule
                   # naming no instant for a stream is not a schedule
                   or not instants
                   or any(not _number(instant) for instant in instants)
                   or instants != sorted(instants)
                   for name, instants in schedule.items())
                # every claimed instant existed, but a shortened or duplicated schedule hid real
                # coverage, so the list must be strictly increasing — no repeats, nothing out of order
                or any(instants != sorted(set(instants)) for instants in schedule.values())):
        # a schedule is a chronological list per stream, not a set in arbitrary order
        return False
    # OWNER DECISION: `cadence_s`, `streams_required` and `permitted_gaps_s` are **episode
    # parameters**, not frozen inputs. F11 asked for them to be checked against the frozen policy, but the
    # frozen input roles (act/diagnostic_episode_inputs.py:37) define no window policy, so the audit checks them for
    # internal consistency here and, through `_window_matches_observed`, against what the episode observed.
    if (not isinstance(window["streams_required"], list) or not window["streams_required"]
            or any(not isinstance(name, str) or not name for name in window["streams_required"])
            or not _number(window["cadence_s"]) or window["cadence_s"] <= 0
            or not isinstance(window["permitted_gaps_s"], list)
            or any(not isinstance(gap, list) or len(gap) != 2 or not all(_number(v) for v in gap)
                   or gap[0] > gap[1] for gap in window["permitted_gaps_s"])):
        return False
    if window["outcome"] not in _WINDOW_OUTCOMES:
        return False
    for key in ("collection_start_s", "collection_end_s", "physics_end_s"):
        if not _number(window[key]):
            return False
    start, end, physics = (window["collection_start_s"], window["collection_end_s"],
                           window["physics_end_s"])
    if not start <= physics <= end:
        return False
    if any(instant < start - _TOLERANCE_S or instant > end + _TOLERANCE_S
           for instants in schedule.values() for instant in instants):
        # a scheduled instant outside the collection window is not part of this episode
        return False
    if any(not (start - _TOLERANCE_S <= gap[0] and gap[1] <= end + _TOLERANCE_S)
           for gap in window["permitted_gaps_s"]):
        # the negation must cover the whole conjunction; without the parentheses a gap that begins
        # inside the window and ends outside it satisfied `not A and B` and was accepted
        # a permitted gap outside the collection window is not a gap this episode could have had
        return False
    first, cutoff = window["first_command_s"], window["label_cutoff_s"]
    if window["outcome"] == "complete":
        if not _number(first) or not _number(cutoff):
            return False
        if not start <= first <= physics or not start <= cutoff <= physics:
            return False
        if cutoff + 0.1 > physics + _TOLERANCE_S:
            # the labelled instant's t + 0.1 reference target must be physically covered
            return False
    elif window["outcome"] == "no_command":
        if first is not None or cutoff is not None:
            return False
    elif window["outcome"] == "no_label":
        if not _number(first) or cutoff is not None:
            return False
    else:
        if mode != "preselected_target_diagnostic":
            # an interrupted window is diagnostic evidence, never a formal one
            return False
        if (first is not None and not _number(first)) or (cutoff is not None and not _number(cutoff)):
            return False
    return True


def _scope_ok(scope) -> bool:
    """The collection-scope document must be the closed kind/version/mode contract."""

    return bool(
        isinstance(scope, dict)
        and set(scope) == _SCOPE_FIELDS
        and scope.get("kind") == "ACT_COLLECTION_SCOPE" and scope.get("schema_version") == 1
        and scope.get("mode") in _SCOPE_MODES and isinstance(scope.get("scene_id"), str)
        and scope.get("scene_id") and type(scope.get("seed")) is int and scope["seed"] >= 0
        and _hex64(scope.get("inputs_sha256")))


def _identity_ok(identity, *, formal: bool = False) -> bool:
    if not (isinstance(identity, dict) and identity
            and all(key in identity for key in _IDENTITY_REQUIRED)
            and isinstance(identity.get("session_id"), str) and identity["session_id"]
            and isinstance(identity.get("attempt_id"), str) and identity["attempt_id"]
            and type(identity.get("reset_epoch")) is int and identity["reset_epoch"] >= 0
            and type(identity.get("release_epoch")) is int and identity["release_epoch"] >= 0):
        return False
    if not formal:
        return True
    lease = identity.get("lease")
    if not isinstance(lease, dict) or set(lease) != _LEASE_FIELDS:
        return False
    try:
        parsed = LeaseIdentity(**lease)
    except (ContractError, TypeError, ValueError):
        return False
    return parsed.attempt_id == identity["attempt_id"]


def _closed(record, fields: frozenset, code: str) -> dict:
    if not isinstance(record, dict) or set(record) != fields:
        raise ValueError(code)
    return record


def _finite(value, code: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(code)
    if nonnegative and value < 0:
        raise ValueError(code)
    return float(value)


def _integer(value, code: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(code)
    return value


@dataclass(frozen=True)
class _Files:
    source: Path
    inputs: Path
    episode: Path
    acquisitions: Path
    row_bindings: Path
    events: Path
    references: Path
    physics: Path

    def streams(self) -> dict:
        return {"acquisitions": self.acquisitions, "row-bindings": self.row_bindings,
                "events": self.events, "references": self.references, "physics": self.physics}


def _capture_window_matches_observed(window, row_times, acquisitions, *, mode):
    """Recompute the continuous camera inventory and label clocks in either scope."""
    if (not _window_ok(window, mode=mode)
            or window["streams_required"] != ["head", "wrist"]
            or set(window["source_schedule"]) != {"head", "wrist"}
            or window["cadence_s"] != _GRID_S or window["permitted_gaps_s"] != []):
        return False
    observed = {camera: sorted(row["stamp_s"] for row in acquisitions.values()
                               if row["camera"] == camera) for camera in ("head", "wrist")}
    if (any(not stamps or stamps != sorted(set(stamps)) for stamps in observed.values())
            or window["source_schedule"] != observed):
        return False
    stamps = [stamp for values in observed.values() for stamp in values]
    if (window["collection_start_s"] != min(stamps) or window["collection_end_s"] != max(stamps)
            or any(later - earlier > _GRID_S * 1.5 + _TOLERANCE_S
                   for values in observed.values() for earlier, later in zip(values, values[1:]))):
        return False
    # Source/audit sequences and row instants were already validated at ingress/readback.
    # The physical stop and first dispatch need their own original boundary proof;
    # neither clock is inferred from a camera or from a physics-history extreme here.
    if row_times:
        return (window["outcome"] in ("complete", "interrupted_diagnostic")
                and window["label_cutoff_s"] == max(row_times))
    return window["outcome"] != "complete" and window["label_cutoff_s"] is None


def _window_matches_observed(window: dict, row_times, acquisitions, physics_times=()) -> bool:
    """One predicate for the window, shared by the seal and the readback."""

    """A formal window must describe the rows and acquisitions this audit actually holds."""

    if window["outcome"] == "complete":
        if not row_times or abs(window["label_cutoff_s"] - max(row_times)) > _TOLERANCE_S:
            # the cutoff is the last labelled observation, not a number chosen to fit
            return False
    elif row_times:
        # an outcome other than complete may not accompany labelled rows
        return False
    # the endpoints are compared with the physics history they claim to summarise — the command is
    # issued before the physics moves and the end must cover the last row
    if physics_times:
        # the endpoints are DERIVED from the physics history rather than merely enclosing
        # it - a window claiming 1.2 while every row ends at 1.1 was accepted by an inequality and is not now
        if (abs(window["first_command_s"] - min(physics_times)) > _TOLERANCE_S
                or abs(window["physics_end_s"] - max(physics_times)) > _TOLERANCE_S):
            return False
    schedule = window["source_schedule"]
    if set(window["streams_required"]) - set(schedule):
        return False
    # the reverse relation — every instant a stream claims must be an instant the episode actually acquired
    # for that stream, not only its endpoints, so a shortened or padded schedule cannot describe coverage it lacks
    acquired: dict = {}
    for row in acquisitions.values():
        acquired.setdefault(row["camera"], set()).add(row["stamp_s"])
    for name, instants in schedule.items():
        stamps = acquired.get(name)
        if stamps and any(all(abs(instant - stamp) > _TOLERANCE_S for stamp in stamps)
                          for instant in instants):
            return False

    def parts(entry):
        if isinstance(entry, dict):
            return entry.get("camera"), entry.get("stamp_s")
        return getattr(entry, "camera", None), getattr(entry, "stamp_s", None)

    held = {}
    for entry in acquisitions.values():
        camera, stamp = parts(entry)
        held.setdefault(camera, []).append(stamp)
    for stream, instants in schedule.items():
        observed = sorted(value for value in held.get(stream, []) if value is not None)
        if not all(any(abs(instant - stamp) <= _TOLERANCE_S for stamp in observed)
                   for instant in instants):
            # a scheduled instant no camera published is an invented schedule entry
            return False
        for earlier, later in zip(instants, instants[1:], strict=False):
            if later - earlier > window["cadence_s"] * 1.5 + _TOLERANCE_S and not any(
                    start - _TOLERANCE_S <= earlier and later <= end + _TOLERANCE_S
                    for start, end in window["permitted_gaps_s"]):
                # a gap beyond the cadence must be one the frozen inputs permit
                return False
    # the collection window is the episode's own claim about what it observed, so its endpoints must be
    # the observed extremes rather than numbers the caller chose; each stream's held stamps are that evidence
    observed_stamps = [value for values in held.values() for value in values if value is not None]
    if not observed_stamps:
        return False
    if (abs(window["collection_start_s"] - min(observed_stamps)) > _TOLERANCE_S
            or abs(window["collection_end_s"] - max(observed_stamps)) > _TOLERANCE_S):
        return False
    return True


def _audit_manifest_key(path: Path) -> tuple:
    from so101_demo.act.qc_session import tree_signature

    path = Path(path).absolute()
    return str(path), tree_signature(path.parent)


def _parse_audit_lines(path: Path) -> list:
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def _records(path: Path, fields: frozenset, code: str, *,
             optional: frozenset = frozenset(),
             optional_any: tuple = ()) -> list:
    try:
        rows = cached_lines(path, _parse_audit_lines)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(code) from error
    # F3: alternative groups are options too, so the base requirement must not demand them
    base = (fields - optional - frozenset().union(*optional_any)) if optional_any \
        else fields - optional
    for row in rows:
        if not isinstance(row, dict) or not base <= set(row) or not set(row) <= fields:
            raise ValueError(code)
        present = optional & set(row)
        if optional_any:
            # F3: exactly one complete group out of the alternatives, or none; a partial group and a
            # mixture of two are refused, so a partial history still cannot pass as complete
            carrying = [group for group in optional_any if group & set(row)]
            if len(carrying) > 1 or (carrying and not carrying[0] <= set(row)):
                raise ValueError(code)
        if present and present != optional:
            # an optional group is all-or-nothing, so a partial raw history cannot pass as complete
            raise ValueError(code)
    return rows


def _hex64(value) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(character in "0123456789abcdef" for character in value))


#: the prescribed lifecycle a formal audit must cover, in order. Declared here rather than imported from the
#: runner so the audit stays readable without it; `test_the_audit_names_the_runner_s_phases` asserts equality, so
#: the two cannot drift apart silently.
FORMAL_PHASES = (
    "SEARCH", "APPROACH", "CLOSE", "MICRO_LIFT", "TRANSPORT",
    "ALIGN", "RELEASE", "RADIAL_RETREAT", "FINAL_CHECK",
)


def _formal_coverage_ok(audit: Path) -> bool:
    """The coverage a formal seal requires, re-checked when the audit is read back."""

    def rows(name):
        return [json.loads(line) for line in (audit / name).read_text().splitlines()]

    try:
        physics, events, references = (rows("physics.jsonl"), rows("events.jsonl"),
                                       rows("references.jsonl"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    # F5: a formal seal must carry the prescribed lifecycle, not one phase's event, so every entry of
    # FORMAL_PHASES needs its own phase_complete beside the release and the accepted reference
    phases = {row["payload"].get("phase") for row in events if row["kind"] == "phase_complete"}
    # F5: a set cannot see order or repetition, so the completions must also run through the registered phases in
    # their registered order with strictly increasing physics steps, one completion per phase
    completions = [(row["payload"].get("phase"), row["payload"].get("physics_step"))
                   for row in events if row["kind"] == "phase_complete"]
    if (any(type(step) is not int for _, step in completions)
            or [phase for phase, _ in completions] != list(FORMAL_PHASES)
            # non-decreasing, because two phases may legitimately complete on the same step of one readback
            or any(later < earlier for (_, earlier), (_, later) in
                   zip(completions, completions[1:]))):
        return False
    # F5: "full registered physics" is every registered kind being present, which is checkable without a phase
    # field the rows do not carry
    kinds = {row["kind"] for row in physics}
    # F5: presence is not history, so each registered kind's rows must also advance in time - a kind whose rows
    # jump backwards, or that appears only once where the phase sequence needs several, is not the history the
    # phase completions above claim to summarise
    for kind in _PHYSICS_KINDS:
        times = [row["sim_time_s"] for row in physics if row["kind"] == kind]
        if (not times or any(type(value) not in (int, float) for value in times)
                or any(later < earlier for earlier, later in zip(times, times[1:]))):
            return False
    # F5: the ratified observations must actually be retained, so at least one physics row carries both records
    # F5: the physics stream and the event stream had never been related, so the epochs the physics rows declare
    # must never decrease and every one of them must be an epoch a release event actually named
    named_epochs = {row["payload"].get("release_epoch") for row in events if row["kind"] == "release"}
    epochs = [row["release_epoch"] for row in physics]
    # F5 (eighth verdict): the episode's own declared initial epoch is exempt from transition naming — only the
    # epochs a release actually entered must be named — while the sequence itself never goes backwards
    # the declared initial epoch lives in the manifest once sealed, but at SEAL time that
    # file does not exist yet and the episode's own identity is what states it - so read whichever is present, or
    # every positive epoch looks unnamed and a real run cannot be sealed at all
    initial = None
    for name in ("audit-manifest.json", "episode.json"):
        try:
            document = json.loads((audit / name).read_bytes())
            # the manifest nests its identity under "identity"; episode.json IS the identity, so both shapes count
            initial = (document.get("identity") or document).get("release_epoch")
            if type(initial) is int:
                break
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, AttributeError):
            continue
    if type(initial) is not int:
        initial = 0
    if type(initial) is not int:
        initial = 0
    if (any(type(epoch) is not int or (epoch > initial and epoch not in named_epochs) for epoch in epochs)
            or any(later < earlier for earlier, later in zip(epochs, epochs[1:]))):
        return False
    observed = any(isinstance(row.get("observation"), dict)
                   and "planning_scene_observation" in row["observation"]
                   and "controller_feedback" in row["observation"] for row in physics)
    return bool(physics and events and references
                # F5: not merely that a reference was accepted, but that it carries one complete raw group -
                # the legacy flat keys or the packed frames - so a bare projected reference is not coverage
                and any(row["accepted"] is True
                        and (_REFERENCE_RAW_FIELDS <= set(row) or _REFERENCE_FRAME_FIELDS <= set(row))
                        for row in references)
                and any(row["kind"] == "release" for row in events)
                and all(phase in phases for phase in FORMAL_PHASES)
                and all(kind in kinds for kind in _PHYSICS_KINDS)
                and observed)
