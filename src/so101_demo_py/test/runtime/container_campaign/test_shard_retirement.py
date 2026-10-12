"""Generation retirement uses original four-lane/native evidence, never flags alone.

The stack/ROS ports below are explicit external I/O fixtures. Filesystem and
current process identity are real; these tests claim no physical stop.
"""

import asyncio
import importlib
import os
import time
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from so101_demo.runtime.container_campaign.process_identity import read_process_owner, pid_namespace_inode
from so101_demo.runtime.parallel_ipc.frames import canonical_json
from so101_teleop.unified.act_stack import ActStackLaunch, ActStackProcessOwner
from so101_teleop.unified.contracts import OwnerKey
from test_controller_stop import run_probe


def fixture(tmp_path, monkeypatch, *, forced=False, goal_failed=False, stack_failed=False):
    mod = importlib.import_module("so101_demo.runtime.container_campaign.retirement")
    _, goals, _ = run_probe(monkeypatch, bad_ack=1 if goal_failed else None)
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    stack_root = root / "stack"
    stack_root.mkdir(mode=0o700)
    owner = read_process_owner(os.getpid())
    native = OwnerKey(501, 501, 100, "a"*64, "b"*64)
    calls = []
    class Stack(ActStackProcessOwner):
        async def stop(self, **kwargs):
            calls.append("native-stop")
            if stack_failed:
                raise RuntimeError("NATIVE_STOP_UNCONFIRMED")
            (stack_root / "cleanup-receipt.json").write_bytes(canonical_json(dict(
                schema_version=1, leader_pid=native.pid, pgid=native.pgid, started_ticks=native.started_ticks,
                argv_sha256=native.argv_sha256, session_id="session1", ros_domain_id=181,
                group_clear=True, graph_clear=True, physical_stop_confirmed=True,
                parent_exited=False, term_sent=True, kill_sent=forced, finished_at_monotonic_ns=time.monotonic_ns())))
            self.process = self.owner = None
    launch = ActStackLaunch(ros2_executable=__import__('pathlib').Path('/usr/bin/true'),
        session_id="session1", evidence_root=stack_root, ros_domain_id=181, environment={})
    stack = Stack(launch, ready_probe=lambda: True, stop_probe=lambda: True, graph_clear_probe=lambda: True)
    stack.owner, stack.process = native, SimpleNamespace(pid=501)
    def goal_probe(**kwargs):
        calls.append("goal-stop")
        return goals
    retirement = mod.NativeShardRetirement(process_owner=owner, launch_generation=7,
        evidence_root=root, stack=stack, ros_namespace="/act/campaign/w00",
        goal_stop_budget_s=5, stack_stop_budget_s=15, goal_stop_probe=goal_probe)
    return mod, root, owner, native, retirement, calls


def test_concurrent_retirement_is_single_flight_and_originals_read_back(tmp_path, monkeypatch):
    mod, root, owner, native, retirement, calls = fixture(tmp_path, monkeypatch)
    async def run():
        first, second = await asyncio.gather(retirement.retire(fenced=True), retirement.retire(fenced=True))
        assert first == second
        assert first["generation"] == 7 and first["process_owner"] == asdict(owner)
        assert all(first[name] is True for name in ("goals_stopped", "controllers_stopped", "ros_children_exited", "ros_graph_empty"))
        assert first["forced"] is False
    asyncio.run(run())
    assert calls == ["goal-stop", "native-stop"]
    actual = mod.read_shard_stop_evidence(root, process_owner=owner, launch_generation=7,
        ros_namespace="/act/campaign/w00", session_id="session1", ros_domain_id=181, namespace_inode=pid_namespace_inode())
    assert actual["goals_stopped"] is True
    assert (root / "retirement/controller-stop.json").is_file()
    assert (root / "retirement/stack-stop.json").is_file()


@pytest.mark.parametrize('native_failure',[None,'forced','missing'])
def test_idle_empty_cancel_acks_need_full_unforced_native_termination(tmp_path,monkeypatch,native_failure):
    mod,root,owner,_native,retirement,calls = fixture(tmp_path,monkeypatch,
        forced=native_failure=='forced',stack_failed=native_failure=='missing')
    original = retirement.goal_probe
    def empty_idle(**kwargs):
        observation = original(**kwargs)
        document = observation.document
        for lane in document['lanes'].values():
            lane.update(goals_canceling=[],statuses=None,status_received_monotonic_ns=None)
        from so101_demo.runtime.container_campaign.controller_stop import ControllerStopObservation
        value = ControllerStopObservation(canonical_json(document))
        assert value.proven is False  # an empty ACK alone is never stop proof
        return value
    retirement.goal_probe = empty_idle
    receipt = asyncio.run(retirement.retire(fenced=True))
    if native_failure is None:
        assert receipt['goals_stopped'] is True
        actual = mod.read_shard_stop_evidence(root,process_owner=owner,launch_generation=7,
            ros_namespace='/act/campaign/w00',session_id='session1',ros_domain_id=181,
            namespace_inode=pid_namespace_inode())
        assert actual['goals_stopped'] is True
    else:
        assert receipt['goals_stopped'] is False
        with pytest.raises(ValueError,match='SHARD_STOP_EVIDENCE_UNCONFIRMED'):
            mod.read_shard_stop_evidence(root,process_owner=owner,launch_generation=7,
                ros_namespace='/act/campaign/w00',session_id='session1',ros_domain_id=181,
                namespace_inode=pid_namespace_inode())


