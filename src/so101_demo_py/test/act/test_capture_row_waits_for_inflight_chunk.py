"""CP-3410: a row waits for a chunk that is still in flight; it does not fail on the wall-clock 100 ms.

The old capture failed a row with INPUT_STALE when a source was not ready 100 ms after the row first waited. For the physics chunk
that was the delivery-age rule by another name: a chunk 300 ms late failed the data from the capture side even after the adapter
stopped refusing it. A provider can now say "the physics source for this instant has not arrived yet" (`awaiting_arrival`); the
capture then waits without the timer, and the arrival is bounded by the receiver-lag policy of the physics adapter (the adapter
fails the data when the newest received sample is more than the policy behind now, the Recorder's finish budget bounds the tail)."""
import pytest

from test_act_scene_association import frozen_scene  # noqa: F401  (fixture)

from test_act_continuous_capture import FakeRecorder, FakeSampler, frames_at, physical_audit, reference, start


class Physical:
    def __init__(self):
        self.ready_value, self.awaiting = False, False

    def ready(self, at_s):
        return self.ready_value

    def awaiting_arrival(self, at_s):
        return self.awaiting

    def __call__(self, at_s):
        return physical_audit(at_s)


def capture_with(physical, clock):
    from so101_demo.act.continuous_capture import ContinuousEpisodeCapture
    return ContinuousEpisodeCapture(recorder=FakeRecorder(), sampler=FakeSampler(), physical_audit=physical,
                                    monotonic=lambda: clock[0], asynchronous_sources=True)


def test_a_chunk_still_in_flight_is_waited_for_beyond_100_ms_and_the_row_is_then_written():
    from so101_demo.act.acquisition import AcquisitionMinter
    clock, physical = [0.], Physical()
    physical.awaiting = True
    capture, minter = capture_with(physical, clock), AcquisitionMinter()
    start(capture)
    frames_at(capture, minter, [1.])
    for moment in (0.05, 0.2, 0.9, 3.0):                  # far beyond 100 ms: the chunk is late, not missing
        clock[0] = moment
        assert capture.drain() == 0
    physical.ready_value, physical.awaiting = True, False
    capture.on_reference(reference(1.1))
    frames_at(capture, minter, [1.1, 1.2])
    clock[0] = 3.1
    assert capture.drain() == 1 and capture.recorder.rows[0]["observation"]["sim_time_s"] == 1.0


def test_a_source_that_is_not_in_flight_still_times_out_after_100_ms():
    from so101_demo.act.acquisition import AcquisitionMinter
    clock, physical = [0.], Physical()
    capture, minter = capture_with(physical, clock), AcquisitionMinter()
    start(capture)
    frames_at(capture, minter, [1.])
    assert capture.drain() == 0
    clock[0] = 0.100001
    with pytest.raises(ValueError, match="INPUT_STALE"):
        capture.drain()


def test_the_provider_reports_a_physics_source_that_has_not_arrived_yet(frozen_scene):
    from test_act_live_physical_audit import provider
    source, values, at_s = provider(frozen_scene)
    assert source.awaiting_arrival(at_s) is False          # no hook configured: never "in flight"
    source.physics_awaiting = lambda at: at > 5.0
    assert source.awaiting_arrival(at_s) is (at_s > 5.0)
    assert source.awaiting_arrival(9.0) is True


def test_the_physics_adapter_knows_the_newest_sample_it_has_received():
    from test_late_physics_chunks_are_not_a_failure import adapter, chunk_at
    value, _ = adapter()
    assert value.latest_sample_time_s() is None
    message, receipt = chunk_at(1)
    value.accept_message(message, receipt_ns=receipt)
    assert value.latest_sample_time_s() == pytest.approx(message.samples[-1].simulation_time_s)   # pending counts: it has arrived
