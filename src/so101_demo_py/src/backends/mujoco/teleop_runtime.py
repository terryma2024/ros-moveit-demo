"""MuJoCo-owned live boundaries used by the simulator-neutral Teleop adapter."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import sys
import threading
import time

import rclpy
from mujoco_ros2_control_msgs.srv import SetPause

from ...ros.kept_nodes import register_kept_ros_nodes
from ...ros.process_init import global_init_options, in_instance_process
from .client import FreeJointResetOverride, JointResetOverride, MujocoRosClient
from ...act.joints import act_joints_for
from ...act.rig_profile import DEFAULT_RIG
from .observer import EvidenceStale, MujocoWorldObserver
from .reset import MujocoResetClient
from ...core.simulation.types import ResetReceipt

CONTROLLERS = ("arm_controller", "gripper_controller")
RESET_JOINTS = (0.0,) * 6
CUP_START = (0.02, -0.28, 0.165)
# A fresh node discovers the pause service from scratch; under load one long wait can miss it. Wait in slices
# (spinning between them) up to the unchanged overall bound, and resend a pause call whose response never came.
PAUSE_SERVICE_WAIT_SLICE_S = 0.5
PAUSE_CALL_TIMEOUT_S = 2.0


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

    Outside an ACT instance the process-global default context is initialised and shut down here, exactly as before. Inside an
    instance stack other task components keep the default context initialised (the retained RGB-D source), and a second
    `init` on it raises `Context.init() must only be called once` while a `shutdown` would pull it out from under them. So
    an instance caller gets a private context of its own that only it initialises and shuts
    down. No signal handler is installed either way (`global_init_options`)."""

    def __init__(self) -> None:
        self.context = None
        self.executor = None
        self._executor_type = None
        if not in_instance_process():
            rclpy.init(**global_init_options())
            return
        from rclpy.context import Context
        from rclpy.executors import SingleThreadedExecutor

        self._executor_type = SingleThreadedExecutor
        self.context = Context()
        try:
            rclpy.init(context=self.context, **global_init_options())
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


def _pause_snapshot(node, observer, timeout_s: float, scope: _RosScope | None = None, client=None,
                    newer_than_call: bool = False):
    """`newer_than_call`: only evidence received after this call began counts. A one-shot observer is new, so every sample it has
    was received after the call began; an observer kept between calls holds the last sample of an earlier call, which says
    nothing about the state now."""
    started_s = time.monotonic()
    if client is None:
        client = node.create_client(SetPause, "/mujoco_ros2_control_node/set_pause")
    ok = rclpy.ok if scope is None else scope.ok
    spin_once = rclpy.spin_once if scope is None else scope.spin_once
    service_deadline = time.monotonic() + timeout_s
    while True:
        remaining_s = service_deadline - time.monotonic()
        if remaining_s <= 0.0 or not ok():
            raise RuntimeError("pause service unavailable")
        if client.wait_for_service(timeout_sec=min(PAUSE_SERVICE_WAIT_SLICE_S, remaining_s)):
            break
        spin_once(node, timeout_sec=0.0)
    discovery_deadline = time.monotonic() + timeout_s
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
    sent_s = 0.0
    pause_accepted = False
    response_received = False
    requests_sent = 0
    stale_reads = 0
    non_paused_reads = 0
    while ok() and time.monotonic() <= deadline:
        now = time.monotonic()
        if future is not None and not future.done() and now - sent_s >= PAUSE_CALL_TIMEOUT_S:
            future = None  # response lost: abandon this call; pause is idempotent, so send it again
        if future is None and now >= next_request_s:
            requests_sent += 1
            future = client.call_async(request)
            sent_s = now
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
            if newer_than_call:
                record = observer.snapshot_with_receipt()
                evidence = record.evidence
            else:
                evidence = observer.snapshot()
        except EvidenceStale:
            stale_reads += 1
            continue
        if newer_than_call and record.received_monotonic_s < started_s:
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


