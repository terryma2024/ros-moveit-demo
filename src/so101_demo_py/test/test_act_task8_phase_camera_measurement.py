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
            "camera": {"frame_id": "head_camera_frame", "width_px": 640, "height_px": 480, "horizontal_fov_rad": 1.0,
                       "position_m": [0.0, 0.0, 0.5], "rpy_rad": [0.0, 0.0, 0.0]}}


def _trajectory(offset_m=0.0):
    """A real per-phase joint path at the admitted period: `PHASE_DURATION_S` of samples, in metres of travel."""

    count = int(round(PHASE_DURATION_S / PERIOD_S)) + 1
    return {"samples": [{"t_s": index * PERIOD_S,
                         "joints_rad": [0.0, 0.0, 0.0, 0.0, offset_m, 0.0]} for index in range(count)]}


def _target():
    return {"class_id": "plastic_cup", "position_m": [0.10, 0.10, 0.02], "radius_m": 0.03}


def _occluder_geometry(document=None):
    """Geometry for EVERY occluder the matrix admits - the fail-closed contract P1-3 (rereview 5) requires.

    The evaluator used to skip an admitted occluder whose geometry was absent, so a measurement could quietly ignore a
    named occluder. It now refuses by name, which means a fixture must supply what the matrix names.
    """

    names = (document or _matrix_document())["occluders"]
    return {name: {"position_m": [0.02, 0.0, 0.10], "radius_m": 0.005} for name in names}


def _evaluator(document, *, trajectory=None, target=None, occluder_geometry=None):
    """The evaluator, given the geometry a measurement actually has."""

    return PhaseCameraMatrixEvaluator(
        document, trajectory=trajectory or _trajectory(), target=target or _target(),
        occluder_geometry=_occluder_geometry(document) if occluder_geometry is None else occluder_geometry)


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


# ----------------------------------------------------------------------------------------------------------------------
# P1-3 (rereview 5): the four things the verdict requires that this file did not yet assert, each in its own words.
# ----------------------------------------------------------------------------------------------------------------------

def test_the_shipped_matrix_is_frozen_and_a_scaffold_is_refused():
    """*"`config/act/task8-phase-camera-matrix-v1.json` still has `phases: []` and `SCAFFOLD_PENDING…`."*

    Two sides, because the finding has two: the SHIPPED matrix must now be a frozen, sampled document, and a scaffold
    handed to the loader must be refused by name rather than loaded and used to substitute defaults.
    """

    import json

    from so101_demo.act.task8_measurement_schema import load_phase_camera_matrix

    shipped = load_phase_camera_matrix()
    assert shipped["status"] == "FROZEN", "the scaffold status is what this fixes"
    assert shipped["phases"], "and an empty phase list cannot bind a measurement"
    assert shipped["camera"]["width_px"] and shipped["camera"]["horizontal_fov_rad"] > 0.0

    scaffold = {"schema_version": 1, "kind": "task8_phase_camera_matrix",
                "occluders": list(shipped["occluders"]), "phases": [],
                "cameras": ["head_camera", "wrist_camera"], "status": "SCAFFOLD_PENDING_DESIGN_TRANSCRIPTION"}
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "scaffold.json"
        path.write_text(json.dumps(scaffold))
        with pytest.raises(ValueError) as error:
            load_phase_camera_matrix(path)
        assert "PHASE_CAMERA" in str(error.value).upper(), str(error.value)


def test_a_camera_without_intrinsics_is_refused_rather_than_defaulted():
    """*"Production reads a missing singular `camera` entry and substitutes defaults."*

    `width_px`/`height_px`/`horizontal_fov_rad` are what the projection is made of; inventing them (640/480/1.0 rad)
    makes `in_frame` a statement about the defaults.
    """

    document = _matrix_document()
    for name in ("width_px", "height_px", "horizontal_fov_rad"):
        document["camera"].pop(name, None)
    with pytest.raises(ValueError) as error:
        _evaluator(document)("CLOSE", 0)
    assert "CAMERA" in str(error.value).upper(), str(error.value)


def test_a_target_projected_outside_the_image_is_not_in_frame():
    """*"marks every positive-depth projection `in_frame=True` without image-bound checks"*.

    Put the cup far off to the side: the pinhole still projects it (positive depth), and the honest answer is that it
    is outside the image - `u` beyond the width - not that it is visible.
    """

    document = _matrix_document()
    far = _target()
    far["position_m"] = [12.0, 0.0, 0.02]          # ~1 m off-axis with a 0.5 m standoff: far outside a 640 px image
    observation = _evaluator(document, target=far)("CLOSE", 0)
    samples = observation.get("samples") or []
    assert samples, "the phase path was sampled"
    assert all(sample.get("in_frame") is False for sample in samples), (
        "a projection outside the image is not in frame: "
        f"{[sample.get('bbox_px') for sample in samples][:3]}")


def test_an_occluder_without_geometry_fails_closed():
    """*"silently skips absent occluder geometry"*.

    The admitted matrix names five occluders; without their geometry the visibility decision cannot be made, and the
    evaluator must say so by name instead of returning a measurement that quietly ignored them.
    """

    document = _matrix_document()
    with pytest.raises(ValueError) as error:
        PhaseCameraMatrixEvaluator(document, trajectory=_trajectory(), target=_target(),
                                   occluder_geometry={})("CLOSE", 0)
    assert "OCCLUDER" in str(error.value).upper(), str(error.value)
