"""The workspace projection document phase 6 consumes: the legal pick workspace in the head camera.

Every fixture here is synthetic: no ROS, no GPU, no detector, no rendering and no motion. The fixtures
build a small sealed geometry seal and a matching geometry contract whose workspace box is narrow enough
that the bounded plan's in-domain stop set does not depend on which coarse-step candidate phase 2 chose,
and a fake scene reader whose camera pose is the seal's own mount model - so the pose cross-check, the
per-pose extents and the union/intersection are all exercised without loading MuJoCo.

What these tests pin:

* the projected points are the geometry contract's declared workspace samples under the seal's own
  workspace-matrix rule (both edges of every axis, the three declared heights);
* the projected poses are the bounded plan's stop points inside `required_search_domain_rad`, deduplicated
  over the sealed anchors, with an anchor start outside the domain recorded rather than clamped;
* a pose set that would depend on the undeclared choice of coarse-step candidate is refused with
  `CAL_PROJECTION_POSE_SET_AMBIGUOUS` instead of being picked silently;
* the document's `top_px`/`bottom_px` are the union of the per-pose extents over the visited poses, and
  the intersection and the aimed band are recorded beside them;
* a point the camera cannot project, a scene/contract/seal disagreement and a reader whose camera pose
  the sealed mount model cannot produce are refused by name;
* the produced document carries `path` + a self-digest, and the installed phase 6 computes
  `vertical_bounds_px` from it;
* the producer writes exactly the document and the receipt into a brand-new directory and refuses an
  existing one.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable

import pytest
from so101_demo.act.head_camera_geometry.contract import HeadCameraGeometryContract, project_point
from so101_demo.act.head_camera_geometry.validation import camera_pose_from_seal
from so101_demo.act.head_search_calibration_geometry import SELECTION_RULE
from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_search_params import compute_vertical_bounds_px
from so101_demo.act.head_search_workspace_projection.projection import (
    CAL_PROJECTION_EMPTY,
    CAL_PROJECTION_EVIDENCE_CONTRADICTORY,
    CAL_PROJECTION_EVIDENCE_MISSING,
    CAL_PROJECTION_POINT_UNPROJECTABLE,
    CAL_PROJECTION_POSE_SET_AMBIGUOUS,
    CalibrationWorkspaceProjectionRefused,
    DIGEST_CONVENTION,
    KIND,
    PHASE,
    projection_poses,
    REFUSAL_CODES,
    sealed_bearing_rad,
    workspace_sample_points,
)
from so101_demo.act.head_search_workspace_projection.writer import (
    build_head_search_workspace_projection,
    write_head_search_workspace_projection,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

FOVY_RAD = 1.0471975511965976
WIDTH = 640
HEIGHT = 480
MOUNT_ORIGIN = (0.0, 0.0, 0.0)
#: the fixture camera rides the neck axis and looks along -y with world +z up, so a workspace sample's
#: row is `240 - focal * z / |y|` and its column `320 - focal * x / |y|`: both are checkable by hand.
#: `CAMERA_BACKWARDS_XYAXES` is the same camera turned around, which puts the whole workspace behind it.
CAMERA_XYAXES = [-1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
CAMERA_BACKWARDS_XYAXES = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
WORKSPACE_X_M = [-0.005, 0.005]
WORKSPACE_Y_M = [-0.35, -0.33]
WORKSPACE_Z_M = [-0.01, 0.01]
WORKSPACE_STEP_M = 0.005
ANCHORS = [
    {"name": "left", "cup_start_m": [-0.005, -0.34, 0.0], "neck_start_rad": 0.0},
    {"name": "forward", "cup_start_m": [0.0, -0.34, 0.0], "neck_start_rad": 0.012},
]


def _digest(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _scene(tmp_path):
    path = tmp_path / "head_search_scene.xml"
    path.write_text('<mujoco model="fixture"><worldbody/></mujoco>\n', encoding="utf-8")
    return path


def _camera_document(local_xyaxes=None) -> dict:
    return {
        "camera_name": "head_camera",
        "width": WIDTH,
        "height": HEIGHT,
        "fovy_rad": FOVY_RAD,
        "distortion_model": "plumb_bob",
        "distortion": [0.0, 0.0, 0.0, 0.0, 0.0],
        "parent_body": "head_mount",
        "local_position_m": [0.0, 0.0, 0.0],
        "local_xyaxes": list(CAMERA_XYAXES if local_xyaxes is None else local_xyaxes),
    }


def _contract_path(tmp_path, scene_path=None, *, local_xyaxes=None):
    """Write the geometry contract the seal was built from and return its path."""

    scene = scene_path if scene_path is not None else _scene(tmp_path)
    document = {
        "camera": _camera_document(local_xyaxes),
        "neck_joint": "neck_yaw_joint",
        "anchors": [dict(anchor) for anchor in ANCHORS],
        "workspace_x_m": list(WORKSPACE_X_M),
        "workspace_y_m": list(WORKSPACE_Y_M),
        "workspace_z_m": list(WORKSPACE_Z_M),
        "workspace_step_m": WORKSPACE_STEP_M,
        "neck_grid_rad": [-3.141592653589793, 3.141592653589793, 0.002],
        "validation_arm_rad": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "coarse_step_candidate_rad": 0.3,
        "safe_interval_margin_rad": 1e-05,
        "safe_bisection_tolerance_rad": 1e-05,
        "fov_tolerance_rad": 1e-06,
        "visible_pixel_minimum": 64,
        "accepted_scene_sha256": _digest(scene),
        "accepted_camera_source_sha256": _digest(scene),
        "scene_path": None,
    }
    path = tmp_path / "head-camera-geometry-contract.json"
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _seal_path(
    tmp_path, scene_path, contract_path, *, mutate: Callable[[dict], None] | None = None
):
    """Write the sealed geometry the contract was sealed into and return its path."""

    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    samples = workspace_sample_points(HeadCameraGeometryContract.from_path(contract_path))
    bearings = [sealed_bearing_rad(point, mount_origin_m=MOUNT_ORIGIN) for point in samples]
    body = {
        "schema_version": 1,
        "camera_name": contract["camera"]["camera_name"],
        "image_width": WIDTH,
        "image_height": HEIGHT,
        "horizontal_fov_rad": 2.0
        * math.atan((WIDTH / 2.0) / ((HEIGHT / 2.0) / math.tan(FOVY_RAD / 2.0))),
        "camera": contract["camera"],
        "camera_mount_origin_m": list(MOUNT_ORIGIN),
        "camera_mount_xyaxes": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0],
        "anchors": [anchor["name"] for anchor in ANCHORS],
        "in_frame_matrix": {
            anchor["name"]: {
                "neck_start_rad": anchor["neck_start_rad"],
                "centre_angle_rad": anchor["neck_start_rad"],
                "samples": [],
                "out_of_frame_rad": [],
            }
            for anchor in ANCHORS
        },
        "workspace_matrix": {
            "samples": len(samples),
            "in_frame": len(samples),
            "key_samples": [],
            "required_domain_rad": [min(bearings), max(bearings)],
        },
        "coarse_step_candidate_rad": contract["coarse_step_candidate_rad"],
        "required_search_domain_rad": [min(bearings), max(bearings)],
        "lock_valid_neck_rad": [-3.141592653589793, 3.141592653589793],
        "safe_interval_contains_required_domain": True,
        "fov_union_covers_required_domain": True,
        "source_digests": {
            "scene_sha256": _digest(scene_path),
            "camera_source_sha256": contract["accepted_camera_source_sha256"],
            "contract_sha256": canonical_sha256({**contract, "scene_path": None}),
            "coarse_step_candidate_rad": contract["coarse_step_candidate_rad"],
        },
    }
    if mutate is not None:
        mutate(body)
    body["seal_sha256"] = canonical_sha256(body)
    path = tmp_path / "head-camera-geometry.json"
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


class FakeSceneReader:
    """A scene reader whose camera pose is the seal's own mount model, or a deliberately shifted one."""

    def __init__(self, seal, *, position_shift=(0.0, 0.0, 0.0), axes_shift=(0.0,) * 6):
        self.seal = seal
        self.position_shift = tuple(position_shift)
        self.axes_shift = tuple(axes_shift)
        self.poses = []
        self.closed = False

    def camera_world_pose(self, neck_rad):
        position, axes = camera_pose_from_seal(self.seal, float(neck_rad))
        self.poses.append(float(neck_rad))
        return (
            [position[index] + self.position_shift[index] for index in range(3)],
            [axes[index] + self.axes_shift[index] for index in range(6)],
        )

    def close(self) -> None:
        self.closed = True


