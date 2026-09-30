"""The diagnostic operation is recognised, and it removes the Head proof and nothing else.

`act_first_episode_diagnostic` is a distinct admission kind: it reuses the same reservation, GPU
lease, contact activation and child ownership as the formal path, but it is fixed to one Worker,
cannot claim qualification, and must present the frozen inputs plus the explicit diagnostic mode
record. The formal and Task 8 payload schemas are unchanged, so neither can inherit these fields.
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

# <wt>/src/so101_teleop/test/teleop/<this file> -> parents[3] is <wt>/src
_SRC = Path(__file__).resolve().parents[3]
for _candidate in (_SRC / "so101_demo_py" / "test", Path(__file__).resolve().parent):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from test_act_campaign_admission import _service, launch  # noqa: E402  (shared fixtures)
from test_act_first_episode_scope import (  # noqa: E402  (frozen-input fixtures)
    _calibration_document,
    _canonical,
    _registry,
    _write_registry,
)


def _diagnostic_spec(tmp_path, *, tag="a", calibration_mutation=None, scope_mutation=None,
                     payload_mutation=None):
    """A complete diagnostic payload: frozen inputs, mode record and a non-Head calibration."""

    from so101_demo.act.first_episode_inputs import freeze_inputs, read_inputs_manifest

    registry = _registry(tmp_path)
    candidates = _write_registry(tmp_path, registry)
    manifest_path = freeze_inputs(candidates, tmp_path / f"inputs-{tag}")
    manifest = read_inputs_manifest(manifest_path)

    def frozen(role: str) -> Path:
        return manifest_path.parent / manifest["roles"][role]["path"]

    calibration = tmp_path / "calibration-nonhead.json"
    document = _calibration_document(tmp_path)
    document["checks"]["fov"] = "UNMEASURED"
    document["checks"]["search"] = "UNMEASURED"
    if calibration_mutation is not None:
        calibration_mutation(document)
    calibration.write_bytes(_canonical(document))

    scope = tmp_path / "collection-scope.json"
    scope_document = {"kind": "ACT_COLLECTION_SCOPE", "schema_version": 1,
                      "mode": "preselected_target_diagnostic", "scene_id": "default", "seed": 0,
                      "inputs_sha256": manifest["inputs_sha256"]}
    if scope_mutation is not None:
        scope_mutation(scope_document)
    scope.write_bytes(_canonical(scope_document))

    proposal_path = Path(registry["roles"]["contact_proposal"]["selected"]["path"])
    receipt_path = Path(registry["roles"]["contact_activation"]["selected"]["path"])
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
        "calibration_report_path": str(calibration),
        "calibration_report_sha256": hashlib.sha256(calibration.read_bytes()).hexdigest(),
        "collection_scope_path": str(scope),
        "collection_scope_sha256": hashlib.sha256(scope.read_bytes()).hexdigest(),
        "inputs_manifest_path": str(manifest_path),
        "inputs_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "children": [launch("w00", 40, "session-0").__dict__],
    }
    if payload_mutation is not None:
        payload_mutation(payload)
    return OperationSpec(command_id="start-1", domain=Domain.VALIDATION,
                         kind="act_first_episode_diagnostic", payload=payload,
                         runtime_id="runtime-1", execution_generation=3,
                         deadline_ns=time.monotonic_ns() + 10**12)


def test_diagnostic_admits_one_worker_with_the_frozen_inputs(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    try:
        service = _service(store)
        context = service.start(_diagnostic_spec(tmp_path))
        assert context.workload_kind == "act_first_episode_diagnostic"
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


def test_formal_and_task8_schemas_refuse_the_diagnostic_fields(tmp_path):
    """The diagnostic fields are a schema error in both other kinds, so they cannot be inherited."""

    spec = _diagnostic_spec(tmp_path)
    store = IntentStore.open(tmp_path / "state")
    try:
        service = _service(store)
        with pytest.raises(ValueError, match="CAMPAIGN_START_SCHEMA"):
            service.start(replace(spec, kind="act_collection_start"))
        with pytest.raises(ValueError, match="CAMPAIGN_START_SCHEMA"):
            service.start(replace(spec, kind="task8_phase"))
        with pytest.raises(ValueError, match="CAMPAIGN_START_SCHEMA"):
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
