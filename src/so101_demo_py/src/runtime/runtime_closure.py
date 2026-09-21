"""Stable macOS task runtime closure, per-run binding and read-back attestation.

Design section 4.1 splits the old single manifest into three layers so that fresh per-run
facts can never be confused with the identity that must survive restarts:

* :class:`RuntimeClosureIdentity` -- only bytes and semantics that are equal across
  restarts: source/submodule commits, the copied install prefix inventory, typed
  executable/library/config inventories and the normalized environment constraints.
  Placement facts (ROS domain, Gazebo partition, session id, evidence root, timestamps)
  are deliberately absent and cannot leak in.
* :class:`RunBinding` -- the per-run facts (campaign/batch, fresh ROS domain, station
  session, evidence root, owner generation, start time).
* :class:`RuntimeAttestation` -- what was really observed after the spawn: process
  identities, loaded image paths read back from the process and the observed ROS domain.

Everything is fail closed: a drifted inventory, a missing submodule commit, a symlinked or
replaced file, a contaminated install prefix, a loaded image that comes from outside the
copied install, or a ROS domain that does not match the run binding raises
:class:`RuntimeClosureError` with a stable ``code``.
"""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ..parallel_batch.resource_identity import canonical_sha256

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle with task_stack
    from .task_stack import OwnedProcessIdentity

CLOSURE_SCHEMA_VERSION = 1

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

    source_commit: str
    mujoco_ros2_control_commit: str
    install_inventory_sha256: str
    executable_inventory: tuple[FileDigest, ...]
    library_inventory: tuple[FileDigest, ...]
    config_inventory: tuple[FileDigest, ...]
    normalized_environment_sha256: str

    def __post_init__(self) -> None:
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

    def as_document(self) -> dict[str, object]:
        return {
            "schema_version": CLOSURE_SCHEMA_VERSION,
            "source_commit": self.source_commit,
            "mujoco_ros2_control_commit": self.mujoco_ros2_control_commit,
            "install_inventory_sha256": self.install_inventory_sha256,
            "executable_inventory": _inventory_document(self.executable_inventory),
            "library_inventory": _inventory_document(self.library_inventory),
            "config_inventory": _inventory_document(self.config_inventory),
            "normalized_environment_sha256": self.normalized_environment_sha256,
        }

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


# --------------------------------------------------------------------------------------
# Readers
# --------------------------------------------------------------------------------------


def _digest_regular_file(path: Path, *, relative_path: str) -> FileDigest:
    """Digest one regular file through a single fd, refusing symlinks and replacements."""

    if path.is_symlink():
        raise RuntimeClosureError("CLOSURE_SYMLINK", str(path))
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise RuntimeClosureError("CLOSURE_UNREADABLE_FILE", f"{path}: {error}") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeClosureError("CLOSURE_NOT_REGULAR_FILE", str(path))
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(descriptor, 1 << 20)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
        if _READ_HOOK is not None:
            _READ_HOOK(path)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or size != after.st_size:
        raise RuntimeClosureError("CLOSURE_FILE_REPLACED", str(path))
    try:
        current = os.stat(path, follow_symlinks=False)
    except OSError as error:
        raise RuntimeClosureError("CLOSURE_FILE_REPLACED", f"{path}: {error}") from error
    if not stat.S_ISREG(current.st_mode) or (current.st_dev, current.st_ino) != (
        after.st_dev,
        after.st_ino,
    ):
        raise RuntimeClosureError("CLOSURE_FILE_REPLACED", str(path))
    return FileDigest(
        relative_path=relative_path, sha256=digest.hexdigest(), size_bytes=size
    )


def _walk_install_files(root: Path) -> tuple[tuple[FileDigest, int], ...]:
    collected: list[tuple[FileDigest, int]] = []
    for current_root, directory_names, file_names in os.walk(root, followlinks=False):
        current = Path(current_root)
        for name in sorted(directory_names):
            candidate = current / name
            if name in SKIPPED_DIRECTORY_NAMES:
                continue
            if candidate.is_symlink():
                raise RuntimeClosureError("CLOSURE_SYMLINK", str(candidate))
        directory_names[:] = sorted(
            name for name in directory_names if name not in SKIPPED_DIRECTORY_NAMES
        )
        for name in sorted(file_names):
            path = current / name
            relative_path = path.relative_to(root).as_posix()
            digest = _digest_regular_file(path, relative_path=relative_path)
            mode = os.stat(path, follow_symlinks=False).st_mode
            collected.append((digest, mode))
    return tuple(collected)


