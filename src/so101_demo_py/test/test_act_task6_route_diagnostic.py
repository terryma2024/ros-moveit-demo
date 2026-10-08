"""Source-bound, no-contact Task 6 route authority stays outside collection."""

from act_identity import ACT_MODEL_SHA256
import hashlib
import json
import os
import threading
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
import mujoco

from so101_demo.act.visible_approach_diagnostic import (
    build_route_manifest, require_route_manifest, require_route_sources,
    route_prefix_matches,
)
from so101_demo.adapters.act.physics import MujocoPathChecker
from so101_demo.adapters.act.phase_contact_allowlist import stationary_cup_support_pairs
from so101_demo.act.ownership import Ownership


PACKAGE = Path(__file__).resolve().parents[1]
SCENE = PACKAGE / "assets/mujoco/act/scene.xml"
PLUGIN = PACKAGE / "config/mujoco/act/task6_route_plugins.yaml"
PROFILE = PACKAGE / "config/mujoco/act/task6_visible_approach_v1.json"


def manifest():
    return build_route_manifest(
        scene_path=SCENE, plugin_path=PLUGIN, profile_path=PROFILE,
        session_id="route-diagnostic-one", attempt_id="route-attempt-one",
    )


def test_route_is_exact_pinned_no_contact_microsegments():
    route = manifest()
    require_route_sources(route)
    assert route["eligible_for_collection"] is False
    assert route["kind"] == "ACT_TASK6_ROUTE_DIAGNOSTIC"
    assert route["model_sha256"] == ACT_MODEL_SHA256
    assert route["allowed_contact_pairs"] == []
    assert route["segment_rows"] == 9
    assert route["path_clearance_m"] == .002
    assert route["max_age_s"] == .2
    assert route["stop_max_age_s"] == 1.5
    assert route["velocity_limit_rad_s"] == [.25] * 6
    assert route["acceleration_limit_rad_s2"] == [1.2] * 6
    rows = route["target_positions"]
    assert len(rows) % 9 == 0
    assert len(rows) > 900
    assert rows[-1] == route["handoff_positions"]
    previous = route["joint_start_rad"]
    for index in range(0, len(rows), 9):
        segment = rows[index:index + 9]
        assert segment[0] == previous
        assert segment[-1] == segment[-2]
        assert max(abs(a - b) for a, b in zip(previous, segment[-1])) <= .02 + 1e-12
        previous = segment[-1]


def test_visual_detour_matches_independently_checked_target_rows():
    route = manifest()
    profile = json.loads(PROFILE.read_text())
    assert profile["visual_detour"] == {
        "joint_index": 3, "begin_segment": 181, "full_segment": 191,
        "last_full_segment": 201, "end_segment": 211,
        "peak_offset_rad": .1,
    }
    rows = json.dumps(route["target_positions"], separators=(",", ":"),
                      allow_nan=False).encode() + b"\n"
    assert hashlib.sha256(rows).hexdigest() == (
        "6cdb83d3b90afba46c9d57101c27a71264310baf33b9a50cde717852db885a11")


