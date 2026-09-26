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
import math
import os
import re
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

_ACT_HASH_ENV = {
    "manifest_sha256": "SO101_ACT_MANIFEST_SHA256",
    "runtime_config_sha256": "SO101_ACT_RUNTIME_CONFIG_SHA256",
    "contact_policy_fingerprint": "SO101_ACT_POLICY_FINGERPRINT",
}


def bound_act_source_settings(report: dict, *, timestep_s: float) -> dict[str, float]:
    """Use only measured calibration and the admitted compiled-model timestep."""
    from so101_demo.act.calibration import require_gate

    if not isinstance(report, dict):
        raise ValueError("CALIBRATION_REQUIRED")
    gate = "formal_collection" if report.get("status") == "QUALIFIED" else "pick_place_validation"
    require_gate(report, gate)
    try:
        measured = report["measurements"]
        age = float(measured["max_age_s"]["value"])
        skew = float(measured["max_skew_s"]["value"])
        speed = float(measured["stop_velocity_rad_s"]["value"])
        timestep = float(timestep_s)
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ValueError("CALIBRATION_REQUIRED") from error
    if (not all(math.isfinite(value) for value in (age, skew, speed, timestep))
            or not 0 < age <= 10 or not 0 < skew <= age
            or not 0 <= speed < 1 or not 0 < timestep <= 0.01
            or timestep * 1.5 >= age):
        raise ValueError("CALIBRATION_REQUIRED")
    return {
        "stop_velocity_rad_s": speed,
        "max_wall_age_s": age,
        "max_source_skew_s": skew,
        "max_sim_gap_s": timestep * 1.5,
        "joint_tolerance_rad": 0.002,
        "cup_pose_tolerance_m": 1e-8,
        "cup_orientation_tolerance": 1e-6,
    }


def maybe_provision_pick_place_port(driver):
    """Compose SEARCH only for the admitted, hash-bound Task 8 manifest."""
    manifest = driver._act_artifacts.read_hashed_json("manifest")
    if manifest.get("kind") != "ACT_TASK8_LIVE":
        return None
    from so101_demo.act.pick_place_validation_manifest import require_pick_place_validation_manifest
    from so101_demo.adapters.act.pick_place_child_port import build_pick_place_child_search_port
    from rclpy.parameter import Parameter
    import rclpy

    require_pick_place_validation_manifest(manifest)
    report = driver._act_artifacts.read_hashed_json("calibration_report")
    worker_id = os.environ["SO101_ACT_WORKER_ID"]
    generation = int(os.environ["SO101_ACT_GENERATION"])

    def service_node_factory():
        return rclpy.create_node(
            f"act_pick_place_io_{worker_id}_{generation}",
            parameter_overrides=[Parameter("use_sim_time", value=True)],
        )

    return build_pick_place_child_search_port(
        node=driver._node, model=driver._act_model,
        contact_pairs=driver._act_contact_pairs, manifest=manifest,
        report=report, sources=driver._act_sources,
        command_broker=driver._act_command_broker,
        connection=driver._act_reset_connection,
        cancelled=driver._act_cancelled, binding=driver._act_head_search,
        evidence_root=driver._act_artifacts.evidence_root,
        campaign_id=os.environ["SO101_ACT_CAMPAIGN_ID"],
        worker_id=worker_id, generation=generation,
        scene_node_factory=service_node_factory,
    )


