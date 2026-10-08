"""Original published pose candidates for independent endpoint boundary proof."""

import copy
from dataclasses import asdict
import json
import math
from pathlib import Path

from .contracts import fields, integer, vector, finite
from .scene_association import _world, _raw_source_matches, source_model_data

WORLD_KIND = "ACT_NATIVE_WORLD_SOURCE"


def world_source_record(received, scene, *, execution_root):
    world = received.evidence
    return json.loads(json.dumps({"kind": WORLD_KIND, "schema_version": 1,
        "execution_root": str(Path(execution_root).absolute()),
        "physics": asdict(world), "received_monotonic_ns": round(received.received_monotonic_s * 1e9),
        "scene_state": copy.deepcopy(scene[0]), "scene_received_monotonic_ns": round(scene[1] * 1e9),
        "native_reference": {"kind": "native_physics_step", "session_id": world.simulation_session_id,
            "reset_epoch": world.reset_epoch, "simulation_step": world.simulation_step}}, allow_nan=False))


def validate_world_source(document, *, identity, previous=None):
    from ..adapters.act.scene_state import SceneStateObserver
    fields(document, {"kind", "schema_version", "execution_root", "physics", "received_monotonic_ns",
                      "scene_state", "scene_received_monotonic_ns", "native_reference"})
    if document["kind"] != WORLD_KIND or type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise ValueError("WORLD_SOURCE_VERSION_INVALID")
    if (not isinstance(document["execution_root"], str) or not Path(document["execution_root"]).is_absolute()
            or ".." in Path(document["execution_root"]).parts):
        raise ValueError("WORLD_SOURCE_EXECUTION_ROOT_INVALID")
    for key in ("received_monotonic_ns", "scene_received_monotonic_ns"):
        integer(document[key], minimum=1)
    world = _world(document["physics"])
    if (world.simulation_session_id != identity["session_id"] or world.reset_epoch != identity["reset_epoch"]
            or world.frame_id != "world" or world.object_state.body != "plastic_cup"
            or world.paused or world.truncated or world.simulation_step < 1):
        raise ValueError("WORLD_SOURCE_SCOPE_INVALID")
    state = world.object_state
    for values in (state.position_world, state.linear_velocity_world, state.angular_velocity_world):
        vector(values, 3)
    vector(state.orientation_xyzw, 4)
    if abs(math.sqrt(sum(value * value for value in state.orientation_xyzw)) - 1) > 1e-3:
        raise ValueError("WORLD_SOURCE_POSE_INVALID")
    reference = document["native_reference"]
    fields(reference, {"kind", "session_id", "reset_epoch", "simulation_step"})
    integer(reference["reset_epoch"], minimum=1)
    integer(reference["simulation_step"], minimum=1)
    if reference != {"kind": "native_physics_step", "session_id": identity["session_id"],
            "reset_epoch": identity["reset_epoch"], "simulation_step": world.simulation_step}:
        raise ValueError("WORLD_SOURCE_REFERENCE_INVALID")
    scene = document["scene_state"]
    SceneStateObserver(model_sha256=scene["model_sha256"], nq=len(scene["qpos"]), nv=len(scene["qvel"]),
        max_age_s=.1, monotonic=lambda: document["scene_received_monotonic_ns"] / 1e9).validate(scene)
    if ((scene["simulation_session_id"], scene["reset_epoch"], scene["simulation_step"])
            != (world.simulation_session_id, world.reset_epoch, world.simulation_step)
            or round(scene["simulation_time_s"] * 1e9) != round(world.simulation_time_s * 1e9)
            or scene["paused"] or scene["clock_interval_begin_monotonic_ns"] > document["received_monotonic_ns"]):
        raise ValueError("WORLD_SOURCE_CLOCK_INVALID")
    if previous is not None:
        old = _world(previous["physics"])
        if (world.publisher_sequence != old.publisher_sequence + 1 or world.simulation_step <= old.simulation_step
                or world.simulation_time_s <= old.simulation_time_s
                or document["received_monotonic_ns"] < previous["received_monotonic_ns"]):
            raise ValueError("WORLD_SOURCE_SEQUENCE_INVALID")
    return world


# A verification loop checks thousands of world sources against ONE model and ONE list of raw physics samples (an episode of
# 100 s has ~8000 sources and ~58000 samples). Hashing the model and scanning the samples once per source made the seal and the QC
# quadratic (tens of minutes). Both are memoised here, keyed on the objects' identity (and, for the list, its length and ends);
# the results are the same values the per-call computation gave.
_MODEL_SHA = {}
_RAW_INDEX = {"list": None, "len": -1, "index": {}}


