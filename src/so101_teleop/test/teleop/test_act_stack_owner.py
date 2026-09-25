"""A Task 8 stack needs its own process owner and terminal proof."""

import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import signal
import sys

import pytest

from so101_teleop.owned_group import terminate_group
from so101_teleop.unified.act_stack import ActStackLaunch, ActStackProcessOwner


def launch(tmp_path, code):
    class TestLaunch(ActStackLaunch):
        def argv(self):
            return [sys.executable, "-c", code]

    return TestLaunch(
        ros2_executable=Path(sys.executable), session_id="act-case-1",
        evidence_root=tmp_path, ros_domain_id=179, environment=dict(os.environ),
    )


def test_closed_production_stack_argv_is_headless_broker_free(tmp_path):
    item = ActStackLaunch(
        ros2_executable=Path(sys.executable), session_id="act-case-1",
        evidence_root=tmp_path, ros_domain_id=179, environment={},
    )
    assert item.argv() == [
        sys.executable, "launch", "so101_demo_py",
        "so101_mujoco_act_execution_stack.launch.py",
        "headless:=true", "sensor_rendering:=true", "act_profile:=true",
        "session_id:=act-case-1", f"task_evidence_root:={tmp_path}",
    ]


def test_live_stack_stops_exact_group_and_writes_receipt(tmp_path):
    async def run():
        item = ActStackProcessOwner(
            launch(tmp_path, "import time; time.sleep(120)"),
            ready_probe=lambda: True, stop_probe=lambda: True,
            graph_clear_probe=lambda: True,
        )
        try:
            owner = await item.start(timeout_s=3)
            assert owner.pid > 0 and owner.pgid == owner.pid
            await item.stop(timeout_s=0.2)
            receipt = json.loads((tmp_path / "cleanup-receipt.json").read_text())
            assert receipt["leader_pid"] == owner.pid
            assert receipt["group_clear"] is True
            assert receipt["graph_clear"] is True
            assert receipt["parent_exited"] is False
            assert item.owner is None
        finally:
            if item.owner is not None:
                terminate_group(pgid=item.owner.pgid, leader_pid=item.owner.pid, timeout_s=0.2)

    asyncio.run(run())


def test_exited_parent_only_retires_after_real_group_clear(tmp_path):
    async def run():
        item = ActStackProcessOwner(
            launch(tmp_path, "import time; time.sleep(.3)"),
            ready_probe=lambda: True, stop_probe=lambda: True,
            graph_clear_probe=lambda: True,
        )
        owner = await item.start(timeout_s=3)
        assert item.process.wait(timeout=3) == 0
        await item.stop(timeout_s=0.2)
        receipt = json.loads((tmp_path / "cleanup-receipt.json").read_text())
        assert receipt["parent_exited"] is True
        assert receipt["pgid"] == owner.pgid

    asyncio.run(run())


def test_exited_parent_with_surviving_descendant_stays_fenced(tmp_path):
    path = tmp_path / "descendant-pid.txt"
    code = (
        "import subprocess,sys,time; "
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']); "
        f"open({str(path)!r},'w').write(str(p.pid)); time.sleep(.3)"
    )

    async def run():
        item = ActStackProcessOwner(
            launch(tmp_path, code), ready_probe=lambda: path.exists(),
            stop_probe=lambda: True, graph_clear_probe=lambda: True,
        )
        child_pid = None
        try:
            owner = await item.start(timeout_s=3)
            child_pid = int(path.read_text())
            assert item.process.wait(timeout=3) == 0
            with pytest.raises(Exception, match="STOP_NOT_CONFIRMED"):
                await item.stop(timeout_s=0.2)
            assert item.owner == owner
            assert not (tmp_path / "cleanup-receipt.json").exists()
            os.kill(child_pid, 0)
        finally:
            if child_pid is not None:
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    asyncio.run(run())


