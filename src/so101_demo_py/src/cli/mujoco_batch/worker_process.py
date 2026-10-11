"""The worker process of a batch: build the worker from its spec, run it and write its results."""

from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from typing import Callable, Mapping

from so101_demo.cli.mujoco_batch.common import CliError, _identity, _jsonable, _write_json
from so101_demo.cli.mujoco_batch.request import _load_runtime_config
from so101_demo.cli.mujoco_batch.rpc_proxies import (
    _CoordinatorRpcProxy,
    _resource_from_dict,
    _WorkerBrokerProxy,
)
from so101_demo.parallel_batch.adaptive_pool import (
    WorkerReadinessReceipt,
    WorkerStartGate,
)
from so101_demo.parallel_batch.artifacts import (
    AttemptWorkspace,
    ValidationWorkspace,
    write_recovery_receipt,
)
from so101_demo.parallel_batch.contracts import (
    AttemptStatus,
    RunMode,
    ValidationStatus,
    teacher_execution_bound_s,
)
from so101_demo.parallel_batch.worker import (
    ParallelWorker,
    adaptive_result_is_infrastructure,
)
from so101_demo.runtime.parallel_ipc import (
    AuthenticatedUnixServer,
    WorkerTokenAuthority,
)
from so101_demo.runtime.parallel_ros_runtime import (
    ParallelRosRuntimePorts as _ConcreteRosWorkerRuntimePorts,
)
from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime


