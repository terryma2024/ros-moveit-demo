#!/usr/bin/env python3
"""Generate the deterministic SO-101 MoveIt expert position map and manifests."""

from __future__ import annotations

import argparse
import csv
import html
import math
import random
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import NamedTuple, Sequence

import yaml


DEFAULT_SEED = 20260911
DEFAULT_Z_M = 0.165
MIN_SEPARATION_M = 0.035
EDGE_MARGIN_M = 0.010
STRATUM_GAP_M = 0.010
CANDIDATE_COUNT = 20

SCENE_PATH = Path("src/so101_demo_py/assets/mujoco/scene.xml")
ANCHOR_PATH = Path("src/so101_demo_py/config/mujoco/rgbd_task_points.yaml")
TARGET_POLICY_PATH = Path(
    "src/so101_demo_py/config/policies/light_cup_wall_pick/v1/mujoco.yaml"
)

QUOTAS = (
    ("near", "left", 2),
    ("near", "center", 2),
    ("near", "right", 2),
    ("mid", "left", 2),
    ("mid", "center", 1),
    ("mid", "right", 2),
    ("far", "left", 2),
    ("far", "center", 1),
    ("far", "right", 2),
)

DISTANCE_ZH = {"near": "近", "mid": "中", "far": "远"}
LATERAL_ZH = {"left": "左", "center": "中", "right": "右"}


class Geometry(NamedTuple):
    table_bounds: tuple[float, float, float, float]
    base_bounds: tuple[float, float, float, float]
    target_center: tuple[float, float]
    target_bounds: tuple[float, float, float, float]
    cup_radius_m: float
    target_tolerance_radius_m: float


class Point(NamedTuple):
    id: str
    name: str
    source: str
    stratum: str
    x_m: float
    y_m: float
    z_m: float


def parse_xyz(value: str, *, field: str) -> tuple[float, float, float]:
    parts = tuple(float(part) for part in value.split())
    if len(parts) != 3 or not all(math.isfinite(part) for part in parts):
        raise ValueError(f"{field} must contain three finite values")
    return parts


def require_element(parent: ET.Element, path: str) -> ET.Element:
    element = parent.find(path)
    if element is None:
        raise ValueError(f"required MuJoCo element is missing: {path}")
    return element


def body_box_bounds(
    worldbody: ET.Element,
    *,
    body_name: str,
    geom_name: str,
) -> tuple[float, float, float, float]:
    body = require_element(worldbody, f"body[@name='{body_name}']")
    geom = require_element(body, f"geom[@name='{geom_name}']")
    if geom.get("type") != "box":
        raise ValueError(f"{geom_name} must remain a MuJoCo box")
    body_pos = parse_xyz(body.get("pos", ""), field=f"{body_name}.pos")
    half_size = parse_xyz(geom.get("size", ""), field=f"{geom_name}.size")
    return (
        round(body_pos[0] - half_size[0], 12),
        round(body_pos[0] + half_size[0], 12),
        round(body_pos[1] - half_size[1], 12),
        round(body_pos[1] + half_size[1], 12),
    )


def mesh_radial_bounds(mesh_path: Path) -> tuple[float, float]:
    radii = []
    for line in mesh_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("v "):
            continue
        x_m, y_m, _z_m = parse_xyz(line[2:], field=f"{mesh_path.name} vertex")
        radii.append(math.hypot(x_m, y_m))
    if not radii:
        raise ValueError(f"target tolerance mesh has no vertices: {mesh_path}")
    return min(radii), max(radii)


