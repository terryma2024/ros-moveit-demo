"""act_evaluate for the native rollout: the calibration substitution, the two new splits and the per-group endpoint errors."""

import json

import pytest

import test_act_contact_calibration as base
from so101_demo.act.contact_calibration import analyze_evidence, make_activation_receipt
from so101_demo.act.rollout_activation import RULING
from so101_demo.cli.act_evaluate import SPLITS, main


def _receipt_files(tmp_path, *, tamper=False):
    offline, live = base._cohorts()
    proposal = analyze_evidence(offline, live, base._metadata())
    receipt = make_activation_receipt(proposal, proposal["policy_fingerprint"], approved_by="user",
                                      approval_reference="test activation", evidence_root=tmp_path,
                                      approved_at="2026-10-07T00:00:00+00:00")
    if tamper:
        receipt["policy_fingerprint"] = "2" * 64
    (tmp_path / "proposal.json").write_text(json.dumps(proposal))
    (tmp_path / "activation-receipt.json").write_text(json.dumps(receipt))
    return tmp_path / "proposal.json", tmp_path / "activation-receipt.json", proposal["policy_fingerprint"]


def _episode(root, split, scene_id, *, point_id, verdict, result, xy, z=0.001, tilt=0.01, done=None):
    directory = root / split / "episodes" / f"{scene_id}-a1"
    directory.mkdir(parents=True)
    (directory / "episode.json").write_text(json.dumps({"scene": {"scene_id": scene_id, "point_id": point_id},
                                                        "verdict": verdict, "group": split}))
    measured = {"initial_position_m": 0.001, "initial_axis_angle_rad": 0.0, "final_xy_error_m": xy,
                "final_z_error_m": z, "final_axis_tilt_rad": tilt}
    (directory / "endpoint.json").write_text(json.dumps({"endpoint": {"result": result, "reasons": [], "measured": measured}}))
    names = ["episode.json", "endpoint.json", "steps.jsonl", "world.jsonl", "stop-proof.json"]
    return {"search_locked": True, "done": verdict == "DONE" if done is None else done, "interventions": 0,
            "elapsed_wall_s": 100.0, "scene_id": scene_id, "evidence": [f"episodes/{scene_id}-a1/{name}" for name in names]}


