"""Deprecated MuJoCo command forwarders."""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Sequence

from so101_demo.backends.mujoco.qualified_phases import scene_setup
from so101_demo.cli import pick_place, qualification


def _warn() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("always", DeprecationWarning)
        warnings.warn(
            "so101_mujoco_demo_py is deprecated; use so101_demo_py",
            DeprecationWarning,
            stacklevel=2,
        )


def map_legacy_args(arguments: Sequence[str] | None) -> list[str]:
    mapped = list(sys.argv[1:] if arguments is None else arguments)
    if any(argument == "--backend" or argument.startswith("--backend=") for argument in mapped):
        raise SystemExit("cannot map legacy argument --backend")
    return ["--backend", "mujoco", *mapped]


def main(arguments: Sequence[str] | None = None) -> int:
    _warn()
    return pick_place.main(map_legacy_args(arguments))


def qualification_main() -> int:
    _warn()
    return qualification.main()


def scene_setup_main() -> int:
    _warn()
    return scene_setup.main()


def unsupported_main() -> int:
    _warn()
    command = Path(sys.argv[0]).name
    raise SystemExit(f"legacy command {command} has no equivalent so101_demo_py entry point")
