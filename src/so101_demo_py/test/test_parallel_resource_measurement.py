"""Clock qualification, authorization and sealing for candidate measurement."""

import hashlib
import json
from pathlib import Path

import pytest

from so101_demo.parallel_batch.measurement_control import ProcessIdentity


@pytest.fixture
def clock_epoch():
    from so101_demo.parallel_batch.resource_measurement import ClockEpoch
    return ClockEpoch('w1', 1, 'session-1', 'reset-1', ProcessIdentity(10, 20, 30, 40), 181)


def clock_window(epoch, index, sim_delta):
    from so101_demo.parallel_batch.resource_measurement import ClockWindow
    return ClockWindow(epoch, float(index), float(index + 1), index * sim_delta,
        (index + 1) * sim_delta, 0.0, .002, 1.0, True, 'EXECUTING',
        0.0, 0.0, .05, .05, .05)


def test_quantized_one_x_is_not_a_deficit(clock_epoch):
    from so101_demo.parallel_batch.resource_measurement import rtf_interval
    window = clock_window(clock_epoch, 0, .998)
    low, high = rtf_interval(window)
    assert low <= 1.0 <= high


def test_two_nonoverlapping_deficits_fail(clock_epoch):
    from so101_demo.parallel_batch.resource_measurement import ClockQualification
    checker = ClockQualification(lag_error_s=.004, maximum_gap_s=.1, maximum_boundary_age_s=.1)
    assert checker.observe(clock_window(clock_epoch, 0, .900), cumulative_lag_s=.1).qualified
    assert not checker.observe(clock_window(clock_epoch, 1, .900), cumulative_lag_s=.2).qualified


def test_single_short_disturbance_and_overlapping_windows_do_not_double_count(clock_epoch):
    from so101_demo.parallel_batch.resource_measurement import ClockQualification
    checker = ClockQualification(lag_error_s=.004, maximum_gap_s=.1, maximum_boundary_age_s=.1)
    assert checker.observe(clock_window(clock_epoch, 0, .900), cumulative_lag_s=.1).qualified
    assert checker.observe(clock_window(clock_epoch, 1, 1.000), cumulative_lag_s=.1).qualified
    # An overlapping window must not be counted as a second independent deficit.
    assert checker.observe(clock_window(clock_epoch, 1, .900), cumulative_lag_s=.2).qualified
    assert not checker.observe(clock_window(clock_epoch, 2, .900), cumulative_lag_s=.3).qualified


def test_ineligible_or_stale_windows_are_invalid(clock_epoch):
    from so101_demo.parallel_batch.resource_measurement import ClockQualification
    checker = ClockQualification(lag_error_s=.004, maximum_gap_s=.1, maximum_boundary_age_s=.1)
    from so101_demo.parallel_batch.resource_measurement import ClockWindow
    window = clock_window(clock_epoch, 0, .900)
    stale = ClockWindow(clock_epoch, 0.0, 1.0, 0.0, .9, 0.0, .002, 1.0, True,
                        'EXECUTING', 0.0, 0.0, .05, .05, 9.0)
    decision = checker.observe(stale, cumulative_lag_s=.1)
    assert not decision.qualified
    assert 'CLOCK_STALE' in decision.reason_codes
    ineligible = ClockWindow(clock_epoch, 0.0, 1.0, 0.0, .9, 0.0, .002, 1.0, False,
                             'EXECUTING', 0.0, 0.0, .05, .05, .05)
    decision = checker.observe(ineligible, cumulative_lag_s=.1)
    assert not decision.qualified
    assert 'WINDOW_INELIGIBLE' in decision.reason_codes


def authorization_document(tmp_path, **changes):
    document = {
        "schema_version": 2, "operator_uid": 1000, "dispatch_id": "dispatch-a",
        "task_id": "task-a", "source_commit": "a" * 40,
        "execution_identity_sha256": "b" * 64, "worker_count": 2,
        "catalog_sha256": "c" * 64, "seed": 7, "lifecycle": "FULL_RESTART",
        "maximum_batches": 1, "batch_deadline_s": 5400.0,
        "expires_at_ns": 4_000_000_000_000_000_000, "batch_root": str(tmp_path / "batches"),
        "owned_scope_sha256": "d" * 64, "safety_policy_sha256": "e" * 64,
        "intent": "CALIBRATION_ONLY", "calibration_sha256": None,
    }
    document.update(changes)
    return document


def write_document(path, document, mode=0o600):
    path.parent.mkdir(mode=0o700, exist_ok=True)
    path.write_text(json.dumps(document, sort_keys=True))
    path.chmod(mode)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_authorization_is_closed_and_intent_bound(tmp_path):
    from so101_demo.parallel_batch.contracts import ContractError
    from so101_demo.parallel_batch.resource_measurement import MeasurementAuthorization
    path = tmp_path / "private/authorization.json"
    digest = write_document(path, authorization_document(tmp_path))
    authorization = MeasurementAuthorization.load(path, expected_sha256=digest)
    assert authorization.worker_count == 2
    assert authorization.intent == "CALIBRATION_ONLY"
    assert authorization.batch_deadline_s == 5400.0
    assert authorization.is_expired(now_ns=5_000_000_000_000_000_000) is True
    assert authorization.is_expired(now_ns=1) is False
    with pytest.raises(ContractError):
        MeasurementAuthorization.load(path, expected_sha256="f" * 64)
    qualification = tmp_path / "private/qualification.json"
    bad = write_document(qualification, authorization_document(tmp_path, intent="QUALIFICATION"))
    with pytest.raises(ContractError) as error:
        MeasurementAuthorization.load(qualification, expected_sha256=bad)
    assert error.value.code == "CALIBRATION_EVIDENCE_REQUIRED"
    unknown = tmp_path / "private/unknown.json"
    unknown_digest = write_document(unknown, authorization_document(tmp_path, worker_count=9))
    with pytest.raises(ContractError):
        MeasurementAuthorization.load(unknown, expected_sha256=unknown_digest)


def test_seal_measurement_writes_candidate_only_document(tmp_path):
    from so101_demo.parallel_batch.resource_measurement import (
        MeasurementAuthorization, seal_measurement)
    from so101_demo.parallel_batch.resource_identity import canonical_sha256
    path = tmp_path / "private/authorization.json"
    digest = write_document(path, authorization_document(tmp_path))
    authorization = MeasurementAuthorization.load(path, expected_sha256=digest)
    raw = tmp_path / "raw/sample.json"
    write_document(raw, {"sequence": 1})
    coverage = tmp_path / "raw/coverage.json"
    write_document(coverage, {"COLD_START": ["observed"]})
    sealed = seal_measurement(
        authorization=authorization, execution_identity_sha256="b" * 64,
        raw_files=(raw,), coverage_events=coverage,
        result={"normal_valid_runs": 1})
    document = json.loads(Path(sealed).read_bytes())
    assert document["schema_version"] == 2
    assert document["worker_count"] == 2
    assert document["execution_identity_sha256"] == "b" * 64
    assert document["raw_files"][0]["sha256"] == hashlib.sha256(raw.read_bytes()).hexdigest()
    for forbidden in ("profile", "profile_sha256", "promotion", "promotion_record_path",
                      "deployment_receipt"):
        assert forbidden not in document
    assert Path(sealed).read_bytes() == json.dumps(
        document, sort_keys=True, separators=(",", ":")).encode()
    assert json.loads(Path(sealed).read_bytes())["authorization_sha256"] == digest
