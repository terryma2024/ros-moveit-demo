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
