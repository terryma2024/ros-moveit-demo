"""Closed task messages keep legacy callbacks out of the container boundary."""

import importlib
import json
import time

import pytest


def decode(document):
    ipc = importlib.import_module('so101_teleop.unified.ipc')
    parser = getattr(ipc, 'decode_container_task', None)
    assert callable(parser), 'four-operation task decoder is missing'
    return parser(json.dumps(document).encode() + b'\n', max_bytes=4096)


def assignment(**changes):
    value = dict(operation='assign_task', deadline_ns=time.monotonic_ns()+5_000_000_000,
                 payload=dict(task_id='scene-001', inputs_ref=dict(path='/act/input/task.json',
                 sha256='a'*64), deadline_monotonic_s=time.monotonic()+4))
    value['payload'].update(changes)
    return value


def test_task_message_contains_id_without_callback_or_identity_proof():
    packet = decode(assignment())
    assert packet.payload['task_id'] == 'scene-001'
    assert set(packet.payload) == {'task_id', 'inputs_ref', 'deadline_monotonic_s'}


@pytest.mark.parametrize('field', ['output_path', 'coordinator', 'worker_spec',
                                 'lease', 'execution_binding', 'commit_proof'])
def test_assignment_rejects_output_and_callback_fields(field):
    with pytest.raises(ValueError):
        decode(assignment(**{field: '/foreign'}))


@pytest.mark.parametrize('task_id', ['', '../other', 'a/b', '.', '..', True])
def test_task_id_cannot_select_another_output_directory(task_id):
    with pytest.raises(ValueError):
        decode(assignment(task_id=task_id))


@pytest.mark.parametrize('operation', ['register_worker', 'grant_lease', 'heartbeat',
                                     'commit_result', 'recovery', 'resume', 'start'])
def test_only_task_controls_reach_an_existing_container(operation):
    with pytest.raises(ValueError):
        decode(dict(operation=operation, deadline_ns=time.monotonic_ns()+5_000_000_000,
                    payload={}))


@pytest.mark.parametrize('deadline', [True, float('nan'), float('inf'), 0.0])
def test_invalid_task_deadline_refused(deadline):
    with pytest.raises(ValueError):
        decode(assignment(deadline_monotonic_s=deadline))


def test_status_and_terminate_need_no_dispatch_token():
    packet = decode(dict(operation='get_status', deadline_ns=time.monotonic_ns()+5_000_000_000,
                         payload={'task_id': 'scene-001'}))
    assert packet.payload == {'task_id': 'scene-001'}
    packet = decode(dict(operation='terminate', deadline_ns=time.monotonic_ns()+5_000_000_000,
                         payload={'reason': 'task timeout'}))
    assert packet.payload == {'reason': 'task timeout'}


def test_expired_transport_deadline_refused():
    packet = assignment()
    packet['deadline_ns'] = time.monotonic_ns()-1
    with pytest.raises(ValueError):
        decode(packet)


def test_duplicate_task_id_field_is_not_silently_replaced():
    ipc = importlib.import_module('so101_teleop.unified.ipc')
    parser = getattr(ipc, 'decode_container_task', None)
    assert callable(parser), 'four-operation task decoder is missing'
    raw = json.dumps(assignment()).replace('"task_id": "scene-001"',
                                          '"task_id":"other","task_id":"scene-001"')
    with pytest.raises(ValueError):
        parser(raw.encode()+b'\n', max_bytes=4096)
