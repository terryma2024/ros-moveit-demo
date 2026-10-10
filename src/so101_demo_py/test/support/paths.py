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
