"""The workspace projection document phase 6 consumes: the legal pick workspace in the head camera.

`vertical_bounds_px` is "the legal pick workspace projected into the head camera, intersected with the
image safety margin, never back-filled from detection extremes" (design section 7.1). Three things have
to exist before an installed phase can compute it: a **declared** legal pick workspace, a projection of
that workspace into the **sealed** head camera, and the image-space extent the projection produces. The
workspace is declared - `config/act/head-camera-geometry-contract.json` fixes
`workspace_x_m`/`workspace_y_m`/`workspace_z_m` and `workspace_step_m`, and the seal's own
`workspace_matrix.samples` counts the samples that declaration produces - but the projection itself is
retained only as that count and five key samples, so this module is the producer that projects it.

Where every number comes from (nothing here is invented):

* **the points**: the geometry contract's declared workspace box under the seal's own sampling rule -
  both declared edges of each axis, at the three declared heights - is the point set. It is the same rule
  the seal's `workspace_matrix` was built with, and this document records the seal's own sample count
  beside the one it computed, refusing a disagreement rather than projecting a different workspace.
* **the poses**: the bounded plan's stop points that lie inside the sealed `required_search_domain_rad`,
  per sealed anchor, plus each anchor's own start angle when that start is inside the domain. The plan is
  phase 2's `bounded_search_stops`, at the coarse step phase 2's own selection rule chooses (the largest
  generated candidate whose sweep covers the required domain from every anchor - the step phase 2
  receipts and phase 6 accepts). A caller holding that plan may declare it instead; a declared step then
  has to be a generated candidate and to cover the domain, or the pose set would be one no plan of this
  geometry could have, which refuses with `CAL_PROJECTION_POSE_SET_AMBIGUOUS`. Every candidate's
  in-domain stop set is recorded and `poses_are_step_independent` says whether the choice mattered. An
  anchor start outside the required domain is recorded as excluded, never clamped.
* **the camera pose**: `head_camera_geometry.camera_pose_from_seal`, the sealed mount model (the neck
  rotates the mount about the world z axis through the sealed `camera_mount_origin_m`), and the scene
  itself is read through MuJoCo at every projected pose so the sealed model and the model the runtime
  steps have to agree, pose by pose, before a point is projected.
* **the projection**: `head_camera_geometry.project_point`, the seal's own projection, and the same
  convention its scene port feeds it (the columns of the rotation are the camera's world axes). The
  document records the camera pose it used for every pose and the function it used for every point.
* **the extent**: per pose, the smallest and largest projected row, clipped to the image; and the
  headline `top_px`/`bottom_px` is the **union** over the visited poses - the envelope of the legal
  workspace in the image, which contains the row of every legal sample at every visited pose. The
  **intersection** over the poses (the rows every visited pose can produce) and the **aimed band** (every
  sample projected at its own bearing, i.e. the row a horizontally centred sample has) are recorded beside
  it, with whether they cover the aimed band, because the lock rule accepts a detection whose box centre
  is inside the centre deadband, and the fine-correction path can hold the neck between the stops.

Not this document's field: the image safety margin. Phase 6 intersects this projection with
`safety_margin_px` from the camera measurements document, so no margin is read, defaulted or intersected
here.

Nothing here loads a detector, touches a GPU, starts a ROS node or commands motion: the run is
detector-free by construction, the receipt and the document both say so, and the only heavy import
(MuJoCo) happens inside the scene reader. Nothing is written unless the caller passes an explicit
`output_dir` (the producer) or `document_path`.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from so101_demo.act.head_camera_geometry import (
    HeadCameraGeometryContract,
    camera_pose_from_seal,
    project_point,
    workspace_matrix_points,
)
from so101_demo.act.head_search_calibration_geometry import (
    SELECTION_RULE,
    choose_coarse_step_candidate,
    generate_coarse_step_candidates,
    read_geometry_document,
)
from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_domain import (
    HeadSearchDomainError,
    bounded_search_stops,
    coverage_is_complete,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

SCHEMA_VERSION = 1
KIND = "head_search_calibration_workspace_projection"
RECEIPT_KIND = "head_search_calibration_workspace_projection_receipt"
PHASE = "workspace_projection"

#: the artefact the run declares under `--workspace-projection`, and the two fields phase 6 reads
ARTIFACT_NAME = "workspace-projection.json"
RECEIPT_ARTIFACT_NAME = "measurement-receipt.json"
TOP_FIELD = "top_px"
BOTTOM_FIELD = "bottom_px"
UNIT = "px"

CAL_PROJECTION_EVIDENCE_MISSING = "CAL_PROJECTION_EVIDENCE_MISSING"
CAL_PROJECTION_EVIDENCE_CONTRADICTORY = "CAL_PROJECTION_EVIDENCE_CONTRADICTORY"
CAL_PROJECTION_POSE_SET_AMBIGUOUS = "CAL_PROJECTION_POSE_SET_AMBIGUOUS"
CAL_PROJECTION_POINT_UNPROJECTABLE = "CAL_PROJECTION_POINT_UNPROJECTABLE"
CAL_PROJECTION_EMPTY = "CAL_PROJECTION_EMPTY"
REFUSAL_CODES = (
    CAL_PROJECTION_EVIDENCE_MISSING,
    CAL_PROJECTION_EVIDENCE_CONTRADICTORY,
    CAL_PROJECTION_POSE_SET_AMBIGUOUS,
    CAL_PROJECTION_POINT_UNPROJECTABLE,
    CAL_PROJECTION_EMPTY,
)

#: the convention the run's other measurement documents use, so phase 6 can cite this one by path+digest
DIGEST_CONVENTION = "sha256 = canonical_sha256(body without the sha256 field)"

#: two poses closer than this are the same pose: phase 2's anchors reach the same domain endpoints
#: through different legs, and a last-bit difference is not a different place to look from
POSE_DEDUP_TOLERANCE_RAD = 1e-12

#: how far the MuJoCo scene reading of a camera pose may differ from the sealed mount model; the sealed
#: derivation reproduced the model to 2.2e-16 when it was measured, so a real disagreement is far larger
CAMERA_POSE_TOLERANCE = 1e-9

POINT_RULE = (
    "the geometry contract's declared workspace box (workspace_x_m x workspace_y_m x workspace_z_m at "
    "workspace_step_m) under the seal's own workspace-matrix rule: both declared edges of each axis, at "
    "the three declared heights (low, mid, high)"
)
POSE_RULE = (
    "the bounded plan's stop points inside the sealed required_search_domain_rad, per sealed anchor, plus "
    "each anchor's own start angle when it lies inside that domain; the plan is phase 2's "
    "`bounded_search_stops` and a pose outside the domain is excluded, never clamped"
)
BOUNDARY_RULE = (
    "top_px = the smallest, and bottom_px = the largest, projected row over the visited poses (the union "
    "of the per-pose extents): the band contains the image row of every legal workspace sample at every "
    "pose the search holds. The intersection over the poses is recorded beside it as a strictly stronger "
    "claim, and so is the aimed band (every sample at its own bearing)"
)
AIMED_RULE = (
    "every workspace sample projected at its own sealed bearing (the seal's own neck_angle_for_point "
    "construction, which puts it on the optical column u = width / 2): the row a horizontally centred "
    "sample has, which is the row the three-frame lock rule accepts"
)
PROJECTION_FUNCTION = "head_camera_geometry.project_point"
CAMERA_POSE_SOURCE = "camera_pose_from_seal"

RECORDED_LIMITATIONS = (
    "the projection covers the contract's declared workspace samples - the target's placement positions "
    "at the declared resting heights - and not the rendered silhouette of the cup: a band taken from "
    "rendered boxes or detections would be the detection-side measurement phase 6 refuses to back-fill",
    "the pose set is the bounded plan's in-domain stop points plus the in-domain anchor starts; the fine "
    "correction path can hold the neck at angles between them, so the aimed band is recorded beside the "
    "pose extents instead of being absorbed into them",
    "the pose set is the bounded plan of the step phase 2's own selection rule chooses, or of the step "
    "the caller declared (which has to be a generated candidate that covers the required domain); every "
    "candidate's own in-domain stop set is recorded in pose_set.candidate_steps and "
    "pose_set.poses_are_step_independent says whether the choice changed the projected poses at all",
    "top_px/bottom_px are the union over the visited poses; the intersection over the poses (the rows "
    "every visited pose can produce) is recorded beside them and is a strictly stronger claim that can "
    "reject a legal observation at a pose where part of the workspace reaches outside it",
    "the image safety margin is not this document's field: phase 6 intersects this projection with the "
    "camera measurements document's declared safety_margin_px, so no margin is defaulted or intersected "
    "here",
)


class CalibrationWorkspaceProjectionRefused(CalibrationInputsRefused):
    """A workspace-projection refusal, carrying the exact code the run records and stops on.

    It is a phase-1 refusal as well, so a caller that catches `CalibrationInputsRefused` catches every
    refusal of the calibration phases and reads the code off the exception.
    """


class SceneCameraPort(Protocol):
    """What the producer asks a scene for: the camera's world pose at one neck angle.

    The returned axes follow the seal's own convention - the camera's x axis and then its y axis, three
    numbers each - so the scene reading and the sealed mount model are compared field for field.
    """

    def camera_world_pose(self, neck_rad: float) -> tuple[Sequence[float], Sequence[float]]: ...

    def close(self) -> None: ...


def _refuse(code: str, detail: str) -> CalibrationWorkspaceProjectionRefused:
    return CalibrationWorkspaceProjectionRefused(code, detail)


def _re_raised(call, *args, **kwargs):
    """Run a reused check, re-raising its refusal as this measurement's own class.

    The sealed-geometry reader and the bounded plan are other modules' code, so the refusals they raise -
    an unsealed geometry, a domain the plan cannot cover - are raised as that module's type. They are this
    measurement's refusals too, so they are re-raised here with the same code.
    """

    try:
        return call(*args, **kwargs)
    except CalibrationInputsRefused as error:
        raise _refuse(error.code, error.detail) from error


def _finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _digest(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _interval(name: str, value, *, path="the sealed geometry") -> tuple[float, float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != 2:
        raise _refuse(
            CAL_PROJECTION_EVIDENCE_MISSING,
            f"{path}: the sealed geometry declares no two-value {name}",
        )
    low, high = (float(bound) for bound in value)
    if not math.isfinite(low) or not math.isfinite(high) or low >= high:
        raise _refuse(
            CAL_PROJECTION_EVIDENCE_MISSING,
            f"{path}: the sealed geometry's {name} {list(value)} is not a finite ordered interval",
        )
    return low, high


def camera_rotation_matrix(axes: Sequence[float]) -> tuple[tuple[float, float, float], ...]:
    """The projection matrix `project_point` takes from the seal's x/y axes.

    `project_point` reads its rotation as the camera frame expressed in world coordinates, which is what
    the seal's `camera_pose_from_seal` returns as two axes: the third is their cross product, and the
    matrix's columns are the three axes. The seal's scene port feeds the same matrix out of MuJoCo's own
    `cam_xmat`, so one convention is used on both sides.
    """

    x_axis = tuple(float(value) for value in axes[0:3])
    y_axis = tuple(float(value) for value in axes[3:6])
    if len(x_axis) != 3 or len(y_axis) != 3:
        raise ValueError("a camera pose must carry an x axis and a y axis of three numbers each")
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


def sealed_camera_pose(seal, neck_rad) -> tuple[tuple[float, float, float], tuple]:
    """The sealed mount model's camera pose at one neck angle, as position and x/y axes."""

    position, axes = camera_pose_from_seal(seal, float(neck_rad))
    return (
        tuple(float(value) for value in position),
        tuple(float(value) for value in axes),
    )


