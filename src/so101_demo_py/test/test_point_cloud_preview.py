from pathlib import Path

import numpy as np
import pytest


def _cloud() -> tuple[np.ndarray, np.ndarray]:
    values = np.linspace(-0.1, 0.1, 30)
    points = np.column_stack((values, np.sin(values * 20.0) * 0.04, values * 0.5))
    colors = np.column_stack(
        (
            np.linspace(0.2, 1.0, len(points)),
            np.linspace(1.0, 0.2, len(points)),
            np.full(len(points), 0.25),
        )
    )
    return points, colors


def test_preview_is_deterministic_png_with_documented_view(tmp_path: Path) -> None:
    from so101_demo.runtime.point_cloud_preview import render_point_cloud_preview

    points, colors = _cloud()
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"

    first_metadata = render_point_cloud_preview(points, colors, first)
    second_metadata = render_point_cloud_preview(points, colors, second)

    assert first.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert first.read_bytes() == second.read_bytes()
    assert first_metadata == second_metadata
    assert first_metadata["projection"] == "perspective"
    assert first_metadata["z_buffer"] is True


def test_preview_rejects_invalid_or_empty_cloud(tmp_path: Path) -> None:
    from so101_demo.runtime.point_cloud_preview import render_point_cloud_preview

    with pytest.raises(ValueError, match="non-empty"):
        render_point_cloud_preview(
            np.empty((0, 3)), np.empty((0, 3)), tmp_path / "empty.png"
        )
    with pytest.raises(ValueError, match="finite"):
        render_point_cloud_preview(
            np.array([[0.0, np.nan, 0.0]]),
            np.ones((1, 3)),
            tmp_path / "nan.png",
        )
