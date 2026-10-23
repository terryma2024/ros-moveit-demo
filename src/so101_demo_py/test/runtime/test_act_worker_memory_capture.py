"""The real Worker point protocol consumes ACT memory frames and retains Stop fences."""

import importlib
from types import SimpleNamespace as NS

import numpy as np
from parallel_worker_runtime_support import _lease, _ProcessGroup, _resources
import pytest


def runtime_case(tmp_path, *, stamp=12_000_000_000, session="session-worker-1"):
    from so101_demo.parallel_batch.act_inference import ActInferenceFrame
    from so101_demo.parallel_batch.contracts.common import RunMode
    from so101_demo.runtime.parallel_worker_parts.process_tree import SourceStampedCapture
    module = importlib.import_module("so101_demo.runtime.act_worker_runtime")
    frame = ActInferenceFrame(np.zeros((4, 5, 3), dtype=np.uint8), 11., stamp,
                              "task_camera_frame", session, "ros_sim", 1)
    def capture(path, boundary):
        assert path.suffix == ".png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"original-image-evidence")
        return SourceStampedCapture(path, boundary + 1., source_stamp_ns=12_000_000_001)
    runtime = module.ActWorkerRuntime(_resources(tmp_path, "worker-1", 0, 181), RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(), capture_act_frame=lambda _lease, _boundary: frame,
        ready_probe=lambda _requirements: True, reset_point=lambda _lease: NS(
            reset_completed_monotonic_s=10., simulation_time_s=10., simulation_session_id="session-worker-1"),
        reserve_workspace=lambda *_args: True, initial_gate=lambda *_args: "gate",
        resume_physics=lambda *_args: True, capture_rgb=capture)
    runtime.start_physical_runtime()
    lease = _lease()
    reset = runtime.reset_point(lease)
    return runtime, lease, reset, frame


def test_worker_initial_gate_uses_memory_frame_without_staged_npy(tmp_path):
    runtime, lease, reset, frame = runtime_case(tmp_path)
    assert runtime.point_initial_gate(lease, reset) == "gate"
    assert runtime.inference_snapshot(lease) is frame
    assert not list(tmp_path.rglob("*.npy"))
    assert len(list(tmp_path.rglob("initial-rgb.png"))) == 1
    with pytest.raises(RuntimeError, match="ACT_CAPTURE_ALREADY_EXISTS"):
        runtime._capture_inference_rgb(lease, 10.)


@pytest.mark.parametrize("changes, reason", [({"stamp": 9_000_000_000}, "reset simulation watermark"),
    ({"session": "other"}, "simulation session mismatch")])
def test_worker_preserves_reset_source_fences(tmp_path, changes, reason):
    runtime, lease, reset, _frame = runtime_case(tmp_path, **changes)
    with pytest.raises(RuntimeError, match=reason):
        runtime.point_initial_gate(lease, reset)


def test_stop_fences_memory_capture_readback(tmp_path):
    runtime, lease, reset, _frame = runtime_case(tmp_path)
    runtime.point_initial_gate(lease, reset)
    runtime.shutdown_control("stop", deadline_monotonic_s=99.)
    with pytest.raises(RuntimeError, match="STOP_REQUESTED"):
        runtime.inference_snapshot(lease)


def test_next_lease_reset_releases_previous_memory_frame(tmp_path):
    runtime, lease, reset, _frame = runtime_case(tmp_path)
    runtime.point_initial_gate(lease, reset)
    new = NS(**{**vars(lease), "attempt_id": "attempt-2"})
    runtime.reset_point(new)
    assert runtime._inference_receipts == {}
