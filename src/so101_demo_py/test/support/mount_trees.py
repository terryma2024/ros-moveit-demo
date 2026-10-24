"""A mounted-build fixture for tests that start containers: the two trees of one commit with their BUILD-COMMIT records.
Every run starts from a mount tree (image mode is retired), so launch-side tests take this instead of an image path."""

from pathlib import Path

from so101_demo.runtime.container_campaign.mount_build import MountBuild

COMMIT = "0123456789abcdef0123456789abcdef01234567"


def make_mount_trees(tmp_path: Path, commit: str = COMMIT, name: str = "mounted") -> MountBuild:
    root = Path(tmp_path) / name / commit[:12]
    for directory in ("install", "source"):
        (root / directory).mkdir(parents=True, exist_ok=True)
        (root / directory / "BUILD-COMMIT").write_text(commit + "\n")
    (root / "install" / "so101_demo_py").mkdir(exist_ok=True)
    return MountBuild(commit=commit, root=root)