def _model_sha256_cached(model):
    from ..adapters.act.physics import model_sha256
    entry = _MODEL_SHA.get(id(model))
    if entry is None or entry[0] is not model:
        if len(_MODEL_SHA) > 8:
            _MODEL_SHA.clear()
        entry = _MODEL_SHA[id(model)] = (model, model_sha256(model))
    return entry[1]


def _raw_steps_at(raw_steps, step):
    """The samples of `raw_steps` at `step`, in list order. A short list (the seal passes a one-element list per source) is scanned;
    a long one is indexed once and the index reused while it is the same list object, kept alive here so its identity cannot be
    reused by another list, and of the same length."""
    if len(raw_steps) <= 64:
        return [sample for sample in raw_steps if sample["physics_step"] == step]
    if _RAW_INDEX["list"] is not raw_steps or _RAW_INDEX["len"] != len(raw_steps):
        index = {}
        for sample in raw_steps:
            index.setdefault(sample["physics_step"], []).append(sample)
        _RAW_INDEX["list"], _RAW_INDEX["len"], _RAW_INDEX["index"] = raw_steps, len(raw_steps), index
    return _RAW_INDEX["index"].get(step, [])


def verify_world_source(document, *, identity, model, model_identity, raw_steps, previous=None):
    import mujoco
    world = validate_world_source(document, identity=identity, previous=previous)
    if model_identity != {"model_sha256": _model_sha256_cached(model), "nq": model.nq, "nv": model.nv,
                          "mujoco_version": mujoco.__version__}:
        raise ValueError("WORLD_SOURCE_MODEL_INVALID")
    scene = document["scene_state"]
    if scene["model_sha256"] != model_identity["model_sha256"]:
        raise ValueError("WORLD_SOURCE_MODEL_INVALID")
    source_model_data(model, world, scene)
    matches = _raw_steps_at(raw_steps, world.simulation_step)
    if len(matches) != 1:
        raise ValueError("WORLD_SOURCE_NATIVE_REQUIRED")
    sample = matches[0]
    if ((sample["simulation_session_id"], sample["reset_epoch"])
            != (world.simulation_session_id, world.reset_epoch)
            or round(sample["simulation_time_s"] * 1e9) != round(world.simulation_time_s * 1e9)
            or sample["model_qpos"] != scene["qpos"] or sample["model_qvel"] != scene["qvel"]
            or not _raw_source_matches(sample, world, scene)):
        raise ValueError("WORLD_SOURCE_NATIVE_MISMATCH")
    return True


def validate_source_clock(clock):
    fields(clock, {"sim_time_ns", "begin_monotonic_ns", "end_monotonic_ns"})
    integer(clock["sim_time_ns"])
    integer(clock["begin_monotonic_ns"], minimum=1)
    integer(clock["end_monotonic_ns"], minimum=clock["begin_monotonic_ns"])
    return clock


def validate_normal_stop_boundary_v2(boundary, *, identity):
    """The V2 normal-stop boundary: a successful `ExecuteTrajectory` result, then every arm and gripper joint at rest.

    It names the world sample the stop is anchored to (session, epoch, step, publisher sequence, sim stamp) and the
    clock of that observation. The anchor sample itself is the Recorder's own original; this proves nothing about it
    beyond the identifiers, which `first_world_after_stop` then matches against that original.
    """
    from types import SimpleNamespace
    fields(boundary, {"kind", "schema_version", "epoch", "source_clock", "confirmed_monotonic_ns",
                      "stop_confirmed_wall_s", "trajectory_result", "joint_positions", "joint_velocities"})
    if (boundary["kind"] != "ACT_NORMAL_STOP_BOUNDARY" or type(boundary["schema_version"]) is not int
            or boundary["schema_version"] != 2):
        raise ValueError("ENDPOINT_STOP_VERSION_INVALID")
    if boundary["trajectory_result"] != "SUCCEEDED":
        raise ValueError("NATIVE_QC_STOP_RESULT_INVALID")
    clock = validate_source_clock(boundary["source_clock"])
    integer(boundary["confirmed_monotonic_ns"], minimum=1)
    if boundary["confirmed_monotonic_ns"] != clock["end_monotonic_ns"]:
        raise ValueError("ENDPOINT_STOP_CLOCK_INVALID")
    epoch = boundary["epoch"]
    fields(epoch, {"session_id", "reset_epoch", "simulation_step", "publisher_sequence",
                   "simulation_time_s", "received_wall_s"})
    for key in ("reset_epoch", "simulation_step", "publisher_sequence"):
        integer(epoch[key], minimum=1)
    finite(epoch["simulation_time_s"], nonnegative=True)
    receipt_ns = round(finite(epoch["received_wall_s"], nonnegative=True) * 1e9)
    confirmed_ns = round(finite(boundary["stop_confirmed_wall_s"], nonnegative=True) * 1e9)
    if ((epoch["session_id"], epoch["reset_epoch"]) != (identity["session_id"], identity["reset_epoch"])
            or not 0 <= clock["sim_time_ns"] - round(epoch["simulation_time_s"] * 1e9) <= 100000000
            or not 0 < receipt_ns <= clock["begin_monotonic_ns"] or confirmed_ns > clock["begin_monotonic_ns"]):
        raise ValueError("ENDPOINT_STOP_MAPPING_INVALID")
    for key in ("joint_positions", "joint_velocities"):
        fields(boundary[key], tuple("123456"))
        for value in boundary[key].values():
            finite(value)
    if any(abs(value) > .002 for value in boundary["joint_velocities"].values()):
        raise ValueError("NATIVE_QC_STOP_MEASURED_MOVING")
    return SimpleNamespace(simulation_session_id=epoch["session_id"], reset_epoch=epoch["reset_epoch"],
                           simulation_step=epoch["simulation_step"], publisher_sequence=epoch["publisher_sequence"],
                           simulation_time_s=epoch["simulation_time_s"])


