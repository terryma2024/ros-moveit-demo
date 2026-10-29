"""Runtime identity, the MuJoCo scene camera and the projection writer."""

from __future__ import annotations

from collections.abc import Sequence
import json
from pathlib import Path
import sys
import time
from typing import Any

from so101_demo.act.head_camera_geometry.contract import HeadCameraGeometryContract
from so101_demo.act.head_search.workspace_projection.projection import (
    ARTIFACT_NAME,
    BOTTOM_FIELD,
    BOUNDARY_RULE,
    CAL_PROJECTION_EVIDENCE_MISSING,
    CAMERA_POSE_SOURCE,
    CAMERA_POSE_TOLERANCE,
    DIGEST_CONVENTION,
    KIND,
    PHASE,
    POINT_RULE,
    PROJECTION_FUNCTION,
    RECEIPT_ARTIFACT_NAME,
    RECEIPT_KIND,
    RECORDED_LIMITATIONS,
    SCHEMA_VERSION,
    TOP_FIELD,
    UNIT,
    SceneCameraPort,
    _aimed_projection,
    _refuse,
    load_projection_inputs,
    project_pose,
    projection_poses,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256


def build_head_search_workspace_projection(
    *,
    scene_path,
    geometry_seal_path,
    geometry_contract_path,
    scene_reader: SceneCameraPort,
    document_path=None,
    coarse_step_rad=None,
    command=None,
) -> dict:
    """Build the document phase 6 declares, from the seal, the contract and the scene.

    The order is: read and cross-check the sealed inputs, decide the pose set, read the camera pose the
    scene really has at every pose, project every declared workspace sample, and only then aggregate the
    extents. Every refusal stops the document before a number is produced. No file is written here.
    """

    inputs = load_projection_inputs(
        geometry_seal_path=geometry_seal_path,
        geometry_contract_path=geometry_contract_path,
        scene_path=scene_path,
    )
    geometry = inputs["geometry"]
    poses = projection_poses(
        seal=inputs["seal"],
        required_domain_rad=geometry["required_search_domain_rad"],
        safe_interval_rad=geometry["lock_valid_neck_rad"],
        anchors_rad=geometry["anchors_rad"],
        horizontal_fov_rad=geometry["horizontal_fov_rad"],
        sealed_candidate_rad=geometry["sealed_coarse_step_candidate_rad"],
        declared_step_rad=coarse_step_rad,
    )
    projections = [
        {**project_pose(inputs=inputs, pose_rad=pose["pose_rad"], reader=scene_reader), **pose}
        for pose in poses["poses"]
    ]
    tops = [projection["top_px"] for projection in projections]
    bottoms = [projection["bottom_px"] for projection in projections]
    union = [min(tops), max(bottoms)]
    intersection = [max(tops), min(bottoms)]
    aimed = _aimed_projection(inputs=inputs)
    aimed_band = aimed["band_px"]
    max_position_delta = max(
        projection["camera_pose"]["scene_reading_max_position_delta_m"] for projection in projections
    )
    max_rotation_delta = max(
        projection["camera_pose"]["scene_reading_max_axes_delta"] for projection in projections
    )
    contract = inputs["contract"]
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "phase": PHASE,
        "path": None if document_path is None else str(document_path),
        "command": command,
        "unit": UNIT,
        TOP_FIELD: float(union[0]),
        BOTTOM_FIELD: float(union[1]),
        "image_width_px": float(contract.image_width),
        "image_height_px": float(contract.image_height),
        "extent": {
            "headline": "union_over_visited_poses",
            "rule": BOUNDARY_RULE,
            "union_px": [float(union[0]), float(union[1])],
            "intersection_px": [float(intersection[0]), float(intersection[1])],
            "intersection_empty": not intersection[0] < intersection[1],
            "per_pose": [
                {
                    "pose_rad": projection["pose_rad"],
                    "top_px": projection["top_px"],
                    "bottom_px": projection["bottom_px"],
                    "in_frame_points": projection["in_frame_points"],
                }
                for projection in projections
            ],
        },
        "aimed_projection": {
            **aimed,
            "covered_by_union": bool(
                union[0] <= aimed_band[0] + 1e-9 and aimed_band[1] <= union[1] + 1e-9
            ),
            "covered_by_intersection": bool(
                intersection[0] <= aimed_band[0] + 1e-9
                and aimed_band[1] <= intersection[1] + 1e-9
            ),
            "union_gap_px": [float(union[0] - aimed_band[0]), float(aimed_band[1] - union[1])],
        },
        "workspace": {
            "declared_by": {
                "geometry_contract": {
                    "path": str(inputs["contract_path"]),
                    "sha256": inputs["contract_sha256"],
                    "keys": {
                        "workspace_x_m": "workspace_x_m",
                        "workspace_y_m": "workspace_y_m",
                        "workspace_z_m": "workspace_z_m",
                        "workspace_step_m": "workspace_step_m",
                    },
                },
                "geometry_seal": {
                    "path": str(inputs["seal_path"]),
                    "sha256": inputs["seal_sha256"],
                    "seal_sha256": inputs["seal"].get("seal_sha256"),
                    "key": "workspace_matrix.samples",
                },
            },
            "rule": POINT_RULE,
            "x_m": list(contract.workspace_x_m),
            "y_m": list(contract.workspace_y_m),
            "z_m": list(contract.workspace_z_m),
            "step_m": contract.workspace_step_m,
            "heights_m": list(
                (
                    contract.workspace_z_m[0],
                    (contract.workspace_z_m[0] + contract.workspace_z_m[1]) / 2.0,
                    contract.workspace_z_m[1],
                )
            ),
            "sample_count": len(inputs["points"]),
            "seal_sample_count": (inputs["seal"].get("workspace_matrix") or {}).get("samples"),
            "bearing_domain_rad": list(inputs["bearing_domain_rad"]),
        },
        "poses": projections,
        "pose_set": {
            "rule": poses["rule"],
            "step_source": poses["step_source"],
            "chosen_step_rad": poses["chosen_step_rad"],
            "phase_2_choice": poses["phase_2_choice"],
            "poses_are_step_independent": poses["poses_are_step_independent"],
            "candidate_steps": poses["candidate_steps"],
            "dedup_tolerance_rad": poses["dedup_tolerance_rad"],
            "pose_count": poses["pose_count"],
            "excluded_poses": poses["excluded_poses"],
        },
        "camera": contract.camera.to_document(),
        "camera_pose_source": CAMERA_POSE_SOURCE,
        "projection_function": PROJECTION_FUNCTION,
        "scene_path": str(inputs["scene_path"]),
        "scene_sha256": inputs["scene_sha256"],
        "sealed_evidence": {
            "geometry_seal": {
                "path": str(inputs["seal_path"]),
                "sha256": inputs["seal_sha256"],
                "seal_sha256": inputs["seal"].get("seal_sha256"),
            },
            "geometry_contract": {
                "path": str(inputs["contract_path"]),
                "sha256": inputs["contract_sha256"],
            },
            "scene": {"path": str(inputs["scene_path"]), "sha256": inputs["scene_sha256"]},
            "cross_checks": inputs["cross_checks"],
        },
        "mujoco_readback": {
            "reader": type(scene_reader).__name__,
            "poses_checked": len(projections),
            "max_position_delta_m": float(max_position_delta),
            "max_rotation_delta": float(max_rotation_delta),
            "agrees": bool(
                max_position_delta <= CAMERA_POSE_TOLERANCE
                and max_rotation_delta <= CAMERA_POSE_TOLERANCE
            ),
            "detail": (
                "the scene's own camera pose was read at every projected pose and compared with the "
                "sealed mount model before any sample was projected"
            ),
        },
        "recorded_limitations": list(RECORDED_LIMITATIONS),
        "refusals": [],
        "measured_here": True,
        "motion_commanded": False,
        "mujoco_neck_commanded": False,
        "mujoco_kinematics_read": True,
        "hardware_motion_commanded": False,
        "detector_loaded": False,
        "cuda_used": False,
        "ros_nodes_started": False,
        "digest_convention": DIGEST_CONVENTION,
    }
    document["sha256"] = canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    return document


