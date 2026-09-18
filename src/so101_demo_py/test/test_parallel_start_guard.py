"""Lightweight start guard: decision model, cheap reads and rejection rules.

These tests are the Task 2 regression for the approved design
`docs/superpowers/specs/2026-09-19-so101-parallel-validation-lightweight-start-guard-design.md`:
one CPU/RAM/GPU snapshot inside a shared deadline, WARN never blocks, missing optional
information is reported as unknown, and no swap/PSI/Git read can influence the decision.
"""

import builtins
import dataclasses
import math
import os
import pathlib
import subprocess
import sys

import pytest

from so101_demo.parallel_batch.start_guard import (
    GpuDevice,
    GuardScope,
    HostPorts,
    Meminfo,
    ProbeError,
    ResourceSnapshot,
    StartGuardPolicy,
    evaluate_snapshot,
    resolve_gpu_target,
    probe_snapshot,
)

GIB = 1 << 30
GPU0 = "GPU-00000000-0000-0000-0000-000000000000"
GPU1 = "GPU-11111111-1111-1111-1111-111111111111"


@pytest.fixture
def scope():
    return GuardScope(
        batch_id="lg-t2",
        epoch=1,
        owner_pid=os.getpid(),
        owner_starttime_ticks=4242,
        gpu_selector=f"UUID:{GPU0}",
        worker_count=4,
    )


@pytest.fixture
def valid_snapshot():
    return ResourceSnapshot(
        observed_monotonic_s=1000.0,
        effective_cpuset=tuple(range(24)),
        effective_cpu_cores=24.0,
        cpu_busy_fraction=0.05,
        ram_capacity_bytes=32 * GIB,
        ram_available_bytes=16 * GIB,
        gpu_uuid=GPU0,
        gpu_total_bytes=16 * GIB,
        gpu_free_bytes=8 * GIB,
        limit_sources=("affinity", "/sys/fs/cgroup/cpu.max"),
    )


def test_equal_floor_passes(valid_snapshot, scope):
    policy = StartGuardPolicy(ram_minimum_fraction=0)
    snapshot = dataclasses.replace(
        valid_snapshot, ram_available_bytes=1 << 30, gpu_free_bytes=1 << 30)
    result = evaluate_snapshot(snapshot, policy, scope)
    assert result.status == "PASS"
    assert result.checks["ram"].status == "PASS"
    assert result.checks["gpu"].status == "PASS"
    assert result.cleanup_state == "CLEAR"


def test_one_byte_below_floor_fails(valid_snapshot, scope):
    policy = StartGuardPolicy(ram_minimum_fraction=0)
    snapshot = dataclasses.replace(
        valid_snapshot, ram_available_bytes=(1 << 30) - 1, gpu_free_bytes=1 << 30)
    result = evaluate_snapshot(snapshot, policy, scope)
    assert result.status == "FAIL"
    assert result.checks["ram"].status == "FAIL"
    assert result.checks["ram"].reason == "RAM_BELOW_MINIMUM"
    assert result.checks["ram"].observed == (1 << 30) - 1
    assert result.checks["ram"].unit == "bytes"


def test_cpu_busy_warns_without_n_prediction(valid_snapshot, scope):
    policy = StartGuardPolicy()
    busy = dataclasses.replace(valid_snapshot, cpu_busy_fraction=0.99)
    for workers in (1, 4, 8):
        result = evaluate_snapshot(busy, policy, dataclasses.replace(scope, worker_count=workers))
        assert result.status == "WARN", workers
        assert result.checks["cpu_busy"].status == "WARN"
        assert result.checks["cpu_busy"].reason == "CPU_BUSY"
        assert all(check.status != "FAIL" for check in result.checks.values())


def test_unknown_cpu_busy_warns(valid_snapshot, scope):
    policy = StartGuardPolicy()
    unknown = dataclasses.replace(valid_snapshot, cpu_busy_fraction=None)
    result = evaluate_snapshot(unknown, policy, scope)
    assert result.status == "WARN"
    assert result.checks["cpu_busy"].reason == "CPU_BUSY_UNKNOWN"
    assert result.checks["cpu_busy"].observed is None


