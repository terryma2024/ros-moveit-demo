"""Freeze a map from installed MuJoCo inputs and the accepted point selection."""

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import yaml

from .catalog import ANCHOR_IDS
from .projection import DEFAULT_PADDING_PX, MARKER_RADIUS_PX, Projection, marker_style, project_xy
from .service import ServiceConflict


_INSTALLED_INPUTS = {
    "execution_policy": "config/mujoco/headless_execution.yaml",
    "dynamic_policy": "config/policies/dynamic_cup_pick/v1/mujoco.yaml",
    "placement_policy": "config/policies/light_cup_wall_pick/v1/mujoco.yaml",
    "task_scene": "config/mujoco/task_scene.yaml",
    "scene": "assets/mujoco/scene.xml",
    "target_mesh": "assets/mujoco/assets/target_landing_tolerance_ring.obj",
    "anchors": "config/mujoco/rgbd_task_points.yaml",
}


def _digest(document):
    return hashlib.sha256(json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


def _paths(layout):
    share = Path(layout.demo_prefix) / "share/so101_demo_py"
    return {
        **{name: share / relative for name, relative in _INSTALLED_INPUTS.items()},
        "catalog": layout.points_path,
        "parallel_config": layout.parallel_config_path,
        "adaptive_config": layout.adaptive_config_path,
    }


def _read_inputs(layout):
    result = {}
    for name, path in _paths(layout).items():
        path = Path(path)
        if not path.is_absolute() or any(parent.is_symlink() for parent in (path, *path.parents)):
            raise ServiceConflict("VALIDATION_MANIFEST_INPUT_INVALID")
        try:
            if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
                raise ServiceConflict("VALIDATION_MANIFEST_INPUT_INVALID")
            result[name] = path.read_bytes()
        except OSError as error:
            raise ServiceConflict("VALIDATION_MANIFEST_INPUT_INVALID") from error
    return result


def _identity(layout, inputs):
    return {
        "source_commit": layout.source_commit,
        "sampler_id": "ai_station_baseline_v1",
        "sampler_version": 1,
        "source_hashes": {name: hashlib.sha256(raw).hexdigest() for name, raw in inputs.items()},
    }


def current_manifest_source_hash(layout):
    """Unavailable installed inputs make old manifests stale, not unreadable."""
    try:
        return _digest(_identity(layout, _read_inputs(layout)))
    except ServiceConflict:
        return _digest({"installed_inputs_unavailable": True})


def _element(parent, path):
    value = parent.find(path)
    if value is None:
        raise ValueError("missing scene element")
    return value


def _finite(values, length):
    if len(values) != length or any(isinstance(value, bool) for value in values):
        raise ValueError("coordinate shape")
    result = tuple(float(value) for value in values)
    if not all(math.isfinite(value) for value in result):
        raise ValueError("non-finite coordinate")
    return result


def _xyz(element, attribute):
    return _finite(element.get(attribute, "").split(), 3)


def _box(world, body_name, geom_name):
    body = _element(world, f"body[@name='{body_name}']")
    geom = _element(body, f"geom[@name='{geom_name}']")
    if geom.get("type") != "box" or any(
        value.get(attribute) is not None
        for value in (body, geom) for attribute in ("quat", "euler", "axisangle", "xyaxes", "zaxis")
    ) or geom.get("pos") is not None:
        raise ValueError("unsupported transformed box")
    x, y, _ = _xyz(body, "pos")
    sx, sy, sz = _xyz(geom, "size")
    if min(sx, sy, sz) <= 0:
        raise ValueError("invalid box size")
    return tuple(round(value, 12) for value in (x - sx, x + sx, y - sy, y + sy))


def _geometry(inputs, selection):
    scene = ET.fromstring(inputs["scene"])
    world = _element(scene, "worldbody")
    table = _element(world, "body[@name='table']")
    table_position = _xyz(table, "pos")
    target_position = _xyz(_element(table, "geom[@name='target_landing_tolerance_ring']"), "pos")
    target_center = tuple(round(table_position[i] + target_position[i], 12) for i in (0, 1))
    bottom = _element(world, "body[@name='plastic_cup']/geom[@name='bottom_collision']")
    cup_radius, half_height = _finite(bottom.get("size", "").split(), 2)
    if bottom.get("type") != "cylinder" or min(cup_radius, half_height) <= 0:
        raise ValueError("cup footprint")
    mesh = _element(scene, "asset/mesh[@name='target_landing_tolerance_ring']")
    if mesh.get("file") != "assets/target_landing_tolerance_ring.obj" or mesh.get("scale") is not None:
        raise ValueError("unbound target mesh")
    radii = [math.hypot(*_finite(line[2:].split(), 3)[:2])
             for line in inputs["target_mesh"].decode("utf-8").splitlines() if line.startswith("v ")]
    if not radii:
        raise ValueError("empty target mesh")
    policy = yaml.safe_load(inputs["placement_policy"])
    region = policy["physical_outcome"]["final_target_region"]
    lower, upper = _finite(region["min_xy_m"], 2), _finite(region["max_xy_m"], 2)
    tolerance = round((upper[0] - lower[0]) / 2, 12)
    if region["kind"] != "axis_aligned_box" or tolerance <= 0 or not all(
        math.isclose(observed, expected, rel_tol=0, abs_tol=1e-12)
        for observed, expected in (
            ((upper[1] - lower[1]) / 2, tolerance),
            (min(radii) - cup_radius, tolerance),
            *((target_center[i], (lower[i] + upper[i]) / 2) for i in (0, 1)),
        )
    ):
        raise ValueError("scene/policy target mismatch")
    anchors = yaml.safe_load(inputs["anchors"])["points"]
    if tuple(point["id"] for point in anchors) != ANCHOR_IDS or any(
        tuple(anchor["cup_position_world_m"]) != point.position_world_m
        for anchor, point in zip(anchors, selection.points[:4])
    ):
        raise ValueError("anchor mismatch")
    geometry = {
        "table_bounds": _box(world, "table", "table_visual"),
        "base_bounds": _box(world, "base_pedestal", "base_pedestal_visual"),
        "target_center": target_center,
        "target_bounds": (lower[0], upper[0], lower[1], upper[1]),
        "candidate_bounds": (-0.045, 0.080, -0.340, -0.240),
        "cup_radius_m": cup_radius,
        "target_tolerance_radius_m": tolerance,
    }
    xmin, xmax, ymin, ymax = geometry["table_bounds"]
    for index, point in enumerate(selection.points):
        x, y, _ = _finite(point.position_world_m, 3)
        clearance = cup_radius + 0.010
        if not (xmin + clearance <= x <= xmax - clearance and ymin + clearance <= y <= ymax - clearance):
            raise ValueError("point edge clearance")
        if any(math.hypot(x - other.position_world_m[0], y - other.position_world_m[1]) < 0.015
               for other in selection.points[:index]):
            raise ValueError("point separation")
    return geometry


def freeze_manifest_context(layout, selection):
    inputs = _read_inputs(layout)
    identity = _identity(layout, inputs)
    if identity["source_hashes"]["catalog"] != selection.catalog_sha256:
        raise ServiceConflict("VALIDATION_MANIFEST_CATALOG_MISMATCH")
    try:
        geometry = _geometry(inputs, selection)
        projection = Projection.from_geometry(geometry, 1200, 900)
    except (ValueError, TypeError, KeyError, IndexError, ET.ParseError, yaml.YAMLError) as error:
        raise ServiceConflict("VALIDATION_MANIFEST_GEOMETRY_INVALID") from error
    top_view = {
        "projection": {**asdict(projection), "padding_px": DEFAULT_PADDING_PX},
        "geometry": geometry,
        "points": [{"id": point.id, "display_id": point.display_id,
                    "position_world_m": point.position_world_m,
                    "projected_px": project_xy(projection, *point.position_world_m[:2])}
                   for point in selection.points],
        "cup_footprint_radius_px": geometry["cup_radius_m"] * projection.pixels_per_m,
        "target_tolerance_radius_px": geometry["target_tolerance_radius_m"] * projection.pixels_per_m,
        "marker_radius_px": MARKER_RADIUS_PX,
        "palette": {},
    }
    for color, state in (("blue", "ELIGIBLE_UNRUN"), ("green", "PASSED"), ("red", "FAILED")):
        style = marker_style(state)
        top_view["palette"][color] = {"stroke": style.stroke, "fill": style.fill, "icon": style.icon}
    source_hash = _digest(identity)
    if current_manifest_source_hash(layout) != source_hash:
        raise ServiceConflict("VALIDATION_MANIFEST_INPUT_CHANGED")
    return {**identity, "geometry_sha256": _digest(geometry), "top_view": top_view}, source_hash
