"""Read-only adapter over the independently owned worker-qualification provider.

This module consumes the budget task's reviewed decision. It never invents a formula,
never synthesises a qualification number, and never falls back to a lower N: an unknown or
rejected exact N blocks the start instead of quietly choosing a smaller batch.
"""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import MutationError, QualificationView
from .ports import BudgetSource, UnknownBudgetSource

SUPPORTED_CONTRACT_VERSION = 2
STATUS_AVAILABLE = "AVAILABLE"
STATUS_UNKNOWN = "UNKNOWN"
STATUS_REJECTED = "REJECTED"
PROVIDER_NOT_READY = "BUDGET_PROVIDER_NOT_READY"


@dataclass(frozen=True)
class BudgetAdapter:
    source: BudgetSource
    contract_version: int = SUPPORTED_CONTRACT_VERSION

    def status(self, selected_n: int, *, runtime_identity: str) -> QualificationView:
        """Return the provider's own view for this exact N and runtime, unmodified."""
        try:
            view = self.source.decision(selected_n, runtime_identity)
        except Exception as error:  # noqa: BLE001 - a broken provider is UNKNOWN, not fatal
            return QualificationView(
                selected_n=selected_n,
                status=STATUS_UNKNOWN,
                reasons=(f"BUDGET_PROVIDER_ERROR: {type(error).__name__}",),
                runtime_identity=runtime_identity,
                contract_version=self.contract_version,
                profile_sha256=None,
                approval_sha256=None,
            )
        return view

    def require_start(self, selected_n: int, *, runtime_identity: str) -> QualificationView:
        """Fresh, live qualification check performed immediately before a start."""
        view = self.status(selected_n, runtime_identity=runtime_identity)
        if view.selected_n != selected_n:
            raise MutationError(
                f"SELECTED_N_MISMATCH: provider answered for {view.selected_n}, not {selected_n}"
            )
        if view.contract_version != self.contract_version:
            raise MutationError(
                f"CONTRACT_VERSION_UNSUPPORTED: {view.contract_version} != {self.contract_version}"
            )
        if view.runtime_identity != runtime_identity:
            raise MutationError(
                f"RUNTIME_IDENTITY_MISMATCH: {view.runtime_identity} != {runtime_identity}"
            )
        if view.status != STATUS_AVAILABLE:
            reasons = ", ".join(view.reasons) or "no reason reported"
            raise MutationError(f"{view.status}: {reasons}")
        if not view.profile_sha256 or not view.approval_sha256:
            raise MutationError(
                f"QUALIFICATION_NOT_PROMOTED: {selected_n} lacks a promoted profile/approval hash"
            )
        return view


def unavailable_source() -> UnknownBudgetSource:
    """The fail-closed source used until the upstream provider is integrated."""
    return UnknownBudgetSource()


__all__ = [
    "BudgetAdapter",
    "BudgetSource",
    "PROVIDER_NOT_READY",
    "QualificationView",
    "STATUS_AVAILABLE",
    "STATUS_REJECTED",
    "STATUS_UNKNOWN",
    "SUPPORTED_CONTRACT_VERSION",
    "unavailable_source",
]
