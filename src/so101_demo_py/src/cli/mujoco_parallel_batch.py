"""User entry point for an isolated, dynamically leased MuJoCo validation batch."""

from __future__ import annotations

import argparse
import configparser
from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from typing import Callable, Mapping

import yaml

from so101_demo.parallel_batch.artifacts import (
    AttemptWorkspace,
    SealedResultAdapter,
    ValidationWorkspace,
    write_recovery_receipt,
)
from so101_demo.parallel_batch.broker import BrokerResponse
from so101_demo.parallel_batch.contracts import (
    AttemptIdentity,
    AttemptStatus,
    BatchRequest,
    BatchSummary,
    ContractError,
    LeaseIdentity,
    ParallelRuntimeConfig,
    RunMode,
    ValidationStatus,
    ValidationIdentity,
    WorkerState,
    ExecutionKind,
    InferenceRequest,
    ModelOutcome,
    NormalizedInferenceResponseIdentity,
    load_parallel_runtime_config,
)
from so101_demo.parallel_batch.coordinator import BatchCoordinator
from so101_demo.parallel_batch.journal import CoordinatorJournal
from so101_demo.parallel_batch.resources import (
    CurrentRuntimeProvenanceProbe,
    ResourceAdmission,
    ResourceManifest,
    ResourceSnapshot,
    ResourceThresholds,
    Task14AcceptanceProvider,
    Task14LiveHeadroomVerifier,
    WorkerResourceAllocator,
    WorkerResources,
)
from so101_demo.parallel_batch.worker import LeaseGrantPaused, ParallelWorker
from so101_demo.runtime.parallel_ipc import (
    AuthenticatedUnixServer,
    BrokerTransport,
    UnixRpcClient,
    WorkerTokenAuthority,
    _inference_request,
    _snapshot,
)
from so101_demo.runtime.parallel_processes import ProcessSupervisor
from so101_demo.runtime.parallel_ros_runtime import (
    ParallelRosRuntimePorts as _ConcreteRosWorkerRuntimePorts,
)
from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime
from so101_demo.runtime.task_stack import OwnedProcessIdentity


_CATALOG_SHA256 = "c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5"
_BROKER_IMAGE = "so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1"
_CURRENT_PROVENANCE_FILES = {
    "source_tree_sha256": "source_tree_sha256.json",
    "install_tree_sha256": "install_tree_sha256.json",
    "runtime_config_sha256": "runtime_config.json",
    "policy_sha256": "policy_sha256.json",
    "scene_sha256": "scene_sha256.json",
    "models_sha256": "models_sha256.json",
    "container_sha256": "container_sha256.json",
    "catalog_sha256": "catalog_sha256.json",
}


class CliError(RuntimeError):
    """Startup or batch composition failed closed."""


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CliError(f"ARGUMENT_ERROR: {message}")


@dataclass(frozen=True, slots=True)
class PreparedBatch:
    request: BatchRequest
    config: ParallelRuntimeConfig
    config_path: Path
    points_path: Path
    catalog: Mapping[str, Mapping[str, object]]
    catalog_sha256: str
    selection_sha256: str
    broker_image: str
    yolo_weights: Path
    yolo_weights_sha256: str
    grounded_root: Path
    grounded_manifest_sha256: str
    provenance: Mapping[str, object]
    manifest: Mapping[str, object]
    provenance_inputs: Mapping[str, object]
    provenance_verifier: Callable[[Mapping[str, object]], Mapping[str, object]]
    live_headroom_evidence: Path | None
    live_headroom_acceptance: Path | None
    live_headroom_current_provenance: Mapping[str, Path]
    live_headroom_verification: Mapping[str, object] | None
    resume: bool


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="so101_parallel_batch")
    parser.add_argument("--points", type=Path, required=True)
    parser.add_argument("--point-id", action="append", default=[])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--worker-count", default="2")
    parser.add_argument("--max-points-per-worker", default="10")
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--broker-image", required=True)
    parser.add_argument("--yolo-weights", type=Path, required=True)
    parser.add_argument("--yolo-weights-sha256", required=True)
    parser.add_argument("--grounded-root", type=Path, required=True)
    parser.add_argument("--grounded-manifest-sha256", required=True)
    parser.add_argument("--run-mode", required=True)
    parser.add_argument("--live-headroom-evidence", type=Path)
    parser.add_argument("--live-headroom-acceptance", type=Path)
    parser.add_argument("--live-headroom-current-provenance-root", type=Path)
    parser.add_argument("--resume", action="store_true")
    return parser


def _integer(name: str, value: str) -> int:
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        raise CliError(f"MALFORMED_INTEGER: {name}")
    result = int(value)
    if result <= 0:
        raise CliError(f"MALFORMED_INTEGER: {name}")
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise CliError(f"PROVENANCE_READ_FAILED: {path}") from error
    return digest.hexdigest()


def _absolute(name: str, path: Path) -> Path:
    raw = str(path)
    if not path.is_absolute() or "\0" in raw or any(part in {".", ".."} for part in raw.split("/")):
        raise CliError(f"ABSOLUTE_PATH_REQUIRED: {name}")
    return path


def _live_headroom_verifier(
    acceptance_path: Path,
    current_provenance: Mapping[str, Path],
) -> Task14LiveHeadroomVerifier:
    return Task14LiveHeadroomVerifier(
        acceptance_provider=Task14AcceptanceProvider(
            acceptance_path=acceptance_path,
        ),
        provenance_probe=CurrentRuntimeProvenanceProbe(
            current_paths=current_provenance,
        ),
    )


def _prepare_live_headroom(options, config, worker_count):
    supplied = (
        options.live_headroom_evidence,
        options.live_headroom_acceptance,
        options.live_headroom_current_provenance_root,
    )
    if worker_count != 3:
        if any(value is not None for value in supplied):
            raise CliError("LIVE_HEADROOM_EVIDENCE_UNEXPECTED")
        return None, None, {}, None
    if any(value is None for value in supplied):
        raise CliError("THREE_WORKER_LIVE_EVIDENCE_REQUIRED")
    evidence = _absolute("live_headroom_evidence", supplied[0])
    acceptance = _absolute("live_headroom_acceptance", supplied[1])
    current_root = _absolute(
        "live_headroom_current_provenance_root", supplied[2]
    )
    current_provenance = {
        name: current_root / filename
        for name, filename in _CURRENT_PROVENANCE_FILES.items()
    }
    verifier = _live_headroom_verifier(acceptance, current_provenance)
    try:
        verified = verifier.verify(evidence, config=config)
    except Exception as error:
        raise CliError("THREE_WORKER_LIVE_EVIDENCE_INVALID") from error
    if not isinstance(verified, Mapping):
        raise CliError("THREE_WORKER_LIVE_EVIDENCE_INVALID")
    return evidence, acceptance, current_provenance, dict(verified)


def _read_existing_json(path: Path, *, label: str) -> Mapping[str, object]:
    """Read one bounded owner-controlled recovery authority without following links."""
    try:
        before = path.lstat()
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        raise CliError(f"RECOVERY_{label}_MISSING") from error
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or not stat.S_ISREG(opened.st_mode)
            or before.st_uid != os.getuid()
            or opened.st_uid != os.getuid()
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
            or opened.st_size <= 0
            or opened.st_size > 8 * 1024 * 1024
        ):
            raise CliError(f"RECOVERY_{label}_INVALID")
        payload = os.read(descriptor, opened.st_size + 1)
        after = os.fstat(descriptor)
        if (
            len(payload) != opened.st_size
            or (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        ):
            raise CliError(f"RECOVERY_{label}_CHANGED")
        document = json.loads(payload.decode("utf-8", errors="strict"))
        if type(document) is not dict:
            raise CliError(f"RECOVERY_{label}_INVALID")
        return document
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CliError(f"RECOVERY_{label}_INVALID") from error
    finally:
        os.close(descriptor)


def _catalog(path: Path) -> tuple[dict[str, Mapping[str, object]], str]:
    path = path.resolve()
    digest = _sha256(path)
    if digest != _CATALOG_SHA256:
        raise CliError("POINT_CATALOG_HASH_MISMATCH")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise CliError("POINT_CATALOG_INVALID") from error
    if type(document) is not dict or set(document) != {"schema_version", "points"}:
        raise CliError("POINT_CATALOG_SCHEMA")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise CliError("POINT_CATALOG_SCHEMA")
    points = document["points"]
    if not isinstance(points, list) or len(points) != 20:
        raise CliError("POINT_CATALOG_SCHEMA")
    catalog = {}
    for point in points:
        if type(point) is not dict or set(point) != {"id", "label", "cup_position_world_m"}:
            raise CliError("POINT_CATALOG_SCHEMA")
        point_id = point["id"]
        if not isinstance(point_id, str) or not point_id or point_id in catalog:
            raise CliError("POINT_CATALOG_DUPLICATE")
        catalog[point_id] = point
    return catalog, digest


def verify_provenance(spec: Mapping[str, object]) -> Mapping[str, object]:
    """Verify exact local model and image inputs before creating the batch root."""

    yolo = _absolute("yolo_weights", Path(spec["yolo_weights"]))
    grounded = _absolute("grounded_root", Path(spec["grounded_root"]))
    if not yolo.is_file() or yolo.is_symlink():
        raise CliError("PROVENANCE_YOLO_PATH")
    if not grounded.is_dir() or grounded.is_symlink():
        raise CliError("PROVENANCE_GROUNDED_PATH")
    manifest = grounded / "manifest.json"
    if not manifest.is_file() or manifest.is_symlink():
        raise CliError("PROVENANCE_GROUNDED_MANIFEST")
    if _sha256(yolo) != spec["yolo_weights_sha256"]:
        raise CliError("PROVENANCE_YOLO_HASH")
    if _sha256(manifest) != spec["grounded_manifest_sha256"]:
        raise CliError("PROVENANCE_GROUNDED_HASH")
    image = spec["broker_image"]
    if image != _BROKER_IMAGE:
        raise CliError("PROVENANCE_BROKER_IMAGE")
    module_import_path = Path(__file__).absolute()
    module_path = module_import_path.resolve()
    try:
        repository_root = Path(subprocess.run(
            ["git", "-C", str(module_path.parent), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5.0,
        ).stdout.strip()).resolve()
        source_commit = subprocess.run(
            ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=5.0,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(repository_root), "status", "--porcelain",
             "--untracked-files=no"],
            check=True, capture_output=True, text=True, timeout=5.0,
        ).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise CliError("PROVENANCE_SOURCE_COMMIT") from error
    if len(source_commit) != 40 or any(character not in "0123456789abcdef" for character in source_commit):
        raise CliError("PROVENANCE_SOURCE_COMMIT")
    if dirty:
        raise CliError("PROVENANCE_SOURCE_DIRTY")
    package_root = repository_root / "src/so101_demo_py"
    console = shutil.which("so101_parallel_batch")
    if console is None:
        raise CliError("PROVENANCE_CONSOLE_MISSING")
    console_path = Path(console).resolve()
    config_path = Path(spec["config"]).resolve()
    points_path = Path(spec["points"]).resolve()
    _validate_provenance_overlay(
        repository_root, module_path, console_path, config_path, points_path
    )
    policy_path = package_root / "config/mujoco/headless_execution.yaml"
    scene_config = package_root / "config/mujoco/task_scene.yaml"
    scene_model = package_root / "assets/mujoco/scene.xml"
    if any(not value.is_file() or value.is_symlink() for value in (
        console_path, module_path, config_path, points_path,
        policy_path, scene_config, scene_model,
    )):
        raise CliError("PROVENANCE_INSTALLED_INPUT_MISSING")
    from so101_demo.cli.parallel_perception_broker import source_hash
    installed_identity = _installed_overlay_identity(
        repository_root, module_import_path, console_path, source_hash=source_hash
    )
    try:
        from so101_demo.cli.parallel_perception_broker import image_record

        immutable_image = image_record(image)
    except Exception as error:
        raise CliError("PROVENANCE_BROKER_IMAGE_READBACK") from error
    return {
        "source_commit": source_commit,
        "source_dirty": False,
        "source_tree_sha256": source_hash(package_root),
        "installed_console_path": str(console_path),
        "installed_console_sha256": _sha256(console_path),
        "installed_module_path": str(module_path),
        "installed_module_sha256": _sha256(module_path),
        **installed_identity,
        "runtime_config_sha256": _sha256(config_path),
        "dynamic_policy_sha256": _sha256(policy_path),
        "task_scene_sha256": _sha256(scene_config),
        "scene_model_sha256": _sha256(scene_model),
        "catalog_sha256": spec["catalog_sha256"],
        "yolo_weights_sha256": spec["yolo_weights_sha256"],
        "grounded_manifest_sha256": spec["grounded_manifest_sha256"],
        "broker_image": image,
        **immutable_image,
    }


def _validate_provenance_overlay(
    repository_root: Path,
    module_path: Path,
    console_path: Path,
    config_path: Path,
    points_path: Path,
) -> None:
    """Reject a source/import/console/config selection spanning checkouts."""

    repository_root = Path(repository_root).resolve()
    package_root = repository_root / "src/so101_demo_py"
    expected_module = (
        package_root / "src/cli/mujoco_parallel_batch.py"
    ).resolve()
    expected_console_root = (
        repository_root / "install/so101_demo_py/lib/so101_demo_py"
    ).resolve()
    try:
        Path(config_path).resolve().relative_to(package_root.resolve())
        Path(points_path).resolve().relative_to(package_root.resolve())
    except ValueError as error:
        raise CliError("PROVENANCE_MIXED_OVERLAY") from error
    if (
        Path(module_path).resolve() != expected_module
        or Path(console_path).resolve()
        != (expected_console_root / "so101_parallel_batch").resolve()
    ):
        raise CliError("PROVENANCE_MIXED_OVERLAY")


def _installed_overlay_identity(
    repository_root: Path,
    module_import_path: Path,
    console_path: Path,
    *,
    source_hash,
) -> Mapping[str, object]:
    """Bind editable build/install artifacts to this exact source checkout."""

    repository_root = Path(repository_root).resolve()
    source_package = (repository_root / "src/so101_demo_py/src").resolve()
    build_package = repository_root / "build/so101_demo_py/so101_demo"
    expected_module = build_package / "cli/mujoco_parallel_batch.py"
    expected_console = (
        repository_root
        / "install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch"
    )
    egg_links = tuple(
        (repository_root / "install/so101_demo_py/lib").glob(
            "python*/site-packages/so101-demo-py.egg-link"
        )
    )
    if (
        Path(module_import_path).absolute() != expected_module.absolute()
        or Path(console_path).absolute() != expected_console.absolute()
        or not build_package.is_symlink()
        or build_package.resolve() != source_package
        or len(egg_links) != 1
    ):
        raise CliError("PROVENANCE_INSTALLED_OVERLAY")
    egg_link = egg_links[0]
    try:
        target_line = egg_link.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, UnicodeError, IndexError) as error:
        raise CliError("PROVENANCE_INSTALLED_OVERLAY") from error
    target = Path(target_line)
    if not target.is_absolute():
        target = egg_link.parent / target
    expected_build_root = (repository_root / "build/so101_demo_py").resolve()
    if target.resolve() != expected_build_root:
        raise CliError("PROVENANCE_INSTALLED_OVERLAY")
    entry_points = expected_build_root / "so101_demo_py.egg-info/entry_points.txt"
    if (
        not entry_points.is_file()
        or entry_points.is_symlink()
        or not console_path.is_file()
        or console_path.is_symlink()
    ):
        raise CliError("PROVENANCE_CONSOLE_METADATA")
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    try:
        parser.read_string(entry_points.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, configparser.Error) as error:
        raise CliError("PROVENANCE_CONSOLE_METADATA") from error
    entry_point = "so101_demo.cli.mujoco_parallel_batch:main"
    if (
        "console_scripts" not in parser
        or parser["console_scripts"].get("so101_parallel_batch") != entry_point
    ):
        raise CliError("PROVENANCE_CONSOLE_METADATA")
    expected_wrapper = _expected_console_wrapper()
    try:
        console_bytes = console_path.read_bytes()
    except OSError as error:
        raise CliError("PROVENANCE_CONSOLE_CONTENT") from error
    if console_bytes != expected_wrapper:
        raise CliError("PROVENANCE_CONSOLE_CONTENT")
    source_tree = source_hash(source_package)
    build_tree = source_hash(build_package.resolve())
    if build_tree != source_tree:
        raise CliError("PROVENANCE_INSTALLED_BYTES")
    return {
        "module_import_path": str(expected_module),
        "module_import_sha256": _sha256(expected_module),
        "source_module_tree_sha256": source_tree,
        "installed_module_tree_path": str(build_package),
        "installed_module_tree_sha256": build_tree,
        "installed_egg_link_path": str(egg_link),
        "installed_egg_link_sha256": _sha256(egg_link),
        "installed_entry_points_path": str(entry_points),
        "installed_entry_points_sha256": _sha256(entry_points),
    }


