"""The campaign CLI's fail-closed gates, driven as a PROCESS so the exit code is the assertion.

Astra P2 asks for a terminal close-out that exits non-zero. This file reaches the gates that fire BEFORE anything is
acquired - the ones a close-out depends on and the ones the existing CLI test does not cover - and it checks the exit
status of a real subprocess rather than only the exception, because that is what an operator's shell sees.

What this file deliberately does NOT claim: the CLI close-out over a real case. That path runs live cases and needs the
stack and the fourteen journals this batch is forbidden to take (CP-1572), so it is reported as an open boundary rather
than tested here.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from so101_demo.cli.act_run_pick_place_validation import load_spec_file


def _spec_document(evidence_root: Path, manifest: Path) -> dict:
    return {
        "command_id": "command-1131", "domain": "validation", "kind": "task8_full",
        "payload": {"evidence_root": str(evidence_root), "manifest_path": str(manifest)},
        "runtime_id": "runtime-1131", "execution_generation": 1,
        "deadline_ns": time.monotonic_ns() + 60_000_000_000,
    }


def _write_spec(tmp_path: Path, document: dict) -> Path:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(document))
    return path


def _run_cli(*arguments: str) -> subprocess.CompletedProcess:
    """Run the real entry point in a subprocess: `raise SystemExit(main())`, exactly as the script does."""

    program = (
        "import sys;"
        "from so101_demo.cli.act_run_pick_place_validation import main;"
        "raise SystemExit(main(sys.argv[1:]))"
    )
    return subprocess.run([sys.executable, "-c", program, *arguments],
                          capture_output=True, text=True, timeout=120)


def test_a_missing_artifact_bundle_refuses_by_name_and_exits_non_zero(tmp_path):
    """The gate that fires first: a declared bundle that is not there stops the run with nothing acquired."""

    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    spec = _write_spec(tmp_path, _spec_document(evidence_root, manifest))
    journal = evidence_root / "campaign.jsonl"

    result = _run_cli("--spec", str(spec), "--journal", str(journal),
                      "--artifact-bundle", str(tmp_path / "absent-receipt.json"))

    assert result.returncode != 0, result.stdout
    assert "TASK8_PREPARATION_REQUIRED" in result.stderr, result.stderr[-400:]
    assert not journal.exists(), "nothing may be acquired before the gate refuses"


def test_a_journal_outside_the_evidence_root_refuses_by_name_and_exits_non_zero(tmp_path):
    """The local-path rule: the journal must live under the case's own evidence root."""

    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    spec = _write_spec(tmp_path, _spec_document(evidence_root, manifest))

    result = _run_cli("--spec", str(spec), "--journal", str(elsewhere / "campaign.jsonl"))

    assert result.returncode != 0, result.stdout
    assert "TASK8_LOCAL_PATH_INVALID" in result.stderr, result.stderr[-400:]


def test_a_spec_with_the_wrong_kind_is_refused_by_the_loader(tmp_path):
    """The loader's own rule, kept here because the gate tests must start from a spec that CAN be loaded."""

    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    document = _spec_document(evidence_root, tmp_path / "manifest.json")
    document["kind"] = "not_task8_full"
    path = _write_spec(tmp_path, document)

    with pytest.raises(ValueError, match="TASK8_SPEC_INVALID"):
        load_spec_file(path)
