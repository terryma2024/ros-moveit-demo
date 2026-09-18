"""Independent promotion: candidate output can never approve itself."""

import json
from pathlib import Path

import pytest

SHA = "a" * 64


def _write(path: Path, document) -> str:
    import hashlib
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(document, sort_keys=True))
    path.chmod(0o600)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stage():
    def dims(value):
        return {"ram_bytes": value, "gpu_bytes": value, "cpu_core_equivalent": value}
    return {
        "demand": dims(1.0), "uncertainty": dims(0.1), "background": dims(1.0),
        "tool_overhead": dims(0.1), "available_headroom": dims(1.0),
    }


@pytest.fixture
def candidate_profile(tmp_path):
    from so101_demo.parallel_batch.resource_budget import ApprovedBudgetProfile
    document = {
        "schema_version": 2, "execution_identity_sha256": SHA,
        "coverage_policy_sha256": "b" * 64,
        "entries": {
            "2": {
                "worker_count": 2, "status": "CANDIDATE", "qualification_sha256": "c" * 64,
                "raw_manifest_sha256s": ["d" * 64],
                "coverage": {"COLD_START": ["observed"]},
                "stages": {name: _stage() for name in
                           ("startup", "steady", "recovery", "finalization")},
                "review_reference": None,
            }
        },
    }
    return ApprovedBudgetProfile.from_document(document, raw_sha256="e" * 64)


@pytest.fixture
def authority(tmp_path):
    from so101_demo.parallel_batch.resource_budget import PromotionAuthority
    root = tmp_path / "trusted-authority"
    root.mkdir(mode=0o700, parents=True)
    return PromotionAuthority(root)


def audit_document(prefix, *, commit="1" * 40):
    """One complete A0 FullByteAudit for the fixture authority."""

    from so101_demo.parallel_batch.resource_identity import FullByteAudit, InventoryEntry
    return FullByteAudit(
        schema_version=2, source_commit=commit, source_clean=True, prefix=str(prefix),
        files=(InventoryEntry("site-packages/so101_demo/__init__.py", "2" * 64),),
        origins={"so101_demo_py": str(prefix)})


def authority_documents(root: Path, profile_sha256: str, audit, *, worker_count=2,
                        sol_target="EXECUTION_RESULT", astra_target="PROFILE",
                        reviewer="astra"):
    """Operator approval plus both independent reviews, bound to P and A0."""

    approval = root / "operator-approval.json"
    _write(approval, {
        "schema_version": 2, "kind": "OPERATOR_APPROVAL", "operator_uid": 1000,
        "decision": "APPROVED", "target": "EXACT_N_PRODUCTION",
        "exact_worker_count": worker_count, "profile_sha256": profile_sha256,
        "measurement_audit_sha256": audit.sha256})
    sol = root / "sol-result-review.json"
    _write(sol, {
        "schema_version": 2, "kind": "INDEPENDENT_REVIEW", "reviewer": "sol",
        "result": "PASS", "target": sol_target, "profile_sha256": profile_sha256,
        "measurement_audit_sha256": audit.sha256})
    astra = root / "astra-profile-review.json"
    _write(astra, {
        "schema_version": 2, "kind": "INDEPENDENT_REVIEW", "reviewer": reviewer,
        "result": "PASS", "target": astra_target, "profile_sha256": profile_sha256,
        "measurement_audit_sha256": audit.sha256})
    return approval, sol, astra


def test_candidate_review_is_not_operator_promotion(tmp_path, candidate_profile, authority):
    from so101_demo.parallel_batch.contracts import ContractError
    from so101_demo.parallel_batch.resource_budget import verify_promotion
    with pytest.raises(ContractError) as error:
        verify_promotion(profile=candidate_profile, promotion_path=None,
                         authority=authority)
    assert error.value.code == "BUDGET_PROFILE_UNAVAILABLE"


