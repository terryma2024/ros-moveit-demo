"""The measurement clock, feedback transport, stop confirmation and the MuJoCo stop flights."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import math
from pathlib import Path
import time

from so101_demo.act.head_search.deadband_measurement.plant import (
    MujocoClosedLoopPlant,
)
from so101_demo.act.head_search.stop_measurement.contracts import (
    CAL_STATIONARY_UNSETTLED,
    CAL_STOP_PROOF_UNCONFIRMED,
    DEFAULT_REALTIME,
    DEFAULT_REVOKE_OFFSETS_S,
    DEFAULT_SAMPLES_PER_POSE,
    DEFAULT_STOP_BUDGET_S,
    MONITORED_JOINTS,
    PACING_TOLERANCE,
    RECEIPT_ARTIFACT,
    _mapping,
    _positive_int,
    _positive_number,
    _refuse,
)
from so101_demo.act.head_search.timing_measurement.contracts import (
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_EVIDENCE_MISSING,
    SETTLE_CONSECUTIVE_STEPS,
    SIMULATION_TIME_BASE,
    _number,
)
from so101_demo.act.head_search.timing_measurement.control import (
    SettleTracker,
)
from so101_demo.act.head_search.timing_params import p99_9


class MeasurementClock:
    """The monotonic clock the flight hands to the installed stop criterion.

    The criterion stamps every receipt with the clock it is given, so the flight gives it a clock it can read
    afterwards: the receipt's own stamp is then the criterion's own reading and not an estimate taken beside
    it, and no private state of the installed port has to be touched.
    """

    def __init__(self, monotonic=time.monotonic) -> None:
        self._monotonic = monotonic
        self.last: float | None = None
        self.reads = 0

    def __call__(self) -> float:
        self.last = float(self._monotonic())
        self.reads += 1
        return self.last


class ControllerFeedbackTransport:
    """The subscription the installed stop criterion registers, with an explicit delivery call.

    `RosControllerPort` registers its feedback callback on the node it is built with. This stand-in keeps that
    callback and delivers `sensor_msgs/JointState` messages to it exactly as rclpy would, so the criterion is
    the installed one and only the transport is the harness's.
    """

    def __init__(self) -> None:
        self.topic: str | None = None
        self.message_type = None
        self.callback = None
        self.delivered = 0

    def create_subscription(self, topic, message_type, callback, qos_profile):
        self.topic = topic
        self.message_type = message_type
        self.callback = callback
        return None

    def deliver(self, message) -> None:
        if self.callback is None:
            raise ValueError("nothing registered a feedback callback on this transport")
        self.callback(message)
        self.delivered += 1


def joint_state_message(*, joint_names, positions, velocities, stamp_s):
    """One `sensor_msgs/JointState` carrying the sampled feedback, as the plant reports it."""

    from sensor_msgs.msg import JointState

    names = [str(name) for name in joint_names]
    message = JointState()
    message.name = names
    message.position = [float(value) for value in positions]
    message.velocity = [float(value) for value in velocities]
    nanoseconds = int(round(float(stamp_s) * 1e9))
    message.header.stamp.sec, message.header.stamp.nanosec = divmod(nanoseconds, 1000000000)
    message.header.frame_id = ""
    return message


def controller_stop_criterion(*, stop_velocity_rad_s, max_age_s, clock=None):
    """The installed stop criterion over the monitored joints, with its transport and clock."""

    from so101_demo.adapters.act.ros_execution import RosControllerPort

    running = MeasurementClock() if clock is None else clock
    transport = ControllerFeedbackTransport()
    port = RosControllerPort(
        transport,
        None,
        MONITORED_JOINTS,
        stop_velocity_rad_s=stop_velocity_rad_s,
        max_age_s=max_age_s,
        monotonic=running,
    )
    return port, transport, running


def confirm_stop(
    *,
    plant,
    port,
    transport,
    clock,
    hold_rad,
    stop_budget_s,
    index,
    reason,
    period_s,
    motion=None,
    revoke_offset_s=None,
    anchor=None,
    pose_rad=None,
    pose_kind=None,
    declared_production_latency_s=None,
) -> dict:
    """Revoke the motion and count the receipts until three consecutive samples qualify.

    This is the stop proof the Task-8 measurement protocol fixes: the request is stamped when the revoke is
    handed to the plant, every feedback period then delivers one receipt to the installed stop criterion, and
    the proof is complete at the third consecutive qualifying receipt. A window that never carries three
    consecutive qualifying receipts inside its declared budget refuses the whole measurement; every receipt's
    own values are kept, so a single slow one can be checked against the bound phase 7 computes later.
    """

    plant.hold_command(float(hold_rad))
    request_monotonic = clock()
    request_sim = float(plant.time_s)
    samples: list[dict] = []
    consecutive = 0
    qualifying_indices: list[int] = []
    confirming: dict | None = None
    cycles_per_sample = max(1, int(round(period_s / float(plant.control_period_s))))
    while float(plant.time_s) - request_sim <= float(stop_budget_s):
        for _ in range(cycles_per_sample):
            plant.step_control_cycle()
        sample = dict(plant.feedback_sample())
        transport.deliver(
            joint_state_message(
                joint_names=MONITORED_JOINTS,
                positions=sample["joint_positions"],
                velocities=sample["joint_velocities"],
                stamp_s=sample["sim_s"],
            )
        )
        received = clock.last
        stopped = bool(port.stopped())
        if stopped:
            consecutive += 1
            qualifying_indices.append(len(samples))
        else:
            consecutive = 0
            qualifying_indices = []
        samples.append(
            {
                "index": len(samples),
                "receive_monotonic_s": received,
                "receive_sim_s": float(sample["sim_s"]),
                "velocity_rad_s": [float(value) for value in sample["velocity_rad_s"]],
                "yaw_rad": float(sample["yaw_rad"]),
                "reference_rad": float(sample["reference_rad"]),
                "position_error_rad": float(sample["position_error_rad"]),
                "qualifying": stopped,
                "consecutive_qualifying": consecutive,
            }
        )
        if consecutive >= 3:
            confirming = samples[-1]
            break
    if confirming is None:
        raise _refuse(
            CAL_STOP_PROOF_UNCONFIRMED,
            f"stop proof {index} ({reason}) found no three consecutive qualifying feedback receipts inside "
            f"its {stop_budget_s} s budget: the widest window recorded was "
            f"{max((sample['consecutive_qualifying'] for sample in samples), default=0)} consecutive "
            f"qualifying samples out of {len(samples)}, and a proof that never confirmed is not written",
        )
    latency = float(confirming["receive_monotonic_s"]) - float(request_monotonic)
    sim_latency = float(confirming["receive_sim_s"]) - request_sim
    factor = None if latency <= 0.0 else sim_latency / latency
    return {
        "index": index,
        "reason": reason,
        "anchor": anchor,
        "pose_rad": pose_rad,
        "pose_kind": pose_kind,
        "revoke_offset_s": revoke_offset_s,
        "motion_target_rad": None if motion is None else float(motion["target_rad"]),
        "hold_rad": float(hold_rad),
        "stop_request_monotonic_s": float(request_monotonic),
        "stop_request_sim_s": request_sim,
        "third_confirming_receive_monotonic_s": float(confirming["receive_monotonic_s"]),
        "third_confirming_receive_sim_s": float(confirming["receive_sim_s"]),
        "latency_s": latency,
        "sim_latency_s": sim_latency,
        "window_real_time_factor": factor,
        "pacing_faithful": factor is not None and abs(factor - 1.0) <= PACING_TOLERANCE,
        "confirming_sample_indices": list(qualifying_indices[-3:]),
        "third_confirming_sample_index": int(confirming["index"]),
        "feedback_samples": samples,
        "exceeds_declared_production_latency_s": (
            None
            if declared_production_latency_s is None
            else latency > float(declared_production_latency_s)
        ),
    }


def _pose_records(poses) -> list[dict]:
    records = []
    for index, pose in enumerate(poses):
        record = _mapping("a declared pose", pose)
        records.append(
            {
                "pose_index": index,
                "anchor": record.get("anchor"),
                "pose_rad": _number(record, "a declared pose", "pose_rad"),
                "pose_kind": record.get("pose_kind"),
            }
        )
    return records


def _plant_of(request: Mapping, factory):
    """The plant of one flight, built from the declared plant request (or the request itself in a test)."""

    return factory(request.get("plant_request") or request)


def _declared_settle(request: Mapping) -> dict:
    """The declared settle rule of one flight, as the floor plan request carries it."""

    source = request.get("plant_request") if isinstance(request.get("plant_request"), Mapping) else request
    return {
        "settle_velocity_rad_s": source.get("settle_velocity_rad_s"),
        "goal_tolerance_rad": source.get("goal_tolerance_rad"),
        "settle_consecutive_steps": source.get("settle_consecutive_steps", SETTLE_CONSECUTIVE_STEPS),
    }


def run_stationary_flight(*, request: Mapping, plant_factory=None) -> dict:
    """Hold every declared pose and sample the monitored joints at the declared feedback period."""

    factory = MujocoStopFlight if plant_factory is None else plant_factory
    poses = _pose_records(request["poses"])
    feedback_period = _positive_number("the declared feedback period", request["feedback_period_s"])
    control_period = _positive_number("the sealed control period", request["control_period_s"])
    samples_per_pose = _positive_int(
        "the declared samples per pose", request.get("samples_per_pose", DEFAULT_SAMPLES_PER_POSE)
    )
    cycles_per_sample = max(1, int(round(feedback_period / control_period)))
    declared_settle = _declared_settle(request)
    plant = _plant_of(request, factory)
    records: list[dict] = []
    try:
        for pose in poses:
            settle = plant.command_through_admission(
                pose["pose_rad"],
                purpose="anchor_positioning" if pose["pose_kind"] == "anchor" else "plan_stop",
            )
            if not settle["settled"]:
                raise _refuse(
                    CAL_STATIONARY_UNSETTLED,
                    f"the pose {pose['pose_rad']} rad of the anchor {pose['anchor']!r} never settled under "
                    f"the declared rule (final velocity {settle['final_velocity_rad_s']} rad/s, final position "
                    f"error {settle['final_position_error_rad']} rad), so its velocity noise is not the "
                    f"stationary state's and is not sampled",
                )
            samples = []
            for _ in range(samples_per_pose):
                for _ in range(cycles_per_sample):
                    plant.step_control_cycle()
                sample = plant.feedback_sample()
                samples.append(
                    {
                        "sim_s": float(sample["sim_s"]),
                        "velocity_rad_s": [float(value) for value in sample["velocity_rad_s"]],
                        "joint_velocities": [float(value) for value in sample["joint_velocities"]],
                        "joint_positions": [float(value) for value in sample["joint_positions"]],
                        "yaw_rad": float(sample["yaw_rad"]),
                        "reference_rad": float(sample["reference_rad"]),
                        "position_error_rad": float(sample["position_error_rad"]),
                        "time_base": SIMULATION_TIME_BASE,
                    }
                )
            magnitudes = [
                max(abs(value) for value in sample["velocity_rad_s"]) for sample in samples
            ]
            records.append(
                {
                    **pose,
                    "settle": dict(settle),
                    "samples": samples,
                    "p99_9_velocity_rad_s": p99_9(magnitudes),
                    "max_velocity_rad_s": max(magnitudes),
                }
            )
    finally:
        close = getattr(plant, "close", None)
        if callable(close):
            close()
    magnitudes = [
        max(abs(value) for value in sample["velocity_rad_s"])
        for record in records
        for sample in record["samples"]
    ]
    return {
        "records": records,
        "flight": {
            "feedback_period_s": feedback_period,
            "control_period_s": control_period,
            "simulation_timestep_s": float(plant.simulation_timestep_s),
            "samples_per_pose": samples_per_pose,
            "sample_count": len(magnitudes),
            "pose_count": len(records),
            "stationary_p99_9_velocity_rad_s": p99_9(magnitudes),
            "max_velocity_rad_s": max(magnitudes),
            "settle_velocity_rad_s": declared_settle["settle_velocity_rad_s"],
            "goal_tolerance_rad": declared_settle["goal_tolerance_rad"],
            "settle_consecutive_steps": int(declared_settle["settle_consecutive_steps"]),
            "real_time_factor": _real_time_factor(plant),
            "pacing": _pacing(plant),
            "ros_nodes_started": False,
        },
    }


def run_submission_flight(*, request: Mapping, plant_factory=None) -> dict:
    """Submit the installed controller's own targets through the admission port and time every lead."""

    factory = MujocoStopFlight if plant_factory is None else plant_factory
    submissions = _mapping_sequence("a declared submission", request["submissions"])
    if not submissions:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            "no submission was declared: the installed controller's plan selects no target for this anchor",
        )
    plant = _plant_of(request, factory)
    records: list[dict] = []
    try:
        for index, submission in enumerate(submissions):
            record = plant.command_through_admission(
                _number(submission, "a declared submission", "target_rad"),
                purpose=submission["purpose"],
            )
            records.append(
                {
                    "index": index,
                    "purpose": submission["purpose"],
                    "submitted_by": submission["submitted_by"],
                    "time_base": SIMULATION_TIME_BASE,
                    **{key: value for key, value in record.items()},
                }
            )
    finally:
        close = getattr(plant, "close", None)
        if callable(close):
            close()
    return {
        "records": records,
        "flight": {
            "control_period_s": float(request["control_period_s"]),
            "simulation_timestep_s": float(plant.simulation_timestep_s),
            "submission_count": len(records),
            "minimum_lead_s": min(record["lead_s"] for record in records),
            "maximum_lead_s": max(record["lead_s"] for record in records),
            "real_time_factor": _real_time_factor(plant),
            "pacing": _pacing(plant),
            "ros_nodes_started": False,
        },
    }


