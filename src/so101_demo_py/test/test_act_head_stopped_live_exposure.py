"""Actual live/CPU protocol on controlled originals; no physical/CUDA proof."""
from copy import deepcopy
import threading
import time
import pytest

from test_act_head_live_exposure import composition,retire
from test_act_head_monitor_ros import refresh_simulation_inputs
from so101_demo.act.head_monitor import digest
from test_act_head_monitor_ipc import server,runtime_process_for_wire


def stopped(tmp_path):
    c=composition(tmp_path,simulation=True)
    c.reader.activate()
    c.request=dict(schema_version=1,epoch='attempt',generation=5,session_id='session',policy_sha256='a'*64,
        simulation_policy_sha256=digest(c.runtime._simulation_policy.readback()),motion_epoch=0,
        observation_sequence=1,settled_source_floor_ns=1_000_000_000,settled_wall_s=10.,
        requested_wall_s=10.,search_deadline_ns=40_000_000_000)
    for observer in (c.cpu,c.root):
        observer.port._head_samples.clear()
        for seq,source,wall in ((2,1_002_000_000,10.002),(3,1_004_000_000,10.004),(4,1_006_000_000,10.006)):
            observer.port._head_samples.append(dict(sequence=seq,source_ns=source,wall_s=wall,
                valid=True,positions=[0.],velocities=[0.]))
        observer.port._head_sequence=4
    advance(c,10.01,1.01)
    c.image=dict(c.image,**deepcopy(c.root._camera));c.info=deepcopy(c.root._infos[1_010_000_000])
    c.detector.expected_source_ns=1_010_000_000
    c.transform.header.stamp.nanosec=10_000_000
    c.capture.sink('INFO',c.info,payload=None);c.capture.sink('IMAGE',c.image,payload=c.data)
    return c


def advance(c,wall,sim):
    for node,observer in ((c.node,c.root),(c.cpu_node,c.cpu)):
        node.wall=wall;node.sim=sim;refresh_simulation_inputs(node,observer)
        observer.poll()
    c.runtime._watchdog_wall=wall


def test_stopped_live_without_request_cannot_call_model_or_cpu_admission(tmp_path):
    c=stopped(tmp_path)
    try:
        with pytest.raises(PermissionError):c.reader.infer()
        assert c.detector.count==0 and not c.calls and c.primary.failed
    finally:retire(c)


def test_stopped_live_new_image_uses_actual_cpu_v2_and_original_job_clock(tmp_path):
    c=stopped(tmp_path)
    try:
        row=c.reader.infer(observation_request=c.request)
        assert row['observation_outcome']=='VALID' and row['observation_sequence']==row['sequence']==1
        assert row['motion_epoch']==0 and row['source_ns']==1_010_000_000 and c.detector.count==1
        assert row['deadline_ns']==10_160_000_000 and row['job_deadline_ns']==11_010_000_000
        assert row['job_started_wall_s']==row['cuda_started_wall_s']==10.01
        assert row['observation_request']==c.request and row['admission_ack']['root_claim']['schema_version']==2
        assert row['completion_ack']['observation_outcome']=='VALID' and c.runtime._exposures._active is None
        assert c.deadlines[0]==pytest.approx(11.01,abs=1e-12) and c.deadlines[1] is None
        assert not c.primary.failed and not c.runtime.revoked
        assert c.reader.next_completed_observation(0)==row
    finally:retire(c)


@pytest.mark.parametrize('field,value',[('generation',6),('motion_epoch',1),('policy_sha256','b'*64),
    ('simulation_policy_sha256','c'*64),('observation_sequence',True),('search_deadline_ns',41_000_000_000)])
def test_stopped_live_request_damage_refuses_before_any_model_or_admission(tmp_path,field,value):
    c=stopped(tmp_path);c.request[field]=value
    try:
        with pytest.raises((PermissionError,ValueError)):c.reader.infer(observation_request=c.request)
        assert c.detector.count==0 and not c.calls and c.primary.failed
    finally:retire(c)


def test_stopped_live_pre_request_image_is_not_new_and_cannot_call_model(tmp_path):
    c=stopped(tmp_path);c.request['requested_wall_s']=10.01
    try:
        assert c.reader.infer(observation_request=c.request) is None
        assert c.detector.count==0 and not c.calls and not c.primary.failed
    finally:retire(c)


