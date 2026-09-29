"""P1-3 (rereview4): the phase camera must MEASURE, not echo configuration.

The verdict's finding, verified in CP-1674: `PhaseCameraMatrixEvaluator.__call__(phase, index)` returns
`{phase, frame_index, row_count, occluders, camera{...}, matrix_sha256}` - all of it read from the admitted document,
with `phase` and `index` echoed as labels. **No trajectory, target bbox, projection or visibility input exists**, so the
observation is a function of the CONFIGURATION alone: change the cup, the camera pose or an occluder, and it cannot
change. The driver then calls it ONCE PER PHASE while labelling the row `period_s=0.002`, so the approved design's
*"three anchors, complete phase path, 2 ms projected sampling"* is a claim about one sample per phase.

What this file requires:
  1. the observation is a function of GEOMETRY - move the target, the camera or an occluder and it must change;
  2. the phase path is SAMPLED at the admitted period, with per-sample inputs AND results retained, so a reader can
     re-derive the projection rather than trust a summary.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from so101_demo.act.task8_production_composition import PhaseCameraMatrixEvaluator  # noqa: E402

PERIOD_S = 0.002
PHASE_DURATION_S = 0.02                      # ten samples at the admitted period


def _matrix_document():
    """The admitted phase-camera matrix's shape, as the evaluator reads it today."""

    return {"schema_version": 1, "kind": "task8_phase_camera_matrix", "matrix_sha256": "a" * 64,
            "occluders": ["fixed_fingertip_00", "jaw_visual_00"],
            "camera": {"frame_id": "head_camera_frame", "width_px": 640, "height_px": 480,
                       "position_m": [0.0, 0.0, 0.5], "rpy_rad": [0.0, 0.0, 0.0]}}


def _trajectory(offset_m=0.0):
    """A real per-phase joint path at the admitted period: `PHASE_DURATION_S` of samples, in metres of travel."""

    count = int(round(PHASE_DURATION_S / PERIOD_S)) + 1
    return {"samples": [{"t_s": index * PERIOD_S,
                         "joints_rad": [0.0, 0.0, 0.0, 0.0, offset_m, 0.0]} for index in range(count)]}


def _target():
    return {"class_id": "plastic_cup", "position_m": [0.10, 0.10, 0.02], "radius_m": 0.03}


def _evaluator(document, *, trajectory=None, target=None):
    """The evaluator, given the geometry a measurement actually has."""

    return PhaseCameraMatrixEvaluator(document, trajectory=trajectory or _trajectory(), target=target or _target())


def test_moving_the_target_changes_the_observation():
    document = _matrix_document()
    base = _evaluator(document)("CLOSE", 0)
    moved_target = _target()
    moved_target["position_m"] = [0.20, 0.10, 0.02]
    moved = _evaluator(document, target=moved_target)("CLOSE", 0)
    assert moved != base, "the observation must depend on where the cup IS, not only on the admitted matrix"


def test_moving_the_camera_changes_the_observation():
    document = _matrix_document()
    base = _evaluator(document)("CLOSE", 0)
    moved_document = copy.deepcopy(document)
    moved_document["camera"]["position_m"] = [0.05, 0.0, 0.5]
    moved = _evaluator(moved_document)("CLOSE", 0)
    assert moved != base, "the observation must depend on the camera's own geometry"


def test_moving_an_occluder_changes_the_observation():
    document = _matrix_document()
    base = _evaluator(document)("CLOSE", 0)
    occluded = copy.deepcopy(document)
    occluded["occluders"] = ["fixed_fingertip_00", "jaw_visual_00", "gripper_visual_00"]
    moved = _evaluator(occluded)("CLOSE", 0)
    assert moved != base, "the observation must be a function of the occluder GEOMETRY, not of a row count"


def test_the_phase_path_is_sampled_at_the_admitted_period_with_inputs_and_results():
    """2 ms sampling means samples, not a label: the count follows the path's duration."""

    observation = _evaluator(_matrix_document())("CLOSE", 0)
    assert observation["period_s"] == pytest.approx(PERIOD_S), observation.get("period_s")
    samples = observation["samples"]
    assert len(samples) == int(round(PHASE_DURATION_S / PERIOD_S)) + 1, len(samples)
    first = samples[0]
    assert "joints_rad" in first, "each sample retains the INPUT it was projected from"
    assert "bbox_px" in first and "in_frame" in first, "each sample retains its RESULT"
    assert samples[1]["t_s"] - samples[0]["t_s"] == pytest.approx(PERIOD_S)


def test_the_formal_entrys_replay_rows_carry_a_measured_observation(tmp_path, monkeypatch):
    """P1-3's wiring half: a sealed batch's phase rows must say MEASURED, not ABSENT.

    The evaluator measures (CP-1675), but the driver still calls it with `(phase, index)` alone, so a production
    replay writes `geometry_state: "ABSENT"` with an empty sample list. **The design's "2 ms projected sampling" is a
    property of the SEALED EVIDENCE**, so this reads the batch the formal entry seals rather than the evaluator in
    isolation - and it is the requirement the marker was introduced to make visible.
    """

    import json as _json

    from test_act_task8_formal_measurement_entry import _formal_run

    measure, argv = _formal_run(tmp_path, monkeypatch)
    assert measure.main(argv) == 0, "the formal entry must seal before its evidence can be judged"
    batch = tmp_path / "batch"
    phase_rows = sorted(batch.rglob("phase-*.json"))
    assert phase_rows, "the private replay writes one row per phase"
    for row in phase_rows:
        record = _json.loads(row.read_bytes())
        observation = record["observation"]
        assert observation.get("geometry_state") == "MEASURED", (
            f"{row.name} carries {observation.get('geometry_state')!r}: the replay must measure the phase path, and "
            "the driver must hand the evaluator the run's trajectory, camera and target")
        assert observation["samples"], f"{row.name} must retain its per-sample inputs and results"
        assert len(observation["samples"]) > 1, "2 ms sampling over a phase is more than one sample"
