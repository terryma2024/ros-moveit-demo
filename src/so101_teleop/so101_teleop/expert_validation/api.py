"""Dedicated FastAPI surface for expert-validation campaigns."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
import inspect
import json
import logging
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

from .preflight import FIXED_WORKER_COUNTS, MACOS_EXECUTION_PROFILES
from so101_teleop.api import validate_bind_address
from so101_teleop.task_artifacts import ArtifactAccessError


#: The one confirmation phrase the candidate first-pass route requires, beside the issued context.
CANDIDATE_FIRST_PASS_CONFIRMATION = "CONFIRM CANDIDATE FIRST PASS"

#: The exact text every platform-bound capability document carries beside the guard policy.
#: The guard is a startup check; it is not a capacity certification and must not be shown as one.
START_GUARD_NOT_A_QUALIFICATION = (
    "The StartGuard policy and status describe one bounded startup check only; they are not a "
    "resource qualification proof and they do not certify macOS capacity."
)

_PROFILE_ROWS = {row.profile: row for row in MACOS_EXECUTION_PROFILES}


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LeaseAcquireRequest(ClosedModel):
    service_session_id: str = Field(min_length=1)


class LeaseMutationRequest(ClosedModel):
    service_session_id: str = Field(min_length=1)
    generation: int = Field(ge=1)


class ManifestCreateRequest(ClosedModel):
    total_points: int = Field(ge=4, le=20)


class CampaignConfiguration(ClosedModel):
    contract_version: Literal[3]
    service_session_id: str = Field(min_length=1)
    lease_id: str = Field(min_length=1)
    lease_generation: int = Field(ge=1)
    manifest_id: str = Field(min_length=1)
    execution_mode: Literal["SEQUENTIAL", "PARALLEL", "ADAPTIVE"]
    worker_count: int | None = Field(default=None, ge=1, le=FIXED_WORKER_COUNTS[-1])
    preferred_worker_count: int | None = Field(default=None, ge=1, le=16)
    fallback_worker_counts: tuple[int, ...] | None = None
    initial_points_per_worker: int | None = Field(default=None, ge=1, le=20)
    worker_start_timeout_s: float | None = Field(default=None, gt=0)
    max_infra_attempts_per_point: int | None = Field(default=None, ge=1)
    yolo_executor_count: Literal[1, 2, 4] | None = None
    #: The macOS routing key. A request that names a profile must name the exact combination its
    #: installed document declares; one that names nothing is never completed by inference.
    execution_profile: Literal[
        "MPS_W2_FIRST_PASS", "MPS_W1_FULL_RESTART_RETRY", "MPS_W1_FIRST_PASS"
    ] | None = None
    batch_kind: Literal["FIRST_PASS", "FULL_RESTART_RETRY"] | None = None

    @model_validator(mode="after")
    def validate_mode(self):
        if self.execution_profile is not None or self.batch_kind is not None:
            self._validate_profile_claim()
        fixed = (self.worker_count,)
        adaptive = (
            self.preferred_worker_count,
            self.fallback_worker_counts,
            self.initial_points_per_worker,
            self.worker_start_timeout_s,
            self.max_infra_attempts_per_point,
            self.yolo_executor_count,
        )
        if self.execution_mode in {"SEQUENTIAL", "PARALLEL"}:
            if any(value is None for value in fixed) or any(value is not None for value in adaptive):
                raise ValueError("FIXED_EXECUTION_CONFIG")
            if self.execution_mode == "SEQUENTIAL" and self.worker_count != 1:
                raise ValueError("SEQUENTIAL_WORKER_COUNT")
            if self.execution_mode == "PARALLEL" and self.worker_count not in FIXED_WORKER_COUNTS[1:]:
                raise ValueError("PARALLEL_WORKER_COUNT")
        else:
            if any(value is not None for value in fixed):
                raise ValueError("ADAPTIVE_FIXED_FIELD")
            if any(value is None for value in adaptive):
                raise ValueError("ADAPTIVE_EXECUTION_CONFIG")
            levels = (self.preferred_worker_count, *self.fallback_worker_counts)
            if any(next_level >= level for level, next_level in zip(levels, levels[1:])):
                raise ValueError("ADAPTIVE_FALLBACK_TIERS")
            if self.yolo_executor_count != 2:
                raise ValueError("ADAPTIVE_YOLO_EXECUTOR_COUNT")
        return self

    def _validate_profile_claim(self) -> None:
        """The claim is the matrix row or nothing: half a key and a cross key are both refused.

        The worker count is deliberately *not* checked here. ``N>2`` is a platform-support
        refusal, so it is decided where the document is loaded and answered with the stable
        ``UNSUPPORTED_ON_MACOS`` reason instead of a shape error.
        """

        if self.execution_profile is None or self.batch_kind is None:
            raise ValueError("EXECUTION_PROFILE_CLAIM")
        row = _PROFILE_ROWS.get(self.execution_profile)
        if row is None or row.batch_kind != self.batch_kind:
            raise ValueError("EXECUTION_PROFILE_CLAIM")
        if row.execution_mode != self.execution_mode:
            raise ValueError("EXECUTION_PROFILE_MODE")


class CampaignStartRequest(CampaignConfiguration):
    command_id: str = Field(min_length=1)
    preflight_receipt_id: str = Field(min_length=1)


class CampaignCancelRequest(ClosedModel):
    service_session_id: str = Field(min_length=1)
    lease_id: str = Field(min_length=1)
    lease_generation: int = Field(ge=1)
    command_id: str = Field(min_length=1)


class RetryRequest(CampaignCancelRequest):
    point_ids: tuple[str, ...] = Field(min_length=1)
    confirmation: str
    #: Which of the two mutually exclusive execution contexts authorizes this retry. A candidate
    #: context id may only be presented here as ``CANDIDATE``; a production retry never accepts one.
    context_kind: Literal["CANDIDATE", "PRODUCTION"] | None = None
    context_id: str | None = None


class CandidateContextIssueRequest(ClosedModel):
    """The coordinates of one bounded candidate run (design section 10).

    Every parameter the design names is required, including the worker count and batch kind: the
    installed matrix row, not a caller's inference, decides whether the combination may be issued.
    There is deliberately no budget, qualification or promotion field.
    """

    context_kind: str = "CANDIDATE"
    command_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    dispatch_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    batch_id: str = Field(min_length=1)
    manifest_id: str = Field(min_length=1)
    execution_profile: str = Field(min_length=1)
    worker_count: int = Field(ge=1)
    batch_kind: str = Field(min_length=1)
    #: The execution document the profile must resolve to, named by the caller and checked against
    #: the installed one: the context binds those exact bytes.
    config_document: str = Field(min_length=1)
    evidence_root: str = Field(min_length=1)
    owner_generation: int = Field(ge=1)
    expires_in_s: float = Field(gt=0)
    max_runs: int = Field(ge=1)


class CandidateExecutionContextResponse(ClosedModel):
    """One issued candidate context, exactly as the design binds it."""

    kind: Literal["CANDIDATE"]
    context_id: str
    task_id: str
    dispatch_id: str
    campaign_id: str
    batch_id: str
    manifest_id: str
    execution_profile: str
    schema_version: int = Field(ge=1)
    batch_kind: Literal["FIRST_PASS", "FULL_RESTART_RETRY"]
    worker_count: int = Field(ge=1)
    config_sha256: str
    #: Present for a composed service: the installed document and copied install the closure covers.
    config_document: str | None = None
    runtime_closure_sha256: str
    install_prefix: str | None = None
    install_binding_sha256: str | None = None
    evidence_root: str
    owner_generation: int = Field(ge=1)
    command_id: str
    issued_at_monotonic_ns: int
    expires_at_monotonic_ns: int
    max_runs: int = Field(ge=1)
    context_sha256: str


class CandidateFirstPassRequest(ClosedModel):
    """One candidate first pass, presented under the context that authorizes it."""

    context_kind: str = "CANDIDATE"
    #: Left optional so a missing context is answered with the named refusal rather than a shape
    #: error, exactly as the retry route answers it.
    context_id: str | None = None
    #: The context's own one-time command. Optional, and checked when present: it is the command
    #: the admission consumes, never a second authority beside it.
    command_id: str | None = None
    confirmation: str


class CandidateFirstPassResponse(ClosedModel):
    """The admitted candidate first pass, before any projection is read back."""

    status: Literal["STARTED"]
    campaign_id: str
    batch_id: str
    manifest_id: str
    execution_profile: str
    schema_version: int = Field(ge=1)
    worker_count: int = Field(ge=1)
    context_id: str
    context_kind: Literal["CANDIDATE"]
    command_id: str
    binding_sha256: str


class StartGuardCheck(ClosedModel):
    """One check of the shared startup guard, in the units the decision used."""

    status: Literal["PASS", "WARN", "FAIL"]
    reason: str = Field(min_length=1)
    observed: float | int | str | None = None
    cutoff: float | int | None = None
    unit: str = Field(min_length=1)


class StartGuardPolicyResponse(ClosedModel):
    """The enforced policy, so a client can display the cutoffs it was judged against.

    ``mps_minimum_headroom_bytes`` is present only for the schema-v4 macOS MPS combination. It is
    the fixed unified-memory floor, reported so a client can show the cutoff that refused a start;
    it is not a capacity certification and it does not scale with the worker count.
    """

    timeout_s: float
    cpu_busy_warn_fraction: float
    ram_minimum_bytes: int
    ram_minimum_fraction: float
    gpu_minimum_bytes: int
    mps_minimum_headroom_bytes: int | None = None


class StartGuardStatus(ClosedModel):
    """The server's own decision. A client cannot supply or overwrite it.

    ``admission_kind`` labels what the accelerator check actually measured. On the macOS MPS
    combination it is ``unified-memory-proxy``: a host unified-memory figure, not a device-level
    free-VRAM reading. Leaving it null is honest for a snapshot that carries no accelerator check.
    """

    status: Literal["PASS", "WARN", "FAIL"]
    cleanup_state: Literal["CLEAR", "PROBE_CLEANUP_BLOCKED"] = "CLEAR"
    checks: dict[str, StartGuardCheck] = {}
    gpu_uuid: str | None = None
    observed_monotonic_s: float | None = None
    admission_kind: str | None = None


class WorkerCountAvailability(ClosedModel):
    worker_count: int = Field(ge=1, le=FIXED_WORKER_COUNTS[-1])
    selectable: bool
    status: str = Field(min_length=1)
    reason_codes: tuple[str, ...] = ()
    profile_sha256: str | None = None
    qualification_sha256: str | None = None


class ExecutionProfileResponse(ClosedModel):
    """One row of the platform-bound support matrix, as the server would execute it.

    The row names the exact routing key a request must claim and carries no budget profile and
    no qualification hash: macOS supports W1 and W2, and that is the whole statement.
    """

    profile: str = Field(min_length=1)
    schema_version: int = Field(ge=1)
    execution_mode: Literal["SEQUENTIAL", "PARALLEL"]
    worker_count: int = Field(ge=1, le=2)
    batch_kind: Literal["FIRST_PASS", "FULL_RESTART_RETRY"]
    accelerator: str = "mps"
    selector: str = "MPS:default"
    platform: str = "macos"
    selectable: bool = True
    status: str = "SUPPORTED"
    reason_codes: tuple[str, ...] = ()
    profile_sha256: str | None = None
    qualification_sha256: str | None = None


def default_worker_count_availability() -> tuple[WorkerCountAvailability, ...]:
    """Unknown until the real executor reports; never fake a qualification."""

    return tuple(
        WorkerCountAvailability(
            worker_count=count, selectable=False, status="UNKNOWN",
            reason_codes=("CAPABILITIES_NOT_LOADED",),
        )
        for count in FIXED_WORKER_COUNTS[1:]
    )


class CapabilitiesResponse(ClosedModel):
    available: bool
    execution_modes: tuple[Literal["SEQUENTIAL", "PARALLEL", "ADAPTIVE"], ...] = ()
    default_execution_mode: Literal["SEQUENTIAL", "PARALLEL", "ADAPTIVE"] = "SEQUENTIAL"
    minimum_points: int = 4
    maximum_points: int = 20
    fixed_worker_counts: tuple[int, ...] = FIXED_WORKER_COUNTS
    worker_count_availability: tuple[WorkerCountAvailability, ...] = Field(
        default_factory=default_worker_count_availability)
    adaptive_default_ladder: tuple[int, ...] = (8, 6, 4, 2, 1)
    start_guard_policy: StartGuardPolicyResponse | None = None
    start_guard: StartGuardStatus | None = None
    lease_duration_s: float = 30.0
    lease_renewal_margin_s: float = 10.0
    #: Present only for a platform-bound composition (macOS). It is the complete answer for this
    #: host, so no budget provider or per-N qualification view takes part in it.
    platform: str | None = None
    support_matrix: tuple[ExecutionProfileResponse, ...] = ()
    execution_profile: str | None = None
    execution_schema_version: int | None = None
    execution_config_sha256: str | None = None
    start_guard_note: str | None = None
    worker_qualifications: tuple[dict[str, object], ...] = ()


class LeaseResponse(ClosedModel):
    lease_id: str
    service_session_id: str
    generation: int
    expires_monotonic_ns: int
    #: The domain's execution generation after this acquire bound the controller. The lease's own
    #: ``generation`` counts renewals and is a different number (design section 5.1): a client that
    #: presents the renewal generation is refused STALE_EXECUTION_GENERATION, and nothing else told it
    #: which value the server holds.
    execution_generation: int | None = None


class LeaseReleaseResponse(ClosedModel):
    lease_id: str
    released: bool


class ManifestPointResponse(ClosedModel):
    id: str
    display_id: str
    label: str
    source: Literal["anchor", "generated"]
    stratum: str
    position_world_m: tuple[float, float, float]


class ManifestSourceHashes(ClosedModel):
    catalog: str
    parallel_config: str
    adaptive_config: str
    execution_policy: str
    dynamic_policy: str
    placement_policy: str
    task_scene: str
    scene: str
    target_mesh: str
    anchors: str


class MapProjectionResponse(ClosedModel):
    width_px: int = Field(gt=0)
    height_px: int = Field(gt=0)
    bounds_m: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]
    padding_px: FiniteFloat = Field(ge=0)
    pixels_per_m: FiniteFloat = Field(gt=0)
    offset_x_px: FiniteFloat
    offset_y_px: FiniteFloat


class MapGeometryResponse(ClosedModel):
    table_bounds: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]
    base_bounds: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]
    target_center: tuple[FiniteFloat, FiniteFloat]
    target_bounds: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]
    candidate_bounds: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]
    cup_radius_m: FiniteFloat = Field(gt=0)
    target_tolerance_radius_m: FiniteFloat = Field(gt=0)


class MapPointResponse(ClosedModel):
    id: str
    display_id: str
    position_world_m: tuple[FiniteFloat, FiniteFloat, FiniteFloat]
    projected_px: tuple[FiniteFloat, FiniteFloat]


class MapPaletteStyle(ClosedModel):
    stroke: str
    fill: str
    icon: Literal["pending", "passed", "failed"]


class MapPaletteResponse(ClosedModel):
    blue: MapPaletteStyle
    green: MapPaletteStyle
    red: MapPaletteStyle


class ManifestTopViewResponse(ClosedModel):
    projection: MapProjectionResponse
    geometry: MapGeometryResponse
    cup_footprint_radius_px: FiniteFloat = Field(gt=0)
    target_tolerance_radius_px: FiniteFloat = Field(gt=0)
    marker_radius_px: FiniteFloat = Field(gt=0)
    points: tuple[MapPointResponse, ...] = Field(min_length=4, max_length=20)
    palette: MapPaletteResponse


class ManifestResponse(ClosedModel):
    manifest_id: str
    point_count: int = 0
    catalog_sha256: str | None = None
    selection_sha256: str | None = None
    stale: bool = False
    points: tuple[ManifestPointResponse, ...] = ()
    manifest_sha256: str | None = None
    source_commit: str | None = None
    sampler_id: str | None = None
    sampler_version: int | None = None
    catalog_seed: int | None = None
    geometry_sha256: str | None = None
    source_hashes: ManifestSourceHashes | None = None
    top_view: ManifestTopViewResponse | None = None


class PreflightResponse(ClosedModel):
    receipt_id: str
    admitted: bool
    manifest_id: str | None = None
    execution_mode: Literal["SEQUENTIAL", "PARALLEL", "ADAPTIVE"] | None = None
    execution_config: dict[str, object] = {}
    resource_observations: dict[str, object] = {}
    start_guard: StartGuardStatus | None = None
    reason_codes: tuple[str, ...] = ()
    expires_at_monotonic_ns: int | None = None
    #: The resolved platform profile this receipt bound, when the document is a macOS one.
    execution_profile: str | None = None
    execution_schema_version: int | None = None
    execution_batch_kind: str | None = None


class AttemptProjectionResponse(ClosedModel):
    generation: int
    status: str
    reason: str | None = None
    kind: Literal["FIRST_PASS", "FULL_RESTART_RETRY"] = "FIRST_PASS"
    attempt_id: str | None = None
    worker_id: str | None = None
    worker_generation: int | None = None
    batch_id: str | None = None


class ArtifactProjectionResponse(ClosedModel):
    artifact_id: str
    campaign_id: str
    batch_id: str
    pool_generation: int | None = None
    worker_id: str | None = None
    worker_generation: int | None = None
    attempt_id: str | None = None
    role: str
    media_type: str
    size_bytes: int
    sha256: str


class PointProjectionResponse(ClosedModel):
    point_id: str
    display_id: str | None = None
    status: str
    retry_eligible: bool = False
    active_worker_id: str | None = None
    reason: str | None = None
    attempts: tuple[AttemptProjectionResponse, ...] = ()
    artifact_ids: tuple[str, ...] = ()
    artifacts: tuple[ArtifactProjectionResponse, ...] = ()


class WorkerProjectionResponse(ClosedModel):
    worker_id: str
    generation: int
    state: str
    current_point_id: str | None = None
    lease_count: int = 0
    max_points_per_worker: int | None = None
    heartbeat_deadline_monotonic_s: float | None = None
    recovery_result: str | None = None
    quarantine_reason: str | None = None


class BrokerProjectionResponse(ClosedModel):
    available: bool
    reason: str | None = None


class RetryHistoryResponse(ClosedModel):
    """One admitted retry, as history. The first-pass counters above never change because of it."""

    campaign_id: str
    batch_id: str
    point_id: str
    original_batch_id: str
    original_result_sha256: str
    command_id: str
    binding_sha256: str
    state: Literal["ADMITTED", "CLEANED"]
    cleanup_receipt_sha256: str | None = None


class CampaignProjectionResponse(ClosedModel):
    campaign_id: str
    manifest_id: str | None = None
    sequence: int
    execution_mode: Literal["SEQUENTIAL", "PARALLEL", "ADAPTIVE"] | None = None
    owner_kind: Literal["COORDINATOR", "ADAPTIVE_WRAPPER"] | None = None
    batch_id: str | None = None
    status: str | None = None
    points: tuple[PointProjectionResponse, ...] = ()
    workers: tuple[WorkerProjectionResponse, ...] = ()
    broker: BrokerProjectionResponse | None = None
    requested: int = 0
    evaluated: int = 0
    execution_started: int = 0
    valid_succeeded: int = 0
    valid_failed: int = 0
    indeterminate: int = 0
    not_executed: int = 0
    evaluation_coverage: float = 0.0
    execution_coverage: float = 0.0
    qualified_success_rate: float | None = None
    coverage_complete: bool | None = None
    execution_complete: bool | None = None
    batch_cleanup_complete: bool = False
    qualification_passed: bool | None = None
    levels_used: tuple[int, ...] = ()
    fallback_history: tuple[dict[str, object], ...] = ()
    current_generation: int | None = None
    infra_attempts: int = 0
    resource_observations: dict[str, object] = {}
    #: Retries appended after the first pass. Read-only history: it never rewrites the point
    #: statuses or the counters that describe what the first pass actually did.
    retry_history: tuple[RetryHistoryResponse, ...] = ()


async def _invoke(method, *args):
    value = method(*args)
    return await value if inspect.isawaitable(value) else value


def _error(error: Exception, *, default_status: int = 409) -> JSONResponse:
    code = str(error) or type(error).__name__
    return JSONResponse(status_code=default_status, content={"code": code})


_LEGACY_EXECUTION_KEY = "max_points_per_worker"


async def _reject_legacy_execution_contract(request: Request) -> None:
    """Refuse legacy quota keys and non-v2 new execution before body validation."""

    if request.method not in {"POST", "PUT", "PATCH"}:
        return
    try:
        raw = await request.body()
    except Exception:  # pragma: no cover - the body is always readable here
        return
    if not raw:
        return
    try:
        payload = json.loads(raw)
    except (UnicodeError, ValueError):
        return
    if not isinstance(payload, dict):
        return
    if _LEGACY_EXECUTION_KEY in payload:
        raise HTTPException(
            status_code=422,
            detail={"code": "LEGACY_MAX_POINTS_PER_WORKER_UNSUPPORTED"},
        )
    version = payload.get("contract_version")
    if type(version) is not int or version != 3:
        raise HTTPException(
            status_code=422,
            detail={"code": "CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION"},
        )


def create_expert_validation_app(
    service,
    static_dir: str | Path | None = None,
    *,
    bind_address: str = "127.0.0.1",
) -> FastAPI:
    validate_bind_address(bind_address)

    async def maintain_lease(app):
        lease_service = getattr(service, "lease_service", None)
        expire_due = getattr(lease_service, "expire_due", None)
        if expire_due is None:
            return
        while True:
            try:
                expire_due()
            except Exception:
                app.state.lease_maintenance_failed = True
                logging.getLogger(__name__).exception("LEASE_MAINTENANCE_FAILED")
                supervisor = getattr(service, "supervisor", None)
                cancel = getattr(supervisor, "cancel_for_reason", None)
                if cancel is not None:
                    try:
                        await _invoke(cancel, "LEASE_MAINTENANCE_FAILED")
                    except Exception:
                        logging.getLogger(__name__).exception("LEASE_OWNER_CANCEL_FAILED")
                return
            await asyncio.sleep(0.25)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(maintain_lease(app))
        try:
            await asyncio.sleep(0)
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="SO-101 Expert Validation", version="1.0.0", lifespan=lifespan)
    app.state.lease_maintenance_failed = False

    @app.middleware("http")
    async def fence_failed_maintenance(request: Request, call_next):
        if (
            app.state.lease_maintenance_failed
            and request.method not in {"GET", "HEAD", "OPTIONS"}
            and not request.url.path.endswith("/cancel")
        ):
            return JSONResponse(status_code=503, content={"code": "LEASE_MAINTENANCE_FAILED"})
        return await call_next(request)

    @app.get("/health")
    async def health():
        if app.state.lease_maintenance_failed:
            return JSONResponse(status_code=503, content={"code": "LEASE_MAINTENANCE_FAILED"})
        return await _invoke(service.health)

    @app.get("/expert-validation/capabilities", response_model=CapabilitiesResponse)
    async def capabilities():
        return await _invoke(service.capabilities)

    @app.post("/expert-validation/lease", response_model=LeaseResponse)
    async def acquire_lease(body: LeaseAcquireRequest):
        try:
            return await _invoke(service.acquire_lease, body.model_dump())
        except Exception as error:
            return _error(error)

    @app.put("/expert-validation/lease/{lease_id}", response_model=LeaseResponse)
    async def renew_lease(lease_id: str, body: LeaseMutationRequest):
        try:
            return await _invoke(service.renew_lease, lease_id, body.model_dump())
        except Exception as error:
            return _error(error)

    @app.delete("/expert-validation/lease/{lease_id}", response_model=LeaseReleaseResponse)
    async def release_lease(lease_id: str, body: LeaseMutationRequest):
        try:
            return await _invoke(service.release_lease, lease_id, body.model_dump())
        except Exception as error:
            return _error(error)

    @app.post("/expert-validation/manifests", response_model=ManifestResponse)
    async def create_manifest(body: ManifestCreateRequest):
        try:
            return await _invoke(service.create_manifest_from_count, body.total_points)
        except Exception as error:
            return _error(error)

    @app.get("/expert-validation/manifests/{manifest_id}", response_model=ManifestResponse)
    async def get_manifest(manifest_id: str):
        try:
            method = getattr(service, "get_manifest_api", service.get_manifest)
            return await _invoke(method, manifest_id)
        except Exception as error:
            return _error(error, default_status=404)

    @app.post(
        "/expert-validation/campaigns/preflight",
        response_model=PreflightResponse,
        dependencies=[Depends(_reject_legacy_execution_contract)],
    )
    async def preflight(body: CampaignConfiguration):
        try:
            return await _invoke(service.preflight_api, body.model_dump(exclude_none=True))
        except Exception as error:
            return _error(error)

    @app.post(
        "/expert-validation/campaigns",
        response_model=CampaignProjectionResponse,
        dependencies=[Depends(_reject_legacy_execution_contract)],
    )
    async def start_campaign(body: CampaignStartRequest):
        try:
            return await _invoke(service.start_campaign_api, body.model_dump(exclude_none=True))
        except Exception as error:
            return _error(error)

    @app.get("/expert-validation/campaigns", response_model=list[CampaignProjectionResponse])
    async def list_campaigns():
        return await _invoke(service.list_campaigns)

    @app.get(
        "/expert-validation/campaigns/{campaign_id}",
        response_model=CampaignProjectionResponse,
    )
    async def get_campaign(campaign_id: str):
        try:
            return await _invoke(service.get_campaign, campaign_id)
        except Exception as error:
            return _error(error, default_status=404)

    @app.post(
        "/expert-validation/campaigns/{campaign_id}/cancel",
        response_model=CampaignProjectionResponse,
    )
    async def cancel_campaign(campaign_id: str, body: CampaignCancelRequest):
        try:
            return await _invoke(service.cancel_campaign, campaign_id, body.model_dump())
        except Exception as error:
            return _error(error)

    @app.post(
        "/expert-validation/campaigns/{campaign_id}/full-restart-retries",
        response_model=CampaignProjectionResponse,
    )
    async def retry_campaign(campaign_id: str, body: RetryRequest):
        if body.confirmation != "CONFIRM FULL_RESTART RETRIES":
            return JSONResponse(status_code=409, content={"code": "CONFIRMATION_REQUIRED"})
        try:
            # The declared context kind decides which endpoint runs this; a context of the other
            # kind is refused by name rather than silently reinterpreted.
            method = getattr(service, "retry_campaign_api", service.retry_campaign)
            return await _invoke(method, campaign_id, body.model_dump(exclude_none=True))
        except Exception as error:
            return _error(error)

    @app.post("/expert-validation/candidate-contexts", response_model=CandidateExecutionContextResponse)
    async def issue_candidate_context(body: CandidateContextIssueRequest):
        try:
            return await _invoke(
                service.issue_candidate_context_api, body.model_dump(exclude_none=True)
            )
        except Exception as error:
            return _error(error)

    @app.post(
        "/expert-validation/campaigns/candidate-first-pass",
        response_model=CandidateFirstPassResponse,
    )
    async def candidate_first_pass(body: CandidateFirstPassRequest):
        if body.confirmation != CANDIDATE_FIRST_PASS_CONFIRMATION:
            return JSONResponse(status_code=409, content={"code": "CONFIRMATION_REQUIRED"})
        try:
            return await _invoke(
                service.start_candidate_first_pass_api, body.model_dump(exclude_none=True)
            )
        except Exception as error:
            return _error(error)

    @app.get("/expert-validation/artifacts/{artifact_id}")
    async def artifact(artifact_id: str):
        try:
            verified = service.artifacts.resolve_opaque_id(artifact_id)
        except (ArtifactAccessError, KeyError, ValueError):
            return JSONResponse(status_code=404, content={"code": "ARTIFACT_NOT_FOUND"})
        return FileResponse(
            verified.path,
            media_type=verified.media_type,
            filename=verified.path.name,
        )

    @app.websocket("/expert-validation/events")
    async def events(websocket: WebSocket):
        await websocket.accept()
        subscribe = getattr(service, "subscribe", None)
        if subscribe is None:
            await websocket.close(code=1011, reason="EVENT_STREAM_UNAVAILABLE")
            return
        queue = subscribe()

        async def send_events():
            while True:
                event = await queue.get()
                await websocket.send_json(
                    event.model_dump() if hasattr(event, "model_dump") else event
                )

        async def receive_disconnect():
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    return

        tasks = {
            asyncio.create_task(send_events()),
            asyncio.create_task(receive_disconnect()),
        }
        try:
            completed, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in completed:
                task.result()
        except WebSocketDisconnect:
            return
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            unsubscribe = getattr(service, "unsubscribe", None)
            if unsubscribe is not None:
                unsubscribe(queue)

    @app.post("/tasks/runs")
    async def disabled_task_runs():
        return JSONResponse(status_code=503, content={"code": "VALIDATION_TASKS_DISABLED"})

    @app.api_route(
        "/tasks/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        include_in_schema=False,
    )
    async def disabled_tasks(path: str):
        return JSONResponse(status_code=503, content={"code": "VALIDATION_TASKS_DISABLED"})

    @app.get("/", include_in_schema=False)
    async def root_redirect():
        return RedirectResponse("/expert-validation", status_code=307)

    if static_dir is not None:
        root = Path(static_dir)
        if root.is_dir() and (root / "index.html").is_file():
            # The shared Vite build emits absolute /assets URLs for both SPAs.
            app.mount(
                "/assets",
                StaticFiles(directory=root / "assets", follow_symlink=True),
                name="validation-vite-assets",
            )
            app.mount(
                "/expert-validation/assets",
                StaticFiles(directory=root / "assets", follow_symlink=True),
                name="expert-validation-assets",
            )

            @app.get("/expert-validation", include_in_schema=False)
            async def validation_page():
                return FileResponse(root / "index.html")

            @app.get("/expert-validation/{path:path}", include_in_schema=False)
            async def validation_fallback(path: str):
                if path.startswith("artifacts/"):
                    # The SPA fallback must never shadow the artifact namespace.
                    return JSONResponse(status_code=404, content={"code": "ARTIFACT_NOT_FOUND"})
                candidate = root / path
                return FileResponse(candidate if candidate.is_file() else root / "index.html")
        else:
            @app.get("/expert-validation", include_in_schema=False)
            async def validation_assets_missing():
                return JSONResponse(status_code=503, content={"code": "WEB_ASSETS_NOT_BUILT"})
    else:
        @app.get("/expert-validation", include_in_schema=False)
        async def validation_assets_unconfigured():
            return JSONResponse(status_code=503, content={"code": "WEB_ASSETS_NOT_BUILT"})

    return app
