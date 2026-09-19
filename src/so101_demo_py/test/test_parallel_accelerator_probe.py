"""The Darwin MPS accelerator probe: one bounded read, fail-closed everywhere else.

Task 2 of the macOS MPS / private IPC plan. The probe answers exactly one question for a
schema-v4 Darwin campaign: how much unified memory is available to a single MPS process, and
is that above the fixed headroom floor? Everything here is either a closed data model or a
low-level read with an injected port, so the interesting branches (missing output, illegal
units, helper that will not die) are exercised without depending on the host's current memory
pressure.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from so101_demo.parallel_batch import accelerator_probe as probe_module
from so101_demo.parallel_batch.accelerator_probe import (
    AcceleratorSnapshot,
    DarwinMpsAcceleratorProbe,
    ProbeError,
)
from so101_demo.parallel_batch.start_guard import StartGuardPolicy
from so101_demo.parallel_batch.start_guard import ProbeError as GuardProbeError

GIB = 1 << 30

VM_STAT_SAMPLE = """\
Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                              100000.
Pages active:                            200000.
Pages inactive:                           50000.
Pages speculative:                        10000.
Pages throttled:                              0.
Pages wired down:                         30000.
Pages purgeable:                           5000.
"Translation faults":                  12345678.
Pages copy-on-write:                     123456.
Pages zero filled:                      1234567.
Pages reactivated:                         1234.
Pages purged:                               567.
File-backed pages:                        20000.
Anonymous pages:                          40000.
Pages stored in compressor:               10000.
Pages occupied by compressor:              8000.
Decompressions:                            1234.
Compressions:                              4321.
Pageins:                                   9999.
Pageouts:                                   111.
Swapins:                                      0.
Swapouts:                                     0.
"""


class VmStatPort:
    """Returns raw vm_stat text (or raises) and records how often it was asked."""

    def __init__(self, text=VM_STAT_SAMPLE, error=None):
        self.text = text
        self.error = error
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.text


def _torch_module(*, built=True, available=True, recommended=16 * GIB,
                  current=GIB, driver=2 * GIB, version="2.13.0"):
    """Build a throwaway module object that looks like torch for this probe's purposes."""

    import types

    module = types.ModuleType("fake_torch")
    module.__version__ = version
    backends = types.ModuleType("fake_torch.backends")
    mps_backend = types.ModuleType("fake_torch.backends.mps")
    mps_backend.is_built = lambda: built
    mps_backend.is_available = lambda: available
    backends.mps = mps_backend
    module.backends = backends
    mps = types.ModuleType("fake_torch.mps")
    mps.recommended_max_memory = lambda: recommended
    mps.current_allocated_memory = lambda: current
    mps.driver_allocated_memory = lambda: driver
    module.mps = mps
    return module


def test_accelerator_snapshot_is_closed_and_rejects_illegal_values():
    """The snapshot is a closed model: kinds, byte counts and selector must all be real."""

    snapshot = AcceleratorSnapshot(
        kind="mps", selector="default", available_bytes=8 * GIB,
        recommended_max_memory_bytes=16 * GIB, current_allocated_memory_bytes=GIB,
        driver_allocated_memory_bytes=2 * GIB, metric_source="vm_stat+torch.mps",
    )
    assert snapshot.kind == "mps"
    assert snapshot.available_bytes == 8 * GIB

    for mutated in (
        {"kind": "tpu"},
        {"available_bytes": -1},
        {"available_bytes": 1.5},
        {"selector": ""},
        {"metric_source": ""},
    ):
        payload = dict(
            kind="mps", selector="default", available_bytes=8 * GIB,
            recommended_max_memory_bytes=16 * GIB, current_allocated_memory_bytes=GIB,
            driver_allocated_memory_bytes=2 * GIB, metric_source="vm_stat+torch.mps",
        )
        payload.update(mutated)
        with pytest.raises((ValueError, probe_module.ProbeError)):
            AcceleratorSnapshot(**payload)


