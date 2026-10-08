"""Recorder-side source alignment scene associations, derived from the Teacher's own scene operations (Phase A4b).

The data side never writes the MoveIt scene. The Teacher publishes each of its real Apply/GetPlanningScene calls as a
`scene_operation` event (`act/scene_operation.py`); this module turns those records, joined with the Recorder's own
recorded physics sources, into the same `ACT_SOURCE_ALIGNMENT_SCENE_ASSOCIATION` documents the QC readback verifies:

* `initial`  the Recorder's OWN read-only query of the scene before the Teacher's SETUP, against a physics source, no apply:
             it asserts that nothing is attached, as the worker's initial gate does (CP-3425); it does not depend on any Teacher event;
* `world_sync` the Teacher's SETUP apply of the full task geometry and its read-back; the cup's pose is the perceived one,
             so its delta against the physics-derived pose is recorded, not required, everything else is strict;
* `attach`   the Teacher's plain attach apply and its read-back; membership, link, touch links and frame are strict and
             the cup's local pose delta is recorded;
* `detach`   the Teacher's detach/sync apply (which did apply source geometry) and its read-back; geometry is strict.

Identity, causality, the 100 ms timing join and membership are strict for every operation. Every failure here only makes
the data INVALID; nothing in this module can reach the Teacher.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass

from .scene_association import (_raw_source_matches, canonical, decode_ros, make_scene_association, source_attachment_geometry,
                                source_geometry, source_model_data)
from .scene_operation import scene_operation_record

_WINDOW_NS = 100_000_000
#: Teacher scene calls that change the geometry the rows' read-backs see (an association is owed for each)
_GEOMETRY_OPERATIONS = {"attach": "attach", "detach": "detach", "sync_world_object": "detach"}


class SceneAssociationError(ValueError):
    """A Teacher scene operation that cannot be associated; the message starts with a stable code.

    `diagnostics` (data-side only) says what the source join saw when it failed.
    """

    def __init__(self, message, diagnostics=None):
        super().__init__(message)
        self.diagnostics = diagnostics


def _required_components():
    from moveit_msgs.msg import PlanningSceneComponents

    return (PlanningSceneComponents.WORLD_OBJECT_NAMES | PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
            | PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS | PlanningSceneComponents.OBJECT_COLORS)


@dataclass(frozen=True)
class AssociationJob:
    """One association the Teacher's operations owe: `apply` is None for the initial one."""

    operation: str
    apply: dict | None
    query: dict
    source_hint: dict | None
    created_monotonic_s: float


class SceneOperationTracker:
    """Ingest `scene_operation` events in order and say which associations they owe.

    A successful Teacher apply of kind attach/detach/sync_world_object is paired with the first later GetPlanningScene read
    of the full scene; the Teacher's setup apply with its read-back owes the initial association. An apply that is still
    waiting for its read-back, or an association not yet admitted, makes `pending_before` name the sim time from which rows
    must wait.
    """

    def __init__(self) -> None:
        self.records: list[dict] = []
        self._open: list[tuple[str, dict, dict | None]] = []     # (association operation, apply record, source hint)
        self.failed: list[dict] = []

    def ingest(self, payload: dict, *, now_s: float | None = None) -> list[AssociationJob]:
        record, _request, response = scene_operation_record(payload)
        now = time.monotonic() if now_s is None else now_s
        self.records.append(record)
        operation, state = payload["operation"], payload["state"]
        success = payload["success"] is True
        jobs: list[AssociationJob] = []
        if record["service"] == "/apply_planning_scene":
            if not success:
                self.failed.append(record)
            elif operation in _GEOMETRY_OPERATIONS:
                self._open.append((_GEOMETRY_OPERATIONS[operation], record, payload.get("source")))
            elif state == "SETUP" and self._writes_task_scene(record):
                # the Teacher's SETUP apply of the full task geometry (not an ACM-only apply): a world_sync alignment is owed
                self._open.append(("world_sync", record, payload.get("source")))
            return jobs
        if not success or not self._is_full_read(record):
            return jobs
        for index, (kind, apply, hint) in enumerate(self._open):
            if self._follows(apply, record):
                del self._open[index]
                jobs.append(AssociationJob(kind, apply, record, hint, now))
                break
        return jobs

    @staticmethod
    def _writes_task_scene(record) -> bool:
        from moveit_msgs.srv import ApplyPlanningScene as _TeacherApplyService   # decoded, never sent: the Recorder only reads

        try:
            request = decode_ros(_TeacherApplyService.Request, record["request"])
        except ValueError:
            return False
        return any(item.id == "plastic_cup" for item in request.scene.world.collision_objects)

    @staticmethod
    def _is_full_read(record) -> bool:
        from moveit_msgs.srv import GetPlanningScene

        try:
            request = decode_ros(GetPlanningScene.Request, record["request"])
        except ValueError:
            return False
        required = _required_components()
        return request.components.components & required == required

    @staticmethod
    def _follows(apply, query) -> bool:
        first, last = apply.get("response_ros_clock"), query.get("request_ros_clock")
        return (first is not None and last is not None
                and first["end_monotonic_ns"] <= last["begin_monotonic_ns"]
                and first["sim_time_ns"] <= last["sim_time_ns"])

    def owed_apply_sim_times(self) -> list[int]:
        """Response sim times of applies whose read-back (hence association) has not been seen yet."""
        return [apply["response_ros_clock"]["sim_time_ns"] for _, apply, _ in self._open
                if apply.get("response_ros_clock") is not None]


