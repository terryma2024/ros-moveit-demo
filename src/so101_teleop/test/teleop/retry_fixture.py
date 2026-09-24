"""Build one complete production retry composition inside a test's own ``tmp_path``.

The retry regression tests used to replay a recorded macOS service state from a fixed ``/tmp`` run
directory. On every other host that directory is absent, so the cases that pin the retry API
boundary, the owner reconcile and the campaign projection all skipped - the assertions that matter
most were the ones never executed. This module builds the same *shape* of production state from
task-local bytes instead:

* the campaign's own batch layout under ``<evidence_root>/campaigns/<campaign>/<batch>/`` (journal,
  per-point documents, binding, result document), written by :mod:`campaign_batch_fixture` - the one
  writer this fixture and the projection tests share, so the bytes the production projection reads
  are the same bytes in both;
* the store rows that bind that batch to a campaign (manifest, consumed preflight receipt, first
  pass, retry queue) and one finished owner row;
* the six ``SO101_VALIDATION_*`` layout inputs as task-local files, with byte copies of the
  repository's v3 first-pass and macOS MPS v5 retry documents;
* a live control lease.

The whole composition is then assembled by the *real* ``create_production_service``, so the store,
supervisor and lease service the tests exercise are the production ones. Nothing here reads a fixed
host path, and nothing here substitutes a ``SimpleNamespace`` for a production authority: the one
boundary a caller may intercept is the supervisor's final ``_spawn``.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

from campaign_batch_fixture import CATALOG_SHA256, SELECTION_SHA256, write_campaign_batch
from so101_teleop.expert_validation.manifest_geometry import current_manifest_source_hash
from so101_teleop.expert_validation.models import (
    BatchBinding,
    CampaignBinding,
    PreflightReceipt,
)
from so101_teleop.expert_validation.production import (
    ProductionRuntimeLayout,
    create_production_service,
)
from so101_teleop.expert_validation.store import SupervisorStore
from so101_teleop.process_identity import (
    IDENTITY_EXITED,
    group_has_live_descendants,
    identity_state,
    read_identity,
)

#: The campaign this fixture builds. It is deliberately not a recorded id: nothing in the fixture
#: depends on a historical run, and a test that names a recorded campaign would fail here.
CAMPAIGN_ID = "campaign-retry-fixture"
BATCH_ID = "b0f1a"
MANIFEST_ID = "manifest-retry-fixture"
RECEIPT_ID = "receipt-retry-fixture"
#: The four anchors are not needed to reach the retry admission; two of them plus the genuinely
#: ``FAILED`` point keep the batch bytes minimal while staying a real selection.
POINT_IDS = ("task_start", "cup_test_forward_5cm", "sample_05_near_center")
#: The point the fixture's first pass really failed, and the one every retry case names.
POINT_ID = "sample_05_near_center"

#: The one hash this fixture owns: the preflight receipt's canonical start-request digest, which
#: nothing verifies against a document. The campaign's own binding hashes come from the shared batch
#: writer, so the bytes this fixture projects and the bytes the projection tests build come from one
#: implementation.
SOURCE_SHA256 = "a" * 64

#: The installed documents the two host branches of retry admission load, copied byte for byte
#: into ``tmp_path``. The restored first pass has no named profile and binds v3; a macOS retry
#: resolves its own MPS v5 document beside that configured file.
V3_PARALLEL_DOCUMENT = (
    Path(__file__).resolve().parents[3] / "so101_demo_py/config/mujoco/parallel_batch_v3.yaml"
)
MPS_RETRY_DOCUMENT = (
    Path(__file__).resolve().parents[3]
    / "so101_demo_py/config/mujoco/parallel_batch_v5_macos_mps_w1_retry.yaml"
)


@dataclass(frozen=True, slots=True)
class RetryProductionSession:
    """The composed production authorities one retry case needs, and where they live."""

    service: object
    store: SupervisorStore
    campaign_id: str
    batch_id: str
    point_id: str
    point_ids: tuple[str, ...]
    evidence_root: Path
    environment: dict
    authority: dict

    def close(self) -> None:
        self.store.close()

    @property
    def lease_body(self) -> dict:
        """The lease half of the console body: exactly what the page session holds."""

        lease = self.authority
        return {
            "service_session_id": lease["service_session_id"],
            "lease_id": lease["lease_id"],
            "lease_generation": lease["generation"],
        }


def campaign_batch_root(evidence_root: Path, *, campaign_id=CAMPAIGN_ID, batch_id=BATCH_ID) -> Path:
    return Path(evidence_root) / "campaigns" / campaign_id / batch_id


def manifest_document(*, point_ids=POINT_IDS) -> dict:
    """The stored selection document ``ProductionExpertValidationService._selection`` requires."""

    return {
        "catalog_id": "catalog-retry-fixture",
        "catalog_seed": 1,
        "catalog_sha256": CATALOG_SHA256,
        "selection_sha256": SELECTION_SHA256,
        "point_ids": list(point_ids),
        "points": [
            {
                "id": point_id,
                "display_id": f"P{index:02d}",
                "label": point_id.replace("_", " "),
                "source": "fixture",
                "stratum": "anchor" if index <= 2 else "near/center",
                "position_world_m": [-0.20 + 0.10 * index, -0.30, 0.05],
            }
            for index, point_id in enumerate(point_ids, start=1)
        ],
    }


def build_environment(root: Path) -> dict:
    """The production environment for this task root: six task-local layout inputs, nothing else.

    ``demo_prefix``/``demo_share`` still come from the ament index, while every file the runtime
    layout must find is written under ``root``. The v3 and MPS v5 documents are copied from the
    repository; the points catalog and adaptive config are written here.
    """

    configuration = (Path(root) / "task-config").resolve()
    configuration.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(V3_PARALLEL_DOCUMENT, configuration / "parallel_batch_v3.yaml")
    shutil.copyfile(MPS_RETRY_DOCUMENT, configuration / MPS_RETRY_DOCUMENT.name)
    (configuration / "points.yaml").write_text(
        "catalog_id: catalog-retry-fixture\npoints:\n"
        + "".join(f"  - id: {point_id}\n" for point_id in POINT_IDS)
    )
    (configuration / "adaptive.yaml").write_text("schema_version: 1\nmode: ADAPTIVE\n")
    for name in ("coordinator", "adaptive-cleanup", "adaptive-wrapper.zsh"):
        (configuration / name).write_text(f"# task-local {name} placeholder\n")
    environment = dict(os.environ)
    environment.update({
        "SO101_VALIDATION_POINTS": str(configuration / "points.yaml"),
        "SO101_VALIDATION_PARALLEL_CONFIG": str(configuration / "parallel_batch_v3.yaml"),
        "SO101_VALIDATION_ADAPTIVE_CONFIG": str(configuration / "adaptive.yaml"),
        "SO101_VALIDATION_COORDINATOR": str(configuration / "coordinator"),
        "SO101_VALIDATION_ADAPTIVE_CLEANUP": str(configuration / "adaptive-cleanup"),
        "SO101_VALIDATION_ADAPTIVE_WRAPPER": str(configuration / "adaptive-wrapper.zsh"),
    })
    return environment


def spawn_owner_process(argv=("-c", "import time; time.sleep(120)")) -> subprocess.Popen:
    """One real process that can play the live owner, in its own session."""

    return subprocess.Popen(
        [sys.executable, *argv],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def end_owner_process(process: subprocess.Popen, timeout: float = 5.0) -> None:
    if process.poll() is None:
        process.kill()
    process.wait(timeout=timeout)


def finished_owner_identity(*, attempts: int = 3):
    """The exact identity of a process that is *proven* gone, read from the kernel, not guessed.

    A recorded owner is retired only on the platform's own proof, so the fixture may not invent a
    pid: it spawns a real child, reads its identity, reaps it, and then verifies with the same
    predicate the store uses that the identity classifies ``EXITED`` and that its process group has
    no live descendant. Anything else would make the positive case pass or fail for the wrong
    reason.
    """

    for _ in range(attempts):
        process = spawn_owner_process()
        identity = read_identity(process.pid)
        end_owner_process(process)
        if identity_state(
            identity.pid, identity.start_marker, identity.command_sha256
        ) == IDENTITY_EXITED and not group_has_live_descendants(identity.pgid, identity.pid):
            return identity
    raise AssertionError("the fixture could not produce a provably finished owner identity")


def record_finished_owner(store: SupervisorStore, *, batch_id: str = BATCH_ID) -> tuple:
    """Record the owner row the recorded defect was about: ``RUNNING``, but really finished."""

    identity = finished_owner_identity()
    store.record_execution_owner_intent(SimpleNamespace(
        batch_id=batch_id,
        argv=("so101_parallel_batch", "--batch-id", batch_id),
        environment={},
    ))
    store.acknowledge_execution_owner(
        batch_id=batch_id,
        pid=identity.pid,
        pgid=identity.pgid,
        started_ticks=identity.start_marker,
    )
    return identity.pid, identity.pgid, identity.start_marker


def install_live_owner(store: SupervisorStore, *, batch_id: str = BATCH_ID) -> subprocess.Popen:
    """Rewrite the owner row to name a process that really is running right now.

    The caller owns the returned process and must end it. The whole identity is written - including
    the command fingerprint - because a row whose fingerprint no longer matches its process is
    *unknowable* rather than live, and this helper is for the live case.
    """

    process = spawn_owner_process()
    identity = read_identity(process.pid)
    store._connection.execute(
        "UPDATE owned_execution SET pid=?, pgid=?, started_ticks=?, argv_sha256=? "
        "WHERE batch_id=?",
        (identity.pid, identity.pgid, identity.start_marker, identity.command_sha256, batch_id),
    )
    return process


def build_retry_session(
    tmp_path,
    *,
    cleanup_complete=True,
    campaign_id: str = CAMPAIGN_ID,
    batch_id: str = BATCH_ID,
    point_id: str = POINT_ID,
    point_ids=POINT_IDS,
    manifest_id: str = MANIFEST_ID,
    receipt_id: str = RECEIPT_ID,
    session_id: str = "retry-fixture-session",
    owner_row: bool = True,
) -> RetryProductionSession:
    """Compose the whole production retry environment for one test inside ``tmp_path``.

    The order is the production order and cannot be reordered: the batch bytes and the store rows
    must exist *before* ``create_production_service`` runs, because that composition restores every
    durable campaign and projects its first-pass batch - which is what commits the canonical
    projection and the batch's own verified cleanup receipt. The lease is acquired afterwards, from
    the composed service, exactly as the console acquires one for a page session.
    """

    root = Path(tmp_path).resolve()
    environment = build_environment(root)
    if not point_ids or point_id not in point_ids:
        raise ValueError("the retry point must be one of the selected points")
    outcomes = {candidate: "PASSED" for candidate in point_ids}
    outcomes[point_id] = "FAILED"
    write_campaign_batch(
        root, outcomes, campaign_id=campaign_id, batch_id=batch_id,
        point_ids=tuple(point_ids), verdict="CAMPAIGN_INCOMPLETE",
        cleanup_complete=cleanup_complete,
    )

    layout = ProductionRuntimeLayout.discover(environment)
    store = SupervisorStore.open((root / "validation-service").resolve())
    try:
        store.record_manifest(
            manifest_id,
            manifest_document(point_ids=tuple(point_ids)),
            source_config_sha256=current_manifest_source_hash(layout),
            created_at_ns=1,
        )
        store.record_preflight_receipt(PreflightReceipt(
            receipt_id=receipt_id, campaign_id=campaign_id, manifest_id=manifest_id,
            canonical_start_request_sha256=SOURCE_SHA256,
            # Deliberately no ``execution_profile``: this fixture is the Linux composition, whose
            # retry admission takes the v3 branch the moment the restored request names no profile.
            receipt={"admitted": True},
            expires_at_monotonic_ns=10_000_000_000,
        ))
        store.consume_preflight_and_bind_campaign_batch(
            receipt_id, SOURCE_SHA256,
            CampaignBinding(
                campaign_id=campaign_id, manifest_id=manifest_id, executor_id="operator",
                operation_id="operation-fixture", executor_config_sha256=SOURCE_SHA256,
                execution_mode="SEQUENTIAL",
                execution_config={"worker_count": 1, "max_points_per_worker": 10},
                preflight_receipt_id=receipt_id,
            ),
            BatchBinding(
                batch_id=batch_id, campaign_id=campaign_id, batch_kind="FIRST_PASS",
                point_id=None,
                journal_root=campaign_batch_root(root, campaign_id=campaign_id,
                                                 batch_id=batch_id) / "journal",
                coordinator_epoch=1,
            ),
            now_monotonic_ns=1,
        )
        # The failed point is already queued, exactly as the console leaves it: the retry endpoint
        # only enqueues when the queue holds no live entry, and a queue that is really there is what
        # makes a request naming another point refuse instead of enqueueing it.
        store.enqueue_retries(campaign_id, (point_id,))
        if owner_row:
            record_finished_owner(store, batch_id=batch_id)
    finally:
        store.close()

    service = create_production_service(root, environment=environment)
    try:
        # The composition's own invariants, checked here so a broken fixture can never look
        # like a passing test: the restore really rebound this campaign, and the first-pass batch
        # was really projected into the durable canonical state the retry admission reads.
        restored = service.get_campaign(campaign_id)
        if restored["campaign_id"] != campaign_id:
            raise AssertionError(f"restore did not rebind {campaign_id}: {restored!r}")
        if service.store.read_projection_state(batch_id).state is None:
            raise AssertionError(f"the first pass {batch_id} was never projected")
        authority = service.acquire_lease({"service_session_id": session_id})
    except BaseException:
        service.store.close()
        raise
    return RetryProductionSession(
        service=service,
        store=service.store,
        campaign_id=campaign_id,
        batch_id=batch_id,
        point_id=point_id,
        point_ids=tuple(point_ids),
        evidence_root=root,
        environment=environment,
        authority=authority,
    )
