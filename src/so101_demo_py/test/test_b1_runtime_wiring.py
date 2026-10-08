"""B1: `run_dynamic_execute` wires the stop flags, the deadline and rclpy's signal option; first-evidence reset boundary."""

import signal
from types import SimpleNamespace

from test_dynamic_scene_sync import RecordingTaskScenePort, _observation, _options, _runtime
from test_b1_teacher_stop_core import evidence


def _run(tmp_path, *, no_option=False):
    from so101_demo.ros.dynamic_runtime import run_dynamic_execute
    events = []
    runtime = _runtime(events, observations=tuple(_observation(simulator_x=-0.03, moveit_x=-0.03) for _ in range(3)),
                       scene=RecordingTaskScenePort())
    sentinel = object()
    seen = {}
    original_init = runtime.rclpy.init
    def init(**kwargs):
        seen["init"] = kwargs
        original_init()
    runtime.rclpy.init = init
    if not no_option:
        runtime.signal_handler_options_no = sentinel
    holder = {}
    original_execution = runtime.execution
    def execution(*args, **kwargs):
        value = original_execution(*args, **kwargs)
        value._teacher_execution_policy = {"execution_deadline_s": 180.0}
        holder["execution"] = value
        return value
    runtime.execution = execution
    handler_during = {}
    original_run = runtime.runner
    def runner(actions, **kwargs):
        value = original_run(actions, **kwargs)
        inner = value.run
        def run(request):
            handler_during["sigint"] = signal.getsignal(signal.SIGINT)
            return inner(request)
        value.run = run
        return value
    runtime.runner = runner
    before = signal.getsignal(signal.SIGINT)
    code = run_dynamic_execute(_options(tmp_path), _runtime=runtime)
    return code, seen, sentinel, holder, handler_during, before


def test_rclpy_is_initialised_without_its_own_signal_handler(tmp_path):
    code, seen, sentinel, *_ = _run(tmp_path)
    assert code == 0 and seen["init"] == {"signal_handler_options": sentinel}


def test_runtime_without_the_option_keeps_the_plain_init(tmp_path):
    code, seen, *_ = _run(tmp_path, no_option=True)
    assert code == 0 and seen["init"] == {}


def test_stop_flags_deadline_and_signal_handler_are_installed_for_the_run_and_restored(tmp_path):
    code, _seen, _sentinel, holder, during, before = _run(tmp_path)
    flags = holder["execution"]._stop_flags
    assert flags is not None and flags.reason() is None
    assert flags._deadline_at is not None  # armed from the frozen execution policy (180 s)
    assert during["sigint"] != before and callable(during["sigint"])
    assert signal.getsignal(signal.SIGINT) == before


def test_reset_complete_is_announced_from_the_first_retained_evidence_of_the_epoch(tmp_path):
    from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution
    from so101_demo.core.simulation.types import ReceivedSimulationEvidence
    from dataclasses import replace
    value = object.__new__(RosDynamicMujocoExecution)
    value._session_id, value._expected_reset_epoch = "s", 1
    old = replace(evidence(step=5), reset_epoch=0)
    first, later = evidence(step=6), evidence(step=9)
    value.observer = SimpleNamespace(retained_with_receipts=lambda: tuple(
        ReceivedSimulationEvidence(item, 1.0) for item in (old, first, later)))
    assert value._verified_reset_boundary()["simulation_step"] == 6
    value.observer = SimpleNamespace(retained_with_receipts=lambda: ())
    assert value._verified_reset_boundary() is None
