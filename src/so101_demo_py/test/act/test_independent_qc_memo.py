"""CP-3456: the content-bound memo of the independent fresh-process QC.

The full QC recomputation of a 100 s episode (seal, physical audit, native QC) takes about five minutes. The Coordinator's result gate
runs it twice under its state lock, the Worker's ResultStore once more, and the Coordinator's result acknowledgement has ten seconds.
The offline processor's fresh-process QC has just done exactly that recomputation on exactly those files, so the run path may rely on
a memo of it that is bound to the content: every episode file, the scope, the frozen inputs and the Teacher manifest, plus the QC
rule version and the report. Anything else (a changed byte, a missing memo, another report) recomputes in full. The read-only
readback (`verify_coordinator_commit`, `act_diagnostic_episode qc`, `verify-commit`) never trusts the memo.
"""

import copy
import json
import os
from pathlib import Path

import pytest

from so101_demo.act import episode_qc, qc_memo


def episode(tmp_path):
    root = tmp_path / "working" / "episode"
    (root / "audit").mkdir(parents=True)
    (root / "frames").mkdir()
    (root / "seal.json").write_text('{"status": "PASSED", "attempt_id": "a", "session_id": "s", "reset_epoch": 1}')
    (root / "audit" / "events.jsonl").write_text('{"x": 1}\n')
    (root / "frames" / "000001-head.png").write_bytes(b"png")
    scope = tmp_path / "scope.json"
    scope.write_text("{}")
    inputs = tmp_path / "inputs-manifest.json"
    inputs.write_text('{"inputs_sha256": "' + "a" * 64 + '"}')
    teacher = tmp_path / "working" / "dynamic" / "dynamic-execute-manifest.json"
    teacher.parent.mkdir()
    teacher.write_text('{"teacher": 1}')
    report = {"kind": "ACT_EPISODE_QC", "schema_version": 3, "rule_version": episode_qc.QC_RULE_VERSION, "status": "PASS",
              "reason": "", "counts": {"records": 3}}
    return root, scope, inputs, teacher, report, tmp_path / "working" / "qc-report.json"


def paths(root, scope, inputs, teacher):
    return dict(episode_root=root, scope=scope, inputs_manifest=inputs, teacher_manifest=teacher)


def test_a_memo_written_for_a_passing_report_is_recognised_for_the_same_content(tmp_path):
    root, scope, inputs, teacher, report, report_path = episode(tmp_path)
    memo = qc_memo.write_memo(report_path, report, **paths(root, scope, inputs, teacher))
    assert memo == report_path.with_name(qc_memo.MEMO_NAME) and memo.is_file()
    assert qc_memo.memo_matches(report_path, report, **paths(root, scope, inputs, teacher)) is True
    # the Teacher manifest may be left to its conventional place beside the episode
    assert qc_memo.memo_matches(report_path, report, **paths(root, scope, inputs, None)) is True


@pytest.mark.parametrize("change", [
    "episode_file_byte", "episode_file_added", "episode_file_removed", "scope", "inputs", "teacher", "teacher_removed", "report",
    "report_status", "rule_version", "memo_missing", "memo_garbage", "memo_other_fingerprint", "symlink_in_episode"])
def test_any_other_content_recomputes_in_full(tmp_path, change):
    root, scope, inputs, teacher, report, report_path = episode(tmp_path)
    memo = qc_memo.write_memo(report_path, report, **paths(root, scope, inputs, teacher))
    asked = copy.deepcopy(report)
    if change == "episode_file_byte":
        (root / "audit" / "events.jsonl").write_text('{"x": 2}\n')
    if change == "episode_file_added":
        (root / "audit" / "extra.jsonl").write_text("")
    if change == "episode_file_removed":
        (root / "frames" / "000001-head.png").unlink()
    if change == "scope":
        scope.write_text('{"mode": "other"}')
    if change == "inputs":
        inputs.write_text("{}")
    if change == "teacher":
        teacher.write_text('{"teacher": 2}')
    if change == "teacher_removed":
        teacher.unlink()
    if change == "report":
        asked["counts"]["records"] = 4
    if change == "report_status":
        asked["status"] = "FAIL"
    if change == "rule_version":
        asked["rule_version"] = "act_data_qc_retired"
    if change == "memo_missing":
        memo.unlink()
    if change == "memo_garbage":
        memo.write_text("not json")
    if change == "memo_other_fingerprint":
        document = json.loads(memo.read_text())
        document["fingerprint"] = "0" * 64
        memo.write_text(json.dumps(document))
    if change == "symlink_in_episode":
        os.symlink(root / "seal.json", root / "link.json")
    assert qc_memo.memo_matches(report_path, asked, **paths(root, scope, inputs, teacher)) is False


