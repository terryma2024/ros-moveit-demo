"""Task 10: freeze the split, collection and qualification scene sets from supplied evidence.

Every input is explicit and evidence-bound: a closed candidate-source document and a reachability
report that answers for exact candidate identities. Nothing is inferred from calibration, no bounds or
budgets are invented, and no module is loaded by import path. If either input is absent or does not
verify, the run fails closed and **no manifest is written**.

Manifests written here are derived from *supplied* documents; they remain `NOT_FROZEN` until the later
runtime preflight produces those inputs, which each output records in its provenance sidecar.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from so101_demo.act.candidate_source import load_candidate_source, sampling_config
from so101_demo.act.sampling import (
    COLLECTION_SPLITS, SPLITS, assert_separated, make_manifest, project_collection_manifest,
)

NOT_FROZEN = "NOT_FROZEN_UNTIL_RUNTIME_PREFLIGHT"
_QUALIFICATION_OUTPUTS = {"functional": "qualification-output", "load": "qualification-load-output"}


def _digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write_new(path: Path, document: dict) -> None:
    """Write once, atomically, and never over an existing artifact."""

    path = Path(path)
    if path.exists() or path.is_symlink():
        raise ValueError("SAMPLING_OUTPUT_EXISTS")
    payload = json.dumps(document, sort_keys=True, indent=2).encode() + b"\n"
    temporary = path.with_name(path.name + ".partial")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _provenance(source_path, report_path, output: Path) -> None:
    _write_new(output.with_name(output.name + ".provenance.json"), {
        "schema_version": 1, "kind": "act_sampling_provenance", "status": NOT_FROZEN,
        "candidate_source_sha256": _digest(source_path),
        "reachability_report_sha256": _digest(report_path),
        "freeze_requires": "runtime_preflight_candidate_source_and_reachability_evidence",
    })


def _xy(candidate: dict) -> tuple[float, float]:
    return (float(candidate["xy"][0]), float(candidate["xy"][1]))


def _project_qualification(source: dict, name: str, *, gap_m: float) -> dict:
    """Deterministically project one supplied qualification set, checking separation first."""

    candidates = list(source["qualification"][name])
    for split in SPLITS:
        assert_separated([_xy(item) for item in candidates],
                         [_xy(item) for item in source["formal"][split]], gap_m)
    other = "load" if name == "functional" else "functional"
    assert_separated([_xy(item) for item in candidates],
                     [_xy(item) for item in source["qualification"][other]], gap_m)
    return {"schema_version": 1, "kind": "act_qualification_scenes", "set": name,
            "count": len(candidates), "candidates": candidates,
            "formal_separation_gap_m": gap_m, "training_eligible": False}


def main(argv: list[str] | None = None, *, load_source=load_candidate_source,
         make_port=None) -> int:
    parser = argparse.ArgumentParser(prog="act_sample", description=__doc__)
    parser.add_argument("--candidate-source", type=Path, required=True)
    parser.add_argument("--reachability-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--collection-output", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--qualification-output", type=Path)
    parser.add_argument("--qualification-load-output", type=Path)
    args = parser.parse_args(argv)

    if make_port is None:
        from so101_demo.adapters.act.reachability_report import ReachabilityReportPort

        make_port = ReachabilityReportPort.from_path
    if not args.candidate_source.is_file() or not args.reachability_report.is_file():
        # fail closed: absent production evidence means no manifest, and nothing is written
        raise ValueError("TASK10_INPUTS_UNAVAILABLE")

    source = load_source(args.candidate_source)
    port = make_port(args.reachability_report)
    config = sampling_config(source, candidate_port=port)
    manifest = make_manifest(config, args.seed)
    collection = project_collection_manifest(manifest)
    qualification = {}
    for name, attribute in _QUALIFICATION_OUTPUTS.items():
        target = getattr(args, attribute.replace("-", "_"))
        if target is not None:
            qualification[name] = (Path(target),
                                   _project_qualification(source, name,
                                                          gap_m=source["minimum_gap_m"]))

    # every check has passed: write, once each, with its provenance sidecar
    _write_new(args.output, manifest)
    _provenance(args.candidate_source, args.reachability_report, args.output)
    _write_new(args.collection_output, collection)
    _provenance(args.candidate_source, args.reachability_report, args.collection_output)
    for _name, (target, document) in sorted(qualification.items()):
        _write_new(target, document)
        _provenance(args.candidate_source, args.reachability_report, target)

    print(json.dumps({"status": NOT_FROZEN, "output": str(args.output),
                      "collection_output": str(args.collection_output),
                      "qualification": sorted(qualification),
                      "collection_splits": list(COLLECTION_SPLITS)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
