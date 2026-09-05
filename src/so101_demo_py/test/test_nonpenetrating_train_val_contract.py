from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
import so101_demo.training.grounding_dino_dataset as dino_dataset
import yaml
from so101_demo.adapters.perception.mujoco_dataset import (
    DatasetConfig,
    DatasetScenario,
    RawRender,
    SceneGeometry,
    generate_dataset,
    limited_split_counts,
    load_dataset_config,
    scenario_plan,
    split_seed_plan,
)
from so101_demo.adapters.perception.mujoco_scene_geometry import (
    TaskGeometryPair,
    TaskSceneGeometry,
)
from so101_demo.training.grounding_dino_dataset import (
    GroundingDinoDatasetError,
    convert_dataset,
)

CONTRACT = "so101-nonpenetrating-train-val-v1"
POLICY = "task-visual-nonpenetration-v1"
SCENARIOS = (
    "no_cup",
    "one_cup_distractors",
    "two_cups",
    "cup_near_bottle",
    "small_far_cup",
    "partially_occluded_cup",
)
SCENE_GEOMETRY = {
    "ordinary_camera_jitter_m": [-0.015, 0.015],
    "cup_a_xy_jitter_m": [-0.045, 0.045],
    "cup_b_xy_jitter_m": [-0.025, 0.025],
    "bottle_xy_jitter_m": [-0.025, 0.025],
    "far_camera_retreat_m": [2.4, 3.0],
    "partial_cup_xy_jitter_m": [-0.025, 0.025],
    "partial_bottle_longitudinal_m": [0.055, 0.105],
    "partial_bottle_perpendicular_m": [-0.025, 0.025],
    "small_bbox_area_max_exclusive": 1024.0,
    "visible_pixel_count_minimum": 64,
    "partial_visible_fraction": [0.35, 0.8],
    "maximum_deterministic_attempts": 64,
}


def _canonical_json(document: object) -> str:
    return json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n"


