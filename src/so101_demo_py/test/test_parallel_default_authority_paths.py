"""R3/R4: the default observation/identity paths and the closed M/D authority chain.

Every assertion here targets the *default* composition an installed consumer reaches:
no admission factory substitution, no global gate seam, no synthetic observation. The
only replaceable inputs are typed low-level host ports and task-owned fixture files.
"""

import json
import os
from pathlib import Path

import pytest

from so101_demo.parallel_batch.contracts import ContractError
from so101_demo.parallel_batch.resource_budget import (
    AllocationScope, ExactNQualification, FixedAdmissionRequest, HostFacts,
    LiveObservationSource, PromotionAuthority, ResourceBudgetProvider,
    build_deployment_receipt, build_live_observation, build_runtime_fingerprint_from_environment,
    compose_production_admission, issue_production_context, publish_promotion,
    verify_promotion)
from so101_demo.parallel_batch.resource_identity import FullByteAudit, InventoryEntry

DIMENSIONS = ("ram_bytes", "gpu_bytes", "cpu_core_equivalent")
COVERAGE_CELLS = (
    "COLD_START", "STEADY_YOLO", "STEADY_GROUNDED_SAM", "STEADY_MIXED", "MOTION_RELEASE",
    "BROKER_RELOAD_WITH_N_RESIDENT", "WORKER_RECOVERY_WITH_N_RESIDENT",
    "FINALIZATION_CLEANUP")
WORKTREE = Path(__file__).resolve().parents[3]
V2_CONFIG = WORKTREE / "src/so101_demo_py/config/mujoco/parallel_batch_v2.yaml"


def _dimensions(value):
    return {name: value for name in DIMENSIONS}


def _write(path: Path, document) -> str:
    import hashlib
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(document, sort_keys=True))
    path.chmod(0o600)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _host_facts(*, total=1000.0, used=170.0, cpu_capacity=8.0, own_rss=10.0,
                attributed=True, **overrides):
    """Typed low-level host port payload; one fixture covers both memory and GPU."""

    values = {
        "mem_total_bytes": int(total), "mem_available_bytes": int(total - used),
        "cpu_capacity": cpu_capacity, "cpu_host_cores": int(cpu_capacity) * 3,
        "cpu_set_used_core_equivalent": 0.1, "cpu_host_used_core_equivalent": 0.1,
        "cpu_quota_core_equivalent": cpu_capacity, "cpuset": "0-7", "nr_throttled": 0,
        "gpu_index": 0, "gpu_name": "fixture-gpu", "gpu_uuid": "GPU-fixture",
        "gpu_total_bytes": total, "gpu_used_bytes": used * 0.9, "gpu_consumers": (11,),
        "same_uid_pids": (11, 12), "own_tree_rss_bytes": int(own_rss),
        "own_tree_gpu_bytes": 0.0, "attributed": attributed,
        "facts": {"gpu_uuid": "GPU-fixture", "cpu_model": "fixture", "kernel": "fixture",
                  "python": "3.12.3", "container_marker": "none", "install_kind": ""},
    }
    values.update(overrides)
    return HostFacts(**values)


# --- R3: the default observation and identity are derived, never placeholder ---------


def test_default_live_observation_is_attributed_and_effective():
    """The installed default probe must not zero-fill or hardcode attribution."""

    observation = build_live_observation()
    assert observation.attribution_complete is True
    for name, value in observation.capacity.items():
        assert value > 0, name
    assert observation.observed["ram_bytes"] > 0
    assert observation.background["ram_bytes"] > 0
    assert observation.tool_overhead["ram_bytes"] > 0
    from so101_demo.parallel_batch.resource_budget import probe_host_facts

    facts = probe_host_facts()
    affinity = len(os.sched_getaffinity(0)) or (os.cpu_count() or 0)
    assert facts.cpu_capacity <= affinity + 1e-9
    assert facts.cpu_capacity <= facts.cpu_host_cores + 1e-9
    assert observation.capacity["cpu_core_equivalent"] == pytest.approx(facts.cpu_capacity)
    assert facts.gpu_total_bytes > 0