def select_source(*, world_records, scene_frames, raw_lookup, identity, model_sha256, anchor,
                  publisher_sequence=None):
    """The physics source that joins `anchor` (the first call that could have made the scene what it is).

    Returns (received world record, (scene frame, scene receipt s), raw record) or raises `SceneAssociationError`.
    `publisher_sequence` names the exact source the Teacher built its request from (detach); otherwise the latest
    eligible source before the call is taken. Eligibility is the QC's own timing join: the source precedes the call by at
    most 100 ms in simulation time and monotonic time, every receipt precedes the call, and the clocks are in causal order.
    """

    clock, request_ns = anchor["request_ros_clock"], anchor["request_monotonic_ns"]
    anchor_sim = clock["sim_time_ns"]
    frames = {}
    for frame, receipt in scene_frames:
        key = (frame["simulation_session_id"], frame["reset_epoch"], frame["simulation_step"])
        frames.setdefault(key, []).append((frame, receipt))
    seen = dict(worlds=0, too_old=0, no_scene_frame=0, no_raw_step=0, rejected_clock=0, newest_world_step=None)
    for received in reversed(list(world_records)):
        world = received.evidence
        seen["worlds"] += 1
        if seen["newest_world_step"] is None:
            seen["newest_world_step"] = world.simulation_step
        if publisher_sequence is not None and world.publisher_sequence != publisher_sequence:
            continue
        if (world.simulation_session_id, world.reset_epoch) != (identity["session_id"], identity["reset_epoch"]):
            raise SceneAssociationError("RECORDER_SOURCE_ALIGNMENT_SOURCE_SCOPE_INVALID")
        source_ns = round(world.simulation_time_s * 1e9)
        received_ns = round(received.received_monotonic_s * 1e9)
        if source_ns > anchor_sim or received_ns > request_ns:
            continue
        if anchor_sim - source_ns > _WINDOW_NS:
            if publisher_sequence is not None:
                raise SceneAssociationError("RECORDER_SOURCE_ALIGNMENT_SOURCE_OUTSIDE_TIMING_WINDOW")
            seen["too_old"] += 1
            break
        if world.paused or world.truncated:
            raise SceneAssociationError("RECORDER_SOURCE_ALIGNMENT_SOURCE_INVALID")
        matching = frames.get((world.simulation_session_id, world.reset_epoch, world.simulation_step), [])
        if len(matching) > 1:
            raise SceneAssociationError("RECORDER_SOURCE_ALIGNMENT_SOURCE_AMBIGUOUS")
        raw = raw_lookup(world.simulation_step)
        if not matching or raw is None:
            if publisher_sequence is not None:
                raise SceneAssociationError("RECORDER_SOURCE_ALIGNMENT_TEACHER_EVENT_UNAVAILABLE")
            seen["no_scene_frame" if not matching else "no_raw_step"] += 1
            continue
        scene, receipt_s = matching[0]
        sample = raw["sample"] if "sample" in raw else raw
        receipt_ns = round(receipt_s * 1e9)
        if (scene["paused"] or scene["model_sha256"] != model_sha256
                or round(scene["simulation_time_s"] * 1e9) != source_ns
                or sample["model_qpos"] != scene["qpos"] or sample["model_qvel"] != scene["qvel"]
                or round(sample["simulation_time_s"] * 1e9) != source_ns
                or not _raw_source_matches(sample, world, scene)):
            raise SceneAssociationError("RECORDER_SOURCE_ALIGNMENT_SOURCE_NATIVE_MISMATCH")
        floor = min(sample["clock_interval_begin_monotonic_ns"], scene["clock_interval_begin_monotonic_ns"],
                    received_ns, receipt_ns)
        if not (sample["clock_interval_end_monotonic_ns"] <= scene["clock_interval_begin_monotonic_ns"] <= received_ns
                and scene["clock_interval_end_monotonic_ns"] <= receipt_ns
                and scene["clock_interval_end_monotonic_ns"] <= clock["begin_monotonic_ns"]
                and receipt_ns <= request_ns):
            if publisher_sequence is not None:
                raise SceneAssociationError("RECORDER_SOURCE_ALIGNMENT_SOURCE_CLOCK_INVALID")
            seen["rejected_clock"] += 1
            continue
        if request_ns - floor > _WINDOW_NS:
            if publisher_sequence is not None:
                raise SceneAssociationError("RECORDER_SOURCE_ALIGNMENT_SOURCE_OUTSIDE_TIMING_WINDOW")
            continue
        return received, (scene, receipt_s), raw
    # The counts are data-side diagnostics only (what the Recorder's own histories held when the join failed).
    raise SceneAssociationError(
        "RECORDER_SOURCE_ALIGNMENT_UNAVAILABLE: " + " ".join(f"{key}={value}" for key, value in seen.items())
        + f" anchor_sim_ns={anchor_sim}", diagnostics=dict(seen, anchor_sim_ns=anchor_sim))


