import json
from pathlib import Path


PACKAGE = Path(__file__).parents[1]


def test_provenance_has_exact_reference_and_hashes() -> None:
    payload = json.loads((PACKAGE / "docs/provenance.json").read_text())
    assert payload["reference_head"] == "71a87165b3e752169a2990f62a07569e4720be9f"
    assert payload["reference_branch"] == "codex/refactor-optimization-r3"
    assert payload["files"]
    for entry in payload["files"]:
        assert set(entry) == {
            "source", "destination", "source_dirty",
            "source_sha256", "destination_sha256",
        }
        assert len(entry["source_sha256"]) == 64
        assert len(entry["destination_sha256"]) == 64
        assert (PACKAGE.parents[1] / entry["source"]).is_file()
        assert (PACKAGE / entry["destination"]).is_file()
