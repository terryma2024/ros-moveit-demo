from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

import pytest


def test_registry_allocates_exclusive_batch_and_registers_checksum(tmp_path: Path) -> None:
    from so101_demo.runtime.task_artifacts import (
        ArtifactRegistryError,
        TaskArtifactRegistry,
    )

    registry = TaskArtifactRegistry(
        tmp_path,
        clock=lambda: datetime(2026, 8, 27, 5, 0, tzinfo=UTC),
    )
    batch = registry.allocate_batch("batch-1")
    point = registry.allocate_point(batch, 1, "task_start")
    payload = point / "point.json"
    payload.write_text('{"status":"RUNNING"}\n')

    artifact = registry.register_file(
        "point-input", payload, "application/json", "sim-a", 1
    )

    digest = hashlib.sha256(payload.read_bytes()).hexdigest()
    assert artifact.relative_path == "batches/batch-1/points/01-task_start/point.json"
    assert artifact.sha256 == digest
    assert artifact.byte_size == len(payload.read_bytes())
    assert artifact.artifact_id == hashlib.sha256(
        f"{artifact.relative_path}\0{digest}".encode()
    ).hexdigest()[:24]
    assert artifact.producing_process == "point-input"
    assert artifact.simulation_session_id == "sim-a"
    assert artifact.reset_epoch == 1
    assert artifact.captured_at == "2026-08-27T05:00:00+00:00"
    with pytest.raises(FrozenInstanceError):
        artifact.sha256 = "changed"  # type: ignore[misc]
    with pytest.raises(ArtifactRegistryError, match="already exists"):
        registry.allocate_batch("batch-1")


def test_registry_rejects_symlink_and_outside_root(tmp_path: Path) -> None:
    from so101_demo.runtime.task_artifacts import (
        ArtifactRegistryError,
        TaskArtifactRegistry,
    )

    registry = TaskArtifactRegistry(tmp_path / "root")
    outside = tmp_path / "outside"
    outside.write_text("secret")
    link = registry.root / "escape"
    link.symlink_to(outside)

    with pytest.raises(ArtifactRegistryError, match="symlink"):
        registry.register_file("escape", link, "text/plain", "sim-a", 1)
    with pytest.raises(ArtifactRegistryError, match="outside"):
        registry.register_file("escape", outside, "text/plain", "sim-a", 1)


@pytest.mark.parametrize("unsafe", ["../escape", "a/b", "", ".", "white space"])
def test_registry_rejects_unsafe_batch_and_point_ids(
    tmp_path: Path, unsafe: str
) -> None:
    from so101_demo.runtime.task_artifacts import (
        ArtifactRegistryError,
        TaskArtifactRegistry,
    )

    registry = TaskArtifactRegistry(tmp_path)
    with pytest.raises(ArtifactRegistryError, match="unsafe"):
        registry.allocate_batch(unsafe)
    batch = registry.allocate_batch("safe-batch")
    with pytest.raises(ArtifactRegistryError, match="unsafe"):
        registry.allocate_point(batch, 1, unsafe)


def test_atomic_json_replaces_complete_document_without_temporary_file(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.task_artifacts import atomic_json

    target = tmp_path / "manifest.json"
    target.write_text('{"old":true}\n')
    atomic_json(target, {"status": "SUCCEEDED", "count": 2})

    assert json.loads(target.read_text()) == {"status": "SUCCEEDED", "count": 2}
    assert list(tmp_path.glob(".*.tmp")) == []


def test_point_allocation_requires_owned_batch_and_is_exclusive(tmp_path: Path) -> None:
    from so101_demo.runtime.task_artifacts import (
        ArtifactRegistryError,
        TaskArtifactRegistry,
    )

    registry = TaskArtifactRegistry(tmp_path / "root")
    other = TaskArtifactRegistry(tmp_path / "other")
    batch = registry.allocate_batch("batch")
    point = registry.allocate_point(batch, 12, "right")
    assert point.relative_to(registry.root).as_posix() == "batches/batch/points/12-right"
    with pytest.raises(ArtifactRegistryError, match="already exists"):
        registry.allocate_point(batch, 12, "right")
    with pytest.raises(ArtifactRegistryError, match="owned batch"):
        other.allocate_point(batch, 1, "task_start")
