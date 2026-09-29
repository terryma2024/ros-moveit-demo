"""P1-1 (rereview 5), first half: the occluder geometry must come from the MODEL, not from a stand-in's invention.

The seam hands the evaluator the same made-up geometry for every occluder
(`{"position_m": [0.02, 0.0, 0.10], "radius_m": 0.005}`), while the ACT scene's own geoms are elsewhere entirely. A
visibility decision made against the seam's numbers is a decision about a scene that does not exist - so this file
asserts the model's own values, and asserts that they are NOT the seam's.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # noqa: E402

from so101_demo.act.task8_bottom_io import BottomIOError, occluder_geometry_from_model  # noqa: E402
from so101_demo.act.task8_measurement_schema import EXPECTED_OCCLUDERS  # noqa: E402

#: the seam's invented values, quoted from `test_act_task8_formal_measurement_entry.py`
SEAM_POSITION = [0.02, 0.0, 0.10]
SEAM_RADIUS = 0.005


def _scene() -> Path:
    from ament_index_python.packages import get_package_share_directory

    return Path(get_package_share_directory("so101_demo_py")) / "assets/mujoco/act/scene.xml"


def test_every_admitted_occluder_gets_its_own_pose_from_the_model():
    import mujoco

    model = mujoco.MjModel.from_xml_path(str(_scene()))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)

    geometry = occluder_geometry_from_model(_scene())
    assert set(geometry) == set(EXPECTED_OCCLUDERS), "every admitted occluder is answered"
    for name in EXPECTED_OCCLUDERS:
        geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, name)
        assert geom_id >= 0, name
        reported = geometry[name]["position_m"]
        expected = [float(value) for value in data.geom_xpos[geom_id]]
        assert reported == pytest.approx(expected, abs=1e-12), f"{name} is where the model puts it"
        assert geometry[name]["radius_m"] == pytest.approx(max(float(v) for v in model.geom_size[geom_id])), name


def test_the_geometry_is_not_the_seams_invented_value():
    """The contrast that makes this a fix rather than a rename."""

    geometry = occluder_geometry_from_model(_scene())
    for name, record in geometry.items():
        assert record["position_m"] != pytest.approx(SEAM_POSITION, abs=1e-6) or \
            record["radius_m"] != pytest.approx(SEAM_RADIUS, abs=1e-9), (
            f"{name} coincidentally matches the seam's invented geometry - check the seam's values before claiming "
            "this distinction")
    # and at least one differs in position, which is the case the visibility decision turns on
    assert any(record["position_m"] != pytest.approx(SEAM_POSITION, abs=1e-3)
               for record in geometry.values())


def test_posing_the_arm_first_moves_the_mounted_occluders():
    """These geoms are mounted on the gripper, so their world poses must follow the joints."""

    at_rest = occluder_geometry_from_model(_scene())
    posed = occluder_geometry_from_model(_scene(), joints_rad=[0.3, -0.2, 0.1, 0.0, 0.4, 0.0, 0.25])
    moved = [name for name in EXPECTED_OCCLUDERS
             if at_rest[name]["position_m"] != pytest.approx(posed[name]["position_m"], abs=1e-9)]
    assert moved, "at least one admitted occluder moves when the arm does - they are gripper-mounted"


def test_a_missing_occluder_geom_is_refused_by_name():
    with pytest.raises(BottomIOError) as error:
        occluder_geometry_from_model(_scene(), names=("no_such_occluder_geom",))
    assert "OCCLUDER_GEOM_MISSING" in str(error.value)


def test_a_missing_scene_is_refused_by_name(tmp_path):
    with pytest.raises(BottomIOError) as error:
        occluder_geometry_from_model(tmp_path / "absent.xml")
    assert "SCENE_MISSING" in str(error.value)


# ----------------------------------------------------------------------------------------------------------------------
# the frame source: the model's own camera, rendered headless (CP-1798 proved this host can)
# ----------------------------------------------------------------------------------------------------------------------

def test_the_frame_source_renders_the_named_camera_at_the_admitted_size():
    import numpy as np

    from so101_demo.act.task8_bottom_io import ModelFrameSource

    with ModelFrameSource(_scene()) as source:
        frame = source({"anchor": "default"})
        assert isinstance(frame, np.ndarray) and frame.shape == (480, 640, 3)
        assert frame.dtype == np.uint8
        assert float(frame.std()) > 1.0, "a blank buffer is not a frame the model rendered"
        # and a DIFFERENT camera gives a different image, which is what proves the name was honoured
        wrist = source({"camera": "wrist_camera"})
        assert wrist.shape == frame.shape
        assert not np.array_equal(wrist, frame), "head and wrist cameras cannot see the same thing"


def test_an_unknown_camera_is_refused_by_name():
    from so101_demo.act.task8_bottom_io import ModelFrameSource

    with pytest.raises(BottomIOError) as error:
        ModelFrameSource(_scene(), camera="no_such_camera")
    assert "FRAME_CAMERA_MISSING" in str(error.value)

    with ModelFrameSource(_scene()) as source:
        with pytest.raises(BottomIOError) as error:
            source({"camera": "no_such_camera"})
        assert "FRAME_CAMERA_MISSING" in str(error.value)


def test_posing_the_arm_changes_what_the_wrist_camera_sees():
    import numpy as np

    from so101_demo.act.task8_bottom_io import ModelFrameSource

    with ModelFrameSource(_scene(), camera="wrist_camera") as source:
        at_rest = source({}).copy()
        source.pose([0.4, -0.3, 0.2, 0.0, 0.5, 0.0, 0.3])
        posed = source({})
        assert not np.array_equal(at_rest, posed), "a gripper-mounted camera must follow the joints"
