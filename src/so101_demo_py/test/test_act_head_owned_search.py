"""Original completed exposures drive the real search, never a fabricated lock."""
from copy import deepcopy
from types import SimpleNamespace
import threading

import pytest

from test_act_search import config, BOX
from so101_demo.cli.head_feedback_bootstrap import _bound_goal_settlement


def exposure(sequence=1, *, q=0., detections=None):
    source=1_000_000_000+(sequence-1)*100_000_000
    wall=source*1e-9
    return dict(epoch='a',session_id='s',sequence=sequence,source_ns=source,
        info_source_ns=source,joint_source_ns=source,tf_source_ns=source,
        image_received_wall_s=wall,info_received_wall_s=wall,deadline_ns=source+150_000_000,
        original_info=dict(source_ns=source,wall_s=wall,frame_id='head_camera_frame',
            k=[400.,0.,320.,0.,400.,240.,0.,0.,1.],d=[0.]*5),
        causal_joint=dict(sequence=sequence,source_ns=source,wall_s=wall,valid=True,
            positions=[q],velocities=[0.]),tf_rotation=[0.,2**-.5,-2**-.5,0.],
        detections=deepcopy([BOX] if detections is None else detections))


def driver():
    from so101_demo.adapters.act.head_owned_search import OwnedHeadSearch
    clock=[1.];events=[];faults=[];sent=[];deadlines=[];rows=[]
    port=SimpleNamespace(_lock=threading.Lock(),_goals={},_head_samples=[])
    from test_act_head_feedback_freshness import policy
    port.feedback_policy=policy()
    port.feedback_snapshot=lambda:dict(sequence=1,valid=True,positions=[0.],velocities=[0.],wall_s=clock[0],
        source_ns=round(clock[0]*1e9),decision=dict(sim_ns=round(clock[0]*1e9),sim_s=clock[0],
            wall_before_s=clock[0],wall_after_s=clock[0]))
    class Primary:
        def dispatch_guard(self):return True
        def fault(self,*args):faults.append(args)
        def dispatch_observation_deadline(self,value):deadlines.append(value)
    class Owner:
        def infer(self):pass
        def next_completed_exposure(self,after_sequence):
            return next((deepcopy(row) for row in rows if row['sequence']>after_sequence),None)
    class Neck:
        def command_neck(self,target,**scope):
            gid='goal-'+str(len(sent)+1);sent.append((gid,target,scope))
            port._goals[gid]=dict(accepted=None,result=None)
            return gid
    search=OwnedHeadSearch(config=config(),primary=Primary(),port=port,owner=Owner(),
        settlement=_bound_goal_settlement,stop_velocity_rad_s=.01,
        monotonic=lambda:clock[0],emit=lambda event,**fields:events.append(dict(event=event,**fields)))
    search.bind_transport(Neck())
    return SimpleNamespace(search=search,clock=clock,rows=rows,port=port,events=events,
        sent=sent,deadlines=deadlines,faults=faults)


def test_mapping_preserves_original_camera_causal_joint_and_header_rotation():
    from so101_demo.adapters.act.head_owned_search import map_owned_search_exposure
    row=exposure();original=deepcopy(row)
    frame,joint=map_owned_search_exposure(row,config())
    assert frame['sim_time_s']==joint['sim_time_s']==1.
    assert frame['received_wall_s']==joint['received_wall_s']==1.
    assert frame['k']==row['original_info']['k']
    assert frame['rotation_optical_to_base'][1][2]==pytest.approx(-1.)
    frame['k'][0]=1.;frame['detections'][0]['track_id']='changed'
    assert row==original


@pytest.mark.parametrize('damage',['scope','info_source','info_frame','joint_future',
    'joint_skew','tf_future','tf_skew','rotation','sequence','joint_invalid','intrinsics','distortion'])
def test_mapping_rejects_foreign_or_noncausal_originals(damage):
    from so101_demo.adapters.act.head_owned_search import map_owned_search_exposure
    row=exposure()
    if damage=='scope':row['epoch']='foreign'
    elif damage=='info_source':row['original_info']['source_ns']+=1
    elif damage=='info_frame':row['original_info']['frame_id']='foreign'
    elif damage=='joint_future':row['causal_joint']['source_ns']+=1
    elif damage=='joint_skew':row['causal_joint']['source_ns']-=20_000_001
    elif damage=='tf_future':row['tf_source_ns']+=1
    elif damage=='tf_skew':row['tf_source_ns']-=20_000_001
    elif damage=='rotation':row['tf_rotation']=[0.]*4
    elif damage=='sequence':row['sequence']=True
    elif damage=='intrinsics':row['original_info']['k'][0]=0.
    elif damage=='distortion':row['original_info']['d']=[]
    else:row['causal_joint']['valid']=False
    with pytest.raises((ValueError,PermissionError)):map_owned_search_exposure(row,config())


