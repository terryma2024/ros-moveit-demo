from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from so101_demo.adapters.perception.mujoco_dataset.config import (
    DatasetConfig,
    limited_split_counts,
    load_dataset_config,
    split_seed_plan,
)
from so101_demo.adapters.perception.mujoco_dataset.generate import generate_dataset
from so101_demo.adapters.perception.mujoco_dataset.models import DatasetScenario, RawRender
from so101_demo.adapters.perception.mujoco_dataset.render import build_labeled_sample
from paths import PACKAGE_ROOT


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


def test_split_seed_ranges_accept_explicit_disjoint_starts() -> None:
    plan = split_seed_plan(
        {"train": 4, "val": 4, "test": 4},
        {"train": 400000, "val": 500000, "test": 600000},
    )

    assert plan == {
        "train": tuple(range(400000, 400004)),
        "val": tuple(range(500000, 500004)),
        "test": tuple(range(600000, 600004)),
    }


@pytest.mark.parametrize(
    "seed_starts",
    [
        {"train": 400000, "val": 500000},
        {"train": 400000, "val": 500000, "test": 600000, "extra": 700000},
        {"train": True, "val": 500000, "test": 600000},
        {"train": -1, "val": 500000, "test": 600000},
        {"train": 999999998, "val": 500000, "test": 600000},
        {"train": 400000, "val": 400003, "test": 600000},
    ],
)
def test_split_seed_ranges_reject_invalid_or_overlapping_starts(
    seed_starts: dict[str, int],
) -> None:
    with pytest.raises(ValueError, match="seed"):
        split_seed_plan({"train": 4, "val": 4, "test": 4}, seed_starts)


def test_twelve_sample_limit_keeps_all_splits_and_scenarios() -> None:
    assert limited_split_counts({"train": 800, "val": 200, "test": 200}, 12) == {
        "train": 4,
        "val": 4,
        "test": 4,
    }


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


def test_config_loads_explicit_seed_starts(tmp_path: Path) -> None:
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
                "split_counts": {"train": 4, "val": 4, "test": 4},
                "seed_starts": {
                    "train": 400000,
                    "val": 500000,
                    "test": 600000,
                },
            }
        ),
        encoding="utf-8",
    )

    config = load_dataset_config(config_path, generator_commit="commit-456")

    assert dict(config.seed_starts) == {
        "train": 400000,
        "val": 500000,
        "test": 600000,
    }


def test_sample_limit_cannot_hide_full_seed_range_overlap(tmp_path: Path) -> None:
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
                "seed_starts": {
                    "train": 400000,
                    "val": 400500,
                    "test": 600000,
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="seed ranges must be disjoint"):
        load_dataset_config(
            config_path,
            generator_commit="commit-789",
            sample_limit=12,
        )


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
        assert all(
            0.0 <= coordinate <= 1.0 for point in instance.polygon_xy for coordinate in point
        )


@pytest.mark.parametrize(
    ("scenario", "expected_names"),
    [
        (DatasetScenario.NO_CUP, []),
        (DatasetScenario.ONE_CUP_DISTRACTORS, ["plastic_cup"]),
        (DatasetScenario.CUP_NEAR_BOTTLE, ["plastic_cup"]),
        (DatasetScenario.TWO_CUPS, ["plastic_cup", "plastic_cup_b"]),
    ],
)
def test_scenario_contract_excludes_inactive_cup_body_ids(
    scenario: DatasetScenario,
    expected_names: list[str],
) -> None:
    render_with_stray_inactive_ids = _raw_render(
        cup_count=2,
        cup_rgba=(1.0, 0.4, 0.0, 1.0),
    )

    sample = build_labeled_sample(
        render_with_stray_inactive_ids,
        seed=42,
        scenario=scenario,
    )

    assert [instance.body_name for instance in sample.instances] == expected_names


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


