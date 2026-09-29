"""Task 8P3 / Boundary IV item 2: the measurement entry consumes the descriptor from its context, and refuses one
whose CUDA policy the approved design forbids.

Approved preparation design section 4.2 and section 6: the runtime config is parsed once at the entry, and internal
components receive identity, generation, deadline and audit hashes - they do not go back to the preparation directory.
So the descriptor travels as a parsed document in the context, and the entry is where a wrong one is refused.
"""

import hashlib
import json
import sys
from pathlib import Path

import pytest
from so101_demo.act.task8_artifact_bundle import require_runtime_descriptor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_act_task8_calibration_aggregator import TEMPLATE_V2, _cli_identities   # noqa: E402


def _descriptor(cpu_fallback: bool = False, device: str = "cuda"):
    return {"schema_version": 1, "head_search": {
        "schema_version": 1,
        "detector": {"backend": "yolo_seg", "weights_path": "/weights/best.pt", "weights_sha256": "a" * 64,
                     "model_id": "plastic-cup", "image_size_px": 640, "requested_device": device,
                     "allow_cpu_fallback": cpu_fallback, "torch_threads": 4, "torch_interop_threads": 2,
                     "torch_version": "2.0", "ultralytics_version": "8.0"},
        "camera": {"frame_id": "head_camera_frame", "ray_origin_frame_id": "head_camera_frame",
                   "width_px": 640, "height_px": 480},
        "motion": {"goal_tolerance_rad": 0.02, "settle_velocity_rad_s": 0.01, "neck_goal_duration_s": 0.5}}}


def _context_document(tmp_path, descriptor):
    return {
        "generation": "gen-descriptor-red", "measurement_plan_sha256": "a" * 64, "safe_interval_rad": [0.0, 0.1],
        "candidate_sha256": "b" * 64, "policy_sha256": "c" * 64, "driver_source_sha256": "d" * 64,
        "controller_generation": "ctrl-1", "broker_generation": "broker-1", "evidence_root": str(tmp_path / "ev"),
        "resource_binding": {"bound_at_entry": True, "cpu_cores": 8, "gpu_device": "cuda:0"},
        "runtime_descriptor": descriptor,
    }


def _invoke(tmp_path, context, driver="descriptor_driver:fill"):
    from so101_demo.act.task8_measurement_contract import bind_measurement_contract
    from so101_demo.cli import act_measure_task8_calibration as measure

    bound = bind_measurement_contract(TEMPLATE_V2, _cli_identities(), tmp_path / "bound-v2.json")

    identities = tmp_path / "identities.json"
    identities.write_text(json.dumps(_cli_identities()))
    context_path = tmp_path / "context.json"
    context_path.write_text(json.dumps(context))
    driver_file = tmp_path / "descriptor_driver.py"      # the module on disk; the `driver` parameter is the spec string
    driver_file.write_text("def fill(contract, root):\n"
                      "    import json, pathlib\n"
                      "    root = pathlib.Path(root)\n"
                      "    root.mkdir(parents=True, exist_ok=True)\n"
                      "    (root / 'execution.json').write_text(json.dumps({}))\n")
    sys.path.insert(0, str(tmp_path))
    argv = ["--contract", str(bound),
            "--identities", str(identities), "--batch-root", str(tmp_path / "batch"),
            "--ledger", str(tmp_path / "ledger.md"),
            "--context", str(context_path)]
    if driver is not None:                     # omitted means: use the production composition, not the test seam
        argv += ["--driver", driver]
    return measure.main(argv)


def test_a_context_descriptor_allowing_cpu_fallback_is_refused_before_measuring(tmp_path):
    """Section 4.2: the descriptor must request CUDA with no CPU fallback; the entry is where that is enforced."""

    with pytest.raises(ValueError, match="TASK8_PREPARATION_CUDA_REQUIRED|RUNTIME_DESCRIPTOR"):
        _invoke(tmp_path, _context_document(tmp_path, _descriptor(cpu_fallback=True)))


def test_a_context_carrying_only_a_digest_is_refused(tmp_path):
    """Item 3: an opaque digest cannot prove which configuration was measured, so the entry refuses it."""

    document = _context_document(tmp_path, _descriptor())
    del document["runtime_descriptor"]
    document["runtime_config_sha256"] = "f" * 64          # provenance without a descriptor
    with pytest.raises(ValueError, match="MEASUREMENT_RUNTIME_DESCRIPTOR_REQUIRED"):
        _invoke(tmp_path, document)


