"""Compatibility surface for the SO-101 web API.

The route table itself lives in one place now: `so101_teleop.unified.app`. This module used to hold a
second, hand-maintained copy of the Teleop routes; that copy was migrated onto the unified app and
deleted (implementation ledger CP-67 through CP-83). What remains here is the small surface other
modules legitimately still import:

- ``validate_bind_address``, re-exported from the leaf policy module;
- the model re-exports below, which ``expert_validation/production.py`` imports from this path.
"""

from __future__ import annotations

from .models import (
    BackendCapabilitiesResponse,
    CaptureResponse,
    CommandResult,
    ReachabilityResponse,
    RenderedImageRequest,
    TaskCaptureRequest,
    TaskMutationRequest,
    TaskRecoveryRequest,
    TaskRunRequest,
    TaskRunSummary,
    TaskShutdownRequest,
    TelemetrySnapshot,
)

from .bind_policy import validate_bind_address

__all__ = ["validate_bind_address"]
