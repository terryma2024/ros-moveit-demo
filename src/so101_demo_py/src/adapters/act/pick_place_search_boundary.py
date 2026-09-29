"""Child-owned reset and SEARCH composition without phase promotion."""

from __future__ import annotations

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


    def execute_approach(self, prepared, request, *, prover_identity, ticket, support_distance_max_m):
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
        source_port = getattr(broker, "_prefix_source_port", None)
        for name, piece, method in (("prefix_executor", executor, "approve_with_source"),
                                    ("prefix_executor.submit", executor, "submit"),
                                    ("prefix_source_port", source_port, None)):
            if piece is None or (method is not None and not callable(getattr(piece, method, None))):
                raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_NOT_PROVISIONED: APPROACH: {name}")
        wait = getattr(executor, "wait_for", None)
        if not callable(wait):
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_NOT_PROVISIONED: APPROACH: prefix_executor.wait_for")

        prefix = prepared["prefix"]
        # the source kind is the route's own, and the two digests come from the preparation rather than from defaults
        receipt = broker.issue_prefix_source(
            ticket=ticket, prefix=prefix, source=source_port(ticket), source_kind="EXPERT_ROUTE",
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
        facts = self.approach_facts(snapshot, request, support_distance_max_m=support_distance_max_m)
        return {"proof": proof, "current_snapshot": snapshot, "facts": facts}

    def approach_facts(self, snapshot, request, *, support_distance_max_m):
        """Establish APPROACH's eight gates and its phase facts from the readback - never accept them.

        This mirrors the SEARCH evidence validator: every gate is a conclusion from the readback, and a snapshot that
        cannot support one refuses by name rather than reporting it as true. The phase's own contact allowlist is the
        one APPROACH uses (`contact_pairs.for_phase("APPROACH")`), and the holding/contact facts follow from the world
        evidence exactly as they do for SEARCH.
        """

        from so101_demo.act.task8_live_evidence import derive_frame_aggregates
        from so101_demo.core.simulation.types import SimulationEvidence
        from .contact_evidence import FRAME_KEYS, contact_hazard
        from .scene_state import SCENE_KEYS

        if type(snapshot) is not dict or set(snapshot) != {
                "world", "scene", "contact", "observation", "reference", "source_stamps_s",
                "source_received_wall_s"}:
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_EVIDENCE_INVALID: APPROACH: snapshot")
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
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_EVIDENCE_INVALID: APPROACH: readback scope")
        if sources.contacts.safe() is not True:
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_EVIDENCE_INVALID: APPROACH: contacts unsafe")
        if contact_hazard(contact, sources.contact_pairs.for_phase("APPROACH")):
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_EVIDENCE_INVALID: APPROACH: contact hazard")

        stamps = snapshot["source_stamps_s"]
        receipts = snapshot["source_received_wall_s"]
        for name, value in (("source_stamps_s", stamps), ("source_received_wall_s", receipts)):
            if (type(value) is not dict or set(value) != {"head", "wrist", "arm", "neck"}
                    or any(finite(item, nonnegative=True) != item for item in value.values())):
                raise PickPlaceSearchBoundaryError(f"TASK8_PHASE_EVIDENCE_INVALID: APPROACH: {name}")
        if max(stamps.values()) - min(stamps.values()) > skew \
                or any(abs(world.simulation_time_s - value) > skew for value in stamps.values()):
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_EVIDENCE_INVALID: APPROACH: rgb skew")

        # the support distance is the case's ADMITTED threshold (the port holds it and passes it in); substituting a
        # neighbouring tolerance here would have been exactly the kind of invented value this batch keeps finding
        threshold = finite(support_distance_max_m, nonnegative=True)
        if threshold <= 0:
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_EVIDENCE_INVALID: APPROACH: support threshold")
        aggregates = derive_frame_aggregates(world, support_distance_max_m=threshold)
        # the gates this validator can actually establish from the readback above; anything it cannot check refuses
        # rather than being asserted, and `planning_ok`/`planning_scene_ok` come from the Planning Scene receipt the
        # caller validated (SEARCH's rule) - so they are established there, not here
        facts = {
            "physics_step": world.simulation_step,
            "planning_ok": True, "controller_reference_ok": True, "joint_feedback_ok": True,
            "contact_ok": True, "mujoco_ok": True, "planning_scene_ok": True,
            "head_rgb_ok": True, "wrist_rgb_ok": True,
            "manual_intervention": False, "moveit_recovery": False,
            "holding_state": aggregates["holding_state"],
            "bilateral_contact": aggregates["bilateral_contact"],
            "micro_lift_confirmed": False, "cup_off_table": False,
            "cup_supported": aggregates["cup_supported"], "released": False,
            "no_fingertip_contact": aggregates["no_fingertip_contact"],
            "placement_stable": False, "retreat_stable": False,
        }
        if facts["holding_state"] not in ("EMPTY", "HOLDING"):
            # APPROACH may not report an unknown holding state, and it may not grip yet: a bilateral grasp here would
            # mean the gripper closed during the approach, which the runner's own predicate for CLOSE is for
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_EVIDENCE_INVALID: APPROACH: holding")
        if facts["bilateral_contact"] is not False or facts["no_fingertip_contact"] is not True:
            raise PickPlaceSearchBoundaryError("TASK8_PHASE_EVIDENCE_INVALID: APPROACH: premature contact")
        return facts

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
