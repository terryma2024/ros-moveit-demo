"""Strict loading for complete backend-specific policy variants."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from .policy import TaskPolicy, load_task_policy

_MANIFEST_KEYS = frozenset({"schema_version", "policy_id", "version", "variants"})
_VARIANT_KEYS = frozenset(
    {"backend", "filename", "policy_sha256", "qualification_status"}
)
_BACKENDS = frozenset({"mujoco", "gazebo", "real_stub"})


class PolicyValidationError(ValueError):
    """A policy variant or its registry metadata is not canonical."""


@dataclass(frozen=True, slots=True)
class LoadedPolicy:
    policy_id: str
    version: str
    backend: str
    path: Path
    policy: TaskPolicy | None
    policy_sha256: str
    qualification_status: str
    configuration: Mapping[str, object]


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PolicyValidationError(f"{name} must be a mapping")
    return value


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], name: str) -> None:
    if frozenset(value) != expected:
        raise PolicyValidationError(f"{name} fields must be exactly {sorted(expected)}")


def _nonempty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise PolicyValidationError(f"{name} must be a non-empty string")
    return value


def _load_real_stub(path: Path, policy_id: str) -> Mapping[str, object]:
    document = _mapping(yaml.safe_load(path.read_bytes()), "real_stub policy")
    _exact_keys(
        document,
        frozenset(
            {
                "schema_version",
                "policy_id",
                "backend",
                "execution_allowed",
                "readiness_error_code",
                "safety",
            }
        ),
        "real_stub policy",
    )
    safety = _mapping(document["safety"], "real_stub safety")
    _exact_keys(
        safety,
        frozenset({"device_access_allowed", "ros_control_io_allowed"}),
        "real_stub safety",
    )
    if document["schema_version"] != 1 or document["policy_id"] != policy_id:
        raise PolicyValidationError("real_stub identity mismatch")
    if document["backend"] != "real_stub":
        raise PolicyValidationError("real_stub backend mismatch")
    if document["execution_allowed"] is not False:
        raise PolicyValidationError("real_stub execution must be disabled")
    if safety["device_access_allowed"] is not False or safety["ros_control_io_allowed"] is not False:
        raise PolicyValidationError("real_stub I/O must be disabled")
    if document["readiness_error_code"] != "REAL_HARDWARE_NOT_CONFIGURED":
        raise PolicyValidationError("real_stub readiness error is not fail closed")
    return MappingProxyType(dict(document))


def load_policy_variant(
    policy_id: str,
    version: str,
    backend: str,
    share_dir: Path,
) -> LoadedPolicy:
    """Load exactly one named variant; missing or mismatched variants never fall back."""

    if backend not in _BACKENDS:
        raise PolicyValidationError(f"unsupported backend: {backend}")
    root = Path(share_dir) / "config" / "policies" / policy_id / version
    manifest_path = root / "manifest.yaml"
    try:
        manifest = _mapping(yaml.safe_load(manifest_path.read_bytes()), "policy manifest")
    except (OSError, yaml.YAMLError) as error:
        raise PolicyValidationError(f"cannot load policy manifest: {error}") from error
    _exact_keys(manifest, _MANIFEST_KEYS, "policy manifest")
    if manifest["schema_version"] != 1:
        raise PolicyValidationError("policy manifest schema_version must be 1")
    if manifest["policy_id"] != policy_id or manifest["version"] != version:
        raise PolicyValidationError("policy manifest identity mismatch")
    variants = _mapping(manifest["variants"], "policy variants")
    if frozenset(variants) != _BACKENDS:
        raise PolicyValidationError("policy manifest must define every backend explicitly")
    entry = _mapping(variants[backend], f"{backend} variant")
    _exact_keys(entry, _VARIANT_KEYS, f"{backend} variant")
    if entry["backend"] != backend:
        raise PolicyValidationError("variant backend mismatch")
    filename = _nonempty_string(entry["filename"], "variant filename")
    if Path(filename).name != filename:
        raise PolicyValidationError("variant filename must not escape its version directory")
    path = root / filename
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise PolicyValidationError(f"cannot load {backend} variant: {error}") from error
    policy_sha256 = hashlib.sha256(raw).hexdigest()
    if entry["policy_sha256"] != policy_sha256:
        raise PolicyValidationError("variant policy hash mismatch")
    qualification_status = _nonempty_string(
        entry["qualification_status"], "qualification status"
    )
    if backend == "real_stub":
        policy = None
        configuration = _load_real_stub(path, policy_id)
    else:
        try:
            policy = load_task_policy(path)
        except (OSError, TypeError, ValueError, yaml.YAMLError) as error:
            raise PolicyValidationError(f"invalid {backend} policy: {error}") from error
        configuration = MappingProxyType({})
    return LoadedPolicy(
        policy_id=policy_id,
        version=version,
        backend=backend,
        path=path,
        policy=policy,
        policy_sha256=policy_sha256,
        qualification_status=qualification_status,
        configuration=configuration,
    )
