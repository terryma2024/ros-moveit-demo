"""The fixed and adaptive campaign projections and their cleanup records."""

from __future__ import annotations

from dataclasses import asdict, replace
import json
from pathlib import Path
from typing import Mapping

from so101_demo.parallel_batch.contracts import BatchSummary, ContractError, PointStatus, RunMode
from so101_teleop.expert_validation.adaptive_events import AdaptiveEventReader
from so101_teleop.expert_validation.campaign_layout import (
    CampaignLayoutReader,
    campaign_committed_attempt,
)
from so101_teleop.expert_validation.committed_artifacts import register_committed_attempt
from so101_teleop.expert_validation.coordinator_events import (
    AcceptedCoordinatorCursor,
    CampaignUpstreamBinding,
    CoordinatorEventReader,
    CoordinatorProjectionError,
    ReadOnlyCoordinatorJournal,
)
from so101_teleop.expert_validation.journal_layout import (
    CAMPAIGN_LAYOUT,
    resolve_fixed_journal_layout,
)
from so101_teleop.expert_validation.models import UpstreamCursor
from so101_teleop.expert_validation.process_owner import (
    CoordinatorOwnershipError,
)
from so101_teleop.expert_validation.production_service.guard import (
    COORDINATOR_EXITED_NON_TERMINAL,
    _verified_cleanup_receipt_sha256,
)
from so101_teleop.expert_validation.reducer import CanonicalCampaignReducer
from so101_teleop.expert_validation.service import ServiceConflict
from so101_teleop.expert_validation.statistics import (
    BrokerProjection,
    PointProjection,
    StatisticsProjectionError,
    WorkerProjection,
    retry_history_document,
    retry_history_entry,
    summarize_first_pass,
)
from so101_teleop.expert_validation.supervisor_store.schema import StoreConflict


