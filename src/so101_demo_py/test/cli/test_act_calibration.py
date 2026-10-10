"""Collection cannot use unmeasured, corrupted or wrongly dimensioned calibration."""

import hashlib
import json
import subprocess
import pytest

from so101_demo.act.calibration import REQUIRED_MEASUREMENTS, require_gate, require_qualified, validate_partial


def test_installed_preflight_reads_explicit_source_root(tmp_path, monkeypatch):
    from ament_index_python import packages
    from so101_demo.cli import act_preflight

    share = tmp_path / "share"
    for relative in ("assets/mujoco/act", "config/mujoco/act"):
        directory = share / relative
        directory.mkdir(parents=True)
        (directory / "asset.txt").write_text(relative)
    monkeypatch.setattr(packages, "get_package_share_directory", lambda name: str(share))
    monkeypatch.setattr(act_preflight, "__file__", str(tmp_path / "installed/act_preflight.py"))

    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=test",
                    "-c", "user.email=test@example.invalid", "commit", "--allow-empty",
                    "-qm", "fixture"], check=True)
    expected = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"],
                                       text=True).strip()
    output = tmp_path / "report.json"
    assert act_preflight.main(["--output", str(output), "--source-root", str(source)]) == 2
    report = json.loads(output.read_text())
    assert report["source_commit"] == expected
    assert report["status"] == "CALIBRATION_REQUIRED"
    assert set(report["checks"].values()) == {"UNMEASURED"}


def test_installed_preflight_preserves_partial_evidence_without_qualification(tmp_path, monkeypatch):
    from ament_index_python import packages
    from so101_demo.cli import act_preflight

    share = tmp_path / "share"
    for relative in ("assets/mujoco/act", "config/mujoco/act"):
        directory = share / relative
        directory.mkdir(parents=True)
        (directory / "asset.txt").write_text(relative)
    monkeypatch.setattr(packages, "get_package_share_directory", lambda name: str(share))
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=test",
                    "-c", "user.email=test@example.invalid", "commit", "--allow-empty",
                    "-qm", "fixture"], check=True)
    baseline = tmp_path / "baseline.json"
    assert act_preflight.main(["--output", str(baseline), "--source-root", str(source)]) == 2
    partial = json.loads(baseline.read_text())
    sample = tmp_path / "camera-sample.json"
    sample.write_text("measured camera sample\n")
    partial["measurements"]["head_translation_m"] = dict(
        value=[-.06, .06, .24], unit="m", sample_path=str(sample),
        sample_sha256=hashlib.sha256(sample.read_bytes()).hexdigest())
    measured = tmp_path / "measured.json"
    measured.write_text(json.dumps(partial))
    output = tmp_path / "partial.json"
    assert act_preflight.main(["--output", str(output), "--source-root", str(source),
                               "--measured-report", str(measured)]) == 2
    assert json.loads(output.read_text()) == partial
    with pytest.raises(ValueError):
        require_qualified(partial)
    sample.write_text("tampered\n")
    with pytest.raises(ValueError, match="CALIBRATION_SAMPLE_HASH_INVALID"):
        act_preflight.main(["--output", str(tmp_path / "tampered.json"),
                            "--source-root", str(source), "--measured-report", str(measured)])


def test_partial_report_refuses_unknown_measurement_and_all_pass_without_full_report(tmp_path):
    partial = report(tmp_path)
    partial["status"] = "CALIBRATION_REQUIRED"
    partial["measurements"] = {"head_translation_m": partial["measurements"]["head_translation_m"]}
    partial["checks"] = {key: "UNMEASURED" for key in partial["checks"]}
    validate_partial(partial)
    partial["measurements"]["unknown"] = partial["measurements"]["head_translation_m"]
    with pytest.raises(ValueError):
        validate_partial(partial)
    del partial["measurements"]["unknown"]
    partial["checks"]["fov"] = "PASS"
    with pytest.raises(ValueError):
        validate_partial(partial)


def report(tmp_path):
    sample=tmp_path/"measurement.json"; sample.write_text("measured evidence\n")
    values={}
    for key,(unit,size) in REQUIRED_MEASUREMENTS.items():
        value=[1.]*size if size>1 else 1.
        if key=="max_fine_corrections": value=3
        values[key]=dict(value=value,unit=unit,sample_path=str(sample),
                         sample_sha256=hashlib.sha256(sample.read_bytes()).hexdigest())
    # a QUALIFIED report must trace to the live campaign that produced it
    campaign = dict(case_root="/run", campaign_result_sha256="c"*64,
                    preparation_receipt_sha256="d"*64,
                    journal_sha256=["e"*64]*14)
    return dict(schema_version=1,status="QUALIFIED",source_commit="a"*40,config_sha256="b"*64,
                source_provenance_sha256="a1"*32, live_campaign=campaign,
                measurements=values, checks={key:"PASS" for key in
                ("fov","collision","search","synchronization","execution","release","retreat")})


