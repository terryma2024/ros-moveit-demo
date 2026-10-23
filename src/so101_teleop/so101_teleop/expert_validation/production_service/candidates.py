"""Candidate context issuance and the candidate first pass."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace
import uuid

from so101_teleop.expert_validation.execution_context import (
    CandidateExecutionContext,
    candidate_run_command_id,
    install_binding_sha256,
    runtime_closure_sha256,
)
from so101_teleop.expert_validation.preflight import (
    CampaignStartRequest,
)
from so101_teleop.expert_validation.production_service.layout import (
    _issuance_request_sha256,
    _sha256,
)
from so101_teleop.expert_validation.service import ServiceConflict


class CandidateFirstPass:
    def issue_candidate_context(
        self,
        *,
        task_id,
        dispatch_id,
        campaign_id,
        batch_id,
        manifest_id,
        execution_profile,
        command_id,
        worker_count=None,
        batch_kind=None,
        config_document=None,
        owner_generation=1,
        max_runs=1,
        evidence_root=None,
        expires_in_s=3600.0,
    ) -> CandidateExecutionContext:
        """Issue one bounded candidate run from the installed document the profile names.

        The row the profile names decides the shape: the caller states the worker count, batch kind
        and config document explicitly, and a combination outside the macOS matrix, or a document
        that is not the installed one for that profile, is refused by name. The context binds the
        runtime closure of the run it authorizes - for a first pass the request the start endpoint
        will build, for a retry the campaign it retries - and the copied install that closure covers.
        Issuance itself is one-time: the caller's command id is consumed durably, so a replay and a
        reuse are both refused, and nothing is issued while an owner is unresolved.
        """

        installed = self._installed_profile_document(execution_profile)
        row = installed.profile
        if (
            config_document is not None
            and Path(config_document).resolve() != Path(installed.path).resolve()
        ):
            raise ServiceConflict("CONTEXT_CONFIG_DOCUMENT_MISMATCH")
        requested_workers = row.worker_count if worker_count is None else worker_count
        requested_kind = row.batch_kind if batch_kind is None else batch_kind
        if requested_workers != row.worker_count or requested_kind != row.batch_kind:
            raise ServiceConflict(
                f"CONTEXT_PROFILE_INVALID: {row.profile}/{installed.schema_version}"
            )
        root = Path(evidence_root) if evidence_root is not None else self.store.root.parent
        probe = SimpleNamespace(
            task_id=task_id,
            dispatch_id=dispatch_id,
            campaign_id=campaign_id,
            batch_id=batch_id,
            manifest_id=manifest_id,
            execution_profile=row.profile,
            schema_version=installed.schema_version,
            batch_kind=requested_kind,
            worker_count=requested_workers,
            evidence_root=root,
            owner_generation=owner_generation,
        )
        if requested_kind == "FIRST_PASS":
            runtime_closure = runtime_closure_sha256(self._candidate_first_pass_request(probe))
        else:
            original = self._campaign_requests.get(campaign_id)
            if original is None:
                # A retry executes an existing campaign: without its durable request there is no
                # runtime closure to bind, so nothing is issued.
                raise ServiceConflict("CONTEXT_CAMPAIGN_UNKNOWN")
            runtime_closure = runtime_closure_sha256(original)
        now = time.monotonic_ns()
        context = CandidateExecutionContext(
            context_id="candidate-" + uuid.uuid4().hex,
            task_id=task_id,
            dispatch_id=dispatch_id,
            campaign_id=campaign_id,
            batch_id=batch_id,
            manifest_id=manifest_id,
            execution_profile=row.profile,
            schema_version=installed.schema_version,
            batch_kind=requested_kind,
            worker_count=requested_workers,
            config_sha256=installed.config_sha256,
            runtime_closure_sha256=runtime_closure,
            evidence_root=root,
            owner_generation=owner_generation,
            command_id=candidate_run_command_id(command_id),
            issued_at_monotonic_ns=now,
            expires_at_monotonic_ns=now + int(expires_in_s * 1_000_000_000),
            max_runs=max_runs,
        )
        self.store.admit_candidate_context_issuance(
            command_id=command_id,
            request_sha256=_issuance_request_sha256(
                task_id=task_id,
                dispatch_id=dispatch_id,
                campaign_id=campaign_id,
                batch_id=batch_id,
                manifest_id=manifest_id,
                execution_profile=row.profile,
                schema_version=installed.schema_version,
                batch_kind=requested_kind,
                worker_count=requested_workers,
                config_sha256=installed.config_sha256,
                runtime_closure_sha256=runtime_closure,
                evidence_root=root,
                owner_generation=owner_generation,
                max_runs=max_runs,
            ),
            context_id=context.context_id,
            campaign_id=campaign_id,
            document=context.as_document(),
        )
        return self.register_candidate_context(context)

    def candidate_context_response(self, context: CandidateExecutionContext) -> dict:
        """The issued context, plus the copied install the runtime closure is bound to."""

        document = super().candidate_context_response(context)
        document.update(
            config_document=str(self._installed_profile_document(context.execution_profile).path),
            install_prefix=str(self.layout.demo_prefix),
            install_binding_sha256=install_binding_sha256(
                install_prefix=self.layout.demo_prefix,
                runtime_closure_sha256=context.runtime_closure_sha256,
            ),
        )
        return document

    def _candidate_first_pass_request(self, context) -> CampaignStartRequest:
        """The one first-pass request a candidate context authorizes.

        Every coordinate comes from the context and the installed document it names, so issuance can
        bind the runtime closure of *this* request before it exists as a run, and the start endpoint
        rebuilds exactly the same bytes instead of accepting a caller's restatement. A context whose
        row is not a first-pass row never reaches this builder.
        """

        installed = self._installed_profile_document(context.execution_profile)
        row = installed.profile
        if (
            row is None
            or row.batch_kind != "FIRST_PASS"
            or row.worker_count != context.worker_count
            or row.batch_kind != context.batch_kind
        ):
            raise ServiceConflict(
                f"CONTEXT_PROFILE_INVALID: {context.execution_profile}/{context.schema_version}"
            )
        resource_document = json.dumps(
            {"mode": row.execution_mode, "worker_count": context.worker_count}, sort_keys=True
        ).encode("utf-8")
        environment = {}
        if self.layout.provenance_binding is not None:
            environment["SO101_PARALLEL_PROVENANCE_BINDING"] = str(
                self.layout.provenance_binding
            )
        return CampaignStartRequest(
            campaign_id=context.campaign_id,
            batch_id=context.batch_id,
            manifest_id=context.manifest_id,
            selection=self._selection(context.manifest_id),
            execution_mode=row.execution_mode,
            evidence_root=context.evidence_root,
            points_path=self.layout.points_path,
            parallel_config_path=installed.path,
            adaptive_config_path=self.layout.adaptive_config_path,
            worker_count=context.worker_count,
            max_points_per_worker=None,
            fallback_worker_counts=(6, 4, 2, 1),
            initial_points_per_worker=3,
            worker_start_timeout_s=120.0,
            max_infra_attempts_per_point=5,
            yolo_executor_count=2,
            service_session_id=f"candidate:{context.task_id}:{context.dispatch_id}",
            lease_generation=context.owner_generation,
            source_commit=self.layout.source_commit,
            install_prefix=str(self.layout.demo_prefix),
            coordinator_executable_sha256=_sha256(self.layout.coordinator_executable),
            adaptive_runner_module_sha256=_sha256(
                Path(__import__("so101_demo.parallel_batch.adaptive_runner", fromlist=["x"]).__file__)
            ),
            adaptive_pool_module_sha256=_sha256(
                Path(__import__("so101_demo.parallel_batch.adaptive_pool", fromlist=["x"]).__file__)
            ),
            adaptive_cleanup_executable_sha256=_sha256(self.layout.cleanup_executable),
            adaptive_wrapper_sha256=_sha256(self.layout.adaptive_wrapper),
            parallel_config_sha256=installed.config_sha256,
            adaptive_config_sha256=_sha256(self.layout.adaptive_config_path),
            yolo_weights_sha256=self.layout.yolo_weights_sha256,
            grounded_sam_manifest_sha256=self.layout.grounded_manifest_sha256,
            broker_image_id=self.layout.broker_image_id,
            resource_manifest_sha256=hashlib.sha256(resource_document).hexdigest(),
            execution_profile=context.execution_profile,
            batch_kind=context.batch_kind,
            yolo_weights_path=self.layout.yolo_weights_path or Path("/models/yolo.pt"),
            grounded_root=self.layout.grounded_root or Path("/models/grounded"),
            coordinator_executable_path=self.layout.coordinator_executable,
            adaptive_wrapper_path=self.layout.adaptive_wrapper,
            provenance_binding_path=self.layout.provenance_binding,
            environment=environment,
        )

    async def candidate_first_pass(self, context, body):
        """The candidate first-pass endpoint: one issued context, one bounded, admitted run."""

        if not isinstance(context, CandidateExecutionContext):
            raise ServiceConflict("CANDIDATE_CONTEXT_REQUIRED")
        if context.batch_kind != "FIRST_PASS":
            raise ServiceConflict("CANDIDATE_FIRST_PASS_CONTEXT_REQUIRED")
        request = self._candidate_first_pass_request(context)
        # The shared startup guard still decides: a candidate run is admitted by the same fresh
        # observation as any other start, and a refusal is returned before any process exists.
        receipt = self.supervisor.preflight_engine.preflight(request)
        if not receipt.admitted:
            raise ServiceConflict("START_GUARD_REFUSED:" + ",".join(receipt.reason_codes))
        result = await self.supervisor.start_candidate_first_pass(
            request=request, context=context, receipt=receipt
        )
        self._campaign_requests[context.campaign_id] = request
        self._campaigns[context.campaign_id] = {
            "campaign_id": context.campaign_id,
            "manifest_id": context.manifest_id,
            "sequence": 1,
            "execution_mode": request.execution_mode,
            "owner_kind": (
                "ADAPTIVE_WRAPPER" if request.execution_mode == "ADAPTIVE" else "COORDINATOR"
            ),
            "batch_id": context.batch_id,
            "status": "STARTED",
            "points": tuple(
                {"point_id": point_id, "status": "UNRUN"}
                for point_id in request.selection.point_ids
            ),
        }
        return result
