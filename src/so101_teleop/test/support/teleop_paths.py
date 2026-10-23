"""Filesystem anchors for the ``so101_teleop`` test suite.

The module name differs from the demo package's ``paths`` because a few tests put both packages'
support directories on ``sys.path`` in one process. ``PACKAGE_ROOT`` is the package source directory,
``SOURCE_ROOT`` is the ``src`` directory that holds every package, and ``REPOSITORY`` is the
repository (or worktree) root.
"""

from pathlib import Path

SUPPORT_DIR = Path(__file__).resolve().parent
TEST_ROOT = SUPPORT_DIR.parent
PACKAGE_ROOT = TEST_ROOT.parent
SOURCE_ROOT = PACKAGE_ROOT.parent
REPOSITORY = SOURCE_ROOT.parent


def _directories_with_tests(root: Path) -> tuple[Path, ...]:
    holders = {path.parent for path in root.rglob("test_*.py")}
    return tuple(sorted(holders | {root}, key=lambda directory: directory.as_posix()))


#: Test modules import each other's fixtures by bare module name (basenames are unique in the package), so every
#: directory that holds a test module is importable; ``conftest.py`` puts them on ``sys.path``.
TEST_DIRECTORIES = _directories_with_tests(TEST_ROOT)

#: The demo package's shared fixtures live in its test directories and its helpers in ``test/support``.
DEMO_TEST_ROOT = SOURCE_ROOT / "so101_demo_py" / "test"
DEMO_TEST_IMPORT_PATH = (DEMO_TEST_ROOT / "support", *_directories_with_tests(DEMO_TEST_ROOT))