def sealed_bearing_rad(point_m, *, mount_origin_m) -> float:
    """The neck angle that puts one workspace point on the optical column.

    This is the seal's own `neck_angle_for_point` construction - the yaw about the world z axis through
    the mount origin - which is how the seal derived its required search domain from its workspace
    matrix, so this document can check the box it projects against the domain the seal recorded.
    """

    origin = [float(value) for value in mount_origin_m]
    return math.atan2(
        float(point_m[0]) - origin[0], -(float(point_m[1]) - origin[1])
    )


def workspace_sample_points(contract) -> tuple[tuple[float, float, float], ...]:
    """The declared workspace samples, under the seal's own workspace-matrix rule."""

    if not isinstance(contract, HeadCameraGeometryContract):
        contract = HeadCameraGeometryContract.from_path(Path(contract))
    return workspace_matrix_points(contract)


def _mount_origin(seal, path) -> tuple[float, float, float]:
    origin = seal.get("camera_mount_origin_m")
    if isinstance(origin, (str, bytes)) or not isinstance(origin, Sequence) or len(origin) != 3:
        raise _refuse(
            CAL_PROJECTION_EVIDENCE_MISSING,
            f"{path}: the sealed geometry records no three-value camera_mount_origin_m, so no workspace "
            f"sample can be aimed at and no required domain can be checked",
        )
    values = tuple(float(value) for value in origin)
    if not all(math.isfinite(value) for value in values):
        raise _refuse(
            CAL_PROJECTION_EVIDENCE_MISSING,
            f"{path}: the sealed geometry's camera_mount_origin_m is not finite",
        )
    return values  # type: ignore[return-value]


