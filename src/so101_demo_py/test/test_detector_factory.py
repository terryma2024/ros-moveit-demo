from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from so101_demo.adapters.perception.detector_factory import (
    DetectorFactoryOptions,
    build_detector,
)
from so101_demo.adapters.perception.grounded_sam_postprocess import GroundedSamThresholds
from so101_demo.runtime.perception_evidence import PerceptionEvidenceWriter


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _grounded_bundle(tmp_path: Path) -> tuple[Path, str, dict[str, object]]:
    root = (tmp_path / "bundle").resolve()
    detector = root / "grounding-dino-tiny"
    segmenter = root / "sam2.1-hiera-tiny"
    detector.mkdir(parents=True)
    segmenter.mkdir()
    (detector / "config.json").write_bytes(b"detector-config")
    (segmenter / "model.safetensors").write_bytes(b"segmenter-weights")
    document: dict[str, object] = {
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
        "files": [
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
        ],
        "dependencies": {},
    }
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
    (root / "manifest.json").write_text(payload, encoding="utf-8")
    return root, _sha256(payload.encode("utf-8")), document


class _FakeGroundedSamDetector:
    runtime_device = "mps"
    cold_start_latency_ms = 12.5
    model_id = "grounding-dino-tiny+sam2.1-hiera-tiny"


def _grounded_options(tmp_path: Path) -> DetectorFactoryOptions:
    root, digest, _document = _grounded_bundle(tmp_path)
    return DetectorFactoryOptions(
        backend="grounded_sam",
        requested_device="mps",
        allow_cpu_fallback=False,
        grounded_model_root=root,
        grounded_manifest_sha256=digest,
        grounded_thresholds=GroundedSamThresholds.defaults(),
    )


def test_factory_builds_grounded_sam_from_verified_bundle(tmp_path: Path) -> None:
    """Catch bypassing immutable bundle verification or omitting its provenance."""

    calls: list[dict[str, Any]] = []

    def fake_grounded_detector_factory(**kwargs: Any) -> _FakeGroundedSamDetector:
        calls.append(kwargs)
        return _FakeGroundedSamDetector()

    built = build_detector(
        _grounded_options(tmp_path),
        grounded_detector_factory=fake_grounded_detector_factory,
    )

    assert isinstance(built.detector, _FakeGroundedSamDetector)
    assert built.cold_start_latency_ms == 12.5
    assert built.provenance_document["pipeline_id"] == "grounding-dino-tiny+sam2.1-hiera-tiny"
    assert built.provenance_document["manifest_sha256"] == calls[0]["bundle"].manifest_sha256
    assert built.provenance_document["manifest"] == calls[0]["bundle"].manifest


@pytest.mark.parametrize("backend", ["yolo_seg", "grounded_sam"])
def test_factory_rejects_missing_or_cross_backend_artifacts(
    tmp_path: Path, backend: str
) -> None:
    """Catch a backend accepting a missing artifact or another backend's artifact."""

    root, digest, _document = _grounded_bundle(tmp_path)
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    options = DetectorFactoryOptions(
        backend=backend,  # type: ignore[arg-type]
        requested_device="mps",
        allow_cpu_fallback=False,
        yolo_weights_path=weights if backend == "grounded_sam" else None,
        yolo_weights_sha256=_sha256(b"weights") if backend == "grounded_sam" else None,
        grounded_model_root=root if backend == "yolo_seg" else None,
        grounded_manifest_sha256=digest if backend == "yolo_seg" else None,
        grounded_thresholds=GroundedSamThresholds.defaults(),
    )

    with pytest.raises(ValueError, match="backend configuration"):
        build_detector(options)


def test_model_provenance_is_atomic_and_never_overwritten(tmp_path: Path) -> None:
    """Catch replacing the immutable model identity after request setup."""

    root = (tmp_path / "evidence").resolve()
    writer = PerceptionEvidenceWriter()

    path = writer.write_model_provenance(root, {"backend": "grounded_sam"})

    assert json.loads(Path(path).read_text(encoding="utf-8")) == {"backend": "grounded_sam"}
    with pytest.raises(FileExistsError, match="model provenance path already exists"):
        writer.write_model_provenance(root, {"backend": "yolo_seg"})
    assert json.loads(Path(path).read_text(encoding="utf-8")) == {"backend": "grounded_sam"}
