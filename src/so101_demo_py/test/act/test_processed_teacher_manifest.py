"""Phase 2 grades an episode that lives under `<run>/processing/<scene>/<attempt>-proc-<n>/`, which has no `dynamic/` directory.

The Teacher manifest is phase 1's sealed one (`<sealed>/dynamic/dynamic-execute-manifest.json`). Every phase-2 QC step (the
processor's memo check, its grading, the Host's readback regrade) must be given that path explicitly: the old default
(`<episode>/../dynamic/...`) names a file that does not exist there. The chain below is the real one (`verify_processed_result`,
`grade_episode`, `_verify_result_qc`, `_recomputed_or_memoised`, `qc_memo`) over real files; only the full QC recomputation is a double, and it
reads its Teacher manifest exactly as `_recompute_native_qc` does (explicit path, else the episode-relative default).
"""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from processed_fixture import Processed

from so101_demo.act import episode_qc, qc_memo, result_store


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build_graded_scene(tmp_path):
    """A VALID/PASS processed scene whose episode, audit, scope, inputs and QC report are consistent real files."""
    scene = Processed(tmp_path)
    assert not (scene.output / "dynamic").exists(), "the phase-2 output directory has no dynamic/"
    scene.scope.write_text(json.dumps(dict(mode="formal", inputs_sha256="1" * 64)))
    scene.inputs.write_text(json.dumps(dict(mode="formal", inputs_sha256="1" * 64)))
    seal = dict(attempt_id=scene.identity["attempt_id"], session_id=scene.identity["session_id"],
                reset_epoch=scene.identity["reset_epoch"], record_count=3)
    (scene.out / "episode/seal.json").write_text(json.dumps(seal))
    (scene.out / "episode/audit").mkdir()
    audit = scene.out / "episode/audit/audit-manifest.json"
    audit.write_text(json.dumps(dict(identity=dict(scene.identity, lease=scene.lease, mode="formal"))))
    report = dict(kind="ACT_EPISODE_QC", schema_version=3, rule_version=episode_qc.QC_RULE_VERSION, status="PASS", reason="",
                  identity=dict(scene.identity, lease=scene.lease, mode="formal"), counts=dict(records=3),
                  inputs_sha256="1" * 64, scope_sha256=sha(scene.scope.read_bytes()), audit_manifest_sha256=sha(audit.read_bytes()),
                  episode_seal_sha256=sha((scene.out / "episode/seal.json").read_bytes()))
    report_path = scene.out / "qc-report.json"
    report_path.write_bytes(episode_qc._report_canonical(report))
    scene.write(episode_seal_sha256=sha((scene.out / "episode/seal.json").read_bytes()), qc_report_sha256=sha(report_path.read_bytes()),
                inputs_sha256="1" * 64, scope_sha256=report["scope_sha256"], audit_manifest_sha256=report["audit_manifest_sha256"])
    return scene, report, report_path


@pytest.fixture
def chain(monkeypatch):
    """The real chain with the schema validator, the audit-lease reader and the full recomputation replaced."""
    monkeypatch.setattr(episode_qc, "read_qc_report", lambda path: json.loads(Path(path).read_bytes()))
    monkeypatch.setattr(result_store, "_verify_audit_lease", lambda manifest, lease: None)
    calls = []

    def recompute(episode_root, *, scope, inputs_manifest, teacher_manifest=None, topic_loss=None):
        teacher = Path(episode_root).parent / "dynamic" / "dynamic-execute-manifest.json" if teacher_manifest is None else teacher_manifest
        calls.append(teacher)
        Path(teacher).read_bytes()          # the real one raises FileNotFoundError here
        return copy.deepcopy(json.loads((Path(episode_root).parent / "qc-report.json").read_bytes()))
    monkeypatch.setattr(episode_qc, "recompute_native_qc", recompute)
    return calls


def test_the_host_readback_recomputes_with_the_sealed_teacher_manifest(tmp_path, chain):
    scene, report, report_path = build_graded_scene(tmp_path)
    from so101_demo.act.processed_result import verify_processed_result

    record = verify_processed_result(scene.output, sealed=scene.sealed, scene_id=scene.scene, result_sha256=scene.result_sha256,
                                     receipt_sha256=scene.receipt_sha256, scope=scene.scope, inputs_manifest=scene.inputs)
    assert record["act_data_status"] == "VALID" and record["act_data_qc"] == "PASS"
    assert chain == [scene.sealed / "dynamic" / "dynamic-execute-manifest.json"]


def test_a_memo_bound_to_the_sealed_teacher_manifest_is_trusted_by_the_processor_grading(tmp_path, chain):
    from so101_demo.runtime.act_processor.processing import grade_episode

    scene, report, report_path = build_graded_scene(tmp_path)
    teacher = scene.sealed / "dynamic" / "dynamic-execute-manifest.json"
    qc_memo.write_memo(report_path, report, episode_root=scene.out / "episode", scope=scene.scope, inputs_manifest=scene.inputs,
                       teacher_manifest=teacher)
    graded = grade_episode(out=scene.out, qc_output=report_path, lease=scene.lease, identity=scene.identity, scope=scene.scope,
                           inputs_manifest=scene.inputs, teacher_status="PASSED", teacher_manifest=teacher)
    assert (graded["status"], graded["qc"]) == ("VALID", "PASS")
    assert chain == [], "the memo covers the report and these files: nothing is recomputed"
    assert qc_memo.memo_matches(report_path, report, episode_root=scene.out / "episode", scope=scene.scope,
                                inputs_manifest=scene.inputs, teacher_manifest=teacher) is True


def test_the_memo_check_and_the_grading_of_a_task_get_the_sealed_teacher_manifest(tmp_path):
    from test_processor_processing import FakeRunner, Fixture, execution

    fixture = Fixture(tmp_path)
    asked = {}

    def memo(**kwargs):
        asked["memo"] = kwargs
        return True

    def grader(**kwargs):
        asked["grader"] = kwargs
        return dict(status="INVALID", reason="x", qc="NOT_RUN", episode_sha256=None, binding=None)
    execution(fixture, FakeRunner(0), grader=grader, memo=memo).run()
    expected = fixture.sealed / "dynamic" / "dynamic-execute-manifest.json"
    assert asked["memo"]["teacher_manifest"] == expected
    assert asked["grader"]["teacher_manifest"] == expected
