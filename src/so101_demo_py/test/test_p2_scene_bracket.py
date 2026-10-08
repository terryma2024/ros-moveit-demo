"""CP-3440 B: a planning-scene read is valid until the NEXT read when the scene is proven unchanged between them.

Pilot bag 031b82c6: the scene service stalled after the Teacher's acm_apply (one read took 251 ms), leaving a 148 ms hole in the
Recorder's reads; the row at 50.506 s had no read within 100 ms and the capture died with INPUT_STALE although the scene had not
changed. The single age rule `source_age_ok_ns` is unchanged; `bracketed_age_ok_ns` extends the validity of a read to the stamp of
the next one, and only with evidence: identical scene content, nothing applied in between. The evidence is part of the row.
"""
import copy
from types import SimpleNamespace

import pytest

from test_act_live_physical_audit import provider
from test_act_scene_association import frozen_scene  # noqa: F401  (fixture)

HOLE_S = 0.148


def moved(read, by_s, *, call_id):
    """The same read, `by_s` later on both clocks and in monotonic time (so it stays after the association's apply)."""
    other = copy.deepcopy(read)
    other["call_id"] = call_id
    shift = round(by_s * 1e9)
    for key in ("request_ros_clock", "response_ros_clock"):
        other[key]["sim_time_ns"] += shift
        other[key]["begin_monotonic_ns"] += shift
        other[key]["end_monotonic_ns"] += shift
    other["request_monotonic_ns"] += shift
    other["response_monotonic_ns"] += shift
    return other


def bracketed(frozen_scene, *, next_by=0.2, change=None):
    source, values, t = provider(frozen_scene)
    later = t + HOLE_S                                  # the row instant: 148 ms after the read, past the 100 ms rule
    values["physics"]["sample"]["simulation_time_s"] = later - 0.01
    values["controller"]["source_stamp_ns"] = round((later - 0.01) * 1e9)
    following = moved(values["planning"], next_by, call_id="following-read")
    if change == "geometry":
        following["response"]["scene"]["world"]["collision_objects"][0]["id"] = "foreign"
    source.planning_next_source = lambda at: copy.deepcopy(following)
    return source, values, later, following


def test_without_a_following_read_a_read_older_than_100_ms_is_not_ready(frozen_scene):
    source, values, later, _ = bracketed(frozen_scene)
    source.planning_next_source = None
    assert source.ready(later) is False


def test_a_hole_with_an_identical_bracket_is_ready_and_the_row_carries_the_evidence(frozen_scene):
    source, values, later, following = bracketed(frozen_scene)
    assert source.ready(later) is True
    row = source(later)
    scene = row["planning_scene"]
    assert scene["query_id"] == values["planning"]["call_id"]
    assert scene["bracket"]["next_query_id"] == "following-read"
    assert scene["bracket"]["next_record"]["response_ros_clock"]["sim_time_ns"] == following["response_ros_clock"]["sim_time_ns"]
    # the stamp stays the read's own: nothing is promoted to the instant
    assert row["physical_stamps"]["planning_scene"] == values["planning"]["response_ros_clock"]["sim_time_ns"] / 1e9


def test_a_fresh_read_needs_no_bracket_and_carries_none(frozen_scene):
    source, values, t = provider(frozen_scene)
    source.planning_next_source = lambda at: pytest.fail("a fresh read must not ask for the next one")
    assert "bracket" not in source(t)["planning_scene"]


def test_a_following_read_that_is_not_after_the_instant_does_not_bracket_it(frozen_scene):
    source, values, later, _ = bracketed(frozen_scene, next_by=0.1)   # response at stamp + 100 ms < the instant (+148 ms)
    assert source.ready(later) is False


def test_a_following_read_with_different_scene_content_is_refused(frozen_scene):
    source, values, later, _ = bracketed(frozen_scene, change="geometry")
    with pytest.raises(ValueError, match="LIVE_PHYSICAL_SCENE_GEOMETRY_INVALID"):
        source.ready(later)


def test_the_interval_test_is_only_the_extension_and_the_age_rule_is_unchanged():
    from so101_demo.act.synchronizer import bracketed_age_ok_ns, source_age_ok_ns
    assert source_age_ok_ns(200_000_000, 100_000_000) is True and source_age_ok_ns(200_000_001, 100_000_000) is False
    assert bracketed_age_ok_ns(250_000_000, 100_000_000, 300_000_000) is True
    assert bracketed_age_ok_ns(300_000_000, 100_000_000, 300_000_000) is False     # the next read's own instant is not bracketed
    assert bracketed_age_ok_ns(99_999_999, 100_000_000, 300_000_000) is False      # nor the future of the earlier read


