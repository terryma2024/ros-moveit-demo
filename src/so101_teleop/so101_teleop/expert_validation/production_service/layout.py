"""Constants, source identity helpers and the production runtime layout."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Mapping

from ament_index_python.packages import get_package_prefix, get_package_share_directory

from so101_teleop.expert_validation.preflight import (
    MACOS_EXECUTION_PROFILES,
)

_BROKER_IMAGE = "so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1"


#: The installed matrix by routing key, so a restored row is resolved by name and never inferred.
PROFILES_BY_NAME = {row.profile: row for row in MACOS_EXECUTION_PROFILES}


def _issuance_request_sha256(
    *,
    task_id,
    dispatch_id,
    campaign_id,
    batch_id,
    manifest_id,
    execution_profile,
    schema_version,
    batch_kind,
    worker_count,
    config_sha256,
    runtime_closure_sha256,
    evidence_root,
    owner_generation,
    max_runs,
) -> str:
    """The one request digest an issuance command is consumed with.

    Every coordinate the caller named is in it, so replaying the same issuance is distinguishable
    from reusing the same command id for a different one.
    """

    document = {
        "operation": "ISSUE_CANDIDATE_CONTEXT",
        "task_id": task_id,
        "dispatch_id": dispatch_id,
        "campaign_id": campaign_id,
        "batch_id": batch_id,
        "manifest_id": manifest_id,
        "execution_profile": execution_profile,
        "schema_version": schema_version,
        "batch_kind": batch_kind,
        "worker_count": worker_count,
        "config_sha256": config_sha256,
        "runtime_closure_sha256": runtime_closure_sha256,
        "evidence_root": str(evidence_root),
        "owner_generation": owner_generation,
        "max_runs": max_runs,
    }
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_file(environment: Mapping[str, str], name: str, default: Path | None = None) -> Path:
    value = environment.get(name)
    path = Path(value) if value else default
    if path is None or not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise RuntimeError(f"{name}_INVALID")
    return path.resolve()


def _optional_file(environment: Mapping[str, str], name: str) -> Path | None:
    value = environment.get(name)
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise RuntimeError(f"{name}_INVALID")
    return path.resolve()


def _source_identity(
    *, module_path: Path, provenance_binding: Path | None = None,
    subprocess_runner=subprocess.run,
) -> tuple[Path, str | None]:
    """Resolve the installed source root; the commit is an optional DEBUG observation.

    A deployment may be a pure copied install with no Git checkout, so this function
    runs no Git command, requires no commit and never refuses on commit content.
    """

    del subprocess_runner
    if provenance_binding is not None:
        binding_path = Path(provenance_binding)
        if (
            not binding_path.is_absolute()
            or binding_path.is_symlink()
            or not binding_path.is_file()
        ):
            raise RuntimeError("SO101_VALIDATION_PROVENANCE_BINDING_INVALID")
        try:
            document = json.loads(binding_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeError("SO101_VALIDATION_PROVENANCE_BINDING_INVALID") from error
        source_root = document.get("source_root")
        if (
            not isinstance(source_root, str)
            or not Path(source_root).is_absolute()
            or Path(source_root).is_symlink()
            or not Path(source_root).is_dir()
        ):
            raise RuntimeError("SO101_VALIDATION_PROVENANCE_BINDING_INVALID")
        source_root = Path(source_root).resolve()
        declared_commit = document.get("source_commit")
        if declared_commit is not None and not isinstance(declared_commit, str):
            raise RuntimeError("SO101_VALIDATION_PROVENANCE_BINDING_INVALID")
        observed = declared_commit.strip() or None if declared_commit else None
        return source_root, observed
    candidate = Path(module_path).resolve().parent
    for parent in (candidate, *candidate.parents):
        if (parent / "src/so101_demo_py").is_dir():
            return parent, None
    return candidate, None


@dataclass(frozen=True, slots=True)
class ProductionRuntimeLayout:
    source_root: Path
    source_commit: str | None
    demo_prefix: Path
    points_path: Path
    parallel_config_path: Path
    adaptive_config_path: Path
    coordinator_executable: Path
    cleanup_executable: Path
    adaptive_wrapper: Path
    provenance_binding: Path | None
    yolo_weights_path: Path | None
    grounded_root: Path | None
    yolo_weights_sha256: str
    grounded_manifest_sha256: str
    broker_image_id: str
    parallel_acceptance: Path | None
    adaptive_acceptance: Path | None
    adaptive_fault_injection: Path | None
    adaptive_performance_tiers: tuple[int, ...]

    @classmethod
    def discover(cls, environment: Mapping[str, str]) -> "ProductionRuntimeLayout":
        demo_prefix = Path(get_package_prefix("so101_demo_py")).resolve()
        demo_share = Path(get_package_share_directory("so101_demo_py")).resolve()
        points = _required_file(
            environment,
            "SO101_VALIDATION_POINTS",
            demo_share / "config/mujoco/moveit_expert_validation_points.yaml",
        )
        parallel = _required_file(
            environment,
            "SO101_VALIDATION_PARALLEL_CONFIG",
            demo_share / "config/mujoco/parallel_batch_linux_cuda.yaml",
        )
        adaptive = _required_file(
            environment,
            "SO101_VALIDATION_ADAPTIVE_CONFIG",
            demo_share / "config/mujoco/adaptive_worker_pool.yaml",
        )
        coordinator = _required_file(
            environment,
            "SO101_VALIDATION_COORDINATOR",
            demo_prefix / "lib/so101_demo_py/so101_parallel_batch",
        )
        cleanup = _required_file(
            environment,
            "SO101_VALIDATION_ADAPTIVE_CLEANUP",
            demo_prefix / "lib/so101_demo_py/so101_parallel_batch_cleanup",
        )
        wrapper = _required_file(
            environment,
            "SO101_VALIDATION_ADAPTIVE_WRAPPER",
            demo_prefix / "lib/so101_demo_py/run_so101_adaptive_batch.zsh",
        )
        provenance_binding = _optional_file(
            environment, "SO101_VALIDATION_PROVENANCE_BINDING"
        )
        import so101_demo

        module = Path(so101_demo.__file__).absolute()
        if provenance_binding is not None and (
            module.is_symlink()
            or not module.is_file()
            or not module.is_relative_to(demo_prefix)
        ):
            raise RuntimeError("SO101_VALIDATION_INSTALLED_MODULE_INVALID")
        source_root, source_commit = _source_identity(
            module_path=module,
            provenance_binding=provenance_binding,
        )
        configured_source = environment.get("SO101_VALIDATION_SOURCE_ROOT")
        if configured_source and Path(configured_source).resolve() != source_root:
            raise RuntimeError("SO101_VALIDATION_SOURCE_ROOT_MISMATCH")
        # A configured commit is DEBUG metadata only: it can never refuse a layout.
        configured_commit = environment.get("SO101_VALIDATION_SOURCE_COMMIT")
        if configured_commit and source_commit is None:
            source_commit = str(configured_commit).strip() or None
        yolo = environment.get("SO101_VALIDATION_YOLO_WEIGHTS")
        yolo_path = Path(yolo).resolve() if yolo else None
        if yolo_path is not None and (not yolo_path.is_file() or yolo_path.is_symlink()):
            raise RuntimeError("SO101_VALIDATION_YOLO_WEIGHTS_INVALID")
        grounded = environment.get("SO101_VALIDATION_GROUNDED_ROOT")
        grounded_root = Path(grounded).resolve() if grounded else None
        if grounded_root is not None and (
            not grounded_root.is_dir()
            or grounded_root.is_symlink()
            or not (grounded_root / "manifest.json").is_file()
        ):
            raise RuntimeError("SO101_VALIDATION_GROUNDED_ROOT_INVALID")
        tiers = tuple(
            int(value)
            for value in environment.get("SO101_VALIDATION_ADAPTIVE_PERFORMANCE_TIERS", "").split(",")
            if value
        )
        return cls(
            source_root=source_root,
            source_commit=source_commit,
            demo_prefix=demo_prefix,
            points_path=points,
            parallel_config_path=parallel,
            adaptive_config_path=adaptive,
            coordinator_executable=coordinator,
            cleanup_executable=cleanup,
            adaptive_wrapper=wrapper,
            provenance_binding=provenance_binding,
            yolo_weights_path=yolo_path,
            grounded_root=grounded_root,
            yolo_weights_sha256=(
                _sha256(yolo_path)
                if yolo_path is not None
                else environment.get("SO101_VALIDATION_YOLO_SHA256", "0" * 64)
            ),
            grounded_manifest_sha256=(
                _sha256(grounded_root / "manifest.json")
                if grounded_root is not None
                else environment.get("SO101_VALIDATION_GROUNDED_SHA256", "0" * 64)
            ),
            broker_image_id=environment.get("SO101_VALIDATION_BROKER_IMAGE", _BROKER_IMAGE),
            parallel_acceptance=_optional_file(environment, "SO101_VALIDATION_PARALLEL_ACCEPTANCE"),
            adaptive_acceptance=_optional_file(environment, "SO101_VALIDATION_ADAPTIVE_ACCEPTANCE"),
            adaptive_fault_injection=_optional_file(
                environment, "SO101_VALIDATION_ADAPTIVE_FAULT_INJECTION"
            ),
            adaptive_performance_tiers=tiers,
        )