def test_empty_cpuset_or_nonpositive_cores_fails(valid_snapshot, scope):
    policy = StartGuardPolicy()
    empty = dataclasses.replace(valid_snapshot, effective_cpuset=(), effective_cpu_cores=0.0)
    result = evaluate_snapshot(empty, policy, scope)
    assert result.status == "FAIL"
    assert result.checks["cpu_capacity"].reason == "CPU_CAPACITY_UNAVAILABLE"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"timeout_s": 0},
        {"timeout_s": -1.0},
        {"timeout_s": 60},
        {"timeout_s": 2.5},
        {"timeout_s": float("nan")},
        {"timeout_s": float("inf")},
        {"cpu_busy_warn_fraction": -0.1},
        {"cpu_busy_warn_fraction": 1.1},
        {"cpu_busy_warn_fraction": float("nan")},
        {"cpu_busy_warn_fraction": float("inf")},
        {"ram_minimum_bytes": -1},
        {"ram_minimum_bytes": 1.5},
        {"ram_minimum_bytes": True},
        {"ram_minimum_fraction": -0.1},
        {"ram_minimum_fraction": 1.5},
        {"ram_minimum_fraction": float("nan")},
        {"gpu_minimum_bytes": -1},
        {"gpu_minimum_bytes": 2.0},
        {"gpu_minimum_bytes": False},
    ],
)
def test_policy_rejects_values_outside_the_closed_range(kwargs):
    with pytest.raises(ValueError):
        StartGuardPolicy(**kwargs)


def test_policy_accepts_the_boundary_values():
    policy = StartGuardPolicy(
        timeout_s=2.0, cpu_busy_warn_fraction=0.0, ram_minimum_bytes=0,
        ram_minimum_fraction=1.0, gpu_minimum_bytes=0)
    assert policy.timeout_s == 2.0


# --------------------------------------------------------------------------------------
# probe reads: injected low-level ports (the real ones are cgroup/meminfo/NVML)
# --------------------------------------------------------------------------------------


def make_ports(tmp_path, *, cgroup_files, self_path="/self", affinity=(0, 1, 2, 3),
               meminfo=(32 * GIB, 16 * GIB), devices=None, environ=None, clock=None):
    return HostPorts(
        cgroup=FakeCgroup(files=cgroup_files, self_path=self_path),
        meminfo=Meminfo(total_bytes=meminfo[0], available_bytes=meminfo[1]),
        affinity=tuple(affinity),
        nvml=FakeNvml(devices if devices is not None else [GpuDevice(0, GPU0, 16 * GIB, 8 * GIB)]),
        environ=dict(environ or {}),
        clock=clock or (lambda: 1000.0),
    )


class FakeCgroup:
    """Minimal cgroup v2 reader over an explicit file map; absent file means absent."""

    def __init__(self, *, files, self_path):
        self._files = dict(files)
        self._self_path = self_path

    def self_path(self):
        return self._self_path

    def ancestors(self):
        parts = [p for p in self._self_path.split("/") if p]
        chain = ["/"]
        for index in range(1, len(parts) + 1):
            chain.append("/" + "/".join(parts[:index]))
        return tuple(reversed(chain))  # nearest first

    def read(self, cgroup, name):
        key = (cgroup.rstrip("/") or "/", name)
        if key not in self._files:
            return None
        value = self._files[key]
        if isinstance(value, Exception):
            raise value
        return value


class FakeNvml:
    def __init__(self, devices):
        self._devices = tuple(devices)
        self.calls = 0

    def devices(self):
        self.calls += 1
        return self._devices


