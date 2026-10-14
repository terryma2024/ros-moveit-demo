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


# ---- a read concurrent with an apply may show the scene before or after it ----------------------------------------------

def _concurrent_next(values, geometry, *, begin_offset_ns=-8_000_000, end_offset_ns=12_000_000):
    """A synthetic admitted association whose apply overlaps the row's planning read (only the fields the rule reads)."""
    read = values["planning"]
    begin, end = read["request_ros_clock"]["begin_monotonic_ns"], read["response_ros_clock"]["end_monotonic_ns"]
    record = {"request_ros_clock": {"begin_monotonic_ns": begin + begin_offset_ns},
              "response_ros_clock": {"end_monotonic_ns": end + end_offset_ns}}
    return {"association_id": "next-association", "apply": {"record": record}, "receipt": {"geometry": geometry}}


def _changed_read_geometry(values):
    from moveit_msgs.srv import GetPlanningScene
    from so101_demo.act.scene_association import canonical, decode_ros
    from so101_demo.control.planning_scene.task_scene import normalized_scene_geometry

    values["planning"]["response"]["scene"]["world"]["collision_objects"][0]["primitives"][0]["dimensions"][0] += .01
    response = decode_ros(GetPlanningScene.Response, values["planning"]["response"])
    return normalized_scene_geometry(response.scene), canonical(normalized_scene_geometry(response.scene))


def test_a_read_concurrent_with_the_next_apply_may_show_exactly_the_next_scene(frozen_scene):
    source, values, at_s = provider(frozen_scene)
    geometry, _ = _changed_read_geometry(values)
    governing = source.scene_association_source(at_s)["association"]["association_id"]
    source.concurrent_apply_source = lambda read: ([_concurrent_next(values, geometry)], False)
    assert source.ready(at_s) is True
    assert source(at_s)["planning_scene"]["association_id"] == governing, "the row stays bound to the governing association"


def test_a_concurrent_read_with_any_other_geometry_still_fails(frozen_scene):
    source, values, at_s = provider(frozen_scene)
    _changed_read_geometry(values)
    wrong = _concurrent_next(values, {"not": "the read's scene"})
    source.concurrent_apply_source = lambda read: ([wrong], False)
    with pytest.raises(ValueError, match="LIVE_PHYSICAL_SCENE_GEOMETRY_INVALID"):
        source.ready(at_s)


def test_a_read_that_did_not_overlap_the_apply_still_fails_even_with_the_matching_geometry(frozen_scene):
    source, values, at_s = provider(frozen_scene)
    geometry, _ = _changed_read_geometry(values)
    # the apply finished 1 ms before the read began, so the read must already show it as the governing scene: it is no race
    before = _concurrent_next(values, geometry, begin_offset_ns=-30_000_000, end_offset_ns=-(
        values["planning"]["response_ros_clock"]["end_monotonic_ns"] - values["planning"]["request_ros_clock"]["begin_monotonic_ns"]) - 1_000_000)
    source.concurrent_apply_source = lambda read: ([before], False)
    with pytest.raises(ValueError, match="LIVE_PHYSICAL_SCENE_GEOMETRY_INVALID"):
        source.ready(at_s)


def _applied_before_read(values, geometry, *, apply_end_before_read_ns=11_000_000, readback_after_read_begin_ns=43_000_000):
    """A synthetic admitted association whose apply FINISHED before the row's planning read began and whose own read-back (the
    association's query) began only after it: the association is not governing yet, but the scene already shows the apply."""
    read = values["planning"]
    begin = read["request_ros_clock"]["begin_monotonic_ns"]
    record = {"request_ros_clock": {"begin_monotonic_ns": begin - apply_end_before_read_ns - 20_000_000},
              "response_ros_clock": {"end_monotonic_ns": begin - apply_end_before_read_ns}}
    query = {"record": {"request_ros_clock": {"begin_monotonic_ns": begin + readback_after_read_begin_ns}}}
    return {"association_id": "next-association", "apply": {"record": record}, "query": query,
            "receipt": {"geometry": geometry}}


def test_a_read_after_the_apply_but_before_its_readback_may_show_exactly_that_scene(frozen_scene):
    """EXP-593: the read began 11 ms after the detach apply finished and 43 ms before the Teacher's own read-back of it."""
    source, values, at_s = provider(frozen_scene)
    geometry, _ = _changed_read_geometry(values)
    governing = source.scene_association_source(at_s)["association"]["association_id"]
    source.concurrent_apply_source = lambda read: ([_applied_before_read(values, geometry)], False)
    assert source.ready(at_s) is True
    assert source(at_s)["planning_scene"]["association_id"] == governing


