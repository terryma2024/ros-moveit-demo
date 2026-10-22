"""A whole parallel rollout run over doubles: waves, re-queue of INVALID attempts, verification, proofs, receipts and results.

Real: `RolloutCampaignOwner`, `RolloutCoordinator` (with the collection's `InstanceDispatch`, `RecordingGate`, task journal and wave
cleanup proof), `WaveAssignment`, the task documents and task-result files, `aggregate`, `container_receipts.seal_stage_containers`,
`stage_records`. Controlled doubles: the container shards (`FakeShard`), the shard's task control (`Instance`, shaped like
`ContainerTaskControl`, which writes the episode files a shard would), the policy service owner and the launch registry.
No Docker, container, ROS or GPU is involved.
"""

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.cli.mujoco_batch.request import _load_runtime_config
from so101_demo.runtime.act_rollout import task_builder
from so101_demo.runtime.act_rollout.coordinator import RolloutCoordinator
from so101_demo.runtime.act_rollout.owner import (
    EXIT_INVALID, EXIT_OK, EXIT_START_FAILED, EXIT_STOP_UNCONFIRMED, RolloutCampaignOwner)
from so101_demo.runtime.act_rollout.plan import build_units
from so101_demo.runtime.container_campaign.paths import make_campaign_paths
from so101_demo.runtime.container_campaign.task_contracts import InstanceStatus, TaskStatus
from so101_demo.runtime.container_campaign.task_results import reserve_task_output, write_task_result
from so101_teleop.unified.contracts import AdmittedCampaignContext

from paths import PACKAGE_ROOT

GPU = "GPU-28221cec-9d21-7753-fd5a-da645740df19"
SCENES = {"groups": {"rollout_standard": [{"scene_id": "task_start"}, {"scene_id": "forward_5cm"}]}}


@pytest.fixture(scope="module")
def runtime():
    return _load_runtime_config(PACKAGE_ROOT / "config/mujoco/parallel_batch_act_offline.yaml")


class Clock:
    """Fake monotonic time advanced by the polling sleep; a tiny real pause keeps it from outrunning file I/O."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.now += seconds
        await asyncio.sleep(0.0005)


class Registry:
    def __init__(self):
        self.proved = []

    def all_terminated(self, inspect):
        return True

    def records(self):
        return []

    def prove_terminated(self, launch_id, document):
        self.proved.append(launch_id)
        return True


class FakeShard:
    """Shaped like `ContainerShardOwner` as the coordinator and the owner use it."""

    def __init__(self, world, launch, root):
        self.world, self.launch, self.root, self.registry = world, launch, root, world.registry
        self._close_task = None
        self.teacher_socket = Path("/act/ipc/teacher/unused.sock")

    async def close(self):
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close())
        return await asyncio.shield(self._close_task)

    async def _close(self):
        self.world.closed.append(self.launch.launch_id)
        return dict(terminated=self.world.close_ok, launch_id=self.launch.launch_id, errors=[])

    def observe_exit(self):
        return {"State": {"Status": "exited"}}


class Launcher:
    def __init__(self, world):
        self.world = world

    def __call__(self, *, plan, worker_ids, context):
        world = self.world
        world.launches.append((plan["wave_index"], worker_ids, context.worker_count))
        shards = []
        for worker_id in worker_ids:
            root = world.run / f"wave-{plan['wave_index']}" / worker_id / f"g{plan['wave_index'] + 1}"
            (root / "output").mkdir(parents=True)
            (root / "task-inputs").mkdir()
            launch = SimpleNamespace(launch_id=f"wave-{plan['wave_index']}-{worker_id}-g{plan['wave_index'] + 1}",
                                     worker_id=worker_id, launch_generation=plan["wave_index"] + 1,
                                     wave_id=f"wave-{plan['wave_index']}", owned_root=str(root))
            shards.append(FakeShard(world, launch, root))
        return tuple(shards)


class Instance:
    """The shard's task control: accepts a task, finishes it after `POLLS` polls and writes what the shard would."""

    POLLS = 40          # long enough that two shards' tasks certainly overlap in real time

    def __init__(self, world, shard):
        self.world, self.shard, self.instance_id = world, shard, shard.launch.launch_id
        self.delivered = {}

    async def start(self):
        if self.world.start_error is not None:
            raise self.world.start_error
        return InstanceStatus(instance_id=self.instance_id, state="READY")

    async def assign_task(self, task):
        document = json.loads(Path(task.inputs_ref.path).read_text())
        self.world.documents[task.task_id] = document
        self.world.running += 1
        self.world.max_running = max(self.world.max_running, self.world.running)
        self.delivered[task.task_id] = 0
        return TaskStatus(task_id=task.task_id, state="ACCEPTED")

    async def get_status(self, task_id=None):
        if task_id is None:
            return InstanceStatus(instance_id=self.instance_id, state="READY")
        self.delivered[task_id] += 1
        if self.delivered[task_id] < self.POLLS:
            return InstanceStatus(instance_id=self.instance_id, state="BUSY", task=TaskStatus(task_id=task_id, state="RUNNING"))
        if self.delivered[task_id] == self.POLLS:
            self.world.running -= 1
            failed = self.world.finish(self.shard, task_id)
            if failed:
                return InstanceStatus(instance_id=self.instance_id, state="BUSY",
                                      task=TaskStatus(task_id=task_id, state="FAILED", fault_reason="boom"))
        return InstanceStatus(instance_id=self.instance_id, state="READY", task=TaskStatus(task_id=task_id, state="SUCCEEDED"))

    async def terminate(self, reason):
        return InstanceStatus(instance_id=self.instance_id, state="TERMINATED", resources_released=True)


