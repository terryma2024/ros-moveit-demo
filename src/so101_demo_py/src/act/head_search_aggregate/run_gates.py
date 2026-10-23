"""Terminal classification and the ownership, runtime, value and journal gates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path

from so101_demo.act.head_search_aggregate.contracts import (
    FAILED,
    LEGAL_TERMINALS,
    PASSED,
    QUAL_BUNDLE_MISMATCH,
    QUAL_BUNDLE_MISSING,
    QUAL_CAMERA_MEASUREMENTS_INCOMPLETE,
    QUAL_CLASS_UNDECLARED,
    QUAL_COVERAGE_INCOMPLETE,
    QUAL_DIGEST_MISMATCH,
    QUAL_INTERRUPTION_UNPROVEN,
    QUAL_JOURNAL_EVIDENCE_MISSING,
    QUAL_JOURNAL_INCOMPLETE,
    QUAL_JOURNAL_MISMATCH,
    QUAL_JOURNAL_MISSING,
    QUAL_JOURNAL_RUNTIME,
    QUAL_JOURNAL_SEEDS,
    QUAL_JOURNAL_VERDICT_CLAIMED,
    QUAL_NO_TERMINAL,
    QUAL_OWNERSHIP_MISMATCH,
    QUAL_OWNERSHIP_MISSING,
    QUAL_OWNERSHIP_REFUSED,
    QUAL_PARTITIONS_MISSING,
    QUAL_PARTITIONS_UNREADABLE,
    QUAL_RUNTIME_CUDA_REQUIRED,
    QUAL_RUNTIME_EXPECTATION_MISSING,
    QUAL_RUNTIME_MISSING,
    QUAL_RUNTIME_OF_RECORD_MISMATCH,
    QUAL_RUNTIME_UNREADABLE,
    QUAL_RUNTIME_VALUES_INCOMPLETE,
    QUAL_RUNTIME_WEIGHTS_MISMATCH,
    QUAL_TERMINAL_NOT_DECLARED,
    QUAL_VALUES_INCOMPLETE,
    QUAL_VALUES_MISMATCH,
    QUAL_VALUES_MISSING,
    QUAL_VALUES_NOT_DURING_QUALIFICATION,
    QUAL_VALUES_UNREADABLE,
    QUAL_WRONG_LOCK,
    READBACK_KIND,
    SCENARIO_REFUSED,
    _digest,
    _path,
    _read_json,
    _Reasons,
    bare,
)
from so101_demo.act.head_search_binding import _CAMERA_MEASURED, _MEASURED
from so101_demo.act.head_search_ownership import (
    APPROVED_VALUE_COUNT,
    EXCLUSIVE_OWNERSHIP_OK,
    default_production_config,
    read_runtime_identity,
)
from so101_demo.act.head_search_ownership import (
    OPERATION as OWNERSHIP_OPERATION,
)
from so101_demo.act.head_search_scenarios.contracts import (
    ARTIFACT as SCENARIOS_ARTIFACT,
)
from so101_demo.act.head_search_scenarios.contracts import (
    EVIDENCE_DIR as SCENARIOS_EVIDENCE_DIR,
)
from so101_demo.act.head_search_scenarios.contracts import (
    JOURNAL_ARTIFACT as SCENARIOS_JOURNAL_ARTIFACT,
)
from so101_demo.act.head_search_scenarios.contracts import (
    KIND as SCENARIOS_KIND,
)
from so101_demo.act.head_search_scenarios.contracts import (
    NOT_FOUND_STATUSES,
    NOT_FOUND_WITHIN_BOUND_STATUSES,
    QUALIFICATION_SPLIT,
)
from so101_demo.act.head_search_scenarios.contracts import (
    PHASE as SCENARIOS_PHASE,
)
from so101_demo.act.head_search_scenarios.journal import JOURNAL_KEYS, scenario_journal_entry
from so101_demo.act.head_search_scenarios.plan import (
    expected_terminals,
    qualification_items,
    requires_interruption,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256


def classify_qualification_terminal(entry: Mapping) -> dict:
    """The plan's per-scenario rule, re-derived from the artefact instead of read from its producer.

    The plan's scenario rule: "Legal single cup ends ``TARGET_LOCKED``; two cups end ``TARGET_AMBIGUOUS``; no
    cup ends ``TARGET_NOT_FOUND`` only with complete coverage; interrupted input ends the old attempt
    fail-closed, proves stop, clears tracker/lock state and reacquires under a new attempt." A scenario
    passes only when its terminal status is one its condition class declares **and** the added obligation
    of that terminal holds; anything else fails, and an artefact that cannot be judged at all refuses.
    """

    if not isinstance(entry, Mapping):
        raise ValueError("a scenario entry must be a mapping")
    condition_class = entry.get("condition_class")
    try:
        terminals = expected_terminals(condition_class)
    except ValueError as error:
        return {
            "verdict": SCENARIO_REFUSED,
            "code": QUAL_CLASS_UNDECLARED,
            "detail": str(error),
        }

    if requires_interruption(condition_class):
        attempts = [item for item in (entry.get("attempts") or []) if isinstance(item, Mapping)]
        injected = [item for item in attempts if item.get("interruption_injected") is True]
        if not injected:
            return {
                "verdict": SCENARIO_REFUSED,
                "code": QUAL_INTERRUPTION_UNPROVEN,
                "detail": (
                    f"the condition class {condition_class!r} is a declared interrupted class, but the "
                    f"scenario {entry.get('seed')} never injected the interruption, so the fail-closed "
                    f"stop and the reacquisition were never exercised"
                ),
            }
        for attempt in injected:
            if attempt.get("stop") is not True:
                return {
                    "verdict": SCENARIO_REFUSED,
                    "code": QUAL_INTERRUPTION_UNPROVEN,
                    "detail": (
                        f"the injected interruption of the scenario {entry.get('seed')} did not stop the "
                        f"controller (status {attempt.get('interruption_decision_status')!r})"
                    ),
                }
            if attempt.get("lock_count_cleared_by_interruption") is not True:
                return {
                    "verdict": SCENARIO_REFUSED,
                    "code": QUAL_INTERRUPTION_UNPROVEN,
                    "detail": (
                        f"the injected interruption of the scenario {entry.get('seed')} left the lock "
                        f"state at {attempt.get('lock_count_after_interruption')!r} instead of clearing it"
                    ),
                }
        if len(attempts) < 2 or attempts[-1].get("interruption_injected") is True:
            return {
                "verdict": SCENARIO_REFUSED,
                "code": QUAL_INTERRUPTION_UNPROVEN,
                "detail": (
                    f"the scenario {entry.get('seed')} ran no second attempt after its interruption, so "
                    f"the search never reacquired"
                ),
            }
        if attempts[-1].get("detector_reset_before_attempt") is not True:
            return {
                "verdict": SCENARIO_REFUSED,
                "code": QUAL_INTERRUPTION_UNPROVEN,
                "detail": (
                    f"the reacquiring attempt of the scenario {entry.get('seed')} did not reset the "
                    f"detector's tracker"
                ),
            }

    terminal = entry.get("terminal_status")
    if terminal is None:
        return {
            "verdict": SCENARIO_REFUSED,
            "code": QUAL_NO_TERMINAL,
            "detail": f"the scenario {entry.get('seed')} recorded no terminal status at all",
        }
    terminal = str(terminal)
    coverage = entry.get("coverage") if isinstance(entry.get("coverage"), Mapping) else {}
    if terminal in terminals:
        if terminal in NOT_FOUND_STATUSES and coverage.get("complete") is not True:
            return {
                "verdict": FAILED,
                "code": QUAL_COVERAGE_INCOMPLETE,
                "detail": (
                    f"the scenario {entry.get('seed')} reported {terminal} without a complete sweep of "
                    f"the required search domain, so the negative is not a clean one"
                ),
            }
        return {"verdict": PASSED, "code": None, "detail": None}
    if terminal == "TARGET_LOCKED":
        return {
            "verdict": FAILED,
            "code": QUAL_WRONG_LOCK,
            "detail": (
                f"the scenario {entry.get('seed')} of the condition class {condition_class!r} locked, "
                f"but that class declares {list(terminals)}: a lock here is a wrong lock"
            ),
        }
    if terminal in NOT_FOUND_WITHIN_BOUND_STATUSES:
        return {
            "verdict": FAILED,
            "code": QUAL_COVERAGE_INCOMPLETE,
            "detail": (
                f"the scenario {entry.get('seed')} stopped at a bound before the sweep covered the "
                f"required search domain"
            ),
        }
    # the three terminals the plan names, plus the bound-limited negative: one of these that the class
    # does not declare is a measured failure, and a status the plan never names cannot be judged at all
    if terminal in (*LEGAL_TERMINALS, "TARGET_NOT_CENTERED"):
        return {
            "verdict": FAILED,
            "code": QUAL_TERMINAL_NOT_DECLARED,
            "detail": (
                f"the scenario {entry.get('seed')} of the condition class {condition_class!r} ended on "
                f"{terminal}, but that class declares the terminal statuses {list(terminals)}"
            ),
        }
    return {
        "verdict": SCENARIO_REFUSED,
        "code": QUAL_TERMINAL_NOT_DECLARED,
        "detail": (
            f"the scenario {entry.get('seed')} ended on the controller status {terminal!r}, which is "
            f"neither a terminal status its condition class declares nor one this phase can judge"
        ),
    }


def _gate_ownership(declared: Mapping, run_root: Path, reasons: _Reasons) -> dict:
    path = _path(declared.get("ownership_receipt"))
    if path is None:
        reasons.absent(
            "exclusive_ownership",
            QUAL_OWNERSHIP_MISSING,
            "ownership_receipt",
            "no Step 1 exclusive-ownership receipt was presented for this qualification",
        )
        return {}
    document, error = _read_json(path)
    if document is None:
        reasons.absent("exclusive_ownership", QUAL_OWNERSHIP_MISSING, "ownership_receipt", error)
        return {}
    readings = {"receipt": str(path), "sha256": _digest(path)}
    if document.get("operation") != OWNERSHIP_OPERATION:
        reasons.violated(
            "exclusive_ownership",
            QUAL_OWNERSHIP_MISMATCH,
            "ownership_receipt",
            f"operation {document.get('operation')!r} is not {OWNERSHIP_OPERATION!r}",
        )
    if document.get("status") != EXCLUSIVE_OWNERSHIP_OK or document.get("refusals"):
        reasons.violated(
            "exclusive_ownership",
            QUAL_OWNERSHIP_REFUSED,
            "ownership_receipt",
            f"status {document.get('status')!r} with refusals {document.get('refusals')!r}",
        )
    planned = document.get("planned_run_root")
    readings["planned_run_root"] = planned
    if str(planned or "") != str(run_root):
        reasons.violated(
            "exclusive_ownership",
            QUAL_OWNERSHIP_MISMATCH,
            "ownership_receipt",
            f"the receipt guards {planned!r}, not this qualification run root {str(run_root)!r}",
        )
    expected = document.get("expected_runtime")
    readings["expected_runtime"] = dict(expected) if isinstance(expected, Mapping) else None
    readings["checked_at_utc"] = document.get("checked_at_utc")
    return readings


def _gate_runtime(declared: Mapping, ownership: Mapping, reasons: _Reasons) -> dict:
    final_run = _path(declared.get("final_run"))
    if final_run is None:
        reasons.absent(
            "runtime_identity",
            QUAL_RUNTIME_MISSING,
            "final_run",
            "no frozen toolchain root was presented, so no runtime identity can be read",
        )
        return {}
    production_config = _path(declared.get("production_config")) or default_production_config(
        final_run
    )
    try:
        runtime = read_runtime_identity(final_run, production_config=production_config)
    except ValueError as error:
        reasons.absent("runtime_identity", QUAL_RUNTIME_UNREADABLE, "final_run", str(error))
        return {}
    readings = {"runtime": runtime, "final_run": str(final_run)}
    if runtime.get("allow_cpu_fallback") is not False or str(runtime.get("cuda_device")) != "cuda:0":
        reasons.violated(
            "runtime_identity",
            QUAL_RUNTIME_CUDA_REQUIRED,
            "final_run",
            f"allow_cpu_fallback={runtime.get('allow_cpu_fallback')!r}, "
            f"cuda_device={runtime.get('cuda_device')!r}",
        )
    if int(runtime.get("values_count", 0)) != APPROVED_VALUE_COUNT:
        reasons.violated(
            "runtime_identity",
            QUAL_RUNTIME_VALUES_INCOMPLETE,
            "final_run",
            f"{runtime.get('values_count')} values, {APPROVED_VALUE_COUNT} approved",
        )
    if runtime.get("setup_bash_present") is not True:
        reasons.violated(
            "runtime_identity",
            QUAL_RUNTIME_OF_RECORD_MISMATCH,
            "final_run",
            "install/setup.bash is missing, so the overlay is not the frozen one",
        )
    declared_weight = runtime.get("weight_sha256_declared")
    observed_weight = runtime.get("weight_sha256_observed")
    if not observed_weight or observed_weight != declared_weight:
        reasons.violated(
            "runtime_identity",
            QUAL_RUNTIME_WEIGHTS_MISMATCH,
            "final_run",
            f"declared {declared_weight!r}, observed {observed_weight!r}",
        )
    expected = declared.get("expected_runtime")
    if not isinstance(expected, Mapping) or not expected:
        expected = ownership.get("expected_runtime") if isinstance(ownership, Mapping) else None
    if not isinstance(expected, Mapping) or not expected:
        reasons.absent(
            "runtime_identity",
            QUAL_RUNTIME_EXPECTATION_MISSING,
            "expected_runtime",
            "no expected runtime of record was declared, so the observed identity has nothing to match",
        )
    else:
        readings["expected_runtime"] = dict(expected)
        for key, wanted in sorted(expected.items()):
            observed_value = runtime.get(key)
            if observed_value != wanted:
                reasons.violated(
                    "runtime_identity",
                    QUAL_RUNTIME_OF_RECORD_MISMATCH,
                    "final_run",
                    f"{key}: expected {wanted!r}, observed {observed_value!r}",
                )
    return readings


def _gate_values(
    declared: Mapping, run_root: Path, runtime: Mapping, reasons: _Reasons
) -> dict:
    observed_runtime = runtime.get("runtime") if isinstance(runtime, Mapping) else None
    if not isinstance(observed_runtime, Mapping):
        observed_runtime = {}
    readings: dict = {}
    # the approved bundle is read first, because it is a presented declaration in its own right: a
    # refusal must cite the bundle it was given even when the readback beside it is missing
    bundle_path = _path(declared.get("approved_bundle"))
    parameters: Mapping = {}
    if bundle_path is None:
        reasons.absent(
            "approved_values_readback",
            QUAL_BUNDLE_MISSING,
            "approved_bundle",
            "no approved calibration bundle was presented, so no approved values can be named",
        )
    else:
        bundle, bundle_error = _read_json(bundle_path)
        if bundle is None:
            reasons.absent(
                "approved_values_readback", QUAL_BUNDLE_MISSING, "approved_bundle", bundle_error
            )
        else:
            readings["approved_bundle"] = str(bundle_path)
            readings["bundle_sha256"] = _digest(bundle_path)
            declared_parameters = bundle.get("parameters")
            parameters = declared_parameters if isinstance(declared_parameters, Mapping) else {}
            if not parameters:
                reasons.violated(
                    "approved_values_readback",
                    QUAL_BUNDLE_MISMATCH,
                    "approved_bundle",
                    "the approved bundle declares no parameters block",
                )
    path = _path(declared.get("runtime_readback"))
    if path is None:
        path = run_root / "qualification-runtime-readback.json"
    document, error = _read_json(path)
    if document is None:
        reasons.absent(
            "approved_values_readback",
            QUAL_VALUES_MISSING
            if not Path(path).exists()
            else QUAL_VALUES_UNREADABLE,
            "runtime_readback",
            f"the during-qualification 17-value readback was not presented: {error}",
        )
        _check_approved_bundle_values(parameters, observed_runtime, readings, reasons)
        # the missing item is named in the refusal, with its path; the citation stays null so nothing
        # points a reader at evidence that does not exist
        return dict(readings)
    readings["readback"] = str(path)
    readings["sha256"] = _digest(path)
    if document.get("kind") != READBACK_KIND:
        reasons.violated(
            "approved_values_readback",
            QUAL_VALUES_MISMATCH,
            "runtime_readback",
            f"kind {document.get('kind')!r} is not {READBACK_KIND!r}",
        )
    if str(document.get("run_root", "")) != str(run_root):
        reasons.violated(
            "approved_values_readback",
            QUAL_VALUES_NOT_DURING_QUALIFICATION,
            "runtime_readback",
            f"the readback was taken under {document.get('run_root')!r}, not under this qualification "
            f"run root {str(run_root)!r}: a readback of another run is not a during-qualification one",
        )
    values = document.get("values")
    if not isinstance(values, Mapping):
        reasons.absent(
            "approved_values_readback",
            QUAL_VALUES_INCOMPLETE,
            "runtime_readback.values",
            "the readback declares no values block",
        )
        values = {}
    absent_names = [name for name in _MEASURED if name not in values]
    if absent_names:
        reasons.absent(
            "approved_values_readback",
            QUAL_VALUES_INCOMPLETE,
            "runtime_readback.values",
            f"{len(absent_names)} of {APPROVED_VALUE_COUNT} approved values were not read back: "
            f"{absent_names}",
        )
    unreadable = [name for name in _MEASURED if name in values and bare(values[name]) is None]
    if unreadable:
        reasons.absent(
            "approved_values_readback",
            QUAL_VALUES_INCOMPLETE,
            "runtime_readback.values",
            f"the readback of {unreadable} carries no effective value",
        )
    read_back = {name: bare(values[name]) for name in _MEASURED if name in values}
    readings["values_count"] = len(read_back)
    if len(read_back) == APPROVED_VALUE_COUNT:
        observed_digest = canonical_sha256(read_back)
        readings["values_sha256"] = observed_digest
        declared_digest = observed_runtime.get("values_sha256")
        if observed_digest != declared_digest:
            reasons.violated(
                "approved_values_readback",
                QUAL_VALUES_MISMATCH,
                "runtime_readback.values",
                f"the read-back values digest to {observed_digest}, but the frozen promoted config "
                f"carries {declared_digest}",
            )
        if document.get("values_sha256") not in (None, observed_digest):
            reasons.violated(
                "approved_values_readback",
                QUAL_VALUES_MISMATCH,
                "runtime_readback.values_sha256",
                f"the readback declares {document.get('values_sha256')!r} but its own values digest to "
                f"{observed_digest}",
            )
    camera = document.get("camera_measurements")
    if not isinstance(camera, Mapping) or any(name not in camera for name in _CAMERA_MEASURED):
        reasons.absent(
            "approved_values_readback",
            QUAL_CAMERA_MEASUREMENTS_INCOMPLETE,
            "runtime_readback.camera_measurements",
            f"the readback does not carry the four camera measurements {list(_CAMERA_MEASURED)}",
        )
    else:
        readings["camera_measurements"] = {
            name: bare(camera[name]) for name in _CAMERA_MEASURED
        }
    detector = document.get("detector")
    if not isinstance(detector, Mapping) or int(detector.get("count", 0)) != 1:
        reasons.violated(
            "approved_values_readback",
            QUAL_VALUES_MISMATCH,
            "runtime_readback.detector",
            f"the readback must show exactly one detector instance, saw "
            f"{detector.get('count') if isinstance(detector, Mapping) else detector!r}",
        )
    elif str(detector.get("device", "")) != "cuda" or detector.get("allow_cpu_fallback") is not False:
        reasons.violated(
            "approved_values_readback",
            QUAL_VALUES_MISMATCH,
            "runtime_readback.detector",
            f"the readback detector is {detector.get('device')!r} with "
            f"allow_cpu_fallback={detector.get('allow_cpu_fallback')!r}",
        )
    for field in ("weight_sha256_declared", "weight_sha256_observed"):
        if document.get(field) not in (None, observed_runtime.get("weight_sha256_declared")):
            reasons.violated(
                "approved_values_readback",
                QUAL_VALUES_MISMATCH,
                f"runtime_readback.{field}",
                f"{field} is {document.get(field)!r}, the frozen config declares "
                f"{observed_runtime.get('weight_sha256_declared')!r}",
            )

    _check_approved_bundle_values(parameters, observed_runtime, readings, reasons)
    return readings


def _check_approved_bundle_values(
    parameters: Mapping, observed_runtime: Mapping, readings: dict, reasons: _Reasons
) -> None:
    """The approved bundle's own values against the values the frozen config carries."""

    if not parameters:
        return
    approved = {name: bare(parameters[name]) for name in _MEASURED if name in parameters}
    if len(approved) != APPROVED_VALUE_COUNT:
        reasons.violated(
            "approved_values_readback",
            QUAL_BUNDLE_MISMATCH,
            "approved_bundle",
            f"the approved bundle carries {len(approved)} of {APPROVED_VALUE_COUNT} approved values",
        )
        return
    approved_digest = canonical_sha256(approved)
    readings["approved_values_sha256"] = approved_digest
    if approved_digest != observed_runtime.get("values_sha256"):
        reasons.violated(
            "approved_values_readback",
            QUAL_BUNDLE_MISMATCH,
            "approved_bundle",
            f"the approved bundle's values digest to {approved_digest}, the frozen config carries "
            f"{observed_runtime.get('values_sha256')!r}",
        )