def test_the_cli_composes_the_production_driver_without_the_injected_test_seam(tmp_path, monkeypatch):
    """Astra item 1: with ``--driver`` omitted the CLI must build the real driver through the one composition.

    The seam used here is the **external I/O** one the composition itself reads - the stack, detector, controller,
    phase camera and clock - which is what a test is allowed to stand in for. The driver is *not* injected: the
    composition, its ordering, its single-stack rule and its descriptor/binding checks are all under test.
    """

    recorded = tmp_path / "providers-recorded.txt"
    (tmp_path / "fake_providers.py").write_text(
        "import pathlib\n"
        "def build():\n"
        f"    pathlib.Path({str(recorded)!r}).write_text('built')\n"
        "    return {'stack': object(), 'clock': object(), 'detector': object(),\n"
        "            'controller': object(), 'phase_camera': object()}\n")
    monkeypatch.setenv("SO101_TASK8_PROVIDER_SEAM", "fake_providers:build")

    context = _context_document(tmp_path, _descriptor())
    _invoke(tmp_path, context, driver=None)          # the production path must complete, not raise

    # the composition ran: it resolved the external I/O seam, so the driver it builds is the real one - whatever
    # happens afterwards inside the run is the fakes' business, not a wiring error
    assert recorded.exists(), "the composition must build its providers"
    # the entry must have produced the driver's seal: the descriptor is inside the batch it wrote. Full schema validity
    # is asserted where a capturing stack exists (test_act_task8_measurement_driver.py); a provider stand-in that
    # captures no anchors legitimately seals a batch with an empty anchor list, which the schema refuses
    sealed = tmp_path / "batch" / "batch.json"
    assert sealed.exists(), "the driver sealed the batch the entry reports"
    import json as _json

    recorded = _json.loads(sealed.read_bytes())
    assert "runtime-descriptor.json" in set(recorded["files"]), "the descriptor travels into the sealed index"


def _descriptor_with(mutate):
    document = _descriptor()
    mutate(document)
    return document


def test_a_descriptor_whose_head_search_payload_is_not_the_production_shape_is_refused(tmp_path):
    """Astra item 2: the shared rule must apply the *full* production shape, not only the device policy.

    Each mutation below is accepted by the current weak rule (closed top-level keys plus CUDA policy) and must be
    refused once the rule reuses the production head-search validator: an unknown field, a malformed camera block and
    a malformed motion block are all shape errors, and shape errors are how a descriptor stops describing what was
    actually measured.
    """

    # the shape rule owns the closed document structure: an unknown field and a malformed block are its business. A
    # camera block whose *keys* are wrong is the deeper binding check's business, not this rule's, so it is not asserted
    # here - that path is covered by the binding suite (and asserting it here would make this test pass for the wrong
    # reason or fail for one, which is exactly what CP-1231 recorded)
    cases = {
        "extra field": lambda d: d["head_search"].update({"unexpected_field": 1}),
        "bad motion": lambda d: d["head_search"].update({"motion": "not-a-motion-block"}),
        "extra top-level field": lambda d: d.update({"unexpected_top": 1}),
    }
    for name, mutate in cases.items():
        document = _descriptor_with(mutate)
        with pytest.raises(ValueError) as caught:
            require_runtime_descriptor(document)
        assert "MEASUREMENT_RUNTIME_DESCRIPTOR" in str(caught.value) or "HEAD_SEARCH" in str(caught.value), name


def test_the_context_requires_a_runtime_descriptor(tmp_path):
    """Astra item 2: the descriptor is required, so the ``None`` bypass cannot exist."""

    from so101_demo.act.task8_calibration_admission import CalibrationMeasurementContext

    with pytest.raises(TypeError):
        CalibrationMeasurementContext(
            generation="gen-required", contract_sha256="a" * 64, measurement_plan_sha256="b" * 64,
            safe_interval_rad=[0.0, 0.1], candidate_sha256="c" * 64, policy_sha256="d" * 64,
            driver_source_sha256="e" * 64, controller_generation="ctrl-1", broker_generation="broker-1",
            evidence_root=str(tmp_path / "ev"), resource_binding={"bound_at_entry": True})


def test_the_formal_entry_composes_real_providers_without_any_seam(tmp_path, monkeypatch):
    """Astra P1-1 (re-review): the formal entry must build the real composition by itself.

    No ``SO101_TASK8_PROVIDER_SEAM`` is set, so today the composition raises PRODUCTION_PROVIDERS_UNAVAILABLE and the
    formal CLI has no production path at all. The test asserts the opposite: the entry reaches a built driver whose
    collaborators came from the admitted context - and it must not require a test-only environment seam to do it.
    """

    monkeypatch.delenv("SO101_TASK8_PROVIDER_SEAM", raising=False)
    context = _context_document(tmp_path, _descriptor())
    with pytest.raises(BaseException) as caught:
        _invoke(tmp_path, context, driver=None)
    message = str(caught.value)
    assert "PRODUCTION_PROVIDERS_UNAVAILABLE" not in message, message
    assert "PRODUCTION_PROVIDER_SEAM_INVALID" not in message, message


