"""Fixed mount derivation and immutable ID-bearing result files, without motion."""

import hashlib
import importlib
import json
import shutil
from pathlib import Path

import pytest

from test_case_artifacts import fixture as case_fixture
from so101_demo.parallel_batch.contracts.identity import LeaseIdentity
from so101_demo.runtime.parallel_ros_ports.observations import ResetBoundaryReceipt
from test_launch import fixture as launch_fixture, build as launch_argv


def results_module():
    import so101_demo.runtime.container_campaign as package
    assert (Path(package.__file__).parent/'task_results.py').is_file(), 'task result writer missing'
    return importlib.import_module('so101_demo.runtime.container_campaign.task_results')


def test_fixed_output_mount_and_distinct_instances(tmp_path):
    paths = importlib.import_module('so101_demo.runtime.container_campaign.paths')
    run = paths.make_campaign_paths(tmp_path, 'new-run')
    mounts = []
    for worker in ('w00', 'w01'):
        owned = run['run']/'wave-00'/worker/'g1'
        owned.mkdir(parents=True)
        (owned/'control').mkdir()
        (owned/'output').mkdir()
        values = paths.build_role_mounts('shard', owned_root=owned, approved_inputs=(),
            config_paths=(), socket_roots=run['socket_roots']|{'control': owned/'control'},
            task_output_root=owned/'output')
        output = next(m for m in values if m.purpose == 'task_output')
        mounts.append(output)
        assert output.target == Path('/act/output') and output.read_only is False
        assert output.source == owned/'output'
        assert not output.source.is_relative_to(run['host'])
    assert mounts[0].source != mounts[1].source


def test_task_workspace_not_overwritten(tmp_path):
    module = results_module()
    first = module.reserve_task_output(tmp_path, 'task-001')
    second = module.reserve_task_output(tmp_path, 'task-002')
    assert first == tmp_path/'tasks/task-001'
    assert second == tmp_path/'tasks/task-002'
    with pytest.raises(ValueError):
        module.reserve_task_output(tmp_path, 'task-001')


def test_collection_requires_only_matching_task_id(tmp_path):
    module = results_module()
    module.reserve_task_output(tmp_path, 'task-001')
    business = dict(teacher_task_result='FAILED', act_data_status='INVALID', act_data_qc='FAIL')
    module.write_task_result(tmp_path, 'task-001', business)
    observed = module.read_task_result(tmp_path, 'task-001')
    assert observed == {'task_id': 'task-001', 'result': business}
    path = tmp_path/'tasks/task-001/task-result.json'
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    module.read_task_result(tmp_path, 'task-001')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    with pytest.raises(ValueError):
        module.write_task_result(tmp_path, 'task-001', {'teacher_task_result': 'PASSED'})


@pytest.mark.parametrize('problem', ['missing_id', 'other_id', 'duplicate_id', 'symlink'])
def test_foreign_or_symlink_output_refused(tmp_path, problem):
    module = results_module()
    root = module.reserve_task_output(tmp_path, 'task-001')
    if problem == 'missing_id':
        (root/'task-result.json').write_text('{"result":{}}')
    elif problem == 'other_id':
        (root/'task-result.json').write_text('{"task_id":"task-002","result":{}}')
    elif problem == 'duplicate_id':
        (root/'task-result.json').write_text('{"task_id":"other","task_id":"task-001","result":{}}')
    else:
        foreign = tmp_path/'foreign.json'
        foreign.write_text('{"task_id":"task-001","result":{}}')
        (root/'task-result.json').symlink_to(foreign)
    with pytest.raises(ValueError):
        module.read_task_result(tmp_path, 'task-001')


def test_original_store_binds_under_task_directory(tmp_path):
    module = importlib.import_module('so101_demo.runtime.container_campaign.case_artifacts')
    refs = case_fixture(tmp_path)
    output = tmp_path/'output'
    output.mkdir()
    try:
        artifacts = module.CollectionCaseArtifacts(worker_id='w00', launch_generation=1,
            worker_root=output, case_inputs={'scene-a': refs['scene-a']}, clock=lambda: 11.,
            task_id='task-001')
    except TypeError as error:
        pytest.fail('task-local artifact binding missing: '+str(error))
    lease = LeaseIdentity('batch', 1, 'w00', 1, 'scene-a', 'attempt-scene-a', 1, 10., 100.)
    reset = ResetBoundaryReceipt('reset-2', 'session', 10.5, 1., 2)
    assert artifacts.reserve_workspace(lease, reset) is True
    assert artifacts.workspace(lease).path == output/'tasks/task-001/attempts/scene-a/attempt-scene-a/working'
    assert not (output/'attempts').exists()


def test_collection_launch_requires_and_mounts_fixed_output(tmp_path):
    module, images, paths = launch_fixture(tmp_path, 'shard')
    paths['entry'].spec.write_text(json.dumps({'workload_kind': 'act_collection'}))
    with pytest.raises(ValueError):
        launch_argv(module, images, paths)
    output = paths['owned_root']/'output'
    output.mkdir(mode=0o700)
    argv = launch_argv(module, images, paths)
    assert 'type=bind,src='+str(output)+',dst=/act/output' in argv


def test_missing_task_directory_is_a_refused_recovery(tmp_path):
    with pytest.raises(ValueError):
        results_module().read_task_result(tmp_path, 'missing-task')


def test_fixed_output_cannot_bind_another_instances_directory(tmp_path):
    paths = importlib.import_module('so101_demo.runtime.container_campaign.paths')
    run = paths.make_campaign_paths(tmp_path, 'new-run')
    owned = run['run']/'wave-00/w00/g1'
    owned.mkdir(parents=True)
    (owned/'control').mkdir()
    foreign = run['run']/'wave-00/w01/g1/output'
    foreign.mkdir(parents=True)
    with pytest.raises(ValueError):
        paths.build_role_mounts('shard', owned_root=owned, approved_inputs=(),
            config_paths=(), socket_roots=run['socket_roots']|{'control': owned/'control'},
            task_output_root=foreign)


def test_sealed_paths_readable_on_host_without_rewrite(tmp_path):
    """External mount is controlled; real output bytes and readback are unchanged."""
    module = results_module()
    container_output = tmp_path/'container-output'
    host_output = tmp_path/'host-output'
    container_output.mkdir()
    task = module.reserve_task_output(container_output, 'task-001')
    sealed = task/'attempts/scene-a/attempt-a/sealed'
    sealed.mkdir(parents=True)
    (sealed/'episode.json').write_bytes(b'{"original_stamp":123,"source":"camera"}\n')
    relative = 'attempts/scene-a/attempt-a/sealed/episode.json'
    module.write_task_result(container_output, 'task-001', {'episode_relative_path': relative})
    # Model the same mounted data under a different Host root, without editing it.
    shutil.copytree(container_output, host_output)
    recovered = module.read_task_result(host_output, 'task-001')
    assert recovered['result']['episode_relative_path'] == relative
    actual = host_output/'tasks/task-001'/relative
    assert actual.read_bytes() == b'{"original_stamp":123,"source":"camera"}\n'
    for name in ('task-result.json', relative):
        assert (host_output/'tasks/task-001'/name).read_bytes() == (task/name).read_bytes()
