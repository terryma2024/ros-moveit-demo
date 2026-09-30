"""Register a Head Search candidate and freeze its operating point for the selection gate.

The consumer side already exists: ``load_frozen_candidate`` reads a six-key document and refuses
anything it cannot apply. This module is the producer for that contract, so a frozen candidate is
built to the validator's rules rather than to a description of them (HS-201/202/205):

    candidate_id  weight_sha256  promotable
    operating_points.head/.task = {min_confidence, tracker: {iou}}
    tracker/postprocess/runtime empty at document level

``register_candidate`` digesting weights reads its inputs and never writes to them: the pinned A
weights stay byte-identical because the plan pins them by sha256.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping

CANDIDATE_IDS = ("A", "B", "C")


class CandidateFreezeError(RuntimeError):
    """A candidate could not be registered or frozen under the validator's rules."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def register_candidate(*, candidate_id: str, weights: Path, output_root: Path) -> dict[str, object]:
    """Write one candidate manifest binding the candidate id to its weight digest.

    Refuses an unknown candidate id or missing weights, and never modifies ``weights``.
    """

    if candidate_id not in CANDIDATE_IDS:
        raise CandidateFreezeError(
            f"CANDIDATE_MANIFEST_INVALID: {candidate_id!r} is not one of {CANDIDATE_IDS}"
        )
    weights = Path(weights)
    if not weights.is_file():
        raise CandidateFreezeError(f"CANDIDATE_MANIFEST_INVALID: no weights at {weights}")
    document = {
        "schema_version": 1,
        "kind": "head-search-candidate",
        "candidate_id": candidate_id,
        "weights": str(weights),
        "weight_sha256": sha256_file(weights),
    }
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    manifest = root / "candidate-manifest.json"
    if manifest.exists():
        raise CandidateFreezeError(f"CANDIDATE_MANIFEST_INVALID: {manifest} already exists")
    manifest.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return document


def freeze_candidate(
    *,
    candidate_id: str,
    weight_sha256: str,
    min_confidence: float,
    tracking_iou: float,
    output: Path,
) -> dict[str, object]:
    """Write the frozen operating point the selection gate loads.

    The gate applies exactly two values - ``min_confidence`` as the detector's confidence and the
    tracker's ``{"iou": ...}`` as its NMS threshold - and refuses any other declaration as
    unsupported, so the document carries those and nothing else. The same operating point is sealed
    for both domains because calibration measures them on the same val/calibration split pair.

    ``promotable`` is written true: a candidate that is not promotable never enters model selection
    (HS-052), and this producer exists only for candidates that may.
    """

    if candidate_id not in CANDIDATE_IDS:
        raise CandidateFreezeError(
            f"EVALUATION_FROZEN_IDENTITY_INVALID: {candidate_id!r} is not one of {CANDIDATE_IDS}"
        )
    if len(weight_sha256) != 64 or any(c not in "0123456789abcdef" for c in weight_sha256):
        raise CandidateFreezeError(
            "EVALUATION_FROZEN_IDENTITY_INVALID: the weight digest must be sha256 hex"
        )
    for name, value in (("min_confidence", min_confidence), ("tracking_iou", tracking_iou)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
            raise CandidateFreezeError(
                f"EVALUATION_FROZEN_IDENTITY_INVALID: {name} must be a number in [0, 1]"
            )
    point = {"min_confidence": float(min_confidence), "tracker": {"iou": float(tracking_iou)}}
    document = {
        "schema_version": 1,
        "kind": "head-search-frozen-candidate",
        "candidate_id": candidate_id,
        "weight_sha256": weight_sha256,
        "promotable": True,
        "operating_points": {"head": dict(point), "task": dict(point)},
        # empty at document level: the gate refuses any declaration it cannot apply
        "tracker": {},
        "postprocess": {},
        "runtime": {},
    }
    output = Path(output)
    if output.exists():
        raise CandidateFreezeError(f"EVALUATION_FROZEN_IDENTITY_INVALID: {output} already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return document
