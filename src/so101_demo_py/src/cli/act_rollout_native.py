"""CLI: run a trained ACT policy in a closed loop on the native MuJoCo stack, one episode at a time.

Design: docs/superpowers/specs/2026-10-18-so101-act-native-rollout-design.md (decisions D1 to D8). The command runs on the host, not in
a container, and bypasses unified admission (D5): it therefore proves its own preconditions first and records them -

    no_container          no running container
    unified_store_idle    the unified service store is IDLE with no GPU lease and no active ACT slot
    ros_graph_empty       no node on the fixed instance ROS domain (181)
    no_instance_process   no process carries an ACT instance marker
    no_gpu_process        no compute process on the GPU

then creates the owned root, applies the fixed instance environment (`native_instance_environment`), starts the stack at the fixed
identity (`instance_stack_launch`, `compose_stack`), runs the episodes of one scene group in sequence through the state machine in
`so101_demo.act.rollout_episode`, and stops the stack with its stop proof. An episode the machine calls INVALID (infrastructure
fault) is re-run up to `--max-invalid-retries` times and reported apart from the policy's results; a scene that stays INVALID ends
the run (the stack is suspect). `rollout_test` is opened once per policy.

Layout under `--evidence-root` (all of it new; nothing is overwritten):

    owned/<run-id>/            the owned root: stack/, output/, control/, tmp/, ros-logs/, stack-stop-proof.json
    <group>/run.json           inputs, preconditions and the calibration substitution of this run
    <group>/act-runs.jsonl     one run row per scene: {search_locked, done, interventions, elapsed_wall_s, scene_id, evidence}
    <group>/invalid-runs.jsonl every INVALID attempt, with its reason
    <group>/episodes/<scene>-a<n>/   episode.json, steps.jsonl, world.jsonl, endpoint.json, stop-proof.json, raw/
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from so101_demo.act.rollout_episode import run_episode

PRECONDITIONS = ("no_container", "unified_store_idle", "ros_graph_empty", "no_instance_process", "no_gpu_process")
INSTANCE_MARKER = b"SO101_ACT_INSTANCE_ROOT="
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
EXIT_OK, EXIT_INVALID, EXIT_REFUSED, EXIT_STOP_UNCONFIRMED, EXIT_START_FAILED = 0, 1, 2, 3, 4


class PreconditionRefused(ValueError):
    """A precondition of the native run failed or could not be proven."""


# ---- preconditions (D5) --------------------------------------------------------------------------------------------------


def check_preconditions(probes: dict) -> dict:
    """Run every probe in order; each returns ``(ok, detail)``. A probe that fails, raises or is absent refuses the run."""

    evidence = {}
    for name in PRECONDITIONS:
        probe = probes.get(name)
        if not callable(probe):
            raise PreconditionRefused(f"ROLLOUT_PRECONDITION_UNPROVEN: {name}: no probe")
        try:
            ok, detail = probe()
        except Exception as error:      # noqa: BLE001 - a probe that cannot answer is not a pass
            raise PreconditionRefused(f"ROLLOUT_PRECONDITION_UNPROVEN: {name}: {error}") from error
        if ok is not True:
            raise PreconditionRefused(f"ROLLOUT_PRECONDITION_FAILED: {name}: {detail}")
        evidence[name] = {"ok": True, "detail": detail}
    return evidence


def _lines(result, tool: str) -> list:
    if result.returncode != 0:
        raise RuntimeError(f"{tool} failed: {str(result.stderr).strip()[:200]}")
    return [line.strip() for line in str(result.stdout).splitlines() if line.strip()]


def container_probe(*, run=subprocess.run):
    """No running container. A Docker socket the process cannot read is "unproven", never "none"."""

    names = _lines(run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, timeout=30,
                       check=False), "docker ps")
    return (not names), names


def gpu_probe(*, run=subprocess.run):
    """No compute process on the GPU (the policy runs on it; a training job or another worker would share it)."""

    processes = _lines(run(["nvidia-smi", "--query-compute-apps=pid,process_name", "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=30, check=False), "nvidia-smi")
    return (not processes), processes


def instance_process_probe(*, proc=Path("/proc"), own_pid=None):
    """No readable process environment carries an ACT instance marker (a left-over stack or recorder of an earlier run)."""

    own_pid = os.getpid() if own_pid is None else own_pid
    found = []
    for entry in sorted(Path(proc).iterdir(), key=lambda item: item.name):
        if not entry.name.isdigit() or int(entry.name) == own_pid:
            continue
        try:
            environment = (entry / "environ").read_bytes().split(b"\x00")
        except OSError:
            continue                    # exited, or another user's / non-dumpable process: cannot carry our marker
        for item in environment:
            if item.startswith(INSTANCE_MARKER):
                found.append({"pid": int(entry.name), "root": item[len(INSTANCE_MARKER):].decode(errors="replace")})
                break
    return (not found), found


def unified_store_probe(root):
    """The unified service store, read-only: IDLE, no GPU workload lease, no active ACT worker slot."""

    import sqlite3

    database = Path(root) / "intents.sqlite3"
    if not database.is_file():
        raise RuntimeError(f"UNIFIED_STORE_UNAVAILABLE: {database}")
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        row = connection.execute("SELECT state FROM global_state WHERE singleton = 1").fetchone()
        leases = connection.execute("SELECT COUNT(*) FROM gpu_workload_leases").fetchone()[0]
        slots = connection.execute("SELECT COUNT(*) FROM act_worker_slots WHERE active = 1").fetchone()[0]
    finally:
        connection.close()
    state = None if row is None else row[0]
    return (state == "IDLE" and leases == 0 and slots == 0), {"state": state, "gpu_leases": leases, "active_slots": slots}


def default_probes(*, unified_state_root, graph_probe) -> dict:
    """The host probes. `graph_probe()` is True when the instance domain has no node (a `RosGraphClearProbe`)."""

    return {"no_container": container_probe, "unified_store_idle": lambda: unified_store_probe(unified_state_root),
            "ros_graph_empty": lambda: (graph_probe() is True, {"domain": 181}),
            "no_instance_process": instance_process_probe, "no_gpu_process": gpu_probe}


def import_preflight(*, importer=importlib.import_module) -> None:
    """D1: rclpy, torch and lerobot must live in one interpreter, with CUDA usable, or the run is refused (the documented
    fallback is a streaming inference subprocess behind `ActInferenceProcess`)."""

    modules = {}
    for name in ("rclpy", "torch", "lerobot"):
        try:
            modules[name] = importer(name)
        except Exception as error:      # noqa: BLE001
            raise RuntimeError(f"ROLLOUT_IMPORT_PREFLIGHT_FAILED: {name}: {error}") from error
    if modules["torch"].cuda.is_available() is not True:
        raise RuntimeError("ROLLOUT_IMPORT_PREFLIGHT_FAILED: torch.cuda is not available")


# ---- the owned root and the environment ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class RolloutLayout:
    evidence_root: Path
    owned_root: Path
    output_root: Path
    control_root: Path
    stack_root: Path
    tmp_root: Path
    ros_log_root: Path


def prepare_layout(evidence_root, run_id) -> RolloutLayout:
    root = Path(evidence_root)
    if (not root.is_absolute() or ".." in root.parts or not root.is_dir() or root.is_symlink()
            or not isinstance(run_id, str) or _ID.fullmatch(run_id) is None):
        raise ValueError("ROLLOUT_LAYOUT_INVALID")
    owned = root / "owned" / run_id
    if owned.exists() or owned.is_symlink():
        raise ValueError("ROLLOUT_OWNED_ROOT_EXISTS")
    (root / "owned").mkdir(mode=0o700, exist_ok=True)
    owned.mkdir(mode=0o700)
    layout = RolloutLayout(root, owned, owned / "output", owned / "control", owned / "stack", owned / "tmp",
                           owned / "ros-logs")
    for directory in (layout.output_root, layout.control_root, layout.stack_root, layout.tmp_root, layout.ros_log_root):
        directory.mkdir(mode=0o700)
    return layout


def session_id_for(run_id: str) -> str:
    return ("rollout-" + run_id)[:64]


def native_environment(base, *, layout, session_id, gpu_uuid, install_prefix) -> dict:
    """The fixed ROS identity, renderer, private locations and instance marker of this run (see `native_instance_environment`)."""

    from so101_demo.runtime.container_campaign.native_owner import native_instance_environment

    return native_instance_environment(dict(base), owned_root=layout.owned_root, session_id=session_id,
                                       gpu_uuid=gpu_uuid, install_prefix=str(install_prefix))


def apply_environment(target, environment) -> None:
    """Make `target` (``os.environ``) equal to `environment`: names the identity removes are removed."""

    for name in [name for name in target if name not in environment]:
        del target[name]
    target.update(environment)


# ---- inputs and evidence -------------------------------------------------------------------------------------------------


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


def episode_document(*, inputs, options, scene, attempt_id, result, preconditions) -> dict:
    observation = dict(inputs.observation)
    observation["cameras"] = list(observation["cameras"])
    return {"schema_version": 1, "kind": "ACT_ROLLOUT_EPISODE", "run_id": options.run_id, "attempt_id": attempt_id,
            "group": scene["group"], "scene": scene, "identity": dict(inputs.identity), "observation": observation,
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


def run_rollout(*, options, inputs, probes, composition_factory, episode_runner=run_episode, environ=None,
                preflight=None, wall=time.monotonic) -> dict:
    """Preconditions, owned root, environment, stack, the episodes of one group in sequence, the stack stop and its proof."""

    group = options.group
    scenes = select_scenes(inputs.scenes, group, options.scene_ids, options.limit)
    policy_sha = inputs.identity["policy_sha256"]
    group_root = Path(options.evidence_root) / group
    marker = group_root / f"opened-{policy_sha[:12]}.json"
    if group == "rollout_test" and marker.exists():
        raise ValueError("ROLLOUT_TEST_ALREADY_OPENED")
    preconditions = check_preconditions(probes)
    if group_root.exists() or group_root.is_symlink():
        raise ValueError("ROLLOUT_GROUP_ROOT_EXISTS")
    layout = prepare_layout(options.evidence_root, options.run_id)
    session_id = session_id_for(options.run_id)
    environ = os.environ if environ is None else environ
    environment = native_environment(environ, layout=layout, session_id=session_id, gpu_uuid=options.gpu_uuid,
                                     install_prefix=options.install_prefix)
    apply_environment(environ, environment)
    if preflight is not None:
        preflight()
    group_root.mkdir(mode=0o700)
    (group_root / "episodes").mkdir(mode=0o700)
    if group == "rollout_test":
        _write_json(marker, {"policy_sha256": policy_sha, "run_id": options.run_id, "scenes": len(scenes)})
    _write_json(group_root / "run.json", {
        "schema_version": 1, "kind": "ACT_ROLLOUT_RUN", "run_id": options.run_id, "group": group,
        "session_id": session_id, "scene_ids": [scene["scene_id"] for scene in scenes],
        "scenes_manifest_sha256": inputs.scenes.get("manifest_sha256"), "identity": dict(inputs.identity),
        "observation": {**inputs.observation, "cameras": list(inputs.observation["cameras"])},
        "calibration": inputs.substitution, "preconditions": preconditions,
        "max_invalid_retries": options.max_invalid_retries})
    composition = composition_factory(layout=layout, environment=environment, inputs=inputs, options=options)
    summary = {"exit_code": EXIT_OK, "done": 0, "verdicts": {}, "invalid_attempts": 0, "invalid_exhausted": [],
               "fault": None, "stack_stop_confirmed": None, "scenes": len(scenes)}
    verdicts = Counter()
    try:
        try:
            composition.start()
        except Exception as error:      # noqa: BLE001
            summary["fault"] = f"{type(error).__name__}: {error}"
            summary["exit_code"] = EXIT_START_FAILED
        else:
            _run_scenes(options, inputs, scenes, composition, group_root, preconditions, episode_runner, wall, summary,
                        verdicts)
    finally:
        try:
            proof = composition.stop()
        except Exception as error:      # noqa: BLE001
            proof = {"confirmed": False, "error": f"{type(error).__name__}: {error}"}
        _write_json(layout.owned_root / "stack-stop-proof.json", proof)
        summary["stack_stop_confirmed"] = proof.get("confirmed") is True
        composition.close()
    summary["verdicts"] = dict(verdicts)
    if summary["exit_code"] == EXIT_OK and summary["invalid_exhausted"]:
        summary["exit_code"] = EXIT_INVALID
    if summary["exit_code"] in (EXIT_OK, EXIT_INVALID) and not summary["stack_stop_confirmed"]:
        summary["exit_code"] = EXIT_STOP_UNCONFIRMED
    return summary


def _run_scenes(options, inputs, scenes, composition, group_root, preconditions, episode_runner, wall, summary, verdicts):
    for scene in scenes:
        for number in range(1, options.max_invalid_retries + 2):
            attempt_id = f"{scene['scene_id']}-a{number}"
            files = EpisodeFiles(group_root / "episodes" / attempt_id)
            try:
                ports = composition.new_ports(scene, attempt_id, files.directory)
                result = episode_runner(scene=scene, attempt_id=attempt_id, ports=ports, settings=inputs.settings,
                                        snapshot_targets=inputs.snapshot_targets, endpoint_policy=inputs.endpoint_policy,
                                        sink=files)
            except Exception as error:      # noqa: BLE001 - the machine reports faults itself; anything else is still a fault
                result = _invalid_result(scene, attempt_id, error)
            names = files.seal(episode_document(inputs=inputs, options=options, scene=scene, attempt_id=attempt_id,
                                                result=result, preconditions=preconditions), result)
            evidence = [f"episodes/{attempt_id}/{name}" for name in names]
            if result["verdict"] == "INVALID":
                summary["invalid_attempts"] += 1
                with (group_root / "invalid-runs.jsonl").open("a") as handle:
                    handle.write(_line({"scene_id": scene["scene_id"], "attempt_id": attempt_id, "reason": result["reason"],
                                        "evidence": evidence}))
                continue
            verdicts[result["verdict"]] += 1
            summary["done"] += 1 if result["done"] else 0
            with (group_root / "act-runs.jsonl").open("a") as handle:
                handle.write(_line({"search_locked": True, "done": result["done"], "interventions": 0,
                                    "elapsed_wall_s": result["timing"]["wall_s"], "scene_id": scene["scene_id"],
                                    "evidence": evidence}))
            break
        else:
            summary["invalid_exhausted"].append(scene["scene_id"])
            return                      # the stack is suspect: no further scene is run on it


# ---- real inputs and composition -----------------------------------------------------------------------------------------


def _sha256(path) -> str:
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_inputs(args) -> RolloutInputs:
    """Read, verify and bind everything a run takes from outside: the frozen inputs manifest, the bundle, the configs, the scenes."""

    from so101_demo.act.bundle import load_bundle
    from so101_demo.act.frozen_runtime_inputs import load_recorder_frozen_policy, load_teacher_frozen_inputs
    from so101_demo.act.policy import observation_spec
    from so101_demo.act.rollout_activation import contact_activation_substitution
    from so101_demo.act.rollout_config import (
        controller_timing, load_rollout_config, rollout_settings)
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
                "inputs_manifest_sha256": _sha256(manifest_path), "runtime_yaml_sha256": _sha256(runtime_path),
                "rollout_yaml_sha256": _sha256(args.rollout_config), "snapshot_sha256": snapshot["snapshot_sha256"],
                "source_commit": frozen.get("source_commit"), "gate_install": str(args.install_prefix),
                "scenes_sha256": scenes.get("manifest_sha256")}
    return RolloutInputs(
        settings=rollout_settings(frozen, config), snapshot_targets=snapshot["targets"], endpoint_policy=endpoint,
        timing=controller_timing(frozen, config), rollout_config=config, observation=observation, scenes=scenes,
        substitution=contact_activation_substitution(receipt, proposal), identity=identity, bundle=bundle,
        bundle_dir=bundle_dir, runtime_config=runtime, frozen=frozen, manifest_path=manifest_path,
        recorder_policy=load_recorder_frozen_policy(manifest_path))


class NativeEpisodePorts:
    """The ports `run_episode` drives, over the shard runtime's reset and gate (`ActRosRuntimePorts`) and the rollout session."""

    def __init__(self, *, runtime, lease, scene, directory, inputs, environment, binding, runner, inference, transport,
                 pilot_factory, monotonic=time.monotonic) -> None:
        self.runtime, self.lease, self.scene, self.directory = runtime, lease, scene, Path(directory)
        self.inputs, self.environment, self.binding = inputs, environment, binding
        self.runner, self.inference, self.transport = runner, inference, transport
        self.pilot_factory, self.monotonic = pilot_factory, monotonic
        self._receipt = None

    def reset(self, scene):
        self._receipt = self.runtime.reset_point(self.lease)
        receipt = self._receipt
        return {"reset_epoch": receipt.reset_epoch_value, "simulation_session_id": receipt.simulation_session_id,
                "simulation_time_s": receipt.simulation_time_s, "joint_positions": receipt.joint_positions}

    def initial_gate(self, scene, receipt):
        return dict(vars(self.runtime.initial_gate(self.lease, self._receipt)))

    def resume_physics(self, receipt):
        return self.runtime.resume_physics(self.lease, self._receipt) is True

    def start_recorder(self, scene):
        pilot = self.pilot_factory(self.directory)
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


