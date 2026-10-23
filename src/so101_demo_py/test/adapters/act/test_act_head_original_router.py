"""Bind the shared primary to callbacks, preserving the original stream."""
import pytest
from types import SimpleNamespace
from test_act_head_local_observer import observer_setup, FakeTime
from test_act_head_stopped_capture import image,info
from test_act_head_feedback_freshness import sample
from so101_demo.adapters.act.head_stopped_capture import StoppedHeadCapture

from so101_demo.adapters.act.head_original_router import HeadOriginalRouter


def _router_setup(monkeypatch):  # not `setup`: pytest 7 treats a module-level setup() as an xunit module hook
    row = observer_setup(monkeypatch, clock=FakeTime(wall=10., sim=1.),
                         camera_frame='head_camera_frame', bind_port_sink=False)
    node, port, primary = row.node, row.port, row.observer
    node.subscriptions = row.subscriptions
    clock_callback = lambda message: None
    node._time_source = SimpleNamespace(
        ros_time_is_active=True, clock_callback=clock_callback,
        _clock_sub=SimpleNamespace(callback=clock_callback, topic_name='/clock'))
    events, faults, originals = [], row.faults, []
    primary._emit = lambda event, **fields: events.append((event, fields))
    router=HeadOriginalRouter(port,lambda kind,row:originals.append((kind,row)))
    port.bind_head_original_sink(router)
    capture=StoppedHeadCapture(node,port,frame_id='head_camera_frame',monotonic=lambda:10.)
    capture.bind_original_sink(router)
    return node,port,primary,capture,router,events,faults,originals


def test_actual_original_callbacks_feed_shared_primary_after_the_one_binding(monkeypatch):
    node,port,primary,capture,router,events,faults,originals=_router_setup(monkeypatch)
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
    finally:primary.close();port.close_head_io(timeout_s=1.)


def test_invalid_original_joint_faults_before_arm_without_waiting_for_a_poll(monkeypatch):
    _,port,primary,_,router,_,faults,originals=_router_setup(monkeypatch)
    try:
        router.bind_primary(primary);bad=sample(1.01);bad.velocity=[];port._feedback(bad)
        assert primary.failed and primary.local_state.faulted and primary._closed_admission and faults
        assert originals[-1][0]=='JOINT' and originals[-1][1]['valid'] is False
        assert primary.snapshot()['outstanding'] == []
    finally:primary.close();port.close_head_io(timeout_s=1.)


def test_router_cannot_rebind_the_original_primary(monkeypatch):
    _,port,primary,_,router,_,faults,_=_router_setup(monkeypatch)
    try:
        router.bind_primary(primary)
        with pytest.raises(PermissionError):router.bind_primary(primary)
    finally:primary.close();port.close_head_io(timeout_s=1.)


def test_retiring_live_original_input_latches_primary_before_it_disappears(monkeypatch):
    _,port,primary,_,router,_,faults,_=_router_setup(monkeypatch)
    try:
        router.bind_primary(primary)
        router.retire()
        assert primary.failed and primary.local_state.faulted and primary._closed_admission and faults
    finally:primary.close();port.close_head_io(timeout_s=1.)


def test_retirement_fault_callback_sees_latched_admission_before_input_is_removed(monkeypatch):
    _,port,primary,_,router,_,_,_=_router_setup(monkeypatch);calls=[]
    def fault(reason):
        assert primary.failed and primary.local_state.faulted and primary._closed_admission
        assert not router._closed and not router._lock.locked()
        calls.append(reason)
    primary._fault_callback=fault
    try:
        router.bind_primary(primary);router.retire()
        assert calls==['HEAD_PRIMARY_ORIGINAL_ROUTER_RETIRED']
        assert router._closed
    finally:primary.close();port.close_head_io(timeout_s=1.)


def test_primary_binding_does_not_seed_or_replay_previous_cached_metadata(monkeypatch):
    node,port,primary,capture,router,_,_,_=_router_setup(monkeypatch)
    try:
        capture._image(image());capture._info(info());capture.take_image()
        router.bind_primary(primary)
        assert primary._images=={} and primary._infos=={} and primary._clock is None
        capture._image(image(1_100_000_000));capture._info(info(1_100_000_000))
        assert set(primary._images)=={1_100_000_000} and set(primary._infos)=={1_100_000_000}
        assert len([row[1] for row in node.subscriptions if row[1]=='/head_camera/color'])==1
    finally:primary.close();port.close_head_io(timeout_s=1.)
