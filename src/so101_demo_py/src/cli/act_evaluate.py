"""Task 16 CLI: summarise one route on one split, with a per-scene evidence index.

The report is written once and names the artifacts it was produced from, so a route comparison can be
reproduced. Runs are read from the route's own runs file — never by scanning the root — and each scene's
evidence paths must stay inside that root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from so101_demo.act.evaluation import summarize

SPLITS = ("rollout_validation", "rollout_test", "comparison")
ROUTES = ("act", "moveit")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_file(value, code: str) -> Path:
    path = Path(value) if value is not None else None
    if path is None or not path.is_file() or path.is_symlink():
        raise ValueError(code)
    return path


def _runs(path: Path) -> list:
    runs, index, seen = [], {}, set()
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError("RUN_RESULT_INVALID")
        scene_id = row.pop("scene_id", None)
        evidence = row.pop("evidence", None)
        runs.append(row)
        if scene_id is None and evidence is None:
            continue
        if not isinstance(scene_id, str) or not scene_id or scene_id in seen:
            raise ValueError("EVALUATION_SCENE_INDEX_INVALID")
        seen.add(scene_id)
        paths = [] if evidence is None else list(evidence)
        for entry in paths:
            if (not isinstance(entry, str) or not entry or entry.startswith("/")
                    or ".." in Path(entry).parts):
                raise ValueError("EVALUATION_EVIDENCE_PATH_INVALID")
        index[scene_id] = paths
    if not runs:
        raise ValueError("EVALUATION_EMPTY")
    return runs, index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="act_evaluate", description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--split", choices=SPLITS, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--runtime-config", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--route", choices=ROUTES, required=True)
    args = parser.parse_args(argv)

    root = args.root
    if not root.is_absolute() or not root.is_dir() or root.is_symlink() or ".." in root.parts:
        raise ValueError("EVALUATION_ROOT_INVALID")
    artifacts = {"manifest": _require_file(args.manifest, "EVALUATION_MANIFEST_MISSING"),
                 "bundle": _require_file(args.bundle, "EVALUATION_BUNDLE_MISSING"),
                 "calibration": _require_file(args.calibration, "EVALUATION_CALIBRATION_MISSING"),
                 "runtime_config": _require_file(args.runtime_config,
                                                 "EVALUATION_RUNTIME_CONFIG_MISSING")}
    runs_path = root / args.split / f"{args.route}-runs.jsonl"
    if not runs_path.is_file():
        raise ValueError("EVALUATION_RUNS_MISSING")
    runs, index = _runs(runs_path)
    report = summarize(runs)
    report.update({"split": args.split, "route": args.route,
                   "artifacts": {name: {"path": str(path), "sha256": _digest(path)}
                                 for name, path in artifacts.items()},
                   "evidence_index": index})

    outputs = {"json": root / args.split / f"{args.route}-report.json",
               "markdown": root / args.split / f"{args.route}-report.md"}
    for path in outputs.values():
        if path.exists() or path.is_symlink():
            raise ValueError("EVALUATION_REPORT_EXISTS")
    outputs["json"].write_text(json.dumps(report, sort_keys=True, indent=2) + chr(10))
    lines = [f"# {args.route} on {args.split}", "",
             f"- runs: {report['runs']}",
             f"- end-to-end: {report['end_to_end']:.3f}",
             f"- locked denominator: {report['locked_denominator']}",
             f"- locked success: {report['locked_success']}",
             f"- interventions: {report['interventions_total']} in "
             f"{report['interventions_runs']} run(s)",
             f"- wall budget violations: {report['budget_violations']} "
             f"(budget {report['wall_budget_s']:.0f} s)", "", "## Evidence", ""]
    lines += [f"- `{scene}`: {', '.join(paths) if paths else 'no evidence recorded'}"
              for scene, paths in sorted(index.items())]
    outputs["markdown"].write_text(chr(10).join(lines) + chr(10))
    print(json.dumps({"split": args.split, "route": args.route,
                      "report": str(outputs["json"]), "markdown": str(outputs["markdown"]),
                      "scenes": len(index)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
