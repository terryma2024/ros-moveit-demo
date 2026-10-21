"""act_scene_sample: the final scene list and its report, in the existing scene-list format."""

import hashlib
import json
import math

import pytest

from so101_demo.act import parallel_collection_contracts, scene_boundary as sb
from so101_demo.act.scene_list_format import KIND, plain_decimal_json, read_scene_rows
from so101_demo.cli import act_scene_sample as cli

RADII = {"E": 0.10, "NE": 0.09, "N": 0.08, "NW": 0.09, "W": 0.10, "SW": 0.09, "S": 0.09, "SE": 0.09}
POINTS = """schema_version: 1
points:
  - {id: task_start, label: a, cup_position_world_m: [0.02, -0.28, 0.165]}
  - {id: cup_test_forward_5cm, label: b, cup_position_world_m: [0.02, -0.33, 0.165]}
  - {id: cup_test_left_5cm, label: c, cup_position_world_m: [-0.03, -0.28, 0.165]}
  - {id: cup_test_right_5cm, label: d, cup_position_world_m: [0.07, -0.28, 0.165]}
"""


def planner(document_filter=lambda x, y: True):
    def call(document):
        return {
            p["id"]: ("REACHABLE", None) if document_filter(*p["cup_position_world_m"][:2]) else ("UNREACHABLE", "X")
            for p in document["points"]
        }

    return call


def inputs(tmp_path, radii=None):
    boundary_points = {n: list(sb.point_on_ray(sb.DEFAULT_CENTRE_XY, n, r)) for n, r in (radii or RADII).items()}
    (tmp_path / "state.json").write_text(json.dumps({"boundary_points": boundary_points}))
    (tmp_path / "points.yaml").write_text(POINTS)
    return ["--state", str(tmp_path / "state.json"), "--rollout-points", str(tmp_path / "points.yaml"),
            "--scenes-output", str(tmp_path / "scenes.json"), "--report-output", str(tmp_path / "report.json"),
            "--call-dir", str(tmp_path / "calls")]


def test_without_a_planner_command_the_cli_refuses_and_writes_nothing(tmp_path):
    with pytest.raises(ValueError, match="SCENE_SAMPLE_REACHABILITY_PROBE_NOT_AVAILABLE"):
        cli.main(inputs(tmp_path))
    assert not (tmp_path / "scenes.json").exists()


def test_the_scene_list_has_the_existing_format_and_the_report_the_required_fields(tmp_path):
    assert cli.main(inputs(tmp_path), reach_call=planner()) == 0
    text = (tmp_path / "scenes.json").read_text()
    document = json.loads(text)
    assert document["kind"] == KIND and document["schema_version"] == 1 and document["cup_z_m"] == 0.165
    assert document["split_quota"] == {"train": 83, "validation": 10, "offline_test": 10}
    rows = document["scenarios"]
    assert len(rows) == 103 and [r["scene_id"] for r in rows][:2] == ["frm-000", "frm-001"]
    assert [r["split"] for r in rows] == ["train"] * 83 + ["validation"] * 10 + ["offline_test"] * 10
    assert len({r["seed"] for r in rows}) == 103 and all(set(r) == {"scene_id", "seed", "split", "cup_position_world_m"} for r in rows)
    literals = []
    json.loads(text, parse_float=lambda literal: literals.append(literal) or float(literal))
    assert literals and not [literal for literal in literals if "e" in literal.lower()]  # plain decimals, no exponents (paths in strings do not count)
    assert read_scene_rows(tmp_path / "scenes.json") == rows
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["scene_count"] == 103 and report["split_counts"] == {"train": 83, "validation": 10, "offline_test": 10}
    assert report["min_spacing_m"] >= 0.004 and report["nearest_pair_m"] >= report["min_spacing_m"] - 1e-9
    assert len(report["region_polygon"]) == 8 and len(report["shrunk_region_polygon"]) == 8
    assert set(report["rollout_nearest_training_m"]) == {"task_start", "cup_test_forward_5cm", "cup_test_left_5cm", "cup_test_right_5cm"}
    assert min(report["rollout_nearest_training_m"].values()) >= 0.004