def test_dataset_manifest_records_explicit_seed_ranges(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.xml"
    fixture.write_text("<mujoco/>", encoding="utf-8")
    config = DatasetConfig(
        mjcf_path=fixture,
        split_counts={"train": 4, "val": 4, "test": 4},
        generator_commit="fresh-data-commit",
        seed_starts={"train": 400000, "val": 500000, "test": 600000},
    )

    manifest = generate_dataset(config, tmp_path / "fresh", renderer=_FakeRenderer())

    assert manifest["seed_ranges"] == {
        "train": [400000, 400003],
        "val": [500000, 500003],
        "test": [600000, 600003],
    }


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
    fixture = PACKAGE_ROOT / "assets/mujoco/multi_object_scene.xml"
    root = ET.parse(fixture).getroot()
    names = {element.attrib["name"] for element in root.iter() if "name" in element.attrib}

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
        "no_cup",
        "two_cups",
        "cup_near_bottle",
    } <= names
    target_body = next(
        element
        for element in root.findall(".//body")
        if element.attrib.get("name") == "plastic_cup"
    )
    assert len(target_body.findall("geom")) == 26


def test_fresh_benchmark_dataset_config_uses_preregistered_seed_namespace() -> None:
    config_path = PACKAGE_ROOT / "config/perception_benchmark/fresh_dataset.yaml"

    config = load_dataset_config(config_path, generator_commit="fresh-source")

    assert config.split_counts == {"train": 480, "val": 200, "test": 200}
    assert config.seed_starts == {
        "train": 700000,
        "val": 800000,
        "test": 900000,
    }


# ----------------------------------------------------------------------------------------------------------------------
# the head-camera profile: the same four scenarios, one camera domain, and a frozen production-camera seal that the
# generation program refuses to run without.
# ----------------------------------------------------------------------------------------------------------------------

from so101_demo.act.head_camera_geometry.contract import scene_source_digests  # noqa: E402
from so101_demo.adapters.perception.mujoco_dataset.config import (
    GeometrySealRequirement,
    split_scene_plan,
)
from so101_demo.adapters.perception.mujoco_dataset.verify import verify_head_search_manifest
from so101_demo.perception_benchmark.contracts import canonical_sha256  # noqa: E402

HEAD_CONFIG_PATH = PACKAGE_ROOT / "config/perception/head_camera_yolo_seg.yaml"
HEAD_SMOKE_CONFIG_PATH = (
    PACKAGE_ROOT / "config/perception/head_camera_yolo_seg_smoke.yaml"
)


class _HeadFakeRenderer:
    """A head-profile render that reports the camera identity the manifest must carry."""

    def __init__(
        self,
        seal: dict | None = None,
        camera_name: str = "head_camera",
        local_position_m: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> None:
        self.camera_name = camera_name
        self.local_position_m = tuple(float(value) for value in local_position_m)
        self.neck_rad = 0.05
        self.fovy_rad = 1.0471975511965976 if seal is None else float(seal["camera"]["fovy_rad"])
        if seal is None:
            self.pose = ((-0.06, 0.06, 0.43), (0.9, 0.0, 0.0, 0.44))
        else:
            from so101_demo.act.head_camera_geometry.validation import (
                camera_pose_from_seal,
                quaternion_wxyz_from_xyaxes,
            )

            predicted, axes = camera_pose_from_seal(seal, self.neck_rad)
            self.pose = (
                tuple(float(value) for value in predicted),
                quaternion_wxyz_from_xyaxes(axes),
            )

    def render(self, seed: int, scenario: DatasetScenario) -> RawRender:
        base = _raw_render(cup_count=scenario.cup_count, cup_rgba=(1.0, 0.4, 0.3, 1.0))
        return RawRender(
            rgb8=base.rgb8,
            geom_ids=base.geom_ids,
            geom_body_ids=base.geom_body_ids,
            body_names=base.body_names,
            camera_name=self.camera_name,
            neck_rad=self.neck_rad,
            camera_position_m=self.pose[0],
            camera_quaternion_wxyz=self.pose[1],
            camera_local_position_m=self.local_position_m,
            camera_local_xyaxes=(-1.0, 0.0, 0.0, 0.0, -0.6, 0.8),
            camera_fovy_rad=self.fovy_rad,
            arm_pose_rad=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )

    def close(self) -> None:
        pass


def _write_head_scene(tmp_path: Path) -> Path:
    fixture = tmp_path / "head_scene.xml"
    fixture.write_text("<mujoco/>", encoding="utf-8")
    return fixture


def _geometry_seal(*, mjcf_path: Path, camera_name: str = "head_camera") -> dict:
    document = {
        "schema_version": 1,
        "camera_name": camera_name,
        "validation_arm_rad": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "camera_mount_origin_m": [-0.06, 0.06, 0.43],
        "camera_mount_xyaxes": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0],
        "image_width": 10,
        "image_height": 8,
        "horizontal_fov_rad": 1.312,
        "camera": {
            "camera_name": camera_name,
            "width": 10,
            "height": 8,
            "fovy_rad": 1.0471975511965976,
            "distortion_model": "plumb_bob",
            "distortion": [0.0, 0.0, 0.0, 0.0, 0.0],
            "parent_body": "head_mount",
            "local_position_m": [0.0, 0.0, 0.0],
            "local_xyaxes": [-1.0, 0.0, 0.0, 0.0, -0.6, 0.8],
        },
        "lock_valid_neck_rad": [-3.14159, 3.14159],
        "required_search_domain_rad": [-0.3, 0.3],
        "safe_interval_contains_required_domain": True,
        "source_digests": dict(scene_source_digests(mjcf_path)),
    }
    document["seal_sha256"] = canonical_sha256(document)
    return document


