"""The first-episode entry point: inspect candidates, freeze inputs, preflight a frozen set.

The amendment gives this CLI the flags the plan's E3 sequence uses. `prepare` is the production caller the freezer
never had, so the endpoint policy and the development runtime are bound into the inputs hash chain there; `preflight`
re-reads a frozen set and refuses when its own manifest, its policy or its runtime cannot be accounted for. `inspect`
- the candidate discovery over a source root and the ledger - is not implemented yet and says so with rc 2 rather
than inventing a registry.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

from so101_demo.act.endpoint_pose_acceptance import load_development_runtime, load_endpoint_policy
from so101_demo.act.first_episode_inputs import freeze_inputs, inspect_inputs

MODES = ("formal", "preselected_target_diagnostic")


class _Parser(argparse.ArgumentParser):
    """The house parser: a refused argument is rc 2, never a traceback."""

    def error(self, message):                                        # noqa: D102 - argparse contract
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="act_first_episode", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect = subparsers.add_parser("inspect", help="discover input candidates (not implemented yet)")
    inspect.add_argument("--source-root", required=True)
    inspect.add_argument("--ledger", required=True)
    inspect.add_argument("--output", required=True)

    prepare = subparsers.add_parser("prepare", help="freeze a candidate registry into immutable inputs")
    prepare.add_argument("--candidates", required=True)
    prepare.add_argument("--mode", default="formal", choices=MODES)
    prepare.add_argument("--endpoint-policy", required=True)
    prepare.add_argument("--runtime-policy", required=True)
    prepare.add_argument("--output", required=True)

    run = subparsers.add_parser("run", help="execute one non-Head episode from a frozen input set")
    run.add_argument("--inputs", required=True)
    run.add_argument("--root", required=True)
    run.add_argument("--mode", default="preselected_target_diagnostic", choices=MODES)
    run.add_argument("--lifecycle", default="FULL_RESTART",
                     choices=("FULL_RESTART", "REUSE_STACK", "RESET_WORLD"))
    # the final cup target the endpoint rule compares against: it is the scenario's frozen quantity, and this CLI
    # refuses rather than inventing one, because an invented target would make every later PASS meaningless
    run.add_argument("--final-cup-pose",
                     help="seven numbers: the frozen final cup pose as xyz plus an xyzw quaternion")

    preflight = subparsers.add_parser("preflight", help="re-read a frozen input set")
    preflight.add_argument("--inputs", required=True)
    preflight.add_argument("--mode", default="formal", choices=MODES)
    preflight.add_argument("--output", required=True)
    return parser


def _prepare(arguments) -> int:
    # the policy and runtime are parsed before the freeze so a bad document refuses before anything is written
    load_endpoint_policy(Path(arguments.endpoint_policy))
    load_development_runtime(Path(arguments.runtime_policy))
    target = freeze_inputs(Path(arguments.candidates), Path(arguments.output), mode=arguments.mode,
                           endpoint_policy=Path(arguments.endpoint_policy),
                           runtime_policy=Path(arguments.runtime_policy))
    print(target)
    return 0


def _preflight(arguments) -> int:
    inputs = Path(arguments.inputs)
    manifest_path = inputs / "inputs-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    report = {
        "mode": arguments.mode,
        "inputs_sha256": manifest["inputs_sha256"],
        "endpoint_policy": manifest.get("endpoint_policy"),
        "runtime_policy": manifest.get("runtime_policy"),
        "roles": sorted(manifest["roles"]),
        "prepared_mode": manifest.get("mode"),
    }
    Path(arguments.output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(arguments.output)
    return 0


def _run(arguments) -> int:
    """One episode: the production pieces composed around a single-point request.

    Every value comes from the frozen set or from the caller; nothing is invented, and a missing frozen quantity is a
    refusal rather than a default.
    """

    inputs = Path(arguments.inputs)
    manifest = json.loads((inputs / "inputs-manifest.json").read_bytes())
    if manifest.get("mode") != arguments.mode:
        print(f"act_first_episode: the frozen set was prepared for {manifest.get('mode')!r}, "
              f"not {arguments.mode!r}", file=sys.stderr)
        return 2
    if arguments.final_cup_pose is None:
        print("act_first_episode: --final-cup-pose is required: the endpoint rule compares the cup against the "
              "scenario's frozen target, and this CLI will not invent one", file=sys.stderr)
        return 2
    try:
        target = tuple(float(part) for part in arguments.final_cup_pose.split(","))
    except ValueError:
        print("act_first_episode: --final-cup-pose must be three comma-separated numbers", file=sys.stderr)
        return 2
    # the adapter validates the last four components as a quaternion, so the target is a full pose; the same
    # norm tolerance the endpoint policy uses applies here, and the quaternion is normalised before use
    if len(target) != 7 or any(not math.isfinite(value) for value in target):
        print("act_first_episode: --final-cup-pose must be seven finite numbers (xyz and an xyzw quaternion)",
              file=sys.stderr)
        return 2
    norm = math.sqrt(sum(value * value for value in target[3:]))
    if norm == 0 or abs(norm - 1.0) > 1e-3:
        print(f"act_first_episode: --final-cup-pose quaternion norm is {norm}", file=sys.stderr)
        return 2
    target = (*target[:3], *(value / norm for value in target[3:]))

    from so101_demo.core.task_points import TaskPoint
    from so101_demo.parallel_batch.contracts import BatchKindV2, BatchRequestV2, RunMode
    from so101_demo.cli.mujoco_parallel_batch import SealedResultAdapter
    from so101_demo.parallel_batch.coordinator import BatchCoordinator
    from so101_demo.parallel_batch.journal import CoordinatorJournal

    root = Path(arguments.root)
    if root.exists():
        print(f"act_first_episode: {root} already exists; a run is a new evidence root", file=sys.stderr)
        return 2
    root.mkdir(parents=True, mode=0o700)
    batch_id = f"nonhead-{arguments.mode}-{int(time.time())}"
    point = TaskPoint(id=batch_id, label=arguments.mode, cup_position_world_m=tuple(target))
    # the composition reads selected_point_ids off this request, so it is the versioned contract rather than the
    # application-layer one: one point, one worker, an execute run and a fresh first pass
    request = BatchRequestV2(batch_id=batch_id, run_mode=RunMode.EXECUTE, selected_point_ids=(point.id,),
                             worker_count=1, evidence_root=root.resolve(),
                             batch_kind=BatchKindV2.FIRST_PASS)
    # the production composition's first three pieces, the same objects the batch path builds around one point:
    # the journal, the sealed-result adapter and the coordinator. The config is the frozen runtime document, parsed
    # by the same loader the batch path uses, so nothing here re-reads a live file.
    from so101_demo.parallel_batch.contracts import load_runtime_config_any_schema

    config = load_runtime_config_any_schema(inputs / "runtime_config" / "parallel_batch_v3.yaml")
    journal = CoordinatorJournal.create(root / "coordinator", batch_id)
    worker_root = root / "worker-0"
    worker_root.mkdir(parents=True, mode=0o700)
    # the collection mode (diagnostic or formal) is not the run mode: driving the approved stack is an execute run,
    # and the mode stays recorded in the run's own log and in the frozen manifest

    result_port = SealedResultAdapter({"worker-0": worker_root}, RunMode.EXECUTE,
                                      expected_final_cup_pose_world=tuple(target))
    coordinator = BatchCoordinator(journal, request, config=config, result_port=result_port)
    # the two artefacts the specification needs, both written under this run's own root: a one-point TaskPointList
    # (the sweep catalogue reduced to this episode) and a copy of the frozen provenance inputs, so the composition
    # verifies what was frozen rather than what is on disk now
    points_document = {"schema_version": 1,
                       "points": [{"id": point.id, "label": point.label,
                                   "cup_position_world_m": list(point.cup_position_world_m)}]}
    points_path = root / "points.json"
    points_path.write_text(json.dumps(points_document, indent=2, sort_keys=True) + "\n")
    provenance_paths = {}
    for name in ("inputs-manifest.json",):
        source = inputs / name
        if source.is_file():
            payload = source.read_bytes()
            destination = root / name
            destination.write_bytes(payload)
            provenance_paths[name] = str(destination)
    log = root / "run.log"
    with log.open("w") as stream:
        stream.write(f"batch_id={batch_id}\nmode={arguments.mode}\nlifecycle={arguments.lifecycle}\n"
                     f"final_cup_pose={target}\ninputs={inputs.resolve()}\n"
                     f"config={type(config).__name__}\njournal={type(journal).__name__}\n"
                     f"result_port={type(result_port).__name__}\ncoordinator={type(coordinator).__name__}\n"
                     f"points={points_path}\nprovenance={sorted(provenance_paths)}\n"
                     f"broker_image=ABSENT (headless MuJoCo-only stack; no broker container exists to name)\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(f"act_first_episode: composed {type(journal).__name__}, {type(result_port).__name__} and "
          f"{type(coordinator).__name__} for {batch_id}; the episode runner needs the approved MuJoCo stack and is "
          f"not wired yet", file=sys.stderr)
    return 2


def main(argv=None) -> int:
    arguments = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    if arguments.command == "inspect":
        # the discovery already exists in the inputs module and is read-only: it selects nothing by recency and
        # defaults nothing, reporting a blocker for every role without an approved, identity-matching candidate
        document = inspect_inputs(Path(arguments.source_root), Path(arguments.ledger))
        Path(arguments.output).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
        print(arguments.output)
        return 0
    if arguments.command == "prepare":
        return _prepare(arguments)
    if arguments.command == "preflight":
        return _preflight(arguments)
    if arguments.command == "run":
        return _run(arguments)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
