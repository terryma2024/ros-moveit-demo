"""Pure verdicts for the declared Head-only 40-case development campaign.

Caller supplies already verified audit and truth facts. These functions do not
validate files, repair producer outcomes, operate ROS, or grant qualification.
"""

from collections import Counter
from copy import deepcopy


CONDITIONS = (
    "nominal", "left_anchor", "forward_anchor", "distractor_present", "two_cups",
    "no_cup", "low_light", "partial_occlusion", "fast_interruption",
    "reacquire_after_stop",
)
ANCHORS = ("default", "left", "forward")
STATUSES = ("PASS", "FAIL", "UNKNOWN", "INVALID", "NOT_RUN")
INTERRUPTIONS = {"fast_interruption": ("camera_loss", "FAULT"),
                 "reacquire_after_stop": ("signal_stop", "INTERRUPTED")}


def _strict_int(value):
    return type(value) is int


def _case_valid(case):
    return (isinstance(case, dict) and _strict_int(case.get("seed"))
            and 900000 <= case["seed"] < 900040
            and case.get("condition_class") == CONDITIONS[(case["seed"] - 900000) % 10]
            and case.get("anchor") in ANCHORS
            and case.get("case_id") == f"hs40-{case['seed']}"
            and _strict_int(case.get("expected_attempt_count"))
            and case.get("expected_attempt_count") ==
            (2 if case.get("condition_class") in INTERRUPTIONS else 1))


def load_cases(partitions: dict) -> list[dict]:
    """Read exactly the declared matrix; retain its order and individual anchors."""
    if not isinstance(partitions, dict) or type(partitions.get("schema_version")) is not int:
        raise ValueError("CAMPAIGN_PARTITIONS_SCHEMA")
    if partitions["schema_version"] != 1 or partitions.get("condition_classes") != list(CONDITIONS):
        raise ValueError("CAMPAIGN_PARTITIONS_SCHEMA")
    if partitions.get("anchors") != list(ANCHORS):
        raise ValueError("CAMPAIGN_PARTITIONS_ANCHORS")
    declared = partitions.get("qualification")
    if not isinstance(declared, list) or len(declared) != 40:
        raise ValueError("CAMPAIGN_MATRIX_COUNT")
    rows = []
    groups = set()
    for index, row in enumerate(declared):
        if not isinstance(row, dict) or not _strict_int(row.get("seed")):
            raise ValueError("CAMPAIGN_SEED_TYPE")
        if row["seed"] != 900000 + index:
            raise ValueError("CAMPAIGN_SEED_ORDER")
        group = row.get("scene_group_id")
        if not isinstance(group, str) or not group.strip() or group in groups:
            raise ValueError("CAMPAIGN_SCENE_GROUP")
        groups.add(group)
        item = deepcopy(row)
        item["case_id"] = f"hs40-{row['seed']}"
        item["expected_attempt_count"] = 2 if row.get("condition_class") in INTERRUPTIONS else 1
        if not _case_valid(item):
            raise ValueError("CAMPAIGN_CASE_DECLARATION")
        rows.append(item)
    splits = []
    for name in ("calibration", "held_out_evaluation"):
        values = partitions.get(name)
        if (not isinstance(values, list) or len(values) != 20
                or any(not _strict_int(x) or x < 0 for x in values)
                or len(set(values)) != len(values)):
            raise ValueError("CAMPAIGN_SPLIT_DECLARATION")
        splits.append(set(values))
    seeds = {row["seed"] for row in rows}
    if splits[0] & splits[1] or any(split & seeds for split in splits):
        raise ValueError("CAMPAIGN_SPLIT_OVERLAP")
    return rows


