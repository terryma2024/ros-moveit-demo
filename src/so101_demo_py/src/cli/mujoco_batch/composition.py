"""The production composition of one batch: stack bring-up, the run loop and teardown."""

from __future__ import annotations

from pathlib import Path
import subprocess
import time
from typing import Callable, Mapping

from so101_demo.cli.mujoco_batch.adaptive_results import AdaptiveResultCapture
from so101_demo.cli.mujoco_batch.broker_lifecycle import BrokerLifecycle
from so101_demo.cli.mujoco_batch.common import CliError, _read_existing_json, _write_json
from so101_demo.cli.mujoco_batch.fixed_web_control import (
    _FixedWebStopRequested,
    _take_fixed_web_control,
)
from so101_demo.cli.mujoco_batch.request import PreparedBatch
from so101_demo.cli.mujoco_batch.rpc_proxies import (
    _resource_manifest_from_dict,
    _WorkerControlProxy,
)
from so101_demo.cli.mujoco_batch.servers import ServerLifecycle
from so101_demo.cli.mujoco_batch.worker_lifecycle import WorkerLifecycle
from so101_demo.cli.mujoco_batch.worker_process import _ArtifactResults
from so101_demo.parallel_batch.adaptive_pool import (
    AdaptivePoolContext,
)
from so101_demo.parallel_batch.artifacts import (
    SealedResultAdapter,
)
from so101_demo.parallel_batch.contracts.common import RunMode
from so101_demo.parallel_batch.contracts.identity import BatchSummary
from so101_demo.parallel_batch.coordinator import BatchCoordinator
from so101_demo.parallel_batch.journal import CoordinatorJournal
from so101_demo.parallel_batch.resource_allocation.models import (
    AllocationPolicy,
    configured_runtime_ipc_root,
)
from so101_demo.parallel_batch.resources import WorkerResourceAllocator
from so101_demo.parallel_batch.web_control import FixedCoordinatorControlServer
from so101_demo.runtime.parallel_ipc import (
    AuthenticatedUnixServer,
    UnixRpcClient,
    WorkerTokenAuthority,
)
from so101_demo.runtime.parallel_processes import ProcessSupervisor, SupervisorError


