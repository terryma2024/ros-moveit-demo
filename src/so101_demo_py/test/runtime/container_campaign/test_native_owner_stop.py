"""Host stop path of one native instance: what its stop proof proves, and what each failure leaves fenced.

A native stop is confirmed only when all of these hold: the signal went to the exact registered leader only; the instance's own
retirement wrote its original stop receipt with all four facts; and the Host then read the leader gone, its process group
empty, no process still carrying the instance marker, and the Host ROS graph on the fixed domain clear. Real: the owner, the
registry, the instance program in a real subprocess with its own `NativeShardRetirement`, real strays. Controlled doubles: the
ROS stack and the Host ROS graph probe (see `native_instance_world`).
"""

import asyncio
import json
import os
import signal
import time

import pytest

from native_instance_world import build_world
from so101_demo.runtime.container_campaign.native_stop import marker_survivors
from so101_demo.runtime.container_campaign.registry import ContainerLaunch


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return open(f'/proc/{pid}/stat').read().rsplit(')', 1)[1].split()[0] != 'Z'


def next_generation(world):
    root = world.root.parent/'g2'
    root.mkdir(exist_ok=True)
    return ContainerLaunch(launch_id='measurement-w00-g2', role='shard', worker_id='w00', wave_id='measurement',
        launch_generation=2, container_name=None, image_digest=None, owned_root=str(root), session_id='campaign-w00-g2',
        launcher='native')


def run(world, body):
    try:
        return asyncio.run(body())
    finally:
        world.cleanup()


def test_close_signals_only_the_registered_leader_and_the_instances_own_retirement_confirms(tmp_path, monkeypatch):
    world = build_world(tmp_path, monkeypatch)
    signals = []
    real_kill = os.kill
    monkeypatch.setattr(os, 'kill', lambda pid, number: signals.append((pid, number)) or real_kill(pid, number))
    async def body():
        await world.owner.start()
        leader = world.owner.owner.pid
        signals.clear()
        receipt = await world.owner.close()
        assert receipt == dict(terminated=True, launch_id=world.launch.launch_id, errors=[])
        assert signals == [(leader, signal.SIGTERM)]                        # one TERM, to the leader pid, nothing else
        exit_document = world.registry.records()[0]['exit_inspect']
        assert exit_document['kind'] == 'native_instance_exit' and exit_document['pid'] == leader
        assert exit_document['leader_state'] in ('absent', 'zombie')
        assert exit_document['group_members'] == [] and exit_document['marker_survivors'] == []
        assert exit_document['graph_clear'] is True
        # the instance's own receipt carries all four facts and was not forced
        stop = json.loads((world.root/'shard-stop.json').read_text())
        assert [stop[name] for name in ('goals_stopped', 'controllers_stopped', 'ros_children_exited', 'ros_graph_empty',
                                        'forced')] == [True, True, True, True, False]
        assert json.loads((world.root/'host-cleanup.json').read_text())['signalled_groups'] == []
        assert (await world.owner.close()) == receipt                         # idempotent: no second signal
        assert len(signals) == 1
        world.registry.register(next_generation(world))                      # the slot is reusable only now
    run(world, body)


def test_an_instance_that_ignores_term_is_not_confirmed_and_keeps_the_slot_fenced(tmp_path, monkeypatch):
    world = build_world(tmp_path, monkeypatch, mode='ignore_term', stop_budget=.6)
    async def body():
        await world.owner.start()
        receipt = await world.owner.close()
        assert receipt['terminated'] is False and receipt['errors'][0]['reason'] == 'SHARD_NATIVE_EXIT_UNCONFIRMED'
        assert world.registry.records()[0]['exit_inspect'] is None
        assert pid_alive(world.owner.owner.pid)                               # no escalation: the stop stays unproven
        with pytest.raises(ValueError, match='LAUNCH_COLLISION: slot not retired'):
            world.registry.register(next_generation(world))
        running = await world.owner.prove_stopped()
        assert running['terminated'] is False
    run(world, body)


def test_a_group_and_graph_clear_exit_without_the_instances_own_receipt_is_not_a_stop(tmp_path, monkeypatch):
    world = build_world(tmp_path, monkeypatch, mode='hard_exit')
    async def body():
        await world.owner.start()
        receipt = await world.owner.close()
        assert receipt['terminated'] is False and receipt['errors'][0]['reason'] == 'LAUNCH_STOP_UNCONFIRMED'
        assert not (world.root/'shard-stop.json').exists()
        assert not pid_alive(world.owner.owner.pid)
        observed = json.loads((world.root/'final-exit.json').read_text())
        assert observed['leader_state'] in ('absent', 'zombie') and observed['group_members'] == []
        assert observed['marker_survivors'] == [] and observed['graph_clear'] is True     # the Host facts alone hold
        assert world.registry.records()[0]['exit_inspect'] is None
    run(world, body)


