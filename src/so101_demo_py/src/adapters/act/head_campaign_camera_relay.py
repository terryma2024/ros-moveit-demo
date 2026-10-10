"""Owned delivery gate for real camera messages, with no new source or clocks."""
import threading
import time
import uuid


class HeadCampaignCameraRelay:
    def __init__(self, *, emit=None):
        self._lock = threading.RLock()
        self.open = True
        self.emit = emit

    def deliver(self, original, callback):
        # Serialize cut against callbacks so its receipt marks the last possible
        # delivery. Forward the original object without editing Header or bytes.
        with self._lock:
            if self.open:
                callback(original)

    def cut_after_sdk_return(self, receipt):
        try:
            goal = uuid.UUID(receipt['goal_uuid'])
            if receipt['status'] != 'SUBMITTED' or goal.version != 4:
                raise ValueError()
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise ValueError('HEAD_CAMERA_CUT_REQUIRES_SDK_UUID') from error
        with self._lock:
            if not self.open:
                raise PermissionError('HEAD_CAMERA_ALREADY_CUT')
            self.open = False
            if self.emit is not None:
                self.emit('CAMPAIGN_CAMERA_DELIVERY_CUT', goal_uuid=str(goal),
                          occurred_ns=time.monotonic_ns(), before_locked=True)

    def close(self):
        with self._lock:
            self.open = False