class Policy:
    def __init__(self, world):
        self.world = world
        self.process = SimpleNamespace(pid=4242)
        self.stop_result = None
        self.healthy_answers = []

    def start(self):
        if self.world.policy_error is not None:
            raise self.world.policy_error
        return {"ready": True, "bundle_sha256": "a" * 64}

    def healthy(self):
        return self.healthy_answers.pop(0) if self.healthy_answers else True

    def stop(self):
        self.world.policy_stopped += 1
        self.stop_result = {"confirmed": self.world.policy_stop_ok, "stop_proof_sha256": "e" * 64, "errors": []}
        return self.stop_result


class World:
    def __init__(self, tmp_path, runtime, *, shards=2, trials=2, retries=1, cap=None):
        self.paths = make_campaign_paths(tmp_path, "run-1")
        self.run = self.paths["run"]
        self.runtime = runtime
        self.clock = Clock()
        self.registry = Registry()
        self.script = {}                      # unit id -> dict(verdict, reason, mode)
        self.documents, self.launches, self.closed = {}, [], []
        self.running = self.max_running = 0
        self.start_error = self.policy_error = None
        self.close_ok = self.policy_stop_ok = True
        self.policy_stopped = 0
        self.policy = Policy(self)
        self.context = AdmittedCampaignContext(
            campaign_id="run-1", operation_id="run-1", workload_kind="act_rollout_start", service_epoch="epoch",
            execution_generation=1, stable_host_id="host", physical_gpu_uuid=GPU, worker_count=shards, source_sha256="d" * 64,
            manifest_sha256="d" * 64, runtime_config_sha256="d" * 64, collection_config_sha256="d" * 64,
            contact_policy_fingerprint="d" * 64, domain_session_map_sha256="d" * 64, resource_binding_id="self",
            evidence_root=str(self.run), admitted_at_monotonic_s=1, deadline_monotonic_s=self.clock.now + 1e6)
        self.options = SimpleNamespace(shards=shards, max_invalid_retries=retries)
        self.units = build_units(SCENES, group="rollout_standard", scene_ids=None, trials=trials, max_invalid_retries=retries)
        self.description = {
            "run_id": "run-1", "run_identity_sha256": "9" * 64,
            "inputs": {"inputs_manifest": {"path": "/x", "sha256": "1" * 64}, "bundle_dir": "/bundle", "install_prefix": "/i"},
            "execution": {"execution_prefix": None, "temporal_ensembling": 0.01},
            "policy": {"socket_path": "/act/ipc/policy/policy.sock", "service_generation": "gen-1", "max_frame_bytes": 4096,
                       "bundle_sha256": "a" * 64, "policy_sha256": "b" * 64},
            "preconditions": {"no_container": {"ok": True, "detail": []}}, "task_timeout_s": 600.0}
        scenes = self.run.parent / "scenes.json"
        scenes.write_text("{}")
        import hashlib
        self.scene_manifest = {"path": str(scenes), "sha256": hashlib.sha256(scenes.read_bytes()).hexdigest()}
        self.cap = cap
        self.instances = {}

    def coordinator_factory(self, *, context, units):
        return RolloutCoordinator(rollout=self.description, units=units, context=context, config=self.runtime,
                                  scene_manifest=self.scene_manifest, max_recording_shards=self.cap, clock=self.clock,
                                  sleep=self.clock.sleep,
                                  control_factory=lambda shard: self.instances.setdefault(shard.launch.launch_id,
                                                                                         Instance(self, shard)))

    def owner(self, **changes):
        arguments = dict(context=self.context, run=self.run, registry=self.registry, launcher=Launcher(self),
                         coordinator_factory=self.coordinator_factory, policy=self.policy, units=self.units,
                         rollout=self.description, options=self.options, docker_runner=lambda argv: None,
                         inspect_container=lambda cid: {}, clock=self.clock, monitor_interval_s=0.005)
        arguments.update(changes)
        return RolloutCampaignOwner(**arguments)

    def finish(self, shard, task_id):
        """Write what the shard's task leaves; True when the task fails instead."""
        document = self.documents[task_id]
        unit_id = document["scene_id"]
        behaviour = self.script.get(unit_id, {})
        if behaviour.get("mode") == "fail":
            return True
        verdict = behaviour.get("verdict", "DONE")
        reason = behaviour.get("reason")
        task_dir = reserve_task_output(shard.root / "output", task_id)
        episode = task_dir / "episode"
        episode.mkdir()
        names = ("episode.json", "endpoint.json", "steps.jsonl", "world.jsonl", "stop-proof.json")
        for name in names:
            (episode / name).write_text("{}\n")
        (episode / "episode.json").write_text(json.dumps({
            "kind": "ACT_ROLLOUT_EPISODE", "run_id": "run-1", "attempt_id": unit_id,
            "verdict": behaviour.get("episode_verdict", verdict), "result": {"motion": {"max_arm_displacement_rad": 0.75}}}))
        result = {"schema_version": 1, "kind": task_builder.RESULT_KIND, "task_id": task_id,
                  "scene_id": behaviour.get("scene_id", unit_id), "point_id": document["point_id"], "group": document["group"],
                  "trial": document["trial"], "attempt_number": document["attempt_number"], "attempt_id": unit_id,
                  "verdict": verdict, "done": verdict == "DONE", "reason": reason, "status": "COMPLETED", "retire_errors": [],
                  "elapsed_wall_s": 120.5, "task_wall_s": 130.0, "counts": {"applied": 10, "clamped_steps": 0},
                  "clamped_steps": 0, "evidence": [f"episode/{name}" for name in names], "goal_response": {"pairs": 10},
                  "stop_confirmed": True}
        write_task_result(shard.root / "output", task_id, result)
        return False