def test_only_a_passing_report_gets_a_memo(tmp_path):
    root, scope, inputs, teacher, report, report_path = episode(tmp_path)
    report["status"] = "FAIL"
    with pytest.raises(ValueError, match="QC_MEMO_REQUIRES_PASS"):
        qc_memo.write_memo(report_path, report, **paths(root, scope, inputs, teacher))
    assert not report_path.with_name(qc_memo.MEMO_NAME).exists()


def test_the_fingerprint_is_cached_per_process_only_while_every_file_is_unchanged(tmp_path, monkeypatch):
    root, scope, inputs, teacher, report, report_path = episode(tmp_path)
    first = qc_memo.fingerprint(**paths(root, scope, inputs, teacher))
    calls = []
    real = qc_memo._file_digest
    monkeypatch.setattr(qc_memo, "_file_digest", lambda path: calls.append(path) or real(path))
    assert qc_memo.fingerprint(**paths(root, scope, inputs, teacher)) == first and calls == [], "second call hashed nothing"
    (root / "audit" / "events.jsonl").write_text('{"x": 22}\n')   # same-size change is a different mtime/inode content
    assert qc_memo.fingerprint(**paths(root, scope, inputs, teacher)) != first and calls


# ---- where the memo is written and where it is trusted -------------------------------------------------------------------------

def test_the_fresh_process_qc_writes_the_memo_beside_a_passing_report_and_not_beside_a_failing_one(tmp_path, monkeypatch):
    from so101_demo.act.offline import independent_qc

    root, scope, inputs, teacher, report, report_path = episode(tmp_path)
    monkeypatch.setattr(episode_qc, "recompute_native_qc", lambda *args, **kwargs: copy.deepcopy(report))
    monkeypatch.setattr(episode_qc, "write_qc_report", lambda document, output: Path(output).write_bytes(episode_qc._report_canonical(document)) or "sha")
    arguments = ["--episode", str(root), "--scope", str(scope), "--inputs-manifest", str(inputs), "--teacher-manifest", str(teacher),
                 "--output", str(report_path)]
    assert independent_qc.main(arguments) == 0
    assert qc_memo.memo_matches(report_path, report, **paths(root, scope, inputs, teacher)) is True
    failing = copy.deepcopy(report)
    failing["status"] = "FAIL"
    report_path.with_name(qc_memo.MEMO_NAME).unlink()
    monkeypatch.setattr(episode_qc, "recompute_native_qc", lambda *args, **kwargs: copy.deepcopy(failing))
    assert independent_qc.main(arguments) == 1
    assert not report_path.with_name(qc_memo.MEMO_NAME).exists()


def _trusting(monkeypatch):
    from so101_demo.act import result_store

    monkeypatch.setattr(result_store.ActCollectionResultVerifier, "TRUST_INDEPENDENT_QC_MEMO", True)
    monkeypatch.setattr(result_store.ActCollectionResultStore, "TRUST_INDEPENDENT_QC_MEMO", True)


def test_the_result_gates_trust_the_memo_only_when_asked_and_the_readback_never_does(monkeypatch):
    from so101_demo.act import result_store

    assert result_store.ActCollectionResultVerifier.TRUST_INDEPENDENT_QC_MEMO is False
    assert result_store.ActCollectionResultStore.TRUST_INDEPENDENT_QC_MEMO is False
    # the readback builds its verifier without the option: it recomputes in full
    import inspect

    source = inspect.getsource(result_store.verify_coordinator_commit)
    assert "trust_independent_qc_memo" not in source and "TRUST_INDEPENDENT_QC_MEMO" not in source


def test_the_production_composition_asks_for_the_memo_in_both_gates():
    import inspect

    from so101_demo.cli import mujoco_parallel_batch

    source = inspect.getsource(mujoco_parallel_batch)
    assert source.count("trust_independent_qc_memo=True") == 2