class _ArtifactResults:
    """Produce reviewed artifacts for the Worker and verify recovery receipts."""

    def __init__(self, worker_roots: Mapping[str, Path], mode: RunMode, *,
                 collection_scope=None, collection_inputs_manifest=None, clock=time.monotonic):
        self.worker_roots = {key: Path(value) for key, value in worker_roots.items()}
        self.mode = mode
        self._workspaces = {}
        self._act_stores = {}
        self._collection_scope = None
        self._collection_inputs_manifest = collection_inputs_manifest
        if collection_inputs_manifest is not None and collection_scope is None:
            raise ValueError('RESULT_QC_ORIGINAL_BINDING_REQUIRED')
        self._clock = clock
        if collection_scope is not None:
            from so101_demo.act.collection_scope import read_collection_scope
            if mode is not RunMode.EXECUTE:
                raise ValueError("ACT_RESULT_EXECUTE_REQUIRED")
            if not callable(clock):
                raise ValueError("RESULT_CLOCK_INVALID")
            self._collection_scope = Path(collection_scope)
            read_collection_scope(self._collection_scope)

    @staticmethod
    def _key(lease):
        return tuple(getattr(lease, name) for name in (
            "batch_id", "coordinator_epoch", "worker_id", "worker_generation",
            "point_id", "attempt_id", "lease_generation",
        ))

    def reserve_workspace(self, lease, reset_receipt):
        if self.mode is RunMode.DRY_RUN:
            raise CliError("DRY_RUN_WORKSPACE_RESERVATION")
        if self._collection_scope is not None:
            from so101_demo.parallel_batch.contracts import LeaseIdentity
            from so101_demo.runtime.parallel_ros_runtime import ResetBoundaryReceipt
            if type(lease) is not LeaseIdentity or type(reset_receipt) is not ResetBoundaryReceipt:
                raise ValueError("ACT_RESET_RECEIPT_SCHEMA")
            if not lease.lease_issued_monotonic_s < reset_receipt.reset_completed_monotonic_s < lease.lease_deadline_monotonic_s:
                raise ValueError("ACT_RESET_TIME_INVALID")
        reset_epoch = getattr(reset_receipt, "reset_epoch", None)
        completed = getattr(reset_receipt, "reset_completed_monotonic_s", None)
        session = getattr(reset_receipt, "simulation_session_id", None)
        simulation_time = getattr(reset_receipt, "simulation_time_s", None)
        if (not isinstance(reset_epoch, str) or not reset_epoch
                or isinstance(completed, bool) or not isinstance(completed, (int, float))
                or not isinstance(session, str) or not session
                or isinstance(simulation_time, bool)
                or not isinstance(simulation_time, (int, float))):
            raise CliError("WORKSPACE_RESET_RECEIPT")
        identity = _identity(lease, self.mode)
        cls = AttemptWorkspace if self.mode is RunMode.EXECUTE else ValidationWorkspace
        workspace = cls.create(
            self.worker_roots[lease.worker_id], identity,
            reset_epoch=reset_epoch,
            source_stamp={
                "reset_completed_monotonic_s": float(completed),
                "simulation_session_id": session,
                "simulation_time_s": float(simulation_time),
            },
            run_mode=self.mode,
        )
        key = self._key(lease)
        prior = self._workspaces.setdefault(key, workspace)
        if prior.path != workspace.path or prior._metadata != workspace._metadata:
            raise CliError("WORKSPACE_IDENTITY_MISMATCH")
        if self._collection_scope is not None:
            from so101_demo.act.result_store import ActCollectionResultStore
            if key in self._act_stores:
                raise ValueError("ACT_WORKSPACE_ALREADY_RESERVED")
            self._act_stores[key] = ActCollectionResultStore(workspace.path.parent, lease,
                clock=self._clock, audit_manifest=workspace.path / "episode/audit/audit-manifest.json",
                scope=self._collection_scope, expected_session_id=session,
                inputs_manifest=self._collection_inputs_manifest, trust_independent_qc_memo=True,
                expected_reset_epoch=reset_receipt.reset_epoch_value, reserved_workspace=workspace)
        return True

    def workspace(self, lease):
        try:
            return self._workspaces[self._key(lease)]
        except KeyError as error:
            raise CliError("WORKSPACE_NOT_RESERVED") from error

    def _seal(self, lease, decision):
        if self._collection_scope is not None:
            try:
                store = self._act_stores[self._key(lease)]
            except KeyError as error:
                raise ValueError("ACT_WORKSPACE_NOT_RESERVED") from error
            return store.seal_attempt(lease, decision)
        identity = _identity(lease, self.mode)
        if self.mode is RunMode.DRY_RUN:
            workspace = ValidationWorkspace.create(
                self.worker_roots[lease.worker_id], identity,
                reset_epoch="scheduler-only",
                source_stamp={"coordinator_epoch": lease.coordinator_epoch},
                run_mode=self.mode,
            )
        else:
            try:
                workspace = self._workspaces[self._key(lease)]
            except KeyError as error:
                raise CliError("WORKSPACE_NOT_RESERVED") from error
        if (
            self.mode is RunMode.PLAN_ONLY
            and decision.status is ValidationStatus.VALIDATION_PASSED
        ):
            segments = getattr(decision, "segment_receipts", None)
            if not isinstance(segments, tuple) or not segments:
                raise CliError("PLANNING_EVIDENCE_MISSING")
            workspace.write_json(
                "planning/segment-receipts.json",
                {
                    "schema_version": 1,
                    "segment_count": len(segments),
                    "segments": [
                        {
                            "state": getattr(
                                getattr(segment, "state", None),
                                "value",
                                str(getattr(segment, "state", "")),
                            ),
                            "start_state_present": getattr(
                                segment, "start_state", None
                            ) is not None,
                            "terminal_state_present": getattr(
                                segment, "terminal_state", None
                            ) is not None,
                            "plan_present": getattr(segment, "plan", None) is not None,
                            "before_scene_present": getattr(
                                segment, "before_scene", None
                            ) is not None,
                            "after_scene_present": getattr(
                                segment, "after_scene", None
                            ) is not None,
                        }
                        for segment in segments
                    ],
                },
            )
        name = "attempt-result.json" if self.mode is RunMode.EXECUTE else "validation-result.json"
        workspace.write_json(
            name,
            {
                "status": decision.status.value,
                "reason": decision.reason,
                "physical_action_proven_absent": decision.physical_action_proven_absent,
            },
        )
        return str(workspace.seal().path)

    def seal_attempt(self, lease, decision):
        if self.mode is not RunMode.EXECUTE:
            raise CliError("ARTIFACT_MODE")
        return self._seal(lease, decision)

    def seal_validation(self, lease, decision):
        if self.mode is RunMode.EXECUTE:
            raise CliError("ARTIFACT_MODE")
        return self._seal(lease, decision)

    def write_recovery_receipt(self, lease, *, succeeded, generation, **_kwargs):
        if generation != lease.worker_generation:
            raise CliError("RECOVERY_GENERATION")
        return write_recovery_receipt(
            self.worker_roots[lease.worker_id], _identity(lease, self.mode), succeeded=succeeded
        )

    def verify_recovery_receipt(self, location, lease, *, succeeded, generation, **_kwargs):
        try:
            path = Path(location)
            path.relative_to(self.worker_roots[lease.worker_id])
            document = json.loads(path.read_text(encoding="utf-8"))
            return (
                path.is_file()
                and not path.is_symlink()
                and document["identity"] == asdict(_identity(lease, self.mode))
                and document["succeeded"] is succeeded
                and generation == lease.worker_generation
            )
        except (OSError, ValueError, KeyError, TypeError):
            return False


