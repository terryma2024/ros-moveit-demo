"""CLI for plan-only reachability checks over one or more task points."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ..application.task_reachability import (
    ReachabilityReport,
    ReachabilityStatus,
    check_task_reachability,
)
from ..core.dynamic_pick_policy import load_dynamic_pick_template
from ..runtime.task_point_config import load_task_point_list


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="task_reachability")
    parser.add_argument("--points", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--evidence-file", type=Path, required=True)
    parser.add_argument("--point-id")
    parser.add_argument("--joint-state-timeout-s", type=float, default=5.0)
    return parser


def _segment_document(segment) -> dict[str, object]:
    return {
        "state": segment.state.value,
        "target": {
            "position_m": list(segment.target.position_m),
            "orientation_xyzw": list(segment.target.orientation_xyzw),
        },
        "accepted": segment.accepted,
        "moveit_error_code": segment.moveit_error_code,
        "failure_code": segment.failure_code,
        "collision_pairs": [list(pair) for pair in segment.collision_pairs],
    }


def _report_document(report: ReachabilityReport) -> dict[str, object]:
    return {
        "point_id": report.point_id,
        "status": report.status.value,
        "segments": [_segment_document(segment) for segment in report.segments],
        "first_failure_code": report.first_failure_code,
        "scene_revision": report.scene_revision,
    }


def result_document(reports: tuple[ReachabilityReport, ...]) -> dict[str, object]:
    status = "SUCCEEDED" if all(
        report.status is ReachabilityStatus.REACHABLE for report in reports
    ) else "FAILED"
    return {"status": status, "reports": [_report_document(report) for report in reports]}


def result_exit_code(reports: tuple[ReachabilityReport, ...]) -> int:
    if any(report.status is ReachabilityStatus.UNKNOWN for report in reports):
        return 1
    if any(report.status is ReachabilityStatus.UNREACHABLE for report in reports):
        return 2
    return 0


def _atomic_json(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main(arguments: list[str] | None = None) -> int:
    options = build_parser().parse_args(arguments)
    reports: tuple[ReachabilityReport, ...] = ()
    node = None
    planner = None
    reader = None
    try:
        template = load_dynamic_pick_template(options.policy, expected_backend="mujoco")
        point_list = load_task_point_list(options.points, template.workspace_bounds_m)
        points = point_list.points
        if options.point_id is not None:
            points = tuple(point for point in points if point.id == options.point_id)
            if not points:
                raise ValueError(f"TASK_POINT_NOT_FOUND: {options.point_id}")

        import rclpy
        from rclpy.parameter import Parameter

        from ..ros.task_reachability import (
            RosJointStateReader,
            RosMoveGroupReachabilityPlanner,
        )

        rclpy.init()
        node = rclpy.create_node(
            "so101_task_reachability",
            parameter_overrides=[Parameter("use_sim_time", value=True)],
        )
        planner = RosMoveGroupReachabilityPlanner(node, template)
        reader = RosJointStateReader(node, template.arm_joint_names)
        start = reader.read(options.joint_state_timeout_s)
        reports = tuple(
            check_task_reachability(point, template, start, planner)
            for point in points
        )
        document = result_document(reports)
        document["session_id"] = options.session_id
    except Exception as error:
        document = {
            "status": "FAILED",
            "reports": [],
            "session_id": options.session_id,
            "failure_code": str(error).split(":", 1)[0],
            "message": str(error),
        }
        exit_code = 1
    else:
        exit_code = result_exit_code(reports)
    finally:
        if reader is not None:
            reader.close()
        if planner is not None:
            planner.close()
        if node is not None:
            node.destroy_node()
            import rclpy

            if rclpy.ok():
                rclpy.shutdown()

    _atomic_json(options.evidence_file, document)
    print(json.dumps(document, sort_keys=True), flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