def _head_config(
    tmp_path: Path,
    *,
    accepted_seal_sha256: str,
    counts: dict[str, int] | None = None,
    camera_name: str = "head_camera",
    promotable: bool = True,
) -> DatasetConfig:
    fixture = _write_head_scene(tmp_path)
    return DatasetConfig(
        mjcf_path=fixture,
        split_counts=counts or {"train": 4, "val": 4, "test": 4},
        generator_commit="head-commit",
        camera_name=camera_name,
        image_width=10,
        image_height=8,
        seed_starts={"train": 400000, "val": 500000, "test": 600000},
        dataset_contract="so101-head-search-yolo-seg-v1",
        geometry_seal=GeometrySealRequirement(
            required=True, accepted_seal_sha256=accepted_seal_sha256
        ),
        neck_yaw_rad=(-0.35, 0.35),
        camera_jitter_m=(0.0, 0.0),
        arm_pose_rad=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        promotable=promotable,
    )


def test_head_camera_plan_has_four_balanced_scenarios() -> None:
    plan = split_scene_plan(
        camera_name="head_camera", counts={"train": 800, "val": 200, "test": 200}
    )

    assert plan.counts("train") == {
        "no_cup": 200,
        "one_cup_distractors": 200,
        "two_cups": 200,
        "cup_near_bottle": 200,
    }
    assert plan.counts("val") == {
        "no_cup": 50,
        "one_cup_distractors": 50,
        "two_cups": 50,
        "cup_near_bottle": 50,
    }
    assert plan.counts("test") == plan.counts("val")
    assert len(plan.samples) == 1200
    assert all(item.camera_name == "head_camera" for item in plan.samples)
    assert plan.promotable is True


def test_head_camera_plan_groups_are_unique_and_split_disjoint() -> None:
    plan = split_scene_plan(camera_name="head_camera", counts={"train": 4, "val": 4, "test": 4})

    groups = [item.scene_group_id for item in plan.samples]
    assert len(set(groups)) == len(groups)
    assert {item.split for item in plan.samples} == {"train", "val", "test"}
    assert plan.counts("train") == {
        "no_cup": 1,
        "one_cup_distractors": 1,
        "two_cups": 1,
        "cup_near_bottle": 1,
    }
    assert plan.samples[0].scene_group_id == f"scene-{plan.samples[0].seed:09d}"


def test_head_camera_plan_rejects_counts_that_cannot_be_split_four_ways() -> None:
    with pytest.raises(ValueError, match="HEAD_SCENE_PLAN_COUNTS_INVALID"):
        split_scene_plan(camera_name="head_camera", counts={"train": 10, "val": 4, "test": 4})


