"""P1-1 (rereview 5), first half: the occluder geometry must come from the MODEL, not from a stand-in's invention.

The seam hands the evaluator the same made-up geometry for every occluder
(`{"position_m": [0.02, 0.0, 0.10], "radius_m": 0.005}`), while the ACT scene's own geoms are elsewhere entirely. A
visibility decision made against the seam's numbers is a decision about a scene that does not exist - so this file
asserts the model's own values, and asserts that they are NOT the seam's.
"""

from __future__ import annotations

from pathlib import Path

import pytest


from so101_demo.act.pick_place_calibration_bottom_io import BottomIOError, occluder_geometry_from_model  # noqa: E402
from so101_demo.act.pick_place_calibration_measurement_schema import EXPECTED_OCCLUDERS  # noqa: E402
from paths import PACKAGE_ROOT

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

    from so101_demo.act.pick_place_calibration_bottom_io import ModelFrameSource
    from so101_demo.core.detection import DetectionFrame

    with ModelFrameSource(_scene()) as source:
        frame = source({"anchor": "default"})
        assert isinstance(frame, DetectionFrame)
        assert frame.source_frame_id == "head_camera" and frame.source_stamp_ns > 0
        assert isinstance(frame.rgb8, np.ndarray) and frame.rgb8.shape == (480, 640, 3)
        assert frame.rgb8.dtype == np.uint8
        assert float(frame.rgb8.std()) > 1.0, "a blank buffer is not a frame the model rendered"
        # and a DIFFERENT camera gives a different image, which is what proves the name was honoured
        wrist = source({"camera": "wrist_camera"})
        assert wrist.source_frame_id == "wrist_camera"
        assert wrist.source_stamp_ns > frame.source_stamp_ns
        assert wrist.rgb8.shape == frame.rgb8.shape
        assert not np.array_equal(wrist.rgb8, frame.rgb8), "head and wrist cameras cannot see the same thing"


def test_an_unknown_camera_is_refused_by_name():
    from so101_demo.act.pick_place_calibration_bottom_io import ModelFrameSource

    with pytest.raises(BottomIOError) as error:
        ModelFrameSource(_scene(), camera="no_such_camera")
    assert "FRAME_CAMERA_MISSING" in str(error.value)

    with ModelFrameSource(_scene()) as source:
        with pytest.raises(BottomIOError) as error:
            source({"camera": "no_such_camera"})
        assert "FRAME_CAMERA_MISSING" in str(error.value)


def test_posing_the_arm_changes_what_the_wrist_camera_sees():
    import numpy as np

    from so101_demo.act.pick_place_calibration_bottom_io import ModelFrameSource

    with ModelFrameSource(_scene(), camera="wrist_camera") as source:
        at_rest = source({}).rgb8.copy()
        source.pose([0.4, -0.3, 0.2, 0.0, 0.5, 0.0, 0.3])
        posed = source({})
        assert not np.array_equal(at_rest, posed.rgb8), "a gripper-mounted camera must follow the joints"


# ----------------------------------------------------------------------------------------------------------------------
# the target: the cup's own pose and size, from the model (it is a FREE body, so its pose is a property of the run)
# ----------------------------------------------------------------------------------------------------------------------

def test_the_target_is_the_cups_own_pose_and_size():
    import mujoco

    from so101_demo.act.pick_place_calibration_bottom_io import target_from_model

    model = mujoco.MjModel.from_xml_path(str(_scene()))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "plastic_cup")

    target = target_from_model(_scene())
    assert target["class_id"] == "plastic_cup", "the whitelisted class the detector queries with"
    assert target["position_m"] == pytest.approx([float(v) for v in data.xpos[body_id]], abs=1e-12)
    extents = [float(v) for i in range(model.ngeom) if model.geom_bodyid[i] == body_id
               for v in model.geom_size[i]]
    assert extents, "the cup body has geoms in this scene"
    assert target["radius_m"] == pytest.approx(max(extents))
    # and it is NOT the seam's invented constant
    assert target["position_m"] != pytest.approx([0.10, 0.10, 0.02], abs=1e-3)
    assert target["radius_m"] != pytest.approx(0.03, abs=1e-6)