def test_actual_controller_locks_only_three_fresh_same_track_frames_without_sdk_motion():
    c=driver()
    for sequence in (1,2,3):
        c.rows.append(exposure(sequence));c.clock[0]=c.rows[-1]['image_received_wall_s']+.01
        result=c.search.tick()
        if sequence<3:assert result is None
    assert result['status']=='TARGET_LOCKED' and result['found'] is True
    assert c.sent==[] and c.search.controller.lock_count==3
    assert c.search.controller.__class__.__name__=='HeadSearchController'


def test_track_change_resets_lock_and_completed_exposure_is_consumed_once():
    c=driver()
    for sequence,track in ((1,'cup1'),(2,'cup2'),(3,'cup2')):
        c.rows.append(exposure(sequence,detections=[dict(BOX,track_id=track)]))
        c.clock[0]=c.rows[-1]['image_received_wall_s']+.01
        assert c.search.tick() is None
    assert c.search.controller.lock_count==2
    assert c.search.tick() is None and c.search.controller.lock_count==2


def test_unknown_goal_blocks_lock_until_terminal_and_three_original_settled_samples():
    c=driver();off_center=dict(BOX,xyxy=[340.,200.,380.,280.])
    c.rows.append(exposure(detections=[off_center]));c.clock[0]=1.01
    assert c.search.tick() is None and len(c.sent)==1
    gid,target,_=c.sent[0]
    assert c.deadlines[0]==pytest.approx(1.15) and c.deadlines[1] is None
    c.rows.append(exposure(2,q=target));c.clock[0]=1.11
    assert c.search.tick() is None and c.search.controller.lock_count==0
    c.port._goals[gid]=dict(accepted=True,result=SimpleNamespace(status=4,
        result=SimpleNamespace(error_code=0)))
    c.clock[0]=1.12;c.search.tick()
    for sequence in (1,2,3):
        wall=1.12+sequence*.01
        c.port._head_samples.append(dict(sequence=10+sequence,source_ns=round(wall*1e9),
            wall_s=wall,positions=[target],velocities=[0.],valid=True))
        c.clock[0]=wall+.001;assert c.search.tick() is None
    for sequence in (3,4,5):
        c.rows.append(exposure(sequence,q=target));c.clock[0]=c.rows[-1]['image_received_wall_s']+.01
        result=c.search.tick()
    assert result['status']=='TARGET_LOCKED' and len(c.sent)==1
    assert len(c.search.commands[0]['confirming_samples'])==3


def test_original_deadline_expiry_faults_before_a_search_dispatch():
    c=driver();c.rows.append(exposure(detections=[]));c.clock[0]=1.15
    with pytest.raises(PermissionError):c.search.tick()
    assert c.faults and c.sent==[]


def test_search_timeout_advances_without_waiting_for_cuda_or_a_new_frame():
    c=driver();assert c.search.tick() is None
    c.clock[0]=31.
    result=c.search.tick()
    assert result['status']=='SEARCH_TIMEOUT' and result['found'] is False
    assert c.faults and c.sent==[]


def test_transport_cannot_be_rebound_to_create_another_dispatch_owner():
    c=driver()
    with pytest.raises(PermissionError):c.search.bind_transport(object())
    assert c.faults


@pytest.mark.parametrize('damage',['rejected','aborted','error_code','callback_error'])
def test_owned_goal_failure_never_permits_a_lock(damage):
    c=driver();c.rows.append(exposure(detections=[dict(BOX,xyxy=[340.,200.,380.,280.])]))
    c.clock[0]=1.01;c.search.tick();gid=c.sent[0][0]
    state=dict(accepted=damage!='rejected',result=None)
    if damage in ('aborted','error_code'):
        state['result']=SimpleNamespace(status=5 if damage=='aborted' else 4,
            result=SimpleNamespace(error_code=1 if damage=='error_code' else 0))
    if damage=='callback_error':state['error']='actual callback failed'
    c.port._goals[gid]=state;c.clock[0]=1.02
    with pytest.raises(PermissionError):c.search.tick()
    assert c.faults and c.search.result is None and len(c.sent)==1
