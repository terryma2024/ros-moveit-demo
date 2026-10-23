"""The rollout's wave coordinator: the collection coordinator with the rollout's task document and time budget.

Everything that makes a wave safe is the collection's own and is reused unchanged: the READY barrier (no task is assigned until
every shard of the wave reports READY), the per-instance status polling that doubles as liveness, one task at a time per instance,
the `RecordingGate` (concurrent episodes cap, tasks in flight, minimum gap between assignments), the durable task journal and the
wave cleanup proof. Only the task document (`task_document`) and the per-task time budget (`task_budget_s`) differ, and the units
carry no per-unit file references: the frozen inputs are common to the run and travel in every task document.
"""

from __future__ import annotations

from so101_demo.runtime.container_campaign.coordinator import ConcurrentCollectionCoordinator, InstanceDispatch
from so101_demo.runtime.act_rollout import task_builder
from so101_demo.runtime.act_rollout.plan import Unit


class RolloutInstanceDispatch(InstanceDispatch):
    """The per-instance loop; `rollout` (set on the class by the coordinator factory) describes the run."""

    rollout = None

    def task_document(self, task_id, scene_id):
        rollout = self.rollout
        unit = rollout["units"][scene_id]
        # the client id names the attempt, so every request row of the policy service joins to an episode
        policy = dict(rollout["policy"], client_id=f"{self.worker_id}-g{self.generation}-{scene_id}")
        return dict(schema_version=1, kind=task_builder.KIND, task_id=task_id, worker_id=self.worker_id,
                    launch_generation=self.generation, wave_id=self.wave_id, scene_id=scene_id, point_id=unit.point_id,
                    group=unit.group, trial=unit.trial, attempt_number=unit.attempt_number, attempt_id=unit.unit_id,
                    run_id=rollout["run_id"], run_identity_sha256=rollout["run_identity_sha256"],
                    inputs=dict(rollout["inputs"]), execution=dict(rollout["execution"]), policy=policy,
                    preconditions=rollout["preconditions"])

    def task_budget_s(self):
        return self.rollout["task_timeout_s"]


class RolloutCoordinator(ConcurrentCollectionCoordinator):
    WORKLOAD_KIND = "act_rollout_start"
    CASE_REFS = frozenset()

    def __init__(self, *, rollout, units, **kwargs):
        """`rollout`: the run's description every task document is made from; `units`: `{unit_id: Unit}` of this wave."""
        for unit in units.values():
            if type(unit) is not Unit:
                raise ValueError("ROLLOUT_COORDINATOR_UNITS_INVALID")
        self.units = dict(units)
        dispatch = type("BoundRolloutInstanceDispatch", (RolloutInstanceDispatch,),
                        {"rollout": dict(rollout, units=self.units)})
        self.DISPATCH = dispatch
        super().__init__(case_inputs={unit_id: {} for unit_id in units}, **kwargs)

