"""Tilt-compensated place height (design `2026-10-09-teacher-tilt-compensated-place-height`).

The held cup carries a small tilt, so a point of its round bottom rim touches the table before the arm has finished the descent.
The DESCEND_TO_PLACE target is therefore computed from the measured tilt: the arm is aimed to end a small guard below first
contact instead of continuing through it.

Pure and standalone: no ROS, no MuJoCo import. The cup bottom of the ACT scene is a round cylinder (``bottom_collision``, radius
0.040 m, half thickness 0.001 m, centred 0.044 m below the body origin), so for a tilt theta the lowest point is a point of the
bottom rim in the direction of the tilt, whatever the azimuth, and the body origin is then at

    z_touch(theta) = z_table + c * cos(theta) + r * sin(theta)       c = 0.045 m (origin to the bottom face), r = 0.040 m

The wall corners (radius 0.0413 m at z -0.043 m) become the lowest points only above about 57 degrees; ``lowest_point_height`` is
the exact general form and the tests compare the two.
"""

from __future__ import annotations

import hashlib
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

#: codes of a failed measurement (``PlaceHeightRefused``); the Teacher turns them into a closed fallback reason, it never stops for them
TILT_UNSTABLE = "TEACHER_PLACE_TILT_UNSTABLE"
TILT_OUT_OF_RANGE = "TEACHER_PLACE_TILT_OUT_OF_RANGE"
HEIGHT_OUT_OF_BOUNDS = "TEACHER_PLACE_HEIGHT_OUT_OF_BOUNDS"
#: a measurement or geometry step that failed for a reason other than an unstable tilt (scene parse error, no cup body, stale or
#: missing joint state, dynamic evidence timeout)
MEASUREMENT_FAILED = "TEACHER_PLACE_MEASUREMENT_FAILED"
REFUSAL_CODES = (TILT_UNSTABLE, TILT_OUT_OF_RANGE, HEIGHT_OUT_OF_BOUNDS, MEASUREMENT_FAILED)
MODE = "tilt_compensated"
#: the guard must be strictly positive: the cup margin is 0, so a target at or above first contact (guard <= 0) leaves the cup without table
#: contact, `actual_table_support` fails and the run ends in DYNAMIC_RELEASE_SUPPORT_NOT_PROVED
#: the offline sweep chatters at 0.1 mm (33 of 70 trials) and only reaches the compression limit from 0.35 mm: the EFFECTIVE guard
#: (guard minus the k half band, the worst case of the measured grasp offset) must stay inside [0.35 mm, 1.0 mm]
GUARD_MIN_M = 3.5e-4
GUARD_MAX_M = 1e-3
EFFECTIVE_GUARD_TOLERANCE_M = 1e-9
K_HALF_BAND_MIN_M = 3e-4
#: the stability window the tilt is measured in: this long, with a tilt range under this
STABILITY_WINDOW_S = 0.100
STABILITY_RANGE_RAD = math.radians(0.05)
STABILITY_TIMEOUT_S = 1.0


