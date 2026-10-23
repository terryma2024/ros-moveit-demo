"""CLI: run the closed-loop rollouts of one policy bundle on N container shards at once.

Design: docs/superpowers/specs/2026-10-22-so101-act-parallel-rollout-design.md (P1 to P7). The native command
(`act_rollout_native`) stays the single-stack reference. This command runs the same episode (the same state machine, ports, recorder,
endpoint rule and evidence files) in `--shards` private containers at once, as the collection does, and serves their policy
requests from ONE policy service on the Host, in the training interpreter (`act_policy_service`).

    queue         every (point, trial) of the group, trial by trial; an INVALID attempt is queued again on fresh shards
                  up to `--max-invalid-retries` more attempts, and is reported apart from the policy's results
    waves         the collection's coordinator: all shards of a wave are READY before the first task is assigned, one task at a
                  time per shard, `--max-concurrent-episodes` episodes at once, `--min-assignment-gap-s` between assignments
    stop          every container is inspected again, its logs are saved, it is removed and proven absent (the receipt); the
                  policy service is stopped by SIGTERM with its own stop proof

Like the native command it bypasses unified admission, so it proves its own preconditions and records them: no container, the unified
store IDLE with no GPU lease and no active ACT slot, no ACT instance process, and no compute process on the GPU - and, once the
policy service is up, that the only compute process is the service itself. A ROS graph check is not needed: each shard is its own
network and IPC namespace.

Layout under `<evidence-root>/<run-id>/` (all of it new):

    run.json  summary.json  table.md           the run's inputs and preconditions, the results, the point x trial x verdict view
    <group>/act-runs.jsonl  invalid-runs.jsonl  the native command's run rows (one per valid attempt, one per INVALID attempt)
    wave-N/wNN/gM/output/tasks/<task>/episode/  episode.json, steps.jsonl, world.jsonl, events.jsonl, endpoint.json,
                                                stop-proof.json, raw/   - the native episode directory, written by the shard
    host/                                       wave verification, task journals, launch registry, receipts, cleanup record
    services/policy/                            the policy service's launch, logs, process record, requests and stop proof

Exit codes: 0 every attempt gave a result and every stop is proven; 1 some (point, trial) never gave a result; 2 refused before
anything started; 3 a stop (a shard, the policy service, a container removal) is not proven; 4 the policy service or the first wave did
not start.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Callable

from so101_demo.act.rollout_execution import DEFAULT_ENSEMBLING_M
from so101_demo.act.rollout_shared import load_inputs
from so101_demo.runtime.act_rollout.coordinator import RolloutCoordinator
from so101_demo.runtime.act_rollout.owner import EXIT_REFUSED, EXIT_RUN_FAULT, RolloutCampaignOwner
from so101_demo.runtime.act_rollout.plan import build_units
from so101_demo.runtime.act_rollout.policy_service import PolicyServiceOwner
from so101_demo.runtime.act_rollout.shard_launcher import WORKLOAD_KIND, RolloutShardLauncher
from so101_demo.runtime.act_rollout.task_builder import identity_sha256
from so101_demo.runtime.container_campaign.mount_build import mount_from_config
from so101_demo.runtime.container_campaign.paths import CONTAINER_POLICY_SOCKET, make_campaign_paths
from so101_demo.runtime.container_campaign.registry import ContainerLaunchRegistry
from so101_demo.runtime.container_campaign.task_control import ContainerTaskControl
from so101_demo.runtime.container_campaign.service_owner import _docker
from so101_demo.runtime.container_campaign.shard_owner import read_container_namespace
from so101_demo.runtime.inference.config import calibration_runtime_hash, load_campaign_config
from so101_teleop.unified.contracts import AdmittedCampaignContext

PRECONDITIONS = ("no_container", "unified_store_idle", "no_instance_process", "no_gpu_process")
GROUPS = ("rollout_standard", "rollout_validation", "rollout_test", "rollout_extrapolation")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_GPU = re.compile(r"GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z")


class Refused(ValueError):
    """The run cannot start: an argument, an input or a precondition."""


@dataclass
class Edges:
    """The external effects of a run, each replaceable only by a controlled double; `None` is the production default."""

    probes: dict | None = None
    gpu_probe: Callable | None = None
    docker_runner: Callable | None = None
    namespace_reader: Callable | None = None
    control_factory: Callable | None = None
    inputs_loader: Callable | None = None
    policy_command: list | None = None
    popen: Callable | None = None
    identity_of: Callable | None = None
    signal_process: Callable | None = None
    health_probe: Callable | None = None
    inspect_container: Callable | None = None
    launcher_factory: Callable | None = None
    environ: dict | None = None
    clock: Callable = time.monotonic
    sleep: Callable = asyncio.sleep       # the coordinator's polling sleep (a test advances a fake clock with it)
    monitor_interval_s: float = 1.0       # how often the policy service's health and the deadline are looked at


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="act_rollout_parallel", description=__doc__, allow_abbrev=False,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--evidence-root", type=Path, required=True, help="the registered evidence root; the run is a new directory in it")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--campaign-config", type=Path, required=True,
                        help="the container campaign config: images (or mount build), GPU and controlled runtime")
    parser.add_argument("--parallel-runtime-config", type=Path, required=True,
                        help="the parallel runtime (heartbeat, start and recovery bounds) the shards and the coordinator run under")
    parser.add_argument("--group", choices=GROUPS, required=True)
    parser.add_argument("--scenes", type=Path, required=True, help="the ACT_ROLLOUT_SCENES list")
    parser.add_argument("--scene-id", dest="scene_ids", action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--trials", type=int, default=1, help="how many trials of each point (a label: there are no episode seeds)")
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--inputs-manifest", type=Path, required=True, help="the frozen inputs manifest of the gated install")
    parser.add_argument("--runtime-config", type=Path, required=True, help="config/act/runtime.yaml")
    parser.add_argument("--rollout-config", type=Path, required=True, help="config/act/rollout.yaml")
    parser.add_argument("--contact-activation-receipt", type=Path)
    parser.add_argument("--contact-proposal", type=Path)
    parser.add_argument("--scene-variant", type=Path, default=None,
                        help="an evaluation-only scene variant (a whitelisted visual edit of the nominal scene, "
                             "`act/scene_variant.py`); bound into the run identity, run.json and every episode.json")
    parser.add_argument("--unified-state-root", type=Path, required=True)
    parser.add_argument("--execution-prefix", type=int, default=None, metavar="N")
    parser.add_argument("--temporal-ensembling", type=float, nargs="?", const=DEFAULT_ENSEMBLING_M, default=None, metavar="M")
    parser.add_argument("--max-invalid-retries", type=int, default=1)
    # runtime parameters: they change when the run is fast, not what an attempt means; the evidence records them
    parser.add_argument("--shards", type=int, default=1, help="shards (containers) per wave, at most one wave at a time")
    parser.add_argument("--max-concurrent-episodes", type=int, default=None,
                        help="episodes recording at once (the recording cap); default: every shard")
    parser.add_argument("--max-tasks-in-flight", type=int, default=None)
    parser.add_argument("--min-assignment-gap-s", type=float, default=0.0,
                        help="the least wall time between two task assignments across the shards")
    parser.add_argument("--task-timeout-s", type=float, default=1800.0, help="the deadline of one task, from its assignment")
    parser.add_argument("--campaign-timeout-s", type=float, default=14400.0)
    parser.add_argument("--policy-python", type=Path, required=True, help="the training interpreter (lerobot, torch)")
    parser.add_argument("--policy-pythonpath", type=Path, default=None,
                        help="where that interpreter finds so101_demo; default: the mounted build's site-packages")
    parser.add_argument("--policy-max-inflight", type=int, default=None, help="default: shards + 2")
    parser.add_argument("--policy-queue-timeout-s", type=float, default=1.0)
    parser.add_argument("--policy-inference-timeout-s", type=float, default=0.5)
    parser.add_argument("--policy-warm-up-calls", type=int, default=3)
    parser.add_argument("--policy-max-consecutive-errors", type=int, default=3,
                        help="stop the run as a policy service fault after this many replies in a row that were errors")
    parser.add_argument("--policy-start-timeout-s", type=float, default=300.0)
    parser.add_argument("--policy-stop-timeout-s", type=float, default=30.0)
    return parser


# ---- preconditions ---------------------------------------------------------------------------------------------------------


def check_preconditions(probes: dict) -> dict:
    """Run every probe in order; each returns ``(ok, detail)``. A probe that fails, raises or is absent refuses the run."""
    evidence = {}
    for name in PRECONDITIONS:
        probe = probes.get(name)
        if not callable(probe):
            raise Refused(f"ROLLOUT_PRECONDITION_UNPROVEN: {name}: no probe")
        try:
            ok, detail = probe()
        except Exception as error:      # noqa: BLE001 - a probe that cannot answer is not a pass
            raise Refused(f"ROLLOUT_PRECONDITION_UNPROVEN: {name}: {error}") from error
        if ok is not True:
            raise Refused(f"ROLLOUT_PRECONDITION_FAILED: {name}: {detail}")
        evidence[name] = {"ok": True, "detail": detail}
    return evidence


def gpu_processes(gpu_uuid, *, run=subprocess.run):
    """``(none, ["pid, name", ...])``: the compute processes on the configured GPU only.

    Another GPU's processes are not this run's business, so `nvidia-smi` is asked for the device of each row and the rows of other
    devices are dropped. A device name that cannot be read is an error, never "none"."""
    result = run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,process_name", "--format=csv,noheader"],
                 capture_output=True, text=True, timeout=30, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"nvidia-smi failed: {str(result.stderr).strip()[:200]}")
    rows = []
    for line in str(result.stdout).splitlines():
        if not line.strip():
            continue
        device, _separator, rest = line.partition(",")
        if not rest.strip():
            raise RuntimeError(f"nvidia-smi row without a device: {line[:100]}")
        if device.strip().lower() == gpu_uuid.lower():
            rows.append(rest.strip())
    return (not rows), rows


def default_probes(unified_state_root, gpu_probe) -> dict:
    from so101_demo.cli.act_rollout_native import container_probe, instance_process_probe, unified_store_probe

    return {"no_container": container_probe, "unified_store_idle": lambda: unified_store_probe(unified_state_root),
            "no_instance_process": instance_process_probe, "no_gpu_process": gpu_probe}


def only_own_gpu_process(probe, policy_pid):
    """After the service is up the compute processes on the GPU are exactly the service (nvidia-smi: ``pid, process_name``)."""
    _free, processes = probe()
    pids = {int(str(line).split(",")[0].strip()) for line in processes}
    return pids <= {policy_pid}, list(processes)


# ---- the run ---------------------------------------------------------------------------------------------------------------


def _sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _ref(path) -> dict:
    return {"path": str(Path(path)), "sha256": _sha256(path)}


def _stable_host_id() -> str:
    try:
        return Path("/etc/machine-id").read_text().strip() or "unknown-host"
    except OSError:
        return "unknown-host"


def check_arguments(args):
    if _ID.fullmatch(args.run_id) is None:
        raise Refused("ROLLOUT_RUN_ID_INVALID")
    for name in ("evidence_root", "campaign_config", "parallel_runtime_config", "scenes", "bundle_dir", "inputs_manifest",
                 "runtime_config", "rollout_config", "unified_state_root", "policy_python"):
        path = getattr(args, name)
        if not path.is_absolute() or ".." in path.parts:
            raise Refused(f"ROLLOUT_PATH_NOT_ABSOLUTE: --{name.replace('_', '-')}")
    if not args.evidence_root.is_dir() or args.evidence_root.is_symlink():
        raise Refused("ROLLOUT_EVIDENCE_ROOT_INVALID")
    variant = getattr(args, "scene_variant", None)
    if variant is not None and (not Path(variant).is_absolute() or ".." in Path(variant).parts or not Path(variant).is_file()
                                or Path(variant).is_symlink()):
        raise Refused("ROLLOUT_SCENE_VARIANT_INVALID")
    if args.shards < 1 or args.trials < 1 or args.max_invalid_retries < 0:
        raise Refused("ROLLOUT_COUNTS_INVALID")
    for name in ("max_concurrent_episodes", "max_tasks_in_flight", "limit", "policy_max_inflight", "policy_max_consecutive_errors"):
        value = getattr(args, name)
        if value is not None and value < 1:
            raise Refused(f"ROLLOUT_COUNTS_INVALID: {name}")
    for name in ("min_assignment_gap_s",):
        if getattr(args, name) < 0:
            raise Refused(f"ROLLOUT_COUNTS_INVALID: {name}")
    for name in ("task_timeout_s", "campaign_timeout_s", "policy_start_timeout_s", "policy_stop_timeout_s",
                 "policy_queue_timeout_s", "policy_inference_timeout_s"):
        if not 0 < getattr(args, name) < float("inf"):
            raise Refused(f"ROLLOUT_TIMING_INVALID: {name}")


def approved_inputs(args, config, mount, parallel_runtime_path):
    """The read-only inputs the shards need at their host paths, without anything the mounted build already shows."""
    wanted = [Path(args.inputs_manifest).parent, Path(args.bundle_dir), Path(args.scenes), Path(args.runtime_config),
              Path(args.rollout_config), Path(parallel_runtime_path), Path(config["controlled_runtime"]["path"])]
    for name in ("contact_activation_receipt", "contact_proposal", "scene_variant"):
        if getattr(args, name, None) is not None:
            wanted.append(Path(getattr(args, name)))
    kept = []
    for path in dict.fromkeys(item.resolve(strict=True) for item in wanted):
        if path.is_relative_to(mount.root) or mount.root.is_relative_to(path):
            continue
        kept.append(path)
    return tuple(path for path in kept if not any(other != path and path.is_relative_to(other) and other.is_dir() for other in kept))


def rollout_description(args, inputs, *, run_id, install_prefix, preconditions, policy_generation, bundle_sha256):
    """What every task document is made of (`RolloutInstanceDispatch.task_document`)."""
    refs = {"inputs_manifest": _ref(args.inputs_manifest), "runtime_config": _ref(args.runtime_config),
            "rollout_config": _ref(args.rollout_config), "scenes": _ref(args.scenes),
            "bundle_json": _ref(Path(args.bundle_dir) / "bundle.json")}
    for name in ("contact_activation_receipt", "contact_proposal", "scene_variant"):
        if getattr(args, name, None) is not None:
            refs[name] = _ref(getattr(args, name))
    return {"run_id": run_id, "run_identity_sha256": identity_sha256(inputs.identity),
            "inputs": dict(refs, bundle_dir=str(args.bundle_dir), install_prefix=str(install_prefix)),
            "execution": {"execution_prefix": args.execution_prefix, "temporal_ensembling": args.temporal_ensembling},
            "policy": {"socket_path": str(CONTAINER_POLICY_SOCKET), "service_generation": policy_generation,
                       "max_frame_bytes": 16 * 1024 * 1024, "bundle_sha256": bundle_sha256,
                       "policy_sha256": inputs.identity["policy_sha256"]},
            "preconditions": preconditions, "task_timeout_s": args.task_timeout_s}


def prepare(args, edges):
    """Everything that can be refused is refused here, before the run directory exists."""
    from so101_demo.act.rig_profile import rig_from_observation

    check_arguments(args)
    config = load_campaign_config(args.campaign_config, roles=("teacher",), expected_sha256=_sha256(args.campaign_config))
    mount = mount_from_config(config)
    install_prefix = mount.package_prefix
    if not _GPU.fullmatch(config["gpu_uuid"]):
        raise Refused("ROLLOUT_GPU_UUID_INVALID")
    arguments = SimpleNamespace(**{name: getattr(args, name) for name in (
        "inputs_manifest", "rollout_config", "runtime_config", "scenes", "bundle_dir", "contact_activation_receipt",
        "contact_proposal", "execution_prefix", "temporal_ensembling", "scene_variant")}, install_prefix=install_prefix)
    try:
        inputs = (edges.inputs_loader or load_inputs)(arguments)
        units = build_units(inputs.scenes, group=args.group, scene_ids=args.scene_ids, trials=args.trials, limit=args.limit,
                            max_invalid_retries=args.max_invalid_retries)
    except (ValueError, OSError, KeyError) as error:
        raise Refused(f"ROLLOUT_INPUTS_REFUSED: {error}") from error
    if calibration_runtime_hash(config["controlled_runtime"]["path"]) != config["controlled_runtime"]["sha256"]:
        raise Refused("ROLLOUT_CONTROLLED_RUNTIME_DRIFT")
    rig = rig_from_observation(inputs.observation["cameras"], inputs.observation["state_dim"])
    pythonpath = args.policy_pythonpath or mount.package_prefix / "lib/python3.12/site-packages"
    if not Path(args.policy_python).is_file():
        raise Refused("ROLLOUT_POLICY_PYTHON_MISSING")
    return config, mount, install_prefix, inputs, units, rig, pythonpath


class FirstAssignmentMarker:
    """Marks the held-out group opened, once, when the first task has been sent to a shard (never before: a run that fails to start
    must not use up the one opening of `rollout_test` per policy). An uncertain exchange counts as sent."""

    def __init__(self, path, document):
        self.path, self.document, self.done = Path(path), document, False

    def __call__(self):
        if not self.done:
            self.done = True
            self.path.parent.mkdir(mode=0o700, exist_ok=True)
            self.path.write_text(json.dumps(self.document) + "\n")

    def wrap(self, factory):
        marker = self

        class MarkingControl:
            def __init__(self, control):
                self._control = control

            def __getattr__(self, name):
                return getattr(self._control, name)

            async def assign_task(self, task):
                try:
                    return await self._control.assign_task(task)
                finally:
                    marker()
        return lambda shard: MarkingControl(factory(shard))


def run(args, edges: Edges, *, log=print) -> int:
    """Refusals (`Refused`, exit 2) come only from `prepare` and the preconditions, before anything exists; once the run directory
    exists, any other failure is exit 6 and the stops are proven by the owner."""
    config, mount, install_prefix, inputs, units, rig, pythonpath = prepare(args, edges)
    policy_sha = inputs.identity["policy_sha256"]
    marker = None
    if args.group == "rollout_test":
        marker = FirstAssignmentMarker(Path(args.evidence_root) / "rollout-test-opened" / f"{policy_sha[:12]}.json",
                                       {"policy_sha256": policy_sha, "run_id": args.run_id, "units": len(units)})
        if marker.path.exists():
            raise Refused("ROLLOUT_TEST_ALREADY_OPENED")
    gpu_probe = edges.gpu_probe or (lambda: gpu_processes(config["gpu_uuid"]))
    probes = edges.probes or default_probes(args.unified_state_root, gpu_probe)
    preconditions = check_preconditions(probes)
    try:
        return _run_started(args, edges, log, config, mount, install_prefix, inputs, units, rig, pythonpath, marker, probes,
                            gpu_probe, preconditions)
    except Exception as error:      # noqa: BLE001 - the directory exists: a run fault, not a refusal
        print(f"ROLLOUT_RUN_FAULT: {type(error).__name__}: {error}", file=sys.stderr)
        return EXIT_RUN_FAULT


def _run_started(args, edges, log, config, mount, install_prefix, inputs, units, rig, pythonpath, marker, probes, gpu_probe,
                 preconditions):
    policy_sha = inputs.identity["policy_sha256"]
    bundle_sha256 = inputs.identity["bundle_sha256"]
    paths = make_campaign_paths(args.evidence_root, args.run_id)
    run_root = paths["run"]
    group_root = run_root / args.group
    group_root.mkdir(mode=0o700)
    parallel_runtime = _ref(args.parallel_runtime_config)
    from so101_demo.cli.mujoco_batch.request import _load_runtime_config
    from so101_demo.runtime.inference.config import validate_file_ref

    runtime = _load_runtime_config(validate_file_ref(parallel_runtime))
    now = edges.clock()
    config_sha = _sha256(args.campaign_config)
    context = AdmittedCampaignContext(
        campaign_id=args.run_id, operation_id=args.run_id, workload_kind=WORKLOAD_KIND, service_epoch=secrets.token_hex(16),
        execution_generation=1, stable_host_id=_stable_host_id(), physical_gpu_uuid=config["gpu_uuid"],
        worker_count=args.shards, source_sha256=config_sha, manifest_sha256=inputs.identity["scenes_sha256"],
        runtime_config_sha256=config["controlled_runtime"]["sha256"], collection_config_sha256=identity_sha256(inputs.identity),
        contact_policy_fingerprint=policy_sha,
        domain_session_map_sha256=hashlib.sha256(json.dumps(list(range(args.shards))).encode()).hexdigest(),
        resource_binding_id="rollout-self-admitted", evidence_root=str(run_root), admitted_at_monotonic_s=now,
        deadline_monotonic_s=now + args.campaign_timeout_s, registered_evidence_root=str(args.evidence_root),
        campaign_config_path=str(args.campaign_config), campaign_config_sha256=config_sha)
    generation = f"{args.run_id}-policy"
    description = rollout_description(args, inputs, run_id=args.run_id, install_prefix=install_prefix,
                                      preconditions=preconditions, policy_generation=generation, bundle_sha256=bundle_sha256)
    runtime_values = {"shards": args.shards, "trials": args.trials, "max_concurrent_episodes": args.max_concurrent_episodes,
                      "max_tasks_in_flight": args.max_tasks_in_flight, "min_assignment_gap_s": args.min_assignment_gap_s,
                      "task_timeout_s": args.task_timeout_s, "campaign_timeout_s": args.campaign_timeout_s,
                      "max_invalid_retries": args.max_invalid_retries}
    runtime_settings = {"gc_freeze": True, "stall_monitor": True,
                        "gc_freeze_points": ["the shard's first task", "each episode reset, before the physics resume"]}
    header = {"identity": dict(inputs.identity), "runtime_settings": runtime_settings, "run_identity_sha256": description["run_identity_sha256"],
              "execution": inputs.execution.document() if inputs.execution is not None else None,
              "runtime": runtime_values, "preconditions": preconditions, "install_prefix": str(install_prefix),
              "mount_build": mount.document(), "rig_profile_sha256": rig.profile_sha256,
              "gpu_uuid": config["gpu_uuid"], "campaign_config_sha256": config_sha}
    if inputs.scene_variant is not None:       # only a variant run has the key: a nominal run.json is unchanged
        header["scene_variant"] = dict(inputs.scene_variant)
    (run_root / "run.json").write_text(json.dumps(dict(header, schema_version=1, kind="ACT_ROLLOUT_PARALLEL_RUN",
                                                       run_id=args.run_id, group=args.group,
                                                       units=[unit.unit_id for unit in units]), sort_keys=True, indent=1) + "\n")
    registry = ContainerLaunchRegistry(Path(paths["host"]) / "launches.sqlite3", create=True)
    docker = edges.docker_runner or _docker
    try:
        inspect = edges.inspect_container or _inspector(docker)
        launcher_arguments = dict(
            context=context, config=config, run=run_root, registry=registry, parallel_runtime=parallel_runtime,
            rollout_identity={"run_identity_sha256": description["run_identity_sha256"],
                              "scenes_sha256": inputs.identity["scenes_sha256"], "policy_sha256": policy_sha,
                              "bundle_sha256": bundle_sha256},
            rig_profile_sha256=rig.profile_sha256,
            approved_inputs=approved_inputs(args, config, mount, args.parallel_runtime_config), config_paths=(),
            docker_runner=docker, namespace_reader=edges.namespace_reader or read_container_namespace)
        if inputs.scene_variant is not None:
            from so101_demo.act.scene_variant_run import spec_entry
            launcher_arguments["scene_variant"] = spec_entry(inputs.scene_variant)
        launcher = (edges.launcher_factory or RolloutShardLauncher)(**launcher_arguments)
        from so101_demo.runtime.act_policy.client import PolicyClient
        from so101_demo.runtime.act_rollout.policy_service import service_health_probe

        health_probe = edges.health_probe or service_health_probe(
            PolicyClient(socket_path=run_root / "ipc" / "policy" / "policy.sock", client_id="host-health",
                         bundle_sha256=bundle_sha256, policy_sha256=policy_sha, cameras=tuple(inputs.observation["cameras"]),
                         max_frame_bytes=1 << 20, service_generation=generation),
            max_consecutive_errors=args.policy_max_consecutive_errors)
        optional = {name: value for name, value in (("popen", edges.popen), ("identity_of", edges.identity_of),
                                                    ("signal_process", edges.signal_process), ("environ", edges.environ))
                    if value is not None}
        policy = PolicyServiceOwner(
            run=run_root, python=args.policy_python, pythonpath=pythonpath, bundle_dir=args.bundle_dir, gpu_uuid=config["gpu_uuid"],
            generation=generation, expected={"bundle_sha256": bundle_sha256, "policy_sha256": policy_sha,
                                             "cameras": list(inputs.observation["cameras"]),
                                             "state_dim": inputs.observation["state_dim"],
                                             "image_shape": list(inputs.observation["image_shape"])},
            max_inflight=args.policy_max_inflight or args.shards + 2, queue_timeout_s=args.policy_queue_timeout_s,
            inference_timeout_s=args.policy_inference_timeout_s, warm_up_calls=args.policy_warm_up_calls,
            undeclared_cameras=tuple(_undeclared_cameras(args.rollout_config)), start_timeout_s=args.policy_start_timeout_s,
            stop_timeout_s=args.policy_stop_timeout_s, command=edges.policy_command, health_probe=health_probe, **optional)
        scene_manifest = _ref(args.scenes)
        control_factory = edges.control_factory or (lambda shard: ContainerTaskControl(owner=shard))
        if marker is not None:
            control_factory = marker.wrap(control_factory)

        def coordinator_factory(*, context, units):
            return RolloutCoordinator(rollout=description, units=units, context=context, config=runtime,
                                      scene_manifest=scene_manifest, max_recording_shards=args.max_concurrent_episodes,
                                      max_tasks_in_flight=args.max_tasks_in_flight, clock=edges.clock, sleep=edges.sleep,
                                      min_assignment_gap_s=args.min_assignment_gap_s or None, control_factory=control_factory)

        checks = []

        def gpu_check(owner):
            """On the configured GPU the only compute process is the policy service: after it starts and before every wave."""
            ok, processes = only_own_gpu_process(gpu_probe, owner.process.pid)
            checks.append({"only_the_policy_service": ok, "policy_pid": owner.process.pid, "processes": processes})
            (run_root / "host" / "gpu-checks.json").write_text(json.dumps(checks) + "\n")
            if not ok:
                raise Refused("ROLLOUT_PRECONDITION_FAILED: no_gpu_process: another compute process is on the GPU")

        owner = RolloutCampaignOwner(
            context=context, run=run_root, registry=registry, launcher=launcher, coordinator_factory=coordinator_factory,
            policy=policy, units=units, rollout=description, options=args, docker_runner=docker, inspect_container=inspect,
            clock=edges.clock, gpu_check=gpu_check, monitor_interval_s=edges.monitor_interval_s)

        async def drive():
            try:
                await owner.run()
            finally:
                cleanup = await owner.close()
            return cleanup

        cleanup = asyncio.run(drive())
        summary = owner.finish(cleanup, header=header)
    finally:
        registry.close()
    log(json.dumps({"run": str(run_root), "exit_code": summary["exit_code"], "totals": summary["totals"],
                    "fault": summary.get("fault")}, sort_keys=True))
    return summary["exit_code"]


def _undeclared_cameras(rollout_config_path):
    import yaml

    document = yaml.safe_load(Path(rollout_config_path).read_text())
    return document["undeclared_bundle_cameras"]


def _inspector(docker):
    def inspect(container_id):
        result = docker(["docker", "inspect", container_id])
        documents = json.loads(result.stdout) if result.returncode == 0 else None
        if type(documents) is not list or len(documents) != 1:
            raise ValueError("CONTAINER_INSPECT_UNREADABLE")
        return documents[0]
    return inspect


def main(argv=None, *, edges=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args, edges or Edges())
    except (Refused, ValueError, OSError) as error:
        print(f"ROLLOUT_REFUSED: {error}", file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
