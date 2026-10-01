"""The runtime readback of the eleven measured calibration parameters.

Phases 6 and 7 measure eleven of the seventeen values; phase 8 requires each of them to carry a startup
readback that proves the running process uses the recorded value rather than restating it. This module
constructs the production component that consumes each value - the installed search controller for the
eight configuration keys it reads, the installed neck search port for the submission lead, the stop
timeout and the freshness bound, and the installed stop criterion for the stop velocity - and records what
it observes off those objects.

Everything here is synthetic and in-process: no ROS node, no MuJoCo, no detector, no GPU and no motion.
The controller and the ports are the installed ones; only their transport (the subscription stand-in the
installed stop criterion already documents) is the harness's.
"""

from __future__ import annotations

import pytest
from so101_demo.act.head_search_measured_readback import (
    CONSTRUCTED_OBSERVATION,
    MEASURED_PARAMETERS,
    NOT_OBSERVABLE,
    observe_measured_readbacks,
)

#: the eleven measured values, at the production shapes the run of record recorded
VALUES = {
    "coarse_step_rad": 0.6560533740603397,
    "search_timeout_s": 0.7089213519976479,
    "center_deadband_px": 3.0,
    "vertical_bounds_px": [191.699852915671, 272.6768492617673],
    "max_fine_corrections": 2,
    "max_fine_total_rad": 0.6961197054865531,
    "max_age_s": 0.014736005008453503,
    "max_skew_s": 0.010000000000001563,
    "submit_lead_s": 0.004,
    "stop_velocity_rad_s": 0.04136050464213824,
    "stop_latency_s": 0.07012353999540209,
}

#: the flat configuration the installed controller is constructed with, at the *declared* production
#: values: the readback overrides the measured keys with the recorded ones and keeps the rest
CONFIGURATION = {
    "attempt_id": "readback-attempt",
    "session_id": "readback-session",
    "search_start_rad": 0.0,
    "horizontal_fov_rad": 1.3121067481206794,
    "coarse_step_rad": 0.3,
    "search_timeout_s": 12.0,
    "max_age_s": 0.05,
    "max_skew_s": 0.02,
    "settle_velocity_rad_s": 0.05,
    "goal_tolerance_rad": 0.05,
    "center_deadband_px": 18.0,
    "vertical_bounds_px": [110.0, 370.0],
    "min_area_px2": 64.0,
    "min_confidence": 0.4,
    "max_fine_corrections": 4,
    "max_fine_total_rad": 0.4,
    "frame_id": "head_camera_optical_frame",
    "ray_origin_frame_id": "base_link",
    "required_search_domain_rad": [-0.17559216195018026, 0.08047101126546086],
    "lock_valid_neck_rad": [-6.283175307179587, 6.283175307179587],
}


def _controller_returning(**overrides):
    """A factory that constructs the installed controller, but not with the configuration it was given."""

    from so101_demo.act.search import HeadSearchController

    def factory(configuration):
        return HeadSearchController({**dict(configuration), **overrides})

    return factory


def _refusing(message):
    def factory(*args, **kwargs):
        raise RuntimeError(message)

    return factory


def test_the_eleven_measured_parameters_are_exactly_the_two_phases_own_values():
    from so101_demo.act.head_search_coarse_step_measurement import PARAMETER as COARSE_STEP
    from so101_demo.act.head_search_search_params import PARAMETERS as PHASE_SIX
    from so101_demo.act.head_search_timing_params import PARAMETERS as PHASE_SEVEN

    # phase 6 owns five of the eleven in its `PARAMETERS` tuple and `coarse_step_rad` beside it
    assert set(MEASURED_PARAMETERS) == set(PHASE_SIX) | set(PHASE_SEVEN) | {COARSE_STEP}
    assert len(MEASURED_PARAMETERS) == 11


def test_every_measured_value_is_read_back_off_the_constructed_component():
    readbacks = observe_measured_readbacks(values=VALUES, configuration=CONFIGURATION)

    assert set(readbacks) == set(MEASURED_PARAMETERS)
    for name in MEASURED_PARAMETERS:
        readback = readbacks[name]
        assert readback["observation"] == CONSTRUCTED_OBSERVATION, name
        assert readback["observed_value"] == VALUES[name], name
        assert readback["verified"] is True, name
        assert readback["source"], name
        assert readback["component"], name


