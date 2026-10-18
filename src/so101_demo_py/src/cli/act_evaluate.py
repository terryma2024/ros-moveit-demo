"""CLI: summarise one route on one split, with a per-scene evidence index.

The report is written once and names the artifacts it was produced from, so a route comparison can be
reproduced. Runs are read from the route's own runs file — never by scanning the root — and each scene's
evidence paths must stay inside that root.

The calibration gate is either a calibration report (`--calibration`) or, as the human ruled for the native
rollout (design 2026-10-18, D8), the contact-policy activation receipt (`--contact-activation-receipt` with its
`--contact-proposal`), which is verified the way collection admission verifies it and recorded in the report as
a substitution. A split whose runs name an `endpoint.json` (the native rollout's) also gets the endpoint errors of
the group and of each scene, so the standard points are reported one by one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from so101_demo.act.evaluation import summarize

SPLITS = ("rollout_standard", "rollout_validation", "rollout_test", "rollout_extrapolation", "comparison")
ENDPOINT_FILE = "endpoint.json"
EPISODE_FILE = "episode.json"
MEASURED_KEYS = ("final_xy_error_m", "final_z_error_m", "final_axis_tilt_rad")
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


def _stats(values: list) -> dict:
    ordered = sorted(values)
    count = len(ordered)
    if not count:
        return {"n": 0, "min": None, "median": None, "mean": None, "max": None}
    middle = count // 2
    median = ordered[middle] if count % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    return {"n": count, "min": ordered[0], "median": median, "mean": sum(ordered) / count, "max": ordered[-1]}


def _read_json(path: Path, *, missing: str):
    if not path.is_file() or path.is_symlink():
        raise ValueError(missing)
    try:
        return json.loads(path.read_bytes())
    except ValueError as error:
        raise ValueError("EVALUATION_ENDPOINT_EVIDENCE_INVALID") from error


def endpoint_report(split_root: Path, index: dict):
    """The endpoint errors of the group and of each scene, from the `endpoint.json` the runs name; None when none is named."""

    entries = {scene: [path for path in paths if Path(path).name == ENDPOINT_FILE] for scene, paths in index.items()}
    entries = {scene: paths for scene, paths in entries.items() if paths}
    if not entries:
        return None
    per_scene, values, results, verdicts = [], {key: [] for key in MEASURED_KEYS}, {}, {}
    for scene, paths in sorted(entries.items()):
        if len(paths) != 1:
            raise ValueError("EVALUATION_ENDPOINT_EVIDENCE_INVALID")
        file = split_root / paths[0]
        if not file.resolve().is_relative_to(split_root.resolve()):
            raise ValueError("EVALUATION_EVIDENCE_PATH_INVALID")
        document = _read_json(file, missing="EVALUATION_ENDPOINT_EVIDENCE_MISSING")
        endpoint = document.get("endpoint") if isinstance(document, dict) else None
        measured = endpoint.get("measured") if isinstance(endpoint, dict) else None
        if not isinstance(measured, dict) or not isinstance(endpoint.get("result"), str):
            raise ValueError("EVALUATION_ENDPOINT_EVIDENCE_INVALID")
        episode_file = file.with_name(EPISODE_FILE)
        episode = _read_json(episode_file, missing="EVALUATION_ENDPOINT_EVIDENCE_INVALID") if episode_file.exists() else {}
        scene_document = episode.get("scene") if isinstance(episode, dict) else None
        verdict = episode.get("verdict") if isinstance(episode, dict) else None
        row = {"scene_id": scene, "point_id": scene_document.get("point_id") if isinstance(scene_document, dict) else None,
               "verdict": verdict, "result": endpoint["result"]}
        for key in MEASURED_KEYS:
            value = measured.get(key)
            row[key] = value
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values[key].append(float(value))
        per_scene.append(row)
        results[endpoint["result"]] = results.get(endpoint["result"], 0) + 1
        verdicts[verdict or "UNKNOWN"] = verdicts.get(verdict or "UNKNOWN", 0) + 1
    return {"scenes": len(per_scene), "results": dict(sorted(results.items())), "verdicts": dict(sorted(verdicts.items())),
            **{key: _stats(values[key]) for key in MEASURED_KEYS}, "per_scene": per_scene}


def _calibration_artifact(args) -> tuple:
    """(calibration file to hash or None, substitution block or None): exactly one calibration source."""

    receipt, proposal, report = args.contact_activation_receipt, args.contact_proposal, args.calibration
    if (report is None) == (receipt is None) or (receipt is None) != (proposal is None):
        raise ValueError("EVALUATION_CALIBRATION_SOURCE_INVALID")
    if report is not None:
        return _require_file(report, "EVALUATION_CALIBRATION_MISSING"), None
    from so101_demo.act.rollout_activation import contact_activation_substitution

    return None, contact_activation_substitution(receipt, proposal)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="act_evaluate", description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--split", choices=SPLITS, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--contact-activation-receipt", type=Path,
                        help="the activation receipt that stands in for --calibration (needs --contact-proposal)")
    parser.add_argument("--contact-proposal", type=Path, help="the contact-policy proposal the receipt activates")
    parser.add_argument("--runtime-config", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--route", choices=ROUTES, required=True)
    args = parser.parse_args(argv)

    root = args.root
    if not root.is_absolute() or not root.is_dir() or root.is_symlink() or ".." in root.parts:
        raise ValueError("EVALUATION_ROOT_INVALID")
    calibration_file, substitution = _calibration_artifact(args)
    artifacts = {"manifest": _require_file(args.manifest, "EVALUATION_MANIFEST_MISSING"),
                 "bundle": _require_file(args.bundle, "EVALUATION_BUNDLE_MISSING"),
                 "runtime_config": _require_file(args.runtime_config, "EVALUATION_RUNTIME_CONFIG_MISSING")}
    if calibration_file is not None:
        artifacts["calibration"] = calibration_file
    runs_path = root / args.split / f"{args.route}-runs.jsonl"
    if not runs_path.is_file():
        raise ValueError("EVALUATION_RUNS_MISSING")
    runs, index = _runs(runs_path)
    report = summarize(runs)
    endpoint = endpoint_report(root / args.split, index)
    bound = {name: {"path": str(path), "sha256": _digest(path)} for name, path in artifacts.items()}
    if substitution is not None:
        bound["calibration"] = substitution
    report.update({"split": args.split, "route": args.route, "artifacts": dict(sorted(bound.items())),
                   "evidence_index": index, "endpoint": endpoint})

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
             f"(budget {report['wall_budget_s']:.0f} s)"]
    if substitution is not None:
        lines.append(f"- calibration gate: substituted by {substitution['substituted_by']} "
                     f"(policy fingerprint {substitution['policy_fingerprint'][:12]}, receipt sha256 "
                     f"{substitution['sha256'][:12]}); {substitution['ruling']}")
    if endpoint is not None:
        lines += ["", "## Endpoint errors", "",
                  f"- scenes: {endpoint['scenes']}; results: {endpoint['results']}; verdicts: {endpoint['verdicts']}"]
        for key in MEASURED_KEYS:
            stat = endpoint[key]
            lines.append(f"- {key}: n {stat['n']}, min {stat['min']}, median {stat['median']}, mean {stat['mean']}, "
                         f"max {stat['max']}")
        lines += ["", "| scene | point | verdict | result | final xy (m) | final z (m) | tilt (rad) |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        lines += [f"| `{row['scene_id']}` | {row['point_id']} | {row['verdict']} | {row['result']} | "
                  f"{row['final_xy_error_m']} | {row['final_z_error_m']} | {row['final_axis_tilt_rad']} |"
                  for row in endpoint["per_scene"]]
    lines += ["", "## Evidence", ""]
    lines += [f"- `{scene}`: {', '.join(paths) if paths else 'no evidence recorded'}"
              for scene, paths in sorted(index.items())]
    outputs["markdown"].write_text(chr(10).join(lines) + chr(10))
    print(json.dumps({"split": args.split, "route": args.route,
                      "report": str(outputs["json"]), "markdown": str(outputs["markdown"]),
                      "scenes": len(index)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
