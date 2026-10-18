"""Proof that the QC regrade speed-ups (O1) leave every verdict and refusal reason unchanged.

Each section keeps a verbatim copy of the pre-change function as the reference and compares (value | exception type and message)
of the reference and the shipped function on valid and corrupt synthetic inputs. Fixtures build their own data."""

import copy
import math
from pathlib import Path

import pytest

from test_act_native_world_history import frozen_scene, source_record  # noqa: F401  (pytest fixture)


def outcome(function, *args, **kwargs):
    try:
        return ("value", function(*args, **kwargs))
    except Exception as error:  # noqa: BLE001 - the refusal type and message are the comparison
        return ("raised", type(error).__name__, str(error))


# ---- (3) validate_world_source: the document checks are shared per source content ------------------------------------------

IDENTITY = {"session_id": "alignment-session", "reset_epoch": 1}


def _reference_imports():
    from so101_demo.act.contracts import fields, integer, vector
    from so101_demo.act.native_endpoints import WORLD_KIND
    from so101_demo.act.scene_association import _world
    return fields, integer, vector, WORLD_KIND, _world


def reference_validate_world_source(document, *, identity, previous=None):
    from so101_demo.adapters.act.scene_state import SceneStateObserver
    fields, integer, vector, WORLD_KIND, _world = _reference_imports()
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


def _following(first, *, sequence=1, step=1, seconds=.01, receipt=1000):
    value = copy.deepcopy(first)
    value["physics"]["publisher_sequence"] += sequence
    value["physics"]["simulation_step"] += step
    value["physics"]["simulation_time_s"] += seconds
    value["scene_state"]["simulation_step"] += step
    value["scene_state"]["simulation_time_s"] += seconds
    value["native_reference"]["simulation_step"] += step
    value["received_monotonic_ns"] += receipt
    return value


def _set(path, replacement):
    def mutate(value):
        target = value
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = replacement
    return mutate


def _delete(path):
    def mutate(value):
        target = value
        for key in path[:-1]:
            target = target[key]
        del target[path[-1]]
    return mutate


DOCUMENT_MUTATIONS = {
    "none": lambda value: None,
    "kind": _set(["kind"], "OTHER"),
    "version_true": _set(["schema_version"], True),
    "version_two": _set(["schema_version"], 2),
    "root_relative": _set(["execution_root"], "relative/root"),
    "root_dotdot": _set(["execution_root"], "/a/../b"),
    "root_not_str": _set(["execution_root"], 5),
    "received_zero": _set(["received_monotonic_ns"], 0),
    "received_float": _set(["received_monotonic_ns"], 1.5),
    "scene_received_bool": _set(["scene_received_monotonic_ns"], True),
    "session": _set(["physics", "simulation_session_id"], "other"),
    "epoch": _set(["physics", "reset_epoch"], 2),
    "frame": _set(["physics", "frame_id"], "gripper"),
    "body": _set(["physics", "object_state", "body"], "box"),
    "paused": _set(["physics", "paused"], True),
    "truncated": _set(["physics", "truncated"], True),
    "step_zero": _set(["physics", "simulation_step"], 0),
    "position_short": _set(["physics", "object_state", "position_world"], [0., 0.]),
    "position_nan": _set(["physics", "object_state", "position_world"], [0., float("nan"), 0.]),
    "velocity_inf": _set(["physics", "object_state", "linear_velocity_world"], [0., float("inf"), 0.]),
    "quaternion_short": _set(["physics", "object_state", "orientation_xyzw"], [0., 0., 1.]),
    "quaternion_norm": _set(["physics", "object_state", "orientation_xyzw"], [0., 0., 0., 1.01]),
    "physics_extra": _set(["physics", "extra"], 1),
    "physics_missing": _delete(["physics", "paused"]),
    "reference_kind": _set(["native_reference", "kind"], "x"),
    "reference_step": _set(["native_reference", "simulation_step"], 99),
    "reference_session": _set(["native_reference", "session_id"], "other"),
    "reference_epoch_bool": _set(["native_reference", "reset_epoch"], True),
    "reference_extra": _set(["native_reference", "extra"], 1),
    "scene_model": _set(["scene_state", "model_sha256"], "0" * 64),
    "scene_qpos_short": _set(["scene_state", "qpos"], [0.]),
    "scene_step": _set(["scene_state", "simulation_step"], 5),
    "scene_time": _set(["scene_state", "simulation_time_s"], 5.),
    "scene_paused": _set(["scene_state", "paused"], True),
    "scene_clock": _set(["scene_state", "clock_interval_begin_monotonic_ns"], 2 ** 62),
    "scene_missing": _delete(["scene_state", "qvel"]),
    "document_extra": _set(["extra"], 1),
    "document_missing": _delete(["native_reference"]),
}


def _step_back(first, value):
    for part in ("physics", "scene_state", "native_reference"):
        value[part]["simulation_step"] = first["physics"]["simulation_step"]


def _time_back(first, value):
    for part in ("physics", "scene_state"):
        value[part]["simulation_time_s"] = first["physics"]["simulation_time_s"]


PREVIOUS_MUTATIONS = {
    "ok": lambda first, value: None,
    "gap": lambda first, value: value["physics"].__setitem__("publisher_sequence", first["physics"]["publisher_sequence"] + 2),
    "replay": lambda first, value: value["physics"].__setitem__("publisher_sequence", first["physics"]["publisher_sequence"]),
    "step_back": _step_back,
    "time_back": _time_back,
    "receipt_back": lambda first, value: value.__setitem__("received_monotonic_ns", first["received_monotonic_ns"] - 1),
}


def _scope(session):
    import contextlib
    from so101_demo.act.qc_session import qc_session
    return qc_session("readback:qc") if session else contextlib.nullcontext()


@pytest.fixture(scope="module")
def first_source(frozen_scene):
    record, _ = source_record(frozen_scene)
    return record


@pytest.mark.parametrize("session", [False, True])
def test_world_source_document_checks_agree_with_the_reference(first_source, session):
    from so101_demo.act.native_endpoints import validate_world_source
    cases = [("valid", copy.deepcopy(first_source))]
    for name, mutate in DOCUMENT_MUTATIONS.items():
        value = copy.deepcopy(first_source)
        mutate(value)
        cases.append((name, value))
    with _scope(session):
        for _ in range(2):  # the second round hits the content memo inside a session
            for name, value in cases:
                expected = outcome(reference_validate_world_source, value, identity=IDENTITY)
                assert outcome(validate_world_source, value, identity=IDENTITY) == expected, name
                # an equal copy in a different object is answered from the memo with the same outcome
                assert outcome(validate_world_source, copy.deepcopy(value), identity=IDENTITY) == expected, name
    assert outcome(reference_validate_world_source, cases[0][1], identity=IDENTITY)[0] == "value"
    accepted = [name for name, value in cases if outcome(reference_validate_world_source, value, identity=IDENTITY)[0] == "value"]
    assert accepted == ["valid", "none", "scene_model", "scene_qpos_short"], accepted


