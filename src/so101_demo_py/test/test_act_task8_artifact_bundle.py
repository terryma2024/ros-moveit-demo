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


def _inputs(tmp_path):
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


@pytest.fixture
def valid_inputs(tmp_path):
    return _inputs(tmp_path)


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


def test_validate_cli_reports_the_bundle_and_refuses_a_bare_directory(tmp_path):
    from so101_demo.act.task8_artifact_bundle import prepare_task8_bundle
    from so101_demo.cli import act_validate_task8_artifacts as validate_cli

    inputs = _inputs(tmp_path)
    receipt = prepare_task8_bundle(inputs, tmp_path / "bundle-cli")
    assert validate_cli.main(["--preparation-receipt", str(receipt)]) == 0
    with pytest.raises(ValueError, match="TASK8_PREPARATION_REQUIRED"):
        validate_cli.main(["--preparation-receipt", str(tmp_path / "bundle-cli" / "missing.json")])


def test_legacy_live_entry_points_are_thin_forwarders():
    """The two legacy modules must not carry a second implementation."""

    here = Path(__file__).resolve()
    # the CLI package lives at src/cli in the repository and at so101_demo/cli in a test mirror
    candidates = [base / relative for base in here.parents
                  for relative in ("src/cli", "cli", "so101_demo/cli")]
    package = next((candidate for candidate in candidates
                    if (candidate / "act_prepare_task8_live.py").is_file()), None)
    assert package is not None, "the CLI package could not be located"
    for name, target in (("act_prepare_task8_live.py", "act_prepare_pick_place_validation"),
                         ("act_task8_live.py", "act_run_pick_place_validation")):
        source = (package / name).read_text()
        assert "sys.modules[__name__] = importlib.import_module(" in source
        assert f"so101_demo.cli.{target}" in source
        assert "def main" not in source


def test_bundle_payload_carries_the_verified_receipt_and_its_raw_digest(tmp_path):
    from so101_demo.act.task8_artifact_bundle import (
        prepare_task8_bundle, task8_bundle_payload,
    )

    receipt = prepare_task8_bundle(_inputs(tmp_path), tmp_path / "bundle-payload")
    payload = task8_bundle_payload(receipt)
    assert set(payload) == {"preparation_receipt_path", "preparation_receipt_sha256"}
    assert payload["preparation_receipt_path"] == str(receipt)
    assert payload["preparation_receipt_sha256"] == hashlib.sha256(receipt.read_bytes()).hexdigest()
    # an uncommitted or tampered bundle can never produce a payload
    with pytest.raises(ValueError, match="TASK8_PREPARATION_REQUIRED"):
        task8_bundle_payload(tmp_path / "bundle-payload" / "missing.json")
    broken = tmp_path / "bundle-broken"
    broken.mkdir()
    (broken / "preparation-receipt.json").write_text("{}")
    with pytest.raises(ValueError):
        task8_bundle_payload(broken / "preparation-receipt.json")


def test_task8_payload_names_its_receipt_and_never_mixes_shapes(tmp_path):
    from so101_demo.act.task8_artifact_bundle import require_task8_payload

    payload = {"preparation_receipt_path": "/run/bundle/preparation-receipt.json",
               "preparation_receipt_sha256": "a" * 64}
    assert require_task8_payload(payload) == payload
    for broken in ({}, {"preparation_receipt_path": "/x"}, dict(payload, preparation_receipt_sha256="nope"),
                   dict(payload, preparation_receipt_path="relative/path")):
        with pytest.raises(ValueError, match="TASK8_PAYLOAD_INVALID"):
            require_task8_payload(broken)
    # a collection-only field in a Task 8 payload is refused, whichever side supplies the key list
    with pytest.raises(ValueError, match="TASK8_PAYLOAD_SHAPE_CONFLICT"):
        require_task8_payload(dict(payload, collection_profile="formal"),
                              collection_only_keys=("collection_profile", "collection_output_root"))


def test_startup_receipt_must_match_its_payload_digest(tmp_path):
    from so101_demo.act.task8_artifact_bundle import (
        prepare_task8_bundle, verify_task8_startup_receipt,
    )

    receipt = prepare_task8_bundle(_inputs(tmp_path), tmp_path / "bundle-startup")
    payload = {"preparation_receipt_path": str(receipt),
               "preparation_receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest()}
    bundle = verify_task8_startup_receipt(payload)
    assert Path(bundle.receipt) == receipt
    with pytest.raises(ValueError, match="TASK8_PREPARATION_RECEIPT_MISMATCH"):
        verify_task8_startup_receipt(dict(payload, preparation_receipt_sha256="0" * 64))
    with pytest.raises(ValueError, match="TASK8_PREPARATION_REQUIRED"):
        verify_task8_startup_receipt(dict(payload,
                                          preparation_receipt_path=str(tmp_path / "absent.json")))