def first_world_after_stop(sources, boundary, *, identity, capture_clock, raw_steps):
    """Recompute FIRST from complete original publisher history, before evaluating pose quality.

    Native/FK source authenticity and full stop verdict/normal-end/lease proofs remain
    required by the enclosing independent audit reader; this selection alone is not QC.
    """
    bound = validate_normal_stop_boundary_v2(boundary, identity=identity)
    capture = validate_source_clock(capture_clock)
    last_native_step = None
    for sample in raw_steps:
        if (sample["simulation_session_id"], sample["reset_epoch"]) != (identity["session_id"], identity["reset_epoch"]):
            raise ValueError("ENDPOINT_NATIVE_SCOPE_INVALID")
        integer(sample["physics_step"], minimum=1)
        integer(sample["clock_interval_begin_monotonic_ns"], minimum=1)
        integer(sample["clock_interval_end_monotonic_ns"], minimum=sample["clock_interval_begin_monotonic_ns"])
        if sample["clock_interval_end_monotonic_ns"] <= boundary["confirmed_monotonic_ns"]:
            last_native_step = max(last_native_step or 0, sample["physics_step"])
    if last_native_step is None or last_native_step < bound.simulation_step:
        raise ValueError("ENDPOINT_STOP_NATIVE_REQUIRED")
    previous, anchor, selected = None, None, None
    for source in sources:
        world = validate_world_source(source, identity=identity, previous=previous)
        previous = source
        matches = [sample for sample in raw_steps if sample["physics_step"] == world.simulation_step]
        if (len(matches) != 1 or round(matches[0]["simulation_time_s"] * 1e9) != round(world.simulation_time_s * 1e9)
                or matches[0]["model_qpos"] != source["scene_state"]["qpos"]
                or matches[0]["model_qvel"] != source["scene_state"]["qvel"]
                or not _raw_source_matches(matches[0], world, source["scene_state"])):
            raise ValueError("ENDPOINT_NATIVE_SOURCE_INVALID")
        native = matches[0]
        if world.publisher_sequence == bound.publisher_sequence:
            if (world.simulation_session_id, world.reset_epoch, world.simulation_step, world.simulation_time_s) != (
                    bound.simulation_session_id, bound.reset_epoch, bound.simulation_step, bound.simulation_time_s):
                raise ValueError("ENDPOINT_STOP_SOURCE_MISMATCH")
            anchor = source
        if anchor is None or world.publisher_sequence <= bound.publisher_sequence:
            continue
        stamp_ns = round(world.simulation_time_s * 1e9)
        stop_ns = boundary["source_clock"]["sim_time_ns"]
        if (stamp_ns < stop_ns or (stamp_ns == stop_ns and world.simulation_step <= last_native_step)
                or native["clock_interval_begin_monotonic_ns"] < boundary["confirmed_monotonic_ns"]
                or source["scene_state"]["clock_interval_begin_monotonic_ns"] < boundary["confirmed_monotonic_ns"]):
            continue
        if selected is None:
            selected = source
    if anchor is None:
        raise ValueError("ENDPOINT_STOP_PREDECESSOR_REQUIRED")
    if selected is None:
        raise ValueError("ENDPOINT_FINAL_SOURCE_UNAVAILABLE")
    if (not 0 <= capture["sim_time_ns"] - round(selected["physics"]["simulation_time_s"] * 1e9) <= 100000000
            or capture["begin_monotonic_ns"] < max(selected["received_monotonic_ns"], selected["scene_received_monotonic_ns"])):
        raise ValueError("ENDPOINT_CAPTURE_CLOCK_INVALID")
    return copy.deepcopy(selected)