def test_moving_the_free_cup_moves_the_target():
    """A free body's pose is the run's, so the target must follow it - not be a constant."""

    from so101_demo.act.pick_place_calibration_bottom_io import target_from_model

    at_rest = target_from_model(_scene())
    displaced = target_from_model(_scene(), joints_rad=[0.0] * 7 + [0.05, 0.0, 0.0])
    assert displaced["position_m"] != pytest.approx(at_rest["position_m"], abs=1e-9), (
        "the free joint's qpos must move the target; the scene's free joints follow the arm's seven")


def test_a_missing_target_body_is_refused_by_name():
    from so101_demo.act.pick_place_calibration_bottom_io import target_from_model

    with pytest.raises(BottomIOError) as error:
        target_from_model(_scene(), body="no_such_cup_body")
    assert "TARGET_BODY_MISSING" in str(error.value)


# ----------------------------------------------------------------------------------------------------------------------
# the head camera: the production camera must see the target-support geometry, and that fact is sealed before any
# dataset image is rendered. The seal is computed from the model, but every rule below is decided in pure code, so
# these tests inject the scene and never need MuJoCo or a GL context.
# ----------------------------------------------------------------------------------------------------------------------

import math  # noqa: E402

from so101_demo.act.head_camera_geometry import (  # noqa: E402
    HeadCameraAnchor,
    HeadCameraGeometryContract,
    horizontal_fov_rad,
    validate_head_camera_geometry,
)

PACKAGE = PACKAGE_ROOT
GEOMETRY_CONTRACT_PATH = PACKAGE / "config/act/head-camera-geometry-contract.json"
FAKE_SCENE_PATH = PACKAGE / "assets/mujoco/act/scene.xml"


def _camera_document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "camera_name": "head_camera",
        "width": 640,
        "height": 480,
        "fovy_rad": math.radians(60.0),
        "distortion_model": "plumb_bob",
        "distortion": [0.0, 0.0, 0.0, 0.0, 0.0],
        "parent_body": "head_mount",
        "local_position_m": [0.0, 0.0, 0.0],
        "local_xyaxes": [-1.0, 0.0, 0.0, 0.0, -0.6, 0.8],
    }
    document.update(overrides)
    return document


def _geometry_contract(**overrides: object) -> HeadCameraGeometryContract:
    document: dict[str, object] = {
        "camera": _camera_document(),
        "neck_joint": "neck_yaw_joint",
        "anchors": [
            {"name": "default", "cup_start_m": [0.08, -0.34, -0.265], "neck_start_rad": 0.1},
            {"name": "left", "cup_start_m": [-0.02, -0.34, -0.265], "neck_start_rad": 0.0},
            {"name": "forward", "cup_start_m": [0.08, -0.42, -0.265], "neck_start_rad": 0.0},
        ],
        "workspace_x_m": [-0.15, 0.10],
        "workspace_y_m": [-0.34, -0.26],
        "workspace_z_m": [-0.28, -0.24],
        "workspace_step_m": 0.05,
        "neck_grid_rad": [-1.0, 1.0, 0.02],
        "validation_arm_rad": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "coarse_step_candidate_rad": 0.2,
        "safe_interval_margin_rad": 1e-5,
        "safe_bisection_tolerance_rad": 1e-5,
        "fov_tolerance_rad": 1e-6,
        "visible_pixel_minimum": 64,
        "accepted_scene_sha256": "a" * 64,
        "accepted_camera_source_sha256": "b" * 64,
    }
    document.update(overrides)
    return HeadCameraGeometryContract.from_document(document)


#: the production camera's own axes: x = -x_world, y = (0, -0.6, 0.8), looking along -z
_FAKE_CAMERA_AXES = ((-1.0, 0.0, 0.0), (0.0, -0.6, 0.8), (0.0, 0.8, 0.6))


def scene_support_height() -> float:
    """The support height the fake scene stands its workspace on."""

    return -0.305


