"""The common raw audit for one episode.

One writer owns the episode's raw evidence: the acquisitions the cameras actually produced, the
controller references the run actually accepted or revoked, the physics observations the run actually
made, the run events, and the binding of each training row to the acquisitions and reference sequence
it consumed. The recorder writes its rows through the same boundary, so a row cannot exist without its
raw binding, and nothing may rewrite the audit after it is sealed.

Every append is a new line; there is no update path. Each source kind has a closed schema, so an
unknown field is refused rather than silently retained, and `seal()` writes the manifest of the raw
audit last, fsyncing every file and the directory before returning. `verify_audit_manifest()` re-reads
the files and recomputes their digests, so a rewritten reference or a missing binding is detected
instead of trusted.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path

from .acquisition import CAMERAS, canonical_acquisition_id
from ..parallel_batch.contracts import ContractError, LeaseIdentity

MANIFEST_KIND = "ACT_EPISODE_AUDIT"
_METADATA_FILES = ("source.json", "inputs.json", "episode.json")
# the ratified collection-window contract (Proposal B): every field, with per-outcome ordering
_WINDOW_FIELDS = frozenset({"source_schedule", "streams_required", "cadence_s", "permitted_gaps_s",
                            "collection_start_s", "collection_end_s", "first_command_s",
                            "physics_end_s", "label_cutoff_s", "outcome"})
_WINDOW_OUTCOMES = ("complete", "no_command", "no_label", "interrupted_diagnostic")
# the frozen collection-scope contract, field for field
_SCOPE_FIELDS = frozenset({"kind", "schema_version", "mode", "scene_id", "seed", "inputs_sha256"})
_SCOPE_MODES = ("formal", "preselected_target_diagnostic")
# the plan names session/reset/release as part of the identity; the rest of the lease document is
# recorded verbatim because the plan does not fix its key names here
_IDENTITY_REQUIRED = ("session_id", "attempt_id", "reset_epoch", "release_epoch")
# the registered lease contract, reused rather than re-specified: a formal episode must name the lease
# it ran under, and its attempt must be the episode's attempt
_LEASE_FIELDS = frozenset({"batch_id", "coordinator_epoch", "worker_id", "worker_generation",
                           "point_id", "attempt_id", "lease_generation",
                           "lease_issued_monotonic_s", "lease_deadline_monotonic_s"})
_STREAM_NAMES = ("acquisitions.jsonl", "row-bindings.jsonl", "events.jsonl",
                 "references.jsonl", "physics.jsonl")
SOURCE_KINDS = ("events", "references", "physics")
_ACQUISITION_FIELDS = frozenset({"camera", "session_id", "reset_epoch", "sequence", "acquisition_id",
                                 "stamp_s", "received_monotonic_ns", "shape", "dtype", "pixel_sha256"})
_ROW_FIELDS = frozenset({"row_index", "sim_time_s", "head_acquisition_id",
                         "wrist_acquisition_id", "reference_sequence"})
_REFERENCE_FIELDS = frozenset({"sequence", "reference_time_s", "source", "positions", "accepted"})
# the observer's raw frame fields (adapters/act/controller_reference_observer.py): either a reference
# record preserves all of them or none, so a partial raw history can never look complete
_REFERENCE_RAW_FIELDS = frozenset({"joint_names", "sim_stamp_ns", "received_monotonic_ns",
                                   "velocities"})
# the ratified Proposal A shape: one frame per controller kind plus the evaluation that produced the
# projected action, all-or-nothing like the legacy group
_REFERENCE_FRAME_FIELDS = frozenset({"frames", "projected_positions", "projection_map"})
_FRAME_KINDS = ("arm", "gripper")
# the ratified source has five ordered arm joints and one gripper joint
_FRAME_SIZES = {"arm": 5, "gripper": 1}
# ratified amendment A.1: the immutable publication lives beside the value evaluated for the
# record's target instant, and the projection map selects the evaluated value
_FRAME_FIELDS = frozenset({"joint_names", "published_positions", "published_velocities",
                           "evaluated_positions", "evaluated_velocities", "evaluation",
                           "sim_stamp_ns", "received_monotonic_ns", "observer_sequence"})
_EVALUATION_FIELDS = frozenset({"requested_sim_time_s", "basis", "goal_id", "accepted_sim_s",
                                "revoked_sim_s"})
_EVALUATION_BASES = ("published", "interval")
_EVENT_FIELDS = frozenset({"sequence", "kind", "identity", "sim_time_s", "monotonic_ns",
                           "payload"})
# the frozen contract delegates the per-kind payload schema here; each entry is the exact key set a
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
}
_EVENT_STRINGS = {"phase": "phase", "reason": "reason", "owner": "dispatch", "permit_id": "accept"}
_EVENT_FLAGS = {"stopped_confirmed", "table_contact", "supported", "no_fingertip_contact",
                "placement_stable", "retreat_stable"}
_EVENT_COUNTS = {"left_contacts", "right_contacts"}
_PHYSICS_FIELDS = frozenset({"sequence", "kind", "sim_time_s", "release_epoch", "observation"})
_PHYSICS_KINDS = ("support", "contact", "pose", "retract")
# the MuJoCo source contract for a physics observation, taken from what the backend already publishes
# (backends/mujoco/qualified_phases/release_retreat.py::evidence_dict) plus the verified support boolean
# the runner adds for support rows; another source would extend this set when it exists
_PHYSICS_OBSERVATION_FIELDS = frozenset({
    # the registered live sample (act/contact_live.py) carries the real source records
    "simulation_session_id", "model_qpos", "model_qvel", "cup_position_m", "cup_velocity_m_s",
    "left_contacts", "right_contacts", "other_contacts", "truncated",
    "diagnostic_hazard_breached",
    # the MuJoCo summary fields stay admissible for sources that only publish them
    "publisher_sequence", "simulation_time_s", "simulation_step", "reset_epoch", "paused",
    "cup_position_world_m", "cup_orientation_world_xyzw",
    "cup_linear_velocity_world_m_s", "cup_angular_velocity_world_rad_s", "left_contact_count",
    "right_contact_count", "table_contact", "other_contact_geoms", "maximum_normal_force_n",
    "supported",
    # the two records the owner ratified defining (Proposal C): what the readback observed, so the
    # gate booleans can be derived instead of asserted
    "planning_scene_observation", "controller_feedback"})
_SCENE_OBSERVATION_FIELDS = frozenset({"scene_revision", "attached_objects", "world_object_ids",
                                       "is_diff", "sim_time_s", "source"})
_FEEDBACK_FIELDS = frozenset({"controller", "commanded_positions", "measured_positions",
                              "measured_velocities", "joint_names", "status_sequence", "sim_time_s"})
_FEEDBACK_CONTROLLERS = ("arm", "gripper")
# one contact record, closed exactly as the registered contract defines it
_CONTACT_FIELDS = frozenset({"robot_geom", "object_body", "normal_force_n", "signed_distance_m"})
_CONTACT_LISTS = ("left_contacts", "right_contacts", "other_contacts")
# each kind must carry the measurements its verdict is made of, not merely a timestamp
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
_PHYSICS_INTEGERS = {"simulation_step", "left_contact_count", "right_contact_count",
                     "publisher_sequence", "reset_epoch"}
_PHYSICS_BOOLEANS = {"table_contact", "supported", "paused"}
# each vector keeps its source dimension: a position and a velocity are 3, a quaternion is 4
_PHYSICS_VECTORS = {"cup_position_world_m": 3, "cup_orientation_world_xyzw": 4,
                    "cup_linear_velocity_world_m_s": 3, "cup_angular_velocity_world_rad_s": 3}
_PHYSICS_STRINGS = {"other_contact_geoms"}
_PHYSICS_VECTOR_LISTS = {"model_qpos", "model_qvel", "cup_position_m", "cup_velocity_m_s"}
# the frozen source contract: rows sit on the 10 Hz grid, a frame is at most one grid step old and
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
            or any(not isinstance(name, str) or not name for name in names)):
        return False
    for key in ("commanded_positions", "measured_positions", "measured_velocities"):
        if not _finite_vector(record[key], length=len(names)):
            return False
    if type(record["status_sequence"]) is not int or record["status_sequence"] < 1:
        return False
    return (not isinstance(record["sim_time_s"], bool)
            and isinstance(record["sim_time_s"], (int, float))
            and math.isfinite(record["sim_time_s"]) and record["sim_time_s"] >= 0)


def _reference_frames_ok(record, *, history: dict | None = None) -> None:
    """Validate the ratified per-frame raw history and its evaluation, or refuse."""

    frames = record["frames"]
    if not isinstance(frames, dict) or set(frames) != set(_FRAME_KINDS):
        raise ValueError("AUDIT_SCHEMA_INVALID")
    for kind, frame in frames.items():
        if not isinstance(frame, dict) or set(frame) != _FRAME_FIELDS:
            raise ValueError("AUDIT_SCHEMA_INVALID")
        names = frame["joint_names"]
        if (not isinstance(names, list) or len(names) != _FRAME_SIZES[kind]
                or any(not isinstance(name, str) or not name for name in names)):
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
        if (pair[0], pair[1]) in seen:
            # six dimensions of one action cannot reuse the same source dimension twice
            raise ValueError("AUDIT_SCHEMA_INVALID")
        seen.add((pair[0], pair[1]))
        if (not isinstance(pair, list) or len(pair) != 2 or pair[0] not in _FRAME_KINDS
                or type(pair[1]) is not int):
            raise ValueError("AUDIT_SCHEMA_INVALID")
        # A.1 ratified: the map selects the evaluated value, the publication stays untouched
        source = frames[pair[0]]["evaluated_positions"]
        if pair[1] < 0 or pair[1] >= len(source):
            raise ValueError("AUDIT_SCHEMA_INVALID")
        if source[pair[1]] != projected[index]:
            # the six-dimensional action must be exactly the mapped source values
            raise ValueError("AUDIT_SCHEMA_INVALID")
    if list(record["positions"]) != list(projected):
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
        if not (_PHYSICS_REQUIRED_REGISTERED[kind] | {"simulation_time_s", "simulation_step"}
                <= set(observation)):
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
                           for entry in value)):
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
        # F3: the first event of an episode names the run's own initial release epoch, never an unrelated one;
        # whether a later step is tied to a release event is a property of the stream, checked when it is sealed
        return epoch in (0, 1)
    if epoch < release_epoch or epoch > release_epoch + 1:
        # the release epoch never goes backwards and advances one release at a time
        return False
    return True


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
        elif key in _EVENT_STRINGS:
            if not isinstance(value, str) or not value:
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
                   or any(not _number(instant) for instant in instants)
                   or instants != sorted(instants)
                   for name, instants in schedule.items())):
        # a schedule is a chronological list per stream, not a set in arbitrary order
        return False
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
    if any(not start - _TOLERANCE_S <= gap[0] and gap[1] <= end + _TOLERANCE_S
           for gap in window["permitted_gaps_s"]):
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


class EpisodeAuditWriter:
    """The single writer of one episode's raw audit."""

    def __init__(self, root: Path, scope: dict, identity: dict, inputs: dict) -> None:
        self.root = Path(root)
        if (not self.root.is_absolute() or ".." in self.root.parts
                or not isinstance(scope, dict) or not isinstance(identity, dict)
                or not isinstance(inputs, dict)):
            raise ValueError("AUDIT_ROOT_INVALID")
        digest = inputs.get("inputs_sha256") if isinstance(inputs, dict) else None
        if not _scope_ok(scope):
            # a scope the frozen contract does not recognise may not open an episode audit
            raise ValueError("AUDIT_SCOPE_INVALID")
        if not _identity_ok(identity, formal=scope["mode"] == "formal"):
            # a formal episode must name the lease it ran under, using the registered contract
            raise ValueError("AUDIT_IDENTITY_INVALID")
        if not inputs:
            raise ValueError("AUDIT_SCOPE_INVALID")
        if not _hex64(digest):
            # the audit always names the frozen inputs it belongs to
            raise ValueError("AUDIT_INPUTS_INVALID")
        self.root.mkdir(parents=False, exist_ok=False)
        audit = self.root / "audit"
        audit.mkdir()
        self.files = _Files(audit / "source.json", audit / "inputs.json", audit / "episode.json",
                            audit / "acquisitions.jsonl", audit / "row-bindings.jsonl",
                            audit / "events.jsonl", audit / "references.jsonl",
                            audit / "physics.jsonl")
        self.scope = dict(scope)
        self.identity = dict(identity)
        self.inputs = dict(inputs)
        self._write_new(self.files.source, _canonical(self.scope))
        self._write_new(self.files.inputs, _canonical(self.inputs))
        self._write_new(self.files.episode, _canonical(self.identity))
        self._streams = {name: self._open(path) for name, path in self.files.streams().items()}
        self._sequence = {name: 0 for name in self._streams}
        self._acquisitions: dict = {}
        self._references: dict = {}
        self._bound: set = set()
        self._last_row_time_s: float | None = None
        self._bound_references: set = set()
        self._revoked_targets: set = set()
        self._event_release_epoch: int | None = None
        self._event_kinds: set = set()
        # F3: which release epochs a `release` event actually named, so seal() can require that every step the
        # stream takes is named by one rather than only that some release happened somewhere
        self._release_named: dict = {}
        self._reference_history: dict = {}
        self._row_indexes: set = set()
        self._row_times: list = []
        self._release_epoch: int | None = None
        self._observed_epochs: dict = {}
        self._sealed: Path | None = None

    # -- the only writer ---------------------------------------------------

    def append_acquisition(self, frame) -> None:
        self._require_open()
        record = {field: getattr(frame, field) for field in _ACQUISITION_FIELDS}
        record["shape"] = list(record["shape"])
        _closed(record, _ACQUISITION_FIELDS, "AUDIT_SCHEMA_INVALID")
        if record["acquisition_id"] in self._acquisitions:
            raise ValueError("AUDIT_ACQUISITION_DUPLICATE")
        self._acquisitions[record["acquisition_id"]] = record
        self._append("acquisitions", record)

    def bind_row(self, row_index, sim_time_s, head_id, wrist_id, reference_sequence) -> None:
        self._require_open()
        record = {"row_index": _integer(row_index, "AUDIT_ROW_INVALID"),
                  "sim_time_s": _finite(sim_time_s, "AUDIT_ROW_INVALID", nonnegative=True),
                  "head_acquisition_id": head_id, "wrist_acquisition_id": wrist_id,
                  "reference_sequence": _integer(reference_sequence, "AUDIT_ROW_INVALID")}
        _closed(record, _ROW_FIELDS, "AUDIT_ROW_INVALID")
        if head_id == wrist_id:
            # the same acquisition in both slots is never a real stereo pair
            raise ValueError("AUDIT_BINDING_INVALID")
        for value, camera in ((head_id, "head"), (wrist_id, "wrist")):
            if not isinstance(value, str) or not value or value not in self._acquisitions:
                # a row may not be bound to an acquisition the audit never saw
                raise ValueError("AUDIT_BINDING_UNKNOWN")
            frame = self._acquisitions[value]
            if frame["camera"] != camera:
                # the head slot takes a head acquisition and the wrist slot a wrist one
                raise ValueError("AUDIT_BINDING_INVALID")
            if (frame["session_id"] != self.identity.get("session_id")
                    or frame["reset_epoch"] != self.identity.get("reset_epoch")):
                # a frame from another session or reset epoch does not belong to this episode
                raise ValueError("AUDIT_BINDING_INVALID")
            if value in self._bound:
                # one acquisition fills one row, the same rule the capture enforces
                raise ValueError("AUDIT_BINDING_REUSED")
        if record["row_index"] in self._row_indexes:
            raise ValueError("AUDIT_ROW_INVALID")
        if record["row_index"] != len(self._row_indexes):
            # rows are a contiguous schedule: no gaps, no reordering
            raise ValueError("AUDIT_ROW_ORDER_INVALID")
        stamps = []
        for value in (head_id, wrist_id):
            frame = self._acquisitions[value]
            age = record["sim_time_s"] - frame["stamp_s"]
            if age < -_TOLERANCE_S or age > _MAX_SOURCE_AGE_S + _TOLERANCE_S:
                # a frame from the future, or one too old, is not causal for this instant
                raise ValueError("AUDIT_BINDING_CAUSALITY_INVALID")
            stamps.append(frame["stamp_s"])
        if abs(stamps[0] - stamps[1]) > _MAX_SKEW_S + _TOLERANCE_S:
            raise ValueError("AUDIT_BINDING_CAUSALITY_INVALID")
        if self._last_row_time_s is not None and abs(
                record["sim_time_s"] - (self._last_row_time_s + _GRID_S)) > _TOLERANCE_S:
            # rows are a contiguous 10 Hz schedule, not merely consecutive integers
            raise ValueError("AUDIT_ROW_SCHEDULE_INVALID")
        entry = self._references.get(record["reference_sequence"])
        target = round(record["sim_time_s"] + _GRID_S, 6)
        if (entry is None or entry["reference_time_s"] != target
                or entry["accepted"] is not True
                or entry["reference_time_s"] in self._revoked_targets):
            # the binding must name a reference this episode accepted for exactly that instant and
            # whose acceptance still stands
            raise ValueError("AUDIT_BINDING_REFERENCE_INVALID")
        self._row_indexes.add(record["row_index"])
        self._row_times.append(record["sim_time_s"])
        self._last_row_time_s = record["sim_time_s"]
        self._bound.update((head_id, wrist_id))
        self._bound_references.add(record["reference_sequence"])
        self._append("row-bindings", record)

    def append_source(self, kind, record) -> None:
        self._require_open()
        if kind not in SOURCE_KINDS:
            raise ValueError("AUDIT_SOURCE_KIND_INVALID")
        if kind == "events":
            item = _closed(record, _EVENT_FIELDS - {"sequence"}, "AUDIT_SCHEMA_INVALID").copy()
            if (not isinstance(item["kind"], str) or item["kind"] not in _EVENT_PAYLOADS
                    or not isinstance(item["identity"], dict) or not item["identity"]
                    or not _event_identity_ok(item["identity"], self.identity,
                                              release_epoch=self._event_release_epoch)
                    or not isinstance(item["payload"], dict)
                    or set(item["payload"]) != _EVENT_PAYLOADS[item["kind"]]):
                # an unknown kind, an empty identity or a payload outside its kind's schema is refused
                raise ValueError("AUDIT_SCHEMA_INVALID")
            _integer(item["monotonic_ns"], "AUDIT_SCHEMA_INVALID", minimum=1)
            # a sim time is recorded only when the source actually supplies one, never invented
            if item["sim_time_s"] is not None:
                _finite(item["sim_time_s"], "AUDIT_SCHEMA_INVALID", nonnegative=True)
            if item["kind"] in ("run_complete", "run_aborted"):
                _integer(item["payload"]["physics_step"], "AUDIT_SCHEMA_INVALID")
            if not _payload_typed(item["payload"]):
                # every value must be the type its key declares, per kind
                raise ValueError("AUDIT_SCHEMA_INVALID")
            if item["kind"] == "phase_complete":
                _integer(item["payload"]["physics_step"], "AUDIT_SCHEMA_INVALID")
                if not isinstance(item["payload"]["phase"], str) or not item["payload"]["phase"]:
                    raise ValueError("AUDIT_SCHEMA_INVALID")
            if item["kind"] == "release":
                if item["payload"]["release_epoch"] != item["identity"]["release_epoch"]:
                    raise ValueError("AUDIT_SCHEMA_INVALID")
            self._event_release_epoch = item["identity"]["release_epoch"]
            self._event_kinds.add(item["kind"])
            _epoch = item["identity"].get("release_epoch")
            if type(_epoch) is int:
                self._release_named[_epoch] = (self._release_named.get(_epoch, False)
                                               or item["kind"] == "release")
            item["sequence"] = self._next("events")
        elif kind == "references":
            keys = set(record) if isinstance(record, dict) else set()
            packed = _REFERENCE_FRAME_FIELDS & keys
            raw_present = _REFERENCE_RAW_FIELDS & keys
            if packed and packed != _REFERENCE_FRAME_FIELDS:
                raise ValueError("AUDIT_SCHEMA_INVALID")
            if packed and raw_present:
                # the ratified per-frame shape and the legacy flat group are alternatives
                raise ValueError("AUDIT_SCHEMA_INVALID")
            if raw_present and raw_present != _REFERENCE_RAW_FIELDS:
                raise ValueError("AUDIT_SCHEMA_INVALID")
            if packed:
                _reference_frames_ok(record, history=self._reference_history)
            elif raw_present:
                _reference_raw_ok(record, "AUDIT_SCHEMA_INVALID")
            item = _closed(record, (_REFERENCE_FIELDS | packed | raw_present) - {"sequence"},
                           "AUDIT_SCHEMA_INVALID").copy()
            _finite(item["reference_time_s"], "AUDIT_SCHEMA_INVALID", nonnegative=True)
            positions = item["positions"]
            if (not isinstance(positions, (list, tuple)) or len(positions) != 6
                    or any(isinstance(value, bool) or not isinstance(value, (int, float))
                           or not math.isfinite(value) for value in positions)):
                raise ValueError("AUDIT_SCHEMA_INVALID")
            item["positions"] = [float(value) for value in positions]
            if item["source"] != "CONTROLLER_REFERENCE" or type(item["accepted"]) is not bool:
                raise ValueError("AUDIT_SCHEMA_INVALID")
            item["sequence"] = self._next("references")
            # the recorded row keeps the declared closed fields; the revocation state lives beside it
            self._references[item["sequence"]] = item
            if item["accepted"] is not True:
                # a revocation voids the acceptance for that target instant, so no row may keep
                # binding an acceptance the controller has since withdrawn
                self._revoked_targets.add(item["reference_time_s"])
        else:
            item = _closed(record, _PHYSICS_FIELDS - {"sequence"}, "AUDIT_SCHEMA_INVALID").copy()
            if item["kind"] not in _PHYSICS_KINDS or not isinstance(item["observation"], dict):
                raise ValueError("AUDIT_SCHEMA_INVALID")
            _finite(item["sim_time_s"], "AUDIT_SCHEMA_INVALID", nonnegative=True)
            epoch = _integer(item["release_epoch"], "AUDIT_SCHEMA_INVALID")
            item["sim_time_s"] = _finite(item["sim_time_s"], "AUDIT_SCHEMA_INVALID",
                                         nonnegative=True)
            if not _physics_observation_typed(item["observation"], kind=item["kind"]):
                raise ValueError("AUDIT_SCHEMA_INVALID")
            if item["observation"]["simulation_time_s"] != item["sim_time_s"]:
                raise ValueError("AUDIT_SCHEMA_INVALID")
            self._apply_epoch(epoch, item["kind"], item["observation"])
            item["sequence"] = self._next("physics")
        self._append(kind, item)

    def seal(self, window: dict) -> Path:
        self._require_open()
        if self.scope.get("mode") == "formal":
            # a formal episode must actually carry the raw source coverage it claims; until the
            # producers exist this refuses rather than sealing an empty audit
            if (not self._sequence["physics"] or not self._sequence["references"]
                    or not self._sequence["events"] or not self._references
                    or "release" not in self._event_kinds
                    # F3: every release step the stream takes must be named by a release event, not just one
                    or any(epoch > 0 and not named for epoch, named in self._release_named.items())):
                raise ValueError("AUDIT_FORMAL_COVERAGE_INCOMPLETE")
        for sequence in sorted(self._bound_references):
            entry = self._references.get(sequence)
            if (entry is None or entry["accepted"] is not True
                    or entry["reference_time_s"] in self._revoked_targets):
                # an already-bound row whose acceptance was revoked before sealing cannot be sealed
                raise ValueError("AUDIT_BINDING_REVOKED")
        if not isinstance(window, dict) or not window:
            raise ValueError("AUDIT_WINDOW_INVALID")
        if (self.scope.get("mode") == "formal" or set(window) == _WINDOW_FIELDS) and not _window_ok(
                window, mode=self.scope.get("mode")):
            # a formal audit states the ratified window; a diagnostic audit may record a legacy one
            raise ValueError("AUDIT_WINDOW_INVALID")
        if self.scope.get("mode") == "formal" and not self._window_matches_rows(window):
            # T3-F11: and it must describe the rows and acquisitions this audit actually holds
            raise ValueError("AUDIT_WINDOW_INVALID")
        for name, stream in self._streams.items():
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
        files = {}
        for target in (*self.files.streams().values(), self.files.source, self.files.inputs,
                       self.files.episode):
            files[target.name] = {"path": target.name, "size": target.stat().st_size,
                                  "sha256": _sha256(target)}
        manifest = {"kind": MANIFEST_KIND, "schema_version": 2,
                    # the digest of the scope payload this audit was collected under
                    "scope_sha256": _sha256(self.files.source),
                    "identity": dict(self.identity), "window": dict(window), "files": files}
        target = self.root / "audit" / "audit-manifest.json"
        self._write_new(target, _canonical(manifest))
        self._fsync_dir(target.parent)
        self._sealed = target
        return target

    # -- helpers -----------------------------------------------------------

    def _window_matches_rows(self, window: dict) -> bool:
        """T3-F11: a formal window must describe the rows and acquisitions this audit actually holds."""

        if window["outcome"] == "complete":
            if not self._row_times or abs(window["label_cutoff_s"] - max(self._row_times)) > _TOLERANCE_S:
                # the cutoff is the last labelled observation, not a number chosen to fit
                return False
        elif self._row_times:
            # an outcome other than complete may not accompany labelled rows
            return False
        schedule = window["source_schedule"]
        if set(window["streams_required"]) - set(schedule):
            return False

        def parts(entry):
            if isinstance(entry, dict):
                return entry.get("camera"), entry.get("stamp_s")
            return getattr(entry, "camera", None), getattr(entry, "stamp_s", None)

        held = {}
        for entry in self._acquisitions.values():
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
        return True

    def _apply_epoch(self, epoch: int, kind: str, observation: dict) -> None:
        if self._release_epoch is None:
            self._release_epoch = epoch
        elif epoch < self._release_epoch:
            raise ValueError("AUDIT_RELEASE_EPOCH_STALE")
        elif epoch > self._release_epoch:
            self._release_epoch = epoch
        if kind == "support":
            supported = observation.get("supported")
            if type(supported) is not bool:
                raise ValueError("AUDIT_SCHEMA_INVALID")
            self._observed_epochs[epoch] = supported

    def _next(self, kind: str) -> int:
        self._sequence[kind] += 1
        return self._sequence[kind]

    def _require_open(self) -> None:
        if self._sealed is not None:
            raise ValueError("AUDIT_ALREADY_SEALED")

    def _append(self, name: str, record: dict) -> None:
        stream = self._streams[name]
        stream.write(_canonical(record) + b"\n")
        stream.flush()

    def _open(self, path: Path):
        return path.open("xb")

    def _write_new(self, path: Path, payload: bytes) -> None:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

    def _fsync_dir(self, directory: Path) -> None:
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def verify_audit_manifest(path: Path) -> dict:
    """Re-read a sealed audit and recompute it.

    The inventory is **required**, not trusted: every expected stream and metadata file must be listed
    with a safe relative path, its size and its digest, so a manifest that omits a stream cannot leave
    that stream unchecked. Each stream is then re-validated semantically with the same closed schemas
    and relationships the writer enforced, because a checksum only proves the bytes did not change.
    """

    path = Path(path)
    try:
        manifest = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("AUDIT_MANIFEST_INVALID") from error
    if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_FIELDS:
        raise ValueError("AUDIT_MANIFEST_INVALID")
    if manifest["kind"] != MANIFEST_KIND or manifest["schema_version"] != 2:
        raise ValueError("AUDIT_MANIFEST_INVALID")
    audit = path.parent
    expected = set(_METADATA_FILES) | set(_STREAM_NAMES)
    files = manifest["files"]
    if not isinstance(files, dict) or set(files) != expected:
        # an inventory that omits a stream, or invents one, is refused rather than partially checked
        raise ValueError("AUDIT_MANIFEST_INVENTORY_INVALID")
    for name, entry in files.items():
        target = audit / name
        if (not isinstance(entry, dict) or set(entry) != {"path", "size", "sha256"}
                or entry["path"] != name or not target.is_file() or target.is_symlink()):
            raise ValueError("AUDIT_MANIFEST_INVENTORY_INVALID")
        payload = target.read_bytes()
        if len(payload) != entry["size"] or _sha256(target) != entry["sha256"]:
            # a changed raw reference, a rewritten stream or a deleted file lands here
            raise ValueError("AUDIT_HASH_MISMATCH")
    formal_window = json.loads((audit / "source.json").read_bytes()).get("mode") == "formal"
    if (not isinstance(manifest["identity"], dict) or not isinstance(manifest["window"], dict)
            or (formal_window and not _window_ok(manifest["window"], mode="formal"))
            or manifest["scope_sha256"] != _sha256(audit / "source.json")):
        # the manifest names the scope it was collected under, and the payload must agree with it
        raise ValueError("AUDIT_MANIFEST_INVALID")
    _verify_streams(audit, manifest["identity"])
    if formal_window and not _formal_coverage_ok(audit):
        # the seal gate's coverage requirement holds when the audit is read back, not only when sealed
        raise ValueError("AUDIT_FORMAL_COVERAGE_INCOMPLETE")
    return manifest


