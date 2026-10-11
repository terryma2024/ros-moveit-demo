"""Retained original published World candidates, independently bound to native steps."""

import copy

import pytest

from test_act_scene_association import association, frozen_scene  # noqa: F401  (pytest fixture)


def source_record(frozen_scene):
    from so101_demo.act.native_endpoints import world_source_record
    from so101_demo.act.scene_association import _world
    from so101_demo.core.simulation.types import ReceivedSimulationEvidence
    document, raw = association(frozen_scene)
    source = document["source"]
    record = world_source_record(ReceivedSimulationEvidence(_world(source["physics"]),
        source["received_monotonic_ns"] / 1e9), (source["scene_state"], source["scene_received_monotonic_ns"] / 1e9),
        execution_root=frozen_scene[0])
    return record, raw


@pytest.mark.parametrize("change", [None, "pose", "raw_time", "scene_qpos", "scene_scope", "frame", "version", "future_receipt", "missing_raw"])
def test_original_world_record_requires_exact_native_and_frozen_model(frozen_scene, change):
    from so101_demo.act.native_endpoints import verify_world_source
    record, raw = source_record(frozen_scene)
    if change == "pose":
        record["physics"]["object_state"]["position_world"][0] += .01
    elif change == "raw_time":
        raw[0]["simulation_time_s"] += .01
    elif change == "scene_qpos":
        record["scene_state"]["qpos"][0] += .01
    elif change == "scene_scope":
        record["scene_state"]["reset_epoch"] += 1
    elif change == "frame":
        record["physics"]["frame_id"] = "gripper"
    elif change == "version":
        record["schema_version"] = True
    elif change == "future_receipt":
        record["scene_received_monotonic_ns"] = record["scene_state"]["clock_interval_end_monotonic_ns"] - 1
    elif change == "missing_raw":
        raw = []
    if change is None:
        from so101_demo.act.diagnostic_episode_inputs import audit_execution_model_identity
        assert verify_world_source(record, identity={"session_id": "alignment-session", "reset_epoch": 1},
            model=frozen_scene[2], model_identity=audit_execution_model_identity(frozen_scene[1]), raw_steps=raw) is True
    else:
        from so101_demo.act.diagnostic_episode_inputs import audit_execution_model_identity
        with pytest.raises(ValueError):
            verify_world_source(record, identity={"session_id": "alignment-session", "reset_epoch": 1},
                model=frozen_scene[2], model_identity=audit_execution_model_identity(frozen_scene[1]), raw_steps=raw)


def test_world_candidate_sequence_gap_and_replay_are_not_complete_history(frozen_scene):
    from so101_demo.act.native_endpoints import validate_world_source
    first, _ = source_record(frozen_scene)
    validate_world_source(first, identity={"session_id": "alignment-session", "reset_epoch": 1})
    following = copy.deepcopy(first)
    for increment in (0, 2):
        following["physics"]["publisher_sequence"] = first["physics"]["publisher_sequence"] + increment
        with pytest.raises(ValueError, match="WORLD_SOURCE_SEQUENCE_INVALID"):
            validate_world_source(following, identity={"session_id": "alignment-session", "reset_epoch": 1}, previous=first)


@pytest.mark.parametrize("norm", [.99925, 1.00075, .99875, 1.00125])
def test_original_world_raw_quaternion_uses_approved_norm_tolerance(frozen_scene, norm):
    from so101_demo.act.native_endpoints import validate_world_source
    record, _ = source_record(frozen_scene)
    record["physics"]["object_state"]["orientation_xyzw"] = [0., 0., 0., norm]
    if abs(norm - 1.) <= .001:
        validate_world_source(record, identity={"session_id": "alignment-session", "reset_epoch": 1})
    else:
        with pytest.raises(ValueError):
            validate_world_source(record, identity={"session_id": "alignment-session", "reset_epoch": 1})


