from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path

import pytest
import setuptools

from so101_demo.adapters.perception.model_bundle import (
    build_model_bundle,
    verify_model_bundle,
)
from so101_demo.adapters.perception.model_runtime import ModelSetupError
from so101_demo.cli.prepare_grounded_sam_bundle import main


PACKAGE_ROOT = Path(__file__).parents[1]
CONFIG_PATH = (PACKAGE_ROOT / "config/perception/grounded_sam.yaml").resolve()


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write_manifest(root: Path, files: list[dict[str, object]]) -> str:
    document = {
        "schema_version": 1,
        "pipeline_id": "grounding-dino-tiny+sam2.1-hiera-tiny",
        "prompt_profile": {"plastic_cup": "plastic cup."},
        "models": {
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
        },
        "files": files,
        "dependencies": {},
    }
    payload = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ) + "\n"
    (root / "manifest.json").write_text(payload, encoding="utf-8")
    return _sha256(payload.encode("utf-8"))


def fake_bundle(tmp_path: Path) -> tuple[Path, str]:
    root = (tmp_path / "bundle").resolve()
    detector = root / "grounding-dino-tiny"
    segmenter = root / "sam2.1-hiera-tiny"
    detector.mkdir(parents=True)
    segmenter.mkdir()
    (detector / "config.json").write_bytes(b"detector-config")
    (segmenter / "model.safetensors").write_bytes(b"segmenter-weights")
    files = [
        {
            "path": "grounding-dino-tiny/config.json",
            "size": 15,
            "sha256": _sha256(b"detector-config"),
        },
        {
            "path": "sam2.1-hiera-tiny/model.safetensors",
            "size": 17,
            "sha256": _sha256(b"segmenter-weights"),
        },
    ]
    return root, _write_manifest(root, files)


def test_verify_bundle_checks_manifest_and_every_regular_file(tmp_path: Path) -> None:
    """Catch verifier changes that skip a declared file's byte digest."""

    root, digest = fake_bundle(tmp_path)

    bundle = verify_model_bundle(root, digest)

    assert bundle.root == root
    assert bundle.manifest_sha256 == digest
    assert bundle.detector_dir == root / "grounding-dino-tiny"
    assert bundle.segmenter_dir == root / "sam2.1-hiera-tiny"

    (root / "sam2.1-hiera-tiny/model.safetensors").write_bytes(b"changed")

    with pytest.raises(ModelSetupError) as error:
        verify_model_bundle(root, digest)
    assert error.value.code == "MODEL_HASH_MISMATCH"


@pytest.mark.parametrize("fault", ["unlisted", "symlink", "path_escape"])
def test_verify_bundle_rejects_structural_file_set_faults(
    tmp_path: Path, fault: str
) -> None:
    """Catch accepting package layouts that can hide or escape unverified content."""

    root, digest = fake_bundle(tmp_path)
    if fault == "unlisted":
        (root / "extra.bin").write_bytes(b"extra")
    elif fault == "symlink":
        (root / "grounding-dino-tiny/linked.bin").symlink_to(
            root / "sam2.1-hiera-tiny/model.safetensors"
        )
    else:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        manifest["files"][0]["path"] = "../outside.bin"
        payload = json.dumps(
            manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ) + "\n"
        (root / "manifest.json").write_text(payload, encoding="utf-8")
        digest = _sha256(payload.encode("utf-8"))

    with pytest.raises(ModelSetupError) as error:
        verify_model_bundle(root, digest)
    assert error.value.code == "MODEL_BUNDLE_INVALID"


def _fake_snapshot_download(tmp_path: Path, calls: list[tuple[str, str]]):
    sources = tmp_path / "snapshots"
    detector = sources / "detector"
    segmenter = sources / "segmenter"
    blobs = tmp_path / "blobs"
    detector.mkdir(parents=True, exist_ok=True)
    segmenter.mkdir(parents=True, exist_ok=True)
    blobs.mkdir(exist_ok=True)
    (blobs / "detector-config").write_bytes(b"detector-config")
    config = detector / "config.json"
    if not config.exists():
        config.symlink_to(blobs / "detector-config")
    (detector / ".cache").mkdir(exist_ok=True)
    (detector / ".cache/metadata").write_bytes(b"ignore")
    (segmenter / "model.safetensors").write_bytes(b"segmenter-weights")

    snapshots = {
        "IDEA-Research/grounding-dino-tiny": detector,
        "facebook/sam2.1-hiera-tiny": segmenter,
    }

    def download(*, repo_id: str, revision: str) -> str:
        calls.append((repo_id, revision))
        return str(snapshots[repo_id])

    return download


def test_builder_copies_fixed_snapshots_without_symlinks(tmp_path: Path) -> None:
    """Catch replacing pinned snapshots with arbitrary sources or retained cache links."""

    calls: list[tuple[str, str]] = []
    destination = tmp_path / "bundle"
    digest = build_model_bundle(
        config_path=CONFIG_PATH,
        destination=destination,
        snapshot_download=_fake_snapshot_download(tmp_path, calls),
    )

    assert calls == [
        ("IDEA-Research/grounding-dino-tiny", "a2bb814dd30d776dcf7e30523b00659f4f141c71"),
        ("facebook/sam2.1-hiera-tiny", "de431c4043854a71d8101e17995dfe596bf101a5"),
    ]
    assert verify_model_bundle(destination, digest).manifest_sha256 == digest
    assert not any(path.is_symlink() for path in destination.rglob("*"))
    assert not (destination / "grounding-dino-tiny/.cache").exists()


