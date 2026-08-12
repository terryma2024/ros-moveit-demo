from __future__ import annotations

import json
from pathlib import Path

import pytest

from so101_mujoco_demo_py.frozen_behavior import (
    FrozenBehaviorViolation,
    verify_frozen_behavior,
    verify_transport_semantics,
)

REPO_ROOT = Path(__file__).parents[3]
MANIFEST_PATH = (
    REPO_ROOT / "docs/experiments/so101-mujoco-phase-aware-frozen-behavior-manifest.json"
)
TRANSPORT_PATH = (
    REPO_ROOT / "src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases/transport.py"
)


def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_current_transport_preserves_manifest_bound_motion_semantics() -> None:
    report = verify_transport_semantics(TRANSPORT_PATH.read_text(encoding="utf-8"), manifest())

    assert report["targets"] == "MATCH"
    assert report["planner_request"] == "MATCH"
    assert report["phase_force_modes"] == "MATCH"


def test_transport_verifier_rejects_planner_scaling_mutation() -> None:
    source = TRANSPORT_PATH.read_text(encoding="utf-8").replace(
        "velocity_scaling=0.05", "velocity_scaling=0.06", 1
    )

    with pytest.raises(FrozenBehaviorViolation, match="velocity_scaling"):
        verify_transport_semantics(source, manifest())


def test_repository_frozen_behavior_and_backend_integration_contract_match() -> None:
    report = verify_frozen_behavior(REPO_ROOT, MANIFEST_PATH)

    assert report["manifest_sha256"] == (
        "0db33d29e866d7e9986269e201baa52eb264308dc45de11ad7dce6f8f1efbeb3"
    )
    assert report["backend_integration_contract"] == "ACTIVE_GAZEBO_NOT_FROZEN"
    assert report["instrumentation_diff_gate"] == "MATCH"
