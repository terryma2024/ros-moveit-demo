"""The Head UI contract shares the formal owner and cannot fabricate targets or Stop."""
import copy
import threading
import uuid

import pytest

from test_act_head_execution_composition import bound_composition


def make_bridge(monkeypatch, tmp_path):
    from so101_demo.adapters.act.head_execution_owner_bridge import HeadExecutionOwnerBridge
    composition, inputs, stack = bound_composition(monkeypatch, tmp_path)
    stack.search.controller.config['required_search_domain_rad'] = [-.17, .08]
    stack.search.controller.config['lock_valid_neck_rad'] = [-.3, .3]
    stack.node.get_fully_qualified_name = lambda: '/controlled_head_owner'
    bridge = HeadExecutionOwnerBridge(composition)
    return bridge, composition, inputs, stack


def finish(composition, stack):
    stack.runtime.close(timeout_s=1.)
    composition.seal({'execution': 'FAILED', 'controlled_fixture': True})


def test_bridge_descriptor_reuses_all_bound_resources_and_stays_unqualified(monkeypatch, tmp_path):
    bridge, composition, inputs, stack = make_bridge(monkeypatch, tmp_path)
    try:
        descriptor = bridge.descriptor()
        assert descriptor['operation'] == 'HEAD_FILE_STAGE1_DEVELOPMENT'
        assert descriptor['execution_scope'] == 'MUJOCO_DEVELOPMENT_UNQUALIFIED'
        assert descriptor['qualification_status'] == 'NOT_QUALIFIED'
        assert descriptor['execution_inputs_sha256'] == inputs.document_sha256
        assert descriptor['run'] == inputs.run
        assert bridge.runtime is stack.runtime
        assert bridge.inference_owner is stack.owner
        assert bridge.search is stack.search
        assert bridge.port is stack.port
        assert descriptor['resource_ids']['writer'] == id(composition.writer)
        descriptor['run']['epoch'] = 'changed'
        assert bridge.descriptor()['run']['epoch'] == inputs.run['epoch']
    finally:
        finish(composition, stack)


def test_bridge_target_delegates_only_declared_initial_move_to_search(monkeypatch, tmp_path):
    bridge, composition, _, stack = make_bridge(monkeypatch, tmp_path)
    calls = []
    goal_uuid = str(uuid.uuid4())
    monkeypatch.setattr(stack.search, 'begin_development_move', lambda target: calls.append(target) or goal_uuid)
    try:
        with pytest.raises(PermissionError, match='HEAD_BRIDGE_TARGET_REFUSED'):
            bridge.submit_target(.01)
        assert calls == []
        result = bridge.submit_target(-.17)
        assert calls == [-.17]
        assert result['goal_uuid'] == goal_uuid
        with pytest.raises(PermissionError, match='HEAD_BRIDGE_TARGET_REFUSED'):
            bridge.submit_target(-.17)
        assert calls == [-.17]
    finally:
        finish(composition, stack)


def test_bridge_foreign_thread_cannot_dispatch_on_owner(monkeypatch, tmp_path):
    bridge, composition, _, stack = make_bridge(monkeypatch, tmp_path)
    calls, errors = [], []
    monkeypatch.setattr(stack.search, 'begin_development_move', lambda target: calls.append(target))
    def foreign_call():
        try:
            bridge.submit_target(-.17)
        except PermissionError as error:
            errors.append(str(error))
    thread = threading.Thread(target=foreign_call)
    try:
        thread.start(); thread.join(timeout=1.)
        assert not thread.is_alive() and errors
        assert calls == []
    finally:
        finish(composition, stack)


@pytest.mark.parametrize('goal_uuid', [None, '', 'not-an-original-uuid'])
def test_bridge_cannot_report_submitted_without_an_original_goal_uuid(monkeypatch, tmp_path, goal_uuid):
    bridge, composition, _, stack = make_bridge(monkeypatch, tmp_path)
    monkeypatch.setattr(stack.search, 'begin_development_move', lambda target: goal_uuid)
    faults = []
    monkeypatch.setattr(stack.runtime, 'fault', lambda reason: faults.append(reason))
    try:
        with pytest.raises(PermissionError, match='HEAD_BRIDGE_GOAL_UUID_INVALID'):
            bridge.submit_target(-.17)
        assert faults == ['HEAD_BRIDGE_GOAL_UUID_INVALID']
        with pytest.raises(PermissionError, match='HEAD_BRIDGE_TARGET_REFUSED'):
            bridge.submit_target(-.17)
    finally:
        finish(composition, stack)


def test_bridge_stop_calls_runtime_without_counting_caller_samples(monkeypatch, tmp_path):
    bridge, composition, _, stack = make_bridge(monkeypatch, tmp_path)
    calls = []
    receipt = dict(physical_stop_confirmed=False, native_close={'ack': True}, cancel_stop={})
    monkeypatch.setattr(stack.runtime, 'stop', lambda origin, evidence: calls.append((origin, evidence)) or copy.deepcopy(receipt))
    monkeypatch.setattr(stack.runtime, 'stop_receipt', lambda: copy.deepcopy(receipt))
    try:
        result = bridge.stop()
        assert len(calls) == 1 and calls[0][0] == 'signal'
        assert result['state'] == 'STOPPING'
        assert result['physical_stop_confirmed'] is False
        receipt['physical_stop_confirmed'] = True
        assert bridge.stop_status()['state'] == 'STOPPED'
    finally:
        finish(composition, stack)


def test_teleop_consumes_exact_owner_bridge_without_detector_factory(monkeypatch, tmp_path):
    import json
    from so101_teleop.head_camera import CONNECTION_ENV, compose_head_camera
    bridge, composition, _, stack = make_bridge(monkeypatch, tmp_path)
    path = tmp_path/'connection.json'
    path.write_text(json.dumps(bridge.descriptor()))
    calls = []
    try:
        backend = compose_head_camera({CONNECTION_ENV: str(path)}, execution_owner=bridge,
                                      detector_factory=lambda: calls.append('detector'))
        assert backend.execution_owner is bridge
        assert backend.qualified() is False
        assert backend.status()['detector_constructed'] == 0
        assert calls == []
        stops = []
        monkeypatch.setattr(bridge, 'stop', lambda: stops.append('stop') or {'state': 'STOPPING'})
        assert backend.stop(raw_sample={'neck_velocity_rad_s': 0., 'sim_time_s': 99.}) == {'state': 'STOPPING'}
        assert stops == ['stop']
    finally:
        finish(composition, stack)


def test_teleop_owner_descriptor_refuses_absent_or_drifted_resource(monkeypatch, tmp_path):
    import json
    from so101_teleop.head_camera import CONNECTION_ENV, CompositionBlocked, compose_head_camera
    bridge, composition, _, stack = make_bridge(monkeypatch, tmp_path)
    path = tmp_path/'connection.json'
    descriptor = bridge.descriptor()
    path.write_text(json.dumps(descriptor))
    try:
        with pytest.raises(CompositionBlocked, match='HEAD_CAMERA_OWNER_REQUIRED'):
            compose_head_camera({CONNECTION_ENV: str(path)})
        descriptor['execution_inputs_sha256'] = '0'*64
        path.write_text(json.dumps(descriptor))
        with pytest.raises(CompositionBlocked, match='HEAD_CAMERA_CONNECTION_MISMATCH'):
            compose_head_camera({CONNECTION_ENV: str(path)}, execution_owner=bridge)
    finally:
        finish(composition, stack)
