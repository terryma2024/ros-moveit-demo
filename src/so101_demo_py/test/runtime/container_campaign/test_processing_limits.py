"""Phase deadlines, the refusal of limits that do not fit the total, and the memory-derived processor count (pure functions)."""

import pytest

from so101_demo.runtime.container_campaign.processing_limits import (
    DEFAULT_MAX_ATTEMPTS, DEFAULT_RESERVE_S, DEFAULT_TASK_TIMEOUT_S, DEFAULT_VERIFICATION_RESERVE_S, processing_task_timeout_s, check_phase_limits, default_processor_count, effective_batch_total_s, phase1_deadline_s,
    phase2_deadline_s, processing_max_attempts, processor_count_for)

GIB = 2**30
TOTAL = 5400


@pytest.mark.parametrize("config", [
    {}, {"collect_timeout_s": 3000}, {"process_timeout_s": 2400}, {"collect_timeout_s": 3000, "process_timeout_s": 2400},
    {"processing_reserve_s": 1800}, {"collect_timeout_s": 1, "process_timeout_s": TOTAL - 1}])
def test_limits_that_fit_the_total_are_accepted(config):
    check_phase_limits(config, TOTAL)


@pytest.mark.parametrize("config", [
    {"collect_timeout_s": 3000, "process_timeout_s": 2401}, {"collect_timeout_s": TOTAL + 1}, {"process_timeout_s": TOTAL + 1},
    {"processing_reserve_s": TOTAL}, {"processing_reserve_s": TOTAL + 1}])
def test_limits_that_exceed_the_total_are_refused(config):
    with pytest.raises(ValueError, match="CAMPAIGN_PHASE_LIMITS_EXCEED_TOTAL"):
        check_phase_limits(config, TOTAL)


def test_without_per_phase_limits_phase_one_stops_when_the_reserve_is_left():
    assert DEFAULT_RESERVE_S == 1800
    assert phase1_deadline_s({}, admitted_s=100., total_deadline_s=100. + TOTAL) == 100. + TOTAL - 1800
    assert phase1_deadline_s({"processing_reserve_s": 600}, admitted_s=100., total_deadline_s=100. + TOTAL) == 100. + TOTAL - 600


def test_collect_timeout_is_measured_from_admission_and_never_passes_the_total():
    assert phase1_deadline_s({"collect_timeout_s": 3000}, admitted_s=100., total_deadline_s=100. + TOTAL) == 3100.
    assert phase1_deadline_s({"collect_timeout_s": 3000, "processing_reserve_s": 1}, admitted_s=100., total_deadline_s=2000.) == 2000.


def test_a_process_timeout_alone_reserves_exactly_that_long_after_phase_one():
    assert phase1_deadline_s({"process_timeout_s": 2400}, admitted_s=0., total_deadline_s=TOTAL) == TOTAL - 2400


def test_process_timeout_is_measured_from_the_start_of_phase_two_and_is_capped_by_the_total():
    assert phase2_deadline_s({}, phase2_start_s=2000., total_deadline_s=5400.) == 5400. - 600
    assert phase2_deadline_s({"process_timeout_s": 1000}, phase2_start_s=2000., total_deadline_s=5400.) == 3000.
    assert phase2_deadline_s({"process_timeout_s": 4000}, phase2_start_s=2000., total_deadline_s=5400.) == 5400. - 600


def test_phase_two_leaves_a_verification_reserve_for_the_hosts_readback():
    assert DEFAULT_VERIFICATION_RESERVE_S == 600
    assert phase2_deadline_s({"verification_reserve_s": 100}, phase2_start_s=2000., total_deadline_s=5400.) == 5300.
    assert phase2_deadline_s({"verification_reserve_s": 100, "process_timeout_s": 1000}, phase2_start_s=2000.,
                             total_deadline_s=5400.) == 3000.
    with pytest.raises(ValueError, match="CAMPAIGN_PHASE_LIMITS_EXCEED_TOTAL"):
        check_phase_limits({"verification_reserve_s": TOTAL}, TOTAL)


def test_a_processing_task_has_its_own_time_budget():
    assert DEFAULT_TASK_TIMEOUT_S == 1800
    assert processing_task_timeout_s({}) == 1800 and processing_task_timeout_s({"processing_task_timeout_s": 2400}) == 2400