def _write(path: Path, payload: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_bytes(payload)


def _rle(mask: np.ndarray) -> list[int]:
    bits = np.asarray(mask, dtype=bool).reshape(-1)
    counts: list[int] = []
    expected = False
    length = 0
    for item in bits:
        value = bool(item)
        if value == expected:
            length += 1
        else:
            counts.append(length)
            expected = value
            length = 1
    counts.append(length)
    return counts


def _mask_fields(prefix: str, mask: np.ndarray) -> dict[str, object]:
    normalized = np.asarray(mask, dtype=np.uint8)
    return {
        f"{prefix}_pixel_count": int(normalized.sum()),
        f"{prefix}_mask_rle_counts": _rle(normalized),
        f"{prefix}_mask_sha256": hashlib.sha256(normalized.tobytes(order="C")).hexdigest(),
    }


def _polygon(mask: np.ndarray) -> list[list[float]]:
    rows, columns = np.nonzero(mask)
    left, right = int(columns.min()), int(columns.max())
    top, bottom = int(rows.min()), int(rows.max())
    width = mask.shape[1] - 1
    height = mask.shape[0] - 1
    return [
        [left / width, top / height],
        [right / width, top / height],
        [right / width, bottom / height],
        [left / width, bottom / height],
    ]


def _ordered_body_scope(scenario: str) -> list[tuple[str, str]]:
    cups = {
        "no_cup": [],
        "one_cup_distractors": ["plastic_cup"],
        "two_cups": ["plastic_cup", "plastic_cup_b"],
        "cup_near_bottle": ["plastic_cup"],
        "small_far_cup": ["plastic_cup"],
        "partially_occluded_cup": ["plastic_cup"],
    }[scenario]
    dynamic = [*cups, "orange_bottle"]
    result = [
        (dynamic[left], dynamic[right])
        for left in range(len(dynamic))
        for right in range(left + 1, len(dynamic))
    ]
    result.extend(
        (body, static) for body in dynamic for static in ("table", "neutral_block", "base_pedestal")
    )
    return result


def _visible_geom(body: str) -> str:
    return {
        "plastic_cup": "cup_a_bottom_visual",
        "plastic_cup_b": "cup_b_bottom_visual",
        "orange_bottle": "bottle_visual",
        "table": "table_visual",
        "neutral_block": "neutral_block_visual",
        "base_pedestal": "base_pedestal_visual",
    }[body]


def _receipt(scenario: str) -> dict[str, object]:
    return {
        "policy": POLICY,
        "accepted": True,
        "state_sha256": "d" * 64,
        "pairs": [
            {
                "body_names": list(body_names),
                "geom_names": [_visible_geom(body_names[0]), _visible_geom(body_names[1])],
                "signed_distance_m": 0.0,
                "primitive_pair_count": 1,
            }
            for body_names in _ordered_body_scope(scenario)
        ],
    }


def _truth(*, seed: int, split: str, scenario: str, partial: bool) -> dict[str, object]:
    visible = np.zeros((480, 640), dtype=np.uint8)
    if partial:
        visible[100:140, 200:240] = 1
    else:
        visible[100:108, 200:208] = 1
    instance: dict[str, object] = {
        "body_id": 4,
        "body_name": "plastic_cup",
        "mask_shape_hw": [480, 640],
        "polygon_xy": _polygon(visible),
        "occlusion_measured": partial,
        "occlusion_state": "partial" if partial else "unmeasured",
        **_mask_fields("visible", visible),
    }
    if partial:
        paired = np.zeros_like(visible)
        paired[90:140, 190:270] = 1
        amodal = visible | paired
        instance.update(
            {
                **_mask_fields("paired_reference", paired),
                **_mask_fields("amodal", amodal),
                "occluded_pixel_count": int(amodal.sum() - visible.sum()),
                "visible_fraction": float(visible.sum() / amodal.sum()),
                "occluder_body_name": "orange_bottle",
                "occlusion_reference": (
                    "visible_union_paired_segmentation_with_declared_occluder_hidden"
                ),
            }
        )
    return {
        "seed": seed,
        "split": split,
        "scenario": scenario,
        "configured_cup_count": 1,
        "visible_instance_count": 1,
        "instances": [instance],
        "scene_geometry": _receipt(scenario),
    }


def _new_source(root: Path) -> tuple[Path, dict[str, object]]:
    samples = [
        {
            "seed": 450000000,
            "split": "train",
            "scenario": "one_cup_distractors",
            "configured_cup_count": 1,
            "visible_instance_count": 1,
            "image": "images/train/450000000.png",
            "label": "labels/train/450000000.txt",
            "truth": "truth/train/450000000.json",
        },
        {
            "seed": 460000000,
            "split": "val",
            "scenario": "partially_occluded_cup",
            "configured_cup_count": 1,
            "visible_instance_count": 1,
            "image": "images/val/460000000.png",
            "label": "labels/val/460000000.txt",
            "truth": "truth/val/460000000.json",
        },
    ]
    for sample in samples:
        _write(root / sample["image"], f"synthetic-{sample['split']}-image".encode())
        truth = _truth(
            seed=sample["seed"],
            split=sample["split"],
            scenario=sample["scenario"],
            partial=sample["scenario"] == "partially_occluded_cup",
        )
        polygon = truth["instances"][0]["polygon_xy"]
        coordinates = " ".join(f"{value:.9f}" for point in polygon for value in point)
        _write(root / sample["label"], f"0 {coordinates}\n")
        _write(root / sample["truth"], _canonical_json(truth))
    _write(
        root / "dataset.yaml",
        "path: .\ntrain: images/train\nval: images/val\nnames:\n  0: plastic_cup\n",
    )
    artifacts = ["dataset.yaml"]
    artifacts.extend(sample[key] for sample in samples for key in ("image", "label", "truth"))
    manifest: dict[str, object] = {
        "schema_version": 2,
        "dataset_contract": CONTRACT,
        "member_splits": ["train", "val"],
        "generator_commit": "c" * 40,
        "mjcf_sha256": "e" * 64,
        "camera_name": "task_camera",
        "image_width": 640,
        "image_height": 480,
        "sample_count": 2,
        "split_counts": {"train": 1, "val": 1},
        "seed_starts": {"train": 450000000, "val": 460000000},
        "seed_ranges": {"train": [450000000, 450000000], "val": [460000000, 460000000]},
        "scenario_quotas": {
            "train": {"one_cup_distractors": 1},
            "val": {"partially_occluded_cup": 1},
        },
        "scene_geometry": copy.deepcopy(SCENE_GEOMETRY),
        "scene_geometry_policy": POLICY,
        "truth_contract": {
            "mask_order": "row_major",
            "mask_rle": "alternating_zero_one_counts_starting_with_zero",
            "mask_sha256": "sha256_uint8_row_major_bytes",
            "partial_occlusion_reference": (
                "visible_union_paired_segmentation_with_declared_occluder_hidden"
            ),
            "canonical_amodal": "visible_bitwise_union_paired_reference",
        },
        "class_instance_totals": {"plastic_cup": 2},
        "samples": samples,
        "artifacts": sorted(artifacts),
    }
    _write(root / "dataset-manifest.json", _canonical_json(manifest))
    return root, manifest


def _rewrite_manifest(root: Path, mutate: Callable[[dict[str, object]], None]) -> None:
    path = root / "dataset-manifest.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_text(_canonical_json(document), encoding="utf-8")


def _rewrite_truth(root: Path, split: str, seed: int, mutate: Callable[[dict], None]) -> None:
    path = root / f"truth/{split}/{seed:09d}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_text(_canonical_json(document), encoding="utf-8")


def _convert(root: Path, output: Path) -> dict[str, str]:
    return convert_dataset(
        root,
        output,
        source_archive_sha256="a" * 64,
        converter_commit="b" * 40,
    )


def _assert_conversion_error(root: Path, output: Path, code: str) -> None:
    with pytest.raises(GroundingDinoDatasetError) as caught:
        manifest, _ = dino_dataset._manifest(root)
        dino_dataset._dataset_contract(root, ("train", "val"))
        samples = [
            dino_dataset._validate_sample_shape(sample, index, ("train", "val"))
            for index, sample in enumerate(manifest["samples"])
        ]
        dino_dataset._validate_manifest_members(manifest, samples, ("train", "val"))
        for sample in samples:
            truth_path = root / sample["truth"]
            dino_dataset._truth_instances(
                truth_path.read_bytes(),
                member=sample["truth"],
                sample=sample,
                image_width=manifest["image_width"],
                image_height=manifest["image_height"],
                schema_version=manifest["schema_version"],
                scene_geometry=manifest["scene_geometry"],
                require_complete_visible_truth=True,
                require_geometry_receipt=True,
            )
    assert caught.value.code == code
    assert not output.exists()


class _FakeRenderer:
    def render(self, seed: int, scenario: DatasetScenario) -> RawRender:
        rgb = np.zeros((8, 10, 3), dtype=np.uint8)
        geoms = np.full((8, 10), -1, dtype=np.int32)
        body_names: dict[int, str] = {}
        if scenario.cup_count:
            geoms[0:8, 1:9] = 1
            body_names[4] = "plastic_cup"
        pairs = tuple(
            TaskGeometryPair(names, (_visible_geom(names[0]), _visible_geom(names[1])), 0.0, 1)
            for names in _ordered_body_scope(scenario.value)
        )
        return RawRender(
            rgb,
            geoms,
            np.asarray([0, 4], dtype=np.int32),
            body_names,
            geometry_receipt=TaskSceneGeometry("f" * 64, pairs),
        )

    def close(self) -> None:
        pass


def _legacy_source(root: Path) -> Path:
    fixture = root.parent / "legacy.xml"
    fixture.write_text("<mujoco/>", encoding="utf-8")
    config = DatasetConfig(
        mjcf_path=fixture,
        split_counts={"train": 1, "val": 1, "test": 1},
        seed_starts={"train": 100, "val": 200, "test": 300},
        scenario_quotas={split: {"no_cup": 1} for split in ("train", "val", "test")},
        generator_commit="c" * 40,
    )
    return root if generate_dataset(config, root, renderer=_FakeRenderer()) else root


def test_train_val_seed_plan_and_six_scenario_schedule_are_exact(tmp_path: Path) -> None:
    fixture = tmp_path / "model.xml"
    fixture.write_text("<mujoco/>", encoding="utf-8")
    quotas = {
        "train": {scenario: 200 for scenario in SCENARIOS},
        "val": {scenario: 50 for scenario in SCENARIOS},
    }
    config = DatasetConfig(
        mjcf_path=fixture,
        split_counts={"train": 1200, "val": 300},
        seed_starts={"train": 450000000, "val": 460000000},
        scenario_quotas=quotas,
        generator_commit="a" * 40,
        require_nonpenetrating_scene=True,
        dataset_contract=CONTRACT,
    )

    seeds = split_seed_plan(config.split_counts, config.seed_starts)
    schedules = scenario_plan(config)

    assert seeds["train"][0] == 450000000
    assert seeds["train"][-1] == 450001199
    assert seeds["val"][0] == 460000000
    assert seeds["val"][-1] == 460000299
    assert set(seeds) == {"train", "val"}
    assert tuple(item.value for item in schedules["train"][:12]) == SCENARIOS * 2
    assert tuple(item.value for item in schedules["val"][-6:]) == SCENARIOS
    assert {item.value: schedules["train"].count(item) for item in DatasetScenario} == quotas[
        "train"
    ]
    assert {item.value: schedules["val"].count(item) for item in DatasetScenario} == quotas["val"]


def test_official_train_val_config_loads_the_frozen_contract() -> None:
    path = (
        Path(__file__).parents[1]
        / "config/perception/plastic_cup_grounding_dino_nonpenetrating_train_val_v1.yaml"
    )

    config = load_dataset_config(path, generator_commit="a" * 40)

    assert config.dataset_contract == CONTRACT
    assert config.split_counts == {"train": 1200, "val": 300}
    assert config.seed_starts == {"train": 450000000, "val": 460000000}
    assert config.scenario_quotas == {
        "train": {scenario: 200 for scenario in SCENARIOS},
        "val": {scenario: 50 for scenario in SCENARIOS},
    }
    assert config.geometry == SceneGeometry.from_mapping(SCENE_GEOMETRY)
    assert config.require_nonpenetrating_scene is True


def test_sample_limit_cannot_modify_new_preregistered_quotas(tmp_path: Path) -> None:
    fixture = tmp_path / "model.xml"
    fixture.write_text("<mujoco/>", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "dataset_contract": CONTRACT,
                "mjcf_path": str(fixture),
                "camera_name": "task_camera",
                "image_width": 640,
                "image_height": 480,
                "split_counts": {"train": 6, "val": 6},
                "seed_starts": {"train": 450000000, "val": 460000000},
                "scenario_quotas": {
                    split: {scenario: 1 for scenario in SCENARIOS} for split in ("train", "val")
                },
                "scene_geometry": SCENE_GEOMETRY,
                "require_nonpenetrating_scene": True,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="sample_limit cannot alter preregistered scenario quotas"):
        load_dataset_config(config_path, generator_commit="a" * 40, sample_limit=2)


def test_public_generator_rejects_compact_fixture_as_official_version(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "model.xml"
    fixture.write_text("<mujoco/>", encoding="utf-8")
    with pytest.raises(ValueError):
        DatasetConfig(
            mjcf_path=fixture,
            split_counts={"train": 2, "val": 2},
            seed_starts={"train": 450000000, "val": 460000000},
            scenario_quotas={
                "train": {"no_cup": 1, "one_cup_distractors": 1},
                "val": {"no_cup": 1, "one_cup_distractors": 1},
            },
            generator_commit="a" * 40,
            require_nonpenetrating_scene=True,
            dataset_contract=CONTRACT,
        )
    assert not (tmp_path / "first").exists()


def test_synthetic_legacy_three_way_generator_and_converter_remain_byte_compatible(
    tmp_path: Path,
) -> None:
    source = _legacy_source(tmp_path / "legacy-source")
    manifest = json.loads((source / "dataset-manifest.json").read_text(encoding="utf-8"))

    assert "dataset_contract" not in manifest
    assert manifest["split_counts"] == {"test": 1, "train": 1, "val": 1}
    assert (source / "dataset.yaml").read_text(encoding="utf-8") == (
        "path: .\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n"
        "  0: plastic_cup\n"
    )
    hashes = _convert(source, tmp_path / "legacy-converted")
    assert set(hashes) == {
        "dataset-profile_sha256",
        "test-sealed-members_sha256",
        "train_inventory_sha256",
        "val_inventory_sha256",
    }
    assert (
        json.loads(
            (tmp_path / "legacy-converted/test-sealed-members.json").read_text(encoding="utf-8")
        )["sample_count"]
        == 1
    )


def test_compact_new_contract_exercises_lower_level_validators_only(tmp_path: Path) -> None:
    source, _ = _new_source(tmp_path / "source")
    manifest, _ = dino_dataset._manifest(source)
    samples = [
        dino_dataset._validate_sample_shape(sample, index, ("train", "val"))
        for index, sample in enumerate(manifest["samples"])
    ]
    dino_dataset._dataset_contract(source, ("train", "val"))
    dino_dataset._validate_manifest_members(manifest, samples, ("train", "val"))
    for sample in samples:
        result = dino_dataset._truth_instances(
            (source / sample["truth"]).read_bytes(),
            member=sample["truth"],
            sample=sample,
            image_width=manifest["image_width"],
            image_height=manifest["image_height"],
            schema_version=manifest["schema_version"],
            scene_geometry=manifest["scene_geometry"],
            require_complete_visible_truth=True,
            require_geometry_receipt=True,
        )
        assert len(result) == sample["visible_instance_count"]
    assert not (tmp_path / "converted").exists()


def _delete_key(key: str) -> Callable[[dict], None]:
    return lambda document: document.pop(key)


@pytest.mark.parametrize(
    ("name", "mutate", "code"),
    [
        ("missing-discriminator", _delete_key("dataset_contract"), "MANIFEST_INVALID"),
        (
            "changed-discriminator",
            lambda document: document.__setitem__("dataset_contract", "unknown"),
            "MANIFEST_INVALID",
        ),
        (
            "schema-downgrade",
            lambda document: document.__setitem__("schema_version", 1),
            "MANIFEST_INVALID",
        ),
        (
            "reordered-splits",
            lambda document: document.__setitem__("member_splits", ["val", "train"]),
            "MANIFEST_INVALID",
        ),
        (
            "duplicate-split",
            lambda document: document.__setitem__("member_splits", ["train", "train"]),
            "MANIFEST_INVALID",
        ),
        (
            "extra-split",
            lambda document: document.__setitem__("member_splits", ["train", "val", "test"]),
            "MANIFEST_INVALID",
        ),
        ("missing-policy", _delete_key("scene_geometry_policy"), "MANIFEST_INVALID"),
        (
            "changed-policy",
            lambda document: document.__setitem__("scene_geometry_policy", "legacy"),
            "MANIFEST_INVALID",
        ),
        (
            "zero-count",
            lambda document: document["split_counts"].__setitem__("train", 0),
            "MANIFEST_INVALID",
        ),
        (
            "bool-count",
            lambda document: document["split_counts"].__setitem__("train", True),
            "MANIFEST_INVALID",
        ),
        (
            "mismatched-count",
            lambda document: document["split_counts"].__setitem__("train", 2),
            "MANIFEST_INVALID",
        ),
        (
            "test-count-map",
            lambda document: document["split_counts"].__setitem__("test", 1),
            "MANIFEST_INVALID",
        ),
        (
            "test-seed-map",
            lambda document: document["seed_starts"].__setitem__("test", 470000000),
            "MANIFEST_INVALID",
        ),
        (
            "test-range-map",
            lambda document: document["seed_ranges"].__setitem__("test", [470000000, 470000000]),
            "MANIFEST_INVALID",
        ),
        (
            "test-quota-map",
            lambda document: document["scenario_quotas"].__setitem__("test", {"no_cup": 1}),
            "MANIFEST_INVALID",
        ),
        (
            "seed-overlap",
            lambda document: document["samples"][1].__setitem__("seed", 450000000),
            "SPLIT_SEEDS_OVERLAP",
        ),
        (
            "test-member",
            lambda document: document["samples"][0].__setitem__(
                "image", "images/test/450000000.png"
            ),
            "MANIFEST_INVALID",
        ),
    ],
)
def test_new_contract_manifest_mutations_fail_at_the_declared_boundary(
    tmp_path: Path, name: str, mutate: Callable[[dict], None], code: str
) -> None:
    source, _ = _new_source(tmp_path / name / "source")
    _rewrite_manifest(source, mutate)

    _assert_conversion_error(source, tmp_path / name / "converted", code)


def test_new_contract_rejects_injected_test_dataset_yaml(tmp_path: Path) -> None:
    source, _ = _new_source(tmp_path / "source")
    (source / "dataset.yaml").write_text(
        "path: .\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n"
        "  0: plastic_cup\n",
        encoding="utf-8",
    )

    _assert_conversion_error(source, tmp_path / "converted", "DATASET_YAML_INVALID")


@pytest.mark.parametrize("removal", ["all", "one"])
def test_new_contract_requires_complete_visible_rle_for_every_target(
    tmp_path: Path, removal: str
) -> None:
    source, _ = _new_source(tmp_path / removal / "source")

    def mutate(document: dict) -> None:
        instance = document["instances"][0]
        fields = ["mask_shape_hw", "visible_mask_rle_counts", "visible_mask_sha256"]
        if removal == "one":
            fields = fields[:1]
        for field in fields:
            instance.pop(field)

    _rewrite_truth(source, "train", 450000000, mutate)

    _assert_conversion_error(source, tmp_path / removal / "converted", "VISIBLE_TRUTH_INVALID")


@pytest.mark.parametrize(
    ("name", "mutate"),
    [
        (
            "missing-reference-rle",
            lambda instance: instance.pop("paired_reference_mask_rle_counts"),
        ),
        ("missing-amodal-hash", lambda instance: instance.pop("amodal_mask_sha256")),
        (
            "wrong-reference-hash",
            lambda instance: instance.__setitem__("paired_reference_mask_sha256", "0" * 64),
        ),
        (
            "wrong-amodal-count",
            lambda instance: instance.__setitem__(
                "amodal_pixel_count", instance["amodal_pixel_count"] + 1
            ),
        ),
        (
            "wrong-occluded-count",
            lambda instance: instance.__setitem__(
                "occluded_pixel_count", instance["occluded_pixel_count"] + 1
            ),
        ),
        (
            "wrong-fraction",
            lambda instance: instance.__setitem__("visible_fraction", 0.5),
        ),
        (
            "wrong-occluder",
            lambda instance: instance.__setitem__("occluder_body_name", "neutral_block"),
        ),
        (
            "wrong-reference-name",
            lambda instance: instance.__setitem__("occlusion_reference", "polygon"),
        ),
        (
            "non-union-amodal",
            lambda instance: instance["amodal_mask_rle_counts"].__setitem__(
                -1, instance["amodal_mask_rle_counts"][-1] - 1
            ),
        ),
    ],
)
def test_new_contract_partial_truth_mutations_are_rejected(
    tmp_path: Path, name: str, mutate: Callable[[dict], None]
) -> None:
    source, _ = _new_source(tmp_path / name / "source")

    def mutate_truth(document: dict) -> None:
        mutate(document["instances"][0])

    _rewrite_truth(source, "val", 460000000, mutate_truth)

    _assert_conversion_error(source, tmp_path / name / "converted", "OCCLUSION_TRUTH_INVALID")


def test_polygon_cannot_replace_new_contract_visible_mask_truth(tmp_path: Path) -> None:
    source, _ = _new_source(tmp_path / "source")

    def mutate(document: dict) -> None:
        instance = document["instances"][0]
        for field in ("mask_shape_hw", "visible_mask_rle_counts", "visible_mask_sha256"):
            instance.pop(field)
        assert len(instance["polygon_xy"]) == 4

    _rewrite_truth(source, "train", 450000000, mutate)

    _assert_conversion_error(source, tmp_path / "converted", "VISIBLE_TRUTH_INVALID")


@pytest.mark.parametrize(
    ("name", "mutate"),
    [
        ("missing-receipt-key", lambda receipt: receipt.pop("state_sha256")),
        ("extra-receipt-key", lambda receipt: receipt.__setitem__("extra", 1)),
        ("accepted-false", lambda receipt: receipt.__setitem__("accepted", False)),
        ("accepted-int", lambda receipt: receipt.__setitem__("accepted", 1)),
        ("bad-state-sha", lambda receipt: receipt.__setitem__("state_sha256", "g" * 64)),
        ("missing-pair", lambda receipt: receipt["pairs"].pop()),
        ("reordered-pair", lambda receipt: receipt["pairs"].reverse()),
        (
            "duplicate-pair",
            lambda receipt: receipt["pairs"].__setitem__(1, copy.deepcopy(receipt["pairs"][0])),
        ),
        (
            "foreign-body",
            lambda receipt: receipt["pairs"][0]["body_names"].__setitem__(0, "foreign"),
        ),
        (
            "collision-proxy-selected",
            lambda receipt: receipt["pairs"][0]["geom_names"].__setitem__(
                0, "cup_a_bottom_collision"
            ),
        ),
        ("missing-pair-key", lambda receipt: receipt["pairs"][0].pop("geom_names")),
        (
            "extra-pair-key",
            lambda receipt: receipt["pairs"][0].__setitem__("extra", 1),
        ),
        (
            "zero-primitive-count",
            lambda receipt: receipt["pairs"][0].__setitem__("primitive_pair_count", 0),
        ),
        (
            "bool-primitive-count",
            lambda receipt: receipt["pairs"][0].__setitem__("primitive_pair_count", True),
        ),
        (
            "nan-distance",
            lambda receipt: receipt["pairs"][0].__setitem__("signed_distance_m", math.nan),
        ),
        (
            "bool-distance",
            lambda receipt: receipt["pairs"][0].__setitem__("signed_distance_m", False),
        ),
        (
            "penetrating-distance",
            lambda receipt: receipt["pairs"][0].__setitem__("signed_distance_m", -2e-9),
        ),
    ],
)
def test_new_contract_geometry_receipt_mutations_are_rejected(
    tmp_path: Path, name: str, mutate: Callable[[dict], None]
) -> None:
    source, _ = _new_source(tmp_path / name / "source")

    def mutate_truth(document: dict) -> None:
        mutate(document["scene_geometry"])

    _rewrite_truth(source, "train", 450000000, mutate_truth)

    _assert_conversion_error(source, tmp_path / name / "converted", "GEOMETRY_RECEIPT_INVALID")


@pytest.mark.parametrize(
    "counts,starts",
    [
        ({"train": 1, "val": 1, "test": 0}, {"train": 1, "val": 2, "test": 3}),
        ({"train": True, "val": 1}, {"train": 1, "val": 2}),
        ({"train": 1, "val": 1}, {"train": 1, "val": 1}),
        ({"train": 1, "val": 1}, {"train": 1, "val": 2, "test": 3}),
    ],
)
def test_seed_plan_rejects_zero_bool_overlap_and_mismatched_split_maps(
    counts: dict[str, int], starts: dict[str, int]
) -> None:
    with pytest.raises(ValueError):
        split_seed_plan(counts, starts)


def test_legacy_sample_limit_control_is_unchanged() -> None:
    assert limited_split_counts({"train": 8, "val": 8, "test": 8}, 6) == {
        "train": 2,
        "val": 2,
        "test": 2,
    }


def test_contract_tests_load_no_rendering_modules() -> None:
    source_root = (Path(__file__).resolve().parents[1] / "src").resolve()
    program = """
import importlib
import sys
from pathlib import Path

forbidden_roots = {"mujoco", "OpenGL"}
module_suffixes = {
    "so101_demo.adapters.perception.mujoco_dataset": (
        "adapters/perception/mujoco_dataset.py"
    ),
    "so101_demo.adapters.perception.mujoco_scene_geometry": (
        "adapters/perception/mujoco_scene_geometry.py"
    ),
    "so101_demo.training.grounding_dino_dataset": (
        "training/grounding_dino_dataset.py"
    ),
}

def loaded_forbidden_roots():
    return {name.split(".", 1)[0] for name in sys.modules} & forbidden_roots

source_root = Path(sys.argv[1]).resolve()
before = loaded_forbidden_roots()
print(f"interpreter={sys.executable}")
print(f"source_root={source_root}")
print(f"forbidden_before={sorted(before)}")
assert not before, before
modules = {name: importlib.import_module(name) for name in module_suffixes}
actual_paths = {name: Path(module.__file__).resolve() for name, module in modules.items()}
expected_paths = {name: source_root / suffix for name, suffix in module_suffixes.items()}
for name in module_suffixes:
    print(f"module={name} actual={actual_paths[name]} expected={expected_paths[name]}")
assert actual_paths == expected_paths, (actual_paths, expected_paths)
after = loaded_forbidden_roots()
print(f"forbidden_after={sorted(after)}")
assert not after, after
"""
    completed = subprocess.run(
        [sys.executable, "-c", program, str(source_root)],
        check=False,
        capture_output=True,
        text=True,
    )
    print(completed.stdout, end="")
    print(completed.stderr, end="", file=sys.stderr)
    assert completed.returncode == 0, (
        f"child stdout:\n{completed.stdout}\nchild stderr:\n{completed.stderr}"
    )


def _official_config_document(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    fixture = tmp_path / "model.xml"
    fixture.write_text("<mujoco/>", encoding="utf-8")
    source = (
        Path(__file__).parents[1]
        / "config/perception/plastic_cup_grounding_dino_nonpenetrating_train_val_v1.yaml"
    )
    document = yaml.safe_load(source.read_text(encoding="utf-8"))
    document["mjcf_path"] = str(fixture)
    return fixture, document


def _official_config_kwargs(fixture: Path) -> dict[str, object]:
    return {
        "mjcf_path": fixture,
        "split_counts": {"train": 1200, "val": 300},
        "seed_starts": {"train": 450000000, "val": 460000000},
        "scenario_quotas": {
            "train": {scenario: 200 for scenario in SCENARIOS},
            "val": {scenario: 50 for scenario in SCENARIOS},
        },
        "generator_commit": "a" * 40,
        "require_nonpenetrating_scene": True,
        "dataset_contract": CONTRACT,
    }


class _RejectBeforeRenderSentinel:
    def __init__(self) -> None:
        self.calls = 0

    def render(self, seed: int, scenario: DatasetScenario) -> RawRender:
        self.calls += 1
        raise AssertionError("new contract must reject before the renderer is called")

    def close(self) -> None:
        pass


@pytest.mark.parametrize("gate", ["missing", "false"])
def test_new_contract_direct_config_requires_nonpenetration_gate(
    tmp_path: Path, gate: str
) -> None:
    fixture, _ = _official_config_document(tmp_path)
    kwargs = _official_config_kwargs(fixture)
    if gate == "missing":
        kwargs.pop("require_nonpenetrating_scene")
    else:
        kwargs["require_nonpenetrating_scene"] = False

    with pytest.raises(ValueError, match="nonpenetrating"):
        DatasetConfig(**kwargs)


@pytest.mark.parametrize("gate", ["missing", "false"])
def test_new_contract_loader_and_generator_reject_before_output_or_render(
    tmp_path: Path, gate: str
) -> None:
    _, document = _official_config_document(tmp_path)
    if gate == "missing":
        document.pop("require_nonpenetrating_scene")
    else:
        document["require_nonpenetrating_scene"] = False
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    output = tmp_path / "output"
    renderer = _RejectBeforeRenderSentinel()

    with pytest.raises(ValueError, match="nonpenetrating"):
        config = load_dataset_config(path, generator_commit="a" * 40)
        generate_dataset(config, output, renderer=renderer)

    assert renderer.calls == 0
    assert not output.exists()


def test_legacy_config_still_accepts_default_and_false_nonpenetration(tmp_path: Path) -> None:
    fixture = tmp_path / "legacy.xml"
    fixture.write_text("<mujoco/>", encoding="utf-8")
    kwargs = {
        "mjcf_path": fixture,
        "split_counts": {"train": 1, "val": 1, "test": 1},
        "generator_commit": "a" * 40,
    }

    assert DatasetConfig(**kwargs).require_nonpenetrating_scene is False
    assert DatasetConfig(**kwargs, require_nonpenetrating_scene=False).dataset_contract is None


@pytest.mark.parametrize("mutation", ["count", "seed-start", "quota-schedule"])
def test_public_generator_rejects_nonofficial_version_population(
    tmp_path: Path, mutation: str
) -> None:
    fixture, _ = _official_config_document(tmp_path)
    kwargs = _official_config_kwargs(fixture)
    if mutation == "count":
        kwargs["split_counts"] = {"train": 1199, "val": 300}
        quotas = copy.deepcopy(kwargs["scenario_quotas"])
        quotas["train"]["no_cup"] = 199
        kwargs["scenario_quotas"] = quotas
    elif mutation == "seed-start":
        kwargs["seed_starts"] = {"train": 450000001, "val": 460000000}
    else:
        quotas = copy.deepcopy(kwargs["scenario_quotas"])
        quotas["train"]["no_cup"] = 199
        quotas["train"]["one_cup_distractors"] = 201
        kwargs["scenario_quotas"] = quotas

    with pytest.raises(ValueError, match="official|contract|population"):
        DatasetConfig(**kwargs)


def test_public_converter_rejects_compact_fixture_as_official_version(tmp_path: Path) -> None:
    source, _ = _new_source(tmp_path / "source")
    output = tmp_path / "converted"

    _assert_public_conversion_error(source, output, "MANIFEST_INVALID")


def _official_version_manifest() -> dict[str, object]:
    samples = []
    for split, count, start, quota in (
        ("train", 1200, 450000000, 200),
        ("val", 300, 460000000, 50),
    ):
        for index in range(count):
            scenario = SCENARIOS[index % len(SCENARIOS)]
            seed = start + index
            samples.append(
                {
                    "seed": seed,
                    "split": split,
                    "scenario": scenario,
                    "configured_cup_count": {
                        "no_cup": 0,
                        "two_cups": 2,
                    }.get(scenario, 1),
                    "visible_instance_count": 0 if scenario == "no_cup" else 1,
                    "image": f"images/{split}/{seed:09d}.png",
                    "label": f"labels/{split}/{seed:09d}.txt",
                    "truth": f"truth/{split}/{seed:09d}.json",
                }
            )
    return {
        "schema_version": 2,
        "dataset_contract": CONTRACT,
        "member_splits": ["train", "val"],
        "split_counts": {"train": 1200, "val": 300},
        "seed_starts": {"train": 450000000, "val": 460000000},
        "seed_ranges": {
            "train": [450000000, 450001199],
            "val": [460000000, 460000299],
        },
        "scenario_quotas": {
            "train": {scenario: 200 for scenario in SCENARIOS},
            "val": {scenario: 50 for scenario in SCENARIOS},
        },
        "samples": samples,
    }


def _official_version_validator():
    validator = getattr(dino_dataset, "_validate_official_train_val_version", None)
    assert callable(validator), "missing official train/val version validator"
    return validator


@pytest.mark.parametrize("mutation", ["count", "seed-start", "seed-range", "quota", "schedule"])
def test_converter_official_version_validator_rejects_population_mutations(
    mutation: str,
) -> None:
    manifest = _official_version_manifest()
    if mutation == "count":
        manifest["split_counts"]["train"] = 1199
    elif mutation == "seed-start":
        manifest["seed_starts"]["train"] = 450000001
    elif mutation == "seed-range":
        manifest["seed_ranges"]["val"][1] = 460000298
    elif mutation == "quota":
        manifest["scenario_quotas"]["train"]["no_cup"] = 199
        manifest["scenario_quotas"]["train"]["one_cup_distractors"] = 201
    else:
        manifest["samples"][0]["scenario"], manifest["samples"][1]["scenario"] = (
            manifest["samples"][1]["scenario"],
            manifest["samples"][0]["scenario"],
        )

    with pytest.raises(GroundingDinoDatasetError, match="MANIFEST_INVALID"):
        _official_version_validator()(manifest)


def _assert_public_conversion_error(root: Path, output: Path, code: str) -> None:
    with pytest.raises(GroundingDinoDatasetError) as caught:
        _convert(root, output)
    assert caught.value.code == code
    assert not output.exists()


def _scenario_truth_case(scenario: str) -> tuple[dict[str, object], dict[str, object]]:
    if scenario == "no_cup":
        truth = {
            "seed": 450000000,
            "split": "train",
            "scenario": scenario,
            "configured_cup_count": 0,
            "visible_instance_count": 0,
            "instances": [],
            "scene_geometry": _receipt(scenario),
        }
    else:
        truth = _truth(
            seed=450000000,
            split="train",
            scenario=scenario,
            partial=scenario == "partially_occluded_cup",
        )
        if scenario == "two_cups":
            second = copy.deepcopy(truth["instances"][0])
            second["body_id"] = 5
            second["body_name"] = "plastic_cup_b"
            truth["instances"].append(second)
            truth["configured_cup_count"] = 2
            truth["visible_instance_count"] = 2
    sample = {
        "seed": truth["seed"],
        "split": truth["split"],
        "scenario": truth["scenario"],
        "configured_cup_count": truth["configured_cup_count"],
        "visible_instance_count": truth["visible_instance_count"],
    }
    return truth, sample


def _validate_scenario_truth(truth: dict[str, object], sample: dict[str, object]) -> None:
    dino_dataset._truth_instances(
        _canonical_json(truth).encode(),
        member="synthetic-truth.json",
        sample=sample,
        image_width=640,
        image_height=480,
        schema_version=2,
        scene_geometry=SCENE_GEOMETRY,
        require_complete_visible_truth=True,
        require_geometry_receipt=True,
    )


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_all_six_scenarios_accept_only_their_canonical_target_set(scenario: str) -> None:
    truth, sample = _scenario_truth_case(scenario)

    _validate_scenario_truth(truth, sample)


@pytest.mark.parametrize(
    "mutation",
    ["empty-partial", "no-cup-target", "inactive-body", "duplicate-body", "empty-small"],
)
def test_new_contract_rejects_scenario_target_count_and_body_mutations(
    mutation: str,
) -> None:
    scenario = {
        "empty-partial": "partially_occluded_cup",
        "no-cup-target": "no_cup",
        "inactive-body": "one_cup_distractors",
        "duplicate-body": "two_cups",
        "empty-small": "small_far_cup",
    }[mutation]
    truth, sample = _scenario_truth_case(scenario)
    if mutation in {"empty-partial", "empty-small"}:
        truth["instances"] = []
        truth["visible_instance_count"] = 0
        sample["visible_instance_count"] = 0
    elif mutation == "no-cup-target":
        target, _ = _scenario_truth_case("one_cup_distractors")
        truth["instances"] = target["instances"]
        truth["configured_cup_count"] = 1
        truth["visible_instance_count"] = 1
        sample["configured_cup_count"] = 1
        sample["visible_instance_count"] = 1
    elif mutation == "inactive-body":
        truth["instances"][0]["body_name"] = "plastic_cup_b"
    else:
        truth["instances"][1]["body_name"] = "plastic_cup"

    with pytest.raises(GroundingDinoDatasetError, match="TRUTH_MISMATCH"):
        _validate_scenario_truth(truth, sample)


def _tree_validator():
    validator = getattr(dino_dataset, "_validate_train_val_source_tree", None)
    assert callable(validator), "missing exact train/val source-tree validator"
    return validator


def _validate_compact_tree(root: Path, manifest: dict[str, object]) -> None:
    samples = [
        dino_dataset._validate_sample_shape(sample, index, ("train", "val"))
        for index, sample in enumerate(manifest["samples"])
    ]
    _tree_validator()(root, manifest, samples)


def test_exact_tree_validator_accepts_canonical_compact_fixture(tmp_path: Path) -> None:
    root, manifest = _new_source(tmp_path / "source")

    _validate_compact_tree(root, manifest)


def test_exact_tree_rejects_unexpected_directory_before_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, manifest = _new_source(tmp_path / "source")
    _validate_compact_tree(root, manifest)
    unexpected = root / "images" / "test"
    unexpected.mkdir()
    (unexpected / "private-member.png").write_bytes(b"must-not-be-enumerated")
    original_scandir = os.scandir

    def guarded_scandir(path: os.PathLike[str] | str):
        candidate = Path(path)
        if candidate == unexpected or unexpected in candidate.parents:
            raise AssertionError("UNEXPECTED_DIRECTORY_TRAVERSAL_SENTINEL")
        return original_scandir(path)

    # Catches recursion before the expected-directories membership check.
    monkeypatch.setattr(os, "scandir", guarded_scandir)
    with pytest.raises(GroundingDinoDatasetError, match="MANIFEST_INVALID|SOURCE_PATH_INVALID"):
        _validate_compact_tree(root, manifest)


@pytest.mark.parametrize("entry_type", ["regular", "directory", "symlink", "fifo"])
def test_exact_tree_validator_rejects_unlisted_entry_types(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entry_type: str
) -> None:
    root, manifest = _new_source(tmp_path / "source")
    unexpected = root / "unexpected-test-entry"
    if entry_type == "regular":
        unexpected.write_bytes(b"must-not-be-read")
        original_read_bytes = Path.read_bytes

        def guarded_read_bytes(path: Path) -> bytes:
            if path == unexpected:
                raise AssertionError("unexpected content must not be read")
            return original_read_bytes(path)

        monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    elif entry_type == "directory":
        unexpected.mkdir()
    elif entry_type == "symlink":
        unexpected.symlink_to("dataset.yaml")
    else:
        os.mkfifo(unexpected)

    with pytest.raises(GroundingDinoDatasetError, match="MANIFEST_INVALID|SOURCE_PATH_INVALID"):
        _validate_compact_tree(root, manifest)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("image", "images/train/450000000.jpg"),
        ("label", "labels/train/45000000.txt"),
        ("truth", "truth/train/not-a-seed.json"),
    ],
)
def test_exact_tree_validator_rejects_noncanonical_listed_member_name(
    tmp_path: Path, field: str, replacement: str
) -> None:
    root, manifest = _new_source(tmp_path / "source")
    sample = manifest["samples"][0]
    original = sample[field]
    target = root / replacement
    target.parent.mkdir(parents=True, exist_ok=True)
    (root / original).rename(target)
    sample[field] = replacement
    manifest["artifacts"] = sorted(
        replacement if item == original else item for item in manifest["artifacts"]
    )

    with pytest.raises(GroundingDinoDatasetError, match="MANIFEST_INVALID|SOURCE_PATH_INVALID"):
        _validate_compact_tree(root, manifest)


def _legacy_measured_none_source(root: Path) -> Path:
    fixture = root.parent / "legacy-measured-none.xml"
    fixture.write_text("<mujoco/>", encoding="utf-8")
    config = DatasetConfig(
        mjcf_path=fixture,
        image_width=10,
        image_height=8,
        split_counts={"train": 1, "val": 1, "test": 1},
        seed_starts={"train": 100, "val": 200, "test": 300},
        scenario_quotas={
            split: {"one_cup_distractors": 1} for split in ("train", "val", "test")
        },
        generator_commit="c" * 40,
    )
    generate_dataset(config, root, renderer=_FakeRenderer())
    truth_path = root / "truth/train/000000100.json"
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    instance = truth["instances"][0]
    instance.update(
        {
            "occlusion_measured": True,
            "occlusion_state": "none",
            "paired_reference_mask_rle_counts": instance["visible_mask_rle_counts"],
            "paired_reference_mask_sha256": instance["visible_mask_sha256"],
            "paired_reference_pixel_count": instance["visible_pixel_count"],
            "amodal_mask_rle_counts": instance["visible_mask_rle_counts"],
            "amodal_mask_sha256": instance["visible_mask_sha256"],
            "amodal_pixel_count": instance["visible_pixel_count"],
            "occluded_pixel_count": 0,
            "visible_fraction": 1.0,
            "occluder_body_name": "orange_bottle",
            "occlusion_reference": (
                "visible_union_paired_segmentation_with_declared_occluder_hidden"
            ),
        }
    )
    truth_path.write_text(_canonical_json(truth), encoding="utf-8")
    return root


def test_legacy_schema2_measured_none_remains_accepted_and_deterministic(tmp_path: Path) -> None:
    source = _legacy_measured_none_source(tmp_path / "source")
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_hashes = _convert(source, first)
    second_hashes = _convert(source, second)

    assert first_hashes == second_hashes
    assert {
        path.relative_to(first).as_posix(): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    } == {
        path.relative_to(second).as_posix(): path.read_bytes()
        for path in second.rglob("*")
        if path.is_file()
    }
    inventory = json.loads((first / "train/inventory.json").read_text(encoding="utf-8"))
    assert inventory["samples"][0]["boxes"][0]["occlusion"] == {
        "amodal_pixel_count": 64,
        "occluded_pixel_count": 0,
        "occluder_body_name": "orange_bottle",
        "state": "none",
        "visible_fraction": 1.0,
    }


@pytest.mark.parametrize("schema", [2.0, []])
def test_new_config_loader_rejects_non_plain_integer_schema(
    tmp_path: Path, schema: object
) -> None:
    _, document = _official_config_document(tmp_path)
    document["schema_version"] = schema
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="schema"):
        load_dataset_config(path, generator_commit="a" * 40)


@pytest.mark.parametrize("schema", [2.0, []])
def test_new_converter_normalizes_non_plain_integer_schema(
    tmp_path: Path, schema: object
) -> None:
    root, _ = _new_source(tmp_path / "source")
    _rewrite_manifest(root, lambda document: document.__setitem__("schema_version", schema))

    with pytest.raises(GroundingDinoDatasetError) as caught:
        dino_dataset._manifest(root)
    assert caught.value.code == "MANIFEST_INVALID"


def test_new_converter_normalizes_huge_integer_geometry_distance(tmp_path: Path) -> None:
    root, _ = _new_source(tmp_path / "source")

    def mutate(document: dict) -> None:
        document["scene_geometry"]["pairs"][0]["signed_distance_m"] = 10**400

    _rewrite_truth(root, "train", 450000000, mutate)

    _assert_conversion_error(root, tmp_path / "converted", "GEOMETRY_RECEIPT_INVALID")
