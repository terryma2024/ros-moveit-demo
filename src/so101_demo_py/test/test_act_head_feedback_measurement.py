"""Complete stopped-workload windows retain every original and matching clock."""

from bisect import bisect_right
import copy
import math

import pytest

from so101_demo.act.head_feedback_measurement import evaluate_feedback_window


def window(rtf=1.):
    def messages(period):
        return [dict(source_ns=10_000_000_000+round(index*period*1e9),
            wall_s=100.+index*period/rtf+.001,valid=True)
            for index in range(math.floor((20.-.001)*rtf/period)+1)]
    joints,cameras,clocks=messages(.01),messages(.1),messages(.002)
    joint_receipts=[sample['wall_s'] for sample in joints]
    camera_receipts=[sample['wall_s'] for sample in cameras]
    decisions=[]
    for index in range(4000):
        now=100.002+index*.005
        decisions.append(dict(joint=dict(joints[bisect_right(joint_receipts,now)-1]),
            camera=dict(cameras[bisect_right(camera_receipts,now)-1]),
            clocks=dict(wall_before_s=now,wall_after_s=now,
                sim_ns=10_000_000_000+math.floor(round((now-100.)*rtf*1e9)/2_000_000)*2_000_000)))
    inferences=[dict(source_ns=frame['source_ns'],info_source_ns=frame['source_ns'],
        joint_source_ns=frame['source_ns'],tf_source_ns=frame['source_ns']-2_000_000,
        image_received_wall_s=frame['wall_s'],
        info_received_wall_s=frame['wall_s'],admission_wall_s=frame['wall_s']+.001,
        completion_wall_s=frame['wall_s']+.004,source_skew_s=.002)
        for frame in cameras]
    return dict(start_wall_s=100.,end_wall_s=120.,decisions=decisions,joint_messages=joints,
        camera_messages=cameras,info_messages=copy.deepcopy(cameras),clock_messages=clocks,
        watchdog_polls=[100.+index*.002 for index in range(10001)],
        inferences=inferences,clock_resolution_s=.002)


def test_complete_window_derives_explicit_separate_clock_bounds():
    measured=evaluate_feedback_window(window(),stop_latency_s=.07)
    values=measured['values']
    assert values['joint_max_receipt_age_s']==pytest.approx(.016)
    assert values['joint_max_source_age_s']==pytest.approx(.016)
    assert values['camera_interarrival_deadline_s']==pytest.approx(.11)
    assert values['clock_interarrival_deadline_s']==pytest.approx(.012)
    assert measured['camera_seed_values']['max_age_s']==pytest.approx(.014)
    assert measured['camera_seed_values']['max_skew_s']==pytest.approx(.004)
    assert measured['quantile']=='linear interpolation at (n-1)*p'
    assert measured['counts']['decisions']==4000
    assert measured['purpose']=='calibration' and measured['motion_authority'] is False


def test_stopped_frame_guard_includes_actual_cpu_receipts_and_main_consumer():
    raw=window()
    for row in raw['inferences']:
        row['matched_consumer_measurement']=dict(motion_authority=False,
            image_source_ns=row['source_ns'],
            cpu_image_received_wall_s=row['image_received_wall_s']-.002,
            cpu_info_received_wall_s=row['info_received_wall_s']-.003,
            cpu_inputs_decision_wall_s=row['admission_wall_s'],
            cpu_completion_decision_wall_s=row['completion_wall_s']+.012,
            root_handoff_decision_wall_s=row['completion_wall_s']+.020)
    measured=evaluate_feedback_window(raw,stop_latency_s=.07)
    # Old direct CUDA population tops at 4ms. The independent slowest
    # consumer is Main at 24ms after Root, 27ms after actual CPU Info.
    assert measured['camera_seed_values']['max_age_s']==pytest.approx(.037)
    assert measured['distributions']['camera_end_to_end_age_s']['count']==2400


