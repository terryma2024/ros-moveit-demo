"""L2 6062afd8 refused the verified reset with COLLECTION_RESET_RECEIPT_INVALID for 8 s.

The Recorder's first retained world record that still has its raw physics step was a record it received when it JOINED the
transient-local world topic: published seconds earlier, received at the join. The V3 validator required the receipt to lie within
0.5 s of the producer's interval end, so every replayed record was refused until the raw ring (8.2 s) rolled past them and the
capture started 8 s late. The receipt is metadata: it only has to follow the producer's interval end."""
import pytest

from so101_demo.act.collection_boundaries import validate_verified_reset

IDENTITY = dict(session_id="s", attempt_id="a", reset_epoch=1)


def boundary(received_after_end_s):
    end = 8_000_000_000
    return dict(kind="ACT_VERIFIED_RESET_BOUNDARY", schema_version=3, **IDENTITY,
                source_clock=dict(sim_time_ns=3_000_000_000, begin_monotonic_ns=end - 100, end_monotonic_ns=end),
                physical_source=dict(session_id="s", reset_epoch=1, simulation_step=1500, publisher_sequence=250,
                                     simulation_time_s=3.0, received_wall_s=end / 1e9 + received_after_end_s))


@pytest.mark.parametrize("delay_s", [0.0, 0.001, 0.4, 3.1, 8.0])
def test_a_replayed_record_received_seconds_after_it_was_produced_is_a_valid_first_evidence(delay_s):
    validate_verified_reset(boundary(delay_s), identity=IDENTITY)


def test_a_receipt_before_the_producers_interval_ended_is_still_refused():
    with pytest.raises(ValueError, match="COLLECTION_RESET_RECEIPT_INVALID"):
        validate_verified_reset(boundary(-0.001), identity=IDENTITY)
