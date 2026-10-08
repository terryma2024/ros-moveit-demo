"""Phase B3: one independent readback process recomputes the QC once and its stages decide everything else afresh.

Reviewed design (`2026-10-08-single-fresh-readback.md`, verdict PASS-WITH-CHANGES, CP-3470): the QC *result* is shared between the stages
of a readback entry point under a full-content fingerprint taken before and after the recomputation and at every lookup; the stored
report, the journal, the index, the receipt and every eligibility decision are read afresh; the process never trusts the memo.
"""

import copy
import hashlib
import json
import os
import types
from pathlib import Path

import pytest

from so101_demo.act import episode_qc, qc_memo, qc_session
from so101_demo.act.qc_session import qc_session as session_scope

ENTRY = "readback:readback"


# ---- the report-level reuse key -------------------------------------------------------------------------------------------

def episode_files(tmp_path):
    root = tmp_path / "attempt"
    (root / "episode" / "audit").mkdir(parents=True)
    (root / "episode" / "seal.json").write_bytes(b"seal-0123456789")
    (root / "episode" / "audit" / "events.jsonl").write_bytes(b'{"a":1}\n')
    (root / "scope.json").write_bytes(b"scope")
    (root / "inputs.json").write_bytes(b"inputs")
    return root


def counting(monkeypatch, report=None, during=None):
    calls = []
    document = report or {"status": "PASS", "marker": 1}

    def inner(episode_root, *, scope, inputs_manifest, teacher_manifest=None, topic_loss=None):
        calls.append(1)
        if during is not None:
            during()
        return copy.deepcopy(document)

    monkeypatch.setattr(episode_qc, "_recompute_native_qc", inner)
    return calls


def recompute(root):
    return episode_qc.recompute_native_qc(root / "episode", scope=root / "scope.json", inputs_manifest=root / "inputs.json")


def test_inside_an_entry_session_the_second_recomputation_of_unchanged_files_is_a_hit(tmp_path, monkeypatch):
    root = episode_files(tmp_path)
    calls = counting(monkeypatch)
    with session_scope(owner=ENTRY) as session:
        first, second = recompute(root), recompute(root)
    assert first == second and len(calls) == 1
    assert session.computations["recompute_native_qc"] == 1 and session.qc_hits == 1


def test_outside_an_entry_session_every_call_recomputes(tmp_path, monkeypatch):
    root = episode_files(tmp_path)
    calls = counting(monkeypatch)
    recompute(root), recompute(root)
    with session_scope():                                   # an internal session shares verifiers, never the QC result
        recompute(root), recompute(root)
    assert len(calls) == 4


def test_a_cached_report_is_a_copy(tmp_path, monkeypatch):
    root = episode_files(tmp_path)
    counting(monkeypatch)
    with session_scope(owner=ENTRY):
        first = recompute(root)
        first["status"] = "FAIL"
        assert recompute(root)["status"] == "PASS"


def test_an_in_place_rewrite_of_the_same_size_with_the_mtime_restored_is_not_a_hit(tmp_path, monkeypatch):
    """The stat of the file is unchanged (size, inode, mtime): a stat key would serve the stale result."""
    root = episode_files(tmp_path)
    counting(monkeypatch)
    victim = root / "episode" / "audit" / "events.jsonl"
    with session_scope(owner=ENTRY):
        recompute(root)
        before = victim.stat()
        with open(victim, "r+b") as stream:
            stream.write(b'{"a":2}\n')
        os.utime(victim, ns=(before.st_atime_ns, before.st_mtime_ns))
        after = victim.stat()
        assert (after.st_size, after.st_ino, after.st_mtime_ns) == (before.st_size, before.st_ino, before.st_mtime_ns)
        with pytest.raises(ValueError, match="READBACK_INPUT_CHANGED"):
            recompute(root)


@pytest.mark.parametrize("target", ["episode/seal.json", "scope.json", "inputs.json"])
def test_any_input_changed_between_two_lookups_fails_closed(tmp_path, monkeypatch, target):
    root = episode_files(tmp_path)
    counting(monkeypatch)
    with session_scope(owner=ENTRY):
        recompute(root)
        (root / target).write_bytes(b"changed-bytes!")
        with pytest.raises(ValueError, match="READBACK_INPUT_CHANGED"):
            recompute(root)


