"""Catch identity splices, illegal consumption, false locks and false Stop proof."""
import importlib
import json

import pytest

from head_run_audit_support import RUN, make_reader, reseal, write_json


def audit(reader):
    try:
        module = importlib.import_module('so101_demo.act.head_run_audit')
    except ModuleNotFoundError as error:
        pytest.fail(f'Offline rules feature is absent: {error}')
    reader.load()
    return module.audit_run(reader)


def verdict(result, rule):
    return result['coverage']['rules'][rule]['verdict']


def observation_records(*, outcome='VALID', center=320, track='cup', sequence=1, epoch=1,
                        lock=1, frame=100000000, expired=False):
    request = dict(epoch=RUN['epoch'], session_id=RUN['session_id'], generation=7,
        observation_sequence=sequence, motion_epoch=epoch, settled_source_floor_ns=50000000,
        settled_wall_s=.04, requested_wall_s=.05, search_deadline_ns=30000000000,
        policy_sha256='c' * 64, simulation_policy_sha256='c' * 64, schema_version=1)
    row = dict(**{k:request[k] for k in ('epoch','session_id','generation','motion_epoch')},
        observation_sequence=sequence, sequence=sequence, observation_request=request,
        source_ns=frame, info_source_ns=frame, tf_source_ns=frame, joint_source_ns=frame-1000000,
        image_received_wall_s=.1, info_received_wall_s=.1, cuda_started_wall_s=.11,
        completion_wall_s=.12, job_started_wall_s=.11, job_deadline_ns=1110000000,
        deadline_ns=250000000, original_info={'width':640,'height':480,'k':[400,0,320,0,400,240,0,0,1]},
        detections=[{'track_id':track,'class_id':0,'confidence':.9,
                     'xyxy':[center-10,230,center+10,250]}], observation_outcome=outcome)
    decision = dict(sequence=sequence, source_ns=frame, track_id=track, lock_count=lock,
        core_tick_wall_s=.3 if expired else .13,
        current_joint_decision={'sim_ns': frame+1000000},
        decision={'status':'TARGET_LOCKED' if lock==3 else 'CENTER_CUP', 'stop':False})
    return [('SEARCH_OBSERVATION_REQUESTED', {'request':request}),
            ('LIVE_STOPPED_OBSERVATION_HANDOFF', {'record':row}),
            ('SEARCH_EXPOSURE_DECISION', {'observation':decision})]


def test_unknown_profile_does_not_manufacture_semantic_pass(tmp_path):
    result = audit(make_reader(tmp_path, [('FAULT', {'reason':'intended'})]))
    assert result['integrity']['status'] == 'PASS'
    assert result['execution_checks']['status'] == 'UNKNOWN'
    assert result['stop']['status'] == 'UNKNOWN'
    assert 'status' not in {k:v for k,v in result.items() if k == 'status'}
    assert result['coverage']['capabilities']['wire_payload_equivalence'] == 'NOT_ASSESSED'


def test_cross_run_splice_is_contract_failure_with_integrity_pass(tmp_path, monkeypatch):
    reader = make_reader(tmp_path, [('FAULT', {'reason':'intended'})], monkeypatch)
    path = reader.run_root / 'events.jsonl'; event = json.loads(path.read_text())
    event['run'] = dict(RUN, generation=8)
    path.write_text(json.dumps(event)+'\n'); reseal(reader.run_root)
    result = audit(reader)
    assert result['integrity']['status'] == 'PASS'
    assert result['execution_checks']['status'] == 'FAIL'
    assert verdict(result, 'HFA-002') == 'VIOLATED'


def test_proven_failure_dominates_missing_evidence(tmp_path, monkeypatch):
    reader = make_reader(tmp_path, [('HEAD_ACTION_SDK_RETURNED', {'goal_uuid':'same'}),
        ('HEAD_ACTION_SDK_RETURNED', {'goal_uuid':'same'})], monkeypatch)
    result = audit(reader)
    assert result['execution_checks']['status'] == 'FAIL'
    assert verdict(result, 'HFA-003') == 'VIOLATED'


