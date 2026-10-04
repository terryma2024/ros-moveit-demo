"""Contract tests for the single-owner Head file evidence protocol."""

import hashlib
import json
import math
import os
from pathlib import Path
import queue
import threading
import time

import pytest

try:
    from so101_demo.act.head_run_evidence import HeadRunEvidence
except ModuleNotFoundError as error:
    if error.name != "so101_demo.act.head_run_evidence":
        raise
    HeadRunEvidence = None


def test_writer_api_is_available():
    assert HeadRunEvidence is not None, "HeadRunEvidence protocol writer is not implemented"


def require_writer():
    if HeadRunEvidence is None:
        pytest.skip("writer API unavailable; see test_writer_api_is_available")


def create(tmp_path, *, capacities=None, faults=None, fault_callback=None):
    require_writer()
    root = tmp_path / "run"
    return HeadRunEvidence.create(
        root,
        {"file_protocol_version": 1, "run_id": "unit-test", "identity": {"scope": "local"}},
        capacities or {},
        fault_callback=fault_callback or (faults.append if faults is not None else None),
    ), root


def finish_ok(writer, **completion):
    return writer.finish({"intended_return_code": 0, "result": "ok", **completion})


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_continuous_global_sequence_preserves_kind_record_and_independent_clocks(tmp_path):
    writer, root = create(tmp_path)
    writer.append("IMAGE", {"original": {"pixel": [11, 12]}, "schema_version": 3},
                  source_stamp_ns=None, observed_mono_ns=20, occurrence_mono_ns=7)
    writer.append("CLOCK", {"wall_ns": 0, "sim_ns": None},
                  source_stamp_ns=0, observed_mono_ns=10, occurrence_mono_ns=30)
    receipt = finish_ok(writer)
    events = rows(root / "events.jsonl")
    assert [event["sequence"] for event in events] == [1, 2]
    assert [(event["kind"], event["record"]) for event in events] == [
        ("IMAGE", {"original": {"pixel": [11, 12]}, "schema_version": 3}),
        ("CLOCK", {"wall_ns": 0, "sim_ns": None}),
    ]
    assert events[0]["source_stamp_ns"] is None
    assert events[0]["occurrence_mono_ns"] == 7
    assert events[1]["source_stamp_ns"] == 0
    assert events[1]["observed_mono_ns"] == 10
    assert events[1]["occurrence_mono_ns"] == 30
    assert receipt["event_count"] == 2


def test_concurrent_producers_receive_one_continuous_global_sequence(tmp_path):
    writer, root = create(tmp_path)
    assigned = []
    assigned_lock = threading.Lock()

    def produce(worker):
        local = []
        for index in range(20):
            sequence = writer.append("RAW", {"worker": worker, "index": index},
                                     source_stamp_ns=None, observed_mono_ns=worker,
                                     occurrence_mono_ns=index)
            local.append(sequence)
        with assigned_lock:
            assigned.extend(local)

    producers = [threading.Thread(target=produce, args=(worker,)) for worker in range(4)]
    for producer in producers:
        producer.start()
    for producer in producers:
        producer.join(timeout=1)
        assert not producer.is_alive()
    finish_ok(writer)
    sequences = [event["sequence"] for event in rows(root / "events.jsonl")]
    assert len(sequences) == 80
    assert sequences == list(range(1, 81))
    assert sorted(assigned) == sequences


def test_queued_records_are_defensively_copied_before_append_returns(tmp_path):
    writer, root = create(tmp_path)
    record = {"nested": [1, {"value": "original"}]}
    writer.append("RAW", record, source_stamp_ns=1, observed_mono_ns=2,
                  occurrence_mono_ns=3)
    record["nested"][1]["value"] = "mutated"
    finish_ok(writer)
    assert rows(root / "events.jsonl")[0]["record"]["nested"][1]["value"] == "original"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_json_values_are_rejected_without_emitting_nonstandard_json(tmp_path, bad):
    writer, root = create(tmp_path)
    with pytest.raises((TypeError, ValueError)):
        writer.append("BAD", {"value": bad}, source_stamp_ns=1,
                      observed_mono_ns=2, occurrence_mono_ns=3)
    with pytest.raises(RuntimeError):
        finish_ok(writer)
    assert (root / "events.jsonl").read_bytes() == b""
    assert not (root / "seal.json").exists()