def test_a_file_changed_during_the_recomputation_fails_closed_and_is_not_kept(tmp_path, monkeypatch):
    root = episode_files(tmp_path)
    calls = counting(monkeypatch, during=lambda: (root / "episode" / "seal.json").write_bytes(b"seal-changed!!!"))
    with session_scope(owner=ENTRY) as session:
        with pytest.raises(ValueError, match="READBACK_INPUT_CHANGED"):
            recompute(root)
        assert session.qc_results == {} and len(calls) == 1


def test_a_failed_recomputation_is_not_remembered(tmp_path, monkeypatch):
    root = episode_files(tmp_path)
    state = {"n": 0}

    def inner(episode_root, **kwargs):
        state["n"] += 1
        raise ValueError("NATIVE_QC_BROKEN")

    monkeypatch.setattr(episode_qc, "_recompute_native_qc", inner)
    with session_scope(owner=ENTRY):
        for _ in range(2):
            with pytest.raises(ValueError, match="NATIVE_QC_BROKEN"):
                recompute(root)
    assert state["n"] == 2


def test_the_reuse_key_includes_the_code_digest(tmp_path, monkeypatch):
    root = episode_files(tmp_path)
    calls = counting(monkeypatch)
    with session_scope(owner=ENTRY):
        recompute(root)
        monkeypatch.setattr(qc_memo, "code_digest", lambda: "0" * 64)
        recompute(root)
    assert len(calls) == 2


def test_the_fingerprint_without_the_memo_cache_hashes_every_byte_each_time(tmp_path):
    root = episode_files(tmp_path)
    arguments = dict(episode_root=root / "episode", scope=root / "scope.json", inputs_manifest=root / "inputs.json")
    one = qc_memo.fingerprint(**arguments, use_cache=False)
    victim = root / "episode" / "audit" / "events.jsonl"
    before = victim.stat()
    victim.write_bytes(b'{"a":9}\n')
    os.utime(victim, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert qc_memo.fingerprint(**arguments, use_cache=False) != one
    assert not qc_memo._CACHE, "the readback fingerprint leaves nothing in the memo's cache"


# ---- the readback never trusts the memo ---------------------------------------------------------------------------------------

def test_the_guard_refuses_a_process_that_holds_memo_state(tmp_path, monkeypatch):
    monkeypatch.setitem(qc_memo._CACHE, ("x",), ("sig", "fp"))
    with pytest.raises(qc_memo.ReadbackMemoForbidden, match="READBACK_MEMO_STATE_PRESENT"):
        with qc_memo.readback_guard():
            pass


def test_the_guard_refuses_a_process_that_built_a_trusting_gate(monkeypatch):
    from so101_demo.act.result_store import ActCollectionResultVerifier

    ActCollectionResultVerifier({}, trust_fresh_qc_memo=True)
    with pytest.raises(qc_memo.ReadbackMemoForbidden, match="READBACK_MEMO_TRUSTING_GATE_BUILT"):
        with qc_memo.readback_guard():
            pass


def test_inside_the_guard_a_trusting_store_or_verifier_cannot_be_built(tmp_path):
    from so101_demo.act.result_store import ActCollectionResultVerifier

    with qc_memo.readback_guard():
        ActCollectionResultVerifier({})                                   # a plain verifier is fine
        with pytest.raises(qc_memo.ReadbackMemoForbidden, match="READBACK_MEMO_TRUST_FORBIDDEN"):
            ActCollectionResultVerifier({}, trust_fresh_qc_memo=True)
        flipped = ActCollectionResultVerifier({})
        flipped.TRUST_FRESH_QC_MEMO = True                                # flipped after construction: refused at the first use
        with pytest.raises(qc_memo.ReadbackMemoForbidden):
            flipped.verify(None, "x", None)


def test_inside_the_guard_the_memo_cannot_be_read_written_or_fingerprinted(tmp_path):
    root = episode_files(tmp_path)
    with qc_memo.readback_guard():
        with pytest.raises(qc_memo.ReadbackMemoForbidden):
            qc_memo.memo_matches(root / "qc-report.json", {"status": "PASS", "rule_version": episode_qc.QC_RULE_VERSION},
                                 episode_root=root / "episode", scope=root / "scope.json", inputs_manifest=root / "inputs.json")
        with pytest.raises(qc_memo.ReadbackMemoForbidden):
            qc_memo.write_memo(root / "qc-report.json", {"status": "PASS"}, episode_root=root / "episode",
                               scope=root / "scope.json", inputs_manifest=root / "inputs.json")
        with pytest.raises(qc_memo.ReadbackMemoForbidden):
            qc_memo.fingerprint(episode_root=root / "episode", scope=root / "scope.json", inputs_manifest=root / "inputs.json")
        qc_memo.fingerprint(episode_root=root / "episode", scope=root / "scope.json", inputs_manifest=root / "inputs.json",
                            use_cache=False)


# ---- the export path ---------------------------------------------------------------------------------------------------------

def test_a_session_that_is_not_a_readback_entry_point_fires_the_export_guard():
    from so101_demo.act import bundle

    for owner in ("internal", "bundle", "training"):
        with session_scope(owner=owner):
            with pytest.raises(ValueError, match="QC_SESSION_IN_EXPORT_PATH"):
                bundle.resolve_committed_episodes(manifest={"episodes": []}, campaign_index="x")
            with pytest.raises(ValueError, match="QC_SESSION_IN_EXPORT_PATH"):
                bundle.export_dataset((), "out", source_manifest_sha256="a" * 64, campaign_index_sha256="b" * 64)
    with session_scope(owner="readback:check-export"):
        with pytest.raises(ValueError, match="MANIFEST_INVALID"):          # the guard lets the entry point through; the checks still run
            bundle.resolve_committed_episodes(manifest={}, campaign_index="x")


def formal_episode(tmp_path):
    root = tmp_path / "run"
    evidence = {"coordinator_root": str(root / "coordinator"), "result_location": str(root / "sealed"),
                "scope_path": str(root / "scope.json"), "inputs_manifest": str(root / "inputs.json"), "receipt": {"r": 1}}
    for name in ("coordinator", "sealed"):
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / "scope.json").write_text("{}")
    (root / "inputs.json").write_text("{}")
    return dict(kind="ACT_COMMITTED_EPISODE", schema_version=2, scene_id="scene", status="PASSED", split="train",
                journal_sha256="a" * 64, verifier_sha256="b" * 64, collection_evidence=evidence)


