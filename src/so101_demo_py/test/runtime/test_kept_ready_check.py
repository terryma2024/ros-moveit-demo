"""The task gates' kept readiness check: a ready verdict from the kept session, everything else from the observer process.

Real here: the rig launch, the repeatable probe and the stack owner's validation of an observation. Controlled doubles: the observer
process (`run` seam) and the kept session (`make_session`), whose `check` answers what a `StackReadinessSession` would.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from paths import PACKAGE_ROOT

from so101_demo.act.rig_profile import HEAD_WRIST_RIG
from so101_demo.runtime.act_instance.program import compose_stack, instance_stack_launch
from so101_demo.runtime.act_instance.ready_check import KEPT_ATTEMPT_TIMEOUT_S, KeptActStackReadyCheck
from test_act_rig_startup_readiness_composition import NOW_NS, observer_output, sleeping

SESSION = "kept-ready-session"


@pytest.fixture
def parts(tmp_path, monkeypatch):
    observer = tmp_path / "act_stack_ready"
    observer.write_text("#!/bin/sh\n")
    observer.chmod(0o700)
    stack_root = tmp_path / "stack"
    stack_root.mkdir()
    launch = sleeping(instance_stack_launch({"simulation_session_id": SESSION}, ros2=Path(sys.executable),
                                            stack_root=stack_root, environment=dict(os.environ), rig=HEAD_WRIST_RIG,
                                            share=PACKAGE_ROOT))
    monkeypatch.setenv("ROS_DOMAIN_ID", str(launch.ros_domain_id))
    runs, sessions = [], []

    def observe(argv, **_kwargs):
        runs.append(argv)
        return subprocess.CompletedProcess(argv, 0, observer_output(argv), b"")

    def artifact(checks=None):
        value = json.loads(observer_output(["x", "--session-id", launch.session_id, "--ros-domain-id", str(launch.ros_domain_id),
                                            *launch.readiness_arguments()]))
        value["captured_monotonic_ns"] = NOW_NS - 10**9
        if checks is not None:
            value["checks"] = checks
        return value

    def session_answering(*outcomes):
        asked = []     # the answers run through all sessions in order, the last one repeats

        class Session:
            closed = False

            def __init__(self):
                self.timeouts = []
                sessions.append(self)

            def check(self, timeout_s):
                self.timeouts.append(timeout_s)
                asked.append(timeout_s)
                outcome = outcomes[min(len(asked) - 1, len(outcomes) - 1)]
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome

            def close(self):
                self.closed = True
        return Session

    def make(*outcomes, in_instance=True):
        return KeptActStackReadyCheck(launch, observer, run=observe, clock_ns=lambda: NOW_NS, in_instance=lambda: in_instance,
                                      make_session=session_answering(*outcomes))
    return SimpleNamespace(make=make, runs=runs, sessions=sessions, artifact=artifact, launch=launch)


def ready(artifact):
    return SimpleNamespace(ready=True, artifact=artifact, report=None)


def not_ready():
    return SimpleNamespace(ready=False, artifact=None, report={"ready": False, "failure_code": "ACT_STACK_PHYSICS_NOT_ADVANCING"})


def test_a_ready_verdict_of_the_kept_session_needs_no_process(parts):
    check = parts.make(ready(parts.artifact()))
    assert [check(), check()] == [True, True]
    assert parts.runs == [] and len(parts.sessions) == 1      # one session for both calls
    assert parts.sessions[0].timeouts == [KEPT_ATTEMPT_TIMEOUT_S] * 2


def test_outside_an_instance_process_the_observer_process_answers(parts):
    check = parts.make(ready(parts.artifact()), in_instance=False)
    assert check() is True and len(parts.runs) == 1 and parts.sessions == []


def test_another_ros_domain_than_the_launchs_is_never_observed_by_the_kept_session(parts, monkeypatch):
    monkeypatch.setenv("ROS_DOMAIN_ID", str(parts.launch.ros_domain_id + 1))
    check = parts.make(ready(parts.artifact()))
    assert check() is True and len(parts.runs) == 1 and parts.sessions == []


def test_not_ready_in_the_kept_session_is_decided_by_the_process_in_both_directions(parts):
    check = parts.make(not_ready())
    assert check() is True and len(parts.runs) == 1            # the process finds the stack ready: so it is

    def failing(argv, **_kwargs):
        parts.runs.append(argv)
        return subprocess.CompletedProcess(argv, 1, b"", b'{"ready": false, "failure_code": "ACT_STACK_X"}\n')
    check.run = failing
    with pytest.raises(ValueError, match="ACT_STACK_READINESS_COMMAND_FAILED rc=1"):
        check()                                                # and its refusal is the one raised, as before
    assert len(parts.runs) == 2


def test_a_session_that_fails_is_closed_and_the_next_call_opens_a_new_one(parts):
    check = parts.make(RuntimeError("context lost"), ready(parts.artifact()))
    assert check() is True and len(parts.runs) == 1
    assert parts.sessions[0].closed is True and check.__dict__["_session"] is None
    assert check() is True and len(parts.sessions) == 2 and len(parts.runs) == 1   # the second call is served by the new session


def test_an_artifact_the_stack_owner_would_refuse_is_not_taken(parts):
    wrong_checks = {"mujoco_session": True}
    check = parts.make(ready(parts.artifact(wrong_checks)))
    assert check() is True and len(parts.runs) == 1            # the process answered, and the session was dropped
    assert parts.sessions[0].closed is True


def test_close_is_idempotent_and_releases_the_session(parts):
    check = parts.make(ready(parts.artifact()))
    check()
    check.close()
    check.close()
    assert parts.sessions[0].closed is True


def test_the_shard_composes_the_kept_check_and_leaves_the_start_probe_single_use(tmp_path):
    from so101_teleop.unified.pick_place_startup_issuer import InstalledActStackReadinessProbe
    observer = tmp_path / "act_stack_ready"
    observer.write_text("#!/bin/sh\n")
    observer.chmod(0o700)
    stack_root = tmp_path / "stack"
    stack_root.mkdir()
    launch = sleeping(instance_stack_launch({"simulation_session_id": SESSION}, ros2=Path(sys.executable),
                                            stack_root=stack_root, environment=dict(os.environ), rig=HEAD_WRIST_RIG,
                                            share=PACKAGE_ROOT))
    ready_probe, ready_check, _stack = compose_stack(launch, observer)
    assert type(ready_check) is KeptActStackReadyCheck and type(ready_probe) is InstalledActStackReadinessProbe
    assert ready_check.kept_attempt_timeout_s == KEPT_ATTEMPT_TIMEOUT_S


def test_the_graph_clear_proof_of_the_stack_stop_runs_after_the_kept_nodes_are_released(parts):
    """EXP-658: the stack stop proves the domain has no node (`ros2 node list`). The instance's own kept readiness session and
    retained evidence reader are nodes of that domain, so they are closed first (GRAPH_NOT_CLEARED otherwise, 7 of 8 shards)."""
    check = parts.make(in_instance=True)       # a registered holder
    events = []
    check.release = lambda: events.append("release")

    def run(argv, **_kwargs):
        events.append("node-list")
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    _ready, _check, stack = compose_stack(parts.launch, check.executable)
    stack.graph_clear_probe.run = run
    assert stack.graph_clear_probe() is True
    assert events and events[-1] == "node-list" and "release" in events[:-1]