class NativeComposition:
    """The real stack, runtime ports, policy and recorder of one run. Built after the environment is applied."""

    def __init__(self, *, layout, environment, inputs, options) -> None:
        from so101_demo.act.policy import ActPolicyRunner
        from so101_demo.adapters.act.inference_process import ActInferenceProcess
        from so101_demo.adapters.act.lerobot import build_policy_from_bundle
        from so101_demo.adapters.act.rollout_ros import RclpyBinding, ThreadInferenceTransport
        from so101_demo.parallel_batch.contracts.common import RunMode
        from so101_demo.runtime.act_instance.program import compose_stack, instance_stack_launch
        from so101_demo.runtime.act_ros_runtime import ActRosRuntimePorts
        from so101_teleop.unified.act_stack_probes import RosGraphClearProbe

        self.layout, self.environment, self.inputs, self.options = layout, environment, inputs, options
        self.session_id = session_id_for(options.run_id)
        policy = build_policy_from_bundle(inputs.bundle_dir, "cuda", bundle=inputs.bundle)
        self.transport = ThreadInferenceTransport(policy.infer)
        self.inference = ActInferenceProcess(config=inputs.runtime_config, transport=self.transport, clock=time.monotonic)
        self.runner = ActPolicyRunner(inputs.bundle, policy, observation={
            "cameras": inputs.observation["cameras"], "state_dim": inputs.observation["state_dim"]})
        self.launch = instance_stack_launch({"simulation_session_id": self.session_id}, ros2=Path(options.ros2),
                                            stack_root=layout.stack_root, environment=environment)
        observer = Path(options.install_prefix) / "lib/so101_demo_py/act_stack_ready"
        _ready, _ready_check, self.stack = compose_stack(self.launch, observer)
        self.graph_probe = RosGraphClearProbe(self.launch, spin_time_s=3.0)
        self.resources = self._resources()
        catalog = {scene["scene_id"]: {"cup_position_world_m": scene["cup_position_world_m"]}
                   for scene in inputs.scenes["groups"][options.group]}
        self.runtime = ActRosRuntimePorts(self.resources, catalog=catalog, config=None, mode=RunMode.EXECUTE,
                                          broker_generation=self.resources.generation,
                                          dependencies={"act_profile": True})
        self.binding = RclpyBinding()
        self.attempts = 0

    def _resources(self):
        from so101_demo.parallel_batch.resource_allocation.models import WorkerResources

        owned, session = self.layout.owned_root, self.session_id
        return WorkerResources(
            worker_id="w00", slot_index=0, generation=1, ros_domain_id=181, simulation_port=session, bridge_port=session,
            gz_partition=session, session_id=session, controller_namespace="/", render_backend="egl",
            render_context_id=session, render_context_namespace=self.layout.tmp_root / "render",
            virtual_display="not_applicable", ros_home=self.layout.tmp_root / "ros-home", ros_log_dir=self.layout.ros_log_root,
            temp_dir=self.layout.tmp_root, socket_namespace=self.layout.control_root,
            socket_path=self.layout.control_root / "worker-unused.sock", worker_root=self.layout.output_root,
            environment=dict(self.environment))

    def start(self):
        import asyncio

        asyncio.run(self.stack.start(timeout_s=self.options.stack_timeout_s))

    def new_ports(self, scene, attempt_id, directory):
        from so101_demo.act.offline.pilot import PilotRecording
        from so101_demo.parallel_batch.contracts.identity import LeaseIdentity
        from so101_demo.runtime.parallel_worker_parts.process_tree import WorkerOwnedProcessTree
        from so101_demo.runtime.task_stack import StackProcessSpec

        self.attempts += 1
        issued = time.monotonic()
        lease = LeaseIdentity(
            batch_id=self.options.run_id, coordinator_epoch=1, worker_id="w00", worker_generation=1,
            point_id=scene["scene_id"], attempt_id=attempt_id, lease_generation=self.attempts,
            lease_issued_monotonic_s=issued,
            lease_deadline_monotonic_s=issued + self.inputs.settings.execution_deadline_s + 600.0)

        def pilot(directory):
            return PilotRecording(
                processes=WorkerOwnedProcessTree(manifest_path=Path(directory) / "owned-runtime-processes.json"),
                root=Path(directory) / "raw", environment=dict(self.environment),
                spec_factory=lambda argv: StackProcessSpec("act-raw-pilot", tuple(argv)),
                timeout_s=float(self.inputs.recorder_policy["ready_timeout_s"]))

        return NativeEpisodePorts(runtime=self.runtime, lease=lease, scene=scene, directory=directory, inputs=self.inputs,
                                  environment=self.environment, binding=self.binding, runner=self.runner,
                                  inference=self.inference, transport=self.transport, pilot_factory=pilot)

    def stop(self) -> dict:
        import asyncio

        from so101_demo.runtime.container_campaign.native_stop import marker_survivors
        from so101_teleop.process_identity import read_identity

        errors = []
        try:
            asyncio.run(self.stack.stop())
        except Exception as error:      # noqa: BLE001
            errors.append(f"{type(error).__name__}: {error}")
        survivors, graph_clear = None, None
        try:
            started = read_identity(os.getpid()).start_marker
            survivors = marker_survivors(str(self.layout.owned_root), started_ticks=started, exclude=(os.getpid(),),
                                         observer_pid=os.getpid())
        except Exception as error:      # noqa: BLE001
            errors.append(f"marker_survivors: {type(error).__name__}: {error}")
        try:
            graph_clear = self.graph_probe() is True
        except Exception as error:      # noqa: BLE001
            errors.append(f"graph_probe: {type(error).__name__}: {error}")
        receipt = self.layout.stack_root / "stack-retirement-receipt.json"
        return {"schema_version": 1, "kind": "ACT_ROLLOUT_STACK_STOP_PROOF", "stack_stop_errors": errors,
                "marker_survivors": survivors, "graph_clear": graph_clear,
                "retirement_receipt": str(receipt) if receipt.exists() else None,
                "confirmed": not errors and survivors == [] and graph_clear is True}

    def close(self):
        self.inference.close()
        self.runtime.close_runtime()