def test_route_prefix_is_sequence_and_byte_content_bound():
    route = manifest()
    for sequence in (0, 1, len(route["target_positions"]) // 9 - 1):
        start = sequence * 9
        prior = route["joint_start_rad"] if sequence == 0 else route["target_positions"][start - 1]
        positions = [prior] + route["target_positions"][start:start + 9]
        prefix = dict(session_id=route["session_id"], attempt_id=route["attempt_id"],
                      sequence=sequence, observation_time_s=10.,
                      target_times_s=[10. + .1 * (index + 1) for index in range(10)],
                      positions=positions)
        assert route_prefix_matches(prefix, route)
        altered = {**prefix, "positions": [list(row) for row in positions]}
        altered["positions"][-1][0] += .001
        assert not route_prefix_matches(altered, route)
        assert not route_prefix_matches({**prefix, "sequence": sequence + 1}, route)
        assert not route_prefix_matches({**prefix, "attempt_id": "other-attempt"}, route)


def test_route_rejects_collecting_and_self_consistent_target_tamper():
    route = manifest()
    with pytest.raises(ValueError):
        require_route_manifest({**route, "eligible_for_collection": True})
    altered = {**route, "target_positions": [row[:] for row in route["target_positions"]]}
    altered["target_positions"][10][0] += .001
    altered["manifest_sha256"] = hashlib.sha256(json.dumps(
        {key: value for key, value in altered.items() if key != "manifest_sha256"},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()
    require_route_manifest(altered)
    with pytest.raises(ValueError, match="source replay"):
        require_route_sources(altered)


@pytest.mark.parametrize("origin", [1., 98.875999999])
def test_every_stopped_microsegment_passes_current_model_path_checker(origin):
    route = manifest()
    checker = MujocoPathChecker(
        SCENE, protected_roots=("base",), cup_joint="cup_free_joint",
        gripper_body="gripper", path_step_s=route["path_step_s"],
        path_clearance_m=route["path_clearance_m"],
        velocity_limit_rad_s=route["velocity_limit_rad_s"],
        acceleration_limit_rad_s2=route["acceleration_limit_rad_s2"],
        allowed_pairs_by_phase={"APPROACH": stationary_cup_support_pairs(
            mujoco.MjModel.from_xml_path(str(SCENE)))},
    )
    model, data = checker.model, checker._data
    for sequence in range(len(route["target_positions"]) // 9):
        start = sequence * 9
        prior = route["joint_start_rad"] if sequence == 0 else route["target_positions"][start - 1]
        rows = route["target_positions"][start:start + 9]
        mujoco.mj_resetDataKeyframe(model, data, 0)
        data.qpos[checker.joints] = prior
        data.qpos[checker.cup_address:checker.cup_address + 3] = route["cup_start_m"]
        data.qpos[checker.cup_address + 3:checker.cup_address + 7] = (1., 0., 0., 0.)
        prefix = dict(session_id=route["session_id"], attempt_id=route["attempt_id"],
                      sequence=sequence, observation_time_s=origin,
                      target_times_s=[origin + .1 * (index + 1) for index in range(10)],
                      positions=[prior] + rows)
        snapshot = dict(model_qpos=data.qpos.tolist(),
                        model_sha256=checker.model_sha256, phase="APPROACH",
                        holding_state="EMPTY", sim_time_s=origin,
                        controller_bridge=dict(time_s=origin, point=dict(
                            positions=prior, velocities=[0.] * 6, accelerations=[])),
                        controller_start_time_s=origin + .05,
                        controller_start_positions=prior,
                        controller_start_velocities=[0.] * 6,
                        cup_in_gripper_transform=None)
        assert checker.check_path(prefix, snapshot), (sequence, checker.last_check)
        assert checker.last_check["samples"] == 52


def test_first_route_segment_checks_measured_settled_start_and_rejects_larger_error():
    route = manifest()
    checker = MujocoPathChecker(
        SCENE, protected_roots=("base",), cup_joint="cup_free_joint",
        gripper_body="gripper", path_step_s=route["path_step_s"],
        path_clearance_m=route["path_clearance_m"],
        velocity_limit_rad_s=route["velocity_limit_rad_s"],
        acceleration_limit_rad_s2=route["acceleration_limit_rad_s2"],
        allowed_pairs_by_phase={"APPROACH": stationary_cup_support_pairs(
            mujoco.MjModel.from_xml_path(str(SCENE)))},
    )
    # EXP-318's actual settled joint/scene readback, before the rejected permit.
    settled = [-.2500333208650234, -.4998717311944051,
               1.5003345807748143, .00008381385810142793,
               .000002264418481035381, -.0000001678964049377884]
    velocity = [6.522744502198619e-9, -1.547625707537602e-7,
                -2.1595300494385906e-8, -1.4966414120858625e-11,
                2.8778131429358235e-14, -4.137176767700265e-16]
    data = checker._data
    mujoco.mj_resetDataKeyframe(checker.model, data, 0)
    data.qpos[checker.joints] = settled
    data.qpos[checker.cup_address:checker.cup_address + 3] = route["cup_start_m"]
    data.qpos[checker.cup_address + 3:checker.cup_address + 7] = (1., 0., 0., 0.)
    origin = 98.875999999
    prefix = dict(session_id=route["session_id"], attempt_id=route["attempt_id"],
                  sequence=0, observation_time_s=origin,
                  target_times_s=[origin + .1 * (index + 1) for index in range(10)],
                  positions=[route["joint_start_rad"]] + route["target_positions"][:9])
    snapshot = dict(model_qpos=data.qpos.tolist(), model_sha256=checker.model_sha256,
                    phase="APPROACH", holding_state="EMPTY", sim_time_s=98.899999999,
                    controller_bridge=dict(time_s=98.898, point=dict(
                        positions=settled, velocities=velocity, accelerations=[])),
                    controller_start_time_s=98.949999999,
                    controller_start_positions=settled,
                    controller_start_velocities=velocity,
                    cup_in_gripper_transform=None)
    assert checker.check_path(prefix, snapshot), checker.last_check
    farther = settled.copy()
    farther[2] += .002
    snapshot["controller_start_positions"] = farther
    assert not checker.check_path(prefix, snapshot)
    assert checker.last_check["reason"] == "PATH_ACCELERATION_LIMIT"


def test_route_plugin_chunk_cadence_fits_the_hard_receipt_deadline():
    import yaml
    route=yaml.safe_load(PLUGIN.read_bytes())["/**"]["ros__parameters"]
    ordinary=yaml.safe_load((PLUGIN.parent/"mujoco_plugins.yaml").read_bytes())[
        "/**"]["ros__parameters"]
    assert route["physics_step_chunk_size"]==10
    assert ordinary["physics_step_chunk_size"]==50
    assert .002*route["physics_step_chunk_size"]/.25<=.08
    assert .002*route["physics_step_chunk_size"]/.25<.2