@pytest.mark.parametrize("change,code", [
    ({}, None),
    ({"result_status": "FAILED"}, "EXPORT_EPISODE_NOT_PASSED"),
    ({"act_data_qc": "FAIL"}, "EXPORT_EPISODE_DATA_QC_NOT_PASSED"),
    ({"export_eligible": False}, "EXPORT_EPISODE_DATA_QC_NOT_PASSED"),
    ({"result_schema_version": 2}, "EXPORT_EPISODE_LEGACY_RESULT"),
    ({"status": "FAIL"}, "EXPORT_EPISODE_LEGACY_RESULT")])
def test_a_formal_export_inside_an_entry_session_still_decides_status_qc_and_eligibility_afresh(tmp_path, monkeypatch, change, code):
    from so101_demo.act import bundle, collection_scope, result_store

    episode = formal_episode(tmp_path)
    proof = dict(commit_frame_sha256="a" * 64, result_sha256="b" * 64, receipt={"r": 1}, collection_mode="formal", status="PASS",
                 result_schema_version=3, result_status="PASSED", act_data_qc="PASS", export_eligible=True)
    proof.update(change)
    monkeypatch.setattr(result_store, "verify_coordinator_commit", lambda *a, **k: dict(proof))
    monkeypatch.setattr(collection_scope, "read_collection_scope", lambda path: {"scene_id": "scene", "mode": "formal"})
    with session_scope(owner="readback:check-export"):
        if code is None:
            assert bundle._verify_collection_for_export(episode) == "formal"
        else:
            with pytest.raises(ValueError, match=code):
                bundle._verify_collection_for_export(episode)


# ---- the command: parity with the standalone commands, one recomputation, no run-side receipt ----------------------------------

def committed_run(tmp_path, monkeypatch, fault=None):
    """The controlled committed result of the existing tests, with the QC double moved to the inner function so the real public wrapper
    (and with it the reuse) is exercised. Returns (run, context, counter)."""
    from so101_demo.act import result_store
    from test_act_result_qc_v2 import controlled_committed_result, copied_commit_fixture

    public = episode_qc.recompute_native_qc
    run, location, scope, inputs, receipt = controlled_committed_result(tmp_path, monkeypatch)
    stored = episode_qc.read_qc_report(location / "qc-report.json")
    monkeypatch.setattr(episode_qc, "recompute_native_qc", public)
    calls = []
    monkeypatch.setattr(episode_qc, "_recompute_native_qc", lambda *a, **k: (calls.append(1), copy.deepcopy(stored))[1])
    if fault == "missing_commit":
        copied = tmp_path / "uncommitted"
        copied_commit_fixture(run, copied, fault="missing_commit")
        location, run = copied / location.relative_to(run), copied
    context = dict(episode=location / "episode", location=location, scope=scope, inputs_manifest=inputs,
                   coordinator_root=run / "coordinator")
    monkeypatch.setattr(result_store, "resolve_native_run", lambda root: context)
    return run, context, calls


