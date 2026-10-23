"""The Teacher's own Planning Scene calls, as `scene_operation` events for the Recorder (Phase A4b).

Every Apply/GetPlanningScene call the Teacher makes is offered to the Teacher event stream (see
`act/teacher_event_stream.py`): the operation kind, the call id, the request and response as CDR (base64) with their
sha256, the simulation and monotonic request/response times and the outcome. The Recorder rebuilds the exact call record
from it and derives the source alignment scene association from the Teacher's real apply and read-back, never by writing the scene
itself. Everything here is bounded and non-blocking: an over-size CDR is replaced by its digest and marked, so the Recorder
knows the data cannot be complete (INVALID), and nothing here can raise into the Teacher.
"""

from __future__ import annotations

import base64
import hashlib

#: bound of one CDR blob in an event; larger values travel as a digest only and make the Recorder's data INVALID
MAX_CDR_BYTES = 262144
EVENT_TYPE = "scene_operation"
SERVICES = ("/apply_planning_scene", "/get_planning_scene")
_PAYLOAD_KEYS = frozenset({
    "operation", "state", "call_id", "phase", "service", "schema_version", "request_cdr_base64", "request_cdr_sha256",
    "response_cdr_base64", "response_cdr_sha256", "oversize", "request_ros_clock", "response_ros_clock",
    "request_monotonic_ns", "response_monotonic_ns", "success", "error", "source"})


class SceneOperationError(ValueError):
    """A scene_operation payload the Recorder cannot use; the message is a stable code."""


def operation_kind(phase: str, state: str | None) -> str:
    """The Teacher's operation kind for a call: attach, detach, sync_world_object, or the call's own phase."""

    if phase == "DYNAMIC_ATTACH":
        return "attach"
    if phase == "DYNAMIC_DETACH_SYNC":
        if state in ("SYNC_WORLD_OBJECT", "RECOVER_SYNC_WORLD_OBJECT"):
            return "sync_world_object"
        return "detach"
    return {"DYNAMIC_SCENE_READBACK": "readback", "DYNAMIC_ACM_READBACK": "acm_readback",
            "DYNAMIC_ACM_APPLY": "acm_apply", "READ_BACK": "readback"}.get(phase, phase.lower())


def _cdr(message):
    from rclpy.serialization import serialize_message

    data = serialize_message(message)
    digest = hashlib.sha256(data).hexdigest()
    if len(data) > MAX_CDR_BYTES:
        return None, digest, True
    return base64.b64encode(data).decode("ascii"), digest, False


def scene_operation_payload(record: dict, request, response, *, state=None, source=None) -> dict:
    """The event payload of one finished Teacher scene call (`record` as `record_scene_service_call` returned it)."""

    request_b64, request_sha, request_big = _cdr(request)
    if response is None:
        response_b64, response_sha, response_big = None, None, False
    else:
        response_b64, response_sha, response_big = _cdr(response)
    success = (record.get("error") is None and response is not None
               and (record["service"] != "/apply_planning_scene" or getattr(response, "success", False) is True))
    return {
        "operation": operation_kind(record["phase"], state), "state": state, "call_id": record["call_id"],
        "phase": record["phase"], "service": record["service"], "schema_version": record["schema_version"],
        "request_cdr_base64": request_b64, "request_cdr_sha256": request_sha,
        "response_cdr_base64": response_b64, "response_cdr_sha256": response_sha,
        "oversize": bool(request_big or response_big),
        "request_ros_clock": record.get("request_ros_clock"), "response_ros_clock": record.get("response_ros_clock"),
        "request_monotonic_ns": record["request_monotonic_ns"], "response_monotonic_ns": record["response_monotonic_ns"],
        "success": bool(success), "error": record.get("error"), "source": source,
    }


def make_scene_operation_hook(stream, *, state=lambda: None, source=lambda: None):
    """`(record, request, response)` callback that offers the call to `stream`. Never blocks, never raises."""

    def hook(record, request, response):
        try:
            payload = scene_operation_payload(record, request, response, state=state(), source=source())
            stream.offer(EVENT_TYPE, payload)
        except BaseException:
            pass

    return hook


def _decoded(data_b64, sha, message_type, code):
    if data_b64 is None:
        raise SceneOperationError(code + "_OVERSIZE")
    try:
        data = base64.b64decode(data_b64, validate=True)
    except (TypeError, ValueError) as error:
        raise SceneOperationError(code + "_BASE64_INVALID") from error
    if hashlib.sha256(data).hexdigest() != sha:
        raise SceneOperationError("SCENE_OPERATION_CDR_DIGEST_MISMATCH")
    from rclpy.serialization import deserialize_message

    try:
        return deserialize_message(data, message_type)
    except Exception as error:
        raise SceneOperationError(code + "_CDR_INVALID") from error


def scene_operation_record(payload: dict) -> tuple[dict, object, object]:
    """(record, request message, response message) rebuilt from an event payload, with every digest checked.

    The record has exactly the shape `record_scene_service_call` returned in the Teacher, so the source alignment verification reads it
    unchanged. A payload that was over-size at the Teacher, whose digest does not match, or that is not a closed document
    raises `SceneOperationError`; the Recorder marks its data INVALID.
    """

    from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
    from rosidl_runtime_py.convert import message_to_ordereddict

    if type(payload) is not dict or set(payload) != _PAYLOAD_KEYS:
        raise SceneOperationError("SCENE_OPERATION_MALFORMED")
    if payload["oversize"] is not False:
        raise SceneOperationError("SCENE_OPERATION_OVERSIZE")
    if payload["service"] not in SERVICES or type(payload["call_id"]) is not str or not payload["call_id"]:
        raise SceneOperationError("SCENE_OPERATION_MALFORMED")
    apply = payload["service"] == "/apply_planning_scene"
    request_type = ApplyPlanningScene.Request if apply else GetPlanningScene.Request
    response_type = ApplyPlanningScene.Response if apply else GetPlanningScene.Response
    request = _decoded(payload["request_cdr_base64"], payload["request_cdr_sha256"], request_type, "SCENE_OPERATION_REQUEST")
    response = None
    if payload["response_cdr_sha256"] is not None or payload["response_cdr_base64"] is not None:
        response = _decoded(payload["response_cdr_base64"], payload["response_cdr_sha256"], response_type,
                            "SCENE_OPERATION_RESPONSE")
    record = {
        "schema_version": payload["schema_version"], "call_id": payload["call_id"], "phase": payload["phase"],
        "service": payload["service"], "request": dict(message_to_ordereddict(request)),
        "request_monotonic_ns": payload["request_monotonic_ns"],
        "response_monotonic_ns": payload["response_monotonic_ns"],
        "response": None if response is None else dict(message_to_ordereddict(response)),
        "error": payload["error"], "request_ros_clock": payload["request_ros_clock"],
        "response_ros_clock": payload["response_ros_clock"],
    }
    return record, request, response
