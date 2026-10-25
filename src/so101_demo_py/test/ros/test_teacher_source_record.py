"""Indoor P3: the Teacher's record of its source, and the helpers the dynamic runtime uses to read it from the frozen scene list."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from paths import PACKAGE_ROOT
from so101_demo.act import appearance_plan as ap
from so101_demo.core.task_geometry import Pose7
from so101_demo.ros.dynamic_frozen_policy import _check_teacher_source_pose, _frozen_teacher_source
from test_frozen_appearance import frozen_set, rows
from test_teacher_diversity_runtime import make_adapter


def sample(x, y=-0.25, z=0.165):
    return SimpleNamespace(pose_world=Pose7((x, y, z, 0.0, 0.0, 0.0, 1.0)))


def observation(x, y=-0.25, z=0.165):
    return SimpleNamespace(simulator_pose_world=SimpleNamespace(position_m=(x, y, z)))


PROOF = {"sha256": "ab" * 32, "declared": "cd" * 32, "loaded": "ef" * 32, "proof": {"kind": "ACT_MODEL_EQUIVALENCE_PROOF"}}


def entry(source, kind=None):
    kind = kind or ("randomised" if source == ap.TEACHER_SOURCE_PRIVILEGED else "nominal")
    return {"teacher_source": source, "appearance": {"kind": kind}}


def bind(monkeypatch, proof=PROOF):
    from so101_demo.act import model_equivalence

    monkeypatch.setattr(model_equivalence, "bound", lambda environ=None: proof)


def test_a_privileged_pose_within_the_published_tolerance_passes_and_returns_the_gap_and_keeps_the_proof(monkeypatch):
    bind(monkeypatch)
    given = entry(ap.TEACHER_SOURCE_PRIVILEGED)
    gap = _check_teacher_source_pose(given, sample(0.02), observation(0.02 + 5e-5))
    assert gap == pytest.approx(5e-5)
    assert given["model_equivalence"] == {"proof_sha256": PROOF["sha256"], "declared_model_sha256": PROOF["declared"],
                                          "loaded_model_sha256": PROOF["loaded"], "proof": PROOF["proof"]}
    with pytest.raises(RuntimeError, match="TEACHER_SOURCE_PRIVILEGED_POSE_MISMATCH"):
        _check_teacher_source_pose(entry(ap.TEACHER_SOURCE_PRIVILEGED), sample(0.02), observation(0.02 + 2e-4))


def test_a_camera_pose_is_measured_and_never_refused_and_no_entry_measures_nothing(monkeypatch):
    bind(monkeypatch, None)
    given = entry(ap.TEACHER_SOURCE_CAMERA)
    assert _check_teacher_source_pose(given, sample(0.02), observation(0.05)) == pytest.approx(0.03)
    assert given["model_equivalence"] is None
    assert _check_teacher_source_pose(None, sample(0.02), observation(0.5)) is None


def test_a_randomised_episode_without_a_bound_proof_and_a_nominal_one_with_a_proof_are_refused_before_any_motion(monkeypatch):
    bind(monkeypatch, None)
    with pytest.raises(RuntimeError, match="TEACHER_SOURCE_MODEL_EQUIVALENCE_MISSING"):
        _check_teacher_source_pose(entry(ap.TEACHER_SOURCE_PRIVILEGED), sample(0.02), observation(0.02))
    bind(monkeypatch)
    with pytest.raises(RuntimeError, match="TEACHER_SOURCE_MODEL_EQUIVALENCE_UNEXPECTED"):
        _check_teacher_source_pose(entry(ap.TEACHER_SOURCE_CAMERA), sample(0.02), observation(0.02))


def test_the_entry_of_the_scene_comes_from_the_frozen_list_and_only_a_list_with_a_plan_has_one(tmp_path):
    frozen, manifest = frozen_set(tmp_path)
    found = _frozen_teacher_source(frozen, manifest, PACKAGE_ROOT, rows()[2]["scene_id"])
    assert found["teacher_source"] == ap.teacher_source_for(found["appearance"]["kind"])
    plain, plain_manifest = frozen_set(tmp_path / "plain", with_plan=False)
    assert _frozen_teacher_source(plain, plain_manifest, PACKAGE_ROOT, "p3-000") is None
    assert _frozen_teacher_source({"mode": "formal"}, manifest, PACKAGE_ROOT, "p3-000") is None
    assert _frozen_teacher_source(None, None, PACKAGE_ROOT, "p3-000") is None
    assert _frozen_teacher_source(frozen, manifest, PACKAGE_ROOT, None) is None
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_NOMINAL_SCENE_MISMATCH"):
        other = tmp_path / "other"
        (other / "assets/mujoco/act").mkdir(parents=True)
        (other / "assets/mujoco/act/scene_side_wrist_indoor.xml").write_text(
            (PACKAGE_ROOT / "assets/mujoco/act/scene_side_wrist_indoor.xml").read_text().replace("ind_main", "ind_main2"))
        _frozen_teacher_source(frozen, manifest, other, "p3-000")


def test_the_source_and_the_draw_are_on_the_teacher_document(tmp_path):
    adapter = make_adapter(tmp_path)
    adapter._document = {}
    written = []
    adapter._write = lambda: written.append(dict(adapter._document))
    frozen, manifest = frozen_set(tmp_path / "f")
    scene = rows()[4]["scene_id"]
    found = _frozen_teacher_source(frozen, manifest, PACKAGE_ROOT, scene)
    found["model_equivalence"] = {"proof_sha256": "ab" * 32}
    adapter._record_teacher_source(found, published_truth_gap_m=3.2e-5)
    record = adapter._document["teacher_source"]
    assert record == {"source": found["teacher_source"], "kind": found["appearance"]["kind"], "plan_sha256": found["appearance"]["plan_sha256"],
                      "draw_sha256": found["appearance"]["draw_sha256"], "variant_sha256": found["appearance"]["variant_sha256"],
                      "published_vs_simulator_m": 3.2e-5, "model_equivalence": {"proof_sha256": "ab" * 32}}
    assert len(written) == 1
