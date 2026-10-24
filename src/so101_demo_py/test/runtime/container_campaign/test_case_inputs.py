"""The Host producer of a campaign's per-scene collection inputs.

Real here: `freeze_inputs`/`verify_frozen_inputs` (through `freeze_campaign_inputs`), `build_collection_scope`,
`write_collection_scope`, `require_scope_for_inputs`, `make_campaign_paths`, `build_role_mounts`,
`CollectionCaseArtifacts`, `load_campaign_config`, the container's `load_task_input` with its frozen-input readers.
Controlled: the role candidates (`_registry`, the sibling freeze tests' synthetic approvals - never a production approval),
the scene rows (hand-written, same `scenarios[]` shape as the sampler) and the execution snapshot source: the synthetic
registry's `source_root` is a temporary tree, so the snapshot is frozen from this repository, as `frozen_child_inputs` does,
with the registry's scene identity and contact proposal built from that snapshot so the real identity checks pass.
Forged variants are a copy of the frozen set with one document edited and its hash chain recomputed, as a self-consistent
forger would. No simulator, container, Head or qualification claim is made.
"""

import copy
import hashlib
import itertools
import json
from pathlib import Path
import shutil
import time

import pytest

from so101_demo.act.collection_scope import build_collection_scope, read_collection_scope
from so101_demo.act.contact_policy import policy_fingerprint
from so101_demo.act.diagnostic_episode_inputs import _canonical, verify_frozen_inputs
from so101_demo.parallel_batch.two_worker_composition import load_execution_config as _load_runtime_config
from so101_demo.runtime.container_campaign import case_inputs
from so101_demo.runtime.container_campaign.case_artifacts import CollectionCaseArtifacts
from so101_demo.runtime.container_campaign.paths import build_role_mounts, make_campaign_paths
from so101_demo.runtime.container_campaign.task_contracts import InputRef, TaskSpec
from so101_demo.runtime.inference.config import load_campaign_config
from test_act_diagnostic_episode_scope import _proposal_and_receipt, _registry, _write_registry
from test_act_formal_scene_scope import ROWS, scene_file
from test_act_policy_freeze import rehash
from test_config_identity import campaign_fixture, write_config
from paths import PACKAGE_ROOT, REPOSITORY

TEACHER_SOCKET = Path('/act/ipc/teacher/inference.sock')

CONFIG = PACKAGE_ROOT / 'config/act'
RUNTIME_YAML = PACKAGE_ROOT / 'config/mujoco/parallel_batch_act_offline.yaml'
DISK_FLOOR = 53687091200
FORGERIES = itertools.count()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ref(path):
    return dict(path=str(path), sha256=sha(path))


def policies():
    return dict(teacher_endpoint=CONFIG / 'teacher_endpoint.yaml',
                teacher_execution_policy=CONFIG / 'teacher_execution_policy.yaml',
                episode_recorder_policy=CONFIG / 'episode_recorder.yaml',
                runtime_policy=CONFIG / 'endpoint_pose_development_runtime.yaml')


def bound_registry(base, snapshot, scene_bytes, **contents):
    """Controlled registry whose scene identity and contact proposal match the real execution snapshot.

    `contents` replaces the bytes of other roles (`runtime_config`, `collection_config`) of the synthetic registry."""
    identity = dict(model_sha256=snapshot['model_sha256'], scene_sha256=hashlib.sha256(scene_bytes).hexdigest(),
                    mujoco_version=snapshot['mujoco_version'])
    registry = _registry(base, contents={'scene_model': scene_bytes, **contents})
    registry['roles']['scene_model']['identity'] = identity
    proposal_path, receipt_path = _proposal_and_receipt(base, model_sha=identity['model_sha256'], tag='-bound')
    proposal = json.loads(proposal_path.read_bytes())
    proposal['payload'].update(scene_sha256=identity['scene_sha256'], mujoco_version=identity['mujoco_version'])
    fingerprint = policy_fingerprint(proposal['payload'])
    proposal['policy_fingerprint'] = fingerprint
    proposal['proposal_sha256'] = hashlib.sha256(_canonical(
        {key: value for key, value in proposal.items() if key != 'proposal_sha256'})).hexdigest()
    receipt = json.loads(receipt_path.read_bytes())
    receipt['policy_fingerprint'] = fingerprint
    proposal_path.write_bytes(_canonical(proposal))
    receipt_path.write_bytes(_canonical(receipt))
    for role, path in (('contact_proposal', proposal_path), ('contact_activation', receipt_path)):
        entry = dict(registry['roles'][role]['selected'], path=str(path), sha256=sha(path))
        registry['roles'][role].update(candidates=[entry], selected=entry)
    return registry


