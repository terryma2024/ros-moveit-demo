"""Camera pose from the seal and the head camera geometry validation."""

from __future__ import annotations

from collections.abc import Mapping
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any

from so101_demo.act.head_camera_geometry.contract import (
    _EPSILON,
    CameraDefinition,
    HeadCameraGeometryContract,
    HeadCameraGeometryError,
    HeadCameraGeometryResult,
    HeadCameraScenePort,
    _coverage_stops,
    coverage_intervals_cover,
    project_point,
)
from so101_demo.act.head_camera_geometry.scene import _MuJoCoHeadCameraScene, _safe_interval
from so101_demo.perception_benchmark.contracts import canonical_sha256


def validate_head_camera_geometry(
    scene_path: Path | str,
    contract: HeadCameraGeometryContract,
    *,
    scene_port: HeadCameraScenePort | None = None,
) -> HeadCameraGeometryResult:
    """Decide every acceptance rule and return the sealed geometry document."""

    scene = Path(scene_path)
    port = _MuJoCoHeadCameraScene(scene, contract) if scene_port is None else scene_port

    digests = dict(port.source_digests())
    scene_sha256 = str(digests.get("scene_sha256", ""))
    camera_source_sha256 = str(digests.get("camera_source_sha256", ""))
    if camera_source_sha256 != contract.accepted_camera_source_sha256 or (
        scene_sha256 != contract.accepted_scene_sha256
    ):
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_SOURCE_DRIFT: the camera source or scene digest changed: "
            f"scene={scene_sha256[:12]} camera={camera_source_sha256[:12]}"
        )

    observed = CameraDefinition.from_document(port.camera_document())
    frozen = contract.camera
    if (
        observed.camera_name != frozen.camera_name
        or observed.width != frozen.width
        or observed.height != frozen.height
        or observed.parent_body != frozen.parent_body
        or abs(observed.fovy_rad - frozen.fovy_rad) > contract.fov_tolerance_rad
        or observed.distortion_model != frozen.distortion_model
        or any(
            abs(observed.distortion[index] - frozen.distortion[index]) > contract.fov_tolerance_rad
            for index in range(5)
        )
        or any(
            abs(observed.local_position_m[index] - frozen.local_position_m[index])
            > contract.fov_tolerance_rad
            for index in range(3)
        )
        or any(
            abs(observed.local_xyaxes[index] - frozen.local_xyaxes[index])
            > contract.fov_tolerance_rad
            for index in range(6)
        )
    ):
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_DEFINITION_DRIFT: the scene's camera definition no longer matches the "
            "contract"
        )

    horizontal_fov = observed.horizontal_fov_rad
    if abs(horizontal_fov - frozen.horizontal_fov_rad) > contract.fov_tolerance_rad:
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_DEFINITION_DRIFT: the observed horizontal field of view differs from the "
            "contract"
        )

    half_fov = horizontal_fov / 2.0
    if contract.coarse_step_candidate_rad > half_fov + contract.fov_tolerance_rad:
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_STEP_EXCEEDS_HALF_FOV: the candidate coarse step "
            f"{contract.coarse_step_candidate_rad} exceeds half the horizontal field of view "
            f"{half_fov}; consecutive stops would leave uncovered gaps"
        )

    support_height = float(port.support_height_m())
    resting_height = support_height + float(port.target_rest_offset_m())
    workspace_low_z, workspace_high_z = contract.workspace_z_m
    if not workspace_low_z - 1e-3 <= resting_height <= workspace_high_z + 1e-3:
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_WORKSPACE_UNSUPPORTED: the declared workspace heights "
            f"[{workspace_low_z}, {workspace_high_z}] do not contain the model's resting target "
            f"height {resting_height} above the support at {support_height}"
        )

    workspace_points = _workspace_matrix_points(contract)
    bearings = [port.neck_angle_for_point(point) for point in workspace_points]
    required_domain = (min(bearings), max(bearings))

    safe_interval = _safe_interval(port, contract)
    if safe_interval is None:
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_SAFE_INTERVAL_INVALID: no unique safe interval contains the zero position "
            "and all three anchor start angles"
        )
    lock_valid_neck_rad = safe_interval
    contains_domain = (
        lock_valid_neck_rad[0] <= required_domain[0] + _EPSILON
        and required_domain[1] <= lock_valid_neck_rad[1] + _EPSILON
    )
    if not contains_domain:
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_REQUIRED_DOMAIN_UNCOVERED: the required search domain "
            f"{required_domain} is not inside the safe interval {lock_valid_neck_rad}"
        )

    intervals: list[tuple[float, float]] = []
    for anchor in contract.anchors:
        for stop in _coverage_stops(
            anchor_rad=anchor.neck_start_rad,
            domain=required_domain,
            step_rad=contract.coarse_step_candidate_rad,
        ):
            if not port.safe_at_neck(stop):
                raise HeadCameraGeometryError(
                    f"HEAD_CAMERA_SWEEP_UNSAFE: stop {stop} for anchor {anchor.name} is outside the "
                    "safe interval"
                )
            intervals.append((stop - half_fov, stop + half_fov))
    covers_domain = coverage_intervals_cover(intervals, required_domain)
    if not covers_domain:
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_FOV_UNION_INCOMPLETE: the coarse stops' field-of-view union does not cover "
            f"the required search domain {required_domain}"
        )

    matrix: dict[str, Mapping[str, Any]] = {}
    failures: list[Mapping[str, Any]] = []
    for anchor in contract.anchors:
        centre_angle = port.neck_angle_for_point(anchor.cup_start_m)
        target_points = tuple(port.target_points_m(anchor))
        if not target_points:
            raise HeadCameraGeometryError(
                f"HEAD_CAMERA_TARGET_GEOMETRY_MISSING: anchor {anchor.name} has no target points"
            )
        samples = []
        out_of_frame: list[float] = []
        for angle in (anchor.neck_start_rad, centre_angle):
            position, rotation = port.camera_world_pose(angle)
            projected = [
                project_point(
                    point_m=point,
                    camera_position_m=position,
                    camera_rotation=rotation,
                    width=observed.width,
                    height=observed.height,
                    fovy_rad=observed.fovy_rad,
                )
                for point in target_points
            ]
            inside = all(item[2] for item in projected)
            visible = None
            if hasattr(port, "visible_pixels"):
                visible = port.visible_pixels(anchor, angle)  # type: ignore[attr-defined]
            visible_ok = visible is None or int(visible) >= contract.visible_pixel_minimum
            in_frame = bool(inside and visible_ok)
            sample = {
                "neck_rad": angle,
                "in_frame": in_frame,
                "projected_points_in_frame": sum(1 for item in projected if item[2]),
                "projected_points": len(projected),
                "visible_pixels": None if visible is None else int(visible),
            }
            if not in_frame:
                out_of_frame.append(angle)
                failures.append({"anchor": anchor.name, **sample})
            samples.append(sample)
        matrix[anchor.name] = {
            "neck_start_rad": anchor.neck_start_rad,
            "centre_angle_rad": centre_angle,
            "samples": samples,
            "out_of_frame_rad": out_of_frame,
        }

    if failures:
        first = failures[0]
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_IN_FRAME_FAILURE: anchor "
            f"{first['anchor']} does not see its target at neck {first['neck_rad']} "
            f"({first['projected_points_in_frame']}/{first['projected_points']} points in frame, "
            f"{first['visible_pixels']} visible pixels)"
        )

    mount_origin, mount_xyaxes = _camera_mount_model(port, contract)
    workspace_matrix, key_samples = _evaluate_workspace_matrix(
        port, contract, observed, workspace_points, required_domain
    )

    return HeadCameraGeometryResult(
        coarse_step_candidate_rad=contract.coarse_step_candidate_rad,
        camera_name=observed.camera_name,
        image_width=observed.width,
        image_height=observed.height,
        horizontal_fov_rad=horizontal_fov,
        camera=observed,
        validation_arm_rad=contract.validation_arm_rad,
        camera_mount_origin_m=mount_origin,
        camera_mount_xyaxes=mount_xyaxes,
        workspace_matrix=workspace_matrix,
        support_height_m=support_height,
        anchors=tuple(anchor.name for anchor in contract.anchors),
        in_frame_matrix=MappingProxyType(matrix),
        in_frame_failures=(),
        required_search_domain_rad=required_domain,
        lock_valid_neck_rad=lock_valid_neck_rad,
        safe_interval_contains_required_domain=True,
        fov_union_covers_required_domain=True,
        camera_source_sha256=camera_source_sha256,
        scene_sha256=scene_sha256,
        contract_sha256=canonical_sha256(contract.to_document()),
    )


