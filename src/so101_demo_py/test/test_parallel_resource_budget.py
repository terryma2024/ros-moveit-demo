"""Closed allocation contexts and the exact-N resource budget provider."""

import json
from pathlib import Path

import pytest

SHA = "a" * 64
DIMENSIONS = ("cpu_core_equivalent", "ram_bytes", "gpu_bytes")


def dimension(ram, gpu=0.0, cpu=0.0):
    return {"cpu_core_equivalent": cpu, "ram_bytes": ram, "gpu_bytes": gpu}


def observation(*, length, observed_ram=None, remaining=None, error=None, capacity=None,
                attribution_complete=True, swap_delta=0, psi_full_delta=0.0, throttled=False,
                monotonic_s=1.0):
    from so101_demo.parallel_batch.resource_budget import LiveResourceObservation
    capacity = capacity or dimension(1000.0, gpu=1000.0, cpu=10.0)
    observed = observed_ram if observed_ram is not None else dimension(100.0)
    remaining = remaining if remaining is not None else dimension(100.0)
    error = error if error is not None else dimension(0.0)
    return LiveResourceObservation(
        monotonic_s=monotonic_s, capacity=capacity, observed=observed,
        background=dimension(50.0), tool_overhead=dimension(10.0), remaining=remaining,
        error=error, attribution_complete=attribution_complete, swap_delta=swap_delta,
        psi_full_delta=psi_full_delta, throttled=throttled)


def qualification_document(worker_count=2, identity=None, **changes):
    document = {
        "schema_version": 2, "execution_identity_sha256": identity or IDENTITY,
        "worker_count": worker_count,
        "coverage_policy_sha256": "b" * 64, "sealed_manifest_sha256s": ["c" * 64],
        "normal_valid_runs": 5, "normal_required_runs": 5, "coverage_complete": True,
        "cleanup_verified": True, "independent_physics_verified": True,
        "resource_contract_verified": True,
    }
    document.update(changes)
    return document


def stage_envelope():
    return {
        "demand": dimension(100.0), "uncertainty": dimension(5.0),
        "background": dimension(50.0), "tool_overhead": dimension(10.0),
        "available_headroom": dimension(100.0),
    }


def profile_document(worker_count=2, status="APPROVED", identity=None, **entry_changes):
    entry = {
        "worker_count": worker_count, "status": status,
        "qualification_sha256": identity or IDENTITY,
        "raw_manifest_sha256s": ["c" * 64],
        "coverage": {"COLD_START": ["observed"], "STEADY_YOLO": ["observed"],
                     "STEADY_GROUNDED_SAM": ["observed"], "STEADY_MIXED": ["observed"],
                     "MOTION_RELEASE": ["observed"],
                     "BROKER_RELOAD_WITH_N_RESIDENT": ["observed"],
                     "WORKER_RECOVERY_WITH_N_RESIDENT": ["observed"],
                     "FINALIZATION_CLEANUP": ["observed"]},
        "stages": {name: stage_envelope() for name in
                   ("startup", "steady", "recovery", "finalization")},
        "review_reference": "astra:review-1",
    }
    entry.update(entry_changes)
    return {
        "schema_version": 2, "execution_identity_sha256": identity or IDENTITY,
        "coverage_policy_sha256": "b" * 64,
        "entries": {str(worker_count): entry},
    }


def write_private(path: Path, document) -> str:
    import hashlib
    path.parent.mkdir(mode=0o700, exist_ok=True)
    path.write_bytes(json.dumps(document, sort_keys=True).encode())
    path.chmod(0o600)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def synthetic_chain(tmp_path, worker_count=2, profile=None):
    profile_path = tmp_path / "sealed/profile.json"
    profile_sha = write_private(profile_path, profile or profile_document(worker_count))
    promotion_path = tmp_path / "authority/promotion.json"
    promotion_sha = write_private(promotion_path, {
        "schema_version": 2, "kind": "PROMOTION", "profile_sha256": profile_sha,
        "operator_approval_uid": 1000, "exact_worker_count": worker_count,
        "reviews": [
            {"reviewer": "sol", "result": "PASS", "sha256": "1" * 64},
            {"reviewer": "astra", "result": "PASS", "sha256": "2" * 64},
        ],
        "sol_result_review_sha256": "1" * 64,
        "astra_profile_review_sha256": "2" * 64,
        "operator_approval_sha256": "3" * 64})
    receipt_path = tmp_path / "deployments/receipt.json"
    write_private(receipt_path, {"schema_version": 2, "kind": "DEPLOYMENT_RECEIPT",
                                 "profile_sha256": profile_sha,
                                 "promotion_sha256": promotion_sha})
    return profile_path, profile_sha, promotion_path, receipt_path


