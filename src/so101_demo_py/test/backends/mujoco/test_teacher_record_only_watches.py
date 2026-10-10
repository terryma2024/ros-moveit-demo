"""Teacher policy v3: the watches still subscribe, but record instead of stopping (design 2026-10-10, section 3 and 7)."""
import math
from dataclasses import replace
from types import SimpleNamespace

import pytest

from so101_demo.core.process_summary import ProcessSummary
from so101_demo.ros.teacher_safety import CollisionWatch, CupSafetyLimits, PhysicsHazardWatch

LIMITS = CupSafetyLimits(3.2101397, 9.8277581e-5)
PAIRS = frozenset({("bottom_collision", "table_collision")})
KNOWN = frozenset({"bottom_collision", "table_collision", "upper_arm_collision"})


def frame(pairs, *, step=10, truncated=False, loss=False, session="s", epoch=1):
    return {"simulation_session_id": session, "reset_epoch": epoch, "physics_step": step, "simulation_time_s": step * 0.002,
            "geom_a": [a for a, _ in pairs], "geom_b": [b for _, b in pairs], "signed_distance_m": [-2e-4] * len(pairs),
            "normal_force_n": [0.7] * len(pairs), "truncated": truncated, "evidence_loss": loss}


def sample(step, force=0.5, left=3e-5, *, truncated=False, hazard=False):
    return SimpleNamespace(simulation_session_id="s", reset_epoch=1, physics_step=step, simulation_time_s=step * 0.002,
                           static_shadow_crossed=hazard, diagnostic_hazard_breached=False, truncated=truncated,
                           total_normal_force_n=force, left_fingertip_compression_m=left, right_fingertip_compression_m=0.0)


def chunk(sequence, *samples):
    return SimpleNamespace(simulation_session_id="s", reset_epoch=1, chunk_sequence=sequence, evidence_loss=False,
                           samples=list(samples))


def test_a_record_only_collision_watch_never_latches_and_offers_the_pair_to_the_tap():
    summary = ProcessSummary(limits=LIMITS)
    watch = CollisionWatch(process_pairs=PAIRS, known_geoms=KNOWN, session_id="s", reset_epoch=1, record_only=True, tap=summary)
    watch.accept(frame([("table_collision", "upper_arm_collision"), ("bottom_collision", "table_collision")]))
    assert watch.hazard is None
    assert list(summary._collisions) == [(10, 0.02, "table_collision", "upper_arm_collision", -2e-4, 0.7)]


@pytest.mark.parametrize("bad", [dict(truncated=True), dict(loss=True), dict(session="other")])
def test_a_record_only_collision_watch_marks_the_summary_incomplete_instead_of_stopping(bad):
    summary = ProcessSummary(limits=LIMITS)
    watch = CollisionWatch(process_pairs=PAIRS, known_geoms=KNOWN, session_id="s", reset_epoch=1, record_only=True, tap=summary)
    watch.accept(frame([], **bad))
    assert watch.hazard is None
    assert summary.build()["complete"] is False


def test_the_default_collision_watch_is_unchanged():
    watch = CollisionWatch(process_pairs=PAIRS, known_geoms=KNOWN, session_id="s", reset_epoch=1)
    watch.accept(frame([("table_collision", "upper_arm_collision")]))
    assert watch.hazard == "DYNAMIC_COLLISION_STOP"


def test_a_record_only_hazard_watch_records_every_step_and_never_trips():
    summary = ProcessSummary(limits=LIMITS)
    watch = PhysicsHazardWatch(session_id="s", reset_epoch=1, limits=None, clock=lambda: 1.0, record_only=True, tap=summary)
    watch.accept_chunk(chunk(1, sample(1, 0.2), sample(2, 9.0, 5e-4), sample(3, 0.1, hazard=True)))
    assert watch.limit_code is None and watch.hazard is None
    assert [item[:3] for item in summary._steps] == [(1, 0.002, 0.2), (2, 0.004, 9.0), (3, 0.006, 0.1)]
    assert watch.last_chunk_monotonic_s == 1.0


