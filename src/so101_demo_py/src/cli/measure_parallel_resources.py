"""Retired: the certified per-N resource measurement entry point.

The lightweight start guard design (2026-09-19) removed the per-N budget chain: the
measurement runtime, its sealed authorizations, its qualification/approval documents and the
authority environment are gone. The console script stays registered so that an operator who
still has the old command gets an explicit retirement error instead of silently running a
different mode.
"""

from __future__ import annotations

import json
import sys

RETIREMENT_MESSAGE = "MEASUREMENT_ENTRY_RETIRED"

RETIREMENT_DETAIL = (
    "the per-N certified measurement runtime was removed by the lightweight start guard "
    "design; use `so101_parallel_batch` for real execution, and history.load_history for "
    "read-only inspection of retained measurement evidence"
)


def retired_document() -> dict:
    return {
        "error": RETIREMENT_MESSAGE,
        "detail": RETIREMENT_DETAIL,
        "readonly": True,
        "authorizes_execution": False,
        "replacement": "so101_parallel_batch",
    }


def main(argv=None) -> int:
    """Report retirement on stdout and exit 2. Never measures, never authorizes."""

    print(json.dumps(retired_document(), sort_keys=True))
    return 2


if __name__ == "__main__":  # pragma: no cover - exercised through the console script
    sys.exit(main())
