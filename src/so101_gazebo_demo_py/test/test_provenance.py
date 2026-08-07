import json
from pathlib import Path


PACKAGE = Path(__file__).parents[1]


def test_provenance_has_exact_reference_and_hashes() -> None:
    payload = json.loads((PACKAGE / "docs/provenance.json").read_text())
    assert payload == {
        "reference_head": "71a87165b3e752169a2990f62a07569e4720be9f",
        "reference_branch": "codex/refactor-optimization-r3",
        "files": [],
    }
