"""Actual full-scene state cannot be replaced with nominal free-body positions."""
import copy
import pytest
from so101_demo.adapters.act.scene_state import SceneStateObserver


def observer():
    now=[10.]
    port=SceneStateObserver(model_sha256='1'*64,nq=14,nv=12,max_age_s=.15,monotonic=lambda:now[0])
    port.reset('s',2,source_floor_s=1.)
    return port,now


def frame():
    return dict(simulation_session_id='s',reset_epoch=2,simulation_step=5,paused=False,
        simulation_time_s=1.01,model_sha256='1'*64,qpos=[.2]*14,qvel=[.3]*12)


def test_all_dynamic_coordinates_survive_and_caller_cannot_mutate_evidence():
    port,now=observer();value=frame();value['qpos'][-1]=.7
    assert port.accept(value)
    value['qpos'][-1]=999
    read=port.snapshot();assert read['qpos'][-1]==.7
    read['qpos'][-1]=998;assert port.snapshot()['qpos'][-1]==.7
    now[0]+=.151
    with pytest.raises(ValueError,match='SCENE_STATE_STALE'):port.snapshot()


@pytest.mark.parametrize('changes',[
    {'model_sha256':'2'*64},{'simulation_session_id':'foreign'}, {'reset_epoch':3},
    {'qpos':[.2]*13},{'qvel':[.3]*11},{'qpos':[float('nan')]*14},
    {'paused':1},{'simulation_step':True},{'simulation_time_s':.99},{'extra':'truth'},
])
def test_invalid_or_unknown_actual_scene_latches_until_new_explicit_reset(changes):
    port,now=observer();value=frame();value.update(changes)
    assert not port.accept(value) and port.hazard
    assert not port.accept(frame())
    with pytest.raises(ValueError):port.snapshot()
    with pytest.raises(ValueError):port.reset('s',2,source_floor_s=1.02)
    port.reset('s',3,source_floor_s=1.02)
    value=frame();value.update(reset_epoch=3,simulation_time_s=1.03)
    assert port.accept(value) and port.snapshot()['reset_epoch']==3


def test_only_proven_old_reset_frames_before_first_current_sample_are_discarded():
    port,now=observer();old=frame();old.update(reset_epoch=1,simulation_time_s=.99)
    assert not port.accept(old) and not port.hazard
    assert port.accept(frame())
    assert not port.accept(old) and port.hazard


def test_reordered_sample_or_unknown_future_receipt_time_cannot_be_used():
    port,now=observer();assert port.accept(frame())
    old=frame();old.update(simulation_step=4,simulation_time_s=1.008)
    assert not port.accept(old) and port.hazard
    port,now=observer();assert port.accept(frame());now[0]-=.001
    with pytest.raises(ValueError,match='SCENE_STATE_STALE'):port.snapshot()


def adapter(port,proof,events):
    from so101_demo.adapters.act.scene_state import RosSceneStateAdapter
    class Node:
        def create_subscription(self,*args):return None
    return RosSceneStateAdapter(Node(),port,on_hazard=events.append,pending_reset_port=proof)


def message(value):
    from so101_mujoco_support.msg import SceneStateEvidence
    value=copy.deepcopy(value);stamp=value.pop('simulation_time_s')
    out=SceneStateEvidence(**value);out.header.stamp.sec=int(stamp)
    out.header.stamp.nanosec=round((stamp-int(stamp))*1e9)
    return out


def test_only_authorized_pending_paused_reset_is_buffered_until_atomic_reset_arm():
    from types import SimpleNamespace
    port,now=observer();assert port.accept(frame());events=[]
    proof=lambda f:f['reset_epoch']==3 and f['paused'] and f['simulation_step']==0
    ros=adapter(port,proof,events)
    future=frame();future.update(reset_epoch=3,paused=True,simulation_step=0,simulation_time_s=1.02)
    ros.accept_message(message(future))
    assert not events and port.snapshot()['reset_epoch']==2
    latest=dict(future,paused=False,simulation_step=5,simulation_time_s=1.03)
    ros.accept_message(message(latest));assert not events
    ros.arm(SimpleNamespace(simulation_session_id='s',reset_epoch=3,simulation_time_s=1.02,
        simulation_step=0,paused=True))
    assert port.snapshot()['reset_epoch']==3 and port.snapshot()['simulation_step']==5


@pytest.mark.parametrize('changes',[{}, {'model_sha256':'2'*64},{'simulation_step':1},{'paused':False}])
def test_unproven_future_scene_or_invalid_reset_shape_is_stopped_once(changes):
    port,now=observer();assert port.accept(frame());events=[]
    ros=adapter(port,lambda f:False,events)
    future=frame();future.update(reset_epoch=3,paused=True,simulation_step=0,simulation_time_s=1.02);future.update(changes)
    ros.accept_message(message(future));ros.accept_message(message(future))
    assert port.hazard and len(events)==1


def test_cached_reset_scene_cannot_arm_against_a_different_atomic_reset_floor():
    from types import SimpleNamespace
    port,now=observer();events=[];ros=adapter(port,lambda f:True,events)
    future=frame();future.update(reset_epoch=3,paused=True,simulation_step=0,simulation_time_s=1.02)
    ros.accept_message(message(future))
    ros.arm(SimpleNamespace(simulation_session_id='s',reset_epoch=3,simulation_time_s=1.025,
        simulation_step=0,paused=True))
    assert len(events)==1 and port.hazard=='SCENE_RESET_FLOOR_INVALID'
