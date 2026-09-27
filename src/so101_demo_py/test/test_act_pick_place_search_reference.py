"""A physical SEARCH interval needs the same original controller publications."""

import copy
from types import SimpleNamespace

import mujoco
import pytest

from so101_demo.act.joints import ACT_JOINTS
from test_act_pick_place_search_history import _sources, _verify
from test_act_stationary_bridge_history import history
from test_act_stationary_reference_history import frames
from test_act_task8_search_boundary import _boundary, _request


def _case():
    model, observed, _, worlds, scenes, contacts = history()
    sources = _sources(model, observed, worlds, scenes, contacts)
    sources.readback.joints = tuple(
        int(model.jnt_qposadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)])
        for name in ACT_JOINTS
    )
    sources.readback.joint_tolerance = .01
    rows = frames()
    identity = (sources.session_id, sources.reset_epoch)
    sources.readback.broker.recent_controller_references = (
        lambda kind: (identity, rows[kind]))
    physical = _verify(sources, observed, model)
    return sources, observed, physical, rows


def _verify_references(sources, observed, physical):
    from so101_demo.adapters.act.pick_place_search_reference import (
        verify_search_stationary_references,
    )

    return verify_search_stationary_references(
        sources, observed, physical, stopped_wall_s=9.99,
    )


def test_selected_search_binds_three_controller_reference_windows():
    sources, observed, physical, _ = _case()
    proof = _verify_references(sources, observed, physical)
    assert proof["bridge_sim_time_ns"] == 1_100_000_000
    assert proof["selected_sim_time_ns"] == 1_200_000_000
    assert proof["sample_count_by_controller"] == {
        "arm": 51, "gripper": 51, "neck": 51}
    assert len(proof["reference_window_sha256"]) == 64
    assert proof["selected_source_sha256"] == physical["selected_source_sha256"]
    assert proof["owner_goal_interval_proof_required"] is True
    assert proof["command_authority"] is False


@pytest.mark.parametrize("change", [
    "missing_frame", "wrong_epoch", "pre_stop_receipt", "changed_arm_reference",
    "neck_drift", "changed_physical_proof",
])
def test_selected_search_refuses_unbound_controller_history(change):
    sources, observed, physical, rows = _case()
    if change == "missing_frame":
        rows["arm"] = rows["arm"][:25] + rows["arm"][26:]
    elif change == "wrong_epoch":
        sources.readback.broker.recent_controller_references = (
            lambda kind: ((sources.session_id, 99), rows[kind]))
    elif change == "pre_stop_receipt":
        arm = list(rows["arm"])
        arm[0] = {**arm[0], "received_monotonic_ns": 9_980_000_000}
        rows["arm"] = tuple(arm)
    elif change == "changed_arm_reference":
        arm = list(rows["arm"])
        arm[-1] = {**arm[-1], "positions": (.001, 0., 0., 0., 0.)}
        rows["arm"] = tuple(arm)
    elif change == "neck_drift":
        neck = list(rows["neck"])
        neck[-1] = {**neck[-1], "positions": (.1,)}
        rows["neck"] = tuple(neck)
    elif change == "changed_physical_proof":
        physical = copy.deepcopy(physical)
        physical["selected_physics_step"] += 1
    with pytest.raises(ValueError, match="SEARCH_REFERENCE_HISTORY_INVALID"):
        _verify_references(sources, observed, physical)


def test_production_search_boundary_supplies_real_reference_verifier():
    sources, observed, physical, _ = _case()
    boundary, _, reset, _, _, _ = _boundary()
    reset.sources = sources
    verified = []

    def segment_factory(_sources_arg, _adapter, _scene, _geometry, **kwargs):
        verified.append(kwargs["reference_verifier"](
            observed, physical, 9.99))
        return SimpleNamespace(run=lambda _request_arg, *, reset_epoch: observed)

    boundary.segment_factory = segment_factory
    request = dict(_request(), session_id=sources.session_id,
                   attempt_id=observed.search_result["attempt_id"])
    boundary.begin(request)
    assert boundary.search(request) is observed
    assert len(verified) == 1
    assert verified[0]["sample_count_by_controller"] == {
        "arm": 51, "gripper": 51, "neck": 51}
    assert verified[0]["command_authority"] is False
