"""One rollout episode as a shard task: validation, binding to the run identity, the episode files and the shutdown proof.

Real: the closed task document, `load_rollout_task`, `bind_inputs`, the real `run_episode` state machine over the episode test's fake
ports, `EpisodeFiles`, `episode_document`, `reserve_task_output`. Controlled doubles: the frozen inputs loader, the policy client, the
ROS ports and the borrowed stack. No container, ROS, simulator, model or GPU is involved.
"""

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.act.rig_profile import DEFAULT_RIG
from so101_demo.act.rollout_shared import EpisodeFiles, RolloutInputs, episode_document
from so101_demo.runtime.act_instance.identity import INSTANCE_ROOT_ENV, SIMULATION_SESSION_ENV
from so101_demo.runtime.act_rollout import task_builder
from so101_demo.runtime.act_rollout.task_builder import RolloutEdges, build_rollout_task, identity_sha256
from so101_demo.runtime.container_campaign.task_contracts import InputRef, TaskSpec

from test_act_rollout_episode import SCENE, SETTINGS, Ports, _endpoint_policy
from test_act_rollout_targets import SNAPSHOT_TARGETS

BUNDLE, POLICY, SCENES = "b" * 64, "c" * 64, "d" * 64
SESSION = "act-test-w00-g1"
GENERATION = "gen-1"
IDENTITY = {"bundle_sha256": BUNDLE, "policy_sha256": POLICY, "scenes_sha256": SCENES, "inputs_manifest_sha256": "e" * 64,
            "gate_install": "/mounted/install/so101_demo_py", "source_commit": "f" * 40}
