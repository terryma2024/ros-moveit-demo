"""CLI (evidence side): the final scene list inside the Teacher success boundary, plus a report.

Reads the finished boundary state (``act_boundary_update`` output with ``boundary_points``) and the standard rollout
points, samples about 103 scenes by seeded Poisson-disk sampling, splits them spatially (83 / 10 / 10) and writes the
scene list in the container-campaign format.  Every scene also passes the five-pose Teacher reachability filter, which
needs the native ACT execution stack: ``--reach-command`` is the same command prefix as for ``act_boundary_prefilter``.
A rollout point outside the region stops the command (``ROLLOUT_POINT_OUTSIDE_REGION``) and nothing is written.
"""

from __future__ import annotations

import argparse
import json
import math
import shlex
from pathlib import Path

from so101_demo.act import rollout_scenes, scene_sampling
from so101_demo.act.five_pose_reachability import CommandReachabilityCall, FivePoseReachability
from so101_demo.act.scene_list_format import CUP_Z_M, scene_document, scene_row, write_new_json

SEED_BASE = 200
SPLIT_ORDER = ("train", "validation", "offline_test")


def sample_with_reachability(boundary_points, rollout_points, reach: FivePoseReachability, **options):
    """Run the pure sampler until a pass asks the planner about nothing new.

    A pass answers an unevaluated position optimistically and records it; the recorded positions are then evaluated in
    batches and the sampler runs again with the verdicts, so the final pass used only real verdicts.
    """

    while True:
        reachable, missing = reach.optimistic()
        sample = scene_sampling.sample_scenes(boundary_points, rollout_points, reachable=reachable, **options)
        if not missing:
            return sample
        reach.evaluate(missing)


def build_rows(sample: scene_sampling.SceneSample, prefix: str) -> list[dict]:
    ordered = [(split, p) for split in SPLIT_ORDER for p, s in zip(sample.points, sample.splits) if s == split]
    return [scene_row(f"{prefix}-{i:03d}", SEED_BASE + i, split, p) for i, (split, p) in enumerate(ordered)]


def main(argv: list[str] | None = None, *, reach_call=None) -> int:
    parser = argparse.ArgumentParser(prog="act_scene_sample", description=__doc__)
    parser.add_argument("--state", type=Path, required=True, help="finished boundary state with boundary_points")
    parser.add_argument("--rollout-points", type=Path, required=True, help="config/mujoco/rgbd_task_points.yaml")
    parser.add_argument("--scenes-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    parser.add_argument("--call-dir", type=Path, required=True, help="per-call points and evidence files (kept)")
    parser.add_argument("--reach-command", help="command prefix that runs task_reachability; points, evidence, session appended")
    parser.add_argument("--count", type=int, default=scene_sampling.DEFAULT_COUNT)
    parser.add_argument("--split-counts", type=int, nargs=3, metavar=("TRAIN", "VALIDATION", "OFFLINE_TEST"), default=(83, 10, 10))
    parser.add_argument("--seed", type=int, default=scene_sampling.DEFAULT_SEED)
    parser.add_argument("--inward-margin-m", type=float, default=scene_sampling.INWARD_MARGIN_M)
    parser.add_argument("--scene-prefix", default="frm")
    args = parser.parse_args(argv)

    if reach_call is None:
        if not args.reach_command:
            raise ValueError("SCENE_SAMPLE_REACHABILITY_PROBE_NOT_AVAILABLE")
        reach_call = CommandReachabilityCall(shlex.split(args.reach_command), args.call_dir, session_prefix="sample")
    for target in (args.scenes_output, args.report_output):
        if target.exists() or target.is_symlink():
            raise ValueError(f"OUTPUT_EXISTS: {target}")
    state = json.loads(args.state.read_text())
    boundary_points = state.get("boundary_points")
    if not isinstance(boundary_points, dict):
        raise ValueError("SCENE_SAMPLE_BOUNDARY_NOT_FINISHED")
    rollout = {s["point_id"]: tuple(s["xy"]) for s in rollout_scenes.load_standard_points(args.rollout_points)}
    counts = dict(zip(SPLIT_ORDER, args.split_counts))
    reach = FivePoseReachability(reach_call)
    sample = sample_with_reachability(
        {name: tuple(p) for name, p in boundary_points.items()}, rollout, reach,
        count=args.count, split_counts=counts, seed=args.seed, margin_m=args.inward_margin_m,
    )
    rows = build_rows(sample, args.scene_prefix)
    rejected = sum(1 for e in reach.pose_log if e["label"] == "true" and e["status"] != "REACHABLE")
    generator = {
        "seed": args.seed, "region": "polygon through the eight boundary points, eroded by the inward margin",
        "inward_margin_m": args.inward_margin_m, "min_spacing_m": sample.spacing_m,
        "min_spacing_floor_m": scene_sampling.MIN_SPACING_FLOOR_M,
        "boundary_state": str(args.state), "reachability_filter": "task_reachability, five poses, keep when all REACHABLE",
    }
    document = scene_document(f"{args.scene_prefix}-boundary-{len(rows)}", rows, cup_z_m=CUP_Z_M, generator=generator, split_quota=counts)
    pairs = [math.dist(a, b) for i, a in enumerate(sample.points) for b in sample.points[:i]]
    report = {
        "kind": "ACT_SCENE_SAMPLE_REPORT", "schema_version": 1, "scene_count": len(rows),
        "region_polygon": [list(p) for p in sample.polygon], "shrunk_region_polygon": [list(p) for p in sample.shrunk_polygon],
        "region_area_m2": sample.area_m2, "min_spacing_m": sample.spacing_m, "nearest_pair_m": round(min(pairs), 6),
        "split_counts": {s: sample.splits.count(s) for s in SPLIT_ORDER},
        "rollout_nearest_scene_m": sample.rollout_nearest_scene_m,
        "rollout_nearest_training_m": sample.rollout_nearest_training_m,
        "positions_rejected_by_reachability": rejected, "reachability_calls": reach.calls, "seed": args.seed,
    }
    write_new_json(args.scenes_output, document)
    write_new_json(args.report_output, report)
    print(json.dumps({"scenes": str(args.scenes_output), "report": str(args.report_output), "min_spacing_m": sample.spacing_m}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