def _expected_console_wrapper() -> bytes:
    """Return the frozen setuptools wrapper for the reviewed entry point."""

    return b"""#!/usr/bin/python3
# EASY-INSTALL-ENTRY-SCRIPT: 'so101-demo-py','console_scripts','so101_parallel_batch'
import re
import sys

# for compatibility with easy_install; see #2198
__requires__ = 'so101-demo-py'

try:
    from importlib.metadata import distribution
except ImportError:
    try:
        from importlib_metadata import distribution
    except ImportError:
        from pkg_resources import load_entry_point


def importlib_load_entry_point(spec, group, name):
    dist_name, _, _ = spec.partition('==')
    matches = (
        entry_point
        for entry_point in distribution(dist_name).entry_points
        if entry_point.group == group and entry_point.name == name
    )
    return next(matches).load()


globals().setdefault('load_entry_point', importlib_load_entry_point)


if __name__ == '__main__':
    sys.argv[0] = re.sub(r'(-script\\.pyw?|\\.exe)?$', '', sys.argv[0])
    sys.exit(load_entry_point('so101-demo-py', 'console_scripts', 'so101_parallel_batch')())
"""


def prepare_batch(argv=None, *, provenance_verifier=verify_provenance) -> PreparedBatch:
    options = build_parser().parse_args(argv)
    evidence_root = _absolute("evidence_root", options.evidence_root)
    if options.resume:
        try:
            root_info = evidence_root.lstat()
        except OSError as error:
            raise CliError("RECOVERY_BATCH_EVIDENCE_ROOT_MISSING") from error
        if (
            evidence_root.is_symlink()
            or not stat.S_ISDIR(root_info.st_mode)
            or root_info.st_uid != os.getuid()
            or stat.S_IMODE(root_info.st_mode) != 0o700
        ):
            raise CliError("RECOVERY_BATCH_EVIDENCE_ROOT_INVALID")
        if (evidence_root / "aggregate_results.json").exists():
            raise CliError("RECOVERY_BATCH_ALREADY_FINALIZED")
    elif evidence_root.exists() or evidence_root.is_symlink():
        raise CliError("DUPLICATE_BATCH_EVIDENCE_ROOT")
    try:
        mode = RunMode(options.run_mode)
    except ValueError as error:
        raise CliError("UNKNOWN_RUN_MODE") from error
    worker_count = _integer("worker_count", options.worker_count)
    max_points = _integer("max_points_per_worker", options.max_points_per_worker)
    catalog, catalog_sha = _catalog(options.points)
    supplied = tuple(options.point_id)
    if len(supplied) != len(set(supplied)):
        raise CliError("DUPLICATE_POINT_ID")
    unknown = set(supplied) - set(catalog)
    if unknown:
        raise CliError(f"UNKNOWN_POINT_ID: {sorted(unknown)!r}")
    selected = tuple(point_id for point_id in catalog if not supplied or point_id in supplied)
    selection_payload = json.dumps(list(selected), separators=(",", ":")).encode("utf-8")
    selection_sha = hashlib.sha256(selection_payload).hexdigest()
    config_path = options.config.resolve()
    config = load_parallel_runtime_config(config_path)
    (
        live_headroom_evidence,
        live_headroom_acceptance,
        live_headroom_current_provenance,
        live_headroom_verification,
    ) = _prepare_live_headroom(options, config, worker_count)
    if options.yolo_weights_sha256 != config.yolo_weights_sha256:
        raise CliError("YOLO_HASH_MISMATCH")
    if options.grounded_manifest_sha256 != config.grounded_sam_manifest_sha256:
        raise CliError("GROUNDED_HASH_MISMATCH")
    if options.broker_image != _BROKER_IMAGE:
        raise CliError("BROKER_IMAGE_MISMATCH")
    try:
        request = BatchRequest(
            options.batch_id,
            mode,
            selected,
            worker_count,
            max_points,
            evidence_root,
        )
    except ContractError as error:
        message = str(error)
        if "INSUFFICIENT_CAPACITY" in message:
            raise CliError(f"INSUFFICIENT_CAPACITY: {message}") from error
        raise CliError(message) from error
    inputs = {
        "points": options.points.resolve(),
        "config": config_path,
        "catalog_sha256": catalog_sha,
        "broker_image": options.broker_image,
        "yolo_weights": options.yolo_weights,
        "yolo_weights_sha256": options.yolo_weights_sha256,
        "grounded_root": options.grounded_root,
        "grounded_manifest_sha256": options.grounded_manifest_sha256,
    }
    try:
        provenance = provenance_verifier(inputs)
    except CliError:
        raise
    except Exception as error:
        raise CliError("PROVENANCE_VERIFICATION_FAILED") from error
    if not isinstance(provenance, Mapping) or not provenance:
        raise CliError("PROVENANCE_VERIFICATION_FAILED")
    manifest = {
        "schema_version": 1,
        "batch_id": request.batch_id,
        "run_mode": request.run_mode.value,
        "selected_point_ids": list(selected),
        "selection_sha256": selection_sha,
        "catalog_sha256": catalog_sha,
        "worker_count": worker_count,
        "max_points_per_worker": max_points,
        "evidence_root": str(evidence_root),
        "provenance": dict(provenance),
        "live_headroom": (
            None
            if live_headroom_verification is None
            else {
                "evidence_path": str(live_headroom_evidence),
                "acceptance_path": str(live_headroom_acceptance),
                "current_provenance_paths": {
                    name: str(path)
                    for name, path in sorted(
                        live_headroom_current_provenance.items()
                    )
                },
                "verification": dict(live_headroom_verification),
            }
        ),
    }
    if options.resume:
        existing = _read_existing_json(
            evidence_root / "batch_manifest.json", label="BATCH_MANIFEST"
        )
        if existing != manifest:
            raise CliError("RECOVERY_BATCH_MANIFEST_MISMATCH")
    return PreparedBatch(
        request,
        config,
        config_path,
        options.points.resolve(),
        catalog,
        catalog_sha,
        selection_sha,
        options.broker_image,
        options.yolo_weights,
        options.yolo_weights_sha256,
        options.grounded_root,
        options.grounded_manifest_sha256,
        dict(provenance),
        manifest,
        dict(inputs),
        provenance_verifier,
        live_headroom_evidence,
        live_headroom_acceptance,
        dict(live_headroom_current_provenance),
        live_headroom_verification,
        options.resume,
    )


def _identity(lease, mode):
    value = {
        "batch_id": lease.batch_id,
        "coordinator_epoch": lease.coordinator_epoch,
        "worker_id": lease.worker_id,
        "worker_generation": lease.worker_generation,
        "point_id": lease.point_id,
        "lease_generation": lease.lease_generation,
    }
    if mode is RunMode.EXECUTE:
        return AttemptIdentity(**value, attempt_id=lease.attempt_id)
    return ValidationIdentity(**value, validation_id=lease.attempt_id)


