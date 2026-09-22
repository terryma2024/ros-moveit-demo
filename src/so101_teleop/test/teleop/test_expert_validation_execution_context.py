"""Task 9: the two execution contexts, and the profile a restored campaign really ran.

The design has no resource-measurement authorization: a live run is either a bounded candidate run
or an installed production run, each bound to a task/dispatch or a service session, a profile and
config hash, a runtime closure, a worker count, a batch, an evidence root, an owner generation, a
one-time command and an expiry. Neither context carries budget, qualification or promotion fields,
and neither may be replayed across a batch, profile, worker count or evidence root.
"""

from dataclasses import fields, replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import time

import pytest

from so101_teleop.expert_validation.catalog import CatalogPoint, PointSelection
from so101_teleop.expert_validation.execution_context import (
    CANDIDATE_CONTEXT_KIND,
    PRODUCTION_CONTEXT_KIND,
    RETRY_BATCH_KIND,
    RETRY_PROFILE,
    RETRY_SCHEMA_VERSION,
    RETRY_WORKER_COUNT,
    CandidateExecutionContext,
    ExecutionContextError,
    ProductionExecutionContext,
    install_binding_sha256,
    retry_batch_root,
    runtime_closure_sha256,
)
from so101_teleop.expert_validation.production import ProductionExpertValidationService
from so101_teleop.expert_validation.store import SupervisorStore

REPO = Path(__file__).resolve().parents[4]
V4_DOCUMENT = REPO / "src/so101_demo_py/config/mujoco/parallel_batch_v4_macos_mps_w2.yaml"
V5_DOCUMENT = REPO / "src/so101_demo_py/config/mujoco/parallel_batch_v5_macos_mps_w1_retry.yaml"
V6_DOCUMENT = REPO / "src/so101_demo_py/config/mujoco/parallel_batch_v6_macos_mps_w1_first_pass.yaml"

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64

#: Any field whose name promises a measurement authority this design deliberately does not have.
FORBIDDEN_FIELDS = ("budget", "qualification", "qualified", "promotion", "promote", "capacity")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate(tmp_path, **changes) -> CandidateExecutionContext:
    values = dict(
        context_id="candidate-context-1",
        task_id="task-9",
        dispatch_id="dispatch-1",
        campaign_id="campaign-1",
        batch_id="retry-001",
        manifest_id="manifest-1",
        execution_profile=RETRY_PROFILE,
        schema_version=RETRY_SCHEMA_VERSION,
        batch_kind=RETRY_BATCH_KIND,
        worker_count=RETRY_WORKER_COUNT,
        config_sha256=SHA_A,
        runtime_closure_sha256=SHA_B,
        evidence_root=tmp_path.resolve(),
        owner_generation=1,
        command_id="cmd-retry-1",
        issued_at_monotonic_ns=1_000,
        expires_at_monotonic_ns=1_000 + 60_000_000_000,
        max_runs=1,
    )
    values.update(changes)
    return CandidateExecutionContext(**values)


def _production(tmp_path, **changes) -> ProductionExecutionContext:
    values = dict(
        context_id="production-context-1",
        service_session_id="session-1",
        lease_id="lease-1",
        lease_generation=1,
        install_prefix=(tmp_path / "install").resolve(),
        install_binding_sha256=install_binding_sha256(
            install_prefix=(tmp_path / "install").resolve(),
            runtime_closure_sha256=SHA_B,
        ),
        execution_profile=RETRY_PROFILE,
        schema_version=RETRY_SCHEMA_VERSION,
        batch_kind=RETRY_BATCH_KIND,
        worker_count=RETRY_WORKER_COUNT,
        campaign_id="campaign-1",
        batch_id="retry-001",
        manifest_id="manifest-1",
        config_sha256=SHA_A,
        runtime_closure_sha256=SHA_B,
        evidence_root=tmp_path.resolve(),
        owner_generation=1,
        command_id="cmd-retry-1",
        issued_at_monotonic_ns=1_000,
        expires_at_monotonic_ns=1_000 + 60_000_000_000,
    )
    values.update(changes)
    return ProductionExecutionContext(**values)