def _classify(entry: FileDigest, mode: int) -> str:
    name = Path(entry.relative_path).name
    if any(marker in name for marker in LIBRARY_MARKERS):
        return "library"
    if Path(name).suffix in CONFIG_SUFFIXES:
        return "config"
    if mode & 0o111:
        return "executable"
    return "other"


def collect_install_inventory(install_root: Path) -> tuple[FileDigest, ...]:
    """Every regular file under the copied install prefix, as relative-path digests."""

    root = _validated_install_root(install_root)
    return tuple(digest for digest, _mode in _walk_install_files(root))


def _validated_install_root(
    install_root: Path, forbidden_roots: Sequence[Path] = ()
) -> Path:
    root = Path(install_root)
    if not root.is_absolute():
        raise RuntimeClosureError(
            "CLOSURE_INSTALL_ROOT_INVALID", f"install root must be absolute: {root}"
        )
    if root.is_symlink():
        raise RuntimeClosureError(
            "CLOSURE_INSTALL_ROOT_INVALID", f"install root must not be a symlink: {root}"
        )
    try:
        resolved = root.resolve(strict=True)
    except OSError as error:
        raise RuntimeClosureError(
            "CLOSURE_INSTALL_ROOT_INVALID", f"{root}: {error}"
        ) from error
    if not resolved.is_dir():
        raise RuntimeClosureError(
            "CLOSURE_INSTALL_ROOT_INVALID", f"install root is not a directory: {resolved}"
        )
    for forbidden in forbidden_roots:
        candidate = Path(forbidden)
        try:
            resolved_forbidden = candidate.resolve(strict=False)
        except OSError:  # pragma: no cover - resolve(strict=False) rarely fails
            continue
        if resolved == resolved_forbidden or resolved.is_relative_to(resolved_forbidden):
            raise RuntimeClosureError(
                "CLOSURE_PREFIX_CONTAMINATION",
                f"{resolved} lives inside the forbidden root {resolved_forbidden}",
            )
    return resolved


def normalized_environment_sha256(
    environment: Mapping[str, str] | None,
    *,
    keys: Sequence[str] = CLOSURE_ENVIRONMENT_KEYS,
) -> str:
    """Digest the closed set of environment constraints that belong to the identity."""

    values = dict(environment or {})
    document = {
        key: (values[key] if isinstance(values.get(key), str) else None) for key in sorted(keys)
    }
    return canonical_sha256(document)


def build_runtime_closure_identity(
    *,
    install_root: Path,
    source_commit: str,
    mujoco_ros2_control_commit: str,
    environment: Mapping[str, str] | None = None,
    forbidden_roots: Sequence[Path] = (),
) -> RuntimeClosureIdentity:
    """Read the frozen copied install once and freeze the restart-stable identity."""

    _require_commit(
        "source_commit", source_commit, missing_code="CLOSURE_SOURCE_COMMIT_MISSING"
    )
    _require_commit(
        "mujoco_ros2_control_commit",
        mujoco_ros2_control_commit,
        missing_code="CLOSURE_SUBMODULE_COMMIT_MISSING",
    )
    root = _validated_install_root(install_root, forbidden_roots)
    collected = _walk_install_files(root)
    if not collected:
        raise RuntimeClosureError("CLOSURE_INVENTORY_EMPTY", str(root))
    buckets: dict[str, list[FileDigest]] = {
        "executable": [],
        "library": [],
        "config": [],
    }
    for digest, mode in collected:
        category = _classify(digest, mode)
        if category in buckets:
            buckets[category].append(digest)
    return RuntimeClosureIdentity(
        source_commit=source_commit,
        mujoco_ros2_control_commit=mujoco_ros2_control_commit,
        install_inventory_sha256=canonical_sha256(
            _inventory_document([digest for digest, _mode in collected])
        ),
        executable_inventory=tuple(buckets["executable"]),
        library_inventory=tuple(buckets["library"]),
        config_inventory=tuple(buckets["config"]),
        normalized_environment_sha256=normalized_environment_sha256(environment),
    )


