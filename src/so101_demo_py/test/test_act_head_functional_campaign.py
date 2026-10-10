"""Campaign evidence must refer to the terminal input and owned OS lifecycle."""
import json

import pytest


def test_terminal_image_selection_uses_stamp_not_last_file():
    from so101_demo.cli.head_search_functional_campaign import select_terminal_image
    rows = [dict(kind='IMAGE_PAYLOAD', record=dict(source_ns=100, payload_sha256='a'*64)),
            dict(kind='IMAGE_PAYLOAD', record=dict(source_ns=200, payload_sha256='b'*64))]
    assert select_terminal_image(rows, dict(timestamp=100e-9)) == rows[0]
    with pytest.raises(ValueError):
        select_terminal_image(rows, dict(timestamp=300e-9))


@pytest.mark.parametrize('damaged', ['stop', 'exit', 'missing'])
def test_unsafe_or_unknown_retirement_blocks_next_attempt(damaged):
    from so101_demo.cli.head_search_functional_campaign import may_continue
    facts = dict(stop_confirmed=True, owned_children_exited=True)
    assert may_continue(facts)
    if damaged == 'missing': facts.pop('stop_confirmed')
    else: facts['stop_confirmed' if damaged == 'stop' else 'owned_children_exited'] = False
    assert not may_continue(facts)


def test_serial_result_retains_failure_without_substituting_debug_attempt():
    from so101_demo.cli.head_search_functional_campaign import summarize
    from test_act_head_functional_acceptance import locked_facts
    from test_act_head_search_campaign_scene import _case
    facts = locked_facts()
    facts.update(original_terminal='FAULT', actual_os_return_code=1, business_rc=1)
    rows = summarize([_case(0), _case(1)], {'hs40-900000': [facts]})
    assert [r['status'] for r in rows] == ['FAIL', 'NOT_RUN']
    assert rows[0]['attempts'][0]['original_terminal'] == 'FAULT'


def test_postflight_requires_actual_os_end_before_graph_check(tmp_path):
    from so101_demo.cli.head_search_functional_campaign import postflight
    with pytest.raises(ValueError, match='ACTUAL_OS_END'):
        postflight(dict(owner=dict(pid=999999999)), {}, tmp_path)


def test_prepared_attempt_passes_real_closed_input_parser(tmp_path):
    import uuid
    from pathlib import Path
    from so101_demo.cli.head_search_functional_campaign import prepare_attempt
    from so101_demo.act.head_execution_inputs import HeadExecutionInputs
    from test_act_head_search_campaign_scene import _baseline, _case
    baseline = _baseline(tmp_path)
    baseline['ros']['environment']['SO101_ACT_RESERVATION_ROOT'] = str(tmp_path/'reservations')
    baseline.update(fault_stop_probes=[],
        stop_declaration=dict(trigger='OPERATOR_STOP', teardown_timeout_s=1.),
        seal_expectation=dict(completion=True, artifacts=['seal.json']),
        log_capture=dict(stdout='stdout.log', stderr='stderr.log'))
    token = 'prepare-'+uuid.uuid4().hex[:12]
    identity = dict(run_id=token, session_id=token, epoch=token+'-epoch', generation=123)
    path = prepare_attempt(_case(0), baseline, tmp_path/'prepared', identity=identity,
                           domain=224)
    inputs = HeadExecutionInputs.parse(path)
    assert Path(inputs.document['snapshot_root']).is_dir()
    assert inputs.run == identity and inputs.save_all_rgb_frames is False
    assert inputs.document['campaign_truth_enabled'] is False


def test_prepared_attempt_reservation_scope_follows_declared_root_not_a_host_constant(tmp_path):
    import hashlib
    from pathlib import Path
    from so101_demo.cli.head_search_functional_campaign import prepare_attempt
    from test_act_head_search_campaign_scene import _baseline, _case
    baseline = _baseline(tmp_path)
    root = tmp_path/'reservation-root'
    baseline['ros']['environment']['SO101_ACT_RESERVATION_ROOT'] = str(root)
    baseline.update(fault_stop_probes=[],
        stop_declaration=dict(trigger='OPERATOR_STOP', teardown_timeout_s=1.),
        seal_expectation=dict(completion=True, artifacts=['seal.json']),
        log_capture=dict(stdout='stdout.log', stderr='stderr.log'))
    token = 'scope-root-1'
    identity = dict(run_id=token, session_id=token, epoch=token+'-epoch', generation=124)
    path = prepare_attempt(_case(0), baseline, tmp_path/'prepared', identity=identity, domain=224)
    environment = json.loads(Path(path).read_text())['ros']['environment']
    assert environment['SO101_ACT_RESERVATION_ROOT'] == str(root)
    assert environment['SO101_ACT_CONTROLLER_RESERVATION_DIR'] == str(
        root/'ipc'/hashlib.sha256(token.encode()).hexdigest()[:16])
    assert Path(environment['ROS_WORKSPACE']) == root/token
    assert 'head-file-protocol-1003' not in json.dumps(environment)


