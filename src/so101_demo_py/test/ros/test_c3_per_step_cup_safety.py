"""C3(a): the cup force and compression rule is evaluated on EVERY physics step of the chunk stream (500 Hz).

The Teacher monitor reads the latest `SimulationEvidence` (~100 Hz); the profile of CP-3375 showed a 5-step spike
(steps 21520-21524: 4.40 N, 1.30e-4 m) it never saw. The rows below are `c2-profile/profile.csv` steps 21515-21530
(summed force N, left compression m); the limits are the frozen activated values.
"""
from types import SimpleNamespace

import pytest

from so101_demo.ros.teacher_safety import CupSafetyLimits

SESSION, EPOCH = "s", 1
FORCE_LIMIT, COMPRESSION_LIMIT = 3.2101397, 9.8277581e-5
PROFILE = [  # (step, summed force N, left compression m) from c2-profile/profile.csv
    (21515, 0.0, 0.0), (21516, 0.40993026676284083, 3.09705770252534e-05),
    (21517, 1.331641584290165, 5.300261762189858e-05), (21518, 1.775598979929368, 5.0668440913363644e-05),
    (21519, 3.0176913772646405, 4.493579501336501e-05), (21520, 4.40091805878215, 5.189615382009025e-05),
    (21521, 3.6664615273124697, 8.763486803425069e-05), (21522, 3.7937712859662844, 0.00011904967512230916),
    (21523, 4.050921588302689, 0.00013041020492275974), (21524, 3.758807214131359, 0.00011791290775453825),
    (21525, 3.1771699386974244, 9.236116035164599e-05), (21526, 2.955233186744276, 6.896009703335621e-05),
    (21527, 2.7288554594262524, 5.4426994142440634e-05), (21528, 2.291809373870562, 5.161600802383852e-05),
    (21529, 2.083419925629254, 5.3703347114892274e-05), (21530, 1.9659914488629322, 5.647686716585568e-05),
]


def sample(step, force=0.5, left=3e-5, right=0.0, *, truncated=False, session=SESSION, epoch=EPOCH):
    return SimpleNamespace(
        simulation_session_id=session, reset_epoch=epoch, physics_step=step, static_shadow_crossed=False,
        diagnostic_hazard_breached=False, truncated=truncated, total_normal_force_n=force,
        left_fingertip_compression_m=left, right_fingertip_compression_m=right)


def chunk(sequence, *samples, evidence_loss=False):
    return SimpleNamespace(simulation_session_id=SESSION, reset_epoch=EPOCH, chunk_sequence=sequence,
                           evidence_loss=evidence_loss, samples=list(samples))


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def watch(*, limits=CupSafetyLimits(FORCE_LIMIT, COMPRESSION_LIMIT), state="CLOSE_GRIPPER", clock=None):
    from so101_demo.ros.teacher_safety import PhysicsHazardWatch
    return PhysicsHazardWatch(session_id=SESSION, reset_epoch=EPOCH, limits=limits, state_getter=lambda: state,
                              clock=clock or Clock())


def feed(value, rows, *, first_sequence=1, per_chunk=5):
    rows = list(rows)
    for index in range(0, len(rows), per_chunk):
        value.accept_chunk(chunk(first_sequence + index // per_chunk,
                                 *[sample(step, force, left) for step, force, left in rows[index:index + per_chunk]]))


def test_the_real_close_gripper_spike_between_100_hz_samples_trips_on_its_first_step():
    value = watch()
    feed(value, PROFILE)
    assert value.limit_code == "DYNAMIC_CUP_FORCE_EXCEEDED"
    assert value.limit_step == 21520 and value.limit_state == "CLOSE_GRIPPER"
    assert value.limit_value == pytest.approx(4.40091805878215)
    assert "per-step" in value.limit_detail and "21520" in value.limit_detail and "CLOSE_GRIPPER" in value.limit_detail


def test_a_100_hz_subsample_that_straddles_the_spike_would_have_missed_the_compression_part():
    # the compression excursion lasts steps 21522-21524; samples at 21520 and 21525 (and the force at 21525, 3.18 N,
    # is below the force limit) see neither, which is how the ~100 Hz monitor missed it
    sampled = [row for row in PROFILE if row[0] in (21515, 21525)]
    assert all(force <= FORCE_LIMIT and left <= COMPRESSION_LIMIT for _step, force, left in sampled)
    value = watch(limits=CupSafetyLimits(1e9, COMPRESSION_LIMIT))
    feed(value, PROFILE)
    assert value.limit_code == "DYNAMIC_CUP_COMPRESSION_EXCEEDED" and value.limit_step == 21522
    assert value.limit_value == pytest.approx(0.00011904967512230916)


def test_a_value_exactly_at_the_limit_does_not_trip_and_both_comparisons_are_strict():
    value = watch()
    value.accept_chunk(chunk(1, sample(1, force=FORCE_LIMIT, left=COMPRESSION_LIMIT, right=COMPRESSION_LIMIT)))
    assert value.limit_code is None
    value.accept_chunk(chunk(2, sample(2, force=FORCE_LIMIT + 1e-9)))
    assert value.limit_code == "DYNAMIC_CUP_FORCE_EXCEEDED"


def test_compression_is_the_larger_of_the_two_fingers():
    value = watch()
    value.accept_chunk(chunk(1, sample(1, left=1e-5, right=COMPRESSION_LIMIT * 1.01)))
    assert value.limit_code == "DYNAMIC_CUP_COMPRESSION_EXCEEDED" and value.limit_step == 1


