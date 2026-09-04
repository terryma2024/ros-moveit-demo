import hashlib
import json
from pathlib import Path

import pytest
from so101_demo.cli.prepare_grounding_dino_dataset import main
from so101_demo.training.grounding_dino_dataset import (
    GroundingDinoDatasetError,
    convert_dataset,
    polygon_to_box,
)

ARCHIVE_SHA = "a" * 64
CONVERTER_COMMIT = "b" * 40


def _write(path: Path, payload: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, bytes):
        path.write_bytes(payload)
    else:
        path.write_text(payload, encoding="utf-8")


def _source(root: Path) -> Path:
    polygon_a = [[0.1, 0.2], [0.4, 0.2], [0.4, 0.6], [0.1, 0.6]]
    polygon_b = [[0.6, 0.1], [1.0, 0.1], [1.0, 0.4], [0.6, 0.4]]
    samples = [
        {
            "seed": 100,
            "split": "train",
            "scenario": "two_cups",
            "configured_cup_count": 2,
            "visible_instance_count": 2,
            "image": "images/train/000000100.png",
            "label": "labels/train/000000100.txt",
            "truth": "truth/train/000000100.json",
        },
        {
            "seed": 200,
            "split": "val",
            "scenario": "no_cup",
            "configured_cup_count": 0,
            "visible_instance_count": 0,
            "image": "images/val/000000200.png",
            "label": "labels/val/000000200.txt",
            "truth": "truth/val/000000200.json",
        },
        {
            "seed": 300,
            "split": "test",
            "scenario": "one_cup_distractors",
            "configured_cup_count": 1,
            "visible_instance_count": 1,
            "image": "images/test/000000300.png",
            "label": "labels/test/000000300.txt",
            "truth": "truth/test/000000300.json",
        },
    ]
    _write(root / "images/train/000000100.png", b"train-image")
    _write(root / "images/val/000000200.png", b"val-image")
    _write(root / "images/test/000000300.png", b"test-image")
    _write(
        root / "labels/train/000000100.txt",
        "0 0.1 0.2 0.4 0.2 0.4 0.6 0.1 0.6\n0 0.6 0.1 1.0 0.1 1.0 0.4 0.6 0.4\n",
    )
    _write(root / "labels/val/000000200.txt", "")
    _write(root / "labels/test/000000300.txt", "sealed-test-label-is-opaque\n")
    _write(
        root / "truth/train/000000100.json",
        json.dumps(
            {
                "seed": 100,
                "split": "train",
                "scenario": "two_cups",
                "configured_cup_count": 2,
                "visible_instance_count": 2,
                "instances": [
                    {
                        "body_id": 1,
                        "body_name": "plastic_cup",
                        "visible_pixel_count": 1200,
                        "polygon_xy": polygon_a,
                    },
                    {
                        "body_id": 2,
                        "body_name": "plastic_cup_b",
                        "visible_pixel_count": 900,
                        "polygon_xy": polygon_b,
                    },
                ],
            }
        ),
    )
    _write(
        root / "truth/val/000000200.json",
        json.dumps(
            {
                "seed": 200,
                "split": "val",
                "scenario": "no_cup",
                "configured_cup_count": 0,
                "visible_instance_count": 0,
                "instances": [],
            }
        ),
    )
    _write(root / "truth/test/000000300.json", "sealed-test-truth-is-opaque\n")
    _write(
        root / "dataset.yaml",
        "path: .\ntrain: images/train\nval: images/val\ntest: images/test\n"
        "names:\n  0: plastic_cup\n",
    )
    artifacts = [
        "dataset.yaml",
        *(sample[key] for sample in samples for key in ("image", "label", "truth")),
    ]
    _write(
        root / "dataset-manifest.json",
        json.dumps(
            {
                "schema_version": 1,
                "generator_commit": "c" * 40,
                "mjcf_sha256": "d" * 64,
                "camera_name": "task_camera",
                "image_width": 640,
                "image_height": 480,
                "sample_count": 3,
                "split_counts": {"test": 1, "train": 1, "val": 1},
                "seed_starts": {"test": 300, "train": 100, "val": 200},
                "seed_ranges": {"test": [300, 300], "train": [100, 100], "val": [200, 200]},
                "class_instance_totals": {"plastic_cup": 3},
                "samples": samples,
                "artifacts": sorted(artifacts),
            }
        ),
    )
    return root


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_polygon_to_box_supports_normalized_and_absolute_boundary_boxes() -> None:
    box = polygon_to_box(((0.0, 0.0), (1.0, 0.0), (1.0, 0.5), (0.0, 0.5)), 640, 480)

    assert box.normalized_xyxy == (0.0, 0.0, 1.0, 0.5)
    assert box.absolute_xyxy == (0.0, 0.0, 640.0, 240.0)