@pytest.fixture(scope='module')
def world(tmp_path_factory):
    """One real formal freeze of a two-scene campaign, its scopes and its campaign config, built once for the module."""
    from so101_demo.act import execution_snapshot

    base = tmp_path_factory.mktemp('case-inputs')
    probe = execution_snapshot.freeze_execution_snapshot(REPOSITORY, base / 'probe')
    scene_bytes = (base / 'probe' / probe['scene_path']).read_bytes()
    candidates = _write_registry(base, bound_registry(base, probe, scene_bytes))
    source = scene_file(base)
    root = base / 'evidence'
    root.mkdir()
    run = make_campaign_paths(root, 'run-1')['run']
    original = execution_snapshot.freeze_execution_snapshot
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(execution_snapshot, 'freeze_execution_snapshot',
                      lambda _source_root, output: original(REPOSITORY, output))
        manifest = case_inputs.freeze_campaign_inputs(run, candidates=candidates, scene_manifest=source, **policies())
    scopes = case_inputs.write_case_scopes(run, inputs_manifest=manifest)
    frozen = verify_frozen_inputs(Path(manifest['path']))
    runtime = _load_runtime_config(RUNTIME_YAML)
    campaign = campaign_fixture(base)
    campaign['gpu_uuid'] = 'GPU-28221cec-9d21-7753-fd5a-da645740df19'
    campaign['controlled_runtime'] = ref(Path(manifest['path']).parent / frozen['roles']['runtime_config']['path'])
    campaign['teacher_service']['model']['model_id'] = runtime.yolo_model_id
    campaign_path = write_config(base, campaign)
    args = dict(campaign_config=load_campaign_config(campaign_path),
                collection_config_sha256=frozen['roles']['collection_config']['sha256'],
                scene_manifest_sha256=frozen['scene_manifest']['sha256'])
    return dict(base=base, root=root, run=run, source=source, candidates=candidates, manifest=manifest, scopes=scopes,
                frozen=frozen, campaign=campaign, campaign_path=campaign_path, args=args,
                binding=case_inputs.campaign_binding(manifest, **args))


def forged_copy(world, tmp_path, mutate):
    """A copy of the frozen set with `mutate(document, directory)` applied and the hash chain recomputed; returns its ref."""
    directory = tmp_path / f'forged-{next(FORGERIES)}'
    shutil.copytree(Path(world['manifest']['path']).parent, directory)
    path = directory / 'inputs-manifest.json'
    document = json.loads(path.read_bytes())
    mutate(document, directory)
    rehash(path, document)
    return ref(path)


def rewrite_role(document, directory, role, edit):
    entry = document['roles'][role]
    target = directory / entry['path']
    value = json.loads(target.read_bytes())
    edit(value)
    payload = _canonical(value)
    target.write_bytes(payload)
    entry.update(sha256=hashlib.sha256(payload).hexdigest(), bytes=len(payload))


def refused(code, call, *args, **kwargs):
    with pytest.raises(ValueError, match=code):
        call(*args, **kwargs)


def endpoint_fields(campaign):
    return {role: dict(role=role, socket_path='/act/ipc/' + role + '/inference.sock',
                       service_generation='service-' + role, max_frame_bytes=campaign[role + '_service']['max_frame_bytes'])
            for role in ('head', 'teacher')}


def task_for(world, tmp_path, monkeypatch, scene):
    """The shard spec and a task input document for `scene`, in the shape the Host writes and the container loads."""
    from so101_demo.runtime.container_campaign import task_builder

    root = tmp_path / ('owned-' + scene)
    (root / 'task-inputs').mkdir(parents=True)
    session = 'session-' + scene
    runtime_path = RUNTIME_YAML
    binding, frozen, campaign = world['binding'], world['frozen'], world['campaign']
    identity = dict(manifest_sha256='a' * 64, runtime_config_sha256=campaign['controlled_runtime']['sha256'],
                    collection_config_sha256=frozen['roles']['collection_config']['sha256'],
                    contact_policy_fingerprint=binding['contact_policy_fingerprint'])
    spec = dict(workload_kind='act_collection', campaign_id='campaign-1', worker_id='w00', launch_generation=1,
                execution_generation=1, simulation_session_id=session, owned_root=str(root),
                business_identity=identity, parallel_runtime=ref(runtime_path),
                campaign_config=ref(world['campaign_path']), deadline_monotonic_s=time.monotonic() + 3600,
                wave_id='wave-0', gpu_uuid=campaign['gpu_uuid'])
    document = dict(schema_version=1, kind=task_builder.KIND, task_id='task-1', worker_id='w00', launch_generation=1,
                    wave_id='wave-0', scene_id=scene, scene_manifest=binding['scene_manifest'],
                    scope=world['scopes'][scene]['scope'], inputs_manifest=world['scopes'][scene]['inputs_manifest'],
                    collection_mode=frozen['mode'])
    endpoints = endpoint_fields(campaign)
    # the launched service roles are whatever the loader's closed field set names
    document.update({role: endpoints[role] for role in ('head', 'teacher') if role in task_builder._FIELDS})
    monkeypatch.delenv('ROS_NAMESPACE', raising=False)
    for name, value in dict(ROS_DOMAIN_ID='181', ROS_LOCALHOST_ONLY='1', ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',
                            SO101_ACT_INSTANCE_ROOT=str(root), SO101_MUJOCO_SESSION_ID=session,
                            MUJOCO_GL='egl').items():
        monkeypatch.setenv(name, value)
    path = root / 'task-inputs' / 'task-1.json'
    path.write_text(json.dumps(document))
    return TaskSpec(task_id='task-1', inputs_ref=InputRef(**ref(path)), deadline_monotonic_s=time.monotonic() + 1800), spec


