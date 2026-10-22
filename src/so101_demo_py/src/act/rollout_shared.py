"""Pieces of the closed-loop rollout that the native tool and the parallel shards share.

They live here, and not in `so101_demo.cli.act_rollout_native`, so that the policy service (which runs in the training interpreter,
without ROS) and the shard task builder can use them without importing the native command. The definitions were moved out of the
native command unchanged (the native module re-exports each name); the inputs loader, the episode evidence files and the episode
document are therefore the very ones the native tool writes, which is what makes a shard's episode schema-identical to a native one.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import time

from so101_demo.act.rollout_execution import resolve_execution


def warm_up_policy(policy, observation: dict, *, calls: int = 3, monotonic=time.monotonic) -> list:
    """Run the model on synthetic observations of the bundle's shapes before the first episode; returns the call latencies.

    The first call of a CUDA model costs far more than the frozen `max_reply_age_s`, so without this the first request of a run
    would always be refused as stale. Nothing of the result is used; the policy is reset afterwards, so no model state reaches
    the first episode."""

    import numpy as np

    sample = {"sim_time_s": 0.0, "state": [0.0] * observation["state_dim"]}
    height, width, _channels = observation["image_shape"]
    for camera in observation["cameras"]:
        sample[camera] = np.zeros((height, width, 3), dtype=np.uint8)
    latencies = []
    for _ in range(calls):
        started = monotonic()
        policy.infer(sample)
        latencies.append(round(monotonic() - started, 6))
    policy.reset()
    return latencies


@dataclass(frozen=True)
class RolloutInputs:
    settings: object
    snapshot_targets: dict
    endpoint_policy: dict
    timing: dict
    rollout_config: dict
    observation: dict
    scenes: dict
    substitution: dict
    identity: dict
    bundle: dict | None = None
    bundle_dir: Path | None = None
    runtime_config: dict | None = None
    frozen: dict | None = None
    manifest_path: Path | None = None
    recorder_policy: dict | None = None
    #: the effective execution mode (`rollout_execution.ExecutionMode`); None is the bundle's frozen behaviour
    execution: object | None = None
    #: file hashes and the outcome-risk / runtime-only values the run used (recorded in run.json, never compared)
    runtime_used: dict | None = None


def _plain(value):
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "__dict__"):
        return vars(value)
    return str(value)


def _line(row) -> str:
    return json.dumps(row, sort_keys=True, default=_plain) + "\n"


def _write_json(path: Path, document) -> None:
    with path.open("x") as handle:
        handle.write(json.dumps(document, sort_keys=True, indent=2, default=_plain) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


class EpisodeFiles:
    """The evidence files of one attempt. The step, world and event rows are appended while the episode runs."""

    ROWS = {"step": "steps.jsonl", "world": "world.jsonl", "event": "events.jsonl"}

    def __init__(self, directory) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True)
        self._handles = {kind: (self.directory / name).open("x") for kind, name in self.ROWS.items()}

    def _append(self, kind, row) -> None:
        handle = self._handles[kind]
        handle.write(_line(row))
        handle.flush()

    def step(self, row) -> None:
        self._append("step", row)

    def world(self, row) -> None:
        self._append("world", row)

    def event(self, row) -> None:
        self._append("event", row)

    def seal(self, document: dict, result: dict) -> list:
        """Close the row files and write the episode, endpoint and stop documents; the names, for the run row."""

        for handle in self._handles.values():
            handle.close()
        endpoint = result.get("endpoint")
        _write_json(self.directory / "episode.json", document)
        _write_json(self.directory / "endpoint.json", {
            "stop_receipt": result.get("stop"), "end_observation": None if endpoint is None else endpoint.get("end_observation"),
            "endpoint": endpoint})
        _write_json(self.directory / "stop-proof.json", {
            "stop": result.get("stop"), "retire_errors": result.get("retire_errors"), "recorder": result.get("recorder"),
            "no_controller_goal_after_retire": not result.get("retire_errors")})
        return ["episode.json", "endpoint.json", "steps.jsonl", "world.jsonl", "stop-proof.json"]


def _execution_document(inputs, result=None):
    """The effective execution mode as recorded: the run's resolved mode, else what the episode itself reports."""

    if inputs.execution is not None:
        return inputs.execution.document()
    return None if result is None else result.get("execution")


