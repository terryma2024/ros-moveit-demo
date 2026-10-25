"""The appearance and Teacher source of a scene, read from the scene list a frozen input set binds (indoor P3).

The list is bound into `inputs_sha256`, so the plan and the rows are frozen with the inputs; every reader re-derives the row it reads."""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from paths import PACKAGE_ROOT
from so101_demo.act import appearance_plan as ap
from so101_demo.act import episode_open, frozen_appearance
from so101_demo.act.diagnostic_episode_inputs import SCENE_MANIFEST_PATH

NOMINAL_DIR = PACKAGE_ROOT / "assets/mujoco/act"
SEED = 710025


def inventory():
    return ap.scene_inventory(NOMINAL_DIR)


def plan():
    return ap.make_plan(seed=SEED, nominal_share=0.25, nominal_scene_sha256=inventory()["scene_sha256"])


def rows(count=12):
    return [{"scene_id": f"p3-{index:03d}", "seed": 100 + index, "split": "formal", "cup_position_world_m": [0.02, -0.25, 0.165]}
            for index in range(count)]


def frozen_set(tmp_path, *, with_plan=True, mutate=None, count=12):
    """`(frozen, manifest_path)`: a frozen-set stand-in whose `scene_manifest` binding is the real one (path, hash, bytes, row count)."""

    annotated = ap.annotate_rows(plan(), rows(count), inventory()) if with_plan else rows(count)
    document = {"kind": "ACT_CONTAINER_SCENE_MANIFEST", "schema_version": 1, "list": "p3", "cup_z_m": 0.165, "scenarios": annotated}
    if with_plan:
        document[frozen_appearance.PLAN_KEY] = plan()
    if mutate is not None:
        mutate(document)
    payload = (json.dumps(document, sort_keys=True, indent=1) + "\n").encode()
    target = tmp_path / SCENE_MANIFEST_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    manifest_path = tmp_path / "inputs-manifest.json"
    manifest_path.write_text("{}")
    frozen = {"mode": "formal", "scene_manifest": {"path": SCENE_MANIFEST_PATH, "sha256": hashlib.sha256(payload).hexdigest(),
                                                   "bytes": len(payload), "scene_count": count}}
    return frozen, manifest_path


def test_a_list_with_a_plan_gives_each_scene_its_verified_appearance_and_source(tmp_path):
    frozen, manifest = frozen_set(tmp_path)
    kinds = set()
    for row in rows():
        entry = frozen_appearance.scene_entry(frozen, manifest, row["scene_id"], inventory=inventory())
        assert entry["plan"] == plan() and entry["appearance"] == ap.derive(plan(), row["scene_id"], inventory())
        assert entry["teacher_source"] == ap.teacher_source_for(entry["appearance"]["kind"])
        kinds.add(entry["appearance"]["kind"])
    assert kinds == {ap.KIND_NOMINAL, ap.KIND_RANDOMISED}


def test_the_inventory_may_be_a_callable_that_is_only_called_for_a_list_with_a_plan(tmp_path):
    frozen, manifest = frozen_set(tmp_path)
    calls = []
    frozen_appearance.scene_entry(frozen, manifest, "p3-000", inventory=lambda: calls.append(1) or inventory())
    assert calls == [1]
    plain, plain_manifest = frozen_set(tmp_path / "plain", with_plan=False)
    assert frozen_appearance.scene_entry(plain, plain_manifest, "p3-000", inventory=lambda: pytest.fail("no plan, no inventory")) is None


def test_a_list_without_a_plan_has_no_appearance_and_a_row_that_claims_one_is_refused(tmp_path):
    plain, manifest = frozen_set(tmp_path, with_plan=False)
    assert frozen_appearance.scene_entry(plain, manifest, "p3-003") is None

    def claim(document):
        document["scenarios"][3]["teacher_source"] = ap.TEACHER_SOURCE_PRIVILEGED

    claimed, claimed_manifest = frozen_set(tmp_path / "claimed", with_plan=False, mutate=claim)
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_ROW_WITHOUT_PLAN"):
        frozen_appearance.scene_entry(claimed, claimed_manifest, "p3-003")


def test_a_row_that_is_not_the_derivation_of_its_scene_id_refuses_every_reader_of_the_list(tmp_path):
    def swap(document):
        document["scenarios"][5]["teacher_source"] = (ap.TEACHER_SOURCE_CAMERA if document["scenarios"][5]["teacher_source"]
                                                      == ap.TEACHER_SOURCE_PRIVILEGED else ap.TEACHER_SOURCE_PRIVILEGED)

    frozen, manifest = frozen_set(tmp_path, mutate=swap)
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_TEACHER_SOURCE_MISMATCH"):
        frozen_appearance.scene_entry(frozen, manifest, "p3-000", inventory=inventory())          # another row than the bad one

    def missing(document):
        del document["scenarios"][2]["appearance"]

    frozen, manifest = frozen_set(tmp_path / "m", mutate=missing)
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_ROW_MISSING"):
        frozen_appearance.scene_entry(frozen, manifest, "p3-000", inventory=inventory())