def camera_pose_from_seal(
    seal: Mapping[str, Any], neck_rad: float
) -> tuple[tuple[float, float, float], tuple[float, ...]]:
    """The world pose the sealed camera must be at for one neck angle.

    The neck rotates the mount about the world z axis through the sealed mount origin, so the camera's
    world position and orientation follow from the sealed local definition alone. A dataset render or a
    manifest that reports any other pose is describing a camera this seal does not cover.
    """

    origin = [float(value) for value in seal["camera_mount_origin_m"]]
    mount = [float(value) for value in seal["camera_mount_xyaxes"]]
    camera = seal["camera"]
    local_position = [float(value) for value in camera["local_position_m"]]
    local_axes = [float(value) for value in camera["local_xyaxes"]]
    cosine, sine = math.cos(float(neck_rad)), math.sin(float(neck_rad))
    rotation = ((cosine, -sine, 0.0), (sine, cosine, 0.0), (0.0, 0.0, 1.0))
    mount_x = (mount[0], mount[1], mount[2])
    mount_y = (mount[3], mount[4], mount[5])
    mount_z = (
        mount_x[1] * mount_y[2] - mount_x[2] * mount_y[1],
        mount_x[2] * mount_y[0] - mount_x[0] * mount_y[2],
        mount_x[0] * mount_y[1] - mount_x[1] * mount_y[0],
    )
    mount_columns = (mount_x, mount_y, mount_z)
    offset = [
        sum(mount_columns[column][row] * local_position[column] for column in range(3))
        for row in range(3)
    ]
    position = [
        origin[row] + sum(rotation[row][column] * offset[column] for column in range(3))
        for row in range(3)
    ]
    axes = []
    for local_axis in (
        (local_axes[0], local_axes[1], local_axes[2]),
        (local_axes[3], local_axes[4], local_axes[5]),
    ):
        in_mount = [
            sum(mount_columns[column][row] * local_axis[column] for column in range(3))
            for row in range(3)
        ]
        axes.append(
            tuple(
                sum(rotation[row][column] * in_mount[column] for column in range(3))
                for row in range(3)
            )
        )
    return (
        tuple(position),
        (
            axes[0][0],
            axes[0][1],
            axes[0][2],
            axes[1][0],
            axes[1][1],
            axes[1][2],
        ),
    )


