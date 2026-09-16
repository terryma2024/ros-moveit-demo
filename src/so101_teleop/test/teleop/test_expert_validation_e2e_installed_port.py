"""Contract tests for the L2 installed execution port and process helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

_E2E_DIR = Path(__file__).resolve().parents[1] / "e2e"
_TELEOP_ROOT = Path(__file__).resolve().parents[2]
_DEMO_SRC = _TELEOP_ROOT.parent / "so101_demo_py" / "src"
for _path in (str(_E2E_DIR), str(_E2E_DIR / "process_helpers"), str(_DEMO_SRC)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from execution_port import (  # noqa: E402
    HelperExecutionPort,
    TEST_PORT_MARKER,
)
from so101_teleop.expert_validation.production import create_production_service  # noqa: E402
from so101_teleop.expert_validation.supervisor import ExpertValidationSupervisor  # noqa: E402
from so101_demo.parallel_batch.artifacts import verify_attempt  # noqa: E402
from so101_demo.parallel_batch.contracts import AttemptIdentity  # noqa: E402
from so101_demo.parallel_batch.journal import CoordinatorJournal  # noqa: E402

import inspect  # noqa: E402


def _port(tmp_path: Path) -> HelperExecutionPort:
    spec = tmp_path / "helper-spec.json"
    spec.write_text(json.dumps({"points": {}, "default_outcome": "FAILED"}) + "\n", "utf-8")
    return HelperExecutionPort(
        python=sys.executable,
        helpers_dir=_E2E_DIR / "process_helpers",
        spec_path=spec,
    )


def test_production_entry_has_no_execution_port():
    signature = inspect.signature(create_production_service)
    assert signature.parameters["execution_port"].default is None
    supervisor_signature = inspect.signature(ExpertValidationSupervisor.__init__)
    assert supervisor_signature.parameters["execution_port"].default is None


def test_production_supervisor_without_port_keeps_production_argv(tmp_path):
    from so101_teleop.expert_validation.supervisor import ExpertValidationSupervisor as S
    from so101_teleop.expert_validation.preflight import PreflightEngine

    class _Store:
        pass

    supervisor = S(store=None, process_owner=None, preflight_engine=None)
    marker = object()
    assert supervisor._apply_execution_port(marker) is marker


def test_port_qualification_manifest_records_real_hashes(tmp_path):
    port = _port(tmp_path)
    manifest = port.qualification_manifest()
    assert manifest.marker == TEST_PORT_MARKER
    for path, digest in (
        (manifest.fixed_helper, manifest.fixed_helper_sha256),
        (manifest.adaptive_helper, manifest.adaptive_helper_sha256),
        (manifest.descendant_helper, manifest.descendant_helper_sha256),
        (manifest.spec_path, manifest.spec_sha256),
    ):
        import hashlib

        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest


def test_fixed_helper_full_protocol(tmp_path):
    port = _port(tmp_path)
    batch_root = tmp_path / "batch" / "b0001"
    batch_root.parent.mkdir(parents=True)
    request = type(
        "Request",
        (),
        {
            "batch_id": "b0001",
            "campaign_id": "campaign-test",
            "batch_root": batch_root,
            "worker_count": 1,
            "max_points_per_worker": 2,
            "selected_point_ids": ("task_start", "cup_test_forward_5cm"),
        },
    )()
    argv = port.fixed_argv(request)
    assert "--adaptive-workers" not in argv
    environment = dict(os.environ)
    environment.update({
        "SO101_FIXED_CONTROL_TOKEN": "ab" * 32,
        "SO101_FIXED_CONTROL_CAMPAIGN_ID": "campaign-test",
        "SO101_FIXED_CONTROL_EPOCH": "1",
        "SO101_FIXED_CONTROL_SOCKET": str(batch_root / "control" / "control.sock"),
    })
    result = subprocess.run(argv, env=environment, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr

    replay = CoordinatorJournal.read_only_replay(batch_root / "coordinator", "b0001")
    types = [event.type for event in replay.events]
    assert types[0] == "BATCH_STARTED"
    assert types[-1] == "BATCH_FINISHED"
    assert types.count("RESULT_COMMITTED") == 2
    epoch = json.loads((batch_root / "coordinator" / "coordinator_epoch.json").read_text())
    assert epoch == {"batch_id": "b0001", "coordinator_epoch": 1}
    cleanup = json.loads((batch_root / "cleanup-gates.json").read_text())
    assert cleanup["owned_descendants_gone"] is True

    for event in replay.events:
        if event.type != "RESULT_COMMITTED":
            continue
        identity = AttemptIdentity(
            **{key: value for key, value in event.payload["identity"].items() if key != "location"}
        )
        sealed = Path(event.payload["response"]["location"])
        verify_attempt(sealed, identity)


def test_fixed_helper_descendant_survives_leader_exit(tmp_path):
    spec = tmp_path / "helper-spec.json"
    spec.write_text(json.dumps({"descendant_mode": "survive"}) + "\n", "utf-8")
    port = HelperExecutionPort(
        python=sys.executable, helpers_dir=_E2E_DIR / "process_helpers", spec_path=spec
    )
    batch_root = tmp_path / "batch" / "b0002"
    batch_root.parent.mkdir(parents=True)
    request = type(
        "Request",
        (),
        {
            "batch_id": "b0002",
            "campaign_id": "campaign-test",
            "batch_root": batch_root,
            "worker_count": 1,
            "max_points_per_worker": 1,
            "selected_point_ids": ("task_start",),
        },
    )()
    process = subprocess.Popen(
        port.fixed_argv(request),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
        env={
            **os.environ,
            "SO101_FIXED_CONTROL_TOKEN": "cd" * 32,
            "SO101_FIXED_CONTROL_CAMPAIGN_ID": "campaign-test",
            "SO101_FIXED_CONTROL_EPOCH": "1",
            "SO101_FIXED_CONTROL_SOCKET": str(batch_root / "control" / "control.sock"),
        },
    )
    descendant_pid = None
    try:
        assert process.wait(timeout=30) == 0
        output = process.stdout.read() if process.stdout else ""
        for line in output.splitlines():
            if line.startswith("descendant_pid="):
                descendant_pid = int(line.split("=", 1)[1])
        assert descendant_pid is not None
        assert Path(f"/proc/{descendant_pid}").exists()
        stat = Path(f"/proc/{descendant_pid}/stat").read_text()
        tail = stat[stat.rfind(")") + 2 :].split()
        assert int(tail[2]) == process.pid
    finally:
        if descendant_pid is not None and Path(f"/proc/{descendant_pid}").exists():
            os.kill(descendant_pid, signal.SIGKILL)
            for _ in range(100):
                if not Path(f"/proc/{descendant_pid}").exists():
                    break
                time.sleep(0.05)


def test_adaptive_helper_handshake_and_sigint_cleanup(tmp_path):
    port = _port(tmp_path)
    runtime_root = tmp_path / "r" / "a001"
    runtime_root.mkdir(parents=True)
    request = type(
        "Request",
        (),
        {
            "batch_id": "a001",
            "campaign_id": "campaign-test",
            "runtime_root": runtime_root,
            "preferred_worker_count": 8,
            "selected_point_ids": ("task_start",),
        },
    )()
    argv = port.adaptive_argv(request)
    assert "--max-points-per-worker" not in argv
    assert "--live-headroom-evidence" not in argv
    process = subprocess.Popen(argv, start_new_session=True)
    try:
        handshake_path = runtime_root / "handshake.json"
        deadline = time.monotonic() + 10
        while not handshake_path.is_file() and time.monotonic() < deadline:
            time.sleep(0.05)
        handshake = json.loads(handshake_path.read_text())
        assert handshake["wrapper_pid"] == process.pid
        assert handshake["batch_id"] == "a001"
        assert handshake["runner_pid"] > 0
        assert Path(f"/proc/{handshake['runner_pid']}").exists()
        process.send_signal(signal.SIGINT)
        assert process.wait(timeout=10) == 0
        receipt = json.loads((runtime_root / "cleanup-receipt.json").read_text())
        assert receipt["cleanup_complete"] is True
        assert not Path(f"/proc/{handshake['runner_pid']}").exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
