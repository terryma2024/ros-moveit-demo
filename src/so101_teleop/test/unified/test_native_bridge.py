"""Host acceptance of a native ACT instance's ready record, by process identity instead of Docker identity.

Real: a short-lived subprocess in a session of its own (the stand-in for the instance leader), the kernel identity reader and
the ready-record checks. Controlled: the instance's own ready document, which the test writes with the fields the
instance program would report.
"""

import os
from pathlib import Path
import signal
import subprocess
import sys

import pytest

from so101_demo.runtime.container_campaign.process_identity import (
    ContainerChildBinding, NativeOwnerKey, ProcessOwnerKey, read_process_owner,
)
from so101_teleop.unified.contracts import MutationError
from so101_teleop.unified.native_bridge import NativeBridgeProcessOwner


@pytest.fixture
def leader():
    """A process that leads a process group of its own, as a native instance does."""
    process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        yield process
    finally:
        process.kill()
        process.wait()


def owner_for(process, tmp_path, **overrides):
    control = tmp_path/'control'
    control.mkdir(exist_ok=True)
    key = NativeOwnerKey.from_process(read_process_owner(process.pid), launch_generation=1)
    arguments = dict(native_owner=key, control_socket_root=control, runtime_id='runtime-1', service_epoch='epoch-1',
        campaign_id='campaign-1', worker_id='w00', execution_generation=3, session_id='session-1')
    return NativeBridgeProcessOwner(**(arguments | overrides)), key, control


def ready_document(key, control, **overrides):
    document = dict(schema_version=1, kind='container_child_ready', generation=key.launch_generation,
        process_owner=dict(pid=key.pid, pgid=key.pgid, started_ticks=key.started_ticks, argv_sha256=key.argv_sha256,
                           environment_sha256=key.environment_sha256),
        pid_namespace_inode=os.stat('/proc/self/ns/pid').st_ino, service_epoch='epoch-1', runtime_id='runtime-1',
        campaign_id='campaign-1', worker_id='w00', execution_generation=3,
        normal_socket=str(control/'normal.sock'), safety_socket=str(control/'safety.sock'))
    return document | overrides


def test_the_ready_record_of_the_registered_leader_binds_the_instance(leader, tmp_path):
    bridge, key, control = owner_for(leader, tmp_path)

    binding = bridge.accept_ready(ready_document(key, control))

    assert type(binding) is ContainerChildBinding and binding.container == key
    assert binding.process == key.process_key() and binding.control_socket == str(control/'normal.sock')
    assert binding.pid_namespace_inode == os.stat('/proc/self/ns/pid').st_ino
    assert bridge.binding is binding and bridge.ready() is True
    with pytest.raises(MutationError, match='NATIVE_READY_IDENTITY_INVALID'):
        bridge.accept_ready(ready_document(key, control))        # a second acceptance is never a rebinding


@pytest.mark.parametrize('damage', ['container_socket', 'generation', 'runtime', 'epoch', 'worker', 'extra_field',
                                    'missing_field', 'schema_bool', 'kind'])
def test_a_ready_record_with_any_content_drift_is_refused(leader, tmp_path, damage):
    bridge, key, control = owner_for(leader, tmp_path)
    document = ready_document(key, control)
    if damage == 'container_socket': document['normal_socket'] = '/act/control/normal.sock'
    elif damage == 'generation': document['generation'] = 2
    elif damage == 'runtime': document['runtime_id'] = 'other'
    elif damage == 'epoch': document['service_epoch'] = 'other'
    elif damage == 'worker': document['worker_id'] = 'w01'
    elif damage == 'extra_field': document['container_id'] = 'x'
    elif damage == 'missing_field': del document['safety_socket']
    elif damage == 'schema_bool': document['schema_version'] = True
    else: document['kind'] = 'other'
    with pytest.raises(MutationError, match='NATIVE_READY_IDENTITY_INVALID'):
        bridge.accept_ready(document)
    assert bridge.binding is None and bridge.ready() is False


@pytest.mark.parametrize('damage', ['other_pid', 'start_ticks', 'argv', 'environment', 'group'])
def test_the_reporting_process_must_be_the_registered_leader_of_the_owned_group(leader, tmp_path, damage):
    bridge, key, control = owner_for(leader, tmp_path)
    own = read_process_owner(os.getpid())
    reported = dict(pid=key.pid, pgid=key.pgid, started_ticks=key.started_ticks, argv_sha256=key.argv_sha256,
                    environment_sha256=key.environment_sha256)
    if damage == 'other_pid': reported = dict(vars_of(own))
    elif damage == 'start_ticks': reported['started_ticks'] += 1
    elif damage == 'argv': reported['argv_sha256'] = 'a'*64
    elif damage == 'environment': reported['environment_sha256'] = 'b'*64
    else: reported['pgid'] = own.pgid                      # a member of some other group
    with pytest.raises(MutationError, match='NATIVE_READY_IDENTITY_INVALID'):
        bridge.accept_ready(ready_document(key, control, process_owner=reported))


def vars_of(owner: ProcessOwnerKey):
    return dict(pid=owner.pid, pgid=owner.pgid, started_ticks=owner.started_ticks, argv_sha256=owner.argv_sha256,
                environment_sha256=owner.environment_sha256)


def test_a_record_that_the_kernel_contradicts_is_refused(leader, tmp_path):
    """The record names the registered leader field for field, but the kernel reads other values for that pid."""
    lies = lambda pid: ProcessOwnerKey(pid, pid, 1, 'a'*64, 'b'*64)
    bridge, key, control = owner_for(leader, tmp_path, read_process_owner=lies)
    with pytest.raises(MutationError, match='NATIVE_READY_IDENTITY_INVALID'):
        bridge.accept_ready(ready_document(key, control))


def test_the_instance_must_report_the_hosts_own_pid_namespace(leader, tmp_path):
    """A container reports a namespace different from the Host's; a native instance reports the Host's, so the group and
    descendant scans the Host does are about the instance."""
    bridge, key, control = owner_for(leader, tmp_path)
    foreign = os.stat('/proc/self/ns/pid').st_ino + 1
    with pytest.raises(MutationError, match='NATIVE_READY_IDENTITY_INVALID'):
        bridge.accept_ready(ready_document(key, control, pid_namespace_inode=foreign))
    host_other, key, control = owner_for(leader, tmp_path, host_namespace=lambda: foreign)
    with pytest.raises(MutationError, match='NATIVE_READY_IDENTITY_INVALID'):
        host_other.accept_ready(ready_document(key, control))
    assert host_other.accept_ready(ready_document(key, control, pid_namespace_inode=foreign)).pid_namespace_inode == foreign


def test_ready_is_true_only_while_the_registered_process_is_alive(leader, tmp_path):
    bridge, key, control = owner_for(leader, tmp_path)
    assert bridge.ready() is False                                # nothing bound yet
    bridge.accept_ready(ready_document(key, control))
    assert bridge.ready() is True
    leader.send_signal(signal.SIGKILL)
    leader.wait()
    assert bridge.ready() is False


def test_the_owner_refuses_a_malformed_configuration(leader, tmp_path):
    _bridge, key, control = owner_for(leader, tmp_path)
    for override in (dict(native_owner=read_process_owner(os.getpid())), dict(control_socket_root=Path('relative')),
                     dict(runtime_id=''), dict(execution_generation=0), dict(session_id=None)):
        with pytest.raises(MutationError, match='NATIVE_BRIDGE_CONFIG_INVALID'):
            owner_for(leader, tmp_path, **override)
