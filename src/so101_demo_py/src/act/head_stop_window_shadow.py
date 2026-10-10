"""Shadow stop window versus the native verdicts, on the current broker stack (design section 3).

The shadow window is computed from ``/neck_controller/controller_state`` beside the native
stop witness. This module compares the two *offline* from the sealed run events and the shadow
log; it grants nothing and changes no run. The comparison blocks the switch to the thin JTC
subclass: any disagreement means the topic-based window is not a safe replacement.

Startup. The native verdict is PASS when a ``PREARM_STATUS`` row is READY. Both verdicts are
judged at the native decision instant ``L`` (the last proof sample of the READY status, else of
the native's last evaluation): the shadow is PASS when a quiet run of controller_state samples is
still unbroken at ``L`` and a 51-sample window of it completes no later than ``L`` plus 102 ms.
A run that ended before ``L`` is not evidence.

End. The native verdict is PASS when ``NATIVE_CLOSE`` was acknowledged and ``CANCEL_STOP``
confirmed the raw stop without service errors. The anchor is the sim stamp of that raw-stop
confirmation in ``CANCEL_STOP`` (the native close receipt carries none). The shadow verdict is
PASS when a complete window of samples all stamped after the anchor finished within the stop
window deadline after it.
"""

import json

from . import head_neck_limits as limits


