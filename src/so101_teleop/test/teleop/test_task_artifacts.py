import hashlib
import json
from pathlib import Path

import pytest

from so101_teleop.task_artifacts import (
    ArtifactAccessError,
    ManifestArtifactStore,
)


PNG = b"\x89PNG\r\n\x1a\n" + b"task-view"


def test_registered_artifact_opens_by_opaque_id_and_verifies_content(tmp_path):
    store = ManifestArtifactStore(tmp_path / "evidence")
    source = store.root / "captures/c1/full-cloud.ply"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"ply\nformat ascii 1.0\nend_header\n")

    record = store.register_file(
        source, "application/octet-stream", capture_id="c1"
    )
    opened = store.open(record.artifact_id)

    assert opened.path == source
    assert opened.media_type == "application/octet-stream"
    assert opened.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()


@pytest.mark.parametrize("relative_path", ["../../etc/passwd", "/etc/passwd"])
def test_manifest_escape_is_rejected(tmp_path, relative_path):
    store = ManifestArtifactStore(tmp_path / "evidence")
    manifest = {
        "schema_version": 1,
        "artifacts": [{
            "artifact_id": "bad-id",
            "relative_path": relative_path,
            "media_type": "text/plain",
            "byte_size": 1,
            "sha256": "0" * 64,
            "capture_id": None,
            "run_id": None,
            "source_artifact_id": None,
            "metadata": {},
        }],
    }
    store.manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ArtifactAccessError, match="ARTIFACT_PATH_INVALID"):
        ManifestArtifactStore(store.root).open("bad-id")


def test_symlink_and_checksum_drift_are_rejected(tmp_path):
    store = ManifestArtifactStore(tmp_path / "evidence")
    source = store.root / "captures/c1/rgb.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(PNG)
    record = store.register_file(source, "image/png", capture_id="c1")
    source.write_bytes(PNG + b"changed")
    with pytest.raises(ArtifactAccessError, match="ARTIFACT_CHECKSUM_MISMATCH"):
        store.open(record.artifact_id)

    target = tmp_path / "foreign.png"
    target.write_bytes(PNG)
    source.unlink()
    source.symlink_to(target)
    with pytest.raises(ArtifactAccessError, match="ARTIFACT_PATH_INVALID"):
        store.open(record.artifact_id)


def test_symlinked_global_manifest_is_rejected(tmp_path):
    store = ManifestArtifactStore(tmp_path / "evidence")
    foreign = tmp_path / "foreign.json"
    foreign.write_text('{"schema_version":1,"artifacts":[]}')
    store.manifest_path.unlink()
    store.manifest_path.symlink_to(foreign)
    with pytest.raises(ArtifactAccessError, match="ARTIFACT_MANIFEST_INVALID"):
        store.open("unknown")


def test_rendered_png_requires_same_capture_ply_and_finite_metadata(tmp_path):
    store = ManifestArtifactStore(tmp_path / "evidence")
    ply = store.root / "captures/c1/full-cloud.ply"
    ply.parent.mkdir(parents=True)
    ply.write_bytes(b"ply\n")
    source = store.register_file(
        ply, "application/octet-stream", capture_id="c1"
    )
    metadata = {
        "view_matrix": [0.0] * 16,
        "projection_matrix": [0.0] * 16,
        "point_size": 1.0,
        "viewport_width": 800,
        "viewport_height": 600,
    }

    rendered = store.register_rendered_image(
        "c1", source.artifact_id, PNG, metadata
    )

    assert store.open(rendered.artifact_id).path.read_bytes() == PNG
    with pytest.raises(ArtifactAccessError, match="RENDER_METADATA_INVALID"):
        store.register_rendered_image(
            "c1",
            source.artifact_id,
            PNG,
            {**metadata, "point_size": float("nan")},
        )
    with pytest.raises(ArtifactAccessError, match="RENDER_PNG_INVALID"):
        store.register_rendered_image(
            "c1", source.artifact_id, b"not-png", metadata
        )
    with pytest.raises(ArtifactAccessError, match="RENDER_SOURCE_INVALID"):
        store.register_rendered_image(
            "different-capture", source.artifact_id, PNG, metadata
        )
