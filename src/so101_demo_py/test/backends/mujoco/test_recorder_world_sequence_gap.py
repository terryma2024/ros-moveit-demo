"""L2 81fa2857 sealed 378 rows and 756 frames and was INVALID.

Reasons: "atomic evidence publisher sequence gap" (sticky hazard of the Recorder's world observer, first read 19 ms after the
capture start), then LIVE_PHYSICAL_SCENE_GEOMETRY_INVALID at the end of the recording (sim 50.5 s) and the seal failure. The
retained data has exactly one source alignment association (the initial one): once the first reason was latched the engine stopped handing
the Teacher's later scene operations to source alignment, so the scene that changed at the end had no association. The row check was right;
its input was missing because of the first reason.

A world gap is a defect of the data only where the data is: the capture retains world evidence from the predecessor of its
start. A gap before that point (the Recorder's own startup, 0.5 s hiccup seen at the first chunk) is outside the retained
record. A gap inside the retained record stays INVALID.
"""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from test_mujoco_observer import _world_pair


def feed(world, first, sequences, *, start_step=1):
    step = start_step
    for sequence in sequences:
        world.accept(replace(first, publisher_sequence=sequence, simulation_step=step, simulation_time_s=step * 0.012),
                     received_at_s=10.)
        step += 1


def test_a_gap_before_the_retained_range_does_not_poison_the_data(monkeypatch):
    from so101_demo.backends.mujoco import observer as module
    gaps = []
    world, first = _world_pair(module, monkeypatch, on_sequence_gap=lambda *args: gaps.append(args), history_capacity=64)
    feed(world, first, [1, 2, 3, 7, 8, 9, 10, 11])      # 4..6 never arrived (startup)
    assert gaps == [(3, 7)]
    records = world.original_records_after(7 - 1)       # the capture is retained from the predecessor: sequence 7
    assert [item.evidence.publisher_sequence for item in records] == [7, 8, 9, 10, 11]


def test_a_gap_inside_the_retained_range_is_still_invalid(monkeypatch):
    from so101_demo.backends.mujoco import observer as module
    world, first = _world_pair(module, monkeypatch, on_sequence_gap=lambda *args: None, history_capacity=64)
    feed(world, first, [1, 2, 3, 4, 5, 9, 10])
    with pytest.raises(module.EvidenceRejected, match="publisher sequence gap"):
        world.original_records_after(3)
    assert [item.evidence.publisher_sequence for item in world.original_records_after(8)] == [9, 10]


def test_the_observer_keeps_what_it_saw_at_each_gap_and_rejection(monkeypatch):
    from so101_demo.backends.mujoco import observer as module
    world, first = _world_pair(module, monkeypatch, on_sequence_gap=lambda *args: None, history_capacity=64)
    feed(world, first, [1, 2, 6])
    log = world.diagnostics()
    assert [(item["previous_sequence"], item["sequence"], item["missing"]) for item in log["gaps"]] == [(2, 6, 3)]
    assert log["callbacks"] >= 0 and log["gaps"][0]["received_monotonic_s"] == 10.


def test_the_world_observer_does_not_latch_a_sticky_hazard_at_a_gap_the_records_are_judged_instead(monkeypatch):
    from so101_demo.act.offline.sources import OfflineRosSources
    from so101_demo.backends.mujoco import observer as module
    monkeypatch.setattr(module, "convert_message", lambda message: message)
    sources = OfflineRosSources.__new__(OfflineRosSources)
    node = SimpleNamespace(create_subscription=lambda *args: object())
    world = sources._default_world_factory(node, "session-1")
    _, first = _world_pair(module, monkeypatch)
    feed(world, first, [1, 2, 5, 6])
    assert world.diagnostics()["gaps"][0]["previous_sequence"] == 2
    assert [item.evidence.publisher_sequence for item in world.original_records_after(4)] == [5, 6]
    with pytest.raises(module.EvidenceRejected, match="sequence gap"):
        world.original_records_after(0)


def test_scene_operations_still_reach_alignment_after_the_data_was_found_invalid(tmp_path):
    from test_act_episode_recorder import build, teacher_script
    script = teacher_script(leading=[("scene_operation", {"operation": "apply", "state": "SETUP"})])
    early = script.pop(-1)
    engine, sources, working = build(tmp_path, script=script)
    engine.latch("SOMETHING_EARLIER")
    for text in early:
        engine.on_event_text(text)
    engine.step()
    assert "scene_operation" in sources.events_seen, "source alignment keeps building the associations the later rows need"