@pytest.mark.parametrize('bad', ['scope','shape','time','range'])
def test_typed_goal_structural_violations_are_checked_without_curve_reproof(tmp_path, monkeypatch, bad):
    points=[{'positions':[0.0],'velocities':[0.0],'accelerations':[0.0],
             'time_from_start':{'sec':0,'nanosec':100}},
            {'positions':[.1],'velocities':[0.0],'accelerations':[0.0],
             'time_from_start':{'sec':1,'nanosec':0}}]
    names=['neck_yaw_joint']
    if bad=='scope': names=['arm_joint']
    if bad=='shape': points[1]['positions']=[]
    if bad=='time': points[1]['time_from_start']={'sec':0,'nanosec':0}
    if bad=='range': points[1]['positions']=[10.0]
    record={'goal_uuid':'a','inventory_record':{'goal_uuid':'a','typed_goal':{
        'trajectory':{'joint_names':names,'points':points}}}}
    result=audit(make_reader(tmp_path,[('HEAD_PREPARED_DISPATCH_TRACE',record)],monkeypatch))
    assert verdict(result,'HFA-004')=='VIOLATED'
    assert result['coverage']['capabilities']['trajectory_safety_reproof']=='NOT_ASSESSED'


@pytest.mark.parametrize('bad', ['expired','outcome','epoch','frame'])
def test_invalid_result_cannot_update_lock_or_target(tmp_path, monkeypatch, bad):
    records=observation_records(expired=bad=='expired',outcome='EXPIRED' if bad=='outcome' else 'VALID')
    if bad=='epoch': records[1][1]['record']['motion_epoch']=9
    if bad=='frame': records[2][1]['observation']['source_ns']=900000000
    result=audit(make_reader(tmp_path,records,monkeypatch))
    assert verdict(result,'HFA-006')=='VIOLATED'
    assert result['execution_checks']['status']=='FAIL'


def test_ack_boolean_without_raw_quiet_joint_is_unknown(tmp_path, monkeypatch):
    records=[('STOP_REQUEST',{'origin':'success'}),('NATIVE_CLOSE',{'ack':True,'error':None,
        'requested_wall_s':.002}),('CANCEL_STOP',{'raw_stop_confirmed':True})]
    result=audit(make_reader(tmp_path,records,monkeypatch))
    assert result['stop']['status']=='UNKNOWN'
    assert verdict(result,'HFA-009')=='UNKNOWN'


def test_original_search_deadline_cannot_be_reset(tmp_path, monkeypatch):
    records=observation_records();second=observation_records(sequence=2)
    second[0][1]['request']['search_deadline_ns']=60000000000
    result=audit(make_reader(tmp_path,records+second,monkeypatch))
    assert verdict(result,'HFA-007')=='VIOLATED'


def test_observation_request_duplicate_is_violation(tmp_path, monkeypatch):
    records=observation_records();records.insert(1,records[0])
    assert verdict(audit(make_reader(tmp_path,records,monkeypatch)),'HFA-007')=='VIOLATED'


def test_three_lock_counts_without_centered_detections_are_rejected(tmp_path, monkeypatch):
    records=[]
    for n in range(1,4): records+=observation_records(sequence=n,lock=n,center=370,frame=n*100000000)
    result=audit(make_reader(tmp_path,records,monkeypatch))
    assert verdict(result,'HFA-008')=='VIOLATED'
    assert result['execution_checks']['status']=='FAIL'


def test_three_distinct_centered_frames_recompute_lock(tmp_path, monkeypatch):
    records=[]
    for n in range(1,4): records+=observation_records(sequence=n,lock=n,frame=n*100000000)
    result=audit(make_reader(tmp_path,records,monkeypatch))
    assert verdict(result,'HFA-008')=='HOLDS'


def test_repeated_frame_cannot_count_three_times(tmp_path, monkeypatch):
    records=[]
    for n in range(1,4): records+=observation_records(sequence=n,lock=n,frame=100000000)
    assert verdict(audit(make_reader(tmp_path,records,monkeypatch)),'HFA-008')=='VIOLATED'


def test_track_change_resets_committed_lock(tmp_path, monkeypatch):
    records=observation_records(lock=1)+observation_records(sequence=2,lock=2,track='other',frame=200000000)
    assert verdict(audit(make_reader(tmp_path,records,monkeypatch)),'HFA-008')=='VIOLATED'


def test_legal_expired_discard_then_retry_does_not_add_or_reset_lock(tmp_path, monkeypatch):
    records=observation_records(lock=1)
    discard=observation_records(sequence=2,outcome='EXPIRED'); discard.pop()
    discard.append(('SEARCH_OBSERVATION_DISCARDED',{'sequence':2,'observation_sequence':2,'outcome':'EXPIRED'}))
    records+=discard+observation_records(sequence=3,lock=2,frame=200000000)
    result=audit(make_reader(tmp_path,records,monkeypatch))
    assert verdict(result,'HFA-006')=='HOLDS'
    assert verdict(result,'HFA-007')=='HOLDS'
    assert verdict(result,'HFA-008')=='HOLDS'


