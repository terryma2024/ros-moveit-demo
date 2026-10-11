"""Task station configuration and environment."""

from __future__ import annotations

from collections.abc import Mapping
import os
import sys

from so101_demo.application.qualification_stack import ros2_command
from so101_demo.parallel_batch.resource_allocation.models import WorkerResources
from so101_demo.runtime.task_stack import (
    PersistentStackConfig,
    StackProcessSpec,
)


def headless_task_station_config(resources: WorkerResources) -> PersistentStackConfig:
    """Construct the single supported Linux headless Worker launch command."""

    if not isinstance(resources, WorkerResources):
        raise TypeError("WorkerResources are required")
    command = ros2_command(
        "launch",
        "so101_demo_py",
        "so101_mujoco_task_station.launch.py",
        "headless:=true",
        "sensor_rendering:=true",
        "include_teleop:=false",
        f"session_id:={resources.session_id}",
        f"task_evidence_root:={resources.worker_root}",
    )
    return PersistentStackConfig(
        resources.session_id,
        True,
        resources.worker_root,
        (StackProcessSpec("task-station", tuple(command)),),
    )


def task_station_config(
    resources: WorkerResources, *, platform: str | None = None
) -> PersistentStackConfig:
    """The single station command this platform can actually run.

    Linux keeps the frozen headless command byte for byte. Darwin cannot use it: the task station
    launcher refuses `headless:=true` on macOS because the MuJoCo viewer's render context must be
    created on the AppKit main thread, so a macOS Worker owns a *visible* station instead. Any
    other platform fails closed rather than silently launching the wrong shape.
    """

    resolved = sys.platform if platform is None else platform
    if resolved == "linux":
        return headless_task_station_config(resources)
    if resolved != "darwin":
        raise RuntimeError(f"unsupported task station platform: {resolved}")
    if not isinstance(resources, WorkerResources):
        raise TypeError("WorkerResources are required")
    command = ros2_command(
        "launch",
        "so101_demo_py",
        "so101_mujoco_task_station.launch.py",
        "headless:=false",
        "sensor_rendering:=true",
        "include_teleop:=false",
        f"session_id:={resources.session_id}",
        f"task_evidence_root:={resources.worker_root}",
    )
    return PersistentStackConfig(
        resources.session_id,
        False,
        resources.worker_root,
        (StackProcessSpec("task-station", tuple(command)),),
    )


#: A station that resolves its nodes from another checkout is not evidence for this branch. The
#: canonical project install is the concrete case CP-UQ261 hit: `ros2_control_node` waited forever
#: for a `/robot_description` the mismatched node set never published.
CANONICAL_INSTALL_MARKER = "moveit-demo/install"


#: Every variable discovery walks. They are scrubbed together because AMENT_PREFIX_PATH alone is
#: not enough: `ros2 run`/`launch` also resolve executables through PATH and libraries through
#: DYLD_LIBRARY_PATH.
_DISCOVERY_VARIABLES = (
    "AMENT_PREFIX_PATH",
    "CMAKE_PREFIX_PATH",
    "COLCON_PREFIX_PATH",
    "PATH",
    "PYTHONPATH",
    "DYLD_LIBRARY_PATH",
    "LD_LIBRARY_PATH",
)


def station_environment(
    resources: WorkerResources | None = None, *, base: Mapping[str, str] | None = None
) -> dict[str, str]:
    """The environment a station may run under: this checkout's chain, never another checkout's.

    Canonical prefixes are stripped from every discovery variable, then the merged result is
    checked again - including whatever the Worker's own environment contributes - and a surviving
    canonical prefix is a refusal rather than a silent launch from the wrong build.
    """

    environment = dict(os.environ if base is None else base)
    for name in _DISCOVERY_VARIABLES:
        value = environment.get(name)
        if not value:
            continue
        kept = [
            entry
            for entry in value.split(os.pathsep)
            if CANONICAL_INSTALL_MARKER not in entry
        ]
        environment[name] = os.pathsep.join(kept)
    if resources is not None:
        environment.update(dict(resources.environment or {}))
        environment["ROS_DOMAIN_ID"] = str(resources.ros_domain_id)
    for name in _DISCOVERY_VARIABLES:
        if CANONICAL_INSTALL_MARKER in environment.get(name, ""):
            raise RuntimeError(
                f"CANONICAL_INSTALL_PREFIX: refusing to launch a station with {name} pointing "
                "at another checkout"
            )
    return environment


def _required(name: str):
    def missing(*_args, **_kwargs):
        raise RuntimeError(f"parallel Worker runtime port is required: {name}")

    return missing
