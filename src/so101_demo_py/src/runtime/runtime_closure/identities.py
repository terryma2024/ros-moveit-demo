"""Closure constants and the digest, alias, closure, run binding and attestation records."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from so101_demo.parallel_batch.canonical_json import canonical_sha256

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle with task_stack
    from so101_demo.runtime.task_stack import OwnedProcessIdentity


CLOSURE_SCHEMA_VERSION = 2


CONTROLLER_RUNTIME_ROLE = "controller_runtime"


MUJOCO_DYLIB_ALIAS_RELATIVE_PATH = "opt/mujoco_vendor/lib/libmujoco.dylib"


MUJOCO_DYLIB_ALIAS_LINK_TEXT = "libmujoco.3.4.0.dylib"


LIBRARY_MARKERS = (".dylib", ".so")


CONFIG_SUFFIXES = frozenset(
    {".yaml", ".yml", ".json", ".xml", ".srdf", ".urdf", ".xacro", ".sdf"}
)


SKIPPED_DIRECTORY_NAMES = frozenset({"__pycache__"})


# Closed allowlist of environment constraints that belong to the runtime identity. The
# volatile placement variables (ROS_DOMAIN_ID, GZ_PARTITION, ROS_HOME, ROS_LOG_DIR,
# TMPDIR/TMP/TEMP, PWD, SHLVL, ...) are intentionally not part of it.
CLOSURE_ENVIRONMENT_KEYS: tuple[str, ...] = (
    "AMENT_PREFIX_PATH",
    "DYLD_FALLBACK_LIBRARY_PATH",
    "DYLD_LIBRARY_PATH",
    "LD_LIBRARY_PATH",
    "MKL_NUM_THREADS",
    "MUJOCO_GL",
    "OMP_NUM_THREADS",
    "PATH",
    "PYTHONNOUSERSITE",
    "PYTHONPATH",
    "PYTORCH_ENABLE_MPS_FALLBACK",
)


# Test seam: called with each file path after its bytes were read and before the
# replacement re-check. Production code leaves it None.
_READ_HOOK: Callable[[Path], None] | None = None


class RuntimeClosureError(RuntimeError):
    """Fail-closed runtime closure error carrying a stable machine-readable code."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True, slots=True)
