"""ACT memory inference capture under the existing Worker point and Stop protocol."""

from so101_demo.parallel_batch.act_inference import ActInferenceFrame
from so101_demo.runtime.parallel_worker_runtime import ParallelWorkerRuntime
from so101_demo.runtime.parallel_worker_parts.process_tree import _finite_timestamp


class ActWorkerRuntime(ParallelWorkerRuntime):
    def __init__(self, *args, capture_act_frame, **kwargs):
        if not callable(capture_act_frame):
            raise ValueError("ACT_CAPTURE_PORT_REQUIRED")
        super().__init__(*args, **kwargs)
        self._capture_act_frame = capture_act_frame

    def reset_point(self, lease):
        receipt = super().reset_point(lease)
        self._inference_receipts.clear()
        return receipt

    def _capture_inference_rgb(self, lease, boundary):
        self._execution_allowed()
        boundary = _finite_timestamp("capture boundary", boundary)
        key = self._lease_key(lease)
        if key in self._inference_receipts:
            raise RuntimeError("ACT_CAPTURE_ALREADY_EXISTS")
        frame = self._capture_act_frame(lease, boundary)
        if type(frame) is not ActInferenceFrame:
            raise RuntimeError("ACT_MEMORY_FRAME_REQUIRED")
        if frame.source_stamp_monotonic_s <= boundary:
            raise RuntimeError("inference RGB source stamp is not newer than boundary")
        reset = self._reset_receipts[key]
        if frame.source_stamp_ns / 1e9 <= reset.simulation_time_s:
            raise RuntimeError("inference RGB is not newer than reset simulation watermark")
        if frame.simulation_session_id != reset.simulation_session_id:
            raise RuntimeError("inference RGB simulation session mismatch")
        self._inference_receipts[key] = frame
        return frame

    def inference_snapshot(self, lease):
        """Return the captured memory frame for this exact live lease."""
        self._execution_allowed()
        key = self._lease_key(lease)
        try:
            frame = self._inference_receipts[key]
        except KeyError as error:
            raise RuntimeError("lease identity has no ACT inference frame") from error
        if type(frame) is not ActInferenceFrame or frame.simulation_session_id != self.resources.session_id:
            raise RuntimeError("ACT_CAPTURE_IDENTITY_MISMATCH")
        return frame