def test_a_record_only_hazard_watch_turns_gaps_and_truncation_into_incompleteness():
    summary = ProcessSummary(limits=LIMITS)
    watch = PhysicsHazardWatch(session_id="s", reset_epoch=1, limits=None, clock=lambda: 1.0, record_only=True, tap=summary)
    watch.accept_chunk(chunk(1, sample(1)))
    watch.accept_chunk(chunk(3, sample(2, truncated=True), sample(9)))
    document = summary.build()
    assert watch.hazard is None and watch.limit_code is None and watch.gaps >= 2
    assert document["complete"] is False and document["incomplete_reasons"]


def test_the_default_hazard_watch_still_trips_and_has_no_tap():
    watch = PhysicsHazardWatch(session_id="s", reset_epoch=1, limits=LIMITS, clock=lambda: 1.0)
    watch.accept_chunk(chunk(1, sample(1, 9.0)))
    assert watch.limit_code == "DYNAMIC_CUP_FORCE_EXCEEDED"


def test_the_world_observer_offers_accepted_evidence_to_a_tap_and_counts_truncated_messages(monkeypatch):
    from so101_demo.backends.mujoco import observer as world_module
    from so101_demo.core.simulation.types import ObjectState, SimulationEvidence
    monkeypatch.setattr(world_module, "convert_message", lambda message: message)
    world = world_module.MujocoWorldObserver(SimpleNamespace(create_subscription=lambda *args: object()), "session-1",
                                             monotonic=lambda: 10.)
    first = SimulationEvidence(
        simulation_time_s=1., frame_id="world", publisher_sequence=1, simulation_step=1, reset_epoch=1,
        simulation_session_id="session-1", paused=False,
        object_state=ObjectState(body_id=1, body="cup", position_world=(0., 0., 0.), orientation_xyzw=(0., 0., 0., 1.),
                                 linear_velocity_world=(0., 0., 0.), angular_velocity_world=(0., 0., 0.)),
        has_contact=False, minimum_signed_distance_m=0., maximum_normal_force_n=0., truncated=False,
        left_fingertip_contacts=(), right_fingertip_contacts=(), other_object_contacts=())
    seen = []
    world.add_tap(lambda evidence, receipt: seen.append((evidence.publisher_sequence, receipt)))
    world.add_tap(lambda evidence, receipt: 1 / 0)               # a failing tap changes nothing
    world.accept(first, received_at_s=10.)
    with pytest.raises(world_module.EvidenceRejected):
        world.accept(replace(first, publisher_sequence=2, simulation_step=2, truncated=True), received_at_s=10.)
    assert seen == [(1, 10.)] and world.truncated_count == 1 and world.snapshot().publisher_sequence == 1


# ---- receipts for the silent-stream rule ---------------------------------------------------------------------------------------

def test_the_record_only_watches_report_every_receipt_to_the_summary():
    summary = ProcessSummary(limits=LIMITS)
    summary.silence_limit_s = 1.0
    now = [100.0]
    collision = CollisionWatch(process_pairs=PAIRS, known_geoms=KNOWN, session_id="s", reset_epoch=1, record_only=True, tap=summary,
                               clock=lambda: now[0])
    hazard = PhysicsHazardWatch(session_id="s", reset_epoch=1, limits=None, clock=lambda: now[0], record_only=True, tap=summary)
    summary.phase_begin("LIFT", 1.0)
    collision.accept(frame([("bottom_collision", "table_collision")]))
    hazard.accept_chunk(chunk(1, sample(1)))
    now[0] = 101.5                                              # both streams fall silent for 1.5 s in the open phase
    collision.accept(frame([("bottom_collision", "table_collision")], step=11))
    hazard.accept_chunk(chunk(2, sample(2)))
    assert summary.build()["incomplete_reasons"] == ["COLLISION_STREAM_SILENT", "PHYSICS_STREAM_SILENT"]
    assert collision.frames_seen == 2 and hazard.chunks_seen == 2


def test_a_record_only_hazard_watch_without_limits_survives_a_normal_stream():
    summary = ProcessSummary(limits=LIMITS)
    watch = PhysicsHazardWatch(session_id="s", reset_epoch=1, limits=None, clock=lambda: 1.0, record_only=True, tap=summary)
    for sequence in range(1, 6):
        watch.accept_chunk(chunk(sequence, sample(sequence)))
    assert watch.limit_code is None and watch.gaps == 0
