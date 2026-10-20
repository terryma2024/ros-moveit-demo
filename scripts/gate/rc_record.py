#!/usr/bin/env python3
"""Record and decision helper for the ros2_control test-skip rule of the fast Host gate.

Run with `python3 -I`. Subcommands:

  decide  --gates DIR --seed FILE --tree HASH --dirty N --apt HASH --full 0|1 --out FILE
          Prints `skip` or `run` on stdout and writes the decision document to --out.
  finish  --decision FILE --gate DIR --colcon-rc N --out FILE
          Writes the per-gate record <gate>/ros2-control-tests.json after the colcon stage.
  seed    --gate DIR --tree HASH --apt HASH --note TEXT --out FILE
          Derives the baseline from an existing gate directory's results (read only).
  tools   --repo DIR --out FILE
          Records the git commit of the gate tools (scripts/gate of the repository under test) and the
          `git diff --stat` of that directory. Prints the commit; exits 1 when scripts/gate is not clean.

Skip rule (all must hold, otherwise RUN):
  1. not --full;
  2. the tracked and untracked state of third_party/ros2_control is clean (dirty == 0);
  3. a baseline exists: the newest record (by recorded_at_epoch) among
     <gates>/*/ros2-control-tests.json and the seed file with ran == true and green == true;
  4. baseline.tree == the git tree object id of third_party/ros2_control at HEAD;
  5. baseline.apt_hash == the hash of the installed ros-jazzy-* package versions now
     (the two packages also link the system ros2_control libraries, so an apt change invalidates it).
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

PACKAGES = ("controller_manager", "hardware_interface_testing")
SUMMARY = re.compile(r"(\S+\.xunit\.xml|\S+\.gtest\.xml): (\d+) tests, (\d+) errors, (\d+) failures, (\d+) skipped")


def load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def candidates(gates, seed, record="ros2-control-tests.json"):
    found = []
    gates = Path(gates)
    for path in sorted(gates.glob("*/" + record)):
        found.append((path, load(path)))
    found.append((Path(seed), load(seed)))
    return [(p, d) for p, d in found if isinstance(d, dict)]


def decide(a):
    reasons = []
    baseline = None
    baseline_path = None
    good = [
        (p, d)
        for p, d in candidates(a.gates, a.seed, a.record_name)
        if d.get("ran") is True and d.get("green") is True and d.get("tree") and d.get("recorded_at_epoch")
    ]
    if good:
        baseline_path, baseline = max(good, key=lambda item: item[1]["recorded_at_epoch"])
    decision = "skip"
    if a.full:
        decision = "run"
        reasons.append("--full requested")
    if a.dirty:
        decision = "run"
        reasons.append(f"working tree under {a.label} is dirty ({a.dirty} entries)")
    if baseline is None:
        decision = "run"
        reasons.append("no green baseline record found")
    else:
        if baseline["tree"] != a.tree:
            decision = "run"
            reasons.append(f"tree differs: baseline {baseline['tree']} vs HEAD {a.tree}")
        if baseline.get("apt_hash") != a.apt:
            decision = "run"
            reasons.append(f"installed ros-jazzy package set differs: baseline {baseline.get('apt_hash')} vs now {a.apt}")
    if decision == "skip":
        reasons.append(f"tree {a.tree} equals the tree of the newest green run ({baseline_path}) and the apt hash is unchanged")
    doc = {
        "decision": decision,
        "packages": list(a.packages),
        "head_tree": a.tree,
        "dirty_entries": a.dirty,
        "apt_hash": a.apt,
        "full": bool(a.full),
        "baseline_file": str(baseline_path) if baseline_path else None,
        "baseline_tree": baseline.get("tree") if baseline else None,
        "baseline_gate": baseline.get("gate") if baseline else None,
        "reasons": reasons,
        "decided_at_epoch": int(time.time()),
    }
    out = Path(a.out)
    if str(out) in ("/dev/stdout", "-"):
        print(json.dumps(doc, indent=2), file=sys.stderr)
    else:
        out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(decision)


def xunit_counts(build_root, package):
    results = Path(build_root) / package / "test_results" / package
    files = sorted(results.glob("*.xml")) if results.is_dir() else []
    return len(files)


def finish(a):
    decision = load(a.decision)
    if decision is None:
        raise SystemExit("decision file unreadable")
    gate = Path(a.gate)
    ran = decision["decision"] == "run"
    build_base = Path(a.build_base) if a.build_base else gate / "build"
    counts = {p: xunit_counts(build_base, p) for p in a.packages}
    green = ran and a.colcon_rc == 0 and all(counts[p] > 0 for p in a.packages)
    doc = {
        "gate": gate.name,
        "recorded_at_epoch": int(time.time()),
        "tree": decision["head_tree"],
        "apt_hash": decision["apt_hash"],
        "ran": ran,
        "green": bool(green),
        "colcon_rc": a.colcon_rc,
        "result_files": counts,
        "decision": decision["decision"],
        "reasons": decision["reasons"],
        "baseline_file": decision["baseline_file"],
        "baseline_tree": decision["baseline_tree"],
        "baseline_gate": decision["baseline_gate"],
        "note": "ran=false means the tests were skipped by the rule and this record is not a baseline candidate",
    }
    if a.tools_commit:
        doc["gate_tools_commit"] = a.tools_commit
    Path(a.out).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ran": ran, "green": bool(green)}))


TOOLS_PATH = "scripts/gate"


def git(repo, *args):
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed in {repo}: {done.stderr.strip()}")
    return done.stdout


def tools(a):
    """Write <out> with the gate tools commit and the diff stat of scripts/gate; exit 1 unless it is clean."""
    head = git(a.repo, "rev-parse", "HEAD").strip()
    commit = git(a.repo, "log", "-1", "--format=%H", "--", TOOLS_PATH).strip()
    tracked = git(a.repo, "ls-files", "--", TOOLS_PATH).split()
    stat = git(a.repo, "diff", "--stat", "HEAD", "--", TOOLS_PATH)
    untracked = git(a.repo, "status", "--porcelain", "--untracked-files=all", "--", TOOLS_PATH)
    clean = bool(tracked) and not stat.strip() and not untracked.strip()
    lines = [
        f"gate_tools_commit={commit}",
        f"gate_tools_head={head}",
        f"gate_tools_files={len(tracked)}",
        f"gate_tools_clean={int(clean)}",
        "gate_tools_diff_stat_begin",
        stat.rstrip("\n"),
        untracked.rstrip("\n"),
        "gate_tools_diff_stat_end",
    ]
    Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(commit)
    if not clean:
        raise SystemExit(1)


def seed(a):
    gate = Path(a.gate)
    runs = sorted(gate.glob("test-run.*/test-result.log"))
    if not runs:
        raise SystemExit("no test-result.log in the source gate")
    totals = {p: [0, 0, 0, 0, 0] for p in PACKAGES}  # files tests errors failures skipped
    for line in runs[-1].read_text(encoding="utf-8", errors="replace").splitlines():
        match = SUMMARY.search(line)
        if not match:
            continue
        for package in PACKAGES:
            if f"/build/{package}/" in match.group(1):
                t = totals[package]
                t[0] += 1
                t[1] += int(match.group(2))
                t[2] += int(match.group(3))
                t[3] += int(match.group(4))
                t[4] += int(match.group(5))
    for package, t in totals.items():
        if t[0] == 0 or t[2] or t[3]:
            raise SystemExit(f"source gate is not green for {package}: {t}")
    result = (gate / "gates-result.txt").read_text(encoding="utf-8").strip()
    if "colcon_rc=0" not in result:
        raise SystemExit(f"source gate colcon_rc is not 0: {result}")
    doc = {
        "gate": gate.name,
        "recorded_at_epoch": int((gate / "gates-result.txt").stat().st_mtime),
        "tree": a.tree,
        "apt_hash": a.apt,
        "ran": True,
        "green": True,
        "colcon_rc": 0,
        "source_gates_result": result,
        "per_package": {p: dict(zip(("xunit_files", "tests", "errors", "failures", "skipped"), t)) for p, t in totals.items()},
        "note": a.note,
    }
    Path(a.out).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(doc, indent=2))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("decide")
    d.add_argument("--gates", required=True)
    d.add_argument("--seed", required=True)
    d.add_argument("--tree", required=True)
    d.add_argument("--dirty", type=int, required=True)
    d.add_argument("--apt", required=True)
    d.add_argument("--full", type=int, required=True)
    d.add_argument("--out", required=True)
    f = sub.add_parser("finish")
    f.add_argument("--decision", required=True)
    f.add_argument("--gate", required=True)
    f.add_argument("--build-base", default=None, help="colcon build base (under the build root); default <gate>/build")
    f.add_argument("--colcon-rc", type=int, required=True)
    f.add_argument("--out", required=True)
    f.add_argument("--tools-commit", default=None, help="commit of scripts/gate that ran; stored in the record")
    t = sub.add_parser("tools")
    t.add_argument("--repo", required=True)
    t.add_argument("--out", required=True)
    s = sub.add_parser("seed")
    s.add_argument("--gate", required=True)
    s.add_argument("--tree", required=True)
    s.add_argument("--apt", required=True)
    s.add_argument("--note", required=True)
    s.add_argument("--out", required=True)
    for sp in (d, f):
        sp.add_argument("--packages", default=",".join(PACKAGES), type=lambda v: tuple(v.split(",")),
                        help="packages whose results the record covers (default: the ros2_control pair)")
    d.add_argument("--record-name", default="ros2-control-tests.json")
    d.add_argument("--label", default="third_party/ros2_control")
    args = parser.parse_args()
    {"decide": decide, "finish": finish, "seed": seed, "tools": tools}[args.cmd](args)


if __name__ == "__main__":
    main()
