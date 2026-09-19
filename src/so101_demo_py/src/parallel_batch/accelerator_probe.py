"""The Darwin MPS accelerator probe: one bounded, fail-closed admission read.

The approved design (2026-09-19, section 6.1) lets macOS admit a schema-v4 W2 campaign without
NVML. Apple GPUs expose no per-device free-VRAM counter, so the admission figure is an explicit
*unified-memory proxy*:

    min(host_available_memory_from_vm_stat, torch.mps.recommended_max_memory())

Everything here fails closed. A missing value, an illegal unit, a helper that overruns its
deadline, a helper that cannot be reaped, or a host figure below the fixed headroom floor all
refuse startup rather than being estimated, rounded or replaced with total RAM. The proxy is
never written into the schema-v3 ``gpu_free_bytes`` slot: ``evaluate_snapshot`` still requires a
real NVML-backed ``ResourceSnapshot`` and cannot be handed this figure.

``torch.mps.current_allocated_memory()`` and ``torch.mps.driver_allocated_memory()`` are recorded
for diagnostics only. They describe this process, not the machine, and they never take part in
the admission comparison.
"""

from __future__ import annotations

import argparse
import math
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Mapping, Protocol

from .start_guard import (
    FAIL,
    PASS,
    GuardCheck,
    StartGuardPolicy,
)
from .start_guard import ProbeError as _GuardProbeError

VM_STAT_PATH = Path("/usr/bin/vm_stat")

#: Grace given to a helper before the probe escalates from terminate to kill.
TERMINATE_GRACE_S = 0.20
KILL_GRACE_S = 0.20

#: What the admission figure actually is. Recorded in every snapshot's provenance.
ADMISSION_KIND = "unified-memory-proxy"


class ProbeError(_GuardProbeError):
    """A required accelerator read failed; the caller must refuse to start.

    It subclasses the start-guard probe error so an MPS refusal and an NVML refusal can be
    handled by the same fail-closed path without either module knowing about the other's
    vocabulary.
    """


@dataclass(frozen=True)
class AcceleratorSnapshot:
    """One accelerator observation. Closed: kinds, units and provenance are all checked."""

    kind: Literal["cuda", "mps"]
    selector: str
    available_bytes: int
    recommended_max_memory_bytes: int | None
    current_allocated_memory_bytes: int | None
    driver_allocated_memory_bytes: int | None
    metric_source: str

    def __post_init__(self) -> None:
        if self.kind not in ("cuda", "mps"):
            raise ValueError("kind must be cuda or mps")
        if not isinstance(self.selector, str) or not self.selector:
            raise ValueError("selector is required")
        for name in ("available_bytes", "recommended_max_memory_bytes",
                     "current_allocated_memory_bytes", "driver_allocated_memory_bytes"):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be a non-negative int")
            if value < 0:
                raise ValueError(f"{name} must be a non-negative int")
        if not isinstance(self.metric_source, str) or not self.metric_source:
            raise ValueError("metric_source is required")

    @property
    def admission_kind(self) -> str:
        """Always the honest label: this is a proxy, not a device-level VRAM proof."""

        return ADMISSION_KIND


@dataclass(frozen=True)
class AcceleratorEvaluation:
    """The v4 decision for one accelerator snapshot. WARN never blocks; FAIL always does."""

    status: str
    checks: Mapping[str, GuardCheck]
    metric_source: str
    admission_kind: str = ADMISSION_KIND

    def __post_init__(self) -> None:
        if self.status not in (PASS, "WARN", FAIL):
            raise ValueError("status must be PASS/WARN/FAIL")
        if not isinstance(self.checks, Mapping):
            raise ValueError("checks must be a mapping")


class AcceleratorProbe(Protocol):
    """The platform probe contract. One call per campaign, inside a shared deadline."""

    def probe(self, *, deadline_monotonic_ns: int) -> AcceleratorSnapshot: ...


# --------------------------------------------------------------------------------------
# the helper process: vm_stat inside the remaining deadline
# --------------------------------------------------------------------------------------