# ---- the Recorder's source: the proof ------------------------------------------------------------------------------------

def sources_with(frozen_scene, *, applies=(), next_geometry_changed=False):
    from so101_demo.act import scene_association
    from so101_demo.ros.episode_recorder_sources import RosRecorderSources
    import threading
    from collections import deque

    source, values, t = provider(frozen_scene)
    document = source.scene_association_source(t)["association"]
    before = values["planning"]
    after = moved(before, 0.2, call_id="after")
    if next_geometry_changed:
        after["response"]["scene"]["world"]["collision_objects"][0]["id"] = "foreign"
    sources = RosRecorderSources.__new__(RosRecorderSources)
    sources._planning_lock = threading.Lock()
    sources._planning_calls = deque([before, after], maxlen=64)
    sources.tracker = SimpleNamespace(records=list(applies))
    sources._association_at = lambda at: source.scene_association_source(at)
    return sources, before, after, t


def apply_call(read, *, inside):
    """A Teacher /apply_planning_scene call that overlaps the interval between the two reads (or is far before it)."""
    shift = round(0.1 * 1e9) if inside else -round(5 * 1e9)
    return {"service": "/apply_planning_scene", "request_monotonic_ns": read["request_ros_clock"]["begin_monotonic_ns"] + shift,
            "response_monotonic_ns": read["request_ros_clock"]["begin_monotonic_ns"] + shift + 1_000_000}


def test_the_source_returns_the_read_and_the_following_one_for_a_proven_hole(frozen_scene):
    sources, before, after, t = sources_with(frozen_scene, applies=[])
    at = t + HOLE_S
    assert sources._planning_source_at(at)["call_id"] == before["call_id"]
    assert sources._planning_next_source_at(at)["call_id"] == "after"


def test_a_fresh_read_is_returned_as_before_and_no_following_read_is_offered(frozen_scene):
    sources, before, after, t = sources_with(frozen_scene, applies=[])
    assert sources._planning_source_at(t + 0.05)["call_id"] == before["call_id"]
    assert sources._planning_next_source_at(t + 0.05) is None


def test_a_hole_that_contains_an_apply_is_not_bracketed(frozen_scene):
    sources, before, after, t = sources_with(frozen_scene, applies=[])
    sources.tracker.records = [apply_call(before, inside=True)]
    assert sources._planning_source_at(t + HOLE_S) is None and sources._planning_next_source_at(t + HOLE_S) is None


def test_an_apply_long_before_the_hole_does_not_prevent_the_bracket(frozen_scene):
    sources, before, after, t = sources_with(frozen_scene, applies=[])
    sources.tracker.records = [apply_call(before, inside=False)]
    assert sources._planning_source_at(t + HOLE_S) is not None


def test_a_hole_with_differing_scene_content_keeps_the_100_ms_rule(frozen_scene):
    sources, before, after, t = sources_with(frozen_scene, next_geometry_changed=True)
    assert sources._planning_source_at(t + HOLE_S) is None


# ---- the Recorder's row audit and the QC reader accept exactly the bracketed row --------------------------------------------

def test_the_row_audit_admits_a_bracketed_stamp_only_with_the_bracket(tmp_path):
    from test_act_recorder import PROVENANCE, audit
    from so101_demo.act.recorder import EpisodeRecorder

    def row(at_s, bracket):
        full = audit(at_s)
        full["physical_stamps"]["planning_scene"] = at_s - HOLE_S
        full["planning_scene"] = {"query_id": "q", "association_id": "a", **({} if bracket is None else {"bracket": bracket})}
        return full

    def recorder(name):
        return EpisodeRecorder(tmp_path / name, session_id="session-1", attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)

    at_s = 5.0
    good = {"next_query_id": "n", "next_record": {"response_ros_clock": {"sim_time_ns": round((at_s + 0.05) * 1e9)}}}
    observation = {"sim_time_s": at_s, "state": [0.0] * 8}
    with pytest.raises(ValueError) as stale:
        recorder("none")._audit(observation, (0.0,) * 6, row(at_s, None))
    assert "EPISODE_SOURCE_STALE" in str(stale.value)
    for name, bracket in (("early", {"next_query_id": "n", "next_record": {"response_ros_clock": {"sim_time_ns": round((at_s - 0.01) * 1e9)}}}),
                          ("malformed", {"next_query_id": "n"})):
        with pytest.raises(ValueError) as refused:
            recorder(name)._audit(observation, (0.0,) * 6, row(at_s, bracket))
        assert "EPISODE_SOURCE_STALE" in str(refused.value)
    try:
        recorder("good")._audit(observation, (0.0,) * 6, row(at_s, good))
    except ValueError as error:
        assert "EPISODE_SOURCE_STALE" not in str(error), "a proven bracket must pass the age check"


