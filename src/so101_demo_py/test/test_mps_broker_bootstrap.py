"""The MPS Broker bootstrap: import order, one lane, and a ready receipt that means "warm".

Task 8 of the macOS MPS / private IPC plan. The environment checks run against *real* child
processes, because "the child refuses before importing torch" is a statement about a process, not
about a function. The lane and warm-up checks run against a synthetic torch seam so every refusal
branch is reachable without MPS hardware; the real-device smoke is a separate gate.
"""

import json
import os
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="MPS broker bootstrap is macOS-only")

from so101_demo.runtime.mps_broker_bootstrap import (
    FALLBACK_ENV,
    MPS_DEVICE,
    BrokerReadyReceipt,
    MpsBootstrapError,
    MpsBrokerBootstrap,
    ModelWarmup,
    SingleMpsExecutionLane,
    child_environment,
    require_fallback_disabled,
    spawn_context,
)

PYTHON = sys.executable

#: A child that imports torch and reports what happened. It proves the refusal happens before the
#: import by printing a marker *after* the import would have succeeded.
CHILD_IMPORT_PROBE = textwrap.dedent(
    """
    import json, os, sys

    document = {"fallback_env": os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK", "<unset>")}
    try:
        from so101_demo.runtime.mps_broker_bootstrap import MpsBootstrapError, require_fallback_disabled
    except Exception as error:  # pragma: no cover - import must work
        print(json.dumps({"import_error": f"{type(error).__name__}: {error}"}))
        raise SystemExit(3)

    try:
        document["checked"] = require_fallback_disabled()
    except MpsBootstrapError as error:
        document["refused"] = error.reason
        print(json.dumps(document))
        raise SystemExit(1)

    # Only reached when the pin is correct: now it is safe to import torch.
    import torch
    document["torch_imported"] = True
    document["torch_version"] = torch.__version__
    print(json.dumps(document))
    """
)


class FakeTensor:
    """A tensor-shaped object: device, shape and dtype are what the receipt records."""

    def __init__(self, *, device=MPS_DEVICE, shape=(1, 3, 640, 640), dtype="torch.float32"):
        self.device = device
        self.shape = shape
        self.dtype = dtype


class FakeModule:
    """A model with parameters on a device, and a forward pass that records its calls."""

    def __init__(self, *, device=MPS_DEVICE, output_device=MPS_DEVICE, calls=None,
                 weights_sha256="w" * 64, config_sha256="c" * 64, parameters=True):
        self._parameters = ([type("P", (), {"device": device})()] if parameters else [])
        self._output_device = output_device
        self._calls = calls if calls is not None else []
        self.weights_sha256 = weights_sha256
        self.config_sha256 = config_sha256

    def parameters(self):
        return list(self._parameters)

    def __call__(self, value):
        self._calls.append((time.monotonic(), threading.get_ident()))
        return FakeTensor(device=self._output_device)


class FakeTorch:
    """The smallest torch surface the bootstrap is allowed to touch."""

    __version__ = "2.13.0"

    def __init__(self, *, available=True, recommended=16 << 30, current=1 << 30, driver=2 << 30,
                 fail_sync=False, fail_setter=False):
        self._available = available
        self._recommended = recommended
        self._current = current
        self._driver = driver
        self._fail_sync = fail_sync
        self._fail_setter = fail_setter
        self.set_fraction_calls = []
        self.sync_calls = 0

        outer = self

        class _Mps:
            @staticmethod
            def is_available():
                return outer._available

            @staticmethod
            def set_per_process_memory_fraction(fraction):
                if outer._fail_setter:
                    raise RuntimeError("memory fraction setter unavailable")
                outer.set_fraction_calls.append(fraction)

            @staticmethod
            def synchronize():
                outer.sync_calls += 1
                if outer._fail_sync:
                    raise RuntimeError("synchronize failed")

            @staticmethod
            def recommended_max_memory():
                return outer._recommended

            @staticmethod
            def current_allocated_memory():
                return outer._current

            @staticmethod
            def driver_allocated_memory():
                return outer._driver

        self.mps = _Mps()

        class _Backends:
            pass

        backends = _Backends()
        mps_backend = type("MpsBackend", (), {"is_available": staticmethod(
            lambda: outer._available)})()
        backends.mps = mps_backend
        self.backends = backends