def test_non_utf8_text_is_rejected_before_queueing(tmp_path):
    writer, root = create(tmp_path)
    with pytest.raises((TypeError, ValueError, UnicodeError)):
        writer.append("BAD\udcff", {}, source_stamp_ns=1,
                      observed_mono_ns=2, occurrence_mono_ns=3)
    with pytest.raises(RuntimeError):
        finish_ok(writer)
    assert (root / "events.jsonl").read_bytes() == b""
    assert not (root / "seal.json").exists()


def test_capacity_and_high_water_counters_are_sealed_and_append_is_nonblocking(tmp_path):
    writer, root = create(tmp_path, capacities={"event_queue_capacity": 2,
                                                "max_event_bytes": 1024,
                                                "max_queue_bytes": 2048})
    start = time.monotonic()
    for index in range(2):
        writer.append("FAST", {"index": index}, source_stamp_ns=None,
                      observed_mono_ns=index, occurrence_mono_ns=index)
    assert time.monotonic() - start < 0.1
    seal = finish_ok(writer)
    assert seal["counters"]["event_capacity"] == 2
    assert 1 <= seal["counters"]["event_high_water"] <= 2
    assert seal["counters"]["event_count"] == 2


def test_default_protocol_queue_capacities_are_recorded_in_manifest(tmp_path):
    writer, root = create(tmp_path)
    finish_ok(writer)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["writer_capacities"]["event_queue_capacity"] == 4096
    assert manifest["writer_capacities"]["artifact_queue_capacity"] == 8


def test_oversized_event_fault_is_sticky_not_silent_and_cannot_seal(tmp_path):
    faults = []
    writer, root = create(tmp_path, capacities={"max_event_bytes": 256}, faults=faults)
    with pytest.raises((BufferError, OverflowError, ValueError)):
        writer.append("TOO_LARGE", {"value": "x" * 1000}, source_stamp_ns=1,
                      observed_mono_ns=2, occurrence_mono_ns=3)
    with pytest.raises(RuntimeError):
        finish_ok(writer)
    assert faults
    assert not (root / "seal.json").exists()


def test_event_queue_overflow_notifies_local_fault_callback_and_never_seals(tmp_path, monkeypatch):
    require_writer()
    from so101_demo.act import head_run_evidence as module

    entered = threading.Event()
    release = threading.Event()
    original = module.HeadRunEvidence._write_event

    def blocked(self, item):
        if not entered.is_set():
            entered.set()
            assert release.wait(2)
        return original(self, item)

    monkeypatch.setattr(module.HeadRunEvidence, "_write_event", blocked)
    faults = []
    writer, root = create(tmp_path, capacities={"event_queue_capacity": 2}, faults=faults)
    writer.append("FIRST", {}, source_stamp_ns=None, observed_mono_ns=1,
                  occurrence_mono_ns=1)
    assert entered.wait(1)
    writer.append("SECOND", {}, source_stamp_ns=None, observed_mono_ns=2,
                  occurrence_mono_ns=2)
    with pytest.raises((BufferError, OverflowError, RuntimeError)):
        writer.append("THIRD", {}, source_stamp_ns=None, observed_mono_ns=3,
                      occurrence_mono_ns=3)
    assert faults
    release.set()
    with pytest.raises(RuntimeError):
        finish_ok(writer)
    assert not (root / "seal.json").exists()


def test_artifact_queue_overflow_is_bounded_and_never_seals(tmp_path, monkeypatch):
    require_writer()
    from so101_demo.act import head_run_evidence as module

    entered = threading.Event()
    release = threading.Event()
    original = module.HeadRunEvidence._write_artifact

    def blocked(self, item):
        if not entered.is_set():
            entered.set()
            assert release.wait(2)
        return original(self, item)

    monkeypatch.setattr(module.HeadRunEvidence, "_write_artifact", blocked)
    faults = []
    writer, root = create(tmp_path, capacities={"artifact_queue_capacity": 2}, faults=faults)
    writer.add_artifact(b"first", media_type="application/octet-stream", suffix="bin")
    assert entered.wait(1)
    writer.add_artifact(b"second", media_type="application/octet-stream", suffix="bin")
    with pytest.raises(BufferError):
        writer.add_artifact(b"third", media_type="application/octet-stream", suffix="bin")
    assert faults
    release.set()
    with pytest.raises(RuntimeError):
        finish_ok(writer)
    assert not (root / "seal.json").exists()


