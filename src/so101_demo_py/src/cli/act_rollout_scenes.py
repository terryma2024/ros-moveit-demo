"""CLI (evidence side, stub): write the rollout scene list of one policy evaluation.

The pure rules live in `so101_demo.act.rollout_scenes`. What this command adds is the I/O around them: it reads the standard task
points, the anchor triangle and the taken training scenes, asks a reachability probe about each candidate point and writes the scene
list once. The live probe (`task_reachability` against the native stack, five Teacher poses per point, plain decimals) is run by the
evidence-side generator and is NOT part of this module: without an injected `reachable_factory` the command refuses
(`ROLLOUT_REACHABILITY_PROBE_NOT_AVAILABLE`) and writes nothing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from so101_demo.act import rollout_scenes as scenes_module


def _taken_xy(paths) -> list:
    points = []
    for path in paths:
        document = json.loads(Path(path).read_bytes())
        rows = document.get("scenarios") or document.get("scenes") if isinstance(document, dict) else None
        if not isinstance(rows, list):
            raise ValueError("ROLLOUT_TAKEN_SCENES_INVALID")
        for row in rows:
            points.append((float(row["xy"][0]), float(row["xy"][1])))
    return points


def main(argv: list[str] | None = None, *, reachable_factory=None) -> int:
    parser = argparse.ArgumentParser(prog="act_rollout_scenes", description=__doc__)
    parser.add_argument("--points", type=Path, required=True, help="config/mujoco/rgbd_task_points.yaml")
    parser.add_argument("--anchors", type=Path, required=True, help="config/act/pick-place-live-anchors.yaml")
    parser.add_argument("--taken-scenes", type=Path, nargs="+", required=True,
                        help="the scene lists of the training data (their xy are the taken points)")
    parser.add_argument("--place-xy", type=float, nargs=2, required=True, metavar=("X", "Y"),
                        help="the Teacher place target xy of the frozen execution snapshot")
    parser.add_argument("--reset-z-m", type=float, default=0.165)
    parser.add_argument("--validation-count", type=int, default=20)
    parser.add_argument("--test-count", type=int, default=20)
    parser.add_argument("--extrapolation-count", type=int, default=0)
    parser.add_argument("--extrapolation-x", type=float, nargs=2, default=(0.03, 0.07), metavar=("X0", "X1"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    if reachable_factory is None:
        raise ValueError("ROLLOUT_REACHABILITY_PROBE_NOT_AVAILABLE")
    if args.output.exists() or args.output.is_symlink():
        raise ValueError("ROLLOUT_SCENES_OUTPUT_EXISTS")
    reachable = reachable_factory()
    triangle = scenes_module.anchor_triangle(args.anchors)
    taken = _taken_xy(args.taken_scenes)
    place = tuple(args.place_xy)
    standard = scenes_module.load_standard_points(args.points, triangle=triangle, taken_xy=taken)
    groups = {scenes_module.GROUP_STANDARD: standard}
    occupied = [tuple(scene["xy"]) for scene in standard]
    triangle_region = {"kind": "triangle", "vertices": triangle}
    plan = [(scenes_module.GROUP_VALIDATION, args.validation_count, triangle_region),
            (scenes_module.GROUP_TEST, args.test_count, triangle_region)]
    if args.extrapolation_count:
        ys = [vertex[1] for vertex in triangle]
        plan.append((scenes_module.GROUP_EXTRAPOLATION, args.extrapolation_count,
                     {"kind": "box", "x": tuple(args.extrapolation_x), "y": (min(ys), max(ys)),
                      "exclude_triangle": triangle}))
    seeds = {**scenes_module.SEEDS, scenes_module.GROUP_EXTRAPOLATION: scenes_module.SEEDS[
        scenes_module.GROUP_TEST] + 1}
    for group, count, region in plan:
        if count < 1:
            continue
        sampled = scenes_module.sample_group(
            group=group, seed=seeds[group], count=count, region=region, place_xy=place, reachable=reachable,
            taken_xy=taken, rollout_xy=occupied, reset_z_m=args.reset_z_m)
        groups[group] = sampled
        occupied += [tuple(scene["xy"]) for scene in sampled]
    document = scenes_module.build_scene_document(groups, parameters={
        "place_xy": list(place), "triangle": [list(vertex) for vertex in triangle],
        "place_exclusion_m": scenes_module.PLACE_EXCLUSION_M, "min_gap_within_m": scenes_module.MIN_GAP_WITHIN_M,
        "min_gap_to_taken_m": scenes_module.MIN_GAP_TO_TAKEN_M, "taken_count": len(taken),
        "seeds": {group: seeds[group] for group, count, _region in plan if count >= 1}})
    scenes_module.verify_scene_document(document, taken_xy=taken, place_xy=place)
    args.output.write_text(json.dumps(document, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "manifest_sha256": document["manifest_sha256"],
                      "groups": {name: len(items) for name, items in groups.items()}}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
