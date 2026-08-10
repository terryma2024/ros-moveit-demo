import os

import pytest


@pytest.mark.skipif(
    os.environ.get("SO101_PY_RUN_LIVE_ATTACHMENT") != "1",
    reason="set SO101_PY_RUN_LIVE_ATTACHMENT=1 inside the isolated Task 8 stack",
)
def test_live_attachment_evidence_contract() -> None:
    from so101_gazebo_demo.test_support.live_attachment import run_live_gate

    evidence = run_live_gate()
    assert evidence.bilateral_contact_before_attach
    assert evidence.attached
    assert evidence.micro_lift_world_z >= 0.002
    assert evidence.max_object_tcp_drift_m <= 0.001
    assert evidence.solver_stable
    assert evidence.detached
    assert evidence.object_settled_independently
    assert not evidence.original_collision_plugin_loaded