def make_policy_runner(inputs, policy):
    """The policy runner of a run: the bundle's frozen prefix, or the execution mode's override (one step for ensembling)."""

    from so101_demo.act.policy import ActPolicyRunner

    mode = inputs.execution
    return ActPolicyRunner(inputs.bundle, policy, observation={
        "cameras": inputs.observation["cameras"], "state_dim": inputs.observation["state_dim"]},
        execution_prefix=None if mode is None else mode.runner_prefix)


def episode_document(*, inputs, options, scene, attempt_id, result, preconditions) -> dict:
    observation = dict(inputs.observation)
    observation["cameras"] = list(observation["cameras"])
    return {"schema_version": 1, "kind": "ACT_ROLLOUT_EPISODE", "run_id": options.run_id, "attempt_id": attempt_id,
            "group": scene["group"], "scene": scene, "identity": dict(inputs.identity), "observation": observation,
            "execution": _execution_document(inputs, result),
            "joint_limit_clamp_tolerance_rad": inputs.settings.joint_limit_clamp_tolerance_rad,
            "calibration": inputs.substitution, "preconditions": preconditions, "verdict": result["verdict"],
            "reason": result["reason"], "done": result["done"], "status": result["status"], "result": result}


def select_scenes(document: dict, group: str, scene_ids=None, limit=None) -> list:
    groups = document.get("groups", {})
    if group not in groups or not groups[group]:
        raise ValueError("ROLLOUT_GROUP_UNKNOWN: " + str(group))
    scenes = list(groups[group])
    if scene_ids:
        by_id = {scene["scene_id"]: scene for scene in scenes}
        for scene_id in scene_ids:
            if scene_id not in by_id:
                raise ValueError("ROLLOUT_SCENE_UNKNOWN: " + str(scene_id))
        scenes = [by_id[scene_id] for scene_id in scene_ids]
    if limit is not None:
        scenes = scenes[:limit]
    return scenes


def _invalid_result(scene, attempt_id, error) -> dict:
    return {"scene_id": scene["scene_id"], "group": scene.get("group"), "attempt_id": attempt_id, "verdict": "INVALID",
            "done": False, "reason": "EPISODE_RUNNER_FAULT: " + (str(error) or type(error).__name__)[:250],
            "status": "FAULT", "phases": [], "counts": None, "motion": None, "stop": {"confirmed": False},
            "endpoint": None, "timing": {"wall_s": 0.0}, "retire_errors": [], "recorder": None}


