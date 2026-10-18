"""The container start path of a stack, offline: the instance launch, the shard's probes and the stack owner, for each rig.

EXP-7001 (the first container run of the side+wrist rig) failed `SHARD_START_FAILED` because the start probe validated the
observer's output against a check set that named `head_rgb`. This drives the same path the shard program composes
(`instance_stack_launch` -> `compose_stack` -> `ActStackProcessOwner.start` -> the task gates' repeatable check -> `stop`)
with the real readiness evaluation of the rig as the observer's output; only the ROS subprocess is a double (the `run` seam).
Real here: the rig profile file the launch hands the observer, `act_stack_ready.evaluate_act_stack_readiness` for that rig,
the start probe, the repeatable ready check, the stop probe, and the stack owner with a real process group.
"""

from dataclasses import fields
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from paths import PACKAGE_ROOT

from so101_demo.act.rig_profile import DEFAULT_RIG, HEAD_WRIST_RIG, SIDE_WRIST_RIG, load_rig_profile
from so101_demo.cli.act_stack_ready import actions_for, controllers_for, evaluate_act_stack_readiness
from so101_demo.runtime.act_instance.program import compose_stack, instance_stack_launch
from so101_teleop.unified.act_stack import ActStackLaunch

NOW_S = 100.0
NOW_NS = 100_000_000_000
SESSION = "act-composition-02"


def observer_output(argv) -> bytes:
    """What the installed observer prints for a healthy stack of the rig named by its `--rig-profile` argument (none = rig v1)."""
    options = dict(zip(argv[1::2], argv[2::2]))
    rig = DEFAULT_RIG if "--rig-profile" not in options else load_rig_profile(options["--rig-profile"])
    joint_width = 7 if rig.has_neck else 6
    result = evaluate_act_stack_readiness(
        session_id=options["--session-id"], ros_domain_id=int(options["--ros-domain-id"]), now_s=NOW_S,
        worlds=tuple({"session_id": options["--session-id"], "reset_epoch": 0, "step": step, "sim_time_s": 10.0 + step / 1000,
                      "paused": False, "received_s": NOW_S - 0.1 + n * 0.09} for n, step in enumerate((100, 125))),
        joints=tuple({"stamp_s": 10.1 + n * 0.02, "received_s": NOW_S - 0.06 + n * 0.02,
                      "velocity": (0.0,) * joint_width} for n in range(3)),
        rgb={camera: {"stamp_s": 10.125, "received_s": NOW_S - 0.02, "width": 640, "height": 480, "encoding": "rgb8",
                      "step": 1920, "byte_count": 640 * 480 * 3} for camera in rig.camera_names},
        controllers={name: "active" for name in controllers_for(rig)},
        services={name: True for name in ("/apply_planning_scene", "/get_planning_scene", "/plan_kinematic_path")},
        actions={name: True for name in actions_for(rig)}, rig=rig)
    assert result.ready, result.failure_code
    return (json.dumps(result.artifact, sort_keys=True) + "\n").encode()


class SleepingStack(ActStackLaunch):
    """The launch of the rig with the ROS launch replaced by a sleeping process (the rest of the launch is untouched)."""

    def argv(self):
        return [sys.executable, "-c", "import time; time.sleep(120)"]


def sleeping(launch):
    return SleepingStack(**{field.name: getattr(launch, field.name) for field in fields(ActStackLaunch)})


@pytest.mark.parametrize("rig, checks", [
    (HEAD_WRIST_RIG, {"head_rgb", "wrist_rgb"}),
    (SIDE_WRIST_RIG, {"side_rgb", "wrist_rgb"}),
])
def test_the_container_start_path_reaches_ready_and_stops_for_each_rig(tmp_path, rig, checks):
    observer = tmp_path / "act_stack_ready"
    observer.write_text("#!/bin/sh\n")
    observer.chmod(0o700)
    stack_root = tmp_path / "stack"
    stack_root.mkdir()
    launch = sleeping(instance_stack_launch({"simulation_session_id": SESSION}, ros2=Path(sys.executable), stack_root=stack_root,
                                            environment=dict(os.environ), rig=rig, share=PACKAGE_ROOT))
    assert launch.rig == rig.rig
    ready, ready_check, stack = compose_stack(launch, observer)
    runs = []

    def observe(argv, **_kwargs):
        runs.append(argv)
        return subprocess.CompletedProcess(argv, 0, observer_output(argv), b"")

    ready.run = ready_check.run = stack.stop_probe.run = observe
    ready.clock_ns = ready_check.clock_ns = stack.stop_probe.clock_ns = lambda: NOW_NS
    stack.graph_clear_probe = lambda: True

    async def lifecycle():
        owner = await stack.start(timeout_s=5)               # the shard start: this raised MutationError for the side+wrist rig
        assert json.loads(ready.readiness_bytes)["checks"].keys() >= checks
        assert {name for name in json.loads(ready.readiness_bytes)["checks"] if name.endswith("_rgb")} == checks
        assert [ready_check(), ready_check()] == [True, True]  # the task gates
        await stack.stop(timeout_s=5)                        # the retirement audit's stop proof: this carried the same ValueError
        return owner

    owner = asyncio.run(lifecycle())
    assert owner.pid > 0 and len(runs) == 1 + 2 + 1
    def without_budget(argv):   # the stop probe observes with its own shorter budget; the rest is the same command
        return [item for index, item in enumerate(argv) if "--timeout-s" not in argv[max(index - 1, 0):index + 1]]

    assert all(without_budget(argv) == without_budget(runs[0]) for argv in runs)
    # the observer is told the rig exactly as the launch names it: no profile argument for rig v1, the profile file for any other
    assert ("--rig-profile" in runs[0]) == (rig is not HEAD_WRIST_RIG)
    assert (tmp_path / "stack" / "cleanup-receipt.json").is_file()