def _camera_mount_model(
    port: HeadCameraScenePort, contract: HeadCameraGeometryContract
) -> tuple[tuple[float, float, float], tuple[float, ...]]:
    pose = getattr(port, "camera_mount_pose", None)
    if pose is None:
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_MOUNT_MODEL_MISSING: the scene cannot report the mount the camera rides on"
        )
    origin, axes = pose()
    return (
        tuple(float(value) for value in origin),
        tuple(float(value) for value in axes),
    )


def workspace_matrix_points(
    contract: HeadCameraGeometryContract,
) -> tuple[tuple[float, float, float], ...]:
    """Every declared workspace sample at every declared height, not just its mid plane.

    This is the public name of the rule the seal's own `workspace_matrix` counts (`samples`), so a
    document that has to project the very workspace the seal was built from can call it instead of
    re-implementing the sampling and hoping the two agree.
    """

    return _workspace_matrix_points(contract)


def _workspace_matrix_points(
    contract: HeadCameraGeometryContract,
) -> tuple[tuple[float, float, float], ...]:
    """Every declared workspace sample at every declared height, not just its mid plane."""

    x_low, x_high = contract.workspace_x_m
    y_low, y_high = contract.workspace_y_m
    z_low, z_high = contract.workspace_z_m
    heights = (z_low, (z_low + z_high) / 2.0, z_high)
    points: list[tuple[float, float, float]] = []
    for x in contract._axis_values(x_low, x_high):
        for y in contract._axis_values(y_low, y_high):
            for z in heights:
                points.append((x, y, z))
    return tuple(points)


