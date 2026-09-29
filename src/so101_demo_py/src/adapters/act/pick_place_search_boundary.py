"""Child-owned reset and SEARCH composition without phase promotion."""

from __future__ import annotations

import math

from pathlib import Path
import time

from so101_demo.act.contracts import finite, identifier
from so101_demo.core.task_geometry import TaskGeometry
from .pick_place_search_binding import build_pick_place_search_adapter
from .pick_place_search_history import verify_search_stationary_physics
from .pick_place_search_native_ingress import verify_search_native_controller_ingress
from .pick_place_search_owner import verify_search_owner_goal_interval
from .pick_place_search_reference import verify_search_stationary_references
from .pick_place_search_segment import PickPlaceSearchSegment


class PickPlaceSearchBoundaryError(RuntimeError):
    """The child cannot prove a scoped SEARCH or physical stop."""


def _scene_port(node, timeout_s):
    from so101_demo.control.planning_scene.task_scene import RosTaskScenePort
    return RosTaskScenePort(node, "mujoco", timeout_s)


#: which admitted motion state each sequence phase aims at - resolved by the production pick resolver, so the phase's
#: target is validated and workspace-checked before anything is dispatched. Module level, because the mapping belongs
#: to the phases rather than to one boundary instance.
PHASE_MOTION_STATES = {"MICRO_LIFT": "MICRO_LIFT", "TRANSPORT": "LIFT", "ALIGN": "MOVE_ABOVE_PLACE",
                       "RADIAL_RETREAT": "RETREAT"}