def test_artifact_is_stored_once_with_verified_sha_and_referenced_by_event(tmp_path):
    writer, root = create(tmp_path)
    raw = b"original image bytes\x00\xff"
    ref = writer.add_artifact(raw, media_type="image/jpeg", suffix="jpg")
    assert writer.add_artifact(raw, media_type="image/jpeg", suffix="jpg") == ref
    writer.append("IMAGE", {"encoding": "jpeg", "width": 1, "height": 1},
                  source_stamp_ns=9, observed_mono_ns=10, occurrence_mono_ns=8,
                  artifact_refs=(ref,))
    seal = finish_ok(writer)
    path = root / ref["path"]
    assert path.read_bytes() == raw
    assert ref["size"] == len(raw)
    assert ref["sha256"] == hashlib.sha256(raw).hexdigest()
    assert rows(root / "events.jsonl")[0]["artifact_refs"] == [ref]
    assert sum(item["path"] == ref["path"] for item in seal["files"]) == 1


@pytest.mark.parametrize("suffix", ["../manifest.json", "/tmp/out", "", ".", ".."])
def test_artifact_suffix_cannot_escape_artifact_directory_or_overwrite_run_files(tmp_path, suffix):
    writer, root = create(tmp_path)
    with pytest.raises((ValueError, PermissionError)):
        writer.add_artifact(b"outside", media_type="application/octet-stream", suffix=suffix)
    finish_ok(writer)
    assert (root / "manifest.json").is_file()
    assert not (root.parent / "manifest.json").exists()


def test_foreign_or_traversal_artifact_reference_is_rejected(tmp_path):
    writer, root = create(tmp_path)
    with pytest.raises((ValueError, PermissionError)):
        writer.append("REF", {}, source_stamp_ns=None, observed_mono_ns=1,
                      occurrence_mono_ns=1,
                      artifact_refs=({"path": "../manifest.json", "size": 1,
                                      "sha256": "0" * 64},))
    finish_ok(writer)
    assert rows(root / "events.jsonl") == []


def test_root_must_be_new_and_symlink_root_is_rejected(tmp_path):
    require_writer()
    existing = tmp_path / "taken"
    existing.mkdir()
    with pytest.raises((FileExistsError, ValueError)):
        HeadRunEvidence.create(existing, {"file_protocol_version": 1}, {})
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "link"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises((FileExistsError, OSError, ValueError)):
        HeadRunEvidence.create(link, {"file_protocol_version": 1}, {})
    assert list(outside.iterdir()) == []


def test_fault_counters_stick_and_fault_callback_is_called_once(tmp_path):
    faults = []
    writer, root = create(tmp_path, capacities={"max_event_bytes": 128}, faults=faults)
    with pytest.raises((BufferError, OverflowError, ValueError)):
        writer.append("BIG", {"payload": "z" * 300}, source_stamp_ns=None,
                      observed_mono_ns=1, occurrence_mono_ns=1)
    with pytest.raises(PermissionError):
        writer.append("LATER", {}, source_stamp_ns=None,
                      observed_mono_ns=2, occurrence_mono_ns=2)
    with pytest.raises(RuntimeError):
        finish_ok(writer)
    assert len(faults) == 1
    assert not (root / "seal.json").exists()


def test_worker_write_error_and_fsync_error_notify_fault_and_prevent_seal(tmp_path, monkeypatch):
    require_writer()
    from so101_demo.act import head_run_evidence as module

    faults = []
    writer, root = create(tmp_path, faults=faults)
    writer.append("EVENT", {}, source_stamp_ns=None, observed_mono_ns=1,
                  occurrence_mono_ns=1)
    monkeypatch.setattr(module, "_fsync_descriptor", lambda _fd: (_ for _ in ()).throw(OSError("ENOSPC")))
    with pytest.raises(RuntimeError):
        finish_ok(writer)
    assert faults
    assert not (root / "seal.json").exists()


