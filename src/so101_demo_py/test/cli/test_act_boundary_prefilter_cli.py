"""act_boundary_prefilter: r_kin per ray from the five-pose filter, written once, only with a planner command."""

import json

import pytest

from so101_demo.cli import act_boundary_prefilter as cli


def planner(limit_x):
    def call(document):
        return {
            p["id"]: ("REACHABLE", None) if p["cup_position_world_m"][0] <= limit_x else ("UNREACHABLE", "MOVEIT_PLAN_FAILED")
            for p in document["points"]
        }

    return call


def test_without_a_planner_command_the_cli_refuses_and_writes_nothing(tmp_path):
    with pytest.raises(ValueError, match="BOUNDARY_REACHABILITY_PROBE_NOT_AVAILABLE"):
        cli.main(["--output", str(tmp_path / "limits.json"), "--call-dir", str(tmp_path / "calls")])
    assert not (tmp_path / "limits.json").exists()


def test_each_ray_stops_at_the_first_failing_five_pose_check_or_hard_limit(tmp_path, capsys):
    output = tmp_path / "limits.json"
    # five poses: the +0.01 x offset must still be reachable, so the E ray stops once x + 0.01 > 0.105
    assert cli.main(["--output", str(output), "--call-dir", str(tmp_path / "calls")], reach_call=planner(0.105)) == 0
    document = json.loads(output.read_text())
    rays = document["rays"]
    assert rays["E"]["last_feasible_m"] == 0.07 and rays["E"]["first_blocked_m"] == 0.08
    assert rays["E"]["reason"] == "UNREACHABLE"
    assert rays["E"]["evaluated"][-1] == {"radius_m": 0.08, "xy": [0.1, -0.29], "status": "UNREACHABLE"}
    assert rays["W"]["reason"] == "PLACE_TARGET" and rays["W"]["last_feasible_m"] == 0.05
    assert (rays["S"]["reason"], rays["S"]["last_feasible_m"]) == ("TABLE_EDGE", 0.16)  # y reaches -0.45 at 0.16 m
    assert (rays["N"]["reason"], rays["N"]["last_feasible_m"]) == ("PEDESTAL", 0.15)
    assert rays["NE"]["last_feasible_m"] == 0.1  # x = 0.02 + 0.0707 * r, +0.01 offset still <= 0.105 at r = 0.10
    assert document["kind"] == "ACT_BOUNDARY_KINEMATIC_LIMITS" and document["centre_xy"] == [0.02, -0.29]
    assert document["reachability"]["roles"] == ["true", "x+", "x-", "y+", "y-"]
    assert json.loads(capsys.readouterr().out)["last_feasible_m"]["E"] == 0.07
    with pytest.raises(ValueError, match="OUTPUT_EXISTS"):
        cli.main(["--output", str(output), "--call-dir", str(tmp_path / "calls")], reach_call=planner(0.105))


def test_the_rays_are_evaluated_in_lockstep_batches(tmp_path):
    calls = []

    def counting(document):
        calls.append(len(document["points"]))
        return planner(0.105)(document)

    cli.main(["--output", str(tmp_path / "limits.json"), "--call-dir", str(tmp_path / "calls")], reach_call=counting)
    # one true batch per lockstep pass, never one call per point: far fewer calls than evaluated poses
    assert max(calls) >= 8 and len(calls) < sum(calls) / 4
