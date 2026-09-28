"""Task 10 closed inputs: the candidate-source document and the reachability-report port."""

import hashlib
import json
from pathlib import Path

import pytest

from so101_demo.act.candidate_source import (
    candidate_identity, load_candidate_source, sampling_config,
)
from so101_demo.act.sampling import REACHABILITY_GATES, SPLITS


def _candidate(index, *, split_seed):
    return {"xy": [index * 0.01, 0.0], "arm_q": [0.0] * 6, "search_start_rad": 0.0,
            "seed": split_seed * 1000 + index}


def _source_document(tmp_path):
    formal = {name: [_candidate(index, split_seed=position)
                     for index in range(1, 4)]
              for position, name in enumerate(SPLITS)}
    qualification = {
        "functional": [_candidate(index, split_seed=90) for index in range(1, 9)],
        "load": [_candidate(index, split_seed=91) for index in range(1, 41)],
    }
    document = {"schema_version": 1, "kind": "act_candidate_source",
                "config_sha256": "a" * 64, "minimum_gap_m": 0.02,
                "formal": formal, "qualification": qualification}
    path = tmp_path / "candidate-source.json"
    path.write_text(json.dumps(document))
    return path, document


def test_candidate_source_closes_counts_identities_and_overlap(tmp_path):
    path, document = _source_document(tmp_path)
    source = load_candidate_source(path)
    assert source["minimum_gap_m"] == 0.02
    assert len(source["qualification"]["functional"]) == 8
    assert len(source["qualification"]["load"]) == 40

    bad_counts = json.loads(json.dumps(document))
    bad_counts["qualification"]["load"] = bad_counts["qualification"]["load"][:39]
    (tmp_path / "short.json").write_text(json.dumps(bad_counts))
    with pytest.raises(ValueError, match="QUALIFICATION_CANDIDATE_COUNT_INVALID"):
        load_candidate_source(tmp_path / "short.json")

    overlap = json.loads(json.dumps(document))
    overlap["qualification"]["functional"][0] = overlap["formal"]["train"][0]
    (tmp_path / "overlap.json").write_text(json.dumps(overlap))
    with pytest.raises(ValueError, match="QUALIFICATION_FORMAL_OVERLAP"):
        load_candidate_source(tmp_path / "overlap.json")

    zero_gap = json.loads(json.dumps(document))
    zero_gap["minimum_gap_m"] = 0.0
    (tmp_path / "gap.json").write_text(json.dumps(zero_gap))
    with pytest.raises(ValueError, match="SPLIT_GAP_INVALID"):
        load_candidate_source(tmp_path / "gap.json")

    unknown_key = json.loads(json.dumps(document))
    unknown_key["bounds"] = [0, 1]
    (tmp_path / "extra.json").write_text(json.dumps(unknown_key))
    with pytest.raises(ValueError, match="CANDIDATE_SOURCE_INVALID"):
        load_candidate_source(tmp_path / "extra.json")


def test_sampling_config_requires_a_verifying_port(tmp_path):
    path, _ = _source_document(tmp_path)
    source = load_candidate_source(path)

    class Port:
        def verify(self, item):
            return {name: True for name in REACHABILITY_GATES}

    config = sampling_config(source, candidate_port=Port())
    assert set(config["candidates"]) == set(SPLITS)
    with pytest.raises(ValueError, match="CANDIDATE_PORT_REQUIRED"):
        sampling_config(source, candidate_port=object())


def test_reachability_port_answers_only_for_exact_supplied_identities(tmp_path):
    from so101_demo.adapters.act.reachability_report import ReachabilityReportPort

    path, document = _source_document(tmp_path)
    candidate = document["formal"]["train"][0]
    identity = candidate_identity(candidate)
    report = {"schema_version": 1, "kind": "act_candidate_reachability",
              "gates": {identity: {name: {"ok": True, "evidence_sha256": "b" * 64}
                                   for name in REACHABILITY_GATES}}}
    report_path = tmp_path / "reachability.json"
    report_path.write_text(json.dumps(report))
    port = ReachabilityReportPort.from_path(report_path)
    verdicts = port.verify(candidate)
    assert set(verdicts) == set(REACHABILITY_GATES) and all(verdicts.values())
    # an identity the report does not hold is refused, never guessed
    with pytest.raises(ValueError, match="CANDIDATE_NOT_IN_REACHABILITY_REPORT"):
        port.verify(document["formal"]["train"][1])
    # a gate without its evidence hash invalidates the whole report
    broken = json.loads(json.dumps(report))
    broken["gates"][identity]["head_visible"] = {"ok": True}
    broken_path = tmp_path / "broken.json"
    broken_path.write_text(json.dumps(broken))
    with pytest.raises(ValueError, match="REACHABILITY_REPORT_INVALID"):
        ReachabilityReportPort.from_path(broken_path)