def test_a_host_ros_graph_that_is_not_clear_is_not_a_stop_until_it_is_read_clear_again(tmp_path, monkeypatch):
    world = build_world(tmp_path, monkeypatch)
    world.graph_clear = False
    async def body():
        await world.owner.start()
        receipt = await world.owner.close()
        assert receipt['terminated'] is False and receipt['errors'][0]['reason'] == 'LAUNCH_STOP_UNCONFIRMED'
        assert json.loads((world.root/'final-exit.json').read_text())['graph_clear'] is False
        with pytest.raises(ValueError, match='LAUNCH_COLLISION: slot not retired'):
            world.registry.register(next_generation(world))
        world.graph_clear = True
        proven = await world.owner.prove_stopped()                            # a late proof sends no signal
        assert proven == dict(terminated=True, launch_id=world.launch.launch_id, errors=[])
        assert (world.root/'late-exit-proof.json').is_file()
        world.registry.register(next_generation(world))
    run(world, body)


def test_a_probe_that_fails_is_not_a_clear_graph(tmp_path, monkeypatch):
    world = build_world(tmp_path, monkeypatch)
    def broken():
        raise OSError('ros2 not runnable')
    world.owner.graph_probe = broken
    async def body():
        await world.owner.start()
        receipt = await world.owner.close()
        assert receipt['terminated'] is False
        assert json.loads((world.root/'final-exit.json').read_text())['graph_clear'] is False
    run(world, body)


@pytest.mark.parametrize('mode', ['orphan', 'group_orphan'])
def test_leftovers_are_terminated_recorded_and_make_the_stop_unconfirmed_for_good(tmp_path, monkeypatch, mode):
    world = build_world(tmp_path, monkeypatch, mode=mode)
    async def body():
        await world.owner.start()
        leader = world.owner.owner
        await asyncio.to_thread(wait_for_stray, world.root, leader.started_ticks)
        stray = marker_survivors(world.root, started_ticks=leader.started_ticks)
        assert stray                                                         # a real process outlives the retiring instance
        receipt = await world.owner.close()
        assert receipt['terminated'] is False and receipt['errors'][0]['reason'] == 'SHARD_NATIVE_LEFTOVERS_TERMINATED'
        leftovers = json.loads((world.root/'native-leftovers.json').read_text())['signalled_groups']
        assert leftovers and all(item['survivors'] == [] for item in leftovers)
        assert not any(pid_alive(pid) for pid in stray)                       # terminated, not left running
        assert marker_survivors(world.root, started_ticks=leader.started_ticks) == []
        assert world.registry.records()[0]['exit_inspect'] is None
        # the Host observations are clean now, but a stop that needed leftovers terminated is never confirmed later
        again = await world.owner.prove_stopped()
        assert again['terminated'] is False and again['errors'][0]['reason'] == 'SHARD_NATIVE_LEFTOVERS_TERMINATED'
        with pytest.raises(ValueError, match='LAUNCH_COLLISION: slot not retired'):
            world.registry.register(next_generation(world))
    run(world, body)


def wait_for_stray(root, started_ticks):
    deadline = time.monotonic()+10
    while not marker_survivors(root, started_ticks=started_ticks) and time.monotonic() < deadline:
        time.sleep(.05)


def test_prove_stopped_sends_no_signal_and_never_confirms_a_running_instance(tmp_path, monkeypatch):
    world = build_world(tmp_path, monkeypatch)
    signals = []
    async def body():
        await world.owner.start()
        real_kill = os.kill
        monkeypatch.setattr(os, 'kill', lambda pid, number: signals.append((pid, number)) or real_kill(pid, number))
        running = await world.owner.prove_stopped()
        assert running['terminated'] is False and running['errors'][0]['reason'] == 'LAUNCH_STOP_UNCONFIRMED'
        assert signals == [] and pid_alive(world.owner.owner.pid)
        monkeypatch.undo()
        assert (await world.owner.close())['terminated'] is True
    run(world, body)


def test_a_drifted_leader_identity_is_never_signalled(tmp_path, monkeypatch):
    """The registered key no longer names the process at the pid (as after pid reuse): nothing is signalled, nothing proven."""
    from dataclasses import replace
    world = build_world(tmp_path, monkeypatch)
    signals = []
    async def body():
        await world.owner.start()
        real = world.owner.owner
        world.owner.owner = replace(real, started_ticks=real.started_ticks+1)
        real_kill = os.kill
        monkeypatch.setattr(os, 'kill', lambda pid, number: signals.append((pid, number)) or real_kill(pid, number))
        receipt = await world.owner.close()
        monkeypatch.undo()
        assert signals == [] and receipt['terminated'] is False
        world.owner.owner = real
    run(world, body)


def test_the_unidentified_process_is_not_left_running(tmp_path, monkeypatch):
    """A process spawned but never identified is ours, so it is stopped, yet no stop is claimed for it."""
    from so101_demo.runtime.container_campaign import native_owner
    world = build_world(tmp_path, monkeypatch, mode='ignore_term')
    def unreadable(pid):
        raise ValueError('PROCESS_OWNER_NOT_LIVE')
    monkeypatch.setattr(native_owner, 'read_process_owner', unreadable)
    async def body():
        with pytest.raises(ValueError, match='SHARD_NATIVE_IDENTITY_UNAVAILABLE'):
            await world.owner.start()
        pid = world.owner.process.pid
        receipt = await world.owner.close()
        assert receipt['terminated'] is False and receipt['errors'][0]['reason'] == 'LAUNCH_OWNER_UNKNOWN'
        assert world.owner.process.poll() is not None and not pid_alive(pid)
    run(world, body)