def _reader(seal_path, **kwargs) -> FakeSceneReader:
    return FakeSceneReader(json.loads(seal_path.read_text(encoding="utf-8")), **kwargs)


def _rotation(axes) -> tuple:
    """`head_camera_geometry.project_point`'s convention: the columns are the camera's world axes."""

    x_axis, y_axis = axes[0:3], axes[3:6]
    z_axis = (
        x_axis[1] * y_axis[2] - x_axis[2] * y_axis[1],
        x_axis[2] * y_axis[0] - x_axis[0] * y_axis[2],
        x_axis[0] * y_axis[1] - x_axis[1] * y_axis[0],
    )
    return (
        (x_axis[0], y_axis[0], z_axis[0]),
        (x_axis[1], y_axis[1], z_axis[1]),
        (x_axis[2], y_axis[2], z_axis[2]),
    )


def _independent_projection(seal, neck_rad, points):
    """Project the fixture's points from first principles, without the producer's own aggregation."""

    position, axes = camera_pose_from_seal(seal, float(neck_rad))
    rotation = _rotation(axes)
    return [
        project_point(
            point_m=point,
            camera_position_m=position,
            camera_rotation=rotation,
            width=WIDTH,
            height=HEIGHT,
            fovy_rad=FOVY_RAD,
        )
        for point in points
    ]


