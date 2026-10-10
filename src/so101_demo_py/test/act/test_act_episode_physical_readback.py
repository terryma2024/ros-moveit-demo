"""Pure disk-row semantics with controlled native/ROS values and a real frozen MuJoCo model."""

import copy
import math
import time

import pytest

from so101_demo.act import episode_qc
from test_act_scene_association import association, frozen_scene


def materials(frozen_scene):
    import mujoco
    from sensor_msgs.msg import JointState
    from rosidl_runtime_py.convert import message_to_ordereddict
    from so101_demo.act.joints import ACT_JOINTS
    document, raw = association(frozen_scene)
    root, inputs, model = frozen_scene
    sample = raw[0]
    t = sample["simulation_time_s"]
    positions = {name: sample["model_qpos"][model.jnt_qposadr[mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, name)]] for name in ACT_JOINTS}
    original = JointState(name=list(positions), position=list(positions.values()),
                          velocity=[0.] * len(positions))
    original.header.stamp.sec, original.header.stamp.nanosec = divmod(round(t * 1e9), 1000000000)
    # Deterministic receipt: derived from the newest sample's source clock, never a second real read
    # that a loaded gate worker could delay beyond the raw-chunk max_age.
    receipt = raw[-1]["clock_interval_begin_monotonic_ns"] + 1_000_000
    chunk = {"schema_version": 1, "received_monotonic_ns": receipt,
        "chunk": {"chunk_sequence": 1, "simulation_session_id": "alignment-session", "reset_epoch": 1,
            "first_physics_step": 1, "last_physics_step": 1, "first_simulation_time_s": t,
            "last_simulation_time_s": t, "failed_publish_attempts": 0, "handoff_monotonic_ns": 0, "publish_monotonic_ns": 0,
                "publish_deferrals_total": 0, "evidence_loss": False,
            "samples": raw}}
    query = document["query"]["record"]
    audit = {"reset_epoch": 1, "release_epoch": 0, "release_event": False, "release_time_s": None,
        "phase": "PREPARE", "source_stamps": {name: t for name in ("head", "wrist", "arm", "neck")},
        "physical_stamps": {"cup": t, "contacts": t,
            "planning_scene": query["response_ros_clock"]["sim_time_ns"] / 1e9},
        "mujoco_truth": {"source_kind": "native_physics_step", "sample": copy.deepcopy(sample),
            "chunk_sequence": 1, "received_monotonic_ns": receipt},
        "contacts": [], "planning_scene": {"query_id": query["call_id"], "record": copy.deepcopy(query),
            "association_id": document["association_id"]},
        "controller_state": {"source_stamp_ns": round(t * 1e9), "generation": 1,
            "positions": positions, "received_monotonic_s": receipt / 1e9,
            "original_message": dict(message_to_ordereddict(original))}}
    row = {"observation": {"sim_time_s": t, "state": [positions[str(i)] for i in range(1, 7)]
        + [math.sin(positions["neck_yaw_joint"]), math.cos(positions["neck_yaw_joint"])]},
        "audit": audit}
    return [row], [chunk], [document], inputs, {"session_id": "alignment-session", "reset_epoch": 1}


def verify(*args, **kwargs):
    method = getattr(episode_qc, "verify_episode_physical_rows", None)
    assert callable(method), "Independent per-row native/source-alignment/state reader is absent"
    return method(*args, **kwargs)


def test_original_physical_rows_recompute_against_raw_chunks_and_exact_scene_records(frozen_scene):
    rows, chunks, associations, inputs, identity = materials(frozen_scene)
    original = copy.deepcopy((rows, chunks, associations))
    assert verify(rows, raw_chunks=chunks, associations=associations,
                  inputs=inputs, identity=identity) == {"rows": 1, "native_steps": 1, "scene_associations": 1}
    assert (rows, chunks, associations) == original


@pytest.mark.parametrize("change", ["truth_position", "truth_receipt", "chunk_id", "invented_contact",
    "physical_stamp", "query_id", "association_id", "query_geometry", "query_before_apply",
    "controller_copy", "controller_original", "controller_stamp", "controller_unknown",
    "state_arm", "state_neck", "state_stamp", "missing_native", "missing_scene", "foreign_epoch"])
def test_rehashed_row_claim_cannot_displace_original_native_or_scene_or_measured_state(frozen_scene, change):
    rows, chunks, associations, inputs, identity = materials(frozen_scene)
    assert verify(rows, raw_chunks=chunks, associations=associations, inputs=inputs, identity=identity)["rows"] == 1
    audit = rows[0]["audit"]
    if change == "truth_position":
        audit["mujoco_truth"]["sample"]["model_qpos"][0] += .01
    elif change == "truth_receipt":
        audit["mujoco_truth"]["received_monotonic_ns"] += 1
    elif change == "chunk_id":
        audit["mujoco_truth"]["chunk_sequence"] += 1
    elif change == "invented_contact":
        audit["contacts"] = [{"supported": True}]
    elif change == "physical_stamp":
        audit["physical_stamps"]["cup"] += .001
    elif change in ("query_id", "association_id"):
        audit["planning_scene"][change] += "-foreign"
    elif change == "query_geometry":
        audit["planning_scene"]["record"]["response"]["scene"]["world"]["collision_objects"][0]["id"] = "foreign"
    elif change == "query_before_apply":
        audit["planning_scene"]["record"]["request_ros_clock"]["begin_monotonic_ns"] = 1
    elif change == "controller_copy":
        audit["controller_state"]["positions"]["1"] += .01
    elif change == "controller_original":
        audit["controller_state"]["original_message"]["position"][0] += .01
        audit["controller_state"]["positions"]["1"] += .01
    elif change == "controller_stamp":
        audit["controller_state"]["source_stamp_ns"] += 1
    elif change == "controller_unknown":
        audit["controller_state"]["original_message"]["reset_confirmed"] = True
    elif change == "state_arm":
        rows[0]["observation"]["state"][0] += .01
    elif change == "state_neck":
        rows[0]["observation"]["state"][-2:] = [1., 0.]
    elif change == "state_stamp":
        audit["source_stamps"]["arm"] += .001
    elif change == "missing_native":
        chunks = []
    elif change == "missing_scene":
        associations = []
    else:
        identity["reset_epoch"] += 1
    with pytest.raises(ValueError, match="EPISODE_PHYSICAL_"):
        verify(rows, raw_chunks=chunks, associations=associations, inputs=inputs, identity=identity)
