from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = PACKAGE_ROOT / "docs/provenance.json"
SOURCE_COMMIT = "8d7913e7f552a40ee627d65be8b873ac16748bc9"


def test_provenance_entries_are_exact_and_verifiable() -> None:
    document = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    assert document["schema_version"] == 1
    assert document["behavior_source"]["commit"] == SOURCE_COMMIT
    entries = document["adaptations"]
    assert entries
    for entry in entries:
        assert set(entry) == {
            "source_commit",
            "source_path",
            "destination_path",
            "source_sha256",
            "adaptation",
        }
        assert entry["source_commit"] == SOURCE_COMMIT
        assert entry["adaptation"].strip()
        destination = REPOSITORY_ROOT / entry["destination_path"]
        assert destination.is_file()
        source = subprocess.run(
            ["git", "show", f"{SOURCE_COMMIT}:{entry['source_path']}"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
        ).stdout
        assert hashlib.sha256(source).hexdigest() == entry["source_sha256"]


def test_setup_installs_only_the_new_package_provenance() -> None:
    setup_source = (PACKAGE_ROOT / "setup.py").read_text(encoding="utf-8")
    assert '"docs/provenance.json"' in setup_source
    assert "share/{package_name}/docs" in setup_source