def test_smoke_head_camera_plan_is_balanced_but_never_promotable() -> None:
    plan = split_scene_plan(
        camera_name="head_camera",
        counts={"train": 32, "val": 8, "test": 8},
        promotable=False,
    )

    assert plan.promotable is False
    assert plan.counts("val") == {
        "no_cup": 2,
        "one_cup_distractors": 2,
        "two_cups": 2,
        "cup_near_bottle": 2,
    }


def test_head_camera_configs_freeze_the_production_camera_counts_and_seal() -> None:
    production = load_dataset_config(HEAD_CONFIG_PATH, generator_commit="head-commit")
    smoke = load_dataset_config(HEAD_SMOKE_CONFIG_PATH, generator_commit="head-commit")

    assert production.camera_name == "head_camera"
    assert dict(production.split_counts) == {"train": 800, "val": 200, "test": 200}
    assert production.geometry_seal is not None
    assert production.geometry_seal.required is True
    assert len(production.geometry_seal.accepted_seal_sha256) == 64
    assert production.promotable is True
    assert smoke.camera_name == "head_camera"
    assert dict(smoke.split_counts) == {"train": 32, "val": 8, "test": 8}
    assert smoke.promotable is False
    assert smoke.geometry_seal is not None
    assert smoke.geometry_seal.accepted_seal_sha256 == production.geometry_seal.accepted_seal_sha256


def test_head_camera_generation_requires_the_geometry_seal(tmp_path: Path) -> None:
    seal = _geometry_seal(mjcf_path=_write_head_scene(tmp_path))
    config = _head_config(tmp_path, accepted_seal_sha256="f" * 64)

    with pytest.raises(ValueError, match="HEAD_CAMERA_GEOMETRY_SEAL_REQUIRED"):
        generate_dataset(config, tmp_path / "no-seal", renderer=_HeadFakeRenderer(seal))

    with pytest.raises(ValueError, match="HEAD_CAMERA_GEOMETRY_SEAL_DRIFT"):
        generate_dataset(
            config, tmp_path / "drifted", geometry_seal=seal, renderer=_HeadFakeRenderer(seal)
        )


def test_head_camera_generation_records_groups_camera_and_mask_digests(tmp_path: Path) -> None:
    seal = _geometry_seal(mjcf_path=_write_head_scene(tmp_path))
    config = _head_config(tmp_path, accepted_seal_sha256=seal["seal_sha256"])

    manifest = generate_dataset(
        config, tmp_path / "head", geometry_seal=seal, renderer=_HeadFakeRenderer(seal)
    )

    assert manifest["camera_name"] == "head_camera"
    assert manifest["dataset_contract"] == "so101-head-search-yolo-seg-v1"
    assert manifest["geometry_seal_sha256"] == seal["seal_sha256"]
    sample = manifest["samples"][0]
    assert sample["scene_group_id"] == f"scene-{sample['seed']:09d}"
    assert sample["camera"]["frame_id"] == "head_camera"
    assert len(sample["camera"]["k"]) == 9
    assert sample["camera"]["distortion"] == [0.0, 0.0, 0.0, 0.0, 0.0]
    truth = json.loads((tmp_path / "head" / sample["truth"]).read_text())
    assert len(truth["raw_mask_sha256"]) == 64
    assert len({item["scene_group_id"] for item in manifest["samples"]}) == len(manifest["samples"])


def test_head_camera_generation_refuses_a_non_head_camera_render(tmp_path: Path) -> None:
    seal = _geometry_seal(mjcf_path=_write_head_scene(tmp_path))
    config = _head_config(
        tmp_path, accepted_seal_sha256=seal["seal_sha256"], camera_name="task_camera"
    )

    with pytest.raises(ValueError, match="HEAD_CAMERA_GEOMETRY_SEAL_CAMERA_MISMATCH"):
        generate_dataset(
            config, tmp_path / "wrong-camera", geometry_seal=seal, renderer=_HeadFakeRenderer(seal)
        )