def test_stopped_live_wait_for_independent_quiet_proof_keeps_original_claim_and_job_cap(tmp_path):
    c=stopped(tmp_path);proof=deepcopy(list(c.cpu.port._head_samples));c.cpu.port._head_samples.clear()
    c.cpu.port._head_samples.append(proof[-1])
    try:
        assert c.reader.infer(observation_request=c.request) is None
        first=deepcopy(c.calls[0]['exposure']);assert not c.deadlines and c.detector.count==0
        advance(c,10.03,1.03);latest=deepcopy(c.cpu.port._head_samples[-1])
        c.cpu.port._head_samples.clear();c.cpu.port._head_samples.extend(proof+[latest])
        row=c.reader.infer(observation_request=c.request)
        assert c.calls[1]['exposure']==first and row['job_started_wall_s']==10.01
        assert row['cuda_started_wall_s']==10.03 and row['job_deadline_ns']==11_010_000_000
        assert c.detector.count==1 and row['observation_outcome']=='VALID'
    finally:retire(c)


def test_stopped_live_expired_image_finishes_original_job_and_returns_discard_without_fault(tmp_path):
    c=stopped(tmp_path)
    def delayed():
        advance(c,10.2,1.2)
        assert c.runtime._exposures._active is not None
        assert c.runtime._exposures._active['job_deadline_ns']==11_010_000_000
        c.runtime._exposures.poll(c.cpu_node.wall)
        assert c.runtime._exposures._active is not None and not c.runtime.revoked
    c.detector.during=delayed
    try:
        row=c.reader.infer(observation_request=c.request)
        assert row['observation_outcome']=='EXPIRED' and row['detections']==[] and c.detector.count==1
        assert row['discarded_detections'][0]['track_id']=='head-cup-0'
        assert row['deadline_ns']==10_160_000_000 and row['job_deadline_ns']==11_010_000_000
        assert row['completion_wall_s']==10.2 and row['completion_ack']['observation_outcome']=='EXPIRED'
        assert c.runtime._exposures._active is None and c.deadlines[1] is None
        assert c.deadlines[0]==pytest.approx(11.01,abs=1e-12)
        assert not c.primary.failed and not c.runtime.revoked
    finally:retire(c)


def test_stopped_live_original_job_expiry_faults_without_fabricated_completion(tmp_path):
    c=stopped(tmp_path);c.detector.during=lambda:advance(c,11.01,2.01)
    try:
        with pytest.raises(PermissionError):c.reader.infer(observation_request=c.request)
        assert c.detector.count==1 and not c.reader.results and c.primary.failed
        assert c.runtime._exposures._active is not None and 'EXPOSURE_FINISH' not in [r['operation'] for r in c.calls]
        assert len(c.deadlines)==1 and c.deadlines[0]==pytest.approx(11.01,abs=1e-12)
        assert any(wall==pytest.approx(11.01,abs=1e-12) for _,wall in c.faults if wall is not None)
    finally:retire(c)


def test_stopped_live_expired_admission_returns_one_observation_without_cuda_sequence(tmp_path):
    c=stopped(tmp_path);request=c.reader.monitor.request_runtime
    def delayed(record,*,trace=None):
        if record['operation']=='EXPOSURE_ADMIT':advance(c,10.17,1.17)
        return request(record,trace=trace)
    c.reader.monitor.request_runtime=delayed
    try:
        row=c.reader.infer(observation_request=c.request)
        assert row['observation_outcome']=='EXPIRED' and row['observation_sequence']==1 and row['sequence'] is None
        assert c.detector.count==0 and c.reader._sequence==0 and not c.deadlines and c.runtime._exposures._active is None
        assert c.runtime._exposures._observation_sequence==1 and not c.primary.failed
    finally:retire(c)


def test_stopped_live_current_root_motion_cannot_be_hidden_by_cpu_quiet_proof(tmp_path):
    c=stopped(tmp_path);c.root.port._head_feedback['velocities']=[.01]
    try:
        assert c.reader.infer(observation_request=c.request) is None
        assert not c.calls and c.detector.count==0 and not c.deadlines
    finally:retire(c)


def test_stopped_live_replaying_a_completed_request_is_not_another_inference(tmp_path):
    c=stopped(tmp_path)
    try:
        c.reader.infer(observation_request=c.request)
        with pytest.raises(PermissionError):c.reader.infer(observation_request=c.request)
        assert c.detector.count==1 and len(c.reader.results)==1
    finally:retire(c)


