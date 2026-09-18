"""Owned measurement resources: delegated cgroup, real child, sampler and cleanup.

Every capability used here is verified before it is used: the cgroup must expose the
cpu and memory controllers and be writable, the written limits are read back, the
sampler is a real 50ms-lossless loop over the owned cgroup plus whole-device NVML, the
abort path sends a real signal to the owned process group and the cleanup verifies the
containment is empty before it is removed. Offline tests replace only these low-level
host ports with hermetic equivalents; they never replace the safety decisions.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from ..runtime.parallel_ipc import (
    IpcError, require_transport_basename, transport_address)
from .contracts import ContractError
from .measurement_control import (
    MeasurementControl, MeasurementOwnerBinding, ProcessIdentity)

_CGROUP_ROOT = Path("/sys/fs/cgroup")
_DEFAULT_CPU_PERIOD_US = 100000
_MAXIMUM_CONTROL_SOCKET_BYTES = 108
_EVENT_NAMES = (
    "BASELINE_START", "BASELINE_END", "LIMITS_APPLIED", "WORKLOAD_SPAWN", "WORKLOAD_EXIT",
    "SAMPLING_START", "SAMPLING_STOP", "CLEANUP_START", "CLEANUP_END", "QUIET_END",
    "ABORT_LATCHED", "CAPACITY_REFUSED",
)


def own_cgroup_path() -> Path:
    """The cgroup of this process, read from the kernel (no assumption about systemd)."""

    try:
        entry = next(
            line.split("::", 1)[1]
            for line in Path("/proc/self/cgroup").read_text().splitlines()
            if line.startswith("0::")
        )
    except (OSError, StopIteration) as error:
        raise ContractError("MEASUREMENT_CAPABILITY_MISSING: cgroup") from error
    return _CGROUP_ROOT / entry.strip().lstrip("/")


def _advance_sampling_grid(*, now: float, deadline: float,
                           interval_s: float) -> tuple[float, float]:
    """Return the next sampling deadline and the delay to it, on a drift-free grid.

    Waiting the interval *after* each sample makes the period the sum of the sampling work
    and the interval, so a sample slower than the interval alone can exceed the maximum
    sample gap. The grid keeps the period at the interval while the work fits inside it and
    degrades to the work itself when it does not, so a genuinely starved sampler still
    breaches the gap and latches.
    """

    step = max(float(interval_s), 0.0)
    target = float(deadline) + step
    if target < float(now):
        target = float(now)
    return target, max(0.0, target - float(now))


class OwnedCgroupV2:
    """One measurement-owned cgroup with verified limits and a verified empty cleanup."""

    def __init__(self, *, path: Path) -> None:
        self.path = Path(path)
        self.limits: Mapping[str, int] | None = None

    @classmethod
    def create(cls, *, parent: Path, name: str) -> "OwnedCgroupV2":
        if not isinstance(name, str) or not name or "/" in name or len(name) > 96:
            raise ContractError("CGROUP_NAME")
        node = Path(parent) / name
        try:
            node.mkdir(mode=0o700)
        except OSError as error:
            raise ContractError("MEASUREMENT_CAPABILITY_MISSING: cgroup_create") from error
        cgroup = cls(path=node)
        cgroup.require_delegated()
        return cgroup

    def _read(self, name: str, default: str | None = None) -> str:
        try:
            return (self.path / name).read_text().strip()
        except OSError as error:
            if default is not None:
                return default
            raise ContractError(f"MEASUREMENT_CAPABILITY_MISSING: cgroup_{name}") from error

    def require_delegated(self, *, required: Sequence[str] = ("cpu", "memory")) -> None:
        controllers = self._read("cgroup.controllers", "").split()
        missing = [name for name in required if name not in controllers]
        if missing:
            raise ContractError(
                f"MEASUREMENT_CAPABILITY_MISSING: cgroup_controllers {sorted(missing)!r}")
        # cgroup v2 exposes the accounting file cpu.stat as mode 0444 even inside a
        # delegated subtree, so write access is required only for the control files the
        # measurement really writes; cpu.stat must be present and readable.
        for name in ("cgroup.procs", "cpu.max", "memory.max"):
            node = self.path / name
            if not node.exists() or not os.access(node, os.W_OK):
                raise ContractError(f"MEASUREMENT_CAPABILITY_MISSING: cgroup_{name}")
        node = self.path / "cpu.stat"
        if not node.exists() or not os.access(node, os.R_OK):
            raise ContractError("MEASUREMENT_CAPABILITY_MISSING: cgroup_cpu.stat")

    def set_limits(self, *, memory_max_bytes: int, cpu_quota_us: int,
                   period_us: int = _DEFAULT_CPU_PERIOD_US) -> dict[str, int]:
        """Write the pre-spawn caps and read them back; an unapplied cap never starts."""

        if int(memory_max_bytes) <= 0 or int(cpu_quota_us) <= 0 or int(period_us) <= 0:
            raise ContractError("MEASUREMENT_LIMIT_UNENFORCEABLE")
        (self.path / "memory.max").write_text(str(int(memory_max_bytes)))
        (self.path / "cpu.max").write_text(f"{int(cpu_quota_us)} {int(period_us)}")
        applied_memory = self._read("memory.max")
        applied = self._read("cpu.max").split()
        if len(applied) != 2:
            raise ContractError("MEASUREMENT_LIMIT_UNENFORCEABLE")
        quota, applied_period = applied
        # cgroup v2 rounds memory.max down to the page size, so the applied cap may be a
        # few bytes below the requested one. Anything above the request, or below it by a
        # whole page or more, means the cap the measurement relies on was not applied.
        try:
            applied_memory_bytes = int(applied_memory)
        except ValueError as error:
            raise ContractError("MEASUREMENT_LIMIT_UNENFORCEABLE") from error
        page = int(os.sysconf("SC_PAGE_SIZE"))
        within_one_page = 0 < int(memory_max_bytes) - applied_memory_bytes < page
        if (not within_one_page and applied_memory_bytes != int(memory_max_bytes)):
            raise ContractError("MEASUREMENT_LIMIT_UNENFORCEABLE")
        if quota != str(int(cpu_quota_us)) or int(applied_period) != int(period_us):
            raise ContractError("MEASUREMENT_LIMIT_UNENFORCEABLE")
        self.limits = {
            "memory_max_bytes": applied_memory_bytes,
            "cpu_quota_us": int(quota),
            "cpu_period_us": int(applied_period),
        }
        return dict(self.limits)

    def attach(self, pid: int) -> None:
        try:
            (self.path / "cgroup.procs").write_text(str(int(pid)))
        except OSError as error:
            raise ContractError("CGROUP_ATTACH_FAILED") from error
        if int(pid) not in self.pids():
            raise ContractError("CGROUP_ATTACH_FAILED")

    def pids(self) -> tuple[int, ...]:
        pids = []
        for token in self._read("cgroup.procs", "").split():
            try:
                pids.append(int(token))
            except ValueError:
                continue
        return tuple(sorted(pids))

    def _cpu_stat(self) -> dict[str, int]:
        values = {}
        for line in self._read("cpu.stat").splitlines():
            name, _, value = line.partition(" ")
            if value.strip().isdigit():
                values[name] = int(value.strip())
        return values

    def cpu_usage_us(self) -> int:
        return self._cpu_stat().get("usage_usec", 0)

    def nr_throttled(self) -> int:
        return self._cpu_stat().get("nr_throttled", 0)

    @property
    def throttled(self) -> bool:
        return self.nr_throttled() > 0

    @property
    def attribution_complete(self) -> bool:
        return True

    def memory_current(self) -> int:
        return int(self._read("memory.current", "0") or 0)

    def memory_peak(self) -> int:
        return int(self._read("memory.peak", "0") or 0)

    def memory_pressure_full(self) -> int:
        """The owned cgroup's own full-stall time, in microseconds."""

        total = 0
        for line in self._read("memory.pressure").splitlines():
            if line.startswith("full "):
                for token in line.split()[1:]:
                    if token.startswith("total="):
                        total = int(token.split("=", 1)[1])
        return total

    def memory_swap_current(self) -> int:
        """The owned cgroup's own swap, so a policy breach describes the workload.

        Host-wide swap moves for reasons that have nothing to do with the batch, and a
        zero-tolerance rule on it aborts every measurement on this host.
        """

        return int(self._read("memory.swap.current"))

    def memory_events(self) -> dict[str, int]:
        events = {}
        for line in self._read("memory.events", "").splitlines():
            name, _, value = line.partition(" ")
            if value.strip().isdigit():
                events[name] = int(value.strip())
        return events

    def remove(self) -> None:
        if self.pids():
            raise ContractError("MEASUREMENT_CLEANUP_FAILED: cgroup_not_empty")
        try:
            self.path.rmdir()
        except OSError as error:
            raise ContractError("MEASUREMENT_CLEANUP_FAILED: cgroup_remove") from error
        if self.path.exists():
            raise ContractError("MEASUREMENT_CLEANUP_FAILED: cgroup_present")


