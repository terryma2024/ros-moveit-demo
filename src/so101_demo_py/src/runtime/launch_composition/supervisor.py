"""The end-to-end process supervisor and the perception launch exit status."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import signal
import tempfile
import time

from launch import Action
from launch.actions import (
    EmitEvent,
    ExecuteProcess,
    OpaqueFunction,
    TimerAction,
)
from launch.events.process import SignalProcess

from so101_demo.runtime.launch_composition.common import _terminal_launch_actions
from so101_demo.runtime.workflow_events import (
    EventDecoder,
    EventEmitter,
    WorkflowEvent,
    WorkflowProtocolError,
    WorkflowState,
)


@dataclass(frozen=True, slots=True)
class _PerceptionEvidencePaths:
    run_root: Path
    perception: Path
    dynamic: Path


@dataclass(slots=True)
class PerceptionLaunchExitStatus:
    """First terminal child status observed by the perception launch graph."""

    returncode: int | None = None
    workflow_terminal: bool = False

    def record(self, returncode: int) -> None:
        if self.returncode is None:
            self.returncode = returncode

    def mark_workflow_terminal(self) -> None:
        self.workflow_terminal = True

    def resolve(self, launch_service_returncode: int) -> int:
        if self.returncode in {None, 0}:
            return launch_service_returncode
        return self.returncode


@dataclass(slots=True)
class _OwnedE2EProcess:
    action: ExecuteProcess
    label: str
    required_long_lived: bool
    cleanup_only: bool = False
    started: bool = False
    exited: bool = False


class E2ESupervisor:
    """Drive one E2E graph exclusively from validated child events."""

    _RUNTIME_TIMEOUT_S = 600.0
    _VALIDATOR_TIMEOUT_S = 30.0
    _RECOVERY_TIMEOUT_S = 30.0
    # Teardown deadlines are bounded escalation budgets; a saturated host needs more
    # than the original ten seconds to reap a real process tree.
    _SIGINT_TIMEOUT_S = 20.0
    _SIGTERM_TIMEOUT_S = 10.0
    _SIGKILL_TIMEOUT_S = 10.0

    def __init__(
        self,
        *,
        workflow_id: str,
        request_id: str,
        session_id: str,
        backend: str,
        source_commit: str | None,
        installed_prefix: str | None,
        run_root: Path,
        result_file: Path,
        text_agent_action: ExecuteProcess,
        perception_action: ExecuteProcess,
        validator_action: ExecuteProcess,
        container_cleanup_actions: tuple[ExecuteProcess, ...] = (),
        model_provenance: dict[str, object] | None = None,
        perception_startup_timeout_s: float = 30.0,
        cup_pose_timeout_s: float = 45.0,
        clock_ns=time.time_ns,
    ) -> None:
        self.workflow_id = workflow_id
        self.request_id = request_id
        self.session_id = session_id
        self.backend = backend
        self.source_commit = source_commit
        self.installed_prefix = installed_prefix
        self.run_root = run_root
        self.result_file = result_file
        self.text_agent_action = text_agent_action
        self.perception_action = perception_action
        self.validator_action = validator_action
        self.container_cleanup_actions = container_cleanup_actions
        self.model_provenance = dict(model_provenance or {})
        self.perception_startup_timeout_s = perception_startup_timeout_s
        self.cup_pose_timeout_s = cup_pose_timeout_s
        self._clock_ns = clock_ns
        self.workflow_state = WorkflowState(backend)
        self.current_phase = "STACK_READINESS"
        self.primary_failure: dict[str, object] | None = None
        self.secondary_failures: list[dict[str, object]] = []
        self.shutting_down = False
        self._recovery_pending = False
        self.accepted = False
        self._cleanup_observations: list[dict[str, object]] = []
        self.runtime_exit_code: int | None = None
        self.perception_started = False
        self.validator_started = False
        self._terminal_children: set[int] = set()
        self._events: list[WorkflowEvent] = []
        self._owned: dict[int, _OwnedE2EProcess] = {}
        self._deadline_generations: dict[str, int] = {}
        # Events may be delivered late on a loaded host; the floor binds them to this
        # run instead of rejecting a slow read as a protocol violation.
        self._run_started_ns = self._clock_ns()
        self._decoders = {
            id(text_agent_action): EventDecoder(
                workflow_id, frozenset({"text_agent", "dynamic_runtime"}),
                not_before_ns=self._run_started_ns,
            ),
            id(perception_action): EventDecoder(
                workflow_id, frozenset({"perception"}), not_before_ns=self._run_started_ns,
            ),
            id(validator_action): EventDecoder(
                workflow_id, frozenset({"e2e_validator"}), not_before_ns=self._run_started_ns,
            ),
        }
        self.register_owned(
            text_agent_action,
            label="Text Agent and dynamic runtime",
            required_long_lived=False,
        )
        self.register_owned(
            perception_action,
            label="perception",
            required_long_lived=backend == "color_geometry",
        )
        self.register_owned(
            validator_action,
            label="E2E validator",
            required_long_lived=False,
        )
        for cleanup_action in container_cleanup_actions:
            self.register_owned(
                cleanup_action,
                label="owned perception container cleanup",
                required_long_lived=False,
                cleanup_only=True,
            )

    def register_owned(
        self,
        action: ExecuteProcess,
        *,
        label: str,
        required_long_lived: bool,
        started: bool = False,
        cleanup_only: bool = False,
    ) -> None:
        self._owned[id(action)] = _OwnedE2EProcess(
            action=action,
            label=label,
            required_long_lived=required_long_lived,
            cleanup_only=cleanup_only,
            started=started,
        )

    def _atomic_write(self, path: Path, data: bytes) -> None:
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=self.run_root, prefix=f".{path.name}.", delete=False
            ) as stream:
                temporary = stream.name
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary is not None:
                try:
                    Path(temporary).unlink()
                except OSError:
                    pass

    def _persist_trace(self) -> None:
        content = b"".join(
            (
                json.dumps(
                    asdict(event),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                + "\n"
            ).encode("utf-8")
            for event in self._events
        )
        self._atomic_write(self.run_root / "workflow-events.ndjson", content)

    def _failure_record(
        self,
        *,
        component: str,
        code: str,
        message: str,
        exit_code: int | None = None,
    ) -> dict[str, object]:
        return {
            "component": component,
            "code": code,
            "phase": self.current_phase,
            "message": message,
            "exit_code": exit_code,
            "timestamp_ns": self._clock_ns(),
        }

    def _record_failure(self, **values) -> None:
        record = self._failure_record(**values)
        if self.primary_failure is None:
            self.primary_failure = record
        else:
            self.secondary_failures.append(record)

    def _artifact_paths(self) -> dict[str, str]:
        return {
            "event_trace": str(self.run_root / "workflow-events.ndjson"),
            "result": str(self.result_file),
            "perception": str(self.run_root / "perception"),
            "dynamic": str(self.run_root / "dynamic"),
            "acceptance": str(self.run_root / "acceptance"),
        }

    def _write_result(self, *, cleanup_complete: bool) -> None:
        acceptance: dict[str, object] = {}
        acceptance_path = self.run_root / "acceptance" / "result.json"
        if acceptance_path.is_file() and not acceptance_path.is_symlink():
            try:
                loaded = json.loads(acceptance_path.read_text(encoding="utf-8"))
                if type(loaded) is dict:
                    acceptance = loaded
            except (OSError, ValueError):
                acceptance = {}
        document = {
            "schema_version": 1,
            "workflow_id": self.workflow_id,
            "request_id": self.request_id,
            "simulation_session_id": self.session_id,
            "source_commit": self.source_commit,
            "source_commit_authority": "DEBUG_METADATA_ONLY",
            "installed_prefix": self.installed_prefix,
            "perception_backend": self.backend,
            "model_provenance": self.model_provenance,
            "event_trace": [asdict(event) for event in self._events],
            "primary_failure": self.primary_failure,
            "secondary_failures": self.secondary_failures,
            "runtime_exit_code": self.runtime_exit_code,
            "physical_outcome": acceptance.get("physical_outcome", {}),
            "planning_scene_outcome": acceptance.get(
                "planning_scene_outcome", {}
            ),
            "machine_accepted": self.accepted,
            "cleanup_observations": list(self._cleanup_observations),
            "owned_process_cleanup": {
                "complete": cleanup_complete,
                "remaining": [
                    owned.label
                    for owned in self._owned.values()
                    if owned.started and not owned.exited
                ],
            },
            "artifact_paths": self._artifact_paths(),
        }
        self._atomic_write(
            self.result_file,
            (json.dumps(document, indent=2, sort_keys=True) + "\n").encode(),
        )

    def arm_timeout(self, phase: str, seconds: float) -> TimerAction:
        generation = self._deadline_generations.get(phase, 0) + 1
        self._deadline_generations[phase] = generation
        return TimerAction(
            period=seconds,
            actions=[
                OpaqueFunction(
                    function=lambda _context: self.on_timeout(phase, generation)
                )
            ],
        )

    def _cancel_timeout(self, phase: str) -> None:
        self._deadline_generations[phase] = (
            self._deadline_generations.get(phase, 0) + 1
        )

    def on_timeout(self, phase: str, generation: int) -> list[Action]:
        if generation != self._deadline_generations.get(phase):
            return []
        if self.shutting_down and phase not in {"SIGINT", "SIGTERM", "SIGKILL"}:
            return []
        if phase == "RECOVERY":
            return self._begin_teardown()
        if phase in {"SIGINT", "SIGTERM", "SIGKILL"}:
            next_signal = {
                "SIGINT": (signal.SIGTERM, "SIGTERM", self._SIGTERM_TIMEOUT_S),
                "SIGTERM": ("SIGKILL", "SIGKILL", self._SIGKILL_TIMEOUT_S),
            }.get(phase)
            remaining = [
                owned.label for owned in self._owned.values()
                if owned.started and not owned.exited
            ]
            # Escalation is a mechanism, not a verdict: on a loaded host the first
            # signals can be delivered late, so only processes that survive the whole
            # escalation chain are a cleanup failure.
            self._cleanup_observations.append({
                "phase": phase,
                "result": "completed_within_deadline" if not remaining else "escalated",
                "remaining": remaining,
                "timestamp_ns": self._clock_ns(),
            })
            if not remaining:
                return self._finish_cleanup()
            if phase == "SIGTERM":
                # Reaching SIGKILL means the tree did not exit cooperatively, which is a
                # real cleanup failure even though the kill itself will succeed.
                self._record_failure(
                    component="supervisor",
                    code="OWNED_PROCESS_CLEANUP_TIMEOUT",
                    message="owned processes survived SIGTERM",
                )
            if next_signal is not None:
                signal_number, next_phase, seconds = next_signal
                return [
                    *self._signal_actions(signal_number),
                    self.arm_timeout(next_phase, seconds),
                ]
            self._record_failure(
                component="supervisor",
                code="OWNED_PROCESS_CLEANUP_TIMEOUT",
                message=f"owned processes survived {phase}",
            )
            try:
                self._write_result(cleanup_complete=False)
            except OSError:
                pass
            return _terminal_launch_actions(
                "SO-101 E2E owned process cleanup failed", failed=True
            )
        self._record_failure(
            component="supervisor",
            code="WORKFLOW_TIMEOUT",
            message=f"{phase} deadline expired",
        )
        return self._begin_failure_shutdown()

    def _signal_actions(self, signal_number) -> list[Action]:
        actions: list[Action] = []
        for owned in self._owned.values():
            if not owned.started or owned.exited:
                continue
            actions.append(
                EmitEvent(
                    event=SignalProcess(
                        signal_number=signal_number,
                        process_matcher=lambda candidate, target=owned.action: candidate
                        is target,
                    )
                )
            )
        return actions

    def _begin_failure_shutdown(self) -> list[Action]:
        if self.shutting_down or self._recovery_pending:
            return []
        self._recovery_pending = True
        self.current_phase = "RECOVERY"
        # The dynamic runtime owns action-level cancellation/recovery. Let its
        # SIGINT handler finish that bounded recovery before global escalation.
        text = self._owned[id(self.text_agent_action)]
        if not text.started or text.exited:
            return self._begin_teardown()
        return [
            EmitEvent(
                event=SignalProcess(
                    signal_number=signal.SIGINT,
                    process_matcher=lambda candidate: candidate
                    is self.text_agent_action,
                )
            ),
            self.arm_timeout("RECOVERY", self._RECOVERY_TIMEOUT_S),
        ]

    def _begin_teardown(self) -> list[Action]:
        self.shutting_down = True
        self.current_phase = "TEARDOWN"
        actions = self._signal_actions(signal.SIGINT)
        for cleanup_action in self.container_cleanup_actions:
            owned = self._owned[id(cleanup_action)]
            if not owned.started:
                owned.started = True
                actions.append(cleanup_action)
        if not actions:
            return self._finish_cleanup()
        actions.append(self.arm_timeout("SIGINT", self._SIGINT_TIMEOUT_S))
        return actions

    def _finish_cleanup(self) -> list[Action]:
        remaining = [
            item for item in self._owned.values() if item.started and not item.exited
        ]
        if remaining:
            return []
        try:
            self._write_result(cleanup_complete=True)
        except OSError as error:
            self._record_failure(
                component="supervisor",
                code="EVIDENCE_WRITE_FAILED",
                message=str(error),
            )
            return _terminal_launch_actions(
                "SO-101 E2E result write failed", failed=True
            )
        failed = self.primary_failure is not None or not self.accepted
        reason = "SO-101 E2E failed" if failed else "SO-101 E2E accepted"
        return _terminal_launch_actions(reason, failed=failed)

    def on_scene_exit(self, returncode: int) -> list[Action]:
        if returncode != 0:
            self._record_failure(
                component="scene_setup",
                code="SCENE_SETUP_FAILED",
                message="Planning Scene setup failed",
                exit_code=returncode,
            )
            return self._begin_failure_shutdown()
        self._cancel_timeout("STACK_READINESS")
        lines: list[str] = []
        emitter = EventEmitter(
            self.workflow_id, "supervisor", lines.append, self._clock_ns
        )
        event = emitter.emit("STACK_READY", payload={})
        self._events.append(event)
        try:
            self._persist_trace()
            self.workflow_state.accept(event)
        except (OSError, WorkflowProtocolError) as error:
            self._record_failure(
                component="supervisor",
                code=(
                    "EVIDENCE_WRITE_FAILED"
                    if isinstance(error, OSError)
                    else "EVENT_PROTOCOL_INVALID"
                ),
                message=str(error),
            )
            return self._begin_failure_shutdown()
        self.current_phase = "AGENT"
        self._owned[id(self.text_agent_action)].started = True
        return [self.text_agent_action]

    def _actions_for_event(self, event: WorkflowEvent) -> list[Action]:
        effect = self.workflow_state.accept(event)
        self.current_phase = event.event
        if event.status == "ERROR":
            self._terminal_children.add(id(self._action_for_component(event.component)))
        if effect == "FAIL":
            self._record_failure(
                component=event.component,
                code=event.failure_code or "EVENT_PROTOCOL_INVALID",
                message=f"{event.event} reported failure",
            )
            return self._begin_failure_shutdown()
        if event.event == "RUNTIME_STARTED":
            return [self.arm_timeout("RUNTIME", self._RUNTIME_TIMEOUT_S)]
        if effect == "START_PERCEPTION":
            if self.perception_started:
                raise WorkflowProtocolError("perception already started")
            self.perception_started = True
            self._owned[id(self.perception_action)].started = True
            return [
                self.perception_action,
                self.arm_timeout(
                    "PERCEPTION_STARTUP", self.perception_startup_timeout_s
                ),
            ]
        if event.event == "PERCEPTION_READY":
            self._cancel_timeout("PERCEPTION_STARTUP")
            return [self.arm_timeout("CUP_POSE", self.cup_pose_timeout_s)]
        if event.event == "CUP_POSE_PUBLISHED":
            self._cancel_timeout("CUP_POSE")
            self._terminal_children.add(id(self.perception_action))
        if effect == "START_ACCEPTANCE":
            self._cancel_timeout("RUNTIME")
            if self.validator_started:
                raise WorkflowProtocolError("validator already started")
            self.validator_started = True
            self._terminal_children.add(id(self.text_agent_action))
            self._owned[id(self.validator_action)].started = True
            return [
                self.validator_action,
                self.arm_timeout("VALIDATOR", self._VALIDATOR_TIMEOUT_S),
            ]
        if effect == "ACCEPT":
            self._cancel_timeout("VALIDATOR")
            self.accepted = True
            self._terminal_children.add(id(self.validator_action))
            return self._begin_teardown()
        return []

    def _action_for_component(self, component: str) -> ExecuteProcess:
        if component in {"text_agent", "dynamic_runtime"}:
            return self.text_agent_action
        if component == "perception":
            return self.perception_action
        return self.validator_action

    def on_stdout(self, child: ExecuteProcess, chunk: bytes) -> list[Action]:
        decoder = self._decoders.get(id(child))
        if decoder is None:
            self._record_failure(
                component="supervisor",
                code="EVENT_PROTOCOL_INVALID",
                message="stdout received from unregistered child",
            )
            return self._begin_failure_shutdown()
        actions: list[Action] = []
        try:
            for event in decoder.feed(chunk, now_ns=self._clock_ns()):
                self._events.append(event)
                self._persist_trace()
                actions.extend(self._actions_for_event(event))
        except (OSError, WorkflowProtocolError) as error:
            self._record_failure(
                component="supervisor",
                code=(
                    "EVIDENCE_WRITE_FAILED"
                    if isinstance(error, OSError)
                    else "EVENT_PROTOCOL_INVALID"
                ),
                message=getattr(error, "detail", str(error)),
            )
            actions.extend(self._begin_failure_shutdown())
        return actions

    def on_exit(self, child: ExecuteProcess, returncode: int) -> list[Action]:
        owned = self._owned.get(id(child))
        if owned is None:
            return []
        owned.exited = True
        try:
            decoder = self._decoders.get(id(child))
            if decoder is not None:
                decoder.finish(now_ns=self._clock_ns())
        except WorkflowProtocolError as error:
            self._record_failure(
                component=owned.label,
                code="EVENT_PROTOCOL_INVALID",
                message=error.detail,
                exit_code=returncode,
            )
        if child is self.text_agent_action:
            self.runtime_exit_code = returncode
        if owned.cleanup_only:
            if returncode != 0:
                self._record_failure(
                    component=owned.label,
                    code="OWNED_CONTAINER_CLEANUP_FAILED",
                    message="owned container cleanup returned nonzero",
                    exit_code=returncode,
                )
            return self._finish_cleanup() if self.shutting_down else []
        if self.shutting_down:
            return self._finish_cleanup()
        if self._recovery_pending and child is self.text_agent_action:
            if id(child) not in self._terminal_children and returncode != 0:
                self._record_failure(
                    component=owned.label,
                    code="CHILD_EXITED_WITHOUT_TERMINAL_EVENT",
                    message="child exited during recovery without a terminal event",
                    exit_code=returncode,
                )
            return self._begin_teardown()
        if owned.required_long_lived and not self.accepted:
            self._record_failure(
                component=owned.label,
                code="REQUIRED_PROCESS_EXITED",
                message="required process exited before E2E acceptance",
                exit_code=returncode,
            )
            return self._begin_failure_shutdown()
        if id(child) not in self._terminal_children and returncode != 0:
            self._record_failure(
                component=owned.label,
                code="CHILD_EXITED_WITHOUT_TERMINAL_EVENT",
                message="child exited without a valid terminal event",
                exit_code=returncode,
            )
            return self._begin_failure_shutdown()
        if child is self.text_agent_action and id(child) not in self._terminal_children:
            self._record_failure(
                component=owned.label,
                code="CHILD_EXITED_WITHOUT_TERMINAL_EVENT",
                message="Text Agent exited before runtime terminal event",
                exit_code=returncode,
            )
            return self._begin_failure_shutdown()
        return []
