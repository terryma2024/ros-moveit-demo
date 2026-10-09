"""Causal per-grid joins of retained native physics and actual scene/controller records."""

import copy
import math

from .contracts import identifier, integer
from .episode_audit import _identity_ok
from .joints import ACT_JOINTS, ordered_positions
from .nonfinite import json_safe
from .synchronizer import bracketed_age_ok_ns, source_age_ok_ns


class LivePhysicalAuditProvider:
    def __init__(self, *, identity, inputs, scene_association_source, physics_source,
                 planning_source, controller_source, lifecycle_source, physics_awaiting=None, planning_next_source=None,
                 concurrent_apply_source=None):
        if not _identity_ok(identity, formal=True):
            raise ValueError("LIVE_PHYSICAL_IDENTITY_INVALID")
        integer(identity["reset_epoch"], minimum=1)
        if not all(callable(value) for value in (scene_association_source, physics_source,
                                                planning_source, controller_source, lifecycle_source)):
            raise ValueError("LIVE_PHYSICAL_SOURCE_BINDING_INVALID")
        self._identity, self._inputs = copy.deepcopy(identity), copy.deepcopy(inputs)
        self.scene_association_source = scene_association_source
        self.physics_source, self.planning_source = physics_source, planning_source
        self.controller_source, self.lifecycle_source = controller_source, lifecycle_source
        #: optional `at_s -> bool`: the physics chunk for this instant has not arrived yet (it is in flight, not missing)
        self.physics_awaiting = physics_awaiting
        #: optional `at_s -> read record | None`: the first planning-scene read AFTER `at_s`, offered only when the read the
        #: planning source returned is older than the age rule allows and the source has established the bracket (CP-3440 B)
        self.planning_next_source = planning_next_source
        #: optional `read -> (admitted association documents whose apply overlaps the read, an overlapping apply is not admitted yet)`
        #: (CP-3489): a read concurrent with an apply may show the scene before or after it
        self.concurrent_apply_source = concurrent_apply_source
        self._release_epoch = identity["release_epoch"]
        self._release_time_s = None
        self._validated_associations = {}
        self._last_grid_ns = None

    @property
    def identity(self):
        return copy.deepcopy(self._identity)

    def admit_scene_association(self, bound):
        """Authenticate on the sole writer path, before publishing the derived lookup."""
        from .scene_association import canonical, verify_scene_association
        owned = copy.deepcopy(bound)
        signature = canonical(owned)
        association_id = owned["association"]["association_id"]
        previous = self._validated_associations.get(association_id)
        if signature == previous:
            return
        if previous is not None:
            raise ValueError("LIVE_PHYSICAL_ASSOCIATION_ID_REUSED")
        verify_scene_association(owned["association"], inputs=self._inputs,
                                identity=self._identity, raw_steps=owned["raw_steps"])
        self._validated_associations[association_id] = signature

    def _verify_scene(self, planning, response, at_s):
        from ..control.planning_scene.task_scene import normalized_scene_geometry
        from .scene_association import canonical, concurrent_apply_geometry_matches
        bound = self.scene_association_source(at_s)
        if bound is None:
            return False
        document, raw_steps = bound["association"], bound["raw_steps"]
        signature = canonical(bound)
        if signature != self._validated_associations.get(document["association_id"]):
            return False
        from .scene_association import association_anchor
        applied = association_anchor(document)
        if (applied["response_ros_clock"]["end_monotonic_ns"]
                > planning["request_ros_clock"]["begin_monotonic_ns"]
                or applied["response_ros_clock"]["sim_time_ns"] > planning["request_ros_clock"]["sim_time_ns"]):
            raise ValueError("LIVE_PHYSICAL_SCENE_GEOMETRY_INVALID")
        observed = canonical(normalized_scene_geometry(response.scene))
        if observed != canonical(document["receipt"]["geometry"]):
            # CP-3489: a read concurrent with the NEXT apply may already show its scene; exactly that geometry is accepted
            hook = self.concurrent_apply_source
            if hook is None:
                raise ValueError("LIVE_PHYSICAL_SCENE_GEOMETRY_INVALID")
            associations, pending = hook(planning)
            if not concurrent_apply_geometry_matches(planning, observed, document["association_id"], associations):
                if pending:
                    return False        # the overlapping apply's association is not built yet: the row waits
                raise ValueError("LIVE_PHYSICAL_SCENE_GEOMETRY_INVALID")
        return document["association_id"]

    def _verify_apply_anchor(self, planning, at_s):
        """CP-3449: `planning` must be the successful apply that anchors the governing association. The scene it produced is proven by
        the read that follows it (checked by the caller against the same association), so nothing is compared here."""
        from .scene_association import _call, association_anchor, canonical
        bound = self.scene_association_source(at_s)
        if bound is None:
            return False
        document = bound["association"]
        if canonical(bound) != self._validated_associations.get(document["association_id"]):
            return False
        if document["apply"] is None:
            raise ValueError("LIVE_PHYSICAL_SCENE_INVALID")
        _call(planning, "/apply_planning_scene")
        response = planning["response"]
        if (canonical(planning) != canonical(association_anchor(document)) or not isinstance(response, dict)
                or response.get("success") is not True):
            raise ValueError("LIVE_PHYSICAL_SCENE_INVALID")
        return document["association_id"]

    def _parts(self, at_s):
        from moveit_msgs.msg import PlanningSceneComponents
        from moveit_msgs.srv import GetPlanningScene
        from .scene_association import _call, decode_ros
        if type(at_s) not in (int, float) or not math.isfinite(at_s) or at_s < 0:
            raise ValueError("LIVE_PHYSICAL_GRID_INVALID")
        grid_ns = round(at_s * 1e9)
        values = (self.physics_source(at_s), self.planning_source(at_s),
                  self.controller_source(at_s), self.lifecycle_source(at_s))
        if any(value is None for value in values):
            return None
        physics, planning, controller, lifecycle = values
        sample = physics["sample"]
        if (sample["simulation_session_id"] != self.identity["session_id"]
                or sample["reset_epoch"] != self.identity["reset_epoch"]):
            raise ValueError("LIVE_PHYSICAL_SCOPE_INVALID")
        required = (PlanningSceneComponents.WORLD_OBJECT_NAMES | PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
                    | PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS | PlanningSceneComponents.OBJECT_COLORS)
        # CP-3449: the scene source of a row between the Teacher's apply and the first read after it is that APPLY
        apply_form = planning.get("service") == "/apply_planning_scene"
        if apply_form:
            association_id = self._verify_apply_anchor(planning, at_s)
        else:
            _call(planning, "/get_planning_scene")
            decode_ros(GetPlanningScene.Request, planning["request"])
            response = decode_ros(GetPlanningScene.Response, planning["response"])
            if (planning["request"]["components"]["components"] & required != required
                    or not isinstance(planning["response"], dict) or set(planning["response"]) != {"scene"}):
                raise ValueError("LIVE_PHYSICAL_SCENE_INVALID")
            association_id = self._verify_scene(planning, response, at_s)
        if not association_id:
            return None
        integer(controller["source_stamp_ns"])
        integer(controller["generation"], minimum=1)
        ordered_positions(controller["positions"], ACT_JOINTS)
        planning_stamp = planning["response_ros_clock"]["sim_time_ns"]
        next_read = None
        if apply_form or not source_age_ok_ns(grid_ns, planning_stamp):
            # older than the age rule, or the apply itself: valid only if the next read carries the same scene and nothing was
            # applied between
            next_read = None if self.planning_next_source is None else self.planning_next_source(at_s)
            if next_read is None:
                return None
            _call(next_read, "/get_planning_scene")
            next_request = decode_ros(GetPlanningScene.Request, next_read["request"])
            next_response = decode_ros(GetPlanningScene.Response, next_read["response"])
            if (next_request.components.components & required != required
                    or not isinstance(next_read["response"], dict) or set(next_read["response"]) != {"scene"}):
                raise ValueError("LIVE_PHYSICAL_SCENE_INVALID")
            # the later read must be causally after the same association and show the same geometry as the first
            if self._verify_scene(next_read, next_response, at_s) != association_id:
                raise ValueError("LIVE_PHYSICAL_SCENE_BRACKET_INVALID")
            if not bracketed_age_ok_ns(grid_ns, planning_stamp, next_read["response_ros_clock"]["sim_time_ns"]):
                return None
        stamps = (round(sample["simulation_time_s"] * 1e9), controller["source_stamp_ns"]) + (
            (planning_stamp,) if next_read is None else ())
        if any(not source_age_ok_ns(grid_ns, stamp) for stamp in stamps):
            return None
        identifier(lifecycle["phase"])
        epoch, release = lifecycle["release_epoch"], lifecycle["release_time_s"]
        integer(epoch)
        if epoch not in (self._release_epoch, self._release_epoch + 1):
            raise ValueError("LIVE_PHYSICAL_RELEASE_INVALID")
        if epoch == self.identity["release_epoch"]:
            if release is not None:
                raise ValueError("LIVE_PHYSICAL_RELEASE_INVALID")
        else:
            if type(release) not in (int, float) or not math.isfinite(release) or release < 0:
                raise ValueError("LIVE_PHYSICAL_RELEASE_INVALID")
            release_ns = round(release * 1e9)
            if epoch == self._release_epoch and release != self._release_time_s:
                raise ValueError("LIVE_PHYSICAL_RELEASE_INVALID")
            if any(stamp < release_ns for stamp in (*stamps, planning_stamp)):
                return None
            if epoch > self._release_epoch and (self._last_grid_ns is None
                                               or not self._last_grid_ns < release_ns <= grid_ns):
                raise ValueError("LIVE_PHYSICAL_RELEASE_INVALID")
        return copy.deepcopy((*values, association_id, next_read))

    def ready(self, at_s):
        return self._parts(at_s) is not None

    def unready_cause(self, at_s):
        """Which row source is not causal at `at_s` (observation for the start-gate telemetry, CP-3414)."""
        try:
            for name, source in (("physics", self.physics_source), ("planning_scene", self.planning_source),
                                 ("controller_state", self.controller_source), ("lifecycle", self.lifecycle_source)):
                if source(at_s) is None:
                    return name
            return "association_or_window"
        except Exception as error:
            return "error:" + type(error).__name__

    def awaiting_arrival(self, at_s):
        hook = self.physics_awaiting
        return False if hook is None else hook(at_s) is True

    def __call__(self, at_s):
        parts = self._parts(at_s)
        if parts is None:
            raise ValueError("LIVE_PHYSICAL_SOURCE_UNAVAILABLE")
        physics, planning, controller, lifecycle, association_id, next_read = parts
        grid_ns = round(at_s * 1e9)
        if self._last_grid_ns is not None and grid_ns <= self._last_grid_ns:
            raise ValueError("LIVE_PHYSICAL_GRID_REUSED")
        sample = physics["sample"]
        release_event = lifecycle["release_epoch"] > self._release_epoch
        contacts = [dict(contact, source_group=group)
                    for group in ("left_fingertip_contacts", "right_fingertip_contacts", "other_object_contacts")
                    for contact in sample[group]]
        row = {"reset_epoch": self.identity["reset_epoch"], "release_epoch": lifecycle["release_epoch"],
            "release_event": release_event, "release_time_s": lifecycle["release_time_s"],
            "phase": "RELEASE" if release_event else lifecycle["phase"],
            "physical_stamps": {"cup": sample["simulation_time_s"], "contacts": sample["simulation_time_s"],
                "planning_scene": planning["response_ros_clock"]["sim_time_ns"] / 1e9},
            "mujoco_truth": {"source_kind": "native_physics_step", **physics}, "contacts": contacts,
            # The originals are ROS messages converted to dicts; non-finite floats in them (NaN effort of a joint state) are tagged,
            # never dropped, because the retained rows are strict canonical JSON (CP-3412). Finite values pass through unchanged.
            "planning_scene": {"query_id": planning["call_id"], "record": json_safe(planning),
                "association_id": association_id,
                # present only when the read is older than the age rule and was admitted by bracketing (CP-3440 B)
                **({} if next_read is None else {"bracket": {"next_query_id": next_read["call_id"],
                                                             "next_record": json_safe(next_read)}})},
            "controller_state": json_safe(controller),
            # Only the capture's subsequent accepted original t+.1 join supplies these labels.
            "reference_time_s": None, "reference_source": None, "reference_positions": None}
        self._release_epoch, self._release_time_s, self._last_grid_ns = (
            lifecycle["release_epoch"], lifecycle["release_time_s"], grid_ns)
        return row
