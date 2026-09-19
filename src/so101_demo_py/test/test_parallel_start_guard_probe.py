"""The bounded startup probe: helper ownership, single-flight and durable cleanup state.

Task 4 of the lightweight start guard plan. The real helper process is exercised here (not a
mock of the coordinator's decision): only the lowest-level process port is replaced, and only
for the branch the kernel cannot be asked to produce on demand.
"""

import json
import os
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

from so101_demo.parallel_batch import start_guard_probe as probe_module
from so101_demo.parallel_batch.start_guard import GuardScope, StartGuardPolicy

GPU0 = "GPU-00000000-0000-0000-0000-000000000000"


@pytest.fixture
def scope():
    return GuardScope(batch_id="lg-t4", epoch=1, owner_pid=os.getpid(),
                      owner_starttime_ticks=1, gpu_selector="INDEX:0", worker_count=4)


@pytest.fixture
def coordinator(tmp_path):
    return probe_module.ProbeCoordinator(tmp_path / "start-guard-state")


class RecordingPopen:
    """Wrap the real Popen so the test can observe the helper it must reap."""

    def __init__(self):
        self.processes = []
        self.calls = 0

    def __call__(self, argv, **kwargs):
        self.calls += 1
        process = subprocess.Popen(argv, **kwargs)
        self.processes.append(process)
        return process


class UnreapableProcess:
    """A process port that reports success forever: the kernel branch the tests need."""

    def __init__(self, pid):
        self.pid = pid
        self.terminated = False
        self.killed = False

    def poll(self):
        return None

    def wait(self, timeout=None):
        raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


def test_all_reads_are_helper_owned(coordinator, scope, monkeypatch):
    """The owner must never read the resource files; the helper process does all of it."""

    def forbidden(*args, **kwargs):
        raise AssertionError("the owner process must not read resources")

    monkeypatch.setattr("so101_demo.parallel_batch.start_guard.probe_snapshot", forbidden)
    policy = StartGuardPolicy()
    result = coordinator.check(policy, scope)
    if sys.platform == "darwin":
        assert result.status == "FAIL"
        assert result.checks["probe"].reason == "GPU_TARGET_UNAVAILABLE"
        assert result.cleanup_state == "CLEAR"
        return
    assert result.status in ("PASS", "WARN"), result
    assert result.snapshot is not None
    assert result.snapshot.gpu_uuid.startswith("GPU-")


def test_normal_path_reaps_the_helper_and_leaves_clear_state(coordinator, scope):
    recorder = RecordingPopen()
    guarded = probe_module.ProbeCoordinator(coordinator.state_path.parent, popen=recorder)
    started = time.monotonic()
    result = guarded.check(StartGuardPolicy(), scope)
    elapsed = time.monotonic() - started

    if sys.platform == "darwin":
        assert result.status == "FAIL"
        assert result.checks["probe"].reason == "GPU_TARGET_UNAVAILABLE"
    else:
        assert result.status in ("PASS", "WARN"), result
    assert result.cleanup_state == "CLEAR"
    assert recorder.calls == 1
    assert elapsed < 2.5, elapsed
    helper = recorder.processes[0]
    assert helper.poll() is not None, "the helper must be reaped"
    # Absence of a cleanup record is CLEAR; a leftover BLOCKED record would not be.
    assert coordinator.cleanup_state() == "CLEAR"
    assert not coordinator.state_path.exists() or json.loads(
        coordinator.state_path.read_text())["cleanup_state"] == "CLEAR"


def test_native_timeout_is_bounded(coordinator, scope):
    fake = UnreapableProcess(pid=os.getpid())
    guarded = probe_module.ProbeCoordinator(
        coordinator.state_path.parent, popen=lambda argv, **kwargs: fake,
        terminate_grace_s=0.2, kill_grace_s=0.2)
    policy = StartGuardPolicy(timeout_s=1.0)
    started = time.monotonic()
    result = guarded.check(policy, scope)
    elapsed = time.monotonic() - started

    assert result.status == "FAIL"
    assert result.cleanup_state == probe_module.PROBE_CLEANUP_BLOCKED
    budget = policy.timeout_s + 0.2 + 0.2 + 0.5
    assert elapsed <= budget, (elapsed, budget)
    assert fake.terminated and fake.killed
    state = json.loads(coordinator.state_path.read_text())
    assert state["cleanup_state"] == probe_module.PROBE_CLEANUP_BLOCKED
    assert state["pid"] == os.getpid()
    assert state["start_time_ticks"] > 0


def test_unreapable_blocks_retry_and_spawn(coordinator, scope):
    fake = UnreapableProcess(pid=os.getpid())
    guarded = probe_module.ProbeCoordinator(
        coordinator.state_path.parent, popen=lambda argv, **kwargs: fake)
    guarded.check(StartGuardPolicy(timeout_s=0.5), scope)

    recorder = RecordingPopen()
    retry = probe_module.ProbeCoordinator(coordinator.state_path.parent, popen=recorder)
    result = retry.check(StartGuardPolicy(), scope)
    assert result.status == "FAIL"
    assert result.checks["probe"].reason == probe_module.PROBE_CLEANUP_BLOCKED
    assert recorder.calls == 0, "no new helper may start while cleanup is blocked"


