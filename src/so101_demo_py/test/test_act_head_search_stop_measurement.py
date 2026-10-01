"""The stop and feedback measurement producers: every number is a declaration or a measurement.

The fixtures here are synthetic: a controller declaration whose constants are written in the test, a
controller configuration that declares its own rates, and a scripted plant that reports the velocities the
test asks for. Nothing in this file starts MuJoCo, a detector, a ROS node or a GPU. The last group of tests
hands the produced documents to the installed phase-7 consumers, so the shapes this module writes are the
shapes `so101_head_search_calibration run` reads.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from so101_demo.act import head_search_stop_measurement as stop
from so101_demo.act.head_search_timing_params import (
    CAL_STOP_LATENCY_EXCEEDED,
    CAL_SUBMIT_LEAD_UNVERIFIED,
    compute_stop_latency_s,
    compute_stop_velocity_rad_s,
    compute_submit_lead_s,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

#: the installed controller's own stopped-velocity window, as the running controller declares it
STOP_HEADER = """#ifndef SO101_MUJOCO_SUPPORT__CONTROLLER_STOP_WITNESS_HPP_
#define SO101_MUJOCO_SUPPORT__CONTROLLER_STOP_WITNESS_HPP_

class ControllerStopWitness final
{
public:
  static constexpr size_t required_samples = 51;
  static constexpr int64_t step_ns = 2000000;
  static constexpr int64_t max_age_ns = 200000000;
  static constexpr double stop_velocity_rad_s = 0.002;
};

#endif
"""

CONTROLLERS = """controller_manager:
  ros__parameters:
    update_rate: 500
    neck_controller:
      type: so101_mujoco_support/BrokerOwnedTrajectoryController
joint_state_broadcaster:
  ros__parameters:
    update_rate: 100
neck_controller:
  ros__parameters:
    joints:
    - neck_yaw_joint
"""


def _header(tmp_path: Path, text: str = STOP_HEADER, name: str = "controller_stop_witness.hpp") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _controllers(tmp_path: Path, text: str = CONTROLLERS) -> Path:
    path = tmp_path / "ros2_controllers.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def _documents(tmp_path: Path):
    """A declared tolerance and feedback pair, and the documents the three measurement producers write."""

    header = _header(tmp_path)
    controllers = _controllers(tmp_path)
    tolerance = stop.declared_controller_stop_tolerance(
        installed_declaration=header,
        source_declaration=header,
        controller_config_path=controllers,
    )
    feedback = stop.build_feedback_measurements(
        path=tmp_path / "feedback-measurements.json",
        declaration=stop.read_feedback_declarations(controllers),
        quantisation=stop.declared_quantisation(tmp_path / "absent-quantisation.json"),
    )
    return {
        "header": header,
        "controllers": controllers,
        "tolerance": tolerance,
        "feedback": feedback,
        "controller": stop.build_controller_stop_config(
            path=tmp_path / "controller-stop-config.json",
            tolerance=tolerance,
            controller_config_path=controllers,
        ),
    }


# --- the controller's stopped tolerance: a declaration, cited and cross-checked -----------------------


def test_the_stop_config_reads_the_installed_declaration_and_cites_it(tmp_path: Path) -> None:
    """The controller's own stopped tolerance is a declared constant, never a measured or defaulted one."""

    documents = _documents(tmp_path)
    document = documents["controller"]
    tolerance = documents["tolerance"]

    assert tolerance["stopped_tolerance_rad_s"] == 0.002
    assert tolerance["measured_here"] is False
    assert tolerance["declared_by"]["path"] == str(documents["header"])
    assert tolerance["declared_by"]["constant"] == "stop_velocity_rad_s"
    assert tolerance["declared_by"]["source_line"].strip().endswith("stop_velocity_rad_s = 0.002;")
    assert tolerance["window_samples"] == 51
    assert tolerance["window_step_s"] == 0.002
    assert tolerance["window_max_age_s"] == 0.2
    # the window step is the controller's own update period, so both declarations agree
    assert tolerance["controller_cycle_period_s"] == 0.002
    assert tolerance["cross_checks"]["window_step_matches_controller_period"] is True

    assert document["stopped_tolerance_rad_s"] == 0.002
    assert document["phase"] == "controller_stop_config"
    assert document["measured_here"] is False
    assert document["path"] == str(tmp_path / "controller-stop-config.json")
    assert document["sha256"] == canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    assert document["refusals"] == []


