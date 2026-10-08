"""Closed readback of complete native physics chunks and original callback receipts.

This record is distinct from the older contact-policy projection. No field in the
native ROS message is removed, and source clock intervals remain monotonic times.
The native chunk does not publish a world publisher sequence or model digest.
"""

from __future__ import annotations

import copy
import math

_ENVELOPE = {"schema_version", "received_monotonic_ns", "chunk"}
_CHUNK = {"chunk_sequence", "simulation_session_id", "reset_epoch", "first_physics_step",
          "last_physics_step", "first_simulation_time_s", "last_simulation_time_s",
          "failed_publish_attempts", "handoff_monotonic_ns", "publish_monotonic_ns", "publish_deferrals_total",
          "evidence_loss", "samples"}
_STEP = {"simulation_session_id", "reset_epoch", "physics_step", "simulation_time_s",
         "clock_interval_begin_monotonic_ns", "clock_interval_end_monotonic_ns", "model_qpos",
         "model_qvel", "object_pose_world", "object_twist_world", "has_contact", "truncated",
         "maximum_normal_force_n", "total_normal_force_n", "left_fingertip_total_normal_force_n",
         "right_fingertip_total_normal_force_n", "fingertip_max_single_contact_force_n",
         "global_max_single_contact_force_n", "left_fingertip_compression_m", "right_fingertip_compression_m",
         "net_contact_force_world_n", "static_shadow_crossed", "diagnostic_hazard_breached",
         "left_fingertip_contacts", "right_fingertip_contacts", "other_object_contacts"}
_CONTACT = {"body1_id", "geom1_id", "body1", "geom1", "body2_id", "geom2_id", "body2", "geom2",
            "position_world", "normal_world", "signed_distance_m", "normal_force_n"}
_FORCES = {"maximum_normal_force_n", "total_normal_force_n", "left_fingertip_total_normal_force_n",
           "right_fingertip_total_normal_force_n", "fingertip_max_single_contact_force_n",
           "global_max_single_contact_force_n", "left_fingertip_compression_m", "right_fingertip_compression_m"}
_CONTACT_LISTS = ("left_fingertip_contacts", "right_fingertip_contacts", "other_object_contacts")


def _exact(value, keys):
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("PHYSICS_RAW_SCHEMA_INVALID")


def _integer(value, minimum=0, maximum=2**64-1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("PHYSICS_RAW_INTEGER_INVALID")
    return value


def _number(value, *, nonnegative=False):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or nonnegative and value < 0):
        raise ValueError("PHYSICS_RAW_NUMBER_INVALID")
    return value


def _vector(value, size=None):
    if not isinstance(value, list) or not value or size is not None and len(value) != size:
        raise ValueError("PHYSICS_RAW_VECTOR_INVALID")
    for item in value:
        _number(item)


def _xyz(value):
    _exact(value, {"x", "y", "z"})
    for item in value.values():
        _number(item)


def raw_chunk_from_ros(message, *, received_monotonic_ns, max_samples=None, max_contacts=None):
    """Copy original ROS values; receipt is supplied by the actual callback boundary."""
    from rosidl_runtime_py.convert import message_to_ordereddict
    from so101_mujoco_support.msg import PhysicsStepEvidenceChunk
    if not isinstance(message, PhysicsStepEvidenceChunk):
        raise ValueError("PHYSICS_RAW_MESSAGE_TYPE_INVALID")
    if max_samples is not None and len(message.samples) > max_samples:
        raise ValueError("PHYSICS_RAW_PRODUCER_BOUNDS_INVALID")
    if max_contacts is not None and any(sum(len(getattr(sample, name)) for name in _CONTACT_LISTS) > max_contacts
                                        for sample in message.samples):
        raise ValueError("PHYSICS_RAW_PRODUCER_BOUNDS_INVALID")
    record = {"schema_version": 1, "received_monotonic_ns": received_monotonic_ns,
              "chunk": copy.deepcopy(dict(message_to_ordereddict(message)))}
    verify_raw_chunk(record, max_samples=max_samples, max_contacts=max_contacts)
    return record


