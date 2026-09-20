"""Budget adapter tests: exact N, no downgrade, no cached profile, no bypass."""

from __future__ import annotations

import pytest

from so101_teleop.unified.budget_adapter import (
    STATUS_AVAILABLE,
    BudgetAdapter,
    QualificationView,
    unavailable_source,
)
from so101_teleop.unified.contracts import MutationError


class RejectedSource:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    def decision(self, selected_n, runtime_identity):
        self.calls.append((selected_n, runtime_identity))
        return QualificationView(selected_n, "REJECTED", ("R_CHANGED",), runtime_identity, 2, None, None)


class AvailableSource:
    def __init__(self, *, contract_version: int = 2) -> None:
        self.contract_version = contract_version
        self.calls: list[tuple[int, str]] = []

    def decision(self, selected_n, runtime_identity):
        self.calls.append((selected_n, runtime_identity))
        return QualificationView(
            selected_n,
            STATUS_AVAILABLE,
            (),
            runtime_identity,
            self.contract_version,
            "profile-sha",
            "approval-sha",
        )


class ExplodingSource:
    def decision(self, selected_n, runtime_identity):
        raise RuntimeError("provider offline")


def test_exact_n_never_downgrades_or_uses_cached_profile():
    source = RejectedSource()
    adapter = BudgetAdapter(source)
    assert adapter.status(8, runtime_identity="new-R").selected_n == 8
    with pytest.raises(MutationError, match="R_CHANGED"):
        adapter.require_start(8, runtime_identity="new-R")
    assert source.calls == [(8, "new-R"), (8, "new-R")]


@pytest.mark.parametrize("selected_n", [2, 3, 4, 5, 6, 7, 8])
def test_unknown_provider_keeps_every_n_disabled(selected_n):
    adapter = BudgetAdapter(unavailable_source())
    view = adapter.status(selected_n, runtime_identity="R")
    assert view.selected_n == selected_n
    assert view.status == "UNKNOWN"
    assert view.reasons == ("BUDGET_PROVIDER_NOT_READY",)
    with pytest.raises(MutationError, match="BUDGET_PROVIDER_NOT_READY"):
        adapter.require_start(selected_n, runtime_identity="R")


def test_available_exact_n_requires_a_promoted_profile_and_approval():
    adapter = BudgetAdapter(AvailableSource())
    view = adapter.require_start(5, runtime_identity="R")
    assert view.selected_n == 5 and view.status == STATUS_AVAILABLE
    assert view.profile_sha256 == "profile-sha" and view.approval_sha256 == "approval-sha"


def test_provider_answering_for_a_different_n_is_refused():
    class WrongN:
        def decision(self, selected_n, runtime_identity):
            return QualificationView(
                selected_n - 1, STATUS_AVAILABLE, (), runtime_identity, 2, "p", "a"
            )

    adapter = BudgetAdapter(WrongN())
    with pytest.raises(MutationError, match="SELECTED_N_MISMATCH"):
        adapter.require_start(6, runtime_identity="R")


def test_v1_contract_is_refused_without_silently_accepting_it():
    adapter = BudgetAdapter(AvailableSource(contract_version=1))
    with pytest.raises(MutationError, match="CONTRACT_VERSION_UNSUPPORTED"):
        adapter.require_start(4, runtime_identity="R")


def test_available_without_hashes_is_not_promoted():
    class NoHashes:
        def decision(self, selected_n, runtime_identity):
            return QualificationView(selected_n, STATUS_AVAILABLE, (), runtime_identity, 2, None, None)

    adapter = BudgetAdapter(NoHashes())
    with pytest.raises(MutationError, match="QUALIFICATION_NOT_PROMOTED"):
        adapter.require_start(4, runtime_identity="R")


def test_provider_failure_becomes_unknown_with_an_explicit_reason():
    adapter = BudgetAdapter(ExplodingSource())
    view = adapter.status(7, runtime_identity="R")
    assert view.status == "UNKNOWN"
    assert view.reasons == ("BUDGET_PROVIDER_ERROR: RuntimeError",)
    with pytest.raises(MutationError, match="UNKNOWN"):
        adapter.require_start(7, runtime_identity="R")


def test_retry_stays_a_single_point_full_restart_context():
    """An operator retry is its own N1 context, never a downgrade of a rejected N."""
    adapter = BudgetAdapter(unavailable_source())
    with pytest.raises(MutationError, match="BUDGET_PROVIDER_NOT_READY"):
        adapter.require_start(1, runtime_identity="R")
    assert adapter.status(1, runtime_identity="R").selected_n == 1


def test_lifecycle_start_gate_uses_the_adapter_without_a_cached_view():
    from so101_teleop.unified.lifecycle import UnifiedLifecycle
    from so101_teleop.unified.ports import UnifiedServices

    composition = UnifiedServices(
        teleop=None, tasks=None, validation=None, budget_source=unavailable_source()
    )
    lifecycle = UnifiedLifecycle(composition)
    with pytest.raises(MutationError, match="BUDGET_PROVIDER_NOT_READY"):
        lifecycle.require_start(4, runtime_identity="R")
    composition.budget_source = AvailableSource()
    assert lifecycle.require_start(4, runtime_identity="R").status == STATUS_AVAILABLE
