from collections import deque

from so101_gazebo_demo.physical_outcome import FinalPlacementSample
from so101_gazebo_demo.release_settle import ReleaseSettleExecutor
from test_physical_outcome import policy, sample


def test_release_settle_collects_only_active_epoch_until_success() -> None:
    observations = deque(
        [sample(0, epoch="old")] + [sample(index) for index in range(5)]
    )
    now = [0.0]
    executor = ReleaseSettleExecutor(
        policy(),
        observe=observations.popleft,
        monotonic=lambda: now[0],
        wait=lambda duration: now.__setitem__(0, now[0] + duration),
        cancelled=lambda: False,
    )
    result = executor.run("release-2", 100)
    assert result.status == "SUCCEEDED"
    assert result.evaluation.success
    assert result.evaluation.sample_count == 5


def test_release_settle_cancellation_preserves_samples() -> None:
    observations = deque([sample(0), sample(1)])
    calls = [0]

    def cancelled() -> bool:
        calls[0] += 1
        return calls[0] > 1

    executor = ReleaseSettleExecutor(
        policy(), observations.popleft, lambda: 0.0, lambda _: None, cancelled,
    )
    result = executor.run("release-2", 100)
    assert result.status == "CANCELLED"
    assert len(result.samples) == 1


def test_release_settle_timeout_returns_final_failure_without_sleeping() -> None:
    now = [0.0]
    sequence = [0]

    def next_sample() -> FinalPlacementSample:
        index = sequence[0]
        sequence[0] += 1
        return sample(index, supported=False)

    executor = ReleaseSettleExecutor(
        policy(), next_sample, lambda: now[0],
        lambda duration: now.__setitem__(0, now[0] + duration), lambda: False,
    )
    result = executor.run("release-2", 100)
    assert result.status == "TIMED_OUT"
    assert result.evaluation.failure_code == "FINAL_UNSUPPORTED"
    assert len(result.samples) <= policy().max_telemetry_samples