def test_stopped_live_image_expiring_during_admission_reply_is_completed_without_starting_cuda(tmp_path):
    c=stopped(tmp_path);original=c.reader.monitor.request_runtime
    def delayed(record,*,trace=None):
        reply=original(record,trace=trace)
        if record['operation']=='EXPOSURE_ADMIT':advance(c,10.17,1.17)
        return reply
    c.reader.monitor.request_runtime=delayed
    try:
        row=c.reader.infer(observation_request=c.request)
        assert row['observation_outcome']=='EXPIRED' and row['inference_performed'] is False
        assert row['cuda_started_wall_s'] is None and c.detector.count==0
        assert c.runtime._exposures._active is None and not c.primary.failed
        assert row['completion_ack']['exposure_finished'] is True
    finally:retire(c)


def test_stopped_live_root_motion_after_cpu_admission_blocks_cuda_and_revokes(tmp_path):
    c=stopped(tmp_path);original=c.reader.monitor.request_runtime
    def moved(record,*,trace=None):
        reply=original(record,trace=trace)
        if record['operation']=='EXPOSURE_ADMIT':c.root.port._head_feedback['velocities']=[.01]
        return reply
    c.reader.monitor.request_runtime=moved
    try:
        with pytest.raises(PermissionError):c.reader.infer(observation_request=c.request)
        assert c.detector.count==0 and not c.reader.results and c.primary.failed
        assert c.runtime._exposures._active is not None
    finally:retire(c)


def test_stopped_live_sim_time_advance_at_handoff_discards_without_assuming_rtf_one(tmp_path):
    c=stopped(tmp_path);original=c.reader.emit
    def progressed(event,**fields):
        original(event,**fields)
        if event=='LIVE_STOPPED_OBSERVATION_FINISHED':advance(c,10.02,1.22)
    c.reader.emit=progressed
    try:
        row=c.reader.infer(observation_request=c.request)
        assert row['observation_outcome']=='EXPIRED' and row['detections']==[]
        assert row['handoff_decision']['sim_ns']==1_220_000_000
        assert c.detector.count==1 and not c.primary.failed
    finally:retire(c)


def test_stopped_live_discard_ack_cannot_hide_future_observation_clock(tmp_path):
    c=stopped(tmp_path);original=c.reader.monitor.request_runtime
    def damaged(record,*,trace=None):
        if record['operation']=='EXPOSURE_INPUTS':advance(c,10.17,1.17)
        reply=original(record,trace=trace);reply['observed_wall_s']=11.
        return reply
    c.reader.monitor.request_runtime=damaged
    try:
        with pytest.raises(PermissionError):c.reader.infer(observation_request=c.request)
        assert c.detector.count==0 and not c.reader.results and c.primary.failed
    finally:retire(c)


@pytest.mark.parametrize('server',[{'mode':'fragment','operation':'EXPOSURE_INPUTS'}],indirect=True)
def test_stopped_live_rpc_finishes_original_real_unix_frame_without_resend(tmp_path,server):
    c=stopped(tmp_path);connection,peer,child=server
    monitor,channel=runtime_process_for_wire(connection,peer,child)
    c.reader.monitor=monitor;c.reader.monotonic=time.monotonic
    released=threading.Event()
    def release():
        deadline=time.monotonic()+1.
        while time.monotonic()<deadline and not monitor.runtime_pending:released.wait(.001)
        if monitor.runtime_pending:
            child.stdin.write(b'\n');child.stdin.flush();released.set()
    worker=threading.Thread(target=release,daemon=False);worker.start()
    try:
        reply,trace=c.reader._stopped_rpc(dict(operation='EXPOSURE_INPUTS'),round((time.monotonic()+.5)*1e9))
        assert released.is_set() and reply['stage']=='PRESENT' and reply['motion_authority'] is False
        assert channel._codec.sequence==1 and not monitor.runtime_pending
        assert len(trace['attempts'])==1 and trace['attempts'][0]['error_type']=='TimeoutError'
        assert trace['attempts'][0]['recovery']['completed_wall_s']<=trace['received_wall_s']
        assert c.detector.count==0 and not c.reader.results  # Wire receipt grants no frame authority.
    finally:
        worker.join(1.);channel.close();retire(c)


def test_stopped_live_detector_failure_retains_original_attempt_and_cuda_clock(tmp_path):
    c=stopped(tmp_path)
    def fail():raise RuntimeError('controlled detector failure')
    c.detector.during=fail
    try:
        with pytest.raises(RuntimeError):c.reader.infer(observation_request=c.request)
        attempts=c.reader.close()['original_attempts']
        assert attempts[-1]['observation_sequence']==1 and attempts[-1]['job_deadline_ns']==11_010_000_000
        assert attempts[-1]['phases']['cuda_started']==10.01 and attempts[-1]['outcome']=='REFUSED'
        assert c.detector.count==1 and c.runtime._exposures._active is not None and not c.reader.results
    finally:retire(c)