class RosWorkerRuntimePorts(_ConcreteRosWorkerRuntimePorts):
    """Production F20 ports with an explicit process-free test injection seam."""

    def __init__(
        self,
        resources,
        *,
        catalog=None,
        config=None,
        mode=RunMode.PLAN_ONLY,
        side_effects: Mapping[str, Callable] | None = None,
        workspace_provider=None,
        authorize=None,
        broker_generation=None,
        act_profile=False,
        teacher_execution_policy=None,
    ):
        supplied = dict(side_effects or {})
        unknown = set(supplied) - self.REQUIRED
        if unknown:
            raise CliError(f"UNKNOWN_RUNTIME_PORT: {sorted(unknown)!r}")
        super().__init__(
            resources,
            catalog={} if catalog is None else catalog,
            config=config,
            mode=mode,
            broker_generation=broker_generation,
            dependencies={
                "workspace_provider": workspace_provider,
                "authorize": authorize,
                "act_profile": act_profile,
                # the values of the frozen execution policy this episode's manifest is bound to (None: structural checks only)
                "teacher_execution_policy": teacher_execution_policy,
            },
        )
        self.side_effects = supplied

    def kwargs(self):
        concrete = super().kwargs()
        concrete.update(self.side_effects)
        return concrete


def _build_worker_from_spec(path, *, runtime_side_effects=None):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    required_fields = {
        "schema_version", "batch_id", "run_mode", "config_path", "socket_path",
        "token_path", "coordinator_epoch", "resources", "broker_socket_path",
        "broker_generation", "catalog", "control_token_path",
        "control_socket_path", "shutdown_deadline_s", "max_frame_bytes",
    }
    adaptive_fields = {
        "start_paused", "worker_start_timeout_s", "adaptive_workers"
    }
    episode_fields = {"episode_scope_path", "episode_inputs_manifest", "collection"}
    if (
        type(document) is not dict
        or set(document) - episode_fields not in (required_fields, required_fields | adaptive_fields)
        or document["schema_version"] != 1
        or (
            "start_paused" in document
            and (
                document["start_paused"] is not True
                or document["adaptive_workers"] is not True
            )
        )
    ):
        raise CliError("WORKER_SPEC_INVALID")
    for name in (episode_fields - {"collection"}) & set(document):
        value = document[name]
        if not isinstance(value, str) or not Path(value).is_absolute() or ".." in Path(value).parts:
            raise CliError("WORKER_EPISODE_INPUT_INVALID")
    if type(document["broker_generation"]) is not int or document["broker_generation"] <= 0:
        raise CliError("WORKER_SPEC_BROKER_GENERATION")
    resources = _resource_from_dict(document["resources"])
    mode = RunMode(document["run_mode"])
    config = _load_runtime_config(Path(document["config_path"]))
    # The ACT station (neck controller, seven-joint reset) is selected by the frozen inputs manifest. No broker lifecycle.
    act_profile = mode is RunMode.EXECUTE and document.get("episode_inputs_manifest") is not None
    coordinator = _CoordinatorRpcProxy(
        document["socket_path"],
        document["token_path"],
        worker_id=resources.worker_id,
        generation=resources.generation,
        mode=mode,
        coordinator_epoch=document["coordinator_epoch"],
    )
    results = _ArtifactResults({resources.worker_id: resources.worker_root}, mode,
        collection_scope=document["episode_scope_path"] if act_profile else None,
        collection_inputs_manifest=document["episode_inputs_manifest"] if act_profile else None)
    runtime_kwargs = {}
    runtime_ports = None
    broker_proxy = None
    frozen_execution_policy = None
    if act_profile and mode is not RunMode.DRY_RUN:
        # the manifest the worker writes is bound to the frozen Teacher execution policy (its place_height record)
        try:
            from ..act.diagnostic_episode_inputs import verify_frozen_inputs
            from ..act.frozen_runtime_inputs import EXECUTION_POLICY_BINDING

            frozen = verify_frozen_inputs(Path(document["episode_inputs_manifest"]))
            frozen_execution_policy = dict(frozen[EXECUTION_POLICY_BINDING]["values"])
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise CliError("WORKER_EPISODE_INPUT_INVALID") from error
    if mode is not RunMode.DRY_RUN:
        runtime_ports = RosWorkerRuntimePorts(
            resources,
            catalog=document["catalog"],
            config=config,
            mode=mode,
            side_effects=runtime_side_effects,
            workspace_provider=results.workspace,
            authorize=coordinator.authorize_local,
            broker_generation=document["broker_generation"],
            act_profile=act_profile,
            teacher_execution_policy=frozen_execution_policy,
        )
        runtime_kwargs = runtime_ports.kwargs()
        runtime_kwargs["reserve_workspace"] = results.reserve_workspace
        runtime_kwargs["pose_receive_timeout_s"] = teacher_execution_bound_s(config)
        # the scope document this worker's episode belongs to, if the specification names one: the path
        # travels in the specification because that is how every other fact from outside the worker arrives here,
        # and a worker whose specification omits it records nothing, exactly as before.
        _scope_path = document.get("episode_scope_path")
        if _scope_path is not None:
            runtime_kwargs["episode_scope_path"] = str(_scope_path)
        _inputs_manifest = document.get("episode_inputs_manifest")
        if _inputs_manifest is not None:
            runtime_kwargs["episode_inputs_manifest"] = str(_inputs_manifest)
        if "collection" in document:
            # the independent Recorder this worker starts around every Teacher attempt (Phase A4c); re-validated here
            # so a specification that names a fault outside the sandbox refuses the worker before any Teacher starts
            from so101_demo.act.collection_orchestration import (
                CollectionRefused,
                collection_from_document,
            )
            try:
                runtime_kwargs["collection"] = collection_from_document(document["collection"])
            except CollectionRefused as error:
                raise CliError(str(error)) from error
        # A stable slot replacement is represented by the next private Worker
        # spec generation; it never reallocates ROS domains or directories.
        runtime_kwargs["replace_resources"] = coordinator.replace_resources
        # The run's scope document belongs here, written once and named to every worker, but this file has no
        # frozen manifest to build it from: `_frozen` is act_diagnostic_episode.py's name and lives in that
        # process, not this one. Whether the batch path is given the frozen set, or the composition that
        # already reads it writes the document, is the one question left before the last wire is complete
        # Until then the port is absent, which is the state every existing caller is in.
        # Recording happens in the episode's own process, not here: the physical facts the row audit
        # needs live on the far side of a subprocess boundary, so an episode opened here would see the parent's
        # frames and boundaries rather than the episode's. The parent still owns the result port and the commit.
        broker_proxy = _WorkerBrokerProxy(
            coordinator, document["broker_socket_path"], resources, config,
            broker_generation=document["broker_generation"],
            broker_generation_consumer=runtime_ports.bind_broker_generation,
            perception_runner=runtime_ports.run_perception_chain,
        )

        def rebind(replacement):
            if runtime_ports.rebind_resources(replacement) is not True:
                return False
            broker_proxy.resources = replacement
            return True

        runtime_kwargs["rebind_resources"] = rebind
    runtime = build_worker_runtime(resources, mode, **runtime_kwargs)
    worker = ParallelWorker({
        "coordinator": coordinator,
        "broker": broker_proxy if mode is not RunMode.DRY_RUN else SimpleNamespace(
            request_model=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                CliError("DRY_RUN_BROKER_FORBIDDEN")
            ),
            cancel_generation=lambda *_args: True,
        ),
        "runtime": runtime,
        "results": results,
        "clock": time.monotonic,
        "config": config,
        "worker_id": resources.worker_id,
        "generation": resources.generation,
        **(
            {"adaptive_workers": True}
            if document.get("adaptive_workers") is True
            else {}
        ),
    })
    return worker, runtime


