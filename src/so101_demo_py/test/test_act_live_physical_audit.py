"""Controlled full native/ROS per-grid joins; no live acceptance."""

import copy

import pytest

from test_act_scene_association import association, frozen_scene


def provider(frozen_scene):
    from so101_demo.act.joints import ACT_JOINTS
    from so101_demo.act.live_physical_audit import LivePhysicalAuditProvider
    document, raw = association(frozen_scene)
    time_s = raw[0]["simulation_time_s"]
    values = {"physics": {"sample": copy.deepcopy(raw[0]), "chunk_sequence": 1,
                         "received_monotonic_ns": document["source"]["received_monotonic_ns"]},
        "planning": copy.deepcopy(document["query"]["record"]), "controller": {
            "positions": dict.fromkeys(ACT_JOINTS, 0.), "generation": 1,
            "source_stamp_ns": round(time_s * 1e9), "received_monotonic_s": 1.},
        "lifecycle": {"phase": "PREPARE", "release_epoch": 0, "release_time_s": None}}
    identity = {"session_id": "alignment-session", "attempt_id": "alignment-attempt", "reset_epoch": 1, "release_epoch": 0,
        "lease": {"batch_id": "batch", "coordinator_epoch": 1, "worker_id": "worker", "worker_generation": 1,
                  "point_id": "point", "attempt_id": "alignment-attempt", "lease_generation": 1,
                  "lease_issued_monotonic_s": 1., "lease_deadline_monotonic_s": 121.}}
    result = LivePhysicalAuditProvider(identity=identity, inputs=frozen_scene[1],
        scene_association_source=lambda at: {"association": copy.deepcopy(document), "raw_steps": copy.deepcopy(raw)},
        physics_source=lambda at: copy.deepcopy(values["physics"]),
        planning_source=lambda at: copy.deepcopy(values["planning"]),
        controller_source=lambda at: copy.deepcopy(values["controller"]),
        lifecycle_source=lambda at: copy.deepcopy(values["lifecycle"]))
    result.admit_scene_association({"association": document, "raw_steps": raw})
    return result, values, time_s


def test_complete_per_grid_join_owns_originals_and_defers_future_action(frozen_scene):
    from so101_demo.act.episode_assembly import PhysicalAuditAdapter
    source, values, at_s = provider(frozen_scene)
    original = copy.deepcopy(values)
    assert source.ready(at_s) is True and source.ready(at_s) is True
    row = source(at_s)
    assert set(row) == set(PhysicalAuditAdapter.KEYS)
    assert row["mujoco_truth"]["sample"] == original["physics"]["sample"]
    assert row["planning_scene"]["record"] == original["planning"]
    assert row["controller_state"] == original["controller"]
    assert row["reference_positions"] is None and row["reference_source"] is None
    row["mujoco_truth"]["sample"]["model_qpos"][0] += 1.
    assert values == original
    with pytest.raises(ValueError, match="LIVE_PHYSICAL_GRID_REUSED"):
        source(at_s)


def test_capture_readiness_does_not_authenticate_frozen_assets_under_ingress_lock(frozen_scene, monkeypatch):
    from so101_demo.act import scene_association
    source, values, at_s = provider(frozen_scene)
    calls = []
    actual = scene_association.verify_scene_association
    def observe(*args, **kwargs):
        calls.append("authentication under capture readiness")
        return actual(*args, **kwargs)
    monkeypatch.setattr(scene_association, "verify_scene_association", observe)
    assert source.ready(at_s) is True
    assert calls == [], "capture readiness performed frozen I/O/model compilation"


def test_unadmitted_or_altered_association_cannot_make_capture_ready(frozen_scene):
    source, values, at_s = provider(frozen_scene)
    original = source.scene_association_source(at_s)
    unadmitted = copy.deepcopy(original)
    unadmitted["association"]["association_id"] += "-unadmitted"
    source.scene_association_source = lambda at: copy.deepcopy(unadmitted)
    assert source.ready(at_s) is False
    unadmitted["association"]["expected"]["geometry"]["objects"][0]["pose"]["values"][0] += .01
    with pytest.raises(ValueError, match="SOURCE_ALIGNMENT_INVALID"):
        source.admit_scene_association(unadmitted)
    assert source.ready(at_s) is False
    source.scene_association_source = lambda at: copy.deepcopy(original)
    assert source.ready(at_s) is True


