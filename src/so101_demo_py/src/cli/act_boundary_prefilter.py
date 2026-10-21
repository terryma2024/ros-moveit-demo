"""CLI (evidence side): the offline kinematic limit r_kin of each of the eight boundary rays.

Walks every ray outward in 1 cm steps with the five-pose Teacher reachability filter (the same filter the formal scene
generation used) and stops at the first unreachable point or hard limit.  The filter needs the native ACT execution
stack running (ROS 2, MoveIt ``/move_group``, joint states): ``--reach-command`` is the command prefix that runs the
``task_reachability`` executable inside it, for example ``zsh reach_call.zsh <out> <container>``.  Without a command (or an
injected ``reach_call``) the command refuses and writes nothing.
"""

from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path

from so101_demo.act import scene_boundary as boundary
from so101_demo.act.boundary_search import LIMITS_KIND
from so101_demo.act.five_pose_reachability import (
    ROLES,
    CommandReachabilityCall,
    FivePoseReachability,
    PoseNotEvaluatedError,
)
from so101_demo.act.scene_list_format import write_new_json


def compute_limits(rays: dict, reach: FivePoseReachability) -> dict[str, boundary.KinematicLimit]:
    """Lockstep over the rays: each pass asks for the first unevaluated point of every unfinished ray, in one batch."""

    limits: dict[str, boundary.KinematicLimit] = {}
    while len(limits) < len(rays):
        misses = []
        for name, ray in rays.items():
            if name in limits:
                continue
            try:
                limits[name] = boundary.kinematic_limit(ray, reach.is_reachable)
            except PoseNotEvaluatedError as error:
                misses.append((error.x, error.y))
        if misses:
            reach.evaluate(misses)
    return limits


def _evaluated_points(ray, limit: boundary.KinematicLimit, reach: FivePoseReachability) -> list[dict]:
    evaluated = []
    for point in ray:
        if limit.first_blocked_m is not None and point.radius_m > limit.first_blocked_m:
            break
        hard = boundary.hard_limit_violation(point.x, point.y)
        status = hard or ("REACHABLE" if reach.is_reachable(point.x, point.y) else "UNREACHABLE")
        evaluated.append({"radius_m": point.radius_m, "xy": [point.x, point.y], "status": status})
    return evaluated


def main(argv: list[str] | None = None, *, reach_call=None) -> int:
    parser = argparse.ArgumentParser(prog="act_boundary_prefilter", description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="the r_kin JSON (written once)")
    parser.add_argument("--call-dir", type=Path, required=True, help="per-call points and evidence files (kept)")
    parser.add_argument("--reach-command", help="command prefix that runs task_reachability; points, evidence, session appended")
    parser.add_argument("--centre", type=float, nargs=2, default=boundary.DEFAULT_CENTRE_XY, metavar=("X", "Y"))
    parser.add_argument("--step-m", type=float, default=boundary.DEFAULT_STEP_M)
    parser.add_argument("--max-radius-m", type=float, default=boundary.DEFAULT_MAX_RADIUS_M)
    args = parser.parse_args(argv)

    if reach_call is None:
        if not args.reach_command:
            raise ValueError("BOUNDARY_REACHABILITY_PROBE_NOT_AVAILABLE")
        reach_call = CommandReachabilityCall(shlex.split(args.reach_command), args.call_dir)
    if args.output.exists() or args.output.is_symlink():
        raise ValueError(f"OUTPUT_EXISTS: {args.output}")
    rays = boundary.ray_candidates(tuple(args.centre), 8, args.step_m, args.max_radius_m)
    reach = FivePoseReachability(reach_call)
    limits = compute_limits(rays, reach)
    document = {
        "kind": LIMITS_KIND,
        "schema_version": 1,
        "centre_xy": list(args.centre),
        "step_m": args.step_m,
        "max_radius_m": args.max_radius_m,
        "reachability": {
            "tool": "task_reachability --ik-backend native (five poses per position)",
            "roles": [role for role, _dx, _dy in ROLES],
            "keep_when": "all five poses REACHABLE",
            "calls": reach.calls,
        },
        "rays": {
            name: {
                "last_feasible_m": limits[name].last_feasible_m,
                "first_blocked_m": limits[name].first_blocked_m,
                "reason": limits[name].reason,
                "evaluated": _evaluated_points(ray, limits[name], reach),
            }
            for name, ray in rays.items()
        },
        "pose_log": reach.pose_log,
    }
    write_new_json(args.output, document)
    summary = {name: limits[name].last_feasible_m for name in rays}
    print(json.dumps({"output": str(args.output), "last_feasible_m": summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
