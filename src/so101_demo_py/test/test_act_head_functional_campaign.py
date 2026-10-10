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


def test_prepared_attempt_workspace_follows_declared_root_not_a_host_constant(tmp_path):
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
    assert 'SO101_ACT_CONTROLLER_RESERVATION_DIR' not in environment
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

def _window(first=1_000_000_000):
    return dict(n=51, first_sim_ns=first, last_sim_ns=first + 100_000_000, max_abs_feedback_velocity=0.0005,
                max_abs_reference_velocity=0.0, reference_position=0.2, max_age_ns=1_000_000, completed_mono_ns=5)


def startup_protocol_facts():
    activation = 'act-1-4242'
    return dict(stop_confirmed=True,owned_children_exited=True,children=[dict(pid=999999999,rc=0)],
        postflight=dict(owner_absent=True,graph_empty=True,graph_rc=0),
        startup_protocol=dict(seal_verified=True,
            CONTROLLER_READBACK=[dict(controller='neck_controller',
                controller_type='so101_mujoco_support/HeadNeckTrajectoryController',state='active',
                activation_id=activation,parameters={'head_deadman_timeout_s':0.2})],
            DEADMAN_ARMED=[dict(socket_path='/tmp/dm/neck-act-1-4242.sock',peer_pid=4242,
                activation_id=activation,head_deadman_period_s=0.02,head_deadman_timeout_s=0.2)],
            GRAPH_PROOF=[dict(own_gids={'/neck_controller/follow_joint_trajectory':[]},allowed_node_names=['a'],
                foreign_allowed=[],service_clients={},watched={})],
            STARTUP_STOP_WINDOW=[_window()],
            STOCK_STOP_PROOF=[dict(terminal={'g':4},raw_stop_samples=[1,2,3],raw_stop_confirmed_sim_ns=5,
                window=_window(2_000_000_000),deadman_closed_planned=True)],
            DEADMAN_CLOSED_PLANNED=[dict(activation_id=activation)],
            DEADMAN_CLOSED_FAULT=[],
            CANCEL_STOP=[dict(raw_stop_confirmed=True,cancel_error=None,result_error=None)]))


def test_strict_startup_allows_complete_protocol_and_interruption_only():
    from so101_demo.cli.head_search_functional_campaign import may_continue
    facts=startup_protocol_facts();facts['original_terminal']='INTERRUPTED'
    assert may_continue(facts,require_startup_protocol=True)


@pytest.mark.parametrize('damage',[
    'readback_missing','readback_duplicate','readback_type','readback_inactive','armed_missing','armed_activation',
    'armed_pid','armed_period','armed_timeout','graph_missing','graph_shape','window_missing','window_short',
    'window_fast','window_reference_fast','proof_missing','proof_not_planned','proof_window_short',
    'proof_terminal','proof_samples','close_missing','close_activation','stop_missing','stop_error',
    'graph','owner','child','seal','missing','protocol_type'])
def test_strict_startup_stops_at_first_refusal_or_missing_evidence(damage):
    from so101_demo.cli.head_search_functional_campaign import may_continue
    facts=startup_protocol_facts();p=facts['startup_protocol']
    if damage=='readback_missing':p['CONTROLLER_READBACK']=[]
    elif damage=='readback_duplicate':p['CONTROLLER_READBACK']*=2
    elif damage=='readback_type':p['CONTROLLER_READBACK'][0]['controller_type']='joint_trajectory_controller/JointTrajectoryController'
    elif damage=='readback_inactive':p['CONTROLLER_READBACK'][0]['state']='inactive'
    elif damage=='armed_missing':p['DEADMAN_ARMED']=[]
    elif damage=='armed_activation':p['DEADMAN_ARMED'][0]['activation_id']='other'
    elif damage=='armed_pid':p['DEADMAN_ARMED'][0]['peer_pid']=0
    elif damage=='armed_period':p['DEADMAN_ARMED'][0]['head_deadman_period_s']=0.05
    elif damage=='armed_timeout':p['DEADMAN_ARMED'][0]['head_deadman_timeout_s']=1.0
    elif damage=='graph_missing':p['GRAPH_PROOF']=[]
    elif damage=='graph_shape':p['GRAPH_PROOF'][0]['own_gids']=None
    elif damage=='window_missing':p['STARTUP_STOP_WINDOW']=[]
    elif damage=='window_short':p['STARTUP_STOP_WINDOW'][0]['n']=50
    elif damage=='window_fast':p['STARTUP_STOP_WINDOW'][0]['max_abs_feedback_velocity']=0.0021
    elif damage=='window_reference_fast':p['STARTUP_STOP_WINDOW'][0]['max_abs_reference_velocity']=0.01
    elif damage=='proof_missing':p['STOCK_STOP_PROOF']=[]
    elif damage=='proof_not_planned':p['STOCK_STOP_PROOF'][0]['deadman_closed_planned']=False
    elif damage=='proof_window_short':p['STOCK_STOP_PROOF'][0]['window']['n']=3
    elif damage=='proof_terminal':p['STOCK_STOP_PROOF'][0]['terminal']={'g':2}
    elif damage=='proof_samples':p['STOCK_STOP_PROOF'][0]['raw_stop_samples']=[1]
    elif damage=='close_missing':p['DEADMAN_CLOSED_PLANNED']=[]
    elif damage=='close_activation':p['DEADMAN_CLOSED_PLANNED'][0]['activation_id']='other'
    elif damage=='stop_missing':p['CANCEL_STOP']=[]
    elif damage=='stop_error':p['CANCEL_STOP'][0]['cancel_error']='TimeoutError'
    elif damage=='graph':facts['postflight']['graph_empty']=False
    elif damage=='owner':facts['postflight']['owner_absent']=False
    elif damage=='child':facts['children'][0]['rc']=1
    elif damage=='seal':p['seal_verified']=False
    elif damage=='missing':facts.pop('startup_protocol')
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

def test_strict_run_case_stops_before_second_attempt_after_a_refused_deadman_arm(tmp_path,monkeypatch):
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
    facts['startup_protocol']['DEADMAN_ARMED']=[]
    monkeypatch.setattr(campaign,'prepare_attempt',prepare)
    monkeypatch.setattr(campaign,'launch_installed',launch)
    monkeypatch.setattr(campaign,'extract_attempt',lambda *args: facts)
    output=tmp_path/'case';output.mkdir()
    result=campaign.run_case(_case(9),{},output=output,prefix='strict-test',python='python',
        executable='entry',domain=229,generation_base=17,minimum_free_bytes=0,require_startup_protocol=True)
    assert len(result)==len(calls)==1
    assert not (output/'attempt-2').exists()
