"""Build and verify immutable Grounded DINO + SAM2 model bundles."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import platform
import re
import shutil
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from so101_demo.adapters.perception.model_runtime import ModelSetupError

_PIPELINE_ID = "grounding-dino-tiny+sam2.1-hiera-tiny"
_LEGACY_PROMPT_PROFILE = {"plastic_cup": "plastic cup."}
_FINETUNED_PROMPT_PROFILE = {"cup": "cup."}
_LOCKED_DEPENDENCIES = {
    "Pillow": "12.3.0",
    "PyYAML": "6.0.2",
    "huggingface-hub": "0.34.4",
    "mujoco": "3.12.0",
    "safetensors": "0.6.2",
    "scipy": "1.17.1",
    "tokenizers": "0.22.0",
    "torch": "2.13.0",
    "torchvision": "0.28.0",
    "transformers": "4.56.2",
    "ultralytics": "8.4.115",
}
_MODELS = {
    "detector": {
        "model_id": "IDEA-Research/grounding-dino-tiny",
        "revision": "a2bb814dd30d776dcf7e30523b00659f4f141c71",
        "directory": "grounding-dino-tiny",
    },
    "segmenter": {
        "model_id": "facebook/sam2.1-hiera-tiny",
        "revision": "de431c4043854a71d8101e17995dfe596bf101a5",
        "directory": "sam2.1-hiera-tiny",
    },
}
_MANIFEST_FIELDS = {
    "schema_version",
    "pipeline_id",
    "prompt_profile",
    "models",
    "files",
    "dependencies",
}
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_DEPENDENCY_PIN = re.compile(
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)=="
    r"(?P<version>[A-Za-z0-9][A-Za-z0-9._+!-]*)\Z"
)
_AT_FDCWD = -100
_RENAME_EXCL = 0x00000004
_RENAME_NOREPLACE = 1
_CHECKPOINT_RUNTIME_FILES = frozenset(
    {
        "config.json",
        "model.safetensors",
        "preprocessor_config.json",
        "special_tokens_map.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.txt",
    }
)
_CHECKPOINT_IDENTITY_FIELDS = {
    "base_model_sha256",
    "contract_sha256",
    "train_inventory_sha256",
    "training_commit",
    "val_inventory_sha256",
}
_SAM_CHECKPOINT_RUNTIME_FILES = frozenset(
    {
        "model/config.json",
        "model/model.safetensors",
        "model/preprocessor_config.json",
        "model/processor_config.json",
    }
)
_SAM_CHECKPOINT_FILES = _SAM_CHECKPOINT_RUNTIME_FILES | {
    "epoch-receipt.json",
    "training-state.pt",
}
_SAM_CHECKPOINT_IDENTITY_FIELDS = {
    "base_manifest_sha256",
    "recipe",
    "source_commit",
    "source_manifest_sha256",
    "train_inventory_sha256",
}
_SELECTED_METRIC_FIELDS = {
    "box_threshold",
    "epoch",
    "f1",
    "fn",
    "fp",
    "multi_cup_recall",
    "precision",
    "recall",
    "small_target_recall",
    "text_threshold",
    "tp",
}
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True)
class VerifiedModelBundle:
    root: Path
    manifest_sha256: str
    detector_dir: Path
    segmenter_dir: Path
    manifest: Mapping[str, Any]

    @property
    def target_class_id(self) -> str:
        profile = self.manifest["prompt_profile"]
        return next(iter(profile))

    @property
    def prompt(self) -> str:
        profile = self.manifest["prompt_profile"]
        return str(profile[self.target_class_id])


def _invalid(detail: str) -> ModelSetupError:
    return ModelSetupError("MODEL_BUNDLE_INVALID", detail)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_manifest(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _relative_path(value: object) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise _invalid("manifest file path must be a non-empty string")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or "\\" in value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise _invalid(f"manifest file path escapes bundle: {value!r}")
    return path


def _valid_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _validate_checkpoint_identity(value: object) -> Mapping[str, str]:
    if not isinstance(value, Mapping) or set(value) != _CHECKPOINT_IDENTITY_FIELDS:
        raise _invalid("fine-tuned checkpoint identity is invalid")
    identity = dict(value)
    for name in _CHECKPOINT_IDENTITY_FIELDS - {"training_commit"}:
        if not _valid_sha256(identity[name]):
            raise _invalid(f"fine-tuned checkpoint identity {name} is invalid")
    if not isinstance(identity["training_commit"], str) or _COMMIT.fullmatch(
        identity["training_commit"]
    ) is None:
        raise _invalid("fine-tuned checkpoint training_commit is invalid")
    return identity  # type: ignore[return-value]


def _validate_selected_metrics(value: object, completed_epoch: int) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _SELECTED_METRIC_FIELDS:
        raise _invalid("fine-tuned selected validation metrics are invalid")
    metrics = dict(value)
    if type(metrics["epoch"]) is not int or metrics["epoch"] != completed_epoch:
        raise _invalid("fine-tuned selected epoch does not match checkpoint")
    for name in ("tp", "fp", "fn"):
        if type(metrics[name]) is not int or metrics[name] < 0:
            raise _invalid(f"fine-tuned metric {name} is invalid")
    for name in _SELECTED_METRIC_FIELDS - {"epoch", "tp", "fp", "fn"}:
        value = metrics[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _invalid(f"fine-tuned metric {name} is invalid")
        normalized = float(value)
        if not 0.0 <= normalized <= 1.0:
            raise _invalid(f"fine-tuned metric {name} is invalid")
    return metrics


def _validate_sam_checkpoint_identity(value: object) -> Mapping[str, str]:
    if not isinstance(value, Mapping) or set(value) != _SAM_CHECKPOINT_IDENTITY_FIELDS:
        raise _invalid("adapted SAM checkpoint identity is invalid")
    identity = dict(value)
    for name in _SAM_CHECKPOINT_IDENTITY_FIELDS - {"recipe", "source_commit"}:
        if not _valid_sha256(identity[name]):
            raise _invalid(f"adapted SAM checkpoint identity {name} is invalid")
    if (
        not isinstance(identity["recipe"], str)
        or not identity["recipe"]
        or not isinstance(identity["source_commit"], str)
        or _COMMIT.fullmatch(identity["source_commit"]) is None
    ):
        raise _invalid("adapted SAM checkpoint recipe or source commit is invalid")
    return identity  # type: ignore[return-value]


def _validate_finetuned_models(
    value: object, *, adapted_segmenter: bool = False
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"detector", "segmenter"}:
        raise _invalid("fine-tuned manifest models are invalid")
    detector = value["detector"]
    segmenter = value["segmenter"]
    detector_fields = {
        "artifact_kind",
        "checkpoint_identity",
        "checkpoint_manifest_sha256",
        "completed_epoch",
        "directory",
        "model_id",
        "revision",
        "selected_val_metrics",
    }
    if not isinstance(detector, Mapping) or set(detector) != detector_fields:
        raise _invalid("fine-tuned detector provenance is invalid")
    if any(detector[name] != _MODELS["detector"][name] for name in _MODELS["detector"]):
        raise _invalid("fine-tuned detector base identity is invalid")
    if detector["artifact_kind"] != "fine_tuned_checkpoint":
        raise _invalid("fine-tuned detector artifact kind is invalid")
    if not _valid_sha256(detector["checkpoint_manifest_sha256"]):
        raise _invalid("fine-tuned checkpoint manifest SHA256 is invalid")
    completed_epoch = detector["completed_epoch"]
    if type(completed_epoch) is not int or completed_epoch <= 0:
        raise _invalid("fine-tuned completed epoch is invalid")
    _validate_checkpoint_identity(detector["checkpoint_identity"])
    _validate_selected_metrics(detector["selected_val_metrics"], completed_epoch)

    segmenter_fields = (
        {
            "artifact_kind",
            "checkpoint_identity",
            "checkpoint_manifest_sha256",
            "completed_epoch",
            "directory",
            "model_id",
            "revision",
            "source_bundle_manifest_sha256",
        }
        if adapted_segmenter
        else {
            "artifact_kind",
            "directory",
            "model_id",
            "revision",
            "source_bundle_manifest_sha256",
        }
    )
    if not isinstance(segmenter, Mapping) or set(segmenter) != segmenter_fields:
        raise _invalid("frozen segmenter provenance is invalid")
    if any(segmenter[name] != _MODELS["segmenter"][name] for name in _MODELS["segmenter"]):
        raise _invalid("frozen segmenter identity is invalid")
    if not _valid_sha256(segmenter["source_bundle_manifest_sha256"]):
        raise _invalid("frozen segmenter source provenance is invalid")
    if adapted_segmenter:
        completed_epoch = segmenter["completed_epoch"]
        identity = _validate_sam_checkpoint_identity(segmenter["checkpoint_identity"])
        if (
            segmenter["artifact_kind"] != "decoder_only_checkpoint"
            or not _valid_sha256(segmenter["checkpoint_manifest_sha256"])
            or type(completed_epoch) is not int
            or completed_epoch <= 0
            or identity["base_manifest_sha256"]
            != segmenter["source_bundle_manifest_sha256"]
        ):
            raise _invalid("adapted segmenter provenance is invalid")
    elif segmenter["artifact_kind"] != "frozen_snapshot":
        raise _invalid("frozen segmenter source provenance is invalid")
    return value


def _manifest_files(document: Mapping[str, Any]) -> dict[str, tuple[int, str]]:
    if set(document) != _MANIFEST_FIELDS:
        raise _invalid("manifest has unsupported or missing fields")
    schema_version = document.get("schema_version")
    if schema_version not in {1, 2, 3}:
        raise _invalid("manifest schema_version must be 1, 2, or 3")
    if document.get("pipeline_id") != _PIPELINE_ID:
        raise _invalid("manifest pipeline_id is not the fixed pipeline")
    if schema_version == 1:
        if document.get("prompt_profile") != _LEGACY_PROMPT_PROFILE:
            raise _invalid("manifest prompt_profile is not the fixed legacy prompt")
        if document.get("models") != _MODELS:
            raise _invalid("manifest models do not match the fixed revisions")
        models = document["models"]
    elif schema_version == 2:
        if document.get("prompt_profile") != _FINETUNED_PROMPT_PROFILE:
            raise _invalid("manifest prompt_profile is not generic cup")
        models = _validate_finetuned_models(document.get("models"))
    else:
        if document.get("prompt_profile") != _FINETUNED_PROMPT_PROFILE:
            raise _invalid("manifest prompt_profile is not generic cup")
        models = _validate_finetuned_models(
            document.get("models"), adapted_segmenter=True
        )
    if document.get("dependencies") != _LOCKED_DEPENDENCIES:
        raise _invalid("manifest dependencies do not match the fixed dependency pins")
    entries = document.get("files")
    if not isinstance(entries, list) or not entries:
        raise _invalid("manifest files must be a non-empty list")

    expected: dict[str, tuple[int, str]] = {}
    valid_prefixes = tuple(f"{model['directory']}/" for model in models.values())
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) != {"path", "size", "sha256"}:
            raise _invalid("manifest file entry has unsupported or missing fields")
        path = _relative_path(entry["path"])
        relative = path.as_posix()
        if not relative.startswith(valid_prefixes):
            raise _invalid(f"manifest file is outside model directories: {relative}")
        size = entry["size"]
        sha256 = entry["sha256"]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise _invalid(f"manifest size is invalid for {relative}")
        if not isinstance(sha256, str) or _SHA256.fullmatch(sha256) is None:
            raise _invalid(f"manifest SHA256 is invalid for {relative}")
        if relative in expected:
            raise _invalid(f"manifest repeats file: {relative}")
        expected[relative] = (size, sha256)
    return expected


def _regular_files(root: Path) -> set[str]:
    files: set[str] = set()

    def visit(directory: Path) -> None:
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                if entry.is_symlink():
                    raise _invalid(f"bundle contains symlink: {path.relative_to(root)}")
                if entry.is_dir(follow_symlinks=False):
                    visit(path)
                elif entry.is_file(follow_symlinks=False):
                    files.add(path.relative_to(root).as_posix())
                else:
                    raise _invalid(f"bundle contains non-regular entry: {path.relative_to(root)}")

    visit(root)
    return files


def verify_model_bundle(
    root: Path,
    expected_manifest_sha256: str,
) -> VerifiedModelBundle:
    """Verify a bundle before allowing it to enter the perception runtime."""

    root = Path(root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise _invalid("bundle root must be an absolute, non-symlink directory")
    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise _invalid("bundle manifest must be a regular file")
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_sha256 != expected_manifest_sha256:
        raise ModelSetupError(
            "MODEL_HASH_MISMATCH",
            f"expected manifest {expected_manifest_sha256}, observed {manifest_sha256}",
        )
    try:
        document = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _invalid("manifest is not valid UTF-8 JSON") from error
    if not isinstance(document, dict):
        raise _invalid("manifest must be a JSON object")
    if manifest_bytes != _canonical_manifest(document):
        raise _invalid("manifest is not canonically encoded")

    expected_files = _manifest_files(document)
    actual_files = _regular_files(root)
    if actual_files != set(expected_files) | {"manifest.json"}:
        raise _invalid("bundle regular-file set does not match manifest")
    for relative, (expected_size, expected_sha256) in expected_files.items():
        path = root / relative
        if path.stat().st_size != expected_size:
            raise ModelSetupError("MODEL_HASH_MISMATCH", f"size mismatch for {relative}")
        observed_sha256 = _sha256_file(path)
        if observed_sha256 != expected_sha256:
            raise ModelSetupError(
                "MODEL_HASH_MISMATCH",
                f"SHA256 mismatch for {relative}: expected {expected_sha256}, observed {observed_sha256}",
            )
    return VerifiedModelBundle(
        root=root,
        manifest_sha256=manifest_sha256,
        detector_dir=root / document["models"]["detector"]["directory"],
        segmenter_dir=root / document["models"]["segmenter"]["directory"],
        manifest=document,
    )


def _parse_dependency_lock(lock_path: Path) -> dict[str, str]:
    if lock_path.is_symlink() or not lock_path.is_file():
        raise ValueError("dependency lock must be a regular file")
    dependencies: dict[str, str] = {}
    normalized_names: set[str] = set()
    for line_number, raw_line in enumerate(
        lock_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _DEPENDENCY_PIN.fullmatch(line)
        if match is None:
            raise ValueError(
                f"dependency lock line {line_number} must be an exact name==version pin"
            )
        name = match.group("name")
        normalized_name = re.sub(r"[-_.]+", "-", name).lower()
        if normalized_name in normalized_names:
            raise ValueError(f"duplicate dependency pin: {name}")
        normalized_names.add(normalized_name)
        dependencies[name] = match.group("version")
    if dependencies != _LOCKED_DEPENDENCIES:
        raise ValueError("dependency lock does not match the fixed dependency set")
    return dependencies


def _load_fixed_config(config_path: Path) -> dict[str, str]:
    if config_path.is_symlink() or not config_path.is_file():
        raise ValueError("config must be a regular file")
    document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError("config must be a mapping")
    if document.get("schema_version") != 1 or document.get("pipeline_id") != _PIPELINE_ID:
        raise ValueError("config does not select the fixed Grounded SAM pipeline")
    if document.get("models") != _MODELS:
        raise ValueError("config model IDs or revisions are not fixed values")
    if document.get("prompts") != _LEGACY_PROMPT_PROFILE:
        raise ValueError("config prompt is not the fixed plastic-cup prompt")
    return _parse_dependency_lock(config_path.with_name("requirements.lock"))


def _copy_snapshot(source: Path, destination: Path) -> list[dict[str, object]]:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("snapshot_download must return a non-symlink directory")
    files: list[dict[str, object]] = []
    for current, directories, names in os.walk(source, followlinks=False):
        current_path = Path(current)
        relative_dir = current_path.relative_to(source)
        kept_directories: list[str] = []
        for name in directories:
            candidate = current_path / name
            if name == ".cache":
                continue
            if candidate.is_symlink():
                raise ValueError(f"snapshot directory must not be a symlink: {candidate}")
            kept_directories.append(name)
        directories[:] = kept_directories
        target_dir = destination / relative_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in sorted(names):
            source_path = current_path / name
            relative = source_path.relative_to(source)
            if ".cache" in relative.parts:
                continue
            target_path = destination / relative
            if source_path.is_symlink():
                resolved = source_path.resolve(strict=True)
                if not resolved.is_file():
                    raise ValueError(f"snapshot symlink target is not a regular file: {relative}")
                shutil.copyfile(resolved, target_path)
            elif source_path.is_file():
                shutil.copyfile(source_path, target_path)
            else:
                raise ValueError(f"snapshot entry is not a regular file: {relative}")
            files.append(
                {
                    "path": target_path.relative_to(destination.parent).as_posix(),
                    "size": target_path.stat().st_size,
                    "sha256": _sha256_file(target_path),
                }
            )
    return files


def _rename_exclusive(source: Path, destination: Path) -> None:
    """Atomically install a directory only when its destination does not exist."""

    libc = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)
    system = platform.system()
    if system == "Darwin":
        renamex_np = libc.renamex_np
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
        result = renamex_np(source_bytes, destination_bytes, _RENAME_EXCL)
    elif system == "Linux":
        try:
            renameat2 = libc.renameat2
        except AttributeError as error:
            raise OSError(errno.ENOTSUP, "renameat2 is unavailable") from error
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = renameat2(
            _AT_FDCWD,
            source_bytes,
            _AT_FDCWD,
            destination_bytes,
            _RENAME_NOREPLACE,
        )
    else:
        raise OSError(errno.ENOTSUP, f"no exclusive directory rename for {system}")
    if result != 0:
        raise OSError(ctypes.get_errno(), "exclusive directory rename failed")


def build_model_bundle(
    config_path: Path,
    destination: Path,
    snapshot_download: Callable[..., str],
) -> str:
    """Build one immutable bundle, without overwriting an existing destination."""

    config_path = Path(config_path)
    destination = Path(destination)
    dependencies = _load_fixed_config(config_path)
    parent = destination.parent
    if not parent.is_dir():
        raise FileNotFoundError(f"bundle destination parent does not exist: {parent}")
    if os.path.lexists(destination):
        raise FileExistsError(f"bundle destination already exists: {destination}")

    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.staging-", dir=parent))
    try:
        files: list[dict[str, object]] = []
        for model in _MODELS.values():
            snapshot = Path(
                snapshot_download(repo_id=model["model_id"], revision=model["revision"])
            )
            files.extend(_copy_snapshot(snapshot, staging / model["directory"]))
        document: dict[str, Any] = {
            "schema_version": 1,
            "pipeline_id": _PIPELINE_ID,
            "prompt_profile": _LEGACY_PROMPT_PROFILE,
            "models": _MODELS,
            "files": sorted(files, key=lambda entry: str(entry["path"])),
            "dependencies": dependencies,
        }
        manifest_bytes = _canonical_manifest(document)
        (staging / "manifest.json").write_bytes(manifest_bytes)
        digest = hashlib.sha256(manifest_bytes).hexdigest()
        verify_model_bundle(staging, digest)
        try:
            _rename_exclusive(staging, destination)
        except OSError as error:
            if error.errno == errno.EEXIST:
                raise FileExistsError(
                    f"bundle destination already exists: {destination}"
                ) from error
            raise
        return digest
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def _verified_checkpoint_document(
    checkpoint_root: Path,
    expected_manifest_sha256: str,
) -> Mapping[str, Any]:
    root = Path(checkpoint_root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ValueError("checkpoint root must be an absolute, non-symlink directory")
    if not _valid_sha256(expected_manifest_sha256):
        raise ValueError("expected checkpoint manifest SHA256 is invalid")
    manifest_path = root / "checkpoint-manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("checkpoint manifest must be a regular file")
    payload = manifest_path.read_bytes()
    observed_sha256 = hashlib.sha256(payload).hexdigest()
    if observed_sha256 != expected_manifest_sha256:
        raise ValueError(
            "checkpoint manifest SHA256 mismatch: "
            f"expected {expected_manifest_sha256}, observed {observed_sha256}"
        )
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("checkpoint manifest is not valid UTF-8 JSON") from error
    if payload != _canonical_manifest(document):
        raise ValueError("checkpoint manifest is not canonically encoded")
    fields = {
        "complete",
        "completed_epoch",
        "files",
        "identity",
        "schema_version",
        "selected_val_metrics",
    }
    if not isinstance(document, Mapping) or set(document) != fields:
        raise ValueError("checkpoint manifest fields are invalid")
    if document["schema_version"] != 1 or document["complete"] is not True:
        raise ValueError("checkpoint manifest is incomplete or unsupported")
    completed_epoch = document["completed_epoch"]
    if type(completed_epoch) is not int or completed_epoch <= 0:
        raise ValueError("checkpoint completed epoch is invalid")
    try:
        _validate_checkpoint_identity(document["identity"])
        _validate_selected_metrics(document["selected_val_metrics"], completed_epoch)
    except ModelSetupError as error:
        raise ValueError(error.detail) from error
    entries = document["files"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("checkpoint files are invalid")
    expected: dict[str, tuple[int, str]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) != {"path", "sha256", "size"}:
            raise ValueError("checkpoint file entry is invalid")
        relative = _relative_path(entry["path"]).as_posix()
        if "/" in relative or relative == "checkpoint-manifest.json":
            raise ValueError("checkpoint file path is invalid")
        size = entry["size"]
        sha256 = entry["sha256"]
        if type(size) is not int or size < 0 or not _valid_sha256(sha256):
            raise ValueError(f"checkpoint file metadata is invalid for {relative}")
        if relative in expected:
            raise ValueError(f"checkpoint repeats file: {relative}")
        expected[relative] = (size, sha256)
    required = _CHECKPOINT_RUNTIME_FILES | {"training-state.pt"}
    if set(expected) != required:
        raise ValueError("checkpoint file set is not the complete training checkpoint")
    actual = _regular_files(root)
    if actual != set(expected) | {"checkpoint-manifest.json"}:
        raise ValueError("checkpoint regular-file set does not match manifest")
    for relative, (size, sha256) in expected.items():
        path = root / relative
        if path.stat().st_size != size or _sha256_file(path) != sha256:
            raise ValueError(f"checkpoint member hash mismatch for {relative}")
    return document


def _verified_sam_checkpoint_document(
    checkpoint_root: Path,
    expected_manifest_sha256: str,
) -> Mapping[str, Any]:
    root = Path(checkpoint_root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ValueError("SAM checkpoint root must be an absolute, non-symlink directory")
    if not _valid_sha256(expected_manifest_sha256):
        raise ValueError("expected SAM checkpoint manifest SHA256 is invalid")
    manifest_path = root / "checkpoint-manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("SAM checkpoint manifest must be a regular file")
    payload = manifest_path.read_bytes()
    observed_sha256 = hashlib.sha256(payload).hexdigest()
    if observed_sha256 != expected_manifest_sha256:
        raise ValueError(
            "SAM checkpoint manifest SHA256 mismatch: "
            f"expected {expected_manifest_sha256}, observed {observed_sha256}"
        )
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("SAM checkpoint manifest is not valid UTF-8 JSON") from error
    if payload != _canonical_manifest(document):
        raise ValueError("SAM checkpoint manifest is not canonically encoded")
    if (
        not isinstance(document, Mapping)
        or set(document) != {"complete", "completed_epoch", "files", "identity", "schema_version"}
        or document["schema_version"] != 1
        or document["complete"] is not True
        or type(document["completed_epoch"]) is not int
        or document["completed_epoch"] <= 0
    ):
        raise ValueError("SAM checkpoint manifest is incomplete or unsupported")
    try:
        _validate_sam_checkpoint_identity(document["identity"])
    except ModelSetupError as error:
        raise ValueError(error.detail) from error
    entries = document["files"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("SAM checkpoint files are invalid")
    expected: dict[str, tuple[int, str]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) != {"path", "sha256", "size"}:
            raise ValueError("SAM checkpoint file entry is invalid")
        relative = _relative_path(entry["path"]).as_posix()
        size = entry["size"]
        sha256 = entry["sha256"]
        if (
            relative == "checkpoint-manifest.json"
            or type(size) is not int
            or size < 0
            or not _valid_sha256(sha256)
            or relative in expected
        ):
            raise ValueError(f"SAM checkpoint file metadata is invalid for {relative}")
        expected[relative] = (size, sha256)
    if set(expected) != _SAM_CHECKPOINT_FILES:
        raise ValueError("SAM checkpoint file set is incomplete")
    if _regular_files(root) != set(expected) | {"checkpoint-manifest.json"}:
        raise ValueError("SAM checkpoint regular-file set does not match manifest")
    for relative, (size, sha256) in expected.items():
        path = root.joinpath(*PurePosixPath(relative).parts)
        if path.stat().st_size != size or _sha256_file(path) != sha256:
            raise ValueError(f"SAM checkpoint member hash mismatch for {relative}")
    return document


def compose_finetuned_model_bundle(
    *,
    checkpoint_root: Path,
    expected_checkpoint_manifest_sha256: str,
    source_bundle_root: Path,
    expected_source_manifest_sha256: str,
    destination: Path,
) -> str:
    """Compose one immutable generic-cup bundle from verified local artifacts."""

    destination = Path(destination)
    parent = destination.parent
    if not parent.is_dir():
        raise FileNotFoundError(f"bundle destination parent does not exist: {parent}")
    if os.path.lexists(destination):
        raise FileExistsError(f"bundle destination already exists: {destination}")
    checkpoint_root = Path(checkpoint_root).resolve()
    checkpoint = _verified_checkpoint_document(
        checkpoint_root, expected_checkpoint_manifest_sha256
    )
    source_bundle = verify_model_bundle(
        Path(source_bundle_root), expected_source_manifest_sha256
    )
    if source_bundle.manifest["schema_version"] != 1:
        raise ValueError("source SAM bundle must use the frozen schema-v1 snapshot")

    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.staging-", dir=parent))
    try:
        detector_dir = staging / _MODELS["detector"]["directory"]
        detector_dir.mkdir()
        files: list[dict[str, object]] = []
        for name in sorted(_CHECKPOINT_RUNTIME_FILES):
            source = checkpoint_root / name
            target = detector_dir / name
            shutil.copyfile(source, target)
            files.append(
                {
                    "path": target.relative_to(staging).as_posix(),
                    "size": target.stat().st_size,
                    "sha256": _sha256_file(target),
                }
            )
        files.extend(
            _copy_snapshot(
                source_bundle.segmenter_dir,
                staging / _MODELS["segmenter"]["directory"],
            )
        )
        document: dict[str, Any] = {
            "schema_version": 2,
            "pipeline_id": _PIPELINE_ID,
            "prompt_profile": _FINETUNED_PROMPT_PROFILE,
            "models": {
                "detector": {
                    **_MODELS["detector"],
                    "artifact_kind": "fine_tuned_checkpoint",
                    "checkpoint_manifest_sha256": expected_checkpoint_manifest_sha256,
                    "checkpoint_identity": dict(checkpoint["identity"]),
                    "completed_epoch": checkpoint["completed_epoch"],
                    "selected_val_metrics": dict(checkpoint["selected_val_metrics"]),
                },
                "segmenter": {
                    **_MODELS["segmenter"],
                    "artifact_kind": "frozen_snapshot",
                    "source_bundle_manifest_sha256": expected_source_manifest_sha256,
                },
            },
            "files": sorted(files, key=lambda entry: str(entry["path"])),
            "dependencies": dict(source_bundle.manifest["dependencies"]),
        }
        manifest_bytes = _canonical_manifest(document)
        (staging / "manifest.json").write_bytes(manifest_bytes)
        digest = hashlib.sha256(manifest_bytes).hexdigest()
        verify_model_bundle(staging, digest)
        try:
            _rename_exclusive(staging, destination)
        except OSError as error:
            if error.errno == errno.EEXIST:
                raise FileExistsError(
                    f"bundle destination already exists: {destination}"
                ) from error
            raise
        return digest
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def compose_adapted_model_bundle(
    *,
    detector_checkpoint_root: Path,
    expected_detector_checkpoint_manifest_sha256: str,
    segmenter_checkpoint_root: Path,
    expected_segmenter_checkpoint_manifest_sha256: str,
    source_bundle_root: Path,
    expected_source_manifest_sha256: str,
    destination: Path,
) -> str:
    """Compose a generic-cup bundle from verified DINO and decoder-only SAM checkpoints."""

    destination = Path(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(
            f"bundle destination parent does not exist: {destination.parent}"
        )
    if os.path.lexists(destination):
        raise FileExistsError(f"bundle destination already exists: {destination}")
    detector_root = Path(detector_checkpoint_root).resolve()
    segmenter_root = Path(segmenter_checkpoint_root).resolve()
    detector = _verified_checkpoint_document(
        detector_root, expected_detector_checkpoint_manifest_sha256
    )
    segmenter = _verified_sam_checkpoint_document(
        segmenter_root, expected_segmenter_checkpoint_manifest_sha256
    )
    source_bundle = verify_model_bundle(
        Path(source_bundle_root), expected_source_manifest_sha256
    )
    source_schema = source_bundle.manifest["schema_version"]
    source_segmenter = source_bundle.manifest["models"]["segmenter"]
    if source_schema not in {1, 2} or (
        source_schema == 2 and source_segmenter.get("artifact_kind") != "frozen_snapshot"
    ):
        raise ValueError("adapted SAM source must be an original frozen snapshot bundle")
    if segmenter["identity"]["base_manifest_sha256"] != expected_source_manifest_sha256:
        raise ValueError("SAM checkpoint base bundle identity mismatch")

    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.staging-", dir=destination.parent))
    try:
        detector_dir = staging / _MODELS["detector"]["directory"]
        segmenter_dir = staging / _MODELS["segmenter"]["directory"]
        detector_dir.mkdir()
        segmenter_dir.mkdir()
        files: list[dict[str, object]] = []
        for name in sorted(_CHECKPOINT_RUNTIME_FILES):
            source = detector_root / name
            target = detector_dir / name
            shutil.copyfile(source, target)
            files.append(
                {
                    "path": target.relative_to(staging).as_posix(),
                    "size": target.stat().st_size,
                    "sha256": _sha256_file(target),
                }
            )
        for relative in sorted(_SAM_CHECKPOINT_RUNTIME_FILES):
            source = segmenter_root.joinpath(*PurePosixPath(relative).parts)
            target = segmenter_dir / PurePosixPath(relative).name
            shutil.copyfile(source, target)
            files.append(
                {
                    "path": target.relative_to(staging).as_posix(),
                    "size": target.stat().st_size,
                    "sha256": _sha256_file(target),
                }
            )
        document: dict[str, Any] = {
            "schema_version": 3,
            "pipeline_id": _PIPELINE_ID,
            "prompt_profile": _FINETUNED_PROMPT_PROFILE,
            "models": {
                "detector": {
                    **_MODELS["detector"],
                    "artifact_kind": "fine_tuned_checkpoint",
                    "checkpoint_manifest_sha256": expected_detector_checkpoint_manifest_sha256,
                    "checkpoint_identity": dict(detector["identity"]),
                    "completed_epoch": detector["completed_epoch"],
                    "selected_val_metrics": dict(detector["selected_val_metrics"]),
                },
                "segmenter": {
                    **_MODELS["segmenter"],
                    "artifact_kind": "decoder_only_checkpoint",
                    "checkpoint_manifest_sha256": expected_segmenter_checkpoint_manifest_sha256,
                    "checkpoint_identity": dict(segmenter["identity"]),
                    "completed_epoch": segmenter["completed_epoch"],
                    "source_bundle_manifest_sha256": expected_source_manifest_sha256,
                },
            },
            "files": sorted(files, key=lambda entry: str(entry["path"])),
            "dependencies": dict(source_bundle.manifest["dependencies"]),
        }
        manifest_bytes = _canonical_manifest(document)
        (staging / "manifest.json").write_bytes(manifest_bytes)
        digest = hashlib.sha256(manifest_bytes).hexdigest()
        verify_model_bundle(staging, digest)
        try:
            _rename_exclusive(staging, destination)
        except OSError as error:
            if error.errno == errno.EEXIST:
                raise FileExistsError(
                    f"bundle destination already exists: {destination}"
                ) from error
            raise
        return digest
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