def standalone(command, run, output):
    from so101_demo.cli import act_first_episode

    return act_first_episode.main([command, "--run", str(run.parent), "--output", str(output)])


@pytest.mark.parametrize("fault", [None, "missing_commit"])
def test_readback_gives_the_bytes_and_exit_codes_of_the_three_standalone_commands(tmp_path, monkeypatch, fault):
    from so101_demo.cli import act_first_episode

    run, context, calls = committed_run(tmp_path, monkeypatch, fault)
    alone = tmp_path / "alone"
    alone.mkdir()
    codes = {name: standalone(name, run, alone / f"{name}.json") for name in ("qc", "verify-commit", "check-export")}
    standalone_calls = len(calls)
    del calls[:]
    together = tmp_path / "together"
    rc = act_first_episode.main(["readback", "--run", str(run.parent), "--output-dir", str(together)])
    receipt = json.loads((together / "readback-receipt.json").read_bytes())
    for name, code in codes.items():
        stage = receipt["stages"][name]
        assert stage["rc"] == code, name
        assert (together / f"{name}.json").is_file() == (alone / f"{name}.json").is_file()
        if (alone / f"{name}.json").is_file():
            assert (together / f"{name}.json").read_bytes() == (alone / f"{name}.json").read_bytes(), name
    assert rc == next((code for code in codes.values() if code), 0)
    assert len(calls) <= 1, "one recomputation for the whole readback"
    assert standalone_calls >= (0 if fault else 3), "the standalone commands recompute once each"


def test_check_export_recomputes_the_qc_once_not_three_times(tmp_path, monkeypatch):
    run, context, calls = committed_run(tmp_path, monkeypatch)
    assert standalone("check-export", run, tmp_path / "export.json") == 0
    assert len(calls) == 1


def test_readback_writes_one_receipt_that_binds_the_three_digests_the_fingerprint_and_the_process(tmp_path, monkeypatch):
    from so101_demo.cli import act_first_episode

    run, context, calls = committed_run(tmp_path, monkeypatch)
    out = tmp_path / "readback"
    rc = act_first_episode.main(["readback", "--run", str(run.parent), "--output-dir", str(out)])
    receipt = json.loads((out / "readback-receipt.json").read_bytes())
    assert len(calls) == 1 and receipt["qc_recomputations"] == 1 and receipt["pid"] == os.getpid()
    digests = receipt["qc_report_sha256"]
    assert digests["agree"] is True and digests["recomputed"] == digests["stored"] == digests["commit_proof"]
    assert digests["stored"] == hashlib.sha256((context["location"] / "qc-report.json").read_bytes()).hexdigest()
    proof = json.loads((out / "verify-commit.json").read_bytes())
    assert receipt["journal_terminal_sha256"] == proof["journal_terminal_sha256"]
    assert receipt["code_digest"] == qc_memo.code_digest() and len(receipt["input_fingerprint"]) == 64
    assert receipt["stages"]["qc"]["rc"] == 3 and receipt["stages"]["verify-commit"]["rc"] == 0, "a QC FAIL does not stop the commit proof"
    assert receipt["stages"]["check-export"]["status"] == "PASS" and rc == 3 and receipt["status"] == "PASS"
    assert act_first_episode.main(["readback", "--run", str(run.parent), "--output-dir", str(out)]) == 4, "an existing output directory is never reused"


def test_a_run_that_is_not_a_diagnostic_has_no_export_check_stage(tmp_path, monkeypatch):
    from so101_demo.cli import act_first_episode

    run, context, calls = committed_run(tmp_path, monkeypatch)
    monkeypatch.setattr(act_first_episode, "_run_mode", lambda context: "formal")
    monkeypatch.setattr(act_first_episode, "_check_export", lambda arguments: pytest.fail("a formal run has no refusal check"))
    out = tmp_path / "readback"
    act_first_episode.main(["readback", "--run", str(run.parent), "--output-dir", str(out)])
    stage = json.loads((out / "readback-receipt.json").read_bytes())["stages"]["check-export"]
    assert stage["status"] == "NOT_APPLICABLE" and stage["rc"] == 0 and stage["reason"].startswith("DIAGNOSTIC_EXPORT_CHECK_MODE_REQUIRED")
    assert not (out / "check-export.json").exists()


