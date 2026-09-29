"""Task 3 (approved measurement protocol v2): phase-camera replay and live coverage.

Replay rows arrive at 2 ms and live rows at 10 Hz, and the two time axes must stay separate: a replay result may
satisfy geometric feasibility but may never be reported as live continuity. Everything here is deterministic and
free of ROS.
"""

import pytest

# the design's phase-camera coverage table and the approved plan name the same nine phases
PHASES = ("SEARCH", "APPROACH", "CLOSE", "MICRO_LIFT", "TRANSPORT", "ALIGN", "RELEASE",
          "RADIAL_RETREAT", "FINAL_CHECK")
CAMERAS = ("head_camera", "wrist_camera")
ALLOWED_OCCLUDERS = (
    "fixed_fingertip_pad_visual", "gripper_visual_00", "gripper_visual_01",
    "jaw_visual_00", "moving_fingertip_pad_visual",
)


def _matrix():
    return {
        "schema_version": 1,
        "kind": "task8_phase_camera_matrix",
        "occluders": list(ALLOWED_OCCLUDERS),
        "cameras": list(CAMERAS),
        "phases": [{"phase": phase, "cameras": list(CAMERAS),
                    "visible_fraction_min": 0.80, "out_of_frame_fraction_max": 0.02,
                    "bbox_center_bounds_px": [4.0, 635.0, 4.0, 475.0],
                    "max_source_gap_s": 0.100} for phase in PHASES],
    }


def _live_frame(**overrides):
    frame = {"session_id": "s", "reset_epoch": 1, "attempt_id": "a", "phase": "SEARCH",
             "camera": "head_camera", "group_owner": "arm", "monotonic_s": 0.0,
             "visible_fraction": 0.90, "out_of_frame_fraction": 0.01,
             "bbox_center_px": [320.0, 240.0]}
    frame.update(overrides)
    return frame


def _phase_camera():
    from so101_demo.act import task8_phase_camera as module

    return module


def test_the_module_exposes_the_documented_interfaces():
    module = _phase_camera()
    for name in ("evaluate_replay_coverage", "evaluate_live_continuity", "rasterize_cup_projection"):
        assert hasattr(module, name), name


def test_replay_rows_cannot_be_reported_as_live_continuity():
    module = _phase_camera()
    replay_rows = [{"phase": "SEARCH", "camera": "head_camera", "monotonic_s": 0.002 * index,
                    "visible_fraction": 0.9, "out_of_frame_fraction": 0.0,
                    "bbox_center_px": [320.0, 240.0]} for index in range(5)]
    verdict = module.evaluate_live_continuity(replay_rows, "calibration_live", _matrix())
    assert verdict["verdict"] == "INVALID"
    assert "REPLAY_ROWS" in verdict["reason"]


@pytest.mark.parametrize("phase", PHASES)
def test_every_phase_and_both_cameras_are_required(phase):
    module = _phase_camera()
    matrix = _matrix()
    matrix["phases"] = [entry for entry in matrix["phases"] if entry["phase"] != phase]
    rows = [{"phase": other, "camera": camera, "monotonic_s": 0.0, "visible_fraction": 0.9,
             "out_of_frame_fraction": 0.0, "bbox_center_px": [320.0, 240.0]}
            for other in PHASES if other != phase for camera in CAMERAS]
    verdict = module.evaluate_replay_coverage(rows, matrix)
    assert verdict["verdict"] == "FAIL"
    assert phase in verdict["reason"]


@pytest.mark.parametrize("case", [
    {"monotonic_s": 0.150},                                  # 100 ms source gap
    {"session_id": "other"},                                 # crossing session
    {"reset_epoch": 2},                                      # crossing reset epoch
    {"attempt_id": "b"},                                     # crossing attempt
    {"group_owner": "table"},                                # wrong group owner
    {"out_of_frame_fraction": 0.05},                         # above the 0.02 ceiling
    {"visible_fraction": 0.50},                              # below the 0.80 floor
    {"bbox_center_px": [700.0, 240.0]},                      # centre outside [4,635]x[4,475]
])
def test_live_continuity_rejects_each_named_violation(case):
    module = _phase_camera()
    frames = [_live_frame(monotonic_s=0.0), _live_frame(**case)]
    verdict = module.evaluate_live_continuity(frames, "calibration_live", _matrix())
    assert verdict["verdict"] != "PASS", case


