"""Runtime memory setting of a rollout (T0b): keep the long-lived heap out of the cyclic collector's way.

A generation-2 collection walks every tracked object; with the model, lerobot and ROS loaded that took 70-120 ms, about four times an
episode, and held the GIL for all of it. `gc.freeze()` moves the current objects to the permanent generation, which no collection
visits. A `gc.collect()` first, so that cyclic garbage is freed rather than frozen. This changes memory timing only, never control logic.
"""

import gc
import time


def freeze_heap():
    """collect, then freeze; returns the record that goes into the episode / run evidence."""

    started = time.monotonic()
    collected = gc.collect()
    frozen_before = gc.get_freeze_count()
    gc.freeze()
    return {"collected": collected, "frozen_before": frozen_before, "frozen_after": gc.get_freeze_count(),
            "duration_s": time.monotonic() - started, "monotonic_s": time.monotonic()}
