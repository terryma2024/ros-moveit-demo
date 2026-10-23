"""What the policy service did for an episode, computed from step rows (pure)."""

import pytest

from so101_demo.act.service_telemetry import merge_summaries, sample_from_row, summarize_service


def test_an_applied_step_gives_its_service_account_and_the_clients_round_trip():
    row = {"applied": True, "latency_wall_s": 0.0213,
           "service": {"outcome": "OK", "queue_wait_ms": 2.5, "inference_ms": 11.0, "bundle_sha256": "a" * 64}}
    assert sample_from_row(row) == {"outcome": "OK", "queue_wait_ms": 2.5, "inference_ms": 11.0, "round_trip_s": 0.0213}


def test_a_late_step_gives_the_round_trip_from_its_submit_and_reply_times():
    row = {"late": True, "submit_wall_s": 100.0, "reply_wall_s": 100.4,
           "service": {"outcome": "QUEUE_TIMEOUT", "queue_wait_ms": 90.0, "inference_ms": None}}
    assert sample_from_row(row) == {"outcome": "QUEUE_TIMEOUT", "queue_wait_ms": 90.0, "inference_ms": None, "round_trip_s": 0.4}


def test_a_row_without_a_service_account_gives_no_sample():
    assert sample_from_row({"applied": True, "latency_wall_s": 0.01}) is None
    assert sample_from_row({"skipped": True, "service": "not a dict"}) is None


def test_the_summary_counts_outcomes_and_takes_statistics_of_the_times_that_exist():
    samples = [{"outcome": "OK", "queue_wait_ms": float(index), "inference_ms": 10.0 + index, "round_trip_s": 0.02 + index / 1000}
               for index in range(1, 6)]
    samples.append({"outcome": "QUEUE_FULL", "queue_wait_ms": None, "inference_ms": None, "round_trip_s": 0.001})
    summary = summarize_service(samples)
    assert summary["replies"] == 6 and summary["outcomes"] == {"OK": 5, "QUEUE_FULL": 1}
    assert summary["queue_wait_ms"] == {"n": 5, "p50": 3.0, "p95": pytest.approx(4.8), "p99": pytest.approx(4.96), "max": 5.0}
    assert summary["inference_ms"]["n"] == 5 and summary["inference_ms"]["max"] == 15.0
    assert summary["round_trip_s"]["n"] == 6 and summary["round_trip_s"]["max"] == pytest.approx(0.025)


def test_no_sample_gives_empty_statistics():
    summary = summarize_service([])
    assert summary["replies"] == 0 and summary["outcomes"] == {} and summary["queue_wait_ms"]["p50"] is None


def test_summaries_of_episodes_add_their_counts():
    merged = merge_summaries([{"replies": 3, "outcomes": {"OK": 2, "QUEUE_FULL": 1}}, {"replies": 2, "outcomes": {"OK": 2}}])
    assert merged == {"replies": 5, "outcomes": {"OK": 4, "QUEUE_FULL": 1}}
