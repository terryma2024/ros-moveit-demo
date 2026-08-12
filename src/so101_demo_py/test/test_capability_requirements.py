import pytest
from so101_demo.application.qualification import (
    InvalidRun,
    require_mujoco_qualification_capabilities,
)
from so101_demo.ports.capabilities import BackendCapabilities, CapabilityRequirements


def _capabilities(*, trace: bool) -> BackendCapabilities:
    return BackendCapabilities(
        atomic_snapshot=False,
        snapshot_with_receipt=True,
        reset_epoch=True,
        pause=False,
        viewer_camera=False,
        physical_contact_force=True,
        lossless_physics_step_trace=trace,
    )


def test_base_execute_accepts_missing_trace() -> None:
    assert CapabilityRequirements.base_execute().validate(_capabilities(trace=False)).accepted


def test_mujoco_qualification_requires_lossless_trace() -> None:
    result = CapabilityRequirements.mujoco_qualification().validate(
        _capabilities(trace=False)
    )
    assert not result.accepted
    assert result.error_code == "CAPABILITY_MISSING"
    assert result.missing == ("lossless_physics_step_trace",)
    with pytest.raises(InvalidRun, match="lossless_physics_step_trace"):
        require_mujoco_qualification_capabilities(_capabilities(trace=False))
