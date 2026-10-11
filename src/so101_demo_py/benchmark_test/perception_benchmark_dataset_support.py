"""Archive builders and helpers shared by the benchmark dataset tests."""

from __future__ import annotations

import hashlib
from io import BytesIO
import json
from pathlib import Path
import tarfile
from typing import Callable

import PIL
from PIL import Image
import pytest

from so101_demo.perception_benchmark.dataset import contracts as dataset_module_contracts
from so101_demo.perception_benchmark.dataset import loading as dataset_module_loading
from so101_demo.perception_benchmark.dataset import truth as dataset_module_truth
from so101_demo.perception_benchmark.dataset import verifier as dataset_module_verifier
from so101_demo.perception_benchmark.dataset.contracts import TestSeal as DatasetTestSeal
from so101_demo.perception_benchmark.dataset.contracts import sha256_file
from so101_demo.perception_benchmark.dataset.verifier import DatasetArchiveVerifier

SCENARIOS = (
    "no_cup",
    "one_cup_distractors",
    "two_cups",
    "cup_near_bottle",
)


_POLYGON = ((0.25, 0.25), (0.75, 0.25), (0.5, 0.75))


_INSTALLED_PILLOW = PIL.__version__


_PINNED_PILLOW = dataset_module_contracts._RASTERIZER["version"]


@pytest.fixture(autouse=True)
def _skip_what_needs_the_pinned_rasterizer(monkeypatch: pytest.MonkeyPatch) -> None:
    """The truth masks are rasterized with a Pillow whose output is part of the dataset contract (`_RASTERIZER`, pinned in the
    perception lock files). With any other Pillow installed the rasterizer refuses (RASTERIZER_VERSION_MISMATCH) by design, so a test
    that reaches it cannot run: it is skipped, with the reason, instead of failing on the environment. Everything that does not
    rasterize still runs, a test that patches the version to exercise the refusal still sees the real check, and with the pinned
    Pillow nothing is skipped (install it with `uv pip install pillow==<pin>` into the interpreter that runs the gate)."""
    if _INSTALLED_PILLOW == _PINNED_PILLOW:
        return
    real = dataset_module_truth._require_rasterizer_version

    def checked() -> None:
        if PIL.__version__ == _INSTALLED_PILLOW:
            pytest.skip(f"needs Pillow {_PINNED_PILLOW} (the dataset rasterizer pin); {_INSTALLED_PILLOW} is installed")
        real()

    monkeypatch.setattr(dataset_module_loading, "_require_rasterizer_version", checked)
    monkeypatch.setattr(dataset_module_verifier, "_require_rasterizer_version", checked)
    monkeypatch.setattr(dataset_module_truth, "_require_rasterizer_version", checked)


def _png_bytes(index: int, *, width: int = 640, height: int = 480) -> bytes:
    image = Image.new(
        "RGB",
        (width, height),
        ((index >> 16) & 255, (index >> 8) & 255, index & 255),
    )
    payload = BytesIO()
    image.save(payload, format="PNG")
    return payload.getvalue()


def _truth_and_label(index: int, scenario: str) -> tuple[bytes, bytes]:
    count = {
        "no_cup": 0,
        "one_cup_distractors": 1,
        "two_cups": 2,
        "cup_near_bottle": 1,
    }[scenario]
    instances = [
        {
            "body_id": instance_index + 1,
            "body_name": "plastic_cup" if instance_index == 0 else "plastic_cup_b",
            "visible_pixel_count": 3,
            "polygon_xy": [list(point) for point in _POLYGON],
        }
        for instance_index in range(count)
    ]
    truth = {
        "seed": 300000 + index,
        "split": "test",
        "scenario": scenario,
        "configured_cup_count": count,
        "visible_instance_count": count,
        "instances": instances,
    }
    label_line = "0 0.25 0.25 0.75 0.25 0.5 0.75\n"
    return (
        (json.dumps(truth, sort_keys=True, separators=(",", ":")) + "\n").encode(),
        (label_line * count).encode(),
    )


