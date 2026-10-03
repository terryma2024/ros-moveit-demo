"""Pre-policy CPU original measurement cannot acquire inference or motion authority."""
import hashlib

import pytest

from so101_demo.act.head_monitor import HeadMonitorEpoch
from so101_demo.adapters.act.head_monitor_process import MonitorRuntimeProtocol
from test_act_head_monitor_prearm import prepared,completed


def measurement(tmp_path):
    node,runtime,observer=prepared()
    runtime.epoch=HeadMonitorEpoch(epoch='attempt',generation=5,session_id='session')
    runtime._policy=None;observer._policy=None;observer._active=False
    observer.port._feedback_policy=None;observer.port._head_bootstrap=True
    claim=dict(epoch='attempt',generation=5,session_id='session',image_source_ns=10**9,
        info_source_ns=10**9,joint_source_ns=10**9,tf_source_ns=10**9,
        image_frame_id=observer.camera_frame,payload_sha256=hashlib.sha256(bytes(640*480*3)).hexdigest(),
        image_received_wall_s=10.,info_received_wall_s=10.)
    protocol=MonitorRuntimeProtocol(dict(epoch='attempt',generation=5,session_id='session',
        primary=runtime.primary),tmp_path)
    protocol._future=completed(runtime)
    return node,runtime,observer,claim,protocol


def test_configured_cpu_measures_both_real_originals_and_completion_without_a_lease(tmp_path):
    node,runtime,observer,claim,protocol=measurement(tmp_path)
    try:
        before=runtime._exposures.summary();polls=list(observer.watchdog_polls)
        reply=protocol.handle(dict(operation='CALIBRATION_FRAME_INPUTS',exposure=claim))
        assert reply['stage']=='CONFIGURED' and reply['inputs_ready'] is True
        assert reply['calibration_measurement'] is True and reply['motion_authority'] is False
        assert reply['original_snapshot']['image']['source_ns']==10**9
        assert reply['original_snapshot']['info']['wall_s']==10.
        done=protocol.handle(dict(operation='CALIBRATION_FRAME_COMPLETION',completion=dict(
            claim=claim,completion_wall_s=10.,result_sha256='b'*64)))
        assert done['measurement_complete'] is True and done['motion_authority'] is False
        assert done['original_snapshot']['decision']['wall_after_s']==10.
        assert runtime.epoch.stage=='PRESENT' and not runtime.epoch.inventory and runtime.epoch.sequence==0
        assert runtime._exposures.summary()==before and list(observer.watchdog_polls)==polls
        assert runtime._watchdog_wall==10. and not observer._active and runtime._policy is None
    finally:observer.close(timeout_s=1.)


def test_prepolicy_probe_waits_only_for_an_original_not_physically_received(tmp_path):
    _,runtime,observer,claim,protocol=measurement(tmp_path)
    try:
        observer._camera=None;observer._images.clear();observer._image_source=999_000_000
        reply=protocol.handle(dict(operation='CALIBRATION_FRAME_INPUTS',exposure=claim))
        assert reply['inputs_ready'] is False and reply['motion_authority'] is False
        assert not runtime.revoked and runtime._exposures.summary()['sequence']==0
    finally:observer.close(timeout_s=1.)


def test_probe_current_clock_copies_precede_decision_and_cannot_renew_progress(tmp_path,monkeypatch):
    node,runtime,observer,claim,protocol=measurement(tmp_path)
    snapshot=observer.port.original_feedback_snapshot
    def decision():
        value=snapshot()
        observer._camera['wall_s']=10.001
        observer._clock['wall_s']=10.001
        return value
    monkeypatch.setattr(observer.port,'original_feedback_snapshot',decision)
    try:
        reply=protocol.handle(dict(operation='CALIBRATION_FRAME_INPUTS',exposure=claim))
        assert reply['original_snapshot']['image']['wall_s']==10.
        assert reply['original_snapshot']['clock']['wall_s']==10.
        assert runtime._watchdog_wall==10. and runtime._exposures.summary()['active'] is None
    finally:observer.close(timeout_s=1.)


@pytest.mark.parametrize('damage',['epoch','generation','session','payload','frame','future_receipt',
    'future_header','cached_missing','invalid_image','wrong_hash','joint','moving','clock',
    'watchdog','executor','policy','active','revoked','extra','deadline','completion_future'])
def test_prepolicy_probe_refuses_bad_scope_originals_or_changed_runtime_stage(tmp_path,damage):
    node,runtime,observer,claim,protocol=measurement(tmp_path)
    try:
        if damage=='epoch':claim['epoch']='foreign'
        elif damage=='generation':claim['generation']=True
        elif damage=='session':claim['session_id']='foreign'
        elif damage=='payload':claim['payload_sha256']='bad'
        elif damage=='frame':claim['image_frame_id']='foreign'
        elif damage=='future_receipt':claim['image_received_wall_s']=10.001
        elif damage=='future_header':claim['tf_source_ns']=1_000_000_001
        elif damage=='cached_missing':observer._camera=None;observer._images.clear()
        elif damage=='invalid_image':observer._camera['valid']=False
        elif damage=='wrong_hash':observer._camera['payload_sha256']='c'*64
        elif damage=='joint':observer.port._head_feedback['valid']=False
        elif damage=='moving':observer.port._head_feedback['velocities']=(.1,)
        elif damage=='clock':observer._clock=None
        elif damage=='watchdog':runtime._watchdog_wall=9.98
        elif damage=='executor':observer._executor_wall=9.98
        elif damage=='policy':runtime._policy={'sha256':'a'*64}
        elif damage=='active':observer._active=True
        elif damage=='revoked':runtime.fault('original failure',10.)
        elif damage in ('extra','deadline'):claim[damage]=10_150_000_000
        request=dict(operation='CALIBRATION_FRAME_INPUTS',exposure=claim)
        if damage=='completion_future':request=dict(operation='CALIBRATION_FRAME_COMPLETION',
            completion=dict(claim=claim,completion_wall_s=10.001,result_sha256='b'*64))
        with pytest.raises(PermissionError):protocol.handle(request)
        assert runtime._exposures.summary()['sequence']==0 and not runtime.epoch.inventory
    finally:observer.close(timeout_s=1.)