def test_the_list_round_trips_through_the_campaign_scene_reader(tmp_path):
    cli.main(inputs(tmp_path), reach_call=planner())
    path = tmp_path / "scenes.json"
    reference = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    ids = parallel_collection_contracts.scene_ids(reference, count=103)
    assert len(ids) == len(set(ids)) == 103
    rows = json.loads(path.read_text())["scenarios"]
    points = [r["cup_position_world_m"][:2] for r in rows]
    assert min(math.dist(a, b) for i, a in enumerate(points) for b in points[:i]) >= 0.004
    assert all(sb.hard_limit_violation(*p) is None for p in points)


def test_scenes_that_fail_the_five_pose_filter_are_not_used(tmp_path):
    cli.main([*inputs(tmp_path), "--count", "40", "--split-counts", "30", "5", "5"], reach_call=planner(lambda x, y: x < 0.105))
    rows = json.loads((tmp_path / "scenes.json").read_text())["scenarios"]
    assert all(r["cup_position_world_m"][0] + 0.01 < 0.105 + 1e-9 for r in rows)
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["positions_rejected_by_reachability"] > 0


def test_a_boundary_that_leaves_a_rollout_point_outside_stops_the_cli_before_writing(tmp_path):
    arguments = inputs(tmp_path, {name: 0.03 for name in sb.RAY_NAMES})
    with pytest.raises(Exception, match="ROLLOUT_POINT_OUTSIDE_REGION"):
        cli.main(arguments, reach_call=planner())
    assert not (tmp_path / "scenes.json").exists() and not (tmp_path / "report.json").exists()


def test_an_unfinished_boundary_state_is_refused(tmp_path):
    arguments = inputs(tmp_path)
    (tmp_path / "state.json").write_text(json.dumps({"brackets": {}}))
    with pytest.raises(ValueError, match="SCENE_SAMPLE_BOUNDARY_NOT_FINISHED"):
        cli.main(arguments, reach_call=planner())


def test_plain_decimals_replace_exponent_numbers():
    assert plain_decimal_json({"a": 1e-05, "b": [-2.5e-07, 0.5]}) == '{"a": 0.000010, "b": [-0.000000, 0.5]}'


def test_plain_decimal_json_leaves_strings_that_look_like_exponents_alone():
    document = {"path": "/x/gate-94933e030f2e/y", "k1e5": "1e5", "list": ["2E-3", 7e-06], "n": 3}
    text = plain_decimal_json(document)
    assert json.loads(text) == {**document, "list": ["2E-3", 0.000007]}
    assert text == '{"path": "/x/gate-94933e030f2e/y", "k1e5": "1e5", "list": ["2E-3", 0.000007], "n": 3}'


def test_plain_decimal_json_indent_and_sorted_keys_match_json_dumps_without_exponents():
    document = {"b": [1, 2.5, {"z": None, "a": True}], "a": "1e5", "e": [], "f": {}}
    assert plain_decimal_json(document, sort_keys=True, indent=2) == json.dumps(document, sort_keys=True, indent=2)
    assert plain_decimal_json(document) == json.dumps(document)


def test_boundary_kinds_set_the_margin_rule_and_the_report_lists_the_rollout_points(tmp_path):
    arguments = inputs(tmp_path)
    state = json.loads((tmp_path / "state.json").read_text())
    state["boundary_kinds"] = {name: "PLACE_TARGET" if name in ("W", "NW") else "REACH" for name in RADII}
    (tmp_path / "state.json").write_text(json.dumps(state))
    assert cli.main(arguments, reach_call=planner()) == 0
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["boundary_kinds"]["W"] == "PLACE_TARGET" and report["boundary_kinds"]["E"] == "REACH"
    assert report["place_exclusion_m"] == 0.045
    assert set(report["rollout_region"]) == {"task_start", "cup_test_forward_5cm", "cup_test_left_5cm", "cup_test_right_5cm"}
    assert all(entry["inside_region"] and entry["edge_distance_m"] > 0 for entry in report["rollout_region"].values())
    document = json.loads((tmp_path / "scenes.json").read_text())
    assert document["generator"]["boundary_kinds"]["NW"] == "PLACE_TARGET"
    assert "taper" in document["generator"]["inward_margin_rule"]


