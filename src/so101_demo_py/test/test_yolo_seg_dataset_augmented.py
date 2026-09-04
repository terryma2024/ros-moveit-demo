from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from so101_demo.adapters.perception.mujoco_dataset import (
    DatasetConfig,
    DatasetScenario,
    RawRender,
    SceneGeometry,
    build_labeled_sample,
    decode_binary_mask_rle,
    encode_binary_mask_rle,
    generate_dataset,
    load_dataset_config,
    scenario_plan,
    select_bounded_render,
)

SCENARIO_ORDER = (
    DatasetScenario.NO_CUP,
    DatasetScenario.ONE_CUP_DISTRACTORS,
    DatasetScenario.TWO_CUPS,
    DatasetScenario.CUP_NEAR_BOTTLE,
    DatasetScenario.SMALL_FAR_CUP,
    DatasetScenario.PARTIALLY_OCCLUDED_CUP,
)


def _render(
    *,
    visible_slice: tuple[slice, slice],
    amodal_slice: tuple[slice, slice] | None = None,
) -> RawRender:
    rgb = np.zeros((480, 640, 3), dtype=np.uint8)
    visible = np.full((480, 640), -1, dtype=np.int32)
    visible[visible_slice] = 3
    amodal = None
    if amodal_slice is not None:
        amodal = np.full((480, 640), -1, dtype=np.int32)
        amodal[amodal_slice] = 3
    return RawRender(
        rgb8=rgb,
        geom_ids=visible,
        geom_body_ids=np.asarray([0, 0, 0, 4]),
        body_names={4: "plastic_cup", 9: "orange_bottle"},
        amodal_geom_ids=amodal,
        occluder_body_name="orange_bottle" if amodal is not None else None,
        occlusion_reference=(
            "visible_union_paired_segmentation_with_declared_occluder_hidden"
            if amodal is not None
            else None
        ),
    )


def _quotas(count: int = 1) -> dict[str, dict[str, int]]:
    return {
        split: {scenario.value: count for scenario in SCENARIO_ORDER}
        for split in ("train", "val", "test")
    }


