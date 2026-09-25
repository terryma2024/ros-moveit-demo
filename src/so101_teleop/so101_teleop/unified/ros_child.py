"""Non-web ROS child entrypoint.

This module is the only place where ROS is imported. The web process never imports it;
it is executed as ``python -m so101_teleop.unified.ros_child`` with an argv built from
validated server configuration. The child owns its own ROS client, threads and IPC
endpoints, and it never gains the right to stop a simulator, controller or foreign
process it does not own.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import signal
import threading
import time
import uuid
from pathlib import Path

from .child_runtime import ChildIpcServer, ChildRuntime
from .contracts import (
    ActionKey,
    ActionTerminal,
    DispatchAck,
    DispatchToken,
    MutationError,
    OwnerKey,
    PendingChildKey,
)
from .ipc import DEFAULT_MAX_BYTES

CHILD_SERVICE_TOKEN_ENV = "SO101_CHILD_SERVICE_TOKEN"
CHILD_SERVICE_EPOCH_ENV = "SO101_CHILD_SERVICE_EPOCH"
CHILD_WEB_PID_ENV = "SO101_CHILD_WEB_PID"
CHILD_HEARTBEAT_ENV = "SO101_CHILD_HEARTBEAT"
CHILD_HEARTBEAT_TIMEOUT_ENV = "SO101_CHILD_HEARTBEAT_TIMEOUT_S"
CHILD_NORMAL_QUEUE_ENV = "SO101_CHILD_NORMAL_QUEUE_LIMIT"
DEFAULT_HEARTBEAT_TIMEOUT_S = 5.0


def act_identity_from_environment(environment) -> tuple[str | None, str | None, int | None]:
    values = (
        environment.get("SO101_ACT_CAMPAIGN_ID"),
        environment.get("SO101_ACT_WORKER_ID"),
        environment.get("SO101_ACT_GENERATION"),
    )
    if all(value is None for value in values):
        return None, None, None
    if any(not isinstance(value, str) or not value for value in values):
        raise MutationError("ACT_CHILD_IDENTITY_INCOMPLETE")
    if not values[2].isdecimal() or str(int(values[2])) != values[2]:
        raise MutationError("ACT_CHILD_GENERATION_INVALID")
    return values[0], values[1], int(values[2])


class RclpyActionDriver:
    """One child-owned ROS action adapter with real goal and stop evidence.

    ROS imports and node creation remain inside this process. The trusted ACT
    supervisor must register a validated goal before the normal dispatch path
    can submit it; a bare token never creates motion.
    """

    def __init__(self, *, broker=None, owner: OwnerKey | None = None,
                 stop_timeout_s: float | None = None, accept_timeout_s: float | None = None) -> None:
        self._node = None
        self._executor = None
        self._thread = None
        self._broker = broker
        self._owner = owner or local_owner(os.environ.get("SO101_ACT_WORKER_ID", "child"))
        self._stop_timeout_s = float(stop_timeout_s if stop_timeout_s is not None else
                                     os.environ.get("SO101_ACT_STOP_TIMEOUT_S", "2.0"))
        self._accept_timeout_s = float(accept_timeout_s if accept_timeout_s is not None else
                                       os.environ.get("SO101_ACT_ACCEPT_TIMEOUT_S", "2.0"))
        if not (0 < self._stop_timeout_s <= 30 and 0 < self._accept_timeout_s <= 30):
            raise MutationError("ROS_DRIVER_TIMEOUT_INVALID")
        self._goals: dict[str, dict] = {}
        if self._broker is None and os.environ.get("SO101_ACT_CAMPAIGN_ID"):
            self._broker = self._start_ros_broker()

    def _start_ros_broker(self):
        """Provision the existing ACT ROS driver inside this isolated child."""
        try:
            speed = float(os.environ["SO101_ACT_STOP_VELOCITY_RAD_S"])
            max_age = float(os.environ["SO101_ACT_EVIDENCE_MAX_AGE_S"])
        except (KeyError, TypeError, ValueError) as error:
            raise MutationError("ROS_DRIVER_CONFIG_MISSING") from error
        if not (0 <= speed < 1 and 0 < max_age <= 10):
            raise MutationError("ROS_DRIVER_CONFIG_INVALID")
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.parameter import Parameter
        from so101_demo.adapters.act.ros_broker import RosBrokerDriver

        rclpy.init()
        try:
            name = f"act_worker_{os.environ['SO101_ACT_WORKER_ID']}_{os.environ['SO101_ACT_GENERATION']}"
            self._node = rclpy.create_node(name, parameter_overrides=[Parameter("use_sim_time", value=True)])
            broker = RosBrokerDriver(self._node, stop_velocity_rad_s=speed, max_age_s=max_age)
            self._executor = SingleThreadedExecutor()
            self._executor.add_node(self._node)
            self._thread = threading.Thread(target=self._executor.spin, name="act-child-rclpy", daemon=True)
            self._thread.start()
            return broker
        except BaseException:
            if self._node is not None:
                self._node.destroy_node()
            rclpy.shutdown()
            raise

    def allocate_goal_uuid(self, key: PendingChildKey) -> str:
        return str(uuid.uuid4())

    def register_action(self, token: DispatchToken, goal_uuid: str, kind: str, goal) -> None:
        if self._broker is None:
            raise MutationError("ROS_DRIVER_NOT_PROVISIONED")
        if kind not in ("arm", "gripper", "execute_trajectory"):
            raise MutationError("ROS_ACTION_KIND_INVALID")
        try:
            parsed = uuid.UUID(goal_uuid)
        except (TypeError, ValueError) as error:
            raise MutationError("ROS_GOAL_UUID_INVALID") from error
        if str(parsed) != goal_uuid or goal_uuid in self._goals or token.deadline_ns <= time.monotonic_ns():
            raise MutationError("ROS_GOAL_REGISTRATION_INVALID")
        self._goals[goal_uuid] = {"token": token, "kind": kind, "goal": goal,
                                  "internal_id": None, "cancel_requested": False}

    def _record(self, goal_uuid: str) -> dict:
        record = self._goals.get(goal_uuid)
        if record is None:
            raise MutationError("ROS_GOAL_NOT_REGISTERED")
        return record

    def _key(self, token: DispatchToken, goal_uuid: str) -> ActionKey:
        return ActionKey(token.operation_id, token.child_id, goal_uuid, self._owner,
                         token.runtime_id, token.execution_generation)

    def _stop_unknown(self, reason: str) -> None:
        if self._broker is None:
            raise MutationError("ROS_DRIVER_NOT_PROVISIONED")
        try:
            self._broker.stop_all(reason)
        except Exception as error:
            raise MutationError("ROS_STOP_REQUEST_FAILED") from error

    async def submit(self, token: DispatchToken, goal_uuid: str) -> DispatchAck:
        record = self._record(goal_uuid)
        if record["token"] != token or self._broker is None or token.deadline_ns <= time.monotonic_ns():
            raise MutationError("ROS_GOAL_TOKEN_INVALID")
        if record["internal_id"] is None:
            if record["cancel_requested"]:
                raise MutationError("ROS_GOAL_REVOKED")
            try:
                record["internal_id"] = self._broker.submit(
                    record["kind"], record["goal"], goal_uuid=goal_uuid
                )
            except Exception as error:
                self._stop_unknown("ROS_GOAL_SEND_UNKNOWN")
                raise MutationError("ROS_GOAL_SEND_UNKNOWN") from error
        deadline_ns = min(token.deadline_ns, time.monotonic_ns() + int(self._accept_timeout_s * 1e9))
        while time.monotonic_ns() < deadline_ns:
            state = self._broker.goal_state(record["internal_id"])
            if state.get("driver_error"):
                self._stop_unknown("ROS_GOAL_RESPONSE_UNKNOWN")
                raise MutationError("ROS_GOAL_RESPONSE_UNKNOWN")
            if state.get("accepted") is not None:
                if state["accepted"] is True and state.get("ros_goal_uuid") != uuid.UUID(goal_uuid).hex:
                    self._stop_unknown("ROS_GOAL_UUID_MISMATCH")
                    raise MutationError("ROS_GOAL_UUID_MISMATCH")
                return DispatchAck(self._key(token, goal_uuid), state["accepted"] is True)
            await asyncio.sleep(0.005)
        self._stop_unknown("ROS_GOAL_ACCEPT_TIMEOUT")
        raise MutationError("ROS_GOAL_ACCEPT_TIMEOUT")

    async def cancel(self, goal_uuid: str) -> bool:
        record = self._record(goal_uuid)
        record["cancel_requested"] = True
        if self._broker is None:
            raise MutationError("ROS_DRIVER_NOT_PROVISIONED")
        if record["internal_id"] is not None:
            self._broker.cancel(record["internal_id"])
        deadline_ns = time.monotonic_ns() + int(self._stop_timeout_s * 1e9)
        while time.monotonic_ns() < deadline_ns:
            self._broker.refresh_stop()
            if self._broker.stopped():
                return True
            await asyncio.sleep(0.005)
        self._stop_unknown("ROS_STOP_NOT_CONFIRMED")
        return False

    async def terminal(self, goal_uuid: str) -> ActionTerminal:
        record = self._record(goal_uuid)
        if self._broker is None or record["internal_id"] is None:
            raise MutationError("ROS_GOAL_NOT_SUBMITTED")
        token = record["token"]
        while time.monotonic_ns() < token.deadline_ns:
            state = self._broker.goal_state(record["internal_id"])
            if state.get("driver_error"):
                self._stop_unknown("ROS_GOAL_RESULT_UNKNOWN")
                raise MutationError("ROS_GOAL_RESULT_UNKNOWN")
            if state.get("status") in (4, 5, 6):
                self._broker.refresh_idle()
                if self._broker.stopped():
                    result = state.get("result") or {}
                    succeeded = state["status"] == 4 and result.get("error_code") == 0
                    return ActionTerminal(self._key(token, goal_uuid), succeeded, True, True)
            await asyncio.sleep(0.005)
        self._stop_unknown("ROS_GOAL_TERMINAL_TIMEOUT")
        raise MutationError("ROS_GOAL_TERMINAL_TIMEOUT")

    async def stop_act(self, reason: str) -> bool:
        self._stop_unknown(reason)
        deadline_ns = time.monotonic_ns() + int(self._stop_timeout_s * 1e9)
        while time.monotonic_ns() < deadline_ns:
            self._broker.refresh_stop()
            if self._broker.stopped():
                return True
            await asyncio.sleep(0.005)
        return False

    def close(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(timeout_sec=2.0)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._node is not None:
            self._node.destroy_node()
        if self._node is not None:
            import rclpy
            if rclpy.ok():
                rclpy.shutdown()


def local_owner(runtime_id: str) -> OwnerKey:
    import hashlib
    import json
    from ..process_identity import ProcessIdentityError, read_identity

    try:
        identity = read_identity(os.getpid())
    except ProcessIdentityError as error:
        raise MutationError("ACT_CHILD_OWNER_UNREADABLE") from error
    if not identity.live:
        raise MutationError("ACT_CHILD_OWNER_NOT_LIVE")
    return OwnerKey(
        pid=identity.pid,
        pgid=identity.pgid,
        started_ticks=identity.start_marker,
        argv_sha256=identity.command_sha256,
        environment_sha256=hashlib.sha256(json.dumps(dict(os.environ), sort_keys=True).encode()).hexdigest(),
    )


async def watchdog(runtime: ChildRuntime, *, web_pid: int | None, heartbeat: Path | None, timeout_s: float) -> None:
    """Stop accepting mutations and revoke known goals when the web owner disappears."""
    while True:
        await asyncio.sleep(min(timeout_s, 1.0) / 2)
        if runtime.web_dead:
            return
        dead = False
        if web_pid is not None:
            try:
                os.kill(web_pid, 0)
            except (ProcessLookupError, PermissionError):
                dead = True
        if heartbeat is not None:
            if not heartbeat.is_file():
                dead = True
            elif time.time() - heartbeat.stat().st_mtime > timeout_s:
                dead = True
        if dead:
            await runtime.mark_web_dead("web owner heartbeat lost")
            return


async def serve(server: ChildIpcServer, runtime: ChildRuntime, watchdog_task: asyncio.Task) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_name in ("SIGTERM", "SIGINT"):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(getattr(signal, signal_name), stop.set)
    await stop.wait()
    watchdog_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await watchdog_task
    await server.close()
    close_driver = getattr(runtime.driver, "close", None)
    if callable(close_driver):
        close_driver()
    del runtime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SO-101 unified non-web ROS child")
    parser.add_argument("--socket-root", required=True, type=Path)
    parser.add_argument("--runtime-id", required=True)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args(argv)

    service_token = os.environ.get(CHILD_SERVICE_TOKEN_ENV)
    service_epoch = os.environ.get(CHILD_SERVICE_EPOCH_ENV)
    if not service_token or not service_epoch:
        parser.error(f"{CHILD_SERVICE_TOKEN_ENV} and {CHILD_SERVICE_EPOCH_ENV} are required")
    normal_queue_limit = int(os.environ.get(CHILD_NORMAL_QUEUE_ENV, "2"))
    web_pid = os.environ.get(CHILD_WEB_PID_ENV)
    heartbeat = os.environ.get(CHILD_HEARTBEAT_ENV)
    timeout_s = float(os.environ.get(CHILD_HEARTBEAT_TIMEOUT_ENV, DEFAULT_HEARTBEAT_TIMEOUT_S))
    campaign_id, worker_id, generation = act_identity_from_environment(os.environ)

    runtime = ChildRuntime(
        RclpyActionDriver(),
        owner=local_owner(args.runtime_id),
        service_epoch=service_epoch,
        runtime_id=args.runtime_id,
        normal_queue_limit=normal_queue_limit,
        act_campaign_id=campaign_id,
        act_worker_id=worker_id,
        act_generation=generation,
    )
    server = ChildIpcServer(
        runtime,
        socket_root=args.socket_root,
        owner=runtime.owner,
        service_epoch=service_epoch,
        service_token=service_token,
        max_bytes=args.max_bytes,
    )

    async def run() -> None:
        await server.start()
        watchdog_task = asyncio.get_running_loop().create_task(
            watchdog(
                runtime,
                web_pid=int(web_pid) if web_pid else None,
                heartbeat=Path(heartbeat) if heartbeat else None,
                timeout_s=timeout_s,
            )
        )
        await serve(server, runtime, watchdog_task)

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
