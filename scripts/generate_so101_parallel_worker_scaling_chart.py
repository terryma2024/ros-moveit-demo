#!/usr/bin/env python3
"""Generate the checked SO-101 fixed-Worker scaling chart from maintained JSON."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = REPOSITORY_ROOT / "docs/guides/data/so101-parallel-worker-scaling.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "docs/guides/assets/so101-parallel-worker-scaling.svg"
SVG_NS = "http://www.w3.org/2000/svg"


def _number(value: object, name: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        raise ValueError(f"{name} must be finite and >= {minimum}")
    return number


def validate_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    levels = document.get("levels")
    if not isinstance(levels, list) or not levels:
        raise ValueError("levels must be a non-empty list")

    workers_seen: set[int] = set()
    prior_workers = 0
    for index, row in enumerate(levels):
        if not isinstance(row, dict):
            raise ValueError(f"levels[{index}] must be an object")
        workers = row.get("workers")
        if isinstance(workers, bool) or not isinstance(workers, int) or workers <= 0:
            raise ValueError(f"levels[{index}].workers must be a positive integer")
        if workers in workers_seen or workers <= prior_workers:
            raise ValueError("worker levels must be unique and strictly increasing")
        workers_seen.add(workers)
        prior_workers = workers
        status = row.get("status")
        valid = row.get("valid_performance_sample")
        if status not in {"PASSED", "FAILED"} or type(valid) is not bool:
            raise ValueError(f"levels[{index}] has invalid status/sample fields")
        metrics = (
            "execution_s",
            "throughput_points_per_min",
            "speedup_vs_w1",
            "parallel_efficiency",
            "peak_memory_b",
        )
        if status == "PASSED":
            if not valid or row.get("successful_points") != document["contract"]["catalog_points"]:
                raise ValueError("PASSED level must be a complete valid sample")
            for name in metrics:
                _number(row.get(name), f"levels[{index}].{name}", minimum=0.000001)
        elif valid or any(row.get(name) is not None for name in metrics):
            raise ValueError("FAILED aggregate level must use null performance metrics")

    attempts = document.get("failed_attempts")
    if not isinstance(attempts, list):
        raise ValueError("failed_attempts must be a list")
    attempt_ids: set[str] = set()
    for index, attempt in enumerate(attempts):
        if not isinstance(attempt, dict):
            raise ValueError(f"failed_attempts[{index}] must be an object")
        identity = attempt.get("experiment_id")
        if not isinstance(identity, str) or not identity or identity in attempt_ids:
            raise ValueError("failed attempt experiment IDs must be unique")
        attempt_ids.add(identity)
        workers = attempt.get("workers")
        if workers not in workers_seen:
            raise ValueError("failed attempt must reference a declared Worker level")
        points = attempt.get("successful_points")
        if isinstance(points, bool) or not isinstance(points, int):
            raise ValueError("failed attempt successful_points must be an integer")
        if not 0 <= points < document["contract"]["catalog_points"]:
            raise ValueError("failed attempt cannot be a complete sample")
        _number(attempt.get("peak_memory_b"), "failed attempt peak_memory_b")
        if type(attempt.get("cleanup_passed")) is not bool:
            raise ValueError("failed attempt cleanup_passed must be boolean")
    return document


def load_and_validate(path: Path) -> dict[str, object]:
    return validate_document(json.loads(path.read_text(encoding="utf-8")))


def _escape(value: object) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _worker_x(
    worker: int,
    box: tuple[float, float, float, float],
    worker_domain: tuple[int, int],
) -> float:
    left, _, width, _ = box
    worker_min, worker_max = worker_domain
    return left + (worker - worker_min) / (worker_max - worker_min) * width


def _points(
    rows: list[dict[str, object]],
    field: str,
    box: tuple[float, float, float, float],
    maximum: float,
    worker_domain: tuple[int, int],
) -> list[tuple[float, float]]:
    _, top, _, height = box
    result = []
    for row in rows:
        x = _worker_x(row["workers"], box, worker_domain)
        y = top + height - float(row[field]) / maximum * height
        result.append((x, y))
    return result


def _polyline(points: list[tuple[float, float]], css_class: str) -> str:
    coords = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return f'<polyline class="{css_class}" points="{coords}"/>'


def render_svg(document: dict[str, object]) -> str:
    valid = [row for row in document["levels"] if row["valid_performance_sample"]]
    failed = [row for row in document["levels"] if not row["valid_performance_sample"]]
    workers = [row["workers"] for row in document["levels"]]
    worker_domain = (workers[0], workers[-1])
    boxes = ((92.0, 138.0, 1018.0, 170.0), (92.0, 382.0, 1018.0, 170.0), (92.0, 626.0, 1018.0, 170.0))
    fields = ("execution_s", "speedup_vs_w1", "peak_memory_b")
    maxima = (1700.0, 10.0, 11 * 1024**3)
    titles = ("20 点有效执行区间（秒，越低越好）", "相对 W1 加速比（虚线为理想线）", "Runner cgroup 峰值内存（GiB）")
    lines = [
        f'<svg xmlns="{SVG_NS}" viewBox="0 0 1200 900" role="img" aria-labelledby="title desc">',
        '<title id="title">SO-101 固定 Worker 扩容曲线</title>',
        '<desc id="desc">W1、W2、W4、W6、W8、W10 都有完整有效样本；W10 的两次历史失败保留在数据中，不作为性能点。</desc>',
        '<style>text{font-family:system-ui,-apple-system,"Noto Sans CJK SC",sans-serif;fill:#1f2937}.title{font-size:28px;font-weight:700}.sub{font-size:14px;fill:#4b5563}.panel{fill:#fff;stroke:#d1d5db}.grid{stroke:#e5e7eb;stroke-width:1}.axis{stroke:#6b7280;stroke-width:1.5}.valid{fill:none;stroke:#1677ff;stroke-width:4;stroke-linejoin:round;stroke-linecap:round}.ideal{fill:none;stroke:#94a3b8;stroke-width:2;stroke-dasharray:7 6}.dot{fill:#fff;stroke:#1677ff;stroke-width:3}.fail{stroke:#dc2626;stroke-width:4;stroke-linecap:round}.label{font-size:13px}.small{font-size:12px;fill:#64748b}.panel-title{font-size:17px;font-weight:650}.legend{font-size:13px}</style>',
        '<rect width="1200" height="900" fill="#f8fafc"/>',
        '<text class="title" x="60" y="50">SO-101 固定 Worker 扩容曲线</text>',
        '<text class="sub" x="60" y="78">冻结 20 点 / C2 / YOLO-first / 无 Worker fallback；每个有效档位 n=1</text>',
        '<line x1="785" y1="46" x2="815" y2="46" class="valid"/><text class="legend" x="824" y="51">有效样本</text>',
    ]
    if failed:
        lines.extend([
            '<line x1="930" y1="38" x2="946" y2="54" class="fail"/><line x1="946" y1="38" x2="930" y2="54" class="fail"/><text class="legend" x="956" y="51">失败档位（不连线）</text>',
        ])

    for panel_index, (box, field, maximum, panel_title) in enumerate(zip(boxes, fields, maxima, titles)):
        left, top, width, height = box
        lines.append(f'<rect class="panel" x="60" y="{top - 38:.1f}" width="1080" height="226" rx="10"/>')
        lines.append(f'<text class="panel-title" x="{left:.1f}" y="{top - 10:.1f}">{panel_title}</text>')
        for step in range(5):
            y = top + height - step / 4 * height
            lines.append(f'<line class="grid" x1="{left:.1f}" y1="{y:.1f}" x2="{left + width:.1f}" y2="{y:.1f}"/>')
            value = maximum * step / 4
            if field == "peak_memory_b":
                label = f"{value / 1024**3:.1f}"
            else:
                label = f"{value:.0f}"
            lines.append(f'<text class="small" text-anchor="end" x="{left - 10:.1f}" y="{y + 4:.1f}">{label}</text>')
        lines.append(f'<line class="axis" x1="{left:.1f}" y1="{top + height:.1f}" x2="{left + width:.1f}" y2="{top + height:.1f}"/>')
        valid_points = _points(valid, field, box, maximum, worker_domain)
        lines.append(_polyline(valid_points, "valid"))
        if field == "speedup_vs_w1":
            ideal_rows = [{"workers": row["workers"], field: row["workers"]} for row in valid]
            lines.append(
                _polyline(
                    _points(ideal_rows, field, box, maximum, worker_domain),
                    "ideal",
                )
            )
        for row, (x, y) in zip(valid, valid_points):
            lines.append(
                f'<circle class="dot" data-role="valid-point" data-worker="{row["workers"]}" '
                f'cx="{x:.1f}" cy="{y:.1f}" r="5"/>'
            )
            if field == "execution_s":
                label = f'{row[field]:.1f} s'
            elif field == "speedup_vs_w1":
                label = f'{row[field]:.2f}× / {row["throughput_points_per_min"]:.2f} 点/分'
            else:
                label = f'{row[field] / 1024**3:.2f} GiB'
            lines.append(
                f'<text class="label" data-role="value-label" data-worker="{row["workers"]}" '
                f'text-anchor="middle" x="{x:.1f}" y="{max(top + 14, y - 10):.1f}">'
                f'{_escape(label)}</text>'
            )
        for worker in workers:
            x = _worker_x(worker, box, worker_domain)
            lines.append(
                f'<text class="small" data-role="worker-tick" data-worker="{worker}" '
                f'text-anchor="middle" x="{x:.1f}" y="{top + height + 20:.1f}">W{worker}</text>'
            )
        for failed_row in failed:
            failed_worker = failed_row["workers"]
            fail_x = _worker_x(failed_worker, box, worker_domain)
            if field == "peak_memory_b":
                failed_attempts = [
                    attempt
                    for attempt in document["failed_attempts"]
                    if attempt["workers"] == failed_worker
                ]
                failure_peak = max(attempt["peak_memory_b"] for attempt in failed_attempts)
                fail_y = top + height - failure_peak / maximum * height
                fail_label = f'失败峰值 {failure_peak / 1024**3:.2f} GiB'
            else:
                fail_y = top + height - 12
                fail_label = f"无有效 W{failed_worker} 性能值"
            lines.extend([
                f'<line class="fail" data-role="failure-marker" data-worker="{failed_worker}" '
                f'x1="{fail_x - 7:.1f}" y1="{fail_y - 7:.1f}" '
                f'x2="{fail_x + 7:.1f}" y2="{fail_y + 7:.1f}"/>',
                f'<line class="fail" data-role="failure-marker" data-worker="{failed_worker}" '
                f'x1="{fail_x + 7:.1f}" y1="{fail_y - 7:.1f}" '
                f'x2="{fail_x - 7:.1f}" y2="{fail_y + 7:.1f}"/>',
                f'<text class="small" data-role="failure-label" data-worker="{failed_worker}" '
                f'text-anchor="end" x="{fail_x - 12:.1f}" y="{fail_y - 10:.1f}">'
                f'{fail_label}</text>',
            ])

    w10 = next(row for row in document["levels"] if row["workers"] == 10)
    w10_failure_ids = " / ".join(
        attempt["experiment_id"]
        for attempt in document["failed_attempts"]
        if attempt["workers"] == 10
    )
    w10_footer = f'W10：{w10["experiment_id"]} 完成 20/20'
    if w10_failure_ids:
        w10_footer += f"；{w10_failure_ids} 保留为失败历史，不进入性能折线。"
    else:
        w10_footer += "。"
    lines.extend([
        f'<text class="sub" x="60" y="865">{_escape(w10_footer)}</text>',
        '</svg>',
    ])
    svg = "\n".join(lines) + "\n"
    ET.fromstring(svg)
    return svg


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="fail if output is stale")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    options = parse_args(argv)
    rendered = render_svg(load_and_validate(options.data))
    if options.check:
        if not options.output.is_file() or options.output.read_text(encoding="utf-8") != rendered:
            print(f"stale generated chart: {options.output}", file=sys.stderr)
            return 1
        return 0
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