def test_a_stack_that_reports_the_other_rigs_cameras_is_never_ready(tmp_path):
    """Exact equality: a side+wrist stack that reports head_rgb, and a head+wrist stack that reports side_rgb, are refused."""
    observer = tmp_path / "act_stack_ready"
    observer.write_text("#!/bin/sh\n")
    observer.chmod(0o700)
    for rig, wrong in ((SIDE_WRIST_RIG, HEAD_WRIST_RIG), (HEAD_WRIST_RIG, SIDE_WRIST_RIG)):
        stack_root = tmp_path / f"stack-{rig.rig}"
        stack_root.mkdir()
        launch = instance_stack_launch({"simulation_session_id": SESSION}, ros2=Path(sys.executable), stack_root=stack_root,
                                       environment=dict(os.environ), rig=rig, share=PACKAGE_ROOT)
        ready, _check, _stack = compose_stack(launch, observer)
        wrong_argv = ["", "--session-id", SESSION, "--ros-domain-id", str(launch.ros_domain_id),
                      *(["--rig-profile", str(PACKAGE_ROOT / "config/act/rig-v2.yaml")] if wrong is SIDE_WRIST_RIG else [])]
        ready.run = lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 0, observer_output(wrong_argv), b"")
        ready.clock_ns = lambda: NOW_NS
        with pytest.raises(ValueError, match="ACT_STACK_READINESS_OUTPUT_INVALID"):
            ready()


@pytest.mark.parametrize("rig", [HEAD_WRIST_RIG, SIDE_WRIST_RIG])
def test_the_startup_proof_is_issued_written_and_consumed_for_each_rig(tmp_path, rig):
    """start probe -> issuer (writes readiness.json and the receipt) -> the child's consumer, with the rig's own check set."""
    from types import SimpleNamespace

    from so101_teleop.unified.contracts import MutationError, OwnerKey
    from so101_teleop.unified.pick_place_startup_issuer import PickPlaceStartupProofIssuer, expected_checks_for_launch
    from so101_teleop.unified.pick_place_startup_proof import PickPlaceStartupProofConsumer

    observer = tmp_path / "act_stack_ready"
    observer.write_text("#!/bin/sh\n")
    observer.chmod(0o700)
    stack_root = tmp_path / "stack"
    stack_root.mkdir()
    launch = instance_stack_launch({"simulation_session_id": SESSION}, ros2=Path(sys.executable), stack_root=stack_root,
                                   environment=dict(os.environ), rig=rig, share=PACKAGE_ROOT)
    ready, _check, _stack = compose_stack(launch, observer)
    ready.run = lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 0, observer_output(argv), b"")
    ready.clock_ns = lambda: NOW_NS
    assert ready() is True
    proof_root = tmp_path / "pick-place-live" / "campaign-289" / "stack"
    proof_root.mkdir(parents=True)
    context = SimpleNamespace(evidence_root=str(tmp_path), campaign_id="campaign-289", operation_id="operation-289",
                              source_sha256="1" * 64, manifest_sha256="2" * 64, runtime_config_sha256="3" * 64,
                              collection_config_sha256="4" * 64, contact_policy_fingerprint="5" * 64)
    child = SimpleNamespace(campaign_id="campaign-289", worker_id="w1", execution_generation=7,
                            mujoco_session_id=SESSION, ros_domain_id=launch.ros_domain_id)
    stack_owner, child_owner = OwnerKey(1234, 1234, 101, "a" * 64, "b" * 64), OwnerKey(2345, 2345, 202, "c" * 64, "d" * 64)
    checks = expected_checks_for_launch(launch)
    assert checks == ready.expected_checks
    receipt = PickPlaceStartupProofIssuer(context, child, stack_owner, child_owner, checks=checks,
                                          live_probe=lambda _owner: True, clock_ns=lambda: NOW_NS).issue(ready.readiness_bytes)
    assert (proof_root / "readiness.json").read_bytes() == ready.readiness_bytes
    consumer = PickPlaceStartupProofConsumer(context, child, stack_owner=stack_owner, child_owner=child_owner, checks=checks,
                                             live_probe=lambda _owner: True, clock_ns=lambda: NOW_NS)
    assert consumer.consume() == receipt
    # a consumer of the other rig's check set never accepts the proof
    other = SIDE_WRIST_RIG if rig is HEAD_WRIST_RIG else HEAD_WRIST_RIG
    (proof_root / "startup-consumed.json").unlink()
    wrong = PickPlaceStartupProofConsumer(
        context, child, stack_owner=stack_owner, child_owner=child_owner,
        checks=frozenset({"mujoco_session", "advancing_physics", "controller_states", "moveit_graph", "physical_stop",
                          *(f"{camera}_rgb" for camera in other.camera_names)}),
        live_probe=lambda _owner: True, clock_ns=lambda: NOW_NS)
    with pytest.raises(MutationError, match="PICK_PLACE_VALIDATION_STARTUP_PROOF_INVALID"):
        wrong.consume()