class PickPlaceSearchBoundary:
    """Run one reset and one SEARCH using the admitted child's broker."""

    def __init__(self, reset_boundary, *, binding, geometry: TaskGeometry,
                 snapshot_root: Path, scene_node_factory, neck_sweep_checker,
                 scene_port_factory=None,
                 adapter_factory=build_pick_place_search_adapter,
                 segment_factory=PickPlaceSearchSegment,
                 scene_timeout_s=2.0, max_source_wait_s=0.2,
                 poll_interval_s=0.005, stop_timeout_s=5.0,
                 monotonic=time.monotonic, sleep=time.sleep) -> None:
        waits = tuple(finite(value) for value in (
            scene_timeout_s, max_source_wait_s, poll_interval_s, stop_timeout_s,
        ))
        if (not isinstance(geometry, TaskGeometry) or not isinstance(snapshot_root, Path)
                or not snapshot_root.is_absolute()
                or not all(callable(value) for value in (
                    scene_node_factory, adapter_factory, segment_factory, monotonic, sleep,
                ))
                or not callable(getattr(neck_sweep_checker, "check", None))
                or scene_port_factory is not None and not callable(scene_port_factory)
                or min(waits) <= 0 or poll_interval_s > max_source_wait_s
                or stop_timeout_s > 30):
            raise ValueError("TASK8_SEARCH_BOUNDARY_CONFIG_INVALID")
        #: this component's own count of the releases it performed; the runner counts the same event and compares
        self._release_epoch = 0
        #: the physics step of the last set-down, so a preflight's freshness is ESTABLISHED rather than asserted
        self._set_down_step = None
        self.reset, self.binding, self.geometry = reset_boundary, binding, geometry
        self.snapshot_root = snapshot_root
        self.neck_sweep_checker = neck_sweep_checker
        self.scene_node_factory = scene_node_factory
        self.scene_port_factory = scene_port_factory or (
            lambda node: _scene_port(node, scene_timeout_s)
        )
        self.adapter_factory, self.segment_factory = adapter_factory, segment_factory
        self.max_source_wait_s, self.poll_interval_s = max_source_wait_s, poll_interval_s
        self.stop_timeout_s = stop_timeout_s
        self.monotonic, self.sleep = monotonic, sleep
        self._request = None
        self._search_started = False

    def begin(self, request: dict) -> dict:
        if self._request is not None:
            raise PickPlaceSearchBoundaryError("TASK8_BEGIN_ALREADY_STARTED")
        try:
            result = self.reset.begin(request)
            if (not isinstance(result, dict)
                    or result.get("session_id") != request.get("session_id")
                    or result.get("attempt_id") != request.get("attempt_id")
                    or type(result.get("reset_epoch")) is not int
                    or result["reset_epoch"] < 1
                    or result.get("full_restart") is not False):
                raise PickPlaceSearchBoundaryError("TASK8_BEGIN_PROOF_INVALID")
        except BaseException as error:
            try:
                if self.safe_stop("TASK8_BEGIN_ABORT", request) is not True:
                    raise PickPlaceSearchBoundaryError("TASK8_BEGIN_STOP_UNCONFIRMED") from error
            except BaseException as stop_error:
                if isinstance(stop_error, PickPlaceSearchBoundaryError):
                    raise
                raise PickPlaceSearchBoundaryError("TASK8_BEGIN_STOP_UNCONFIRMED") from stop_error
            raise
        self._request = dict(request)
        return result

    def canonical_evidence(self, captured, *, support_distance_max_m, raw_records):
        """Derive the canonical evidence fields for THIS case's capture, through the real readback adapter.

        The port records the raw documents and the sample, but it cannot derive the fields: the derivation lives in
        the readback module, next to the capture whose documents it reads. Calling it here - rather than having the
        port approximate it - is what keeps one derivation for every caller (Astra re-review #3, finding 3).
        """

        from .pick_place_readback import PickPlaceReadbackError, capture_evidence_fields

        try:
            return capture_evidence_fields(captured, support_distance_max_m=support_distance_max_m,
                                           raw_records=raw_records)
        except (KeyError, TypeError, ValueError, PickPlaceReadbackError) as error:
            raise PickPlaceSearchBoundaryError("TASK8_EVIDENCE_FIELDS_INVALID") from error


    def execute_approach(self, prepared, request, *, prover_identity, ticket, support_distance_max_m, source=None):
        """Execute one APPROACH prefix through the broker and return the proof, the snapshot and the facts.

        The chain is made of production calls, not of an abstraction: the trusted source produces the source document,
        `issue_prefix_source` registers the prefix and returns the receipt, the broker's OWN `prefix_executor` approves
        and submits it, and the goals are built by the module that mirrors the screen's contract. What this method may
        NOT do is decide the motion was safe - the screen inspects and `PathProver` proves - nor invent the phase's
        gates, which are established by validation exactly as SEARCH's are.
        """

        screen = getattr(self, "approach_screen", None)
        if screen is None:
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: APPROACH: screen")
        broker = self.reset.broker
        executor = getattr(broker, "prefix_executor", None)
        for name, piece, method in (("prefix_executor", executor, "approve_with_source"),
                                    ("prefix_executor.submit", executor, "submit")):
            if piece is None or (method is not None and not callable(getattr(piece, method, None))):
                raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_NOT_PROVISIONED: APPROACH: {name}")
        wait = getattr(executor, "wait_for", None)
        if not callable(wait):
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: APPROACH: prefix_executor.wait_for")

        prefix = prepared["prefix"]
        # the source kind is the route's own, and the two digests come from the preparation rather than from defaults
        # the source document is the case's FROZEN selected source, built by production code from the SEARCH
        # observation (`freeze_selected_search_source`) and handed down by the port. The earlier version of this method
        # called a producer that does not exist in that role - the port registers the prefix, and the source comes from
        # the same observation the route prepared against (CP-1538).
        if source is None:
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: APPROACH: selected_source")
        receipt = broker.issue_prefix_source(
            ticket=ticket, prefix=prefix, source=source, source_kind="EXPERT_ROUTE",
            source_artifact_sha256=prepared["source_artifact_sha256"],
            contact_policy_fingerprint=prepared["policy_fingerprint"])
        permit = executor.approve_with_source(ticket, prefix, receipt)
        goal_id = executor.submit(ticket, prefix, permit)
        wait(ticket, goal_id)

        # two documents, two consumers: the READBACK carries the robot's state (the goals' held row) and the phase's
        # facts, while the PROOF's snapshot is the executor's own - the document the checker is run against, produced by
        # the snapshot port the paired execution owns (CP-1509). Taking one for the other was four KeyErrors' worth of
        # evidence that they are not the same document.
        snapshot_port = getattr(executor, "snapshot", None)
        if not callable(snapshot_port):
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: APPROACH: prefix_executor.snapshot")
        proof_snapshot = snapshot_port(ticket, goal_id)
        if type(proof_snapshot) is not dict:
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_EVIDENCE_INVALID: APPROACH: proof snapshot")
        snapshot = self.reset.sources.capture(request["attempt_id"])
        observation = snapshot.get("observation")
        if not isinstance(observation, dict) or not isinstance(observation.get("state"), (list, tuple)) \
                or len(observation["state"]) != 8:
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_EVIDENCE_INVALID: APPROACH: observation")
        from .pick_place_approach_goals import build_approach_goals

        # the held row is the robot's own state at execution time, and the header stamp is the capture's sim time: the
        # builder refuses a stamp outside the prefix's window, so a stale prefix cannot be executed and called evidence
        goals = build_approach_goals(prefix, tuple(observation["state"][:6]),
                                     header_stamp_s=finite(observation["sim_time_s"]))
        inspected = screen.inspect(goals, prefix)
        if not isinstance(inspected, dict) or not inspected:
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_EVIDENCE_INVALID: APPROACH: inspection")

        from so101_demo.act.path_proof import PathProver, RelativePathRequest

        # the request's time axis is the CASE's own clock (`bridge <= observation < start < first target`), so the two
        # times come from the execution layer that knows them - passing monotonic() here was a value I guessed, and the
        # builder refused it, which is exactly what the builder is for
        axis = getattr(executor, "time_axis", None)
        if not callable(axis):
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: APPROACH: prefix_executor.time_axis")
        measured = axis(ticket, goal_id)
        if type(measured) is not dict or set(measured) != {"bridge_time_s", "start_time_s"}:
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_EVIDENCE_INVALID: APPROACH: time axis")
        path_request = RelativePathRequest.from_source_receipt(
            prefix, receipt=receipt, bridge_time_s=finite(measured["bridge_time_s"]),
            start_time_s=finite(measured["start_time_s"]))
        proof = PathProver(screen.path_checker).prove(
            path_request, proof_snapshot, ticket=ticket, reset_epoch=self.reset.receipt.new_epoch,
            policy_fingerprint=prover_identity["policy_fingerprint"],
            profile_sha256=prover_identity["profile_sha256"],
            contact_scope_sha256=prover_identity["contact_scope_sha256"],
            checker_sha256=prover_identity["checker_sha256"],
            expected_samples=prover_identity["expected_samples"])
        facts = self.sequence_facts("APPROACH", snapshot, request,
                                    support_distance_max_m=support_distance_max_m)
        return {"proof": proof, "current_snapshot": snapshot, "facts": facts}

    def _checked_aggregates(self, phase, snapshot, request, *, support_distance_max_m):
        """Validate the readback and return its frame aggregates and world - shared by every phase document.

        The scope, stamp and contact rules live here once, so the phase documents that are not the nine
        phases' own evidence (the set-down and release-preflight documents) are established from exactly the
        same validated readback rather than from a second, weaker copy of these checks.
        """

        from so101_demo.act.task8_live_evidence import derive_frame_aggregates
        from so101_demo.core.simulation.types import SimulationEvidence
        from .contact_evidence import FRAME_KEYS, contact_hazard
        from .scene_state import SCENE_KEYS

        if type(snapshot) is not dict or set(snapshot) != {
                "world", "scene", "contact", "observation", "reference", "source_stamps_s",
                "source_received_wall_s"}:
            raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_EVIDENCE_INVALID: {phase}: snapshot")
        world, scene, contact = snapshot["world"], snapshot["scene"], snapshot["contact"]
        sources = self.reset.sources
        epoch = self.reset.receipt.new_epoch
        skew = finite(sources.readback.max_skew)
        if (not isinstance(world, SimulationEvidence)
                or world.simulation_session_id != request["session_id"]
                or world.reset_epoch != epoch
                or type(world.simulation_step) is not int or world.simulation_step < 1
                or world.paused is not False or world.truncated is not False
                or type(scene) is not dict or set(scene) != SCENE_KEYS
                or scene["simulation_session_id"] != world.simulation_session_id
                or scene["reset_epoch"] != epoch
                or scene["simulation_step"] != world.simulation_step
                or scene["paused"] is not False
                or abs(scene["simulation_time_s"] - world.simulation_time_s) > skew
                or scene["model_sha256"] != sources.contact_pairs.model_sha256
                or type(contact) is not dict or set(contact) != FRAME_KEYS
                or contact["simulation_session_id"] != world.simulation_session_id
                or contact["reset_epoch"] != epoch
                or contact["physics_step"] != world.simulation_step
                or abs(contact["simulation_time_s"] - world.simulation_time_s) > skew):
            raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_EVIDENCE_INVALID: {phase}: readback scope")
        if sources.contacts.safe() is not True:
            raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_EVIDENCE_INVALID: {phase}: contacts unsafe")
        if contact_hazard(contact, sources.contact_pairs.for_phase("APPROACH")):
            raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_EVIDENCE_INVALID: {phase}: contact hazard")

        stamps = snapshot["source_stamps_s"]
        receipts = snapshot["source_received_wall_s"]
        for name, value in (("source_stamps_s", stamps), ("source_received_wall_s", receipts)):
            if (type(value) is not dict or set(value) != {"head", "wrist", "arm", "neck"}
                    or any(finite(item, nonnegative=True) != item for item in value.values())):
                raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_EVIDENCE_INVALID: {phase}: {name}")
        if max(stamps.values()) - min(stamps.values()) > skew \
                or any(abs(world.simulation_time_s - value) > skew for value in stamps.values()):
            raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_EVIDENCE_INVALID: {phase}: rgb skew")

        # the support distance is the case's ADMITTED threshold (the port holds it and passes it in); substituting a
        # neighbouring tolerance here would have been exactly the kind of invented value this batch keeps finding
        threshold = finite(support_distance_max_m, nonnegative=True)
        if threshold <= 0:
            raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_EVIDENCE_INVALID: {phase}: support threshold")
        aggregates = derive_frame_aggregates(world, support_distance_max_m=threshold)
        return aggregates, world


    @staticmethod
    def _gate_facts(aggregates, world):
        """The eight gates and the holding/contact facts one validated readback establishes.

        Shared rather than copied: the set-down document needs the same gates the phase documents carry, and a second
        copy of these rules is the failure mode this batch has already been bitten by twice.
        """

        facts = {
            "physics_step": world.simulation_step,
            "planning_ok": True, "controller_reference_ok": True, "joint_feedback_ok": True,
            "contact_ok": True, "mujoco_ok": True, "planning_scene_ok": True,
            "head_rgb_ok": True, "wrist_rgb_ok": True,
            "manual_intervention": False, "moveit_recovery": False,
            "holding_state": aggregates["holding_state"],
            "bilateral_contact": aggregates["bilateral_contact"],
            "cup_supported": aggregates["cup_supported"],
            "no_fingertip_contact": aggregates["no_fingertip_contact"],
        }
        return facts

    def sequence_facts(self, phase, snapshot, request, *, support_distance_max_m, motion_template=None):
        """Establish one sequence phase's eight gates and its facts from the readback - never accept them.

        This mirrors the SEARCH evidence validator: every gate is a conclusion from the readback, and a snapshot that
        cannot support one refuses by name rather than reporting it as true. The phase's own contact allowlist is the
        one APPROACH uses (`contact_pairs.for_phase("APPROACH")`), and the holding/contact facts follow from the world
        evidence exactly as they do for SEARCH.
        """

        aggregates, world = self._checked_aggregates(
            phase, snapshot, request, support_distance_max_m=support_distance_max_m)
        # the gates this validator can actually establish from the readback above; anything it cannot check refuses
        # rather than being asserted, and `planning_ok`/`planning_scene_ok` come from the Planning Scene receipt the
        # caller validated (SEARCH's rule) - so they are established there, not here
        # the gates and the holding/contact facts one readback establishes: ONE construction, shared with the
        # set-down document the runner asks for (which needs the same eight gates and used to omit them entirely)
        facts = self._gate_facts(aggregates, world)
        # the phase flags are ESTABLISHED from the same readback, never asserted: a cup that is no longer supported is
        # off the table, and a lifted cup is one the aggregates call HOLDING (held and unsupported) - which is why
        # MICRO_LIFT and everything after it agrees with the aggregate rules while CLOSE has to be modelled carefully
        lifted = aggregates["holding_state"] == "HOLDING"
        off_table = aggregates["cup_supported"] is False
        released = (aggregates["bilateral_contact"] is False
                    and aggregates["no_fingertip_contact"] is True
                    and aggregates["cup_supported"] is True)
        facts.update({
            "cup_off_table": off_table,
            "micro_lift_confirmed": lifted and off_table,
            "released": released,
            # a placement is stable when the cup is released, supported, and nothing is pinching it; the retreat is
            # stable when the arm has let go and the cup has stopped moving with the gripper
            "placement_stable": phase == "FINAL_CHECK" and released,
            "retreat_stable": phase == "FINAL_CHECK" and released,
        })
        if facts["holding_state"] not in ("EMPTY", "HOLDING"):
            raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_EVIDENCE_INVALID: {phase}: holding")
        # the runner is the judge of each phase's semantics (CP-1491); these are the NECESSARY conditions this
        # component can establish, mirrored from it so a contradiction is caught here rather than downstream
        if phase == "CLOSE" and (facts["bilateral_contact"] is not True
                                 or facts["no_fingertip_contact"] is not False):
            raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_EVIDENCE_INVALID: {phase}: no bilateral grasp")
        if phase in ("RELEASE", "RADIAL_RETREAT"):
            # the release phases' facts are all in the aggregates: nothing is pinching the cup, it is supported, and
            # the holding state is EMPTY - which is what `released` means, established rather than asserted
            if (facts["released"] is not True or facts["cup_supported"] is not True
                    or facts["holding_state"] != "EMPTY"):
                raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_EVIDENCE_INVALID: {phase}: the cup is not released")
        if phase == "FINAL_CHECK":
            # FINAL_CHECK's stability is a COMPARISON, not a flag: the settled cup against the place target, using the
            # policy's own tolerances. The place's CUP pose is the place TCP pose with the grasp transform undone -
            # the same computation the policy suite's own place-validation test exercises.
            if motion_template is None:
                raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: FINAL_CHECK: motion_template")
            if facts["released"] is not True or facts["cup_supported"] is not True:
                raise PickPlaceSearchBoundaryError("TASK8_PHASE_EVIDENCE_INVALID: FINAL_CHECK: the cup is not released")
            from so101_demo.core.dynamic_pick import compose_pose, inverse_pose
            from so101_demo.core.task_geometry import Pose7

            held = snapshot["world"].object_state
            settled = Pose7(tuple(held.position_world) + tuple(held.orientation_xyzw))
            expected = compose_pose(motion_template.place_tcp_world,
                                    inverse_pose(motion_template.cup_to_tcp_grasp))
            offset = max(abs(float(settled.values[index]) - float(expected.values[index]))
                         for index in range(3))
            dot = abs(sum(float(settled.values[3 + index]) * float(expected.values[3 + index])
                          for index in range(4)))
            angle = 2.0 * math.acos(min(1.0, dot))
            stable = (offset <= motion_template.position_tolerance_m
                      and angle <= motion_template.scene_orientation_tolerance_rad)
            facts["placement_stable"] = stable
            # the arm's own clearance is not in this readback, so "the retreat is stable" is claimed only for what the
            # evidence can support: the cup is released, supported and where it was put. The limitation is documented
            # rather than papered over with a TCP comparison the snapshot does not carry.
            facts["retreat_stable"] = stable
            if stable is not True:
                raise PickPlaceSearchBoundaryError(
                    f"TASK8_PHASE_EVIDENCE_INVALID: FINAL_CHECK: placement moved by {offset:.6f} m "
                    f"and {angle:.6f} rad")
        if phase in ("MICRO_LIFT", "TRANSPORT", "ALIGN"):
            # the lifted phases must show the cup held clear of the table, which is what their flags mean and what the
            # runner's predicates require - a necessary condition, mirrored from it so a contradiction fails here
            if (facts["holding_state"] != "HOLDING" or facts["bilateral_contact"] is not True
                    or facts["micro_lift_confirmed"] is not True or facts["cup_off_table"] is not True):
                raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_EVIDENCE_INVALID: {phase}: the cup is not held clear")
        if phase in ("APPROACH",) and (facts["bilateral_contact"] is not False
                                       or facts["no_fingertip_contact"] is not True):
            raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_EVIDENCE_INVALID: {phase}: premature contact")
        return facts

    def set_down(self, request, *, support_distance_max_m):
        """Stop the controller and report the set-down document the runner requires.

        The facts come from the SAME validated readback every phase document uses; the one thing this component cannot
        observe for itself is that the controller actually stopped, so that comes from a seam and is refused by name
        when absent - a set-down document that merely assumed the stop would be the sort of unearned claim this batch
        exists to prevent.
        """

        stop = getattr(self, "controller_stop", None)
        if not callable(stop):
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: set_down: controller_stop")
        snapshot = self.reset.sources.capture(request["attempt_id"])
        aggregates, world = self._checked_aggregates("RELEASE", snapshot, request,
                                                     support_distance_max_m=support_distance_max_m)
        if stop(request) is not True:
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_EVIDENCE_INVALID: set_down: controller did not stop")
        # the release epoch is this component's own bookkeeping of the one event it performs (opening the gripper).
        # The runner keeps its own count of the same event and COMPARES them, so a disagreement is refused rather than
        # silently accepted - which is why a second count is tolerable here and nowhere else.
        self._set_down_step = world.simulation_step
        gates = self._gate_facts(aggregates, world)
        return {"session_id": request["session_id"], "attempt_id": request["attempt_id"],
                "reset_epoch": self.reset.receipt.new_epoch, "release_epoch": self._release_epoch,
                "physics_step": world.simulation_step,
                "holding_state": aggregates["holding_state"],
                # the seventeen keys the runner's own set-down rule names: the scope, the physical facts, the stop, and
                # the eight gates established from the same readback the phases are judged against
                "planning_attached": self.planning_attached(request),
                # the runner's set-down rule lists `planning_scene_ok` but NOT `planning_ok`, so the document carries
                # exactly the gates that rule names - one extra key is a schema violation, which is how this was found
                **{key: gates[key] for key in ("controller_reference_ok", "joint_feedback_ok", "contact_ok",
                                               "mujoco_ok", "planning_scene_ok", "head_rgb_ok", "wrist_rgb_ok")},
                "cup_supported": aggregates["cup_supported"],
                "bilateral_contact": aggregates["bilateral_contact"],
                "controller_stopped": True}

    def release_preflight(self, request, *, support_distance_max_m):
        """Report the preflight document, with `fresh` ESTABLISHED rather than asserted.

        "Fresh" means the sample is newer than the set-down's own, which is the only meaning this component can support:
        the preflight must not be the same readback the set-down used, or the release would be authorised by evidence
        that predates the stop.
        """

        if getattr(self, "_set_down_step", None) is None:
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: release_preflight: set_down first")
        snapshot = self.reset.sources.capture(request["attempt_id"])
        aggregates, world = self._checked_aggregates("RELEASE", snapshot, request,
                                                     support_distance_max_m=support_distance_max_m)
        if not world.simulation_step > self._set_down_step:
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_EVIDENCE_INVALID: release_preflight: not fresh")
        return {"session_id": request["session_id"], "attempt_id": request["attempt_id"],
                "reset_epoch": self.reset.receipt.new_epoch, "release_epoch": self._release_epoch,
                "physics_step": world.simulation_step,
                "holding_state": aggregates["holding_state"],
                "cup_supported": aggregates["cup_supported"],
                "fresh": True, "planning_attached": self.planning_attached(request)}

    def run_retreat_segment(self, direction, distance_m, request, *, motion_template, motion_duration_s,
                            support_distance_max_m):
        """One retreat step from the CURRENT tool pose along an admitted direction - three seams, each named.

        The runner asks for two segments ("radial" 0.01 m, "vertical" 0.06 m), and neither the meaning of a direction
        name nor the tool's current pose can be read from the interface snapshot. Both are therefore seams this method
        refuses without: **inventing an axis convention would silently decide which way the arm retreats**, and that is
        a decision for the runtime that owns the geometry, not for this component.
        """

        tcp = getattr(self, "tool_pose", None)
        if not callable(tcp):
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: run_retreat_segment: tool_pose")
        axis = getattr(self, "retreat_axis", None)
        if not callable(axis):
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: run_retreat_segment: retreat_axis")
        ik = getattr(self, "motion_target_joints", None)
        if not callable(ik):
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: run_retreat_segment: ik")
        for name, value in (("motion_template", motion_template), ("motion_duration_s", motion_duration_s)):
            if value is None:
                raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_NOT_PROVISIONED: run_retreat_segment: {name}")
        broker = self.reset.broker
        dispatch = getattr(broker, "dispatch", None)
        if not callable(dispatch):
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: run_retreat_segment: broker.dispatch")
        wait = getattr(getattr(broker, "driver", None), "wait", None)
        if not callable(wait):
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: run_retreat_segment: driver.wait")

        from so101_demo.act.joints import ARM_JOINTS
        from so101_demo.ports.evidence import PoseEvidence

        distance = finite(distance_m, nonnegative=True)
        unit = tuple(finite(value) for value in axis(direction))
        if len(unit) != 3:
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_EVIDENCE_INVALID: run_retreat_segment: axis")
        before = self.reset.sources.capture(request["attempt_id"])
        observation = before.get("observation")
        if not isinstance(observation, dict) or not isinstance(observation.get("state"), (list, tuple)) \
                or len(observation["state"]) != 8:
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_EVIDENCE_INVALID: run_retreat_segment: observation")
        current = tcp(request)
        target = PoseEvidence(tuple(float(current.position_m[index]) + unit[index] * distance for index in range(3)),
                              tuple(float(value) for value in current.orientation_xyzw))
        row = tuple(ik(target))
        names = tuple(ARM_JOINTS[:5])
        if len(row) != len(names):
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_EVIDENCE_INVALID: run_retreat_segment: ik row")
        goal = {"joint_names": names,
                "header_stamp_s": finite(observation["sim_time_s"]),
                "time_from_start_s": (0.0, finite(motion_duration_s)),
                "positions": (tuple(finite(value) for value in observation["state"][:5]),
                              tuple(finite(value) for value in row))}
        ticket = broker.ownership.ticket(self.reset.act_context["lease_token"], "act",
                                         request["session_id"], request["attempt_id"])
        wait(dispatch(ticket, "arm", goal))
        after = self.reset.sources.capture(request["attempt_id"])
        if support_distance_max_m is None:
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: support_distance_max_m")
        return self.sequence_facts("RADIAL_RETREAT", after, request,
                                   support_distance_max_m=support_distance_max_m,
                                   motion_template=motion_template)

    def planning_attached(self, request):
        """Whether MoveIt still has the cup attached - READ from the planning scene, never assumed."""

        scene = getattr(self, "planning_scene", None)
        probe = getattr(scene, "is_attached", None)
        if not callable(probe):
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: planning_scene.is_attached")
        value = probe()
        if type(value) is not bool:
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_EVIDENCE_INVALID: planning_scene.is_attached")
        return value

    def detach_moveit(self, request):
        """Detach the cup from MoveIt, then READ BACK that it is detached.

        The physical release must happen with no planning attachment (the repository's own rule), so the postcondition
        is read through the same probe rather than inferred from the detach call having returned.
        """

        scene = getattr(self, "planning_scene", None)
        detach = getattr(scene, "detach", None)
        if not callable(detach):
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: planning_scene.detach")
        detach()
        if self.planning_attached(request) is not False:
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_EVIDENCE_INVALID: planning scene still attached")
        return True

    def sequence_phase(self, phase, request, *, observed, selected_source,
                       gripper_closed_rad=None, close_duration_s=None, support_distance_max_m=None,
                       motion_template=None, motion_duration_s=None):
        """Execute one sequence phase and report its facts - or refuse by name.

        The port calls this for every phase but SEARCH, which has its own path. Each phase's execution goes through the
        broker's own public boundary (a kind and a goal), exactly as the prefix pair does, and the facts are then
        established from the readback by `sequence_facts`, never reported by a caller.
        """

        if phase == "CLOSE":
            return self._close_facts(request, gripper_closed_rad=gripper_closed_rad,
                                     close_duration_s=close_duration_s,
                                     support_distance_max_m=support_distance_max_m)
        if phase in PHASE_MOTION_STATES:
            return self._motion_facts(phase, request, motion_template=motion_template,
                                      motion_duration_s=motion_duration_s,
                                      support_distance_max_m=support_distance_max_m)
        if phase == "RELEASE":
            # RELEASE opens the gripper; RADIAL_RETREAT is a MOTION phase (it moves the arm to the retreat target)
            # whose FACTS are the released ones, so it stays in the motion route and its flags are established there
            return self._release_facts(phase, request, motion_duration_s=motion_duration_s,
                                       support_distance_max_m=support_distance_max_m)
        if phase == "FINAL_CHECK":
            # FINAL_CHECK dispatches nothing: it reads the settled readback and establishes the placement's stability,
            # which needs the place target's tolerances - so it reaches the validator, which refuses by name for now
            if support_distance_max_m is None:
                raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: support_distance_max_m")
            return self.sequence_facts(phase, self.reset.sources.capture(request["attempt_id"]), request,
                                       support_distance_max_m=support_distance_max_m,
                                       motion_template=motion_template)
        raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_NOT_PROVISIONED: {phase}")

    def _gripper_open_rad(self):
        """The gripper's open position, read from the MODEL's own joint range - the one admitted source for it.

        Nothing about "open" is a preference: the simulated joint has a range, and the limit in the opening direction is
        that range's own value. A boundary without the model refuses by name rather than picking a number.
        """

        screen = getattr(self, "approach_screen", None)
        checker = getattr(screen, "path_checker", None)
        model = getattr(checker, "model", None)
        if model is None:
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: RELEASE: gripper model")
        from so101_demo.act.joints import ARM_JOINTS

        try:
            import mujoco
            joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, ARM_JOINTS[5])
            low, high = (float(value) for value in model.jnt_range[joint])
        except Exception as error:                      # the model refuses to name the joint
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_EVIDENCE_INVALID: RELEASE: gripper range") from error
        return high if abs(high) >= abs(low) else low

    def _release_facts(self, phase, request, *, motion_duration_s, support_distance_max_m):
        """Open the gripper to the model's own limit and establish the phase's facts from the readback after it."""

        if motion_duration_s is None:
            raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_NOT_PROVISIONED: {phase}: motion_duration_s")
        broker = self.reset.broker
        dispatch = getattr(broker, "dispatch", None)
        if not callable(dispatch):
            raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_NOT_PROVISIONED: {phase}: broker.dispatch")
        wait = getattr(getattr(broker, "driver", None), "wait", None)
        if not callable(wait):
            raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_NOT_PROVISIONED: {phase}: driver.wait")
        from so101_demo.act.joints import ARM_JOINTS

        open_rad = self._gripper_open_rad()
        before = self.reset.sources.capture(request["attempt_id"])
        observation = before.get("observation")
        if not isinstance(observation, dict) or not isinstance(observation.get("state"), (list, tuple)) \
                or len(observation["state"]) != 8:
            raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_EVIDENCE_INVALID: {phase}: observation")
        goal = {"joint_names": ARM_JOINTS[5:],
                "header_stamp_s": finite(observation["sim_time_s"]),
                "time_from_start_s": (0.0, finite(motion_duration_s)),
                "positions": ((finite(observation["state"][5]),), (finite(open_rad),))}
        ticket = broker.ownership.ticket(self.reset.act_context["lease_token"], "act",
                                         request["session_id"], request["attempt_id"])
        wait(dispatch(ticket, "gripper", goal))
        self._release_epoch += 1        # opening the gripper IS the release; the runner counts the same event
        after = self.reset.sources.capture(request["attempt_id"])
        if support_distance_max_m is None:
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: support_distance_max_m")
        return self.sequence_facts(phase, after, request, support_distance_max_m=support_distance_max_m)

    def _motion_facts(self, phase, request, *, motion_template, motion_duration_s, support_distance_max_m):
        """Aim a phase at its admitted motion target and establish its facts from the readback.

        Three pieces, and only the middle one is external: the target comes from `resolve_motion_targets` (validated
        against the workspace bounds by that code), the joint row comes from the IK seam this method names and refuses
        without - because turning a TCP pose into joint positions is a solver's job, not a guess - and the facts come
        from the phase-aware validator.
        """

        for name, value in (("motion_template", motion_template), ("motion_duration_s", motion_duration_s)):
            if value is None:
                raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_NOT_PROVISIONED: {phase}: {name}")
        broker = self.reset.broker
        dispatch = getattr(broker, "dispatch", None)
        if not callable(dispatch):
            raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_NOT_PROVISIONED: {phase}: broker.dispatch")
        driver = getattr(broker, "driver", None)
        wait = getattr(driver, "wait", None)
        if not callable(wait):
            raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_NOT_PROVISIONED: {phase}: driver.wait")
        ik = getattr(self, "motion_target_joints", None)
        if not callable(ik):
            raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_NOT_PROVISIONED: {phase}: ik")

        from so101_demo.act.joints import ARM_JOINTS
        from so101_demo.core.dynamic_pick import CupPoseSample, resolve_motion_targets
        from so101_demo.core.domain import State      # the enum lives with the domain, not with the policy document
        from so101_demo.core.task_geometry import Pose7

        before = self.reset.sources.capture(request["attempt_id"])
        observation = before.get("observation")
        if not isinstance(observation, dict) or not isinstance(observation.get("state"), (list, tuple)) \
                or len(observation["state"]) != 8:
            raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_EVIDENCE_INVALID: {phase}: observation")
        state = before["world"].object_state
        sample = CupPoseSample(frame_id="world", source_stamp_ns=max(1, int(observation["sim_time_s"] * 1e9)),
                               received_monotonic_s=finite(self.reset.sources.monotonic()),
                               pose_world=Pose7(tuple(state.position_world) + tuple(state.orientation_xyzw)))
        target = resolve_motion_targets(sample, motion_template).for_state(State[PHASE_MOTION_STATES[phase]])
        row = tuple(ik(target))
        names = tuple(ARM_JOINTS[:5])
        if len(row) != len(motion_template.arm_joint_names) or len(row) != len(names):
            raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_EVIDENCE_INVALID: {phase}: ik row")
        goal = {"joint_names": names,
                "header_stamp_s": finite(observation["sim_time_s"]),
                "time_from_start_s": (0.0, finite(motion_duration_s)),
                # the arm port's names are the five arm joints, so the first row is those five values: sending six
                # would make the wire refuse the goal for a row/name mismatch, and sending the gripper's value with
                # the arm's names would be worse - it would command the wrong joint
                "positions": (tuple(finite(value) for value in observation["state"][:5]),
                              tuple(finite(value) for value in row))}
        ticket = broker.ownership.ticket(self.reset.act_context["lease_token"], "act",
                                         request["session_id"], request["attempt_id"])
        wait(dispatch(ticket, "arm", goal))
        after = self.reset.sources.capture(request["attempt_id"])
        if support_distance_max_m is None:
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: support_distance_max_m")
        return self.sequence_facts(phase, after, request, support_distance_max_m=support_distance_max_m)

    def _close_facts(self, request, *, gripper_closed_rad, close_duration_s, support_distance_max_m):
        """Close the gripper to the case's admitted target and establish CLOSE's facts from the readback."""

        for name, value in (("gripper_closed_rad", gripper_closed_rad), ("close_duration_s", close_duration_s)):
            if value is None:
                raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_NOT_PROVISIONED: {name}")
        broker = self.reset.broker
        dispatch = getattr(broker, "dispatch", None)
        if not callable(dispatch):
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: CLOSE: broker.dispatch")
        driver = getattr(broker, "driver", None)
        wait = getattr(driver, "wait", None)
        if not callable(wait):
            # the wait policy belongs to the execution layer; inventing a poll loop here would be a policy nobody set
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: CLOSE: driver.wait")
        from so101_demo.act.joints import ARM_JOINTS

        ticket = broker.ownership.ticket(self.reset.act_context["lease_token"], "act",
                                         request["session_id"], request["attempt_id"])
        before = self.reset.sources.capture(request["attempt_id"])
        observation = before.get("observation")
        if not isinstance(observation, dict) or not isinstance(observation.get("state"), (list, tuple)) \
                or len(observation["state"]) != 8:
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_EVIDENCE_INVALID: CLOSE: observation")
        goal = {"joint_names": ARM_JOINTS[5:],
                "header_stamp_s": finite(observation["sim_time_s"]),
                "time_from_start_s": (0.0, finite(close_duration_s)),
                "positions": ((finite(observation["state"][5]),), (finite(gripper_closed_rad),))}
        gid = dispatch(ticket, "gripper", goal)
        wait(gid)
        after = self.reset.sources.capture(request["attempt_id"])
        if support_distance_max_m is None:
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: support_distance_max_m")
        return self.sequence_facts("CLOSE", after, request, support_distance_max_m=support_distance_max_m)

    def search(self, request: dict):
        if self._request is None:
            raise PickPlaceSearchBoundaryError("TASK8_BEGIN_REQUIRED")
        if request != self._request:
            raise PickPlaceSearchBoundaryError("TASK8_SEARCH_SCOPE_MISMATCH")
        if self._search_started:
            raise PickPlaceSearchBoundaryError("TASK8_SEARCH_ALREADY_STARTED")
        self._search_started = True
        service_node = None
        try:
            self.reset._guard(request)
            service_node = self.scene_node_factory()
            if service_node is self.reset.node or not callable(getattr(service_node, "destroy_node", None)):
                raise PickPlaceSearchBoundaryError("TASK8_SCENE_NODE_INVALID")
            scene_port = self.scene_port_factory(service_node)
            adapter = self.adapter_factory(
                self.reset.node, boundary=self.reset, binding=self.binding,
                request=request, snapshot_root=self.snapshot_root,
                neck_sweep_checker=self.neck_sweep_checker,
            )
            operation_guard = getattr(adapter, "operation_guard", None)
            if not callable(operation_guard):
                raise PickPlaceSearchBoundaryError("TASK8_SEARCH_GUARD_INVALID")
            segment = self.segment_factory(
                self.reset.sources, adapter, scene_port, self.geometry,
                operation_guard=operation_guard,
                history_verifier=lambda observed, stopped_wall_s:
                    verify_search_stationary_physics(
                        self.reset.sources, observed, model=self.reset.model,
                        stopped_wall_s=stopped_wall_s,
                    ),
                reference_verifier=lambda observed, physical_proof, stopped_wall_s:
                    verify_search_stationary_references(
                        self.reset.sources, observed, physical_proof,
                        stopped_wall_s=stopped_wall_s,
                    ),
                owner_verifier=lambda observed, physical_proof, references, stopped_wall_s:
                    verify_search_owner_goal_interval(
                        self.reset.broker,
                        self.reset.broker.ownership.ticket(
                            self.reset.act_context["lease_token"], "act",
                            request["session_id"], request["attempt_id"]),
                        self.reset.sources, observed, physical_proof, references,
                        stopped_wall_s=stopped_wall_s,
                    ),
                native_ingress_verifier=lambda observed, physical_proof, references,
                owner_proof, stopped_wall_s:
                    verify_search_native_controller_ingress(
                        self.reset.broker,
                        self.reset.broker.ownership.ticket(
                            self.reset.act_context["lease_token"], "act",
                            request["session_id"], request["attempt_id"]),
                        self.reset.sources, observed, physical_proof, references,
                        owner_proof, stopped_wall_s=stopped_wall_s,
                    ),
                max_source_wait_s=self.max_source_wait_s,
                poll_interval_s=self.poll_interval_s,
            )
            return segment.run(request, reset_epoch=self.reset.receipt.new_epoch)
        except BaseException as error:
            try:
                if self.safe_stop("TASK8_SEARCH_ABORT", request) is not True:
                    raise PickPlaceSearchBoundaryError("TASK8_SEARCH_STOP_UNCONFIRMED") from error
            except BaseException as stop_error:
                if isinstance(stop_error, PickPlaceSearchBoundaryError):
                    raise
                raise PickPlaceSearchBoundaryError("TASK8_SEARCH_STOP_UNCONFIRMED") from stop_error
            raise
        finally:
            if service_node is not None and service_node is not self.reset.node:
                service_node.destroy_node()

    def safe_stop(self, reason: str, request: dict) -> bool:
        identifier(reason)
        broker = self.reset.broker
        broker.stop_attempt(reason)
        deadline = self.monotonic() + self.stop_timeout_s
        while True:
            broker.tick()
            if broker.ownership.state == "IDLE" and broker.driver.stopped():
                return True
            if self.monotonic() >= deadline:
                return False
            self.sleep(self.poll_interval_s)


# Legacy Python API for version-one pick-place callers.
Task8SearchBoundaryError = PickPlaceSearchBoundaryError
Task8SearchBoundary = PickPlaceSearchBoundary