def load_geometry(repository_root: Path) -> Geometry:
    scene = ET.parse(repository_root / SCENE_PATH).getroot()
    worldbody = require_element(scene, "worldbody")
    table_bounds = body_box_bounds(
        worldbody,
        body_name="table",
        geom_name="table_visual",
    )
    base_bounds = body_box_bounds(
        worldbody,
        body_name="base_pedestal",
        geom_name="base_pedestal_visual",
    )

    table = require_element(worldbody, "body[@name='table']")
    table_pos = parse_xyz(table.get("pos", ""), field="table.pos")
    target_geom = require_element(
        table,
        "geom[@name='target_landing_tolerance_ring']",
    )
    target_local = parse_xyz(
        target_geom.get("pos", ""),
        field="target_landing_tolerance_ring.pos",
    )
    target_center = (
        round(table_pos[0] + target_local[0], 12),
        round(table_pos[1] + target_local[1], 12),
    )

    cup = require_element(worldbody, "body[@name='plastic_cup']")
    cup_bottom = require_element(cup, "geom[@name='bottom_collision']")
    cup_size = tuple(float(part) for part in cup_bottom.get("size", "").split())
    if cup_bottom.get("type") != "cylinder" or len(cup_size) != 2:
        raise ValueError("plastic_cup bottom_collision must remain a MuJoCo cylinder")
    cup_radius_m = cup_size[0]

    target_mesh = require_element(
        scene,
        "asset/mesh[@name='target_landing_tolerance_ring']",
    )
    mesh_file = target_mesh.get("file")
    if not mesh_file:
        raise ValueError("target_landing_tolerance_ring mesh file is missing")
    mesh_path = repository_root / SCENE_PATH.parent / mesh_file
    target_ring_inner_radius_m, _target_ring_outer_radius_m = mesh_radial_bounds(
        mesh_path
    )
    target_ring_clearance_m = round(
        target_ring_inner_radius_m - cup_radius_m,
        12,
    )
    if target_ring_clearance_m <= 0.0:
        raise ValueError("target ring must be larger than the cup footprint")

    policy = yaml.safe_load((repository_root / TARGET_POLICY_PATH).read_text(encoding="utf-8"))
    region = policy["physical_outcome"]["final_target_region"]
    if region.get("kind") != "axis_aligned_box":
        raise ValueError("final target region must remain an axis-aligned box")
    min_xy = tuple(float(value) for value in region["min_xy_m"])
    max_xy = tuple(float(value) for value in region["max_xy_m"])
    if len(min_xy) != 2 or len(max_xy) != 2:
        raise ValueError("final target region must contain two XY bounds")
    target_bounds = (min_xy[0], max_xy[0], min_xy[1], max_xy[1])
    policy_half_extents = (
        (max_xy[0] - min_xy[0]) / 2.0,
        (max_xy[1] - min_xy[1]) / 2.0,
    )
    target_tolerance_radius_m = round(policy_half_extents[0], 12)
    if not all(
        math.isclose(extent, target_tolerance_radius_m, abs_tol=1e-12)
        for extent in (*policy_half_extents, target_ring_clearance_m)
    ):
        raise ValueError("target ring clearance and policy target tolerance disagree")
    expected_center = (
        (min_xy[0] + max_xy[0]) / 2.0,
        (min_xy[1] + max_xy[1]) / 2.0,
    )
    if not all(
        math.isclose(observed, expected, abs_tol=1e-12)
        for observed, expected in zip(target_center, expected_center)
    ):
        raise ValueError(
            "scene target center and policy target acceptance center disagree"
        )

    return Geometry(
        table_bounds=table_bounds,
        base_bounds=base_bounds,
        target_center=target_center,
        target_bounds=target_bounds,
        cup_radius_m=cup_radius_m,
        target_tolerance_radius_m=target_tolerance_radius_m,
    )


