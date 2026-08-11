"""Strict parser for package-installed, immutable backend profiles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Mapping

import yaml

from .protocol import BackendCapabilities, BackendId, BackendOperation


class ProfileError(RuntimeError):
    """A selected backend profile is absent, inconsistent, or unsafe."""


@dataclass(frozen=True)
class ExecutableSpec:
    package: str
    executable: str
    timeout_s: float
    fixed_args: tuple[str, ...] = ()
    scene_style: Literal["positional", "flag"] | None = None


@dataclass(frozen=True)
class BackendProfile:
    backend: BackendId
    owner_package: str
    probe: ExecutableSpec
    capabilities: BackendCapabilities
    operations: Mapping[BackendOperation, ExecutableSpec]


_PROFILE_FIELDS = {"backend", "owner_package", "probe", "capabilities", "operations"}
_SPEC_FIELDS = {"package", "executable", "timeout_s", "fixed_args", "scene_style"}
_CAPABILITY_FIELDS = set(BackendCapabilities.__dataclass_fields__)


def _schema_error(detail: str) -> ProfileError:
    return ProfileError(f"PROFILE_SCHEMA_INVALID: {detail}")


def _require_exact_mapping(value, fields: set[str], label: str) -> dict:
    if not isinstance(value, dict):
        raise _schema_error(f"{label} must be a mapping")
    actual = set(value)
    if actual != fields:
        raise _schema_error(
            f"{label} fields differ; missing={sorted(fields - actual)} "
            f"extra={sorted(actual - fields)}"
        )
    return value


def _parse_spec(value, label: str) -> ExecutableSpec:
    data = _require_exact_mapping(value, _SPEC_FIELDS, label)
    package = data["package"]
    executable = data["executable"]
    timeout_s = data["timeout_s"]
    fixed_args = data["fixed_args"]
    scene_style = data["scene_style"]
    if not isinstance(package, str) or not package:
        raise _schema_error(f"{label}.package must be a non-empty string")
    if not isinstance(executable, str) or not executable:
        raise _schema_error(f"{label}.executable must be a non-empty string")
    if not isinstance(timeout_s, (int, float)) or isinstance(timeout_s, bool) or timeout_s <= 0:
        raise _schema_error(f"{label}.timeout_s must be positive")
    if not isinstance(fixed_args, list) or not all(isinstance(item, str) for item in fixed_args):
        raise _schema_error(f"{label}.fixed_args must be a string list")
    if scene_style not in (None, "positional", "flag"):
        raise _schema_error(f"{label}.scene_style is invalid")
    return ExecutableSpec(
        package=package,
        executable=executable,
        timeout_s=float(timeout_s),
        fixed_args=tuple(fixed_args),
        scene_style=scene_style,
    )


def load_profile_file(path: Path, expected_backend: str) -> BackendProfile:
    try:
        payload = yaml.safe_load(Path(path).read_text())
    except (OSError, yaml.YAMLError) as error:
        raise ProfileError(f"PROFILE_LOAD_FAILED: {error}") from error
    data = _require_exact_mapping(payload, _PROFILE_FIELDS, "profile")
    if data["backend"] != expected_backend:
        raise ProfileError(
            f"PROFILE_BACKEND_MISMATCH: expected {expected_backend!r}, "
            f"got {data['backend']!r}"
        )
    if data["backend"] not in ("gazebo_cpp", "gazebo_py", "mujoco_py"):
        raise _schema_error("backend is not a fixed ID")
    owner_package = data["owner_package"]
    if not isinstance(owner_package, str) or not owner_package:
        raise _schema_error("owner_package must be a non-empty string")

    capability_data = _require_exact_mapping(
        data["capabilities"], _CAPABILITY_FIELDS, "capabilities"
    )
    if not all(type(value) is bool for value in capability_data.values()):
        raise _schema_error("all capabilities must be booleans")
    capabilities = BackendCapabilities(**capability_data)

    operation_data = data["operations"]
    if not isinstance(operation_data, dict):
        raise _schema_error("operations must be a mapping")
    operations = {}
    for name, value in operation_data.items():
        try:
            operation = BackendOperation(name)
        except ValueError as error:
            raise _schema_error(f"unknown operation {name!r}") from error
        operations[operation] = _parse_spec(value, f"operations.{name}")

    probe = _parse_spec(data["probe"], "probe")
    specs = (probe, *operations.values())
    if any(spec.package != owner_package for spec in specs):
        raise _schema_error("every executable package must equal owner_package")
    return BackendProfile(
        backend=data["backend"],
        owner_package=owner_package,
        probe=probe,
        capabilities=capabilities,
        operations=MappingProxyType(operations),
    )
