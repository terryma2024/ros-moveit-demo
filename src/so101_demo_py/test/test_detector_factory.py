from __future__ import annotations

import hashlib
import json
import multiprocessing
from pathlib import Path
from typing import Any

import pytest
from so101_demo.adapters.perception.detector_factory import (
    DetectorFactoryOptions,
    build_detector,
)
from so101_demo.adapters.perception.grounded_sam_postprocess import GroundedSamThresholds
from so101_demo.runtime.perception_evidence import PerceptionEvidenceWriter

LOCKED_DEPENDENCIES = {
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
        "dependencies": LOCKED_DEPENDENCIES,
    }
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
    (root / "manifest.json").write_text(payload, encoding="utf-8")
    return root, _sha256(payload.encode("utf-8")), document


class _FakeGroundedSamDetector:
    runtime_device = "mps"
    cold_start_latency_ms = 12.5
    model_id = "grounding-dino-tiny+sam2.1-hiera-tiny"


class _FakeYoloDetector:
    runtime_device = "mps"
    cold_start_latency_ms = 4.0


def _concurrent_provenance_write(
    root: str,
    document: dict[str, str],
    barrier: Any,
    result_queue: Any,
) -> None:
    try:
        barrier.wait()
        PerceptionEvidenceWriter().write_model_provenance(Path(root), document)
    except FileExistsError:
        result_queue.put(("exists", document["backend"]))
    except BaseException as error:
        result_queue.put(("error", repr(error)))
    else:
        result_queue.put(("written", document["backend"]))


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


def test_factory_builds_yolo_with_verified_weight_provenance(tmp_path: Path) -> None:
    """Catch losing the verified YOLO digest or caller-selected model settings."""

    weights = tmp_path / "best.pt"
    weights.write_bytes(b"verified-yolo-weights")
    calls: list[dict[str, Any]] = []

    def fake_yolo_detector_factory(**kwargs: Any) -> _FakeYoloDetector:
        calls.append(kwargs)
        return _FakeYoloDetector()

    built = build_detector(
        DetectorFactoryOptions(
            backend="yolo_seg",
            requested_device="mps",
            allow_cpu_fallback=False,
            yolo_weights_path=weights,
            yolo_weights_sha256=_sha256(b"verified-yolo-weights"),
            yolo_model_id="plastic-cup-yolo11s-seg-v2",
            yolo_imgsz=512,
        ),
        yolo_detector_factory=fake_yolo_detector_factory,
    )

    assert isinstance(built.detector, _FakeYoloDetector)
    assert calls == [
        {
            "weights_path": weights,
            "expected_sha256": _sha256(b"verified-yolo-weights"),
            "requested_device": "mps",
            "allow_cpu_fallback": False,
            "model_id": "plastic-cup-yolo11s-seg-v2",
            "imgsz": 512,
        }
    ]
    assert built.provenance_document == {
        "backend": "yolo_seg",
        "model_id": "plastic-cup-yolo11s-seg-v2",
        "weights_sha256": _sha256(b"verified-yolo-weights"),
    }


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


def test_concurrent_model_provenance_writers_preserve_the_first_document(
    tmp_path: Path,
) -> None:
    """Catch a second concurrent provenance writer replacing the winner's document."""

    context = multiprocessing.get_context("fork")
    root = (tmp_path / "evidence").resolve()
    documents = [{"backend": f"backend-{index}"} for index in range(4)]
    barrier = context.Barrier(len(documents) + 1)
    result_queue = context.Queue()
    processes = [
        context.Process(
            target=_concurrent_provenance_write,
            args=(str(root), document, barrier, result_queue),
        )
        for document in documents
    ]
    for process in processes:
        process.start()
    barrier.wait()
    results = [result_queue.get(timeout=5.0) for _document in documents]
    for process in processes:
        process.join(timeout=5.0)
        assert process.exitcode == 0

    winners = [backend for status, backend in results if status == "written"]
    assert len(winners) == 1
    assert [status for status, _detail in results].count("exists") == 3
    assert json.loads((root / "model-provenance.json").read_text(encoding="utf-8")) == {
        "backend": winners[0]
    }
