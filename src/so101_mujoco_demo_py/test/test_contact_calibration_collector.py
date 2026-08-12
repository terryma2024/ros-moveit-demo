from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from so101_mujoco_demo_py.contact_calibration import PHYSICAL_REGIMES  # noqa: E402
from so101_mujoco_demo_py.contact_calibration_collector import (  # noqa: E402
    CalibrationReadinessPending,
    CollectionAborted,
    CollectionRequest,
    ContactCalibrationCollector,
    RobotCalibrationState,
    _argument_parser,
)
from so101_mujoco_demo_py.simulation.types import (  # noqa: E402
    ContactEvidence,
    ObjectState,
    ReceivedSimulationEvidence,
    SimulationEvidence,
)


def test_contact_calibration_collector_module_exists() -> None:
    assert (PACKAGE_ROOT / "so101_mujoco_demo_py/contact_calibration_collector.py").is_file()


def test_collector_has_console_and_direct_script_entry_points() -> None:
    assert (PACKAGE_ROOT / "scripts/collect_contact_calibration.py").is_file()
    setup_text = (PACKAGE_ROOT / "setup.py").read_text(encoding="utf-8")
    assert (
        "collect_contact_calibration = so101_mujoco_demo_py.contact_calibration_collector:main"
    ) in setup_text


def make_contact(side: str, force_n: float = 1.0) -> ContactEvidence:
    return ContactEvidence(
        body1_id=1,
        geom1_id=2,
        body1="cup",
        geom1="cup_collision",
        body2_id=3,
        geom2_id=4,
        body2="moving_jaw" if side == "right" else "fixed_finger",
        geom2=f"{side}_fingertip_pad",
        position_world=(0.2, 0.0, 0.03),
        normal_world=(1.0, 0.0, 0.0),
        signed_distance_m=-0.0004,
        normal_force_n=force_n,
    )


def evidence(
    sequence: int,
    *,
    session: str = "session-a",
    epoch: int = 4,
    left: bool = True,
    right: bool = True,
    other: bool = False,
    force_n: float = 1.0,
    position: tuple[float, float, float] = (0.2, 0.0, 0.03),
) -> SimulationEvidence:
    left_contacts = (make_contact("left", force_n),) if left else ()
    right_contacts = (make_contact("right", force_n),) if right else ()
    other_contacts = (make_contact("table", force_n),) if other else ()
    contacts = left_contacts + right_contacts + other_contacts
    return SimulationEvidence(
        simulation_time_s=sequence * 0.01,
        frame_id="world",
        publisher_sequence=sequence,
        simulation_step=sequence * 10,
        reset_epoch=epoch,
        simulation_session_id=session,
        paused=False,
        object_state=ObjectState(
            body_id=1,
            body="cup",
            position_world=position,
            orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
            linear_velocity_world=(0.001, 0.0, 0.0),
            angular_velocity_world=(0.0, 0.0, 0.0),
        ),
        has_contact=bool(contacts),
        minimum_signed_distance_m=min(
            (contact.signed_distance_m for contact in contacts), default=0.0
        ),
        maximum_normal_force_n=max((contact.normal_force_n for contact in contacts), default=0.0),
        truncated=False,
        left_fingertip_contacts=left_contacts,
        right_fingertip_contacts=right_contacts,
        other_object_contacts=other_contacts,
    )


class Observer:
    def __init__(self, snapshots: list[ReceivedSimulationEvidence]) -> None:
        self.snapshots = iter(snapshots)

    def snapshot_with_receipt(self) -> ReceivedSimulationEvidence:
        return next(self.snapshots)


class InitiallyStaleObserver(Observer):
    def __init__(self, snapshots: list[ReceivedSimulationEvidence]) -> None:
        super().__init__(snapshots)
        self.first = True

    def snapshot_with_receipt(self) -> ReceivedSimulationEvidence:
        if self.first:
            self.first = False
            from so101_mujoco_demo_py.mujoco.observer import EvidenceStale

            raise EvidenceStale("no atomic evidence has been accepted")
        return super().snapshot_with_receipt()


