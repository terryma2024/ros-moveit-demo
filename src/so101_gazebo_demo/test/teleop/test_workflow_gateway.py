import asyncio

import pytest

from so101_teleop.models import ValidationEvidence, WorkflowSnapshot
from so101_teleop.workflow_gateway import WorkflowGateway, WorkflowRejected


class FakeRunner:
    def __init__(self):
        self.steps = []

    async def start(self, run_id, session_id):
        return WorkflowSnapshot(run_id=run_id, current_state="IDLE", next_state="CLOSE_GRIPPER",
                                checkpoint_session_id=session_id, checkpoint_fresh=True)

    async def step(self, run_id, override=False):
        self.steps.append((run_id, override))
        if override:
            return WorkflowSnapshot(run_id=run_id, current_state="VERIFY_PHYSICAL_GRASP",
                                    next_state="ATTACH_GAZEBO", checkpoint_fresh=True)
        return WorkflowSnapshot(
            run_id=run_id, current_state="VALIDATION_FAILED", next_state="VERIFY_PHYSICAL_GRASP",
            checkpoint_fresh=True,
            validation=ValidationEvidence(passed=False, failure_code="PHYSICAL_GRASP_FOLLOW_RATIO",
                                          measured={"cup_follow_ratio": 0.2}, thresholds={"min_cup_follow_ratio": 0.8}),
        )


def test_step_derives_only_checkpoint_next_state_without_browser_state_input():
    """Allowing a browser-selected state would allow Attach to be skipped into."""
    async def scenario():
        runner = FakeRunner()
        gateway = WorkflowGateway(runner)
        started = await gateway.start("run-a", "session-a")

        result = await gateway.step("run-a", snapshot_revision=4)

        assert started.next_state == "CLOSE_GRIPPER"
        assert runner.steps == [("run-a", False)]
        assert result.current_state == "VALIDATION_FAILED"

    asyncio.run(scenario())


def test_force_continue_is_one_shot_and_binds_validation_evidence():
    """Reusing an override after it advances would turn a narrow validation exception into a bypass."""
    async def scenario():
        gateway = WorkflowGateway(FakeRunner())
        await gateway.start("run-a", "session-a")
        await gateway.step("run-a", snapshot_revision=7)

        advanced = await gateway.force_continue("force-1", "run-a", 7, "FORCE CONTINUE")

        assert advanced.next_state == "ATTACH_GAZEBO"
        assert len(advanced.override_audit) == 1
        with pytest.raises(WorkflowRejected, match="OVERRIDE_NOT_ALLOWED"):
            await gateway.force_continue("force-2", "run-a", 7, "FORCE CONTINUE")

    asyncio.run(scenario())


def test_force_continue_rejects_action_failure_and_stale_checkpoint():
    """An action/controller failure or stale checkpoint must remain non-overridable."""
    async def scenario():
        gateway = WorkflowGateway(FakeRunner())
        await gateway.start("run-a", "session-a")
        gateway._snapshot = WorkflowSnapshot(run_id="run-a", current_state="VALIDATION_FAILED",
                                             checkpoint_fresh=False,
                                             validation=ValidationEvidence(passed=False, failure_code="ACTION_FAILED"))

        with pytest.raises(WorkflowRejected, match="OVERRIDE_NOT_ALLOWED"):
            await gateway.force_continue("force-1", "run-a", 2, "FORCE CONTINUE")

    asyncio.run(scenario())