def _pose(poses, angle, tolerance=1e-9):
    """The pose whose angle is `angle`, tolerating the last-bit differences merges absorb."""

    matches = [pose for pose in poses if abs(pose["pose_rad"] - angle) <= tolerance]
    assert matches, f"no projected pose within {tolerance} of {angle}"
    return matches[0]


# --- the projected point set ----------------------------------------------------------------------


def test_workspace_sample_points_are_the_seal_matrix_rule(tmp_path) -> None:
    contract = HeadCameraGeometryContract.from_path(_contract_path(tmp_path))

    points = workspace_sample_points(contract)

    assert len(points) == 3 * 5 * 3
    assert sorted({point[0] for point in points}) == pytest.approx([-0.005, 0.0, 0.005])
    assert sorted({point[1] for point in points}) == pytest.approx(
        [-0.35, -0.345, -0.34, -0.335, -0.33]
    )
    assert sorted({point[2] for point in points}) == pytest.approx([-0.01, 0.0, 0.01])


# --- the projected pose set -----------------------------------------------------------------------


def test_projection_poses_are_the_bounded_stops_inside_the_required_domain(tmp_path) -> None:
    scene = _scene(tmp_path)
    contract_path = _contract_path(tmp_path, scene)
    seal = json.loads(_seal_path(tmp_path, scene, contract_path).read_text(encoding="utf-8"))
    domain = seal["required_search_domain_rad"]

    poses = projection_poses(
        seal=seal,
        required_domain_rad=domain,
        safe_interval_rad=seal["lock_valid_neck_rad"],
        anchors_rad={"left": 0.0, "forward": 0.012},
        horizontal_fov_rad=seal["horizontal_fov_rad"],
        sealed_candidate_rad=seal["coarse_step_candidate_rad"],
    )

    angles = [pose["pose_rad"] for pose in poses["poses"]]
    assert angles == pytest.approx(sorted([domain[0], 0.0, 0.012, domain[1]]), abs=1e-9)
    assert _pose(poses["poses"], 0.0)["kinds"] == ["anchor_start"]
    assert _pose(poses["poses"], 0.012)["kinds"] == ["anchor_start"]
    assert _pose(poses["poses"], domain[0])["kinds"] == ["plan_stop"]
    assert _pose(poses["poses"], domain[1])["kinds"] == ["plan_stop"]
    assert all(pose["visited_by"] for pose in poses["poses"])
    assert poses["excluded_poses"] == []
    assert len(poses["candidate_steps"]) > 1, "phase 2's own candidates are all checked"
    # the step is the one phase 2's selection rule chooses: the largest candidate above the domain width
    assert poses["step_source"] == "phase_2_selection_rule"
    assert poses["chosen_step_rad"] == pytest.approx(seal["horizontal_fov_rad"] / 2.0)
    assert poses["chosen_step_rad"] == pytest.approx(poses["phase_2_choice"]["chosen_candidate_rad"])
    assert poses["phase_2_choice"]["rule"] == SELECTION_RULE
    assert all(record["pose_set_agrees"] for record in poses["candidate_steps"])
    assert poses["poses_are_step_independent"] is True