def test_the_qc_reader_recomputes_the_bracket_from_the_two_original_reads(frozen_scene):
    """The fixture's row sits at t = 2 ms, so the read cannot be made 148 ms old here; the age arithmetic of a stale read is covered
    by the provider and the row-audit tests above. What the reader owes is the proof: the following read after the instant, causal
    after the same association, the same geometry, and no scene change between the two."""
    from test_act_episode_physical_readback import materials, verify

    def with_bracket(change=None):
        rows, chunks, associations, inputs, identity = materials(frozen_scene)
        audit = rows[0]["audit"]
        t = rows[0]["observation"]["sim_time_s"]
        query = audit["planning_scene"]["record"]
        following = moved(query, 0.1, call_id="following")          # after the first read in monotonic time too
        for key in ("request_ros_clock", "response_ros_clock"):
            following[key]["sim_time_ns"] = round((t + 0.05) * 1e9)
        audit["planning_scene"]["bracket"] = {"next_query_id": "following", "next_record": following}
        if change == "geometry":
            following["response"]["scene"]["world"]["collision_objects"][0]["id"] = "foreign"
        if change == "not_after_instant":
            for key in ("request_ros_clock", "response_ros_clock"):
                following[key]["sim_time_ns"] = round(t * 1e9)
        if change == "id":
            audit["planning_scene"]["bracket"]["next_query_id"] = "other"
        if change == "before_apply":
            following["request_ros_clock"]["begin_monotonic_ns"] = 1
        return rows, chunks, associations, inputs, identity

    rows, chunks, associations, inputs, identity = with_bracket()
    try:
        assert verify(rows, raw_chunks=chunks, associations=associations, inputs=inputs, identity=identity)["rows"] == 1
    except ValueError as error:
        import traceback
        pytest.fail("a proven bracket was refused: " + "".join(traceback.format_exception(error.__cause__))[-900:])
    for change in ("geometry", "not_after_instant", "id", "before_apply"):
        rows, chunks, associations, inputs, identity = with_bracket(change)
        with pytest.raises(ValueError, match="EPISODE_PHYSICAL_READBACK_INVALID"):
            verify(rows, raw_chunks=chunks, associations=associations, inputs=inputs, identity=identity)


def test_a_retained_ros_record_with_tagged_non_finite_values_decodes_and_round_trips():
    """Pilot bag 031b82c6: the retained planning-scene read of a row carries NaN fields. The audit keeps them as `__non_finite_float__`
    tags (canonical JSON refuses NaN); the QC reader decoded the tagged record with `set_message_fields` and failed with
    SOURCE_ALIGNMENT_ROS_CONTENT_INVALID ('must be real number, not dict'). The tag is the exact inverse of the original."""
    import math

    from moveit_msgs.msg import CollisionObject
    from moveit_msgs.srv import GetPlanningScene
    from rosidl_runtime_py.convert import message_to_ordereddict

    from so101_demo.act.nonfinite import json_safe
    from so101_demo.act.scene_association import canonical, decode_ros

    response = GetPlanningScene.Response()
    response.scene.world.collision_objects.append(CollisionObject(id="box"))
    response.scene.world.collision_objects[0].pose.position.x = math.nan
    response.scene.world.collision_objects[0].pose.position.y = -math.inf
    tagged = json_safe(dict(message_to_ordereddict(response)))
    assert tagged["scene"]["world"]["collision_objects"][0]["pose"]["position"]["x"] == {"__non_finite_float__": "nan"}
    decoded = decode_ros(GetPlanningScene.Response, tagged)
    pose = decoded.scene.world.collision_objects[0].pose.position
    assert math.isnan(pose.x) and pose.y == -math.inf
    assert canonical(json_safe(dict(message_to_ordereddict(decoded)))) == canonical(tagged)
    finite = GetPlanningScene.Response()
    assert decode_ros(GetPlanningScene.Response, dict(message_to_ordereddict(finite))) == finite     # nothing changes for finite records
