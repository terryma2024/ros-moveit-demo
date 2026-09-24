"""Contract tests for the registered execution gate.

The gate is loaded directly from source by path, exactly as the plan requires, so the
tests exercise the real script that every RED/GREEN invocation of this task goes
through. The unit API is injected with explicit policies; that is a test seam and does
not grant any production execution authority.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

GATE_PATH = Path(__file__).parents[1] / "test/e2e/record_gate.py"

POLICY_FIELDS = {
    "execution_host": "unit-host",
    "task_root": "/tmp/unit-root",
    "require_ai_station_nvme": False,
}


def load_gate_module():
    """Load the gate script as a module without installing it as a package."""
    spec = importlib.util.spec_from_file_location("so101_teleop_gate", GATE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def gate():
    return load_gate_module()


def write_policy(root: Path, policy: dict) -> tuple[Path, str]:
    path = root / "policy.json"
    payload = json.dumps(policy, sort_keys=True).encode()
    path.write_bytes(payload)
    return path, hashlib.sha256(payload).hexdigest()


def freeze_policy(monkeypatch, root: Path, policy: dict) -> Path:
    path, digest = write_policy(root, policy)
    monkeypatch.setenv("SO101_GATE_POLICY", str(path))
    monkeypatch.setenv("SO101_GATE_POLICY_SHA256", digest)
    return path


def make_fake_python(root: Path, name: str, executable_line: str, temp_line: str) -> Path:
    script = root / name
    script.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' {shell_quote(executable_line)}\n"
        f"printf '%s\\n' {shell_quote(temp_line)}\n"
    )
    script.chmod(0o755)
    return script


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def test_gate_proves_exact_python_temp_and_retains_nonzero(gate, tmp_path):
    rc = gate.run_gate(
        root=tmp_path,
        python=Path(sys.executable),
        argv=[sys.executable, "-c", "raise SystemExit(7)"],
        policy=gate.GatePolicy("unit-host", tmp_path, False),
    )
    record = next((tmp_path / "gates").glob("*/result.json"))
    data = json.loads(record.read_text())
    assert rc == data["exit_code"] == 7
    assert Path(data["tempfile_dir"]).is_relative_to(record.parent)
    assert data["elapsed_seconds"] >= 0
    assert (record.parent / "stderr.txt").exists()


def test_gate_records_argv_stdout_and_scratch_proof(gate, tmp_path):
    rc = gate.run_gate(
        root=tmp_path,
        python=Path(sys.executable),
        argv=[sys.executable, "-c", "import tempfile,sys;print(tempfile.gettempdir())"],
        policy=gate.GatePolicy("unit-host", tmp_path, False),
    )
    record = next((tmp_path / "gates").glob("*/result.json"))
    data = json.loads(record.read_text())
    assert rc == data["exit_code"] == 0
    assert data["argv"][0] == sys.executable
    assert Path(data["test_python"]).resolve() == Path(sys.executable).resolve()
    run_dir = record.parent
    assert (run_dir / "stdout.txt").read_text().strip() == data["tempfile_dir"]
    assert Path(data["tempfile_dir"]).is_relative_to(run_dir)
    assert (run_dir / "tmp").is_dir()


def test_gate_refuses_unregistered_root(gate, tmp_path):
    registered = tmp_path / "registered"
    registered.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(RuntimeError, match="REGISTERED_ROOT_MISMATCH"):
        gate.run_gate(
            root=other,
            python=Path(sys.executable),
            argv=[sys.executable, "-c", "raise SystemExit(0)"],
            policy=gate.GatePolicy("unit-host", registered, False),
        )
    assert not (other / "gates").exists()


def test_gate_requires_nvme_root_when_policy_demands_it(gate, tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "NVME_EVIDENCE_ROOT", tmp_path / "registered-nvme-root")
    with pytest.raises(RuntimeError, match="REGISTERED_NVME_ROOT_REQUIRED"):
        gate.run_gate(
            root=tmp_path,
            python=Path(sys.executable),
            argv=[sys.executable, "-c", "raise SystemExit(0)"],
            policy=gate.GatePolicy("ai-station", tmp_path, True),
        )
    assert not (tmp_path / "gates").exists()


def test_gate_rejects_interpreter_mismatch_before_starting_command(gate, tmp_path):
    marker = tmp_path / "started.marker"
    fake = make_fake_python(tmp_path, "not-python", "/nonexistent/other-python", str(tmp_path))
    with pytest.raises(RuntimeError, match="TEST_PYTHON_TEMP_MISMATCH"):
        gate.run_gate(
            root=tmp_path,
            python=fake,
            argv=["/bin/sh", "-c", f"touch {marker}"],
            policy=gate.GatePolicy("unit-host", tmp_path, False),
        )
    assert not marker.exists(), "command under test must not start after a proof mismatch"


def test_gate_rejects_temp_mismatch_before_starting_command(gate, tmp_path):
    marker = tmp_path / "started.marker"
    fake = make_fake_python(tmp_path, "wrong-temp", str(tmp_path / "wrong-temp"), "/tmp")
    with pytest.raises(RuntimeError, match="TEST_PYTHON_TEMP_MISMATCH"):
        gate.run_gate(
            root=tmp_path,
            python=fake,
            argv=["/bin/sh", "-c", f"touch {marker}"],
            policy=gate.GatePolicy("unit-host", tmp_path, False),
        )
    assert not marker.exists(), "command under test must not start after a proof mismatch"


def test_gate_uses_a_fresh_scratch_directory_per_call(gate, tmp_path):
    policy = gate.GatePolicy("unit-host", tmp_path, False)
    argv = [sys.executable, "-c", "raise SystemExit(0)"]
    assert gate.run_gate(root=tmp_path, python=Path(sys.executable), argv=argv, policy=policy) == 0
    assert gate.run_gate(root=tmp_path, python=Path(sys.executable), argv=argv, policy=policy) == 0
    runs = sorted((tmp_path / "gates").glob("*/result.json"))
    assert len(runs) == 2
    temps = {json.loads(run.read_text())["tempfile_dir"] for run in runs}
    assert len(temps) == 2
    assert all(Path(temp).is_dir() for temp in temps)


def test_load_registered_policy_accepts_matching_host_and_root(gate, monkeypatch, tmp_path):
    policy = {
        "execution_host": gate.socket.gethostname(),
        "task_root": str(tmp_path),
        "require_ai_station_nvme": False,
    }
    freeze_policy(monkeypatch, tmp_path, policy)
    loaded = gate.load_registered_policy()
    assert loaded.execution_host == policy["execution_host"]
    assert loaded.task_root == tmp_path
    assert loaded.require_ai_station_nvme is False


@pytest.mark.parametrize(
    "host, task_root, expected_nvme",
    [
        ("ai-station", "/data/work/so101-evidence/unified-webapp/R1", True),
        ("other-linux", "/home/someone/so101-evidence/run-1", False),
        ("macos-host", "/tmp/so101-debug-unified-webapp-impl-20260920", False),
    ],
)
def test_load_registered_policy_records_operator_nvme_flag(
    gate, monkeypatch, tmp_path, host, task_root, expected_nvme
):
    """The NVMe requirement comes from the registered object, never from OS guessing."""
    policy = {
        "execution_host": host,
        "task_root": task_root,
        "require_ai_station_nvme": expected_nvme,
    }
    freeze_policy(monkeypatch, tmp_path, policy)
    monkeypatch.setattr(socket, "gethostname", lambda: host)
    loaded = gate.load_registered_policy()
    assert loaded.require_ai_station_nvme is expected_nvme
    assert loaded.task_root == Path(task_root)
    assert loaded.execution_host == host


def test_load_registered_policy_refuses_host_mismatch(gate, monkeypatch, tmp_path):
    policy = dict(POLICY_FIELDS, execution_host="some-other-host")
    freeze_policy(monkeypatch, tmp_path, policy)
    with pytest.raises(RuntimeError, match="REGISTERED_HOST_MISMATCH"):
        gate.load_registered_policy()


def test_load_registered_policy_refuses_hash_drift(gate, monkeypatch, tmp_path):
    path, digest = write_policy(tmp_path, POLICY_FIELDS)
    monkeypatch.setenv("SO101_GATE_POLICY", str(path))
    monkeypatch.setenv("SO101_GATE_POLICY_SHA256", "0" * 64)
    with pytest.raises(RuntimeError, match="GATE_POLICY_HASH_MISMATCH"):
        gate.load_registered_policy()
    assert digest != "0" * 64


@pytest.mark.parametrize(
    "mutation, code",
    [
        ({"execution_host": None}, "GATE_POLICY_INVALID"),
        ({"task_root": None}, "GATE_POLICY_INVALID"),
        ({"require_ai_station_nvme": None}, "GATE_POLICY_INVALID"),
    ],
)
def test_load_registered_policy_refuses_missing_fields(gate, monkeypatch, tmp_path, mutation, code):
    policy = dict(POLICY_FIELDS)
    policy.update(mutation)
    freeze_policy(monkeypatch, tmp_path, policy)
    with pytest.raises(RuntimeError, match=code):
        gate.load_registered_policy()


def test_load_registered_policy_requires_reference_and_digest(gate, monkeypatch):
    monkeypatch.delenv("SO101_GATE_POLICY", raising=False)
    monkeypatch.delenv("SO101_GATE_POLICY_SHA256", raising=False)
    with pytest.raises(RuntimeError, match="GATE_POLICY_UNREGISTERED"):
        gate.load_registered_policy()
    monkeypatch.setenv("SO101_GATE_POLICY", "/nonexistent/policy.json")
    monkeypatch.setenv("SO101_GATE_POLICY_SHA256", "a" * 64)
    with pytest.raises(RuntimeError, match="GATE_POLICY_MISSING"):
        gate.load_registered_policy()


def test_cli_runs_registered_gate_and_reports_child_exit_code(monkeypatch, tmp_path):
    policy = {
        "execution_host": socket.gethostname(),
        "task_root": str(tmp_path),
        "require_ai_station_nvme": False,
    }
    _, digest = write_policy(tmp_path, policy)
    env = dict(
        os.environ,
        SO101_GATE_POLICY=str(tmp_path / "policy.json"),
        SO101_GATE_POLICY_SHA256=digest,
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(GATE_PATH),
            "--root",
            str(tmp_path),
            "--python",
            sys.executable,
            "--",
            sys.executable,
            "-c",
            "raise SystemExit(7)",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 7, completed.stderr
    record = next((tmp_path / "gates").glob("*/result.json"))
    data = json.loads(record.read_text())
    assert data["exit_code"] == 7
    assert data["argv"][-1] == "raise SystemExit(7)"


def test_cli_without_registered_policy_fails_closed(monkeypatch, tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("SO101_GATE_POLICY")}
    completed = subprocess.run(
        [
            sys.executable,
            str(GATE_PATH),
            "--root",
            str(tmp_path),
            "--python",
            sys.executable,
            "--",
            sys.executable,
            "-c",
            "raise SystemExit(0)",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "GATE_POLICY_UNREGISTERED" in completed.stderr
    assert not (tmp_path / "gates").exists()
