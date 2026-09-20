"""Deterministically export the unified OpenAPI contract and its filtered views.

There is exactly one route table: the unified app. The former Teleop and Validation
documents are filtered projections of that same schema, so no second, hand-maintained copy
of the routes can drift. Every view keeps the original component references intact.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

from .unified.app import create_unified_app, schema_services

TELEOP_TITLE = "SO-101 Teleop"
VALIDATION_TITLE = "SO-101 Expert Validation"
UNIFIED_TITLE = "SO-101 Unified"

#: Paths that only exist because the two services are now one, and therefore are absent
#: from the compatibility Teleop view.
UNIFIED_ONLY_PATHS = frozenset(
    {
        "/health/live",
        "/health/ready",
        "/plans/{plan_id}/execute-all",
        "/control/instances",
        "/control/instances/handoff",
        "/control/instances/{instance_id}/channel",
    }
)

VALIDATION_PREFIXES = ("/expert-validation", "/tasks", "/health")


def unified_schema() -> dict:
    app = create_unified_app(
        schema_services(), static_dir=None, capture_dir=None, bind_address="127.0.0.1"
    )
    return app.openapi()


def _write(destination: str | Path, schema: dict) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return path


def _with_title(schema: dict, title: str) -> dict:
    document = dict(schema)
    document["info"] = dict(schema.get("info", {}), title=title)
    return document


def _filter_paths(schema: dict, keep) -> dict:
    document = dict(schema)
    document["paths"] = {path: item for path, item in schema["paths"].items() if keep(path)}
    return document


def export_unified_openapi(output: str | Path) -> Path:
    """The aggregate document covering the real, single route table."""
    return _write(output, _with_title(unified_schema(), UNIFIED_TITLE))


def export_openapi(output: str | Path) -> Path:
    """Compatibility Teleop view: the same schema without the validation and unified paths."""

    def keep(path: str) -> bool:
        if path in UNIFIED_ONLY_PATHS:
            return False
        if path.startswith("/expert-validation"):
            return False
        return not path.startswith("/control/instances")

    return _write(output, _with_title(_filter_paths(unified_schema(), keep), TELEOP_TITLE))


def export_validation_openapi(output: str | Path) -> Path:
    """Compatibility Validation view: its own paths plus the shared Tasks contract."""

    def keep(path: str) -> bool:
        if path in UNIFIED_ONLY_PATHS:
            return False
        return path.startswith(VALIDATION_PREFIXES)

    return _write(output, _with_title(_filter_paths(unified_schema(), keep), VALIDATION_TITLE))


def main() -> None:
    if len(sys.argv) == 2:
        export_openapi(sys.argv[1])
        return
    if len(sys.argv) == 3 and sys.argv[1] == "--validation":
        export_validation_openapi(sys.argv[2])
        return
    if len(sys.argv) == 3 and sys.argv[1] == "--unified":
        export_unified_openapi(sys.argv[2])
        return
    raise SystemExit(
        "usage: python3 -m so101_teleop.openapi_export [--validation|--unified] OUTPUT"
    )


if __name__ == "__main__":
    main()