_EDGE = 3


def _edges(items):
    items = list(items)
    return items if len(items) <= 2 * _EDGE else items[:_EDGE] + [None] + items[-_EDGE:]


def describe_alignment_inputs(*, world_records, scene_frames, raw_range, anchor, error=None, now_monotonic_ns=None) -> dict:
    """What the Recorder held when an association could not be built: steps and stamps only, bounded, no samples.

    `overlap` is the proof the next run needs: the simulation steps that exist in the world records AND the scene frames
    AND the retained raw range (the join needs one of them to also sit inside the 100 ms window before the anchor).
    """

    worlds = [(item.evidence.simulation_step, item.evidence.publisher_sequence,
               round(item.evidence.simulation_time_s * 1e9), round(item.received_monotonic_s * 1e9))
              for item in world_records]
    frames = [(frame["simulation_step"], round(frame["simulation_time_s"] * 1e9), round(receipt * 1e9))
              for frame, receipt in scene_frames]
    world_steps, frame_steps = {item[0] for item in worlds}, {item[0] for item in frames}
    low, high = (None, None) if raw_range is None else raw_range
    both = sorted(world_steps & frame_steps)
    all_three = [step for step in both if low is not None and low <= step <= high]
    clock = anchor["request_ros_clock"]
    return {
        "anchor": {"sim_time_ns": clock["sim_time_ns"], "begin_monotonic_ns": clock["begin_monotonic_ns"],
                   "end_monotonic_ns": clock["end_monotonic_ns"], "request_monotonic_ns": anchor["request_monotonic_ns"],
                   "now_monotonic_ns": now_monotonic_ns},
        "world_records": {"count": len(worlds), "step_sequence_sim_received_ns": _edges(worlds)},
        "scene_frames": {"count": len(frames), "step_sim_received_ns": _edges(frames)},
        "raw_steps": None if raw_range is None else {"min": low, "max": high},
        "overlap": {"world_and_scene_steps": len(both), "world_scene_and_raw_steps": len(all_three),
                    "newest_all_three": all_three[-_EDGE:], "world_only": sorted(world_steps - frame_steps)[-_EDGE:],
                    "scene_only": sorted(frame_steps - world_steps)[-_EDGE:]},
        "error": None if error is None else str(error)[:300],
        "rejections": None if error is None else getattr(error, "diagnostics", None),
    }