class PlaceHeightRefused(RuntimeError):
    """A refusal with a stable code; the message starts with it (``CODE: detail``)."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


@dataclass(frozen=True, slots=True)
class CupGeometry:
    table_top_z_m: float
    half_height_m: float          # c: body origin to the bottom face
    rim_radius_m: float           # r: radius of the round bottom
    wall_corner_radius_m: float
    wall_corner_z_m: float        # relative to the body origin
    scene_sha256: str


def cup_geometry_from_scene(scene_path) -> CupGeometry:
    """The geometry the formula uses, read from the frozen scene file (and its hash), not hard-coded."""
    raw = Path(scene_path).read_bytes()
    root = ET.fromstring(raw)
    cup = next(b for b in root.iter("body") if b.get("name") == "plastic_cup")
    bottom = next(g for g in cup.iter("geom") if g.get("name") == "bottom_collision")
    if bottom.get("type") != "cylinder":
        raise ValueError("PLACE_GEOMETRY: the cup bottom is not a cylinder")
    radius, half_thickness = (float(v) for v in bottom.get("size").split()[:2])
    centre_z = float(bottom.get("pos").split()[2])
    table = next(b for b in root.iter("body") if b.get("name") == "table")
    table_geom = next(g for g in table.iter("geom") if g.get("name") == "table_collision")
    table_top = float(table.get("pos").split()[2]) + float(table_geom.get("size").split()[2])
    wall = next(g for g in cup.iter("geom") if g.get("name") == "wall_near_collision")
    half_width, half_depth, half_h = (float(v) for v in wall.get("size").split())
    wall_y, wall_z = float(wall.get("pos").split()[1]), float(wall.get("pos").split()[2])
    outer = wall_y + half_depth
    return CupGeometry(
        table_top_z_m=table_top, half_height_m=-(centre_z - half_thickness), rim_radius_m=radius,
        wall_corner_radius_m=math.hypot(outer, half_width), wall_corner_z_m=wall_z - half_h,
        scene_sha256=hashlib.sha256(raw).hexdigest())


def touch_center_z(theta_rad: float, geometry: CupGeometry) -> float:
    """z of the cup body origin at first table contact for a tilt theta: z_table + c cos(theta) + r sin(theta)."""
    return (geometry.table_top_z_m + geometry.half_height_m * math.cos(theta_rad)
            + geometry.rim_radius_m * math.sin(theta_rad))


def lowest_point_height(theta_rad: float, geometry: CupGeometry) -> float:
    """The exact origin height at first contact over the bottom rim and the wall corners (the larger of the two)."""
    rim = geometry.half_height_m * math.cos(theta_rad) + geometry.rim_radius_m * math.sin(theta_rad)
    corner = (-geometry.wall_corner_z_m * math.cos(theta_rad) + geometry.wall_corner_radius_m * math.sin(theta_rad))
    return geometry.table_top_z_m + max(rim, corner)


@dataclass(frozen=True, slots=True)
class PlaceHeightPolicy:
    guard_m: float
    tracking_offset_m: float
    tilt_min_rad: float
    tilt_max_rad: float
    grasp_offset_m: float
    grasp_offset_half_band_m: float
    max_deviation_m: float
    scene_sha256: str
    reference_offset_m: float = -0.01325

    @classmethod
    def from_document(cls, document: dict) -> "PlaceHeightPolicy":
        """The closed policy fields (already validated by the policy loader); re-checked here so the module stands alone."""
        policy = cls(
            guard_m=float(document["place_touchdown_guard_m"]),
            tracking_offset_m=float(document["place_tracking_offset_m"]),
            tilt_min_rad=float(document["place_tilt_min_rad"]), tilt_max_rad=float(document["place_tilt_max_rad"]),
            grasp_offset_m=float(document["place_grasp_offset_m"]),
            grasp_offset_half_band_m=float(document["place_grasp_offset_half_band_m"]),
            max_deviation_m=float(document["place_target_max_deviation_m"]),
            scene_sha256=str(document["place_geometry_scene_sha256"]),
            reference_offset_m=float(document["place_reference_offset_m"]))
        policy.validate()
        return policy

    def validate(self) -> None:
        finite = (self.guard_m, self.tracking_offset_m, self.tilt_min_rad, self.tilt_max_rad, self.grasp_offset_m,
                  self.grasp_offset_half_band_m, self.max_deviation_m, self.reference_offset_m)
        if not all(math.isfinite(v) for v in finite):
            raise ValueError("place height policy: a value is not finite")
        if not GUARD_MIN_M <= self.guard_m <= GUARD_MAX_M:
            raise ValueError(f"place height policy: place_touchdown_guard_m must be within [{GUARD_MIN_M}, {GUARD_MAX_M}]")
        if (self.guard_m - self.grasp_offset_half_band_m < GUARD_MIN_M - EFFECTIVE_GUARD_TOLERANCE_M
                or self.guard_m + self.grasp_offset_half_band_m > GUARD_MAX_M + EFFECTIVE_GUARD_TOLERANCE_M):
            raise ValueError("place height policy: the effective guard (guard -/+ the k half band) must stay within "
                             f"[{GUARD_MIN_M}, {GUARD_MAX_M}]")
        if not 0.0 <= self.tracking_offset_m <= 1e-3:
            raise ValueError("place height policy: place_tracking_offset_m must be within [0, 0.001]")
        if not 0.0 < self.tilt_min_rad < self.tilt_max_rad <= 0.2:
            raise ValueError("place height policy: the tilt range must satisfy 0 < min < max <= 0.2 rad")
        if not 0.0 < self.grasp_offset_m < 0.1 or not K_HALF_BAND_MIN_M <= self.grasp_offset_half_band_m <= 2e-3:
            raise ValueError("place height policy: the grasp offset or its band is out of range")
        if not -0.05 <= self.reference_offset_m <= 0.05:
            raise ValueError("place height policy: place_reference_offset_m must be within 0.05 m")
        if not 0.0 < self.max_deviation_m <= 0.005:
            raise ValueError("place height policy: place_target_max_deviation_m must be within (0, 0.005]")
        if len(self.scene_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.scene_sha256):
            raise ValueError("place height policy: place_geometry_scene_sha256 is not a sha256")


def target_tcp_z(theta_rad: float, k_m: float, geometry: CupGeometry, policy: PlaceHeightPolicy) -> float:
    """The commanded TCP z of DESCEND_TO_PLACE: z_touch(theta) + k + tracking offset - guard.

    ``k`` is the actual TCP height above the cup body origin (forward kinematics of the actual joints, sag included) measured at
    the same instant as theta; the tracking offset is the calibrated difference between the commanded and the actual TCP z at the
    end of the descent (0.16 mm), so that the ACTUAL arm ends ``guard`` past (below) the first-contact pose."""
    return touch_center_z(theta_rad, geometry) + k_m + policy.tracking_offset_m - policy.guard_m


def _check_compensated(document, policy: PlaceHeightPolicy | None) -> None:
    """QC side (ValueError): a tilt-compensated record is the formula applied to its own recorded measurement, within every bound.

    With the frozen ``policy`` the guard, the tracking offset, the scene hash, the tilt range, the k band and the deviation bound
    are checked against it as well."""
    try:
        geometry = document["geometry"]
        theta, k, target, guard, tracking, old = (float(document[key]) for key in (
            "tilt_rad", "grasp_offset_m", "target_tcp_z_m", "guard_m", "tracking_offset_m", "constant_offset_target_tcp_z_m"))
        recomputed = (geometry["table_top_z_m"] + geometry["half_height_m"] * math.cos(theta)
                      + geometry["rim_radius_m"] * math.sin(theta) + k + tracking - guard)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PLACE_HEIGHT: fields") from error
    if (not all(math.isfinite(v) for v in (theta, k, target, guard, tracking, old, recomputed))
            or abs(recomputed - target) > 1e-9 or not GUARD_MIN_M <= guard <= GUARD_MAX_M):
        raise ValueError("PLACE_HEIGHT: values")
    if policy is not None and (
            guard != policy.guard_m or tracking != policy.tracking_offset_m or document.get("scene_sha256") != policy.scene_sha256
            or not policy.tilt_min_rad <= theta <= policy.tilt_max_rad
            or abs(k - policy.grasp_offset_m) > policy.grasp_offset_half_band_m
            or abs(target - old) > policy.max_deviation_m):
        raise ValueError("PLACE_HEIGHT: policy")


# ---- the tilt-compensated target is a strategy with a closed fallback, never a refusal ------------------------------
#: the closed set of reasons for which the Teacher uses the reference target (hover z + the reference offset) instead of the tilt-compensated one
RECORD_SCHEMA = "teacher_place_height"
MODE_FALLBACK = "fallback_reference"
FB_TILT_UNSTABLE = "TILT_UNSTABLE"                  # no stable window in 1 s
FB_TILT_OUT_OF_RANGE = "TILT_OUT_OF_RANGE"          # outside the calibrated range (or not finite)
FB_K_OUT_OF_BAND = "K_OUT_OF_BAND"                  # k outside its band
FB_TARGET_DEVIATION = "TARGET_DEVIATION"            # more than max_deviation_m from the reference target (or outside the workspace)
FB_JOINT_STATE_STALE = "JOINT_STATE_STALE"          # the joint state k needs is older than state_max_age_s
FB_SCENE_HASH_MISMATCH = "SCENE_HASH_MISMATCH"      # the scene is not the one the geometry was fitted for
FB_MEASUREMENT_FAILED = "MEASUREMENT_FAILED"        # geometry or timeout
FALLBACK_REASONS = (FB_TILT_UNSTABLE, FB_TILT_OUT_OF_RANGE, FB_K_OUT_OF_BAND, FB_TARGET_DEVIATION, FB_JOINT_STATE_STALE,
                    FB_SCENE_HASH_MISMATCH, FB_MEASUREMENT_FAILED)
RECORD_KEYS = frozenset({
    "schema", "mode", "fallback_reason", "detail", "tilt_rad", "grasp_offset_m", "touch_center_z_m", "guard_m", "tracking_offset_m",
    "target_tcp_z_m", "constant_offset_target_tcp_z_m", "computed_target_tcp_z_m", "scene_sha256", "geometry"})


def _record(mode, reason, detail, *, policy, old_target_z_m, target_z_m, geometry=None, theta=None, k=None, computed=None,
               scene_sha256=None) -> dict:
    return {
        "schema": RECORD_SCHEMA, "mode": mode, "fallback_reason": reason, "detail": str(detail)[:300],
        "tilt_rad": theta, "grasp_offset_m": k,
        "touch_center_z_m": None if geometry is None or theta is None or not math.isfinite(theta) else touch_center_z(theta, geometry),
        "guard_m": policy.guard_m, "tracking_offset_m": policy.tracking_offset_m, "target_tcp_z_m": target_z_m,
        "constant_offset_target_tcp_z_m": old_target_z_m, "computed_target_tcp_z_m": computed,
        "scene_sha256": scene_sha256 if scene_sha256 is not None else (None if geometry is None else geometry.scene_sha256),
        "geometry": None if geometry is None else {
            "table_top_z_m": geometry.table_top_z_m, "half_height_m": geometry.half_height_m,
            "rim_radius_m": geometry.rim_radius_m}}


def fallback_record(reason: str, old_target_z_m: float, policy: PlaceHeightPolicy, *, detail: str = "", geometry=None,
                    theta=None, k=None, computed=None) -> dict:
    """The record of a fallback: the target used is the reference target (`old_target_z_m`), the measurements so far are kept."""
    if reason not in FALLBACK_REASONS:
        raise ValueError("PLACE_HEIGHT: fallback reason")
    return _record(MODE_FALLBACK, reason, detail, policy=policy, old_target_z_m=old_target_z_m, target_z_m=old_target_z_m,
                      geometry=geometry, theta=theta, k=k, computed=computed)


def plan_place_height(theta_rad: float, k_m: float, old_target_z_m: float, geometry: CupGeometry, policy: PlaceHeightPolicy,
                         workspace_z_range=(0.0, 1.0)) -> dict:
    """The record of one measurement: tilt-compensated inside every calibrated bound, else the fallback with the first failing
    reason (scene, tilt, k, deviation). Never raises for a bound."""
    if geometry.scene_sha256 != policy.scene_sha256:
        return fallback_record(FB_SCENE_HASH_MISMATCH, old_target_z_m, policy, geometry=geometry, theta=theta_rad, k=k_m,
                               detail="the scene model is not the one the place geometry was fitted for")
    if not (math.isfinite(theta_rad) and math.isfinite(k_m)) or not policy.tilt_min_rad <= theta_rad <= policy.tilt_max_rad:
        return fallback_record(FB_TILT_OUT_OF_RANGE, old_target_z_m, policy, geometry=geometry,
                               theta=theta_rad if math.isfinite(theta_rad) else None, k=k_m if math.isfinite(k_m) else None,
                               detail=f"tilt {math.degrees(theta_rad):.3f} deg outside {math.degrees(policy.tilt_min_rad):.2f}-"
                                      f"{math.degrees(policy.tilt_max_rad):.2f} deg")
    if abs(k_m - policy.grasp_offset_m) > policy.grasp_offset_half_band_m:
        return fallback_record(FB_K_OUT_OF_BAND, old_target_z_m, policy, geometry=geometry, theta=theta_rad, k=k_m,
                               detail=f"grasp offset {k_m:.6f} m outside {policy.grasp_offset_m:.6f} +- {policy.grasp_offset_half_band_m:.6f} m")
    target = target_tcp_z(theta_rad, k_m, geometry, policy)
    if abs(target - old_target_z_m) > policy.max_deviation_m or not workspace_z_range[0] <= target <= workspace_z_range[1]:
        return fallback_record(FB_TARGET_DEVIATION, old_target_z_m, policy, geometry=geometry, theta=theta_rad, k=k_m, computed=target,
                               detail=f"target z {target:.6f} m is {abs(target - old_target_z_m) * 1000:.3f} mm from the reference target "
                                      f"(limit {policy.max_deviation_m * 1000:.1f} mm) or outside the workspace")
    return _record(MODE, None, "", policy=policy, old_target_z_m=old_target_z_m, target_z_m=target, geometry=geometry,
                      theta=theta_rad, k=k_m, computed=target)


def validate_document(document, policy: PlaceHeightPolicy | None = None, *, workspace_z_range=(0.0, 1.0)) -> None:
    """QC side (ValueError) for a `teacher_place_height` record.

    ``tilt_compensated``: the recomputation of the formula from the recorded measurement, within every bound of the frozen policy.
    ``fallback_reference``: a reason of the closed enum, a target equal to the reference target, and (with the policy) a reason that
    the recorded measurement actually shows for tilt, k, deviation and scene hash. The other reasons carry no measurement to check."""
    if type(document) is not dict or document.get("schema") != RECORD_SCHEMA or set(document) != RECORD_KEYS:
        raise ValueError("PLACE_HEIGHT: schema")
    mode, reason = document["mode"], document["fallback_reason"]
    if mode == MODE:
        if reason is not None:
            raise ValueError("PLACE_HEIGHT: fallback reason on a compensated record")
        if any(document[key] is None for key in ("tilt_rad", "grasp_offset_m", "geometry", "scene_sha256")):
            raise ValueError("PLACE_HEIGHT: fields")
        _check_compensated(document, policy)
        return
    if mode != MODE_FALLBACK or reason not in FALLBACK_REASONS:
        raise ValueError("PLACE_HEIGHT: mode")
    try:
        target, old = float(document["target_tcp_z_m"]), float(document["constant_offset_target_tcp_z_m"])
    except (TypeError, ValueError) as error:
        raise ValueError("PLACE_HEIGHT: fields") from error
    if not (math.isfinite(target) and math.isfinite(old)) or abs(target - old) > 1e-9:
        raise ValueError("PLACE_HEIGHT: the fallback target is not the reference target")
    if policy is None:
        return
    if document["guard_m"] != policy.guard_m or document["tracking_offset_m"] != policy.tracking_offset_m:
        raise ValueError("PLACE_HEIGHT: policy")
    theta, k = document["tilt_rad"], document["grasp_offset_m"]

    def number(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

    if reason == FB_SCENE_HASH_MISMATCH and document["scene_sha256"] == policy.scene_sha256:
        raise ValueError("PLACE_HEIGHT: scene hash reason without a mismatch")
    if reason == FB_TILT_OUT_OF_RANGE and number(theta) and policy.tilt_min_rad <= theta <= policy.tilt_max_rad:
        raise ValueError("PLACE_HEIGHT: tilt reason with the tilt in range")
    if reason == FB_K_OUT_OF_BAND and (not number(k) or abs(k - policy.grasp_offset_m) <= policy.grasp_offset_half_band_m):
        raise ValueError("PLACE_HEIGHT: k reason with k in band")
    if reason == FB_TARGET_DEVIATION:
        computed = document["computed_target_tcp_z_m"]
        if not number(computed) or (abs(computed - old) <= policy.max_deviation_m
                                    and workspace_z_range[0] <= computed <= workspace_z_range[1]):
            raise ValueError("PLACE_HEIGHT: deviation reason within the bound")