def _sha256(path) -> str:
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_inputs(args) -> RolloutInputs:
    """Read, verify and bind everything a run takes from outside: the frozen inputs manifest, the bundle, the configs, the scenes."""

    from so101_demo.act.bundle import load_bundle
    from so101_demo.act.frozen_runtime_inputs import load_recorder_frozen_policy, load_teacher_frozen_inputs
    from so101_demo.act.policy import observation_spec
    from so101_demo.act.rig_profile import rig_from_observation
    from so101_demo.act.rollout_activation import contact_activation_substitution
    from so101_demo.act import rollout_config as rollout_values
    from so101_demo.act import runtime_config as runtime_values
    from so101_demo.act.rollout_config import (
        camera_topics_for, controller_timing, load_rollout_config, rollout_settings)
    from so101_demo.act.rollout_scenes import verify_scene_document
    from so101_demo.act.runtime_config import load_runtime_config
    from so101_demo.act.teacher_endpoint import load_teacher_endpoint_policy

    manifest_path = Path(args.inputs_manifest)
    frozen, snapshot, snapshot_root = load_teacher_frozen_inputs(manifest_path)
    config = load_rollout_config(args.rollout_config)
    bundle_dir = Path(args.bundle_dir)
    bundle = load_bundle(bundle_dir / "bundle.json")
    declared = bundle["normalization"].get("observation") is not None
    spec = observation_spec(bundle, legacy_cameras=config["undeclared_bundle_cameras"])
    # the rig the stack must compose and the topics the executor subscribes to are decided here, before any process starts
    camera_topics_for(config, spec["cameras"])
    rig_from_observation(spec["cameras"], spec["state_dim"])
    image_shape = bundle["normalization"].get("image_shape")
    if not isinstance(image_shape, list) or len(image_shape) != 3 or image_shape[0] != 3:
        raise ValueError("ROLLOUT_BUNDLE_IMAGE_SHAPE_INVALID")
    observation = {"cameras": spec["cameras"], "state_dim": spec["state_dim"],
                   "image_shape": [image_shape[1], image_shape[2], 3],
                   "source": "bundle" if declared else "rollout_config.undeclared_bundle_cameras"}
    endpoint = load_teacher_endpoint_policy(snapshot_root / "config/act/teacher_endpoint.yaml")
    if endpoint["policy_sha256"] != frozen["teacher_endpoint"]["policy_sha256"]:
        raise ValueError("ROLLOUT_ENDPOINT_POLICY_MISMATCH")
    scenes = json.loads(Path(args.scenes).read_bytes())
    verify_scene_document(scenes, taken_xy=None, place_xy=None)
    receipt = Path(args.contact_activation_receipt) if args.contact_activation_receipt else (
        manifest_path.parent / frozen["roles"]["contact_activation"]["path"])
    proposal = Path(args.contact_proposal) if args.contact_proposal else (
        manifest_path.parent / frozen["roles"]["contact_proposal"]["path"])
    runtime_path = Path(args.runtime_config)
    runtime = load_runtime_config(runtime_path)
    identity = {"bundle_sha256": _sha256(bundle_dir / "bundle.json"), "policy_sha256": bundle["policy_sha256"],
                "inputs_manifest_sha256": _sha256(manifest_path),
                "runtime_logic_sha256": runtime_values.logic_sha256(runtime),
                "rollout_logic_sha256": rollout_values.logic_sha256(config), "snapshot_sha256": snapshot["snapshot_sha256"],
                "source_commit": frozen.get("source_commit"), "gate_install": str(args.install_prefix),
                "scenes_sha256": scenes.get("manifest_sha256")}
    # the execution mode is a LOGIC setting: refused here when invalid, and bound into the identity when it is an override, so
    # runs of different modes can never be mixed (the default keeps the identity of every earlier run unchanged)
    execution = resolve_execution(bundle["action"], prefix=getattr(args, "execution_prefix", None),
                                  ensembling=getattr(args, "temporal_ensembling", None))
    if execution.source != "bundle":
        identity["execution_mode"] = execution.document()
    settings = rollout_settings(frozen, config)
    # the clamp tolerance is a LOGIC setting too (it changes what reaches the controller): bound into the identity when set, so a
    # run with it can never be mixed with one without; absent keeps the identity of every earlier run unchanged
    if settings.joint_limit_clamp_tolerance_rad is not None:
        identity["joint_limit_clamp_tolerance_rad"] = settings.joint_limit_clamp_tolerance_rad
    # what the run used of the files and is not in the identity: the file hashes and the outcome-risk and runtime-only values
    runtime_used = {"runtime_yaml_sha256": _sha256(runtime_path), "rollout_yaml_sha256": _sha256(args.rollout_config),
                    "runtime": runtime_values.runtime_values(runtime), "rollout": rollout_values.runtime_values(config)}
    return RolloutInputs(
        runtime_used=runtime_used, settings=settings, snapshot_targets=snapshot["targets"], endpoint_policy=endpoint,
        timing=controller_timing(frozen, config), rollout_config=config, observation=observation, scenes=scenes,
        substitution=contact_activation_substitution(receipt, proposal), identity=identity, bundle=bundle,
        bundle_dir=bundle_dir, runtime_config=runtime, frozen=frozen, manifest_path=manifest_path,
        recorder_policy=load_recorder_frozen_policy(manifest_path), execution=execution)


class RelocatedRecording:
    """A raw recording made where the recorder is allowed to write (under the instance's owned root: it refuses a bag anywhere
    else, `CONTAINER_BAG_ROOT_MISMATCH`), moved into the episode's evidence directory once the recorder has closed the bag."""

    def __init__(self, recording, *, target) -> None:
        self.recording, self.target = recording, Path(target)

    @property
    def ready(self):
        return self.recording.ready

    @property
    def failure(self):
        return self.recording.failure

    def start(self):
        return self.recording.start()

    def finish(self):
        facts = self.recording.finish()
        source = Path(self.recording.root)
        try:
            if source.is_dir():
                if self.target.exists():
                    raise FileExistsError(str(self.target))
                os.rename(source, self.target)
                facts = dict(facts, relocated_from=str(source), relocated_to=str(self.target))
        except OSError as error:
            facts = dict(facts, failure=f"RAW_RELOCATE_FAILED: {error}"[:300])
        return facts


