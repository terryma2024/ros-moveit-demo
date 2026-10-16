"""The Teacher re-acquires a stale physics source right before its DETACH/SYNC apply (EXP-607).

A request names the snapshot it was built from. When the Teacher thread was off-CPU between that snapshot and the dispatch,
the named source is old against the simulation clock; the request is rebuilt from a fresh snapshot (bounded, journaled) and
still names exactly the snapshot it was built from. The 100 ms window and every data rule are untouched.
"""

import dataclasses
import json

from moveit_msgs.srv import GetPlanningScene

from so101_demo.act.teacher_endpoint import EXECUTION_KIND
from so101_demo.core.domain import State
from so101_demo.ros.dynamic_execution import scene as scene_module
from test_act_recorder_scene import Context
from test_act_scene_association import frozen_scene  # noqa: F401  (pytest fixture)
from test_act_teacher_scene_operations import harness


def teacher_adapter(ctx, ages_s):
    """A Teacher `_detach_or_sync` harness. The clock stands 1 s after the world's time; successive `_snapshot()` calls return
    sources whose ages against that clock are `ages_s` (the last one repeats)."""
    ctx.stamp()
    adapter, wire = harness(ctx)
    adapter._execution_policy = {"kind": EXECUTION_KIND, "state_max_age_s": 60.0}
    adapter._get_scene.respond = lambda request: GetPlanningScene.Response(scene=ctx.world_scene())
    clock_s = ctx.world.simulation_time_s + 1.0
    ctx.offset_ns = round(1.0 * 1e9)
    snaps = [dataclasses.replace(ctx.world, simulation_time_s=clock_s - age, simulation_step=ctx.world.simulation_step + index,
                                 publisher_sequence=ctx.world.publisher_sequence + index)
             for index, age in enumerate(ages_s)]
    taken = []

    def snapshot():
        taken.append(snaps[min(len(taken), len(snaps) - 1)])
        return taken[-1]

    adapter._snapshot = snapshot
    adapter._supported_release_preflight = snapshot
    named = []
    original = adapter._apply_scene.respond
    adapter._apply_scene.respond = lambda request: (named.append(dict(adapter._scene_op_source)), original(request))[1]
    adapter._scene_state_value = State.DETACH_MOVEIT.value
    return adapter, taken, named, snaps


def run(adapter):
    adapter._detach_or_sync(State.DETACH_MOVEIT)
    return adapter._document["scene_transactions"][-1]


def source_of(snap):
    return {"simulation_step": snap.simulation_step, "publisher_sequence": snap.publisher_sequence,
            "simulation_time_s": snap.simulation_time_s}


def test_constants_are_named_and_the_window_is_untouched():
    from so101_demo.act import recorder_scene

    assert scene_module.STALE_SOURCE_RESNAP_S == 0.05 and scene_module.STALE_SOURCE_RESNAP_MAX_ATTEMPTS == 3
    assert recorder_scene._WINDOW_NS == 100_000_000


def test_a_stale_source_is_re_snapshotted_and_the_fresh_source_is_named(frozen_scene):
    ctx = Context(frozen_scene)
    adapter, taken, named, snaps = teacher_adapter(ctx, [0.40, 0.01])
    transaction = run(adapter)
    assert taken[:-1] == snaps   # the last `_snapshot()` call is the post-detach record
    assert named == [source_of(snaps[1])]
    assert transaction["source_physics"]["publisher_sequence"] == snaps[1].publisher_sequence
    assert transaction["source_resnap"]["attempts"] == 1
    assert [round(age, 3) for age in transaction["source_resnap"]["source_ages_s"]] == [0.40, 0.01]
    assert transaction["source_resnap"]["threshold_s"] == 0.05 and transaction["source_resnap"]["max_attempts"] == 3
    assert transaction["geometry_verification"]["mismatches"] == []
    assert transaction["apply_call_id"] == adapter._scene_service_calls[0]["call_id"]
    json.dumps(adapter._document["scene_transactions"])   # the manifest still serialises every recorded transaction


def test_still_stale_after_the_bound_the_freshest_is_dispatched_and_every_attempt_recorded(frozen_scene):
    ctx = Context(frozen_scene)
    adapter, taken, named, snaps = teacher_adapter(ctx, [0.90, 0.80, 0.70, 0.60, 0.50])
    transaction = run(adapter)
    assert len(taken[:-1]) == 4  # the first snapshot and three re-snapshots, never more
    assert named == [source_of(snaps[3])]
    assert transaction["source_physics"]["publisher_sequence"] == snaps[3].publisher_sequence
    assert transaction["source_resnap"]["attempts"] == 3
    assert [round(age, 2) for age in transaction["source_resnap"]["source_ages_s"]] == [0.90, 0.80, 0.70, 0.60]
    assert len(adapter._document["scene_transactions"]) == 1


def test_a_fresh_source_takes_no_re_snapshot_and_adds_nothing(frozen_scene):
    ctx = Context(frozen_scene)
    adapter, taken, named, snaps = teacher_adapter(ctx, [0.02, 0.01])
    transaction = run(adapter)
    assert len(taken[:-1]) == 1 and named == [source_of(snaps[0])]
    assert "source_resnap" not in transaction
    assert transaction["source_physics"]["publisher_sequence"] == snaps[0].publisher_sequence


def test_a_source_just_inside_the_threshold_is_not_re_snapshotted(frozen_scene):
    ctx = Context(frozen_scene)
    adapter, taken, named, snaps = teacher_adapter(ctx, [0.049, 0.01])
    run(adapter)
    assert len(taken[:-1]) == 1