def test_expected_fault_search_failure_is_not_integrity_failure(tmp_path, monkeypatch):
    result=audit(make_reader(tmp_path,[('FAULT',{'reason':'intended'})],monkeypatch))
    assert result['integrity']['status']=='PASS'
    assert result['search']['outcome']=='FAILED'
    assert verdict(result,'HFA-011')=='HOLDS'


def test_forced_kill_is_exit_failure_despite_missing_postflight(tmp_path, monkeypatch):
    result=audit(make_reader(tmp_path,[('EXECUTION_STACK_RETIREMENT',{'forced_kill':[123],
        'errors':[],'closed':True,'retired':True,'children':[]})],monkeypatch))
    assert result['exit_cleanup']['status']=='FAIL'


@pytest.mark.parametrize('invalid_sample',[False,True])
def test_stop_quiet_samples_can_precede_independent_terminal_reply(tmp_path, monkeypatch, invalid_sample):
    records=[('FAULT',{'occurred_ns':1000000,'reason':'intended'}),
        ('DEADMAN_ARMED',{'activation_id':'x'})]
    for n in range(3,6):
        records.append(('JOINT',{'source_ns':n*1000000,'sequence':n,'wall_s':n*.001,
            'raw_names':['neck_yaw_joint'],'raw_positions':[0.0],'raw_velocities':[0.0],
            'valid':True}))
    if invalid_sample:
        records.append(('JOINT',{'source_ns':5500000,'sequence':6,'wall_s':.0055,
            'raw_names':['neck_yaw_joint'],'raw_positions':[0.0],'raw_velocities':[], 'valid':True}))
    records+=[('HEAD_ACTION_SDK_RETURNED',{'goal_uuid':'a'}),
        ('HEAD_ACTION_SERVICE_REQUEST',{'goal_uuid':'a','original':{'goal_info':{'goal_id':{'uuid':[0]*15+[1]}}}}),
        ('HEAD_ACTION_CANCEL',{'goal_uuid':'a','original':{'return_code':0,'goals_canceling':[{'goal_id':{'uuid':[0]*15+[1]}}]}}),
        ('HEAD_ACTION_GET_RESULT',{'goal_uuid':'a','callback_wall_ns':6000000,
            'callback_sim_ns':6000000,'original':{'status':6,'result':{'error_code':-1}}}),
        ('CANCEL_STOP',{'raw_stop_confirmed':True,'cancel_error':None,'result_error':None,
                        'raw_stop_confirmed_sim_ns':5000000}),
        ('STOCK_STOP_PROOF',{'terminal':{'a':4},'raw_stop_samples':[3000000,4000000,5000000],
            'raw_stop_confirmed_sim_ns':5000000,
            'window':{'first_sim_ns':9000000,'last_sim_ns':9100000,'n':51},'deadman_closed_planned':False}),
        ('DEADMAN_CLOSED_FAULT',{'reason':'intended','ack':True,'error':None,'requested_wall_s':.0015}),
        ('EXECUTION_LOOP_RETIREMENT',{'outcomes':{'runtime':{'deadman_close':{
            'ack':True,'error':None,'planned':False}}}})]
    result=audit(make_reader(tmp_path,records,monkeypatch))
    assert result['stop']['status']==('UNKNOWN' if invalid_sample else 'PASS')


def test_f015_postflight_domain_field_is_versioned_scope_not_conflict(tmp_path, monkeypatch):
    reader=make_reader(tmp_path,[('FAULT',{'reason':'intended'})],monkeypatch)
    post=write_json(tmp_path/'inputs/postflight/result.json',{'phase':'postflight','domain':200,
        'partition':'session','commands':{'ps':{'rc':0},'graph':{'rc':0}},'ready':True})
    (tmp_path/'inputs/postflight/ps.stdout').write_text('999 1 unrelated_service\n')
    (tmp_path/'inputs/postflight/graph.stdout').write_text('/unrelated\n')
    receipt=json.loads(reader.execution_receipt.read_text());receipt['refs']['owned_postflight']=post
    ref=write_json(reader.execution_receipt,receipt);reader.receipt_sha256=ref['sha256']
    result=audit(reader)
    assert not any(x['code']=='OWNED_POSTFLIGHT_SCOPE_MATCH' and x['category']=='CONTRACT'
                   for x in result['findings'])


def test_new_sdk_motion_between_request_and_consume_rejects_old_result(tmp_path,monkeypatch):
    records=observation_records()
    records.insert(2,('HEAD_ACTION_SDK_RETURNED',{'goal_uuid':'later-motion','callback_wall_ns':120000000}))
    result=audit(make_reader(tmp_path,records,monkeypatch))
    assert verdict(result,'HFA-006')=='VIOLATED'