def test_a_read_after_the_apply_before_its_readback_with_any_other_geometry_still_fails(frozen_scene):
    source, values, at_s = provider(frozen_scene)
    _changed_read_geometry(values)
    wrong = _applied_before_read(values, {"not": "the read's scene"})
    source.concurrent_apply_source = lambda read: ([wrong], False)
    with pytest.raises(ValueError, match="LIVE_PHYSICAL_SCENE_GEOMETRY_INVALID"):
        source.ready(at_s)


def test_a_read_that_began_after_the_readback_of_the_apply_still_fails_with_the_matching_geometry(frozen_scene):
    source, values, at_s = provider(frozen_scene)
    geometry, _ = _changed_read_geometry(values)
    late = _applied_before_read(values, geometry, readback_after_read_begin_ns=-1_000_000)
    source.concurrent_apply_source = lambda read: ([late], False)
    with pytest.raises(ValueError, match="LIVE_PHYSICAL_SCENE_GEOMETRY_INVALID"):
        source.ready(at_s)


def test_a_concurrent_apply_whose_association_is_not_built_yet_makes_the_row_wait(frozen_scene):
    source, values, at_s = provider(frozen_scene)
    _changed_read_geometry(values)
    source.concurrent_apply_source = lambda read: ([], True)
    assert source.ready(at_s) is False
    source.concurrent_apply_source = lambda read: ([], False)
    with pytest.raises(ValueError, match="LIVE_PHYSICAL_SCENE_GEOMETRY_INVALID"):
        source.ready(at_s)


def test_the_concurrency_rule_itself():
    from so101_demo.act.scene_association import canonical, concurrent_apply_geometry_matches, read_overlaps_apply

    def call(begin, end):
        return {"request_ros_clock": {"begin_monotonic_ns": begin}, "response_ros_clock": {"end_monotonic_ns": end}}

    apply = call(1000, 2000)
    assert read_overlaps_apply(call(1500, 1600), apply) and read_overlaps_apply(call(1900, 2500), apply)
    assert read_overlaps_apply(call(500, 1000), apply) and read_overlaps_apply(call(2000, 2100), apply)   # touching counts
    assert not read_overlaps_apply(call(2001, 2100), apply) and not read_overlaps_apply(call(500, 999), apply)
    next_association = {"association_id": "b", "apply": {"record": apply}, "receipt": {"geometry": {"x": 1}}}
    initial = {"association_id": "a", "apply": None, "receipt": {"geometry": {"x": 0}}}
    read = call(1500, 1600)
    assert concurrent_apply_geometry_matches(read, canonical({"x": 1}), "a", [initial, next_association])
    assert not concurrent_apply_geometry_matches(read, canonical({"x": 2}), "a", [initial, next_association])
    assert not concurrent_apply_geometry_matches(read, canonical({"x": 1}), "b", [initial, next_association]), "not itself"
    assert not concurrent_apply_geometry_matches(call(3000, 3100), canonical({"x": 1}), "a", [initial, next_association])


def test_the_rule_for_a_read_between_an_apply_and_its_readback():
    from so101_demo.act.scene_association import canonical, concurrent_apply_geometry_matches, read_follows_apply_before_readback

    def read_at(begin):
        return {"request_ros_clock": {"begin_monotonic_ns": begin}, "response_ros_clock": {"end_monotonic_ns": begin + 5}}

    def association(identifier, apply_end, readback_begin, geometry):
        return {"association_id": identifier, "receipt": {"geometry": geometry},
                "apply": {"record": {"request_ros_clock": {"begin_monotonic_ns": apply_end - 20},
                                     "response_ros_clock": {"end_monotonic_ns": apply_end}}},
                "query": {"record": {"request_ros_clock": {"begin_monotonic_ns": readback_begin}}}}

    initial = {"association_id": "a", "apply": None, "receipt": {"geometry": {"x": 0}}}
    detach = association("b", 1000, 1100, {"x": 1})
    assert read_follows_apply_before_readback(read_at(1011), detach)
    assert read_follows_apply_before_readback(read_at(1000), detach), "touching the end of the apply counts"
    assert not read_follows_apply_before_readback(read_at(999), detach), "that read overlaps the apply instead"
    assert not read_follows_apply_before_readback(read_at(1100), detach), "the read-back began: the association governs"
    assert not read_follows_apply_before_readback(read_at(1500), detach)
    assert not read_follows_apply_before_readback(read_at(1011), initial)
    assert concurrent_apply_geometry_matches(read_at(1011), canonical({"x": 1}), "a", [initial, detach])
    assert not concurrent_apply_geometry_matches(read_at(1011), canonical({"x": 2}), "a", [initial, detach])
    assert not concurrent_apply_geometry_matches(read_at(1011), canonical({"x": 1}), "b", [initial, detach]), "not itself"
    assert not concurrent_apply_geometry_matches(read_at(1100), canonical({"x": 1}), "a", [initial, detach])