def scope(worker_count=2, kind="FIXED_PRODUCTION"):
    from so101_demo.parallel_batch.resource_budget import AllocationScope
    return AllocationScope("batch-a", 1, worker_count, kind, IDENTITY)


def current_identity():
    from so101_demo.parallel_batch.resource_identity import RuntimeFingerprint
    return RuntimeFingerprint(2, {"gpu_uuid": "GPU-1"}, "d" * 64, SHA, "e" * 64, "f" * 64)


IDENTITY = current_identity().sha256


@pytest.mark.parametrize("capacity,observed,remaining,error,expected", [
    (1000, 200, 600, 0, True), (1000, 200, 601, 0, False),
    (4, .4, 2.8, 0, True), (4, .4, 2.9, 0, False),
    (1000, 600, 150, 50, True), (1000, 810, 0, 0, False)])
def test_exact_twenty_percent(capacity, observed, remaining, error, expected):
    from so101_demo.parallel_batch.resource_budget import headroom_ok
    assert headroom_ok(capacity, observed, remaining, error) is expected


@pytest.mark.parametrize("capacity,observed,remaining,error,expected", [
    (1000, 200, 600, 0, True), (1000, 200, 601, 0, False),
    (4, .4, 2.8, 0, True), (4, .4, 2.9, 0, False),
    (1000, 600, 150, 50, True), (1000, 810, 0, 0, False),
    (1000, 800, 0, 1, False), (1000, 200, 600, float("nan"), False),
    (0, 0, 0, 0, False), (1000, -1, 0, 0, False), (1000, 200, float("inf"), 0, False)])
def test_headroom_table(capacity, observed, remaining, error, expected):
    from so101_demo.parallel_batch.resource_budget import headroom_ok
    assert headroom_ok(capacity, observed, remaining, error) is expected


def test_live_observation_requires_declared_units_and_finite_values():
    from so101_demo.parallel_batch.contracts import ContractError
    from so101_demo.parallel_batch.resource_budget import LiveResourceObservation
    good = observation(length=1)
    assert set(good.capacity) == set(DIMENSIONS)
    with pytest.raises(ContractError):
        LiveResourceObservation(
            monotonic_s=1.0, capacity={"ram_bytes": 1.0}, observed=dimension(1.0),
            background=dimension(0.0), tool_overhead=dimension(0.0),
            remaining=dimension(0.0), error=dimension(0.0), attribution_complete=True,
            swap_delta=0, psi_full_delta=0.0, throttled=False)
    with pytest.raises(ContractError):
        LiveResourceObservation(
            monotonic_s=float("nan"), capacity=dimension(1.0), observed=dimension(0.0),
            background=dimension(0.0), tool_overhead=dimension(0.0),
            remaining=dimension(0.0), error=dimension(0.0), attribution_complete=True,
            swap_delta=0, psi_full_delta=0.0, throttled=False)


def test_contexts_cannot_be_forged_or_mixed():
    from so101_demo.parallel_batch.contracts import ContractError
    from so101_demo.parallel_batch.resource_budget import (
        AdaptiveAllocationContext, FixedProductionContext, MeasurementContext)
    with pytest.raises(ContractError) as error:
        FixedProductionContext(scope=scope(), authority_sha256=SHA, profile_sha256=SHA,
                               qualification_sha256=SHA, control_binding_sha256=SHA)
    assert error.value.code == "ALLOCATION_CONTEXT_MISMATCH"
    with pytest.raises(ContractError):
        MeasurementContext(scope=scope(kind="MEASUREMENT"), authority_sha256=SHA,
                           authorization_sha256=SHA, owned_scope_sha256=SHA)
    with pytest.raises(ContractError):
        AdaptiveAllocationContext(scope=scope(kind="ADAPTIVE"), authority_sha256=SHA,
                                  pool_token_sha256=SHA, pool_generation=1)


def test_candidate_profile_cannot_issue_production_context(tmp_path):
    from so101_demo.parallel_batch.contracts import ContractError
    from so101_demo.parallel_batch.resource_budget import (
        ResourceBudgetProvider, issue_production_context)
    provider = ResourceBudgetProvider()
    with pytest.raises(ContractError) as error:
        issue_production_context(provider=provider, scope=scope(), profile_path=None,
                                 expected_profile_sha256=None, promotion_path=None,
                                 deployment_receipt_path=None, control_binding={"lease_id": "l"})
    assert error.value.code == "BUDGET_PROFILE_UNAVAILABLE"


