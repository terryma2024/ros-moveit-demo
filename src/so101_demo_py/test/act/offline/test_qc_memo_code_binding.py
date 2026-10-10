"""The QC memo is bound to the source of the QC code, and VALID data needs a covering memo."""

import copy
import json
from pathlib import Path

import pytest

from so101_demo.act import episode_qc, qc_memo
from so101_demo.act.offline import orchestration

from test_offline_recording_switch import (LEASE, FakePilot, FakeProcesses, ScriptedGroup, _decision, _exit_code,
                                    collection_for, pilot_factory, worker_runtime)
from test_independent_qc_memo import episode, paths


@pytest.fixture(autouse=True)
def _fresh_fake_pilots():
    FakePilot.instances.clear()
    FakePilot.log = None
    yield
    FakePilot.instances.clear()
    FakePilot.log = None


# ---- the memo is bound to the QC code ----------------------------------------------------------------------------------------

def test_the_code_digest_covers_the_qc_chain_and_is_stable():
    digest = qc_memo.code_digest()
    assert len(digest) == 64 and digest == qc_memo.code_digest()
    assert {"episode_qc", "episode_audit", "recorder", "qc_memo"} <= set(qc_memo.CODE_MODULES)
    package = Path(qc_memo.__file__).parent
    assert all((package / f"{name}.py").is_file() for name in qc_memo.CODE_MODULES)


def test_a_memo_written_by_other_qc_code_triggers_a_full_recompute(tmp_path, monkeypatch):
    from so101_demo.act import result_store

    root, scope, inputs, teacher, report, report_path = episode(tmp_path)
    monkeypatch.setattr(qc_memo, "code_digest", lambda: "a" * 64)          # the QC code that wrote the memo
    qc_memo.write_memo(report_path, report, **paths(root, scope, inputs, teacher))
    assert qc_memo.memo_matches(report_path, report, **paths(root, scope, inputs, teacher)) is True
    monkeypatch.setattr(qc_memo, "code_digest", lambda: "b" * 64)          # a Coordinator from another install
    assert qc_memo.memo_matches(report_path, report, **paths(root, scope, inputs, teacher)) is False
    calls = []
    monkeypatch.setattr(episode_qc, "recompute_native_qc", lambda *a, **k: calls.append(1) or copy.deepcopy(report))
    assert result_store._recomputed_or_memoised(report_path, report, episode_root=root, scope=scope, inputs_manifest=inputs,
                                                trust_memo=True, reader=episode_qc.recompute_native_qc) == report
    assert calls == [1], "the code digest differs: recomputed in full"


def test_a_memo_without_a_code_digest_or_with_the_old_schema_is_not_trusted(tmp_path):
    root, scope, inputs, teacher, report, report_path = episode(tmp_path)
    memo = qc_memo.write_memo(report_path, report, **paths(root, scope, inputs, teacher))
    document = json.loads(memo.read_text())
    for change in ({"code_digest": None}, {"schema_version": 1}):
        mutated = {**document, **change}
        if change.get("code_digest", 1) is None:
            del mutated["code_digest"]
        memo.write_text(json.dumps(mutated))
        assert qc_memo.memo_matches(report_path, report, **paths(root, scope, inputs, teacher)) is False, change

# ---- VALID data needs the memo; a missing or stale memo never costs the Teacher its sealed result -----------------

def test_the_default_memo_check_is_the_real_memo_match(tmp_path, monkeypatch):
    root, scope, inputs, teacher, report, report_path = episode(tmp_path)
    monkeypatch.setattr(episode_qc, "read_qc_report", lambda path: copy.deepcopy(report))
    kwargs = dict(qc_output=report_path, episode_root=root, scope=scope, inputs_manifest=inputs)
    assert orchestration._memo_covers(**kwargs) is False, "no memo yet"
    qc_memo.write_memo(report_path, report, **paths(root, scope, inputs, teacher))
    assert orchestration._memo_covers(**kwargs) is True
    (root / "audit" / "events.jsonl").write_text('{"x": 99}\n')
    assert orchestration._memo_covers(**kwargs) is False, "stale: the episode changed after the memo"
    monkeypatch.setattr(episode_qc, "read_qc_report", lambda path: (_ for _ in ()).throw(ValueError("unreadable")))
    assert orchestration._memo_covers(**kwargs) is False


@pytest.mark.parametrize("memo", ["missing", "stale"])
def test_a_processor_verdict_without_a_covering_memo_is_invalid_data_not_valid_data(tmp_path, memo):
    collection, point, _ = collection_for(tmp_path, memo_check=lambda **kwargs: False)
    collection.start_before_teacher()
    outcome = collection.finish(lease=LEASE, deadline_s=collection._clock() + 100_000.0)
    assert (outcome.data_status, outcome.reason) == ("INVALID", "OFFLINE_QC_MEMO_NOT_VALID")
    assert "qc_report_path" not in outcome.facts


@pytest.mark.parametrize("memo", ["missing", "stale"])
def test_a_missing_or_stale_memo_keeps_the_teacher_pass_sealed_instead_of_losing_it_to_the_lease_deadline(tmp_path, monkeypatch, memo):
    from act_result_teacher import sealed_teacher
    from test_act_result_schema3 import setup_result
    from test_parallel_worker_runtime import _lease

    from so101_demo.act.collection_orchestration import CollectionOptions

    monkeypatch.setattr(orchestration, "PilotRecording", pilot_factory())
    monkeypatch.setattr(orchestration, "_memo_covers", lambda **kwargs: False)         # no memo, or a memo of other bytes
    events = []
    runtime, group, events, clock = worker_runtime(tmp_path / "w", CollectionOptions("on"), events=events,
                                                   group=ScriptedGroup(events, FakeProcesses()))
    runtime.start_physical_runtime()
    lease = _lease()
    runtime.reset_and_validate_point(lease)
    baseline = _decision()
    decision = runtime._finish_collection(lease, baseline)
    assert (decision.act_data_status, decision.act_data_reason) == ("INVALID", "OFFLINE_QC_MEMO_NOT_VALID")
    assert decision.qc_report_path is None, "the store never sees a QC report it would have to recompute"
    assert (decision.status, decision.teacher_execution_status, decision.teacher_task_result) == (
        baseline.status, baseline.teacher_execution_status, baseline.teacher_task_result)
    (tmp_path / "store").mkdir()
    store, seal, document, inputs = setup_result(tmp_path / "store", monkeypatch)
    monkeypatch.setattr(episode_qc, "recompute_native_qc", lambda *a, **k: pytest.fail("the store recomputed the QC (290 s)"))
    location = store.seal(seal, teacher=sealed_teacher(store, "PASSED", data=decision.act_data_status, reason=decision.act_data_reason))
    sealed = json.loads((location / "result.json").read_bytes())
    assert sealed["status"] == "PASSED" and sealed["act_data_status"] == "INVALID" and sealed["act_data_qc"] == "NOT_RUN"
    assert _exit_code(sealed, monkeypatch) == 3
