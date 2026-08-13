from dataclasses import dataclass

import pytest

PHASES = (
    "OBSERVE_INITIAL",
    "CANCEL_ARM_GOALS",
    "CANCEL_GRIPPER_GOALS",
    "DETACH_PHYSICAL",
    "DETACH_MOVEIT",
    "PARK_CUP",
    "SYNC_PARKED_SCENE",
    "OPEN_GRIPPER",
    "PLAN_HOME",
    "EXECUTE_HOME",
    "RESTORE_CUP",
    "SYNC_FINAL_SCENE",
    "VERIFY_FINAL",
)


@dataclass
class FakeResetPorts:
    failure_at: str | None = None

    def __post_init__(self) -> None:
        self.calls = []
        self.plan = object()

    def _step(self, phase: str):
        from so101_demo.ports.reset import ResetStepReceipt

        self.calls.append(phase)
        if phase == self.failure_at:
            return ResetStepReceipt(
                False,
                f"RESET_{phase}_FAILED",
                {"phase": phase, "observed": "failed"},
            )
        return ResetStepReceipt(True, None, {"phase": phase, "observed": "ok"})

    def observe_initial(self):
        return self._step("OBSERVE_INITIAL")

    def cancel_arm_goals(self):
        return self._step("CANCEL_ARM_GOALS")

    def cancel_gripper_goals(self):
        return self._step("CANCEL_GRIPPER_GOALS")

    def detach_task_object(self):
        caller = "DETACH_PHYSICAL" if "DETACH_PHYSICAL" not in self.calls else "DETACH_MOVEIT"
        return self._step(caller)

    def park_task_object(self, pose):
        self.park_pose = pose
        return self._step("PARK_CUP")

    def synchronize_task_scene(self, pose):
        phase = "SYNC_PARKED_SCENE" if "SYNC_PARKED_SCENE" not in self.calls else "SYNC_FINAL_SCENE"
        self.scene_poses = getattr(self, "scene_poses", []) + [pose]
        return self._step(phase)

    def open_gripper(self):
        return self._step("OPEN_GRIPPER")

    def plan_home(self, named_state: str):
        from so101_demo.ports.reset import HomePlanReceipt

        self.calls.append("PLAN_HOME")
        self.named_state = named_state
        if self.failure_at == "PLAN_HOME":
            return HomePlanReceipt(False, None, "RESET_PLAN_HOME_FAILED", {})
        return HomePlanReceipt(True, self.plan, None, {"plan_id": "exact-home"})

    def execute_home_and_verify(self, plan):
        self.executed_plan = plan
        return self._step("EXECUTE_HOME")

    def restore_task_object(self, pose):
        self.restore_pose = pose
        return self._step("RESTORE_CUP")

    def verify_final(self):
        return self._step("VERIFY_FINAL")


def _request():
    from so101_demo.core.task_geometry import Pose7
    from so101_demo.ports.reset import TransactionalResetRequest

    return TransactionalResetRequest(
        backend="gazebo",
        session_id="reset-session",
        named_home_state="home",
        parking_pose=Pose7((0.45, 0.25, 0.08, 0.0, 0.0, 0.0, 1.0)),
        spawn_pose=Pose7((0.02, -0.28, 0.165, 0.0, 0.0, 0.0, 1.0)),
    )


def _coordinator(fake: FakeResetPorts):
    from so101_demo.application.transactional_reset import TransactionalResetCoordinator
    from so101_demo.ports.reset import TransactionalResetPorts

    return TransactionalResetCoordinator(
        TransactionalResetPorts(
            observation=fake,
            goals=fake,
            physical=fake,
            scene=fake,
            robot=fake,
        )
    )


def test_transaction_runs_all_thirteen_phases_and_reuses_exact_plan() -> None:
    fake = FakeResetPorts()

    receipt = _coordinator(fake).run(_request())

    assert receipt.success
    assert receipt.phase == "VERIFY_FINAL"
    assert receipt.failure_code is None
    assert fake.calls == list(PHASES)
    assert fake.named_state == "home"
    assert fake.executed_plan is fake.plan
    assert fake.park_pose == _request().parking_pose
    assert fake.restore_pose == _request().spawn_pose
    assert fake.scene_poses == [_request().parking_pose, _request().spawn_pose]
    assert receipt.evidence["completed_phases"] == list(PHASES)


@pytest.mark.parametrize("failure_at", PHASES)
def test_transaction_stops_at_first_failed_phase_without_partial_success(
    failure_at: str,
) -> None:
    fake = FakeResetPorts(failure_at)

    receipt = _coordinator(fake).run(_request())

    index = PHASES.index(failure_at)
    assert not receipt.success
    assert receipt.phase == failure_at
    assert receipt.failure_code == f"RESET_{failure_at}_FAILED"
    assert fake.calls == list(PHASES[: index + 1])
    assert receipt.evidence["completed_phases"] == list(PHASES[:index])
    assert "partial_success" not in receipt.evidence


def test_port_exception_maps_to_stable_phase_failure() -> None:
    fake = FakeResetPorts()

    def fail():
        raise RuntimeError("transport disappeared")

    fake.cancel_gripper_goals = fail
    receipt = _coordinator(fake).run(_request())

    assert not receipt.success
    assert receipt.phase == "CANCEL_GRIPPER_GOALS"
    assert receipt.failure_code == "RESET_CANCEL_GRIPPER_GOALS_FAILED"
    assert receipt.evidence["failure"]["exception_type"] == "RuntimeError"


def test_real_physical_port_fails_closed() -> None:
    from so101_demo.ports.reset import FailClosedPhysicalObjectResetPort

    result = FailClosedPhysicalObjectResetPort().detach_task_object()

    assert not result.success
    assert result.failure_code == "RESET_REAL_ARM_UNAVAILABLE"