def test_promotion_binds_profile_audit_reviews_and_operator(tmp_path, candidate_profile, authority):
    from so101_demo.parallel_batch.resource_budget import (
        publish_promotion, verify_promotion)
    trusted = authority
    audit = audit_document(tmp_path / "candidate-install")
    approval, sol, astra = authority_documents(
        trusted.root, candidate_profile.raw_sha256, audit)
    promotion = publish_promotion(
        profile_path=tmp_path / "candidate/profile.json",
        profile_sha256=candidate_profile.raw_sha256,
        operator_approval=approval, sol_result_review=sol, astra_profile_review=astra,
        measurement_audit=audit, destination=trusted.root / "promotion.json",
        authority=trusted)
    document = json.loads(Path(promotion).read_bytes())
    assert document["profile_sha256"] == candidate_profile.raw_sha256
    assert document["operator_approval_uid"] == 1000
    assert document["measurement_audit_sha256"] == audit.sha256
    assert document["documents"]["astra_profile_review"] == astra.name
    for forbidden in ("deployment_receipt", "deployment_receipt_sha256", "installed_audit",
                      "deployment_receipt_path"):
        assert forbidden not in document
    verify_promotion(profile=candidate_profile, promotion_path=Path(promotion),
                     authority=trusted)
    other_root = tmp_path / "other-authority"
    other_root.mkdir(mode=0o700)
    from so101_demo.parallel_batch.resource_budget import PromotionAuthority
    with pytest.raises(Exception):
        verify_promotion(profile=candidate_profile, promotion_path=Path(promotion),
                         authority=PromotionAuthority(other_root))


def test_promotion_refuses_a_candidate_tree_approval(tmp_path, candidate_profile):
    from so101_demo.parallel_batch.contracts import ContractError
    from so101_demo.parallel_batch.resource_budget import (
        PromotionAuthority, publish_promotion)
    candidate_root = tmp_path / "candidate"
    candidate_root.mkdir(mode=0o700, parents=True)
    audit = audit_document(tmp_path / "candidate-install")
    approval = candidate_root / "operator-approval.json"
    _write(approval, {"schema_version": 2, "operator_uid": 1000, "decision": "APPROVED"})
    trusted_root = tmp_path / "trusted-authority"
    trusted_root.mkdir(mode=0o700, exist_ok=True)
    trusted = PromotionAuthority(trusted_root)
    with pytest.raises(ContractError) as error:
        publish_promotion(
            profile_path=candidate_root / "profile.json",
            profile_sha256=candidate_profile.raw_sha256,
            operator_approval=approval,
            sol_result_review=approval, astra_profile_review=approval,
            measurement_audit=audit, destination=trusted.root / "promotion.json",
            authority=trusted)
    assert error.value.code == "PROMOTION_AUTHORITY_INVALID"


def test_deployment_receipt_binds_promotion_profile_and_location(tmp_path, candidate_profile):
    from so101_demo.parallel_batch.resource_budget import build_deployment_receipt
    from so101_demo.parallel_batch.resource_identity import FullByteAudit, InventoryEntry
    audit = FullByteAudit(
        schema_version=2, source_commit="1" * 40, source_clean=True,
        prefix="/tmp/uq-install", files=(InventoryEntry("a.py", "2" * 64),),
        origins={"so101_demo_py": "/tmp/uq-install"})
    promotion_path = tmp_path / "trusted-authority/promotion.json"
    _write(promotion_path, {"schema_version": 1, "kind": "PROMOTION",
                            "profile_sha256": candidate_profile.raw_sha256})
    receipt = build_deployment_receipt(
        promotion_path=promotion_path,
        profile_sha256=candidate_profile.raw_sha256, installed_audit=audit,
        execution_identity_sha256=SHA,
        location_binding={"prefix": "/tmp/uq-install"})
    document = json.loads(Path(receipt).read_bytes())
    assert document["profile_sha256"] == candidate_profile.raw_sha256
    assert document["installed_audit_sha256"] == audit.sha256
    assert document["location_binding"]["prefix"] == "/tmp/uq-install"


