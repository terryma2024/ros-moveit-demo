"""Phase deadlines, the refusal of limits that do not fit the total, and the memory-derived processor count (pure functions)."""

import pytest

from so101_demo.runtime.container_campaign.processing_limits import (
    DEFAULT_MAX_ATTEMPTS, DEFAULT_RESERVE_S, DEFAULT_TASK_TIMEOUT_S, DEFAULT_VERIFICATION_RESERVE_S, processing_task_timeout_s, check_phase_limits, default_processor_count, phase1_deadline_s,
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
