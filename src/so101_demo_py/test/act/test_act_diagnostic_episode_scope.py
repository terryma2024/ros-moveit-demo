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
from so101_demo.act.diagnostic_episode_inputs import (
    CANDIDATES_KIND,
    INPUT_ROLES,
    MANIFEST_KIND,
    freeze_inputs,
    inspect_inputs,
    read_candidate_registry,
    read_inputs_manifest,
    require_nonhead_gate,
    verify_frozen_inputs,
)
from paths import REPOSITORY

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


def test_unicode_common_scope_keeps_the_exact_audit_payload_bytes(tmp_path):
    from so101_demo.act.episode_audit import EpisodeAuditWriter
    scope = build_collection_scope("preselected_target_diagnostic", scene_id="场景", seed=0,
                                   inputs_sha256=INPUTS_SHA)
    target = tmp_path / "collection-scope.json"
    write_collection_scope(scope, target)
    writer = EpisodeAuditWriter(tmp_path / "episode", scope,
        {"session_id": "session", "attempt_id": "attempt", "reset_epoch": 1, "release_epoch": 0,
         "mode": scope["mode"], "scene_id": scope["scene_id"], "seed": 0},
        {"inputs_sha256": INPUTS_SHA})
    try:
        assert target.read_bytes() == writer.files.source.read_bytes()
    finally:
        for stream in writer._streams.values():
            stream.close()


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


def _calibration_document(tmp_path, *, checks=None, status="CALIBRATION_REQUIRED",
                          config_sha=CONFIG_SHA):
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
            "config_sha256": config_sha, "source_provenance_sha256": "c" * 64,
            "measurements": measurements, "checks": resolved}


def test_nonhead_gate_accepts_a_report_without_head_search_measurements(tmp_path):
    report = _calibration_document(tmp_path)
    assert report["checks"]["fov"] == "UNMEASURED" and report["checks"]["search"] == "UNMEASURED"
    assert require_nonhead_gate(report)["status"] == "CALIBRATION_REQUIRED"


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


def test_nonhead_gate_records_the_identity_but_requires_provenance_and_shape(tmp_path):
    """CP-1928: a report measured for another revision is still usable, but must be well formed."""

    for field, other in (("source_commit", "f" * 40), ("config_sha256", "f" * 64)):
        moved = _calibration_document(tmp_path)
        moved[field] = other
        assert require_nonhead_gate(moved)["status"] == "CALIBRATION_REQUIRED"
    malformed = _calibration_document(tmp_path)
    malformed["source_commit"] = "not-a-commit"
    with pytest.raises(ValueError, match="NONHEAD_SAFETY_NOT_READY"):
        require_nonhead_gate(malformed)
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


PROFILE_FILES = {
    "assets/mujoco/act/scene.xml": b"<mujoco><worldbody/></mujoco>\n",
    "config/mujoco/act/policy.json": b"{\"kind\": \"ACT_PROFILE\"}\n",
}


