#!/usr/bin/env python3
"""Does a light reachability stack answer like a full execution stack?

Input: for each stack kind, one or more repeats of the same points, each a task_reachability output ({"reports": [{point_id, status,
first_failure_code, ...}]}). A point's verdict is (status, first_failure_code). Defined boundary tolerance: a point is *borderline* when its
verdict is not the same across the repeats of one stack kind (the planner decides it on a numerical knife edge, e.g. the 1/734 point of the
first measurement flips about 1 in 12 calls on the full stack too). A difference between the kinds is tolerated only on a borderline point;
on a stable point it is a hard mismatch. Equivalent = at least one point and no hard mismatch. Exit 1 on a hard mismatch.

usage: compare_verdicts.py --full F.json [F.json ...] --light L.json [L.json ...]
"""
import argparse
import json
import sys


def load(path):
    with open(path) as handle:
        return {r["point_id"]: {"status": r["status"], "first_failure_code": r["first_failure_code"]} for r in json.load(handle)["reports"]}


def _key(verdict):
    return (verdict["status"], verdict["first_failure_code"])


def compare(full, light):
    """full, light: lists of {point_id: verdict} (one per repeat)."""
    ids = set().union(*full, *light) if (full or light) else set()
    equal, borderline, hard = 0, [], []
    for point in sorted(ids):
        sides = []
        for repeats in (full, light):
            seen = {_key(r[point]) for r in repeats if point in r}
            missing = any(point not in r for r in repeats) or not repeats
            sides.append((seen, missing))
        (full_seen, full_missing), (light_seen, light_missing) = sides
        if full_missing or light_missing:
            hard.append(point)
        elif len(full_seen) == 1 and full_seen == light_seen:
            equal += 1
        elif len(full_seen) > 1 or len(light_seen) > 1:
            borderline.append(point)
        else:
            hard.append(point)
    return {"points": len(ids), "equal": equal, "borderline": borderline, "hard_mismatch": hard,
            "equivalent": bool(ids) and not hard}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--full", nargs="+", required=True)
    parser.add_argument("--light", nargs="+", required=True)
    args = parser.parse_args(argv)
    result = compare([load(p) for p in args.full], [load(p) for p in args.light])
    json.dump(result, sys.stdout, indent=2)
    print()
    return 0 if result["equivalent"] else 1


if __name__ == "__main__":
    sys.exit(main())
