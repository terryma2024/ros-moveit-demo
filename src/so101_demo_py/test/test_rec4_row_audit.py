"""Recorder round 4 (CP-3407): the first row reached the recorder queue and its writer failed (RECORDER_QUEUE_WRITE_FAILED, 5.5 s
after ready, capture start +0.1 s). The live physical audit row must satisfy the recorder's closed audit schema."""
import copy
import math
from types import SimpleNamespace

import pytest

from test_act_live_physical_audit import provider
from test_act_scene_association import frozen_scene  # noqa: F401  (fixture)


def live_audit(frozen_scene):
    source, values, at_s = provider(frozen_scene)
    row = source(at_s)
    # what the capture adds: the sampler's source stamps (the LiveSampler narrows its audit to exactly this)
    row = dict(row, source_stamps={name: at_s for name in ("head", "wrist", "arm", "neck")},
               reference_time_s=at_s + .1, reference_source="CONTROLLER_REFERENCE", reference_positions=[0.] * 6)
    return row, at_s


def test_the_live_row_has_exactly_the_recorders_audit_keys(frozen_scene):
    from so101_demo.act.recorder import _AUDIT_KEYS
    row, _ = live_audit(frozen_scene)
    # the live provider owes the thirteen, the sampler source_stamps; the capture adds the episode's own two ids
    assert set(row) | {"session_id", "attempt_id"} == set(_AUDIT_KEYS)


def physical_13(at_s):
    """The thirteen values `PhysicalAuditAdapter.KEYS` hands the capture - exactly the live provider's shape."""
    from test_act_recorder import audit
    from so101_demo.act.episode_assembly import PhysicalAuditAdapter
    full = audit(at_s)
    return {key: full[key] for key in PhysicalAuditAdapter.KEYS}


def test_a_capture_over_the_live_row_shape_seals_through_the_real_recorder(tmp_path):
    """RED at L2: the 13 provider keys + source_stamps lack session_id and attempt_id, the recorder refused the first row
    (EPISODE_AUDIT_SCHEMA) in its writer thread and the run went INVALID with RECORDER_QUEUE_WRITE_FAILED."""
    from so101_demo.act.episode_assembly import assemble_episode_capture
    from test_act_seal_and_downgrade import IDENTITY, SCOPE, AcquisitionGuard, AcquisitionMinter, ProductionProducer, feed, reference
    from test_act_recorder import PROVENANCE

    root = tmp_path / "episode"
    capture = assemble_episode_capture(
        sampler=ProductionProducer(), physical_audit=physical_13, guard=AcquisitionGuard(), identity=IDENTITY,
        provenance=PROVENANCE, inputs={"inputs_sha256": "a" * 64}, episode_root=root, scope=SCOPE,
        scope_path=str(root / "audit" / "source.json"), deadline_s=120.0, monotonic=lambda: 0.0)
    minter = AcquisitionMinter()
    capture.start("session-1", "attempt-1", 2, 1.0)
    for stamp in (1.0, 1.1, 1.2, 1.3):
        for camera in ("head", "wrist"):
            feed(capture, minter, camera=camera, stamp_s=stamp, session="session-1", reset_epoch=2)
        capture.on_reference(reference(stamp + 0.1))
        capture.drain()
    capture.finish(1.3, window={"start_s": 1.0, "end_s": 1.3, "label_cutoff_s": 1.3},
                   outcome={"status": "FAILED", "reason": "search_failed", "task8_success": False,
                            "stopped_confirmed": True})
    assert (root / "seal.json").is_file() and len(list((root / "frames").glob("*-head.png"))) >= 2


def test_a_queue_write_failure_names_the_writers_exception_in_the_result(tmp_path):
    """L2 named only RECORDER_QUEUE_WRITE_FAILED: the writer thread's exception was kept in the queue and never reported."""
    import json
    from test_act_episode_recorder import build, result_of
    engine, sources, working = build(tmp_path)

    def failing(engine_):
        queue = engine_.episode.capture.recorder
        queue._writer_error = "ValueError('EPISODE_AUDIT_SCHEMA')"
        raise RuntimeError("RECORDER_QUEUE_WRITE_FAILED")

    sources.collect = failing
    engine.episode.capture.recorder = type("Q", (), {"snapshot": lambda self: {"writer_error": "ValueError('EPISODE_AUDIT_SCHEMA')"},
                                                    "check": lambda self: None, "close": lambda self: None,
                                                    "root": engine.episode.capture.recorder.root})()
    engine.run()
    first = result_of(working)["reasons"][0]
    assert first["reason"] == "RECORDER_QUEUE_WRITE_FAILED" and "EPISODE_AUDIT_SCHEMA" in first["writer_error"]


def test_the_real_providers_row_is_accepted_by_the_real_recorder(frozen_scene, tmp_path):
    """The values the live provider produces (native sample, planning-scene record, controller state) pass the recorder's checks."""
    from so101_demo.act.recorder import EpisodeRecorder
    from test_act_recorder import PROVENANCE, observation
    source, values, at_s = provider(frozen_scene)
    row = source(at_s)
    observed = observation(at_s)
    audit = dict(row, source_stamps={name: at_s for name in ("head", "wrist", "arm", "neck")},
                 reference_time_s=at_s + .1, reference_source="CONTROLLER_REFERENCE", reference_positions=[0.] * 6,
                 session_id="session-1", attempt_id="attempt-1", reset_epoch=2)
    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1", attempt_id="attempt-1", reset_epoch=2,
                               provenance=PROVENANCE)
    recorder.append(observed, (0.,) * 6, audit)
    assert (tmp_path / "episode" / "records.jsonl").stat().st_size > 0