def test_only_the_first_violating_step_is_kept_and_other_epochs_are_ignored():
    value = watch()
    value.accept_chunk(chunk(1, sample(1, force=9.0, epoch=0), sample(2, force=9.0, session="other")))
    assert value.limit_code is None
    value.accept_chunk(chunk(2, sample(3, force=4.0), sample(4, force=8.0)))
    value.accept_chunk(chunk(3, sample(5, force=9.0)))
    assert value.limit_step == 3 and value.limit_value == 4.0


def test_without_limits_the_watch_is_the_old_flag_only_watch():
    value = watch(limits=None)
    value.accept_chunk(SimpleNamespace(simulation_session_id=SESSION, reset_epoch=EPOCH, samples=[
        SimpleNamespace(simulation_session_id=SESSION, reset_epoch=EPOCH, physics_step=1,
                        static_shadow_crossed=False, diagnostic_hazard_breached=False)]))
    assert value.limit_code is None and value.gaps == 0


# ---- missing or gapped evidence is unavailable, never OK ----------------------------------------------------

def test_a_chunk_sequence_gap_a_step_gap_loss_or_a_truncated_sample_count_as_a_gap():
    value = watch()
    value.accept_chunk(chunk(1, sample(1), sample(2)))
    value.accept_chunk(chunk(3, sample(3)))                       # chunk 2 missing
    assert value.gaps == 1 and "chunk_sequence" in value.gap_detail
    value.accept_chunk(chunk(4, sample(7)))                       # steps 6 missing inside a continuing sequence
    assert value.gaps == 2 and "physics_step" in value.gap_detail
    value.accept_chunk(chunk(5, sample(8), evidence_loss=True))
    assert value.gaps == 3 and "evidence_loss" in value.gap_detail
    value.accept_chunk(chunk(6, sample(9, truncated=True)))
    assert value.gaps == 4 and "truncated" in value.gap_detail


def test_a_contiguous_stream_has_no_gap_and_tracks_the_last_chunk_time():
    clock = Clock()
    value = watch(clock=clock)
    feed(value, [(step, 0.5, 3e-5) for step in range(1, 21)])
    assert value.gaps == 0 and value.last_chunk_monotonic_s == clock.now


# ---- the Teacher monitor stops on the per-step latch, gaps and silence ---------------------------------------

def adapter(tmp_path, plugin):
    from test_b1_teacher_execution import make_adapter
    value = make_adapter(tmp_path)
    value._physics_hazard_watch = plugin
    return value


def test_the_monitor_stops_on_a_per_step_violation_the_100_hz_sample_never_showed(tmp_path):
    from test_b1_teacher_execution import run_monitor
    clock = Clock()
    plugin = watch(clock=clock)
    value = adapter(tmp_path, plugin)
    plugin.clock = value._monotonic
    plugin.arm()
    run_monitor(value)                                     # nominal 100 Hz sample, nothing latched
    feed(plugin, PROFILE)
    with pytest.raises(RuntimeError, match="DYNAMIC_CUP_FORCE_EXCEEDED"):
        run_monitor(value)
    violation = value._document["monitor_violation"]
    assert violation["reason"] == "DYNAMIC_CUP_FORCE_EXCEEDED"
    assert violation["per_step"] == {"step": 21520, "state": "CLOSE_GRIPPER", "value": 4.40091805878215,
                                     "limit": FORCE_LIMIT, "kind": "summed_force_n"}


def test_a_gap_after_the_goal_began_stops_as_unavailable_and_an_earlier_gap_does_not(tmp_path):
    from test_b1_teacher_execution import no_snapshot
    from so101_demo.core.domain import State
    plugin = watch()
    value = adapter(tmp_path, plugin)
    plugin.clock = value._monotonic
    plugin.arm()
    plugin.accept_chunk(chunk(1, sample(1)))
    plugin.accept_chunk(chunk(3, sample(9)))               # a gap before this goal began
    no_snapshot(value)
    monitor = value._motion_monitor(State.MOVE_ABOVE_PLACE)
    plugin.accept_chunk(chunk(4, sample(10)))
    monitor()
    plugin.accept_chunk(chunk(6, sample(20)))              # chunk 5 lost while the goal is active
    with pytest.raises(RuntimeError, match="DYNAMIC_STATE_UNAVAILABLE_STOP"):
        monitor()


def test_a_silent_chunk_stream_stops_after_the_unavailable_bound(tmp_path):
    from test_b1_teacher_execution import no_snapshot, evidence
    from so101_demo.core.domain import State
    plugin = watch()
    value = adapter(tmp_path, plugin)
    plugin.clock = value._monotonic
    plugin.arm()
    plugin.accept_chunk(chunk(1, sample(1)))
    no_snapshot(value)
    monitor = value._motion_monitor(State.MOVE_ABOVE_PLACE)
    monitor()
    stop_after = value._execution_policy["state_unavailable_stop_s"]
    value._now[0] += 0.1
    value.observer.put(evidence())
    value._joint_state_received_monotonic_s = value._now[0]
    monitor()                                             # silent for 0.1 s: tolerated
    value._now[0] += stop_after + 0.2
    value.observer.put(evidence())
    value._joint_state_received_monotonic_s = value._now[0]
    with pytest.raises(RuntimeError, match="DYNAMIC_STATE_UNAVAILABLE_STOP"):
        monitor()
