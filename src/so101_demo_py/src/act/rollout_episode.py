"""One closed-loop rollout episode: reset -> gate -> resume -> recorder -> nodes -> loop -> stop -> settle -> endpoint -> retire.

The state machine owns the order and the verdicts; every effect goes through injected ports, so it is exercised with fakes and
holds no ROS, MuJoCo or GPU import. The ports (an object with the methods below) are:

    reset(scene) -> receipt                      the reset boundary (reset_epoch, simulation_session_id, simulation_time_s)
    initial_gate(scene, receipt)                 raises when the gate rejects the reset world
    resume_physics(receipt) -> bool
    start_recorder(scene) -> recorder            recorder.finish() -> facts with "failure"
    open_session(scene, receipt, attempt_id)     creates the executor's nodes (AFTER the gate: the gate's exact node inventory
                                                 refuses extra nodes) and returns the session:
        begin(session_id, attempt_id), sim_time(), spin(), observe() -> (observation, audit) | None,
        submit_prefix(prefix) -> goal id, stop(reason), stop_confirmed() -> bool, cup_pose() -> world observation, close()
    runner, inference                            the policy runner and the one-in-flight inference boundary
    cancel_motion(), confirm_no_controller_goal() -> bool, monotonic()

Decisions (design 2026-10-18, D2 to D6): the loop is free-running and anchored to simulation time, one inference per new
observation set; a late reply or a prefix that is late at submission sends nothing (the previous goal holds) and is counted; with
no fresh observation for the frozen `state_unavailable_stop_s` the executor stops with `STOPPED_SAFETY`; the horizon is the frozen
`execution_deadline_s` and there is no early-stop rule; the neck is not commanded and its drift is logged. A verdict is DONE (the
endpoint PASS with a confirmed stop), FAILED, NO_MOTION (the arm never moved), or INVALID (an infrastructure fault: re-run).
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import traceback

from .contracts import ContractError, validate_action_prefix
from .joints import clamp_positions
from .policy import to_action_prefix
from .rollout_execution import PREFIX_END_TOLERANCE_S, ChunkEnsembler, default_mode
from .rollout_targets import evaluate_rollout_endpoint, rollout_targets

#: Reply refusals of the inference boundary that mean "the answer came too late to describe the present".
LATE_REPLY_ERRORS = ("INFERENCE_TIMEOUT", "INFERENCE_REPLY_STALE")
SUBSTITUTIONS = {
    "start_target": "commanded_reset_pose",
    "completed": "horizon_reached_with_confirmed_stop",
}


@dataclass(frozen=True)
class RolloutSettings:
    """The runtime values of an episode, every one taken from the frozen inputs manifest or the rollout config."""

    execution_deadline_s: float
    state_unavailable_stop_s: float
    settle_s: float
    no_motion_threshold_rad: float
    stop_wait_s: float
    #: the longest (wall) wait for the first joint state and the cup pose after the nodes exist, before the loop starts
    ready_wait_s: float
    #: a prefix that exceeds a joint limit by at most this many rad is clamped to the limit instead of refused; None (the key is
    #: absent from `config/act/rollout.yaml`) keeps the refusal. A logic parameter: it changes what is sent to the controller.
    joint_limit_clamp_tolerance_rad: float | None = None

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if name == "joint_limit_clamp_tolerance_rad" and value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError("ROLLOUT_SETTINGS_INVALID")


class _Abort(Exception):
    """An infrastructure fault that ends the episode as INVALID; `args[0]` is the reason."""


def _text(error: BaseException) -> str:
    return (str(error) or type(error).__name__)[:300]


def _noop_sink():
    class Sink:
        def step(self, row): ...
        def world(self, row): ...
        def event(self, row): ...
    return Sink()


class _Loop:
    """The mutable state of one loop, kept out of the verdict code."""

    def __init__(self, observation_keys, execution=None):
        self.counts = {"observations": 0, "inferences": 0, "applied": 0, "late_replies": 0, "prefix_late": 0,
                       "limit_refused": 0, "skipped_observations": 0, "prefix_wait_observations": 0,
                       "clamped_steps": 0}
        #: the execution mode (None: the bundle's own, one inference per observation); an open-loop prefix holds the next
        #: inference until its last target time (`hold_until`), and an ensembling mode keeps the chunks (`ensembler`)
        self.execution = execution
        self.hold_until = None
        self.ensembler = None
        if execution is not None and execution.ensembling:
            self.ensembler = ChunkEnsembler(execution.ensemble_m, execution.chunk_size)
        self.sequence = 0
        self.pending = None
        self.outcome = None
        self.first_state = None
        self.arm_max = 0.0
        self.neck_max = 0.0
        #: the observed states are the six arm joints only: no neck is measured, so no neck drift is reported
        self.no_neck_state = False
        self.observation_keys = observation_keys

    def note_state(self, state):
        if self.first_state is None:
            self.first_state = list(state)
        self.arm_max = max(self.arm_max, max(abs(a - b) for a, b in zip(state[:6], self.first_state[:6])))
        if len(state) > 6:
            self.neck_max = max(self.neck_max, max(abs(a - b) for a, b in zip(state[6:], self.first_state[6:])))
        else:
            self.no_neck_state = True


def _step_row(pending, **fields):
    row = {"sequence": pending["sequence"], "observation_sim_s": pending["observation"]["sim_time_s"],
           "state": list(pending["observation"]["state"]), "audit": pending["audit"],
           "submit_sim_s": pending["submit_sim_s"], "submit_wall_s": pending["submit_wall_s"]}
    row.update(fields)
    return row


def _resolve(loop, ports, session, sink, settings):
    """Poll the in-flight request once and act on the answer. Returns after at most one resolution."""

    pending = loop.pending
    try:
        reply = ports.inference.poll()
    except ValueError as error:
        reason = str(error)
        if reason not in LATE_REPLY_ERRORS:
            raise _Abort(f"INFERENCE_FAILED: {_text(error)}") from error
        ports.inference.abandon()
        loop.pending = None
        loop.counts["late_replies"] += 1
        sink.step(_step_row(pending, late=True, held=True, applied=False, reason=reason,
                            reply_sim_s=session.sim_time(), reply_wall_s=ports.monotonic()))
        return
    if not reply:
        return
    loop.pending = None
    reply_sim, reply_wall = session.sim_time(), ports.monotonic()
    try:
        prediction = ports.runner.predict_from_chunk(pending["observation"], pending["sequence"], reply["actions"])
        prefix = to_action_prefix(prediction)
    except ValueError as error:
        raise _Abort(f"INFERENCE_FAILED: {_text(error)}") from error
    extra = {}
    if loop.ensembler is not None:
        # the chunk joins the ensemble before the late check: a late chunk is still a valid prediction for the later steps
        try:
            loop.ensembler.add(pending["observation"]["sim_time_s"], reply["actions"])
            action, contributors = loop.ensembler.action_at(prefix["target_times_s"][0])
            prefix = validate_action_prefix(dict(prefix, positions=(action,)))
        except (ValueError, ContractError) as error:
            raise _Abort(f"INFERENCE_FAILED: ENSEMBLE: {_text(error)}") from error
        extra["ensemble"] = {"m": loop.execution.ensemble_m, "contributors": contributors}
    tolerance = settings.joint_limit_clamp_tolerance_rad
    if tolerance is not None:
        # an overshoot of a joint limit of at most the tolerance is moved onto the limit; one above it (any joint of the prefix)
        # leaves the prefix as it is, and the executor refuses it as before
        try:
            positions, clamps = clamp_positions(prefix["positions"], tolerance)
        except ValueError:
            clamps = []
        if clamps:
            prefix = dict(prefix, positions=positions)
            extra["clamped"] = True
            extra["clamps"] = clamps
            loop.counts["clamped_steps"] += 1
    row = _step_row(pending, late=False, reply_sim_s=reply_sim, reply_wall_s=reply_wall,
                    latency_wall_s=round(reply_wall - pending["submit_wall_s"], 6),
                    reply_age_s=reply.get("age_s"), chunk=[list(map(float, step)) for step in reply["actions"]],
                    prefix=prefix, **extra)
    try:
        goal = session.submit_prefix(prefix)
    except ValueError as error:
        # the adapter refused before sending anything: the previous goal holds, and the loop goes on
        code = str(error)
        counter = "prefix_late" if code.startswith("PREFIX_LATE") else "limit_refused"
        loop.counts[counter] += 1
        sink.step(dict(row, held=True, applied=False, reason=code))
        return
    except PermissionError as error:
        loop.counts["limit_refused"] += 1
        sink.step(dict(row, held=True, applied=False, reason=_text(error)))
        return
    except RuntimeError as error:
        sink.step(dict(row, held=True, applied=False, reason=_text(error)))
        raise _Abort(f"CONTROLLER_PAIR_FAILED: {_text(error)}") from error
    loop.counts["applied"] += 1
    if loop.execution is not None and loop.execution.open_loop:
        # the prefix runs open-loop: the next inference starts from the first observation at its end
        loop.hold_until = prefix["target_times_s"][-1]
    sink.step(dict(row, held=False, applied=True, goal_id=goal))


def _drive(session, ports, settings, sink, loop):
    """The control loop. Ends with `loop.outcome` set to HORIZON or STOPPED_SAFETY."""

    start = session.sim_time()
    deadline = start + settings.execution_deadline_s
    last_fresh_sim, last_fresh_wall = start, ports.monotonic()
    while True:
        now = session.sim_time()
        if now >= deadline:
            loop.outcome = "HORIZON"
            return
        if loop.pending is not None:
            _resolve(loop, ports, session, sink, settings)
        fresh = session.observe()
        if fresh is not None:
            observation, audit = fresh
            last_fresh_sim, last_fresh_wall = now, ports.monotonic()
            loop.counts["observations"] += 1
            loop.note_state(observation["state"])
            pose = session.cup_pose()
            if pose is not None:
                sink.world({"observation_sim_s": observation["sim_time_s"], **pose})
            if loop.pending is None and loop.hold_until is not None \
                    and observation["sim_time_s"] < loop.hold_until - PREFIX_END_TOLERANCE_S:
                loop.counts["prefix_wait_observations"] += 1
                sink.step({"sequence": None, "skipped": True, "observation_sim_s": observation["sim_time_s"],
                           "state": list(observation["state"]), "audit": audit, "late": False, "held": True,
                           "applied": False, "reason": "PREFIX_IN_PROGRESS"})
            elif loop.pending is None:
                loop.hold_until = None
                sequence = loop.sequence
                try:
                    ports.inference.submit(observation, sequence=sequence)
                except ValueError as error:
                    raise _Abort(f"INFERENCE_FAILED: {_text(error)}") from error
                loop.sequence += 1
                loop.counts["inferences"] += 1
                loop.pending = {"sequence": sequence, "observation": observation, "audit": audit,
                                "submit_sim_s": now, "submit_wall_s": ports.monotonic()}
            else:
                loop.counts["skipped_observations"] += 1
                sink.step({"sequence": None, "skipped": True, "observation_sim_s": observation["sim_time_s"],
                           "state": list(observation["state"]), "audit": audit, "late": False, "held": True,
                           "applied": False})
        elif (now - last_fresh_sim >= settings.state_unavailable_stop_s
              or ports.monotonic() - last_fresh_wall >= settings.state_unavailable_stop_s):
            loop.outcome = "STOPPED_SAFETY"
            return
        session.spin()


def _await_ready(session, ports, settings):
    """Wait, bounded in wall time, for the first joint state and then the cup pose; returns the start cup observation.

    The nodes are created after the initial gate, so their subscriptions need a moment to discover the publishers. Starting the
    loop without the first joint state would make the simulation clock unreadable, and starting without the cup pose would leave
    the episode without its start observation: both refuse the episode as an infrastructure fault instead."""

    deadline = ports.monotonic() + settings.ready_wait_s
    while not session.ready():
        if ports.monotonic() >= deadline:
            raise _Abort(f"SESSION_NOT_READY: joint_state not received within {settings.ready_wait_s} s")
        session.spin()
    while True:
        pose = session.cup_pose()
        if pose is not None:
            return pose
        if ports.monotonic() >= deadline:
            raise _Abort(f"SESSION_NOT_READY: cup_pose not received within {settings.ready_wait_s} s")
        session.spin()


def _await_stop(session, ports, settings, reason):
    """Command the stop and wait, in wall time, for the terminal acknowledgement and zero-speed feedback."""

    session.stop(reason)
    deadline = ports.monotonic() + settings.stop_wait_s
    while not session.stop_confirmed() and ports.monotonic() < deadline:
        session.spin()
    return session.stop_confirmed()


def _stop_diagnostics(session):
    """What the session says about an unconfirmed stop (empty when it cannot say)."""

    reader = getattr(session, "stop_diagnostics", None)
    try:
        return reader() if callable(reader) else None
    except Exception as error:      # noqa: BLE001
        return {"unreadable": _text(error)}


def _settle(session, ports, settings):
    """Advance simulation time by `settle_s` after the confirmed stop, then take the one end observation."""

    target = session.sim_time() + settings.settle_s
    wall_deadline = ports.monotonic() + settings.settle_s + settings.state_unavailable_stop_s
    while True:
        if session.sim_time() >= target:
            pose = session.cup_pose()
            if pose is not None and pose["simulation_time_s"] >= target:
                return pose
        if ports.monotonic() >= wall_deadline:
            return None
        session.spin()


def _verdict(result, loop, stop_confirmed, endpoint, settings):
    """(verdict, reason) of a run that reached its end: INVALID for an unproven stop or an unconfirmed endpoint."""

    if loop.outcome == "STOPPED_SAFETY":
        return "INVALID", "OBSERVATION_STALE"
    if not stop_confirmed:
        return "INVALID", "STOP_UNCONFIRMED"
    if endpoint is None:
        return "INVALID", "END_OBSERVATION_UNAVAILABLE"
    if endpoint["result"] == "UNCONFIRMED":
        return "INVALID", "ENDPOINT_UNCONFIRMED: " + "; ".join(endpoint["reasons"])[:280]
    if loop.arm_max < settings.no_motion_threshold_rad:
        return "NO_MOTION", "NO_MOTION"
    if endpoint["result"] == "PASS":
        return "DONE", None
    return "FAILED", "; ".join(endpoint["reasons"])


def _check_runner(execution, runner) -> None:
    """The policy runner must have been built for the mode: the open-loop prefix size, or one step for the ensemble."""

    have = getattr(runner, "execution_prefix", None)
    if execution.source == "cli" and have != execution.execution_prefix:
        raise ValueError(f"EXECUTION_RUNNER_MISMATCH: runner prefix {have}, mode {execution.execution_prefix}")


def run_episode(*, scene, attempt_id, ports, settings, snapshot_targets, endpoint_policy, sink=None, execution=None) -> dict:
    """Run one episode on `scene` and return its result document (the caller writes it; nothing here touches the disk).

    `execution` is the run-time execution mode (`rollout_execution.ExecutionMode`); None keeps the bundle's frozen behaviour."""

    sink = sink or _noop_sink()
    if execution is not None:
        _check_runner(execution, ports.runner)
    effective = execution if execution is not None else default_mode(getattr(ports.runner, "execution_prefix", None))
    wall_start = ports.monotonic()
    result = {"scene_id": scene["scene_id"], "group": scene.get("group"), "attempt_id": attempt_id,
              "verdict": None, "done": False, "reason": None, "status": None, "phases": [],
              "counts": None, "motion": None, "stop": {"confirmed": False}, "endpoint": None,
              "timing": {}, "substitutions": dict(SUBSTITUTIONS), "receipt": None, "gate": None, "recorder": None,
              "execution": effective.document()}
    start_target, end_target = rollout_targets(snapshot_targets, cup_position_world_m=scene["cup_position_world_m"])
    result["targets"] = {"start_target": start_target, "end_target": end_target}
    loop = _Loop(None, execution)
    recorder = session = None
    fault = None
    start_observation = end_observation = None
    stop_confirmed = False
    try:
        try:
            receipt = ports.reset(scene)
        except Exception as error:
            raise _Abort(f"RESET_FAILED: {_text(error)}") from error
        result["receipt"] = dict(receipt)
        result["phases"].append("reset")
        try:
            result["gate"] = ports.initial_gate(scene, receipt)
        except Exception as error:
            raise _Abort(f"GATE_FAILED: {_text(error)}") from error
        result["phases"].append("gate")
        try:
            resumed = ports.resume_physics(receipt)
        except Exception as error:
            raise _Abort(f"RESUME_FAILED: {_text(error)}") from error
        if resumed is not True:
            raise _Abort("RESUME_FAILED")
        result["phases"].append("resume")
        try:
            recorder = ports.start_recorder(scene)
        except Exception as error:
            raise _Abort(f"RECORDER_FAILED: {_text(error)}") from error
        result["phases"].append("recorder")
        session_id = receipt["simulation_session_id"]
        try:
            session = ports.open_session(scene, receipt, attempt_id)
            session.begin(session_id, attempt_id)
            ports.runner.reset(session_id, attempt_id)
        except Exception as error:
            raise _Abort(f"SESSION_OPEN_FAILED: {_text(error)}") from error
        result["phases"].append("nodes")
        start_observation = _await_ready(session, ports, settings)
        loop_start_sim = session.sim_time()
        result["timing"]["loop_start_sim_s"] = loop_start_sim
        try:
            _drive(session, ports, settings, sink, loop)
        finally:
            try:
                result["timing"]["loop_sim_s"] = round(session.sim_time() - loop_start_sim, 6)
            except Exception:       # noqa: BLE001 - the clock failing here must not hide the error that ended the loop
                result["timing"]["loop_sim_s"] = None
        result["phases"].append("loop")
        result["status"] = "STOPPED_SAFETY" if loop.outcome == "STOPPED_SAFETY" else "COMPLETED"
        stop_confirmed = _await_stop(session, ports, settings,
                                     "STOPPED_SAFETY" if loop.outcome == "STOPPED_SAFETY" else "ROLLOUT_HORIZON")
        result["stop"] = {"confirmed": stop_confirmed, "sim_time_s": session.sim_time()}
        if not stop_confirmed:
            result["stop"]["diagnostics"] = _stop_diagnostics(session)
        result["phases"].append("stop")
        if stop_confirmed and loop.outcome != "STOPPED_SAFETY":
            end_observation = _settle(session, ports, settings)
            result["phases"].append("settle")
    except Exception as error:      # noqa: BLE001 - an _Abort names its reason; any other error is still an infrastructure fault
        fault = str(error) if isinstance(error, _Abort) else f"EPISODE_FAULT: {type(error).__name__}: {_text(error)}"
        result["status"] = "FAULT"
        # the reason is capped; the trace of the error (and of the error that caused it) is kept whole for the evidence
        result["fault_trace"] = "".join(traceback.format_exception(error))[-6000:]
        if session is not None and not stop_confirmed:
            try:
                result["stop"] = {"confirmed": _await_stop(session, ports, settings, "ROLLOUT_FAULT"), "after_fault": True}
            except Exception as stop_error:     # noqa: BLE001
                result["stop"] = {"confirmed": False, "after_fault": True, "error": _text(stop_error)}
            stop_confirmed = result["stop"]["confirmed"] is True
            if not stop_confirmed:
                fault += " | STOP_UNCONFIRMED"
                result["stop"]["diagnostics"] = _stop_diagnostics(session)
    finally:
        retire_errors = []
        if loop.pending is not None:
            # a request still in flight at the end is never applied; the boundary must be free for the next episode
            try:
                ports.inference.abandon()
            except Exception as error:
                retire_errors.append("INFERENCE_ABANDON_FAILED: " + _text(error))
        if recorder is not None:
            try:
                facts = recorder.finish()
                result["recorder"] = facts
                if isinstance(facts, dict) and (facts.get("failure") or facts.get("ready") is False):
                    retire_errors.append("RECORDER_FAILED: " + str(facts.get("failure"))[:200])
            except Exception as error:
                retire_errors.append("RECORDER_FAILED: " + _text(error))
        if session is not None:
            try:
                session.close()
            except Exception as error:
                retire_errors.append("SESSION_CLOSE_FAILED: " + _text(error))
        try:
            ports.cancel_motion()
            if ports.confirm_no_controller_goal() is not True:
                retire_errors.append("RETIRE_UNCONFIRMED")
        except Exception as error:
            retire_errors.append("RETIRE_UNCONFIRMED: " + _text(error))
    result["counts"] = dict(loop.counts)
    result["motion"] = {"max_arm_displacement_rad": round(loop.arm_max, 9), **({} if loop.no_neck_state else {"neck_deviation_max": round(loop.neck_max, 9)}),
                        "no_motion_threshold_rad": settings.no_motion_threshold_rad}
    if loop.pending is not None:
        sink.step(_step_row(loop.pending, late=False, held=True, applied=False, reason="UNRESOLVED_AT_END"))
    if fault is None and start_observation is not None and stop_confirmed and loop.outcome != "STOPPED_SAFETY":
        result["endpoint"] = evaluate_rollout_endpoint(
            endpoint_policy, start_target=start_target, end_target=end_target,
            start_observation=start_observation, end_observation=end_observation) if end_observation is not None else None
        sink.event({"endpoint": result["endpoint"]})
    if fault is not None:
        verdict, reason = "INVALID", fault
    else:
        verdict, reason = _verdict(result, loop, stop_confirmed, result["endpoint"], settings)
        if loop.outcome == "STOPPED_SAFETY" and result["endpoint"] is None:
            result["endpoint"] = None
    if retire_errors and verdict != "INVALID":
        verdict, reason = "INVALID", retire_errors[0]
    elif retire_errors:
        reason = reason + " | " + retire_errors[0]
    result.update(verdict=verdict, reason=reason, done=verdict == "DONE")
    result["retire_errors"] = retire_errors
    result["timing"]["wall_s"] = round(ports.monotonic() - wall_start, 6)
    return result