def test_the_stop_config_refuses_a_declaration_that_carries_no_tolerance(tmp_path: Path) -> None:
    """A header that declares the window but no stopped tolerance declares nothing to write."""

    header = _header(tmp_path, STOP_HEADER.replace("  static constexpr double stop_velocity_rad_s = 0.002;\n", ""))
    with pytest.raises(stop.CalibrationStopMeasurementRefused) as refused:
        stop.declared_controller_stop_tolerance(
            installed_declaration=header,
            source_declaration=header,
            controller_config_path=_controllers(tmp_path),
        )
    assert refused.value.code == stop.CAL_CONTROLLER_STOP_TOLERANCE_UNDECLARED


def test_the_stop_config_refuses_two_disagreeing_declarations(tmp_path: Path) -> None:
    """The running controller's declaration is the one to cite: a source that differs is refused."""

    installed = _header(tmp_path, STOP_HEADER, name="installed.hpp")
    source = _header(tmp_path, STOP_HEADER.replace("0.002", "0.010"), name="source.hpp")
    with pytest.raises(stop.CalibrationStopMeasurementRefused) as refused:
        stop.declared_controller_stop_tolerance(
            installed_declaration=installed,
            source_declaration=source,
            controller_config_path=_controllers(tmp_path),
        )
    assert refused.value.code == stop.CAL_CONTROLLER_STOP_TOLERANCE_CONTRADICTORY


def test_the_stop_config_refuses_a_window_step_that_contradicts_the_controller_period(
    tmp_path: Path,
) -> None:
    """A window that does not step at the controller's own period is another controller's declaration."""

    header = _header(tmp_path, STOP_HEADER.replace("step_ns = 2000000", "step_ns = 1000000"))
    with pytest.raises(stop.CalibrationStopMeasurementRefused) as refused:
        stop.declared_controller_stop_tolerance(
            installed_declaration=header,
            source_declaration=header,
            controller_config_path=_controllers(tmp_path),
        )
    assert refused.value.code == stop.CAL_CONTROLLER_STOP_TOLERANCE_CONTRADICTORY


# --- the feedback period and the quantisation resolution ---------------------------------------------


def test_the_feedback_document_declares_both_rates_and_refuses_the_quantisation(tmp_path: Path) -> None:
    """`period_s` is the rate the stop path's feedback arrives at; no resolution is declared anywhere."""

    controllers = _controllers(tmp_path)
    declaration = stop.read_feedback_declarations(controllers)
    assert declaration["period_s"] == 0.01
    assert declaration["feedback_rate_hz"] == 100.0
    assert declaration["controller_cycle_period_s"] == 0.002
    assert declaration["declared_by"]["period_s"]["keys"] == {
        "joint_state_broadcaster": "ros__parameters.update_rate"
    }

    document = stop.build_feedback_measurements(
        path=tmp_path / "feedback-measurements.json",
        declaration=declaration,
        quantisation=stop.undeclared_quantisation(),
    )
    assert document["period_s"] == 0.01
    assert document["controller_cycle_period_s"] == 0.002
    assert document["quantisation_rad"] is None
    assert document["quantisation"]["measured_here"] is False
    assert document["quantisation"]["declared"] is False
    assert [refusal["code"] for refusal in document["refusals"]] == [
        stop.CAL_FEEDBACK_QUANTISATION_UNDECLARED
    ]
    # the undeclared field is `null` and the period is still usable, so the document is written
    assert document["path"] == str(tmp_path / "feedback-measurements.json")