def read_jsonl(path):
    rows = []
    with open(path, 'r', encoding='utf-8') as stream:
        for number, line in enumerate(stream, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError as error:
                raise ValueError(f'SHADOW_JSONL_INVALID: line {number}') from error
            if type(row) is not dict:
                raise ValueError(f'SHADOW_JSONL_INVALID: line {number}')
            rows.append(row)
    return rows


def _rows(rows, kind):
    return [row for row in rows if row.get('kind') == kind]


def _record(row):
    record = row.get('record')
    return record if isinstance(record, dict) else {}


def _verdict(native, shadow, **fields):
    return dict(native='PASS' if native else 'FAIL', shadow='PASS' if shadow['pass'] else 'FAIL',
                shadow_reason=shadow.get('reason'), equal=bool(native) == bool(shadow['pass']),
                **fields)


def _startup_candidates(shadow):
    """The shadow's quiet extents before the first goal: logged runs, else the first window row."""
    runs = [(row['first_sim_ns'], row['last_sim_ns']) for row in _rows(shadow, 'SHADOW_QUIET_RUN')
            if row.get('phase') == 'startup' and type(row.get('first_sim_ns')) is int
            and type(row.get('last_sim_ns')) is int]
    if runs:
        return runs, None
    windows = [row for row in _rows(shadow, 'SHADOW_WINDOW') if row.get('phase') == 'startup']
    if not windows:
        return [], None
    goals = _rows(shadow, 'SHADOW_FIRST_GOAL')
    if goals and type(windows[0].get('mono_ns')) is int and windows[0]['mono_ns'] > goals[0]['mono_ns']:
        return [], 'AFTER_FIRST_GOAL'
    window = windows[0]['window']
    return [(window['first_sim_ns'], window['last_sim_ns'])], None


def compare_startup(events, shadow):
    """Native PREARM versus the shadow, judged at the native decision instant ``L``.

    ``L`` is the sim stamp of the last proof sample of the READY status, or, when the native never
    reached READY, of its last evaluation. The shadow says READY at ``L`` when some quiet run is
    still unbroken at ``L`` and a 51-sample window of it completes no later than ``L`` + 102 ms. A
    run that ended before ``L`` is not evidence for it, however early it completed, and a quiet
    period that began after the native gave up (the post-fault hold) is not a startup run.
    """
    statuses = [row for row in _rows(events, 'PREARM_STATUS') if isinstance(_record(row).get('proof'), dict)]
    ready = [row for row in statuses if _record(row).get('status') == 'READY']
    native = bool(ready)
    decision_row = ready[0] if ready else (statuses[-1] if statuses else None)
    stamp = None if decision_row is None else _record(decision_row)['proof'].get('last_sim_time_ns')
    decision = stamp if type(stamp) is int else None
    candidates, refusal = _startup_candidates(shadow)
    span = (limits.STOP_WINDOW_SAMPLES - 1) * limits.STOP_WINDOW_STEP_NS
    chosen, margin = None, None
    if refusal is not None:
        outcome = {'pass': False, 'reason': refusal}
    elif decision is None:
        outcome = {'pass': False, 'reason': 'NATIVE_NEVER_EVALUATED'}
    elif not candidates:
        outcome = {'pass': False, 'reason': 'NO_WINDOW'}
    else:
        bound = decision + limits.STOP_WINDOW_STARTUP_SLACK_NS
        covering = [run for run in candidates if run[1] >= decision]
        if not covering:
            outcome = {'pass': False, 'reason': 'RUN_ENDED_BEFORE_NATIVE_DECISION'}
            chosen = max(candidates, key=lambda run: run[1])
        else:
            chosen = min(covering, key=lambda run: run[0])
            margin = bound - (chosen[0] + span)
            outcome = {'pass': margin >= 0, 'reason': None if margin >= 0 else 'LATE'}
    return _verdict(native, outcome,
                    native_ready_sim_ns=decision if native else None, native_decision_sim_ns=decision,
                    margin_ns=margin,
                    shadow_first_sim_ns=None if chosen is None else chosen[0],
                    shadow_last_sim_ns=None if chosen is None else chosen[1],
                    shadow_complete_sim_ns=None if chosen is None else chosen[0] + span,
                    slack_ns=limits.STOP_WINDOW_STARTUP_SLACK_NS)


def compare_end(events, shadow):
    closes = [row for row in _rows(events, 'NATIVE_CLOSE')
              if _record(row).get('ack') is True and _record(row).get('error') is None
              and isinstance(_record(row).get('receipt'), dict)
              and _record(row)['receipt'].get('status') in ('ARMED_CLOSED', 'NOT_ARMED_CLOSED')]
    stops = [row for row in _rows(events, 'CANCEL_STOP')
             if _record(row).get('raw_stop_confirmed') is True
             and _record(row).get('cancel_error') is None and _record(row).get('result_error') is None]
    native = bool(closes) and bool(stops)
    stamp = _record(stops[0]).get('raw_stop_confirmed_sim_ns') if stops else None
    stamp = stamp if type(stamp) is int else None
    deadline_ns = round(limits.STOP_WINDOW_DEADLINE_S * 1e9)
    phases = _rows(shadow, 'SHADOW_END_PHASE')
    windows = [row for row in _rows(shadow, 'SHADOW_WINDOW') if row.get('phase') == 'end']
    window = windows[0]['window'] if windows else None
    margin = None
    if not phases:
        outcome = {'pass': False, 'reason': 'NO_END_PHASE'}
    elif stamp is None or phases[0].get('raw_stop_sim_ns') != stamp:
        outcome = {'pass': False, 'reason': 'RAW_STOP_STAMP_MISMATCH'}
    elif window is None:
        outcome = {'pass': False, 'reason': 'NO_WINDOW'}
    elif window['first_sim_ns'] <= stamp:
        outcome = {'pass': False, 'reason': 'NOT_AFTER_RAW_STOP'}
    else:
        margin = stamp + deadline_ns - window['last_sim_ns']
        outcome = {'pass': margin >= 0, 'reason': None if margin >= 0 else 'LATE'}
    return _verdict(native, outcome, raw_stop_sim_ns=stamp, margin_ns=margin, deadline_ns=deadline_ns,
                    shadow_first_sim_ns=None if window is None else window['first_sim_ns'],
                    shadow_last_sim_ns=None if window is None else window['last_sim_ns'])


def compare_run(events, shadow):
    startup, end = compare_startup(events, shadow), compare_end(events, shadow)
    return dict(startup=startup, end=end, equal=startup['equal'] and end['equal'])
