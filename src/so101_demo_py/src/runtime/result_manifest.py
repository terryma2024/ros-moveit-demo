"""Rich execution and qualification result classification."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..core.domain import ExecutionRunStatus, FailureCategory, QualificationStatus

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class RunResultManifest:
    run_status: ExecutionRunStatus
    qualification_status: QualificationStatus
    backend: str
    session_id: str
    reset_epoch: int
    policy_sha256: str
    bundle_sha256: str
    first_failed_phase: str | None
    failure_category: FailureCategory | None
    error_code: str | None
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.backend or not self.session_id or self.reset_epoch < 0:
            raise ValueError("run identity is invalid")
        if not _SHA256.fullmatch(self.policy_sha256) or not _SHA256.fullmatch(
            self.bundle_sha256
        ):
            raise ValueError("result provenance hashes must be complete SHA-256 values")


def classify_run(
    *,
    backend: str,
    session_id: str,
    reset_epoch: int,
    policy_sha256: str,
    bundle_sha256: str,
    error_code: str | None,
    evidence_valid: bool,
    first_failed_phase: str | None = None,
    failure_category: FailureCategory | None = None,
    evidence_refs: tuple[str, ...] = (),
    rejected: bool = False,
    qualified: bool = False,
) -> RunResultManifest:
    if not evidence_valid:
        run_status = ExecutionRunStatus.INVALID
    elif rejected:
        run_status = ExecutionRunStatus.REJECTED
    elif error_code is not None:
        run_status = ExecutionRunStatus.FAILED
    else:
        run_status = ExecutionRunStatus.SUCCEEDED
    qualification_status = (
        QualificationStatus.QUALIFIED
        if run_status is ExecutionRunStatus.SUCCEEDED and qualified
        else QualificationStatus.NOT_QUALIFIED
    )
    return RunResultManifest(
        run_status,
        qualification_status,
        backend,
        session_id,
        reset_epoch,
        policy_sha256,
        bundle_sha256,
        first_failed_phase,
        failure_category,
        error_code,
        evidence_refs,
    )
