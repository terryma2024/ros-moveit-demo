from __future__ import annotations

import hashlib
import math
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from so101_teleop.expert_validation.catalog import (
    CatalogError,
    _parse_catalog_bytes,
    load_baseline_catalog,
    select_catalog_points,
    selection_sha256,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CATALOG_PATH = (
    REPOSITORY_ROOT
    / "src/so101_demo_py/config/mujoco/moveit_expert_validation_points_v1.yaml"
)
CATALOG_SHA256 = "c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5"


def _swap_first_two_points(document: dict[str, object]) -> None:
    points = document["points"]
    assert isinstance(points, list)
    points[0], points[1] = points[1], points[0]


@pytest.fixture(autouse=True)
def source_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "so101_teleop.expert_validation.catalog._catalog_path",
        lambda: CATALOG_PATH,
    )


def test_baseline_catalog_is_shared_with_parallel_runtime() -> None:
    points = load_baseline_catalog()

    assert [point.id for point in points[:4]] == [
        "task_start",
        "cup_test_forward_5cm",
        "cup_test_left_5cm",
        "cup_test_right_5cm",
    ]
    assert points[4].position_world_m == (-0.020732, -0.249568, 0.165)
    assert points[-1].id == "sample_16_far_right"
    assert points[-1].position_world_m == (0.071574, -0.319255, 0.165)


def test_selection_is_stable_and_uses_only_catalog_ids() -> None:
    selection = select_catalog_points(total_points=9)

    assert [point.id for point in selection.points] == [
        "task_start",
        "cup_test_forward_5cm",
        "cup_test_left_5cm",
        "cup_test_right_5cm",
        "sample_01_near_left",
        "sample_02_near_center",
        "sample_06_mid_left",
        "sample_07_mid_center",
        "sample_08_mid_right",
    ]
    assert [point.display_id for point in selection.points] == [
        f"P{index:02d}" for index in range(1, 10)
    ]
    assert selection.catalog_seed == 20260911
    assert selection.catalog_sha256 == CATALOG_SHA256
    assert selection.selection_sha256 == selection_sha256(
        [point.id for point in selection.points]
    )


@pytest.mark.parametrize("total_points", [3, 21, True])
def test_selection_rejects_counts_outside_v1_contract(total_points: object) -> None:
    with pytest.raises(CatalogError, match="TOTAL_POINTS_RANGE"):
        select_catalog_points(total_points=total_points)  # type: ignore[arg-type]


def test_catalog_rejects_byte_hash_drift() -> None:
    raw = CATALOG_PATH.read_bytes() + b"\n"

    with pytest.raises(CatalogError, match="POINT_CATALOG_HASH_MISMATCH"):
        _parse_catalog_bytes(raw, expected_sha256=CATALOG_SHA256)


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda document: document["points"][1].update(id="task_start"), "POINT_CATALOG_DUPLICATE"),
        (
            lambda document: document["points"][4]["cup_position_world_m"].__setitem__(
                0, math.inf
            ),
            "POINT_CATALOG_COORDINATE",
        ),
        (
            _swap_first_two_points,
            "POINT_CATALOG_ANCHORS",
        ),
    ],
)
def test_catalog_rejects_invalid_runtime_documents(mutate, reason: str) -> None:
    document = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    mutate(document)
    raw = yaml.safe_dump(document, sort_keys=False).encode("utf-8")

    with pytest.raises(CatalogError, match=reason):
        _parse_catalog_bytes(raw, expected_sha256=hashlib.sha256(raw).hexdigest())


def test_twenty_point_fixture_preserves_exact_minimum_spacing() -> None:
    selection = select_catalog_points(total_points=20)
    minimum = min(
        math.dist(a.position_world_m[:2], b.position_world_m[:2])
        for index, a in enumerate(selection.points)
        for b in selection.points[index + 1 :]
    )

    assert minimum == pytest.approx(0.015116191120781703)
    assert len({point.id for point in selection.points}) == 20


def test_top_view_script_consumes_baseline_selection(tmp_path: Path) -> None:
    result = subprocess.run(
        (
            sys.executable,
            str(REPOSITORY_ROOT / "scripts/generate_so101_moveit_expert_position_top_view.py"),
            "--repository-root",
            str(REPOSITORY_ROOT),
            "--catalog-profile",
            "ai_station_baseline_v1",
            "--total-points",
            "9",
            "--output-dir",
            str(tmp_path),
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    document = yaml.safe_load(
        (tmp_path / "so101-position-manifest.yaml").read_text(encoding="utf-8")
    )
    assert [point["id"] for point in document["points"]] == [
        "task_start",
        "cup_test_forward_5cm",
        "cup_test_left_5cm",
        "cup_test_right_5cm",
        "sample_01_near_left",
        "sample_02_near_center",
        "sample_06_mid_left",
        "sample_07_mid_center",
        "sample_08_mid_right",
    ]