def test_case_inputs_are_mountable_and_hash_bound(world, tmp_path, monkeypatch):
    from so101_demo.runtime.container_campaign import task_builder

    run, manifest, scopes, frozen = world['run'], world['manifest'], world['scopes'], world['frozen']
    inputs = run / 'inputs'
    refs = [manifest, world['binding']['scene_manifest'], *(item[name] for item in scopes.values()
                                                            for name in ('scope', 'inputs_manifest'))]
    assert manifest['path'] == str(inputs / 'frozen' / 'inputs-manifest.json')
    for item in refs:
        assert set(item) == {'path', 'sha256'} and Path(item['path']).is_relative_to(inputs)
        assert sha(item['path']) == item['sha256']
    assert world['binding']['scene_manifest']['path'] == str(inputs / 'frozen' / 'scene_manifest' / 'scenes.json')
    assert frozen['mode'] == 'formal' and frozen['scene_manifest']['scene_count'] == 2
    for scene, item in scopes.items():
        assert item['inputs_manifest'] == manifest
        scope = read_collection_scope(item['scope']['path'], expected_mode='formal',
                                      expected_inputs_sha256=frozen['inputs_sha256'])
        assert scope['scene_id'] == scene
    # the real mount rules accept the one inputs directory as a read-only input, and nothing under the run root besides it
    shard = run / 'wave-0' / 'w00' / 'g1'
    (shard / 'control').mkdir(parents=True)
    sockets = {'head': run / 'ipc' / 'head', 'teacher': run / 'ipc' / 'teacher', 'control': shard / 'control'}
    mounts = build_role_mounts('shard', owned_root=shard, approved_inputs=(inputs,), socket_roots=sockets, config_paths=())
    assert [(mount.source, mount.target, mount.read_only) for mount in mounts if mount.purpose == 'input'] == [
        (inputs, inputs, True)]
    # the real per-case artifact writers accept both scopes as formal, scene-bound cases
    worker = tmp_path / 'worker'
    worker.mkdir(mode=0o700)
    artifacts = CollectionCaseArtifacts(worker_id='w00', launch_generation=1, worker_root=worker, case_inputs=scopes)
    assert set(artifacts.writers) == {'scene-a', 'scene-b'}
    # the real container loader accepts the Host-shaped task of two different non-default scenes
    for row in ROWS:
        task, spec = task_for(world, tmp_path, monkeypatch, row['scene_id'])
        loaded = task_builder.load_task_input(task, spec,teacher_socket=TEACHER_SOCKET)
        assert loaded.scene_id == row['scene_id'] and loaded.row == row
        assert loaded.refs['scope'] == scopes[row['scene_id']]['scope']
        assert loaded.refs['inputs_manifest'] == manifest


def test_binding_refuses_runtime_or_collection_hash_drift(world, tmp_path):
    args = world['args']
    campaign = copy.deepcopy(args['campaign_config'])
    campaign['controlled_runtime']['sha256'] = 'e' * 64
    refused('CASE_INPUTS_RUNTIME_CONFIG_MISMATCH', case_inputs.campaign_binding, world['manifest'],
            **dict(args, campaign_config=campaign))
    refused('CASE_INPUTS_COLLECTION_CONFIG_MISMATCH', case_inputs.campaign_binding, world['manifest'],
            **dict(args, collection_config_sha256='e' * 64))
    refused('CASE_INPUTS_SCENE_MANIFEST_MISMATCH', case_inputs.campaign_binding, world['manifest'],
            **dict(args, scene_manifest_sha256='e' * 64))
    # a manifest that is not the frozen file's own bytes is not read at all
    refused('CASE_INPUTS_MANIFEST_REF_INVALID', case_inputs.campaign_binding, dict(world['manifest'], sha256='e' * 64), **args)
    # a set that is not formal, and a formal set binding no scene list, are not campaign inputs
    refused('CASE_INPUTS_NOT_FORMAL', case_inputs.campaign_binding, forged_copy(
        world, tmp_path, lambda document, _: (document.pop('scene_manifest'), document.update(
            mode='preselected_target_diagnostic'))), **args)


