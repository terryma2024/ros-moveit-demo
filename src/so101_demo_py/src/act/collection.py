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
