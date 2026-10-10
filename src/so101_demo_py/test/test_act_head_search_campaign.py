"""Head-only campaign verdicts preserve expected negatives and missing evidence."""

import copy
import importlib
import json
from pathlib import Path

import pytest


PARTITIONS = Path(__file__).parents[1] / "config/act/head-search-scenario-partitions-v1.json"


def campaign():
    return importlib.import_module("so101_demo.act.head_search_campaign")


def partitions():
    return json.loads(PARTITIONS.read_text())


def case(condition="nominal"):
    return next(c for c in campaign().load_cases(partitions())
                if c["condition_class"] == condition)


def attempt(index=1, terminal="TARGET_LOCKED"):
    return {
        "identity": {"run_id": f"run-{index}", "session_id": f"session-{index}",
                     "epoch": f"epoch-{index}", "generation": index},
        "admission": "VALID", "original_terminal": terminal,
        "business_rc": 0 if terminal == "TARGET_LOCKED" else 1,
        "actual_os_return_code": 0 if terminal == "TARGET_LOCKED" else 1,
        "audit_rc": 0,
        "audit": {"integrity": "PASS", "execution": "PASS",
                  "stop": "PASS", "exit_cleanup": "PASS"},
        "truth": {"status": "PASS", "target": "CORRECT",
                  "coverage_complete": True},
        "non_neck_dispatch": 0, "wrong_locks": 0,
    }


def test_matrix_keeps_declared_order_and_anchor_without_mutating_partition():
    original = partitions()
    before = copy.deepcopy(original)
    rows = campaign().load_cases(original)
    assert original == before
    assert [r["seed"] for r in rows] == list(range(900000, 900040))
    assert [r["anchor"] for r in rows] == [r["anchor"] for r in before["qualification"]]
    assert len({r["case_id"] for r in rows}) == 40
    assert sum(r["expected_attempt_count"] for r in rows) == 48
    rows[0]["anchor"] = "changed"
    assert original == before


@pytest.mark.parametrize("defect", ["bool_seed", "duplicate", "split_overlap", "class",
                                    "anchor", "scene_group", "reordered", "missing"])
def test_bad_matrix_refused(defect):
    document = partitions()
    if defect == "bool_seed":
        document["qualification"][0]["seed"] = True
    elif defect == "duplicate":
        document["qualification"][1]["seed"] = 900000
    elif defect == "split_overlap":
        document["calibration"][0] = 900000
    elif defect == "class":
        document["qualification"][0]["condition_class"] = "two_cups"
    elif defect == "anchor":
        document["qualification"][0]["anchor"] = "unknown"
    elif defect == "scene_group":
        document["qualification"][1]["scene_group_id"] = document["qualification"][0]["scene_group_id"]
    elif defect == "reordered":
        document["qualification"].reverse()
    else:
        document["qualification"].pop()
    with pytest.raises(ValueError):
        campaign().load_cases(document)


def test_correct_lock_passes_with_original_facts_retained():
    facts = attempt()
    before = copy.deepcopy(facts)
    result = campaign().classify_case(case(), [facts])
    assert result["status"] == "PASS"
    assert result["qualified"] is False
    assert result["attempts"] == [before]
    assert facts == before


def test_two_cups_expected_business_failure_can_be_case_pass():
    facts = attempt(terminal="TARGET_AMBIGUOUS")
    facts["truth"]["target"] = "AMBIGUOUS"
    result = campaign().classify_case(case("two_cups"), [facts])
    assert result["status"] == "PASS"
    assert result["attempts"][0]["business_rc"] == 1


def test_no_cup_requires_actual_complete_coverage():
    facts = attempt(terminal="TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL")
    facts["truth"]["target"] = "ABSENT"
    assert campaign().classify_case(case("no_cup"), [facts])["status"] == "PASS"
    facts["truth"]["coverage_complete"] = False
    assert campaign().classify_case(case("no_cup"), [facts])["status"] == "FAIL"


