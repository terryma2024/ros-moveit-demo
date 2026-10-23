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
from so101_demo.act.rollout_execution import DEFAULT_ENSEMBLING_M
# the pieces the parallel shards share with this command live in act/rollout_shared.py (moved unchanged); the names stay importable here
from so101_demo.act.rollout_shared import (  # noqa: F401
    EpisodeFiles, NativeEpisodePorts, RelocatedRecording, RolloutInputs, _execution_document, _invalid_result, _line, _plain,
    _sha256, _write_json, episode_document, load_inputs, make_policy_runner, pilot_factory_for, select_scenes, warm_up_policy)

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
        "execution": _execution_document(inputs), "runtime_used": inputs.runtime_used,
        "joint_limit_clamp_tolerance_rad": inputs.settings.joint_limit_clamp_tolerance_rad,
        "observation": {**inputs.observation, "cameras": list(inputs.observation["cameras"])},
        "calibration": inputs.substitution, "preconditions": preconditions,
        "max_invalid_retries": options.max_invalid_retries})
    composition = composition_factory(layout=layout, environment=environment, inputs=inputs, options=options)
    summary = {"inference_warm_up_s": getattr(composition, "warm_up_s", None), "exit_code": EXIT_OK, "done": 0,
               "verdicts": {}, "invalid_attempts": 0, "invalid_exhausted": [], "clamped_steps": 0,
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
                                        sink=files, execution=inputs.execution)
            except Exception as error:      # noqa: BLE001 - the machine reports faults itself; anything else is still a fault
                result = _invalid_result(scene, attempt_id, error)
            names = files.seal(episode_document(inputs=inputs, options=options, scene=scene, attempt_id=attempt_id,
                                                result=result, preconditions=preconditions), result)
            summary["clamped_steps"] += (result.get("counts") or {}).get("clamped_steps", 0)
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


class NativeComposition:
    """The real stack, runtime ports, policy and recorder of one run. Built after the environment is applied."""

    def __init__(self, *, layout, environment, inputs, options) -> None:
        from so101_demo.act.rig_profile import rig_from_observation
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
        self.warm_up_s = warm_up_policy(policy, inputs.observation)
        from so101_demo.act.stall_diagnostics import StallMonitor

        self.stall_monitor = StallMonitor()
        policy.span_sink = self.stall_monitor.record_span
        self.transport = ThreadInferenceTransport(policy.infer, span_sink=self.stall_monitor.record_span)
        self.stall_monitor.start()
        self.inference = ActInferenceProcess(config=inputs.runtime_config, transport=self.transport, clock=time.monotonic)
        self.runner = make_policy_runner(inputs, policy)
        # the rig the policy was trained on (its bundle's observation declaration) is the rig of the stack that runs it
        self.rig = rig_from_observation(inputs.observation["cameras"], inputs.observation["state_dim"])
        self.launch = instance_stack_launch({"simulation_session_id": self.session_id}, ros2=Path(options.ros2),
                                            stack_root=layout.stack_root, environment=environment, rig=self.rig)
        observer = Path(options.install_prefix) / "lib/so101_demo_py/act_stack_ready"
        _ready, _ready_check, self.stack = compose_stack(self.launch, observer)
        self.graph_probe = RosGraphClearProbe(self.launch, spin_time_s=3.0)
        self.resources = self._resources()
        catalog = {scene["scene_id"]: {"cup_position_world_m": scene["cup_position_world_m"]}
                   for scene in inputs.scenes["groups"][options.group]}
        self.runtime = ActRosRuntimePorts(self.resources, catalog=catalog, config=None, mode=RunMode.EXECUTE,
                                          broker_generation=self.resources.generation,
                                          dependencies={"act_profile": True, "rig": self.rig})
        self.binding = RclpyBinding()
        self.attempts = 0
        self._closed = False

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

    def pilot_factory(self):
        """The recorder factory of this run: the raw recorder records the rig the stack composes (its profile file, the same one
        the launch observes), so a side+wrist stack is recorded without head or neck topics."""

        return pilot_factory_for(environment=self.environment, ready_timeout_s=float(self.inputs.recorder_policy["ready_timeout_s"]),
                                 rig_profile=self.launch.rig_profile)

    def new_ports(self, scene, attempt_id, directory):
        from so101_demo.parallel_batch.contracts.identity import LeaseIdentity

        self.attempts += 1
        issued = time.monotonic()
        lease = LeaseIdentity(
            batch_id=self.options.run_id, coordinator_epoch=1, worker_id="w00", worker_generation=1,
            point_id=scene["scene_id"], attempt_id=attempt_id, lease_generation=self.attempts,
            lease_issued_monotonic_s=issued,
            lease_deadline_monotonic_s=issued + self.inputs.settings.execution_deadline_s + 600.0)

        pilot = self.pilot_factory()

        return NativeEpisodePorts(runtime=self.runtime, lease=lease, scene=scene, directory=directory, inputs=self.inputs,
                                  environment=self.environment, binding=self.binding, runner=self.runner,
                                  inference=self.inference, transport=self.transport, pilot_factory=pilot,
                                  recording_dir=self.layout.output_root / "recordings" / attempt_id,
                                  stall_monitor=self.stall_monitor)

    def stop(self) -> dict:
        import asyncio

        from so101_demo.runtime.container_campaign.native_stop import marker_survivors
        from so101_teleop.process_identity import read_identity

        errors = []
        # A faulted episode can leave the simulation paused (the reset pauses it); the controllers answer no cancel while it is,
        # so the stack's stop would never be proven. Releasing the pause is idempotent.
        resumed = None
        try:
            resumed = self.runtime.resume_physics(None, None) is True
        except Exception as error:      # noqa: BLE001
            errors.append(f"resume_physics: {type(error).__name__}: {error}")
        # this process's own ROS participants (the retained pause control, the rollout binding) must be gone before the stack's
        # graph is judged clear: they are nodes of the same domain
        try:
            self.close()
        except Exception as error:      # noqa: BLE001
            errors.append(f"close_own_ros: {type(error).__name__}: {error}")
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
                "marker_survivors": survivors, "graph_clear": graph_clear, "physics_resumed_before_stop": resumed,
                "retirement_receipt": str(receipt) if receipt.exists() else None,
                "confirmed": not errors and survivors == [] and graph_clear is True}

    def close(self):
        if self._closed:
            return
        self._closed = True
        failures = []
        for step in (self.inference.close, self.runtime.close_runtime, self.binding.shutdown, self.stall_monitor.stop):
            try:
                step()
            except Exception as error:      # noqa: BLE001 - every step runs; the first failure is raised after
                failures.append(error)
        if failures:
            raise failures[0]


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
    parser.add_argument("--execution-prefix", type=int, default=None, metavar="N",
                        help="execute the first N actions of each chunk open-loop, then infer again (1..chunk_size); "
                             "default: the bundle's frozen prefix")
    parser.add_argument("--temporal-ensembling", type=float, nargs="?", const=DEFAULT_ENSEMBLING_M, default=None, metavar="M",
                        help="ACT temporal ensembling with weights exp(-M*i), i=0 the oldest prediction (default M 0.01); "
                             "exclusive with --execution-prefix")
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
