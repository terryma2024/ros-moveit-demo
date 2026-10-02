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
