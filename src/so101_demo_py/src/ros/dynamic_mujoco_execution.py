"""MuJoCo execution adapter for the perception-driven shared workflow."""

from __future__ import annotations

import copy
import json
import math
import os
import sys
import time
from pathlib import Path
from dataclasses import asdict, replace
from typing import Any

from ..application.e2e_acceptance import (
    FINAL_MAX_ANGULAR_SPEED_RAD_S,
    FINAL_MAX_LINEAR_SPEED_M_S,
    FINAL_MAX_UPRIGHT_TILT_RAD,
    FINAL_SUPPORT_HEIGHT_RANGE_M,
    FINAL_XY_TOLERANCE_M,
)
from ..control.gripper.client import GripperClient
from ..control.moveit.deterministic_horizon import (
    MOVE_ABOVE_PLAN_CANDIDATE_COUNT,
    HorizonStep,
    HorizonWaypoint,
    cartesian_candidate_score,
    interpolated_move_above_waypoints,
    solve_horizon,
    validate_cartesian_corridor,
)
from ..control.moveit.planning import JointPlanRequest, MoveItPlanningClient
from ..control.moveit.pose_ik import create_pose_ik, describe_pose_ik
from ..control.planning_scene.acm import set_collision_allowed
from ..control.trajectory.executor import (
    MoveItExecutionClient,
    SustainedConditionGuard,
    make_execute_goal,
)
from ..application.staged_approach import maximum_joint_error
from ..core.domain import ActionResult, ActionStatus, Failure, FailureCategory, State
from ..core.workflow import TERMINAL_STOP_CODES
from ..core.dynamic_pick import (
    DynamicPickTemplate,
    ResolvedMotionTargets,
    compose_pose,
    inverse_pose,
)
from ..ports.evidence import PoseEvidence
from .task_reachability import _compute_while_progressing
from .teacher_safety import evaluate_cup_contacts
from .teacher_stop import TeacherStop


MANIFEST_SCHEMA = "so101-dynamic-mujoco-execute-v2"
# Controller stop confirmation for the Teacher end observation: the existing driver stop baseline (D5).
_TEACHER_STOP_VELOCITY_RAD_S = 0.002
# Bounded wait for the stream's publisher thread to drain at close; a stuck publisher is abandoned, never waited for.
_STREAM_FLUSH_S = 1.0
# Execution errors that mean "the controller outcome was never settled" rather than "the execution failed".
_CONTROLLER_UNSETTLED_CODES = frozenset({
    "GRIPPER_GOAL_TIMEOUT", "GRIPPER_RESULT_TIMEOUT", "MOVEIT_EXECUTION_GOAL_TIMEOUT", "MOVEIT_EXECUTION_TIMEOUT",
    "TEACHER_CANCEL_UNSETTLED",
})
# Plan start drift: the plan's first point against the latest measured arm joints (same bound as `qualified_phases`).
_PLAN_START_DRIFT_MAX_RAD = 0.01
# Defaults for a partially constructed adapter only; the frozen `teacher_execution_policy_v1.yaml` is always used when
# it is loaded, and the Teacher refuses to start without it.
_DEFAULT_STATE_MAX_AGE_S = 0.5
#: tolerance of the 100 ms place-height stability window, on both sides (simulation time is a float sum of steps)
_WINDOW_TOLERANCE_S = 1e-6
_DEFAULT_STATE_UNAVAILABLE_STOP_S = 1.0


class _ExecutionFailed(RuntimeError):
    """A non-stop failure of one trajectory execution; carries the `ActionResult` for the terminal-pose reconciliation."""

    def __init__(self, message: str, result: ActionResult) -> None:
        super().__init__(message)
        self.result = result


def _mark_phase(name):
    """D30, observation only: mark the active phase timer if any; never raises."""
    try:
        from .dynamic_runtime import _mark_active_phase
        _mark_active_phase(name)
    except Exception:
        pass


# Burst-spin budget (S3). `rclpy.spin_once` runs at most one callback, while evidence, scene, joint-state, chunk and
# camera callbacks arrive at hundreds per second in total (scenes alone at 100 Hz), so one spin per progress call left
# the depth-256 queues seconds behind. A zero-timeout spin costs well under 0.2 ms when a callback is ready, so 10 ms
# drains dozens of queued callbacks per call and keeps the added latency of one progress call at about 10 ms.
_SPIN_BURST_BUDGET_S = 0.010
# Characters kept of an error text recorded in the manifest.
_DATA_REASON_MAX_CHARS = 300


def _spin_burst(node, first_timeout_s=0.01, budget_s=_SPIN_BURST_BUDGET_S, spin=None):
    """One `spin_once(timeout_sec=first_timeout_s)`, then zero-timeout spins until `budget_s` has elapsed.

    Scheduling only: every callback runs exactly as before, just sooner and in larger batches. Exceptions from
    `spin` propagate unchanged. `spin` defaults to `rclpy.spin_once`.
    """
    if spin is None:
        import rclpy
        spin = rclpy.spin_once
    began = time.monotonic()
    spin(node, timeout_sec=first_timeout_s)
    while time.monotonic() - began < budget_s:
        spin(node, timeout_sec=0.0)



