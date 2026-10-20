"""Closed readback of complete native physics chunks and original callback receipts.

This record is distinct from the older contact-policy projection. No field in the
native ROS message is removed, and source clock intervals remain monotonic times.
The native chunk does not publish a world publisher sequence or model digest.
"""

from __future__ import annotations

import array
import math

from .qc_session import Identity, session_memo

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
    if not isinstance(value, dict) or value.keys() != keys:
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


_NUMBER_TYPES = frozenset((int, float))
_isfinite = math.isfinite


def _numbers(values, *, nonnegative=False):
    """`_number` for every value of an iterable, with the type test and the finiteness test run in C over the whole batch.

    Same verdict as calling `_number` on each value: an exact int or float (bool and subclasses are refused), finite, and
    (when asked) not negative. The error is the same `PHYSICS_RAW_NUMBER_INVALID`.
    """
    values = list(values)
    if not _NUMBER_TYPES.issuperset(map(type, values)) or not all(map(_isfinite, values)) \
            or nonnegative and any(value < 0 for value in values):
        raise ValueError("PHYSICS_RAW_NUMBER_INVALID")


def _vector(value, size=None):
    if not isinstance(value, list) or not value or size is not None and len(value) != size:
        raise ValueError("PHYSICS_RAW_VECTOR_INVALID")
    _numbers(value)


def _xyz(value):
    _exact(value, {"x", "y", "z"})
    _numbers(value.values())


_CONVERTERS: dict = {}
_PRIMITIVES = (bool, int, float, str)


def _converter_for(message_class):
    """A function with the output of `message_to_ordereddict` for `message_class` (plain dicts in the field order), or None when the
    class has a field this does not handle (the caller then uses `message_to_ordereddict`). Built once per class from its field types."""
    if message_class in _CONVERTERS:
        return _CONVERTERS[message_class]
    from rosidl_runtime_py.utilities import get_message

    plan = []
    for name, type_name in message_class.get_fields_and_field_types().items():
        many = "[" in type_name or "<" in type_name
        base = type_name.split("<")[-1].rstrip(">").split("[")[0]
        if "/" in base:
            nested = _converter_for(get_message(base))
            if nested is None:
                _CONVERTERS[message_class] = None
                return None
            plan.append((name, "ms" if many else "m", nested))
        elif base in ("octet", "char", "wstring") or base.startswith("string<") or base.startswith("wstring"):
            _CONVERTERS[message_class] = None
            return None
        else:
            plan.append((name, "ps" if many else "p", None))

    def convert(message):
        out = {}
        for name, kind, nested in plan:
            value = getattr(message, name)
            if kind == "p":
                if type(value) not in _PRIMITIVES:
                    raise _Unhandled
                out[name] = value
            elif kind == "m":
                out[name] = nested(value)
            elif kind == "ps":
                if type(value) is list:
                    items = value
                elif type(value) is array.array:
                    items = list(value)
                else:
                    raise _Unhandled
                if not _PRIMITIVE_SET.issuperset(map(type, items)):
                    raise _Unhandled
                out[name] = list(items)
            else:
                if type(value) is not list:
                    raise _Unhandled
                out[name] = [nested(item) for item in value]
        return out
    _CONVERTERS[message_class] = convert
    return convert


class _Unhandled(Exception):
    """A value the specialised conversion does not know: the generic one runs instead."""


_PRIMITIVE_SET = frozenset(_PRIMITIVES)


def message_to_dict(message):
    """`dict(message_to_ordereddict(message))` for a physics evidence message, without the generic per-value dispatch (about 3x faster).

    The values are the message's own scalars; arrays become lists. Anything this does not recognise (bytes fields, numpy arrays) takes
    the generic conversion, so the result is always what the generic one gives."""
    from rosidl_runtime_py.convert import message_to_ordereddict

    convert = _converter_for(type(message))
    if convert is not None:
        try:
            return convert(message)
        except _Unhandled:
            pass
    return dict(message_to_ordereddict(message))


