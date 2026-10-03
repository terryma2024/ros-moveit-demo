"""Real owned CPU exec/ROS setup remains unarmed and strictly staged.

These adapter controls use a CPU-only stand-in native owner with no controller,
no CUDA, no simulator and no motion endpoint. They cannot qualify a runtime.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest

from test_act_head_monitor_process import config
from so101_demo.adapters.act.controller_reservation_provision import (
    _process_start_ticks,write_controller_reservation_provision,write_head_primary_fault_provision)
from so101_demo.adapters.act.head_monitor_process import start_monitor


@pytest.fixture
def runtime_setup(config,tmp_path):
    owner=subprocess.Popen([sys.executable,'-c','import sys;sys.stdin.read()'],stdin=subprocess.PIPE)
    monitor=None
    try:
        native=dict(uid=os.geteuid(),pid=owner.pid,start_ticks=_process_start_ticks(owner.pid))
        directory=config['ipc_directory']
        write_controller_reservation_provision(directory/'neck.provision',role='neck',session_id=config['session_id'])
        write_head_primary_fault_provision(directory/'neck-primary-revoke.provision',session_id=config['session_id'],
            native_owner=native,socket_path=directory/'neck-primary-revoke.sock')
        evidence=Path('/data/work/so101-evidence/act-data/20260930-antzb-head-search-krIv681m')
        sources={
            'weights':evidence/'head-yolo-models-20260930T120608Z/candidate-c2a/head-task-mixed-taskweighted/weights/best.pt',
            'geometry':evidence/'head-camera-probe11-20260930T101722Z/head-camera-geometry.json',
            'candidate':tmp_path/'candidate-reference.json',
            'runtime_manifest':tmp_path/'runtime-manifest-reference.json'}
        # Explicit test references, not the actual sealed candidate/runtime.
        sources['candidate'].write_text('{"test_reference_only":true}\n')
        sources['runtime_manifest'].write_text('{"test_reference_only":true}\n')
        for path in sources.values():assert path.is_file()
        dependencies={key:dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                      for key,path in sources.items()}
        environment=dict(config['environment'],ROS_DOMAIN_ID=str(130+int(uuid.uuid4().hex[:4],16)%90))
        monitor=start_monitor(**dict(config,environment=environment))
        configuration=dict(native_owner=native,reservation_directory=str(directory),journal_path=str(tmp_path/'monitor-journal.jsonl'),
            dependencies=dependencies,purpose='calibration',observer=dict(stop_velocity_rad_s=.002,stop_latency_s=.07,
                camera_max_age_s=.05,camera_frame_id='head_camera_optical_frame'))
        yield monitor,configuration,config
    finally:
        if monitor is not None:monitor.close()
        if owner.poll() is None:owner.stdin.close();owner.wait(timeout=2.)


def configured(monitor,configuration):
    reply=monitor.request_runtime({'operation':'CONFIGURE','configuration':configuration})
    assert reply['stage']=='CONFIGURE_PENDING'
    reply=monitor.await_runtime(phase='configuration',timeout_s=5.)
    assert reply['stage']=='CONFIGURED'
    return reply


def test_owned_cpu_configure_publishes_only_scoped_presence_without_motion(runtime_setup):
    monitor,configuration,config=runtime_setup
    reply=configured(monitor,configuration)
    assert reply['motion_authority'] is False and reply['purpose']=='calibration'
    assert reply['stage']=='CONFIGURED'
    assert reply['monitor_peer']==monitor.identity
    assert reply['executor']=='SingleThreadedExecutor'
    assert reply['joint_qos']==dict(depth=5,reliability='BEST_EFFORT')
    assert reply['camera_qos']==dict(depth=32,reliability='RELIABLE')
    assert reply['clock_qos']==dict(depth=1,reliability='BEST_EFFORT')
    assert reply['clock_subscription_count']==1
    native_transport=reply['native_transport']
    assert native_transport['abi']==1 and native_transport['clock']=='CLOCK_MONOTONIC'
    assert native_transport['sha256']==hashlib.sha256(Path(native_transport['path']).read_bytes()).hexdigest()
    assert reply['goal_codec_warmup']['native_arm_count']==reply['goal_codec_warmup']['sdk_send_count']==0
    assert reply['goal_codec_warmup']['payload_bytes']>0
    assert reply['node_name']=='head_monitor_launch_a'
    assert set(reply['provisions'])=={'main','primary_fault','monitor_fault'}
    for provision in reply['provisions'].values():
        assert provision['sha256']==hashlib.sha256(Path(provision['path']).read_bytes()).hexdigest()
        assert 'capability' not in provision
    assert not list(config['ipc_directory'].glob('*.sock'))  # stand-in owner has no native listener
    assert 'torch' not in config['log_path'].read_text()
    monitor.close()
    seal=Path(configuration['journal_path']+'.seal.json')
    document=json.loads(seal.read_text())
    assert document['stage']=='RETIRED' and document['motion_authority'] is False
    assert document['journal_sha256']==hashlib.sha256(Path(configuration['journal_path']).read_bytes()).hexdigest()
    assert document['native_close'] is None  # unarmed presence is no fault-close ACK


@pytest.mark.parametrize('operation',[
    {'operation':'PREARM_READY','policy':{'policy_sha256':'a'*64}},
    {'operation':'ARMED_READY','identities':{}},
    {'operation':'REGISTER','inventory':{}},
    {'operation':'DISPATCH','binding':{}},
    {'operation':'EXPOSURE_INPUTS','exposure':{}},
    {'operation':'EXPOSURE_ADMIT','exposure':{}},
    {'operation':'EXPOSURE_FINISH','completion':{}},
])
def test_configured_presence_cannot_grant_prepolicy_ready_or_inventory(runtime_setup,operation):
    monitor,configuration,_=runtime_setup
    configured(monitor,configuration)
    with pytest.raises((OSError,PermissionError,RuntimeError,ValueError)):
        monitor.request_runtime(operation)
    with pytest.raises((OSError,PermissionError,RuntimeError,ValueError)):
        monitor.request_runtime({'operation':'CONFIGURATION'})


def test_modified_weights_identity_cannot_publish_configured_presence(runtime_setup):
    monitor,configuration,_=runtime_setup
    configuration['dependencies']['weights']['sha256']='f'*64
    monitor.request_runtime({'operation':'CONFIGURE','configuration':configuration})
    with pytest.raises((OSError,PermissionError,RuntimeError,ValueError)):
        monitor.await_runtime(phase='configuration',timeout_s=2.)
    assert not Path(configuration['journal_path']).exists()


def test_authenticated_unarmed_retirement_exits_cleanly(runtime_setup):
    monitor,configuration,_=runtime_setup
    monitor.request_runtime({'operation':'CONFIGURE','configuration':configuration})
    monitor.await_runtime(phase='configuration',timeout_s=2.)
    receipt=monitor.close()
    assert receipt['shutdown_ack'] is True
    assert receipt['exit_code']==0


def test_actual_owned_cpu_fault_receipt_and_retirement_do_not_invent_native_ack(runtime_setup):
    monitor,configuration,config=runtime_setup
    configured(monitor,configuration)
    wall=time.monotonic()
    ack=monitor.request_runtime(dict(operation='FAULT',fault=dict(reason='controlled primary fault',fault_wall_s=wall)))
    assert ack['stage']=='REVOKED' and ack['motion_authority'] is False
    assert ack['fault']==dict(reason='controlled primary fault',fault_wall_s=wall)
    assert ack['monitor_peer']==monitor.identity and ack['epoch']==config['epoch']
    receipt=monitor.close()
    assert receipt['shutdown_ack'] is True and receipt['exit_code']==0
    seal=json.loads(Path(configuration['journal_path']+'.seal.json').read_text())
    assert seal['stage']=='RETIRED' and seal['motion_authority'] is False
    assert seal['native_close'] is None and seal['native_close_error'] is not None
    body=Path(configuration['journal_path']).read_bytes()
    assert seal['journal_sha256']==hashlib.sha256(body).hexdigest()
    records=[json.loads(line) for line in body.splitlines()]
    notice=next(row for row in records if row['event']=='PRIMARY_FAULT_NOTICE')
    assert notice['reported_fault']==ack['fault']


def test_late_authenticated_heartbeat_after_fault_keeps_owned_retirement_available(runtime_setup):
    monitor,configuration,config=runtime_setup
    configured(monitor,configuration)
    fault=dict(reason='controlled original exposure expiry',fault_wall_s=time.monotonic())
    ack=monitor.request_runtime(dict(operation='FAULT',fault=fault))
    assert ack['stage']=='REVOKED' and ack['fault']==fault
    wall=time.monotonic()
    heartbeat=dict(wall_s=wall,executor_wall_s=wall,inference_deadline_wall_s=fault['fault_wall_s'])
    reply=monitor.request_heartbeat(lambda:heartbeat)
    assert reply['request']=='HEARTBEAT' and reply['stage']=='REVOKED'
    assert reply['heartbeat_rejected'] is True and reply['motion_authority'] is False
    assert reply['fault']==fault and reply['monitor_peer']==monitor.identity
    assert reply['epoch']==config['epoch'] and reply['generation']==config['generation']
    assert reply['session_id']==config['session_id'] and reply['purpose']=='calibration'
    receipt=monitor.close()
    assert receipt['shutdown_ack'] is True and receipt['exit_code']==0
    seal=json.loads(Path(configuration['journal_path']+'.seal.json').read_text())
    assert seal['stage']=='RETIRED' and seal['fault']==fault
    assert seal['native_close'] is None and seal['native_close_error'] is not None
    # Stand-in native owner has no listener: an owned reap cannot invent that ACK.
    assert seal['journal_sha256']==hashlib.sha256(Path(configuration['journal_path']).read_bytes()).hexdigest()