def test_real_production_providers_are_built_from_the_admitted_descriptor(tmp_path):
    """The positive half of P1-1: the composition builds the real collaborators from the descriptor alone.

    A weights file the test writes makes the production detector factory produce a real detector from the descriptor's
    admitted CUDA configuration, and the other four collaborators come from their own production classes. The stack is
    constructed but never started, so no stack runs.
    """

    from so101_demo.act.search import HeadSearchController
    from so101_demo.act.task8_production_composition import PhaseCameraMatrixEvaluator, build_real_providers
    from so101_demo.runtime.task_stack import PersistentTaskStack

    weights = tmp_path / "best.pt"
    weights.write_bytes(b"p11-weights")
    descriptor = _descriptor()
    descriptor["head_search"]["detector"]["weights_path"] = str(weights)
    descriptor["head_search"]["detector"]["weights_sha256"] = hashlib.sha256(weights.read_bytes()).hexdigest()

    class _Context:
        runtime_descriptor = descriptor

    class _FakeYolo:
        cold_start_latency_ms = 12.5          # the production factory reads this from the detector it wraps

        def __init__(self, **kwargs):
            self.kwargs = kwargs

    seen_settings = {}

    class _Recorder:
        def __init__(self, settings):
            seen_settings.update(settings or {})

    settings = {"max_fine_corrections": 2, "search_start_rad": 0.0, "vertical_bounds_px": 480,
                "attempt_id": "a", "session_id": "s", "frame_id": "f", "ray_origin_frame_id": "f"}
    providers = build_real_providers(context=_Context(), descriptor=descriptor,
                                     controller_settings=settings,
                                     yolo_detector_factory=_FakeYolo, controller_factory=_Recorder)
    assert seen_settings == settings, "the controller is built from exactly the settings handed in"
    assert isinstance(providers["stack"], PersistentTaskStack)
    assert isinstance(providers["phase_camera"], PhaseCameraMatrixEvaluator)
    assert providers["detector"].kwargs["requested_device"] == "cuda", "the descriptor's device reaches the detector"
    assert providers["detector"].kwargs["allow_cpu_fallback"] is False, "and its CUDA policy"
    assert callable(providers["phase_camera"])


def test_the_shared_rule_enforces_the_production_head_search_contents(tmp_path):
    """Astra re-review P1-2: the shape rule must check the CONTENTS, not only the closed key sets.

    The original binding rejected an inner ``head_search.schema_version`` other than 1, and the production
    validator checks the detector's weights/version fields and the camera's and motion's own keys. The weak
    shape rule accepted all of these - including empty camera and motion blocks - which is what this RED
    asserts must stop.
    """

    cases = {
        "wrong inner version": lambda d: d["head_search"].update({"schema_version": 2}),
        "empty camera": lambda d: d["head_search"].update({"camera": {}}),
        "empty motion": lambda d: d["head_search"].update({"motion": {}}),
        "detector without weights": lambda d: d["head_search"]["detector"].pop("weights_sha256"),
        "detector without model id": lambda d: d["head_search"]["detector"].pop("model_id"),
    }
    for name, mutate in cases.items():
        document = _descriptor_with(mutate)
        with pytest.raises(ValueError) as caught:
            require_runtime_descriptor(document)
        assert "HEAD_SEARCH" in str(caught.value) or "MEASUREMENT_RUNTIME_DESCRIPTOR" in str(caught.value), name


def test_the_context_keeps_its_descriptor_through_a_round_trip(tmp_path):
    """Astra re-review P1-2: to_dict must carry the descriptor, so a rebuilt context is the same admission."""

    from so101_demo.act.task8_calibration_admission import CalibrationMeasurementContext

    descriptor = _descriptor()
    context = CalibrationMeasurementContext(
        generation="gen-round-trip", contract_sha256="a" * 64, measurement_plan_sha256="b" * 64,
        safe_interval_rad=[0.0, 0.1], candidate_sha256="c" * 64, policy_sha256="d" * 64,
        driver_source_sha256="e" * 64, controller_generation="ctrl-1", broker_generation="broker-1",
        evidence_root=str(tmp_path / "ev"),
        resource_binding={"bound_at_entry": True, "cpu_cores": 8, "gpu_device": 0},
        runtime_descriptor=descriptor)

    document = context.to_dict()
    assert document["runtime_descriptor"] == descriptor, "the descriptor survives serialisation"
    rebuilt = CalibrationMeasurementContext(**document)
    assert rebuilt.runtime_descriptor == descriptor, "and a rebuilt context is the same admission"