class CampaignProjection:
    def _with_retry_history(self, campaign_id, projection):
        """Append the durable retry history. It is a read: nothing above it is recomputed."""

        admissions = getattr(self.store, "retry_admissions", None)
        if admissions is None:
            # A read-only cursor double keeps no admission table; it has no history to append.
            return projection
        rows = tuple(admissions(campaign_id))
        if not rows:
            # No retry has ever been admitted: the projection is returned unchanged, so a cached
            # campaign keeps its identity.
            return projection
        history = tuple(
            retry_history_document(
                retry_history_entry({
                    **row,
                    "cleanup_receipt_sha256": getattr(
                        self.store.batch(row["batch_id"]), "cleanup_receipt_sha256", None
                    ),
                })
            )
            for row in rows
        )
        return {**projection, "retry_history": history}

    def _campaign_projection(self, campaign_id):
        try:
            cached = self._campaigns[campaign_id]
        except KeyError as error:
            raise ServiceConflict("VALIDATION_CAMPAIGN_NOT_FOUND") from error
        request = self._campaign_requests.get(campaign_id)
        if request is None:
            return self._with_recovery_fence(campaign_id, cached)
        if request.execution_mode == "ADAPTIVE":
            try:
                projection = self._adaptive_campaign_projection(request)
            except CoordinatorProjectionError as error:
                if str(error) == "JOURNAL_REPLAY_INCOMPLETE":
                    return self._with_recovery_fence(campaign_id, cached)
                raise ServiceConflict("UPSTREAM_PROJECTION_INVALID") from error
            if projection is None:
                return self._with_recovery_fence(campaign_id, cached)
            projection = self._with_recovery_fence(campaign_id, projection)
            self._campaigns[campaign_id] = projection
            return projection
        try:
            projection = self._fixed_campaign_projection(request)
        except (CoordinatorProjectionError, ContractError, StatisticsProjectionError) as error:
            if str(error) == "JOURNAL_REPLAY_INCOMPLETE":
                return self._with_recovery_fence(campaign_id, cached)
            raise ServiceConflict("UPSTREAM_PROJECTION_INVALID") from error
        if projection is None:
            return self._with_recovery_fence(campaign_id, cached)
        projection = self._with_recovery_fence(campaign_id, projection)
        self._campaigns[campaign_id] = projection
        return projection

    def _owner_exited(self, request) -> bool:
        """True when the process this service owns for the batch is dead with nothing left running in its group.

        Read before the journal so that every event the owner wrote before it exited is part of the same
        projection: a coordinator that committed its terminal event and then exited is terminal, not exited.
        An absent or foreign owner proves nothing (a restarted service reconnects before it projects).
        """
        owner = getattr(getattr(self, "supervisor", None), "process_owner", None)
        active = getattr(owner, "active_execution", None)
        if (
            active is None
            or getattr(active, "campaign_id", None) != request.campaign_id
            or getattr(active, "batch_id", None) != request.batch_id
        ):
            return False
        try:
            status = owner.poll(active)
        except CoordinatorOwnershipError:
            return False
        return status.running is False and status.descendants_alive is False

    def _with_recovery_fence(self, campaign_id, projection):
        # Web admission state must not rewrite upstream outcomes or receipts.
        if self.store.recovery_fence(campaign_id) is not None:
            return {**projection, "status": "NEEDS_OPERATOR_RECOVERY"}
        return projection

    def _fixed_campaign_projection(self, request):
        batch_root = (
            Path(request.evidence_root)
            / "campaigns"
            / request.campaign_id
            / request.batch_id
        ).resolve()
        try:
            layout = resolve_fixed_journal_layout(batch_root, request.batch_id)
        except CoordinatorProjectionError as error:
            if str(error) == "JOURNAL_NOT_PRESENT":
                # The one typed outcome that means "this batch has not published a journal yet":
                # a batch still starting keeps its cached projection, exactly as a missing epoch
                # document did before. Every other code is a refusal, never a silent pick.
                return None
            raise
        journal_root = layout.journal_root
        binding = CampaignUpstreamBinding(
            campaign_id=request.campaign_id,
            batch_id=request.batch_id,
            owner_kind="COORDINATOR",
            owner_epoch_or_generation=layout.epoch,
            journal_root=journal_root,
            batch_root=batch_root,
        )
        owner_exited = self._owner_exited(request)
        journal = ReadOnlyCoordinatorJournal(journal_root, request.batch_id)
        if layout.layout == CAMPAIGN_LAYOUT:
            # The macOS campaign journal: the same verification, its own committed payload schema.
            reader = CampaignLayoutReader(journal, binding)
            persist_reducer = CanonicalCampaignReducer(identity_required=False)
        else:
            reader = CoordinatorEventReader(journal, binding)
            persist_reducer = None
        batch = reader.read_after(AcceptedCoordinatorCursor.initial(binding))
        if not batch.events:
            return None
        # The canonical durable projection is committed before it is read back: a retry admission
        # validates the original point's business result against exactly this state, never against
        # a value this request happened to compute.
        self._persist_canonical_projection(request, batch, reducer=persist_reducer)
        state = batch.projected_state
        raw_points = state.get("points")
        if not isinstance(raw_points, Mapping):
            raise CoordinatorProjectionError("POINT_PROJECTION_INVALID")
        selected = tuple(request.selection.point_ids)
        # A canonical projection only carries points that already produced an event. A selected
        # point with no event at all is UNRUN; any point outside the selection is a real defect.
        if set(raw_points) - set(selected):
            raise CoordinatorProjectionError("POINT_PROJECTION_INVALID")
        raw_workers = state.get("workers", {})
        if not isinstance(raw_workers, Mapping):
            raise CoordinatorProjectionError("WORKER_PROJECTION_INVALID")
        active_by_point = {}
        for worker_id, raw_worker in raw_workers.items():
            if not isinstance(worker_id, str) or not isinstance(raw_worker, Mapping):
                raise CoordinatorProjectionError("WORKER_PROJECTION_INVALID")
            lease = raw_worker.get("lease")
            if lease is not None:
                if not isinstance(lease, Mapping):
                    raise CoordinatorProjectionError("WORKER_PROJECTION_INVALID")
                point_id = lease.get("point_id")
                attempt_id = lease.get("attempt_id")
                if (
                    point_id not in selected
                    or not isinstance(attempt_id, str)
                    or point_id in active_by_point
                ):
                    raise CoordinatorProjectionError("WORKER_PROJECTION_INVALID")
                active_by_point[point_id] = (attempt_id, worker_id)
        execution_started_ids = set()
        for event in batch.events:
            if event.type != "ATTEMPT_STARTED":
                continue
            identity = event.payload.get("identity")
            identity = identity if isinstance(identity, Mapping) else event.payload
            if identity.get("point_id") not in selected:
                raise CoordinatorProjectionError("ATTEMPT_PROJECTION_INVALID")
            execution_started_ids.add(identity["point_id"])
        display_ids = {point.id: point.display_id for point in request.selection.points}
        evidence_by_point = {point_id: [] for point_id in selected}
        committed_identities = set()
        for event in batch.events:
            if event.type != "RESULT_COMMITTED":
                continue
            if layout.layout == CAMPAIGN_LAYOUT:
                # The campaign layout has no sealed attempt manifest to import; its result was
                # verified against the journal's own terminal and the batch's per-point document,
                # and no artifact is registered for it.
                evidence = campaign_committed_attempt(event, binding)
            else:
                if not isinstance(event.payload.get("identity"), Mapping):
                    # A canonical result event must still reference the sealed attempt it commits:
                    # the import is authorized by that reference, never by a flat outcome field.
                    raise CoordinatorProjectionError("RESULT_REFERENCE_INVALID")
                evidence = register_committed_attempt(event, binding, selected, self.artifacts)
            if evidence.identity in committed_identities:
                raise CoordinatorProjectionError("DUPLICATE_COMMITTED_ATTEMPT")
            committed_identities.add(evidence.identity)
            evidence_by_point[evidence.identity.point_id].append(evidence)
        points = []
        point_statuses = {}
        unrun_point: dict[str, object] = {"status": "UNRUN", "attempts": 0, "terminal": False}
        for point_id in selected:
            raw_point = raw_points.get(point_id, unrun_point)
            if not isinstance(raw_point, Mapping):
                raise CoordinatorProjectionError("POINT_PROJECTION_INVALID")
            try:
                status = PointStatus(raw_point["status"])
            except (KeyError, TypeError, ValueError) as error:
                raise CoordinatorProjectionError("POINT_PROJECTION_INVALID") from error
            attempts = raw_point.get("attempts", 0)
            if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
                raise CoordinatorProjectionError("POINT_PROJECTION_INVALID")
            if not isinstance(raw_point.get("terminal", False), bool):
                raise CoordinatorProjectionError("POINT_PROJECTION_INVALID")
            active_attempt = raw_point.get("active_attempt")
            active_worker_id = None
            if active_attempt is not None:
                active_lease = active_by_point.get(point_id)
                if (
                    not isinstance(active_attempt, str)
                    or active_lease is None
                    or active_lease[0] != active_attempt
                ):
                    raise CoordinatorProjectionError("POINT_PROJECTION_INVALID")
                active_worker_id = active_lease[1]
            elif point_id in active_by_point:
                raise CoordinatorProjectionError("POINT_PROJECTION_INVALID")
            reason = raw_point.get("blocked_by")
            if reason is not None and not isinstance(reason, str):
                raise CoordinatorProjectionError("POINT_PROJECTION_INVALID")
            point_statuses[point_id] = status
            points.append(
                PointProjection(
                    point_id=point_id,
                    status=status,
                    evaluated=status in {PointStatus.PASSED, PointStatus.FAILED},
                    execution_started=point_id in execution_started_ids,
                    active_worker_id=active_worker_id,
                    reason=reason,
                )
            )

        workers = []
        for worker_id, raw_worker in sorted(raw_workers.items()):
            if not isinstance(worker_id, str) or not isinstance(raw_worker, Mapping):
                raise CoordinatorProjectionError("WORKER_PROJECTION_INVALID")
            lease = raw_worker.get("lease")
            if lease is not None and not isinstance(lease, Mapping):
                raise CoordinatorProjectionError("WORKER_PROJECTION_INVALID")
            generation = raw_worker.get("generation", 1)
            lease_count = raw_worker.get("lease_count", 0)
            worker_state = raw_worker.get("state", "ACTIVE")
            if (
                type(generation) is not int or generation <= 0
                or type(lease_count) is not int or lease_count < 0
                or not isinstance(worker_state, str) or not worker_state
            ):
                raise CoordinatorProjectionError("WORKER_PROJECTION_INVALID")
            workers.append(
                WorkerProjection(
                    worker_id=worker_id,
                    generation=generation,
                    state=worker_state,
                    active_point_id=lease.get("point_id") if lease is not None else None,
                    lease_count=lease_count,
                    quarantine_reason=raw_worker.get("quarantine_reason"),
                    recovery_result=raw_worker.get("recovery_result"),
                )
            )

        terminal_reason = state.get("terminal_reason")
        if terminal_reason is not None and not isinstance(terminal_reason, str):
            raise CoordinatorProjectionError("BATCH_PROJECTION_INVALID")
        terminal = terminal_reason is not None and (
            all(
                raw_points.get(point_id, unrun_point).get("terminal", False)
                for point_id in selected
            )
            or (
                state.get("batch_infrastructure_terminal") is not None
                and not active_by_point
            )
        )
        cleanup_complete = state.get("batch_cleanup_complete", False)
        if not isinstance(cleanup_complete, bool):
            raise CoordinatorProjectionError("BATCH_PROJECTION_INVALID")
        owner_lost = owner_exited and not terminal
        if owner_lost:
            # The owned coordinator is gone without a terminal event: nothing will ever advance this batch, so it is
            # terminal for every consumer. Its journal leases are stale, and cleanup is complete only when the
            # batch's own verified cleanup event exists.
            terminal = True
            terminal_reason = terminal_reason or COORDINATOR_EXITED_NON_TERMINAL
            cleanup_complete = cleanup_complete or _verified_cleanup_receipt_sha256(batch) is not None
            points = [replace(point, active_worker_id=None) for point in points]
            workers = [replace(worker, active_point_id=None) for worker in workers]
        if terminal and cleanup_complete:
            # A first pass runs for its whole campaign inside the coordinator, so the supervisor's
            # spawn-result receipt (``start_first_pass``) never sees it. The batch's own verified
            # journal is the only authority for this receipt: without it ``admit_retry`` refuses
            # the original with ``RETRY_ORIGINAL_CLEANUP_INCOMPLETE`` while this very projection
            # reports cleanup complete.
            self._record_verified_batch_cleanup(request, batch)
        summary = BatchSummary(
            run_mode=RunMode.EXECUTE,
            point_statuses=point_statuses,
            batch_terminal=terminal,
            batch_cleanup_complete=cleanup_complete,
            terminal_reason=terminal_reason,
        )
        broker_healthy = state.get("broker_healthy", True)
        broker_failed = state.get("broker_recovery_failed", False)
        if not isinstance(broker_healthy, bool) or not isinstance(broker_failed, bool):
            raise CoordinatorProjectionError("BROKER_PROJECTION_INVALID")
        statistics = summarize_first_pass(
            summary,
            points,
            workers=workers,
            broker=BrokerProjection(
                available=broker_healthy and not broker_failed,
                reason="BROKER_RECOVERY_FAILED" if broker_failed else None,
            ),
        )
        if terminal_reason == "WEB_CANCEL_REQUESTED":
            status = "CANCELLED" if terminal and cleanup_complete else "CANCELLING"
        elif owner_lost:
            status = "INFRA_FAILED" if cleanup_complete else "CLEANING_UP"
        elif terminal and cleanup_complete and statistics.qualification_passed:
            status = "COMPLETED"
        elif terminal and cleanup_complete and statistics.valid_failed:
            status = "COMPLETED_WITH_FAILURES"
        elif terminal and cleanup_complete:
            status = "INFRA_FAILED"
        elif terminal:
            status = "CLEANING_UP"
        else:
            status = "RUNNING"
        final_event = batch.events[-1]
        self.store.accept_upstream_cursor(
            UpstreamCursor(
                batch_id=request.batch_id,
                owner_kind="COORDINATOR",
                owner_epoch_or_generation=final_event.owner_epoch,
                segment_id=f"segment-{final_event.owner_epoch:020d}",
                event_id=f"event-{final_event.sequence:020d}",
                frame_sha256=final_event.frame_sha256,
            )
        )
        projected_points = tuple(
            {
                "point_id": point.point_id,
                "display_id": display_ids[point.point_id],
                "status": point.status.value,
                "retry_eligible": point.retry_eligible,
                "active_worker_id": point.active_worker_id,
                "reason": point.reason,
                "attempts": tuple(
                    {"generation": evidence.identity.lease_generation,
                     "attempt_id": evidence.identity.attempt_id,
                     "worker_id": evidence.identity.worker_id,
                     "worker_generation": evidence.identity.worker_generation,
                     "batch_id": evidence.identity.batch_id, "kind": "FIRST_PASS",
                     "status": evidence.status}
                    for evidence in evidence_by_point[point.point_id]
                ),
                "artifact_ids": tuple(
                    artifact.artifact_id for evidence in evidence_by_point[point.point_id]
                    for artifact in evidence.artifacts
                ),
                "artifacts": tuple(
                    asdict(artifact) for evidence in evidence_by_point[point.point_id]
                    for artifact in evidence.artifacts
                ),
            }
            for point in statistics.points
        )
        projected_workers = tuple(
            {
                "worker_id": worker.worker_id,
                "generation": worker.generation,
                "state": worker.state,
                "current_point_id": worker.active_point_id,
                "lease_count": worker.lease_count,
                "recovery_result": worker.recovery_result,
                "quarantine_reason": worker.quarantine_reason,
            }
            for worker in statistics.workers
        )
        return {
            "campaign_id": request.campaign_id,
            "manifest_id": request.manifest_id,
            "sequence": batch.next_cursor.sequence,
            "execution_mode": request.execution_mode,
            "owner_kind": "COORDINATOR",
            "batch_id": request.batch_id,
            "status": status,
            "points": projected_points,
            "workers": projected_workers,
            "broker": asdict(statistics.broker),
            "requested": statistics.requested,
            "evaluated": statistics.evaluated,
            "execution_started": statistics.execution_started,
            "valid_succeeded": statistics.valid_succeeded,
            "valid_failed": statistics.valid_failed,
            "indeterminate": statistics.indeterminate,
            "not_executed": statistics.not_executed,
            "evaluation_coverage": statistics.evaluation_coverage,
            "execution_coverage": statistics.execution_coverage,
            "qualified_success_rate": statistics.qualified_success_rate,
            "coverage_complete": statistics.coverage_complete,
            "execution_complete": statistics.execution_complete,
            "batch_cleanup_complete": statistics.batch_cleanup_complete,
            "qualification_passed": statistics.qualification_passed,
            **({"terminal_reason": terminal_reason} if owner_lost else {}),
        }

    def _record_verified_batch_cleanup(self, request, batch) -> None:
        """Record the cleanup receipt a terminal-clean batch's own verified bytes prove.

        Two things are deliberately never done here: no receipt is derived from anything but the
        verified ``CLEANUP_COMMITTED`` frame of this batch, and an existing durable receipt is never
        replaced. A batch whose bytes show no committed cleanup leaves the column NULL, so the retry
        admission keeps refusing ``RETRY_ORIGINAL_CLEANUP_INCOMPLETE`` exactly as it did.
        """

        record = getattr(self.store, "record_batch_cleanup", None)
        read = getattr(self.store, "batch", None)
        if record is None or read is None:
            # A read-only cursor double keeps no batch table; it has no receipt to record.
            return
        receipt_sha256 = _verified_cleanup_receipt_sha256(batch)
        if receipt_sha256 is None:
            return
        durable = read(request.batch_id)
        if durable is None or durable.cleanup_receipt_sha256 is not None:
            # No durable batch to bind the receipt to, or one already committed: a read never
            # rewrites a receipt another verification recorded.
            return
        record(request.batch_id, receipt_sha256)

    def _persist_canonical_projection(self, request, batch, *, reducer=None) -> None:
        """Commit the verified canonical prefix, its attempts and its cursor in one transaction.

        A journal that carries no canonical frame at all (a v1-v3 delta journal) has no canonical
        state to persist and is left exactly as it was: the durable reducer state exists only for
        the campaigns whose events the canonical reducer defines. ``reducer`` is the one the
        projection already reduced these events with, so the committed state and the projected
        state can never disagree.
        """

        from so101_teleop.expert_validation.reducer import CanonicalCampaignReducer, ReducerError

        accept = getattr(self.store, "accept_projection_batch", None)
        if accept is None or not batch.events:
            # A read-only cursor double has no projection table to commit into.
            return
        if reducer is None:
            reducer = CanonicalCampaignReducer()
        final = batch.events[-1]
        next_cursor = UpstreamCursor(
            batch_id=request.batch_id,
            owner_kind="COORDINATOR",
            owner_epoch_or_generation=final.owner_epoch,
            segment_id=f"segment-{final.owner_epoch:020d}",
            event_id=f"event-{final.sequence:020d}",
            frame_sha256=final.frame_sha256,
        )
        snapshot = self.store.read_projection_state(request.batch_id)
        try:
            accept(
                batch_id=request.batch_id,
                expected_cursor=snapshot.cursor,
                events=batch.events,
                next_cursor=next_cursor,
                reducer=reducer,
            )
        except ReducerError as error:
            if error.code == "REDUCER_STATE_REQUIRED":
                return
            raise CoordinatorProjectionError("PROJECTION_PERSIST_FAILED") from error
        except (StoreConflict, ValueError) as error:
            raise CoordinatorProjectionError("PROJECTION_PERSIST_FAILED") from error

    def _adaptive_campaign_projection(self, request):
        """Project the adaptive Runner journal; never the nested pool journals."""
        batch_root = (
            Path(request.evidence_root)
            / "campaigns"
            / request.campaign_id
            / request.batch_id
        ).resolve()
        journal_root = batch_root / "r" / request.batch_id / "journal"
        epoch_path = journal_root / "coordinator_epoch.json"
        if epoch_path.is_symlink():
            raise CoordinatorProjectionError("OWNER_EPOCH_INVALID")
        if not epoch_path.exists():
            return None
        if not epoch_path.is_file():
            raise CoordinatorProjectionError("OWNER_EPOCH_INVALID")
        try:
            epoch_document = json.loads(epoch_path.read_text(encoding="utf-8"))
            epoch = epoch_document["coordinator_epoch"]
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise CoordinatorProjectionError("OWNER_EPOCH_INVALID") from error
        if (
            epoch_document.get("batch_id") != request.batch_id
            or isinstance(epoch, bool)
            or not isinstance(epoch, int)
            or epoch <= 0
        ):
            raise CoordinatorProjectionError("OWNER_EPOCH_INVALID")
        binding = CampaignUpstreamBinding(
            campaign_id=request.campaign_id,
            batch_id=request.batch_id,
            owner_kind="ADAPTIVE_RUNNER",
            owner_epoch_or_generation=epoch,
            journal_root=journal_root,
            batch_root=batch_root,
        )
        owner_exited = self._owner_exited(request)
        reader = AdaptiveEventReader(
            ReadOnlyCoordinatorJournal(journal_root, request.batch_id),
            binding,
        )
        batch = reader.read_after(AcceptedCoordinatorCursor.initial(binding))
        if not batch.events:
            return None
        view = batch.projection
        selected = tuple(request.selection.point_ids)
        display_ids = {point.id: point.display_id for point in request.selection.points}
        projected_points = []
        succeeded = failed = indeterminate = 0
        for point_id in selected:
            point_view = view.points.get(point_id)
            point_status = point_view.status if point_view is not None else "UNRUN"
            if point_status == "PASSED":
                succeeded += 1
            elif point_status == "FAILED":
                failed += 1
            elif point_status not in {"UNRUN"}:
                indeterminate += 1
            projected_points.append({
                "point_id": point_id,
                "display_id": display_ids[point_id],
                "status": point_status,
                "retry_eligible": point_status == "FAILED",
                "active_worker_id": None,
                "reason": None,
                "attempts": (),
                "artifact_ids": (),
                "artifacts": (),
            })
        terminal_status = view.terminal_status
        cleanup_complete = view.cleanup_complete is True
        owner_lost = owner_exited and terminal_status is None
        if owner_lost:
            # The wrapper is gone and its runner wrote no terminal event: nothing will advance this batch.
            status = "INFRA_FAILED" if cleanup_complete else "CLEANING_UP"
        elif terminal_status is None:
            status = "RUNNING"
        elif not cleanup_complete:
            status = "CLEANING_UP"
        else:
            # The Runner's terminal vocabulary is already the campaign one.
            status = terminal_status
        requested = len(selected)
        evaluated = succeeded + failed
        final_event = batch.events[-1]
        self.store.accept_upstream_cursor(
            UpstreamCursor(
                batch_id=request.batch_id,
                owner_kind="ADAPTIVE_RUNNER",
                owner_epoch_or_generation=final_event.owner_epoch,
                segment_id=f"segment-{final_event.owner_epoch:020d}",
                event_id=f"event-{final_event.sequence:020d}",
                frame_sha256=final_event.frame_sha256,
            )
        )
        return {
            "campaign_id": request.campaign_id,
            "manifest_id": request.manifest_id,
            "sequence": batch.next_cursor.sequence,
            "execution_mode": request.execution_mode,
            "owner_kind": "ADAPTIVE_WRAPPER",
            "batch_id": request.batch_id,
            "status": status,
            "points": tuple(projected_points),
            "workers": (),
            "broker": None,
            "requested": requested,
            "evaluated": evaluated,
            "execution_started": evaluated + indeterminate,
            "valid_succeeded": succeeded,
            "valid_failed": failed,
            "indeterminate": indeterminate,
            "not_executed": requested - evaluated - indeterminate,
            "evaluation_coverage": evaluated / requested if requested else 0.0,
            "execution_coverage": (
                (evaluated + indeterminate) / requested if requested else 0.0
            ),
            "qualified_success_rate": (
                succeeded / evaluated if evaluated else None
            ),
            "coverage_complete": (terminal_status is not None or owner_lost) and evaluated == requested,
            "execution_complete": terminal_status is not None or owner_lost,
            "batch_cleanup_complete": cleanup_complete,
            "qualification_passed": (
                terminal_status == "COMPLETED" if terminal_status is not None
                else False if owner_lost else None
            ),
            "levels_used": view.levels_used,
            "fallback_history": tuple(
                {
                    "generation": fallback.generation,
                    "from_count": fallback.from_count,
                    "to_count": fallback.to_count,
                    "reason": fallback.reason,
                    "transition": fallback.transition,
                }
                for fallback in view.fallbacks
            ),
            "current_generation": view.current_generation,
            "infra_attempts": sum(
                point.infra_attempts for point in view.points.values()
            ),
            **({"terminal_reason": COORDINATOR_EXITED_NON_TERMINAL} if owner_lost else {}),
        }