def test_production_admission_requires_approved_exact_n_and_live_headroom(tmp_path):
    from so101_demo.parallel_batch.contracts import ContractError
    from so101_demo.parallel_batch.resource_budget import (
        ResourceBudgetProvider, ExactNQualification, issue_production_context)
    provider = ResourceBudgetProvider()
    profile_path, profile_sha, promotion_path, receipt_path = synthetic_chain(tmp_path, 2)
    provider.load(profile_path, expected_sha256=profile_sha)
    provider.record_qualification(ExactNQualification.from_document(
        qualification_document(2), raw_sha256=IDENTITY))
    context = issue_production_context(
        provider=provider, scope=scope(2), profile_path=profile_path,
        expected_profile_sha256=profile_sha, promotion_path=promotion_path,
        deployment_receipt_path=receipt_path, control_binding={"lease_id": "lease-a"})
    healthy = provider.admit_production(context=context, current=current_identity(),
                                        live=observation(length=1), now_monotonic_s=1.1)
    assert healthy.admitted is True, healthy.reason_codes
    assert healthy.worker_count == 2
    tight = provider.admit_production(context=context, current=current_identity(),
                                      live=observation(length=1, remaining=dimension(750.0)),
                                      now_monotonic_s=1.1)
    assert tight.admitted is False
    assert "RAM_HEADROOM" in tight.reason_codes
    unattributed = provider.admit_production(
        context=context, current=current_identity(),
        live=observation(length=1, attribution_complete=False), now_monotonic_s=1.1)
    assert unattributed.admitted is False
    assert "BACKGROUND_ENVELOPE_EXCEEDED" in unattributed.reason_codes
    swapped = provider.admit_production(
        context=context, current=current_identity(),
        live=observation(length=1, swap_delta=4096), now_monotonic_s=1.1)
    assert swapped.admitted is False and "SWAP_PRESSURE" in swapped.reason_codes
    stale = provider.admit_production(context=context, current=current_identity(),
                                      live=observation(length=1), now_monotonic_s=99.0)
    assert stale.admitted is False and "RESOURCE_PROBE_FAILED" in stale.reason_codes
    drifted = provider.admit_production(
        context=context, current=current_identity(),
        live=observation(length=1, throttled=True), now_monotonic_s=1.1)
    assert drifted.admitted is False and "CPU_HEADROOM" in drifted.reason_codes
    with pytest.raises(ContractError) as error:
        provider.admit_production(context=context,
                                  current=type(current_identity())(2, {"gpu": "GPU-2"},
                                                                   "d" * 64, SHA, "e" * 64, "f" * 64),
                                  live=observation(length=1), now_monotonic_s=1.1)
    assert error.value.code == "RUNTIME_FINGERPRINT_MISMATCH"


def test_missing_exact_n_entry_and_n8_substitution_are_rejected(tmp_path):
    from so101_demo.parallel_batch.contracts import ContractError
    from so101_demo.parallel_batch.resource_budget import (
        ResourceBudgetProvider, ExactNQualification, issue_production_context)
    provider = ResourceBudgetProvider()
    profile_path, profile_sha, promotion_path, receipt_path = synthetic_chain(tmp_path, 4)
    provider.load(profile_path, expected_sha256=profile_sha)
    provider.record_qualification(ExactNQualification.from_document(
        qualification_document(4), raw_sha256=IDENTITY))
    with pytest.raises(ContractError) as error:
        issue_production_context(
            provider=provider, scope=scope(8), profile_path=profile_path,
            expected_profile_sha256=profile_sha, promotion_path=promotion_path,
            deployment_receipt_path=receipt_path, control_binding={"lease_id": "lease-a"})
    assert error.value.code == "EXACT_N_UNQUALIFIED"
    unknown = profile_document(4)
    unknown["entries"]["8"] = {
        "worker_count": 8, "status": "UNKNOWN", "qualification_sha256": None,
        "raw_manifest_sha256s": [], "coverage": {}, "stages": {}, "review_reference": None}
    profile_path2 = tmp_path / "unknown/sealed-profile.json"
    profile_sha2 = write_private(profile_path2, unknown)
    provider2 = ResourceBudgetProvider()
    provider2.load(profile_path2, expected_sha256=profile_sha2)
    provider2.record_qualification(ExactNQualification.from_document(
        qualification_document(4), raw_sha256=IDENTITY))
    with pytest.raises(ContractError) as error:
        issue_production_context(
            provider=provider2, scope=scope(8), profile_path=profile_path2,
            expected_profile_sha256=profile_sha2, promotion_path=promotion_path,
            deployment_receipt_path=receipt_path, control_binding={"lease_id": "lease-a"})
    assert error.value.code == "EXACT_N_UNQUALIFIED"


