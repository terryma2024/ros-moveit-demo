"""The task gates of a borrowed native stack never reuse the single-use start probe.

Real here: the stack's `InstalledActStackReadinessProbe` (already consumed, as after the shard start), the repeatable
`RepeatableActStackReadyProbe`, the builder, the runtime and the whole task flow of `test_task_builder`. Controlled
double: the observer subprocess (`run` seam), which answers a valid no-motion observation. The first real collection run
failed with ACT_STACK_READINESS_PROBE_REUSED at the first task gate because a double stack accepted repeated calls.
"""

import subprocess

import pytest

from test_task_builder import (  # noqa: F401  (fixtures and the flow rig)
    OBSERVER_NOW_NS, Rig, TEACHER_SOCKET, builder, env, fault_of, flow, make_task, shared_env,
    verified_inputs_are_remembered_per_file_signature,
)
from so101_teleop.unified.act_stack_probes import RepeatableActStackReadyProbe

#: The retired per-worker field; built from fragments so the source-tree absence test keeps matching nothing.
NS_FIELD = "ros" + "_namespace"
NS_OPTION = "--ros" + "-namespace"


def failing_check(flow, returncode=1):
    def observe(argv, **kwargs):
        return subprocess.CompletedProcess(argv, returncode, b"", b"")
    return RepeatableActStackReadyProbe(flow.stack.launch, flow.observer, run=observe, clock_ns=lambda: OBSERVER_NOW_NS)


def test_the_start_probe_of_the_stack_is_spent_and_stays_single_use(flow):
    with pytest.raises(ValueError, match="ACT_STACK_READINESS_PROBE_REUSED"):
        flow.stack.ready_probe()


def test_each_task_gate_observes_the_stack_afresh_and_never_the_start_probe(flow, monkeypatch):
    rig = Rig(flow, monkeypatch, teacher="FAILED")
    before = len(flow.observer_runs)
    rig.execution.run()
    assert len(flow.observer_runs) - before == 2, "start_physical_runtime and worker_ready_gate each observe"
    assert rig.execution.shutdown_owned() is True
    assert rig.execution.retire_proofs["ready_gate"] is True
    runs = flow.observer_runs[before:]
    assert len(runs) == 3, "the case retirement observes once more"
    for argv in runs:
        assert argv[argv.index("--session-id") + 1] == flow.stack.launch.session_id
        assert argv[argv.index("--ros-domain-id") + 1] == str(flow.stack.launch.ros_domain_id)
        assert str(flow.stack.launch.ros_domain_id) == "181" and NS_OPTION not in argv
        assert argv[0] == str(flow.observer)
    with pytest.raises(ValueError, match="ACT_STACK_READINESS_PROBE_REUSED"):
        flow.stack.ready_probe()


def test_a_second_task_on_the_same_stack_passes_its_own_gates(flow, monkeypatch):
    first = Rig(flow, monkeypatch, teacher="FAILED")
    first.execution.run()
    assert first.execution.shutdown_owned() is True
    before = len(flow.observer_runs)
    second = Rig(flow, monkeypatch, teacher="DEADLINE")
    second.execution.run()
    assert second.execution.shutdown_owned() is True
    assert len(flow.observer_runs) - before == 3


def test_a_failing_observer_is_not_ready_and_the_first_cause_reaches_the_fault(flow, monkeypatch):
    rig = Rig(flow, monkeypatch, build=False)
    rig.build_kwargs["ready_check"] = failing_check(flow)
    rig.attach(builder().build_collection_task(rig.task, **rig.build_kwargs))
    error = fault_of(rig)
    assert error.code.startswith("COLLECTION_NATIVE_STACK_NOT_READY")
    assert "ACT_STACK_READINESS_COMMAND_FAILED" in error.code
    assert rig.execution.state.lease is None and ("reset",) not in rig.events


@pytest.mark.parametrize("answer", [False, None, 1, "yes"])
def test_only_an_exact_true_counts_as_ready(flow, monkeypatch, answer):
    rig = Rig(flow, monkeypatch, build=False)
    rig.build_kwargs["ready_check"] = lambda: answer
    rig.attach(builder().build_collection_task(rig.task, **rig.build_kwargs))
    error = fault_of(rig)
    assert error.code.startswith("COLLECTION_NATIVE_STACK_NOT_READY")
    assert "COLLECTION_READY_CHECK_NOT_TRUE" in error.code


def test_a_gate_that_turns_unready_after_start_is_a_fault_with_its_cause(flow, monkeypatch):
    answers = iter([True])

    def check():
        if next(answers, False):
            return True
        raise ValueError("ACT_STACK_PHYSICS_NOT_ADVANCING")

    rig = Rig(flow, monkeypatch, build=False)
    rig.build_kwargs["ready_check"] = check
    rig.attach(builder().build_collection_task(rig.task, **rig.build_kwargs))
    error = fault_of(rig)
    assert error.code == "TASK_RUNTIME_NOT_READY: ACT_STACK_PHYSICS_NOT_ADVANCING"
    assert rig.execution.state.lease is None


@pytest.mark.parametrize("supplied", ["missing", "not_callable", "the_consumed_start_probe"])
def test_build_refuses_without_a_repeatable_ready_check(env, supplied):
    kwargs = {}
    if supplied == "not_callable":
        kwargs["ready_check"] = "ready"
    elif supplied == "the_consumed_start_probe":
        kwargs["ready_check"] = env.stack.ready_probe
    with pytest.raises(ValueError, match="COLLECTION_READY_CHECK_REQUIRED"):
        builder().build_collection_task(
            make_task(env), stack=env.stack, shard_spec=env.spec, output_root=env.output,
            teacher_socket=TEACHER_SOCKET, **kwargs)
    assert not (env.output / "tasks").exists()
