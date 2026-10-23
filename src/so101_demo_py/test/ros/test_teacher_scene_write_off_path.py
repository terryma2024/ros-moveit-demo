"""No manifest write sits between a Teacher scene apply and its read-back request (EXP-608).

A slow manifest write (host IO pressure) right after the apply delayed the read-back request by 0.16-0.5 s, and the replay
then waited past its 100 ms window for the association built from that read-back. The transaction is persisted once, after
the read-back, on every exit path.
"""

import pytest
from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene

from so101_demo.core.domain import State
from test_act_recorder_scene import Context
from test_act_scene_association import frozen_scene  # noqa: F401  (pytest fixture)
from test_act_teacher_scene_operations import harness


def instrumented(ctx):
    adapter, wire = harness(ctx)
    adapter._scene_state_value = State.DETACH_MOVEIT.value
    log = []
    adapter._write = lambda: log.append(("write", len(wire), [dict(t) for t in adapter._document["scene_transactions"]]))
    adapter._apply_scene.respond = lambda request: (log.append(("apply",)), ApplyPlanningScene.Response(success=True))[1]
    scene = ctx.world_scene()
    adapter._get_scene.respond = lambda request: (log.append(("readback",)), GetPlanningScene.Response(scene=scene))[1]
    return adapter, log


def kinds(log):
    return [entry[0] for entry in log]


def test_no_write_between_the_apply_and_the_readback_request(frozen_scene):
    adapter, log = instrumented(Context(frozen_scene))
    adapter._detach_or_sync(State.DETACH_MOVEIT)
    assert kinds(log)[:2] == ["apply", "readback"]
    assert kinds(log).count("write") == 1 and kinds(log)[-1] == "write"
    transaction = log[-1][2][0]
    assert transaction["apply_call_id"] and transaction["query_call_id"] and transaction["geometry_verification"]


def test_a_slow_writer_does_not_delay_the_readback_request(frozen_scene):
    import time

    ctx = Context(frozen_scene)
    adapter, log = instrumented(ctx)
    stamps = {}
    apply_respond, get_respond = adapter._apply_scene.respond, adapter._get_scene.respond
    adapter._apply_scene.respond = lambda request: (apply_respond(request), stamps.setdefault("applied", time.monotonic()))[0]
    adapter._get_scene.respond = lambda request: (stamps.setdefault("readback", time.monotonic()), get_respond(request))[1]
    adapter._write = lambda: time.sleep(0.3)
    adapter._detach_or_sync(State.DETACH_MOVEIT)
    assert stamps["readback"] - stamps["applied"] < 0.1


def test_refused_apply_persists_once(frozen_scene):
    adapter, log = instrumented(Context(frozen_scene))
    adapter._apply_scene.respond = lambda request: (log.append(("apply",)), ApplyPlanningScene.Response(success=False))[1]
    with pytest.raises(RuntimeError, match="DYNAMIC_DETACH_SYNC_FAILED"):
        adapter._detach_or_sync(State.DETACH_MOVEIT)
    assert kinds(log) == ["apply", "write"]
    assert log[-1][2][0]["apply_call_id"]


def test_apply_exception_persists_once(frozen_scene):
    adapter, log = instrumented(Context(frozen_scene))

    def boom(request):
        raise RuntimeError("apply exploded")

    adapter._apply_scene.respond = boom
    with pytest.raises(RuntimeError, match="apply exploded"):
        adapter._detach_or_sync(State.DETACH_MOVEIT)
    assert kinds(log) == ["write"]
    assert len(log[-1][2]) == 1


def test_readback_exception_persists_once_with_the_apply_recorded(frozen_scene):
    adapter, log = instrumented(Context(frozen_scene))

    def boom(request):
        raise RuntimeError("readback exploded")

    adapter._get_scene.respond = boom
    with pytest.raises(RuntimeError, match="readback exploded"):
        adapter._detach_or_sync(State.DETACH_MOVEIT)
    assert kinds(log) == ["apply", "write"]
    assert log[-1][2][0]["apply_call_id"] and log[-1][2][0]["query_call_id"]


def test_readback_mismatch_persists_once(frozen_scene):
    ctx = Context(frozen_scene)
    adapter, log = instrumented(ctx)
    attached = ctx.attached_scene(0.0)
    adapter._get_scene.respond = lambda request: (log.append(("readback",)), GetPlanningScene.Response(scene=attached))[1]
    with pytest.raises(RuntimeError, match="DYNAMIC_DETACH_SYNC_READBACK_MISMATCH"):
        adapter._detach_or_sync(State.DETACH_MOVEIT)
    assert kinds(log) == ["apply", "readback", "write"]
