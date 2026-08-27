from pathlib import Path

import pytest
import yaml

from so101_demo.core.task_points import (
    TaskPointError,
    parse_task_point_list,
)
from so101_demo.runtime.task_point_config import (
    dump_task_point_list,
    load_task_point_list,
)


PACKAGE_ROOT = Path(__file__).parents[1]
PRESET_PATH = PACKAGE_ROOT / "config/mujoco/rgbd_task_points.yaml"
WORKSPACE_BOUNDS_M = (-0.30, -0.50, 0.10, 0.35, 0.20, 0.50)


def test_four_presets_and_custom_point_round_trip() -> None:
    points = load_task_point_list(PRESET_PATH, WORKSPACE_BOUNDS_M)
    custom = parse_task_point_list(
        {
            "schema_version": 1,
            "points": [
                {
                    "id": "custom_1",
                    "label": "Custom 1",
                    "cup_position_world_m": [0.01, -0.30, 0.165],
                }
            ],
        },
        WORKSPACE_BOUNDS_M,
    )

    restored = parse_task_point_list(
        yaml.safe_load(dump_task_point_list(custom)),
        WORKSPACE_BOUNDS_M,
    )

    assert [point.id for point in points.points] == [
        "task_start",
        "cup_test_forward_5cm",
        "cup_test_left_5cm",
        "cup_test_right_5cm",
    ]
    assert [point.cup_position_world_m for point in points.points] == [
        (0.02, -0.28, 0.165),
        (0.02, -0.33, 0.165),
        (-0.03, -0.28, 0.165),
        (0.07, -0.28, 0.165),
    ]
    assert restored == custom


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": 2, "points": []},
        {"schema_version": 1, "points": []},
        {
            "schema_version": 1,
            "points": [
                {
                    "id": "bad/id",
                    "label": "Bad",
                    "cup_position_world_m": [0.0, 0.0, 0.0],
                }
            ],
        },
        {
            "schema_version": 1,
            "points": [
                {
                    "id": "p",
                    "label": "P",
                    "cup_position_world_m": [float("nan"), 0.0, 0.0],
                }
            ],
        },
    ],
)
def test_invalid_point_lists_fail_closed(payload: object) -> None:
    with pytest.raises(TaskPointError):
        parse_task_point_list(payload, WORKSPACE_BOUNDS_M)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": 1, "points": [], "unexpected": True},
        {
            "schema_version": 1,
            "points": [
                {
                    "id": "p",
                    "label": "P",
                    "cup_position_world_m": [0.0, -0.2, 0.2],
                    "unexpected": True,
                }
            ],
        },
        {
            "schema_version": 1,
            "points": [
                {
                    "id": "p",
                    "label": "",
                    "cup_position_world_m": [0.0, -0.2, 0.2],
                }
            ],
        },
        {
            "schema_version": 1,
            "points": [
                {
                    "id": "p",
                    "label": "P",
                    "cup_position_world_m": [True, -0.2, 0.2],
                }
            ],
        },
        {
            "schema_version": 1,
            "points": [
                {
                    "id": "p",
                    "label": "P",
                    "cup_position_world_m": [0.36, -0.2, 0.2],
                }
            ],
        },
        {
            "schema_version": 1,
            "points": [
                {
                    "id": "duplicate",
                    "label": "One",
                    "cup_position_world_m": [0.0, -0.2, 0.2],
                },
                {
                    "id": "duplicate",
                    "label": "Two",
                    "cup_position_world_m": [0.01, -0.2, 0.2],
                },
            ],
        },
    ],
)
def test_point_schema_rejects_unknown_invalid_and_duplicate_values(payload: object) -> None:
    with pytest.raises(TaskPointError):
        parse_task_point_list(payload, WORKSPACE_BOUNDS_M)  # type: ignore[arg-type]


def test_load_wraps_yaml_and_filesystem_failures(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.yaml"
    malformed.write_text("points: [\n", encoding="utf-8")

    with pytest.raises(TaskPointError, match="TASK_POINT_YAML_INVALID"):
        load_task_point_list(malformed, WORKSPACE_BOUNDS_M)
    with pytest.raises(TaskPointError, match="TASK_POINT_READ_FAILED"):
        load_task_point_list(tmp_path / "missing.yaml", WORKSPACE_BOUNDS_M)


def test_workspace_bounds_must_be_finite_and_ordered() -> None:
    payload = {
        "schema_version": 1,
        "points": [
            {
                "id": "p",
                "label": "P",
                "cup_position_world_m": [0.0, -0.2, 0.2],
            }
        ],
    }

    with pytest.raises(TaskPointError, match="TASK_POINT_WORKSPACE_INVALID"):
        parse_task_point_list(payload, (0.0, 0.0, 0.0, 0.0, 1.0, 1.0))
    with pytest.raises(TaskPointError, match="TASK_POINT_WORKSPACE_INVALID"):
        parse_task_point_list(payload, (0.0, 0.0, 0.0, 1.0, float("inf"), 1.0))