def _bootstrap(fake, *, models=None, fraction=0.8, lane_capacity=8, environ=None):
    return MpsBrokerBootstrap(
        models=models if models is not None else (("yolo", FakeModule),),
        memory_fraction=fraction,
        lane_capacity=lane_capacity,
        environ=environ if environ is not None else {FALLBACK_ENV: "0"},
        torch_module=lambda: fake,
    )


# --------------------------------------------------------------------------------------
# import-order safety, proven in real child processes
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["1", "true", "yes", "", "0 ", "00"])
def test_child_refuses_before_importing_torch_when_the_fallback_is_not_zero(value):
    """An inherited or malformed fallback value stops the child before `import torch`."""

    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [p for p in sys.path if p] + [environment.get("PYTHONPATH", "")]).strip(os.pathsep)
    environment[FALLBACK_ENV] = value
    result = subprocess.run(
        [PYTHON, "-c", CHILD_IMPORT_PROBE], capture_output=True, text=True, timeout=120,
        env=environment,
    )
    assert result.returncode == 1, result.stderr[-2000:]
    document = json.loads(result.stdout.strip().splitlines()[-1])
    assert document["refused"] == "MPS_FALLBACK_ENABLED"
    assert "torch_imported" not in document


def test_child_refuses_when_the_fallback_variable_is_absent():
    """Absence is refused: PyTorch's own default would allow a silent CPU fallback."""

    environment = dict(os.environ)
    environment.pop(FALLBACK_ENV, None)
    result = subprocess.run(
        [PYTHON, "-c", CHILD_IMPORT_PROBE], capture_output=True, text=True, timeout=120,
        env=environment,
    )
    assert result.returncode == 1, result.stderr[-2000:]
    document = json.loads(result.stdout.strip().splitlines()[-1])
    assert document["refused"] == "MPS_FALLBACK_NOT_PINNED"
    assert "torch_imported" not in document