def _attempt_check(facts):
    if not isinstance(facts, dict):
        return "INVALID", "ATTEMPT_TYPE"
    identity = facts.get("identity")
    if (not isinstance(identity, dict)
            or any(not isinstance(identity.get(k), str) or not identity[k].strip()
                   for k in ("run_id", "session_id", "epoch"))
            or not _strict_int(identity.get("generation")) or identity["generation"] < 0):
        return "INVALID", "ATTEMPT_IDENTITY"
    if facts.get("admission") != "VALID":
        return "INVALID", "ATTEMPT_ADMISSION"
    for name in ("business_rc", "actual_os_return_code", "audit_rc"):
        if not _strict_int(facts.get(name)):
            return "INVALID", f"{name.upper()}_TYPE"
    business_rc = facts["business_rc"]
    if (business_rc not in (0, 1)
            or facts["actual_os_return_code"] != business_rc):
        return "INVALID", "ATTEMPT_RC_CONFLICT"
    if facts["audit_rc"] != 0:
        return "UNKNOWN", "AUDIT_INCOMPLETE"
    audit = facts.get("audit", {})
    if not isinstance(audit, dict):
        return "INVALID", "AUDIT_TYPE"
    categories = [audit.get(k) for k in ("integrity", "execution", "stop", "exit_cleanup")]
    if "FAIL" in categories:
        return "FAIL", "AUDIT_CATEGORY_FAILED"
    if any(category != "PASS" for category in categories):
        return "UNKNOWN", "AUDIT_CATEGORY_UNPROVEN"
    for name in ("non_neck_dispatch", "wrong_locks"):
        if name not in facts:
            return "UNKNOWN", f"{name.upper()}_UNPROVEN"
        if not _strict_int(facts[name]) or facts[name] < 0:
            return "INVALID", f"{name.upper()}_TYPE"
        if facts[name] != 0:
            return "FAIL", name.upper()
    truth = facts.get("truth")
    if not isinstance(truth, dict) or truth.get("status") != "PASS":
        return "UNKNOWN", "SCENE_TRUTH_UNPROVEN"
    terminal = facts.get("original_terminal")
    if not isinstance(terminal, str) or not terminal:
        return "UNKNOWN", "TERMINAL_UNPROVEN"
    if business_rc != (0 if terminal == "TARGET_LOCKED" else 1):
        return "INVALID", "TERMINAL_RC_CONFLICT"
    return "PASS", None


def classify_case(case: dict, attempts: list[dict]) -> dict:
    """Classify a fixed case without overwriting any raw per-attempt facts."""
    if not _case_valid(case) or not isinstance(attempts, list):
        raise ValueError("CAMPAIGN_CASE_INPUT")
    result = deepcopy(case)
    result.update(attempts=deepcopy(attempts), qualified=False)

    def finish(outcome, reason):
        result.update(status=outcome, reasons=[reason] if reason else [])
        return result

    expected = case["expected_attempt_count"]
    if len(attempts) > expected:
        return finish("INVALID", "EXTRA_ATTEMPT")
    if len(attempts) < expected:
        return finish("NOT_RUN", "REQUIRED_ATTEMPT_NOT_RUN")
    for facts in attempts:
        outcome, reason = _attempt_check(facts)
        if outcome != "PASS":
            return finish(outcome, reason)
    condition = case["condition_class"]
    if condition in INTERRUPTIONS:
        first, second = attempts
        if any(first["identity"][key] == second["identity"][key]
               for key in ("run_id", "session_id", "epoch", "generation")):
            return finish("INVALID", "REACQUISITION_IDENTITY_REUSED")
        kind, terminal = INTERRUPTIONS[condition]
        injection = first.get("injection")
        if not isinstance(injection, dict) or injection.get("status") != "PASS":
            return finish("UNKNOWN", "INTERRUPTION_UNPROVEN")
        if (injection.get("kind") != kind or injection.get("before_locked") is not True
                or first["original_terminal"] != terminal):
            return finish("INVALID", "INTERRUPTION_NOT_APPLIED_BEFORE_LOCK")
        final = second
    else:
        final = attempts[0]
    terminal = final["original_terminal"]
    truth = final["truth"]
    if condition == "two_cups":
        correct = terminal == "TARGET_AMBIGUOUS" and truth.get("target") == "AMBIGUOUS"
    elif condition == "no_cup":
        correct = (terminal == "TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL"
                   and truth.get("target") == "ABSENT"
                   and truth.get("coverage_complete") is True)
    else:
        correct = terminal == "TARGET_LOCKED" and truth.get("target") == "CORRECT"
    return finish("PASS" if correct else "FAIL", None if correct else "UNEXPECTED_SEARCH_RESULT")


def aggregate_cases(cases: list[dict]) -> dict:
    """Require all 40 declared rows, including explicit NOT_RUN results.

    Missing rows cannot be safely invented: their anchors belong to the manifest.
    """
    if not isinstance(cases, list) or len(cases) != 40:
        raise ValueError("CAMPAIGN_AGGREGATE_COUNT")
    if (any(not _case_valid(c) or c.get("status") not in STATUSES for c in cases)
            or len({c["seed"] for c in cases}) != 40):
        raise ValueError("CAMPAIGN_AGGREGATE_ROWS")

    def counts(rows):
        values = Counter(row["status"] for row in rows)
        return {status: values[status] for status in STATUSES}

    return {
        "schema_version": 1, "qualified": False, "cases": deepcopy(cases),
        "expected_case_count": 40, "expected_attempt_count": 48,
        "counts": counts(cases),
        "by_condition": {kind: counts([c for c in cases if c["condition_class"] == kind])
                         for kind in CONDITIONS},
        "by_anchor": {anchor: counts([c for c in cases if c["anchor"] == anchor])
                      for anchor in ANCHORS},
    }
