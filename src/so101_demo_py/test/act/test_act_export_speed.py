"""Export speed-ups (to-do 12): QC memo trust, one syncfs instead of per-file fsync, threaded writes, one read per frame.

Fixture-only: the trees are built under tmp_path; nothing reads the host's evidence or datasets.
"""
import os
from pathlib import Path

import pytest

from so101_demo.act import bundle
from so101_demo.act.bundle import clear_verification_memo, export_dataset, resolve_committed_episodes
from so101_demo.act.training import attach_episode_content
from act_export_fixture import complete_export_entries
from test_act_bundle_parallel import DIGESTS, MANIFEST, fork_pool, tree_bytes, workspace  # noqa: F401
from test_act_export_frames import _rows, _sealed

KW = dict(source_manifest_sha256="a" * 64, campaign_index_sha256="b" * 64)


def record_readbacks(monkeypatch):
    """Wrap the processed readback; every call appends the keyword arguments that mattered (in-process only)."""
    from so101_demo.act import processed_result
    seen = []
    inner = processed_result.verify_processed_result

    def wrapped(output, **kwargs):
        seen.append(kwargs.get("trust_memo", False))
        return inner(output, **kwargs)
    monkeypatch.setattr(processed_result, "verify_processed_result", wrapped)
    return seen


def test_the_qc_memo_is_trusted_only_when_the_caller_asks(tmp_path, monkeypatch):
    entries, _ = workspace(tmp_path, monkeypatch, scenes=("001",))
    seen = record_readbacks(monkeypatch)
    bundle._verified_collection(entries[0])
    clear_verification_memo()
    bundle._verified_collection(entries[0], True)
    assert seen == [False, True]


def test_a_pass_that_trusted_the_memo_never_answers_a_caller_that_did_not(tmp_path, monkeypatch):
    entries, _ = workspace(tmp_path, monkeypatch, scenes=("001",))
    seen = record_readbacks(monkeypatch)
    bundle._verified_collection(entries[0], True)
    bundle._verified_collection(entries[0], True)           # a hit
    assert seen == [True]
    bundle._verified_collection(entries[0])                 # full recomputation, and it replaces the entry
    assert seen == [True, False]
    bundle._verified_collection(entries[0], True)           # a full pass answers a trusting caller too
    bundle._verified_collection(entries[0])
    assert seen == [True, False]


def test_the_whole_pre_training_pipeline_trusts_the_memo_once_per_episode(tmp_path, monkeypatch):
    entries, index = workspace(tmp_path, monkeypatch)
    seen = record_readbacks(monkeypatch)
    resolved = resolve_committed_episodes(manifest=MANIFEST, campaign_index=index, trust_qc_memo=True)
    export_dataset(attach_episode_content(resolved, root=tmp_path, trust_qc_memo=True), tmp_path / "dataset",
                   trust_qc_memo=True, **DIGESTS)
    assert seen == [True] * 4


def test_the_default_still_recomputes_in_full(tmp_path, monkeypatch):
    entries, index = workspace(tmp_path, monkeypatch)
    seen = record_readbacks(monkeypatch)
    resolved = resolve_committed_episodes(manifest=MANIFEST, campaign_index=index)
    export_dataset(attach_episode_content(resolved, root=tmp_path), tmp_path / "dataset", **DIGESTS)
    assert seen == [False] * 4


def test_the_pool_primes_the_memo_with_the_trust_flag(tmp_path, monkeypatch, fork_pool):
    entries, index = workspace(tmp_path, monkeypatch)
    resolved = resolve_committed_episodes(manifest=MANIFEST, campaign_index=index, workers=3, trust_qc_memo=True)
    assert [held[3] for held in bundle._VERIFICATION_MEMO.values()] == [True] * 4
    seen = record_readbacks(monkeypatch)
    attach_episode_content(resolved, root=tmp_path, workers=3, trust_qc_memo=True)
    assert seen == []                       # the pool's trusted passes are memo hits for a trusting caller
    attach_episode_content(resolved, root=tmp_path, workers=3)                       # an untrusting caller verifies again, in the pool
    assert [held[3] for held in bundle._VERIFICATION_MEMO.values()] == [False] * 4


def test_a_frame_is_read_once_on_the_happy_path(tmp_path, monkeypatch):
    entries = complete_export_entries(tmp_path, monkeypatch, content=_rows(3))
    reads, checks = [], []
    inner = bundle._read_frame
    monkeypatch.setattr(bundle, "_read_frame", lambda path, digest: (reads.append(path), inner(path, digest))[1])
    monkeypatch.setattr(bundle, "_file_sha256", lambda *a, **k: checks.append(a) or pytest.fail("a separate frame hash pass ran"))
    document = export_dataset(entries, tmp_path / "dataset", **KW)
    assert len(reads) == sum(len(item["frames"]) for item in document["episodes"]) == 12 and not checks