def test_projection_poses_record_which_candidate_steps_would_project_a_different_pose_set(
    tmp_path,
) -> None:
    scene = _scene(tmp_path)
    contract_path = _contract_path(tmp_path, scene)
    seal = json.loads(_seal_path(tmp_path, scene, contract_path).read_text(encoding="utf-8"))

    poses = projection_poses(
        seal=seal,
        required_domain_rad=[-1.0, 1.0],
        safe_interval_rad=seal["lock_valid_neck_rad"],
        anchors_rad={"left": 0.0},
        horizontal_fov_rad=seal["horizontal_fov_rad"],
        sealed_candidate_rad=seal["coarse_step_candidate_rad"],
    )

    # a required domain wider than the steps lets the smaller candidates add stops inside it, and the
    # plan that is projected is still the one phase 2's rule chooses
    assert poses["poses_are_step_independent"] is False
    assert any(record["pose_set_agrees"] is False for record in poses["candidate_steps"])
    assert poses["step_source"] == "phase_2_selection_rule"
    assert poses["chosen_step_rad"] == max(record["coarse_step_rad"] for record in poses["candidate_steps"])
    assert poses["chosen_step_rad"] == pytest.approx(seal["horizontal_fov_rad"] / 2.0)
    chosen = next(
        record
        for record in poses["candidate_steps"]
        if record["coarse_step_rad"] == poses["chosen_step_rad"]
    )
    assert poses["pose_count"] == len(chosen["in_domain_stops_rad"]) + 1


def test_projection_poses_use_a_declared_step_that_phase_2_could_have_receipted(tmp_path) -> None:
    scene = _scene(tmp_path)
    contract_path = _contract_path(tmp_path, scene)
    seal = json.loads(_seal_path(tmp_path, scene, contract_path).read_text(encoding="utf-8"))
    domain = seal["required_search_domain_rad"]
    common = {
        "seal": seal,
        "required_domain_rad": domain,
        "safe_interval_rad": seal["lock_valid_neck_rad"],
        "anchors_rad": {"left": 0.0, "forward": 0.012},
        "horizontal_fov_rad": seal["horizontal_fov_rad"],
        "sealed_candidate_rad": seal["coarse_step_candidate_rad"],
    }

    by_rule = projection_poses(**common)
    declared = projection_poses(**common, declared_step_rad=0.3)

    assert declared["step_source"] == "declared"
    assert declared["chosen_step_rad"] == pytest.approx(0.3)
    assert declared["chosen_step_rad"] in [
        record["coarse_step_rad"] for record in declared["candidate_steps"]
    ]
    # both steps are wider than this fixture's domain, so the projected poses are the same
    assert [pose["pose_rad"] for pose in declared["poses"]] == pytest.approx(
        [pose["pose_rad"] for pose in by_rule["poses"]]
    )
    assert declared["poses_are_step_independent"] is True