def projection_poses(
    *,
    seal,
    required_domain_rad,
    safe_interval_rad,
    anchors_rad: Mapping[str, float],
    horizontal_fov_rad: float,
    sealed_candidate_rad=None,
    declared_step_rad=None,
) -> dict:
    """The poses the search visits inside the required domain, with every candidate step's verdict.

    The plan whose stops are projected is the one phase 2's own selection rule chooses - the largest
    generated coarse-step candidate whose bounded sweep covers the required domain from every anchor -
    which is exactly the step phase 2 receipts and phase 6 accepts. A caller that holds that plan may
    declare it with `declared_step_rad` instead; a declared step then has to be one of the generated
    candidates and to cover the domain, because a step phase 2 could not have receipted is not the plan
    the search walks. Every candidate's in-domain stop set is recorded, and
    `poses_are_step_independent` says whether the choice changed the pose set at all. The returned poses
    are sorted by angle, deduplicated within `POSE_DEDUP_TOLERANCE_RAD`, and carry the kinds and the
    anchors that command them.
    """

    domain = _interval("required_search_domain_rad", required_domain_rad)
    safe = _interval("lock_valid_neck_rad", safe_interval_rad)
    if not (safe[0] <= domain[0] + 1e-9 and domain[1] <= safe[1] + 1e-9):
        raise _refuse(
            CAL_PROJECTION_EVIDENCE_CONTRADICTORY,
            f"the sealed required domain {list(domain)} is not inside the sealed safe interval "
            f"{list(safe)}, so the poses the plan would command are not the poses the seal allows",
        )
    fov = float(horizontal_fov_rad)
    if not math.isfinite(fov) or fov <= 0.0:
        raise _refuse(
            CAL_PROJECTION_EVIDENCE_MISSING,
            f"the sealed geometry declares the non-positive horizontal field of view {horizontal_fov_rad!r}",
        )
    anchors = _anchors(anchors_rad)
    candidates = generate_coarse_step_candidates(
        fov,
        sealed_candidate_rad=None if sealed_candidate_rad is None else float(sealed_candidate_rad),
    )
    if not candidates:
        raise _refuse(
            CAL_PROJECTION_EVIDENCE_MISSING,
            "the sealed field of view generates no coarse-step candidate, so the bounded plan the search "
            "walks cannot be reproduced",
        )

    choice = _re_raised(
        choose_coarse_step_candidate,
        horizontal_fov_rad=fov,
        required_search_domain_rad=domain,
        safe_interval_rad=safe,
        anchors_rad=anchors,
        sealed_candidate_rad=None if sealed_candidate_rad is None else float(sealed_candidate_rad),
    )
    chosen_by_rule = float(choice["chosen_candidate_rad"])
    if declared_step_rad is None:
        chosen, step_source = chosen_by_rule, "phase_2_selection_rule"
    else:
        declared = float(declared_step_rad)
        if not any(abs(declared - float(candidate)) <= POSE_DEDUP_TOLERANCE_RAD for candidate in candidates):
            raise _refuse(
                CAL_PROJECTION_POSE_SET_AMBIGUOUS,
                f"the declared coarse step {declared} is none of the candidates phase 2 generates from the "
                f"sealed field of view {list(candidates)}, so the poses it produces are not a plan phase 2 "
                f"could have receipted",
            )
        for name, anchor in anchors.items():
            plan = _plan(
                anchors_name=name, anchor=anchor, domain=domain, safe=safe, fov=fov, step=declared
            )
            if not coverage_is_complete(plan, required_domain_rad=domain):
                raise _refuse(
                    CAL_PROJECTION_POSE_SET_AMBIGUOUS,
                    f"the declared coarse step {declared} does not cover the required domain from anchor "
                    f"{name!r}, so it is not the plan the search walks",
                )
        chosen, step_source = declared, "declared"

    records = []
    sets: dict[float, list[float]] = {}
    for step in candidates:
        stops = _plan_targets(anchors=anchors, domain=domain, safe=safe, fov=fov, step=step)
        inside = [
            (name, target, index)
            for name, target, index in stops
            if domain[0] - POSE_DEDUP_TOLERANCE_RAD
            <= target
            <= domain[1] + POSE_DEDUP_TOLERANCE_RAD
        ]
        sets[float(step)] = sorted(target for _name, target, _index in inside)
        records.append(
            {
                "coarse_step_rad": float(step),
                "source": "sealed" if float(step) == float(sealed_candidate_rad or 0.0) else "generated",
                "in_domain_stops_rad": sets[float(step)],
                "stop_count": len(sets[float(step)]),
            }
        )
    reference = sets[chosen]
    for record in records:
        record["pose_set_agrees"] = _same_angles(reference, sets[record["coarse_step_rad"]])
    independent = all(record["pose_set_agrees"] for record in records)

    excluded: list[dict] = []
    poses: list[dict] = []
    for name, anchor in anchors.items():
        if domain[0] - POSE_DEDUP_TOLERANCE_RAD <= anchor <= domain[1] + POSE_DEDUP_TOLERANCE_RAD:
            _merge_pose(poses, anchor, kind="anchor_start", anchor=name)
        else:
            excluded.append(
                {
                    "anchor": name,
                    "neck_rad": anchor,
                    "reason": "outside_required_search_domain",
                    "domain_rad": [domain[0], domain[1]],
                }
            )
    for name, target, index in _plan_targets(
        anchors=anchors, domain=domain, safe=safe, fov=fov, step=chosen
    ):
        if domain[0] - POSE_DEDUP_TOLERANCE_RAD <= target <= domain[1] + POSE_DEDUP_TOLERANCE_RAD:
            _merge_pose(poses, target, kind="plan_stop", anchor=name, stop_index=index)
        else:
            excluded.append(
                {
                    "anchor": name,
                    "neck_rad": target,
                    "reason": "outside_required_search_domain",
                    "domain_rad": [domain[0], domain[1]],
                }
            )
    poses.sort(key=lambda pose: pose["pose_rad"])
    return {
        "rule": POSE_RULE,
        "required_search_domain_rad": [domain[0], domain[1]],
        "safe_interval_rad": [safe[0], safe[1]],
        "horizontal_fov_rad": fov,
        "step_source": step_source,
        "chosen_step_rad": chosen,
        "phase_2_choice": {
            "rule": SELECTION_RULE,
            "chosen_candidate_rad": chosen_by_rule,
            "chosen_index": choice["chosen_index"],
            "candidates": list(choice["candidates"]),
        },
        "poses_are_step_independent": bool(independent),
        "candidate_steps": records,
        "dedup_tolerance_rad": POSE_DEDUP_TOLERANCE_RAD,
        "poses": poses,
        "excluded_poses": excluded,
        "pose_count": len(poses),
    }


