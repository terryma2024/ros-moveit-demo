import asyncio
import json
import signal
import subprocess
from pathlib import Path
import inspect

import pytest

from so101_teleop.backends.registry import load_backend_profile
from so101_teleop.task_gateway import (
    CliTaskGateway,
    TaskCaptureOwnerRequest,
    TaskGatewayBusy,
    TaskGatewayError,
    TaskOwnerRequest,
    TaskReachabilityOwnerRequest,
)


PACKAGE = Path(__file__).resolve().parents[2]


class FakeProcess:
    def __init__(self, pid=4101):
        self.pid = pid
        self.returncode = None

    def poll(self):
        return self.returncode


def executable_prefix(tmp_path, executable):
    path = tmp_path / "lib" / "so101_demo_py" / executable
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def gateway_for(
    tmp_path,
    *,
    process=None,
    capture_result=None,
    attached_mujoco_pid=53900,
):
    profile = load_backend_profile("mujoco_py", PACKAGE)
    for spec in profile.operations.values():
        executable_prefix(tmp_path / "install", spec.executable)
    popen_calls = []
    run_calls = []
    child = process or FakeProcess()

    def popen(argv, **kwargs):
        popen_calls.append((argv, kwargs))
        return child

    def run(argv, **kwargs):
        run_calls.append((argv, kwargs))
        return capture_result or subprocess.CompletedProcess(
            argv, 0, json.dumps({"status": "SUCCEEDED"}), ""
        )

    gateway = CliTaskGateway(
        profile,
        package_prefix_resolver=lambda _package: str(tmp_path / "install"),
        popen=popen,
        run_process=run,
        getpgid=lambda pid: pid + 100,
        killpg=lambda pgid, sig: None,
        uuid_factory=lambda: "run-safe-001",
        attached_mujoco_pid=attached_mujoco_pid,
    )
    return gateway, child, popen_calls, run_calls


def request(evidence_root):
    return TaskOwnerRequest(
        simulation_session_id="sim-session-a",
        points_yaml=(
            "schema_version: 1\npoints:\n"
            "  - id: free-a\n"
            "    label: Free A\n"
            "    cup_position_world_m: [0.02, -0.30, 0.165]\n"
        ),
        evidence_root=evidence_root,
    )


def test_start_batch_owns_fixed_process_group_and_exclusive_input(tmp_path):
    gateway, child, popen_calls, _ = gateway_for(tmp_path)

    handle = asyncio.run(gateway.start_batch(request(tmp_path / "evidence")))

    assert handle.run_id == "run-safe-001"
    assert (handle.pid, handle.pgid) == (child.pid, child.pid + 100)
    assert handle.manifest_path == (
        tmp_path / "evidence/batches/run-safe-001/batch-result.json"
    )
    points = tmp_path / "evidence/.task-inputs/run-safe-001/points.yaml"
    assert points.read_text().startswith("schema_version: 1")
    argv, options = popen_calls[0]
    assert argv[0].endswith("/lib/so101_demo_py/so101_mujoco_rgbd_batch")
    assert argv[1:] == [
        "--points", str(points),
        "--batch-id", "run-safe-001",
        "--session-id", "sim-session-a",
        "--evidence-root", str(tmp_path / "evidence"),
        "--attach-existing-stack",
        "--mujoco-pid", "53900",
    ]
    assert options["shell"] is False
    assert options["start_new_session"] is True


def test_start_batch_attaches_to_explicit_task_station_mujoco_pid(tmp_path):
    profile = load_backend_profile("mujoco_py", PACKAGE)
    for spec in profile.operations.values():
        executable_prefix(tmp_path / "install", spec.executable)
    popen_calls = []

    def popen(argv, **kwargs):
        popen_calls.append((argv, kwargs))
        return FakeProcess()

    gateway = CliTaskGateway(
        profile,
        package_prefix_resolver=lambda _package: str(tmp_path / "install"),
        popen=popen,
        getpgid=lambda pid: pid + 100,
        uuid_factory=lambda: "attached-run",
        attached_mujoco_pid=53900,
    )

    asyncio.run(gateway.start_batch(request(tmp_path / "evidence")))

    argv = popen_calls[0][0]
    assert argv[-3:] == ["--attach-existing-stack", "--mujoco-pid", "53900"]


def test_start_batch_fails_closed_without_attached_task_station(tmp_path):
    gateway, _child, popen_calls, _ = gateway_for(
        tmp_path, attached_mujoco_pid=None
    )

    with pytest.raises(TaskGatewayError, match="TASK_STATION_MUJOCO_PID_MISSING"):
        asyncio.run(gateway.start_batch(request(tmp_path / "evidence")))

    assert popen_calls == []


def test_only_one_active_batch_is_allowed(tmp_path):
    gateway, _child, popen_calls, _ = gateway_for(tmp_path)
    asyncio.run(gateway.start_batch(request(tmp_path / "evidence")))

    with pytest.raises(TaskGatewayBusy, match="TASK_BATCH_ACTIVE"):
        asyncio.run(gateway.start_batch(request(tmp_path / "other")))

    assert len(popen_calls) == 1


def test_status_reads_only_registered_atomic_manifest(tmp_path):
    gateway, child, _popen_calls, _ = gateway_for(tmp_path)
    handle = asyncio.run(gateway.start_batch(request(tmp_path / "evidence")))

    assert asyncio.run(gateway.status(handle.run_id)) == {
        "run_id": handle.run_id,
        "status": "RUNNING",
        "pid": child.pid,
    }
    handle.manifest_path.parent.mkdir(parents=True)
    handle.manifest_path.write_text('{"status":"SUCCEEDED","points":[]}\n')
    assert asyncio.run(gateway.status(handle.run_id))["status"] == "SUCCEEDED"
    with pytest.raises(TaskGatewayError, match="TASK_RUN_NOT_FOUND"):
        asyncio.run(gateway.status("../foreign"))


