"""Compose one closed-loop rollout episode inside a shard container: the shard-side task of the parallel rollout.

The shard owns the native stack (`program.serve_instance` starts and retires it); this builder borrows it. One task is one
attempt of one point: the same `run_episode` state machine, the same `NativeEpisodePorts` over `ActRosRuntimePorts`, the same
`PilotRecording`, endpoint evaluation and `EpisodeFiles` as the native command - they are imported from `act/rollout_shared.py`, where
they were moved unchanged - so the episode directory (episode.json, steps.jsonl, world.jsonl, events.jsonl, endpoint.json,
stop-proof.json, raw/) has the schema of a native episode. What differs is only where the policy runs: behind the unchanged
`ActInferenceProcess` rules, the transport is a request to the host's policy service (`runtime/act_policy`).

The builder validates the closed task document before it creates anything, binds the frozen inputs to the run identity the Host wrote
into the shard spec, and checks the policy service's readiness reply against the bundle the task names. A verdict INVALID is a result,
not a fault: the task still succeeds and the Host decides whether to run the scene again.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import re
import threading
import time
from types import SimpleNamespace

from so101_demo.act.parallel_collection_contracts import read_document
from so101_demo.act.rollout_episode import run_episode
from so101_demo.act.rollout_shared import (
    EpisodeFiles, NativeEpisodePorts, _invalid_result, episode_document, load_inputs, make_policy_runner, pilot_factory_for)
from so101_demo.runtime.act_instance.identity import (
    ACT_INSTANCE_ROS_DOMAIN_ID, ACT_INSTANCE_ROS_NAMESPACE, INSTANCE_ROOT_ENV, verify_instance_environment)
from so101_demo.runtime.container_campaign.task_contracts import TaskSpec
from so101_demo.runtime.container_campaign.task_results import reserve_task_output
from so101_demo.runtime.inference.config import validate_file_ref
from so101_demo.runtime.parallel_ipc.frames import canonical_json

KIND = "ACT_CONTAINER_ROLLOUT_TASK"
RESULT_KIND = "ACT_CONTAINER_ROLLOUT_TASK_RESULT"
GROUPS = ("rollout_standard", "rollout_validation", "rollout_test", "rollout_extrapolation")
_FIELDS = {"schema_version", "kind", "task_id", "worker_id", "launch_generation", "wave_id", "scene_id", "point_id", "group",
           "trial", "attempt_number", "attempt_id", "run_id", "run_identity_sha256", "inputs", "execution", "policy",
           "preconditions"}
_REFS = ("inputs_manifest", "runtime_config", "rollout_config", "scenes", "bundle_json")
_OPTIONAL_REFS = ("contact_activation_receipt", "contact_proposal", "scene_variant")
#: besides the file references: where the bundle directory is and which installed prefix the run is bound to
_PLAIN_INPUTS = ("bundle_dir", "install_prefix")
_POLICY = {"socket_path", "service_generation", "client_id", "max_frame_bytes", "bundle_sha256", "policy_sha256"}
_ATTEMPT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\Z")


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def identity_sha256(identity: dict) -> str:
    """The run identity as one hash: what the Host writes into the shard spec and into every task, and every shard recomputes."""
    return hashlib.sha256(canonical_json(identity)).hexdigest()


@dataclass(frozen=True)
class RolloutTaskInput:
    task_id: str
    root: Path
    document: dict
    inputs: object
    scene: dict
    shard_spec: dict


def _check_spec(spec):
    try:
        if (type(spec) is not dict or spec["workload_kind"] != "act_rollout"
                or any(type(spec[name]) is not str for name in ("campaign_id", "worker_id", "wave_id", "owned_root",
                                                               "simulation_session_id", "gpu_uuid"))
                or re.fullmatch(r"w[0-9]+", spec["worker_id"]) is None or type(spec["launch_generation"]) is not int
                or not _finite(spec["deadline_monotonic_s"]) or type(spec["rollout_identity"]) is not dict):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ValueError("ROLLOUT_SHARD_SPEC_INVALID") from None
    return spec


def _ref(document, name):
    ref = document["inputs"][name]
    validate_file_ref(ref)
    return Path(ref["path"])


def load_rollout_task(task, shard_spec, *, policy_socket, install_prefix, clock=time.monotonic):
    """Validate the assignment against the shard and the frozen originals; creates nothing."""
    if type(task) is not TaskSpec:
        raise ValueError("ROLLOUT_TASK_SPEC_INVALID")
    _check_spec(shard_spec)
    now = clock()
    if (shard_spec["deadline_monotonic_s"] <= now or task.deadline_monotonic_s <= now
            or task.deadline_monotonic_s > shard_spec["deadline_monotonic_s"]):
        raise ValueError("ROLLOUT_TASK_DEADLINE_INVALID")
    root = Path(shard_spec["owned_root"])
    try:
        verify_instance_environment(os.environ, session_id=shard_spec["simulation_session_id"])
        drift = os.environ.get(INSTANCE_ROOT_ENV) != str(root)
    except ValueError:
        drift = True
    if root.resolve(strict=True) != root or not root.is_dir() or drift:
        raise ValueError("ROLLOUT_TASK_ENVIRONMENT_DRIFT")
    if task.inputs_ref.path != str(root / "task-inputs" / (task.task_id + ".json")):
        raise ValueError("ROLLOUT_TASK_INPUT_LOCATION_INVALID")
    try:
        document = read_document(validate_file_ref(task.inputs_ref.model_dump()))
    except Exception as error:      # noqa: BLE001 - unreadable, duplicate keys, not an object: one input fault
        raise ValueError("ROLLOUT_TASK_INPUT_INVALID") from error
    try:
        if (set(document) != _FIELDS or document["schema_version"] != 1 or type(document["schema_version"]) is not int
                or document["kind"] != KIND or document["task_id"] != task.task_id or document["group"] not in GROUPS
                or type(document["trial"]) is not int or type(document["attempt_number"]) is not int
                or document["trial"] < 1 or document["attempt_number"] < 1
                or _ATTEMPT.fullmatch(document["attempt_id"]) is None or _ID.fullmatch(document["scene_id"]) is None
                or type(document["point_id"]) is not str or type(document["run_id"]) is not str
                or type(document["preconditions"]) is not dict
                or type(document["inputs"]) is not dict
                or not {*_REFS, *_PLAIN_INPUTS} <= set(document["inputs"]) <= {*_REFS, *_PLAIN_INPUTS, *_OPTIONAL_REFS}
                or document["inputs"]["install_prefix"] != str(install_prefix)
                or type(document["policy"]) is not dict or set(document["policy"]) != _POLICY or type(document["execution"]) is not dict
                or set(document["execution"]) != {"execution_prefix", "temporal_ensembling"}):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ValueError("ROLLOUT_TASK_INPUT_INVALID") from None
    for name in ("worker_id", "launch_generation", "wave_id"):
        if type(document[name]) is not type(shard_spec[name]) or document[name] != shard_spec[name]:
            raise ValueError("ROLLOUT_TASK_CONTEXT_MISMATCH")
    policy = document["policy"]
    if (policy["socket_path"] != str(policy_socket) or type(policy["service_generation"]) is not str
            or not policy["service_generation"] or type(policy["max_frame_bytes"]) is not int or policy["max_frame_bytes"] <= 0
            or policy["bundle_sha256"] != document["inputs"]["bundle_json"]["sha256"]
            or policy["policy_sha256"] != shard_spec["rollout_identity"]["policy_sha256"]
            or policy["bundle_sha256"] != shard_spec["rollout_identity"]["bundle_sha256"]):
        raise ValueError("ROLLOUT_POLICY_ENDPOINT_INVALID")
    files = {name: _ref(document, name) for name in _REFS}
    optional = {name: (None if document["inputs"].get(name) is None else _ref(document, name)) for name in _OPTIONAL_REFS}
    bundle_dir = Path(document["inputs"]["bundle_dir"])
    if files["bundle_json"] != bundle_dir / "bundle.json":
        raise ValueError("ROLLOUT_TASK_INPUT_INVALID")
    execution = document["execution"]
    arguments = SimpleNamespace(
        inputs_manifest=files["inputs_manifest"], rollout_config=files["rollout_config"], runtime_config=files["runtime_config"],
        scenes=files["scenes"], bundle_dir=bundle_dir, contact_activation_receipt=optional["contact_activation_receipt"],
        contact_proposal=optional["contact_proposal"], scene_variant=optional["scene_variant"],
        install_prefix=document["inputs"]["install_prefix"],
        execution_prefix=execution["execution_prefix"], temporal_ensembling=execution["temporal_ensembling"])
    return arguments, document, root


def bind_inputs(arguments, document, shard_spec, *, inputs_loader=load_inputs):
    """Load the frozen inputs and prove they are the ones the run was started with."""
    inputs = inputs_loader(arguments)
    digest = identity_sha256(inputs.identity)
    expected = shard_spec["rollout_identity"]
    if (digest != document["run_identity_sha256"] or digest != expected["run_identity_sha256"]
            or inputs.identity.get("scenes_sha256") != expected["scenes_sha256"]
            or inputs.identity.get("policy_sha256") != expected["policy_sha256"]
            or inputs.identity.get("bundle_sha256") != expected["bundle_sha256"]):
        raise ValueError("ROLLOUT_TASK_IDENTITY_MISMATCH")
    group = inputs.scenes.get("groups", {}).get(document["group"]) or []
    scene = next((item for item in group if item["scene_id"] == document["point_id"]), None)
    if scene is None:
        raise ValueError("ROLLOUT_TASK_SCENE_UNKNOWN")
    return inputs, scene


def rollout_resources(shard_spec, *, task_root):
    """The shard's `WorkerResources` for one task: task data under `task_root`, everything else under the owned root."""
    from so101_demo.parallel_batch.resource_allocation.models import WorkerResources

    _check_spec(shard_spec)
    root = Path(shard_spec["owned_root"])
    session = shard_spec["simulation_session_id"]
    temporary = root / "tmp"
    return WorkerResources(worker_id=shard_spec["worker_id"], slot_index=int(shard_spec["worker_id"][1:]),
                           generation=shard_spec["launch_generation"], ros_domain_id=ACT_INSTANCE_ROS_DOMAIN_ID,
                           simulation_port=session, bridge_port=session, gz_partition=session, session_id=session,
                           controller_namespace=ACT_INSTANCE_ROS_NAMESPACE, render_backend="egl", render_context_id=session,
                           render_context_namespace=temporary / "render", virtual_display="not_applicable",
                           ros_home=temporary / "ros-home", ros_log_dir=root / "ros-logs", temp_dir=temporary,
                           socket_namespace=root / "control", socket_path=root / "control" / "worker-unused.sock",
                           worker_root=Path(task_root), environment=dict(os.environ))


