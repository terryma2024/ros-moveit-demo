"""The plugin's two per-step hazard flags (`static_shadow_crossed`, `diagnostic_hazard_breached`) stop the Teacher.

Plugin source (`simulation_evidence_plugin.cpp:418-420`): `static_shadow_crossed` = largest single cup contact force of
the step > `static_shadow_force_n` (1.1579004532160448 N), `diagnostic_hazard_breached` = summed cup contact force
>= `diagnostic_hard_stop_force_n` (11.60 N), both on every physics step (500 Hz) in `PhysicsStepEvidence` chunks, while
`SimulationEvidence` is published at 100 Hz. The frozen sum limit (3.21 N) does not imply the single-contact 1.158 N rule.
"""
from types import SimpleNamespace

import pytest

SESSION, EPOCH = "s", 1


def sample(step, *, shadow=False, hazard=False, session=SESSION, epoch=EPOCH):
    return SimpleNamespace(simulation_session_id=session, reset_epoch=epoch, physics_step=step,
                           static_shadow_crossed=shadow, diagnostic_hazard_breached=hazard,
                           model_qpos=[0.0] * 14)


def chunk(*samples):
    return SimpleNamespace(simulation_session_id=SESSION, reset_epoch=EPOCH, samples=list(samples))


def watch():
    from so101_demo.ros.teacher_safety import PhysicsHazardWatch
    return PhysicsHazardWatch(session_id=SESSION, reset_epoch=EPOCH)


def test_quiet_chunks_do_not_latch():
    value = watch()
    value.accept_chunk(chunk(sample(1), sample(2)))
    assert value.hazard is None and value.chunks_seen == 1


@pytest.mark.parametrize("flag,name", [("shadow", "static_shadow_crossed"), ("hazard", "diagnostic_hazard_breached")])
def test_either_plugin_flag_latches_with_the_first_step(flag, name):
    value = watch()
    value.accept_chunk(chunk(sample(1), sample(2, **{flag: True}), sample(3, **{flag: True})))
    assert value.hazard == "DYNAMIC_PHYSICS_HAZARD" and value.hazard_step == 2 and name in value.detail
    value.accept_chunk(chunk(sample(4)))
    assert value.hazard == "DYNAMIC_PHYSICS_HAZARD" and value.hazard_step == 2  # latched


def test_samples_of_an_earlier_epoch_or_another_session_are_ignored():
    value = watch()
    value.accept_chunk(chunk(sample(1, shadow=True, epoch=0), sample(2, hazard=True, session="other")))
    assert value.hazard is None


def test_the_watch_keeps_no_per_sample_copy():
    value = watch()
    value.accept_chunk(chunk(*[sample(step) for step in range(1, 51)]))
    assert not any(isinstance(item, (list, tuple, dict)) and len(item) > 4 for item in vars(value).values())


def test_subscription_uses_the_chunk_topic_with_a_bounded_queue():
    seen = {}

    class Node:
        def create_subscription(self, message_type, topic, callback, qos):
            seen.update(type=message_type.__name__, topic=topic, depth=qos.depth, callback=callback)
            return object()

    value = watch()
    value.attach(Node())
    assert seen["type"] == "PhysicsStepEvidenceChunk" and seen["topic"] == "/so101/simulation/physics_step_chunks"
    assert 1 <= seen["depth"] <= 200
    seen["callback"](chunk(sample(7, shadow=True)))
    assert value.hazard_step == 7


def test_the_monitor_stops_on_a_latched_plugin_hazard_and_the_code_is_terminal(tmp_path):
    from test_teacher_moveit_execution import make_adapter, run_monitor
    from so101_demo.core.workflow import TERMINAL_STOP_CODES
    adapter = make_adapter(tmp_path)
    value = watch()
    adapter._physics_hazard_watch = value
    run_monitor(adapter)
    value.accept_chunk(chunk(sample(9, shadow=True)))
    with pytest.raises(RuntimeError, match="DYNAMIC_PHYSICS_HAZARD"):
        run_monitor(adapter)
    assert "DYNAMIC_PHYSICS_HAZARD" in TERMINAL_STOP_CODES