# --- joint mode (boundary design amendment 3) ---------------------------------------------------------------------
def joint_inputs(tmp_path, name="out"):
    arguments = inputs(tmp_path)
    arguments = [a for a in arguments if a not in (str(tmp_path / "scenes.json"), "--scenes-output")]
    arguments[arguments.index(str(tmp_path / "report.json"))] = str(tmp_path / (name + "-report.json"))
    return arguments + ["--lists", "formal:103,qualification:40,functional:8", "--scenes-output-dir", str(tmp_path / name)]


def test_joint_mode_writes_three_disjoint_lists_in_the_existing_format(tmp_path):
    assert cli.main(joint_inputs(tmp_path), reach_call=planner()) == 0
    directory = tmp_path / "out"
    assert sorted(p.name for p in directory.iterdir()) == ["formal-103.scenes.json", "functional-8.scenes.json", "qualification-40.scenes.json"]
    formal = read_scene_rows(directory / "formal-103.scenes.json")
    qualification = read_scene_rows(directory / "qualification-40.scenes.json")
    functional = read_scene_rows(directory / "functional-8.scenes.json")
    assert [r["split"] for r in formal] == ["train"] * 83 + ["validation"] * 10 + ["offline_test"] * 10
    assert {r["split"] for r in qualification} == {"qualification"} and {r["split"] for r in functional} == {"functional"}
    assert [r["scene_id"] for r in qualification][:2] == ["qual-00", "qual-01"] and [r["scene_id"] for r in functional][:2] == ["fn-00", "fn-01"]
    assert len(qualification) == 40 and len(functional) == 8 and len(formal) == 103
    everything = formal + qualification + functional
    assert len({r["scene_id"] for r in everything}) == 151 and len({r["seed"] for r in everything}) == 151
    points = [tuple(r["cup_position_world_m"][:2]) for r in everything]
    assert len(set(points)) == 151 and min(math.dist(a, b) for i, a in enumerate(points) for b in points[:i]) >= 0.004
    for path in directory.iterdir():
        document = json.loads(path.read_text())
        assert document["kind"] == KIND and document["cup_z_m"] == 0.165
        assert not [l for l in _literals(path.read_text()) if "e" in l.lower()]


def _literals(text):
    found = []
    json.loads(text, parse_float=lambda literal: found.append(literal) or float(literal))
    return found


def test_joint_report_records_hashes_seeds_and_the_clearances(tmp_path):
    cli.main(joint_inputs(tmp_path), reach_call=planner())
    report = json.loads((tmp_path / "out-report.json").read_text())
    assert report["mode"] == "joint" and report["scene_count"] == 151 and report["seed"] == 576020
    for name, count in (("formal", 103), ("qualification", 40), ("functional", 8)):
        entry = report["lists"][name]
        assert entry["count"] == count and entry["sha256"] == hashlib.sha256(open(entry["path"], "rb").read()).hexdigest()
        assert entry["nearest_pair_within_m"] >= 0.004 and min(entry["rollout_nearest_scene_m"].values()) >= 0.004
    assert report["lists"]["formal"]["first_seed"] == 200 and report["lists"]["qualification"]["first_seed"] == 400 and report["lists"]["functional"]["first_seed"] == 600
    assert min(report["nearest_pair_across_lists_m"].values()) >= 0.004 and report["nearest_pair_m"] >= 0.004


