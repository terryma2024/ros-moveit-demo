"""MuJoCo execution adapter for the perception-driven shared workflow."""

from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from so101_demo.application.e2e_acceptance import (
    MANIFEST_SCHEMA_VERSION,
    SCHEMA_GENERAL,
)
from so101_demo.control.gripper.client import GripperClient
from so101_demo.control.moveit.deterministic_horizon import (
    HorizonStep,
)
from so101_demo.control.moveit.planning import MoveItPlanningClient
from so101_demo.control.moveit.pose_ik import create_pose_ik, describe_pose_ik
from so101_demo.control.trajectory.executor import (
    MoveItExecutionClient,
    make_execute_goal,
)
from so101_demo.core.domain import State
from so101_demo.core.dynamic_pick import (
    DynamicPickTemplate,
    ResolvedMotionTargets,
)
from so101_demo.ros.dynamic_execution.evidence import ExecutionEvidence
from so101_demo.ros.dynamic_execution.joint_state import JointStateIntake
from so101_demo.ros.dynamic_execution.motion import MotionExecution
from so101_demo.ros.dynamic_execution.phases import PhaseSequencing
from so101_demo.ros.dynamic_execution.planning import MotionPlanning
from so101_demo.ros.dynamic_execution.release import ReleaseSequence
from so101_demo.ros.dynamic_execution.safety import MotionSafety
from so101_demo.ros.dynamic_execution.scene import SceneOperations
from so101_demo.ros.dynamic_execution.teacher import TeacherRun


class RosDynamicMujocoExecution(ExecutionEvidence, TeacherRun, JointStateIntake, MotionSafety, MotionPlanning, MotionExecution, ReleaseSequence, SceneOperations, PhaseSequencing):
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

        from so101_demo.backends.mujoco.observer import MujocoWorldObserver

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
        from so101_demo.act.endpoint_pose_acceptance import load_development_runtime

        runtime_policy_path = urdf_path.parents[2] / "config/act/endpoint_pose_development_runtime.yaml"
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
        from so101_demo.act.teacher_event_stream import StreamEventSink
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
            "schema": SCHEMA_GENERAL,
            "schema_version": MANIFEST_SCHEMA_VERSION,
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

    # ---- Teacher event stream (Phase A4a): /so101/teacher/events for the independent Recorder process --------------------
    # The Teacher thread only offers events to a bounded queue (never waits, never raises). A publisher thread drains it.

    # ---- Teacher result (Phase A1b): start/end observation, endpoint verdict, audit-only diagnostics -----------------
    # The Teacher decides its own task result from the cup's start and end pose in the executed world. Nothing here
    # reads the episode recorder, the capture or the phase port, so a Teacher without a recorder runs unchanged.

    # Set by the entry that starts an external Recorder (`--collection on`). Off by default: a Teacher with no Recorder
    # issues no extra stop request.
    final_stop_proof_enabled = False
    #: Diagnostic only: the State at whose execute boundary one execution failure is injected (None: off)
    inject_failure_at = None

    # ---- stop flags (user stop, parent death, attempt deadline) -------------------------------------------------------
    # A flag is raised only where a cancel (or no goal at all) follows: the trajectory monitor and the gripper hook
    # while a goal is active, and the wait loops, the state-machine entry and the next-goal sites while none is. It is
    # never raised from `_progress`, which `executor.execute` and `GripperClient.command` call before their monitor:
    # a raise there would leave the active goal running.

    # ---- phase events (SO101_TEACHER_EVENT) ------------------------------------------------------------------------
    # One `phase_begin` and one `phase_finish` per state, each with the sim stamp read at that instant. A state that
    # sends a goal begins at the goal send (after any pre-dispatch check), so the stamp is the one at which the Teacher
    # sent its first command; the Recorder takes its first-command clock from the first such event.

    _GOAL_STATES = frozenset({
        State.PREPARE_OPEN_GRIPPER, State.CLOSE_GRIPPER, State.OPEN_GRIPPER, State.RECOVER_OPEN_GRIPPER})

    # ---- Teacher states (design 2026-10-10 sections 3 and 5a): fixed dwells, the release sequence --------------------------------

    #: the states that move the held cup (after ATTACH_MOVEIT); only MOVE_ABOVE_PLACE moves it laterally
    _CARRY_STATES = frozenset({State.LIFT, State.MOVE_ABOVE_PLACE, State.DESCEND_TO_PLACE})

    def close(self) -> None:
        self._close_event_stream()
        self._node.destroy_subscription(self._joint_subscription)
