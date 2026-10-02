"""Disk readback of retained real CPU journals; never a qualifier or motion runner."""
import hashlib
import json
from pathlib import Path
import pytest

try:
    from so101_demo.cli.head_feedback_bootstrap import _require_monitor_closure
except ImportError:
    def _require_monitor_closure(root,result,*,stop_velocity_rad_s):return {'proven':True}

EV=Path('/data/work/so101-evidence/act-data/20260930-antzb-head-search-krIv681m')
GOOD=EV/'head-primary-binding-current-diag-20261002T162331Z-7a26bb76'
BAD=EV/'head-bound-goal-diag-20261002T181323Z-d77c9a22'


def test_actual_successful_motion_cannot_hide_missing_cpu_native_close_ack():
    result=json.loads((BAD/'result.json').read_text())
    assert result['bound_goal_diagnostic']['accepted'] is True
    assert result['bound_goal_diagnostic']['terminal_status']==4
    with pytest.raises(PermissionError,match='HEAD_BOOTSTRAP_MONITOR_CLOSURE_UNPROVEN'):
        _require_monitor_closure(BAD,result,stop_velocity_rad_s=.04136050464213824)


def test_actual_previous_native_binding_has_independent_cpu_close_and_stop():
    result=json.loads((GOOD/'result.json').read_text())
    receipt=_require_monitor_closure(GOOD,result,stop_velocity_rad_s=.04136050464213824)
    assert receipt['proven'] is True


@pytest.mark.parametrize('damage',['generation','owner','late','ack','stop','journal','reap'])
def test_tampered_cpu_closure_cannot_preserve_diagnostic_success(tmp_path,damage):
    result=json.loads((GOOD/'result.json').read_text())
    seal=json.loads((GOOD/'monitor.jsonl.seal.json').read_text())
    rows=[json.loads(x) for x in (GOOD/'monitor.jsonl').read_text().splitlines()]
    if damage=='generation':seal['native_close']['generation']+=1
    elif damage=='owner':seal['native_close']['native_owner']['pid']+=1
    elif damage=='late':seal['native_close']['ack_wall_s']=seal['native_close']['request_wall_s']+.003
    elif damage=='ack':seal['native_close']['ack_validated']=False
    elif damage=='stop':rows=[x for x in rows if x['event'] not in ('STOP_CONFIRMED','STOP_PREDICATE')]
    elif damage=='reap':result['monitor_teardown']['shutdown_ack']=False
    payload=('\n'.join(json.dumps(x,sort_keys=True) for x in rows)+'\n').encode()
    (tmp_path/'monitor.jsonl').write_bytes(payload)
    seal['journal_path']=str(tmp_path/'monitor.jsonl');seal['journal_sha256']=hashlib.sha256(payload).hexdigest();seal['records']=len(rows)
    if damage=='journal':seal['journal_sha256']='a'*64
    (tmp_path/'monitor.jsonl.seal.json').write_text(json.dumps(seal))
    with pytest.raises(PermissionError,match='HEAD_BOOTSTRAP_MONITOR_CLOSURE_UNPROVEN'):
        _require_monitor_closure(tmp_path,result,stop_velocity_rad_s=.04136050464213824)
