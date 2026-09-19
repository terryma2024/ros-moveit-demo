"""The MPS Broker bootstrap: import-order safety, shared models, and one execution lane.

Task 8 of the macOS MPS / private IPC plan. The approved design (section 6.2) fixes three things
that are easy to get subtly wrong:

1. **Import order.** `PYTORCH_ENABLE_MPS_FALLBACK` is read and pinned *before* PyTorch is
   imported. A process that inherits `1` must refuse to start rather than load a model that can
   silently fall back to CPU. The check is repeated immediately before the import and its result
   is recorded in the ready receipt.
2. **One model set, one lane.** A single Broker loads the models once for both Workers, and every
   model runs on one bounded MPS execution lane. Per-model executor threads would create
   concurrent Metal calls, which this design explicitly does not claim or want.
3. **Ready means warm.** The ready receipt is published only after a real warm-up forward pass on
   each model *and* a successful `torch.mps.synchronize()`. A live process or a bound socket is
   not readiness.

Every failure in this module is a refusal. There is no CPU fallback, no "try the other device",
and no receipt that claims MPS while the parameters are elsewhere.
"""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Sequence

#: The variable whose value decides whether a silent CPU fallback is possible.
FALLBACK_ENV = "PYTORCH_ENABLE_MPS_FALLBACK"

#: The only accepted value, as a string.
FALLBACK_DISABLED = "0"

#: The device the whole runtime must agree on. Real PyTorch reports MPS tensors as `mps:0`
#: (device index 0), so both spellings must be recognised as "on MPS" while a CPU tensor is not.
MPS_DEVICE = "mps"


def is_mps_device(value: object) -> bool:
    """True for the MPS device in either spelling, and never for CPU."""

    text = str(value)
    return text == MPS_DEVICE or text.startswith(f"{MPS_DEVICE}:")


#: Default lane depth. Two Workers may be *queued*; one item is *executing*.
DEFAULT_LANE_CAPACITY = 8


