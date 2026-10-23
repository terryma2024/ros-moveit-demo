"""The stack owner issues a single proof only from a fresh installed observation."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from so101_teleop.unified.act_stack import ActStackLaunch
from so101_teleop.unified.contracts import MutationError, OwnerKey
from so101_teleop.unified.pick_place_startup_issuer import (
    InstalledActStackReadinessProbe, PickPlaceStartupProofIssuer,
)
from so101_teleop.unified.pick_place_startup_proof import PickPlaceStartupProofConsumer


NOW_NS = 1_000_000_000_000
CHECKS = (
    "mujoco_session", "advancing_physics", "controller_states",
    "moveit_graph", "physical_stop", "head_rgb", "wrist_rgb",
)
STACK_OWNER = OwnerKey(12345, 12345, 101, "a" * 64, "b" * 64)
CHILD_OWNER = OwnerKey(23456, 23456, 202, "c" * 64, "d" * 64)


def prepared(tmp_path):
    root = tmp_path / "pick-place-live" / "campaign-289" / "stack"
    root.mkdir(parents=True)
    context = SimpleNamespace(
        evidence_root=str(tmp_path), campaign_id="campaign-289",
        operation_id="operation-289", source_sha256="1" * 64,
        manifest_sha256="2" * 64, runtime_config_sha256="3" * 64,
        collection_config_sha256="4" * 64,
        contact_policy_fingerprint="5" * 64,
    )
    child = SimpleNamespace(
        campaign_id=context.campaign_id, worker_id="w1", execution_generation=7,
        mujoco_session_id="session-289", ros_domain_id=179,
    )
    launch = ActStackLaunch(
        ros2_executable=Path("/usr/bin/python3"), session_id=child.mujoco_session_id,
        evidence_root=root, ros_domain_id=child.ros_domain_id,
        environment={"GZ_PARTITION": "act-data-exp289-179"},
    )
    artifact = {
        "schema_version": 1, "session_id": child.mujoco_session_id,
        "ros_domain_id": child.ros_domain_id,
        "captured_monotonic_ns": NOW_NS - 1_000_000_000,
        "checks": {name: True for name in CHECKS},
    }
    return context, child, launch, root, artifact


def observe(tmp_path, launch, artifact, *, returncode=0):
    binary = tmp_path / "act_stack_ready"
    binary.write_text("#!/usr/bin/env python3\n")
    binary.chmod(0o700)
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, returncode,
                                           (json.dumps(artifact) + "\n").encode(), b"")

    probe = InstalledActStackReadinessProbe(
        launch, binary, run=runner, clock_ns=lambda: NOW_NS,
    )
    return probe, calls


def test_installed_probe_and_owner_issuer_are_consumed_once(tmp_path):
    context, child, launch, root, artifact = prepared(tmp_path)
    probe, calls = observe(tmp_path, launch, artifact)
    assert probe() is True
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv[:3] == [str(tmp_path / "act_stack_ready"), "--session-id", "session-289"]
    assert kwargs["env"]["ROS_DOMAIN_ID"] == "179"
    assert kwargs["env"]["GZ_PARTITION"] == "act-data-exp289-179"
    issuer = PickPlaceStartupProofIssuer(
        context, child, STACK_OWNER, CHILD_OWNER, checks=frozenset(CHECKS),
        live_probe=lambda _owner: True, clock_ns=lambda: NOW_NS,
    )
    receipt = issuer.issue(probe.readiness_bytes)
    assert receipt["stack_owner"] == asdict(STACK_OWNER)
    assert receipt["child_owner"] == asdict(CHILD_OWNER)
    assert receipt["readiness_sha256"] == hashlib.sha256(probe.readiness_bytes).hexdigest()
    assert (root / "readiness.json").read_bytes() == probe.readiness_bytes
    consumer = PickPlaceStartupProofConsumer(
        context, child, stack_owner=STACK_OWNER, child_owner=CHILD_OWNER,
        checks=frozenset(CHECKS), live_probe=lambda _owner: True, clock_ns=lambda: NOW_NS,
    )
    assert consumer.consume() == receipt
    with pytest.raises(MutationError, match="PICK_PLACE_VALIDATION_STARTUP_PROOF_ALREADY_CONSUMED"):
        consumer.consume()
    with pytest.raises(MutationError, match="PICK_PLACE_VALIDATION_STARTUP_PROOF_ALREADY_ISSUED"):
        issuer.issue(probe.readiness_bytes)
    with pytest.raises(ValueError, match="ACT_STACK_READINESS_PROBE_REUSED"):
        probe()


@pytest.mark.parametrize("change", ["session", "domain", "check", "stale"])
def test_probe_rejects_wrong_or_stale_observation_without_writing(tmp_path, change):
    context, child, launch, root, artifact = prepared(tmp_path)
    if change == "session":
        artifact["session_id"] = "other"
    elif change == "domain":
        artifact["ros_domain_id"] = 180
    elif change == "check":
        artifact["checks"]["physical_stop"] = False
    else:
        artifact["captured_monotonic_ns"] = NOW_NS - 31_000_000_000
    probe, _ = observe(tmp_path, launch, artifact)
    with pytest.raises(ValueError, match="ACT_STACK_READINESS_OUTPUT_INVALID"):
        probe()
    assert not (root / "readiness.json").exists()


def test_failed_observer_error_carries_the_observers_last_stderr_line(tmp_path):
    """The observer prints why it was not ready as its last stderr line; that line used to be dropped."""
    context, child, launch, root, artifact = prepared(tmp_path)
    binary = tmp_path / "act_stack_ready"
    binary.write_text("#!/usr/bin/env python3\n")
    binary.chmod(0o700)
    failure = '{"checks":{"advancing_physics":false},"failure_code":"ACT_STACK_WORLD_SESSION_INVALID","ready":false}'

    def runner(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv, 1, b"", b"[WARN] [rcl]: ROS_LOCALHOST_ONLY is deprecated\n" + failure.encode() + b"\n")

    probe = InstalledActStackReadinessProbe(launch, binary, run=runner, clock_ns=lambda: NOW_NS)
    with pytest.raises(ValueError, match="^ACT_STACK_READINESS_COMMAND_FAILED rc=1: ") as caught:
        probe()
    assert failure in str(caught.value) and "ROS_LOCALHOST_ONLY" not in str(caught.value)

    long = InstalledActStackReadinessProbe(
        launch, binary, clock_ns=lambda: NOW_NS,
        run=lambda argv, **kwargs: subprocess.CompletedProcess(argv, 2, b"", b"x" * 5000))
    with pytest.raises(ValueError) as caught:
        long()
    assert len(str(caught.value)) < 1000

    silent = InstalledActStackReadinessProbe(
        launch, binary, clock_ns=lambda: NOW_NS,
        run=lambda argv, **kwargs: subprocess.CompletedProcess(argv, 3, b"", b""))
    with pytest.raises(ValueError, match="^ACT_STACK_READINESS_COMMAND_FAILED rc=3$"):
        silent()


def test_failed_observer_and_retired_owner_cannot_issue(tmp_path):
    context, child, launch, root, artifact = prepared(tmp_path)
    probe, _ = observe(tmp_path, launch, artifact, returncode=1)
    with pytest.raises(ValueError, match="ACT_STACK_READINESS_COMMAND_FAILED"):
        probe()
    raw = (json.dumps(artifact) + "\n").encode()
    issuer = PickPlaceStartupProofIssuer(
        context, child, STACK_OWNER, CHILD_OWNER, checks=frozenset(CHECKS),
        live_probe=lambda owner: owner != STACK_OWNER, clock_ns=lambda: NOW_NS,
    )
    with pytest.raises(MutationError, match="PICK_PLACE_VALIDATION_STARTUP_PROOF_INVALID"):
        issuer.issue(raw)
    assert not (root / "startup-receipt.json").exists()


def test_issuer_rejects_scope_mismatch_before_writing(tmp_path):
    context, child, _, root, artifact = prepared(tmp_path)
    child.mujoco_session_id = "other"
    raw = (json.dumps(artifact) + "\n").encode()
    issuer = PickPlaceStartupProofIssuer(
        context, child, STACK_OWNER, CHILD_OWNER, checks=frozenset(CHECKS),
        live_probe=lambda _owner: True, clock_ns=lambda: NOW_NS,
    )
    with pytest.raises(MutationError, match="PICK_PLACE_VALIDATION_STARTUP_PROOF_INVALID"):
        issuer.issue(raw)
    assert not (root / "readiness.json").exists()


def test_repeatable_ready_probe_observes_afresh_and_leaves_the_start_probe_alone(tmp_path):
    from so101_teleop.unified.act_stack_probes import RepeatableActStackReadyProbe

    _, _, launch, _, artifact = prepared(tmp_path)
    start, calls = observe(tmp_path, launch, artifact)
    assert start() is True

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, (json.dumps(artifact) + "\n").encode(), b"")

    repeatable = RepeatableActStackReadyProbe(
        launch, tmp_path / "act_stack_ready", run=runner, clock_ns=lambda: NOW_NS,
    )
    assert [repeatable() for _ in range(3)] == [True, True, True]
    assert len(calls) == 4
    assert all(argv == calls[0][0] for argv, _ in calls)
    with pytest.raises(ValueError, match="ACT_STACK_READINESS_PROBE_REUSED"):
        start()


def test_repeatable_ready_probe_refuses_a_bad_scope_when_built_and_reports_each_failure(tmp_path):
    from so101_teleop.unified.act_stack_probes import RepeatableActStackReadyProbe

    _, _, launch, _, artifact = prepared(tmp_path)
    with pytest.raises(ValueError, match="ACT_STACK_READINESS_PROBE_CONFIG_INVALID"):
        RepeatableActStackReadyProbe(launch, tmp_path / "missing")
    observe(tmp_path, launch, artifact)   # writes the executable observer
    codes = iter([1, 0])

    def runner(argv, **kwargs):
        return subprocess.CompletedProcess(argv, next(codes), (json.dumps(artifact) + "\n").encode(), b"")

    probe = RepeatableActStackReadyProbe(
        launch, tmp_path / "act_stack_ready", run=runner, clock_ns=lambda: NOW_NS,
    )
    with pytest.raises(ValueError, match="ACT_STACK_READINESS_COMMAND_FAILED"):
        probe()
    assert probe() is True


# --- the expected readiness check set follows the rig profile the stack composes (EXP-7001: SHARD_START_FAILED) ---

BASE_CHECKS = ("mujoco_session", "advancing_physics", "controller_states", "moveit_graph", "physical_stop")
SIDE_WRIST_CHECKS = (*BASE_CHECKS, "side_rgb", "wrist_rgb")


def rig_launch(tmp_path, rig):
    """A launch of a named rig: the default rig carries no profile file, another one carries its profile document."""
    from so101_demo.act.rig_profile import SIDE_WRIST_RIG, dump_rig_profile

    root = tmp_path / "stack"
    root.mkdir(exist_ok=True)
    arguments = {}
    if rig == "side-wrist":
        profile = tmp_path / "rig-v2.yaml"
        profile.write_bytes(dump_rig_profile(SIDE_WRIST_RIG))
        arguments = dict(rig=rig, rig_profile=profile)
    return ActStackLaunch(
        ros2_executable=Path("/usr/bin/python3"), session_id="session-289", evidence_root=root,
        ros_domain_id=179, environment={"GZ_PARTITION": "act-data-exp289-179"}, **arguments,
    )


def observation(checks):
    return {
        "schema_version": 1, "session_id": "session-289", "ros_domain_id": 179,
        "captured_monotonic_ns": NOW_NS - 1_000_000_000, "checks": {name: True for name in checks},
    }


def test_side_wrist_probe_accepts_exactly_the_side_wrist_check_set(tmp_path):
    probe, calls = observe(tmp_path, rig_launch(tmp_path, "side-wrist"), observation(SIDE_WRIST_CHECKS))
    assert probe() is True
    assert set(json.loads(probe.readiness_bytes)["checks"]) == set(SIDE_WRIST_CHECKS)
    assert calls[0][0][-2:] == ["--rig-profile", str(tmp_path / "rig-v2.yaml")]


@pytest.mark.parametrize("checks", [
    (*BASE_CHECKS, "head_rgb", "wrist_rgb"),               # the other rig's set
    (*BASE_CHECKS, "side_rgb"),                            # a camera missing
    (*SIDE_WRIST_CHECKS, "head_rgb"),                      # a superset
    SIDE_WRIST_CHECKS[:-1],                                # a subset
    (*SIDE_WRIST_CHECKS, "task_rgb"),                      # an unknown extra camera
])
def test_side_wrist_probe_refuses_any_other_check_set(tmp_path, checks):
    probe, _ = observe(tmp_path, rig_launch(tmp_path, "side-wrist"), observation(checks))
    with pytest.raises(ValueError, match="ACT_STACK_READINESS_OUTPUT_INVALID"):
        probe()
    assert probe.readiness_bytes is None


@pytest.mark.parametrize("checks", [
    SIDE_WRIST_CHECKS,
    (*BASE_CHECKS, "head_rgb"),
    (*BASE_CHECKS, "head_rgb", "wrist_rgb", "side_rgb"),
])
def test_head_wrist_probe_still_refuses_everything_but_head_and_wrist(tmp_path, checks):
    probe, _ = observe(tmp_path, rig_launch(tmp_path, "head-wrist"), observation(checks))
    with pytest.raises(ValueError, match="ACT_STACK_READINESS_OUTPUT_INVALID"):
        probe()


def test_head_wrist_probe_accepts_exactly_the_head_wrist_check_set(tmp_path):
    probe, _ = observe(tmp_path, rig_launch(tmp_path, "head-wrist"), observation(CHECKS))
    assert probe() is True


def test_the_expected_check_sets_are_the_observers_own_check_names(tmp_path):
    """The validator's set is the observer's `check_order_for` of the same rig (one source for the names)."""
    from so101_demo.act.rig_profile import HEAD_WRIST_RIG, SIDE_WRIST_RIG
    from so101_demo.cli import act_stack_ready
    from so101_teleop.unified.pick_place_startup_issuer import expected_checks_for_launch

    for name, rig in (("head-wrist", HEAD_WRIST_RIG), ("side-wrist", SIDE_WRIST_RIG)):
        assert expected_checks_for_launch(rig_launch(tmp_path, name)) == frozenset(
            check for check, _code in act_stack_ready.check_order_for(rig))
    assert expected_checks_for_launch(rig_launch(tmp_path, "head-wrist")) == frozenset(CHECKS)


def test_a_profile_file_of_another_rig_than_the_launch_names_is_refused(tmp_path):
    from so101_demo.act.rig_profile import HEAD_WRIST_RIG, dump_rig_profile

    launch = rig_launch(tmp_path, "side-wrist")
    launch.rig_profile.write_bytes(dump_rig_profile(HEAD_WRIST_RIG))
    binary = tmp_path / "act_stack_ready"
    binary.write_text("#!/usr/bin/env python3\n")
    binary.chmod(0o700)
    with pytest.raises(ValueError, match="ACT_STACK_READINESS_PROBE_CONFIG_INVALID"):
        InstalledActStackReadinessProbe(launch, binary)


def issue_and_consume(tmp_path, rig, *, issue_checks=None, consume_checks=None):
    """A proof of `rig`'s stack: probe the observation, issue it, write it, consume it as the child does."""
    from so101_teleop.unified.pick_place_startup_issuer import expected_checks_for_launch

    context, child, _, root, _ = prepared(tmp_path)
    launch = rig_launch(tmp_path, rig)
    expected = expected_checks_for_launch(launch)
    probe, _ = observe(tmp_path, launch, observation(expected))
    assert probe() is True
    issuer = PickPlaceStartupProofIssuer(
        context, child, STACK_OWNER, CHILD_OWNER, checks=issue_checks or probe.expected_checks,
        live_probe=lambda _owner: True, clock_ns=lambda: NOW_NS)
    receipt = issuer.issue(probe.readiness_bytes)
    assert (root / "readiness.json").read_bytes() == probe.readiness_bytes
    consumer = PickPlaceStartupProofConsumer(
        context, child, stack_owner=STACK_OWNER, child_owner=CHILD_OWNER, checks=consume_checks or expected,
        live_probe=lambda _owner: True, clock_ns=lambda: NOW_NS)
    return receipt, consumer