def raw_chunk_from_ros(message, *, received_monotonic_ns, max_samples=None, max_contacts=None):
    """Copy original ROS values; receipt is supplied by the actual callback boundary."""
    from so101_mujoco_support.msg import PhysicsStepEvidenceChunk
    if not isinstance(message, PhysicsStepEvidenceChunk):
        raise ValueError("PHYSICS_RAW_MESSAGE_TYPE_INVALID")
    if max_samples is not None and len(message.samples) > max_samples:
        raise ValueError("PHYSICS_RAW_PRODUCER_BOUNDS_INVALID")
    if max_contacts is not None and any(sum(len(getattr(sample, name)) for name in _CONTACT_LISTS) > max_contacts
                                        for sample in message.samples):
        raise ValueError("PHYSICS_RAW_PRODUCER_BOUNDS_INVALID")
    record = {"schema_version": 1, "received_monotonic_ns": received_monotonic_ns,
              # `message_to_ordereddict` builds a new tree of containers around immutable scalars: a copy of it would be a second
              # copy of nothing anyone else holds
              "chunk": message_to_dict(message)}
    verify_raw_chunk(record, max_samples=max_samples, max_contacts=max_contacts)
    return record


def _chunk_key(record, *, previous=None, session_id=None, reset_epoch=None, nq=None, nv=None, max_samples=None,
               max_contacts=None, previous_verified=False):
    return (Identity(record), None if previous is None else Identity(previous), session_id, reset_epoch, nq, nv, max_samples,
            max_contacts, previous_verified)


@session_memo(_chunk_key, copy_result=False)
def verify_raw_chunk(record, *, previous=None, session_id=None, reset_epoch=None,
                     nq=None, nv=None, max_samples=None, max_contacts=None, previous_verified=False):
    """Recompute source type, scope, loss, clocks and .002 s continuity from raw values.

    The first retained chunk may start after reset. Complete episode coverage must
    separately bind its actual first/last steps to reset/command/stop boundaries.

    `previous` is verified first, as a record on its own, unless the caller states `previous_verified`: a loop that has just
    verified `previous` with these very arguments as the current record of its previous pass (and so would have stopped on a
    defect) says so, and the chunk is not checked a second time.

    The checks fall in two groups: those that read the record alone (envelope, integer and number types, finiteness, clocks, flags,
    quaternion norm, the continuity of one sample to the next inside the chunk, the first/last bookkeeping) and those that compare
    it with the arguments (the session and reset epoch, `nq`/`nv`/`max_samples`/`max_contacts`, the `previous` chunk). The standalone
    check of a retained chunk and the continuity check of the same chunk (different arguments, so different memo entries) share the
    first group inside a QC session: once a call over this very record has returned, the record passed every check of that group,
    and a later call over it with other arguments runs the second group only, in the order it always ran. A call that raised
    leaves nothing behind."""
    from .qc_session import active

    session = active()
    marker = None if session is None else ("raw_chunk_record_checked", Identity(record))
    known = marker is not None and marker in session.cache
    result = _verify_raw_chunk(record, previous=previous, session_id=session_id, reset_epoch=reset_epoch, nq=nq, nv=nv,
                               max_samples=max_samples, max_contacts=max_contacts, previous_verified=previous_verified,
                               known=known)
    if marker is not None and not known:
        session.cache[marker] = True
    return result


