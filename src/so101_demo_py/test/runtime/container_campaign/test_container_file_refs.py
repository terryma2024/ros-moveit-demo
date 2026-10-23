"""Every file a container's loaders open must be mounted into that container.

A config or spec holds `{path, sha256}` file refs that the loader reads back. The Host can read any path, so a Host-side
check never shows that the container can: this suite builds the real launch argv, derives the container's view of the
filesystem from its `--mount` options (a path is visible when a mount source is that file or contains it), and runs the real
loaders under that view. The eight-worker qualification campaign failed at once because `qualification_contract` was such a
ref and was not mounted (`CAMPAIGN_SHARD_SPEC_INVALID`); worker counts 1 and 2 carry `null` there and never showed it.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import time

import pytest

from test_config_identity import campaign_fixture, file_ref, write_config
from so101_demo.cli import campaign_inference
from so101_demo.runtime.act_instance.spec import load_spec
from so101_demo.runtime.container_campaign.launch import InferenceLaunchArgs, build_container_argv
from so101_demo.runtime.container_campaign.paths import make_campaign_paths
from so101_demo.runtime.container_campaign.registry import ContainerLaunchRegistry
from so101_demo.runtime.container_campaign.shard_launcher import ContainerShardLauncher
from so101_demo.runtime.inference import config as config_module
from so101_demo.runtime.inference.config import load_campaign_config
from so101_teleop.unified.contracts import AdmittedCampaignContext
from so101_teleop.unified.worker_slots import ActWorkerSlot

GPU = 'GPU-28221cec-9d21-7753-fd5a-da645740df19'

#: Refs that a loader reads only as a hash shape, never opens, in the role under test: the Head weights in a Teacher-role load.
NOT_OPENED = {('head_service', 'model', 'weights')}


def file_refs(document, trail=()):
    """Every `{path, sha256}` ref reachable in a JSON document, with the key trail to it."""
    found = []
    if isinstance(document, dict):
        if set(document) == {'path', 'sha256'} and isinstance(document['path'], str):
            found.append((trail, document))
        else:
            for key, value in document.items():
                found.extend(file_refs(value, trail+(key,)))
    elif isinstance(document, list):
        for index, value in enumerate(document):
            found.extend(file_refs(value, trail+(index,)))
    return found


def mount_sources(argv):
    """(source, target, read_only) of every `--mount` in an argv."""
    mounts = []
    for index, flag in enumerate(argv):
        if flag == '--mount':
            fields = dict(item.partition('=')[::2] for item in argv[index+1].split(',') if '=' in item)
            mounts.append((Path(fields['src']), Path(fields['dst']), argv[index+1].endswith(',readonly')))
    return mounts


def visible(path, argv):
    """Whether the container sees `path`: a mount maps the same host path at that target (the fixed rule) and contains it."""
    path = Path(path)
    return any(source == target and (source == path or source in path.parents) for source, target, _ in mount_sources(argv))


@pytest.fixture
def container_view(monkeypatch):
    """Run the real loaders as the container sees the filesystem: only paths under the given argv's mounts open."""
    real = config_module._open_regular
    state = {}

    def install(argv):
        state['argv'] = argv

    def guarded(path):
        if 'argv' in state and not visible(path, state['argv']):
            raise FileNotFoundError(str(path))
        return real(path)

    monkeypatch.setattr(config_module, '_open_regular', guarded)
    return install