def test_the_feedback_document_derives_a_declared_quantisation(tmp_path: Path) -> None:
    """A declared encoder resolution is a declaration: the resolution is derived from it, not chosen."""

    counts = tmp_path / "encoder-declaration.json"
    counts.write_text(
        json.dumps({"counts_per_revolution": 4096, "joint_travel_rad": 2 * math.pi}),
        encoding="utf-8",
    )
    derived = stop.declared_quantisation(counts)
    assert derived["declared"] is True
    assert derived["measured_here"] is False
    assert derived["quantisation_rad"] == pytest.approx(2 * math.pi / 4096)
    assert derived["declared_by"]["keys"] == {
        "counts_per_revolution": "counts_per_revolution",
        "joint_travel_rad": "joint_travel_rad",
    }

    direct = tmp_path / "quantisation-declaration.json"
    direct.write_text(json.dumps({"quantisation_rad": 0.0001}), encoding="utf-8")
    assert stop.declared_quantisation(direct)["quantisation_rad"] == 0.0001

    controllers = _controllers(tmp_path)
    document = stop.build_feedback_measurements(
        path=tmp_path / "feedback-measurements.json",
        declaration=stop.read_feedback_declarations(controllers),
        quantisation=stop.declared_quantisation(direct),
    )
    assert document["measured_here"] is False
    assert document["quantisation_rad"] == 0.0001
    assert document["refusals"] == []


def test_the_feedback_document_refuses_a_configuration_without_a_feedback_rate(tmp_path: Path) -> None:
    """Without a declared broadcaster rate there is no period the stop path's feedback arrives at."""

    controllers = _controllers(
        tmp_path,
        CONTROLLERS.replace("joint_state_broadcaster:\n  ros__parameters:\n    update_rate: 100\n", ""),
    )
    with pytest.raises(stop.CalibrationStopMeasurementRefused) as refused:
        stop.read_feedback_declarations(controllers)
    assert refused.value.code == stop.CAL_FEEDBACK_PERIOD_UNDECLARED


# --- the installed phase-7 consumers read exactly these shapes ---------------------------------------


def _stationary_document(tmp_path: Path, samples) -> dict:
    path = tmp_path / "stationary-measurements.json"
    body = {
        "schema_version": 1,
        "kind": stop.STATIONARY_KIND,
        "phase": stop.STATIONARY_PHASE,
        "measured_here": True,
        "monitored_joints": list(stop.MONITORED_JOINTS),
        "samples": list(samples),
        "path": str(path),
    }
    return {**body, "sha256": canonical_sha256(body)}


def test_phase_seven_accepts_the_three_documents_and_computes_the_envelope(tmp_path: Path) -> None:
    """`compute_stop_velocity_rad_s` is the consumer: the envelope is the three declared terms' sum."""

    documents = _documents(tmp_path)
    stationary = _stationary_document(
        tmp_path,
        [
            {"index": index, "velocity_rad_s": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, magnitude]}
            for index, magnitude in enumerate((0.0005, 0.001, 0.003, 0.002))
        ],
    )
    (tmp_path / "quantisation.json").write_text(
        json.dumps({"quantisation_rad": 0.0001}), encoding="utf-8"
    )
    feedback = stop.build_feedback_measurements(
        path=tmp_path / "feedback-measurements.json",
        declaration=stop.read_feedback_declarations(documents["controllers"]),
        quantisation=stop.declared_quantisation(tmp_path / "quantisation.json"),
    )
    block = compute_stop_velocity_rad_s(
        stationary=stationary, feedback=feedback, controller=documents["controller"]
    )
    # nearest-rank p99.9 of four samples is the largest one, and the two other terms are declared
    assert block["value"] == pytest.approx(0.003 + 0.0001 / 0.01 + 0.002)
    assert block["observed_distribution"]["quantisation_rad"] == 0.0001
    assert block["observed_distribution"]["stopped_tolerance_rad_s"] == 0.002
    assert [reference["sha256"] for reference in block["input_evidence"]] == [
        stationary["sha256"],
        feedback["sha256"],
        documents["controller"]["sha256"],
    ]