def test_fingerprint_derives_from_frozen_proposal_and_receipt(world, tmp_path):
    frozen, run = world['frozen'], Path(world['manifest']['path']).parent
    proposal = json.loads((run / frozen['roles']['contact_proposal']['path']).read_bytes())
    receipt = json.loads((run / frozen['roles']['contact_activation']['path']).read_bytes())
    fingerprint = world['binding']['contact_policy_fingerprint']
    assert fingerprint == proposal['policy_fingerprint'] == policy_fingerprint(proposal['payload'])
    assert fingerprint == receipt['policy_fingerprint']
    assert world['binding'] == case_inputs.campaign_binding(world['manifest'], **world['args'])
    # neither the proposal's recorded fingerprint, its payload, nor the receipt may disagree
    def stale_proposal_field(document, directory):
        rewrite_role(document, directory, 'contact_proposal', lambda value: value.update(policy_fingerprint='f' * 64))

    def edited_payload(document, directory):
        rewrite_role(document, directory, 'contact_proposal',
                     lambda value: value['payload'].update(policy_id='another-policy'))

    def other_receipt(document, directory):
        rewrite_role(document, directory, 'contact_activation', lambda value: value.update(policy_fingerprint='f' * 64))

    for edit in (stale_proposal_field, edited_payload, other_receipt):
        forged = forged_copy(world, tmp_path, edit)
        refused('CASE_INPUTS_CONTACT_POLICY_MISMATCH', case_inputs.campaign_binding, forged, **world['args'])


def test_spot_check_receipt_refused_for_formal(world, tmp_path):
    # the freeze itself refuses a plan-signed candidate receipt for a formal set and leaves no frozen directory behind
    registry = _registry(tmp_path)
    registry['roles']['contact_activation']['selected']['approval'] = 'spot_check_candidate'
    registry['roles']['contact_activation']['candidates'][0]['approval'] = 'spot_check_candidate'
    root = tmp_path / 'evidence'
    root.mkdir()
    run = make_campaign_paths(root, 'run-spot')['run']
    refused('INPUT_NOT_APPROVED', case_inputs.freeze_campaign_inputs, run, candidates=_write_registry(tmp_path, registry),
            scene_manifest=scene_file(tmp_path), **policies())
    assert not (run / 'inputs' / 'frozen').exists()
    # a self-consistent forged manifest that names such a receipt is refused at the binding too
    forged = forged_copy(world, tmp_path, lambda document, _: document['roles']['contact_activation'].update(
        approval='spot_check_candidate'))
    refused('CASE_INPUTS_CONTACT_APPROVAL_INVALID', case_inputs.campaign_binding, forged, **world['args'])


def test_freeze_refuses_an_existing_frozen_directory(world):
    refused('INPUT_OUTPUT_EXISTS', case_inputs.freeze_campaign_inputs, world['run'], candidates=world['candidates'],
            scene_manifest=world['source'], **policies())


def test_scopes_cover_exactly_the_bound_rows_and_are_not_overwritten(world):
    run, scopes, frozen = world['run'], world['scopes'], world['frozen']
    directory = run / 'inputs' / 'scopes'
    assert set(scopes) == {row['scene_id'] for row in ROWS}
    assert sorted(path.name for path in directory.iterdir()) == ['scene-a.json', 'scene-b.json']
    for row in ROWS:
        document = json.loads(Path(scopes[row['scene_id']]['scope']['path']).read_bytes())
        assert document == build_collection_scope('formal', scene_id=row['scene_id'], seed=row['seed'],
                                                  inputs_sha256=frozen['inputs_sha256'])
    before = {path.name: path.read_bytes() for path in directory.iterdir()}
    refused('CASE_SCOPES_EXIST', case_inputs.write_case_scopes, run, inputs_manifest=world['manifest'])
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == before
    # a manifest of another run's frozen set is not this run's input
    other = make_campaign_paths(world['root'], 'run-other')['run']
    refused('CASE_INPUTS_LOCATION_INVALID', case_inputs.write_case_scopes, other, inputs_manifest=world['manifest'])
    assert not (other / 'inputs').exists()


