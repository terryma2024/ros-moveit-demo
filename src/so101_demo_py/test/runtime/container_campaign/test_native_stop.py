"""Host observation of a native instance's exit, on real short-lived processes.

Real: the kernel identity reader, process groups and sessions, signals, and a fixture `/proc` tree for the cases a test user
cannot create (an unreadable environment). The Host ROS graph probe is the only controlled double.
"""

import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from so101_demo.runtime.act_instance.identity import INSTANCE_ROOT_ENV
from so101_demo.runtime.container_campaign.native_stop import (
    UNREADABLE, group_survivors, leader_state, marker_survivors, observe_native_exit, stop_descendants,
)
from so101_demo.runtime.container_campaign.process_identity import NativeOwnerKey, native_exit_proven, read_process_owner

#: Everything the tests spawn starts after this process; older processes with unreadable environments (the session manager) are skipped.
SINCE_TEST_START = read_process_owner(os.getpid()).started_ticks
SLEEP = [sys.executable, '-c', 'import time; time.sleep(120)']


@pytest.fixture
def spawned():
    processes = []
    def spawn(argv=SLEEP, *, environment=None, session=True):
        process = subprocess.Popen(argv, start_new_session=session, env=environment, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
        processes.append(process)
        return process
    yield spawn
    for process in processes:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except OSError:
            pass
        process.kill()
        process.wait()


def key_of(process):
    deadline = time.monotonic()+5
    while True:
        try:
            return NativeOwnerKey.from_process(read_process_owner(process.pid), launch_generation=1)
        except ValueError:          # the process is still settling after exec
            if time.monotonic() > deadline:
                raise
            time.sleep(.02)


def wait_until(condition):
    deadline = time.monotonic()+10
    while not condition() and time.monotonic() < deadline:
        time.sleep(.02)
    assert condition()


def test_the_leader_is_live_then_a_zombie_then_absent(spawned):
    process = spawned()
    key = key_of(process)
    assert leader_state(key) == 'live'
    process.kill()
    wait_until(lambda: leader_state(key) == 'zombie')                     # killed but not yet waited for
    process.wait()
    assert leader_state(key) == 'absent'


def test_a_different_process_at_the_pid_is_replaced_and_a_contradiction_is_unknown(spawned):
    from dataclasses import replace
    process = spawned()
    key = key_of(process)
    assert leader_state(replace(key, started_ticks=key.started_ticks+1)) == 'replaced'
    assert leader_state(replace(key, argv_sha256='c'*64)) == 'unknown'
    with pytest.raises(ValueError, match='NATIVE_OWNER_KEY_REQUIRED'):
        leader_state(read_process_owner(process.pid))


def test_group_members_outlive_the_leader_and_are_reported_until_gone(spawned):
    process = spawned(['/bin/sh', '-c', 'sleep 120 & sleep 120 & wait'])
    key = key_of(process)
    wait_until(lambda: len(group_survivors(key.pgid)) == 3)
    process.kill()
    process.wait()
    survivors = group_survivors(key.pgid)
    assert len(survivors) == 2 and key.pid not in survivors
    os.killpg(key.pgid, signal.SIGKILL)
    wait_until(lambda: group_survivors(key.pgid) == [])


def test_a_process_in_another_session_is_found_by_the_instance_marker_alone(spawned, tmp_path):
    root = tmp_path/'wave-0/w00/g1'
    marked = spawned(environment=dict(os.environ, **{INSTANCE_ROOT_ENV: str(root)}))
    other = spawned(environment=dict(os.environ, **{INSTANCE_ROOT_ENV: str(tmp_path/'wave-0/w00/g2')}))
    plain = spawned()
    wait_until(lambda: marker_survivors(root, started_ticks=SINCE_TEST_START) == [marked.pid])
    assert other.pid not in marker_survivors(root, started_ticks=SINCE_TEST_START) and plain.pid not in marker_survivors(root, started_ticks=SINCE_TEST_START)
    assert marker_survivors(root, started_ticks=SINCE_TEST_START, exclude=(marked.pid,)) == []
    marked.kill()
    marked.wait()
    assert marker_survivors(root, started_ticks=SINCE_TEST_START) == []                  # a finished process is not a survivor


def fixture_proc(tmp_path, entries):
    proc = tmp_path/'proc'
    proc.mkdir()
    for pid, (state, started, environ, mode) in entries.items():
        entry = proc/str(pid)
        entry.mkdir()
        fields = [state, '1'] + ['0']*17 + [str(started)]
        (entry/'stat').write_text(f'{pid} (name with ) paren) ' + ' '.join(fields))
        if environ is not None:
            (entry/'environ').write_bytes(environ)
            (entry/'environ').chmod(mode)
    return proc


def test_an_unreadable_environment_is_skipped_only_when_it_predates_the_instance(tmp_path):
    root = tmp_path/'g1'
    marker = f'{INSTANCE_ROOT_ENV}={root}'.encode()
    proc = fixture_proc(tmp_path, {
        10: ('S', 50, b'A=1\x00' + marker + b'\x00', 0o600),         # carries the marker
        11: ('Z', 150, b'', 0o600),                                   # zombie: not live
        12: ('S', 60, b'A=1\x00', 0o600),                             # no marker
        13: ('S', 90, b'A=1\x00', 0o000),                             # unreadable, older than the instance (session manager)
        14: ('S', 200, b'A=1\x00', 0o000),                            # unreadable, newer than the instance: cannot be ruled out
        15: ('S', 70, None, 0),                                       # exited between listing and reading
    })
    assert marker_survivors(root, started_ticks=100, proc=proc) == [10, UNREADABLE]
    assert marker_survivors(root, started_ticks=100, proc=proc, exclude=(10,)) == [UNREADABLE]
    (proc/'13'/'environ').chmod(0o600)
    (proc/'14'/'environ').chmod(0o600)


def test_the_exit_observation_is_the_document_the_proof_judges(spawned, tmp_path):
    root = tmp_path/'g1'
    root.mkdir()
    process = spawned(['/bin/sh', '-c', 'sleep 120 & wait'])
    key = key_of(process)
    live = observe_native_exit(key, root, graph_probe=lambda: True)
    assert live['leader_state'] == 'live' and live['group_members'] and native_exit_proven(key, live) is False
    process.kill()
    process.wait()
    leftover = observe_native_exit(key, root, graph_probe=lambda: True)
    assert leftover['leader_state'] == 'absent' and leftover['group_members'] and native_exit_proven(key, leftover) is False
    os.killpg(key.pgid, signal.SIGKILL)
    wait_until(lambda: group_survivors(key.pgid) == [])
    gone = observe_native_exit(key, root, graph_probe=lambda: True)
    assert native_exit_proven(key, gone) is True and gone['owned_root'] == str(root)
    assert native_exit_proven(key, observe_native_exit(key, root, graph_probe=lambda: False)) is False
    def broken():
        raise OSError('ros2 not runnable')
    assert observe_native_exit(key, root, graph_probe=broken)['graph_clear'] is False
    assert native_exit_proven(key, observe_native_exit(key, root, graph_probe=lambda: 'yes')) is False
    with pytest.raises(ValueError, match='NATIVE_OBSERVATION_CONFIG_INVALID'):
        observe_native_exit(key, root, graph_probe=None)


def test_descendants_are_terminated_only_when_provably_the_instances(spawned, tmp_path):
    root = tmp_path/'g1'
    marker = dict(os.environ, **{INSTANCE_ROOT_ENV: str(root)})
    leader = spawned(['/bin/sh', '-c', 'sleep 120 & wait'], environment=marker)                  # the leader's own group
    key = key_of(leader)
    stray = spawned(environment=marker)                                                            # another session
    # a group with a member that does not carry the marker: not provably the instance's, so left alone
    mixed_env = {name: value for name, value in os.environ.items()}
    mixed = spawned(['/bin/sh', '-c', f'env {INSTANCE_ROOT_ENV}={root} sleep 120 & wait'], environment=mixed_env)
    wait_until(lambda: len(group_survivors(key.pgid)) == 2 and len(marker_survivors(root, started_ticks=SINCE_TEST_START)) >= 4)
    leader.kill()
    leader.wait()

    signalled = stop_descendants(key, root, timeout_s=3., proc=Path('/proc'))

    pgids = sorted(item['pgid'] for item in signalled)
    assert key.pgid in pgids and stray.pid in pgids                                              # both groups, by pgid
    assert all(item['survivors'] == [] for item in signalled)
    assert stray.wait(10) is not None                                                              # terminated
    assert group_survivors(key.pgid) == []
    assert mixed.pid not in pgids and group_survivors(mixed.pid) != []                             # left alone
    remaining = marker_survivors(root, started_ticks=SINCE_TEST_START)
    assert remaining and all(os.getpgid(pid) == mixed.pid for pid in remaining)
    assert stop_descendants(key, root, timeout_s=1.) == []                                         # nothing else to do