def test_phase_seven_refuses_the_stationary_document_without_a_declared_quantisation(
    tmp_path: Path,
) -> None:
    """The honest consequence of an undeclared resolution: phase 7 refuses rather than assuming one."""

    documents = _documents(tmp_path)
    stationary = _stationary_document(
        tmp_path, [{"index": 0, "velocity_rad_s": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.001]}]
    )
    with pytest.raises(ValueError, match="quantisation_rad"):
        compute_stop_velocity_rad_s(
            stationary=stationary,
            feedback=documents["feedback"],
            controller=documents["controller"],
        )


def test_phase_seven_accepts_the_submission_document_and_refuses_a_wall_clock_one(tmp_path: Path) -> None:
    """A submission is verified in simulation time or refused: the phase's own rule, on this document."""

    path = tmp_path / "controller-submissions.json"
    body = {
        "schema_version": 1,
        "kind": stop.SUBMISSIONS_KIND,
        "phase": stop.SUBMISSIONS_PHASE,
        "time_base": "simulation",
        "simulation_timestep_s": 0.002,
        "path": str(path),
        "samples": [
            {
                "index": 0,
                "time_base": "simulation",
                "submit_snapshot_sim_s": 0.0,
                "first_target_sim_s": 0.002,
            },
            {
                "index": 1,
                "time_base": "simulation",
                "submit_snapshot_sim_s": 0.4,
                "first_target_sim_s": 0.402,
            },
        ],
    }
    document = {**body, "sha256": canonical_sha256(body)}
    mujoco = {
        "path": str(tmp_path / "mujoco-measurements.json"),
        "sha256": "a" * 64,
        "simulation_timestep_s": 0.002,
    }
    block = compute_submit_lead_s(submissions=document, mujoco=mujoco)
    assert block["value"] == pytest.approx(0.002 + 0.002)
    assert block["observed_distribution"]["submissions_verified_in_simulation_time"] is True

    wall = json.loads(json.dumps(document))
    wall["samples"][1]["time_base"] = "wall_clock"
    with pytest.raises(Exception) as refused:
        compute_submit_lead_s(submissions=wall, mujoco=mujoco)
    assert getattr(refused.value, "code", None) == CAL_SUBMIT_LEAD_UNVERIFIED


def test_phase_seven_accepts_the_stop_proof_document_and_fails_a_slow_sample(tmp_path: Path) -> None:
    """Every proof's own latency is checked: one slow sample fails, however many fast ones surround it."""

    path = tmp_path / "stop-proofs.json"
    samples = [
        {
            "index": index,
            "stop_request_monotonic_s": float(index),
            "third_confirming_receive_monotonic_s": float(index) + 0.02,
        }
        for index in range(4)
    ]
    body = {
        "schema_version": 1,
        "kind": stop.STOP_PROOFS_KIND,
        "phase": stop.STOP_PROOFS_PHASE,
        "path": str(path),
        "samples": samples,
    }
    document = {**body, "sha256": canonical_sha256(body)}
    feedback = {
        "path": str(tmp_path / "feedback-measurements.json"),
        "sha256": "b" * 64,
        "period_s": 0.01,
    }
    block = compute_stop_latency_s(stop_proofs=document, feedback=feedback)
    assert block["value"] == pytest.approx(0.02 + 0.01)

    # a thousand fast samples make the nearest-rank p99.9 a real percentile, so one slow sample is beyond it
    slow = json.loads(json.dumps(document))
    slow["samples"] = [
        {
            "index": index,
            "stop_request_monotonic_s": float(index),
            "third_confirming_receive_monotonic_s": float(index) + (0.5 if index == 500 else 0.02),
        }
        for index in range(1001)
    ]
    with pytest.raises(Exception) as refused:
        compute_stop_latency_s(stop_proofs=slow, feedback=feedback)
    assert getattr(refused.value, "code", None) == CAL_STOP_LATENCY_EXCEEDED