def _plan_targets(*, anchors, domain, safe, fov, step) -> list[tuple[str, float, int]]:
    targets: list[tuple[str, float, int]] = []
    for name, anchor in anchors.items():
        plan = _plan(
            anchors_name=name, anchor=anchor, domain=domain, safe=safe, fov=fov, step=step
        )
        for index, target in enumerate(plan.targets_rad):
            targets.append((name, float(target), index))
    return targets


def _plan(*, anchors_name: str, anchor: float, domain, safe, fov, step):
    """The bounded plan of one anchor, or this measurement's own refusal when it cannot be built."""

    try:
        return bounded_search_stops(
            anchor_rad=anchor,
            required_domain_rad=domain,
            safe_interval_rad=safe,
            horizontal_fov_rad=fov,
            coarse_step_rad=float(step),
        )
    except HeadSearchDomainError as error:
        raise _refuse(
            CAL_PROJECTION_EVIDENCE_CONTRADICTORY,
            f"the sealed geometry's bounded plan cannot be built from anchor {anchors_name!r} "
            f"({anchor}) at the coarse step {step}: {error}",
        ) from error


def _same_angles(first: Sequence[float], second: Sequence[float]) -> bool:
    if len(first) != len(second):
        return False
    return all(
        abs(left - right) <= POSE_DEDUP_TOLERANCE_RAD for left, right in zip(first, second, strict=True)
    )


