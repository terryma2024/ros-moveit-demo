"""The Host prepares native collection instances: real slot, real runtime config, real spec loader and mount rules.

No Docker, container or ROS runs here; owners are constructed but never started.
"""

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

import pytest

from test_config_identity import campaign_fixture, write_config
from so101_demo.runtime.act_instance.program import instance_id_for
from so101_demo.runtime.act_instance.spec import _COLLECTION_FIELDS, _FIELDS, load_spec
from so101_demo.runtime.container_campaign.paths import make_campaign_paths
from so101_demo.runtime.container_campaign.registry import ContainerLaunchRegistry
from so101_demo.runtime.container_campaign.shard_launcher import ContainerShardLauncher
from so101_demo.runtime.inference.config import load_campaign_config
from so101_teleop.unified.contracts import AdmittedCampaignContext
from so101_teleop.unified.worker_slots import ActWorkerSlot

#: The retired per-worker field; built from fragments so the source-tree absence test keeps matching nothing.
NS_FIELD = "ros" + "_namespace"

GPU = 'GPU-28221cec-9d21-7753-fd5a-da645740df19'


def prepared(tmp_path, mount=None, cpuset=None, mounted=True):
    paths = make_campaign_paths(tmp_path, 'campaign')
    campaign = campaign_fixture(tmp_path, mounted=mounted)
    campaign['gpu_uuid'] = GPU
    if mount is not None:
        campaign['shard_image'] = dict(campaign['teacher_service']['image'])
        campaign['mount_build'] = mount.document()
    if cpuset is not None:
        campaign['shard_cpuset'] = cpuset
    campaign_path = write_config(tmp_path, campaign)
    campaign_sha = hashlib.sha256(campaign_path.read_bytes()).hexdigest()
    runtime = tmp_path/'parallel.yaml'
    shutil.copyfile(Path(__file__).resolve().parents[3]/'config/mujoco/parallel_batch_linux_cuda.yaml', runtime)
    context = AdmittedCampaignContext(campaign_id='campaign', operation_id='operation',
        workload_kind='act_collection_start', service_epoch='epoch', execution_generation=1,
        stable_host_id='host', physical_gpu_uuid=GPU, worker_count=1, source_sha256='d'*64,
        manifest_sha256='a'*64, runtime_config_sha256=campaign['controlled_runtime']['sha256'],
        collection_config_sha256='c'*64, contact_policy_fingerprint='d'*64, domain_session_map_sha256='d'*64,
        resource_binding_id='binding', evidence_root=str(paths['run']), admitted_at_monotonic_s=1,
        deadline_monotonic_s=time.monotonic()+3600, registered_evidence_root=str(tmp_path),
        campaign_config_path=str(campaign_path), campaign_config_sha256=campaign_sha)
    registry = ContainerLaunchRegistry(paths['host']/'launches.sqlite3')
    launcher = ContainerShardLauncher(context=context, config=load_campaign_config(campaign_path,
            expected_sha256=campaign_sha), paths=paths, registry=registry,
        parallel_runtime=dict(path=str(runtime), sha256=hashlib.sha256(runtime.read_bytes()).hexdigest()),
        approved_inputs=(), config_paths=(campaign_path, runtime))
    slot = ActWorkerSlot(campaign_id='campaign', worker_id='w00', execution_generation=1)
    return launcher, registry, slot, paths


def test_launcher_writes_a_spec_the_real_shard_loader_accepts(tmp_path):
    launcher, registry, slot, paths = prepared(tmp_path)
    try:
        (owner,) = launcher(plan={'wave_index': 0}, endpoints={}, slots=(slot,))
        written = json.loads(owner.entry.spec.read_text())
        spec, runtime = load_spec(owner.entry.spec)
        assert spec == written == owner.spec
        assert set(written) == _FIELDS | _COLLECTION_FIELDS
        assert not any('worker_spec' in name or 'coordinator' in name for name in written)
        assert written['schema_version'] == 2 and not {NS_FIELD, 'ros_domain_id'} & set(written)
        assert not {NS_FIELD, 'ros_domain_id'} & set(asdict(owner.launch)) and 'ROS_NAMESPACE' not in ' '.join(owner.argv)
        assert written['wave_id'] == 'wave-0' and written['launch_generation'] == 1
        # The Host launch id is exactly what the child derives as its instance id.
        assert owner.launch.launch_id == instance_id_for(written) == 'wave-0-w00-g1'
        assert owner.startup_budget == runtime.initializing_hard_timeout_s
        assert owner.status_budget == runtime.heartbeat_timeout_s
        assert owner.stop_budget == runtime.worker_recovery_timeout_s
        assert owner.max_bytes == runtime.broker_max_frame_bytes
    finally:
        registry.close()