# --- the simulation-time base proof ------------------------------------------------------------------


def test_the_submission_time_base_proof_accepts_the_step_grid(tmp_path: Path) -> None:
    """Every lead is proved to be the simulation clock's, against the sealed timestep and period."""

    proof = stop.verify_submission_time_base(
        [
            {
                "index": 0,
                "time_base": "simulation",
                "submit_snapshot_sim_s": 0.0,
                "first_target_sim_s": 0.002,
                "lead_s": 0.002,
                "plant_consumed_sim_s": 0.002,
            },
            {
                "index": 1,
                "time_base": "simulation",
                "submit_snapshot_sim_s": 0.4,
                "first_target_sim_s": 0.402,
                "lead_s": 0.002,
                "plant_consumed_sim_s": 0.402,
            },
        ],
        simulation_timestep_s=0.002,
        control_period_s=0.002,
    )
    assert proof["time_base"] == "simulation"
    assert proof["sample_count"] == 2
    assert proof["minimum_lead_s"] == 0.002
    assert proof["maximum_lead_s"] == 0.002

    off_grid = [
        {
            "index": 0,
            "time_base": "simulation",
            "submit_snapshot_sim_s": 0.0,
            "first_target_sim_s": 0.05,
            "lead_s": 0.05,
            "plant_consumed_sim_s": 0.05,
        }
    ]
    with pytest.raises(stop.CalibrationStopMeasurementRefused) as refused:
        stop.verify_submission_time_base(
            off_grid, simulation_timestep_s=0.002, control_period_s=0.002
        )
    assert refused.value.code == stop.CAL_TIMING_TIME_BASE_UNVERIFIED


# --- the stop proof: three consecutive qualifying feedbacks ------------------------------------------


class _ScriptedPlant:
    """A plant whose velocities are scripted: the proof's rule is what is under test, not the physics."""

    def __init__(self, velocities, *, period_s: float = 0.002, feedback_period_s: float = 0.01) -> None:
        self.control_period_s = period_s
        self.feedback_period_s = feedback_period_s
        self.simulation_timestep_s = period_s
        self._velocities = list(velocities)
        self._index = 0
        self.time_s = 0.0
        self.reference_rad = 0.4
        self.holds: list[float] = []
        self.cycles = 0

    @property
    def yaw_rad(self) -> float:
        return self.reference_rad

    def hold_command(self, rad: float) -> None:
        self.holds.append(float(rad))
        self.reference_rad = float(rad)

    def step_control_cycle(self) -> None:
        self.cycles += 1
        self.time_s += self.control_period_s

    def feedback_sample(self) -> dict:
        velocity = self._velocities[min(self._index, len(self._velocities) - 1)]
        self._index += 1
        return {
            "sim_s": self.time_s,
            "monotonic_s": 0.0,
            "yaw_rad": self.yaw_rad,
            "reference_rad": self.reference_rad,
            "position_error_rad": 0.0,
            "velocity_rad_s": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, velocity],
            "joint_positions": [0.0] * 7,
            "joint_velocities": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, velocity],
        }

    def real_time_factor(self) -> float:
        return 1.0

    def close(self) -> None:
        pass


def _port_and_clock(*, stop_velocity_rad_s: float = 0.05, max_age_s: float = 0.05):
    clock = stop.MeasurementClock()
    transport = stop.ControllerFeedbackTransport()
    from so101_demo.adapters.act.ros_execution import RosControllerPort

    port = RosControllerPort(
        transport,
        None,
        stop.MONITORED_JOINTS,
        stop_velocity_rad_s=stop_velocity_rad_s,
        max_age_s=max_age_s,
        monotonic=clock,
    )
    return port, clock, transport