def test_disk_floor_comes_from_frozen_runtime_policy(world, tmp_path):
    assert world['binding']['disk_floor_bytes'] == world['frozen']['runtime_policy']['hard_stops'][
        'disk_free_min_bytes'] == DISK_FLOOR

    def raised_floor(document, _):
        from so101_demo.act.endpoint_pose_acceptance import validate_development_runtime
        policy = document['runtime_policy']
        policy['hard_stops'] = dict(policy['hard_stops'], disk_free_min_bytes=2 * DISK_FLOOR)
        policy['sha256'] = hashlib.sha256(_canonical(validate_development_runtime(
            {'kind': 'ACT_ENDPOINT_DEVELOPMENT_RUNTIME', 'schema_version': 1,
             **{key: value for key, value in policy.items() if key != 'sha256'}}))).hexdigest()

    forged = forged_copy(world, tmp_path, raised_floor)
    assert case_inputs.campaign_binding(forged, **world['args'])['disk_floor_bytes'] == 2 * DISK_FLOOR
    # a set frozen without a runtime policy has no floor to read
    refused('CASE_INPUTS_RUNTIME_POLICY_MISSING', case_inputs.campaign_binding, forged_copy(
        world, tmp_path, lambda document, _: document.pop('runtime_policy')), **world['args'])


# ---- the camera rig is part of the frozen inputs and of the controlled identity --------------------------------------------------

def test_a_campaign_freeze_always_records_its_rig_profile_and_the_default_is_head_wrist_rig(world):
    from so101_demo.act.rig_profile import DEFAULT_RIG, HEAD_WRIST_RIG, rig_from_frozen
    frozen = world['frozen']
    binding = frozen['rig_profile']
    assert binding['path'] == 'policies/rig_profile.yaml' and binding['policy_sha256'] == HEAD_WRIST_RIG.profile_sha256
    assert rig_from_frozen(frozen).document == DEFAULT_RIG.document
    assert world['binding']['rig_profile_sha256'] == HEAD_WRIST_RIG.profile_sha256
    assert (Path(world['manifest']['path']).parent / binding['path']).is_file()


@pytest.fixture(scope='module')
def side_world(world, tmp_path_factory):
    """One real formal freeze under the side+wrist rig: its execution snapshot is that of the side+wrist scene."""
    from so101_demo.act import execution_snapshot
    from so101_demo.act.rig_profile import SIDE_WRIST_RIG

    base = tmp_path_factory.mktemp('case-inputs-side')
    probe = execution_snapshot.freeze_execution_snapshot(REPOSITORY, base / 'probe', SIDE_WRIST_RIG)
    scene_bytes = (base / 'probe' / probe['scene_path']).read_bytes()
    candidates = _write_registry(base, bound_registry(base, probe, scene_bytes))
    root = base / 'evidence'
    root.mkdir()
    run = make_campaign_paths(root, 'run-1')['run']
    original = execution_snapshot.freeze_execution_snapshot
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(execution_snapshot, 'freeze_execution_snapshot',
                      lambda _source_root, output, rig=None: original(REPOSITORY, output, rig))
        manifest = case_inputs.freeze_campaign_inputs(run, candidates=candidates, scene_manifest=scene_file(base),
                                                      rig_profile=CONFIG / 'rig-v2.yaml', **policies())
    frozen = verify_frozen_inputs(Path(manifest['path']))
    scopes = case_inputs.write_case_scopes(run, inputs_manifest=manifest)
    side_campaign = dict(world['campaign'], rig_profile_sha256=SIDE_WRIST_RIG.profile_sha256)
    campaign_path = write_config(base, side_campaign)
    args = dict(campaign_config=load_campaign_config(campaign_path),
                collection_config_sha256=frozen['roles']['collection_config']['sha256'],
                scene_manifest_sha256=frozen['scene_manifest']['sha256'])
    return dict(base=base, manifest=manifest, frozen=frozen, args=args, snapshot=probe, scopes=scopes,
                campaign=side_campaign, campaign_path=campaign_path, run=run,
                binding=case_inputs.campaign_binding(manifest, **args))


