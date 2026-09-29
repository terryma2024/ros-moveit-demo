"""Task 4 (approved measurement protocol v2): bounded calibration admission and dynamic neck binding.

A calibration generation may admit exactly one measurement flight while the production child stays rejected; arm
commands must byte-match the measurement plan; and a neck target may be dynamic only when it is uniquely derived
from policy state, inside the approved safe interval, and independently sweep-safe. A caller that bypasses the
binding and submits straight to the broker is refused.
"""

import pytest

SAFE_INTERVAL = [-1.0, 1.0]
PLAN_SHA = "a" * 64
POLICY_STATE = {"neck_start_rad": 0.1, "coarse_step_rad": 0.2, "horizontal_fov_rad": 1.3494818844471055}


def _admission():
    from so101_demo.act.task8_calibration_admission import CalibrationMeasurementAdmission

    return CalibrationMeasurementAdmission(
        generation="g1", status="CALIBRATION_REQUIRED", measurement_plan_sha256=PLAN_SHA,
        safe_interval_rad=SAFE_INTERVAL, controller_generation="ctrl-1", broker_generation="g1")


def _binding():
    from so101_demo.adapters.act.task8_calibration_search_binding import CalibrationSearchBinding

    def sweep_safe(target_rad: float) -> bool:
        return SAFE_INTERVAL[0] <= target_rad <= SAFE_INTERVAL[1]

    return CalibrationSearchBinding(admission=_admission(), policy_state=POLICY_STATE, sweep_checker=sweep_safe)


def test_calibration_required_admits_one_flight_and_rejects_the_production_child():
    admission = _admission()
    granted = admission.admit(role="calibration", generation="g1", operation="arm_probe")
    assert granted["admitted"] is True
    assert admission.admit(role="act", generation="g1", operation="arm_probe")["admitted"] is False
    assert admission.admit(role="calibration", generation="g1", operation="arm_probe")["admitted"] is False


@pytest.mark.parametrize("case", [
    {"operation": "release"},                     # release is never part of a measurement flight
    {"operation": "recorder"},                    # Recorder is not an admitted operation
    {"operation": "unknown_op"},                  # unknown operation
    {"generation": "g2"},                         # stale/foreign generation
    {"role": "act"},                              # production child, whatever the operation
])
def test_admission_refuses_every_named_case(case):
    arguments = {"role": "calibration", "generation": "g1", "operation": "arm_probe"}
    arguments.update(case)
    assert _admission().admit(**arguments)["admitted"] is False


def test_arm_commands_must_byte_match_the_measurement_plan():
    binding = _binding()
    assert binding.authorize_arm_command(plan_sha256=PLAN_SHA)["authorized"] is True
    with pytest.raises(ValueError, match="MEASUREMENT_PLAN_MISMATCH"):
        binding.authorize_arm_command(plan_sha256="b" * 64)


def test_dynamic_neck_targets_must_be_inside_the_interval_and_sweep_safe():
    binding = _binding()
    granted = binding.authorize_neck_target(target_rad=0.5, policy_state=POLICY_STATE)
    assert granted["authorized"] is True and granted["target_rad"] == pytest.approx(0.5)
    with pytest.raises(ValueError, match="NECK_TARGET_OUTSIDE_INTERVAL"):
        binding.authorize_neck_target(target_rad=1.5, policy_state=POLICY_STATE)
    with pytest.raises(ValueError, match="NECK_TARGET_NOT_SWEEP_SAFE"):
        binding.authorize_neck_target(target_rad=0.5, policy_state=POLICY_STATE, sweep_safe=False)


def test_a_caller_bypassing_the_binding_is_refused_by_the_broker():
    binding = _binding()
    with pytest.raises(ValueError, match="CALIBRATION_BINDING_REQUIRED"):
        binding.submit_directly_to_broker(target_rad=0.5, receipt=None)


def test_coarse_accumulator_advances_only_on_a_new_target():
    binding = _binding()
    first = binding.advance(target_rad=0.5)
    assert first["advanced"] is True and first["target_rad"] == pytest.approx(0.5)
    again = binding.advance(target_rad=0.5)
    assert again["advanced"] is False and again["reason"] == "REISSUE_NO_ADVANCE"
    moved = binding.advance(target_rad=0.7)
    assert moved["advanced"] is True and moved["classification"] == "coarse"


def test_fine_corrections_are_classified_separately_and_start_the_timeout():
    binding = _binding()
    deadline = binding.advance_deadline(monotonic_s=1.0)
    assert deadline["started_monotonic_s"] == pytest.approx(1.0)
    fine = binding.advance(target_rad=0.55, classification="fine")
    assert fine["classification"] == "fine"
    assert binding.deadline_elapsed(terminal_monotonic_s=1.5) == pytest.approx(0.5)


def test_the_first_target_beyond_the_interval_terminates_without_submitting():
    binding = _binding()
    outcome = binding.advance(target_rad=2.0)
    assert outcome["advanced"] is False
    assert outcome["reason"] == "TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL"
    assert binding.submitted_targets == []


