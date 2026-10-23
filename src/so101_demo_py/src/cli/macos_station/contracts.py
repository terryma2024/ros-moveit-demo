"""Modes, phases, budgets, failure codes and the report types of the station diagnostic."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class StationDiagnosticError(RuntimeError):
    """Fail-closed diagnostic error with a stable machine-readable code."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


class StationMode(StrEnum):
    MINIMAL_CONTROLLER_MANAGER = "MINIMAL_CONTROLLER_MANAGER"
    ROBOT_SYSTEM_CONTROLLER_MANAGER = "ROBOT_SYSTEM_CONTROLLER_MANAGER"
    FULL_TASK_STATION = "FULL_TASK_STATION"
    FIXED_DYLIB_FARM_FULL_TASK_STATION = "FIXED_DYLIB_FARM_FULL_TASK_STATION"


#: The authorized fixed dylib farm contract (design section 17). The legacy FULL_TASK_STATION
#: N/P/F entry stays as historical diagnostics and is never used for CP-MSC-A2-FARM.
FARM_CONTRACT_RECEIPT_SCHEMA_VERSION = 1


FARM_CLOSURE_PREFIXES = (
    "/opt/ros/jazzy/install",
    "/opt/ros/jazzy/extra_ws/install",
    "/opt/data/so101/runtime/fork/current",
    "/opt/data/so101/workspace/install",
    "/opt/ros/jazzy/dylib_farm/current",
)


FARM_ROOT_HINT = Path("/opt/ros/jazzy/dylib_farm")


READINESS_RELATIVE_PATH = "lib/so101_demo_py/motion_stack_ready"


CONTROLLER_RELATIVE_PATH = "lib/mujoco_ros2_control/ros2_control_node"


PLUGIN_BASENAME = "libmujoco_ros2_control.dylib"


VENDOR_BASENAME = "libmujoco.3.4.0.dylib"


class StationPhase(StrEnum):
    PLUGIN_RESOLVED = "PLUGIN_RESOLVED"
    SIMULATION_ENDPOINT_READY = "SIMULATION_ENDPOINT_READY"
    HARDWARE_INITIALIZING = "HARDWARE_INITIALIZING"
    HARDWARE_READY = "HARDWARE_READY"
    CONTROLLER_MANAGER_SERVICES_READY = "CONTROLLER_MANAGER_SERVICES_READY"
    CONTROLLERS_ACTIVE = "CONTROLLERS_ACTIVE"


_SECOND = 1_000_000_000


PHASE_BUDGETS_NS: Mapping[StationPhase, int] = {
    StationPhase.PLUGIN_RESOLVED: 5 * _SECOND,
    StationPhase.SIMULATION_ENDPOINT_READY: 20 * _SECOND,
    StationPhase.HARDWARE_INITIALIZING: 10 * _SECOND,
    StationPhase.HARDWARE_READY: 10 * _SECOND,
    StationPhase.CONTROLLER_MANAGER_SERVICES_READY: 10 * _SECOND,
    StationPhase.CONTROLLERS_ACTIVE: 30 * _SECOND,
}


HARDWARE_INITIALIZING_BUDGET_NS = PHASE_BUDGETS_NS[StationPhase.HARDWARE_INITIALIZING]


HARDWARE_READY_BUDGET_NS = PHASE_BUDGETS_NS[StationPhase.HARDWARE_READY]


FAILURE_SERVICE_INVISIBLE = "STATION_CONTROLLER_SERVICE_INVISIBLE"


FAILURE_CALL_TIMEOUT = "STATION_CONTROLLER_CALL_TIMEOUT"


FAILURE_CONTROLLERS_NOT_ACTIVE = "STATION_CONTROLLERS_NOT_ACTIVE"


FAILURE_MOVEIT_SERVICES = "STATION_MOVEIT_SERVICES_UNAVAILABLE"


FAILURE_MOVEIT_ACTIONS = "STATION_MOVEIT_ACTIONS_UNAVAILABLE"


_CLI_DEFAULT_TIMEOUT_S = 60.0


@dataclass(frozen=True, slots=True)
class DirectControllerObservation:
    """One bounded direct query of the controller manager, without the MoveIt graph."""

    service_visible: bool
    call_completed: bool
    controllers: Mapping[str, str]
    ros_domain_id: int
    observed_monotonic_ns: int

    def as_document(self) -> dict[str, object]:
        return {
            "service_visible": self.service_visible,
            "call_completed": self.call_completed,
            "controllers": dict(self.controllers),
            "ros_domain_id": self.ros_domain_id,
            "observed_monotonic_ns": self.observed_monotonic_ns,
        }


@dataclass(frozen=True, slots=True)
class PhaseDeadline:
    phase: StationPhase
    deadline_monotonic_ns: int
    observed_monotonic_ns: int | None
    expired: bool

    def as_document(self) -> dict[str, object]:
        return {
            "phase": self.phase.value,
            "deadline_monotonic_ns": self.deadline_monotonic_ns,
            "observed_monotonic_ns": self.observed_monotonic_ns,
            "expired": self.expired,
        }


@dataclass(frozen=True, slots=True)
class StationDiagnosticReport:
    mode: StationMode
    ros_domain_id: int
    observation: DirectControllerObservation
    phases: tuple[PhaseDeadline, ...]
    server_pid: int | None
    server_birth_identity: int | None
    loaded_images: tuple[str, ...]
    node_names: tuple[str, ...]
    service_names: tuple[str, ...]
    failure_code: str | None

    @property
    def last_observed_phase(self) -> StationPhase | None:
        observed = [
            record.phase for record in self.phases if record.observed_monotonic_ns is not None
        ]
        return observed[-1] if observed else None

    def as_document(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "ros_domain_id": self.ros_domain_id,
            "observation": self.observation.as_document(),
            "phases": [record.as_document() for record in self.phases],
            "last_observed_phase": (
                None if self.last_observed_phase is None else self.last_observed_phase.value
            ),
            "server_pid": self.server_pid,
            "server_birth_identity": self.server_birth_identity,
            "loaded_images": list(self.loaded_images),
            "node_names": list(self.node_names),
            "service_names": list(self.service_names),
            "failure_code": self.failure_code,
        }


@dataclass(frozen=True, slots=True)
class StationProcessHandle:
    """The task-owned diagnostic child and the identity read back for it."""

    pid: int
    birth_identity: int
    argv: tuple[str, ...]
    process: object