def test_a_side_wrist_campaign_freezes_the_side_wrist_snapshot_and_binds_only_a_side_wrist_campaign(world, side_world):
    from so101_demo.act.rig_files import rig_model_files
    from so101_demo.act.rig_profile import HEAD_WRIST_RIG, SIDE_WRIST_RIG, rig_from_frozen

    frozen = side_world['frozen']
    assert rig_from_frozen(frozen) is SIDE_WRIST_RIG
    execution = Path(side_world['manifest']['path']).parent / frozen['execution_snapshot']['path']
    files = rig_model_files(SIDE_WRIST_RIG)
    assert json.loads((execution / 'execution-manifest.json').read_bytes())['scene_path'] == files.scene
    assert frozen['execution_snapshot']['model_identity']['nq'] == 13
    assert frozen['roles']['scene_model']['identity']['scene_sha256'] == hashlib.sha256(
        (PACKAGE_ROOT / files.scene).read_bytes()).hexdigest()
    # its physics chunk configuration is the side+wrist plugin config's, not the head+wrist one
    assert frozen['execution_snapshot']['physics_chunks']['config_sha256'] == hashlib.sha256(
        (PACKAGE_ROOT / files.plugins).read_bytes()).hexdigest()
    binding = case_inputs.campaign_binding(side_world['manifest'], **side_world['args'])
    assert binding['rig_profile_sha256'] == SIDE_WRIST_RIG.profile_sha256
    # the rig enters the inputs hash chain: the two campaigns share no inputs digest
    assert frozen['inputs_sha256'] != world['frozen']['inputs_sha256']
    # a campaign config that names no rig, or the other one, is not this freeze's
    campaign_config = side_world['args']['campaign_config']
    no_rig = {key: value for key, value in campaign_config.items() if key != 'rig_profile_sha256'}
    head_rig = dict(campaign_config, rig_profile_sha256=HEAD_WRIST_RIG.profile_sha256)
    for config in (no_rig, head_rig):
        refused('CASE_INPUTS_RIG_PROFILE_MISMATCH', case_inputs.campaign_binding, side_world['manifest'],
                **dict(side_world['args'], campaign_config=config))


def test_the_container_loads_the_rig_the_frozen_inputs_bind_and_refuses_a_campaign_that_names_another(world, side_world,
                                                                                                    tmp_path, monkeypatch):
    from so101_demo.act.rig_profile import DEFAULT_RIG, HEAD_WRIST_RIG, SIDE_WRIST_RIG
    from so101_demo.runtime.container_campaign import task_builder

    side_task = dict(world, scopes=side_world['scopes'], frozen=side_world['frozen'], binding=side_world['binding'],
                     campaign=side_world['campaign'], campaign_path=side_world['campaign_path'])
    task, spec = task_for(side_task, tmp_path / 'side', monkeypatch, 'scene-a')
    assert task_builder.load_task_input(task, spec, teacher_socket=TEACHER_SOCKET).rig is SIDE_WRIST_RIG
    task, spec = task_for(world, tmp_path / 'head', monkeypatch, 'scene-a')
    loaded = task_builder.load_task_input(task, spec, teacher_socket=TEACHER_SOCKET)
    assert loaded.rig is HEAD_WRIST_RIG is DEFAULT_RIG
    # a head+wrist freeze under a campaign config that names the side+wrist rig is not a task of that campaign
    mismatched = dict(world, campaign_path=side_world['campaign_path'])
    task, spec = task_for(mismatched, tmp_path / 'mismatch', monkeypatch, 'scene-a')
    refused('COLLECTION_CASE_RIG_MISMATCH', task_builder.load_task_input, task, spec, teacher_socket=TEACHER_SOCKET)


def test_a_rig_forged_into_a_frozen_set_of_another_rigs_snapshot_is_refused(world, tmp_path):
    from so101_demo.act.rig_profile import SIDE_WRIST_RIG, dump_rig_profile
    from so101_demo.act.diagnostic_episode_inputs import rig_profile_binding

    def to_v2(document, directory):
        payload = dump_rig_profile(SIDE_WRIST_RIG)
        (directory / 'policies' / 'rig_profile.yaml').write_bytes(payload)
        document['rig_profile'] = rig_profile_binding(payload)

    # a self-consistent forger changes the profile only: the execution snapshot is still the head+wrist scene's
    refused('INPUTS_RIG_SCENE_MISMATCH', verify_frozen_inputs, Path(forged_copy(world, tmp_path, to_v2)['path']))


def test_a_frozen_set_and_a_campaign_config_that_name_different_rigs_are_refused(world, tmp_path):
    from so101_demo.act.rig_profile import HEAD_WRIST_RIG, SIDE_WRIST_RIG

    # the campaign config names rig v2 (its hash), the frozen set is rig v1
    v2_config = dict(world['args']['campaign_config'], rig_profile_sha256=SIDE_WRIST_RIG.profile_sha256)
    refused('CASE_INPUTS_RIG_PROFILE_MISMATCH', case_inputs.campaign_binding, world['manifest'],
            **dict(world['args'], campaign_config=v2_config))
    # the campaign config names rig v1 explicitly: the same as naming none
    v1_config = dict(world['args']['campaign_config'], rig_profile_sha256=HEAD_WRIST_RIG.profile_sha256)
    assert case_inputs.campaign_binding(world['manifest'], **dict(world['args'], campaign_config=v1_config)) == world['binding']


