"""P1-2 (rereview4): one ten-field identity rule, end to end, with no rewriting.

The verdict's finding: `task8_measurement_contract.py` preserves the input identity and then computes a BOUND-DOCUMENT
self-digest that contains it; the CLI requires a sealed batch's identity to equal the admitted one exactly; and
`task8_calibration_aggregator.py` instead requires the batch's `measurement_contract_sha256` to equal the
bound-document self-digest. Those are two different quantities, so - unless a fixture rewrites the field - a batch the
formal entry seals is refused by the aggregator as a foreign contract.

Measured before writing this file (CP-1672): with the repo's own fixtures,
    identity["measurement_contract_sha256"] (declared, admitted by the CLI) = 080808080808…
    bound_document["contract_sha256"]        (what the aggregator compares) = 53cb2428e922…
so the two are NOT equal, and `batch_factory`'s rewrite is exactly the workaround the verdict calls "not an end-to-end
fix".

What this file requires:
  1. a batch sealed by the FORMAL ENTRY reaches the REAL aggregator with no rewriting and no resealing;
  2. a batch naming a DIFFERENT contract is still refused (the foreign-contract negative).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _formally_sealed(tmp_path, monkeypatch):
    """Run the formal entry (no `--driver`, no provider seam) and return its sealed batch plus its bound contract."""

    from test_act_task8_formal_measurement_entry import _formal_run

    measure, argv = _formal_run(tmp_path, monkeypatch)
    assert measure.main(argv) == 0, "the formal entry must seal before this file can judge what it sealed"
    return (tmp_path / "batch",
            Path(argv[argv.index("--contract") + 1]),
            json.loads((tmp_path / "batch" / "batch.json").read_bytes()))


def test_a_formally_sealed_batch_reaches_the_aggregator_without_rewriting(tmp_path, monkeypatch):
    """The end-to-end rule: what the entry seals is what the aggregator must accept."""

    from so101_demo.act.task8_calibration_aggregator import aggregate_task8_calibration

    batch_root, bound_path, sealed = _formally_sealed(tmp_path, monkeypatch)
    contract = json.loads(bound_path.read_bytes())

    # the two quantities, so a failure says WHICH contract rule disagreed
    declared = sealed["identity"]["measurement_contract_sha256"]
    bound_self = contract["contract_sha256"]

    # P1-2 (rereview 5): this used to be a `try/except ValueError` that only asserted the refusal was not
    # `CALIBRATION_IDENTITY_MISMATCH` - so a TOTAL aggregator failure (`RAW_EVIDENCE_REQUIRED`) still produced GREEN.
    # The rule is the end-to-end one: the entry's seal must be CONSUMED, and the consumption must produce output.
    output_root = tmp_path / "out"
    report = aggregate_task8_calibration([batch_root], contract, output_root)
    assert isinstance(report, dict) and report, "the aggregator returns a report rather than raising"

    # real output: a field-verdict set recomputed from the sealed raw records, and a report document on disk
    verdicts = report.get("field_verdicts") or report.get("verdicts") or {}
    assert verdicts, f"the aggregator recomputed measurements from the sealed batch: {sorted(report)}"
    recomputed = [field for field, value in verdicts.items() if value != "UNMEASURED"]
    assert recomputed, (
        "and at least one field was recomputed from raw evidence rather than declared UNMEASURED: "
        f"{verdicts} (seal names {declared[:16]}…, bound document's self-digest is {bound_self[:16]}…)")
    written = sorted(path.name for path in output_root.rglob("*.json"))
    assert written, f"the aggregation published its documents: {output_root}"


def test_a_batch_naming_another_contract_is_still_refused(tmp_path, monkeypatch):
    """And the consistency must not become an absence of the rule: a foreign contract is a refusal."""

    from so101_demo.act.task8_calibration_aggregator import aggregate_task8_calibration
    from so101_demo.act.task8_measurement_contract import close_measurement_batch

    batch_root, bound_path, sealed = _formally_sealed(tmp_path, monkeypatch)
    contract = json.loads(bound_path.read_bytes())

    foreign = tmp_path / "foreign-batch"
    foreign.mkdir()
    for entry in sorted(batch_root.rglob("*")):
        if entry.is_file() and entry.name != "batch.json":
            target = foreign / entry.relative_to(batch_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(entry.read_bytes())
    identity = dict(sealed["identity"])
    identity["measurement_contract_sha256"] = "f" * 64          # names a contract that is not this one
    close_measurement_batch(foreign, identity, status="CLOSED",
                            cleanup={"group_clear": True, "generation": "g1", "reason": "foreign-contract negative"})

    with pytest.raises(ValueError, match="CALIBRATION_IDENTITY_MISMATCH"):
        aggregate_task8_calibration([foreign], contract, tmp_path / "out-foreign")
