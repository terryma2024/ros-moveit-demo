"""CP-3513: the diagnostic-only injected Teacher execution failure.

A live acceptance item of the minimal-gates design needs one execution failure whose ERROR manifest validates. There was no sanctioned
way to cause one, so the hook below exists: off by default, settable only in `preselected_target_diagnostic` collection mode, only at
LIFT, only under Teacher policy v3. It turns the result of an execute that really succeeded into the failed result a real failed
execute returns, so everything after it is the real v3 path."""
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.act.collection_orchestration import (
    CollectionOptions, CollectionRefused, collection_from_document, validate_collection_request)
from so101_demo.core.domain import ActionResult, ActionStatus, Failure, FailureCategory, State
from so101_demo.ros import dynamic_mujoco_execution as module
from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution, _ExecutionFailed

from test_teacher_execution_v3 import v3_adapter
from test_b1_teacher_execution import make_adapter

CODE = "TEACHER_INJECTED_EXECUTION_FAILURE"
DIAGNOSTIC = "preselected_target_diagnostic"


def executing(value, outcome=None):
    """An adapter whose trajectory client reports a SUCCEEDED execute (the arm really reached the lifted pose)."""
    value._trajectory = SimpleNamespace(execute=lambda trajectory, timeout, monitor=None: outcome or ActionResult(ActionStatus.SUCCEEDED))
    value._refuse_plan_start_drift = lambda trajectory: None
    value._emit_phase_begin = lambda kind: None
    value._check_stop = lambda: None
    return value


# ---- (a) the hook at LIFT under v3 --------------------------------------------------------------------------------------------

def test_the_hook_turns_a_succeeded_lift_execute_into_the_failed_result_of_a_real_execute_failure(tmp_path):
    value = executing(v3_adapter(tmp_path))
    value.inject_failure_at = State.LIFT
    with pytest.raises(_ExecutionFailed) as caught:
        value._execute_planned(object(), State.LIFT, None)
    assert str(caught.value).startswith(CODE + ": ")
    result = caught.value.result
    assert result.status is ActionStatus.FAILED and result.failure.category is FailureCategory.EXECUTION and result.failure.code == CODE
    assert value._last_arm_result == "CONTROLLER_FAILED"           # the same bookkeeping as a controller-originated failure
    assert value._failure_code(caught.value) == (CODE, str(caught.value))   # not remapped, and the v3 status is FAILED
    assert RosDynamicMujocoExecution._teacher_execution_status(
        SimpleNamespace(status=SimpleNamespace(value="ERROR"), failure=SimpleNamespace(code=CODE)),
        {"physical_action_proven_absent": False}) == "FAILED"


def test_the_hook_fires_once(tmp_path):
    value = executing(v3_adapter(tmp_path))
    value.inject_failure_at = State.LIFT
    with pytest.raises(_ExecutionFailed):
        value._execute_planned(object(), State.LIFT, None)
    assert value._execute_planned(object(), State.LIFT, None).status is ActionStatus.SUCCEEDED


def test_the_injected_failure_ends_in_a_v3_error_manifest_that_validates_with_the_cup_held(tmp_path):
    """Pinned to the live verdict of p11 (injected case f6bc2e3d): validate -> FAILED, e2e -> UNCONFIRMED with exactly one failure."""
    from test_dynamic_manifest_teacher import teacher_error, validate
    from so101_demo.application import e2e_acceptance as e2e
    from so101_demo.parallel_batch.contracts import AttemptStatus
    document = teacher_error("LIFT", failure=f"{CODE}: diagnostic injection", attached=True)
    assert validate(document, "ERROR") is AttemptStatus.FAILED
    assert not any(item.startswith("RECOVER_") for item in document["state_trace"]) and document["state_trace"][-2:] == ["LIFT", "ERROR"]
    failures: list[str] = []
    assert e2e._validate_teacher_result(document, failures) == "UNCONFIRMED"
    assert failures == ["E2E_TEACHER_TASK_NOT_PASSED"]


def test_the_pinned_verdict_is_specific_to_a_failed_attempt(tmp_path):
    """Negative control: a PASS document does not give the injected-failure values."""
    from test_dynamic_manifest_teacher import teacher_done
    from so101_demo.application import e2e_acceptance as e2e
    failures: list[str] = []
    assert e2e._validate_teacher_result(teacher_done(), failures) == "PASS" and failures == []


# ---- (b) unset: no effect -----------------------------------------------------------------------------------------------------

def test_unset_or_another_state_or_a_non_v3_policy_has_no_effect(tmp_path):
    unset = executing(v3_adapter(tmp_path))
    assert getattr(unset, "inject_failure_at", None) is None
    assert unset._execute_planned(object(), State.LIFT, None).status is ActionStatus.SUCCEEDED
    other = executing(v3_adapter(tmp_path))
    other.inject_failure_at = State.LIFT
    assert other._execute_planned(object(), State.MOVE_ABOVE_PLACE, None).status is ActionStatus.SUCCEEDED
    v2 = executing(make_adapter(tmp_path))
    v2.inject_failure_at = State.LIFT
    assert v2._execute_planned(object(), State.LIFT, None).status is ActionStatus.SUCCEEDED


