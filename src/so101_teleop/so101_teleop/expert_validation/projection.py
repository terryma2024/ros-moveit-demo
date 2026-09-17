"""Pure world-to-SVG projection and marker-style contracts."""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
from typing import Mapping, Sequence


DEFAULT_PADDING_PX = 48.0
MARKER_RADIUS_PX = 10.0


@dataclass(frozen=True, slots=True)
class Projection:
    width_px: int
    height_px: int
    bounds_m: tuple[float, float, float, float]
    pixels_per_m: float
    offset_x_px: float
    offset_y_px: float

    @property
    def pixels_per_m_x(self) -> float:
        return self.pixels_per_m

    @property
    def pixels_per_m_y(self) -> float:
        return self.pixels_per_m

    @classmethod
    def from_geometry(
        cls,
        geometry: Mapping[str, object],
        width_px: int,
        height_px: int,
        *,
        padding_px: float = DEFAULT_PADDING_PX,
    ) -> Projection:
        if (
            isinstance(width_px, bool)
            or isinstance(height_px, bool)
            or not isinstance(width_px, int)
            or not isinstance(height_px, int)
            or width_px <= 0
            or height_px <= 0
        ):
            raise ValueError("PROJECTION_SIZE")
        raw_bounds = geometry.get("table_bounds")
        if (
            not isinstance(raw_bounds, Sequence)
            or isinstance(raw_bounds, (str, bytes))
            or len(raw_bounds) != 4
            or any(
                isinstance(value, bool)
                or not isinstance(value, Real)
                or not math.isfinite(float(value))
                for value in raw_bounds
            )
        ):
            raise ValueError("PROJECTION_GEOMETRY")
        xmin, xmax, ymin, ymax = (float(value) for value in raw_bounds)
        if xmin >= xmax or ymin >= ymax:
            raise ValueError("PROJECTION_GEOMETRY")
        if not math.isfinite(padding_px) or padding_px < 0:
            raise ValueError("PROJECTION_PADDING")
        available_width = width_px - 2.0 * padding_px
        available_height = height_px - 2.0 * padding_px
        if available_width <= 0 or available_height <= 0:
            raise ValueError("PROJECTION_PADDING")
        scale = min(
            available_width / (xmax - xmin),
            available_height / (ymax - ymin),
        )
        plot_width = (xmax - xmin) * scale
        plot_height = (ymax - ymin) * scale
        left = (width_px - plot_width) / 2.0
        top = (height_px - plot_height) / 2.0
        return cls(
            width_px=width_px,
            height_px=height_px,
            bounds_m=(xmin, xmax, ymin, ymax),
            pixels_per_m=scale,
            offset_x_px=left - xmin * scale,
            offset_y_px=top + ymax * scale,
        )


def project_xy(value: Projection, x_m: float, y_m: float) -> tuple[float, float]:
    if not all(
        isinstance(coordinate, Real)
        and not isinstance(coordinate, bool)
        and math.isfinite(float(coordinate))
        for coordinate in (x_m, y_m)
    ):
        raise ValueError("PROJECTION_COORDINATE")
    return (
        value.offset_x_px + float(x_m) * value.pixels_per_m,
        value.offset_y_px - float(y_m) * value.pixels_per_m,
    )


@dataclass(frozen=True, slots=True)
class MarkerStyle:
    semantic_color: str
    stroke: str
    fill: str
    icon: str
    radius_px: float = MARKER_RADIUS_PX


_STYLE_BY_COLOR = {
    "blue": MarkerStyle("blue", "#1976d2", "#e3f2fd", "pending"),
    "green": MarkerStyle("green", "#2e7d32", "#e8f5e9", "passed"),
    "red": MarkerStyle("red", "#d32f2f", "#fde8e8", "failed"),
}
_COLOR_BY_STATE = {
    "ELIGIBLE_UNRUN": "blue",
    "LEASED": "blue",
    "EXECUTING": "blue",
    "INFRA_INTERRUPTED_REQUEUEABLE": "blue",
    "PASSED": "green",
    "FAILED": "red",
    "INDETERMINATE": "red",
    "TERMINAL_UNRUN": "red",
    "INVALID_BLOCKED": "red",
    "INFRA_FAILED_REMAINDER": "red",
}


def marker_style(status: str) -> MarkerStyle:
    try:
        return _STYLE_BY_COLOR[_COLOR_BY_STATE[status]]
    except (KeyError, TypeError) as error:
        raise ValueError("UNKNOWN_MARKER_STATUS") from error
