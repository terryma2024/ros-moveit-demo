from __future__ import annotations

import os
import time

import pytest
import rclpy

from so101_mujoco_demo_py.mujoco.observer import EvidenceStale, MujocoWorldObserver


@pytest.mark.skipif(
    os.environ.get("SO101_MUJOCO_LIVE_TEST") != "1",
    reason="requires the task-owned isolated MuJoCo launch",
)
def test_observer_consumes_two_real_atomic_plugin_messages() -> None:
    session_id = os.environ["SO101_MUJOCO_SESSION_ID"]
    rclpy.init()
    node = rclpy.create_node("so101_mujoco_observer_live_contract")
    observer = MujocoWorldObserver(node, session_id, max_age_s=0.5)
    deadline = time.monotonic() + 10.0
    first = None
    second = None
    try:
        while time.monotonic() < deadline and second is None:
            rclpy.spin_once(node, timeout_sec=0.1)
            try:
                current = observer.snapshot()
            except EvidenceStale:
                continue
            if first is None:
                first = current
            elif current.publisher_sequence > first.publisher_sequence:
                second = current
        assert first is not None and second is not None, (
            f"accepted first={first is not None} second={second is not None} "
            f"rejected_count={observer.rejected_count} "
            f"last_rejection={observer.last_rejection!r}"
        )
        assert first.simulation_session_id == session_id
        assert second.simulation_session_id == session_id
        assert second.publisher_sequence > first.publisher_sequence
        assert second.simulation_step >= first.simulation_step
        assert second.object_state.body == "cup"
        assert second.truncated is False
        assert isinstance(second.left_fingertip_contacts, tuple)
        assert isinstance(second.right_fingertip_contacts, tuple)
        assert isinstance(second.other_object_contacts, tuple)
    finally:
        node.destroy_node()
        rclpy.shutdown()