def test_default_observation_marks_incomplete_attribution_as_a_refusal():
    source = LiveObservationSource(host_probe=lambda: _host_facts(attributed=False))
    observation = source()
    assert observation.attribution_complete is False
    from so101_demo.parallel_batch.resource_budget import _live_reasons

    assert "BACKGROUND_ENVELOPE_EXCEEDED" in _live_reasons(observation, now_monotonic_s=None)


def test_default_observation_ignores_swap_and_reports_only_throttling():
    """CPU/RAM/GPU-only amendment (74d6b781): the default observation does not carry swap
    or PSI as dimensions, so movement in those deprecated counters changes nothing while
    CPU throttling is still reported."""

    state = {"throttled": 0}

    def probe():
        return _host_facts(nr_throttled=state["throttled"])

    source = LiveObservationSource(host_probe=probe)
    first = source()
    assert (first.swap_delta, first.psi_full_delta, first.throttled) == (None, None, False)
    state.update(throttled=2)
    second = source()
    assert second.swap_delta is None and second.psi_full_delta is None
    assert second.throttled is True


def test_default_probe_exposes_no_swap_or_psi_facts():
    """A SwapTotal difference cannot drift R because the default probe publishes no swap
    or PSI keys at all."""

    from so101_demo.parallel_batch.resource_budget import probe_host_facts

    facts = probe_host_facts()
    document = dict(facts.facts)
    for name in ("swap_total_bytes", "swap_pages", "psi_full_s", "swap_used_bytes",
                 "psi_full_host_us"):
        assert name not in document, name
        assert not hasattr(facts, name), name


# --- R3: the installed composer derives identity and applies the qualified demand ----

def _derived_environment(tmp_path, *, source_root=WORKTREE, install_prefix=None):
    install_prefix = install_prefix or (WORKTREE / "src")
    binding = tmp_path / "provenance-binding.json"
    _write(binding, {
        "schema_version": 1, "kind": "TEST_BINDING", "install_kind": "offline_copied",
        "install_prefix": str(install_prefix), "source_root": str(source_root),
        "source_commit": "a" * 40,
    })
    return {
        "SO101_VALIDATION_PROVENANCE_BINDING": str(binding),
        "SO101_PARALLEL_RUNTIME_CONFIG": str(V2_CONFIG),
    }


def _identity(tmp_path, install_prefix) -> str:
    """The identity the installed composer itself derives from the fixture ports."""

    environment = _derived_environment(tmp_path, install_prefix=install_prefix)
    fingerprint = build_runtime_fingerprint_from_environment(
        environment, identity=None, config_path=V2_CONFIG, source_root=WORKTREE,
        install_prefix=install_prefix, host_probe=lambda environment=None: _host_facts(),
        inventory_reader=_fixture_reader)
    return fingerprint.sha256