def test_finished_and_handoff_job_payload_cannot_conflict(tmp_path,monkeypatch):
    from copy import deepcopy
    records=observation_records();finished=deepcopy(records[1][1])
    finished['record']['source_ns']=777000000
    records.insert(1,('LIVE_STOPPED_OBSERVATION_FINISHED',finished))
    assert verdict(audit(make_reader(tmp_path,records,monkeypatch)),'HFA-006')=='VIOLATED'


def test_cancel_response_requires_saved_original_service_request(tmp_path,monkeypatch):
    goal='00000000-0000-0000-0000-000000000001'
    records=[('HEAD_ACTION_SDK_RETURNED',{'goal_uuid':goal}),
        ('HEAD_ACTION_CANCEL',{'goal_uuid':goal,'original':{'return_code':0,
            'goals_canceling':[{'goal_id':{'uuid':[0]*15+[1]}}]}})]
    result=audit(make_reader(tmp_path,records,monkeypatch))
    assert any(x['code']=='SERVICE_RESPONSE_REQUEST_ORIGINAL_MISSING' for x in result['findings'])


def test_typed_final_position_must_match_dispatched_target(tmp_path,monkeypatch):
    goal='00000000-0000-0000-0000-000000000001'
    typed={'joint_names':['neck_yaw_joint'],'points':[{'positions':[.1],'velocities':[0],
        'accelerations':[0],'time_from_start':{'sec':1,'nanosec':0}}]}
    records=[('HEAD_PREPARED_DISPATCH_TRACE',{'goal_uuid':goal,'inventory_record':{
        'goal_uuid':goal,'typed_goal':{'trajectory':typed}}}),
        ('HEAD_ACTION_SDK_RETURNED',{'goal_uuid':goal}),
        ('SEARCH_OWNED_GOAL_DISPATCHED',{'command':{'goal_uuid':goal,'target_rad':1.0}})]
    assert verdict(audit(make_reader(tmp_path,records,monkeypatch)),'HFA-004')=='VIOLATED'


def test_native_ack_without_original_cancel_response_cannot_prove_stop(tmp_path,monkeypatch):
    # The owned SDK action exists. Native ACK/quiet samples alone cannot replace
    # the actual cancel request/reply obligations after a nonterminal fault.
    records=[('HEAD_ACTION_SDK_RETURNED',{'goal_uuid':'a'}),('FAULT',{'occurred_ns':2000000}),
        ('HEAD_ACTION_GET_RESULT',{'goal_uuid':'a','callback_wall_ns':3000000,
            'original':{'status':6,'result':{'error_code':-1}}}),
        ('NATIVE_CLOSE',{'ack':True,'requested_wall_s':.0035})]
    for n in range(5,8):records.append(('JOINT',{'source_ns':n*1000000,'sequence':n,'wall_s':n*.001,
        'raw_names':['neck_yaw_joint'],'raw_positions':[0],'raw_velocities':[0],'valid':True}))
    records.append(('CANCEL_STOP',{'raw_stop_confirmed':True}))
    result=audit(make_reader(tmp_path,records,monkeypatch))
    assert result['stop']['status']=='UNKNOWN'


def test_missing_run_manifest_with_external_identity_is_unknown(tmp_path,monkeypatch):
    reader=make_reader(tmp_path,[('FAULT',{})],monkeypatch)
    inputs=write_json(tmp_path/'inputs/execution-inputs.json',{'run':RUN})
    receipt=json.loads(reader.execution_receipt.read_text());receipt['refs']['inputs']=inputs
    ref=write_json(reader.execution_receipt,receipt);reader.receipt_sha256=ref['sha256']
    reader.run_root.rename(reader.run_root.with_name('retained-omitted-run'))
    result=audit(reader)
    assert result['integrity']['status']=='INCOMPLETE'
    assert result['execution_checks']['status']=='UNKNOWN'


def test_missing_completion_is_a_gap_not_declared_outcome_conflict(tmp_path,monkeypatch):
    reader=make_reader(tmp_path,[('FAULT',{'reason':'intended'})],monkeypatch)
    (reader.run_root/'completion.json').rename(reader.run_root.parent/'omitted-completion.json')
    result=audit(reader)
    assert result['integrity']['status']=='INCOMPLETE'
    assert result['execution_checks']['status']=='UNKNOWN'