def _evaluate_workspace_matrix(
    port: HeadCameraScenePort,
    contract: HeadCameraGeometryContract,
    camera: CameraDefinition,
    workspace_points: tuple[tuple[float, float, float], ...],
    required_domain: tuple[float, float],
) -> tuple[Mapping[str, Any], list[Mapping[str, Any]]]:
    """Every workspace sample must be inside the frame when the neck points at it.

    Projection decides the whole matrix; the samples that carry the required domain's endpoints are
    additionally rendered, so the occluders the scene actually contains are part of the evidence and
    not an assumption about them.
    """

    records = []
    embedded = []
    for point in workspace_points:
        if not bool(port.target_clear_of_support(point)):
            embedded.append({"point_m": list(point)})
            continue
        neck = port.neck_angle_for_point(point)
        position, rotation = port.camera_world_pose(neck)
        u, v, inside = project_point(
            point_m=point,
            camera_position_m=position,
            camera_rotation=rotation,
            width=camera.width,
            height=camera.height,
            fovy_rad=camera.fovy_rad,
        )
        records.append(
            {
                "point_m": list(point),
                "neck_rad": neck,
                "u": u,
                "v": v,
                "in_frame": bool(inside),
                "visible_pixels": None,
            }
        )
    endpoints = [
        min(records, key=lambda record: record["neck_rad"]),
        max(records, key=lambda record: record["neck_rad"]),
    ]
    anchor_samples = [
        {
            "point_m": list(anchor.cup_start_m),
            "neck_rad": port.neck_angle_for_point(anchor.cup_start_m),
            "anchor": anchor.name,
        }
        for anchor in contract.anchors
    ]
    key_records = []
    failures = []
    for record in endpoints + anchor_samples:
        neck = float(record["neck_rad"])
        point = tuple(record["point_m"])
        kind = "anchor" if "anchor" in record else "required_domain_endpoint"
        visible = int(port.visible_pixels_for_point(point, neck))
        # every key sample - the three anchors and both required-domain endpoints - must be rendered
        # visible in the scene as it stands, at the arm pose this contract declares. A target the
        # camera cannot put pixels on is not a target the search can find.
        sight = dict(port.endpoint_visibility(point, neck))
        key = {
            **record,
            "kind": kind,
            "visible_pixels": visible,
            "first_hit_body": sight.get("first_hit_body"),
            "in_frame": visible >= contract.visible_pixel_minimum,
        }
        key_records.append(key)
        if key["in_frame"] is False:
            failures.append(key)
    if embedded:
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_WORKSPACE_EMBEDDED: "
            f"{len(embedded)} declared workspace samples put the target inside the support; first is "
            f"{embedded[0]['point_m']}"
        )
    out_of_frame = [record for record in records if not record["in_frame"]]
    if out_of_frame or failures:
        first = (out_of_frame or failures)[0]
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_WORKSPACE_MATRIX_INCOMPLETE: "
            f"{len(out_of_frame)} of {len(records)} workspace samples are outside the frame and "
            f"{len(failures)} key samples are not visibly rendered; first is {first}"
        )
    matrix = {
        "samples": len(records),
        "in_frame": len(records) - len(out_of_frame),
        "rendered_key_samples": len(key_records),
        "key_samples": key_records,
        "min_rendered_visible_pixels": min(int(record["visible_pixels"]) for record in key_records),
        "min_anchor_visible_pixels": min(
            int(record["visible_pixels"]) for record in key_records if record["kind"] == "anchor"
        ),
        "required_domain_rad": [required_domain[0], required_domain[1]],
    }
    return (MappingProxyType(matrix), key_records)


def quaternion_wxyz_from_xyaxes(xyaxes: object) -> tuple[float, float, float, float]:
    """The unit quaternion (w, x, y, z) of the rotation two frame axes describe.

    MuJoCo hands a camera's orientation around as the x and y axes of its frame; a manifest records it
    as a quaternion. This is the one conversion between them, so a recorded pose can be compared with
    the pose the seal predicts instead of merely being finite.
    """

    values = [float(value) for value in xyaxes]  # type: ignore[union-attr]
    x_axis = values[0:3]
    y_axis = values[3:6]
    z_axis = [
        x_axis[1] * y_axis[2] - x_axis[2] * y_axis[1],
        x_axis[2] * y_axis[0] - x_axis[0] * y_axis[2],
        x_axis[0] * y_axis[1] - x_axis[1] * y_axis[0],
    ]
    matrix = (
        (x_axis[0], y_axis[0], z_axis[0]),
        (x_axis[1], y_axis[1], z_axis[1]),
        (x_axis[2], y_axis[2], z_axis[2]),
    )
    trace = matrix[0][0] + matrix[1][1] + matrix[2][2]
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        quaternion = (
            0.25 * scale,
            (matrix[2][1] - matrix[1][2]) / scale,
            (matrix[0][2] - matrix[2][0]) / scale,
            (matrix[1][0] - matrix[0][1]) / scale,
        )
    elif matrix[0][0] > matrix[1][1] and matrix[0][0] > matrix[2][2]:
        scale = math.sqrt(1.0 + matrix[0][0] - matrix[1][1] - matrix[2][2]) * 2.0
        quaternion = (
            (matrix[2][1] - matrix[1][2]) / scale,
            0.25 * scale,
            (matrix[0][1] + matrix[1][0]) / scale,
            (matrix[0][2] + matrix[2][0]) / scale,
        )
    elif matrix[1][1] > matrix[2][2]:
        scale = math.sqrt(1.0 + matrix[1][1] - matrix[0][0] - matrix[2][2]) * 2.0
        quaternion = (
            (matrix[0][2] - matrix[2][0]) / scale,
            (matrix[0][1] + matrix[1][0]) / scale,
            0.25 * scale,
            (matrix[1][2] + matrix[2][1]) / scale,
        )
    else:
        scale = math.sqrt(1.0 + matrix[2][2] - matrix[0][0] - matrix[1][1]) * 2.0
        quaternion = (
            (matrix[1][0] - matrix[0][1]) / scale,
            (matrix[0][2] + matrix[2][0]) / scale,
            (matrix[1][2] + matrix[2][1]) / scale,
            0.25 * scale,
        )
    norm = math.sqrt(sum(value * value for value in quaternion))
    if not math.isfinite(norm) or norm <= 0.0:
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_ORIENTATION_INVALID: the axes are not a rotation"
        )
    return (
        quaternion[0] / norm,
        quaternion[1] / norm,
        quaternion[2] / norm,
        quaternion[3] / norm,
    )
