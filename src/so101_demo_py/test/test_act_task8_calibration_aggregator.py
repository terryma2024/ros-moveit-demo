"""Task 8P2: the aggregator derives verdicts from raw evidence, never from labels.

Batch layout (the producer's contract, pinned here):
  batch.json                  identity + status (RUNNING|CLOSED|INVALID)
  fov/<anchor>.json           {"samples":[{"t_s":float,"target_in_view":bool}]}
  search/<anchor>.json        {"lock_frames":[{"t_s":float,"target_id":str,"qualified":bool}]}
  sync/<anchor>.json          {"samples":[{"age_s":float,"skew_s":float}]}
  collision.json              {"calls":[{"request_index":int,"duration_ms":float,
                                          "contact_ok":bool}]}
  execution.json              {"reference_matches_permit":bool,"velocity_ok":bool,
                               "acceleration_ok":bool,"submit_lead_s":float,"stop_ok":bool}
  cleanup-receipt.json        {"group_clear":bool}
"""

import json
from pathlib import Path

import pytest

from so101_demo.act.task8_calibration_aggregator import aggregate_task8_calibration
from so101_demo.act.task8_measurement_contract import (
    bind_measurement_contract, close_measurement_batch,
)

PACKAGE = Path(__file__).resolve().parents[1]
TEMPLATE = PACKAGE / "config/act/task8-calibration-measurement-contract-v1.json"
ANCHORS = ("default", "left", "forward")


