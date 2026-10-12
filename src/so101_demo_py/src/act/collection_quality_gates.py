"""The four quality gates of a container-collection qualification, per scene, from the sealed originals.

Every verdict is recomputed from files re-read now: `result.json` (hash-bound by the task readback), `qc-report.json` (hash-bound
by the result), `topic-loss.json` (hash-bound by the QC report), `episode/seal.json` and `episode/records.jsonl` (hash-bound by
the result and by the seal) and the Teacher manifest. Nothing here consumes a number a report or a memo claims.

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


def _qc_report(sealed, result):
    """The QC report the result names, or None when no QC ran. A named report must still hash to the result's binding."""
    digest = result['qc_report_sha256']
    if digest is None:
        return None
    from so101_demo.act import episode_qc

    path = sealed/'qc-report.json'
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
    return ('PASS' if passed else 'FAIL'), file_ref(sealed/'qc-report.json')


_GATES = dict(recorder_lossless=_lossless, frame_continuity=_continuity, qc_valid_rate=_qc_valid,
              teacher_physical_success_rate=_teacher)


def evaluate_scene(proof):
    """`{gate: (outcome, source ref or None, error or None)}` for one verified task readback proof.

    A gate whose evidence cannot be read or contradicts its binding is `NO_EVIDENCE` with the error, so the caller can name it."""
    sealed, result = _result(proof)
    try:
        report = _qc_report(sealed, result)
        failure = None
    except ValueError as error:
        report, failure = None, error
    verdicts = {}
    for name in QUALITY_ORDER:
        try:
            if failure is not None:
                raise failure
            outcome, source = _GATES[name](sealed, result, report)
            verdicts[name] = (outcome, source, None)
        except (OSError, ValueError, TypeError, KeyError) as error:
            verdicts[name] = ('NO_EVIDENCE', None, str(error) or type(error).__name__)
    return verdicts


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
