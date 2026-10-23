"""Citations, publication and the qualification aggregate."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from so101_demo.act.head_search_aggregate.contracts import (
    ACCEPTANCE_GATES,
    ANCHORS,
    CLOSED_REPORT_ARTIFACT,
    DECLARED_CONTRACTS,
    DECLARED_INPUTS,
    EVIDENCE_INCOMPLETE,
    FIT_WARNING,
    GATES,
    HOLDS,
    INFORMATIONAL_INPUTS,
    KIND,
    MISSING,
    MISSING_CODES,
    OPERATION,
    PHASE,
    QUALIFICATION_ARTIFACT,
    QUALIFICATION_GATES,
    QUALIFIED,
    REFUSED,
    SCHEMA_VERSION,
    VERDICT_ARTIFACT,
    VIOLATED,
    _path,
    _read_json,
    _Reasons,
    _require_new_root,
    _write,
    bare,
)
from so101_demo.act.head_search_aggregate.measurement_gates import (
    _gate_cadence,
    _gate_restarts,
    _gate_smoke,
    _gate_stops,
    _gate_teleop,
    _gate_terminals,
)
from so101_demo.act.head_search_aggregate.run_gates import (
    _gate_journal,
    _gate_ownership,
    _gate_runtime,
    _gate_values,
)
from so101_demo.act.head_search_binding import _CAMERA_MEASURED, _MEASURED
from so101_demo.perception_benchmark.contracts import canonical_sha256


def aggregate_qualification(
    inputs: Mapping[str, object], run_root: Path
) -> dict:
    """Consume the declared phase artefacts and publish a verdict, or the refusal that names them.

    The run root is claimed exclusively first, then every gate is evaluated against its own artefact.
    The verdict document is always written; the plan's Step 5 documents are written only when the nine
    qualification gates hold, and the verdict is ``HEAD_SEARCH_QUALIFIED`` only when the Teleop
    acceptance gate holds as well.
    """

    if not isinstance(inputs, Mapping):
        raise ValueError("the aggregate needs the declared evidence mapping")
    root = _require_new_root(run_root)
    reasons = _Reasons()

    unknown = sorted(
        str(key)
        for key in inputs
        if key not in DECLARED_INPUTS and key not in INFORMATIONAL_INPUTS
    )
    if unknown:
        for name in unknown:
            reasons.absent(
                "exclusive_ownership",
                EVIDENCE_INCOMPLETE,
                name,
                f"{name!r} is not a declared input of the aggregate phase: the declared inputs are "
                f"{list(DECLARED_INPUTS)}. An undeclared key is refused rather than ignored, because a "
                f"misspelled declaration would otherwise skip the gate it was meant to satisfy",
            )
    if not any(key in DECLARED_INPUTS for key in inputs):
        reasons.absent(
            "exclusive_ownership",
            EVIDENCE_INCOMPLETE,
            "evidence",
            "no declared evidence at all was presented, so this run has nothing to aggregate",
        )

    _write(
        root,
        "calibration-state.json",
        {"state": "RUNNING", "phase": PHASE, "run_root": str(root)},
    )

    ownership = _gate_ownership(inputs, root, reasons)
    runtime = _gate_runtime(inputs, ownership, reasons)
    values = _gate_values(inputs, root, runtime, reasons)
    journal = _gate_journal(inputs, runtime, reasons)
    terminals = _gate_terminals(journal, reasons)
    cadence = _gate_cadence(journal, reasons)
    stops = _gate_stops(journal, reasons)
    restarts = _gate_restarts(inputs, runtime, values, reasons)
    smoke = _gate_smoke(inputs, runtime, reasons)
    teleop = _gate_teleop(inputs, runtime, values, reasons)

    readings = {
        "exclusive_ownership": ownership,
        "runtime_identity": runtime,
        "approved_values_readback": values,
        "scenario_journal": {
            key: value for key, value in journal.items() if key not in ("entries", "rows")
        },
        "scenario_terminals": terminals,
        "frame_cadence": cadence,
        "stop_proofs": stops,
        "anchor_restarts": restarts,
        "production_smoke": smoke,
        "teleop_acceptance": teleop,
    }
    blocking = reasons.both()
    by_gate: dict[str, list[dict]] = {}
    for reason in blocking:
        by_gate.setdefault(str(reason["gate"]), []).append(reason)
    gates = {
        gate: {
            "status": (
                MISSING
                if any(reason["code"] in MISSING_CODES for reason in by_gate.get(gate, []))
                else VIOLATED
                if by_gate.get(gate)
                else HOLDS
            ),
            "reasons": len(by_gate.get(gate, [])),
            "codes": sorted({str(reason["code"]) for reason in by_gate.get(gate, [])}),
        }
        for gate in GATES
    }
    status = QUALIFIED if not blocking else REFUSED
    observed_runtime = runtime.get("runtime") if isinstance(runtime, Mapping) else None
    observed_runtime = observed_runtime if isinstance(observed_runtime, Mapping) else {}
    source_commit = str(observed_runtime.get("source_commit", ""))
    final_run = _path(inputs.get("final_run"))
    runtime_id = (
        f"{final_run.name}@{source_commit[:12]}" if final_run is not None and source_commit else ""
    )

    citations = _citations(
        inputs, root, ownership, values, journal, restarts, smoke, teleop
    )
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "operation": OPERATION,
        "phase": PHASE,
        "status": status,
        "verdict_status": status,
        "run_root": str(root),
        "runtime_id": runtime_id,
        "source_commit": source_commit or None,
        "declared_gates": list(GATES),
        "qualification_gates": list(QUALIFICATION_GATES),
        "acceptance_gates": list(ACCEPTANCE_GATES),
        "gates": gates,
        "missing": reasons.missing,
        "violations": reasons.violations,
        "blocking_reasons": blocking,
        "citations": citations,
        "checks": readings,
        "declared_contracts": DECLARED_CONTRACTS,
        "fit_warning": FIT_WARNING,
    }

    qualification_gates_hold = all(
        gates[gate]["status"] == HOLDS for gate in QUALIFICATION_GATES
    )
    document["qualification_document_status"] = (
        "PUBLISHED" if qualification_gates_hold else "NOT_PUBLISHED"
    )
    if qualification_gates_hold:
        _publish_qualification(
            root, document, citations, values, runtime_id, source_commit, journal, terminals
        )
    _write(root, VERDICT_ARTIFACT, document)
    _write(
        root,
        "calibration-state.json",
        {
            "state": status,
            "phase": PHASE,
            "run_root": str(root),
            "qualification_document_status": document["qualification_document_status"],
        },
    )
    return document


def _citations(
    inputs: Mapping,
    root: Path,
    ownership: Mapping,
    values: Mapping,
    journal: Mapping,
    restarts: Mapping,
    smoke: Mapping,
    teleop: Mapping,
) -> dict:
    """Every cited root, with the digest of the artefact that lives there; absent roots stay null."""

    def citation(readings: Mapping, *keys: str) -> dict | None:
        if not isinstance(readings, Mapping) or not readings:
            return None
        entry = {key: readings.get(key) for key in keys}
        if not any(entry.values()):
            return None
        # the cited root is the first declared location this evidence actually carries, so a citation is
        # never a key with a null root beside a populated digest
        entry["root"] = next(
            (
                entry.get(key)
                for key in ("root", "receipt", "journal", "document", "readback", "approved_bundle")
                if entry.get(key)
            ),
            None,
        )
        return entry

    citations: dict = {
        "production_smoke": citation(
            smoke, "root", "journal", "sha256", "sealed_journal", "sealed_journal_sha256"
        ),
        "scenarios": citation(
            journal, "root", "document", "document_sha256", "journal", "journal_sha256"
        ),
        "teleop_acceptance": citation(teleop, "receipt", "sha256", "qualification_report"),
        "ownership_receipt": citation(ownership, "receipt", "sha256"),
        "runtime_readback": citation(values, "readback", "sha256"),
        "approved_bundle": citation(values, "approved_bundle", "bundle_sha256"),
        "qualification_run_root": {"root": str(root)},
    }
    receipts = restarts.get("receipts") if isinstance(restarts, Mapping) else None
    receipts = receipts if isinstance(receipts, Mapping) else {}
    for anchor in ANCHORS:
        entry = receipts.get(anchor)
        citations[f"restart_{anchor}"] = (
            {"root": entry.get("path"), "receipt": entry.get("path"), "sha256": entry.get("sha256")}
            if isinstance(entry, Mapping)
            else None
        )
    return citations


def _publish_qualification(
    root: Path,
    verdict: Mapping,
    citations: Mapping,
    values: Mapping,
    runtime_id: str,
    source_commit: str,
    journal: Mapping,
    terminals: Mapping,
) -> None:
    """The plan's Step 5 documents: one PASS sample, the citations, and nothing the gates did not see."""

    observed = values.get("values") if isinstance(values, Mapping) else None
    del observed  # the readback's values are recomputed below from the same document
    readback = values.get("readback") if isinstance(values, Mapping) else None
    document_values = {}
    camera = values.get("camera_measurements") if isinstance(values, Mapping) else {}
    camera = camera if isinstance(camera, Mapping) else {}
    if readback:
        source, _ = _read_json(Path(str(readback)))
        if source is not None and isinstance(source.get("values"), Mapping):
            document_values = {name: bare(source["values"][name]) for name in _MEASURED}
    sample = {
        "status": "PASS",
        "values": document_values,
        "camera_measurements": {name: camera.get(name) for name in _CAMERA_MEASURED},
        "values_sha256": canonical_sha256(document_values) if document_values else None,
        "source_commit": source_commit or None,
        "runtime_id": runtime_id,
        "scenario_count": (journal.get("journal_rows") if isinstance(journal, Mapping) else None),
        "scenarios_passed": (
            terminals.get("passed") if isinstance(terminals, Mapping) else None
        ),
    }
    qualification = {
        "schema_version": SCHEMA_VERSION,
        "kind": "head_search_qualification",
        "status": "PASS",
        "operation": OPERATION,
        "run_root": str(root),
        "runtime_id": runtime_id,
        "source_commit": source_commit or None,
        "samples": [sample],
        "citations": citations,
        "gates": {
            gate: verdict["gates"][gate]["status"] for gate in QUALIFICATION_GATES
        },
        "verdict_sha256": canonical_sha256(
            {
                "gates": verdict["gates"],
                "citations": citations,
                "missing": verdict["missing"],
                "violations": verdict["violations"],
            }
        ),
    }
    _write(root, QUALIFICATION_ARTIFACT, qualification)
    report = {
        "status": QUALIFIED,
        "operation": OPERATION,
        "run_root": str(root),
        "runtime_id": runtime_id,
        "head_search_runtime_id": runtime_id,
        "source_commit": source_commit or None,
        "bundle_sha256": (
            values.get("bundle_sha256") if isinstance(values, Mapping) else None
        ),
        "citations": citations,
        "qualification_sha256": canonical_sha256(qualification),
        "qualification_verdict": verdict["verdict_status"],
    }
    _write(root, CLOSED_REPORT_ARTIFACT, report)