def _worker_result_document(result):
    """One result for worker-run-results.json. `failure_origin_type` (design 2026-10-10 section 1) is written only when it is set, so a
    file without an input refusal is byte-for-byte what it always was and old readers never see a new key."""
    document = _jsonable(result)
    if document.get("failure_origin_type") is None:
        document.pop("failure_origin_type", None)
    return document


def _write_worker_results(resources, results):
    path = resources.worker_root / "worker-run-results.json"
    _write_json(path, {
        "schema_version": 1,
        "worker_id": resources.worker_id,
        "worker_generation": resources.generation,
        "results": [_worker_result_document(result) for result in results],
    })
    return path


def _worker_results_failed(results, *, adaptive_workers=False):
    """Classify only an unrecovered or nonterminal Worker result as fatal."""
    if not results:
        return True
    if adaptive_workers:
        return any(adaptive_result_is_infrastructure(result) for result in results)
    for result in results:
        if result.stopped_reason in {"POINT_TERMINAL", "NO_POINT"}:
            continue
        if (
            result.stopped_reason == "INITIAL_GATE_FAILED"
            and result.recovered is True
            and result.terminal_status in {
                AttemptStatus.INVALID,
                ValidationStatus.VALIDATION_INVALID,
            }
        ):
            continue
        return True
    return False


