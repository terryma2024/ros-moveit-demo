"""Deterministic macOS Gate A control set, direct loader probe and reducer."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ..parallel_batch.resource_identity import canonical_sha256
from .runtime_closure import (
    RuntimeClosureIdentity,
    build_runtime_closure_identity,
    default_loaded_image_probe,
    verify_runtime_closure,
)

CONTROL_SCHEMA_VERSION = 1
_SESSION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_ALL_PHASES = (
    "PLUGIN_RESOLVED",
    "SIMULATION_ENDPOINT_READY",
    "HARDWARE_INITIALIZING",
    "HARDWARE_READY",
    "CONTROLLER_MANAGER_SERVICES_READY",
    "CONTROLLERS_ACTIVE",
)
_SEMANTIC_ENVIRONMENT_KEYS = (
    "AMENT_PREFIX_PATH",
    "CMAKE_PREFIX_PATH",
    "COLCON_PREFIX_PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "PYTHONNOUSERSITE",
    "PYTHONPATH",
    "RMW_IMPLEMENTATION",
    "ROS_DISTRO",
    "ROS_PYTHON_VERSION",
    "ROS_VERSION",
)


class GateAControlError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


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


@dataclass(frozen=True, slots=True)
class FrozenSemanticLaunchContract:
    argv: tuple[str, ...]
    environment: Mapping[str, str]
    vendor_library_directory: Path

    def __post_init__(self) -> None:
        if not self.argv or any(not isinstance(value, str) or not value for value in self.argv):
            raise GateAControlError("CONTROL_SEMANTIC_INVALID", "argv")
        vendor = Path(self.vendor_library_directory)
        if not vendor.is_absolute():
            raise GateAControlError("CONTROL_SEMANTIC_INVALID", str(vendor))
        values = dict(self.environment)
        if any(not isinstance(key, str) or not isinstance(value, str) for key, value in values.items()):
            raise GateAControlError("CONTROL_SEMANTIC_INVALID", "environment")
        object.__setattr__(self, "environment", values)
        object.__setattr__(self, "vendor_library_directory", vendor)

    def as_document(self) -> dict[str, object]:
        return {
            "argv": list(self.argv),
            "environment": dict(sorted(self.environment.items())),
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
    n = dict(negative.environment)
    p = dict(positive.environment)
    if any(key.startswith("DYLD_") for key in n):
        raise GateAControlError("CONTROL_SEMANTIC_DIFF", "negative contains DYLD")
    expected = dict(n)
    expected["DYLD_LIBRARY_PATH"] = str(negative.vendor_library_directory)
    if p != expected:
        raise GateAControlError("CONTROL_SEMANTIC_DIFF", "environment")


@dataclass(frozen=True, slots=True)
class GateAControlSetManifest:
    gate_a_run_root: Path
    closure: RuntimeClosureIdentity
    plugin_relative_path: str
    vendor_relative_path: str
    plugin_xml_relative_path: str
    scene_relative_path: str
    diagnostic_relative_path: str
    semantic: FrozenSemanticLaunchContract
    tool_versions: Mapping[str, str]

    def __post_init__(self) -> None:
        root = Path(self.gate_a_run_root)
        if not root.is_absolute():
            raise GateAControlError("CONTROL_MANIFEST_INVALID", str(root))
        if self.closure.install_root == root or not self.closure.install_root.is_relative_to(root):
            raise GateAControlError(
                "CONTROL_MANIFEST_INVALID",
                "install root must be a strict descendant of the Gate A run root",
            )
        inventory = self.closure.inventory
        for relative in (
            self.plugin_relative_path,
            self.vendor_relative_path,
            self.plugin_xml_relative_path,
            self.scene_relative_path,
            self.diagnostic_relative_path,
        ):
            if relative not in inventory:
                raise GateAControlError("CONTROL_MANIFEST_MISSING", relative)
        aliases = self.closure.dylib_alias_inventory
        if len(aliases) != 1:
            raise GateAControlError("CONTROL_MANIFEST_ALIAS", str(len(aliases)))
        if aliases[0].target_relative_path != self.vendor_relative_path:
            raise GateAControlError("CONTROL_MANIFEST_ALIAS", self.vendor_relative_path)
        object.__setattr__(self, "gate_a_run_root", root)
        object.__setattr__(self, "tool_versions", dict(self.tool_versions))

    @property
    def install_root(self) -> Path:
        return self.closure.install_root

    @property
    def plugin_path(self) -> Path:
        return self.install_root / self.plugin_relative_path

    @property
    def vendor_path(self) -> Path:
        return self.install_root / self.vendor_relative_path

    @property
    def scene_path(self) -> Path:
        return self.install_root / self.scene_relative_path

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.as_document())

    def as_document(self) -> dict[str, object]:
        return {
            "schema_version": CONTROL_SCHEMA_VERSION,
            "gate_a_run_root": str(self.gate_a_run_root),
            "closure": self.closure.as_document(),
            "plugin_relative_path": self.plugin_relative_path,
            "vendor_relative_path": self.vendor_relative_path,
            "plugin_xml_relative_path": self.plugin_xml_relative_path,
            "scene_relative_path": self.scene_relative_path,
            "diagnostic_relative_path": self.diagnostic_relative_path,
            "semantic": self.semantic.as_document(),
            "tool_versions": dict(sorted(self.tool_versions.items())),
        }

    @classmethod
    def from_document(
        cls, document: Mapping[str, object]
    ) -> "GateAControlSetManifest":
        if int(document.get("schema_version", -1)) != CONTROL_SCHEMA_VERSION:
            raise GateAControlError("CONTROL_MANIFEST_SCHEMA")
        tools = document.get("tool_versions")
        if not isinstance(tools, dict):
            raise GateAControlError("CONTROL_MANIFEST_INVALID", "tool_versions")
        return cls(
            gate_a_run_root=Path(str(document["gate_a_run_root"])),
            closure=RuntimeClosureIdentity.from_document(document["closure"]),
            plugin_relative_path=str(document["plugin_relative_path"]),
            vendor_relative_path=str(document["vendor_relative_path"]),
            plugin_xml_relative_path=str(document["plugin_xml_relative_path"]),
            scene_relative_path=str(document["scene_relative_path"]),
            diagnostic_relative_path=str(document["diagnostic_relative_path"]),
            semantic=FrozenSemanticLaunchContract.from_document(document["semantic"]),
            tool_versions={str(key): str(value) for key, value in tools.items()},
        )


def _strict_descendant(path: Path, root: Path, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=False)
    if resolved == root or not resolved.is_relative_to(root):
        raise GateAControlError("CONTROL_BINDING_INVALID", label)
    return resolved


@dataclass(frozen=True, slots=True)
class GateARunBinding:
    control: str
    run_root: Path
    session_id: str
    ros_domain_id: int
    report_path: Path
    task_evidence_root: Path
    ros_home: Path
    ros_log_dir: Path
    tmpdir: Path
    tmp: Path
    temp: Path
    expanded_argv: tuple[str, ...]
    expanded_environment: Mapping[str, str]
    normalized_semantic_sha256: str

    @classmethod
    def create(
        cls,
        *,
        run_root: Path,
        session_id: str,
        ros_domain_id: int,
        control: str = "N",
        manifest: GateAControlSetManifest | None = None,
    ) -> "GateARunBinding":
        root = Path(run_root).resolve(strict=True)
        if control not in {"N", "P", "F"}:
            raise GateAControlError("CONTROL_BINDING_INVALID", control)
        if not _SESSION_PATTERN.fullmatch(session_id):
            raise GateAControlError("CONTROL_BINDING_INVALID", session_id)
        if not isinstance(ros_domain_id, int) or not 0 <= ros_domain_id <= 232:
            raise GateAControlError("CONTROL_BINDING_INVALID", str(ros_domain_id))
        report = _strict_descendant(root / "station-report.json", root, "report")
        evidence = _strict_descendant(root / "evidence", root, "evidence")
        ros_home = _strict_descendant(root / "ros-home", root, "ROS_HOME")
        ros_log = _strict_descendant(ros_home / "log", root, "ROS_LOG_DIR")
        tmpdir = _strict_descendant(root / "tmp", root, "TMPDIR")
        for directory in (evidence, ros_home, ros_log, tmpdir):
            directory.mkdir(parents=True, exist_ok=True)
            if directory.is_symlink() or not directory.is_dir():
                raise GateAControlError("CONTROL_BINDING_INVALID", str(directory))
        if manifest is None:
            expanded_argv: tuple[str, ...] = ()
            environment: dict[str, str] = {
                "ROS_DOMAIN_ID": str(ros_domain_id),
                "ROS_HOME": str(ros_home),
                "ROS_LOG_DIR": str(ros_log),
                "TMPDIR": str(tmpdir),
                "TMP": str(tmpdir),
                "TEMP": str(tmpdir),
            }
            semantic_hash = canonical_sha256({"argv": [], "environment": {}})
        else:
            replacements = {
                "@SESSION_ID@": session_id,
                "@TASK_EVIDENCE_ROOT@": str(evidence),
                "@MANIFEST_SCENE@": str(manifest.scene_path),
            }
            expanded_argv = tuple(
                _replace_tokens(value, replacements) for value in manifest.semantic.argv
            )
            environment = {
                key: value
                for key, value in manifest.semantic.environment.items()
                if not key.startswith("DYLD_")
            }
            if control == "P":
                environment["DYLD_LIBRARY_PATH"] = str(
                    manifest.semantic.vendor_library_directory
                )
            environment.update(
                {
                    "ROS_DOMAIN_ID": str(ros_domain_id),
                    "ROS_HOME": str(ros_home),
                    "ROS_LOG_DIR": str(ros_log),
                    "TMPDIR": str(tmpdir),
                    "TMP": str(tmpdir),
                    "TEMP": str(tmpdir),
                }
            )
            semantic_hash = canonical_sha256(manifest.semantic.as_document())
        return cls(
            control=control,
            run_root=root,
            session_id=session_id,
            ros_domain_id=ros_domain_id,
            report_path=report,
            task_evidence_root=evidence,
            ros_home=ros_home,
            ros_log_dir=ros_log,
            tmpdir=tmpdir,
            tmp=tmpdir,
            temp=tmpdir,
            expanded_argv=expanded_argv,
            expanded_environment=environment,
            normalized_semantic_sha256=semantic_hash,
        )

    def as_document(self) -> dict[str, object]:
        return {
            "schema_version": CONTROL_SCHEMA_VERSION,
            "control": self.control,
            "run_root": str(self.run_root),
            "session_id": self.session_id,
            "ros_domain_id": self.ros_domain_id,
            "report_path": str(self.report_path),
            "task_evidence_root": str(self.task_evidence_root),
            "ROS_HOME": str(self.ros_home),
            "ROS_LOG_DIR": str(self.ros_log_dir),
            "TMPDIR": str(self.tmpdir),
            "TMP": str(self.tmp),
            "TEMP": str(self.temp),
            "expanded_argv": list(self.expanded_argv),
            "expanded_environment": dict(sorted(self.expanded_environment.items())),
            "normalized_semantic_sha256": self.normalized_semantic_sha256,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> "GateARunBinding":
        if int(document.get("schema_version", -1)) != CONTROL_SCHEMA_VERSION:
            raise GateAControlError("CONTROL_BINDING_INVALID", "schema")
        root = Path(str(document["run_root"])).resolve(strict=True)
        paths = {
            "report_path": _strict_descendant(
                Path(str(document["report_path"])), root, "report"
            ),
            "task_evidence_root": _strict_descendant(
                Path(str(document["task_evidence_root"])), root, "evidence"
            ),
            "ros_home": _strict_descendant(
                Path(str(document["ROS_HOME"])), root, "ROS_HOME"
            ),
            "ros_log_dir": _strict_descendant(
                Path(str(document["ROS_LOG_DIR"])), root, "ROS_LOG_DIR"
            ),
            "tmpdir": _strict_descendant(
                Path(str(document["TMPDIR"])), root, "TMPDIR"
            ),
            "tmp": _strict_descendant(Path(str(document["TMP"])), root, "TMP"),
            "temp": _strict_descendant(Path(str(document["TEMP"])), root, "TEMP"),
        }
        if not paths["tmpdir"] == paths["tmp"] == paths["temp"]:
            raise GateAControlError("CONTROL_BINDING_INVALID", "temp mismatch")
        session = str(document["session_id"])
        domain = int(document["ros_domain_id"])
        if not _SESSION_PATTERN.fullmatch(session) or not 0 <= domain <= 232:
            raise GateAControlError("CONTROL_BINDING_INVALID", "session/domain")
        argv = document.get("expanded_argv")
        environment = document.get("expanded_environment")
        if not isinstance(argv, list) or not isinstance(environment, dict):
            raise GateAControlError("CONTROL_BINDING_INVALID", "expanded semantics")
        return cls(
            control=str(document["control"]),
            run_root=root,
            session_id=session,
            ros_domain_id=domain,
            expanded_argv=tuple(str(value) for value in argv),
            expanded_environment={
                str(key): str(value) for key, value in environment.items()
            },
            normalized_semantic_sha256=str(document["normalized_semantic_sha256"]),
            **paths,
        )


def _replace_tokens(value: str, replacements: Mapping[str, str]) -> str:
    expanded = value
    for token, replacement in replacements.items():
        expanded = expanded.replace(token, replacement)
    if "@" in expanded:
        raise GateAControlError("CONTROL_BINDING_INVALID", expanded)
    return expanded


@dataclass(frozen=True, slots=True)
class DirectDlopenObservation:
    markers: tuple[str, ...]
    dlerror: str | None
    plugin_path: Path
    plugin_sha256: str
    vendor_path: Path | None
    vendor_sha256: str | None
    loaded_images: tuple[str, ...]

    @property
    def succeeded(self) -> bool:
        return bool(self.markers and self.markers[-1] == "DLOPEN_SUCCEEDED")

    def as_document(self) -> dict[str, object]:
        return {
            "markers": list(self.markers),
            "dlerror": self.dlerror,
            "plugin_path": str(self.plugin_path),
            "plugin_sha256": self.plugin_sha256,
            "vendor_path": None if self.vendor_path is None else str(self.vendor_path),
            "vendor_sha256": self.vendor_sha256,
            "loaded_images": list(self.loaded_images),
        }

    @classmethod
    def from_document(
        cls, document: Mapping[str, object]
    ) -> "DirectDlopenObservation":
        return cls(
            markers=tuple(str(value) for value in document["markers"]),
            dlerror=(None if document.get("dlerror") is None else str(document["dlerror"])),
            plugin_path=Path(str(document["plugin_path"])),
            plugin_sha256=str(document["plugin_sha256"]),
            vendor_path=(
                None if document.get("vendor_path") is None else Path(str(document["vendor_path"]))
            ),
            vendor_sha256=(
                None if document.get("vendor_sha256") is None else str(document["vendor_sha256"])
            ),
            loaded_images=tuple(str(value) for value in document.get("loaded_images", [])),
        )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_direct_dlopen(
    plugin: Path, vendor: Path | None = None
) -> DirectDlopenObservation:
    plugin_path = Path(plugin).resolve(strict=True)
    vendor_path = None if vendor is None else Path(vendor).resolve(strict=True)
    markers = ["DLOPEN_STARTED"]
    try:
        ctypes.CDLL(
            str(plugin_path),
            mode=getattr(os, "RTLD_NOW", 2) | getattr(os, "RTLD_LOCAL", 0),
        )
        markers.append("DLOPEN_SUCCEEDED")
        error = None
        try:
            images = tuple(str(path) for path in default_loaded_image_probe(os.getpid()))
        except Exception:
            images = ()
    except OSError as load_error:
        markers.append("DLOPEN_FAILED")
        error = str(load_error)
        images = ()
    return DirectDlopenObservation(
        markers=tuple(markers),
        dlerror=error,
        plugin_path=plugin_path,
        plugin_sha256=_sha256_file(plugin_path),
        vendor_path=vendor_path,
        vendor_sha256=None if vendor_path is None else _sha256_file(vendor_path),
        loaded_images=images,
    )


@dataclass(frozen=True, slots=True)
class GateAControlObservation:
    invariants_valid: bool
    collector_healthy: bool
    process_identity_stable: bool
    controller_role_attested: bool
    controller_executable_attested: bool
    dlopen_marker: str | None
    loader_error: str | None
    exact_vendor_missing: bool
    plugin_image_attested: bool
    vendor_image_attested: bool
    ros_instance_markers: tuple[str, ...]
    ready: bool
    first_bad_phase: str | None
    timed_out: bool
    cleanup_complete: bool
    invalid_reasons: tuple[str, ...]

    def as_document(self) -> dict[str, object]:
        return {
            "invariants_valid": self.invariants_valid,
            "collector_healthy": self.collector_healthy,
            "process_identity_stable": self.process_identity_stable,
            "controller_role_attested": self.controller_role_attested,
            "controller_executable_attested": self.controller_executable_attested,
            "dlopen_marker": self.dlopen_marker,
            "loader_error": self.loader_error,
            "exact_vendor_missing": self.exact_vendor_missing,
            "plugin_image_attested": self.plugin_image_attested,
            "vendor_image_attested": self.vendor_image_attested,
            "ros_instance_markers": list(self.ros_instance_markers),
            "ready": self.ready,
            "first_bad_phase": self.first_bad_phase,
            "timed_out": self.timed_out,
            "cleanup_complete": self.cleanup_complete,
            "invalid_reasons": list(self.invalid_reasons),
        }

    @classmethod
    def from_document(
        cls, document: Mapping[str, object]
    ) -> "GateAControlObservation":
        return cls(
            invariants_valid=bool(document["invariants_valid"]),
            collector_healthy=bool(document["collector_healthy"]),
            process_identity_stable=bool(document["process_identity_stable"]),
            controller_role_attested=bool(document["controller_role_attested"]),
            controller_executable_attested=bool(document["controller_executable_attested"]),
            dlopen_marker=(
                None if document.get("dlopen_marker") is None else str(document["dlopen_marker"])
            ),
            loader_error=(
                None if document.get("loader_error") is None else str(document["loader_error"])
            ),
            exact_vendor_missing=bool(document["exact_vendor_missing"]),
            plugin_image_attested=bool(document["plugin_image_attested"]),
            vendor_image_attested=bool(document["vendor_image_attested"]),
            ros_instance_markers=tuple(str(value) for value in document["ros_instance_markers"]),
            ready=bool(document["ready"]),
            first_bad_phase=(
                None if document.get("first_bad_phase") is None else str(document["first_bad_phase"])
            ),
            timed_out=bool(document["timed_out"]),
            cleanup_complete=bool(document["cleanup_complete"]),
            invalid_reasons=tuple(str(value) for value in document["invalid_reasons"]),
        )

    @property
    def observation_class(self) -> ObservationClass:
        invariants = (
            self.invariants_valid
            and self.collector_healthy
            and self.process_identity_stable
            and self.controller_role_attested
            and self.controller_executable_attested
            and not self.timed_out
            and self.cleanup_complete
            and not self.invalid_reasons
            and self.dlopen_marker in {"DLOPEN_SUCCEEDED", "DLOPEN_FAILED"}
        )
        if not invariants:
            return ObservationClass.INVALID
        if (
            self.dlopen_marker == "DLOPEN_FAILED"
            and self.exact_vendor_missing
            and bool(self.loader_error)
            and not self.ros_instance_markers
            and not self.ready
        ):
            return ObservationClass.MISSING_VENDOR_BEFORE_ROS_PLUGIN_INSTANCE_INIT
        if (
            self.dlopen_marker == "DLOPEN_SUCCEEDED"
            and self.plugin_image_attested
            and self.vendor_image_attested
            and self.ros_instance_markers == _ALL_PHASES
            and self.ready
            and self.first_bad_phase is None
        ):
            return ObservationClass.PASS
        if (
            self.dlopen_marker == "DLOPEN_SUCCEEDED"
            and self.plugin_image_attested
            and self.vendor_image_attested
            and bool(self.first_bad_phase)
            and not self.ready
        ):
            return ObservationClass.NON_RPATH_FAILURE
        return ObservationClass.INVALID


@dataclass(frozen=True, slots=True)
class GateADecision:
    current: CurrentBoundaryVerdict
    controller: ControllerVerdict
    negative_class: ObservationClass
    positive_class: ObservationClass
    reason: str

    def as_document(self) -> dict[str, str]:
        return {
            "current_boundary_verdict": self.current.value,
            "controller_verdict": self.controller.value,
            "negative_class": self.negative_class.value,
            "positive_class": self.positive_class.value,
            "reason": self.reason,
        }


def reduce_gate_a_controls(
    negative: GateAControlObservation,
    positive: GateAControlObservation,
) -> GateADecision:
    n = negative.observation_class
    p = positive.observation_class
    if n is ObservationClass.INVALID or p is ObservationClass.INVALID:
        return GateADecision(
            CurrentBoundaryVerdict.INVALID_CONTROL,
            ControllerVerdict.NOT_EXCLUDED,
            n,
            p,
            "one or both controls violate required invariants",
        )
    if (
        n is ObservationClass.MISSING_VENDOR_BEFORE_ROS_PLUGIN_INSTANCE_INIT
        and p is ObservationClass.PASS
    ):
        return GateADecision(
            CurrentBoundaryVerdict.CONFIRMED_RPATH,
            ControllerVerdict.EXCLUDED_BEFORE_ROS_PLUGIN_INSTANCE_INIT,
            n,
            p,
            "P removes the exact manifest vendor loader failure",
        )
    if n is ObservationClass.PASS and p is ObservationClass.PASS:
        return GateADecision(
            CurrentBoundaryVerdict.CURRENT_CLOSURE_ALREADY_VALID,
            ControllerVerdict.CURRENT_CONTROLLER_PATH_OPERATIONAL,
            n,
            p,
            "the no-DYLD current closure already passes",
        )
    if n is ObservationClass.NON_RPATH_FAILURE and p in {
        ObservationClass.PASS,
        ObservationClass.NON_RPATH_FAILURE,
    }:
        return GateADecision(
            CurrentBoundaryVerdict.CURRENT_NON_RPATH_FAILURE,
            ControllerVerdict.NOT_EXCLUDED,
            n,
            p,
            f"negative first bad ROS phase: {negative.first_bad_phase}",
        )
    if (
        n is ObservationClass.MISSING_VENDOR_BEFORE_ROS_PLUGIN_INSTANCE_INIT
        and p is ObservationClass.NON_RPATH_FAILURE
    ):
        return GateADecision(
            CurrentBoundaryVerdict.CURRENT_NON_RPATH_FAILURE,
            ControllerVerdict.NOT_EXCLUDED,
            n,
            p,
            f"positive first bad ROS phase: {positive.first_bad_phase}",
        )
    return GateADecision(
        CurrentBoundaryVerdict.INVALID_CONTROL,
        ControllerVerdict.NOT_EXCLUDED,
        n,
        p,
        "control pair is not in the reviewed decision matrix",
    )


def build_control_set_manifest(
    *,
    gate_a_run_root: Path,
    install_root: Path,
    source_commit: str,
    submodule_commit: str,
    environment: Mapping[str, str],
) -> GateAControlSetManifest:
    base_environment = {
        key: value
        for key in _SEMANTIC_ENVIRONMENT_KEYS
        if isinstance((value := environment.get(key)), str)
    }
    base_environment["PYTHONNOUSERSITE"] = "1"
    if any(key.startswith("DYLD_") for key in base_environment):
        raise GateAControlError("CONTROL_SEMANTIC_INVALID", "DYLD in base")
    closure = build_runtime_closure_identity(
        install_root=install_root,
        source_commit=source_commit,
        mujoco_ros2_control_commit=submodule_commit,
        environment=base_environment,
    )
    semantic = FrozenSemanticLaunchContract(
        argv=(
            "ros2",
            "launch",
            "so101_demo_py",
            "so101_mujoco_task_station.launch.py",
            "headless:=false",
            "sensor_rendering:=true",
            "include_teleop:=false",
            "session_id:=@SESSION_ID@",
            "task_evidence_root:=@TASK_EVIDENCE_ROOT@",
            "readiness_timeout_s:=90.0",
            "mujoco_scene:=@MANIFEST_SCENE@",
            "mujoco_initial_keyframe:=task_start",
        ),
        environment=base_environment,
        vendor_library_directory=closure.install_root / "opt/mujoco_vendor/lib",
    )
    return GateAControlSetManifest(
        gate_a_run_root=Path(gate_a_run_root).resolve(strict=True),
        closure=closure,
        plugin_relative_path="lib/libmujoco_ros2_control.dylib",
        vendor_relative_path="opt/mujoco_vendor/lib/libmujoco.3.4.0.dylib",
        plugin_xml_relative_path=(
            "share/mujoco_ros2_control/mujoco_system_interface_plugin.xml"
        ),
        scene_relative_path="share/so101_demo_py/assets/mujoco/scene.xml",
        diagnostic_relative_path=(
            "lib/so101_demo_py/so101_diagnose_macos_station"
        ),
        semantic=semantic,
        tool_versions={
            "python": sys.version.split()[0],
            "platform": sys.platform,
        },
    )


def write_json(path: Path, document: Mapping[str, object]) -> None:
    target = Path(path)
    if not target.is_absolute() or target.is_symlink():
        raise GateAControlError("CONTROL_OUTPUT_INVALID", str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{secrets.token_hex(8)}.tmp")
    payload = json.dumps(document, sort_keys=True, indent=2) + "\n"
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)
    directory = os.open(target.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def load_manifest(path: Path) -> GateAControlSetManifest:
    return GateAControlSetManifest.from_document(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )


def load_binding(path: Path) -> GateARunBinding:
    return GateARunBinding.from_document(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )


def _next_domain(run_root: Path, session_id: str) -> int:
    used: set[int] = set()
    for path in run_root.parent.rglob("run-binding.json"):
        try:
            used.add(int(json.loads(path.read_text(encoding="utf-8"))["ros_domain_id"]))
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
    start = int(hashlib.sha256(session_id.encode()).hexdigest()[:8], 16) % 233
    for offset in range(233):
        candidate = (start + offset) % 233
        if candidate not in used:
            return candidate
    raise GateAControlError("CONTROL_BINDING_INVALID", "no free ROS domain")


def _execute_probe_child(
    manifest: GateAControlSetManifest, binding: GateARunBinding
) -> DirectDlopenObservation:
    verify_runtime_closure(
        manifest.closure,
        install_root=manifest.install_root,
        source_commit=manifest.closure.source_commit,
        mujoco_ros2_control_commit=manifest.closure.mujoco_ros2_control_commit,
        environment=manifest.semantic.environment,
    )
    command = (
        sys.executable,
        "-m",
        "so101_demo.runtime.macos_dlopen_probe",
        "--child-dlopen",
        "--plugin",
        str(manifest.plugin_path),
        "--vendor",
        str(manifest.vendor_path),
    )
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=dict(binding.expanded_environment),
        timeout=30.0,
    )
    candidates = [line for line in completed.stdout.splitlines() if line.startswith("{")]
    if not candidates:
        raise GateAControlError(
            "DLOPEN_CHILD_INVALID",
            f"rc={completed.returncode} stderr={completed.stderr.strip()}",
        )
    observation = DirectDlopenObservation.from_document(json.loads(candidates[-1]))
    if completed.returncode not in {0, 1}:
        raise GateAControlError("DLOPEN_CHILD_INVALID", str(completed.returncode))
    return observation


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="macos_dlopen_probe")
    parser.add_argument("--create-manifest", action="store_true")
    parser.add_argument("--create-run-binding", action="store_true")
    parser.add_argument("--child-dlopen", action="store_true")
    parser.add_argument("--reduce-controls", action="store_true")
    parser.add_argument("--manifest")
    parser.add_argument("--run-binding")
    parser.add_argument("--control", choices=("N", "P", "F"))
    parser.add_argument("--run-root")
    parser.add_argument("--session-id")
    parser.add_argument("--ros-domain-id", type=int)
    parser.add_argument("--install-root")
    parser.add_argument("--gate-a-run-root")
    parser.add_argument("--source-commit")
    parser.add_argument("--submodule-commit")
    parser.add_argument("--plugin")
    parser.add_argument("--vendor")
    parser.add_argument("--negative")
    parser.add_argument("--positive")
    parser.add_argument("--output")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> int:
    options = parse_arguments(argv)
    if options.child_dlopen:
        if not options.plugin:
            raise GateAControlError("DLOPEN_CHILD_INVALID", "plugin")
        observation = run_direct_dlopen(
            Path(options.plugin), None if not options.vendor else Path(options.vendor)
        )
        print(json.dumps(observation.as_document(), sort_keys=True), flush=True)
        return 0 if observation.succeeded else 1
    if options.create_manifest:
        required = (
            options.gate_a_run_root,
            options.install_root,
            options.source_commit,
            options.submodule_commit,
            options.output,
        )
        if not all(required):
            raise GateAControlError("CONTROL_MANIFEST_INVALID", "arguments")
        manifest = build_control_set_manifest(
            gate_a_run_root=Path(options.gate_a_run_root),
            install_root=Path(options.install_root),
            source_commit=options.source_commit,
            submodule_commit=options.submodule_commit,
            environment=os.environ,
        )
        write_json(Path(options.output), manifest.as_document())
        return 0
    if options.create_run_binding:
        if not all((options.manifest, options.control, options.run_root, options.session_id, options.output)):
            raise GateAControlError("CONTROL_BINDING_INVALID", "arguments")
        manifest = load_manifest(Path(options.manifest))
        run_root = Path(options.run_root)
        run_root.mkdir(parents=True, exist_ok=False)
        domain = (
            options.ros_domain_id
            if options.ros_domain_id is not None
            else _next_domain(run_root, options.session_id)
        )
        binding = GateARunBinding.create(
            run_root=run_root,
            session_id=options.session_id,
            ros_domain_id=domain,
            control=options.control,
            manifest=manifest,
        )
        write_json(Path(options.output), binding.as_document())
        return 0
    if options.reduce_controls:
        if not all((options.negative, options.positive, options.output)):
            raise GateAControlError("CONTROL_REDUCER_INVALID", "arguments")
        negative = GateAControlObservation.from_document(
            json.loads(Path(options.negative).read_text(encoding="utf-8"))
        )
        positive = GateAControlObservation.from_document(
            json.loads(Path(options.positive).read_text(encoding="utf-8"))
        )
        write_json(
            Path(options.output), reduce_gate_a_controls(negative, positive).as_document()
        )
        return 0
    if not all((options.manifest, options.run_binding, options.control, options.output)):
        raise GateAControlError("DLOPEN_CONTROL_INVALID", "arguments")
    manifest = load_manifest(Path(options.manifest))
    binding = load_binding(Path(options.run_binding))
    if binding.control != options.control:
        raise GateAControlError("DLOPEN_CONTROL_INVALID", "binding control mismatch")
    observation = _execute_probe_child(manifest, binding)
    write_json(Path(options.output), observation.as_document())
    return 0 if observation.succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
