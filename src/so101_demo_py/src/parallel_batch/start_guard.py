"""Lightweight start guard: one CPU/RAM/GPU snapshot inside a shared deadline.

The approved design (2026-09-19) replaces the per-N certified budget chain with a single
cheap pre-start check. Everything here is either a closed data model, a pure decision, or a
low-level read against cgroup v2, ``/proc`` and NVML. No paging or memory-stall counter is
consulted, no forecast scales with the worker count, and nothing is read from Git.

The blocking reads are meant to be executed by a bounded helper process (Task 4): this
module only exposes them with an injectable low-level port so the helper, the CLI and the
tests all use the same code path.
"""

from __future__ import annotations

import ctypes
import math
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Protocol, Sequence

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

#: Two counters 100 ms apart, per the approved design. It is a port default so that unit
#: tests can drive the same code path without a real delay.
CPU_BUSY_WINDOW_S = 0.100

_CGROUP_ROOT = Path("/sys/fs/cgroup")
_MEMINFO_PATH = Path("/proc/meminfo")
_PROC_STAT_PATH = Path("/proc/stat")


class ProbeError(RuntimeError):
    """A required read failed or the deadline was reached; the caller must report FAIL."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


def _require_finite_number(name: str, value: object, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a real number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    if number < minimum or number > maximum:
        raise ValueError(f"{name} must be within [{minimum}, {maximum}]")
    return number


def _require_bytes(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be a non-negative int")
    if value < 0:
        raise ValueError(f"{name} must be a non-negative int")
    return value


def _require_non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative int")
    return value


def _require_positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive int")
    return value


_IDENTIFIER_OK = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


def _require_identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value[0] in "-_":
        raise ValueError(f"{name} must be an identifier")
    if any(ch not in _IDENTIFIER_OK for ch in value):
        raise ValueError(f"{name} must be an identifier")
    return value


@dataclass(frozen=True)
class StartGuardPolicy:
    """Closed policy. Configuration cannot enlarge the deadline past the design's 2 s.

    ``mps_minimum_headroom_bytes`` belongs to the schema-v4 Darwin combination only. It is a
    fixed positive byte count that blocks a plainly short-of-memory start; it does not scale
    with the worker count, the model count or the point count, and it is not a capacity
    certification. It stays ``None`` for every other platform, so a v3 document cannot carry
    an MPS threshold and a Linux v4 document cannot silently acquire one.
    """

    timeout_s: float = 2.0
    cpu_busy_warn_fraction: float = 0.90
    ram_minimum_bytes: int = 1 << 30
    ram_minimum_fraction: float = 0.05
    gpu_minimum_bytes: int = 1 << 30
    mps_minimum_headroom_bytes: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "timeout_s", _require_finite_number(
            "timeout_s", self.timeout_s, minimum=1e-6, maximum=2.0))
        object.__setattr__(self, "cpu_busy_warn_fraction", _require_finite_number(
            "cpu_busy_warn_fraction", self.cpu_busy_warn_fraction, minimum=0.0, maximum=1.0))
        object.__setattr__(self, "ram_minimum_bytes", _require_bytes(
            "ram_minimum_bytes", self.ram_minimum_bytes))
        object.__setattr__(self, "ram_minimum_fraction", _require_finite_number(
            "ram_minimum_fraction", self.ram_minimum_fraction, minimum=0.0, maximum=1.0))
        object.__setattr__(self, "gpu_minimum_bytes", _require_bytes(
            "gpu_minimum_bytes", self.gpu_minimum_bytes))
        if self.mps_minimum_headroom_bytes is not None:
            object.__setattr__(self, "mps_minimum_headroom_bytes", _require_positive_bytes(
                "mps_minimum_headroom_bytes", self.mps_minimum_headroom_bytes))


def _require_positive_bytes(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be a positive int")
    if value <= 0:
        raise ValueError(f"{name} must be a positive int")
    return value


def _require_gpu_selector(value: object) -> str:
    if not isinstance(value, str) or ":" not in value:
        raise ValueError("gpu_selector must be UUID:<uuid> or INDEX:<index>")
    kind, _, body = value.partition(":")
    if kind == "UUID":
        if not body.startswith("GPU-") or len(body) <= len("GPU-"):
            raise ValueError("gpu_selector UUID must be a GPU- UUID")
        return value
    if kind == "INDEX":
        if not body.isdigit():
            raise ValueError("gpu_selector INDEX must be a non-negative integer")
        return value
    raise ValueError("gpu_selector must be UUID:<uuid> or INDEX:<index>")


@dataclass(frozen=True)
class GuardScope:
    """The real owner/epoch identity a guard result belongs to."""

    batch_id: str
    epoch: int
    owner_pid: int
    owner_starttime_ticks: int
    gpu_selector: str
    worker_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "batch_id", _require_identifier("batch_id", self.batch_id))
        object.__setattr__(self, "epoch", _require_non_negative_int("epoch", self.epoch))
        object.__setattr__(self, "owner_pid", _require_positive_int("owner_pid", self.owner_pid))
        object.__setattr__(self, "owner_starttime_ticks", _require_non_negative_int(
            "owner_starttime_ticks", self.owner_starttime_ticks))
        object.__setattr__(self, "gpu_selector", _require_gpu_selector(self.gpu_selector))
        object.__setattr__(self, "worker_count", _require_positive_int(
            "worker_count", self.worker_count))


@dataclass(frozen=True)
class GpuDevice:
    index: int
    uuid: str
    total_bytes: int
    free_bytes: int


@dataclass(frozen=True)
class ResourceSnapshot:
    observed_monotonic_s: float
    effective_cpuset: tuple[int, ...]
    effective_cpu_cores: float
    cpu_busy_fraction: float | None
    ram_capacity_bytes: int
    ram_available_bytes: int
    gpu_uuid: str
    gpu_total_bytes: int
    gpu_free_bytes: int
    limit_sources: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_monotonic_s", _require_finite_number(
            "observed_monotonic_s", self.observed_monotonic_s, minimum=0.0, maximum=math.inf))
        cpuset = tuple(self.effective_cpuset)
        for cpu in cpuset:
            _require_non_negative_int("effective_cpuset entry", cpu)
        object.__setattr__(self, "effective_cpuset", cpuset)
        object.__setattr__(self, "effective_cpu_cores", _require_finite_number(
            "effective_cpu_cores", self.effective_cpu_cores, minimum=0.0, maximum=math.inf))
        if self.cpu_busy_fraction is not None:
            object.__setattr__(self, "cpu_busy_fraction", _require_finite_number(
                "cpu_busy_fraction", self.cpu_busy_fraction, minimum=0.0, maximum=1.0))
        for name in ("ram_capacity_bytes", "ram_available_bytes", "gpu_total_bytes",
                     "gpu_free_bytes"):
            object.__setattr__(self, name, _require_bytes(name, getattr(self, name)))
        if not isinstance(self.gpu_uuid, str):
            raise ValueError("gpu_uuid must be a string")
        object.__setattr__(self, "limit_sources", tuple(str(s) for s in self.limit_sources))


@dataclass(frozen=True)
class GuardCheck:
    status: str
    reason: str
    observed: int | float | str | None
    cutoff: int | float | None
    unit: str

    def __post_init__(self) -> None:
        if self.status not in (PASS, WARN, FAIL):
            raise ValueError("status must be PASS/WARN/FAIL")
        if not self.unit:
            raise ValueError("unit is required")


@dataclass(frozen=True)
class GuardResult:
    scope: GuardScope
    status: str
    started_monotonic_s: float
    completed_monotonic_s: float
    checks: dict[str, GuardCheck]
    snapshot: ResourceSnapshot | None
    cleanup_state: str

    def __post_init__(self) -> None:
        if self.status not in (PASS, WARN, FAIL):
            raise ValueError("status must be PASS/WARN/FAIL")
        if self.cleanup_state not in ("CLEAR", "PROBE_CLEANUP_BLOCKED"):
            raise ValueError("cleanup_state must be CLEAR/PROBE_CLEANUP_BLOCKED")
        if self.completed_monotonic_s < self.started_monotonic_s:
            raise ValueError("completed_monotonic_s must not precede started_monotonic_s")


# --------------------------------------------------------------------------------------
# low-level ports
# --------------------------------------------------------------------------------------


class CgroupReader(Protocol):
    def self_path(self) -> str: ...

    def ancestors(self) -> tuple[str, ...]: ...

    def read(self, cgroup: str, name: str) -> str | None: ...


class NvmlPort(Protocol):
    def devices(self) -> tuple[GpuDevice, ...]: ...


@dataclass(frozen=True)
class Meminfo:
    total_bytes: int | None
    available_bytes: int | None


@dataclass(frozen=True)
class HostPorts:
    """The lowest-level seams. ``host_ports()`` builds the real ones.

    ``busy_window_s`` defaults to 0 so a test can drive the busy-counter path without a real
    delay; the production factory uses :data:`CPU_BUSY_WINDOW_S`.
    """

    cgroup: CgroupReader
    meminfo: Meminfo
    affinity: tuple[int, ...]
    nvml: NvmlPort
    environ: Mapping[str, str] = field(default_factory=dict)
    clock: object = time.monotonic
    busy_window_s: float = 0.0
    proc_stat: Path = _PROC_STAT_PATH


class SysfsCgroupReader:
    """Real cgroup v2 reader: own scope plus every visible ancestor."""

    def __init__(self, root: Path = _CGROUP_ROOT, self_path: str | None = None) -> None:
        self._root = Path(root)
        self._self_path = self_path

    def self_path(self) -> str:
        if self._self_path is None:
            self._self_path = _read_own_cgroup_path()
        return self._self_path

    def ancestors(self) -> tuple[str, ...]:
        parts = [p for p in self.self_path().split("/") if p]
        chain = ["/"]
        for index in range(1, len(parts) + 1):
            chain.append("/" + "/".join(parts[:index]))
        return tuple(reversed(chain))  # nearest first, root last

    def read(self, cgroup: str, name: str) -> str | None:
        path = self._root / cgroup.lstrip("/") / name
        try:
            return path.read_text().strip()
        except FileNotFoundError:
            return None


def _read_own_cgroup_path() -> str:
    try:
        document = Path("/proc/self/cgroup").read_text()
    except (OSError, UnicodeError):
        return "/"
    for line in document.splitlines():
        fields = line.split(":", 2)
        if len(fields) == 3 and fields[0] == "0":
            return fields[2].strip() or "/"
    return "/"


class CtypesNvmlPort:
    """Whole-device NVML reads through libnvidia-ml; no per-process accounting."""

    _MEMORY_INFO_FIELDS = (("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong),
                           ("used", ctypes.c_ulonglong))

    def __init__(self, library_name: str = "libnvidia-ml.so.1") -> None:
        self._library_name = library_name
        self._library = None

    def _load(self):
        if self._library is None:
            try:
                library = ctypes.CDLL(self._library_name)
            except OSError as exc:
                raise ProbeError("GPU_TARGET_UNAVAILABLE", str(exc)) from exc
            if library.nvmlInit_v2() != 0:
                raise ProbeError("GPU_TARGET_UNAVAILABLE", "nvmlInit_v2")
            self._library = library
        return self._library

    def devices(self) -> tuple[GpuDevice, ...]:
        library = self._load()
        count = ctypes.c_uint(0)
        if library.nvmlDeviceGetCount_v2(ctypes.byref(count)) != 0:
            raise ProbeError("GPU_TARGET_UNAVAILABLE", "nvmlDeviceGetCount_v2")
        memory_type = type("MemoryInfo", (ctypes.Structure,),
                           {"_fields_": list(self._MEMORY_INFO_FIELDS)})
        devices = []
        for index in range(count.value):
            handle = ctypes.c_void_p()
            if library.nvmlDeviceGetHandleByIndex_v2(index, ctypes.byref(handle)) != 0:
                raise ProbeError("GPU_TARGET_UNAVAILABLE", f"nvmlDeviceGetHandleByIndex_v2:{index}")
            uuid_buffer = ctypes.create_string_buffer(96)
            if library.nvmlDeviceGetUUID(handle, uuid_buffer, ctypes.c_uint(96)) != 0:
                raise ProbeError("GPU_TARGET_UNAVAILABLE", f"nvmlDeviceGetUUID:{index}")
            memory = memory_type()
            if library.nvmlDeviceGetMemoryInfo(handle, ctypes.byref(memory)) != 0:
                raise ProbeError("GPU_TARGET_UNAVAILABLE", f"nvmlDeviceGetMemoryInfo:{index}")
            devices.append(GpuDevice(index=index, uuid=uuid_buffer.value.decode("utf-8", "replace"),
                                     total_bytes=int(memory.total), free_bytes=int(memory.free)))
        return tuple(devices)


def read_meminfo(path: Path = _MEMINFO_PATH) -> Meminfo:
    try:
        text = Path(path).read_text()
    except OSError:
        if sys.platform != "darwin":
            return Meminfo(total_bytes=None, available_bytes=None)
        return _read_macos_meminfo()
    values: dict[str, int] = {}
    for line in text.splitlines():
        fields = line.split(":")
        if len(fields) != 2:
            continue
        parts = fields[1].split()
        if not parts or not parts[0].isdigit():
            continue
        values[fields[0].strip()] = int(parts[0]) * 1024
    return Meminfo(total_bytes=values.get("MemTotal"), available_bytes=values.get("MemAvailable"))


def _read_macos_meminfo() -> Meminfo:
    try:
        try:
            total_bytes = int(os.sysconf("SC_PAGE_SIZE")) * int(
                os.sysconf("SC_PHYS_PAGES")
            )
        except (OSError, ValueError):
            total_result = subprocess.run(
                ["/usr/sbin/sysctl", "-n", "hw.memsize"],
                check=True,
                capture_output=True,
                text=True,
                timeout=0.5,
            )
            total_bytes = int(total_result.stdout.strip())
        vm_result = subprocess.run(
            ["/usr/bin/vm_stat"],
            check=True,
            capture_output=True,
            text=True,
            timeout=0.5,
        )
        page_match = re.search(r"page size of ([0-9]+) bytes", vm_result.stdout)
        if page_match is None:
            raise ValueError("vm_stat page size missing")
        page_size = int(page_match.group(1))
        reclaimable = 0
        wanted = {"free", "inactive", "speculative", "purgeable"}
        for name, count in re.findall(
            r"^Pages ([A-Za-z ]+):\s+([0-9]+)\.$", vm_result.stdout, re.MULTILINE
        ):
            if name.strip().lower() in wanted:
                reclaimable += int(count)
        available_bytes = min(total_bytes, reclaimable * page_size)
        if total_bytes <= 0 or available_bytes < 0:
            raise ValueError("invalid macOS memory counters")
    except (OSError, ValueError, subprocess.SubprocessError):
        return Meminfo(total_bytes=None, available_bytes=None)
    return Meminfo(total_bytes=total_bytes, available_bytes=available_bytes)


def _host_affinity() -> tuple[int, ...]:
    getter = getattr(os, "sched_getaffinity", None)
    if getter is not None:
        return tuple(sorted(getter(0)))
    count = os.cpu_count()
    return tuple(range(count)) if count is not None and count > 0 else ()


def host_ports() -> HostPorts:
    return HostPorts(
        cgroup=SysfsCgroupReader(),
        meminfo=read_meminfo(),
        affinity=_host_affinity(),
        nvml=CtypesNvmlPort(),
        environ=dict(os.environ),
        clock=time.monotonic,
        busy_window_s=CPU_BUSY_WINDOW_S,
    )


# --------------------------------------------------------------------------------------
# GPU target resolution
# --------------------------------------------------------------------------------------


def _visible_indices(environ: Mapping[str, str], devices: Sequence[GpuDevice]):
    """Return the visible physical indices, or None when the host list applies."""

    cuda = environ.get("CUDA_VISIBLE_DEVICES")
    nvidia = environ.get("NVIDIA_VISIBLE_DEVICES")
    if cuda is not None and nvidia is not None and cuda.strip() != nvidia.strip():
        raise ProbeError("GPU_MAPPING_AMBIGUOUS", "CUDA_VISIBLE_DEVICES disagrees with "
                                                  "NVIDIA_VISIBLE_DEVICES")
    raw = cuda if cuda is not None else nvidia
    if raw is None:
        return None
    text = raw.strip()
    if text in ("", "-1"):
        return ()
    by_uuid = {device.uuid: device.index for device in devices}
    indices = []
    for token in text.split(","):
        token = token.strip()
        if not token:
            raise ProbeError("GPU_MAPPING_AMBIGUOUS", raw)
        if token.lstrip("-").isdigit():
            index = int(token)
            if index < 0:
                return ()
            indices.append(index)
        elif token in by_uuid:
            indices.append(by_uuid[token])
        else:
            raise ProbeError("GPU_MAPPING_AMBIGUOUS", raw)
    if len(set(indices)) != len(indices):
        raise ProbeError("GPU_MAPPING_AMBIGUOUS", raw)
    return tuple(indices)


def resolve_gpu_target(selector: str, devices: Sequence[GpuDevice],
                       environ: Mapping[str, str]) -> GpuDevice:
    kind, _, body = selector.partition(":")
    devices = tuple(devices)
    if not devices:
        raise ProbeError("GPU_TARGET_UNAVAILABLE", "no NVML device")
    visible = _visible_indices(environ, devices)
    pool = devices if visible is None else tuple(d for d in devices if d.index in visible)
    if kind == "UUID":
        matches = [d for d in pool if d.uuid == body]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise ProbeError("GPU_TARGET_NOT_VISIBLE", body)
        raise ProbeError("GPU_MAPPING_AMBIGUOUS", body)
    position = int(body)
    if visible is None:
        matches = [d for d in devices if d.index == position]
    else:
        if position >= len(visible):
            raise ProbeError("GPU_TARGET_NOT_VISIBLE", str(position))
        matches = [d for d in devices if d.index == visible[position]]
    if len(matches) == 1:
        return matches[0]
    raise ProbeError("GPU_TARGET_NOT_VISIBLE", str(position))


# --------------------------------------------------------------------------------------
# the cheap reads
# --------------------------------------------------------------------------------------


def _parse_cpu_list(text: str) -> tuple[int, ...]:
    cpus: set[int] = set()
    for token in text.strip().split(","):
        token = token.strip()
        if not token:
            raise ProbeError("CPU_CPUSET_INVALID", text)
        if "-" in token:
            low, _, high = token.partition("-")
            if not low.isdigit() or not high.isdigit():
                raise ProbeError("CPU_CPUSET_INVALID", text)
            if int(high) < int(low):
                raise ProbeError("CPU_CPUSET_INVALID", text)
            cpus.update(range(int(low), int(high) + 1))
        elif token.isdigit():
            cpus.add(int(token))
        else:
            raise ProbeError("CPU_CPUSET_INVALID", text)
    return tuple(sorted(cpus))


def _read_cgroup(reader: CgroupReader, cgroup: str, name: str, reason: str) -> str | None:
    try:
        return reader.read(cgroup, name)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ProbeError(reason, f"{cgroup}/{name}") from exc


def _read_cpu(ports: HostPorts, clock) -> tuple[tuple[int, ...], float, list[str]]:
    sources = ["affinity"]
    affinity = tuple(sorted(ports.affinity))
    if not affinity:
        raise ProbeError("CPU_CAPACITY_UNAVAILABLE", "empty affinity")
    cpuset = affinity
    quota_cores: float | None = None
    for cgroup in ports.cgroup.ancestors():
        raw = _read_cgroup(ports.cgroup, cgroup, "cpuset.cpus.effective", "CPU_CPUSET_UNREADABLE")
        if raw:
            parsed = _parse_cpu_list(raw)
            if parsed:
                cpuset = tuple(sorted(set(cpuset) & set(parsed)))
                sources.append(f"cpuset.cpus.effective:{cgroup}")
        quota = _read_cgroup(ports.cgroup, cgroup, "cpu.max", "CPU_QUOTA_UNREADABLE")
        if quota is None:
            continue
        fields = quota.split()
        if len(fields) != 2:
            raise ProbeError("CPU_QUOTA_INVALID", f"{cgroup}/cpu.max: {quota}")
        raw_quota, raw_period = fields
        if raw_quota == "max":
            continue
        try:
            quota_us = int(raw_quota)
            period_us = int(raw_period)
        except ValueError as exc:
            raise ProbeError("CPU_QUOTA_INVALID", f"{cgroup}/cpu.max: {quota}") from exc
        if quota_us <= 0 or period_us <= 0:
            raise ProbeError("CPU_QUOTA_INVALID", f"{cgroup}/cpu.max: {quota}")
        cores = quota_us / period_us
        quota_cores = cores if quota_cores is None else min(quota_cores, cores)
        sources.append(f"cpu.max:{cgroup}")
    cores = float(len(cpuset))
    if quota_cores is not None:
        cores = min(cores, quota_cores)
    return cpuset, cores, sources


def _read_ram(ports: HostPorts) -> tuple[int, int, list[str]]:
    if ports.meminfo.total_bytes is None or ports.meminfo.available_bytes is None:
        raise ProbeError("RAM_HOST_UNREADABLE", str(_MEMINFO_PATH))
    capacity = int(ports.meminfo.total_bytes)
    available = int(ports.meminfo.available_bytes)
    sources = ["host-meminfo"]
    for cgroup in ports.cgroup.ancestors():
        raw = _read_cgroup(ports.cgroup, cgroup, "memory.max", "RAM_LIMIT_UNREADABLE")
        if raw is None or raw == "max":
            continue
        try:
            limit = int(raw)
        except ValueError as exc:
            raise ProbeError("RAM_LIMIT_INVALID", f"{cgroup}/memory.max: {raw}") from exc
        if limit < 0:
            raise ProbeError("RAM_LIMIT_INVALID", f"{cgroup}/memory.max: {raw}")
        current_raw = _read_cgroup(ports.cgroup, cgroup, "memory.current",
                                   "RAM_LIMIT_CURRENT_UNREADABLE")
        if current_raw is None:
            raise ProbeError("RAM_LIMIT_CURRENT_UNREADABLE", cgroup)
        try:
            current = int(current_raw)
        except ValueError as exc:
            raise ProbeError("RAM_LIMIT_CURRENT_INVALID", f"{cgroup}/memory.current") from exc
        capacity = min(capacity, limit)
        available = min(available, max(0, limit - current))
        sources.append(f"memory.max:{cgroup}")
    return capacity, available, sources


def _read_cpu_busy(ports: HostPorts, clock, deadline_monotonic_s: float) -> float | None:
    window = float(ports.busy_window_s or 0.0)
    if clock() + window > deadline_monotonic_s:
        return None
    try:
        first = _read_proc_stat_totals(ports.proc_stat)
        if window > 0:
            time.sleep(window)
        second = _read_proc_stat_totals(ports.proc_stat)
    except (OSError, ValueError):
        return None
    if first is None or second is None:
        return None
    total_delta = second[1] - first[1]
    idle_delta = second[0] - first[0]
    if total_delta <= 0 or idle_delta < 0:
        return None
    busy = 1.0 - (idle_delta / total_delta)
    if not math.isfinite(busy):
        return None
    return min(1.0, max(0.0, busy))


def _read_proc_stat_totals(path: Path) -> tuple[int, int] | None:
    for line in Path(path).read_text().splitlines():
        if not line.startswith("cpu "):
            continue
        fields = [int(value) for value in line.split()[1:] if value.isdigit()]
        if len(fields) < 4:
            return None
        idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
        return idle, sum(fields)
    return None


def probe_snapshot(policy: StartGuardPolicy, scope: GuardScope, deadline_monotonic_s: float, *,
                   ports: HostPorts | None = None) -> ResourceSnapshot:
    """Read one CPU/RAM/GPU snapshot; raise :class:`ProbeError` on any required failure."""

    if not isinstance(policy, StartGuardPolicy):
        raise ValueError("policy must be a StartGuardPolicy")
    if not isinstance(scope, GuardScope):
        raise ValueError("scope must be a GuardScope")
    active = ports or host_ports()
    clock = active.clock or time.monotonic
    if clock() > deadline_monotonic_s:
        raise ProbeError("PROBE_DEADLINE_EXCEEDED", f"{clock():.3f} > {deadline_monotonic_s:.3f}")

    cpuset, cores, sources = _read_cpu(active, clock)
    if clock() > deadline_monotonic_s:
        raise ProbeError("PROBE_DEADLINE_EXCEEDED", "after cpu read")
    ram_capacity, ram_available, ram_sources = _read_ram(active)
    if clock() > deadline_monotonic_s:
        raise ProbeError("PROBE_DEADLINE_EXCEEDED", "after ram read")
    busy = _read_cpu_busy(active, clock, deadline_monotonic_s)
    target = resolve_gpu_target(scope.gpu_selector, active.nvml.devices(), active.environ)
    sources = list(sources) + list(ram_sources)
    return ResourceSnapshot(
        observed_monotonic_s=clock(),
        effective_cpuset=cpuset,
        effective_cpu_cores=cores,
        cpu_busy_fraction=busy,
        ram_capacity_bytes=ram_capacity,
        ram_available_bytes=ram_available,
        gpu_uuid=target.uuid,
        gpu_total_bytes=target.total_bytes,
        gpu_free_bytes=target.free_bytes,
        limit_sources=tuple(sources),
    )


# --------------------------------------------------------------------------------------
# the pure decision
# --------------------------------------------------------------------------------------


def evaluate_snapshot(snapshot: ResourceSnapshot, policy: StartGuardPolicy,
                      scope: GuardScope, *, started_monotonic_s: float | None = None,
                      completed_monotonic_s: float | None = None) -> GuardResult:
    """PASS/WARN/FAIL for one snapshot. WARN never blocks startup; FAIL always does."""

    if not isinstance(snapshot, ResourceSnapshot):
        raise ValueError("snapshot must be a ResourceSnapshot")
    if not isinstance(policy, StartGuardPolicy) or not isinstance(scope, GuardScope):
        raise ValueError("policy and scope must be the closed models")

    checks: dict[str, GuardCheck] = {}

    if not snapshot.effective_cpuset or not math.isfinite(snapshot.effective_cpu_cores) \
            or snapshot.effective_cpu_cores <= 0:
        checks["cpu_capacity"] = GuardCheck(
            FAIL, "CPU_CAPACITY_UNAVAILABLE", snapshot.effective_cpu_cores, None, "cores")
    else:
        checks["cpu_capacity"] = GuardCheck(
            PASS, "CPU_CAPACITY_OK", snapshot.effective_cpu_cores, None, "cores")

    busy = snapshot.cpu_busy_fraction
    if busy is None:
        checks["cpu_busy"] = GuardCheck(
            WARN, "CPU_BUSY_UNKNOWN", None, policy.cpu_busy_warn_fraction, "fraction")
    elif busy > policy.cpu_busy_warn_fraction:
        checks["cpu_busy"] = GuardCheck(
            WARN, "CPU_BUSY", busy, policy.cpu_busy_warn_fraction, "fraction")
    else:
        checks["cpu_busy"] = GuardCheck(
            PASS, "CPU_BUSY_OK", busy, policy.cpu_busy_warn_fraction, "fraction")

    floor = max(policy.ram_minimum_bytes,
                int(math.floor(policy.ram_minimum_fraction * snapshot.ram_capacity_bytes)))
    if snapshot.ram_available_bytes < floor:
        checks["ram"] = GuardCheck(
            FAIL, "RAM_BELOW_MINIMUM", snapshot.ram_available_bytes, floor, "bytes")
    else:
        checks["ram"] = GuardCheck(
            PASS, "RAM_OK", snapshot.ram_available_bytes, floor, "bytes")

    if not snapshot.gpu_uuid:
        checks["gpu"] = GuardCheck(FAIL, "GPU_TARGET_UNAVAILABLE", None,
                                   policy.gpu_minimum_bytes, "bytes")
    elif snapshot.gpu_free_bytes < policy.gpu_minimum_bytes:
        checks["gpu"] = GuardCheck(FAIL, "GPU_FREE_BELOW_MINIMUM", snapshot.gpu_free_bytes,
                                   policy.gpu_minimum_bytes, "bytes")
    else:
        checks["gpu"] = GuardCheck(PASS, "GPU_OK", snapshot.gpu_free_bytes,
                                   policy.gpu_minimum_bytes, "bytes")

    statuses = {check.status for check in checks.values()}
    status = FAIL if FAIL in statuses else (WARN if WARN in statuses else PASS)
    moment = snapshot.observed_monotonic_s
    started = moment if started_monotonic_s is None else started_monotonic_s
    completed = moment if completed_monotonic_s is None else completed_monotonic_s
    if completed < started:
        completed = started
    return GuardResult(scope=scope, status=status, started_monotonic_s=started,
                       completed_monotonic_s=completed, checks=checks, snapshot=snapshot,
                       cleanup_state="CLEAR")