class _FakeHeadCameraScene:
    """The production scene reduced to the facts the validator decides on."""

    def __init__(
        self,
        *,
        fovy_rad: float = math.radians(60.0),
        safe_radius_rad: float = 1.0,
        target_offset_m: tuple[float, float, float] = (0.0, 0.0, 0.0),
        visible_pixels: int = 1000,
        workspace_failures: set[tuple[float, float]] | None = None,
        embedded: set[tuple[float, float]] | None = None,
        xyaxes: tuple[float, ...] = (-1.0, 0.0, 0.0, 0.0, -0.6, 0.8),
    ) -> None:
        self._camera_document = _camera_document(fovy_rad=fovy_rad, local_xyaxes=list(xyaxes))
        self._safe_radius_rad = float(safe_radius_rad)
        self._target_offset_m = tuple(float(value) for value in target_offset_m)
        self._visible_pixels = int(visible_pixels)
        self._workspace_failures = set(workspace_failures or ())
        self._embedded = set(embedded or ())

    def support_height_m(self) -> float:
        return scene_support_height()

    def target_rest_offset_m(self) -> float:
        return 0.045

    def target_clear_of_support(self, point_m) -> bool:
        return (round(float(point_m[0]), 6), round(float(point_m[1]), 6)) not in self._embedded

    def occluder_points_m(self):
        return ()

    def workspace_point_fails(self, point_m) -> bool:
        return (
            round(float(point_m[0]), 6),
            round(float(point_m[1]), 6),
        ) in self._workspace_failures

    def visible_pixels_for_point(self, point_m, neck_rad: float) -> int:
        if self.workspace_point_fails(point_m):
            return 0
        return self._visible_pixels

    def endpoint_visibility(self, point_m, neck_rad: float):
        if self.workspace_point_fails(point_m):
            return {"first_hit_body": "table", "visible_to_camera": False, "robot_occluded": False}
        return {
            "first_hit_body": "plastic_cup",
            "visible_to_camera": True,
            "robot_occluded": False,
        }

    def workspace_point_out_of_frame(self, point_m) -> bool:
        return self.workspace_point_fails(point_m)

    def camera_document(self):
        return dict(self._camera_document)

    def camera_mount_pose(self):
        return (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)

    def camera_world_pose(self, neck_rad: float):
        cosine, sine = math.cos(neck_rad), math.sin(neck_rad)
        rotation = (
            (cosine, -sine, 0.0),
            (sine, cosine, 0.0),
            (0.0, 0.0, 1.0),
        )
        # R(neck) = Rz(neck) * R0, exactly as the neck joint rotates the mounted production camera
        return (0.0, 0.0, 0.0), tuple(
            tuple(
                sum(rotation[row][index] * _FAKE_CAMERA_AXES[index][column] for index in range(3))
                for column in range(3)
            )
            for row in range(3)
        )

    def target_points_m(self, anchor: HeadCameraAnchor):
        return (
            tuple(
                point + offset for point, offset in zip(anchor.cup_start_m, self._target_offset_m)
            ),
        )

    def neck_angle_for_point(self, point_m):
        return math.atan2(float(point_m[0]), -float(point_m[1]))

    def safe_at_neck(self, neck_rad: float) -> bool:
        return abs(float(neck_rad)) <= self._safe_radius_rad

    def visible_pixels(self, anchor: HeadCameraAnchor, neck_rad: float) -> int:
        return self._visible_pixels

    def source_digests(self):
        return {"scene_sha256": "a" * 64, "camera_source_sha256": "b" * 64}


def test_horizontal_fov_matches_the_mujoco_camera_convention():
    assert horizontal_fov_rad(fovy_rad=math.radians(60.0), width=640, height=480) == pytest.approx(
        1.3120, abs=1e-3
    )
    assert horizontal_fov_rad(fovy_rad=math.radians(90.0), width=640, height=480) > math.radians(
        90.0
    )


