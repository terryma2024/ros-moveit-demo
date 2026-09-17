"""Deterministically export the public Teleop OpenAPI contract."""

from __future__ import annotations

import json
from pathlib import Path
import sys

from .api import create_app
from .expert_validation.api import create_expert_validation_app


class _SchemaOnlyService:
    """The route table does not call this service while exporting schema."""

    async def camera_presets(self):
        return {"presets": []}


class _ValidationSchemaOnlyService:
    artifacts = None


def export_openapi(output: str | Path) -> Path:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        create_app(_SchemaOnlyService()).openapi(),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"
    destination.write_text(payload)
    return destination


def export_validation_openapi(output: str | Path) -> Path:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        create_expert_validation_app(_ValidationSchemaOnlyService()).openapi(),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"
    destination.write_text(payload)
    return destination


def main() -> None:
    if len(sys.argv) == 2:
        export_openapi(sys.argv[1])
        return
    if len(sys.argv) == 3 and sys.argv[1] == "--validation":
        export_validation_openapi(sys.argv[2])
        return
    raise SystemExit(
        "usage: python3 -m so101_teleop.openapi_export [--validation] OUTPUT"
    )


if __name__ == "__main__":
    main()
