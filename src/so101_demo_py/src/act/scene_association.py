"""Versioned actual source/apply/query/readback evidence for a world cup scene."""

from __future__ import annotations

import copy
from dataclasses import asdict, fields as dataclass_fields, replace
import hashlib
import json
import math
from pathlib import Path
import uuid

from .contracts import fields, identifier, integer, sha256
from .qc_session import Identity, load_model, session_memo

KIND = "ACT_SOURCE_ALIGNMENT_SCENE_ASSOCIATION"
RULE = "frozen_geometry_from_native_step"
#: operations a document may name. `initial` has no apply: the Recorder's own read-only query of the scene BEFORE the Teacher's
#: SETUP, associated with a physics source, asserting that nothing is attached (what the worker's initial gate guarantees): schema_version 3
#: (version 2 asserted the Teacher's setup scene and is never accepted again). The others carry the Teacher's apply;
#: `world_sync` is the Teacher's SETUP apply of the full task geometry (the cup's pose is audit-only: it is the perceived one).
OPERATIONS = ("world_sync", "attach", "detach", "initial")
_FIELDS = {"kind", "schema_version", "rule", "association_id", "operation", "execution_root",
           "source", "expected", "apply", "query", "receipt"}
_CALL_FIELDS = {"schema_version", "call_id", "phase", "service", "request", "response",
                "request_monotonic_ns", "response_monotonic_ns", "error",
                "request_ros_clock", "response_ros_clock"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _json(value):
    return json.loads(canonical(value))


def _ros_value(value):
    # rosidl represents CollisionObject.operation's octet as a one-character string.
    if isinstance(value, dict):
        result = {key: _ros_value(item) for key, item in value.items()}
        if "operation" in result:
            octet = result["operation"]
            if not isinstance(octet, str) or len(octet) != 1 or ord(octet) > 255:
                raise ValueError("SOURCE_ALIGNMENT_ROS_OPERATION_INVALID")
            result["operation"] = bytes((ord(octet),))
        return result
    if isinstance(value, list):
        return [_ros_value(item) for item in value]
    return value


def decode_ros(message_type, value):
    from rosidl_runtime_py.convert import message_to_ordereddict
    from rosidl_runtime_py.set_message import set_message_fields

    from .nonfinite import json_safe, restore_non_finite

    result = message_type()
    try:
        # a retained record keeps NaN / inf as explicit tags (canonical JSON refuses them): restore the originals first
        set_message_fields(result, _ros_value(restore_non_finite(value)))
    except (AssertionError, AttributeError, TypeError, ValueError) as error:
        raise ValueError("SOURCE_ALIGNMENT_ROS_CONTENT_INVALID") from error
    if canonical(json_safe(message_to_ordereddict(result))) != canonical(json_safe(value)):
        raise ValueError("SOURCE_ALIGNMENT_ROS_REPRESENTATION_INVALID")
    return result


def _clock(value):
    fields(value, {"sim_time_ns", "begin_monotonic_ns", "end_monotonic_ns"})
    integer(value["sim_time_ns"], minimum=0)
    for key in ("begin_monotonic_ns", "end_monotonic_ns"):
        integer(value[key], minimum=1)
    if value["begin_monotonic_ns"] > value["end_monotonic_ns"]:
        raise ValueError("SOURCE_ALIGNMENT_CLOCK_INVALID")


def _call(value, service):
    fields(value, _CALL_FIELDS)
    if type(value["schema_version"]) is not int or value["schema_version"] != 2:
        raise ValueError("SOURCE_ALIGNMENT_ACTUAL_CLOCK_REQUIRED")
    identifier(value["call_id"])
    identifier(value["phase"])
    if value["service"] != service or value["error"] is not None:
        raise ValueError("SOURCE_ALIGNMENT_SERVICE_REFUSED")
    for key in ("request_monotonic_ns", "response_monotonic_ns"):
        integer(value[key], minimum=1)
    _clock(value["request_ros_clock"])
    _clock(value["response_ros_clock"])
    first, last = value["request_ros_clock"], value["response_ros_clock"]
    if not (first["end_monotonic_ns"] <= value["request_monotonic_ns"]
            <= value["response_monotonic_ns"] <= last["begin_monotonic_ns"]
            and first["sim_time_ns"] <= last["sim_time_ns"]):
        raise ValueError("SOURCE_ALIGNMENT_CLOCK_INVALID")


def association_anchor(document):
    """The call after which the scene is the one the association describes: the apply, or for `initial` the query."""
    apply = document["apply"]
    return document["query"]["record"] if apply is None else apply["record"]


def read_overlaps_apply(read, apply_record):
    """A `/get_planning_scene` call ran concurrently with a Teacher `/apply_planning_scene` call: the apply was requested before the
    read finished and finished after the read began (both on the one monotonic clock)."""
    return (apply_record["request_ros_clock"]["begin_monotonic_ns"] <= read["response_ros_clock"]["end_monotonic_ns"]
            and apply_record["response_ros_clock"]["end_monotonic_ns"] >= read["request_ros_clock"]["begin_monotonic_ns"])


def read_follows_apply_before_readback(read, association):
    """A `/get_planning_scene` call began after the association's Teacher apply finished and before the Teacher's own read-back of that
    apply began (all on the one monotonic clock). Until that read-back the association is not the governing one, yet the scene
    already is the apply's result."""
    apply = association.get("apply")
    query = association.get("query")
    if not isinstance(apply, dict) or not isinstance(query, dict):
        return False
    begin = read["request_ros_clock"]["begin_monotonic_ns"]
    return (apply["record"]["response_ros_clock"]["end_monotonic_ns"] <= begin
            < query["record"]["request_ros_clock"]["begin_monotonic_ns"])


def concurrent_apply_geometry_matches(read, read_geometry, governing_id, associations):
    """A read next to an association's apply may legitimately show the new scene before that association governs.

    True when `read` overlaps the apply of an association other than `governing_id`, or began after that apply finished and before
    the association's own read-back (`read_follows_apply_before_readback`), and `read_geometry` (canonical normalized geometry)
    is EXACTLY that association's receipt geometry. Anything else is still a mismatch."""
    for other in associations:
        if other["association_id"] == governing_id or other["apply"] is None:
            continue
        if ((read_overlaps_apply(read, association_anchor(other)) or read_follows_apply_before_readback(read, other))
                and canonical(other["receipt"]["geometry"]) == read_geometry):
            return True
    return False


def validate_scene_association(document):
    """Check the closed transport and all unique associations without trusting digests."""
    fields(document, _FIELDS)
    initial = document["operation"] == "initial"
    if (document["kind"] != KIND or type(document["schema_version"]) is not int
            or document["schema_version"] != (3 if initial else 1) or document["rule"] != RULE
            or document["operation"] not in OPERATIONS):
        raise ValueError("SOURCE_ALIGNMENT_SCHEMA_INVALID")
    root = Path(document["execution_root"])
    if not root.is_absolute() or ".." in root.parts:
        raise ValueError("SOURCE_ALIGNMENT_EXECUTION_ROOT_INVALID")
    source, expected, apply, query, receipt = (document[key] for key in
                                              ("source", "expected", "apply", "query", "receipt"))
    fields(source, {"record_id", "physics_reference", "physics", "physics_sha256",
                   "received_monotonic_ns", "scene_state", "scene_received_monotonic_ns"})
    fields(expected, {"record_id", "geometry", "sha256"})
    if initial:
        if apply is not None:
            raise ValueError("SOURCE_ALIGNMENT_SCHEMA_INVALID")
    else:
        fields(apply, {"record", "source_id", "expected_id", "expected_sha256"})
    fields(query, {"record", "apply_id"})
    fields(receipt, {"receipt_id", "query_id", "geometry", "sha256", "verification"})
    fields(source["physics_reference"], {"kind", "session_id", "reset_epoch", "simulation_step"})
    if source["physics_reference"]["kind"] != "native_physics_step":
        raise ValueError("SOURCE_ALIGNMENT_SOURCE_REFERENCE_INVALID")
    ids = (document["association_id"], source["record_id"], expected["record_id"],
           *(() if initial else (apply["record"]["call_id"],)), query["record"]["call_id"], receipt["receipt_id"])
    for value in ids:
        identifier(value)
    if len(set(ids)) != len(ids):
        raise ValueError("SOURCE_ALIGNMENT_DUPLICATE_RECORD_ID")
    for value in (source["physics_sha256"], expected["sha256"], receipt["sha256"]):
        sha256(value)
    if (digest(source["physics"]) != source["physics_sha256"]
            or digest(expected["geometry"]) != expected["sha256"]
            or digest(receipt["geometry"]) != receipt["sha256"]
            or receipt["query_id"] != query["record"]["call_id"]):
        raise ValueError("SOURCE_ALIGNMENT_INVALID")
    if initial:
        if query["apply_id"] is not None:
            raise ValueError("SOURCE_ALIGNMENT_INVALID")
    elif (apply["source_id"] != source["record_id"]
            or apply["expected_id"] != expected["record_id"]
            or apply["expected_sha256"] != expected["sha256"]
            or query["apply_id"] != apply["record"]["call_id"]):
        raise ValueError("SOURCE_ALIGNMENT_INVALID")
    _call(query["record"], "/get_planning_scene")
    if not initial:
        _call(apply["record"], "/apply_planning_scene")
        if (apply["record"]["response"] != {"success": True}
                or apply["record"]["response_ros_clock"]["end_monotonic_ns"]
                > query["record"]["request_ros_clock"]["begin_monotonic_ns"]
                or apply["record"]["response_ros_clock"]["sim_time_ns"]
                > query["record"]["request_ros_clock"]["sim_time_ns"]):
            raise ValueError("SOURCE_ALIGNMENT_APPLY_QUERY_ORDER_INVALID")
    for key in ("received_monotonic_ns", "scene_received_monotonic_ns"):
        integer(source[key], minimum=1)
    canonical(document)


@session_memo(lambda document: Identity(document), copy_result=False)
def _world(document):
    # the result is a frozen dataclass: inside a QC session one document is decoded once and the object is shared
    from ..core.simulation.types import SimulationEvidence, ObjectState, ContactEvidence
    fields(document, {field.name for field in dataclass_fields(SimulationEvidence)})
    for key in ("has_contact", "paused", "truncated"):
        if type(document[key]) is not bool:
            raise ValueError("SOURCE_ALIGNMENT_WORLD_SCALAR_INVALID")
    for key in ("simulation_time_s", "minimum_signed_distance_m", "maximum_normal_force_n"):
        if type(document[key]) not in (int, float) or not math.isfinite(document[key]):
            raise ValueError("SOURCE_ALIGNMENT_WORLD_SCALAR_INVALID")
    state = document["object_state"]
    fields(state, {field.name for field in dataclass_fields(ObjectState)})
    state = ObjectState(**{key: tuple(value) if isinstance(value, list) else value
                           for key, value in state.items()})
    groups = {}
    for key in ("left_fingertip_contacts", "right_fingertip_contacts", "other_object_contacts"):
        groups[key] = []
        for value in document[key]:
            fields(value, {field.name for field in dataclass_fields(ContactEvidence)})
            for scalar in ("signed_distance_m", "normal_force_n"):
                if type(value[scalar]) not in (int, float) or not math.isfinite(value[scalar]):
                    raise ValueError("SOURCE_ALIGNMENT_WORLD_SCALAR_INVALID")
            groups[key].append(ContactEvidence(**{name: tuple(item) if isinstance(item, list) else item
                                                  for name, item in value.items()}))
        groups[key] = tuple(groups[key])
    return SimulationEvidence(**{**document, "object_state": state, **groups})


def claim_scene_records(document, records):
    """Admit immutable record IDs and one unique transaction per actual call."""
    entries = (
        (document["association_id"], "association", document),
        (document["source"]["record_id"], "source", document["source"]),
        (document["expected"]["record_id"], "expected", document["expected"]),
        *(() if document["apply"] is None else
          ((document["apply"]["record"]["call_id"], "apply", document["apply"]["record"]),)),
        (document["query"]["record"]["call_id"], "query", document["query"]["record"]),
        (document["receipt"]["receipt_id"], "receipt", document["receipt"]),
    )
    additions = {}
    for record_id, role, value in entries:
        content = (role, canonical(value))
        if record_id in records and (role not in ("source", "expected")
                                     or records[record_id] != content):
            raise ValueError("AUDIT_SOURCE_ALIGNMENT_INVALID")
        additions[record_id] = content
    records.update(additions)


def source_geometry(base, world):
    from ..core.task_geometry import Pose7
    cup = replace(base.object("plastic_cup"), pose=Pose7.parse(
        [*world.object_state.position_world, *world.object_state.orientation_xyzw], "alignment.cup"))
    return replace(base, objects=(*base.objects[:2], cup), source={
        "session_id": world.simulation_session_id, "reset_epoch": world.reset_epoch,
        "simulation_step": world.simulation_step, "publisher_sequence": world.publisher_sequence,
        "simulation_time_s": world.simulation_time_s, "frame_id": world.frame_id,
        "cup_body": world.object_state.body})


def source_attachment_geometry(geometry, model, data):
    """Derive the cup's local shadow from the same original frozen-model FK step."""
    import mujoco
    import numpy as np
    from ..core.task_geometry import Pose7
    link = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "gripper")
    if link < 0:
        raise ValueError("SOURCE_ALIGNMENT_ATTACHMENT_LINK_INVALID")
    cup = geometry.object("plastic_cup")
    position = data.xmat[link].reshape(3, 3).T @ (np.array(cup.pose.values[:3]) - data.xpos[link])
    link_quaternion = np.zeros(4)
    mujoco.mju_mat2Quat(link_quaternion, data.xmat[link])
    inverse = link_quaternion * np.array([1., -1., -1., -1.])
    x, y, z, w = cup.pose.values[3:]
    local_quaternion = np.zeros(4)
    mujoco.mju_mulQuat(local_quaternion, inverse, np.array([w, x, y, z]))
    local_pose = Pose7.parse([*map(float, position), *map(float, local_quaternion[[1, 2, 3, 0]])], "alignment.local_cup")
    return _json({"world_geometry": asdict(geometry), "link_name": "gripper", "frame_id": "gripper",
                  "touch_links": ["gripper", "jaw"], "local_cup": asdict(replace(cup, pose=local_pose))})


