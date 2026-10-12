"""The offline processor must bind actual frozen inputs and the full lease before creating evidence (opener: act.episode_open)."""

import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace

import pytest

from so101_demo.act.collection_scope import build_collection_scope, write_collection_scope
from so101_demo.act.diagnostic_episode_inputs import freeze_inputs
from so101_demo.act.episode_open import open_recorder_episode
from test_act_diagnostic_episode_scope import _registry, _write_registry
from paths import PACKAGE_ROOT, REPOSITORY


def _options(tmp_path, *, inputs=None, working=None):
    """The processor's own options for an attempt whose workspace is `working` (the reserved lease namespace)."""
    working = working or tmp_path / "worker" / "attempts" / "task_start" / "attempt" / "working"
    return SimpleNamespace(
        session_id="session", attempt_id="attempt", expected_reset_epoch=2, episode_root=working / "episode",
        evidence_root=working / "dynamic", episode_scope=tmp_path / "scope.json",
        episode_inputs_manifest=inputs if inputs is not None else tmp_path / "absent-inputs.json", fault="none",
        batch_id="batch", coordinator_epoch=3, worker_id="worker", worker_generation=4, point_id="task_start",
        lease_generation=5, lease_issued_monotonic_s=time.monotonic() - 1,
        lease_deadline_monotonic_s=time.monotonic() + 300)


def test_missing_frozen_manifest_refuses_before_creating_recorder(tmp_path):
    write_collection_scope(build_collection_scope("preselected_target_diagnostic", scene_id="default", seed=0,
                                                  inputs_sha256="a" * 64), tmp_path / "scope.json")
    options = _options(tmp_path)
    options.episode_inputs_manifest = None
    with pytest.raises(ValueError, match="EPISODE_FROZEN_INPUTS_REQUIRED"):
        open_recorder_episode(options)
    assert not options.evidence_root.exists()


