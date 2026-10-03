"""Controlled diagnostic settlement tests; application proof is a separate live run."""
from types import SimpleNamespace
import pytest
from so101_demo.cli.head_feedback_bootstrap import _bound_goal_settlement

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

@pytest.mark.parametrize('stage',['STOPPED_BOOTSTRAP_MEASURED','NATIVE_BINDING_STOPPED_DIAGNOSTIC','BOUND_GOAL_STOPPED_DIAGNOSTIC'])
def test_late_failure_irreversibly_refuses_attempt(stage):
    from so101_demo.cli.head_feedback_bootstrap import _record_refusal
    result=dict(status=stage,qualification=False)
    _record_refusal(result,RuntimeError('later failure'))
    assert result['status']=='REFUSED'
    assert result['error']['type']=='RuntimeError'


def test_prepare_imports_and_goal_codecs_constructs_no_runtime_resources(monkeypatch):
    from rclpy.node import Node
    from rclpy.action import ActionClient
    from so101_demo.adapters.act.head_reservation_authority import HeadReservationAuthority
    from so101_demo.act.head_search_restarts import TimedHeadDetector
    from so101_demo.cli.head_feedback_bootstrap import _prepare_bound_goal_dispatch
    def forbidden(*args,**kw):raise AssertionError('new runtime resource or motion factory')
    monkeypatch.setattr(Node,'__init__',forbidden)
    monkeypatch.setattr(ActionClient,'__init__',forbidden)
    monkeypatch.setattr(HeadReservationAuthority,'__init__',forbidden)
    monkeypatch.setattr(TimedHeadDetector,'build',forbidden)
    receipt=_prepare_bound_goal_dispatch()
    assert receipt['goal_codec']['native_arm_count']==receipt['goal_codec']['sdk_send_count']==0
    assert receipt['goal_codec']['payload_bytes']>0
    assert set(receipt['modules'])=={
        'so101_demo.act.head_search_calibration_admission_document',
        'so101_demo.act.head_search_calibration_run',
        'so101_demo.adapters.act.head_inventory_dispatch',
        'so101_demo.adapters.act.ros_neck',
        'so101_demo.adapters.act.head_live_exposure',
        'so101_demo.adapters.act.head_owned_search'}


def test_search_controller_flag_requires_the_existing_once_owned_pipeline(capsys):
    from so101_demo.cli.head_feedback_bootstrap import main
    argv=[]
    for name in ('run-root','reservation-root','runtime-manifest','production-config','geometry-seal',
                 'frozen-candidate','urdf','scene','plugin-config','controller-config'):
        argv+=['--'+name,'/nonexistent/head-input']
    with pytest.raises(SystemExit) as error:main(argv+['--search-controller-diagnostic'])
    assert error.value.code==2
    assert '--search-controller-diagnostic requires --owned-inference-diagnostic' in capsys.readouterr().err


@pytest.mark.parametrize('conflict',['--bound-goal-diagnostic','--search-controller-diagnostic',
    '--moving-exposure-diagnostic','--owned-inference-diagnostic','--native-binding-diagnostic'])
def test_live_pipeline_measurement_is_exclusive_and_cannot_restore_sdk(conflict,capsys):
    from so101_demo.cli.head_feedback_bootstrap import main
    argv=[]
    for name in ('run-root','reservation-root','runtime-manifest','production-config','geometry-seal',
                 'frozen-candidate','urdf','scene','plugin-config','controller-config'):
        argv+=['--'+name,'/nonexistent/head-input']
    with pytest.raises(SystemExit) as error:main(argv+['--live-pipeline-measurement',conflict])
    assert error.value.code==2
    assert '--live-pipeline-measurement is exclusive' in capsys.readouterr().err


@pytest.mark.parametrize('counts',[(1,0),(0,1),(None,0)])
def test_trajectory_preparation_is_refused_before_reading_inputs_after_arm_or_send(counts):
    from so101_demo.cli.head_feedback_bootstrap import _prepare_bound_goal_plan
    def forbidden():raise AssertionError('trajectory input read after ARM or an SDK send')
    result=dict(native_arm_count=counts[0],goal_send_count=counts[1])
    with pytest.raises(PermissionError):
        _prepare_bound_goal_plan(port=SimpleNamespace(feedback_snapshot=forbidden),
            production={},geometry={},result=result)


def test_search_refusal_retains_post_arm_reserve_and_last_dispatch_boundaries():
    from so101_demo.cli.head_feedback_bootstrap import _run_owned_search_diagnostic
    def fail():raise PermissionError('original exposure expired')
    driver=SimpleNamespace(tick=fail,result=None,commands=[],observations=[])
    receipts=[dict(operation='SOGB',request_wall_s=1.,ack_wall_s=1.001)]
    traces=[dict(error_type='PermissionError',phases=[dict(phase='dispatch_2_entry',wall_s=1.002)])]
    dispatcher=SimpleNamespace(inventory={},authority=SimpleNamespace(exchange_receipts=receipts),
        dispatch_traces=traces)
    result=dict(search_controller_diagnostic={})
    with pytest.raises(PermissionError,match='original exposure expired'):
        _run_owned_search_diagnostic(driver=driver,dispatcher=dispatcher,result=result,emit=lambda *a,**k:None)
    evidence=result['search_controller_diagnostic']
    assert evidence['main_exchange_receipts']==receipts
    assert evidence['dispatch_traces']==traces
    receipts.clear()
    assert evidence['main_exchange_receipts']


