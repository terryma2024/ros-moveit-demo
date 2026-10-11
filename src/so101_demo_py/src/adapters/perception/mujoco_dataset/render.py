"""Mask and polygon encoding, labelled samples, acceptance checks and bounded render selection."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import asdict
import hashlib
import os
from pathlib import Path
from typing import Any, Mapping, Protocol

import numpy as np

from so101_demo.adapters.perception.mujoco_dataset.models import (
    DatasetScenario,
    LabeledInstance,
    LabeledSample,
    RawRender,
    RenderEventSink,
    SceneGeometry,
    _emit_render_event,
)
from so101_demo.adapters.perception.mujoco_scene_geometry import (
    ScenePenetrationError,
    TaskSceneGeometry,
)


def _convex_hull(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    unique = sorted(set(points))
    if len(unique) <= 1:
        return unique

    def cross(
        origin: tuple[int, int],
        first: tuple[int, int],
        second: tuple[int, int],
    ) -> int:
        return (first[0] - origin[0]) * (second[1] - origin[1]) - (first[1] - origin[1]) * (
            second[0] - origin[0]
        )

    lower: list[tuple[int, int]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[int, int]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def _polygon_from_mask(mask: np.ndarray) -> tuple[tuple[float, float], ...]:
    height, width = mask.shape
    rows, columns = np.nonzero(mask)
    hull = _convex_hull(list(zip(columns.tolist(), rows.tolist(), strict=True)))
    if len(hull) < 3:
        left, right = int(columns.min()), int(columns.max())
        top, bottom = int(rows.min()), int(rows.max())
        hull = [(left, top), (right, top), (right, bottom), (left, bottom)]
    x_scale = max(1, width - 1)
    y_scale = max(1, height - 1)
    return tuple(
        (
            min(1.0, max(0.0, x / x_scale)),
            min(1.0, max(0.0, y / y_scale)),
        )
        for x, y in hull
    )


def encode_binary_mask_rle(mask: np.ndarray) -> tuple[int, ...]:
    """Encode a row-major binary mask as alternating zero/one run lengths."""

    normalized = np.asarray(mask, dtype=bool)
    if normalized.ndim != 2:
        raise ValueError("binary mask must be two-dimensional")
    flat = normalized.reshape(-1)
    counts: list[int] = []
    expected = False
    run = 0
    for value in flat:
        bit = bool(value)
        if bit == expected:
            run += 1
        else:
            counts.append(run)
            expected = bit
            run = 1
    counts.append(run)
    return tuple(counts)


def decode_binary_mask_rle(counts: Any, shape_hw: Any) -> np.ndarray:
    """Decode the canonical row-major alternating binary-mask RLE."""

    if (
        not isinstance(shape_hw, (tuple, list))
        or len(shape_hw) != 2
        or any(type(value) is not int or value <= 0 for value in shape_hw)
    ):
        raise ValueError("mask shape must contain two positive integers")
    if (
        not isinstance(counts, (tuple, list))
        or not counts
        or any(type(value) is not int or value < 0 for value in counts)
    ):
        raise ValueError("mask RLE counts must be nonnegative integers")
    total = int(shape_hw[0]) * int(shape_hw[1])
    if sum(counts) != total:
        raise ValueError("mask RLE counts do not match the declared shape")
    flat = np.empty(total, dtype=bool)
    offset = 0
    value = False
    for count in counts:
        flat[offset : offset + count] = value
        offset += count
        value = not value
    return flat.reshape((int(shape_hw[0]), int(shape_hw[1])))


def _mask_sha256(mask: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(mask, dtype=np.uint8).tobytes(order="C")).hexdigest()


def build_labeled_sample(
    render: RawRender,
    *,
    seed: int,
    scenario: DatasetScenario,
) -> LabeledSample:
    active_cup_bodies = {
        DatasetScenario.NO_CUP: frozenset(),
        DatasetScenario.ONE_CUP_DISTRACTORS: frozenset({"plastic_cup"}),
        DatasetScenario.TWO_CUPS: frozenset({"plastic_cup", "plastic_cup_b"}),
        DatasetScenario.CUP_NEAR_BOTTLE: frozenset({"plastic_cup"}),
        DatasetScenario.SMALL_FAR_CUP: frozenset({"plastic_cup"}),
        DatasetScenario.PARTIALLY_OCCLUDED_CUP: frozenset({"plastic_cup"}),
    }[scenario]
    visible_geom_ids = np.unique(render.geom_ids[render.geom_ids >= 0])
    if any(geom_id >= len(render.geom_body_ids) for geom_id in visible_geom_ids):
        raise ValueError("segmentation contains an out-of-range geom ID")
    instances: list[LabeledInstance] = []
    for body_id, body_name in sorted(render.body_names.items()):
        if body_name not in active_cup_bodies:
            continue
        target_geoms = np.flatnonzero(render.geom_body_ids == body_id)
        mask = np.isin(render.geom_ids, target_geoms)
        if not mask.any():
            continue
        paired_reference_mask = (
            None
            if render.amodal_geom_ids is None
            else np.isin(render.amodal_geom_ids, target_geoms)
        )
        amodal_mask = None if paired_reference_mask is None else mask | paired_reference_mask
        instances.append(
            LabeledInstance(
                body_id=body_id,
                body_name=body_name,
                mask=mask,
                polygon_xy=_polygon_from_mask(mask),
                amodal_mask=amodal_mask,
                paired_reference_mask=paired_reference_mask,
                occluder_body_name=render.occluder_body_name,
                occlusion_reference=render.occlusion_reference,
            )
        )
    return LabeledSample(seed, scenario, render.rgb8, tuple(instances))


def _bbox_area_px2(instance: LabeledInstance) -> float:
    height, width = instance.mask.shape
    x_values = [point[0] for point in instance.polygon_xy]
    y_values = [point[1] for point in instance.polygon_xy]
    return (max(x_values) - min(x_values)) * width * (max(y_values) - min(y_values)) * height


def _sample_meets_acceptance(sample: LabeledSample, geometry: SceneGeometry) -> bool:
    if sample.scenario == DatasetScenario.SMALL_FAR_CUP:
        if len(sample.instances) != 1:
            return False
        instance = sample.instances[0]
        return (
            instance.visible_pixel_count >= geometry.visible_pixel_count_minimum
            and 0.0 < _bbox_area_px2(instance) < geometry.small_bbox_area_max_exclusive
        )
    if sample.scenario == DatasetScenario.PARTIALLY_OCCLUDED_CUP:
        if len(sample.instances) != 1:
            return False
        instance = sample.instances[0]
        fraction = instance.visible_fraction
        return (
            instance.occlusion_measured
            and instance.occlusion_state == "partial"
            and instance.visible_pixel_count >= geometry.visible_pixel_count_minimum
            and instance.occluded_pixel_count is not None
            and instance.occluded_pixel_count >= 1
            and fraction is not None
            and geometry.partial_visible_fraction[0]
            <= fraction
            <= geometry.partial_visible_fraction[1]
        )
    return True


def _validate_observed_penetration_error(
    error: ScenePenetrationError,
    *,
    seed: int,
    scenario: DatasetScenario,
    attempt_index: int,
) -> TaskSceneGeometry:
    receipt = getattr(error, "receipt", None)
    if not isinstance(receipt, TaskSceneGeometry):
        raise ValueError("observed penetration receipt is missing or invalid")
    if (
        getattr(error, "seed", None) != seed
        or getattr(error, "scenario", None) != scenario
        or getattr(error, "attempt_index", None) != attempt_index
    ):
        raise ValueError("observed penetration context does not match the active attempt")
    receipt.validate_scope(scenario.cup_count)
    if receipt.accepted:
        raise ValueError("observed penetration receipt must reject the scene")
    return receipt


def select_bounded_render(
    seed: int,
    scenario: DatasetScenario,
    render_attempt: Callable[[np.random.Generator], RawRender],
    geometry: SceneGeometry,
    *,
    require_nonpenetrating_scene: bool = False,
    event_sink: RenderEventSink | None = None,
) -> RawRender:
    """Select the first deterministic render satisfying an augmented scenario gate."""

    bounded = scenario in {
        DatasetScenario.SMALL_FAR_CUP,
        DatasetScenario.PARTIALLY_OCCLUDED_CUP,
    }
    attempts = (
        geometry.maximum_deterministic_attempts if bounded or require_nonpenetrating_scene else 1
    )
    scenario_ordinal = tuple(DatasetScenario).index(scenario)
    for attempt_index in range(attempts):
        random = np.random.default_rng(
            np.random.SeedSequence([seed, scenario_ordinal, attempt_index])
        )
        try:
            render = render_attempt(random)
        except ScenePenetrationError as error:
            if require_nonpenetrating_scene:
                if event_sink is not None:
                    _validate_observed_penetration_error(
                        error,
                        seed=seed,
                        scenario=scenario,
                        attempt_index=attempt_index,
                    )
                continue
            raise
        if require_nonpenetrating_scene:
            if not isinstance(render.geometry_receipt, TaskSceneGeometry):
                raise ValueError("required geometry receipt is missing or invalid")
            render.geometry_receipt.validate_scope(scenario.cup_count)
            if not render.geometry_receipt.accepted:
                continue
        sample = build_labeled_sample(render, seed=seed, scenario=scenario)
        if _sample_meets_acceptance(sample, geometry):
            _emit_render_event(
                event_sink,
                "accepted",
                seed,
                scenario,
                attempt_index,
                render.geometry_receipt,
            )
            return render
        _emit_render_event(
            event_sink,
            "scenario_rejected",
            seed,
            scenario,
            attempt_index,
            render.geometry_receipt,
        )
    raise RuntimeError(f"{scenario.value} failed {attempts} deterministic attempts for seed {seed}")


class DatasetRenderer(Protocol):
    def render(self, seed: int, scenario: DatasetScenario) -> RawRender: ...

    def close(self) -> None: ...


def _exclusive_text(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(contents)
        stream.flush()
        os.fsync(stream.fileno())


def _label_text(sample: LabeledSample) -> str:
    rows = []
    for instance in sample.instances:
        coordinates = " ".join(
            f"{coordinate:.9f}" for point in instance.polygon_xy for coordinate in point
        )
        rows.append(f"0 {coordinates}")
    return "" if not rows else "\n".join(rows) + "\n"


def _truth_instance_document(instance: LabeledInstance) -> dict[str, Any]:
    document: dict[str, Any] = {
        "body_id": instance.body_id,
        "body_name": instance.body_name,
        "mask_shape_hw": list(instance.mask.shape),
        "visible_pixel_count": instance.visible_pixel_count,
        "visible_mask_rle_counts": list(encode_binary_mask_rle(instance.mask)),
        "visible_mask_sha256": _mask_sha256(instance.mask),
        "polygon_xy": [list(point) for point in instance.polygon_xy],
        "occlusion_measured": instance.occlusion_measured,
        "occlusion_state": instance.occlusion_state,
    }
    if not instance.occlusion_measured:
        return document
    assert instance.amodal_mask is not None
    assert instance.paired_reference_mask is not None
    assert instance.amodal_pixel_count is not None
    assert instance.paired_reference_pixel_count is not None
    assert instance.occluded_pixel_count is not None
    assert instance.visible_fraction is not None
    document.update(
        {
            "paired_reference_pixel_count": instance.paired_reference_pixel_count,
            "paired_reference_mask_rle_counts": list(
                encode_binary_mask_rle(instance.paired_reference_mask)
            ),
            "paired_reference_mask_sha256": _mask_sha256(instance.paired_reference_mask),
            "amodal_pixel_count": instance.amodal_pixel_count,
            "amodal_mask_rle_counts": list(encode_binary_mask_rle(instance.amodal_mask)),
            "amodal_mask_sha256": _mask_sha256(instance.amodal_mask),
            "occluded_pixel_count": instance.occluded_pixel_count,
            "visible_fraction": instance.visible_fraction,
            "occluder_body_name": instance.occluder_body_name,
            "occlusion_reference": instance.occlusion_reference,
        }
    )
    return document


def _resolved_scenario_quotas(
    schedules: Mapping[str, tuple[DatasetScenario, ...]],
) -> dict[str, dict[str, int]]:
    return {
        split: dict(
            sorted(
                Counter(scenario.value for scenario in schedule).items(),
                key=lambda item: tuple(DatasetScenario).index(DatasetScenario(item[0])),
            )
        )
        for split, schedule in schedules.items()
    }


def _scene_geometry_document(geometry: SceneGeometry) -> dict[str, Any]:
    return {
        name: list(value) if isinstance(value, tuple) else value
        for name, value in asdict(geometry).items()
    }