def build(tmp_path, *, contract):
    paths = make_campaign_paths(tmp_path, 'campaign')
    campaign = campaign_fixture(tmp_path)
    campaign['gpu_uuid'] = GPU
    if contract:
        campaign['qualification_contract'] = file_ref(tmp_path/'gate-contract.json', b'{"worker_count":8}\n')
    campaign_path = write_config(tmp_path, campaign)
    campaign_sha = hashlib.sha256(campaign_path.read_bytes()).hexdigest()
    runtime = tmp_path/'parallel.yaml'
    shutil.copyfile(Path(__file__).resolve().parents[3]/'config/mujoco/parallel_batch_linux_cuda.yaml', runtime)
    (paths['run']/'inputs').mkdir()
    context = AdmittedCampaignContext(campaign_id='campaign', operation_id='operation',
        workload_kind='act_collection_start', service_epoch='epoch', execution_generation=1,
        stable_host_id='host', physical_gpu_uuid=GPU, worker_count=1, source_sha256='d'*64,
        manifest_sha256='a'*64, runtime_config_sha256=campaign['controlled_runtime']['sha256'],
        collection_config_sha256='c'*64, contact_policy_fingerprint='d'*64, domain_session_map_sha256='d'*64,
        resource_binding_id='binding', evidence_root=str(paths['run']), admitted_at_monotonic_s=1,
        deadline_monotonic_s=time.monotonic()+3600, registered_evidence_root=str(tmp_path),
        campaign_config_path=str(campaign_path), campaign_config_sha256=campaign_sha)
    registry = ContainerLaunchRegistry(paths['host']/'launches.sqlite3')
    # The production approved inputs of `act_collect_parallel`: the frozen run inputs, the runtime YAML, the controlled
    # runtime and the Teacher weights; the campaign config is the one config path.
    approved = (paths['run']/'inputs', runtime, Path(campaign['controlled_runtime']['path']),
                Path(campaign['teacher_service']['model']['weights']['path']))
    launcher = ContainerShardLauncher(context=context,
        config=load_campaign_config(campaign_path, expected_sha256=campaign_sha), paths=paths, registry=registry,
        parallel_runtime=dict(path=str(runtime), sha256=hashlib.sha256(runtime.read_bytes()).hexdigest()),
        approved_inputs=approved, config_paths=(campaign_path,))
    slot = ActWorkerSlot(campaign_id='campaign', worker_id='w00', execution_generation=1)
    return launcher, registry, slot, paths, campaign, campaign_path, approved


def test_shard_mounts_the_qualification_contract_read_only_and_the_spec_loads_in_the_container_view(tmp_path, container_view):
    launcher, registry, slot, paths, campaign, campaign_path, _ = build(tmp_path, contract=True)
    try:
        (owner,) = launcher(plan={'wave_index': 0}, endpoints={}, slots=(slot,))
        contract = Path(campaign['qualification_contract']['path'])
        assert (contract, contract, True) in mount_sources(owner.argv)
        assert mount_sources(owner.argv).count((contract, contract, True)) == 1
        container_view(owner.argv)
        assert load_spec(owner.entry.spec)[0] == owner.spec
    finally:
        registry.close()


def test_without_the_contract_mount_the_container_view_refuses_the_spec(tmp_path, container_view):
    launcher, registry, slot, paths, campaign, campaign_path, _ = build(tmp_path, contract=True)
    try:
        (owner,) = launcher(plan={'wave_index': 0}, endpoints={}, slots=(slot,))
        contract = Path(campaign['qualification_contract']['path'])
        argv = []
        index = 0
        while index < len(owner.argv):  # the argv the shard had before the fix: every mount except the contract
            if owner.argv[index] == '--mount' and f'src={contract},' in owner.argv[index+1]:
                index += 2
                continue
            argv.append(owner.argv[index])
            index += 1
        assert not visible(contract, argv)
        container_view(argv)
        with pytest.raises(ValueError, match='CAMPAIGN_SHARD_SPEC_INVALID'):
            load_spec(owner.entry.spec)
    finally:
        registry.close()


