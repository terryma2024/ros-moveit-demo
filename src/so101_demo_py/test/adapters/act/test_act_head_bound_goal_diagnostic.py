"""Controlled diagnostic settlement tests; application proof is a separate live run."""
from types import SimpleNamespace
import pytest
from so101_demo.act.head_feedback import bound_goal_settlement as _bound_goal_settlement

def sample(sequence=2, source_ns=200, wall_s=None, q=.1, velocity=0.):
    return dict(sequence=sequence,source_ns=source_ns,wall_s=1.2+sequence*.01 if wall_s is None else wall_s,
                positions=(q,),velocities=(velocity,),valid=True)

def goal(accepted=True,status=4,code=0):
    return dict(accepted=accepted,result=SimpleNamespace(status=status,
                result=SimpleNamespace(error_code=code)))

def check(records, state=None):
    return _bound_goal_settlement(records,goal() if state is None else state,
            target_rad=.1,position_tolerance_rad=.05,velocity_tolerance_rad_s=.04,
            source_floor_ns=100,dispatch_wall_s=1.,terminal_wall_s=1.1)

def test_settlement_requires_three_distinct_post_terminal_originals():
    assert check([sample()]*3) is None
    assert check([sample(2,200),sample(3,300)]) is None
    proof=check([sample(2,200),sample(3,300),sample(4,400)])
    assert [row['sequence'] for row in proof]==[2,3,4]

@pytest.mark.parametrize('records',[
    [sample(2,90),sample(3,100),sample(4,110)],
    [sample(2,200,1.05),sample(3,300),sample(4,400)],
    [sample(2,200),sample(3,300,q=.2),sample(4,400)],
    [sample(2,200),sample(3,300,velocity=.05),sample(4,400)],
    [sample(2,200),sample(3,300),sample(4,200)],
])
def test_carry_in_unsettled_and_regression_cannot_prove_settlement(records):
    assert check(records) is None

@pytest.mark.parametrize('state',[goal(None),goal(False),goal(status=5),goal(code=-1)])
def test_unknown_rejected_aborted_or_error_results_never_prove_settlement(state):
    assert check([sample(2,200),sample(3,300),sample(4,400)],state) is None

def test_proof_owns_original_copies():
    records=[sample(2,200),sample(3,300),sample(4,400)]
    proof=check(records);records[0]['source_ns']=900
    assert proof[0]['source_ns']==200

@pytest.mark.parametrize('field,value',[('positions',(float('nan'),)),('velocities',(float('nan'),)),('wall_s',float('nan'))])
def test_nonfinite_original_never_proves_settlement(field,value):
    rows=[sample(2,200),sample(3,300),sample(4,400)]
    rows[1][field]=value
    assert check(rows) is None





















def test_measurement_digest_bounds_auxiliary_memory_and_preserves_original_hash():
    import hashlib
    import json
    import tracemalloc
    from so101_demo.adapters.act import head_image_artifacts as entry
    document={'epoch':'original','window':{'joint_messages':[
        {'wall_s':10000.+i*.01,'source_ns':1000000000+i*10000000,
         'positions':[0.],'velocities':[0.],'name':'physical-joint-feedback'}
        for i in range(10000)]}}
    expected=hashlib.sha256(json.dumps(document,sort_keys=True,separators=(',',':'),
        allow_nan=False).encode('ascii')).hexdigest()
    tracemalloc.start()
    try:
        actual=entry.digest(document)
        peak=tracemalloc.get_traced_memory()[1]
    finally:tracemalloc.stop()
    assert actual==expected
    assert peak<512*1024, 'measurement digest allocated a complete encoded audit copy'


@pytest.mark.parametrize('value',[
    {'z':[True,None,False],'a':{'é':'💡\\\"\n'}},
    {'negative_zero':-0.,'large':2**63,'tiny':1e-99},
    {'empty':[],'tuple':(0,.002,.010),'object':{}},
])
def test_incremental_entry_digest_is_exact_canonical_body_hash(value):
    from so101_demo.act.head_evidence_identity import digest as canonical_digest
    from so101_demo.adapters.act.head_image_artifacts import digest as entry_digest
    assert entry_digest(value)==canonical_digest(value)


@pytest.mark.parametrize('value',[{'nan':float('nan')},{'infinity':[float('inf')]}])
def test_incremental_entry_digest_refuses_nonfinite_audit_body(value):
    from so101_demo.adapters.act.head_image_artifacts import digest
    with pytest.raises(ValueError):digest(value)


def test_cooperative_publication_keeps_exact_original_file_bytes_and_reference(tmp_path):
    import hashlib
    import json
    from so101_demo.adapters.act.head_image_artifacts import write_json as _write
    record={'scope':'original','rows':[{'ordinal':i,'source_ns':i*2000000,
        'values':[.002,.010,-0.],'label':'é'} for i in range(500)]}
    expected=(json.dumps(record,sort_keys=True,allow_nan=False)+'\n').encode('ascii')
    path=tmp_path/'measurement.json'
    reference=_write(path,record)
    assert path.read_bytes()==expected
    assert reference==dict(path=str(path.resolve()),sha256=hashlib.sha256(expected).hexdigest())
    with pytest.raises(FileExistsError):_write(path,record)