def _approved_profile(tmp_path):
    """A schema2 profile whose exact N4 entry is APPROVED with a visible qualification."""

    from so101_demo.parallel_batch.resource_budget import ApprovedBudgetProfile
    qualification = {
        "schema_version": 2, "execution_identity_sha256": SHA, "worker_count": 4,
        "coverage_policy_sha256": "b" * 64, "sealed_manifest_sha256s": ["d" * 64],
        "normal_valid_runs": 5, "normal_required_runs": 5, "coverage_complete": True,
        "cleanup_verified": True, "independent_physics_verified": True,
        "resource_contract_verified": True,
    }
    qualification_path = tmp_path / "trusted-authority/qualification.json"
    qualification_sha = _write(qualification_path, qualification)
    cells = ("COLD_START", "STEADY_YOLO", "STEADY_GROUNDED_SAM", "STEADY_MIXED",
             "MOTION_RELEASE", "BROKER_RELOAD_WITH_N_RESIDENT",
             "WORKER_RECOVERY_WITH_N_RESIDENT", "FINALIZATION_CLEANUP")
    document = {
        "schema_version": 2, "execution_identity_sha256": SHA,
        "coverage_policy_sha256": "b" * 64,
        "entries": {"4": {
            "worker_count": 4, "status": "APPROVED",
            "qualification_sha256": qualification_sha, "raw_manifest_sha256s": ["d" * 64],
            "coverage": {cell: ["observed"] for cell in cells},
            "stages": {name: _stage() for name in
                       ("startup", "steady", "recovery", "finalization")},
            "review_reference": "astra:round-trip",
        }},
    }
    profile_path = tmp_path / "sealed/profile.json"
    profile_sha = _write(profile_path, document)
    profile = ApprovedBudgetProfile.from_document(document, raw_sha256=profile_sha)
    return profile, profile_path, profile_sha, qualification_path, qualification_sha


