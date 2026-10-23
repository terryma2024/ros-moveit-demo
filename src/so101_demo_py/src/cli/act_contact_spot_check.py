"""Judge one finished container contact-policy spot-check run and write `spot-check-verdict.json`.

The input is the run root of an `act_collect_parallel --spot-check` campaign: its `collection-index.json` (one collected task, a
qualification index with no committed episode), the task result and sealed result the index binds, the phase-2 processed result
the index binds by `processed_result_sha256` (`<run>/processing/<scene>/<attempt>-proc-<n>/processed-result.json`, exactly one
candidate), the QC report that result binds by `qc_report_sha256`, the Teacher `dynamic-execute-manifest.json` that QC bound (the
judged manifest is the bound one, by sha256), and the run's frozen inputs, from
which the contact proposal and the Teacher execution policy are read. Every limit is read from the frozen proposal; nothing is
defaulted. The only fixed value is the over-squeeze close target the CP-3531 reading names (`OVER_SQUEEZE_CLOSE_TARGET_RAD`).

`--spot-check nominal` passes when the Teacher COMPLETED, the endpoint passed, no oracle flag is set, the process summary is complete,
the phase-2 QC passed, and the frozen close target is not the over-squeeze value.

`--spot-check over_squeeze` needs no QC report (QC PASS is a nominal-only criterion): an over-squeeze episode that reaches the
diagnostic hard-stop force flag is refused by the raw-physics sealer (`PHYSICS_RAW_SOURCE_HAZARD`), so phase 2 ends INVALID with
`act_data_qc` NOT_RUN and no QC report. That outcome is accepted only when it is exactly the hazard one (`_hazard_outcome`), and the
Teacher manifest is then bound to the index without QC: index `processed_result_sha256` -> processed result `receipt_sha256` ->
`raw/recording-receipt.json` `documents.teacher_manifest.sha256`. A completed over-squeeze episode that phase 2 grades by the shared Teacher-oracle rule is the second accepted no-QC outcome
(`_oracle_excluded_outcome`): INVALID with `TEACHER_ORACLE_EXCLUDED: ORACLE_CUP_OVERLOAD <phase>` for a phase in the overload window,
`processor_rc` 0, no fault, bound through the same receipt chain. A processed result that does carry a QC report keeps the QC-bound path
(the manifest must equal the QC binding and the receipt binding).

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
import re
import sys

from so101_demo.act.diagnostic_episode_inputs import verify_frozen_inputs
from so101_demo.act.offline.recording_receipt import RECEIPT_KIND, RECEIPT_RELATIVE, TEACHER_MANIFEST_RELATIVE
from so101_demo.act.episode_qc import REFERENCE_CHECK, read_qc_report
from so101_demo.act.processed_result import PROCESSED_KIND, PROCESSED_NAME, data_directory
from so101_demo.core.process_summary import FLAG_COLLISION, FLAG_OVERLOAD, HOLD_PHASES, validate_summary

VERDICT_KIND = 'ACT_CONTACT_SPOT_CHECK_VERDICT'
SPOT_CHECKS = ('nominal', 'over_squeeze')
#: the close target of the over-squeeze source copy (CP-3531): the one fixed value of the judgement
OVER_SQUEEZE_CLOSE_TARGET_RAD = -0.049
#: the phases in which the over-squeeze overload is expected: the close and the grasp checks up to VERIFY_PHYSICAL_GRASP
OVERLOAD_WINDOW = ('CLOSE_GRIPPER', *HOLD_PHASES[:HOLD_PHASES.index('VERIFY_PHYSICAL_GRASP') + 1])
#: the hazard the raw-physics sealer raises for the diagnostic hard-stop force flag (`act.raw_physics_chunks`)
PHYSICS_HAZARD = 'PHYSICS_RAW_SOURCE_HAZARD'
#: the engine latches (`act.offline.engine`) that wrap an exception message as `<prefix>: <message>`; the hazard reaches the processor
#: report as the bare message (the source pump/step) or through these
HAZARD_LATCH_PREFIXES = ('RECORDER_STEP_FAILED', 'RECORDER_FINALIZE_FAILED', 'RECORDER_SOURCE_CLOSE_FAILED', 'RECORDER_SEAL_FAILED',
                         'RECORDER_FINAL_CHECK_FAILED', 'RECORDER_CLOSE_FAILED', 'RECORDER_READBACK_FAILED',
                         'RECORDER_EVENT_HANDLER_FAILED')
ALLOWED_HAZARD_REASONS = (PHYSICS_HAZARD, *(f'{prefix}: {PHYSICS_HAZARD}' for prefix in HAZARD_LATCH_PREFIXES))
#: `runtime.act_processor.processing`: rc 3 -> `OFFLINE_PROCESSOR_INVALID: rc=3; <first four report reasons, 120 chars each>`, 300 chars
_INVALID_PREFIX = 'OFFLINE_PROCESSOR_INVALID: rc=3'
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


_PROC_DIR = re.compile(r'(?P<attempt>.+)-proc-(?P<number>[1-9][0-9]*)')


def _processed_result(run: Path, task: dict, sealed: Path, result_sha: str) -> tuple[Path, dict]:
    """The phase-2 processed result of the task, found the way the production verifier binds it.

    The phase-2 output directory of a scene is `<run>/processing/<scene>/<attempt>-proc-<n>` (`act.processed_result` requires
    `base.name == f"{attempt}-proc-{number}"`, `base.parent.name == scene_id`, `attempt == sealed.parent.name`, and the campaign requires
    it under `<run>/processing/<scene>`). The index entry carries `processed_result_sha256`, the sha256 of its `processed-result.json`.
    The candidates are exactly the directories of that form; the one whose `processed-result.json` hashes to the index value is the
    bound one. None or several is refused."""
    code = 'SPOT_CHECK_BINDING_MISMATCH'
    scene, bound = task['scene_id'], task['processed_result_sha256']
    if type(scene) is not str or type(bound) is not str or not bound:
        raise ValueError(code)
    attempt = sealed.parent.name
    parent = run / 'processing' / scene
    found = []
    for entry in sorted(parent.iterdir()):
        match = _PROC_DIR.fullmatch(entry.name)
        if match is None or match['attempt'] != attempt or entry.is_symlink() or not entry.is_dir():
            continue
        document = entry / PROCESSED_NAME
        if document.is_file() and not document.is_symlink() and _sha(document) == bound:
            found.append((entry, document, int(match['number'])))
    if len(found) != 1:
        raise ValueError(code)
    _entry, path, number = found[0]
    document = _json(path, code)
    if (document.get('kind') != PROCESSED_KIND or document.get('scene_id') != scene or document.get('proc_attempt') != number
            or document.get('task_id') != f'{scene}-proc-{number}' or document.get('phase1_result_sha256') != result_sha):
        raise ValueError(code)
    return path, document


def _receipt_binding(sealed: Path, document: dict, manifest: Path) -> tuple[Path, str]:
    """The sealed recording receipt the processed result binds by `receipt_sha256`, and the Teacher manifest sha256 it records."""
    code = 'SPOT_CHECK_BINDING_MISMATCH'
    receipt = sealed / RECEIPT_RELATIVE
    if receipt.is_symlink() or not receipt.is_file() or _sha(receipt) != document.get('receipt_sha256'):
        raise ValueError(code)
    body = _json(receipt, code)
    entry = (body.get('documents') or {}).get('teacher_manifest') if type(body.get('documents')) is dict else None
    if (body.get('kind') != RECEIPT_KIND or type(entry) is not dict or entry.get('path') != TEACHER_MANIFEST_RELATIVE.as_posix()
            or type(entry.get('sha256')) is not str or _sha(manifest) != entry['sha256']):
        raise ValueError(code)
    return receipt, entry['sha256']


def _hazard_outcome(processed: Path, document: dict, task: dict) -> Path:
    """Accept a processed result with no QC report only when it is exactly the physics-hazard INVALID outcome; returns the
    processor report it binds. Anything else (another reason, a fault, a half-filled QC binding) is refused."""
    code = 'SPOT_CHECK_BINDING_MISMATCH'
    reason = document.get('act_data_reason')
    if (document.get('act_data_status') != 'INVALID' or document.get('act_data_qc') != 'NOT_RUN' or document.get('export_eligible')
            is not False or document.get('processor_rc') != 3 or document.get('diagnostic_fault') != 'none'
            or any(document.get(name) is not None for name in ('qc_report_path', 'qc_report_sha256', 'episode_seal_sha256'))
            or type(reason) is not str
            or task.get('act_data_status') != 'INVALID' or task.get('act_data_qc') != 'NOT_RUN'
            or task.get('act_data_reason') != reason or task.get('export_eligible') is not False):
        raise ValueError(code)
    entry = (document.get('artifacts') or {}).get('processor_report') if type(document.get('artifacts')) is dict else None
    if type(entry) is not dict or entry.get('path') != 'offline-processor-report.json' or type(entry.get('sha256')) is not str:
        raise ValueError(code)
    report = processed.parent / entry['path']
    if report.is_symlink() or not report.is_file() or _sha(report) != entry['sha256']:
        raise ValueError(code)
    body = _json(report, code)
    reasons = body.get('reasons')
    if (body.get('verdict') != 'INVALID' or type(reasons) is not list or not reasons
            or any(item not in ALLOWED_HAZARD_REASONS for item in reasons)
            or reason != (_INVALID_PREFIX + '; ' + '; '.join(str(item)[:120] for item in reasons[:4]))[:300]):
        raise ValueError(code)
    return report


#: `runtime.act_processor.processing`: a QC PASS episode that the shared Teacher-oracle rule excludes grades INVALID with this reason
_ORACLE_EXCLUDED = re.compile(r'TEACHER_ORACLE_EXCLUDED: ' + re.escape(FLAG_OVERLOAD) + r' (?P<phase>[A-Z0-9_#]+)')


def _oracle_excluded_outcome(document: dict, task: dict) -> None:
    """Accept a processed result with no QC report when it is exactly the Teacher-oracle exclusion of an over-squeeze overload
    (plan amendment 6): INVALID, QC NOT_RUN, `processor_rc` 0, no fault, no QC binding, not export eligible, the reason
    `TEACHER_ORACLE_EXCLUDED: ORACLE_CUP_OVERLOAD <phase>` with the phase in the overload window, and the index task agreeing. The
    recording receipt (checked by the caller) binds the Teacher manifest. Anything else is refused."""
    code = 'SPOT_CHECK_BINDING_MISMATCH'
    reason = document.get('act_data_reason')
    match = _ORACLE_EXCLUDED.fullmatch(reason) if type(reason) is str else None
    if (match is None or _phase_name(match['phase']) not in OVERLOAD_WINDOW
            or document.get('act_data_status') != 'INVALID' or document.get('act_data_qc') != 'NOT_RUN'
            or document.get('export_eligible') is not False or document.get('processor_rc') != 0
            or document.get('diagnostic_fault') != 'none'
            or any(document.get(name) is not None for name in ('qc_report_path', 'qc_report_sha256'))
            or task.get('act_data_status') != 'INVALID' or task.get('act_data_qc') != 'NOT_RUN'
            or task.get('act_data_reason') != reason or task.get('export_eligible') is not False):
        raise ValueError(code)


def _bound_files(run: Path, task: dict, spot_check: str) -> dict:
    """The task result, sealed result, phase-2 processed result, Teacher manifest and (QC route) QC report of the one task, each bound
    by sha256. Nominal needs the QC report. Over-squeeze binds the manifest through the recording receipt and takes the QC report only
    when the processed result has one; without it the processed result must be the physics-hazard outcome."""
    code = 'SPOT_CHECK_BINDING_MISMATCH'
    try:
        location = Path(task['location'])
        if not location.is_absolute() or not location.is_relative_to(run) or not location.is_dir():
            raise ValueError(code)
        task_result = location / 'task-result.json'
        sealed = sorted(location.glob('attempts/*/*/sealed'))
        if len(sealed) != 1 or _sha(task_result) != task['task_result_sha256']:
            raise ValueError(code)
        result, manifest = sealed[0] / 'result.json', sealed[0] / 'dynamic/dynamic-execute-manifest.json'
        if _sha(result) != task['result_sha256']:
            raise ValueError(code)
        processed, document = _processed_result(run, task, sealed[0], task['result_sha256'])
        extra = {}
        has_qc = not (document.get('qc_report_path') is None and document.get('qc_report_sha256') is None)
        if spot_check == 'over_squeeze':
            receipt, _manifest_sha = _receipt_binding(sealed[0], document, manifest)
            extra['recording_receipt'] = receipt
            if not has_qc and type(document.get('act_data_reason')) is str and document['act_data_reason'].startswith('TEACHER_ORACLE_EXCLUDED'):
                _oracle_excluded_outcome(document, task)
                extra['route'] = 'recording_receipt_oracle_excluded'
            elif not has_qc:
                extra['processor_report'] = _hazard_outcome(processed, document, task)
                extra['route'] = 'recording_receipt_physics_hazard'
        if spot_check == 'nominal' or has_qc:
            name = document['qc_report_path']
            if type(name) is not str or not name or Path(name).is_absolute() or '..' in Path(name).parts:
                raise ValueError(code)
            qc = data_directory(processed.parent, document) / name
            if qc.is_symlink() or not qc.is_file() or _sha(qc) != document['qc_report_sha256']:
                raise ValueError(code)
            bound = read_qc_report(qc)['checks'][REFERENCE_CHECK]['details']['teacher_manifest_sha256']
            if _sha(manifest) != bound:
                raise ValueError(code)
            extra['qc'] = qc
            extra['route'] = 'qc_report' if spot_check == 'nominal' else 'qc_report_and_recording_receipt'
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ValueError(code) from error
    return dict(task_result=task_result, result=result, processed=processed, manifest=manifest, **extra)


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
    files = _bound_files(run, task, spot_check)
    processed_document = _json(files['processed'], 'SPOT_CHECK_BINDING_MISMATCH')
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
        collection_index=_ref(index_path), task_result=_ref(files['task_result']), sealed_result=_ref(files['result']), processed_result=_ref(files['processed']),
        qc_report=_ref(files['qc']) if 'qc' in files else None, teacher_manifest=_ref(files['manifest']), frozen_inputs=_ref(frozen_manifest),
        proposal=_ref(proposal_path), binding_route=files['route'] if spot_check == 'over_squeeze' else 'qc_report',
        recording_receipt=_ref(files['recording_receipt']) if 'recording_receipt' in files else None,
        processor_report=_ref(files['processor_report']) if 'processor_report' in files else None,
        phase2_outcome=dict(act_data_status=processed_document.get('act_data_status'), act_data_qc=processed_document.get('act_data_qc'),
                            act_data_reason=processed_document.get('act_data_reason'),
                            processor_rc=processed_document.get('processor_rc')),
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
