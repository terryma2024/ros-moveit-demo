"""Filesystem anchors for the ``so101_demo_py`` test suite.

Tests import these constants instead of counting ``Path(__file__).parents[N]``, so a test file can move
between directories without changing which tree it reads. ``PACKAGE_ROOT`` is the package source
directory, ``SOURCE_ROOT`` is the ``src`` directory that holds every package, and ``REPOSITORY`` is the
repository (or worktree) root.
"""

from pathlib import Path

SUPPORT_DIR = Path(__file__).resolve().parent
TEST_ROOT = SUPPORT_DIR.parent
PACKAGE_ROOT = TEST_ROOT.parent
SOURCE_ROOT = PACKAGE_ROOT.parent
REPOSITORY = SOURCE_ROOT.parent


def _test_directories() -> tuple[Path, ...]:
    """Every directory below ``test`` that holds a test module, plus ``test`` itself, in a stable order."""

    holders = {path.parent for path in TEST_ROOT.rglob("test_*.py")}
    return tuple(sorted(holders | {TEST_ROOT}, key=lambda directory: directory.as_posix()))


#: Test modules import each other's fixtures by bare module name (basenames are unique in the package), so every
#: directory that holds a test module is importable. ``conftest.py`` puts them on ``sys.path``; a test that starts a
#: child interpreter passes ``TEST_IMPORT_PATH`` as its ``PYTHONPATH``/``sys.path`` prefix.
TEST_DIRECTORIES = _test_directories()
TEST_IMPORT_PATH = (SUPPORT_DIR, *TEST_DIRECTORIES)
