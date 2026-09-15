from __future__ import annotations

import json
from pathlib import Path

import pytest

from so101_teleop.expert_validation.projection import (
    Projection,
    marker_style,
    project_xy,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = (
    PACKAGE_ROOT / "config/expert_validation/top_view_projection_v1.json"
)


@pytest.fixture
def fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_projection_uses_equal_xy_scale_and_equal_marker_radius(fixture) -> None:
    projection = Projection.from_geometry(fixture["geometry"], 1200, 900)

    assert projection.pixels_per_m_x == projection.pixels_per_m_y == 1340.0
    assert project_xy(projection, 0.02, -0.28) == pytest.approx(
        tuple(fixture["p01_px"])
    )
    assert marker_style("PASSED").radius_px == marker_style("FAILED").radius_px


def test_every_catalog_point_matches_the_hand_checked_fixture(fixture) -> None:
    projection = Projection.from_geometry(fixture["geometry"], 1200, 900)

    for point in fixture["points"]:
        assert project_xy(projection, *point["position_world_m"][:2]) == pytest.approx(
            point["projected_px"]
        )


@pytest.mark.parametrize(
    ("state", "color", "icon"),
    [
        ("ELIGIBLE_UNRUN", "blue", "pending"),
        ("LEASED", "blue", "pending"),
        ("EXECUTING", "blue", "pending"),
        ("INFRA_INTERRUPTED_REQUEUEABLE", "blue", "pending"),
        ("PASSED", "green", "passed"),
        ("FAILED", "red", "failed"),
        ("INDETERMINATE", "red", "failed"),
        ("TERMINAL_UNRUN", "red", "failed"),
        ("INVALID_BLOCKED", "red", "failed"),
        ("INFRA_FAILED_REMAINDER", "red", "failed"),
    ],
)
def test_status_palette_is_fixed(state: str, color: str, icon: str) -> None:
    style = marker_style(state)

    assert style.semantic_color == color
    assert style.icon == icon
    assert style.radius_px == 10.0


def test_projection_rejects_non_finite_and_degenerate_geometry() -> None:
    with pytest.raises(ValueError, match="PROJECTION_GEOMETRY"):
        Projection.from_geometry(
            {"table_bounds": [0.0, 0.0, -0.5, 0.1]}, 1200, 900
        )
    with pytest.raises(ValueError, match="PROJECTION_SIZE"):
        Projection.from_geometry(
            {"table_bounds": [-0.25, 0.25, -0.5, 0.1]}, 0, 900
        )