@pytest.mark.parametrize('bad',['confidence','area'])
def test_ineligible_detection_cannot_increment_lock(tmp_path,monkeypatch,bad):
    records=observation_records()
    detection=records[1][1]['record']['detections'][0]
    if bad=='confidence':detection['confidence']=.01
    else:detection['xyxy']=[319.5,239.5,320.5,240.5]
    assert verdict(audit(make_reader(tmp_path,records,monkeypatch)),'HFA-008')=='VIOLATED'


def test_missing_detector_confidence_is_unknown_not_contract_failure(tmp_path,monkeypatch):
    records=observation_records()
    records[1][1]['record']['detections'][0].pop('confidence')
    assert verdict(audit(make_reader(tmp_path,records,monkeypatch)),'HFA-008')=='UNKNOWN'


def test_ineligible_bbox_aspect_cannot_support_lock(tmp_path,monkeypatch):
    records=observation_records()
    records[1][1]['record']['detections'][0]['xyxy']=[220,238,420,242]
    assert verdict(audit(make_reader(tmp_path,records,monkeypatch)),'HFA-008')=='VIOLATED'


def test_used_joint_must_match_saved_original(tmp_path,monkeypatch):
    records=observation_records();row=records[1][1]['record']
    joint={'source_ns':row['joint_source_ns'],'sequence':10,'wall_s':.09,'valid':True,
           'raw_names':['neck_yaw_joint'],'raw_positions':[0.0],'raw_velocities':[0.0]}
    row['causal_joint']=dict(joint,raw_positions=[.5])
    assert verdict(audit(make_reader(tmp_path,[('JOINT',joint)]+records,monkeypatch)),
                   'HFA-005')=='VIOLATED'


def test_used_tf_vector_shape_is_checked_without_geometry_reproof(tmp_path,monkeypatch):
    records=observation_records()
    records[1][1]['record'].update(tf_translation=[0,0],tf_rotation=[0,0,0,1])
    assert verdict(audit(make_reader(tmp_path,records,monkeypatch)),'HFA-005')=='VIOLATED'


def test_missing_success_error_code_is_unknown_not_error_conflict(tmp_path,monkeypatch):
    records=[('HEAD_ACTION_SDK_RETURNED',{'goal_uuid':'a'}),
             ('HEAD_ACTION_SDK_RESULT',{'goal_uuid':'a','original':{'status':4,'result':{}}})]
    assert verdict(audit(make_reader(tmp_path,records,monkeypatch)),'HFA-004')=='UNKNOWN'


def test_combined_goal_index_is_bounded(tmp_path,monkeypatch):
    module=importlib.import_module('so101_demo.act.head_run_audit')
    monkeypatch.setattr(module,'MAX_CORRELATIONS',1)
    records=[('HEAD_PREPARED_DISPATCH_TRACE',{'goal_uuid':'a'}),
             ('HEAD_ACTION_SDK_RETURNED',{'goal_uuid':'b'})]
    with pytest.raises(module.AuditToolError):audit(make_reader(tmp_path,records,monkeypatch))


def test_same_uuid_terminal_status_contradiction_is_violation(tmp_path,monkeypatch):
    goal='00000000-0000-0000-0000-000000000001'
    records=[('HEAD_ACTION_SDK_RETURNED',{'goal_uuid':goal}),
        ('HEAD_ACTION_SDK_RESULT',{'goal_uuid':goal,'original':{'status':4,'result':{'error_code':0}}}),
        ('HEAD_ACTION_STATUS',{'goal_uuid':goal,'original':{'status':5,
            'goal_info':{'goal_id':{'uuid':[0]*15+[1]}}}})]
    assert verdict(audit(make_reader(tmp_path,records,monkeypatch)),'HFA-003')=='VIOLATED'


def test_consumption_after_original_total_deadline_is_violation(tmp_path,monkeypatch):
    records=observation_records()
    records[0][1]['request']['search_deadline_ns']=110000000
    assert verdict(audit(make_reader(tmp_path,records,monkeypatch)),'HFA-007')=='VIOLATED'


def test_capture_receipt_must_match_original_image_callback(tmp_path,monkeypatch):
    records=observation_records();row=records[1][1]['record']
    info=dict(row['original_info'],source_ns=row['source_ns'],frame_id='camera',wall_s=.1)
    row['original_info']=info
    image=dict(source_ns=row['source_ns'],frame_id='camera',wall_s=.001,width=640,height=480)
    result=audit(make_reader(tmp_path,[('IMAGE',image),('INFO',info)]+records,monkeypatch))
    assert verdict(result,'HFA-005')=='VIOLATED'


