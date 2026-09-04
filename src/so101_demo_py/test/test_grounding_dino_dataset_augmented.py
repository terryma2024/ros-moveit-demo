from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from so101_demo.adapters.perception.mujoco_dataset import (
    DatasetConfig,
    DatasetScenario,
    RawRender,
    decode_binary_mask_rle,
    generate_dataset,
)
from so101_demo.training.grounding_dino_dataset import (
    GroundingDinoDatasetError,
    convert_dataset,
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


class _Renderer:
    def render(self, seed: int, scenario: DatasetScenario) -> RawRender:
        if scenario == DatasetScenario.PARTIALLY_OCCLUDED_CUP:
            return _render(
                visible_slice=(slice(100, 108), slice(200, 208)),
                amodal_slice=(slice(96, 112), slice(200, 210)),
            )
        return _render(visible_slice=(slice(100, 108), slice(200, 208)))

    def close(self) -> None:
        pass


def _source(tmp_path: Path) -> Path:
    fixture = tmp_path / "fixture.xml"
    fixture.write_text("<mujoco/>", encoding="utf-8")
    source = tmp_path / "source"
    config = DatasetConfig(
        mjcf_path=fixture,
        split_counts={"train": 1, "val": 1, "test": 1},
        generator_commit="c" * 40,
        seed_starts={"train": 410000000, "val": 420000000, "test": 440000000},
        scenario_quotas={
            "train": {DatasetScenario.PARTIALLY_OCCLUDED_CUP.value: 1},
            "val": {DatasetScenario.SMALL_FAR_CUP.value: 1},
            "test": {DatasetScenario.PARTIALLY_OCCLUDED_CUP.value: 1},
        },
    )
    generate_dataset(config, source, renderer=_Renderer())
    return source


def test_schema_v2_conversion_verifies_occlusion_and_profiles_small_targets(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    output = tmp_path / "converted"

    convert_dataset(
        source,
        output,
        source_archive_sha256="a" * 64,
        converter_commit="b" * 40,
    )

    train = json.loads((output / "train/inventory.json").read_text(encoding="utf-8"))
    profile = json.loads((output / "dataset-profile.json").read_text(encoding="utf-8"))
    occlusion = train["samples"][0]["boxes"][0]["occlusion"]
    assert occlusion == {
        "amodal_pixel_count": 160,
        "occluded_pixel_count": 96,
        "occluder_body_name": "orange_bottle",
        "state": "partial",
        "visible_fraction": 0.4,
    }
    assert profile["train"]["partial_occlusion"] == {
        "measured_none": 0,
        "measured_partial": 1,
        "unmeasured": 0,
    }
    assert profile["val"]["area_bucket_counts"]["small"] == 1
    assert profile["test"] == {"sample_count": 1, "sealed": True}


def test_schema_v2_truth_persists_visible_rle_for_unmeasured_instance(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)

    truth = json.loads((source / "truth/val/420000000.json").read_text(encoding="utf-8"))
    instance = truth["instances"][0]
    mask = decode_binary_mask_rle(instance["visible_mask_rle_counts"], instance["mask_shape_hw"])

    assert instance["occlusion_measured"] is False
    assert (
        instance["visible_mask_sha256"]
        == hashlib.sha256(mask.astype(np.uint8).tobytes(order="C")).hexdigest()
    )
    assert int(mask.sum()) == instance["visible_pixel_count"] == 64


def test_schema_v2_conversion_fails_closed_on_tampered_occlusion_rle(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    truth_path = source / "truth/train/410000000.json"
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    truth["instances"][0]["amodal_mask_rle_counts"][-1] += 1
    truth_path.write_text(json.dumps(truth), encoding="utf-8")

    with pytest.raises(GroundingDinoDatasetError, match="OCCLUSION_TRUTH_INVALID"):
        convert_dataset(
            source,
            tmp_path / "converted",
            source_archive_sha256="a" * 64,
            converter_commit="b" * 40,
        )


def test_schema_v2_conversion_fails_closed_on_tampered_unmeasured_visible_rle(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    truth_path = source / "truth/val/420000000.json"
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    truth["instances"][0]["visible_mask_rle_counts"][-1] += 1
    truth_path.write_text(json.dumps(truth), encoding="utf-8")

    with pytest.raises(GroundingDinoDatasetError, match="VISIBLE_TRUTH_INVALID"):
        convert_dataset(
            source,
            tmp_path / "converted",
            source_archive_sha256="a" * 64,
            converter_commit="b" * 40,
        )


def test_schema_v2_conversion_rejects_scenario_quota_manifest_mismatch(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    manifest_path = source / "dataset-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["scenario_quotas"]["train"] = {"small_far_cup": 1}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(GroundingDinoDatasetError, match="MANIFEST_INVALID"):
        convert_dataset(
            source,
            tmp_path / "converted",
            source_archive_sha256="a" * 64,
            converter_commit="b" * 40,
        )


def test_schema_v2_conversion_rejects_seed_overlap_across_splits(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    manifest_path = source / "dataset-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["samples"][1]["seed"] = manifest["samples"][0]["seed"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(GroundingDinoDatasetError, match="SPLIT_SEEDS_OVERLAP"):
        convert_dataset(
            source,
            tmp_path / "converted",
            source_archive_sha256="a" * 64,
            converter_commit="b" * 40,
        )
