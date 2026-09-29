"""P1-1 (rereview4): the FORMAL measurement entry must execute.

The verdict's words: *"connect the real CLI -> admitted context -> production adapters with all required parameters and
matching protocols. Add a RED/GREEN success test that does not use `--driver` and does not replace the whole providers
object; replace only bottom external ROS/MuJoCo/model I/O."*

So this file drives `measure.main` with **no `--driver`** and with the **provider seam removed**, and substitutes exactly
two things - the MuJoCo/ROS client and the detector model - through the bottom-I/O seam. Everything between them (the
composition, its ordering, the driver, the seal) is production code.

Today it must fail, and the ledger names why: the CLI's context carries no `calibration_report`, so
`_admitted_controller_config` refuses with `PRODUCTION_CALIBRATION_REPORT_REQUIRED`; the composition then requires an
`io_client` that nothing supplies (`PRODUCTION_CONTROLLER_ADAPTER_REQUIRED`); and the driver calls the real
`YoloSegDetector` as if it were callable when its interface is `detect(frame, query)`.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

BOTTOM_IO_ENV = "SO101_TASK8_BOTTOM_IO_SEAM"
PROVIDER_SEAM_ENV = "SO101_TASK8_PROVIDER_SEAM"

BOTTOM_IO_MODULE = '''"""Only the two bottom boundaries: the MuJoCo/ROS client and the detector model."""

import pathlib

# `with_name`, not `with_suffix`: the module's name is unique per run, so replacing the suffix would move the record
# file's name with it and the test would read a path nothing writes
RECORDED = pathlib.Path(__file__).with_name("bottom_io.seen")


def client():
    """The repo's OWN canned client, reused rather than re-imitated.

    My first stand-in answered every call with `True`/`{}`, captured no anchors, and sealed a batch the schema legitimately
    refuses - which the composition suite's own comment predicts. This is the same boundary, substituted faithfully.
    """

    from test_act_task8_production_composition_contract import CannedMujocoClient

    RECORDED.write_text("client")
    return CannedMujocoClient()


def phase_path(phase):
    """The run's phase path at the admitted 2 ms cadence - the trajectory the replay must sample."""

    joints = [0.0] * 7
    joints[6] = {"SEARCH": 0.0, "APPROACH": 0.1}.get(phase, 0.2)
    return {"samples": [{"t_s": index * 0.002, "joints_rad": list(joints)} for index in range(11)]}


def target():
    """What the camera is looking for - the cup the run's binding admits."""

    return {"class_id": "plastic_cup", "position_m": [0.10, 0.10, 0.02], "radius_m": 0.03}


def occluder_geometry():
    return {"fixed_fingertip_00": {"position_m": [0.02, 0.0, 0.10], "radius_m": 0.005}}


def frame_source(_request):
    RECORDED.write_text(RECORDED.read_text() + "+frame" if RECORDED.exists() else "frame")
    return object()


def detector_factory(*_args, **_kwargs):
    RECORDED.write_text(RECORDED.read_text() + "+detector" if RECORDED.exists() else "detector")
    return _Detector()


