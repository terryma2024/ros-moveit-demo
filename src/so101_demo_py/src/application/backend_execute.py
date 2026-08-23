"""Backend-neutral conversion of one real action boundary into a run result."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.domain import ActionResult, ActionStatus
from ..runtime.result_manifest import RunResultManifest, classify_run


@dataclass(frozen=True, slots=True)
class ExecuteBoundary:
    phase: str
    action: ActionResult
    evidence_valid: bool
    evidence_refs: tuple[str, ...] = ()


def classify_execute_boundary(
    boundary: ExecuteBoundary,
    *,
    backend: str,
    session_id: str,
    reset_epoch: int,
    source_commit: str,
    installed_prefix: str,
    policy_sha256: str,
    bundle_sha256: str,
) -> RunResultManifest:
    """Keep evidence validity independent from a valid policy/action failure."""

    failure = boundary.action.failure
    succeeded = boundary.action.status is ActionStatus.SUCCEEDED
    error_code = None if succeeded else (
        failure.code if failure is not None and failure.code else boundary.action.status.value
    )
    return classify_run(
        backend=backend,
        session_id=session_id,
        reset_epoch=reset_epoch,
        source_commit=source_commit,
        installed_prefix=installed_prefix,
        policy_sha256=policy_sha256,
        bundle_sha256=bundle_sha256,
        error_code=error_code,
        evidence_valid=boundary.evidence_valid,
        first_failed_phase=None if succeeded else boundary.phase,
        failure_category=None if failure is None else failure.category,
        evidence_refs=boundary.evidence_refs,
        qualified=False,
    )
