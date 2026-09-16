"""Scripted expert-validation service for L1 Chrome contract tests.

The scripted service implements the same service port consumed by the
production ``create_expert_validation_app`` routes.  It plays versioned
scenario files: every projected state is declared in the scenario, and the
service never derives robot, physics, or business outcomes itself.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, ValidationError

from so101_teleop.expert_validation.api import create_expert_validation_app


class ScenarioError(RuntimeError):
    """A scenario file violated the closed scripted-fixture contract."""


class ScriptedServiceError(RuntimeError):
    """Scenario-driven service rejection carrying a stable reason code."""


_GOLDEN_TOP_VIEW = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "expert_validation"
    / "top_view_projection_v1.json"
)
_CANDIDATE_BOUNDS = (-0.045, 0.08, -0.34, -0.24)

_ROBOT_TRUTH_KEYS = frozenset(
    {
        "robot_pose",
        "joint_states",
        "joints",
        "tf",
        "mujoco",
        "physics",
        "contact",
        "gazebo",
        "gz_partition",
        "moveit",
        "planning_scene",
        "controller",
    }
)

_ALLOWED_TOP_LEVEL = frozenset(
    {
        "schema_version",
        "scenario_id",
        "description",
        "lease_duration_s",
        "lease_renewal_margin_s",
        "capabilities",
        "mode_availability",
        "initial_campaign",
        "preflight_rejection",
        "expected_commands",
        "event_script",
        "faults",
        "expected_http_refresh_after",
        "terminal_campaign",
        "retry_results",
    }
)


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _CapabilitiesModel(_ClosedModel):
    available: bool = True
    execution_modes: tuple[str, ...] = ("SEQUENTIAL", "PARALLEL", "ADAPTIVE")
    default_execution_mode: str = "SEQUENTIAL"
    minimum_points: int = 4
    maximum_points: int = 20
    fixed_worker_counts: tuple[int, ...] = (1, 2, 3)
    fixed_max_points_per_worker: int = 20
    adaptive_default_ladder: tuple[int, ...] = (8, 6, 4, 2, 1)


class _EventModel(_ClosedModel):
    sequence: int
    hint: str | None = None
    patch: dict[str, Any] | None = None


class _HttpErrorFault(_ClosedModel):
    operation: str
    code: str


class _FaultModel(_ClosedModel):
    omit_sequence: int | None = None
    duplicate_sequence: int | None = None
    late_sequence: int | None = None
    ws_disconnect: bool | None = None
    http_error_once: _HttpErrorFault | None = None


class _PreflightRejection(_ClosedModel):
    reason_codes: tuple[str, ...]


class _ScenarioModel(_ClosedModel):
    schema_version: int
    scenario_id: str
    description: str | None = None
    lease_duration_s: float = 30.0
    lease_renewal_margin_s: float = 10.0
    capabilities: _CapabilitiesModel = _CapabilitiesModel()
    mode_availability: dict[str, str | None] = {}
    initial_campaign: dict[str, Any] | None = None
    preflight_rejection: _PreflightRejection | None = None
    expected_commands: tuple[str, ...] = ()
    event_script: tuple[_EventModel, ...] = ()
    faults: tuple[_FaultModel, ...] = ()
    expected_http_refresh_after: int | None = None
    terminal_campaign: str | None = None
    retry_results: dict[str, str] = {}


@dataclass(frozen=True)
class ScriptedEvent:
    sequence: int
    hint: str | None
    patch: dict[str, Any] | None


@dataclass(frozen=True)
class ScriptedFault:
    kind: str
    value: Any


@dataclass(frozen=True)
class ScriptedScenario:
    schema_version: int
    scenario_id: str
    initial_state: dict[str, Any]
    expected_commands: tuple[str, ...]
    event_script: tuple[ScriptedEvent, ...]
    faults: tuple[ScriptedFault, ...]
    document: dict[str, Any]


def _scan_robot_truth(node: Any) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str) and key.lower() in _ROBOT_TRUTH_KEYS:
                raise ScenarioError(f"ROBOT_TRUTH_FORBIDDEN:{key}")
            _scan_robot_truth(value)
    elif isinstance(node, list):
        for item in node:
            _scan_robot_truth(item)


def load_scenario(path: Path) -> tuple[ScriptedScenario, str]:
    """Load one versioned scenario and return it with its canonical SHA256."""

    try:
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ScenarioError(f"SCENARIO_UNREADABLE:{type(error).__name__}") from error
    if not isinstance(document, dict):
        raise ScenarioError("SCENARIO_NOT_A_MAPPING")
    unknown = set(document) - _ALLOWED_TOP_LEVEL
    if unknown:
        raise ScenarioError(f"UNKNOWN_FIELD:{sorted(unknown)[0]}")
    if "scenario_id" not in document:
        raise ScenarioError("SCENARIO_ID_REQUIRED")
    _scan_robot_truth(document)
    try:
        model = _ScenarioModel.model_validate(document)
    except ValidationError as error:
        raise ScenarioError(f"SCENARIO_INVALID:{error.errors()[0]['type']}") from error
    if model.schema_version != 1:
        raise ScenarioError("SCHEMA_VERSION_UNSUPPORTED")
    sequences = [event.sequence for event in model.event_script]
    if len(sequences) != len(set(sequences)):
        raise ScenarioError("DUPLICATE_SEQUENCE")
    canonical = json.dumps(
        model.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    faults = tuple(
        ScriptedFault(kind, value)
        for fault in model.faults
        for kind, value in fault.model_dump().items()
        if value is not None
    )
    scenario = ScriptedScenario(
        schema_version=model.schema_version,
        scenario_id=model.scenario_id,
        initial_state={
            "capabilities": model.capabilities.model_dump(mode="json"),
            "mode_availability": dict(model.mode_availability),
            "initial_campaign": copy.deepcopy(model.initial_campaign),
            "preflight_rejection": (
                None
                if model.preflight_rejection is None
                else list(model.preflight_rejection.reason_codes)
            ),
            "lease_duration_s": model.lease_duration_s,
            "lease_renewal_margin_s": model.lease_renewal_margin_s,
            "terminal_campaign": model.terminal_campaign,
            "retry_results": dict(model.retry_results),
        },
        expected_commands=model.expected_commands,
        event_script=tuple(
            ScriptedEvent(event.sequence, event.hint, event.patch)
            for event in model.event_script
        ),
        faults=faults,
        document=model.model_dump(mode="json"),
    )
    return scenario, digest


def _golden_points() -> list[dict[str, Any]]:
    return json.loads(_GOLDEN_TOP_VIEW.read_text(encoding="utf-8"))["points"]


def _golden_top_view(point_count: int) -> dict[str, Any]:
    golden = json.loads(_GOLDEN_TOP_VIEW.read_text(encoding="utf-8"))
    return {
        "projection": golden["projection"],
        "geometry": {**golden["geometry"], "candidate_bounds": list(_CANDIDATE_BOUNDS)},
        "cup_footprint_radius_px": golden["cup_footprint_radius_px"],
        "target_tolerance_radius_px": golden["target_tolerance_radius_px"],
        "marker_radius_px": golden["marker_radius_px"],
        "points": golden["points"][:point_count],
        "palette": golden["palette"],
    }


def _manifest_point(point: dict[str, Any], index: int) -> dict[str, Any]:
    anchor = index < 4
    return {
        "id": point["id"],
        "display_id": point["display_id"],
        "label": point["id"],
        "source": "anchor" if anchor else "generated",
        "stratum": "anchor" if anchor else point["id"].split("_", 2)[2].replace("_", "/", 1),
        "position_world_m": list(point["position_world_m"]),
    }


class _ScriptedLeaseService:
    """Minimal lease authority driving the production maintenance loop."""

    def __init__(self, service: "ScriptedValidationService") -> None:
        self._service = service

    def expire_due(self) -> bool:
        lease = self._service._lease
        if lease is None or lease["state"] != "ACTIVE":
            return False
        if time.monotonic_ns() < lease["expires_monotonic_ns"]:
            return False
        lease["state"] = "EXPIRED"
        self._service._unresolved = True
        self._service._log_command("lease_expired", {})
        return True


class _ScriptedArtifactRegistry:
    def __init__(self) -> None:
        self._artifacts: dict[str, tuple[Path, str]] = {}

    def register(self, artifact_id: str, path: Path, media_type: str) -> None:
        self._artifacts[artifact_id] = (path, media_type)

    def resolve_opaque_id(self, artifact_id: str):
        if artifact_id not in self._artifacts:
            raise KeyError(artifact_id)
        path, media_type = self._artifacts[artifact_id]
        return type("VerifiedArtifact", (), {"path": path, "media_type": media_type})()


class _WsCloseSentinel:
    def model_dump(self) -> dict:
        raise RuntimeError("SCRIPTED_WS_CLOSE")


def _deep_merge(target: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)
    return target


class ScriptedValidationService:
    """Service-port implementation that replays one scripted scenario."""

    def __init__(self, scenario: ScriptedScenario, scenario_sha256: str) -> None:
        self.scenario = scenario
        self.scenario_sha256 = scenario_sha256
        initial = scenario.initial_state
        self._capabilities = dict(initial["capabilities"])
        self._mode_availability = dict(initial["mode_availability"])
        self._preflight_rejection = initial["preflight_rejection"]
        self._lease_duration_ns = int(initial["lease_duration_s"] * 1_000_000_000)
        self._lease_renewal_margin_s = initial["lease_renewal_margin_s"]
        self._terminal_campaign = initial["terminal_campaign"]
        self._retry_results = dict(initial["retry_results"])
        self._lease: dict[str, Any] | None = None
        self._unresolved = False
        self._manifests: dict[str, dict[str, Any]] = {}
        self._campaigns: dict[str, dict[str, Any]] = {}
        self._receipts: dict[str, dict[str, Any]] = {}
        self._commands: dict[str, dict[str, Any]] = {}
        self.command_log: list[dict[str, Any]] = []
        self._subscribers: set[asyncio.Queue] = set()
        self._emit_index = 0
        self._held_late: tuple[str, int, str | None] | None = None
        self.emitted_sequences: list[int] = []
        self.lease_service = _ScriptedLeaseService(self)
        self.artifacts = _ScriptedArtifactRegistry()
        if initial["initial_campaign"] is not None:
            campaign = copy.deepcopy(initial["initial_campaign"])
            self._campaigns[campaign["campaign_id"]] = campaign

    # -- internal helpers -------------------------------------------------

    def _log_command(self, operation: str, detail: dict[str, Any]) -> None:
        self.command_log.append({"operation": operation, **detail})

    def _authorize_lease(self, lease_id: str, generation: int, session: str) -> None:
        lease = self._lease
        if lease is None or lease["state"] != "ACTIVE":
            raise ScriptedServiceError("LEASE_NOT_ACTIVE")
        if lease["lease_id"] != lease_id or lease["service_session_id"] != session:
            raise ScriptedServiceError("LEASE_IDENTITY_MISMATCH")
        if lease["generation"] != generation:
            raise ScriptedServiceError("STALE_LEASE_GENERATION")
        if time.monotonic_ns() >= lease["expires_monotonic_ns"]:
            raise ScriptedServiceError("LEASE_EXPIRED")

    def _check_http_fault(self, operation: str) -> None:
        remaining = []
        for fault in self.scenario.faults:
            if fault.kind == "http_error_once" and fault.value["operation"] == operation:
                self._log_command("http_fault", {"operation": operation})
                raise ScriptedServiceError(fault.value["code"])
            remaining.append(fault)
        object.__setattr__(self.scenario, "faults", tuple(remaining))

    def _publish(self, campaign_id: str, sequence: int, hint: str | None) -> None:
        frame = {"campaign_id": campaign_id, "sequence": sequence, "type": hint or "HINT"}
        self.emitted_sequences.append(sequence)
        for queue in list(self._subscribers):
            queue.put_nowait(frame)

    def _publish_ws_close(self) -> None:
        for queue in list(self._subscribers):
            queue.put_nowait(_WsCloseSentinel())

    # -- production service port -------------------------------------------

    def health(self) -> dict[str, Any]:
        return {"ok": True, "service": "expert-validation"}

    def capabilities(self) -> dict[str, Any]:
        return {
            **self._capabilities,
            "lease_duration_s": self._lease_duration_ns / 1_000_000_000,
            "lease_renewal_margin_s": self._lease_renewal_margin_s,
        }

    def acquire_lease(self, body: dict[str, Any]) -> dict[str, Any]:
        self._check_http_fault("acquire_lease")
        self._log_command("acquire_lease", {"service_session_id": body["service_session_id"]})
        lease = self._lease
        if (
            lease is not None
            and lease["state"] == "ACTIVE"
            and lease["service_session_id"] != body["service_session_id"]
            and time.monotonic_ns() < lease["expires_monotonic_ns"]
        ):
            raise ScriptedServiceError("LEASE_HELD")
        self._lease = {
            "lease_id": "lease-" + uuid.uuid4().hex,
            "service_session_id": body["service_session_id"],
            "generation": 1,
            "expires_monotonic_ns": time.monotonic_ns() + self._lease_duration_ns,
            "state": "ACTIVE",
        }
        return {key: self._lease[key] for key in (
            "lease_id", "service_session_id", "generation", "expires_monotonic_ns")}

    def renew_lease(self, lease_id: str, body: dict[str, Any]) -> dict[str, Any]:
        self._check_http_fault("renew_lease")
        self._authorize_lease(lease_id, body["generation"], body["service_session_id"])
        self._log_command("renew_lease", {"generation": body["generation"]})
        assert self._lease is not None
        self._lease["generation"] += 1
        self._lease["expires_monotonic_ns"] = time.monotonic_ns() + self._lease_duration_ns
        return {key: self._lease[key] for key in (
            "lease_id", "service_session_id", "generation", "expires_monotonic_ns")}

    def release_lease(self, lease_id: str, body: dict[str, Any]) -> dict[str, Any]:
        self._authorize_lease(lease_id, body["generation"], body["service_session_id"])
        self._log_command("release_lease", {"lease_id": lease_id})
        if any(
            campaign.get("status") in {"RUNNING", "CANCELLING", "CLEANING_UP"}
            for campaign in self._campaigns.values()
        ):
            raise ScriptedServiceError("ACTIVE_CAMPAIGN")
        assert self._lease is not None
        self._lease["state"] = "RELEASED"
        return {"lease_id": lease_id, "released": True}

    def create_manifest_from_count(self, total_points: int) -> dict[str, Any]:
        self._check_http_fault("create_manifest")
        self._log_command("create_manifest", {"total_points": total_points})
        points = _golden_points()[:total_points]
        document_points = [_manifest_point(point, index) for index, point in enumerate(points)]
        manifest_id = "manifest-" + uuid.uuid4().hex
        canonical = json.dumps(document_points, sort_keys=True, separators=(",", ":"))
        manifest = {
            "manifest_id": manifest_id,
            "point_count": total_points,
            "catalog_sha256": hashlib.sha256(b"ai_station_baseline_v1").hexdigest(),
            "selection_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "stale": False,
            "points": document_points,
            "manifest_sha256": hashlib.sha256(
                (manifest_id + canonical).encode("utf-8")
            ).hexdigest(),
            "source_commit": "scripted",
            "sampler_id": "ai_station_baseline_v1",
            "sampler_version": 1,
            "catalog_seed": 20260911,
            "geometry_sha256": hashlib.sha256(b"top_view_projection_v1").hexdigest(),
            "source_hashes": None,
            "top_view": _golden_top_view(total_points),
        }
        self._manifests[manifest_id] = manifest
        return manifest

    def get_manifest_api(self, manifest_id: str) -> dict[str, Any]:
        try:
            return self._manifests[manifest_id]
        except KeyError as error:
            raise ScriptedServiceError("VALIDATION_MANIFEST_NOT_FOUND") from error

    async def preflight_api(self, body: dict[str, Any]) -> dict[str, Any]:
        self._check_http_fault("preflight")
        self._authorize_lease(
            body["lease_id"], body["lease_generation"], body["service_session_id"]
        )
        if self._unresolved:
            raise ScriptedServiceError("VALIDATION_RECOVERY_REQUIRED")
        reason = self._mode_availability.get(body["execution_mode"])
        if reason:
            raise ScriptedServiceError(reason)
        self._log_command("preflight", {"manifest_id": body["manifest_id"]})
        if self._preflight_rejection is not None:
            return {
                "receipt_id": "receipt-rejected",
                "admitted": False,
                "manifest_id": body["manifest_id"],
                "execution_mode": body["execution_mode"],
                "execution_config": {},
                "resource_observations": {},
                "reason_codes": tuple(self._preflight_rejection),
                "expires_at_monotonic_ns": None,
            }
        canonical = json.dumps(
            {key: body[key] for key in sorted(body)}, sort_keys=True, separators=(",", ":")
        )
        receipt_id = "receipt-" + uuid.uuid4().hex
        self._receipts[receipt_id] = {
            "receipt_id": receipt_id,
            "request_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "body": copy.deepcopy(body),
            "lease_generation": body["lease_generation"],
            "consumed": False,
            "expires_monotonic_ns": time.monotonic_ns() + 60_000_000_000,
        }
        return {
            "receipt_id": receipt_id,
            "admitted": True,
            "manifest_id": body["manifest_id"],
            "execution_mode": body["execution_mode"],
            "execution_config": {
                key: value
                for key, value in body.items()
                if key
                in {
                    "worker_count",
                    "max_points_per_worker",
                    "preferred_worker_count",
                    "fallback_worker_counts",
                    "initial_points_per_worker",
                    "worker_start_timeout_s",
                    "max_infra_attempts_per_point",
                    "yolo_executor_count",
                }
                and value is not None
            },
            "resource_observations": {"logical_cpu_count": 32},
            "reason_codes": (),
            "expires_at_monotonic_ns": self._receipts[receipt_id]["expires_monotonic_ns"],
        }

    async def start_campaign_api(self, body: dict[str, Any]) -> dict[str, Any]:
        self._check_http_fault("start_campaign")
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
        existing = self._commands.get(body["command_id"])
        if existing is not None:
            if existing["request_sha256"] != digest:
                raise ScriptedServiceError("COMMAND_ID_REUSED")
            return existing["result"]
        receipt = self._receipts.get(body["preflight_receipt_id"])
        if receipt is None:
            raise ScriptedServiceError("PREFLIGHT_RECEIPT_MISMATCH")
        expected = {key: value for key, value in receipt["body"].items()}
        comparable = {key: body.get(key) for key in expected}
        if comparable != expected:
            raise ScriptedServiceError("PREFLIGHT_REQUEST_MISMATCH")
        if receipt["consumed"]:
            raise ScriptedServiceError("PREFLIGHT_RECEIPT_CONSUMED")
        self._authorize_lease(
            body["lease_id"], body["lease_generation"], body["service_session_id"]
        )
        if receipt["lease_generation"] != body["lease_generation"]:
            raise ScriptedServiceError("STALE_LEASE_GENERATION")
        if time.monotonic_ns() >= receipt["expires_monotonic_ns"]:
            raise ScriptedServiceError("PREFLIGHT_RECEIPT_EXPIRED")
        receipt["consumed"] = True
        self._log_command("start_campaign", {"manifest_id": body["manifest_id"]})
        manifest = self.get_manifest_api(body["manifest_id"])
        campaign_id = "campaign-" + uuid.uuid4().hex
        projection = {
            "campaign_id": campaign_id,
            "manifest_id": manifest["manifest_id"],
            "sequence": 1,
            "execution_mode": body["execution_mode"],
            "owner_kind": (
                "ADAPTIVE_WRAPPER" if body["execution_mode"] == "ADAPTIVE" else "COORDINATOR"
            ),
            "batch_id": "batch-" + uuid.uuid4().hex[:5],
            "status": "RUNNING",
            "points": tuple(
                {
                    "point_id": point["id"],
                    "display_id": point["display_id"],
                    "status": "UNRUN",
                    "retry_eligible": False,
                    "active_worker_id": None,
                    "reason": None,
                    "attempts": (),
                    "artifact_ids": (),
                    "artifacts": (),
                }
                for point in manifest["points"]
            ),
            "workers": (),
            "broker": {"available": True, "reason": None},
            "requested": manifest["point_count"],
            "evaluated": 0,
            "execution_started": 0,
            "valid_succeeded": 0,
            "valid_failed": 0,
            "indeterminate": 0,
            "not_executed": manifest["point_count"],
            "evaluation_coverage": 0.0,
            "execution_coverage": 0.0,
            "qualified_success_rate": None,
            "coverage_complete": False,
            "execution_complete": False,
            "batch_cleanup_complete": False,
            "qualification_passed": None,
            "levels_used": (),
            "fallback_history": (),
            "current_generation": None,
            "infra_attempts": 0,
            "resource_observations": {},
        }
        self._campaigns[campaign_id] = projection
        result = copy.deepcopy(projection)
        self._commands[body["command_id"]] = {
            "request_sha256": digest,
            "result": result,
        }
        return result

    def list_campaigns(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(campaign) for campaign in self._campaigns.values()]

    def get_campaign(self, campaign_id: str) -> dict[str, Any]:
        try:
            return copy.deepcopy(self._campaigns[campaign_id])
        except KeyError as error:
            raise ScriptedServiceError("VALIDATION_CAMPAIGN_NOT_FOUND") from error

    def cancel_campaign(self, campaign_id: str, body: dict[str, Any]) -> dict[str, Any]:
        self._authorize_lease(
            body["lease_id"], body["lease_generation"], body["service_session_id"]
        )
        self._log_command("cancel_campaign", {"campaign_id": campaign_id})
        campaign = self.get_campaign(campaign_id)
        campaign["status"] = "CANCELLED"
        campaign["batch_cleanup_complete"] = True
        for point in campaign["points"]:
            if point["status"] in {"UNRUN", "RUNNING"}:
                point["status"] = "UNRUN"
                point["active_worker_id"] = None
        self._campaigns[campaign_id] = campaign
        return copy.deepcopy(campaign)

    async def retry_campaign(self, campaign_id: str, body: dict[str, Any]) -> dict[str, Any]:
        self._authorize_lease(
            body["lease_id"], body["lease_generation"], body["service_session_id"]
        )
        self._log_command(
            "retry_campaign", {"campaign_id": campaign_id, "point_ids": list(body["point_ids"])}
        )
        campaign = self.get_campaign(campaign_id)
        if campaign["status"] not in {"COMPLETED", "COMPLETED_WITH_FAILURES"} or not campaign[
            "batch_cleanup_complete"
        ]:
            raise ScriptedServiceError("RETRY_NOT_AVAILABLE")
        by_id = {point["point_id"]: point for point in campaign["points"]}
        for point_id in body["point_ids"]:
            point = by_id.get(point_id)
            if point is None or not point["retry_eligible"] or point["status"] != "FAILED":
                raise ScriptedServiceError("RETRY_POINT_NOT_ELIGIBLE")
        for index, point_id in enumerate(body["point_ids"]):
            point = by_id[point_id]
            outcome = self._retry_results.get(point_id, "PASSED")
            attempts = list(point["attempts"])
            attempts.append(
                {
                    "generation": len(attempts) + 1,
                    "status": outcome,
                    "reason": None if outcome == "PASSED" else "TARGET_TOLERANCE_EXCEEDED",
                    "kind": "FULL_RESTART_RETRY",
                    "attempt_id": f"retry-attempt-{index + 1}",
                    "worker_id": "worker-retry-01",
                    "worker_generation": 1,
                    "batch_id": f"retry-batch-{index + 1}",
                }
            )
            point["attempts"] = tuple(attempts)
            if outcome == "PASSED":
                point["status"] = "PASSED"
                point["retry_eligible"] = False
                point["reason"] = None
        campaign["sequence"] += 1
        self._campaigns[campaign_id] = campaign
        self._publish(campaign_id, campaign["sequence"], "RETRY_COMMITTED")
        return copy.deepcopy(campaign)

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    # -- test control surface (separate port, never product routes) --------

    def emit_next(self) -> dict[str, Any]:
        """Apply the next scripted event and publish its hint with faults."""

        if self._emit_index >= len(self.scenario.event_script):
            return {"emitted": None}
        event = self.scenario.event_script[self._emit_index]
        self._emit_index += 1
        faults = {fault.kind: fault.value for fault in self.scenario.faults}
        campaign_id = next(reversed(self._campaigns))
        campaign = self._campaigns[campaign_id]
        patch = event.patch or {}
        scalar_patch = {
            key: value for key, value in patch.items() if key not in {"points", "workers"}
        }
        _deep_merge(campaign, scalar_patch)
        point_patch = patch.get("points")
        if point_patch:
            merged_points = []
            for point in campaign["points"]:
                update = point_patch.get(point["point_id"])
                if update:
                    merged = copy.deepcopy(point)
                    _deep_merge(merged, update)
                    merged_points.append(merged)
                else:
                    merged_points.append(point)
            campaign["points"] = merged_points
        worker_patch = patch.get("workers")
        if worker_patch:
            existing = {worker["worker_id"]: worker for worker in campaign["workers"]}
            for worker_id, update in worker_patch.items():
                merged = existing.get(worker_id, {"worker_id": worker_id})
                _deep_merge(merged, update)
                existing[worker_id] = merged
            campaign["workers"] = list(existing.values())
        campaign["sequence"] = event.sequence
        if faults.get("ws_disconnect"):
            self._publish_ws_close()
        held = self._held_late
        if faults.get("late_sequence") == event.sequence:
            self._held_late = (campaign_id, event.sequence, event.hint)
        elif faults.get("omit_sequence") == event.sequence:
            pass
        else:
            self._publish(campaign_id, event.sequence, event.hint)
            if faults.get("duplicate_sequence") == event.sequence:
                self._publish(campaign_id, event.sequence, event.hint)
            if held is not None:
                self._publish(*held)
                self._held_late = None
        return {"emitted": event.sequence, "campaign_id": campaign_id}

    def emit_all(self) -> list[dict[str, Any]]:
        results = []
        while True:
            result = self.emit_next()
            if result["emitted"] is None:
                return results
            results.append(result)

    def force_expire_lease(self) -> None:
        if self._lease is not None:
            self._lease["expires_monotonic_ns"] = time.monotonic_ns() - 1


def create_scripted_validation_app(
    scenario: ScriptedScenario,
    scenario_sha256: str,
    static_dir: str | Path | None = None,
) -> FastAPI:
    """Wrap the production routes around the scripted service port."""

    service = ScriptedValidationService(scenario, scenario_sha256)
    app = create_expert_validation_app(service, static_dir)
    app.state.scripted_service = service
    return app


def create_scripted_control_app(service: ScriptedValidationService) -> FastAPI:
    """Separate test-control port; never mounted on the product app."""

    control = FastAPI(title="SO-101 scripted control", docs_url=None, openapi_url=None)

    @control.get("/control/state")
    async def state() -> dict[str, Any]:
        return {
            "scenario_id": service.scenario.scenario_id,
            "scenario_sha256": service.scenario_sha256,
            "emitted_sequences": list(service.emitted_sequences),
            "remaining_events": len(service.scenario.event_script) - service._emit_index,
            "lease": (
                None
                if service._lease is None
                else {key: service._lease[key] for key in (
                    "lease_id", "service_session_id", "generation", "state")}
            ),
        }

    @control.get("/control/commands")
    async def commands() -> list[dict[str, Any]]:
        return list(service.command_log)

    @control.post("/control/emit")
    async def emit() -> dict[str, Any]:
        return service.emit_next()

    @control.post("/control/emit-all")
    async def emit_all() -> list[dict[str, Any]]:
        return service.emit_all()

    @control.post("/control/expire-lease")
    async def expire_lease() -> dict[str, Any]:
        service.force_expire_lease()
        return {"expired": True}

    @control.post("/control/renew-lease")
    async def renew_lease() -> dict[str, Any]:
        lease = service._lease
        if lease is None:
            raise ScriptedServiceError("LEASE_NOT_ACTIVE")
        return service.renew_lease(
            lease["lease_id"],
            {
                "service_session_id": lease["service_session_id"],
                "generation": lease["generation"],
            },
        )

    return control