@pytest.mark.parametrize("field,value,expected", [
    ("stop", "UNKNOWN", "UNKNOWN"), ("exit_cleanup", "UNKNOWN", "UNKNOWN"),
    ("execution", "FAIL", "FAIL"), ("integrity", "FAIL", "FAIL"),
])
def test_audit_rc_zero_does_not_mask_individual_rule_results(field, value, expected):
    facts = attempt()
    facts["audit"][field] = value
    assert campaign().classify_case(case(), [facts])["status"] == expected


@pytest.mark.parametrize("defect,expected", [
    ("wrong_target", "FAIL"), ("wrong_locks", "FAIL"), ("illegal_dispatch", "FAIL"),
    ("missing_truth", "UNKNOWN"), ("bool_rc", "INVALID"),
    ("bool_dispatch", "INVALID"), ("bool_generation", "INVALID"),
    ("missing_audit_field", "UNKNOWN"), ("rc_conflict", "INVALID"),
])
def test_missing_or_unsafe_facts_never_pass(defect, expected):
    facts = attempt()
    if defect == "wrong_target": facts["truth"]["target"] = "WRONG"
    elif defect == "wrong_locks": facts["wrong_locks"] = 1
    elif defect == "illegal_dispatch": facts["non_neck_dispatch"] = 1
    elif defect == "missing_truth": facts.pop("truth")
    elif defect == "bool_rc": facts["business_rc"] = False
    elif defect == "bool_dispatch": facts["non_neck_dispatch"] = False
    elif defect == "bool_generation": facts["identity"]["generation"] = True
    elif defect == "missing_audit_field": facts["audit"].pop("execution")
    else: facts["actual_os_return_code"] = 1
    assert campaign().classify_case(case(), [facts])["status"] == expected


@pytest.mark.parametrize("condition,kind,terminal", [
    ("fast_interruption", "camera_loss", "FAULT"),
    ("reacquire_after_stop", "signal_stop", "INTERRUPTED"),
])
def test_interrupt_needs_real_first_trigger_and_fresh_second_identity(condition, kind, terminal):
    first = attempt(terminal=terminal)
    first["injection"] = {"status": "PASS", "kind": kind, "before_locked": True}
    second = attempt(2)
    assert campaign().classify_case(case(condition), [first, second])["status"] == "PASS"
    assert campaign().classify_case(case(condition), [first])["status"] == "NOT_RUN"
    second["identity"] = copy.deepcopy(first["identity"])
    assert campaign().classify_case(case(condition), [first, second])["status"] == "INVALID"
    second = attempt(2)
    first["injection"]["before_locked"] = False
    assert campaign().classify_case(case(condition), [first, second])["status"] == "INVALID"


def test_early_lock_and_third_attempt_are_invalid_not_retried_success():
    row = case("fast_interruption")
    first = attempt()
    first["injection"] = {"status": "PASS", "kind": "camera_loss", "before_locked": True}
    assert campaign().classify_case(row, [first, attempt(2)])["status"] == "INVALID"
    assert campaign().classify_case(row, [attempt(), attempt(2), attempt(3)])["status"] == "INVALID"


def test_aggregate_preserves_fixed_denominator_and_missing_cases():
    rows = campaign().load_cases(partitions())
    results = [campaign().classify_case(row, [attempt()] if index == 0 else [])
               for index, row in enumerate(rows)]
    result = campaign().aggregate_cases(results)
    assert len(result["cases"]) == 40
    assert result["counts"] == {"PASS": 1, "FAIL": 0, "UNKNOWN": 0,
                                "INVALID": 0, "NOT_RUN": 39}
    assert result["qualified"] is False
    assert len(result["by_condition"]) == 10
    assert sum(sum(c.values()) for c in result["by_anchor"].values()) == 40


def test_duplicate_aggregate_row_refused():
    result = campaign().classify_case(case(), [attempt()])
    with pytest.raises(ValueError):
        campaign().aggregate_cases([result, result])


def test_partial_aggregate_refused_instead_of_inventing_undeclared_anchors():
    with pytest.raises(ValueError):
        campaign().aggregate_cases([campaign().classify_case(case(), [attempt()])])


def test_bool_attempt_count_is_not_a_single_attempt_declaration():
    declaration = case()
    declaration["expected_attempt_count"] = True
    with pytest.raises(ValueError):
        campaign().classify_case(declaration, [attempt()])
