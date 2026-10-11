"""Build and verify the runtime closure, the run binding and the runtime attestation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
from pathlib import Path
import subprocess
import sys
import time

from so101_demo.parallel_batch.canonical_json import canonical_sha256
from so101_demo.runtime.runtime_closure.attestation import (
    _classify,
    _digest_regular_file,
    _validated_install_root,
    _walk_install_files,
    normalized_environment_sha256,
)
from so101_demo.runtime.runtime_closure.identities import (
    FileDigest,
    RunBinding,
    RuntimeAttestation,
    RuntimeClosureError,
    RuntimeClosureIdentity,
    _inventory_document,
    _require_commit,
)


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
    collected, aliases = _walk_install_files(root)
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
        install_root=root,
        source_commit=source_commit,
        mujoco_ros2_control_commit=mujoco_ros2_control_commit,
        install_inventory_sha256=canonical_sha256(
            _inventory_document([digest for digest, _mode in collected])
        ),
        executable_inventory=tuple(buckets["executable"]),
        library_inventory=tuple(buckets["library"]),
        config_inventory=tuple(buckets["config"]),
        dylib_alias_inventory=aliases,
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
    observed_root = _validated_install_root(install_root, forbidden_roots)
    if observed_root != expected.install_root:
        raise RuntimeClosureError(
            "CLOSURE_INSTALL_ROOT_MISMATCH",
            f"expected {expected.install_root}, observed {observed_root}",
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
        fields = line.rsplit(None, 1)
        if not fields:
            continue
        candidate = fields[-1]
        if not candidate.startswith("/"):
            continue
        path = Path(candidate)
        try:
            if path.is_file():
                paths.add(path)
        except OSError:
            continue
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
