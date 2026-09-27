"""Exact bounded probes for one admitted Task 8 ACT stack lifecycle."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import time
from typing import Mapping

from .act_stack import ActStackLaunch, ActStackProcessOwner
from .bridge import ActChildLaunch
from .pick_place_startup_issuer import InstalledActStackReadinessProbe
from .controller_reservation_paths import (
    controller_reservation_directory, controller_reservation_root,
)


class RepeatableActStackStopProbe:
    """Reobserve physical stop whenever an owner retry still has a live stack."""

    def __init__(self, launch: ActStackLaunch, executable: Path, *,
                 run=subprocess.run, clock_ns=time.monotonic_ns) -> None:
        self.launch, self.executable = launch, Path(executable)
        self.run, self.clock_ns = run, clock_ns
        self.timeout_s = 7.0
        self.process_timeout_s = 10.0
        self._new_probe()

    def _new_probe(self) -> InstalledActStackReadinessProbe:
        return InstalledActStackReadinessProbe(
            self.launch, self.executable, run=self.run, clock_ns=self.clock_ns,
            timeout_s=self.timeout_s, process_timeout_s=self.process_timeout_s,
        )

    def __call__(self) -> bool:
        return self._new_probe()()


class RosGraphClearProbe:
    """Require no ROS nodes in this stack's exact domain after group retirement."""

    def __init__(self, launch: ActStackLaunch, *, run=subprocess.run,
                 timeout_s: float = 8.0) -> None:
        if (not isinstance(launch, ActStackLaunch) or not callable(run)
                or not 0 < timeout_s <= 10):
            raise ValueError("ACT_STACK_GRAPH_PROBE_CONFIG_INVALID")
        self.launch, self.run, self.timeout_s = launch, run, timeout_s

    def __call__(self) -> bool:
        argv = [str(self.launch.ros2_executable), "node", "list", "--no-daemon"]
        try:
            result = self.run(
                argv, env=self.launch.process_environment(), shell=False,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=self.timeout_s, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return (result.returncode == 0 and isinstance(result.stdout, bytes)
                and not result.stdout.strip())


def make_pick_place_act_stack(context, child: ActChildLaunch, *,
                         ros2_executable: Path, readiness_executable: Path,
                         base_environment: Mapping[str, str]) -> ActStackProcessOwner:
    """Create the only stack scope allowed for one admitted full Task 8 case."""
    try:
        campaign = context.campaign_id
        campaign_root = Path(context.evidence_root)
        observer = Path(readiness_executable)
        if (not isinstance(child, ActChildLaunch)
                or context.workload_kind != "task8_full" or context.worker_count != 1
                or context.execution_generation != child.execution_generation
                or campaign != child.campaign_id
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", campaign) is None
                or not campaign_root.is_absolute() or ".." in campaign_root.parts
                or not campaign_root.is_dir() or campaign_root.is_symlink()
                or not isinstance(base_environment, Mapping)
                or not observer.is_absolute() or ".." in observer.parts
                or observer.is_symlink() or not observer.is_file()
                or not os.access(observer, os.X_OK)):
            raise ValueError("scope")
        stack_root = campaign_root / "task8-live" / campaign / "stack"
        if (stack_root.parent.parent.is_symlink() or stack_root.parent.is_symlink()
                or stack_root.exists() or stack_root.is_symlink()):
            raise ValueError("existing or linked scope")
        stack_root.parent.mkdir(parents=True, exist_ok=True)
        if stack_root.parent.parent.is_symlink() or stack_root.parent.is_symlink():
            raise ValueError("linked scope")
        stack_root.mkdir(mode=0o700)
        environment = dict(base_environment)
        environment["GZ_PARTITION"] = f"act-pick-place-{child.ros_domain_id}-{campaign}"
        reservation_root = controller_reservation_root(campaign_root, environment)
        environment["SO101_ACT_RESERVATION_ROOT"] = str(reservation_root)
        environment["SO101_ACT_CONTROLLER_RESERVATION_DIR"] = str(
            controller_reservation_directory(reservation_root, child.mujoco_session_id))
        launch = ActStackLaunch(
            ros2_executable=Path(ros2_executable), session_id=child.mujoco_session_id,
            evidence_root=stack_root, ros_domain_id=child.ros_domain_id,
            environment=environment,
        )
        ready = InstalledActStackReadinessProbe(launch, observer)
        stopped = RepeatableActStackStopProbe(launch, observer)
        graph = RosGraphClearProbe(launch)
        return ActStackProcessOwner(
            launch, ready_probe=ready, stop_probe=stopped,
            graph_clear_probe=graph,
        )
    except (AttributeError, OSError, TypeError, ValueError) as error:
        raise ValueError("ACT_STACK_FACTORY_SCOPE_INVALID") from error


# Legacy API for version-one stack ownership.
make_task8_act_stack = make_pick_place_act_stack