@pytest.mark.parametrize("session", [False, True])
def test_world_source_identity_scope_is_part_of_the_shared_result(first_source, session):
    from so101_demo.act.native_endpoints import validate_world_source
    with _scope(session):
        for identity in (IDENTITY, {"session_id": "alignment-session", "reset_epoch": 2}, {"session_id": "x", "reset_epoch": 1}, IDENTITY):
            assert outcome(validate_world_source, first_source, identity=identity) == outcome(
                reference_validate_world_source, first_source, identity=identity)


@pytest.mark.parametrize("session", [False, True])
@pytest.mark.parametrize("name", sorted(PREVIOUS_MUTATIONS))
def test_world_source_previous_checks_agree_with_the_reference(first_source, session, name):
    from so101_demo.act.native_endpoints import validate_world_source
    following = _following(first_source)
    PREVIOUS_MUTATIONS[name](first_source, following)
    with _scope(session):
        for _ in range(2):
            assert outcome(validate_world_source, following, identity=IDENTITY, previous=first_source) == outcome(
                reference_validate_world_source, following, identity=IDENTITY, previous=first_source)
        # the same source without a predecessor is not judged by the earlier predecessor
        assert outcome(validate_world_source, following, identity=IDENTITY) == outcome(
            reference_validate_world_source, following, identity=IDENTITY)
        for broken in ({}, {"physics": {}}, {"physics": 5}):
            assert outcome(validate_world_source, following, identity=IDENTITY, previous=broken) == outcome(
                reference_validate_world_source, following, identity=IDENTITY, previous=broken)


def test_world_source_keys_never_mix_types(first_source):
    from so101_demo.act.native_endpoints import validate_world_source
    mutated = copy.deepcopy(first_source)
    mutated["scene_received_monotonic_ns"] = float(mutated["scene_received_monotonic_ns"])
    with _scope(True):
        validate_world_source(first_source, identity=IDENTITY)
        assert outcome(validate_world_source, mutated, identity=IDENTITY) == outcome(
            reference_validate_world_source, mutated, identity=IDENTITY)
        assert outcome(validate_world_source, mutated, identity=IDENTITY)[0] == "raised"
        unpicklable = copy.deepcopy(first_source)
        unpicklable["kind"] = lambda: None
        assert outcome(validate_world_source, unpicklable, identity=IDENTITY) == outcome(
            reference_validate_world_source, unpicklable, identity=IDENTITY)


def test_world_source_is_validated_once_per_content_inside_a_session(first_source):
    from so101_demo.act.native_endpoints import validate_world_source
    with _scope(True) as session:
        first = validate_world_source(copy.deepcopy(first_source), identity=IDENTITY)
        import json
        second = validate_world_source(json.loads(json.dumps(first_source)), identity=IDENTITY)
        assert first is second
        assert session.computations.get("_validate_world_source_document") == 1


def test_world_source_result_is_shared_between_identities_that_differ_only_outside_the_scope_fields(first_source):
    from so101_demo.act.native_endpoints import validate_world_source
    audit_identity = {**IDENTITY, "attempt_id": "a", "release_epoch": 0}
    native_identity = {**IDENTITY, "lease": {"lease_issued_monotonic_s": 1.}}
    with _scope(True) as session:
        assert validate_world_source(first_source, identity=audit_identity) is validate_world_source(
            first_source, identity=native_identity)
        assert session.computations.get("_validate_world_source_document") == 1
        for identity in ({}, {"session_id": "alignment-session"}, {"reset_epoch": 1}, None, 5):
            assert outcome(validate_world_source, first_source, identity=identity) == outcome(
                reference_validate_world_source, first_source, identity=identity)
        broken = copy.deepcopy(first_source)
        broken["kind"] = "OTHER"
        for identity in ({}, {"reset_epoch": 1}, None):  # a refusal of the document comes before the identity is read
            assert outcome(validate_world_source, broken, identity=identity) == outcome(
                reference_validate_world_source, broken, identity=identity)


# ---- (4) source_model_data: vector comparisons and a reused MjData ------------------------------------------------------------

def reference_source_model_data(model, world, scene):
    """Check original World pose/twist against copied frozen-model coordinates."""
    import mujoco
    import math
    import numpy as np
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, world.object_state.body)
    if world.object_state.body != "plastic_cup" or body < 0 or body != world.object_state.body_id:
        raise ValueError("SOURCE_ALIGNMENT_PHYSICS_BODY_INVALID")
    data = mujoco.MjData(model)
    data.qpos[:] = scene["qpos"]
    data.qvel[:] = scene["qvel"]
    mujoco.mj_forward(model, data)
    pose = [*map(float, data.xpos[body]), *map(float, data.xquat[body][[1, 2, 3, 0]])]
    actual = [*world.object_state.position_world, *world.object_state.orientation_xyzw]
    if (not all(math.isclose(a, b, abs_tol=1e-9, rel_tol=0) for a, b in zip(pose[:3], actual[:3]))
            or not any(all(math.isclose(a, sign * b, abs_tol=1e-9, rel_tol=0)
                          for a, b in zip(pose[3:], actual[3:])) for sign in (1, -1))):
        raise ValueError("SOURCE_ALIGNMENT_SOURCE_POSE_INVALID")
    velocity = np.zeros(6)
    mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_BODY, body, velocity, 0)
    if not all(math.isclose(a, b, abs_tol=1e-9, rel_tol=0) for a, b in zip(
            velocity, (*world.object_state.angular_velocity_world, *world.object_state.linear_velocity_world))):
        raise ValueError("SOURCE_ALIGNMENT_SOURCE_TWIST_INVALID")
    return data




def _source_inputs(frozen_scene):
    from so101_demo.act.scene_association import _world
    from test_act_scene_association import association
    document, _raw = association(frozen_scene)
    source = document["source"]
    return _world(source["physics"]), copy.deepcopy(source["scene_state"])


def _with_state(world, **changes):
    """The world with changed object-state fields. `ObjectState` itself refuses non-finite or mis-sized vectors, so those cases are
    stand-ins that carry the same attributes: `source_model_data` only reads them."""
    from dataclasses import asdict, replace
    from types import SimpleNamespace
    try:
        return replace(world, object_state=replace(world.object_state, **changes))
    except (TypeError, ValueError):
        return SimpleNamespace(object_state=SimpleNamespace(**{**asdict(world.object_state), **changes}))


