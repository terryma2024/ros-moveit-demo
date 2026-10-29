"""A detector bbox is attributed by literal masks, never by track label."""
import copy
import hashlib
import importlib

import pytest


def _inputs(tmp_path):
    frames=[]
    detections=[]
    for number in range(1,4):
        instances=[]
        for name,kind,pixels in [('cup-a','cup',bytes([1,0,0,0])),
                                 ('cup-b','cup',bytes([0,0,0,1])),
                                 ('bottle','distractor',bytes([0,1,0,0]))]:
            path=tmp_path/f'{number}-{name}.mask';path.write_bytes(pixels)
            instances.append(dict(instance_id=name,kind=kind,visible_pixels=sum(pixels),
                mask=dict(path=str(path),sha256=hashlib.sha256(pixels).hexdigest())))
        frames.append(dict(schema_version=1,status='PASS',width=2,height=2,
            source_ns=number*100,frame_sequence=number,simulation_session_id='native-session',
            reset_epoch=1,instances=instances))
        detections.append(dict(source_ns=number*100,bbox_xyxy=[0.,0.,1.,1.]))
    return frames,detections


def _call(frames,detections):
    module=importlib.import_module('so101_demo.act.head_search.campaign_truth')
    return module.attribute_locked_frames(frames,detections)


def test_three_views_attribute_same_real_cup_without_track_name(tmp_path):
    frames,detections=_inputs(tmp_path)
    result=_call(frames,detections)
    assert result['status']=='PASS'
    assert result['instance_id']=='cup-a'
    assert result['wrong_locks']==0
    assert [row['intersection_pixels'] for row in result['frames']]==[1,1,1]


@pytest.mark.parametrize('damage',['two_cups','tie','zero','missing_frame','missing_mask',
    'foreign_epoch','wrong_source','repeat_source','fractional_box','distractor','bad_bbox'])
def test_unproven_or_incorrect_lock_never_becomes_correct(tmp_path,damage):
    frames,detections=_inputs(tmp_path)
    if damage=='two_cups':detections[2]['bbox_xyxy']=[1.,1.,2.,2.]
    elif damage=='tie':detections[0]['bbox_xyxy']=[0.,0.,2.,2.]
    elif damage=='zero':detections[0]['bbox_xyxy']=[0.,1.,1.,2.]
    elif damage=='missing_frame':frames.pop()
    elif damage=='missing_mask':frames[1]['instances'][0]['mask']['sha256']='a'*64
    elif damage=='foreign_epoch':frames[1]['reset_epoch']=2
    elif damage=='wrong_source':detections[0]['source_ns']=999
    elif damage=='repeat_source':frames[1]['source_ns']=frames[0]['source_ns']
    elif damage=='fractional_box':detections[0]['bbox_xyxy']=[.6,.6,1.4,1.4]
    elif damage=='distractor':detections[0]['bbox_xyxy']=[1.,0.,2.,1.]
    else:detections[0]['bbox_xyxy']=[float('nan'),0.,1.,1.]
    result=_call(frames,detections)
    assert result['status']!='PASS'
    if damage in ('two_cups','distractor'):
        assert result['status']=='FAIL' and result['wrong_locks']==1
    else:
        assert result['status']=='UNKNOWN'