def _derived_fixture(tmp_path, *, demand=600.0, uncertainty=0.0):
    """A complete chain whose declared identity is the *derived* fingerprint hash."""

    install_prefix = WORKTREE / "src"
    identity = _identity(tmp_path, install_prefix)
    root = tmp_path / "trusted-authority"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    qualification = {
        "schema_version": 2, "execution_identity_sha256": identity, "worker_count": 4,
        "coverage_policy_sha256": "b" * 64, "sealed_manifest_sha256s": ["d" * 64],
        "normal_valid_runs": 5, "normal_required_runs": 5, "coverage_complete": True,
        "cleanup_verified": True, "independent_physics_verified": True,
        "resource_contract_verified": True,
    }
    qualification_path = root / "qualification.json"
    qualification_sha = _write(qualification_path, qualification)
    stage = {
        "demand": {"ram_bytes": demand, "gpu_bytes": demand, "cpu_core_equivalent": 2.0},
        "uncertainty": _dimensions(uncertainty),
        "background": _dimensions(0.0), "tool_overhead": _dimensions(0.0),
        "available_headroom": _dimensions(200.0),
    }
    profile_path = tmp_path / "sealed-profile/profile.json"
    profile_sha = _write(profile_path, {
        "schema_version": 2, "execution_identity_sha256": identity,
        "coverage_policy_sha256": "b" * 64,
        "entries": {"4": {
            "worker_count": 4, "status": "APPROVED", "qualification_sha256": qualification_sha,
            "raw_manifest_sha256s": ["d" * 64],
            "coverage": {cell: ["observed"] for cell in COVERAGE_CELLS},
            "stages": {name: dict(stage) for name in
                       ("startup", "steady", "recovery", "finalization")},
            "review_reference": "astra:default-path",
        }},
    })
    audit = FullByteAudit(
        schema_version=2, source_commit="1" * 40, source_clean=True,
        prefix=str(install_prefix),
        files=(InventoryEntry("a.py", "2" * 64),),
        origins={"so101_demo_py": str(install_prefix)})
    approval = root / "operator-approval.json"
    _write(approval, {
        "schema_version": 2, "kind": "OPERATOR_APPROVAL", "operator_uid": 1000,
        "decision": "APPROVED", "target": "EXACT_N_PRODUCTION", "exact_worker_count": 4,
        "profile_sha256": profile_sha, "measurement_audit_sha256": audit.sha256})
    sol = root / "sol-result-review.json"
    _write(sol, {
        "schema_version": 2, "kind": "INDEPENDENT_REVIEW", "reviewer": "sol",
        "result": "PASS", "target": "EXECUTION_RESULT", "profile_sha256": profile_sha,
        "measurement_audit_sha256": audit.sha256})
    astra = root / "astra-profile-review.json"
    _write(astra, {
        "schema_version": 2, "kind": "INDEPENDENT_REVIEW", "reviewer": "astra",
        "result": "PASS", "target": "PROFILE", "profile_sha256": profile_sha,
        "measurement_audit_sha256": audit.sha256})
    authority = PromotionAuthority(root)
    promotion_path = publish_promotion(
        profile_path=profile_path, profile_sha256=profile_sha, operator_approval=approval,
        sol_result_review=sol, astra_profile_review=astra, measurement_audit=audit,
        destination=root / "promotion.json", authority=authority)
    location = {"prefix": str(install_prefix), "host": "fixture-host"}
    receipt_path = build_deployment_receipt(
        promotion_path=promotion_path, profile_sha256=profile_sha, installed_audit=audit,
        execution_identity_sha256=identity, location_binding=location)
    return {
        "identity": identity, "audit": audit, "authority": authority, "root": root,
        "profile_path": profile_path, "profile_sha": profile_sha,
        "qualification_path": qualification_path, "qualification_sha": qualification_sha,
        "promotion_path": promotion_path, "receipt_path": receipt_path, "location": location,
        "approval": approval, "sol": sol, "astra": astra,
    }


def _default_gate(tmp_path, chain, *, source, install_prefix):
    environment = _derived_environment(tmp_path, install_prefix=install_prefix)
    audit_path = tmp_path / "trusted-authority/installed-audit.json"
    _write(audit_path, chain["audit"].as_document())
    location_path = tmp_path / "trusted-authority/location.json"
    _write(location_path, chain["location"])
    environment.update({
        "SO101_VALIDATION_BUDGET_PROFILE": str(chain["profile_path"]),
        "SO101_VALIDATION_BUDGET_PROFILE_SHA256": chain["profile_sha"],
        "SO101_VALIDATION_PROMOTION_RECORD": str(chain["promotion_path"]),
        "SO101_VALIDATION_PROMOTION_ROOT": str(chain["root"]),
        "SO101_VALIDATION_DEPLOYMENT_RECEIPT": str(chain["receipt_path"]),
        "SO101_VALIDATION_INSTALLED_AUDIT": str(audit_path),
        "SO101_VALIDATION_LOCATION_BINDING": str(location_path),
        "SO101_VALIDATION_QUALIFICATION_PATHS": json.dumps(
            {"4": str(chain["qualification_path"])}, sort_keys=True),
        "SO101_VALIDATION_EXECUTION_IDENTITY": chain["identity"],
    })
    gate = compose_production_admission(
        environment=environment, current=None, observation_source=source,
        config_path=V2_CONFIG, source_root=WORKTREE, install_prefix=install_prefix,
        host_probe=lambda environment=None: _host_facts(), inventory_reader=_fixture_reader)
    assert gate is not None
    return gate