class FileDigest:
    """One installed file, addressed by its canonical relative path inside the prefix."""

    relative_path: str
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        if not isinstance(self.relative_path, str) or not self.relative_path:
            raise RuntimeClosureError("FILE_DIGEST_PATH", "relative path is required")
        path = Path(self.relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise RuntimeClosureError(
                "FILE_DIGEST_PATH", f"not a canonical relative path: {self.relative_path}"
            )
        if len(self.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise RuntimeClosureError("FILE_DIGEST_SHA256", self.relative_path)
        if self.size_bytes < 0:
            raise RuntimeClosureError("FILE_DIGEST_SIZE", self.relative_path)

    def as_document(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> "FileDigest":
        return cls(
            relative_path=str(document["relative_path"]),
            sha256=str(document["sha256"]),
            size_bytes=int(document["size_bytes"]),
        )


@dataclass(frozen=True, slots=True)
class DylibAliasIdentity:
    """The one closed, installer-produced MuJoCo dylib alias."""

    relative_path: str
    link_text: str
    target_relative_path: str
    target_sha256: str

    def __post_init__(self) -> None:
        if self.relative_path != MUJOCO_DYLIB_ALIAS_RELATIVE_PATH:
            raise RuntimeClosureError("CLOSURE_SYMLINK", self.relative_path)
        if self.link_text != MUJOCO_DYLIB_ALIAS_LINK_TEXT:
            raise RuntimeClosureError("CLOSURE_SYMLINK", self.link_text)
        link = Path(self.link_text)
        if link.is_absolute() or len(link.parts) != 1 or self.link_text in {".", ".."}:
            raise RuntimeClosureError("CLOSURE_SYMLINK", self.link_text)
        expected_target = (
            Path(self.relative_path).parent / self.link_text
        ).as_posix()
        if self.target_relative_path != expected_target:
            raise RuntimeClosureError("CLOSURE_SYMLINK", self.target_relative_path)
        _require_sha256("dylib_alias_target_sha256", self.target_sha256)

    def as_document(self) -> dict[str, str]:
        return {
            "relative_path": self.relative_path,
            "link_text": self.link_text,
            "target_relative_path": self.target_relative_path,
            "target_sha256": self.target_sha256,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> "DylibAliasIdentity":
        return cls(
            relative_path=str(document["relative_path"]),
            link_text=str(document["link_text"]),
            target_relative_path=str(document["target_relative_path"]),
            target_sha256=str(document["target_sha256"]),
        )


def _require_commit(name: str, value: object, *, missing_code: str) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeClosureError(missing_code, f"{name} is required")
    if len(value) not in (40, 64) or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise RuntimeClosureError(f"{name.upper()}_INVALID", value)
    return value


def _require_sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise RuntimeClosureError(f"{name.upper()}_INVALID", str(value))
    return value


def _inventory_document(entries: Sequence[FileDigest]) -> list[dict[str, object]]:
    return [entry.as_document() for entry in sorted(entries, key=lambda item: item.relative_path)]


@dataclass(frozen=True, slots=True)
class RuntimeClosureIdentity:
    """The identity that must be equal across every restart of the station."""

    install_root: Path
    source_commit: str
    mujoco_ros2_control_commit: str
    install_inventory_sha256: str
    executable_inventory: tuple[FileDigest, ...]
    library_inventory: tuple[FileDigest, ...]
    config_inventory: tuple[FileDigest, ...]
    dylib_alias_inventory: tuple[DylibAliasIdentity, ...]
    normalized_environment_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.install_root, Path) or not self.install_root.is_absolute():
            raise RuntimeClosureError(
                "CLOSURE_INSTALL_ROOT_INVALID", str(self.install_root)
            )
        _require_commit(
            "source_commit", self.source_commit, missing_code="CLOSURE_SOURCE_COMMIT_MISSING"
        )
        _require_commit(
            "mujoco_ros2_control_commit",
            self.mujoco_ros2_control_commit,
            missing_code="CLOSURE_SUBMODULE_COMMIT_MISSING",
        )
        _require_sha256("install_inventory_sha256", self.install_inventory_sha256)
        _require_sha256("normalized_environment_sha256", self.normalized_environment_sha256)
        for name in ("executable_inventory", "library_inventory", "config_inventory"):
            entries = getattr(self, name)
            if not isinstance(entries, tuple) or any(
                not isinstance(entry, FileDigest) for entry in entries
            ):
                raise RuntimeClosureError(f"CLOSURE_{name.upper()}_INVALID", name)
        if not isinstance(self.dylib_alias_inventory, tuple) or any(
            not isinstance(entry, DylibAliasIdentity)
            for entry in self.dylib_alias_inventory
        ):
            raise RuntimeClosureError("CLOSURE_DYLIB_ALIAS_INVENTORY_INVALID")

    def as_document(self) -> dict[str, object]:
        return {
            "schema_version": CLOSURE_SCHEMA_VERSION,
            "install_root": str(self.install_root),
            "source_commit": self.source_commit,
            "mujoco_ros2_control_commit": self.mujoco_ros2_control_commit,
            "install_inventory_sha256": self.install_inventory_sha256,
            "executable_inventory": _inventory_document(self.executable_inventory),
            "library_inventory": _inventory_document(self.library_inventory),
            "config_inventory": _inventory_document(self.config_inventory),
            "dylib_alias_inventory": [
                entry.as_document()
                for entry in sorted(
                    self.dylib_alias_inventory,
                    key=lambda item: item.relative_path,
                )
            ],
            "normalized_environment_sha256": self.normalized_environment_sha256,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> "RuntimeClosureIdentity":
        if int(document.get("schema_version", -1)) != CLOSURE_SCHEMA_VERSION:
            raise RuntimeClosureError(
                "CLOSURE_SCHEMA_VERSION", str(document.get("schema_version"))
            )

        def inventory(name: str) -> tuple[FileDigest, ...]:
            raw = document.get(name)
            if not isinstance(raw, list):
                raise RuntimeClosureError(f"CLOSURE_{name.upper()}_INVALID")
            return tuple(FileDigest.from_document(item) for item in raw)

        raw_aliases = document.get("dylib_alias_inventory")
        if not isinstance(raw_aliases, list):
            raise RuntimeClosureError("CLOSURE_DYLIB_ALIAS_INVENTORY_INVALID")
        return cls(
            install_root=Path(str(document["install_root"])),
            source_commit=str(document["source_commit"]),
            mujoco_ros2_control_commit=str(document["mujoco_ros2_control_commit"]),
            install_inventory_sha256=str(document["install_inventory_sha256"]),
            executable_inventory=inventory("executable_inventory"),
            library_inventory=inventory("library_inventory"),
            config_inventory=inventory("config_inventory"),
            dylib_alias_inventory=tuple(
                DylibAliasIdentity.from_document(item) for item in raw_aliases
            ),
            normalized_environment_sha256=str(
                document["normalized_environment_sha256"]
            ),
        )

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.as_document())

    @property
    def inventory(self) -> dict[str, FileDigest]:
        """Every typed entry keyed by relative path, for attestation lookups."""

        return {
            entry.relative_path: entry
            for entry in (
                self.executable_inventory + self.library_inventory + self.config_inventory
            )
        }


@dataclass(frozen=True, slots=True)
class RunBinding:
    """Fresh facts bound to exactly one run; two runs never share a binding."""

    campaign_id: str
    batch_id: str
    ros_domain_id: int
    station_session_id: str
    evidence_root: Path
    owner_generation: int
    started_monotonic_ns: int

    def __post_init__(self) -> None:
        for name in ("campaign_id", "batch_id", "station_session_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise RuntimeClosureError(f"RUN_BINDING_{name.upper()}", "is required")
        if not isinstance(self.ros_domain_id, int) or self.ros_domain_id < 0:
            raise RuntimeClosureError("RUN_BINDING_ROS_DOMAIN_ID", str(self.ros_domain_id))
        if not isinstance(self.evidence_root, Path) or not self.evidence_root.is_absolute():
            raise RuntimeClosureError("RUN_BINDING_EVIDENCE_ROOT", str(self.evidence_root))
        if not isinstance(self.owner_generation, int) or self.owner_generation < 1:
            raise RuntimeClosureError("RUN_BINDING_OWNER_GENERATION", str(self.owner_generation))
        if not isinstance(self.started_monotonic_ns, int) or self.started_monotonic_ns <= 0:
            raise RuntimeClosureError("RUN_BINDING_STARTED_MONOTONIC_NS", str(self.started_monotonic_ns))

    def as_document(self) -> dict[str, object]:
        return {
            "schema_version": CLOSURE_SCHEMA_VERSION,
            "campaign_id": self.campaign_id,
            "batch_id": self.batch_id,
            "ros_domain_id": self.ros_domain_id,
            "station_session_id": self.station_session_id,
            "evidence_root": str(self.evidence_root),
            "owner_generation": self.owner_generation,
            "started_monotonic_ns": self.started_monotonic_ns,
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.as_document())


@dataclass(frozen=True, slots=True)
class RuntimeAttestation:
    """Post-spawn read-back: what identity and images the running children really have."""

    closure_sha256: str
    run_binding_sha256: str
    process_identities: tuple["OwnedProcessIdentity", ...]
    loaded_images: tuple[FileDigest, ...]
    observed_ros_domain_id: int

    def __post_init__(self) -> None:
        _require_sha256("closure_sha256", self.closure_sha256)
        _require_sha256("run_binding_sha256", self.run_binding_sha256)
        if not self.process_identities:
            raise RuntimeClosureError(
                "ATTESTATION_PROCESS_IDENTITIES", "at least one process identity is required"
            )
        if not isinstance(self.observed_ros_domain_id, int) or self.observed_ros_domain_id < 0:
            raise RuntimeClosureError(
                "ATTESTATION_ROS_DOMAIN", str(self.observed_ros_domain_id)
            )

    def as_document(self) -> dict[str, object]:
        return {
            "schema_version": CLOSURE_SCHEMA_VERSION,
            "closure_sha256": self.closure_sha256,
            "run_binding_sha256": self.run_binding_sha256,
            "process_identities": [
                {
                    "role": identity.role,
                    "pid": identity.pid,
                    "pgid": identity.pgid,
                    "cmdline": list(identity.cmdline),
                    "start_time_ticks": identity.start_time_ticks,
                }
                for identity in self.process_identities
            ],
            "loaded_images": _inventory_document(self.loaded_images),
            "observed_ros_domain_id": self.observed_ros_domain_id,
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.as_document())


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    """One process on the owner tree: its role, PID/birth pair and the parent that spawned it.

    The role is written when the spawn intent is recorded, never inferred from a loaded
    image list after the fact.
    """

    role: str
    pid: int
    parent_pid: int
    birth_identity: int
    executable: str

    def as_document(self) -> dict[str, object]:
        return {
            "role": self.role,
            "pid": self.pid,
            "parent_pid": self.parent_pid,
            "birth_identity": self.birth_identity,
            "executable": self.executable,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> "ProcessIdentity":
        return cls(
            role=str(document["role"]),
            pid=int(document["pid"]),  # type: ignore[arg-type]
            parent_pid=int(document["parent_pid"]),  # type: ignore[arg-type]
            birth_identity=int(document["birth_identity"]),  # type: ignore[arg-type]
            executable=str(document["executable"]),
        )


@dataclass(frozen=True, slots=True)
class ControllerRuntimeOwnerBinding:
    """The owner tree a spawn intent recorded before the controller process existed.

    ``closure_prefixes`` and ``dylib_farm_root`` come from the round's frozen contract, so an
    attestation can be re-validated without re-reading the manifest.
    """

    owner_root_role: str
    owner_root_pid: int
    owner_root_birth_identity: int
    spawn_role: str
    expected_executable_relative_path: str
    ancestry: tuple[ProcessIdentity, ...]
    manifest_sha256: str
    closure_prefixes: tuple[str, ...]
    dylib_farm_root: str

    def as_document(self) -> dict[str, object]:
        return {
            "owner_root_role": self.owner_root_role,
            "owner_root_pid": self.owner_root_pid,
            "owner_root_birth_identity": self.owner_root_birth_identity,
            "spawn_role": self.spawn_role,
            "expected_executable_relative_path": self.expected_executable_relative_path,
            "ancestry": [identity.as_document() for identity in self.ancestry],
            "manifest_sha256": self.manifest_sha256,
            "closure_prefixes": list(self.closure_prefixes),
            "dylib_farm_root": self.dylib_farm_root,
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.as_document())

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> "ControllerRuntimeOwnerBinding":
        return cls(
            owner_root_role=str(document["owner_root_role"]),
            owner_root_pid=int(document["owner_root_pid"]),  # type: ignore[arg-type]
            owner_root_birth_identity=int(  # type: ignore[arg-type]
                document["owner_root_birth_identity"]
            ),
            spawn_role=str(document["spawn_role"]),
            expected_executable_relative_path=str(
                document["expected_executable_relative_path"]
            ),
            ancestry=tuple(
                ProcessIdentity.from_document(entry)
                for entry in document["ancestry"]  # type: ignore[union-attr]
            ),
            manifest_sha256=str(document["manifest_sha256"]),
            closure_prefixes=tuple(
                str(prefix)
                for prefix in document["closure_prefixes"]  # type: ignore[union-attr]
            ),
            dylib_farm_root=str(document["dylib_farm_root"]),
        )


@dataclass(frozen=True, slots=True)
class RuntimeProcessAttestation:
    """Per-process loaded-image proof for the pre-bound controller role."""

    role: str
    pid: int
    birth_identity: int
    executable: Path
    loaded_images: tuple[FileDigest, ...]
    plugin_path: Path
    plugin_sha256: str
    vendor_path: Path
    vendor_sha256: str
    owner_binding: ControllerRuntimeOwnerBinding
    owner_binding_sha256: str

    def __post_init__(self) -> None:
        if self.role != "controller_runtime":
            raise RuntimeClosureError("PROCESS_ATTESTATION_ROLE", self.role)
        if self.pid <= 0 or self.birth_identity <= 0:
            raise RuntimeClosureError(
                "PROCESS_ATTESTATION_IDENTITY", f"{self.pid}/{self.birth_identity}"
            )

    def as_document(self) -> dict[str, object]:
        return {
            "role": self.role,
            "pid": self.pid,
            "birth_identity": self.birth_identity,
            "executable": str(self.executable),
            "loaded_images": _inventory_document(self.loaded_images),
            "plugin_path": str(self.plugin_path),
            "plugin_sha256": self.plugin_sha256,
            "vendor_path": str(self.vendor_path),
            "vendor_sha256": self.vendor_sha256,
            "owner_binding": self.owner_binding.as_document(),
            "owner_binding_sha256": self.owner_binding_sha256,
        }


def _attestation_invalid(reason: str, detail: str = "") -> RuntimeClosureError:
    return RuntimeClosureError(
        "PROCESS_ATTESTATION_INVALID", f"{reason}: {detail}" if detail else reason
    )


def _closure_prefix_for(path: Path, prefixes: Sequence[Path]) -> Path | None:
    """The most specific sanctioned prefix that contains ``path``, if any."""

    candidates = [prefix for prefix in prefixes if path.is_relative_to(prefix)]
    if not candidates:
        return None
    return max(candidates, key=lambda prefix: len(prefix.parts))
