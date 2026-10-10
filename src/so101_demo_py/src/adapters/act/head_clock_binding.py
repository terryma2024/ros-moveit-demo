"""Bind Head originals to the existing ROS TimeSource callback before spin."""
import math


def bind_head_clock(node, observe, *, monotonic):
    source = getattr(node, '_time_source', None)
    subscription = None if source is None else source._clock_sub
    if (source is None or not source.ros_time_is_active or subscription is None
            or getattr(node, 'executor', None) is not None
            or not callable(observe) or not callable(monotonic)
            or subscription.callback != source.clock_callback):
        raise PermissionError('HEAD_CLOCK_BINDING_REFUSED')
    update = subscription.callback

    def original_clock(message):
        receipt = monotonic()
        if type(receipt) not in (int, float) or not math.isfinite(receipt) or receipt < 0:
            raise ValueError('HEAD_CLOCK_BINDING_RECEIPT_INVALID')
        # Update the actual node ROS clock using its unchanged TimeSource first.
        # The original receipt precedes both calls; no source/receipt is replaced.
        update(message)
        observe(message, received_wall_s=receipt)

    subscription.callback = original_clock
    return subscription
