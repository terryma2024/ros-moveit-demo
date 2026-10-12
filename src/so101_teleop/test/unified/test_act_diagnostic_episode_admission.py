"""The diagnostic operation is recognised, and it removes the Head proof and nothing else.

`act_diagnostic_episode` is a distinct admission kind: it reuses the same reservation, GPU
lease, contact activation and child ownership as the formal path, but it is fixed to one Worker,
cannot claim qualification, and must present the frozen inputs plus the explicit diagnostic mode
record. The formal and pick-place validation payload schemas are unchanged, so neither can inherit these fields.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import time

import pytest

from so101_teleop.unified.contracts import Domain, OperationSpec
from so101_teleop.unified.intent_store import IntentStore
from teleop_paths import DEMO_TEST_IMPORT_PATH

# the demo package's shared fixtures live in its test directory, its helpers and path constants in test/support
for _candidate in (*DEMO_TEST_IMPORT_PATH, Path(__file__).resolve().parent):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from test_act_campaign_admission import _service, launch  # noqa: E402  (shared fixtures)
from test_act_diagnostic_episode_scope import (  # noqa: E402  (frozen-input fixtures)
    _canonical,
    _entry,
    _registry,
    _write_registry,
)


def _diagnostic_spec(tmp_path, *, tag="a", calibration_mutation=None, scope_mutation=None,
                     payload_mutation=None):
    """A complete diagnostic payload: frozen inputs, mode record and a non-Head calibration."""

    from so101_demo.act.diagnostic_episode_inputs import freeze_inputs, read_inputs_manifest

    registry = _registry(tmp_path)
    # the calibration report is one of the frozen roles, so a mutation has to land before the
    # freeze; changing the file afterwards would only alter a copy nothing reads
    if calibration_mutation is not None:
        calibration = tmp_path / "calibration-nonhead.json"
        document = json.loads(calibration.read_text())
        calibration_mutation(document)
        calibration.write_bytes(_canonical(document))
        for role in ("path_policy", "placement_qc", "rgb_skew"):
            registry["roles"][role]["selected"] = _entry(calibration, "nonhead_calibration")
            registry["roles"][role]["candidates"] = [_entry(calibration, "nonhead_calibration")]
    candidates = _write_registry(tmp_path, registry)
    manifest_path = freeze_inputs(candidates, tmp_path / f"inputs-{tag}")
    manifest = read_inputs_manifest(manifest_path)

    def frozen(role: str) -> Path:
        return manifest_path.parent / manifest["roles"][role]["path"]

    scope = tmp_path / "collection-scope.json"
    scope_document = {"kind": "ACT_COLLECTION_SCOPE", "schema_version": 1,
                      "mode": "preselected_target_diagnostic", "scene_id": "default", "seed": 0,
                      "inputs_sha256": manifest["inputs_sha256"]}
    if scope_mutation is not None:
        scope_mutation(scope_document)
    scope.write_bytes(_canonical(scope_document))

    # every runtime artifact is the frozen copy of its role, which is what admission now requires
    proposal_path = frozen("contact_proposal")
    receipt_path = frozen("contact_activation")
    fingerprint = json.loads(proposal_path.read_text())["policy_fingerprint"]
    payload = {
        "campaign_id": "campaign-1", "backend": "mujoco", "worker_count": 1,
        "source_path": str(frozen("reset_recipe")),
        "source_sha256": manifest["roles"]["reset_recipe"]["sha256"],
        "manifest_path": str(frozen("anchor_scene")),
        "manifest_sha256": manifest["roles"]["anchor_scene"]["sha256"],
        "runtime_config_path": str(frozen("runtime_config")),
        "runtime_config_sha256": manifest["roles"]["runtime_config"]["sha256"],
        "collection_config_path": str(frozen("collection_config")),
        "collection_config_sha256": manifest["roles"]["collection_config"]["sha256"],
        "contact_policy_fingerprint": fingerprint, "proposal_path": str(proposal_path),
        "activation_receipt_path": str(receipt_path), "evidence_root": str(tmp_path),
        "service_epoch": "epoch-1", "resource_binding_id": "binding-1",
        "qualification_mode": False, "qualification_receipt_path": None,
        "calibration_report_path": str(frozen("path_policy")),
        "calibration_report_sha256": manifest["roles"]["path_policy"]["sha256"],
        "collection_scope_path": str(scope),
        "collection_scope_sha256": hashlib.sha256(scope.read_bytes()).hexdigest(),
        "inputs_manifest_path": str(manifest_path),
        "inputs_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "children": [launch("w00", 40, "session-0").__dict__],
    }
    if payload_mutation is not None:
        payload_mutation(payload)
    return OperationSpec(command_id="start-1", domain=Domain.VALIDATION,
                         kind="act_diagnostic_episode", payload=payload,
                         runtime_id="runtime-1", execution_generation=3,
                         deadline_ns=time.monotonic_ns() + 10**12)


def test_diagnostic_admits_one_worker_with_the_frozen_inputs(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    try:
        service = _service(store)
        context = service.start(_diagnostic_spec(tmp_path))
        assert context.workload_kind == "act_diagnostic_episode"
        assert context.worker_count == 1
        assert context.physical_gpu_uuid == "GPU-physical-a"
        assert len(service.child_registry.launches()) == 1
        assert store._query_one("SELECT * FROM gpu_workload_leases") is not None
    finally:
        store.close()


def test_diagnostic_refuses_more_workers_or_any_qualification_claim(tmp_path):
    def with_field(**overrides):
        def mutate(payload):
            payload.update(overrides)

        return mutate

    cases = (
        ("workers", with_field(worker_count=2), "DIAGNOSTIC_SCOPE_INVALID"),
        ("eight", with_field(worker_count=8), "DIAGNOSTIC_SCOPE_INVALID"),
        ("qualification", with_field(qualification_mode=True), "DIAGNOSTIC_QUALIFICATION_INVALID"),
        ("receipt", with_field(qualification_receipt_path="/tmp/qualification.json"),
         "QUALIFICATION_RECEIPT_UNEXPECTED"),
    )
    for name, mutate, code in cases:
        store = IntentStore.open(tmp_path / f"state-{name}")
        try:
            service = _service(store)
            with pytest.raises(ValueError, match=code):
                service.start(_diagnostic_spec(tmp_path, tag=name, payload_mutation=mutate))
            assert service.child_registry.launches() == ()
            assert service.arbiter.is_idle()
            assert store._query_one("SELECT * FROM gpu_workload_leases") is None
        finally:
            store.close()


def test_diagnostic_refuses_a_scope_that_is_not_the_frozen_inputs(tmp_path):
    def relabel(document):
        document["mode"] = "formal"

    def other_inputs(document):
        document["inputs_sha256"] = "b" * 64

    for name, mutate in (("formal", relabel), ("other-inputs", other_inputs)):
        store = IntentStore.open(tmp_path / f"state-{name}")
        try:
            service = _service(store)
            with pytest.raises(ValueError, match="DIAGNOSTIC_SCOPE_UNBOUND"):
                service.start(_diagnostic_spec(tmp_path, tag=name, scope_mutation=mutate))
            assert service.child_registry.launches() == ()
            assert service.arbiter.is_idle()
        finally:
            store.close()


def test_diagnostic_requires_every_nonhead_check_but_no_head_search(tmp_path):
    # the base spec reports fov/search UNMEASURED and is admitted by the first test; a non-Head
    # check may not be skipped the same way, because the diagnostic scope removes no safety gate
    def unmeasure(document):
        document["checks"]["release"] = "UNMEASURED"

    store = IntentStore.open(tmp_path / "state")
    try:
        service = _service(store)
        with pytest.raises(ValueError, match="NONHEAD_SAFETY_NOT_READY"):
            service.start(_diagnostic_spec(tmp_path, calibration_mutation=unmeasure))
        assert service.arbiter.is_idle()
    finally:
        store.close()


def test_formal_and_pick_place_validation_schemas_refuse_the_diagnostic_fields(tmp_path):
    """The diagnostic fields are a schema error in both other kinds, so they cannot be inherited."""

    spec = _diagnostic_spec(tmp_path)
    store = IntentStore.open(tmp_path / "state")
    try:
        service = _service(store)
        with pytest.raises(ValueError, match="CAMPAIGN_START_SCHEMA"):
            service.start(replace(spec, kind="act_collection_start"))
        with pytest.raises(ValueError, match="CAMPAIGN_START_SCHEMA"):
            service.start(replace(spec, kind="pick_place_validation_phase"))
        with pytest.raises(ValueError, match="ACT_CONTAINER_RESUME_FORBIDDEN"):
            service.start(replace(spec, kind="act_collection_resume"))
        assert service.arbiter.is_idle()
    finally:
        store.close()


def test_diagnostic_refuses_a_scope_file_changed_after_the_payload_pin(tmp_path):
    spec = _diagnostic_spec(tmp_path)
    scope = Path(spec.payload["collection_scope_path"])
    document = json.loads(scope.read_text())
    document["seed"] = 1
    scope.write_bytes(_canonical(document))
    store = IntentStore.open(tmp_path / "state")
    try:
        service = _service(store)
        with pytest.raises(ValueError, match="CAMPAIGN_ARTIFACT_HASH_MISMATCH"):
            service.start(spec)
    finally:
        store.close()


def test_diagnostic_refuses_an_artifact_outside_the_frozen_set(tmp_path):
    """A byte-identical copy elsewhere is still not the frozen artifact of this input set."""

    spec = _diagnostic_spec(tmp_path)
    decoy = tmp_path / "decoy-runtime-config.yaml"
    decoy.write_bytes(Path(spec.payload["runtime_config_path"]).read_bytes())
    payload = dict(spec.payload, runtime_config_path=str(decoy),
                   runtime_config_sha256=hashlib.sha256(decoy.read_bytes()).hexdigest())
    store = IntentStore.open(tmp_path / "state")
    try:
        service = _service(store)
        with pytest.raises(ValueError, match="DIAGNOSTIC_SCOPE_UNBOUND"):
            service.start(replace(spec, payload=payload))
        assert service.arbiter.is_idle()
        assert store._query_one("SELECT * FROM gpu_workload_leases") is None
    finally:
        store.close()


def test_diagnostic_refuses_a_scope_outside_the_frozen_anchor(tmp_path):
    def other_seed(document):
        document["seed"] = 1

    def other_scene(document):
        document["scene_id"] = "left"

    for name, mutate in (("seed", other_seed), ("scene", other_scene)):
        store = IntentStore.open(tmp_path / f"state-{name}")
        try:
            service = _service(store)
            with pytest.raises(ValueError, match="DIAGNOSTIC_SCOPE_UNBOUND"):
                service.start(_diagnostic_spec(tmp_path, tag=name, scope_mutation=mutate))
        finally:
            store.close()


def test_diagnostic_refuses_a_deleted_or_changed_frozen_role_file(tmp_path):
    """Admission re-reads the frozen bytes, so a self-consistent manifest is not enough.

    A file the payload pins is refused even earlier by the payload digest. A file the payload does
    not pin (a frozen role with no payload digest of its own) is exactly what the byte verifier is
    for, so that is the case this test drives.
    """

    spec = _diagnostic_spec(tmp_path)
    manifest = json.loads(Path(spec.payload["inputs_manifest_path"]).read_text())
    frozen_root = Path(spec.payload["inputs_manifest_path"]).parent
    unpinned = frozen_root / manifest["roles"]["resource_thresholds"]["path"]
    original = unpinned.read_bytes()

    unpinned.unlink()
    store = IntentStore.open(tmp_path / "state-deleted")
    try:
        service = _service(store)
        with pytest.raises(ValueError, match="DIAGNOSTIC_SCOPE_UNBOUND"):
            service.start(spec)
        assert store._query_one("SELECT * FROM gpu_workload_leases") is None
    finally:
        store.close()

    unpinned.write_bytes(original + b"# changed after the freeze\n")
    store = IntentStore.open(tmp_path / "state-changed")
    try:
        service = _service(store)
        with pytest.raises(ValueError, match="DIAGNOSTIC_SCOPE_UNBOUND"):
            service.start(spec)
    finally:
        store.close()

    # a pinned file is refused by the payload's own digest, before the manifest is even read
    unpinned.write_bytes(original)
    pinned = Path(spec.payload["runtime_config_path"])
    pinned.unlink()
    store = IntentStore.open(tmp_path / "state-pinned")
    try:
        service = _service(store)
        with pytest.raises(ValueError, match="CAMPAIGN_ARTIFACT_INVALID"):
            service.start(spec)
    finally:
        store.close()


def _rewrite_frozen(manifest_path: Path, role: str, payload: bytes) -> dict:
    """Build the reviewer's counterexample class: a self-consistent set with invalid policy bytes.

    The frozen file, the manifest entry and the manifest digest are all updated together, so every
    byte check passes and only the semantic derivation can still refuse it.
    """

    manifest = json.loads(manifest_path.read_text())
    target = manifest_path.parent / manifest["roles"][role]["path"]
    target.write_bytes(payload)
    manifest["roles"][role]["sha256"] = hashlib.sha256(payload).hexdigest()
    manifest["roles"][role]["bytes"] = len(payload)
    manifest["inputs_sha256"] = hashlib.sha256(_canonical(manifest["roles"])).hexdigest()
    manifest_path.write_bytes(_canonical(manifest))
    return manifest


def _refresh_payload(spec, manifest_path: Path, **overrides):
    payload = dict(spec.payload, inputs_manifest_sha256=hashlib.sha256(
        manifest_path.read_bytes()).hexdigest(), **overrides)
    return replace(spec, payload=payload)


def test_diagnostic_refuses_a_frozen_resource_policy_without_stops(tmp_path):
    """A self-consistent frozen set whose configs lack the stop points must still be refused."""

    spec = _diagnostic_spec(tmp_path)
    manifest_path = Path(spec.payload["inputs_manifest_path"])
    runtime_path = Path(spec.payload["runtime_config_path"])
    stripped = runtime_path.read_bytes().replace(b"hard_stops:", b"unrelated:")
    manifest = _rewrite_frozen(manifest_path, "runtime_config", stripped)
    # the scope pins the frozen digest too, so it is refreshed as well: the only thing left that can
    # refuse this set is the resource policy derived from the config bytes
    scope_path = Path(spec.payload["collection_scope_path"])
    scope = json.loads(scope_path.read_text())
    scope["inputs_sha256"] = manifest["inputs_sha256"]
    scope_path.write_bytes(_canonical(scope))
    payload = _refresh_payload(
        spec, manifest_path, runtime_config_sha256=hashlib.sha256(stripped).hexdigest(),
        collection_scope_sha256=hashlib.sha256(scope_path.read_bytes()).hexdigest())
    store = IntentStore.open(tmp_path / "state")
    try:
        service = _service(store)
        with pytest.raises(ValueError, match="DIAGNOSTIC_SCOPE_UNBOUND"):
            service.start(payload)
        assert service.child_registry.launches() == ()
        assert store._query_one("SELECT * FROM gpu_workload_leases") is None
    finally:
        store.close()


def test_diagnostic_accepts_a_frozen_set_whose_identity_is_not_current(tmp_path):
    """The frozen manifest's source and config identity are recorded provenance.

    The set still has to be internally sound: the same manifest with a substituted resource policy
    is refused by the resource derivation below.
    """

    for tag, mutation in (("commit", ("source_commit", "c" * 40)),
                          ("config", ("config_sha256", "e" * 64))):
        spec = _diagnostic_spec(tmp_path, tag=tag)
        manifest_path = Path(spec.payload["inputs_manifest_path"])
        manifest = json.loads(manifest_path.read_text())
        manifest[mutation[0]] = mutation[1]
        manifest_path.write_bytes(_canonical(manifest))
        store = IntentStore.open(tmp_path / f"state-{tag}")
        try:
            service = _service(store)
            context = service.start(_refresh_payload(spec, manifest_path))
            assert context.workload_kind == "act_diagnostic_episode"
            assert store._query_one("SELECT * FROM gpu_workload_leases") is not None
        finally:
            store.close()


def test_diagnostic_refuses_an_anchor_identity_the_bytes_do_not_describe(tmp_path):
    """Recomputing every hash does not let a manifest assert a scene the anchor bytes deny."""

    spec = _diagnostic_spec(tmp_path)
    manifest_path = Path(spec.payload["inputs_manifest_path"])
    manifest = json.loads(manifest_path.read_text())
    manifest["roles"]["anchor_scene"]["identity"] = dict(
        manifest["roles"]["anchor_scene"]["identity"], scene_id="left", seed=1)
    manifest["inputs_sha256"] = hashlib.sha256(_canonical(manifest["roles"])).hexdigest()
    manifest_path.write_bytes(_canonical(manifest))

    scope_path = Path(spec.payload["collection_scope_path"])
    scope = json.loads(scope_path.read_text())
    scope.update(scene_id="left", seed=1, inputs_sha256=manifest["inputs_sha256"])
    scope_path.write_bytes(_canonical(scope))

    payload = _refresh_payload(spec, manifest_path,
                               collection_scope_sha256=hashlib.sha256(
                                   scope_path.read_bytes()).hexdigest())
    store = IntentStore.open(tmp_path / "state")
    try:
        service = _service(store)
        with pytest.raises(ValueError, match="DIAGNOSTIC_SCOPE_UNBOUND"):
            service.start(payload)
    finally:
        store.close()


def test_diagnostic_accepts_two_distinct_approved_calibration_reports(tmp_path):
    """The one-report rule is withdrawn; each frozen report is validated on its own merits."""

    spec = _diagnostic_spec(tmp_path)
    manifest_path = Path(spec.payload["inputs_manifest_path"])
    manifest = json.loads(manifest_path.read_text())
    frozen_skew = manifest_path.parent / manifest["roles"]["rgb_skew"]["path"]
    document = json.loads(frozen_skew.read_text())
    # a genuinely valid second report: the top-level audit field is outside the closed check set
    document["audit_note"] = "a second, distinct approved report"
    second = _canonical(document)
    assert second != frozen_skew.read_bytes()
    manifest = _rewrite_frozen(manifest_path, "rgb_skew", second)
    scope_path = Path(spec.payload["collection_scope_path"])
    scope = json.loads(scope_path.read_text())
    scope["inputs_sha256"] = manifest["inputs_sha256"]
    scope_path.write_bytes(_canonical(scope))
    payload = _refresh_payload(
        spec, manifest_path,
        collection_scope_sha256=hashlib.sha256(scope_path.read_bytes()).hexdigest())
    store = IntentStore.open(tmp_path / "state")
    try:
        service = _service(store)
        context = service.start(payload)
        assert context.workload_kind == "act_diagnostic_episode"
        assert store._query_one("SELECT * FROM gpu_workload_leases") is not None
    finally:
        store.close()


@pytest.mark.parametrize("mutation", ("extra-check-key", "unmeasured-check", "changed-sample"))
def test_diagnostic_refuses_a_secondary_report_that_breaks_its_contract(tmp_path, mutation):
    """Every frozen calibration report carries the same structural contract, not just the pinned one.

    Distinct reports are allowed, so each one is validated on its own bytes; all outer
    hashes (frozen file, manifest, manifest digest, scope, payload) are refreshed so only the report's
    own contract can refuse it.
    """

    spec = _diagnostic_spec(tmp_path)
    manifest_path = Path(spec.payload["inputs_manifest_path"])
    manifest = json.loads(manifest_path.read_text())
    frozen_skew = manifest_path.parent / manifest["roles"]["rgb_skew"]["path"]
    document = json.loads(frozen_skew.read_text())
    if mutation == "extra-check-key":
        document["checks"]["note"] = "smuggled into the closed check set"
    elif mutation == "unmeasured-check":
        document["checks"]["release"] = "UNMEASURED"
    else:
        document["measurements"]["max_skew_s"]["sample_sha256"] = "0" * 64
    second = _canonical(document)
    manifest = _rewrite_frozen(manifest_path, "rgb_skew", second)
    scope_path = Path(spec.payload["collection_scope_path"])
    scope = json.loads(scope_path.read_text())
    scope["inputs_sha256"] = manifest["inputs_sha256"]
    scope_path.write_bytes(_canonical(scope))
    payload = _refresh_payload(
        spec, manifest_path,
        collection_scope_sha256=hashlib.sha256(scope_path.read_bytes()).hexdigest())
    store = IntentStore.open(tmp_path / "state")
    try:
        service = _service(store)
        with pytest.raises(ValueError, match="DIAGNOSTIC_SCOPE_UNBOUND"):
            service.start(payload)
        assert service.child_registry.launches() == ()
        assert store._query_one("SELECT * FROM gpu_workload_leases") is None
    finally:
        store.close()