def test_provider_identity_is_an_owned_full_original_lease(frozen_scene):
    source, values, at_s = provider(frozen_scene)
    original = source.identity
    exposed = source.identity
    exposed["lease"]["worker_generation"] += 1
    assert source.identity == original


def test_admitting_next_scene_preserves_preceding_grid_original_association(frozen_scene):
    source, values, at_s = provider(frozen_scene)
    original = source.scene_association_source(at_s)
    following, raw = association(frozen_scene)
    source.admit_scene_association({"association": following, "raw_steps": raw})
    assert source.ready(at_s) is True
    assert source(at_s)["planning_scene"]["association_id"] == original["association"]["association_id"]


@pytest.mark.parametrize("change", ["missing", "future_physics", "future_scene", "future_controller", "stale",
                                   "scope", "mask", "malformed_scene", "boolean_measurement"])
def test_per_grid_join_refuses_missing_future_foreign_or_malformed_source(frozen_scene, change):
    source, values, at_s = provider(frozen_scene)
    if change == "missing":
        values["physics"] = None
    elif change == "future_physics":
        values["physics"]["sample"]["simulation_time_s"] += .1
    elif change == "future_scene":
        for key in ("request_ros_clock", "response_ros_clock"):
            values["planning"][key]["sim_time_ns"] += 100000000
    elif change == "future_controller":
        values["controller"]["source_stamp_ns"] += 100000000
    elif change == "stale":
        at_s += .100000001
    elif change == "scope":
        values["physics"]["sample"]["reset_epoch"] += 1
    elif change == "mask":
        values["planning"]["request"]["components"]["components"] = 0
    elif change == "malformed_scene":
        values["planning"]["response"]["scene"]["invented_revision"] = 99
    else:
        values["controller"]["positions"]["1"] = True
    if change in ("missing", "future_physics", "future_scene", "future_controller", "stale"):
        assert source.ready(at_s) is False
        with pytest.raises(ValueError, match="LIVE_PHYSICAL_SOURCE_UNAVAILABLE"):
            source(at_s)
    else:
        with pytest.raises((ValueError, AssertionError, TypeError)):
            source.ready(at_s)


@pytest.mark.parametrize("change", ["empty", "dimensions", "colors", "membership"])
def test_full_scene_geometry_is_required_at_per_grid_admission(frozen_scene, change):
    source, values, at_s = provider(frozen_scene)
    scene = values["planning"]["response"]["scene"]
    if change == "empty":
        scene["world"]["collision_objects"] = []
    elif change == "dimensions":
        scene["world"]["collision_objects"][0]["primitives"][0]["dimensions"][0] += .01
    elif change == "colors":
        scene["object_colors"][0]["color"]["r"] += .1
    else:
        scene["world"]["collision_objects"][0]["id"] = "foreign"
    with pytest.raises(ValueError, match="LIVE_PHYSICAL_SCENE_GEOMETRY_INVALID"):
        source.ready(at_s)


def test_committed_release_time_cannot_drift_within_one_epoch(frozen_scene):
    source, values, at_s = provider(frozen_scene)
    source(at_s)
    values["physics"]["sample"]["simulation_time_s"] = at_s + .002
    values["controller"]["source_stamp_ns"] = round((at_s + .002) * 1e9)
    for key in ("request_ros_clock", "response_ros_clock"):
        values["planning"][key]["sim_time_ns"] = round((at_s + .002) * 1e9)
    values["planning"]["call_id"] = "release-query"
    values["lifecycle"] = {"phase": "OPEN_GRIPPER", "release_epoch": 1, "release_time_s": at_s + .001}
    assert source(at_s + .002)["release_event"] is True
    values["lifecycle"]["release_time_s"] = at_s + .0005
    with pytest.raises(ValueError, match="LIVE_PHYSICAL_RELEASE_INVALID"):
        source.ready(at_s + .004)