class _ArtifactResults:
    """Produce reviewed Task 4 artifacts for the Worker and verify recovery receipts."""

    def __init__(self, worker_roots: Mapping[str, Path], mode: RunMode):
        self.worker_roots = {key: Path(value) for key, value in worker_roots.items()}
        self.mode = mode
        self._workspaces = {}

    @staticmethod
    def _key(lease):
        return tuple(getattr(lease, name) for name in (
            "batch_id", "coordinator_epoch", "worker_id", "worker_generation",
            "point_id", "attempt_id", "lease_generation",
        ))

    def reserve_workspace(self, lease, reset_receipt):
        if self.mode is RunMode.DRY_RUN:
            raise CliError("DRY_RUN_WORKSPACE_RESERVATION")
        reset_epoch = getattr(reset_receipt, "reset_epoch", None)
        completed = getattr(reset_receipt, "reset_completed_monotonic_s", None)
        session = getattr(reset_receipt, "simulation_session_id", None)
        simulation_time = getattr(reset_receipt, "simulation_time_s", None)
        if (not isinstance(reset_epoch, str) or not reset_epoch
                or isinstance(completed, bool) or not isinstance(completed, (int, float))
                or not isinstance(session, str) or not session
                or isinstance(simulation_time, bool)
                or not isinstance(simulation_time, (int, float))):
            raise CliError("WORKSPACE_RESET_RECEIPT")
        identity = _identity(lease, self.mode)
        cls = AttemptWorkspace if self.mode is RunMode.EXECUTE else ValidationWorkspace
        workspace = cls.create(
            self.worker_roots[lease.worker_id], identity,
            reset_epoch=reset_epoch,
            source_stamp={
                "reset_completed_monotonic_s": float(completed),
                "simulation_session_id": session,
                "simulation_time_s": float(simulation_time),
            },
            run_mode=self.mode,
        )
        key = self._key(lease)
        prior = self._workspaces.setdefault(key, workspace)
        if prior.path != workspace.path or prior._metadata != workspace._metadata:
            raise CliError("WORKSPACE_IDENTITY_MISMATCH")
        return True

    def workspace(self, lease):
        try:
            return self._workspaces[self._key(lease)]
        except KeyError as error:
            raise CliError("WORKSPACE_NOT_RESERVED") from error

    def _seal(self, lease, decision):
        identity = _identity(lease, self.mode)
        if self.mode is RunMode.DRY_RUN:
            workspace = ValidationWorkspace.create(
                self.worker_roots[lease.worker_id], identity,
                reset_epoch="scheduler-only",
                source_stamp={"coordinator_epoch": lease.coordinator_epoch},
                run_mode=self.mode,
            )
        else:
            try:
                workspace = self._workspaces[self._key(lease)]
            except KeyError as error:
                raise CliError("WORKSPACE_NOT_RESERVED") from error
        if (
            self.mode is RunMode.PLAN_ONLY
            and decision.status is ValidationStatus.VALIDATION_PASSED
        ):
            segments = getattr(decision, "segment_receipts", None)
            if not isinstance(segments, tuple) or not segments:
                raise CliError("PLANNING_EVIDENCE_MISSING")
            workspace.write_json(
                "planning/segment-receipts.json",
                {
                    "schema_version": 1,
                    "segment_count": len(segments),
                    "segments": [
                        {
                            "state": getattr(
                                getattr(segment, "state", None),
                                "value",
                                str(getattr(segment, "state", "")),
                            ),
                            "start_state_present": getattr(
                                segment, "start_state", None
                            ) is not None,
                            "terminal_state_present": getattr(
                                segment, "terminal_state", None
                            ) is not None,
                            "plan_present": getattr(segment, "plan", None) is not None,
                            "before_scene_present": getattr(
                                segment, "before_scene", None
                            ) is not None,
                            "after_scene_present": getattr(
                                segment, "after_scene", None
                            ) is not None,
                        }
                        for segment in segments
                    ],
                },
            )
        name = "attempt-result.json" if self.mode is RunMode.EXECUTE else "validation-result.json"
        workspace.write_json(
            name,
            {
                "status": decision.status.value,
                "reason": decision.reason,
                "physical_action_proven_absent": decision.physical_action_proven_absent,
            },
        )
        return str(workspace.seal().path)

    def seal_attempt(self, lease, decision):
        if self.mode is not RunMode.EXECUTE:
            raise CliError("ARTIFACT_MODE")
        return self._seal(lease, decision)

    def seal_validation(self, lease, decision):
        if self.mode is RunMode.EXECUTE:
            raise CliError("ARTIFACT_MODE")
        return self._seal(lease, decision)

    def write_recovery_receipt(self, lease, *, succeeded, generation, **_kwargs):
        if generation != lease.worker_generation:
            raise CliError("RECOVERY_GENERATION")
        return write_recovery_receipt(
            self.worker_roots[lease.worker_id], _identity(lease, self.mode), succeeded=succeeded
        )

    def verify_recovery_receipt(self, location, lease, *, succeeded, generation, **_kwargs):
        try:
            path = Path(location)
            path.relative_to(self.worker_roots[lease.worker_id])
            document = json.loads(path.read_text(encoding="utf-8"))
            return (
                path.is_file()
                and not path.is_symlink()
                and document["identity"] == asdict(_identity(lease, self.mode))
                and document["succeeded"] is succeeded
                and generation == lease.worker_generation
            )
        except (OSError, ValueError, KeyError, TypeError):
            return False


class RosWorkerRuntimePorts(_ConcreteRosWorkerRuntimePorts):
    """Production F20 ports with an explicit process-free test injection seam."""

    def __init__(
        self,
        resources,
        *,
        catalog=None,
        config=None,
        mode=RunMode.PLAN_ONLY,
        side_effects: Mapping[str, Callable] | None = None,
        workspace_provider=None,
        authorize=None,
        broker_generation=None,
    ):
        supplied = dict(side_effects or {})
        unknown = set(supplied) - self.REQUIRED
        if unknown:
            raise CliError(f"UNKNOWN_RUNTIME_PORT: {sorted(unknown)!r}")
        super().__init__(
            resources,
            catalog={} if catalog is None else catalog,
            config=config,
            mode=mode,
            broker_generation=broker_generation,
            dependencies={
                "workspace_provider": workspace_provider,
                "authorize": authorize,
            },
        )
        self.side_effects = supplied

    def kwargs(self):
        concrete = super().kwargs()
        concrete.update(self.side_effects)
        return concrete