@pytest.mark.parametrize('damage',['future_receipt','early_completion','early_main','source','authority','partial','stripped'])
def test_full_consumer_measurement_refuses_changed_or_missing_original_clocks(damage):
    raw=window()
    raw['consumer_measurement']='MATCHED_CPU_CUDA_MAIN'
    for row in raw['inferences']:
        row['matched_consumer_measurement']=dict(motion_authority=False,
            image_source_ns=row['source_ns'],
            cpu_image_received_wall_s=row['image_received_wall_s'],
            cpu_info_received_wall_s=row['info_received_wall_s'],
            cpu_inputs_decision_wall_s=row['admission_wall_s'],
            cpu_completion_decision_wall_s=row['completion_wall_s'],
            root_handoff_decision_wall_s=row['completion_wall_s']+.002)
    target=raw['inferences'][42];proof=target['matched_consumer_measurement']
    if damage=='future_receipt':proof['cpu_image_received_wall_s']=proof['cpu_inputs_decision_wall_s']+.001
    elif damage=='early_completion':proof['cpu_completion_decision_wall_s']=target['completion_wall_s']-.001
    elif damage=='early_main':proof['root_handoff_decision_wall_s']=target['completion_wall_s']-.001
    elif damage=='source':proof['image_source_ns']+=1
    elif damage=='authority':proof['motion_authority']=True
    elif damage=='partial':target.pop('matched_consumer_measurement')
    else:
        for row in raw['inferences']:row.pop('matched_consumer_measurement')
    with pytest.raises(ValueError):evaluate_feedback_window(raw,stop_latency_s=.07)


@pytest.mark.parametrize('damage',['none','source','actor','detached','changed','schedule'])
def test_scheduled_main_handoff_must_be_an_original_decision_in_the_full_cohort(damage):
    raw=window();raw['consumer_measurement']='MATCHED_CPU_CUDA_MAIN'
    raw['root_handoff_schedule']='EXISTING_5MS_DECISION_WORKER'
    for row in raw['inferences']:
        decision=next(d for d in raw['decisions'] if d['clocks']['wall_after_s']>=row['completion_wall_s'])
        decision.update(calibration_consumed_source_ns=row['source_ns'],
            calibration_completion_ack_wall_s=row['completion_wall_s'],consumer_thread_native_id=77)
        row['root_handoff']=copy.deepcopy(decision)
        row['cpu_measurement_completion']={'ack_wall_s':row['completion_wall_s']}
        row['matched_consumer_measurement']=dict(motion_authority=False,image_source_ns=row['source_ns'],
            cpu_image_received_wall_s=row['image_received_wall_s'],cpu_info_received_wall_s=row['info_received_wall_s'],
            cpu_inputs_decision_wall_s=row['admission_wall_s'],cpu_completion_decision_wall_s=row['completion_wall_s'],
            root_handoff_decision_wall_s=decision['clocks']['wall_after_s'])
    handoff=raw['inferences'][42]['root_handoff']
    if damage=='source':handoff['calibration_consumed_source_ns']+=1
    elif damage=='actor':handoff['consumer_thread_native_id']=0
    elif damage=='detached':handoff['clocks']['wall_before_s']+=.00001
    elif damage=='changed':handoff['joint']['wall_s']-=.00001
    elif damage=='schedule':raw['root_handoff_schedule']='IMMEDIATE_CALLER'
    if damage=='none':assert evaluate_feedback_window(raw,stop_latency_s=.07)['counts']['decisions']==4000
    else:
        with pytest.raises(ValueError):evaluate_feedback_window(raw,stop_latency_s=.07)


def test_source_period_is_never_a_monotonic_margin():
    measured=evaluate_feedback_window(window(.96),stop_latency_s=.07)
    periods=measured['periods'];series=measured['distributions']
    assert periods['joint_source_p50_s']==pytest.approx(.01)
    assert periods['joint_receipt_p50_s']==pytest.approx(.01/.96)
    assert measured['values']['joint_max_receipt_age_s']==pytest.approx(
        series['joint_receipt_age_s']['p99']+periods['joint_receipt_p50_s'])
    assert measured['values']['joint_max_source_age_s']==pytest.approx(
        series['joint_source_age_s']['p99']+periods['joint_source_p50_s'])


@pytest.mark.parametrize('damage',['joint_count','camera_count','decision_count','joint_gap',
    'camera_gap','duplicate_joint','regressed_camera','future_receipt','future_source',
    'invalid_original','nonfinite','clock_regression','clock_stall','wall_clock_regression',
    'watchdog_gap','source_ceiling','clock_receipt_ceiling','missing_inference',
    'duplicate_inference','camera_age_cap','skew_cap','duration'])