def robot_state() -> RobotCalibrationState:
    return RobotCalibrationState(
        q6_rad=0.2,
        arm_joint_positions_rad=(0.0, -0.4, 0.8, 0.5, 0.0),
        tcp_position_world_m=(0.2, 0.0, 0.09),
        tcp_orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
    )


def unilateral_contracts() -> dict:
    return {
        "left_only": {
            "stable_grasp_allowed": False,
            "expected_failure_code": "GRASP_RIGHT_CONTACT_MISSING",
            "physical_evidence": {
                "disposition": "physical_unreachable",
                "references": [{"experiment_id": "EXP-062", "artifact_sha256": "6" * 64}],
            },
            "physical_calibration_sample_count": None,
            "physical_evaluation_sample_count": None,
            "physical_misclassification_rate": None,
        },
        "right_only": {
            "stable_grasp_allowed": False,
            "expected_failure_code": "GRASP_LEFT_CONTACT_MISSING",
            "physical_evidence": {
                "disposition": "observed",
                "references": [{"experiment_id": "EXP-072", "artifact_sha256": "8" * 64}],
            },
            "physical_calibration_sample_count": None,
            "physical_evaluation_sample_count": None,
            "physical_misclassification_rate": None,
        },
    }


def request(tmp_path: Path, **changes) -> CollectionRequest:
    values = {
        "regime": "bilateral_touch",
        "sample_count": 3,
        "simulation_session_id": "session-a",
        "reset_epoch": 4,
        "output_path": tmp_path / "matrix.json",
        "source_commit": "1" * 40,
        "dependency_commit": "2" * 40,
        "model_sha256": "a" * 64,
        "scene_sha256": "b" * 64,
        "motion_policy_sha256": "c" * 64,
        "unilateral_rejection_contracts": unilateral_contracts(),
        "reference_object_position_m": (0.2, 0.0, 0.03),
    }
    values.update(changes)
    return CollectionRequest(**values)


def collector(
    snapshots: list[ReceivedSimulationEvidence], *, cancelled=lambda: False
) -> ContactCalibrationCollector:
    return ContactCalibrationCollector(
        Observer(snapshots),
        robot_state,
        monotonic=lambda: 10.0,
        cancelled=cancelled,
    )


def received(item: SimulationEvidence, at: float = 9.95) -> ReceivedSimulationEvidence:
    return ReceivedSimulationEvidence(item, at)


def test_collector_writes_exact_bounded_count_with_atomic_replacement(tmp_path: Path) -> None:
    output = tmp_path / "matrix.json"
    output.write_text("sentinel", encoding="utf-8")
    target = collector([received(evidence(index)) for index in range(1, 4)])

    result = target.collect(request(tmp_path))

    document = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "VALID"
    assert document["schema_version"] == 3
    assert document["fingerprint"] == {
        "source_commit": "1" * 40,
        "dependency_commit": "2" * 40,
        "model_sha256": "a" * 64,
        "scene_sha256": "b" * 64,
        "motion_policy_sha256": "c" * 64,
    }
    assert document["unilateral_rejection_contracts"] == unilateral_contracts()
    assert set(document["regimes"]) == set(PHYSICAL_REGIMES)
    assert len(document["regimes"]["bilateral_touch"]) == 3
    assert [sample["publisher_sequence"] for sample in document["regimes"]["bilateral_touch"]] == [
        1,
        2,
        3,
    ]
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("regime", ("left_only", "right_only"))
def test_collector_rejects_unilateral_contract_labels_before_observation(
    tmp_path: Path, regime: str
) -> None:
    with pytest.raises(ValueError, match="unsupported calibration regime"):
        request(tmp_path, regime=regime)


def test_collector_cli_exposes_only_five_physical_regimes() -> None:
    action = next(action for action in _argument_parser()._actions if action.dest == "regime")

    assert set(action.choices) == set(PHYSICAL_REGIMES)
    contracts = next(
        action for action in _argument_parser()._actions if action.dest == "unilateral_contracts"
    )
    assert contracts.required is True