def test_confirm_stop_needs_three_consecutive_qualifying_feedback() -> None:
    """The port's own criterion decides: two quiet samples are not a stop proof."""

    plant = _ScriptedPlant([0.4, 0.01, 0.01, 0.01, 0.01])
    port, clock, transport = _port_and_clock()
    proof = stop.confirm_stop(
        plant=plant,
        port=port,
        transport=transport,
        clock=clock,
        hold_rad=0.4,
        stop_budget_s=1.0,
        index=0,
        reason="controller_revoke",
        period_s=plant.feedback_period_s,
    )
    assert proof["confirming_sample_indices"] == [1, 2, 3]
    assert proof["third_confirming_sample_index"] == 3
    assert proof["latency_s"] == pytest.approx(proof["third_confirming_receive_monotonic_s"]
                                               - proof["stop_request_monotonic_s"])
    assert [sample["qualifying"] for sample in proof["feedback_samples"]] == [
        False,
        True,
        True,
        True,
    ]
    assert proof["feedback_samples"][1]["velocity_rad_s"][-1] == 0.01
    assert proof["latency_s"] > 0.0
    # every sample the window saw is recorded, so a single exceedance can be checked later
    assert len(proof["feedback_samples"]) == 4


def test_confirm_stop_refuses_a_window_without_three_consecutive_qualifying_samples() -> None:
    """A quiet sample between two loud ones is not consecutive: the run fails rather than recording it."""

    plant = _ScriptedPlant([0.01, 0.01, 0.4, 0.01, 0.4])
    port, clock, transport = _port_and_clock()
    with pytest.raises(stop.CalibrationStopMeasurementRefused) as refused:
        stop.confirm_stop(
            plant=plant,
            port=port,
            transport=transport,
            clock=clock,
            hold_rad=0.4,
            stop_budget_s=0.03,
            index=0,
            reason="controller_revoke",
            period_s=plant.feedback_period_s,
        )
    assert refused.value.code == stop.CAL_STOP_PROOF_UNCONFIRMED


def test_the_stop_proof_flight_records_one_proof_per_declared_offset(tmp_path: Path) -> None:
    """The flight's shape: one proof per declared revoke offset, each with its own sampled window."""

    class _FlightPlant(_ScriptedPlant):
        def __init__(self, request) -> None:
            super().__init__([0.3] * 4 + [0.01] * 8)
            self.request = request
            self.admissions: list[dict] = []

        def command_through_admission(self, target_rad, *, purpose, max_cycles=None):
            self.admissions.append({"target_rad": float(target_rad), "purpose": purpose})
            snapshot = self.time_s
            cycles = 0
            while cycles < (4 if max_cycles is None else max_cycles):
                self.step_control_cycle()
                cycles += 1
            return {
                "purpose": purpose,
                "target_rad": float(target_rad),
                "submit_snapshot_sim_s": snapshot,
                "first_target_sim_s": snapshot + self.control_period_s,
                "plant_consumed_sim_s": snapshot + self.control_period_s,
                "lead_s": self.control_period_s,
                "steps": cycles,
                "control_cycles": cycles,
                "settled": max_cycles is None,
                "reached": True,
                "final_velocity_rad_s": 0.0,
                "final_position_error_rad": 0.0,
                "quiet_steps": 5,
            }

    result = stop.run_stop_proof_flight(
        request={
            "poses": [
                {"anchor": "left", "pose_rad": 0.0, "pose_kind": "anchor"},
                {"anchor": "left", "pose_rad": 0.08, "pose_kind": "plan"},
            ],
            "revoke_offsets_s": [0.02, 0.04],
            "stop_budget_s": 1.0,
            "feedback_period_s": 0.01,
            "control_period_s": 0.002,
            "stop_velocity_rad_s": 0.05,
            "max_age_s": 0.05,
        },
        plant_factory=_FlightPlant,
    )
    assert len(result["records"]) == 4
    assert [record["revoke_offset_s"] for record in result["records"]] == [0.02, 0.04, 0.02, 0.04]
    assert [record["pose_kind"] for record in result["records"]] == [
        "anchor",
        "anchor",
        "plan",
        "plan",
    ]
    for record in result["records"]:
        assert record["third_confirming_receive_monotonic_s"] > record["stop_request_monotonic_s"]
        assert len(record["feedback_samples"]) >= 3
    assert result["flight"]["proof_count"] == 4
    assert result["flight"]["ros_nodes_started"] is False