def _check_stack(stack, spec, root):
    launch = getattr(stack, "launch", None)
    if (launch is None or launch.ros_domain_id != ACT_INSTANCE_ROS_DOMAIN_ID or launch.session_id != spec["simulation_session_id"]
            or Path(launch.evidence_root) != root / "stack"):
        raise ValueError("ROLLOUT_BORROWED_STACK_MISMATCH")
    process = getattr(stack, "process", None)
    if process is not None and process.poll() is not None:
        raise ValueError("ROLLOUT_STACK_NOT_RUNNING")


class RolloutEdges:
    """The external effects of one task, each replaceable only by a controlled double; the defaults are the production ones."""

    def __init__(self, **overrides):
        self.inputs_loader = load_inputs
        self.episode_runner = run_episode
        self.client_factory = None            # None: the real PolicyClient
        self.ports_factory = None             # None: the real ports over ROS (see `real_ports`)
        self.policy_ready_check = True
        for name, value in overrides.items():
            if not hasattr(self, name):
                raise ValueError("ROLLOUT_EDGE_UNKNOWN: " + name)
            setattr(self, name, value)


class RolloutTaskExecution:
    """One task over its constructed parts: `run` is the whole episode, `request_stop` and `shutdown_owned` end it."""

    def __init__(self, *, task_input, files, ports, inference, transport, runtime, binding, episode_runner, lease, clock,
                 task_dir, recovery_timeout_s):
        self.task_input, self.files, self.ports = task_input, files, ports
        self.inference, self.transport, self.runtime, self.binding = inference, transport, runtime, binding
        self.episode_runner, self.lease, self.clock, self.task_dir = episode_runner, lease, clock, task_dir
        self.recovery_timeout_s = recovery_timeout_s
        self.retire_proofs = None
        self.result = None
        self._lock = threading.Lock()
        self._run_started = False
        self._run_done = threading.Event()
        self._stop_requested = threading.Event()
        self._shutdown_lock = threading.Lock()
        self._shutdown_result = None

    def run(self):
        with self._lock:
            if self._run_started:
                raise RuntimeError("ROLLOUT_TASK_RUN_ALREADY_STARTED")
            self._run_started = True
        document = self.task_input.document
        inputs, scene, attempt_id = self.task_input.inputs, self.task_input.scene, document["attempt_id"]
        try:
            if self._stop_requested.is_set():
                raise RuntimeError("ROLLOUT_TASK_STOP_REQUESTED")
            started = self.clock()
            try:
                result = self.episode_runner(scene=scene, attempt_id=attempt_id, ports=self.ports, settings=inputs.settings,
                                             snapshot_targets=inputs.snapshot_targets, endpoint_policy=inputs.endpoint_policy,
                                             sink=self.files, execution=inputs.execution)
            except Exception as error:      # noqa: BLE001 - the machine reports faults itself; anything else is still a fault
                result = _invalid_result(scene, attempt_id, error)
            options = SimpleNamespace(run_id=document["run_id"])
            names = self.files.seal(episode_document(inputs=inputs, options=options, scene=scene, attempt_id=attempt_id,
                                                     result=result, preconditions=document["preconditions"]), result)
            self.result = task_result(document, result, names, wall_s=self.clock() - started)
            return self.result
        finally:
            self._run_done.set()

    def request_stop(self):
        """Non-blocking and idempotent: the controllers are told to stop; the episode's own retirement still runs."""
        self._stop_requested.set()
        try:
            self.runtime.cancel_motion(self.lease)
        except Exception:       # noqa: BLE001 - the shutdown proof below reports what is left
            pass

    def shutdown_owned(self):
        """Single-flight; True only when the episode has ended and every owned participant is closed. Never raises."""
        with self._shutdown_lock:
            if self._shutdown_result is True:
                return True
            try:
                proven = self._shutdown() is True
            except BaseException:       # noqa: BLE001
                proven = False
            if proven:
                self._shutdown_result = True
            return proven

    def _shutdown(self):
        proofs = {}
        if self._run_started:
            proofs["episode_ended"] = self._run_done.wait(self.recovery_timeout_s)
            if not proofs["episode_ended"]:
                self.retire_proofs = proofs
                return False
        for name, step in (("inference_closed", self.inference.close), ("runtime_closed", self.runtime.close_runtime),
                           ("binding_closed", self.binding.shutdown)):
            try:
                outcome = step()
                proofs[name] = outcome is not False
            except Exception:       # noqa: BLE001
                proofs[name] = False
        if self._run_started:
            result = self.result or {}
            # the episode's own retirement (controllers cancelled and confirmed idle, recorder closed) is part of its result
            proofs["episode_retired"] = result.get("retire_errors") in ([], None) if result else False
        self.retire_proofs = proofs
        return all(value is True for value in proofs.values())