def frozen_child_inputs(tmp_path, *, mode="preselected_target_diagnostic", scene_manifest=None, scope_scene=("default", 0)):
    """Synthetic approval/roles plus real frozen source/model for a Recorder boundary fixture.

    `scene_manifest` (a scenes file, formal `mode` only) is bound by the real `freeze_inputs`; `scope_scene` is the (scene_id, seed)
    of the `scope.json` this writes. The default call is the unchanged diagnostic fixture."""
    from so101_demo.act.execution_snapshot import freeze_execution_snapshot
    from so101_demo.act.contact_policy import policy_fingerprint
    config = PACKAGE_ROOT / "config/act"
    manifest_path = freeze_inputs(_write_registry(tmp_path, _registry(tmp_path)), tmp_path / "inputs",
                                 mode=mode, scene_manifest=scene_manifest,
                                 teacher_endpoint=config / "teacher_endpoint.yaml",
        teacher_execution_policy=config / "teacher_execution_policy.yaml",
        episode_recorder_policy=config / "episode_recorder.yaml",
                                 runtime_policy=config / "endpoint_pose_development_runtime.yaml")
    root = manifest_path.parent
    snapshot = freeze_execution_snapshot(REPOSITORY, root / "execution")
    document = json.loads(manifest_path.read_bytes())
    scene = (root / "execution" / snapshot["scene_path"]).read_bytes()
    role = document["roles"]["scene_model"]
    (root / role["path"]).write_bytes(scene)
    role.update(sha256=hashlib.sha256(scene).hexdigest(), bytes=len(scene), identity={
        "model_sha256": snapshot["model_sha256"], "scene_sha256": hashlib.sha256(scene).hexdigest(),
        "mujoco_version": snapshot["mujoco_version"]})
    proposal_role = document["roles"]["contact_proposal"]
    proposal = json.loads((root / proposal_role["path"]).read_bytes())
    proposal["payload"].update(role["identity"])
    fingerprint = policy_fingerprint(proposal["payload"])
    proposal["policy_fingerprint"] = fingerprint
    proposal["proposal_sha256"] = hashlib.sha256(json.dumps(
        {key: value for key, value in proposal.items() if key != "proposal_sha256"},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    activation_role = document["roles"]["contact_activation"]
    activation = json.loads((root / activation_role["path"]).read_bytes())
    activation["policy_fingerprint"] = fingerprint
    for entry, value in ((proposal_role, proposal), (activation_role, activation)):
        payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        (root / entry["path"]).write_bytes(payload)
        entry.update(sha256=hashlib.sha256(payload).hexdigest(), bytes=len(payload))
    from so101_demo.act.diagnostic_episode_inputs import execution_snapshot_binding
    document["execution_snapshot"] = execution_snapshot_binding(snapshot, root / "execution")
    bindings = {**document["roles"], **{key: document[key] for key in
                ("mode", "teacher_endpoint", "teacher_execution_policy",
                 "episode_recorder", "runtime_policy", "execution_snapshot", "scene_manifest") if key in document}}
    document["inputs_sha256"] = hashlib.sha256(json.dumps(bindings, sort_keys=True,
                                                           separators=(",", ":")).encode()).hexdigest()
    manifest_path.write_text(json.dumps(document))
    write_collection_scope(build_collection_scope(document["mode"], scene_id=scope_scene[0], seed=scope_scene[1],
                                                  inputs_sha256=document["inputs_sha256"]), tmp_path / "scope.json")
    return manifest_path, document, snapshot


def test_actual_recorder_binds_full_lease_frozen_bytes_and_own_episode_directory(tmp_path):
    manifest_path, manifest, snapshot = frozen_child_inputs(tmp_path)
    options = _options(tmp_path, inputs=manifest_path)
    episode = open_recorder_episode(options)
    try:
        root = options.episode_root
        assert root.is_dir() and root.name == "episode"
        identity = json.loads((root / "audit/episode.json").read_bytes())
        assert identity["lease"]["batch_id"] == options.batch_id
        assert identity["lease"]["lease_deadline_monotonic_s"] == options.lease_deadline_monotonic_s
        assert identity["release_epoch"] == 0
        assert identity["reset_epoch"] == 2 and identity["attempt_id"] == "attempt"
        frozen = json.loads((root / "audit/inputs.json").read_bytes())
        assert frozen == manifest
        assert episode.execution_inputs == snapshot
        assert episode.frozen_inputs_manifest == manifest_path
        assert episode.capture.recorder.provenance["source_sha256"] == snapshot["source_sha256"]
        assert episode.capture.recorder.provenance["scene_sha256"] == manifest["roles"]["scene_model"]["sha256"]
        assert not (options.evidence_root / "episode").exists()
    finally:
        episode.close()


@pytest.mark.parametrize("change", ["scope", "missing_lease", "expired_lease", "tampered_role", "unfrozen"])
def test_bad_binding_refuses_before_creating_episode(tmp_path, change):
    manifest_path, manifest, _ = frozen_child_inputs(tmp_path)
    options = _options(tmp_path, inputs=manifest_path)
    if change == "scope":
        scope = json.loads(options.episode_scope.read_bytes())
        scope["inputs_sha256"] = "f" * 64
        options.episode_scope.write_text(json.dumps(scope))
    elif change == "missing_lease":
        options.worker_generation = None
    elif change == "expired_lease":
        options.lease_issued_monotonic_s = time.monotonic() - 2
        options.lease_deadline_monotonic_s = time.monotonic() - 1
    elif change == "tampered_role":
        path = manifest_path.parent / manifest["roles"]["runtime_config"]["path"]
        path.write_bytes(path.read_bytes() + b"bad")
    else:
        options.episode_inputs_manifest = None
    with pytest.raises(ValueError):
        open_recorder_episode(options)
    assert not options.episode_root.exists()


@pytest.mark.parametrize("escape", ["inside", "outside", "evidence_name", "sandbox_elsewhere"])
def test_explicit_episode_root_uses_the_actual_reserved_lease_namespace(tmp_path, escape):
    manifest, _, _ = frozen_child_inputs(tmp_path)
    options = _options(tmp_path, inputs=manifest)
    working = options.episode_root.parent
    if escape == "outside":
        options.episode_root = working / "outside"
    elif escape == "evidence_name":
        options.evidence_root = working / "recorder"
    elif escape == "sandbox_elsewhere":
        # a sandbox location is accepted only for the sandbox layout itself (episode beside its evidence root)
        options.episode_root = tmp_path / "fault-sandbox" / "attempt" / "episode"
    if escape in ("outside", "evidence_name", "sandbox_elsewhere"):
        with pytest.raises(ValueError, match="EPISODE_LOCATION_MISMATCH"):
            open_recorder_episode(options)
        assert not working.exists()
    else:
        episode = open_recorder_episode(options)
        try:
            assert episode.capture.recorder.root == working / "episode"
            assert not (working / "dynamic" / "episode").exists()
            identity = json.loads((working / "episode" / "audit" / "episode.json").read_bytes())
            assert identity["lease"]["attempt_id"] == options.attempt_id
            assert identity["lease"]["point_id"] == options.point_id
        finally:
            episode.close()


def test_sandbox_layout_records_beside_the_run_never_in_an_attempt_workspace(tmp_path):
    manifest, _, _ = frozen_child_inputs(tmp_path)
    options = _options(tmp_path, inputs=manifest)
    base = tmp_path / "run" / "fault-sandbox" / "attempt"
    options.episode_root, options.evidence_root = base / "episode", base / "dynamic"
    episode = open_recorder_episode(options)
    try:
        assert episode.capture.recorder.root == base / "episode"
        assert not (tmp_path / "worker").exists()
    finally:
        episode.close()


def test_run_rejects_a_posthoc_final_target_before_creating_run_root(tmp_path, monkeypatch):
    from so101_demo.cli.act_diagnostic_episode import main
    inputs, manifest, snapshot = frozen_child_inputs(tmp_path)
    root = tmp_path / "live"
    mkdir = Path.mkdir
    def guarded_mkdir(path, *args, **kwargs):
        if path == root:
            raise AssertionError("wrong target reached run-root creation")
        return mkdir(path, *args, **kwargs)
    monkeypatch.setattr(Path, "mkdir", guarded_mkdir)
    target = list(snapshot["targets"]["final_target"])
    target[0] += .5
    assert main(["run", "--inputs", str(inputs.parent), "--root", str(root),
                 "--mode", manifest["mode"], "--lifecycle", "FULL_RESTART",
                 "--final-cup-pose", ",".join(map(str, target))]) == 2
    assert not root.exists()


def test_only_the_model_bound_execution_snapshot_binding_is_accepted(tmp_path):
    from so101_demo.act.diagnostic_episode_inputs import validate_execution_snapshot_binding

    _, manifest, snapshot = frozen_child_inputs(tmp_path)
    binding = manifest["execution_snapshot"]
    assert validate_execution_snapshot_binding(binding)["model_sha256"] == snapshot["model_sha256"]
    retired = {key: binding[key] for key in ("kind", "path", "sha256")} | {"schema_version": 1}
    with pytest.raises(ValueError, match="INPUTS_EXECUTION_SNAPSHOT_INVALID"):
        validate_execution_snapshot_binding(retired)
    with pytest.raises(ValueError, match="INPUTS_EXECUTION_SNAPSHOT_INVALID"):
        validate_execution_snapshot_binding({**binding, "schema_version": 3})


def _scope_for(tmp_path, name, scene_id, seed, inputs_sha256, mode="formal"):
    path = tmp_path / name
    write_collection_scope(build_collection_scope(mode, scene_id=scene_id, seed=seed, inputs_sha256=inputs_sha256), path)
    return path


def test_two_scenes_reach_recorder_open(tmp_path):
    """Two different non-`default` scenes of one bound scene manifest both pass the real scope check at Recorder open.

    Real: `freeze_inputs` (binds the scene manifest), `verify_frozen_inputs`, the real `open_recorder_episode` and its audit
    files. Controlled: the role candidates (synthetic approvals) and the scene rows (hand-written)."""
    from test_act_formal_scene_scope import ROWS, scene_file
    manifest_path, manifest, _ = frozen_child_inputs(tmp_path, mode="formal", scene_manifest=scene_file(tmp_path),
                                                     scope_scene=("scene-a", 11))
    assert "scene_manifest" in manifest and manifest["mode"] == "formal"
    for row in ROWS:
        scene = row["scene_id"]
        working = tmp_path / "worker" / "attempts" / scene / "attempt" / "working"
        options = _options(tmp_path, inputs=manifest_path, working=working)
        options.point_id = scene
        options.episode_scope = _scope_for(tmp_path, f"scope-{scene}.json", scene, row["seed"], manifest["inputs_sha256"])
        episode = open_recorder_episode(options)
        try:
            identity = json.loads((working / "episode" / "audit" / "episode.json").read_bytes())
            assert (identity["scene_id"], identity["seed"], identity["mode"]) == (scene, row["seed"], "formal")
            assert json.loads((working / "episode" / "audit" / "inputs.json").read_bytes()) == manifest
        finally:
            episode.close()


@pytest.mark.parametrize("scene,seed", [("default", 0), ("scene-c", 11), ("scene-a", 12), ("scene-b", 11)])
def test_a_scope_outside_the_bound_scene_manifest_is_refused_at_recorder_open(tmp_path, scene, seed):
    from test_act_formal_scene_scope import scene_file
    manifest_path, manifest, _ = frozen_child_inputs(tmp_path, mode="formal", scene_manifest=scene_file(tmp_path),
                                                     scope_scene=("scene-a", 11))
    working = tmp_path / "worker" / "attempts" / "task_start" / "attempt" / "working"
    options = _options(tmp_path, inputs=manifest_path, working=working)
    options.episode_scope = _scope_for(tmp_path, "scope-outside.json", scene, seed, manifest["inputs_sha256"])
    with pytest.raises(ValueError, match="EPISODE_SCOPE_INPUTS_MISMATCH"):
        open_recorder_episode(options)
    assert not working.exists()