def test_projection_rejects_near_plane_far_and_zero_denominator():
    module = _phase_camera()
    with pytest.raises(ValueError, match="PROJECTION_NEAR_PLANE"):
        module.rasterize_cup_projection(cup_camera_xyz=[0.0, 0.0, 1e-9], width=640, height=480,
                                        fx=400.0, fy=400.0, cx=320.0, cy=240.0, margin_m=1e-6)
    with pytest.raises(ValueError, match="PROJECTION_FAR_OR_BEHIND"):
        module.rasterize_cup_projection(cup_camera_xyz=[0.0, 0.0, -1.0], width=640, height=480,
                                        fx=400.0, fy=400.0, cx=320.0, cy=240.0, margin_m=1e-6)
    with pytest.raises(ValueError, match="PROJECTION_DEGENERATE"):
        module.rasterize_cup_projection(cup_camera_xyz=[0.0, 0.0, 1.0], width=640, height=480,
                                        fx=0.0, fy=400.0, cx=320.0, cy=240.0, margin_m=1e-6)


def test_projection_accepts_the_exact_margin_and_fills_from_the_top_left():
    module = _phase_camera()
    accepted = module.rasterize_cup_projection(cup_camera_xyz=[0.0, 0.0, 1e-6], width=640, height=480,
                                               fx=400.0, fy=400.0, cx=320.0, cy=240.0, margin_m=1e-6)
    assert accepted["u_px"] == pytest.approx(320.0) and accepted["v_px"] == pytest.approx(240.0)
    corner = module.rasterize_cup_projection(cup_camera_xyz=[-0.8, -0.6, 1.0], width=640, height=480,
                                             fx=400.0, fy=400.0, cx=320.0, cy=240.0, margin_m=1e-6)
    assert corner["u_px"] == pytest.approx(0.0) and corner["v_px"] == pytest.approx(0.0)


@pytest.mark.parametrize("owner", list(ALLOWED_OCCLUDERS))
def test_the_five_allowed_visual_occluders_are_permitted(owner):
    module = _phase_camera()
    assert module.occluder_owner_allowed(owner, group=0) is True


@pytest.mark.parametrize("owner", ["table_visual", "collision_geom", "background", "unknown_thing"])
def test_other_or_unknown_owners_are_rejected(owner):
    module = _phase_camera()
    assert module.occluder_owner_allowed(owner, group=0) is False


def test_the_aggregator_hook_keeps_replay_and_live_results_separate():
    from so101_demo.act.task8_calibration_aggregator import derived_phase_camera_checks

    replay_rows = [{"phase": phase, "camera": camera, "monotonic_s": 0.0, "visible_fraction": 0.9,
                    "out_of_frame_fraction": 0.0, "bbox_center_px": [320.0, 240.0]}
                   for phase in PHASES for camera in CAMERAS]
    live_frames = [_live_frame(monotonic_s=0.0), _live_frame(monotonic_s=0.1)]
    folded = derived_phase_camera_checks(replay_rows, live_frames, "calibration_live", _matrix())
    assert folded["replay_coverage"]["verdict"] == "PASS"
    assert folded["live_continuity"]["verdict"] == "PASS"

    stitched = derived_phase_camera_checks(replay_rows, replay_rows, "calibration_live", _matrix())
    assert stitched["replay_coverage"]["verdict"] == "PASS"          # geometric feasibility still holds
    assert stitched["live_continuity"]["verdict"] == "INVALID"       # but never live-continuity success
