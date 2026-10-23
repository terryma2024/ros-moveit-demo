"""The four quality gates of a container-collection qualification, per scene, from the sealed originals.

Every verdict is recomputed from files re-read now: `result.json` (hash-bound by the task readback), `qc-report.json` (hash-bound
by the result), `topic-loss.json` (hash-bound by the QC report), `episode/seal.json` and `episode/records.jsonl` (hash-bound by
the result and by the seal) and the Teacher manifest. Nothing here consumes a number a report or a memo claims.

Two-phase collection. A phase-1 result is `PENDING_QC`: it holds the Teacher half (the Teacher manifest, `result.json`) and the data
half lives under the phase-2 output directory (`processed-result.json`, `episode/`, `qc-report.json`, `topic-loss.json`). With a
`processed` readback record `evaluate_scene` reads the Teacher gate from the phase-1 location and the three data gates from the
phase-2 locations; the phase-1 result hash binds both. A scene phase 2 did not deliver (no record) and a scene phase 1 never recorded
have `NO_EVIDENCE` for the gates they lack: it is never a pass, never a way out of a denominator, and not an evidence error.

A scene is `PASS`, `FAIL` or `NO_EVIDENCE`. `NO_EVIDENCE` means the sealed result carries no authenticated evidence for that gate
(for example a perception no-pose result has no episode, QC report or loss document); it is never a pass and the scene stays in
the denominator. A document that exists but contradicts the hash that binds it raises `EVIDENCE_INVALID`.
"""

import hashlib
import json
import math
from pathlib import Path

from so101_demo.runtime.inference.config import _open_regular

QUALITY_ORDER = ('recorder_lossless', 'frame_continuity', 'qc_valid_rate', 'teacher_physical_success_rate')
OUTCOMES = ('PASS', 'FAIL', 'NO_EVIDENCE')
_CADENCE_S = 0.1
_CADENCE_TOLERANCE_S = 1e-6
_LIMIT = 64*1024*1024


def _invalid():
    return ValueError('EVIDENCE_INVALID')


def _read(path):
    try:
        with _open_regular(path) as stream:
            raw = stream.read(_LIMIT+1)
    except (OSError, ValueError) as error:
        raise _invalid() from error
    if len(raw) > _LIMIT:
        raise _invalid()
    return raw


def _document(raw):
    try:
        value = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as error:
        raise _invalid() from error
    if type(value) is not dict:
        raise _invalid()
    return value


def file_ref(path):
    return dict(path=str(path), sha256=hashlib.sha256(_read(path)).hexdigest())


def intervals_on_grid(times):
    """True when every consecutive recorded instant is one 10 Hz step apart (a single row has no interval to break)."""
    values = list(times)
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
        raise _invalid()
    return all(math.isclose(later-earlier, _CADENCE_S, rel_tol=0, abs_tol=_CADENCE_TOLERANCE_S)
               for earlier, later in zip(values, values[1:]))


def _result(proof):
    sealed = Path(proof['location'])
    raw = _read(sealed/'result.json')
    if hashlib.sha256(raw).hexdigest() != proof['result_sha256']:
        raise _invalid()
    return sealed, _document(raw)


def _qc_name(result):
    return result.get('qc_report_name', 'qc-report.json')


def _qc_report(sealed, result):
    """The QC report the result names, or None when no QC ran. A named report must still hash to the result's binding."""
    digest = result['qc_report_sha256']
    if digest is None:
        return None
    from so101_demo.act import episode_qc

    path = sealed/_qc_name(result)
    if hashlib.sha256(_read(path)).hexdigest() != digest:
        raise _invalid()
    try:
        return episode_qc.read_qc_report(path)
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise _invalid() from error


