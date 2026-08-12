"""Pure parser for the real-stub safety declaration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

ERROR_CODE = "REAL_HARDWARE_NOT_CONFIGURED"


@dataclass(frozen=True, slots=True)
class RealStubSafetyConfiguration:
    execution_allowed: bool
    readiness_error_code: str
    device_access_allowed: bool
    ros_control_io_allowed: bool


def parse_safety_configuration(document: Mapping[str, Any]) -> RealStubSafetyConfiguration:
    """Validate an already-loaded mapping without performing any I/O."""

    safety = document.get("safety")
    if not isinstance(safety, Mapping):
        raise ValueError("real stub safety mapping is required")
    configuration = RealStubSafetyConfiguration(
        execution_allowed=document.get("execution_allowed"),
        readiness_error_code=document.get("readiness_error_code"),
        device_access_allowed=safety.get("device_access_allowed"),
        ros_control_io_allowed=safety.get("ros_control_io_allowed"),
    )
    if configuration.execution_allowed is not False:
        raise ValueError("real stub execution must remain disabled")
    if configuration.readiness_error_code != ERROR_CODE:
        raise ValueError("real stub readiness must use the stable rejection code")
    if configuration.device_access_allowed is not False:
        raise ValueError("real stub device access must remain disabled")
    if configuration.ros_control_io_allowed is not False:
        raise ValueError("real stub ROS control I/O must remain disabled")
    return configuration
