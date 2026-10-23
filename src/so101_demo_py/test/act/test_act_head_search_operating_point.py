"""Phase 3 of the formal head-search calibration: the perception operating-point policy.

The policy layer owns the parts of phase 3 that must not be able to fit the verdict after the fact. The
selection rule is recorded before any measurement exists, the search runs over the four operating-point
values on the head val and calibration-episode measurements only, the choice follows the chain the
campaign declared before it measured, and a point that yields even one false
candidate on an empty scene is refused rather than shipped.

Everything here is synthetic and in memory: no detector, no GPU, no MuJoCo, no ROS. The detection
records carry `x`, `y` and `conf` exactly as the campaign's recorder writes them, and the frames that
exercise the geometric floors and the tracker's IoU additionally carry a bbox as `w`/`h`.
"""

from __future__ import annotations

import json

import pytest
from so101_demo.act.head_search_operating_point import (
    CAL_NO_CUP_FALSE_CANDIDATE,
    CAL_RULE_AFTER_MEASUREMENT,
    CAL_SPLIT_LEAK,
    TIE_BREAK_CHAIN,
    CalibrationOperatingPointRefused,
    choose_operating_point,
    evaluate_operating_point_grid,
    measure_no_cup_false_candidates,
    record_selection_rule,
    report_held_out_measurements,
    select_operating_point,
    validate_head_search_calibration_operating_point,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

CANDIDATE_ID = "C2a"
SELECTION_SPLITS = ("val", "calibration")
HELD_OUT_SPLITS = ("held_out_evaluation",)
BOUNDED = 8.0


def _point(min_confidence, *, tracking_iou=0.95, min_bbox_aspect=1.0, min_area_px2=1.0):
    return {
        "min_confidence": min_confidence,
        "tracking_iou": tracking_iou,
        "min_bbox_aspect": min_bbox_aspect,
        "min_area_px2": min_area_px2,
    }


def _truth(x, y):
    return {"x": x, "y": y}


def _detection(x, y, conf, *, width=None, height=None):
    detection = {"x": x, "y": y, "conf": conf}
    if width is not None:
        detection["w"] = width
        detection["h"] = width if height is None else height
    return detection


def _frame(split, truths, detections, *, domain="head", scenario="nominal", seed=0):
    return {
        "split": split,
        "domain": domain,
        "seed": seed,
        "scenario": scenario,
        "truth": list(truths),
        "detections": {CANDIDATE_ID: list(detections)},
        "match_radius_px": BOUNDED,
    }


def _rule(points, **overrides):
    arguments = {
        "points": points,
        "selection_splits": SELECTION_SPLITS,
        "held_out_splits": HELD_OUT_SPLITS,
        "domain": "head",
    }
    arguments.update(overrides)
    return record_selection_rule(**arguments)


def _select(points, measurements, **overrides):
    return select_operating_point(
        rule=_rule(points, **overrides), measurements=measurements, candidate_id=CANDIDATE_ID
    )


def _refuses(code, call, **arguments):
    with pytest.raises(CalibrationOperatingPointRefused) as caught:
        call(**arguments)
    assert caught.value.code == code
    return caught.value


def _cells(result):
    return [cell["point"] for cell in result["grid"]]


def _cell(result, index):
    return result["grid"][index]


#: the ordinary fixture: five head frames across both selection splits. Total ground truth is six
#: objects, and the 0.30 detection on the fifth frame is far from every truth, so a lower confidence
#: floor buys a false positive rather than a true one.
MAIN_MEASUREMENTS = (
    _frame("val", [_truth(100, 100)], [_detection(100.5, 100.5, 0.90)]),
    _frame("val", [_truth(200, 200)], [_detection(200.4, 200.4, 0.55)]),
    _frame(
        "val",
        [_truth(500, 500)],
        [_detection(560.0, 560.0, 0.30), _detection(500.1, 500.1, 0.90)],
    ),
    _frame("calibration", [_truth(300, 300)], [_detection(300.2, 300.2, 0.80)]),
    _frame("calibration", [_truth(400, 400), _truth(430, 400)], [_detection(400.1, 400.1, 0.95)]),
)

#: f1 = 5/6 (the low-confidence bystander is a false positive), 10/11 (unique best) and 8/10
MAIN_POINTS = (_point(0.25), _point(0.35), _point(0.60))

#: six truths on a 160 px grid and six 400 px boxes whose overlaps are 0.14-0.67. At IoU 0.30 the
#: first box suppresses three of them and the second suppresses the last, leaving two detections that
#: match two truths; at IoU 0.95 all six survive and match three truths plus three false positives.
#: Both points come out at f1 = 0.5, and the one with the higher recall has the HIGHER confidence floor,
#: so only the declared recall tie-break can select it.
RECALL_MEASUREMENTS = (
    _frame(
        "val",
        [
            _truth(100, 100),
            _truth(260, 100),
            _truth(420, 100),
            _truth(100, 260),
            _truth(260, 260),
            _truth(420, 260),
        ],
        [
            _detection(100.2, 100.2, 0.99, width=400),
            _detection(260.2, 260.2, 0.98, width=400),
            _detection(260.3, 100.3, 0.97, width=400),
            _detection(180.0, 100.0, 0.96, width=400),
            _detection(260.0, 180.0, 0.95, width=400),
            _detection(340.0, 260.0, 0.94, width=400),
        ],
    ),
)
RECALL_POINTS = (_point(0.30, tracking_iou=0.30), _point(0.90, tracking_iou=0.95))

#: one truth, one detection on it and one 4x4 false detection far away: only an area floor above 16 px
#: removes the false positive
AREA_MEASUREMENTS = (
    _frame(
        "val",
        [_truth(100, 100)],
        [
            _detection(100.2, 100.2, 0.90, width=40),
            _detection(400.0, 400.0, 0.95, width=4),
        ],
    ),
)
AREA_POINTS = (_point(0.30, min_area_px2=1.0), _point(0.30, min_area_px2=64.0))

#: the same idea on the aspect floor: a 100x10 false detection is 0.1 tall per unit wide, so only an
#: aspect floor above that removes it
ASPECT_MEASUREMENTS = (
    _frame(
        "val",
        [_truth(100, 100)],
        [
            _detection(100.2, 100.2, 0.90, width=40),
            _detection(400.0, 400.0, 0.95, width=100, height=10),
        ],
    ),
)
ASPECT_POINTS = (_point(0.30, min_bbox_aspect=0.05), _point(0.30, min_bbox_aspect=0.5))

#: two detections in boxes overlapping by 0.67: the point whose IoU threshold is below that overlap
#: keeps the detection on the truth and a clean f1 of 1.0, the one above keeps the second detection too
#: and pays a false positive (the second centre is 80 px from every truth)
IOU_MEASUREMENTS = (
    _frame(
        "val",
        [_truth(100, 100)],
        [
            _detection(100.2, 100.2, 0.90, width=400),
            _detection(180.2, 100.2, 0.85, width=400),
        ],
    ),
)
IOU_POINTS = (_point(0.30, tracking_iou=0.95), _point(0.30, tracking_iou=0.50))

#: one clean frame, one frame whose only detection is below the higher floor and one genuinely empty
#: scene whose detection is below it too
NO_CUP_MEASUREMENTS = (
    _frame("val", [_truth(100, 100)], [_detection(100.3, 100.3, 0.90)]),
    _frame("val", [_truth(200, 200)], [_detection(200.2, 200.2, 0.28)]),
    _frame("val", [], [_detection(400.0, 400.0, 0.30)], scenario="no_cup"),
)
NO_CUP_POINTS = (_point(0.25), _point(0.35))

#: held-out frames that would flip the choice towards the LOWEST confidence point if the selection ever
#: consumed them: the 0.30 detection on a seventh object is a true positive only for 0.25
HELD_OUT_MEASUREMENTS = (
    _frame("held_out_evaluation", [_truth(700, 700)], [_detection(700.2, 700.2, 0.30)]),
)


def test_records_the_rule_before_any_measurement_and_digests_it():
    rule = _rule(MAIN_POINTS)

    body = {key: value for key, value in rule.items() if key != "rule_sha256"}
    assert rule["rule_sha256"] == canonical_sha256(body)
    assert rule["recorded_before_measurement"] is True
    assert rule["measurements_admitted"] == 0
    assert rule["points"] == list(MAIN_POINTS)
    assert tuple(rule["tie_break_chain"]) == tuple(TIE_BREAK_CHAIN)
    assert tuple(rule["selection_splits"]) == SELECTION_SPLITS
    assert tuple(rule["held_out_splits"]) == HELD_OUT_SPLITS


def test_a_rule_recorded_after_a_measurement_is_refused():
    error = _refuses(CAL_RULE_AFTER_MEASUREMENT, _rule, points=MAIN_POINTS, measurements_admitted=1)
    assert "measurement" in error.detail


def test_a_rule_replaced_after_a_measurement_is_refused():
    first = _rule(MAIN_POINTS)

    _refuses(
        CAL_RULE_AFTER_MEASUREMENT,
        _rule,
        points=MAIN_POINTS,
        measurements_admitted=2,
        existing_rule=first,
    )


def test_a_rule_replaced_before_any_measurement_records_what_it_replaces():
    first = _rule(MAIN_POINTS)
    second = _rule(MAIN_POINTS, existing_rule=first)

    assert second["replaces_rule_sha256"] == first["rule_sha256"]
    assert first["replaces_rule_sha256"] is None
    assert second["rule_sha256"] != first["rule_sha256"]


def test_a_point_that_is_not_the_four_operating_point_values_is_a_caller_error():
    with pytest.raises(ValueError):
        _rule(({"min_confidence": 0.3, "tracking_iou": 0.5, "min_area_px2": 64.0},))


def test_a_duplicated_point_is_a_caller_error():
    with pytest.raises(ValueError):
        _rule((_point(0.25), _point(0.25)))


def test_selection_and_held_out_splits_must_not_overlap():
    with pytest.raises(ValueError):
        _rule(MAIN_POINTS, held_out_splits=("val",))


def test_the_grid_drops_detections_below_the_confidence_floor():
    grid = evaluate_operating_point_grid(
        rule=_rule(MAIN_POINTS), measurements=MAIN_MEASUREMENTS, candidate_id=CANDIDATE_ID
    )

    assert [cell["point"] for cell in grid["cells"]] == list(MAIN_POINTS)
    assert [cell["true_positive"] for cell in grid["cells"]] == [5, 5, 4]
    assert [cell["false_positive"] for cell in grid["cells"]] == [1, 0, 0]
    assert [cell["false_negative"] for cell in grid["cells"]] == [1, 1, 2]
    assert grid["cells"][1]["f1"] == pytest.approx(10 / 11)
    assert grid["cells"][1]["recall"] == pytest.approx(5 / 6)
    assert grid["cells"][0]["f1"] == pytest.approx(5 / 6)
    assert grid["cells"][0]["filters_reapplied"] == ["min_confidence"]


def test_a_detection_mapping_is_a_caller_error_not_four_detections():
    frame = dict(MAIN_MEASUREMENTS[0])
    frame["detections"] = {CANDIDATE_ID: {"n": 1, "max_conf": 0.9, "found": True, "centres": []}}

    with pytest.raises(ValueError):
        evaluate_operating_point_grid(
            rule=_rule(MAIN_POINTS), measurements=(frame,), candidate_id=CANDIDATE_ID
        )


def test_a_frame_without_a_measurement_for_the_candidate_is_a_caller_error():
    frame = dict(MAIN_MEASUREMENTS[0])
    frame["detections"] = {}

    with pytest.raises(ValueError):
        evaluate_operating_point_grid(
            rule=_rule(MAIN_POINTS), measurements=(frame,), candidate_id=CANDIDATE_ID
        )


def test_the_happy_path_selects_the_point_with_the_best_f1():
    result = _select(MAIN_POINTS, MAIN_MEASUREMENTS)

    assert result["chosen_point"] == MAIN_POINTS[1]
    assert result["chosen_index"] == 1
    assert result["ties_broken_by"] == "f1"
    assert result["chosen_cell"]["f1"] == pytest.approx(10 / 11)
    assert _cells(result) == list(MAIN_POINTS)


def test_the_tie_break_prefers_the_higher_recall_at_equal_f1():
    result = _select(RECALL_POINTS, RECALL_MEASUREMENTS)

    assert [cell["f1"] for cell in result["grid"]] == [pytest.approx(0.5), pytest.approx(0.5)]
    assert [cell["recall"] for cell in result["grid"]] == [
        pytest.approx(2 / 6),
        pytest.approx(3 / 6),
    ]
    assert result["chosen_point"] == RECALL_POINTS[1]
    assert result["chosen_index"] == 1
    assert result["ties_broken_by"] == "recall"


def test_the_tie_break_prefers_the_lower_confidence_at_equal_f1_and_recall():
    points = (_point(0.70), _point(0.60))
    result = _select(points, MAIN_MEASUREMENTS)

    assert _cell(result, 0)["f1"] == _cell(result, 1)["f1"]
    assert _cell(result, 0)["recall"] == _cell(result, 1)["recall"]
    assert result["chosen_index"] == 1
    assert result["ties_broken_by"] == "min_confidence"


def test_a_tie_that_survives_the_chain_goes_to_the_first_declared_point():
    points = (_point(0.30, tracking_iou=0.95), _point(0.30, tracking_iou=0.30))
    result = _select(points, MAIN_MEASUREMENTS)

    assert _cell(result, 0)["f1"] == _cell(result, 1)["f1"]
    assert _cell(result, 0)["recall"] == _cell(result, 1)["recall"]
    assert (
        _cell(result, 0)["point"]["min_confidence"] == _cell(result, 1)["point"]["min_confidence"]
    )
    assert result["chosen_index"] == 0
    assert result["ties_broken_by"] == "declared_order"


def test_the_tracker_iou_re_suppresses_overlapping_detections():
    result = _select(IOU_POINTS, IOU_MEASUREMENTS)

    assert _cell(result, 0)["false_positive"] == 1
    assert _cell(result, 0)["f1"] == pytest.approx(2 / 3)
    assert _cell(result, 1)["false_positive"] == 0
    assert _cell(result, 1)["f1"] == pytest.approx(1.0)
    assert "tracking_iou" in _cell(result, 1)["filters_reapplied"]
    assert result["chosen_index"] == 1


def test_the_area_floor_removes_a_small_detection():
    result = _select(AREA_POINTS, AREA_MEASUREMENTS)

    assert _cell(result, 0)["false_positive"] == 1
    assert _cell(result, 0)["f1"] == pytest.approx(2 / 3)
    assert _cell(result, 1)["false_positive"] == 0
    assert _cell(result, 1)["f1"] == pytest.approx(1.0)
    assert "min_area_px2" in _cell(result, 1)["filters_reapplied"]
    assert result["chosen_index"] == 1


def test_the_aspect_floor_removes_a_flat_detection():
    result = _select(ASPECT_POINTS, ASPECT_MEASUREMENTS)

    assert _cell(result, 0)["false_positive"] == 1
    assert _cell(result, 0)["f1"] == pytest.approx(2 / 3)
    assert _cell(result, 1)["false_positive"] == 0
    assert _cell(result, 1)["f1"] == pytest.approx(1.0)
    assert "min_bbox_aspect" in _cell(result, 1)["filters_reapplied"]
    assert result["chosen_index"] == 1


def test_a_record_without_boxes_can_only_re_apply_the_confidence_floor():
    grid = evaluate_operating_point_grid(
        rule=_rule(MAIN_POINTS), measurements=MAIN_MEASUREMENTS, candidate_id=CANDIDATE_ID
    )

    for cell in grid["cells"]:
        assert cell["filters_reapplied"] == ["min_confidence"]
        assert cell["detections_without_geometry"] == cell["detections_kept"]


def test_the_phase_matches_the_gates_episode_cells():
    from so101_demo.cli.evaluate_head_search_yolo_candidates import _episode_cells

    rule = _rule((_point(0.0, tracking_iou=1.0, min_bbox_aspect=1.0, min_area_px2=1.0),))
    grid = evaluate_operating_point_grid(
        rule=rule, measurements=MAIN_MEASUREMENTS, candidate_id=CANDIDATE_ID
    )
    cell = grid["cells"][0]

    for split in SELECTION_SPLITS:
        gate = _episode_cells(list(MAIN_MEASUREMENTS), CANDIDATE_ID, "head", split)
        assert cell["splits"][split]["f1"] == pytest.approx(gate["f1"])
        assert cell["splits"][split]["recall"] == pytest.approx(gate["recall"])
        assert cell["splits"][split]["bbox_center_p95_px"] == pytest.approx(
            gate["bbox_center_p95_px"]
        )


def test_a_held_out_frame_in_the_selection_measurements_is_refused():
    error = _refuses(
        CAL_SPLIT_LEAK,
        _select,
        points=MAIN_POINTS,
        measurements=MAIN_MEASUREMENTS + HELD_OUT_MEASUREMENTS,
    )
    assert "held_out_evaluation" in error.detail


def test_a_frame_of_an_undeclared_split_is_refused():
    undeclared = _frame("test", [_truth(900, 900)], [_detection(900.1, 900.1, 0.90)])

    _refuses(
        CAL_SPLIT_LEAK, _select, points=MAIN_POINTS, measurements=MAIN_MEASUREMENTS + (undeclared,)
    )


def test_a_frame_that_declares_no_split_is_refused():
    undeclared = {key: value for key, value in MAIN_MEASUREMENTS[0].items() if key != "split"}

    _refuses(CAL_SPLIT_LEAK, _select, points=MAIN_POINTS, measurements=(undeclared,))


def test_only_the_declared_selection_splits_are_consumed():
    result = _select(MAIN_POINTS, MAIN_MEASUREMENTS)

    assert result["measurements_consumed"] == {
        "total": 5,
        "per_split": {"val": 3, "calibration": 2},
    }
    assert result["split_isolation"]["held_out_frames"] == 0


def test_only_the_declared_domain_is_consumed():
    task_frame = _frame("val", [_truth(950, 950)], [_detection(950.1, 950.1, 0.90)], domain="task")
    with_task = MAIN_MEASUREMENTS + (task_frame,)

    result = _select(MAIN_POINTS, with_task)

    assert result["measurements_consumed"]["total"] == 5
    assert result["split_isolation"]["per_split"] == {"val": 4, "calibration": 2}
    assert result["grid"] == _select(MAIN_POINTS, MAIN_MEASUREMENTS)["grid"]


def test_a_measurement_set_with_no_head_frame_is_a_caller_error():
    task_frame = _frame("val", [_truth(950, 950)], [_detection(950.1, 950.1, 0.90)], domain="task")

    with pytest.raises(ValueError):
        _select(MAIN_POINTS, (task_frame,))


def test_a_no_cup_false_candidate_blocks_the_point_with_the_best_f1():
    error = _refuses(
        CAL_NO_CUP_FALSE_CANDIDATE, _select, points=NO_CUP_POINTS, measurements=NO_CUP_MEASUREMENTS
    )
    assert "1" in error.detail

    without_the_empty_scene = _select(NO_CUP_POINTS, NO_CUP_MEASUREMENTS[:-1])
    assert without_the_empty_scene["chosen_point"] == NO_CUP_POINTS[0]
    assert without_the_empty_scene["no_cup_guard"]["clean"] is True


def test_the_no_cup_guard_counts_only_the_empty_scenes():
    rule = _rule(NO_CUP_POINTS)
    measurements = (
        _frame(
            "val",
            [_truth(100, 100)],
            [_detection(100.3, 100.3, 0.90), _detection(600.0, 600.0, 0.30)],
        ),
        _frame("val", [], [_detection(700.0, 700.0, 0.30)], scenario="nominal"),
        _frame("val", [], [_detection(800.0, 800.0, 0.30)], scenario="no_cup"),
        _frame("val", [], [], scenario="no_cup"),
    )

    guard = measure_no_cup_false_candidates(
        rule=rule, measurements=measurements, candidate_id=CANDIDATE_ID, point=NO_CUP_POINTS[0]
    )

    assert guard["frames_checked"] == 2
    assert guard["no_cup_false_candidates"] == 1
    assert guard["clean"] is False


def test_a_point_that_suppresses_the_empty_scene_is_clean_and_selected():
    result = _select((_point(0.35), _point(0.60)), NO_CUP_MEASUREMENTS)

    assert result["no_cup_guard"]["clean"] is True
    assert result["no_cup_guard"]["frames_checked"] == 1
    assert result["chosen_point"] == _point(0.35)


def test_held_out_measurements_are_reported_only_and_never_decide():
    rule = _rule(MAIN_POINTS)
    without = validate_head_search_calibration_operating_point(
        rule=rule, measurements=MAIN_MEASUREMENTS, candidate_id=CANDIDATE_ID
    )
    document = validate_head_search_calibration_operating_point(
        rule=rule,
        measurements=MAIN_MEASUREMENTS,
        candidate_id=CANDIDATE_ID,
        held_out_measurements=HELD_OUT_MEASUREMENTS,
    )

    assert document["chosen_point"] == MAIN_POINTS[1]
    assert document["chosen_point"] == without["chosen_point"]
    assert document["grid"] == without["grid"]
    assert document["held_out_consumed_for_selection"] is False
    assert document["held_out_report"]["consumed_for_selection"] is False
    assert document["held_out_report"]["measured"] is True
    assert document["held_out_report"]["frame_count"] == 1
    assert document["held_out_report"]["splits"]["held_out_evaluation"]["f1"] == pytest.approx(0.0)


def test_without_held_out_measurements_the_report_says_so():
    document = validate_head_search_calibration_operating_point(
        rule=_rule(MAIN_POINTS), measurements=MAIN_MEASUREMENTS, candidate_id=CANDIDATE_ID
    )

    assert document["held_out_report"]["measured"] is False
    assert document["held_out_report"]["frame_count"] == 0


def test_the_held_out_report_refuses_an_undeclared_split():
    undeclared = _frame("test", [_truth(900, 900)], [_detection(900.1, 900.1, 0.90)])

    _refuses(
        CAL_SPLIT_LEAK,
        report_held_out_measurements,
        rule=_rule(MAIN_POINTS),
        measurements=(undeclared,),
        candidate_id=CANDIDATE_ID,
        point=MAIN_POINTS[1],
    )


def test_re_evaluation_is_deterministic_and_the_grid_keeps_the_declared_order():
    first = _select(MAIN_POINTS, MAIN_MEASUREMENTS)
    second = _select(MAIN_POINTS, MAIN_MEASUREMENTS)

    assert first["chosen_point"] == second["chosen_point"]
    assert first["chosen_index"] == second["chosen_index"]
    assert first["ties_broken_by"] == second["ties_broken_by"]
    assert first["grid"] == second["grid"]
    assert first["grid_sha256"] == second["grid_sha256"]
    assert _cells(first) == list(MAIN_POINTS)


def test_re_evaluation_does_not_depend_on_the_frame_order():
    reordered = MAIN_MEASUREMENTS[3:] + MAIN_MEASUREMENTS[:3]

    assert (
        _select(MAIN_POINTS, reordered)["grid"] == _select(MAIN_POINTS, MAIN_MEASUREMENTS)["grid"]
    )


def test_the_phase_refuses_a_rule_record_that_admits_measurements_before_it():
    rule = _rule(MAIN_POINTS)
    body = {key: value for key, value in rule.items() if key != "rule_sha256"}
    body["measurements_admitted"] = 3
    doctored = {**body, "rule_sha256": canonical_sha256(body)}

    _refuses(
        CAL_RULE_AFTER_MEASUREMENT,
        validate_head_search_calibration_operating_point,
        rule=doctored,
        measurements=MAIN_MEASUREMENTS,
        candidate_id=CANDIDATE_ID,
    )


def test_a_hand_rolled_rule_record_is_a_caller_error():
    with pytest.raises(ValueError):
        validate_head_search_calibration_operating_point(
            rule={"points": list(MAIN_POINTS)},
            measurements=MAIN_MEASUREMENTS,
            candidate_id=CANDIDATE_ID,
        )


def test_the_phase_writes_only_the_explicit_output_path(tmp_path):
    output = tmp_path / "phase3.json"
    before = set(tmp_path.rglob("*"))

    document = validate_head_search_calibration_operating_point(
        rule=_rule(MAIN_POINTS),
        measurements=MAIN_MEASUREMENTS,
        candidate_id=CANDIDATE_ID,
        held_out_measurements=HELD_OUT_MEASUREMENTS,
        output_path=output,
    )

    assert set(tmp_path.rglob("*")) - before == {output}
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["chosen_point"] == document["chosen_point"]
    assert written["held_out_consumed_for_selection"] is False


def test_the_chosen_point_is_the_four_values_the_later_phases_carry_over():
    result = _select(MAIN_POINTS, MAIN_MEASUREMENTS)

    assert result["chosen_point"] == {
        "min_confidence": 0.35,
        "tracking_iou": 0.95,
        "min_bbox_aspect": 1.0,
        "min_area_px2": 1.0,
    }


def test_the_choice_names_the_point_the_chain_and_the_deciding_key():
    rule = _rule(MAIN_POINTS)
    grid = evaluate_operating_point_grid(
        rule=rule, measurements=MAIN_MEASUREMENTS, candidate_id=CANDIDATE_ID
    )

    choice = choose_operating_point(rule=rule, grid=grid)

    assert set(choice) == {
        "tie_break_chain",
        "ties_broken_by",
        "chosen_point",
        "chosen_index",
        "chosen_cell",
    }
    assert choice["chosen_point"] == MAIN_POINTS[1]
    assert choice["chosen_cell"] == grid["cells"][1]
    assert choice["ties_broken_by"] == "f1"
