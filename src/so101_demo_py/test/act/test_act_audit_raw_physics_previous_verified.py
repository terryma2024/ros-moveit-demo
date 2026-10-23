"""The audit writer does not verify the previous raw chunk a second time (to-do 2e).

`verify_raw_chunk(record, previous=...)` verifies `previous` first, as a record on its own, unless the caller says `previous_verified`.
The writer's previous chunk is the record it verified one append ago, with the same arguments, so it says so."""
from act_episode_audit_support import identity, scope
import pytest

from so101_demo.act import raw_physics_chunks
from so101_demo.act.episode_audit.writer import EpisodeAuditWriter


def chunk_event(sequence):
    raw = {"received_monotonic_ns": 10 + sequence,
           "chunk": {"last_simulation_time_s": 0.1 * sequence, "chunk_sequence": sequence, "simulation_session_id": "s", "reset_epoch": 1,
                     "samples": [{"physics_step": 5 * sequence - 1, "simulation_time_s": 0.1 * sequence - 0.002,
                                  "clock_interval_end_monotonic_ns": 7 * sequence, "model_qpos": [0.5]},
                                 {"physics_step": 5 * sequence, "simulation_time_s": 0.1 * sequence,
                                  "clock_interval_end_monotonic_ns": 7 * sequence + 1, "model_qpos": [0.5]}]}}
    return {"kind": "physics_chunk", "identity": identity(), "sim_time_s": 0.1 * sequence, "monotonic_ns": 1000 + sequence,
            "payload": {"raw_chunk": raw}}


def test_only_the_first_chunk_is_verified_without_a_verified_previous(tmp_path, monkeypatch):
    calls = []

    def verify(record, **kwargs):
        if "previous" not in kwargs:        # the standalone check of the payload types (`checks._payload_typed`)
            return
        calls.append((record["chunk"]["chunk_sequence"], kwargs["previous"] and kwargs["previous"]["chunk"]["chunk_sequence"],
                      kwargs.get("previous_verified")))
    monkeypatch.setattr(raw_physics_chunks, "verify_raw_chunk", verify)
    writer = EpisodeAuditWriter(tmp_path / "episode", scope(), identity(), {"inputs_sha256": "a" * 64})
    for sequence in (1, 2, 3):
        writer.append_source("events", chunk_event(sequence))
    assert calls == [(1, None, False), (2, 1, True), (3, 2, True)]


def test_the_kept_previous_chunk_holds_exactly_what_the_continuity_check_reads(tmp_path, monkeypatch):
    kept = []
    monkeypatch.setattr(raw_physics_chunks, "verify_raw_chunk",
                        lambda record, **kwargs: kept.append(kwargs["previous"]) if "previous" in kwargs else None)
    writer = EpisodeAuditWriter(tmp_path / "episode", scope(), identity(), {"inputs_sha256": "a" * 64})
    writer.append_source("events", chunk_event(1))
    writer.append_source("events", chunk_event(2))
    assert kept == [None, {"received_monotonic_ns": 11, "chunk": {
        "chunk_sequence": 1, "simulation_session_id": "s", "reset_epoch": 1,
        "samples": [{"physics_step": 5, "simulation_time_s": 0.1, "clock_interval_end_monotonic_ns": 8}]}}]


def test_a_refused_chunk_is_not_remembered_as_previous(tmp_path, monkeypatch):
    seen = []

    def verify(record, **kwargs):
        if "previous" not in kwargs:
            return
        seen.append(kwargs["previous"] and kwargs["previous"]["chunk"]["chunk_sequence"])
        if record["chunk"]["chunk_sequence"] == 2:
            raise ValueError("PHYSICS_RAW_CONTINUITY")
    monkeypatch.setattr(raw_physics_chunks, "verify_raw_chunk", verify)
    writer = EpisodeAuditWriter(tmp_path / "episode", scope(), identity(), {"inputs_sha256": "a" * 64})
    writer.append_source("events", chunk_event(1))
    with pytest.raises(ValueError, match="PHYSICS_RAW_CONTINUITY"):
        writer.append_source("events", chunk_event(2))
    writer.append_source("events", chunk_event(3))
    assert seen == [None, 1, 1]
