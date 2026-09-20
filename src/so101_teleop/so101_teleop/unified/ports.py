"""Pure service ports for the unified web app.

These protocols describe what the aggregated routers may call. They import no ROS and no
concrete service, so the app factory can be built and schema-exported in an environment
without ROS. ``schema_services`` supplies a schema-only implementation; it is never a
production execution switch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Protocol

from .contracts import QualificationView


class BudgetSource(Protocol):
    """Upstream worker-qualification provider, consumed read-only."""

    def decision(self, selected_n: int, runtime_identity: str) -> QualificationView: ...


class UnknownBudgetSource:
    """Fail-closed stand-in used until the reviewed upstream provider is integrated."""

    contract_version = 2

    def decision(self, selected_n: int, runtime_identity: str) -> QualificationView:
        return QualificationView(
            selected_n=selected_n,
            status="UNKNOWN",
            reasons=("BUDGET_PROVIDER_NOT_READY",),
            runtime_identity=runtime_identity,
            contract_version=self.contract_version,
            profile_sha256=None,
            approval_sha256=None,
        )


class TeleopPort(Protocol):
    def health(self) -> Awaitable[dict]: ...

    def current_snapshot(self) -> Awaitable[Any]: ...

    def capabilities(self) -> Awaitable[dict]: ...

    def camera_presets(self) -> Awaitable[dict]: ...

    def telemetry_wait(self) -> Awaitable[None]: ...

    def command(self, name: str, body: dict) -> Awaitable[Any]: ...

    def execute_plan(self, plan_id: str, body: dict) -> Awaitable[Any]: ...


class TasksArtifactPort(Protocol):
    root: Path

    def open(self, artifact_id: str) -> Any: ...

    def register_file(self, path: Path, media_type: str) -> Any: ...


class TasksPort(Protocol):
    artifacts: TasksArtifactPort

    def presets(self) -> Awaitable[dict]: ...

    def reachability(self, body: Any) -> Awaitable[Any]: ...

    def start(self, body: Any) -> Awaitable[Any]: ...

    def list_runs(self) -> Awaitable[list]: ...

    def status(self, run_id: str) -> Awaitable[Any]: ...

    def cancel(self, run_id: str, body: Any) -> Awaitable[Any]: ...

    def recovery(self, run_id: str, body: Any) -> Awaitable[Any]: ...

    def capture(self, body: Any) -> Awaitable[Any]: ...

    def rendered_image(self, capture_id: str, body: Any) -> Awaitable[Any]: ...

    def shutdown(self, body: Any) -> Awaitable[Any]: ...

    def subscribe(self, maxsize: int = 64) -> Any: ...

    def unsubscribe(self, queue: Any) -> None: ...


class ValidationArtifactPort(Protocol):
    def resolve_opaque_id(self, artifact_id: str) -> Any: ...


class ValidationPort(Protocol):
    artifacts: ValidationArtifactPort

    def health(self) -> Any: ...

    def capabilities(self) -> Any: ...

    def acquire_lease(self, body: dict) -> Any: ...

    def renew_lease(self, lease_id: str, body: dict) -> Any: ...

    def release_lease(self, lease_id: str, body: dict) -> Any: ...

    def create_manifest_from_count(self, total_points: int) -> Any: ...

    def get_manifest_api(self, manifest_id: str) -> Any: ...

    def preflight_api(self, body: dict) -> Any: ...

    def start_campaign_api(self, body: dict) -> Any: ...

    def list_campaigns(self) -> Any: ...

    def get_campaign(self, campaign_id: str) -> Any: ...

    def cancel_campaign(self, campaign_id: str, body: dict) -> Any: ...

    def retry_campaign(self, campaign_id: str, body: dict) -> Any: ...

    def subscribe(self, maxsize: int = 64) -> Any: ...

    def unsubscribe(self, queue: Any) -> None: ...


class ExecutionPort(Protocol):
    """The innermost validation execution seam (argv construction)."""

    def fixed_argv(self, request: Any) -> tuple[str, ...]: ...

    def adaptive_argv(self, request: Any) -> tuple[str, ...]: ...


@dataclass
class UnifiedServices:
    teleop: TeleopPort | None
    tasks: TasksPort | None
    validation: ValidationPort | None
    arbiter: Any = None
    instances: Any = None
    safety: Any = None
    bridge: Any = None
    budget_source: BudgetSource = field(default_factory=UnknownBudgetSource)
    lifecycle: Any = None
    #: True for the schema-only composition used by OpenAPI export and route tests.
    schema_only: bool = False

    def domain_ready(self) -> dict[str, str]:
        return {
            "teleop": "ready" if self.teleop is not None else "unavailable",
            "tasks": "ready" if self.tasks is not None else "unavailable",
            "validation": "ready" if self.validation is not None else "unavailable",
        }