def test_actual_producer_outputs_round_trip_into_the_context_issuer(tmp_path):
    """publish_promotion/build_deployment_receipt output must feed issue_production_context."""

    from so101_demo.parallel_batch.resource_budget import (
        AllocationScope, ExactNQualification, PromotionAuthority, ResourceBudgetProvider,
        build_deployment_receipt, issue_production_context, publish_promotion,
        verify_promotion)

    profile, profile_path, profile_sha, qualification_path, qualification_sha = _approved_profile(tmp_path)
    trusted_root = tmp_path / "trusted-authority"
    trusted_root.mkdir(mode=0o700, exist_ok=True)
    authority = PromotionAuthority(trusted_root)
    audit = audit_document(tmp_path / "install")
    approval, sol, astra = authority_documents(
        trusted_root, profile_sha, audit, worker_count=4)
    promotion_path = publish_promotion(
        profile_path=profile_path, profile_sha256=profile_sha,
        operator_approval=approval, sol_result_review=sol, astra_profile_review=astra,
        measurement_audit=audit, destination=trusted_root / "promotion.json",
        authority=authority)
    location = {"prefix": str(tmp_path / "install"), "host": "fixture-host"}
    receipt_path = build_deployment_receipt(
        promotion_path=promotion_path, profile_sha256=profile_sha, installed_audit=audit,
        execution_identity_sha256=SHA, location_binding=location)

    verify_promotion(profile=profile, promotion_path=promotion_path, authority=authority,
                     execution_identity_sha256=SHA, exact_worker_count=4)

    provider = ResourceBudgetProvider()
    provider.load(profile_path, expected_sha256=profile_sha)
    provider.record_qualification(ExactNQualification.from_document(
        json.loads(qualification_path.read_bytes()), raw_sha256=qualification_sha))
    scope = AllocationScope("batch-a", 1, 4, "FIXED_PRODUCTION", SHA)
    context = issue_production_context(
        provider=provider, scope=scope, profile_path=profile_path,
        expected_profile_sha256=profile_sha, promotion_path=promotion_path,
        deployment_receipt_path=receipt_path, control_binding=dict(location),
        authority=authority, installed_audit=audit, current_identity_sha256=SHA,
        location_binding=dict(location))
    assert context.profile_sha256 == profile_sha
    assert context.qualification_sha256 == qualification_sha
    assert context.scope.worker_count == 4

    # Deleting, changing or substituting any single authority field is refused.
    from so101_demo.parallel_batch.contracts import ContractError

    foreign_audit = audit_document(tmp_path / "foreign-install", commit="3" * 40)
    with pytest.raises(ContractError) as error:
        issue_production_context(
            provider=provider, scope=scope, profile_path=profile_path,
            expected_profile_sha256=profile_sha, promotion_path=promotion_path,
            deployment_receipt_path=receipt_path, control_binding=dict(location),
            authority=authority, installed_audit=foreign_audit,
            current_identity_sha256=SHA, location_binding=dict(location))
    assert error.value.code == "DEPLOYMENT_RECEIPT_AUDIT_MISMATCH"

    receipt_document = json.loads(Path(receipt_path).read_bytes())
    receipt_document.pop("location_binding")
    deleted_receipt = trusted_root / "deleted-receipt.json"
    _write(deleted_receipt, receipt_document)
    with pytest.raises(ContractError) as error:
        issue_production_context(
            provider=provider, scope=scope, profile_path=profile_path,
            expected_profile_sha256=profile_sha, promotion_path=promotion_path,
            deployment_receipt_path=deleted_receipt, control_binding=dict(location),
            authority=authority, installed_audit=audit, current_identity_sha256=SHA,
            location_binding=dict(location))
    assert "DEPLOYMENT_RECEIPT_MISSING_FIELD" in error.value.code

    with pytest.raises(ContractError) as error:
        issue_production_context(
            provider=provider, scope=scope, profile_path=profile_path,
            expected_profile_sha256=profile_sha, promotion_path=promotion_path,
            deployment_receipt_path=receipt_path, control_binding=dict(location),
            authority=authority, installed_audit=audit, current_identity_sha256="9" * 64,
            location_binding=dict(location))
    assert error.value.code == "DEPLOYMENT_RECEIPT_IDENTITY_MISMATCH"

    with pytest.raises(ContractError) as error:
        issue_production_context(
            provider=provider, scope=scope, profile_path=profile_path,
            expected_profile_sha256=profile_sha, promotion_path=promotion_path,
            deployment_receipt_path=receipt_path, control_binding=dict(location),
            authority=authority, installed_audit=audit, current_identity_sha256=SHA,
            location_binding={"prefix": "/elsewhere"})
    assert error.value.code == "DEPLOYMENT_RECEIPT_LOCATION_MISMATCH"

    # An independent review whose target does not match its role is not a promotion.
    wrong_target = authority_documents(
        trusted_root, profile_sha, audit, worker_count=4,
        astra_target="EXECUTION_RESULT", reviewer="astra")[2]
    wrong_path = trusted_root / "wrong-target-review.json"
    _write(wrong_path, json.loads(Path(wrong_target).read_bytes()))
    with pytest.raises(ContractError) as error:
        publish_promotion(
            profile_path=profile_path, profile_sha256=profile_sha,
            operator_approval=approval, sol_result_review=sol,
            astra_profile_review=wrong_path,
            measurement_audit=audit, destination=trusted_root / "wrong-promotion.json",
            authority=authority)
    assert error.value.code == "INDEPENDENT_REVIEW_TARGET"


