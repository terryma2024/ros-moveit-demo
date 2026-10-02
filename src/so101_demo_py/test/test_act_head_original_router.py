"""Bind the shared primary to callbacks, preserving the original stream."""
import pytest
from test_act_head_primary_observer import shared
from test_act_head_stopped_capture import image,info
from test_act_head_feedback_freshness import sample
from so101_demo.adapters.act.head_stopped_capture import StoppedHeadCapture

try:
    from so101_demo.adapters.act.head_original_router import HeadOriginalRouter
except ModuleNotFoundError:
    class HeadOriginalRouter:
        def __init__(self,port,sink):self.sink=sink
        def __call__(self,kind,record):self.sink(kind,record)
        def bind_primary(self,primary):pass
        def retire(self):pass


def setup():
    node,port,primary,events,faults=shared();originals=[]
    router=HeadOriginalRouter(port,lambda kind,row:originals.append((kind,row)))
    port.bind_head_original_sink(router)
    capture=StoppedHeadCapture(node,port,frame_id='head_camera_frame',monotonic=lambda:node.wall)
    capture.bind_original_sink(router)
    return node,port,primary,capture,router,events,faults,originals


def test_actual_original_callbacks_feed_shared_primary_after_the_one_binding():
    node,port,primary,capture,router,events,faults,originals=setup()
    try:
        router.bind_primary(primary)
        capture._image(image());capture._info(info())
        from rosgraph_msgs.msg import Clock
        msg=Clock();msg.clock.sec=1;capture._clock(msg)
        port._feedback(sample(1.01))
        assert primary._clock['wall_s']==10. and primary._clock['source_ns']==1_000_000_000
        assert primary._images[1_000_000_000]['wall_s']==10.
        assert primary._infos[1_000_000_000]['wall_s']==10.
        assert [kind for kind,_ in originals]==['IMAGE','INFO','CLOCK','JOINT']
        assert any(event=='JOINT_ORIGINAL' for event,_ in events)
        assert not faults
        assert [row[1] for row in node.subscriptions].count('/joint_states')==1
    finally:primary.close(timeout_s=1.);port.close_head_io(timeout_s=1.)


def test_invalid_original_joint_faults_before_arm_without_waiting_for_a_poll():
    _,port,primary,_,router,_,faults,originals=setup()
    try:
        router.bind_primary(primary);bad=sample(1.01);bad.velocity=[];port._feedback(bad)
        assert primary.failed and port._head_policy_binding_failed and faults
        assert originals[-1][0]=='JOINT' and originals[-1][1]['valid'] is False
        assert not primary._active
    finally:primary.close(timeout_s=1.);port.close_head_io(timeout_s=1.)


def test_router_cannot_rebind_the_original_primary():
    _,port,primary,_,router,_,faults,_=setup()
    try:
        router.bind_primary(primary)
        with pytest.raises(PermissionError):router.bind_primary(primary)
    finally:primary.close(timeout_s=1.);port.close_head_io(timeout_s=1.)


def test_retiring_live_original_input_latches_primary_before_it_disappears():
    _,port,primary,_,router,_,faults,_=setup()
    try:
        router.bind_primary(primary)
        router.retire()
        assert primary.failed and port._head_policy_binding_failed and faults
    finally:primary.close(timeout_s=1.);port.close_head_io(timeout_s=1.)


def test_retirement_fault_callback_sees_latched_admission_before_input_is_removed():
    _,port,primary,_,router,_,_,_=setup();calls=[]
    def fault(reason,wall):
        assert primary.failed and port._head_policy_binding_failed
        assert not router._closed and not router._lock.locked()
        calls.append(reason)
    primary.fault_callback=fault
    try:
        router.bind_primary(primary);router.retire()
        assert calls==['HEAD_PRIMARY_ORIGINAL_ROUTER_RETIRED']
        assert router._closed
    finally:primary.close(timeout_s=1.);port.close_head_io(timeout_s=1.)


def test_primary_binding_does_not_seed_or_replay_previous_cached_metadata():
    node,port,primary,capture,router,_,_,_=setup()
    try:
        capture._image(image());capture._info(info());capture.take_image()
        router.bind_primary(primary)
        assert primary._images=={} and primary._infos=={} and primary._clock is None
        capture._image(image(1_100_000_000));capture._info(info(1_100_000_000))
        assert set(primary._images)=={1_100_000_000} and set(primary._infos)=={1_100_000_000}
        assert len([row[1] for row in node.subscriptions if row[1]=='/head_camera/color'])==1
    finally:primary.close(timeout_s=1.);port.close_head_io(timeout_s=1.)