def verify_runtime_closure(
    expected: RuntimeClosureIdentity,
    *,
    install_root: Path,
    source_commit: str,
    mujoco_ros2_control_commit: str,
    environment: Mapping[str, str] | None = None,
    forbidden_roots: Sequence[Path] = (),
) -> RuntimeClosureIdentity:
    """Re-read the prefix before spawning and fail closed on any drift."""

    if not isinstance(expected, RuntimeClosureIdentity):
        raise RuntimeClosureError("CLOSURE_IDENTITY_TYPE", type(expected).__name__)
    if source_commit != expected.source_commit:
        raise RuntimeClosureError(
            "CLOSURE_SOURCE_COMMIT_MISMATCH",
            f"expected {expected.source_commit}, observed {source_commit}",
        )
    if mujoco_ros2_control_commit != expected.mujoco_ros2_control_commit:
        raise RuntimeClosureError(
            "CLOSURE_SUBMODULE_COMMIT_MISMATCH",
            f"expected {expected.mujoco_ros2_control_commit}, observed {mujoco_ros2_control_commit}",
        )
    observed = build_runtime_closure_identity(
        install_root=install_root,
        source_commit=source_commit,
        mujoco_ros2_control_commit=mujoco_ros2_control_commit,
        environment=environment,
        forbidden_roots=forbidden_roots,
    )
    if observed.install_inventory_sha256 != expected.install_inventory_sha256:
        raise RuntimeClosureError(
            "CLOSURE_INVENTORY_DRIFT",
            f"install inventory {observed.install_inventory_sha256} != {expected.install_inventory_sha256}",
        )
    if observed.normalized_environment_sha256 != expected.normalized_environment_sha256:
        raise RuntimeClosureError(
            "CLOSURE_ENVIRONMENT_DRIFT",
            f"environment {observed.normalized_environment_sha256} != {expected.normalized_environment_sha256}",
        )
    if observed.sha256 != expected.sha256:
        raise RuntimeClosureError(
            "CLOSURE_IDENTITY_DRIFT",
            f"{observed.sha256} != {expected.sha256}",
        )
    return observed


def build_run_binding(
    *,
    campaign_id: str,
    batch_id: str,
    ros_domain_id: int,
    station_session_id: str,
    evidence_root: Path,
    owner_generation: int,
    started_monotonic_ns: int | None = None,
) -> RunBinding:
    return RunBinding(
        campaign_id=campaign_id,
        batch_id=batch_id,
        ros_domain_id=ros_domain_id,
        station_session_id=station_session_id,
        evidence_root=Path(evidence_root),
        owner_generation=owner_generation,
        started_monotonic_ns=(
            time.monotonic_ns() if started_monotonic_ns is None else started_monotonic_ns
        ),
    )


def build_runtime_attestation(
    *,
    closure: RuntimeClosureIdentity,
    run_binding: RunBinding,
    install_root: Path,
    process_identities: Sequence["OwnedProcessIdentity"],
    loaded_images: Sequence[Path],
    observed_ros_domain_id: int,
) -> RuntimeAttestation:
    """Attest only what was read back: identities, loaded images and the observed domain."""

    if not isinstance(closure, RuntimeClosureIdentity):
        raise RuntimeClosureError("CLOSURE_IDENTITY_TYPE", type(closure).__name__)
    if not isinstance(run_binding, RunBinding):
        raise RuntimeClosureError("RUN_BINDING_TYPE", type(run_binding).__name__)
    identities = tuple(process_identities)
    if not identities:
        raise RuntimeClosureError(
            "ATTESTATION_PROCESS_IDENTITIES", "at least one process identity is required"
        )
    if len({identity.role for identity in identities}) != len(identities):
        raise RuntimeClosureError("ATTESTATION_PROCESS_ROLES", "roles must be unique")
    if len({identity.pid for identity in identities}) != len(identities):
        raise RuntimeClosureError("ATTESTATION_PROCESS_PIDS", "pids must be unique")
    if observed_ros_domain_id != run_binding.ros_domain_id:
        raise RuntimeClosureError(
            "ATTESTATION_ROS_DOMAIN_MISMATCH",
            f"observed {observed_ros_domain_id}, bound {run_binding.ros_domain_id}",
        )
    root = _validated_install_root(install_root)
    known = closure.inventory
    known_names = {Path(entry.relative_path).name: entry for entry in known.values()}
    attested: list[FileDigest] = []
    seen: set[str] = set()
    for image in loaded_images:
        path = Path(image)
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise RuntimeClosureError("LOADED_IMAGE_UNREADABLE", f"{path}: {error}") from error
        if resolved.is_relative_to(root):
            relative_path = resolved.relative_to(root).as_posix()
            entry = known.get(relative_path)
            if entry is None:
                raise RuntimeClosureError("LOADED_IMAGE_UNKNOWN", relative_path)
            digest = _digest_regular_file(resolved, relative_path=relative_path)
            if digest.sha256 != entry.sha256 or digest.size_bytes != entry.size_bytes:
                raise RuntimeClosureError(
                    "LOADED_IMAGE_DIGEST_MISMATCH",
                    f"{relative_path}: {digest.sha256} != {entry.sha256}",
                )
            if relative_path not in seen:
                seen.add(relative_path)
                attested.append(digest)
            continue
        if resolved.name in known_names:
            raise RuntimeClosureError(
                "LOADED_IMAGE_OUTSIDE_INSTALL",
                f"{resolved} carries the closure artifact {resolved.name}",
            )
    return RuntimeAttestation(
        closure_sha256=closure.sha256,
        run_binding_sha256=run_binding.sha256,
        process_identities=identities,
        loaded_images=tuple(attested),
        observed_ros_domain_id=observed_ros_domain_id,
    )