def test_unsupported_detection_class_cannot_support_lock(tmp_path,monkeypatch):
    records=observation_records();records[1][1]['record']['detections'][0]['class_id']=99
    assert verdict(audit(make_reader(tmp_path,records,monkeypatch)),'HFA-008')=='VIOLATED'


def test_unverified_profile_original_is_unknown(tmp_path,monkeypatch):
    reader=make_reader(tmp_path,[('FAULT',{'reason':'intended'})],monkeypatch)
    source=tmp_path/'inputs/source.json';source.rename(source.with_name('retained-omitted-source.json'))
    result=audit(reader)
    assert result['integrity']['status']=='INCOMPLETE'
    assert result['execution_checks']['status']=='UNKNOWN'


@pytest.mark.parametrize('boundary,rule,code',[
    ('result','HFA-006','RESULT_CONSUMED_BEFORE_DEADLINE'),
    ('total','HFA-007','CONSUMPTION_WITHIN_ORIGINAL_TOTAL_DEADLINE'),
    ('capture','HFA-005','CAPTURE_RECEIPT_AFTER_SETTLED_IMAGE_RECEIVED_WALL_S'),
    ('request','HFA-007','REQUEST_WITHIN_ORIGINAL_DEADLINE')])
def test_float_timestamp_boundary_is_unknown(tmp_path,monkeypatch,boundary,rule,code):
    records=observation_records();request=records[0][1]['request'];row=records[1][1]['record']
    if boundary=='result':row['deadline_ns']=130000000
    elif boundary=='total':request['search_deadline_ns']=130000000
    elif boundary=='capture':row['image_received_wall_s']=request['settled_wall_s']
    else:request['search_deadline_ns']=50000000
    result=audit(make_reader(tmp_path,records,monkeypatch))
    check=next(item for item in result['coverage']['rules'][rule]['checks'] if item['code']==code)
    assert check['verdict']=='UNKNOWN'


@pytest.mark.parametrize('field,bad',[('encoding','bgr8'),('payload_bytes',3),('valid',False),('width',320),('info_valid',False)])
def test_original_image_contract_is_checked(tmp_path,monkeypatch,field,bad):
    records=observation_records();row=records[1][1]['record']
    info=dict(row['original_info'],source_ns=row['source_ns'],frame_id='camera',wall_s=.1)
    image=dict(source_ns=row['source_ns'],frame_id='camera',wall_s=.1,width=640,height=480,
               step=1920,encoding='rgb8',is_bigendian=0,payload_bytes=921600,valid=True)
    if field=='info_valid':info['valid']=bad
    else:image[field]=bad
    if field=='width':info['width']=bad
    row['original_info']=info
    assert verdict(audit(make_reader(tmp_path,[('IMAGE',image),('INFO',info)]+records,monkeypatch)),
                   'HFA-005')=='VIOLATED'


@pytest.mark.parametrize('timing,expected',[('after','PASS'),('before','FAIL'),('missing','UNKNOWN'),('bool','FAIL'),('child_bool','FAIL'),('command_bool','FAIL')])
def test_postflight_must_be_sampled_after_actual_os_exit(tmp_path,monkeypatch,timing,expected):
    records=[('FAULT',{'reason':'intended'}),('EXECUTION_LOOP_RETIREMENT',{'failures':{}}),
        ('EXECUTION_STACK_RETIREMENT',{'retired':True}),
        ('EXECUTION_CHILD_RETIREMENT',{'children':[{'pid':22,'rc':0}]}),
        ('EXECUTION_OWNER_DESCRIPTOR',{'node':'/owned'})]
    reader=make_reader(tmp_path,records,monkeypatch)
    if timing=='child_bool':
        path=reader.run_root/'events.jsonl'
        events=[json.loads(line) for line in path.read_text().splitlines()]
        for event in events:
            if event['kind']=='EXECUTION_CHILD_RETIREMENT':event['record']['children'][0]['rc']=False
        path.write_text(''.join(json.dumps(event)+'\n' for event in events));reseal(reader.run_root)
    receipt=json.loads(reader.execution_receipt.read_text());launcher_path=__import__('pathlib').Path(receipt['refs']['launcher']['path'])
    launcher=json.loads(launcher_path.read_text());launcher['ended_ns']=1000
    receipt['refs']['launcher']=write_json(launcher_path,launcher)
    commands={'ps':{'rc':0},'graph':{'rc':0}}
    if timing=='command_bool':commands['ps']['rc']=False
    if timing!='missing':
        for row in commands.values():row['started_ns']=2000 if timing in ('after','child_bool','command_bool') else (999 if timing=='before' else True)
    post=write_json(tmp_path/'inputs/postflight/result.json',{'phase':'postflight','domain':200,
        'partition':'session','commands':commands,'ready':True})
    (tmp_path/'inputs/postflight/ps.stdout').write_text('999 1 unrelated_service\n')
    (tmp_path/'inputs/postflight/graph.stdout').write_text('/unrelated\n')
    receipt['refs']['owned_postflight']=post
    reference=write_json(reader.execution_receipt,receipt);reader.receipt_sha256=reference['sha256']
    assert audit(reader)['exit_cleanup']['status']==expected