class NvmlDevicePort:
    """Whole-device NVML facts behind the two attributes the sampler consumes."""

    def __init__(self, *, device_index: int = 0, reader=None) -> None:
        from .resource_budget import read_nvml_device

        self.device_index = int(device_index)
        self._reader = reader or read_nvml_device
        self._last: Mapping[str, object] = {}

    def refresh(self) -> Mapping[str, object]:
        device = self._reader(self.device_index)
        if not isinstance(device, Mapping) or float(device.get("total_bytes", 0)) <= 0:
            raise ContractError("MEASUREMENT_CAPABILITY_MISSING: nvml_device")
        self._last = device
        return device

    @property
    def total_bytes(self) -> int:
        return int(self.refresh()["total_bytes"])

    @property
    def used_bytes(self) -> int:
        return int(self.refresh()["used_bytes"])

    @property
    def consumers(self) -> tuple[int, ...]:
        return tuple(self.refresh().get("consumers", ()))

    @property
    def name(self) -> str:
        return str(self.refresh().get("name", ""))


@dataclass
class OwnedChild:
    """A real child process in its own session, attached to the owned cgroup."""

    process: subprocess.Popen
    streams: tuple = ()

    def wait(self, timeout: float | None = None) -> int | None:
        try:
            return self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None

    def kill_group(self, *, sig: int = signal.SIGTERM) -> None:
        try:
            os.killpg(os.getpgid(self.process.pid), sig)
        except (ProcessLookupError, PermissionError):
            return

    def close_streams(self) -> None:
        for handle in self.streams:
            try:
                handle.close()
            except OSError:
                continue

    @property
    def returncode(self) -> int | None:
        return self.process.returncode