def test_worker_event_write_error_is_sticky_and_prevents_seal(tmp_path, monkeypatch):
    require_writer()
    from so101_demo.act import head_run_evidence as module

    faults = []
    writer, root = create(tmp_path, faults=faults)
    monkeypatch.setattr(module.HeadRunEvidence, "_write_event",
                        lambda *_args: (_ for _ in ()).throw(OSError("disk write failed")))
    writer.append("EVENT", {}, source_stamp_ns=None, observed_mono_ns=1,
                  occurrence_mono_ns=1)
    deadline = time.monotonic() + 1
    while not faults and time.monotonic() < deadline:
        time.sleep(0.005)
    with pytest.raises(RuntimeError):
        finish_ok(writer)
    assert faults
    assert not (root / "seal.json").exists()


def test_tail_corruption_or_readback_hash_mismatch_cannot_produce_success_seal(tmp_path, monkeypatch):
    require_writer()
    from so101_demo.act import head_run_evidence as module

    writer, root = create(tmp_path)
    writer.append("EVENT", {"ok": True}, source_stamp_ns=1, observed_mono_ns=2,
                  occurrence_mono_ns=3)
    original = module._verify_readback

    def corrupt(run_root, *args, **kwargs):
        with (run_root / "events.jsonl").open("ab") as stream:
            stream.write(b'{"sequence":\n')
            stream.flush()
            os.fsync(stream.fileno())
        return original(run_root, *args, **kwargs)

    monkeypatch.setattr(module, "_verify_readback", corrupt)
    with pytest.raises(RuntimeError):
        finish_ok(writer)
    assert not (root / "seal.json").exists()


def test_artifact_sha_mismatch_during_readback_cannot_produce_success_seal(tmp_path, monkeypatch):
    require_writer()
    from so101_demo.act import head_run_evidence as module

    writer, root = create(tmp_path)
    ref = writer.add_artifact(b"original", media_type="application/octet-stream", suffix="bin")
    writer.append("RAW", {}, source_stamp_ns=None, observed_mono_ns=1,
                  occurrence_mono_ns=1, artifact_refs=(ref,))
    original = module._verify_readback

    def corrupt_artifact(run_root, *args, **kwargs):
        (run_root / ref["path"]).write_bytes(b"tampered")
        return original(run_root, *args, **kwargs)

    monkeypatch.setattr(module, "_verify_readback", corrupt_artifact)
    with pytest.raises(RuntimeError):
        finish_ok(writer)
    assert not (root / "seal.json").exists()