class RosDynamicMujocoExecution:
    """Execute one dynamic run while preserving the repository workflow states."""

    _ARM_JOINTS = ("1", "2", "3", "4", "5")
    _PREOPEN_Q6 = 0.465038
    _CLOSE_Q6 = -0.0485   # the plain dynamic_cup_pick_place close; the ACT Teacher's is the frozen policy value
    _RELEASE_Q6 = 0.75
    _MAX_FORCE_N = 11.60

    @staticmethod
    def _workflow_identity_fields(
        workflow_id: str | None, request_id: str | None
    ) -> dict[str, str]:
        if workflow_id is None and request_id is None:
            return {}
        if (
            type(workflow_id) is not str
            or not workflow_id.strip()
            or type(request_id) is not str
            or not request_id.strip()
        ):
            raise ValueError("dynamic execution provenance is incomplete")
        return {"workflow_id": workflow_id, "request_id": request_id}

    @staticmethod
    def _parallel_identity_fields(identity) -> dict[str, object]:
        if identity is None:
            return {}
        fields = {
            "batch_id", "coordinator_epoch", "worker_id", "worker_generation",
            "point_id", "attempt_id", "lease_generation",
        }
        if type(identity) is not dict or set(identity) != fields:
            raise ValueError("dynamic parallel lease identity is incomplete")
        for name in ("batch_id", "worker_id", "point_id", "attempt_id"):
            if not isinstance(identity[name], str) or not identity[name]:
                raise ValueError("dynamic parallel lease identity is invalid")
        for name in (
            "coordinator_epoch", "worker_generation", "lease_generation"
        ):
            if type(identity[name]) is not int or identity[name] <= 0:
                raise ValueError("dynamic parallel lease identity is invalid")
        return {"parallel_lease_identity": dict(identity)}

    def __init__(
        self,
        node: Any,
        template: DynamicPickTemplate,
        targets: ResolvedMotionTargets,
        *,
        session_id: str,
        expected_reset_epoch: int,
        evidence_file: Path,
        urdf_path: Path,
        policy_path: Path,
        policy_sha256: str,
        workflow_id: str | None = None,
        request_id: str | None = None,
        parallel_lease_identity: dict[str, object] | None = None,
        event_stream=None,
        ik_backend: str | None = None,
    ) -> None:
        from control_msgs.action import FollowJointTrajectory
        from moveit_msgs.action import ExecuteTrajectory
        from moveit_msgs.srv import ApplyPlanningScene, GetMotionPlan, GetPlanningScene
        from rclpy.action import ActionClient
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import JointState

        from ..backends.mujoco.observer import MujocoWorldObserver

        workflow_identity = self._workflow_identity_fields(workflow_id, request_id)
        parallel_identity = self._parallel_identity_fields(parallel_lease_identity)
        if not session_id or expected_reset_epoch < 0:
            raise ValueError("dynamic execution provenance is incomplete")
        self._node = node
        self._template = template
        self._targets = targets
        self._session_id = session_id
        self._expected_reset_epoch = expected_reset_epoch
        self._evidence_file = evidence_file
        self._ik = create_pose_ik(
            urdf_path,
            template.arm_joint_names,
            template.planning_frame,
            template.tcp_link,
            backend=ik_backend,
        )
        self._positions: dict[str, float] = {}
        self._joint_state_generation = 0
        self._joint_state_source_stamp_ns: int | None = None
        self._joint_state_received_monotonic_s: float | None = None
        self._state_events: list[dict[str, object]] = []
        self._planning_attempts: list[dict[str, object]] = []
        self._pick_horizon_steps: dict[State, tuple[HorizonStep, ...]] = {}
        self._final_samples: list[dict[str, object]] = []
        self._release_marker_sequence: int | None = None
        self._attached = False
        self._initial = None
        self._before_micro_lift = None
        self._scene_readback: dict[str, object] | None = None
        self._task_geometry = None
        self._last_scene_response = None
        self._release_authorization = None
        self._release_scene_geometry = None
        self._scene_source_observer = None
        self._monotonic = time.monotonic
        from ..act.endpoint_pose_acceptance import load_development_runtime

        runtime_policy_path = urdf_path.parents[2] / "config/act/endpoint_pose_development_runtime_v1.yaml"
        self._release_runtime_policy = load_development_runtime(runtime_policy_path)
        # The release scope is (session, reset epoch, attempt). There is no lease: nothing here asks for one.
        lease = parallel_identity.get("parallel_lease_identity")
        self._attempt_id = (lease["attempt_id"] if lease is not None else (request_id or workflow_id or "standalone"))
        # Stop and safety ports, set by the entry (`run_dynamic_execute`); None means the original pick-place behaviour.
        self._stop_flags = None
        self._safety_limits = None
        self._collision_watch = None
        self._physics_hazard_watch = None
        self._stop_suspended = False
        self._unavailable_since = None
        self._last_arm_result = None
        self._safety_state = None
        from ..act.teacher_event_stream import StreamEventSink
        # One-way, bounded and non-blocking: the Teacher publishes its execution facts to the /so101/teacher/events
        # stream for the independent Recorder process. The Teacher holds no data side: there is nothing here that reads
        # the Recorder, a capture or an episode.
        self._event_sink = StreamEventSink(None)
        self._event_stream = None
        self._event_stream_error = None
        # `event_stream` is the one the entry started before the first scene call (so the setup scene is on it too).
        self._start_event_stream(node, session_id, expected_reset_epoch,
                                 parallel_identity.get("parallel_lease_identity"), request_id, existing=event_stream)
        self._touch_collision_allowed = False
        self._joint_subscription = node.create_subscription(
            JointState,
            "/joint_states",
            self._on_joint_state,
            qos_profile_sensor_data,
        )
        self.observer = MujocoWorldObserver(
            node, session_id, max_age_s=0.5, subscription_depth=256,
            # Buffer capacity (about 40 s at 50 Hz), not a threshold: originals must outlive slow off-thread admission.
            history_capacity=2048)
        self._planning = MoveItPlanningClient(
            node.create_client(GetMotionPlan, "/plan_kinematic_path"),
            progress=self._wait_progress,  # no goal is active while MoveIt plans: a stop flag may end this wait
        )
        self._trajectory = MoveItExecutionClient(
            ActionClient(node, ExecuteTrajectory, "/execute_trajectory"),
            goal_factory=make_execute_goal,
            progress=self._progress,
        )
        self._gripper = GripperClient(
            ActionClient(
                node,
                FollowJointTrajectory,
                "/gripper_controller/follow_joint_trajectory",
            ),
            progress=self._progress,
        )
        self._apply_scene = node.create_client(ApplyPlanningScene, "/apply_planning_scene")
        self._get_scene = node.create_client(GetPlanningScene, "/get_planning_scene")
        self._scene_service_calls: list[dict] = []
        self._load_teacher_policies(urdf_path)
        self._document: dict[str, object] = {
            "schema": MANIFEST_SCHEMA,
            "status": "RUNNING",
            "simulation_session_id": session_id,
            "expected_reset_epoch": expected_reset_epoch,
            "policy_path": str(policy_path),
            "policy_sha256": policy_sha256,
            "ik_solver": describe_pose_ik(self._ik),
            "input_cup_pose_world": list(targets.input_pose.pose_world.values),
            "input_frame_id": targets.input_pose.frame_id,
            "input_source_stamp_ns": targets.input_pose.source_stamp_ns,
            "resolved_targets": {
                state.value: [*pose.position_m, *pose.orientation_xyzw]
                for state, pose in sorted(targets.targets.items(), key=lambda item: item[0].value)
            },
            "state_events": self._state_events,
            "planning_attempts": self._planning_attempts,
            "final_samples": self._final_samples,
            "scene_service_calls": self._scene_service_calls,
            "process_diagnostics": [],
            "teacher_policies": self._teacher_policy_files,
        }
        if self._teacher_config_error is not None:
            self._document["teacher_config_error"] = self._teacher_config_error
        if self._event_stream_error is not None:
            self._document["teacher_event_stream"] = {"error": self._event_stream_error}
        self._document.update(workflow_identity)
        self._document.update(parallel_identity)
        self._write()

    @property
    def evidence_file(self) -> Path:
        return self._evidence_file

    def _write(self) -> None:
        self._evidence_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._evidence_file.with_name(f".{self._evidence_file.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(self._document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self._evidence_file)

    # ---- Teacher event stream (Phase A4a): /so101/teacher/events for the independent Recorder process --------------------
    # The Teacher thread only offers events to a bounded queue (never waits, never raises). A publisher thread drains it.

    def _start_event_stream(self, node, session_id, reset_epoch, lease_identity, request_id, *, existing=None) -> None:
        """Use (or create) the ROS publisher and the stream. Any failure leaves the Teacher without a stream, never
        without a run."""
        from ..act.teacher_event_stream import StreamEventSink

        if existing is not None:
            self._event_stream = existing
            self._event_sink = StreamEventSink(existing)
            return
        from ..adapters.act.ros_teacher_event_stream import start_teacher_event_stream

        stream, close, error = start_teacher_event_stream(node, session_id, reset_epoch, lease_identity, request_id)
        if stream is None:
            self._event_stream, self._event_stream_error = None, error
            return
        stream.close_publisher = close
        self._event_stream = stream
        self._event_sink = StreamEventSink(stream)

    def _stream_emit(self, event_type, payload) -> None:
        """Offer one Teacher fact to the stream. Never blocks, never raises into control."""
        try:
            stream = getattr(self, "_event_stream", None)
            if stream is not None:
                stream.offer(event_type, payload)
        except Exception:
            pass

    def _stream_manifest_block(self) -> None:
        """Record the drop counter and last published seq in the manifest (best effort, never raises)."""
        try:
            stream = getattr(self, "_event_stream", None)
            if stream is not None:
                self._document["teacher_event_stream"] = stream.snapshot()
        except Exception:
            pass

    def _close_event_stream(self) -> None:
        """Flush the stream (bounded), publish the final counters and release the ROS publisher. Never raises."""
        try:
            stream = getattr(self, "_event_stream", None)
            if stream is None:
                return
            stream.close(flush_timeout_s=_STREAM_FLUSH_S)
            self._stream_manifest_block()
            try:
                self._write()
            except Exception:
                pass
            closer = getattr(stream, "close_publisher", None)
            if callable(closer):
                closer()
        except Exception:
            pass

    # ---- Teacher result (Phase A1b): start/end observation, endpoint verdict, audit-only diagnostics -----------------
    # The Teacher decides its own task result from the cup's start and end pose in the executed world. Nothing here
    # reads the episode recorder, the capture or the phase port, so a Teacher without a recorder runs unchanged.

    def _load_teacher_policies(self, urdf_path) -> None:
        """Load both frozen Teacher policy documents from the installed share config dir the runtime already uses."""

        import hashlib

        from ..act.teacher_endpoint import load_teacher_endpoint_policy, load_teacher_execution_policy

        self._teacher_config_error = None
        self._teacher_policy_files = {}
        self._teacher_endpoint_policy = None
        self._teacher_execution_policy = None
        try:
            config_dir = Path(urdf_path).parents[2] / "config/act"
            self._teacher_config_dir = config_dir
            endpoint_path = config_dir / "teacher_endpoint_v2.yaml"
            execution_path = config_dir / "teacher_execution_policy_v1.yaml"
            endpoint_bytes, execution_bytes = endpoint_path.read_bytes(), execution_path.read_bytes()
        except (OSError, IndexError) as error:
            self._teacher_config_error = f"TEACHER_POLICY_UNAVAILABLE: {error}"
            return
        try:
            self._teacher_endpoint_policy = load_teacher_endpoint_policy(endpoint_bytes)
            self._teacher_execution_policy = load_teacher_execution_policy(execution_bytes)
        except ValueError as error:
            self._teacher_config_error = str(error)
            return
        self._teacher_policy_files = {
            "endpoint": {"path": str(endpoint_path), "file_sha256": hashlib.sha256(endpoint_bytes).hexdigest(),
                         "policy_sha256": self._teacher_endpoint_policy["policy_sha256"]},
            "execution": {"path": str(execution_path), "file_sha256": hashlib.sha256(execution_bytes).hexdigest(),
                          "policy_sha256": self._teacher_execution_policy["policy_sha256"]},
        }

    def _select_execution_policy(self, file_name: str) -> None:
        """Load the execution policy the freeze names (``teacher_execution_policy_v1.yaml`` or ``..._v2.yaml``) instead of the default."""

        import hashlib

        from ..act.teacher_endpoint import load_teacher_execution_policy

        config_dir = getattr(self, "_teacher_config_dir", None)
        if config_dir is None:
            return                                      # the policies did not load at all: the config error is already set
        path = config_dir / file_name
        try:
            raw = path.read_bytes()
            policy = load_teacher_execution_policy(raw)
        except (OSError, ValueError) as error:
            self._teacher_execution_policy = None
            self._teacher_config_error = f"TEACHER_POLICY_UNAVAILABLE: {error}"
            return
        self._teacher_execution_policy = policy
        files = getattr(self, "_teacher_policy_files", None)
        if files:
            files["execution"] = {"path": str(path), "file_sha256": hashlib.sha256(raw).hexdigest(),
                                  "policy_sha256": policy["policy_sha256"]}

    @staticmethod
    def _teacher_pose_document(values) -> dict[str, object]:
        x, y, z, qx, qy, qz, qw = (float(item) for item in values)
        norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
        if not norm > 0.0:
            norm = 1.0
        return {"position": [x, y, z],
                "orientation": {"x": qx / norm, "y": qy / norm, "z": qz / norm, "w": qw / norm}}

    def _teacher_targets(self) -> tuple[dict[str, object], dict[str, object]]:
        """(start_target, end_target), both frozen before the first motion.

        The start target is the input cup pose this run was resolved from. The end target is the place pose today's
        VALIDATE_FINAL_PLACEMENT frozen (XY and attitude of the expected cup pose); its height is the input cup's
        resting height, because that expected pose is a TCP-derived geometric pose, not a table-resting height.
        """

        start_values = tuple(self._targets.input_pose.pose_world.values)
        expected = compose_pose(self._template.place_tcp_world, inverse_pose(self._template.cup_to_tcp_grasp))
        end_values = (expected.values[0], expected.values[1], start_values[2], *expected.values[3:7])
        return self._teacher_pose_document(start_values), self._teacher_pose_document(end_values)

    @staticmethod
    def _teacher_observation(value) -> dict[str, object]:
        x, y, z, w = value.object_state.orientation_xyzw
        return {
            "position": list(value.object_state.position_world),
            "orientation": {"x": x, "y": y, "z": z, "w": w},
            "simulation_time_s": value.simulation_time_s,
            "frame_id": value.frame_id,
            "object_id": value.object_state.body,
            "session_id": value.simulation_session_id,
            "reset_epoch": value.reset_epoch,
            "publisher_sequence": value.publisher_sequence,
            "simulation_step": value.simulation_step,
        }

    def _capture_teacher_start(self):
        """Refuse an invalid config, then read the one start observation before any arm or gripper motion.

        Returns the snapshot, or None when the object was built without the Teacher policies (legacy partial
        construction). The pre-motion config checks are the only reason this raises.
        """

        error = getattr(self, "_teacher_config_error", None)
        if error is not None:
            self._document["teacher_config_error"] = error
            raise RuntimeError(error)
        policy = getattr(self, "_teacher_endpoint_policy", None)
        if policy is None:
            return None
        from ..act.teacher_endpoint import validate_task_targets

        self._check_place_geometry_before_motion()
        start_target, end_target = self._teacher_targets()
        try:
            validate_task_targets(policy, start_target, end_target)
        except ValueError as invalid:
            self._document["teacher_config_error"] = str(invalid)
            self._write()
            raise RuntimeError(str(invalid)) from invalid
        self._document["teacher_targets"] = {"start_target": start_target, "end_target": end_target}
        snapshot = self._snapshot()
        self._document["teacher_start_observation"] = self._teacher_observation(snapshot)
        self._write()
        observation = self._document["teacher_start_observation"]
        boundary = self._verified_reset_boundary() or observation
        self._stream_emit("reset_complete", {
            "session_id": boundary["session_id"], "reset_epoch": boundary["reset_epoch"],
            "simulation_time_s": boundary["simulation_time_s"],
            "simulation_step": boundary["simulation_step"],
            "publisher_sequence": boundary["publisher_sequence"],
            # the receipt of that first evidence on the monotonic clock, for the Recorder's causal ordering
            "received_monotonic_ns": boundary.get("received_monotonic_ns", time.monotonic_ns())})
        self._stream_emit("teacher_start_observation", {"observation": copy.deepcopy(observation)})
        return snapshot

    def _check_place_geometry_before_motion(self) -> None:
        """Policy v2 only: load and hash-check the scene geometry before any motion, so a bad scene refuses at the start of the
        run instead of with the cup held at the place pose. Raises a terminal ``TEACHER_PLACE_*`` stop."""

        policy = getattr(self, "_teacher_execution_policy", None)
        if (policy is None or not policy.get("place_height_mode")
                or getattr(self, "_execution_snapshot_root", None) is None):
            return
        from ..core.place_height import (
            HEIGHT_OUT_OF_BOUNDS, MEASUREMENT_FAILED, PlaceHeightPolicy, PlaceHeightRefused)

        try:
            height_policy = PlaceHeightPolicy.from_document(policy)
            geometry = self._place_geometry()
            if geometry.scene_sha256 != height_policy.scene_sha256:
                raise PlaceHeightRefused(
                    HEIGHT_OUT_OF_BOUNDS, "the scene model is not the one the place geometry was fitted for")
        except PlaceHeightRefused as refusal:
            self._document["place_height"] = {"mode": policy["place_height_mode"], "refused": refusal.code,
                                             "detail": str(refusal)[:300]}
            self._write()
            raise TeacherStop(refusal.code, str(refusal)) from refusal
        except Exception as error:
            self._document["place_height"] = {"mode": policy["place_height_mode"], "refused": MEASUREMENT_FAILED,
                                             "detail": f"{type(error).__name__}: {error}"[:300]}
            self._write()
            raise TeacherStop(MEASUREMENT_FAILED, f"{type(error).__name__}: {error}"[:300]) from error

    def _verified_reset_boundary(self):
        """The first retained `SimulationEvidence` of this session and the expected reset epoch, or None.

        This is the reset boundary the Teacher announces as `reset_complete`: the first sample the Teacher's own
        observer saw after the reset, not a later snapshot, and independent of whoever ran the reset.
        """
        try:
            retained = self.observer.retained_with_receipts()
        except Exception:
            return None
        for record in retained:
            value = record.evidence
            if value.simulation_session_id == self._session_id and value.reset_epoch == self._expected_reset_epoch:
                return {**self._teacher_observation(value),
                        "received_monotonic_ns": round(record.received_monotonic_s * 1e9)}
        return None

    def _controllers_stopped_at(self, execution_policy):
        """Receipt time (the observer's monotonic clock) of the fresh joint state that showed every arm and gripper
        joint below the stop velocity, or None.

        Bounded by the execution policy's state_unavailable_stop_s; missing, stale or undersized velocity data
        never counts as stopped. A stop flag ends the wait.
        """

        clock = getattr(self, "_monotonic", time.monotonic)
        deadline = clock() + execution_policy["state_unavailable_stop_s"]
        while True:
            received = getattr(self, "_joint_state_received_monotonic_s", None)
            velocities = getattr(self, "_joint_velocities", {})
            fresh = received is not None and 0.0 <= clock() - received <= execution_policy["state_max_age_s"]
            if fresh and all(
                    isinstance(velocities.get(name), (int, float)) and math.isfinite(velocities[name])
                    and abs(velocities[name]) <= _TEACHER_STOP_VELOCITY_RAD_S
                    for name in (*self._ARM_JOINTS, "6")):
                return received
            if clock() >= deadline:
                return None
            self._wait_progress()

    def _controllers_stopped(self, execution_policy) -> bool:
        """True once fresh joint states show every arm and gripper joint below the stop velocity."""
        return self._controllers_stopped_at(execution_policy) is not None

    def _settled_snapshot(self, settle_s: float, stall_s: float):
        """One world snapshot taken settle_s of simulation time after the first fresh one.

        The clock is the MuJoCo publisher's simulation time carried by the world snapshots, so the wait is in
        simulation time whatever the node clock is. It fails if simulation time stops advancing for stall_s.
        """

        clock = getattr(self, "_monotonic", time.monotonic)
        latest = self._snapshot()
        target_s = latest.simulation_time_s + settle_s
        advanced_at = clock()
        while latest.simulation_time_s < target_s:
            if clock() - advanced_at > stall_s:
                raise RuntimeError("TEACHER_END_SETTLE_CLOCK_STALLED")
            candidate = self._snapshot()
            if candidate.simulation_time_s > latest.simulation_time_s:
                latest, advanced_at = candidate, clock()
        return latest

    def _take_teacher_end_observation(self):
        """(observation or None, problem or None): stop check first, then settle_s, then ONE snapshot."""

        policy = getattr(self, "_teacher_endpoint_policy", None)
        execution_policy = getattr(self, "_teacher_execution_policy", None)
        if policy is None or execution_policy is None:
            return None, "TEACHER_ENDPOINT_POLICY_UNAVAILABLE"
        try:
            if not self._controllers_stopped(execution_policy):
                return None, "TEACHER_END_CONTROLLER_STOP_UNCONFIRMED"
            snapshot = self._settled_snapshot(policy["tolerances"]["settle_s"],
                                              execution_policy["state_unavailable_stop_s"])
        except Exception as error:
            return None, f"TEACHER_END_OBSERVATION_UNAVAILABLE: {error}"
        return self._teacher_observation(snapshot), None

    @staticmethod
    def _teacher_execution_status(result, failure_evidence) -> str:
        if result.status.value == "DONE":
            return "COMPLETED"
        code = "" if result.failure is None else result.failure.code
        config_code = code.startswith(("TEACHER_ENDPOINT_", "TEACHER_POLICY_", "TEACHER_EXECUTION_POLICY_"))
        if code in ("TEACHER_USER_STOP", "TEACHER_PARENT_DIED"):
            return "STOPPED_USER"
        if code == "TEACHER_DEADLINE":
            return "DEADLINE"
        if not config_code and code != "TEACHER_CANCEL_UNSETTLED" and (code in TERMINAL_STOP_CODES or code.startswith(
                ("DYNAMIC_RELEASE_", "DYNAMIC_NORMAL_STOP_", "TEACHER_"))):
            return "STOPPED_SAFETY"
        action_absent = bool((failure_evidence or {}).get("physical_action_proven_absent"))
        if code in _CONTROLLER_UNSETTLED_CODES and not action_absent:
            return "INDETERMINATE"
        return "FAILED"

    def _teacher_manifest_fields(self, result, failure_evidence, end_observation, end_problem) -> dict[str, object]:
        """The v2 Teacher fields. PASS only for a COMPLETED execution whose endpoint judgement is PASS."""

        from ..act.teacher_endpoint import RULE_VERSION, evaluate_teacher_endpoint

        execution = self._teacher_execution_status(result, failure_evidence)
        start_observation = self._document.get("teacher_start_observation")
        targets = self._document.get("teacher_targets") or {}
        policy = getattr(self, "_teacher_endpoint_policy", None)
        reasons: list[str] = []
        try:
            if policy is None or not targets:
                raise ValueError(self._document.get("teacher_config_error") or getattr(
                    self, "_teacher_config_error", None) or "TEACHER_ENDPOINT_TARGETS_UNAVAILABLE")
            task = evaluate_teacher_endpoint(
                policy, start_target=targets["start_target"], end_target=targets["end_target"],
                start_observation=start_observation, end_observation=end_observation)
        except Exception as error:
            reasons.append(str(error))
            task = {
                "rule_version": RULE_VERSION, "policy_sha256": None if policy is None else policy["policy_sha256"],
                "result": "UNCONFIRMED", "reasons": reasons, "measured": None,
                "start_target": targets.get("start_target"), "end_target": targets.get("end_target"),
                "start_observation": start_observation, "end_observation": end_observation,
            }
        if end_problem is not None:
            task["reasons"] = [end_problem, *task["reasons"]]
        if execution != "COMPLETED" and task["result"] == "PASS":
            task["result"] = "UNCONFIRMED"
            task["reasons"] = ["TEACHER_EXECUTION_NOT_COMPLETED", *task["reasons"]]
        return {
            "schema": MANIFEST_SCHEMA,
            "teacher_execution_status": execution,
            "teacher_task_result": task,
            "teacher_start_observation": start_observation,
            "teacher_end_observation": end_observation,
            # The Teacher holds no data side. The data status of an attempt is the independent Recorder's
            # (`recorder-result.json`), mapped by the orchestrator; this field only says the Teacher recorded nothing.
            "act_data_status": "DISABLED",
            "process_diagnostics": self._document.setdefault("process_diagnostics", []),
            "teacher_policies": getattr(self, "_teacher_policy_files", {}),
        }

    @staticmethod
    def _contact_documents(items) -> list[dict[str, object]]:
        return [
            {
                "geom1": getattr(item, "geom1", None),
                "geom2": getattr(item, "geom2", None),
                "position_world_m": (None if getattr(item, "position_world", None) is None
                                     else list(item.position_world)),
                "signed_distance_m": getattr(item, "signed_distance_m", None),
                "normal_force_n": getattr(item, "normal_force_n", None),
            }
            for item in items
        ]

    def _record_process_diagnostic(self, code: str, state, *, sample=None, facts=None, **details) -> None:
        """Record one audit-only process-quality observation. Never raises into, cancels or fails the state.

        The first occurrence of a code in a state is written with its sample and contacts; repeats only count.
        """

        try:
            key = (code, None if state is None else state.value)
            index = self.__dict__.setdefault("_process_diagnostic_index", {})
            if key in index:
                index[key]["count"] += 1
                return
            entry: dict[str, object] = {
                "code": code, "state": key[1], "audit_only": True, "count": 1,
                "monotonic_s": getattr(self, "_monotonic", time.monotonic)(), **details,
            }
            if facts is not None:
                entry["facts"] = facts
            if sample is not None:
                entry["sample"] = self._evidence(sample)
                entry["contacts"] = {
                    "left": self._contact_documents(sample.left_fingertip_contacts),
                    "right": self._contact_documents(sample.right_fingertip_contacts),
                    "other": self._contact_documents(sample.other_object_contacts),
                }
            index[key] = entry
            self._document.setdefault("process_diagnostics", []).append(entry)
            self._write()
        except Exception as error:
            print(f"DYNAMIC_PROCESS_DIAGNOSTIC_FAILED {code} {error}", file=sys.stderr, flush=True)

    # Set by the entry that starts an external Recorder (`--collection on`). Off by default: a Teacher with no Recorder
    # issues no extra stop request.
    final_stop_proof_enabled = False

    def _publish_final_normal_stop(self) -> None:
        """Publish the confirmed normal-stop proof after the sequence closed, for the Recorder's final boundary.

        Teacher side, after its own sequence: the owner's stop baseline is the one the release preflight already uses.
        A failure is recorded in the manifest and never changes the Teacher result.
        """
        if not self.final_stop_proof_enabled:
            return
        try:
            proof = self._normal_stop_proof()
            self._publish_teacher_event("normal_stop", {"proof": proof})
        except Exception as error:
            self._document["teacher_final_stop_error"] = str(error)[:_DATA_REASON_MAX_CHARS]

    def finish(self, result) -> None:
        # After a stop the flags stay set: the failure evidence, the end observation and the manifest are still taken.
        self._stop_suspended = True
        failure_evidence = None
        done = result.status.value == "DONE"
        if done:
            self._publish_final_normal_stop()
        if not done:
            failure_evidence = self._capture_failure_evidence(result)
        end_observation = end_problem = None
        if done:
            end_observation, end_problem = self._take_teacher_end_observation()
        self._document.update(self._teacher_manifest_fields(result, failure_evidence, end_observation, end_problem))
        self._stream_emit("teacher_end_observation", {
            "observation": copy.deepcopy(end_observation),
            "problem": end_problem})
        self._document.update(
            {
                "status": "DONE" if done else "ERROR",
                "current_state": result.current_state.value,
                "transition_count": result.transition_count,
                "state_trace": [state.value for state in result.state_trace],
                "failure": None if result.failure is None else result.failure.code,
                "release_marker_sequence": self._release_marker_sequence,
                "planning_scene_readback": self._scene_readback,
                "failure_evidence": failure_evidence,
            }
        )
        self._stream_emit("terminal", {
            "status": self._document["status"],
            "teacher_execution_status": self._document["teacher_execution_status"],
            "teacher_task_result": self._document["teacher_task_result"]["result"],
            "failure": self._document["failure"]})
        self._stream_manifest_block()
        self._write()

    @staticmethod
    def _failure_boundary(state_trace, failure=None) -> State | None:
        from ..core.workflow import SO101_WORKFLOW

        terminal = failure is not None and failure.code in TERMINAL_STOP_CODES
        for current, following in zip(state_trace, state_trace[1:]):
            transition = SO101_WORKFLOW.transitions.get(current)
            if transition is not None and (following is transition[1] or terminal and following is State.ERROR):
                return current
        return None

    def _capture_failure_evidence(self, result) -> dict[str, object]:
        boundary = self._failure_boundary(result.state_trace, result.failure)
        no_action = (
            tuple(result.state_trace) == (State.IDLE, State.ERROR)
            and not self._state_events
            and not self._planning_attempts
        )
        evidence: dict[str, object] = {
            "failure_boundary_state": None if boundary is None else boundary.value,
            "physical_action_proven_absent": no_action,
            "terminal_sample": None,
            "planning_scene_readback": None,
            "capture_errors": [],
        }
        if no_action:
            return evidence
        prior_sequences = [
            value.get("publisher_sequence")
            for event in self._state_events
            for value in (event.get("before"), event.get("after"))
            if isinstance(value, dict)
            and type(value.get("publisher_sequence")) is int
        ]
        freshness_floor = max(
            [0, *prior_sequences, self._release_marker_sequence or 0]
        )
        try:
            deadline = time.monotonic() + 2.0
            terminal = self._snapshot()
            while terminal.publisher_sequence <= freshness_floor:
                if time.monotonic() >= deadline:
                    raise RuntimeError("DYNAMIC_FAILURE_EVIDENCE_STALE")
                terminal = self._snapshot()
            evidence["terminal_sample"] = self._evidence(terminal)
        except Exception as error:
            evidence["capture_errors"].append(
                f"PHYSICAL:{str(error).split(':', 1)[0]}"
            )
        try:
            attached, world = self._scene_membership()
            evidence["planning_scene_readback"] = {
                "attached_object_ids": attached,
                "world_primitive_counts": world,
            }
        except Exception as error:
            evidence["capture_errors"].append(
                f"SCENE:{str(error).split(':', 1)[0]}"
            )
        return evidence

    def _progress(self) -> None:
        import rclpy

        # Observation only (D12): time each sub-step so one slow call is explained by its parts.
        began = time.monotonic()
        lap = began
        substeps = {}

        def tick(name):
            nonlocal lap
            now = time.monotonic()
            substeps[name] = round((now - lap) * 1e3, 3)
            lap = now

        try:
            # Control needs exactly one thing here: its own callbacks (world observer, joint states, controller
            # results). A failure of those is an execution error and propagates.
            _spin_burst(self._node, spin=rclpy.spin_once)
            tick("spin_once")
        finally:
            self._report_slow_progress(began, substeps)

    def _report_slow_progress(self, began, substeps):
        """Emit a bounded fact line for one slow `_progress` call; never raises."""
        try:
            total_ms = (time.monotonic() - began) * 1e3
            emitted = getattr(self, "_progress_slow_lines", 0)
            if total_ms <= 50.0 or emitted >= 20:
                return
            self._progress_slow_lines = emitted + 1
            substeps.setdefault("spin_once", 0.0)
            document = {"total_ms": round(total_ms, 3), "substeps_ms": substeps}
            line = "DYNAMIC_PROGRESS_SLOW " + json.dumps(document, sort_keys=True, separators=(",", ":"))
            print(line.encode()[:2000].decode(errors="ignore"), file=sys.stderr, flush=True)
        except Exception:
            pass

    # ---- stop flags (user stop, parent death, attempt deadline) -------------------------------------------------------
    # A flag is raised only where a cancel (or no goal at all) follows: the trajectory monitor and the gripper hook
    # while a goal is active, and the wait loops, the state-machine entry and the next-goal sites while none is. It is
    # never raised from `_progress`, which `executor.execute` and `GripperClient.command` call before their monitor:
    # a raise there would leave the active goal running.

    def _check_stop(self) -> None:
        flags = getattr(self, "_stop_flags", None)
        if flags is not None and not getattr(self, "_stop_suspended", False):
            flags.raise_if_stopped()

    def _wait_progress(self) -> None:
        """`_progress` plus the stop check, for waits that have no active goal."""
        self._progress()
        self._check_stop()

    def _on_joint_state(self, message: Any) -> None:
        if len(message.name) == len(message.position):
            positions = dict(
                (name, float(position))
                for name, position in zip(message.name, message.position, strict=True)
            )
            self._positions.update(positions)
            velocity = getattr(message, "velocity", None)
            if velocity is not None and len(velocity) == len(message.name):
                if not hasattr(self, "_joint_velocities"):
                    self._joint_velocities = {}
                self._joint_velocities.update(
                    (name, float(item)) for name, item in zip(message.name, velocity, strict=True))
            if all(name in positions for name in self._ARM_JOINTS):
                stamp = getattr(getattr(message, "header", None), "stamp", None)
                self._joint_state_source_stamp_ns = (
                    None if stamp is None else int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)
                )
                self._joint_state_received_monotonic_s = time.monotonic()
                self._joint_state_generation += 1

    def _joint_state(
        self,
        timeout_s: float = 5.0,
        *,
        after_generation: int | None = None,
    ) -> tuple[float, ...]:
        deadline = time.monotonic() + timeout_s
        while any(name not in self._positions for name in self._ARM_JOINTS) or (
            after_generation is not None and self._joint_state_generation <= after_generation
        ):
            if time.monotonic() >= deadline:
                raise RuntimeError("JOINT_STATE_TIMEOUT")
            self._wait_progress()
        return tuple(self._positions[name] for name in self._ARM_JOINTS)

    def _snapshot(self):
        from ..backends.mujoco.observer import EvidenceStale

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            self._wait_progress()
            try:
                value = self.observer.snapshot()
            except EvidenceStale:
                continue
            if value.simulation_session_id != self._session_id:
                raise RuntimeError("DYNAMIC_SESSION_MISMATCH")
            if value.reset_epoch != self._expected_reset_epoch or value.paused:
                raise RuntimeError("DYNAMIC_RESET_EPOCH_MISMATCH")
            return value
        raise RuntimeError("DYNAMIC_EVIDENCE_TIMEOUT")

    @staticmethod
    def _evidence(value) -> dict[str, object]:
        return {
            "publisher_sequence": value.publisher_sequence,
            "simulation_step": value.simulation_step,
            "reset_epoch": value.reset_epoch,
            "cup_position_world_m": list(value.object_state.position_world),
            "cup_orientation_world_xyzw": list(value.object_state.orientation_xyzw),
            "cup_linear_velocity_world_m_s": list(value.object_state.linear_velocity_world),
            "cup_angular_velocity_world_rad_s": list(value.object_state.angular_velocity_world),
            "left_contact_count": len(value.left_fingertip_contacts),
            "right_contact_count": len(value.right_fingertip_contacts),
            "maximum_normal_force_n": value.maximum_normal_force_n,
            "table_contact": any(
                item.geom2 == "table_collision" for item in value.other_object_contacts
            ),
        }

    def _record_monitor_violation(self, state: State, reason: str, value) -> None:
        def contacts(items) -> list[dict[str, object]]:
            return [
                {
                    "geom1": getattr(item, "geom1", None),
                    "geom2": getattr(item, "geom2", None),
                    "position_world_m": (
                        None if getattr(item, "position_world", None) is None
                        else list(item.position_world)
                    ),
                    "signed_distance_m": getattr(item, "signed_distance_m", None),
                    "normal_force_n": getattr(item, "normal_force_n", None),
                }
                for item in items
            ]

        violation = {
            "state": state.value,
            "reason": reason,
            "sample": self._evidence(value),
            "contacts": {
                "left": contacts(value.left_fingertip_contacts),
                "right": contacts(value.right_fingertip_contacts),
                "other": contacts(value.other_object_contacts),
            },
            "last_joint_positions_rad": {
                name: self._positions.get(name) for name in (*self._ARM_JOINTS, "6")
            },
            "last_joint_state_received_monotonic_s": self._joint_state_received_monotonic_s,
        }
        self._document.setdefault("monitor_violation", violation)
        self._document.setdefault("monitor_violations", []).append(violation)

    def _record(self, state: State, before, after, **details: object) -> None:
        self._state_events.append(
            {
                "state": state.value,
                "before": None if before is None else self._evidence(before),
                "after": None if after is None else self._evidence(after),
                **details,
            }
        )
        self._write()

    @staticmethod
    def _table_contact(value) -> bool:
        return any(item.geom2 == "table_collision" for item in value.other_object_contacts)

    @staticmethod
    def _bilateral(value) -> bool:
        return bool(value.left_fingertip_contacts and value.right_fingertip_contacts)

    @staticmethod
    def _reject_carried_table_contact(state: State, table_contact: bool) -> bool:
        return bool(table_contact and state is not State.MICRO_LIFT)

    @staticmethod
    def _interpolate_pose(
        start: PoseEvidence, target: PoseEvidence, fraction: float
    ) -> PoseEvidence:
        if not 0.0 <= fraction <= 1.0:
            raise ValueError("pose interpolation fraction must be in [0, 1]")
        position = tuple(
            start.position_m[index]
            + fraction * (target.position_m[index] - start.position_m[index])
            for index in range(3)
        )
        start_q = start.orientation_xyzw
        target_q = target.orientation_xyzw
        if sum(a * b for a, b in zip(start_q, target_q, strict=True)) < 0.0:
            target_q = tuple(-value for value in target_q)
        quaternion = tuple(
            start_q[index] + fraction * (target_q[index] - start_q[index]) for index in range(4)
        )
        norm = math.sqrt(sum(value * value for value in quaternion))
        return PoseEvidence(position, tuple(value / norm for value in quaternion))

    @staticmethod
    def _upright_tilt_rad(quaternion_xyzw: tuple[float, float, float, float]) -> float:
        x, y, _z, _w = quaternion_xyzw
        world_z_dot = 1.0 - 2.0 * (x * x + y * y)
        return math.acos(min(1.0, max(-1.0, world_z_dot)))

    @staticmethod
    def _is_reconcilable_control_failure(result: ActionResult) -> bool:
        """Recognize only MoveIt's controller-level false-negative candidate."""

        return bool(
            result.status is not ActionStatus.SUCCEEDED
            and result.failure is not None
            and result.failure.code == "MOVEIT_EXECUTION_FAILED"
            and result.failure.metrics.get("moveit_error_code") == -6.0
        )

    @staticmethod
    def _terminal_pose_reconciliation(
        actual: PoseEvidence,
        target: PoseEvidence,
        *,
        position_tolerance_m: float,
        orientation_tolerance_rad: float,
        orientation_error_rad,
    ) -> dict[str, float] | None:
        """Accept CONTROL_FAILED only when fresh terminal TCP evidence proves arrival."""

        position_error_m = math.dist(actual.position_m, target.position_m)
        orientation_error = orientation_error_rad(actual, target)
        if position_error_m > position_tolerance_m or orientation_error > orientation_tolerance_rad:
            return None
        return {
            "moveit_error_code": -6,
            "terminal_position_error_m": position_error_m,
            "terminal_orientation_error_rad": orientation_error,
        }

    def _wait_stable(self, predicate, duration_s: float, timeout_s: float):
        started: float | None = None
        latest = None
        last_sequence = -1
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            value = self._snapshot()
            if value.publisher_sequence == last_sequence:
                continue
            last_sequence = value.publisher_sequence
            self._enforce_safety(getattr(self, "_safety_state", None), value)
            healthy = bool(predicate(value)) and value.maximum_normal_force_n <= self._MAX_FORCE_N
            now = time.monotonic()
            started = started if healthy and started is not None else (now if healthy else None)
            latest = value
            if started is not None and now - started >= duration_s:
                return latest
        raise RuntimeError("DYNAMIC_STABLE_STATE_TIMEOUT")

    def _record_planning_attempt(self, document: dict[str, object]) -> None:
        attempts = getattr(self, "_planning_attempts", None)
        if attempts is None:
            attempts = []
            self._planning_attempts = attempts
            self._document["planning_attempts"] = attempts
        attempts.append(document)
        self._write()

    def _motion_horizon(
        self,
        state: State,
        motion_targets: list[PoseEvidence],
        current: tuple[float, ...],
    ) -> tuple[HorizonStep, ...]:
        pick_prefix = {
            State.MOVE_ABOVE_OBJECT,
            State.DESCEND,
            State.MICRO_LIFT,
            State.LIFT,
        }
        cached = getattr(self, "_pick_horizon_steps", {}).get(state)
        if cached:
            return cached

        has_full_target_set = hasattr(self, "_targets")
        if state in pick_prefix and has_full_target_set:
            above = self._targets.for_state(State.MOVE_ABOVE_OBJECT)
            descend = self._targets.for_state(State.DESCEND)
            waypoints = list(
                _compute_while_progressing(
                    lambda: interpolated_move_above_waypoints(self._ik, current, above),
                    self._progress,
                )
            )
            waypoints.extend(
                HorizonWaypoint(
                    State.DESCEND,
                    index,
                    self._interpolate_pose(above, descend, index / 6.0),
                )
                for index in range(1, 7)
            )
            waypoints.extend(
                (
                    HorizonWaypoint(
                        State.MICRO_LIFT,
                        0,
                        self._targets.for_state(State.MICRO_LIFT),
                    ),
                    HorizonWaypoint(State.LIFT, 0, self._targets.for_state(State.LIFT)),
                )
            )
        else:
            waypoints = [
                HorizonWaypoint(state, index, target) for index, target in enumerate(motion_targets)
            ]

        result = _compute_while_progressing(
            lambda: solve_horizon(
                self._ik,
                tuple(waypoints),
                current,
                position_tolerance_m=self._template.position_tolerance_m,
                orientation_tolerance_rad=max(self._template.orientation_tolerance_rad),
                beam_width=3,
            ),
            self._progress,
        )
        if state in pick_prefix and has_full_target_set:
            horizon_document = result.to_document()
            horizon_document.update(
                selection_reason=(
                    "minimum deterministic cumulative score among complete beam paths"
                ),
                admitted=bool(result.paths),
            )
            self._document["pick_prefix_horizon"] = horizon_document
            self._write()
        if not result.paths:
            raise RuntimeError("DYNAMIC_IK_HORIZON_FAILED")
        selected = result.paths[0].steps
        if state in pick_prefix and has_full_target_set:
            grouped: dict[State, tuple[HorizonStep, ...]] = {}
            for step in selected:
                grouped.setdefault(step.waypoint.state, ())
                grouped[step.waypoint.state] += (step,)
            self._pick_horizon_steps = grouped
            return grouped[state]
        return selected

    def _plan_candidate_set(
        self,
        *,
        state: State,
        step: HorizonStep,
        current: tuple[float, ...],
        joint_target: tuple[float, ...],
    ):
        candidate_count = (
            MOVE_ABOVE_PLAN_CANDIDATE_COUNT
            if state is State.MOVE_ABOVE_OBJECT
            else 1
        )
        candidates = []
        corridor_receipts: list[dict[str, object]] = []
        last_failure = "CUP_POSE_PLAN_FAILED"
        scaling = self._planning_scaling(state)
        for candidate_index in range(candidate_count):
            planned = self._planning.plan_joint_path(
                JointPlanRequest(
                    joint_names=self._ARM_JOINTS,
                    current_positions=current,
                    target_positions=joint_target,
                    velocity_scaling=scaling[0],
                    acceleration_scaling=scaling[1],
                    planning_time_s=self._template.planning_timeout_s,
                    planning_group=self._template.planning_group,
                    tcp_link=self._template.tcp_link,
                ),
                timeout_s=self._template.planning_timeout_s + 5.0,
            )
            if planned.failure is not None or planned.trajectory is None:
                last_failure = (
                    "CUP_POSE_PLAN_FAILED"
                    if planned.failure is None
                    else planned.failure.code
                )
                self._record_planning_attempt(
                    {
                        "kind": "moveit_joint_plan",
                        "state": state.value,
                        "segment_index": step.waypoint.segment_index,
                        "candidate_index": candidate_index,
                        "candidate_count": candidate_count,
                        "accepted": False,
                        "failure_code": last_failure,
                        "joint_target_rad": list(joint_target),
                    }
                )
                continue
            self._record_planning_attempt(
                {
                    "kind": "moveit_joint_plan",
                    "state": state.value,
                    "segment_index": step.waypoint.segment_index,
                    "candidate_index": candidate_index,
                    "candidate_count": candidate_count,
                    "accepted": True,
                    "failure_code": None,
                    "joint_target_rad": list(joint_target),
                    "trajectory_sample_count": len(
                        planned.trajectory.joint_trajectory.points
                    ),
                }
            )
            corridor = validate_cartesian_corridor(
                self._ik,
                planned.trajectory,
                self._ARM_JOINTS,
                current,
                step.waypoint.target,
                maximum_deviation_m=(
                    0.008
                    if state
                    in {
                        State.DESCEND,
                        State.MICRO_LIFT,
                        State.LIFT,
                        State.DESCEND_TO_PLACE,
                    }
                    else 0.050
                ),
                orientation_tolerance_rad=max(
                    self._template.orientation_tolerance_rad
                ),
                minimum_clearance_z_m=(
                    0.145
                    if state in {State.DESCEND, State.MICRO_LIFT, State.LIFT}
                    else -math.inf
                ),
            )
            corridor_document = corridor.to_document()
            corridor_document.update(
                kind=(
                    "moveit_plan_candidate"
                    if candidate_count > 1
                    else "actual_moveit_cartesian_corridor"
                ),
                validation_kind="actual_moveit_cartesian_corridor",
                state=state.value,
                segment_index=step.waypoint.segment_index,
                candidate_index=candidate_index,
                candidate_count=candidate_count,
            )
            corridor_receipts.append(corridor_document)
            self._record_planning_attempt(corridor_document)
            last_failure = corridor.failure_code or "CARTESIAN_CORRIDOR_FAILED"
            if corridor.accepted:
                candidates.append(
                    (
                        cartesian_candidate_score(
                            corridor, candidate_index=candidate_index
                        ),
                        candidate_index,
                        planned,
                    )
                )
        if not candidates:
            raise RuntimeError(last_failure)
        _, selected_index, selected = min(candidates, key=lambda item: item[0])
        if candidate_count > 1:
            self._record_planning_attempt(
                {
                    "kind": "moveit_plan_selection",
                    "state": state.value,
                    "segment_index": step.waypoint.segment_index,
                    "candidate_index": selected_index,
                    "candidate_count": candidate_count,
                    "accepted_candidate_count": len(candidates),
                    "selection_reason": (
                        "minimum orientation error, Cartesian deviation, "
                        "sample count, then candidate index"
                    ),
                }
            )
        return selected, corridor_receipts

    def _motion_planning_start(self):
        return self._joint_state()

    def _monitor_sample(self):
        """The latest world sample for the monitor, read without blocking, or None while the state is unavailable.

        Unlike `_snapshot` this never waits and never spins: `executor.execute` has just called `progress()`. The
        safety checks that need the sample count as unavailable when the newest evidence or joint state is older than
        `state_max_age_s` (or the evidence is truncated). Unavailability longer than `state_unavailable_stop_s` is a
        stop. The identity checks of `_snapshot` (session, pause, reset epoch) apply to the latest sample.
        """
        from ..backends.mujoco.observer import EvidenceStale

        policy = getattr(self, "_teacher_execution_policy", None) or {}
        max_age = policy.get("state_max_age_s", _DEFAULT_STATE_MAX_AGE_S)
        stop_after = policy.get("state_unavailable_stop_s", _DEFAULT_STATE_UNAVAILABLE_STOP_S)
        now = self._monotonic()
        try:
            value = self.observer.snapshot_with_receipt().evidence
        except EvidenceStale:
            value = None
        joint_received = getattr(self, "_joint_state_received_monotonic_s", None)
        joint_fresh = joint_received is not None and 0.0 <= now - joint_received <= max_age
        if value is None or value.truncated or not joint_fresh:
            since = getattr(self, "_unavailable_since", None)
            if since is None:
                since = self._unavailable_since = now
            if now - since > stop_after:
                raise TeacherStop(
                    "DYNAMIC_STATE_UNAVAILABLE_STOP",
                    f"necessary state unavailable for {now - since:.3f}s (limit {stop_after}s)")
            return None
        self._unavailable_since = None
        if value.simulation_session_id != self._session_id:
            raise TeacherStop("DYNAMIC_SESSION_MISMATCH")
        if value.reset_epoch != self._expected_reset_epoch or value.paused:
            raise TeacherStop("DYNAMIC_RESET_EPOCH_MISMATCH")
        return value

    def _enforce_safety(self, state, value) -> None:
        """The execution protections that stop the robot, on one fresh sample: raises `TeacherStop`.

        1. the original maximum single-contact force (11.60 N);
        2. with the frozen contact policy: summed cup force and fingertip compression (same limits as the broker);
        3. with the robot contact watch: a collision pair outside the cup process pairs.
        Everything else the broker checked about the process (hold, stability, contact timing) stays audit-only.
        """
        if value.maximum_normal_force_n > self._MAX_FORCE_N:
            self._record_monitor_violation(state or State.IDLE, "DYNAMIC_FORCE_LIMIT_EXCEEDED", value)
            raise TeacherStop("DYNAMIC_FORCE_LIMIT_EXCEEDED")
        limits = getattr(self, "_safety_limits", None)
        plugin = getattr(self, "_physics_hazard_watch", None)
        if plugin is not None and plugin.limit_code is not None:
            self._enforce_step_limit(state, plugin)
        if limits is not None:
            verdict = evaluate_cup_contacts(value, limits)
            if verdict.code is not None:
                self._record_monitor_violation(state or State.IDLE, verdict.code, value)
                raise TeacherStop(
                    verdict.code,
                    f"summed force {verdict.summed_force_n:.6f} N (limit {limits.maximum_safe_force_n:.6f}), "
                    f"compression {verdict.compression_m:.9f} m (limit {limits.maximum_compression_distance_m:.9f})")
        watch = getattr(self, "_collision_watch", None)
        if watch is not None and watch.hazard is not None:
            raise TeacherStop(watch.hazard, watch.detail)
        if plugin is not None and plugin.hazard is not None:
            raise TeacherStop(plugin.hazard, plugin.detail)

    def _enforce_step_limit(self, state, plugin) -> None:
        """The same frozen rule evaluated on every 500 Hz physics step of the chunk stream (C3a)."""
        self._record_per_step_violation(state or State.IDLE, plugin)
        raise TeacherStop(plugin.limit_code, plugin.limit_detail)

    def _record_per_step_violation(self, state: State, plugin) -> None:
        self._document.setdefault("monitor_violation", {
            "state": state.value, "reason": plugin.limit_code, "sample": None,
            "per_step": {"step": plugin.limit_step, "state": plugin.limit_state, "value": plugin.limit_value,
                         "limit": plugin.limit_limit, "kind": plugin.limit_kind},
            "last_joint_positions_rad": {
                name: self._positions.get(name) for name in (*self._ARM_JOINTS, "6")},
            "last_joint_state_received_monotonic_s": self._joint_state_received_monotonic_s,
        })

    def _step_evidence_available(self, plugin, baseline_gaps: int) -> None:
        """P4/P9 for the per-step stream: a gap since the goal began, or silence beyond the bound, is a stop."""

        if plugin is None or plugin.limits is None:
            return
        if plugin.gaps > baseline_gaps:
            raise TeacherStop("DYNAMIC_STATE_UNAVAILABLE_STOP", "per-step physics evidence gap: " + plugin.gap_detail)
        policy = getattr(self, "_teacher_execution_policy", None) or {}
        now = self._monotonic()
        last = plugin.last_chunk_monotonic_s
        if last is None:
            last = plugin.armed_monotonic_s
        silent = 0.0 if last is None else now - last
        if silent > policy.get("state_unavailable_stop_s", _DEFAULT_STATE_UNAVAILABLE_STOP_S):
            raise TeacherStop(
                "DYNAMIC_STATE_UNAVAILABLE_STOP", f"per-step physics evidence silent for {silent:.3f}s")

    def _motion_monitor(self, state: State):
        """Per-trajectory monitor, also the gripper's. It raises (and the client cancels the goal) for: a stop flag,
        state unavailable too long, an identity change, the force limits and a collision. Every process check is
        audit-only (D3)."""

        carried = state in {
            State.MICRO_LIFT,
            State.LIFT,
            State.MOVE_ABOVE_PLACE,
            State.DESCEND_TO_PLACE,
            State.RECOVER_LIFT_TO_SAFE_HEIGHT,
            State.RECOVER_MOVE_ABOVE_PICK,
            State.RECOVER_DESCEND_TO_PICK,
        }
        guard = SustainedConditionGuard(0.08, clock=getattr(self, "_monotonic", time.monotonic))
        step_watch = getattr(self, "_physics_hazard_watch", None)
        goal_gaps = []   # the gap count when the goal's first monitor call runs (after its first spin drained any backlog)

        def monitor() -> None:
            self._check_stop()
            if step_watch is not None:
                if not goal_gaps:
                    goal_gaps.append(step_watch.gaps)
                if step_watch.limit_code is not None:
                    self._enforce_step_limit(state, step_watch)
                self._step_evidence_available(step_watch, goal_gaps[0])
            value = self._monitor_sample()
            if value is None:
                return
            self._enforce_safety(state, value)
            if carried:
                try:
                    guard.require(self._bilateral(value), "dynamic carry lost bilateral contact")
                except RuntimeError as lost:
                    self._record_process_diagnostic(
                        "DYNAMIC_CARRY_BILATERAL_LOST", state, sample=value, message=str(lost))
                if self._reject_carried_table_contact(state, self._table_contact(value)):
                    self._record_process_diagnostic("DYNAMIC_EARLY_TABLE_CONTACT", state, sample=value)
            elif state in {State.MOVE_ABOVE_OBJECT, State.DESCEND} and self._initial is not None:
                displacement = math.dist(
                    value.object_state.position_world,
                    self._initial.object_state.position_world,
                )
                if displacement > 0.005:
                    self._record_process_diagnostic(
                        "DYNAMIC_PRECLOSE_CUP_MOVED", state, sample=value, displacement_m=displacement)

        return monitor

    def _unsettled_cancel(self, reason: str, goal: str, state) -> TeacherStop:
        """A cancel that did not settle within its bound ends the run; the worker then confirms and cancels every
        goal (`cancel_and_confirm_parallel_goals`)."""
        self._document["cancel_unsettled"] = {
            "reason": reason, "goal": goal, "state": None if state is None else state.value}
        try:
            self._write()
        except Exception:
            pass
        return TeacherStop("TEACHER_CANCEL_UNSETTLED", reason)

    def _refuse_plan_start_drift(self, trajectory) -> None:
        """Refuse a plan whose first point is more than 0.01 rad from the measured arm joints (no goal is sent)."""
        try:
            names = list(trajectory.joint_trajectory.joint_names)
            first = dict(zip(names, trajectory.joint_trajectory.points[0].positions, strict=True))
            start = tuple(float(first[name]) for name in self._ARM_JOINTS)
            handoff = tuple(float(self._positions[name]) for name in self._ARM_JOINTS)
        except (AttributeError, IndexError, KeyError, TypeError, ValueError) as error:
            raise RuntimeError("DYNAMIC_PLAN_START_DRIFT: start state unavailable") from error
        drift = maximum_joint_error(handoff, start)
        if drift > _PLAN_START_DRIFT_MAX_RAD:
            raise RuntimeError(
                f"DYNAMIC_PLAN_START_DRIFT: {drift:.6f} rad exceeds {_PLAN_START_DRIFT_MAX_RAD} rad")

    def _execute_planned(self, trajectory, state: State, monitor) -> ActionResult:
        """One `ExecuteTrajectory` goal through `MoveItExecutionClient`.

        Returns on SUCCEEDED. Otherwise raises: `TeacherStop` for a monitor stop (its own code) or a cancel that did
        not settle, `_ExecutionFailed` for a controller-originated failure (reject, abort result, timeout whose
        cancel settled), which keeps the original RECOVER_* route.
        """
        self._check_stop()
        self._refuse_plan_start_drift(trajectory)
        self._last_arm_result = None
        self._emit_phase_begin("arm")
        executed = self._trajectory.execute(
            trajectory, getattr(self, "_execute_timeout_s", 45.0), monitor=monitor)
        if executed.status is ActionStatus.SUCCEEDED:
            self._last_arm_result = "SUCCEEDED"
            return executed
        failure = executed.failure
        code = failure.code if failure is not None else "DYNAMIC_EXECUTION_FAILED"
        message = "" if failure is None else failure.message
        settled = None if failure is None else failure.metrics.get("cancel_settled")
        if code == "MOVEIT_EXECUTION_MONITOR_ABORTED":
            self._last_arm_result = "MONITOR_ABORTED"
            reason = message.split(":", 1)[0] or code
            if settled == 0.0:
                raise self._unsettled_cancel(reason, "arm", state)
            raise RuntimeError(message or code)  # the monitor's own coded reason, e.g. DYNAMIC_CUP_FORCE_EXCEEDED
        if code == "MOVEIT_EXECUTION_TIMEOUT" and settled == 0.0:
            self._last_arm_result = "TIMED_OUT"
            raise self._unsettled_cancel(code, "arm", state)
        self._last_arm_result = ("CONTROLLER_FAILED" if code in (
            "MOVEIT_EXECUTION_FAILED", "MOVEIT_EXECUTION_REJECTED", "MOVEIT_EXECUTION_UNAVAILABLE") else "TIMED_OUT")
        raise _ExecutionFailed(f"{code}: {message}", executed)

    def _motion(self, state: State, target: PoseEvidence) -> None:
        before = self._snapshot()
        current = self._motion_planning_start()
        motion_targets = [target]
        if state in {State.DESCEND, State.MOVE_ABOVE_PLACE, State.DESCEND_TO_PLACE}:
            start_pose = self._ik.forward(current)
            motion_targets = [
                self._interpolate_pose(start_pose, target, step / 6.0) for step in range(1, 7)
            ]

        monitor = self._motion_monitor(state)

        trajectory_points = 0
        segment_joint_targets: list[list[float]] = []
        execution_reconciliations: list[dict[str, float]] = []
        cartesian_corridor_receipts: list[dict[str, object]] = []
        joint_target = current
        resolved_pose = self._ik.forward(current)
        horizon_steps = self._motion_horizon(state, motion_targets, current)
        for segment_index, step in enumerate(horizon_steps):
            self._check_stop()  # no new goal is planned or sent after a stop
            motion_target = step.waypoint.target
            joint_target = step.receipt.joint_positions_rad
            if joint_target is None:
                raise RuntimeError("DYNAMIC_IK_HORIZON_FAILED")
            resolved_pose = self._ik.forward(joint_target)
            selection_document = step.receipt.to_document()
            selection_document.update(
                kind="deterministic_ik_selection",
                selection_reason="selected complete-path minimum cumulative score",
            )
            self._record_planning_attempt(selection_document)
            planned, candidate_corridors = self._plan_candidate_set(
                state=state,
                step=step,
                current=current,
                joint_target=joint_target,
            )
            cartesian_corridor_receipts.extend(candidate_corridors)
            execution_generation = self._joint_state_generation
            try:
                self._execute_planned(planned.trajectory, state, monitor)
            except _ExecutionFailed as failed:
                # The trajectory client has already cancelled and settled the goal. Persist the
                # triggering atomic sample before recovery can replace it with a later snapshot.
                if "monitor_violation" in self._document:
                    self._write()
                if self._is_reconcilable_control_failure(failed.result):
                    current = self._joint_state(after_generation=execution_generation)
                    reconciliation = self._terminal_pose_reconciliation(
                        self._ik.forward(current),
                        motion_target,
                        position_tolerance_m=self._template.position_tolerance_m,
                        orientation_tolerance_rad=max(self._template.orientation_tolerance_rad),
                        orientation_error_rad=self._ik.orientation_error_rad,
                    )
                    if reconciliation is not None:
                        reconciliation["segment_index"] = float(segment_index)
                        execution_reconciliations.append(reconciliation)
                        trajectory_points += len(planned.trajectory.joint_trajectory.points)
                        segment_joint_targets.append(list(joint_target))
                        continue
                raise
            except RuntimeError:
                if "monitor_violation" in self._document:
                    self._write()
                raise
            trajectory_points += len(planned.trajectory.joint_trajectory.points)
            segment_joint_targets.append(list(joint_target))
            current = self._joint_state(after_generation=execution_generation)
        after = self._snapshot()
        snapshot_joint_generation = self._joint_state_generation
        current = self._joint_state(after_generation=snapshot_joint_generation)
        terminal_pose = self._ik.forward(current)
        details: dict[str, object] = {
            "target_pose": [*target.position_m, *target.orientation_xyzw],
            "resolved_joint_target_rad": list(joint_target),
            "segment_joint_targets_rad": segment_joint_targets,
            "resolved_fk_pose": [
                *resolved_pose.position_m,
                *resolved_pose.orientation_xyzw,
            ],
            "resolved_position_error_m": math.dist(resolved_pose.position_m, target.position_m),
            "resolved_orientation_error_rad": self._ik.orientation_error_rad(resolved_pose, target),
            "terminal_joint_positions_rad": list(current),
            "terminal_fk_pose": [
                *terminal_pose.position_m,
                *terminal_pose.orientation_xyzw,
            ],
            "terminal_position_error_m": math.dist(terminal_pose.position_m, target.position_m),
            "terminal_orientation_error_rad": self._ik.orientation_error_rad(terminal_pose, target),
            "terminal_joint_state_generation": self._joint_state_generation,
            "terminal_joint_state_source_stamp_ns": self._joint_state_source_stamp_ns,
            "terminal_joint_state_received_monotonic_s": (self._joint_state_received_monotonic_s),
            "trajectory_points": trajectory_points,
            "execution_reconciliations": execution_reconciliations,
            "cartesian_corridor_receipts": cartesian_corridor_receipts,
        }
        if state is State.MICRO_LIFT:
            self._before_micro_lift = before
            lift = after.object_state.position_world[2] - before.object_state.position_world[2]
            bilateral = self._bilateral(after)
            table_contact = self._table_contact(after)
            if not 0.001 <= lift <= 0.010 or not bilateral or table_contact:
                # Audit-only (D3): micro-lift verification is process quality; the endpoint decides the task result.
                self._record_process_diagnostic(
                    "DYNAMIC_MICRO_LIFT_NOT_PROVED", state, sample=after,
                    facts={"physical_cup_lift_m": lift, "bilateral_contact": bilateral,
                           "table_contact": table_contact})
            details.update(
                physical_cup_lift_m=lift,
                physical_bilateral_contact=bilateral,
                physical_table_contact=table_contact,
                validation_failure=None,
            )
        self._record(state, before, after, **details)

    def _command_gripper(self, state: State, target: float, *, before=None) -> None:
        self._check_stop()  # no new goal after a stop
        if before is None:
            before = self._snapshot()
        timeout_s = getattr(self, "_gripper_timeout_s", 15.0)
        # The gripper goal has the arm goal's stop path: the same monitor, a raise cancels the goal.
        monitor = self._motion_monitor(state)
        if state in (State.OPEN_GRIPPER, State.RECOVER_OPEN_GRIPPER):
            def before_dispatch():
                self._check_selected_release_freshness(before)
                self._emit_phase_begin("gripper")

            result = self._gripper.command(target, 2.0, timeout_s, before_dispatch=before_dispatch, monitor=monitor)
        else:
            result = self._gripper.command(
                target, 2.0, timeout_s, before_dispatch=lambda: self._emit_phase_begin("gripper"), monitor=monitor)
        if result.status is not ActionStatus.SUCCEEDED:
            failure = result.failure
            code = failure.code if failure is not None else "GRIPPER_COMMAND_FAILED"
            settled = None if failure is None else failure.metrics.get("cancel_settled")
            if code == "GRIPPER_MONITOR_ABORTED":
                reason = failure.message.split(":", 1)[0] or code
                if settled == 0.0:
                    raise self._unsettled_cancel(reason, "gripper", state)
                raise RuntimeError(failure.message or code)  # the monitor's own coded reason
            if code == "GRIPPER_RESULT_TIMEOUT" and settled == 0.0:
                raise self._unsettled_cancel(code, "gripper", state)
            raise RuntimeError(code)
        after = self._snapshot()
        self._record(state, before, after, target_q6_rad=target)

    def _release_bounds(self):
        """(state age bound, support distance bound) for the release preflight.

        The age is the Teacher execution policy's `state_max_age_s`, not the ACT RGB-synchronisation age: the
        support-before-open check is execution protection and keeps no dependence on the 100 ms data contract.
        """
        from ..act.contracts import finite

        try:
            age = finite(self._teacher_execution_policy["state_max_age_s"])
            distance = finite(self._release_runtime_policy["safety_release"]["support_distance_max_m"])
            if age <= 0 or distance <= 0:
                raise ValueError("release bounds")
            return age, distance
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise RuntimeError("DYNAMIC_RELEASE_POLICY_INVALID") from error

    def _release_scope(self):
        """(session, reset epoch, attempt): the scope of one release. There is no lease token."""
        attempt = getattr(self, "_attempt_id", None)
        if (not isinstance(self._session_id, str) or not self._session_id
                or type(self._expected_reset_epoch) is not int
                or not isinstance(attempt, str) or not attempt):
            raise RuntimeError("DYNAMIC_RELEASE_SCOPE_REQUIRED")
        return (self._session_id, self._expected_reset_epoch, attempt)

    def _publish_teacher_event(self, kind, payload) -> None:
        """Offer one Teacher fact to the stream. Bounded, non-blocking, never raises into control."""
        try:
            self._event_sink.publish(kind, payload)
        except Exception:
            pass

    def _normal_stop_proof(self):
        """The proof that the arm is stopped: a terminal `ExecuteTrajectory` result (SUCCEEDED, or a controller
        failure that left the arm held) followed by fresh `/joint_states` below the stop velocity.

        `stop_confirmed_wall_s` is the receipt time of the confirming joint state on the same monotonic clock as the
        observer receipts, which `_first_source_after_stop` uses to choose the first post-stop source.
        """
        from ..backends.mujoco.observer import EvidenceStale

        age, _ = self._release_bounds()
        scope = self._release_scope()
        result = getattr(self, "_last_arm_result", None)
        if result not in ("SUCCEEDED", "CONTROLLER_FAILED"):
            raise RuntimeError("DYNAMIC_NORMAL_STOP_UNCONFIRMED")
        confirmed = self._controllers_stopped_at(self._teacher_execution_policy)
        if confirmed is None:
            raise RuntimeError("DYNAMIC_NORMAL_STOP_UNCONFIRMED")
        if not 0 <= self._monotonic() - confirmed <= age:
            raise RuntimeError("DYNAMIC_NORMAL_STOP_SOURCE_INVALID")
        try:
            record = self.observer.snapshot_with_receipt()
        except EvidenceStale as error:
            raise RuntimeError("DYNAMIC_NORMAL_STOP_UNCONFIRMED") from error
        world = record.evidence
        if (world.simulation_session_id, world.reset_epoch) != (scope[0], scope[1]):
            raise RuntimeError("DYNAMIC_NORMAL_STOP_SOURCE_INVALID")
        names = (*self._ARM_JOINTS, "6")
        # One instant on both clocks: the monotonic time now (never before the world receipt or the stop confirmation)
        # and the simulation clock read at that instant, after the node's queued `/clock` callbacks ran. The older world
        # record's own time alone would sit behind this instant by the steps simulated since it was received.
        self._refresh_node_clock()
        instant_ns = max(round(self._monotonic() * 1e9), round(record.received_monotonic_s * 1e9),
                         round(confirmed * 1e9))
        sim_ns = round(world.simulation_time_s * 1e9)
        try:
            sim_ns = max(sim_ns, int(self._node.get_clock().now().nanoseconds))
        except Exception:
            pass
        stop_clock = {"sim_time_ns": sim_ns, "begin_monotonic_ns": instant_ns, "end_monotonic_ns": instant_ns}
        proof = {
            "kind": "TEACHER_NORMAL_STOP",
            "scope": {"session_id": scope[0], "reset_epoch": scope[1], "attempt_id": scope[2]},
            "epoch": {"session_id": scope[0], "reset_epoch": scope[1]},
            "trajectory_result": result,
            "stop_confirmed_wall_s": float(confirmed),
            "joint_positions": {name: float(self._positions[name]) for name in names},
            "joint_velocities": {name: float(self._joint_velocities[name]) for name in names},
            "sim_stamp_s": world.simulation_time_s,
            "simulation_step": world.simulation_step,
            # the world sample this stop is anchored to, for the Recorder's own copy of the same evidence
            "publisher_sequence": world.publisher_sequence,
            "received_wall_s": float(record.received_monotonic_s),
            "source_clock": stop_clock,
        }
        self._document.setdefault("normal_stop_proofs", []).append(proof)
        return proof

    def _first_source_after_stop(self, proof, *, previous_step, previous_sequence):
        from ..adapters.act.scene_state import SceneStateObserver

        age, _ = self._release_bounds()
        scene_observer = getattr(self, "_scene_source_observer", None)
        if not isinstance(scene_observer, SceneStateObserver):
            raise RuntimeError("DYNAMIC_RELEASE_SOURCE_CLOCK_REQUIRED")
        deadline = self._monotonic() + age
        # The owner may read its epoch after confirming stop. That later observation
        # cannot move FIRST past a source already generated after stop confirmation.
        minimum_step = previous_step
        pending_source = None
        facts = {"iterations": 0, "last_scene_error": None, "scene_steps_held": [], "waiting_for_scene_frame": 0,
                 "skipped_before_stop": 0, "pending_step": None, "pending_sequence": None, "newest_evidence_step": None,
                 "newest_evidence_sequence": None, "previous_step": previous_step, "previous_sequence": previous_sequence,
                 "stop_confirmed_wall_s": proof["stop_confirmed_wall_s"]}
        while self._monotonic() <= deadline:
            now = self._monotonic()
            facts["iterations"] += 1
            current = self.observer.recent_with_receipts()
            if current:
                facts["newest_evidence_step"] = current[-1].evidence.simulation_step
                facts["newest_evidence_sequence"] = current[-1].evidence.publisher_sequence
            if pending_source is not None and not 0 <= now - pending_source.received_monotonic_s <= age:
                raise RuntimeError("DYNAMIC_RELEASE_SOURCE_EXPIRED")
            for received in ((pending_source,) if pending_source is not None else current):
                source = received.evidence
                if (source.simulation_session_id, source.reset_epoch) != (
                        self._session_id, self._expected_reset_epoch):
                    raise RuntimeError("DYNAMIC_RELEASE_SOURCE_SCOPE_INVALID")
                if source.paused or source.truncated:
                    raise RuntimeError("DYNAMIC_RELEASE_SOURCE_INVALID")
                if (source.simulation_step > minimum_step and source.publisher_sequence > previous_sequence
                        and received.received_monotonic_s >= proof["stop_confirmed_wall_s"]
                        and 0 <= now - received.received_monotonic_s <= age):
                    pending_source = received
                    facts["pending_step"], facts["pending_sequence"] = source.simulation_step, source.publisher_sequence
                    try:
                        scenes = scene_observer.recent_frames_with_receipts()
                    except ValueError as error:
                        if str(error) in ("SCENE_STATE_UNAVAILABLE", "SCENE_STATE_STALE"):
                            facts["last_scene_error"] = str(error)
                            break  # wait for this candidate's association, never skip to a later source
                        raise RuntimeError("DYNAMIC_RELEASE_SOURCE_CLOCK_INVALID") from error
                    facts["scene_steps_held"] = [frame["simulation_step"] for frame, _ in scenes][-8:]
                    matched = [(frame, receipt) for frame, receipt in scenes if
                        (frame["simulation_session_id"], frame["reset_epoch"], frame["simulation_step"])
                        == (source.simulation_session_id, source.reset_epoch, source.simulation_step)]
                    if not matched:
                        facts["waiting_for_scene_frame"] += 1
                        break
                    if len(matched) != 1:
                        raise RuntimeError("DYNAMIC_RELEASE_SOURCE_CLOCK_INVALID")
                    scene, scene_receipt = matched[0]
                    begin, end = (scene["clock_interval_begin_monotonic_ns"],
                                  scene["clock_interval_end_monotonic_ns"])
                    if (scene["paused"] or scene["model_sha256"] != scene_observer.model_sha256
                            or round(scene["simulation_time_s"] * 1e9) != round(source.simulation_time_s * 1e9)
                            or not 0 < begin <= end <= round(scene_receipt * 1e9)
                            or begin > round(received.received_monotonic_s * 1e9)):
                        raise RuntimeError("DYNAMIC_RELEASE_SOURCE_CLOCK_INVALID")
                    if begin < round(proof["stop_confirmed_wall_s"] * 1e9):
                        facts["skipped_before_stop"] += 1
                        pending_source = None
                        continue  # actually generated before stop; a later receipt cannot change that
                    if not 0 <= now - end * 1e-9 <= age:
                        raise RuntimeError("DYNAMIC_RELEASE_SOURCE_CLOCK_INVALID")
                    # Selection is independent of support/pose quality. A bad first eligible source
                    # is refused by the next gate, never skipped for a later good sample.
                    self._document.setdefault("post_stop_sources", []).append({
                        "source_physics": asdict(source),
                        "received_monotonic_s": received.received_monotonic_s,
                        "source_scene": scene,
                        "scene_received_monotonic_s": scene_receipt,
                        "stop_confirmed_wall_s": proof["stop_confirmed_wall_s"]})
                    self._selected_release_source = received
                    self._selected_release_source_clock = (begin, end, scene_receipt)
                    self._selected_release_source_scene = (copy.deepcopy(scene), scene_receipt)
                    self._selected_release_stop_proof = copy.deepcopy(proof)
                    return source
            self._wait_progress()
        # the code stays DYNAMIC_RELEASE_POST_STOP_SOURCE_UNAVAILABLE (what follows the colon is detail only); the facts say what the
        # loop was waiting for, so that the next occurrence can be explained (CP-3489)
        self._document["post_stop_source_unavailable"] = facts
        raise RuntimeError("DYNAMIC_RELEASE_POST_STOP_SOURCE_UNAVAILABLE: " + json.dumps(facts, sort_keys=True, default=str))

    def _check_selected_release_freshness(self, source):
        age, _ = self._release_bounds()
        selected = getattr(self, "_selected_release_source", None)
        if (selected is None or selected.evidence != source
                or not 0 <= self._monotonic() - selected.received_monotonic_s <= age):
            raise RuntimeError("DYNAMIC_RELEASE_SOURCE_EXPIRED")
        clock = getattr(self, "_selected_release_source_clock", None)
        if clock is not None and (not 0 <= self._monotonic() - clock[1] * 1e-9 <= age
                                  or not 0 <= self._monotonic() - clock[2] <= age):
            raise RuntimeError("DYNAMIC_RELEASE_SOURCE_EXPIRED")

    def _require_supported_bilateral(self, source):
        from ..act.task8_live_evidence import actual_table_support

        _, distance = self._release_bounds()
        if (not actual_table_support(source, support_distance_max_m=distance)
                or not source.left_fingertip_contacts or not source.right_fingertip_contacts):
            raise RuntimeError("DYNAMIC_RELEASE_SUPPORT_NOT_PROVED")

    def _supported_release_preflight(self):
        self._release_authorization = None
        self._release_bounds()
        scope = self._release_scope()
        if self._attached is not True:
            raise RuntimeError("DYNAMIC_RELEASE_ATTACHMENT_NOT_PROVED")
        baseline = self._snapshot()
        proof = self._normal_stop_proof()
        source = self._first_source_after_stop(proof, previous_step=baseline.simulation_step,
                                              previous_sequence=baseline.publisher_sequence)
        self._require_supported_bilateral(source)
        self._release_authorization = (*scope, source.simulation_step, source.publisher_sequence)
        return source

    def _confirm_detached_shadow(self):
        from ..control.planning_scene.task_scene import verify_task_scene

        if self._attached is not False or self._release_scene_geometry is None:
            return False
        self._scene_membership()
        return verify_task_scene(self._last_scene_response, self._release_scene_geometry).success

    def _open_supported_gripper(self, state):
        self._release_bounds()
        scope = self._release_scope()
        if state is State.RECOVER_OPEN_GRIPPER:
            # Recovery has no forward preflight, but it opens only on the same proofs: arm stopped, a first post-stop
            # source, and the cup force-bearing on the table with both fingertip sides in contact. Without them it
            # does not open: the gripper holds and the run ends in ERROR.
            self._release_authorization = None
            baseline = self._snapshot()
            previous_step, previous_sequence = baseline.simulation_step, baseline.publisher_sequence
        else:
            authorization = self._release_authorization
            self._release_authorization = None
            if authorization is None or authorization[:3] != scope:
                raise RuntimeError("DYNAMIC_RELEASE_PREFLIGHT_REQUIRED")
            if self._attached is not False or self._confirm_detached_shadow() is not True:
                raise RuntimeError("DYNAMIC_RELEASE_DETACH_NOT_PROVED")
            previous_step, previous_sequence = authorization[3], authorization[4]
        proof = self._normal_stop_proof()
        source = self._first_source_after_stop(proof, previous_step=previous_step,
                                              previous_sequence=previous_sequence)
        self._require_supported_bilateral(source)
        self._release_marker_sequence = source.publisher_sequence
        self._write()
        self._check_selected_release_freshness(source)
        self._command_gripper(state, self._RELEASE_Q6, before=source)

    def _call(self, client, request, timeout_s: float, code: str, *, before_dispatch=None):
        self._check_stop()
        if not client.wait_for_service(timeout_sec=timeout_s):
            raise RuntimeError(f"{code}_UNAVAILABLE")

        def invoke():
            if before_dispatch is not None:
                before_dispatch()
            future = client.call_async(request)
            deadline = time.monotonic() + timeout_s
            while not future.done() and time.monotonic() < deadline:
                self._wait_progress()  # a service wait has no active goal: a stop flag ends it
            response = future.result() if future.done() else None
            if response is None:
                raise RuntimeError(f"{code}_TIMEOUT")
            return response

        from ..control.planning_scene.task_scene import record_scene_service_call

        return record_scene_service_call(
            request=request, phase=code,
            service=("/apply_planning_scene" if client is self._apply_scene
                     else "/get_planning_scene"),
            invoke=invoke, records=self._scene_service_calls,
            ros_clock=(self._node.get_clock() if hasattr(self._node, "get_clock") else None),
            clock_refresh=self._refresh_node_clock, clock_floor=self._world_sim_floor_ns,
            on_record=self._scene_operation_hook())

    def _refresh_node_clock(self) -> None:
        """Drain the node's queued callbacks so its simulation clock is current (stamps only; never raises)."""
        try:
            _spin_burst(self._node, first_timeout_s=0.0)
        except Exception:
            pass

    def _world_sim_floor_ns(self):
        """Simulation time (ns) of the newest world sample already received, or None. A clock stamp is never older."""
        try:
            return round(self.observer.snapshot_with_receipt().evidence.simulation_time_s * 1e9)
        except Exception:
            return None

    def _scene_operation_hook(self):
        """Offer every Teacher scene call to the event stream (non-blocking); None when there is no stream."""
        stream = getattr(self, "_event_stream", None)
        if stream is None:
            return None
        from ..act.scene_operation import make_scene_operation_hook

        return make_scene_operation_hook(stream, state=lambda: getattr(self, "_scene_state_value", None),
                                         source=lambda: getattr(self, "_scene_op_source", None))

    def _scene_membership(self) -> tuple[list[str], dict[str, int]]:
        from moveit_msgs.msg import PlanningSceneComponents
        from moveit_msgs.srv import GetPlanningScene

        request = GetPlanningScene.Request()
        request.components.components = (
            PlanningSceneComponents.WORLD_OBJECT_NAMES
            | PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
            | PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS
            | PlanningSceneComponents.OBJECT_COLORS
        )
        response = self._call(self._get_scene, request, 5.0, "DYNAMIC_SCENE_READBACK")
        self._last_scene_response = response.scene
        attached = [
            item.object.id for item in response.scene.robot_state.attached_collision_objects
        ]
        world = {item.id: len(item.primitives) for item in response.scene.world.collision_objects}
        return attached, world

    def _set_touch_collision(self, allowed: bool) -> None:
        from moveit_msgs.msg import PlanningScene, PlanningSceneComponents
        from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene

        request = GetPlanningScene.Request()
        request.components.components = PlanningSceneComponents.ALLOWED_COLLISION_MATRIX
        response = self._call(self._get_scene, request, 5.0, "DYNAMIC_ACM_READBACK")
        matrix = copy.deepcopy(response.scene.allowed_collision_matrix)
        set_collision_allowed(matrix, "jaw", "plastic_cup", allowed)
        set_collision_allowed(matrix, "gripper", "plastic_cup", allowed)
        scene = PlanningScene()
        scene.is_diff = True
        # MoveIt replaces the robot state (and re-creates its attached bodies, losing the attached cup's colour) when the
        # message's robot_state is not a diff; every other apply here already sets it.
        scene.robot_state.is_diff = True
        scene.allowed_collision_matrix = matrix
        applied = self._call(
            self._apply_scene,
            ApplyPlanningScene.Request(scene=scene),
            5.0,
            "DYNAMIC_ACM_APPLY",
        )
        if not applied.success:
            raise RuntimeError("DYNAMIC_ACM_APPLY_FAILED")
        self._touch_collision_allowed = allowed

    def _transaction_scene_membership(self, transaction):
        start = len(getattr(self, "_scene_service_calls", ()))
        try:
            return self._scene_membership()
        finally:
            calls = getattr(self, "_scene_service_calls", ())
            if len(calls) > start:
                transaction["query_call_id"] = calls[start]["call_id"]
                self._write()

    def _attach(self, state: State) -> None:
        from moveit_msgs.srv import ApplyPlanningScene
        from ..control.planning_scene.task_scene import make_plain_attach_scene

        # One request form: the plain attach. The independent Recorder derives its scene association from the
        # `scene_operation` events of this apply and read-back; nothing here depends on it.
        before = self._snapshot()
        response = self._call(self._apply_scene, ApplyPlanningScene.Request(scene=make_plain_attach_scene()),
                              5.0, "DYNAMIC_ATTACH")
        if not response.success:
            raise RuntimeError("DYNAMIC_ATTACH_FAILED")
        attached_ids, world = self._scene_membership()
        if "plastic_cup" not in attached_ids:
            raise RuntimeError("DYNAMIC_ATTACH_READBACK_MISMATCH")
        self._attached = True
        if self._touch_collision_allowed:
            self._set_touch_collision(False)
        self._record(state, before, self._snapshot(), attached_ids=attached_ids, world=world)

    def _detach_or_sync(self, state: State) -> None:
        from moveit_msgs.msg import AttachedCollisionObject, CollisionObject, PlanningScene
        from moveit_msgs.srv import ApplyPlanningScene
        from ..core.simulation.types import SimulationEvidence
        from ..core.task_geometry import TaskGeometry
        from ..act.scene_association import source_geometry
        from ..control.planning_scene.task_scene import _collision_object, verify_task_scene

        before = (self._supported_release_preflight()
                  if state in (State.DETACH_MOVEIT, State.RECOVER_DETACH_MOVEIT) else self._snapshot())
        if (not isinstance(self._task_geometry, TaskGeometry)
                or not isinstance(before, SimulationEvidence)
                or before.simulation_session_id != self._session_id
                or before.reset_epoch != self._expected_reset_epoch
                or before.paused or before.truncated or before.object_state.body != "plastic_cup"):
            raise RuntimeError("DYNAMIC_DETACH_SYNC_SOURCE_INVALID")
        expected_geometry = source_geometry(self._task_geometry, before)
        cup = expected_geometry.object("plastic_cup")
        # The apply's exact source survives refusal/timeout; a later failure snapshot cannot
        # replace the sample from which this requested scene was derived.
        import uuid

        transaction = {
            "schema_version": 1, "transaction_id": str(uuid.uuid4()), "phase": state.value,
            "source_physics": asdict(before), "expected_geometry": asdict(expected_geometry),
            "apply_call_id": None, "query_call_id": None, "geometry_verification": None,
        }
        self._document.setdefault("scene_transactions", []).append(transaction)
        self._write()
        remove = AttachedCollisionObject()
        remove.object.id = "plastic_cup"
        remove.object.operation = CollisionObject.REMOVE
        scene = PlanningScene()
        scene.is_diff = True
        scene.robot_state.is_diff = True
        scene.robot_state.attached_collision_objects = [remove]
        scene.world.collision_objects = [
            _collision_object(cup, expected_geometry.frame_id)
        ]
        def before_dispatch():
            if state in (State.DETACH_MOVEIT, State.RECOVER_DETACH_MOVEIT):
                self._check_selected_release_freshness(before)
        start = len(getattr(self, "_scene_service_calls", ()))
        # The physics snapshot this request's cup pose was derived from, named on the scene_operation event so an
        # independent consumer joins the same original step.
        self._scene_op_source = {"simulation_step": before.simulation_step,
                                 "publisher_sequence": before.publisher_sequence,
                                 "simulation_time_s": before.simulation_time_s}
        try:
            response = self._call(
                self._apply_scene, ApplyPlanningScene.Request(scene=scene), 5.0,
                "DYNAMIC_DETACH_SYNC", before_dispatch=before_dispatch)
        finally:
            self._scene_op_source = None
            calls = getattr(self, "_scene_service_calls", ())
            if len(calls) > start:
                transaction["apply_call_id"] = calls[start]["call_id"]
                self._write()
        calls = getattr(self, "_scene_service_calls", ())
        if not response.success:
            raise RuntimeError("DYNAMIC_DETACH_SYNC_FAILED")
        attached_ids, world = self._transaction_scene_membership(transaction)
        if "plastic_cup" in attached_ids or world.get("plastic_cup") != 13:
            raise RuntimeError("DYNAMIC_DETACH_SYNC_READBACK_MISMATCH")
        verification = verify_task_scene(self._last_scene_response, expected_geometry)
        transaction["geometry_verification"] = verification.evidence
        self._write()
        if not verification.success:
            raise RuntimeError("DYNAMIC_DETACH_SYNC_GEOMETRY_MISMATCH")
        self._attached = False
        self._release_scene_geometry = expected_geometry
        self._scene_readback = {
            "attached_object_ids": attached_ids,
            "world_primitive_counts": world,
            "source_physics": asdict(before),
            "geometry_verification": verification.evidence,
        }
        if self._touch_collision_allowed:
            self._set_touch_collision(False)
        self._record(state, before, self._snapshot(), **self._scene_readback)

    def _wait_release(self, state: State) -> None:
        before = self._snapshot()

        def released(value) -> bool:
            linear = max(abs(item) for item in value.object_state.linear_velocity_world)
            angular = max(abs(item) for item in value.object_state.angular_velocity_world)
            return (
                self._table_contact(value)
                and not value.left_fingertip_contacts
                and not value.right_fingertip_contacts
                and linear <= FINAL_MAX_LINEAR_SPEED_M_S
                and angular <= FINAL_MAX_ANGULAR_SPEED_RAD_S
            )

        try:
            after = self._wait_stable(released, 0.20, 4.0)
        except RuntimeError as error:
            if str(error) != "DYNAMIC_STABLE_STATE_TIMEOUT":
                raise
            # The stability window is an observation now (D3); the task result is the endpoint pose.
            after = self._snapshot()
            self._record_process_diagnostic(
                "DYNAMIC_SETTLE_WINDOW_NOT_MET", state, sample=after,
                facts={"window_s": 0.20, "timeout_s": 4.0})
        self._final_samples.append(self._evidence(after))
        self._record(state, before, after)

    def _validate_final(self, state: State) -> None:
        before = self._snapshot()
        expected = compose_pose(
            self._template.place_tcp_world,
            inverse_pose(self._template.cup_to_tcp_grasp),
        )
        actual = before.object_state
        xy_error = math.dist(actual.position_world[:2], expected.values[:2])
        q = actual.orientation_xyzw
        upright = self._upright_tilt_rad(q)
        if (
            xy_error > FINAL_XY_TOLERANCE_M
            or not (
                FINAL_SUPPORT_HEIGHT_RANGE_M[0]
                <= actual.position_world[2]
                <= FINAL_SUPPORT_HEIGHT_RANGE_M[1]
            )
            or upright > FINAL_MAX_UPRIGHT_TILT_RAD
            or not self._table_contact(before)
            or before.left_fingertip_contacts
            or before.right_fingertip_contacts
        ):
            # Audit-only (D3): the pass/fail verdict is the Teacher endpoint rule applied at the end of the run.
            self._record_process_diagnostic(
                "DYNAMIC_FINAL_PLACEMENT_NOT_PROVED", state, sample=before,
                facts={"xy_error_m": xy_error, "height_m": actual.position_world[2], "upright_tilt_rad": upright,
                       "table_contact": self._table_contact(before),
                       "left_contact_count": len(before.left_fingertip_contacts),
                       "right_contact_count": len(before.right_fingertip_contacts)})
        self._record(
            state,
            before,
            before,
            expected_cup_pose_world=list(expected.values),
            final_xy_error_m=xy_error,
            final_upright_tilt_rad=upright,
        )

    # ---- phase events (SO101_TEACHER_EVENT_V2) ------------------------------------------------------------------------
    # One `phase_begin` and one `phase_finish` per state, each with the sim stamp read at that instant. A state that
    # sends a goal begins at the goal send (after any pre-dispatch check), so the stamp is the one at which the Teacher
    # sent its first command; the Recorder takes its first-command clock from the first such event.

    _GOAL_STATES = frozenset({
        State.PREPARE_OPEN_GRIPPER, State.CLOSE_GRIPPER, State.OPEN_GRIPPER, State.RECOVER_OPEN_GRIPPER})

    def _sim_time_ns(self):
        try:
            return int(self._node.get_clock().now().nanoseconds)
        except Exception:
            return None

    def _phase_open(self, state: State, target) -> None:
        self._phase_state, self._phase_begun = state, False
        if target is None and state not in self._GOAL_STATES:
            self._emit_phase_begin(None)

    def _emit_phase_begin(self, goal_kind) -> None:
        """Publish the pending `phase_begin`, once per state. Never raises."""
        try:
            state = getattr(self, "_phase_state", None)
            if state is None or getattr(self, "_phase_begun", True):
                return
            self._phase_begun = True
            self._stream_emit("phase_begin", {
                "state": state.value, "sim_time_ns": self._sim_time_ns(), "monotonic_ns": time.monotonic_ns(),
                "goal_sent": goal_kind is not None, "goal_kind": goal_kind})
        except Exception:
            pass

    def _phase_finish(self, status: str, code=None) -> None:
        try:
            state = getattr(self, "_phase_state", None)
            if state is None:
                return
            self._emit_phase_begin(None)  # a state that never sent a goal still begins before it finishes
            self._stream_emit("phase_finish", {
                "state": state.value, "sim_time_ns": self._sim_time_ns(), "monotonic_ns": time.monotonic_ns(),
                "status": status, "code": code})
        except Exception:
            pass
        finally:
            self._phase_state = None

    def perform(self, state: State, target: PoseEvidence | None) -> ActionResult:
        if getattr(self, '_first_state_marked', False):
            return self._perform_state(state, target)
        self._first_state_marked = True
        _mark_phase('runner.first_state.begin')
        try:
            return self._perform_state(state, target)
        finally:
            _mark_phase('runner.first_state.end')

    #: the states that move the held cup (after ATTACH_MOVEIT); only MOVE_ABOVE_PLACE moves it laterally
    _CARRY_STATES = frozenset({State.LIFT, State.MOVE_ABOVE_PLACE, State.DESCEND_TO_PLACE})

    def _place_target(self, state: State, target):
        """The DESCEND_TO_PLACE target for frozen inputs; every other target and run is untouched.

        Policy v1: lowered by the constant ACT offset. Policy v2: computed from the cup tilt and the grasp offset measured on the
        evidence now (``core.place_height``); a measurement outside what was calibrated raises a ``TEACHER_PLACE_*`` terminal stop
        before any motion (the cup stays held, nothing is released). Called from ``_perform_state`` under
        ``_safety_state = DESCEND_TO_PLACE`` and before ``_phase_open``, so the force limits are enforced while it measures."""

        if state is not State.DESCEND_TO_PLACE or target is None or getattr(self, "_execution_snapshot_root", None) is None:
            return target
        policy = getattr(self, "_teacher_execution_policy", None)
        if policy is not None and policy.get("place_height_mode"):
            return self._compensated_place_target(target, policy)
        if policy is None or "place_descend_offset_m" not in policy:
            raise RuntimeError("TEACHER_POLICY_UNAVAILABLE: place_descend_offset_m")
        x, y, z = target.position_m
        return PoseEvidence((x, y, z + float(policy["place_descend_offset_m"])), target.orientation_xyzw)

    def _place_geometry(self):
        from ..core.place_height import cup_geometry_from_scene

        geometry = getattr(self, "_place_geometry_value", None)
        if geometry is None:
            geometry = cup_geometry_from_scene(Path(self._execution_snapshot_root) / "assets/mujoco/act/scene.xml")
            self._place_geometry_value = geometry
        return geometry

    def _compensated_place_target(self, target, policy) -> PoseEvidence:
        from ..core.place_height import (
            MEASUREMENT_FAILED, PlaceHeightPolicy, PlaceHeightRefused, plan_place_height)

        x, y, z = target.position_m
        height_policy = PlaceHeightPolicy.from_document(policy)
        try:
            theta, k = self._measure_place_height()
            document = plan_place_height(theta, k, z + height_policy.reference_offset_m, self._place_geometry(), height_policy)
        except PlaceHeightRefused as refusal:
            self._document["place_height"] = {"mode": policy["place_height_mode"], "refused": refusal.code,
                                             "detail": str(refusal)[:300]}
            self._write()
            raise
        except Exception as error:
            # a stop that already has its own terminal code (force limit, user stop, ...) keeps it
            if isinstance(error, TeacherStop) or str(error).split(":")[0] in TERMINAL_STOP_CODES:
                raise
            # anything else (scene parse error, no cup body, evidence or joint-state timeout) is terminal as well: the cup stays
            # held; it must never reach RECOVER_LIFT_TO_SAFE_HEIGHT at the place pose
            failure = PlaceHeightRefused(MEASUREMENT_FAILED, f"{type(error).__name__}: {error}"[:300])
            self._document["place_height"] = {"mode": policy["place_height_mode"], "refused": MEASUREMENT_FAILED,
                                             "detail": str(failure)[:300]}
            self._write()
            raise failure from error
        self._document["place_height"] = document
        self._write()
        return PoseEvidence((x, y, document["target_tcp_z_m"]), target.orientation_xyzw)

    def _measure_place_height(self) -> tuple[float, float]:
        """(tilt rad, grasp offset m) of the held cup, from a stable window of fresh evidence: at least 100 ms of simulation whose tilt
        range stays under 0.05 deg, within 1 s (else TEACHER_PLACE_TILT_UNSTABLE). ``k`` is the actual TCP height (forward
        kinematics of the actual joints, sag included) above the cup origin at the end of the window."""

        from ..core.place_height import (
            STABILITY_RANGE_RAD, STABILITY_TIMEOUT_S, STABILITY_WINDOW_S, TILT_UNSTABLE, PlaceHeightRefused)

        window: list[tuple[float, float, object]] = []
        last_sequence = -1
        seen: list[tuple[float, float]] = []
        widest_span_s = 0.0
        deadline = time.monotonic() + STABILITY_TIMEOUT_S
        while time.monotonic() < deadline:
            value = self._snapshot()
            if value.publisher_sequence == last_sequence:
                continue
            last_sequence = value.publisher_sequence
            self._enforce_safety(getattr(self, "_safety_state", None), value)
            now_s = value.simulation_time_s
            tilt = self._upright_tilt_rad(value.object_state.orientation_xyzw)
            seen.append((now_s, tilt))
            window.append((now_s, tilt, value))
            # The window is the newest samples that cover at least STABILITY_WINDOW_S: drop the oldest while the next one is still
            # old enough to start such a window. The evidence cadence (12 ms live) need not divide 100 ms, so a window that is cut
            # back to at most 100 ms (the first version) never reaches it: live it stalled at 96 ms and every run refused.
            while len(window) >= 2 and now_s - window[1][0] >= STABILITY_WINDOW_S - _WINDOW_TOLERANCE_S:
                window.pop(0)
            span_s = now_s - window[0][0]
            widest_span_s = max(widest_span_s, span_s)
            if span_s >= STABILITY_WINDOW_S - _WINDOW_TOLERANCE_S:
                tilts = [item[1] for item in window]
                if max(tilts) - min(tilts) < STABILITY_RANGE_RAD:
                    cup_z = value.object_state.position_world[2]
                    self._require_fresh_joint_state()
                    tcp_z = self._ik.forward(self._motion_planning_start()).position_m[2]
                    self._require_fresh_joint_state()
                    tilts.sort()
                    return tilts[len(tilts) // 2], tcp_z - cup_z
        tilts_seen = [item[1] for item in seen]
        latest = [item[1] for item in window]
        raise PlaceHeightRefused(
            TILT_UNSTABLE,
            f"no {STABILITY_WINDOW_S * 1000:.0f} ms window with a tilt range under {math.degrees(STABILITY_RANGE_RAD):.2f} deg "
            f"within {STABILITY_TIMEOUT_S:.0f} s; samples {len(seen)}"
            + (f", simulation span {seen[-1][0] - seen[0][0]:.3f} s, tilt range {math.degrees(max(tilts_seen) - min(tilts_seen)):.4f} deg, "
               f"latest window {len(window)} samples over {window[-1][0] - window[0][0]:.3f} s with range "
               f"{math.degrees(max(latest) - min(latest)):.4f} deg, widest window {widest_span_s:.3f} s" if seen else ", none received"))

    def _require_fresh_joint_state(self) -> None:
        """k is computed from the joint state: it must be younger than the execution policy's ``state_max_age_s``."""

        from ..core.place_height import MEASUREMENT_FAILED, PlaceHeightRefused

        policy = getattr(self, "_teacher_execution_policy", None) or {}
        max_age = policy.get("state_max_age_s", _DEFAULT_STATE_MAX_AGE_S)
        received = getattr(self, "_joint_state_received_monotonic_s", None)
        age = None if received is None else self._monotonic() - received
        if age is None or not 0.0 <= age <= max_age:
            raise PlaceHeightRefused(MEASUREMENT_FAILED, f"the joint state is not fresh (age {age}, limit {max_age} s)")

    def _planning_scaling(self, state: State) -> tuple[float, float]:
        """(velocity, acceleration) MoveIt scaling: the frozen carry values for the carry states with frozen inputs."""

        template = (self._template.velocity_scaling, self._template.acceleration_scaling)
        if getattr(self, "_execution_snapshot_root", None) is None or state not in self._CARRY_STATES:
            return template
        policy = getattr(self, "_teacher_execution_policy", None)
        if (policy is None or "carry_max_velocity_scaling" not in policy
                or "carry_max_acceleration_scaling" not in policy):
            raise RuntimeError("TEACHER_POLICY_UNAVAILABLE: carry scaling")
        return float(policy["carry_max_velocity_scaling"]), float(policy["carry_max_acceleration_scaling"])

    def _close_target_q6(self) -> float:
        """The CLOSE_GRIPPER target: the frozen Teacher policy value with frozen inputs, else the original constant."""

        if getattr(self, "_execution_snapshot_root", None) is None:
            return self._CLOSE_Q6
        policy = getattr(self, "_teacher_execution_policy", None)
        if policy is None or "gripper_close_target_rad" not in policy:
            raise RuntimeError("TEACHER_POLICY_UNAVAILABLE: gripper_close_target_rad")
        return float(policy["gripper_close_target_rad"])

    def _perform_state(self, state: State, target: PoseEvidence | None) -> ActionResult:
        try:
            self._check_stop()  # the state machine never starts a new state, hence a new goal, after a stop
            self._safety_state = state
            target = self._place_target(state, target)
            if getattr(self, "_initial", None) is None and not getattr(self, "_teacher_start_attempted", False):
                # The Teacher's own start observation: read from its world observer after reset and before the first
                # arm or gripper command, independent of the recorder, the capture and the data side.
                self._teacher_start_attempted = True
                started = self._capture_teacher_start()
                if started is not None:
                    self._initial = started
            self._scene_state_value = state.value
            self._phase_open(state, target)
            if self._initial is None:
                self._initial = self._snapshot()
            if state is State.DESCEND:
                # The final approach intentionally brings the gripper and jaw into
                # contact with the cup. Keep this exception narrow and remove it
                # immediately after MoveIt owns the attached object.
                self._set_touch_collision(True)
            if target is not None:
                if state in {State.RETREAT, State.RECOVER_RETREAT}:
                    # The released cup has already been restored as a world object,
                    # while the gripper begins this motion inside its conservative
                    # collision proxy. Allow only the cup touch pair until the
                    # gripper has physically retreated, then restore normal checks.
                    self._set_touch_collision(True)
                    try:
                        self._motion(state, target)
                    finally:
                        self._set_touch_collision(False)
                else:
                    self._motion(state, target)
            elif state is State.PREPARE_OPEN_GRIPPER:
                self._command_gripper(state, self._PREOPEN_Q6)
            elif state is State.CLOSE_GRIPPER:
                self._command_gripper(state, self._close_target_q6())
            elif state is State.WAIT_GRASP_STABLE:
                before = self._snapshot()
                try:
                    after = self._wait_stable(self._bilateral, 0.25, 6.0)
                except RuntimeError as error:
                    if str(error) != "DYNAMIC_STABLE_STATE_TIMEOUT":
                        raise
                    # Audit-only (D3): an unstable grasp is a diagnostic, the endpoint decides the task result.
                    after = self._snapshot()
                    self._record_process_diagnostic(
                        "DYNAMIC_STABLE_STATE_TIMEOUT", state, sample=after,
                        facts={"window_s": 0.25, "timeout_s": 6.0})
                self._record(state, before, after)
            elif state is State.VERIFY_PHYSICAL_GRASP:
                before = self._snapshot()
                if (
                    self._before_micro_lift is None
                    or before.object_state.position_world[2]
                    - self._before_micro_lift.object_state.position_world[2]
                    < 0.001
                    or not self._bilateral(before)
                ):
                    # Audit-only (D3): the transition proceeds to ATTACH_MOVEIT.
                    lift = (None if self._before_micro_lift is None else
                            before.object_state.position_world[2]
                            - self._before_micro_lift.object_state.position_world[2])
                    self._record_process_diagnostic(
                        "DYNAMIC_PHYSICAL_GRASP_NOT_PROVED", state, sample=before,
                        facts={"physical_cup_lift_m": lift, "bilateral_contact": self._bilateral(before)})
                self._record(state, before, before)
            elif state is State.ATTACH_MOVEIT:
                self._attach(state)
            elif state in {State.DETACH_MOVEIT, State.SYNC_WORLD_OBJECT}:
                self._detach_or_sync(state)
            elif state is State.OPEN_GRIPPER:
                self._open_supported_gripper(state)
            elif state is State.WAIT_RELEASE_SETTLE:
                self._wait_release(state)
            elif state is State.VALIDATE_FINAL_PLACEMENT:
                self._validate_final(state)
            elif state is State.RECOVER_OPEN_GRIPPER:
                self._open_supported_gripper(state)
            elif state in {State.RECOVER_DETACH_MOVEIT, State.RECOVER_SYNC_WORLD_OBJECT}:
                self._detach_or_sync(state)
            elif state is State.RECOVER_DETACH_GAZEBO:
                value = self._snapshot()
                self._record(state, value, value, simulator_constraint_calls=0)
            else:
                value = self._snapshot()
                self._record(state, value, value)
            self._phase_finish("SUCCEEDED")
            return ActionResult(ActionStatus.SUCCEEDED)
        except Exception as error:
            code = str(error).split(":", 1)[0] or "DYNAMIC_EXECUTION_FAILED"
            self._document["last_error"] = str(error)
            self._phase_finish("FAILED", code)
            self._write()
            return ActionResult(
                ActionStatus.FAILED,
                Failure(FailureCategory.EXECUTION, code, str(error)),
            )

    def close(self) -> None:
        self._close_event_stream()
        self._node.destroy_subscription(self._joint_subscription)