def test_the_configuration_is_the_declared_one_overridden_with_the_measured_values():
    readbacks = observe_measured_readbacks(values=VALUES, configuration=CONFIGURATION)

    configuration = readbacks["coarse_step_rad"]["configuration"]
    # the measured keys are the recorded ones, and the keys the calibration does not measure are the
    # declared production ones - the readback never invents a configuration of its own
    assert configuration["coarse_step_rad"] == VALUES["coarse_step_rad"]
    assert configuration["max_fine_corrections"] == VALUES["max_fine_corrections"]
    assert configuration["horizontal_fov_rad"] == CONFIGURATION["horizontal_fov_rad"]
    assert configuration["search_start_rad"] == CONFIGURATION["search_start_rad"]


def test_the_search_controller_values_are_read_off_the_object_and_not_restated():
    readbacks = observe_measured_readbacks(
        values=VALUES,
        configuration=CONFIGURATION,
        controller_factory=_controller_returning(search_timeout_s=99.0),
    )

    readback = readbacks["search_timeout_s"]
    # the component in force uses another value, so the observation is that other value: the module
    # queries the constructed component instead of echoing the value it was handed
    assert readback["observed_value"] == 99.0
    assert readback["verified"] is False
    assert readbacks["max_skew_s"]["verified"] is True


def test_the_coarse_step_is_read_off_the_bounded_stop_plan_the_controller_built():
    readbacks = observe_measured_readbacks(values=VALUES, configuration=CONFIGURATION)

    readback = readbacks["coarse_step_rad"]
    assert readback["also_observed"]["plan.coarse_step_rad"] == VALUES["coarse_step_rad"]


def test_a_controller_that_cannot_be_constructed_leaves_its_values_unverified_with_a_reason():
    readbacks = observe_measured_readbacks(
        values=VALUES,
        configuration=CONFIGURATION,
        controller_factory=_refusing("the installed controller refuses the recorded values"),
    )

    for name in (
        "coarse_step_rad",
        "search_timeout_s",
        "center_deadband_px",
        "vertical_bounds_px",
        "max_fine_corrections",
        "max_fine_total_rad",
        "max_skew_s",
    ):
        readback = readbacks[name]
        assert readback["verified"] is False, name
        assert readback["observation"] == NOT_OBSERVABLE, name
        assert "refuses the recorded values" in readback["reason"], name
        # no observation is fabricated: an unobservable value keeps the recorded one and says so
        assert readback["observed_value"] == VALUES[name], name
    # the freshness bound has three consumers: the two that could be queried agreed on the recorded
    # value, and the record still withholds the proof because the controller could not be asked
    age = readbacks["max_age_s"]
    assert age["verified"] is False
    assert age["observed_value"] == VALUES["max_age_s"]
    assert "could not be constructed" in age["reason"]
    # the timing and stop values do not go through the controller, so they are still observed
    assert readbacks["stop_velocity_rad_s"]["verified"] is True


def test_the_freshness_and_timeout_thresholds_are_observed_at_their_exact_boundary():
    readbacks = observe_measured_readbacks(values=VALUES, configuration=CONFIGURATION)

    deadline = readbacks["search_timeout_s"]["behavioural"]
    assert deadline["probe"] == "search_deadline"
    assert deadline["at_threshold"] == "SEARCH_TIMEOUT"
    assert deadline["just_before_threshold"] is None
    assert deadline["verified"] is True

    freshness = readbacks["max_age_s"]["behavioural"]
    assert freshness["probe"] == "frame_freshness"
    assert freshness["at_threshold"] == "fresh"
    assert freshness["just_beyond_threshold"] == "INPUT_STALE"
    assert freshness["verified"] is True

    skew = readbacks["max_skew_s"]["behavioural"]
    assert skew["probe"] == "frame_skew"
    assert skew["at_threshold"] == "fresh"
    assert skew["just_beyond_threshold"] == "INPUT_STALE"
    assert skew["verified"] is True


def test_the_submission_lead_the_stop_timeout_and_the_freshness_bound_are_read_off_the_neck_port():
    readbacks = observe_measured_readbacks(values=VALUES, configuration=CONFIGURATION)

    lead = readbacks["submit_lead_s"]
    assert lead["observed_value"] == VALUES["submit_lead_s"]
    assert "RosNeckSearchPort" in lead["component"]
    assert lead["source"].endswith(".lead")

    timeout = readbacks["stop_latency_s"]
    assert timeout["observed_value"] == VALUES["stop_latency_s"]
    assert timeout["source"].endswith(".stop_timeout")

    # the freshness bound is read from both components that consume it, and both have to agree
    age = readbacks["max_age_s"]
    assert age["observed_value"] == VALUES["max_age_s"]
    assert age["also_observed"]["neck_port.max_age"] == VALUES["max_age_s"]
    assert age["also_observed"]["stop_criterion.max_age"] == VALUES["max_age_s"]


