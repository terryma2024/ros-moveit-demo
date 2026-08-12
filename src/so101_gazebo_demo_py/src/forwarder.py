"""Deprecated Gazebo command forwarders."""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Sequence

from so101_demo.cli import pick_place


_UNMAPPABLE = (
    "--backend",
    "--live-runtime",
    "--object-config",
    "--planning-diagnostics-dir",
    "--validation-policy",
)


def _warn() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("always", DeprecationWarning)
        warnings.warn(
            "so101_gazebo_demo_py is deprecated; use so101_demo_py",
            DeprecationWarning,
            stacklevel=2,
        )


def map_legacy_args(arguments: Sequence[str] | None) -> list[str]:
    mapped = list(sys.argv[1:] if arguments is None else arguments)
    for option in _UNMAPPABLE:
        if any(argument == option or argument.startswith(f"{option}=") for argument in mapped):
            raise SystemExit(f"cannot map legacy argument {option}")
    return ["--backend", "gazebo", *mapped]


def main(arguments: Sequence[str] | None = None) -> int:
    _warn()
    return pick_place.main(map_legacy_args(arguments))


def unsupported_main() -> int:
    _warn()
    command = Path(sys.argv[0]).name
    raise SystemExit(f"legacy command {command} has no equivalent so101_demo_py entry point")