def task_result(document, result, names, *, wall_s):
    """The compact task result the Host journals: the verdict and where the episode evidence is (relative to the task directory)."""
    counts = result.get("counts") or {}
    summary = {
        "schema_version": 1, "kind": RESULT_KIND, "task_id": document["task_id"], "scene_id": document["scene_id"],
        "point_id": document["point_id"], "group": document["group"], "trial": document["trial"],
        "attempt_number": document["attempt_number"], "attempt_id": document["attempt_id"],
        "verdict": result["verdict"], "done": result["done"], "reason": result["reason"], "status": result["status"],
        "retire_errors": list(result.get("retire_errors") or []), "elapsed_wall_s": result["timing"]["wall_s"],
        "task_wall_s": round(wall_s, 6), "counts": counts, "clamped_steps": counts.get("clamped_steps", 0),
        "evidence": [f"episode/{name}" for name in names],
        "goal_response": result.get("goal_response"),
        #: the policy service's account of this episode's replies: counts by outcome, queue wait, model time, round trip
        "service": result.get("service"),
        "stop_confirmed": (result.get("stop") or {}).get("confirmed") is True}
    return summary


_SHARD_RUNTIME = {}
_SHARD_RUNTIME_LOCK = threading.Lock()


def shard_runtime():
    """The runtime settings every shard process shares with the native command (T0b): once per process, `gc.collect()` + `gc.freeze()`
    (the shard's warm-up: the libraries are loaded and the first task is about to start) and the stall monitor (GC callbacks, a 1 ms
    heartbeat, CPU accounting), which each episode summarises into `stall_attribution`. The per-episode freeze is done by the ports at the
    reset, before the physics resume (`NativeEpisodePorts.resume_physics`)."""

    from so101_demo.act import runtime_memory
    from so101_demo.act.stall_diagnostics import StallMonitor

    with _SHARD_RUNTIME_LOCK:
        if not _SHARD_RUNTIME:
            warm_up = runtime_memory.freeze_heap()
            monitor = StallMonitor()
            monitor.start()
            _SHARD_RUNTIME.update(freeze_heap=runtime_memory.freeze_heap, stall_monitor=monitor, warm_up_heap=warm_up)
        return dict(_SHARD_RUNTIME)