def test_singleflight_wait_counts_against_deadline(coordinator, scope):
    """A second request must fail inside its own deadline instead of queueing forever."""

    import fcntl

    holder = os.open(coordinator.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        policy = StartGuardPolicy(timeout_s=0.5)
        started = time.monotonic()
        result = coordinator.check(policy, scope)
        elapsed = time.monotonic() - started
    finally:
        fcntl.flock(holder, fcntl.LOCK_UN)
        os.close(holder)
    assert result.status == "FAIL"
    assert result.checks["probe"].reason == "PROBE_BUSY"
    assert elapsed <= 0.5 + 0.5, elapsed


def test_restart_recovers_exact_pid_starttime(coordinator):
    def write_state(state):
        coordinator._write_state_sync(state)

    # 1. a recorded helper that is already gone clears the state with a recorded disappearance
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead_pid = dead.pid
    dead.wait(timeout=10)
    write_state(probe_module.CleanupState(
        cleanup_state=probe_module.PROBE_CLEANUP_BLOCKED, pid=dead_pid,
        start_time_ticks=1, detail="stale test state"))
    assert coordinator.recover_owned_cleanup() == probe_module.CLEAR
    assert json.loads(coordinator.state_path.read_text())["cleanup_state"] == probe_module.CLEAR
    assert "gone" in json.loads(coordinator.state_path.read_text())["detail"]

    # 2. a live process whose recorded start time does not match must never be signalled
    own_identity = probe_module.read_process_identity(os.getpid())
    write_state(probe_module.CleanupState(
        cleanup_state=probe_module.PROBE_CLEANUP_BLOCKED, pid=os.getpid(),
        start_time_ticks=own_identity.start_time_ticks + 1, detail="reused pid"))
    assert coordinator.recover_owned_cleanup() == probe_module.CLEAR
    assert probe_module.read_process_identity(os.getpid()) is not None, "own process untouched"
    assert "reused" in json.loads(coordinator.state_path.read_text())["detail"]

    # 3. an exact owned match is terminated through the bounded exact-identity path
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        identity = probe_module.read_process_identity(child.pid)
        write_state(probe_module.CleanupState(
            cleanup_state=probe_module.PROBE_CLEANUP_BLOCKED, pid=child.pid,
            start_time_ticks=identity.start_time_ticks, detail="owned helper"))
        assert coordinator.recover_owned_cleanup() == probe_module.CLEAR
        child.wait(timeout=10)
        assert child.poll() is not None
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)


def test_process_identity_uses_creation_time_without_procfs(monkeypatch):
    """macOS cleanup still binds signals to a PID plus stable birth identity."""

    def missing_procfs(_path):
        raise FileNotFoundError("procfs unavailable")

    class FakeProcess:
        def __init__(self, pid):
            self.pid = pid

        def create_time(self):
            return 1234.567890

        def status(self):
            return "running"

    fake_psutil = types.SimpleNamespace(
        Process=FakeProcess,
        STATUS_ZOMBIE="zombie",
        Error=RuntimeError,
    )
    monkeypatch.setattr(Path, "read_text", missing_procfs)
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)

    identity = probe_module.read_process_identity(4321)

    assert identity == probe_module.ProcessIdentityRecord(
        pid=4321, start_time_ticks=1234567890)


def test_persistent_state_corruption_fails_closed(coordinator, scope):
    coordinator.state_path.write_text("{not json")
    recorder = RecordingPopen()
    guarded = probe_module.ProbeCoordinator(coordinator.state_path.parent, popen=recorder)
    result = guarded.check(StartGuardPolicy(), scope)
    assert result.status == "FAIL"
    assert result.checks["probe"].reason == "PROBE_STATE_CORRUPT"
    assert result.cleanup_state == probe_module.PROBE_CLEANUP_BLOCKED
    assert recorder.calls == 0
    assert coordinator.cleanup_state() == probe_module.PROBE_CLEANUP_BLOCKED


def test_helper_rejects_a_malformed_request():
    import tempfile

    read_fd, write_fd = os.pipe()
    result_read, result_write = os.pipe()
    os.write(write_fd, b"{not a request")
    os.close(write_fd)
    try:
        assert probe_module.run_helper(read_fd, result_write) == 2
        payload = json.loads(os.read(result_read, 4096).decode())
        assert "PROBE_REQUEST_INVALID" in payload["error"]
    finally:
        for descriptor in (read_fd, result_read, result_write):
            try:
                os.close(descriptor)
            except OSError:
                pass


def test_helper_entry_point_requires_explicit_fds():
    with pytest.raises(SystemExit) as excinfo:
        probe_module.main([])
    assert excinfo.value.code == 2


def test_state_root_requires_the_task_root(monkeypatch):
    monkeypatch.delenv("SO101_TASK_ROOT", raising=False)
    with pytest.raises(probe_module.CoordinatorError, match="PROBE_STATE_ROOT_UNSET"):
        probe_module.default_state_root()
    monkeypatch.setenv("SO101_TASK_ROOT", "/tmp/so101-task-root")
    assert probe_module.default_state_root() == Path("/tmp/so101-task-root/start-guard-state")


def test_coordination_key_separates_task_roots(tmp_path):
    first = probe_module.coordination_key(tmp_path / "a")
    second = probe_module.coordination_key(tmp_path / "b")
    assert first != second
    assert probe_module.coordination_key(tmp_path / "a") == first
    assert len(first) == 64


def test_helper_module_is_importable_as_a_module_entry_point():
    completed = subprocess.run([sys.executable, "-m", probe_module.HELPER_MODULE, "--help"],
                               capture_output=True, text=True, env=dict(os.environ))
    assert completed.returncode == 0, completed.stderr
    assert "--request-fd" in completed.stdout and "--result-fd" in completed.stdout
