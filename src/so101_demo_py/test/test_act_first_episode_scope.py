"""Task 1 of the non-head first-episode plan: explicit mode and closed scope binding.

The diagnostic mode replaces only target selection and the Head prerequisite. Robot, contact,
controller, reset, collision, holding, release, sampling and identity gates all still apply, so
these tests assert both directions: the diagnostic mode must not clear a non-Head safety gate, and
the formal mode must still require real Head qualification.
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from so101_demo.act.collection_scope import (
    SCOPE_KIND,
    SCOPE_SCHEMA_VERSION,
    CollectionMode,
    build_collection_scope,
    read_collection_scope,
    require_scope,
    write_collection_scope,
)
from so101_demo.act.first_episode_inputs import (
    CANDIDATES_KIND,
    INPUT_ROLES,
    MANIFEST_KIND,
    freeze_inputs,
    inspect_inputs,
    read_candidate_registry,
    read_inputs_manifest,
    require_nonhead_gate,
)

INPUTS_SHA = "a" * 64
SOURCE_COMMIT = "a" * 40
CONFIG_SHA = "b" * 64


def test_diagnostic_does_not_bypass_nonhead_safety():
    with pytest.raises(ValueError, match="NONHEAD_SAFETY_NOT_READY"):
        require_scope("preselected_target_diagnostic", head_ready=False,
                      nonhead_ready=False, worker_count=1, resume=False)


def test_formal_still_requires_head_qualification():
    with pytest.raises(ValueError, match="HEAD_QUALIFICATION_REQUIRED"):
        require_scope("formal", head_ready=False, nonhead_ready=True,
                      worker_count=1, resume=False)


def test_unknown_mode_is_refused_by_name():
    for bad in ("diagnostic", "", None, 1, "FORMAL"):
        with pytest.raises(ValueError, match="COLLECTION_MODE_UNKNOWN"):
            require_scope(bad, head_ready=True, nonhead_ready=True,
                          worker_count=1, resume=False)


def test_diagnostic_is_one_worker_and_never_resumes():
    mode = require_scope("preselected_target_diagnostic", head_ready=False,
                         nonhead_ready=True, worker_count=1, resume=False)
    assert mode is CollectionMode.DIAGNOSTIC
    for workers, resume in ((2, False), (8, False), (0, False), (1, True)):
        with pytest.raises(ValueError, match="DIAGNOSTIC_SCOPE_INVALID"):
            require_scope("preselected_target_diagnostic", head_ready=False,
                          nonhead_ready=True, worker_count=workers, resume=resume)


def test_formal_remains_the_default_scope():
    # the formal mode needs the real Head proof and keeps the W8 worker count; the diagnostic
    # mode is opt-in and never inherits a caller's accidental default
    assert require_scope(CollectionMode.FORMAL, head_ready=True, nonhead_ready=True,
                         worker_count=8, resume=False) is CollectionMode.FORMAL
    assert require_scope("preselected_target_diagnostic", head_ready=False, nonhead_ready=True,
                         worker_count=1, resume=False) is CollectionMode.DIAGNOSTIC


def test_scope_classification_spawns_nothing_and_touches_no_resource(monkeypatch, tmp_path):
    """Choosing a mode is pure classification: no process, no reset, no action, no file."""

    def _refuse(*args, **kwargs):
        raise AssertionError("scope classification must not spawn or mutate")

    monkeypatch.setattr(subprocess, "Popen", _refuse)
    monkeypatch.setattr(subprocess, "run", _refuse)
    monkeypatch.setattr(os, "fork", _refuse, raising=False)
    monkeypatch.setattr(os, "posix_spawn", _refuse, raising=False)
    monkeypatch.setattr(os, "system", _refuse)
    monkeypatch.chdir(tmp_path)
    before = sorted(tmp_path.iterdir())
    assert require_scope("preselected_target_diagnostic", head_ready=False,
                         nonhead_ready=True, worker_count=1, resume=False) is CollectionMode.DIAGNOSTIC
    assert sorted(tmp_path.iterdir()) == before


def test_scope_document_is_closed_and_binds_the_frozen_inputs(tmp_path):
    scope = build_collection_scope(CollectionMode.DIAGNOSTIC, scene_id="default", seed=0,
                                   inputs_sha256=INPUTS_SHA)
    assert set(scope) == {"kind", "schema_version", "mode", "scene_id", "seed", "inputs_sha256"}
    assert scope["kind"] == SCOPE_KIND
    assert scope["schema_version"] == SCOPE_SCHEMA_VERSION
    assert scope["mode"] == "preselected_target_diagnostic"
    target = tmp_path / "collection-scope.json"
    digest = write_collection_scope(scope, target)
    assert digest == hashlib.sha256(target.read_bytes()).hexdigest()
    assert read_collection_scope(target) == scope


def test_scope_document_is_bound_to_the_frozen_inputs_digest(tmp_path):
    scope = build_collection_scope(CollectionMode.DIAGNOSTIC, scene_id="default", seed=0,
                                   inputs_sha256=INPUTS_SHA)
    target = tmp_path / "collection-scope.json"
    write_collection_scope(scope, target)
    assert read_collection_scope(target, expected_inputs_sha256=INPUTS_SHA)["inputs_sha256"] == INPUTS_SHA
    with pytest.raises(ValueError, match="COLLECTION_SCOPE_INVALID"):
        read_collection_scope(target, expected_inputs_sha256="b" * 64)


def test_scope_document_refuses_a_rewritten_mode_or_identity(tmp_path):
    scope = build_collection_scope(CollectionMode.DIAGNOSTIC, scene_id="default", seed=0,
                                   inputs_sha256=INPUTS_SHA)
    target = tmp_path / "collection-scope.json"
    write_collection_scope(scope, target)
    for mutation in ({"mode": "unknown"}, {"seed": -1}, {"seed": True}, {"scene_id": ""},
                     {"schema_version": 2}, {"kind": "OTHER"}, {"extra": 1},
                     {"inputs_sha256": "not-a-digest"}):
        broken = dict(scope)
        broken.update(mutation)
        target.write_text(json.dumps(broken, sort_keys=True))
        with pytest.raises(ValueError, match="COLLECTION_SCOPE_INVALID"):
            read_collection_scope(target)
    target.write_text("{not json")
    with pytest.raises(ValueError, match="COLLECTION_SCOPE_INVALID"):
        read_collection_scope(target)


def test_a_diagnostic_scope_cannot_be_relabelled_formal(tmp_path):
    """A copied directory with one edited word must not become formal evidence.

    Rewriting `mode` alone leaves a structurally valid document, so the reader refuses it only when
    the caller states the mode it expects — which is how the audit/seal/QC/result hash chain will
    bind the identity this milestone ran under.
    """

    scope = build_collection_scope(CollectionMode.DIAGNOSTIC, scene_id="default", seed=0,
                                   inputs_sha256=INPUTS_SHA)
    target = tmp_path / "collection-scope.json"
    write_collection_scope(scope, target)
    relabelled = dict(scope, mode="formal")
    target.write_text(json.dumps(relabelled, sort_keys=True))
    assert read_collection_scope(target)["mode"] == "formal"
    with pytest.raises(ValueError, match="COLLECTION_SCOPE_INVALID"):
        read_collection_scope(target, expected_mode=CollectionMode.DIAGNOSTIC)
    assert read_collection_scope(target, expected_mode=CollectionMode.FORMAL)["mode"] == "formal"


def test_scope_document_cannot_be_overwritten(tmp_path):
    scope = build_collection_scope(CollectionMode.DIAGNOSTIC, scene_id="default", seed=0,
                                   inputs_sha256=INPUTS_SHA)
    target = tmp_path / "collection-scope.json"
    write_collection_scope(scope, target)
    original = target.read_bytes()
    with pytest.raises(ValueError, match="COLLECTION_SCOPE_ALREADY_WRITTEN"):
        write_collection_scope(scope, target)
    assert target.read_bytes() == original


def test_scope_document_rejects_missing_inputs_binding(tmp_path):
    for bad in (None, "", "a" * 63, "A" * 64, "z" * 64):
        with pytest.raises(ValueError, match="COLLECTION_SCOPE_INVALID"):
            build_collection_scope(CollectionMode.DIAGNOSTIC, scene_id="default", seed=0,
                                   inputs_sha256=bad)
    for bad_scene, bad_seed in (("", 0), ("default", -1), ("default", True), ("default", 0.0)):
        with pytest.raises(ValueError, match="COLLECTION_SCOPE_INVALID"):
            build_collection_scope(CollectionMode.DIAGNOSTIC, scene_id=bad_scene, seed=bad_seed,
                                   inputs_sha256=INPUTS_SHA)
    with pytest.raises(ValueError, match="COLLECTION_MODE_UNKNOWN"):
        build_collection_scope("diagnostic", scene_id="default", seed=0, inputs_sha256=INPUTS_SHA)


# ---------------------------------------------------------------------------
# non-Head safety gate: every non-Head check is required, the Head ones are not
# ---------------------------------------------------------------------------

NONHEAD_MEASUREMENTS = {
    "path_step_s": 0.01, "path_clearance_m": 0.002, "max_age_s": 0.1, "max_skew_s": 0.05,
    "velocity_limit_rad_s": [0.25] * 6, "acceleration_limit_rad_s2": [0.5] * 6,
    "submit_lead_s": 0.05, "stop_velocity_rad_s": 0.01, "stop_latency_s": 0.5,
    "grasp_occlusion_window_s": 0.5, "support_distance_m": 0.01, "release_stable_s": 0.5,
    "retreat_distance_m": 0.05, "placement_stable_s": 0.5,
}
NONHEAD_CHECKS = ("collision", "synchronization", "execution", "release", "retreat")
ALL_CHECKS = ("fov", "collision", "search", "synchronization", "execution", "release", "retreat")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _calibration_document(tmp_path, *, checks=None, status="CALIBRATION_REQUIRED"):
    from so101_demo.act.calibration import REQUIRED_MEASUREMENTS

    sample = tmp_path / "calibration-sample.json"
    if not sample.exists():
        sample.write_text(json.dumps({"kind": "head_search_qualification", "status": "PASS"}))
    sample_sha = hashlib.sha256(sample.read_bytes()).hexdigest()
    measurements = {}
    for name, value in NONHEAD_MEASUREMENTS.items():
        unit, _size = REQUIRED_MEASUREMENTS[name]
        measurements[name] = {"value": value, "unit": unit, "sample_path": str(sample),
                              "sample_sha256": sample_sha}
    resolved = {name: "UNMEASURED" for name in ALL_CHECKS}
    resolved.update({name: "PASS" for name in NONHEAD_CHECKS})
    if checks is not None:
        resolved = dict(resolved, **checks)
    return {"schema_version": 1, "status": status, "source_commit": SOURCE_COMMIT,
            "config_sha256": CONFIG_SHA, "source_provenance_sha256": "c" * 64,
            "measurements": measurements, "checks": resolved}


def test_nonhead_gate_accepts_a_report_without_head_search_measurements(tmp_path):
    report = _calibration_document(tmp_path)
    assert report["checks"]["fov"] == "UNMEASURED" and report["checks"]["search"] == "UNMEASURED"
    assert require_nonhead_gate(report, source_commit=SOURCE_COMMIT,
                                config_sha256=CONFIG_SHA)["status"] == "CALIBRATION_REQUIRED"


def test_nonhead_gate_refuses_any_unmeasured_nonhead_check(tmp_path):
    for name in NONHEAD_CHECKS:
        report = _calibration_document(tmp_path, checks={name: "UNMEASURED"})
        with pytest.raises(ValueError, match="NONHEAD_SAFETY_NOT_READY"):
            require_nonhead_gate(report)


def test_nonhead_gate_refuses_a_pass_without_its_measurements(tmp_path):
    report = _calibration_document(tmp_path)
    del report["measurements"]["path_step_s"]
    with pytest.raises(ValueError, match="NONHEAD_SAFETY_NOT_READY"):
        require_nonhead_gate(report)
    report = _calibration_document(tmp_path)
    report["measurements"]["path_step_s"]["sample_sha256"] = "d" * 64
    with pytest.raises(ValueError, match="NONHEAD_SAFETY_NOT_READY"):
        require_nonhead_gate(report)


def test_nonhead_gate_refuses_a_drifting_identity_or_missing_provenance(tmp_path):
    report = _calibration_document(tmp_path)
    with pytest.raises(ValueError, match="CALIBRATION_SOURCE_CONFIG_MISMATCH"):
        require_nonhead_gate(report, source_commit="f" * 40)
    with pytest.raises(ValueError, match="CALIBRATION_SOURCE_CONFIG_MISMATCH"):
        require_nonhead_gate(report, config_sha256="f" * 64)
    broken = _calibration_document(tmp_path)
    del broken["source_provenance_sha256"]
    with pytest.raises(ValueError, match="NONHEAD_SAFETY_NOT_READY"):
        require_nonhead_gate(broken)
    with pytest.raises(ValueError, match="NONHEAD_SAFETY_NOT_READY"):
        require_nonhead_gate({"status": "QUALIFIED"})


# ---------------------------------------------------------------------------
# freezing: one approved candidate per role, copied once and hashed
# ---------------------------------------------------------------------------

def _proposal_and_receipt(root, *, model_sha="1" * 64, tag=""):
    payload = {
        "schema_version": 1, "policy_id": "synthetic-first-episode", "thresholds": {
            "minimum_bilateral_force_n": 0.1, "maximum_compression_distance_m": 0.001,
            "maximum_safe_force_n": 2.0, "maximum_hold_linear_speed_m_s": 0.01,
            "minimum_stable_hold_duration_s": 0.1},
        "evaluation": {"maximum_observation_age_s": 0.2, "minimum_consecutive_samples": 2},
        "allowed_other_contact_bodies": [], "mujoco_version": "3.12.0",
        "model_sha256": model_sha, "scene_sha256": "2" * 64, "motion_policy_sha256": "3" * 64,
        "source_evidence_sha256": "4" * 64, "collector_sha256": "5" * 64,
        "live_collector_sha256": "6" * 64, "analyzer_sha256": "7" * 64, "config_sha256": "8" * 64}
    fingerprint = hashlib.sha256(_canonical(payload)).hexdigest()
    regimes = ("no_contact", "bilateral_touch", "over_compression", "micro_lift_slip",
               "stable_hold")
    proposal = {
        "status": "DISABLED", "payload": payload, "policy_fingerprint": fingerprint,
        "source_evidence_sha256": payload["source_evidence_sha256"],
        "counts": {name: {"offline": 20, "live": 5} for name in regimes},
        "negative_controls": {"table_only": ["no_contact"], "post_release": ["no_contact"],
                              "left_only": ["left_only"], "right_only": ["right_only"]},
        "confusion_matrix": {name: {name: 5} for name in regimes},
        "false_positive_rate": 0, "false_negative_rate": 0}
    proposal["proposal_sha256"] = hashlib.sha256(_canonical(proposal)).hexdigest()
    receipt = {"policy_fingerprint": fingerprint,
               "source_evidence_sha256": payload["source_evidence_sha256"],
               "approved_by": "user", "approval_reference": "synthetic-test-approval",
               "approved_at": "2026-09-25T00:00:00+00:00", "evidence_root": str(root)}
    proposal_path = root / f"proposal{tag}.json"
    receipt_path = root / f"activation{tag}.json"
    proposal_path.write_bytes(_canonical(proposal))
    receipt_path.write_bytes(_canonical(receipt))
    return proposal_path, receipt_path


def _entry(path, approval="source_controlled"):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "approved": True, "approval": approval}


def _registry(tmp_path):
    """One approved candidate per role, with the two evidence-bound roles verified for real."""

    source_root = tmp_path / "source"
    source_root.mkdir(exist_ok=True)
    proposal_path, receipt_path = _proposal_and_receipt(tmp_path)
    calibration = tmp_path / "calibration-nonhead.json"
    calibration.write_bytes(_canonical(_calibration_document(tmp_path)))
    roles = {}
    for role in INPUT_ROLES:
        if role == "contact_proposal":
            entry = {"path": str(proposal_path),
                     "sha256": hashlib.sha256(proposal_path.read_bytes()).hexdigest(),
                     "approved": True, "approval": "disabled_proposal"}
        elif role == "contact_activation":
            entry = {"path": str(receipt_path),
                     "sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
                     "approved": True, "approval": "user_activation"}
        elif role in ("path_policy", "placement_qc", "rgb_skew"):
            entry = {"path": str(calibration),
                     "sha256": hashlib.sha256(calibration.read_bytes()).hexdigest(),
                     "approved": True, "approval": "nonhead_calibration"}
        else:
            path = source_root / f"{role}.json"
            if not path.exists():
                path.write_bytes(_canonical({"role": role}))
            entry = _entry(path)
        roles[role] = {"status": "READY", "candidates": [entry], "selected": entry,
                       "identity": None, "blocker": None}
    roles["scene_model"]["identity"] = {"model_sha256": "1" * 64, "scene_sha256": "2" * 64,
                                        "mujoco_version": "3.12.0"}
    return {"kind": CANDIDATES_KIND, "schema_version": 1, "source_root": str(source_root),
            "source_commit": SOURCE_COMMIT, "evidence_root": str(tmp_path), "roles": roles}


def _write_registry(tmp_path, registry):
    path = tmp_path / "input-candidates.json"
    path.write_bytes(_canonical(registry))
    return path


def test_freeze_copies_one_verified_candidate_per_role(tmp_path):
    registry = _registry(tmp_path)
    candidates = _write_registry(tmp_path, registry)
    manifest_path = freeze_inputs(candidates, tmp_path / "inputs")
    assert manifest_path == tmp_path / "inputs" / "inputs-manifest.json"
    manifest = read_inputs_manifest(manifest_path)
    assert manifest["kind"] == MANIFEST_KIND
    assert set(manifest["roles"]) == set(INPUT_ROLES)
    for role, item in manifest["roles"].items():
        copied = tmp_path / "inputs" / item["path"]
        assert copied.is_file(), role
        assert hashlib.sha256(copied.read_bytes()).hexdigest() == item["sha256"]
    assert read_candidate_registry(candidates) == registry
    # the frozen digest covers the copied bytes, so it is stable across a second freeze
    again = freeze_inputs(candidates, tmp_path / "inputs-again")
    assert read_inputs_manifest(again)["inputs_sha256"] == manifest["inputs_sha256"]


def test_freeze_refuses_a_missing_or_unselected_role(tmp_path):
    registry = _registry(tmp_path)
    del registry["roles"]["path_policy"]
    with pytest.raises(ValueError, match="NONHEAD_INPUT_BINDING_REQUIRED"):
        freeze_inputs(_write_registry(tmp_path, registry), tmp_path / "inputs")
    registry = _registry(tmp_path)
    registry["roles"]["reset_recipe"]["selected"] = None
    with pytest.raises(ValueError, match="NONHEAD_INPUT_BINDING_REQUIRED"):
        freeze_inputs(_write_registry(tmp_path, registry), tmp_path / "inputs")
    registry = _registry(tmp_path)
    registry["roles"]["reset_recipe"]["status"] = "MISSING"
    with pytest.raises(ValueError, match="NONHEAD_INPUT_BINDING_REQUIRED"):
        freeze_inputs(_write_registry(tmp_path, registry), tmp_path / "inputs")


def test_freeze_refuses_ambiguity_and_unapproved_candidates(tmp_path):
    registry = _registry(tmp_path)
    role = registry["roles"]["anchor_scene"]
    role["candidates"] = role["candidates"] + [dict(role["selected"])]
    with pytest.raises(ValueError, match="INPUT_CANDIDATE_AMBIGUOUS"):
        freeze_inputs(_write_registry(tmp_path, registry), tmp_path / "inputs")
    registry = _registry(tmp_path)
    registry["roles"]["anchor_scene"]["selected"]["approved"] = False
    with pytest.raises(ValueError, match="INPUT_NOT_APPROVED"):
        freeze_inputs(_write_registry(tmp_path, registry), tmp_path / "inputs")
    registry = _registry(tmp_path)
    registry["roles"]["anchor_scene"]["selected"]["approval"] = "trust-me"
    with pytest.raises(ValueError, match="INPUT_NOT_APPROVED"):
        freeze_inputs(_write_registry(tmp_path, registry), tmp_path / "inputs")


def test_freeze_refuses_a_stale_activation_or_identity_mismatch(tmp_path):
    registry = _registry(tmp_path)
    receipt = json.loads(Path(registry["roles"]["contact_activation"]["selected"]["path"]).read_text())
    receipt["policy_fingerprint"] = "e" * 64
    stale = tmp_path / "stale-activation.json"
    stale.write_bytes(_canonical(receipt))
    registry["roles"]["contact_activation"]["selected"] = _entry(stale, "user_activation")
    registry["roles"]["contact_activation"]["candidates"] = [_entry(stale, "user_activation")]
    with pytest.raises(ValueError, match="INPUT_ACTIVATION_STALE"):
        freeze_inputs(_write_registry(tmp_path, registry), tmp_path / "inputs")
    registry = _registry(tmp_path)
    registry["roles"]["scene_model"]["identity"]["model_sha256"] = "9" * 64
    with pytest.raises(ValueError, match="INPUT_IDENTITY_MISMATCH"):
        freeze_inputs(_write_registry(tmp_path, registry), tmp_path / "inputs")
    # a policy that is internally consistent but was activated for another model is still refused
    registry = _registry(tmp_path)
    other_proposal, other_receipt = _proposal_and_receipt(tmp_path, model_sha="9" * 64, tag="-other")
    registry["roles"]["contact_proposal"]["selected"] = _entry(other_proposal, "disabled_proposal")
    registry["roles"]["contact_proposal"]["candidates"] = [_entry(other_proposal, "disabled_proposal")]
    registry["roles"]["contact_activation"]["selected"] = _entry(other_receipt, "user_activation")
    registry["roles"]["contact_activation"]["candidates"] = [_entry(other_receipt, "user_activation")]
    with pytest.raises(ValueError, match="INPUT_IDENTITY_MISMATCH"):
        freeze_inputs(_write_registry(tmp_path, registry), tmp_path / "inputs")


def test_freeze_refuses_a_changed_source_candidate_and_an_existing_output(tmp_path):
    registry = _registry(tmp_path)
    victim = Path(registry["roles"]["reset_recipe"]["selected"]["path"])
    victim.write_bytes(b"changed after inspection")
    with pytest.raises(ValueError, match="INPUT_IDENTITY_MISMATCH"):
        freeze_inputs(_write_registry(tmp_path, registry), tmp_path / "inputs")
    registry = _registry(tmp_path)
    (tmp_path / "inputs").mkdir()
    with pytest.raises(ValueError, match="INPUT_OUTPUT_EXISTS"):
        freeze_inputs(_write_registry(tmp_path, registry), tmp_path / "inputs")


def test_inputs_manifest_is_closed_and_read_back_strictly(tmp_path):
    candidates = _write_registry(tmp_path, _registry(tmp_path))
    manifest_path = freeze_inputs(candidates, tmp_path / "inputs")
    manifest = read_inputs_manifest(manifest_path)
    for mutation in ({"kind": "OTHER"}, {"schema_version": 2}, {"extra": 1}):
        broken = dict(manifest, **mutation)
        manifest_path.write_bytes(_canonical(broken))
        with pytest.raises(ValueError, match="INPUTS_MANIFEST_INVALID"):
            read_inputs_manifest(manifest_path)
    manifest_path.write_bytes(b"{not json")
    with pytest.raises(ValueError, match="INPUTS_MANIFEST_INVALID"):
        read_inputs_manifest(manifest_path)
# ---------------------------------------------------------------------------
# the real worktree: the frozen initial state, and the blockers that exist today
# ---------------------------------------------------------------------------

WORKTREE = Path(__file__).resolve().parents[3]
BLOCKER_CODES = {"NONHEAD_INPUT_BINDING_REQUIRED", "INPUT_CANDIDATE_AMBIGUOUS", "INPUT_NOT_APPROVED",
                 "INPUT_IDENTITY_MISMATCH", "INPUT_ACTIVATION_STALE"}


def _real_registry(tmp_path):
    """Inspect this worktree read-only; skip where the registered evidence root is absent."""

    ledger = WORKTREE / "docs/experiments/so101-act-data-experiment-ledger.md"
    if not ledger.is_file() or not Path("/data/work/so101-evidence").is_dir():
        pytest.skip("requires the ai-station worktree and its registered evidence root")
    document = inspect_inputs(WORKTREE, ledger)
    path = tmp_path / "input-candidates.json"
    path.write_bytes(_canonical(document))
    return document, path


def test_inspect_inputs_freezes_the_plan_anchor_and_the_installed_scene(tmp_path):
    document, _ = _real_registry(tmp_path)
    assert set(document) == {"kind", "schema_version", "source_root", "source_commit",
                             "evidence_root", "roles"}
    assert document["kind"] == CANDIDATES_KIND
    assert set(document["roles"]) == set(INPUT_ROLES)
    # the milestone's frozen initial state, taken from the checked-in anchor file (EXP-115)
    anchor = document["roles"]["anchor_scene"]["identity"]
    assert anchor["scene_id"] == "default"
    assert anchor["seed"] == 0
    assert anchor["cup_start_m"] == [0.02, -0.28, 0.165]
    assert anchor["neck_start_rad"] == 0.1
    # and the scene identity is the compiled model the activated policy names, not the XML text
    scene = document["roles"]["scene_model"]["identity"]
    assert set(scene) == {"model_sha256", "scene_sha256", "mujoco_version"}
    assert document["roles"]["scene_model"]["status"] in ("READY", "UNAPPROVED",
                                                          "IDENTITY_MISMATCH")


def test_inspect_inputs_never_defaults_a_missing_value(tmp_path):
    """Every role that is not READY names the blocker a freeze would raise, in a closed code set."""

    document, candidates = _real_registry(tmp_path)
    for role, item in document["roles"].items():
        if item["status"] == "READY":
            assert item["selected"] is not None and item["blocker"] is None, role
        else:
            assert item["blocker"] in BLOCKER_CODES, role
            assert item["selected"] is None, role
    blockers = [item["blocker"] for item in document["roles"].values()
                if item["status"] != "READY"]
    if blockers:
        with pytest.raises(ValueError) as error:
            freeze_inputs(candidates, tmp_path / "inputs")
        assert str(error.value) in blockers


# ---------------------------------------------------------------------------
# the collection boundary: a diagnostic record is never training evidence
# ---------------------------------------------------------------------------

def test_a_diagnostic_collection_record_is_never_trainable():
    """A diagnostic episode can be really committed and still must not enter training."""

    from so101_demo.act.collection import training_eligible

    def record(**overrides):
        base = {"status": "PASSED", "qc": "PASS", "done": True, "interventions": 0,
                "coordinator_committed": True, "collection_mode": "formal"}
        base.update(overrides)
        return base

    assert training_eligible(record())
    assert not training_eligible(record(collection_mode="preselected_target_diagnostic"))
    assert not training_eligible(record(collection_mode="unknown"))
    assert not training_eligible(record(collection_mode=None))
    # a record that carries no mode at all keeps the pre-existing record-level semantics; the
    # exporter boundary that refuses a missing mode is Task 4's
    assert training_eligible({key: value for key, value in record().items()
                              if key != "collection_mode"})
