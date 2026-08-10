from collections import deque

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
    def __init__(self, values) -> None:
        self.values = deque(values)
        self.calls = 0

    def snapshot(self) -> SimulationEvidence:
        self.calls += 1
        return self.values.popleft()


def corroboration() -> OutcomeCorroboration:
    return OutcomeCorroboration(
        moveit_detached=True,
        controller_healthy=True,
        safety_healthy=True,
        shadow_divergence_healthy=True,
    )


def test_release_settle_collects_only_active_epoch_until_success() -> None:
    observer = Observer(evidence(index) for index in range(5))
    now = [0.0]
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
    observer = Observer(evidence(index, supported=False) for index in range(42))

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
    observer = Observer(
        [evidence(index) for index in range(3)]
        + [evidence(index, reset_epoch=3) for index in range(3, 43)]
    )
    now = [0.0]
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