def _merge_pose(poses: list[dict], angle: float, *, kind: str, anchor: str, stop_index=None) -> None:
    for pose in poses:
        if abs(pose["pose_rad"] - angle) <= POSE_DEDUP_TOLERANCE_RAD:
            if kind not in pose["kinds"]:
                pose["kinds"].append(kind)
            if anchor not in pose["visited_by"]:
                pose["visited_by"].append(anchor)
            if abs(pose["pose_rad"] - angle) > 0.0:
                pose["merged_from_rad"].append(angle)
            if stop_index is not None and stop_index not in pose["stop_indices"]:
                pose["stop_indices"].append(stop_index)
            return
    poses.append(
        {
            "pose_rad": float(angle),
            "kinds": [kind],
            "visited_by": [anchor],
            "merged_from_rad": [],
            "stop_indices": [] if stop_index is None else [stop_index],
        }
    )


def _anchors(anchors_rad) -> dict[str, float]:
    if not isinstance(anchors_rad, Mapping) or not anchors_rad:
        raise _refuse(
            CAL_PROJECTION_EVIDENCE_MISSING,
            "the sealed geometry declares no anchor to plan a bounded sweep from",
        )
    anchors: dict[str, float] = {}
    for name, angle in anchors_rad.items():
        if type(name) is not str or not name or not _finite(angle):
            raise _refuse(
                CAL_PROJECTION_EVIDENCE_MISSING,
                "every sealed anchor must be named and carry a finite neck start angle",
            )
        anchors[name] = float(angle)
    return anchors


