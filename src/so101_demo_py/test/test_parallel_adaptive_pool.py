"""Safety contracts for adaptive pool startup readiness."""

from dataclasses import replace
from types import SimpleNamespace

import pytest


def valid_receipt(worker_id="w1", *, generation=1, observed=10.0):
    from so101_demo.parallel_batch.adaptive_pool import WorkerReadinessReceipt

    return WorkerReadinessReceipt(
        worker_id=worker_id,
        generation=generation,
        process_start_ticks=1234,
        coordinator_registered=True,
        runtime_ready=True,
        broker_ready=True,
        broker_generation=1,
        observed_monotonic_s=observed,
    )


def test_worker_cannot_request_a_lease_before_release_start():
    from so101_demo.parallel_batch.adaptive_pool import WorkerStartGate

    gate = WorkerStartGate(expected_worker_id="w1", generation=1)
    gate.record_readiness(valid_receipt("w1", generation=1))

    assert gate.wait_released(timeout_s=0.0) is False
    gate.release("w1", generation=1)
    assert gate.wait_released(timeout_s=0.0) is True


@pytest.mark.parametrize(
    "receipt",
    [
        lambda: valid_receipt("w2"),
        lambda: valid_receipt(generation=2),
        lambda: replace(valid_receipt(), runtime_ready=False),
        lambda: replace(valid_receipt(), broker_ready=False),
    ],
)
def test_start_gate_rejects_wrong_identity_or_incomplete_readiness(receipt):
    from so101_demo.parallel_batch.adaptive_pool import WorkerStartGate

    gate = WorkerStartGate(expected_worker_id="w1", generation=1)

    with pytest.raises(ValueError, match="WORKER_READINESS"):
        gate.record_readiness(receipt())


def test_release_requires_a_recorded_matching_receipt():
    from so101_demo.parallel_batch.adaptive_pool import WorkerStartGate

    gate = WorkerStartGate(expected_worker_id="w1", generation=1)
    with pytest.raises(ValueError, match="WORKER_NOT_READY"):
        gate.release("w1", generation=1)
    gate.record_readiness(valid_receipt())
    with pytest.raises(ValueError, match="WORKER_IDENTITY"):
        gate.release("w2", generation=1)


def test_readiness_receipt_rejects_boolean_numeric_fields():
    from so101_demo.parallel_batch.adaptive_pool import WorkerReadinessReceipt

    with pytest.raises(ValueError, match="PROCESS_START_TICKS"):
        WorkerReadinessReceipt("w1", 1, True, True, True, True, 1, 10.0)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, duration):
        self.now += duration


class HealthySupervisor:
    def __init__(self):
        self.checks = 0

    def assert_healthy(self):
        self.checks += 1


def startup_composition(clock, controls, recorder):
    from so101_demo.cli.mujoco_parallel_batch import ProductionBatchComposition

    composition = object.__new__(ProductionBatchComposition)
    composition._clock = clock
    composition._sleep = clock.sleep
    composition.supervisor = HealthySupervisor()
    composition.worker_controls = controls
    composition._adaptive_worker_processes = {
        control.worker_id: SimpleNamespace(start_time=1234)
        for control in controls
    }
    composition.broker_generation = 1
    composition.adaptive_context = SimpleNamespace(
        options=SimpleNamespace(worker_start_timeout_s=120.0)
    )
    composition._pool_running_recorder = recorder
    return composition


def test_control_socket_appearing_after_six_seconds_uses_shared_120_second_deadline():
    clock = FakeClock()

    class Control:
        worker_id = "w1"
        generation = 1

        def readiness(self):
            return None if clock.now < 6.0 else valid_receipt(observed=clock.now)

        def release_start(self):
            return True

    recorded = []
    composition = startup_composition(clock, [Control()], recorded.append)

    composition._release_adaptive_workers()

    assert clock.now >= 6.0
    assert len(recorded) == 1


def test_worker_ready_timeout_occurs_without_release_or_pool_running_record():
    clock = FakeClock()

    class Control:
        worker_id = "w1"
        generation = 1

        def readiness(self):
            return None

        def release_start(self):
            raise AssertionError("unready worker was released")

    recorded = []
    composition = startup_composition(clock, [Control()], recorded.append)

    from so101_demo.cli.mujoco_parallel_batch import CliError

    with pytest.raises(CliError, match="WORKER_READY_TIMEOUT"):
        composition._release_adaptive_workers()
    assert clock.now == 120.0
    assert recorded == []


def test_second_release_failure_is_after_pool_running_linearization():
    clock = FakeClock()
    order = []

    class Control:
        generation = 1

        def __init__(self, worker_id, succeeds):
            self.worker_id = worker_id
            self.succeeds = succeeds

        def readiness(self):
            return valid_receipt(self.worker_id, observed=clock.now)

        def release_start(self):
            order.append(("release", self.worker_id))
            return self.succeeds

    composition = startup_composition(
        clock,
        [Control("w1", True), Control("w2", False)],
        lambda receipts: order.append(("pool_running", len(receipts))),
    )

    from so101_demo.cli.mujoco_parallel_batch import CliError

    with pytest.raises(CliError, match="POOL_RUNTIME_RELEASE_FAILED"):
        composition._release_adaptive_workers()
    assert order == [
        ("pool_running", 2),
        ("release", "w1"),
        ("release", "w2"),
    ]


@pytest.mark.parametrize(
    "change",
    [
        {"broker_generation": 2},
        {"observed_monotonic_s": -0.1},
    ],
)
def test_final_readiness_recheck_rejects_wrong_broker_or_stale_receipt(change):
    clock = FakeClock()
    clock.now = 2.0

    class Control:
        worker_id = "w1"
        generation = 1

        def readiness(self):
            values = {
                "broker_generation": 1,
                "observed_monotonic_s": clock.now,
            }
            values.update(change)
            if values["observed_monotonic_s"] < 0:
                values["observed_monotonic_s"] = 0.0
            return replace(valid_receipt(observed=clock.now), **values)

        def release_start(self):
            raise AssertionError("invalid receipt was released")

    composition = startup_composition(clock, [Control()], lambda _receipts: None)

    from so101_demo.cli.mujoco_parallel_batch import CliError

    with pytest.raises(CliError, match="WORKER_READINESS_INVALID"):
        composition._release_adaptive_workers()
