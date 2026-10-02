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