def test_the_stop_velocity_is_read_off_the_installed_stop_criterion():
    readbacks = observe_measured_readbacks(values=VALUES, configuration=CONFIGURATION)

    readback = readbacks["stop_velocity_rad_s"]
    assert readback["observed_value"] == VALUES["stop_velocity_rad_s"]
    assert readback["component"].endswith("RosControllerPort")
    assert readback["source"].endswith(".stop_velocity")
    assert readback["verified"] is True


def test_a_neck_port_that_cannot_be_constructed_leaves_its_values_unverified_with_a_reason():
    readbacks = observe_measured_readbacks(
        values=VALUES,
        configuration=CONFIGURATION,
        neck_port_factory=_refusing("no broker is admitted for this readback"),
    )

    for name in ("submit_lead_s", "stop_latency_s", "max_age_s"):
        assert readbacks[name]["verified"] is False, name
        assert "no broker is admitted" in readbacks[name]["reason"], name
        assert readbacks[name]["observed_value"] == VALUES[name], name
    assert readbacks["coarse_step_rad"]["verified"] is True


def test_a_stop_criterion_that_cannot_be_constructed_leaves_only_its_value_unverified():
    readbacks = observe_measured_readbacks(
        values=VALUES,
        configuration=CONFIGURATION,
        stop_criterion_factory=_refusing("the installed stop criterion refused the value"),
    )

    assert readbacks["stop_velocity_rad_s"]["verified"] is False
    assert "refused the value" in readbacks["stop_velocity_rad_s"]["reason"]
    assert readbacks["submit_lead_s"]["verified"] is True


def test_only_the_measured_keys_are_overridden_and_only_they_are_read_back():
    """Phase 7 asks about its five while phase 6 asks about its six: neither sees the other's blocks."""

    values = {
        "max_age_s": VALUES["max_age_s"],
        "max_skew_s": VALUES["max_skew_s"],
        "submit_lead_s": VALUES["submit_lead_s"],
        "stop_velocity_rad_s": VALUES["stop_velocity_rad_s"],
        "stop_latency_s": VALUES["stop_latency_s"],
    }

    readbacks = observe_measured_readbacks(values=values, configuration=CONFIGURATION)

    assert set(readbacks) == set(values)
    for name, value in values.items():
        assert readbacks[name]["observed_value"] == value, name
        assert readbacks[name]["verified"] is True, name
    # the six phase 6 owns are not in this call at all, so no block of another phase is invented
    assert "coarse_step_rad" not in readbacks
    assert "vertical_bounds_px" not in readbacks


def test_a_value_that_is_not_one_of_the_eleven_is_a_caller_error():
    with pytest.raises(ValueError):
        observe_measured_readbacks(
            values={"horizontal_fov_rad": 1.31}, configuration=CONFIGURATION
        )


def test_the_harness_stand_ins_are_recorded_and_are_not_one_of_the_seventeen():
    readbacks = observe_measured_readbacks(values=VALUES, configuration=CONFIGURATION)

    harness = readbacks["submit_lead_s"]["harness"]
    assert harness["goal_duration_s"] > 0.0
    assert harness["command_guard"] == "always_true"
    assert harness["transport"] == "subscription stand-in"
    assert not set(harness) & set(MEASURED_PARAMETERS)


def test_the_recorded_threshold_is_the_float_the_component_was_constructed_with():
    readbacks = observe_measured_readbacks(values=VALUES, configuration=CONFIGURATION)

    # the exact-boundary probes measure the threshold the component applies, not a rounded copy of it
    assert readbacks["search_timeout_s"]["behavioural"]["threshold_s"] == VALUES["search_timeout_s"]
    assert readbacks["max_age_s"]["behavioural"]["threshold_s"] == VALUES["max_age_s"]
    assert readbacks["max_skew_s"]["behavioural"]["threshold_s"] == VALUES["max_skew_s"]
    for name in MEASURED_PARAMETERS:
        assert len(readbacks[name]["configuration_sha256"]) == 64, name