@pytest.mark.parametrize("failure_point", ["completion", "rename", "parent_fsync"])
def test_publication_failures_never_delete_or_claim_a_success_seal(
        tmp_path, monkeypatch, failure_point):
    require_writer()
    from so101_demo.act import head_run_evidence as module

    writer, root = create(tmp_path)
    if failure_point == "completion":
        target = "_write_completion"
        replacement = lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("completion ENOSPC"))
    elif failure_point == "rename":
        target = "_atomic_replace"
        replacement = lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("rename failed"))
    else:
        target = "_fsync_directory"
        replacement = lambda path: (_ for _ in ()).throw(OSError("directory fsync failed"))

        # This guard records an attempted deletion while preserving the
        # synthetic partial evidence tree for inspection.
        deleted = []
        original_unlink = Path.unlink

        def guarded_unlink(path, *args, **kwargs):
            if path == root / "seal.json":
                deleted.append(path)
                return None
            return original_unlink(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", guarded_unlink)
    monkeypatch.setattr(module, target, replacement)
    with pytest.raises(RuntimeError):
        finish_ok(writer)
    if failure_point == "parent_fsync":
        assert (root / "seal.json").is_file()
        assert deleted == []
    else:
        assert not (root / "seal.json").exists()


@pytest.mark.parametrize("relative", ["manifest.json", "events.jsonl", "completion.json"])
def test_valid_json_readback_tampering_is_detected_against_original_bytes(
        tmp_path, monkeypatch, relative):
    require_writer()
    from so101_demo.act import head_run_evidence as module

    writer, root = create(tmp_path)
    writer.append("EVENT", {"value": "original"}, source_stamp_ns=1,
                  observed_mono_ns=2, occurrence_mono_ns=3)
    original = module._verify_readback

    def tamper_then_readback(run_root, *args, **kwargs):
        target = run_root / relative
        value = json.loads(target.read_text(encoding="utf-8"))
        if relative == "events.jsonl":
            value["record"]["value"] = "tampered"
            target.write_text(json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n",
                              encoding="utf-8")
        else:
            value["tampered"] = True
            target.write_text(json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n",
                              encoding="utf-8")
        return original(run_root, *args, **kwargs)

    monkeypatch.setattr(module, "_verify_readback", tamper_then_readback)
    with pytest.raises(RuntimeError):
        finish_ok(writer)
    assert not (root / "seal.json").exists()


def test_worker_waits_for_explicit_finish_after_closed_state(tmp_path, monkeypatch):
    waiting = threading.Event()
    release = threading.Event()
    original_get = queue.Queue.get
    original_start = threading.Thread.start

    def delayed_empty(work_queue, *args, **kwargs):
        if getattr(work_queue, "_hfp_test_gate", False):
            work_queue._hfp_test_gate = False
            waiting.set()
            assert release.wait(1)
            raise queue.Empty
        return original_get(work_queue, *args, **kwargs)

    def gated_start(thread):
        if thread.name == "head-run-evidence-writer":
            writer = thread._target.__self__
            writer._queue._hfp_test_gate = True
        return original_start(thread)

    monkeypatch.setattr(queue.Queue, "get", delayed_empty)
    monkeypatch.setattr(threading.Thread, "start", gated_start)
    writer, root = create(tmp_path)
    outcome = []

    def finish():
        try:
            outcome.append(finish_ok(writer))
        except BaseException as error:
            outcome.append(error)

    finisher = threading.Thread(target=finish)
    finisher.start()
    assert waiting.wait(1)
    deadline = time.monotonic() + 1
    while not writer._closed and time.monotonic() < deadline:
        time.sleep(0.001)
    assert writer._closed
    release.set()
    finisher.join(timeout=1)
    assert not finisher.is_alive()
    assert len(outcome) == 1 and isinstance(outcome[0], dict)
    assert (root / "seal.json").is_file()


def test_faulted_bounded_close_cancels_worker_after_queue_drains(tmp_path, monkeypatch):
    require_writer()
    waiting = threading.Event()
    release = threading.Event()
    original_get = queue.Queue.get
    original_start = threading.Thread.start

    def gated_get(work_queue, *args, **kwargs):
        if getattr(work_queue, "_hfp_test_gate", False):
            work_queue._hfp_test_gate = False
            waiting.set()
            release.wait()
            raise queue.Empty
        return original_get(work_queue, *args, **kwargs)

    def gated_start(thread):
        if thread.name == "head-run-evidence-writer":
            writer = thread._target.__self__
            writer._queue._hfp_test_gate = True
        return original_start(thread)

    monkeypatch.setattr(queue.Queue, "get", gated_get)
    monkeypatch.setattr(threading.Thread, "start", gated_start)
    writer, root = create(
        tmp_path,
        capacities={"event_queue_capacity": 1, "artifact_queue_capacity": 1},
    )
    try:
        assert waiting.wait(1)
        writer.append("EVENT", {}, source_stamp_ns=None, observed_mono_ns=1,
                      occurrence_mono_ns=1)
        writer.add_artifact(b"artifact", media_type="application/octet-stream", suffix="bin")
        with pytest.raises(RuntimeError, match="HEAD_RUN_EVIDENCE_CLOSE_TIMEOUT"):
            writer.finish({"intended_return_code": 0, "result": "ok"}, timeout_s=0.01)
        assert writer._closed and writer._failed
        release.set()
        writer._thread.join(timeout=0.5)
        assert not writer._thread.is_alive(), "faulted closed writer worker did not cancel"
        assert writer._events.closed
        assert writer._queue.unfinished_tasks == 0
        assert writer._pending_events == writer._pending_artifacts == writer._pending_bytes == 0
        assert not (root / "completion.json").exists()
        assert not (root / "seal.json").exists()
    finally:
        release.set()
        # The pre-fix worker has no fault-cancellation branch. Give it an owned
        # sentinel after queued work drains so this behavioral RED stays bounded.
        if writer._thread.is_alive():
            try:
                writer._queue.put(None, timeout=1)
            except queue.Full:
                pass
            writer._thread.join(timeout=1)


def test_fault_drain_handles_queued_finish_as_finish_and_balances_queue(tmp_path, monkeypatch):
    require_writer()
    from so101_demo.act import head_run_evidence as module

    entered = threading.Event()
    release = threading.Event()
    writer, root = create(tmp_path)
    uncaught = []
    monkeypatch.setattr(threading, "excepthook", lambda args: uncaught.append(args.exc_value))

    def fail_after_finish_is_queued(_self, _item):
        entered.set()
        assert release.wait(1)
        raise OSError("injected event failure")

    monkeypatch.setattr(module.HeadRunEvidence, "_write_event", fail_after_finish_is_queued)
    writer.append("EVENT", {}, source_stamp_ns=None, observed_mono_ns=1,
                  occurrence_mono_ns=1)
    assert entered.wait(1)
    errors = []
    finisher = threading.Thread(target=lambda: _finish_capture(writer, errors))
    finisher.start()
    deadline = time.monotonic() + 1
    while writer._queue.empty() and time.monotonic() < deadline:
        time.sleep(0.001)
    assert not writer._queue.empty()
    release.set()
    finisher.join(timeout=1)
    writer._thread.join(timeout=1)
    assert not finisher.is_alive() and not writer._thread.is_alive()
    assert errors and isinstance(errors[0], RuntimeError)
    assert uncaught == []
    assert writer._queue.unfinished_tasks == 0
    assert writer._pending_events == writer._pending_artifacts == writer._pending_bytes == 0
    assert not (root / "seal.json").exists()


def _finish_capture(writer, errors):
    try:
        finish_ok(writer)
    except BaseException as error:
        errors.append(error)


def test_parent_symlink_is_rejected_before_any_run_files_are_written(tmp_path):
    require_writer()
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(outside, target_is_directory=True)
    run_root = linked_parent / "run"
    with pytest.raises((OSError, ValueError)):
        HeadRunEvidence.create(run_root, {"file_protocol_version": 1}, {})
    assert linked_parent.is_symlink()
    assert list(outside.iterdir()) == []


def test_artifacts_directory_symlink_is_rejected_and_displaced_directory_retained(tmp_path):
    require_writer()
    writer, root = create(tmp_path)
    outside = tmp_path / "outside-artifacts"
    outside.mkdir()
    displaced = root / "artifacts.displaced"
    (root / "artifacts").rename(displaced)
    (root / "artifacts").symlink_to(outside, target_is_directory=True)
    writer.add_artifact(b"artifact", media_type="application/octet-stream", suffix="bin")
    deadline = time.monotonic() + 1
    while not writer._failed and time.monotonic() < deadline:
        time.sleep(0.001)
    with pytest.raises(RuntimeError):
        finish_ok(writer)
    assert displaced.is_dir()
    assert (root / "artifacts").is_symlink()
    assert list(outside.iterdir()) == []


def test_oversized_memoryview_is_rejected_before_copy(tmp_path, monkeypatch):
    require_writer()
    from so101_demo.act import head_run_evidence as module

    writer, _root = create(tmp_path, capacities={"max_artifact_bytes": 4})
    copy_called = []
    bytes_type = bytes

    class ObservedBytes(bytes_type):
        def __new__(cls, value=b"", *args, **kwargs):
            copy_called.append(value)
            return super().__new__(cls, value, *args, **kwargs)

    monkeypatch.setattr(module, "bytes", ObservedBytes, raising=False)
    with pytest.raises(BufferError):
        writer.add_artifact(memoryview(bytearray(b"oversized")),
                            media_type="application/octet-stream", suffix="bin")
    assert copy_called == []
    with pytest.raises(RuntimeError):
        finish_ok(writer)


@pytest.mark.parametrize("timeout", [True, float("nan"), float("inf"), -float("inf")])
def test_invalid_finish_timeout_is_rejected_before_closing_writer(tmp_path, timeout):
    writer, root = create(tmp_path)
    with pytest.raises((TypeError, ValueError)):
        writer.finish({"result": "ok"}, timeout_s=timeout)
    assert finish_ok(writer)["event_count"] == 0
    assert (root / "seal.json").is_file()


def test_creation_and_artifact_directory_entries_are_fsynced_in_parent_directories(
        tmp_path, monkeypatch):
    require_writer()
    from so101_demo.act import head_run_evidence as module

    original = module._fsync_directory
    calls = []

    def record_fsync(path):
        calls.append(Path(path))
        return original(path)

    monkeypatch.setattr(module, "_fsync_directory", record_fsync)
    writer, root = create(tmp_path)
    creation_calls = calls[:]
    assert creation_calls.count(tmp_path) >= 1
    assert creation_calls.count(root) >= 1
    writer.add_artifact(b"artifact", media_type="application/octet-stream", suffix="bin")
    finish_ok(writer)
    assert calls.index(root / "artifacts") > calls.index(tmp_path)
    assert calls.count(root) >= 2


def test_dead_worker_finish_is_bounded_and_refuses_to_seal(tmp_path, monkeypatch):
    require_writer()
    from so101_demo.act import head_run_evidence as module

    monkeypatch.setattr(module.threading.Thread, "start", lambda _self: None)
    writer, root = create(tmp_path, capacities={"close_timeout_s": 0.05})
    assert not writer._thread.is_alive()
    start = time.monotonic()
    with pytest.raises(RuntimeError):
        finish_ok(writer)
    assert time.monotonic() - start < 0.2
    assert not (root / "seal.json").exists()


def test_stalled_writer_finish_times_out_without_later_success_seal(tmp_path, monkeypatch):
    require_writer()
    from so101_demo.act import head_run_evidence as module

    entered = threading.Event()
    release = threading.Event()
    faults = []

    def blocked(_self, _item):
        entered.set()
        assert release.wait(2)

    monkeypatch.setattr(module.HeadRunEvidence, "_write_event", blocked)
    writer, root = create(tmp_path, capacities={"close_timeout_s": 0.05}, faults=faults)
    writer.append("EVENT", {}, source_stamp_ns=None, observed_mono_ns=1,
                  occurrence_mono_ns=1)
    assert entered.wait(1)
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="CLOSE_TIMEOUT"):
        finish_ok(writer, timeout_s=0.05)
    assert time.monotonic() - started < 0.2
    assert faults
    release.set()
    writer._thread.join(timeout=1)
    assert not writer._thread.is_alive()
    assert not (root / "seal.json").exists()


