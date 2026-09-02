"""Deterministic per-image comparison of frozen Mac and Linux records."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

import numpy as np

from so101_demo.perception_benchmark.codec import read_mask
from so101_demo.perception_benchmark.contracts import PredictionRecord, RawCandidate
from so101_demo.perception_benchmark.matching import _hungarian_minimize, mask_iou


@dataclass(frozen=True, slots=True)
class CandidatePairComparison:
    """One Hungarian-paired candidate comparison across two platforms."""

    mac_candidate_id: str
    linux_candidate_id: str
    ranking_score_source_equal: bool
    mac_ranking_score_source: str
    linux_ranking_score_source: str
    ranking_score_absolute_delta: float
    ranking_score_relative_delta: float | None
    confidence_absolute_delta: float
    confidence_relative_delta: float | None
    class_confidence_presence_equal: bool
    class_confidence_absolute_delta: float | None
    class_confidence_relative_delta: float | None
    grounding_box_score_presence_equal: bool
    grounding_box_score_absolute_delta: float | None
    grounding_box_score_relative_delta: float | None
    grounding_text_score_presence_equal: bool
    grounding_text_score_absolute_delta: float | None
    grounding_text_score_relative_delta: float | None
    sam_quality_presence_equal: bool
    sam_quality_absolute_delta: float | None
    sam_quality_relative_delta: float | None
    mask_iou: float
    box_iou: float


@dataclass(frozen=True, slots=True)
class CrossPlatformItem:
    """All exact comparison results for one composite image identity."""

    formal_sample_index: int
    image_sha256: str
    model_id: str
    config_sha256: str
    run_kind: str
    mac_candidate_ids: tuple[str, ...]
    linux_candidate_ids: tuple[str, ...]
    candidate_count_equal: bool
    candidate_ids_equal: bool
    candidate_pairs: tuple[CandidatePairComparison, ...]
    unmatched_mac_candidate_ids: tuple[str, ...]
    unmatched_linux_candidate_ids: tuple[str, ...]
    decision_equal: bool
    error_type_equal: bool
    mac_decision: str
    linux_decision: str
    mac_error_type: str | None
    linux_error_type: str | None
    mac_runtime_device: str
    linux_runtime_device: str
    runtime_device_pair_expected: bool
    weights_sha256_equal: bool
    runtime_name_equal: bool
    runtime_version_equal: bool
    runtime_environment_equal: bool
    runtime_environment_identity_equal: bool
    mac_runtime_environment: Mapping[str, str]
    linux_runtime_environment: Mapping[str, str]
    is_mismatch: bool


@dataclass(frozen=True, slots=True)
class CrossPlatformSummary:
    """Complete, ordered cross-platform comparison without float suppression."""

    pair_count: int
    mismatch_count: int
    mismatch_image_shas: tuple[str, ...]
    items: tuple[CrossPlatformItem, ...]


def _identity(record: PredictionRecord) -> tuple[int, str, str, str, str]:
    return (
        record.formal_sample_index,
        record.image_sha256,
        record.model_id,
        record.config_sha256,
        record.run_kind.value,
    )


def _validated_records(
    name: str, records: Sequence[PredictionRecord]
) -> dict[tuple[int, str, str, str, str], PredictionRecord]:
    items = tuple(records)
    if not all(isinstance(record, PredictionRecord) for record in items):
        raise ValueError(f"{name} must contain PredictionRecord values")
    result = {_identity(record): record for record in items}
    if len(result) != len(items):
        raise ValueError(f"{name} composite identities must be unique")
    return result


def _required_root(name: str, value: Path | None) -> Path:
    if value is None:
        raise ValueError(f"{name} is required when candidate masks are present")
    try:
        root = Path(value).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError(f"{name} must be an existing directory") from error
    if not root.is_dir():
        raise ValueError(f"{name} must be an existing directory")
    return root


def _box_iou(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    first_x0, first_y0, first_x1, first_y1 = first
    second_x0, second_y0, second_x1, second_y1 = second
    intersection_width = max(0.0, min(first_x1, second_x1) - max(first_x0, second_x0))
    intersection_height = max(0.0, min(first_y1, second_y1) - max(first_y0, second_y0))
    intersection = intersection_width * intersection_height
    first_area = (first_x1 - first_x0) * (first_y1 - first_y0)
    second_area = (second_x1 - second_x0) * (second_y1 - second_y0)
    union = first_area + second_area - intersection
    return 0.0 if union == 0.0 else float(intersection / union)


def _relative_delta(first: float, second: float) -> float | None:
    absolute = abs(first - second)
    if second == 0.0:
        return 0.0 if absolute == 0.0 else None
    return float(absolute / abs(second))


def _optional_score_delta(
    first: float | None,
    second: float | None,
) -> tuple[bool, float | None, float | None]:
    presence_equal = (first is None) == (second is None)
    if first is None or second is None:
        return presence_equal, None, None
    absolute = float(abs(first - second))
    return presence_equal, absolute, _relative_delta(first, second)


_PLATFORM_ENVIRONMENT_KEYS = frozenset(
    {
        "accelerator",
        "architecture",
        "device",
        "machine",
        "operating_system",
        "os",
        "platform",
        "runtime_device",
    }
)


def _runtime_environment_identity(
    environment: Mapping[str, str],
) -> Mapping[str, str]:
    return MappingProxyType(
        {
            key: value
            for key, value in sorted(environment.items())
            if key not in _PLATFORM_ENVIRONMENT_KEYS
        }
    )


def _candidate_pairs(
    mac_candidates: tuple[RawCandidate, ...],
    linux_candidates: tuple[RawCandidate, ...],
    mac_root: Path | None,
    linux_root: Path | None,
) -> tuple[
    tuple[CandidatePairComparison, ...], tuple[str, ...], tuple[str, ...]
]:
    ordered_mac = tuple(sorted(mac_candidates, key=lambda candidate: candidate.candidate_id))
    ordered_linux = tuple(
        sorted(linux_candidates, key=lambda candidate: candidate.candidate_id)
    )
    if not ordered_mac or not ordered_linux:
        return (
            (),
            tuple(candidate.candidate_id for candidate in ordered_mac),
            tuple(candidate.candidate_id for candidate in ordered_linux),
        )
    if mac_root is None or linux_root is None:
        raise ValueError("both evidence roots are required for candidate comparison")
    mac_masks = tuple(read_mask(candidate.mask, mac_root) for candidate in ordered_mac)
    linux_masks = tuple(
        read_mask(candidate.mask, linux_root) for candidate in ordered_linux
    )
    ious = np.asarray(
        [
            [mask_iou(mac_mask, linux_mask) for linux_mask in linux_masks]
            for mac_mask in mac_masks
        ],
        dtype=np.float64,
    )
    assignment = _hungarian_minimize(-ious)
    pairs: list[CandidatePairComparison] = []
    paired_mac: set[int] = set()
    paired_linux: set[int] = set()
    for mac_index, linux_index in enumerate(assignment):
        if linux_index is None:
            continue
        mac_candidate = ordered_mac[mac_index]
        linux_candidate = ordered_linux[linux_index]
        absolute_delta = abs(
            mac_candidate.ranking_score - linux_candidate.ranking_score
        )
        class_delta = _optional_score_delta(
            mac_candidate.class_confidence,
            linux_candidate.class_confidence,
        )
        box_score_delta = _optional_score_delta(
            mac_candidate.grounding_box_score,
            linux_candidate.grounding_box_score,
        )
        text_score_delta = _optional_score_delta(
            mac_candidate.grounding_text_score,
            linux_candidate.grounding_text_score,
        )
        quality_delta = _optional_score_delta(
            mac_candidate.sam_quality,
            linux_candidate.sam_quality,
        )
        pairs.append(
            CandidatePairComparison(
                mac_candidate_id=mac_candidate.candidate_id,
                linux_candidate_id=linux_candidate.candidate_id,
                ranking_score_source_equal=(
                    mac_candidate.ranking_score_source
                    == linux_candidate.ranking_score_source
                ),
                mac_ranking_score_source=mac_candidate.ranking_score_source,
                linux_ranking_score_source=linux_candidate.ranking_score_source,
                ranking_score_absolute_delta=float(absolute_delta),
                ranking_score_relative_delta=_relative_delta(
                    mac_candidate.ranking_score, linux_candidate.ranking_score
                ),
                confidence_absolute_delta=float(absolute_delta),
                confidence_relative_delta=_relative_delta(
                    mac_candidate.ranking_score, linux_candidate.ranking_score
                ),
                class_confidence_presence_equal=class_delta[0],
                class_confidence_absolute_delta=class_delta[1],
                class_confidence_relative_delta=class_delta[2],
                grounding_box_score_presence_equal=box_score_delta[0],
                grounding_box_score_absolute_delta=box_score_delta[1],
                grounding_box_score_relative_delta=box_score_delta[2],
                grounding_text_score_presence_equal=text_score_delta[0],
                grounding_text_score_absolute_delta=text_score_delta[1],
                grounding_text_score_relative_delta=text_score_delta[2],
                sam_quality_presence_equal=quality_delta[0],
                sam_quality_absolute_delta=quality_delta[1],
                sam_quality_relative_delta=quality_delta[2],
                mask_iou=float(ious[mac_index, linux_index]),
                box_iou=_box_iou(
                    mac_candidate.bbox_xyxy, linux_candidate.bbox_xyxy
                ),
            )
        )
        paired_mac.add(mac_index)
        paired_linux.add(linux_index)
    pairs.sort(key=lambda item: (item.mac_candidate_id, item.linux_candidate_id))
    return (
        tuple(pairs),
        tuple(
            candidate.candidate_id
            for index, candidate in enumerate(ordered_mac)
            if index not in paired_mac
        ),
        tuple(
            candidate.candidate_id
            for index, candidate in enumerate(ordered_linux)
            if index not in paired_linux
        ),
    )


def _records_match_image(mac: PredictionRecord, linux: PredictionRecord) -> None:
    fields = (
        "formal_sample_index",
        "split",
        "scenario",
        "image_relpath",
        "image_sha256",
        "image_width",
        "image_height",
        "model_id",
        "config_sha256",
        "threshold_lock_sha256",
        "run_kind",
    )
    if any(getattr(mac, field) != getattr(linux, field) for field in fields):
        raise ValueError("cross-platform records do not share one composite identity")


def compare_platforms(
    mac_records: Sequence[PredictionRecord],
    linux_records: Sequence[PredictionRecord],
    *,
    mac_evidence_root: Path | None = None,
    linux_evidence_root: Path | None = None,
) -> CrossPlatformSummary:
    """Compare every paired record and list every exact mismatch.

    Roots remain optional for the backward-compatible empty-candidate case. If either
    platform has any candidate mask, both platform roots are required and verified.
    """

    mac_by_identity = _validated_records("mac_records", mac_records)
    linux_by_identity = _validated_records("linux_records", linux_records)
    if set(mac_by_identity) != set(linux_by_identity):
        raise ValueError("platform records must cover the same composite identities")
    has_mac_candidates = any(record.raw_candidates for record in mac_by_identity.values())
    has_linux_candidates = any(
        record.raw_candidates for record in linux_by_identity.values()
    )
    mac_root = (
        _required_root("mac_evidence_root", mac_evidence_root)
        if has_mac_candidates or has_linux_candidates
        else None
    )
    linux_root = (
        _required_root("linux_evidence_root", linux_evidence_root)
        if has_mac_candidates or has_linux_candidates
        else None
    )

    items: list[CrossPlatformItem] = []
    for identity in sorted(mac_by_identity):
        mac = mac_by_identity[identity]
        linux = linux_by_identity[identity]
        _records_match_image(mac, linux)
        mac_ids = tuple(
            candidate.candidate_id
            for candidate in sorted(
                mac.raw_candidates, key=lambda candidate: candidate.candidate_id
            )
        )
        linux_ids = tuple(
            candidate.candidate_id
            for candidate in sorted(
                linux.raw_candidates, key=lambda candidate: candidate.candidate_id
            )
        )
        pairs, unmatched_mac, unmatched_linux = _candidate_pairs(
            mac.raw_candidates,
            linux.raw_candidates,
            mac_root,
            linux_root,
        )
        decision_equal = mac.decision is linux.decision
        error_type_equal = mac.error_type == linux.error_type
        mac_provenance = mac.runtime_provenance
        linux_provenance = linux.runtime_provenance
        weights_equal = (
            mac_provenance.weights_sha256 == linux_provenance.weights_sha256
        )
        runtime_name_equal = (
            mac_provenance.runtime_name == linux_provenance.runtime_name
        )
        runtime_version_equal = (
            mac_provenance.runtime_version == linux_provenance.runtime_version
        )
        mac_environment = MappingProxyType(dict(mac_provenance.environment))
        linux_environment = MappingProxyType(dict(linux_provenance.environment))
        environment_equal = mac_environment == linux_environment
        environment_identity_equal = (
            _runtime_environment_identity(mac_environment)
            == _runtime_environment_identity(linux_environment)
        )
        device_pair_expected = (
            mac_provenance.runtime_device == "mps"
            and linux_provenance.runtime_device == "cuda"
        )
        pair_mismatch = any(
            not pair.ranking_score_source_equal
            or pair.ranking_score_absolute_delta != 0.0
            or not pair.class_confidence_presence_equal
            or (pair.class_confidence_absolute_delta or 0.0) != 0.0
            or not pair.grounding_box_score_presence_equal
            or (pair.grounding_box_score_absolute_delta or 0.0) != 0.0
            or not pair.grounding_text_score_presence_equal
            or (pair.grounding_text_score_absolute_delta or 0.0) != 0.0
            or not pair.sam_quality_presence_equal
            or (pair.sam_quality_absolute_delta or 0.0) != 0.0
            or pair.mask_iou != 1.0
            or pair.box_iou != 1.0
            for pair in pairs
        )
        is_mismatch = (
            len(mac_ids) != len(linux_ids)
            or mac_ids != linux_ids
            or bool(unmatched_mac)
            or bool(unmatched_linux)
            or pair_mismatch
            or not decision_equal
            or not error_type_equal
            or not weights_equal
            or not runtime_name_equal
            or not runtime_version_equal
            or not environment_identity_equal
            or not device_pair_expected
        )
        items.append(
            CrossPlatformItem(
                formal_sample_index=mac.formal_sample_index,
                image_sha256=mac.image_sha256,
                model_id=mac.model_id,
                config_sha256=mac.config_sha256,
                run_kind=mac.run_kind.value,
                mac_candidate_ids=mac_ids,
                linux_candidate_ids=linux_ids,
                candidate_count_equal=len(mac_ids) == len(linux_ids),
                candidate_ids_equal=mac_ids == linux_ids,
                candidate_pairs=pairs,
                unmatched_mac_candidate_ids=unmatched_mac,
                unmatched_linux_candidate_ids=unmatched_linux,
                decision_equal=decision_equal,
                error_type_equal=error_type_equal,
                mac_decision=mac.decision.value,
                linux_decision=linux.decision.value,
                mac_error_type=mac.error_type,
                linux_error_type=linux.error_type,
                mac_runtime_device=mac_provenance.runtime_device,
                linux_runtime_device=linux_provenance.runtime_device,
                runtime_device_pair_expected=device_pair_expected,
                weights_sha256_equal=weights_equal,
                runtime_name_equal=runtime_name_equal,
                runtime_version_equal=runtime_version_equal,
                runtime_environment_equal=environment_equal,
                runtime_environment_identity_equal=environment_identity_equal,
                mac_runtime_environment=mac_environment,
                linux_runtime_environment=linux_environment,
                is_mismatch=is_mismatch,
            )
        )
    mismatch_shas = tuple(item.image_sha256 for item in items if item.is_mismatch)
    deltas = (
        value
        for item in items
        for pair in item.candidate_pairs
        for value in (
            pair.ranking_score_absolute_delta,
            pair.ranking_score_relative_delta,
            pair.class_confidence_absolute_delta,
            pair.class_confidence_relative_delta,
            pair.grounding_box_score_absolute_delta,
            pair.grounding_box_score_relative_delta,
            pair.grounding_text_score_absolute_delta,
            pair.grounding_text_score_relative_delta,
            pair.sam_quality_absolute_delta,
            pair.sam_quality_relative_delta,
        )
        if value is not None
    )
    if any(not math.isfinite(value) for value in deltas):
        raise ValueError("comparison produced a nonfinite score delta")
    return CrossPlatformSummary(
        pair_count=len(items),
        mismatch_count=len(mismatch_shas),
        mismatch_image_shas=mismatch_shas,
        items=tuple(items),
    )


__all__ = (
    "CandidatePairComparison",
    "CrossPlatformItem",
    "CrossPlatformSummary",
    "compare_platforms",
)
