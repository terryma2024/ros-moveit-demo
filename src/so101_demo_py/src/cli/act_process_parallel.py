"""CLI: run one later stage of an ACT collection campaign whose phase 1 was run with `act_collect_parallel --stop-after-phase1`.

The stages are `--phase2` (process the recorded waves), `--retry-round N` (record the INVALID scenes again and process them; N is
1..3) and `--finalize` (the campaign result and the frozen index). Each is its own admission of the same campaign: it takes the GPU
lease and its own worker slots, runs, proves its containers stopped and settles, so the GPU is free between stages. The run root is
the one phase 1 made; a stage writes its record `host/<stage>-complete.json` last, chained by hash to the record before it.

Everything that can be refused is refused before admission: the stage selection, the arguments, the plane's contract and the stage
records (the stage before, the logic document, the admitted inputs, the images; `STAGE_*` codes). A stage runs once
(`STAGE_ALREADY_COMPLETE`), `--retry-round` is refused on a qualification run (`STAGE_RETRY_ON_QUALIFICATION_RUN`), after a retry
round that did not run (`STAGE_RETRY_ROUND_OUT_OF_ORDER`) and beyond `retry_invalid_max_rounds` (`STAGE_RETRY_ROUNDS_EXCEEDED`).

The inputs are the ones phase 1 was given (the same files, checked by hash); the runtime document may differ from stage to stage.
Exit codes as `act_collect_parallel`: 0 completed and settled; 2 refused before admission; 1 anything after admission.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from so101_demo.act.parallel_collection_contracts import read_document
from so101_demo.cli.act_collect_parallel import (
    CollectionEdges, _describe, _inspector, _native_edges, _preflight, _regular, _settle_unbuilt, _sha)
from so101_demo.runtime import act_fixed_collection_composition as composition
from so101_demo.runtime.container_campaign import stage_records
from so101_demo.runtime.container_campaign.case_inputs import (
    FROZEN_DIRECTORY, INPUTS_DIRECTORY, MANIFEST_NAME, campaign_binding, read_case_scopes)
from so101_demo.runtime.container_campaign.paths import existing_campaign_paths, validate_registered_evidence_root
from so101_demo.runtime.inference.config import load_campaign_config, load_runtime_document
from so101_teleop.unified.compose import compose_services
from so101_teleop.unified.worker_slots import ActWorkerSlot

_PATH_OPTIONS = ('manifest', 'source', 'collection_config', 'runtime_config', 'campaign_config')


def _parser():
    parser = argparse.ArgumentParser(prog='act_process_parallel', description=__doc__, allow_abbrev=False,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    stage = parser.add_mutually_exclusive_group()
    stage.add_argument('--phase2', action='store_true')
    stage.add_argument('--retry-round', type=int, default=None, metavar='N')
    stage.add_argument('--finalize', action='store_true')
    parser.add_argument('--campaign-id', required=True)
    parser.add_argument('--run-id', required=True, help='the run directory phase 1 made under the registered evidence root')
    parser.add_argument('--worker-count', type=int, required=True)
    parser.add_argument('--qualification', action='store_true')
    parser.add_argument('--spot-check', action='store_true')
    parser.add_argument('--instance-launcher', choices=('container', 'native'), default='container')
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--qualification-report', type=Path)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--collection-config', type=Path, required=True)
    parser.add_argument('--runtime-config', type=Path, required=True)
    parser.add_argument('--campaign-config', type=Path, required=True)
    parser.add_argument('--runtime-document', type=Path, default=None)
    return parser


def _stage_name(args):
    chosen = [name for name, on in (('phase2', args.phase2), ('finalize', args.finalize),
                                    ('retry', args.retry_round is not None)) if on]
    if len(chosen) != 1:
        raise ValueError('STAGE_SELECTION_INVALID')
    if chosen[0] == 'retry':
        if type(args.retry_round) is not int or not 1 <= args.retry_round <= stage_records.MAX_RETRY_ROUNDS:
            raise ValueError('STAGE_RETRY_ROUNDS_EXCEEDED')
        if args.qualification or args.spot_check:
            raise ValueError('STAGE_RETRY_ON_QUALIFICATION_RUN')
        return stage_records.retry_stage(args.retry_round)
    return stage_records.PHASE2 if chosen[0] == 'phase2' else stage_records.FINALIZE


async def _run_stage(owner, stage, manifest):
    if stage == stage_records.PHASE2:
        return await owner.stage_phase2(manifest)
    if stage == stage_records.FINALIZE:
        return await owner.stage_finalize(manifest)
    return await owner.stage_retry(manifest, int(stage.rsplit('-', 1)[1]))


def main(argv=None, *, edges=None) -> int:
    args = _parser().parse_args(argv)
    edges = CollectionEdges() if edges is None else edges
    spot_check = bool(args.spot_check)
    plane = 'spot_check' if spot_check else 'qualification' if args.qualification else 'formal'
    try:
        stage = _stage_name(args)
        resolved, report, scenes, scenes_sha = _preflight(args, _PATH_OPTIONS)
        services = compose_services(edges.environment, act_inventory=edges.act_inventory, act_host_id=edges.act_host_id,
            act_container_inspect=None if edges.docker_runner is None else _inspector(edges.docker_runner),
            act_calibration_identity=edges.calibration_identity_probe)
        workload = services.act_workload
        if workload is None:
            raise ValueError(f'ACT_COLLECTION_UNIFIED_SERVICE_UNAVAILABLE: {services.act_error}')
        config_sha = _sha(resolved['campaign_config'])
        config = load_campaign_config(resolved['campaign_config'], roles=('teacher',), expected_sha256=config_sha)
        runtime_document = (None if args.runtime_document is None
                            else load_runtime_document(_regular(args.runtime_document)))
        registered = validate_registered_evidence_root(config['evidence_root'], config['evidence_root'],
                                                      registration=workload.root_registration)
        paths = existing_campaign_paths(registered, args.run_id)
        run = paths['run']
        inputs_manifest = dict(path=str(run / INPUTS_DIRECTORY / FROZEN_DIRECTORY / MANIFEST_NAME),
                               sha256=_sha(run / INPUTS_DIRECTORY / FROZEN_DIRECTORY / MANIFEST_NAME))
        stage_records.check_before_admission(paths['host'], stage,
            logic=dict(path=str(resolved['campaign_config']), sha256=config_sha))
        case_inputs = read_case_scopes(run, inputs_manifest=inputs_manifest, plane=plane)
        binding = campaign_binding(inputs_manifest, campaign_config=config, plane=plane,
            collection_config_sha256=_sha(resolved['collection_config']), scene_manifest_sha256=scenes_sha)
        arguments = SimpleNamespace(campaign_id=args.campaign_id, manifest=resolved['manifest'], source=resolved['source'],
            runtime_config=resolved['runtime_config'], collection_config=resolved['collection_config'],
            campaign_config=resolved['campaign_config'], root=run, qualification=bool(args.qualification or spot_check),
            spot_check=spot_check, qualification_report=report, worker_count=args.worker_count,
            instance_launcher=args.instance_launcher, runtime_document=runtime_document, stage=stage)
        spec = composition.prepare_collection_operation(arguments, services=services,
                                                        contact_policy_fingerprint=binding['contact_policy_fingerprint'])
        parallel_runtime = composition.collection_parallel_runtime(resolved['collection_config'])
        manifest_document = read_document(resolved['manifest'])
    except (OSError, ValueError, KeyError, TypeError) as error:
        return _fail_stage('REFUSED: ' + _describe(error), 2)
    try:
        context = workload.start(spec, allow_existing=False)
    except Exception as error:  # noqa: BLE001 - admission refuses with its own code; nothing was taken
        return _fail_stage('ADMISSION_REFUSED: ' + _describe(error), 1)
    approved = tuple(dict.fromkeys(Path(value) for value in (run / 'inputs', parallel_runtime['path'],
        config['controlled_runtime']['path'], config['teacher_service']['model']['weights']['path'])))
    try:
        owner = composition.build_container_campaign_owner(context, config=config, paths=paths,
            slots=tuple(ActWorkerSlot(**item) for item in spec.payload['worker_slots']),
            manifest_path=resolved['manifest'], scene_manifest=binding['scene_manifest'], case_inputs=case_inputs,
            parallel_runtime=parallel_runtime, approved_inputs=approved, qualification=bool(args.qualification or spot_check),
            collection_mode='preselected_target_diagnostic' if spot_check else 'formal',
            approved_disk_floor_bytes=binding['disk_floor_bytes'], docker_runner=edges.docker_runner,
            service_query=edges.service_query, namespace_reader=edges.namespace_reader,
            control_factory=edges.control_factory, instance_launcher=args.instance_launcher,
            native=_native_edges(edges, args), admit_processor_slots=workload.admit_processor_slots,
            runtime_document=runtime_document, stage=stage)
    except Exception as error:  # noqa: BLE001 - admitted but not built: nothing was launched, so ask admission to settle
        return _settle_unbuilt(workload, context, run, error)
    cleanup = []

    async def drive():
        try:
            return await _run_stage(owner, stage, manifest_document), None
        except Exception as error:  # noqa: BLE001 - reported after the stop proof
            return None, error
        finally:
            cleanup.append(await owner.close())
    result, failure = asyncio.run(drive())
    owner.registry.close()
    if not cleanup or cleanup[0].get('terminated') is not True:
        if failure is not None:
            print('act_process_parallel: STAGE_FAILED: ' + _describe(failure), file=sys.stderr)
        return _fail_stage('CAMPAIGN_CLEANUP_UNCONFIRMED: lease and worker slots stay held; see host/campaign-cleanup.json', 1)
    try:
        workload.finish(context, cleanup_confirmed=True)
    except Exception as error:  # noqa: BLE001 - a refused settle leaves everything held
        return _fail_stage('CAMPAIGN_SETTLE_REFUSED: ' + str(error), 1)
    if failure is not None:
        return _fail_stage('STAGE_FAILED: ' + _describe(failure), 1)
    print(json.dumps(dict(run=str(run), plane=plane, **{name: value for name, value in result.items()
                                                          if name in ('campaign_id', 'stage', 'status', 'reason', 'processing')}),
                     sort_keys=True))
    return 0


def _fail_stage(message, code):
    print('act_process_parallel: ' + message, file=sys.stderr)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
