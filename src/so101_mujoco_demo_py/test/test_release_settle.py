from collections import deque
from dataclasses import dataclass, replace
from typing import Callable

from test_physical_outcome import policy

from so101_mujoco_demo_py.release_settle import OutcomeCorroboration, ReleaseSettleExecutor
from so101_mujoco_demo_py.simulation.types import ContactEvidence, ObjectState, SimulationEvidence


def evidence(index: int, *, supported: bool = True, reset_epoch: int = 2) -> SimulationEvidence:
    contacts = (
        (
            ContactEvidence(
                7,
                8,
                "plastic_cup",
                "cup",
                9,
                10,
                "table",
                "table_top",
                (-0.08, -0.25, 0.155),
                (0.0, 0.0, 1.0),
                -1e-7,
                0.2,
            ),
        )
        if supported
        else ()
    )
    return SimulationEvidence(
        10.0 + index * 0.05,
        "world",
        101 + index,
        index,
        reset_epoch,
        "session-a",
        False,
        ObjectState(
            7,
            "plastic_cup",
            (-0.08, -0.25, 0.165),
            (0.0, 0.0, 0.0, 1.0),
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
        ),
        bool(contacts),
        -1e-7 if contacts else 0.0,
        0.2 if contacts else 0.0,
        False,
        (),
        (),
        contacts,
    )


class Observer:
    def __init__(self, values, received_at: Callable[[], float] = lambda: 0.0) -> None:
        self.values = deque(values)
        self.received_at = received_at
        self.calls = 0

    def snapshot(self) -> SimulationEvidence:
        self.calls += 1
        return self.values.popleft()

    def snapshot_with_receipt(self) -> "TimedSnapshot":
        return TimedSnapshot(self.snapshot(), self.received_at())


@dataclass(frozen=True)
class TimedSnapshot:
    evidence: SimulationEvidence
    received_monotonic_s: float


class LooselyFreshObserver(Observer):
    def __init__(self, values, received_at: Callable[[], float]) -> None:
        super().__init__(values, received_at)


def corroboration() -> OutcomeCorroboration:
    return OutcomeCorroboration(
        moveit_detached=True,
        controller_healthy=True,
        safety_healthy=True,
        shadow_divergence_healthy=True,
    )


def test_release_settle_collects_only_active_epoch_until_success() -> None:
    now = [0.0]
    observer = Observer((evidence(index) for index in range(5)), lambda: now[0])
    executor = ReleaseSettleExecutor(
        policy(),
        observer=observer,
        corroborate=corroboration,
        monotonic=lambda: now[0],
        wait=lambda duration: now.__setitem__(0, now[0] + duration),
        cancelled=lambda: False,
    )
    result = executor.run("release-2", 100)
    assert result.status == "SUCCEEDED"
    assert result.evaluation.success
    assert result.evaluation.sample_count == 5
    assert observer.calls == 5


def test_release_settle_records_true_receipt_monotonic_separate_from_sim_time() -> None:
    now = [1000.0]
    observer = Observer((evidence(index) for index in range(5)), lambda: now[0])
    executor = ReleaseSettleExecutor(
        policy(),
        observer,
        corroboration,
        lambda: now[0],
        lambda duration: now.__setitem__(0, now[0] + duration),
        lambda: False,
    )
    result = executor.run("release-2", 100)
    assert result.status == "SUCCEEDED"
    assert result.samples[0].source_timestamp_s == 10.0
    assert result.samples[0].observed_monotonic_s == 1000.0


def test_release_settle_enforces_physical_policy_age_over_looser_observer_cache() -> None:
    now = [10.0]
    physical_policy = replace(policy(), settle_timeout_s=0.21)
    stale_observer = LooselyFreshObserver(
        (evidence(index) for index in range(5)),
        received_at=lambda: now[0] - 0.15,
    )
    stale = ReleaseSettleExecutor(
        physical_policy,
        stale_observer,
        corroboration,
        lambda: now[0],
        lambda duration: now.__setitem__(0, now[0] + duration),
        lambda: False,
    ).run("release-2", 100)
    assert stale.status == "TIMED_OUT"
    assert stale.samples == ()

    now[0] = 10.0
    fresh_observer = LooselyFreshObserver(
        (evidence(index) for index in range(5)),
        received_at=lambda: now[0] - 0.05,
    )
    fresh = ReleaseSettleExecutor(
        physical_policy,
        fresh_observer,
        corroboration,
        lambda: now[0],
        lambda duration: now.__setitem__(0, now[0] + duration),
        lambda: False,
    ).run("release-2", 100)
    assert fresh.status == "SUCCEEDED"
    assert fresh.samples[0].observed_monotonic_s == 9.95


def test_release_settle_cancellation_preserves_samples() -> None:
    observer = Observer((evidence(0), evidence(1)))
    calls = [0]

    def cancelled() -> bool:
        calls[0] += 1
        return calls[0] > 1

    executor = ReleaseSettleExecutor(
        policy(), observer, corroboration, lambda: 0.0, lambda _: None, cancelled
    )
    result = executor.run("release-2", 100)
    assert result.status == "CANCELLED"
    assert len(result.samples) == 1


def test_release_settle_timeout_returns_final_failure_bounded() -> None:
    now = [0.0]
    observer = Observer((evidence(index, supported=False) for index in range(42)), lambda: now[0])

    executor = ReleaseSettleExecutor(
        policy(),
        observer,
        corroboration,
        lambda: now[0],
        lambda duration: now.__setitem__(0, now[0] + duration),
        lambda: False,
    )
    result = executor.run("release-2", 100)
    assert result.status == "TIMED_OUT"
    assert result.evaluation.failure_code == "FINAL_UNSUPPORTED"
    assert len(result.samples) <= policy().max_telemetry_samples


def test_release_settle_rejects_samples_crossing_reset_epoch() -> None:
    now = [0.0]
    observer = Observer(
        [evidence(index) for index in range(3)]
        + [evidence(index, reset_epoch=3) for index in range(3, 43)],
        lambda: now[0],
    )
    executor = ReleaseSettleExecutor(
        policy(),
        observer,
        corroboration,
        lambda: now[0],
        lambda duration: now.__setitem__(0, now[0] + duration),
        lambda: False,
    )
    result = executor.run("release-2", 100, release_reset_epoch=2)
    assert result.status == "TIMED_OUT"
    assert result.evaluation.failure_code == "FINAL_STALE_EVIDENCE"
