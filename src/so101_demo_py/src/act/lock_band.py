"""The horizontal band a Head Search lock run counts frames in, shared by the controller and the audit."""

# A lock run starts only inside the strict `center_deadband_px`. Once it has started, a frame still counts
# while its horizontal error stays inside `center_deadband_px + LOCK_HOLD_MARGIN_PX`. The margin absorbs the
# centre jitter of a partially occluded mask at a fixed pose, which moved one bbox edge by a few pixels between
# frames of an unchanged pose while the run was one frame from locking. It is deliberately not a config key.
LOCK_HOLD_MARGIN_PX = 3.0


def lock_band_px(deadband_px, lock_count):
    """Inclusive half-width of the band: strict to start a run, widened once a run is running."""
    return deadband_px + LOCK_HOLD_MARGIN_PX if lock_count >= 1 else deadband_px


def counts_for_lock(error_px, centre_row_px, *, deadband_px, vertical_bounds_px, lock_count):
    """True when a frame extends (or starts, at lock_count 0) the lock run."""
    return (abs(error_px) <= lock_band_px(deadband_px, lock_count)
            and vertical_bounds_px[0] <= centre_row_px <= vertical_bounds_px[1])