OBSERVATION = {"cameras": ("head", "wrist"), "state_dim": 8, "image_shape": [4, 6, 3], "source": "bundle"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ref(path):
    return {"path": str(path), "sha256": sha(path)}


class World:
    def __init__(self, tmp_path, monkeypatch):
        self.tmp = tmp_path
        self.root = tmp_path / "run" / "wave-0" / "w00" / "g1"
        for name in ("tmp", "control", "output", "task-inputs", "stack"):
            (self.root / name).mkdir(parents=True)
        self.socket = Path("/act/ipc/policy/policy.sock")
        self.install = Path("/mounted/install/so101_demo_py")
        files = tmp_path / "inputs"
        files.mkdir()
        bundle_dir = files / "bundle"
        bundle_dir.mkdir()
        for name in ("manifest.json", "runtime.yaml", "rollout.yaml", "scenes.json"):
            (files / name).write_text(name)
        (bundle_dir / "bundle.json").write_text("{}")
        self.bundle_dir = bundle_dir
        self.refs = {"inputs_manifest": ref(files / "manifest.json"), "runtime_config": ref(files / "runtime.yaml"),
                     "rollout_config": ref(files / "rollout.yaml"), "scenes": ref(files / "scenes.json"),
                     "bundle_json": ref(bundle_dir / "bundle.json")}
        self.policy_bundle_sha = self.refs["bundle_json"]["sha256"]
        self.identity = dict(IDENTITY, bundle_sha256=self.policy_bundle_sha)
        self.spec = {"workload_kind": "act_rollout", "campaign_id": "campaign", "worker_id": "w00", "launch_generation": 1,
                     "wave_id": "wave-0", "owned_root": str(self.root), "simulation_session_id": SESSION,
                     "gpu_uuid": "GPU-00000000-0000-0000-0000-000000000000", "deadline_monotonic_s": time.monotonic() + 1e6,
                     "rollout_identity": {"run_identity_sha256": identity_sha256(self.identity), "scenes_sha256": SCENES,
                                          "policy_sha256": POLICY, "bundle_sha256": self.policy_bundle_sha}}
        self.stack = SimpleNamespace(launch=SimpleNamespace(ros_domain_id=181, session_id=SESSION,
                                                            evidence_root=self.root / "stack", rig=DEFAULT_RIG.rig,
                                                            rig_profile=None), process=None)
        monkeypatch.setenv("ROS_DOMAIN_ID", "181")
        monkeypatch.setenv("MUJOCO_GL", "egl")
        monkeypatch.setenv("ROS_LOCALHOST_ONLY", "1")
        monkeypatch.setenv("ROS_AUTOMATIC_DISCOVERY_RANGE", "LOCALHOST")
        monkeypatch.delenv("ROS_NAMESPACE", raising=False)
        monkeypatch.setenv(SIMULATION_SESSION_ENV, SESSION)
        monkeypatch.setenv(INSTANCE_ROOT_ENV, str(self.root))
        self.ports = Ports()
        self.closed = []
        self.cancelled = []

    def document(self, **changes):
        document = {"schema_version": 1, "kind": task_builder.KIND, "task_id": "wave-0-w00-unit-1", "worker_id": "w00",
                    "launch_generation": 1, "wave_id": "wave-0", "scene_id": "unit-1", "point_id": SCENE["scene_id"],
                    "group": "rollout_standard", "trial": 1, "attempt_number": 1, "attempt_id": "unit-1-a1",
                    "run_id": "run-1", "run_identity_sha256": identity_sha256(self.identity),
                    "inputs": dict(self.refs, bundle_dir=str(self.bundle_dir), install_prefix=str(self.install)),
                    "execution": {"execution_prefix": None, "temporal_ensembling": None},
                    "policy": {"socket_path": str(self.socket), "service_generation": GENERATION, "client_id": "w00-g1",
                               "max_frame_bytes": 1 << 22, "bundle_sha256": self.policy_bundle_sha, "policy_sha256": POLICY},
                    "preconditions": {"no_container": {"ok": True, "detail": []}}}
        document.update(changes)
        return document

    def task(self, document=None, **changes):
        document = self.document() if document is None else document
        path = self.root / "task-inputs" / (document["task_id"] + ".json")
        path.write_text(json.dumps(document))
        spec = TaskSpec(task_id=document["task_id"], inputs_ref=InputRef(path=str(path), sha256=sha(path)),
                        deadline_monotonic_s=time.monotonic() + 1000)
        return spec.model_copy(update=changes) if changes else spec

    def inputs(self, args):
        return RolloutInputs(
            settings=SETTINGS, snapshot_targets=SNAPSHOT_TARGETS, endpoint_policy=_endpoint_policy(), timing={},
            rollout_config={}, observation=dict(OBSERVATION), substitution={"substituted_by": "receipt"},
            scenes={"groups": {"rollout_standard": [SCENE]}, "manifest_sha256": SCENES}, identity=dict(self.identity),
            runtime_config={"inference": {"device": "cuda", "request_timeout_s": 0.5, "max_reply_age_s": 0.3}},
            recorder_policy={"ready_timeout_s": 1.0})

    def edges(self, **changes):
        world = self

        class Client:
            def query(self, kind, **_):
                return world.ready

        self.ready = {"ready": True, "bundle_sha256": self.policy_bundle_sha, "policy_sha256": POLICY,
                      "cameras": ["head", "wrist"], "state_dim": 8, "image_shape": [4, 6, 3]}

        def ports_factory(**kwargs):
            world.factory_kwargs = kwargs
            runtime = SimpleNamespace(cancel_motion=lambda lease: world.cancelled.append(lease),
                                      close_runtime=lambda: world.closed.append("runtime"))
            inference = SimpleNamespace(close=lambda: world.closed.append("inference"))
            binding = SimpleNamespace(shutdown=lambda: world.closed.append("binding"))
            return SimpleNamespace(ports=world.ports, inference=inference, transport=None, runtime=runtime, binding=binding,
                                   lease="lease-1")

        values = dict(inputs_loader=self.inputs, client_factory=lambda policy, inputs: Client(), ports_factory=ports_factory)
        values.update(changes)
        return RolloutEdges(**values)

    def build(self, task=None, **changes):
        edges = changes.pop("edges", None) or self.edges()
        return build_rollout_task(task or self.task(), stack=changes.pop("stack", self.stack), shard_spec=changes.pop("spec", self.spec),
                                  output_root=self.root / "output", policy_socket=self.socket, install_prefix=self.install,
                                  edges=edges, recovery_timeout_s=changes.pop("recovery_timeout_s", 2.0), **changes)


@pytest.fixture
def world(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch)


def episode_dir(world, task_id="wave-0-w00-unit-1"):
    return world.root / "output" / "tasks" / task_id / "episode"


def test_a_valid_task_runs_one_episode_and_leaves_the_native_episode_files(world):
    execution = world.build()
    assert (world.root / "output" / "tasks" / "wave-0-w00-unit-1").is_dir()
    result = execution.run()
    assert result["kind"] == task_builder.RESULT_KIND and result["verdict"] == "DONE" and result["done"] is True
    assert (result["scene_id"], result["point_id"], result["trial"], result["attempt_id"]) == (
        "unit-1", SCENE["scene_id"], 1, "unit-1-a1")
    names = {path.name for path in episode_dir(world).iterdir()}
    assert names == {"episode.json", "steps.jsonl", "world.jsonl", "events.jsonl", "endpoint.json", "stop-proof.json"}
    assert result["evidence"] == [f"episode/{name}" for name in
                                  ("episode.json", "endpoint.json", "steps.jsonl", "world.jsonl", "stop-proof.json")]
    document = json.loads((episode_dir(world) / "episode.json").read_text())
    assert document["kind"] == "ACT_ROLLOUT_EPISODE" and document["run_id"] == "run-1" and document["attempt_id"] == "unit-1-a1"
    assert document["verdict"] == "DONE" and document["preconditions"] == {"no_container": {"ok": True, "detail": []}}
    assert json.dumps(result)           # the journal stores it


def shape(value):
    """The structure of a document: keys, nested keys, and the type of every leaf."""
    if isinstance(value, dict):
        return {key: shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [shape(item) for item in value[:1]]
    return type(value).__name__


def test_the_episode_is_schema_identical_to_one_the_native_loop_writes(world, tmp_path):
    shard = world.build()
    shard.run()
    # what `act_rollout_native._run_scenes` does for one attempt, over the same fake ports and the very same functions
    native_ports = Ports()
    files = EpisodeFiles(tmp_path / "native-episode")
    from so101_demo.act.rollout_episode import run_episode
    result = run_episode(scene=SCENE, attempt_id="unit-1-a1", ports=native_ports, settings=SETTINGS,
                         snapshot_targets=SNAPSHOT_TARGETS, endpoint_policy=_endpoint_policy(), sink=files, execution=None)
    options = SimpleNamespace(run_id="run-1")
    names = files.seal(episode_document(inputs=world.inputs(None), options=options, scene=SCENE, attempt_id="unit-1-a1",
                                        result=result, preconditions={"no_container": {"ok": True, "detail": []}}), result)
    shard_files = {path.name for path in episode_dir(world).iterdir()}
    assert shard_files == {path.name for path in (tmp_path / "native-episode").iterdir()}
    assert set(names) <= shard_files
    for name in ("episode.json", "endpoint.json", "stop-proof.json"):
        mine = json.loads((episode_dir(world) / name).read_text())
        native = json.loads((tmp_path / "native-episode" / name).read_text())
        if name == "episode.json":
            # the shard episode additionally names its goal response summary only when the session reports one: absent here
            assert shape(mine) == shape(native)
        else:
            assert shape(mine) == shape(native)
    for name in ("steps.jsonl", "world.jsonl", "events.jsonl"):
        mine = (episode_dir(world) / name).read_text().splitlines()
        native = (tmp_path / "native-episode" / name).read_text().splitlines()
        assert len(mine) == len(native) and [shape(json.loads(row)) for row in mine] == [shape(json.loads(row)) for row in native]


def test_an_invalid_episode_is_a_result_not_a_fault(world):
    world.ports = Ports(gate_error=RuntimeError("gate says no"))
    result = world.build().run()
    assert result["verdict"] == "INVALID" and result["done"] is False and result["reason"].startswith("GATE_FAILED")
    assert (episode_dir(world) / "episode.json").is_file()


def test_an_episode_runner_that_raises_is_sealed_as_an_invalid_attempt(world):
    def broken(**_):
        raise RuntimeError("runner exploded")
    result = world.build(edges=world.edges(episode_runner=broken)).run()
    assert result["verdict"] == "INVALID" and "EPISODE_RUNNER_FAULT" in result["reason"]
    assert json.loads((episode_dir(world) / "episode.json").read_text())["verdict"] == "INVALID"


@pytest.mark.parametrize("mutate,code", [
    (lambda d: d.update(worker_id="w01"), "ROLLOUT_TASK_CONTEXT_MISMATCH"),
    (lambda d: d.update(wave_id="wave-9"), "ROLLOUT_TASK_CONTEXT_MISMATCH"),
    (lambda d: d.update(extra=1), "ROLLOUT_TASK_INPUT_INVALID"),
    (lambda d: d.update(group="rollout_unknown"), "ROLLOUT_TASK_INPUT_INVALID"),
    (lambda d: d.update(trial=0), "ROLLOUT_TASK_INPUT_INVALID"),
    (lambda d: d.update(attempt_id="bad id"), "ROLLOUT_TASK_INPUT_INVALID"),
    (lambda d: d["inputs"].pop("scenes"), "ROLLOUT_TASK_INPUT_INVALID"),
    (lambda d: d["inputs"].update(install_prefix="/elsewhere"), "ROLLOUT_TASK_INPUT_INVALID"),
    (lambda d: d["policy"].update(socket_path="/tmp/other.sock"), "ROLLOUT_POLICY_ENDPOINT_INVALID"),
    (lambda d: d["policy"].update(policy_sha256="0" * 64), "ROLLOUT_POLICY_ENDPOINT_INVALID"),
    (lambda d: d.update(run_identity_sha256="0" * 64), "ROLLOUT_TASK_IDENTITY_MISMATCH"),
    (lambda d: d.update(point_id="no-such-point"), "ROLLOUT_TASK_SCENE_UNKNOWN"),
])
def test_a_task_that_does_not_fit_the_shard_or_the_run_is_refused_before_anything_is_created(world, mutate, code):
    document = world.document()
    mutate(document)
    with pytest.raises(ValueError, match=code):
        world.build(task=world.task(document))
    assert not (world.root / "output" / "tasks").exists() or not any((world.root / "output" / "tasks").iterdir())


def test_a_changed_input_file_is_refused(world):
    document = world.document()
    (world.bundle_dir / "bundle.json").write_text("changed")
    with pytest.raises(ValueError):
        world.build(task=world.task(document))


def test_a_task_input_in_the_wrong_place_or_past_the_deadline_is_refused(world):
    task = world.task()
    with pytest.raises(ValueError, match="ROLLOUT_TASK_INPUT_LOCATION_INVALID"):
        world.build(task=task.model_copy(update={"inputs_ref": InputRef(path=str(world.tmp / "x.json"), sha256="a" * 64)}))
    with pytest.raises(ValueError, match="ROLLOUT_TASK_DEADLINE_INVALID"):
        world.build(task=world.task(deadline_monotonic_s=1.0))
    expired = dict(world.spec, deadline_monotonic_s=1.0)
    with pytest.raises(ValueError, match="ROLLOUT_TASK_DEADLINE_INVALID"):
        world.build(spec=expired)


def test_an_environment_that_drifted_from_the_instance_identity_is_refused(world, monkeypatch):
    monkeypatch.setenv("ROS_DOMAIN_ID", "7")
    with pytest.raises(ValueError, match="ROLLOUT_TASK_ENVIRONMENT_DRIFT"):
        world.build()


def test_the_borrowed_stack_must_be_this_shards_stack_and_alive(world):
    other = SimpleNamespace(launch=SimpleNamespace(ros_domain_id=181, session_id="another", evidence_root=world.root / "stack",
                                                   rig=DEFAULT_RIG.rig, rig_profile=None), process=None)
    with pytest.raises(ValueError, match="ROLLOUT_BORROWED_STACK_MISMATCH"):
        world.build(stack=other)
    dead = SimpleNamespace(launch=world.stack.launch, process=SimpleNamespace(poll=lambda: 1))
    with pytest.raises(ValueError, match="ROLLOUT_STACK_NOT_RUNNING"):
        world.build(stack=dead)


def test_a_policy_service_that_is_not_the_one_the_task_names_is_refused(world):
    edges = world.edges()
    world.ready["bundle_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="ROLLOUT_POLICY_SERVICE_MISMATCH"):
        world.build(edges=edges)
    world.ready.update(bundle_sha256=world.policy_bundle_sha, cameras=["side", "wrist"])
    with pytest.raises(ValueError, match="ROLLOUT_POLICY_SERVICE_MISMATCH"):
        world.build(task=world.task(world.document(task_id="wave-0-w00-unit-2", scene_id="unit-2", attempt_id="unit-2-a1")),
                    edges=edges)
    world.ready.update(cameras=["head", "wrist"], ready=False)
    with pytest.raises(ValueError, match="ROLLOUT_POLICY_SERVICE_MISMATCH"):
        world.build(task=world.task(world.document(task_id="wave-0-w00-unit-3", scene_id="unit-3", attempt_id="unit-3-a1")),
                    edges=edges)


def test_a_task_directory_is_reserved_once(world):
    world.build()
    with pytest.raises(ValueError, match="TASK_OUTPUT_ALREADY_EXISTS_OR_INVALID"):
        world.build()


def test_the_run_method_runs_once(world):
    execution = world.build()
    execution.run()
    with pytest.raises(RuntimeError, match="ROLLOUT_TASK_RUN_ALREADY_STARTED"):
        execution.run()


def test_shutdown_closes_every_owned_participant_and_proves_it(world):
    execution = world.build()
    execution.run()
    assert execution.shutdown_owned() is True
    assert world.closed == ["inference", "runtime", "binding"]
    assert execution.retire_proofs == {"episode_ended": True, "inference_closed": True, "runtime_closed": True,
                                       "binding_closed": True, "episode_retired": True}
    assert execution.shutdown_owned() is True and world.closed == ["inference", "runtime", "binding"]    # single flight


def test_shutdown_before_the_run_has_nothing_to_wait_for(world):
    execution = world.build()
    assert execution.shutdown_owned() is True


def test_shutdown_is_not_proven_while_the_episode_is_still_running(world):
    gate = threading.Event()

    def slow(**kwargs):
        gate.wait(5)
        raise RuntimeError("late")
    execution = world.build(edges=world.edges(episode_runner=slow), recovery_timeout_s=0.05)
    thread = threading.Thread(target=execution.run)
    thread.start()
    time.sleep(0.05)
    assert execution.shutdown_owned() is False and world.closed == []
    gate.set()
    thread.join(5)


def test_a_failed_close_is_reported_not_raised(world):
    execution = world.build()
    execution.run()
    execution.runtime.close_runtime = lambda: (_ for _ in ()).throw(RuntimeError("ros gone"))
    assert execution.shutdown_owned() is False
    assert execution.retire_proofs["runtime_closed"] is False


def test_request_stop_cancels_the_controllers_and_never_raises(world):
    execution = world.build()
    execution.request_stop()
    assert world.cancelled == ["lease-1"]
    execution.runtime.cancel_motion = lambda lease: (_ for _ in ()).throw(RuntimeError("no ros"))
    execution.request_stop()
    with pytest.raises(RuntimeError, match="ROLLOUT_TASK_STOP_REQUESTED"):
        execution.run()


def test_the_resources_keep_task_data_in_the_task_directory_and_the_rest_under_the_owned_root(world):
    task_dir = world.root / "output" / "tasks" / "t"
    resources = task_builder.rollout_resources(world.spec, task_root=task_dir)
    assert resources.worker_root == task_dir and resources.ros_domain_id == 181 and resources.controller_namespace == "/"
    assert resources.session_id == SESSION and resources.socket_namespace == world.root / "control"
    assert resources.ros_log_dir == world.root / "ros-logs" and resources.temp_dir == world.root / "tmp"
    assert resources.environment["ROS_DOMAIN_ID"] == "181" and "SO101_ACT_INSTANCE_ROOT" in resources.environment
    assert os.environ.get(INSTANCE_ROOT_ENV) == str(world.root)


class FakePilot:
    """The recorder as the episode sees it: its own directory holds the process manifest and `raw/`."""

    def __init__(self, directory):
        self.directory, self.root, self.ready, self.failure = Path(directory), Path(directory) / "raw", False, None

    def start(self):
        self.root.mkdir(parents=True)
        (self.directory / "owned-runtime-processes.json").write_text("{}")
        (self.root / "bag-probe-trace.jsonl").write_text("{}\n")
        (self.root / "ready.json").write_text("{}")
        self.ready = True

    def finish(self):
        return {"ready": True, "failure": None}


class FakeBinding:
    def shutdown(self):
        pass


class FakeRuntime:
    instances = []

    def __init__(self, resources, **keywords):
        self.resources, self.keywords = resources, keywords
        FakeRuntime.instances.append(self)

    def close_runtime(self):
        pass


def listing(root):
    return sorted(str(path.relative_to(root)) for path in Path(root).rglob("*") if path.is_file())


@pytest.fixture
def fake_ros(monkeypatch):
    import so101_demo.adapters.act.rollout_ros as rollout_ros
    import so101_demo.runtime.act_ros_runtime as ros_runtime

    FakeRuntime.instances = []
    monkeypatch.setattr(rollout_ros, "RclpyBinding", FakeBinding)
    monkeypatch.setattr(ros_runtime, "ActRosRuntimePorts", FakeRuntime)
    monkeypatch.setattr(task_builder, "make_policy_runner", lambda inputs, policy: SimpleNamespace(policy=policy))
    monkeypatch.setattr(task_builder, "pilot_factory_for", lambda **keywords: FakePilot)
    return FakeRuntime


def real_parts(world, fake_ros, monkeypatch):
    document = world.document()
    inputs = world.inputs(None)
    scene = dict(SCENE)
    task_dir = world.root / "output" / "tasks" / "wave-0-w00-unit-1"
    task_dir.mkdir(parents=True)
    files = EpisodeFiles(task_dir / "episode")
    client = SimpleNamespace(query=lambda *a, **k: None, infer=lambda *a, **k: None)
    parts = task_builder.real_ports(shard_spec=world.spec, document=document, inputs=inputs, scene=scene, stack=world.stack,
                                    task_dir=task_dir, files=files, policy_client=client, clock=time.monotonic)
    return parts, task_dir, files, scene, document, inputs


def test_the_real_ports_are_built_over_the_shard_runtime_the_socket_transport_and_the_native_episode_ports(world, fake_ros, monkeypatch):
    parts, task_dir, files, scene, document, inputs = real_parts(world, fake_ros, monkeypatch)
    try:
        (runtime,) = fake_ros.instances
        assert parts.runtime is runtime and runtime.resources.worker_root == task_dir
        assert runtime.resources.session_id == SESSION and runtime.resources.ros_domain_id == 181
        assert runtime.keywords["catalog"] == {scene["scene_id"]: {"cup_position_world_m": scene["cup_position_world_m"]}}
        assert runtime.keywords["config"] is None and runtime.keywords["mode"].name == "EXECUTE"
        assert runtime.keywords["broker_generation"] == 1
        assert runtime.keywords["dependencies"]["act_profile"] is True and runtime.keywords["dependencies"]["rig"].rig == DEFAULT_RIG.rig
        lease = parts.lease
        assert (lease.worker_id, lease.worker_generation, lease.point_id, lease.attempt_id, lease.lease_generation) == (
            "w00", 1, scene["scene_id"], "unit-1-a1", 1)
        assert lease.batch_id == "campaign-wave-0"
        assert lease.lease_deadline_monotonic_s - lease.lease_issued_monotonic_s == pytest.approx(
            inputs.settings.execution_deadline_s + 600.0)
        # the policy sits behind the unchanged boundary, over the socket transport, with the reply window of the frozen config
        assert parts.inference.transport is parts.transport and parts.transport.reply_window_s == 0.3
        assert parts.transport.request_timeout_s == 0.5
        ports = parts.ports
        assert ports.runtime is runtime and ports.lease is lease and ports.directory == files.directory
        assert ports.recording_dir == task_dir / "recordings" / "unit-1-a1"
        assert ports.binding is parts.binding and ports.scene == scene
        assert ports.runner.policy.__class__.__name__ == "RemotePolicy"
    finally:
        parts.transport.close()


def test_a_borrowed_stack_of_another_rig_than_the_bundles_is_refused(world, fake_ros, monkeypatch):
    world.stack.launch.rig = "side_wrist"
    with pytest.raises(ValueError, match="ROLLOUT_BORROWED_STACK_RIG_MISMATCH"):
        real_parts(world, fake_ros, monkeypatch)


def test_the_shard_episode_directory_holds_exactly_what_a_native_one_does(world, fake_ros, monkeypatch, tmp_path):
    from so101_demo.act.rollout_shared import NativeEpisodePorts

    parts, task_dir, files, scene, document, inputs = real_parts(world, fake_ros, monkeypatch)
    parts.transport.close()
    shard_pilot = parts.ports.start_recorder(scene)
    shard_pilot.finish()
    # what the native composition does for the same attempt: the recorder beside the episode, the raw directory moved in
    native_directory = tmp_path / "native" / "episodes" / "unit-1-a1"
    EpisodeFiles(native_directory)                           # the row files a native episode starts with
    native = NativeEpisodePorts(runtime=None, lease=None, scene=scene, directory=native_directory, inputs=inputs, environment={},
                                binding=None, runner=None, inference=None, transport=None, pilot_factory=FakePilot,
                                recording_dir=tmp_path / "native" / "output" / "recordings" / "unit-1-a1")
    native.start_recorder(scene).finish()
    assert listing(files.directory) == listing(native_directory) == [
        "events.jsonl", "raw/bag-probe-trace.jsonl", "raw/ready.json", "steps.jsonl", "world.jsonl"]
    # and the process manifest stays beside the episode, in both
    assert listing(task_dir / "recordings") == ["unit-1-a1/owned-runtime-processes.json"]
    assert listing(tmp_path / "native" / "output") == ["recordings/unit-1-a1/owned-runtime-processes.json"]


def test_the_task_result_carries_the_services_account_of_the_episode(world):
    result = world.build().run()
    assert "service" in result and result["service"] is None            # the fake session has no service; the key is always there
    summary = {"replies": 2, "outcomes": {"OK": 2}}
    shaped = task_builder.task_result(world.document(), {"verdict": "DONE", "done": True, "reason": None, "status": "COMPLETED",
                                                         "timing": {"wall_s": 1.0}, "service": summary}, ["episode.json"], wall_s=2.0)
    assert shaped["service"] == summary