def _model_cases(world):
    state = world.object_state
    position, orientation = list(state.position_world), list(state.orientation_xyzw)
    linear, angular = list(state.linear_velocity_world), list(state.angular_velocity_world)
    nan, inf = float("nan"), float("inf")

    def moved(index, delta):
        return tuple(value + delta if i == index else value for i, value in enumerate(position))

    cases = {"valid": world}
    for index in range(3):
        for name, delta in (("at_tolerance", 1e-9), ("just_inside", 0.9e-9), ("just_outside", 1.1e-9), ("far", 1e-3), ("negative_outside", -2e-9)):
            cases[f"position{index}_{name}"] = _with_state(world, position_world=moved(index, delta))
    cases["position_nan"] = _with_state(world, position_world=(nan, position[1], position[2]))
    cases["position_inf"] = _with_state(world, position_world=(inf, position[1], position[2]))
    cases["position_ints"] = _with_state(world, position_world=tuple(int(value) for value in position))
    cases["position_short"] = _with_state(world, position_world=tuple(position[:2]))
    cases["position_long"] = _with_state(world, position_world=(*position, 0.))
    cases["orientation_flipped"] = _with_state(world, orientation_xyzw=tuple(-value for value in orientation))
    cases["orientation_half_flipped"] = _with_state(world, orientation_xyzw=(-orientation[0], -orientation[1], orientation[2], orientation[3]))
    cases["orientation_flipped_off"] = _with_state(world, orientation_xyzw=tuple(-value + (2e-9 if i == 3 else 0.) for i, value in enumerate(orientation)))
    cases["orientation_flipped_edge"] = _with_state(world, orientation_xyzw=tuple(-value + (1e-9 if i == 3 else 0.) for i, value in enumerate(orientation)))
    cases["orientation_off"] = _with_state(world, orientation_xyzw=(orientation[0] + 1e-6, *orientation[1:]))
    cases["orientation_nan"] = _with_state(world, orientation_xyzw=(nan, *orientation[1:]))
    cases["orientation_inf"] = _with_state(world, orientation_xyzw=(inf, *orientation[1:]))
    cases["orientation_short"] = _with_state(world, orientation_xyzw=tuple(orientation[:3]))
    cases["orientation_ints"] = _with_state(world, orientation_xyzw=(0, 0, 0, 1))
    for index in range(3):
        cases[f"linear{index}_far"] = _with_state(world, linear_velocity_world=tuple(v + (1e-3 if i == index else 0.) for i, v in enumerate(linear)))
        cases[f"angular{index}_far"] = _with_state(world, angular_velocity_world=tuple(v + (1e-3 if i == index else 0.) for i, v in enumerate(angular)))
        cases[f"linear{index}_edge"] = _with_state(world, linear_velocity_world=tuple(v + (1e-9 if i == index else 0.) for i, v in enumerate(linear)))
        cases[f"angular{index}_outside"] = _with_state(world, angular_velocity_world=tuple(v + (1.1e-9 if i == index else 0.) for i, v in enumerate(angular)))
    cases["linear_nan"] = _with_state(world, linear_velocity_world=(nan, 0., 0.))
    cases["angular_inf"] = _with_state(world, angular_velocity_world=(inf, 0., 0.))
    cases["linear_short"] = _with_state(world, linear_velocity_world=(0., 0.))
    cases["linear_ints"] = _with_state(world, linear_velocity_world=(0, 0, 0))
    cases["swapped_velocity"] = _with_state(world, linear_velocity_world=tuple(angular), angular_velocity_world=tuple(linear))
    cases["body_name"] = _with_state(world, body="box")
    cases["body_id"] = _with_state(world, body_id=state.body_id + 1)
    cases["body_missing"] = _with_state(world, body="nothing", body_id=-1)
    return cases


def _snapshot(data):
    import numpy as np
    return tuple(np.array(getattr(data, name)).tobytes() for name in ("qpos", "qvel", "xpos", "xquat", "cvel", "qacc"))


def test_source_model_data_agrees_with_the_reference_on_valid_and_corrupt_sources(frozen_scene):
    import mujoco
    from so101_demo.act.scene_association import source_model_data
    model = frozen_scene[2]
    world, scene = _source_inputs(frozen_scene)
    cases = _model_cases(world)
    scratch = mujoco.MjData(model)
    refused = set()
    for _ in range(2):  # the scratch data is reused across valid and refused sources, in order
        for name, candidate in cases.items():
            expected = outcome(reference_source_model_data, model, candidate, scene)
            fresh = outcome(source_model_data, model, candidate, scene)
            reused = outcome(source_model_data, model, candidate, scene, data=scratch)
            if expected[0] == "raised":
                refused.add(name)
                assert fresh == expected == reused, name
            else:
                assert fresh[0] == reused[0] == "value", name
                assert _snapshot(fresh[1]) == _snapshot(expected[1]) == _snapshot(reused[1]), name
    assert "valid" not in refused and "orientation_flipped" not in refused
    assert {"position0_just_outside", "position_nan", "orientation_half_flipped", "angular0_outside", "body_name", "body_id",
            "linear_nan", "angular_inf", "position_inf", "orientation_inf"} <= refused
    assert len(refused) > 20


def test_source_model_data_refuses_with_the_reference_reason(frozen_scene):
    from so101_demo.act.scene_association import source_model_data
    model = frozen_scene[2]
    world, scene = _source_inputs(frozen_scene)
    reasons = {}
    for name, candidate in _model_cases(world).items():
        result = outcome(reference_source_model_data, model, candidate, scene)
        if result[0] == "raised":
            reasons.setdefault(result[2], []).append(name)
            assert outcome(source_model_data, model, candidate, scene) == result
    assert set(reasons) >= {"SOURCE_ALIGNMENT_SOURCE_POSE_INVALID", "SOURCE_ALIGNMENT_SOURCE_TWIST_INVALID",
                            "SOURCE_ALIGNMENT_PHYSICS_BODY_INVALID"}


def test_source_model_data_scene_state_errors_match_the_reference(frozen_scene):
    import mujoco
    from so101_demo.act.scene_association import source_model_data
    model = frozen_scene[2]
    world, scene = _source_inputs(frozen_scene)
    scratch = mujoco.MjData(model)
    broken = {"short_qpos": {**scene, "qpos": scene["qpos"][:3]}, "missing_qvel": {k: v for k, v in scene.items() if k != "qvel"},
              "shifted": {**scene, "qpos": [value + .5 for value in scene["qpos"]]},
              "nan_qvel": {**scene, "qvel": [float("nan"), *scene["qvel"][1:]]}}
    for name, value in broken.items():
        expected = outcome(reference_source_model_data, model, world, value)
        for keywords in ({}, {"data": scratch}):
            actual = outcome(source_model_data, model, world, value, **keywords)
            assert actual[0] == expected[0], name
            if expected[0] == "raised":
                assert actual == expected, name
            else:
                assert _snapshot(actual[1]) == _snapshot(expected[1]), name
    # the reused data is not poisoned by the refusals above
    assert _snapshot(source_model_data(model, world, scene, data=scratch)) == _snapshot(reference_source_model_data(model, world, scene))


def test_source_model_checked_matches_the_reference_and_reuses_one_data(frozen_scene):
    import mujoco
    from so101_demo.act import native_endpoints
    model = frozen_scene[2]
    world, scene = _source_inputs(frozen_scene)
    cases = _model_cases(world)
    from so101_demo.act.qc_session import qc_session
    with qc_session("readback:qc"):
        for name, candidate in cases.items():
            expected = outcome(reference_source_model_data, model, candidate, scene)
            actual = outcome(native_endpoints._source_model_checked, model, candidate, scene)
            assert actual[0] == expected[0], name
            if expected[0] == "raised":
                assert actual == expected, name
    assert native_endpoints._scratch_data(model) is native_endpoints._scratch_data(model)
    assert isinstance(native_endpoints._scratch_data(model), mujoco.MjData)