def test_projection_poses_refuse_a_declared_step_phase_2_could_not_have_chosen(tmp_path) -> None:
    scene = _scene(tmp_path)
    contract_path = _contract_path(tmp_path, scene)
    seal = json.loads(_seal_path(tmp_path, scene, contract_path).read_text(encoding="utf-8"))
    domain = seal["required_search_domain_rad"]

    with pytest.raises(CalibrationWorkspaceProjectionRefused) as error:
        projection_poses(
            seal=seal,
            required_domain_rad=domain,
            safe_interval_rad=seal["lock_valid_neck_rad"],
            anchors_rad={"left": 0.0},
            horizontal_fov_rad=seal["horizontal_fov_rad"],
            sealed_candidate_rad=seal["coarse_step_candidate_rad"],
            declared_step_rad=0.25,
        )

    assert error.value.code == CAL_PROJECTION_POSE_SET_AMBIGUOUS
    assert "none of the candidates" in error.value.detail


def test_projection_poses_record_an_anchor_whose_start_is_outside_the_domain(tmp_path) -> None:
    scene = _scene(tmp_path)
    contract_path = _contract_path(tmp_path, scene)
    seal = json.loads(_seal_path(tmp_path, scene, contract_path).read_text(encoding="utf-8"))
    domain = seal["required_search_domain_rad"]
    outside = domain[1] + 0.5

    poses = projection_poses(
        seal=seal,
        required_domain_rad=domain,
        safe_interval_rad=seal["lock_valid_neck_rad"],
        anchors_rad={"left": 0.0, "default": outside},
        horizontal_fov_rad=seal["horizontal_fov_rad"],
        sealed_candidate_rad=seal["coarse_step_candidate_rad"],
    )

    record = next(item for item in poses["excluded_poses"] if item["anchor"] == "default")
    assert record["reason"] == "outside_required_search_domain"
    assert record["neck_rad"] == pytest.approx(outside)
    assert all(abs(pose["pose_rad"] - outside) > 1e-9 for pose in poses["poses"])


# --- the extent -----------------------------------------------------------------------------------


def _document(tmp_path, *, reader=None, extra=None, **overrides):
    scene = _scene(tmp_path)
    contract_path = _contract_path(tmp_path, scene, local_xyaxes=extra)
    seal_path = _seal_path(tmp_path, scene, contract_path)
    return build_head_search_workspace_projection(
        scene_path=scene,
        geometry_seal_path=seal_path,
        geometry_contract_path=contract_path,
        document_path=tmp_path / "workspace-projection.json",
        scene_reader=reader if reader is not None else _reader(seal_path),
        **overrides,
    )


def test_extent_is_the_union_over_the_visited_poses_with_the_intersection_beside_it(tmp_path) -> None:
    document = _document(tmp_path)
    seal = json.loads((tmp_path / "head-camera-geometry.json").read_text(encoding="utf-8"))
    contract = HeadCameraGeometryContract.from_path(
        tmp_path / "head-camera-geometry-contract.json"
    )
    points = workspace_sample_points(contract)

    expected = {}
    for pose in document["poses"]:
        rows = _independent_projection(seal, pose["pose_rad"], points)
        expected[pose["pose_rad"]] = (min(row[1] for row in rows), max(row[1] for row in rows))

    for pose in document["poses"]:
        top, bottom = expected[pose["pose_rad"]]
        assert pose["top_px"] == pytest.approx(top, abs=1e-9)
        assert pose["bottom_px"] == pytest.approx(bottom, abs=1e-9)
        assert pose["projected_points"] == len(points)
        assert pose["in_frame_points"] == len(points)

    tops = [value[0] for value in expected.values()]
    bottoms = [value[1] for value in expected.values()]
    assert document["top_px"] == pytest.approx(min(tops), abs=1e-9)
    assert document["bottom_px"] == pytest.approx(max(bottoms), abs=1e-9)
    assert document["extent"]["union_px"] == pytest.approx([min(tops), max(bottoms)], abs=1e-9)
    assert document["extent"]["intersection_px"] == pytest.approx([max(tops), min(bottoms)], abs=1e-9)
    assert document["extent"]["headline"] == "union_over_visited_poses"
    assert document["top_px"] < document["bottom_px"]
    assert document["unit"] == "px"
    assert document["extent"]["per_pose"][0]["pose_rad"] == document["poses"][0]["pose_rad"]


