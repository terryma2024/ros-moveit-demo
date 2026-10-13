"""MuJoCo-owned live boundaries used by the simulator-neutral Teleop adapter."""

from __future__ import annotations

from dataclasses import dataclass
import json
import sys
import time

import rclpy
from mujoco_ros2_control_msgs.srv import SetPause

from ...runtime.container_campaign.ros_namespace import (
    container_ros_global_init_options,
    container_ros_namespace,
)
from .client import FreeJointResetOverride, JointResetOverride, MujocoRosClient
from ...act.joints import ACT_JOINTS
from .observer import EvidenceStale, MujocoWorldObserver
from .reset import MujocoResetClient
from ...core.simulation.types import ResetReceipt

CONTROLLERS = ("arm_controller", "gripper_controller")
RESET_JOINTS = (0.0,) * 6
CUP_START = (0.02, -0.28, 0.165)


@dataclass(frozen=True, slots=True)
class TransactionalResetEvidence:
    """Reset receipt plus the exact post-reset joint sample it validated."""

    receipt: ResetReceipt
    joint_positions: tuple[float, ...]

    def __getattr__(self, name):
        return getattr(self.receipt, name)


def _log_pause_snapshot_failure(reason, observer, started_s, timeout_s, requests_sent,
                                response_received, pause_accepted, stale_reads, non_paused_reads):
    """Emit one observation-only stderr line; never raises."""
    try:
        def read(name, default=None):
            try:
                return getattr(observer, name)
            except Exception:
                return default

        latest = None
        try:
            retained = observer.retained_with_receipts()
            if retained:
                record = retained[-1]
                evidence = record.evidence
                latest = {
                    "paused": evidence.paused,
                    "simulation_step": evidence.simulation_step,
                    "simulation_time_s": evidence.simulation_time_s,
                    "receipt_age_s": time.monotonic() - record.received_monotonic_s,
                    "session_id": evidence.simulation_session_id,
                    "reset_epoch": evidence.reset_epoch,
                    "publisher_sequence": evidence.publisher_sequence,
                }
        except Exception:
            latest = None
        payload = {
            "reason": reason,
            "elapsed_s": time.monotonic() - started_s,
            "timeout_s": timeout_s,
            "requests_sent": requests_sent,
            "response_received": response_received,
            "pause_accepted": pause_accepted,
            "publisher_count": read("publisher_count"),
            "callback_count": read("callback_count"),
            "rejected_count": read("rejected_count"),
            "last_rejection": str(read("last_rejection", ""))[:200],
            "latest": latest,
            "stale_reads": stale_reads,
            "non_paused_reads": non_paused_reads,
        }
        print("PAUSE_SNAPSHOT_FAILURE " + json.dumps(payload, default=str), file=sys.stderr, flush=True)
    except Exception:
        pass


class _RosScope:
    """The ROS context one evidence read or reset runs in.

    Outside a container the process-global default context is initialised and shut down here, exactly as before. Inside a
    container stack other task components keep the default context initialised (the retained RGB-D source), and a second
    `init` on it raises `Context.init() must only be called once` while a `shutdown` would pull it out from under them. So
    a container caller gets a private context of its own, with the container addressing, that only it initialises and shuts
    down. No signal handler is installed either way (`container_ros_global_init_options`)."""

    def __init__(self) -> None:
        self.context = None
        self.executor = None
        self._executor_type = None
        if container_ros_namespace() is None:
            rclpy.init(**container_ros_global_init_options())
            return
        from rclpy.context import Context
        from rclpy.executors import SingleThreadedExecutor

        self._executor_type = SingleThreadedExecutor
        self.context = Context()
        try:
            rclpy.init(context=self.context, **container_ros_global_init_options())
        except BaseException:
            self.close()
            raise

    def create_node(self, name: str):
        if self.context is None:
            return rclpy.create_node(name)
        return rclpy.create_node(name, context=self.context)

    def _executor(self):
        if self.executor is None:
            self.executor = self._executor_type(context=self.context)
        return self.executor

    def spin_once(self, node, timeout_sec: float) -> None:
        if self.context is None:
            rclpy.spin_once(node, timeout_sec=timeout_sec)
        else:
            rclpy.spin_once(node, executor=self._executor(), timeout_sec=timeout_sec)

    def ok(self) -> bool:
        return rclpy.ok() if self.context is None else rclpy.ok(context=self.context)

    def client_options(self) -> dict:
        return {} if self.context is None else {"executor": self._executor()}

    def abandon(self, nodes=()) -> None:
        """Release what construction made when it failed half way. The default context is left as it always was."""
        if self.context is not None:
            for node in reversed(nodes):
                node.destroy_node()
            self.close()

    def close(self) -> None:
        if self.context is None:
            rclpy.shutdown()
            return
        if self.executor is not None:
            self.executor.shutdown()
            self.executor = None
        self.context.try_shutdown()


