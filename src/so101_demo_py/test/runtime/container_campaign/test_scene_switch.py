"""The shard's stack follows the scene of its task (indoor P3, T1).

Real: the appearance plan, the variant realization and its stripped physics fingerprint (MuJoCo compiles the real indoor scene), the stack
owner with its stop and receipt. Controlled doubles: the stack process (a sleeping Python), its probes, the compile hash of the nominal scene."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from paths import PACKAGE_ROOT
from so101_demo.act import appearance_plan as ap
from so101_demo.act import model_equivalence
from so101_demo.act import scene_variant_run
from so101_demo.runtime.container_campaign import scene_switch as module
from so101_teleop.owned_group import terminate_group
from so101_teleop.unified.act_stack import ActStackLaunch, ActStackProcessOwner

NOMINAL_MODEL = "ab" * 32
SEED = 710025
SHARE = PACKAGE_ROOT


@pytest.fixture(autouse=True, scope="module")
def _pool_share(indoor_pool_share):
    """The switch verifies the installed texture files (`verify_files=True`), so it runs on a share in which they exist and match."""
    global SHARE
    SHARE = indoor_pool_share
    yield


class SleepingLaunch(ActStackLaunch):
    def argv(self):
        return [sys.executable, "-c", "import time; time.sleep(120)"]


def inventory():
    return ap.scene_inventory(SHARE / "assets/mujoco/act")


def plan():
    return ap.make_plan(seed=SEED, nominal_share=0.25, nominal_scene_sha256=inventory()["scene_sha256"], pool_identity=inventory()["pool_identity"])


def appearance(scene_id):
    return ap.derive(plan(), scene_id, inventory())


def scenes(kind, count):
    found = []
    for index in range(200):
        scene = f"sw-{index:03d}"
        if appearance(scene)["kind"] == kind:
            found.append(scene)
        if len(found) == count:
            return found
    raise AssertionError(kind)


class Env:
    def __init__(self, tmp_path):
        self.root = tmp_path / "owned"
        (self.root / "stack").mkdir(parents=True)
        self.launch = SleepingLaunch(ros2_executable=Path(sys.executable), session_id="act-switch-1", evidence_root=self.root / "stack",
                                     ros_domain_id=179, environment=dict(os.environ))
        self.stack = ActStackProcessOwner(self.launch, ready_probe=lambda: True, stop_probe=lambda: True, graph_clear_probe=lambda: True)
        self.probes = []
        self.compiled = []

        def model_sha256(path):
            self.compiled.append(Path(path).name)
            return NOMINAL_MODEL if Path(path).name == "scene_side_wrist_indoor.xml" else "cd" * 32

        def new_probe(launch):
            probe = lambda: True      # noqa: E731
            probe.readiness_bytes = b'{"ready":true}\n'
            self.probes.append(launch)
            return probe

        self.switch = module.StackSceneSwitch(stack=self.stack, owned_root=self.root, share=SHARE, new_ready_probe=new_probe,
                                              start_timeout_s=10, stop_timeout_s=2, model_sha256=model_sha256)

    async def start(self):
        await self.stack.start(timeout_s=5)

    def stop(self):
        if self.stack.owner is not None:
            terminate_group(pgid=self.stack.owner.pgid, leader_pid=self.stack.owner.pid, timeout_s=0.5)


@pytest.fixture
def env(tmp_path, monkeypatch):
    for name in (model_equivalence.ENV_PATH, model_equivalence.ENV_SHA256):
        monkeypatch.delenv(name, raising=False)
    item = Env(tmp_path)
    asyncio.run(item.start())
    yield item
    item.stop()


def go(env, scene):
    return env.switch.switch(appearance(scene), scene, expected_model_sha256=NOMINAL_MODEL)


def test_a_nominal_task_on_the_nominal_stack_switches_nothing(env):
    owner = env.stack.owner
    record = go(env, scenes(ap.KIND_NOMINAL, 1)[0])
    assert record["switched"] is False and env.stack.owner is owner and env.switch.switches == 0
    assert not (env.root / module.SWITCH_DIRECTORY).exists() and env.stack.launch.mujoco_scene is None


def test_a_randomised_task_stops_the_stack_and_starts_it_with_its_variant_and_the_declared_nominal_identity(env):
    scene = scenes(ap.KIND_RANDOMISED, 1)[0]
    before = env.stack.owner
    record = go(env, scene)
    realized = env.root / "scene-variant" / scene / "scene_variant.xml"
    assert record["switched"] is True and record["switch_index"] == 1 and realized.is_file()
    assert env.stack.launch.mujoco_scene == realized and env.stack.launch.declared_model_sha256 == NOMINAL_MODEL
    # D1: the substitution is proved before the stack starts: both hashes and the proof's hash, the proof bound to this process
    proof = record["equivalence_proof"]
    assert env.stack.launch.equivalence_proof_sha256 == proof["sha256"] and proof["loaded_model_sha256"] == "cd" * 32
    bound = model_equivalence.bound()
    assert bound["sha256"] == proof["sha256"] and (bound["declared"], bound["loaded"]) == (NOMINAL_MODEL, "cd" * 32)
    document = json.loads(Path(proof["path"]).read_text())
    assert document["scene_id"] == scene and document["fingerprint_version"] == 2
    assert document["nominal_physics_fingerprint"] == document["variant_physics_fingerprint"] and document["realized_sha256"] == record["to_realized_sha256"]
    assert env.stack.owner is not None and env.stack.owner.pid != before.pid and record["stopped_owner_pid"] == before.pid
    assert record["declared_model_sha256"] == NOMINAL_MODEL
    assert record["to_realized_sha256"] and record["from_realized_sha256"] is None
    assert env.probes[-1] is env.stack.launch and record["readiness_sha256"] != ""
    assert record["stop_s"] >= 0 and record["start_s"] >= 0 and record["total_s"] >= record["stop_s"]
    # the stack's own receipt of the first stop is kept under its own name, so the shard's final stop can write its receipt
    assert not (env.root / "stack" / "cleanup-receipt.json").exists()
    archived = json.loads((env.root / "stack" / "cleanup-receipt-1.json").read_text())
    assert archived["leader_pid"] == before.pid and record["stop_receipt"] == "cleanup-receipt-1.json"
    written = json.loads((env.root / module.SWITCH_DIRECTORY / f"001-{scene}.json").read_text())
    assert written == record
    assert "scene_side_wrist_indoor.xml" in env.compiled


def test_the_same_appearance_twice_switches_once_and_another_one_switches_again_and_back_to_nominal(env):
    first, second = scenes(ap.KIND_RANDOMISED, 2)
    nominal = scenes(ap.KIND_NOMINAL, 1)[0]
    assert go(env, first)["switched"] is True
    again = env.switch.switch(appearance(first), "sw-same-draw", expected_model_sha256=NOMINAL_MODEL)
    assert again["switched"] is False and env.switch.switches == 1
    assert go(env, second)["switch_index"] == 2
    assert (env.root / "stack" / "cleanup-receipt-2.json").is_file()
    back = go(env, nominal)
    assert back["switched"] is True and back["to_realized_sha256"] is None and back["declared_model_sha256"] is None
    assert env.stack.launch.mujoco_scene is None and env.stack.launch.declared_model_sha256 is None
    assert env.stack.launch.equivalence_proof_sha256 is None and back["equivalence_proof"] is None and model_equivalence.bound() is None
    # the shard's own final stop finds its receipt where it always is, whatever number of switches came before
    asyncio.run(env.stack.stop(timeout_s=2))
    assert json.loads((env.root / "stack" / "cleanup-receipt.json").read_text())["graph_clear"] is True
    assert sorted(path.name for path in (env.root / "stack").iterdir()) == [
        "cleanup-receipt-1.json", "cleanup-receipt-2.json", "cleanup-receipt-3.json", "cleanup-receipt.json"]


def test_a_nominal_scene_that_does_not_compile_to_the_frozen_identity_leaves_the_stack_as_it_was(env):
    scene = scenes(ap.KIND_RANDOMISED, 1)[0]
    owner = env.stack.owner
    with pytest.raises(module.SceneSwitchRefused, match="SCENE_SWITCH_NOMINAL_MODEL_MISMATCH"):
        env.switch.switch(appearance(scene), scene, expected_model_sha256="ef" * 32)
    assert env.stack.owner is owner and env.stack.process.poll() is None and env.switch.switches == 0
    assert not (env.root / module.PROOF_DIRECTORY).exists() and model_equivalence.bound() is None


def test_a_variant_whose_physics_differ_from_the_nominal_is_refused_and_leaves_nothing_behind(env, monkeypatch):
    scene = scenes(ap.KIND_RANDOMISED, 1)[0]
    owner = env.stack.owner
    monkeypatch.setattr(scene_variant_run, "stripped_physics_fingerprint_of_file", lambda path: str(path))
    with pytest.raises(module.SceneSwitchRefused, match="SCENE_SWITCH_VARIANT_REFUSED"):
        go(env, scene)
    assert env.stack.owner is owner and not (env.root / "scene-variant" / scene / "scene_variant.xml").exists()


def test_a_variant_that_is_not_the_one_the_row_names_is_refused(env):
    scene = scenes(ap.KIND_RANDOMISED, 1)[0]
    row = dict(appearance(scene), variant_sha256="0" * 64)
    with pytest.raises(module.SceneSwitchRefused, match="SCENE_SWITCH_VARIANT_HASH_MISMATCH"):
        env.switch.switch(row, scene, expected_model_sha256=NOMINAL_MODEL)


def test_a_stack_that_is_not_running_cannot_be_switched(env):
    scene = scenes(ap.KIND_RANDOMISED, 1)[0]
    asyncio.run(env.stack.stop(timeout_s=2))
    with pytest.raises(module.SceneSwitchRefused, match="SCENE_SWITCH_STACK_NOT_RUNNING"):
        go(env, scene)


def test_the_task_record_names_the_draw_the_source_and_the_switch(env):
    scene = scenes(ap.KIND_RANDOMISED, 1)[0]
    record = go(env, scene)
    entry = {"plan": plan(), "appearance": appearance(scene), "teacher_source": ap.teacher_source_for(ap.KIND_RANDOMISED)}
    path = env.switch.record_task("wave-0-w00-" + scene, entry, record)
    document = json.loads(path.read_text())
    assert document["teacher_source"] == "privileged_pose" and document["draw_sha256"] == appearance(scene)["draw_sha256"]
    assert document["switch"] == record and document["plan_sha256"] == plan()["plan_sha256"]
    with pytest.raises(FileExistsError):
        env.switch.record_task("wave-0-w00-" + scene, entry, record)


def test_the_switch_needs_a_positive_start_timeout_and_a_probe_factory(env):
    with pytest.raises(ValueError, match="SCENE_SWITCH_CONFIG_INVALID"):
        module.StackSceneSwitch(stack=env.stack, owned_root=env.root, share=SHARE, new_ready_probe=None, start_timeout_s=10)
    with pytest.raises(ValueError, match="SCENE_SWITCH_CONFIG_INVALID"):
        module.StackSceneSwitch(stack=env.stack, owned_root=env.root, share=SHARE, new_ready_probe=lambda launch: None, start_timeout_s=0)