def mujoco_version() -> str | None:
    """The MuJoCo the scene reader would load, or None when this environment has none."""

    try:
        import mujoco
    except ImportError:  # pragma: no cover - this environment ships MuJoCo
        return None
    return str(mujoco.__version__)


def runtime_identity(*, output_dir, scene_reader: SceneCameraPort | None = None) -> dict:
    """What the producer ran as: the interpreter, the module it loaded and the tools it did not load."""

    import so101_demo

    return {
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "so101_demo_module_path": str(Path(so101_demo.__file__).resolve()),
        "mujoco_version": mujoco_version(),
        "scene_reader": None if scene_reader is None else type(scene_reader).__name__,
        "output_dir": str(output_dir),
        "mujoco_only": True,
        "detector_loaded": False,
        "cuda_used": False,
        "ros_nodes_started": False,
        "motion_commanded": False,
    }


class MuJoCoSceneCamera:
    """The sealed scene read through MuJoCo: the camera's world pose at one neck angle.

    This is the same reading `head_camera_geometry`'s own scene port takes - the camera body's world
    position and the columns of its `cam_xmat` as the x and y axes - with the declared validation arm pose
    and the requested neck angle set before `mj_forward`, so the scene's camera pose and the sealed mount
    model can be compared field for field. No renderer, no GL context, no detector.
    """

    def __init__(self, scene_path, contract: HeadCameraGeometryContract) -> None:
        import mujoco

        self._mujoco = mujoco
        self._model = mujoco.MjModel.from_xml_path(str(Path(scene_path)))
        self._data = mujoco.MjData(self._model)
        self._camera_id = mujoco.mj_name2id(
            self._model, mujoco.mjtObj.mjOBJ_CAMERA, contract.camera_name
        )
        if self._camera_id < 0:
            raise _refuse(
                CAL_PROJECTION_EVIDENCE_MISSING,
                f"{contract.camera_name} is not a camera of {scene_path}",
            )
        self._neck_id = mujoco.mj_name2id(
            self._model, mujoco.mjtObj.mjOBJ_JOINT, contract.neck_joint
        )
        if self._neck_id < 0:
            raise _refuse(
                CAL_PROJECTION_EVIDENCE_MISSING,
                f"{contract.neck_joint} is not a joint of {scene_path}",
            )
        self._neck_qpos_adr = int(self._model.jnt_qposadr[self._neck_id])
        self._arm_qpos_adr = []
        for index, joint_name in enumerate(("1", "2", "3", "4", "5", "6")):
            joint_id = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
            if joint_id < 0:
                raise _refuse(
                    CAL_PROJECTION_EVIDENCE_MISSING,
                    f"the scene {scene_path} names no arm joint {joint_name!r}",
                )
            self._arm_qpos_adr.append(
                (int(self._model.jnt_qposadr[joint_id]), float(contract.validation_arm_rad[index]))
            )

    def camera_world_pose(self, neck_rad: float) -> tuple[Sequence[float], Sequence[float]]:
        mujoco = self._mujoco
        mujoco.mj_resetData(self._model, self._data)
        for address, value in self._arm_qpos_adr:
            self._data.qpos[address] = value
        self._data.qpos[self._neck_qpos_adr] = float(neck_rad)
        mujoco.mj_forward(self._model, self._data)
        camera_id = self._camera_id
        position = [float(value) for value in self._data.cam_xpos[camera_id]]
        matrix = self._data.cam_xmat[camera_id].reshape(3, 3)
        axes = [
            float(matrix[0][0]),
            float(matrix[1][0]),
            float(matrix[2][0]),
            float(matrix[0][1]),
            float(matrix[1][1]),
            float(matrix[2][1]),
        ]
        return (position, axes)

    def close(self) -> None:
        self._data = None
        self._model = None


