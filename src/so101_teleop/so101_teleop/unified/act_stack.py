"""Exact process owner for one admitted, broker-free ACT MuJoCo stack.

The readiness, physical stop and ROS graph probes are required dependencies.
This owner does not infer any of those properties from process liveness.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Callable, Mapping

from so101_teleop.owned_group import terminate_group
from .bridge import (
    _require_group_clear, _retirement_owner_state, _write_retirement_receipt,
    identity_for,
)
from .contracts import MutationError, OwnerKey


@dataclass(frozen=True, slots=True)
class ActStackLaunch:
    ros2_executable: Path
    session_id: str
    evidence_root: Path
    ros_domain_id: int
    environment: Mapping[str, str]

    def __post_init__(self) -> None:
        binary, root = Path(self.ros2_executable), Path(self.evidence_root)
        if (sys.platform != "linux" or not binary.is_absolute() or ".." in binary.parts
                or not binary.is_file() or not os.access(binary, os.X_OK)):
            raise ValueError("ACT_STACK_EXECUTABLE_INVALID")
        if (not root.is_absolute() or ".." in root.parts or not root.is_dir()
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", self.session_id)
                or type(self.ros_domain_id) is not int or not 0 <= self.ros_domain_id <= 232
                or not isinstance(self.environment, Mapping)
                or any(not isinstance(key, str) or not isinstance(value, str)
                       for key, value in self.environment.items())):
            raise ValueError("ACT_STACK_LAUNCH_INVALID")

    def argv(self) -> list[str]:
        return [
            str(self.ros2_executable), "launch", "so101_demo_py",
            "so101_mujoco_act_execution_stack.launch.py",
            "headless:=true", "sensor_rendering:=true", "act_profile:=true",
            f"session_id:={self.session_id}", f"task_evidence_root:={self.evidence_root}",
        ]

    def process_environment(self) -> dict[str, str]:
        return {
            **self.environment,
            "ROS_DOMAIN_ID": str(self.ros_domain_id),
            "SO101_SIMULATION_SESSION_ID": self.session_id,
            "SO101_TASK_EVIDENCE_ROOT": str(self.evidence_root),
        }


class ActStackProcessOwner:
    """Own one process group, retaining its fence until all proofs are durable."""

    def __init__(
        self, launch: ActStackLaunch, *, ready_probe: Callable[[], bool],
        stop_probe: Callable[[], bool], graph_clear_probe: Callable[[], bool],
        popen=subprocess.Popen,
    ) -> None:
        if not isinstance(launch, ActStackLaunch) or not all(
            callable(probe) for probe in (ready_probe, stop_probe, graph_clear_probe)
        ):
            raise ValueError("ACT_STACK_OWNER_CONFIG_INVALID")
        self.launch = launch
        self.ready_probe = ready_probe
        self.stop_probe = stop_probe
        self.graph_clear_probe = graph_clear_probe
        self.popen = popen
        self.process: subprocess.Popen | None = None
        self.owner: OwnerKey | None = None

    async def start(self, *, timeout_s: float = 90.0) -> OwnerKey:
        if self.process is not None:
            raise MutationError("ACT_STACK_ALREADY_STARTED")
        if not 0 < timeout_s <= 300:
            raise MutationError("ACT_STACK_TIMEOUT_INVALID")
        argv = self.launch.argv()
        environment = self.launch.process_environment()
        self.process = self.popen(
            argv, env=environment, shell=False, start_new_session=True,
            stdin=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + timeout_s
        identity_deadline = min(deadline, time.monotonic() + 1.0)
        while True:
            try:
                self.owner = identity_for(self.process.pid, argv, environment)
                break
            except MutationError as error:
                if self.process.poll() is not None:
                    raise MutationError("ACT_STACK_EXITED_BEFORE_IDENTITY") from error
                if time.monotonic() >= identity_deadline:
                    raise MutationError("ACT_STACK_IDENTITY_UNAVAILABLE") from error
                await asyncio.sleep(0.01)
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise MutationError("ACT_STACK_EXITED_BEFORE_READY")
            try:
                if await asyncio.wait_for(asyncio.to_thread(self.ready_probe),
                                          timeout=max(0.001, deadline - time.monotonic())) is True:
                    return self.owner
            except (OSError, ValueError, asyncio.TimeoutError) as error:
                raise MutationError("ACT_STACK_READINESS_UNPROVED") from error
            await asyncio.sleep(0.02)
        raise MutationError("ACT_STACK_READINESS_UNPROVED")

    async def stop(self, *, timeout_s: float = 5.0) -> None:
        if self.process is None:
            return
        if self.owner is None:
            raise MutationError("ACT_STACK_OWNER_UNVERIFIED")
        if not 0 < timeout_s <= 30:
            raise MutationError("ACT_STACK_TIMEOUT_INVALID")
        try:
            stopped = await asyncio.wait_for(asyncio.to_thread(self.stop_probe), timeout_s)
        except (OSError, ValueError, asyncio.TimeoutError) as error:
            raise MutationError("STOP_NOT_CONFIRMED") from error
        if stopped is not True:
            raise MutationError("STOP_NOT_CONFIRMED")
        owner = self.owner
        state = _retirement_owner_state(owner)
        if state not in ("live", "exited"):
            raise MutationError("ACT_STACK_OWNER_IDENTITY_DRIFT")
        receipt = None
        if state == "live":
            receipt = terminate_group(
                pgid=owner.pgid, leader_pid=owner.pid, timeout_s=timeout_s,
            )
            if not receipt.clear:
                raise MutationError("STOP_NOT_CONFIRMED")
        try:
            self.process.wait(timeout=1.0)
        except subprocess.TimeoutExpired as error:
            raise MutationError("STOP_NOT_CONFIRMED") from error
        _require_group_clear(owner.pgid)
        try:
            graph_clear = await asyncio.wait_for(asyncio.to_thread(self.graph_clear_probe), timeout_s)
        except (OSError, ValueError, asyncio.TimeoutError) as error:
            raise MutationError("GRAPH_NOT_CLEARED") from error
        if graph_clear is not True:
            raise MutationError("GRAPH_NOT_CLEARED")
        try:
            _write_retirement_receipt(self.launch.evidence_root, {
                "schema_version": 1,
                "leader_pid": owner.pid,
                "pgid": owner.pgid,
                "started_ticks": owner.started_ticks,
                "argv_sha256": owner.argv_sha256,
                "session_id": self.launch.session_id,
                "ros_domain_id": self.launch.ros_domain_id,
                "group_clear": True,
                "graph_clear": True,
                "physical_stop_confirmed": True,
                "parent_exited": state == "exited",
                "term_sent": receipt.term_sent if receipt else False,
                "kill_sent": receipt.kill_sent if receipt else False,
                "finished_at_monotonic_ns": time.monotonic_ns(),
            })
        except (OSError, TypeError, ValueError) as error:
            raise MutationError("ACT_STACK_RECEIPT_FAILED") from error
        self.process = None
        self.owner = None