def test_null_contract_adds_no_mount_and_loads_in_the_container_view(tmp_path, container_view):
    launcher, registry, slot, paths, campaign, campaign_path, approved = build(tmp_path, contract=False)
    try:
        (owner,) = launcher(plan={'wave_index': 0}, endpoints={}, slots=(slot,))
        sources = {source for source, _, _ in mount_sources(owner.argv)}
        assert 'gate-contract.json' not in ' '.join(map(str, sources))
        # Exactly the owned root, its output, the approved inputs, the one config, the spec and the three sockets.
        assert sources == {Path(owner.launch.owned_root), Path(owner.launch.owned_root)/'output', *approved,
            campaign_path, owner.entry.spec, paths['socket_roots']['head'], paths['socket_roots']['teacher'],
            Path(owner.launch.owned_root)/'control'}
        container_view(owner.argv)
        assert load_spec(owner.entry.spec)[0] == owner.spec
    finally:
        registry.close()


@pytest.mark.parametrize('contract', [False, True])
def test_every_file_ref_of_the_shard_spec_and_campaign_config_is_mounted(tmp_path, contract):
    launcher, registry, slot, paths, campaign, campaign_path, _ = build(tmp_path, contract=contract)
    try:
        (owner,) = launcher(plan={'wave_index': 0}, endpoints={}, slots=(slot,))
        refs = (file_refs(json.loads(owner.entry.spec.read_text()), ('spec',))
                + file_refs(json.loads(campaign_path.read_text()), ()))
        assert {trail[-1] for trail, _ in refs} >= {'controlled_runtime', 'parallel_runtime', 'campaign_config', 'weights'}
        assert bool(contract) == any(trail == ('qualification_contract',) for trail, _ in refs)
        unmounted = [trail for trail, ref in refs if trail not in NOT_OPENED and not visible(ref['path'], owner.argv)]
        assert unmounted == []
        # Exempt refs are exempt only because the Teacher-role load does not open them.
        assert [trail for trail, ref in refs if trail in NOT_OPENED and visible(ref['path'], owner.argv)] == []
    finally:
        registry.close()


def test_teacher_container_needs_no_campaign_config_or_contract(tmp_path, container_view):
    paths = make_campaign_paths(tmp_path, 'campaign')
    campaign = campaign_fixture(tmp_path)
    campaign['qualification_contract'] = file_ref(tmp_path/'gate-contract.json', b'{"worker_count":8}\n')
    settings = campaign['teacher_service']
    config_path = paths['run']/'teacher-service.json'
    config_path.write_text(json.dumps(settings, sort_keys=True))
    owned = paths['services']['teacher']
    (owned/'tmp').mkdir(mode=0o700)
    entry = InferenceLaunchArgs(config=config_path, generation='campaign-teacher-g1',
        startup_deadline_monotonic_ns=time.monotonic_ns()+10**11, receive_budget_s=1.0)
    images = {name: dict(digest='sha256:'+digest*64, package_source_sha256='c'*64, install_sha256='d'*64)
              for name, digest in (('head', 'a'), ('teacher', 'a'), ('shard', 'b'))}
    argv = build_container_argv(role='teacher', image=images, gpu_uuid=GPU, container_name='so101-campaign-teacher-g1',
        uid=os.getuid(), gid=os.getgid(),
        host_paths=dict(owned_root=owned, approved_inputs=(Path(settings['model']['weights']['path']),),
            socket_roots=paths['socket_roots'], config_paths=(config_path,), entry=entry))
    # The Teacher reads its own service settings only; the only ref in them is its weights, which are mounted.
    refs = file_refs(settings)
    assert [trail for trail, _ in refs] == [('model', 'weights')]
    assert all(visible(ref['path'], argv) for _, ref in refs)
    assert not visible(campaign['qualification_contract']['path'], argv)
    assert not visible(paths['run']/'campaign.json', argv)
    container_view(argv)
    arguments = type('Arguments', (), dict(config=config_path, role='teacher', gpu_uuid=GPU,
        startup_deadline_monotonic_ns=entry.startup_deadline_monotonic_ns, head_descriptor=None,
        head_descriptor_sha256=None))
    config, descriptor = campaign_inference._inputs(arguments)
    assert descriptor is None and config == settings