def test_a_plan_for_another_installed_scene_or_a_plan_that_needs_an_inventory_is_refused(tmp_path):
    frozen, manifest = frozen_set(tmp_path)
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_INVENTORY_REQUIRED"):
        frozen_appearance.scene_entry(frozen, manifest, "p3-000")
    other = dict(inventory(), scene_sha256="0" * 64)
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_NOMINAL_SCENE_MISMATCH"):
        frozen_appearance.scene_entry(frozen, manifest, "p3-000", inventory=other)
    with pytest.raises(ValueError, match="APPEARANCE_SCENE_NOT_IN_LIST"):
        frozen_appearance.scene_entry(frozen, manifest, "p3-999", inventory=inventory())


def test_a_scene_list_that_changed_after_the_freeze_is_refused(tmp_path):
    frozen, manifest = frozen_set(tmp_path)
    path = tmp_path / SCENE_MANIFEST_PATH
    document = json.loads(path.read_text())
    document["scenarios"][0]["appearance"]["kind"] = "randomised"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="INPUTS_SCENE_MANIFEST_INVALID"):
        frozen_appearance.scene_entry(frozen, manifest, "p3-000", inventory=inventory())


NOMINAL_MODEL = "ab" * 32
LOADED_MODEL = "cd" * 32


def equivalence_of(entry, tmp_path):
    """What the Teacher records for a variant stack: the proof of this variant (realized on this host) and its hashes."""
    from so101_demo.act import model_equivalence, scene_variant_run

    realized = scene_variant_run.realize_into(tmp_path / "proof-variant", PACKAGE_ROOT, entry["appearance"]["variant"])
    proof = model_equivalence.make_proof(scene_id=entry["appearance"]["scene_id"], declared_model_sha256=NOMINAL_MODEL,
                                         loaded_model_sha256=LOADED_MODEL, record=realized)
    return {"proof": proof, "proof_sha256": model_equivalence.proof_sha256(proof), "declared_model_sha256": NOMINAL_MODEL,
            "loaded_model_sha256": LOADED_MODEL}


def teacher_record(entry, tmp_path=None):
    appearance = entry["appearance"]
    return {"source": entry["teacher_source"], "kind": appearance["kind"], "plan_sha256": appearance["plan_sha256"],
            "draw_sha256": appearance["draw_sha256"], "variant_sha256": appearance["variant_sha256"],
            "model_equivalence": None if appearance["variant"] is None else equivalence_of(entry, tmp_path)}


def scene_with(tmp_path, kind):
    frozen, manifest = frozen_set(tmp_path)
    for row in rows():
        entry = frozen_appearance.scene_entry(frozen, manifest, row["scene_id"], inventory=inventory())
        if entry["appearance"]["kind"] == kind:
            return frozen, manifest, row["scene_id"], entry
    raise AssertionError(kind)


def test_the_identity_of_a_randomised_episode_carries_the_draw_the_realized_hash_and_the_privileged_source(tmp_path):
    frozen, manifest, scene, entry = scene_with(tmp_path, ap.KIND_RANDOMISED)
    record_in = teacher_record(entry, tmp_path)
    arguments = episode_open.appearance_arguments(frozen, manifest, scene, record_in, share=PACKAGE_ROOT, declared_expected=NOMINAL_MODEL)
    assert arguments["teacher_source"] == ap.TEACHER_SOURCE_PRIVILEGED
    record = arguments["scene_appearance"]
    # D1: both hashes and the proof's hash are in the identity
    assert record["model_equivalence"] == {"declared_model_sha256": NOMINAL_MODEL, "loaded_model_sha256": LOADED_MODEL,
                                           "proof_sha256": record_in["model_equivalence"]["proof_sha256"]}
    assert record["kind"] == "randomised" and record["layout"] == "A" and record["plan_sha256"] == plan()["plan_sha256"]
    assert record["variant_sha256"] == entry["appearance"]["variant_sha256"] and record["cup_family"] in ap.POOLS["cups"]
    assert len(record["realized_sha256"]) == 64 and record["fingerprint_version"] == 2
    assert record["physics_fingerprint"] == record["nominal_physics_fingerprint"]
    assert record["variant_name"] == f"p3-{scene}"
    again = episode_open.appearance_arguments(frozen, manifest, scene, record_in, share=PACKAGE_ROOT, declared_expected=NOMINAL_MODEL)
    assert again == arguments