# --------------------------------------------------------------------------------------
# Platform read-back probes
# --------------------------------------------------------------------------------------


def read_process_birth_identity(pid: int) -> int:
    """Read a stable birth identity for ``pid`` so PID reuse cannot be mistaken for it."""

    if not isinstance(pid, int) or pid <= 0:
        raise RuntimeClosureError("PROCESS_IDENTITY_INVALID", str(pid))
    if sys.platform == "darwin":
        completed = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart="],
            check=False,
            capture_output=True,
            text=True,
        )
        text = completed.stdout.strip()
        if completed.returncode != 0 or not text:
            raise RuntimeClosureError(
                "PROCESS_IDENTITY_UNAVAILABLE", f"ps could not describe PID {pid}"
            )
        return int(hashlib.sha256(f"darwin\0{text}".encode()).hexdigest()[:15], 16)
    try:
        fields = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()
    except OSError as error:
        raise RuntimeClosureError(
            "PROCESS_IDENTITY_UNAVAILABLE", f"{pid}: {error}"
        ) from error
    if len(fields) <= 19:
        raise RuntimeClosureError("PROCESS_IDENTITY_UNAVAILABLE", f"incomplete stat for {pid}")
    return int(fields[19])


def _darwin_loaded_images(pid: int) -> tuple[Path, ...]:
    completed = subprocess.run(
        ["vmmap", str(pid)], check=False, capture_output=True, text=True
    )
    if completed.returncode != 0:
        raise RuntimeClosureError(
            "LOADED_IMAGE_PROBE_FAILED",
            f"vmmap {pid} exited {completed.returncode}: {completed.stderr.strip()}",
        )
    paths: set[Path] = set()
    for line in completed.stdout.splitlines():
        candidate = line.rsplit(None, 1)[-1]
        if not candidate.startswith("/"):
            continue
        path = Path(candidate)
        if path.is_file():
            paths.add(path)
    return tuple(sorted(paths))


def _linux_loaded_images(pid: int) -> tuple[Path, ...]:
    try:
        document = Path(f"/proc/{pid}/maps").read_text(encoding="utf-8")
    except OSError as error:
        raise RuntimeClosureError(
            "LOADED_IMAGE_PROBE_FAILED", f"{pid}: {error}"
        ) from error
    paths: set[Path] = set()
    for line in document.splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) < 6 or not fields[5].startswith("/"):
            continue
        path = Path(fields[5])
        if path.is_file():
            paths.add(path)
    return tuple(sorted(paths))


def default_loaded_image_probe(pid: int) -> tuple[Path, ...]:
    """Read back the images a live process really has mapped."""

    if not isinstance(pid, int) or pid <= 0:
        raise RuntimeClosureError("PROCESS_IDENTITY_INVALID", str(pid))
    if sys.platform == "darwin":
        return _darwin_loaded_images(pid)
    return _linux_loaded_images(pid)