def test_a_receipt_with_two_recomputations_fails_its_own_stage_check(tmp_path, monkeypatch):
    from so101_demo.cli import act_first_episode

    run, context, calls = committed_run(tmp_path, monkeypatch)
    inner = episode_qc._recompute_native_qc
    monkeypatch.setattr(episode_qc, "_recompute_for_readback",
                        lambda session, root, **kw: (session.note("recompute_native_qc"), inner(root, **kw))[1])   # no reuse
    out = tmp_path / "readback"
    rc = act_first_episode.main(["readback", "--run", str(run.parent), "--output-dir", str(out)])
    receipt = json.loads((out / "readback-receipt.json").read_bytes())
    assert receipt["status"] == "FAIL" and any(item.startswith("READBACK_RECOMPUTE_COUNT") for item in receipt["failures"])


def test_the_readback_never_opens_the_memo_even_when_a_matching_one_is_present(tmp_path, monkeypatch):
    from so101_demo.cli import act_first_episode

    run, context, calls = committed_run(tmp_path, monkeypatch)
    memo = context["location"] / qc_memo.MEMO_NAME
    stored = (context["location"] / "qc-report.json")
    memo.write_text(json.dumps({"kind": qc_memo.MEMO_KIND, "report_sha256": "0" * 64}))
    opened = []
    real_open = os.open
    monkeypatch.setattr(os, "open", lambda path, *a, **k: (opened.append(str(path)), real_open(path, *a, **k))[1])
    out = tmp_path / "readback"
    act_first_episode.main(["readback", "--run", str(run.parent), "--output-dir", str(out)])
    assert not [path for path in opened if path.endswith(qc_memo.MEMO_NAME)]
    assert len(calls) == 1, "the QC was recomputed in this process"


def test_a_process_with_a_filled_memo_cache_or_a_trusting_gate_is_refused_by_every_entry_point(tmp_path, monkeypatch, capsys):
    from so101_demo.cli import act_first_episode

    run, context, calls = committed_run(tmp_path, monkeypatch)
    monkeypatch.setitem(qc_memo._CACHE, ("leak",), ("sig", "fp"))
    for name in ("qc", "verify-commit", "check-export"):
        assert standalone(name, run, tmp_path / f"{name}.json") == 4
    assert act_first_episode.main(["readback", "--run", str(run.parent), "--output-dir", str(tmp_path / "rb")]) == 4
    assert calls == [] and "READBACK_MEMO_STATE_PRESENT" in capsys.readouterr().err
    qc_memo._CACHE.clear()
    from so101_demo.act.result_store import ActCollectionResultVerifier
    ActCollectionResultVerifier({}, trust_fresh_qc_memo=True)
    assert standalone("qc", run, tmp_path / "again.json") == 4


def test_the_run_command_writes_the_commit_proof_only(tmp_path, monkeypatch):
    """The run process builds memo-trusting gates (the Coordinator's), so it is not an independent readback: no receipt, no export check."""
    from so101_demo.act import result_store
    from so101_demo.cli import act_first_episode
    from test_act_result_qc_v2 import controlled_committed_result

    run, location, scope, inputs, _ = controlled_committed_result(tmp_path, monkeypatch, completed=True, teacher_outcome="PASSED")
    context = dict(episode=location / "episode", location=location, scope=scope, inputs_manifest=inputs,
                   coordinator_root=run / "coordinator")
    monkeypatch.setattr(result_store, "resolve_native_run", lambda root: context)
    monkeypatch.setattr(act_first_episode, "_check_export", lambda arguments: pytest.fail("the run does not check the export"))
    monkeypatch.setattr(act_first_episode, "_readback", lambda *a, **k: pytest.fail("the run does not read back"))
    root = run.parent
    code, report = act_first_episode._verified_run_completion(root)
    assert code == 3 and (root / "commit-proof.json").is_file()
    assert not (root / act_first_episode.READBACK_RECEIPT).exists() and not list(root.glob("check-export*"))
    assert not list(root.glob("qc*.json")) and not list(root.glob("verify-commit*"))
