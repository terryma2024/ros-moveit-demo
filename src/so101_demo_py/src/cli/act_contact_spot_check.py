"""Judge one finished container contact-policy spot-check run and write `spot-check-verdict.json`.

The input is the run root of an `act_collect_parallel --spot-check` campaign: its `collection-index.json` (one collected task, a
qualification index with no committed episode), the task result and sealed result the index binds, the QC report and the Teacher
`dynamic-execute-manifest.json` that QC bound (the judged manifest is the bound one, by sha256), and the run's frozen inputs, from
which the contact proposal and the Teacher execution policy are read. Every limit is read from the frozen proposal; nothing is
defaulted. The only fixed value is the over-squeeze close target the CP-3531 reading names (`OVER_SQUEEZE_CLOSE_TARGET_RAD`).

`--spot-check nominal` passes when the Teacher COMPLETED, the endpoint passed, no oracle flag is set, the process summary is complete,
the phase-2 QC passed, and the frozen close target is not the over-squeeze value.

`--spot-check over_squeeze` (the CP-3531 reading: under Teacher policy v3 the process summary never stops the run) passes when the
frozen close target is the over-squeeze value, the Teacher COMPLETED, `ORACLE_CUP_OVERLOAD` is flagged in a phase from CLOSE_GRIPPER
to VERIFY_PHYSICAL_GRASP, the peak summed force is above the proposal's `maximum_safe_force_n` or the peak compression above its
`maximum_compression_distance_m`, the summary's thresholds equal the proposal's, and no `ORACLE_COLLISION` comes before the first
overload.

Exit codes: 0 PASS (the verdict file is written), 1 FAIL (written), 2 refused (nothing is written): unreadable or inconsistent inputs,
an existing output file, or bad arguments. The verdict is a record, not an activation: it grants nothing by itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys

from so101_demo.act.diagnostic_episode_inputs import verify_frozen_inputs
from so101_demo.act.episode_qc import REFERENCE_CHECK, read_qc_report
from so101_demo.core.process_summary import FLAG_COLLISION, FLAG_OVERLOAD, HOLD_PHASES, validate_summary

VERDICT_KIND = 'ACT_CONTACT_SPOT_CHECK_VERDICT'
SPOT_CHECKS = ('nominal', 'over_squeeze')
#: the close target of the over-squeeze source copy (CP-3531): the one fixed value of the judgement
OVER_SQUEEZE_CLOSE_TARGET_RAD = -0.049
#: the phases in which the over-squeeze overload is expected: the close and the grasp checks up to VERIFY_PHYSICAL_GRASP
OVERLOAD_WINDOW = ('CLOSE_GRIPPER', *HOLD_PHASES[:HOLD_PHASES.index('VERIFY_PHYSICAL_GRASP') + 1])
_NOMINAL_CHECKS = ('teacher_completed', 'endpoint_pass', 'no_oracle_flag', 'summary_complete', 'phase2_qc_pass',
                   'close_target_is_not_the_over_squeeze_value')
_OVER_SQUEEZE_CHECKS = ('teacher_completed', 'close_target_is_over_squeeze', 'overload_in_window', 'peak_over_a_limit',
                        'summary_thresholds_equal_proposal', 'no_collision_before_first_overload')


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json(path, code):
    try:
        document = json.loads(Path(path).read_bytes())
    except (OSError, ValueError) as error:
        raise ValueError(code) from error
    if type(document) is not dict:
        raise ValueError(code)
    return document


def _ref(path) -> dict:
    return dict(path=str(path), sha256=_sha(path))


def _phase_name(key: str) -> str:
    return key.split('#', 1)[0]


def _index(run: Path) -> tuple[dict, dict]:
    index = _json(run / 'collection-index.json', 'SPOT_CHECK_INDEX_INVALID')
    tasks = index.get('collected_tasks')
    if (index.get('kind') != 'act_collection_frozen_index' or index.get('qualification') is not True
            or index.get('committed_episodes') != [] or index.get('scenes_without_evidence')
            or type(tasks) is not list or len(tasks) != 1 or type(tasks[0]) is not dict or index.get('scene_count') != 1):
        raise ValueError('SPOT_CHECK_INDEX_INVALID')
    return index, tasks[0]


def _frozen(run: Path) -> tuple[Path, dict, Path, dict]:
    """(manifest path, frozen set, proposal path, proposal) of the run, the proposal re-read against its frozen hash."""
    manifest = run / 'inputs/frozen/inputs-manifest.json'
    try:
        frozen = verify_frozen_inputs(manifest)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError('SPOT_CHECK_FROZEN_INPUTS_INVALID') from error
    scenes = frozen.get('scene_manifest')
    if frozen.get('mode') != 'preselected_target_diagnostic' or type(scenes) is not dict or scenes.get('scene_count') != 1:
        raise ValueError('SPOT_CHECK_NOT_DIAGNOSTIC')
    code = 'SPOT_CHECK_FROZEN_PROPOSAL_INVALID'
    try:
        entry = frozen['roles']['contact_proposal']
        path = manifest.parent / entry['path']
        if _sha(path) != entry['sha256']:
            raise ValueError(code)
        proposal = _json(path, code)
        thresholds = proposal['payload']['thresholds']
        for name in ('maximum_safe_force_n', 'maximum_compression_distance_m'):
            if type(thresholds[name]) not in (int, float) or isinstance(thresholds[name], bool) or not math.isfinite(thresholds[name]):
                raise ValueError(code)
        if type(proposal.get('policy_fingerprint')) is not str:
            raise ValueError(code)
    except (OSError, KeyError, TypeError) as error:
        raise ValueError(code) from error
    return manifest, frozen, path, proposal


def _bound_files(run: Path, task: dict) -> dict:
    """The task result, sealed result, QC report and Teacher manifest of the one task, each bound by sha256."""
    code = 'SPOT_CHECK_BINDING_MISMATCH'
    try:
        location = Path(task['location'])
        if not location.is_absolute() or not location.is_relative_to(run) or not location.is_dir():
            raise ValueError(code)
        task_result = location / 'task-result.json'
        sealed = sorted(location.glob('attempts/*/*/sealed'))
        if len(sealed) != 1 or _sha(task_result) != task['task_result_sha256']:
            raise ValueError(code)
        result, qc, manifest = sealed[0] / 'result.json', sealed[0] / 'qc-report.json', sealed[0] / 'dynamic/dynamic-execute-manifest.json'
        if _sha(result) != task['result_sha256']:
            raise ValueError(code)
        bound = read_qc_report(qc)['checks'][REFERENCE_CHECK]['details']['teacher_manifest_sha256']
        if _sha(manifest) != bound:
            raise ValueError(code)
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ValueError(code) from error
    return dict(task_result=task_result, result=result, qc=qc, manifest=manifest)


def _equal(left, right) -> bool:
    return (type(left) in (int, float) and not isinstance(left, bool) and math.isfinite(left)
            and math.isclose(left, right, rel_tol=1e-9, abs_tol=0.0))


def judge_run(run, spot_check, *, expected_fingerprint=None) -> dict:
    """The verdict document of one spot-check run; `ValueError('SPOT_CHECK_...')` for any input it cannot judge."""
    if spot_check not in SPOT_CHECKS:
        raise ValueError('SPOT_CHECK_KIND_INVALID')
    run = Path(run)
    if not run.is_absolute() or run.resolve(strict=True) != run:
        raise ValueError('SPOT_CHECK_RUN_INVALID')
    index_path = run / 'collection-index.json'
    _index_document, task = _index(run)
    frozen_manifest, frozen, proposal_path, proposal = _frozen(run)
    if expected_fingerprint is not None and proposal['policy_fingerprint'] != expected_fingerprint:
        raise ValueError('SPOT_CHECK_FINGERPRINT_MISMATCH')
    files = _bound_files(run, task)
    manifest = _json(files['manifest'], 'SPOT_CHECK_SUMMARY_INVALID')
    process = manifest.get('teacher_process_summary')
    try:
        validate_summary(process)
    except ValueError as error:
        raise ValueError('SPOT_CHECK_SUMMARY_INVALID') from error

    thresholds = proposal['payload']['thresholds']
    force_limit = float(thresholds['maximum_safe_force_n'])
    compression_limit_m = float(thresholds['maximum_compression_distance_m'])
    compression_limit_um = compression_limit_m * 1e6
    phases = process['phases']
    in_window = {key: value for key, value in phases.items() if _phase_name(key) in OVERLOAD_WINDOW}
    peak_force = max((value['peak_force_n'] for value in in_window.values() if value['peak_force_n'] is not None), default=None)
    peak_compression = max((value['peak_compression_um'] for value in in_window.values()
                            if value['peak_compression_um'] is not None), default=None)
    overload_phases = [key for key, value in phases.items() if FLAG_OVERLOAD in value['oracle_flags']]
    collision_phases = [key for key, value in phases.items() if FLAG_COLLISION in value['oracle_flags']]
    overload_steps = [step for value in phases.values() for step in (value['first_force_exceedance_step'],
                                                                      value['first_compression_exceedance_step']) if step is not None]
    collision_steps = [pair['first_step'] for value in phases.values() for pair in value['collision_pairs']]
    first_overload = min(overload_steps, default=None)
    first_collision = min(collision_steps, default=None)
    close = frozen.get('teacher_execution_policy', {}).get('values', {}).get('gripper_close_target_rad')
    is_over_squeeze_close = close == OVER_SQUEEZE_CLOSE_TARGET_RAD
    summary_thresholds = process.get('thresholds')
    thresholds_equal = (type(summary_thresholds) is dict and _equal(summary_thresholds.get('summed_force_n'), force_limit)
                        and _equal(summary_thresholds.get('compression_um'), compression_limit_um))
    completed = manifest.get('teacher_execution_status') == 'COMPLETED' and task.get('teacher_execution_status') == 'COMPLETED'

    if spot_check == 'nominal':
        checks = {
            'teacher_completed': completed,
            'endpoint_pass': ((manifest.get('teacher_task_result') or {}).get('result') == 'PASS'
                              and task.get('teacher_task_result') == 'PASS'),
            'no_oracle_flag': not process['flags'][FLAG_OVERLOAD] and not process['flags'][FLAG_COLLISION],
            'summary_complete': process['complete'] is True,
            'phase2_qc_pass': task.get('act_data_qc') == 'PASS',
            'close_target_is_not_the_over_squeeze_value': not is_over_squeeze_close,
        }
    else:
        checks = {
            'teacher_completed': completed,
            'close_target_is_over_squeeze': is_over_squeeze_close,
            'overload_in_window': any(_phase_name(key) in OVERLOAD_WINDOW for key in overload_phases),
            'peak_over_a_limit': ((peak_force is not None and peak_force > force_limit)
                                  or (peak_compression is not None and peak_compression > compression_limit_um)),
            'summary_thresholds_equal_proposal': thresholds_equal,
            'no_collision_before_first_overload': (not collision_steps
                                                   or (first_overload is not None and first_collision >= first_overload)),
        }
    reasons = [name for name, ok in checks.items() if not ok]
    return dict(
        kind=VERDICT_KIND, schema_version=1, spot_check=spot_check, verdict='FAIL' if reasons else 'PASS', reasons=reasons,
        checks=checks, policy_fingerprint=proposal['policy_fingerprint'], run=str(run),
        campaign_id=_index_document.get('campaign_id'), scene_id=task.get('scene_id'), task_id=task.get('task_id'),
        collection_index=_ref(index_path), task_result=_ref(files['task_result']), sealed_result=_ref(files['result']),
        qc_report=_ref(files['qc']), teacher_manifest=_ref(files['manifest']), frozen_inputs=_ref(frozen_manifest),
        proposal=_ref(proposal_path),
        limits=dict(maximum_safe_force_n=force_limit, maximum_compression_distance_m=compression_limit_m,
                    maximum_compression_um=compression_limit_um),
        summary_thresholds=summary_thresholds,
        measured=dict(peak_force_n=peak_force, peak_compression_um=peak_compression, window_phases=list(in_window),
                      overload_phases=overload_phases, collision_phases=collision_phases,
                      first_overload_step=first_overload, first_collision_step=first_collision),
        teacher=dict(execution_status=manifest.get('teacher_execution_status'),
                     task_result=(manifest.get('teacher_task_result') or {}).get('result'),
                     summary_complete=process['complete'], flags=process['flags'],
                     phase2_qc=task.get('act_data_qc')),
        gripper_close_target_rad=close)


def write_verdict(document: dict, output) -> str:
    """Write the verdict once; an existing file is refused, never overwritten. Returns its sha256."""
    payload = (json.dumps(document, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    try:
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    except OSError as error:
        raise ValueError('SPOT_CHECK_VERDICT_NOT_WRITABLE') from error
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(payload).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='act_contact_spot_check', description=__doc__, allow_abbrev=False,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--run', type=Path, required=True, help='the finished spot-check run root')
    parser.add_argument('--spot-check', choices=SPOT_CHECKS, required=True)
    parser.add_argument('--output', type=Path, required=True, help='spot-check-verdict.json; written once')
    parser.add_argument('--expected-fingerprint', help='refuse a run whose frozen proposal has another policy fingerprint')
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        document = judge_run(args.run, args.spot_check, expected_fingerprint=args.expected_fingerprint)
        digest = write_verdict(document, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('act_contact_spot_check: REFUSED: ' + str(error), file=sys.stderr)
        return 2
    print(json.dumps(dict(verdict=document['verdict'], output=str(args.output), sha256=digest), sort_keys=True))
    return 0 if document['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