def go(world, **changes):
    owner = world.owner(**changes)

    async def drive():
        try:
            await owner.run()
        finally:
            cleanup = await owner.close()
        return cleanup
    cleanup = asyncio.run(drive())
    summary = owner.finish(cleanup, header={"runtime": {"shards": world.options.shards}})
    return owner, cleanup, summary


@pytest.fixture
def world(tmp_path, runtime):
    return World(tmp_path, runtime)


def test_every_unit_runs_in_one_wave_and_the_run_is_proven_stopped(world):
    owner, cleanup, summary = go(world)
    assert world.launches == [(0, ("w00", "w01"), 2)]
    assert summary["exit_code"] == EXIT_OK and summary["totals"] == {
        "done": 4, "valid": 4, "invalid_attempts": 0, "invalid_exhausted": 0, "not_run": 0, "units": 4}
    assert cleanup["terminated"] is True and cleanup["policy_service"]["confirmed"] is True and world.policy_stopped == 1
    assert sorted(world.closed) == ["wave-0-w00-g1", "wave-0-w01-g1"]
    verified = json.loads((world.run / "host" / "wave-0-verified.json").read_text())
    assert verified["kind"] == "ACT_ROLLOUT_WAVE_VERIFIED" and len(verified["units"]) == 4
    assert all(item["state"] == "COLLECTED" and len(item["evidence"]) == 5 for item in verified["units"])
    assert all(len(evidence["sha256"]) == 64 for item in verified["units"] for evidence in item["evidence"])
    assert (world.run / "host" / "containers-receipt-01-rollout.json").is_file()
    assert (world.run / "host" / "rollout-complete.json").is_file() and (world.run / "host" / "campaign-cleanup.json").is_file()
    rows = [json.loads(line) for line in (world.run / "rollout_standard" / "act-runs.jsonl").read_text().splitlines()]
    assert len(rows) == 4 and set(rows[0]) == {"search_locked", "done", "interventions", "elapsed_wall_s", "scene_id", "evidence"}
    assert rows[0]["evidence"][0].endswith("/episode/episode.json") and rows[0]["scene_id"] in ("task_start", "forward_5cm")
    assert not (world.run / "rollout_standard" / "invalid-runs.jsonl").exists()
    assert "| task_start | 2 / 2 (0) | DONE | DONE |" in (world.run / "table.md").read_text()
    assert json.loads((world.run / "summary.json").read_text())["exit_code"] == 0


