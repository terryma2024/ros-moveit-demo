"""The `aggregate` phase: declared gates, and a refusal that names every missing item.

Every fixture here is synthetic and is written by `head_search_qualification_fixtures`: no stack, no
detector, no GPU and no ROS node is started, and nothing in this file measures anything. The point of the
file is the *gate*: a complete and consistent evidence set qualifies; remove or damage exactly one declared
item and the phase refuses, naming it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from head_search_qualification_fixtures import (
    ANCHORS,
    FIXTURE_CAMERA_MEASUREMENTS,
    FIXTURE_VALUES,
    Fixture,
    build_fixture,
    digest,
)
from so101_demo.act.head_search_aggregate.aggregate import aggregate_qualification
from so101_demo.act.head_search_aggregate.contracts import (
    ACCEPTANCE_GATES,
    CLOSED_REPORT_ARTIFACT,
    GATES,
    QUALIFICATION_ARTIFACT,
    QUALIFICATION_GATES,
    QUALIFIED,
    REFUSED,
    VERDICT_ARTIFACT,
)
from so101_demo.act.head_search_aggregate.run_gates import classify_qualification_terminal
from so101_demo.act.head_search_binding import _CAMERA_MEASURED, _MEASURED
from so101_demo.act.head_search_scenarios.contracts import ARTIFACT, EVIDENCE_DIR, JOURNAL_ARTIFACT
from so101_demo.act.head_search_scenarios.journal import aggregate_scenarios, scenario_journal_entry
from so101_demo.perception_benchmark.contracts import canonical_sha256


def _fixture(tmp_path: Path) -> Fixture:
    return build_fixture(tmp_path / "evidence", run_root=tmp_path / "qualification-run")


def _verdict(fixture: Fixture, **overrides) -> dict:
    return aggregate_qualification(fixture.inputs(**overrides), fixture.run_root)


def _blocking(document: dict, gate: str) -> list[dict]:
    return [
        reason
        for reason in document["missing"] + document["violations"]
        if reason["gate"] == gate
    ]


def _seed_entries(fixture: Fixture) -> dict[int, dict]:
    directory = fixture.paths["scenario_evidence_dir"]
    entries = {}
    for path in sorted(directory.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        entries[int(document["seed"])] = document
    return entries


def _rebuild_scenarios(fixture: Fixture, entries: dict[int, dict]) -> None:
    """Re-project the journal rows and the document from the per-scenario evidence on disk."""

    ordered = [entries[seed] for seed in sorted(entries)]
    rows = [scenario_journal_entry(entry) for entry in ordered]
    for entry in ordered:
        (fixture.paths["scenario_evidence_dir"] / f"{entry['seed']}.json").write_text(
            json.dumps(entry, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    fixture.paths["scenarios_journal"].write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )
    document = json.loads(fixture.paths["scenarios_document"].read_text(encoding="utf-8"))
    aggregate = aggregate_scenarios(ordered)
    for key in (
        "scenario_count",
        "passed_count",
        "failed_count",
        "refused_count",
        "by_condition_class",
        "by_anchor",
        "terminal_statuses",
        "zero_wrong_locks",
        "wrong_locks",
        "cadence_all_continuous",
        "stop_proofs_all_proven",
    ):
        document[key] = aggregate[key]
    document["records"] = rows
    document["sha256"] = canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    fixture.paths["scenarios_document"].write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _non_lock_seed(entries: dict[int, dict]) -> int:
    """A scenario whose condition class never declares a lock, so a lock there is unambiguous damage."""

    return next(
        seed
        for seed in sorted(entries)
        if entries[seed]["condition_class"] in ("no_cup", "two_cups")
    )


def _damage_one_scenario(fixture: Fixture, mutate) -> int:
    """Damage exactly one scenario, keep every cross-reference consistent, and return its seed."""

    entries = _seed_entries(fixture)
    seed = _non_lock_seed(entries)
    mutate(entries[seed])
    _rebuild_scenarios(fixture, entries)
    return seed


# --- the passing fixture ----------------------------------------------------------------------------


def test_a_complete_fixture_set_qualifies_and_publishes_the_plan_documents(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    document = _verdict(fixture)

    assert document["status"] == QUALIFIED, json.dumps(document["blocking_reasons"], indent=1)
    assert document["verdict_status"] == QUALIFIED
    assert document["missing"] == [] and document["violations"] == []
    for gate in GATES:
        assert document["gates"][gate]["status"] == "HOLDS", gate

    # the exact phase-root citations the plan's Step 5 requires
    citations = document["citations"]
    for phase in (
        "production_smoke",
        "scenarios",
        "restart_default",
        "restart_left",
        "restart_forward",
        "teleop_acceptance",
    ):
        assert citations[phase] is not None and citations[phase]["root"], phase
    # a citation's root is its own evidence, never another item the same gate happened to read
    assert citations["approved_bundle"]["root"] == str(fixture.paths["approved_bundle"])
    assert citations["runtime_readback"]["root"] == str(fixture.paths["runtime_readback"])

    qualification = json.loads((fixture.run_root / QUALIFICATION_ARTIFACT).read_text())
    assert qualification["status"] == "PASS"
    assert len(qualification["samples"]) == 1
    sample = qualification["samples"][0]
    assert set(sample["values"]) == set(_MEASURED) and len(sample["values"]) == 17
    assert set(sample["camera_measurements"]) == set(_CAMERA_MEASURED)
    assert set(qualification["citations"]) >= set(citations)
    assert (fixture.run_root / VERDICT_ARTIFACT).is_file()

    report = json.loads((fixture.run_root / CLOSED_REPORT_ARTIFACT).read_text())
    assert report["status"] == "HEAD_SEARCH_QUALIFIED"
    assert report["bundle_sha256"] == digest(fixture.paths["approved_bundle"])
    from so101_demo.act.head_search_qualification import require_gate

    with pytest.raises(ValueError, match="PICK_PLACE_LIVE_GATE_REFUSED"):
        require_gate(report, "pick_place_live")


def test_the_declared_gate_list_is_exactly_the_plan_and_task_gates() -> None:
    assert GATES == QUALIFICATION_GATES + ACCEPTANCE_GATES
    assert set(GATES) == {
        "exclusive_ownership",
        "runtime_identity",
        "approved_values_readback",
        "scenario_journal",
        "scenario_terminals",
        "frame_cadence",
        "stop_proofs",
        "anchor_restarts",
        "production_smoke",
        "teleop_acceptance",
    }


def test_a_hex_only_evidence_set_can_never_qualify(tmp_path: Path) -> None:
    """The HS-233/HS-315 defect: any well-formed digest used to be enough to publish a pass."""

    fixture = _fixture(tmp_path)
    document = aggregate_qualification(
        {"evidence": {name: "a" * 64 for name in ("production_smoke", "scenarios", "restarts")}},
        fixture.run_root,
    )
    assert document["status"] == REFUSED
    assert not (fixture.run_root / CLOSED_REPORT_ARTIFACT).exists()
    assert not (fixture.run_root / QUALIFICATION_ARTIFACT).exists()
    assert {reason["code"] for reason in document["missing"]} >= {
        "HEAD_SEARCH_QUALIFICATION_EVIDENCE_INCOMPLETE"
    }


def test_an_unknown_declared_input_is_refused_rather_than_silently_skipped(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    document = _verdict(fixture, prodution_smoke_root=fixture.paths["production_smoke_root"])
    assert document["status"] == REFUSED
    assert any("prodution_smoke_root" in reason["item"] for reason in document["missing"])


# --- each gate missing in turn ----------------------------------------------------------------------


def _drop_ownership(fixture: Fixture):
    return fixture.inputs_without("ownership_receipt")


def _break_runtime_identity(fixture: Fixture):
    (fixture.paths["final_run"] / "source-commit.txt").unlink()
    return fixture.inputs()


def _drop_values_readback(fixture: Fixture):
    return fixture.inputs_without("runtime_readback")


def _drop_scenario_journal(fixture: Fixture):
    fixture.paths["scenarios_journal"].unlink()
    return fixture.inputs()


def _wrong_lock_terminal(fixture: Fixture):
    def mutate(entry):
        entry["terminal_status"] = "TARGET_LOCKED"
        entry["found"] = True
        entry["locked"] = True
        entry["cup_found"] = True

    _damage_one_scenario(fixture, mutate)
    return fixture.inputs()


def _broken_cadence(fixture: Fixture):
    _damage_one_scenario(fixture, lambda entry: entry["frame_cadence"].update(continuous=False))
    return fixture.inputs()


def _unproven_stop(fixture: Fixture):
    _damage_one_scenario(fixture, lambda entry: entry["stop_proof"].update(proven=False))
    return fixture.inputs()


def _drop_restart_receipts(fixture: Fixture):
    return fixture.inputs_without("restart_receipts")


def _drop_restart_left(fixture: Fixture):
    declared = fixture.inputs()
    declared["restart_receipts"] = [
        path
        for path in declared["restart_receipts"]
        if path.name != "restart-left-receipt.json"
    ]
    return declared


def _drop_smoke(fixture: Fixture):
    return fixture.inputs_without("production_smoke_root")


def _drop_teleop(fixture: Fixture):
    return fixture.inputs_without("teleop_acceptance_receipt")


GATE_DAMAGE = {
    "exclusive_ownership": _drop_ownership,
    "runtime_identity": _break_runtime_identity,
    "approved_values_readback": _drop_values_readback,
    "scenario_journal": _drop_scenario_journal,
    "scenario_terminals": _wrong_lock_terminal,
    "frame_cadence": _broken_cadence,
    "stop_proofs": _unproven_stop,
    "anchor_restarts": _drop_restart_receipts,
    "production_smoke": _drop_smoke,
    "teleop_acceptance": _drop_teleop,
}


@pytest.mark.parametrize("gate", GATES)
def test_each_gate_missing_in_turn_refuses_and_names_that_gate(tmp_path: Path, gate: str) -> None:
    fixture = _fixture(tmp_path)
    declared = GATE_DAMAGE[gate](fixture)
    document = aggregate_qualification(declared, fixture.run_root)

    assert document["status"] == REFUSED
    assert document["verdict_status"] == REFUSED
    assert document["gates"][gate]["status"] != "HOLDS"
    reasons = _blocking(document, gate)
    assert reasons, f"the refusal did not name the {gate!r} gate"
    assert all(reason["item"] for reason in reasons)
    if gate in ACCEPTANCE_GATES:
        # the plan's own ordering runs the acceptance after the qualifier returns, so the closed
        # report the acceptance consumed exists while the verdict is still REFUSED: the declaration
        # is explicit in the verdict and the exit code is non-zero
        assert document["qualification_document_status"] == "PUBLISHED"
        report = json.loads((fixture.run_root / CLOSED_REPORT_ARTIFACT).read_text())
        assert report["qualification_verdict"] == REFUSED
    else:
        assert document["qualification_document_status"] == "NOT_PUBLISHED"
        assert not (fixture.run_root / CLOSED_REPORT_ARTIFACT).exists()
        assert not (fixture.run_root / QUALIFICATION_ARTIFACT).exists()


def test_a_missing_declared_evidence_item_is_named_one_by_one(tmp_path: Path) -> None:
    """Every one of the four items that really are missing today must appear in the refusal."""

    fixture = _fixture(tmp_path)
    document = aggregate_qualification(
        fixture.inputs_without(
            "production_smoke_root",
            "restart_receipts",
            "teleop_acceptance_receipt",
            "runtime_readback",
        ),
        fixture.run_root,
    )
    assert document["status"] == REFUSED
    named = {reason["gate"] for reason in document["missing"]}
    assert named == {
        "production_smoke",
        "anchor_restarts",
        "teleop_acceptance",
        "approved_values_readback",
    }
    items = " ".join(str(reason["item"]) for reason in document["missing"])
    assert "production_smoke" in items
    assert {reason["item"] for reason in document["missing"]} >= {
        "restart_receipts",
        "teleop_acceptance_receipt",
        "runtime_readback",
    }


def test_a_citation_is_null_when_its_evidence_was_never_presented(tmp_path: Path) -> None:
    """A citation points at presented evidence or at nothing - never at a path that does not exist."""

    fixture = _fixture(tmp_path)
    document = aggregate_qualification(
        fixture.inputs_without(
            "runtime_readback", "restart_receipts", "teleop_acceptance_receipt"
        ),
        fixture.run_root,
    )
    citations = document["citations"]
    assert citations["runtime_readback"] is None
    assert citations["restart_default"] is None
    assert citations["restart_left"] is None
    assert citations["restart_forward"] is None
    assert citations["teleop_acceptance"] is None
    assert citations["scenarios"]["root"] == str(fixture.paths["scenarios_root"])
    assert citations["scenarios"]["document_sha256"]
    assert citations["approved_bundle"]["root"] == str(fixture.paths["approved_bundle"])
    assert citations["approved_bundle"]["bundle_sha256"] == digest(fixture.paths["approved_bundle"])
    assert citations["ownership_receipt"]["root"] == str(fixture.paths["ownership_receipt"])


def test_the_three_restart_receipts_must_cover_every_anchor_exactly_once(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    document = aggregate_qualification(_drop_restart_left(fixture), fixture.run_root)
    reasons = _blocking(document, "anchor_restarts")
    assert document["status"] == REFUSED
    assert any("left" in reason["detail"] for reason in reasons)


# --- tampering --------------------------------------------------------------------------------------


def test_a_tampered_scenarios_digest_is_refused(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    document = json.loads(fixture.paths["scenarios_document"].read_text(encoding="utf-8"))
    document["passed_count"] = 39
    document["failed_count"] = 1
    fixture.paths["scenarios_document"].write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    verdict = _verdict(fixture)
    assert verdict["status"] == REFUSED
    assert any(
        reason["code"] == "QUAL_AGGREGATE_DIGEST_MISMATCH"
        for reason in _blocking(verdict, "scenario_journal")
    )


def test_a_tampered_journal_row_is_refused(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    rows = [
        json.loads(line)
        for line in fixture.paths["scenarios_journal"].read_text(encoding="utf-8").splitlines()
    ]
    index = next(
        position
        for position, row in enumerate(rows)
        if row["condition_class"] in ("no_cup", "two_cups")
    )
    rows[index]["terminal_status"] = "TARGET_LOCKED"
    fixture.paths["scenarios_journal"].write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )
    verdict = _verdict(fixture)
    assert verdict["status"] == REFUSED
    assert _blocking(verdict, "scenario_journal")


def test_a_tampered_per_scenario_evidence_document_is_refused(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    entries = _seed_entries(fixture)
    seed = _non_lock_seed(entries)
    entries[seed]["terminal_status"] = "TARGET_LOCKED"
    (fixture.paths["scenario_evidence_dir"] / f"{seed}.json").write_text(
        json.dumps(entries[seed], indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    verdict = _verdict(fixture)
    assert verdict["status"] == REFUSED
    assert _blocking(verdict, "scenario_journal")


def test_a_tampered_approved_bundle_is_refused(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    document = json.loads(fixture.paths["approved_bundle"].read_text(encoding="utf-8"))
    document["parameters"]["max_fine_corrections"]["value"] = 99
    fixture.paths["approved_bundle"].write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    verdict = _verdict(fixture)
    assert verdict["status"] == REFUSED
    assert _blocking(verdict, "approved_values_readback")


def test_a_seed_the_partitions_do_not_declare_is_refused(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    document = json.loads(fixture.paths["scenarios_document"].read_text(encoding="utf-8"))
    document["seeds"] = sorted(document["seeds"])[:-1]
    document["sha256"] = canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    fixture.paths["scenarios_document"].write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    verdict = _verdict(fixture)
    assert verdict["status"] == REFUSED
    assert _blocking(verdict, "scenario_journal")


# --- the classification rule ------------------------------------------------------------------------


def _entry(condition_class: str, terminal: str | None, *, coverage_complete: bool = True) -> dict:
    entry = {
        "condition_class": condition_class,
        "seed": 900000,
        "terminal_status": terminal,
        "coverage": {"complete": coverage_complete},
        "stop_proof": {"proven": True},
        "frame_cadence": {"continuous": True},
        "attempts": [
            {
                "interruption_injected": True,
                "stop": True,
                "lock_count_cleared_by_interruption": True,
                "detector_reset_before_attempt": False,
            },
            {"interruption_injected": False, "detector_reset_before_attempt": True},
        ],
    }
    entry["attempts"][-1]["detector_reset_before_attempt"] = True
    return entry


@pytest.mark.parametrize(
    ("condition_class", "terminal"),
    [
        ("nominal", "TARGET_LOCKED"),
        ("two_cups", "TARGET_AMBIGUOUS"),
        ("no_cup", "TARGET_NOT_FOUND"),
    ],
)
def test_the_three_declared_terminals_pass(condition_class: str, terminal: str) -> None:
    verdict = classify_qualification_terminal(_entry(condition_class, terminal))
    assert verdict["verdict"] == "PASSED", verdict


@pytest.mark.parametrize(
    ("condition_class", "terminal", "coverage_complete", "code"),
    [
        ("no_cup", "TARGET_LOCKED", True, "QUAL_AGGREGATE_WRONG_LOCK"),
        ("two_cups", "TARGET_LOCKED", True, "QUAL_AGGREGATE_WRONG_LOCK"),
        ("nominal", "TARGET_AMBIGUOUS", True, "QUAL_AGGREGATE_TERMINAL_NOT_DECLARED"),
        ("nominal", "TARGET_NOT_FOUND", True, "QUAL_AGGREGATE_TERMINAL_NOT_DECLARED"),
        ("no_cup", "TARGET_NOT_FOUND", False, "QUAL_AGGREGATE_COVERAGE_INCOMPLETE"),
        (
            "nominal",
            "TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL",
            True,
            "QUAL_AGGREGATE_COVERAGE_INCOMPLETE",
        ),
        ("nominal", "TARGET_NOT_CENTERED", True, "QUAL_AGGREGATE_TERMINAL_NOT_DECLARED"),
        ("nominal", None, True, "QUAL_AGGREGATE_NO_TERMINAL"),
        ("nominal", "SOMETHING_ELSE", True, "QUAL_AGGREGATE_TERMINAL_NOT_DECLARED"),
    ],
)
def test_anything_other_than_the_declared_terminal_fails(
    condition_class: str, terminal, coverage_complete: bool, code: str
) -> None:
    verdict = classify_qualification_terminal(
        _entry(condition_class, terminal, coverage_complete=coverage_complete)
    )
    assert verdict["verdict"] != "PASSED"
    assert verdict["code"] == code, verdict


def test_an_interruption_class_that_never_interrupted_is_refused() -> None:
    entry = _entry("fast_interruption", "TARGET_LOCKED")
    entry["attempts"] = [
        {"interruption_injected": False, "detector_reset_before_attempt": True},
    ]
    verdict = classify_qualification_terminal(entry)
    assert verdict["verdict"] != "PASSED"
    assert verdict["code"] == "QUAL_AGGREGATE_INTERRUPTION_UNPROVEN"


def test_a_journalled_pass_the_rule_calls_a_failure_is_a_violation(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    # a no_cup scenario that locked, with the producer's own outcome still reading PASSED
    entries = _seed_entries(fixture)
    seed = next(
        seed for seed, entry in entries.items() if entry["condition_class"] == "no_cup"
    )
    entries[seed]["terminal_status"] = "TARGET_LOCKED"
    entries[seed]["found"] = True
    entries[seed]["cup_found"] = True
    _rebuild_scenarios(fixture, entries)
    verdict = _verdict(fixture)
    assert verdict["status"] == REFUSED
    reasons = _blocking(verdict, "scenario_terminals")
    assert any(str(seed) in reason["item"] for reason in reasons)
    assert verdict["gates"]["scenario_journal"]["status"] == "HOLDS"
    assert verdict["gates"]["frame_cadence"]["status"] == "HOLDS"
    assert verdict["gates"]["stop_proofs"]["status"] == "HOLDS"


def test_every_anchor_has_a_restart_receipt_for_a_declared_anchor(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    document = _verdict(fixture)
    for anchor in ANCHORS:
        assert document["citations"][f"restart_{anchor}"]["root"]
    assert set(FIXTURE_VALUES) == set(_MEASURED)
    assert set(FIXTURE_CAMERA_MEASUREMENTS) == set(_CAMERA_MEASURED)
    assert (fixture.paths["scenario_evidence_dir"] / EVIDENCE_DIR).name == EVIDENCE_DIR
    assert ARTIFACT in {path.name for path in fixture.paths["scenarios_root"].iterdir()}
    assert JOURNAL_ARTIFACT in {path.name for path in fixture.paths["scenarios_root"].iterdir()}
    assert VERDICT_ARTIFACT not in {path.name for path in fixture.paths["scenarios_root"].iterdir()}