def test_collector_waits_for_first_atomic_evidence_within_bounded_deadline(
    tmp_path: Path,
) -> None:
    target = ContactCalibrationCollector(
        InitiallyStaleObserver([received(evidence(1))]),
        robot_state,
        monotonic=lambda: 10.0,
    )

    result = target.collect(request(tmp_path, sample_count=1))

    assert result["collected_sample_count"] == 1


def test_collector_waits_for_first_robot_state_without_admitting_sample(
    tmp_path: Path,
) -> None:
    calls = 0

    def initially_missing_state() -> RobotCalibrationState:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise CalibrationReadinessPending("no joint state is available")
        return robot_state()

    target = ContactCalibrationCollector(
        Observer([received(evidence(1)), received(evidence(2))]),
        initially_missing_state,
        monotonic=lambda: 10.0,
    )

    result = target.collect(request(tmp_path, sample_count=1))

    assert result["collected_sample_count"] == 1
    sample = json.loads((tmp_path / "matrix.json").read_text(encoding="utf-8"))["regimes"][
        "bilateral_touch"
    ][0]
    assert sample["publisher_sequence"] == 2


def test_collector_skips_repeated_snapshot_until_new_sequence(tmp_path: Path) -> None:
    target = collector([received(evidence(1)), received(evidence(1)), received(evidence(2))])

    result = target.collect(request(tmp_path, sample_count=2))

    assert result["collected_sample_count"] == 2
    samples = json.loads((tmp_path / "matrix.json").read_text(encoding="utf-8"))["regimes"][
        "bilateral_touch"
    ]
    assert [sample["publisher_sequence"] for sample in samples] == [1, 2]


def test_stable_hold_requires_continuous_bilateral_preroll_before_recording(
    tmp_path: Path,
) -> None:
    target = collector([received(evidence(index)) for index in range(1, 34)])

    target.collect(
        request(
            tmp_path,
            regime="stable_hold",
            sample_count=3,
            stable_hold_preroll_s=0.30,
        )
    )

    samples = json.loads((tmp_path / "matrix.json").read_text(encoding="utf-8"))["regimes"][
        "stable_hold"
    ]
    assert [sample["publisher_sequence"] for sample in samples] == [31, 32, 33]
    assert samples[0]["contact_duration_s"] == pytest.approx(0.30)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("source_commit", "0" * 40),
        ("scene_sha256", "short"),
        ("motion_policy_sha256", "0" * 64),
    ),
)
def test_collection_request_rejects_placeholder_or_malformed_identity(
    tmp_path: Path, field: str, value: str
) -> None:
    with pytest.raises(ValueError, match=field):
        request(tmp_path, **{field: value})


def test_collector_rejects_existing_v3_matrix_fingerprint_drift(tmp_path: Path) -> None:
    first = collector([received(evidence(1))])
    first.collect(request(tmp_path, sample_count=1))

    second = collector([received(evidence(2))])
    with pytest.raises(CollectionAborted, match="scene_sha256 mismatch"):
        second.collect(request(tmp_path, sample_count=1, scene_sha256="e" * 64))


@pytest.mark.parametrize(
    ("items", "message"),
    [
        ([received(evidence(1, session="wrong"))], "session"),
        ([received(evidence(1, epoch=5))], "reset"),
        ([received(evidence(2)), received(evidence(1))], "sequence"),
        ([received(evidence(1), at=9.0)], "stale"),
    ],
)
def test_collector_rejects_stream_boundary_violations(
    tmp_path: Path, items: list[ReceivedSimulationEvidence], message: str
) -> None:
    with pytest.raises(CollectionAborted, match=message):
        collector(items).collect(request(tmp_path))


