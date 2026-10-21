"""CLI (evidence side): the final scene list inside the Teacher success boundary, plus a report.

Reads the finished boundary state (``act_boundary_update`` output with ``boundary_points``) and the standard rollout
points, samples about 103 scenes by seeded Poisson-disk sampling, splits them spatially (83 / 10 / 10) and writes the
scene list in the container-campaign format.  Every scene also passes the five-pose Teacher reachability filter, which
needs the native ACT execution stack: ``--reach-command`` is the same command prefix as for ``act_boundary_prefilter``.
A rollout point outside the region stops the command (``ROLLOUT_POINT_OUTSIDE_REGION``) and nothing is written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shlex
from pathlib import Path

from so101_demo.act import rollout_scenes, scene_sampling
from so101_demo.act.five_pose_reachability import CommandReachabilityCall, FivePoseReachability
from so101_demo.act.scene_list_format import CUP_Z_M, scene_document, scene_row, write_new_json

SEED_BASE = 200
#: Deepest-draw multiple of the pre-fetched candidate cloud; set from the real planner rates (progress-goal2.md item 28).
DEFAULT_PREFETCH_FACTOR = 2.0
#: Joint mode (boundary design amendment 3): list name -> (scene id prefix, first row seed, split name of its rows; ``None`` = split spatially).
JOINT_LISTS = {"formal": ("frm", 200, None), "qualification": ("qual", 400, "qualification"), "functional": ("fn", 600, "functional")}
JOINT_SPLIT_LIST = "formal"
DECIMALS_REPORT = 6
SPLIT_ORDER = ("train", "validation", "offline_test")


def _prefetch(reach: FivePoseReachability, boundary_points, rollout_points, missing, factor: float, options) -> None:
    """Evaluate all five poses of the whole candidate cloud at once (see ``scene_sampling.candidate_cloud``).

    The sample is a function of the per-position verdicts only, so this changes how many sampler passes and planner rounds
    are needed, not the outcome. Without it every pass learns about the few positions its predecessor rejected and asks for
    those in a new round: one planner round after the other, about a hundred passes for a formal list. With the cloud the
    planner rounds are independent of each other (and run side by side on a pool); a position beyond the cloud makes the next
    pass ask for a deeper one, so the cloud doubles its factor at every step instead of growing by a few positions.
    """

    cloud = scene_sampling.candidate_cloud(
        boundary_points, rollout_points, missing, factor=factor, seed=options.get("seed", scene_sampling.DEFAULT_SEED),
        margin_m=options.get("margin_m", scene_sampling.INWARD_MARGIN_M),
        rollout_clearance_m=options.get("rollout_clearance_m", scene_sampling.ROLLOUT_CLEARANCE_M),
        boundary_kinds=options.get("boundary_kinds"))
    reach.evaluate(cloud)


def sample_with_reachability(boundary_points, rollout_points, reach: FivePoseReachability, *, prefetch_factor: float = 0.0, **options):
    """Run the pure sampler until a pass asks the planner about nothing new.

    A pass answers an unevaluated position optimistically and records it; the recorded positions are then evaluated in
    batches and the sampler runs again with the verdicts, so the final pass used only real verdicts. With a
    ``prefetch_factor`` the positions asked about are evaluated together with a cloud of candidates around them.
    """

    while True:
        reachable, missing = reach.optimistic()
        sample = scene_sampling.sample_scenes(boundary_points, rollout_points, reachable=reachable, **options)
        if not missing:
            return sample
        if prefetch_factor > 0:
            _prefetch(reach, boundary_points, rollout_points, missing, prefetch_factor, options)
            prefetch_factor *= 2     # a miss after a cloud means the cloud was too shallow: the next one is twice as deep
        reach.evaluate(missing)


def sample_joint_with_reachability(boundary_points, rollout_points, reach: FivePoseReachability, *, prefetch_factor: float = 0.0, **options):
    """``sample_with_reachability`` for ``scene_sampling.sample_joint``."""

    while True:
        reachable, missing = reach.optimistic()
        sample = scene_sampling.sample_joint(boundary_points, rollout_points, reachable=reachable, **options)
        if not missing:
            return sample
        if prefetch_factor > 0:
            _prefetch(reach, boundary_points, rollout_points, missing, prefetch_factor, options)
            prefetch_factor *= 2     # a miss after a cloud means the cloud was too shallow: the next one is twice as deep
        reach.evaluate(missing)


def build_rows(sample: scene_sampling.SceneSample, prefix: str) -> list[dict]:
    ordered = [(split, p) for split in SPLIT_ORDER for p, s in zip(sample.points, sample.splits) if s == split]
    return [scene_row(f"{prefix}-{i:03d}", SEED_BASE + i, split, p) for i, (split, p) in enumerate(ordered)]


def parse_lists(text: str) -> dict[str, int]:
    """``formal:103,qualification:40,functional:8`` -> ordered counts; the names must be those of ``JOINT_LISTS``."""

    counts: dict[str, int] = {}
    for item in text.split(","):
        name, _, number = item.partition(":")
        if name not in JOINT_LISTS or name in counts or not number.isdigit() or int(number) < 1:
            raise ValueError(f"SCENE_SAMPLE_LISTS_INVALID: {item!r}")
        counts[name] = int(number)
    if JOINT_SPLIT_LIST not in counts or len(counts) < 2:
        raise ValueError("SCENE_SAMPLE_LISTS_INVALID: need the formal list and at least one more")
    return counts


def build_joint_rows(sample: scene_sampling.JointSceneSample, name: str) -> list[dict]:
    prefix, seed_base, split_name = JOINT_LISTS[name]
    points = sample.lists[name]
    if split_name is None:
        ordered = [(split, p) for split in SPLIT_ORDER for p, s in zip(points, sample.splits) if s == split]
    else:
        ordered = [(split_name, p) for p in points]
    width = 3 if len(points) > 100 else 2
    return [scene_row(f"{prefix}-{i:0{width}d}", seed_base + i, split, p) for i, (split, p) in enumerate(ordered)]


def main_joint(args, reach_calls) -> int:
    counts = parse_lists(args.lists)
    if args.scenes_output_dir is None:
        raise ValueError("SCENE_SAMPLE_OUTPUT_DIR_REQUIRED")
    targets = {name: args.scenes_output_dir / f"{name}-{count}.scenes.json" for name, count in counts.items()}
    for target in (*targets.values(), args.report_output):
        if target.exists() or target.is_symlink():
            raise ValueError(f"OUTPUT_EXISTS: {target}")
    state = json.loads(args.state.read_text())
    boundary_points = state.get("boundary_points")
    if not isinstance(boundary_points, dict):
        raise ValueError("SCENE_SAMPLE_BOUNDARY_NOT_FINISHED")
    boundary_kinds = state.get("boundary_kinds")
    rollout = {s["point_id"]: tuple(s["xy"]) for s in rollout_scenes.load_standard_points(args.rollout_points)}
    split_counts = dict(zip(SPLIT_ORDER, args.split_counts))
    if sum(split_counts.values()) != counts[JOINT_SPLIT_LIST]:
        split_counts = {"train": counts[JOINT_SPLIT_LIST] - 20, "validation": 10, "offline_test": 10}
    reach = FivePoseReachability(reach_calls[0], pool=reach_calls if len(reach_calls) > 1 else None)
    sample = sample_joint_with_reachability(
        {name: tuple(p) for name, p in boundary_points.items()}, rollout, reach, prefetch_factor=args.prefetch_factor,
        list_counts=counts, split_list=JOINT_SPLIT_LIST, split_counts=split_counts, seed=args.seed,
        margin_m=args.inward_margin_m, boundary_kinds=boundary_kinds,
    )
    region = scene_sampling.Region(sample.polygon, args.inward_margin_m, vertex_scales=scene_sampling.vertex_scales(boundary_kinds))
    args.scenes_output_dir.mkdir(parents=True, exist_ok=True)
    generator_common = {
        "seed": args.seed, "region": "polygon through the eight boundary points, eroded by the inward margin",
        "inward_margin_m": args.inward_margin_m, "min_spacing_m": sample.spacing_m,
        "inward_margin_rule": "full margin on reach-limited edges, none on hard-limit edges, linear taper on mixed edges",
        "place_exclusion_m": scene_sampling.boundary.PLACE_EXCLUSION_M,
        "boundary_kinds": dict(zip(scene_sampling.boundary.RAY_NAMES, sample.boundary_kinds)),
        "min_spacing_floor_m": scene_sampling.MIN_SPACING_FLOOR_M,
        "boundary_state": str(args.state), "reachability_filter": "task_reachability, five poses, keep when all REACHABLE",
        "joint_sample": {"lists": counts, "assignment": "k-means strata, smallest list first, one point per stratum nearest its centroid; the largest list is the rest",
                         "design": "boundary design amendment 3: one Poisson-disk sample, every pair of all lists at least min_spacing_m apart"},
    }
    sha256 = {}
    list_info = {}
    for name, count in counts.items():
        rows = build_joint_rows(sample, name)
        quota = split_counts if JOINT_LISTS[name][2] is None else {JOINT_LISTS[name][2]: count}
        document = scene_document(f"{name}-{count}-joint", rows, cup_z_m=CUP_Z_M, generator=dict(generator_common, list=name, first_seed=JOINT_LISTS[name][1]),
                                  split_quota=quota)
        write_new_json(targets[name], document)
        sha256[name] = hashlib.sha256(targets[name].read_bytes()).hexdigest()
        points = sample.lists[name]
        within = [math.dist(a, b) for i, a in enumerate(points) for b in points[:i]]
        list_info[name] = {
            "count": count, "path": str(targets[name]), "sha256": sha256[name], "first_seed": JOINT_LISTS[name][1], "scene_id_prefix": JOINT_LISTS[name][0],
            "nearest_pair_within_m": round(min(within), 6),
            "rollout_nearest_scene_m": sample.rollout_nearest_scene_m[name],
        }
    everything = [p for points in sample.lists.values() for p in points]
    pairs = [math.dist(a, b) for i, a in enumerate(everything) for b in everything[:i]]
    cross = {}
    names = list(counts)
    for i, a in enumerate(names):
        for b in names[:i]:
            cross[f"{a}-{b}"] = round(min(math.dist(p, q) for p in sample.lists[a] for q in sample.lists[b]), 6)
    rejected = sum(1 for e in reach.pose_log if e["label"] == "true" and e["status"] != "REACHABLE")
    report = {
        "kind": "ACT_SCENE_SAMPLE_REPORT", "schema_version": 2, "mode": "joint", "scene_count": len(everything), "lists": list_info,
        "region_polygon": [list(p) for p in sample.polygon], "shrunk_region_polygon": [list(p) for p in sample.shrunk_polygon],
        "region_area_m2": sample.area_m2, "min_spacing_m": sample.spacing_m, "nearest_pair_m": round(min(pairs), 6),
        "nearest_pair_across_lists_m": cross,
        "split_counts": {s: sample.splits.count(s) for s in SPLIT_ORDER},
        "boundary_kinds": dict(zip(scene_sampling.boundary.RAY_NAMES, sample.boundary_kinds)),
        "place_exclusion_m": scene_sampling.boundary.PLACE_EXCLUSION_M,
        "rollout_region": {
            name: {"inside_region": region.contains((float(p[0]), float(p[1]))),
                   "edge_distance_m": round(scene_sampling.distance_to_polygon_edge((float(p[0]), float(p[1])), sample.polygon), DECIMALS_REPORT)}
            for name, p in rollout.items()
        },
        "positions_rejected_by_reachability": rejected, "reachability_calls": reach.calls, "seed": args.seed,
        "reachability_pool_size": len(reach_calls),
    }
    write_new_json(args.report_output, report)
    print(json.dumps({"lists": sha256, "report": str(args.report_output), "min_spacing_m": sample.spacing_m}, sort_keys=True))
    return 0


def main(argv: list[str] | None = None, *, reach_call=None, reach_pool=None) -> int:
    parser = argparse.ArgumentParser(prog="act_scene_sample", description=__doc__)
    parser.add_argument("--state", type=Path, required=True, help="finished boundary state with boundary_points")
    parser.add_argument("--rollout-points", type=Path, required=True, help="config/mujoco/rgbd_task_points.yaml")
    parser.add_argument("--scenes-output", type=Path, help="the scene list (single-list mode)")
    parser.add_argument("--lists", help="joint mode (amendment 3), e.g. formal:103,qualification:40,functional:8: one sample divided into lists")
    parser.add_argument("--scenes-output-dir", type=Path, help="joint mode: where <name>-<count>.scenes.json are written")
    parser.add_argument("--report-output", type=Path, required=True)
    parser.add_argument("--call-dir", type=Path, required=True, help="per-call points and evidence files (kept)")
    parser.add_argument("--reach-command", action="append",
                        help="command prefix that runs task_reachability; points, evidence, session appended. Repeat it for several "
                             "execution stacks: the planner batches then run at the same time, one per stack")
    parser.add_argument("--prefetch-factor", type=float, default=DEFAULT_PREFETCH_FACTOR,
                        help="evaluate the true poses of all candidates up to this multiple of the deepest draw the sampler's first "
                             "pass needs in one round (>= 1), 0 = off. The scenes are the same either way")
    parser.add_argument("--count", type=int, default=scene_sampling.DEFAULT_COUNT)
    parser.add_argument("--split-counts", type=int, nargs=3, metavar=("TRAIN", "VALIDATION", "OFFLINE_TEST"), default=(83, 10, 10))
    parser.add_argument("--seed", type=int, default=scene_sampling.DEFAULT_SEED)
    parser.add_argument("--inward-margin-m", type=float, default=scene_sampling.INWARD_MARGIN_M)
    parser.add_argument("--scene-prefix", default="frm")
    args = parser.parse_args(argv)

    if args.prefetch_factor != 0 and args.prefetch_factor < 1:
        raise ValueError("SCENE_SAMPLE_PREFETCH_FACTOR_INVALID")
    if reach_call is None:
        if not args.reach_command:
            raise ValueError("SCENE_SAMPLE_REACHABILITY_PROBE_NOT_AVAILABLE")
        reach_pool = [CommandReachabilityCall(shlex.split(command), args.call_dir, session_prefix="sample" if i == 0 else f"sample-s{i}")
                      for i, command in enumerate(args.reach_command)]
        reach_call = reach_pool[0]
    reach_calls = list(reach_pool) if reach_pool else [reach_call]
    if args.lists is not None:
        return main_joint(args, reach_calls)
    if args.scenes_output is None:
        raise ValueError("SCENE_SAMPLE_OUTPUT_REQUIRED")
    for target in (args.scenes_output, args.report_output):
        if target.exists() or target.is_symlink():
            raise ValueError(f"OUTPUT_EXISTS: {target}")
    state = json.loads(args.state.read_text())
    boundary_points = state.get("boundary_points")
    if not isinstance(boundary_points, dict):
        raise ValueError("SCENE_SAMPLE_BOUNDARY_NOT_FINISHED")
    boundary_kinds = state.get("boundary_kinds")  # absent in states of the 1 cm search: every point is then reach-limited
    rollout = {s["point_id"]: tuple(s["xy"]) for s in rollout_scenes.load_standard_points(args.rollout_points)}
    counts = dict(zip(SPLIT_ORDER, args.split_counts))
    reach = FivePoseReachability(reach_calls[0], pool=reach_calls if len(reach_calls) > 1 else None)
    sample = sample_with_reachability(
        {name: tuple(p) for name, p in boundary_points.items()}, rollout, reach, prefetch_factor=args.prefetch_factor,
        count=args.count, split_counts=counts, seed=args.seed, margin_m=args.inward_margin_m,
        boundary_kinds=boundary_kinds,
    )
    region = scene_sampling.Region(sample.polygon, args.inward_margin_m, vertex_scales=scene_sampling.vertex_scales(boundary_kinds))
    rows = build_rows(sample, args.scene_prefix)
    rejected = sum(1 for e in reach.pose_log if e["label"] == "true" and e["status"] != "REACHABLE")
    generator = {
        "seed": args.seed, "region": "polygon through the eight boundary points, eroded by the inward margin",
        "inward_margin_m": args.inward_margin_m, "min_spacing_m": sample.spacing_m,
        "inward_margin_rule": "full margin on reach-limited edges, none on hard-limit edges, linear taper on mixed edges",
        "place_exclusion_m": scene_sampling.boundary.PLACE_EXCLUSION_M,
        "boundary_kinds": dict(zip(scene_sampling.boundary.RAY_NAMES, sample.boundary_kinds)),
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
        "boundary_kinds": dict(zip(scene_sampling.boundary.RAY_NAMES, sample.boundary_kinds)),
        "place_exclusion_m": scene_sampling.boundary.PLACE_EXCLUSION_M,
        "rollout_region": {
            name: {"inside_region": region.contains((float(p[0]), float(p[1]))),
                   "edge_distance_m": round(scene_sampling.distance_to_polygon_edge((float(p[0]), float(p[1])), sample.polygon), DECIMALS_REPORT)}
            for name, p in rollout.items()
        },
        "rollout_nearest_scene_m": sample.rollout_nearest_scene_m,
        "rollout_nearest_training_m": sample.rollout_nearest_training_m,
        "positions_rejected_by_reachability": rejected, "reachability_calls": reach.calls, "seed": args.seed,
        "reachability_pool_size": len(reach_calls),
    }
    write_new_json(args.scenes_output, document)
    write_new_json(args.report_output, report)
    print(json.dumps({"scenes": str(args.scenes_output), "report": str(args.report_output), "min_spacing_m": sample.spacing_m}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