@pytest.mark.parametrize("field", ["os_return_code", "exit_code", "returncode", "process_rc"])
def test_completion_cannot_claim_the_actual_process_exit_code(tmp_path, field):
    writer, root = create(tmp_path)
    with pytest.raises(RuntimeError):
        finish_ok(writer, **{field: 0})
    assert not (root / "seal.json").exists()


def test_success_seal_hashes_manifest_events_artifacts_and_completion_but_not_itself(tmp_path):
    writer, root = create(tmp_path)
    writer.append("EVENT", {"n": 1}, source_stamp_ns=None, observed_mono_ns=1,
                  occurrence_mono_ns=1)
    finish_ok(writer, intended_return_code=23)
    seal = json.loads((root / "seal.json").read_text(encoding="utf-8"))
    assert "seal.json" not in {file["path"] for file in seal["files"]}
    for item in seal["files"]:
        content = (root / item["path"]).read_bytes()
        assert len(content) == item["size"]
        assert hashlib.sha256(content).hexdigest() == item["sha256"]
    completion = json.loads((root / "completion.json").read_text(encoding="utf-8"))
    assert completion["intended_return_code"] == 23
    assert "os_return_code" not in completion
    assert seal["event_count"] == 1


def test_finish_is_single_use_and_root_is_immutable_after_seal(tmp_path):
    writer, root = create(tmp_path)
    finish_ok(writer)
    original = (root / "seal.json").read_bytes()
    with pytest.raises(PermissionError):
        writer.append("LATE", {}, source_stamp_ns=None, observed_mono_ns=1,
                      occurrence_mono_ns=1)
    with pytest.raises((PermissionError, RuntimeError)):
        finish_ok(writer)
    assert (root / "seal.json").read_bytes() == original