def load_projection_inputs(*, geometry_seal_path, geometry_contract_path, scene_path) -> dict:
    """Read the seal and the contract, and refuse anything that does not describe one geometry.

    The seal is read through the calibration's own reader, so its `seal_sha256` has to be the canonical
    digest of its body before any value is taken from it; the contract is read through the geometry
    module's own contract loader, so a contract the seal was not built from cannot be projected. Every
    cross-check here is a refusal, never a preference between two candidate values.
    """

    seal_path = Path(geometry_seal_path)
    contract_path = Path(geometry_contract_path)
    scene = Path(scene_path)
    for path in (seal_path, contract_path, scene):
        if not path.is_file():
            raise _refuse(
                CAL_PROJECTION_EVIDENCE_MISSING,
                f"the workspace projection needs {path}, which is not a file",
            )
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    if not isinstance(seal, Mapping):
        raise _refuse(
            CAL_PROJECTION_EVIDENCE_MISSING, f"{seal_path}: the sealed geometry is not a JSON object"
        )
    geometry = _re_raised(read_geometry_document, seal, path=str(seal_path))
    try:
        contract = HeadCameraGeometryContract.from_path(contract_path)
    except (OSError, ValueError) as error:
        raise _refuse(
            CAL_PROJECTION_EVIDENCE_MISSING,
            f"{contract_path}: the geometry contract cannot be read as the declared workspace "
            f"({error})",
        ) from error

    scene_sha256 = _digest(scene)
    source_digests = seal.get("source_digests")
    if not isinstance(source_digests, Mapping) or "scene_sha256" not in source_digests:
        raise _refuse(
            CAL_PROJECTION_EVIDENCE_MISSING,
            f"{seal_path}: the sealed geometry records no source_digests.scene_sha256, so the scene the "
            f"projection reads its camera pose from is not the scene the seal covers",
        )
    checks = {
        "scene_digest_agrees_with_the_seal": source_digests["scene_sha256"] == scene_sha256,
        "scene_digest_agrees_with_the_contract": contract.accepted_scene_sha256 == scene_sha256,
        "camera_source_digest_agrees": (
            source_digests.get("camera_source_sha256") == contract.accepted_camera_source_sha256
        ),
    }
    for name, agreed in checks.items():
        if not agreed:
            raise _refuse(
                CAL_PROJECTION_EVIDENCE_CONTRADICTORY,
                f"the sealed geometry, the geometry contract and the scene do not describe one geometry: "
                f"{name} is false (scene {scene} digests to {scene_sha256})",
            )

    sealed_camera = seal.get("camera")
    frozen = contract.camera.to_document()
    observed = sealed_camera if isinstance(sealed_camera, Mapping) else {}
    tolerance = float(contract.fov_tolerance_rad)
    camera_checks = {
        "camera_name": observed.get("camera_name") == frozen["camera_name"],
        "width": observed.get("width") == frozen["width"],
        "height": observed.get("height") == frozen["height"],
        "fovy_rad": _close(observed.get("fovy_rad"), frozen["fovy_rad"], tolerance),
        "distortion_model": observed.get("distortion_model") == frozen["distortion_model"],
        "distortion": _vectors_close(observed.get("distortion"), frozen["distortion"], tolerance),
        "local_position_m": _vectors_close(
            observed.get("local_position_m"), frozen["local_position_m"], tolerance
        ),
        "local_xyaxes": _vectors_close(
            observed.get("local_xyaxes"), frozen["local_xyaxes"], tolerance
        ),
    }
    for name, agreed in camera_checks.items():
        if not agreed:
            raise _refuse(
                CAL_PROJECTION_EVIDENCE_CONTRADICTORY,
                f"the sealed geometry's camera and the geometry contract's camera are not the same "
                f"camera: {name} disagrees",
            )
    fov = float(geometry["horizontal_fov_rad"])
    if not _close(fov, contract.horizontal_fov_rad(), tolerance):
        raise _refuse(
            CAL_PROJECTION_EVIDENCE_CONTRADICTORY,
            f"the sealed horizontal field of view {fov} is not the one the contract's camera definition "
            f"implies ({contract.horizontal_fov_rad()})",
        )

    points = workspace_sample_points(contract)
    seal_samples = (seal.get("workspace_matrix") or {}).get("samples")
    if seal_samples != len(points):
        raise _refuse(
            CAL_PROJECTION_EVIDENCE_CONTRADICTORY,
            f"the seal's workspace_matrix counts {seal_samples!r} samples but the contract's declared "
            f"workspace box produces {len(points)}, so the box this document would project is not the one "
            f"the seal was built from",
        )
    mount_origin = _mount_origin(seal, seal_path)
    bearings = [sealed_bearing_rad(point, mount_origin_m=mount_origin) for point in points]
    bearing_domain = [min(bearings), max(bearings)]
    domain = [float(value) for value in geometry["required_search_domain_rad"]]
    if not _same_angles(bearing_domain, domain):
        raise _refuse(
            CAL_PROJECTION_EVIDENCE_CONTRADICTORY,
            f"the workspace box's own bearings span {bearing_domain} but the seal records the required "
            f"search domain {domain}: the declared box is not the box the seal was built from",
        )
    return {
        "seal": seal,
        "seal_path": seal_path,
        "seal_sha256": _digest(seal_path),
        "geometry": geometry,
        "contract": contract,
        "contract_path": contract_path,
        "contract_sha256": _digest(contract_path),
        "scene_path": scene,
        "scene_sha256": scene_sha256,
        "points": points,
        "mount_origin_m": mount_origin,
        "bearing_domain_rad": bearing_domain,
        "cross_checks": {
            **checks,
            **{f"camera_{name}": value for name, value in camera_checks.items()},
            "workspace_sample_count_agrees": True,
            "workspace_bearings_agree_with_the_required_domain": True,
            "required_domain_inside_safe_interval": (
                float(geometry["lock_valid_neck_rad"][0]) <= domain[0]
                and domain[1] <= float(geometry["lock_valid_neck_rad"][1])
            ),
        },
    }


