"""Named V1 fixed-waypoint entry point."""

from __future__ import annotations

from .pick_place import main as _fixed_main


def main(arguments: list[str] | None = None) -> int:
    return _fixed_main(arguments, prog="fixed_cup_pick_place")


if __name__ == "__main__":
    raise SystemExit(main())
