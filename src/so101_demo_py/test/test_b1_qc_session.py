"""Phase B1: the QC repeats pure verifiers over unchanged files; a session runs each once, and nothing else about the verdict changes.

`qc_session` keeps a verifier's result only for the duration of one session, keyed on the arguments and on the signature of every
file the call reads. These tests pin the contract (scope, invalidation, errors, sharing) and the equivalence of the faster
primitives with the checks they replaced.
"""

import copy
import math

import pytest
from so101_demo.act import qc_session
from so101_demo.act.qc_session import (
    Identity,
    cached_lines,
    file_signature,
    session_memo,
    tree_signature,
)
from so101_demo.act.qc_session import qc_session as session_scope


def counting(tmp_path):
    """A memoised 'verifier' over the files below `tmp_path`: it returns their total size and counts its runs."""
    calls = []

    @session_memo(lambda root: (str(root), tree_signature(root)))
    def verify(root):
        calls.append(root)
        return {"size": sum(path.stat().st_size for path in root.rglob("*") if path.is_file())}

    return verify, calls


def test_outside_a_session_nothing_is_kept(tmp_path):
    (tmp_path / "a").write_text("x")
    verify, calls = counting(tmp_path)
    assert verify(tmp_path) == verify(tmp_path) == {"size": 1}
    assert len(calls) == 2 and qc_session.active() is None


def test_inside_a_session_the_second_call_over_the_same_files_is_a_hit(tmp_path):
    (tmp_path / "a").write_text("x")
    verify, calls = counting(tmp_path)
    with session_scope() as session:
        assert verify(tmp_path) == {"size": 1}
        assert verify(tmp_path) == {"size": 1}
    assert len(calls) == 1 and (session.hits, session.misses) == (1, 1)
    assert session.computations == {verify.__wrapped__.__qualname__: 1}


@pytest.mark.parametrize("change", ["content", "added", "removed", "replaced"])
def test_a_changed_file_is_never_served_from_the_session(tmp_path, change):
    (tmp_path / "a").write_text("xx")
    (tmp_path / "b").write_text("yy")
    verify, calls = counting(tmp_path)
    with session_scope():
        verify(tmp_path)
        if change == "content":
            (tmp_path / "a").write_text("xxx")
        elif change == "added":
            (tmp_path / "c").write_text("z")
        elif change == "removed":
            (tmp_path / "b").unlink()
        else:
            (tmp_path / "a").unlink()
            (tmp_path / "a").write_text("qq")      # same size, new inode and mtime
        verify(tmp_path)
    assert len(calls) == 2


def test_a_verifier_that_raises_is_not_remembered(tmp_path):
    state = {"calls": 0}

    @session_memo(lambda: "key")
    def verify():
        state["calls"] += 1
        raise ValueError("EPISODE_BROKEN")

    with session_scope():
        for _ in range(2):
            with pytest.raises(ValueError, match="EPISODE_BROKEN"):
                verify()
    assert state["calls"] == 2


def test_a_session_ends_with_its_context_and_a_nested_session_is_separate(tmp_path):
    (tmp_path / "a").write_text("x")
    verify, calls = counting(tmp_path)
    with session_scope() as outer:
        verify(tmp_path)
        with session_scope() as inner:
            verify(tmp_path)                       # the inner session starts empty
            assert qc_session.active() is inner
        assert qc_session.active() is outer
    assert qc_session.active() is None and len(calls) == 2
    verify(tmp_path)
    assert len(calls) == 3


def test_the_result_is_copied_in_and_out_unless_sharing_is_asked_for(tmp_path):
    (tmp_path / "a").write_text("x")
    verify, _ = counting(tmp_path)
    with session_scope():
        first = verify(tmp_path)
        first["size"] = 99
        assert verify(tmp_path) == {"size": 1}

    @session_memo(lambda: "shared", copy_result=False)
    def shared():
        return {"n": 1}

    with session_scope():
        assert shared() is shared()


def test_identity_keys_compare_by_object_not_by_value():
    one, same_value = [1], [1]
    assert Identity(one) == Identity(one) and Identity(one) != Identity(same_value)
    assert len({Identity(one), Identity(one), Identity(same_value)}) == 2