def test_status_rejects_manifest_reached_through_symlinked_batch_root(tmp_path):
    gateway, _child, _popen_calls, _ = gateway_for(tmp_path)
    root = tmp_path / "evidence"
    handle = asyncio.run(gateway.start_batch(request(root)))
    foreign = tmp_path / "foreign"
    (foreign / handle.run_id).mkdir(parents=True)
    (foreign / handle.run_id / "batch-result.json").write_text(
        '{"status":"SUCCEEDED"}\n'
    )
    (root / "batches").symlink_to(foreign, target_is_directory=True)

    with pytest.raises(TaskGatewayError, match="TASK_MANIFEST_INVALID"):
        asyncio.run(gateway.status(handle.run_id))


def test_cancel_signals_only_owned_pgid_with_bounded_escalation(tmp_path):
    process = FakeProcess()
    signals = []
    profile = load_backend_profile("mujoco_py", PACKAGE)
    for spec in profile.operations.values():
        executable_prefix(tmp_path / "install", spec.executable)

    async def sleep(_seconds):
        if signals and signals[-1][1] == signal.SIGTERM:
            process.returncode = -signal.SIGTERM

    gateway = CliTaskGateway(
        profile,
        package_prefix_resolver=lambda _package: str(tmp_path / "install"),
        popen=lambda _argv, **_kwargs: process,
        getpgid=lambda _pid: 4201,
        killpg=lambda pgid, sig: signals.append((pgid, sig)),
        sleep=sleep,
        stop_timeout_s=0.001,
        uuid_factory=lambda: "cancel-run",
        attached_mujoco_pid=53900,
    )
    handle = asyncio.run(gateway.start_batch(request(tmp_path / "evidence")))

    result = asyncio.run(gateway.cancel(handle.run_id))

    assert signals == [(4201, signal.SIGINT), (4201, signal.SIGTERM)]
    assert result["status"] == "CANCELLED"
    with pytest.raises(TaskGatewayError, match="TASK_RUN_NOT_ACTIVE"):
        asyncio.run(gateway.cancel(handle.run_id))


def test_cancel_timeout_retains_exclusive_owner_for_safe_retry(tmp_path):
    process = FakeProcess()
    profile = load_backend_profile("mujoco_py", PACKAGE)
    for spec in profile.operations.values():
        executable_prefix(tmp_path / "install", spec.executable)
    gateway = CliTaskGateway(
        profile,
        package_prefix_resolver=lambda _package: str(tmp_path / "install"),
        popen=lambda _argv, **_kwargs: process,
        getpgid=lambda _pid: 4201,
        killpg=lambda _pgid, _sig: None,
        sleep=lambda _seconds: asyncio.sleep(0),
        monotonic=(clock := iter((0.0, 0.0, 1.0, 1.0, 2.0, 2.0))).__next__,
        stop_timeout_s=0.5,
        uuid_factory=lambda: "timeout-run",
        attached_mujoco_pid=53900,
    )
    handle = asyncio.run(gateway.start_batch(request(tmp_path / "evidence")))

    result = asyncio.run(gateway.cancel(handle.run_id))

    assert result["status"] == "CANCEL_TIMEOUT"
    with pytest.raises(TaskGatewayBusy, match="TASK_BATCH_ACTIVE"):
        asyncio.run(gateway.start_batch(request(tmp_path / "other")))


def test_capture_uses_fixed_sensor_owner_and_exclusive_directory(tmp_path):
    gateway, _child, _popen_calls, run_calls = gateway_for(tmp_path)

    result = asyncio.run(gateway.capture(TaskCaptureOwnerRequest(
        "sim-session-a", tmp_path / "evidence"
    )))

    argv, options = run_calls[0]
    assert argv[0].endswith("/lib/so101_demo_py/rgbd_sensor_capture")
    assert argv[1] == "--output-directory"
    assert Path(argv[2]).parent == tmp_path / "evidence/captures"
    assert options["shell"] is False
    assert options["check"] is False
    assert result["status"] == "SUCCEEDED"


def test_gateway_rejects_relative_or_symlink_evidence_roots(tmp_path):
    gateway, _child, popen_calls, _ = gateway_for(tmp_path)
    with pytest.raises(TaskGatewayError, match="TASK_EVIDENCE_ROOT_INVALID"):
        asyncio.run(gateway.start_batch(request(Path("relative"))))
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(TaskGatewayError, match="TASK_EVIDENCE_ROOT_INVALID"):
        asyncio.run(gateway.start_batch(request(link)))
    assert popen_calls == []


def test_task_service_gateway_surface_is_narrow():
    public_methods = {
        name
        for name, member in inspect.getmembers(CliTaskGateway, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_methods == {"start_batch", "status", "cancel", "capture"}


def test_reachability_request_uses_fixed_plan_only_owner(tmp_path):
    gateway, _child, popen_calls, _ = gateway_for(tmp_path)
    policy = tmp_path / "policy.yaml"
    policy.write_text("version: 1\n")
    base = request(tmp_path / "evidence")

    handle = asyncio.run(gateway.start_batch(TaskReachabilityOwnerRequest(
        base.simulation_session_id,
        base.points_yaml,
        base.evidence_root,
        policy,
    )))

    argv = popen_calls[0][0]
    assert argv[0].endswith("/lib/so101_demo_py/task_reachability")
    assert "--batch-id" not in argv
    assert argv[argv.index("--policy") + 1] == str(policy)
    assert handle.manifest_path.parent.name == "reachability"
