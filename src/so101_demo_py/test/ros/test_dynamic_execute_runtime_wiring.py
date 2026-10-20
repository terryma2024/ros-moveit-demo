"""`run_dynamic_execute` wires the stop flags, the deadline and rclpy's signal option; first-evidence reset boundary."""

import signal
from types import SimpleNamespace

from test_dynamic_scene_sync import RecordingTaskScenePort, _observation, _options, _runtime
from test_teacher_stop_flags_and_cup_safety import evidence


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
        value._execution_policy = {"execution_deadline_s": 180.0}
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


def _boundary_run(schema, paused_steps, steps=(1, 2, 3, 4, 5, 6)):
    from dataclasses import replace
    from so101_demo.core.simulation.types import ReceivedSimulationEvidence
    from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution
    value = object.__new__(RosDynamicMujocoExecution)
    value._session_id, value._expected_reset_epoch = "s", 1
    value._execution_policy = None if schema is None else {"schema_version": schema}
    value.observer = SimpleNamespace(retained_with_receipts=lambda: tuple(
        ReceivedSimulationEvidence(replace(evidence(step=step), paused=step in paused_steps), step * 0.01)
        for step in steps))
    return value


def test_schema_4_reset_boundary_is_the_first_record_after_the_last_pause_in_the_ring():
    assert _boundary_run(4, {3, 4})._verified_reset_boundary()["simulation_step"] == 5
    # several pauses: the last one counts
    assert _boundary_run(4, {2, 5})._verified_reset_boundary()["simulation_step"] == 6


def test_schema_3_and_an_unreadable_schema_keep_the_first_record_as_the_boundary():
    for schema in (3, None):
        assert _boundary_run(schema, {3, 4})._verified_reset_boundary()["simulation_step"] == 1


def test_schema_4_without_a_paused_record_keeps_the_first_record_as_the_boundary():
    assert _boundary_run(4, set())._verified_reset_boundary()["simulation_step"] == 1


def test_schema_4_fails_closed_when_the_ring_is_all_paused_or_ends_paused():
    import pytest
    for paused in ({1, 2, 3, 4, 5, 6}, {5, 6}):
        with pytest.raises(RuntimeError, match="TEACHER_RESET_BOUNDARY_PAUSED_RING"):
            _boundary_run(4, paused)._verified_reset_boundary()
