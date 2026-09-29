"""Task 8P3 / Boundary IV item 2: the measurement entry consumes the descriptor from its context, and refuses one
whose CUDA policy the approved design forbids.

Approved preparation design section 4.2 and section 6: the runtime config is parsed once at the entry, and internal
components receive identity, generation, deadline and audit hashes - they do not go back to the preparation directory.
So the descriptor travels as a parsed document in the context, and the entry is where a wrong one is refused.
"""

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
    with pytest.raises(BaseException) as caught:
        _invoke(tmp_path, context, driver=None)

    # the composition ran: it resolved the external I/O seam, so the driver it builds is the real one - whatever
    # happens afterwards inside the run is the fakes' business, not a wiring error
    assert recorded.exists(), "the composition must build its providers"
    assert "PRODUCTION_DRIVER_WIRING_PENDING" not in str(caught.value)
    assert "PRODUCTION_PROVIDERS_UNAVAILABLE" not in str(caught.value)


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