def read_vm_stat(*, timeout_s: float) -> str:
    """Run `/usr/bin/vm_stat` with a hard timeout and always reap the child.

    Returns the raw text. Raises :class:`ProbeError` with a stable reason when the helper
    times out, cannot be reaped or exits non-zero. Never returns a partial or guessed value.
    """

    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ProbeError("VM_STAT_TIMEOUT", f"non-positive budget {timeout_s!r}")
    try:
        process = subprocess.Popen(
            [str(VM_STAT_PATH)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise ProbeError("VM_STAT_FAILED", str(error)) from error
    try:
        stdout, stderr = _communicate_or_reap(process, timeout_s=timeout_s)
    except ProbeError:
        raise
    if process.returncode != 0:
        raise ProbeError(
            "VM_STAT_FAILED",
            f"exit {process.returncode}: {stderr.decode('utf-8', 'replace').strip()[:200]}",
        )
    return stdout.decode("utf-8", "replace")


def _communicate_or_reap(process, *, timeout_s: float) -> tuple[bytes, bytes]:
    """Collect the helper's output, or terminate/kill and reap it, or refuse."""

    try:
        return process.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _reap_helper(process, timeout_s=TERMINATE_GRACE_S)
        raise ProbeError("VM_STAT_TIMEOUT", f"helper exceeded {timeout_s:.3f}s") from None
    except OSError as error:  # pragma: no cover - platform dependent
        _reap_helper(process, timeout_s=TERMINATE_GRACE_S)
        raise ProbeError("VM_STAT_FAILED", str(error)) from error


def _reap_helper(process, *, timeout_s: float) -> None:
    """Terminate, then kill, then confirm the helper is gone.

    Two distinct failures are reported separately, because they mean different things: a helper
    that ignored its deadline is ``VM_STAT_TIMEOUT``, while a child that cannot be confirmed
    dead at all is ``VM_STAT_NOT_REAPED``. Either way the probe refuses; it never returns while
    an unaccounted helper may still be writing.
    """

    try:
        process.terminate()
    except OSError:
        pass
    graceful = False
    try:
        process.wait(timeout=timeout_s)
        graceful = True
    except subprocess.TimeoutExpired:
        pass
    except OSError:
        pass
    if not graceful:
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=KILL_GRACE_S)
    except subprocess.TimeoutExpired as error:
        raise ProbeError(
            "VM_STAT_NOT_REAPED", "helper survived SIGKILL confirmation") from error
    except OSError as error:
        raise ProbeError("VM_STAT_NOT_REAPED", str(error)) from error
    if process.poll() is None:
        raise ProbeError("VM_STAT_NOT_REAPED", "helper is still running")
    if not graceful:
        raise ProbeError(
            "VM_STAT_TIMEOUT", f"helper ignored {timeout_s:.3f}s and had to be killed")


# --------------------------------------------------------------------------------------
# vm_stat parsing
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class VmStatReading:
    """The parsed counters. `available_bytes` is reclaimable-looking pages only."""

    page_size_bytes: int
    available_bytes: int
    total_bytes: int

    #: Which page buckets were summed, so the number can be audited rather than trusted.
    counted_pages: tuple[str, ...] = ()


_VM_STAT_COUNTED_PAGES = ("free", "inactive", "speculative", "purgeable")


def parse_vm_stat(text: str, *, total_bytes: int | None = None) -> VmStatReading:
    """Parse raw `vm_stat` output; refuse anything missing, unit-less or malformed."""

    if not isinstance(text, str) or not text.strip():
        raise ProbeError("VM_STAT_OUTPUT_MISSING", "empty vm_stat output")
    page_match = re.search(r"page size of ([0-9]+) bytes", text)
    if page_match is None:
        raise ProbeError("VM_STAT_PAGE_SIZE", "page size not reported")
    page_size = int(page_match.group(1))
    if page_size <= 0:
        raise ProbeError("VM_STAT_PAGE_SIZE", f"page size {page_size}")

    counts: dict[str, int] = {}
    for name, count in re.findall(
        r"^Pages ([A-Za-z ]+):\s+([0-9]+)\.$", text, re.MULTILINE
    ):
        counts.setdefault(name.strip().lower(), 0)
        counts[name.strip().lower()] += int(count)
    if not counts:
        raise ProbeError("VM_STAT_COUNTERS", "no page counters found")
    if any(name not in counts for name in _VM_STAT_COUNTED_PAGES):
        missing = [name for name in _VM_STAT_COUNTED_PAGES if name not in counts]
        raise ProbeError("VM_STAT_COUNTERS", f"missing page buckets: {missing}")

    reclaimable_pages = sum(counts[name] for name in _VM_STAT_COUNTED_PAGES)
    available = reclaimable_pages * page_size
    capacity = total_bytes if total_bytes is not None else available
    if total_bytes is not None:
        available = min(available, total_bytes)
    return VmStatReading(
        page_size_bytes=page_size,
        available_bytes=available,
        total_bytes=capacity,
        counted_pages=_VM_STAT_COUNTED_PAGES,
    )


def _read_total_bytes() -> int | None:
    """Host RAM capacity. Darwin answers from sysconf; the sysctl binary is a fallback."""

    try:
        return int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
    except (OSError, ValueError):
        pass
    try:
        result = subprocess.run(
            ["/usr/sbin/sysctl", "-n", "hw.memsize"],
            check=True, capture_output=True, text=True, timeout=0.5,
        )
        return int(result.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


# --------------------------------------------------------------------------------------
# the probe
# --------------------------------------------------------------------------------------


@dataclass
class DarwinMpsPorts:
    """Low-level reads. Injected so every refusal branch is directly testable."""

    torch_module: Callable[[], object]
    vm_stat: Callable[[], str]
    clock: Callable[[], float]
    total_bytes: Callable[[], int | None] = _read_total_bytes


def _default_torch_module() -> object:
    import torch  # noqa: PLC0415 - imported only on the Darwin MPS path

    return torch


def _default_vm_stat() -> str:
    return read_vm_stat(timeout_s=1.0)


class DarwinMpsAcceleratorProbe:
    """The schema-v4 Darwin probe: one snapshot inside the caller's deadline."""

    def __init__(self, *, ports: DarwinMpsPorts | None = None) -> None:
        self._ports = ports or DarwinMpsPorts(
            torch_module=_default_torch_module,
            vm_stat=_default_vm_stat,
            clock=time.monotonic,
        )

    @property
    def ports(self) -> DarwinMpsPorts:
        return self._ports

    def probe(self, *, deadline_monotonic_ns: int) -> AcceleratorSnapshot:
        if isinstance(deadline_monotonic_ns, bool) or not isinstance(
                deadline_monotonic_ns, int):
            raise ProbeError("PROBE_DEADLINE_INVALID", repr(deadline_monotonic_ns))
        clock = self._ports.clock
        deadline_s = deadline_monotonic_ns / 1_000_000_000
        if clock() > deadline_s:
            raise ProbeError(
                "PROBE_DEADLINE_EXCEEDED", f"deadline {deadline_s:.3f} already passed")

        torch = self._ports.torch_module()
        backends = getattr(torch, "backends", None)
        mps_backend = getattr(backends, "mps", None)
        if mps_backend is None or not callable(getattr(mps_backend, "is_built", None)):
            raise ProbeError("MPS_UNAVAILABLE", "torch.backends.mps absent")
        if not mps_backend.is_built():
            raise ProbeError("MPS_UNAVAILABLE", "torch.backends.mps.is_built() is false")
        if not callable(getattr(mps_backend, "is_available", None)) or not \
                mps_backend.is_available():
            raise ProbeError("MPS_UNAVAILABLE", "torch.backends.mps.is_available() is false")

        recommended = _require_optional_bytes(
            "MPS_RECOMMENDED_MEMORY", getattr(torch.mps, "recommended_max_memory", None),
            required=True,
        )
        current = _require_optional_bytes(
            "MPS_CURRENT_ALLOCATED", getattr(torch.mps, "current_allocated_memory", None))
        driver = _require_optional_bytes(
            "MPS_DRIVER_ALLOCATED", getattr(torch.mps, "driver_allocated_memory", None))

        if clock() > deadline_s:
            raise ProbeError("PROBE_DEADLINE_EXCEEDED", "after torch MPS reads")

        try:
            raw = self._ports.vm_stat()
        except ProbeError:
            raise
        except Exception as error:  # noqa: BLE001 - any helper failure is a refusal
            raise ProbeError("VM_STAT_FAILED", f"{type(error).__name__}: {error}") from error
        reading = parse_vm_stat(raw, total_bytes=self._ports.total_bytes())

        if clock() > deadline_s:
            raise ProbeError("PROBE_DEADLINE_EXCEEDED", "after vm_stat read")

        available = min(reading.available_bytes, recommended)
        version = str(getattr(torch, "__version__", "unknown"))
        return AcceleratorSnapshot(
            kind="mps",
            selector="default",
            available_bytes=available,
            recommended_max_memory_bytes=recommended,
            current_allocated_memory_bytes=current,
            driver_allocated_memory_bytes=driver,
            metric_source=(
                f"{ADMISSION_KIND}:vm_stat(host_available)+torch.mps.recommended_max_memory"
                f"@torch{version}"
            ),
        )

    # -- helper access for evidence/tests -------------------------------------------------

    def read_vm_stat_bounded(self, *, timeout_s: float) -> str:
        """Call the configured vm_stat port; the default port is itself bounded."""

        return self._ports.vm_stat()


def _require_optional_bytes(name: str, getter: object, *, required: bool = False
                            ) -> int | None:
    """Call an optional torch memory getter and validate its value strictly."""

    if getter is None:
        if required:
            raise ProbeError(f"{name}_MISSING", "getter absent")
        return None
    try:
        value = getter()
    except ProbeError:
        raise
    except Exception as error:  # noqa: BLE001 - a torch failure is a refusal
        raise ProbeError(f"{name}_FAILED", f"{type(error).__name__}: {error}") from error
    if value is None:
        if required:
            raise ProbeError(f"{name}_MISSING", "returned None")
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProbeError(f"{name}_INVALID", f"{value!r} is not an int")
    if value <= 0 and required:
        raise ProbeError(f"{name}_INVALID", f"{value!r} is not positive")
    if value < 0:
        raise ProbeError(f"{name}_INVALID", f"{value!r} is negative")
    return value


def evaluate_accelerator_snapshot(snapshot: AcceleratorSnapshot,
                                  policy: StartGuardPolicy) -> AcceleratorEvaluation:
    """The v4 decision: is the unified-memory proxy at or above the fixed headroom floor?"""

    if not isinstance(snapshot, AcceleratorSnapshot):
        raise ValueError("snapshot must be an AcceleratorSnapshot")
    if not isinstance(policy, StartGuardPolicy):
        raise ValueError("policy must be a StartGuardPolicy")
    floor = policy.mps_minimum_headroom_bytes
    if floor is None:
        raise ProbeError(
            "MPS_MINIMUM_HEADROOM_BYTES", "the Darwin combination requires the fixed floor")
    if snapshot.kind != "mps":
        raise ProbeError("ACCELERATOR_KIND", f"{snapshot.kind} is not the MPS combination")

    status = PASS if snapshot.available_bytes >= floor else FAIL
    reason = "MPS_HEADROOM_OK" if status == PASS else "MPS_HEADROOM_BELOW_MINIMUM"
    check = GuardCheck(status, reason, snapshot.available_bytes, floor, "bytes")
    return AcceleratorEvaluation(
        status=status,
        checks={"mps_headroom": check},
        metric_source=snapshot.metric_source,
    )


# --------------------------------------------------------------------------------------
# probe selection
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class MpsAcceleratorProbeSelection:
    """The selected probe plus the admission label it is allowed to claim."""

    probe: AcceleratorProbe
    admission_kind: str = ADMISSION_KIND


def select_accelerator_probe(kind: str) -> MpsAcceleratorProbeSelection | None:
    """Return the MPS probe for the Darwin combination; `None` keeps the v3 NVML path.

    There is deliberately no CPU or "auto" branch: a schema that asks for MPS gets the MPS
    probe or a refusal, and a schema that asks for CUDA keeps using the NVML-backed v3 path.
    """

    if kind == "mps":
        return MpsAcceleratorProbeSelection(probe=DarwinMpsAcceleratorProbe())
    if kind == "cuda":
        return None
    raise ProbeError("ACCELERATOR_KIND", f"unknown accelerator kind {kind!r}")


# --------------------------------------------------------------------------------------
# module entry point: the bounded helper the coordinator may run as a subprocess
# --------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="so101_demo.parallel_batch.accelerator_probe",
        description="Read one bounded Darwin MPS accelerator snapshot as JSON.",
    )
    parser.add_argument("--deadline-monotonic-ns", type=int, required=True)
    return parser


def snapshot_to_document(snapshot: AcceleratorSnapshot) -> dict:
    return {
        "kind": snapshot.kind,
        "selector": snapshot.selector,
        "available_bytes": snapshot.available_bytes,
        "recommended_max_memory_bytes": snapshot.recommended_max_memory_bytes,
        "current_allocated_memory_bytes": snapshot.current_allocated_memory_bytes,
        "driver_allocated_memory_bytes": snapshot.driver_allocated_memory_bytes,
        "metric_source": snapshot.metric_source,
    }


def main(argv: list[str] | None = None) -> int:
    import json

    args = build_parser().parse_args(argv)
    try:
        snapshot = DarwinMpsAcceleratorProbe().probe(
            deadline_monotonic_ns=args.deadline_monotonic_ns)
    except ProbeError as error:
        print(json.dumps({"error": error.reason, "detail": error.detail}))
        return 1
    print(json.dumps(snapshot_to_document(snapshot)))
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    sys.exit(main())
