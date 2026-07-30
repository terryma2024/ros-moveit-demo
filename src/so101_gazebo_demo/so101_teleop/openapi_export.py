"""Deterministically export the public Teleop OpenAPI contract."""

from __future__ import annotations

import json
from pathlib import Path
import sys

from .api import create_app


class _SchemaOnlyService:
    """The route table does not call this service while exporting schema."""


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


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python3 -m so101_teleop.openapi_export OUTPUT")
    export_openapi(sys.argv[1])


if __name__ == "__main__":
    main()
