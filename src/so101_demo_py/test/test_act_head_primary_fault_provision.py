"""Primary close-only publication must never grant the monitor's scope."""

import os
import sys

import pytest

from so101_demo.adapters.act.controller_reservation_provision import (
    _process_start_ticks, write_head_primary_fault_provision,
)
from test_act_head_revocation import native_server, ack

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Linux peer credentials required')


def publish(path, owner, endpoint, session='head-test'):
    return write_head_primary_fault_provision(path, session_id=session,
        native_owner=owner, socket_path=endpoint)


def test_actual_primary_scope_and_capability_are_published_once(native_server):
    path, owner, _ = native_server(ack())
    destination = path.parent / 'neck-primary-revoke.provision'
    endpoint = path.parent / 'neck-primary-revoke.sock'
    capability = publish(destination, owner, endpoint)
    raw = destination.read_bytes()
    assert raw[:8] == b'SOPR' + bytes((2, 4, 9, len(os.fsencode(endpoint))))
    assert int.from_bytes(raw[8:12], 'big') == os.geteuid()
    assert int.from_bytes(raw[12:16], 'big') == os.getpid()
    assert int.from_bytes(raw[16:24], 'big') == _process_start_ticks(os.getpid())
    assert len(capability) == 32 and any(capability) and raw[24:56] == capability
    assert int.from_bytes(raw[56:60], 'big') == owner['uid']
    assert int.from_bytes(raw[60:64], 'big') == owner['pid']
    assert int.from_bytes(raw[64:72], 'big') == owner['start_ticks']
    assert raw[72:] == b'head-test' + os.fsencode(endpoint)
    assert destination.stat().st_mode & 0o777 == 0o600
    assert destination.stat().st_nlink == 1
    with pytest.raises(FileExistsError):publish(destination, owner, endpoint)
    assert destination.read_bytes() == raw


def test_primary_writer_cannot_publish_monitor_authority(native_server):
    path, owner, _ = native_server(ack())
    destination = path.parent / 'neck-revoke.provision'
    endpoint = path.parent / 'neck-revoke.sock'
    with pytest.raises(ValueError):publish(destination, owner, endpoint)
    assert not destination.exists()


@pytest.mark.parametrize('damage', ['actor_is_native', 'ticks', 'uid', 'bool_pid',
    'session', 'arm_path', 'monitor_endpoint', 'other_parent', 'long_endpoint'])
def test_invalid_primary_scope_never_publishes(native_server, damage):
    path, owner, _ = native_server(ack())
    destination = path.parent / 'neck-primary-revoke.provision'
    endpoint = path.parent / 'neck-primary-revoke.sock'
    session = 'head-test'
    if damage == 'actor_is_native':
        owner = dict(uid=os.geteuid(), pid=os.getpid(), start_ticks=_process_start_ticks(os.getpid()))
    elif damage == 'ticks':owner = dict(owner, start_ticks=owner['start_ticks']+1)
    elif damage == 'uid':owner = dict(owner, uid=owner['uid']+1)
    elif damage == 'bool_pid':owner = dict(owner, pid=True)
    elif damage == 'session':session = 'bad/session'
    elif damage == 'arm_path':destination = path.parent / 'arm.provision'
    elif damage == 'monitor_endpoint':endpoint = path.parent / 'neck-revoke.sock'
    elif damage == 'other_parent':endpoint = path.parent.parent / 'neck-primary-revoke.sock'
    else:endpoint = path.parent / ('x'*108) / 'neck-primary-revoke.sock'
    with pytest.raises(ValueError):publish(destination, owner, endpoint, session)
    assert not destination.exists()


def test_primary_writer_refuses_symlinked_private_parent(native_server):
    path, owner, _ = native_server(ack())
    link = path.parent.parent / (path.parent.name + '-alias')
    link.symlink_to(path.parent, target_is_directory=True)
    destination = link / 'neck-primary-revoke.provision'
    with pytest.raises(PermissionError):publish(destination, owner, link / 'neck-primary-revoke.sock')
    assert not destination.exists()


def test_primary_writer_refuses_nonprivate_parent(native_server):
    path, owner, _ = native_server(ack())
    destination = path.parent / 'neck-primary-revoke.provision'
    os.chmod(path.parent, 0o755)
    with pytest.raises(PermissionError):publish(destination, owner, path.parent / 'neck-primary-revoke.sock')
    assert not destination.exists()