def test_the_task_documents_carry_the_run_the_unit_and_the_policy_endpoint(world):
    go(world)
    document = world.documents["wave-0-w00-task_start-t1-a1"]
    assert document["kind"] == task_builder.KIND and document["run_id"] == "run-1" and document["run_identity_sha256"] == "9" * 64
    assert (document["scene_id"], document["point_id"], document["trial"], document["attempt_number"],
            document["attempt_id"]) == ("task_start-t1-a1", "task_start", 1, 1, "task_start-t1-a1")
    assert document["group"] == "rollout_standard" and document["worker_id"] == "w00" and document["launch_generation"] == 1
    assert document["policy"]["client_id"] == "w00-g1" and document["policy"]["socket_path"] == "/act/ipc/policy/policy.sock"
    assert document["execution"] == {"execution_prefix": None, "temporal_ensembling": 0.01}
    assert document["inputs"]["install_prefix"] == "/i" and document["preconditions"] == {"no_container": {"ok": True, "detail": []}}
    assert set(document) == task_builder._FIELDS
    other = world.documents["wave-0-w01-forward_5cm-t1-a1"]
    assert other["policy"]["client_id"] == "w01-g1"
    journal = json.loads((world.run / "host/wave-0/task-journal/wave-0-w00-task_start-t1-a1/assigned.json").read_text())
    assert journal["task"]["deadline_monotonic_s"] <= world.context.deadline_monotonic_s


def test_an_invalid_attempt_is_run_again_on_fresh_shards_and_counted_apart(world):
    world.script["forward_5cm-t2-a1"] = {"verdict": "INVALID", "reason": "CONTROLLER_PAIR_FAILED: goal response timeout"}
    owner, cleanup, summary = go(world)
    assert world.launches == [(0, ("w00", "w01"), 2), (1, ("w00",), 1)]       # the retry wave needs one shard
    assert summary["exit_code"] == EXIT_OK and summary["totals"]["invalid_attempts"] == 1 and summary["totals"]["done"] == 4
    cell = next(unit for unit in summary["units"] if unit["point_id"] == "forward_5cm" and unit["trial"] == 2)
    assert [attempt["verdict"] for attempt in cell["attempts"]] == ["INVALID", "DONE"] and cell["final_verdict"] == "DONE"
    assert cell["attempts"][0]["reason"].startswith("CONTROLLER_PAIR_FAILED")
    invalid = [json.loads(line) for line in (world.run / "rollout_standard" / "invalid-runs.jsonl").read_text().splitlines()]
    assert invalid[0]["attempt_id"] == "forward_5cm-t2-a1" and invalid[0]["scene_id"] == "forward_5cm"
    assert "forward_5cm-t2-a2" in world.documents["wave-1-w00-forward_5cm-t2-a2"]["attempt_id"]
    assert sorted(world.closed) == ["wave-0-w00-g1", "wave-0-w01-g1", "wave-1-w00-g2"]