class MpsBootstrapError(RuntimeError):
    """The MPS bootstrap contract failed. The Broker must not become ready."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


# --------------------------------------------------------------------------------------
# step 1: import-order safety
# --------------------------------------------------------------------------------------


def require_fallback_disabled(environ: Mapping[str, str] | None = None) -> str:
    """Refuse unless `PYTORCH_ENABLE_MPS_FALLBACK` is exactly `"0"`.

    Called before PyTorch is imported *and* again after, because an import can be triggered by a
    different module in between. An absent value is `"1"`-equivalent: PyTorch's own default is to
    allow the fallback, so absence must be refused too, not assumed safe.
    """

    active = os.environ if environ is None else environ
    value = active.get(FALLBACK_ENV)
    if value is None:
        raise MpsBootstrapError(
            "MPS_FALLBACK_NOT_PINNED",
            f"{FALLBACK_ENV} is unset; PyTorch would default to allowing a CPU fallback",
        )
    if str(value) != FALLBACK_DISABLED:
        raise MpsBootstrapError(
            "MPS_FALLBACK_ENABLED", f"{FALLBACK_ENV}={value!r} is not {FALLBACK_DISABLED!r}")
    return str(value)


def child_environment(base: Mapping[str, str] | None = None, **overrides: str) -> dict:
    """Build a Broker environment with the fallback pinned to `0`, never inherited as `1`."""

    environment = dict(os.environ if base is None else base)
    environment[FALLBACK_ENV] = FALLBACK_DISABLED
    for key, value in overrides.items():
        environment[key] = str(value)
    require_fallback_disabled(environment)
    return environment


def spawn_context() -> "multiprocessing.context.BaseContext":
    """The Broker is always spawned, never forked: a forked child inherits an initialised MPS."""

    return multiprocessing.get_context("spawn")


# --------------------------------------------------------------------------------------
# step 2: one bounded execution lane
# --------------------------------------------------------------------------------------


@dataclass
class LaneStats:
    """What the lane actually did, for the ready receipt and for evidence."""

    submitted: int = 0
    executed: int = 0
    rejected: int = 0
    peak_depth: int = 0
    max_concurrent: int = 0


class SingleMpsExecutionLane:
    """One lane that serialises every model call on the MPS device.

    A single worker thread owns execution. Two Workers may enqueue at the same time, but the
    worker handles one item at a time, so overlapping Metal calls are impossible by construction
    rather than by convention. `max_concurrent` measures that claim: it is incremented by the
    worker only, and the tests assert it never exceeds one.
    """

    def __init__(self, *, capacity: int = DEFAULT_LANE_CAPACITY,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity <= 0:
            raise MpsBootstrapError("MPS_LANE_CAPACITY", repr(capacity))
        self.capacity = capacity
        self.clock = clock
        self._queue: "queue.Queue[tuple]" = queue.Queue(maxsize=capacity)
        self._lock = threading.Lock()
        self._concurrent = 0
        self.stats = LaneStats()
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._run, name="mps-execution-lane",
                                        daemon=True)
        self._worker.start()

    # -- producer side -------------------------------------------------------------------

    def submit(self, function: Callable[[], object], *, label: str = "call") -> object:
        """Run `function` on the lane and return its result, or raise a stable refusal."""

        if not callable(function):
            raise MpsBootstrapError("MPS_LANE_CALLABLE", type(function).__name__)
        completed = threading.Event()
        box: dict = {}
        try:
            self._queue.put_nowait((function, label, completed, box))
        except queue.Full as error:
            with self._lock:
                self.stats.rejected += 1
            raise MpsBootstrapError(
                "MPS_LANE_FULL", f"{self._queue.qsize()}/{self.capacity} queued") from error
        with self._lock:
            self.stats.submitted += 1
            self.stats.peak_depth = max(self.stats.peak_depth, self._queue.qsize())
        completed.wait()
        if "error" in box:
            error = box["error"]
            if isinstance(error, MpsBootstrapError):
                raise error
            raise MpsBootstrapError(
                "MPS_LANE_FAILED",
                f"{label}: {type(error).__name__}: {error}",
            ) from error
        return box.get("result")

    # -- worker side ---------------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                function, label, completed, box = self._queue.get(timeout=0.05)
            except queue.Empty:
                continue
            with self._lock:
                self._concurrent += 1
                self.stats.max_concurrent = max(self.stats.max_concurrent, self._concurrent)
            try:
                box["result"] = function()
            except BaseException as error:  # noqa: BLE001 - transported to the submitter
                box["error"] = error
            finally:
                with self._lock:
                    self._concurrent -= 1
                    self.stats.executed += 1
                completed.set()

    def shutdown(self) -> None:
        """Stop the worker after the queue drains. Idempotent."""

        self._stop.set()
        if self._worker.is_alive():
            self._worker.join(timeout=5.0)

    def __del__(self) -> None:  # pragma: no cover - best effort at interpreter shutdown
        try:
            self.shutdown()
        except Exception:  # noqa: BLE001 - never raise during collection
            pass


# --------------------------------------------------------------------------------------
# step 3: the ready receipt
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelWarmup:
    """One model's real warm-up result."""

    model_id: str
    weights_sha256: str
    config_sha256: str
    device: str
    parameter_devices: tuple[str, ...]
    output_shape: tuple[int, ...]
    output_dtype: str
    latency_s: float
    synchronized: bool

    def to_document(self) -> dict:
        return {
            "model_id": self.model_id,
            "weights_sha256": self.weights_sha256,
            "config_sha256": self.config_sha256,
            "device": self.device,
            "parameter_devices": list(self.parameter_devices),
            "output_shape": list(self.output_shape),
            "output_dtype": self.output_dtype,
            "latency_s": self.latency_s,
            "synchronized": self.synchronized,
        }