def _lossless(sealed, result, report):
    from so101_demo.act import topic_loss

    if report is None:
        return 'NO_EVIDENCE', None
    path = sealed/topic_loss.DOCUMENT_NAME
    try:
        check = topic_loss.qc_check(sealed/'episode', identity=report['identity'], path=path)
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise _invalid() from error
    if check != report['checks'][topic_loss.CHECK_NAME]:
        raise _invalid()
    document = _document(_read(path))
    lost = document['transport_lost']
    passed = (check['status'] == 'PASS' and document['status'] == 'PASS' and document['lost_in_window'] == 0
              and not document['reasons'] and lost.get('reported') is not None and lost.get('unattributed', 0) == 0
              and all(item['missing_in_window'] == 0 for item in document['topics'].values() if item['used']))
    return ('PASS' if passed else 'FAIL'), file_ref(path)


def _continuity(sealed, result, report):
    if report is None or result['episode_seal_sha256'] is None:
        return 'NO_EVIDENCE', None
    seal = sealed/'episode'/'seal.json'
    if hashlib.sha256(_read(seal)).hexdigest() != result['episode_seal_sha256']:
        raise _invalid()
    document = _document(_read(seal))
    rows = [json.loads(line) for line in _read(sealed/'episode'/'records.jsonl').decode('utf-8').splitlines() if line]
    if type(document.get('record_count')) is not int or document['record_count'] != len(rows):
        raise _invalid()
    try:
        times = [row['observation']['sim_time_s'] for row in rows]
    except (KeyError, TypeError) as error:
        raise _invalid() from error
    return ('PASS' if intervals_on_grid(times) else 'FAIL'), file_ref(seal)


def _teacher(sealed, result, report):
    manifest = sealed/'dynamic'/'dynamic-execute-manifest.json'
    claim = (result['teacher_execution_status'], result['teacher_task_result'])
    try:
        present = manifest.is_file() and not manifest.is_symlink()
    except OSError as error:
        raise _invalid() from error
    if not present:
        # the manifest-free form is the perception no-pose business result: the Teacher never ran, nothing to grade
        if claim != ('INDETERMINATE', 'UNCONFIRMED'):
            raise _invalid()
        return 'NO_EVIDENCE', file_ref(sealed/'result.json')
    document = _document(_read(manifest))
    stated = document.get('teacher_task_result')
    if (document.get('teacher_execution_status') != claim[0] or type(stated) is not dict
            or stated.get('result') != claim[1]):
        raise _invalid()
    if claim == ('COMPLETED', 'PASS'):
        outcome = 'PASS'
    elif claim[1] == 'UNCONFIRMED':
        outcome = 'NO_EVIDENCE'
    else:
        outcome = 'FAIL'
    return outcome, file_ref(manifest)


def _qc_valid(sealed, result, report):
    if report is None:
        return 'NO_EVIDENCE', None
    passed = result['act_data_qc'] == 'PASS' and report['status'] == 'PASS'
    return ('PASS' if passed else 'FAIL'), file_ref(sealed/_qc_name(result))


_GATES = dict(recorder_lossless=_lossless, frame_continuity=_continuity, qc_valid_rate=_qc_valid,
              teacher_physical_success_rate=_teacher)


#: why a scene is outside the `QC_VALID_EPISODES` population (human decision D2); a closed vocabulary
EXCLUSION_REASONS = ('NO_QC_EVIDENCE', 'DATA_NOT_VALID', 'QC_NOT_PASS')


def qc_valid_membership(result, report):
    """`(member, reason)`: whether the scene is an episode whose data is VALID with QC PASS, and why not when it is not.

    Judged from the re-read result and QC report: `NO_QC_EVIDENCE` (no QC report: a perception no-pose or any result whose data
    was INVALID before QC), `DATA_NOT_VALID` (the data status is not VALID) and `QC_NOT_PASS` (QC ran and did not pass)."""
    if report is None:
        return False, 'NO_QC_EVIDENCE'
    if result['act_data_status'] != 'VALID':
        return False, 'DATA_NOT_VALID'
    if result['act_data_qc'] != 'PASS' or report['status'] != 'PASS':
        return False, 'QC_NOT_PASS'
    return True, None