def _close(value, expected, tolerance) -> bool:
    return _finite(value) and abs(float(value) - float(expected)) <= tolerance


def _vectors_close(value, expected, tolerance) -> bool:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return False
    if len(value) != len(expected):
        return False
    return all(_close(item, target, tolerance) for item, target in zip(value, expected, strict=True))


def project_pose(
    *,
    inputs,
    pose_rad: float,
    reader: SceneCameraPort,
    camera_pose=None,
) -> dict:
    """Project every declared workspace sample at one pose, with the evidence for each projection.

    The scene's own reading of the camera pose is compared with the sealed mount model before a point is
    projected: a scene whose camera is not where the seal says it is cannot supply the projection, and the
    disagreement is a refusal rather than a preference. A sample the camera cannot project at all - one
    behind it - refuses the pose; a pose whose whole projection falls outside the image refuses too.
    """

    seal = inputs["seal"]
    contract = inputs["contract"]
    points = inputs["points"]
    width = float(contract.image_width)
    height = float(contract.image_height)
    position, axes = sealed_camera_pose(seal, pose_rad)
    if camera_pose is None:
        observed_position, observed_axes = reader.camera_world_pose(float(pose_rad))
    else:
        observed_position, observed_axes = camera_pose
    position_delta = max(
        abs(float(observed_position[index]) - position[index]) for index in range(3)
    )
    rotation_delta = max(
        abs(float(observed_axes[index]) - axes[index]) for index in range(6)
    )
    if position_delta > CAMERA_POSE_TOLERANCE or rotation_delta > CAMERA_POSE_TOLERANCE:
        raise _refuse(
            CAL_PROJECTION_EVIDENCE_CONTRADICTORY,
            f"the scene's camera pose at neck {pose_rad} differs from the sealed mount model by "
            f"{position_delta} m and {rotation_delta} in its axes: the projection would not be the sealed "
            f"camera's, so it is refused rather than preferred",
        )
    rotation = camera_rotation_matrix(axes)
    records = []
    rows = []
    in_frame = 0
    for point in points:
        u, v, inside = project_point(
            point_m=point,
            camera_position_m=position,
            camera_rotation=rotation,
            width=int(width),
            height=int(height),
            fovy_rad=float(contract.camera.fovy_rad),
        )
        if not math.isfinite(u) or not math.isfinite(v):
            raise _refuse(
                CAL_PROJECTION_POINT_UNPROJECTABLE,
                f"the workspace sample {list(point)} is not in front of the sealed camera at neck "
                f"{pose_rad}, so the workspace has no image-space extent there",
            )
        in_frame += int(bool(inside))
        rows.append(v)
        records.append(
            {
                "point_m": [float(value) for value in point],
                "u": float(u),
                "v": float(v),
                "in_frame": bool(inside),
                "pose_rad": float(pose_rad),
                "projection": PROJECTION_FUNCTION,
            }
        )
    if not in_frame:
        raise _refuse(
            CAL_PROJECTION_EMPTY,
            f"no workspace sample is inside the frame at neck {pose_rad}, so the pose contributes no "
            f"image-space extent",
        )
    raw_top, raw_bottom = min(rows), max(rows)
    top = max(0.0, raw_top)
    bottom = min(height, raw_bottom)
    if not top < bottom:
        raise _refuse(
            CAL_PROJECTION_EMPTY,
            f"the workspace projection at neck {pose_rad} spans the rows [{raw_top}, {raw_bottom}], which "
            f"is empty once clipped to the {height} px image",
        )
    return {
        "pose_rad": float(pose_rad),
        "top_px": float(top),
        "bottom_px": float(bottom),
        "raw_top_px": float(raw_top),
        "raw_bottom_px": float(raw_bottom),
        "clipped_to_image": bool(raw_top < 0.0 or raw_bottom > height),
        "u_min_px": min(record["u"] for record in records),
        "u_max_px": max(record["u"] for record in records),
        "projected_points": len(records),
        "in_frame_points": in_frame,
        "out_of_frame_points": len(records) - in_frame,
        "camera_pose": {
            "source": CAMERA_POSE_SOURCE,
            "position_m": [float(value) for value in position],
            "xyaxes": [float(value) for value in axes],
            "rotation": [list(row) for row in rotation],
            "scene_reading_max_position_delta_m": position_delta,
            "scene_reading_max_axes_delta": rotation_delta,
        },
        "points": records,
    }