@pytest.mark.parametrize('problem',['missing_ack','rejected_ack','active_status','canceling_goal'])
def test_native_termination_cannot_cover_uncertain_or_nonempty_goal_ack(tmp_path,monkeypatch,problem):
    mod,root,owner,_native,retirement,calls = fixture(tmp_path,monkeypatch)
    original = retirement.goal_probe
    def uncertain(**kwargs):
        observation = original(**kwargs)
        document = observation.document
        for lane in document['lanes'].values():
            lane.update(goals_canceling=[],statuses=None,status_received_monotonic_ns=None)
        lane = document['lanes']['neck']
        if problem == 'missing_ack':
            lane.update(cancel_return_code=None,cancel_received_monotonic_ns=None,goals_canceling=None)
        elif problem == 'rejected_ack': lane['cancel_return_code'] = 1
        elif problem == 'canceling_goal':
            lane['goals_canceling'] = [{'uuid':'a'*32,'stamp':{'sec':1,'nanosec':2}}]
        else:
            lane['statuses'] = [{'status':2,'goal':{'uuid':'a'*32,'stamp':{'sec':1,'nanosec':2}}}]
            lane['status_received_monotonic_ns'] = document['completed_monotonic_ns']
        from so101_demo.runtime.container_campaign.controller_stop import ControllerStopObservation
        return ControllerStopObservation(canonical_json(document))
    retirement.goal_probe = uncertain
    receipt = asyncio.run(retirement.retire(fenced=True))
    assert receipt['controllers_stopped'] is True and receipt['goals_stopped'] is False
    with pytest.raises(ValueError,match='SHARD_STOP_EVIDENCE_UNCONFIRMED'):
        mod.read_shard_stop_evidence(root,process_owner=owner,launch_generation=7,
            ros_namespace='/act/campaign/w00',session_id='session1',ros_domain_id=181,
            namespace_inode=pid_namespace_inode())


@pytest.mark.parametrize("problem", ["goal", "native", "forced"])
def test_uncertain_or_forced_stop_is_retained_and_never_retried(tmp_path, monkeypatch, problem):
    mod, root, owner, _native, retirement, calls = fixture(tmp_path, monkeypatch,
        goal_failed=problem=="goal", stack_failed=problem=="native", forced=problem=="forced")
    async def run():
        receipt = await retirement.retire(fenced=True)
        assert not (all(receipt[name] for name in ("goals_stopped", "controllers_stopped", "ros_children_exited", "ros_graph_empty")) and not receipt["forced"])
        assert await retirement.retire(fenced=True) == receipt
    asyncio.run(run())
    assert calls == ["goal-stop", "native-stop"]
    with pytest.raises(ValueError, match="SHARD_STOP_EVIDENCE_UNCONFIRMED"):
        mod.read_shard_stop_evidence(root, process_owner=owner, launch_generation=7,
            ros_namespace="/act/campaign/w00", session_id="session1", ros_domain_id=181, namespace_inode=pid_namespace_inode())


def test_unfenced_stop_cannot_invoke_ros_or_publish_receipt(tmp_path, monkeypatch):
    _, root, _owner, _native, retirement, calls = fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="SHARD_RETIREMENT_NOT_FENCED"):
        asyncio.run(retirement.retire(fenced=False))
    assert not calls and not (root / "shard-stop.json").exists()


@pytest.mark.parametrize("problem", ["raw_goal", "raw_native", "summary", "generation", "namespace", "session", "domain"])
def test_summary_and_original_evidence_scope_drift_rejected(tmp_path, monkeypatch, problem):
    import json

    mod, root, owner, _native, retirement, _calls = fixture(tmp_path, monkeypatch)
    asyncio.run(retirement.retire(fenced=True))
    kwargs = dict(process_owner=owner, launch_generation=7, ros_namespace="/act/campaign/w00",
                  session_id="session1", ros_domain_id=181, namespace_inode=pid_namespace_inode())
    if problem == "raw_goal": (root / "retirement/controller-stop.json").write_text('{}')
    elif problem == "raw_native": (root / "retirement/stack-stop.json").write_text('{}')
    elif problem == "summary":
        doc=json.loads((root / "shard-stop.json").read_bytes()); doc["forced"]=True
        (root / "shard-stop.json").write_bytes(canonical_json(doc))
    elif problem == "generation": kwargs["launch_generation"] = 8
    elif problem == "namespace": kwargs["ros_namespace"] = "/act/other/w00"
    elif problem == "session": kwargs["session_id"] = "other"
    elif problem == "domain": kwargs["ros_domain_id"] = 182
    with pytest.raises(ValueError, match="SHARD_STOP_EVIDENCE"):
        mod.read_shard_stop_evidence(root, **kwargs)


def test_process_identity_drift_during_stop_cannot_publish_success(tmp_path, monkeypatch):
    mod, root, _owner, _native, retirement, calls = fixture(tmp_path, monkeypatch)
    observations = iter([True, False])
    monkeypatch.setattr(mod, "process_owner_matches", lambda owner: next(observations))
    with pytest.raises(ValueError, match="SHARD_RETIREMENT_PROCESS_CHANGED"):
        asyncio.run(retirement.retire(fenced=True))
    assert calls == ["goal-stop", "native-stop"]
    assert not (root / "shard-stop.json").exists()
