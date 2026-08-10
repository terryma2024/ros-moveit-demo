from pathlib import Path
import yaml

from so101_gazebo_demo.domain import State
from so101_gazebo_demo.workflow import SO101_WORKFLOW
from .run_behavior_matrix import run_behavior


FIXTURE=Path(__file__).parents[1]/"fixtures/behavior_matrix.yaml"


def test_frozen_reference_cases_match() -> None:
    for case in yaml.safe_load(FIXTURE.read_text())["cases"]:
        observed=run_behavior(case["arguments"])
        for key,value in case["expected"].items(): assert observed[key] == value, case["case"]


def test_every_action_failure_and_stop_boundary_is_machine_comparable() -> None:
    forward=set(run_behavior(["--mode","dry_run"])["state_trace"])
    for state in sorted(SO101_WORKFLOW.action_states,key=lambda item:item.value):
        failed=run_behavior(["--mode","dry_run","--fail-at",state.value])
        if state.value in forward:
            expected_exit = 0 if state is State.VERIFY_PHYSICAL_GRASP else 1
            assert failed["exit_code"] == expected_exit and failed["failure_code"] == "INJECTED_FAILURE"
        else:
            assert failed["status"] == "DONE"
        stopped=run_behavior(["--mode","dry_run","--stop-after",state.value])
        assert stopped["exit_code"] in (0,1)


def test_every_supported_plan_only_state_plans_exactly_that_state() -> None:
    for state in SO101_WORKFLOW.plan_only_states:
        result=run_behavior(["--mode","plan_only","--plan-only-state",state.value])
        assert result["exit_code"] == 0
        assert result["status"] == "PLAN_ONLY_COMPLETE"
        assert result["state_trace"] == [state.value]