def stop_shard_runtime():
    """Stop the monitor of this process (tests; a shard just exits). Idempotent."""

    with _SHARD_RUNTIME_LOCK:
        monitor = _SHARD_RUNTIME.pop("stall_monitor", None)
        _SHARD_RUNTIME.clear()
    if monitor is not None:
        monitor.stop()


def real_ports(*, shard_spec, document, inputs, scene, stack, task_dir, files, policy_client, clock):
    """The production ports of one episode: the shard runtime, the ROS binding and the recorder; mirrors `NativeComposition`."""
    from so101_demo.act.rig_profile import rig_from_observation
    from so101_demo.adapters.act.inference_process import ActInferenceProcess
    from so101_demo.adapters.act.rollout_ros import RclpyBinding
    from so101_demo.parallel_batch.contracts.common import RunMode
    from so101_demo.parallel_batch.contracts.identity import LeaseIdentity
    from so101_demo.runtime.act_policy.client import RemotePolicy, SocketInferenceTransport
    from so101_demo.runtime.act_ros_runtime import ActRosRuntimePorts

    rig = rig_from_observation(inputs.observation["cameras"], inputs.observation["state_dim"])
    if getattr(stack.launch, "rig", rig.rig) != rig.rig:
        raise ValueError("ROLLOUT_BORROWED_STACK_RIG_MISMATCH")
    extras = shard_runtime()
    resources = rollout_resources(shard_spec, task_root=task_dir)
    inference_config = inputs.runtime_config["inference"]
    # the client stops waiting for a reply when the boundary would refuse it as too old (and never after the request timeout)
    transport = SocketInferenceTransport(policy_client, request_timeout_s=inference_config["request_timeout_s"],
                                         max_reply_age_s=inference_config["max_reply_age_s"])
    inference = ActInferenceProcess(config=inputs.runtime_config, transport=transport, clock=time.monotonic)
    runner = make_policy_runner(inputs, RemotePolicy())
    runtime = ActRosRuntimePorts(resources, catalog={scene["scene_id"]: {"cup_position_world_m": scene["cup_position_world_m"]}},
                                 config=None, mode=RunMode.EXECUTE, broker_generation=resources.generation,
                                 dependencies={"act_profile": True, "rig": rig})
    binding = RclpyBinding()
    issued = time.monotonic()
    lease = LeaseIdentity(
        batch_id=shard_spec["campaign_id"] + "-" + shard_spec["wave_id"], coordinator_epoch=1, worker_id=shard_spec["worker_id"],
        worker_generation=shard_spec["launch_generation"], point_id=scene["scene_id"], attempt_id=document["attempt_id"],
        lease_generation=1, lease_issued_monotonic_s=issued,
        lease_deadline_monotonic_s=issued + inputs.settings.execution_deadline_s + 600.0)
    pilot = pilot_factory_for(environment=dict(os.environ), ready_timeout_s=float(inputs.recorder_policy["ready_timeout_s"]),
                              rig_profile=stack.launch.rig_profile)
    ports = NativeEpisodePorts(runtime=runtime, lease=lease, scene=scene, directory=files.directory, inputs=inputs,
                               environment=dict(os.environ), binding=binding, runner=runner, inference=inference,
                               transport=transport, pilot_factory=pilot,
                               # as natively: the recorder works beside the episode (its process manifest stays there) and its raw
                               # directory is moved into the episode directory when the recorder has closed the bag
                               recording_dir=Path(task_dir) / "recordings" / document["attempt_id"],
                               stall_monitor=extras["stall_monitor"], freeze_heap=extras["freeze_heap"])
    return SimpleNamespace(ports=ports, inference=inference, transport=transport, runtime=runtime, binding=binding, lease=lease)