def _fixture_reader(root: Path, kind: str) -> dict[str, bytes]:
    """Same-file-set inventory port so the identity is stable inside this fixture."""

    del root, kind
    return {"a.py": b"print('a')\n"}


def test_installed_composer_derives_the_identity_it_declares(tmp_path):
    chain = _derived_fixture(tmp_path)
    source = LiveObservationSource(host_probe=lambda: _host_facts())
    gate = _default_gate(tmp_path, chain, source=source, install_prefix=WORKTREE / "src")
    assert gate.execution_identity_sha256 == chain["identity"]
    request = FixedAdmissionRequest(
        worker_count=4, batch_id="batch-a", epoch=1,
        execution_identity_sha256=chain["identity"], request_kind=gate.request_kind)
    decision = gate.admit(request)
    assert decision.admitted is True, decision.reason_codes
    assert decision.profile_sha256 == chain["profile_sha"]


def test_exact_n_demand_comes_from_the_profile_and_refuses_when_it_does_not_fit(tmp_path):
    chain = _derived_fixture(tmp_path, demand=600.0)
    observation = {"observed": 170.0}

    def source():
        return LiveObservationSource(
            host_probe=lambda: _host_facts(used=observation["observed"]))()

    gate = _default_gate(tmp_path, chain, source=source, install_prefix=WORKTREE / "src")
    request = FixedAdmissionRequest(
        worker_count=4, batch_id="batch-a", epoch=1,
        execution_identity_sha256=chain["identity"], request_kind=gate.request_kind)
    # 170 + 600 = 770 <= 800 of one capacity envelope: admitted.
    assert gate.admit(request).admitted is True
    # 300 + 600 = 900 > 800: the same profile can no longer admit.
    observation["observed"] = 300.0
    refused = gate.admit(request)
    assert refused.admitted is False
    assert refused.reason_codes


def test_default_composer_refuses_a_declared_identity_it_cannot_derive(tmp_path):
    chain = _derived_fixture(tmp_path)
    environment = _derived_environment(tmp_path, install_prefix=WORKTREE / "src")
    audit_path = tmp_path / "trusted-authority/installed-audit.json"
    _write(audit_path, chain["audit"].as_document())
    location_path = tmp_path / "trusted-authority/location.json"
    _write(location_path, chain["location"])
    environment.update({
        "SO101_VALIDATION_BUDGET_PROFILE": str(chain["profile_path"]),
        "SO101_VALIDATION_BUDGET_PROFILE_SHA256": chain["profile_sha"],
        "SO101_VALIDATION_PROMOTION_RECORD": str(chain["promotion_path"]),
        "SO101_VALIDATION_PROMOTION_ROOT": str(chain["root"]),
        "SO101_VALIDATION_DEPLOYMENT_RECEIPT": str(chain["receipt_path"]),
        "SO101_VALIDATION_INSTALLED_AUDIT": str(audit_path),
        "SO101_VALIDATION_LOCATION_BINDING": str(location_path),
        "SO101_VALIDATION_QUALIFICATION_PATHS": json.dumps(
            {"4": str(chain["qualification_path"])}, sort_keys=True),
        "SO101_VALIDATION_EXECUTION_IDENTITY": "9" * 64,
    })
    with pytest.raises(ContractError) as error:
        compose_production_admission(
            environment=environment, observation_source=lambda: None,
            config_path=V2_CONFIG, source_root=WORKTREE, install_prefix=WORKTREE / "src",
            host_probe=lambda environment=None: _host_facts(), inventory_reader=_fixture_reader)
    assert "RUNTIME_FINGERPRINT_MISMATCH" in str(error.value)


