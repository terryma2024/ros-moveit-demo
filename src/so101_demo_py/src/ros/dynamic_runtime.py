"""ROS-aware composition for the V2.1 single-state dynamic plan-only path."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from ..application.dynamic_plan_only import (
    DynamicPlanningOptions,
    plan_dynamic_state_with_scene_gates,
)
from ..cli.cup_pose_subscriber import status_line
from ..core.domain import Failure, FailureCategory, RunMode, RunRequest, RunResult, RunStatus, State
from ..core.dynamic_pick import resolve_motion_targets
from ..core.dynamic_pick_policy import (
    LoadedDynamicPolicy,
    load_dynamic_pick_template,
    load_dynamic_policy_variant,
)
from ..core.runner import StateMachineRunner
from ..profiling.session import SemanticProfiler
from ..profiling.wrappers import profile_actions
from ..runtime.dynamic_plan_manifest import write_dynamic_plan_manifest
from ..runtime.workflow_events import EventEmitter, normalize_failure_code
from .cup_pose_source import RosCupPoseSource
from .cup_scene_observer import RosCupSceneObserver
from .dynamic_planner import RosDynamicPlanner


_PHASE_TIMING_PREFIX = "DYNAMIC_EXECUTE_PHASE_TIMING "
_PHASE_TIMING_MAX_BYTES = 8000
_CENSUS_MAX_TOPICS = 32
_STALL_PREFIX = "DYNAMIC_MAIN_STALL "
_STALL_THRESHOLD_NS = 300_000_000
_STALL_POLL_S = 0.05
_STALL_MAX_LINES = 10
_STALL_MAX_FRAMES = 15
# Observation-only: the timer of the run_dynamic_execute call in progress, if any, so that helpers
# below it (the reachability preflight) can mark phases without a signature change.
_ACTIVE_PHASE_TIMER = None


class _PhaseTimer:
    """Bounded monotonic phase marks plus an optional callback census; never raises."""

    def __init__(self):
        self.start_ns = time.monotonic_ns()
        self.phases = []
        self.census = None
        self.node = None
        self.last_progress_ns = self.start_ns
        self.stall_threshold_ns = _STALL_THRESHOLD_NS
        self.stall_poll_s = _STALL_POLL_S
        self.stall_max_lines = _STALL_MAX_LINES
        self._stall_stop = threading.Event()
        self._stall_thread = None

    def mark(self, name):
        try:
            now = time.monotonic_ns()
            self.last_progress_ns = now
            if len(self.phases) < 256:
                self.phases.append([name, now - self.start_ns])
        except Exception:
            pass

    def start_stall_sampler(self, main_thread_ident):
        """D15, observation only: report where the main thread is while nothing makes progress."""
        try:
            if self._stall_thread is not None:
                return
            self._stall_thread = threading.Thread(target=self._sample_stalls, args=(main_thread_ident,),
                                                  daemon=True, name="dynamic-main-stall-sampler")
            self._stall_thread.start()
        except Exception:
            pass

    def stop_stall_sampler(self):
        try:
            self._stall_stop.set()
            thread = self._stall_thread
            if thread is not None and thread is not threading.current_thread():
                thread.join(1.0)
        except Exception:
            pass

    def _progress_ns(self):
        latest = self.last_progress_ns
        for entry in list((self.census or {}).values()):
            receipt = entry.get("last_receipt_monotonic_ns")
            if isinstance(receipt, int) and receipt > latest:
                latest = receipt
        return latest

    def _sample_stalls(self, main_thread_ident):
        try:
            lines, armed = 0, True
            while not self._stall_stop.wait(self.stall_poll_s):
                stalled_ns = time.monotonic_ns() - self._progress_ns()
                if stalled_ns <= self.stall_threshold_ns:
                    armed = True
                    continue
                if not armed or lines >= self.stall_max_lines:
                    continue
                armed = False
                lines += 1
                frame = sys._current_frames().get(main_thread_ident)
                frames = [] if frame is None else [
                    f"{item.filename}:{item.lineno}:{item.name}"
                    for item in traceback.extract_stack(frame)[-_STALL_MAX_FRAMES:]]
                phases = self.phases
                document = {"last_phase": phases[-1][0] if phases else None,
                            "stall_ms": stalled_ns / 1e6, "frames": frames}
                print(_STALL_PREFIX + json.dumps(document, sort_keys=True, separators=(",", ":")),
                      file=sys.stderr, flush=True)
        except BaseException:
            pass

    def emit(self, outcome):
        self.stop_stall_sampler()
        try:
            clock_ns = None
            try:
                clock_ns = int(self.node.get_clock().now().nanoseconds)
            except Exception:
                pass
            document = {"phases": list(self.phases), "outcome": str(outcome)[:200],
                        "census": self.census, "ros_clock_ns": clock_ns}
            line = json.dumps(document, sort_keys=True, separators=(",", ":"))
            while len(line) > _PHASE_TIMING_MAX_BYTES and document["phases"]:
                del document["phases"][len(document["phases"]) // 2:]
                document["truncated"] = True
                line = json.dumps(document, sort_keys=True, separators=(",", ":"))
            print(_PHASE_TIMING_PREFIX + line, file=sys.stderr, flush=True)
        except Exception:
            pass


def _mark_active_phase(name):
    timer = _ACTIVE_PHASE_TIMER
    if timer is not None:
        timer.mark(name)


def _record_callback_lag(node, entry, callback_args):
    """D14, observation only: sim-time backlog lag of a header-stamped message at callback time.

    Keeps `max_lag_s` and `last_lag_s` in the census entry. Messages without a `header.stamp` are skipped;
    never raises.
    """
    try:
        stamp = callback_args[0].header.stamp
        lag_s = (int(node.get_clock().now().nanoseconds)
                 - (int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec))) / 1e9
        entry["last_lag_s"] = lag_s
        if entry.get("max_lag_s") is None or lag_s > entry["max_lag_s"]:
            entry["max_lag_s"] = lag_s
    except Exception:
        pass


def _install_callback_census(node):
    """Count invocations per subscribed topic by wrapping `node.create_subscription`.

    Observation only: callbacks run unchanged. Returns the live census mapping, or None when the node
    has no subscription factory or cannot be wrapped.
    """
    try:
        create = getattr(node, "create_subscription", None)
        if not callable(create):
            return None
        census = {}

        def counted_create_subscription(*args, **kwargs):
            try:
                topic = str(args[1] if len(args) > 1 else kwargs["topic"])
                if len(args) > 2:
                    callback, location = args[2], 2
                else:
                    callback, location = kwargs["callback"], None
                if callable(callback) and (topic in census or len(census) < _CENSUS_MAX_TOPICS):
                    entry = census.setdefault(
                        topic, {"count": 0, "last_receipt_monotonic_ns": None})

                    def counted_callback(*callback_args, **callback_kwargs):
                        entry["count"] += 1
                        entry["last_receipt_monotonic_ns"] = time.monotonic_ns()
                        _record_callback_lag(node, entry, callback_args)
                        return callback(*callback_args, **callback_kwargs)

                    if location is None:
                        kwargs["callback"] = counted_callback
                    else:
                        args = args[:location] + (counted_callback,) + args[location + 1:]
            except Exception:
                pass
            return create(*args, **kwargs)

        node.create_subscription = counted_create_subscription
        return census
    except Exception:
        return None


def _write_consumer_ready_receipt(path: Path, document: dict[str, object]) -> None:
    """Exclusively publish one fsync-backed child READY boundary."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = (
        json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")
    # The final name appears only with its complete, durable content: the parent polls this path and must never read an
    # empty or partial receipt (it failed the point gate on one, under slow fsync). The temporary name is hard-linked
    # to the final one, which stays exclusive (FileExistsError) and atomic.
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
    )
    try:
        try:
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                if written <= 0:
                    raise OSError("consumer READY receipt write made no progress")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.link(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    directory = os.open(
        path.parent,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
    )
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _failure_code(error: Exception) -> str:
    code = getattr(error, "code", None)
    if isinstance(code, str) and code:
        return code
    prefix = str(error).split(":", 1)[0]
    if prefix and prefix.upper() == prefix and " " not in prefix:
        return prefix
    return "DYNAMIC_PLAN_FAILED"


def _load_policy(options, share_dir: Path) -> LoadedDynamicPolicy:
    if not options.dynamic_policy:
        return load_dynamic_policy_variant(share_dir, backend=options.backend)
    path = Path(options.dynamic_policy)
    raw = path.read_bytes()
    return LoadedDynamicPolicy(
        load_dynamic_pick_template(
            path,
            expected_backend=options.backend,
            expected_execution_allowed=False,
        ),
        path,
        hashlib.sha256(raw).hexdigest(),
        "CALIBRATION_REQUIRED",
        options.backend,
        False,
    )


def run_dynamic_plan_only(options) -> int:
    if not options.plan_only_state or not options.evidence_file:
        print("status=ERROR failure=DYNAMIC_PLAN_CONFIG_REQUIRED")
        return 1
    try:
        state = State(options.plan_only_state)
    except ValueError:
        print("status=ERROR failure=PLAN_ONLY_STATE_UNSUPPORTED")
        return 1

    import rclpy
    from ament_index_python.packages import get_package_share_directory
    from rclpy.parameter import Parameter

    share_dir = Path(get_package_share_directory("so101_demo_py"))
    try:
        loaded = _load_policy(options, share_dir)
    except Exception as error:
        print(status_line("ERROR", failure=_failure_code(error), message=error))
        return 1
    installed_prefix = options.installed_prefix or str(share_dir.parents[1])
    rclpy.init()
    node = rclpy.create_node(
        "so101_dynamic_cup_pick_place",
        parameter_overrides=[Parameter("use_sim_time", value=True)],
    )
    scene = None
    planner = None
    try:
        source = RosCupPoseSource(node, loaded.template)
        source.arm(min(5.0, options.cup_pose_timeout_s))
        sample = source.get_one(options.cup_pose_timeout_s)
        targets = resolve_motion_targets(sample, loaded.template)
        scene = RosCupSceneObserver(node)
        planner = RosDynamicPlanner(node, loaded.template.arm_joint_names)
        planning = DynamicPlanningOptions(
            loaded.template.planning_frame,
            loaded.template.planning_group,
            loaded.template.tcp_link,
            loaded.template.position_tolerance_m,
            loaded.template.orientation_tolerance_rad,
            loaded.template.planning_timeout_s,
            loaded.template.velocity_scaling,
            loaded.template.acceleration_scaling,
        )
        plan, before, after = plan_dynamic_state_with_scene_gates(
            state=state,
            provider=targets,
            control=planner.control,
            options=planning,
            scene=scene,
            sample=sample,
            template=loaded.template,
        )
        if not plan.accepted or after is None:
            print(
                status_line(
                    "ERROR",
                    failure="CUP_POSE_PLAN_FAILED",
                    message=plan.error_code or "MoveIt planning failed",
                )
            )
            return 1
        evidence_path = write_dynamic_plan_manifest(
            Path(options.evidence_file),
            backend=options.backend,
            source_commit=options.source_commit,
            installed_prefix=installed_prefix,
            policy_path=loaded.path,
            policy_sha256=loaded.sha256,
            qualification_status=loaded.qualification_status,
            selected_state=state.value,
            sample=sample,
            targets=targets,
            before_scene=before,
            after_scene=after,
            plan=plan,
        )
        print(
            status_line(
                "PLAN_ONLY_COMPLETE",
                strategy="dynamic",
                state=state.value,
                evidence=evidence_path,
            )
        )
        return 0
    except Exception as error:
        print(status_line("ERROR", failure=_failure_code(error), message=error))
        return 1
    finally:
        if planner is not None:
            planner.close()
        if scene is not None:
            scene.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def _dynamic_execute_runtime(ik_backend: str | None = None):
    """Load ROS adapters lazily and expose a narrow orchestration test seam."""

    import rclpy
    from ament_index_python.packages import get_package_share_directory
    from rclpy.parameter import Parameter
    from rclpy.signals import SignalHandlerOptions

    from ..application.dynamic_execute import build_dynamic_actions
    from ..application.task_reachability import check_task_reachability
    from ..control.planning_scene.task_scene import RosTaskScenePort
    from ..core.task_geometry import load_task_geometry
    from ..core.task_points import TaskPoint
    from .cup_scene_observer import RosMujocoCupSceneObserver
    from .data_source_binding import bind_data_sources
    from .dynamic_mujoco_execution import RosDynamicMujocoExecution
    from .task_reachability import RosJointStateReader, RosMoveGroupReachabilityPlanner

    def reachability_preflight(node, sample, template, scene_revision, progress=None):
        point = TaskPoint(
            id="perceived_cup",
            label="Perceived cup",
            cup_position_world_m=tuple(sample.pose_world.values[:3]),
        )
        # `progress=None` keeps the planner's own bare spin; only a caller that owns a drainable source passes one.
        planner_options = {} if ik_backend is None else {"ik_backend": ik_backend}
        if progress is not None:
            planner_options["progress"] = progress
        planner = RosMoveGroupReachabilityPlanner(node, template, **planner_options)
        reader = RosJointStateReader(node, template.arm_joint_names)
        try:
            _mark_active_phase("reachability.read.begin")
            start = reader.read(template.planning_timeout_s)
            _mark_active_phase("reachability.read.end")
            _mark_active_phase("check_task_reachability.begin")
            try:
                return check_task_reachability(
                    point,
                    template,
                    start,
                    planner,
                    scene_revision=scene_revision,
                )
            finally:
                _mark_active_phase("check_task_reachability.end")
        finally:
            reader.close()
            planner.close()

    return SimpleNamespace(
        rclpy=rclpy,
        # `rclpy.init` must not install its own SIGINT/SIGTERM handler: it shuts the context down before any cancel
        # could be sent. The Teacher installs a handler that only sets a stop flag.
        signal_handler_options_no=SignalHandlerOptions.NO,
        parameter=Parameter,
        get_package_share_directory=get_package_share_directory,
        load_policy=load_dynamic_policy_variant,
        load_geometry=load_task_geometry,
        cup_pose_source=RosCupPoseSource,
        cup_scene_observer=RosMujocoCupSceneObserver,
        task_scene_port=RosTaskScenePort,
        cleanup_task_scene=lambda _scene: None,
        resolve_motion_targets=resolve_motion_targets,
        reachability_preflight=reachability_preflight,
        execution=RosDynamicMujocoExecution,
        build_actions=build_dynamic_actions,
        runner=StateMachineRunner,
        bind_scene_source=bind_data_sources,
    )




def _write_reachability_evidence(
    path: Path, session_id: str, report: Any, *, ik_backend: str = "native"
) -> None:
    from ..cli.task_reachability import result_document

    document = result_document((report,))
    document["session_id"] = session_id
    document["ik_backend"] = ik_backend
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


@dataclass(frozen=True, slots=True)
class _CleanupFailure:
    resource: str
    error: BaseException


@dataclass(frozen=True, slots=True)
class _CleanupOutcome:
    failures: tuple[_CleanupFailure, ...]

    @property
    def message(self) -> str:
        return "; ".join(f"{failure.resource}: {failure.error}" for failure in self.failures)


def _cleanup_dynamic_execute(
    *,
    runtime: Any,
    initialized_here: bool,
    node: Any | None,
    execution: Any | None,
    task_scene: Any | None,
    truth_observer: Any | None,
    scene_source_binding: Any | None = None,
) -> _CleanupOutcome:
    """Attempt every owned cleanup operation and retain all failures."""

    failures: list[_CleanupFailure] = []

    def attempt(resource: str, operation: Callable[[], None]) -> None:
        try:
            operation()
        except BaseException as error:
            failures.append(_CleanupFailure(resource, error))

    if execution is not None:
        attempt("execution", execution.close)
    if task_scene is not None:
        attempt("task_scene", lambda: runtime.cleanup_task_scene(task_scene))
    if truth_observer is not None:
        attempt("truth_observer", truth_observer.close)
    if scene_source_binding is not None:
        attempt("scene_source", scene_source_binding.close)
    if node is not None:
        attempt("node", node.destroy_node)
    if initialized_here:
        attempt("rclpy_context", runtime.rclpy.shutdown)
    return _CleanupOutcome(tuple(failures))


class ExecutionSnapshotObserver:
    """The runner's release-marker observer: the execution's own waiting `_snapshot`, not a bare `observer.snapshot()`.

    The bare call raised `EvidenceStale` on a single stale sample (max age 0.2 s) and ended the run; under load the evidence
    topic's lag reached 2.5 s. `_snapshot` spins the executor and retries until a fresh sample or its own unchanged deadline.
    """

    def __init__(self, execution: Any) -> None:
        self._execution = execution

    def snapshot(self):
        return self._execution._snapshot()


def _unreachable_pre_motion_result() -> RunResult:
    """The Teacher's terminal result when the reachability preflight decided UNREACHABLE: the first transition fails and no
    action ran, which is the shape the execution's failure evidence proves physical action absent from."""
    return RunResult(
        status=RunStatus.ERROR,
        current_state=State.ERROR,
        failure=Failure(FailureCategory.PRECONDITION, "DYNAMIC_TARGET_UNREACHABLE", "DYNAMIC_TARGET_UNREACHABLE"),
        transition_count=1,
        state_trace=(State.IDLE, State.ERROR),
    )


def _finish_failed_execution(execution: Any, error: Exception) -> None:
    class FailedResult:
        status = type("Status", (), {"value": "ERROR"})()
        current_state = State.ERROR
        transition_count = 0
        state_trace = (State.ERROR,)
        failure = type("Failure", (), {"code": _failure_code(error)})()

    execution.finish(FailedResult())


def _execution_state_max_age_s(share_dir, *, teacher_run: bool):
    """The execution policy's state age (the Teacher policy of a Teacher run, else the general runtime policy), or None when it
    cannot be read.

    An unreadable policy is refused where the execution loads it (no motion without it); this only sizes the
    scene observer the release preflight joins against.
    """
    from ..act.general_runtime_policy import GENERAL_RUNTIME_FILE, load_general_runtime_policy
    from ..act.teacher_endpoint import EXECUTION_POLICY_FILE, load_teacher_execution_policy

    loader, file_name = ((load_teacher_execution_policy, EXECUTION_POLICY_FILE) if teacher_run
                         else (load_general_runtime_policy, GENERAL_RUNTIME_FILE))
    try:
        return loader(Path(share_dir) / "config/act" / file_name)["state_max_age_s"]
    except (OSError, ValueError):
        return None


def run_dynamic_execute(
    options,
    *,
    profiler: SemanticProfiler | None = None,
    event_emitter: EventEmitter | None = None,
    _runtime=None,
) -> int:
    """Run the MuJoCo dynamic strategy through the shared state machine.

    The Teacher records nothing and holds no data side (Phase A4c). The offline episode processor
    rebuilds the episode from the record-only bag of the Teacher's event stream and the shared sources; whatever it does cannot reach this function. Returned
    codes: 0 = the Teacher COMPLETED; 1 = it did not (or one of its own resources failed to clean up). The data verdict
    is the Recorder's, never this process's.

    When `options.frozen_inputs_manifest` is given the Teacher loads its execution snapshot and its frozen policies from
    that manifest and refuses a mismatch before any motion.
    """

    global _ACTIVE_PHASE_TIMER
    status_stream = sys.stderr if event_emitter is not None else sys.stdout
    terminal_emitted = False

    def emit_failure(candidate: object) -> None:
        nonlocal terminal_emitted
        if event_emitter is None or terminal_emitted:
            return
        event_emitter.emit(
            "RUNTIME_FAILED",
            payload={},
            failure_code=normalize_failure_code("RUNTIME_FAILED", candidate),
        )
        terminal_emitted = True

    if (
        not options.session_id
        or options.expected_reset_epoch is None
        or options.evidence_root is None
    ):
        emit_failure("DYNAMIC_LIVE_RUNTIME_CONFIG_REQUIRED")
        print(
            "status=ERROR failure=DYNAMIC_LIVE_RUNTIME_CONFIG_REQUIRED",
            file=status_stream,
        )
        return 1

    from ..application.cup_pose_preflight import (
        validate_cup_scene,
        validate_mujoco_scene_identity,
    )
    from ..application.dynamic_scene_sync import prepare_dynamic_cup_scene

    from ..control.moveit.pose_ik import resolve_ik_backend

    try:
        ik_backend = resolve_ik_backend(getattr(options, "ik_backend", None))
    except ValueError as error:
        emit_failure("IK_BACKEND_UNSUPPORTED")
        print(status_line("ERROR", failure="IK_BACKEND_UNSUPPORTED", message=error),
              file=status_stream)
        return 1
    runtime = _dynamic_execute_runtime(ik_backend) if _runtime is None else _runtime
    setup_token = (
        profiler.start_span("runtime.setup", {"backend": "mujoco"})
        if profiler is not None
        else None
    )
    setup_finished = False

    def finish_setup(outcome: str, reason_code: str | None = None) -> None:
        nonlocal setup_finished
        if setup_token is None or setup_finished:
            return
        attributes: dict[str, object] = {"backend": "mujoco"}
        if reason_code is not None:
            attributes["reason_code"] = reason_code
        profiler.finish_span(setup_token, outcome=outcome, attributes=attributes)
        setup_finished = True

    share_dir = Path(runtime.get_package_share_directory("so101_demo_py"))
    execution_inputs = None
    frozen = None
    manifest_option = getattr(options, "frozen_inputs_manifest", None)
    if manifest_option is not None:
        from ..act.frozen_runtime_inputs import load_teacher_frozen_inputs
        try:
            frozen, execution_inputs, share_dir = load_teacher_frozen_inputs(Path(manifest_option))
        except Exception as error:
            failure_code = _failure_code(error)
            finish_setup("rejected", failure_code)
            emit_failure(failure_code)
            print(status_line("ERROR", failure=failure_code, message=error), file=status_stream)
            return 1
    # A Teacher run (frozen inputs, the minimal runtime gates): the simulator comparison of the perceived cup pose (S05) is telemetry
    teacher_run = frozen is not None
    inject_failure_at = getattr(options, "inject_failure_at", None)
    if inject_failure_at is not None:
        # The diagnostic injection is refused by name, before any motion, unless the run has frozen inputs and the state is LIFT
        refusal = None if teacher_run and inject_failure_at == "LIFT" else (
            "TEACHER_INJECTION_REQUIRES_FROZEN_INPUTS" if not teacher_run else f"TEACHER_INJECTION_STATE_UNSUPPORTED: {inject_failure_at}")
        if refusal is not None:
            finish_setup("rejected", refusal.split(":")[0])
            emit_failure(refusal.split(":")[0])
            print(status_line("ERROR", failure=refusal.split(":")[0], message=refusal), file=status_stream)
            return 1
    try:
        loaded = runtime.load_policy(share_dir, backend="mujoco")
    except Exception as error:
        failure_code = _failure_code(error)
        finish_setup("rejected", failure_code)
        emit_failure(failure_code)
        print(
            status_line("ERROR", failure=failure_code, message=error),
            file=status_stream,
        )
        return 1
    if not loaded.execution_allowed:
        finish_setup("rejected", "DYNAMIC_EXECUTION_NOT_QUALIFIED")
        emit_failure("DYNAMIC_EXECUTION_NOT_QUALIFIED")
        print(
            "status=ERROR failure=DYNAMIC_EXECUTION_NOT_QUALIFIED",
            file=status_stream,
        )
        return 1
    try:
        geometry = runtime.load_geometry(
            share_dir / "assets" / "common" / "geometry-manifest.yaml"
        )
    except Exception as error:
        failure_code = _failure_code(error)
        finish_setup("rejected", failure_code)
        emit_failure(failure_code)
        print(
            status_line("ERROR", failure=failure_code, message=error),
            file=status_stream,
        )
        return 1

    initialized_here = False
    node = None
    event_stream = None
    event_stream_close = None
    truth_observer = None
    scene_source_binding = None
    task_scene = None
    execution = None
    result = None
    evidence_file = Path(options.evidence_root) / "dynamic-execute-manifest.json"
    reachability_file = Path(options.evidence_root) / "reachability-observed.json"
    primary_failure = None
    primary_message = None
    secondary_failures: list[tuple[str, BaseException]] = []
    lease_names = (
        "batch_id", "coordinator_epoch", "worker_id", "worker_generation",
        "point_id", "attempt_id", "lease_generation",
    )
    lease_values = {name: getattr(options, name, None) for name in lease_names}
    if any(value is not None for value in lease_values.values()):
        if any(value is None for value in lease_values.values()):
            emit_failure("DYNAMIC_PARALLEL_LEASE_IDENTITY_INCOMPLETE")
            print(
                "status=ERROR failure=DYNAMIC_PARALLEL_LEASE_IDENTITY_INCOMPLETE",
                file=status_stream,
            )
            return 1
        parallel_lease_identity = lease_values
    else:
        parallel_lease_identity = None
    phase_timer = _PhaseTimer()
    _ACTIVE_PHASE_TIMER = phase_timer
    mark = phase_timer.mark
    stop_flags = None
    restore_signals = None
    watchdog = None
    try:
        # Stop flags exist before rclpy does, so a SIGINT/SIGTERM during setup is already a flag. Handlers are
        # installed on the main thread only (`signal.signal` refuses elsewhere).
        from .teacher_stop import DeadlineWatchdog, StopFlags
        stop_flags = StopFlags()
        if threading.current_thread() is threading.main_thread():
            restore_signals = stop_flags.install_signal_handlers()
        init_options = getattr(runtime, "signal_handler_options_no", None)
        runtime.rclpy.init(**({} if init_options is None else {"signal_handler_options": init_options}))
        initialized_here = True
        node = runtime.rclpy.create_node(
            "so101_dynamic_cup_pick_place",
            parameter_overrides=[runtime.parameter("use_sim_time", value=True)],
        )
        phase_timer.node = node
        # The Teacher's event stream exists before its first scene call, so the setup scene is on it too. A node that
        # cannot publish leaves the Teacher without a stream, never without a run.
        from ..adapters.act.ros_teacher_event_stream import start_teacher_event_stream
        event_stream, event_stream_close, _stream_error = start_teacher_event_stream(
            node, options.session_id, options.expected_reset_epoch, parallel_lease_identity,
            getattr(options, "request_id", None))
        if event_stream is not None:
            event_stream.close_publisher = event_stream_close
        phase_timer.census = _install_callback_census(node)
        phase_timer.start_stall_sampler(threading.get_ident())
        source = runtime.cup_pose_source(node, loaded.template)
        # A stop request (SIGINT/SIGTERM, parent death, deadline) ends the pose wait; without it the wait ran to its
        # own timeout and the owner's bounded shutdown found the process alive.
        source.stop_check = stop_flags.raise_if_stopped
        mark("source.arm.begin")
        ready_boundary = source.arm(min(5.0, options.cup_pose_timeout_s))
        mark("source.arm.end")
        stop_flags.raise_if_stopped()
        if parallel_lease_identity is not None:
            ready_receipt = getattr(options, "ready_receipt", None)
            expected_ready_receipt = Path(options.evidence_root) / "consumer-ready.json"
            if ready_receipt is None or Path(ready_receipt) != expected_ready_receipt:
                raise RuntimeError("DYNAMIC_READY_RECEIPT_IDENTITY")
            _write_consumer_ready_receipt(
                expected_ready_receipt,
                {
                    "schema_version": 1,
                    "kind": "dynamic_consumer_ready",
                    "session_id": options.session_id,
                    "reset_epoch": options.expected_reset_epoch,
                    "parallel_lease_identity": parallel_lease_identity,
                    "ready_ros_ns": ready_boundary.ready_ros_ns,
                    "ready_monotonic_s": ready_boundary.ready_monotonic_s,
                },
            )
        elif getattr(options, "ready_receipt", None) is not None:
            raise RuntimeError("DYNAMIC_READY_RECEIPT_WITHOUT_LEASE")
        if event_emitter is not None:
            ready_payload = {
                "session_id": options.session_id,
                "reset_epoch": options.expected_reset_epoch,
            }
            if hasattr(options, "request_id"):
                ready_payload["request_id"] = options.request_id
            event_emitter.emit(
                "RUNTIME_READY",
                payload=ready_payload,
            )
        print(
            "status=READY subscription=/cup_pose",
            flush=True,
            file=status_stream,
        )
        mark("ready")
        mark("get_one.begin")
        sample = source.get_one(options.cup_pose_timeout_s)
        mark("get_one.end")
        stop_flags.raise_if_stopped()
        print(
            f"status=POSE_ACCEPTED source_stamp_ns={sample.source_stamp_ns} "
            f"session_id={options.session_id} reset_epoch={options.expected_reset_epoch}",
            flush=True,
            file=status_stream,
        )
        truth_observer = runtime.cup_scene_observer(
            node,
            options.session_id,
            options.expected_reset_epoch,
        )
        mark("truth.observe_initial.begin")
        initial = truth_observer.observe(5.0)
        mark("truth.observe_initial.end")
        validate_mujoco_scene_identity(
            initial,
            expected_session_id=options.session_id,
            expected_reset_epoch=options.expected_reset_epoch,
        )
        mark("bind_scene_source.begin")
        binder = getattr(runtime, "bind_scene_source", None)
        if binder is not None:
            model_path = (share_dir / execution_inputs["scene_path"] if execution_inputs is not None
                          else share_dir / "assets/mujoco/scene.xml")
            scene_age = _execution_state_max_age_s(share_dir, teacher_run=teacher_run)
            scene_source_binding = binder(node, session_id=options.session_id,
                reset_epoch=options.expected_reset_epoch, model_path=model_path,
                expected_model=execution_inputs, max_age_s=.1,
                **({} if scene_age is None else {"scene_max_age_s": scene_age}))
        elif execution_inputs is not None:
            raise RuntimeError("DYNAMIC_SOURCE_CLOCK_BINDING_REQUIRED")
        mark("bind_scene_source.end")
        mark("task_scene_port.begin")
        task_scene = runtime.task_scene_port(
            node,
            "mujoco",
            loaded.template.planning_timeout_s,
        )
        if event_stream is not None and hasattr(task_scene, "on_service_call"):
            from ..act.scene_operation import make_scene_operation_hook
            task_scene.on_service_call = make_scene_operation_hook(event_stream, state=lambda: "SETUP")
        mark("task_scene_port.end")
        mark("prepare_dynamic_cup_scene.begin")
        perception_error = None
        perception_error_failed = False
        if teacher_run:
            # telemetry only: a pose that cannot be compared (degenerate quaternion, missing truth) never refuses the run
            try:
                from ..application.cup_pose_preflight import perception_error as measure_perception_error
                perception_error = measure_perception_error(sample, initial)
            except Exception:  # noqa: BLE001
                perception_error, perception_error_failed = None, True
        prepare_dynamic_cup_scene(
            sample,
            initial,
            loaded.template,
            geometry,
            task_scene,
            **({"perception_gate": False} if teacher_run else {}),
        )
        mark("prepare_dynamic_cup_scene.end")
        mark("validate_cup_scene.1.observe.begin")
        observed = truth_observer.observe(5.0)
        mark("validate_cup_scene.1.observe.end")
        mark("validate_cup_scene.1.check.begin")
        validate_cup_scene(sample, observed, loaded.template, **({"perception_gate": False} if teacher_run else {}))
        mark("validate_cup_scene.1.check.end")
        mark("validate_cup_scene.2.observe.begin")
        observed = truth_observer.observe(5.0)
        mark("validate_cup_scene.2.observe.end")
        mark("validate_cup_scene.2.check.begin")
        validate_cup_scene(sample, observed, loaded.template, **({"perception_gate": False} if teacher_run else {}))
        mark("validate_cup_scene.2.check.end")
        mark("resolve_motion_targets.begin")
        targets = runtime.resolve_motion_targets(sample, loaded.template)
        mark("resolve_motion_targets.end")
        mark("reachability_preflight.begin")
        reachability = runtime.reachability_preflight(
            node,
            sample,
            loaded.template,
            getattr(initial, "reset_epoch", None),
        )
        mark("reachability_preflight.end")
        stop_flags.raise_if_stopped()
        _write_reachability_evidence(
            reachability_file,
            options.session_id,
            reachability,
            ik_backend=ik_backend,
        )
        # UNREACHABLE is the Teacher's own decision, taken before any motion: the execution is constructed only to write its
        # terminal manifest (IDLE -> ERROR, no action), so the host reads a sealed Teacher failure instead of a missing receipt.
        # Any other non-REACHABLE status (UNKNOWN) is not a decision and stays an error that writes no manifest.
        target_unreachable = reachability.status.value == "UNREACHABLE"
        if not target_unreachable and reachability.status.value != "REACHABLE":
            raise RuntimeError("DYNAMIC_TARGET_REACHABILITY_UNKNOWN")
        mark("execution.construct.begin")
        execution = runtime.execution(

            node,
            loaded.template,
            targets,
            session_id=options.session_id,
            expected_reset_epoch=options.expected_reset_epoch,
            evidence_file=evidence_file,
            urdf_path=share_dir / "assets" / "mujoco" / "so101.urdf",
            policy_path=loaded.path,
            policy_sha256=loaded.sha256,
            workflow_id=getattr(options, "workflow_id", None),
            request_id=getattr(options, "request_id", None),
            parallel_lease_identity=parallel_lease_identity,
            ik_backend=ik_backend,
            **({} if event_stream is None else {"event_stream": event_stream}),
        )
        mark("execution.construct.end")
        execution._task_geometry = geometry
        if getattr(options, "final_stop_proof", False) is True:
            execution.final_stop_proof_enabled = True
        if inject_failure_at is not None:
            execution.inject_failure_at = State(inject_failure_at)
        if execution_inputs is not None:
            execution._execution_snapshot_root = share_dir
            # the freeze names the Teacher execution policy
            execution._select_execution_policy()
        if scene_source_binding is not None:
            execution._scene_source_observer = scene_source_binding.observer
            execution._scene_source_binding = scene_source_binding
        if execution_inputs is not None:
            execution._release_runtime_policy = {"kind": "ACT_ENDPOINT_DEVELOPMENT_RUNTIME", "schema_version": 1,
                **{key: value for key, value in frozen["runtime_policy"].items() if key != "sha256"}}
            # The activated contact policy's cup force/compression limits and the collision geometry, from the same
            # frozen inputs the broker-era Teacher read. A mismatch refuses before any motion.
            from . import teacher_safety
            # the r10b limits and the collision geometry are only the thresholds and the pair filter of the telemetry. The watches
            # subscribe but record (never latch); a failed load marks the summary incomplete and refuses nothing (design 2, S09).
            summary = execution._process_summary
            execution._perception_error = perception_error
            if perception_error_failed:
                summary.note_incomplete("PERCEPTION_ERROR_UNAVAILABLE")
            try:
                safety = teacher_safety.load_frozen_safety(Path(manifest_option))
            except Exception as error:  # noqa: BLE001 - non-gating
                safety = None
                execution._safety_limits_error = f"SAFETY_LOAD_FAILED:{_failure_code(error)}"
            if safety is not None:
                execution._safety_limits = summary.limits = safety.limits
                watch = teacher_safety.CollisionWatch(
                    process_pairs=safety.process_pairs, known_geoms=safety.known_geoms, session_id=options.session_id,
                    reset_epoch=options.expected_reset_epoch, record_only=True, tap=summary,
                    clock=execution._monotonic)
                watch.attach(node)
                execution._collision_watch = watch
            else:
                summary.note_incomplete("COLLISION_GEOMETRY_UNAVAILABLE")
            hazards = teacher_safety.PhysicsHazardWatch(
                session_id=options.session_id, reset_epoch=options.expected_reset_epoch, limits=None,
                state_getter=lambda: execution._safety_state, clock=execution._monotonic, record_only=True, tap=summary)
            hazards.attach(node)
            hazards.arm()
            execution._physics_hazard_watch = hazards
        execution._stop_flags = stop_flags
        # A Teacher run (the minimal runtime gates) runs its own workflow definition: the same forward states, no RECOVER_* chain.
        workflow_options = {}
        if teacher_run:
            from ..core.workflow import TEACHER_WORKFLOW
            workflow_options = {"workflow": TEACHER_WORKFLOW}
        if target_unreachable:
            finish_setup("accepted")
            result = _unreachable_pre_motion_result()
        else:
            mark("build_actions.begin")
            actions = profile_actions(
                runtime.build_actions(execution, targets, **workflow_options),
                profiler,
            )
            mark("build_actions.end")
            runner = runtime.runner(
                actions,
                session_id=options.session_id,
                policy_bundle_sha256=loaded.sha256,
                # The runner reads the Teacher's own evidence, no copy: it used to be wrapped by a recorder that appended every
                # observation to a list nothing ever read (an unbounded Teacher-side data copy with no consumer, removed in A4a).
                world_observer=ExecutionSnapshotObserver(execution),
                **workflow_options,
            )
            finish_setup("accepted")
            # The attempt deadline is frozen here, from the frozen execution policy. The watchdog thread only sets a flag:
            # the monitor, the gripper hook and the state machine read it on the executing thread.
            deadline_s = (getattr(execution, "_execution_policy", None) or {}).get("execution_deadline_s")
            if deadline_s is not None:
                stop_flags.arm_deadline(deadline_s)
                watchdog = DeadlineWatchdog(stop_flags)
                watchdog.start()
            stop_flags.raise_if_stopped()
            mark("runner.run.begin")
            result = runner.run(RunRequest(mode=RunMode.EXECUTE))
    except Exception as error:
        finish_setup("rejected", _failure_code(error))
        primary_failure = _failure_code(error)
        primary_message = error
        if execution is not None:
            try:
                _finish_failed_execution(execution, error)
            except BaseException as finish_error:
                secondary_failures.append(("DYNAMIC_EXECUTION_FINISH_FAILED", finish_error))
    else:
        try:
            execution.finish(result)
        except BaseException as finish_error:
            if result.status.value == "DONE":
                primary_failure = "DYNAMIC_EXECUTION_FINISH_FAILED"
                primary_message = finish_error
            else:
                secondary_failures.append(("DYNAMIC_EXECUTION_FINISH_FAILED", finish_error))
        if result.status.value != "DONE":
            primary_failure = "DYNAMIC_EXECUTION_FAILED"
            if result.failure is not None and result.failure.code:
                primary_failure = result.failure.code
    finally:
        _ACTIVE_PHASE_TIMER = None
        if watchdog is not None:
            watchdog.stop()
        if restore_signals is not None:
            restore_signals()
        phase_timer.stop_stall_sampler()
        phase_timer.emit("ok" if primary_failure is None else primary_failure)
        cleanup_token = (
            profiler.start_span("runtime.cleanup")
            if profiler is not None
            else None
        )
        if execution is None and event_stream is not None:
            # No execution took the stream over (the run failed before it was constructed): retire it here, bounded.
            try:
                event_stream.close(flush_timeout_s=1.0)
                if event_stream_close is not None:
                    event_stream_close()
            except Exception:
                pass
        cleanup = _cleanup_dynamic_execute(
            runtime=runtime,
            initialized_here=initialized_here,
            node=node,
            execution=execution,
            task_scene=task_scene,
            truth_observer=truth_observer,
            scene_source_binding=scene_source_binding,
        )
        if cleanup_token is not None:
            profiler.finish_span(
                cleanup_token,
                outcome="ok" if not cleanup.failures else "error",
                attributes={"failure_count": len(cleanup.failures)},
            )

        teacher_cleanup_failures = tuple(cleanup.failures)

    if primary_failure is not None:
        emit_failure(primary_failure)
        fields = {"failure": primary_failure}
        if result is not None:
            fields["evidence"] = evidence_file
        if primary_message is not None:
            fields["message"] = primary_message
        print(status_line("ERROR", **fields), file=status_stream)
        for failure, error in secondary_failures:
            print(
                status_line("ERROR", failure=failure, message=error, secondary=True),
                file=status_stream,
            )
        if teacher_cleanup_failures:
            print(
                status_line(
                    "ERROR",
                    failure="DYNAMIC_EXECUTION_CLEANUP_FAILED",
                    message=_CleanupOutcome(teacher_cleanup_failures).message,
                    secondary=True,
                ),
                file=status_stream,
            )
        return 1

    if teacher_cleanup_failures:
        emit_failure("DYNAMIC_EXECUTION_CLEANUP_FAILED")
        print(
            status_line(
                "ERROR",
                failure="DYNAMIC_EXECUTION_CLEANUP_FAILED",
                message=_CleanupOutcome(teacher_cleanup_failures).message,
                workflow_status="DONE",
            ),
            file=status_stream,
        )
        return 1

    if event_emitter is not None:
        event_emitter.emit(
            "RUNTIME_COMPLETED",
            payload={"manifest_path": str(evidence_file), "runtime_exit_code": 0},
        )
        terminal_emitted = True
    print(
        status_line(
            "DONE",
            strategy="dynamic",
            evidence=evidence_file,
            transition_count=result.transition_count,
        ),
        file=status_stream,
    )
    return 0
