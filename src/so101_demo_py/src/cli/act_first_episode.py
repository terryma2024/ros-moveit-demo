"""Inspect approved candidates, freeze and preflight inputs, collect one non-Head episode,
and independently read its original native QC, Coordinator commit and diagnostic export refusal.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

from so101_demo.act.endpoint_pose_acceptance import load_development_runtime
from so101_demo.act.first_episode_inputs import (
    freeze_inputs, inspect_inputs, read_inputs_manifest, verify_frozen_inputs,
)

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

    inspect = subparsers.add_parser("inspect", help="discover approved input candidates without selecting by recency")
    inspect.add_argument("--source-root", required=True)
    inspect.add_argument("--ledger", required=True)
    inspect.add_argument("--output", required=True)

    prepare = subparsers.add_parser("prepare", help="freeze a candidate registry into immutable inputs")
    prepare.add_argument("--candidates", required=True)
    prepare.add_argument("--mode", default="formal", choices=MODES)
    prepare.add_argument("--teacher-endpoint", required=True,
                         help="teacher_endpoint_v2 policy file, frozen with its sha256 and full effective values")
    prepare.add_argument("--teacher-execution-policy", required=True,
                         help="teacher_execution_policy_v1 file, frozen with its sha256 and full effective values")
    prepare.add_argument("--episode-recorder-policy", required=True,
                         help="episode_recorder_v1 file, frozen with its sha256 and full effective values")
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
    run.add_argument("--collection", default="on", choices=("on", "off"),
                     help="on: a record-only `ros2 bag record` process records the run (raw/bag) and the offline processor builds "
                          "the episode from it after the Teacher ended; off: no recorder, no processing, no QC")
    run.add_argument("--raw-pilot", default=None, choices=("on", "off"),
                     help="retired (CP-3456): the bag recorder is the only data path. `on` is accepted and does nothing; `off` "
                          "with --collection on is refused")
    run.add_argument("--collection-fault", default="none",
                     choices=("none", "recorder_absent", "recorder_late", "queue_overflow", "source_gap",
                              "output_write_failure"),
                     help="sandbox fault injection (preselected_target_diagnostic mode only, outputs under "
                          "<run>/fault-sandbox/)")
    run.add_argument("--final-cup-pose",
                     help="seven numbers: the frozen final cup pose as xyz plus an xyzw quaternion")

    preflight = subparsers.add_parser("preflight", help="re-read a frozen input set")
    preflight.add_argument("--inputs", required=True)
    preflight.add_argument("--mode", default="formal", choices=MODES)
    preflight.add_argument("--output", required=True)
    qc = subparsers.add_parser('qc', help='independently recompute sealed native episode QC without live ports')
    qc_source=qc.add_mutually_exclusive_group(required=True)
    qc_source.add_argument('--run')
    qc_source.add_argument('--episode')
    qc.add_argument('--scope')
    qc.add_argument('--inputs')
    qc.add_argument('--output', required=True)
    commit=subparsers.add_parser('verify-commit',help='re-read the actual Coordinator journal, index and QC-bound receipt')
    commit.add_argument('--run',required=True)
    commit.add_argument('--output',required=True)
    export=subparsers.add_parser('check-export',help='verify both common export boundaries refuse the committed diagnostic')
    export.add_argument('--run',required=True)
    export.add_argument('--output',required=True)
    return parser


def _prepare(arguments) -> int:
    # the policies and runtime are parsed before the freeze so a bad document refuses before anything is written
    load_development_runtime(Path(arguments.runtime_policy))
    target = freeze_inputs(Path(arguments.candidates), Path(arguments.output), mode=arguments.mode,
                           teacher_endpoint=Path(arguments.teacher_endpoint),
                           teacher_execution_policy=Path(arguments.teacher_execution_policy),
                           episode_recorder_policy=Path(arguments.episode_recorder_policy),
                           runtime_policy=Path(arguments.runtime_policy), execution_inputs=True)
    print(target)
    return 0


def _preflight(arguments) -> int:
    inputs = Path(arguments.inputs)
    manifest_path = inputs / "inputs-manifest.json"
    try:
        manifest = verify_frozen_inputs(manifest_path)
        if manifest.get("mode") != arguments.mode:
            raise ValueError("INPUT_MODE_MISMATCH")
    except (OSError, ValueError) as error:
        print(f"act_first_episode: {error}", file=sys.stderr)
        return 2
    report = {
        "mode": arguments.mode,
        "inputs_sha256": manifest["inputs_sha256"],
        "teacher_endpoint_v2": manifest.get("teacher_endpoint_v2"),
        "teacher_execution_policy_v1": manifest.get("teacher_execution_policy_v1"),
        "episode_recorder_v1": manifest.get("episode_recorder_v1"),
        "runtime_policy": manifest.get("runtime_policy"),
        "roles": sorted(manifest["roles"]),
        "prepared_mode": manifest.get("mode"),
    }
    Path(arguments.output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(arguments.output)
    return 0


def _qc(arguments) -> int:
    from ..act.episode_qc import recompute_native_qc, write_qc_report
    try:
        if arguments.run is not None:
            from ..act.result_store import resolve_native_run
            if arguments.scope is not None or arguments.inputs is not None:
                raise ValueError('QC_RUN_ORIGINAL_BINDINGS_REQUIRED')
            context=resolve_native_run(Path(arguments.run))
            root,scope,inputs_manifest=context['episode'],context['scope'],context['inputs_manifest']
        else:
            if arguments.scope is None or arguments.inputs is None:
                raise ValueError('QC_ORIGINAL_BINDINGS_REQUIRED')
            root,scope,inputs_manifest=Path(arguments.episode),Path(arguments.scope),Path(arguments.inputs)/'inputs-manifest.json'
        report = recompute_native_qc(root, scope=scope, inputs_manifest=inputs_manifest)
        digest = write_qc_report(report, Path(arguments.output))
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f'act_first_episode: {error}', file=sys.stderr)
        return 4 if arguments.run is not None else 2
    print(json.dumps(dict(status=report['status'], output=arguments.output, sha256=digest), sort_keys=True))
    return 0 if report['status'] == 'PASS' else (3 if arguments.run is not None else 1)


def _verify_commit(arguments) -> int:
    from ..act.result_store import resolve_native_run,verify_coordinator_commit,write_commit_proof
    try:
        context=resolve_native_run(Path(arguments.run))
        proof=verify_coordinator_commit(context['coordinator_root'],location=context['location'],
            scope=context['scope'],inputs_manifest=context['inputs_manifest'])
        digest=write_commit_proof(proof,Path(arguments.output))
    except (OSError,ValueError,TypeError,KeyError) as error:
        print(f'act_first_episode: {error}',file=sys.stderr)
        return 3
    print(json.dumps(dict(status=proof['status'],output=arguments.output,sha256=digest),sort_keys=True))
    return 0


def _check_export(arguments) -> int:
    from ..act.result_store import resolve_native_run,verify_coordinator_commit,write_export_rejection_proof
    from ..act.collection_scope import read_collection_scope
    from ..act.bundle import resolve_committed_episodes,export_dataset
    try:
        context=resolve_native_run(Path(arguments.run))
        scope=read_collection_scope(context['scope'])
        if scope['mode']!='preselected_target_diagnostic':
            raise ValueError('DIAGNOSTIC_EXPORT_CHECK_MODE_REQUIRED')
        commit=verify_coordinator_commit(context['coordinator_root'],location=context['location'],
            scope=context['scope'],inputs_manifest=context['inputs_manifest'])
        index=context['coordinator_root']/'aggregate_results.json'
        entry=dict(kind='ACT_COMMITTED_EPISODE',schema_version=2,scene_id=scope['scene_id'],split='train',
            status=commit['result_status'],journal_sha256=commit['commit_frame_sha256'],verifier_sha256=commit['result_sha256'],
            collection_evidence=dict(coordinator_root=str(context['coordinator_root']),result_location=str(context['location']),
                scope_path=str(context['scope']),inputs_manifest=str(context['inputs_manifest']),receipt=commit['receipt']))
        dataset=Path(arguments.output).with_name(Path(arguments.output).name+'.dataset')
        checks={}
        calls={'resolver':lambda:resolve_committed_episodes(manifest=dict(episodes=[entry]),campaign_index=index),
            'direct_export':lambda:export_dataset((entry,),dataset,source_manifest_sha256=scope['inputs_sha256'],
                campaign_index_sha256=hashlib.sha256(index.read_bytes()).hexdigest())}
        for name,call in calls.items():
            try:call()
            except ValueError as error:
                if str(error)!='DIAGNOSTIC_EPISODE_NOT_TRAINABLE':raise
                checks[name]=str(error)
            else:raise ValueError('DIAGNOSTIC_EXPORT_UNEXPECTEDLY_ELIGIBLE')
        if dataset.exists() or dataset.is_symlink():raise ValueError('DIAGNOSTIC_EXPORT_DATASET_PRODUCED')
        proof=dict(kind='ACT_DIAGNOSTIC_EXPORT_REJECTION',schema_version=1,status='PASS',checks=checks,
            identity=commit['identity'],result_status=commit['result_status'],collection_mode=scope['mode'],
            qc_report_sha256=commit['qc_report_sha256'],scope_sha256=commit['scope_sha256'],
            commit_frame_sha256=commit['commit_frame_sha256'],result_sha256=commit['result_sha256'],
            dataset_produced=False,perception_or_policy_models_loaded=False)
        digest=write_export_rejection_proof(proof,Path(arguments.output))
    except (OSError,ValueError,TypeError,KeyError) as error:
        print(f'act_first_episode: {error}',file=sys.stderr)
        return 3
    print(json.dumps(dict(status=proof['status'],output=arguments.output,sha256=digest),sort_keys=True))
    return 0


def _verified_run_completion(run_root):
    """Return success only after original native QC, commit and cleanup readback."""
    from ..act.result_store import (resolve_native_run, verify_coordinator_commit,
                                   verify_coordinator_cleanup, write_commit_proof)
    try:
        context = resolve_native_run(Path(run_root))
        proof = verify_coordinator_commit(context['coordinator_root'],
            location=context['location'], scope=context['scope'],
            inputs_manifest=context['inputs_manifest'])
        cleanup = verify_coordinator_cleanup(context['coordinator_root'], commit_proof=proof)
        # The Teacher result and the data QC are reported separately: a Teacher success with failing data still
        # exits non-zero, and the report keeps the Teacher status so that is never read as a task failure.
        report = dict(teacher_result_status=proof['result_status'],
            teacher_task_result=proof.get('teacher_task_result'), act_data_qc=proof.get('act_data_qc'),
            export_eligible=proof['export_eligible'], result_location=str(context['location']))
        if proof['result_status'] != 'PASSED':
            # exit 1: the Teacher itself did not pass; the data verdict stays in the report beside it
            return 1, dict(status='FAIL', reason='TEACHER_TASK_NOT_PASSED', **report)
        # A passed Teacher attempt keeps its verified commit proof even when its data failed QC.
        receipt_path = Path(run_root) / 'commit-proof.json'
        digest = write_commit_proof(proof, receipt_path)
        report.update(receipt_path=str(receipt_path), receipt_sha256=digest,
                      cleanup_proof_path=cleanup['cleanup_proof_path'])
        if proof.get('act_data_status') == 'DISABLED':
            # collection off: the Teacher passed and no data was asked for, so there is nothing to grade
            return 0, dict(status='PASS', **report)
        if proof.get('act_data_qc') != 'PASS':
            # exit 3: the Teacher passed but the data is INVALID or its independent QC did not pass. The gate reads the
            # QC verdict itself: export eligibility also needs a trainable mode, which a diagnostic run never has
            return 3, dict(status='FAIL', reason='ACT_DATA_QC_NOT_PASSED', **report)
        return 0, dict(status='PASS', **report)
    except (OSError, ValueError, TypeError, KeyError) as error:
        return 4, dict(status='FAIL', reason=str(error))


def _nonhead_provenance(inputs: dict) -> dict:
    """Read the actual approved image/model identities for the existing deployment."""
    manifest_path = Path(inputs["inputs_manifest"])
    raw_manifest = manifest_path.read_bytes()
    document = json.loads(raw_manifest)
    if document["inputs_sha256"] != inputs["expected_inputs_sha256"]:
        raise ValueError("NONHEAD_PROVENANCE_INPUTS_IDENTITY_MISMATCH")
    if hashlib.sha256(raw_manifest).hexdigest() != inputs["inputs_manifest_sha256"]:
        raise ValueError("NONHEAD_PROVENANCE_MANIFEST_MISMATCH")
    scene = Path(inputs["scene_model"])
    scene_sha = hashlib.sha256(scene.read_bytes()).hexdigest()
    if scene_sha != document["roles"]["scene_model"]["sha256"]:
        raise ValueError("NONHEAD_PROVENANCE_SCENE_MISMATCH")
    yolo, grounded = Path(inputs["yolo_weights"]), Path(inputs["grounded_root"])
    if (not yolo.is_absolute() or not yolo.is_file() or yolo.is_symlink()
            or not grounded.is_absolute() or not grounded.is_dir() or grounded.is_symlink()
            or not (grounded / "manifest.json").is_file()
            or (grounded / "manifest.json").is_symlink()):
        raise ValueError("NONHEAD_PROVENANCE_MODEL_PATH")
    yolo_sha = hashlib.sha256(yolo.read_bytes()).hexdigest()
    grounded_sha = hashlib.sha256((grounded / "manifest.json").read_bytes()).hexdigest()
    if (yolo_sha != inputs["yolo_weights_sha256"]
            or grounded_sha != inputs["grounded_manifest_sha256"]):
        raise ValueError("NONHEAD_PROVENANCE_MODEL_MISMATCH")
    if inputs["broker_image"] != BROKER_IMAGE:
        raise ValueError("NONHEAD_PROVENANCE_IMAGE_MISMATCH")
    from .parallel_perception_broker import image_record
    image = image_record(BROKER_IMAGE)
    if image.get("image_id") != BROKER_IMAGE_ID:
        raise ValueError("NONHEAD_PROVENANCE_IMAGE_MISMATCH")
    return {
        "kind": "ACT_NONHEAD_DEPLOYMENT_PROVENANCE", "schema_version": 1,
        "inputs_manifest": str(manifest_path),
        "inputs_manifest_sha256": inputs["inputs_manifest_sha256"],
        "inputs_sha256": document["inputs_sha256"],
        "scene_model": str(scene), "scene_model_sha256": scene_sha,
        "broker_image": BROKER_IMAGE, **image,
        "yolo_weights": str(yolo), "yolo_weights_sha256": yolo_sha,
        "grounded_root": str(grounded), "grounded_manifest_sha256": grounded_sha,
    }

#: the broker image the coordinator approved for this milestone (CP-2760): the perception stack and torch
#: live inside it, which is what the host lacks - and reusing it is the decision that supersedes the
#: container-free route this path was written under (CP-2854)
BROKER_IMAGE = "so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1"
BROKER_IMAGE_ID = "sha256:010dca70ce3ce995367793642c2e5515718986253cecacc032e9f7f7ec6c5457"
YOLO_WEIGHTS = Path("/data/work/models/so101-perception/yolo11n-seg-plastic-cup/best.pt")
GROUNDED_ROOT = Path("/data/work/models/so101-perception/grounded-sam-cup-pickplace/bundle")


def _broker_command(composition):
    """The deployment's container-free broker command.

    The broker parses the flags `broker_argv()` freezes, but the default route runs them **inside the image**, where
    `/runtime`, `/inputs` and `/models` are mounted. On the host those have to name this run's own paths, so the frozen
    flags are taken as-is and the flag values that describe locations are substituted with the composition's - the
    perception endpoint on its IPC root, the broker's input root, its ready receipt and the spec document it prepared.
    Everything the broker *verifies* (the frozen detector identity and its digest) is left untouched.
    """

    from so101_demo.cli.parallel_perception_broker import broker_argv

    flags = [str(item) for item in broker_argv()]
    # three of the composition's locations are always populated and the fourth falls back to the same authority IPC
    # root the composition itself builds its broker runtime root from (CP-2533)
    ipc_root = composition.runtime_ipc_root or composition.authority.ipc_root
    substitutions = {
        "--endpoint": str(ipc_root / "perception.sock"),
        "--input-root": str(composition.broker_input_root),
        "--ready-receipt": str(composition.broker_runtime_root / "ready.json"),
        "--runtime-spec": str(composition.broker_spec_path),
        # the transport checks a declared digest against the file this flag names, so it too must point at the
        # file whose digest the specification declares (CP-2542)
        "--yolo-weights": str(composition.spec.yolo_weights),
    }
    for index, flag in enumerate(flags):
        if flag in substitutions and index + 1 < len(flags):
            flags[index + 1] = substitutions[flag]
    return [sys.executable, "-m", "so101_demo.cli.parallel_perception_broker", *flags]


def _run(arguments) -> int:
    """One episode: the production pieces composed around a single-point request.

    Every value comes from the frozen set or from the caller; nothing is invented, and a missing frozen quantity is a
    refusal rather than a default.
    """

    inputs = Path(arguments.inputs)
    try:
        manifest_bytes = (inputs / "inputs-manifest.json").read_bytes()
        manifest = verify_frozen_inputs(inputs / "inputs-manifest.json")
        if json.loads(manifest_bytes) != manifest:
            raise ValueError("EPISODE_INPUTS_IDENTITY_CHANGED")
    except (OSError, ValueError) as error:
        print(f"act_first_episode: {error}", file=sys.stderr)
        return 2
    if manifest.get("mode") != arguments.mode:
        print(f"act_first_episode: the frozen set was prepared for {manifest.get('mode')!r}, "
              f"not {arguments.mode!r}", file=sys.stderr)
        return 2
    try:
        from ..act.execution_snapshot import verify_execution_snapshot
        binding = manifest.get("execution_snapshot")
        if binding is None:
            raise ValueError("EPISODE_EXECUTION_INPUTS_REQUIRED")
        snapshot = verify_execution_snapshot(inputs / binding["path"], expected_sha256=binding["sha256"])
        endpoint_targets = snapshot["targets"]
        target = tuple(endpoint_targets["final_target"])
        if arguments.final_cup_pose is not None:
            supplied = tuple(float(part) for part in arguments.final_cup_pose.split(","))
            if len(supplied) != 7 or any(not math.isfinite(value) for value in supplied):
                raise ValueError("EPISODE_FINAL_TARGET_INVALID")
            norm = math.sqrt(sum(value * value for value in supplied[3:]))
            if norm == 0 or abs(norm - 1) > 1e-3:
                raise ValueError("EPISODE_FINAL_TARGET_INVALID")
            if (any(abs(a - b) > 1e-12 for a, b in zip(supplied[:3], target[:3]))
                    or abs(sum(a / norm * b for a, b in zip(supplied[3:], target[3:]))) < 1 - 1e-12):
                raise ValueError("EPISODE_FINAL_TARGET_FROZEN_MISMATCH")
    except (OSError, ValueError) as error:
        print(f"act_first_episode: {error}", file=sys.stderr)
        return 2

    # The collection request is refused here, before any Teacher start (and before the run root exists): an unknown
    # value, or a fault outside the diagnostic mode. Every fault output is additionally checked by the worker.
    from ..act.collection_orchestration import CollectionRefused, validate_collection_request
    try:
        collection = validate_collection_request(arguments.collection, arguments.collection_fault,
                                                 run_mode=arguments.mode, run_root=Path(arguments.root).resolve(),
                                                 raw_pilot=None if getattr(arguments, "raw_pilot", None) is None else arguments.raw_pilot == "on")
        from ..act.frozen_runtime_inputs import load_recorder_frozen_policy, load_teacher_frozen_inputs
        load_teacher_frozen_inputs(inputs / "inputs-manifest.json")
        if collection.enabled:
            load_recorder_frozen_policy(inputs / "inputs-manifest.json")
    except (CollectionRefused, OSError, ValueError) as error:
        print(f"act_first_episode: {error}", file=sys.stderr)
        return 2
    from so101_demo.core.task_points import TaskPoint
    from so101_demo.parallel_batch.contracts import BatchKindV2, BatchRequestV2, RunMode

    root = Path(arguments.root)
    if root.exists():
        print(f"act_first_episode: {root} already exists; a run is a new evidence root", file=sys.stderr)
        return 2
    root.mkdir(parents=True, mode=0o700)
    batch_id = f"nonhead-{arguments.mode}-{int(time.time())}"
    # the point must be one the approved catalogue actually names: task_start is the episode's start, and the
    # request selects exactly that one id, so the sweep vehicle runs a single episode (CP-2519)
    point = TaskPoint(id="task_start", label=arguments.mode,
                      cup_position_world_m=tuple(endpoint_targets["initial_target"][:3]))
    # the composition reads selected_point_ids off this request, so it is the versioned contract rather than the
    # application-layer one: one point, one worker, an execute run and a fresh first pass
    request = BatchRequestV2(batch_id=batch_id, run_mode=RunMode.EXECUTE, selected_point_ids=(point.id,),
                             worker_count=1, evidence_root=(root / "run").resolve(),
                             batch_kind=BatchKindV2.FIRST_PASS)
    # ProductionBatchComposition owns the run's journal and Coordinator.
    from so101_demo.parallel_batch.contracts import load_runtime_config_any_schema

    config_path = inputs / manifest["roles"]["runtime_config"]["path"]
    config = load_runtime_config_any_schema(config_path)
    # the collection mode (diagnostic or formal) is not the run mode: driving the approved stack is an execute run,
    # and the mode stays recorded in the run's own log and in the frozen manifest

    # the frozen set is re-read once more before the composition is built
    try:
        if ((inputs / "inputs-manifest.json").read_bytes() != manifest_bytes
                or verify_frozen_inputs(inputs / "inputs-manifest.json") != manifest):
            raise ValueError("EPISODE_INPUTS_IDENTITY_CHANGED")
    except (OSError, ValueError) as error:
        print(f"act_first_episode: {error}", file=sys.stderr)
        return 2
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
            payload = manifest_bytes
            destination = root / name
            destination.write_bytes(payload)
            provenance_paths[name] = str(destination)
    log = root / "run.log"
    with log.open("w") as stream:
        stream.write(f"batch_id={batch_id}\nmode={arguments.mode}\nlifecycle={arguments.lifecycle}\n"
                     f"final_cup_pose={target}\ninputs={inputs.resolve()}\n"
                     f"config={type(config).__name__}\ncomposition=ProductionBatchComposition\n"
                     f"points={points_path}\nprovenance={sorted(provenance_paths)}\n"
                     f"broker_image={BROKER_IMAGE} (reused, per the coordinator's decision CP-2760)\n")
        stream.flush()
        os.fsync(stream.fileno())
    from so101_demo.cli.mujoco_parallel_batch import ProductionBatchComposition, PreparedBatch
    from so101_demo.parallel_batch.start_guard import StartGuardPolicy
    from so101_demo.parallel_batch.start_guard_probe import compose_default_start_guard

    catalog = {point.id: points_document["points"][0]}
    catalog_sha = hashlib.sha256(points_path.read_bytes()).hexdigest()
    selection_sha = hashlib.sha256(json.dumps([point.id], separators=(",", ":")).encode()).hexdigest()
    manifest_path = root / "inputs-manifest.json"
    scene_path = inputs / manifest["roles"]["scene_model"]["path"]
    provenance_inputs = {"inputs_manifest": str(manifest_path),
                         "inputs_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                         "expected_inputs_sha256": manifest["inputs_sha256"],
                         "scene_model": str(scene_path), "yolo_weights": str(YOLO_WEIGHTS),
                         "yolo_weights_sha256": config.yolo_weights_sha256,
                         "grounded_root": str(GROUNDED_ROOT),
                         "grounded_manifest_sha256": config.grounded_sam_manifest_sha256,
                         "broker_image": BROKER_IMAGE}
    provenance = _nonhead_provenance(provenance_inputs)
    spec = PreparedBatch(
        start_guard=compose_default_start_guard(StartGuardPolicy(),
                                               state_root=root / "start-guard"),
        request=request, adaptive_request=None, config=config,
        config_path=config_path, adaptive_config_path=None,
        points_path=points_path, catalog=catalog, expected_final_cup_pose_world=tuple(target),
        catalog_sha256=catalog_sha, selection_sha256=selection_sha, broker_image=BROKER_IMAGE,
        # the broker spec takes these four from the specification itself, so they name the frozen documents that
        # really participate here - the development runtime and the scene model - with the same digests the
        # provenance states (CP-2540)
        # the transport checks each declared digest against the file beside it, so both names point at one real
        # file and carry that file's own digest: the frozen scene model, whose copy is byte-identical to the source
        # the transport compares these against the frozen runtime configuration's own fields, so the run declares
        # exactly what that configuration carries rather than a digest of its own choosing (CP-2543)
        yolo_weights=YOLO_WEIGHTS,
        yolo_weights_sha256=config.yolo_weights_sha256,
        grounded_root=GROUNDED_ROOT,
        grounded_manifest_sha256=config.grounded_sam_manifest_sha256,
        provenance=provenance, manifest=manifest,
        provenance_inputs=provenance_inputs, provenance_verifier=_nonhead_provenance,
        start_guard_evidence=None, resume=False)
    # this route runs the broker as a host process beside the run, so its spec names the host copy of the runtime
    # config rather than the container mount (CP-2680/2681)
    # the composition builds the ACT result port when it is given the episode scope below, so the coordinator's ACT gate
    # fires on a real ACT episode (CP-2798/2802)
    # the broker runs in its image, which is the route the coordinator approved (CP-2760): the composition's
    # own default builds that command from the spec, so the container-free builder is not passed here
    # The episodes of this run share one scope document: its values - mode, scene, seed, inputs digest - are the
    # same for every episode, while each episode's own audit source is a different path under that episode's
    # root. It is written here because this is the process that holds the frozen set; the composition only
    # carries the path into the worker specifications (CP-2862).
    from so101_demo.act.collection_scope import build_collection_scope, write_collection_scope

    _scope_path = root / "episode-scope.json"
    write_collection_scope(build_collection_scope(
        str(manifest["mode"]), scene_id=str(manifest["roles"]["anchor_scene"]["identity"]["scene_id"]),
        seed=int(manifest["roles"]["anchor_scene"]["identity"]["seed"]),
        inputs_sha256=str(manifest["inputs_sha256"])), _scope_path)
    composition = ProductionBatchComposition(spec, collection=collection,
        episode_scope_path=str(_scope_path),
        episode_inputs_manifest=str((inputs / "inputs-manifest.json").resolve()))
    # the drive, exactly as the batch path does it: the composition runs itself, its summary becomes an outcome
    # document, and the document is written as the aggregate beside the run's own evidence
    from so101_demo.cli.mujoco_parallel_batch import _run_with_shutdown_signals, _write_json, outcome_document

    evidence_root = request.evidence_root
    if not evidence_root.exists():
        evidence_root.mkdir(parents=True, mode=0o700)
    if not spec.resume:
        _write_json(evidence_root / "batch_manifest.json", dict(spec.manifest))
    summary = _run_with_shutdown_signals(composition.run)
    _summary_code, document = outcome_document(summary)
    _write_json(evidence_root / "aggregate_results.json", document)
    code, document = _verified_run_completion(root)
    print(json.dumps(document, sort_keys=True))
    return code


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
    if arguments.command == 'qc':
        return _qc(arguments)
    if arguments.command == 'verify-commit':
        return _verify_commit(arguments)
    if arguments.command == 'check-export':
        return _check_export(arguments)
    if arguments.command == "run":
        return _run(arguments)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
