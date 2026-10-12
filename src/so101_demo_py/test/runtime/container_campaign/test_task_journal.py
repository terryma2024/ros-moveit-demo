"""Host task journal over real task-result files; attribution is task_id and the registered instance only.

Real: the journal, `task_results` files, `TaskSpec`. No simulator, container or qualification is involved.
"""

import hashlib
import json
from types import SimpleNamespace

import pytest

from so101_demo.runtime.container_campaign.paths import host_task_output
from so101_demo.runtime.container_campaign.task_contracts import InputRef, TaskSpec
from so101_demo.runtime.container_campaign.task_journal import (
    ContainerTaskJournal, read_container_task_result,
)
from so101_demo.runtime.container_campaign.task_results import reserve_task_output, write_task_result


def make_instance(base, worker='w00', wave='wave-0'):
    owned = base/wave/worker/'g1'
    (owned/'output').mkdir(parents=True)
    (owned/'task-inputs').mkdir()
    return owned


def make_world(tmp_path, workers=('w00',)):
    owners = {worker: make_instance(tmp_path/'run', worker) for worker in workers}
    instances = {f'wave-0-{worker}-g1': dict(owner_root=str(owned), worker_id=worker,
                 launch_generation=1, wave_id='wave-0') for worker, owned in owners.items()}
    journal = ContainerTaskJournal(tmp_path/'run/host/wave-0/task-journal', instances=instances,
                                   clock=iter(range(1, 100)).__next__)
    return SimpleNamespace(journal=journal, owners=owners, instances=instances, tmp=tmp_path)


def make_task(world, scene='s1', worker='w00', *, document=None):
    task_id = f'wave-0-{worker}-{scene}'
    path = world.owners[worker]/'task-inputs'/(task_id+'.json')
    path.write_text(json.dumps(document or dict(task_id=task_id, worker_id=worker, launch_generation=1,
                                                wave_id='wave-0', scene_id=scene)))
    task = TaskSpec(task_id=task_id, inputs_ref=InputRef(path=str(path),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest()), deadline_monotonic_s=1e9)
    return task, host_task_output(world.owners[worker], task_id), f'wave-0-{worker}-g1'


def assign(world, scene='s1', worker='w00'):
    task, output, instance = make_task(world, scene, worker)
    world.journal.assign(instance_id=instance, task=task, host_output=output)
    return task


def write_result(world, task, result, worker='w00'):
    reserve_task_output(world.owners[worker]/'output', task.task_id)
    write_task_result(world.owners[worker]/'output', task.task_id, result)