def _xyz(value):
    fields(value, {"x", "y", "z"})
    return [value[key] for key in ("x", "y", "z")]


@session_memo(lambda sample, world, scene: (Identity(sample), Identity(world), Identity(scene)), copy_result=False)
def _raw_source_matches(sample, world, scene):
    state = world.object_state
    pose, twist = sample["object_pose_world"], sample["object_twist_world"]
    orientation = pose["orientation"]
    fields(orientation, {"x", "y", "z", "w"})
    if (_xyz(pose["position"]) != list(state.position_world)
            or [orientation[key] for key in ("x", "y", "z", "w")] != list(state.orientation_xyzw)
            or _xyz(twist["linear"]) != list(state.linear_velocity_world)
            or _xyz(twist["angular"]) != list(state.angular_velocity_world)
            or sample["has_contact"] != world.has_contact or sample["truncated"] != world.truncated
            or sample["maximum_normal_force_n"] != world.maximum_normal_force_n):
        return False
    begin, end = (sample["clock_interval_begin_monotonic_ns"], sample["clock_interval_end_monotonic_ns"])
    if not (type(begin) is int and type(end) is int
            and 0 < begin <= end <= scene["clock_interval_begin_monotonic_ns"]):
        return False
    for key in ("left_fingertip_contacts", "right_fingertip_contacts", "other_object_contacts"):
        contacts = []
        for contact in sample[key]:
            value = dict(contact)
            for vector in ("position_world", "normal_world"):
                value[vector] = _xyz(value[vector])
            contacts.append(value)
        if canonical(contacts) != canonical([asdict(contact) for contact in getattr(world, key)]):
            return False
    return True