def test_ownership_admits_the_calibration_role_with_a_restricted_capability_set():
    from so101_demo.act.ownership import CALIBRATION_CAPABILITIES, CAPABILITIES, OWNERS, Ownership

    assert "calibration" in OWNERS
    assert CAPABILITIES["calibration"] == CALIBRATION_CAPABILITIES
    assert {"arm_probe", "neck_target", "stop", "retire"} <= CALIBRATION_CAPABILITIES
    assert not {"release", "recorder"} & CALIBRATION_CAPABILITIES

    ownership = Ownership()
    token = ownership.acquire("calibration", "session-1", "attempt-1")
    assert token and ownership.state == "RUNNING"
    assert ownership.require_capability("calibration", "arm_probe") is True
    with pytest.raises(PermissionError, match="CAPABILITY_NOT_GRANTED: calibration may not release"):
        ownership.require_capability("calibration", "release")
    # the production owner keeps its existing semantics: unrestricted and still acquirable
    assert ownership.require_capability("act", "release") is True


class _Receipt:
    def __init__(self, signed_by):
        self.signed_by = signed_by


def test_the_broker_accepts_only_a_matching_probe_or_a_signed_receipt():
    from so101_demo.act.ownership import Ownership
    from so101_demo.adapters.act.command_broker import CommandBroker

    broker = object.__new__(CommandBroker)          # unit-level check of the enforcement seam itself
    broker.ownership = Ownership()
    broker.bind_measurement_plan(PLAN_SHA)
    ticket = (3, "token", "calibration", "session-1", "attempt-1")

    # a byte-matching arm probe is accepted; a different plan hash is not
    assert broker._require_calibration_authority(ticket, "arm_probe", {"plan_sha256": PLAN_SHA}) is True
    with pytest.raises(PermissionError, match="MEASUREMENT_PLAN_MISMATCH"):
        broker._require_calibration_authority(ticket, "arm_probe", {"plan_sha256": "c" * 64})
    # a neck target needs the adapter's receipt signed for this generation; a bare goal does not qualify
    assert broker._require_calibration_authority(ticket, "neck_target",
                                                {"receipt": _Receipt(3)}) is True
    with pytest.raises(PermissionError, match="CALIBRATION_BINDING_REQUIRED"):
        broker._require_calibration_authority(ticket, "neck_target", {"target_rad": 0.5})
    # release and any unknown operation fall outside the calibration capability set and are refused by that
    # gate first, so the message names the capability rather than the operation
    with pytest.raises(PermissionError, match="CAPABILITY_NOT_GRANTED: calibration may not release"):
        broker._require_calibration_authority(ticket, "release", {})
    with pytest.raises(PermissionError, match="CAPABILITY_NOT_GRANTED: calibration may not mystery"):
        broker._require_calibration_authority(ticket, "mystery", {})
    # the production owner is untouched by the gate
    production = (4, "token", "act", "session-1", "attempt-1")
    assert broker._require_calibration_authority(production, "release", {}) is True


def _context(**overrides):
    from so101_demo.act.task8_calibration_admission import CalibrationMeasurementContext

    arguments = {"generation": "g1", "contract_sha256": "a" * 64, "measurement_plan_sha256": PLAN_SHA,
                 "safe_interval_rad": SAFE_INTERVAL, "candidate_sha256": "b" * 64,
                 "policy_sha256": "c" * 64, "driver_source_sha256": "d" * 64,
                 "controller_generation": "ctrl-1", "broker_generation": "g1",
                 "evidence_root": "/data/work/so101-evidence/act-data/run",
                 "resource_binding": {"bound_at_entry": True, "cpu_cores": 8, "gpu_device": 0}}
    arguments.update(overrides)
    return CalibrationMeasurementContext(**arguments)


def test_the_context_requires_an_entry_origin_resource_binding():
    from so101_demo.act.task8_calibration_admission import CalibrationMeasurementContext

    with pytest.raises(ValueError, match="RESOURCE_BINDING_REQUIRED"):
        _context(resource_binding={"bound_at_entry": False, "cpu_cores": 8, "gpu_device": 0})
    with pytest.raises(ValueError, match="RESOURCE_BINDING_REQUIRED"):
        _context(resource_binding={"cpu_cores": 8, "gpu_device": 0})
    with pytest.raises(ValueError, match="RESOURCE_BINDING_REQUIRED"):
        _context(resource_binding=None)
    assert CalibrationMeasurementContext.REQUIRED_BINDING_KEYS == ("bound_at_entry", "cpu_cores", "gpu_device")


def test_the_context_carries_its_identity_and_builds_a_matching_admission():
    context = _context()
    document = context.to_dict()
    assert document["resource_binding"]["bound_at_entry"] is True
    assert document["safe_interval_rad"] == SAFE_INTERVAL
    admission = context.admission(status="CALIBRATION_REQUIRED")
    assert admission.generation == context.generation
    assert admission.measurement_plan_sha256 == context.measurement_plan_sha256
    assert admission.admit(role="calibration", generation="g1", operation="arm_probe")["admitted"] is True


def test_every_decided_event_carries_the_admission_generation():
    """The plan requires the admission generation on every event; the context is the single origin of it."""

    context = _context()
    admission = context.admission(status="CALIBRATION_REQUIRED")
    admission.admit(role="calibration", generation="g1", operation="arm_probe")
    admission.admit(role="act", generation="g1", operation="arm_probe")
    admission.admit(role="calibration", generation="g2", operation="arm_probe")
    admission.admit(role="calibration", generation="g1", operation="neck_target")
    assert [event["generation"] for event in admission.events] == ["g1"] * 4
    assert [event["admitted"] for event in admission.events] == [True, False, False, False]
    assert admission.events[1]["reason"].startswith("ROLE_NOT_CALIBRATION")
    assert admission.events[2]["reason"].startswith("GENERATION_MISMATCH")
    # the bound context is the one identity every downstream receipt can cite
    assert context.to_dict()["generation"] == "g1"