def test_a_frozen_set_sealed_before_rig_profiles_is_head_wrist_rig_and_still_binds_a_head_wrist_campaign(world, tmp_path):
    from so101_demo.act.rig_profile import HEAD_WRIST_RIG, rig_from_frozen

    legacy = forged_copy(world, tmp_path, lambda document, _: document.pop('rig_profile'))
    assert 'rig_profile' not in verify_frozen_inputs(Path(legacy['path']))
    assert rig_from_frozen(verify_frozen_inputs(Path(legacy['path']))) is HEAD_WRIST_RIG
    assert case_inputs.campaign_binding(legacy, **world['args'])['rig_profile_sha256'] == HEAD_WRIST_RIG.profile_sha256


def test_an_altered_rig_profile_file_is_refused_with_its_binding_intact(world, tmp_path):
    def tamper(document, directory):
        path = directory / 'policies' / 'rig_profile.yaml'
        path.write_bytes(path.read_bytes() + b'# edited\n')

    refused('INPUTS_RIG_PROFILE_INVALID', verify_frozen_inputs,
            Path(forged_copy(world, tmp_path, tamper)['path']))


def test_the_campaign_config_may_name_a_rig_and_only_by_a_sha256(world, tmp_path):
    campaign = dict(world['campaign'], rig_profile_sha256='f' * 64)
    loaded = load_campaign_config(write_config(tmp_path, campaign))
    assert loaded['rig_profile_sha256'] == 'f' * 64
    for bad in ('F' * 64, 'f' * 63, 5):
        with pytest.raises(ValueError, match='CAMPAIGN_CONFIG_INVALID'):
            load_campaign_config(write_config(tmp_path, dict(world['campaign'], rig_profile_sha256=bad)))


# ---- the spot-check plane: one diagnostic-mode scene row, a candidate or an activation receipt -----------------------------------

@pytest.fixture(scope='module')
def spot_world(world, tmp_path_factory):
    """One real spot-check freeze (diagnostic mode, one scene row, a spot_check_candidate receipt), its scope and binding."""
    from so101_demo.act import execution_snapshot

    base = tmp_path_factory.mktemp('case-inputs-spot')
    probe = execution_snapshot.freeze_execution_snapshot(REPOSITORY, base / 'probe')
    scene_bytes = (base / 'probe' / probe['scene_path']).read_bytes()
    registry = bound_registry(base, probe, scene_bytes)
    activation = registry['roles']['contact_activation']
    for entry in (activation['selected'], activation['candidates'][0]):
        entry['approval'] = 'spot_check_candidate'
    candidates = _write_registry(base, registry)
    root = base / 'evidence'
    root.mkdir()
    run = make_campaign_paths(root, 'run-spot')['run']
    original = execution_snapshot.freeze_execution_snapshot
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(execution_snapshot, 'freeze_execution_snapshot',
                      lambda _source_root, output: original(REPOSITORY, output))
        manifest = case_inputs.freeze_campaign_inputs(run, candidates=candidates, plane='spot_check',
                                                      scene_manifest=scene_file(base, ROWS[:1]), **policies())
    scopes = case_inputs.write_case_scopes(run, inputs_manifest=manifest, plane='spot_check')
    frozen = verify_frozen_inputs(Path(manifest['path']))
    runtime = ref(Path(manifest['path']).parent / frozen['roles']['runtime_config']['path'])
    campaign_path = write_config(base, dict(world['campaign'], controlled_runtime=runtime))
    args = dict(campaign_config=load_campaign_config(campaign_path),
                collection_config_sha256=frozen['roles']['collection_config']['sha256'],
                scene_manifest_sha256=frozen['scene_manifest']['sha256'])
    return dict(base=base, root=root, run=run, manifest=manifest, scopes=scopes, frozen=frozen, args=args,
                candidates=candidates, binding=case_inputs.campaign_binding(manifest, plane='spot_check', **args))


def test_a_spot_check_freeze_is_diagnostic_one_row_and_its_scope_is_in_that_mode(spot_world):
    frozen, scopes = spot_world['frozen'], spot_world['scopes']
    assert frozen['mode'] == 'preselected_target_diagnostic' and frozen['scene_manifest']['scene_count'] == 1
    assert frozen['roles']['contact_activation']['approval'] == 'spot_check_candidate'
    assert set(scopes) == {'scene-a'}
    scope = read_collection_scope(scopes['scene-a']['scope']['path'], expected_mode='preselected_target_diagnostic',
                                  expected_inputs_sha256=frozen['inputs_sha256'])
    assert scope == build_collection_scope('preselected_target_diagnostic', scene_id='scene-a', seed=ROWS[0]['seed'],
                                           inputs_sha256=frozen['inputs_sha256'])
    proposal = json.loads((Path(spot_world['manifest']['path']).parent
                           / frozen['roles']['contact_proposal']['path']).read_bytes())
    assert spot_world['binding']['contact_policy_fingerprint'] == policy_fingerprint(proposal['payload'])