def _add_bytes(
    archive: tarfile.TarFile,
    name: str,
    payload: bytes,
    *,
    mtime: int = 1,
) -> None:
    member = tarfile.TarInfo(name)
    member.size = len(payload)
    member.mtime = mtime
    archive.addfile(member, BytesIO(payload))


def build_fixture_archive(
    tmp_path: Path,
    *,
    split_count: int = 200,
    include_val: bool = False,
    semantic_payloads: bool = True,
    image_size: tuple[int, int] = (640, 480),
    duplicate_image_sha: bool = False,
    scenario_for_index: Callable[[int], str] | None = None,
    label_mismatch: bool = False,
    payload_marker: bytes = b"",
    image_offset: int = 0,
    extra_member_payload: bytes | None = None,
) -> Path:
    archive_path = tmp_path / "fixture.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        splits = ("test", "val") if include_val else ("test",)
        for split in splits:
            for index in range(split_count):
                stem = f"{(300000 if split == 'test' else 200000) + index:09d}"
                prefix = "dataset"
                if not semantic_payloads:
                    image_payload = b"not-a-png" + payload_marker
                    truth_payload = b"not-json: scenario polygon truth_count" + payload_marker
                    label_payload = b"not-a-label" + payload_marker
                else:
                    image_index = 0 if duplicate_image_sha else index
                    image_payload = _png_bytes(
                        image_index + image_offset + (1000 if split == "val" else 0),
                        width=image_size[0],
                        height=image_size[1],
                    )
                    scenario = (
                        scenario_for_index(index)
                        if scenario_for_index is not None
                        else SCENARIOS[index % len(SCENARIOS)]
                    )
                    truth_payload, label_payload = _truth_and_label(index, scenario)
                    if split == "val":
                        document = json.loads(truth_payload)
                        document["seed"] = 200000 + index
                        document["split"] = "val"
                        truth_payload = (
                            json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
                        ).encode()
                    if label_mismatch and index == 0:
                        label_payload = b"0 0.1 0.1 0.2 0.1 0.15 0.2\n"
                _add_bytes(archive, f"{prefix}/images/{split}/{stem}.png", image_payload)
                _add_bytes(archive, f"{prefix}/labels/{split}/{stem}.txt", label_payload)
                _add_bytes(archive, f"{prefix}/truth/{split}/{stem}.json", truth_payload)
        if extra_member_payload is not None:
            _add_bytes(
                archive,
                "dataset/metadata/build.txt",
                extra_member_payload,
            )
    return archive_path


def _verified_unlocked_seal(
    archive: Path,
    tmp_path: Path,
    *,
    suffix: str = "",
) -> DatasetTestSeal:
    inventory = DatasetArchiveVerifier().verify_archive(
        archive,
        sha256_file(archive),
        tmp_path / f"sealed{suffix}.json",
    )
    return DatasetTestSeal(
        inventory.sealed_test_member_inventory_sha256,
        tmp_path / f"test-access{suffix}.jsonl",
    ).unlock(
        tmp_path / f"yolo-lock{suffix}.json",
        tmp_path / f"grounded-lock{suffix}.json",
        verify_lock=lambda path: "b" * 64 if path.name.startswith("yolo-lock") else "c" * 64,
    )


def _public_inventory_anchors(root: Path, split: str) -> dict[str, object]:
    payload = (root / "inventory.json").read_bytes()
    document = json.loads(payload)
    anchors: dict[str, object] = {
        "expected_split": split,
        "expected_archive_sha256": document["archive_sha256"],
        "expected_inventory_sha256": hashlib.sha256(payload).hexdigest(),
    }
    if split == "test":
        access = document["test_access"]
        anchors.update(
            {
                "expected_test_access_event_sha256": access["event_sha256"],
                "expected_sealed_member_inventory_sha256": access["sealed_member_inventory_sha256"],
                "expected_threshold_lock_sha256s": tuple(access["threshold_lock_sha256s"]),
            }
        )
    return anchors
