"""Phase 6 of the formal head-search calibration: the five search parameters.

Every fixture here is synthetic: no ROS, no MuJoCo, no detector, no GPU, no motion. The measured inputs
are plain dictionaries carrying the path and sha256 of the evidence file they came from, exactly as the
phase consumes them, and the sweep fixture is the phase-2 geometry document as phase 2 writes it.

The tests pin the five formulas of design section 7.1, every refusal the phase owns, the deadband
search's smallest-stable-value rule, determinism, and the evidence-block contract phase 8 imposes.
"""

from __future__ import annotations

import json

import pytest
from so101_demo.act.head_search_calibration_bundle import (
    ALSO_RECORDED_ITEMS,
    PARAMETER_EVIDENCE_KEYS,
    RUNTIME_IDENTITY_FIELDS,
    assemble_calibration_bundle,
)
from so101_demo.act.head_search_calibration_inputs import (
    SEALED_INPUT_NAMES,
    CalibrationInputsRefused,
)
from so101_demo.act.head_search_coarse_step_measurement.contracts import (
    CAL_SWEEP_EVIDENCE_CONTRADICTORY,
    CAL_SWEEP_EVIDENCE_PARTIAL,
)
from so101_demo.act.head_search_operating_point import CAL_SPLIT_LEAK
from so101_demo.act.head_search_search_params import (
    CAL_DEADBAND_OSCILLATES,
    CAL_EFFECTIVE_VALUE_MISMATCH,
    CAL_SWEEP_UNSTABLE,
    CAL_TIMEOUT_UNBOUNDED,
    CAL_VERTICAL_BOUNDS_UNPROJECTED,
    PARAMETERS,
    CalibrationSearchParamsRefused,
    compute_center_deadband_px,
    compute_max_fine_corrections,
    compute_max_fine_total_rad,
    compute_search_timeout_s,
    compute_vertical_bounds_px,
    max_stable_stop_points,
    validate_head_search_calibration_search_parameters,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64

HELD_OUT_SPLITS = ("head_held_out",)

#: the sealed camera geometry the campaign measured (HS-290): 640x480 head camera
HORIZONTAL_FOV_RAD = 1.3121067481206794
IMAGE_WIDTH_PX = 640
IMAGE_HEIGHT_PX = 480
SAFETY_MARGIN_PX = 48.0

#: the p99 timing measurements of one search step and the controller's control period
P99_SETTLE_S = 0.24
P99_FRAME_S = 0.06
CONTROL_PERIOD_S = 0.1

#: the values the happy-path sweep, deadband trial and fine-correction episodes imply
EXPECTED_MAX_STABLE_STOPS = 3
EXPECTED_TIMEOUT_S = 1.4
EXPECTED_DEADBAND_PX = 2.0
EXPECTED_VERTICAL_BOUNDS_PX = [96.0, 432.0]
EXPECTED_MAX_FINE_CORRECTIONS = 5
EXPECTED_MAX_FINE_TOTAL_RAD = 0.14

#: the parameters phase 6 does not own, as minimal valid values for the phase-8 assembly test
PERCEPTION_VALUES = {
    "min_confidence": (0.25, "ratio"),
    "tracking_iou": (0.5, "ratio"),
    "min_bbox_aspect": (0.5, "ratio"),
    "min_area_px2": (100.0, "px^2"),
}

TIMING_VALUES = {
    "max_age_s": (0.15, "s"),
    "max_skew_s": (0.05, "s"),
    "submit_lead_s": (0.02, "s"),
    "stop_velocity_rad_s": (0.01, "rad/s"),
    "stop_latency_s": (0.05, "s"),
}


def camera_document(**overrides) -> dict:
    """The head-camera measurement document: field of view, resolution, jitter and image margin."""

    document = {
        "path": "camera-config.json",
        "sha256": SHA_A,
        "horizontal_fov_rad": HORIZONTAL_FOV_RAD,
        "image_width_px": IMAGE_WIDTH_PX,
        "image_height_px": IMAGE_HEIGHT_PX,
        "centre_jitter_rad": 0.004,
        "safety_margin_px": SAFETY_MARGIN_PX,
    }
    document.update(overrides)
    return document


def timing_document(**overrides) -> dict:
    """The per-step timing measurements: p99 settle, p99 frame time and one control period."""

    document = {
        "path": "timing-measurements.json",
        "sha256": SHA_B,
        "p99_settle_s": P99_SETTLE_S,
        "p99_frame_s": P99_FRAME_S,
        "control_period_s": CONTROL_PERIOD_S,
    }
    document.update(overrides)
    return document


def sweep_document(*, safe_interval=(-6.0, 6.0), anchors=None, **overrides) -> dict:
    """The phase-2 document as phase 2 writes it: sealed geometry plus the bounded coverage proof."""

    if anchors is None:
        anchors = [
            {
                "anchor": "default",
                "anchor_rad": 0.1,
                "targets_rad": [-0.17559216195018026, 0.08047101126546086],
                "stop_count": 2,
            },
            {
                "anchor": "left",
                "anchor_rad": 0.0,
                "targets_rad": [-0.17559216195018026, 0.08047101126546086, 0.2],
                "stop_count": 3,
            },
        ]
    document = {
        "schema_version": 1,
        "kind": "head_search_calibration_geometry",
        "phase": "geometry_coverage",
        "sealed_geometry": {"path": "head-camera-geometry.json", "sha256": SHA_C},
        "geometry": {
            "horizontal_fov_rad": HORIZONTAL_FOV_RAD,
            "lock_valid_neck_rad": list(safe_interval),
            "required_search_domain_rad": [-0.17559216195018026, 0.08047101126546086],
            "anchors_rad": {"default": 0.1, "left": 0.0},
        },
        "coverage_proof": {
            "required_search_domain_rad": [-0.17559216195018026, 0.08047101126546086],
            "safe_interval_rad": list(safe_interval),
            "horizontal_fov_rad": HORIZONTAL_FOV_RAD,
            "coarse_step_candidate_rad": 0.6560533740603397,
            "sweep": "bounded_two_way",
            "coverage": "horizontal_fov_union_of_stops",
            "anchors": anchors,
            "coverage_complete": True,
        },
        "motion_commanded": False,
    }
    document.update(overrides)
    return document


def deadband_candidates(records=None) -> list:
    """The recorded deadband trials: one longest locked run and reversal count per candidate."""

    if records is None:
        records = [
            {"center_deadband_px": 1.0, "longest_locked_run_frames": 1, "direction_reversals": 5},
            {"center_deadband_px": 2.0, "longest_locked_run_frames": 3, "direction_reversals": 0},
            {"center_deadband_px": 6.0, "longest_locked_run_frames": 8, "direction_reversals": 0},
        ]
    return [dict(record) for record in records]


def workspace_projection(**overrides) -> dict:
    """The legal pick workspace projected into the head camera, in image pixels."""

    document = {
        "path": "workspace-projection.json",
        "sha256": SHA_D,
        "top_px": 96.0,
        "bottom_px": 470.0,
    }
    document.update(overrides)
    return document


def episodes(*, split="head_held_out") -> list:
    """Held-out validation episodes; the failed one is excluded from every number."""

    return [
        {
            "episode_id": "held-01",
            "split": split,
            "succeeded": True,
            "fine_corrections": 2,
            "fine_corrections_rad": [0.02, 0.03],
        },
        {
            "episode_id": "held-02",
            "split": split,
            "succeeded": True,
            "fine_corrections": 4,
            "fine_corrections_rad": [0.01, 0.04, 0.02, 0.03],
        },
        {
            "episode_id": "held-03",
            "split": split,
            "succeeded": False,
            "fine_corrections": 6,
            "fine_corrections_rad": [0.05, 0.05, 0.05, 0.05, 0.05, 0.05],
        },
    ]


def synthetic_block(value, unit) -> dict:
    """A minimal evidence block for a parameter phase 6 does not own."""

    return {
        "value": value,
        "unit": unit,
        "selection_formula": "synthetic fixture of another phase",
        "input_evidence": [{"path": "fixture.json", "sha256": SHA_A}],
        "observed_distribution": {"fixture": 1},
        "safety_margin": {"margin": 0.0},
        "production_owner": "so101_demo.act.search.HeadSearchController",
        "startup_readback": {"observed_value": value},
    }


def synthetic_runtime_identity() -> dict:
    """A complete runtime identity, field for field."""

    identity = {field: "measured-once" for field in RUNTIME_IDENTITY_FIELDS}
    identity["detector_weights_sha256"] = SHA_A
    identity["camera_intrinsics_sha256"] = SHA_B
    return identity


#: the generated candidate steps of the phase-6 fixture geometry (HS-290's field of view, largest first)
COARSE_STEP_CANDIDATES = (
    0.6560533740603397,
    0.32802668703016985,
    0.16401334351508493,
    0.08200667175754246,
    0.04100333587877123,
)
COARSE_STEP_OBSERVATIONS_PATH = "coarse-step-observations.json"


def coarse_step_observations(*, geometry=None, weights_sha256=SHA_A, steps=None, digest=True) -> dict:
    """The raw val sweep of the phase-6 fixture geometry: a real bounded plan, four val scenes.

    The stops are the repository's own `bounded_search_stops`, because phase 6 refuses a recorded stop
    that is not the bounded plan of its candidate.
    """

    from so101_demo.act.head_search_calibration_geometry import generate_coarse_step_candidates
    from so101_demo.act.head_search_domain import bounded_search_stops

    geometry = sweep_document()["geometry"] if geometry is None else geometry
    if steps is None:
        steps = generate_coarse_step_candidates(geometry["horizontal_fov_rad"])
    anchors_rad = dict(geometry["anchors_rad"])
    scenes = (
        (410000, "scene-004100000", "one_cup_distractors", 1),
        (410002, "scene-004100002", "two_cups", 2),
    )
    candidates = []
    for step in steps:
        anchors = []
        for name, anchor_rad in anchors_rad.items():
            plan = bounded_search_stops(
                anchor_rad=anchor_rad,
                required_domain_rad=geometry["required_search_domain_rad"],
                safe_interval_rad=geometry["lock_valid_neck_rad"],
                horizontal_fov_rad=geometry["horizontal_fov_rad"],
                coarse_step_rad=step,
            )
            anchors.append(
                {
                    "anchor": name,
                    "anchor_rad": anchor_rad,
                    "targets_rad": [float(target) for target in plan.targets_rad],
                }
            )
        records = []
        for scene_id, scene_group_id, scenario, visible in scenes:
            cups = (("plastic_cup", 100.0, 100.0), ("plastic_cup_b", 200.0, 120.0))[:visible]
            stops = []
            for anchor in anchors:
                for index, target in enumerate(anchor["targets_rad"]):
                    stops.append(
                        {
                            "anchor": anchor["anchor"],
                            "stop_index": index,
                            "stop_rad": target,
                            "truth": [
                                {"x": x, "y": y, "body": body, "visible_px": 8000}
                                for body, x, y in cups
                            ],
                            "detections": [
                                {"x": x + 0.2, "y": y + 0.2, "conf": 0.9 - 0.05 * position}
                                for position, (_body, x, y) in enumerate(cups)
                            ],
                            "image_sha256": SHA_D,
                        }
                    )
            records.append(
                {
                    "scene_id": scene_id,
                    "scene_group_id": scene_group_id,
                    "scenario": scenario,
                    "dataset_visible_instances": visible,
                    "passes": [{"pass_index": 0, "stops": stops}],
                }
            )
        candidates.append({"coarse_step_rad": float(step), "anchors": anchors, "scenes": records})
    document = {
        "schema_version": 1,
        "kind": "head_search_coarse_step_val_sweep",
        "phase": "coarse_step_measurement",
        "domain": "head",
        "split": "val",
        "match_radius_px": 8.0,
        "passes": 1,
        "geometry": {
            "path": "head-camera-geometry.json",
            "sha256": SHA_C,
            "seal_sha256": SHA_C,
            "horizontal_fov_rad": geometry["horizontal_fov_rad"],
            "lock_valid_neck_rad": list(geometry["lock_valid_neck_rad"]),
            "required_search_domain_rad": list(geometry["required_search_domain_rad"]),
            "anchors_rad": anchors_rad,
        },
        "model": {
            "candidate_id": "C",
            "weights_sha256": weights_sha256,
            "min_confidence": 0.25,
            "tracking_iou": 0.5,
        },
        "dataset": {
            "manifest_path": "head-dataset/dataset-manifest.json",
            "manifest_sha256": SHA_D,
            "split": "val",
            "scene_count": len(scenes),
            "scene_limit": None,
        },
        "candidates": candidates,
        "path": COARSE_STEP_OBSERVATIONS_PATH,
    }
    document["sha256"] = (
        canonical_sha256({key: value for key, value in document.items() if key != "sha256"})
        if digest
        else "0" * 64
    )
    return document


def build(**overrides) -> dict:
    """The phase document for the happy-path fixtures, with any input replaced by the caller."""

    arguments = {
        "bounded_sweep": sweep_document(),
        "timing": timing_document(),
        "camera": camera_document(),
        "deadband_candidates": deadband_candidates(),
        "workspace_projection": workspace_projection(),
        "fine_correction_episodes": episodes(),
        "held_out_splits": HELD_OUT_SPLITS,
    }
    arguments.update(overrides)
    return validate_head_search_calibration_search_parameters(**arguments)


def refusal_of(call):
    """Run one call that must refuse and return the code it refused with."""

    with pytest.raises(CalibrationSearchParamsRefused) as raised:
        call()
    assert isinstance(raised.value, CalibrationInputsRefused)
    return raised.value.code


# --------------------------------------------------------------------------------------------------
# happy path: all five values, with the evidence block phase 8 consumes
# --------------------------------------------------------------------------------------------------


def test_happy_path_computes_the_five_parameters_in_design_order():
    document = build()

    assert document["phase"] == "search_parameters"
    assert list(document["parameters"]) == list(PARAMETERS)
    assert document["motion_commanded"] is False
    assert document["parameters"]["search_timeout_s"]["value"] == pytest.approx(EXPECTED_TIMEOUT_S)
    assert document["parameters"]["center_deadband_px"]["value"] == EXPECTED_DEADBAND_PX
    assert document["parameters"]["vertical_bounds_px"]["value"] == EXPECTED_VERTICAL_BOUNDS_PX
    assert document["parameters"]["max_fine_corrections"]["value"] == EXPECTED_MAX_FINE_CORRECTIONS
    assert document["parameters"]["max_fine_total_rad"]["value"] == pytest.approx(
        EXPECTED_MAX_FINE_TOTAL_RAD
    )


def test_every_evidence_block_carries_exactly_the_phase_8_keys():
    document = build()

    for name, block in document["parameters"].items():
        assert set(block) == set(PARAMETER_EVIDENCE_KEYS), name
        assert block["unit"], name
        assert block["selection_formula"], name
        assert block["production_owner"], name
        assert block["observed_distribution"], name
        assert block["safety_margin"], name
        assert block["input_evidence"], name
        assert block["startup_readback"]["observed_value"] == block["value"], name


def test_evidence_units_are_the_ones_the_design_fixes():
    document = build()

    assert document["parameters"]["search_timeout_s"]["unit"] == "s"
    assert document["parameters"]["center_deadband_px"]["unit"] == "px"
    assert document["parameters"]["vertical_bounds_px"]["unit"] == "px"
    assert document["parameters"]["max_fine_corrections"]["unit"] == "count"
    assert document["parameters"]["max_fine_total_rad"]["unit"] == "rad"


def test_evidence_cites_the_measured_inputs_with_their_digests():
    document = build()

    referenced = {
        (reference["path"], reference["sha256"])
        for block in document["parameters"].values()
        for reference in block["input_evidence"]
    }
    assert ("timing-measurements.json", SHA_B) in referenced
    assert ("camera-config.json", SHA_A) in referenced
    assert ("head-camera-geometry.json", SHA_C) in referenced
    assert ("workspace-projection.json", SHA_D) in referenced


# --------------------------------------------------------------------------------------------------
# search_timeout_s
# --------------------------------------------------------------------------------------------------


def test_search_timeout_formula_uses_stops_p99_times_and_the_control_period_guard():
    block = compute_search_timeout_s(
        bounded_sweep=sweep_document(),
        timing=timing_document(),
        max_fine_corrections=EXPECTED_MAX_FINE_CORRECTIONS,
    )

    assert block["value"] == pytest.approx(
        EXPECTED_MAX_STABLE_STOPS * (P99_SETTLE_S + P99_FRAME_S)
        + EXPECTED_MAX_FINE_CORRECTIONS * CONTROL_PERIOD_S
    )
    assert block["observed_distribution"]["max_stable_stop_points"] == EXPECTED_MAX_STABLE_STOPS
    assert block["observed_distribution"]["p99_settle_s"] == P99_SETTLE_S
    assert block["observed_distribution"]["p99_frame_s"] == P99_FRAME_S
    assert block["observed_distribution"]["control_period_s"] == CONTROL_PERIOD_S
    assert block["safety_margin"]["guard_control_periods"] == EXPECTED_MAX_FINE_CORRECTIONS
    assert block["safety_margin"]["guard_s"] == pytest.approx(
        EXPECTED_MAX_FINE_CORRECTIONS * CONTROL_PERIOD_S
    )
    assert "p99_settle_s" in block["selection_formula"]
    assert "p99_frame_s" in block["selection_formula"]
    assert "control_period_s" in block["selection_formula"]


def test_max_stable_stop_points_is_the_maximum_over_the_sweep_anchors():
    assert max_stable_stop_points(sweep_document()) == EXPECTED_MAX_STABLE_STOPS
    proof = sweep_document()["coverage_proof"]
    assert max_stable_stop_points(proof) == EXPECTED_MAX_STABLE_STOPS


def test_search_timeout_refuses_without_a_stable_stop_point():
    code = refusal_of(
        lambda: compute_search_timeout_s(
            bounded_sweep=sweep_document(anchors=[]),
            timing=timing_document(),
            max_fine_corrections=EXPECTED_MAX_FINE_CORRECTIONS,
        )
    )

    assert code == CAL_TIMEOUT_UNBOUNDED


def test_search_timeout_refuses_without_the_p99_measurements():
    for timing in (timing_document(p99_settle_s=None), {"path": "t.json", "sha256": SHA_B}):
        code = refusal_of(
            lambda timing=timing: compute_search_timeout_s(
                bounded_sweep=sweep_document(),
                timing=timing,
                max_fine_corrections=EXPECTED_MAX_FINE_CORRECTIONS,
            )
        )
        assert code == CAL_TIMEOUT_UNBOUNDED


def test_search_timeout_refuses_without_a_fine_correction_bound():
    for corrections in (0, None):
        code = refusal_of(
            lambda corrections=corrections: compute_search_timeout_s(
                bounded_sweep=sweep_document(),
                timing=timing_document(),
                max_fine_corrections=corrections,
            )
        )
        assert code == CAL_TIMEOUT_UNBOUNDED


# --------------------------------------------------------------------------------------------------
# center_deadband_px
# --------------------------------------------------------------------------------------------------


def test_deadband_starts_from_the_centre_jitter_and_the_camera_angular_resolution():
    block = compute_center_deadband_px(camera=camera_document(), candidates=deadband_candidates())

    rad_per_px = HORIZONTAL_FOV_RAD / IMAGE_WIDTH_PX
    assert block["observed_distribution"]["rad_per_px"] == pytest.approx(rad_per_px)
    assert block["observed_distribution"]["centre_jitter_px"] == pytest.approx(0.004 / rad_per_px)
    assert block["observed_distribution"]["start_deadband_px"] == EXPECTED_DEADBAND_PX
    assert "ceil" in block["selection_formula"]
    assert "three consecutive frames" in block["selection_formula"]
    assert "reversal" in block["selection_formula"]


def test_deadband_chooses_the_smallest_stable_value_and_skips_oscillating_ones():
    block = compute_center_deadband_px(
        camera=camera_document(),
        candidates=deadband_candidates(
            [
                {
                    "center_deadband_px": 2.0,
                    "longest_locked_run_frames": 4,
                    "direction_reversals": 2,
                },
                {
                    "center_deadband_px": 4.0,
                    "longest_locked_run_frames": 5,
                    "direction_reversals": 1,
                },
                {
                    "center_deadband_px": 6.0,
                    "longest_locked_run_frames": 6,
                    "direction_reversals": 0,
                },
                {
                    "center_deadband_px": 9.0,
                    "longest_locked_run_frames": 9,
                    "direction_reversals": 0,
                },
            ]
        ),
    )

    assert block["value"] == 6.0
    verdicts = block["observed_distribution"]["candidates"]
    assert verdicts["2.0"]["oscillated"] is True
    assert verdicts["2.0"]["chosen"] is False
    assert verdicts["4.0"]["oscillated"] is True
    assert verdicts["6.0"]["chosen"] is True
    assert verdicts["9.0"]["chosen"] is False
    assert block["safety_margin"]["chosen_minus_start_px"] == 4.0


def test_deadband_chooses_the_smallest_of_two_stable_values():
    block = compute_center_deadband_px(
        camera=camera_document(),
        candidates=deadband_candidates(
            [
                {
                    "center_deadband_px": 5.0,
                    "longest_locked_run_frames": 3,
                    "direction_reversals": 0,
                },
                {
                    "center_deadband_px": 8.0,
                    "longest_locked_run_frames": 9,
                    "direction_reversals": 0,
                },
            ]
        ),
    )

    assert block["value"] == 5.0


def test_deadband_requires_three_consecutive_locked_frames():
    code = refusal_of(
        lambda: compute_center_deadband_px(
            camera=camera_document(),
            candidates=deadband_candidates(
                [
                    {
                        "center_deadband_px": 3.0,
                        "longest_locked_run_frames": 2,
                        "direction_reversals": 0,
                    }
                ]
            ),
        )
    )

    assert code == CAL_DEADBAND_OSCILLATES


def test_deadband_refuses_when_every_candidate_oscillates_in_the_searched_range():
    code = refusal_of(
        lambda: compute_center_deadband_px(
            camera=camera_document(),
            candidates=deadband_candidates(
                [
                    {
                        "center_deadband_px": 2.0,
                        "longest_locked_run_frames": 3,
                        "direction_reversals": 1,
                    },
                    {
                        "center_deadband_px": 6.0,
                        "longest_locked_run_frames": 8,
                        "direction_reversals": 2,
                    },
                ]
            ),
        )
    )

    assert code == CAL_DEADBAND_OSCILLATES


def test_deadband_ignores_a_stable_candidate_below_the_computed_start():
    block = compute_center_deadband_px(
        camera=camera_document(),
        candidates=deadband_candidates(
            [
                {
                    "center_deadband_px": 1.0,
                    "longest_locked_run_frames": 9,
                    "direction_reversals": 0,
                },
                {
                    "center_deadband_px": 7.0,
                    "longest_locked_run_frames": 3,
                    "direction_reversals": 0,
                },
            ]
        ),
    )

    assert block["value"] == 7.0
    assert block["observed_distribution"]["candidates"]["1.0"]["in_searched_range"] is False


def test_deadband_refuses_when_no_candidate_is_declared_at_all():
    code = refusal_of(lambda: compute_center_deadband_px(camera=camera_document(), candidates=[]))

    assert code == CAL_DEADBAND_OSCILLATES


# --------------------------------------------------------------------------------------------------
# vertical_bounds_px
# --------------------------------------------------------------------------------------------------


def test_vertical_bounds_intersect_the_workspace_projection_with_the_image_safety_margin():
    block = compute_vertical_bounds_px(
        workspace_projection=workspace_projection(), camera=camera_document()
    )

    assert block["value"] == EXPECTED_VERTICAL_BOUNDS_PX
    assert block["observed_distribution"]["workspace_projection_px"] == [96.0, 470.0]
    assert block["observed_distribution"]["image_safety_margin_px"] == SAFETY_MARGIN_PX
    assert block["observed_distribution"]["image_height_px"] == IMAGE_HEIGHT_PX
    assert block["safety_margin"]["bottom_clip_px"] == pytest.approx(470.0 - 432.0)
    assert block["safety_margin"]["safety_margin_px"] == SAFETY_MARGIN_PX
    assert "workspace" in block["selection_formula"]
    assert "detection" in block["selection_formula"]


def test_vertical_bounds_are_never_backfilled_from_detection_extremes():
    code = refusal_of(
        lambda: compute_vertical_bounds_px(
            workspace_projection=None,
            camera=camera_document(),
            detection_extremes=[{"y1_px": 100.0, "y2_px": 400.0}],
        )
    )

    assert code == CAL_VERTICAL_BOUNDS_UNPROJECTED
    # even when a projection is available, detection extremes are never the evidence
    code = refusal_of(
        lambda: compute_vertical_bounds_px(
            workspace_projection=workspace_projection(),
            camera=camera_document(),
            detection_extremes=[{"y1_px": 100.0, "y2_px": 400.0}],
        )
    )
    assert code == CAL_VERTICAL_BOUNDS_UNPROJECTED


def test_vertical_bounds_refuse_without_a_workspace_projection():
    code = refusal_of(
        lambda: compute_vertical_bounds_px(workspace_projection=None, camera=camera_document())
    )

    assert code == CAL_VERTICAL_BOUNDS_UNPROJECTED


def test_vertical_bounds_refuse_when_the_projection_misses_the_safety_margin():
    code = refusal_of(
        lambda: compute_vertical_bounds_px(
            workspace_projection=workspace_projection(top_px=460.0, bottom_px=478.0),
            camera=camera_document(),
        )
    )

    assert code == CAL_VERTICAL_BOUNDS_UNPROJECTED


def test_vertical_bounds_missing_camera_margin_is_a_caller_error():
    with pytest.raises(ValueError):
        compute_vertical_bounds_px(
            workspace_projection=workspace_projection(),
            camera={"path": "camera-config.json", "sha256": SHA_A, "image_height_px": 480.0},
        )


# --------------------------------------------------------------------------------------------------
# max_fine_corrections and max_fine_total_rad
# --------------------------------------------------------------------------------------------------


def test_max_fine_corrections_is_the_successful_maximum_plus_one_recovery_allowance():
    block = compute_max_fine_corrections(
        episodes=episodes(), held_out_splits=HELD_OUT_SPLITS, bounded_sweep=sweep_document()
    )

    assert block["value"] == EXPECTED_MAX_FINE_CORRECTIONS
    assert isinstance(block["value"], int)
    assert block["observed_distribution"]["max_needed_fine_corrections"] == 4
    assert block["observed_distribution"]["successful_episodes"] == ["held-01", "held-02"]
    assert block["safety_margin"]["recovery_allowance"] == 1
    assert "recovery" in block["selection_formula"]


def test_max_fine_total_rad_is_the_largest_cumulative_plus_the_largest_single_correction():
    block = compute_max_fine_total_rad(
        episodes=episodes(), held_out_splits=HELD_OUT_SPLITS, bounded_sweep=sweep_document()
    )

    assert block["value"] == pytest.approx(EXPECTED_MAX_FINE_TOTAL_RAD)
    assert block["observed_distribution"][
        "largest_cumulative_fine_correction_rad"
    ] == pytest.approx(0.10)
    assert block["observed_distribution"]["largest_single_correction_rad"] == pytest.approx(0.04)
    assert block["safety_margin"]["observed_largest_single_correction_rad"] == pytest.approx(0.04)
    assert "cumulative" in block["selection_formula"]
    assert "largest single" in block["selection_formula"]


def test_max_fine_corrections_refuses_when_the_budget_would_leave_the_safe_interval():
    code = refusal_of(
        lambda: compute_max_fine_corrections(
            episodes=episodes(),
            held_out_splits=HELD_OUT_SPLITS,
            bounded_sweep=sweep_document(safe_interval=(-0.2, 0.2)),
        )
    )

    assert code == CAL_SWEEP_UNSTABLE


def test_max_fine_total_rad_refuses_when_it_would_cross_the_safe_interval():
    code = refusal_of(
        lambda: compute_max_fine_total_rad(
            episodes=episodes(),
            held_out_splits=HELD_OUT_SPLITS,
            bounded_sweep=sweep_document(safe_interval=(-0.2, 0.21)),
        )
    )

    assert code == CAL_SWEEP_UNSTABLE


def test_fine_correction_numbers_refuse_when_no_episode_succeeded():
    failed = [
        {
            "episode_id": "held-01",
            "split": "head_held_out",
            "succeeded": False,
            "fine_corrections": 3,
            "fine_corrections_rad": [0.02, 0.02, 0.02],
        }
    ]

    assert (
        refusal_of(
            lambda: compute_max_fine_corrections(
                episodes=failed, held_out_splits=HELD_OUT_SPLITS, bounded_sweep=sweep_document()
            )
        )
        == CAL_SWEEP_UNSTABLE
    )
    assert (
        refusal_of(
            lambda: compute_max_fine_total_rad(
                episodes=failed, held_out_splits=HELD_OUT_SPLITS, bounded_sweep=sweep_document()
            )
        )
        == CAL_SWEEP_UNSTABLE
    )


def test_fine_correction_numbers_refuse_calibration_frames():
    for split in ("calibration", "head_val"):
        for compute in (compute_max_fine_corrections, compute_max_fine_total_rad):
            code = refusal_of(
                lambda compute=compute, split=split: compute(
                    episodes=episodes(split=split),
                    held_out_splits=HELD_OUT_SPLITS,
                    bounded_sweep=sweep_document(),
                )
            )
            assert code == CAL_SPLIT_LEAK, (compute.__name__, split)
        assert (
            refusal_of(lambda split=split: build(fine_correction_episodes=episodes(split=split)))
            == CAL_SPLIT_LEAK
        )


def test_fine_correction_numbers_refuse_an_episode_without_a_split():
    frames = episodes()
    del frames[0]["split"]

    for compute in (compute_max_fine_corrections, compute_max_fine_total_rad):
        code = refusal_of(
            lambda compute=compute: compute(
                episodes=frames, held_out_splits=HELD_OUT_SPLITS, bounded_sweep=sweep_document()
            )
        )
        assert code == CAL_SPLIT_LEAK, compute.__name__


# --------------------------------------------------------------------------------------------------
# determinism, writing, and the phase-8 contract
# --------------------------------------------------------------------------------------------------


def test_the_phase_document_is_deterministic():
    first = build()
    second = build()

    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_the_phase_writes_nothing_without_an_output_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    build()

    assert list(tmp_path.iterdir()) == []


def test_the_phase_writes_its_document_once_when_asked(tmp_path):
    output = tmp_path / "search-calibration.json"
    document = validate_head_search_calibration_search_parameters(
        bounded_sweep=sweep_document(),
        timing=timing_document(),
        camera=camera_document(),
        deadband_candidates=deadband_candidates(),
        workspace_projection=workspace_projection(),
        fine_correction_episodes=episodes(),
        held_out_splits=HELD_OUT_SPLITS,
        output_path=output,
    )

    assert sorted(path.name for path in tmp_path.iterdir()) == ["search-calibration.json"]
    assert json.loads(output.read_text(encoding="utf-8")) == document


def test_a_reported_startup_readback_is_checked_and_recorded():
    document = build(
        startup_readbacks={
            "search_timeout_s": {
                "observed_value": EXPECTED_TIMEOUT_S,
                "read_from": "head_search_runtime.json",
            }
        }
    )

    readback = document["parameters"]["search_timeout_s"]["startup_readback"]
    assert readback["verified"] is True
    assert readback["read_from"] == "head_search_runtime.json"


def test_a_startup_readback_that_disagrees_refuses_with_phase_8s_code():
    code = refusal_of(
        lambda: build(startup_readbacks={"search_timeout_s": {"observed_value": 9.75}})
    )

    assert code == CAL_EFFECTIVE_VALUE_MISMATCH


def test_the_six_blocks_survive_phase_8_assembly_verbatim():
    document = build(
        bounded_sweep=sweep_document(chosen_candidate_rad=COARSE_STEP_CANDIDATES[0]),
        coarse_step_observations=coarse_step_observations(),
        selected_weights_sha256=SHA_A,
    )
    phase_inputs = {
        "geometry_coverage": {
            "parameters": {
                "horizontal_fov_rad": synthetic_block(HORIZONTAL_FOV_RAD, "rad"),
                "lock_valid_neck_rad": synthetic_block([-6.0, 6.0], "rad"),
            }
        },
        "perception_operating_point": {
            "parameters": {
                name: synthetic_block(value, unit)
                for name, (value, unit) in PERCEPTION_VALUES.items()
            }
        },
        "search_parameters": {
            "parameters": {name: dict(block) for name, block in document["parameters"].items()}
        },
        "timing_stop_parameters": {
            "parameters": {
                name: synthetic_block(value, unit) for name, (value, unit) in TIMING_VALUES.items()
            }
        },
    }
    assembly = assemble_calibration_bundle(
        status="SUCCEEDED",
        command="ros2 run so101_demo_py so101_head_search_calibration run --run-root /evidence/run-01",
        exit_code=0,
        phase_inputs=phase_inputs,
        controlled_dependencies={
            name: {"path": f"{name}.json", "sha256": SHA_A} for name in SEALED_INPUT_NAMES
        },
        runtime_identity=synthetic_runtime_identity(),
        also_recorded={
            name: {
                "value_or_definition": 0.01 if name.endswith("rad_s") else "definition",
                "input_evidence": [{"path": "fixture.json", "sha256": SHA_A}],
                "startup_readback": {"observed_value": 0.01},
            }
            for name in ALSO_RECORDED_ITEMS
        },
    )

    bundled = assembly["bundle"]["parameters"]
    for name, block in document["parameters"].items():
        assert bundled[name] == block, name


# --------------------------------------------------------------------------------------------------
# the sixth parameter: the val sweep phase 6 owns the value of
# --------------------------------------------------------------------------------------------------


def test_phase_six_owns_the_coarse_step_when_the_val_sweep_is_declared():
    document = build(
        bounded_sweep=sweep_document(chosen_candidate_rad=COARSE_STEP_CANDIDATES[0]),
        coarse_step_observations=coarse_step_observations(),
        selected_weights_sha256=SHA_A,
    )

    assert list(document["parameter_names"]) == [
        "coarse_step_rad",
        *PARAMETERS,
    ]
    assert set(document["parameters"]) == {"coarse_step_rad", *PARAMETERS}
    assert document["uncomputed_parameter"] is None
    block = document["parameters"]["coarse_step_rad"]
    assert block["value"] == COARSE_STEP_CANDIDATES[0], "the largest candidate of the fixture"
    assert block["unit"] == "rad"
    assert tuple(block) == PARAMETER_EVIDENCE_KEYS
    assert document["coarse_step_measurement"]["chosen_coarse_step_rad"] == block["value"]
    assert document["coarse_step_measurement"]["candidates"], "every candidate keeps its verdict"


def test_without_a_declared_sweep_phase_six_still_records_the_gap_rather_than_a_number():
    document = build()

    assert "coarse_step_rad" not in document["parameters"]
    assert document["uncomputed_parameter"]["name"] == "coarse_step_rad"
    assert document["uncomputed_parameter"]["computed_here"] is False
    assert document["coarse_step_measurement"] is None


def test_a_val_sweep_that_supports_another_step_than_the_receipted_one_refuses_unstable():
    """Phase 2's receipts bind one step: a sweep supporting another leaves them unproven."""

    code = refusal_of(
        lambda: build(
            bounded_sweep=sweep_document(chosen_candidate_rad=COARSE_STEP_CANDIDATES[1]),
            coarse_step_observations=coarse_step_observations(),
            selected_weights_sha256=SHA_A,
        )
    )

    assert code == CAL_SWEEP_UNSTABLE


def test_a_bounded_sweep_without_a_receipted_candidate_refuses_the_coarse_step():
    code = refusal_of(
        lambda: build(
            coarse_step_observations=coarse_step_observations(),
            selected_weights_sha256=SHA_A,
        )
    )

    assert code == CAL_SWEEP_UNSTABLE


def test_a_val_sweep_of_another_model_is_refused_with_the_sweeps_own_code():
    code = refusal_of(
        lambda: build(
            bounded_sweep=sweep_document(chosen_candidate_rad=COARSE_STEP_CANDIDATES[0]),
            coarse_step_observations=coarse_step_observations(weights_sha256="9" * 64),
            selected_weights_sha256=SHA_A,
        )
    )

    assert code == CAL_SWEEP_EVIDENCE_CONTRADICTORY


def test_a_val_sweep_whose_digest_is_not_its_body_is_refused():
    code = refusal_of(
        lambda: build(
            bounded_sweep=sweep_document(chosen_candidate_rad=COARSE_STEP_CANDIDATES[0]),
            coarse_step_observations=coarse_step_observations(digest=False),
            selected_weights_sha256=SHA_A,
        )
    )

    assert code == CAL_SWEEP_EVIDENCE_CONTRADICTORY


def test_a_val_sweep_that_missed_a_candidate_is_refused_as_partial():
    code = refusal_of(
        lambda: build(
            bounded_sweep=sweep_document(chosen_candidate_rad=COARSE_STEP_CANDIDATES[0]),
            coarse_step_observations=coarse_step_observations(
                steps=COARSE_STEP_CANDIDATES[:-1]
            ),
            selected_weights_sha256=SHA_A,
        )
    )

    assert code == CAL_SWEEP_EVIDENCE_PARTIAL


def test_a_reported_startup_readback_of_the_coarse_step_is_checked_and_recorded():
    document = build(
        bounded_sweep=sweep_document(chosen_candidate_rad=COARSE_STEP_CANDIDATES[0]),
        coarse_step_observations=coarse_step_observations(),
        selected_weights_sha256=SHA_A,
        startup_readbacks={
            "coarse_step_rad": {
                "observed_value": COARSE_STEP_CANDIDATES[0],
                "read_from": "head_search_runtime.json",
            }
        },
    )

    readback = document["parameters"]["coarse_step_rad"]["startup_readback"]
    assert readback["verified"] is True
    assert readback["read_from"] == "head_search_runtime.json"

    code = refusal_of(
        lambda: build(
            bounded_sweep=sweep_document(chosen_candidate_rad=COARSE_STEP_CANDIDATES[0]),
            coarse_step_observations=coarse_step_observations(),
            selected_weights_sha256=SHA_A,
            startup_readbacks={"coarse_step_rad": {"observed_value": 0.5}},
        )
    )
    assert code == CAL_EFFECTIVE_VALUE_MISMATCH


def test_the_coarse_step_is_not_computed_from_a_declared_number():
    """The value comes from the swept evidence, never from the candidate phase 2 happened to receipt."""

    document = build(
        bounded_sweep=sweep_document(chosen_candidate_rad=COARSE_STEP_CANDIDATES[0]),
        coarse_step_observations=coarse_step_observations(),
        selected_weights_sha256=SHA_A,
    )

    block = document["parameters"]["coarse_step_rad"]
    assert block["selection_formula"]
    assert block["observed_distribution"]["measured_candidate_steps"] == list(
        COARSE_STEP_CANDIDATES
    )
    assert block["safety_margin"]["half_fov_rad"] == HORIZONTAL_FOV_RAD / 2.0
    assert [reference["path"] for reference in block["input_evidence"]] == [
        "head-camera-geometry.json",
        COARSE_STEP_OBSERVATIONS_PATH,
    ]


def test_a_constructed_readback_keeps_its_own_observation_and_verdict():
    """A readback taken off the running component is not relabelled as a caller's report."""

    from so101_demo.act.head_search_measured_readback import CONSTRUCTED_OBSERVATION

    document = build(
        startup_readbacks={
            "search_timeout_s": {
                "observed_value": EXPECTED_TIMEOUT_S,
                "observation": CONSTRUCTED_OBSERVATION,
                "verified": True,
                "source": "HeadSearchController(...).config['search_timeout_s']",
            }
        }
    )

    readback = document["parameters"]["search_timeout_s"]["startup_readback"]
    assert readback["observation"] == CONSTRUCTED_OBSERVATION
    assert readback["verified"] is True
    assert readback["source"] == "HeadSearchController(...).config['search_timeout_s']"


def test_a_constructed_readback_of_an_unobservable_value_stays_unverified():
    """A value the component could not be queried for is recorded unverified, never as an observation."""

    from so101_demo.act.head_search_measured_readback import CONSTRUCTED_OBSERVATION, NOT_OBSERVABLE

    document = build(
        startup_readbacks={
            "search_timeout_s": {
                "observed_value": EXPECTED_TIMEOUT_S,
                "observation": NOT_OBSERVABLE,
                "verified": False,
                "reason": "the installed controller refused the recorded values",
            }
        }
    )

    readback = document["parameters"]["search_timeout_s"]["startup_readback"]
    assert readback["verified"] is False
    assert readback["observation"] == NOT_OBSERVABLE
    assert "refused the recorded values" in readback["reason"]
    assert CONSTRUCTED_OBSERVATION != NOT_OBSERVABLE
