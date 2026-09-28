"""Task 8P3: the receipt schema must describe the validator, not an older idea of it."""

import json
from pathlib import Path

from so101_demo.act import task8_artifact_bundle as module

PACKAGE = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((PACKAGE / "config/act/task8-preparation-receipt-schema.json").read_text())


def test_the_schema_matches_the_validators_own_constants():
    assert SCHEMA["properties"]["kind"]["const"] == module.KIND
    assert SCHEMA["properties"]["schema_version"]["const"] == module.SCHEMA_VERSION
    assert set(SCHEMA["required"]) == {
        "schema_version", "kind", "bundle_root", "manifest_path", "manifest_sha256",
        "manifest_source_sha256", "artifacts", "identities", "receipt_sha256"}
    # the artifact and identity sets come from the module's own tuples, so a new artifact cannot be added
    # to the code without failing here
    assert tuple(SCHEMA["properties"]["artifacts"]["required"]) == tuple(sorted(module._ARTIFACTS))
    assert tuple(SCHEMA["properties"]["identities"]["required"]) == tuple(sorted(module._IDENTITIES))
    assert SCHEMA["additionalProperties"] is False
    assert SCHEMA["properties"]["artifacts"]["additionalProperties"] is False


def test_every_artifact_and_identity_entry_is_a_closed_digest_record():
    for name, entry in SCHEMA["properties"]["artifacts"]["properties"].items():
        assert entry["additionalProperties"] is False, name
        assert sorted(entry["required"]) == ["relative_path", "sha256", "source_sha256"], name
        for field in ("sha256", "source_sha256"):
            assert entry["properties"][field]["pattern"] == "^[0-9a-f]{64}$", name
    for name, entry in SCHEMA["properties"]["identities"]["properties"].items():
        assert entry["pattern"] == "^[0-9a-f]{64}$", name


def test_the_receipt_digest_is_computed_over_the_document_without_itself():
    """The schema documents a self-digest; the module's own helper must be what computes it."""

    document = {"schema_version": module.SCHEMA_VERSION, "kind": module.KIND, "bundle_root": "/tmp/bundle"}
    with_digest = {**document, "receipt_sha256": module._receipt_sha256(document)}
    assert module._receipt_sha256(with_digest) == with_digest["receipt_sha256"]   # excluding itself
    assert with_digest["receipt_sha256"] != module._receipt_sha256({**document, "bundle_root": "/tmp/other"})
    assert "receipt_sha256" in SCHEMA["required"]