def test_collector_rejects_truncated_and_nonfinite_atomic_state(tmp_path: Path) -> None:
    truncated = evidence(1)
    object.__setattr__(truncated, "truncated", True)
    with pytest.raises(CollectionAborted, match="truncated"):
        collector([received(truncated)]).collect(request(tmp_path))

    nonfinite = evidence(2)
    object.__setattr__(nonfinite.object_state, "position_world", (float("nan"), 0.0, 0.03))
    with pytest.raises(CollectionAborted, match="finite"):
        collector([received(nonfinite)]).collect(request(tmp_path))


@pytest.mark.parametrize(
    ("sample", "message"),
    [
        (evidence(1, left=False, right=False, other=True), "bilateral"),
        (evidence(1, left=True, right=False), "bilateral"),
        (evidence(1, left=False, right=True), "bilateral"),
    ],
)
def test_other_or_one_sided_contacts_never_count_as_bilateral(
    tmp_path: Path, sample: SimulationEvidence, message: str
) -> None:
    with pytest.raises(CollectionAborted, match=message):
        collector([received(sample)]).collect(request(tmp_path, wrong_side_limit=1))


def test_collector_aborts_on_diagnostic_safety_boundaries(tmp_path: Path) -> None:
    displaced = evidence(1, left=False, right=False, position=(0.204, 0.0, 0.03))
    with pytest.raises(CollectionAborted, match="displacement"):
        collector([received(displaced)]).collect(
            request(tmp_path, regime="no_contact", pre_contact=True)
        )

    hazardous = evidence(2, force_n=11.61)
    with pytest.raises(CollectionAborted, match="force"):
        collector([received(hazardous)]).collect(request(tmp_path))


def test_pre_contact_and_terminal_total_displacement_use_independent_limits(
    tmp_path: Path,
) -> None:
    four_mm = evidence(
        1,
        left=False,
        right=False,
        position=(0.204, 0.0, 0.03),
    )
    accepted = collector([received(four_mm)]).collect(
        request(tmp_path, regime="no_contact", sample_count=1, pre_contact=False)
    )
    assert accepted["status"] == "VALID"

    with pytest.raises(CollectionAborted, match="pre-contact"):
        collector([received(four_mm)]).collect(
            request(
                tmp_path / "pre-contact",
                regime="no_contact",
                sample_count=1,
                pre_contact=True,
            )
        )

    eleven_mm = evidence(
        2,
        left=False,
        right=False,
        position=(0.211, 0.0, 0.03),
    )
    with pytest.raises(CollectionAborted, match="terminal total"):
        collector([received(eleven_mm)]).collect(
            request(
                tmp_path / "terminal-total",
                regime="no_contact",
                sample_count=1,
                pre_contact=False,
            )
        )


def test_collector_cancellation_preserves_partial_metadata(tmp_path: Path) -> None:
    calls = iter((False, True))
    target = collector([received(evidence(1))], cancelled=lambda: next(calls))

    with pytest.raises(CollectionAborted, match="cancel"):
        target.collect(request(tmp_path))

    partial = json.loads((tmp_path / "matrix.partial.json").read_text(encoding="utf-8"))
    assert partial["status"] == "INVALID"
    assert partial["collected_sample_count"] == 1
    assert "cancel" in partial["reason"]
    assert not (tmp_path / "matrix.json").exists()


def test_collector_uses_existing_sensor_data_observer_qos(monkeypatch) -> None:
    from rclpy.qos import qos_profile_sensor_data

    support = ModuleType("so101_mujoco_support")
    messages = ModuleType("so101_mujoco_support.msg")
    messages.SimulationEvidence = type("RosSimulationEvidence", (), {})
    support.msg = messages
    monkeypatch.setitem(sys.modules, "so101_mujoco_support", support)
    monkeypatch.setitem(sys.modules, "so101_mujoco_support.msg", messages)
    from so101_mujoco_demo_py.mujoco.observer import MujocoWorldObserver

    class Node:
        def create_subscription(self, _message, _topic, _callback, qos):
            self.qos = qos
            return object()

    node = Node()
    MujocoWorldObserver(node, "session-a")

    assert node.qos is qos_profile_sensor_data