# --------------------------------------------------------------------------------------
# The two contexts carry execution authority only
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("factory", [_candidate, _production])
def test_context_carries_no_budget_qualification_or_promotion_field(tmp_path, factory):
    context = factory(tmp_path)
    names = {field.name for field in fields(context)} | set(context.as_document())
    assert not [name for name in names if any(word in name for word in FORBIDDEN_FIELDS)]


def test_candidate_context_names_its_own_kind_and_scope(tmp_path):
    context = _candidate(tmp_path, max_runs=3)
    assert context.kind == CANDIDATE_CONTEXT_KIND
    document = context.as_document()
    assert document["kind"] == CANDIDATE_CONTEXT_KIND
    assert document["task_id"] == "task-9" and document["dispatch_id"] == "dispatch-1"
    assert document["max_runs"] == 3
    assert document["evidence_root"] == str(tmp_path.resolve())


def test_production_context_names_its_own_kind_and_session(tmp_path):
    context = _production(tmp_path)
    assert context.kind == PRODUCTION_CONTEXT_KIND
    document = context.as_document()
    assert document["kind"] == PRODUCTION_CONTEXT_KIND
    assert document["service_session_id"] == "session-1"
    assert document["lease_id"] == "lease-1" and document["lease_generation"] == 1
    assert document["install_prefix"] == str((tmp_path / "install").resolve())


def test_the_two_contexts_are_different_types_and_neither_accepts_the_other(tmp_path):
    candidate = _candidate(tmp_path)
    production = _production(tmp_path)
    assert not isinstance(candidate, ProductionExecutionContext)
    assert not isinstance(production, CandidateExecutionContext)
    assert candidate.kind != production.kind


def test_context_is_expired_exactly_at_its_deadline(tmp_path):
    context = _candidate(tmp_path, issued_at_monotonic_ns=100, expires_at_monotonic_ns=200)
    assert context.is_expired(199) is False
    assert context.is_expired(200) is True
    assert context.is_expired(201) is True


def test_context_refuses_a_non_positive_expiry_or_a_deadline_before_issue(tmp_path):
    with pytest.raises(ExecutionContextError, match="CONTEXT_EXPIRY_INVALID"):
        _candidate(tmp_path, expires_at_monotonic_ns=1_000)
    with pytest.raises(ExecutionContextError, match="CONTEXT_EXPIRY_INVALID"):
        _candidate(tmp_path, expires_at_monotonic_ns=999)
    with pytest.raises(ExecutionContextError, match="CONTEXT_POSITIVE_INTEGER"):
        _candidate(tmp_path, max_runs=0)


# --------------------------------------------------------------------------------------
# The production context is issued from the installed matrix, never from a claim
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("profile", "schema_version", "batch_kind", "worker_count"),
    [
        ("MPS_W2_FIRST_PASS", 4, "FIRST_PASS", 2),
        ("MPS_W1_FULL_RESTART_RETRY", 5, "FULL_RESTART_RETRY", 1),
        ("MPS_W1_FIRST_PASS", 6, "FIRST_PASS", 1),
    ],
)
def test_production_context_accepts_every_installed_profile_row(
    tmp_path, profile, schema_version, batch_kind, worker_count
):
    context = _production(
        tmp_path,
        execution_profile=profile,
        schema_version=schema_version,
        batch_kind=batch_kind,
        worker_count=worker_count,
    )
    assert context.schema_version == schema_version