def _gate_journal(
    declared: Mapping, runtime: Mapping, reasons: _Reasons
) -> dict:
    observed_runtime = runtime.get("runtime") if isinstance(runtime, Mapping) else {}
    if not isinstance(observed_runtime, Mapping):
        observed_runtime = {}
    partitions_path = _path(declared.get("scenario_partitions"))
    items: list[dict] = []
    if partitions_path is None:
        reasons.absent(
            "scenario_journal",
            QUAL_PARTITIONS_MISSING,
            "scenario_partitions",
            "the declared scenario partitions were not presented, so the forty declared seeds cannot be "
            "read independently of the journal that claims them",
        )
    else:
        partitions, error = _read_json(partitions_path)
        if partitions is None:
            reasons.absent(
                "scenario_journal", QUAL_PARTITIONS_UNREADABLE, "scenario_partitions", error
            )
        else:
            try:
                items = qualification_items(partitions)
            except (ValueError, Exception) as error:  # noqa: BLE001 - a refused declaration is a refusal
                reasons.absent(
                    "scenario_journal", QUAL_PARTITIONS_UNREADABLE, "scenario_partitions", str(error)
                )
                items = []

    root = _path(declared.get("scenarios_root"))
    if root is None:
        reasons.absent(
            "scenario_journal",
            QUAL_JOURNAL_MISSING,
            "scenarios_root",
            "no 40-scenario phase root was presented",
        )
        return {"declared_seeds": sorted(int(item["seed"]) for item in items)}
    readings: dict = {
        "root": str(root),
        "declared_seeds": sorted(int(item["seed"]) for item in items),
    }
    document, error = _read_json(root / SCENARIOS_ARTIFACT)
    if document is None:
        reasons.absent(
            "scenario_journal", QUAL_JOURNAL_MISSING, SCENARIOS_ARTIFACT, error
        )
    else:
        readings["document"] = str(root / SCENARIOS_ARTIFACT)
        if document.get("kind") != SCENARIOS_KIND or document.get("phase") != SCENARIOS_PHASE:
            reasons.violated(
                "scenario_journal",
                QUAL_JOURNAL_MISMATCH,
                SCENARIOS_ARTIFACT,
                f"kind {document.get('kind')!r} / phase {document.get('phase')!r} is not the scenarios "
                f"phase's own document",
            )
        if document.get("split") != QUALIFICATION_SPLIT:
            reasons.violated(
                "scenario_journal",
                QUAL_JOURNAL_MISMATCH,
                SCENARIOS_ARTIFACT,
                f"split {document.get('split')!r} is not {QUALIFICATION_SPLIT!r}",
            )
        declared_digest = document.get("sha256")
        recomputed = canonical_sha256(
            {key: value for key, value in document.items() if key != "sha256"}
        )
        if declared_digest != recomputed:
            reasons.violated(
                "scenario_journal",
                QUAL_DIGEST_MISMATCH,
                SCENARIOS_ARTIFACT,
                f"the document declares {declared_digest!r} over its own body, which digests to "
                f"{recomputed}: the document was changed after it was written",
            )
        readings["document_sha256"] = declared_digest
        if document.get("qualification_verdict") is not None:
            reasons.violated(
                "scenario_journal",
                QUAL_JOURNAL_VERDICT_CLAIMED,
                SCENARIOS_ARTIFACT,
                "the scenarios phase published a qualification verdict; only this phase may",
            )
        partitions_block = document.get("scenario_partitions")
        if partitions_path is not None and isinstance(partitions_block, Mapping):
            if partitions_block.get("sha256") != _digest(partitions_path):
                reasons.violated(
                    "scenario_journal",
                    QUAL_JOURNAL_MISMATCH,
                    SCENARIOS_ARTIFACT,
                    f"the scenarios cite the partitions {partitions_block.get('sha256')!r}, the presented "
                    f"document digests to {_digest(partitions_path)}",
                )
        if observed_runtime:
            claimed = document.get("runtime_identity")
            claimed = dict(claimed) if isinstance(claimed, Mapping) else {}
            for key in (
                "source_commit",
                "production_config_sha256",
                "values_sha256",
                "weight_sha256_declared",
                "weight_sha256_observed",
                "allow_cpu_fallback",
                "cuda_device",
            ):
                if key in claimed and claimed.get(key) != observed_runtime.get(key):
                    reasons.violated(
                        "scenario_journal",
                        QUAL_JOURNAL_RUNTIME,
                        SCENARIOS_ARTIFACT,
                        f"the scenarios ran under {key}={claimed.get(key)!r}, the presented frozen "
                        f"runtime is {observed_runtime.get(key)!r}",
                    )

    journal_path = root / SCENARIOS_JOURNAL_ARTIFACT
    if not journal_path.is_file():
        reasons.absent(
            "scenario_journal",
            QUAL_JOURNAL_MISSING,
            SCENARIOS_JOURNAL_ARTIFACT,
            f"{journal_path} does not exist",
        )
        return readings
    readings["journal"] = str(journal_path)
    readings["journal_sha256"] = _digest(journal_path)
    rows: list[dict] = []
    malformed = []
    for number, line in enumerate(journal_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            malformed.append(f"line {number}: {error}")
            continue
        if not isinstance(row, Mapping):
            malformed.append(f"line {number}: not a document")
            continue
        missing_keys = [key for key in JOURNAL_KEYS if key not in row]
        if missing_keys:
            malformed.append(f"line {number} (seed {row.get('seed')}): no {missing_keys}")
            continue
        rows.append(dict(row))
    if malformed:
        reasons.absent(
            "scenario_journal",
            QUAL_JOURNAL_INCOMPLETE,
            SCENARIOS_JOURNAL_ARTIFACT,
            f"{len(malformed)} journal rows are not readable rows: {malformed[:4]}",
        )
    readings["journal_rows"] = len(rows)
    declared_seeds = readings["declared_seeds"]
    row_seeds = sorted(int(row["seed"]) for row in rows)
    if len(declared_seeds) != 40:
        reasons.absent(
            "scenario_journal",
            QUAL_JOURNAL_INCOMPLETE,
            "scenario_partitions",
            f"the declared partitions carry {len(declared_seeds)} qualification items, not the forty "
            f"scenarios the plan fixes",
        )
    if row_seeds != declared_seeds or len(set(row_seeds)) != len(row_seeds):
        unexpected = sorted(set(row_seeds) - set(declared_seeds))
        unmeasured = sorted(set(declared_seeds) - set(row_seeds))
        reasons.violated(
            "scenario_journal",
            QUAL_JOURNAL_SEEDS,
            SCENARIOS_JOURNAL_ARTIFACT,
            f"the journal covers {len(set(row_seeds))} distinct seeds: {len(unmeasured)} declared seeds "
            f"have no row {unmeasured[:6]} and {len(unexpected)} rows carry an undeclared seed "
            f"{unexpected[:6]}",
        )
    if document is not None:
        document_seeds = document.get("seeds")
        document_seeds = (
            sorted(int(seed) for seed in document_seeds)
            if isinstance(document_seeds, Sequence) and not isinstance(document_seeds, (str, bytes))
            else []
        )
        if document_seeds != declared_seeds:
            reasons.violated(
                "scenario_journal",
                QUAL_JOURNAL_SEEDS,
                SCENARIOS_ARTIFACT,
                f"the scenarios document declares {len(document_seeds)} seeds, the partitions declare "
                f"{len(declared_seeds)}",
            )
        if int(document.get("scenario_count", 0)) != len(rows) or len(rows) != 40:
            reasons.violated(
                "scenario_journal",
                QUAL_JOURNAL_INCOMPLETE,
                SCENARIOS_ARTIFACT,
                f"the document claims {document.get('scenario_count')} scenarios and the journal carries "
                f"{len(rows)} rows; the plan fixes forty",
            )

    by_seed: dict[int, dict] = {}
    evidence: dict[int, dict] = {}
    for row in rows:
        by_seed[int(row["seed"])] = row
    for seed in declared_seeds or sorted(by_seed):
        evidence_path = root / SCENARIOS_EVIDENCE_DIR / f"{seed}.json"
        entry, error = _read_json(evidence_path)
        if entry is None:
            reasons.absent(
                "scenario_journal",
                QUAL_JOURNAL_EVIDENCE_MISSING,
                f"{SCENARIOS_EVIDENCE_DIR}/{seed}.json",
                f"the scenario {seed} has no per-scenario evidence document: {error}",
            )
            continue
        evidence[seed] = entry
        row = by_seed.get(seed)
        if row is None:
            continue
        try:
            projected = scenario_journal_entry(entry)
        except ValueError as error:
            reasons.absent(
                "scenario_journal",
                QUAL_JOURNAL_INCOMPLETE,
                f"{SCENARIOS_EVIDENCE_DIR}/{seed}.json",
                f"the evidence of the scenario {seed} is not a journal entry: {error}",
            )
            continue
        if projected != row:
            differing = sorted(
                key for key in JOURNAL_KEYS if projected.get(key) != row.get(key)
            )
            reasons.violated(
                "scenario_journal",
                QUAL_JOURNAL_MISMATCH,
                f"{SCENARIOS_EVIDENCE_DIR}/{seed}.json",
                f"the journal row of the scenario {seed} is not the row its own evidence document "
                f"projects: {differing[:6]} differ",
            )
        if int(entry.get("seed", -1)) != seed:
            reasons.violated(
                "scenario_journal",
                QUAL_JOURNAL_MISMATCH,
                f"{SCENARIOS_EVIDENCE_DIR}/{seed}.json",
                f"the evidence filed as {seed} declares the seed {entry.get('seed')!r}",
            )
    if document is not None:
        records = document.get("records")
        records = records if isinstance(records, Sequence) and not isinstance(records, (str, bytes)) else []
        record_by_seed = {
            int(record["seed"]): dict(record)
            for record in records
            if isinstance(record, Mapping) and "seed" in record
        }
        if len(record_by_seed) != len(by_seed):
            reasons.violated(
                "scenario_journal",
                QUAL_JOURNAL_INCOMPLETE,
                SCENARIOS_ARTIFACT,
                f"the document carries {len(record_by_seed)} records for {len(by_seed)} journal rows",
            )
        for seed, record in record_by_seed.items():
            if by_seed.get(seed) != record:
                reasons.violated(
                    "scenario_journal",
                    QUAL_JOURNAL_MISMATCH,
                    SCENARIOS_ARTIFACT,
                    f"the record of the scenario {seed} in the document is not its journal row",
                )
    readings["entries"] = evidence
    readings["rows"] = by_seed
    return readings
