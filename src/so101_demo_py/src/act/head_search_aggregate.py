"""The `aggregate` phase of the head search qualification: declared gates, and a refusal that names them.

This module is the phase the qualification plan calls ``aggregate`` (the last entry of
``head_search_qualification.RUN_PHASES``) and the phase ``head_search_scenarios.aggregate_scenarios``
names as the owner of the qualification verdict. It consumes the phase artefacts of a qualification run
and publishes a verdict **only if every declared gate holds**.

The gates are declared here, one constant at a time, and each one is evaluated against the artefact that
carries it - never against a summary of it:

======================  ==========================================================================
gate                    the artefact, and what it must show
======================  ==========================================================================
exclusive_ownership     the Step 1 ``EXCLUSIVE_OWNERSHIP_OK`` receipt whose ``planned_run_root`` is
                        **this** qualification run root, with the runtime of record it expected
runtime_identity        the frozen root of record read off disk: commit stamp, promoted config, the 17
                        approved values, the sealed weights, CUDA-only, no CPU fallback
approved_values_readback  the during-qualification readback: all 17 effective values and the four
                        camera measurements, taken under **this** run root, plus the approved bundle
                        whose values digest is the one the readback observed
scenario_journal        ``scenarios.json`` (self digest verified), ``scenario-journal.jsonl`` and one
                        per-scenario evidence document per declared seed, all 40 declared seeds
scenario_terminals      each scenario's terminal against the terminal statuses its condition class
                        declares (locked / expected-not-found / expected-ambiguous pass; anything else
                        fails), re-derived from the per-scenario evidence rather than read from the
                        producer's own ``outcome``
frame_cadence           the 10 Hz contract of every scenario: no duplicate, backward or undeclared gap
stop_proofs             every scenario's held stop proof: three consecutive qualifying samples
anchor_restarts         exactly one independent ``FULL_RESTART`` receipt per anchor, once each
production_smoke        the production smoke journal with its producer/sealed-journal/aggregator chain
teleop_acceptance       the separately owned Teleop acceptance receipt
======================  ==========================================================================

Missing or unreadable evidence is a refusal that **names the item**; it is never a pass and never a
silent skip. A gate whose evidence is present but does not hold is a violation. Both are reported
together, and the verdict is ``HEAD_SEARCH_QUALIFICATION_REFUSED`` whenever either list is non-empty.

Two document families come out of this phase, and they are deliberately not the same thing:

* ``qualification-verdict.json`` - this phase's own verdict over **all ten** gates.
* ``head-search-qualification.json`` and ``head-search-qualified-report.json`` - the plan's Step 5
  documents, published only when the nine **qualification** gates hold. The plan's own ordering requires
  the closed head-only report to exist before Step 6 starts the Teleop acceptance stack and the receipt
  that Step 6 writes can only be verified afterwards; the verdict is therefore ``REFUSED`` (and the CLI
  exits 2) until the acceptance receipt is presented too, and the verdict document says so explicitly in
  ``qualification_document_status``. Nothing is published from a gate that did not hold.

There is no resume, no phase selection and no existing-root mode: the run root must not exist, and a
refused qualification is repeated under a brand new run root.

Declared evidence contract for the three artefacts no producer writes yet (restart receipt, smoke
journal, Teleop acceptance receipt) is listed in :data:`DECLARED_CONTRACTS` and enforced field by field
below; those documents do not exist today, so the gates refuse by name rather than guess.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from so101_demo.act.head_search_binding import _CAMERA_MEASURED, _MEASURED
from so101_demo.act.head_search_ownership import (
    APPROVED_VALUE_COUNT,
    EXCLUSIVE_OWNERSHIP_OK,
    OPERATION as OWNERSHIP_OPERATION,
    default_production_config,
    read_runtime_identity,
)
from so101_demo.act.head_search_scenarios import (
    ARTIFACT as SCENARIOS_ARTIFACT,
    EVIDENCE_DIR as SCENARIOS_EVIDENCE_DIR,
    JOURNAL_ARTIFACT as SCENARIOS_JOURNAL_ARTIFACT,
    KIND as SCENARIOS_KIND,
    NOT_FOUND_STATUSES,
    NOT_FOUND_WITHIN_BOUND_STATUSES,
    PHASE as SCENARIOS_PHASE,
    QUALIFICATION_SPLIT,
    JOURNAL_KEYS,
    expected_terminals,
    qualification_items,
    requires_interruption,
    scenario_journal_entry,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

SCHEMA_VERSION = 1
KIND = "head_search_qualification_verdict"
PHASE = "aggregate"
OPERATION = "QUALIFICATION_RUN"

#: the two verdicts, and the only two: the plan's own words are "HEAD_SEARCH_QUALIFIED or an exact blocker"
QUALIFIED = "HEAD_SEARCH_QUALIFIED"
REFUSED = "HEAD_SEARCH_QUALIFICATION_REFUSED"

#: the per-scenario rule's own vocabulary, taken from the phase that produced the journals
PASSED = "PASSED"
FAILED = "FAILED"
SCENARIO_REFUSED = "REFUSED"

#: a gate's status in the verdict document
HOLDS = "HOLDS"
MISSING = "MISSING"
VIOLATED = "VIOLATED"

VERDICT_ARTIFACT = "qualification-verdict.json"
QUALIFICATION_ARTIFACT = "head-search-qualification.json"
CLOSED_REPORT_ARTIFACT = "head-search-qualified-report.json"

#: the nine gates the plan's Step 5 documents stand on
QUALIFICATION_GATES = (
    "exclusive_ownership",
    "runtime_identity",
    "approved_values_readback",
    "scenario_journal",
    "scenario_terminals",
    "frame_cadence",
    "stop_proofs",
    "anchor_restarts",
    "production_smoke",
)
#: the tenth gate: the separately owned Teleop acceptance, which follows the qualifier and therefore
#: gates the verdict (and the CLI's exit code) rather than the closed report the acceptance consumed
ACCEPTANCE_GATES = ("teleop_acceptance",)
#: every declared gate, in the order the verdict reports them
GATES = QUALIFICATION_GATES + ACCEPTANCE_GATES
#: the phase roots the plan's Step 5 requires the qualification document to cite
CITATION_PHASES = (
    "production_smoke",
    "scenarios",
    "restart_default",
    "restart_left",
    "restart_forward",
    "teleop_acceptance",
)
ANCHORS = ("default", "left", "forward")

#: every key the aggregate accepts, and nothing else: a misspelled declared input refuses by name
DECLARED_INPUTS = (
    "ownership_receipt",
    "final_run",
    "production_config",
    "approved_bundle",
    "runtime_readback",
    "production_smoke_root",
    "scenarios_root",
    "restart_receipts",
    "teleop_acceptance_receipt",
    "scenario_partitions",
    "expected_runtime",
)
#: keys a caller may pass for information; they carry no gate
INFORMATIONAL_INPUTS = ("run_root", "runtime_id", "evidence")

SMOKE_JOURNAL_ARTIFACT = "production-smoke-journal.json"
READBACK_KIND = "head_search_qualification_runtime_readback"
SMOKE_KIND = "head_search_production_smoke_journal"
RESTART_KIND = "head_search_full_restart_receipt"
TELEOP_KIND = "head_search_teleop_acceptance_receipt"

FRAME_RATE_HZ = 10.0
FRAME_PERIOD_S = 0.1
STOP_PROOF_SAMPLES = 3
SOCKET_PATH_LIMIT_BYTES = 103
TELEOP_E2E_CASE = "e2e/head-camera.spec.ts"
MINIMUM_SCREENSHOTS = 6

#: the plan's own terminal vocabulary: every scenario must end on one of these three, and on the one its
#: condition class declares
LEGAL_TERMINALS = ("TARGET_LOCKED", "TARGET_NOT_FOUND", "TARGET_AMBIGUOUS")

EVIDENCE_INCOMPLETE = "HEAD_SEARCH_QUALIFICATION_EVIDENCE_INCOMPLETE"
QUAL_OWNERSHIP_MISSING = "QUAL_AGGREGATE_OWNERSHIP_MISSING"
QUAL_OWNERSHIP_MISMATCH = "QUAL_AGGREGATE_OWNERSHIP_MISMATCH"
QUAL_OWNERSHIP_REFUSED = "QUAL_AGGREGATE_OWNERSHIP_REFUSED"
QUAL_RUNTIME_MISSING = "QUAL_AGGREGATE_RUNTIME_MISSING"
QUAL_RUNTIME_UNREADABLE = "QUAL_AGGREGATE_RUNTIME_UNREADABLE"
QUAL_RUNTIME_OF_RECORD_MISMATCH = "QUAL_AGGREGATE_RUNTIME_OF_RECORD_MISMATCH"
QUAL_RUNTIME_CUDA_REQUIRED = "QUAL_AGGREGATE_RUNTIME_CUDA_REQUIRED"
QUAL_RUNTIME_VALUES_INCOMPLETE = "QUAL_AGGREGATE_RUNTIME_VALUES_INCOMPLETE"
QUAL_RUNTIME_WEIGHTS_MISMATCH = "QUAL_AGGREGATE_RUNTIME_WEIGHTS_MISMATCH"
QUAL_RUNTIME_EXPECTATION_MISSING = "QUAL_AGGREGATE_RUNTIME_EXPECTATION_MISSING"
QUAL_VALUES_MISSING = "QUAL_AGGREGATE_VALUES_MISSING"
QUAL_VALUES_UNREADABLE = "QUAL_AGGREGATE_VALUES_UNREADABLE"
QUAL_VALUES_INCOMPLETE = "QUAL_AGGREGATE_VALUES_INCOMPLETE"
QUAL_VALUES_MISMATCH = "QUAL_AGGREGATE_VALUES_MISMATCH"
QUAL_VALUES_NOT_DURING_QUALIFICATION = "QUAL_AGGREGATE_VALUES_NOT_DURING_QUALIFICATION"
QUAL_CAMERA_MEASUREMENTS_INCOMPLETE = "QUAL_AGGREGATE_CAMERA_MEASUREMENTS_INCOMPLETE"
QUAL_BUNDLE_MISSING = "QUAL_AGGREGATE_BUNDLE_MISSING"
QUAL_BUNDLE_MISMATCH = "QUAL_AGGREGATE_BUNDLE_MISMATCH"
QUAL_JOURNAL_MISSING = "QUAL_AGGREGATE_JOURNAL_MISSING"
QUAL_JOURNAL_UNREADABLE = "QUAL_AGGREGATE_JOURNAL_UNREADABLE"
QUAL_JOURNAL_EVIDENCE_MISSING = "QUAL_AGGREGATE_SCENARIO_EVIDENCE_MISSING"
QUAL_JOURNAL_INCOMPLETE = "QUAL_AGGREGATE_JOURNAL_INCOMPLETE"
QUAL_JOURNAL_SEEDS = "QUAL_AGGREGATE_SCENARIO_SEEDS"
QUAL_JOURNAL_MISMATCH = "QUAL_AGGREGATE_JOURNAL_MISMATCH"
QUAL_JOURNAL_VERDICT_CLAIMED = "QUAL_AGGREGATE_JOURNAL_VERDICT_CLAIMED"
QUAL_JOURNAL_RUNTIME = "QUAL_AGGREGATE_JOURNAL_RUNTIME"
QUAL_PARTITIONS_MISSING = "QUAL_AGGREGATE_PARTITIONS_MISSING"
QUAL_PARTITIONS_UNREADABLE = "QUAL_AGGREGATE_PARTITIONS_UNREADABLE"
QUAL_DIGEST_MISMATCH = "QUAL_AGGREGATE_DIGEST_MISMATCH"
QUAL_TERMINALS_UNJUDGEABLE = "QUAL_AGGREGATE_TERMINALS_UNJUDGEABLE"
QUAL_TERMINAL_NOT_DECLARED = "QUAL_AGGREGATE_TERMINAL_NOT_DECLARED"
QUAL_NO_TERMINAL = "QUAL_AGGREGATE_NO_TERMINAL"
QUAL_WRONG_LOCK = "QUAL_AGGREGATE_WRONG_LOCK"
QUAL_COVERAGE_INCOMPLETE = "QUAL_AGGREGATE_COVERAGE_INCOMPLETE"
QUAL_INTERRUPTION_UNPROVEN = "QUAL_AGGREGATE_INTERRUPTION_UNPROVEN"
QUAL_CLASS_UNDECLARED = "QUAL_AGGREGATE_CONDITION_CLASS_UNDECLARED"
QUAL_OUTCOME_DISAGREES = "QUAL_AGGREGATE_OUTCOME_DISAGREES"
QUAL_COUNTS_MISMATCH = "QUAL_AGGREGATE_COUNTS_MISMATCH"
QUAL_CADENCE_MISSING = "QUAL_AGGREGATE_CADENCE_MISSING"
QUAL_CADENCE_BROKEN = "QUAL_AGGREGATE_CADENCE_BROKEN"
QUAL_STOP_PROOF_MISSING = "QUAL_AGGREGATE_STOP_PROOF_MISSING"
QUAL_STOP_PROOF_UNPROVEN = "QUAL_AGGREGATE_STOP_PROOF_UNPROVEN"
QUAL_RESTART_MISSING = "QUAL_AGGREGATE_RESTART_MISSING"
QUAL_RESTART_UNREADABLE = "QUAL_AGGREGATE_RESTART_UNREADABLE"
QUAL_RESTART_INCOMPLETE = "QUAL_AGGREGATE_RESTART_INCOMPLETE"
QUAL_RESTART_COUNT = "QUAL_AGGREGATE_RESTART_COUNT"
QUAL_SMOKE_MISSING = "QUAL_AGGREGATE_SMOKE_MISSING"
QUAL_SMOKE_UNREADABLE = "QUAL_AGGREGATE_SMOKE_UNREADABLE"
QUAL_SMOKE_INCOMPLETE = "QUAL_AGGREGATE_SMOKE_INCOMPLETE"
QUAL_TELEOP_MISSING = "QUAL_AGGREGATE_TELEOP_MISSING"
QUAL_TELEOP_UNREADABLE = "QUAL_AGGREGATE_TELEOP_UNREADABLE"
QUAL_TELEOP_INCOMPLETE = "QUAL_AGGREGATE_TELEOP_INCOMPLETE"

#: the refusal codes that mean "this evidence was not presented at all", for a reader that wants the
#: missing list without the violations
MISSING_CODES = (
    EVIDENCE_INCOMPLETE,
    QUAL_OWNERSHIP_MISSING,
    QUAL_RUNTIME_MISSING,
    QUAL_RUNTIME_UNREADABLE,
    QUAL_RUNTIME_EXPECTATION_MISSING,
    QUAL_VALUES_MISSING,
    QUAL_VALUES_UNREADABLE,
    QUAL_VALUES_INCOMPLETE,
    QUAL_CAMERA_MEASUREMENTS_INCOMPLETE,
    QUAL_BUNDLE_MISSING,
    QUAL_JOURNAL_MISSING,
    QUAL_JOURNAL_UNREADABLE,
    QUAL_JOURNAL_EVIDENCE_MISSING,
    QUAL_JOURNAL_INCOMPLETE,
    QUAL_PARTITIONS_MISSING,
    QUAL_PARTITIONS_UNREADABLE,
    QUAL_CADENCE_MISSING,
    QUAL_STOP_PROOF_MISSING,
    QUAL_RESTART_MISSING,
    QUAL_RESTART_UNREADABLE,
    QUAL_SMOKE_MISSING,
    QUAL_SMOKE_UNREADABLE,
    QUAL_TELEOP_MISSING,
    QUAL_TELEOP_UNREADABLE,
)

#: the evidence contract this phase declares for the three artefacts that have no producer yet. The
#: fields are enforced below; this constant is the declaration a reviewer reads first.
DECLARED_CONTRACTS = {
    "restart_receipt": {
        "kind": RESTART_KIND,
        "required": (
            "anchor",
            "lifecycle=FULL_RESTART",
            "runtime.{source_commit,production_config_sha256,values_sha256,"
            "weight_sha256_declared,weight_sha256_observed}",
            "teardown.{previous_stack_stopped,controller_owner_stopped,children_exited,graph_clear}",
            "reconstruction.{stack_started,one_mujoco_instance,one_controller_owner}",
            "detector.{loaded,count=1,device=cuda,weights_sha256}",
            "search.{terminal_status=TARGET_LOCKED,coverage_complete,wrong_locks=0}",
            "lock.consecutive_frames>=3",
            "timing.{frame_rate_hz=10.0,cadence_continuous,within_thresholds}",
            "stop.{proven,qualifying_samples>=3}",
            "gates.{graph,detector,search,lock,timing,stop}=PASS",
        ),
    },
    "production_smoke_journal": {
        "kind": SMOKE_KIND,
        "required": (
            "producer.{entry,argv_sha256,stack_owned}",
            f"journal.{{path,sha256}} pointing at a sealed journal file",
            "aggregator.{entry,journal_sha256,status=SUCCEEDED}",
            "runtime.{source_commit,production_config_sha256,values_sha256}",
            "terminal_status=TARGET_LOCKED",
            "frame_cadence.continuous with zero duplicate/backward/undeclared gaps",
            "commands.{bounded,outside_corridor_count=0}",
            "stop_proof.{proven,qualifying_samples>=3}",
            "detector.{count=1,device=cuda,allow_cpu_fallback=false}",
            "zero_wrong_locks",
        ),
    },
    "teleop_acceptance_receipt": {
        "kind": TELEOP_KIND,
        "required": (
            "operation=TELEOP_ACCEPTANCE",
            "runtime_id,source_commit,bundle_sha256",
            "qualification_report.{path,sha256,status=HEAD_SEARCH_QUALIFIED} verified on disk",
            "detector.{count=1,teleop_detector_factory_count=0}",
            "teardown.{controller_stopped,process_groups_exited>=2,graph_clear}",
            f"bridge.socket_paths <= {SOCKET_PATH_LIMIT_BYTES} bytes and cleanup_receipt verified",
            f"e2e.{TELEOP_E2E_CASE} PASSED with >= {MINIMUM_SCREENSHOTS} screenshots on disk",
        ),
    },
}

FIT_WARNING = (
    "the aggregate phase publishes a verdict only from the artefacts it is given: it starts no stack, "
    "loads no detector and commands no motion. A refused verdict is the honest answer for missing "
    "evidence, and the missing list is the work order for the next qualification run"
)


# --- small readers ------------------------------------------------------------------------------------


def _path(value) -> Path | None:
    if value is None:
        return None
    text = str(value)
    return Path(text) if text else None


def _digest(path: Path) -> str:
    return __import__("hashlib").sha256(Path(path).read_bytes()).hexdigest()


def _read_json(path: Path) -> tuple[dict | None, str]:
    """Read one declared document; a missing or unreadable file is a named refusal, never an exception."""

    if not Path(path).is_file():
        return None, f"{path} does not exist"
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return None, f"{path} is unreadable: {error}"
    if not isinstance(document, Mapping):
        return None, f"{path} is not a document"
    return dict(document), ""


def bare(value):
    """`{name: {"value": v}}` and `{name: v}` are the same declaration; this is the bare value."""

    if isinstance(value, Mapping) and "value" in value:
        return value["value"]
    return value


def _finite(value) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return value == value and value not in (float("inf"), float("-inf"))


class _Reasons:
    """The missing and violated lists, kept apart so a reader sees what was absent and what failed."""

    def __init__(self) -> None:
        self.missing: list[dict] = []
        self.violations: list[dict] = []

    def absent(self, gate: str, code: str, item: str, detail: str) -> None:
        self.missing.append({"gate": gate, "code": code, "item": item, "detail": detail})

    def violated(self, gate: str, code: str, item: str, detail: str) -> None:
        self.violations.append({"gate": gate, "code": code, "item": item, "detail": detail})

    def both(self) -> list[dict]:
        return self.missing + self.violations


def _require_new_root(run_root: Path) -> Path:
    """Claim a brand-new run root exclusively, so two qualifications cannot both believe they won it."""

    root = Path(run_root)
    root.parent.mkdir(parents=True, exist_ok=True)
    try:
        root.mkdir()
    except FileExistsError as error:
        raise ValueError(
            f"RUN_ROOT_ALREADY_EXISTS: {root} exists and no runner may resume it"
        ) from error
    return root


def _write(root: Path, name: str, document: Mapping[str, object]) -> Path:
    target = root / name
    pending = root / f".{name}.pending"
    pending.write_text(
        json.dumps(dict(document), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(pending, target)
    return target


# --- the per-scenario rule ----------------------------------------------------------------------------


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


# --- the gates ----------------------------------------------------------------------------------------


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


def _gate_terminals(journal: Mapping, reasons: _Reasons) -> dict:
    entries = journal.get("entries") if isinstance(journal, Mapping) else None
    entries = entries if isinstance(entries, Mapping) else {}
    rows = journal.get("rows") if isinstance(journal, Mapping) else None
    rows = rows if isinstance(rows, Mapping) else {}
    if not entries:
        reasons.absent(
            "scenario_terminals",
            QUAL_TERMINALS_UNJUDGEABLE,
            SCENARIOS_JOURNAL_ARTIFACT,
            "no per-scenario evidence was readable, so no terminal status can be judged",
        )
        return {}
    passed = 0
    codes: dict[str, int] = {}
    for seed in sorted(entries):
        entry = entries[seed]
        verdict = classify_qualification_terminal(entry)
        if verdict["verdict"] == PASSED:
            passed += 1
        else:
            codes[str(verdict["code"])] = codes.get(str(verdict["code"]), 0) + 1
            reasons.violated(
                "scenario_terminals",
                str(verdict["code"]),
                f"scenario {seed} ({entry.get('condition_class')})",
                str(verdict["detail"]),
            )
        row = rows.get(seed) if isinstance(rows, Mapping) else None
        if isinstance(row, Mapping):
            row_passed = row.get("outcome") == PASSED
            if row_passed != (verdict["verdict"] == PASSED):
                reasons.violated(
                    "scenario_terminals",
                    QUAL_OUTCOME_DISAGREES,
                    f"scenario {seed} ({entry.get('condition_class')})",
                    f"the journal row reads outcome={row.get('outcome')!r} while the artefact's terminal "
                    f"{entry.get('terminal_status')!r} is judged {verdict['verdict']}",
                )
    return {"passed": passed, "judged": len(entries), "outcome_codes": codes}


def _gate_cadence(journal: Mapping, reasons: _Reasons) -> dict:
    rows = journal.get("rows") if isinstance(journal, Mapping) else None
    rows = rows if isinstance(rows, Mapping) else {}
    document = None
    if isinstance(journal, Mapping) and journal.get("document"):
        document, _ = _read_json(Path(journal["document"]))
    if not rows:
        reasons.absent(
            "frame_cadence",
            QUAL_CADENCE_MISSING,
            SCENARIOS_JOURNAL_ARTIFACT,
            "no journal rows were readable, so the 10 Hz contract cannot be checked",
        )
        return {}
    broken = []
    for seed in sorted(rows):
        cadence = rows[seed].get("frame_cadence")
        if not isinstance(cadence, Mapping):
            broken.append(f"{seed}: no frame_cadence block")
            continue
        if (
            cadence.get("continuous") is not True
            or int(cadence.get("duplicate_count", 0)) != 0
            or int(cadence.get("backward_count", 0)) != 0
            or int(cadence.get("undeclared_gap_count", 0)) != 0
        ):
            broken.append(f"{seed}: {dict(cadence)}")
            continue
        if not _finite(cadence.get("frame_period_s")) or abs(
            float(cadence["frame_period_s"]) - FRAME_PERIOD_S
        ) > 1e-9:
            broken.append(f"{seed}: frame period {cadence.get('frame_period_s')!r} is not 10 Hz")
    if broken:
        reasons.violated(
            "frame_cadence",
            QUAL_CADENCE_BROKEN,
            SCENARIOS_JOURNAL_ARTIFACT,
            f"{len(broken)} of {len(rows)} scenarios violate the 10 Hz frame contract: {broken[:4]}",
        )
    if isinstance(document, Mapping) and document.get("cadence_all_continuous") is not True:
        reasons.violated(
            "frame_cadence",
            QUAL_CADENCE_BROKEN,
            SCENARIOS_ARTIFACT,
            "the scenarios document does not claim continuous cadence for all forty scenarios",
        )
    return {"checked": len(rows), "broken": len(broken)}


def _gate_stops(journal: Mapping, reasons: _Reasons) -> dict:
    rows = journal.get("rows") if isinstance(journal, Mapping) else None
    rows = rows if isinstance(rows, Mapping) else {}
    document = None
    if isinstance(journal, Mapping) and journal.get("document"):
        document, _ = _read_json(Path(journal["document"]))
    if not rows:
        reasons.absent(
            "stop_proofs",
            QUAL_STOP_PROOF_MISSING,
            SCENARIOS_JOURNAL_ARTIFACT,
            "no journal rows were readable, so no stop proof can be read",
        )
        return {}
    unproven = []
    for seed in sorted(rows):
        proof = rows[seed].get("stop_proof")
        if not isinstance(proof, Mapping):
            unproven.append(f"{seed}: no stop_proof block")
            continue
        if (
            proof.get("proven") is not True
            or int(proof.get("longest_consecutive_run", 0)) < STOP_PROOF_SAMPLES
            or int(proof.get("sample_count", 0)) < STOP_PROOF_SAMPLES
        ):
            unproven.append(
                f"{seed}: proven={proof.get('proven')!r} "
                f"consecutive={proof.get('longest_consecutive_run')!r} "
                f"samples={proof.get('sample_count')!r}"
            )
    if unproven:
        reasons.violated(
            "stop_proofs",
            QUAL_STOP_PROOF_UNPROVEN,
            SCENARIOS_JOURNAL_ARTIFACT,
            f"{len(unproven)} of {len(rows)} scenarios carry no proven stop: {unproven[:4]}",
        )
    if isinstance(document, Mapping) and document.get("stop_proofs_all_proven") is not True:
        reasons.violated(
            "stop_proofs",
            QUAL_STOP_PROOF_UNPROVEN,
            SCENARIOS_ARTIFACT,
            "the scenarios document does not claim a proven stop for all forty scenarios",
        )
    return {"checked": len(rows), "unproven": len(unproven)}


def _gate_restarts(
    declared: Mapping, runtime: Mapping, approved: Mapping, reasons: _Reasons
) -> dict:
    observed_runtime = runtime.get("runtime") if isinstance(runtime, Mapping) else {}
    if not isinstance(observed_runtime, Mapping):
        observed_runtime = {}
    presented = declared.get("restart_receipts")
    if presented is None:
        reasons.absent(
            "anchor_restarts",
            QUAL_RESTART_MISSING,
            "restart_receipts",
            "no FULL_RESTART anchor receipts were presented; the plan fixes exactly one independent "
            "restart for each of default, left and forward",
        )
        return {}
    if isinstance(presented, (str, bytes)) or not isinstance(presented, Sequence):
        reasons.absent(
            "anchor_restarts",
            QUAL_RESTART_UNREADABLE,
            "restart_receipts",
            "the restart receipts must be the sequence of receipt files",
        )
        return {}
    readings: dict = {"receipts": {}, "seen": []}
    by_anchor: dict[str, list[tuple[Path, dict]]] = {}
    for value in presented:
        path = _path(value)
        if path is None:
            reasons.absent(
                "anchor_restarts", QUAL_RESTART_UNREADABLE, "restart_receipts", "an empty receipt path"
            )
            continue
        document, error = _read_json(path)
        if document is None:
            reasons.absent(
                "anchor_restarts", QUAL_RESTART_UNREADABLE, path.name, error
            )
            continue
        anchor = str(document.get("anchor", ""))
        by_anchor.setdefault(anchor, []).append((path, document))
        readings["seen"].append(anchor)
    for anchor in ANCHORS:
        receipts = by_anchor.get(anchor, [])
        if not receipts:
            reasons.absent(
                "anchor_restarts",
                QUAL_RESTART_MISSING,
                f"restart_{anchor}",
                f"exactly one independent FULL_RESTART receipt for the {anchor!r} anchor must be "
                f"presented; none was",
            )
            continue
        if len(receipts) > 1:
            reasons.violated(
                "anchor_restarts",
                QUAL_RESTART_COUNT,
                f"restart_{anchor}",
                f"{len(receipts)} receipts were presented for the {anchor!r} anchor; the manifest must "
                f"contain each anchor exactly once",
            )
        path, document = receipts[0]
        readings["receipts"][anchor] = {"path": str(path), "sha256": _digest(path)}
        label = f"restart_{anchor}"
        if document.get("kind") != RESTART_KIND:
            reasons.violated(
                "anchor_restarts",
                QUAL_RESTART_INCOMPLETE,
                label,
                f"kind {document.get('kind')!r} is not {RESTART_KIND!r}",
            )
        if document.get("lifecycle") != "FULL_RESTART":
            reasons.violated(
                "anchor_restarts",
                QUAL_RESTART_INCOMPLETE,
                label,
                f"lifecycle {document.get('lifecycle')!r} is not FULL_RESTART",
            )
        teardown = document.get("teardown")
        teardown = teardown if isinstance(teardown, Mapping) else {}
        for field in ("previous_stack_stopped", "controller_owner_stopped", "children_exited", "graph_clear"):
            if teardown.get(field) is not True:
                reasons.violated(
                    "anchor_restarts",
                    QUAL_RESTART_INCOMPLETE,
                    label,
                    f"the teardown did not prove {field}",
                )
        reconstruction = document.get("reconstruction")
        reconstruction = reconstruction if isinstance(reconstruction, Mapping) else {}
        for field in ("stack_started", "one_mujoco_instance", "one_controller_owner"):
            if reconstruction.get(field) is not True:
                reasons.violated(
                    "anchor_restarts",
                    QUAL_RESTART_INCOMPLETE,
                    label,
                    f"the reconstruction did not prove {field}",
                )
        detector = document.get("detector")
        detector = detector if isinstance(detector, Mapping) else {}
        if int(detector.get("count", 0)) != 1 or str(detector.get("device", "")) != "cuda":
            reasons.violated(
                "anchor_restarts",
                QUAL_RESTART_INCOMPLETE,
                label,
                f"the restart did not run exactly one CUDA detector: count={detector.get('count')!r} "
                f"device={detector.get('device')!r}",
            )
        if detector.get("weights_sha256") not in (None, observed_runtime.get("weight_sha256_declared")):
            reasons.violated(
                "anchor_restarts",
                QUAL_RESTART_INCOMPLETE,
                label,
                f"the restart detector ran weights {detector.get('weights_sha256')!r}",
            )
        search = document.get("search")
        search = search if isinstance(search, Mapping) else {}
        if (
            search.get("terminal_status") != "TARGET_LOCKED"
            or search.get("coverage_complete") is not True
            or int(search.get("wrong_locks", 0)) != 0
        ):
            reasons.violated(
                "anchor_restarts",
                QUAL_RESTART_INCOMPLETE,
                label,
                f"the restart search did not end on a clean lock: {dict(search)}",
            )
        lock = document.get("lock")
        lock = lock if isinstance(lock, Mapping) else {}
        if int(lock.get("consecutive_frames", 0)) < 3:
            reasons.violated(
                "anchor_restarts",
                QUAL_RESTART_INCOMPLETE,
                label,
                f"the restart lock carried {lock.get('consecutive_frames')!r} consecutive frames",
            )
        timing = document.get("timing")
        timing = timing if isinstance(timing, Mapping) else {}
        if (
            timing.get("cadence_continuous") is not True
            or timing.get("within_thresholds") is not True
            or abs(float(timing.get("frame_rate_hz", 0.0)) - FRAME_RATE_HZ) > 1e-9
        ):
            reasons.violated(
                "anchor_restarts",
                QUAL_RESTART_INCOMPLETE,
                label,
                f"the restart timing gates did not pass: {dict(timing)}",
            )
        stop = document.get("stop")
        stop = stop if isinstance(stop, Mapping) else {}
        if (
            stop.get("proven") is not True
            or int(stop.get("qualifying_samples", 0)) < STOP_PROOF_SAMPLES
        ):
            reasons.violated(
                "anchor_restarts",
                QUAL_RESTART_INCOMPLETE,
                label,
                f"the restart stop proof is unproven: {dict(stop)}",
            )
        gates = document.get("gates")
        gates = gates if isinstance(gates, Mapping) else {}
        failed = sorted(
            name
            for name in ("graph", "detector", "search", "lock", "timing", "stop")
            if gates.get(name) != "PASS"
        )
        if failed:
            reasons.violated(
                "anchor_restarts",
                QUAL_RESTART_INCOMPLETE,
                label,
                f"the restart did not pass {failed}",
            )
        restart_runtime = document.get("runtime")
        restart_runtime = restart_runtime if isinstance(restart_runtime, Mapping) else {}
        for key in (
            "source_commit",
            "production_config_sha256",
            "values_sha256",
            "weight_sha256_declared",
            "weight_sha256_observed",
            "allow_cpu_fallback",
            "cuda_device",
        ):
            if key in restart_runtime and restart_runtime.get(key) != observed_runtime.get(key):
                reasons.violated(
                    "anchor_restarts",
                    QUAL_RESTART_INCOMPLETE,
                    label,
                    f"the restart ran {key}={restart_runtime.get(key)!r}, the presented frozen runtime "
                    f"is {observed_runtime.get(key)!r}",
                )
        bundle = approved.get("bundle_sha256") if isinstance(approved, Mapping) else None
        if bundle and document.get("approved_bundle_sha256") not in (None, bundle):
            reasons.violated(
                "anchor_restarts",
                QUAL_RESTART_INCOMPLETE,
                label,
                f"the restart ran the bundle {document.get('approved_bundle_sha256')!r}, the presented "
                f"approved bundle is {bundle!r}",
            )
    extra = sorted(anchor for anchor in by_anchor if anchor not in ANCHORS)
    if extra:
        reasons.violated(
            "anchor_restarts",
            QUAL_RESTART_COUNT,
            "restart_receipts",
            f"receipts were presented for anchors outside the declared three: {extra}",
        )
    return readings


def _gate_smoke(declared: Mapping, runtime: Mapping, reasons: _Reasons) -> dict:
    observed_runtime = runtime.get("runtime") if isinstance(runtime, Mapping) else {}
    if not isinstance(observed_runtime, Mapping):
        observed_runtime = {}
    root = _path(declared.get("production_smoke_root"))
    if root is None:
        reasons.absent(
            "production_smoke",
            QUAL_SMOKE_MISSING,
            "production_smoke_root",
            "no production smoke phase root was presented; the plan requires producer -> sealed journal "
            "-> actual aggregator, and a planning-coverage proof is not a smoke journal",
        )
        return {}
    readings: dict = {"root": str(root)}
    journal_path = root / SMOKE_JOURNAL_ARTIFACT
    document, error = _read_json(journal_path)
    if document is None:
        present = sorted(path.name for path in root.iterdir()) if root.is_dir() else []
        reasons.absent(
            "production_smoke",
            QUAL_SMOKE_MISSING,
            f"production_smoke journal ({SMOKE_JOURNAL_ARTIFACT})",
            f"{error}; the root carries {present}, which is not the smoke journal the plan requires",
        )
        return readings
    readings["journal"] = str(journal_path)
    readings["sha256"] = _digest(journal_path)
    label = SMOKE_JOURNAL_ARTIFACT
    if document.get("kind") != SMOKE_KIND or document.get("phase") != "production_smoke":
        reasons.violated(
            "production_smoke",
            QUAL_SMOKE_INCOMPLETE,
            label,
            f"kind {document.get('kind')!r} / phase {document.get('phase')!r} is not the production "
            f"smoke journal",
        )
    producer = document.get("producer")
    producer = producer if isinstance(producer, Mapping) else {}
    if not producer.get("entry") or producer.get("stack_owned") is not True:
        reasons.violated(
            "production_smoke",
            QUAL_SMOKE_INCOMPLETE,
            label,
            f"the smoke does not declare the producer that owned its stack: {dict(producer)}",
        )
    sealed = document.get("journal")
    sealed = sealed if isinstance(sealed, Mapping) else {}
    sealed_path = _path(sealed.get("path"))
    if sealed_path is None or not sealed_path.is_file():
        reasons.absent(
            "production_smoke",
            QUAL_SMOKE_MISSING,
            "production_smoke sealed journal",
            f"the smoke journal names no readable sealed journal: {sealed.get('path')!r}",
        )
    else:
        sealed_digest = _digest(sealed_path)
        readings["sealed_journal"] = str(sealed_path)
        readings["sealed_journal_sha256"] = sealed_digest
        if sealed.get("sha256") != sealed_digest:
            reasons.violated(
                "production_smoke",
                QUAL_DIGEST_MISMATCH,
                "production_smoke sealed journal",
                f"the declared journal digest {sealed.get('sha256')!r} is not the digest of "
                f"{sealed_path} ({sealed_digest})",
            )
        aggregator = document.get("aggregator")
        aggregator = aggregator if isinstance(aggregator, Mapping) else {}
        if (
            aggregator.get("journal_sha256") != sealed_digest
            or aggregator.get("status") != "SUCCEEDED"
            or not aggregator.get("entry")
        ):
            reasons.violated(
                "production_smoke",
                QUAL_SMOKE_INCOMPLETE,
                label,
                f"the aggregator did not consume the sealed journal: {dict(aggregator)}",
            )
    if document.get("terminal_status") != "TARGET_LOCKED":
        reasons.violated(
            "production_smoke",
            QUAL_SMOKE_INCOMPLETE,
            label,
            f"the smoke ended on {document.get('terminal_status')!r}, not TARGET_LOCKED",
        )
    if document.get("zero_wrong_locks") is not True:
        reasons.violated(
            "production_smoke", QUAL_SMOKE_INCOMPLETE, label, "the smoke does not claim zero wrong locks"
        )
    cadence = document.get("frame_cadence")
    cadence = cadence if isinstance(cadence, Mapping) else {}
    if (
        cadence.get("continuous") is not True
        or int(cadence.get("duplicate_count", 0)) != 0
        or int(cadence.get("backward_count", 0)) != 0
        or int(cadence.get("undeclared_gap_count", 0)) != 0
    ):
        reasons.violated(
            "production_smoke",
            QUAL_SMOKE_INCOMPLETE,
            label,
            f"the smoke does not carry a continuous 10 Hz sequence: {dict(cadence)}",
        )
    commands = document.get("commands")
    commands = commands if isinstance(commands, Mapping) else {}
    if commands.get("bounded") is not True or int(commands.get("outside_corridor_count", -1)) != 0:
        reasons.violated(
            "production_smoke",
            QUAL_SMOKE_INCOMPLETE,
            label,
            f"the smoke does not prove bounded commands: {dict(commands)}",
        )
    proof = document.get("stop_proof")
    proof = proof if isinstance(proof, Mapping) else {}
    if proof.get("proven") is not True or int(proof.get("qualifying_samples", 0)) < STOP_PROOF_SAMPLES:
        reasons.violated(
            "production_smoke",
            QUAL_STOP_PROOF_UNPROVEN,
            label,
            f"the smoke carries no proven three-sample stop: {dict(proof)}",
        )
    detector = document.get("detector")
    detector = detector if isinstance(detector, Mapping) else {}
    if (
        int(detector.get("count", 0)) != 1
        or str(detector.get("device", "")) != "cuda"
        or detector.get("allow_cpu_fallback") is not False
    ):
        reasons.violated(
            "production_smoke",
            QUAL_SMOKE_INCOMPLETE,
            label,
            f"the smoke did not run exactly one CUDA detector without CPU fallback: {dict(detector)}",
        )
    smoke_runtime = document.get("runtime")
    smoke_runtime = smoke_runtime if isinstance(smoke_runtime, Mapping) else {}
    for key in (
        "source_commit",
        "production_config_sha256",
        "values_sha256",
        "weight_sha256_declared",
        "weight_sha256_observed",
    ):
        if key in smoke_runtime and smoke_runtime.get(key) != observed_runtime.get(key):
            reasons.violated(
                "production_smoke",
                QUAL_SMOKE_INCOMPLETE,
                label,
                f"the smoke ran {key}={smoke_runtime.get(key)!r}, the presented frozen runtime is "
                f"{observed_runtime.get(key)!r}",
            )
    return readings


def _gate_teleop(
    declared: Mapping, runtime: Mapping, approved: Mapping, reasons: _Reasons
) -> dict:
    observed_runtime = runtime.get("runtime") if isinstance(runtime, Mapping) else {}
    if not isinstance(observed_runtime, Mapping):
        observed_runtime = {}
    path = _path(declared.get("teleop_acceptance_receipt"))
    if path is None:
        reasons.absent(
            "teleop_acceptance",
            QUAL_TELEOP_MISSING,
            "teleop_acceptance_receipt",
            "no Teleop acceptance receipt was presented; the separately owned acceptance fixture is the "
            "last declaration the plan requires before a qualification verdict",
        )
        return {}
    document, error = _read_json(path)
    if document is None:
        reasons.absent(
            "teleop_acceptance", QUAL_TELEOP_MISSING, "teleop_acceptance_receipt", error
        )
        return {}
    root = path.parent
    readings = {"receipt": str(path), "sha256": _digest(path)}
    label = "teleop_acceptance_receipt"
    if document.get("kind") != TELEOP_KIND or document.get("operation") != "TELEOP_ACCEPTANCE":
        reasons.violated(
            "teleop_acceptance",
            QUAL_TELEOP_INCOMPLETE,
            label,
            f"kind {document.get('kind')!r} / operation {document.get('operation')!r} is not a Teleop "
            f"acceptance receipt",
        )
    if document.get("source_commit") not in (None, observed_runtime.get("source_commit")):
        reasons.violated(
            "teleop_acceptance",
            QUAL_TELEOP_INCOMPLETE,
            label,
            f"the acceptance ran the commit {document.get('source_commit')!r}, the frozen runtime is "
            f"{observed_runtime.get('source_commit')!r}",
        )
    bundle = approved.get("bundle_sha256") if isinstance(approved, Mapping) else None
    if not bundle:
        reasons.absent(
            "teleop_acceptance",
            QUAL_BUNDLE_MISSING,
            "approved_bundle",
            "no approved bundle was presented, so the acceptance cannot be bound to one",
        )
    elif document.get("bundle_sha256") != bundle:
        reasons.violated(
            "teleop_acceptance",
            QUAL_TELEOP_INCOMPLETE,
            label,
            f"the acceptance ran the bundle {document.get('bundle_sha256')!r}, the approved bundle is "
            f"{bundle!r}",
        )
    report = document.get("qualification_report")
    report = report if isinstance(report, Mapping) else {}
    report_path = _path(report.get("path"))
    if report.get("status") != "HEAD_SEARCH_QUALIFIED":
        reasons.violated(
            "teleop_acceptance",
            QUAL_TELEOP_INCOMPLETE,
            label,
            f"the acceptance did not start from a closed head-only report: "
            f"status {report.get('status')!r}",
        )
    elif report_path is None or not report_path.is_file():
        reasons.absent(
            "teleop_acceptance",
            QUAL_TELEOP_MISSING,
            "teleop acceptance qualification_report",
            f"the cited closed report {report.get('path')!r} does not exist",
        )
    elif report.get("sha256") != _digest(report_path):
        reasons.violated(
            "teleop_acceptance",
            QUAL_DIGEST_MISMATCH,
            "teleop acceptance qualification_report",
            f"the cited report digests to {_digest(report_path)}, not {report.get('sha256')!r}",
        )
    else:
        readings["qualification_report"] = {
            "path": str(report_path),
            "sha256": report.get("sha256"),
        }
    detector = document.get("detector")
    detector = detector if isinstance(detector, Mapping) else {}
    if int(detector.get("count", -1)) != 1 or int(detector.get("teleop_detector_factory_count", -1)) != 0:
        reasons.violated(
            "teleop_acceptance",
            QUAL_TELEOP_INCOMPLETE,
            label,
            f"the acceptance must show one detector and a Teleop detector factory count of zero: "
            f"{dict(detector)}",
        )
    teardown = document.get("teardown")
    teardown = teardown if isinstance(teardown, Mapping) else {}
    if (
        teardown.get("controller_stopped") is not True
        or teardown.get("graph_clear") is not True
        or int(teardown.get("process_groups_exited", 0)) < 2
    ):
        reasons.violated(
            "teleop_acceptance",
            QUAL_TELEOP_INCOMPLETE,
            label,
            f"the acceptance does not prove controller stop, both process groups exited and a clear "
            f"graph: {dict(teardown)}",
        )
    bridge = document.get("bridge")
    bridge = bridge if isinstance(bridge, Mapping) else {}
    sockets = bridge.get("socket_paths")
    sockets = sockets if isinstance(sockets, Sequence) and not isinstance(sockets, (str, bytes)) else []
    overlong = [str(name) for name in sockets if len(os.fsencode(str(name))) > SOCKET_PATH_LIMIT_BYTES]
    if len(sockets) < 2 or overlong:
        reasons.violated(
            "teleop_acceptance",
            QUAL_TELEOP_INCOMPLETE,
            label,
            f"the bridge socket paths must all be {SOCKET_PATH_LIMIT_BYTES} bytes or fewer: "
            f"{overlong or sockets}",
        )
    else:
        readings["socket_path_bytes"] = max(len(os.fsencode(str(name))) for name in sockets)
    cleanup = bridge.get("cleanup_receipt")
    cleanup = cleanup if isinstance(cleanup, Mapping) else {}
    cleanup_path = _path(cleanup.get("path"))
    if cleanup_path is None or not cleanup_path.is_file():
        reasons.absent(
            "teleop_acceptance",
            QUAL_TELEOP_MISSING,
            "teleop acceptance cleanup_receipt",
            f"the bridge cleanup receipt {cleanup.get('path')!r} does not exist",
        )
    elif cleanup.get("sha256") not in (None, _digest(cleanup_path)):
        reasons.violated(
            "teleop_acceptance",
            QUAL_DIGEST_MISMATCH,
            "teleop acceptance cleanup_receipt",
            f"the cleanup receipt digests to {_digest(cleanup_path)}, not {cleanup.get('sha256')!r}",
        )
    e2e = document.get("e2e")
    e2e = e2e if isinstance(e2e, Mapping) else {}
    screenshots = e2e.get("screenshots")
    screenshots = (
        screenshots
        if isinstance(screenshots, Sequence) and not isinstance(screenshots, (str, bytes))
        else []
    )
    present = []
    for name in screenshots:
        candidate = Path(str(name))
        if not candidate.is_absolute():
            candidate = root / candidate
        present.append(candidate)
    missing_shots = [str(candidate) for candidate in present if not candidate.is_file()]
    if (
        e2e.get("case") != TELEOP_E2E_CASE
        or e2e.get("status") != "PASSED"
        or int(e2e.get("raw_overlay_pairs", 0)) < 1
        or len(present) < MINIMUM_SCREENSHOTS
        or missing_shots
    ):
        reasons.violated(
            "teleop_acceptance",
            QUAL_TELEOP_INCOMPLETE,
            label,
            f"the installed acceptance did not pass with fresh evidence: case={e2e.get('case')!r} "
            f"status={e2e.get('status')!r} pairs={e2e.get('raw_overlay_pairs')!r} "
            f"screenshots={len(present)} missing={missing_shots[:3]}",
        )
    else:
        readings["screenshots"] = [str(candidate) for candidate in present]
    return readings


# --- the phase ----------------------------------------------------------------------------------------


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
