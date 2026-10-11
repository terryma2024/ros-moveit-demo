"""Verdict types, the frozen semantic launch contract and the semantic delta check."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
import os
from pathlib import Path

from so101_demo.runtime.macos_dlopen_gate.farm import GateAControlError
from so101_demo.runtime.runtime_closure.identities import RuntimeClosureIdentity


class CurrentBoundaryVerdict(StrEnum):
    UNCONFIRMED_CURRENT = "UNCONFIRMED_CURRENT"
    CONFIRMED_RPATH = "CONFIRMED_RPATH"
    CURRENT_CLOSURE_ALREADY_VALID = "CURRENT_CLOSURE_ALREADY_VALID"
    CURRENT_NON_RPATH_FAILURE = "CURRENT_NON_RPATH_FAILURE"
    INVALID_CONTROL = "INVALID_CONTROL"


class ControllerVerdict(StrEnum):
    NOT_EXCLUDED = "NOT_EXCLUDED"
    EXCLUDED_BEFORE_ROS_PLUGIN_INSTANCE_INIT = (
        "EXCLUDED_BEFORE_ROS_PLUGIN_INSTANCE_INIT"
    )
    CURRENT_CONTROLLER_PATH_OPERATIONAL = "CURRENT_CONTROLLER_PATH_OPERATIONAL"


class LegacyAttribution(StrEnum):
    LEGACY_TRACEABLE = "LEGACY_TRACEABLE"
    LEGACY_PROVENANCE_UNRECOVERABLE = "LEGACY_PROVENANCE_UNRECOVERABLE"


class ObservationClass(StrEnum):
    PASS = "PASS"
    MISSING_VENDOR_BEFORE_ROS_PLUGIN_INSTANCE_INIT = (
        "MISSING_VENDOR_BEFORE_ROS_PLUGIN_INSTANCE_INIT"
    )
    NON_RPATH_FAILURE = "NON_RPATH_FAILURE"
    INVALID = "INVALID"


def _closure_library_directory(vendor_library_directory: Path) -> Path:
    vendor = Path(vendor_library_directory)
    if vendor.parts[-3:] != ("opt", "mujoco_vendor", "lib"):
        raise GateAControlError("CONTROL_SEMANTIC_INVALID", "vendor directory")
    return vendor.parents[2] / "lib"


@dataclass(frozen=True, slots=True)
class FrozenSemanticLaunchContract:
    argv: tuple[str, ...]
    environment: Mapping[str, str]
    python_executable: Path
    ros2_script: Path
    ros_library_directory: Path
    vendor_library_directory: Path

    def __post_init__(self) -> None:
        if not self.argv or any(not isinstance(value, str) or not value for value in self.argv):
            raise GateAControlError("CONTROL_SEMANTIC_INVALID", "argv")
        python_executable = Path(self.python_executable)
        ros2_script = Path(self.ros2_script)
        ros_library = Path(self.ros_library_directory)
        vendor = Path(self.vendor_library_directory)
        closure_library = _closure_library_directory(vendor)
        for value in (python_executable, ros2_script, ros_library, vendor):
            if not value.is_absolute():
                raise GateAControlError("CONTROL_SEMANTIC_INVALID", str(value))
        if self.argv[:2] != (str(python_executable), str(ros2_script)):
            raise GateAControlError("CONTROL_SEMANTIC_INVALID", "ros2 interpreter")
        values = dict(self.environment)
        if any(not isinstance(key, str) or not isinstance(value, str) for key, value in values.items()):
            raise GateAControlError("CONTROL_SEMANTIC_INVALID", "environment")
        dyld = {key: value for key, value in values.items() if key.startswith("DYLD_")}
        baseline = os.pathsep.join((str(closure_library), str(ros_library)))
        allowed_library_paths = {
            baseline,
            os.pathsep.join((baseline, str(vendor))),
        }
        if (
            set(dyld) != {"DYLD_LIBRARY_PATH"}
            or dyld["DYLD_LIBRARY_PATH"] not in allowed_library_paths
        ):
            raise GateAControlError("CONTROL_SEMANTIC_INVALID", "ROS dylib baseline")
        object.__setattr__(self, "environment", values)
        object.__setattr__(self, "python_executable", python_executable)
        object.__setattr__(self, "ros2_script", ros2_script)
        object.__setattr__(self, "ros_library_directory", ros_library)
        object.__setattr__(self, "vendor_library_directory", vendor)

    def as_document(self) -> dict[str, object]:
        return {
            "argv": list(self.argv),
            "environment": dict(sorted(self.environment.items())),
            "python_executable": str(self.python_executable),
            "ros2_script": str(self.ros2_script),
            "ros_library_directory": str(self.ros_library_directory),
            "vendor_library_directory": str(self.vendor_library_directory),
        }

    @classmethod
    def from_document(
        cls, document: Mapping[str, object]
    ) -> "FrozenSemanticLaunchContract":
        raw_argv = document.get("argv")
        raw_environment = document.get("environment")
        if not isinstance(raw_argv, list) or not isinstance(raw_environment, dict):
            raise GateAControlError("CONTROL_SEMANTIC_INVALID")
        return cls(
            argv=tuple(str(value) for value in raw_argv),
            environment={str(key): str(value) for key, value in raw_environment.items()},
            python_executable=Path(str(document["python_executable"])),
            ros2_script=Path(str(document["ros2_script"])),
            ros_library_directory=Path(str(document["ros_library_directory"])),
            vendor_library_directory=Path(str(document["vendor_library_directory"])),
        )


def validate_np_semantic_delta(
    negative: FrozenSemanticLaunchContract,
    positive: FrozenSemanticLaunchContract,
) -> None:
    if negative.argv != positive.argv:
        raise GateAControlError("CONTROL_SEMANTIC_DIFF", "argv")
    if negative.vendor_library_directory != positive.vendor_library_directory:
        raise GateAControlError("CONTROL_SEMANTIC_DIFF", "vendor directory")
    if (
        negative.python_executable != positive.python_executable
        or negative.ros2_script != positive.ros2_script
        or negative.ros_library_directory != positive.ros_library_directory
    ):
        raise GateAControlError("CONTROL_SEMANTIC_DIFF", "ROS bootstrap")
    n = dict(negative.environment)
    p = dict(positive.environment)
    n_dyld = {key: value for key, value in n.items() if key.startswith("DYLD_")}
    baseline = os.pathsep.join(
        (
            str(_closure_library_directory(negative.vendor_library_directory)),
            str(negative.ros_library_directory),
        )
    )
    if n_dyld != {
        "DYLD_LIBRARY_PATH": baseline
    }:
        raise GateAControlError("CONTROL_SEMANTIC_DIFF", "negative ROS baseline")
    expected = dict(n)
    expected["DYLD_LIBRARY_PATH"] = os.pathsep.join(
        (
            baseline,
            str(negative.vendor_library_directory),
        )
    )
    if p != expected:
        raise GateAControlError("CONTROL_SEMANTIC_DIFF", "environment")


def _closure_dylib_basenames(closure: RuntimeClosureIdentity) -> frozenset[str]:
    names = {
        Path(entry.relative_path).name
        for entry in closure.library_inventory
        if Path(entry.relative_path).name.endswith(".dylib")
    }
    names.update(
        Path(alias.relative_path).name for alias in closure.dylib_alias_inventory
    )
    return frozenset(names)