def test_planes_and_frozen_modes_must_agree(world, spot_world):
    # the formal and qualification planes keep formal mode; the spot-check plane needs the diagnostic mode
    for plane in ('formal', 'qualification'):
        refused('CASE_INPUTS_NOT_FORMAL', case_inputs.campaign_binding, spot_world['manifest'], plane=plane,
                **spot_world['args'])
        assert case_inputs.campaign_binding(world['manifest'], plane=plane, **world['args']) == world['binding']
    refused('CASE_INPUTS_NOT_FORMAL', case_inputs.campaign_binding, spot_world['manifest'], **spot_world['args'])
    refused('CASE_INPUTS_NOT_SPOT_CHECK', case_inputs.campaign_binding, world['manifest'], plane='spot_check',
            **world['args'])
    refused('CASE_INPUTS_PLANE_INVALID', case_inputs.campaign_binding, world['manifest'], plane='diagnostic',
            **world['args'])
    # scopes: written once per row, in the frozen mode, and only for the plane that mode belongs to
    fresh = make_campaign_paths(spot_world['root'], 'run-spot-other')['run']
    refused('CASE_INPUTS_LOCATION_INVALID', case_inputs.write_case_scopes, fresh, inputs_manifest=spot_world['manifest'],
            plane='spot_check')
    refused('CASE_INPUTS_NOT_FORMAL', case_inputs.write_case_scopes, spot_world['run'],
            inputs_manifest=spot_world['manifest'])
    refused('CASE_INPUTS_NOT_SPOT_CHECK', case_inputs.write_case_scopes, world['run'], inputs_manifest=world['manifest'],
            plane='spot_check')
    refused('CASE_SCOPES_EXIST', case_inputs.write_case_scopes, spot_world['run'], inputs_manifest=spot_world['manifest'],
            plane='spot_check')


def test_a_candidate_receipt_is_accepted_only_by_the_spot_check_plane(world, spot_world, tmp_path):
    # the formal planes refuse a candidate approval even in a self-consistent forged formal set
    forged = forged_copy(world, tmp_path, lambda document, _: document['roles']['contact_activation'].update(
        approval='spot_check_candidate'))
    for plane in ('formal', 'qualification'):
        refused('CASE_INPUTS_CONTACT_APPROVAL_INVALID', case_inputs.campaign_binding, forged, plane=plane,
                **world['args'])
    # the spot-check plane accepts the candidate and also a user activation (design Q5), and refuses any other approval
    as_user = forged_copy(spot_world, tmp_path, lambda document, _: document['roles']['contact_activation'].update(
        approval='user_activation'))
    accepted = case_inputs.campaign_binding(as_user, plane='spot_check', **spot_world['args'])
    assert accepted['contact_policy_fingerprint'] == spot_world['binding']['contact_policy_fingerprint']
    other = forged_copy(spot_world, tmp_path, lambda document, _: document['roles']['contact_activation'].update(
        approval='source_controlled'))
    refused('CASE_INPUTS_CONTACT_APPROVAL_INVALID', case_inputs.campaign_binding, other, plane='spot_check',
            **spot_world['args'])


def test_a_spot_check_freeze_refuses_more_than_one_scene_and_the_formal_freeze_still_refuses_a_candidate(spot_world,
                                                                                                         tmp_path):
    root = tmp_path / 'evidence'
    root.mkdir()
    run = make_campaign_paths(root, 'run-two')['run']
    refused('INPUT_SCENE_MANIFEST_INVALID', case_inputs.freeze_campaign_inputs, run, candidates=spot_world['candidates'],
            plane='spot_check', scene_manifest=scene_file(tmp_path), **policies())
    assert not (run / 'inputs' / 'frozen').exists()
    one = scene_file(tmp_path, ROWS[:1], 'one.json')
    refused('CASE_INPUTS_PLANE_INVALID', case_inputs.freeze_campaign_inputs, run, candidates=spot_world['candidates'],
            plane='other', scene_manifest=one, **policies())
    refused('INPUT_NOT_APPROVED', case_inputs.freeze_campaign_inputs, run, candidates=spot_world['candidates'],
            scene_manifest=one, **policies())