def load_anchors(repository_root: Path) -> list[Point]:
    payload = yaml.safe_load((repository_root / ANCHOR_PATH).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or len(payload.get("points", ())) != 4:
        raise ValueError("canonical RGB-D task-point file must contain four schema-v1 anchors")

    anchors = []
    for index, raw in enumerate(payload["points"], start=1):
        position = tuple(float(value) for value in raw["cup_position_world_m"])
        if len(position) != 3 or not all(math.isfinite(value) for value in position):
            raise ValueError(f"anchor {raw.get('id')} has an invalid world position")
        anchors.append(
            Point(
                id=f"P{index:02d}",
                name=str(raw["id"]),
                source="existing",
                stratum="anchor",
                x_m=position[0],
                y_m=position[1],
                z_m=position[2],
            )
        )
    return anchors


def sample_bounds(geometry: Geometry) -> tuple[float, float, float, float]:
    table_xmin, table_xmax, table_ymin, _table_ymax = geometry.table_bounds
    _base_xmin, _base_xmax, base_ymin, _base_ymax = geometry.base_bounds
    clearance = geometry.cup_radius_m + EDGE_MARGIN_M
    return (
        table_xmin + clearance,
        table_xmax - clearance,
        table_ymin + clearance,
        base_ymin - clearance,
    )


def split_three(
    low: float,
    high: float,
    labels: Sequence[str],
) -> dict[str, tuple[float, float]]:
    first = low + (high - low) / 3.0
    second = low + 2.0 * (high - low) / 3.0
    half_gap = STRATUM_GAP_M / 2.0
    bounds = (
        (low, round(first - half_gap, 6)),
        (round(first + half_gap, 6), round(second - half_gap, 6)),
        (round(second + half_gap, 6), high),
    )
    return dict(zip(labels, bounds))


def stratum_bounds(
    geometry: Geometry,
) -> tuple[dict[str, tuple[float, float]], dict[str, tuple[float, float]]]:
    xmin, xmax, ymin, ymax = sample_bounds(geometry)
    x_bins = split_three(xmin, xmax, ("left", "center", "right"))
    y_bins = split_three(ymin, ymax, ("far", "mid", "near"))
    return x_bins, y_bins


def generate_positions(
    anchors: Sequence[Point],
    geometry: Geometry,
    *,
    seed: int = DEFAULT_SEED,
) -> list[Point]:
    if len(anchors) != 4:
        raise ValueError("exactly four canonical anchors are required")
    x_bins, y_bins = stratum_bounds(geometry)
    rng = random.Random(seed)
    points = list(anchors)
    xy = [(point.x_m, point.y_m) for point in points]
    next_index = len(points) + 1

    for distance, lateral, count in QUOTAS:
        for _ in range(count):
            for _attempt in range(10_000):
                x_m = round(rng.uniform(*x_bins[lateral]), 6)
                y_m = round(rng.uniform(*y_bins[distance]), 6)
                if min(math.dist((x_m, y_m), prior) for prior in xy) >= MIN_SEPARATION_M:
                    break
            else:
                raise RuntimeError(f"unable to fill stratum {distance}/{lateral}")
            points.append(
                Point(
                    id=f"P{next_index:02d}",
                    name=f"generated_{distance}_{lateral}_{next_index:02d}",
                    source="generated",
                    stratum=f"{distance}-{lateral}",
                    x_m=x_m,
                    y_m=y_m,
                    z_m=anchors[0].z_m,
                )
            )
            xy.append((x_m, y_m))
            next_index += 1
    return points


def validate(points: Sequence[Point], geometry: Geometry) -> float:
    if len(points) != CANDIDATE_COUNT:
        raise ValueError(f"expected {CANDIDATE_COUNT} positions, got {len(points)}")
    if [point.id for point in points] != [f"P{index:02d}" for index in range(1, 21)]:
        raise ValueError("position display IDs must be consecutive P01 through P20")
    if len({point.name for point in points}) != len(points):
        raise ValueError("position manifest IDs must be unique")
    if len({(point.x_m, point.y_m, point.z_m) for point in points}) != len(points):
        raise ValueError("position coordinates must be unique")
    if sum(point.source == "existing" for point in points) != 4:
        raise ValueError("the first four points must be canonical anchors")
    if sum(point.source == "generated" for point in points) != 16:
        raise ValueError("exactly 16 generated points are required")

    xmin, xmax, ymin, ymax = geometry.table_bounds
    sample_xmin, sample_xmax, sample_ymin, sample_ymax = sample_bounds(geometry)
    for point in points:
        if not (
            xmin + geometry.cup_radius_m <= point.x_m <= xmax - geometry.cup_radius_m
            and ymin + geometry.cup_radius_m <= point.y_m <= ymax - geometry.cup_radius_m
        ):
            raise ValueError(f"{point.name} does not keep the cup supported by the table")
        if not (
            sample_xmin <= point.x_m <= sample_xmax
            and sample_ymin <= point.y_m <= sample_ymax
        ):
            raise ValueError(f"{point.name} is outside the conservative candidate region")

    minimum = min(
        math.dist((a.x_m, a.y_m), (b.x_m, b.y_m))
        for index, a in enumerate(points)
        for b in points[index + 1 :]
    )
    if minimum < MIN_SEPARATION_M:
        raise ValueError(
            f"minimum point separation {minimum:.9f} m is below {MIN_SEPARATION_M:.3f} m"
        )
    return minimum


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def svg_figure(
    points: Sequence[Point],
    geometry: Geometry,
    minimum_separation: float,
    *,
    seed: int,
) -> str:
    width, height = 1600, 1100
    plot_left, plot_top, scale = 90.0, 115.0, 1300.0
    table_xmin, table_xmax, table_ymin, table_ymax = geometry.table_bounds

    def px(x_m: float) -> float:
        return plot_left + (x_m - table_xmin) * scale

    def py(y_m: float) -> float:
        return plot_top + (table_ymax - y_m) * scale

    def rect(bounds: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        xmin, xmax, ymin, ymax = bounds
        return px(xmin), py(ymax), (xmax - xmin) * scale, (ymax - ymin) * scale

    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">SO-101 MoveIt 专家 20 个杯子初始位置俯视图</title>',
        '<desc id="desc">按世界坐标等比例绘制桌面、方形机械臂底座、移动目标点、4 个既有杯子中心点和 16 个固定种子生成的杯子中心点。</desc>',
        '<rect width="1600" height="1100" fill="#ffffff"/>',
        '<style>',
        'text{font-family:Arial,"PingFang SC","Noto Sans CJK SC",sans-serif;fill:#172033}',
        '.title{font-size:28px;font-weight:700}.subtitle{font-size:15px;fill:#4a5568}',
        '.axis{font-size:13px;fill:#4a5568}.label{font-size:13px;font-weight:600}',
        '.small{font-size:12px;fill:#4a5568}.table-head{font-size:13px;font-weight:700}',
        '.table-cell{font-size:12px}.mono{font-family:"SFMono-Regular",Consolas,monospace}',
        '</style>',
        '<text x="90" y="48" class="title">SO-101 MoveIt 专家：20 个杯子初始位置（俯视，等比例）</text>',
        f'<text x="90" y="76" class="subtitle">world 坐标；X 向右，Y 向上；负 Y 为机械臂前方。所有杯子中心 Z = {points[0].z_m:.3f} m。</text>',
    ]

    tx, ty, tw, th = rect(geometry.table_bounds)
    elements.append(f'<rect x="{tx:.1f}" y="{ty:.1f}" width="{tw:.1f}" height="{th:.1f}" fill="#ead7bc" stroke="#7a5432" stroke-width="2"/>')
    for index in range(-5, 6):
        x_m = index * 0.05
        if table_xmin <= x_m <= table_xmax:
            x = px(x_m)
            elements.append(f'<line x1="{x:.1f}" y1="{ty:.1f}" x2="{x:.1f}" y2="{ty + th:.1f}" stroke="#bca98e" stroke-width="1"/>')
            elements.append(f'<text x="{x:.1f}" y="{ty + th + 23:.1f}" class="axis" text-anchor="middle">{x_m:.2f}</text>')
    for index in range(-10, 3):
        y_m = index * 0.05
        if table_ymin <= y_m <= table_ymax:
            y = py(y_m)
            elements.append(f'<line x1="{tx:.1f}" y1="{y:.1f}" x2="{tx + tw:.1f}" y2="{y:.1f}" stroke="#bca98e" stroke-width="1"/>')
            elements.append(f'<text x="{tx - 12:.1f}" y="{y + 4:.1f}" class="axis" text-anchor="end">{y_m:.2f}</text>')
    elements.append(f'<text x="{tx + tw / 2:.1f}" y="{ty + th + 52:.1f}" class="label" text-anchor="middle">X world (m)</text>')
    elements.append(f'<text x="30" y="{ty + th / 2:.1f}" class="label" text-anchor="middle" transform="rotate(-90 30 {ty + th / 2:.1f})">Y world (m)</text>')

    candidate_bounds = sample_bounds(geometry)
    sx, sy, sw, sh = rect(candidate_bounds)
    elements.append(f'<rect x="{sx:.1f}" y="{sy:.1f}" width="{sw:.1f}" height="{sh:.1f}" fill="none" stroke="#2f6fad" stroke-width="2" stroke-dasharray="8 6"/>')
    elements.append(f'<text x="{sx + 8:.1f}" y="{sy + 20:.1f}" class="small">16 点生成区域</text>')
    x_bins, y_bins = stratum_bounds(geometry)
    for boundary in (
        x_bins["left"][1],
        x_bins["center"][0],
        x_bins["center"][1],
        x_bins["right"][0],
    ):
        x = px(boundary)
        elements.append(f'<line x1="{x:.1f}" y1="{sy:.1f}" x2="{x:.1f}" y2="{sy + sh:.1f}" stroke="#7da4c8" stroke-width="1" stroke-dasharray="3 6"/>')
    for boundary in (
        y_bins["far"][1],
        y_bins["mid"][0],
        y_bins["mid"][1],
        y_bins["near"][0],
    ):
        y = py(boundary)
        elements.append(f'<line x1="{sx:.1f}" y1="{y:.1f}" x2="{sx + sw:.1f}" y2="{y:.1f}" stroke="#7da4c8" stroke-width="1" stroke-dasharray="3 6"/>')

    bx, by, bw, bh = rect(geometry.base_bounds)
    base_width_mm = (geometry.base_bounds[1] - geometry.base_bounds[0]) * 1000
    base_depth_mm = (geometry.base_bounds[3] - geometry.base_bounds[2]) * 1000
    elements.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}" fill="#5e6572" stroke="#272b33" stroke-width="2"/>')
    elements.append(f'<line x1="{px(0)-8:.1f}" y1="{py(0):.1f}" x2="{px(0)+8:.1f}" y2="{py(0):.1f}" stroke="#ffffff" stroke-width="2"/>')
    elements.append(f'<line x1="{px(0):.1f}" y1="{py(0)-8:.1f}" x2="{px(0):.1f}" y2="{py(0)+8:.1f}" stroke="#ffffff" stroke-width="2"/>')
    elements.append(f'<text x="{px(0):.1f}" y="{py(0)+5:.1f}" class="label" text-anchor="middle" style="fill:#ffffff">机械臂底座</text>')
    elements.append(f'<text x="{px(0):.1f}" y="{py(0)+24:.1f}" class="small" text-anchor="middle" style="fill:#ffffff">{base_width_mm:.0f} × {base_depth_mm:.0f} mm</text>')

    rx, ry, rw, rh = rect(geometry.target_bounds)
    target_x, target_y = px(geometry.target_center[0]), py(geometry.target_center[1])
    target_tolerance_radius_px = geometry.target_tolerance_radius_m * scale
    elements.append(f'<rect x="{rx:.1f}" y="{ry:.1f}" width="{rw:.1f}" height="{rh:.1f}" fill="#ffdddd" stroke="#c62828" stroke-width="2"/>')
    elements.append(f'<circle data-role="target-center-tolerance" cx="{target_x:.1f}" cy="{target_y:.1f}" r="{target_tolerance_radius_px:.1f}" fill="none" stroke="#c62828" stroke-width="2" stroke-dasharray="5 4"/>')
    elements.append(f'<line x1="{target_x-10:.1f}" y1="{target_y:.1f}" x2="{target_x+10:.1f}" y2="{target_y:.1f}" stroke="#c62828" stroke-width="3"/>')
    elements.append(f'<line x1="{target_x:.1f}" y1="{target_y-10:.1f}" x2="{target_x:.1f}" y2="{target_y+10:.1f}" stroke="#c62828" stroke-width="3"/>')
    elements.append(f'<line x1="{target_x:.1f}" y1="{target_y+13:.1f}" x2="{target_x:.1f}" y2="{target_y+50:.1f}" stroke="#c62828" stroke-width="1.5"/>')
    elements.append(f'<text x="{target_x:.1f}" y="{target_y+66:.1f}" class="label" text-anchor="middle" style="fill:#a51f1f">移动目标 T</text>')
    elements.append(f'<text x="{target_x:.1f}" y="{target_y+83:.1f}" class="small" text-anchor="middle" style="fill:#a51f1f">({geometry.target_center[0]:.3f}, {geometry.target_center[1]:.3f})</text>')

    p01 = points[0]
    elements.append(
        f'<circle data-role="p01-cup-footprint" cx="{px(p01.x_m):.1f}" '
        f'cy="{py(p01.y_m):.1f}" r="{geometry.cup_radius_m * scale:.1f}" '
        'fill="none" stroke="#7a4800" stroke-width="2" '
        'stroke-dasharray="8 6"/>'
    )

    for point in points:
        x, y = px(point.x_m), py(point.y_m)
        if point.source == "existing":
            vertices = f"{x:.1f},{y-11:.1f} {x+11:.1f},{y:.1f} {x:.1f},{y+11:.1f} {x-11:.1f},{y:.1f}"
            elements.append(f'<polygon points="{vertices}" fill="#ffb84d" stroke="#7a4800" stroke-width="2"/>')
        else:
            elements.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" fill="#5aa7df" stroke="#164f78" stroke-width="2"/>')
        elements.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="#111827"/>')
        elements.append(f'<text x="{x+11:.1f}" y="{y-10:.1f}" class="label">{esc(point.id)}</text>')

    arrow_x = px(0.225)
    elements.extend(
        [
            f'<line x1="{arrow_x:.1f}" y1="{py(-0.02):.1f}" x2="{arrow_x:.1f}" y2="{py(-0.12):.1f}" stroke="#172033" stroke-width="2"/>',
            f'<polygon points="{arrow_x-6:.1f},{py(-0.12)-10:.1f} {arrow_x+6:.1f},{py(-0.12)-10:.1f} {arrow_x:.1f},{py(-0.12):.1f}" fill="#172033"/>',
            f'<text x="{arrow_x-10:.1f}" y="{py(-0.07):.1f}" class="small" text-anchor="end">前方 −Y</text>',
        ]
    )

    panel_x = 825
    elements.append(f'<text x="{panel_x}" y="118" class="title" style="font-size:21px">中心点坐标</text>')
    elements.append(f'<text x="{panel_x}" y="144" class="subtitle">既有 4 点 + seed {seed} 生成 16 点</text>')
    columns = ((0, "ID"), (54, "类别"), (178, "X (m)"), (278, "Y (m)"), (378, "Z (m)"))
    for offset, label in columns:
        elements.append(f'<text x="{panel_x + offset}" y="178" class="table-head">{esc(label)}</text>')
    elements.append(f'<line x1="{panel_x}" y1="188" x2="1515" y2="188" stroke="#aab2bf" stroke-width="1"/>')
    row_y = 214
    for index, point in enumerate(points):
        if point.source == "existing":
            category = "既有锚点"
        else:
            distance, lateral = point.stratum.split("-")
            category = f"生成·{DISTANCE_ZH[distance]}{LATERAL_ZH[lateral]}"
        values = (
            point.id,
            category,
            f"{point.x_m:+.6f}",
            f"{point.y_m:+.6f}",
            f"{point.z_m:.3f}",
        )
        if index % 2 == 0:
            elements.append(f'<rect x="{panel_x-8}" y="{row_y-18}" width="700" height="27" fill="#f3f6fa"/>')
        for (offset, _label), value in zip(columns, values):
            class_name = "table-cell mono" if offset >= 178 or offset == 0 else "table-cell"
            elements.append(f'<text x="{panel_x + offset}" y="{row_y}" class="{class_name}">{esc(value)}</text>')
        row_y += 31

    legend_y = 855
    sample_xmin, sample_xmax, sample_ymin, sample_ymax = candidate_bounds
    table_width_mm = (table_xmax - table_xmin) * 1000
    table_depth_mm = (table_ymax - table_ymin) * 1000
    target_width_mm = (geometry.target_bounds[1] - geometry.target_bounds[0]) * 1000
    target_depth_mm = (geometry.target_bounds[3] - geometry.target_bounds[2]) * 1000
    elements.extend(
        [
            f'<polygon points="{panel_x},{legend_y-10} {panel_x+10},{legend_y} {panel_x},{legend_y+10} {panel_x-10},{legend_y}" fill="#ffb84d" stroke="#7a4800" stroke-width="2"/>',
            f'<circle cx="{panel_x}" cy="{legend_y}" r="2.5" fill="#111827"/>',
            f'<text x="{panel_x+20}" y="{legend_y+5}" class="small">既有位置 / 杯子中心</text>',
            f'<circle cx="{panel_x+215}" cy="{legend_y}" r="9" fill="#5aa7df" stroke="#164f78" stroke-width="2"/>',
            f'<circle cx="{panel_x+215}" cy="{legend_y}" r="2.5" fill="#111827"/>',
            f'<text x="{panel_x+235}" y="{legend_y+5}" class="small">生成位置 / 杯子中心</text>',
            f'<rect x="{panel_x+442}" y="{legend_y-9}" width="18" height="18" fill="#ffdddd" stroke="#c62828" stroke-width="2"/>',
            f'<text x="{panel_x+470}" y="{legend_y+5}" class="small">策略接受框 {target_width_mm:.0f} × {target_depth_mm:.0f} mm</text>',
            f'<circle cx="{panel_x+5}" cy="890" r="9" fill="none" stroke="#7a4800" stroke-width="2" stroke-dasharray="6 4"/>',
            f'<text x="{panel_x+25}" y="895" class="small">P01 杯底范围 r = {geometry.cup_radius_m*1000:.0f} mm</text>',
            f'<circle cx="{panel_x+275}" cy="890" r="9" fill="none" stroke="#c62828" stroke-width="2" stroke-dasharray="5 4"/>',
            f'<text x="{panel_x+295}" y="895" class="small">目标中心容差圆 r = {geometry.target_tolerance_radius_m*1000:.0f} mm</text>',
            f'<line x1="{panel_x}" y1="920" x2="1515" y2="920" stroke="#aab2bf" stroke-width="1"/>',
            f'<text x="{panel_x}" y="946" class="small">桌面：{table_width_mm:.0f} × {table_depth_mm:.0f} mm；杯半径：{geometry.cup_radius_m*1000:.0f} mm；底座：{base_width_mm:.0f} × {base_depth_mm:.0f} mm。</text>',
            f'<text x="{panel_x}" y="970" class="small">生成范围：X [{sample_xmin:.2f}, {sample_xmax:.2f}] m，Y [{sample_ymin:.2f}, {sample_ymax:.2f}] m；近/中/远 × 左/中/右分层。</text>',
            f'<text x="{panel_x}" y="994" class="small">点间最小距离：{minimum_separation*1000:.1f} mm（阈值 35 mm）；坐标保留至 1 µm。</text>',
            f'<text x="{panel_x}" y="1018" class="small">注：20 个杯子点表示 20 个独立初始场景，不是同时放置 20 个杯子。</text>',
            '<text x="90" y="1065" class="small">几何来源：scene.xml、target_landing_tolerance_ring.obj、rgbd_task_points.yaml 与 light_cup_wall_pick/v1/mujoco.yaml。</text>',
        ]
    )
    elements.append("</svg>")
    return "\n".join(elements) + "\n"


