"""act_boundary_update: Teacher verdicts of a finished debug campaign folded into the brackets."""

import json

import pytest

from so101_demo.act import boundary_search as bs
from so101_demo.cli import act_boundary_update as cli


def limits(ceiling=0.1):
    rays = {n: {"last_feasible_m": ceiling} for n in ("E", "NE", "N", "NW", "W", "SW", "S", "SE")}
    return {"kind": bs.LIMITS_KIND, "centre_xy": [0.02, -0.29], "rays": rays}


def manifest(passed=True, **override):
    document = {
        "teacher_execution_status": "COMPLETED" if passed else "FAILED",
        "teacher_task_result": {"result": "PASS" if passed else "FAIL"},
        "current_state": "DONE" if passed else "ERROR",
        "failure": None if passed else "TARGET_UNREACHABLE: x",
    }
    document.update(override)
    return document


def make_campaign(root, pending, outcomes, missing=()):
    """A finished-run fixture: host/campaign-result.json plus one sealed manifest per scene."""

    scenes = []
    for name, probe in pending["probes"].items():
        sealed = root / "wave-0" / probe["scene_id"] / "sealed"
        if probe["scene_id"] not in missing:
            (sealed / "dynamic").mkdir(parents=True)
            (sealed / "dynamic" / "dynamic-execute-manifest.json").write_text(json.dumps(outcomes[name]))
        scenes.append({"scene_id": probe["scene_id"], "phase1": {"location": str(sealed)},
                       "phase2": {"act_data_status": "VALID", "act_data_qc": "PASS"}})
    (root / "host").mkdir(parents=True, exist_ok=True)
    (root / "host" / "campaign-result.json").write_text(json.dumps({"schema_version": 2, "scenes": scenes}))


def pending_state(tmp_path):
    pending, _ = bs.round_state(bs.initial_state(limits()))
    (tmp_path / "pending.json").write_text(json.dumps(pending))
    return pending


def test_teacher_verdicts_move_the_brackets_and_the_data_verdict_is_only_recorded(tmp_path, capsys):
    pending = pending_state(tmp_path)
    outcomes = {name: manifest(name != "N") for name in pending["probes"]}
    make_campaign(tmp_path / "run", pending, outcomes)
    assert cli.main(["--state", str(tmp_path / "pending.json"), "--run-root", str(tmp_path / "run"),
                     "--output", str(tmp_path / "updated.json")]) == 0
    updated = json.loads((tmp_path / "updated.json").read_text())
    assert updated["status"] == "UPDATED" and updated["round"] == 1 and updated["probes"] == {}
    assert updated["brackets"]["E"]["phase"] == "REPEAT" and updated["brackets"]["E"]["lo_m"] == 0.1
    assert updated["brackets"]["N"]["hi_m"] == 0.1 and updated["brackets"]["N"]["lo_m"] == 0.0
    entry = updated["history"]["N"][0]
    assert entry["teacher_pass"] is False and entry["failure"] == "TARGET_UNREACHABLE: x" and entry["act_data_status"] == "VALID"
    assert json.loads(capsys.readouterr().out)["teacher_pass"]["N"] is False


@pytest.mark.parametrize("override", [
    {"failure": "PLAN_FAILED"}, {"current_state": "ERROR"}, {"teacher_execution_status": "FAILED"},
    {"teacher_task_result": {"result": "FAIL"}},
])
def test_each_pass_condition_is_needed(tmp_path, override):
    pending = pending_state(tmp_path)
    outcomes = {name: manifest(**override) if name == "E" else manifest() for name in pending["probes"]}
    make_campaign(tmp_path / "run", pending, outcomes)
    cli.main(["--state", str(tmp_path / "pending.json"), "--run-root", str(tmp_path / "run"), "--output", str(tmp_path / "u.json")])
    updated = json.loads((tmp_path / "u.json").read_text())
    assert updated["history"]["E"][0]["teacher_pass"] is False and updated["history"]["NE"][0]["teacher_pass"] is True


def test_a_scene_without_a_manifest_stops_the_update_and_writes_nothing(tmp_path):
    pending = pending_state(tmp_path)
    make_campaign(tmp_path / "run", pending, {name: manifest() for name in pending["probes"]}, missing={"bnd-SW-r1"})
    with pytest.raises(ValueError, match="BOUNDARY_VERDICT_MISSING: bnd-SW-r1"):
        cli.main(["--state", str(tmp_path / "pending.json"), "--run-root", str(tmp_path / "run"), "--output", str(tmp_path / "u.json")])
    assert not (tmp_path / "u.json").exists()


def test_an_unreadable_campaign_result_is_a_named_error_and_the_output_is_written_once(tmp_path):
    pending_state(tmp_path)
    (tmp_path / "run").mkdir()
    with pytest.raises(ValueError, match="BOUNDARY_CAMPAIGN_RESULT_UNAVAILABLE"):
        cli.main(["--state", str(tmp_path / "pending.json"), "--run-root", str(tmp_path / "run"), "--output", str(tmp_path / "u.json")])
    (tmp_path / "u.json").write_text("{}")
    with pytest.raises(ValueError, match="OUTPUT_EXISTS"):
        cli.main(["--state", str(tmp_path / "pending.json"), "--run-root", str(tmp_path / "run"), "--output", str(tmp_path / "u.json")])