def write_head_search_workspace_projection(
    *,
    scene_path,
    geometry_seal_path,
    geometry_contract_path,
    output_dir,
    scene_reader: SceneCameraPort | None = None,
    coarse_step_rad=None,
    command=None,
) -> dict:
    """Produce the workspace projection document and its receipt into a brand-new directory.

    The directory is claimed before anything is read, so an existing one is refused rather than merged
    with; a reader the caller passed is closed here, and one this producer opened is closed too. The
    document and the receipt are the only files this producer creates.
    """

    started = time.time()
    scene = Path(scene_path)
    if not scene.is_file():
        raise FileNotFoundError(f"the workspace projection needs {scene}")
    output = Path(output_dir)
    output.mkdir(parents=True)
    reader = scene_reader
    try:
        if reader is None:
            contract = HeadCameraGeometryContract.from_path(Path(geometry_contract_path))
            reader = MuJoCoSceneCamera(scene, contract)
        document_path = output / ARTIFACT_NAME
        document = build_head_search_workspace_projection(
            scene_path=scene,
            geometry_seal_path=geometry_seal_path,
            geometry_contract_path=geometry_contract_path,
            scene_reader=reader,
            document_path=document_path,
            coarse_step_rad=coarse_step_rad,
            command=command,
        )
    finally:
        close = getattr(reader, "close", None)
        if callable(close):
            close()
    document_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": RECEIPT_KIND,
        "phase": PHASE,
        "status": "SUCCEEDED",
        "command": command,
        "unit": UNIT,
        TOP_FIELD: document[TOP_FIELD],
        BOTTOM_FIELD: document[BOTTOM_FIELD],
        "union_px": list(document["extent"]["union_px"]),
        "intersection_px": list(document["extent"]["intersection_px"]),
        "aimed_px": list(document["aimed_projection"]["band_px"]),
        "pose_count": document["pose_set"]["pose_count"],
        "poses_rad": [pose["pose_rad"] for pose in document["poses"]],
        "chosen_step_rad": document["pose_set"]["chosen_step_rad"],
        "step_source": document["pose_set"]["step_source"],
        "poses_are_step_independent": document["pose_set"]["poses_are_step_independent"],
        "projected_point_records": sum(len(pose["points"]) for pose in document["poses"]),
        "point_count": document["workspace"]["sample_count"],
        "image_width_px": document["image_width_px"],
        "image_height_px": document["image_height_px"],
        "measurement_path": str(document_path),
        "measurement_sha256": document["sha256"],
        "scene_path": document["scene_path"],
        "scene_sha256": document["scene_sha256"],
        "geometry_seal_path": document["sealed_evidence"]["geometry_seal"]["path"],
        "geometry_seal_sha256": document["sealed_evidence"]["geometry_seal"]["sha256"],
        "geometry_contract_path": document["sealed_evidence"]["geometry_contract"]["path"],
        "geometry_contract_sha256": document["sealed_evidence"]["geometry_contract"]["sha256"],
        "mujoco_readback": document["mujoco_readback"]["agrees"],
        "mujoco_readback_detail": dict(document["mujoco_readback"]),
        "excluded_poses": document["pose_set"]["excluded_poses"],
        "refusals": list(document["refusals"]),
        "elapsed_s": time.time() - started,
        "runtime_identity": runtime_identity(output_dir=output, scene_reader=reader),
        "mujoco_kinematics_read": True,
        "detector_loaded": False,
        "cuda_used": False,
        "ros_nodes_started": False,
        "mujoco_neck_commanded": False,
        "hardware_motion_commanded": False,
        "motion_commanded": False,
    }
    (output / RECEIPT_ARTIFACT_NAME).write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "document": document,
        "receipt": receipt,
        "document_path": document_path,
        "output_dir": output,
        "poses": document["poses"],
        "refusals": list(document["refusals"]),
    }