def test_unqualified_and_missing_evidence_cannot_start_collection(tmp_path):
    with pytest.raises(ValueError): require_qualified({"status":"CALIBRATION_REQUIRED","checks":{}})
    measured=report(tmp_path); require_qualified(measured)
    measured["measurements"].pop("stop_latency_s")
    with pytest.raises(ValueError): require_qualified(measured)


def test_task8_ready_requires_measured_five_checks_but_refuses_formal(tmp_path):
    ready = report(tmp_path)
    ready["status"] = "TASK8_READY"
    ready["checks"]["release"] = "UNMEASURED"
    ready["checks"]["retreat"] = "UNMEASURED"
    del ready["measurements"]["release_stable_s"]
    del ready["measurements"]["retreat_distance_m"]
    del ready["measurements"]["placement_stable_s"]
    require_gate(ready, "pick_place_validation")
    require_gate(ready, "task8_live")
    with pytest.raises(ValueError, match="CALIBRATION_REQUIRED"):
        require_gate(ready, "formal_collection")
    ready["measurements"].pop("path_clearance_m")
    with pytest.raises(ValueError, match="CALIBRATION_CHECK_EVIDENCE_MISSING"):
        require_gate(ready, "task8_live")


def test_task8_ready_refuses_unmeasured_or_premature_release_pass(tmp_path):
    ready = report(tmp_path)
    ready["status"] = "TASK8_READY"
    ready["checks"]["release"] = "UNMEASURED"
    ready["checks"]["retreat"] = "UNMEASURED"
    ready["checks"]["execution"] = "UNMEASURED"
    with pytest.raises(ValueError, match="CALIBRATION_REQUIRED"):
        require_gate(ready, "task8_live")
    ready["checks"]["execution"] = "PASS"
    ready["checks"]["release"] = "PASS"
    with pytest.raises(ValueError, match="CALIBRATION_REQUIRED"):
        require_gate(ready, "task8_live")


def test_full_qualification_is_formal_gate_only(tmp_path):
    measured = report(tmp_path)
    require_gate(measured, "formal_collection")
    with pytest.raises(ValueError):
        require_gate({"status": "CALIBRATION_REQUIRED", "checks": {}}, "task8_live")


def test_preflight_cli_emits_task8_ready_only_for_verified_preflight(tmp_path, monkeypatch):
    from ament_index_python import packages
    from so101_demo.cli import act_preflight

    share = tmp_path / "share"
    for relative in ("assets/mujoco/act", "config/mujoco/act"):
        directory = share / relative
        directory.mkdir(parents=True)
        (directory / "asset.txt").write_text(relative)
    monkeypatch.setattr(packages, "get_package_share_directory", lambda name: str(share))
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=test",
                    "-c", "user.email=test@example.invalid", "commit", "--allow-empty",
                    "-qm", "fixture"], check=True)
    baseline = tmp_path / "baseline.json"
    assert act_preflight.main(["--output", str(baseline), "--source-root", str(source)]) == 2
    ready = report(tmp_path)
    ready["source_commit"] = json.loads(baseline.read_text())["source_commit"]
    ready["config_sha256"] = json.loads(baseline.read_text())["config_sha256"]
    ready["status"] = "TASK8_READY"
    ready["checks"]["release"] = ready["checks"]["retreat"] = "UNMEASURED"
    measured = tmp_path / "measured.json"
    measured.write_text(json.dumps(ready))
    output = tmp_path / "ready.json"
    assert act_preflight.main(["--output", str(output), "--source-root", str(source),
                               "--measured-report", str(measured)]) == 0
    assert json.loads(output.read_text())["status"] == "TASK8_READY"


@pytest.mark.parametrize("mutation", ("hash","unit","nan","extra","check","bool"))
def test_measurement_corruption_fails_closed(tmp_path,mutation):
    measured=report(tmp_path); item=measured["measurements"]["stop_latency_s"]
    if mutation=="hash": item["sample_sha256"]="c"*64
    if mutation=="unit": item["unit"]="milliseconds"
    if mutation=="nan": item["value"]=float("nan")
    if mutation=="bool": item["value"]=True
    if mutation=="extra": measured["truth"]=True
    if mutation=="check": measured["checks"]["release"]="UNMEASURED"
    with pytest.raises(ValueError): require_qualified(measured)