def test_scenario_plan_is_quota_derived_round_robin_and_exact(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.xml"
    fixture.write_text("<mujoco/>", encoding="utf-8")
    config = DatasetConfig(
        mjcf_path=fixture,
        split_counts={"train": 12, "val": 12, "test": 12},
        generator_commit="a" * 40,
        scenario_quotas=_quotas(2),
    )

    plan = scenario_plan(config)

    assert plan["train"] == SCENARIO_ORDER + SCENARIO_ORDER
    assert {scenario: plan["val"].count(scenario) for scenario in SCENARIO_ORDER} == {
        scenario: 2 for scenario in SCENARIO_ORDER
    }


def test_scenario_quota_mismatch_is_rejected_before_generation(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.xml"
    fixture.write_text("<mujoco/>", encoding="utf-8")
    quotas = _quotas()
    quotas["train"].pop(DatasetScenario.SMALL_FAR_CUP.value)

    with pytest.raises(ValueError, match="scenario quotas"):
        DatasetConfig(
            mjcf_path=fixture,
            split_counts={"train": 6, "val": 6, "test": 6},
            generator_commit="a" * 40,
            scenario_quotas=quotas,
        )


def test_augmented_config_is_the_preregistered_contract() -> None:
    config_path = (
        Path(__file__).parents[1] / "config/perception/plastic_cup_grounding_dino_augmented_r3.yaml"
    )

    config = load_dataset_config(config_path, generator_commit="b" * 40)

    assert config.split_counts == {"train": 1200, "val": 300, "test": 300}
    assert config.seed_starts == {
        "train": 410000000,
        "val": 420000000,
        "test": 440000000,
    }
    assert config.scenario_quotas["train"] == {scenario.value: 200 for scenario in SCENARIO_ORDER}
    assert config.geometry.far_camera_retreat_m == (2.4, 3.0)
    assert config.geometry.partial_visible_fraction == (0.35, 0.8)


def test_binary_mask_rle_round_trip_is_canonical() -> None:
    mask = np.zeros((5, 7), dtype=bool)
    mask[1:4, 2:6] = True
    mask[2, 3] = False

    counts = encode_binary_mask_rle(mask)

    assert counts[0] > 0
    assert np.array_equal(decode_binary_mask_rle(counts, mask.shape), mask)
    assert encode_binary_mask_rle(decode_binary_mask_rle(counts, mask.shape)) == counts


def test_partial_occlusion_truth_uses_visible_subset_of_paired_amodal_mask() -> None:
    render = _render(
        visible_slice=(slice(100, 108), slice(200, 208)),
        amodal_slice=(slice(96, 112), slice(200, 210)),
    )

    sample = build_labeled_sample(
        render,
        seed=410000005,
        scenario=DatasetScenario.PARTIALLY_OCCLUDED_CUP,
    )

    instance = sample.instances[0]
    assert instance.occlusion_measured is True
    assert instance.occlusion_state == "partial"
    assert instance.visible_pixel_count == 64
    assert instance.amodal_pixel_count == 160
    assert instance.occluded_pixel_count == 96
    assert instance.visible_fraction == pytest.approx(0.4)
    assert instance.occluder_body_name == "orange_bottle"


def test_partial_occlusion_canonical_amodal_unions_visible_and_paired_reference() -> None:
    render = _render(
        visible_slice=(slice(100, 108), slice(200, 208)),
        amodal_slice=(slice(104, 112), slice(204, 212)),
    )

    sample = build_labeled_sample(
        render,
        seed=410000005,
        scenario=DatasetScenario.PARTIALLY_OCCLUDED_CUP,
    )

    instance = sample.instances[0]
    assert instance.paired_reference_pixel_count == 64
    assert instance.amodal_pixel_count == 112
    assert instance.occluded_pixel_count == 48
    assert np.array_equal(
        instance.amodal_mask,
        instance.mask | instance.paired_reference_mask,
    )


def test_bounded_acceptance_enforces_small_and_partial_contracts() -> None:
    geometry = SceneGeometry()
    small = _render(visible_slice=(slice(100, 108), slice(200, 208)))
    medium = _render(visible_slice=(slice(100, 140), slice(200, 240)))
    partial = _render(
        visible_slice=(slice(100, 108), slice(200, 208)),
        amodal_slice=(slice(96, 112), slice(200, 210)),
    )

    assert (
        select_bounded_render(
            410000000,
            DatasetScenario.SMALL_FAR_CUP,
            lambda _: small,
            geometry,
        )
        is small
    )
    with pytest.raises(RuntimeError, match="64 deterministic attempts"):
        select_bounded_render(
            410000000,
            DatasetScenario.SMALL_FAR_CUP,
            lambda _: medium,
            geometry,
        )
    assert (
        select_bounded_render(
            410000000,
            DatasetScenario.PARTIALLY_OCCLUDED_CUP,
            lambda _: partial,
            geometry,
        )
        is partial
    )


def test_bounded_attempt_seed_stream_is_deterministic_and_scenario_namespaced() -> None:
    failing = _render(visible_slice=(slice(100, 140), slice(200, 240)))
    first: list[int] = []
    second: list[int] = []
    other: list[int] = []

    def record(target: list[int]):
        def render_attempt(random: np.random.Generator) -> RawRender:
            target.append(int(random.integers(0, 2**31)))
            return failing

        return render_attempt

    for scenario, target in (
        (DatasetScenario.SMALL_FAR_CUP, first),
        (DatasetScenario.SMALL_FAR_CUP, second),
        (DatasetScenario.PARTIALLY_OCCLUDED_CUP, other),
    ):
        with pytest.raises(RuntimeError, match="64 deterministic attempts"):
            select_bounded_render(410000007, scenario, record(target), SceneGeometry())

    assert first == second
    assert first != other
    assert len(first) == 64


class _MeasuredRenderer:
    def render(self, seed: int, scenario: DatasetScenario) -> RawRender:
        if scenario == DatasetScenario.PARTIALLY_OCCLUDED_CUP:
            return _render(
                visible_slice=(slice(100, 108), slice(200, 208)),
                amodal_slice=(slice(96, 112), slice(200, 210)),
            )
        return _render(visible_slice=(slice(100, 108), slice(200, 208)))

    def close(self) -> None:
        pass


def test_schema_v2_manifest_and_truth_persist_measured_occlusion(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.xml"
    fixture.write_text("<mujoco/>", encoding="utf-8")
    config = DatasetConfig(
        mjcf_path=fixture,
        split_counts={"train": 1, "val": 1, "test": 1},
        generator_commit="c" * 40,
        seed_starts={"train": 410000000, "val": 420000000, "test": 440000000},
        scenario_quotas={
            split: {DatasetScenario.PARTIALLY_OCCLUDED_CUP.value: 1}
            for split in ("train", "val", "test")
        },
    )

    manifest = generate_dataset(config, tmp_path / "dataset", renderer=_MeasuredRenderer())

    truth = json.loads(
        (tmp_path / "dataset/truth/train/410000000.json").read_text(encoding="utf-8")
    )
    instance = truth["instances"][0]
    assert manifest["schema_version"] == 2
    assert manifest["scenario_quotas"]["train"] == {"partially_occluded_cup": 1}
    assert instance["mask_shape_hw"] == [480, 640]
    assert instance["occlusion_measured"] is True
    assert instance["occlusion_state"] == "partial"
    assert instance["visible_fraction"] == 0.4
    assert len(instance["visible_mask_sha256"]) == 64
    assert instance["paired_reference_pixel_count"] == 160
    assert len(instance["paired_reference_mask_sha256"]) == 64
    assert len(instance["amodal_mask_sha256"]) == 64
    assert (
        decode_binary_mask_rle(instance["visible_mask_rle_counts"], instance["mask_shape_hw"]).sum()
        == 64
    )
