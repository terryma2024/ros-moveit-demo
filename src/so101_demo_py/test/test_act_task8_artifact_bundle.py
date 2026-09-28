"""Task 8P3: a self-contained bundle is admitted only through its committed receipt.

Receipt shape (the producer contract pinned here):
  {"schema_version", "kind": "task8_preparation_receipt", "bundle_root",
   "manifest_path", "artifacts": {name: {"relative_path", "sha256", "source_sha256"}},
   "identities": {...}, "receipt_sha256"}
The seven business artifacts are source_provenance, runtime_config, collection_config,
calibration_report, head_search_qualification, measurement_contract, anchors; the policy
proposal and activation receipt travel with them.
"""

import hashlib
import json
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
ARTIFACTS = ("source_provenance", "runtime_config", "collection_config", "calibration_report",
             "head_search_qualification", "measurement_contract", "anchors", "proposal",
             "activation_receipt")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) if not isinstance(payload, str) else payload)
    return path


class ValidInputs:
    """A closed set of business artifacts in a source evidence directory."""

    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.identities = {"source_provenance_sha256": "a" * 64, "runtime_config_sha256": "b" * 64,
                           "anchors_sha256": "c" * 64, "contact_policy_fingerprint": "d" * 64,
                           "act_profile_sha256": "e" * 64}
        self.paths = {}
        for name in ARTIFACTS:
            document = {"schema_version": 1, "kind": name, "payload": name}
            self.paths[name] = _write(root / f"{name}.json", document)
        # the manifest is produced by Task 8P1/P2 inputs and bound into the bundle
        self.manifest = _write(root / "manifest.json", {
            "schema_version": 2, "kind": "ACT_TASK8_LIVE", "manifest_sha256": "f" * 64})


@pytest.fixture
def valid_inputs(tmp_path):
    from so101_demo.act.task8_artifact_bundle import Task8ArtifactInputs

    source = ValidInputs(tmp_path / "evidence")
    return Task8ArtifactInputs(
        source_root=tmp_path / "repo", install_overlay=tmp_path / "install",
        source_provenance=source.paths["source_provenance"],
        runtime_config=source.paths["runtime_config"],
        collection_config=source.paths["collection_config"],
        calibration_report=source.paths["calibration_report"],
        head_search_qualification=source.paths["head_search_qualification"],
        measurement_contract=source.paths["measurement_contract"],
        anchors=source.paths["anchors"], proposal=source.paths["proposal"],
        activation_receipt=source.paths["activation_receipt"], manifest=source.manifest,
        identities=source.identities)


def test_committed_bundle_survives_source_evidence_becoming_unavailable(valid_inputs, tmp_path):
    from so101_demo.act.task8_artifact_bundle import (
        prepare_task8_bundle, verify_prepared_task8_bundle,
    )

    receipt = prepare_task8_bundle(valid_inputs, tmp_path / "bundle-001")
    assert Path(receipt).name == "preparation-receipt.json"
    original = valid_inputs.calibration_report.parent
    original.rename(tmp_path / "old-evidence-unavailable")
    verified = verify_prepared_task8_bundle(receipt)
    assert Path(verified.calibration_report).parent == Path(receipt).parent
    assert Path(verified.calibration_report).is_file()


def test_bundle_without_receipt_is_never_admitted(valid_inputs, tmp_path, monkeypatch):
    import so101_demo.act.task8_artifact_bundle as bundle_module
    from so101_demo.act.task8_artifact_bundle import (
        prepare_task8_bundle, verify_prepared_task8_bundle,
    )

    def fail_publish(*_args, **_kwargs):
        raise OSError("injected receipt publish failure")

    monkeypatch.setattr(bundle_module, "_publish_receipt", fail_publish)
    root = tmp_path / "bundle-002"
    with pytest.raises(OSError):
        prepare_task8_bundle(valid_inputs, root)
    assert not (root / "preparation-receipt.json").exists()
    monkeypatch.undo()
    with pytest.raises(ValueError, match="TASK8_PREPARATION_REQUIRED"):
        verify_prepared_task8_bundle(root / "preparation-receipt.json")


def test_receipt_records_every_artifact_hash_and_identity(valid_inputs, tmp_path):
    from so101_demo.act.task8_artifact_bundle import (
        prepare_task8_bundle, verify_prepared_task8_bundle,
    )

    receipt = Path(prepare_task8_bundle(valid_inputs, tmp_path / "bundle-003"))
    document = json.loads(receipt.read_text())
    assert document["kind"] == "task8_preparation_receipt"
    assert set(document["artifacts"]) == set(ARTIFACTS)
    for name, entry in document["artifacts"].items():
        bundled = receipt.parent / entry["relative_path"]
        assert bundled.is_file() and _sha(bundled) == entry["sha256"]
        # each artifact is its own Task8ArtifactInputs field, not a dict entry
        assert entry["source_sha256"] == _sha(Path(getattr(valid_inputs, name)))
    assert document["identities"] == valid_inputs.identities
    assert verify_prepared_task8_bundle(receipt)


def test_tampered_bundle_artifact_is_refused(valid_inputs, tmp_path):
    from so101_demo.act.task8_artifact_bundle import (
        prepare_task8_bundle, verify_prepared_task8_bundle,
    )

    receipt = Path(prepare_task8_bundle(valid_inputs, tmp_path / "bundle-004"))
    document = json.loads(receipt.read_text())
    target = receipt.parent / document["artifacts"]["calibration_report"]["relative_path"]
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(ValueError):
        verify_prepared_task8_bundle(receipt)


def test_startup_validation_is_pure_and_acquires_nothing(valid_inputs, tmp_path, monkeypatch):
    from so101_demo.act.task8_artifact_bundle import (
        prepare_task8_bundle, validate_task8_startup_artifacts,
    )

    receipt = prepare_task8_bundle(valid_inputs, tmp_path / "bundle-005")
    calls = []

    class Spy:
        def __init__(self, *args, **kwargs):
            calls.append("constructed")

        def start(self, *args, **kwargs):
            calls.append("start")
            raise AssertionError("the validator must not start a workload service")

    monkeypatch.setattr("so101_teleop.unified.bridge.UnifiedWorkloadService", Spy,
                        raising=False)
    monkeypatch.setattr("so101_teleop.unified.compose.compose_services",
                        lambda *a, **k: calls.append("compose"), raising=False)
    payload = {"preparation_receipt_path": str(receipt),
               "preparation_receipt_sha256": _sha(Path(receipt))}
    verified = validate_task8_startup_artifacts(payload)
    assert Path(verified.calibration_report).is_file()
    assert calls == []