def _verify_raw_chunk(record, *, previous, session_id, reset_epoch, nq, nv, max_samples, max_contacts, previous_verified, known):
    """`verify_raw_chunk`; with `known` the checks that read the record alone are skipped (they have passed for this record)."""
    if not known:
        _exact(record, _ENVELOPE)
        if type(record["schema_version"]) is not int or record["schema_version"] != 1:
            raise ValueError("PHYSICS_RAW_VERSION_INVALID")
        receipt = _integer(record["received_monotonic_ns"], 1, 2**63-1)
    else:
        receipt = record["received_monotonic_ns"]
    for dimension in (nq, nv):
        if dimension is not None:
            _integer(dimension, 1)
    if max_samples is not None:
        _integer(max_samples, 1)
    if max_contacts is not None:
        _integer(max_contacts)
    chunk = record["chunk"]
    if not known:
        _exact(chunk, _CHUNK)
        if (not isinstance(chunk["simulation_session_id"], str) or not chunk["simulation_session_id"]
                or session_id is not None and chunk["simulation_session_id"] != session_id
                or reset_epoch is not None and chunk["reset_epoch"] != reset_epoch):
            raise ValueError("PHYSICS_RAW_SCOPE_INVALID")
        _integer(chunk["reset_epoch"])
        _integer(chunk["chunk_sequence"])
        for name in ("handoff_monotonic_ns", "publish_monotonic_ns", "publish_deferrals_total"):
            _integer(chunk[name])     # publish-path instrumentation: telemetry, never a rule
        if chunk["evidence_loss"] is not False or _integer(chunk["failed_publish_attempts"]) != 0:
            raise ValueError("PHYSICS_RAW_SOURCE_LOSS")
        samples = chunk["samples"]
        if not isinstance(samples, list) or not samples:
            raise ValueError("PHYSICS_RAW_SAMPLES_INVALID")
    else:
        samples = chunk["samples"]
        if (session_id is not None and chunk["simulation_session_id"] != session_id
                or reset_epoch is not None and chunk["reset_epoch"] != reset_epoch):
            raise ValueError("PHYSICS_RAW_SCOPE_INVALID")
    if max_samples is not None and len(samples) > max_samples:
        raise ValueError("PHYSICS_RAW_PRODUCER_BOUNDS_INVALID")
    prior = None
    if previous is not None:
        if not previous_verified:
            verify_raw_chunk(previous, session_id=session_id, reset_epoch=reset_epoch, nq=nq, nv=nv,
                             max_samples=max_samples, max_contacts=max_contacts)
        prior_chunk = previous["chunk"]
        if (chunk["chunk_sequence"] != prior_chunk["chunk_sequence"] + 1
                or (chunk["simulation_session_id"], chunk["reset_epoch"]) !=
                   (prior_chunk["simulation_session_id"], prior_chunk["reset_epoch"])
                or receipt < previous["received_monotonic_ns"]):
            raise ValueError("PHYSICS_RAW_CONTINUITY_INVALID")
        prior = prior_chunk["samples"][-1]
    if known:
        _verify_known_chunk_arguments(samples, prior, nq=nq, nv=nv, max_contacts=max_contacts)
        return record
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
        quat = list(pose["orientation"].values())
        _numbers(quat)
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
        _numbers((sample[name] for name in _FORCES), nonnegative=True)
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
    # User-authorized contract: there is no per-chunk delivery-age rule. How long a chunk took from its newest
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


def _verify_known_chunk_arguments(samples, prior, *, nq, nv, max_contacts):
    """The sample loop of `_verify_raw_chunk` for a record whose own checks have passed: only what depends on the arguments is left,
    in the order the full loop raises it per sample: the step/time/clock continuity of the first sample to the `previous` chunk's
    last one, the sizes of the two state vectors, the contact bound. (Inside the chunk the continuity of one sample to the next is a
    property of the record.)"""
    if prior is None and nq is None and nv is None and max_contacts is None:
        return
    first = True
    for sample in samples:
        if first and prior is not None:
            sim = round(sample["simulation_time_s"] * 1e9)
            if (sample["physics_step"] != prior["physics_step"] + 1
                    or sim - round(prior["simulation_time_s"] * 1e9) != 2_000_000
                    or sample["clock_interval_begin_monotonic_ns"] < prior["clock_interval_end_monotonic_ns"]):
                raise ValueError("PHYSICS_RAW_CONTINUITY_INVALID")
        first = False
        if nq is not None and len(sample["model_qpos"]) != nq:
            raise ValueError("PHYSICS_RAW_VECTOR_INVALID")
        if nv is not None and len(sample["model_qvel"]) != nv:
            raise ValueError("PHYSICS_RAW_VECTOR_INVALID")
        if max_contacts is not None and sum(len(sample[name]) for name in _CONTACT_LISTS) > max_contacts:
            raise ValueError("PHYSICS_RAW_PRODUCER_BOUNDS_INVALID")
