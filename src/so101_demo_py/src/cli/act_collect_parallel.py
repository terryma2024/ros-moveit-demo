"""CLI: admit and run one ACT collection campaign (Teacher service, instance waves, four-operation task control).

Everything that can be refused is refused before admission, and nothing is spawned before it: the arguments, the plane's
contract, every input file and the frozen per-scene inputs are checked first, in a new run root that only holds files. Admission
then takes the GPU lease and the worker slots; the owner starts the Teacher service once and one shard per slot per wave; `finish`
settles only after every original container stop is proven. An unproven stop leaves the lease and the slots held and exits
non-zero.

Exit codes: 0 completed and settled; 2 refused before admission; 1 anything after admission (admission refusal, a run fault, an
unproven stop, a refused settle). Planes: `--qualification` with `--worker-count` 1/2/8 (functional contract, 8 or 16 scenes, debug only: it never yields a
qualification report) or 8 (gate contract, 40 scenes), otherwise formal (8 workers, `--manifest` is the scene list and `--qualification-report` the container qualification report,
a report built from another run of the registered evidence root, which formal admission recomputes and verifies in full). In the
exact-eight qualification plane `--run-id` must be the gate contract's `qualification_run_id`.

`--spot-check` is the contact-policy spot-check plane (one worker, exactly one scene, `--manifest` the spot-check run contract,
`ACT_COLLECTION_SPOT_CHECK_RUN`). It runs in the diagnostic collection mode: the inputs are frozen in that mode with the scene
list of one row, and the contact receipt may be a plan-signed spot-check candidate. It is a qualification-mode run (the payload
schema is unchanged), has no retry and no qualification report, writes an index that lists no committed episode, and is never
exported or trained on. `--qualification` and `--qualification-report` are refused with it.

Every instance runs as one Docker container per worker, started from the base image with the host-built mount trees (`mount_build`);
native collection is retired (migration M4), and the single-stack native rollout is `act_rollout_native`.

Environment (read by `compose_services`): SO101_UNIFIED_EVIDENCE_ROOT (the registered evidence root), SO101_ACT_GPU_SELECTOR,
SO101_ACT_RESOURCE_BINDING_ID.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace
from typing import Callable, Mapping

from so101_demo.act.parallel_collection_contracts import (
    read_document, validate_run_contract,
)
from so101_demo.runtime.act_fixed_collection_composition import (
    build_container_campaign_owner, collection_parallel_runtime, prepare_collection_operation,
)
from so101_demo.runtime.container_campaign.case_inputs import (
    campaign_binding, freeze_campaign_inputs, write_case_scopes,
)
from so101_demo.runtime.container_campaign.paths import make_campaign_paths, validate_registered_evidence_root
from so101_demo.runtime.container_campaign.registry import ContainerLaunchRegistry
from so101_demo.runtime.container_campaign.mount_build import mount_from_config
from so101_demo.runtime.inference.config import load_campaign_config, load_runtime_document, validate_file_ref
from so101_teleop.unified.compose import compose_services
from so101_teleop.unified.worker_slots import ActWorkerSlot

_ID = r'[a-zA-Z0-9][a-zA-Z0-9_-]*'
_PATH_OPTIONS = ('manifest', 'source', 'collection_config', 'runtime_config', 'campaign_config', 'input_candidates',
                 'teacher_endpoint', 'teacher_execution_policy', 'episode_recorder_policy', 'runtime_policy')


@dataclass(frozen=True)
class CollectionEdges:
    """The external effects of a campaign, each replaceable only by a controlled double; `None` is the production default.

    environment              process environment for `compose_services` (default: `os.environ`)
    act_inventory            physical GPU inventory probe (default: NVML through ctypes)
    act_host_id              stable host id (default: `/etc/machine-id`)
    calibration_identity_probe  installed ACT profile identity (default: `installed_calibration_identity`)
    docker_runner            Docker CLI executor for the Teacher service, the shards and admission's `finish` inspection
                             (default: `docker` through subprocess)
    service_query            Teacher socket query (default: the real `InferenceClient`)
    namespace_reader         container PID namespace reader (default: `/proc` with the documented sudo fallback)
    control_factory          container control channel per shard owner (default: `ContainerTaskControl` over the private socket)
    None of these reaches admission, the owner, the coordinator's decisions or the wave verifier.
    """

    environment: Mapping[str, str] | None = None
    act_inventory: Callable | None = None
    act_host_id: Callable | None = None
    calibration_identity_probe: Callable | None = None
    docker_runner: Callable | None = None
    service_query: Callable | None = None
    namespace_reader: Callable | None = None
    control_factory: Callable | None = None


def _parser():
    parser = argparse.ArgumentParser(prog='act_collect_parallel', description=__doc__, allow_abbrev=False,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--campaign-id', required=True)
    parser.add_argument('--run-id', required=True, help='name of the new run directory under the registered evidence root')
    parser.add_argument('--worker-count', type=int, required=True)
    parser.add_argument('--qualification', action='store_true')
    parser.add_argument('--spot-check', action='store_true',
                        help='the contact-policy spot-check plane: one worker, one scene, the spot-check run contract, '
                             'diagnostic collection mode (refuses --qualification and --qualification-report)')
    parser.add_argument('--manifest', type=Path, required=True,
                        help='functional contract (1/2/8 workers, 8 or 16 scenes, debug only), gate contract (8 workers, 40 scenes), '
                             'or the formal scene list')
    parser.add_argument('--qualification-report', type=Path, help='formal plane only')
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--collection-config', type=Path, required=True)
    parser.add_argument('--runtime-config', type=Path, required=True)
    parser.add_argument('--campaign-config', type=Path, required=True)
    parser.add_argument('--runtime-document', type=Path, default=None,
                        help='the run\'s runtime values (worker counts, time limits, retry rounds): not part of the campaign identity')
    parser.add_argument('--stop-after-phase1', action='store_true',
                        help='stop once phase 1 is proven stopped and durable; phase 2 and the rest run as later stages (act_process_parallel)')
    parser.add_argument('--input-candidates', type=Path, required=True)
    parser.add_argument('--teacher-endpoint', type=Path, required=True)
    parser.add_argument('--teacher-execution-policy', type=Path, required=True)
    parser.add_argument('--episode-recorder-policy', type=Path, required=True)
    parser.add_argument('--runtime-policy', type=Path, required=True,
                        help='development runtime policy; its hard_stops carry the disk floor')
    parser.add_argument('--rig-profile', type=Path, default=None,
                        help='rig profile (config/act/rig-v*.yaml) the campaign collects under; frozen into the inputs. Default: '
                             'rig v1, recorded explicitly. The campaign config\'s rig_profile_sha256 (absent = rig v1) must match')
    return parser


def _regular(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('FIXED_COLLECTION_INPUT_UNREADABLE')
    return path.resolve(strict=True)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _inspector(docker_runner):
    def inspect(container_id):
        result = docker_runner(['docker', 'inspect', container_id])
        documents = json.loads(result.stdout) if result.returncode == 0 else None
        if type(documents) is not list or len(documents) != 1:
            raise ValueError('CONTAINER_INSPECT_UNREADABLE')
        return documents[0]
    return inspect


def _preflight(args, path_options=_PATH_OPTIONS):
    """Pure checks of the arguments and the plane's contract; returns the resolved paths and the scene list to freeze."""
    if re.fullmatch(_ID, args.campaign_id) is None:
        raise ValueError('COLLECTION_CAMPAIGN_ID_INVALID')
    if re.fullmatch(_ID, args.run_id) is None:
        raise ValueError('CAMPAIGN_RUN_ID_INVALID')
    spot_check = bool(args.spot_check)
    if spot_check and args.qualification:
        raise ValueError('COLLECTION_RUN_CONTRACT_MISMATCH')
    if args.worker_count not in ((1,) if spot_check else (1, 2, 8) if args.qualification else (8,)):
        raise ValueError('COLLECTION_WORKER_COUNT_INVALID')
    if (args.qualification or spot_check) and args.qualification_report is not None:
        raise ValueError('COLLECTION_RUN_CONTRACT_MISMATCH')
    if not (args.qualification or spot_check) and args.qualification_report is None:
        raise ValueError('EIGHT_WORKER_QUALIFICATION_REQUIRED')
    resolved = {name: _regular(getattr(args, name)) for name in path_options}
    report = None if args.qualification_report is None else _regular(args.qualification_report)
    try:
        document = read_document(resolved['manifest'])
    except (OSError, ValueError, UnicodeError) as error:
        raise ValueError('COLLECTION_MANIFEST_INVALID') from error
    if args.qualification or spot_check:
        plane, contract = validate_run_contract(document)
        if (plane == 'spot_check') != spot_check or contract['worker_count'] != args.worker_count:
            raise ValueError('COLLECTION_RUN_CONTRACT_MISMATCH')
        if plane == 'gate' and args.run_id != contract['qualification_run_id']:
            raise ValueError('QUALIFICATION_RUN_ID_MISMATCH')
        scenes = validate_file_ref(contract['scene_manifest'])
        scenes_sha = contract['scene_manifest']['sha256']
    else:
        scenes, scenes_sha = resolved['manifest'], _sha(resolved['manifest'])
        if type(document.get('scenarios')) is not list or not document['scenarios']:
            raise ValueError('COLLECTION_MANIFEST_INVALID')
    return resolved, report, scenes, scenes_sha