def test_ancestor_memory_remaining_wins(tmp_path, scope):
    ports = make_ports(
        tmp_path,
        cgroup_files={
            ("/", "memory.max"): "max",
            ("/parent/self", "memory.max"): "max",
            ("/parent/self", "memory.current"): "1024",
            ("/parent", "memory.max"): str(4 * GIB),
            ("/parent", "memory.current"): str(4 * GIB - GIB // 2),
        },
        self_path="/parent/self",
    )
    snapshot = probe_snapshot(StartGuardPolicy(), scope, 1010.0, ports=ports)
    assert snapshot.ram_available_bytes == GIB // 2
    assert snapshot.ram_capacity_bytes == 4 * GIB

    result = evaluate_snapshot(snapshot, StartGuardPolicy(), scope)
    assert result.status == "FAIL"
    assert result.checks["ram"].reason == "RAM_BELOW_MINIMUM"
    assert result.checks["ram"].cutoff == GIB
    assert any("parent" in source for source in snapshot.limit_sources)


def test_cpu_max_inherits(tmp_path, scope):
    ports = make_ports(
        tmp_path,
        cgroup_files={
            ("/parent/self", "cpu.max"): "max 100000",
            ("/parent", "cpu.max"): "800000 100000",
            ("/parent", "cpuset.cpus.effective"): "0-7",
        },
        self_path="/parent/self",
        affinity=tuple(range(24)),
    )
    snapshot = probe_snapshot(StartGuardPolicy(), scope, 1010.0, ports=ports)
    assert snapshot.effective_cpu_cores == 8.0
    assert snapshot.effective_cpuset == tuple(range(8))
    assert any("cpu.max" in source for source in snapshot.limit_sources)
    assert evaluate_snapshot(snapshot, StartGuardPolicy(), scope).status in {"PASS", "WARN"}


def test_cpu_max_unlimited_keeps_the_cpuset_count(tmp_path, scope):
    ports = make_ports(
        tmp_path,
        cgroup_files={("/self", "cpu.max"): "max 100000"},
        self_path="/self",
        affinity=tuple(range(24)),
    )
    snapshot = probe_snapshot(StartGuardPolicy(), scope, 1010.0, ports=ports)
    assert snapshot.effective_cpu_cores == 24.0


def test_missing_controller_uses_host(tmp_path, scope):
    ports = make_ports(tmp_path, cgroup_files={}, self_path="/self", affinity=tuple(range(6)))
    snapshot = probe_snapshot(StartGuardPolicy(), scope, 1010.0, ports=ports)
    assert snapshot.effective_cpuset == tuple(range(6))
    assert snapshot.effective_cpu_cores == 6.0
    assert snapshot.ram_capacity_bytes == 32 * GIB
    assert snapshot.ram_available_bytes == 16 * GIB


def test_existing_unreadable_limit_fails(tmp_path, scope):
    ports = make_ports(
        tmp_path,
        cgroup_files={
            ("/self", "memory.max"): str(8 * GIB),
            ("/self", "memory.current"): PermissionError(13, "denied"),
        },
        self_path="/self",
    )
    with pytest.raises(ProbeError) as excinfo:
        probe_snapshot(StartGuardPolicy(), scope, 1010.0, ports=ports)
    assert excinfo.value.reason == "RAM_LIMIT_CURRENT_UNREADABLE"
    assert "/self" in str(excinfo.value)


def test_invalid_cpu_quota_fails(tmp_path, scope):
    ports = make_ports(
        tmp_path,
        cgroup_files={("/self", "cpu.max"): "garbage"},
        self_path="/self",
    )
    with pytest.raises(ProbeError) as excinfo:
        probe_snapshot(StartGuardPolicy(), scope, 1010.0, ports=ports)
    assert excinfo.value.reason == "CPU_QUOTA_INVALID"


def test_unreadable_meminfo_fails(tmp_path, scope):
    ports = dataclasses.replace(
        make_ports(tmp_path, cgroup_files={}, self_path="/self"),
        meminfo=Meminfo(total_bytes=None, available_bytes=None))
    with pytest.raises(ProbeError) as excinfo:
        probe_snapshot(StartGuardPolicy(), scope, 1010.0, ports=ports)
    assert excinfo.value.reason == "RAM_HOST_UNREADABLE"


def test_deadline_is_respected_before_reading(tmp_path, scope):
    ports = make_ports(tmp_path, cgroup_files={}, self_path="/self", clock=lambda: 1005.0)
    with pytest.raises(ProbeError) as excinfo:
        probe_snapshot(StartGuardPolicy(), scope, 1002.0, ports=ports)
    assert excinfo.value.reason == "PROBE_DEADLINE_EXCEEDED"


def test_gpu_visible_mapping_matches_uuid(tmp_path, scope):
    devices = [GpuDevice(0, GPU0, 16 * GIB, 8 * GIB), GpuDevice(1, GPU1, 24 * GIB, 20 * GIB)]

    ports = make_ports(tmp_path, cgroup_files={}, self_path="/self", devices=devices,
                       environ={"CUDA_VISIBLE_DEVICES": "1"})
    visible_only = dataclasses.replace(scope, gpu_selector=f"UUID:{GPU1}")
    snapshot = probe_snapshot(StartGuardPolicy(), visible_only, 1010.0, ports=ports)
    assert snapshot.gpu_uuid == GPU1
    assert snapshot.gpu_free_bytes == 20 * GIB
    assert ports.nvml.calls == 1

    # INDEX is an index into the visible list when CUDA_VISIBLE_DEVICES is set.
    index_scope = dataclasses.replace(scope, gpu_selector="INDEX:0")
    assert probe_snapshot(StartGuardPolicy(), index_scope, 1010.0, ports=ports).gpu_uuid == GPU1

    with pytest.raises(ProbeError) as excinfo:
        probe_snapshot(StartGuardPolicy(), scope, 1010.0, ports=ports)
    assert excinfo.value.reason == "GPU_TARGET_NOT_VISIBLE"


def test_gpu_ambiguous_mapping_fails(tmp_path, scope):
    devices = [GpuDevice(0, GPU0, 16 * GIB, 8 * GIB), GpuDevice(1, GPU1, 24 * GIB, 20 * GIB)]
    for environ in ({"CUDA_VISIBLE_DEVICES": "1,1"}, {"CUDA_VISIBLE_DEVICES": "x"},
                    {"CUDA_VISIBLE_DEVICES": "0", "NVIDIA_VISIBLE_DEVICES": "1"},
                    {"CUDA_VISIBLE_DEVICES": "7"}):
        ports = make_ports(tmp_path, cgroup_files={}, self_path="/self", devices=devices,
                           environ=environ)
        with pytest.raises(ProbeError) as excinfo:
            probe_snapshot(StartGuardPolicy(), scope, 1010.0, ports=ports)
        assert excinfo.value.reason in {"GPU_MAPPING_AMBIGUOUS", "GPU_TARGET_NOT_VISIBLE"}, environ


def test_gpu_unavailable_fails(tmp_path, scope):
    ports = dataclasses.replace(
        make_ports(tmp_path, cgroup_files={}, self_path="/self"),
        nvml=FakeNvml([]))
    with pytest.raises(ProbeError) as excinfo:
        probe_snapshot(StartGuardPolicy(), scope, 1010.0, ports=ports)
    assert excinfo.value.reason == "GPU_TARGET_UNAVAILABLE"


def test_gpu_free_below_minimum_is_not_a_missing_device(valid_snapshot, scope):
    low = dataclasses.replace(valid_snapshot, gpu_free_bytes=GIB - 1)
    result = evaluate_snapshot(low, StartGuardPolicy(), scope)
    assert result.checks["gpu"].reason == "GPU_FREE_BELOW_MINIMUM"
    assert result.checks["gpu"].observed == GIB - 1
    assert result.checks["gpu"].cutoff == GIB


def test_gpu_selector_syntax_is_validated(scope):
    for selector in ("", "GPU-0", "UUID:", "INDEX:", "INDEX:-1", "INDEX:x", "uuid:" + GPU0):
        with pytest.raises(ValueError):
            dataclasses.replace(scope, gpu_selector=selector)


def test_scope_rejects_invalid_fields(scope):
    for kwargs in ({"batch_id": ""}, {"epoch": -1}, {"owner_pid": 0},
                   {"worker_count": 0}, {"owner_starttime_ticks": -1}):
        with pytest.raises(ValueError):
            dataclasses.replace(scope, **kwargs)


@pytest.fixture
def forbidden_reads(monkeypatch):
    """Any swap/PSI/pressure file read, or any Git invocation, fails the test."""

    forbidden = ("swap", "psi", "pressure")
    real_open = builtins.open
    real_read_text = pathlib.Path.read_text
    real_read_bytes = pathlib.Path.read_bytes
    real_run = subprocess.run
    real_popen = subprocess.Popen

    def check(target):
        text = str(target).lower()
        if any(token in text for token in forbidden):
            raise AssertionError(f"forbidden resource read: {target}")

    def guarded_open(file, *args, **kwargs):
        check(file)
        return real_open(file, *args, **kwargs)

    def guarded_read_text(self, *args, **kwargs):
        check(self)
        return real_read_text(self, *args, **kwargs)

    def guarded_read_bytes(self, *args, **kwargs):
        check(self)
        return real_read_bytes(self, *args, **kwargs)

    def guarded_run(argv, *args, **kwargs):
        if isinstance(argv, (list, tuple)) and argv and "git" in str(argv[0]):
            raise AssertionError(f"forbidden Git invocation: {argv}")
        return real_run(argv, *args, **kwargs)

    def guarded_popen(argv, *args, **kwargs):
        if isinstance(argv, (list, tuple)) and argv and "git" in str(argv[0]):
            raise AssertionError(f"forbidden Git invocation: {argv}")
        return real_popen(argv, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(pathlib.Path, "read_text", guarded_read_text)
    monkeypatch.setattr(pathlib.Path, "read_bytes", guarded_read_bytes)
    monkeypatch.setattr(subprocess, "run", guarded_run)
    monkeypatch.setattr(subprocess, "Popen", guarded_popen)
    return forbidden


def test_guard_decides_without_readingswap_or_psi(forbidden_reads, tmp_path, scope):
    ports = make_ports(tmp_path, cgroup_files={}, self_path="/self")
    snapshot = probe_snapshot(StartGuardPolicy(), scope, 1010.0, ports=ports)
    assert evaluate_snapshot(snapshot, StartGuardPolicy(), scope).status in {"PASS", "WARN"}


def test_guard_source_has_no_swap_or_psi_reference(forbidden_reads):
    import so101_demo.parallel_batch.start_guard as module

    text = pathlib.Path(module.__file__).read_text().lower()
    for token in forbidden_reads:
        assert token not in text, token


def test_real_host_probe_returns_a_usable_snapshot(scope):
    """The real cgroup/meminfo/NVML reads work on this host without any deadline breach."""
    policy = StartGuardPolicy(timeout_s=2.0)
    clock = __import__("time").monotonic
    started = clock()
    selector = "INDEX:0"
    snapshot = probe_snapshot(policy, dataclasses.replace(scope, gpu_selector=selector),
                              started + policy.timeout_s)
    elapsed = clock() - started
    assert elapsed < policy.timeout_s
    assert snapshot.effective_cpuset, snapshot
    assert snapshot.effective_cpu_cores > 0
    assert snapshot.ram_capacity_bytes > 0
    assert snapshot.ram_available_bytes > 0
    assert snapshot.gpu_uuid.startswith("GPU-")
    assert snapshot.gpu_total_bytes > 0
    result = evaluate_snapshot(snapshot, policy, scope)
    assert result.status in {"PASS", "WARN"}, result
    assert result.completed_monotonic_s >= result.started_monotonic_s


def test_busy_window_default_is_100ms():
    import so101_demo.parallel_batch.start_guard as module

    assert module.CPU_BUSY_WINDOW_S == 0.1
    assert module.host_ports().busy_window_s == module.CPU_BUSY_WINDOW_S


def test_resolve_gpu_target_is_pure(scope):
    devices = (GpuDevice(0, GPU0, 16 * GIB, 8 * GIB),)
    target = resolve_gpu_target("INDEX:0", devices, {})
    assert target.uuid == GPU0
    with pytest.raises(ProbeError):
        resolve_gpu_target("INDEX:3", devices, {})