def run_stop_proof_flight(*, request: Mapping, plant_factory=None) -> dict:
    """Revoke real motions at the declared offsets and prove every stop with the installed criterion."""

    factory = MujocoStopFlight if plant_factory is None else plant_factory
    poses = _pose_records(request["poses"])
    offsets = [_positive_number("a declared revoke offset", value, allow_zero=True)
               for value in request.get("revoke_offsets_s", DEFAULT_REVOKE_OFFSETS_S)]
    if not offsets:
        raise _refuse(CAL_TIMING_EVIDENCE_MISSING, "no revoke offset was declared, so no stop is requested")
    control_period = _positive_number("the sealed control period", request["control_period_s"])
    feedback_period = _positive_number("the declared feedback period", request["feedback_period_s"])
    stop_budget = _positive_number("the declared stop budget", request.get("stop_budget_s", DEFAULT_STOP_BUDGET_S))
    plant = _plant_of(request, factory)
    port, transport, clock = controller_stop_criterion(
        stop_velocity_rad_s=request["stop_velocity_rad_s"],
        max_age_s=request["max_age_s"],
    )
    records: list[dict] = []
    try:
        for pose in poses:
            for offset in offsets:
                cycles = max(1, int(round(offset / control_period)))
                motion = plant.command_through_admission(
                    pose["pose_rad"], purpose="plan_stop", max_cycles=cycles
                )
                records.append(
                    confirm_stop(
                        plant=plant,
                        port=port,
                        transport=transport,
                        clock=clock,
                        hold_rad=plant.yaw_rad,
                        stop_budget_s=stop_budget,
                        index=len(records),
                        reason="plan_stop_revoke",
                        period_s=feedback_period,
                        motion=motion,
                        revoke_offset_s=offset,
                        anchor=pose["anchor"],
                        pose_rad=pose["pose_rad"],
                        pose_kind=pose["pose_kind"],
                        declared_production_latency_s=request.get("declared_production_latency_s"),
                    )
                )
    finally:
        close = getattr(plant, "close", None)
        if callable(close):
            close()
    latencies = [record["latency_s"] for record in records]
    return {
        "records": records,
        "flight": {
            "feedback_period_s": feedback_period,
            "control_period_s": control_period,
            "simulation_timestep_s": float(plant.simulation_timestep_s),
            "stop_velocity_rad_s": float(request["stop_velocity_rad_s"]),
            "max_age_s": float(request["max_age_s"]),
            "stop_budget_s": stop_budget,
            "revoke_offsets_s": offsets,
            "declared_production_latency_s": request.get("declared_production_latency_s"),
            "proof_count": len(records),
            "p99_9_latency_s": p99_9(latencies),
            "slowest_latency_s": max(latencies),
            "real_time_factor": _real_time_factor(plant),
            "pacing": _pacing(plant),
            "ros_nodes_started": False,
        },
    }


