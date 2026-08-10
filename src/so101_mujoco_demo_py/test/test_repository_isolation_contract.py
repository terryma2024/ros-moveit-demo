from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
GATE_RELATIVE_PATH = Path(
    "src/so101_mujoco_demo_py/scripts/check_migration_isolation.sh"
)
GATE_PATH = REPOSITORY_ROOT / GATE_RELATIVE_PATH
LEDGER_PATH = (
    REPOSITORY_ROOT
    / "docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md"
)
MAIN_BASE_COMMIT = "d300e7a41fb274d6d7e120699b7040666ea61904"
EXPECTED_BRANCH = "codex/so101-mujoco-ros2"
LEGACY_NAMESPACE = "so101_gazebo_" + "demo_py"
PROTECTED_TREE = Path("src") / ("so101_gazebo_" + "demo_py")
BACKUP_BRANCH = "codex/so101-mujoco-ros2-pre-" + "isolation-20260810"


def run(*command: str | Path, cwd: Path = REPOSITORY_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(part) for part in command],
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
    )


def require_success(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


def require_gate_artifact() -> None:
    if not GATE_PATH.is_file():
        pytest.skip("isolation gate is the production artifact under TDD")


def require_gate_failure(
    checkout: Path, expected_message: str
) -> subprocess.CompletedProcess[str]:
    result = run(checkout / GATE_RELATIVE_PATH, cwd=checkout)
    assert result.returncode != 0, result.stdout + result.stderr
    assert expected_message in result.stderr
    return result


@pytest.fixture
def isolated_checkout(tmp_path: Path) -> Path:
    require_gate_artifact()
    checkout = tmp_path / "checkout"
    require_success(
        run(
            "git",
            "clone",
            "--quiet",
            "--shared",
            str(REPOSITORY_ROOT),
            str(checkout),
        )
    )

    copied_gate = checkout / GATE_RELATIVE_PATH
    copied_gate.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(GATE_PATH, copied_gate)
    copied_gate.chmod(0o755)

    provenance = checkout / "docs/implementation-provenance.md"
    provenance.parent.mkdir(parents=True, exist_ok=True)
    provenance.write_text(f"Rejected backup: `{BACKUP_BRANCH}`.\n")
    return checkout


def test_required_isolation_artifacts_exist() -> None:
    missing = [
        str(artifact.relative_to(REPOSITORY_ROOT))
        for artifact in (GATE_PATH, LEDGER_PATH)
        if not artifact.is_file()
    ]
    assert not missing, f"missing required artifacts: {missing}"
    assert os.access(GATE_PATH, os.X_OK)


def test_worktree_uses_the_exact_main_base() -> None:
    result = run("git", "merge-base", "HEAD", "origin/main")
    require_success(result)
    assert result.stdout.strip() == MAIN_BASE_COMMIT


def test_gate_accepts_the_current_isolated_worktree() -> None:
    require_gate_artifact()
    require_success(run(GATE_PATH))


def test_gate_rejects_a_different_main_base(isolated_checkout: Path) -> None:
    parent_result = run(
        "git", "rev-parse", f"{MAIN_BASE_COMMIT}^", cwd=isolated_checkout
    )
    require_success(parent_result)
    require_success(
        run(
            "git",
            "update-ref",
            "refs/remotes/origin/main",
            parent_result.stdout.strip(),
            cwd=isolated_checkout,
        )
    )

    require_gate_failure(isolated_checkout, "unexpected main merge-base")


def test_gate_rejects_the_wrong_branch(isolated_checkout: Path) -> None:
    require_success(
        run("git", "switch", "--quiet", "-c", "test/wrong-branch", cwd=isolated_checkout)
    )

    require_gate_failure(isolated_checkout, "unexpected branch")


def test_gate_rejects_tracked_protected_tree_drift(isolated_checkout: Path) -> None:
    protected_file = isolated_checkout / PROTECTED_TREE / "README.md"
    protected_file.write_text(protected_file.read_text() + "\nprotected drift\n")

    require_gate_failure(isolated_checkout, "protected Gazebo tree differs")


def test_gate_rejects_untracked_protected_tree_status(isolated_checkout: Path) -> None:
    untracked_file = isolated_checkout / PROTECTED_TREE / "unexpected.txt"
    untracked_file.write_text("must be rejected\n")

    require_gate_failure(isolated_checkout, "protected Gazebo tree has worktree changes")


@pytest.mark.parametrize(
    ("relative_path", "contents"),
    [
        (
            Path("package.xml"),
            f"<package><exec_depend>{LEGACY_NAMESPACE}</exec_depend></package>\n",
        ),
        (
            Path("setup.py"),
            f"install_requires=[{LEGACY_NAMESPACE!r}]\n",
        ),
        (
            Path("so101_mujoco_demo_py/runtime.py"),
            f"from {LEGACY_NAMESPACE}.runtime import Runtime\n",
        ),
        (
            Path("launch/runtime.launch.py"),
            "from launch_ros.substitutions import FindPackageShare\n"
            f"RESOURCE = FindPackageShare({LEGACY_NAMESPACE!r})\n",
        ),
    ],
    ids=["package-xml", "setup-py", "python-import", "launch-resource-lookup"],
)
def test_gate_rejects_legacy_runtime_dependencies(
    isolated_checkout: Path, relative_path: Path, contents: str
) -> None:
    dependency_file = isolated_checkout / "src/so101_mujoco_demo_py" / relative_path
    dependency_file.parent.mkdir(parents=True, exist_ok=True)
    dependency_file.write_text(contents)

    require_gate_failure(isolated_checkout, "legacy Gazebo Python namespace")


def test_gate_allows_legacy_source_paths_in_provenance_json(
    isolated_checkout: Path,
) -> None:
    provenance = (
        isolated_checkout
        / "src/so101_mujoco_demo_py/docs/provenance.json"
    )
    provenance.parent.mkdir(parents=True, exist_ok=True)
    provenance.write_text(
        '{"behavior_source": "src/' + LEGACY_NAMESPACE + '/runtime.py"}\n'
    )

    require_success(run(isolated_checkout / GATE_RELATIVE_PATH, cwd=isolated_checkout))


def test_gate_allows_backup_branch_only_in_documentation(
    isolated_checkout: Path,
) -> None:
    require_success(run(isolated_checkout / GATE_RELATIVE_PATH, cwd=isolated_checkout))

    leaked_reference = isolated_checkout / "src/so101_mujoco_demo_py/README.txt"
    leaked_reference.parent.mkdir(parents=True, exist_ok=True)
    leaked_reference.write_text(f"Runtime fallback: {BACKUP_BRANCH}\n")

    require_gate_failure(isolated_checkout, "backup branch reference outside documentation")