def test_boolean_cancel_return_code_is_not_integer_success(tmp_path,monkeypatch):
    goal='00000000-0000-0000-0000-000000000001'
    records=[('HEAD_ACTION_SDK_RETURNED',{'goal_uuid':goal}),
        ('HEAD_ACTION_SERVICE_REQUEST',{'goal_uuid':goal,'original':{'goal_info':{'goal_id':{'uuid':[0]*15+[1]}}}}),
        ('HEAD_ACTION_CANCEL',{'goal_uuid':goal,'original':{'return_code':False,
            'goals_canceling':[{'goal_id':{'uuid':[0]*15+[1]}}]}})]
    result=audit(make_reader(tmp_path,records,monkeypatch))
    assert any(x['code']=='CANCEL_REPLY_UUID_MATCH' and x['category']=='CONTRACT' for x in result['findings'])


def test_boolean_scoped_generation_cannot_match_integer_one(tmp_path,monkeypatch):
    reader=make_reader(tmp_path,[('SEARCH_OBSERVATION_REQUESTED',{'request':{'generation':True}})],monkeypatch)
    manifest=json.loads((reader.run_root/'manifest.json').read_text());manifest['run']['generation']=1
    write_json(reader.run_root/'manifest.json',manifest)
    path=reader.run_root/'events.jsonl';event=json.loads(path.read_text());event['run']['generation']=1
    path.write_text(json.dumps(event)+'\n');reseal(reader.run_root)
    assert verdict(audit(reader),'HFA-002')=='VIOLATED'


def test_controller_boot_generation_must_match_run(tmp_path,monkeypatch):
    identity={'boot':'boot-a','incarnation':'inc-a','generation':8}
    records=[('HEAD_ACTION_SDK_RETURNED',{'goal_uuid':'a','controller_identity':identity})]
    result=audit(make_reader(tmp_path,records,monkeypatch))
    assert verdict(result,'HFA-002')=='VIOLATED'


@pytest.mark.parametrize('corrupt',[False,True])
def test_corrupt_consumed_rgb_cannot_support_capture_pass(tmp_path,monkeypatch,corrupt):
    import hashlib
    from head_run_audit_support import corpus, reference, reader_module
    records=observation_records();row=records[1][1]['record'];request=records[0][1]['request']
    image_bytes=b'\0'*(640*480*3);digest=hashlib.sha256(image_bytes).hexdigest()
    row['payload_sha256']=digest
    row.update(tf_translation=[0,0,0],tf_rotation=[0,0,0,1])
    info=row['original_info'];info.update(frame_id='camera',source_ns=100000000,wall_s=.1,valid=True)
    goal='00000000-0000-0000-0000-000000000001'
    samples=[{'sequence':n,'source_ns':n*10000000,'wall_s':.01+n*.005,
              'raw_names':['neck_yaw_joint'],'raw_positions':[0.0],'raw_velocities':[0.0],
              'valid':True,'positions':[0.0],'velocities':[0.0]} for n in range(1,4)]
    capture_joint=dict(samples[-1],sequence=4,source_ns=row['joint_source_ns'],wall_s=.09)
    row['causal_joint']=capture_joint
    request['settled_source_floor_ns']=30000000
    trajectory={'joint_names':['neck_yaw_joint'],'points':[{'positions':[0.0],'velocities':[0.0],
        'accelerations':[0.0],'time_from_start':{'sec':1,'nanosec':0}}]}
    prefix=[('HEAD_PREPARED_DISPATCH_TRACE',{'goal_uuid':goal,'inventory_record':{
        'goal_uuid':goal,'typed_goal':{'trajectory':trajectory}}}),
        ('HEAD_ACTION_SDK_RETURNED',{'goal_uuid':goal}),
        ('HEAD_ACTION_SDK_RESULT',{'goal_uuid':goal,'callback_sim_ns':5000000,
            'callback_wall_ns':10000000,'original':{'status':4,'result':{'error_code':0}}})]
    prefix += [('JOINT',x) for x in samples] + [('JOINT',capture_joint)]
    prefix += [('SEARCH_OWNED_GOAL_SETTLED',{'command':{'goal_uuid':goal,'target_rad':0.0,
        'settled_wall_s':.04,'terminal_source_floor_ns':5000000,'confirming_samples':samples}}),
        ('IMAGE',{'source_ns':100000000,'frame_id':'camera','width':640,'height':480,
                  'payload_sha256':digest,'wall_s':.1,'step':1920,'encoding':'rgb8',
                  'is_bigendian':0,'payload_bytes':921600,'valid':True}),('INFO',info)]
    reader=make_reader(tmp_path,prefix+records,monkeypatch)
    artifact=reader.run_root/'artifacts'/f'{digest}.rgb';artifact.parent.mkdir();artifact.write_bytes(image_bytes)
    reseal(reader.run_root);seal=json.loads((reader.run_root/'seal.json').read_text())
    seal['counters']['artifact_count']=1;write_json(reader.run_root/'seal.json',seal)
    # Original seal still describes the captured payload; the independent byte changes.
    if corrupt:artifact.write_bytes(b'X'+image_bytes[1:])
    result=audit(reader)
    assert result['integrity']['status']==('FAIL' if corrupt else 'PASS')
    assert verdict(result,'HFA-005')==('UNKNOWN' if corrupt else 'HOLDS')