@pytest.mark.parametrize("rig", ["head-wrist", "side-wrist"])
def test_a_proof_is_issued_written_and_consumed_end_to_end_for_each_rig(tmp_path, rig):
    receipt, consumer = issue_and_consume(tmp_path, rig)
    assert consumer.consume() == receipt


@pytest.mark.parametrize("rig, other", [("head-wrist", "side-wrist"), ("side-wrist", "head-wrist")])
def test_a_consumer_of_another_rigs_check_set_refuses_the_proof(tmp_path, rig, other):
    from so101_teleop.unified.pick_place_startup_issuer import expected_checks_for_launch

    other_dir = tmp_path / "other"
    other_dir.mkdir()
    _, consumer = issue_and_consume(tmp_path, rig, consume_checks=expected_checks_for_launch(rig_launch(other_dir, other)))
    with pytest.raises(MutationError, match="PICK_PLACE_VALIDATION_STARTUP_PROOF_INVALID"):
        consumer.consume()


@pytest.mark.parametrize("rig, other", [("head-wrist", "side-wrist"), ("side-wrist", "head-wrist")])
def test_an_issuer_of_another_rigs_check_set_refuses_the_observation_without_writing(tmp_path, rig, other):
    from so101_teleop.unified.pick_place_startup_issuer import expected_checks_for_launch

    other_dir = tmp_path / "other"
    other_dir.mkdir()
    with pytest.raises(MutationError, match="PICK_PLACE_VALIDATION_STARTUP_PROOF_INVALID"):
        issue_and_consume(tmp_path, rig, issue_checks=expected_checks_for_launch(rig_launch(other_dir, other)))
    assert not (tmp_path / "pick-place-live" / "campaign-289" / "stack" / "readiness.json").exists()


def test_issuer_and_consumer_have_no_default_check_set(tmp_path):
    context, child, _, _, _ = prepared(tmp_path)
    with pytest.raises(TypeError):
        PickPlaceStartupProofIssuer(context, child, STACK_OWNER, CHILD_OWNER)
    with pytest.raises(TypeError):
        PickPlaceStartupProofConsumer(context, child, stack_owner=STACK_OWNER, child_owner=CHILD_OWNER)
    with pytest.raises(ValueError, match="CONFIG_INVALID"):
        PickPlaceStartupProofConsumer(context, child, stack_owner=STACK_OWNER, child_owner=CHILD_OWNER, checks=frozenset())