def _records(path: Path, fields: frozenset, code: str, *,
             optional: frozenset = frozenset(),
             optional_any: tuple = ()) -> list:
    try:
        rows = [json.loads(line) for line in path.read_text().splitlines()]
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


def _formal_coverage_ok(audit: Path) -> bool:
    """The coverage a formal seal requires, re-checked when the audit is read back."""

    def rows(name):
        return [json.loads(line) for line in (audit / name).read_text().splitlines()]

    try:
        physics, events, references = (rows("physics.jsonl"), rows("events.jsonl"),
                                       rows("references.jsonl"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return bool(physics and events and references
                and any(row["accepted"] is True for row in references)
                and any(row["kind"] == "release" for row in events))


def _verify_streams(audit: Path, identity: dict) -> None:
    """Re-apply admission semantics to every stream, not just its checksum."""

    acquisitions = {}
    per_camera: dict = {}
    for row in _records(audit / "acquisitions.jsonl", _ACQUISITION_FIELDS,
                        "AUDIT_ACQUISITION_INVALID"):
        if (row["camera"] not in CAMERAS or list(row["shape"]) != [480, 640, 3]
                or row["dtype"] != "uint8" or not _hex64(row["pixel_sha256"])
                or type(row["sequence"]) is not int or row["sequence"] < 1
                or type(row["reset_epoch"]) is not int or row["reset_epoch"] < 0
                or type(row["received_monotonic_ns"]) is not int or row["received_monotonic_ns"] < 1
                or not isinstance(row["stamp_s"], (int, float)) or isinstance(row["stamp_s"], bool)
                or not math.isfinite(row["stamp_s"]) or row["stamp_s"] < 0
                or not math.isfinite(row["received_monotonic_ns"])):
            raise ValueError("AUDIT_ACQUISITION_INVALID")
        if row["acquisition_id"] != canonical_acquisition_id(
                row["session_id"], row["reset_epoch"], row["camera"], row["sequence"]):
            raise ValueError("AUDIT_ACQUISITION_INVALID")
        key = (row["camera"], row["session_id"], row["reset_epoch"])
        previous_sequence, previous_stamp = per_camera.get(key, (0, -1.0))
        if (row["acquisition_id"] in acquisitions or row["sequence"] <= previous_sequence
                or row["stamp_s"] <= previous_stamp):
            # a new sequence must also be a new source instant: ordering alone is not monotonic time
            raise ValueError("AUDIT_ACQUISITION_INVALID")
        per_camera[key] = (row["sequence"], row["stamp_s"])
        acquisitions[row["acquisition_id"]] = row
    revoked = set()
    references = {}
    sequence = 0
    frame_history: dict = {}
    for row in _records(audit / "references.jsonl",
                        _REFERENCE_FIELDS | _REFERENCE_RAW_FIELDS | _REFERENCE_FRAME_FIELDS,
                        "AUDIT_REFERENCE_INVALID",
                        optional_any=(_REFERENCE_RAW_FIELDS, _REFERENCE_FRAME_FIELDS)):
        if (type(row["sequence"]) is not int or row["sequence"] != sequence + 1
                or row["source"] != "CONTROLLER_REFERENCE"
                or type(row["accepted"]) is not bool
                or not isinstance(row["positions"], list) or len(row["positions"]) != 6
                or not isinstance(row["reference_time_s"], (int, float))
                or isinstance(row["reference_time_s"], bool)
                or not math.isfinite(row["reference_time_s"]) or row["reference_time_s"] < 0
                or any(isinstance(value, bool) or not isinstance(value, (int, float))
                       or not math.isfinite(value) for value in row["positions"])):
            raise ValueError("AUDIT_REFERENCE_INVALID")
        sequence = row["sequence"]
        packed_keys = _REFERENCE_FRAME_FIELDS & set(row)
        raw_keys = _REFERENCE_RAW_FIELDS & set(row)
        if packed_keys and raw_keys:
            # the two groups are alternatives at admission, so readback refuses them together too
            raise ValueError("AUDIT_REFERENCE_INVALID")
        if packed_keys:
            _reference_frames_ok(row, history=frame_history)
        elif raw_keys:
            _reference_raw_ok(row, "AUDIT_REFERENCE_INVALID")
        references[row["sequence"]] = row
        if row["accepted"] is not True:
            revoked.add(row["reference_time_s"])
    bound: set = set()
    indexes: set = set()
    last_time: float | None = None
    for row in _records(audit / "row-bindings.jsonl", _ROW_FIELDS, "AUDIT_ROW_INVALID"):
        if (type(row["row_index"]) is not int or row["row_index"] < 0
                or row["row_index"] in indexes or row["row_index"] != len(indexes)
                or row["head_acquisition_id"] == row["wrist_acquisition_id"]
                or not isinstance(row["sim_time_s"], (int, float))
                or isinstance(row["sim_time_s"], bool)
                or not math.isfinite(row["sim_time_s"]) or row["sim_time_s"] < 0):
            raise ValueError("AUDIT_ROW_INVALID")
        indexes.add(row["row_index"])
        stamps = []
        for value, camera in ((row["head_acquisition_id"], "head"),
                              (row["wrist_acquisition_id"], "wrist")):
            frame = acquisitions.get(value)
            if frame is None or value in bound or frame["camera"] != camera:
                raise ValueError("AUDIT_BINDING_UNKNOWN")
            if (frame["session_id"] != identity.get("session_id")
                    or frame["reset_epoch"] != identity.get("reset_epoch")):
                raise ValueError("AUDIT_BINDING_INVALID")
            age = row["sim_time_s"] - frame["stamp_s"]
            if age < -_TOLERANCE_S or age > _MAX_SOURCE_AGE_S + _TOLERANCE_S:
                raise ValueError("AUDIT_BINDING_CAUSALITY_INVALID")
            stamps.append(frame["stamp_s"])
            bound.add(value)
        if abs(stamps[0] - stamps[1]) > _MAX_SKEW_S + _TOLERANCE_S:
            raise ValueError("AUDIT_BINDING_CAUSALITY_INVALID")
        if last_time is not None and abs(row["sim_time_s"] - (last_time + _GRID_S)) > _TOLERANCE_S:
            raise ValueError("AUDIT_ROW_SCHEDULE_INVALID")
        last_time = row["sim_time_s"]
        target = round(row["sim_time_s"] + _GRID_S, 6)
        named = references.get(row["reference_sequence"])
        if named is None or named["reference_time_s"] != target or named["accepted"] is not True:
            # the binding must resolve to a reference this episode accepted for exactly that instant
            raise ValueError("AUDIT_BINDING_REFERENCE_INVALID")
        if target in revoked:
            raise ValueError("AUDIT_BINDING_REVOKED")
    sequence = 0
    event_epoch: int | None = None
    for row in _records(audit / "events.jsonl", _EVENT_FIELDS, "AUDIT_EVENT_INVALID"):
        payload = row["payload"]
        if (type(row["sequence"]) is not int or row["sequence"] != sequence + 1
                or row["kind"] not in _EVENT_PAYLOADS
                or not isinstance(row["identity"], dict) or not row["identity"]
                or type(row["monotonic_ns"]) is not int or row["monotonic_ns"] < 1
                or not isinstance(payload, dict)
                or set(payload) != _EVENT_PAYLOADS[row["kind"]]):
            raise ValueError("AUDIT_EVENT_INVALID")
        if row["sim_time_s"] is not None and (
                isinstance(row["sim_time_s"], bool) or not isinstance(row["sim_time_s"], (int, float))
                or not math.isfinite(row["sim_time_s"]) or row["sim_time_s"] < 0):
            raise ValueError("AUDIT_EVENT_INVALID")
        if row["kind"] == "release" and (
                payload.get("release_epoch") != (row["identity"].get("release_epoch"))):
            # F3: the writer correlates a release payload's epoch with its identity, so the readback does
            # too; a re-signed event may not claim one epoch in its payload and another in its identity
            raise ValueError("AUDIT_EVENT_INVALID")
        if not _event_identity_ok(row["identity"], identity, release_epoch=event_epoch):
            raise ValueError("AUDIT_EVENT_INVALID")
        event_epoch = row["identity"]["release_epoch"]
        if row["kind"] in ("phase_complete", "run_complete", "run_aborted"):
            if type(payload["physics_step"]) is not int or payload["physics_step"] < 0:
                raise ValueError("AUDIT_EVENT_INVALID")
        if row["kind"] == "phase_complete" and (not isinstance(payload["phase"], str)
                                                or not payload["phase"]):
            raise ValueError("AUDIT_EVENT_INVALID")
        if not _payload_typed(payload):
            raise ValueError("AUDIT_EVENT_INVALID")
        sequence = row["sequence"]
    # F3: on a formal audit every release step the stream takes must be named by a release event - the
    # writer's own tie (CP-2137) restated here, because a re-signed stream never passes through the writer.
    # A diagnostic audit is out of scope, exactly as it is for that gate.
    _source = audit / "source.json"
    _formal_mode = False
    if _source.is_file():
        try:
            _formal_mode = json.loads(_source.read_bytes()).get("mode") == "formal"
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            _formal_mode = False
    if _formal_mode and (audit / "events.jsonl").is_file():
        _named: dict = {}
        for _row in _records(audit / "events.jsonl", _EVENT_FIELDS, "AUDIT_EVENT_INVALID"):
            _step = _row["identity"].get("release_epoch")
            if type(_step) is int:
                _named[_step] = _named.get(_step, False) or _row["kind"] == "release"
        if any(step > 0 and not seen for step, seen in _named.items()):
            raise ValueError("AUDIT_EVENT_INVALID")

    epoch: int | None = None
    sequence = 0
    for row in _records(audit / "physics.jsonl", _PHYSICS_FIELDS, "AUDIT_PHYSICS_INVALID"):
        if (type(row["sequence"]) is not int or row["sequence"] != sequence + 1
                or row["kind"] not in _PHYSICS_KINDS
                or isinstance(row["sim_time_s"], bool)
                or not isinstance(row["sim_time_s"], (int, float))
                or not math.isfinite(row["sim_time_s"]) or row["sim_time_s"] < 0
                or row["observation"].get("simulation_time_s") != row["sim_time_s"]
                or type(row["release_epoch"]) is not int or row["release_epoch"] < 0
                ):
            raise ValueError("AUDIT_PHYSICS_INVALID")
        sequence = row["sequence"]
        if epoch is None or row["release_epoch"] > epoch:
            epoch = row["release_epoch"]
        elif row["release_epoch"] < epoch:
            raise ValueError("AUDIT_RELEASE_EPOCH_STALE")
        if not _physics_observation_typed(row["observation"], kind=row["kind"]):
            # readback applies the same source contract the writer admitted
            raise ValueError("AUDIT_PHYSICS_INVALID")
    declared = json.loads((audit / "episode.json").read_bytes())
    scope = json.loads((audit / "source.json").read_bytes())
    inputs = json.loads((audit / "inputs.json").read_bytes())
    if (declared != identity or not _scope_ok(scope) or not _identity_ok(declared)
            or not isinstance(inputs, dict) or not _hex64(inputs.get("inputs_sha256"))
            or inputs["inputs_sha256"] != scope["inputs_sha256"]
            or not _identity_ok(declared, formal=scope["mode"] == "formal")):
        # the manifest identity must be the identity the episode actually recorded, and the scope and
        # inputs payloads must be the closed documents they claim to be
        raise ValueError("AUDIT_METADATA_INVALID")