def _quiet_joints(first=3, last=6):
    return [('JOINT',{'source_ns':n*1000000,'sequence':n,'wall_s':n*.001,
        'raw_names':['neck_yaw_joint'],'raw_positions':[0.0],'raw_velocities':[0.0],'valid':True})
        for n in range(first,last)]


def _stop_records(*, planned=True, window_n=51, proof=True):
    window = {'first_sim_ns': 9000000, 'last_sim_ns': 9100000, 'n': window_n}
    records = [('STOP_REQUEST',{'origin':'success','occurred_ns':1000000})] if planned else \
        [('FAULT',{'occurred_ns':1000000,'reason':'intended'})]
    records.append(('DEADMAN_ARMED',{'activation_id':'x'}))
    records += _quiet_joints()
    records.append(('CANCEL_STOP',{'raw_stop_confirmed':True,'cancel_error':None,'result_error':None,
                                   'raw_stop_confirmed_sim_ns':5000000}))
    if proof:
        records.append(('STOCK_STOP_PROOF',{'terminal':{'a':4},'raw_stop_samples':[3000000,4000000,5000000],
                                            'raw_stop_confirmed_sim_ns':5000000,'window':window,
                                            'deadman_closed_planned':planned}))
    records.append(('DEADMAN_CLOSED_PLANNED',{'activation_id':'x'}) if planned else
                   ('DEADMAN_CLOSED_FAULT',{'reason':'intended','ack':True,'error':None,
                                            'requested_wall_s':.0015}))
    records.append(('EXECUTION_LOOP_RETIREMENT',{'outcomes':{'runtime':{'deadman_close':{
        'ack':True,'error':None,'planned':planned}}}}))
    return records


def test_hfa009_accepts_a_planned_dead_man_close_after_the_stop_proof(tmp_path, monkeypatch):
    result=audit(make_reader(tmp_path,_stop_records(),monkeypatch))
    assert result['stop']['status']=='PASS', result['stop']
    assert verdict(result,'HFA-009')!='VIOLATED'


def test_hfa009_wrong_window_size_is_a_stop_failure(tmp_path, monkeypatch):
    result=audit(make_reader(tmp_path,_stop_records(window_n=50),monkeypatch))
    assert result['stop']['status']=='FAIL'


def test_hfa009_missing_stop_proof_after_a_confirmed_raw_stop_is_unknown(tmp_path, monkeypatch):
    result=audit(make_reader(tmp_path,_stop_records(proof=False),monkeypatch))
    assert result['stop']['status']=='UNKNOWN'


def test_hfa009_fault_close_must_be_acknowledged(tmp_path, monkeypatch):
    records=_stop_records(planned=False)
    for index,(kind,record) in enumerate(records):
        if kind=='DEADMAN_CLOSED_FAULT':records[index]=(kind,dict(record,ack=False))
    result=audit(make_reader(tmp_path,records,monkeypatch))
    assert result['stop']['status']=='FAIL'




def test_hfa009_accepts_an_acknowledged_fault_close_after_a_proven_stop(tmp_path, monkeypatch):
    # The campaign classifier accepts the same shape (a fault origin latches at once, the stop is proven).
    result=audit(make_reader(tmp_path,_stop_records(planned=False),monkeypatch))
    assert result['stop']['status']=='PASS', result['stop']
    assert verdict(result,'HFA-009')!='VIOLATED'
