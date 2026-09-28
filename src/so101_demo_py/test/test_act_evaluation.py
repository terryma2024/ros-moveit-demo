"""Task 16: a search failure stays in the denominator, and no locked runs means no locked rate."""

import pytest

from so101_demo.act.evaluation import WALL_BUDGET_S, summarize


def test_search_failure_remains_in_denominator():
    runs = [{"search_locked": False, "done": False, "interventions": 0, "elapsed_wall_s": 1.},
            {"search_locked": True, "done": True, "interventions": 0, "elapsed_wall_s": 119.}]
    report = summarize(runs)
    assert report["end_to_end"] == .5
    assert report["locked_denominator"] == 1
    assert report["locked_success"] == 1.


def test_interventions_and_the_wall_budget_are_reported_per_route():
    report = summarize([
        {"search_locked": True, "done": True, "interventions": 2, "elapsed_wall_s": 121.},
        {"search_locked": True, "done": False, "interventions": 0, "elapsed_wall_s": 10.},
        {"search_locked": False, "done": False, "interventions": 1, "elapsed_wall_s": 30.}])
    assert report["runs"] == 3
    assert report["end_to_end"] == pytest.approx(1 / 3)
    assert report["interventions_total"] == 3 and report["interventions_runs"] == 2
    assert report["budget_violations"] == 1 and report["wall_budget_s"] == WALL_BUDGET_S
    assert report["elapsed_wall_s"] == {"min": 10.0, "median": 30.0, "max": 121.0}


def test_a_route_that_never_locked_reports_no_rate_rather_than_a_perfect_one():
    report = summarize([{"search_locked": False, "done": False, "interventions": 0,
                         "elapsed_wall_s": 5.}])
    assert report["locked_denominator"] == 0 and report["locked_success"] is None
    assert report["end_to_end"] == 0.0


def test_empty_or_malformed_runs_are_refused_rather_than_summarised():
    with pytest.raises(ValueError, match="EVALUATION_EMPTY"):
        summarize([])
    for bad in ({"search_locked": True}, "run", 1,
                {"search_locked": "yes", "done": True, "interventions": 0, "elapsed_wall_s": 1.},
                {"search_locked": True, "done": True, "interventions": -1, "elapsed_wall_s": 1.},
                {"search_locked": True, "done": True, "interventions": 0, "elapsed_wall_s": float("nan")},
                {"search_locked": True, "done": True, "interventions": 0, "elapsed_wall_s": True}):
        with pytest.raises(ValueError, match="RUN_RESULT_INVALID"):
            summarize([bad])


def _workspace(tmp_path, *, runs=None, scene_ids=("act-1", "act-2")):
    import json
    from pathlib import Path as _Path

    root = tmp_path / "run"
    (root / "rollout_validation").mkdir(parents=True)
    rows = runs or [{"search_locked": True, "done": True, "interventions": 0, "elapsed_wall_s": 10.0},
                    {"search_locked": False, "done": False, "interventions": 0, "elapsed_wall_s": 5.0}]
    lines = []
    for position, row in enumerate(rows):
        if position < len(scene_ids):
            lines.append(json.dumps({**row, "scene_id": scene_ids[position],
                                     "evidence": [f"evidence/{scene_ids[position]}.json"]}))
        else:
            lines.append(json.dumps(row))
    (root / "rollout_validation" / "act-runs.jsonl").write_text(chr(10).join(lines) + chr(10))
    files = {}
    for name in ("manifest", "bundle", "calibration", "runtime-config"):
        path = tmp_path / f"{name}.json"
        path.write_text("{}")
        files[name] = path
    return root, files


def test_the_report_is_written_once_with_a_per_scene_evidence_index(tmp_path, capsys):
    import json
    from pathlib import Path as _Path

    from so101_demo.cli.act_evaluate import main

    root, files = _workspace(tmp_path)
    argv = ["--manifest", str(files["manifest"]), "--split", "rollout_validation",
            "--bundle", str(files["bundle"]), "--calibration", str(files["calibration"]),
            "--runtime-config", str(files["runtime-config"]), "--root", str(root), "--route", "act"]
    assert main(argv) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["scenes"] == 2
    report = json.loads((root / "rollout_validation" / "act-report.json").read_text())
    assert report["end_to_end"] == 0.5 and report["locked_success"] == 1.0
    assert report["evidence_index"] == {"act-1": ["evidence/act-1.json"],
                                        "act-2": ["evidence/act-2.json"]}
    assert all(len(entry["sha256"]) == 64 for entry in report["artifacts"].values())
    markdown = (root / "rollout_validation" / "act-report.md").read_text()
    assert "end-to-end: 0.500" in markdown and "`act-1`" in markdown
    with pytest.raises(ValueError, match="EVALUATION_REPORT_EXISTS"):
        main(argv)


def test_the_cli_refuses_what_it_cannot_evaluate(tmp_path):
    from so101_demo.cli.act_evaluate import main

    root, files = _workspace(tmp_path)
    base = ["--manifest", str(files["manifest"]), "--split", "rollout_validation",
            "--bundle", str(files["bundle"]), "--calibration", str(files["calibration"]),
            "--runtime-config", str(files["runtime-config"]), "--root", str(root), "--route", "act"]
    # replace the VALUE that follows each flag, not a position in the list
    for flag, replacement in (("--split", "not-a-split"), ("--route", "not-a-route")):
        argv = list(base)
        argv[argv.index(flag) + 1] = replacement
        with pytest.raises(SystemExit):
            main(argv)
    for flag, value, code in (("--bundle", root / "absent.json", "EVALUATION_BUNDLE_MISSING"),
                              ("--calibration", root / "absent.json", "EVALUATION_CALIBRATION_MISSING"),
                              ("--runtime-config", root / "absent.json",
                               "EVALUATION_RUNTIME_CONFIG_MISSING")):
        argv = list(base)
        argv[argv.index(flag) + 1] = str(value)
        with pytest.raises(ValueError, match=code):
            main(argv)
    # a runs file with no lines is not an evaluation
    (root / "rollout_validation" / "act-runs.jsonl").write_text("")
    with pytest.raises(ValueError, match="EVALUATION_EMPTY"):
        main(base)
    # a scene index must not repeat a scene or reach outside the root
    (root / "rollout_validation" / "act-runs.jsonl").write_text(
        '{"search_locked": true, "done": true, "interventions": 0, "elapsed_wall_s": 1.0, '
        '"scene_id": "a", "evidence": ["../escape.json"]}' + chr(10))
    with pytest.raises(ValueError, match="EVALUATION_EVIDENCE_PATH_INVALID"):
        main(base)