def _describe(error):
    """The error and its causes, so a wrapped refusal still names the code that produced it."""
    parts = []
    while error is not None and len(parts) < 5:
        parts.append(str(error) or type(error).__name__)
        error = error.__cause__
    return ' <- '.join(parts)


def _fail(message, code):
    print('act_collect_parallel: ' + message, file=sys.stderr)
    return code


def main(argv=None, *, edges=None) -> int:
    args = _parser().parse_args(argv)
    edges = CollectionEdges() if edges is None else edges
    spot_check = bool(args.spot_check)
    plane = 'spot_check' if spot_check else 'qualification' if args.qualification else 'formal'
    try:
        resolved, report, scenes, scenes_sha = _preflight(args)
        services = compose_services(edges.environment, act_inventory=edges.act_inventory, act_host_id=edges.act_host_id,
            act_container_inspect=None if edges.docker_runner is None else _inspector(edges.docker_runner),
            act_calibration_identity=edges.calibration_identity_probe)
        workload = services.act_workload
        if workload is None:
            raise ValueError(f'ACT_COLLECTION_UNIFIED_SERVICE_UNAVAILABLE: {services.act_error}')
        config_sha = _sha(resolved['campaign_config'])
        config = load_campaign_config(resolved['campaign_config'], roles=('teacher',), expected_sha256=config_sha)
        mount_from_config(config)                   # MOUNT_BUILD_REQUIRED before the run id is used or anything is frozen
        runtime_document = (None if args.runtime_document is None
                            else load_runtime_document(_regular(args.runtime_document)))
        registered = validate_registered_evidence_root(config['evidence_root'], config['evidence_root'],
                                                      registration=workload.root_registration)
        paths = make_campaign_paths(registered, args.run_id)
        run = paths['run']
        try:
            inputs_manifest = freeze_campaign_inputs(run, candidates=resolved['input_candidates'], scene_manifest=scenes,
                teacher_endpoint=resolved['teacher_endpoint'],
                teacher_execution_policy=resolved['teacher_execution_policy'],
                episode_recorder_policy=resolved['episode_recorder_policy'], runtime_policy=resolved['runtime_policy'],
                rig_profile=None if getattr(args, 'rig_profile', None) is None else _regular(args.rig_profile),
                plane=plane)
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise ValueError('CASE_INPUTS_FREEZE_REFUSED: ' + str(error)) from error
        case_inputs = write_case_scopes(run, inputs_manifest=inputs_manifest, plane=plane)
        binding = campaign_binding(inputs_manifest, campaign_config=config, plane=plane,
            collection_config_sha256=_sha(resolved['collection_config']), scene_manifest_sha256=scenes_sha)
        arguments = SimpleNamespace(campaign_id=args.campaign_id, manifest=resolved['manifest'], source=resolved['source'],
            runtime_config=resolved['runtime_config'], collection_config=resolved['collection_config'],
            campaign_config=resolved['campaign_config'], root=run, qualification=bool(args.qualification or spot_check),
            spot_check=spot_check, qualification_report=report, worker_count=args.worker_count,
            instance_launcher='container', runtime_document=runtime_document)
        spec = prepare_collection_operation(arguments, services=services,
                                            contact_policy_fingerprint=binding['contact_policy_fingerprint'])
        parallel_runtime = collection_parallel_runtime(resolved['collection_config'])
    except (OSError, ValueError, KeyError, TypeError) as error:
        return _fail('REFUSED: ' + _describe(error), 2)
    try:
        context = workload.start(spec, allow_existing=False)
    except Exception as error:  # noqa: BLE001 - admission refuses with its own code; nothing was taken
        return _fail('ADMISSION_REFUSED: ' + _describe(error), 1)
    approved = tuple(dict.fromkeys(Path(value) for value in (run / 'inputs', parallel_runtime['path'],
        config['controlled_runtime']['path'], config['teacher_service']['model']['weights']['path'])))
    try:
        owner = build_container_campaign_owner(context, config=config, paths=paths,
            slots=tuple(ActWorkerSlot(**item) for item in spec.payload['worker_slots']),
            manifest_path=resolved['manifest'], scene_manifest=binding['scene_manifest'], case_inputs=case_inputs,
            parallel_runtime=parallel_runtime, approved_inputs=approved, qualification=bool(args.qualification or spot_check),
            collection_mode='preselected_target_diagnostic' if spot_check else 'formal',
            approved_disk_floor_bytes=binding['disk_floor_bytes'], docker_runner=edges.docker_runner,
            service_query=edges.service_query, namespace_reader=edges.namespace_reader,
            control_factory=edges.control_factory, admit_processor_slots=workload.admit_processor_slots,
            runtime_document=runtime_document, stop_after_phase1=args.stop_after_phase1)
    except Exception as error:  # noqa: BLE001 - admitted but not built: nothing was launched, so ask admission to settle
        return _settle_unbuilt(workload, context, run, error)
    cleanup = []

    async def drive():
        try:
            return await owner.run(read_document(resolved['manifest'])), None
        except Exception as error:  # noqa: BLE001 - reported after the stop proof
            return None, error
        finally:
            cleanup.append(await owner.close())
    result, failure = asyncio.run(drive())
    owner.registry.close()
    if not cleanup or cleanup[0].get('terminated') is not True:
        if failure is not None:
            print('act_collect_parallel: CAMPAIGN_RUN_FAILED: ' + _describe(failure), file=sys.stderr)
        return _fail('CAMPAIGN_CLEANUP_UNCONFIRMED: lease and worker slots stay held; see host/campaign-cleanup.json', 1)
    try:
        workload.finish(context, cleanup_confirmed=True)
    except Exception as error:  # noqa: BLE001 - a refused settle leaves everything held
        return _fail('CAMPAIGN_SETTLE_REFUSED: ' + str(error), 1)
    record_error = cleanup[0].get('cleanup_record_error')
    if record_error is not None:
        # the stop is proven and the lease released; the cleanup record could not be written: a second error beside the run's own
        if failure is not None:
            print('act_collect_parallel: CAMPAIGN_RUN_FAILED: ' + _describe(failure), file=sys.stderr)
        return _fail('CLEANUP_RECORD_FAILED: ' + record_error, 1)
    if failure is not None:
        return _fail('CAMPAIGN_RUN_FAILED: ' + _describe(failure), 1)
    summary = dict(campaign_id=result['campaign_id'], run=str(run), plane=plane,
                   scene_count=result['scene_count'], waves=len(result['waves']))
    retry = result.get('retry')
    if retry is not None:
        summary.update(retry_rounds=retry['rounds_run'], recovered=retry['recovered'])
    if result.get('stop'):
        summary['stop'] = result['stop']
    task_faults = result.get('task_faults')
    if task_faults:
        summary['task_faults'] = task_faults
    print(json.dumps(summary, sort_keys=True))
    if retry is not None and retry['status'] == 'ABORTED':
        return _fail('CAMPAIGN_RETRY_ABORTED: ' + str(retry.get('reason')) + '; see host/campaign-result.json', 1)
    if task_faults:
        # The run root holds complete results; the exit code only tells scripts that some scenes faulted.
        return _fail('CAMPAIGN_COMPLETED_WITH_FAULTS: ' + str(len(task_faults)) + ' scene(s) faulted; see host/campaign-result.json', 1)
    return 0


def _settle_unbuilt(workload, context, run, error):
    """The owner could not be built. Construction launches nothing, so with an empty launch registry there is nothing to stop."""
    print('act_collect_parallel: CAMPAIGN_OWNER_BUILD_FAILED: ' + _describe(error), file=sys.stderr)
    registry = None
    try:
        registry = ContainerLaunchRegistry(run / 'host/launches.sqlite3', create=False)
        if registry.records():
            return _fail('CAMPAIGN_CLEANUP_UNCONFIRMED: launches exist; lease and worker slots stay held', 1)
        registry.close()
        registry = None
        workload.finish(context, cleanup_confirmed=True)
    except Exception as settle:  # noqa: BLE001 - whatever admission refuses stays held
        return _fail('CAMPAIGN_SETTLE_REFUSED: ' + str(settle), 1)
    finally:
        if registry is not None:
            registry.close()
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