def test_verify_head_search_manifest_accepts_a_sealed_head_dataset(tmp_path: Path) -> None:
    seal = _geometry_seal(mjcf_path=_write_head_scene(tmp_path))
    config = _head_config(tmp_path, accepted_seal_sha256=seal["seal_sha256"])
    manifest = generate_dataset(
        config, tmp_path / "head", geometry_seal=seal, renderer=_HeadFakeRenderer(seal)
    )

    report = verify_head_search_manifest(
        manifest,
        dataset_root=tmp_path / "head",
        geometry_seal=seal,
        expected_train=4,
        expected_val=4,
        expected_test=4,
    )

    assert report["status"] == "OK"
    assert report["scene_group_count"] == 12
    assert report["promotable"] is True


def test_verify_head_search_manifest_refuses_a_smoke_manifest_as_production(tmp_path: Path) -> None:
    seal = _geometry_seal(mjcf_path=_write_head_scene(tmp_path))
    config = _head_config(tmp_path, accepted_seal_sha256=seal["seal_sha256"], promotable=False)
    manifest = generate_dataset(
        config, tmp_path / "smoke", geometry_seal=seal, renderer=_HeadFakeRenderer(seal)
    )

    with pytest.raises(ValueError, match="HEAD_DATASET_NOT_PROMOTABLE"):
        verify_head_search_manifest(
            manifest,
            dataset_root=tmp_path / "smoke",
            geometry_seal=seal,
            expected_train=4,
            expected_val=4,
            expected_test=4,
        )
    assert (
        verify_head_search_manifest(
            manifest,
            dataset_root=tmp_path / "smoke",
            geometry_seal=seal,
            expected_train=4,
            expected_val=4,
            expected_test=4,
            require_non_promotable=True,
        )["promotable"]
        is False
    )


def test_verify_head_search_manifest_refuses_count_drift_and_group_leakage(tmp_path: Path) -> None:
    seal = _geometry_seal(mjcf_path=_write_head_scene(tmp_path))
    config = _head_config(tmp_path, accepted_seal_sha256=seal["seal_sha256"])
    manifest = generate_dataset(
        config, tmp_path / "head", geometry_seal=seal, renderer=_HeadFakeRenderer(seal)
    )

    with pytest.raises(ValueError, match="HEAD_DATASET_COUNT_MISMATCH"):
        verify_head_search_manifest(
            manifest,
            dataset_root=tmp_path / "head",
            geometry_seal=seal,
            expected_train=8,
            expected_val=4,
            expected_test=4,
        )

    leaked = json.loads(json.dumps(manifest))
    leaked["samples"][1]["scene_group_id"] = leaked["samples"][0]["scene_group_id"]
    with pytest.raises(ValueError, match="HEAD_DATASET_SCENE_GROUP_DUPLICATE"):
        verify_head_search_manifest(
            leaked,
            dataset_root=tmp_path / "head",
            geometry_seal=seal,
            expected_train=4,
            expected_val=4,
            expected_test=4,
        )


def test_scene_group_ids_are_camera_independent_world_identities() -> None:
    plan = split_scene_plan(camera_name="head_camera", counts={"train": 4, "val": 4, "test": 4})

    assert plan.samples[0].scene_group_id == f"scene-{plan.samples[0].seed:09d}"
    assert all(not item.scene_group_id.startswith("head_camera") for item in plan.samples)


def test_cross_domain_seed_reuse_is_refused_across_split_names() -> None:
    from so101_demo.cli.verify_head_search_dataset import cross_domain_report

    head = {"samples": [{"seed": 1, "split": "train", "scene_group_id": "scene-000000001"}]}
    task = {"samples": [{"seed": 1, "split": "test", "scene_group_id": "scene-000000001"}]}

    with pytest.raises(ValueError, match="HEAD_DATASET_SEED_LEAK"):
        cross_domain_report(head, task)


def test_cross_domain_scene_group_leak_is_refused_when_splits_disagree() -> None:
    from so101_demo.cli.verify_head_search_dataset import cross_domain_report

    head = {"samples": [{"seed": 1, "split": "train", "scene_group_id": "scene-000000001"}]}
    task = {"samples": [{"seed": 2, "split": "test", "scene_group_id": "scene-000000001"}]}

    with pytest.raises(ValueError, match="SCENE_GROUP_SPLIT_LEAK"):
        cross_domain_report(head, task)