def test_actual_audit_retains_world_source_and_independent_reader_refuses_resigned_native_mismatch(frozen_scene, tmp_path):
    import hashlib
    import json
    import shutil
    from so101_demo.act.collection_scope import build_collection_scope
    from so101_demo.act.episode_audit.verification import verify_audit_manifest
    from so101_demo.act.episode_audit.writer import EpisodeAuditWriter
    from so101_demo.act.lossless_recorder import LosslessRecorderQueue
    from so101_demo.act.scene_association import canonical
    from test_act_lossless_recorder_queue import POLICY
    record, raw = source_record(frozen_scene)
    identity = {"session_id": "alignment-session", "attempt_id": "attempt", "reset_epoch": 1, "release_epoch": 0,
        "scene_id": "default", "seed": 0, "mode": "preselected_target_diagnostic"}
    scope = build_collection_scope(identity["mode"], scene_id="default", seed=0,
        inputs_sha256=frozen_scene[1]["inputs_sha256"])
    writer = EpisodeAuditWriter(tmp_path / "episode", scope, identity, frozen_scene[1])
    try:
        writer.append_raw_physics({"schema_version": 1, "received_monotonic_ns": raw[-1]["clock_interval_begin_monotonic_ns"] + 1_000_000,
            "chunk": {"chunk_sequence": 1, "simulation_session_id": "alignment-session", "reset_epoch": 1,
                "first_physics_step": 1, "last_physics_step": 1, "first_simulation_time_s": raw[0]["simulation_time_s"],
                "last_simulation_time_s": raw[0]["simulation_time_s"], "failed_publish_attempts": 0, "handoff_monotonic_ns": 0, "publish_monotonic_ns": 0,
                "publish_deferrals_total": 0,
                "evidence_loss": False, "samples": raw}})
        writer.append_world_source(record)
        queue = LosslessRecorderQueue(object(), policy=POLICY)
        queue.close()
        writer.append_recorder_queue(queue.snapshot(), sim_time_s=raw[0]["simulation_time_s"])
        path = writer.seal({"start_s": .002, "end_s": .002, "label_cutoff_s": .002})
    finally:
        for stream in writer._streams.values():
            stream.close()
    assert verify_audit_manifest(path)["identity"] == identity
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    copied = tmp_path / "isolated-resigned-source"
    shutil.copytree(path.parent, copied)
    events_path = copied / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_bytes().splitlines()]
    event = next(value for value in events if value["kind"] == "world_source")
    event["payload"]["world_source"]["scene_state"]["qpos"][0] += .01
    payload = b"".join(canonical(value) + b"\n" for value in events)
    events_path.write_bytes(payload)
    manifest = json.loads(path.read_bytes())
    manifest["files"]["events.jsonl"].update(size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    copied_manifest = copied / path.name
    copied_manifest.write_bytes(canonical(manifest))
    with pytest.raises(ValueError):
        verify_audit_manifest(copied_manifest)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert verify_audit_manifest(path)["identity"] == identity


@pytest.mark.parametrize("late", [False, True])
def test_actual_child_drains_original_candidates_without_skipping_missing_scene(frozen_scene, monkeypatch, late):
    from types import SimpleNamespace
    from so101_demo.act.scene_association import _world
    from so101_demo.core.simulation.types import ReceivedSimulationEvidence
    from so101_demo.ros.recorder_data_side import RecorderDataSide
    document, _ = source_record(frozen_scene)
    source = ReceivedSimulationEvidence(_world(document["physics"]), document["received_monotonic_ns"] / 1e9)
    scene = (document["scene_state"], document["scene_received_monotonic_ns"] / 1e9)
    value = RecorderDataSide.__new__(RecorderDataSide)
    value._world_record_cursor = source.evidence.publisher_sequence - 1
    value._execution_snapshot_root = frozen_scene[0]
    value._session_id, value._expected_reset_epoch = "alignment-session", 1
    value.observer = SimpleNamespace(original_records_after=lambda cursor: (source,) if cursor < source.evidence.publisher_sequence else ())
    scenes, retained = [], []
    value._scene_source_binding = SimpleNamespace(observer=SimpleNamespace(original_frames_with_receipts=lambda min_simulation_step=None: tuple(scenes)))
    value.episode_recorder = SimpleNamespace(capture=SimpleNamespace(audit=SimpleNamespace(append_world_source=retained.append)))
    now = [10.]
    monkeypatch.setattr("so101_demo.ros.recorder_data_side.time.monotonic", lambda: now[0])
    assert value._drain_world_sources() == 0 and retained == []
    assert value._world_record_cursor == source.evidence.publisher_sequence - 1
    if late:
        # The 100 ms is judged on the receipts (a frame received 101 ms after its world record), not on the
        # pass cadence; a frame that is merely observed late by a slow pass is covered by test_recorder_hot_path_defects.
        scene = (scene[0], scene[1] + .101)
    scenes.append(scene)
    if late:
        now[0] += .101
        for _ in range(2):
            with pytest.raises(RuntimeError, match="DYNAMIC_WORLD_SOURCE_SCENE_MISSING"):
                value._drain_world_sources()
        assert retained == [] and value._world_record_cursor == source.evidence.publisher_sequence - 1
        return
    assert value._drain_world_sources() == 1 and retained == [document]
    originals=getattr(value,'original_collection_worlds',None)
    assert callable(originals),'FIRST runtime has no readonly original world history'
    assert originals()==[document]
    copied=originals();copied[0]['physics']['publisher_sequence']+=1
    assert originals()==[document],'caller changed the retained original world source'
    assert value._drain_world_sources() == 0