@pytest.mark.parametrize(
    ("profile", "schema_version", "batch_kind", "worker_count"),
    [
        ("MPS_W4_FAST", 7, "FIRST_PASS", 4),
        ("MPS_W2_FIRST_PASS", 5, "FULL_RESTART_RETRY", 2),
        ("MPS_W1_FIRST_PASS", 6, "FIRST_PASS", 2),
    ],
)
def test_production_context_refuses_anything_outside_the_installed_matrix(
    tmp_path, profile, schema_version, batch_kind, worker_count
):
    with pytest.raises(ExecutionContextError, match="CONTEXT_PROFILE_INVALID"):
        _production(
            tmp_path,
            execution_profile=profile,
            schema_version=schema_version,
            batch_kind=batch_kind,
            worker_count=worker_count,
        )


def test_production_context_refuses_an_unknown_install_or_invalid_binding(tmp_path):
    with pytest.raises(ExecutionContextError, match="CONTEXT_SHA256_INVALID"):
        _production(tmp_path, install_binding_sha256="not-a-sha")


@pytest.mark.parametrize(
    ("profile", "schema_version", "batch_kind", "worker_count"),
    [
        ("MPS_W2_FIRST_PASS", 4, "FIRST_PASS", 1),
        ("MPS_W1_FIRST_PASS", 6, "FULL_RESTART_RETRY", 1),
        ("MPS_W1_FULL_RESTART_RETRY", 5, "FULL_RESTART_RETRY", 2),
    ],
)
def test_candidate_context_refuses_a_combination_outside_the_installed_matrix(
    tmp_path, profile, schema_version, batch_kind, worker_count
):
    """A candidate run executes an installed row; the caller never restates its shape."""

    with pytest.raises(ExecutionContextError, match="CONTEXT_PROFILE_INVALID"):
        _candidate(
            tmp_path,
            execution_profile=profile,
            schema_version=schema_version,
            batch_kind=batch_kind,
            worker_count=worker_count,
        )


def test_install_binding_covers_the_prefix_and_the_whole_runtime_closure(tmp_path):
    first = install_binding_sha256(install_prefix=tmp_path.resolve(), runtime_closure_sha256=SHA_A)
    assert first == install_binding_sha256(
        install_prefix=tmp_path.resolve(), runtime_closure_sha256=SHA_A
    )
    assert first != install_binding_sha256(
        install_prefix=tmp_path.resolve(), runtime_closure_sha256=SHA_B
    )
    assert first != install_binding_sha256(
        install_prefix=(tmp_path / "other").resolve(), runtime_closure_sha256=SHA_A
    )


# --------------------------------------------------------------------------------------
# The runtime closure hash covers every executable and config byte
# --------------------------------------------------------------------------------------


def _campaign_request(**changes):
    values = dict(
        campaign_id="campaign-1",
        batch_id="batch-1",
        manifest_id="manifest-1",
        selection=None,
        execution_mode="SEQUENTIAL",
        evidence_root=Path("/evidence"),
        points_path=Path("/points.yaml"),
        parallel_config_path=Path("/parallel.yaml"),
        adaptive_config_path=Path("/adaptive.yaml"),
        worker_count=1,
        max_points_per_worker=None,
        fallback_worker_counts=(6, 4, 2, 1),
        initial_points_per_worker=3,
        worker_start_timeout_s=120.0,
        max_infra_attempts_per_point=5,
        yolo_executor_count=2,
        service_session_id="session-1",
        lease_generation=1,
        source_commit="1" * 40,
        install_prefix="/opt/validation",
        coordinator_executable_sha256=SHA_A,
        adaptive_runner_module_sha256=SHA_A,
        adaptive_pool_module_sha256=SHA_A,
        adaptive_cleanup_executable_sha256=SHA_A,
        adaptive_wrapper_sha256=SHA_A,
        parallel_config_sha256=SHA_A,
        adaptive_config_sha256=SHA_A,
        yolo_weights_sha256=SHA_A,
        grounded_sam_manifest_sha256=SHA_A,
        broker_image_id="sha256:" + SHA_A,
        resource_manifest_sha256=SHA_A,
    )
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    "field",
    [
        "coordinator_executable_sha256",
        "adaptive_runner_module_sha256",
        "adaptive_pool_module_sha256",
        "adaptive_cleanup_executable_sha256",
        "adaptive_wrapper_sha256",
        "parallel_config_sha256",
        "adaptive_config_sha256",
        "yolo_weights_sha256",
        "grounded_sam_manifest_sha256",
        "broker_image_id",
        "resource_manifest_sha256",
        "install_prefix",
        "source_commit",
    ],
)
def test_runtime_closure_changes_with_every_executable_and_config_field(field):
    baseline = runtime_closure_sha256(_campaign_request())
    other = "sha256:" + SHA_B if field == "broker_image_id" else (
        "/opt/other" if field == "install_prefix" else (
            "2" * 40 if field == "source_commit" else SHA_B
        )
    )
    assert runtime_closure_sha256(_campaign_request(**{field: other})) != baseline


