"""Exact-N qualification: normal validity, coverage cells and fault envelopes."""

import pytest

from so101_demo.parallel_batch.measurement_control import ProcessIdentity
from so101_demo.parallel_batch.resource_identity import canonical_sha256


def normal_run(index, outcome='FAILED', coverage=None, *, worker_count=2, points=20,
               validity='VALID', full_restart=True, physics=True, resources=True,
               cleanup=True, identities=None, concurrent_window=(1.0, 2.0)):
    from so101_demo.parallel_batch.resource_measurement import RunEvidence
    return RunEvidence(
        batch_id=f'normal-{index}', worker_count=worker_count,
        execution_identity_sha256='a' * 64, validity=validity, outcome=outcome,
        full_restart=full_restart, point_count=points,
        actual_worker_identities=identities or tuple(
            ProcessIdentity(100 + slot, 1, 1000, 100 + slot)
            for slot in range(1, worker_count + 1)),
        concurrent_window=concurrent_window, coverage=dict(coverage or {}),
        sealed_manifest_sha256=canonical_sha256({'synthetic_batch': index}),
        independent_physics_verified=physics, resource_contract_verified=resources,
        cleanup_verified=cleanup)


ALL_CELLS = ('COLD_START', 'STEADY_YOLO', 'STEADY_GROUNDED_SAM', 'STEADY_MIXED',
             'MOTION_RELEASE', 'BROKER_RELOAD_WITH_N_RESIDENT',
             'WORKER_RECOVERY_WITH_N_RESIDENT', 'FINALIZATION_CLEANUP')


def full_coverage(cells=ALL_CELLS):
    return {cell: ('observed',) for cell in cells}


def accumulator(worker_count=2):
    from so101_demo.parallel_batch.resource_measurement import QualificationAccumulator
    return QualificationAccumulator(worker_count, 'a' * 64, 'b' * 64)


def test_five_valid_business_failures_do_not_fill_motion_coverage():
    q = accumulator()
    for i in range(5):
        q.add_normal(normal_run(i, coverage={'STEADY_YOLO': ('observed',)}))
    decision = q.decision()
    assert not decision.qualified
    assert 'COVERAGE_INCOMPLETE' in decision.reason_codes


def test_five_normal_runs_with_full_coverage_qualify():
    q = accumulator()
    for i in range(5):
        q.add_normal(normal_run(i, outcome='PASSED', coverage=full_coverage()))
    for cell in ALL_CELLS:
        for extra in range(2):
            q.add_coverage(normal_run(100 + extra, coverage={cell: ('observed',)}),
                           fast_channel=bool(extra))
    decision = q.decision()
    assert decision.qualified, decision.reason_codes
    record = q.seal_index()
    assert record.worker_count == 2
    assert record.normal_valid_runs == 5
    assert record.coverage_complete is True
    assert record.schema_version == 2
    for forbidden in ('profile_sha256', 'promotion_record_path', 'deployment_receipt_sha256'):
        assert forbidden not in record.as_document()


def test_invalid_runs_and_missing_concurrency_do_not_count():
    """STRUCTURALLY incomplete runs never count; an INVALID run ends the batch."""

    clean = accumulator()
    clean.add_normal(normal_run(1, coverage=full_coverage(), concurrent_window=None))
    clean.add_normal(normal_run(2, coverage=full_coverage(), identities=(
        ProcessIdentity(101, 1, 1000, 101),)))
    for i in range(5):
        clean.add_normal(normal_run(10 + i, outcome='PASSED', coverage=full_coverage()))
    assert clean.normal_run_count == 5
    assert clean.decision().qualified, clean.decision().reason_codes

    # An INVALID run does not enter the denominator and terminates this batch.
    invalid = accumulator()
    invalid.add_normal(normal_run(0, validity='INVALID', coverage=full_coverage()))
    for i in range(5):
        invalid.add_normal(normal_run(10 + i, outcome='PASSED', coverage=full_coverage()))
    decision = invalid.decision()
    assert not decision.qualified
    assert 'SEQUENCE_TERMINATED' in decision.reason_codes


def test_infra_failure_terminates_the_normal_sequence():
    q = accumulator()
    for i in range(3):
        q.add_normal(normal_run(i, outcome='PASSED', coverage=full_coverage()))
    q.add_normal(normal_run(3, outcome='INFRA_FAILURE', coverage=full_coverage()))
    for i in range(4, 9):
        q.add_normal(normal_run(i, outcome='PASSED', coverage=full_coverage()))
    decision = q.decision()
    assert not decision.qualified
    # The infrastructure failure terminates this qualification sequence even though
    # later complete runs exist; a fresh sequence needs a new sealed batch.
    assert 'SEQUENCE_TERMINATED' in decision.reason_codes
    assert q.fault_run_count == 0


def test_fault_pressure_never_extends_the_normal_or_product_sequence():
    q = accumulator()
    for i in range(5):
        q.add_normal(normal_run(i, outcome='PASSED', coverage=full_coverage()))
    coverage_before = q.coverage_counts()
    q.add_fault(normal_run(50, outcome='INFRA_FAILURE', coverage=full_coverage()))
    assert q.normal_run_count == 5
    assert q.product_success_count == 5
    assert q.fault_run_count == 1
    assert q.coverage_counts() == coverage_before


def test_worker_count_and_identity_mismatch_refuse_qualification():
    q = accumulator(worker_count=4)
    for i in range(5):
        q.add_normal(normal_run(i, outcome='PASSED', coverage=full_coverage(),
                                worker_count=4))
    for cell in ALL_CELLS:
        for extra in range(2):
            q.add_coverage(normal_run(200 + extra, worker_count=4,
                                      coverage={cell: ('observed',)}),
                           fast_channel=bool(extra))
    decision = q.decision()
    assert decision.qualified, decision.reason_codes
    assert q.seal_index().worker_count == 4

    # A four-slot qualification can never be satisfied by two-slot evidence.
    other = accumulator(worker_count=4)
    for i in range(5):
        other.add_normal(normal_run(i, outcome='PASSED', coverage=full_coverage(),
                                    worker_count=2))
    refused = other.decision()
    assert refused.qualified is False
    assert 'EXACT_N_UNQUALIFIED' in refused.reason_codes


def test_candidate_profile_stays_candidate_and_needs_reviews():
    from so101_demo.parallel_batch.resource_measurement import build_candidate_profile
    q = accumulator()
    for i in range(5):
        q.add_normal(normal_run(i, outcome='PASSED', coverage=full_coverage()))
    for cell in ALL_CELLS:
        for extra in range(2):
            q.add_coverage(normal_run(100 + extra, coverage={cell: ('observed',)}),
                           fast_channel=bool(extra))
    record = q.seal_index()
    profile = build_candidate_profile(
        execution_identity_sha256='a' * 64, coverage_policy_sha256='b' * 64,
        qualifications=(record,),
        covered_demands={2: {'startup': {
            'ram_bytes': 1.0, 'gpu_bytes': 1.0, 'cpu_core_equivalent': 1.0}}},
        uncertainty={2: {'startup': {
            'ram_bytes': 0.1, 'gpu_bytes': 0.1, 'cpu_core_equivalent': 0.1}}},
        baseline={2: {
            'ram_bytes': 10.0, 'gpu_bytes': 10.0, 'cpu_core_equivalent': 1.0}},
        audits={'raw_manifest_sha256s': record.sealed_manifest_sha256s})
    entry = profile.entry(2)
    assert entry.status == 'CANDIDATE'
    assert entry.review_reference is None
    assert profile.schema_version == 2