def build_association(job: AssociationJob, selection, *, base_geometry, model, execution_root):
    """(association document, raw record) for one job from the Teacher's records and the selected physics source."""

    from moveit_msgs.srv import GetPlanningScene

    from ..control.planning_scene.task_scene import verify_task_scene
    from ..core.task_geometry import Pose7

    received, (scene, receipt_s), raw = selection
    world = received.evidence
    expected_world = source_geometry(base_geometry, world)
    response = decode_ros(GetPlanningScene.Response, job.query["response"])
    if job.operation == "attach":
        data = source_model_data(model, world, scene)
        expected = source_attachment_geometry(expected_world, model, data)
        verification = verify_task_scene(
            response.scene, expected_world, expected_cup_attachment=expected["link_name"],
            expected_cup_local_pose=Pose7.parse(expected["local_cup"]["pose"]["values"], "alignment.local"),
            expected_touch_links=tuple(expected["touch_links"]), cup_local_pose_audit_only=True)
        geometry = expected
    elif job.operation == "detach":
        verification, geometry = verify_task_scene(response.scene, expected_world), expected_world
    elif job.operation == "world_sync":
        verification = verify_task_scene(response.scene, expected_world, cup_world_pose_audit_only=True)
        geometry = expected_world
    elif job.operation == "initial":
        from ..control.planning_scene.task_scene import PRE_SETUP_EXPECTATION, verify_pre_setup_scene
        verification, geometry = verify_pre_setup_scene(response.scene), PRE_SETUP_EXPECTATION
    else:
        raise SceneAssociationError("RECORDER_SOURCE_ALIGNMENT_OPERATION_UNKNOWN")
    if not verification.success:
        raise SceneAssociationError("RECORDER_SOURCE_ALIGNMENT_GEOMETRY_MISMATCH: " + ",".join(verification.evidence["mismatches"]))
    document = make_scene_association(
        execution_root=execution_root, source=world, scene_state=scene,
        received_monotonic_ns=round(received.received_monotonic_s * 1e9), scene_received_monotonic_ns=round(receipt_s * 1e9),
        geometry=geometry, apply_call=job.apply, query_call=job.query, verification=verification,
        operation=job.operation)
    return document, copy.deepcopy(raw)


class SceneAssociations:
    """The admitted associations of one recording, as the physical audit provider reads them."""

    def __init__(self) -> None:
        self.history: list[dict] = []
        self._pending: dict[str, int] = {}

    def pend(self, key: str, sim_time_ns: int) -> None:
        """An association is built and being verified: rows from its anchor on wait for it."""
        self._pending[key] = sim_time_ns

    def settle(self, key: str) -> None:
        self._pending.pop(key, None)

    def admit(self, bound: dict) -> None:
        self.history.append(copy.deepcopy(bound))

    def at(self, at_s: float, tracker: SceneOperationTracker | None = None, unbuilt_sim_times=()):
        """The latest admitted association at `at_s`, or None while one is still owed (rows wait, they never guess).

        Owed: an apply whose read-back was not seen (tracker), a job issued and not built yet (`unbuilt_sim_times`, the
        sim times of their anchors), or one built and being verified (pending)."""

        at_ns = round(at_s * 1e9)
        if any(sim <= at_ns for sim in unbuilt_sim_times):
            return None
        if tracker is not None:
            owed = tracker.owed_apply_sim_times()
            if any(sim <= at_ns for sim in owed):
                return None
        if any(sim <= at_ns for sim in self._pending.values()):
            return None
        from .scene_association import association_anchor

        for bound in reversed(self.history):
            if association_anchor(bound["association"])["response_ros_clock"]["sim_time_ns"] <= at_ns:
                return copy.deepcopy(bound)
        return None

    def same(self, other_id: str, document: dict) -> bool:
        return any(canonical(item["association"]) == canonical(document)
                   for item in self.history if item["association"]["association_id"] == other_id)