@pytest.mark.parametrize("available_gib,expected", [(0.5, 1), (2.9, 1), (3, 1), (8.9, 2), (36, 12), (500, 12), (100, 12)])
def test_default_processor_count_is_memory_over_three_gib_between_one_and_twelve(available_gib, expected):
    assert default_processor_count(int(available_gib * GIB)) == expected


def test_a_configured_processor_count_overrides_the_default_but_never_exceeds_the_queue():
    assert processor_count_for({}, queue_length=40, available_bytes=18 * GIB) == 6
    assert processor_count_for({"processor_count": 16}, queue_length=40, available_bytes=18 * GIB) == 16
    assert processor_count_for({"processor_count": 16}, queue_length=3, available_bytes=18 * GIB) == 3
    assert processor_count_for({}, queue_length=2, available_bytes=300 * GIB) == 2
    assert processor_count_for({}, queue_length=1, available_bytes=0) == 1


def test_max_attempts_default_is_three():
    assert DEFAULT_MAX_ATTEMPTS == 3 and processing_max_attempts({}) == 3 and processing_max_attempts({"processing_max_attempts": 5}) == 5


def test_the_9000_s_campaign_total_fits_both_phases_and_the_default_reserves():
    from so101_demo.runtime.container_campaign.processing_limits import check_phase_limits, phase1_deadline_s
    check_phase_limits({"collect_timeout_s": 5000, "process_timeout_s": 3400}, 9000.)
    # phase 1 dispatch stops at total - processing_reserve_s (1800); phase 2 ends at total - verification_reserve_s (600)
    assert phase1_deadline_s({}, admitted_s=0., total_deadline_s=9000.) == 7200.
    assert phase2_deadline_s({}, phase2_start_s=7000., total_deadline_s=9000.) == 8400.


def test_the_campaign_config_total_replaces_the_runtime_yaml_total_and_names_its_source():
    assert effective_batch_total_s({}, 9000.0) == (9000.0, "runtime yaml")
    assert effective_batch_total_s({"batch_hard_timeout_s": 4000}, 9000.0) == (4000, "campaign config")
    assert effective_batch_total_s({"batch_hard_timeout_s": 14400}, 9000.0) == (14400, "campaign config")


@pytest.mark.parametrize('cap,recording_s', [(8, 2160), (4, 3480)])
def test_retry_fallback_covers_every_sequential_task_batch_and_real_processor_startup(cap, recording_s):
    from so101_demo.runtime.container_campaign.processing_limits import retry_round_plan
    runtime = dict(initializing_hard_timeout_s=180, executing_hard_timeout_s=300,
                   finalizing_hard_timeout_s=120, worker_recovery_timeout_s=60)
    estimate = retry_round_plan({'max_concurrent_recordings': cap}, now_s=100, total_deadline_s=10000,
                               scene_count=20, worker_count=8, processor_count=8, observed={}, runtime=runtime)
    assert estimate['components']['recording_s'] == recording_s
    assert estimate['components']['processor_start_s'] == 180
    assert estimate['components']['processing_s'] == 5580
    assert estimate['needed_s'] == recording_s + 60 + 5580


def test_retry_observations_take_precedence_and_leave_the_verification_reserve():
    from so101_demo.runtime.container_campaign.processing_limits import retry_round_plan
    estimate = retry_round_plan({'verification_reserve_s': 600}, now_s=100, total_deadline_s=1000,
                               scene_count=2, worker_count=8, processor_count=2,
                               observed=dict(wave_wall_s=[100, 120], task_s=[80, 90], sync_s=10,
                                             processor_start_s=[20, 30]), runtime={})
    assert estimate['needed_s'] == 250 and estimate['recording_deadline_s'] == 270
    assert estimate['fits'] is True and estimate['available_s'] == 300


@pytest.mark.parametrize('extra,recording_s', [({'max_tasks_in_flight': 2}, 6780), ({'min_assignment_gap_s': 1000}, 19840)])
def test_retry_fallback_respects_the_task_gate_and_assignment_spacing(extra, recording_s):
    from so101_demo.runtime.container_campaign.processing_limits import retry_round_plan
    runtime = dict(initializing_hard_timeout_s=180, executing_hard_timeout_s=300,
                   finalizing_hard_timeout_s=120, worker_recovery_timeout_s=60)
    estimate = retry_round_plan(extra, now_s=100, total_deadline_s=10000, scene_count=20, worker_count=8,
                               processor_count=8, observed={}, runtime=runtime)
    assert estimate['components']['recording_s'] == recording_s
    assert estimate['fits'] is False
