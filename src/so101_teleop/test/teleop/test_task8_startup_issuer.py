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
from so101_teleop.unified.task8_startup_issuer import (
    InstalledActStackReadinessProbe, Task8StartupProofIssuer,
)
from so101_teleop.unified.task8_startup_proof import Task8StartupProofConsumer


NOW_NS = 1_000_000_000_000
CHECKS = (
    "mujoco_session", "advancing_physics", "controller_states",
    "moveit_graph", "physical_stop", "head_rgb", "wrist_rgb",
)
STACK_OWNER = OwnerKey(12345, 12345, 101, "a" * 64, "b" * 64)
CHILD_OWNER = OwnerKey(23456, 23456, 202, "c" * 64, "d" * 64)


def prepared(tmp_path):
    root = tmp_path / "task8-live" / "campaign-289" / "stack"
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
    issuer = Task8StartupProofIssuer(
        context, child, STACK_OWNER, CHILD_OWNER,
        live_probe=lambda _owner: True, clock_ns=lambda: NOW_NS,
    )
    receipt = issuer.issue(probe.readiness_bytes)
    assert receipt["stack_owner"] == asdict(STACK_OWNER)
    assert receipt["child_owner"] == asdict(CHILD_OWNER)
    assert receipt["readiness_sha256"] == hashlib.sha256(probe.readiness_bytes).hexdigest()
    assert (root / "readiness.json").read_bytes() == probe.readiness_bytes
    consumer = Task8StartupProofConsumer(
        context, child, stack_owner=STACK_OWNER, child_owner=CHILD_OWNER,
        live_probe=lambda _owner: True, clock_ns=lambda: NOW_NS,
    )
    assert consumer.consume() == receipt
    with pytest.raises(MutationError, match="TASK8_STARTUP_PROOF_ALREADY_CONSUMED"):
        consumer.consume()
    with pytest.raises(MutationError, match="TASK8_STARTUP_PROOF_ALREADY_ISSUED"):
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


def test_failed_observer_and_retired_owner_cannot_issue(tmp_path):
    context, child, launch, root, artifact = prepared(tmp_path)
    probe, _ = observe(tmp_path, launch, artifact, returncode=1)
    with pytest.raises(ValueError, match="ACT_STACK_READINESS_COMMAND_FAILED"):
        probe()
    raw = (json.dumps(artifact) + "\n").encode()
    issuer = Task8StartupProofIssuer(
        context, child, STACK_OWNER, CHILD_OWNER,
        live_probe=lambda owner: owner != STACK_OWNER, clock_ns=lambda: NOW_NS,
    )
    with pytest.raises(MutationError, match="TASK8_STARTUP_PROOF_INVALID"):
        issuer.issue(raw)
    assert not (root / "startup-receipt.json").exists()


def test_issuer_rejects_scope_mismatch_before_writing(tmp_path):
    context, child, _, root, artifact = prepared(tmp_path)
    child.mujoco_session_id = "other"
    raw = (json.dumps(artifact) + "\n").encode()
    issuer = Task8StartupProofIssuer(
        context, child, STACK_OWNER, CHILD_OWNER,
        live_probe=lambda _owner: True, clock_ns=lambda: NOW_NS,
    )
    with pytest.raises(MutationError, match="TASK8_STARTUP_PROOF_INVALID"):
        issuer.issue(raw)
    assert not (root / "readiness.json").exists()