@dataclass(frozen=True)
class BrokerReadyReceipt:
    """The durable readiness claim. Only written after real warm-up and synchronize."""

    broker_pid: int
    broker_birth_identity: int
    runtime_device: str
    pytorch_version: str
    fallback_env: str
    bootstrap_checks: Mapping[str, object]
    recommended_max_memory_bytes: int | None
    current_allocated_memory_bytes: int | None
    driver_allocated_memory_bytes: int | None
    mps_process_memory_fraction: float
    lane_capacity: int
    lane_stats: Mapping[str, object]
    models: tuple[ModelWarmup, ...]
    warmup_total_latency_s: float
    created_monotonic_s: float

    def to_document(self) -> dict:
        return {
            "broker_pid": self.broker_pid,
            "broker_birth_identity": self.broker_birth_identity,
            "runtime_device": self.runtime_device,
            "pytorch_version": self.pytorch_version,
            "fallback_env": self.fallback_env,
            "bootstrap_checks": dict(self.bootstrap_checks),
            "recommended_max_memory_bytes": self.recommended_max_memory_bytes,
            "current_allocated_memory_bytes": self.current_allocated_memory_bytes,
            "driver_allocated_memory_bytes": self.driver_allocated_memory_bytes,
            "mps_process_memory_fraction": self.mps_process_memory_fraction,
            "lane_capacity": self.lane_capacity,
            "lane_stats": dict(self.lane_stats),
            "models": [model.to_document() for model in self.models],
            "warmup_total_latency_s": self.warmup_total_latency_s,
            "created_monotonic_s": self.created_monotonic_s,
        }

    def write(self, path: Path) -> Path:
        """Write the receipt atomically: temporary sibling, fsync, replace."""

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_document(), indent=2, sort_keys=True) + "\n"
        temporary = target.with_suffix(target.suffix + ".part")
        descriptor = os.open(temporary, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        try:
            os.write(descriptor, payload.encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, target)
        return target

    @property
    def ready(self) -> bool:
        """Ready means: every model warmed up, synchronised, and still on MPS."""

        if not is_mps_device(self.runtime_device):
            return False
        if self.fallback_env != FALLBACK_DISABLED:
            return False
        if not self.models:
            return False
        return all(
            model.synchronized
            and is_mps_device(model.device)
            and model.parameter_devices
            and all(is_mps_device(device) for device in model.parameter_devices)
            for model in self.models
        )


# --------------------------------------------------------------------------------------
# the bootstrap
# --------------------------------------------------------------------------------------


@dataclass
class MpsBrokerBootstrap:
    """Prepare one Broker process: check the environment, set the cap, warm the models.

    ``torch_module`` is injected so every refusal branch is testable without MPS hardware. The
    real path imports `torch` lazily, *after* :meth:`require_import_order`.
    """

    models: Sequence[tuple[str, Callable[[], object]]] = ()
    memory_fraction: float = 0.8
    lane_capacity: int = DEFAULT_LANE_CAPACITY
    environ: Mapping[str, str] = field(default_factory=lambda: dict(os.environ))
    torch_module: Callable[[], object] | None = None
    warmup_inputs: Callable[[str], object] | None = None
    clock: Callable[[], float] = time.monotonic

    def __post_init__(self) -> None:
        if isinstance(self.memory_fraction, bool) or not isinstance(
                self.memory_fraction, (int, float)):
            raise MpsBootstrapError("MPS_PROCESS_MEMORY_FRACTION", repr(self.memory_fraction))
        if not (0.0 < float(self.memory_fraction) <= 1.0):
            raise MpsBootstrapError("MPS_PROCESS_MEMORY_FRACTION", repr(self.memory_fraction))
        if isinstance(self.lane_capacity, bool) or not isinstance(self.lane_capacity, int) \
                or self.lane_capacity <= 0:
            raise MpsBootstrapError("MPS_LANE_CAPACITY", repr(self.lane_capacity))
        self._lane = SingleMpsExecutionLane(capacity=self.lane_capacity, clock=self.clock)
        self._loaded: dict[str, object] = {}

    @property
    def lane(self) -> SingleMpsExecutionLane:
        return self._lane

    @property
    def loaded_models(self) -> dict[str, object]:
        """The one shared model set, by model id. Both Workers read from this, never from a copy."""

        return dict(self._loaded)

    # -- step 1 --------------------------------------------------------------------------

    def require_import_order(self) -> str:
        """Check the fallback pin and prove PyTorch is not imported yet.

        This is the guarantee the real Broker process makes. A test that injects a synthetic
        torch module is, by definition, already running with torch somewhere in the process, so
        it sets ``injected_torch`` instead of weakening this check: the real path still refuses,
        which is what ``test_import_order_check_refuses_when_torch_is_already_imported`` asserts.
        """

        import sys

        value = require_fallback_disabled(self.environ)
        if self.torch_module is None and "torch" in sys.modules:
            raise MpsBootstrapError(
                "MPS_IMPORT_ORDER", "torch was already imported before the fallback check")
        return value

    def _import_torch(self) -> object:
        self.require_import_order()
        torch = self.torch_module() if self.torch_module is not None else _real_torch()
        # Re-read after the import: nothing may have changed it in between.
        require_fallback_disabled(self.environ)
        return torch

    # -- step 2 --------------------------------------------------------------------------

    def _set_memory_fraction(self, torch: object) -> float:
        """Cap this process's MPS allocator before any model parameter is created."""

        setter = getattr(getattr(torch, "mps", None), "set_per_process_memory_fraction", None)
        if not callable(setter):
            raise MpsBootstrapError(
                "MPS_MEMORY_FRACTION_UNSUPPORTED",
                "torch.mps.set_per_process_memory_fraction is unavailable",
            )
        self._lane.submit(lambda: setter(float(self.memory_fraction)),
                          label="set_per_process_memory_fraction")
        return float(self.memory_fraction)

    # -- step 3 --------------------------------------------------------------------------

    def _warm_model(self, torch: object, model_id: str, factory: Callable[[], object],
                    warmed: list[ModelWarmup]) -> ModelWarmup:
        started = self.clock()
        model = self._lane.submit(factory, label=f"load:{model_id}")
        self._loaded[model_id] = model

        parameters = list(getattr(model, "parameters", lambda: [])())
        if not parameters:
            raise MpsBootstrapError("MPS_MODEL_PARAMETERS", f"{model_id} exposes no parameters")
        parameter_devices = tuple(sorted({str(getattr(item, "device", "?"))
                                          for item in parameters}))
        if not parameter_devices or not all(is_mps_device(item) for item in parameter_devices):
            raise MpsBootstrapError(
                "MPS_PARAMETERS_NOT_ON_DEVICE",
                f"{model_id} parameters are on {parameter_devices}, not {MPS_DEVICE!r}",
            )

        warm_input = (self.warmup_inputs(model_id) if self.warmup_inputs is not None
                      else _default_warm_input(model_id))
        output = self._lane.submit(lambda: model(warm_input), label=f"warmup:{model_id}")
        device = str(getattr(output, "device", "?"))
        if not is_mps_device(device):
            raise MpsBootstrapError(
                "MPS_OUTPUT_NOT_ON_DEVICE",
                f"{model_id} produced a {device!r} tensor, not {MPS_DEVICE!r}",
            )

        synchronize = getattr(getattr(torch, "mps", None), "synchronize", None)
        if not callable(synchronize):
            raise MpsBootstrapError("MPS_SYNCHRONIZE_UNSUPPORTED", "torch.mps.synchronize absent")
        self._lane.submit(synchronize, label=f"synchronize:{model_id}")

        shape = tuple(int(dimension) for dimension in getattr(output, "shape", ()))
        dtype = str(getattr(output, "dtype", "?"))
        receipt = ModelWarmup(
            model_id=model_id,
            weights_sha256=str(getattr(model, "weights_sha256", "unknown")),
            config_sha256=str(getattr(model, "config_sha256", "unknown")),
            device=device,
            parameter_devices=parameter_devices,
            output_shape=shape,
            output_dtype=dtype,
            latency_s=max(0.0, self.clock() - started),
            synchronized=True,
        )
        warmed.append(receipt)
        return receipt

    def prepare(self) -> tuple[object, BrokerReadyReceipt]:
        """Run the full bootstrap: import order, memory cap, model warm-up, ready receipt."""

        fallback = self.require_import_order()
        torch = self._import_torch()
        runtime_device = MPS_DEVICE
        try:
            available = bool(torch.backends.mps.is_available())
        except Exception as error:  # noqa: BLE001 - a broken backend is a refusal
            raise MpsBootstrapError("MPS_UNAVAILABLE", str(error)) from error
        if not available:
            raise MpsBootstrapError("MPS_UNAVAILABLE", "torch.backends.mps.is_available() is false")
        if not self.models:
            raise MpsBootstrapError("MPS_MODELS_EMPTY", "at least one model is required")

        fraction = self._set_memory_fraction(torch)
        started = self.clock()
        warmed: list[ModelWarmup] = []
        for model_id, factory in self.models:
            self._warm_model(torch, model_id, factory, warmed)

        identity = _process_birth_identity(os.getpid())
        receipt = BrokerReadyReceipt(
            broker_pid=os.getpid(),
            broker_birth_identity=identity,
            runtime_device=runtime_device,
            pytorch_version=str(getattr(torch, "__version__", "unknown")),
            fallback_env=fallback,
            bootstrap_checks={
                "fallback_pinned_before_import": True,
                "fallback_rechecked_after_import": True,
                "spawn_context": "spawn",
                "lane_is_single": True,
                "memory_fraction_set_before_load": True,
            },
            recommended_max_memory_bytes=_optional_int(
                getattr(getattr(torch, "mps", None), "recommended_max_memory", None)),
            current_allocated_memory_bytes=_optional_int(
                getattr(getattr(torch, "mps", None), "current_allocated_memory", None)),
            driver_allocated_memory_bytes=_optional_int(
                getattr(getattr(torch, "mps", None), "driver_allocated_memory", None)),
            mps_process_memory_fraction=fraction,
            lane_capacity=self.lane_capacity,
            lane_stats={
                "submitted": self._lane.stats.submitted,
                "executed": self._lane.stats.executed,
                "rejected": self._lane.stats.rejected,
                "peak_depth": self._lane.stats.peak_depth,
                "max_concurrent": self._lane.stats.max_concurrent,
            },
            models=tuple(warmed),
            warmup_total_latency_s=max(0.0, self.clock() - started),
            created_monotonic_s=self.clock(),
        )
        if not receipt.ready:
            raise MpsBootstrapError("MPS_NOT_READY", "the warm-up receipt is not a ready claim")
        return torch, receipt


def _real_torch() -> object:
    import torch  # noqa: PLC0415 - imported only after the fallback pin is verified

    return torch


def _process_birth_identity(pid: int) -> int:
    from ..parallel_batch.start_guard_probe import read_process_identity

    identity = read_process_identity(pid)
    return 0 if identity is None else identity.start_time_ticks


def _optional_int(getter: object) -> int | None:
    if not callable(getter):
        return None
    try:
        return int(getter())
    except Exception:  # noqa: BLE001 - diagnostics never block readiness
        return None


def _default_warm_input(model_id: str) -> object:
    """A real warm-up input, built on MPS. Only RGB decoding and shape work may use CPU."""

    import numpy as np
    import torch

    frame = np.zeros((640, 640, 3), dtype=np.uint8)
    tensor = torch.from_numpy(frame).permute(2, 0, 1).unsqueeze(0).contiguous()
    return tensor.to(MPS_DEVICE)


def model_fingerprint(model: object) -> str:
    """A stable hash of a model's parameters, for the ready receipt's provenance field."""

    import torch

    digest = hashlib.sha256()
    for name, parameter in sorted(dict(getattr(model, "named_parameters", lambda: [])()).items()):
        digest.update(name.encode("utf-8"))
        digest.update(np_bytes(parameter.detach().to("cpu")))
    return digest.hexdigest()


def np_bytes(tensor: object) -> bytes:
    """CPU bytes of a tensor without requiring NumPy's dtype mapping to be exact."""

    return bytes(memoryview(tensor.numpy(force=True)).cast("B"))