def test_the_stationary_flight_samples_every_pose_at_the_feedback_period() -> None:
    """Stationary noise is measured where the search waits: held poses, sampled at the feedback period."""

    class _StationaryPlant(_ScriptedPlant):
        def __init__(self, request) -> None:
            super().__init__([0.001] * 64)
            self.request = request

        def command_through_admission(self, target_rad, *, purpose, max_cycles=None):
            snapshot = self.time_s
            for _ in range(2):
                self.step_control_cycle()
            return {
                "purpose": purpose,
                "target_rad": float(target_rad),
                "submit_snapshot_sim_s": snapshot,
                "first_target_sim_s": snapshot + self.control_period_s,
                "plant_consumed_sim_s": snapshot + self.control_period_s,
                "lead_s": self.control_period_s,
                "steps": 2,
                "control_cycles": 2,
                "settled": True,
                "reached": True,
                "final_velocity_rad_s": 0.0,
                "final_position_error_rad": 0.0,
                "quiet_steps": 5,
            }

    result = stop.run_stationary_flight(
        request={
            "poses": [
                {"anchor": "left", "pose_rad": 0.0, "pose_kind": "anchor"},
                {"anchor": "left", "pose_rad": 0.08, "pose_kind": "plan"},
            ],
            "samples_per_pose": 4,
            "feedback_period_s": 0.01,
            "control_period_s": 0.002,
            "max_settle_s": 1.0,
        },
        plant_factory=_StationaryPlant,
    )
    assert result["flight"]["sample_count"] == 8
    assert result["flight"]["pose_count"] == 2
    assert len(result["records"]) == 2
    for record in result["records"]:
        assert record["settle"]["settled"] is True
        assert len(record["samples"]) == 4
        assert record["samples"][0]["velocity_rad_s"] == [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.001]
        assert record["p99_9_velocity_rad_s"] == 0.001
    assert result["flight"]["stationary_p99_9_velocity_rad_s"] == 0.001


def test_the_stationary_flight_refuses_a_pose_that_never_settles() -> None:
    """A pose the declared settle rule never reaches is refused, never sampled as if it were still."""

    class _UnsettledPlant(_ScriptedPlant):
        def __init__(self, request) -> None:
            super().__init__([0.4] * 8)

        def command_through_admission(self, target_rad, *, purpose, max_cycles=None):
            snapshot = self.time_s
            self.step_control_cycle()
            return {
                "purpose": purpose,
                "target_rad": float(target_rad),
                "submit_snapshot_sim_s": snapshot,
                "first_target_sim_s": snapshot + self.control_period_s,
                "plant_consumed_sim_s": snapshot + self.control_period_s,
                "lead_s": self.control_period_s,
                "steps": 1,
                "control_cycles": 1,
                "settled": False,
                "reached": False,
                "final_velocity_rad_s": 0.4,
                "final_position_error_rad": 0.2,
                "quiet_steps": 0,
            }

    with pytest.raises(stop.CalibrationStopMeasurementRefused) as refused:
        stop.run_stationary_flight(
            request={
                "poses": [{"anchor": "left", "pose_rad": 0.0, "pose_kind": "anchor"}],
                "samples_per_pose": 2,
                "feedback_period_s": 0.01,
                "control_period_s": 0.002,
                "max_settle_s": 1.0,
            },
            plant_factory=_UnsettledPlant,
        )
    assert refused.value.code == stop.CAL_STATIONARY_UNSETTLED