def test_runtime_closure_is_a_stable_hash_of_its_own_document():
    digest = runtime_closure_sha256(_campaign_request())
    assert isinstance(digest, str) and len(digest) == 64
    assert digest == runtime_closure_sha256(_campaign_request())


def test_retry_batch_root_is_the_one_path_the_store_and_supervisor_both_derive(tmp_path):
    evidence = tmp_path.resolve()
    assert retry_batch_root(evidence, "campaign-1", "retry-001") == (
        evidence / "campaigns" / "campaign-1" / "retry-001"
    ).resolve()


# --------------------------------------------------------------------------------------
# Task 8 left a gap: a restored campaign must be rebuilt from its receipt's own profile
# --------------------------------------------------------------------------------------


def _selection(count=4):
    points = tuple(
        CatalogPoint(
            id=f"point_{index}",
            label=f"Point {index}",
            source="generated",
            stratum="near/center",
            position_world_m=(float(index), 0.0, 0.0),
            display_id=f"P{index:02d}",
        )
        for index in range(1, count + 1)
    )
    return PointSelection("catalog", 1, SHA_A, points, tuple(p.id for p in points), SHA_A)


def _restored_service(tmp_path, store):
    install = tmp_path / "install"
    install.mkdir(parents=True, exist_ok=True)
    for name in ("so101_parallel_batch", "cleanup", "run_adaptive.zsh"):
        path = install / name
        path.write_text("binary\n", encoding="utf-8")
    (tmp_path / "points.yaml").write_text("points: []\n", encoding="utf-8")
    (tmp_path / "adaptive.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    service = object.__new__(ProductionExpertValidationService)
    service.store = store
    service.layout = SimpleNamespace(
        demo_prefix=(tmp_path / "install").resolve(),
        points_path=(tmp_path / "points.yaml").resolve(),
        parallel_config_path=V4_DOCUMENT,
        adaptive_config_path=(tmp_path / "adaptive.yaml").resolve(),
        coordinator_executable=(tmp_path / "install/so101_parallel_batch").resolve(),
        cleanup_executable=(tmp_path / "install/cleanup").resolve(),
        adaptive_wrapper=(tmp_path / "install/run_adaptive.zsh").resolve(),
        yolo_weights_path=None,
        yolo_weights_sha256=SHA_A,
        grounded_root=None,
        grounded_manifest_sha256=SHA_A,
        broker_image_id="sha256:" + SHA_A,
        provenance_binding=None,
        source_commit="1" * 40,
    )
    service._selection = lambda manifest_id: _selection()
    return service


def _persisted_campaign(tmp_path, profile_claim):
    """One durable campaign row whose receipt named ``profile_claim`` (or nothing)."""

    from so101_teleop.expert_validation.models import (
        BatchBinding,
        CampaignBinding,
        PreflightReceipt,
    )

    store = SupervisorStore.open((tmp_path / "store").resolve())
    store.record_manifest(
        "manifest-1",
        {
            "catalog_sha256": SHA_A,
            "selection_sha256": SHA_A,
            "point_ids": ["point_1", "point_2", "point_3", "point_4"],
        },
        source_config_sha256=SHA_A,
        created_at_ns=1,
    )
    document = {
        "execution_profile": "MPS_W1_FIRST_PASS",
        "schema_version": 6,
        "batch_kind": "FIRST_PASS",
        "execution_config_sha256": _sha256(V6_DOCUMENT),
    }
    store.record_preflight_receipt(
        PreflightReceipt(
            receipt_id="receipt-1",
            campaign_id="campaign-1",
            manifest_id="manifest-1",
            canonical_start_request_sha256=SHA_A,
            receipt=document,
            expires_at_monotonic_ns=10_000_000_000,
        )
    )
    store.consume_preflight_and_bind_campaign_batch(
        "receipt-1",
        SHA_A,
        CampaignBinding(
            campaign_id="campaign-1",
            manifest_id="manifest-1",
            executor_id="expert-validation-web",
            operation_id="first-pass",
            executor_config_sha256=SHA_A,
            execution_mode="SEQUENTIAL",
            execution_config={"worker_count": 1},
            preflight_receipt_id="receipt-1",
        ),
        BatchBinding(
            batch_id="b001",
            campaign_id="campaign-1",
            batch_kind="FIRST_PASS",
            point_id=None,
            journal_root=(tmp_path / "store/campaigns/campaign-1/b001").resolve(),
            coordinator_epoch=1,
        ),
        now_monotonic_ns=1,
    )
    row = store.campaign_records()[0]
    return store, row


def test_restored_request_binds_the_receipts_own_profile_not_the_configured_document(tmp_path):
    """A restart of a v6 W1 campaign must not rebuild it against the configured v4 document."""

    store, row = _persisted_campaign(tmp_path, "MPS_W1_FIRST_PASS")
    try:
        request = _restored_service(tmp_path, store)._restored_request(row)
        assert request.execution_profile == "MPS_W1_FIRST_PASS"
        assert request.batch_kind == "FIRST_PASS"
        assert request.parallel_config_path == V6_DOCUMENT
        assert request.parallel_config_sha256 == _sha256(V6_DOCUMENT)
        assert request.worker_count == 1
        assert request.execution_mode == "SEQUENTIAL"
    finally:
        store.close()


def test_restored_request_keeps_the_configured_document_without_a_profile_receipt(tmp_path):
    store, row = _persisted_campaign(tmp_path, None)
    try:
        connection = store._connection
        connection.execute(
            "UPDATE preflight_receipts SET receipt_json = ? WHERE receipt_id = 'receipt-1'",
            (json.dumps({"admitted": True}),),
        )
        service = _restored_service(tmp_path, store)
        request = service._restored_request(row)
        assert request.execution_profile is None
        assert request.parallel_config_path == V4_DOCUMENT
        assert request.parallel_config_sha256 == _sha256(V4_DOCUMENT)
    finally:
        store.close()


def test_restored_request_refuses_a_receipt_naming_an_uninstalled_profile(tmp_path):
    store, row = _persisted_campaign(tmp_path, "MPS_W1_FIRST_PASS")
    try:
        connection = store._connection
        connection.execute(
            "UPDATE preflight_receipts SET receipt_json = ? WHERE receipt_id = 'receipt-1'",
            (json.dumps({"execution_profile": "MPS_W8_FAST", "schema_version": 8}),),
        )
        service = _restored_service(tmp_path, store)
        with pytest.raises(Exception, match="UNSUPPORTED_ON_MACOS|EXECUTION_PROFILE"):
            service._restored_request(row)
    finally:
        store.close()


# --------------------------------------------------------------------------------------
# A CandidateExecutionContext is one bounded run, and its deadline is not extended
# --------------------------------------------------------------------------------------


def test_candidate_context_replay_is_refused_after_its_command_is_consumed(tmp_path):
    """The context itself never grants a second run: only a fresh command does."""

    now = time.monotonic_ns()
    context = _candidate(
        tmp_path,
        issued_at_monotonic_ns=now,
        expires_at_monotonic_ns=now + 60_000_000_000,
        max_runs=2,
    )
    consumed = replace(context, command_id="cmd-retry-2")
    assert consumed.command_id != context.command_id
    assert consumed.context_sha256() != context.context_sha256()


# --------------------------------------------------------------------------------------
# Task 11 closure: the candidate context has a real issuance entry point
#
# The gap Task 11 found: `issue_candidate_context()` authorized the retry endpoint only and
# had no HTTP route and no CLI caller, so no first-pass candidate run could be authorized.
# Issuance is now one-time and command-scoped, binds the profile's installed document and the
# current runtime closure / copied-install binding, and is refused by a fence or an unknown
# owner.
# --------------------------------------------------------------------------------------


def _issuance_service(tmp_path, *, store=None, campaigns=None):
    """A composed production service whose installed documents are the three real ones."""

    import shutil

    from so101_teleop.expert_validation.production import ProductionExpertValidationService

    root = tmp_path.resolve()
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    for document in (V4_DOCUMENT, V5_DOCUMENT, V6_DOCUMENT):
        shutil.copyfile(document, config_dir / document.name)
    install = root / "install"
    install.mkdir(parents=True, exist_ok=True)
    for name in ("so101_parallel_batch", "cleanup", "run_adaptive.zsh"):
        (install / name).write_text("binary\n", encoding="utf-8")
    (root / "adaptive.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    (root / "points.yaml").write_text("points: []\n", encoding="utf-8")
    store = store or SupervisorStore.open(root / "store")
    service = ProductionExpertValidationService(
        layout=SimpleNamespace(
            parallel_config_path=config_dir / V4_DOCUMENT.name,
            demo_prefix=install,
            points_path=root / "points.yaml",
            adaptive_config_path=root / "adaptive.yaml",
            coordinator_executable=install / "so101_parallel_batch",
            cleanup_executable=install / "cleanup",
            adaptive_wrapper=install / "run_adaptive.zsh",
            yolo_weights_path=None,
            yolo_weights_sha256=SHA_A,
            grounded_root=None,
            grounded_manifest_sha256=SHA_A,
            broker_image_id="sha256:" + SHA_A,
            provenance_binding=None,
            source_commit="1" * 40,
        ),
        registry=None,
        artifacts=None,
        store=store,
        supervisor=None,
        lease_service=None,
        current_source_config_sha256=lambda: SHA_A,
    )
    service._selection = lambda manifest_id: _selection()
    for campaign_id, request in (campaigns or {}).items():
        service._campaign_requests[campaign_id] = request
    return service, store, config_dir


def _issue(service, config_dir, **changes):
    values = dict(
        task_id="task-11",
        dispatch_id="candidate-w2",
        campaign_id="campaign-candidate-1",
        batch_id="b001",
        manifest_id="manifest-1",
        execution_profile="MPS_W2_FIRST_PASS",
        worker_count=2,
        batch_kind="FIRST_PASS",
        config_document=str(config_dir / V4_DOCUMENT.name),
        evidence_root=str((config_dir.parent / "evidence").resolve()),
        command_id="cmd-issue-1",
        owner_generation=1,
        expires_in_s=3600.0,
        max_runs=1,
    )
    values.update(changes)
    return service.issue_candidate_context(**values)


@pytest.mark.parametrize(
    ("profile", "document", "schema_version", "worker_count", "batch_kind"),
    [
        ("MPS_W2_FIRST_PASS", V4_DOCUMENT, 4, 2, "FIRST_PASS"),
        ("MPS_W1_FIRST_PASS", V6_DOCUMENT, 6, 1, "FIRST_PASS"),
    ],
)
def test_a_candidate_context_is_issued_for_a_first_pass_from_its_installed_document(
    tmp_path, profile, document, schema_version, worker_count, batch_kind
):
    service, store, config_dir = _issuance_service(tmp_path)
    try:
        context = _issue(
            service,
            config_dir,
            execution_profile=profile,
            config_document=str(config_dir / document.name),
            worker_count=worker_count,
            batch_kind=batch_kind,
        )
        assert context.execution_profile == profile
        assert context.schema_version == schema_version
        assert context.batch_kind == batch_kind and context.worker_count == worker_count
        assert context.config_sha256 == _sha256(config_dir / document.name)
        assert context.command_id == "cmd-issue-1-run"
        assert context.evidence_root == (config_dir.parent / "evidence").resolve()
        assert context.max_runs == 1
        assert context.is_expired(time.monotonic_ns()) is False
        # The context binds the bytes and the closure the first-pass start will execute.
        request = service._candidate_first_pass_request(context)
        assert runtime_closure_sha256(request) == context.runtime_closure_sha256
        assert request.campaign_id == context.campaign_id
        assert request.batch_id == context.batch_id
        assert request.evidence_root == context.evidence_root
        assert request.parallel_config_path == config_dir / document.name
        assert service.candidate_context(context.context_id) == context
        # The response names the installed document and the copied install the closure covers.
        response = service.candidate_context_response(context)
        assert response["config_document"] == str(config_dir / document.name)
        assert response["install_prefix"] == str((config_dir.parent / "install").resolve())
        assert response["install_binding_sha256"] == install_binding_sha256(
            install_prefix=(config_dir.parent / "install").resolve(),
            runtime_closure_sha256=context.runtime_closure_sha256,
        )
        assert response["context_sha256"] == context.context_sha256()
        # Issuance is durable: the one-time command carries the document it minted.
        row = store._connection.execute(
            "SELECT state, result_json FROM commands WHERE command_id = 'cmd-issue-1'"
        ).fetchone()
        assert row["state"] == "COMPLETE"
        assert json.loads(row["result_json"])["context_id"] == context.context_id
    finally:
        store.close()


def test_a_candidate_context_is_issued_for_a_retry_of_an_existing_campaign(tmp_path):
    service, store, config_dir = _issuance_service(tmp_path)
    try:
        original = _campaign_request()
        service._campaign_requests["campaign-1"] = original
        context = _issue(
            service,
            config_dir,
            execution_profile=RETRY_PROFILE,
            config_document=str(config_dir / V5_DOCUMENT.name),
            worker_count=RETRY_WORKER_COUNT,
            batch_kind=RETRY_BATCH_KIND,
            campaign_id="campaign-1",
            batch_id="retry-001",
            command_id="cmd-issue-retry",
        )
        assert context.batch_kind == RETRY_BATCH_KIND
        assert context.schema_version == RETRY_SCHEMA_VERSION
        assert context.runtime_closure_sha256 == runtime_closure_sha256(original)
        assert context.command_id == "cmd-issue-retry-run"

        with pytest.raises(Exception, match="CONTEXT_CAMPAIGN_UNKNOWN"):
            _issue(
                service,
                config_dir,
                execution_profile=RETRY_PROFILE,
                config_document=str(config_dir / V5_DOCUMENT.name),
                worker_count=RETRY_WORKER_COUNT,
                batch_kind=RETRY_BATCH_KIND,
                campaign_id="campaign-nobody",
                batch_id="retry-001",
                command_id="cmd-issue-retry-2",
            )
    finally:
        store.close()


def test_a_replayed_issuance_or_a_reused_command_id_is_refused(tmp_path):
    service, store, config_dir = _issuance_service(tmp_path)
    try:
        _issue(service, config_dir)
        with pytest.raises(Exception, match="CONTEXT_COMMAND_ALREADY_CONSUMED"):
            _issue(service, config_dir)
        with pytest.raises(Exception, match="CONTEXT_COMMAND_ID_REUSED"):
            _issue(service, config_dir, dispatch_id="candidate-w1")
        assert len(service._candidate_contexts) == 1
    finally:
        store.close()


@pytest.mark.parametrize(
    ("profile", "document", "worker_count", "batch_kind", "code"),
    [
        ("MPS_W2_FIRST_PASS", V4_DOCUMENT, 1, "FIRST_PASS", "CONTEXT_PROFILE_INVALID"),
        ("MPS_W1_FIRST_PASS", V6_DOCUMENT, 1, "FULL_RESTART_RETRY", "CONTEXT_PROFILE_INVALID"),
        ("MPS_W1_FULL_RESTART_RETRY", V5_DOCUMENT, 2, "FULL_RESTART_RETRY",
         "CONTEXT_PROFILE_INVALID"),
        ("MPS_W8_FAST", V4_DOCUMENT, 8, "FIRST_PASS", "UNSUPPORTED_ON_MACOS"),
    ],
)
def test_issuing_refuses_a_combination_outside_the_macos_matrix(
    tmp_path, profile, document, worker_count, batch_kind, code
):
    service, store, config_dir = _issuance_service(tmp_path)
    try:
        with pytest.raises(Exception, match=code):
            _issue(
                service,
                config_dir,
                execution_profile=profile,
                config_document=str(config_dir / document.name),
                worker_count=worker_count,
                batch_kind=batch_kind,
            )
        assert service._candidate_contexts == {}
        assert store._connection.execute(
            "SELECT count(*) FROM commands WHERE command_id = 'cmd-issue-1'"
        ).fetchone()[0] == 0
    finally:
        store.close()


def test_issuing_refuses_a_config_document_that_is_not_the_installed_one(tmp_path):
    service, store, config_dir = _issuance_service(tmp_path)
    try:
        with pytest.raises(Exception, match="CONTEXT_CONFIG_DOCUMENT_MISMATCH"):
            _issue(
                service,
                config_dir,
                execution_profile="MPS_W1_FIRST_PASS",
                config_document=str(config_dir / V4_DOCUMENT.name),
                worker_count=1,
            )
        (config_dir / V6_DOCUMENT.name).unlink()
        with pytest.raises(Exception, match="EXECUTION_DOCUMENT_MISSING"):
            _issue(
                service,
                config_dir,
                execution_profile="MPS_W1_FIRST_PASS",
                config_document=str(config_dir / V6_DOCUMENT.name),
                worker_count=1,
                command_id="cmd-issue-missing",
            )
    finally:
        store.close()


def test_issuing_is_refused_by_a_recovery_fence_or_an_unknown_owner(tmp_path):
    from so101_teleop.expert_validation.store import StoreConflict
    from test_expert_validation_store import _admit_first_pass, _first_pass_fixture

    store, request, context, intent, receipt, campaign, batch = _first_pass_fixture(
        tmp_path / "durable"
    )
    _admit_first_pass(store, request, context, intent, receipt, campaign, batch)
    service, store, config_dir = _issuance_service(tmp_path, store=store)
    try:
        with pytest.raises(StoreConflict, match="CONTEXT_OWNER_UNKNOWN"):
            _issue(service, config_dir)
        store.record_recovery_fence(
            "campaign-1", "b001", reason="OWNER_TREE_UNRESOLVED", command_id="recover-1"
        )
        with pytest.raises(StoreConflict, match="CONTEXT_RECOVERY_FENCE"):
            _issue(service, config_dir)
        assert service._candidate_contexts == {}
        assert store._connection.execute(
            "SELECT count(*) FROM commands WHERE command_id = 'cmd-issue-1'"
        ).fetchone()[0] == 0
    finally:
        store.close()
