"""Task 8P3: the compatibility import paths carry no second implementation."""

from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
ALIASES = ("act_prepare_task8_live.py", "act_task8_live.py", "act_prepare_task8_live_artifacts.py")


def test_the_aliases_are_thin_forwards_to_the_canonical_modules():
    for name in ALIASES:
        source = (PACKAGE / "src/cli" / name).read_text()
        assert "sys.modules[__name__] = importlib.import_module(" in source, name
        # a shim that grew logic would be the second implementation the plan forbids
        assert len(source.splitlines()) <= 10, name


def test_importing_an_alias_yields_the_canonical_module():
    import importlib
    import sys

    sys.path.insert(0, str(PACKAGE / "src"))
    for alias, canonical in (("so101_demo.cli.act_prepare_task8_live_artifacts",
                              "so101_demo.cli.act_prepare_pick_place_validation"),
                             ("so101_demo.cli.act_prepare_task8_live",
                              "so101_demo.cli.act_prepare_pick_place_validation")):
        module = importlib.import_module(alias)
        target = importlib.import_module(canonical)
        assert module is target, alias
        assert callable(getattr(module, "main", None)), alias


def test_the_setup_entries_point_at_the_aliases_and_the_canonical_paths():
    setup = (PACKAGE / "setup.py").read_text()
    for entry in ("act_prepare_pick_place_validation", "act_prepare_task8_live",
                  "act_prepare_task8_live_artifacts", "act_run_pick_place_validation"):
        assert f'"{entry} = ' in setup, entry