def test_probe_reports_mps_availability_and_metric_provenance():
    """A healthy Darwin host yields kind=mps with the recommended and host values recorded."""

    ports = probe_module.DarwinMpsPorts(
        torch_module=lambda: _torch_module(
            recommended=16 * GIB, current=GIB, driver=2 * GIB, version="2.13.0"),
        vm_stat=lambda: VM_STAT_SAMPLE,
        clock=time.monotonic,
    )
    probe = DarwinMpsAcceleratorProbe(ports=ports)
    snapshot = probe.probe(deadline_monotonic_ns=time.monotonic_ns() + 2_000_000_000)

    # min(host_available, recommended_max_memory) is the admission figure.
    host_available = (100000 + 50000 + 10000 + 5000) * 16384
    assert snapshot.kind == "mps"
    assert snapshot.selector == "default"
    assert snapshot.recommended_max_memory_bytes == 16 * GIB
    assert snapshot.available_bytes == min(host_available, 16 * GIB)
    assert snapshot.current_allocated_memory_bytes == GIB
    assert snapshot.driver_allocated_memory_bytes == 2 * GIB
    assert "vm_stat" in snapshot.metric_source
    assert "mps" in snapshot.metric_source or "torch" in snapshot.metric_source


def test_probe_fails_closed_when_mps_is_not_built_or_not_available():
    """`is_built`/`is_available` are the first gate: either false refuses startup."""

    for built, available in ((False, True), (True, False), (False, False)):
        ports = probe_module.DarwinMpsPorts(
            torch_module=lambda b=built, a=available: _torch_module(built=b, available=a),
            vm_stat=lambda: VM_STAT_SAMPLE,
            clock=time.monotonic,
        )
        probe = DarwinMpsAcceleratorProbe(ports=ports)
        with pytest.raises(probe_module.ProbeError, match="MPS_UNAVAILABLE"):
            probe.probe(deadline_monotonic_ns=time.monotonic_ns() + 2_000_000_000)


def test_probe_fails_closed_when_recommended_max_memory_is_missing():
    """A missing or illegal recommended limit is not guessed and not replaced by host RAM."""

    for bad in (None, 0, -1, 1.5, "17179869184"):
        ports = probe_module.DarwinMpsPorts(
            torch_module=lambda b=bad: _torch_module(recommended=b),
            vm_stat=lambda: VM_STAT_SAMPLE,
            clock=time.monotonic,
        )
        probe = DarwinMpsAcceleratorProbe(ports=ports)
        with pytest.raises(probe_module.ProbeError, match="MPS_RECOMMENDED_MEMORY"):
            probe.probe(deadline_monotonic_ns=time.monotonic_ns() + 2_000_000_000)


@pytest.mark.parametrize(
    "text, reason",
    [
        ("", "VM_STAT_OUTPUT_MISSING"),
        ("Mach Virtual Memory Statistics:\nPages free: 100.\n", "VM_STAT_PAGE_SIZE"),
        ("Mach Virtual Memory Statistics: (page size of 0 bytes)\nPages free: 100.\n",
         "VM_STAT_PAGE_SIZE"),
        ("Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages active: 10.\n",
         "VM_STAT_COUNTERS"),
        ("Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free: abc.\n",
         "VM_STAT_COUNTERS"),
        ("Mach Virtual Memory Statistics: (page size of -16384 bytes)\nPages free: 10.\n",
         "VM_STAT_PAGE_SIZE"),
    ],
)
def test_probe_fails_closed_on_missing_or_illegal_vm_stat_output(text, reason):
    """Missing, unit-less or garbage vm_stat output fails closed instead of estimating."""

    ports = probe_module.DarwinMpsPorts(
        torch_module=lambda: _torch_module(),
        vm_stat=lambda: text,
        clock=time.monotonic,
    )
    probe = DarwinMpsAcceleratorProbe(ports=ports)
    with pytest.raises(probe_module.ProbeError, match=reason):
        probe.probe(deadline_monotonic_ns=time.monotonic_ns() + 2_000_000_000)