def pipeline_harness():
    import threading
    clock=[1.];events=[];ticks=[];quiescence=[]
    identity=dict(name='existing-inference',ident=2,native_id=3,daemon=False)
    port=SimpleNamespace(feedback_snapshot=lambda:dict(decision=dict(
        wall_before_s=clock[0],wall_after_s=clock[0],sim_ns=round(clock[0]*10**9)),
        sequence=len(ticks)+1,source_ns=round(clock[0]*10**9),wall_s=clock[0],valid=True))
    primary=SimpleNamespace(ready=True,failed=False,port=port,observer=SimpleNamespace(camera_age=.05),
        dispatch_guard=lambda:ticks.append(clock[0]),fault=lambda *args:events.append(('fault',args)))
    rows=[]
    for i in range(200):
        wall=1.1+i*.1;source=round(wall*10**9)
        image=dict(wall_s=wall+.001,source_ns=source,valid=True,payload_sha256='a'*64)
        info=dict(wall_s=wall+.002,source_ns=source,valid=True)
        rows.append(dict(sequence=i+1,source_ns=source,image_received_wall_s=wall,
            info_received_wall_s=wall+.001,payload_sha256='a'*64,deadline_ns=round((wall+.05)*10**9),
            cuda_started_wall_s=wall+.003,completion_wall_s=wall+.019,
            admission_ack=dict(exposure_admitted=True,original_snapshot=dict(image=image,info=info,
                decision=dict(wall_after_s=wall+.003))),
            completion_ack=dict(exposure_finished=True,original_snapshot=dict(
                decision=dict(wall_after_s=wall+.020)))))
    class Owner:
        def infer(self):pass
        def next_completed_exposure(self,after_sequence):
            return next((row for row in rows if row['sequence']>after_sequence
                and row['completion_ack']['original_snapshot']['decision']['wall_after_s']<=clock[0]),None)
        def quiesce_live(self):
            assert not quiescence;quiescence.append(clock[0])
        def live_quiescence(self):
            if not quiescence or clock[0]<quiescence[0]+.020:return None
            return dict(requested_wall_s=quiescence[0],quiesced_wall_s=clock[0],inference_owner=identity)
    result=dict(goal_send_count=0,native_arm_count=1,inference_owner=identity,
        live_pipeline_measurement=dict(window=dict(start_ns=1_050_000_000,end_ns=21_050_000_000)))
    return SimpleNamespace(clock=clock,events=events,ticks=ticks,rows=rows,primary=primary,port=port,
        owner=Owner(),result=result,sleep=lambda seconds:clock.__setitem__(0,clock[0]+seconds))


def test_full_live_pipeline_window_retains_all_four_receipts_and_200_frames():
    from so101_demo.cli import head_feedback_bootstrap as module
    c=pipeline_harness()
    receipt=module._run_live_pipeline_measurement(port=c.port,primary=c.primary,owner=c.owner,
        result=c.result,emit=lambda event,**fields:c.events.append((event,fields)),
        monotonic=lambda:c.clock[0],sleep=c.sleep)
    assert receipt['window']==dict(start_ns=1_050_000_000,end_ns=21_050_000_000)
    assert receipt['frame_count']==200 and receipt['qualification'] is False
    assert receipt['sdk_send_count']==0 and c.result['goal_send_count']==0
    assert len(receipt['frames'])==200 and receipt['quiescence']['inference_owner']==c.result['inference_owner']
    assert len(c.ticks)>=4000 and c.clock[0]>=21.07
    assert receipt['frames'][0]['original']==c.rows[0]
    # A frame can reach the Main handoff on the following5ms control tick.
    assert receipt['frame_age']['values']['max_age_s']==pytest.approx(.035)
    assert receipt['frame_age']['sample_count']==2400


@pytest.mark.parametrize('damage',['missing','extra','sdk','source','late_completion','revoked'])
def test_live_window_cannot_hide_missing_frames_motion_or_invalid_originals(damage):
    from so101_demo.cli import head_feedback_bootstrap as module
    c=pipeline_harness()
    if damage=='missing':c.rows.pop(30)
    elif damage=='extra':c.rows[-1]['sequence']=201
    elif damage=='sdk':c.result['goal_send_count']=1
    elif damage=='source':c.rows[30]['source_ns']+=2
    elif damage=='late_completion':c.rows[30]['completion_wall_s']+=.050
    elif damage=='revoked':c.primary.ready=False;c.primary.failed=True
    with pytest.raises((PermissionError,ValueError)):
        module._run_live_pipeline_measurement(port=c.port,primary=c.primary,owner=c.owner,
            result=c.result,emit=lambda *args,**fields:None,monotonic=lambda:c.clock[0],sleep=c.sleep)
    assert c.result['live_pipeline_measurement'].get('status')!='LIVE_PIPELINE_MEASURED_UNPROMOTED'


@pytest.mark.parametrize('past',[False,True])
def test_live_window_boundary_uses_actual_measured_schema_and_original_receipt(past):
    import threading
    from so101_demo.cli import head_feedback_bootstrap as module
    image=dict(source_ns=1_000_000_000,wall_s=10.,valid=True)
    observer=SimpleNamespace(_lock=threading.Lock(),_images={image['source_ns']:image},_camera=None)
    primary=SimpleNamespace(observer=observer,dispatch_guard=lambda:True)
    measured=dict(distributions=dict(camera_receipt_gap_s=dict(p50=.1),
        camera_end_to_end_age_s=dict(p99=.020),joint_receipt_period_s=dict(p99=.011)))
    if past:
        with pytest.raises(PermissionError):
            module._declare_live_pipeline_window(primary,measured,monotonic=lambda:10.05)
    else:
        window=module._declare_live_pipeline_window(primary,measured,monotonic=lambda:10.02)
        assert window['start_ns']==10_050_000_000 and window['end_ns']==30_050_000_000
        assert window['boundary_original']==image and image['wall_s']==10.
        assert window['phase_s']==.05