class NativeEpisodePorts:
    """The ports `run_episode` drives, over the shard runtime's reset and gate (`ActRosRuntimePorts`) and the rollout session."""

    def __init__(self, *, runtime, lease, scene, directory, inputs, environment, binding, runner, inference, transport,
                 pilot_factory, recording_dir=None, monotonic=time.monotonic) -> None:
        self.recording_dir = None if recording_dir is None else Path(recording_dir)
        self.runtime, self.lease, self.scene, self.directory = runtime, lease, scene, Path(directory)
        self.inputs, self.environment, self.binding = inputs, environment, binding
        self.runner, self.inference, self.transport = runner, inference, transport
        self.pilot_factory, self.monotonic = pilot_factory, monotonic
        self._receipt = None

    def reset(self, scene):
        # The previous episode left the retained pause control (a node `/so101_live_runtime_pause_control`) alive; the initial
        # gate's exact node inventory refuses it, so every episode starts with the runtime's retained ROS resources released.
        self.runtime.close_runtime()
        self._receipt = self.runtime.reset_point(self.lease)
        receipt = self._receipt
        return {"reset_epoch": receipt.reset_epoch_value, "simulation_session_id": receipt.simulation_session_id,
                "simulation_time_s": receipt.simulation_time_s, "joint_positions": receipt.joint_positions}

    def initial_gate(self, scene, receipt):
        return dict(vars(self.runtime.initial_gate(self.lease, self._receipt)))

    def resume_physics(self, receipt):
        return self.runtime.resume_physics(self.lease, self._receipt) is True

    def start_recorder(self, scene):
        if self.recording_dir is None:
            pilot = self.pilot_factory(self.directory)
        else:
            pilot = RelocatedRecording(self.pilot_factory(self.recording_dir), target=self.directory / "raw")
        pilot.start()
        if not pilot.ready:
            facts = pilot.finish()
            raise RuntimeError(pilot.failure or facts.get("failure") or "RAW_PILOT_NOT_READY")
        return pilot

    def open_session(self, scene, receipt, attempt_id):
        from so101_demo.adapters.act.rollout_ros import build_ros_session

        if not self.transport.quiesce(5.0):
            raise RuntimeError("ROLLOUT_INFERENCE_NOT_IDLE")
        config, observation = self.inputs.rollout_config, self.inputs.observation
        frozen = self.inputs.frozen

        def world_observer(node, session_id):
            from so101_demo.backends.mujoco.observer import MujocoWorldObserver
            return MujocoWorldObserver(node, session_id, max_age_s=config["world_max_age_s"], accept_truncated=True)

        return build_ros_session(
            binding=self.binding, config=config, cameras=observation["cameras"], state_dim=observation["state_dim"],
            image_shape=tuple(observation["image_shape"]), session_id=receipt["simulation_session_id"],
            source_floor_s=receipt["simulation_time_s"], timing=self.inputs.timing,
            rgb_sync=frozen["runtime_policy"]["rgb_sync"], world_observer_factory=world_observer)

    def cancel_motion(self):
        return self.runtime.cancel_motion(self.lease)

    def confirm_no_controller_goal(self):
        return self.runtime.confirm_no_controller_goal(self.lease) is True


def pilot_factory_for(*, environment, ready_timeout_s, rig_profile):
    """`pilot(directory) -> PilotRecording`: the raw recorder of one episode, recording the rig whose profile file `rig_profile` is."""

    from so101_demo.act.offline.pilot import PilotRecording
    from so101_demo.runtime.parallel_worker_parts.process_tree import WorkerOwnedProcessTree
    from so101_demo.runtime.task_stack import StackProcessSpec

    def pilot(directory):
        return PilotRecording(
            processes=WorkerOwnedProcessTree(manifest_path=Path(directory) / "owned-runtime-processes.json"),
            root=Path(directory) / "raw", environment=dict(environment),
            spec_factory=lambda argv: StackProcessSpec("act-raw-pilot", tuple(argv)),
            timeout_s=float(ready_timeout_s), rig_profile=rig_profile)
    return pilot