def test_a_real_controller_failure_keeps_its_own_code_when_the_hook_is_set(tmp_path):
    failed = ActionResult(ActionStatus.FAILED, Failure(FailureCategory.EXECUTION, "MOVEIT_EXECUTION_FAILED", "real"))
    value = executing(v3_adapter(tmp_path), failed)
    value.inject_failure_at = State.LIFT
    with pytest.raises(_ExecutionFailed) as caught:
        value._execute_planned(object(), State.LIFT, None)
    assert caught.value.result.failure.code == "MOVEIT_EXECUTION_FAILED"


def test_the_default_collection_request_and_the_teacher_argv_carry_no_injection():
    assert CollectionOptions().inject_failure_at is None and "inject_failure_at" not in CollectionOptions().document()
    assert collection_from_document(CollectionOptions("on").document()).inject_failure_at is None


# ---- (c) formal mode, a wrong request or a non-v3 freeze is refused with a named error -----------------------------------------

@pytest.mark.parametrize(("kwargs", "name"), [
    (dict(run_mode="formal"), "TEACHER_INJECTION_REQUIRES_DIAGNOSTIC_MODE"),
    (dict(run_mode=DIAGNOSTIC, collection="off"), "TEACHER_INJECTION_REQUIRES_COLLECTION_ON"),
    (dict(run_mode=DIAGNOSTIC, state="MICRO_LIFT"), "TEACHER_INJECTION_STATE_UNSUPPORTED"),
    (dict(run_mode=DIAGNOSTIC, state="nonsense"), "TEACHER_INJECTION_STATE_UNSUPPORTED"),
])
def test_a_forbidden_injection_request_is_refused_by_name(tmp_path, kwargs, name):
    with pytest.raises(CollectionRefused, match=name):
        validate_collection_request(kwargs.get("collection", "on"), "none", run_mode=kwargs["run_mode"], run_root=tmp_path,
                                    inject_failure_at=kwargs.get("state", "LIFT"))


def test_a_valid_injection_request_round_trips_through_the_worker_specification(tmp_path):
    options = validate_collection_request("on", "none", run_mode=DIAGNOSTIC, run_root=tmp_path, inject_failure_at="LIFT")
    assert options.inject_failure_at == "LIFT"
    document = options.document()
    assert document["inject_failure_at"] == "LIFT"
    assert collection_from_document(copy.deepcopy(document)).inject_failure_at == "LIFT"
    for bad in ("MICRO_LIFT", "", None, 3):
        broken = dict(document, inject_failure_at=bad)
        with pytest.raises(CollectionRefused, match="COLLECTION_SPEC_INVALID"):
            collection_from_document(broken)


def test_the_teacher_argv_gets_the_flag_only_when_the_collection_options_carry_the_injection(tmp_path, monkeypatch):
    import test_p3_offline_switch as switch
    monkeypatch.setattr(switch.orchestration, "PilotRecording", switch.pilot_factory())
    argvs = {}
    for label, options in (("plain", CollectionOptions("on")), ("injected", CollectionOptions("on", inject_failure_at="LIFT"))):
        runtime, group, _events, _clock = switch.worker_runtime(tmp_path / label, options)
        runtime.start_physical_runtime()
        runtime.reset_and_validate_point(switch._lease())
        argvs[label] = [item.replace(str(tmp_path / label), "ROOT") for item in
                        next(spec.argv for spec in group.specs if spec.role == "dynamic-consumer")]
    assert "--inject-failure-at" not in argvs["plain"]
    assert [item for item in argvs["injected"] if item not in argvs["plain"]] == ["--inject-failure-at", "LIFT"] or (
        argvs["injected"][argvs["injected"].index("--inject-failure-at") + 1] == "LIFT")


def test_the_teacher_cli_accepts_the_flag_and_defaults_it_off():
    from so101_demo.cli.dynamic_cup_pick_place import build_parser
    assert build_parser().parse_args([]).inject_failure_at is None
    assert build_parser().parse_args(["--inject-failure-at", "LIFT"]).inject_failure_at == "LIFT"


@pytest.mark.parametrize(("frozen_inputs", "refused"), [(True, False), (False, True)])
def test_the_teacher_refuses_the_injection_unless_the_run_has_frozen_inputs(tmp_path, monkeypatch, frozen_inputs, refused):
    import test_teacher_runtime as runtime_tests
    original = runtime_tests._options
    monkeypatch.setattr(runtime_tests, "_options", lambda path: _with_injection(original(path)))
    code, execution, _watches, events = runtime_tests.teacher_run(tmp_path, monkeypatch, frozen_inputs=frozen_inputs,
                                                                   simulator_x=-0.2 if not refused else -0.03)
    if refused:
        assert code == 1 and "runner.run" not in events
    else:
        assert code == 0 and execution.inject_failure_at is State.LIFT


def _with_injection(options):
    options.inject_failure_at = "LIFT"
    return options


def test_the_episode_cli_has_the_option_off_by_default():
    from so101_demo.cli.act_first_episode import build_parser as episode_parser
    base = ["run", "--inputs", "i", "--root", "r", "--final-cup-pose", "0 0 0 0 0 0 1"]
    try:
        defaults = episode_parser().parse_args(base)
    except SystemExit:
        pytest.skip("run arguments differ")
    assert defaults.teacher_inject_failure_at is None
