"""The collection CLI runs one native single worker through the same campaign chain a container uses.

The world and every double are those of `test_container_task_campaign_integration` (admission, the SQLite store, GPU lease and
slot registry, frozen inputs, the Teacher service owner against a scripted Docker daemon, the coordinator, task control, the
task journal and `finish`). The one difference is the instance: `--instance-launcher native` makes the launcher a
`NativeInstanceLauncher`, so the instance is a real subprocess leading a process group of its own, running the real instance
program (`native_instance_world`), whose own stop receipt the real registry then verifies. As there, the four task operations
are answered by the scripted instance behind the control client, because the simulator, the Teacher and the episode are not
here; the wave readback is controlled the same way.
"""

import json
import os
from pathlib import Path
import shutil
import sys

import pytest

import native_instance_world
from test_container_task_campaign_integration import (  # noqa: F401  (fixtures and the world of the container chain)
    Spies, argv_for, controlled_verifier, make_world, run, shared,
)
from test_controller_stop import run_probe
from so101_demo.cli.act_collect_parallel import CollectionEdges, main
from so101_demo.runtime.container_campaign.native_owner import NativeInstanceOwner


def native_world(tmp_path, shared, monkeypatch, *, plane='W1', **options):
    world = make_world(tmp_path, shared, monkeypatch, plane=plane, **options)
    _, goals, _ = run_probe(monkeypatch)
    goal_file = world.root/'goal-stop.json'
    goal_file.write_bytes(goals.payload)
    install = world.root/'install'
    install.mkdir()
    edges = world.edges
    world.edges = CollectionEdges(environment=edges.environment, act_inventory=edges.act_inventory,
        act_host_id=edges.act_host_id, calibration_identity_probe=edges.calibration_identity_probe,
        docker_runner=edges.docker_runner, service_query=edges.service_query, namespace_reader=edges.namespace_reader,
        control_factory=edges.control_factory, install_prefix=install,
        native_edges=dict(ros2_executable=Path(shutil.which('ros2')), command=[sys.executable, str(Path(native_instance_world.__file__).resolve()), '--mode', 'serve',
                                   '--goal-stop', str(goal_file)],
                          base_environment=dict(os.environ), graph_probe_factory=lambda prefix, launch, env: (lambda: True)))
    return world


def test_the_native_single_worker_runs_the_whole_campaign_chain_and_settles(tmp_path, shared, monkeypatch, capsys):
    world = native_world(tmp_path, shared, monkeypatch, polls_to_finish=2)
    spies = Spies(monkeypatch)
    verified = controlled_verifier(monkeypatch)
    code, out, err = run(world, capsys, instance_launcher='native')
    assert code == 0, err
    summary = json.loads(out.strip().splitlines()[-1])
    assert summary['plane'] == 'qualification' and summary['scene_count'] == 8 and summary['waves'] == 1
    run_root = world.evidence/'run-one'
    (owner,) = spies.owners
    (shard,) = owner.shards
    assert type(shard) is NativeInstanceOwner and shard.launch.launcher == 'native'
    # admission recorded the launcher; the Teacher is still a container, the instance is not
    payload = json.loads(spies.workload.arbiter.store._query_one('SELECT payload_json FROM parents')['payload_json'])
    assert payload['instance_launcher'] == 'native' and payload['worker_count'] == 1
    assert len(world.docker.runs(shard=False)) == 1 and world.docker.runs(shard=True) == []
    # the layout seen from the Host is the container's: control, output/tasks/<task_id>, stack, retirement
    root = run_root/'wave-0/w00/g1'
    for name in ('control', 'output', 'stack', 'retirement', 'task-inputs', 'tmp'):
        assert (root/name).is_dir(), name
    documents = [entry[2] for entry in world.log if entry[1] == 'task_document']
    assert len(documents) == 8
    for document in documents:
        assert document['teacher']['socket_path'] == str(run_root/'ipc/teacher/inference.sock')      # the Host path
        assert (root/'output/tasks'/document['task_id']/'task-result.json').is_file()
        assert (run_root/'host/wave-0/task-journal'/document['task_id']/'collected.json').is_file()
    operations = [entry[1] for entry in world.log if entry[1] != 'task_document']
    assert operations.count('assign_task') == 8 and operations.count('terminate') == 1
    # the same wave verification: the unchanged class, built once, over the registry record of the native instance
    assert len(verified) == 1 and verified[0]['qualification'] is True
    # the stop was proven from the instance's own receipt and the Host observation, then settled
    cleanup = json.loads((run_root/'host/campaign-cleanup.json').read_bytes())
    assert cleanup['terminated'] is True and cleanup['shards'][0]['terminated'] is True
    observed = json.loads((root/'final-exit.json').read_bytes())
    assert observed['kind'] == 'native_instance_exit' and observed['leader_state'] in ('absent', 'zombie')
    assert observed['group_members'] == [] and observed['marker_survivors'] == [] and observed['graph_clear'] is True
    stop = json.loads((root/'shard-stop.json').read_bytes())
    assert [stop[name] for name in ('goals_stopped', 'controllers_stopped', 'ros_children_exited', 'ros_graph_empty',
                                    'forced')] == [True, True, True, True, False]
    assert len(spies.finishes) == 1 and spies.finishes[0][1] is True
    assert spies.lease() is None and spies.active_slots() == ()