def first_world_after_start(sources, *, identity, reset_clock, capture_start_clock,
                            first_dispatch_clock, capture_clock, raw_steps):
    """Select initial FIRST from retained originals; enclosing reader verifies reset/dispatch authority."""
    reset, start, dispatch, capture = [validate_source_clock(clock) for clock in (
        reset_clock, capture_start_clock, first_dispatch_clock, capture_clock)]
    if (not reset["sim_time_ns"] <= start["sim_time_ns"] <= capture["sim_time_ns"] <= dispatch["sim_time_ns"]
            or reset["end_monotonic_ns"] > start["begin_monotonic_ns"]
            or start["end_monotonic_ns"] > capture["begin_monotonic_ns"]
            or capture["end_monotonic_ns"] > dispatch["begin_monotonic_ns"]):
        raise ValueError("ENDPOINT_INITIAL_BOUNDARY_INVALID")
    selected=first_world_after_capture_start(sources,identity=identity,reset_clock=reset,
        capture_start_clock=start,capture_clock=capture,raw_steps=raw_steps)
    if round(selected['physics']['simulation_time_s']*1e9)>=dispatch['sim_time_ns']:
        raise ValueError('ENDPOINT_INITIAL_CAPTURE_INVALID')
    return selected


def first_world_after_capture_start(sources, *, identity, reset_clock, capture_start_clock,
                                    capture_clock, raw_steps):
    """Online FIRST selection, with no invented future dispatch or pose-quality filter.

    The sealed reader additionally compares this original capture to the actual
    first enqueue through first_world_after_start.
    """
    reset,start,capture=[validate_source_clock(clock) for clock in (
        reset_clock,capture_start_clock,capture_clock)]
    if (not reset['sim_time_ns']<=start['sim_time_ns']<=capture['sim_time_ns']
            or reset['end_monotonic_ns']>start['begin_monotonic_ns']
            or start['end_monotonic_ns']>capture['begin_monotonic_ns']):
        raise ValueError('ENDPOINT_INITIAL_BOUNDARY_INVALID')
    floor = max(reset["sim_time_ns"], start["sim_time_ns"])
    previous, predecessor, selected = None, False, None
    for source in sources:
        world = validate_world_source(source, identity=identity, previous=previous)
        previous = source
        matches = [sample for sample in raw_steps if sample["physics_step"] == world.simulation_step]
        if (len(matches) != 1 or (matches[0]["simulation_session_id"], matches[0]["reset_epoch"])
                != (identity["session_id"], identity["reset_epoch"])
                or round(matches[0]["simulation_time_s"] * 1e9) != round(world.simulation_time_s * 1e9)
                or matches[0]["model_qpos"] != source["scene_state"]["qpos"]
                or matches[0]["model_qvel"] != source["scene_state"]["qvel"]
                or not _raw_source_matches(matches[0], world, source["scene_state"])):
            raise ValueError("ENDPOINT_NATIVE_SOURCE_INVALID")
        native = matches[0]
        stamp_ns = round(world.simulation_time_s * 1e9)
        if (stamp_ns < floor or native["clock_interval_begin_monotonic_ns"] < start["end_monotonic_ns"]):
            predecessor = True
            continue
        if selected is None:
            if not predecessor:
                raise ValueError("ENDPOINT_INITIAL_PREDECESSOR_REQUIRED")
            selected = source
    if selected is None:
        raise ValueError("ENDPOINT_INITIAL_SOURCE_UNAVAILABLE")
    stamp_ns = round(selected["physics"]["simulation_time_s"] * 1e9)
    if (not 0 <= capture["sim_time_ns"] - stamp_ns <= 100_000_000
            or capture["begin_monotonic_ns"] < max(selected["received_monotonic_ns"],
                selected["scene_received_monotonic_ns"])):
        raise ValueError("ENDPOINT_INITIAL_CAPTURE_INVALID")
    return copy.deepcopy(selected)