def test_every_projected_point_carries_the_evidence_of_how_it_was_obtained(tmp_path) -> None:
    document = _document(tmp_path)

    for pose in document["poses"]:
        assert pose["camera_pose"]["source"] == "camera_pose_from_seal"
        assert len(pose["camera_pose"]["rotation"]) == 3
        assert len(pose["camera_pose"]["rotation"][0]) == 3
        assert len(pose["camera_pose"]["position_m"]) == 3
        for record in pose["points"]:
            assert set(record) >= {"point_m", "u", "v", "in_frame", "pose_rad", "projection"}
            assert record["projection"] == "head_camera_geometry.project_point"
            assert record["pose_rad"] == pose["pose_rad"]
            assert len(record["point_m"]) == 3
            assert math.isfinite(record["u"]) and math.isfinite(record["v"])


def test_the_aimed_band_is_recorded_beside_the_pose_extents(tmp_path) -> None:
    document = _document(tmp_path)

    aimed = document["aimed_projection"]
    assert aimed["points"] == document["poses"][0]["projected_points"]
    assert aimed["u_equals_width_over_two"] is True
    assert aimed["band_px"][0] < aimed["band_px"][1]
    assert aimed["covered_by_union"] in (True, False)
    assert aimed["covered_by_intersection"] in (True, False)
    assert len(document["recorded_limitations"]) >= 3
    assert "fine correction" in " ".join(document["recorded_limitations"])


def test_the_document_carries_the_keys_phase_6_reads(tmp_path) -> None:
    document = _document(tmp_path)

    assert document["kind"] == KIND and document["phase"] == PHASE
    assert document["digest_convention"] == DIGEST_CONVENTION
    assert document["path"] == str(tmp_path / "workspace-projection.json")
    assert type(document["top_px"]) is float and type(document["bottom_px"]) is float
    assert document["sha256"] == canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    assert document["refusals"] == []
    assert document["detector_loaded"] is False
    assert document["cuda_used"] is False
    assert document["motion_commanded"] is False
    assert document["mujoco_neck_commanded"] is False
    assert document["hardware_motion_commanded"] is False
    assert document["ros_nodes_started"] is False
    assert document["workspace"]["sample_count"] == len(
        workspace_sample_points(
            HeadCameraGeometryContract.from_path(tmp_path / "head-camera-geometry-contract.json")
        )
    )
    assert document["sealed_evidence"]["scene"]["sha256"] == document["scene_sha256"]
    assert document["sealed_evidence"]["geometry_seal"]["sha256"] == _digest(
        tmp_path / "head-camera-geometry.json"
    )
    assert document["sealed_evidence"]["geometry_contract"]["sha256"] == _digest(
        tmp_path / "head-camera-geometry-contract.json"
    )
    assert document["pose_set"]["chosen_step_rad"] > 0.0
    assert document["pose_set"]["step_source"] == "phase_2_selection_rule"
    assert document["pose_set"]["poses_are_step_independent"] is True


def test_a_document_built_without_a_path_names_none(tmp_path) -> None:
    scene = _scene(tmp_path)
    contract_path = _contract_path(tmp_path, scene)
    seal_path = _seal_path(tmp_path, scene, contract_path)

    document = build_head_search_workspace_projection(
        scene_path=scene,
        geometry_seal_path=seal_path,
        geometry_contract_path=contract_path,
        scene_reader=_reader(seal_path),
    )

    assert document["path"] is None