def test_a_valid_memo_skips_the_recomputation_in_the_result_qc_readback_and_a_missing_one_does_not(tmp_path, monkeypatch):
    """`_verify_result_qc` with a real (tiny) episode would need the whole audit; the recomputation is the only expensive step and is
    observed through its reader, with every cheap binding check done on real files."""
    from so101_demo.act import result_store

    root, scope, inputs, teacher, report, report_path = episode(tmp_path)
    calls = []
    monkeypatch.setattr(episode_qc, "recompute_native_qc", lambda *args, **kwargs: calls.append(kwargs) or copy.deepcopy(report))
    assert result_store._recomputed_or_memoised(report_path, report, episode_root=root, scope=scope, inputs_manifest=inputs,
                                                trust_memo=True, reader=episode_qc.recompute_native_qc) == report
    assert len(calls) == 1, "no memo yet: recomputed"
    qc_memo.write_memo(report_path, report, **paths(root, scope, inputs, teacher))
    calls.clear()
    assert result_store._recomputed_or_memoised(report_path, report, episode_root=root, scope=scope, inputs_manifest=inputs,
                                                trust_memo=True, reader=episode_qc.recompute_native_qc) == report
    assert calls == [], "a valid memo: not recomputed"
    assert result_store._recomputed_or_memoised(report_path, report, episode_root=root, scope=scope, inputs_manifest=inputs,
                                                trust_memo=False, reader=episode_qc.recompute_native_qc) == report
    assert len(calls) == 1, "the readback never trusts the memo"


# ---- the two result gates, on a real sealed result ----------------------------------------------------------------------------

def _tripwires(monkeypatch, *, memo_covers):
    from so101_demo.act import result_store

    def tripwire(*args, **kwargs):
        pytest.fail("a verification the memo covers was repeated")

    monkeypatch.setattr(result_store, "_qc_memo_covers", lambda *args, **kwargs: memo_covers)
    monkeypatch.setattr(qc_memo, "memo_matches", lambda *args, **kwargs: memo_covers)
    calls = []
    real_seal = result_store.verify_episode_seal
    monkeypatch.setattr(result_store, "verify_episode_seal", lambda *a, **k: calls.append("seal") or real_seal(*a, **k))
    return calls, tripwire


def test_the_coordinators_gate_skips_the_covered_verifications_only_when_it_trusts_a_covering_memo(tmp_path, monkeypatch):
    from test_act_result_schema3 import _verifier, sealed_teacher, setup_result
    from so101_demo.parallel_batch.contracts import RunMode
    from test_act_result_qc import lease

    store, seal, document, inputs = setup_result(tmp_path, monkeypatch)
    location = store.seal(seal, teacher=sealed_teacher(store, "PASSED"))
    for trusts, covers, expected_seal_reads in ((False, True, 1), (True, False, 1), (True, True, 0)):
        calls, tripwire = _tripwires(monkeypatch, memo_covers=covers)
        verifier = _verifier(tmp_path, location, inputs)
        verifier.TRUST_INDEPENDENT_QC_MEMO = trusts
        recomputed = []
        monkeypatch.setattr(episode_qc, "recompute_native_qc", lambda *a, **k: recomputed.append(1) or copy.deepcopy(document))
        assert verifier.verify(lease(), str(location), RunMode.EXECUTE)["status"] == "PASSED"
        assert len(calls) == expected_seal_reads, (trusts, covers)
        assert len(recomputed) == (0 if trusts and covers else 1), (trusts, covers)


def test_the_stores_gate_skips_the_covered_verifications_only_when_it_trusts_a_covering_memo(tmp_path, monkeypatch):
    from test_act_result_schema3 import sealed_teacher, setup_result

    for trusts, covers, expected_seal_reads in ((False, True, 1), (True, False, 1), (True, True, 0)):
        scratch = tmp_path / f"{trusts}-{covers}"
        scratch.mkdir()
        store, seal, document, inputs = setup_result(scratch, monkeypatch)
        store.TRUST_INDEPENDENT_QC_MEMO = trusts
        report_path = store.working / "qc-report.json"
        episode_qc.write_qc_report(document, report_path)
        calls, tripwire = _tripwires(monkeypatch, memo_covers=covers)
        recomputed = []
        monkeypatch.setattr(episode_qc, "recompute_native_qc", lambda *a, **k: recomputed.append(1) or copy.deepcopy(document))
        location = store.seal(seal, teacher=sealed_teacher(store, "PASSED"), qc_report_path=report_path)
        result = json.loads((location / "result.json").read_bytes())
        assert result["status"] == "PASSED" and result["act_data_qc"] == "PASS"
        assert len(calls) == expected_seal_reads, (trusts, covers)
        assert len(recomputed) == (0 if trusts and covers else 1), (trusts, covers)