def test_cross_domain_report_refuses_a_malformed_task_partition() -> None:
    from so101_demo.cli.verify_head_search_dataset import cross_domain_report

    head = {"samples": [{"seed": 1, "split": "train", "scene_group_id": "scene-000000001"}]}
    task = {"samples": [{"seed": 2, "split": "test", "scene_group_id": ""}]}

    with pytest.raises(ValueError, match="HEAD_DATASET_TASK_PARTITION_INVALID"):
        cross_domain_report(head, task)


def test_head_camera_generation_never_moves_the_sealed_camera(tmp_path: Path) -> None:
    seal = _geometry_seal(mjcf_path=_write_head_scene(tmp_path))
    config = _head_config(tmp_path, accepted_seal_sha256=seal["seal_sha256"])

    jittered = _HeadFakeRenderer(seal, local_position_m=(-0.014, -0.002, 0.009))
    with pytest.raises(ValueError, match="HEAD_DATASET_CAMERA_LOCAL_POSE_DRIFT"):
        generate_dataset(config, tmp_path / "jitter", geometry_seal=seal, renderer=jittered)

    manifest = generate_dataset(
        config, tmp_path / "steady", geometry_seal=seal, renderer=_HeadFakeRenderer(seal)
    )
    sample = manifest["samples"][0]
    assert sample["camera"]["local_position_m"] == [0.0, 0.0, 0.0]
    assert sample["image_sha256"] and len(sample["image_sha256"]) == 64


def test_verify_head_search_manifest_refuses_a_modified_file(tmp_path: Path) -> None:
    seal = _geometry_seal(mjcf_path=_write_head_scene(tmp_path))
    config = _head_config(tmp_path, accepted_seal_sha256=seal["seal_sha256"])
    manifest = generate_dataset(
        config, tmp_path / "head", geometry_seal=seal, renderer=_HeadFakeRenderer(seal)
    )

    (tmp_path / "head" / manifest["samples"][0]["image"]).write_bytes(b"CORRUPTED FILE\n")

    with pytest.raises(ValueError, match="HEAD_DATASET_FILE_DIGEST_MISMATCH"):
        verify_head_search_manifest(
            manifest,
            dataset_root=tmp_path / "head",
            geometry_seal=seal,
            expected_train=4,
            expected_val=4,
            expected_test=4,
        )


def test_verify_head_search_manifest_refuses_a_reused_file_path(tmp_path: Path) -> None:
    seal = _geometry_seal(mjcf_path=_write_head_scene(tmp_path))
    config = _head_config(tmp_path, accepted_seal_sha256=seal["seal_sha256"])
    manifest = generate_dataset(
        config, tmp_path / "head", geometry_seal=seal, renderer=_HeadFakeRenderer(seal)
    )

    reused = json.loads(json.dumps(manifest))
    reused["samples"][1]["image"] = reused["samples"][0]["image"]

    with pytest.raises(ValueError, match="HEAD_DATASET_FILE_REUSED"):
        verify_head_search_manifest(
            reused,
            dataset_root=tmp_path / "head",
            geometry_seal=seal,
            expected_train=4,
            expected_val=4,
            expected_test=4,
        )


def test_verify_head_search_manifest_refuses_an_incomplete_camera_identity(tmp_path: Path) -> None:
    seal = _geometry_seal(mjcf_path=_write_head_scene(tmp_path))
    config = _head_config(tmp_path, accepted_seal_sha256=seal["seal_sha256"])
    manifest = generate_dataset(
        config, tmp_path / "head", geometry_seal=seal, renderer=_HeadFakeRenderer(seal)
    )

    for mutation in (
        {"k": [float("nan")] * 9, "position_m": [0.0, 0.0, 0.0]},
        {"neck_rad": None, "quaternion_wxyz": [1.0, 0.0, 0.0, 0.0]},
    ):
        broken = json.loads(json.dumps(manifest))
        broken["samples"][0]["camera"].update(mutation)
        with pytest.raises(ValueError, match="HEAD_DATASET_CAMERA_IDENTITY_INVALID"):
            verify_head_search_manifest(
                broken,
                dataset_root=tmp_path / "head",
                geometry_seal=seal,
                expected_train=4,
                expected_val=4,
                expected_test=4,
            )