def build_rollout_task(task, *, stack, shard_spec, output_root, policy_socket, install_prefix, clock=time.monotonic,
                       edges=None, recovery_timeout_s=60.0):
    """Validate, then reserve the task directory and build the episode's parts; starts no process and sends no command."""
    edges = edges or RolloutEdges()
    arguments, document, root = load_rollout_task(task, shard_spec, policy_socket=policy_socket,
                                                  install_prefix=install_prefix, clock=clock)
    _check_stack(stack, shard_spec, root)
    inputs, scene = bind_inputs(arguments, document, shard_spec, inputs_loader=edges.inputs_loader)
    policy = document["policy"]
    if edges.client_factory is None:
        from so101_demo.runtime.act_policy.client import PolicyClient
        client = PolicyClient(socket_path=policy["socket_path"], client_id=policy["client_id"],
                              bundle_sha256=policy["bundle_sha256"], policy_sha256=policy["policy_sha256"],
                              cameras=tuple(inputs.observation["cameras"]), max_frame_bytes=policy["max_frame_bytes"],
                              service_generation=policy["service_generation"])
    else:
        client = edges.client_factory(policy, inputs)
    if edges.policy_ready_check:
        ready = client.query("policy_ready_query")
        if (ready.get("ready") is not True or ready["bundle_sha256"] != policy["bundle_sha256"]
                or ready["policy_sha256"] != policy["policy_sha256"]
                or list(ready["cameras"]) != list(inputs.observation["cameras"])
                or ready["state_dim"] != inputs.observation["state_dim"]
                or list(ready["image_shape"]) != list(inputs.observation["image_shape"])):
            raise ValueError("ROLLOUT_POLICY_SERVICE_MISMATCH")
    task_dir = reserve_task_output(output_root, task.task_id)
    files = EpisodeFiles(task_dir / "episode")
    task_input = RolloutTaskInput(task_id=task.task_id, root=root, document=document, inputs=inputs, scene=scene,
                                  shard_spec=shard_spec)
    factory = edges.ports_factory or real_ports
    parts = factory(shard_spec=shard_spec, document=document, inputs=inputs, scene=scene, stack=stack, task_dir=task_dir,
                    files=files, policy_client=client, clock=clock)
    return RolloutTaskExecution(task_input=task_input, files=files, ports=parts.ports, inference=parts.inference,
                                transport=parts.transport, runtime=parts.runtime, binding=parts.binding,
                                episode_runner=edges.episode_runner, lease=parts.lease, clock=clock, task_dir=task_dir,
                                recovery_timeout_s=recovery_timeout_s)
