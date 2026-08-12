from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
GATE_RELATIVE_PATH = Path("src/so101_mujoco_demo_py/scripts/check_migration_isolation.sh")
GATE_PATH = REPOSITORY_ROOT / GATE_RELATIVE_PATH
IMPLEMENTATION_ROOT = Path("src/so101_mujoco_demo_py")
GAZEBO_PACKAGE = "so101_gazebo_demo_py"
APPROVED_URL = "git@gitee.com:zjumty/mujoco_ros2_control.git"


def run(*command: str | Path, cwd: Path = REPOSITORY_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(part) for part in command],
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
    )


def require_gate_failure(checkout: Path, message: str) -> None:
    result = run(checkout / GATE_RELATIVE_PATH, cwd=checkout)
    assert result.returncode != 0, result.stdout + result.stderr
    assert message in result.stderr


@pytest.fixture
def isolated_checkout(tmp_path: Path) -> Path:
    checkout = tmp_path / "checkout"
    result = run("git", "clone", "--quiet", "--shared", str(REPOSITORY_ROOT), str(checkout))
    assert result.returncode == 0, result.stdout + result.stderr
    gate = checkout / GATE_RELATIVE_PATH
    gate.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(GATE_PATH, gate)
    gate.chmod(0o755)
    backend = checkout / "scripts/check_backend_integration.py"
    backend.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPOSITORY_ROOT / "scripts/check_backend_integration.py", backend)
    return checkout


def test_gate_accepts_current_tree() -> None:
    result = run(GATE_PATH)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "backend integration contract passed" in result.stdout


def test_gate_ignores_ordinary_gazebo_pycache(isolated_checkout: Path) -> None:
    pycache = isolated_checkout / "src/so101_gazebo_demo_py/src/__pycache__/backend.cpython-312.pyc"
    pycache.parent.mkdir(parents=True, exist_ok=True)
    pycache.write_bytes(b"ordinary ignored bytecode cache")

    result = run(isolated_checkout / GATE_RELATIVE_PATH, cwd=isolated_checkout)
    assert result.returncode == 0, result.stdout + result.stderr


def test_gate_allows_gazebo_backend_development_on_any_branch(
    isolated_checkout: Path,
) -> None:
    branch = run("git", "switch", "-c", "integration/backend-convergence", cwd=isolated_checkout)
    assert branch.returncode == 0, branch.stdout + branch.stderr
    source = isolated_checkout / "src/so101_gazebo_demo_py/src/backend_convergence.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("BACKEND_CONVERGENCE = True\n", encoding="utf-8")

    result = run(isolated_checkout / GATE_RELATIVE_PATH, cwd=isolated_checkout)
    assert result.returncode == 0, result.stdout + result.stderr


def test_gate_allows_declared_gazebo_backend_dependency(isolated_checkout: Path) -> None:
    package_xml = isolated_checkout / IMPLEMENTATION_ROOT / "package.xml"
    text = package_xml.read_text(encoding="utf-8").replace(
        "</package>",
        f"  <exec_depend>{GAZEBO_PACKAGE}</exec_depend>\n</package>",
    )
    package_xml.write_text(text, encoding="utf-8")
    source = isolated_checkout / IMPLEMENTATION_ROOT / "so101_mujoco_demo_py/declared_backend.py"
    source.write_text(f"BACKEND = '{GAZEBO_PACKAGE}'\n", encoding="utf-8")
    result = run(isolated_checkout / GATE_RELATIVE_PATH, cwd=isolated_checkout)
    assert result.returncode == 0, result.stdout + result.stderr


def test_gate_rejects_undeclared_gazebo_backend_dependency(isolated_checkout: Path) -> None:
    source = isolated_checkout / IMPLEMENTATION_ROOT / "so101_mujoco_demo_py/undeclared_backend.py"
    source.write_text(f"BACKEND = '{GAZEBO_PACKAGE}'\n", encoding="utf-8")
    require_gate_failure(isolated_checkout, "undeclared Gazebo backend dependency")


@pytest.mark.parametrize("kind", ["outside", "git", "cycle"])
def test_gate_rejects_implementation_symlink_escape_git_or_cycle(
    isolated_checkout: Path,
    kind: str,
) -> None:
    link = isolated_checkout / IMPLEMENTATION_ROOT / "launch/linked.py"
    link.parent.mkdir(parents=True, exist_ok=True)
    if kind == "outside":
        target = isolated_checkout.parent / "outside.py"
        target.write_text("VALUE = 1\n", encoding="utf-8")
        link.symlink_to(target)
        expected = "escapes repository"
    elif kind == "git":
        link.symlink_to(isolated_checkout / ".git")
        expected = "enters Git metadata"
    else:
        link.symlink_to(isolated_checkout / IMPLEMENTATION_ROOT / "launch")
        (isolated_checkout / IMPLEMENTATION_ROOT / "launch/self.py").symlink_to(link)
        expected = "cycle"
    require_gate_failure(isolated_checkout, expected)


def test_gate_rejects_unapproved_control_submodule_url(isolated_checkout: Path) -> None:
    gitmodules = isolated_checkout / ".gitmodules"
    gitmodules.write_text(
        gitmodules.read_text(encoding="utf-8").replace(
            APPROVED_URL,
            "https://example.invalid/wrong.git",
        ),
        encoding="utf-8",
    )
    require_gate_failure(isolated_checkout, "control submodule URL")


def test_gate_rejects_non_gitlink_control_dependency(isolated_checkout: Path) -> None:
    blob = run("git", "rev-parse", "HEAD:.gitmodules", cwd=isolated_checkout)
    assert blob.returncode == 0
    result = run(
        "git",
        "update-index",
        "--add",
        "--cacheinfo",
        "100644",
        blob.stdout.strip(),
        "third_party/mujoco_ros2_control",
        cwd=isolated_checkout,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    require_gate_failure(isolated_checkout, "control dependency is not recorded as a gitlink")


def test_runtime_and_install_provenance_gates_remain_available() -> None:
    runtime = REPOSITORY_ROOT / IMPLEMENTATION_ROOT / "scripts/check_mujoco_runtime.py"
    reset = REPOSITORY_ROOT / IMPLEMENTATION_ROOT / "scripts/check_reset_qualified_runtime.py"
    assert runtime.is_file() and reset.is_file()
    assert "installed_hashes" in runtime.read_text(encoding="utf-8")
    assert "installed file hash mismatch" in reset.read_text(encoding="utf-8")


@pytest.mark.parametrize("mutation", ["behavior_commit", "backup_commit", "adaptation_hash"])
def test_gate_rejects_tampered_provenance(isolated_checkout: Path, mutation: str) -> None:
    path = isolated_checkout / IMPLEMENTATION_ROOT / "docs/provenance.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "behavior_commit":
        document["behavior_source"]["commit"] = "0" * 40
    elif mutation == "backup_commit":
        document["rejected_backup"]["commit"] = "1" * 40
    else:
        document["adaptations"][0]["source_sha256"] = "f" * 64
    path.write_text(json.dumps(document), encoding="utf-8")
    require_gate_failure(isolated_checkout, "provenance")