def _workspace(tmp_path, split="rollout_standard"):
    root = tmp_path / "run"
    (root / split).mkdir(parents=True)
    rows = [_episode(root, split, "rollout-standard-task_start", point_id="task_start", verdict="DONE", result="PASS", xy=0.004),
            _episode(root, split, "rollout-standard-forward", point_id="cup_test_forward_5cm", verdict="FAILED",
                     result="FAIL", xy=0.05, tilt=0.4),
            _episode(root, split, "rollout-standard-left", point_id="cup_test_left_5cm", verdict="NO_MOTION",
                     result="FAIL", xy=0.0504),
            _episode(root, split, "rollout-standard-right", point_id="cup_test_right_5cm", verdict="DONE", result="PASS",
                     xy=0.012)]
    (root / split / "act-runs.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    files = {}
    for name in ("manifest", "bundle", "runtime-config", "calibration"):
        path = tmp_path / f"{name}.json"
        path.write_text("{}")
        files[name] = path
    return root, files


def _argv(root, files, split="rollout_standard", *calibration):
    return ["--manifest", str(files["manifest"]), "--split", split, "--bundle", str(files["bundle"]),
            *calibration, "--runtime-config", str(files["runtime-config"]), "--root", str(root), "--route", "act"]


def test_the_new_splits_are_accepted():
    assert {"rollout_standard", "rollout_extrapolation", "rollout_validation", "rollout_test"} <= set(SPLITS)


def test_the_receipt_replaces_the_calibration_report_and_the_substitution_is_recorded(tmp_path, capsys):
    root, files = _workspace(tmp_path)
    proposal, receipt, fingerprint = _receipt_files(tmp_path)
    argv = _argv(root, files, "rollout_standard", "--contact-activation-receipt", str(receipt),
                 "--contact-proposal", str(proposal))
    assert main(argv) == 0
    report = json.loads((root / "rollout_standard" / "act-report.json").read_text())
    calibration = report["artifacts"]["calibration"]
    assert calibration["substituted_by"] == "contact_activation_receipt"
    assert calibration["path"] == str(receipt) and len(calibration["sha256"]) == 64
    assert calibration["policy_fingerprint"] == fingerprint and calibration["ruling"] == RULING
    assert set(report["artifacts"]) == {"manifest", "bundle", "calibration", "runtime_config"}
    markdown = (root / "rollout_standard" / "act-report.md").read_text()
    assert "calibration gate" in markdown and "contact_activation_receipt" in markdown and fingerprint[:12] in markdown
    assert json.loads(capsys.readouterr().out)["scenes"] == 4


def test_a_calibration_report_still_binds_as_a_file(tmp_path):
    root, files = _workspace(tmp_path)
    assert main(_argv(root, files, "rollout_standard", "--calibration", str(files["calibration"]))) == 0
    report = json.loads((root / "rollout_standard" / "act-report.json").read_text())
    assert set(report["artifacts"]["calibration"]) == {"path", "sha256"}


def test_exactly_one_calibration_source_is_required(tmp_path):
    root, files = _workspace(tmp_path)
    proposal, receipt, _ = _receipt_files(tmp_path)
    with pytest.raises(ValueError, match="EVALUATION_CALIBRATION_SOURCE_INVALID"):
        main(_argv(root, files))
    with pytest.raises(ValueError, match="EVALUATION_CALIBRATION_SOURCE_INVALID"):
        main(_argv(root, files, "rollout_standard", "--calibration", str(files["calibration"]),
                   "--contact-activation-receipt", str(receipt), "--contact-proposal", str(proposal)))
    with pytest.raises(ValueError, match="EVALUATION_CALIBRATION_SOURCE_INVALID"):
        main(_argv(root, files, "rollout_standard", "--contact-activation-receipt", str(receipt)))   # no proposal
    with pytest.raises(ValueError, match="EVALUATION_CALIBRATION_SOURCE_INVALID"):
        main(_argv(root, files, "rollout_standard", "--contact-proposal", str(proposal)))
    assert not (root / "rollout_standard" / "act-report.json").exists()


def test_a_receipt_that_does_not_verify_writes_no_report(tmp_path):
    root, files = _workspace(tmp_path)
    proposal, receipt, _ = _receipt_files(tmp_path, tamper=True)
    with pytest.raises(ValueError, match="ROLLOUT_ACTIVATION_NOT_VERIFIED"):
        main(_argv(root, files, "rollout_standard", "--contact-activation-receipt", str(receipt),
                   "--contact-proposal", str(proposal)))
    assert not (root / "rollout_standard" / "act-report.json").exists()


def test_the_report_gives_the_endpoint_errors_of_the_group_and_of_each_point(tmp_path):
    root, files = _workspace(tmp_path)
    main(_argv(root, files, "rollout_standard", "--calibration", str(files["calibration"])))
    report = json.loads((root / "rollout_standard" / "act-report.json").read_text())
    endpoint = report["endpoint"]
    assert endpoint["scenes"] == 4 and endpoint["results"] == {"FAIL": 2, "PASS": 2}
    assert endpoint["verdicts"] == {"DONE": 2, "FAILED": 1, "NO_MOTION": 1}
    xy = endpoint["final_xy_error_m"]
    assert xy["n"] == 4 and xy["min"] == pytest.approx(0.004) and xy["max"] == pytest.approx(0.0504)
    assert xy["median"] == pytest.approx((0.012 + 0.05) / 2) and xy["mean"] == pytest.approx((0.004 + 0.05 + 0.0504 + 0.012) / 4)
    assert endpoint["final_axis_tilt_rad"]["max"] == pytest.approx(0.4)
    per_scene = {row["scene_id"]: row for row in endpoint["per_scene"]}
    assert per_scene["rollout-standard-right"]["point_id"] == "cup_test_right_5cm"
    assert per_scene["rollout-standard-left"] == {
        "scene_id": "rollout-standard-left", "point_id": "cup_test_left_5cm", "verdict": "NO_MOTION", "result": "FAIL",
        "final_xy_error_m": 0.0504, "final_z_error_m": 0.001, "final_axis_tilt_rad": 0.01}
    assert [row["scene_id"] for row in endpoint["per_scene"]] == sorted(per_scene)
    markdown = (root / "rollout_standard" / "act-report.md").read_text()
    assert "## Endpoint errors" in markdown and "cup_test_right_5cm" in markdown and "NO_MOTION" in markdown


def test_a_group_without_endpoint_evidence_has_no_endpoint_section(tmp_path):
    root = tmp_path / "run"
    (root / "rollout_validation").mkdir(parents=True)
    (root / "rollout_validation" / "act-runs.jsonl").write_text(json.dumps({
        "search_locked": True, "done": True, "interventions": 0, "elapsed_wall_s": 1.0, "scene_id": "a",
        "evidence": ["evidence/a.json"]}) + "\n")
    files = {}
    for name in ("manifest", "bundle", "runtime-config", "calibration"):
        files[name] = tmp_path / f"{name}.json"
        files[name].write_text("{}")
    main(_argv(root, files, "rollout_validation", "--calibration", str(files["calibration"])))
    assert json.loads((root / "rollout_validation" / "act-report.json").read_text())["endpoint"] is None


def test_listed_endpoint_evidence_that_is_missing_or_unreadable_is_refused(tmp_path):
    root, files = _workspace(tmp_path)
    broken = root / "rollout_standard" / "episodes" / "rollout-standard-left-a1" / "endpoint.json"
    broken.write_text("{not json")
    argv = _argv(root, files, "rollout_standard", "--calibration", str(files["calibration"]))
    with pytest.raises(ValueError, match="EVALUATION_ENDPOINT_EVIDENCE_INVALID"):
        main(argv)
    broken.unlink()
    with pytest.raises(ValueError, match="EVALUATION_ENDPOINT_EVIDENCE_MISSING"):
        main(argv)
    assert not (root / "rollout_standard" / "act-report.json").exists()
