from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
GATE = PACKAGE_ROOT / "scripts/check_ruff.sh"
CONFIG = PACKAGE_ROOT / "ruff.toml"


def test_ruff_gate_is_executable_and_pins_version_and_rules() -> None:
    assert GATE.is_file()
    assert os.access(GATE, os.X_OK)
    config = CONFIG.read_text(encoding="utf-8")
    assert 'required-version = "==0.15.20"' in config
    assert 'select = ["E4", "E7", "E9", "F", "I"]' in config


def test_ruff_gate_executes_check_and_format_on_only_new_package(tmp_path: Path) -> None:
    calls = tmp_path / "calls"
    fake_ruff = tmp_path / "ruff"
    fake_ruff.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ $1 == --version ]]; then echo 'ruff 0.15.20'; exit 0; fi\n"
        f"printf '%s\\n' \"$*\" >> {calls}\n",
        encoding="utf-8",
    )
    fake_ruff.chmod(0o755)
    environment = dict(os.environ)
    environment["PATH"] = f"{tmp_path}:{environment['PATH']}"

    result = subprocess.run(
        [str(GATE)],
        cwd=PACKAGE_ROOT,
        env=environment,
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    invocations = calls.read_text(encoding="utf-8").splitlines()
    assert len(invocations) == 2
    assert invocations[0].startswith("check ")
    assert invocations[1].startswith("format --check ")
    for invocation in invocations:
        assert "setup.py" in invocation
        assert "so101_mujoco_demo_py" in invocation
        assert "test" in invocation
        assert "scripts" in invocation
        assert "launch" not in invocation or (PACKAGE_ROOT / "launch").is_dir()
        assert "config" not in invocation or (PACKAGE_ROOT / "config").is_dir()
        assert "so101_gazebo_demo_py" not in invocation


def test_real_ruff_gate_passes_for_the_package() -> None:
    result = subprocess.run(
        [str(GATE)],
        cwd=PACKAGE_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "All checks passed!" in result.stdout
    assert "files already formatted" in result.stdout


def test_real_ruff_gate_rejects_a_package_lint_violation(tmp_path: Path) -> None:
    package_copy = tmp_path / "so101_mujoco_demo_py"
    shutil.copytree(PACKAGE_ROOT, package_copy)
    (package_copy / "so101_mujoco_demo_py" / "broken.py").write_text(
        "undefined_name\n", encoding="utf-8"
    )

    result = subprocess.run(
        [str(package_copy / "scripts/check_ruff.sh")],
        cwd=package_copy,
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "F821" in result.stdout
