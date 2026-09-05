"""Lossless, frame-bound DINO proposal receipts for serial val collection."""

from __future__ import annotations

import hashlib
import io
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np
from PIL import Image
from so101_demo.core.detection import DetectionFrame
from so101_demo.perception_benchmark.adapters.base import CollectionMode
from so101_demo.training.grounded_sam_val_calibration import (
    ValDataset,
    _read_canonical,
    _write_exclusive_json,
)

_MODEL_ID = "grounding-dino-tiny+sam2.1-hiera-tiny"
_SCHEMA = "so101-grounded-sam-proposal-receipts/v1"


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("PROPOSAL_RECEIPT_INVALID")


def _identity(dataset: ValDataset, source: str, model: str) -> dict[str, Any]:
    _require(isinstance(dataset, ValDataset) and bool(dataset.samples))
    _require(isinstance(source, str) and re.fullmatch(r"[0-9a-f]{40}", source) is not None)
    _require(isinstance(model, str) and re.fullmatch(r"[0-9a-f]{64}", model) is not None)
    return dict(
        schema_version=_SCHEMA,
        source_commit=source,
        model_manifest_sha256=model,
        val_inventory_sha256=dataset.inventory_sha256,
        source_manifest_sha256=dataset.source_manifest_sha256,
        prompt="cup.",
        label="cup",
        box_floor=0.01,
        text_floor=0.01,
    )


def _frame_identity(sample: Any) -> tuple[dict[str, Any], np.ndarray]:
    payload = sample.image_path.read_bytes()
    _require(hashlib.sha256(payload).hexdigest() == sample.image_sha256)
    with Image.open(io.BytesIO(payload)) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    return dict(
        formal_sample_index=sample.formal_sample_index,
        seed=sample.seed,
        image_sha256=sample.image_sha256,
        rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),
        source_stamp_ns=sample.seed,
        source_frame_id="synthetic_val_camera",
        image_height=int(rgb.shape[0]),
        image_width=int(rgb.shape[1]),
    ), rgb


@dataclass(frozen=True, slots=True)
class RetainedGroundingProposal:
    """A complete DINO proposal, independent of any SAM mask acceptance."""

    candidate_id: str
    bbox_xyxy: tuple[float, float, float, float]
    grounding_box_score: float
    grounding_text_score: float
    label: str = "cup"

    def document(self) -> dict[str, Any]:
        return dict(
            candidate_id=self.candidate_id,
            bbox_xyxy=list(self.bbox_xyxy),
            grounding_box_score=self.grounding_box_score,
            grounding_text_score=self.grounding_text_score,
            label=self.label,
        )


def _proposals(
    values: Sequence[Any], width: int, height: int
) -> tuple[RetainedGroundingProposal, ...]:
    output = []
    for index, (bbox, box_score, text_score) in enumerate(values):
        _require(len(bbox) == 4)
        _require(
            all(
                type(v) in (int, float) and math.isfinite(v) for v in (*bbox, box_score, text_score)
            )
        )
        _require(0.01 <= box_score <= 1 and 0.01 <= text_score <= 1)
        _require(0 <= bbox[0] < bbox[2] <= width and 0 <= bbox[1] < bbox[3] <= height)
        output.append(
            RetainedGroundingProposal(
                f"grounded-sam-{index:03d}", tuple(bbox), box_score, text_score
            )
        )
    _require(output == sorted(output, key=lambda p: (-p.grounding_box_score, p.bbox_xyxy)))
    return tuple(output)


def _survivors_match(
    candidates: Sequence[Any], proposals: Sequence[RetainedGroundingProposal]
) -> None:
    by_id = {p.candidate_id: p for p in proposals}
    seen = set()
    for candidate in candidates:
        _require(candidate.candidate_id not in seen and candidate.candidate_id in by_id)
        seen.add(candidate.candidate_id)
        proposal = by_id[candidate.candidate_id]
        _require(
            candidate.label == "cup"
            and candidate.bbox_xyxy == proposal.bbox_xyxy
            and candidate.grounding_box_score == proposal.grounding_box_score
            and candidate.grounding_text_score == proposal.grounding_text_score
        )


def _read(path: Path) -> tuple[dict[str, Any], str]:
    _require(path.is_file() and not path.is_symlink() and path.stat().st_nlink == 1)
    document, payload = _read_canonical(path, "PROPOSAL_RECEIPT_INVALID")
    return dict(document), hashlib.sha256(payload).hexdigest()