def _derived_config_sha(source_root) -> str:
    """The ACT profile digest of a synthetic source tree, computed like the production rule."""

    package = Path(source_root) / "src/so101_demo_py"
    files = {}
    for relative, payload in PROFILE_FILES.items():
        path = package / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(payload)
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashlib.sha256(json.dumps(files, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


ANCHOR_YAML = (b"schema_version: 1\nmeasurement_experiment: EXP-115\nanchors:\n"
               b"  default:\n    cup_start_m: [0.02, -0.28, 0.165]\n    neck_start_rad: 0.1\n")
RUNTIME_YAML = (b"start_guard:\n  timeout_s: 2.0\n  cpu_busy_warn_fraction: 0.9\n"
                b"  ram_minimum_bytes: 1073741824\n  ram_minimum_fraction: 0.05\n"
                b"  gpu_minimum_bytes: 1073741824\nhard_stops:\n  rtf_min: 0.5\n"
                b"  disk_free_min_bytes: 5368709120\n")
COLLECTION_YAML = (b"recorder:\n  sample_rate_hz: 10\n  queue_capacity_samples: 16\n"
                   b"  queue_high_watermark_samples: 12\n"
                   b"  queue_recovery_watermark_samples: 8\n"
                   b"  queue_high_watermark_hold_s: 0.2\n  lossless: true\n")


def _derived_anchor_identity(payload: bytes) -> dict:
    import yaml

    document = yaml.safe_load(payload)
    anchor = document["anchors"]["default"]
    return {"scene_id": "default", "seed": 0,
            "cup_start_m": [float(value) for value in anchor["cup_start_m"]],
            "neck_start_rad": float(anchor["neck_start_rad"]),
            "anchor_file_sha256": hashlib.sha256(payload).hexdigest(),
            "measurement_experiment": document.get("measurement_experiment")}


def _derived_resource_identity(runtime_bytes: bytes, collection_bytes: bytes) -> dict:
    """The same shape the gate derives; tolerant of broken bytes so a negative case can be built."""

    import yaml

    runtime = yaml.safe_load(runtime_bytes) or {}
    guard = runtime.get("start_guard") or {}
    hard = runtime.get("hard_stops") or {}
    recorder = (yaml.safe_load(collection_bytes) or {}).get("recorder") or {}
    return {"start_guard": {key: guard.get(key) for key in
                            ("timeout_s", "cpu_busy_warn_fraction", "ram_minimum_bytes",
                             "ram_minimum_fraction", "gpu_minimum_bytes")},
            "rtf_hard_stop": hard.get("rtf_min"),
            "disk_hard_stop": hard.get("disk_free_min_bytes"),
            "queue_hard_stop": {"queue_capacity_samples": recorder.get("queue_capacity_samples"),
                                "queue_high_watermark_samples": recorder.get("queue_high_watermark_samples"),
                                "queue_recovery_watermark_samples": recorder.get("queue_recovery_watermark_samples"),
                                "queue_high_watermark_hold_s": recorder.get("queue_high_watermark_hold_s"),
                                "lossless": recorder.get("lossless"),
                                "sample_rate_hz": recorder.get("sample_rate_hz"),
                                "source": "collection_config.recorder"},
            "runtime_config_sha256": hashlib.sha256(runtime_bytes).hexdigest(),
            "collection_config_sha256": hashlib.sha256(collection_bytes).hexdigest()}


def _registry(tmp_path, *, contents=None):
    """One approved candidate per role, with the evidence-bound roles built as the real gate reads
    them: the anchor and the resource policy are derived from the bytes their roles carry.
    """

    source_root = tmp_path / "source"
    source_root.mkdir(exist_ok=True)
    config_sha = _derived_config_sha(source_root)
    supplied = dict(contents or {})
    supplied.setdefault("anchor_scene", ANCHOR_YAML)
    supplied.setdefault("runtime_config", RUNTIME_YAML)
    supplied.setdefault("collection_config", COLLECTION_YAML)
    proposal_path, receipt_path = _proposal_and_receipt(tmp_path)
    calibration = tmp_path / "calibration-nonhead.json"
    calibration.write_bytes(_canonical(_calibration_document(tmp_path, config_sha=config_sha)))
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
            suffix = ".yaml" if role in ("anchor_scene", "runtime_config", "collection_config",
                                         "resource_thresholds") else ".json"
            path = source_root / f"{role}{suffix}"
            payload = supplied.get(role)
            if payload is not None:
                path.write_bytes(payload)
            elif not path.exists():
                path.write_bytes(_canonical({"role": role}))
            entry = _entry(path)
        roles[role] = {"status": "READY", "candidates": [entry], "selected": entry,
                       "identity": None, "blocker": None}
    roles["scene_model"]["identity"] = {"model_sha256": "1" * 64, "scene_sha256": "2" * 64,
                                        "mujoco_version": "3.12.0"}
    roles["anchor_scene"]["identity"] = _derived_anchor_identity(supplied["anchor_scene"])
    # the inspector points the resource role at the runtime config it derives the policy from
    runtime_entry = roles["runtime_config"]["selected"]
    roles["resource_thresholds"]["selected"] = dict(runtime_entry)
    roles["resource_thresholds"]["candidates"] = [dict(runtime_entry)]
    roles["resource_thresholds"]["identity"] = _derived_resource_identity(
        supplied["runtime_config"], supplied["collection_config"])
    return {"kind": CANDIDATES_KIND, "schema_version": 1, "source_root": str(source_root),
            "source_commit": SOURCE_COMMIT, "config_sha256": config_sha,
            "evidence_root": str(tmp_path), "roles": roles}


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
    assert manifest["schema_version"] == 2
    # a version 1 manifest, or one still carrying the retired broker roles, is refused rather than read silently
    for mutation in ({"kind": "OTHER"}, {"schema_version": 1}, {"schema_version": 3}, {"extra": 1},
                     {"broker" + "_stop_policy": {"path": "p", "sha256": "0" * 64, "bytes": 1}},
                     {"teacher_bound" + "_timing": {"path": "p", "sha256": "0" * 64, "bytes": 1}}):
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

WORKTREE = REPOSITORY
BLOCKER_CODES = {"NONHEAD_INPUT_BINDING_REQUIRED", "INPUT_CANDIDATE_AMBIGUOUS", "INPUT_NOT_APPROVED",
                 "INPUT_IDENTITY_MISMATCH", "INPUT_ACTIVATION_STALE"}


def _real_registry(tmp_path):
    """Inspect this checkout read-only; the ledger is a tracked file, so this runs on any machine."""

    ledger = WORKTREE / "docs/experiments/so101-act-data-experiment-ledger.md"
    assert ledger.is_file(), "the tracked ACT ledger is part of every checkout"
    document = inspect_inputs(WORKTREE, ledger)
    path = tmp_path / "input-candidates.json"
    path.write_bytes(_canonical(document))
    return document, path


def test_inspect_inputs_freezes_the_plan_anchor_and_the_installed_scene(tmp_path):
    document, _ = _real_registry(tmp_path)
    assert set(document) == {"kind", "schema_version", "source_root", "source_commit",
                             "config_sha256", "evidence_root", "roles"}
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


def test_freeze_accepts_the_production_input_formats(tmp_path):
    """The real inputs are YAML, XML and Python; only the policy roles carry a JSON contract."""

    registry = _registry(tmp_path, contents={
        "scene_model": b"<mujoco><worldbody><body name='cup'/></worldbody></mujoco>\n",
        "reset_recipe": b"def pick_place_reset_targets(model, manifest, request):\n    return None\n",
        "reference_interpolation": b"class MoveItExpertActionTap:\n    def reference(self, at_s):\n        return at_s\n",
        "anchor_scene": (b"schema_version: 1\nmeasurement_experiment: EXP-115\nanchors:\n"
                         b"  default:\n    cup_start_m: [0.02, -0.28, 0.165]\n    neck_start_rad: 0.1\n"),
        "runtime_config": (b"start_guard:\n  timeout_s: 2.0\n  cpu_busy_warn_fraction: 0.9\n"
                           b"  ram_minimum_bytes: 1073741824\n  ram_minimum_fraction: 0.05\n"
                           b"  gpu_minimum_bytes: 1073741824\nhard_stops:\n  rtf_min: 0.5\n"
                           b"  disk_free_min_bytes: 5368709120\n"),
        "collection_config": (b"recorder:\n  sample_rate_hz: 10\n  queue_capacity_samples: 16\n"
                              b"  queue_high_watermark_samples: 12\n"
                              b"  queue_recovery_watermark_samples: 8\n"
                              b"  queue_high_watermark_hold_s: 0.2\n  lossless: true\n"),
    })
    manifest_path = freeze_inputs(_write_registry(tmp_path, registry), tmp_path / "inputs")
    manifest = read_inputs_manifest(manifest_path)
    frozen = manifest_path.parent / manifest["roles"]["scene_model"]["path"]
    assert frozen.read_bytes().startswith(b"<mujoco>")
    anchor = manifest_path.parent / manifest["roles"]["anchor_scene"]["path"]
    assert anchor.read_bytes().startswith(b"schema_version")


def test_frozen_bytes_are_re_verified_not_just_described(tmp_path):
    """A self-consistent manifest must not satisfy admission once its files are gone or changed."""

    manifest_path = freeze_inputs(_write_registry(tmp_path, _registry(tmp_path)),
                                  tmp_path / "inputs")
    manifest = read_inputs_manifest(manifest_path)
    verify_frozen_inputs(manifest_path)
    victim = manifest_path.parent / manifest["roles"]["path_policy"]["path"]

    original = victim.read_bytes()
    victim.unlink()
    with pytest.raises(ValueError, match="INPUTS_FROZEN_BYTES_INVALID"):
        verify_frozen_inputs(manifest_path)

    victim.write_bytes(original + b"\n")
    with pytest.raises(ValueError, match="INPUTS_FROZEN_BYTES_INVALID"):
        verify_frozen_inputs(manifest_path)

    victim.unlink()
    victim.symlink_to(tmp_path / "elsewhere.json")
    (tmp_path / "elsewhere.json").write_bytes(original)
    with pytest.raises(ValueError, match="INPUTS_FROZEN_BYTES_INVALID"):
        verify_frozen_inputs(manifest_path)
    assert read_inputs_manifest(manifest_path)["inputs_sha256"] == manifest["inputs_sha256"]


def test_freeze_copies_the_verified_bytes_not_a_second_read(tmp_path, monkeypatch):
    """A candidate replaced between verification and copying must not become the frozen input."""

    from so101_demo.act import diagnostic_episode_inputs

    registry = _registry(tmp_path)
    victim = Path(registry["roles"]["reset_recipe"]["selected"]["path"])
    original = victim.read_bytes()
    real_verify = diagnostic_episode_inputs._verify_roles

    def racing_verify(document, **kwargs):
        payloads = real_verify(document, **kwargs)
        victim.write_bytes(b"replaced after verification\n")
        return payloads

    monkeypatch.setattr(diagnostic_episode_inputs, "_verify_roles", racing_verify)
    manifest_path = freeze_inputs(_write_registry(tmp_path, registry), tmp_path / "inputs")
    manifest = read_inputs_manifest(manifest_path)
    frozen = manifest_path.parent / manifest["roles"]["reset_recipe"]["path"]
    assert frozen.read_bytes() == original
    assert manifest["roles"]["reset_recipe"]["sha256"] == hashlib.sha256(original).hexdigest()
    verify_frozen_inputs(manifest_path)


def test_freeze_refuses_an_anchor_the_bytes_do_not_describe(tmp_path):
    """A registry may assert an anchor identity; the anchor file has to actually carry it."""

    # anchor bytes that do not carry the milestone's frozen anchor are an unbound input
    other_anchor = ANCHOR_YAML.replace(b"neck_start_rad: 0.1", b"neck_start_rad: 0.0")
    (tmp_path / "other").mkdir(parents=True, exist_ok=True)
    (tmp_path / "asserted").mkdir(parents=True, exist_ok=True)
    registry = _registry(tmp_path / "other", contents={"anchor_scene": other_anchor})
    with pytest.raises(ValueError, match="NONHEAD_INPUT_BINDING_REQUIRED"):
        freeze_inputs(_write_registry(tmp_path / "other", registry), tmp_path / "other-inputs")

    # valid anchor bytes with an asserted identity they do not describe are an identity mismatch
    registry = _registry(tmp_path / "asserted")
    registry["roles"]["anchor_scene"]["identity"] = dict(
        registry["roles"]["anchor_scene"]["identity"], scene_id="left", seed=1)
    with pytest.raises(ValueError, match="INPUT_IDENTITY_MISMATCH"):
        freeze_inputs(_write_registry(tmp_path / "asserted", registry), tmp_path / "asserted-inputs")


def test_freeze_refuses_a_ready_registry_without_the_resource_policy(tmp_path):
    """Reporting READY is not enforcement: the gate re-derives the policy from the config bytes."""

    for label, runtime in (("no-stops", RUNTIME_YAML.replace(b"hard_stops:", b"unrelated:")),
                           ("bool-stop", RUNTIME_YAML.replace(b"rtf_min: 0.5", b"rtf_min: false")),
                           ("zero-stop", RUNTIME_YAML.replace(b"rtf_min: 0.5", b"rtf_min: 0.0"))):
        case = tmp_path / label
        case.mkdir(parents=True, exist_ok=True)
        registry = _registry(case, contents={"runtime_config": runtime})
        assert registry["roles"]["resource_thresholds"]["status"] == "READY"
        with pytest.raises(ValueError, match="NONHEAD_INPUT_BINDING_REQUIRED"):
            freeze_inputs(_write_registry(case, registry), case / "inputs")

    for label, collection in (
            ("not-lossless", COLLECTION_YAML.replace(b"lossless: true", b"lossless: false")),
            ("bad-watermarks", COLLECTION_YAML.replace(b"queue_recovery_watermark_samples: 8",
                                                       b"queue_recovery_watermark_samples: 13")),
            ("wrong-rate", COLLECTION_YAML.replace(b"sample_rate_hz: 10", b"sample_rate_hz: 5"))):
        case = tmp_path / label
        case.mkdir(parents=True, exist_ok=True)
        registry = _registry(case, contents={"collection_config": collection})
        with pytest.raises(ValueError, match="NONHEAD_INPUT_BINDING_REQUIRED"):
            freeze_inputs(_write_registry(case, registry), case / "inputs")


def test_freeze_refuses_a_resource_role_that_owns_another_file(tmp_path):
    registry = _registry(tmp_path)
    other = registry["roles"]["collection_config"]["selected"]
    registry["roles"]["resource_thresholds"]["selected"] = dict(other)
    registry["roles"]["resource_thresholds"]["candidates"] = [dict(other)]
    with pytest.raises(ValueError, match="INPUT_IDENTITY_MISMATCH"):
        freeze_inputs(_write_registry(tmp_path, registry), tmp_path / "inputs")


def test_a_malformed_collection_mode_is_ineligible_not_a_raise():
    from so101_demo.act.collection import training_eligible

    record = {"status": "PASSED", "qc": "PASS", "done": True, "interventions": 0,
              "coordinator_committed": True, "collection_mode": "formal"}
    for malformed in ([], {}, 0, 1.0, True, object()):
        assert training_eligible(dict(record, collection_mode=malformed)) is False


def test_ledger_references_keep_absolute_and_relative_paths(tmp_path):
    """An absolute reference under the registered root must resolve to itself, not to a duplicate."""

    from so101_demo.act.diagnostic_episode_inputs import _ledger_referenced_json

    evidence = tmp_path / "evidence"
    (evidence / "experiments" / "run").mkdir(parents=True)
    absolute = evidence / "experiments" / "run" / "report.json"
    relative = evidence / "experiments" / "run" / "second.json"
    outside = tmp_path / "elsewhere" / "outside.json"
    outside.parent.mkdir()
    for path in (absolute, relative, outside):
        path.write_bytes(b"{}")
    ledger = tmp_path / "ledger.md"
    ledger.write_text(f"see {absolute}\nand experiments/run/second.json\nand {outside}\n")
    found = _ledger_referenced_json(ledger, evidence)
    assert absolute in found
    assert relative in found
    assert outside not in found


def test_resource_role_refuses_missing_hard_stops(tmp_path):
    """A start guard alone is not the resource policy: the plan also requires the stop points."""

    from so101_demo.act.diagnostic_episode_inputs import _inspect_resource_thresholds

    root = tmp_path / "source"
    (root / "src/so101_demo_py/config/act").mkdir(parents=True)
    (root / "src/so101_demo_py/config/mujoco").mkdir(parents=True)
    (root / "src/so101_demo_py/config/mujoco/parallel_batch_act_offline.yaml").write_bytes(RUNTIME_YAML)
    (root / "src/so101_demo_py/config/act/parallel_collection.yaml").write_bytes(COLLECTION_YAML)
    ready = _inspect_resource_thresholds(root)
    assert ready["status"] == "READY"
    assert ready["identity"]["rtf_hard_stop"] == 0.5
    assert ready["identity"]["queue_hard_stop"]["queue_high_watermark_samples"] == 12

    runtime = root / "src/so101_demo_py/config/mujoco/parallel_batch_act_offline.yaml"
    runtime.write_bytes(RUNTIME_YAML.replace(b"hard_stops:", b"unrelated:"))
    missing = _inspect_resource_thresholds(root)
    assert missing["status"] == "MISSING"
    assert missing["blocker"] == "NONHEAD_INPUT_BINDING_REQUIRED"

    for label, broken in (("bool stop", RUNTIME_YAML.replace(b"rtf_min: 0.5", b"rtf_min: false")),
                          ("zero stop", RUNTIME_YAML.replace(b"rtf_min: 0.5", b"rtf_min: 0.0"))):
        runtime.write_bytes(broken)
        assert _inspect_resource_thresholds(root)["status"] == "MISSING", label

    runtime.write_bytes(RUNTIME_YAML)
    collection = root / "src/so101_demo_py/config/act/parallel_collection.yaml"
    for label, broken in (("not lossless", COLLECTION_YAML.replace(b"lossless: true",
                                                                  b"lossless: false")),
                          ("bad watermark order",
                           COLLECTION_YAML.replace(b"queue_recovery_watermark_samples: 8",
                                                   b"queue_recovery_watermark_samples: 13")),
                          ("wrong rate", COLLECTION_YAML.replace(b"sample_rate_hz: 10",
                                                                 b"sample_rate_hz: 5"))):
        collection.write_bytes(broken)
        assert _inspect_resource_thresholds(root)["status"] == "MISSING", label


"""Task 1 of the non-head first-episode plan: explicit mode and closed scope binding.

The diagnostic mode replaces only target selection and the Head prerequisite. Robot, contact,
controller, reset, collision, holding, release, sampling and identity gates all still apply, so
these tests assert both directions: the diagnostic mode must not clear a non-Head safety gate, and
the formal mode must still require real Head qualification.
"""


def test_freeze_accepts_a_calibration_report_with_another_recorded_identity(tmp_path):
    """CP-1928: a report measured for another revision is frozen as-is, with its identity recorded."""

    registry = _registry(tmp_path)
    old_identity = tmp_path / "calibration-other-config.json"
    old_identity.write_bytes(_canonical(_calibration_document(tmp_path, config_sha="d" * 64)))
    entry = _entry(old_identity, "nonhead_calibration")
    registry["roles"]["placement_qc"]["selected"] = entry
    registry["roles"]["placement_qc"]["candidates"] = [entry]
    manifest_path = freeze_inputs(_write_registry(tmp_path, registry), tmp_path / "inputs")
    manifest = read_inputs_manifest(manifest_path)
    assert manifest["roles"]["placement_qc"]["sha256"] == entry["sha256"]
    assert manifest["roles"]["placement_qc"]["path"].endswith("calibration-other-config.json")


def test_freeze_accepts_two_distinct_approved_calibration_reports(tmp_path):
    """CP-1928 withdrew the one-report rule: each calibration role is validated on its own merits."""

    registry = _registry(tmp_path)
    other = tmp_path / "calibration-second.json"
    document = _calibration_document(tmp_path, config_sha=_derived_config_sha(tmp_path / "source"))
    other.write_bytes(_canonical(dict(document, note="a second report")))
    entry = _entry(other, "nonhead_calibration")
    registry["roles"]["rgb_skew"]["selected"] = entry
    registry["roles"]["rgb_skew"]["candidates"] = [entry]
    manifest_path = freeze_inputs(_write_registry(tmp_path, registry), tmp_path / "inputs")
    manifest = read_inputs_manifest(manifest_path)
    assert manifest["roles"]["rgb_skew"]["sha256"] == entry["sha256"]
    assert manifest["roles"]["rgb_skew"]["sha256"] != manifest["roles"]["path_policy"]["sha256"]


def test_freeze_accepts_an_identity_it_cannot_prove(tmp_path):
    """CP-1928: the registry's identity is recorded provenance; it is no longer proved live."""

    registry = _registry(tmp_path)
    registry["source_commit"] = "f" * 40
    registry["config_sha256"] = "f" * 64
    manifest_path = freeze_inputs(_write_registry(tmp_path, registry), tmp_path / "inputs")
    manifest = read_inputs_manifest(manifest_path)
    assert manifest["source_commit"] == "f" * 40
    assert manifest["config_sha256"] == "f" * 64


def test_ledger_references_reject_traversal_and_symlink_escapes(tmp_path):
    from so101_demo.act.diagnostic_episode_inputs import _ledger_referenced_json

    evidence = tmp_path / "evidence"
    (evidence / "experiments").mkdir(parents=True)
    inside = evidence / "experiments" / "report.json"
    inside.write_bytes(b"{}")
    traversal = evidence / ".." / "outside-report.json"
    (tmp_path / "outside-report.json").write_bytes(b"{}")
    outside = tmp_path / "elsewhere.json"
    outside.write_bytes(b"{}")
    link = evidence / "linked.json"
    link.symlink_to(outside)
    ledger = tmp_path / "ledger.md"
    ledger.write_text(f"see {inside}\nand {traversal}\nand {link}\n")
    # compare canonical paths: a lexical member of an unresolved set would hide the escape
    resolved = {path.resolve() for path in _ledger_referenced_json(ledger, evidence)}
    assert inside.resolve() in resolved
    assert traversal.resolve() not in resolved
    assert link.resolve() not in resolved
    assert outside.resolve() not in resolved