def test_the_offline_hook_offers_the_association_of_an_apply_that_finished_before_the_read_and_is_not_read_back_yet():
    from types import SimpleNamespace

    from so101_demo.act.offline import sources

    cls = next(value for value in vars(sources).values() if isinstance(value, type) and hasattr(value, "_concurrent_apply_for"))
    host = object.__new__(cls)
    applied = {"call_id": "apply-a", "service": "/apply_planning_scene", "request_ros_clock": {"begin_monotonic_ns": 980},
               "response_ros_clock": {"end_monotonic_ns": 1000}, "response": {"success": True}}
    document = {"association_id": "A", "apply": {"record": applied},
                "query": {"record": {"request_ros_clock": {"begin_monotonic_ns": 1100}}}}
    host.tracker = SimpleNamespace(records=[applied])
    host.associations = SimpleNamespace(history=[{"association": document}])

    def read_at(begin):
        return {"request_ros_clock": {"begin_monotonic_ns": begin}, "response_ros_clock": {"end_monotonic_ns": begin + 5}}

    documents, _pending = host._concurrent_apply_for(read_at(1011))
    assert [item["association_id"] for item in documents] == ["A"]
    documents, _pending = host._concurrent_apply_for(read_at(1100))
    assert documents == []


def test_the_offline_hook_finds_the_teachers_overlapping_applies_in_the_tracker():
    """The Teacher's applies are in the scene-operation tracker, not among the Recorder's own reads; an overlapping apply with
    an admitted association is offered, one without is `pending`, a failed or disjoint one is ignored."""
    from types import SimpleNamespace

    from so101_demo.act.offline import sources

    cls = next(value for value in vars(sources).values() if isinstance(value, type) and hasattr(value, "_concurrent_apply_for"))
    host = object.__new__(cls)

    def call(identifier, begin, end, *, success=True, service="/apply_planning_scene"):
        return {"call_id": identifier, "service": service, "request_ros_clock": {"begin_monotonic_ns": begin},
                "response_ros_clock": {"end_monotonic_ns": end}, "response": {"success": success}}

    admitted = call("apply-a", 1000, 2000)
    host.tracker = SimpleNamespace(records=[admitted, call("apply-b", 1500, 2500), call("failed", 1000, 2000, success=False),
                                            call("later", 9000, 9500), call("read", 1000, 2000, service="/get_planning_scene")])
    host.associations = SimpleNamespace(history=[{"association": {"association_id": "A", "apply": {"record": admitted}}}])
    read = {"request_ros_clock": {"begin_monotonic_ns": 1900}, "response_ros_clock": {"end_monotonic_ns": 1950}}
    documents, pending = host._concurrent_apply_for(read)
    assert [document["association_id"] for document in documents] == ["A"] and pending is True, "apply-b has no association yet"
    disjoint = {"request_ros_clock": {"begin_monotonic_ns": 3000}, "response_ros_clock": {"end_monotonic_ns": 3100}}
    assert host._concurrent_apply_for(disjoint) == ([], False)
    # the Teacher event of an apply concurrent with the read is replayed after the read: until the replay is a settle time past
    # the read, "no overlapping apply" is not yet proof
    import time as time_module
    base = time_module.monotonic_ns()
    young = {"request_ros_clock": {"begin_monotonic_ns": base - 1000}, "response_ros_clock": {"end_monotonic_ns": base - 500}}
    assert host._concurrent_apply_for(young) == ([], True)
    old = {"request_ros_clock": {"begin_monotonic_ns": base - 10**9}, "response_ros_clock": {"end_monotonic_ns": base - 10**9 + 1}}
    assert host._concurrent_apply_for(old) == ([], False)