def _run_worker_spec(path, *, runtime_side_effects=None):
    worker, runtime = _build_worker_from_spec(
        path, runtime_side_effects=runtime_side_effects
    )
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    resources = _resource_from_dict(document["resources"])
    control_id = f"{resources.worker_id}-control"
    control_path = Path(document["control_socket_path"])
    control_authority = WorkerTokenAuthority(
        control_path.parent.parent,
        coordinator_epoch=document["coordinator_epoch"],
        ipc_root=control_path.parent,
    )
    control_authority.load_token(
        control_id, resources.generation, Path(document["control_token_path"])
    )
    start_gate = (
        WorkerStartGate(
            expected_worker_id=resources.worker_id,
            generation=resources.generation,
        )
        if document.get("start_paused") is True
        else None
    )

    if start_gate is not None and worker.prepare_for_start() is not True:
        return 1

    def current_readiness():
        if start_gate is None:
            raise CliError("WORKER_READINESS_NOT_ADAPTIVE")
        try:
            from so101_demo.runtime.task_stack import _linux_process_identity

            process_start_ticks = _linux_process_identity(os.getpid())[2]
            runtime_ready = runtime.worker_ready_gate() is True
            if document["run_mode"] == RunMode.DRY_RUN.value:
                broker_generation = document["broker_generation"]
                broker_ready = True
            else:
                broker_generation = worker._broker._refresh_broker(
                    wait_until_healthy=False,
                    startup=True,
                )
                broker_ready = broker_generation == document["broker_generation"]
            receipt = WorkerReadinessReceipt(
                worker_id=resources.worker_id,
                generation=resources.generation,
                process_start_ticks=process_start_ticks,
                coordinator_registered=worker._registered is True,
                runtime_ready=runtime_ready,
                broker_ready=broker_ready,
                broker_generation=broker_generation,
                observed_monotonic_s=time.monotonic(),
            )
            start_gate.record_readiness(receipt)
            return receipt
        except Exception:
            return None

    def control_handler(message):
        if message.get("kind") != "worker_call":
            raise CliError("WORKER_CONTROL_SCHEMA")
        payload = message["payload"]
        if type(payload) is not dict or set(payload) != {"operation"}:
            raise CliError("WORKER_CONTROL_SCHEMA")
        operation = payload["operation"]
        if operation == "readiness":
            receipt = current_readiness()
            return {
                "ready": receipt is not None,
                "receipt": None if receipt is None else _jsonable(receipt),
            }
        if operation == "release_start":
            if start_gate is None:
                raise CliError("WORKER_READINESS_NOT_ADAPTIVE")
            start_gate.release(resources.worker_id, resources.generation)
            return {"completed": True}
        if operation not in {
            "stop", "cancel_motion", "confirm_no_controller_goal", "recover"
        }:
            raise CliError("WORKER_CONTROL_OPERATION")
        completed = runtime.shutdown_control(
            operation,
            deadline_monotonic_s=time.monotonic() + document["shutdown_deadline_s"],
        )
        if operation == "stop":
            worker.request_stop()
        return {"completed": completed}

    control_server = AuthenticatedUnixServer(
        control_path,
        control_authority,
        control_handler,
        deadline_s=document["shutdown_deadline_s"],
        max_frame_bytes=document["max_frame_bytes"],
    )
    control_thread = threading.Thread(target=control_server.serve_forever, daemon=True)
    control_thread.start()
    try:
        if start_gate is not None and not start_gate.wait_released(
            document["worker_start_timeout_s"]
        ):
            return 1
        results = worker.run()
        _write_worker_results(resources, results)
        return int(
            _worker_results_failed(
                results,
                adaptive_workers=document.get("adaptive_workers", False),
            )
        )
    finally:
        try:
            runtime.shutdown_owned()
        finally:
            control_server.close()
            control_thread.join(timeout=1.0)