def test_round_trip_refuses_altered_reviews_profile_n_and_location(tmp_path):
    from so101_demo.parallel_batch.contracts import ContractError
    from so101_demo.parallel_batch.resource_budget import (
        AllocationScope, ExactNQualification, PromotionAuthority, ResourceBudgetProvider,
        build_deployment_receipt, issue_production_context, publish_promotion)

    profile, profile_path, profile_sha, qualification_path, qualification_sha = _approved_profile(tmp_path)
    trusted_root = tmp_path / "trusted-authority"
    trusted_root.mkdir(mode=0o700, exist_ok=True)
    authority = PromotionAuthority(trusted_root)
    audit = audit_document(tmp_path / "install")
    approval, sol, astra = authority_documents(
        trusted_root, profile_sha, audit, worker_count=4)

    # An independent review that did not pass can never produce a promotion.
    failing_astra = trusted_root / "astra-failing.json"
    _write(failing_astra, {
        "schema_version": 2, "kind": "INDEPENDENT_REVIEW", "reviewer": "astra",
        "result": "CHANGES_REQUIRED", "target": "PROFILE", "profile_sha256": profile_sha,
        "measurement_audit_sha256": audit.sha256})
    with pytest.raises(ContractError) as error:
        publish_promotion(
            profile_path=profile_path, profile_sha256=profile_sha,
            operator_approval=approval, sol_result_review=sol,
            astra_profile_review=failing_astra, measurement_audit=audit,
            destination=trusted_root / "rejected-promotion.json", authority=authority)
    assert "INDEPENDENT_REVIEW_REQUIRED" in str(error.value)

    promotion_path = publish_promotion(
        profile_path=profile_path, profile_sha256=profile_sha,
        operator_approval=approval, sol_result_review=sol, astra_profile_review=astra,
        measurement_audit=audit, destination=trusted_root / "promotion.json",
        authority=authority)

    def provider_for():
        provider = ResourceBudgetProvider()
        provider.load(profile_path, expected_sha256=profile_sha)
        provider.record_qualification(ExactNQualification.from_document(
            json.loads(qualification_path.read_bytes()), raw_sha256=qualification_sha))
        return provider

    scope = AllocationScope("batch-a", 1, 4, "FIXED_PRODUCTION", SHA)
    location = {"prefix": str(tmp_path / "install"), "host": "fixture-host"}

    # Altered promotion: a different profile hash inside the record.
    altered = json.loads(Path(promotion_path).read_bytes())
    altered["profile_sha256"] = "9" * 64
    altered_path = trusted_root / "altered-promotion.json"
    _write(altered_path, altered)
    with pytest.raises(ContractError) as error:
        issue_production_context(
            provider=provider_for(), scope=scope, profile_path=profile_path,
            expected_profile_sha256=profile_sha, promotion_path=altered_path,
            deployment_receipt_path=trusted_root / "missing.json",
            control_binding=dict(location), authority=authority, installed_audit=audit,
            current_identity_sha256=SHA, location_binding=dict(location))
    assert "PROMOTION_PROFILE_MISMATCH" in str(error.value)

    # A promotion without the independent review documents is invalid.
    without_reviews = dict(altered)
    without_reviews["profile_sha256"] = profile_sha
    without_reviews.pop("documents", None)
    no_review_path = trusted_root / "no-reviews.json"
    _write(no_review_path, without_reviews)
    with pytest.raises(ContractError) as error:
        issue_production_context(
            provider=provider_for(), scope=scope, profile_path=profile_path,
            expected_profile_sha256=profile_sha, promotion_path=no_review_path,
            deployment_receipt_path=trusted_root / "missing.json",
            control_binding=dict(location), authority=authority, installed_audit=audit,
            current_identity_sha256=SHA, location_binding=dict(location))
    assert "PROMOTION_MISSING_FIELD" in str(error.value)

    # The same command cannot be replayed for a different exact N.
    other_scope = AllocationScope("batch-a", 1, 2, "FIXED_PRODUCTION", SHA)
    with pytest.raises(ContractError) as error:
        issue_production_context(
            provider=provider_for(), scope=other_scope, profile_path=profile_path,
            expected_profile_sha256=profile_sha, promotion_path=promotion_path,
            deployment_receipt_path=trusted_root / "missing.json",
            control_binding=dict(location), authority=authority, installed_audit=audit,
            current_identity_sha256=SHA, location_binding=dict(location))
    assert "EXACT_N_UNQUALIFIED" in str(error.value)

    # A tampered deployment receipt (wrong promotion hash) is refused.
    receipt_path = build_deployment_receipt(
        promotion_path=promotion_path, profile_sha256=profile_sha, installed_audit=audit,
        execution_identity_sha256=SHA, location_binding=location)
    tampered = json.loads(Path(receipt_path).read_bytes())
    tampered["promotion_sha256"] = "8" * 64
    tampered_path = trusted_root / "tampered-receipt.json"
    _write(tampered_path, tampered)
    with pytest.raises(ContractError) as error:
        issue_production_context(
            provider=provider_for(), scope=scope, profile_path=profile_path,
            expected_profile_sha256=profile_sha, promotion_path=promotion_path,
            deployment_receipt_path=tampered_path, control_binding=dict(location),
            authority=authority, installed_audit=audit, current_identity_sha256=SHA,
            location_binding=dict(location))
    assert "DEPLOYMENT_RECEIPT_PROMOTION_MISMATCH" in str(error.value)