def verify_raw_chunk(record, *, previous=None, session_id=None, reset_epoch=None,
                     nq=None, nv=None, max_samples=None, max_contacts=None):
    """Recompute source type, scope, loss, clocks and .002 s continuity from raw values.

    The first retained chunk may start after reset. Complete episode coverage must
    separately bind its actual first/last steps to reset/command/stop boundaries.
    """
    _exact(record, _ENVELOPE)
    if type(record["schema_version"]) is not int or record["schema_version"] != 1:
        raise ValueError("PHYSICS_RAW_VERSION_INVALID")
    receipt = _integer(record["received_monotonic_ns"], 1, 2**63-1)
    for dimension in (nq, nv):
        if dimension is not None:
            _integer(dimension, 1)
    if max_samples is not None:
        _integer(max_samples, 1)
    if max_contacts is not None:
        _integer(max_contacts)
    chunk = record["chunk"]
    _exact(chunk, _CHUNK)
    if (not isinstance(chunk["simulation_session_id"], str) or not chunk["simulation_session_id"]
            or session_id is not None and chunk["simulation_session_id"] != session_id
            or reset_epoch is not None and chunk["reset_epoch"] != reset_epoch):
        raise ValueError("PHYSICS_RAW_SCOPE_INVALID")
    _integer(chunk["reset_epoch"])
    _integer(chunk["chunk_sequence"])
    for name in ("handoff_monotonic_ns", "publish_monotonic_ns", "publish_deferrals_total"):
        _integer(chunk[name])     # publish-path instrumentation (CP-3410): telemetry, never a rule
    if chunk["evidence_loss"] is not False or _integer(chunk["failed_publish_attempts"]) != 0:
        raise ValueError("PHYSICS_RAW_SOURCE_LOSS")
    samples = chunk["samples"]
    if not isinstance(samples, list) or not samples:
        raise ValueError("PHYSICS_RAW_SAMPLES_INVALID")
    if max_samples is not None and len(samples) > max_samples:
        raise ValueError("PHYSICS_RAW_PRODUCER_BOUNDS_INVALID")
    prior = None
    if previous is not None:
        verify_raw_chunk(previous, session_id=session_id, reset_epoch=reset_epoch, nq=nq, nv=nv,
                         max_samples=max_samples, max_contacts=max_contacts)
        prior_chunk = previous["chunk"]
        if (chunk["chunk_sequence"] != prior_chunk["chunk_sequence"] + 1
                or (chunk["simulation_session_id"], chunk["reset_epoch"]) !=
                   (prior_chunk["simulation_session_id"], prior_chunk["reset_epoch"])
                or receipt < previous["received_monotonic_ns"]):
            raise ValueError("PHYSICS_RAW_CONTINUITY_INVALID")
        prior = prior_chunk["samples"][-1]
    for sample in samples:
        _exact(sample, _STEP)
        if (sample["simulation_session_id"], sample["reset_epoch"]) != (
                chunk["simulation_session_id"], chunk["reset_epoch"]):
            raise ValueError("PHYSICS_RAW_SCOPE_INVALID")
        _integer(sample["reset_epoch"])
        _integer(sample["physics_step"], 1)
        sim = round(_number(sample["simulation_time_s"], nonnegative=True) * 1e9)
        begin = _integer(sample["clock_interval_begin_monotonic_ns"], 1, 2**63-1)
        end = _integer(sample["clock_interval_end_monotonic_ns"], 1, 2**63-1)
        if not 0 < begin <= end <= receipt:
            raise ValueError("PHYSICS_RAW_CLOCK_INVALID")
        if prior is not None and (sample["physics_step"] != prior["physics_step"] + 1
                or sim - round(prior["simulation_time_s"] * 1e9) != 2_000_000
                or begin < prior["clock_interval_end_monotonic_ns"]):
            raise ValueError("PHYSICS_RAW_CONTINUITY_INVALID")
        _vector(sample["model_qpos"], nq)
        _vector(sample["model_qvel"], nv)
        pose = sample["object_pose_world"]
        _exact(pose, {"position", "orientation"})
        _xyz(pose["position"])
        _exact(pose["orientation"], {"x", "y", "z", "w"})
        quat = [_number(item) for item in pose["orientation"].values()]
        if abs(math.sqrt(sum(item * item for item in quat)) - 1.) > 1e-3:
            raise ValueError("PHYSICS_RAW_QUATERNION_INVALID")
        twist = sample["object_twist_world"]
        _exact(twist, {"linear", "angular"})
        _xyz(twist["linear"])
        _xyz(twist["angular"])
        _xyz(sample["net_contact_force_world_n"])
        if sample["truncated"] is not False or sample["diagnostic_hazard_breached"] is not False:
            raise ValueError("PHYSICS_RAW_SOURCE_HAZARD")
        if type(sample["has_contact"]) is not bool or type(sample["static_shadow_crossed"]) is not bool:
            raise ValueError("PHYSICS_RAW_FLAG_INVALID")
        for name in _FORCES:
            _number(sample[name], nonnegative=True)
        for name in _CONTACT_LISTS:
            if not isinstance(sample[name], list):
                raise ValueError("PHYSICS_RAW_CONTACT_INVALID")
        if max_contacts is not None and sum(len(sample[name]) for name in _CONTACT_LISTS) > max_contacts:
            raise ValueError("PHYSICS_RAW_PRODUCER_BOUNDS_INVALID")
        for name in _CONTACT_LISTS:
            for contact in sample[name]:
                _exact(contact, _CONTACT)
                for name in ("body1_id", "geom1_id", "body2_id", "geom2_id"):
                    _integer(contact[name], maximum=2**31-1)
                for name in ("body1", "geom1", "body2", "geom2"):
                    if not isinstance(contact[name], str) or not contact[name]:
                        raise ValueError("PHYSICS_RAW_CONTACT_INVALID")
                _xyz(contact["position_world"])
                _xyz(contact["normal_world"])
                _number(contact["signed_distance_m"])
                _number(contact["normal_force_n"], nonnegative=True)
        prior = sample
    # CP-3410 (user-authorized contract change): there is no per-chunk delivery-age rule. How long a chunk took from its newest
    # sample to the receiver is recorded as telemetry; a late chunk is as valid as any other. Continuity, scope and every
    # content check above and below are unchanged; backlog and receiver lag are bounded by the adapter's frozen policy.
    if (_integer(chunk["first_physics_step"], 1) != samples[0]["physics_step"]
            or _integer(chunk["last_physics_step"], 1) != samples[-1]["physics_step"]
            or round(_number(chunk["first_simulation_time_s"], nonnegative=True) * 1e9) !=
               round(samples[0]["simulation_time_s"] * 1e9)
            or round(_number(chunk["last_simulation_time_s"], nonnegative=True) * 1e9) !=
               round(samples[-1]["simulation_time_s"] * 1e9)):
        raise ValueError("PHYSICS_RAW_ENVELOPE_INVALID")
    return record
