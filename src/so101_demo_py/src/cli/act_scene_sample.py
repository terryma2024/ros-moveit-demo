"""CLI (evidence side): the final scene list inside the Teacher success boundary, plus a report.

Reads the finished boundary state (``act_boundary_update`` output with ``boundary_points``) and the standard rollout
points, samples about 103 scenes by seeded Poisson-disk sampling, splits them spatially (83 / 10 / 10) and writes the
scene list in the container-campaign format.  Every scene also passes the five-pose Teacher reachability filter, which
needs the native ACT execution stack: ``--reach-command`` is the same command prefix as for ``act_boundary_prefilter``.
A rollout point outside the region stops the command (``ROLLOUT_POINT_OUTSIDE_REGION``) and nothing is written.

R3-a re-filter: the five-pose filter runs before the scenes have their final ids, so it cannot carry a Teacher execution policy with
per-episode diversity values (they derive from the scene id). With ``--refilter-command`` and ``--refilter-policy`` every written list is
then checked again, one point per scene with the FINAL scene id as point id, under that policy (``refilter_scenes``); a scene that is not
REACHABLE under its own values is dropped from the list and named in the report, and an UNKNOWN verdict stops the command. The re-filter
alone, on an existing list, is ``--refilter-scenes``. The dropped rows leave gaps in the numbering; the ids never change.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shlex
import subprocess
from collections import Counter
from functools import partial
from pathlib import Path

from so101_demo.act import rollout_scenes, scene_sampling
from so101_demo.act.five_pose_reachability import (
    DEFAULT_BATCH_POSES, CommandReachabilityCall, FivePoseReachability, refilter_scenes)
from so101_demo.act.scene_list_format import CUP_Z_M, read_scene_rows, scene_document, scene_row, write_new_json

SEED_BASE = 200
#: Joint mode (boundary design amendment 3): list name -> (scene id prefix, first row seed, split name of its rows; ``None`` = split spatially).
JOINT_LISTS = {"formal": ("frm", 200, None), "qualification": ("qual", 400, "qualification"), "functional": ("fn", 600, "functional")}
JOINT_SPLIT_LIST = "formal"
DECIMALS_REPORT = 6
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


def sample_joint_with_reachability(boundary_points, rollout_points, reach: FivePoseReachability, **options):
    """``sample_with_reachability`` for ``scene_sampling.sample_joint``."""

    while True:
        reachable, missing = reach.optimistic()
        sample = scene_sampling.sample_joint(boundary_points, rollout_points, reachable=reachable, **options)
        if not missing:
            return sample
        reach.evaluate(missing)


#: the environment variable `scripts/reach/reach_call.zsh` reads for the Teacher execution policy of a call
REFILTER_POLICY_ENV = "REACH_TEACHER_POLICY"


def refilter_call_from(command: str, directory: Path, policy: Path, *, run=subprocess.run) -> CommandReachabilityCall:
    """The re-filter's planner call: `command` (a reach-call prefix) with the Teacher execution policy `policy` in its environment, and
    the permission to carry that policy, which only a call keyed by the final scene ids has (`per_scene_ids`)."""

    environment = {**os.environ, REFILTER_POLICY_ENV: str(policy)}
    return CommandReachabilityCall(shlex.split(command), directory, session_prefix="refilter", per_scene_ids=True,
                                   run=partial(run, env=environment))


def refilter_list(rows: list[dict], call, policy: dict) -> tuple[list[dict], dict]:
    """`(kept rows, record)`: the re-filter of one list under `policy` (`{"path", "sha256"}`); the record names every dropped scene."""

    kept, rejected = refilter_scenes(rows, call)
    if not kept:
        raise ValueError("SCENE_SAMPLE_REFILTER_EMPTY")
    return kept, {"policy": policy, "input_count": len(rows), "kept_count": len(kept), "rejected": rejected}


def _quota(rows: list[dict]) -> dict:
    return dict(Counter(row["split"] for row in rows))


def _policy_ref(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"SCENE_SAMPLE_REFILTER_POLICY_MISSING: {path}")
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main_refilter_only(args, call, policy: dict) -> int:
    """``--refilter-scenes``: the re-filter of an existing list into ``--scenes-output`` and ``--report-output``."""

    for target in (args.scenes_output, args.report_output):
        if target is None or target.exists() or target.is_symlink():
            raise ValueError(f"OUTPUT_EXISTS: {target}")
    source = args.refilter_scenes
    rows = read_scene_rows(source)
    kept, record = refilter_list(rows, call, policy)
    original = json.loads(source.read_text())
    document = scene_document(original.get("list", source.stem), kept, cup_z_m=original.get("cup_z_m", CUP_Z_M),
                              generator=dict(original.get("generator", {}), refilter=dict(record, source={
                                  "path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()})),
                              split_quota=_quota(kept))
    write_new_json(args.scenes_output, document)
    report = {"kind": "ACT_SCENE_REFILTER_REPORT", "schema_version": 1, "refilter": record,
              "output": {"path": str(args.scenes_output), "sha256": hashlib.sha256(args.scenes_output.read_bytes()).hexdigest()}}
    write_new_json(args.report_output, report)
    print(json.dumps({"scenes": str(args.scenes_output), "kept": len(kept), "rejected": len(record["rejected"])}, sort_keys=True))
    return 0


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


def main_joint(args, reach_calls, refilter=None) -> int:
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
    reach = FivePoseReachability(reach_calls[0], batch_poses=args.batch_poses, pool=reach_calls if len(reach_calls) > 1 else None)
    sample = sample_joint_with_reachability(
        {name: tuple(p) for name, p in boundary_points.items()}, rollout, reach,
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
        generator = dict(generator_common, list=name, first_seed=JOINT_LISTS[name][1])
        record = None
        if refilter is not None:
            rows, record = refilter_list(rows, *refilter)
            generator["refilter"] = record
            quota = _quota(rows)
        document = scene_document(f"{name}-{count}-joint", rows, cup_z_m=CUP_Z_M, generator=generator, split_quota=quota)
        write_new_json(targets[name], document)
        sha256[name] = hashlib.sha256(targets[name].read_bytes()).hexdigest()
        points = [tuple(row["cup_position_world_m"][:2]) for row in rows] if record is not None else sample.lists[name]
        sample.lists[name] = points
        within = [math.dist(a, b) for i, a in enumerate(points) for b in points[:i]]
        list_info[name] = {
            "count": len(rows), "path": str(targets[name]), "sha256": sha256[name], "first_seed": JOINT_LISTS[name][1], "scene_id_prefix": JOINT_LISTS[name][0],
            "nearest_pair_within_m": round(min(within), 6) if within else None,
            "rollout_nearest_scene_m": sample.rollout_nearest_scene_m[name],
        }
        if record is not None:
            list_info[name]["sampled_count"] = count
            list_info[name]["refilter"] = record
    everything = [p for points in sample.lists.values() for p in points]
    pairs = [math.dist(a, b) for i, a in enumerate(everything) for b in everything[:i]]
    cross = {}
    names = list(counts)
    for i, a in enumerate(names):
        for b in names[:i]:
            cross[f"{a}-{b}"] = round(min(math.dist(p, q) for p in sample.lists[a] for q in sample.lists[b]), 6)
    rejected = sum(1 for e in reach.pose_log if e["label"] == "true" and e["status"] != "REACHABLE")
    split_report = ({s: sample.splits.count(s) for s in SPLIT_ORDER} if refilter is None
                    else {s: n for s, n in _quota(read_scene_rows(targets[JOINT_SPLIT_LIST])).items()})
    report = {
        "kind": "ACT_SCENE_SAMPLE_REPORT", "schema_version": 2, "mode": "joint", "scene_count": len(everything), "lists": list_info,
        "region_polygon": [list(p) for p in sample.polygon], "shrunk_region_polygon": [list(p) for p in sample.shrunk_polygon],
        "region_area_m2": sample.area_m2, "min_spacing_m": sample.spacing_m, "nearest_pair_m": round(min(pairs), 6),
        "nearest_pair_across_lists_m": cross,
        "split_counts": split_report,
        "boundary_kinds": dict(zip(scene_sampling.boundary.RAY_NAMES, sample.boundary_kinds)),
        "place_exclusion_m": scene_sampling.boundary.PLACE_EXCLUSION_M,
        "rollout_region": {
            name: {"inside_region": region.contains((float(p[0]), float(p[1]))),
                   "edge_distance_m": round(scene_sampling.distance_to_polygon_edge((float(p[0]), float(p[1])), sample.polygon), DECIMALS_REPORT)}
            for name, p in rollout.items()
        },
        "positions_rejected_by_reachability": rejected, "reachability_calls": reach.calls, "seed": args.seed,
        "reachability_pool_size": len(reach_calls), "batch_poses": args.batch_poses,
    }
    write_new_json(args.report_output, report)
    print(json.dumps({"lists": sha256, "report": str(args.report_output), "min_spacing_m": sample.spacing_m}, sort_keys=True))
    return 0


def main(argv: list[str] | None = None, *, reach_call=None, reach_pool=None, refilter_call=None) -> int:
    parser = argparse.ArgumentParser(prog="act_scene_sample", description=__doc__)
    parser.add_argument("--state", type=Path, help="finished boundary state with boundary_points")
    parser.add_argument("--rollout-points", type=Path, help="config/mujoco/rgbd_task_points.yaml")
    parser.add_argument("--scenes-output", type=Path, help="the scene list (single-list mode)")
    parser.add_argument("--lists", help="joint mode (amendment 3), e.g. formal:103,qualification:40,functional:8: one sample divided into lists")
    parser.add_argument("--scenes-output-dir", type=Path, help="joint mode: where <name>-<count>.scenes.json are written")
    parser.add_argument("--report-output", type=Path, required=True)
    parser.add_argument("--call-dir", type=Path, required=True, help="per-call points and evidence files (kept)")
    parser.add_argument("--stacks", type=int, help="run the --reach-command template on this many execution stacks; the text {slot} in the command "
                        "is replaced by 0, 1, ... so each stack gets its own container and call directory")
    parser.add_argument("--batch-poses", type=int, default=DEFAULT_BATCH_POSES,
                        help="most poses in one planner call (a short batch is cut into one share per stack first)")
    parser.add_argument("--reach-command", action="append",
                        help="command prefix that runs task_reachability; points, evidence, session appended. Repeat it for several "
                             "execution stacks: the planner batches then run at the same time, one per stack")
    parser.add_argument("--count", type=int, default=scene_sampling.DEFAULT_COUNT)
    parser.add_argument("--split-counts", type=int, nargs=3, metavar=("TRAIN", "VALIDATION", "OFFLINE_TEST"), default=(83, 10, 10))
    parser.add_argument("--seed", type=int, default=scene_sampling.DEFAULT_SEED)
    parser.add_argument("--inward-margin-m", type=float, default=scene_sampling.INWARD_MARGIN_M)
    parser.add_argument("--scene-prefix", default="frm")
    parser.add_argument("--refilter-command", help="R3-a: command prefix of the re-filter's planner calls (the same form as --reach-command, one stack); "
                        "every written list is then checked again with the final scene ids as point ids under --refilter-policy")
    parser.add_argument("--refilter-policy", type=Path, help="R3-a: the schema 6 Teacher execution policy the re-filter runs under, as the planner's container "
                        "sees it (it is given to the call in REACH_TEACHER_POLICY and recorded with its sha256)")
    parser.add_argument("--refilter-scenes", type=Path, help="R3-a: only re-filter this existing scene list into --scenes-output (no sampling)")
    args = parser.parse_args(argv)

    refilter = None
    if args.refilter_command is not None or args.refilter_policy is not None or refilter_call is not None or args.refilter_scenes is not None:
        if args.refilter_policy is None or (refilter_call is None and args.refilter_command is None):
            raise ValueError("SCENE_SAMPLE_REFILTER_NEEDS_COMMAND_AND_POLICY")
        policy = _policy_ref(args.refilter_policy)
        refilter = (refilter_call or refilter_call_from(args.refilter_command, args.call_dir, args.refilter_policy), policy)
    if args.refilter_scenes is not None:
        return main_refilter_only(args, *refilter)
    if args.state is None or args.rollout_points is None:
        raise ValueError("SCENE_SAMPLE_STATE_AND_ROLLOUT_POINTS_REQUIRED")

    if args.batch_poses < 1:
        raise ValueError("SCENE_SAMPLE_BATCH_POSES_INVALID")
    if args.stacks is not None:
        if args.stacks < 1:
            raise ValueError("SCENE_SAMPLE_STACKS_INVALID")
        if args.reach_command and len(args.reach_command) > 1:
            raise ValueError("SCENE_SAMPLE_STACKS_WITH_REPEATED_COMMANDS")
        if args.reach_command and args.stacks > 1 and "{slot}" not in args.reach_command[0]:
            raise ValueError("SCENE_SAMPLE_STACKS_NEED_SLOT")
        if args.reach_command:
            args.reach_command = [args.reach_command[0].replace("{slot}", str(i)) for i in range(args.stacks)]
    if reach_call is None:
        if not args.reach_command:
            raise ValueError("SCENE_SAMPLE_REACHABILITY_PROBE_NOT_AVAILABLE")
        reach_pool = [CommandReachabilityCall(shlex.split(command), args.call_dir, session_prefix="sample" if i == 0 else f"sample-s{i}")
                      for i, command in enumerate(args.reach_command)]
        reach_call = reach_pool[0]
    reach_calls = list(reach_pool) if reach_pool else [reach_call]
    if args.lists is not None:
        return main_joint(args, reach_calls, refilter)
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
    reach = FivePoseReachability(reach_calls[0], batch_poses=args.batch_poses, pool=reach_calls if len(reach_calls) > 1 else None)
    sample = sample_with_reachability(
        {name: tuple(p) for name, p in boundary_points.items()}, rollout, reach,
        count=args.count, split_counts=counts, seed=args.seed, margin_m=args.inward_margin_m,
        boundary_kinds=boundary_kinds,
    )
    region = scene_sampling.Region(sample.polygon, args.inward_margin_m, vertex_scales=scene_sampling.vertex_scales(boundary_kinds))
    rows = build_rows(sample, args.scene_prefix)
    sampled_count = len(rows)
    refilter_record = None
    if refilter is not None:
        rows, refilter_record = refilter_list(rows, *refilter)
        counts = _quota(rows)
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
    if refilter_record is not None:
        generator["refilter"] = refilter_record
    document = scene_document(f"{args.scene_prefix}-boundary-{len(rows)}", rows, cup_z_m=CUP_Z_M, generator=generator, split_quota=counts)
    points = [tuple(row["cup_position_world_m"][:2]) for row in rows]
    pairs = [math.dist(a, b) for i, a in enumerate(points) for b in points[:i]]
    report = {
        "kind": "ACT_SCENE_SAMPLE_REPORT", "schema_version": 1, "scene_count": len(rows),
        **({} if refilter_record is None else {"sampled_count": sampled_count, "refilter": refilter_record}),
        "region_polygon": [list(p) for p in sample.polygon], "shrunk_region_polygon": [list(p) for p in sample.shrunk_polygon],
        "region_area_m2": sample.area_m2, "min_spacing_m": sample.spacing_m, "nearest_pair_m": round(min(pairs), 6),
        "split_counts": {s: sample.splits.count(s) for s in SPLIT_ORDER} if refilter_record is None else {s: counts.get(s, 0) for s in SPLIT_ORDER},
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
        "reachability_pool_size": len(reach_calls), "batch_poses": args.batch_poses,
    }
    write_new_json(args.scenes_output, document)
    write_new_json(args.report_output, report)
    print(json.dumps({"scenes": str(args.scenes_output), "report": str(args.report_output), "min_spacing_m": sample.spacing_m}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
