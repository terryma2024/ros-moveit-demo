"""Paired microbenchmark for the profiling-disabled hot paths."""

from __future__ import annotations

import gc
import json
import random
import statistics
import sys
from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter_ns

from so101_demo.application.text_agent import AgentRequest, TextAgent
from so101_demo.core.domain import ActionResult, ActionStatus, RunRequest, State
from so101_demo.core.runner import ExecutionContext
from so101_demo.ports.pick_place_executor import RuntimeDispatchResult
from so101_demo.ports.task_planner import PlannerCandidate, PlannerMetadata
from so101_demo.profiling.wrappers import profile_actions


ITERATIONS = 10_000
WARMUP_REPEATS = 5
MEASURED_REPEATS = 30


class _Planner:
    _candidate = PlannerCandidate(
        value={
            "outcome": "supported",
            "command": {
                "target_object": "plastic_cup",
                "action": "pick",
                "constraints": {},
            },
        },
        metadata=PlannerMetadata("benchmark", "fixed", 0, 0, 0, 0, False),
    )

    def plan(self, _instruction: str) -> PlannerCandidate:
        return self._candidate


class _Executor:
    def dispatch(self, _request) -> RuntimeDispatchResult:
        raise AssertionError("preview must not dispatch")


class _Action:
    _result = ActionResult(ActionStatus.SUCCEEDED)

    def run(self, _context: ExecutionContext) -> ActionResult:
        return self._result


@dataclass(frozen=True, slots=True)
class _Scenario:
    name: str
    baseline: Callable[[], None]
    disabled: Callable[[], None]


def _text_agent_scenario() -> _Scenario:
    request = AgentRequest(
        request_id="benchmark-request",
        instruction="pick the plastic cup",
        mode="preview",
        execute=False,
        backend="mujoco",
    )
    baseline_agent = TextAgent(_Planner(), _Executor())
    disabled_agent = TextAgent(_Planner(), _Executor(), profiler=None)
    return _Scenario(
        "text_agent_preview",
        lambda: baseline_agent._handle(request),
        lambda: disabled_agent.handle(request),
    )


def _state_action_scenario() -> _Scenario:
    state = State.PREPARE_OPEN_GRIPPER
    context = ExecutionContext(RunRequest(), state, 0)
    action = _Action()
    baseline_actions = {state: action}
    disabled_actions = profile_actions({state: action}, None)
    return _Scenario(
        "dry_run_state_action",
        lambda: baseline_actions[state].run(context),
        lambda: disabled_actions[state].run(context),
    )


def _measure(call: Callable[[], None]) -> int:
    started = perf_counter_ns()
    for _ in range(ITERATIONS):
        call()
    return perf_counter_ns() - started


def _run_scenario(scenario: _Scenario, rng: random.Random) -> dict[str, object]:
    for _ in range(WARMUP_REPEATS):
        calls = [scenario.baseline, scenario.disabled]
        rng.shuffle(calls)
        for call in calls:
            _measure(call)

    samples: dict[str, list[float]] = {"baseline": [], "disabled": []}
    for _ in range(MEASURED_REPEATS):
        cases = [
            ("baseline", scenario.baseline),
            ("disabled", scenario.disabled),
        ]
        rng.shuffle(cases)
        for name, call in cases:
            samples[name].append(_measure(call) / ITERATIONS)

    baseline = statistics.median(samples["baseline"])
    disabled = statistics.median(samples["disabled"])
    allowed_delta = max(baseline * 0.02, 100.0)
    delta = disabled - baseline
    return {
        "name": scenario.name,
        "iterations_per_repeat": ITERATIONS,
        "warmup_repeats": WARMUP_REPEATS,
        "measured_repeats": MEASURED_REPEATS,
        "baseline_median_ns_per_iteration": baseline,
        "disabled_median_ns_per_iteration": disabled,
        "delta_ns_per_iteration": delta,
        "allowed_delta_ns_per_iteration": allowed_delta,
        "pass": delta <= allowed_delta,
    }


def main() -> int:
    rng = random.Random(0x501)
    gc.disable()
    try:
        results = [
            _run_scenario(_text_agent_scenario(), rng),
            _run_scenario(_state_action_scenario(), rng),
        ]
    finally:
        gc.enable()
    document = {
        "schema_version": 1,
        "python": sys.version,
        "results": results,
        "pass": all(bool(result["pass"]) for result in results),
    }
    print(json.dumps(document, sort_keys=True, separators=(",", ":")))
    return 0 if document["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