def _aimed_projection(*, inputs) -> dict:
    """Every sample at its own sealed bearing: the band a horizontally centred sample occupies."""

    seal = inputs["seal"]
    contract = inputs["contract"]
    width = float(contract.image_width)
    height = float(contract.image_height)
    rows = []
    columns = []
    for point in inputs["points"]:
        bearing = sealed_bearing_rad(point, mount_origin_m=inputs["mount_origin_m"])
        position, axes = sealed_camera_pose(seal, bearing)
        u, v, inside = project_point(
            point_m=point,
            camera_position_m=position,
            camera_rotation=camera_rotation_matrix(axes),
            width=int(width),
            height=int(height),
            fovy_rad=float(contract.camera.fovy_rad),
        )
        if not math.isfinite(u) or not math.isfinite(v) or not inside:
            raise _refuse(
                CAL_PROJECTION_POINT_UNPROJECTABLE,
                f"the workspace sample {list(point)} is not projectable at its own bearing {bearing}, so "
                f"the aimed band cannot be recorded",
            )
        rows.append(v)
        columns.append(u)
    return {
        "rule": AIMED_RULE,
        "points": len(rows),
        "band_px": [float(min(rows)), float(max(rows))],
        "u_equals_width_over_two": all(abs(u - width / 2.0) <= 1e-6 for u in columns),
        "u_min_px": float(min(columns)),
        "u_max_px": float(max(columns)),
    }


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