def test_builder_refuses_existing_destination_and_missing_parent(tmp_path: Path) -> None:
    """Catch a builder change that can overwrite bundles or stage in another location."""

    calls: list[tuple[str, str]] = []
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(FileExistsError):
        build_model_bundle(CONFIG_PATH, existing, _fake_snapshot_download(tmp_path, calls))
    assert calls == []

    with pytest.raises(FileNotFoundError):
        build_model_bundle(
            CONFIG_PATH,
            tmp_path / "missing-parent/bundle",
            _fake_snapshot_download(tmp_path, calls),
        )


def test_builder_removes_only_its_staging_directory_after_snapshot_failure(
    tmp_path: Path,
) -> None:
    """Catch a failed download leaving builder-owned staging data behind."""

    destination = tmp_path / "bundle"
    calls = 0

    def failing_download(*, repo_id: str, revision: str) -> str:
        nonlocal calls
        calls += 1
        raise RuntimeError("snapshot unavailable")

    with pytest.raises(RuntimeError, match="snapshot unavailable"):
        build_model_bundle(CONFIG_PATH, destination, failing_download)
    assert calls == 1
    assert not destination.exists()
    assert list(tmp_path.glob(".bundle.staging-*")) == []


def test_builder_refuses_a_destination_created_during_snapshot_download(
    tmp_path: Path,
) -> None:
    """Catch an atomic install that replaces an empty concurrent destination."""

    destination = tmp_path / "bundle"
    calls: list[tuple[str, str]] = []
    download = _fake_snapshot_download(tmp_path, calls)

    def racing_download(*, repo_id: str, revision: str) -> str:
        if not destination.exists():
            destination.mkdir()
        return download(repo_id=repo_id, revision=revision)

    with pytest.raises(FileExistsError):
        build_model_bundle(CONFIG_PATH, destination, racing_download)
    assert destination.is_dir()
    assert calls == [
        ("IDEA-Research/grounding-dino-tiny", "a2bb814dd30d776dcf7e30523b00659f4f141c71"),
        ("facebook/sam2.1-hiera-tiny", "de431c4043854a71d8101e17995dfe596bf101a5"),
    ]
    assert list(tmp_path.glob(".bundle.staging-*")) == []


def test_builder_preserves_a_marked_destination_created_during_snapshot_download(
    tmp_path: Path,
) -> None:
    """Catch a race handler that removes data owned by a concurrent destination creator."""

    destination = tmp_path / "bundle"
    download = _fake_snapshot_download(tmp_path, [])

    def racing_download(*, repo_id: str, revision: str) -> str:
        if not destination.exists():
            destination.mkdir()
            (destination / "concurrent-owner.txt").write_text("preserve", encoding="utf-8")
        return download(repo_id=repo_id, revision=revision)

    with pytest.raises(FileExistsError):
        build_model_bundle(CONFIG_PATH, destination, racing_download)
    assert (destination / "concurrent-owner.txt").read_text(encoding="utf-8") == "preserve"
    assert list(tmp_path.glob(".bundle.staging-*")) == []


def test_cli_accepts_only_absolute_config_and_output_paths(monkeypatch, tmp_path: Path) -> None:
    """Catch the CLI accepting a working-directory-dependent bundle location."""

    calls: list[tuple[Path, Path]] = []

    def fake_build(config_path: Path, destination: Path, snapshot_download: object) -> str:
        calls.append((config_path, destination))
        return "a" * 64

    monkeypatch.setattr(
        "so101_demo.cli.prepare_grounded_sam_bundle.build_model_bundle", fake_build
    )
    assert main(["--config", str(CONFIG_PATH), "--output", str(tmp_path / "bundle")]) == 0
    assert calls == [(CONFIG_PATH, tmp_path / "bundle")]
    with pytest.raises(SystemExit):
        main(["--config", "relative.yaml", "--output", str(tmp_path / "bundle")])
    with pytest.raises(SystemExit):
        main(["--config", str(CONFIG_PATH), "--output", "relative-bundle"])


def test_setup_registers_the_prepare_grounded_sam_bundle_command(monkeypatch) -> None:
    """Catch a package build that omits the public bundle-preparation command."""

    captured: dict[str, object] = {}
    monkeypatch.setattr(setuptools, "setup", lambda **kwargs: captured.update(kwargs))
    monkeypatch.chdir(PACKAGE_ROOT)
    runpy.run_path(str(PACKAGE_ROOT / "setup.py"), run_name="__main__")

    entry_points = captured["entry_points"]
    assert isinstance(entry_points, dict)
    assert (
        "prepare_grounded_sam_bundle = "
        "so101_demo.cli.prepare_grounded_sam_bundle:main"
        in entry_points["console_scripts"]
    )