def test_the_identity_of_a_nominal_episode_names_the_camera_source_and_no_variant(tmp_path):
    frozen, manifest, scene, entry = scene_with(tmp_path, ap.KIND_NOMINAL)
    arguments = episode_open.appearance_arguments(frozen, manifest, scene, teacher_record(entry), share=PACKAGE_ROOT)
    assert arguments["teacher_source"] == ap.TEACHER_SOURCE_CAMERA
    assert arguments["scene_appearance"]["kind"] == "nominal" and arguments["scene_appearance"]["variant_sha256"] is None
    assert "realized_sha256" not in arguments["scene_appearance"] and "model_equivalence" not in arguments["scene_appearance"]
    with pytest.raises(ValueError, match="APPEARANCE_MODEL_EQUIVALENCE_UNEXPECTED"):
        episode_open.appearance_arguments(frozen, manifest, scene, {**teacher_record(entry), "model_equivalence": {"proof": {}}}, share=PACKAGE_ROOT)


def test_the_identity_is_refused_when_the_teacher_manifest_does_not_say_the_same(tmp_path):
    frozen, manifest, scene, entry = scene_with(tmp_path, ap.KIND_RANDOMISED)
    good = teacher_record(entry, tmp_path)
    for bad in (None, {}, {**good, "source": ap.TEACHER_SOURCE_CAMERA}, {**good, "draw_sha256": "0" * 64}, {**good, "plan_sha256": "1" * 64}):
        with pytest.raises(ValueError, match="APPEARANCE_TEACHER_MANIFEST_MISMATCH"):
            episode_open.appearance_arguments(frozen, manifest, scene, bad, share=PACKAGE_ROOT)


def test_a_randomised_identity_without_a_valid_proof_for_this_variant_and_the_frozen_model_is_refused(tmp_path):
    frozen, manifest, scene, entry = scene_with(tmp_path, ap.KIND_RANDOMISED)
    good = teacher_record(entry, tmp_path)
    proof = good["model_equivalence"]
    # no proof at all: the run had the override set and nothing proved it
    for equivalence in (None, {}, {**proof, "proof_sha256": "00" * 32}, {**proof, "loaded_model_sha256": "ee" * 32}):
        with pytest.raises(ValueError, match="APPEARANCE_MODEL_EQUIVALENCE_INVALID"):
            episode_open.appearance_arguments(frozen, manifest, scene, {**good, "model_equivalence": equivalence}, share=PACKAGE_ROOT,
                                              declared_expected=NOMINAL_MODEL)
    with pytest.raises(ValueError, match="APPEARANCE_MODEL_EQUIVALENCE_INVALID"):       # a proof of another declared identity than the frozen model
        episode_open.appearance_arguments(frozen, manifest, scene, good, share=PACKAGE_ROOT, declared_expected="ef" * 32)
    other = next(row for row in rows() if row["scene_id"] != scene
                 and frozen_appearance.scene_entry(frozen, manifest, row["scene_id"], inventory=inventory())["appearance"]["variant"] is not None)
    other_entry = frozen_appearance.scene_entry(frozen, manifest, other["scene_id"], inventory=inventory())
    with pytest.raises(ValueError, match="APPEARANCE_MODEL_EQUIVALENCE_NOT_THIS_VARIANT"):   # a proof of another variant
        episode_open.appearance_arguments(frozen, manifest, scene, {**good, "model_equivalence": equivalence_of(other_entry, tmp_path / "o")},
                                          share=PACKAGE_ROOT, declared_expected=NOMINAL_MODEL)


def test_a_freeze_that_binds_no_scene_list_or_a_list_without_a_plan_adds_nothing_to_the_identity(tmp_path):
    assert episode_open.appearance_arguments({"mode": "formal"}, tmp_path / "m.json", "p3-000", None, share=PACKAGE_ROOT) == {}
    plain, manifest = frozen_set(tmp_path, with_plan=False)
    assert episode_open.appearance_arguments(plain, manifest, "p3-000", None, share=PACKAGE_ROOT) == {}


def test_a_variant_that_changed_the_physics_is_refused_when_the_identity_is_opened(tmp_path, monkeypatch):
    frozen, manifest, scene, entry = scene_with(tmp_path, ap.KIND_RANDOMISED)
    from so101_demo.act import scene_variant_run

    monkeypatch.setattr(scene_variant_run, "stripped_physics_fingerprint_of_file", lambda path: str(path))
    with pytest.raises(Exception, match="SCENE_VARIANT_PHYSICS_MISMATCH"):
        episode_open.appearance_arguments(frozen, manifest, scene, teacher_record(entry, tmp_path), share=PACKAGE_ROOT)
