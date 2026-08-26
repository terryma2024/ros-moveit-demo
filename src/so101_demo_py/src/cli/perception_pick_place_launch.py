"""Status-preserving command boundary for the MuJoCo perception launch."""

from __future__ import annotations

import sys
from collections.abc import Iterable

from launch.actions import SetLaunchConfiguration
from ros2launch.api.api import parse_launch_arguments

from launch import LaunchDescription, LaunchService

from ..runtime.launch_composition import (
    PerceptionLaunchExitStatus,
    build_perception_pick_place_launch_description,
)


def run_launch_description(
    description: LaunchDescription,
    exit_status: PerceptionLaunchExitStatus,
    *,
    argv: Iterable[str] | None = None,
) -> int:
    """Run a description and return its original terminal child status."""
    arguments = list(argv or ())
    launch_configurations = [
        SetLaunchConfiguration(name, value) for name, value in parse_launch_arguments(arguments)
    ]
    configured_description = LaunchDescription([*launch_configurations, *description.entities])
    service = LaunchService(argv=arguments)
    service.include_launch_description(configured_description)
    return exit_status.resolve(service.run())


def main(argv: Iterable[str] | None = None) -> int:
    """Run the installed perception launch with status-preserving semantics."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    exit_status = PerceptionLaunchExitStatus()
    description = build_perception_pick_place_launch_description(exit_status)
    return run_launch_description(description, exit_status, argv=arguments)
