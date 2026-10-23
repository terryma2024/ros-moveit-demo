"""The Host prepares a native single-worker instance: the same spec and directories as a container, a native owner.

Real: the launcher, the spec loader, the real launch registry and owner construction. Nothing is started; the Teacher
endpoint is a plain namespace carrying the Host path of the Teacher socket.
"""

import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from test_shard_launcher import GPU, prepared
from so101_demo.runtime.act_instance.spec import _COLLECTION_FIELDS, _FIELDS, load_spec
from so101_demo.runtime.container_campaign.native_launcher import (
    NATIVE_INSTANCE_MODULE, NativeInstanceLauncher, installed_graph_probe,
)
from so101_demo.runtime.container_campaign.native_owner import NativeInstanceOwner
from so101_demo.runtime.container_campaign.paths import host_teacher_socket
from so101_demo.runtime.container_campaign.shard_launcher import ContainerShardLauncher


def native_launcher(tmp_path, **overrides):
    container, registry, slot, paths = prepared(tmp_path)
    arguments = dict(context=container.context, config=container.config, paths=paths, registry=registry,
        parallel_runtime=container.parallel_runtime, approved_inputs=(), config_paths=container.config_paths,
        install_prefix=tmp_path/'install', ros2_executable=tmp_path/'ros/bin/ros2',
        base_environment=dict(PATH='/usr/bin', ROS_NAMESPACE='/stale'))
    launcher = NativeInstanceLauncher(**(arguments | overrides))
    endpoints = dict(teacher=SimpleNamespace(socket_path=host_teacher_socket(paths['run'])))
    return launcher, container, registry, slot, paths, endpoints


def test_the_native_launcher_writes_the_same_spec_a_container_gets_and_a_native_owner(tmp_path):
    launcher, container, registry, slot, paths, endpoints = native_launcher(tmp_path)
    try:
        (owner,) = launcher(plan={'wave_index': 0}, endpoints=endpoints, slots=(slot,))
        written = json.loads(owner.entry.spec.read_text())
        spec, runtime = load_spec(owner.entry.spec)
        assert type(owner) is NativeInstanceOwner and spec == written == owner.spec
        assert set(written) == _FIELDS | _COLLECTION_FIELDS and written['kind'] == 'ACT_CONTAINER_SHARD'
        launch = owner.launch
        assert launch.launcher == 'native' and launch.container_name is None and launch.image_digest is None
        assert launch.launch_id == 'wave-0-w00-g1' and launch.session_id == written['simulation_session_id']
        assert owner.argv[:3] == [sys.executable, '-m', NATIVE_INSTANCE_MODULE]
        assert owner.argv[3:] == ['--spec', str(owner.entry.spec), '--install-prefix', str(tmp_path/'install'),
                                  '--ros2', str(tmp_path/'ros/bin/ros2')]
        assert owner.startup_budget == runtime.initializing_hard_timeout_s
        assert owner.status_budget == runtime.heartbeat_timeout_s and owner.stop_budget == runtime.worker_recovery_timeout_s
        assert owner.environment['ROS_DOMAIN_ID'] == '181' and 'ROS_NAMESPACE' not in owner.environment
        assert owner.environment['CUDA_VISIBLE_DEVICES'] == GPU and owner.environment['PATH'] == '/usr/bin'
    finally:
        registry.close()


def test_the_native_and_the_container_launcher_write_byte_identical_specs_for_the_same_slot(tmp_path):
    native, container, registry, slot, paths, endpoints = native_launcher(tmp_path)
    try:
        (owner,) = native(plan={'wave_index': 0}, endpoints=endpoints, slots=(slot,))
        native_spec = json.loads(owner.entry.spec.read_text())
    finally:
        registry.close()
    other = tmp_path/'other'
    other.mkdir()
    twin, registry, slot, paths = prepared(other)
    try:
        (container_owner,) = twin(plan={'wave_index': 0}, endpoints={}, slots=(slot,))
        container_spec = json.loads(container_owner.entry.spec.read_text())
    finally:
        registry.close()
    differing = {name for name in native_spec if native_spec[name] != container_spec[name]}
    # only what names this run's own directories and its random identities differs, never the shape or the workload
    assert set(native_spec) == set(container_spec)
    assert differing <= {'owned_root', 'service_token', 'campaign_config', 'parallel_runtime', 'controlled_runtime',
                         'deadline_monotonic_s'}


