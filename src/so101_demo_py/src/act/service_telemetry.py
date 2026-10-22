"""What the policy service did for an episode, from the step rows: outcomes counted, queue wait, inference time and round trip.

The timing gate of the parallel rollout (design 2026-10-22, "Timing gate") judges the inference round trip and the late replies. A
step row that carries a `service` account (the policy service's reply for that request) gives one sample; the episode's result and
the run's summary report the samples as counts by outcome and p50/p95/p99/max of the three times. Pure: no process, no clock.
"""

from __future__ import annotations

from collections import Counter

from .goal_pair_telemetry import latency_stats


def sample_from_row(row: dict):
    """`{outcome, queue_wait_ms, inference_ms, round_trip_s}` of a step row that carries a service account, else None.

    The round trip is the client's wall time from sending the request to having the reply: `latency_wall_s` of an applied step, or
    `reply_wall_s - submit_wall_s` of a late one."""

    service = row.get("service")
    if not isinstance(service, dict):
        return None
    round_trip = row.get("latency_wall_s")
    if round_trip is None and row.get("reply_wall_s") is not None and row.get("submit_wall_s") is not None:
        round_trip = round(row["reply_wall_s"] - row["submit_wall_s"], 6)
    return {"outcome": service.get("outcome"), "queue_wait_ms": service.get("queue_wait_ms"),
            "inference_ms": service.get("inference_ms"), "round_trip_s": round_trip}


def summarize_service(samples) -> dict:
    """Counts by outcome and the statistics of each time over `samples` (a time a sample lacks is left out of its statistics)."""

    samples = list(samples)
    return {"replies": len(samples), "outcomes": dict(Counter(sample["outcome"] for sample in samples)),
            "queue_wait_ms": latency_stats(s["queue_wait_ms"] for s in samples if s["queue_wait_ms"] is not None),
            "inference_ms": latency_stats(s["inference_ms"] for s in samples if s["inference_ms"] is not None),
            "round_trip_s": latency_stats(s["round_trip_s"] for s in samples if s["round_trip_s"] is not None)}


def merge_summaries(summaries) -> dict:
    """Only the counts add up across episodes; the statistics of a run are computed from the samples (`summarize_service`)."""

    outcomes = Counter()
    replies = 0
    for summary in summaries:
        replies += summary["replies"]
        outcomes.update(summary["outcomes"])
    return {"replies": replies, "outcomes": dict(outcomes)}