@pytest.mark.parametrize("workers", [1, 4])
def test_threads_write_the_same_bytes_as_the_serial_path(tmp_path, monkeypatch, fork_pool, workers):
    entries = complete_export_entries(tmp_path, monkeypatch, scene_ids=("act-1", "act-2", "act-3"), content=_rows(3))
    serial = export_dataset(entries, tmp_path / "serial", workers=1, **KW)
    threaded = export_dataset(entries, tmp_path / "threaded", workers=workers, **KW)
    assert tree_bytes(tmp_path / "serial") == tree_bytes(tmp_path / "threaded")
    assert serial["export_sha256"] == threaded["export_sha256"]


def test_the_first_refusal_in_manifest_order_wins_whatever_thread_met_it_first(tmp_path, monkeypatch, fork_pool):
    entries = complete_export_entries(tmp_path, monkeypatch, scene_ids=("act-1", "act-2", "act-3", "act-4"), content=_rows(3))
    (_sealed(tmp_path, entries[1]) / "frames" / "000001-head.png").write_bytes(b"changed")       # act-2: digest mismatch
    (_sealed(tmp_path, entries[2]) / "frames" / "000000-wrist.png").unlink()                       # act-3: missing
    for _ in range(5):
        with pytest.raises(ValueError, match="EXPORT_EPISODE_FRAME_DIGEST_MISMATCH"):
            export_dataset(entries, tmp_path / "dataset", workers=4, **KW)
        assert not (tmp_path / "dataset").exists() and not (tmp_path / "dataset.partial").exists()


def test_an_earlier_episode_with_a_bad_frame_beats_a_later_refused_record(tmp_path, monkeypatch):
    entries = complete_export_entries(tmp_path, monkeypatch, content=_rows(2))
    (_sealed(tmp_path, entries[0]) / "frames" / "000000-head.png").write_bytes(b"changed")
    entries[1]["status"] = "FAILED"                                      # EXPORT_EPISODE_NOT_PASSED at the second record
    with pytest.raises(ValueError, match="EXPORT_EPISODE_FRAME_DIGEST_MISMATCH"):
        export_dataset(entries, tmp_path / "dataset", **KW)


def test_one_syncfs_runs_after_every_file_is_written_and_before_the_rename(tmp_path, monkeypatch):
    if os.uname().sysname != "Linux":
        pytest.skip("syncfs(2) is Linux only; the fallback is tested below")
    entries = complete_export_entries(tmp_path, monkeypatch, content=_rows(3))
    calls, fsyncs = [], []
    inner = bundle._syncfs

    def spy(path):
        path = Path(path)
        names = {str(item.relative_to(path)) for item in path.rglob("*") if item.is_file()}
        calls.append((path.name, (tmp_path / "dataset").exists(), "export-manifest.json" in names, len(names)))
        return inner(path)
    monkeypatch.setattr(bundle, "_syncfs", spy)
    monkeypatch.setattr(os, "fsync", lambda fd: fsyncs.append(fd))
    export_dataset(entries, tmp_path / "dataset", workers=2, **KW)
    assert calls == [("dataset.partial", False, True, 2 + 12 + 1)] and fsyncs == []


def test_without_syncfs_every_file_is_fsynced_as_before(tmp_path, monkeypatch):
    entries = complete_export_entries(tmp_path, monkeypatch, content=_rows(3))
    fsyncs = []
    real = os.fsync
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr(bundle, "_syncfs", lambda path: pytest.fail("syncfs on a platform without it"))
    monkeypatch.setattr(os, "fsync", lambda fd: (fsyncs.append(fd), real(fd))[1])
    export_dataset(entries, tmp_path / "dataset", **KW)
    assert len(fsyncs) == 2 + 12 + 1


def test_a_libc_without_syncfs_falls_back_to_the_global_sync(tmp_path, monkeypatch):
    entries = complete_export_entries(tmp_path, monkeypatch, content=_rows(1))
    synced = []
    monkeypatch.setattr(bundle, "_syncfs", lambda path: False)
    monkeypatch.setattr(os, "sync", lambda: synced.append(1))
    monkeypatch.setattr("platform.system", lambda: "Linux")
    export_dataset(entries, tmp_path / "dataset", **KW)
    assert synced == [1]