def test_child_with_the_correct_pin_imports_torch_normally():
    """With `PYTORCH_ENABLE_MPS_FALLBACK=0` the child proceeds and records the version."""

    environment = dict(os.environ)
    environment[FALLBACK_ENV] = "0"
    result = subprocess.run(
        [PYTHON, "-c", CHILD_IMPORT_PROBE], capture_output=True, text=True, timeout=300,
        env=environment,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    document = json.loads(result.stdout.strip().splitlines()[-1])
    assert document["torch_imported"] is True
    assert document["checked"] == "0"
    assert document["torch_version"]


def test_require_fallback_disabled_is_exact():
    """The check is a string comparison against `0`, not a truthiness test."""

    assert require_fallback_disabled({FALLBACK_ENV: "0"}) == "0"
    for bad in ("1", "0.0", "False", "", " 0"):
        with pytest.raises(MpsBootstrapError):
            require_fallback_disabled({FALLBACK_ENV: bad})
    with pytest.raises(MpsBootstrapError, match="MPS_FALLBACK_NOT_PINNED"):
        require_fallback_disabled({})


def test_child_environment_overrides_an_inherited_enabled_fallback():
    """An inherited `1` is replaced, never passed through."""

    inherited = {FALLBACK_ENV: "1", "OTHER": "kept"}
    built = child_environment(inherited)
    assert built[FALLBACK_ENV] == "0"
    assert built["OTHER"] == "kept"


def test_the_broker_context_is_spawn_not_fork():
    """A forked child would inherit an initialised MPS; the bootstrap uses spawn."""

    context = spawn_context()
    assert context.get_start_method() == "spawn"


def test_import_order_check_refuses_when_torch_is_already_imported():
    """If something imported torch first, the pin was not in effect: refuse.

    This runs against the *real* path (no injected torch module), which is the only configuration
    where "torch is already imported" is a meaningful statement.
    """

    import torch  # noqa: F401 - the point of the test

    assert "torch" in sys.modules
    bootstrap = MpsBrokerBootstrap(models=(("yolo", FakeModule),), memory_fraction=0.8,
                                   environ={FALLBACK_ENV: "0"})
    assert bootstrap.torch_module is None
    with pytest.raises(MpsBootstrapError, match="MPS_IMPORT_ORDER"):
        bootstrap.require_import_order()


# --------------------------------------------------------------------------------------
# memory fraction
# --------------------------------------------------------------------------------------


def test_memory_fraction_is_set_before_any_model_is_loaded():
    """The allocator cap is applied first, and its value is recorded in the receipt."""

    fake = FakeTorch()
    loaded = []

    def factory():
        loaded.append(len(fake.set_fraction_calls))
        return FakeModule()

    bootstrap = _bootstrap(fake, models=(("yolo", factory),))
    _torch, receipt = bootstrap.prepare()
    assert fake.set_fraction_calls == [0.8], "the cap must be set exactly once, before loading"
    assert loaded == [1], "the model must be loaded only after the cap exists"
    assert receipt.mps_process_memory_fraction == 0.8


@pytest.mark.parametrize("fraction", [0, 0.0, -0.1, 1.5, True, None, "0.8"])
def test_a_bad_memory_fraction_is_refused_at_construction(fraction):
    with pytest.raises(MpsBootstrapError, match="MPS_PROCESS_MEMORY_FRACTION"):
        MpsBrokerBootstrap(models=(("yolo", FakeModule),), memory_fraction=fraction,
                           environ={FALLBACK_ENV: "0"}, torch_module=lambda: FakeTorch())


def test_a_missing_memory_fraction_setter_is_a_refusal():
    fake = FakeTorch(fail_setter=True)
    bootstrap = _bootstrap(fake)
    with pytest.raises(MpsBootstrapError, match="MPS_LANE_FAILED"):
        bootstrap.prepare()


# --------------------------------------------------------------------------------------
# one lane
# --------------------------------------------------------------------------------------


def test_lane_serialises_execution_across_threads():
    """Concurrent submitters never overlap inside the lane: max_concurrent stays 1."""

    lane = SingleMpsExecutionLane(capacity=16)
    active = 0
    peak = 0
    lock = threading.Lock()

    def work():
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.005)
        with lock:
            active -= 1
        return "done"

    results = []
    threads = [threading.Thread(target=lambda: results.append(lane.submit(work)))
               for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert results == ["done"] * 8
    assert peak == 1, f"the lane executed {peak} calls concurrently"
    assert lane.stats.max_concurrent == 1
    assert lane.stats.executed == 8


def test_lane_rejects_when_full():
    """The lane is bounded: an over-capacity submission is refused, not queued forever."""

    lane = SingleMpsExecutionLane(capacity=2)
    blocker = threading.Event()
    entered = threading.Event()

    def blocking():
        entered.set()
        blocker.wait(timeout=10)
        return "ok"

    thread = threading.Thread(target=lambda: lane.submit(blocking))
    thread.start()
    assert entered.wait(timeout=5)
    # Fill the queue behind the executing item, then overflow it.
    filler = [threading.Thread(target=lambda: lane.submit(lambda: "x")) for _ in range(2)]
    for item in filler:
        item.start()
    time.sleep(0.05)
    with pytest.raises(MpsBootstrapError, match="MPS_LANE_FULL"):
        lane.submit(lambda: "overflow")
    assert lane.stats.rejected >= 1
    blocker.set()
    thread.join(timeout=10)
    for item in filler:
        item.join(timeout=10)


def test_lane_wraps_operator_failure_with_the_label():
    """An operator failure is reported with the labelled boundary that produced it."""

    lane = SingleMpsExecutionLane(capacity=2)

    def exploding():
        raise RuntimeError("unsupported operator")

    with pytest.raises(MpsBootstrapError, match="MPS_LANE_FAILED"):
        lane.submit(exploding, label="warmup:yolo")


def test_the_broker_lane_is_shared_and_never_per_model():
    """Two models use one lane object, so Metal calls cannot be concurrent by construction."""

    calls = []
    modules = {}

    def factory(model_id):
        def build():
            modules[model_id] = FakeModule(calls=calls)
            return modules[model_id]
        return build

    bootstrap = _bootstrap(
        FakeTorch(),
        models=(("yolo", factory("yolo")), ("grounded-sam", factory("grounded-sam"))),
    )
    _torch, receipt = bootstrap.prepare()
    assert bootstrap.lane.stats.max_concurrent == 1
    assert len(receipt.models) == 2
    assert {model.model_id for model in receipt.models} == {"yolo", "grounded-sam"}
    assert receipt.lane_stats["max_concurrent"] == 1


# --------------------------------------------------------------------------------------
# warm-up and the ready receipt
# --------------------------------------------------------------------------------------


def test_a_model_with_parameters_off_mps_blocks_ready():
    """Parameters on CPU are a refusal, not a warning: this is the no-CPU-fallback rule."""

    bootstrap = _bootstrap(FakeTorch(), models=(("yolo", lambda: FakeModule(device="cpu")),))
    with pytest.raises(MpsBootstrapError, match="MPS_PARAMETERS_NOT_ON_DEVICE"):
        bootstrap.prepare()


def test_an_output_tensor_off_mps_blocks_ready():
    """An output on CPU means the operator ran elsewhere: refuse."""

    bootstrap = _bootstrap(
        FakeTorch(), models=(("yolo", lambda: FakeModule(output_device="cpu")),))
    with pytest.raises(MpsBootstrapError, match="MPS_OUTPUT_NOT_ON_DEVICE"):
        bootstrap.prepare()


def test_a_failed_synchronize_blocks_ready():
    """Warm-up without a successful `torch.mps.synchronize()` is not readiness."""

    fake = FakeTorch(fail_sync=True)
    bootstrap = _bootstrap(fake, models=(("yolo", FakeModule),))
    with pytest.raises(MpsBootstrapError, match="MPS_LANE_FAILED"):
        bootstrap.prepare()
    assert fake.sync_calls == 1


def test_unavailable_mps_blocks_ready_without_any_allocation():
    """No MPS means no start: the setter must not even be called."""

    fake = FakeTorch(available=False)
    bootstrap = _bootstrap(fake)
    with pytest.raises(MpsBootstrapError, match="MPS_UNAVAILABLE"):
        bootstrap.prepare()
    assert fake.set_fraction_calls == []


def test_an_empty_model_set_blocks_ready():
    bootstrap = _bootstrap(FakeTorch(), models=())
    with pytest.raises(MpsBootstrapError, match="MPS_MODELS_EMPTY"):
        bootstrap.prepare()


def test_a_model_without_parameters_blocks_ready():
    bootstrap = _bootstrap(FakeTorch(), models=(("yolo", lambda: FakeModule(parameters=False)),))
    with pytest.raises(MpsBootstrapError, match="MPS_MODEL_PARAMETERS"):
        bootstrap.prepare()


def test_ready_receipt_carries_every_required_fact():
    """The receipt records identity, device, provenance, metrics, fraction, latency and shapes."""

    fake = FakeTorch()
    bootstrap = _bootstrap(fake, models=(("yolo", lambda: FakeModule()),))
    _torch, receipt = bootstrap.prepare()
    document = receipt.to_document()
    assert document["broker_pid"] == os.getpid()
    assert document["broker_birth_identity"] > 0
    assert document["runtime_device"] == MPS_DEVICE
    assert document["pytorch_version"] == "2.13.0"
    assert document["fallback_env"] == "0"
    assert document["recommended_max_memory_bytes"] == 16 << 30
    assert document["current_allocated_memory_bytes"] == 1 << 30
    assert document["driver_allocated_memory_bytes"] == 2 << 30
    assert document["mps_process_memory_fraction"] == 0.8
    assert document["lane_capacity"] == 8
    model = document["models"][0]
    assert model["model_id"] == "yolo"
    assert model["device"] == MPS_DEVICE
    assert model["parameter_devices"] == [MPS_DEVICE]
    assert model["output_shape"] == [1, 3, 640, 640]
    assert model["output_dtype"] == "torch.float32"
    assert model["latency_s"] >= 0
    assert model["synchronized"] is True
    assert document["warmup_total_latency_s"] >= 0
    assert receipt.ready is True


def test_receipt_write_is_atomic_and_readable(tmp_path):
    fake = FakeTorch()
    bootstrap = _bootstrap(fake, models=(("yolo", FakeModule),))
    _torch, receipt = bootstrap.prepare()
    path = receipt.write(tmp_path / "broker-ready.json")
    assert path.exists()
    on_disk = json.loads(path.read_text())
    assert on_disk["runtime_device"] == MPS_DEVICE
    assert list(path.parent.glob("*.part")) == []


def test_a_receipt_claiming_a_foreign_device_is_not_ready():
    """`ready` is derived from the recorded facts, not stored as a boolean."""

    model = ModelWarmup(model_id="yolo", weights_sha256="w" * 64, config_sha256="c" * 64,
                        device="cpu", parameter_devices=("cpu",), output_shape=(1,),
                        output_dtype="torch.float32", latency_s=0.1, synchronized=True)
    receipt = BrokerReadyReceipt(
        broker_pid=os.getpid(), broker_birth_identity=1, runtime_device="cpu",
        pytorch_version="2.13.0", fallback_env="0", bootstrap_checks={},
        recommended_max_memory_bytes=None, current_allocated_memory_bytes=None,
        driver_allocated_memory_bytes=None, mps_process_memory_fraction=0.8, lane_capacity=8,
        lane_stats={}, models=(model,), warmup_total_latency_s=0.1, created_monotonic_s=0.0)
    assert receipt.ready is False


def test_a_receipt_on_the_wrong_fallback_value_is_not_ready():
    model = ModelWarmup(model_id="yolo", weights_sha256="w" * 64, config_sha256="c" * 64,
                        device=MPS_DEVICE, parameter_devices=(MPS_DEVICE,), output_shape=(1,),
                        output_dtype="torch.float32", latency_s=0.1, synchronized=True)
    receipt = BrokerReadyReceipt(
        broker_pid=os.getpid(), broker_birth_identity=1, runtime_device=MPS_DEVICE,
        pytorch_version="2.13.0", fallback_env="1", bootstrap_checks={},
        recommended_max_memory_bytes=None, current_allocated_memory_bytes=None,
        driver_allocated_memory_bytes=None, mps_process_memory_fraction=0.8, lane_capacity=8,
        lane_stats={}, models=(model,), warmup_total_latency_s=0.1, created_monotonic_s=0.0)
    assert receipt.ready is False


def test_mps_device_index_spelling_is_accepted_but_cpu_never_is():
    """Real PyTorch reports `mps:0`; the check must accept it and still refuse CPU."""

    from so101_demo.runtime.mps_broker_bootstrap import is_mps_device

    assert is_mps_device("mps") is True
    assert is_mps_device("mps:0") is True
    assert is_mps_device("cpu") is False
    assert is_mps_device("cuda:0") is False
    assert is_mps_device(None) is False
    assert is_mps_device("mpsx") is False

    # And a model whose parameters report the indexed spelling still becomes ready.
    bootstrap = _bootstrap(FakeTorch(),
                           models=(("yolo", lambda: FakeModule(device="mps:0",
                                                               output_device="mps:0")),))
    _torch, receipt = bootstrap.prepare()
    assert receipt.ready is True
    assert receipt.models[0].parameter_devices == ("mps:0",)