@pytest.mark.parametrize("gate", ["stop", "graph"])
def test_missing_stop_or_graph_proof_cannot_retire(tmp_path, gate):
    async def run():
        item = ActStackProcessOwner(
            launch(tmp_path, "import time; time.sleep(120)"),
            ready_probe=lambda: True, stop_probe=lambda: gate != "stop",
            graph_clear_probe=lambda: gate != "graph",
        )
        try:
            owner = await item.start(timeout_s=3)
            with pytest.raises(Exception, match="STOP_NOT_CONFIRMED|GRAPH_NOT_CLEARED"):
                await item.stop(timeout_s=0.2)
            assert item.owner == owner
            assert not (tmp_path / "cleanup-receipt.json").exists()
        finally:
            if item.owner is not None:
                terminate_group(pgid=item.owner.pgid, leader_pid=item.owner.pid, timeout_s=0.2)

    asyncio.run(run())


def test_missing_readiness_keeps_spawned_stack_owned(tmp_path):
    async def run():
        item = ActStackProcessOwner(
            launch(tmp_path, "import time; time.sleep(120)"),
            ready_probe=lambda: False, stop_probe=lambda: True,
            graph_clear_probe=lambda: True,
        )
        try:
            with pytest.raises(Exception, match="ACT_STACK_READINESS_UNPROVED"):
                await item.start(timeout_s=0.1)
            assert item.owner is not None
            assert item.process.poll() is None
            assert not (tmp_path / "cleanup-receipt.json").exists()
        finally:
            if item.owner is not None:
                terminate_group(pgid=item.owner.pgid, leader_pid=item.owner.pid, timeout_s=0.2)

    asyncio.run(run())


def test_owner_pid_drift_or_receipt_failure_keeps_fence(tmp_path, monkeypatch):
    from so101_teleop.unified import act_stack

    async def run():
        item = ActStackProcessOwner(
            launch(tmp_path, "import time; time.sleep(120)"),
            ready_probe=lambda: True, stop_probe=lambda: True,
            graph_clear_probe=lambda: True,
        )
        owner = await item.start(timeout_s=3)
        try:
            item.owner = replace(owner, started_ticks=owner.started_ticks + 1)
            with pytest.raises(Exception, match="ACT_STACK_OWNER_IDENTITY_DRIFT"):
                await item.stop(timeout_s=0.2)
            assert item.process.poll() is None
            item.owner = owner

            def failed_receipt(_root, _document):
                raise OSError("fsync failed")

            monkeypatch.setattr(act_stack, "_write_retirement_receipt", failed_receipt)
            with pytest.raises(Exception, match="ACT_STACK_RECEIPT_FAILED"):
                await item.stop(timeout_s=0.2)
            assert item.owner == owner
            assert not (tmp_path / "cleanup-receipt.json").exists()
        finally:
            terminate_group(pgid=owner.pgid, leader_pid=owner.pid, timeout_s=0.2)

    asyncio.run(run())


def test_graph_clear_retry_does_not_requery_stopped_exited_stack(tmp_path):
    calls = {"stop": 0, "graph": 0}

    def physical_stop():
        calls["stop"] += 1
        if calls["stop"] > 1:
            raise ValueError("observer cannot run after stack exit")
        return True

    def graph_clear():
        calls["graph"] += 1
        return calls["graph"] > 1

    async def run():
        item = ActStackProcessOwner(
            launch(tmp_path, "import time; time.sleep(120)"),
            ready_probe=lambda: True, stop_probe=physical_stop,
            graph_clear_probe=graph_clear,
        )
        owner = await item.start(timeout_s=3)
        with pytest.raises(Exception, match="GRAPH_NOT_CLEARED"):
            await item.stop(timeout_s=0.2)
        assert item.owner == owner
        assert item.process.poll() is not None
        await item.stop(timeout_s=0.2)
        assert calls == {"stop": 1, "graph": 2}
        assert (tmp_path / "cleanup-receipt.json").exists()

    asyncio.run(run())
