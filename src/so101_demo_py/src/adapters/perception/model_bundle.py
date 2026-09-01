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
_PROMPT_PROFILE = {"plastic_cup": "plastic cup."}
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
_AT_FDCWD = -100
_RENAME_EXCL = 0x00000004
_RENAME_NOREPLACE = 1


@dataclass(frozen=True)
class VerifiedModelBundle:
    root: Path
    manifest_sha256: str
    detector_dir: Path
    segmenter_dir: Path
    manifest: Mapping[str, Any]


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


def _manifest_files(document: Mapping[str, Any]) -> dict[str, tuple[int, str]]:
    if set(document) != _MANIFEST_FIELDS:
        raise _invalid("manifest has unsupported or missing fields")
    if document.get("schema_version") != 1:
        raise _invalid("manifest schema_version must be 1")
    if document.get("pipeline_id") != _PIPELINE_ID:
        raise _invalid("manifest pipeline_id is not the fixed pipeline")
    if document.get("prompt_profile") != _PROMPT_PROFILE:
        raise _invalid("manifest prompt_profile is not the fixed prompt")
    if document.get("models") != _MODELS:
        raise _invalid("manifest models do not match the fixed revisions")
    if not isinstance(document.get("dependencies"), Mapping):
        raise _invalid("manifest dependencies must be a mapping")
    entries = document.get("files")
    if not isinstance(entries, list) or not entries:
        raise _invalid("manifest files must be a non-empty list")

    expected: dict[str, tuple[int, str]] = {}
    valid_prefixes = tuple(f"{model['directory']}/" for model in _MODELS.values())
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


def verify_model_bundle(root: Path, expected_manifest_sha256: str) -> VerifiedModelBundle:
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
        detector_dir=root / _MODELS["detector"]["directory"],
        segmenter_dir=root / _MODELS["segmenter"]["directory"],
        manifest=document,
    )


def _load_fixed_config(config_path: Path) -> None:
    if config_path.is_symlink() or not config_path.is_file():
        raise ValueError("config must be a regular file")
    document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError("config must be a mapping")
    if document.get("schema_version") != 1 or document.get("pipeline_id") != _PIPELINE_ID:
        raise ValueError("config does not select the fixed Grounded SAM pipeline")
    if document.get("models") != _MODELS:
        raise ValueError("config model IDs or revisions are not fixed values")
    if document.get("prompts") != _PROMPT_PROFILE:
        raise ValueError("config prompt is not the fixed plastic-cup prompt")


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
    _load_fixed_config(config_path)
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
            "prompt_profile": _PROMPT_PROFILE,
            "models": _MODELS,
            "files": sorted(files, key=lambda entry: str(entry["path"])),
            "dependencies": {},
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
