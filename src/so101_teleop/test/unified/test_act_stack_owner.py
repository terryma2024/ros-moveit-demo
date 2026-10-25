"""A stack needs its own process owner and terminal proof."""

import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import sys
from types import SimpleNamespace

import pytest

from so101_teleop.owned_group import terminate_group
from so101_teleop.unified.act_stack import ActStackLaunch, ActStackProcessOwner
from so101_teleop.unified.bridge import _retirement_owner_state, identity_for
from so101_teleop.process_identity import read_identity


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


def test_shebang_owner_records_kernel_command_fingerprint(tmp_path):
    script = tmp_path / "ros2-like-script"
    ready = tmp_path / "ready"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys, time\n"
        "pathlib.Path(sys.argv[1]).write_text('ready')\n"
        "time.sleep(120)\n"
    )
    script.chmod(0o700)
    argv = [str(script), str(ready), "scope-exp292"]
    environment = dict(os.environ)
    process = subprocess.Popen(
        argv, env=environment, shell=False, start_new_session=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 5
        while not ready.exists():
            assert process.poll() is None
            assert time.monotonic() < deadline
            time.sleep(0.01)
        identity = read_identity(process.pid)
        owner = identity_for(process.pid, argv, environment)
        assert owner.argv_sha256 == identity.command_sha256
        assert _retirement_owner_state(owner) == "live"
    finally:
        terminate_group(pgid=process.pid, leader_pid=process.pid, timeout_s=0.2)
        process.wait(timeout=3)


def test_pre_setsid_identity_cannot_capture_the_parent_process_group(monkeypatch):
    import so101_teleop.unified.bridge as bridge_module

    pid = 12345
    argv = ["/tmp/owned-launch", "--scope", "exp292"]
    monkeypatch.setattr(bridge_module, "read_identity", lambda _pid: SimpleNamespace(
        argv=tuple(argv), pgid=pid - 1, start_marker=101,
        command_sha256="a" * 64,
    ))
    with pytest.raises(Exception, match="PROCESS_GROUP_NOT_ISOLATED"):
        identity_for(pid, argv, {})


def test_a_stack_with_a_scene_variant_is_launched_with_that_scene_and_none_other_is(tmp_path):
    profile = tmp_path / "rig-side.yaml"
    profile.write_text("rig: side-wrist\n")
    scene = tmp_path / "scene_variant.xml"
    scene.write_text("<mujoco/>")
    common = dict(ros2_executable=Path(sys.executable), session_id="act-case-1", evidence_root=tmp_path, ros_domain_id=179,
                  environment={}, rig="side-wrist", rig_profile=profile)
    plain = ActStackLaunch(**common)
    assert plain.mujoco_scene is None and not any(item.startswith("mujoco_scene:=") for item in plain.argv())
    varied = ActStackLaunch(**common, mujoco_scene=scene)
    assert varied.argv() == [*plain.argv(), f"mujoco_scene:={scene}"]
    for broken in (Path("scene.xml"), tmp_path / "missing.xml", tmp_path / ".." / "scene_variant.xml", tmp_path):
        with pytest.raises(ValueError, match="ACT_STACK_SCENE_INVALID"):
            ActStackLaunch(**common, mujoco_scene=broken)


def test_a_stack_of_another_rig_is_launched_with_the_rig_and_observed_with_its_profile(tmp_path):
    profile = tmp_path / "rig-side.yaml"
    profile.write_text("rig: side-wrist\n")
    common = dict(ros2_executable=Path(sys.executable), session_id="act-case-1", evidence_root=tmp_path,
                  ros_domain_id=179, environment={})
    default = ActStackLaunch(**common)
    assert default.rig == "head-wrist" and default.rig_profile is None and default.readiness_arguments() == []
    side = ActStackLaunch(**common, rig="side-wrist", rig_profile=profile)
    assert side.argv() == [*default.argv(), "rig:=side-wrist"]
    assert side.readiness_arguments() == ["--rig-profile", str(profile)]
    # the default rig is never given a profile argument, and any other rig must name an existing absolute profile file
    for kwargs in (dict(rig_profile=profile), dict(rig="side-wrist"), dict(rig="side-wrist", rig_profile=tmp_path / "missing"),
                   dict(rig="Side Wrist", rig_profile=profile), dict(rig="side-wrist", rig_profile=Path("rig-side.yaml"))):
        with pytest.raises(ValueError, match="ACT_STACK_RIG_INVALID"):
            ActStackLaunch(**common, **kwargs)


def test_a_declared_model_identity_needs_a_scene_variant_a_lowercase_sha_and_reaches_only_the_simulator_environment(tmp_path):
    from so101_teleop.unified.act_stack import DECLARED_MODEL_ENV, PROOF_SHA256_ENV

    scene = tmp_path / "scene_variant.xml"
    scene.write_text("<mujoco/>")
    common = dict(ros2_executable=Path(sys.executable), session_id="act-case-1", evidence_root=tmp_path, ros_domain_id=179)
    digest = "ab" * 32
    proof = "cd" * 32
    plain = ActStackLaunch(**common, environment={DECLARED_MODEL_ENV: "f" * 64, PROOF_SHA256_ENV: "e" * 64, "X": "1"})
    assert DECLARED_MODEL_ENV not in plain.process_environment() and PROOF_SHA256_ENV not in plain.process_environment()
    assert plain.process_environment()["X"] == "1"   # an override is never inherited
    declared = ActStackLaunch(**common, environment={"X": "1"}, mujoco_scene=scene, declared_model_sha256=digest, equivalence_proof_sha256=proof)
    assert declared.process_environment()[DECLARED_MODEL_ENV] == digest and declared.process_environment()[PROOF_SHA256_ENV] == proof
    assert declared.argv() == [*plain.argv(), f"mujoco_scene:={scene}"]
    for bad in ("A" * 64, "a" * 63, "g" * 64, "", 5):
        with pytest.raises(ValueError, match="ACT_STACK_DECLARED_MODEL_INVALID"):
            ActStackLaunch(**common, environment={}, mujoco_scene=scene, declared_model_sha256=bad, equivalence_proof_sha256=proof)
        with pytest.raises(ValueError, match="ACT_STACK_DECLARED_MODEL_INVALID"):
            ActStackLaunch(**common, environment={}, mujoco_scene=scene, declared_model_sha256=digest, equivalence_proof_sha256=bad)
    with pytest.raises(ValueError, match="ACT_STACK_DECLARED_MODEL_INVALID"):
        ActStackLaunch(**common, environment={}, declared_model_sha256=digest, equivalence_proof_sha256=proof)   # no variant scene
    # an override without its proof, and a proof without an override, are refused
    with pytest.raises(ValueError, match="ACT_STACK_DECLARED_MODEL_NEEDS_PROOF"):
        ActStackLaunch(**common, environment={}, mujoco_scene=scene, declared_model_sha256=digest)
    with pytest.raises(ValueError, match="ACT_STACK_DECLARED_MODEL_NEEDS_PROOF"):
        ActStackLaunch(**common, environment={}, mujoco_scene=scene, equivalence_proof_sha256=proof)


def test_a_stopped_stack_relaunches_with_another_scene_and_a_running_one_does_not(tmp_path):
    from so101_teleop.unified.contracts import MutationError

    scene = tmp_path / "scene_variant.xml"
    scene.write_text("<mujoco/>")

    async def run():
        first = launch(tmp_path, "import time; time.sleep(120)")
        item = ActStackProcessOwner(first, ready_probe=lambda: True, stop_probe=lambda: True, graph_clear_probe=lambda: True)
        owner = await item.start(timeout_s=3)
        second = replace(first, mujoco_scene=scene, declared_model_sha256="cd" * 32, equivalence_proof_sha256="ef" * 32)
        with pytest.raises(MutationError, match="ACT_STACK_RELAUNCH_WHILE_RUNNING"):
            item.relaunch_with(second, ready_probe=lambda: True)
        await item.stop(timeout_s=0.2)
        (tmp_path / "cleanup-receipt.json").rename(tmp_path / "cleanup-receipt-0.json")
        for changed in (replace(first, session_id="act-case-2"), replace(first, ros_domain_id=178),
                        replace(first, environment={"Y": "2"})):
            with pytest.raises(MutationError, match="ACT_STACK_RELAUNCH_IDENTITY_CHANGED"):
                item.relaunch_with(changed, ready_probe=lambda: True)
        with pytest.raises(ValueError, match="ACT_STACK_OWNER_CONFIG_INVALID"):
            item.relaunch_with(second, ready_probe=None)
        probes = []
        item.relaunch_with(second, ready_probe=lambda: probes.append(1) or True)
        assert item.launch is second and item.owner is None and item.process is None
        again = await item.start(timeout_s=3)
        assert probes and again.pid != owner.pid
        await item.stop(timeout_s=0.2)
        assert json.loads((tmp_path / "cleanup-receipt.json").read_text())["leader_pid"] == again.pid
        assert json.loads((tmp_path / "cleanup-receipt-0.json").read_text())["leader_pid"] == owner.pid

    asyncio.run(run())