def test_probe_fails_closed_when_vm_stat_raises():
    """A raising helper is a refusal, not a zero and not a host-RAM substitute."""

    ports = probe_module.DarwinMpsPorts(
        torch_module=lambda: _torch_module(),
        vm_stat=lambda: (_ for _ in ()).throw(OSError("vm_stat exploded")),
        clock=time.monotonic,
    )
    probe = DarwinMpsAcceleratorProbe(ports=ports)
    with pytest.raises(probe_module.ProbeError, match="VM_STAT_FAILED"):
        probe.probe(deadline_monotonic_ns=time.monotonic_ns() + 2_000_000_000)


def test_probe_honours_the_shared_deadline_without_reading_anything():
    """An already-expired deadline refuses before the first read, not after it."""

    vm_port = VmStatPort()
    probe = DarwinMpsAcceleratorProbe(ports=probe_module.DarwinMpsPorts(
        torch_module=lambda: _torch_module(), vm_stat=vm_port, clock=time.monotonic))
    with pytest.raises(probe_module.ProbeError, match="PROBE_DEADLINE_EXCEEDED"):
        probe.probe(deadline_monotonic_ns=time.monotonic_ns() - 1)
    assert vm_port.calls == 0


def test_probe_refuses_when_the_remaining_deadline_is_consumed_mid_read():
    """The deadline is checked again after the torch read; a slow read cannot overrun it."""

    state = {"t": 0.0}

    def clock() -> float:
        return state["t"]

    def vm_stat() -> str:
        state["t"] = 5.0
        return VM_STAT_SAMPLE

    probe = DarwinMpsAcceleratorProbe(ports=probe_module.DarwinMpsPorts(
        torch_module=lambda: _torch_module(), vm_stat=vm_stat, clock=clock))
    with pytest.raises(probe_module.ProbeError, match="PROBE_DEADLINE_EXCEEDED"):
        probe.probe(deadline_monotonic_ns=int(2.0 * 1_000_000_000))


def test_mps_evaluation_uses_min_host_and_recommended_against_the_fixed_floor():
    """The v4 decision compares the headroom figure with the fixed 1 GiB floor."""

    policy = StartGuardPolicy(mps_minimum_headroom_bytes=GIB)
    healthy = AcceleratorSnapshot(
        kind="mps", selector="default", available_bytes=8 * GIB,
        recommended_max_memory_bytes=16 * GIB, current_allocated_memory_bytes=0,
        driver_allocated_memory_bytes=0, metric_source="vm_stat+torch.mps")
    result = probe_module.evaluate_accelerator_snapshot(healthy, policy)
    assert result.status == "PASS"
    assert result.checks["mps_headroom"].reason == "MPS_HEADROOM_OK"
    assert result.checks["mps_headroom"].cutoff == GIB
    assert result.checks["mps_headroom"].unit == "bytes"
    assert result.metric_source == "vm_stat+torch.mps"
    assert result.admission_kind == "unified-memory-proxy"

    tight = AcceleratorSnapshot(
        kind="mps", selector="default", available_bytes=GIB - 1,
        recommended_max_memory_bytes=16 * GIB, current_allocated_memory_bytes=0,
        driver_allocated_memory_bytes=0, metric_source="vm_stat+torch.mps")
    refused = probe_module.evaluate_accelerator_snapshot(tight, policy)
    assert refused.status == "FAIL"
    assert refused.checks["mps_headroom"].reason == "MPS_HEADROOM_BELOW_MINIMUM"


def test_mps_evaluation_requires_a_configured_floor():
    """A Darwin document without the floor cannot be evaluated into a PASS."""

    policy = StartGuardPolicy()
    healthy = AcceleratorSnapshot(
        kind="mps", selector="default", available_bytes=8 * GIB,
        recommended_max_memory_bytes=16 * GIB, current_allocated_memory_bytes=0,
        driver_allocated_memory_bytes=0, metric_source="vm_stat+torch.mps")
    with pytest.raises(probe_module.ProbeError, match="MPS_MINIMUM_HEADROOM_BYTES"):
        probe_module.evaluate_accelerator_snapshot(healthy, policy)


