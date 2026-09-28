"""Task 10 CLI: closed inputs, fail-closed writes, deterministic qualification projection."""

import json

import pytest

from so101_demo.act.candidate_source import candidate_identity
from so101_demo.act.sampling import COLLECTION_SPLITS, REACHABILITY_GATES, SPLITS
from so101_demo.cli.act_sample import NOT_FROZEN, main


def _candidate(index, *, band):
    return {"xy": [0.10 * band + 0.01 * index, 0.0], "arm_q": [0.0] * 6,
            "search_start_rad": 0.0, "seed": band * 1000 + index}


def _inputs(tmp_path):
    formal = {name: [_candidate(index, band=position + 1) for index in range(1, 4)]
              for position, name in enumerate(SPLITS)}
    qualification = {"functional": [_candidate(index, band=90) for index in range(1, 9)],
                     "load": [_candidate(index, band=91) for index in range(1, 41)]}
    source = {"schema_version": 1, "kind": "act_candidate_source", "config_sha256": "a" * 64,
              "minimum_gap_m": 0.02, "formal": formal, "qualification": qualification}
    source_path = tmp_path / "candidate-source.json"
    source_path.write_text(json.dumps(source))
    gates = {candidate_identity(item): {gate: {"ok": True, "evidence_sha256": "b" * 64}
                                        for gate in REACHABILITY_GATES}
             for name in SPLITS for item in formal[name]}
    report_path = tmp_path / "reachability.json"
    report_path.write_text(json.dumps({"schema_version": 1,
                                       "kind": "act_candidate_reachability",
                                       "gates": gates}))
    return source_path, report_path


def test_cli_writes_manifests_and_records_not_frozen(tmp_path):
    source_path, report_path = _inputs(tmp_path)
    output, collection = tmp_path / "split.json", tmp_path / "collection.json"
    assert main(["--candidate-source", str(source_path),
                 "--reachability-report", str(report_path),
                 "--output", str(output), "--collection-output", str(collection),
                 "--seed", "7"]) == 0
    manifest = json.loads(output.read_text())
    collection_manifest = json.loads(collection.read_text())
    assert {row["split"] for row in collection_manifest["scenarios"]} == set(COLLECTION_SPLITS)
    for path in (output, collection):
        provenance = json.loads(Path_provenance(path).read_text())
        assert provenance["status"] == NOT_FROZEN
        assert provenance["candidate_source_sha256"] and provenance["reachability_report_sha256"]


def Path_provenance(output):
    from pathlib import Path
    return Path(str(output) + ".provenance.json")


def test_cli_fails_closed_without_evidence_and_never_writes(tmp_path):
    source_path, report_path = _inputs(tmp_path)
    output, collection = tmp_path / "split.json", tmp_path / "collection.json"
    with pytest.raises(ValueError, match="TASK10_INPUTS_UNAVAILABLE"):
        main(["--candidate-source", str(tmp_path / "absent.json"),
              "--reachability-report", str(report_path),
              "--output", str(output), "--collection-output", str(collection), "--seed", "7"])
    assert not output.exists() and not collection.exists()
    # a report that does not hold the candidates refuses before any write
    empty_report = tmp_path / "empty-report.json"
    empty_report.write_text(json.dumps({"schema_version": 1,
                                        "kind": "act_candidate_reachability", "gates": {}}))
    with pytest.raises(ValueError, match="CANDIDATE_NOT_IN_REACHABILITY_REPORT"):
        main(["--candidate-source", str(source_path),
              "--reachability-report", str(empty_report),
              "--output", str(output), "--collection-output", str(collection), "--seed", "7"])
    assert not output.exists()


def test_cli_refuses_to_overwrite_and_projects_the_qualification_sets(tmp_path):
    source_path, report_path = _inputs(tmp_path)
    output, collection = tmp_path / "split.json", tmp_path / "collection.json"
    functional, load = tmp_path / "functional.json", tmp_path / "load.json"
    argv = ["--candidate-source", str(source_path), "--reachability-report", str(report_path),
            "--output", str(output), "--collection-output", str(collection), "--seed", "7",
            "--qualification-output", str(functional),
            "--qualification-load-output", str(load)]
    assert main(argv) == 0
    assert json.loads(functional.read_text())["count"] == 8
    assert json.loads(load.read_text())["count"] == 40
    assert json.loads(functional.read_text())["training_eligible"] is False
    with pytest.raises(ValueError, match="SAMPLING_OUTPUT_EXISTS"):
        main(argv)                      # a second run never overwrites published artifacts
