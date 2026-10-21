"""act_boundary_round: the next round as a debug-campaign scene list plus the sidecar state."""

import hashlib
import json

import pytest

from so101_demo.act import boundary_search as bs
from so101_demo.act import parallel_collection_contracts
from so101_demo.cli import act_boundary_round as cli


def write_limits(path, ceiling=0.12):
    rays = {n: {"last_feasible_m": ceiling, "first_blocked_m": None, "reason": "RAY_END"}
            for n in ("E", "NE", "N", "NW", "W", "SW", "S", "SE")}
    path.write_text(json.dumps({"kind": bs.LIMITS_KIND, "centre_xy": [0.02, -0.29], "rays": rays}))


def test_the_first_round_comes_from_the_limits_and_both_outputs_are_written_once(tmp_path, capsys):
    write_limits(tmp_path / "limits.json")
    arguments = ["--limits", str(tmp_path / "limits.json"), "--scenes-output", str(tmp_path / "round-1.scenes.json"),
                 "--state-output", str(tmp_path / "round-1.state.json")]
    assert cli.main(arguments) == 0
    scenes = json.loads((tmp_path / "round-1.scenes.json").read_text())
    state = json.loads((tmp_path / "round-1.state.json").read_text())
    assert scenes["kind"] == "ACT_CONTAINER_SCENE_MANIFEST" and scenes["cup_z_m"] == 0.165
    assert [row["scene_id"] for row in scenes["scenarios"]][:2] == ["bnd-E-r1", "bnd-NE-r1"]
    assert all(set(row) == {"scene_id", "seed", "split", "cup_position_world_m"} for row in scenes["scenarios"])
    assert state["status"] == "ROUND_PENDING" and state["probes"]["E"]["xy"] == scenes["scenarios"][0]["cup_position_world_m"][:2]
    assert json.loads(capsys.readouterr().out)["round"] == 1
    # the functional debug contract takes exactly 8 scenes and identifier scene ids
    reference = {"path": str(tmp_path / "round-1.scenes.json"),
                 "sha256": hashlib.sha256((tmp_path / "round-1.scenes.json").read_bytes()).hexdigest()}
    assert len(parallel_collection_contracts.scene_ids(reference, count=8)) == 8
    with pytest.raises(ValueError, match="OUTPUT_EXISTS"):
        cli.main(arguments)


def test_a_later_round_reads_the_updated_state_and_a_finished_search_writes_nothing(tmp_path, capsys):
    write_limits(tmp_path / "limits.json", 0.03)
    state = bs.initial_state(json.loads((tmp_path / "limits.json").read_text()))
    for _ in range(2):  # ceiling pass, repeat pass: every ray is final
        pending, _scenes = bs.round_state(state)
        state = bs.apply_verdicts(pending, {p["scene_id"]: {"teacher_pass": True} for p in pending["probes"].values()})
    (tmp_path / "updated.json").write_text(json.dumps(state))
    outputs = ["--scenes-output", str(tmp_path / "s.json"), "--state-output", str(tmp_path / "t.json")]
    assert cli.main(["--state", str(tmp_path / "updated.json"), *outputs]) == 0
    assert not (tmp_path / "s.json").exists() and not (tmp_path / "t.json").exists()
    assert json.loads(capsys.readouterr().out)["status"] == "FINISHED"


def test_a_pending_state_cannot_start_another_round(tmp_path):
    write_limits(tmp_path / "limits.json")
    pending, _ = bs.round_state(bs.initial_state(json.loads((tmp_path / "limits.json").read_text())))
    (tmp_path / "pending.json").write_text(json.dumps(pending))
    with pytest.raises(ValueError, match="BOUNDARY_STATE_NOT_UPDATED"):
        cli.main(["--state", str(tmp_path / "pending.json"), "--scenes-output", str(tmp_path / "s.json"),
                  "--state-output", str(tmp_path / "t.json")])


def test_a_refined_limits_file_with_the_earlier_verified_state_starts_verification_and_bisection_rounds(tmp_path, capsys):
    rays = {n: {"last_feasible_m": 0.058, "limit_kind": "REACH"} for n in ("E", "NE", "N", "NW", "W", "SW", "S", "SE")}
    rays["W"] = {"last_feasible_m": 0.087, "limit_kind": "PLACE_TARGET"}
    (tmp_path / "refined.json").write_text(json.dumps({"kind": bs.LIMITS_KIND, "centre_xy": [0.02, -0.29], "rays": rays}))
    earlier = bs.initial_state(json.loads((tmp_path / "refined.json").read_text()))
    for name in earlier["brackets"]:  # an earlier finished search with every boundary at 0.05
        earlier["brackets"][name].update(phase="FINAL", boundary_m=0.05, boundary_verified=True)
    (tmp_path / "earlier.json").write_text(json.dumps(earlier))
    arguments = ["--limits", str(tmp_path / "refined.json"), "--verified-from", str(tmp_path / "earlier.json"),
                 "--scenes-output", str(tmp_path / "s.json"), "--state-output", str(tmp_path / "t.json")]
    assert cli.main(arguments) == 0
    state = json.loads((tmp_path / "t.json").read_text())
    assert state["probes"]["E"]["kind"] == "verify" and state["probes"]["E"]["radius_m"] == 0.058
    assert state["probes"]["W"]["kind"] == "ceiling" and state["probes"]["W"]["radius_m"] == 0.087
    unfinished = {**earlier, "brackets": {**earlier["brackets"], "E": {**earlier["brackets"]["E"], "phase": "SEARCH"}}}
    (tmp_path / "unfinished.json").write_text(json.dumps(unfinished))
    with pytest.raises(ValueError, match="BOUNDARY_VERIFIED_STATE_NOT_FINISHED"):
        cli.main(["--limits", str(tmp_path / "refined.json"), "--verified-from", str(tmp_path / "unfinished.json"),
                  "--scenes-output", str(tmp_path / "s2.json"), "--state-output", str(tmp_path / "t2.json")])
