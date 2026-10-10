"""Campaign truth attachment is sealed, opt-in and bound to actual native reset."""
import copy
import hashlib
import importlib
import json
from pathlib import Path

import pytest

from test_act_head_campaign_fixture_reset import _prepared
from test_act_head_campaign_truth_collector import _writer


class Node:
    def __init__(self):self.subscriptions=[]
    def create_subscription(self,cls,topic,callback,qos):
        self.subscriptions.append((cls,topic,callback,qos));return self.subscriptions[-1]
    def destroy_subscription(self,subscription):self.subscriptions.remove(subscription);return True


def _module():
    return importlib.import_module('so101_demo.adapters.act.head_campaign_truth_collector')


def test_absent_fixture_does_not_construct_writer_or_ros_subscriptions(tmp_path):
    from types import SimpleNamespace
    node=Node()
    assert _module().create_campaign_truth_collector(node=node,inputs=SimpleNamespace(refs={}),writer=None) is None
    assert node.subscriptions==[]


def test_attachment_matches_sealed_native_plugin_then_binds_actual_reset_once(tmp_path):
    inputs,prepared,_=_prepared(tmp_path)
    writer=_writer(tmp_path)
    node=Node();collector=None
    try:
        collector=_module().create_campaign_truth_collector(node=node,inputs=inputs,writer=writer)
        assert [row[1] for row in node.subscriptions]==['/head_campaign/paired_truth',
            '/head_camera/color','/head_camera/camera_info','/so101/simulation/physics_step_chunks']
        assert collector.recorder.native_identity is None
        truth=prepared['fixture']['truth_manifest']
        receipt=dict(paused=True,simulation_step=0,model_sha256=truth['model_sha256'],
            simulation_session_id=truth['simulation_session_id'],reset_epoch=1)
        collector.recorder.bind_reset(receipt)
        assert collector.recorder.native_identity=={
            'simulation_session_id':truth['simulation_session_id'],'reset_epoch':1}
        with pytest.raises(ValueError):collector.recorder.bind_reset(receipt)
        assert collector.recorder.failure
    finally:
        if collector is not None:assert collector.close()['closed']
        writer.finish({'execution':'TEST_ONLY'})


@pytest.mark.parametrize('damage',['logs_off','session','capture','model','render_config','truth_disabled','frame_id'])
def test_sealed_but_inconsistent_campaign_refuses_before_subscribing(tmp_path,damage):
    import yaml
    inputs,prepared,_=_prepared(tmp_path)
    if damage=='logs_off':inputs.document['event_log_enabled']=False
    elif damage in ('session','capture','model','render_config'):
        path=Path(inputs.refs['scenario_fixture']['path']);document=json.loads(path.read_text())
        key={'session':'simulation_session_id','capture':'capture_identity',
             'model':'model_sha256','render_config':'render_config_sha256'}[damage]
        document['truth_manifest'][key]='c'*64
        path.write_text(json.dumps(document));inputs.refs['scenario_fixture']['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    else:
        path=Path(inputs.refs['mujoco_plugin']['path']);document=yaml.safe_load(path.read_text())
        camera=document['/**']['ros__parameters']['mujoco_plugins']['mujoco_camera_plugin']['head_camera']
        if damage=='truth_disabled':camera['truth_enabled']=False
        else:camera['frame_name']='other_frame'
        path.write_text(yaml.safe_dump(document));inputs.refs['mujoco_plugin']['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    writer=_writer(tmp_path);node=Node()
    try:
        with pytest.raises((ValueError,PermissionError)):
            _module().create_campaign_truth_collector(node=node,inputs=inputs,writer=writer)
        assert node.subscriptions==[]
    finally:writer.finish({'execution':'TEST_ONLY'})


def test_provider_attaches_before_stack_start_and_retires_with_the_teardown(monkeypatch,tmp_path):
    import test_act_head_execution_provider as existing
    old_inputs=existing.build_inputs
    order=[]
    def campaign_inputs(*args,**kwargs):
        inputs,policy=old_inputs(*args,**kwargs)
        # Only the provider wiring seam is injected; factory validation has its
        # own real scene/CDR tests above. No dead-man helper or Stop ACK is forged.
        inputs.refs['scenario_fixture']={'path':'not_read_by_injected_factory','sha256':'a'*64}
        return inputs,policy
    monkeypatch.setattr(existing,'build_inputs',campaign_inputs)
    class Collector:
        def close(self):order.append('truth_close');return {'closed':True}
    def attach(*,node,inputs,writer):
        assert node is not None and writer is not None
        order.append('truth_attached')
        return Collector()
    monkeypatch.setattr(_module(),'create_campaign_truth_collector',attach)
    provider=existing.provider_module()
    original_assemble=provider.assemble
    def assemble(composition,inputs,*,plan):
        cls=plan['constructors']['stack']['callable']
        old_start=cls.start
        def start(stack):
            assert order==['truth_attached']
            order.append('stack_started')
            return old_start(stack)
        monkeypatch.setattr(cls,'start',start)
        handle=original_assemble(composition,inputs,plan=plan)
        seen['handle']=handle
        return handle
    seen={}
    monkeypatch.setattr(provider,'assemble',assemble)
    original_teardown=provider.teardown
    def teardown(built):
        # The fixture's explicit teardown list omits the truth stage; add the provider's own.
        if 'campaign_truth' in seen['handle'] and not any(stage=='campaign_truth' for stage,_ in built):
            built=list(built)+[('campaign_truth',seen['handle']['campaign_truth'])]
        failures=original_teardown(built)
        assert order==['truth_attached','stack_started','truth_close']
        assert any(stage=='campaign_truth' for stage,_ in built)
        return failures
    monkeypatch.setattr(provider,'teardown',teardown)
    existing.test_assemble_binds_ros_with_the_launcher_stack(monkeypatch,tmp_path)
    assert order==['truth_attached','stack_started','truth_close']