def test_joint_mode_is_deterministic(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir(), second.mkdir()
    cli.main(joint_inputs(first), reach_call=planner())
    cli.main(joint_inputs(second), reach_call=planner())
    for name in ("formal-103", "qualification-40", "functional-8"):
        # the generator record names the state file path, which differs between the two directories; the rows are the data
        assert read_scene_rows(first / "out" / f"{name}.scenes.json") == read_scene_rows(second / "out" / f"{name}.scenes.json")


def test_joint_mode_refuses_bad_lists_and_existing_outputs(tmp_path):
    arguments = joint_inputs(tmp_path)
    arguments[arguments.index("--lists") + 1] = "qualification:40,functional:8"
    with pytest.raises(ValueError, match="SCENE_SAMPLE_LISTS_INVALID"):
        cli.main(arguments, reach_call=planner())
    arguments[arguments.index("--lists") + 1] = "formal:103,other:4"
    with pytest.raises(ValueError, match="SCENE_SAMPLE_LISTS_INVALID"):
        cli.main(arguments, reach_call=planner())
    cli.main(joint_inputs(tmp_path), reach_call=planner())
    with pytest.raises(ValueError, match="OUTPUT_EXISTS"):
        cli.main(joint_inputs(tmp_path), reach_call=planner())


# --- pre-fetch and several planners (item 28): the same scenes, found with fewer sequential steps -------------------------
def corner(x, y):
    """Rejects a corner of the region, so the first pass of the sampler is wrong about some points and the next ones about more."""

    return not (x > 0.04 and y < -0.33)


SMALL_LISTS = ["--lists", "formal:24,functional:2"]


def recording(log, predicate=corner):
    inner = planner(predicate)

    def call(document):
        log.append([tuple(p["cup_position_world_m"][:2]) for p in document["points"]])
        return inner(document)

    return call


def counting_passes(monkeypatch):
    passes = []
    original = cli.scene_sampling.sample_joint

    def counted(*args, **keywords):
        passes.append(1)
        return original(*args, **keywords)

    monkeypatch.setattr(cli.scene_sampling, "sample_joint", counted)
    return passes


def run_joint(tmp_path, name, **keywords):
    directory = tmp_path / name
    directory.mkdir()
    arguments = joint_inputs(directory)
    arguments[arguments.index("--lists") + 1] = SMALL_LISTS[1]
    assert cli.main(arguments + keywords.pop("extra", []), **keywords) == 0
    return {n: read_scene_rows(directory / "out" / f"{n}.scenes.json") for n in ("formal-24", "functional-2")}, \
        json.loads((directory / "out-report.json").read_text())


def test_prefetch_and_a_pool_find_the_scenes_the_plain_run_finds(tmp_path):
    plain, plain_report = run_joint(tmp_path, "plain", reach_call=recording([]), extra=["--prefetch-factor", "0"])
    fast, fast_report = run_joint(tmp_path, "fast", reach_call=recording([]), reach_pool=[recording([]) for _ in range(3)])
    assert fast == plain and all(len(rows) for rows in plain.values())
    assert plain_report["positions_rejected_by_reachability"] > 0
    assert fast_report["reachability_pool_size"] == 3 and plain_report["reachability_pool_size"] == 1


def test_prefetch_needs_far_fewer_sampler_passes_than_the_pass_by_pass_run(tmp_path, monkeypatch):
    passes = counting_passes(monkeypatch)
    run_joint(tmp_path, "plain", reach_call=recording([]), extra=["--prefetch-factor", "0"])
    plain_passes, passes[:] = len(passes), []
    run_joint(tmp_path, "fast", reach_call=recording([]))
    # each pass of the plain run learns about a few more rejected positions; the cloud answers them in one round
    assert plain_passes >= 20 and len(passes) <= 4


def test_the_single_list_mode_takes_the_pool_and_the_prefetch_too(tmp_path):
    plain_directory, fast_directory = tmp_path / "plain", tmp_path / "fast"
    plain_directory.mkdir(), fast_directory.mkdir()
    small = ["--count", "30", "--split-counts", "10", "10", "10"]
    assert cli.main(inputs(plain_directory) + small + ["--prefetch-factor", "0"], reach_call=planner(corner)) == 0
    assert cli.main(inputs(fast_directory) + small, reach_call=planner(corner), reach_pool=[planner(corner), planner(corner)]) == 0
    assert read_scene_rows(plain_directory / "scenes.json") == read_scene_rows(fast_directory / "scenes.json")


def test_every_reach_command_becomes_one_planner_with_its_own_call_files(tmp_path, monkeypatch):
    made = []

    class Recorder:
        def __init__(self, command, directory, session_prefix="boundary"):
            made.append((command, session_prefix))

        def __call__(self, document):
            return planner(corner)(document)

    monkeypatch.setattr(cli, "CommandReachabilityCall", Recorder)
    assert cli.main(inputs(tmp_path) + ["--reach-command", "zsh a.zsh out one", "--reach-command", "zsh a.zsh out two"]) == 0
    assert made == [(["zsh", "a.zsh", "out", "one"], "sample"), (["zsh", "a.zsh", "out", "two"], "sample-s1")]


def test_a_negative_prefetch_factor_is_refused(tmp_path):
    with pytest.raises(ValueError, match="SCENE_SAMPLE_PREFETCH_FACTOR_INVALID"):
        cli.main(inputs(tmp_path) + ["--prefetch-factor", "0.5"], reach_call=planner())