# ---- (5) _decoded_pixel_sha256: the filter bytes are stripped in one pass -----------------------------------------------------

import hashlib
import struct
import zlib

def reference_decoded_pixel_sha256(path: Path) -> str:
    """Decode a lossless RGB PNG and hash its pixels exactly as the acquisition did.

    The writer stores filter-0 rows, so decoding needs only zlib; hashing the concatenated RGB bytes
    reproduces the digest the camera boundary minted over the (480, 640, 3) uint8 array.
    """

    payload = path.read_bytes()
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("EPISODE_FRAME_INVALID")
    offset, chunks, header = 8, [], None
    while offset + 8 <= len(payload):
        length = struct.unpack(">I", payload[offset:offset + 4])[0]
        kind = payload[offset + 4:offset + 8]
        body = payload[offset + 8:offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            chunks.append(body)
        elif kind == b"IEND":
            break
    if header != (640, 480, 8, 2, 0, 0, 0) or not chunks:
        raise ValueError("EPISODE_FRAME_INVALID")
    raw = zlib.decompress(b"".join(chunks))
    if len(raw) != 480 * (1 + 1920):
        raise ValueError("EPISODE_FRAME_INVALID")
    rows = []
    for row in range(480):
        start = row * (1 + 1920)
        if raw[start] != 0:
            raise ValueError("EPISODE_FRAME_INVALID")
        rows.append(raw[start + 1:start + 1 + 1920])
    return hashlib.sha256(b"".join(rows)).hexdigest()


def _png(raw, *, header=(640, 480, 8, 2, 0, 0, 0), idat_parts=1, signature=b"\x89PNG\r\n\x1a\n", end=True, trailing=b""):
    from so101_demo.act.recorder import _png_chunk
    compressed = zlib.compress(raw, level=6)
    size = max(1, len(compressed) // idat_parts)
    parts = [compressed[i:i + size] for i in range(0, len(compressed), size)] if idat_parts > 1 else [compressed]
    return (signature + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", *header))
            + b"".join(_png_chunk(b"IDAT", part) for part in parts)
            + (_png_chunk(b"IEND", b"") if end else b"") + trailing)


def _scanlines(seed, filters=None):
    import numpy as np
    rng = np.random.default_rng(seed)
    pixels = rng.integers(0, 256, size=(480, 1920), dtype=np.uint8)
    column = np.zeros((480, 1), dtype=np.uint8)
    for row, value in (filters or {}).items():
        column[row, 0] = value
    return np.concatenate([column, pixels], axis=1).tobytes()


def _png_cases():
    valid = _scanlines(1)
    flat = bytes(480 * 1921)
    return {
        "valid": _png(valid), "valid_many_idat": _png(valid, idat_parts=5), "flat": _png(flat),
        "valid_trailing": _png(valid, trailing=b"junk"), "no_iend": _png(valid, end=False),
        "filter_first_row": _png(_scanlines(2, {0: 1})), "filter_middle_row": _png(_scanlines(3, {240: 4})),
        "filter_last_row": _png(_scanlines(4, {479: 255})), "filter_many_rows": _png(_scanlines(5, {7: 1, 99: 2, 300: 3})),
        "signature": _png(valid, signature=b"\x89PNG\r\n\x1a\x0b"), "empty": b"",
        "short_raw": _png(valid[:-1]), "long_raw": _png(valid + b"\x00"), "empty_raw": _png(b""),
        "header_width": _png(valid, header=(641, 480, 8, 2, 0, 0, 0)), "header_depth": _png(valid, header=(640, 480, 16, 2, 0, 0, 0)),
        "header_color": _png(valid, header=(640, 480, 8, 6, 0, 0, 0)), "header_interlace": _png(valid, header=(640, 480, 8, 2, 0, 0, 1)),
        "no_idat": _png(valid)[:8] + _png(valid)[8:33] + _png(valid)[-12:],
        "no_ihdr": _png(valid)[:8] + _png(valid)[33:],
        "truncated_zlib": _png(valid)[:200],
        "short_signature_only": b"\x89PNG\r\n\x1a\n",
    }


def test_decoded_pixel_digest_agrees_with_the_reference(tmp_path):
    from so101_demo.act.recorder import _decoded_pixel_sha256
    cases = _png_cases()
    refused = []
    for name, payload in cases.items():
        path = tmp_path / f"{name}.png"
        path.write_bytes(payload)
        expected = outcome(reference_decoded_pixel_sha256, path)
        assert outcome(_decoded_pixel_sha256, path) == expected, name
        if expected[0] == "raised":
            refused.append(name)
    assert outcome(_decoded_pixel_sha256, tmp_path / "valid.png")[0] == "value"
    assert outcome(_decoded_pixel_sha256, tmp_path / "valid_many_idat.png")[0] == "value"
    assert outcome(_decoded_pixel_sha256, tmp_path / "missing.png") == outcome(reference_decoded_pixel_sha256, tmp_path / "missing.png")
    assert {"filter_first_row", "filter_middle_row", "filter_last_row", "filter_many_rows", "signature", "short_raw", "long_raw",
            "header_width", "no_idat", "truncated_zlib"} <= set(refused)
    for name in ("filter_first_row", "filter_middle_row", "filter_last_row", "filter_many_rows"):
        assert outcome(_decoded_pixel_sha256, tmp_path / f"{name}.png") == ("raised", "ValueError", "EPISODE_FRAME_INVALID")


def test_decoded_pixel_digest_is_the_digest_of_the_original_array(tmp_path):
    import numpy as np
    from so101_demo.act.recorder import _decoded_pixel_sha256, _rgb_png
    frame = np.random.default_rng(9).integers(0, 256, size=(480, 640, 3), dtype=np.uint8)
    path = tmp_path / "frame.png"
    path.write_bytes(_rgb_png(frame))
    assert _decoded_pixel_sha256(path) == hashlib.sha256(frame.tobytes()).hexdigest() == reference_decoded_pixel_sha256(path)


# ---- (1) decode_ros: one decode and comparison per message content inside a session ------------------------------------------

def reference_decode_ros(message_type, value):
    from rosidl_runtime_py.convert import message_to_ordereddict
    from rosidl_runtime_py.set_message import set_message_fields

    from so101_demo.act.nonfinite import json_safe, restore_non_finite

    from so101_demo.act.scene_association import _ros_value, canonical
    result = message_type()
    try:
        # a retained record keeps NaN / inf as explicit tags (canonical JSON refuses them): restore the originals first
        set_message_fields(result, _ros_value(restore_non_finite(value)))
    except (AssertionError, AttributeError, TypeError, ValueError) as error:
        raise ValueError("SOURCE_ALIGNMENT_ROS_CONTENT_INVALID") from error
    if canonical(json_safe(message_to_ordereddict(result))) != canonical(json_safe(value)):
        raise ValueError("SOURCE_ALIGNMENT_ROS_REPRESENTATION_INVALID")
    return result


def _ros_values(frozen_scene):
    """Real message contents: the association's apply and query records, a JointState with NaN efforts and a controller state."""
    from control_msgs.msg import JointTrajectoryControllerState
    from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
    from rosidl_runtime_py.convert import message_to_ordereddict
    from sensor_msgs.msg import JointState
    from so101_demo.act.nonfinite import json_safe
    from so101_demo.act.scene_association import _json
    from test_act_scene_association import association
    document, _raw = association(frozen_scene)
    apply, query = document["apply"]["record"], document["query"]["record"]
    joint = JointState(name=["a", "b"], position=[.1, .2], velocity=[], effort=[float("nan"), float("inf")])
    joint.header.stamp.sec, joint.header.stamp.nanosec = 3, 4
    state = JointTrajectoryControllerState(joint_names=["a"])
    state.reference.positions, state.reference.velocities = [.5], [.25]
    state.header.stamp.sec = 7
    return {
        "apply_request": (ApplyPlanningScene.Request, apply["request"]),
        "apply_response": (ApplyPlanningScene.Response, apply["response"]),
        "query_request": (GetPlanningScene.Request, query["request"]),
        "query_response": (GetPlanningScene.Response, query["response"]),
        "joint_state_non_finite": (JointState, json_safe(_json(json_safe(dict(message_to_ordereddict(joint)))))),
        "controller_state": (JointTrajectoryControllerState, _json(message_to_ordereddict(state))),
    }


def _decode_cases(frozen_scene):
    from so101_demo.act.scene_association import _json
    cases = dict(_ros_values(frozen_scene))
    kind, value = cases["query_response"]
    request_type, request = cases["query_request"]
    first_object = lambda v: v["scene"]["world"]["collision_objects"][0]  # noqa: E731

    def changed(source, mutate):
        copy_ = copy.deepcopy(source)
        mutate(copy_)
        return copy_

    cases.update({
        "unknown_field": (kind, changed(value, lambda v: v.__setitem__("surprise", 1))),
        "missing_field": (kind, changed(value, lambda v: v.pop("scene"))),
        "wrong_type": (kind, changed(value, lambda v: v["scene"].__setitem__("name", 5))),
        "bad_nested_type": (kind, changed(value, lambda v: first_object(v)["pose"]["position"].__setitem__("x", "text"))),
        "float_shift": (kind, changed(value, lambda v: first_object(v)["pose"]["position"].__setitem__("x", first_object(v)["pose"]["position"]["x"] + 1e-12))),
        "operation_long": (kind, changed(value, lambda v: first_object(v).__setitem__("operation", "ab"))),
        "operation_range": (kind, changed(value, lambda v: first_object(v).__setitem__("operation", "\u0100"))),
        "operation_int": (kind, changed(value, lambda v: first_object(v).__setitem__("operation", 1))),
        "operation_other": (kind, changed(value, lambda v: first_object(v).__setitem__("operation", "\x01"))),
        "extra_object": (kind, changed(value, lambda v: v["scene"]["world"]["collision_objects"].append(copy.deepcopy(first_object(v))))),
        "request_components_text": (request_type, changed(request, lambda v: v["components"].__setitem__("components", "x"))),
        "request_unknown": (request_type, changed(request, lambda v: v.__setitem__("zzz", []))),
        "tag_in_finite_field": (request_type, changed(request, lambda v: v["components"].__setitem__("components", {"__non_finite_float__": "nan"}))),
        "not_a_dict": (kind, None), "list_value": (kind, []), "string_value": (kind, "text"),
        "joint_tag_bad": (cases["joint_state_non_finite"][0], changed(cases["joint_state_non_finite"][1],
                          lambda v: v["effort"].__setitem__(0, {"__non_finite_float__": "bogus"}))),
        "joint_name_number": (cases["joint_state_non_finite"][0], changed(cases["joint_state_non_finite"][1],
                              lambda v: v.__setitem__("name", [1, 2]))),
    })
    return cases


def _message_outcome(function, message_type, value):
    from rosidl_runtime_py.convert import message_to_ordereddict
    from so101_demo.act.nonfinite import json_safe
    from so101_demo.act.scene_association import canonical
    try:
        message = function(message_type, value)
    except Exception as error:  # noqa: BLE001
        return ("raised", type(error).__name__, str(error), type(error.__cause__).__name__)
    return ("value", canonical(json_safe(message_to_ordereddict(message))), message)


@pytest.mark.parametrize("session", [False, True])
def test_decode_ros_agrees_with_the_reference(frozen_scene, session):
    from so101_demo.act.scene_association import decode_ros
    cases = _decode_cases(frozen_scene)
    raised = {}
    with _scope(session):
        for _ in range(3):  # later rounds are answered from the session
            for name, (message_type, value) in cases.items():
                expected = _message_outcome(reference_decode_ros, message_type, copy.deepcopy(value))
                actual = _message_outcome(decode_ros, message_type, copy.deepcopy(value))
                assert actual[0] == expected[0], name
                if expected[0] == "raised":
                    assert actual == expected, name
                    raised[name] = expected[2]
                else:
                    assert actual[1] == expected[1], name
                    if not name.startswith("joint_"):  # their efforts hold NaN, which never equals NaN
                        assert actual[2] == expected[2], name  # message equality, not only its dictionary form
    assert raised["unknown_field"] == "SOURCE_ALIGNMENT_ROS_CONTENT_INVALID"
    assert {"unknown_field", "wrong_type", "bad_nested_type", "operation_long", "not_a_dict", "joint_tag_bad"} <= set(raised)
    assert "SOURCE_ALIGNMENT_ROS_REPRESENTATION_INVALID" in raised.values()
    assert not {"apply_request", "apply_response", "query_request", "query_response", "joint_state_non_finite",
                "controller_state"} & set(raised)


def test_decode_ros_is_decoded_once_per_content_inside_a_session(frozen_scene):
    import json
    from so101_demo.act.scene_association import decode_ros
    message_type, value = _decode_cases(frozen_scene)["query_response"]
    with _scope(True) as session:
        first = decode_ros(message_type, value)
        second = decode_ros(message_type, json.loads(json.dumps(value)))  # equal content, another parse
        third = decode_ros(message_type, copy.deepcopy(value))
        assert session.computations.get("decode_ros") == 1
        assert first is second is third
        # a different content is its own entry
        other = copy.deepcopy(value)
        other["scene"]["name"] = "elsewhere"
        assert decode_ros(message_type, other).scene.name == "elsewhere"
        assert decode_ros(message_type, value).scene.name == first.scene.name != "elsewhere"
        assert session.computations.get("decode_ros") == 2
    # outside a session every call decodes afresh
    assert decode_ros(message_type, value) is not decode_ros(message_type, value)


def test_session_readers_do_not_change_the_messages_they_decode(frozen_scene):
    """The shared message is only sound while its readers leave it alone: run the readers that take it and compare it afterwards."""
    from rosidl_runtime_py.convert import message_to_ordereddict
    from so101_demo.act.scene_association import canonical, decode_ros, verify_scene_association
    from so101_demo.act.nonfinite import json_safe
    from test_act_scene_association import association
    document, raw = association(frozen_scene)
    with _scope(True):
        from moveit_msgs.srv import GetPlanningScene
        response = decode_ros(GetPlanningScene.Response, document["query"]["record"]["response"])
        before = canonical(json_safe(message_to_ordereddict(response)))
        assert verify_scene_association(document, inputs=frozen_scene[1],
            identity={"session_id": "alignment-session", "reset_epoch": 1}, raw_steps=raw).success
        assert canonical(json_safe(message_to_ordereddict(response))) == before
        assert decode_ros(GetPlanningScene.Response, document["query"]["record"]["response"]) is response


def test_decode_ros_does_not_remember_a_refusal_or_mix_int_and_float(frozen_scene):
    from so101_demo.act.scene_association import decode_ros
    cases = _decode_cases(frozen_scene)
    message_type, value = cases["query_response"]
    bad = copy.deepcopy(value)
    bad["surprise"] = 1
    with _scope(True) as session:
        for _ in range(2):
            assert outcome(decode_ros, message_type, bad)[1] == "ValueError"
        assert "decode_ros" not in session.computations
        stamp_type, stamp = cases["controller_state"]
        as_int, as_float = copy.deepcopy(stamp), copy.deepcopy(stamp)
        as_int["header"]["stamp"]["sec"] = 7
        as_float["header"]["stamp"]["sec"] = 7.0
        assert decode_ros(stamp_type, as_int).header.stamp.sec == 7
        assert outcome(decode_ros, stamp_type, as_float) == outcome(reference_decode_ros, stamp_type, as_float)


# ---- (2) verify_raw_chunk: the record's own checks run once, the argument checks every time ---------------------------------

def reference_verify_raw_chunk(record, *, previous=None, session_id=None, reset_epoch=None,
                     nq=None, nv=None, max_samples=None, max_contacts=None, previous_verified=False):
    """Recompute source type, scope, loss, clocks and .002 s continuity from raw values.

    The first retained chunk may start after reset. Complete episode coverage must
    separately bind its actual first/last steps to reset/command/stop boundaries.

    `previous` is verified first, as a record on its own, unless the caller states `previous_verified`: a loop that has just
    verified `previous` with these very arguments as the current record of its previous pass (and so would have stopped on a
    defect) says so, and the chunk is not checked a second time.
    """
    from so101_demo.act.raw_physics_chunks import (_CHUNK, _CONTACT, _CONTACT_LISTS, _ENVELOPE, _FORCES, _STEP, _exact, _integer,
                                                   _number, _numbers, _vector, _xyz)
    import math
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
        _integer(chunk[name])     # publish-path instrumentation: telemetry, never a rule
    if chunk["evidence_loss"] is not False or _integer(chunk["failed_publish_attempts"]) != 0:
        raise ValueError("PHYSICS_RAW_SOURCE_LOSS")
    samples = chunk["samples"]
    if not isinstance(samples, list) or not samples:
        raise ValueError("PHYSICS_RAW_SAMPLES_INVALID")
    if max_samples is not None and len(samples) > max_samples:
        raise ValueError("PHYSICS_RAW_PRODUCER_BOUNDS_INVALID")
    prior = None
    if previous is not None:
        if not previous_verified:
            reference_verify_raw_chunk(previous, session_id=session_id, reset_epoch=reset_epoch, nq=nq, nv=nv,
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


SESSION = "alignment-session"


def _chunk_pair(frozen_scene, per_chunk=3):
    from test_act_scene_association import association
    _document, raw = association(frozen_scene)
    template = raw[0]
    contact = {"body1_id": 1, "geom1_id": 2, "body1": "a", "geom1": "b", "body2_id": 3, "geom2_id": 4, "body2": "c", "geom2": "d",
               "position_world": {"x": 0., "y": 0., "z": 0.}, "normal_world": {"x": 0., "y": 0., "z": 1.},
               "signed_distance_m": -.001, "normal_force_n": 1.5}
    step, chunks = 1, []
    for sequence in (1, 2):
        samples = []
        for _ in range(per_chunk):
            sample = copy.deepcopy(template)
            sample["physics_step"] = step
            sample["simulation_time_s"] = step * .002
            sample["clock_interval_begin_monotonic_ns"] = 1000 + step * 10
            sample["clock_interval_end_monotonic_ns"] = 1000 + step * 10 + 5
            sample["other_object_contacts"] = [copy.deepcopy(contact)]
            samples.append(sample)
            step += 1
        chunks.append({"schema_version": 1, "received_monotonic_ns": 10 ** 6 * sequence, "chunk": {
            "chunk_sequence": sequence, "simulation_session_id": SESSION, "reset_epoch": 1,
            "first_physics_step": samples[0]["physics_step"], "last_physics_step": samples[-1]["physics_step"],
            "first_simulation_time_s": samples[0]["simulation_time_s"], "last_simulation_time_s": samples[-1]["simulation_time_s"],
            "failed_publish_attempts": 0, "handoff_monotonic_ns": 0, "publish_monotonic_ns": 0, "publish_deferrals_total": 0,
            "evidence_loss": False, "samples": samples}})
    return chunks


def _sample_edit(index, mutate):
    def edit(chunk):
        mutate(chunk["chunk"]["samples"][index])
    return edit


def _chunk_edit(mutate):
    return lambda chunk: mutate(chunk["chunk"])


def _record_edit(mutate):
    return lambda chunk: mutate(chunk)


def _put(key, value):
    return lambda target: target.__setitem__(key, value)


def _drop(key):
    return lambda target: target.pop(key)


def _put_in(outer, key, value):
    return lambda target: target[outer].__setitem__(key, value)


RAW_MUTATIONS = {
    "none": lambda chunk: None,
    "envelope_extra": _record_edit(_put("surprise", 1)), "version": _record_edit(_put("schema_version", 2)),
    "version_bool": _record_edit(_put("schema_version", True)), "receipt_zero": _record_edit(_put("received_monotonic_ns", 0)),
    "receipt_early": _record_edit(_put("received_monotonic_ns", 1500)), "receipt_float": _record_edit(_put("received_monotonic_ns", 2e6)),
    "chunk_missing": _chunk_edit(_drop("handoff_monotonic_ns")), "session_empty": _chunk_edit(_put("simulation_session_id", "")),
    "session_int": _chunk_edit(_put("simulation_session_id", 5)), "epoch_bool": _chunk_edit(_put("reset_epoch", True)),
    "sequence_negative": _chunk_edit(_put("chunk_sequence", -1)), "telemetry_str": _chunk_edit(_put("publish_deferrals_total", "x")),
    "loss": _chunk_edit(_put("evidence_loss", True)), "failed_publish": _chunk_edit(_put("failed_publish_attempts", 1)),
    "samples_empty": _chunk_edit(_put("samples", [])), "samples_tuple": _chunk_edit(lambda c: c.__setitem__("samples", tuple(c["samples"]))),
    "first_step": _chunk_edit(_put("first_physics_step", 99)), "last_step": _chunk_edit(_put("last_physics_step", 99)),
    "first_time": _chunk_edit(_put("first_simulation_time_s", 9.)), "last_time_nan": _chunk_edit(_put("last_simulation_time_s", float("nan"))),
    "sample_extra": _sample_edit(1, _put("surprise", 1)), "sample_missing": _sample_edit(0, _drop("has_contact")),
    "sample_scope": _sample_edit(1, _put("simulation_session_id", "other")), "sample_epoch": _sample_edit(2, _put("reset_epoch", 2)),
    "step_zero": _sample_edit(0, _put("physics_step", 0)), "step_gap": _sample_edit(1, lambda s: s.__setitem__("physics_step", s["physics_step"] + 1)),
    "time_negative": _sample_edit(0, _put("simulation_time_s", -1.)), "time_gap": _sample_edit(2, lambda s: s.__setitem__("simulation_time_s", s["simulation_time_s"] + .001)),
    "time_inf": _sample_edit(1, _put("simulation_time_s", float("inf"))),
    "begin_zero": _sample_edit(0, _put("clock_interval_begin_monotonic_ns", 0)), "begin_after_end": _sample_edit(1, lambda s: s.__setitem__("clock_interval_begin_monotonic_ns", s["clock_interval_end_monotonic_ns"] + 1)),
    "end_after_receipt": _sample_edit(2, _put("clock_interval_end_monotonic_ns", 10 ** 9)), "clock_overlap": _sample_edit(1, lambda s: s.__setitem__("clock_interval_begin_monotonic_ns", 1)),
    "qpos_empty": _sample_edit(0, _put("model_qpos", [])), "qpos_short": _sample_edit(1, lambda s: s["model_qpos"].pop()),
    "qpos_nan": _sample_edit(0, lambda s: s["model_qpos"].__setitem__(0, float("nan"))), "qpos_bool": _sample_edit(2, lambda s: s["model_qpos"].__setitem__(1, True)),
    "qvel_long": _sample_edit(0, lambda s: s["model_qvel"].append(0.)), "qvel_str": _sample_edit(1, lambda s: s["model_qvel"].__setitem__(0, "x")),
    "pose_extra": _sample_edit(0, lambda s: s["object_pose_world"].__setitem__("extra", 1)), "position_inf": _sample_edit(1, lambda s: s["object_pose_world"]["position"].__setitem__("x", float("inf"))),
    "quaternion": _sample_edit(0, lambda s: s["object_pose_world"]["orientation"].__setitem__("w", 2.)), "quaternion_nan": _sample_edit(2, lambda s: s["object_pose_world"]["orientation"].__setitem__("x", float("nan"))),
    "twist_missing": _sample_edit(1, lambda s: s["object_twist_world"].pop("linear")), "twist_str": _sample_edit(0, lambda s: s["object_twist_world"]["angular"].__setitem__("z", "x")),
    "net_force_nan": _sample_edit(2, lambda s: s["net_contact_force_world_n"].__setitem__("y", float("nan"))),
    "truncated": _sample_edit(0, _put("truncated", True)), "hazard": _sample_edit(1, _put("diagnostic_hazard_breached", True)),
    "flag_int": _sample_edit(0, _put("has_contact", 1)), "shadow_flag": _sample_edit(2, _put("static_shadow_crossed", None)),
    "force_negative": _sample_edit(0, _put("total_normal_force_n", -1.)), "force_bool": _sample_edit(1, _put("maximum_normal_force_n", True)),
    "contacts_tuple": _sample_edit(0, lambda s: s.__setitem__("left_fingertip_contacts", ())),
    "contact_extra": _sample_edit(1, lambda s: s["other_object_contacts"][0].__setitem__("extra", 1)),
    "contact_id": _sample_edit(0, lambda s: s["other_object_contacts"][0].__setitem__("body1_id", 2 ** 31)),
    "contact_name": _sample_edit(2, lambda s: s["other_object_contacts"][0].__setitem__("geom2", "")),
    "contact_position": _sample_edit(1, lambda s: s["other_object_contacts"][0]["position_world"].__setitem__("x", float("nan"))),
    "contact_distance_nan": _sample_edit(0, lambda s: s["other_object_contacts"][0].__setitem__("signed_distance_m", float("nan"))),
    "contact_force_negative": _sample_edit(2, lambda s: s["other_object_contacts"][0].__setitem__("normal_force_n", -.5)),
    "many_contacts": _sample_edit(1, lambda s: s["other_object_contacts"].extend(copy.deepcopy(s["other_object_contacts"][0]) for _ in range(5))),
    "not_a_dict": lambda chunk: None,
}

RAW_ARGUMENTS = {
    "standalone": lambda first, second: dict(),
    "full": lambda first, second: dict(previous=first, previous_verified=True, session_id=SESSION, reset_epoch=1, nq=14, nv=13,
                                       max_samples=50, max_contacts=128),
    "full_unverified_previous": lambda first, second: dict(previous=first, session_id=SESSION, reset_epoch=1, nq=14, nv=13,
                                                           max_samples=50, max_contacts=128),
    "first_chunk_scope": lambda first, second: dict(session_id=SESSION, reset_epoch=1, nq=14, nv=13, max_samples=50, max_contacts=128),
    "scope_session": lambda first, second: dict(session_id="other", reset_epoch=1),
    "scope_epoch": lambda first, second: dict(session_id=SESSION, reset_epoch=2),
    "nq_wrong": lambda first, second: dict(nq=15), "nv_wrong": lambda first, second: dict(nv=12), "nq_zero": lambda first, second: dict(nq=0),
    "nq_bool": lambda first, second: dict(nq=True), "dims_both_wrong": lambda first, second: dict(nq=15, nv=12),
    "max_samples_small": lambda first, second: dict(max_samples=2), "max_samples_zero": lambda first, second: dict(max_samples=0),
    "max_contacts_small": lambda first, second: dict(max_contacts=1), "max_contacts_negative": lambda first, second: dict(max_contacts=-1),
    "previous_only": lambda first, second: dict(previous=first, previous_verified=True),
    "previous_unverified": lambda first, second: dict(previous=first),
    "previous_wrong_dims": lambda first, second: dict(previous=first, previous_verified=True, nq=15),
    "previous_itself": lambda first, second: dict(previous=second, previous_verified=True),
    "previous_malformed": lambda first, second: dict(previous={"chunk": {}}, previous_verified=True),
    "previous_no_chunk": lambda first, second: dict(previous={}, previous_verified=True),
}


def _previous_variants(first):
    variants = {"plain": first}
    gap = copy.deepcopy(first)
    gap["chunk"]["samples"][-1]["physics_step"] += 1
    variants["step_gap"] = gap
    late = copy.deepcopy(first)
    late["chunk"]["samples"][-1]["simulation_time_s"] += .001
    variants["time_gap"] = late
    sequence = copy.deepcopy(first)
    sequence["chunk"]["chunk_sequence"] = 5
    variants["sequence"] = sequence
    receipt = copy.deepcopy(first)
    receipt["received_monotonic_ns"] = 10 ** 9
    variants["receipt"] = receipt
    clock = copy.deepcopy(first)
    clock["chunk"]["samples"][-1]["clock_interval_end_monotonic_ns"] = 10 ** 5
    variants["clock"] = clock
    other = copy.deepcopy(first)
    other["chunk"]["simulation_session_id"] = "other"
    variants["scope"] = other
    return variants


def _raw_outcome(function, record, **kwargs):
    return outcome(function, record, **kwargs)


def test_raw_chunk_checks_agree_with_the_reference_in_every_order(frozen_scene):
    import itertools
    from so101_demo.act.raw_physics_chunks import verify_raw_chunk
    first, second = _chunk_pair(frozen_scene)
    refused_somewhere = set()
    names = [name for name in RAW_ARGUMENTS if name not in ("previous_itself",)]
    for mutation_name, mutate in RAW_MUTATIONS.items():
        for target_index in (0, 1):
            base = [copy.deepcopy(first), copy.deepcopy(second)]
            if mutation_name == "not_a_dict":
                base[target_index] = ["not", "a", "dict"]
            else:
                mutate(base[target_index])
            for previous_name, previous in _previous_variants(base[0]).items() if target_index == 1 else (("plain", base[0]),):
                if mutation_name != "none" and previous_name != "plain" and target_index == 1 and mutation_name not in ("sample_extra", "qpos_short", "step_gap"):
                    continue
                record = base[target_index]
                for argument_names in itertools.permutations(("standalone", "full", "scope_session", "nq_wrong", "max_contacts_small"), 3):
                    with _scope(True):
                        for argument_name in argument_names:
                            kwargs = RAW_ARGUMENTS[argument_name](previous, record)
                            if "previous" in kwargs and target_index == 0:
                                kwargs = {key: value for key, value in kwargs.items() if key not in ("previous", "previous_verified")}
                            expected = _raw_outcome(reference_verify_raw_chunk, copy.deepcopy(record), **copy.deepcopy(kwargs))
                            actual = _raw_outcome(verify_raw_chunk, record, **kwargs)
                            assert actual[0] == expected[0] and actual[1:2] == expected[1:2], (mutation_name, target_index, previous_name, argument_names, argument_name)
                            if expected[0] == "raised":
                                assert actual == expected, (mutation_name, target_index, previous_name, argument_names, argument_name)
                                refused_somewhere.add((mutation_name, expected[2]))
                            else:
                                assert actual[1] is record
    reasons = {reason for _name, reason in refused_somewhere}
    assert {"PHYSICS_RAW_SCHEMA_INVALID", "PHYSICS_RAW_VERSION_INVALID", "PHYSICS_RAW_INTEGER_INVALID", "PHYSICS_RAW_SCOPE_INVALID",
            "PHYSICS_RAW_SOURCE_LOSS", "PHYSICS_RAW_SAMPLES_INVALID", "PHYSICS_RAW_CLOCK_INVALID", "PHYSICS_RAW_CONTINUITY_INVALID",
            "PHYSICS_RAW_VECTOR_INVALID", "PHYSICS_RAW_NUMBER_INVALID", "PHYSICS_RAW_QUATERNION_INVALID",
            "PHYSICS_RAW_SOURCE_HAZARD", "PHYSICS_RAW_FLAG_INVALID", "PHYSICS_RAW_CONTACT_INVALID",
            "PHYSICS_RAW_PRODUCER_BOUNDS_INVALID", "PHYSICS_RAW_ENVELOPE_INVALID"} <= reasons, reasons


def test_raw_chunk_argument_checks_agree_after_the_record_has_passed(frozen_scene):
    """The path the speed-up opens: a record that has passed once, then asked again with every other set of arguments."""
    from so101_demo.act.raw_physics_chunks import verify_raw_chunk
    first, second = _chunk_pair(frozen_scene)
    ran = 0
    for previous_name, previous in _previous_variants(first).items():
        for name, build in RAW_ARGUMENTS.items():
            for order in ("standalone", "full"):
                with _scope(True) as session:
                    record = copy.deepcopy(second)
                    warm = {} if order == "standalone" else RAW_ARGUMENTS["full"](first, record)
                    warm_expected = _raw_outcome(reference_verify_raw_chunk, copy.deepcopy(record), **copy.deepcopy(warm))
                    warm_actual = _raw_outcome(verify_raw_chunk, record, **warm)
                    assert warm_actual[:2] == warm_expected[:2] or warm_expected[0] == "raised", (order, name)
                    kwargs = build(previous, record)
                    expected = _raw_outcome(reference_verify_raw_chunk, copy.deepcopy(record), **copy.deepcopy(kwargs))
                    actual = _raw_outcome(verify_raw_chunk, record, **kwargs)
                    assert actual[0] == expected[0], (previous_name, name, order)
                    if expected[0] == "raised":
                        assert actual == expected, (previous_name, name, order)
                    ran += 1
    assert ran >= 100


def test_raw_chunk_record_checks_are_shared_inside_a_session_only(frozen_scene):
    from so101_demo.act.raw_physics_chunks import verify_raw_chunk
    first, second = _chunk_pair(frozen_scene)
    arguments = RAW_ARGUMENTS["full"](first, second)
    with _scope(True) as session:
        verify_raw_chunk(second)
        verify_raw_chunk(second, **arguments)
        assert session.computations.get("verify_raw_chunk") == 2  # two argument sets, two memo entries
        assert any(key[0] == "raw_chunk_record_checked" for key in session.cache)
    # a record changed after it passed is not trusted by a new session
    changed = copy.deepcopy(second)
    with _scope(True):
        verify_raw_chunk(changed)
    changed["chunk"]["samples"][0]["model_qpos"][0] = float("nan")
    with _scope(True):
        with pytest.raises(ValueError, match="PHYSICS_RAW_NUMBER_INVALID"):
            verify_raw_chunk(changed, nq=14)
    # a refusal leaves nothing behind: the same record is refused again under other arguments
    broken = copy.deepcopy(second)
    broken["chunk"]["samples"][1]["model_qpos"][0] = float("nan")
    with _scope(True) as session:
        for kwargs in ({"nq": 14}, {}, {"nq": 14, "nv": 13}):
            with pytest.raises(ValueError, match="PHYSICS_RAW_NUMBER_INVALID"):
                verify_raw_chunk(broken, **kwargs)
        assert not [key for key in session.cache if key[0] == "raw_chunk_record_checked"]
