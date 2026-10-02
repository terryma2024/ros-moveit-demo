"""The live reader binds original pixels to CPU admission and one detector call."""
from types import SimpleNamespace
import hashlib

import pytest

from test_act_head_monitor_exposure import ready, refresh
from test_act_head_monitor_prearm import completed
from test_act_head_monitor_ros import ready_monitor
from so101_demo.act.head_monitor_ipc import HeadMonitorCodec
from so101_demo.adapters.act.head_primary_supervisor import HeadPrimarySupervisor
from so101_demo.adapters.act.head_monitor_process import MonitorRuntimeProtocol
from so101_demo.cli import head_feedback_bootstrap as bootstrap


def composition(tmp_path):
    cpu_node,runtime,cpu,_=ready()
    node,root,_,_=ready_monitor();events=[];faults=[];calls=[];deadlines=[]
    protocol=MonitorRuntimeProtocol(dict(epoch='attempt',generation=5,session_id='session',primary=runtime.primary),tmp_path)
    protocol._future=completed(runtime);protocol._policy_future=completed(True)
    scope=dict(secret=b'x'*32,epoch='attempt',generation=5,session_id='session')
    sender=HeadMonitorCodec(**scope,role='monitor');receiver=HeadMonitorCodec(**scope,role='primary')
    class Monitor:
        def request_runtime(self,record):
            calls.append(record)
            return receiver.decode(sender.encode(protocol.handle(record)))
    class Primary:
        epoch=runtime.epoch;primary=runtime.identity;port=root.port
        observer=root
        failed=False;ready=True
        _ack=HeadPrimarySupervisor._ack
        def dispatch_guard(self):
            if self.failed:raise PermissionError('primary revoked')
            original=root.port.original_feedback_snapshot()
            root._policy.check_joint(original['sample'],original['decision'])
        def inference_deadline(self,value):deadlines.append(value)
        def fault(self,reason,wall=None):
            self.failed=True;self.ready=False;faults.append((reason,wall))
    class Capture:
        def bind_live_sink(self,sink):self.sink=sink
    class Detector:
        count=0;resets=0;during=None
        def reset(self):self.resets+=1
        def detect(self,pixels,**identity):
            self.count+=1
            assert pixels.shape==(480,640,3) and pixels[0,0,0]==0
            assert identity==dict(session_id='session',attempt_id='attempt',source_stamp_ns=10**9,
                source_frame_id=root.camera_frame)
            if self.during:self.during()
            return [dict(xyxy=(1.,2.,3.,4.),confidence=.9,class_id=0,track_id='head-cup-0')]
    transform=SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=1,nanosec=0)),
        transform=SimpleNamespace(translation=SimpleNamespace(x=0.,y=0.,z=0.),
            rotation=SimpleNamespace(x=0.,y=0.,z=0.,w=1.)))
    class TF:
        available=True;stamp=None
        def can_transform(self,parent,frame,stamp):self.stamp=stamp.nanoseconds;return self.available
        def lookup_transform(self,*args):return transform
    capture=Capture();detector=Detector();primary=Primary();tf=TF()
    reader=bootstrap._bind_live_exposures(capture=capture,port=root.port,buffer=tf,
        detector=detector,primary=primary,monitor=Monitor(),camera_skew_s=.01,
        emit=lambda event,**fields:events.append(dict(event=event,**fields)))
    data=bytes(640*480*3)
    image=dict(cpu._camera,width=640,height=480,step=1920,encoding='rgb8',is_bigendian=0,
        payload_bytes=len(data),payload_sha256=hashlib.sha256(data).hexdigest())
    info=dict(cpu._infos[10**9])
    def originals():
        capture.sink('INFO',info,payload=None);capture.sink('IMAGE',image,payload=data)
    return SimpleNamespace(reader=reader,node=node,root=root,cpu_node=cpu_node,runtime=runtime,cpu=cpu,
        detector=detector,primary=primary,tf=tf,transform=transform,capture=capture,events=events,
        calls=calls,deadlines=deadlines,faults=faults,originals=originals,image=image,info=info,data=data)


def retire(c):c.root.close(timeout_s=1.);c.cpu.close(timeout_s=1.)


def test_actual_cpu_protocol_pairs_original_pixels_and_one_detector_call(tmp_path):
    c=composition(tmp_path)
    try:
        assert c.detector.resets==1 and c.reader.infer() is None
        c.originals();row=c.reader.infer()
        assert row['completion_ack']['exposure_finished'] is True
        assert row['admission_ack']['exposure_admitted'] is True
        assert row['payload_sha256']==c.image['payload_sha256'] and c.tf.stamp==10**9
        assert c.detector.count==1 and c.reader.infer() is None
        assert [r['operation'] for r in c.calls]==['EXPOSURE_ADMIT','EXPOSURE_FINISH']
        assert c.deadlines==[10.05,10.05,None] and not c.faults
        assert row['detections'][0]['xyxy']==[1.,2.,3.,4.]
        assert len(c.reader.results)==1
    finally:retire(c)