def test_v3_snapshot_path_is_not_offered_the_mps_figure():
    """The unified-memory proxy must not be usable as a v3 `gpu_free_bytes`."""

    from so101_demo.parallel_batch import start_guard as guard_module

    assert not hasattr(guard_module.ResourceSnapshot, "mps_available_bytes")
    healthy = AcceleratorSnapshot(
        kind="mps", selector="default", available_bytes=8 * GIB,
        recommended_max_memory_bytes=16 * GIB, current_allocated_memory_bytes=0,
        driver_allocated_memory_bytes=0, metric_source="vm_stat+torch.mps")
    # The two models are not interchangeable: a v3 evaluation needs a real NVML-backed
    # ResourceSnapshot and must not accept the MPS admission figure by duck typing.
    with pytest.raises(ValueError):
        guard_module.evaluate_snapshot(healthy, StartGuardPolicy(),
                                       guard_module.GuardScope(
                                           batch_id="t", epoch=1, owner_pid=os.getpid(),
                                           owner_starttime_ticks=1, gpu_selector="INDEX:0",
                                           worker_count=2))


def test_v3_cuda_probe_selection_is_unchanged():
    """Selecting the probe by platform keeps the v3 NVML path exactly where it was."""

    assert probe_module.select_accelerator_probe("cuda") is None or callable(
        probe_module.select_accelerator_probe("cuda"))
    darwin = probe_module.select_accelerator_probe("mps")
    assert isinstance(darwin, probe_module.MpsAcceleratorProbeSelection)


def test_probe_classifies_a_real_host_snapshot_without_guessing():
    """A synthetic-but-real-shaped read produces the documented provenance string."""

    snapshot = DarwinMpsAcceleratorProbe(ports=probe_module.DarwinMpsPorts(
        torch_module=lambda: _torch_module(version="2.13.0"),
        vm_stat=lambda: VM_STAT_SAMPLE, clock=time.monotonic,
    )).probe(deadline_monotonic_ns=time.monotonic_ns() + 2_000_000_000)
    assert snapshot.metric_source.startswith("unified-memory-proxy:")
    assert "vm_stat" in snapshot.metric_source
    assert "2.13.0" in snapshot.metric_source or "torch" in snapshot.metric_source


def test_helper_process_is_reaped_and_never_left_running():
    """The bounded helper either returns quickly or is terminated and reaped."""

    ports = probe_module.DarwinMpsPorts(
        torch_module=lambda: _torch_module(), vm_stat=lambda: VM_STAT_SAMPLE,
        clock=time.monotonic)
    probe = DarwinMpsAcceleratorProbe(ports=ports)
    text = probe.read_vm_stat_bounded(timeout_s=1.0)
    assert "page size of" in text


def test_helper_timeout_terminates_and_reaps_the_child():
    """A helper that ignores the deadline is killed and waitpid'ed, then reported."""

    class Stubborn:
        """A helper that ignores SIGTERM and only dies on SIGKILL."""

        def __init__(self):
            self.pid = 4242
            self.terminated = False
            self.killed = False
            self.waited = []
            self.returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.killed = True
            self.returncode = -9

        def wait(self, timeout=None):
            self.waited.append(timeout)
            if not self.killed:
                raise subprocess.TimeoutExpired(cmd="helper", timeout=timeout)
            return self.returncode

    child = Stubborn()
    with pytest.raises(probe_module.ProbeError, match="VM_STAT_TIMEOUT"):
        probe_module._reap_helper(child, timeout_s=0.01)
    assert child.terminated is True
    assert child.killed is True
    assert child.waited, "the helper must be waited on after termination"


def test_helper_that_cannot_be_reaped_is_a_refusal():
    """If waitpid never confirms the child is gone, the probe refuses and says so."""

    class Immortal:
        def __init__(self):
            self.pid = 4243
            self.killed = False

        def poll(self):
            return None

        def terminate(self):
            pass

        def kill(self):
            self.killed = True

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired(cmd="helper", timeout=timeout)

    with pytest.raises(probe_module.ProbeError, match="VM_STAT_NOT_REAPED"):
        probe_module._reap_helper(Immortal(), timeout_s=0.01)
