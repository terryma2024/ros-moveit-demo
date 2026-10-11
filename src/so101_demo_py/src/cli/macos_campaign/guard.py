"""The campaign guard scope and phases, route specs and the guard admission."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
import time
from typing import Callable

from so101_demo.cli.macos_campaign.journal import (
    MPS_TWO_WORKER_FIRST_PASS,
    TWO_WORKER_FIRST_PASS_BATCH_KIND,
)
from so101_demo.parallel_batch.contracts import (
    ContractError,
    ParallelRuntimeConfigMacosMpsSingleWorkerFirstPass,
    ParallelRuntimeConfigMacosMpsSingleWorkerRetry,
    ParallelRuntimeConfigMacosMpsTwoWorker,
)
from so101_demo.parallel_batch.single_worker_composition import (
    MPS_SINGLE_WORKER_FIRST_PASS,
    MPS_SINGLE_WORKER_FULL_RESTART_RETRY,
    SINGLE_WORKER_FIRST_PASS_BATCH_KIND,
    SINGLE_WORKER_RETRY_BATCH_KIND,
    compose_single_worker_first_pass,
    compose_single_worker_retry,
)
from so101_demo.parallel_batch.start_guard import CAMPAIGN_GUARD_EPOCH, FAIL
from so101_demo.parallel_batch.start_guard_probe import (
    GUARD_RESULT_FD_VARIABLE,
    UNSET_PROBE,
    GuardHandoverRefused,
    consume_guard_handover,
    darwin_guard_scope,
    publish_guard_handover,
    run_campaign_start_guard,
)
from so101_demo.parallel_batch.two_worker_composition import (
    compose_two_worker_campaign,
)

#: Which phase this process is in. The guard phase runs before the campaign child exists and is
#: the only phase allowed to import the accelerator probe; the broker phase is entered through
#: this process's own inherited pipe, or it is refused.
GUARD_PHASE_VARIABLE = "SO101_CAMPAIGN_PHASE"


GUARD_PHASE = "guard"


BROKER_PHASE = "broker"


def campaign_guard_scope(*, batch_id: str, worker_count: int,
                         epoch: int = CAMPAIGN_GUARD_EPOCH):
    """The campaign-level scope: epoch 0, the real owner identity, the approved MPS selector.

    Per-spawn epochs start at 1, so a campaign preflight can never be mistaken for a spawn
    admission. The owner facts (PID and birth identity) are the same on both sides of the `exec`,
    which is what makes them checkable after it rather than assumed.
    """

    return darwin_guard_scope(batch_id=batch_id, worker_count=worker_count, epoch=epoch)


def guard_document(result) -> dict:
    """The audit projection of one guard result. It is written down, never read back as input."""

    checks = dict(result.checks)
    head = checks.get("mps_headroom")
    reason = None
    for name in ("mps_accelerator", "probe", "ram", "cpu_capacity", "mps_headroom"):
        check = checks.get(name)
        if check is not None and check.status == FAIL:
            reason = check.reason
            break
    if reason is None:
        reason = head.reason if head is not None else "START_GUARD_OK"
    return {
        "status": result.status,
        "reason": reason,
        "epoch": result.scope.epoch,
        "scope": {
            "batch_id": result.scope.batch_id,
            "epoch": result.scope.epoch,
            "owner_pid": result.scope.owner_pid,
            "owner_starttime_ticks": result.scope.owner_starttime_ticks,
            "gpu_selector": result.scope.gpu_selector,
            "worker_count": result.scope.worker_count,
        },
        "cleanup_state": result.cleanup_state,
        "available_bytes": None if head is None else head.observed,
        "cutoff": None if head is None else head.cutoff,
        "admission_kind": "unified-memory-proxy" if head is not None else None,
        "checks": {
            name: {"status": check.status, "reason": check.reason, "observed": check.observed,
                   "cutoff": check.cutoff, "unit": check.unit}
            for name, check in checks.items()
        },
    }


def run_guard_phase(arguments, *, policy, batch_id, worker_count, probe=UNSET_PROBE, state_root=None):
    """Take one fresh campaign observation and record it for audit.

    The on-disk copy is written on every attempt - PASS, WARN or FAIL - and it is never an input:
    a `start-guard.json` left by an earlier epoch, a different owner or a tampered run cannot
    admit anything, and it cannot block a healthy fresh probe either.
    """

    result = run_campaign_start_guard(policy=policy, batch_id=batch_id, worker_count=worker_count,
                                      probe=probe, state_root=state_root)
    document = guard_document(result)
    root = Path(arguments.evidence_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "start-guard.json").write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    return document, result


def broker_phase_guard(environment, *, scope, max_age_s, forbidden_modules=("torch",),
                       clock=time.monotonic):
    """Read the one-shot admission from the inherited pipe this process created, or refuse.

    Nothing is read from disk here, whatever a `start-guard.json` says. A missing descriptor, a
    scope/owner/epoch mismatch, an expired result, a refusal or a guard-phase import that survived
    the `exec` are all refusals by name.
    """

    raw = environment.get(GUARD_RESULT_FD_VARIABLE)
    if raw is None or not str(raw).strip().isdigit():
        raise GuardHandoverRefused(
            "GUARD_HANDOVER_MISSING",
            "the admission must arrive through the inherited pipe this process created")
    return consume_guard_handover(int(raw), scope=scope, max_age_s=max_age_s, clock=clock,
                                  forbidden_modules=forbidden_modules)


def _audit_guard(arguments) -> dict | None:
    """The on-disk guard record, read defensively and only for the evidence document."""

    path = Path(arguments.evidence_root) / "start-guard.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


@dataclass(frozen=True)
class CampaignRouteSpec:
    """One row of the support matrix, wired to the entry point that executes it."""

    execution_profile: str
    batch_kind: str
    config_class: type
    module: str
    worker_ids: tuple[str, ...]
    default_point_ids: tuple[str, ...]
    minimum_served: int
    composer: Callable[..., object]

    @property
    def worker_count(self) -> int:
        return len(self.worker_ids)

    @property
    def pass_label(self) -> str:
        return "TWO_WORKER_CAMPAIGN_PASS" if self.worker_count == 2 else "SINGLE_WORKER_CAMPAIGN_PASS"

    @property
    def incomplete_label(self) -> str:
        return "TWO_WORKER_CAMPAIGN_INCOMPLETE" if self.worker_count == 2 else "SINGLE_WORKER_CAMPAIGN_INCOMPLETE"


ROUTE_SPECS: tuple[CampaignRouteSpec, ...] = (
    CampaignRouteSpec(
        execution_profile=MPS_TWO_WORKER_FIRST_PASS, batch_kind=TWO_WORKER_FIRST_PASS_BATCH_KIND,
        config_class=ParallelRuntimeConfigMacosMpsTwoWorker, module="so101_demo.cli.macos_two_worker_campaign",
        worker_ids=("worker-01", "worker-02"), default_point_ids=("p1", "p2"), minimum_served=6,
        composer=compose_two_worker_campaign),
    CampaignRouteSpec(
        execution_profile=MPS_SINGLE_WORKER_FULL_RESTART_RETRY, batch_kind=SINGLE_WORKER_RETRY_BATCH_KIND,
        config_class=ParallelRuntimeConfigMacosMpsSingleWorkerRetry, module="so101_demo.cli.macos_mps_single_worker_retry",
        worker_ids=("worker-01",), default_point_ids=("p1",), minimum_served=3,
        composer=compose_single_worker_retry),
    CampaignRouteSpec(
        execution_profile=MPS_SINGLE_WORKER_FIRST_PASS, batch_kind=SINGLE_WORKER_FIRST_PASS_BATCH_KIND,
        config_class=ParallelRuntimeConfigMacosMpsSingleWorkerFirstPass, module="so101_demo.cli.macos_mps_single_worker_first_pass",
        worker_ids=("worker-01",), default_point_ids=("p1",), minimum_served=3,
        composer=compose_single_worker_first_pass),
)


def route_spec(execution_profile: str) -> CampaignRouteSpec:
    """The one entry point that executes a profile. There is no generic fallback."""

    for spec in ROUTE_SPECS:
        if spec.execution_profile == execution_profile:
            return spec
    raise ContractError(f"EXECUTION_PROFILE_UNKNOWN: {execution_profile}")


class RefusedRun(Exception):
    """A refusal before anything was spawned. It is reported as evidence, not as a traceback."""

    def __init__(self, stage: str, detail: str, exit_code: int = 1) -> None:
        super().__init__(f"{stage}: {detail}")
        self.stage = stage
        self.detail = detail
        self.exit_code = exit_code


def _guard_admission(arguments, argv, plan, spec, document):
    """The fresh campaign admission, handed over through this process's own pipe.

    Returns the admitted result in the broker phase; in the guard phase it either refuses (and
    returns ``None`` after writing the refusal document) or replaces this process with the broker
    phase. The on-disk record is written for audit either way and is never read as input.
    """

    scope = campaign_guard_scope(batch_id=arguments.batch_id, worker_count=plan.worker_count)
    if os.environ.get(GUARD_PHASE_VARIABLE) != BROKER_PHASE:
        read_fd, write_fd = os.pipe()
        audit, result = run_guard_phase(
            arguments, policy=plan.config.start_guard, batch_id=arguments.batch_id,
            worker_count=plan.worker_count,
            state_root=arguments.evidence_root / "start-guard-state")
        print(json.dumps({"phase": "start-guard", **audit}, indent=2, sort_keys=True), flush=True)
        if result.status == FAIL or result.cleanup_state != "CLEAR":
            for descriptor in (read_fd, write_fd):
                try:
                    os.close(descriptor)
                except OSError:  # pragma: no cover - already closed
                    pass
            document.update(status="REFUSED", stage="start_guard", start_guard=audit)
            print(json.dumps(document, indent=2, sort_keys=True))
            return None
        publish_guard_handover(write_fd, result)
        # The admission travels through this pipe and nowhere else: the descriptor is made
        # inheritable and the process is replaced, so the guard phase's interpreter - including
        # its torch import - does not survive into the broker phase.
        os.set_inheritable(read_fd, True)
        child_environment = dict(os.environ)
        child_environment[GUARD_RESULT_FD_VARIABLE] = str(read_fd)
        child_environment[GUARD_PHASE_VARIABLE] = BROKER_PHASE
        child_environment["PYTORCH_ENABLE_MPS_FALLBACK"] = "0"
        os.execve(sys.executable, [sys.executable, "-m", spec.module, *argv], child_environment)
        raise AssertionError("unreachable")  # pragma: no cover - execve never returns

    document["start_guard"] = _audit_guard(arguments)
    admitted = broker_phase_guard(os.environ, scope=scope,
                                  max_age_s=plan.start_guard_timeout_s)
    document["start_guard_admission"] = {"status": admitted.status,
                                         "epoch": admitted.scope.epoch,
                                         "source": "inherited-pipe"}
    return admitted
