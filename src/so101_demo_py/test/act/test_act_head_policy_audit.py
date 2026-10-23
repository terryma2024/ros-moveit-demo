"""Read-only sealed measurement audits have no motion or approval authority."""
import copy
import hashlib
import json

import pytest

from test_act_head_feedback_measurement import window
from so101_demo.act.head_feedback_measurement import evaluate_feedback_window


@pytest.fixture
def audit_input(tmp_path):
    dependencies={name:dict(path=str(tmp_path/(name+'.reference')),sha256=letter*64)
        for name,letter in [('weights','a'),('geometry','b'),('candidate','c'),('runtime_manifest','d')]}
    context=dict(epoch='attempt',generation=5,session_id='session',dependencies=dependencies)
    document=dict(copy.deepcopy(context),window=window())
    def seal(value):
        owned=copy.deepcopy(value)
        owned['sha256']=hashlib.sha256(json.dumps(owned,sort_keys=True,separators=(',',':'),
            allow_nan=False).encode('ascii')).hexdigest()
        payload=(json.dumps(owned,sort_keys=True,allow_nan=False)+'\n').encode('ascii')
        path=tmp_path/('measurement-'+hashlib.sha256(payload).hexdigest()+'.json')
        path.write_bytes(payload)
        return dict(path=str(path),sha256=hashlib.sha256(payload).hexdigest()),owned
    reference,sealed=seal(document)
    return context,document,reference,sealed,seal


def test_readonly_audit_keeps_the_exact_entire_original_formula_result(audit_input):
    from so101_demo.act.head_policy_audit import audit_measurement
    context,document,reference,sealed,_=audit_input
    result=audit_measurement(reference,context=context,stop_latency_s=.07)
    assert result['purpose']=='calibration' and result['motion_authority'] is False
    assert result['reference']==reference and result['context']==context
    assert result['body_sha256']==sealed['sha256']
    assert result['computed']==evaluate_feedback_window(document['window'],stop_latency_s=.07)
    assert len(json.dumps(result).encode('ascii'))<16384
    assert 'window' not in result and 'approval' not in result


@pytest.mark.parametrize('damage',['file_sha','inner_sha','epoch','generation','session_id',
    'dependencies','extra','missing','duration','invalid_original','ceiling'])
def test_readonly_audit_refuses_tampered_binding_or_incomplete_originals(audit_input,damage):
    from so101_demo.act.head_policy_audit import audit_measurement
    context,document,reference,sealed,seal=audit_input
    if damage=='file_sha':reference=dict(reference,sha256='f'*64)
    elif damage=='inner_sha':
        path=reference['path']
        sealed['sha256']='e'*64
        payload=json.dumps(sealed).encode('ascii')
        from pathlib import Path
        Path(path).write_bytes(payload)
        reference=dict(path=path,sha256=hashlib.sha256(payload).hexdigest())
    else:
        if damage=='epoch':document['epoch']='foreign'
        elif damage=='generation':document['generation']=6
        elif damage=='session_id':document['session_id']='foreign'
        elif damage=='dependencies':document['dependencies']['geometry']['sha256']='f'*64
        elif damage=='extra':document['approval']=True
        elif damage=='missing':document.pop('session_id')
        elif damage=='duration':document['window']['end_wall_s']-=.001
        elif damage=='invalid_original':document['window']['clock_messages'][-1]['valid']=False
        elif damage=='ceiling':document['window']['clock_resolution_s']=.06
        reference,_=seal(document)
    with pytest.raises((PermissionError,ValueError)):
        audit_measurement(reference,context=context,stop_latency_s=.07)


@pytest.mark.parametrize('damage',['relative','noncanonical','symlink'])
def test_readonly_audit_keeps_original_regular_nofollow_path_checks(audit_input,tmp_path,damage):
    from pathlib import Path
    from so101_demo.act.head_policy_audit import audit_measurement
    context,_,reference,_,_=audit_input
    if damage=='relative':reference=dict(reference,path=Path(reference['path']).name)
    elif damage=='noncanonical':reference=dict(reference,path=str(tmp_path/'missing')+'/../'+Path(reference['path']).name)
    else:
        link=tmp_path/'linked-measurement.json';link.symlink_to(reference['path'])
        reference=dict(reference,path=str(link))
    with pytest.raises((OSError,PermissionError,ValueError)):
        audit_measurement(reference,context=context,stop_latency_s=.07)
