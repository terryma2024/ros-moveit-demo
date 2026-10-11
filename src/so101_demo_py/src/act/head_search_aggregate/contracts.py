"""Qualification gates, declared inputs and contracts, missing codes and small readers."""

from __future__ import annotations

from collections.abc import Mapping
import json
import os
from pathlib import Path

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


#: gates the verdict (and the CLI's exit code) rather than the closed report the acceptance consumed
ACCEPTANCE_GATES = ("teleop_acceptance",)


GATES = QUALIFICATION_GATES + ACCEPTANCE_GATES


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