class MeasurementSession:
    """Owns the cgroup, sampler, abort latch, deadline and cleanup of one batch."""

    def __init__(
        self, *, authorization, batch_root: Path, batch_id: str, sampling, safety,
        owner: ProcessIdentity,
        cgroup_parent: Path | None = None, device_index: int = 0,
        clock: Callable[[], float] = time.monotonic,
        observation_source=None, cgroup_factory=None, device_factory=None,
        host_facts=None, quiet_s: float | None = None, maximum_quiet_s: float = 5.0,
        sampler_interval_s: float | None = None, epoch: int = 1,
        deadline_s: float | None = None,
    ) -> None:
        for name in ("dispatch_id", "task_id", "worker_count", "batch_deadline_s",
                     "safety_policy_sha256", "owned_scope_sha256", "execution_identity_sha256",
                     "raw_sha256"):
            if not hasattr(authorization, name):
                raise ContractError(f"AUTHORIZATION_FIELD: {name}")
        if not isinstance(owner, ProcessIdentity):
            raise ContractError("PROCESS_IDENTITY: owner")
        if not isinstance(batch_id, str) or not batch_id or "/" in batch_id:
            raise ContractError("BATCH_ID")
        self.authorization = authorization
        self.batch_id = batch_id
        self.batch_root = Path(batch_root)
        self.sampling = sampling
        self.safety = safety
        self.owner = owner
        self.clock = clock
        self.device_index = int(device_index)
        self.epoch = int(epoch)
        self.cgroup_parent = Path(cgroup_parent) if cgroup_parent else own_cgroup_path()
        self._observation_source = observation_source
        self._cgroup_factory = cgroup_factory
        self._device_factory = device_factory
        self._host_facts = host_facts
        self._quiet_s = float(
            min(sampling.post_cleanup_quiet_s if quiet_s is None else quiet_s, maximum_quiet_s))
        self._interval_s = float(
            sampling.resource_sample_interval_s if sampler_interval_s is None
            else sampler_interval_s)
        authorized_deadline = float(authorization.batch_deadline_s)
        if deadline_s is not None and not 0 < float(deadline_s) <= authorized_deadline:
            # A caller may shorten the authorized deadline for an offline run, never
            # extend it: the sealed authorization stays the upper bound.
            raise ContractError("MEASUREMENT_DEADLINE_INVALID")
        self.deadline_s = authorized_deadline if deadline_s is None else float(deadline_s)
        self.raw_root = self.batch_root / "raw"
        self.samples_path = self.raw_root / "samples.jsonl"
        self.events_path = self.batch_root / "coverage-events.json"
        self.receipt_path = self.batch_root / "cleanup-receipt.json"
        self.stdout_path = self.raw_root / "workload-stdout.log"
        self.stderr_path = self.raw_root / "workload-stderr.log"
        self.cgroup: OwnedCgroupV2 | None = None
        self.device = None
        self.control: MeasurementControl | None = None
        self.child: OwnedChild | None = None
        self.limits: Mapping[str, int] | None = None
        self.capacity: Mapping[str, float] | None = None
        self.baseline: Mapping[str, object] | None = None
        self.abort_reason: str | None = None
        self.deadline_exceeded = False
        self.samples = 0
        self._events: dict[str, float | None] = {name: None for name in _EVENT_NAMES}
        self._thread: threading.Thread | None = None
        self._stopped = threading.Event()
        self._rebaseline = threading.Event()
        self._lock = threading.Lock()
        self._directory_fd: int | None = None
        self._control_socket: socket.socket | None = None
        self._control_address: str | None = None

    # -- events and receipts ---------------------------------------------------------
    def _record(self, name: str) -> None:
        with self._lock:
            self._events[name] = float(self.clock())
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(
                {"event": name, "monotonic_s": float(self.clock())}, sort_keys=True) + "\n")

    def event_times(self) -> dict[str, float | None]:
        with self._lock:
            return dict(self._events)

    # -- lifecycle -------------------------------------------------------------------
    def begin(self) -> Mapping[str, object]:
        """Verify the capabilities, apply the caps and start the baseline."""

        self.batch_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.raw_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.events_path.touch(mode=0o600)
        self._record("BASELINE_START")
        observation = self._observe()
        self.capacity = dict(observation.capacity)
        self.device = (self._device_factory() if self._device_factory is not None
                       else NvmlDevicePort(device_index=self.device_index))
        name = f"so101-measurement-{self.authorization.dispatch_id}-{self.batch_id}"[:96]
        self.cgroup = (self._cgroup_factory() if self._cgroup_factory is not None
                       else OwnedCgroupV2.create(parent=self.cgroup_parent, name=name))
        envelope = float(self.safety.capacity_fraction)
        memory_max = int(
            envelope * observation.capacity["ram_bytes"] - observation.background["ram_bytes"]
            - observation.tool_overhead["ram_bytes"])
        cpu_quota = int((
            envelope * observation.capacity["cpu_core_equivalent"]
            - observation.background["cpu_core_equivalent"]
            - observation.tool_overhead["cpu_core_equivalent"]) * self.sampling.cgroup_cpu_period_us)
        if memory_max <= 0 or cpu_quota <= 0:
            self._record("CAPACITY_REFUSED")
            raise ContractError("MEASUREMENT_LIMIT_UNENFORCEABLE")
        self.limits = self.cgroup.set_limits(
            memory_max_bytes=memory_max, cpu_quota_us=cpu_quota,
            period_us=self.sampling.cgroup_cpu_period_us)
        self._record("LIMITS_APPLIED")
        self.baseline = {
            "monotonic_s": float(self.clock()),
            "capacity": dict(observation.capacity),
            "background": dict(observation.background),
            "tool_overhead": dict(observation.tool_overhead),
            "attribution_complete": bool(observation.attribution_complete),
            "limits": dict(self.limits),
        }
        self._bind_control()
        self._record("BASELINE_END")
        return dict(self.baseline)

    def _observe(self):
        if self._observation_source is not None:
            observation = self._observation_source()
        else:
            from .resource_budget import LiveObservationSource

            observation = LiveObservationSource(
                gpu_device_index=self.device_index,
                host_probe=self._host_facts)()
        if not observation.attribution_complete:
            raise ContractError("MEASUREMENT_CAPABILITY_MISSING: attribution")
        return observation

    def _bind_control(self) -> None:
        """Bind the real owner control endpoint; its address stays inside the batch root."""

        try:
            require_transport_basename("owner-control.sock")
            self._directory_fd = os.open(self.batch_root, os.O_RDONLY | os.O_DIRECTORY)
            address = transport_address(Path("owner-control.sock"), self._directory_fd)
        except IpcError as error:
            raise ContractError(
                f"MEASUREMENT_CAPABILITY_MISSING: control_endpoint {error.code}"
                if hasattr(error, "code") else "MEASUREMENT_CAPABILITY_MISSING: control_endpoint"
            ) from error
        if len(os.fsencode(address)) > _MAXIMUM_CONTROL_SOCKET_BYTES:
            raise ContractError("CONTROL_SOCKET_PATH_TOO_LONG")
        endpoint = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            endpoint.bind(address)
            endpoint.listen(1)
        except OSError as error:
            endpoint.close()
            raise ContractError("MEASUREMENT_CAPABILITY_MISSING: control_endpoint") from error
        self._control_socket = endpoint
        self._control_address = address
        binding = MeasurementOwnerBinding(
            authorization_sha256=self.authorization.raw_sha256,
            task_id=str(self.authorization.task_id),
            campaign_id=str(self.authorization.task_id),
            batch_id=self.batch_id,
            epoch=self.epoch,
            owner=self.owner,
            control_socket=Path(address),  # short /proc/self/fd/<dirfd> form
            control_token_sha256=hashlib.sha256(
                f"{self.authorization.raw_sha256}:{self.batch_id}".encode()
            ).hexdigest(),
            owned_scope_sha256=self.authorization.owned_scope_sha256,
            sampler=self.owner,
            abort_policy_sha256=self.authorization.safety_policy_sha256,
            events_path=self.events_path,
        )
        self.control = MeasurementControl(
            binding, clock=self.clock, cancel_sender=self._cancel_owned_workload,
            scope_verifier=self._scope_verified, containment=self._containment_cleared,
            maximum_sample_gap_s=float(self.sampling.maximum_sample_gap_s))

    # -- control callbacks -----------------------------------------------------------
    def _scope_verified(self, owned_scope_sha256: str) -> bool:
        return (
            owned_scope_sha256 == self.authorization.owned_scope_sha256
            and self.cgroup is not None
        )

    def _containment_cleared(self, owned_scope_sha256: str) -> bool:
        if owned_scope_sha256 != self.authorization.owned_scope_sha256:
            return False
        return self.cgroup is None or not self.cgroup.pids()

    def _cancel_owned_workload(self, binding, reason: str) -> dict:
        """Send the owned-group cancel; only a verification-confirmed scope is signalled."""

        receipt: dict[str, object] = {
            "reason": str(reason), "monotonic_s": float(self.clock()), "sent": False,
            "scope_verified": self._scope_verified(binding.owned_scope_sha256),
        }
        if not receipt["scope_verified"]:
            raise ContractError("FOREIGN_IDENTITY")
        self._record("ABORT_LATCHED")
        child = self.child
        if child is not None and child.returncode is None:
            child.kill_group(sig=signal.SIGTERM)
            receipt.update(sent=True, target_pgid=os.getpgid(child.process.pid),
                           signal="SIGTERM")
        return receipt

    def permit_side_effect(self) -> None:
        if self.control is not None:
            self.control.permit_side_effect()

    # -- sampling --------------------------------------------------------------------
    def start_sampling(self) -> None:
        if self.cgroup is None or self.device is None:
            raise ContractError("MEASUREMENT_SESSION")
        self._stopped.clear()
        self._record("SAMPLING_START")
        if self.control is not None:
            self.control.mark_sampling_start(self.clock())
        self._thread = threading.Thread(target=self._sample_loop, name="measurement-sampler",
                                        daemon=True)
        self._thread.start()

    def _sample_loop(self) -> None:
        from .resource_measurement import sample_resources

        state: dict = {"cpu_window_s": max(float(self._interval_s),
                                           float(self.sampling.cgroup_cpu_period_us) / 1e6)}
        sequence = 0
        deadline = self.clock()
        while not self._stopped.is_set():
            if self._rebaseline.is_set():
                # Only usage accumulated from the attach point is the workload's own.
                self._rebaseline.clear()
                state = {"cpu_window_s": max(float(self._interval_s),
                                             float(self.sampling.cgroup_cpu_period_us) / 1e6)}
            sequence += 1
            try:
                sample = sample_resources(
                    owned_inventory=(self.owner,), cgroup=self.cgroup, device=self.device,
                    sequence=sequence, state=state)
            except Exception as error:  # noqa: BLE001 - a lost sample latches the abort
                if self.control is not None:
                    self.control.check_health(
                        self.clock(), sampler_alive=False, endpoint_healthy=False,
                        breach=f"SAMPLER_FAILED: {type(error).__name__}")
                return
            with self._lock:
                self.samples = sequence
            with self.samples_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "sequence": sample.sequence,
                    "monotonic_s": sample.monotonic_s,
                    "observation": {
                        "capacity": dict(sample.observation.capacity),
                        "observed": dict(sample.observation.observed),
                        "background": dict(sample.observation.background),
                        "remaining": dict(sample.observation.remaining),
                        "error": dict(sample.observation.error),
                        "attribution_complete": sample.observation.attribution_complete,
                        "swap_delta": sample.observation.swap_delta,
                        "psi_full_delta": sample.observation.psi_full_delta,
                        "throttled": sample.observation.throttled,
                    },
                    "diagnostics": dict(sample.diagnostics),
                    "memory_events": self.cgroup.memory_events() if self.cgroup else {},
                }, sort_keys=True) + "\n")
            if self.control is not None:
                self.control.observe_sample(sample.sequence, sample.monotonic_s)
                self.control.check_health(
                    self.clock(), sampler_alive=True,
                    endpoint_healthy=bool(self._control_socket is not None),
                    breach=self._breach(sample))
                if self.control.stop_requested():
                    self.abort_reason = self.control.latch_reason
                    return
            deadline, delay = _advance_sampling_grid(
                now=self.clock(), deadline=deadline, interval_s=float(self._interval_s))
            self._stopped.wait(delay)

    def _request_sampling_rebaseline(self) -> None:
        """Drop the sampler's carry-over so a migrated task's earlier CPU is not counted."""

        self._rebaseline.set()

    def _breach(self, sample) -> str | None:
        observation = sample.observation
        minimum_free = float(self.safety.minimum_free_fraction)
        if not observation.attribution_complete:
            return "UNATTRIBUTED_CONSUMER"
        # CPU/RAM/GPU-only amendment (74d6b781): swap and PSI activity are not breach
        # dimensions. The deprecated observation fields may still carry values and must not
        # be able to latch an abort here.
        if self.safety.throttling_disqualifies_run and observation.throttled:
            return "CPU_THROTTLED"
        capacity = observation.capacity
        if capacity["ram_bytes"] - observation.background["ram_bytes"] < (
            minimum_free * capacity["ram_bytes"]
        ):
            return "MEMORY_MINIMUM_FREE"
        if capacity["gpu_bytes"] - observation.background["gpu_bytes"] < (
            minimum_free * capacity["gpu_bytes"]
        ):
            return "GPU_MINIMUM_FREE"
        if observation.observed["cpu_core_equivalent"] > float(
            self.safety.capacity_fraction
        ) * capacity["cpu_core_equivalent"]:
            return "CPU_ENVELOPE"
        if self.cgroup is not None:
            events = self.cgroup.memory_events()
            for name in ("oom", "oom_kill", "high", "max"):
                if events.get(name, 0) > 0:
                    return f"CGROUP_MEMORY_{name.upper()}"
        return None

    # -- workload --------------------------------------------------------------------
    def spawn(self, *, argv: Sequence[str], cwd: Path, environment: Mapping[str, str] | None = None,
              label: str = "workload") -> OwnedChild:
        if self.cgroup is None:
            raise ContractError("MEASUREMENT_SESSION")
        self.permit_side_effect()
        stdout = self.stdout_path.open("ab")
        stderr = self.stderr_path.open("ab")
        try:
            process = subprocess.Popen(
                [str(item) for item in argv], cwd=str(cwd),
                env=None if environment is None else dict(environment),
                stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL,
                start_new_session=True)
        except OSError as error:
            stdout.close()
            stderr.close()
            raise ContractError(f"MEASUREMENT_WORKLOAD_UNAVAILABLE: {label}") from error
        child = OwnedChild(process=process, streams=(stdout, stderr))
        self.child = child
        self._record("WORKLOAD_SPAWN")
        try:
            self.cgroup.attach(process.pid)
            self._request_sampling_rebaseline()
        except ContractError:
            child.kill_group()
            child.wait(timeout=5.0)
            raise
        return child

    def supervise(self, child: OwnedChild) -> int:
        """Wait for the workload while enforcing the deadline, sampler and abort latch."""

        deadline = float(self.deadline_s)
        started = float(self.clock())
        while True:
            remaining = deadline - (float(self.clock()) - started)
            if remaining <= 0:
                self.deadline_exceeded = True
                if self.control is not None:
                    self.control.check_health(
                        self.clock(), sampler_alive=bool(self._thread and self._thread.is_alive()),
                        endpoint_healthy=True, breach="BATCH_DEADLINE_EXCEEDED")
                child.kill_group()
                child.wait(timeout=10.0)
                break
            code = child.wait(timeout=min(0.05, remaining))
            if code is not None:
                self._record("WORKLOAD_EXIT")
                return code
            if self.control is not None:
                self.control.check_health(
                    self.clock(), sampler_alive=bool(self._thread and self._thread.is_alive()),
                    endpoint_healthy=bool(self._control_socket is not None), breach=None)
                if self.control.stop_requested():
                    self.abort_reason = self.control.latch_reason
                    child.kill_group()
                    child.wait(timeout=10.0)
                    return child.returncode if child.returncode is not None else -1
        self._record("WORKLOAD_EXIT")
        return child.returncode if child.returncode is not None else -1

    def finish(self) -> Mapping[str, object]:
        """Stop sampling, verify the containment, remove it and record the receipt."""

        self._record("CLEANUP_START")
        child = self.child
        if child is not None:
            if child.returncode is None:
                child.kill_group()
                child.wait(timeout=10.0)
            child.close_streams()
        cleared_at = None
        if self.cgroup is not None:
            for _ in range(200):
                if not self.cgroup.pids():
                    cleared_at = float(self.clock())
                    break
                time.sleep(0.05)
            if cleared_at is None:
                raise ContractError("MEASUREMENT_CLEANUP_FAILED: workload_alive")
        exited = float(self.clock())
        if self._quiet_s > 0:
            time.sleep(self._quiet_s)
        self._record("QUIET_END")
        self._stopped.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(5.0, 2 * self._interval_s))
            if thread.is_alive():
                raise ContractError("MEASUREMENT_CLEANUP_FAILED: sampler_alive")
        self._record("SAMPLING_STOP")
        if self.cgroup is not None:
            self.cgroup.remove()
            self.cgroup = None
        if self._control_socket is not None:
            self._control_socket.close()
            self._control_socket = None
            if self._control_address and os.path.exists(self._control_address):
                os.unlink(self._control_address)
        if self._directory_fd is not None:
            os.close(self._directory_fd)
            self._directory_fd = None
        self._record("CLEANUP_END")
        receipt = {
            "schema_version": 1,
            "kind": "MEASUREMENT_CLEANUP_RECEIPT",
            "authorization_sha256": self.authorization.raw_sha256,
            "batch_id": self.batch_id,
            "containment_cleared": True,
            "limits": dict(self.limits or {}),
            "samples": self.samples,
            "events": self.event_times(),
            "control_events": (
                {} if self.control is None else self.control.event_times()),
            "exited_monotonic_s": exited,
            "abort_reason": self.abort_reason,
            "deadline_exceeded": self.deadline_exceeded,
        }
        self.receipt_path.write_text(json.dumps(receipt, sort_keys=True))
        self.receipt_path.chmod(0o600)
        return receipt

    def raw_files(self) -> tuple[Path, ...]:
        candidates = (self.samples_path, self.events_path, self.receipt_path,
                      self.stdout_path, self.stderr_path)
        return tuple(path for path in candidates if path.is_file())


def read_child_streams(paths: Sequence[Path]) -> dict[str, str]:
    """Decode the recorded raw streams without truncation."""

    return {
        Path(path).name: Path(path).read_text(errors="replace") for path in paths
        if Path(path).is_file()
    }