def _pause_snapshot(node, observer, timeout_s: float, scope: _RosScope | None = None):
    started_s = time.monotonic()
    client = node.create_client(SetPause, "/mujoco_ros2_control_node/set_pause")
    if not client.wait_for_service(timeout_sec=timeout_s):
        raise RuntimeError("pause service unavailable")
    discovery_deadline = time.monotonic() + timeout_s
    ok = rclpy.ok if scope is None else scope.ok
    spin_once = rclpy.spin_once if scope is None else scope.spin_once
    while ok() and time.monotonic() <= discovery_deadline:
        if observer.publisher_count > 0:
            break
        spin_once(node, timeout_sec=0.01)
    else:
        raise RuntimeError("atomic evidence publisher discovery timed out")
    request = SetPause.Request()
    request.paused = True
    deadline = time.monotonic() + timeout_s
    retry_period_s = min(0.05, timeout_s / 2.0)
    next_request_s = time.monotonic()
    future = None
    pause_accepted = False
    response_received = False
    requests_sent = 0
    stale_reads = 0
    non_paused_reads = 0
    while ok() and time.monotonic() <= deadline:
        now = time.monotonic()
        if future is None and now >= next_request_s:
            requests_sent += 1
            future = client.call_async(request)
            next_request_s = now + retry_period_s
        spin_once(node, timeout_sec=0.01)
        if future is not None and future.done():
            response = future.result()
            if response is None:
                raise RuntimeError("pause snapshot request failed")
            response_received = True
            pause_accepted = pause_accepted or bool(response.success)
            future = None
        try:
            evidence = observer.snapshot()
        except EvidenceStale:
            stale_reads += 1
            continue
        if evidence.paused:
            return evidence
        non_paused_reads += 1
    reason = ("pause snapshot request timed out" if not response_received
              else "pause snapshot request failed" if not pause_accepted
              else "fresh paused atomic MuJoCo evidence unavailable")
    _log_pause_snapshot_failure(reason, observer, started_s, timeout_s, requests_sent,
                                response_received, pause_accepted, stale_reads, non_paused_reads)
    raise RuntimeError(reason)


def current_evidence(simulation_session_id: str, timeout_s: float = 5.0):
    """Return a fresh paused snapshot without advancing physics."""

    scope = _RosScope()
    try:
        node = scope.create_node("so101_teleop_mujoco_evidence")
        # one-shot: it joins a long-lived stack, possibly just after a reset, behind the publisher's transient-local replay
        observer = MujocoWorldObserver(node, simulation_session_id, max_age_s=1.0, rebaseline_stale_join=True)
    except BaseException:
        scope.abandon()
        raise
    try:
        evidence = _pause_snapshot(node, observer, timeout_s, scope)
        if evidence.simulation_session_id != simulation_session_id:
            raise RuntimeError("atomic evidence session mismatch")
        return evidence
    finally:
        try:
            node.destroy_node()
        finally:
            scope.close()


def transactional_reset(
    simulation_session_id: str,
    *,
    keyframe: str = "task_start",
    expected_object_position=CUP_START,
    free_joint_overrides: tuple[FreeJointResetOverride, ...] = (),
    timeout_s: float = 10.0,
    act_profile: bool = False,
):
    """Run the qualified controller/pause/reset/epoch transaction.

    `act_profile=True` is the ACT station: the neck controller is switched with the arm and gripper and the seven ACT
    joints are written and verified (with the paused scalar snapshot). It carries no broker, lease or reservation.
    """

    teacher = act_profile is True
    scope = _RosScope()
    nodes = []
    try:
        service_node = scope.create_node("so101_teleop_mujoco_reset_services")
        nodes.append(service_node)
        joint_node = scope.create_node("so101_teleop_mujoco_reset_joints")
        nodes.append(joint_node)
        observer_node = scope.create_node("so101_teleop_mujoco_reset_evidence")
        nodes.append(observer_node)
        services = MujocoRosClient(service_node, joint_node, service_timeout_s=timeout_s, **scope.client_options())
        observer = MujocoWorldObserver(observer_node, simulation_session_id, max_age_s=1.0)

        def progress() -> None:
            scope.spin_once(observer_node, timeout_sec=0.005)
            services.progress()

        resetter = MujocoResetClient(
            services,
            observer,
            simulation_session_id=simulation_session_id,
            controller_names=(*CONTROLLERS,"neck_controller") if teacher else CONTROLLERS,
            expected_joint_positions=(0.,)*7 if teacher else RESET_JOINTS,
            expected_object_position=expected_object_position,
            timeout_s=timeout_s,
            progress=progress,
            **({"expected_joint_names":ACT_JOINTS} if teacher else {}),
        )
    except BaseException:
        scope.abandon(nodes)
        raise
    try:
        reset_kwargs={"joint_overrides":tuple(JointResetOverride(name,0.) for name in ACT_JOINTS)} if teacher else {}
        receipt = resetter.reset(keyframe, free_joint_overrides,**reset_kwargs)
        return TransactionalResetEvidence(receipt, services.latest_joint_positions())
    finally:
        try:
            for node in reversed(nodes):
                node.destroy_node()
        finally:
            scope.close()