class ProductionBatchComposition(BrokerLifecycle, WorkerLifecycle, AdaptiveResultCapture, ServerLifecycle):
    """Connect reviewed batch components; no result is synthesized by this layer."""

    def __init__(
        self,
        spec: PreparedBatch,
        **kwargs,
    ):
        self.worker_servers = []
        self.fixed_control_server = None
        self._server_threads = []
        self.allocator = None
        self.journal = None
        self._startup_stage = "constructor"
        try:
            # the scope document the episodes of this run belong to. Optional: a composition told nothing about
            # it produces workers whose specifications omit the field, which is the behaviour every existing caller has.
            # Popped rather than read: _initialize names its keywords one by one and takes no **kwargs, so a key left
            # in the mapping would reach it as an unexpected argument and fail the whole run at construction.
            self._episode_scope_path = kwargs.pop("episode_scope_path", None)
            self._episode_inputs_manifest = kwargs.pop("episode_inputs_manifest", None)
            # the validated collection options of an ACT diagnostic-episode run (Phase A4c); None for every other caller
            self._collection = kwargs.pop("collection", None)
            # the container-broker flag defaults here as well as in _initialize: tests replace _initialize to keep
            # its side effects out, and an attribute that only exists when the real initialiser ran is an attribute
            # those tests cannot rely on - which is how this one started failing once the container-free route was
            # removed and the flag stopped being passed explicitly
            self._uses_production_broker_container = kwargs.get("container_brokers", True)
            self._initialize(spec, **kwargs)
        except BaseException as error:
            partial_cleanup = self._release_partial()
            try:
                error.startup_stage = self._startup_stage
                error.partial_cleanup = partial_cleanup
            except (AttributeError, TypeError):
                pass
            raise

    def _initialize(
        self,
        spec: PreparedBatch,
        *,
        resource_probe=None,
        claim_root: Path | None = None,
        runtime_side_effects_factory: Callable[[object], Mapping[str, Callable]] | None = None,
        broker_request_model=None,
        worker_launcher=None,
        supervisor=None,
        broker_command_builder=None,
        container_brokers: bool = True,
        provenance_revalidator=None,
        broker_health_client_factory=UnixRpcClient,
        container_runner=subprocess.run,
        clock=time.monotonic,
        sleep=time.sleep,
        adaptive_context: AdaptivePoolContext | None = None,
        allocation_policy: AllocationPolicy | None = None,
        pool_running_recorder=None,
    ):
        self._startup_stage = "validate_context"
        self._fixed_web_control = _take_fixed_web_control(spec)
        if spec.request is None:
            raise CliError("POOL_REQUEST_REQUIRED")
        if adaptive_context is not None:
            if (
                not isinstance(adaptive_context, AdaptivePoolContext)
                or adaptive_context.request != spec.request
                or not callable(pool_running_recorder)
            ):
                raise CliError("ADAPTIVE_POOL_CONTEXT")
        self.spec = spec
        self.runtime_ipc_root = configured_runtime_ipc_root(
            spec.request.batch_id
        )
        self.adaptive_context = adaptive_context
        self._pool_running_recorder = pool_running_recorder
        self.worker_exit_codes = ()
        self.adaptive_attempt_statuses = {}
        self.adaptive_result_locations = {}
        self.adaptive_cleanup_complete = False
        self.adaptive_diagnostics = []
        self._clock = clock
        self._sleep = sleep
        self._startup_stage = "process_supervisor"
        from so101_demo.runtime.qualified_commands import qualified_prefix_from_env

        self.supervisor = supervisor or ProcessSupervisor(
            spec.request.batch_id,
            manifest_path=spec.request.evidence_root / "owned-processes.json",
            qualified_prefix=qualified_prefix_from_env(),
        )
        self._container_runner = container_runner
        # the spec is written before any builder runs (3002 vs 3110), so this cannot be inferred from the command:
        # it is declared, defaulting to the repository's long-standing container route, and the container-free CLI
        # path says otherwise explicitly
        if type(container_brokers) is not bool:
            raise ValueError("CONTAINER_BROKERS_INVALID")
        self._uses_production_broker_container = container_brokers
        self.journal = None
        self._startup_stage = "allocator_create"
        self.allocator = WorkerResourceAllocator(
            spec.config,
            spec.request.evidence_root,
            probe=resource_probe,
            claim_root=claim_root,
            start_guard=getattr(spec, 'start_guard', None),
            batch_id=spec.request.batch_id,
            allocation_policy=(
                allocation_policy
                if allocation_policy is not None
                else None
                if adaptive_context is None
                else AllocationPolicy(
                    max_worker_count=adaptive_context.options.worker_count,
                    ros_domain_ids=adaptive_context.options.ros_domain_ids,
                    persistent_cleanup_claims=True,
                )
            ),
            ipc_root=self.runtime_ipc_root,
        )
        self._startup_stage = "resource_allocation"
        if spec.resume:
            self.journal = CoordinatorJournal.create(
                spec.request.evidence_root / "coordinator", spec.request.batch_id
            )
            prior_processes = _read_existing_json(
                spec.request.evidence_root / "owned-processes.json",
                label="PROCESS_MANIFEST",
            )
            retire = getattr(self.supervisor, "retire_manifest", None)
            if not callable(retire) or retire(prior_processes) is not True:
                raise CliError("RECOVERY_PROCESS_FENCE_FAILED")
            resource_document = _read_existing_json(
                spec.request.evidence_root / "resource_manifest.json",
                label="RESOURCE_MANIFEST",
            )
            prior_manifest = _resource_manifest_from_dict(resource_document)
            self.resource_manifest = self.allocator.adopt_existing(prior_manifest)
            self._remove_stale_worker_sockets()
        else:
            self.resource_manifest = self.allocator.allocate(spec.request.worker_count)
            self.allocator.write_manifest()
        worker_roots = {
            worker.worker_id: worker.worker_root for worker in self.resource_manifest.workers
        }
        if self._episode_scope_path is None:
            # no episode scope: the generic production adapter keeps its own paths, as the coordinator's gate
            # requires (its comment in _commit says the ACT gate is "selected by the result contract the port
            # implements - the generic production adapter must keep its own paths")
            self.result_verifier = SealedResultAdapter(
                worker_roots,
                spec.request.run_mode,
                expected_final_cup_pose_world=spec.expected_final_cup_pose_world,
            )
        else:
            # an episode scope is present: build the ACT result port, so the ACT gate fires on a real ACT episode. It
            # takes the same worker_roots, and its verify() has the same signature as the adapter's
            from so101_demo.act.result_store import ActCollectionResultVerifier
            self.result_verifier = ActCollectionResultVerifier(
                worker_roots,
                scope=self._episode_scope_path,
                inputs_manifest=self._episode_inputs_manifest,
                trust_independent_qc_memo=True,
            )
        self._startup_stage = "coordinator_journal"
        if self.journal is None:
            self.journal = CoordinatorJournal.create(
                spec.request.evidence_root / "coordinator", spec.request.batch_id
            )
        if self._episode_scope_path is not None:
            self.result_verifier.bind_execution_journal(self.journal)
        self._startup_stage = "coordinator"
        self.coordinator = BatchCoordinator(
            self.journal,
            spec.request,
            config=spec.config,
            result_port=self.result_verifier,
            clock=clock,
            point_selector=(
                None if adaptive_context is None else adaptive_context.selector.choose
            ),
        )
        if self._fixed_web_control is not None:
            binding = self._fixed_web_control
            if binding.coordinator_epoch != self.journal.coordinator_epoch:
                raise CliError("FIXED_CONTROL_COORDINATOR_EPOCH_MISMATCH")
            self._startup_stage = "fixed_web_control"
            binding.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.fixed_control_server = FixedCoordinatorControlServer(
                coordinator=self.coordinator, campaign_id=binding.campaign_id,
                control_token=binding.token, path=binding.path,
            )
        self.results = _ArtifactResults(worker_roots, spec.request.run_mode)
        self._recovered_worker_ids = None
        if spec.resume:
            self._recovered_worker_ids = self._readmit_recovered_slots()
            self.resource_manifest = self.allocator.manifest
        if broker_request_model is not None:
            raise CliError("IN_PROCESS_BROKER_FORBIDDEN")
        self._worker_children_reaped = False
        self._startup_stage = "control_authority"
        self.authority = WorkerTokenAuthority(
            spec.request.evidence_root,
            coordinator_epoch=self.journal.coordinator_epoch,
            ipc_root=self.runtime_ipc_root,
        )
        self._broker_command_builder = broker_command_builder
        self._broker_health_client_factory = broker_health_client_factory
        self._provenance_revalidator = (
            spec.provenance_verifier
            if provenance_revalidator is None
            else provenance_revalidator
        )
        self.broker_spec_path = None
        self.broker_generation = (
            self._prior_broker_generation() if spec.resume else 0
        )
        self.broker_runtime_root = self.authority.ipc_root / "broker"
        self.broker_input_root = spec.request.evidence_root / "broker-inputs"
        self.broker_socket_path = self.broker_runtime_root / "perception.sock"
        self._startup_stage = "broker_runtime"
        if spec.request.run_mode is not RunMode.DRY_RUN:
            if spec.resume:
                if not self.broker_input_root.is_dir() or self.broker_input_root.is_symlink():
                    raise CliError("RECOVERY_BROKER_INPUT_ROOT")
                prior_root = self._broker_runtime_for_generation(self.broker_generation)
                if (prior_root / "container.cid").exists():
                    self.broker_runtime_root = prior_root
                    self.broker_spec_path = prior_root / "broker-spec.json"
                    self._retire_broker_container(
                        runtime_root=prior_root,
                        generation=self.broker_generation,
                    )
            else:
                self.broker_input_root.mkdir(mode=0o700)
            self._prepare_broker_generation(self.broker_generation + 1)
        self.worker_specs = []
        self.worker_controls = []
        self._runtime_side_effects_factory = runtime_side_effects_factory
        self._worker_launcher = worker_launcher
        self._startup_stage = "worker_ipc"
        for resources in self.resource_manifest.workers:
            if (
                self._recovered_worker_ids is not None
                and resources.worker_id not in self._recovered_worker_ids
            ):
                continue
            token_path = self.authority.issue(resources.worker_id, resources.generation)
            control_id = f"{resources.worker_id}-control"
            control_token_path = self.authority.issue(control_id, resources.generation)
            control_socket_path = self.authority.ipc_root / f"{control_id}.sock"
            socket_path = self.authority.ipc_root / f"{resources.worker_id}.sock"
            server = AuthenticatedUnixServer(
                socket_path,
                self.authority,
                self._coordinator_handler,
                deadline_s=spec.config.heartbeat_timeout_s,
                max_frame_bytes=spec.config.broker_max_frame_bytes,
            )
            worker_spec = {
                "schema_version": 1,
                **({} if self._episode_scope_path is None
                   else {"episode_scope_path": str(self._episode_scope_path)}),
                **({} if self._episode_inputs_manifest is None
                   else {"episode_inputs_manifest": str(self._episode_inputs_manifest)}),
                **({} if self._collection is None else {"collection": self._collection.document()}),
                "batch_id": spec.request.batch_id,
                "run_mode": spec.request.run_mode.value,
                "config_path": str(spec.config_path),
                "socket_path": str(socket_path),
                "token_path": str(token_path),
                "control_token_path": str(control_token_path),
                "control_socket_path": str(control_socket_path),
                "shutdown_deadline_s": spec.config.heartbeat_timeout_s,
                "max_frame_bytes": spec.config.broker_max_frame_bytes,
                "coordinator_epoch": self.journal.coordinator_epoch,
                "broker_socket_path": str(self.broker_socket_path),
                "broker_generation": self.broker_generation or 1,
                "catalog": {
                    point_id: self.spec.catalog[point_id]
                    for point_id in self.spec.request.selected_point_ids
                },
                "resources": resources.to_dict(),
            }
            if adaptive_context is not None:
                worker_spec.update(
                    start_paused=True,
                    adaptive_workers=True,
                    worker_start_timeout_s=(
                        adaptive_context.options.worker_start_timeout_s
                    ),
                )
            worker_path = resources.worker_root / (
                "worker-spec.json" if not spec.resume
                else f"worker-spec-e{self.journal.coordinator_epoch}-g{resources.generation}.json"
            )
            _write_json(worker_path, worker_spec)
            self.worker_specs.append(worker_path)
            self.worker_servers.append(server)
            self.worker_controls.append(_WorkerControlProxy(
                control_socket_path,
                control_token_path,
                worker_id=resources.worker_id,
                generation=resources.generation,
                coordinator_epoch=self.journal.coordinator_epoch,
                deadline_s=spec.config.heartbeat_timeout_s,
                orphan_manifest=resources.worker_root / "owned-runtime-processes.json",
            ))
        self._startup_stage = "initialized"

    def run(self) -> BatchSummary:
        failure = False
        cleanup = False
        cleanup_actions = {}

        def tracked_cleanup(name, action):
            def invoke():
                try:
                    succeeded = action() is True
                except Exception as error:
                    cleanup_actions[name] = {
                        "succeeded": False,
                        "error_type": type(error).__name__,
                        "error_message": str(error),
                    }
                    return False
                cleanup_actions[name] = {
                    "succeeded": succeeded,
                    "error_type": None,
                    "error_message": None,
                }
                return succeeded

            return invoke

        try:
            self._start_servers()
            self._start_broker()
            self._wait_broker_ready()
            if self._worker_launcher is not None:
                codes = []
                for path in self.worker_specs:
                    self._check_fixed_web_stop()
                    codes.append(self._worker_launcher(self, path))
            else:
                self._start_workers()
                wait_kwargs = {
                    "deadline_monotonic_s": (
                        self._clock() + self.spec.config.batch_hard_timeout_s
                    ),
                    "health_recovery": (
                        None
                        if self.adaptive_context is not None
                        else self._recover_broker
                    ),
                    "health_probe": lambda _expected: (
                        self.coordinator.snapshot().broker_healthy
                    ),
                }
                # Unconditional: an owned measurement owner must be able to stop child
                # waits even when no production Web control server exists.
                wait_kwargs["stop_requested"] = self._stop_requested
                if self.adaptive_context is not None:
                    wait_kwargs.update(
                        stop_on_nonzero=True,
                        on_nonzero=self._record_adaptive_infrastructure_failure,
                    )
                codes = self.supervisor.wait_for_children(
                    **wait_kwargs,
                )
                self._worker_children_reaped = True
            self.worker_exit_codes = tuple(codes)
            failure = any(code != 0 for code in codes)
            self._settle_shared_dependency_failure()
            snapshot = self.coordinator.snapshot()
        except _FixedWebStopRequested:
            # No new execution/result path: finally performs the same verified
            # Worker/controller/Broker cleanup and public completion below.
            pass
        except SupervisorError as error:
            if not (
                self._fixed_web_stop_requested()
                and (str(error) == "COOPERATIVE_STOP_REQUESTED"
                     or isinstance(error.__cause__, _FixedWebStopRequested))
            ):
                raise
        finally:
            try:
                process_error = None
                try:
                    process_cleanup = self.supervisor.shutdown(
                        stop_leases=tracked_cleanup(
                            "stop_leases", self._stop_new_leases
                        ),
                        cancel_goal=tracked_cleanup(
                            "cancel_goal", self._cancel_worker_goals
                        ),
                        confirm_goal_cancelled=tracked_cleanup(
                            "confirm_goal_cancelled",
                            self._confirm_worker_goals_cancelled,
                        ),
                        request_recovery=tracked_cleanup(
                            "request_recovery", self._request_worker_recovery
                        ),
                    )
                except Exception as error:
                    process_cleanup = False
                    process_error = error
                process_record = {
                    "succeeded": process_cleanup is True,
                    "error_type": (
                        None if process_error is None
                        else type(process_error).__name__
                    ),
                    "error_message": (
                        None if process_error is None else str(process_error)
                    ),
                }
                container_error = None
                try:
                    container_cleanup = self._retire_broker_container()
                except Exception as error:
                    container_cleanup = False
                    container_error = error
                container_record = {
                    "succeeded": container_cleanup is True,
                    "error_type": (
                        None if container_error is None
                        else type(container_error).__name__
                    ),
                    "error_message": (
                        None if container_error is None else str(container_error)
                    ),
                }
                cleanup = process_cleanup and container_cleanup
                snapshot = self.coordinator.snapshot()
                completion_allowed = bool(
                    snapshot.terminal_reason
                    and cleanup
                    and (not failure or self.adaptive_context is not None)
                )
                completion_attempted = completion_allowed
                completion_error = None
                if completion_allowed:
                    try:
                        snapshot = self.coordinator.complete_cleanup(
                            owned_processes_stopped=True, controllers_stopped=True
                        )
                    except Exception as error:
                        cleanup = False
                        completion_error = error
                self._capture_adaptive_results()
                _write_json(
                    self.spec.request.evidence_root / "cleanup-gates.json",
                    {
                        "schema_version": 1,
                        "batch_id": self.spec.request.batch_id,
                        "actions": cleanup_actions,
                        "process_cleanup": process_record,
                        "container_cleanup": container_record,
                        "cleanup_gates_passed": cleanup,
                        "coordinator_completion": {
                            "attempted": completion_attempted,
                            "succeeded": bool(
                                completion_attempted
                                and completion_error is None
                                and snapshot.summary.batch_cleanup_complete
                            ),
                            "error_type": (
                                None if completion_error is None
                                else type(completion_error).__name__
                            ),
                            "error_message": (
                                None if completion_error is None
                                else str(completion_error)
                            ),
                        },
                        "batch_cleanup_complete": (
                            snapshot.summary.batch_cleanup_complete
                        ),
                    },
                )
                if process_error is not None:
                    raise process_error
                if completion_error is not None:
                    raise completion_error
            finally:
                self._stop_servers()
                adaptive_released = self._release_adaptive_resources(cleanup)
                self.adaptive_cleanup_complete = bool(
                    cleanup
                    and adaptive_released
                    and snapshot.summary.batch_cleanup_complete
                )
                self.journal.close()
                self.allocator.close()
                if self._release_runtime_ipc_root() is not True:
                    raise CliError("RUNTIME_IPC_CLEANUP_INCOMPLETE")
        return snapshot.summary