def _jsonable(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _lease_wire(lease):
    if lease is None:
        return None
    return {
        name: getattr(lease, name)
        for name in (
            "batch_id", "coordinator_epoch", "worker_id", "worker_generation",
            "point_id", "attempt_id", "lease_generation",
        )
    }


_RPC_PAYLOAD_FIELDS = {
    "current_broker": set(),
    "register_worker": {"generation", "recovery_deadline_monotonic_s"},
    "grant_lease": {"generation"},
    "record_recovery": {
        "generation", "succeeded", "fenced", "owned_processes_stopped",
        "controllers_stopped", "readmitted", "recovery_deadline_monotonic_s",
    },
    "replace_resources": {"expected_generation"},
    "heartbeat": set(),
    "ack_lease": set(),
    "ack_attempt_started": {"gate_summary"},
    "ack_validation_started": {"gate_summary"},
    "begin_finalizing": set(),
    "commit_result": {"location"},
    "commit_validation": {"location"},
}


def _validate_rpc_payload(payload):
    if type(payload) is not dict or type(payload.get("operation")) is not str:
        raise CliError("RPC_PAYLOAD_SCHEMA")
    operation = payload["operation"]
    fields = _RPC_PAYLOAD_FIELDS.get(operation)
    if fields is None or set(payload) != {"operation", *fields}:
        raise CliError("RPC_PAYLOAD_SCHEMA")
    values = {name: payload[name] for name in fields}
    integer_fields = {"generation", "expected_generation"}
    if any(type(values[name]) is not int or values[name] <= 0 for name in fields & integer_fields):
        raise CliError("RPC_PAYLOAD_TYPE")
    if "location" in fields and (
        not isinstance(values["location"], str) or not values["location"]
    ):
        raise CliError("RPC_PAYLOAD_TYPE")
    if "gate_summary" in fields and type(values["gate_summary"]) is not dict:
        raise CliError("RPC_PAYLOAD_TYPE")
    if operation == "register_worker":
        deadline = values["recovery_deadline_monotonic_s"]
        if deadline is not None and (
            isinstance(deadline, bool) or not isinstance(deadline, (int, float))
        ):
            raise CliError("RPC_PAYLOAD_TYPE")
    if operation == "record_recovery":
        if any(type(values[name]) is not bool for name in (
            "succeeded", "fenced", "owned_processes_stopped",
            "controllers_stopped", "readmitted",
        )):
            raise CliError("RPC_PAYLOAD_TYPE")
        deadline = values["recovery_deadline_monotonic_s"]
        if isinstance(deadline, bool) or not isinstance(deadline, (int, float)):
            raise CliError("RPC_PAYLOAD_TYPE")
    return payload


def _validate_broker_authority_payload(payload):
    if type(payload) is not dict or type(payload.get("operation")) is not str:
        raise CliError("BROKER_RPC_PAYLOAD_SCHEMA")
    expected = {
        "authenticate_broker_message": {"operation", "message"},
        "authorize_inference": {"operation", "request", "snapshot"},
        "broker_health_down": {
            "operation", "outcome", "request_id", "reason",
        },
    }.get(payload["operation"])
    if expected is None or set(payload) != expected:
        raise CliError("BROKER_RPC_PAYLOAD_SCHEMA")
    if payload["operation"] in {
        "authenticate_broker_message", "authorize_inference"
    } and any(
        type(payload[name]) is not dict for name in expected - {"operation"}
    ):
        raise CliError("BROKER_RPC_PAYLOAD_TYPE")
    if payload["operation"] == "broker_health_down":
        if payload["outcome"] not in {
            "INFRA_ERROR", "QUEUE_TIMEOUT", "INFERENCE_TIMEOUT"
        } or any(
            not isinstance(payload[name], str) or not payload[name]
            for name in ("request_id", "reason")
        ):
            raise CliError("BROKER_RPC_PAYLOAD_TYPE")
    return payload


class _CoordinatorRpcProxy:
    """Worker-side authenticated proxy with retry-safe idempotency identities."""

    def __init__(self, socket_path, token_path, *, worker_id, generation, mode, coordinator_epoch):
        self.client = UnixRpcClient(socket_path)
        self.token_path = token_path
        self.token = self.token_path.read_text(encoding="ascii")
        self.worker_id = worker_id
        self.generation = generation
        self.mode = mode
        self.coordinator_epoch = coordinator_epoch
        self._lease = None
        self._sequence = 0

    @property
    def request(self):
        return SimpleNamespace(run_mode=self.mode)

    def _call(self, operation, *, lease=None, request_key=None, **values):
        self._sequence += 1
        key = request_key or f"{operation}-{self.worker_id}-{self.generation}-{self._sequence}"
        message = {
            "schema_version": 1,
            "kind": "coordinator_call",
            "coordinator_epoch": values.pop("coordinator_epoch", None)
            or (lease.coordinator_epoch if lease is not None else self.coordinator_epoch),
            "worker_id": self.worker_id,
            "worker_generation": self.generation,
            "lease": _lease_wire(lease),
            "request_id": f"rpc-{self.worker_id}-{self._sequence}",
            "idempotency_key": key,
            "token": self.token,
            "payload": {"operation": operation, **_jsonable(values)},
        }
        try:
            response = self.client.call(message)
        except (OSError, RuntimeError):
            # One retry with byte-identical request safely covers a dropped ACK.
            response = self.client.call(message)
        return response["payload"]

    @property
    def token_path(self):
        return getattr(self, "_token_path")

    @token_path.setter
    def token_path(self, value):
        self._token_path = Path(value)

    def register_worker(self, worker_id, *, generation, recovery_deadline_monotonic_s=None):
        value = self._call(
            "register_worker",
            generation=generation,
            recovery_deadline_monotonic_s=recovery_deadline_monotonic_s,
        )
        if generation != self.generation:
            self.generation = generation
        return _worker_ack(value)

    def grant_lease(self, worker_id, *, generation, request_key=None):
        value = self._call("grant_lease", generation=generation, request_key=request_key)
        if type(value) is not dict or set(value) != {
            "lease", "lease_grant_paused", "recovery_deadline_monotonic_s",
        }:
            raise CliError("LEASE_GRANT_OUTCOME_SCHEMA")
        lease = value["lease"]
        paused = value["lease_grant_paused"]
        deadline = value["recovery_deadline_monotonic_s"]
        if paused is True:
            if (lease is not None or isinstance(deadline, bool)
                    or not isinstance(deadline, (int, float))):
                raise CliError("LEASE_GRANT_OUTCOME_SCHEMA")
            raise LeaseGrantPaused("BROKER_RECOVERING")
        if paused is not False or deadline is not None:
            raise CliError("LEASE_GRANT_OUTCOME_SCHEMA")
        self._lease = None if lease is None else LeaseIdentity(**lease)
        return self._lease

    def ack_lease(self, lease, *, request_key):
        return _worker_ack(self._call("ack_lease", lease=lease, request_key=request_key))

    def ack_attempt_started(self, lease, *, request_key, gate_summary=None):
        return _worker_ack(self._call(
            "ack_attempt_started", lease=lease, request_key=request_key, gate_summary=gate_summary
        ))

    def ack_validation_started(self, lease, *, request_key, gate_summary=None):
        return _worker_ack(self._call(
            "ack_validation_started", lease=lease, request_key=request_key, gate_summary=gate_summary
        ))

    def begin_finalizing(self, lease, *, request_key):
        return _worker_ack(self._call("begin_finalizing", lease=lease, request_key=request_key))

    def heartbeat(self, lease):
        return LeaseIdentity(**self._call("heartbeat", lease=lease))

    def authorize_local(self, request):
        lease = self._lease
        if lease is None:
            return False
        execution_id = (
            request.attempt_id
            if request.execution_kind is ExecutionKind.ATTEMPT
            else request.validation_id
        )
        expected = (
            lease.batch_id,
            lease.coordinator_epoch,
            lease.worker_id,
            lease.worker_generation,
            lease.point_id,
            lease.lease_generation,
            lease.attempt_id,
        )
        actual = (
            request.batch_id,
            request.coordinator_epoch,
            request.worker_id,
            request.worker_generation,
            request.point_id,
            request.lease_generation,
            execution_id,
        )
        if actual != expected:
            return False
        try:
            acknowledged = self.heartbeat(lease)
        except Exception:
            return False
        return _lease_wire(acknowledged) == _lease_wire(lease)

    def commit_result(self, lease, location, *, request_key):
        value = self._call(
            "commit_result", lease=lease, request_key=request_key, location=location
        )
        from so101_demo.parallel_batch.contracts import AttemptStatus
        value["status"] = AttemptStatus(value["status"])
        return value

    def commit_validation(self, lease, location, *, request_key):
        value = self._call(
            "commit_validation", lease=lease, request_key=request_key, location=location
        )
        from so101_demo.parallel_batch.contracts import ValidationStatus
        value["status"] = ValidationStatus(value["status"])
        return value

    def record_recovery(self, worker_id, **values):
        generation = values["generation"]
        value = self._call(
            "record_recovery", lease=None, generation=generation, **{
                key: item for key, item in values.items() if key != "generation"
            }
        )
        if generation != self.generation:
            self.generation = generation
        return _worker_ack(value)

    def replace_resources(self, worker_id, *, expected_generation):
        value = self._call(
            "replace_resources",
            lease=None,
            expected_generation=expected_generation,
        )
        return _resource_from_dict(value)

    def current_broker(self):
        if self._lease is None:
            raise CliError("BROKER_DISCOVERY_ACTIVE_LEASE_REQUIRED")
        value = self._call("current_broker", lease=self._lease)
        fields = {
            "healthy", "broker_generation", "broker_socket_path",
            "recovery_deadline_monotonic_s",
        }
        if type(value) is not dict or set(value) != fields:
            raise CliError("BROKER_AUTHORITY_SCHEMA")
        healthy = value["healthy"]
        generation = value["broker_generation"]
        endpoint = value["broker_socket_path"]
        deadline = value["recovery_deadline_monotonic_s"]
        if type(healthy) is not bool:
            raise CliError("BROKER_AUTHORITY_SCHEMA")
        if healthy:
            if (
                type(generation) is not int
                or generation <= 0
                or not isinstance(endpoint, str)
                or not Path(endpoint).is_absolute()
                or deadline is not None
            ):
                raise CliError("BROKER_AUTHORITY_SCHEMA")
        if not healthy and (
            generation is not None
            or endpoint is not None
            or isinstance(deadline, bool)
            or not isinstance(deadline, (int, float))
        ):
            raise CliError("BROKER_AUTHORITY_SCHEMA")
        return value


class _WorkerControlProxy:
    """Parent-side authenticated control of one live Worker shutdown path."""

    def __init__(self, socket_path, token_path, *, worker_id, generation,
                 coordinator_epoch, deadline_s, orphan_manifest=None,
                 identity_probe=None, signal_process=os.kill):
        self.socket_path = Path(socket_path)
        self.client = UnixRpcClient(self.socket_path, deadline_s=deadline_s)
        self.token = Path(token_path).read_text(encoding="ascii")
        self.worker_id = worker_id
        self.generation = generation
        self.coordinator_epoch = coordinator_epoch
        self.deadline_s = deadline_s
        self.orphan_manifest = (
            None if orphan_manifest is None else Path(orphan_manifest)
        )
        if identity_probe is None:
            from so101_demo.runtime.task_stack import _linux_process_identity
            identity_probe = _linux_process_identity
        self._identity_probe = identity_probe
        self._signal_process = signal_process
        self._sequence = 0

    def _orphan_identities(self):
        path = self.orphan_manifest
        if path is None or not path.exists():
            return ()
        if (
            path.is_symlink() or not path.is_file()
            or path.stat().st_uid != os.getuid()
            or stat.S_IMODE(path.stat().st_mode) != 0o600
        ):
            raise CliError("WORKER_CHILD_MANIFEST_IDENTITY")
        document = json.loads(path.read_text(encoding="utf-8"))
        if type(document) is not dict or set(document) != {"schema_version", "processes"}:
            raise CliError("WORKER_CHILD_MANIFEST_SCHEMA")
        if document["schema_version"] != 1 or type(document["processes"]) is not list:
            raise CliError("WORKER_CHILD_MANIFEST_SCHEMA")
        identities = []
        for value in document["processes"]:
            if type(value) is not dict or set(value) != {
                "role", "pid", "pgid", "cmdline", "start_time_ticks"
            }:
                raise CliError("WORKER_CHILD_MANIFEST_SCHEMA")
            identity = OwnedProcessIdentity(
                value["role"], value["pid"], value["pgid"],
                tuple(value["cmdline"]), value["start_time_ticks"],
            )
            identities.append(identity)
        return tuple(identities)

    def _recover_orphans(self):
        identities = self._orphan_identities()

        def matches(identity):
            try:
                return self._identity_probe(identity.pid) == (
                    identity.pgid, identity.cmdline, identity.start_time_ticks
                )
            except (OSError, ProcessLookupError, RuntimeError):
                return False

        for identity in identities:
            if not matches(identity):
                return False
        deadline = time.monotonic() + self.deadline_s / 2.0
        for identity in identities:
            try:
                self._signal_process(identity.pid, signal.SIGINT)
            except ProcessLookupError:
                continue
        while identities and time.monotonic() < deadline:
            identities = tuple(
                identity for identity in identities
                if matches(identity)
            )
            if identities:
                time.sleep(0.01)
        for identity in identities:
            if not matches(identity):
                return False
            self._signal_process(identity.pid, signal.SIGTERM)
        deadline = time.monotonic() + self.deadline_s / 2.0
        while identities and time.monotonic() < deadline:
            identities = tuple(identity for identity in identities if matches(identity))
            if identities:
                time.sleep(0.01)
        return not identities

    def call(self, operation):
        if operation not in {
            "stop", "cancel_motion", "confirm_no_controller_goal", "recover"
        }:
            raise CliError("WORKER_CONTROL_OPERATION")
        # A cleanly exited Worker has already run its own finally path.
        if not self.socket_path.exists():
            identities = self._orphan_identities()
            if not identities:
                return True
            return operation == "recover" and self._recover_orphans()
        self._sequence += 1
        message = {
            "schema_version": 1,
            "kind": "worker_call",
            "coordinator_epoch": self.coordinator_epoch,
            "worker_id": f"{self.worker_id}-control",
            "worker_generation": self.generation,
            "lease": None,
            "request_id": f"control-{self.worker_id}-{self._sequence}",
            "idempotency_key": f"control-{operation}-{self._sequence}",
            "token": self.token,
            "payload": {"operation": operation},
        }
        value = self.client.call(message)["payload"]
        return type(value) is dict and value == {"completed": True}


def _worker_ack(value):
    lease = value.get("lease")
    return SimpleNamespace(
        state=WorkerState(value["state"]),
        generation=value["generation"],
        lease=None if lease is None else LeaseIdentity(**lease),
    )


def _resource_from_dict(value):
    paths = {
        "render_context_namespace", "ros_home", "ros_log_dir", "temp_dir",
        "socket_namespace", "socket_path", "worker_root",
    }
    normalized = dict(value)
    for name in paths:
        normalized[name] = Path(normalized[name])
    return WorkerResources(**normalized)


def _resource_manifest_from_dict(value):
    fields = {
        "schema_version", "mode", "backend", "evidence_root",
        "requested_worker_count", "worker_count", "admission",
        "domain_claim_scope", "domain_claims", "process_scan",
        "live_headroom_evidence", "workers",
    }
    if type(value) is not dict or set(value) != fields:
        raise CliError("RECOVERY_RESOURCE_MANIFEST_SCHEMA")
    admission = value["admission"]
    if type(admission) is not dict or set(admission) != {
        "admitted", "observed", "required", "required_live_headroom_ratio", "failures",
    }:
        raise CliError("RECOVERY_RESOURCE_MANIFEST_SCHEMA")
    try:
        observed = ResourceSnapshot(**admission["observed"])
        required = ResourceThresholds(**admission["required"])
        restored_admission = ResourceAdmission(
            admission["admitted"],
            observed,
            required,
            admission["required_live_headroom_ratio"],
            tuple(admission["failures"]),
        )
        return ResourceManifest(
            schema_version=value["schema_version"],
            mode=value["mode"],
            backend=value["backend"],
            evidence_root=Path(value["evidence_root"]),
            requested_worker_count=value["requested_worker_count"],
            worker_count=value["worker_count"],
            admission=restored_admission,
            domain_claim_scope=value["domain_claim_scope"],
            domain_claims=tuple(value["domain_claims"]),
            process_scan=value["process_scan"],
            live_headroom_evidence=value["live_headroom_evidence"],
            workers=tuple(_resource_from_dict(item) for item in value["workers"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise CliError("RECOVERY_RESOURCE_MANIFEST_SCHEMA") from error


class _WorkerBrokerProxy:
    def __init__(
        self, coordinator: _CoordinatorRpcProxy, endpoint, resources, config,
        *, broker_generation, perception_runner=None,
        client_factory=UnixRpcClient, clock=time.monotonic, sleep=time.sleep,
    ):
        self.coordinator = coordinator
        self._client_factory = client_factory
        self.client = client_factory(
            endpoint,
            deadline_s=config.executing_hard_timeout_s,
            max_frame_bytes=config.broker_max_frame_bytes,
        )
        self.resources = resources
        self.config = config
        if type(broker_generation) is not int or broker_generation <= 0:
            raise CliError("BROKER_GENERATION_AUTHORITY")
        self.broker_generation = broker_generation
        self.perception_runner = perception_runner
        self._clock = clock
        self._sleep = sleep
        self._sequence = 0

    def cancel_generation(self, worker_id, generation):
        self._refresh_broker(wait_until_healthy=True)
        self._sequence += 1
        key = f"broker-cancel-{worker_id}-{generation}"
        message = self._message(
            key,
            None,
            {
                "operation": "cancel_generation",
                "worker_id": worker_id,
                "worker_generation": generation,
            },
        )
        return self._call(message)["cancelled"]

    def _refresh_broker(self, *, wait_until_healthy):
        deadline = self._clock() + self.config.broker_recovery_timeout_s
        while True:
            authority = self.coordinator.current_broker()
            if authority["healthy"]:
                generation = authority["broker_generation"]
                if generation < self.broker_generation:
                    raise CliError("BROKER_GENERATION_ROLLBACK")
                self.broker_generation = generation
                self.client = self._client_factory(
                    authority["broker_socket_path"],
                    deadline_s=self.config.executing_hard_timeout_s,
                    max_frame_bytes=self.config.broker_max_frame_bytes,
                )
                return generation
            recovery_deadline = authority["recovery_deadline_monotonic_s"]
            deadline = min(deadline, recovery_deadline)
            if not wait_until_healthy or self._clock() >= deadline:
                raise CliError("BROKER_UNHEALTHY")
            self._sleep(min(0.01, max(0.0, deadline - self._clock())))

    def _message(self, key, lease, payload):
        return {
            "schema_version": 1,
            "kind": "broker_call",
            "coordinator_epoch": self.coordinator.coordinator_epoch,
            "worker_id": self.coordinator.worker_id,
            "worker_generation": self.coordinator.generation,
            "lease": _lease_wire(lease),
            "request_id": key,
            "idempotency_key": key,
            "token": self.coordinator.token,
            "payload": payload,
        }

    def _call(self, message):
        try:
            return self.client.call(message)["payload"]
        except (OSError, RuntimeError):
            return self.client.call(message)["payload"]

    def request_model(
        self,
        lease,
        execution_kind,
        *,
        snapshot,
        start_event_id,
        start_event_type,
        reset_epoch,
    ):
        if self.perception_runner is not None:
            return self.perception_runner(
                lease,
                execution_kind,
                snapshot,
                lambda model_id, before_send: self._request_one(
                    lease,
                    execution_kind,
                    model_id=model_id,
                    snapshot=snapshot,
                    start_event_id=start_event_id,
                    start_event_type=start_event_type,
                    reset_epoch=reset_epoch,
                    before_send=before_send,
                ),
            )
        return self._request_one(
            lease,
            execution_kind,
            model_id=self.config.yolo_model_id,
            snapshot=snapshot,
            start_event_id=start_event_id,
            start_event_type=start_event_type,
            reset_epoch=reset_epoch,
        )

    def _request_one(
        self, lease, execution_kind, *, model_id, snapshot, start_event_id,
        start_event_type, reset_epoch, before_send=None,
    ):
        request_generation = self._refresh_broker(wait_until_healthy=False)
        self._sequence += 1
        request_id = f"{lease.attempt_id}-{model_id}"
        identity = {
            "request_id": request_id,
            "model_id": model_id,
            "execution_kind": execution_kind,
            "batch_id": lease.batch_id,
            "coordinator_epoch": lease.coordinator_epoch,
            "worker_id": lease.worker_id,
            "worker_generation": lease.worker_generation,
            "point_id": lease.point_id,
            "lease_generation": lease.lease_generation,
            "reset_epoch": reset_epoch,
            "image_timestamp_s": snapshot.source_stamp_ns / 1_000_000_000.0,
            "input_relative_path": str(
                snapshot.path.relative_to(self.resources.worker_root.parent)
            ),
            "input_sha256": snapshot.input_sha256,
        }
        if execution_kind is ExecutionKind.ATTEMPT:
            identity["attempt_id"] = lease.attempt_id
        else:
            identity["validation_id"] = lease.attempt_id
        request = InferenceRequest(**identity)
        if before_send is not None:
            before_send(request)
        from so101_demo.runtime.parallel_perception_runtime import Snapshot

        broker_snapshot = Snapshot(
            snapshot.shape,
            snapshot.source_stamp_ns,
            snapshot.source_frame_id,
            start_event_id,
            start_event_type,
            NormalizedInferenceResponseIdentity.from_request(request),
        )
        key = f"broker-{request_id}"
        message = self._message(
            key,
            lease,
            {
                "operation": "infer",
                "request": BrokerTransport.serialize_request(request),
                "snapshot": BrokerTransport.serialize_snapshot(broker_snapshot),
            },
        )
        value = self._call(message)
        current_generation = self._refresh_broker(wait_until_healthy=False)
        if (
            value.get("broker_generation") != request_generation
            or value.get("broker_generation") != current_generation
        ):
            raise CliError("BROKER_GENERATION_CHANGED")
        return BrokerResponse(
            request,
            value["broker_generation"],
            ModelOutcome(value["outcome"]),
            value["candidate"],
            value["reason"],
            value["queued_monotonic_s"],
            value["queue_deadline_monotonic_s"],
            value["started_monotonic_s"],
            value["inference_deadline_monotonic_s"],
            value["completed_monotonic_s"],
        )


def _build_worker_from_spec(path, *, runtime_side_effects=None):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if type(document) is not dict or set(document) != {
        "schema_version", "batch_id", "run_mode", "config_path", "socket_path",
        "token_path", "coordinator_epoch", "resources", "broker_socket_path",
        "broker_generation", "catalog", "control_token_path",
        "control_socket_path", "shutdown_deadline_s", "max_frame_bytes",
    } or document["schema_version"] != 1:
        raise CliError("WORKER_SPEC_INVALID")
    if type(document["broker_generation"]) is not int or document["broker_generation"] <= 0:
        raise CliError("WORKER_SPEC_BROKER_GENERATION")
    resources = _resource_from_dict(document["resources"])
    mode = RunMode(document["run_mode"])
    config = load_parallel_runtime_config(Path(document["config_path"]))
    coordinator = _CoordinatorRpcProxy(
        document["socket_path"],
        document["token_path"],
        worker_id=resources.worker_id,
        generation=resources.generation,
        mode=mode,
        coordinator_epoch=document["coordinator_epoch"],
    )
    results = _ArtifactResults({resources.worker_id: resources.worker_root}, mode)
    runtime_kwargs = {}
    runtime_ports = None
    broker_proxy = None
    if mode is not RunMode.DRY_RUN:
        runtime_ports = RosWorkerRuntimePorts(
            resources,
            catalog=document["catalog"],
            config=config,
            mode=mode,
            side_effects=runtime_side_effects,
            workspace_provider=results.workspace,
            authorize=coordinator.authorize_local,
            broker_generation=document["broker_generation"],
        )
        runtime_kwargs = runtime_ports.kwargs()
        runtime_kwargs["reserve_workspace"] = results.reserve_workspace
        # A stable slot replacement is represented by the next private Worker
        # spec generation; it never reallocates ROS domains or directories.
        runtime_kwargs["replace_resources"] = coordinator.replace_resources
        broker_proxy = _WorkerBrokerProxy(
            coordinator, document["broker_socket_path"], resources, config,
            broker_generation=document["broker_generation"],
            perception_runner=runtime_ports.run_perception_chain,
        )

        def rebind(replacement):
            if runtime_ports.rebind_resources(replacement) is not True:
                return False
            broker_proxy.resources = replacement
            return True

        runtime_kwargs["rebind_resources"] = rebind
    runtime = build_worker_runtime(resources, mode, **runtime_kwargs)
    worker = ParallelWorker({
        "coordinator": coordinator,
        "broker": broker_proxy if mode is not RunMode.DRY_RUN else SimpleNamespace(
            request_model=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                CliError("DRY_RUN_BROKER_FORBIDDEN")
            ),
            cancel_generation=lambda *_args: True,
        ),
        "runtime": runtime,
        "results": results,
        "clock": time.monotonic,
        "config": config,
        "worker_id": resources.worker_id,
        "generation": resources.generation,
    })
    return worker, runtime


def _write_worker_results(resources, results):
    path = resources.worker_root / "worker-run-results.json"
    _write_json(path, {
        "schema_version": 1,
        "worker_id": resources.worker_id,
        "worker_generation": resources.generation,
        "results": [_jsonable(result) for result in results],
    })
    return path


def _worker_results_failed(results):
    """Classify only an unrecovered or nonterminal Worker result as fatal."""
    if not results:
        return True
    for result in results:
        if result.stopped_reason in {"POINT_TERMINAL", "NO_POINT"}:
            continue
        if (
            result.stopped_reason == "INITIAL_GATE_FAILED"
            and result.recovered is True
            and result.terminal_status in {
                AttemptStatus.INVALID,
                ValidationStatus.VALIDATION_INVALID,
            }
        ):
            continue
        return True
    return False


def _run_worker_spec(path, *, runtime_side_effects=None):
    worker, runtime = _build_worker_from_spec(
        path, runtime_side_effects=runtime_side_effects
    )
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    resources = _resource_from_dict(document["resources"])
    control_id = f"{resources.worker_id}-control"
    control_path = Path(document["control_socket_path"])
    control_authority = WorkerTokenAuthority(
        control_path.parent.parent,
        coordinator_epoch=document["coordinator_epoch"],
    )
    control_authority.load_token(
        control_id, resources.generation, Path(document["control_token_path"])
    )

    def control_handler(message):
        if message.get("kind") != "worker_call":
            raise CliError("WORKER_CONTROL_SCHEMA")
        payload = message["payload"]
        if type(payload) is not dict or set(payload) != {"operation"}:
            raise CliError("WORKER_CONTROL_SCHEMA")
        operation = payload["operation"]
        if operation not in {
            "stop", "cancel_motion", "confirm_no_controller_goal", "recover"
        }:
            raise CliError("WORKER_CONTROL_OPERATION")
        completed = runtime.shutdown_control(
            operation,
            deadline_monotonic_s=time.monotonic() + document["shutdown_deadline_s"],
        )
        if operation == "stop":
            worker.request_stop()
        return {"completed": completed}

    control_server = AuthenticatedUnixServer(
        control_path,
        control_authority,
        control_handler,
        deadline_s=document["shutdown_deadline_s"],
        max_frame_bytes=document["max_frame_bytes"],
    )
    control_thread = threading.Thread(target=control_server.serve_forever, daemon=True)
    control_thread.start()
    try:
        results = worker.run()
        _write_worker_results(resources, results)
        return int(_worker_results_failed(results))
    finally:
        try:
            runtime.shutdown_owned()
        finally:
            control_server.close()
            control_thread.join(timeout=1.0)


class ProductionBatchComposition:
    """Connect reviewed batch components; no result is synthesized by this layer."""

    def __init__(
        self,
        spec: PreparedBatch,
        **kwargs,
    ):
        self.worker_servers = []
        self._server_threads = []
        self.broker_authority_server = None
        self.allocator = None
        self.journal = None
        try:
            self._initialize(spec, **kwargs)
        except BaseException:
            self._release_partial()
            raise

    def _initialize(
        self,
        spec: PreparedBatch,
        *,
        resource_probe=None,
        claim_root: Path | None = None,
        runtime_side_effects_factory: Callable[[object], Mapping[str, Callable]] | None = None,
        broker_request_model=None,
        worker_launcher=None,
        supervisor=None,
        broker_command_builder=None,
        provenance_revalidator=None,
        broker_health_client_factory=UnixRpcClient,
        container_runner=subprocess.run,
        clock=time.monotonic,
        sleep=time.sleep,
    ):
        self.spec = spec
        self._clock = clock
        self._sleep = sleep
        self.supervisor = supervisor or ProcessSupervisor(
            spec.request.batch_id,
            manifest_path=spec.request.evidence_root / "owned-processes.json",
        )
        self._container_runner = container_runner
        self._uses_production_broker_container = broker_command_builder is None
        self.journal = None
        live_headroom_verifier = None
        if spec.request.worker_count == 3:
            if (
                spec.live_headroom_evidence is None
                or spec.live_headroom_acceptance is None
                or spec.live_headroom_verification is None
            ):
                raise CliError("THREE_WORKER_LIVE_EVIDENCE_REQUIRED")
            live_headroom_verifier = _live_headroom_verifier(
                spec.live_headroom_acceptance,
                spec.live_headroom_current_provenance,
            )
            try:
                current_headroom = live_headroom_verifier.verify(
                    spec.live_headroom_evidence,
                    config=spec.config,
                )
            except Exception as error:
                raise CliError("THREE_WORKER_LIVE_EVIDENCE_INVALID") from error
            if dict(current_headroom) != dict(spec.live_headroom_verification):
                raise CliError("THREE_WORKER_LIVE_EVIDENCE_CHANGED")
        self.allocator = WorkerResourceAllocator(
            spec.config,
            spec.request.evidence_root,
            probe=resource_probe,
            claim_root=claim_root,
            live_headroom_evidence=spec.live_headroom_evidence,
            live_headroom_verifier=live_headroom_verifier,
            batch_id=spec.request.batch_id,
        )
        if spec.resume:
            self.journal = CoordinatorJournal.create(
                spec.request.evidence_root / "coordinator", spec.request.batch_id
            )
            prior_processes = _read_existing_json(
                spec.request.evidence_root / "owned-processes.json",
                label="PROCESS_MANIFEST",
            )
            retire = getattr(self.supervisor, "retire_manifest", None)
            if not callable(retire) or retire(prior_processes) is not True:
                raise CliError("RECOVERY_PROCESS_FENCE_FAILED")
            resource_document = _read_existing_json(
                spec.request.evidence_root / "resource_manifest.json",
                label="RESOURCE_MANIFEST",
            )
            prior_manifest = _resource_manifest_from_dict(resource_document)
            self.resource_manifest = self.allocator.adopt_existing(prior_manifest)
            self._remove_stale_worker_sockets()
        else:
            self.resource_manifest = self.allocator.allocate(spec.request.worker_count)
            self.allocator.write_manifest()
        worker_roots = {
            worker.worker_id: worker.worker_root for worker in self.resource_manifest.workers
        }
        self.result_verifier = SealedResultAdapter(worker_roots, spec.request.run_mode)
        if self.journal is None:
            self.journal = CoordinatorJournal.create(
                spec.request.evidence_root / "coordinator", spec.request.batch_id
            )
        self.coordinator = BatchCoordinator(
            self.journal,
            spec.request,
            config=spec.config,
            result_port=self.result_verifier,
            clock=clock,
        )
        self.results = _ArtifactResults(worker_roots, spec.request.run_mode)
        self._recovered_worker_ids = None
        if spec.resume:
            self._recovered_worker_ids = self._readmit_recovered_slots()
            self.resource_manifest = self.allocator.manifest
        if broker_request_model is not None:
            raise CliError("IN_PROCESS_BROKER_FORBIDDEN")
        self._worker_children_reaped = False
        self.authority = WorkerTokenAuthority(
            spec.request.evidence_root,
            coordinator_epoch=self.journal.coordinator_epoch,
        )
        self._broker_command_builder = broker_command_builder
        self._broker_health_client_factory = broker_health_client_factory
        self._provenance_revalidator = (
            spec.provenance_verifier
            if provenance_revalidator is None
            else provenance_revalidator
        )
        self.broker_spec_path = None
        self.broker_authority_server = None
        self._broker_authority_thread = None
        self.broker_generation = (
            self._prior_broker_generation() if spec.resume else 0
        )
        self.broker_runtime_root = self.authority.ipc_root / "broker"
        self.broker_input_root = spec.request.evidence_root / "broker-inputs"
        self.broker_authority = None
        self.broker_socket_path = self.broker_runtime_root / "perception.sock"
        if spec.request.run_mode is not RunMode.DRY_RUN:
            if spec.resume:
                if not self.broker_input_root.is_dir() or self.broker_input_root.is_symlink():
                    raise CliError("RECOVERY_BROKER_INPUT_ROOT")
                prior_root = self._broker_runtime_for_generation(self.broker_generation)
                if (prior_root / "container.cid").exists():
                    self.broker_runtime_root = prior_root
                    self.broker_spec_path = prior_root / "broker-spec.json"
                    self._retire_broker_container(
                        runtime_root=prior_root,
                        generation=self.broker_generation,
                    )
            else:
                self.broker_input_root.mkdir(mode=0o700)
            self._prepare_broker_generation(self.broker_generation + 1)
        self.worker_specs = []
        self.worker_controls = []
        self._runtime_side_effects_factory = runtime_side_effects_factory
        self._worker_launcher = worker_launcher
        for resources in self.resource_manifest.workers:
            if (
                self._recovered_worker_ids is not None
                and resources.worker_id not in self._recovered_worker_ids
            ):
                continue
            token_path = self.authority.issue(resources.worker_id, resources.generation)
            control_id = f"{resources.worker_id}-control"
            control_token_path = self.authority.issue(control_id, resources.generation)
            control_socket_path = self.authority.ipc_root / f"{control_id}.sock"
            socket_path = self.authority.ipc_root / f"{resources.worker_id}.sock"
            server = AuthenticatedUnixServer(
                socket_path,
                self.authority,
                self._coordinator_handler,
                deadline_s=spec.config.heartbeat_timeout_s,
                max_frame_bytes=spec.config.broker_max_frame_bytes,
            )
            worker_spec = {
                "schema_version": 1,
                "batch_id": spec.request.batch_id,
                "run_mode": spec.request.run_mode.value,
                "config_path": str(spec.config_path),
                "socket_path": str(socket_path),
                "token_path": str(token_path),
                "control_token_path": str(control_token_path),
                "control_socket_path": str(control_socket_path),
                "shutdown_deadline_s": spec.config.heartbeat_timeout_s,
                "max_frame_bytes": spec.config.broker_max_frame_bytes,
                "coordinator_epoch": self.journal.coordinator_epoch,
                "broker_socket_path": str(self.broker_socket_path),
                "broker_generation": self.broker_generation or 1,
                "catalog": {
                    point_id: self.spec.catalog[point_id]
                    for point_id in self.spec.request.selected_point_ids
                },
                "resources": resources.to_dict(),
            }
            worker_path = resources.worker_root / (
                "worker-spec.json" if not spec.resume
                else f"worker-spec-e{self.journal.coordinator_epoch}-g{resources.generation}.json"
            )
            _write_json(worker_path, worker_spec)
            self.worker_specs.append(worker_path)
            self.worker_servers.append(server)
            self.worker_controls.append(_WorkerControlProxy(
                control_socket_path,
                control_token_path,
                worker_id=resources.worker_id,
                generation=resources.generation,
                coordinator_epoch=self.journal.coordinator_epoch,
                deadline_s=spec.config.heartbeat_timeout_s,
                orphan_manifest=resources.worker_root / "owned-runtime-processes.json",
            ))

    def _remove_stale_worker_sockets(self):
        """Remove only prior generation sockets after exact process fencing."""
        ipc_root = self.spec.request.evidence_root / "ipc"
        for worker in self.resource_manifest.workers:
            for name in (f"{worker.worker_id}.sock", f"{worker.worker_id}-control.sock"):
                path = ipc_root / name
                try:
                    info = path.lstat()
                except FileNotFoundError:
                    continue
                if (
                    not stat.S_ISSOCK(info.st_mode)
                    or info.st_uid != os.getuid()
                ):
                    raise CliError("RECOVERY_STALE_SOCKET_INVALID")
                path.unlink()

    def _readmit_recovered_slots(self):
        """Rotate every reusable slot after replay has adjudicated old leases."""
        snapshot = self.coordinator.tick()
        admitted = set()
        for base in self.resource_manifest.workers:
            prior = snapshot.workers.get(base.worker_id)
            prior_generation = base.generation if prior is None else prior.generation
            if prior_generation < base.generation:
                raise CliError("RECOVERY_WORKER_GENERATION_ROLLBACK")
            current = base
            while current.generation < prior_generation + 1:
                current = self.allocator.replace(
                    current.worker_id, expected_generation=current.generation
                )
            if prior is None:
                self.coordinator.register_worker(
                    current.worker_id, generation=current.generation
                )
                admitted.add(current.worker_id)
                continue
            if prior.lease is not None:
                raise CliError("RECOVERY_ACTIVE_LEASE_NOT_ADJUDICATED")
            if prior.state is WorkerState.RECOVERING:
                deadline = prior.recovery_deadline_monotonic_s
                if deadline is None or self._clock() >= deadline:
                    self.coordinator.tick()
                    continue
                self.coordinator.register_worker(
                    current.worker_id,
                    generation=current.generation,
                    recovery_deadline_monotonic_s=deadline,
                )
                final = self.coordinator.record_recovery(
                    current.worker_id,
                    generation=current.generation,
                    succeeded=True,
                    fenced=True,
                    owned_processes_stopped=True,
                    controllers_stopped=True,
                    readmitted=True,
                    recovery_deadline_monotonic_s=deadline,
                )
                if final.state is not WorkerState.AVAILABLE:
                    raise CliError("RECOVERY_WORKER_READMISSION_FAILED")
                admitted.add(current.worker_id)
            elif prior.state is WorkerState.AVAILABLE:
                final = self.coordinator.register_worker(
                    current.worker_id, generation=current.generation
                )
                if final.state is not WorkerState.AVAILABLE:
                    raise CliError("RECOVERY_WORKER_READMISSION_FAILED")
                admitted.add(current.worker_id)
            elif prior.state not in {WorkerState.QUARANTINED, WorkerState.STOPPED}:
                raise CliError("RECOVERY_WORKER_STATE")
        return frozenset(admitted)

    def _broker_runtime_for_generation(self, generation):
        if generation == 1:
            return self.authority.ipc_root / "broker"
        return self.authority.ipc_root / f"broker-g{generation}"

    def _prior_broker_generation(self):
        if self.spec.request.run_mode is RunMode.DRY_RUN:
            return 0
        generations = []
        ipc_root = self.spec.request.evidence_root / "ipc"
        for path in ipc_root.glob("broker*/broker-spec.json"):
            document = _read_existing_json(path, label="BROKER_SPEC")
            generation = document.get("broker_generation")
            if (
                document.get("batch_id") != self.spec.request.batch_id
                or type(generation) is not int
                or generation <= 0
            ):
                raise CliError("RECOVERY_BROKER_SPEC_IDENTITY")
            expected_root = (
                ipc_root / "broker" if generation == 1
                else ipc_root / f"broker-g{generation}"
            )
            if path.parent != expected_root:
                raise CliError("RECOVERY_BROKER_SPEC_IDENTITY")
            generations.append(generation)
        if not generations or len(generations) != len(set(generations)):
            raise CliError("RECOVERY_BROKER_SPEC_MISSING")
        return max(generations)

    def _prepare_broker_generation(self, generation):
        if type(generation) is not int or generation != self.broker_generation + 1:
            raise CliError("BROKER_GENERATION_SEQUENCE")
        previous_server = self.broker_authority_server
        previous_thread = self._broker_authority_thread
        if previous_server is not None:
            previous_server.close()
            self.broker_authority_server = None
            self._broker_authority_thread = None
        if previous_thread is not None:
            previous_thread.join(
                timeout=self.spec.config.heartbeat_timeout_s + 1.0
            )
            if previous_thread.is_alive():
                raise CliError("BROKER_AUTHORITY_SHUTDOWN_TIMEOUT")
        runtime_root = (
            self.authority.ipc_root / "broker"
            if generation == 1
            else self.authority.ipc_root / f"broker-g{generation}"
        )
        runtime_root.mkdir(mode=0o700)
        authority = WorkerTokenAuthority(
            self.spec.request.evidence_root,
            coordinator_epoch=self.journal.coordinator_epoch,
            ipc_root=runtime_root,
        )
        token_path = authority.issue("broker", generation)
        authority_server = AuthenticatedUnixServer(
            runtime_root / "broker-authority.sock",
            authority,
            self._coordinator_handler,
            deadline_s=self.spec.config.heartbeat_timeout_s,
            max_frame_bytes=self.spec.config.broker_max_frame_bytes,
        )
        config_copy = runtime_root / "runtime-config.yaml"
        _write_bytes(config_copy, self.spec.config_path.read_bytes())
        spec_path = runtime_root / "broker-spec.json"
        _write_json(
            spec_path,
            {
                "schema_version": 1,
                "kind": "so101_parallel_broker_runtime",
                "batch_id": self.spec.request.batch_id,
                "coordinator_epoch": self.journal.coordinator_epoch,
                "broker_generation": generation,
                "run_mode": self.spec.request.run_mode.value,
                "image_id": self.spec.provenance.get("image_id"),
                "yolo_weights_sha256": self.spec.yolo_weights_sha256,
                "grounded_manifest_sha256": self.spec.grounded_manifest_sha256,
                "config_path": "/runtime/runtime-config.yaml",
                "authority_endpoint": "/runtime/broker-authority.sock",
                "authority_token_path": f"/runtime/{token_path.name}",
                "request_deadline_s": self.spec.config.heartbeat_timeout_s,
                "max_frame_bytes": self.spec.config.broker_max_frame_bytes,
            },
        )
        self.broker_generation = generation
        self.broker_runtime_root = runtime_root
        self.broker_socket_path = runtime_root / "perception.sock"
        self.broker_container_id_path = runtime_root / "container.cid"
        self.broker_authority = authority
        self.broker_token_path = token_path
        self.broker_spec_path = spec_path
        self.broker_authority_server = authority_server
        self._broker_authority_thread = None

    def _start_broker_authority_server(self):
        if self.broker_authority_server is None:
            return
        thread = threading.Thread(
            target=self.broker_authority_server.serve_forever,
            daemon=True,
        )
        thread.start()
        self._broker_authority_thread = thread

    def _release_partial(self):
        for server in getattr(self, "worker_servers", ()):
            try:
                server.close()
            except Exception:
                pass
        server = getattr(self, "broker_authority_server", None)
        if server is not None:
            try:
                server.close()
                self.broker_authority_server = None
            except Exception:
                pass
        thread = getattr(self, "_broker_authority_thread", None)
        if thread is not None:
            thread.join(timeout=self.spec.config.heartbeat_timeout_s + 1.0)
            self._broker_authority_thread = None
        journal = getattr(self, "journal", None)
        if journal is not None:
            try:
                journal.close()
            except Exception:
                pass
        allocator = getattr(self, "allocator", None)
        if allocator is not None:
            try:
                allocator.close()
            except Exception:
                pass

    def _start_broker(self):
        if self.broker_spec_path is None:
            return None
        try:
            current_provenance = self._provenance_revalidator(
                self.spec.provenance_inputs
            )
        except Exception as error:
            raise CliError("PROVENANCE_REVALIDATION_FAILED") from error
        if dict(current_provenance) != dict(self.spec.provenance):
            raise CliError("PROVENANCE_DRIFT")
        if self._broker_command_builder is not None:
            command = self._broker_command_builder(self)
        else:
            from so101_demo.cli.parallel_perception_broker import (
                container_run_argv,
                gpu_groups,
                image_record,
            )

            image_id = self.spec.provenance.get("image_id")
            if not isinstance(image_id, str):
                raise CliError("BROKER_IMAGE_ID_REQUIRED")
            try:
                current_image = image_record(self.spec.broker_image)
            except Exception as error:
                raise CliError("BROKER_IMAGE_READBACK_FAILED") from error
            if any(
                self.spec.provenance.get(name) != value
                for name, value in current_image.items()
            ):
                raise CliError("BROKER_IMAGE_TAG_DRIFT")
            command = container_run_argv(
                self.spec.request.evidence_root,
                runtime_root=self.broker_runtime_root,
                input_root=self.broker_input_root,
                image_id=image_id,
                yolo_weights=self.spec.yolo_weights.resolve(),
                grounded_root=self.spec.grounded_root.resolve(),
                gpu_groups=gpu_groups(),
                uid=os.getuid(),
                gid=os.getgid(),
                batch_id=self.spec.request.batch_id,
                broker_generation=self.broker_generation,
            )
        return self.supervisor.start("broker", command)

    def _container_inspect(self, container_id):
        return self._container_runner(
            ["docker", "inspect", "--type", "container", container_id],
            check=False,
            capture_output=True,
            text=True,
            timeout=self.spec.config.heartbeat_timeout_s,
        )

    def _harden_broker_container_id(self):
        """Make Docker's daemon-created cidfile private before trusting it."""

        path = self.broker_container_id_path
        try:
            before = path.lstat()
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError as error:
            raise CliError("BROKER_CONTAINER_ID_MISSING") from error
        try:
            current = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or not stat.S_ISREG(current.st_mode)
                or before.st_uid != os.getuid()
                or current.st_uid != os.getuid()
                or (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino)
            ):
                raise CliError("BROKER_CONTAINER_ID_INVALID")
            value = os.read(descriptor, 66).decode("ascii").strip()
            if re.fullmatch(r"[0-9a-f]{64}", value) is None:
                raise CliError("BROKER_CONTAINER_ID_INVALID")
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
        except (OSError, UnicodeError) as error:
            raise CliError("BROKER_CONTAINER_ID_INVALID") from error
        finally:
            os.close(descriptor)
        return True

    def _retire_broker_container(self, *, runtime_root=None, generation=None):
        """Stop only the exact Docker container created for this Broker generation."""

        if not self._uses_production_broker_container or self.broker_spec_path is None:
            return True
        runtime_root = self.broker_runtime_root if runtime_root is None else Path(runtime_root)
        generation = self.broker_generation if generation is None else generation
        container_id_path = runtime_root / "container.cid"
        try:
            identity = container_id_path.lstat()
            container_id = container_id_path.read_text(encoding="ascii").strip()
        except (OSError, UnicodeError) as error:
            raise CliError("BROKER_CONTAINER_ID_MISSING") from error
        if (
            not stat.S_ISREG(identity.st_mode)
            or identity.st_uid != os.getuid()
            or stat.S_IMODE(identity.st_mode) != 0o600
            or re.fullmatch(r"[0-9a-f]{64}", container_id) is None
        ):
            raise CliError("BROKER_CONTAINER_ID_INVALID")
        inspected = self._container_inspect(container_id)
        if inspected.returncode != 0:
            return True
        try:
            documents = json.loads(inspected.stdout)
        except (TypeError, json.JSONDecodeError) as error:
            raise CliError("BROKER_CONTAINER_INSPECT_INVALID") from error
        if type(documents) is not list or len(documents) != 1 or type(documents[0]) is not dict:
            raise CliError("BROKER_CONTAINER_INSPECT_INVALID")
        document = documents[0]
        labels = document.get("Config", {}).get("Labels", {})
        mounts = {
            (item.get("Source"), item.get("Destination"))
            for item in document.get("Mounts", ())
            if type(item) is dict
        }
        if (
            document.get("Id") != container_id
            or document.get("Image") != self.spec.provenance.get("image_id")
            or labels.get("com.so101.batch-id") != self.spec.request.batch_id
            or labels.get("com.so101.broker-generation") != str(generation)
            or (str(runtime_root), "/runtime") not in mounts
            or (str(self.broker_input_root), "/inputs") not in mounts
        ):
            raise CliError("BROKER_CONTAINER_IDENTITY")
        stopped = self._container_runner(
            [
                "docker", "stop", "--timeout",
                str(max(1, int(self.spec.config.heartbeat_timeout_s))),
                container_id,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=self.spec.config.heartbeat_timeout_s + 2.0,
        )
        removal_deadline = self._clock() + self.spec.config.heartbeat_timeout_s
        after = self._container_inspect(container_id)
        while after.returncode == 0 and self._clock() < removal_deadline:
            remaining = removal_deadline - self._clock()
            self._sleep(min(0.05, remaining))
            after = self._container_inspect(container_id)
        if stopped.returncode != 0 and after.returncode == 0:
            raise CliError("BROKER_CONTAINER_STOP_FAILED")
        if after.returncode == 0:
            raise CliError("BROKER_CONTAINER_SURVIVED")
        return True

    def _wait_broker_ready(self, *, deadline_monotonic_s=None):
        if self.broker_spec_path is None:
            return True
        deadline = (
            self._clock() + self.spec.config.broker_recovery_timeout_s
            if deadline_monotonic_s is None
            else deadline_monotonic_s
        )
        ready = self.broker_runtime_root / "ready.json"
        while self._clock() < deadline:
            self.supervisor.assert_healthy()
            try:
                socket_info = self.broker_socket_path.lstat()
            except FileNotFoundError:
                socket_info = None
            try:
                ready_info = ready.lstat()
            except FileNotFoundError:
                ready_info = None
            if socket_info is not None:
                if not stat.S_ISSOCK(socket_info.st_mode):
                    raise CliError("BROKER_READY_ENDPOINT_NOT_SOCKET")
            if ready_info is not None and stat.S_ISLNK(ready_info.st_mode):
                raise CliError("BROKER_READY_RECEIPT_INVALID")
            if (
                socket_info is not None
                and ready_info is not None
                and stat.S_ISSOCK(socket_info.st_mode)
                and stat.S_ISREG(ready_info.st_mode)
                and socket_info.st_uid == os.getuid()
                and ready_info.st_uid == os.getuid()
                and stat.S_IMODE(socket_info.st_mode) == 0o600
                and stat.S_IMODE(ready_info.st_mode) == 0o600
            ):
                if self._uses_production_broker_container:
                    self._harden_broker_container_id()
                try:
                    document = json.loads(ready.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError) as error:
                    raise CliError("BROKER_READY_RECEIPT_INVALID") from error
                expected = {
                    "batch_id": self.spec.request.batch_id,
                    "run_mode": self.spec.request.run_mode.value,
                    "coordinator_epoch": self.journal.coordinator_epoch,
                    "broker_generation": self.broker_generation,
                    "image_id": self.spec.provenance.get("image_id"),
                    "yolo_weights_sha256": self.spec.yolo_weights_sha256,
                    "grounded_manifest_sha256": self.spec.grounded_manifest_sha256,
                }
                _validate_broker_ready(document, expected)
                ready_bytes = json.dumps(
                    document, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode("utf-8")
                ready_sha256 = hashlib.sha256(ready_bytes).hexdigest()
                client = self._broker_health_client_factory(
                    self.broker_socket_path,
                    deadline_s=self.spec.config.heartbeat_timeout_s,
                    max_frame_bytes=self.spec.config.broker_max_frame_bytes,
                )
                message = {
                    "schema_version": 1,
                    "kind": "broker_call",
                    "coordinator_epoch": self.journal.coordinator_epoch,
                    "worker_id": "broker",
                    "worker_generation": self.broker_generation,
                    "lease": None,
                    "request_id": f"broker-health-{self.broker_generation}",
                    "idempotency_key": f"broker-health-{self.broker_generation}",
                    "token": self.broker_token_path.read_text(encoding="ascii"),
                    "payload": {"operation": "health", "ready_sha256": ready_sha256},
                }
                response = client.call(message)
                payload = response.get("payload")
                if (
                    type(payload) is not dict
                    or set(payload) != {"ready", "ready_sha256"}
                    or payload["ready"] != document
                    or payload["ready_sha256"] != ready_sha256
                ):
                    raise CliError("BROKER_READY_HEALTH_IDENTITY")
                try:
                    socket_after = self.broker_socket_path.lstat()
                except FileNotFoundError as error:
                    raise CliError("BROKER_READY_ENDPOINT_CHANGED") from error
                if (
                    (socket_after.st_dev, socket_after.st_ino)
                    != (socket_info.st_dev, socket_info.st_ino)
                    or not stat.S_ISSOCK(socket_after.st_mode)
                ):
                    raise CliError("BROKER_READY_ENDPOINT_CHANGED")
                return True
            self._sleep(0.01)
        raise CliError("BROKER_READY_TIMEOUT")

    def _recover_broker(self, expected, _exit_code):
        snapshot = self.coordinator.mark_broker_health(False)
        deadline = snapshot.broker_recovery_deadline_monotonic_s
        if deadline is None:
            raise CliError("BROKER_RECOVERY_DEADLINE_MISSING")
        replacement = None
        previous_runtime_root = self.broker_runtime_root
        previous_generation = self.broker_generation
        try:
            if self.supervisor.retire_owned(expected) is not True:
                raise CliError("BROKER_RETIRE_FAILED")
            if self._retire_broker_container(
                runtime_root=previous_runtime_root,
                generation=previous_generation,
            ) is not True:
                raise CliError("BROKER_CONTAINER_RETIRE_FAILED")
            self._prepare_broker_generation(self.broker_generation + 1)
            self._start_broker_authority_server()
            replacement = self._start_broker()
            self._wait_broker_ready(deadline_monotonic_s=deadline)
            self.coordinator.mark_broker_health(True)
            return True
        except Exception:
            if replacement is not None:
                try:
                    self.supervisor.retire_owned(replacement)
                except Exception:
                    pass
            while self._clock() < deadline:
                self._sleep(min(0.01, max(0.0, deadline - self._clock())))
            self.coordinator.tick()
            return False

    def _stop_new_leases(self):
        self.coordinator.request_stop(reason="SUPERVISOR_SHUTDOWN")
        return self._worker_control("stop")

    def _settle_shared_dependency_failure(self):
        """Let active leases reach terminal or immutable stage deadlines."""
        snapshot = self.coordinator.snapshot()
        while snapshot.broker_recovery_failed and snapshot.terminal_reason is None:
            active = [
                worker for worker in snapshot.workers.values()
                if worker.lease is not None
            ]
            if not active:
                snapshot = self.coordinator.tick()
                break
            deadlines = [snapshot.batch_deadline_monotonic_s]
            for worker in active:
                deadlines.extend(value for value in (
                    worker.lease.lease_deadline_monotonic_s,
                    worker.stage_deadline_monotonic_s,
                    worker.heartbeat_deadline_monotonic_s,
                ) if value is not None)
            deadline = min(deadlines)
            now = self._clock()
            if now < deadline:
                self._sleep(min(0.01, deadline - now))
            snapshot = self.coordinator.tick()
        return snapshot

    def _worker_control(self, operation):
        if getattr(self, "_worker_children_reaped", False):
            return True
        okay = True
        for control in self.worker_controls:
            try:
                okay = control.call(operation) is True and okay
            except Exception:
                okay = False
        return okay

    def _cancel_worker_goals(self):
        return self._worker_control("cancel_motion")

    def _confirm_worker_goals_cancelled(self):
        return self._worker_control("confirm_no_controller_goal")

    def _request_worker_recovery(self):
        return self._worker_control("recover")

    def _start_workers(self):
        for path, resources in zip(
            self.worker_specs, self.resource_manifest.workers, strict=True
        ):
            command = (
                sys.executable, "-m", "so101_demo.cli.mujoco_parallel_batch",
                "--internal-worker", str(path),
            )
            self.supervisor.start(
                "worker", command, environment=dict(resources.environment)
            )
        if not callable(getattr(self.supervisor, "assert_healthy", None)):
            return
        deadline = time.monotonic() + self.spec.config.heartbeat_timeout_s
        while time.monotonic() < deadline:
            self.supervisor.assert_healthy()
            if all(
                control.socket_path.is_socket()
                and not control.socket_path.is_symlink()
                and stat.S_IMODE(control.socket_path.stat().st_mode) == 0o600
                for control in self.worker_controls
            ):
                return
            time.sleep(0.01)
        raise CliError("WORKER_CONTROL_READY_TIMEOUT")

    def _active_lease(self, message):
        worker = self.coordinator.snapshot().workers.get(message["worker_id"])
        if worker is None or worker.lease is None:
            raise CliError("RPC_ACTIVE_LEASE_REQUIRED")
        if _lease_wire(worker.lease) != message["lease"]:
            raise CliError("RPC_STALE_LEASE")
        return worker.lease

    def _broker_discovery_lease(self, message):
        """Authorize discovery from an active or exact just-terminal lease."""
        try:
            return self._active_lease(message)
        except CliError:
            pass
        snapshot = self.coordinator.snapshot()
        worker = snapshot.workers.get(message["worker_id"])
        lease = message.get("lease")
        if (
            worker is None
            or worker.generation != message["worker_generation"]
            or worker.state is not WorkerState.RECOVERING
            or worker.lease is not None
            or type(lease) is not dict
        ):
            raise CliError("BROKER_DISCOVERY_LEASE")
        terminal_identity = None
        for event in reversed(self.journal.replay().events):
            if event.type not in {
                "RESULT_COMMITTED", "VALIDATION_COMMITTED", "LEASE_EXPIRED",
            }:
                continue
            identity = event.payload.get("identity")
            if (
                type(identity) is dict
                and identity.get("worker_id") == message["worker_id"]
                and identity.get("worker_generation")
                == message["worker_generation"]
            ):
                terminal_identity = identity
                break
        if terminal_identity is None or any(
            terminal_identity.get(name) != value for name, value in lease.items()
        ):
            raise CliError("BROKER_DISCOVERY_LEASE")
        return True

    def _coordinator_handler(self, message):
        payload = message["payload"]
        operation = payload.get("operation")
        worker_id = message["worker_id"]
        generation = message["worker_generation"]
        if worker_id == "broker":
            _validate_broker_authority_payload(payload)
            if generation != self.broker_generation:
                raise CliError("BROKER_GENERATION")
            if operation == "authenticate_broker_message":
                inner = payload.get("message")
                if type(inner) is not dict:
                    raise CliError("BROKER_INNER_MESSAGE")
                token_authority = (
                    self.broker_authority
                    if inner.get("worker_id") == "broker"
                    else self.authority
                )
                token_authority.authenticate(inner)
                return {"authenticated": True}
            if operation == "broker_health_down":
                self.coordinator.mark_broker_health(False)
                return {"accepted": True}
            if operation == "authorize_inference":
                request = _inference_request(payload.get("request"))
                snapshot = _snapshot(payload.get("snapshot"))
                if snapshot.start_identity != NormalizedInferenceResponseIdentity.from_request(
                    request
                ):
                    raise CliError("BROKER_START_IDENTITY")
                worker = self.coordinator.snapshot().workers.get(request.worker_id)
                if (
                    worker is None
                    or worker.state is not WorkerState.EXECUTING
                    or worker.generation != request.worker_generation
                    or worker.lease is None
                    or worker.stop_requested
                    or not worker.inference_allowed
                ):
                    return {"authorized": False}
                lease = worker.lease
                if any(
                    getattr(lease, name) != getattr(request, name)
                    for name in (
                        "batch_id",
                        "coordinator_epoch",
                        "worker_id",
                        "worker_generation",
                        "point_id",
                        "lease_generation",
                    )
                ) or lease.attempt_id != (
                    request.attempt_id
                    if request.execution_kind is ExecutionKind.ATTEMPT
                    else request.validation_id
                ):
                    return {"authorized": False}
                event = next(
                    (
                        item
                        for item in self.journal.replay().events
                        if item.idempotency_key == snapshot.start_event_id
                    ),
                    None,
                )
                expected_type = (
                    "ATTEMPT_STARTED"
                    if request.execution_kind is ExecutionKind.ATTEMPT
                    else "VALIDATION_STARTED"
                )
                if (
                    event is None
                    or event.type != expected_type
                    or snapshot.start_event_type != expected_type
                    or event.coordinator_epoch != request.coordinator_epoch
                ):
                    return {"authorized": False}
                identity = event.payload.get("identity")
                if type(identity) is not dict:
                    return {"authorized": False}
                expected = {
                    "batch_id": lease.batch_id,
                    "coordinator_epoch": lease.coordinator_epoch,
                    "worker_id": lease.worker_id,
                    "worker_generation": lease.worker_generation,
                    "point_id": lease.point_id,
                    "attempt_id": lease.attempt_id,
                    "lease_generation": lease.lease_generation,
                }
                authorized = (
                    all(identity.get(name) == value for name, value in expected.items())
                    and type(identity.get("gate_summary")) is dict
                    and identity["gate_summary"].get("reset_epoch")
                    == request.reset_epoch
                )
                return {"authorized": authorized}
            raise CliError("BROKER_AUTHORITY_OPERATION")
        _validate_rpc_payload(payload)
        if operation == "current_broker":
            self._broker_discovery_lease(message)
            snapshot = self.coordinator.snapshot()
            if not snapshot.broker_healthy:
                return {
                    "healthy": False,
                    "broker_generation": None,
                    "broker_socket_path": None,
                    "recovery_deadline_monotonic_s": (
                        snapshot.broker_recovery_deadline_monotonic_s
                    ),
                }
            return {
                "healthy": True,
                "broker_generation": self.broker_generation,
                "broker_socket_path": str(self.broker_socket_path),
                "recovery_deadline_monotonic_s": None,
            }
        if operation == "register_worker":
            requested = payload.get("generation")
            ack = self.coordinator.register_worker(
                worker_id,
                generation=requested,
                recovery_deadline_monotonic_s=payload.get("recovery_deadline_monotonic_s"),
            )
            if requested != generation:
                self.authority.advance_generation(worker_id, generation, requested)
            return _jsonable(ack)
        if operation == "grant_lease":
            outcome = self.coordinator.grant_lease_outcome(
                worker_id,
                generation=payload.get("generation"),
                request_key=message["idempotency_key"],
            )
            lease = outcome["lease"]
            if lease is not None:
                self.authority.bind_lease(worker_id, generation, _lease_wire(lease))
            return _jsonable(outcome)
        if operation == "record_recovery":
            values = {key: value for key, value in payload.items() if key != "operation"}
            return _jsonable(self.coordinator.record_recovery(worker_id, **values))
        if operation == "replace_resources":
            return self.allocator.replace(
                worker_id,
                expected_generation=payload.get("expected_generation"),
            ).to_dict()
        lease = self._active_lease(message)
        if operation == "heartbeat":
            return _jsonable(self.coordinator.heartbeat(lease))
        if operation == "ack_lease":
            return _jsonable(self.coordinator.ack_lease(
                lease, request_key=message["idempotency_key"]
            ))
        if operation in {"ack_attempt_started", "ack_validation_started"}:
            method = getattr(self.coordinator, operation)
            return _jsonable(method(
                lease,
                request_key=message["idempotency_key"],
                gate_summary=payload.get("gate_summary"),
            ))
        if operation == "begin_finalizing":
            return _jsonable(self.coordinator.begin_finalizing(
                lease, request_key=message["idempotency_key"]
            ))
        if operation in {"commit_result", "commit_validation"}:
            return _jsonable(getattr(self.coordinator, operation)(
                lease,
                payload.get("location"),
                request_key=message["idempotency_key"],
            ))
        raise CliError("RPC_UNKNOWN_OPERATION")

    def _start_servers(self):
        for server in self.worker_servers:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self._server_threads.append(thread)
        self._start_broker_authority_server()

    def _stop_servers(self):
        for server in self.worker_servers:
            server.close()
        if self.broker_authority_server is not None:
            self.broker_authority_server.close()
            self.broker_authority_server = None
        for thread in self._server_threads:
            thread.join(timeout=1.0)
        if self._broker_authority_thread is not None:
            self._broker_authority_thread.join(
                timeout=self.spec.config.heartbeat_timeout_s + 1.0
            )
            self._broker_authority_thread = None

    def _run_worker_local(self, path):
        resources = _resource_from_dict(json.loads(Path(path).read_text())["resources"])
        side_effects = (
            None if self._runtime_side_effects_factory is None
            else self._runtime_side_effects_factory(resources)
        )
        worker, runtime = _build_worker_from_spec(
            path, runtime_side_effects=side_effects
        )
        self.last_local_components = (worker, runtime)
        try:
            results = worker.run()
            return int(
                not results
                or any(
                    result.stopped_reason not in {"POINT_TERMINAL", "NO_POINT"}
                    for result in results
                )
            )
        finally:
            runtime.shutdown_owned()

    def run(self) -> BatchSummary:
        failure = False
        cleanup = False
        cleanup_actions = {}

        def tracked_cleanup(name, action):
            def invoke():
                try:
                    succeeded = action() is True
                except Exception as error:
                    cleanup_actions[name] = {
                        "succeeded": False,
                        "error_type": type(error).__name__,
                        "error_message": str(error),
                    }
                    return False
                cleanup_actions[name] = {
                    "succeeded": succeeded,
                    "error_type": None,
                    "error_message": None,
                }
                return succeeded

            return invoke

        try:
            self._start_servers()
            self._start_broker()
            self._wait_broker_ready()
            if self._worker_launcher is not None:
                codes = [self._worker_launcher(self, path) for path in self.worker_specs]
            else:
                self._start_workers()
                codes = self.supervisor.wait_for_children(
                    deadline_monotonic_s=(
                        self._clock() + self.spec.config.batch_hard_timeout_s
                    ),
                    health_recovery=self._recover_broker,
                    health_probe=lambda _expected: (
                        self.coordinator.snapshot().broker_healthy
                    ),
                )
                self._worker_children_reaped = True
            failure = any(code != 0 for code in codes)
            self._settle_shared_dependency_failure()
            snapshot = self.coordinator.snapshot()
        finally:
            try:
                process_error = None
                try:
                    process_cleanup = self.supervisor.shutdown(
                        stop_leases=tracked_cleanup(
                            "stop_leases", self._stop_new_leases
                        ),
                        cancel_goal=tracked_cleanup(
                            "cancel_goal", self._cancel_worker_goals
                        ),
                        confirm_goal_cancelled=tracked_cleanup(
                            "confirm_goal_cancelled",
                            self._confirm_worker_goals_cancelled,
                        ),
                        request_recovery=tracked_cleanup(
                            "request_recovery", self._request_worker_recovery
                        ),
                    )
                except Exception as error:
                    process_cleanup = False
                    process_error = error
                process_record = {
                    "succeeded": process_cleanup is True,
                    "error_type": (
                        None if process_error is None
                        else type(process_error).__name__
                    ),
                    "error_message": (
                        None if process_error is None else str(process_error)
                    ),
                }
                container_error = None
                try:
                    container_cleanup = self._retire_broker_container()
                except Exception as error:
                    container_cleanup = False
                    container_error = error
                container_record = {
                    "succeeded": container_cleanup is True,
                    "error_type": (
                        None if container_error is None
                        else type(container_error).__name__
                    ),
                    "error_message": (
                        None if container_error is None else str(container_error)
                    ),
                }
                cleanup = process_cleanup and container_cleanup
                snapshot = self.coordinator.snapshot()
                completion_attempted = bool(
                    snapshot.terminal_reason and cleanup and not failure
                )
                completion_error = None
                if snapshot.terminal_reason and cleanup and not failure:
                    try:
                        snapshot = self.coordinator.complete_cleanup(
                            owned_processes_stopped=True, controllers_stopped=True
                        )
                    except Exception as error:
                        cleanup = False
                        completion_error = error
                _write_json(
                    self.spec.request.evidence_root / "cleanup-gates.json",
                    {
                        "schema_version": 1,
                        "batch_id": self.spec.request.batch_id,
                        "actions": cleanup_actions,
                        "process_cleanup": process_record,
                        "container_cleanup": container_record,
                        "cleanup_gates_passed": cleanup,
                        "coordinator_completion": {
                            "attempted": completion_attempted,
                            "succeeded": bool(
                                completion_attempted
                                and completion_error is None
                                and snapshot.summary.batch_cleanup_complete
                            ),
                            "error_type": (
                                None if completion_error is None
                                else type(completion_error).__name__
                            ),
                            "error_message": (
                                None if completion_error is None
                                else str(completion_error)
                            ),
                        },
                        "batch_cleanup_complete": (
                            snapshot.summary.batch_cleanup_complete
                        ),
                    },
                )
                if process_error is not None:
                    raise process_error
                if completion_error is not None:
                    raise completion_error
            finally:
                self._stop_servers()
                self.journal.close()
                self.allocator.close()
        return snapshot.summary


def outcome_document(summary: BatchSummary) -> tuple[int, dict[str, object]]:
    if not isinstance(summary, BatchSummary):
        raise CliError("BATCH_SUMMARY_REQUIRED")
    document = {
        "schema_version": 1,
        "run_mode": summary.run_mode.value,
        "batch_terminal": summary.batch_terminal,
        "batch_cleanup_complete": summary.batch_cleanup_complete,
        "point_statuses": {key: value.value for key, value in summary.point_statuses.items()},
        "validation_statuses": {
            key: value.value for key, value in summary.validation_statuses.items()
        },
        "validation_complete": summary.validation_complete,
        "validation_passed": summary.validation_passed,
        "qualification_applicable": summary.qualification_applicable,
        "qualification_passed": summary.qualification_passed,
    }
    if summary.run_mode is RunMode.EXECUTE:
        passed = summary.qualification_passed
    else:
        passed = summary.validation_passed and summary.batch_cleanup_complete
    return (0 if passed else 1), document


def _write_json(path: Path, document: Mapping[str, object]) -> None:
    payload = json.dumps(
        document, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_bytes(path: Path, payload: bytes) -> None:
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _validate_broker_ready(document, expected):
    fields = {
        "schema_version", "kind", "batch_id", "run_mode", "coordinator_epoch",
        "broker_generation", "image_id", "yolo_weights_sha256",
        "grounded_manifest_sha256", "models",
    }
    if type(document) is not dict or set(document) != fields:
        raise CliError("BROKER_READY_RECEIPT_SCHEMA")
    if document["schema_version"] != 1 or document["kind"] != "so101_parallel_broker_ready":
        raise CliError("BROKER_READY_RECEIPT_SCHEMA")
    for name, value in expected.items():
        if type(document.get(name)) is not type(value) or document.get(name) != value:
            raise CliError("BROKER_READY_RECEIPT_IDENTITY")
    models = document["models"]
    expected_models = {
        "plastic-cup-yolo11n-seg-v1": {
            "ready": True,
            "weights_sha256": expected["yolo_weights_sha256"],
        },
        "grounded-sam": {
            "ready": True,
            "manifest_sha256": expected["grounded_manifest_sha256"],
        },
    }
    if models != expected_models:
        raise CliError("BROKER_READY_RECEIPT_MODELS")
    return True


def _run_with_shutdown_signals(call):
    """Turn SIGINT/SIGTERM into the same bounded exception/finally path."""

    if threading.current_thread() is not threading.main_thread():
        return call()
    previous = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}

    def terminate(number, _frame):
        raise CliError(f"SHUTDOWN_SIGNAL:{signal.Signals(number).name}")

    try:
        for number in previous:
            signal.signal(number, terminate)
        return call()
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def run_cli(
    argv=None,
    *,
    provenance_verifier=verify_provenance,
    composition_factory=ProductionBatchComposition,
) -> int:
    try:
        spec = prepare_batch(argv, provenance_verifier=provenance_verifier)
        composition = composition_factory(spec)
        root = spec.request.evidence_root
        if not root.exists():
            root.mkdir(parents=True, mode=0o700)
        if not spec.resume:
            _write_json(root / "batch_manifest.json", spec.manifest)
        summary = _run_with_shutdown_signals(composition.run)
        code, document = outcome_document(summary)
        aggregate = root / "aggregate_results.json"
        _write_json(aggregate, document)
        print(json.dumps(document, sort_keys=True))
        return code
    except (CliError, ContractError, OSError, ValueError) as error:
        print(json.dumps({"status": "ERROR", "message": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


def main(argv=None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if values[:1] == ["--internal-worker"]:
        if len(values) != 2:
            return 1
        return _run_with_shutdown_signals(
            lambda: _run_worker_spec(Path(values[1]))
        )
    return run_cli(values)


if __name__ == "__main__":
    raise SystemExit(main())
