"""CP-3449: the apply-bounded bracket.

Pilot bag 429dbf50: the Teacher's attach apply answered at 62.894 s, the grid row sat at 62.900 s, and the first planning-scene read
that could follow the apply answered at 62.918 s. A row may only use a read that began after the apply and is not from the future, so
the row had no scene source and the capture died with INPUT_STALE although the scene was the one the apply had just produced.

For a row between the apply's response and the first read after it, the scene source is that APPLY when all hold: the apply
succeeded; the first read after it carries the association's geometry; no other apply lies between the two. The row then carries the
apply as `planning_scene.record` and that read as `bracket.next_record`. Every other scene rule is unchanged.

The numbers of the real case, relative to the apply response (62.894): row +6 ms, following read +24 ms.
"""
import copy
import threading
from collections import deque
from types import SimpleNamespace

import pytest

from test_act_live_physical_audit import provider
from test_act_scene_association import frozen_scene  # noqa: F401  (fixture)
from test_p2_scene_bracket import moved

ROW_AFTER_APPLY_S = 0.006
READ_AFTER_APPLY_S = 0.024


def apply_form(frozen_scene, *, change=None):
    source, values, t = provider(frozen_scene)
    document = source.scene_association_source(t)["association"]
    apply = copy.deepcopy(document["apply"]["record"])
    row_at = t + ROW_AFTER_APPLY_S
    values["physics"]["sample"]["simulation_time_s"] = row_at - 0.002
    values["controller"]["source_stamp_ns"] = round((row_at - 0.002) * 1e9)
    following = moved(values["planning"], READ_AFTER_APPLY_S, call_id="following-read")
    if change == "geometry":
        following["response"]["scene"]["world"]["collision_objects"][0]["id"] = "foreign"
    if change == "failed":
        apply["response"]["success"] = False
    if change == "foreign_apply":
        apply["call_id"] = "another-apply"
    values["planning"] = apply
    source.planning_next_source = None if change == "no_following" else (lambda at: copy.deepcopy(following))
    source.planning_source = lambda at: copy.deepcopy(values["planning"])
    return source, values, row_at, following, document


def test_a_row_between_the_apply_and_the_first_read_is_ready_and_carries_the_apply_and_the_read(frozen_scene):
    source, values, row_at, following, document = apply_form(frozen_scene)
    assert source.ready(row_at) is True
    scene = source(row_at)["planning_scene"]
    assert scene["query_id"] == document["apply"]["record"]["call_id"] and scene["record"]["service"] == "/apply_planning_scene"
    assert scene["bracket"]["next_query_id"] == "following-read"
    assert scene["bracket"]["next_record"]["response_ros_clock"]["sim_time_ns"] == following["response_ros_clock"]["sim_time_ns"]
    # the stamp stays the apply's own: nothing is promoted to the instant
    row = provider_row(source, row_at)
    assert row["physical_stamps"]["planning_scene"] == document["apply"]["record"]["response_ros_clock"]["sim_time_ns"] / 1e9


def provider_row(source, row_at):
    source._last_grid_ns = None
    return source(row_at)


def test_without_the_following_read_the_apply_alone_is_not_a_source(frozen_scene):
    source, values, row_at, _, _ = apply_form(frozen_scene, change="no_following")
    assert source.ready(row_at) is False


def test_a_following_read_with_other_scene_content_is_invalid(frozen_scene):
    source, values, row_at, _, _ = apply_form(frozen_scene, change="geometry")
    with pytest.raises(ValueError, match="LIVE_PHYSICAL_SCENE_GEOMETRY_INVALID"):
        source.ready(row_at)


def test_a_failed_apply_is_invalid(frozen_scene):
    source, values, row_at, _, _ = apply_form(frozen_scene, change="failed")
    with pytest.raises(ValueError, match="LIVE_PHYSICAL_SCENE"):
        source.ready(row_at)


def test_an_apply_that_is_not_the_governing_associations_is_invalid(frozen_scene):
    source, values, row_at, _, _ = apply_form(frozen_scene, change="foreign_apply")
    with pytest.raises(ValueError, match="LIVE_PHYSICAL_SCENE"):
        source.ready(row_at)


# ---- the Recorder's source: the proof ------------------------------------------------------------------------------------

def sources_with(frozen_scene, *, others=(), changed=False, extra_before=False):
    from so101_demo.act.offline.sources import OfflineRosSources

    source, values, t = provider(frozen_scene)
    document = source.scene_association_source(t)["association"]
    anchor = document["apply"]["record"]
    after = moved(values["planning"], READ_AFTER_APPLY_S, call_id="after")
    if changed:
        after["response"]["scene"]["world"]["collision_objects"][0]["id"] = "foreign"
    sources = OfflineRosSources.__new__(OfflineRosSources)
    sources._planning_lock = threading.Lock()
    sources._planning_calls = deque([after], maxlen=64)
    sources.tracker = SimpleNamespace(records=[copy.deepcopy(anchor), *others])
    sources._association_at = lambda at: source.scene_association_source(at)
    return sources, anchor, after, t


def other_apply(anchor, *, after, success=True):
    """A Teacher apply that falls between the anchor apply and the following read."""
    return {"service": "/apply_planning_scene", "call_id": "other-apply",
            "request_monotonic_ns": anchor["response_monotonic_ns"] + 1_000,
            "response_monotonic_ns": anchor["response_monotonic_ns"] + 2_000,
            "response": {"success": success}}


def test_the_source_returns_the_apply_and_the_following_read(frozen_scene):
    sources, anchor, after, t = sources_with(frozen_scene)
    at = t + ROW_AFTER_APPLY_S
    assert sources._planning_source_at(at)["call_id"] == anchor["call_id"]
    assert sources._planning_next_source_at(at)["call_id"] == "after"