def test_the_default_launcher_is_the_container_and_records_it(tmp_path, shared, monkeypatch, capsys):
    world = native_world(tmp_path, shared, monkeypatch)
    spies = Spies(monkeypatch)
    controlled_verifier(monkeypatch)
    code, out, err = run(world, capsys)
    assert code == 0, err
    payload = json.loads(spies.workload.arbiter.store._query_one('SELECT payload_json FROM parents')['payload_json'])
    assert payload['instance_launcher'] == 'container'
    assert len(world.docker.runs(shard=True)) == 1 and spies.owners[0].shards[0].launch.launcher == 'container'


def test_native_with_more_than_one_worker_is_refused_before_the_run_root_exists(tmp_path, shared, monkeypatch, capsys):
    world = native_world(tmp_path, shared, monkeypatch, plane='W8')
    code, out, err = run(world, capsys, instance_launcher='native')
    assert code == 2 and 'COLLECTION_NATIVE_SINGLE_WORKER_ONLY' in err
    assert not (world.evidence/'run-one').exists() and world.docker.calls == []


def test_an_unknown_launcher_is_refused_by_the_parser(tmp_path, shared, monkeypatch, capsys):
    world = native_world(tmp_path, shared, monkeypatch)
    with pytest.raises(SystemExit) as refused:
        main(argv_for(world, instance_launcher='docker'), edges=world.edges)
    assert refused.value.code == 2 and 'invalid choice' in capsys.readouterr().err


def test_a_native_run_is_refused_at_admission_while_a_container_slot_is_active(tmp_path, shared, monkeypatch, capsys):
    """The unified entry refuses before any resource: nothing is taken and no run directory content is spawned."""
    from dataclasses import asdict
    from so101_teleop.unified.worker_slots import ActWorkerSlot

    world = native_world(tmp_path, shared, monkeypatch)
    spies = Spies(monkeypatch)
    real_validate = __import__('so101_teleop.unified.worker_slots', fromlist=['x']).ActWorkerSlotRegistry.validate

    def hold_a_container_slot(registry, slots, *, launcher='container'):
        # a container campaign that is still admitted on this host
        registry.store._connection.execute('INSERT INTO act_worker_slots VALUES (?,?,?,?,1)',
            ('other-campaign', 'w00', 1, json.dumps(asdict(ActWorkerSlot('other-campaign', 'w00', 1)))))
        return real_validate(registry, slots, launcher=launcher)
    monkeypatch.setattr('so101_teleop.unified.worker_slots.ActWorkerSlotRegistry.validate', hold_a_container_slot)
    code, out, err = run(world, capsys, instance_launcher='native')
    assert code == 1 and 'ADMISSION_REFUSED' in err and 'NATIVE_INSTANCE_EXCLUSIVE' in err
    assert spies.lease() is None and world.docker.calls == []
