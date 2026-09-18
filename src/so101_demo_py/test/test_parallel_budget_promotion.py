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
    approval = tmp_path / "trusted-authority/operator-approval.json"
    _write(approval, {"schema_version": 1, "operator_uid": 1000, "decision": "APPROVED",
                      "exact_worker_count": 2, "profile_sha256": candidate_profile.raw_sha256})
    sol = tmp_path / "trusted-authority/sol-review.json"
    _write(sol, {"schema_version": 1, "reviewer": "sol", "result": "PASS"})
    astra = tmp_path / "trusted-authority/astra-review.json"
    _write(astra, {"schema_version": 1, "reviewer": "astra", "result": "PASS"})
    promotion = publish_promotion(
        profile_path=tmp_path / "candidate/profile.json",
        profile_sha256=candidate_profile.raw_sha256,
        operator_approval=approval, sol_result_review=sol, astra_profile_review=astra,
        measurement_audit={"kind": "A0", "sha256": "f" * 64},
        destination=trusted.root / "promotion.json")
    document = json.loads(Path(promotion).read_bytes())
    assert document["profile_sha256"] == candidate_profile.raw_sha256
    assert document["operator_approval_uid"] == 1000
    assert document["measurement_audit"]["sha256"] == "f" * 64
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
    approval = candidate_root / "operator-approval.json"
    _write(approval, {"schema_version": 1, "operator_uid": 1000, "decision": "APPROVED",
                      "exact_worker_count": 2, "profile_sha256": candidate_profile.raw_sha256})
    trusted = tmp_path / "trusted-authority"
    trusted.mkdir(mode=0o700)
    with pytest.raises(ContractError) as error:
        publish_promotion(
            profile_path=candidate_root / "profile.json",
            profile_sha256=candidate_profile.raw_sha256,
            operator_approval=approval,
            sol_result_review=approval, astra_profile_review=approval,
            measurement_audit={"kind": "A0", "sha256": "f" * 64},
            destination=trusted / "promotion.json")
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