def test_the_instance_directories_are_the_containers_with_the_hosts_teacher_socket_path(tmp_path):
    launcher, container, registry, slot, paths, endpoints = native_launcher(tmp_path)
    try:
        (owner,) = launcher(plan={'wave_index': 0}, endpoints=endpoints, slots=(slot,))
        root = Path(owner.launch.owned_root)
        for name in ('tmp', 'control', 'output', 'task-inputs'):
            directory = root/name
            assert directory.is_dir() and not directory.is_symlink()
            assert directory.stat().st_uid == os.getuid() and directory.stat().st_mode & 0o777 == 0o700
        assert root == paths['run']/'wave-0/w00/g1'
        assert owner.teacher_socket == paths['run']/'ipc/teacher/inference.sock'
        assert owner.environment['SO101_ACT_INSTANCE_OUTPUT'] == str(root/'output')
    finally:
        registry.close()


def test_the_native_launcher_is_for_exactly_one_worker_and_a_prefix(tmp_path):
    container, registry, slot, paths = prepared(tmp_path)
    try:
        from dataclasses import replace
        arguments = dict(context=container.context, config=container.config, paths=paths, registry=registry,
            parallel_runtime=container.parallel_runtime, approved_inputs=(), config_paths=container.config_paths)
        with pytest.raises(ValueError, match='COLLECTION_NATIVE_LAUNCHER_INVALID'):
            NativeInstanceLauncher(install_prefix=Path('relative'), **arguments)
        with pytest.raises(ValueError, match='COLLECTION_NATIVE_LAUNCHER_INVALID'):
            NativeInstanceLauncher(install_prefix=tmp_path, **(arguments | dict(
                context=replace(container.context, worker_count=2))))
        with pytest.raises(ValueError, match='COLLECTION_NATIVE_LAUNCHER_INVALID'):
            NativeInstanceLauncher(install_prefix=tmp_path, ros2_executable=Path('ros2'), **arguments)
        with pytest.raises(ValueError, match='COLLECTION_NATIVE_LAUNCHER_INVALID'):      # no ros2 on the Host's PATH
            NativeInstanceLauncher(install_prefix=tmp_path, base_environment=dict(PATH=str(tmp_path/'empty')), **arguments)
        host_bin = tmp_path/'host-bin'
        host_bin.mkdir()
        (host_bin/'ros2').write_text('#!/bin/sh\n')
        (host_bin/'ros2').chmod(0o700)
        resolved = NativeInstanceLauncher(install_prefix=tmp_path, base_environment=dict(PATH=str(host_bin)), **arguments)
        assert isinstance(resolved, ContainerShardLauncher) and resolved.ros2_executable == host_bin/'ros2'
    finally:
        registry.close()


def test_the_production_graph_probe_reads_the_hosts_graph_on_the_fixed_domain_without_the_marker(tmp_path):
    launcher, container, registry, slot, paths, endpoints = native_launcher(tmp_path)
    try:
        (owner,) = launcher(plan={'wave_index': 0}, endpoints=endpoints, slots=(slot,))
        ros2 = tmp_path/'ros/bin/ros2'
        ros2.parent.mkdir(parents=True)
        ros2.write_text('#!/bin/sh\n{ echo "ARGV=$*"; env | grep -E "^(ROS_DOMAIN_ID|ROS_LOCALHOST_ONLY|SO101_ACT_INSTANCE_ROOT)="; } > "$0.seen"\n')
        ros2.chmod(0o700)
        probe = installed_graph_probe(ros2, owner.launch, owner.environment)
        assert probe() is True                                           # `ros2 node list` printed no node
        text = Path(str(ros2)+'.seen').read_text()
        seen = text.split('\n')
        assert seen[0] == 'ARGV=node list --no-daemon --spin-time 3'
        assert 'ROS_DOMAIN_ID=181' in seen and 'ROS_LOCALHOST_ONLY=1' in seen
        assert not [item for item in seen if item.startswith('SO101_ACT_INSTANCE_ROOT')]
        ros2.write_text('#!/bin/sh\necho /some_node\n')
        assert installed_graph_probe(ros2, owner.launch, owner.environment)() is False
    finally:
        registry.close()