def test_verify_head_search_manifest_refuses_a_truth_that_belongs_to_another_group(
    tmp_path: Path,
) -> None:
    seal = _geometry_seal(mjcf_path=_write_head_scene(tmp_path))
    config = _head_config(tmp_path, accepted_seal_sha256=seal["seal_sha256"])
    manifest = generate_dataset(
        config, tmp_path / "head", geometry_seal=seal, renderer=_HeadFakeRenderer(seal)
    )
    sample = manifest["samples"][0]
    truth_path = tmp_path / "head" / sample["truth"]
    truth = json.loads(truth_path.read_text())
    truth["scene_group_id"] = "scene-999999999"
    truth_path.write_text(json.dumps(truth, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest["samples"][0]["truth_sha256"] = hashlib.sha256(truth_path.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="HEAD_DATASET_TRUTH_IDENTITY_MISMATCH"):
        verify_head_search_manifest(
            manifest,
            dataset_root=tmp_path / "head",
            geometry_seal=seal,
            expected_train=4,
            expected_val=4,
            expected_test=4,
        )


def test_verify_head_search_manifest_refuses_a_symlink_escape(tmp_path: Path) -> None:
    import shutil

    seal = _geometry_seal(mjcf_path=_write_head_scene(tmp_path))
    config = _head_config(tmp_path, accepted_seal_sha256=seal["seal_sha256"])
    manifest = generate_dataset(
        config, tmp_path / "head", geometry_seal=seal, renderer=_HeadFakeRenderer(seal)
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    foreign = outside / "foreign.png"
    shutil.copy(tmp_path / "head" / manifest["samples"][1]["image"], foreign)
    (tmp_path / "head" / "nested").symlink_to(outside, target_is_directory=True)
    broken = json.loads(json.dumps(manifest))
    broken["samples"][1]["image"] = "nested/foreign.png"
    broken["samples"][1]["image_sha256"] = hashlib.sha256(foreign.read_bytes()).hexdigest()
    broken["samples"][1]["image_bytes"] = len(foreign.read_bytes())

    with pytest.raises(ValueError, match="HEAD_DATASET_FILE_PATH_INVALID"):
        verify_head_search_manifest(
            broken,
            dataset_root=tmp_path / "head",
            geometry_seal=seal,
            expected_train=4,
            expected_val=4,
            expected_test=4,
        )


def test_verify_head_search_manifest_refuses_a_symlink_alias(tmp_path: Path) -> None:
    seal = _geometry_seal(mjcf_path=_write_head_scene(tmp_path))
    config = _head_config(tmp_path, accepted_seal_sha256=seal["seal_sha256"])
    manifest = generate_dataset(
        config, tmp_path / "head", geometry_seal=seal, renderer=_HeadFakeRenderer(seal)
    )
    target = tmp_path / "head" / manifest["samples"][0]["image"]
    (tmp_path / "head" / "alias.png").symlink_to(target)
    broken = json.loads(json.dumps(manifest))
    broken["samples"][1]["image"] = "alias.png"
    broken["samples"][1]["image_sha256"] = broken["samples"][0]["image_sha256"]
    broken["samples"][1]["image_bytes"] = broken["samples"][0]["image_bytes"]

    with pytest.raises(ValueError, match="HEAD_DATASET_FILE_REUSED"):
        verify_head_search_manifest(
            broken,
            dataset_root=tmp_path / "head",
            geometry_seal=seal,
            expected_train=4,
            expected_val=4,
            expected_test=4,
        )


def test_verify_head_search_manifest_refuses_a_mask_shaped_like_another_image(
    tmp_path: Path,
) -> None:
    seal = _geometry_seal(mjcf_path=_write_head_scene(tmp_path))
    config = _head_config(tmp_path, accepted_seal_sha256=seal["seal_sha256"])
    manifest = generate_dataset(
        config, tmp_path / "head", geometry_seal=seal, renderer=_HeadFakeRenderer(seal)
    )
    index = next(
        position
        for position, item in enumerate(manifest["samples"])
        if item["scenario"] != "no_cup"
    )
    sample = manifest["samples"][index]
    truth_path = tmp_path / "head" / sample["truth"]
    truth = json.loads(truth_path.read_text())
    assert truth["instances"], "a cup scenario has instances"
    height, width = truth["instances"][0]["mask_shape_hw"]
    truth["instances"][0]["mask_shape_hw"] = [width * 2, height // 2]
    truth_path.write_text(json.dumps(truth, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest["samples"][index]["truth_sha256"] = hashlib.sha256(truth_path.read_bytes()).hexdigest()
    manifest["samples"][index]["truth_bytes"] = len(truth_path.read_bytes())

    with pytest.raises(ValueError, match="HEAD_DATASET_TRUTH_IDENTITY_MISMATCH"):
        verify_head_search_manifest(
            manifest,
            dataset_root=tmp_path / "head",
            geometry_seal=seal,
            expected_train=4,
            expected_val=4,
            expected_test=4,
        )


def test_verify_head_search_manifest_refuses_a_sample_aggregate_the_truth_does_not_have(
    tmp_path: Path,
) -> None:
    seal = _geometry_seal(mjcf_path=_write_head_scene(tmp_path))
    config = _head_config(tmp_path, accepted_seal_sha256=seal["seal_sha256"])
    manifest = generate_dataset(
        config, tmp_path / "head", geometry_seal=seal, renderer=_HeadFakeRenderer(seal)
    )
    broken = json.loads(json.dumps(manifest))
    broken["samples"][0]["raw_mask_sha256"] = "f" * 64

    with pytest.raises(ValueError, match="HEAD_DATASET_TRUTH_IDENTITY_MISMATCH"):
        verify_head_search_manifest(
            broken,
            dataset_root=tmp_path / "head",
            geometry_seal=seal,
            expected_train=4,
            expected_val=4,
            expected_test=4,
        )


def test_head_camera_generation_refuses_a_non_finite_orientation(tmp_path: Path) -> None:
    seal = _geometry_seal(mjcf_path=_write_head_scene(tmp_path))
    config = _head_config(tmp_path, accepted_seal_sha256=seal["seal_sha256"])

    class _NanOrientation:
        def __init__(self, inner):
            self.inner = inner

        def render(self, seed, scenario):
            render = self.inner.render(seed, scenario)
            return replace(render, camera_quaternion_wxyz=(float("nan"),) * 4)

        def close(self):
            self.inner.close()

    with pytest.raises(ValueError, match="HEAD_DATASET_CAMERA_IDENTITY_INVALID"):
        generate_dataset(
            config,
            tmp_path / "nan",
            geometry_seal=seal,
            renderer=_NanOrientation(_HeadFakeRenderer(seal)),
        )


def test_head_camera_generation_refuses_a_render_outside_the_declared_neck_range(
    tmp_path: Path,
) -> None:
    seal = _geometry_seal(mjcf_path=_write_head_scene(tmp_path))
    config = _head_config(tmp_path, accepted_seal_sha256=seal["seal_sha256"])

    class _OutOfRangeNeck:
        def __init__(self, inner, neck_rad):
            self.inner = inner
            self.neck_rad = float(neck_rad)

        def render(self, seed, scenario):
            render = self.inner.render(seed, scenario)
            position, quaternion = self.inner.pose
            return replace(
                render,
                neck_rad=self.neck_rad,
                camera_position_m=position,
                camera_quaternion_wxyz=quaternion,
            )

        def close(self):
            self.inner.close()

    for neck_rad in (0.5, 6.283275307179586):
        with pytest.raises(ValueError, match="HEAD_DATASET_CAMERA_NECK_UNSAFE"):
            generate_dataset(
                config,
                tmp_path / f"neck-{neck_rad}",
                geometry_seal=seal,
                renderer=_OutOfRangeNeck(_HeadFakeRenderer(seal), neck_rad),
            )