def _processed(processed, proof, result):
    """`(data directory, result for the data gates)` from a phase-2 readback record, re-reading `processed-result.json`.

    The document must hash to the record, name the phase-1 result hash of the proof, and agree with the directory the record names;
    the data verdict and the bindings of the data gates come from it, the Teacher facts stay those of the phase-1 `result.json`."""
    from so101_demo.act.processed_result import PROCESSED_NAME, data_directory

    try:
        output = Path(processed['output_dir'])
        raw = _read(output/PROCESSED_NAME)
        if hashlib.sha256(raw).hexdigest() != processed['processed_result']['sha256']:
            raise _invalid()
        document = _document(raw)
        if (document.get('phase1_result_sha256') != proof['result_sha256']
                or processed.get('phase1_result_sha256') != proof['result_sha256']
                or Path(processed['data_dir']) != data_directory(output, document)):
            raise _invalid()
        merged = dict(result, **{name: document[name] for name in (
            'act_data_status', 'act_data_reason', 'act_data_qc', 'export_eligible', 'episode_seal_sha256', 'qc_report_sha256')})
        merged['qc_report_name'] = document['qc_report_path'] or 'qc-report.json'
    except (KeyError, TypeError) as error:
        raise _invalid() from error
    return Path(processed['data_dir']), merged


def _no_evidence(error=None):
    return ('NO_EVIDENCE', None, error)


def evaluate_scene(proof, processed=None):
    """`(verdicts, membership)` for one verified task readback proof.

    `verdicts` is `{gate: (outcome, source ref or None, error or None)}`: a gate whose evidence cannot be read or contradicts its
    binding is `NO_EVIDENCE` with the error, so the caller can name it. `membership` is `(member, reason)` of
    `qc_valid_membership`; when the QC evidence itself cannot be read the scene is kept in the population (`(True, None)`), so
    unreadable evidence is never a way out of a gate.

    `proof` is None for a scene phase 1 never recorded (every gate `NO_EVIDENCE`, no error). A proof whose `processing` is `PENDING`
    is a phase-1 record: its data gates read `processed`, the phase-2 readback record (`act.processed_result`), or, when there is
    none, have no evidence; its Teacher gate always reads the phase-1 location."""
    if proof is None:
        return {name: _no_evidence() for name in QUALITY_ORDER}, (True, None)
    sealed, result = _result(proof)
    pending = proof.get('processing') == 'PENDING'
    data, data_result, available, failure = sealed, result, True, None
    if pending:
        if processed is None:
            available = False
        else:
            try:
                data, data_result = _processed(processed, proof, result)
            except ValueError as error:
                failure = error
    report, membership = None, (True, None)
    if available and failure is None:
        try:
            report = _qc_report(data, data_result)
            membership = qc_valid_membership(data_result, report)
        except ValueError as error:
            failure = error
    verdicts = {}
    for name in QUALITY_ORDER:
        if name == 'teacher_physical_success_rate':
            # the Teacher half is phase 1's; only a legacy inline result lets a data failure take it down as well
            blocked = failure if not pending else None
            args = (sealed, result, report)
        elif not available:
            verdicts[name] = _no_evidence()
            continue
        else:
            blocked, args = failure, (data, data_result, report)
        try:
            if blocked is not None:
                raise blocked
            outcome, source = _GATES[name](*args)
            verdicts[name] = (outcome, source, None)
        except (OSError, ValueError, TypeError, KeyError) as error:
            verdicts[name] = _no_evidence(str(error) or type(error).__name__)
    return verdicts, membership


def apply_rule(rule, outcomes):
    """`(passed, verdict)` of a validated rule over the outcomes of the whole population, in integers only.

    `EVERY` passes only when every scene passed. `AT_LEAST` passes when `passed * denominator >= numerator * population`."""
    population = len(outcomes)
    passed = sum(1 for outcome in outcomes if outcome == 'PASS')
    if population == 0:
        return passed, 'FAIL'
    if rule['pass']['kind'] == 'EVERY':
        ok = passed == population
    else:
        ok = passed*rule['pass']['denominator'] >= rule['pass']['numerator']*population
    return passed, 'PASS' if ok else 'FAIL'