def source_model_data(model, world, scene):
    """Check original World pose/twist against copied frozen-model coordinates."""
    import mujoco
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


def verify_scene_association(document, *, inputs, identity, raw_steps):
    """Authenticate frozen assets, reconstruct source geometry, and verify actual ROS contents."""
    from moveit_msgs.msg import PlanningSceneComponents
    from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
    from ..adapters.act.scene_state import SceneStateObserver
    from ..core.task_geometry import load_task_geometry
    from ..control.planning_scene.task_scene import normalized_scene_geometry, verify_task_scene
    from .execution_snapshot import verify_execution_snapshot
    from .diagnostic_episode_inputs import audit_execution_model_identity

    validate_scene_association(document)
    if not isinstance(raw_steps, (list, tuple)) or not raw_steps:
        raise ValueError("SOURCE_ALIGNMENT_NATIVE_STEP_REFERENCE_REQUIRED")
    model_identity = audit_execution_model_identity(inputs)
    if model_identity is None:
        raise ValueError("SOURCE_ALIGNMENT_FROZEN_INPUTS_REQUIRED")
    root = Path(document["execution_root"])
    snapshot = verify_execution_snapshot(root, expected_sha256=inputs["execution_snapshot"]["sha256"])
    if model_identity != {key: snapshot[key] for key in ("model_sha256", "nq", "nv", "mujoco_version")}:
        raise ValueError("SOURCE_ALIGNMENT_FROZEN_MODEL_IDENTITY_MISMATCH")
    source = document["source"]
    world = _world(source["physics"])
    reference = source["physics_reference"]
    if (reference != {"kind": "native_physics_step", "session_id": identity["session_id"],
                     "reset_epoch": identity["reset_epoch"], "simulation_step": world.simulation_step}
            or world.simulation_session_id != identity["session_id"]
            or world.reset_epoch != identity["reset_epoch"] or world.simulation_step < 1
            or world.paused or world.truncated or world.object_state.body != "plastic_cup"
            or abs(sum(value * value for value in world.object_state.orientation_xyzw) - 1) > 1e-3):
        raise ValueError("SOURCE_ALIGNMENT_PHYSICS_SOURCE_INVALID")
    scene = source["scene_state"]
    observer = SceneStateObserver(model_sha256=model_identity["model_sha256"],
        nq=model_identity["nq"], nv=model_identity["nv"], max_age_s=.1,
        monotonic=lambda: source["scene_received_monotonic_ns"] * 1e-9)
    observer.validate(scene)
    if (scene["simulation_session_id"] != world.simulation_session_id
            or scene["reset_epoch"] != world.reset_epoch or scene["simulation_step"] != world.simulation_step
            or round(scene["simulation_time_s"] * 1e9) != round(world.simulation_time_s * 1e9)
            or scene["paused"] or scene["clock_interval_begin_monotonic_ns"] > source["received_monotonic_ns"]):
        raise ValueError("SOURCE_ALIGNMENT_SCENE_SOURCE_INVALID")
    model = load_model(root / snapshot["scene_path"], root=root)
    data = source_model_data(model, world, scene)
    matches = [sample for sample in raw_steps if sample["physics_step"] == world.simulation_step]
    if (len(matches) != 1 or matches[0]["model_qpos"] != scene["qpos"]
            or matches[0]["model_qvel"] != scene["qvel"]
            or matches[0]["reset_epoch"] != world.reset_epoch
            or matches[0]["simulation_session_id"] != world.simulation_session_id
            or round(matches[0]["simulation_time_s"] * 1e9) != round(world.simulation_time_s * 1e9)
            or not _raw_source_matches(matches[0], world, scene)):
        raise ValueError("SOURCE_ALIGNMENT_NATIVE_STEP_REFERENCE_INVALID")
    initial = document["operation"] == "initial"
    apply, query = (None if initial else document["apply"]["record"]), document["query"]["record"]
    # The source must precede the first call that could have made the scene what it is: the Teacher's apply, or for the
    # initial association the read-only query itself.
    anchor = association_anchor(document)
    source_time = round(world.simulation_time_s * 1e9)
    request_clock = anchor["request_ros_clock"]
    if (not 0 <= request_clock["sim_time_ns"] - source_time <= 100000000
            or scene["clock_interval_end_monotonic_ns"] > request_clock["begin_monotonic_ns"]
            or source["received_monotonic_ns"] > anchor["request_monotonic_ns"]
            or source["scene_received_monotonic_ns"] > anchor["request_monotonic_ns"]
            or anchor["request_monotonic_ns"] - min(matches[0]["clock_interval_begin_monotonic_ns"],
                 scene["clock_interval_begin_monotonic_ns"],
                 source["received_monotonic_ns"], source["scene_received_monotonic_ns"]) > 100000000):
        raise ValueError("SOURCE_ALIGNMENT_SOURCE_CLOCK_MAPPING_INVALID")
    expected = source_geometry(load_task_geometry(root / "assets/common/geometry-manifest.yaml"), world)
    attachment = source_attachment_geometry(expected, model, data) if document["operation"] == "attach" else None
    from ..control.planning_scene.task_scene import PRE_SETUP_EXPECTATION, verify_pre_setup_scene
    expected_record = (PRE_SETUP_EXPECTATION if initial else attachment if attachment is not None else asdict(expected))
    if canonical(expected_record) != canonical(document["expected"]["geometry"]):
        raise ValueError("SOURCE_ALIGNMENT_FROZEN_GEOMETRY_MISMATCH")
    request = None
    if not initial:
        request = decode_ros(ApplyPlanningScene.Request, apply["request"])
        decode_ros(ApplyPlanningScene.Response, apply["response"])
    query_request = decode_ros(GetPlanningScene.Request, query["request"])
    required = (PlanningSceneComponents.WORLD_OBJECT_NAMES | PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
                | PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS | PlanningSceneComponents.OBJECT_COLORS)
    if query_request.components.components & required != required:
        raise ValueError("SOURCE_ALIGNMENT_QUERY_COMPONENTS_INVALID")
    response = decode_ros(GetPlanningScene.Response, query["response"])
    if initial:
        verification = verify_pre_setup_scene(response.scene)
    elif document["operation"] == "world_sync":
        # The Teacher's SETUP writes the PERCEIVED cup pose: its delta against the physics-derived pose is recorded, membership,
        # frame, primitives, colours and every other object stay strict.
        verification = verify_task_scene(response.scene, expected, cup_world_pose_audit_only=True)
    elif attachment is None:
        verification = verify_task_scene(response.scene, expected)
    else:
        from ..core.task_geometry import Pose7
        # The Teacher's request is the plain attach, which applies no cup geometry: membership, link, touch links and
        # frame are strict and the cup's local pose delta against the source-derived pose is recorded, not required.
        verification = verify_task_scene(response.scene, expected, expected_cup_attachment=attachment["link_name"],
            expected_cup_local_pose=Pose7.parse(attachment["local_cup"]["pose"]["values"], "alignment.local"),
            expected_touch_links=tuple(attachment["touch_links"]), cup_local_pose_audit_only=True)
    if (not verification.success or document["receipt"]["verification"] != _json(asdict(verification))
            or document["receipt"]["geometry"] != _json(normalized_scene_geometry(response.scene))):
        raise ValueError("SOURCE_ALIGNMENT_ACTUAL_GEOMETRY_MISMATCH")
    if initial:
        return verification
    observed_request = _json(normalized_scene_geometry(request.scene))
    # A successful query cannot conceal an unrelated apply. Check the original requested
    # cup contents, full fixed geometry when applied, and explicit detach operation.
    from ..control.planning_scene.task_scene import make_task_scene
    wanted = normalized_scene_geometry(make_task_scene(expected))
    if document["operation"] == "world_sync":
        # exactly `make_task_scene` of the frozen geometry with the cup at the pose the request itself carries
        from ..application.dynamic_scene_sync import geometry_with_cup_pose
        from ..core.task_geometry import Pose7
        cups = [item for item in request.scene.world.collision_objects if item.id == "plastic_cup"]
        if len(cups) != 1:
            raise ValueError("SOURCE_ALIGNMENT_APPLY_GEOMETRY_MISMATCH")
        pose = Pose7.parse([cups[0].pose.position.x, cups[0].pose.position.y, cups[0].pose.position.z,
                            cups[0].pose.orientation.x, cups[0].pose.orientation.y, cups[0].pose.orientation.z,
                            cups[0].pose.orientation.w], "alignment.request")
        synced = geometry_with_cup_pose(expected, pose)
        # colours are float32 on the wire: both sides are compared as they travel (a CDR round trip)
        from rclpy.serialization import deserialize_message, serialize_message

        def travelled(message):
            return deserialize_message(serialize_message(message), type(message))

        wanted_request = travelled(ApplyPlanningScene.Request(scene=make_task_scene(synced)))
        if (_json(normalized_scene_geometry(travelled(request).scene))
                != _json(normalized_scene_geometry(wanted_request.scene))):
            raise ValueError("SOURCE_ALIGNMENT_APPLY_GEOMETRY_MISMATCH")
        request = travelled(request)
    elif document["operation"] == "attach":
        # The Teacher's request is always the plain attach (no geometry); the verification above already proved the
        # observed attached geometry against the source-derived local pose.
        from ..control.planning_scene.task_scene import make_plain_attach_scene
        wanted_request = ApplyPlanningScene.Request(scene=make_plain_attach_scene())
    else:
        cup = next(item for item in wanted["world"] if item["id"] == "plastic_cup")
        if (observed_request["world"] != [cup] or observed_request["colors"]
                or len(request.scene.robot_state.attached_collision_objects) != 1):
            raise ValueError("SOURCE_ALIGNMENT_APPLY_GEOMETRY_MISMATCH")
        removal = request.scene.robot_state.attached_collision_objects[0]
        if (removal.object.id != "plastic_cup" or removal.object.operation != b"\x01"
                or removal.object.primitives or removal.object.meshes or removal.object.planes):
            raise ValueError("SOURCE_ALIGNMENT_DETACH_OPERATION_INVALID")
        from moveit_msgs.msg import AttachedCollisionObject, CollisionObject, PlanningScene
        from ..control.planning_scene.task_scene import _collision_object
        removal = AttachedCollisionObject()
        removal.object.id = "plastic_cup"
        removal.object.operation = CollisionObject.REMOVE
        wanted_scene = PlanningScene()
        wanted_scene.is_diff = True
        wanted_scene.robot_state.is_diff = True
        wanted_scene.robot_state.attached_collision_objects = [removal]
        wanted_scene.world.collision_objects = [_collision_object(expected.object("plastic_cup"), expected.frame_id)]
        wanted_request = ApplyPlanningScene.Request(scene=wanted_scene)
    from rosidl_runtime_py.convert import message_to_ordereddict
    recorded = apply["request"]
    if document["operation"] == "world_sync":
        recorded = message_to_ordereddict(request)
    if canonical(message_to_ordereddict(wanted_request)) != canonical(recorded):
        raise ValueError("SOURCE_ALIGNMENT_APPLY_REQUEST_INVALID")
    return verification