def build_native_composition(**kwargs):
    return NativeComposition(**kwargs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="act_rollout_native", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--group", choices=("rollout_standard", "rollout_validation", "rollout_test",
                                            "rollout_extrapolation"), required=True)
    parser.add_argument("--scenes", type=Path, required=True, help="the ACT_ROLLOUT_SCENES list")
    parser.add_argument("--scene-id", dest="scene_ids", action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--inputs-manifest", type=Path, required=True, help="the frozen inputs manifest of the gate install")
    parser.add_argument("--runtime-config", type=Path, required=True, help="config/act/runtime.yaml")
    parser.add_argument("--rollout-config", type=Path, required=True, help="config/act/rollout.yaml")
    parser.add_argument("--contact-activation-receipt", type=Path, help="default: the frozen inputs' activation receipt")
    parser.add_argument("--contact-proposal", type=Path, help="default: the frozen inputs' contact proposal")
    parser.add_argument("--install-prefix", type=Path, required=True, help="the gate install the stack is launched from")
    parser.add_argument("--ros2", type=Path, required=True)
    parser.add_argument("--gpu-uuid", required=True)
    parser.add_argument("--unified-state-root", type=Path, required=True)
    parser.add_argument("--max-invalid-retries", type=int, default=1)
    parser.add_argument("--stack-timeout-s", type=float, default=120.0)
    return parser


def main(argv=None, *, inputs_loader=None, probes=None, composition_factory=None, preflight=import_preflight,
         environ=None, episode_runner=run_episode) -> int:
    args = build_parser().parse_args(argv)
    try:
        inputs = (inputs_loader or load_inputs)(args)
        if probes is None:
            from so101_demo.runtime.act_instance.program import instance_stack_launch
            from so101_teleop.unified.act_stack_probes import RosGraphClearProbe

            # the probe launch is the run's launch in all but its (not yet created) stack root: only its ROS identity is used
            launch = instance_stack_launch({"simulation_session_id": session_id_for(args.run_id)}, ros2=args.ros2,
                                           stack_root=args.evidence_root, environment=dict(os.environ))
            probes = default_probes(unified_state_root=args.unified_state_root,
                                    graph_probe=RosGraphClearProbe(launch, spin_time_s=3.0))
        summary = run_rollout(options=args, inputs=inputs, probes=probes,
                              composition_factory=composition_factory or build_native_composition,
                              episode_runner=episode_runner, environ=environ, preflight=preflight)
    except (PreconditionRefused, ValueError, RuntimeError, OSError) as error:
        print(f"ROLLOUT_REFUSED: {error}", file=sys.stderr)
        return EXIT_REFUSED
    print(json.dumps(summary, sort_keys=True))
    return summary["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