def test_the_installed_phase_6_computes_vertical_bounds_from_the_document(tmp_path) -> None:
    document = _document(tmp_path)
    camera = {
        "path": str(tmp_path / "camera-measurements.json"),
        "sha256": canonical_sha256({"n": "camera-measurements"}),
        "horizontal_fov_rad": 1.3121067481206794,
        "image_width_px": 640.0,
        "image_height_px": 480.0,
        "centre_jitter_rad": 0.0006,
        "safety_margin_px": 120.0,
    }

    block = compute_vertical_bounds_px(camera=camera, workspace_projection=document)

    assert block["value"] == [
        max(document["top_px"], 120.0),
        min(document["bottom_px"], 360.0),
    ]
    assert block["observed_distribution"]["workspace_projection_px"] == [
        document["top_px"],
        document["bottom_px"],
    ]
    cited = {(reference["path"], reference["sha256"]) for reference in block["input_evidence"]}
    assert (document["path"], document["sha256"]) in cited
    assert block["safety_margin"]["detections_used"] is False


# --- refusals -------------------------------------------------------------------------------------


def test_projection_refuses_a_point_the_camera_cannot_project(tmp_path) -> None:
    scene = _scene(tmp_path)
    # the same contract and seal, with the camera turned around: every workspace sample is behind it
    contract_path = _contract_path(tmp_path, scene, local_xyaxes=CAMERA_BACKWARDS_XYAXES)
    seal_path = _seal_path(tmp_path, scene, contract_path)
    reader = _reader(seal_path)

    with pytest.raises(CalibrationWorkspaceProjectionRefused) as error:
        build_head_search_workspace_projection(
            scene_path=scene,
            geometry_seal_path=seal_path,
            geometry_contract_path=contract_path,
            scene_reader=reader,
        )

    assert error.value.code == CAL_PROJECTION_POINT_UNPROJECTABLE


def test_projection_refuses_a_seal_that_declares_no_scene_digest(tmp_path) -> None:
    scene = _scene(tmp_path)
    contract_path = _contract_path(tmp_path, scene)
    seal_path = _seal_path(
        tmp_path,
        scene,
        contract_path,
        mutate=lambda body: body["source_digests"].pop("scene_sha256"),
    )

    with pytest.raises(CalibrationWorkspaceProjectionRefused) as error:
        build_head_search_workspace_projection(
            scene_path=scene,
            geometry_seal_path=seal_path,
            geometry_contract_path=contract_path,
            scene_reader=_reader(seal_path),
        )

    assert error.value.code == CAL_PROJECTION_EVIDENCE_MISSING


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda body: body["source_digests"].__setitem__("scene_sha256", "0" * 64),
            id="scene-digest",
        ),
        pytest.param(
            lambda body: body["camera"].__setitem__("fovy_rad", 1.2), id="camera-definition"
        ),
        pytest.param(
            lambda body: body["workspace_matrix"].__setitem__("samples", 3),
            id="workspace-sample-count",
        ),
        pytest.param(
            lambda body: body.__setitem__("required_search_domain_rad", [0.0, 0.1]),
            id="required-domain",
        ),
    ],
)
def test_projection_refuses_evidence_that_disagrees(tmp_path, mutate) -> None:
    scene = _scene(tmp_path)
    contract_path = _contract_path(tmp_path, scene)
    seal_path = _seal_path(tmp_path, scene, contract_path, mutate=mutate)

    with pytest.raises(CalibrationWorkspaceProjectionRefused) as error:
        build_head_search_workspace_projection(
            scene_path=scene,
            geometry_seal_path=seal_path,
            geometry_contract_path=contract_path,
            scene_reader=_reader(seal_path),
        )

    assert error.value.code == CAL_PROJECTION_EVIDENCE_CONTRADICTORY


def test_projection_refuses_a_reader_pose_the_sealed_mount_model_cannot_produce(tmp_path) -> None:
    scene = _scene(tmp_path)
    contract_path = _contract_path(tmp_path, scene)
    seal_path = _seal_path(tmp_path, scene, contract_path)

    with pytest.raises(CalibrationWorkspaceProjectionRefused) as error:
        build_head_search_workspace_projection(
            scene_path=scene,
            geometry_seal_path=seal_path,
            geometry_contract_path=contract_path,
            scene_reader=_reader(seal_path, axes_shift=(1e-3, 0.0, 0.0, 0.0, 0.0, 0.0)),
        )

    assert error.value.code == CAL_PROJECTION_EVIDENCE_CONTRADICTORY
    assert "camera pose" in error.value.detail