def _mapping_sequence(name: str, value) -> list[Mapping]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        raise _refuse(CAL_TIMING_EVIDENCE_MISSING, f"{name} sequence is empty or not a sequence")
    for item in value:
        _mapping(name, item)
    return list(value)


def _real_time_factor(plant) -> float | None:
    factor = getattr(plant, "real_time_factor", None)
    return None if not callable(factor) else factor()


def _pacing(plant) -> dict:
    return {
        "realtime": bool(getattr(plant, "realtime", False)),
        "max_lag_s": getattr(plant, "max_lag_s", None),
        "rule": (
            "the plant is paced to the monotonic clock (as the production MuJoCo loop is), so the monotonic "
            "stop latency is a real-time quantity and not an artefact of a fast in-process loop; the achieved "
            "real-time factor and the largest lag are recorded beside every measurement"
        ),
    }


class MujocoStopFlight(MujocoClosedLoopPlant):
    """The sealed scene's neck, driven through an admission port and sampled as the stop path sees it.

    This is the only place in this module that imports MuJoCo, and it does so inside the call. It holds the
    six arm joints where the sealed model starts them, commands the neck's own position actuator once per
    sealed control cycle, samples the velocities of the monitored joints, and paces the loop to the monotonic
    clock. It commands the simulated neck only: no ROS node starts, no detector runs, no hardware is
    addressed.
    """

    def __init__(self, request: Mapping) -> None:
        super().__init__(request)
        self.control_period_s = float(request["control_period_s"])
        self.feedback_period_s = float(request["feedback_period_s"])
        self.realtime = bool(request.get("realtime", DEFAULT_REALTIME))
        self.max_lag_s = 0.0
        self.stop_velocity_rad_s = float(request["stop_velocity_rad_s"])
        self.max_age_s = float(request["max_age_s"])
        self.monitored_joints = tuple(request.get("monitored_joints") or MONITORED_JOINTS)
        self._dof_addresses: list[int] = []
        self._qpos_addresses: list[int] = []
        for name in self.monitored_joints:
            joint = self._mujoco.mj_name2id(self._model, self._mujoco.mjtObj.mjOBJ_JOINT, name)
            if joint < 0:
                raise _refuse(
                    CAL_TIMING_EVIDENCE_CONTRADICTORY,
                    f"the sealed scene {request['scene_path']} has no {name!r} joint, so its velocity cannot "
                    f"be sampled",
                )
            self._dof_addresses.append(int(self._model.jnt_dofadr[joint]))
            self._qpos_addresses.append(int(self._model.jnt_qposadr[joint]))
            actuator = self._mujoco.mj_name2id(
                self._model, self._mujoco.mjtObj.mjOBJ_ACTUATOR, name
            )
            if actuator >= 0:
                # hold every monitored joint where the sealed model starts it: the arm must not be pulled to
                # a command this flight never declared
                self._data.ctrl[actuator] = float(self._data.qpos[self._qpos_addresses[-1]])
        self._reference_rad = self.yaw_rad
        self._goal_pending: float | None = None
        self._start_monotonic = time.monotonic()
        self._start_sim_s = self.time_s

    def joint_velocity_vector(self) -> tuple[float, ...]:
        return tuple(float(self._data.qvel[address]) for address in self._dof_addresses)

    def joint_position_vector(self) -> tuple[float, ...]:
        return tuple(float(self._data.qpos[address]) for address in self._qpos_addresses)

    def hold_command(self, rad: float) -> None:
        self._data.ctrl[self._actuator] = float(rad)
        self._reference_rad = float(rad)

    def step_control_cycle(self) -> None:
        for _ in range(self._steps_per_control):
            self._mujoco.mj_step(self._model, self._data)
        self._pace()

    def _pace(self) -> None:
        if not self.realtime:
            return
        target = self._start_monotonic + (self.time_s - self._start_sim_s)
        lag = target - time.monotonic()
        if lag > 0.0:
            time.sleep(lag)
        self.max_lag_s = max(self.max_lag_s, time.monotonic() - target)

    def real_time_factor(self) -> float | None:
        wall = time.monotonic() - self._start_monotonic
        return None if wall <= 0.0 else (self.time_s - self._start_sim_s) / wall

    def feedback_sample(self) -> dict:
        return {
            "sim_s": self.time_s,
            "yaw_rad": self.yaw_rad,
            "reference_rad": self._reference_rad,
            "position_error_rad": self._reference_rad - self.yaw_rad,
            "joint_velocities": list(self.joint_velocity_vector()),
            "joint_positions": list(self.joint_position_vector()),
            "velocity_rad_s": list(self.joint_velocity_vector()),
        }

    def command_through_admission(self, target_rad: float, *, purpose: str, max_cycles=None) -> dict:
        """Snapshot one goal, drain it at the next control cycle, and settle on it (or stop early)."""

        target = float(target_rad)
        snapshot_sim = self.time_s
        reference_before = self._reference_rad
        tracker = SettleTracker(
            settle_velocity_rad_s=self._settle_velocity_rad_s,
            goal_tolerance_rad=self._goal_tolerance_rad,
            consecutive_steps=self._settle_consecutive_steps,
        )
        budget = max(1, int(math.ceil(self.max_settle_s / self.control_period_s)) + 1)
        limit = budget if max_cycles is None else min(budget, int(max_cycles))
        self._goal_pending = target
        cycles = 0
        consumed_sim = None
        settled = reached = False
        while cycles < limit:
            if self._goal_pending is not None:
                self.hold_command(self._goal_pending)
                self._goal_pending = None
            self.step_control_cycle()
            cycles += 1
            if consumed_sim is None:
                consumed_sim = self.time_s
            error = target - self.yaw_rad
            if abs(error) <= self._goal_tolerance_rad:
                reached = True
            if tracker.observe(self.velocity_rad_s, error):
                settled = True
                break
        if consumed_sim is None:  # pragma: no cover - limit is at least one cycle
            raise _refuse(
                CAL_TIMING_EVIDENCE_MISSING,
                "the admission port drained no goal: no target of this submission reached the plant",
            )
        return {
            "purpose": purpose,
            "target_rad": target,
            "reference_before_rad": reference_before,
            "submit_snapshot_sim_s": snapshot_sim,
            "first_target_sim_s": consumed_sim,
            "plant_consumed_sim_s": consumed_sim,
            "lead_s": consumed_sim - snapshot_sim,
            "control_cycles": cycles,
            "steps": cycles * self._steps_per_control,
            "settled": settled,
            "reached": reached,
            "final_velocity_rad_s": self.velocity_rad_s,
            "final_position_error_rad": target - self.yaw_rad,
            "quiet_steps": tracker.quiet_steps,
        }


def _write(output: Path, document: Mapping, receipt: Mapping) -> None:
    (output / RECEIPT_ARTIFACT).write_text(
        json.dumps(dict(receipt), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    artifact = Path(document["path"])
    artifact.write_text(json.dumps(dict(document), indent=2, sort_keys=True) + "\n", encoding="utf-8")
