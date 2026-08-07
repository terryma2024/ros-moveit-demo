"""Private best-effort diagnostics for failed planning requests."""

import json
import os
from pathlib import Path
import time
from typing import Any, Mapping


class PlanningDiagnostics:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)

    def write_failure(self, code: str, data: Mapping[str, Any]) -> Path | None:
        try:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.directory, 0o700)
            path = self.directory / f"{time.time_ns()}-{code}.json"
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(data, stream, sort_keys=True, allow_nan=False)
                stream.write("\n")
            return path
        except (OSError, TypeError, ValueError):
            return None

    def write_success(self, data: Mapping[str, Any]) -> None:
        del data
        return None