def test_projection_refuses_a_geometry_seal_its_own_digest_cannot_vouch_for(tmp_path) -> None:
    scene = _scene(tmp_path)
    contract_path = _contract_path(tmp_path, scene)
    seal_path = _seal_path(
        tmp_path, scene, contract_path, mutate=lambda body: body.update(seal_sha256="f" * 64)
    )

    with pytest.raises(CalibrationInputsRefused):
        build_head_search_workspace_projection(
            scene_path=scene,
            geometry_seal_path=seal_path,
            geometry_contract_path=contract_path,
            scene_reader=_reader(seal_path),
        )


def test_every_refusal_code_is_the_measurement_s_own() -> None:
    assert REFUSAL_CODES == (
        CAL_PROJECTION_EVIDENCE_MISSING,
        CAL_PROJECTION_EVIDENCE_CONTRADICTORY,
        CAL_PROJECTION_POSE_SET_AMBIGUOUS,
        CAL_PROJECTION_POINT_UNPROJECTABLE,
        CAL_PROJECTION_EMPTY,
    )


# --- the producer ---------------------------------------------------------------------------------


def test_write_projection_claims_a_brand_new_directory(tmp_path) -> None:
    scene = _scene(tmp_path)
    contract_path = _contract_path(tmp_path, scene)
    seal_path = _seal_path(tmp_path, scene, contract_path)
    output = tmp_path / "workspace-projection-20261002T000000Z"
    reader = _reader(seal_path)

    result = write_head_search_workspace_projection(
        scene_path=scene,
        geometry_seal_path=seal_path,
        geometry_contract_path=contract_path,
        output_dir=output,
        scene_reader=reader,
        command="so101_head_search_calibration measure-workspace-projection",
    )

    document = json.loads((output / "workspace-projection.json").read_text(encoding="utf-8"))
    receipt = json.loads((output / "measurement-receipt.json").read_text(encoding="utf-8"))
    assert sorted(path.name for path in output.iterdir()) == [
        "measurement-receipt.json",
        "workspace-projection.json",
    ]
    assert document["path"] == str(output / "workspace-projection.json")
    assert document["command"] == "so101_head_search_calibration measure-workspace-projection"
    assert receipt["measurement_path"] == document["path"]
    assert receipt["measurement_sha256"] == document["sha256"]
    assert receipt["top_px"] == document["top_px"]
    assert receipt["bottom_px"] == document["bottom_px"]
    assert receipt["pose_count"] == len(document["poses"])
    assert receipt["refusals"] == []
    assert receipt["detector_loaded"] is False
    assert receipt["runtime_identity"]["mujoco_only"] is True
    assert result["document"]["sha256"] == document["sha256"]
    assert reader.closed is True, "the producer closes the reader it was given"

    with pytest.raises(FileExistsError):
        write_head_search_workspace_projection(
            scene_path=scene,
            geometry_seal_path=seal_path,
            geometry_contract_path=contract_path,
            output_dir=output,
            scene_reader=_reader(seal_path),
        )


def test_write_projection_records_the_camera_pose_readback_it_took(tmp_path) -> None:
    scene = _scene(tmp_path)
    contract_path = _contract_path(tmp_path, scene)
    seal_path = _seal_path(tmp_path, scene, contract_path)
    output = tmp_path / "workspace-projection"

    result = write_head_search_workspace_projection(
        scene_path=scene,
        geometry_seal_path=seal_path,
        geometry_contract_path=contract_path,
        output_dir=output,
        scene_reader=_reader(seal_path),
    )

    readback = result["document"]["mujoco_readback"]
    assert readback["reader"] == "FakeSceneReader"
    assert readback["poses_checked"] == len(result["document"]["poses"])
    assert readback["max_position_delta_m"] <= 1e-9
    assert readback["max_rotation_delta"] <= 1e-9
    assert readback["agrees"] is True
    assert result["receipt"]["mujoco_readback"] is True