def _write(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    return path


@pytest.fixture
def contract(tmp_path):
    identities = {"source_provenance_sha256": "a" * 64, "runtime_config_sha256": "b" * 64,
                  "anchors_sha256": "c" * 64, "contact_policy_fingerprint": "d" * 64,
                  "act_profile_sha256": "e" * 64}
    return json.loads(bind_measurement_contract(TEMPLATE, identities,
                                                tmp_path / "contract.json").read_text())


def batch_factory(tmp_path, contract, name="batch", *, declared_status="CLOSED", status_field=None,
                  source_provenance_sha256="a" * 64, lock_frames=None, fov_ok=True,
                  sync=True, collision_ok=True, execution_ok=True):
    root = tmp_path / name
    lock_frames = lock_frames or {"default": 4, "left": 4, "forward": 4}
    (root / "declared.json").parent.mkdir(parents=True, exist_ok=True)
    _write(root / "declared.json", {"declared_status": declared_status})
    for anchor in ANCHORS:
        samples = [{"t_s": index * 0.002,
                    "target_in_view": fov_ok or index < 3} for index in range(6)]
        _write(root / f"fov/{anchor}.json", {"samples": samples})
        frames = [{"t_s": index * 0.05, "target_id": "cup", "qualified": index < lock_frames[anchor]}
                  for index in range(max(lock_frames.values()) + 1)]
        _write(root / f"search/{anchor}.json", {"lock_frames": frames})
        if sync:
            _write(root / f"sync/{anchor}.json",
                   {"samples": [{"age_s": 0.05, "skew_s": 0.01} for _ in range(4)]})
    calls = [{"request_index": index, "duration_ms": 20.0 if collision_ok or index != 3 else 40.0,
              "contact_ok": True} for index in range(4)]
    _write(root / "collision.json", {"calls": calls})
    _write(root / "execution.json", {"reference_matches_permit": execution_ok,
                                     "velocity_ok": execution_ok, "acceleration_ok": execution_ok,
                                     "submit_lead_s": 0.05, "stop_ok": execution_ok})
    _write(root / "cleanup-receipt.json", {"group_clear": True})
    _write(root / "measurements.json", {
        "measurements": {name: {"value": 1.0, "unit": "rad"} for name in (
            "horizontal_fov_rad", "coarse_step_rad", "search_timeout_s",
            "max_fine_corrections", "max_fine_total_rad", "min_confidence", "tracking_iou",
            "min_bbox_aspect", "center_deadband_px", "vertical_bounds_px", "min_area_px2",
            "max_age_s", "max_skew_s", "lock_valid_neck_rad", "submit_lead_s",
            "stop_velocity_rad_s", "stop_latency_s")},
        "camera_measurements": {name: {"value": 1.0, "unit": "px"} for name in (
            "head_intrinsics_px", "head_translation_m", "head_rpy_rad",
            "yaw_zero_bearing_rad")},
        "observed_lock_frames": {anchor: lock_frames[anchor] for anchor in ANCHORS}})
    # the batch is sealed by the production entry point, which records every raw file hash
    close_measurement_batch(root, {"source_provenance_sha256": source_provenance_sha256,
                                   "contract_sha256": contract["contract_sha256"],
                                   "source_commit": "a" * 40, "config_sha256": "b" * 64,
                                   "session_id": "s", "reset_epoch": 1,
                                   "attempt_id": "attempt-1"},
                            status=(status_field or
                                    ("INVALID" if declared_status == "INVALID"
                                     else "CLOSED")))
    return root


def _report(outputs):
    return json.loads(Path(outputs["calibration_report"]).read_text())


def test_aggregator_never_trusts_raw_pass_labels(tmp_path, contract):
    batch = batch_factory(tmp_path, contract,
                          lock_frames={"default": 2, "left": 4, "forward": 4},
                          declared_status="PASS")
    report = _report(aggregate_task8_calibration((batch,), contract, tmp_path / "out"))
    assert report["status"] == "CALIBRATION_REQUIRED"
    assert report["checks"]["search"] == "FAIL"


def test_aggregator_rejects_mixed_source_provenance(tmp_path, contract):
    a = batch_factory(tmp_path, contract, "a", source_provenance_sha256="a" * 64)
    b = batch_factory(tmp_path, contract, "b", source_provenance_sha256="b" * 64)
    with pytest.raises(ValueError, match="CALIBRATION_IDENTITY_MISMATCH"):
        aggregate_task8_calibration((a, b), contract, tmp_path / "out")


def test_full_pass_with_release_unmeasured_becomes_task8_ready(tmp_path, contract):
    batch = batch_factory(tmp_path, contract)
    outputs = aggregate_task8_calibration((batch,), contract, tmp_path / "out")
    assert set(outputs) == {"head_search_qualification", "calibration_report",
                            "aggregation_receipt"}
    report = _report(outputs)
    assert report["status"] == "TASK8_READY"
    assert set(report["checks"]) >= {"fov", "collision", "search", "synchronization", "execution"}
    assert all(value == "PASS" for key, value in report["checks"].items()
               if key in {"fov", "collision", "search", "synchronization", "execution"})
    assert report["checks"].get("release") == "UNMEASURED"
    assert report["checks"].get("retreat") == "UNMEASURED"
    assert report["source_provenance_sha256"] == "a" * 64
    sample = json.loads(Path(outputs["head_search_qualification"]).read_text())
    assert sample["source_provenance_sha256"] == "a" * 64


@pytest.mark.parametrize("mutation,check", [
    ("fov", "fov"), ("sync", "synchronization"), ("collision", "collision"),
    ("execution", "execution"),
])
def test_out_of_contract_evidence_fails_the_matching_check(tmp_path, contract, mutation, check):
    kwargs = {"fov_ok": mutation != "fov", "sync": mutation != "sync",
              "collision_ok": mutation != "collision", "execution_ok": mutation != "execution"}
    batch = batch_factory(tmp_path, contract, **kwargs)
    report = _report(aggregate_task8_calibration((batch,), contract, tmp_path / "out"))
    assert report["checks"][check] in ("FAIL", "UNMEASURED")
    assert report["status"] == "CALIBRATION_REQUIRED"


def test_invalid_batch_is_refused_and_missing_input_is_unmeasured(tmp_path, contract):
    poisoned = batch_factory(tmp_path, contract, "poisoned", status_field="INVALID")
    with pytest.raises(ValueError, match="CALIBRATION_BATCH_INVALID"):
        aggregate_task8_calibration((poisoned,), contract, tmp_path / "out")
    partial = batch_factory(tmp_path, contract, "partial", sync=False)
    report = _report(aggregate_task8_calibration((partial,), contract, tmp_path / "out2"))
    assert report["checks"]["synchronization"] == "UNMEASURED"
    assert report["status"] == "CALIBRATION_REQUIRED"


def test_aggregation_is_deterministic_and_tamper_evident(tmp_path, contract):
    batch = batch_factory(tmp_path, contract)
    root = tmp_path / "out"
    first = aggregate_task8_calibration((batch,), contract, root)
    first_bytes = {key: Path(path).read_bytes() for key, path in first.items()}
    # the same sealed batch aggregated again derives byte-identical outputs: the report's
    # sample path is absolute, so determinism is asserted against the same output root
    second = aggregate_task8_calibration((batch,), contract, root)
    for key in first:
        assert Path(second[key]).read_bytes() == first_bytes[key]
    frame = batch / "fov/default.json"
    payload = json.loads(frame.read_text())
    payload["samples"][0]["target_in_view"] = False
    frame.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        aggregate_task8_calibration((batch,), contract, tmp_path / "three")
    assert not list((tmp_path / "three").glob("*TASK8_READY*"))


def _identities():
    return {"source_provenance_sha256": "a" * 64, "runtime_config_sha256": "b" * 64,
            "anchors_sha256": "c" * 64, "contact_policy_fingerprint": "d" * 64,
            "act_profile_sha256": "e" * 64}


def test_offline_report_cli_rebuilds_without_any_status_override(tmp_path, contract):
    from so101_demo.cli import act_build_task8_calibration_report as builder

    batch = batch_factory(tmp_path, contract)
    identities = tmp_path / "identities.json"
    identities.write_text(json.dumps(_identities()))
    bound = bind_measurement_contract(TEMPLATE, _identities(), tmp_path / "bound.json")
    assert builder.main(["--contract", str(bound), "--identities", str(identities),
                         "--batch-root", str(batch),
                         "--output-root", str(tmp_path / "out")]) == 0
    report = json.loads((tmp_path / "out/calibration-report.json").read_text())
    assert report["status"] == "TASK8_READY"
    with pytest.raises(SystemExit):
        builder.main(["--contract", str(bound), "--identities", str(identities),
                      "--batch-root", str(batch), "--output-root", str(tmp_path / "out2"),
                      "--status", "TASK8_READY"])          # no override flag exists


def test_measure_cli_seals_only_on_success_and_keeps_the_ledger_honest(tmp_path, contract):
    from so101_demo.cli import act_measure_task8_calibration as measure

    identities = tmp_path / "identities.json"
    identities.write_text(json.dumps(_identities()))
    bound = bind_measurement_contract(TEMPLATE, _identities(), tmp_path / "bound.json")
    ledger = tmp_path / "ledger.md"
    driver_module = tmp_path / "driver.py"
    driver_module.write_text(
        "def fill(contract, root):\n"
        "    import json, pathlib\n"
        "    root = pathlib.Path(root)\n"
        "    root.mkdir(parents=True, exist_ok=True)\n"
        "    (root / 'execution.json').write_text(json.dumps({}))\n"
        "def boom(contract, root):\n"
        "    raise RuntimeError('measurement failed')\n")
    import sys
    sys.path.insert(0, str(tmp_path))
    batch = tmp_path / "batch"
    assert measure.main(["--contract", str(bound), "--identities", str(identities),
                         "--batch-root", str(batch), "--ledger", str(ledger),
                         "--driver", "driver:fill"]) == 0
    assert (batch / "batch.json").is_file()
    # ledger lines read "- Task 8P2 measurement <STATE>: contract=... provenance=... note"
    assert [line.split()[4] for line in ledger.read_text().splitlines()] == [
        "PLANNED:", "RUNNING:", "VALID:"]
    failing = tmp_path / "failing"
    with pytest.raises(RuntimeError):
        measure.main(["--contract", str(bound), "--identities", str(identities),
                      "--batch-root", str(failing), "--ledger", str(ledger),
                      "--driver", "driver:boom"])
    assert not (failing / "batch.json").exists()
    assert ledger.read_text().splitlines()[-1].split()[4] == "INVALID:"
