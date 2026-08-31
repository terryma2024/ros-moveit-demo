from __future__ import annotations

import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from so101_demo.adapters.perception.mujoco_dataset import (
    DatasetConfig,
    DatasetScenario,
    RawRender,
    build_labeled_sample,
    generate_dataset,
    limited_split_counts,
    load_dataset_config,
    split_seed_plan,
)


def _raw_render(*, cup_count: int, cup_rgba: tuple[float, ...]) -> RawRender:
    rgb = np.zeros((8, 10, 3), dtype=np.uint8)
    rgb[:, :] = np.rint(np.asarray(cup_rgba[:3]) * 255).astype(np.uint8)
    geom_ids = np.full((8, 10), -1, dtype=np.int32)
    if cup_count >= 1:
        geom_ids[1:5, 1:4] = 3
    if cup_count == 2:
        geom_ids[2:7, 6:9] = 8
    geom_ids[0:3, 8:10] = 12
    return RawRender(
        rgb8=rgb,
        geom_ids=geom_ids,
        geom_body_ids=np.asarray([0, 0, 0, 4, 0, 0, 0, 0, 7, 0, 0, 0, 9]),
        body_names={4: "plastic_cup", 7: "plastic_cup_b", 9: "orange_bottle"},
    )


def test_split_seed_ranges_are_fixed_and_disjoint() -> None:
    plan = split_seed_plan({"train": 800, "val": 200, "test": 200})

    assert plan["train"] == tuple(range(100000, 100800))
    assert plan["val"] == tuple(range(200000, 200200))
    assert plan["test"] == tuple(range(300000, 300200))
    assert not (set(plan["train"]) & set(plan["val"]))
    assert not (set(plan["train"]) & set(plan["test"]))
    assert not (set(plan["val"]) & set(plan["test"]))


def test_twelve_sample_limit_keeps_all_splits_and_scenarios() -> None:
    assert limited_split_counts(
        {"train": 800, "val": 200, "test": 200}, 12
    ) == {"train": 4, "val": 4, "test": 4}


def test_config_resolves_mjcf_relative_to_config_file(tmp_path: Path) -> None:
    fixture = tmp_path / "assets/fixture.xml"
    fixture.parent.mkdir()
    fixture.write_text("<mujoco/>", encoding="utf-8")
    config_path = tmp_path / "config/dataset.yaml"
    config_path.parent.mkdir()
    config_path.write_text(
        json.dumps(
            {
                "mjcf_path": "../assets/fixture.xml",
                "camera_name": "task_camera",
                "image_width": 640,
                "image_height": 480,
                "split_counts": {"train": 800, "val": 200, "test": 200},
            }
        ),
        encoding="utf-8",
    )

    config = load_dataset_config(config_path, generator_commit="commit-123")

    assert config.mjcf_path == fixture
    assert config.generator_commit == "commit-123"


@pytest.mark.parametrize("cup_count", (0, 1, 2))
def test_object_id_labels_preserve_zero_one_or_two_instances(cup_count: int) -> None:
    sample = build_labeled_sample(
        _raw_render(cup_count=cup_count, cup_rgba=(1.0, 0.4, 0.0, 1.0)),
        seed=42,
        scenario=DatasetScenario.for_cup_count(cup_count),
    )

    assert sample.rgb8.shape == (8, 10, 3)
    assert len(sample.instances) == cup_count
    assert all(instance.mask.shape == (8, 10) for instance in sample.instances)
    for instance in sample.instances:
        assert instance.mask.any()
        assert len(instance.polygon_xy) >= 3
        assert all(0.0 <= coordinate <= 1.0 for point in instance.polygon_xy for coordinate in point)


def test_material_color_is_not_used_to_build_labels() -> None:
    orange = build_labeled_sample(
        _raw_render(cup_count=2, cup_rgba=(1.0, 0.4, 0.0, 1.0)),
        seed=7,
        scenario=DatasetScenario.TWO_CUPS,
    )
    blue = build_labeled_sample(
        _raw_render(cup_count=2, cup_rgba=(0.0, 0.0, 1.0, 1.0)),
        seed=7,
        scenario=DatasetScenario.TWO_CUPS,
    )

    assert [item.body_name for item in orange.instances] == [
        item.body_name for item in blue.instances
    ]
    assert [item.polygon_xy for item in orange.instances] == [
        item.polygon_xy for item in blue.instances
    ]
    assert not np.array_equal(orange.rgb8, blue.rgb8)


def test_raw_render_rejects_mismatched_rgb_and_object_id_dimensions() -> None:
    with pytest.raises(ValueError, match="dimensions"):
        RawRender(
            rgb8=np.zeros((8, 10, 3), dtype=np.uint8),
            geom_ids=np.zeros((7, 10), dtype=np.int32),
            geom_body_ids=np.zeros(1, dtype=np.int32),
            body_names={0: "world"},
        )


class _FakeRenderer:
    def render(self, seed: int, scenario: DatasetScenario) -> RawRender:
        return _raw_render(
            cup_count=scenario.cup_count,
            cup_rgba=(1.0, ((seed % 17) + 1) / 18.0, 0.1, 1.0),
        )

    def close(self) -> None:
        pass


def test_dataset_manifest_and_labels_are_reproducible(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.xml"
    fixture.write_text("<mujoco/>", encoding="utf-8")
    config = DatasetConfig(
        mjcf_path=fixture,
        split_counts={"train": 4, "val": 4, "test": 4},
        generator_commit="a2c5e03",
    )
    first = generate_dataset(config, tmp_path / "first", renderer=_FakeRenderer())
    second = generate_dataset(config, tmp_path / "second", renderer=_FakeRenderer())

    assert first == second
    assert first["sample_count"] == 12
    assert first["split_counts"] == {"test": 4, "train": 4, "val": 4}
    assert first["class_instance_totals"] == {"plastic_cup": 12}
    for relative_path in first["artifacts"]:
        left = tmp_path / "first" / relative_path
        right = tmp_path / "second" / relative_path
        assert left.read_bytes() == right.read_bytes()
    assert json.loads((tmp_path / "first/dataset-manifest.json").read_text()) == first


def test_generate_dataset_refuses_existing_output_root(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.xml"
    fixture.write_text("<mujoco/>", encoding="utf-8")
    config = DatasetConfig(
        mjcf_path=fixture,
        split_counts={"train": 1, "val": 1, "test": 1},
        generator_commit="a2c5e03",
    )
    output = tmp_path / "dataset"
    output.mkdir()

    with pytest.raises(FileExistsError, match="output root"):
        generate_dataset(config, output, renderer=_FakeRenderer())


def test_repository_fixture_exposes_camera_targets_distractors_and_scenarios() -> None:
    fixture = (
        Path(__file__).parents[1] / "assets/mujoco/v5_multi_object_scene.xml"
    )
    root = ET.parse(fixture).getroot()
    names = {
        element.attrib["name"]
        for element in root.iter()
        if "name" in element.attrib
    }

    assert {
        "task_camera",
        "plastic_cup",
        "plastic_cup_b",
        "orange_bottle",
        "neutral_block",
        "cup_free_joint",
        "cup_b_free_joint",
        "bottle_free_joint",
        "task_start",
        "v5_no_cup",
        "v5_two_cups",
        "v5_cup_near_bottle",
    } <= names
    target_body = next(
        element
        for element in root.findall(".//body")
        if element.attrib.get("name") == "plastic_cup"
    )
    assert len(target_body.findall("geom")) == 26
