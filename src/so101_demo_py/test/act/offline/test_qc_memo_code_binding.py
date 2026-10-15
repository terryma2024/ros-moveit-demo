"""The QC memo is bound to the source of the QC code, and VALID data needs a covering memo."""

import copy
import json
from pathlib import Path

import pytest

from so101_demo.act import episode_qc, qc_memo
from so101_demo.runtime.act_processor import processing

from test_offline_recording_switch import FakePilot
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
    assert all((package / f"{name}.py").is_file() or (package / name / "__init__.py").is_file() for name in qc_memo.CODE_MODULES)


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
    assert processing.qc_memo_matches(**kwargs) is False, "no memo yet"
    qc_memo.write_memo(report_path, report, **paths(root, scope, inputs, teacher))
    assert processing.qc_memo_matches(**kwargs) is True
    (root / "audit" / "events.jsonl").write_text('{"x": 99}\n')
    assert processing.qc_memo_matches(**kwargs) is False, "stale: the episode changed after the memo"
    monkeypatch.setattr(episode_qc, "read_qc_report", lambda path: (_ for _ in ()).throw(ValueError("unreadable")))
    assert processing.qc_memo_matches(**kwargs) is False
