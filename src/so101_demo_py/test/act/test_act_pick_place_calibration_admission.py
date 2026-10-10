"""bounded calibration admission and dynamic neck binding.

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
    from so101_demo.act.pick_place_calibration_admission import CalibrationMeasurementAdmission

    return CalibrationMeasurementAdmission(
        generation="g1", status="CALIBRATION_REQUIRED", measurement_plan_sha256=PLAN_SHA,
        safe_interval_rad=SAFE_INTERVAL, controller_generation="ctrl-1", broker_generation="g1")


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


def _context(**overrides):
    from so101_demo.act.pick_place_calibration_admission import CalibrationMeasurementContext

    arguments = {"generation": "g1", "contract_sha256": "a" * 64, "measurement_plan_sha256": PLAN_SHA,
                 "safe_interval_rad": SAFE_INTERVAL, "candidate_sha256": "b" * 64,
                 "policy_sha256": "c" * 64, "driver_source_sha256": "d" * 64,
                 "controller_generation": "ctrl-1", "broker_generation": "g1",
                 "evidence_root": "/data/work/so101-evidence/act-data/run",
                 "resource_binding": {"bound_at_entry": True, "cpu_cores": 8, "gpu_device": 0}}
    # Astra item 2: the descriptor is a required part of the context, so every context in this suite carries one
    # Astra re-review P1-2 strengthened the shared rule to check the contents, so the fixture supplies a
    # COMPLETE production descriptor - strengthening the fixture rather than weakening the rule
    arguments.setdefault("runtime_descriptor", {
        "schema_version": 1,
        "head_search": {"schema_version": 1,
                        # the shared rule is closed over the detector block, so the fixture supplies every
                        # member the production document carries - the thread and software-version fields included
                        "detector": {"backend": "yolo_seg", "weights_path": "/weights/best.pt",
                                     "weights_sha256": "a" * 64, "model_id": "plastic-cup",
                                     "image_size_px": 640, "requested_device": "cuda",
                                     "allow_cpu_fallback": False, "torch_threads": 4,
                                     "torch_interop_threads": 2, "torch_version": "2.0",
                                     "ultralytics_version": "8.0"},
                        "camera": {"frame_id": "head_camera_frame",
                                   "ray_origin_frame_id": "head_camera_frame",
                                   "width_px": 640, "height_px": 480},
                        "motion": {"goal_tolerance_rad": 0.02, "settle_velocity_rad_s": 0.01,
                                   "neck_goal_duration_s": 0.5}}})
    arguments.update(overrides)
    return CalibrationMeasurementContext(**arguments)


def test_the_context_requires_an_entry_origin_resource_binding():
    from so101_demo.act.pick_place_calibration_admission import CalibrationMeasurementContext

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
