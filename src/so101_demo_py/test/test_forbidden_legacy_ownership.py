"""Repository contract for the sole canonical SO-101 Python demo package."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
REMOVED_PACKAGE_NAMES = tuple(f"so101_{backend}_demo_py" for backend in ("mujoco", "gazebo"))
PROCESS_DOCUMENT_ROOTS = (
    Path("docs/experiments"),
    Path("docs/plans"),
    Path("docs/provenance"),
    Path("docs/superpowers/plans"),
    Path("docs/superpowers/specs"),
)
TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".tsx",
    ".ts",
    ".xml",
    ".yaml",
    ".yml",
    ".zsh",
}


@pytest.mark.parametrize("package_name", REMOVED_PACKAGE_NAMES)
def test_removed_compatibility_package_directory_is_absent(package_name: str) -> None:
    assert not (SOURCE_ROOT / package_name).exists()


def _is_process_document(path: Path) -> bool:
    return any(path == root or root in path.parents for root in PROCESS_DOCUMENT_ROOTS)


def test_active_repository_surfaces_do_not_reference_removed_packages() -> None:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    )
    offenders: list[str] = []
    for encoded_path in completed.stdout.split(b"\0"):
        if not encoded_path:
            continue
        relative = Path(encoded_path.decode("utf-8"))
        if _is_process_document(relative) or relative.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = (REPOSITORY_ROOT / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(package_name in text for package_name in REMOVED_PACKAGE_NAMES):
            offenders.append(str(relative))
    assert offenders == []


def test_teleop_profiles_name_the_canonical_runtime_owner() -> None:
    profile_root = SOURCE_ROOT / "so101_teleop/config/backends"
    for profile in (profile_root / "gazebo_py.yaml", profile_root / "mujoco_py.yaml"):
        text = profile.read_text(encoding="utf-8")
        assert "owner_package: so101_demo_py" in text
        assert all(package_name not in text for package_name in REMOVED_PACKAGE_NAMES)