def test_extractor_reads_sealed_detector_records_and_actual_rgb_payload(tmp_path,monkeypatch):
    import hashlib,json
    from PIL import Image
    import so101_demo.cli.head_search_functional_campaign as campaign
    from head_run_audit_support import corpus,reseal,RUN
    from test_act_head_search_campaign_scene import _baseline,_case
    from so101_demo.act.head_search_campaign_scene import prepare_case_fixture
    baseline=_baseline(tmp_path)
    baseline['run']=dict(RUN)
    prepared=prepare_case_fixture(_case(0),baseline,tmp_path/'fixture',paired_truth_enabled=False)
    baseline['refs'].update(prepared['refs'])
    run,_,_,_=corpus(tmp_path,[
        # The actual exposure emit(kind, record=saved) goes through a **record
        # forwarding sink, so the writer envelope retains this inner record.
        ('LIVE_STOPPED_OBSERVATION_FINISHED',dict(record=dict(source_ns=100,inference_performed=True))),
        ('LIVE_STOPPED_OBSERVATION_FINISHED',dict(record=dict(source_ns=200,inference_performed=False)))])
    raw=bytes([10,20,30,40,50,60]);payload=run/'artifacts/frame.rgb'
    payload.parent.mkdir();payload.write_bytes(raw)
    rows=[json.loads(line) for line in (run/'events.jsonl').read_text().splitlines()]
    image=dict(rows[0],kind='IMAGE_PAYLOAD',sequence=3,
        record=dict(source_ns=100,width=2,height=1,step=6,encoding='rgb8',
                    payload_sha256=hashlib.sha256(raw).hexdigest()),
        artifact_refs=[dict(path='artifacts/frame.rgb',size=len(raw),sha256=hashlib.sha256(raw).hexdigest())])
    (run/'events.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in [*rows,image]))
    reseal(run)
    baseline['run_root']=str(run)
    inputs=tmp_path/'extraction-inputs.json';inputs.write_text(json.dumps(baseline))
    # This unit exercises sealed extraction, not live graph retirement. Keep
    # that unproven boundary false instead of fabricating a safe runtime.
    monkeypatch.setattr(campaign,'postflight',lambda *args:dict(graph_empty=False,owner_absent=False))
    output=tmp_path/'extracted';output.mkdir()
    facts=campaign.extract_attempt(inputs,dict(actual_os_return_code=1),output)
    assert facts['image_count']==facts['inference_count']==1
    assert facts['save_mode_verified'] is True
    assert facts['first_detection_image']['source_ns']==100
    assert Image.open(output/'first-detection.png').tobytes()==raw
    assert facts['owned_children_exited'] is False
    payload.write_bytes(b'altered')
    with pytest.raises(ValueError,match='SEAL_MISMATCH'):
        campaign.extract_attempt(inputs,dict(actual_os_return_code=1),output)

def startup_protocol_facts():
    from copy import deepcopy
    from so101_demo.adapters.act.head_control_protocol import parse_proof_record
    from test_act_head_reservation_authority import startup_proof
    scope=dict(role=3,generation=5,incarnation='inc',boot='boot')
    owner=dict(uid=1000,pid=55,start_ticks=99)
    proof=parse_proof_record(startup_proof())
    bootstrap=dict(scope,status='AVAILABLE',ack_validated=True,stored_generation=0,native_owner=deepcopy(owner))
    ready=dict(scope,status='READY',native_status=0,gate_reason=0,stored_generation=0,native_owner=deepcopy(owner),proof=proof)
    arm=dict(status='ACK',native_status=0,phase='NONE',gate_reason=0,role=3,generation=5,native_owner=deepcopy(owner),proof=deepcopy(proof))
    arm['proof']['evaluation_id']+=1
    close=dict(ack=True,error=None,receipt=dict(scope,status='ARMED_CLOSED',stored_generation=5,ack_validated=True,native_owner=deepcopy(owner)))
    return dict(stop_confirmed=True,owned_children_exited=True,children=[dict(pid=999999999,rc=0)],
        postflight=dict(owner_absent=True,graph_empty=True,graph_rc=0),
        startup_protocol=dict(seal_verified=True,BOOTSTRAP_IDENTITY=[bootstrap],PREARM_STATUS=[ready],
            ARM_RESULT=[arm],NATIVE_CLOSE=[close],CANCEL_STOP=[dict(raw_stop_confirmed=True,error=None)]))


def test_strict_startup_allows_complete_ack_and_interruption_only():
    from so101_demo.cli.head_search_functional_campaign import may_continue
    facts=startup_protocol_facts();facts['original_terminal']='INTERRUPTED'
    assert may_continue(facts,require_startup_protocol=True)


@pytest.mark.parametrize('damage',[
    'arm_reject','arm_missing','arm_duplicate','arm_id','arm_owner','arm_wrapper8',
    'ready_missing','ready_wrapper8','ready_scope','ready_duplicate',
    'close_missing','close_unarmed','close_scope','close_false_ack','close_stored',
    'bootstrap_missing','bootstrap_duplicate','bootstrap_scope','bootstrap_owner',
    'stop_missing','stop_error','graph','owner','child','seal','missing','proof_range','protocol_type'])
def test_strict_startup_stops_at_first_refusal_or_missing_evidence(damage):
    from so101_demo.cli.head_search_functional_campaign import may_continue
    facts=startup_protocol_facts();p=facts['startup_protocol']
    if damage=='arm_reject':p['ARM_RESULT'][0].update(status='REJECT',phase='STOP_BEFORE')
    elif damage=='arm_missing':p['ARM_RESULT']=[]
    elif damage=='arm_duplicate':p['ARM_RESULT']*=2
    elif damage=='arm_id':p['ARM_RESULT'][0]['proof']['evaluation_id']=47
    elif damage=='arm_owner':p['ARM_RESULT'][0]['native_owner']['pid']=66
    elif damage=='arm_wrapper8':p['ARM_RESULT'][0]['proof']['wrapper_reason']=8
    elif damage=='ready_missing':p['PREARM_STATUS']=[]
    elif damage=='ready_wrapper8':p['PREARM_STATUS'][0]['proof']['wrapper_reason']=8
    elif damage=='ready_scope':p['PREARM_STATUS'][0]['incarnation']='other'
    elif damage=='ready_duplicate':p['PREARM_STATUS']*=2
    elif damage=='close_missing':p['NATIVE_CLOSE']=[]
    elif damage=='close_unarmed':p['NATIVE_CLOSE'][0]['receipt'].update(status='NOT_ARMED_CLOSED',stored_generation=0)
    elif damage=='close_scope':p['NATIVE_CLOSE'][0]['receipt']['boot']='other'
    elif damage=='close_false_ack':p['NATIVE_CLOSE'][0]['receipt']['ack_validated']=False
    elif damage=='close_stored':p['NATIVE_CLOSE'][0]['receipt']['stored_generation']=0
    elif damage=='bootstrap_missing':p['BOOTSTRAP_IDENTITY']=[]
    elif damage=='bootstrap_duplicate':p['BOOTSTRAP_IDENTITY']*=2
    elif damage=='bootstrap_scope':p['BOOTSTRAP_IDENTITY'][0]['role']=1
    elif damage=='bootstrap_owner':p['BOOTSTRAP_IDENTITY'][0]['native_owner']=None
    elif damage=='stop_missing':p['CANCEL_STOP']=[]
    elif damage=='stop_error':p['CANCEL_STOP'][0]['error']='TimeoutError'
    elif damage=='graph':facts['postflight']['graph_empty']=False
    elif damage=='owner':facts['postflight']['owner_absent']=False
    elif damage=='child':facts['children'][0]['rc']=1
    elif damage=='seal':p['seal_verified']=False
    elif damage=='missing':facts.pop('startup_protocol')
    elif damage=='proof_range':p['PREARM_STATUS'][0]['proof']['evaluation_id']=2**65
    elif damage=='protocol_type':facts['startup_protocol']=[]
    assert not may_continue(facts,require_startup_protocol=True)


def test_strict_startup_records_come_only_from_seal_verified_events(tmp_path,monkeypatch):
    # Existing extraction test also checks payload corruption. The strict flag
    # must reject missing event coverage before interpreting startup messages.
    import json
    from head_run_audit_support import corpus
    import so101_demo.cli.head_search_functional_campaign as campaign
    from test_act_head_search_campaign_scene import _baseline
    run,_,_,_=corpus(tmp_path,[])
    seal=json.loads((run/'seal.json').read_text())
    seal['files']=[row for row in seal['files'] if row['path']!='events.jsonl']
    (run/'seal.json').write_text(json.dumps(seal))
    baseline=_baseline(tmp_path);baseline['run_root']=str(run)
    path=tmp_path/'inputs.json';path.write_text(json.dumps(baseline))
    out=tmp_path/'extract';out.mkdir()
    with pytest.raises(ValueError,match='EVENTS_UNSEALED'):
        campaign.extract_attempt(path,dict(actual_os_return_code=1),out)

def test_strict_run_case_stops_before_second_attempt_after_arm_reject(tmp_path,monkeypatch):
    import so101_demo.cli.head_search_functional_campaign as campaign
    from test_act_head_search_campaign_scene import _case
    calls=[]
    def prepare(case,baseline,output,**kwargs):
        output.mkdir(parents=True)
        path=output/'inputs.json';path.write_text('{}')
        return path
    def launch(*args,**kwargs):
        calls.append(kwargs)
        return dict(actual_os_return_code=1)
    facts=startup_protocol_facts()
    facts.update(original_terminal='FAULT')
    facts['startup_protocol']['ARM_RESULT'][0].update(status='REJECT',phase='STOP_BEFORE')
    monkeypatch.setattr(campaign,'prepare_attempt',prepare)
    monkeypatch.setattr(campaign,'launch_installed',launch)
    monkeypatch.setattr(campaign,'extract_attempt',lambda *args: facts)
    output=tmp_path/'case';output.mkdir()
    result=campaign.run_case(_case(9),{},output=output,prefix='strict-test',python='python',
        executable='entry',domain=229,generation_base=17,minimum_free_bytes=0,require_startup_protocol=True)
    assert len(result)==len(calls)==1
    assert not (output/'attempt-2').exists()
