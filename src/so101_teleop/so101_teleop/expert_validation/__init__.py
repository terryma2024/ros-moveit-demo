"""Web-facing adapters for isolated expert-validation campaigns."""

from .catalog import (
    CatalogError,
    CatalogPoint,
    PointSelection,
    load_baseline_catalog,
    select_catalog_points,
    selection_sha256,
)
from .projection import MarkerStyle, Projection, marker_style, project_xy

__all__ = [
    "CatalogError",
    "CatalogPoint",
    "PointSelection",
    "load_baseline_catalog",
    "MarkerStyle",
    "marker_style",
    "Projection",
    "project_xy",
    "select_catalog_points",
    "selection_sha256",
]