def test_measurement_context_needs_authorization_but_no_profile(tmp_path):
    from so101_demo.parallel_batch.resource_budget import (
        ResourceBudgetProvider, issue_measurement_context)
    provider = ResourceBudgetProvider()
    authorization = tmp_path / "private/authorization.json"
    authorization_sha = write_private(authorization, {"schema_version": 2, "worker_count": 2,
                                                      "intent": "CALIBRATION_ONLY"})
    owner = {"authorization_sha256": authorization_sha, "owned_scope_sha256": "9" * 64}
    context = issue_measurement_context(provider=provider, scope=scope(2, "MEASUREMENT"),
                                        authorization_path=authorization, owner_binding=owner)
    admission = provider.admit_measurement(context=context, current=current_identity(),
                                           live=observation(length=1), now_monotonic_s=1.1)
    assert admission.admitted is True, admission.reason_codes
    assert admission.profile_sha256 is None
    with pytest.raises(Exception) as error:
        provider.admit_production(context=context, current=current_identity(),
                                  live=observation(length=1), now_monotonic_s=1.1)
    assert "ALLOCATION_CONTEXT_MISMATCH" in str(error.value)


def test_qualification_provider_rejects_schema1_n_and_identity_mismatch():
    from so101_demo.parallel_batch.resource_budget import (
        ExactNQualification, ExactNQualificationProvider)
    provider = ExactNQualificationProvider()
    record = ExactNQualification.from_document(
        qualification_document(2, identity=SHA), raw_sha256=SHA)
    good = provider.verify(record=record, worker_count=2,
                           execution_identity_sha256=SHA, coverage_policy_sha256="b" * 64)
    assert good.qualified is True
    wrong_n = provider.verify(record=record, worker_count=4,
                              execution_identity_sha256=SHA, coverage_policy_sha256="b" * 64)
    assert wrong_n.qualified is False and "EXACT_N_UNQUALIFIED" in wrong_n.reason_codes
    wrong_identity = provider.verify(record=record, worker_count=2,
                                     execution_identity_sha256="f" * 64,
                                     coverage_policy_sha256="b" * 64)
    assert wrong_identity.qualified is False
    assert "RUNTIME_FINGERPRINT_MISMATCH" in wrong_identity.reason_codes
    with pytest.raises(Exception):
        ExactNQualification.from_document(qualification_document(2, schema_version=1),
                                          raw_sha256=SHA)
    with pytest.raises(Exception):
        ExactNQualification.from_document(qualification_document(2, profile_sha256=SHA),
                                          raw_sha256=SHA)


def test_qualification_record_cannot_reference_profile_or_receipts(tmp_path):
    from so101_demo.parallel_batch.contracts import ContractError
    from so101_demo.parallel_batch.resource_budget import ExactNQualification
    for forbidden in ("profile_sha256", "promotion_record_path", "deployment_receipt_sha256"):
        document = qualification_document(2)
        document[forbidden] = SHA
        with pytest.raises(ContractError):
            ExactNQualification.from_document(document, raw_sha256=SHA)


def test_profile_rejects_unknown_status_and_zero_filled_unknown_entry(tmp_path):
    from so101_demo.parallel_batch.contracts import ContractError
    from so101_demo.parallel_batch.resource_budget import ApprovedBudgetProfile
    good = ApprovedBudgetProfile.from_document(profile_document(2), raw_sha256=SHA)
    assert good.entry(2).status == "APPROVED"
    with pytest.raises(ContractError):
        ApprovedBudgetProfile.from_document(profile_document(2, status="MAYBE"), raw_sha256=SHA)
    with pytest.raises(ContractError):
        ApprovedBudgetProfile.from_document(
            profile_document(2, status="UNKNOWN", stages={}), raw_sha256=SHA)
    with pytest.raises(ContractError):
        ApprovedBudgetProfile.from_document(profile_document(2, mystery=1), raw_sha256=SHA)
    assert ApprovedBudgetProfile.from_document(profile_document(2), raw_sha256=SHA).entry(8) is None