def write_csv(path: Path, points: Sequence[Point]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("id", "name", "source", "stratum", "x_m", "y_m", "z_m"),
        )
        writer.writeheader()
        for point in points:
            writer.writerow(point._asdict())


def write_yaml(path: Path, points: Sequence[Point]) -> None:
    lines = ["schema_version: 1", "points:"]
    for point in points:
        lines.extend(
            [
                f"  - id: {point.name}",
                f"    label: {point.id} {point.source} {point.stratum}",
                "    cup_position_world_m: "
                f"[{point.x_m:.6f}, {point.y_m:.6f}, {point.z_m:.3f}]",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_png(svg_path: Path, png_path: Path, *, width: int, height: int) -> None:
    converter = shutil.which("rsvg-convert")
    if converter is None:
        raise RuntimeError("--png requires rsvg-convert on PATH")
    subprocess.run(
        (
            converter,
            "-w",
            str(width),
            "-h",
            str(height),
            "-o",
            str(png_path),
            str(svg_path),
        ),
        check=True,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    default_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description=(
            "Generate a deterministic, dimensionally accurate SO-101 MoveIt expert "
            "position map plus YAML and CSV manifests."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=default_root)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--png", action="store_true", help="also render a 1600x1100 PNG")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repository_root = args.repo_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    geometry = load_geometry(repository_root)
    anchors = load_anchors(repository_root)
    points = generate_positions(anchors, geometry, seed=args.seed)
    minimum_separation = validate(points, geometry)

    svg_path = output_dir / "so101-position-top-view.svg"
    csv_path = output_dir / "so101-position-manifest.csv"
    yaml_path = output_dir / "so101-position-manifest.yaml"
    svg_path.write_text(
        svg_figure(points, geometry, minimum_separation, seed=args.seed),
        encoding="utf-8",
    )
    write_csv(csv_path, points)
    write_yaml(yaml_path, points)
    if args.png:
        render_png(
            svg_path,
            output_dir / "so101-position-top-view.png",
            width=1600,
            height=1100,
        )

    print(f"POINTS={len(points)}")
    print(f"ANCHORS={sum(point.source == 'existing' for point in points)}")
    print(f"GENERATED={sum(point.source == 'generated' for point in points)}")
    print(f"MIN_SEPARATION_M={minimum_separation:.9f}")
    print(f"SVG={svg_path}")
    print(f"CSV={csv_path}")
    print(f"YAML={yaml_path}")
    if args.png:
        print(f"PNG={output_dir / 'so101-position-top-view.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