class _FencedPickPlacePort:
    """Prevent a cancelled Task 8 thread from starting its next physical phase."""

    def __init__(self, port, cancelled: threading.Event) -> None:
        self._port = port
        self._cancelled = cancelled

    def __getattr__(self, name):
        method = getattr(self._port, name)
        if name == "safe_stop" or not callable(method):
            return method

        def guarded(*args, **kwargs):
            if self._cancelled.is_set():
                raise MutationError("ACT_TASK8_CANCELLED")
            result = method(*args, **kwargs)
            if self._cancelled.is_set():
                raise MutationError("ACT_TASK8_CANCELLED")
            return result

        return guarded


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
                 stop_timeout_s: float | None = None, accept_timeout_s: float | None = None,
                 pick_place_port=None, task8_port=None,
                 act_hashes: dict[str, str] | None = None,
                 startup_proof_consumer=None) -> None:
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
        if pick_place_port is not None and task8_port is not None:
            raise MutationError("ACT_PICK_PLACE_PORT_AMBIGUOUS")
        self._pick_place_port = pick_place_port if pick_place_port is not None else task8_port
        if startup_proof_consumer is not None and not callable(startup_proof_consumer):
            raise MutationError("TASK8_STARTUP_CONSUMER_INVALID")
        self._startup_proof_consumer = startup_proof_consumer
        self._pick_place_startup_used = False
        self._act_cancelled = threading.Event()
        self._act_hashes = (act_hashes if act_hashes is not None else
                            {key: os.environ.get(name) for key, name in _ACT_HASH_ENV.items()})
        self._act_artifacts = None
        self._act_model = None
        self._act_contact_pairs = None
        self._act_sources = None
        self._act_hazard_dispatcher = None
        self._act_command_broker = None
        self._act_reset_connection = None
        if os.environ.get("SO101_ACT_CAMPAIGN_ID"):
            from .act_artifacts import ActArtifactBinding
            self._act_artifacts = ActArtifactBinding.verify_environment(os.environ)
            digests = dict(self._act_artifacts.hashes)
            if self._act_hashes != {
                "manifest_sha256": digests["manifest"],
                "runtime_config_sha256": digests["runtime_config"],
                "contact_policy_fingerprint": self._act_artifacts.policy_fingerprint,
            }:
                raise ValueError("ACT_ARTIFACT_BINDING_INVALID")
            from so101_demo.act.head_search_binding import validate_head_search_binding
            self._act_head_search = validate_head_search_binding(
                self._act_artifacts.read_hashed_json("runtime_config"),
                self._act_artifacts.read_hashed_json("calibration_report"),
            )
            if self._broker is None:
                from so101_demo.adapters.act.phase_contact_allowlist import load_installed_phase_contact_allowlist
                paths = dict(self._act_artifacts.paths)
                self._act_model, self._act_contact_pairs = load_installed_phase_contact_allowlist(
                    proposal_path=paths["proposal"],
                    receipt_path=paths["activation_receipt"],
                    expected_fingerprint=self._act_artifacts.policy_fingerprint,
                )
        if self._broker is None and os.environ.get("SO101_ACT_CAMPAIGN_ID"):
            self._broker = self._start_ros_broker()

    def _start_ros_broker(self):
        """Provision the existing ACT ROS driver inside this isolated child."""
        if self._act_artifacts is None or self._act_model is None or self._act_contact_pairs is None:
            raise MutationError("ACT_ARTIFACT_BINDING_INVALID")
        report = self._act_artifacts.read_hashed_json("calibration_report")
        settings = bound_act_source_settings(report, timestep_s=self._act_model.opt.timestep)
        speed = settings.pop("stop_velocity_rad_s")
        max_age = settings["max_wall_age_s"]
        session_id = os.environ.get("SO101_SIMULATION_SESSION_ID")
        if not isinstance(session_id, str) or not session_id:
            raise MutationError("ACT_CHILD_IDENTITY_INCOMPLETE")
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.parameter import Parameter
        from so101_demo.act.ownership import Ownership
        from so101_demo.adapters.act.command_broker import CommandBroker, LocalBrokerConnection
        from so101_demo.adapters.act.ros_broker import RosBrokerDriver
        from so101_demo.adapters.act.pick_place_sources import PickPlaceRosEvidence, PickPlaceHazardDispatcher

        rclpy.init()
        try:
            name = f"act_worker_{os.environ['SO101_ACT_WORKER_ID']}_{os.environ['SO101_ACT_GENERATION']}"
            self._node = rclpy.create_node(name, parameter_overrides=[Parameter("use_sim_time", value=True)])
            broker = RosBrokerDriver(self._node, stop_velocity_rad_s=speed, max_age_s=max_age)
            self._act_command_broker = CommandBroker(
                broker, ownership=Ownership(), simulation_session_id=session_id,
            )
            self._act_reset_connection = LocalBrokerConnection(self._act_command_broker)
            self._act_sources = PickPlaceRosEvidence(
                self._node, broker, model=self._act_model,
                contact_pairs=self._act_contact_pairs, session_id=session_id,
                **settings,
            )
            self._act_hazard_dispatcher = PickPlaceHazardDispatcher(
                self._act_sources, broker, self._act_cancelled,
                command_broker=self._act_command_broker,
            )
            self._executor = SingleThreadedExecutor()
            self._executor.add_node(self._node)
            self._thread = threading.Thread(target=self._executor.spin, name="act-child-rclpy", daemon=True)
            self._thread.start()
            self._act_hazard_dispatcher.start()
            self._pick_place_port = maybe_provision_pick_place_port(self)
            return broker
        except BaseException:
            if self._act_reset_connection is not None:
                self._act_reset_connection.close()
                self._act_reset_connection = None
            self._act_command_broker = None
            if self._act_hazard_dispatcher is not None:
                self._act_hazard_dispatcher.close()
            if self._executor is not None:
                self._executor.shutdown(timeout_sec=2.0)
            if self._thread is not None:
                self._thread.join(timeout=2.0)
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
        authority = self._act_command_broker
        if authority is None:
            self._act_cancelled.set()
            self._stop_unknown(reason)
        else:
            if authority.driver is not self._broker:
                raise MutationError("ACT_BROKER_DRIVER_MISMATCH")
            try:
                authority.stop_attempt(reason, cancelled_event=self._act_cancelled)
            except Exception as error:
                raise MutationError("ROS_STOP_REQUEST_FAILED") from error
        deadline_ns = time.monotonic_ns() + int(self._stop_timeout_s * 1e9)
        while time.monotonic_ns() < deadline_ns:
            if authority is None:
                self._broker.refresh_stop()
            else:
                authority.tick()
            if self._broker.stopped() and (authority is None or authority.ownership.state == "IDLE"):
                return True
            await asyncio.sleep(0.005)
        return False

    @property
    def _task8_port(self):
        """Compatibility attribute for version-one child callers."""
        return self._pick_place_port

    @_task8_port.setter
    def _task8_port(self, value) -> None:
        self._pick_place_port = value

    async def _run_pick_place(self, request, *, mode: str) -> dict:
        if self._pick_place_port is None:
            raise MutationError("ACT_TASK8_PORT_NOT_PROVISIONED")
        if self._act_cancelled.is_set():
            raise MutationError("ACT_TASK8_CANCELLED")
        if (not isinstance(self._act_hashes, dict)
                or set(self._act_hashes) != set(_ACT_HASH_ENV)
                or any(not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
                       for value in self._act_hashes.values())):
            raise MutationError("ACT_TASK8_HASHES_NOT_BOUND")
        if any(request.payload.get(key) != value for key, value in self._act_hashes.items()):
            raise MutationError("ACT_TASK8_HASH_MISMATCH")
        if request.deadline_ns <= time.monotonic_ns():
            raise MutationError("ACT_DEADLINE_EXPIRED")
        if self._pick_place_startup_used:
            raise MutationError("TASK8_STARTUP_PROOF_ALREADY_CONSUMED")
        self._pick_place_startup_used = True
        if self._startup_proof_consumer is None:
            from .pick_place_child_startup import consume_child_pick_place_startup
            receipt = consume_child_pick_place_startup(request, self._owner, os.environ)
        else:
            receipt = self._startup_proof_consumer(request)
        bind = getattr(self._pick_place_port, "bind_startup_receipt", None)
        if not callable(bind):
            raise MutationError("ACT_TASK8_PORT_INVALID")
        try:
            bind(receipt)
        except Exception as error:
            raise MutationError("ACT_TASK8_PORT_INVALID") from error
        from so101_demo.act.pick_place_runner import PickPlaceRunner

        task = {
            "mode": mode,
            "stop_after": request.payload.get("stop_after") if mode == "phase_prefix" else None,
            "lifecycle": "FULL_RESTART",
            "scenario_id": request.payload["scenario_id"],
            "session_id": request.session_id,
            "attempt_id": request.attempt_id,
            "deadline_ns": request.deadline_ns,
        }
        try:
            result = await asyncio.to_thread(
                PickPlaceRunner(_FencedPickPlacePort(self._pick_place_port, self._act_cancelled)).run,
                task,
            )
        except BaseException as error:
            if await self.stop_act("TASK8_FAILED") is not True:
                raise MutationError("ACT_TASK8_STOP_NOT_CONFIRMED") from error
            raise MutationError("ACT_TASK8_FAILED") from error
        if await self.stop_act("TASK8_COMPLETED") is not True:
            raise MutationError("ACT_TASK8_STOP_NOT_CONFIRMED")
        if result.get("stopped_confirmed") is not True:
            raise MutationError("ACT_TASK8_STOP_NOT_CONFIRMED")
        return result

    async def pick_place_phase(self, request) -> dict:
        if request.operation != "task8_phase":
            raise MutationError("ACT_TASK8_OPERATION_MISMATCH")
        return await self._run_pick_place(request, mode="phase_prefix")

    async def pick_place_full(self, request) -> dict:
        if request.operation != "task8_full":
            raise MutationError("ACT_TASK8_OPERATION_MISMATCH")
        return await self._run_pick_place(request, mode="full")

    async def task8_phase(self, request) -> dict:
        """Compatibility entry point for version-one IPC dispatchers."""
        return await self.pick_place_phase(request)

    async def task8_full(self, request) -> dict:
        """Compatibility entry point for version-one IPC dispatchers."""
        return await self.pick_place_full(request)

    async def cancel_act(self, request) -> dict:
        reason = request.payload["reason"]
        confirmed = await self.stop_act(reason)
        return {"stopped_confirmed": confirmed is True, "reason": reason}

    async def act_collection_start(self, request) -> dict:
        raise MutationError("ACT_COLLECTION_NOT_PROVISIONED")

    async def act_collection_resume(self, request) -> dict:
        raise MutationError("ACT_COLLECTION_NOT_PROVISIONED")

    def close(self) -> None:
        try:
            if self._act_hazard_dispatcher is not None:
                self._act_hazard_dispatcher.close()
        finally:
            if self._act_reset_connection is not None:
                self._act_reset_connection.close()
                self._act_reset_connection = None
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


# Legacy Python API for version-one pick-place provisioning.
maybe_provision_task8_port = maybe_provision_pick_place_port