class RetainedEvidence:
    """`current_evidence` over a ROS context, node, observer and pause client that stay open between calls.

    Every one-shot read pays for a new context, node, subscription and pause-service discovery (seconds under load), and one
    task reads the evidence a handful of times. This keeps them for the task: each call still sends the pause request and
    returns a fresh paused snapshot of the same session, so what it returns is what `current_evidence` returns. Only inside an
    ACT instance process, where the scope is a private context; anywhere else, and on any failure of the retained path, the call
    is the one-shot read (the retained parts are dropped first and reopened by the next call). A publisher sequence gap is
    expected here (a depth-1 subscription that nobody spins between calls keeps only the newest sample) and is data
    completeness, not a hazard; a reset in between shows as a rejection and ends up in the one-shot read as well."""

    def __init__(self, simulation_session_id: str, *, one_shot=None, in_instance=in_instance_process) -> None:
        self._session_id = simulation_session_id
        self._one_shot = current_evidence if one_shot is None else one_shot
        self._in_instance = in_instance
        self._lock = threading.Lock()
        self._scope = self._node = self._observer = self._client = None
        register_kept_ros_nodes(self)

    def _open(self) -> None:
        scope = _RosScope()
        try:
            node = scope.create_node("so101_teleop_mujoco_evidence_retained")
        except BaseException:
            scope.abandon()
            raise
        self._scope, self._node = scope, node
        self._observer = MujocoWorldObserver(node, self._session_id, max_age_s=1.0, rebaseline_stale_join=True,
                                             on_sequence_gap=lambda _previous, _current: None)
        self._client = node.create_client(SetPause, "/mujoco_ros2_control_node/set_pause")

    def close(self) -> None:
        with self._lock:
            self._drop()

    def release(self) -> None:
        """Close the node before an inventory check of the domain (see `so101_demo.ros.kept_nodes`); the next read reopens it."""
        self.close()

    def _drop(self) -> None:
        scope, node = self._scope, self._node
        self._scope = self._node = self._observer = self._client = None
        if node is not None:
            try:
                node.destroy_node()
            except BaseException:
                pass
        if scope is not None:
            try:
                scope.close()
            except BaseException:
                pass

    def __call__(self, simulation_session_id: str, timeout_s: float = 5.0):
        if simulation_session_id != self._session_id or not self._in_instance():
            return self._one_shot(simulation_session_id, timeout_s=timeout_s)
        with self._lock:
            try:
                if self._node is None:
                    self._open()
                evidence = _pause_snapshot(self._node, self._observer, timeout_s, self._scope, self._client, newer_than_call=True)
                if evidence.simulation_session_id != simulation_session_id:
                    raise RuntimeError("atomic evidence session mismatch")
                return evidence
            except Exception:
                self._drop()
        return self._one_shot(simulation_session_id, timeout_s=timeout_s)


def transactional_reset(
    simulation_session_id: str,
    *,
    keyframe: str = "task_start",
    expected_object_position=CUP_START,
    free_joint_overrides: tuple[FreeJointResetOverride, ...] = (),
    timeout_s: float = 10.0,
    act_profile: bool = False,
    rig=DEFAULT_RIG,
    start_joint_positions=None,
):
    """Run the qualified controller/pause/reset/epoch transaction.

    `act_profile=True` is the ACT station: the neck controller is switched with the arm and gripper and the seven ACT
    joints are written and verified (with the paused scalar snapshot). It carries no broker, lease or reservation.
    A `rig` without a neck (the side+wrist rig) has no neck controller and its ACT joints are the six arm joints.

    `start_joint_positions` (R3-a) is the joint vector the ACT reset writes and verifies instead of all zero, one finite value per ACT
    joint of the rig; None is the all-zero `task_start` reset. Only the ACT station takes it.
    """

    teacher = act_profile is True
    joints = act_joints_for(rig)
    if start_joint_positions is None:
        start = (0.,) * len(joints)
    else:
        try:
            start = tuple(float(value) for value in start_joint_positions)
        except (TypeError, ValueError):
            start = ()
        if not teacher or len(start) != len(joints) or any(not math.isfinite(value) for value in start):
            raise ValueError("START_JOINT_POSITIONS_INVALID: one finite value per ACT joint, ACT station only")
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
            controller_names=(*CONTROLLERS,*(("neck_controller",) if rig.has_neck else ())) if teacher else CONTROLLERS,
            expected_joint_positions=start if teacher else RESET_JOINTS,
            expected_object_position=expected_object_position,
            timeout_s=timeout_s,
            progress=progress,
            **({"expected_joint_names":joints,"act_audit":True} if teacher else {}),
        )
    except BaseException:
        scope.abandon(nodes)
        raise
    try:
        reset_kwargs={"joint_overrides":tuple(JointResetOverride(name,position) for name,position in zip(joints,start))} if teacher else {}
        receipt = resetter.reset(keyframe, free_joint_overrides,**reset_kwargs)
        return TransactionalResetEvidence(receipt, services.latest_joint_positions())
    finally:
        try:
            for node in reversed(nodes):
                node.destroy_node()
        finally:
            scope.close()