def test_a_unit_that_stays_invalid_ends_without_a_result_and_the_run_exits_nonzero(world):
    world.script["task_start-t1-a1"] = {"verdict": "INVALID", "reason": "A"}
    world.script["task_start-t1-a2"] = {"verdict": "INVALID", "reason": "B"}
    owner, cleanup, summary = go(world)
    assert summary["exit_code"] == EXIT_INVALID and summary["totals"]["invalid_exhausted"] == 1
    assert summary["totals"]["valid"] == 3 and summary["totals"]["invalid_attempts"] == 2
    assert len(world.launches) == 2                                              # one retry round, no third attempt


def test_a_policy_result_that_is_not_done_is_a_result_and_is_not_run_again(world):
    world.script["task_start-t1-a1"] = {"verdict": "FAILED", "reason": "FINAL_XY_OUT_OF_TOLERANCE"}
    world.script["forward_5cm-t1-a1"] = {"verdict": "NO_MOTION", "reason": "NO_MOTION"}
    owner, cleanup, summary = go(world)
    assert summary["exit_code"] == EXIT_OK and len(world.launches) == 1
    assert summary["totals"]["done"] == 2 and summary["totals"]["valid"] == 4
    assert "FINAL_XY_OUT_OF_TOLERANCE | max arm displacement 0.750 rad" in (world.run / "table.md").read_text()


def test_a_task_that_fails_is_an_invalid_attempt_of_that_scene_and_is_run_again(world):
    world.script["task_start-t2-a1"] = {"mode": "fail"}
    owner, cleanup, summary = go(world)
    cell = next(unit for unit in summary["units"] if unit["point_id"] == "task_start" and unit["trial"] == 2)
    assert [attempt["verdict"] for attempt in cell["attempts"]] == ["INVALID", "DONE"]
    assert cell["attempts"][0]["state"] == "FAULT" and "CONTAINER_TASK_FAILED" in cell["attempts"][0]["reason"]
    assert summary["exit_code"] == EXIT_OK and summary["totals"]["done"] == 4


@pytest.mark.parametrize("behaviour,fragment", [
    ({"scene_id": "another-unit"}, "task result does not describe this unit"),
    ({"episode_verdict": "FAILED"}, "episode.json does not match the task result"),
])
def test_a_result_that_does_not_match_its_unit_or_its_episode_is_not_trusted(world, behaviour, fragment):
    world.script["task_start-t1-a1"] = behaviour
    owner, cleanup, summary = go(world)
    cell = next(unit for unit in summary["units"] if unit["point_id"] == "task_start" and unit["trial"] == 1)
    assert cell["attempts"][0]["verdict"] == "INVALID" and "ROLLOUT_RESULT_UNVERIFIED" in cell["attempts"][0]["reason"]
    assert fragment in cell["attempts"][0]["reason"]


def test_a_shard_that_does_not_start_ends_the_wave_and_the_run_with_every_container_closed(world):
    world.start_error = RuntimeError("SHARD_CONTAINER_LAUNCH_FAILED")
    owner, cleanup, summary = go(world)
    assert summary["exit_code"] == EXIT_START_FAILED and summary["totals"]["not_run"] == 4
    assert "ROLLOUT_WAVE_FAILED" in summary["fault"] and sorted(world.closed) == ["wave-0-w00-g1", "wave-0-w01-g1"]
    assert cleanup["terminated"] is True and world.policy_stopped == 1