class ProposalReceiptAdapter:
    """Wrap one serial raw adapter; receipt failure poisons the whole run."""

    def __init__(
        self,
        *,
        dataset: ValDataset,
        evidence_root: Path,
        source_commit: str,
        model_manifest_sha256: str,
        adapter_factory: Callable[[Callable], Any],
    ) -> None:
        self._identity = _identity(dataset, source_commit, model_manifest_sha256)
        root = Path(evidence_root)
        _require(root.is_absolute() and root.is_dir() and not root.is_symlink())
        self._root = root
        self._receipts = root / "proposal-receipts"
        _require(not self._receipts.exists() and not self._receipts.is_symlink())
        self._receipts.mkdir()
        self._dataset = dataset
        self._hashes: list[str] = []
        self._survivors: list[tuple[Any, ...]] = []
        self._active: dict[str, Any] | None = None
        self._observed: tuple[RetainedGroundingProposal, ...] | None = None
        self._failed = False
        self._closed = False
        self._adapter = adapter_factory(self._observe)
        self._runtime()

    @property
    def model_id(self) -> str:
        return self._adapter.model_id

    @property
    def runtime_device(self) -> str:
        return self._adapter.runtime_device

    def _runtime(self) -> None:
        _require(self.model_id == _MODEL_ID and self.runtime_device == "cuda")

    def _observe(self, values: Sequence[Any]) -> None:
        try:
            self._persist_observation(values)
        except Exception as error:
            self._failed = True
            raise ValueError("PROPOSAL_RECEIPT_INVALID") from error

    def _persist_observation(self, values: Sequence[Any]) -> None:
        _require(self._active is not None and self._observed is None and not self._failed)
        active = self._active
        proposals = _proposals(values, active["image_width"], active["image_height"])
        document = {**self._identity, **active, "proposals": [p.document() for p in proposals]}
        path = self._receipts / f"{active['formal_sample_index']:06d}.json"
        digest = _write_exclusive_json(path, document)
        readback, readback_digest = _read(path)
        _require(readback == document and readback_digest == digest)
        self._hashes.append(digest)
        self._observed = proposals

    def collect(self, frame: DetectionFrame, mode: CollectionMode) -> Any:
        try:
            _require(not self._failed and not self._closed and self._active is None)
            _require(isinstance(frame, DetectionFrame) and mode == CollectionMode.LOW_FLOOR)
            _require(len(self._survivors) < len(self._dataset.samples))
            self._runtime()
            active, rgb = _frame_identity(self._dataset.samples[len(self._survivors)])
            _require(
                frame.source_stamp_ns == active["source_stamp_ns"]
                and frame.source_frame_id == active["source_frame_id"]
                and np.array_equal(frame.rgb8, rgb)
            )
            self._active, self._observed = active, None
            result = self._adapter.collect(frame, mode)
            _require(self._observed is not None and not self._failed)
            _survivors_match(result.raw_candidates, self._observed)
            self._runtime()
            self._survivors.append(tuple(result.raw_candidates))
            self._active = None
            return result
        except Exception as error:
            self._failed = True
            raise ValueError("PROPOSAL_RECEIPT_INVALID") from error

    def finalize(self) -> dict[str, Any]:
        """Seal the receipt inventory only after every expected frame completed."""
        try:
            _require(not self._failed and not self._closed and self._active is None)
            _require(len(self._survivors) == len(self._hashes) == len(self._dataset.samples))
            manifest = {
                **self._identity,
                "status": "VALID",
                "receipt_count": len(self._hashes),
                "receipt_sha256s": self._hashes.copy(),
            }
            # Verify all receipt bytes before publishing the terminal inventory.
            _, hashes = _verify_members(
                self._receipts, self._dataset, self._identity, self._survivors
            )
            _require(hashes == self._hashes)
            _require(len(list(self._receipts.iterdir())) == len(self._hashes))
            _write_exclusive_json(self._receipts / "manifest.json", manifest)
            load_verified_proposal_receipts(
                self._root,
                dataset=self._dataset,
                expected_source_commit=self._identity["source_commit"],
                expected_model_manifest_sha256=self._identity["model_manifest_sha256"],
                raw_candidates_by_sample=self._survivors,
            )
            self._closed = True
            return manifest
        except Exception as error:
            self._failed = True
            raise ValueError("PROPOSAL_RECEIPT_INVALID") from error


def _verify_members(
    receipts: Path,
    dataset: ValDataset,
    identity: dict[str, Any],
    raw_candidates_by_sample: Sequence[Sequence[Any]],
) -> tuple[Any, list[str]]:
    _require(len(raw_candidates_by_sample) == len(dataset.samples))
    output, hashes = [], []
    for sample, candidates in zip(dataset.samples, raw_candidates_by_sample, strict=True):
        document, digest = _read(receipts / f"{sample.formal_sample_index:06d}.json")
        frame_identity, _ = _frame_identity(sample)
        proposals = _proposals(
            tuple(
                (p["bbox_xyxy"], p["grounding_box_score"], p["grounding_text_score"])
                for p in document["proposals"]
            ),
            frame_identity["image_width"],
            frame_identity["image_height"],
        )
        _require(
            document
            == {**identity, **frame_identity, "proposals": [p.document() for p in proposals]}
        )
        _survivors_match(candidates, proposals)
        hashes.append(digest)
        output.append(proposals)
    return tuple(output), hashes


def load_verified_proposal_receipts(
    root: Path,
    *,
    dataset: ValDataset,
    expected_source_commit: str,
    expected_model_manifest_sha256: str,
    raw_candidates_by_sample: Sequence[Sequence[Any]],
) -> tuple[tuple[RetainedGroundingProposal, ...], ...]:
    """Read all receipts and prove frame/model identity and raw-survivor coverage."""
    try:
        identity = _identity(dataset, expected_source_commit, expected_model_manifest_sha256)
        root = Path(root)
        _require(root.is_absolute() and root.is_dir() and not root.is_symlink())
        receipts = root / "proposal-receipts"
        _require(receipts.is_dir() and not receipts.is_symlink())
        manifest, _ = _read(receipts / "manifest.json")
        count = len(dataset.samples)
        _require(len(raw_candidates_by_sample) == count)
        _require(
            {p.name for p in receipts.iterdir()}
            == {"manifest.json", *(f"{i:06d}.json" for i in range(count))}
        )
        output, hashes = _verify_members(receipts, dataset, identity, raw_candidates_by_sample)
        _require(
            manifest
            == {**identity, "status": "VALID", "receipt_count": count, "receipt_sha256s": hashes}
        )
        return tuple(output)
    except Exception as error:
        raise ValueError("PROPOSAL_RECEIPT_INVALID") from error