def test_invalid_complete_window_cannot_create_policy_or_clip_outliers(damage):
    raw=window()
    if damage=='joint_count':raw['joint_messages']=raw['joint_messages'][:1899]
    elif damage=='camera_count':raw['camera_messages']=raw['camera_messages'][:189]
    elif damage=='decision_count':raw['decisions']=raw['decisions'][:3899]
    elif damage=='joint_gap':raw['joint_messages'].pop(100)
    elif damage=='camera_gap':raw['camera_messages'].pop(100)
    elif damage=='duplicate_joint':raw['joint_messages'][100]['source_ns']=raw['joint_messages'][99]['source_ns']
    elif damage=='regressed_camera':raw['camera_messages'][100]['source_ns']=raw['camera_messages'][99]['source_ns']-1
    elif damage=='future_receipt':raw['decisions'][100]['joint']['wall_s']=raw['decisions'][100]['clocks']['wall_after_s']+.001
    elif damage=='future_source':raw['decisions'][100]['joint']['source_ns']=raw['decisions'][100]['clocks']['sim_ns']+1
    elif damage=='invalid_original':raw['joint_messages'][100]['valid']=False
    elif damage=='nonfinite':raw['decisions'][100]['joint']['wall_s']=float('nan')
    elif damage=='clock_regression':raw['decisions'][100]['clocks']['sim_ns']=raw['decisions'][99]['clocks']['sim_ns']-1
    elif damage=='clock_stall':raw['decisions'][100]['clocks']['sim_ns']=raw['decisions'][99]['clocks']['sim_ns']
    elif damage=='wall_clock_regression':raw['decisions'][100]['clocks']['wall_before_s']=raw['decisions'][99]['clocks']['wall_after_s']-.001
    elif damage=='watchdog_gap':raw['watchdog_polls']=raw['watchdog_polls'][:100]+raw['watchdog_polls'][106:]
    elif damage=='source_ceiling':
        originals={record['source_ns']:record for record in raw['joint_messages']}
        for decision in raw['decisions']:
            earlier=originals.get(decision['joint']['source_ns']-10_000_000)
            if earlier is not None:decision['joint']=dict(earlier)
    elif damage=='clock_receipt_ceiling':
        raw['clock_messages'][500]['wall_s']=raw['clock_messages'][499]['wall_s']+.014
    elif damage=='missing_inference':raw['inferences'].pop(100)
    elif damage=='duplicate_inference':raw['inferences'][100]=copy.deepcopy(raw['inferences'][99])
    elif damage=='camera_age_cap':
        raw['inferences'][100]['completion_wall_s']=raw['inferences'][100]['image_received_wall_s']+.145
        raw['inferences'][101]['admission_wall_s']=raw['inferences'][100]['completion_wall_s']+.001
        raw['inferences'][101]['completion_wall_s']=raw['inferences'][101]['admission_wall_s']+.004
    elif damage=='skew_cap':
        for inference in raw['inferences']:
            inference['source_skew_s']=.049
            inference['tf_source_ns']=inference['source_ns']-49_000_000
    else:raw['end_wall_s']=119.99
    refusal={'source_ceiling':'HEAD_WINDOW_POLICY_CEILING',
             'camera_age_cap':'HEAD_WINDOW_CAMERA_CEILING'}.get(damage)
    with pytest.raises(ValueError,match=refusal):evaluate_feedback_window(raw,stop_latency_s=.07)


@pytest.mark.parametrize('damage', ['missing_info','changed_info_receipt','future_info_source',
    'missing_skew_sources','forged_skew','unlinked_joint','watchdog_start_gap','watchdog_end_gap',
    'clock_gap_outlier','snapshot_not_original'])
def test_every_original_and_observed_outlier_remains_bound(damage):
    raw=window()
    if damage=='missing_info':raw['info_messages'].pop(100)
    elif damage=='changed_info_receipt':raw['inferences'][100]['info_received_wall_s']+=.0001
    elif damage=='future_info_source':raw['inferences'][100]['info_source_ns']+=1
    elif damage=='missing_skew_sources':del raw['inferences'][100]['tf_source_ns']
    elif damage=='forged_skew':raw['inferences'][100]['tf_source_ns']-=1_000_000
    elif damage=='unlinked_joint':raw['inferences'][100]['joint_source_ns']-=1
    elif damage=='watchdog_start_gap':raw['watchdog_polls']=raw['watchdog_polls'][6:]
    elif damage=='watchdog_end_gap':raw['watchdog_polls']=raw['watchdog_polls'][:-6]
    elif damage=='clock_gap_outlier':
        # Preserve observed order: this specifically exercises the single gap
        # above p99+margin, rather than accidentally causing receipt regression.
        for sample in raw['clock_messages'][500:]:sample['wall_s']+=.014
        raw['clock_messages']=raw['clock_messages'][:-7]
    else:raw['decisions'][100]['joint']['source_ns']-=1
    with pytest.raises(ValueError):evaluate_feedback_window(raw,stop_latency_s=.07)