def test_collect_only_after_matching_success(tmp_path):
    world = make_world(tmp_path)
    task = assign(world)
    with pytest.raises(ValueError, match='TASK_RESULT_ID_OR_FILE_INVALID'):
        read_container_task_result(world.owners['w00'], task_id=task.task_id)
    write_result(world, task, dict(teacher_task_result='PASS'))
    result = read_container_task_result(world.owners['w00'], task_id=task.task_id)
    assert result['task_dir'] == str(host_task_output(world.owners['w00'], task.task_id))
    path = host_task_output(world.owners['w00'], task.task_id)/'task-result.json'
    assert result['task_result_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    record = world.journal.collect(task_id=task.task_id, result=result)
    assert record['result'] == dict(teacher_task_result='PASS') and record['scene_id'] == 's1'
    with pytest.raises(ValueError, match='TASK_JOURNAL_ALREADY_TERMINAL'):
        world.journal.collect(task_id=task.task_id, result=result)
    with pytest.raises(ValueError, match='TASK_JOURNAL_TASK_NOT_ASSIGNED'):
        world.journal.collect(task_id='wave-0-w00-unassigned', result=result)


def test_collection_requires_only_matching_task_id(tmp_path):
    world = make_world(tmp_path)
    task = assign(world)
    business = dict(teacher_task_result='FAILED', act_data_status='INVALID', act_data_qc='FAIL', junk=[1])
    write_result(world, task, business)
    record = world.journal.collect(task_id=task.task_id,
                                   result=read_container_task_result(world.owners['w00'], task_id=task.task_id))
    assert record['result'] == business
    rows = world.journal.records()
    assert rows[task.task_id]['collected'] == record and rows[task.task_id]['failed'] is None


def test_missing_or_mismatched_result_id_refused(tmp_path):
    world = make_world(tmp_path)
    task = assign(world)
    other = assign(world, 's2')
    write_result(world, task, dict(value=1))
    good = read_container_task_result(world.owners['w00'], task_id=task.task_id)
    with pytest.raises(ValueError, match='TASK_JOURNAL_RESULT_MISMATCH'):
        world.journal.collect(task_id=other.task_id, result=good)
    with pytest.raises(ValueError, match='TASK_JOURNAL_RESULT_MISMATCH'):
        world.journal.collect(task_id=task.task_id, result=good | {'task_id': other.task_id})
    with pytest.raises(ValueError, match='TASK_JOURNAL_RESULT_MISMATCH'):
        world.journal.collect(task_id=task.task_id, result=good | {'task_dir': str(world.tmp)})
    # A result file that names another task is refused at the reader.
    path = host_task_output(world.owners['w00'], task.task_id)/'task-result.json'
    path.write_text(json.dumps(dict(task_id=other.task_id, result={})))
    with pytest.raises(ValueError, match='TASK_RESULT_ID_OR_FILE_INVALID'):
        read_container_task_result(world.owners['w00'], task_id=task.task_id)
    assert world.journal.records()[task.task_id]['collected'] is None


def test_fail_cannot_replace_collected(tmp_path):
    world = make_world(tmp_path)
    task, failed_task = assign(world), assign(world, 's2')
    write_result(world, task, {})
    world.journal.collect(task_id=task.task_id,
                          result=read_container_task_result(world.owners['w00'], task_id=task.task_id))
    with pytest.raises(ValueError, match='TASK_JOURNAL_ALREADY_COLLECTED'):
        world.journal.fail(task_id=task.task_id, reason='late')
    record = world.journal.fail(task_id=failed_task.task_id, reason='x'*400)
    assert len(record['reason']) == 300
    assert world.journal.fail(task_id=failed_task.task_id, reason='again') == record
    write_result(world, failed_task, {})
    with pytest.raises(ValueError, match='TASK_JOURNAL_ALREADY_TERMINAL'):
        world.journal.collect(task_id=failed_task.task_id,
            result=read_container_task_result(world.owners['w00'], task_id=failed_task.task_id))
    rows = world.journal.records()
    assert rows[task.task_id]['collected'] and rows[failed_task.task_id]['failed']['reason'] == 'x'*300


def test_assign_refuses_foreign_output_or_duplicate_scene(tmp_path):
    world = make_world(tmp_path, ('w00', 'w01'))
    task, output, instance = make_task(world, 's1')
    foreign = host_task_output(world.owners['w01'], task.task_id)
    with pytest.raises(ValueError, match='TASK_JOURNAL_FOREIGN_OUTPUT'):
        world.journal.assign(instance_id=instance, task=task, host_output=foreign)
    with pytest.raises(ValueError, match='TASK_JOURNAL_INSTANCE_UNREGISTERED'):
        world.journal.assign(instance_id='wave-0-w09-g1', task=task, host_output=output)
    other_task, other_output, _ = make_task(world, 's9', 'w01')
    with pytest.raises(ValueError, match='TASK_JOURNAL_FOREIGN_OUTPUT'):
        world.journal.assign(instance_id=instance, task=other_task, host_output=other_output)
    wrong = make_task(world, 's3', document=dict(task_id='wave-0-w00-s3', worker_id='w01',
                      launch_generation=1, wave_id='wave-0', scene_id='s3'))
    with pytest.raises(ValueError, match='TASK_JOURNAL_INPUT_INVALID'):
        world.journal.assign(instance_id=wrong[2], task=wrong[0], host_output=wrong[1])
    assert world.journal.records() == {}
    world.journal.assign(instance_id=instance, task=task, host_output=output)
    with pytest.raises(ValueError, match='TASK_JOURNAL_SCENE_DUPLICATE'):
        assign(world, 's1', 'w01')
    with pytest.raises(ValueError, match='TASK_JOURNAL_SCENE_DUPLICATE'):
        world.journal.assign(instance_id=instance, task=task, host_output=output)
    assert list(world.journal.records()) == [task.task_id]


def test_symlink_or_foreign_owner_root_refused(tmp_path):
    world = make_world(tmp_path)
    link = tmp_path/'alias'
    link.symlink_to(world.owners['w00'], target_is_directory=True)
    for bad in (str(link), 'wave-0/w00/g1', str(tmp_path/'missing'), str(world.owners['w00']/'output'),
                str(world.owners['w00'].parent)):
        instances = {'a': dict(world.instances['wave-0-w00-g1'], owner_root=str(world.owners['w00'])),
                     'b': dict(world.instances['wave-0-w00-g1'], owner_root=bad)}
        with pytest.raises(ValueError, match='TASK_JOURNAL_INSTANCE_ROOT_INVALID'):
            ContainerTaskJournal(tmp_path/'journal-a', instances=instances)
    with pytest.raises(ValueError, match='TASK_JOURNAL_INSTANCE_ROOT_INVALID'):
        ContainerTaskJournal(world.owners['w00']/'journal', instances=world.instances)
    # An owner-root symlink reached through a registered task directory is refused by the readers.
    task = assign(world)
    write_result(world, task, {})
    target = world.tmp/'elsewhere'
    target.mkdir()
    (target/'task-result.json').write_text(json.dumps(dict(task_id=task.task_id, result={})))
    path = host_task_output(world.owners['w00'], task.task_id)
    (path/'task-result.json').unlink()
    (path/'task-result.json').symlink_to(target/'task-result.json')
    with pytest.raises(ValueError, match='TASK_RESULT_ID_OR_FILE_INVALID'):
        read_container_task_result(world.owners['w00'], task_id=task.task_id)
    with pytest.raises(ValueError, match='TASK_RESULT_ID_OR_FILE_INVALID'):
        read_container_task_result(link, task_id=task.task_id)


def test_records_reload_from_disk(tmp_path):
    world = make_world(tmp_path)
    task, second = assign(world), assign(world, 's2')
    write_result(world, task, dict(v=1))
    world.journal.collect(task_id=task.task_id,
                          result=read_container_task_result(world.owners['w00'], task_id=task.task_id))
    again = ContainerTaskJournal(world.journal.root, instances=world.instances)
    assert again.records() == world.journal.records()
    assert list(again.records()) == sorted([task.task_id, second.task_id])
    with pytest.raises(ValueError, match='TASK_JOURNAL_SCENE_DUPLICATE'):
        assign(SimpleNamespace(journal=again, owners=world.owners), 's2')


def test_half_built_journal_directory_fails_closed(tmp_path):
    world = make_world(tmp_path)
    (world.journal.root/'wave-0-w00-s1').mkdir()    # a crash between mkdir and the assigned record
    with pytest.raises(ValueError, match='TASK_JOURNAL_TASK_NOT_ASSIGNED'):
        world.journal.records()
    task, output, instance = make_task(world, 's2')
    with pytest.raises(ValueError, match='TASK_JOURNAL_TASK_NOT_ASSIGNED'):
        world.journal.assign(instance_id=instance, task=task, host_output=output)
    with pytest.raises(ValueError, match='TASK_JOURNAL_TASK_NOT_ASSIGNED'):
        world.journal.fail(task_id='wave-0-w00-s1', reason='x')
