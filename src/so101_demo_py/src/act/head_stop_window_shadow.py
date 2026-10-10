"""Shadow stop window versus the native verdicts, on the current broker stack (design section 3).

The shadow window is computed from ``/neck_controller/controller_state`` beside the native
stop witness. This module compares the two *offline* from the sealed run events and the shadow
log; it grants nothing and changes no run. The comparison blocks the switch to the thin JTC
subclass: any disagreement means the topic-based window is not a safe replacement.

Startup. The native verdict is PASS when a ``PREARM_STATUS`` row is READY, with the sim stamp
of its last proof sample. The shadow verdict is PASS when its first complete window finished
before the first goal and, when the native verdict is PASS, its last sim stamp is no later than
the native READY stamp plus 102 ms.

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


def compare_startup(events, shadow):
    ready = [row for row in _rows(events, 'PREARM_STATUS') if _record(row).get('status') == 'READY']
    native_stamp = None
    if ready:
        proof = _record(ready[0]).get('proof')
        stamp = proof.get('last_sim_time_ns') if isinstance(proof, dict) else None
        native_stamp = stamp if type(stamp) is int else None
    native = bool(ready)
    windows = [row for row in _rows(shadow, 'SHADOW_WINDOW') if row.get('phase') == 'startup']
    goals = _rows(shadow, 'SHADOW_FIRST_GOAL')
    window = windows[0]['window'] if windows else None
    margin = None
    if window is None:
        outcome = {'pass': False, 'reason': 'NO_WINDOW'}
    elif goals and type(windows[0].get('mono_ns')) is int and windows[0]['mono_ns'] > goals[0]['mono_ns']:
        outcome = {'pass': False, 'reason': 'AFTER_FIRST_GOAL'}
    elif native and native_stamp is not None:
        bound = native_stamp + limits.STOP_WINDOW_STARTUP_SLACK_NS
        margin = bound - window['last_sim_ns']
        outcome = {'pass': margin >= 0, 'reason': None if margin >= 0 else 'LATE'}
    else:
        outcome = {'pass': True, 'reason': None}
    return _verdict(native, outcome,
                    native_ready_sim_ns=native_stamp, margin_ns=margin,
                    shadow_first_sim_ns=None if window is None else window['first_sim_ns'],
                    shadow_last_sim_ns=None if window is None else window['last_sim_ns'],
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