def test_a_policy_service_that_does_not_start_launches_nothing_and_still_proves_its_stop(world):
    world.policy_error = RuntimeError("POLICY_SERVICE_READY_TIMEOUT")
    owner, cleanup, summary = go(world)
    assert summary["exit_code"] == EXIT_START_FAILED and world.launches == [] and "POLICY_SERVICE_START_FAILED" in summary["fault"]
    assert cleanup["terminated"] is True and cleanup["receipt"] is None and world.policy_stopped == 1
    assert summary["totals"]["not_run"] == 4


def test_an_unhealthy_policy_service_stops_the_dispatch_and_the_rest_is_not_run(world):
    world.policy.healthy_answers = [False]
    owner = world.owner(sleep=asyncio.sleep, monitor_interval_s=0.001)
    # the fake instances answer instantly in fake time, so hold the first status poll until the monitor has looked
    original = Instance.get_status

    async def slow(self, task_id=None):
        await asyncio.sleep(0.02)
        return await original(self, task_id)
    Instance.get_status = slow
    try:
        async def drive():
            try:
                await owner.run()
            finally:
                return await owner.close()
        cleanup = asyncio.run(drive())
    finally:
        Instance.get_status = original
    summary = owner.finish(cleanup, header={})
    assert owner.dispatch_stopped in ("ROLLOUT_POLICY_SERVICE_UNHEALTHY", "ROLLOUT_CLOSING")
    assert summary["exit_code"] != EXIT_OK


def test_a_shard_whose_stop_is_not_proven_stops_the_run_unconfirmed(world):
    world.close_ok = False
    owner, cleanup, summary = go(world)
    assert summary["exit_code"] == EXIT_STOP_UNCONFIRMED and cleanup["terminated"] is False
    assert "ROLLOUT_SHARD_STOP_UNCONFIRMED" in summary["fault"]
    assert not (world.run / "host" / "containers-receipt-01-rollout.json").exists()      # nothing removed that is not proven


def test_a_policy_service_stop_that_is_not_confirmed_is_an_unconfirmed_run(world):
    world.policy_stop_ok = False
    owner, cleanup, summary = go(world)
    assert summary["exit_code"] == EXIT_STOP_UNCONFIRMED and summary["totals"]["done"] == 4


def test_the_recording_cap_limits_the_episodes_running_at_once(tmp_path, runtime):
    (tmp_path / "capped").mkdir()
    capped = World(tmp_path / "capped", runtime, shards=2, trials=3, cap=1)
    go(capped)
    assert capped.max_running == 1
    (tmp_path / "free").mkdir()
    free = World(tmp_path / "free", runtime, shards=2, trials=3)
    go(free)
    assert free.max_running == 2


def test_the_campaign_deadline_stops_the_dispatch(world):
    owner = world.owner(context=replace(world.context, deadline_monotonic_s=world.clock.now - 500))
    cleanup = asyncio.run(_drive(owner))
    summary = owner.finish(cleanup, header={})
    assert world.launches == [] and summary["totals"]["not_run"] == 4 and summary["exit_code"] == EXIT_INVALID


async def _drive(owner):
    try:
        await owner.run()
    finally:
        return await owner.close()


def test_an_interrupted_run_still_closes_every_shard_and_stops_the_policy_service(world):
    owner = world.owner()

    async def interrupted():
        task = asyncio.create_task(owner.run())
        for _ in range(2000):
            if world.launches and world.running:
                break
            await asyncio.sleep(0.001)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return await owner.close()
    cleanup = asyncio.run(interrupted())
    assert world.launches and cleanup["terminated"] is True and world.policy_stopped == 1
    assert sorted(world.closed) == ["wave-0-w00-g1", "wave-0-w01-g1"]
    summary = owner.finish(cleanup, header={})
    assert summary["exit_code"] == EXIT_INVALID and summary["totals"]["not_run"] > 0