def test_a_second_apply_between_the_two_leaves_the_row_without_a_source(frozen_scene):
    sources, anchor, after, t = sources_with(frozen_scene)
    sources.tracker.records.append(other_apply(anchor, after=after))
    at = t + ROW_AFTER_APPLY_S
    assert sources._planning_source_at(at) is None and sources._planning_next_source_at(at) is None


def test_a_failed_second_apply_between_the_two_also_counts(frozen_scene):
    sources, anchor, after, t = sources_with(frozen_scene)
    sources.tracker.records.append(other_apply(anchor, after=after, success=False))
    assert sources._planning_source_at(t + ROW_AFTER_APPLY_S) is None


def test_a_following_read_with_other_content_leaves_the_row_without_a_source(frozen_scene):
    sources, anchor, after, t = sources_with(frozen_scene, changed=True)
    assert sources._planning_source_at(t + ROW_AFTER_APPLY_S) is None


def test_a_failed_anchor_apply_is_no_source(frozen_scene):
    sources, anchor, after, t = sources_with(frozen_scene)
    sources.tracker.records[0]["response"]["success"] = False
    sources._association_at = lambda at: _failed(sources, frozen_scene, at)
    assert sources._planning_source_at(t + ROW_AFTER_APPLY_S) is None


def _failed(sources, frozen_scene, at):
    source, values, t = provider(frozen_scene)
    bound = source.scene_association_source(t)
    bound["association"]["apply"]["record"]["response"]["success"] = False
    return bound


def test_a_read_before_the_instant_keeps_the_read_rules(frozen_scene):
    """Only a row with no usable read at or before it is served by the apply: with one, the 100 ms rule and CP-3440 B decide."""
    sources, anchor, after, t = sources_with(frozen_scene)
    before = moved(after, -0.020, call_id="before")      # a read that answered at t + 4 ms, before the row
    sources._planning_calls = deque([before, after], maxlen=64)
    assert sources._planning_source_at(t + ROW_AFTER_APPLY_S)["call_id"] == "before"


# ---- the QC reader recomputes it from the original records -------------------------------------------------------------------

def test_the_qc_reader_accepts_the_apply_bracket_and_refuses_what_is_not_proven(frozen_scene):
    from test_act_episode_physical_readback import materials, verify

    def build(change=None):
        rows, chunks, associations, inputs, identity = materials(frozen_scene)
        audit = rows[0]["audit"]
        t = rows[0]["observation"]["sim_time_s"]
        document = associations[0]
        apply = copy.deepcopy(document["apply"]["record"])
        query = audit["planning_scene"]["record"]
        following = moved(query, 0.1, call_id="following")
        for key in ("request_ros_clock", "response_ros_clock"):
            following[key]["sim_time_ns"] = round((t + 0.05) * 1e9)
        audit["planning_scene"] = {"query_id": apply["call_id"], "record": apply, "association_id": document["association_id"],
                                   "bracket": {"next_query_id": "following", "next_record": following}}
        audit["physical_stamps"]["planning_scene"] = apply["response_ros_clock"]["sim_time_ns"] / 1e9
        if change == "geometry":
            following["response"]["scene"]["world"]["collision_objects"][0]["id"] = "foreign"
        if change == "failed":
            apply["response"]["success"] = False
        if change == "not_the_anchor":
            apply["call_id"] = audit["planning_scene"]["query_id"] = "another"
        if change == "no_bracket":
            del audit["planning_scene"]["bracket"]
        if change == "read_before_apply":
            following["request_ros_clock"]["begin_monotonic_ns"] = 1
        if change == "not_after_instant":
            for key in ("request_ros_clock", "response_ros_clock"):
                following[key]["sim_time_ns"] = round(t * 1e9)
        return rows, chunks, associations, inputs, identity

    rows, chunks, associations, inputs, identity = build()
    try:
        assert verify(rows, raw_chunks=chunks, associations=associations, inputs=inputs, identity=identity)["rows"] == 1
    except ValueError as error:
        import traceback
        pytest.fail("a proven apply bracket was refused: " + "".join(traceback.format_exception(error.__cause__))[-900:])
    for change in ("geometry", "failed", "not_the_anchor", "no_bracket", "read_before_apply", "not_after_instant"):
        rows, chunks, associations, inputs, identity = build(change)
        with pytest.raises(ValueError, match="EPISODE_PHYSICAL_READBACK_INVALID"):
            verify(rows, raw_chunks=chunks, associations=associations, inputs=inputs, identity=identity)


def test_the_row_audit_refuses_an_apply_without_the_read_that_follows_it(tmp_path):
    from test_act_recorder import PROVENANCE, audit
    from so101_demo.act.recorder import EpisodeRecorder

    at_s = 5.0
    observation = {"sim_time_s": at_s, "state": [0.0] * 8}

    def row(bracket):
        full = audit(at_s)
        full["physical_stamps"]["planning_scene"] = at_s - 0.006
        full["planning_scene"] = {"query_id": "q", "association_id": "a", "record": {"service": "/apply_planning_scene"},
                                  **({} if bracket is None else {"bracket": bracket})}
        return full

    def recorder(name):
        return EpisodeRecorder(tmp_path / name, session_id="session-1", attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)

    with pytest.raises(ValueError) as refused:
        recorder("none")._audit(observation, (0.0,) * 6, row(None))
    assert "EPISODE_SOURCE_STALE" in str(refused.value)
    good = {"next_query_id": "n", "next_record": {"response_ros_clock": {"sim_time_ns": round((at_s + 0.018) * 1e9)}}}
    try:
        recorder("good")._audit(observation, (0.0,) * 6, row(good))
    except ValueError as error:
        assert "EPISODE_SOURCE_STALE" not in str(error)
