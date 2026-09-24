"""CTest registration covers exactly the ordinary pytest modules of this package.

``colcon test`` reaches this package's ordinary suite through the ``so101_add_pytest_test``
registrations, not by walking ``test/``: a module nobody registers is a module the package gate
never runs, and a registration whose file is gone makes the gate fail on a missing path. This
contract compares the two sets instead of trusting either one, and it proves the comparison can
fail by deleting a registration from a ``tmp_path`` copy. The worktree ``CMakeLists.txt`` is only
ever read.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CMAKE_LISTS = PACKAGE_ROOT / "CMakeLists.txt"

_REGISTRATION = re.compile(
    r"so101_add_pytest_test\(\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s+(?P<path>test/[^\s()]+\.py)\s*\)"
)
_TEST_FUNCTION = re.compile(r"^\s*(?:async\s+)?def test_", re.MULTILINE)


class RegistrationGaps(NamedTuple):
    """How the registered set differs from the ordinary modules that really carry tests."""

    unregistered: tuple[str, ...]
    unknown_paths: tuple[str, ...]
    duplicate_names: tuple[str, ...]
    duplicate_paths: tuple[str, ...]


def registered_tests(cmake_text: str) -> tuple[tuple[str, str], ...]:
    """Every ``so101_add_pytest_test(<name> test/<...>.py)`` pair, in source order."""

    return tuple(
        (match.group("name"), match.group("path")) for match in _REGISTRATION.finditer(cmake_text)
    )


def ordinary_modules(test_root: Path) -> tuple[str, ...]:
    """Every ``test/**/test_*.py`` that really carries a test, package-relative and sorted.

    A helper module that only lends fixtures or constants to its neighbours - ``test_support.py``
    is the one here - is not a CTest case and is therefore not part of the registered set.
    """

    modules = []
    for path in sorted(test_root.rglob("test_*.py")):
        if not _TEST_FUNCTION.search(path.read_text(encoding="utf-8")):
            continue
        modules.append(path.relative_to(PACKAGE_ROOT).as_posix())
    return tuple(modules)


def registration_gaps(cmake_text: str, *, package_root: Path = PACKAGE_ROOT) -> RegistrationGaps:
    pairs = registered_tests(cmake_text)
    names = [name for name, _ in pairs]
    paths = [path for _, path in pairs]
    registered = set(paths)
    modules = set(ordinary_modules(package_root / "test"))
    return RegistrationGaps(
        unregistered=tuple(sorted(modules - registered)),
        unknown_paths=tuple(sorted(registered - modules)),
        duplicate_names=tuple(sorted({name for name in names if names.count(name) > 1})),
        duplicate_paths=tuple(sorted({path for path in paths if paths.count(path) > 1})),
    )


def test_registration_matches_the_ordinary_test_modules() -> None:
    """One module, one registration: nothing the gate would skip, nothing it would trip over."""

    gaps = registration_gaps(CMAKE_LISTS.read_text(encoding="utf-8"))

    assert gaps.unregistered == (), f"modules the package gate would never run: {gaps.unregistered}"
    assert gaps.unknown_paths == (), f"registrations naming no test module: {gaps.unknown_paths}"


def test_every_registration_is_unique() -> None:
    """A repeated name overwrites a CTest case; a repeated path runs the same module twice."""

    gaps = registration_gaps(CMAKE_LISTS.read_text(encoding="utf-8"))

    assert gaps.duplicate_names == (), f"duplicate CTest names: {gaps.duplicate_names}"
    assert gaps.duplicate_paths == (), f"modules registered twice: {gaps.duplicate_paths}"


def test_the_checker_reports_a_registration_removed_from_a_tmp_path_copy(tmp_path: Path) -> None:
    """The control: the same comparison must fail when a registration is gone."""

    cmake_text = CMAKE_LISTS.read_text(encoding="utf-8")
    pairs = registered_tests(cmake_text)
    assert pairs, "the CMake source registers no pytest module at all"
    name, path = pairs[-1]
    line = re.search(
        rf"^.*so101_add_pytest_test\(\s*{name}\s+{re.escape(path)}\s*\).*$\n?", cmake_text,
        re.MULTILINE,
    )
    assert line is not None, (name, path)
    copy = tmp_path / "CMakeLists.txt"
    copy.write_text(cmake_text[: line.start()] + cmake_text[line.end() :], encoding="utf-8")

    gaps = registration_gaps(copy.read_text(encoding="utf-8"))

    assert path in gaps.unregistered, gaps
    assert name not in {registered for registered, _ in registered_tests(copy.read_text())}