def test_tf_wait_keeps_original_source_and_receipt_until_it_can_be_admitted(tmp_path):
    c=composition(tmp_path)
    try:
        c.originals();c.tf.available=False
        assert c.reader.infer() is None and not c.calls and not c.deadlines
        c.tf.available=True;row=c.reader.infer()
        assert row['image_received_wall_s']==10. and row['source_ns']==10**9
        assert c.detector.count==1
    finally:retire(c)


@pytest.mark.parametrize('damage',['tf_future','tf_skew','tf_invalid','payload','info_missing','root_fault'])
def test_invalid_live_original_cannot_enter_cuda(tmp_path,damage):
    c=composition(tmp_path)
    try:
        if damage=='tf_future':c.transform.header.stamp.nanosec=1
        elif damage=='tf_skew':c.transform.header.stamp.sec=0;c.transform.header.stamp.nanosec=989_999_999
        elif damage=='tf_invalid':c.transform.transform.rotation.w=0.
        elif damage=='payload':c.image['payload_sha256']='f'*64
        elif damage=='root_fault':c.primary.failed=True
        if damage=='info_missing':c.capture.sink('IMAGE',c.image,payload=c.data)
        else:
            if damage=='payload':
                with pytest.raises((ValueError,PermissionError)):c.originals()
                assert c.detector.count==0 and c.primary.failed
                return
            c.originals()
        if damage=='info_missing':
            assert c.reader.infer() is None and not c.calls
        else:
            with pytest.raises((ValueError,PermissionError)):c.reader.infer()
            assert c.primary.failed
        assert c.detector.count==0
    finally:retire(c)


@pytest.mark.parametrize('damage',['root_revoke','late_cuda','foreign_result'])
def test_result_after_cuda_cannot_escape_original_context_and_deadline(tmp_path,damage):
    c=composition(tmp_path)
    try:
        c.originals()
        if damage=='root_revoke':c.detector.during=lambda:setattr(c.primary,'failed',True)
        elif damage=='late_cuda':
            def late():
                c.node.wall=10.051;refresh(c.cpu_node,c.runtime,c.cpu,10.051)
            c.detector.during=late
        else:c.detector.during=lambda:c.runtime.fault('owned CPU revoke',10.)
        with pytest.raises((ValueError,PermissionError)):c.reader.infer()
        assert c.detector.count==1 and not c.reader.results and c.primary.failed
        assert c.deadlines[-1] is not None
    finally:retire(c)


def test_reader_retirement_consumes_pending_and_prevents_late_cuda(tmp_path):
    c=composition(tmp_path)
    try:
        c.originals();proof=c.reader.close()
        assert proof['retired'] and proof['inference_calls']==0
        with pytest.raises(PermissionError):c.reader.infer()
        assert c.detector.count==0
    finally:retire(c)


def test_reentrant_inference_cannot_clear_the_owned_call_in_progress(tmp_path):
    c=composition(tmp_path)
    try:
        c.originals()
        def nested():
            with pytest.raises(PermissionError):c.reader.infer()
            assert c.reader._busy
        c.detector.during=nested
        with pytest.raises(PermissionError):c.reader.infer()
        assert c.detector.count==1 and not c.reader.results
    finally:retire(c)


def test_pending_info_cannot_extend_original_frame_deadline(tmp_path):
    c=composition(tmp_path)
    try:
        c.capture.sink('IMAGE',c.image,payload=c.data)
        assert c.reader.infer() is None
        c.node.wall=10.051
        with pytest.raises(PermissionError):c.reader.infer()
        assert c.detector.count==0 and c.faults[0][1]==pytest.approx(10.05)
    finally:retire(c)


def test_before_admission_replacement_is_audited_with_original_receipt(tmp_path):
    c=composition(tmp_path)
    try:
        c.originals()
        c.capture.sink('IMAGE',dict(c.image,source_ns=1_001_000_000,wall_s=10.001),payload=c.data)
        drop=next(row for row in c.events if row['event']=='LIVE_EXPOSURE_DROPPED_BEFORE_ADMISSION')
        assert drop['original']['source_ns']==10**9 and drop['original']['wall_s']==10.
        assert drop['replacing_source_ns']==1_001_000_000 and not c.calls
    finally:retire(c)


def test_primary_clock_must_catch_original_header_before_claim_not_be_restamped(tmp_path):
    c=composition(tmp_path)
    try:
        c.originals();c.node.sim=.999
        c.root.port._head_feedback['source_ns']=999_000_000
        assert c.reader.infer() is None and not c.calls and not c.deadlines
        c.node.sim=1.;c.root.port._head_feedback['source_ns']=10**9
        row=c.reader.infer()
        assert row['source_ns']==10**9 and row['image_received_wall_s']==10.
    finally:retire(c)
