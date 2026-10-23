"""CLI (evidence side): fold the Teacher verdicts of a finished boundary round into the brackets.

Reads the sidecar state of ``act_boundary_round`` and the finished debug campaign's run root.  For every probe, the
scene's phase-1 sealed ``dynamic/dynamic-execute-manifest.json`` decides: Teacher PASS means
``teacher_execution_status == COMPLETED``, ``teacher_task_result.result == PASS``, ``current_state == DONE`` and
``failure is None`` (as in the earlier analyses).  The phase-2 data verdict is recorded next to it and does not count.
A scene without a manifest stops the command and writes nothing: a lost scene is not a Teacher failure.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from so101_demo.act import boundary_search
from so101_demo.act.scene_boundary import teacher_passed
from so101_demo.act.scene_list_format import write_new_json

MANIFEST_PATH = "dynamic/dynamic-execute-manifest.json"


def read_verdicts(run_root: Path, scene_ids: list[str]) -> dict[str, dict]:
    result_path = run_root / "host" / "campaign-result.json"
    try:
        campaign = json.loads(result_path.read_text())
    except (OSError, ValueError) as error:
        raise ValueError(f"BOUNDARY_CAMPAIGN_RESULT_UNAVAILABLE: {result_path}") from error
    if campaign.get("schema_version") != 2 or not isinstance(campaign.get("scenes"), list):
        raise ValueError("BOUNDARY_CAMPAIGN_RESULT_INVALID")
    scenes = {scene.get("scene_id") or scene.get("phase1", {}).get("scene_id"): scene for scene in campaign["scenes"]}
    verdicts = {}
    for scene_id in scene_ids:
        scene = scenes.get(scene_id)
        location = ((scene or {}).get("phase1") or {}).get("location")
        try:
            manifest = json.loads((Path(location) / MANIFEST_PATH).read_text())
        except (TypeError, OSError, ValueError) as error:
            raise ValueError(f"BOUNDARY_VERDICT_MISSING: {scene_id}") from error
        task = manifest.get("teacher_task_result")
        phase2 = scene.get("phase2") or {}
        verdicts[scene_id] = {
            "teacher_pass": teacher_passed(manifest),
            "teacher_execution_status": manifest.get("teacher_execution_status"),
            "endpoint_result": task.get("result") if isinstance(task, dict) else None,
            "current_state": manifest.get("current_state"),
            "failure": manifest.get("failure"),
            "act_data_status": phase2.get("act_data_status"),
            "act_data_qc": phase2.get("act_data_qc"),
        }
    return verdicts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="act_boundary_update", description=__doc__)
    parser.add_argument("--state", type=Path, required=True, help="the round's sidecar state")
    parser.add_argument("--run-root", type=Path, required=True, help="the finished debug campaign's run root")
    parser.add_argument("--output", type=Path, required=True, help="the updated state (written once)")
    args = parser.parse_args(argv)

    if args.output.exists() or args.output.is_symlink():
        raise ValueError(f"OUTPUT_EXISTS: {args.output}")
    pending = json.loads(args.state.read_text())
    probes = pending.get("probes", {})
    verdicts = read_verdicts(args.run_root, [probe["scene_id"] for probe in probes.values()])
    updated = boundary_search.apply_verdicts(pending, verdicts)
    write_new_json(args.output, updated)
    print(json.dumps({
        "round": updated["round"],
        "teacher_pass": {name: verdicts[probe["scene_id"]]["teacher_pass"] for name, probe in probes.items()},
        "phase": {name: bracket["phase"] for name, bracket in updated["brackets"].items()},
        "finished": boundary_search.is_finished(updated),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