def test_cached_lines_share_one_parse_per_kind_and_per_file_signature(tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_text('{"n":1}\n{"n":2}\n')
    parses = []

    def parse(target):
        parses.append(target)
        return [{"n": 1}, {"n": 2}]

    with session_scope():
        first = cached_lines(path, parse)
        assert cached_lines(path, parse) is first
        assert cached_lines(path, parse, "lenient") is not first      # another kind is another entry
        path.write_text('{"n":1}\n{"n":2}\n{"n":3}\n')
        assert cached_lines(path, parse) is not first
    assert len(parses) == 3
    assert cached_lines(path, parse) is not cached_lines(path, parse)  # outside a session nothing is shared


def test_file_signature_changes_with_size_inode_and_mtime(tmp_path):
    path = tmp_path / "f"
    path.write_text("a")
    before = file_signature(path)
    path.write_text("ab")
    assert file_signature(path) != before
    assert file_signature(tmp_path / "missing")[1] is None


def test_the_model_is_loaded_once_per_session_and_not_shared_outside_one(tmp_path, monkeypatch):
    import mujoco

    scene = tmp_path / "scene.xml"
    scene.write_text('<mujoco><worldbody><body name="b"><geom size="0.1"/></body></worldbody></mujoco>')
    loads = []
    real = mujoco.MjModel.from_xml_path
    monkeypatch.setattr(mujoco.MjModel, "from_xml_path", staticmethod(lambda path: loads.append(path) or real(path)))
    first = qc_session.load_model(scene)
    assert qc_session.load_model(scene) is not first and len(loads) == 2
    with session_scope():
        one = qc_session.load_model(scene)
        assert qc_session.load_model(scene) is one
    assert len(loads) == 3


# ---- the faster primitives give the verdict of the ones they replaced ----------------------------------------------------

from so101_demo.act import raw_physics_chunks as raw  # noqa: E402

NUMBER_CASES = [0, 1, -1, 0.0, -0.0, 1.5, -2.5, 10 ** 30, 1e308, True, False, None, "1", "x", [], (1,), float("nan"),
                float("inf"), -float("inf"), 2 ** 70]


def reference_number(value, *, nonnegative=False):
    """The check `_numbers` replaced, as it was written."""
    if type(value) not in (int, float) or not math.isfinite(value) or nonnegative and value < 0:
        raise ValueError("PHYSICS_RAW_NUMBER_INVALID")


def verdict(function, *args, **kwargs):
    try:
        function(*args, **kwargs)
    except Exception as error:   # noqa: BLE001 - the type and message are the verdict
        return type(error), str(error)
    return None


@pytest.mark.parametrize("nonnegative", [False, True])
def test_the_batch_number_check_has_the_verdict_of_the_per_value_check(nonnegative):
    for first in NUMBER_CASES:
        for second in NUMBER_CASES:
            batch = verdict(raw._numbers, [first, second], nonnegative=nonnegative)
            single = verdict(lambda: [reference_number(item, nonnegative=nonnegative) for item in (first, second)])
            assert batch == single, (first, second)


def test_vector_and_xyz_keep_their_error_codes():
    assert verdict(raw._vector, [0.1, 0.2], 2) is None
    assert verdict(raw._vector, [], None) == (ValueError, "PHYSICS_RAW_VECTOR_INVALID")
    assert verdict(raw._vector, [0.1], 2) == (ValueError, "PHYSICS_RAW_VECTOR_INVALID")
    assert verdict(raw._vector, [0.1, True], 2) == (ValueError, "PHYSICS_RAW_NUMBER_INVALID")
    assert verdict(raw._xyz, {"x": 0, "y": 1.0, "z": -2}) is None
    assert verdict(raw._xyz, {"x": 0, "y": 1.0}) == (ValueError, "PHYSICS_RAW_SCHEMA_INVALID")
    assert verdict(raw._xyz, {"x": 0, "y": float("nan"), "z": 1}) == (ValueError, "PHYSICS_RAW_NUMBER_INVALID")
    assert verdict(raw._exact, [1], {"a"}) == (ValueError, "PHYSICS_RAW_SCHEMA_INVALID")


def make_chunk(sequence, first, count=3, receipt=10 ** 12):
    def sample(step):
        return {"simulation_session_id": "s", "reset_epoch": 1, "physics_step": step, "simulation_time_s": step * 0.002,
                "clock_interval_begin_monotonic_ns": 10 ** 9 + step * 2_000_000,
                "clock_interval_end_monotonic_ns": 10 ** 9 + step * 2_000_000 + 1_000_000, "model_qpos": [0.1, 0.2],
                "model_qvel": [0.0], "object_pose_world": {"position": {"x": 0.0, "y": 0.0, "z": 0.1},
                                                           "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}},
                "object_twist_world": {"linear": {"x": 0.0, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": 0.0}},
                "has_contact": False, "truncated": False, "maximum_normal_force_n": 0.0, "total_normal_force_n": 0.0,
                "left_fingertip_total_normal_force_n": 0.0, "right_fingertip_total_normal_force_n": 0.0,
                "fingertip_max_single_contact_force_n": 0.0, "global_max_single_contact_force_n": 0.0,
                "left_fingertip_compression_m": 0.0, "right_fingertip_compression_m": 0.0,
                "net_contact_force_world_n": {"x": 0.0, "y": 0.0, "z": 0.0}, "static_shadow_crossed": False,
                "diagnostic_hazard_breached": False, "left_fingertip_contacts": [], "right_fingertip_contacts": [],
                "other_object_contacts": []}
    samples = [sample(step) for step in range(first, first + count)]
    return {"schema_version": 1, "received_monotonic_ns": receipt,
            "chunk": {"chunk_sequence": sequence, "simulation_session_id": "s", "reset_epoch": 1,
                      "first_physics_step": first, "last_physics_step": first + count - 1,
                      "first_simulation_time_s": samples[0]["simulation_time_s"],
                      "last_simulation_time_s": samples[-1]["simulation_time_s"], "failed_publish_attempts": 0,
                      "handoff_monotonic_ns": 0, "publish_monotonic_ns": 0, "publish_deferrals_total": 0,
                      "evidence_loss": False, "samples": samples}}


KWARGS = dict(session_id="s", reset_epoch=1, nq=2, nv=1, max_samples=10, max_contacts=10)


def test_a_valid_chain_of_chunks_verifies_with_and_without_the_previous_check():
    first, second = make_chunk(1, 1), make_chunk(2, 4, receipt=10 ** 12 + 1)
    assert raw.verify_raw_chunk(first, **KWARGS) is first
    assert raw.verify_raw_chunk(second, previous=first, **KWARGS) is second
    assert raw.verify_raw_chunk(second, previous=first, previous_verified=True, **KWARGS) is second


def test_the_previous_chunk_is_verified_unless_the_caller_says_it_just_was():
    first, second = make_chunk(1, 1), make_chunk(2, 4, receipt=10 ** 12 + 1)
    first["chunk"]["samples"][0]["model_qpos"][0] = "x"
    with pytest.raises(ValueError, match="PHYSICS_RAW_NUMBER_INVALID"):
        raw.verify_raw_chunk(second, previous=first, **KWARGS)
    # the flag is the caller's statement; the chunk is then not looked at again (the loops that pass it verified it a pass earlier)
    assert raw.verify_raw_chunk(second, previous=first, previous_verified=True, **KWARGS) is second


def test_continuity_between_chunks_is_still_enforced_when_the_previous_is_not_rechecked():
    first, gap = make_chunk(1, 1), make_chunk(2, 9, receipt=10 ** 12 + 1)
    with pytest.raises(ValueError, match="PHYSICS_RAW_CONTINUITY_INVALID"):
        raw.verify_raw_chunk(gap, previous=first, previous_verified=True, **KWARGS)
    wrong_sequence = make_chunk(5, 4, receipt=10 ** 12 + 1)
    with pytest.raises(ValueError, match="PHYSICS_RAW_CONTINUITY_INVALID"):
        raw.verify_raw_chunk(wrong_sequence, previous=first, previous_verified=True, **KWARGS)


def test_inside_a_session_one_chunk_is_verified_once_per_set_of_arguments():
    first = make_chunk(1, 1)
    with session_scope() as session:
        raw.verify_raw_chunk(first, **KWARGS)
        raw.verify_raw_chunk(first, **KWARGS)
        raw.verify_raw_chunk(first, **dict(KWARGS, max_samples=11))      # other arguments are another check
        assert session.computations == {"verify_raw_chunk": 2}
    first["chunk"]["samples"][0]["model_qvel"][0] = None
    with session_scope():
        with pytest.raises(ValueError, match="PHYSICS_RAW_NUMBER_INVALID"):
            raw.verify_raw_chunk(first, **KWARGS)


# ---- the step index that replaced the quadratic scan ---------------------------------------------------------------------

def test_raw_steps_at_gives_the_samples_of_a_step_in_list_order_for_short_and_long_lists():
    from so101_demo.act import native_endpoints

    short = [{"physics_step": step % 5, "tag": step} for step in range(30)]
    long = [{"physics_step": step % 40, "tag": step} for step in range(400)]
    for samples in (short, long):
        for step in (0, 3, 39, 77, -1):
            assert native_endpoints._raw_steps_at(samples, step) == [item for item in samples if item["physics_step"] == step]
    other = copy.deepcopy(long)
    other[3]["physics_step"] = 777
    assert native_endpoints._raw_steps_at(other, 777) == [other[3]]       # a different list is indexed afresh


# ---- where the sessions are opened ----------------------------------------------------------------------------------------

def test_recompute_native_qc_opens_a_session_when_none_is_active_and_joins_the_one_that_is(monkeypatch):
    from so101_demo.act import episode_qc

    seen = []
    monkeypatch.setattr(episode_qc, "_recompute_native_qc", lambda *args, **kwargs: seen.append(qc_session.active()) or {"ok": True})
    assert qc_session.active() is None
    episode_qc.recompute_native_qc("e", scope="s", inputs_manifest="i")
    assert seen[0] is not None and qc_session.active() is None
    with session_scope() as outer:
        episode_qc.recompute_native_qc("e", scope="s", inputs_manifest="i")
    assert seen[1] is outer


def test_the_offline_engine_seals_and_reads_back_inside_one_session(tmp_path, monkeypatch):
    from test_act_episode_recorder import NOT_EXHAUSTED, build, result_of

    engine, _, working = build(tmp_path)
    inside = []
    original = engine._seal
    monkeypatch.setattr(engine, "_seal", lambda: (inside.append(qc_session.active()), original())[1])
    assert engine.process(NOT_EXHAUSTED) == 0
    assert inside and inside[0] is not None and qc_session.active() is None
    assert result_of(working)["status"] == "VALID"
