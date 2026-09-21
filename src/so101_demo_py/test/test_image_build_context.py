"""Contract: container images that install ``so101_demo_py`` must carry every file
its ``setup.py`` packages relative to the package directory.

``setup.py`` adds ``../../scripts/run_so101_adaptive_batch.zsh`` to ``data_files``.
Relative to the package directory inside an image (``/opt/so101_demo_py``) that path
resolves to ``/scripts/run_so101_adaptive_batch.zsh``. A Dockerfile that copies only
``src/so101_demo_py`` therefore fails while the wheel build copies data files, long
before the image can be used. The build context and the ``COPY`` instructions must
agree with ``setup.py``, so that contract is asserted here instead of being rediscovered
by a full image build.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path, PurePosixPath


REPOSITORY_ROOT = Path(__file__).parents[3]
PACKAGE_SOURCE = "src/so101_demo_py"
DOCKERFILES = sorted((REPOSITORY_ROOT / "src/so101_demo_py/docker").glob("*/Dockerfile"))

_COPY_PATTERN = re.compile(r"^\s*COPY\s+(?:--\S+\s+)*(\S+)\s+(\S+)\s*$")


def _normalize(path: PurePosixPath) -> PurePosixPath:
    parts: list[str] = []
    for part in path.parts:
        if part in ("", "/", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return PurePosixPath("/", *parts)


def _packaged_parent_paths() -> list[str]:
    """``data_files`` entries in ``setup.py`` that escape the package directory."""

    setup_py = (REPOSITORY_ROOT / "src/so101_demo_py/setup.py").read_text(encoding="utf-8")
    tree = ast.parse(setup_py)
    found = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("../")
    }
    assert found, "setup.py no longer packages any parent-relative file"
    return sorted(found)


def _context_path(relative: str) -> str:
    """Repository-relative path a ``COPY`` source must use for a packaged parent file."""

    resolved = _normalize(PurePosixPath(PACKAGE_SOURCE) / relative)
    return str(resolved).lstrip("/")


def _copy_instructions(dockerfile: Path) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        match = _COPY_PATTERN.match(line)
        if match:
            pairs.append((match.group(1), match.group(2)))
    return pairs


def _dockerignore_matches(pattern: str, path: str) -> bool:
    pattern = pattern.rstrip("/")
    if pattern in {"*", "**"}:
        return True
    if pattern.endswith("/**"):
        prefix = pattern[: -len("/**")]
        return path == prefix or path.startswith(prefix + "/")
    return path == pattern or path.startswith(pattern + "/")


def _context_included(relative: str, ignore_file: Path) -> bool:
    """Whether a repository-relative path survives the Dockerfile-specific ignore list."""

    if not ignore_file.is_file():
        return True
    included = True
    for raw in ignore_file.read_text(encoding="utf-8").splitlines():
        pattern = raw.strip()
        if not pattern or pattern.startswith("#"):
            continue
        if _dockerignore_matches(pattern.lstrip("!"), relative):
            included = pattern.startswith("!")
    return included


def _images_installing_the_package() -> list[Path]:
    selected = [
        dockerfile
        for dockerfile in DOCKERFILES
        if any(
            source.rstrip("/") == PACKAGE_SOURCE
            for source, _ in _copy_instructions(dockerfile)
        )
    ]
    assert selected, "no Dockerfile copies the so101_demo_py package"
    return selected


def test_every_packaged_parent_file_reaches_its_image() -> None:
    required_relative = _packaged_parent_paths()

    failures: list[str] = []
    for dockerfile in _images_installing_the_package():
        copies = _copy_instructions(dockerfile)
        package_destination = _normalize(
            PurePosixPath(
                next(
                    destination
                    for source, destination in copies
                    if source.rstrip("/") == PACKAGE_SOURCE
                )
            )
        )
        ignore_file = dockerfile.with_name(dockerfile.name + ".dockerignore")

        for relative in required_relative:
            target = _normalize(package_destination / relative)
            context_path = _context_path(relative)
            for source, destination in copies:
                source_path = REPOSITORY_ROOT / source
                destination_path = _normalize(PurePosixPath(destination))
                if source_path.is_file():
                    if destination_path == target and _context_included(
                        source, ignore_file
                    ):
                        break
                elif destination_path == target or str(target).startswith(
                    str(destination_path) + "/"
                ):
                    tail = target.relative_to(destination_path)
                    if (source_path / str(tail)).is_file() and _context_included(
                        source, ignore_file
                    ):
                        break
            else:
                failures.append(
                    f"{dockerfile.relative_to(REPOSITORY_ROOT)} does not provide "
                    f"{target} (setup.py packages {relative}, build context "
                    f"{context_path})"
                )

    assert not failures, "\n".join(failures)


def test_images_installing_the_package_use_their_own_ignore_list() -> None:
    for dockerfile in _images_installing_the_package():
        ignore_file = dockerfile.with_name(dockerfile.name + ".dockerignore")
        if not ignore_file.is_file():
            continue
        required = _packaged_parent_paths()
        for relative in required:
            assert _context_included(_context_path(relative), ignore_file), (
                f"{ignore_file.relative_to(REPOSITORY_ROOT)} excludes "
                f"{_context_path(relative)}, which setup.py packages as {relative}"
            )