@pytest.mark.parametrize(
    "polygon",
    (
        (),
        ((0.1, 0.2), (0.1, 0.4), (0.1, 0.6)),
        ((0.1, 0.2), (0.4, 0.2), (1.1, 0.6)),
        ((0.1, 0.2), (0.4, float("nan")), (0.4, 0.6)),
    ),
)
def test_polygon_to_box_rejects_empty_degenerate_or_invalid_polygons(polygon) -> None:
    with pytest.raises(GroundingDinoDatasetError, match="POLYGON_INVALID"):
        polygon_to_box(polygon, 640, 480)


def test_conversion_normalizes_multiple_instances_and_preserves_provenance(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path / "source")
    output = tmp_path / "output"

    result = convert_dataset(
        source,
        output,
        source_archive_sha256=ARCHIVE_SHA,
        converter_commit=CONVERTER_COMMIT,
    )

    train = _json(output / "train/inventory.json")
    assert train["class_name"] == "cup"
    assert train["prompt"] == "cup."
    assert train["source_archive_sha256"] == ARCHIVE_SHA
    assert train["converter_commit"] == CONVERTER_COMMIT
    assert len(train["samples"][0]["boxes"]) == 2
    assert train["samples"][0]["boxes"][1]["normalized_xyxy"] == [0.6, 0.1, 1.0, 0.4]
    assert train["samples"][0]["boxes"][1]["absolute_xyxy"] == [384.0, 48.0, 640.0, 192.0]
    assert {item["class_name"] for item in train["samples"][0]["boxes"]} == {"cup"}
    assert {item["text"] for item in train["samples"][0]["boxes"]} == {"cup."}
    for name in ("image_sha256", "label_sha256", "truth_sha256"):
        assert len(train["samples"][0][name]) == 64
    assert (
        result["train_inventory_sha256"]
        == hashlib.sha256((output / "train/inventory.json").read_bytes()).hexdigest()
    )


def test_conversion_keeps_test_annotations_sealed_and_members_disjoint(tmp_path: Path) -> None:
    source = _source(tmp_path / "source")
    output = tmp_path / "output"

    convert_dataset(
        source,
        output,
        source_archive_sha256=ARCHIVE_SHA,
        converter_commit=CONVERTER_COMMIT,
    )

    seal = _json(output / "test-sealed-members.json")
    assert seal["sealed"] is True
    assert seal["split"] == "test"
    assert "boxes" not in json.dumps(seal)
    assert "scenario" not in json.dumps(seal)
    train = _json(output / "train/inventory.json")
    val = _json(output / "val/inventory.json")
    member_sets = [
        {sample["image_relpath"] for sample in inventory["samples"]} for inventory in (train, val)
    ] + [{sample["image_relpath"] for sample in seal["samples"]}]
    assert not (member_sets[0] & member_sets[1])
    assert not (member_sets[0] & member_sets[2])
    assert not (member_sets[1] & member_sets[2])
    profile = _json(output / "dataset-profile.json")
    assert profile["test"] == {"sample_count": 1, "sealed": True}
    assert profile["train"]["lighting"] == "unknown"
    assert profile["train"]["background"] == "unknown"
    assert profile["train"]["partial_occlusion"] == "unknown"


def test_conversion_is_deterministic_and_refuses_existing_output(tmp_path: Path) -> None:
    source = _source(tmp_path / "source")
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_result = convert_dataset(
        source, first, source_archive_sha256=ARCHIVE_SHA, converter_commit=CONVERTER_COMMIT
    )
    second_result = convert_dataset(
        source, second, source_archive_sha256=ARCHIVE_SHA, converter_commit=CONVERTER_COMMIT
    )

    assert first_result == second_result
    assert {
        path.relative_to(first): path.read_bytes() for path in first.rglob("*") if path.is_file()
    } == {
        path.relative_to(second): path.read_bytes() for path in second.rglob("*") if path.is_file()
    }
    with pytest.raises(GroundingDinoDatasetError, match="OUTPUT_ROOT_ALREADY_EXISTS"):
        convert_dataset(
            source,
            first,
            source_archive_sha256=ARCHIVE_SHA,
            converter_commit=CONVERTER_COMMIT,
        )


def test_conversion_rejects_split_member_overlap(tmp_path: Path) -> None:
    source = _source(tmp_path / "source")
    manifest_path = source / "dataset-manifest.json"
    manifest = _json(manifest_path)
    manifest["samples"][2]["image"] = manifest["samples"][0]["image"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(GroundingDinoDatasetError, match="SPLIT_MEMBERS_OVERLAP"):
        convert_dataset(
            source,
            tmp_path / "output",
            source_archive_sha256=ARCHIVE_SHA,
            converter_commit=CONVERTER_COMMIT,
        )


def test_cli_reports_deterministic_inventory_hashes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _source(tmp_path / "source")
    output = tmp_path / "output"

    exit_code = main(
        [
            "--source-root",
            str(source),
            "--output-root",
            str(output),
            "--source-archive-sha256",
            ARCHIVE_SHA,
            "--converter-commit",
            CONVERTER_COMMIT,
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert report["status"] == "OK"
    assert (
        report["train_inventory_sha256"]
        == hashlib.sha256((output / "train/inventory.json").read_bytes()).hexdigest()
    )
