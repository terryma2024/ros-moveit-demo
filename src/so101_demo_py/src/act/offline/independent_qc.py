"""Independent-process QC of an offline episode: `python -m so101_demo.act.offline.independent_qc ...`.

It imports nothing from the processor and holds no state of the replay. It runs the same read-only recomputation the QC command
runs (`episode_qc.recompute_native_qc`) against the original scope and frozen inputs, and writes the common QC report.
Exit codes: 0 PASS, 1 FAIL verdict, 2 the QC could not run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="independent_qc")
    parser.add_argument("--episode", type=Path, required=True)
    parser.add_argument("--scope", type=Path, required=True)
    parser.add_argument("--inputs-manifest", type=Path, required=True)
    parser.add_argument("--teacher-manifest", type=Path)
    parser.add_argument("--topic-loss", type=Path, help="the topic-loss gate document (default: beside the episode)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--diagnostic-ignore-scene-colors", action="store_true",
                        help="DIAGNOSTIC ONLY: compare scene geometry without object colours, as the diagnostic processor run did")
    arguments = parser.parse_args(argv)
    from ..episode_qc import recompute_native_qc, write_qc_report

    if arguments.diagnostic_ignore_scene_colors:
        from ...control.planning_scene import task_scene

        real = task_scene.normalized_scene_geometry

        def without_colors(scene):
            geometry = real(scene)
            geometry["colors"] = []
            return geometry

        task_scene.normalized_scene_geometry = without_colors

    try:
        report = recompute_native_qc(arguments.episode, scope=arguments.scope, inputs_manifest=arguments.inputs_manifest,
                                     teacher_manifest=arguments.teacher_manifest, topic_loss=arguments.topic_loss)
        digest = write_qc_report(report, arguments.output)
        if report["status"] == "PASS" and not arguments.diagnostic_ignore_scene_colors:
            # The run's result gates may rely on this exact recomputation instead of repeating it
            from .. import qc_memo

            qc_memo.write_memo(arguments.output, report, episode_root=arguments.episode, scope=arguments.scope,
                               inputs_manifest=arguments.inputs_manifest, teacher_manifest=arguments.teacher_manifest,
                               topic_loss=arguments.topic_loss)
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"status": "ERROR", "reason": f"{type(error).__name__}: {error}"[:500]}, sort_keys=True))
        return 2
    print(json.dumps({"status": report["status"], "reason": report.get("reason", ""), "output": str(arguments.output),
                      "sha256": digest, "counts": report.get("counts")}, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
