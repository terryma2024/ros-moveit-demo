"""Closed ACT workload port for the existing fixed ParallelWorker lifecycle."""

from __future__ import annotations


class ActCollectionWorkload:
    """Delegate one authorized scenario while retaining Worker lease boundaries."""

    kind = "act_collection"

    def run_authorized(self, lease, *, runtime, broker, boundary,
                       start_event_id, start_event_type, reset_epoch):
        collect = getattr(runtime, "collect_authorized_scenario", None)
        if not callable(collect):
            raise RuntimeError("ACT_COLLECTION_RUNTIME_UNAVAILABLE")
        return boundary(lambda current: collect(
            current, broker=broker, boundary=boundary,
            start_event_id=start_event_id, start_event_type=start_event_type,
            reset_epoch=reset_epoch,
        ))


def training_eligible(record: dict) -> bool:
    """A record enters training only when it is a committed, clean, complete success.

    A business failure is retained as evidence but never exported, and a record whose coordinator has
    not committed is not yet a result — it is a run in progress.
    """

    # fail closed on a missing or malformed field: the plan's own boundary case passes a record that
    # carries neither `status` nor `coordinator_committed` and expects it to be ineligible, so an
    # incomplete record is refused rather than raising out of a gate on training data
    if not isinstance(record, dict):
        return False
    return (record.get("status") == "PASSED" and record.get("qc") == "PASS"
            and record.get("done") is True and record.get("interventions") == 0
            and record.get("coordinator_committed") is True)