def test_default_fingerprint_is_not_the_declared_identity_by_construction(tmp_path):
    """The old defect copied the declared identity into S/E/I; it is now derived."""

    environment = _derived_environment(tmp_path, install_prefix=WORKTREE / "src")
    fingerprint = build_runtime_fingerprint_from_environment(
        environment, identity=None, config_path=V2_CONFIG, source_root=WORKTREE,
        install_prefix=WORKTREE / "src",
        host_probe=lambda environment=None: _host_facts(), inventory_reader=_fixture_reader)
    assert fingerprint.sha256 != "9" * 64
    assert fingerprint.semantic_config_sha256 != fingerprint.sha256
    assert fingerprint.execution_inventory_sha256 != fingerprint.sha256
    assert fingerprint.installed_inventory_sha256 != fingerprint.sha256
    with pytest.raises(ContractError) as error:
        build_runtime_fingerprint_from_environment(
            environment, identity="9" * 64, config_path=V2_CONFIG, source_root=WORKTREE,
            install_prefix=WORKTREE / "src",
            host_probe=lambda environment=None: _host_facts(),
            inventory_reader=_fixture_reader)
    assert "RUNTIME_FINGERPRINT_MISMATCH" in str(error.value)


# --- R4: the deployment receipt fields are bound to current authority ----------------


def _provider_for(chain):
    provider = ResourceBudgetProvider()
    provider.load(chain["profile_path"], expected_sha256=chain["profile_sha"])
    provider.record_qualification(ExactNQualification.from_document(
        json.loads(Path(chain["qualification_path"]).read_bytes()),
        raw_sha256=chain["qualification_sha"]))
    return provider


def _issue(chain, **overrides):
    values = {
        "provider": _provider_for(chain),
        "scope": AllocationScope("batch-a", 1, 4, "FIXED_PRODUCTION", chain["identity"]),
        "profile_path": chain["profile_path"],
        "expected_profile_sha256": chain["profile_sha"],
        "promotion_path": chain["promotion_path"],
        "deployment_receipt_path": chain["receipt_path"],
        "control_binding": dict(chain["location"]),
        "authority": chain["authority"],
        "installed_audit": chain["audit"],
        "current_identity_sha256": chain["identity"],
        "location_binding": dict(chain["location"]),
    }
    values.update(overrides)
    return issue_production_context(**values)


def test_complete_closed_chain_mints_one_context(tmp_path):
    chain = _derived_fixture(tmp_path)
    verify_promotion(
        profile=_provider_for(chain)._profile,  # type: ignore[attr-defined]
        promotion_path=chain["promotion_path"], authority=chain["authority"],
        execution_identity_sha256=chain["identity"], exact_worker_count=4)
    context = _issue(chain)
    assert context.profile_sha256 == chain["profile_sha"]
    assert context.scope.worker_count == 4


def test_deleted_or_foreign_receipt_authority_is_refused(tmp_path):
    """Deleting/changing A1, R or location must never mint a production context."""

    chain = _derived_fixture(tmp_path)
    foreign_audit = FullByteAudit(
        schema_version=2, source_commit="3" * 40, source_clean=True,
        prefix=str(tmp_path / "other-install"),
        files=(InventoryEntry("a.py", "4" * 64),),
        origins={"so101_demo_py": str(tmp_path / "other-install")})
    with pytest.raises(ContractError) as error:
        _issue(chain, installed_audit=foreign_audit)
    assert "DEPLOYMENT_RECEIPT_AUDIT_MISMATCH" in str(error.value)

    with pytest.raises(ContractError) as error:
        _issue(chain, current_identity_sha256="9" * 64)
    assert "DEPLOYMENT_RECEIPT_IDENTITY_MISMATCH" in str(error.value)

    with pytest.raises(ContractError) as error:
        _issue(chain, location_binding={"prefix": "/elsewhere", "host": "fixture-host"})
    assert "DEPLOYMENT_RECEIPT_LOCATION_MISMATCH" in str(error.value)

    with pytest.raises(ContractError) as error:
        _issue(chain, control_binding={"prefix": "/elsewhere"})
    assert "CONTROL_BINDING_MISMATCH" in str(error.value)

    deleted = json.loads(Path(chain["receipt_path"]).read_bytes())
    deleted.pop("installed_audit_sha256", None)
    deleted_path = chain["root"] / "deleted-receipt.json"
    _write(deleted_path, deleted)
    with pytest.raises(ContractError) as error:
        _issue(chain, deployment_receipt_path=deleted_path)
    assert "DEPLOYMENT_RECEIPT_MISSING_FIELD" in str(error.value)

    unknown = json.loads(Path(chain["receipt_path"]).read_bytes())
    unknown["extra"] = "unexpected"
    unknown_path = chain["root"] / "unknown-receipt.json"
    _write(unknown_path, unknown)
    with pytest.raises(ContractError) as error:
        _issue(chain, deployment_receipt_path=unknown_path)
    assert "DEPLOYMENT_RECEIPT_UNKNOWN_FIELD" in str(error.value)