def test_later_completion_does_not_make_a_backward_frame_admissible():
    raw=window()
    raw['inferences'][100],raw['inferences'][101]=raw['inferences'][101],raw['inferences'][100]
    older=raw['inferences'][101]
    older['admission_wall_s']=raw['inferences'][100]['completion_wall_s']+.001
    older['completion_wall_s']=older['admission_wall_s']+.001
    with pytest.raises(ValueError):evaluate_feedback_window(raw,stop_latency_s=.07)


def with_carry_in():
    raw=window()
    carry={}
    for name,field,period in (('joint','joint_messages',.01),('camera','camera_messages',.1),
                             ('info','info_messages',.1),('clock','clock_messages',.002)):
        first=raw[field][0]
        carry[name]=dict(first,source_ns=first['source_ns']-round(period*1e9),wall_s=first['wall_s']-period)
    raw['carry_in']=carry
    raw['decisions'].insert(0,dict(joint=dict(carry['joint']),camera=dict(carry['camera']),
        clocks=dict(wall_before_s=100.0005,wall_after_s=100.0005,sim_ns=10_000_000_000)))
    return raw


def test_pre_window_originals_bind_first_decision_without_inflating_window_counts():
    measured=evaluate_feedback_window(with_carry_in(),stop_latency_s=.07)
    assert measured['counts']['joint_messages']==2000
    assert measured['counts']['camera_messages']==200
    assert measured['counts']['decisions']==4001
    assert measured['carry_in_counts']==dict(joint=1,camera=1,info=1,clock=1)
    assert measured['distributions']['camera_source_age_s']['max']>=.1


@pytest.mark.parametrize('damage',['invalid','future_receipt','source_gap','source_collision','changed_copy','missing_reference'])
def test_carry_in_never_substitutes_counts_or_forgives_bad_originals(damage):
    raw=with_carry_in()
    if damage=='invalid':raw['carry_in']['joint']['valid']=False
    elif damage=='future_receipt':raw['carry_in']['camera']['wall_s']=100.002
    elif damage=='source_gap':raw['carry_in']['joint']['source_ns']-=10_000_000
    elif damage=='source_collision':raw['carry_in']['camera']['source_ns']=raw['camera_messages'][0]['source_ns']
    elif damage=='changed_copy':raw['decisions'][0]['joint']['wall_s']-=.001
    else:del raw['carry_in']
    with pytest.raises(ValueError):evaluate_feedback_window(raw,stop_latency_s=.07)


def camera_transport_window():
    """Every original is retained; a 12 ms pipeline delay is not phase clipping."""
    raw=with_carry_in()
    for field in ('camera_messages','info_messages'):
        for message in raw[field]:message['wall_s']+=.012
    for name in ('camera','info'):raw['carry_in'][name]['wall_s']+=.012
    originals=[raw['carry_in']['camera']]+raw['camera_messages']
    receipts=[original['wall_s'] for original in originals]
    for decision in raw['decisions']:
        index=bisect_right(receipts,decision['clocks']['wall_before_s'])-1
        decision['camera']=dict(originals[index])
    for inference in raw['inferences']:
        for field in ('image_received_wall_s','info_received_wall_s','admission_wall_s','completion_wall_s'):
            inference[field]+=.012
    return raw


def test_camera_source_margin_does_not_pay_an_exposure_interval_twice():
    measured=evaluate_feedback_window(camera_transport_window(),stop_latency_s=.07)
    assert measured['distributions']['camera_source_age_s']['count']==4001
    assert measured['distributions']['camera_source_age_s']['p99']==pytest.approx(.112)
    assert measured['values']['camera_max_source_age_s']==pytest.approx(.122)
    assert measured['values']['camera_max_source_age_s']<=2*measured['periods']['camera_source_p50_s']
    assert measured['formulas']['camera_max_source_age_s']=='camera_source_age_s.p99 + joint_source_period_s.p50'


def test_original_camera_stale_inside_hard_ceiling_still_fails_tighter_bound():
    raw=camera_transport_window();decision=raw['decisions'][695]
    older=decision['camera']['source_ns']-100_000_000
    originals={record['source_ns']:record for record in raw['camera_messages']}
    decision['camera']=dict(originals[older])
    age=(decision['clocks']['sim_ns']-older)*1e-9
    assert .122<age<.2
    with pytest.raises(ValueError,match='HEAD_WINDOW_OBSERVATION_EXCEEDS_BOUND'):
        evaluate_feedback_window(raw,stop_latency_s=.07)
