"""The ACT profile's readiness contract: the neck controller joins the node inventory and the ready probe, and a failed probe
leaves its reason in the worker result.

The native `act_diagnostic_episode run` station that used to bind the ACT launch to the frozen inputs was removed with the old
native ACT path; the container and native campaign stacks come from `act_stack` and `ActRosRuntimePorts`.
"""
import subprocess
from types import SimpleNamespace

from so101_demo.parallel_batch.contracts.common import RunMode
from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime
from parallel_worker_runtime_support import _ProcessGroup, _resources


def started_runtime(tmp_path):
    processes = _ProcessGroup()
    runtime = build_worker_runtime(
        _resources(tmp_path / "w", "worker-01", 0, 181), RunMode.EXECUTE, process_group=processes,
        reset_point=lambda _lease: None, initial_gate=lambda *_a: object(), capture_rgb=lambda *_a: None)
    runtime.start_physical_runtime()
    return runtime


def test_the_readiness_node_set_and_the_ready_probe_include_the_neck_for_the_act_profile(monkeypatch):
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts as Ports
    base = tuple(sorted(Ports.expected_worker_nodes() + (
        "/controller_manager", "/move_group/moveit", "/moveit_simple_controller_manager", "/robotsystem",
        "/move_group_private_1", "/moveit_1", "/transform_listener_impl_a")))
    assert Ports.worker_node_inventory_matches(tuple(sorted(base + ("/neck_controller",))), teacher_profile=True)
    assert not Ports.worker_node_inventory_matches(base, teacher_profile=True)       # the L1 failure: no neck
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: seen.append(argv) or SimpleNamespace(returncode=0, stdout="", stderr=""))
    ports = object.__new__(Ports)
    ports.dependencies = {"act_profile": True}
    assert ports.ready_probe(()) is True and "--include-neck" in seen[0]


def test_a_failed_ready_probe_leaves_its_reason_in_the_worker_result_not_only_in_a_log(tmp_path, monkeypatch):
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts as Ports
    reason = '{"failure_code": "MOTION_STACK_CONTROLLER_NOT_ACTIVE", "phase": "CONTROLLERS", "ready": false}'
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: SimpleNamespace(returncode=1, stdout=reason + "\n", stderr=""))
    ports = object.__new__(Ports)
    ports.dependencies = {"act_profile": True}
    assert ports.ready_probe(()) is False
    assert "MOTION_STACK_CONTROLLER_NOT_ACTIVE" in ports.ready_failure_message
    runtime = started_runtime(tmp_path)
    runtime._ready_probe = ports.ready_probe
    assert runtime.worker_ready_gate() is False
    assert "MOTION_STACK_CONTROLLER_NOT_ACTIVE" in runtime.ready_failure()