def test_production_head_camera_covers_geometry_matrix_at_all_anchors():
    result = validate_head_camera_geometry(
        FAKE_SCENE_PATH, _geometry_contract(), scene_port=_FakeHeadCameraScene()
    )

    assert result.in_frame_failures == ()
    assert tuple(result.anchors) == ("default", "left", "forward")
    assert result.camera_name == "head_camera"
    assert result.safe_interval_contains_required_domain is True
    assert result.fov_union_covers_required_domain is True
    assert result.horizontal_fov_rad == pytest.approx(1.3120, abs=1e-3)
    assert -1.0 < result.lock_valid_neck_rad[0] < result.lock_valid_neck_rad[1] < 1.0
    assert result.required_search_domain_rad[0] == pytest.approx(-0.5233, abs=0.01)
    assert result.required_search_domain_rad[1] == pytest.approx(0.3672, abs=0.01)

    seal = result.to_document()
    assert seal["schema_version"] == 1
    assert seal["camera_name"] == "head_camera"
    assert seal["image_width"] == 640 and seal["image_height"] == 480
    assert tuple(seal["in_frame_matrix"]) == ("default", "left", "forward")
    assert all(record["out_of_frame_rad"] == [] for record in seal["in_frame_matrix"].values()), (
        "every anchor's target stays inside the frame at its own start and centring angles"
    )
    assert seal["source_digests"]["camera_source_sha256"] == "b" * 64
    assert result.sha256 == seal["seal_sha256"] and len(result.sha256) == 64
    matrix = seal["in_frame_matrix"]["default"]
    assert matrix["neck_start_rad"] == pytest.approx(0.1)
    assert all(sample["in_frame"] for sample in matrix["samples"])
    assert all(sample["visible_pixels"] == 1000 for sample in matrix["samples"])


def test_geometry_seal_refuses_a_target_outside_the_head_camera_frame():
    scene = _FakeHeadCameraScene(target_offset_m=(5.0, 0.0, 0.0))

    with pytest.raises(ValueError, match="HEAD_CAMERA_IN_FRAME_FAILURE"):
        validate_head_camera_geometry(FAKE_SCENE_PATH, _geometry_contract(), scene_port=scene)


def test_geometry_seal_refuses_a_target_the_camera_cannot_see():
    scene = _FakeHeadCameraScene(visible_pixels=10)

    with pytest.raises(ValueError, match="HEAD_CAMERA_IN_FRAME_FAILURE"):
        validate_head_camera_geometry(FAKE_SCENE_PATH, _geometry_contract(), scene_port=scene)


def test_geometry_seal_refuses_a_required_domain_outside_the_safe_interval():
    contract = _geometry_contract(
        anchors=[
            {"name": "default", "cup_start_m": [0.08, -0.34, -0.265], "neck_start_rad": 0.0},
            {"name": "left", "cup_start_m": [-0.02, -0.34, -0.265], "neck_start_rad": 0.0},
            {"name": "forward", "cup_start_m": [0.08, -0.42, -0.265], "neck_start_rad": 0.0},
        ]
    )
    scene = _FakeHeadCameraScene(safe_radius_rad=0.04)

    with pytest.raises(ValueError, match="HEAD_CAMERA_REQUIRED_DOMAIN_UNCOVERED"):
        validate_head_camera_geometry(FAKE_SCENE_PATH, contract, scene_port=scene)


def test_the_coverage_proof_rejects_a_gap_inside_the_required_domain():
    from so101_demo.act.head_camera_geometry import coverage_intervals_cover

    assert coverage_intervals_cover(((-1.0, -0.1), (0.1, 1.0)), (-1.0, 1.0)) is False
    assert coverage_intervals_cover(((-1.0, 0.0), (-0.1, 1.0)), (-1.0, 1.0)) is True
    assert coverage_intervals_cover(((-0.5, 0.0), (0.0, 0.6)), (-1.0, 1.0)) is False


def test_geometry_seal_refuses_a_changed_production_camera_source():
    contract = _geometry_contract(accepted_camera_source_sha256="c" * 64)

    with pytest.raises(ValueError, match="HEAD_CAMERA_SOURCE_DRIFT"):
        validate_head_camera_geometry(FAKE_SCENE_PATH, contract, scene_port=_FakeHeadCameraScene())


def test_geometry_seal_refuses_a_changed_camera_definition():
    scene = _FakeHeadCameraScene(xyaxes=(-1.0, 0.0, 0.0, 0.0, -0.9, 0.44))

    with pytest.raises(ValueError, match="HEAD_CAMERA_DEFINITION_DRIFT"):
        validate_head_camera_geometry(FAKE_SCENE_PATH, _geometry_contract(), scene_port=scene)