class _Client:
    """The stack adapter's lowest boundary: every call it delegates to is recorded and answered."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            if name in ("camera_info", "tf"):
                return {}
            if name == "search":
                return {"detections": []}
            if name == "probe":
                return {}
            return True
        return call


class _Detector:
    """The REAL detector protocol and the REAL return TYPE: `detect(frame, query)` -> `DetectionBatch`.

    P1-1 (rereview 5): this stand-in used to return a dictionary (`{"detections": []}`), which is why the protocol
    mismatch between the production detector and the driver stayed invisible - the adapter passed `detect()` through
    unchanged and only a real `DetectionBatch` fails to serialize. Substituting bottom I/O does not license substituting
    the interface, so this now builds the production type, with readers for the parts the record must carry.
    """

    cold_start_latency_ms = 1.0

    def detect(self, frame, query):
        del frame, query
        from so101_demo.core.detection import DetectionBatch

        return DetectionBatch(
            model_id="bottom-io-stand-in", weights_sha256="b" * 64, runtime_device="cuda",
            inference_latency_ms=0.0, image_width=640, image_height=480, candidates=())
'''


def _formal_run(tmp_path, monkeypatch):
    """Drive the formal entry: no `--driver`, no provider seam, only bottom I/O substituted."""

    from test_act_task8_measurement_runtime_descriptor import _context_document, _descriptor
    from so101_demo.act.task8_measurement_contract import bind_measurement_contract
    from test_act_task8_measurement_runtime_descriptor import TEMPLATE_V2
    from so101_demo.act.task8_measurement_contract import require_v2_identity
    from test_act_task8_calibration_aggregator import _cli_identities
    from so101_demo.cli import act_measure_task8_calibration as measure

    monkeypatch.delenv(PROVIDER_SEAM_ENV, raising=False)          # the verdict forbids this seam
    # a UNIQUE module name per run: `importlib.import_module` caches by name, so a fixed name would hand a later test
    # the earlier test's module - and with it the earlier test's `.seen` path
    module_name = f"bottom_io_{uuid.uuid4().hex}"
    (tmp_path / f"{module_name}.py").write_text(BOTTOM_IO_MODULE)
    monkeypatch.setenv(BOTTOM_IO_ENV,
                       f"{module_name}:client,{module_name}:detector_factory,{module_name}:frame_source,"
                       f"{module_name}:phase_path,{module_name}:target,{module_name}:occluder_geometry")

    identities_document = _cli_identities()
    identities = tmp_path / "identities.json"
    identities.write_text(json.dumps(identities_document))
    bound = bind_measurement_contract(TEMPLATE_V2, identities_document, tmp_path / "bound-v2.json")
    # the repo's own MATCHED pair (runtime descriptor + admitted calibration), reused rather than re-invented: a
    # mismatched pair is refused as HEAD_SEARCH_SAMPLE_MISMATCH, which is the binding doing its job
    from test_act_head_search_binding import _inputs

    runtime, calibration, _weights, _sample = _inputs(tmp_path)     # the first value IS the runtime descriptor
    document = _context_document(tmp_path, runtime)
    document["calibration_report"] = calibration
    document["session_id"] = "session-1"
    document["attempt_id"] = "attempt-1"
    document["search_start_rad"] = 0.0
    context_path = tmp_path / "context.json"
    context_path.write_text(json.dumps(document))
    require_v2_identity(identities_document)

    argv = ["--contract", str(bound), "--identities", str(identities),
            "--batch-root", str(tmp_path / "batch"), "--ledger", str(tmp_path / "ledger.md"),
            "--context", str(context_path)]
    sys.path.insert(0, str(tmp_path))
    return measure, argv


def test_the_formal_entry_seals_a_closed_batch_with_no_driver_and_no_provider_seam(tmp_path, monkeypatch):
    """The success test P1-1 asks for: every layer real except the two bottom boundaries."""

    measure, argv = _formal_run(tmp_path, monkeypatch)
    exit_code = measure.main(argv)
    ledger = tmp_path / "ledger.md"
    recorded = ledger.read_text() if ledger.is_file() else "(no ledger)"
    assert exit_code == 0, (
        f"the formal entry must succeed, not report {exit_code}; what it recorded was:\n{recorded}")

    sealed = json.loads((tmp_path / "batch" / "batch.json").read_bytes())
    assert sealed["status"] == "CLOSED", sealed["status"]
    assert sealed["cleanup"] is not None, "a CLOSED batch carries its cleanup proof"
    assert "runtime-descriptor.json" in set(sealed["files"]), "the descriptor travels into the sealed index"
    seen = (tmp_path / "bottom_io.seen").read_text()
    assert set(seen.split("+")) <= {"client", "detector", "frame"}, (
        f"only the bottom boundaries were substituted, saw {seen!r}")


def test_the_formal_path_exposes_the_missing_calibration_by_name(tmp_path, monkeypatch):
    """A missing parameter must be named as itself - the verdict's 'the same path must expose missing parameters'."""

    from so101_demo.act.task8_production_composition import ProductionCompositionError

    measure, argv = _formal_run(tmp_path, monkeypatch)
    # drop the one thing the composition validates first, and require the refusal to SAY SO
    context_path = Path(argv[argv.index("--context") + 1])
    document = json.loads(context_path.read_bytes())
    document.pop("calibration_report")
    context_path.write_text(json.dumps(document))
    with pytest.raises(ProductionCompositionError, match="PRODUCTION_CALIBRATION_REPORT_REQUIRED") as raised:
        measure.main(argv)
    assert "PRODUCTION_CALIBRATION_REPORT_REQUIRED" in str(raised.value)


def test_the_driver_uses_the_detectors_real_interface(tmp_path):
    """The interface half of P1-1: the production detector is `detect(frame, query)`, never `__call__`."""

    from so101_demo.adapters.perception.yolo_seg import YoloSegDetector

    assert hasattr(YoloSegDetector, "detect"), "the production detector's interface is detect()"
    # `hasattr(cls, "__call__")` is True for EVERY class, because the metaclass defines it - so the identity check is
    # the class's own namespace, not the attribute lookup the driver would do
    assert "__call__" not in vars(YoloSegDetector), (
        "the production detector declares no __call__, so a driver that calls it as a function cannot work")