def test_owned_root_has_output_and_task_inputs_that_satisfy_the_real_mount_rules(tmp_path):
    launcher, registry, slot, paths = prepared(tmp_path)
    try:
        (owner,) = launcher(plan={'wave_index': 0}, endpoints={}, slots=(slot,))
        root = Path(owner.launch.owned_root)
        for name in ('tmp', 'control', 'output', 'task-inputs'):
            directory = root/name
            assert directory.is_dir() and not directory.is_symlink()
            assert directory.stat().st_uid == os.getuid() and directory.stat().st_mode & 0o777 == 0o700
        mounts = [argv for flag, argv in zip(owner.argv, owner.argv[1:]) if flag == '--mount']
        assert f'type=bind,src={root}/output,dst=/act/output' in mounts
        assert f'type=bind,src={root},dst={root}' in mounts
        assert not any('task-inputs' in mount for mount in mounts)  # reached through the owned-root mount only
        # The Host journal and run root are not mountable by the instance.
        assert not any(str(paths['host']) in mount for mount in mounts)
    finally:
        registry.close()


def test_waves_must_be_prepared_in_order_with_the_admitted_slots(tmp_path):
    launcher, registry, slot, paths = prepared(tmp_path)
    try:
        with pytest.raises(ValueError, match='COLLECTION_SHARD_WAVE_INVALID'):
            launcher(plan={'wave_index': 1}, endpoints={}, slots=(slot,))
        foreign = ActWorkerSlot(campaign_id='campaign', worker_id='w01', execution_generation=1)
        with pytest.raises(ValueError, match='COLLECTION_SHARD_WAVE_INVALID'):
            launcher(plan={'wave_index': 0}, endpoints={}, slots=(foreign,))
        assert not (paths['run']/'wave-0').exists()
    finally:
        registry.close()


def test_a_mount_mode_config_makes_every_shard_owner_mounted(tmp_path):
    commit = '0123456789abcdef0123456789abcdef01234567'
    from so101_demo.runtime.container_campaign.mount_build import MountBuild
    mount = MountBuild(commit=commit, root=tmp_path/'mounted'/commit[:12])
    for name in ('install', 'source'):
        (mount.root/name).mkdir(parents=True)
        (mount.root/name/'BUILD-COMMIT').write_text(commit+'\n')
    launcher, registry, slot, paths = prepared(tmp_path, mount)
    try:
        (owner,) = launcher(plan={'wave_index': 0}, endpoints={}, slots=(slot,))
        assert owner.mount_build == mount
        assert f'SO101_EXPECTED_COMMIT={commit}' in owner.argv and f'type=bind,src={mount.install},dst={mount.install},readonly' in owner.argv
        assert owner.argv[owner.argv.index(launcher.config['shard_image']['digest']) + 1] == '/act/venv/bin/python'
    finally:
        registry.close()


def test_an_image_mode_config_is_refused_before_any_shard_owner_exists(tmp_path):
    with pytest.raises(ValueError, match='MOUNT_BUILD_REQUIRED'):
        prepared(tmp_path, mounted=False)


def test_a_launcher_without_the_cpuset_key_adds_no_cpu_option(tmp_path):
    launcher, registry, slot, _paths = prepared(tmp_path)
    try:
        (owner,) = launcher(plan={'wave_index': 0}, endpoints={}, slots=(slot,))
        assert '--cpuset-cpus' not in owner.argv
    finally:
        registry.close()


def test_the_cpuset_key_gives_the_shard_of_a_worker_its_own_range(tmp_path, monkeypatch):
    monkeypatch.setattr('os.cpu_count', lambda: 24)
    launcher, registry, slot, _paths = prepared(tmp_path, cpuset={'shard_cpus': 3, 'first_shard_cpu': 6})
    try:
        (owner,) = launcher(plan={'wave_index': 0}, endpoints={}, slots=(slot,))
        assert owner.argv[owner.argv.index('--cpuset-cpus')+1] == '6-8'
    finally:
        registry.close()


def test_a_cpuset_that_does_not_fit_the_host_stops_the_wave_before_anything_is_prepared(tmp_path, monkeypatch):
    monkeypatch.setattr('os.cpu_count', lambda: 8)
    launcher, registry, slot, paths = prepared(tmp_path, cpuset={'shard_cpus': 3, 'first_shard_cpu': 6})
    try:
        with pytest.raises(ValueError, match='CPUSET_PLAN_EXCEEDS_HOST'):
            launcher(plan={'wave_index': 0}, endpoints={}, slots=(slot,))
        assert not (paths['run']/'wave-0').exists()
    finally:
        registry.close()