def make_scene_association(*, execution_root, source, scene_state, received_monotonic_ns,
                           scene_received_monotonic_ns, geometry, apply_call, query_call,
                           verification, operation):
    """Copy actual records into one immutable, uniquely linked audit value."""
    source_id, expected_id, receipt_id = (str(uuid.uuid4()) for _ in range(3))
    physics, expected, observed = (_json(asdict(source)),
        _json(geometry if isinstance(geometry, dict) else asdict(geometry)), _json(verification.evidence["observed_geometry"]))
    return _json({"kind": KIND, "schema_version": 3 if operation == "initial" else 1, "rule": RULE,
        "association_id": str(uuid.uuid4()), "operation": operation,
        "execution_root": str(Path(execution_root).absolute()),
        "source": {"record_id": source_id, "physics_reference": {"kind": "native_physics_step",
            "session_id": source.simulation_session_id, "reset_epoch": source.reset_epoch,
            "simulation_step": source.simulation_step}, "physics": physics,
            "physics_sha256": digest(physics), "received_monotonic_ns": received_monotonic_ns,
            "scene_state": copy.deepcopy(scene_state), "scene_received_monotonic_ns": scene_received_monotonic_ns},
        "expected": {"record_id": expected_id, "geometry": expected, "sha256": digest(expected)},
        "apply": None if apply_call is None else {"record": copy.deepcopy(apply_call), "source_id": source_id,
            "expected_id": expected_id, "expected_sha256": digest(expected)},
        "query": {"record": copy.deepcopy(query_call), "apply_id": None if apply_call is None else apply_call["call_id"]},
        "receipt": {"receipt_id": receipt_id, "query_id": query_call["call_id"],
            "geometry": observed, "sha256": digest(observed), "verification": asdict(verification)}})