def test_promotion_documents_must_bind_profile_target_and_audit(tmp_path):
    """A well-shaped review hash is not authority; the documents are re-read."""

    chain = _derived_fixture(tmp_path)
    provider = _provider_for(chain)
    profile = provider._profile  # type: ignore[attr-defined]

    # Unknown field inside M itself.
    promotion = json.loads(Path(chain["promotion_path"]).read_bytes())
    promotion["unexpected"] = 1
    unknown_path = chain["root"] / "unknown-promotion.json"
    _write(unknown_path, promotion)
    with pytest.raises(ContractError) as error:
        verify_promotion(profile=profile, promotion_path=unknown_path,
                         authority=chain["authority"])
    assert "PROMOTION_UNKNOWN_FIELD" in str(error.value)

    # A review document that does not bind this profile.
    foreign = json.loads(Path(chain["astra"]).read_bytes())
    foreign["profile_sha256"] = "9" * 64
    foreign_path = chain["root"] / "foreign-astra.json"
    foreign_sha = _write(foreign_path, foreign)
    substituted = json.loads(Path(chain["promotion_path"]).read_bytes())
    substituted["astra_profile_review_sha256"] = foreign_sha
    substituted["documents"]["astra_profile_review"] = foreign_path.name
    substituted["reviews"] = [
        {"reviewer": "sol", "result": "PASS",
         "sha256": substituted["sol_result_review_sha256"]},
        {"reviewer": "astra", "result": "PASS", "sha256": foreign_sha},
    ]
    substituted_path = chain["root"] / "substituted-promotion.json"
    _write(substituted_path, substituted)
    with pytest.raises(ContractError) as error:
        verify_promotion(profile=profile, promotion_path=substituted_path,
                         authority=chain["authority"])
    assert "PROMOTION_REVIEW_BINDING" in str(error.value)

    # A top-level review hash that is not the recorded review list entry.
    mismatched = json.loads(Path(chain["promotion_path"]).read_bytes())
    mismatched["sol_result_review_sha256"] = "7" * 64
    mismatched_path = chain["root"] / "mismatched-promotion.json"
    _write(mismatched_path, mismatched)
    with pytest.raises(ContractError) as error:
        verify_promotion(profile=profile, promotion_path=mismatched_path,
                         authority=chain["authority"])
    assert "PROMOTION_REVIEWS" in str(error.value)

    # A swapped measurement audit (A0) no longer matches the reviews that bound it.
    swapped = json.loads(Path(chain["promotion_path"]).read_bytes())
    swapped["measurement_audit"]["source_commit"] = "5" * 40
    swapped_path = chain["root"] / "swapped-audit-promotion.json"
    _write(swapped_path, swapped)
    with pytest.raises(ContractError) as error:
        verify_promotion(profile=profile, promotion_path=swapped_path,
                         authority=chain["authority"])
    assert "PROMOTION_AUDIT_MISMATCH" in str(error.value)