def test_the_tracked_geometry_contract_pins_the_production_camera_and_three_anchors():
    contract = HeadCameraGeometryContract.from_path(GEOMETRY_CONTRACT_PATH)

    assert contract.camera_name == "head_camera"
    assert contract.neck_joint == "neck_yaw_joint"
    assert (contract.image_width, contract.image_height) == (640, 480)
    assert tuple(anchor.name for anchor in contract.anchors) == ("default", "left", "forward")
    assert contract.anchors[0].cup_start_m == pytest.approx((0.02, -0.28, 0.165))
    assert contract.anchors[1].cup_start_m == pytest.approx((-0.08, -0.28, 0.165))
    assert contract.anchors[2].cup_start_m == pytest.approx((0.02, -0.36, 0.165))
    assert contract.neck_grid_rad == pytest.approx((-2.0 * math.pi, 2.0 * math.pi, 0.002))
    assert 0.0 < contract.coarse_step_candidate_rad <= contract.horizontal_fov_rad() / 2.0


def test_geometry_seal_closes_the_neck_grid_at_both_declared_endpoints():
    contract = _geometry_contract()
    grid = contract.neck_grid()

    assert grid[0] == pytest.approx(-1.0)
    assert grid[-1] == pytest.approx(1.0)
    assert len(grid) == 101


def test_geometry_seal_refuses_an_oversized_coarse_step():
    contract = _geometry_contract(coarse_step_candidate_rad=10.0)

    with pytest.raises(ValueError, match="HEAD_CAMERA_STEP_EXCEEDS_HALF_FOV"):
        validate_head_camera_geometry(FAKE_SCENE_PATH, contract, scene_port=_FakeHeadCameraScene())


def test_geometry_seal_refuses_a_workspace_that_is_not_on_the_declared_support():
    contract = _geometry_contract(workspace_z_m=[100.0, 101.0])

    with pytest.raises(ValueError, match="HEAD_CAMERA_WORKSPACE_UNSUPPORTED"):
        validate_head_camera_geometry(FAKE_SCENE_PATH, contract, scene_port=_FakeHeadCameraScene())


def test_geometry_seal_evaluates_every_workspace_sample_at_every_declared_height():
    scene = _FakeHeadCameraScene(workspace_failures={(-0.15, -0.26)})

    with pytest.raises(ValueError, match="HEAD_CAMERA_WORKSPACE_MATRIX_INCOMPLETE"):
        validate_head_camera_geometry(FAKE_SCENE_PATH, _geometry_contract(), scene_port=scene)


def test_geometry_seal_freezes_the_camera_definition_it_accepted():
    result = validate_head_camera_geometry(
        FAKE_SCENE_PATH, _geometry_contract(), scene_port=_FakeHeadCameraScene()
    )
    seal = result.to_document()

    assert seal["camera"]["camera_name"] == "head_camera"
    assert seal["camera"]["local_position_m"] == [0.0, 0.0, 0.0]
    assert seal["camera"]["local_xyaxes"] == pytest.approx([-1.0, 0.0, 0.0, 0.0, -0.6, 0.8])
    assert seal["workspace_matrix"]["samples"] == seal["workspace_matrix"]["in_frame"]
    assert seal["workspace_matrix"]["samples"] > 0
    assert seal["workspace_matrix"]["min_anchor_visible_pixels"] == 1000
    assert seal["workspace_matrix"]["min_rendered_visible_pixels"] == 1000
    endpoints = [
        sample
        for sample in seal["workspace_matrix"]["key_samples"]
        if sample["kind"] == "required_domain_endpoint"
    ]
    assert len(endpoints) == 2
    assert all(sample["first_hit_body"] == "plastic_cup" for sample in endpoints)
    assert {sample["kind"] for sample in seal["workspace_matrix"]["key_samples"]} == {
        "anchor",
        "required_domain_endpoint",
    }
    assert seal["support_height_m"] == pytest.approx(scene_support_height())
    assert len(seal["workspace_matrix"]["key_samples"]) >= 3
    assert all(sample["in_frame"] for sample in seal["workspace_matrix"]["key_samples"])
