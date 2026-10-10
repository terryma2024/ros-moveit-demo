"""Phase 7 of the formal head-search calibration: the five timing and stop parameters.

Every fixture here is synthetic: no ROS, no MuJoCo, no detector, no GPU, no motion. The measured
records reuse the raw evidence shapes the Task-8 measurement contract already fixes for these five
fields (`decision_minus_received_monotonic_max`, `max_minus_min_required_source_stamp_max`,
`first_target_sim_minus_submit_snapshot_sim_min`, `max_abs_velocity_over_three_strictly_increasing_
feedback`, `third_confirming_receive_minus_stop_request_monotonic_max`), so the same flight's records
feed both this phase's computation and the later verification.

The percentile fixtures carry 1000 samples on purpose: phase 7 takes the nearest-rank p99.9, which is
the second largest of a thousand samples, so a test can show that a single slow outlier is not hidden
by the percentile and still trips the hard bound.

The tests pin the five formulas of design section 7.1, every refusal the phase owns, the hard caps
expressed in the declared 10 Hz frame periods, the sim-time requirement on every submission,
determinism, and the evidence-block contract phase 8 imposes.
"""

from __future__ import annotations

import json

import pytest
from so101_demo.act.head_search_calibration_bundle import (
    ALSO_RECORDED_ITEMS,
    ALSO_RECORDED_KEYS,
    PARAMETER_EVIDENCE_KEYS,
    RUNTIME_IDENTITY_FIELDS,
    assemble_calibration_bundle,
)
from so101_demo.act.head_search_calibration_inputs import (
    SEALED_INPUT_NAMES,
    CalibrationInputsRefused,
)
from so101_demo.act.head_search_calibration_run import TIMING_NAME
from so101_demo.act.head_search_timing_params import (
    ARTIFACT_NAME,
    CAL_EFFECTIVE_VALUE_MISMATCH,
    CAL_FRESHNESS_EXCEEDED,
    CAL_SKEW_EXCEEDED,
    CAL_STOP_LATENCY_EXCEEDED,
    CAL_SUBMIT_LEAD_UNVERIFIED,
    FRAME_CONTRACT_HZ,
    FRAME_CONTRACT_ITEM,
    PARAMETERS,
    CalibrationTimingParamsRefused,
    compute_max_age_s,
    compute_max_skew_s,
    compute_stop_latency_s,
    compute_stop_velocity_rad_s,
    compute_submit_lead_s,
    p99_9,
    validate_head_search_calibration_timing_params,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
SHA_F = "f" * 64
SHA_G = "0" * 64
SHA_H = "1" * 64
SHA_I = "2" * 64

#: the declared 10 Hz frame contract of the design (section 7.1, final paragraph)
FRAME_RATE_HZ = 10.0
FRAME_PERIOD_S = 1.0 / FRAME_RATE_HZ

#: the design's own margins: 10 ms for the frame age, one clock resolution for the skew, one MuJoCo
#: simulation timestep for the submit lead and one feedback period for the stop latency
FRESHNESS_MARGIN_S = 0.010
CLOCK_RESOLUTION_S = 0.0005
MUJOCO_TIMESTEP_S = 0.002
FEEDBACK_PERIOD_S = 0.02
FEEDBACK_QUANTISATION_RAD = 0.0005
STOPPED_TOLERANCE_RAD_S = 0.008

#: a thousand samples is more than one p99.9 step, so the percentile is not simply the maximum
MEASUREMENTS = 1000

#: the happy-path distributions; every p99.9 is the second largest sample of its thousand
AGES = [0.07] * 995 + [0.08] * 4 + [0.09]
SPREADS = [0.030] * 995 + [0.035] * 4 + [0.040]
LEADS = [0.0200, 0.0201, 0.0202]
STATIONARY_VELOCITIES = [0.004] * MEASUREMENTS
LATENCIES = [0.03] * 995 + [0.04] * 4 + [0.05]

EXPECTED_P99_9_AGE_S = 0.08
EXPECTED_MAX_AGE_S = EXPECTED_P99_9_AGE_S + FRESHNESS_MARGIN_S
EXPECTED_P99_9_SKEW_S = 0.035
EXPECTED_MAX_SKEW_S = EXPECTED_P99_9_SKEW_S + CLOCK_RESOLUTION_S
EXPECTED_SUBMIT_LEAD_S = min(LEADS) + MUJOCO_TIMESTEP_S
EXPECTED_P99_9_STATIONARY_RAD_S = 0.004
EXPECTED_STOP_VELOCITY_RAD_S = (
    EXPECTED_P99_9_STATIONARY_RAD_S
    + FEEDBACK_QUANTISATION_RAD / FEEDBACK_PERIOD_S
    + STOPPED_TOLERANCE_RAD_S
)
EXPECTED_P99_9_LATENCY_S = 0.04
EXPECTED_STOP_LATENCY_S = EXPECTED_P99_9_LATENCY_S + FEEDBACK_PERIOD_S


def age_records(ages) -> list:
    """The raw frame-age records: the age is decision_monotonic minus received_monotonic."""

    return [
        {"received_monotonic_s": float(index), "decision_monotonic_s": float(index) + float(age)}
        for index, age in enumerate(ages)
    ]


def skew_records(spreads) -> list:
    """The raw skew records: one causal tuple of source stamps per record.

    Both stamps are anchored at zero so the measured spread is the exact float the fixture declares:
    the boundary tests compare it against a cap of exactly half a frame period.
    """

    return [{"stamps": [0.0, float(spread)]} for spread in spreads]


def submission_records(leads) -> list:
    """The raw controller submission records, stamped in simulation time only."""

    return [
        {"submit_snapshot_sim_s": float(index), "first_target_sim_s": float(index) + float(lead)}
        for index, lead in enumerate(leads)
    ]


def stationary_records(maxima) -> list:
    """The stationary feedback records: each one carries the six arm joints and the neck."""

    return [
        {
            "receive_monotonic_s": float(index),
            "velocity_rad_s": [0.0, float(maximum), 0.0, 0.0, 0.0, 0.0, 0.0],
        }
        for index, maximum in enumerate(maxima)
    ]


def stop_latency_records(latencies) -> list:
    """The raw stop proofs: stop/revoke request to the third confirming feedback."""

    return [
        {
            "stop_request_monotonic_s": float(index),
            "third_confirming_receive_monotonic_s": float(index) + float(latency),
        }
        for index, latency in enumerate(latencies)
    ]


def frame_contract_document(**overrides) -> dict:
    """The declared 10 Hz frame contract every cap above is expressed in."""

    document = {
        "path": "frame-contract.json",
        "sha256": SHA_A,
        "frame_rate_hz": FRAME_RATE_HZ,
    }
    document.update(overrides)
    return document


def age_document(samples=None, **overrides) -> dict:
    """The end-to-end frame-age measurements; `samples` is the raw record list."""

    document = {
        "path": "frame-age.json",
        "sha256": SHA_B,
        "samples": age_records(AGES) if samples is None else list(samples),
    }
    document.update(overrides)
    return document


def skew_document(samples=None, **overrides) -> dict:
    """The skew measurements and the clock resolution; `samples` is the raw record list."""

    document = {
        "path": "frame-skew.json",
        "sha256": SHA_C,
        "clock_resolution_s": CLOCK_RESOLUTION_S,
        "samples": skew_records(SPREADS) if samples is None else list(samples),
    }
    document.update(overrides)
    return document


def submissions_document(samples=None, **overrides) -> dict:
    """The controller goal-admission submissions; `samples` is the raw record list."""

    document = {
        "path": "controller-submissions.json",
        "sha256": SHA_D,
        "samples": submission_records(LEADS) if samples is None else list(samples),
    }
    document.update(overrides)
    return document


def mujoco_document(**overrides) -> dict:
    """The MuJoCo runtime measurement: the simulation timestep."""

    document = {
        "path": "mujoco-runtime.json",
        "sha256": SHA_E,
        "simulation_timestep_s": MUJOCO_TIMESTEP_S,
    }
    document.update(overrides)
    return document


def stationary_document(samples=None, **overrides) -> dict:
    """The stationary velocity measurements; `samples` is the raw record list."""

    document = {
        "path": "stationary-velocity.json",
        "sha256": SHA_F,
        "samples": stationary_records(STATIONARY_VELOCITIES) if samples is None else list(samples),
    }
    document.update(overrides)
    return document


def feedback_document(**overrides) -> dict:
    """The controller feedback: its quantisation resolution and one feedback period."""

    document = {
        "path": "controller-feedback.json",
        "sha256": SHA_G,
        "quantisation_rad": FEEDBACK_QUANTISATION_RAD,
        "period_s": FEEDBACK_PERIOD_S,
    }
    document.update(overrides)
    return document


def controller_document(**overrides) -> dict:
    """The controller stop configuration: the tolerance it already accepts as stopped."""

    document = {
        "path": "controller-stop-config.json",
        "sha256": SHA_H,
        "stopped_tolerance_rad_s": STOPPED_TOLERANCE_RAD_S,
    }
    document.update(overrides)
    return document


def stop_latency_document(samples=None, **overrides) -> dict:
    """The stop/revoke proofs; `samples` is the raw record list."""

    document = {
        "path": "stop-proofs.json",
        "sha256": SHA_I,
        "samples": stop_latency_records(LATENCIES) if samples is None else list(samples),
    }
    document.update(overrides)
    return document


def synthetic_block(value, unit) -> dict:
    """A minimal evidence block for a parameter phase 7 does not own."""

    return {
        "value": value,
        "unit": unit,
        "selection_formula": "synthetic fixture of another phase",
        "input_evidence": [{"path": "fixture.json", "sha256": SHA_A}],
        "observed_distribution": {"fixture": 1},
        "safety_margin": {"margin": 0.0},
        "production_owner": "so101_demo.act.search.HeadSearchController",
        "startup_readback": {"observed_value": value},
    }


def synthetic_runtime_identity() -> dict:
    """A complete runtime identity, field for field."""

    identity = {field: "measured-once" for field in RUNTIME_IDENTITY_FIELDS}
    identity["detector_weights_sha256"] = SHA_A
    identity["camera_intrinsics_sha256"] = SHA_B
    return identity


def build(**overrides) -> dict:
    """The phase document for the happy-path fixtures, with any input replaced by the caller."""

    arguments = {
        "frame_age": age_document(),
        "skew": skew_document(),
        "frame_contract": frame_contract_document(),
        "submissions": submissions_document(),
        "mujoco": mujoco_document(),
        "stationary": stationary_document(),
        "feedback": feedback_document(),
        "controller": controller_document(),
        "stop_proofs": stop_latency_document(),
    }
    arguments.update(overrides)
    return validate_head_search_calibration_timing_params(**arguments)


def refusal_of(call) -> CalibrationTimingParamsRefused:
    """Run one call that must refuse and return the refusal it raised."""

    with pytest.raises(CalibrationTimingParamsRefused) as raised:
        call()
    assert isinstance(raised.value, CalibrationInputsRefused)
    return raised.value


def caller_error_of(call) -> str:
    """Run one call that must be a caller error and return its message.

    A coded refusal is not a caller error: the assertion below keeps the two apart, because a
    malformed document must not be reported as a design refusal.
    """

    with pytest.raises(ValueError) as raised:
        call()
    assert not isinstance(raised.value, CalibrationInputsRefused)
    return str(raised.value)


# --------------------------------------------------------------------------------------------------
# happy path: all five values, with the evidence block phase 8 consumes
# --------------------------------------------------------------------------------------------------


def test_happy_path_computes_the_five_parameters_in_design_order():
    document = build()

    assert document["phase"] == "timing_stop_parameters"
    assert list(document["parameters"]) == list(PARAMETERS)
    assert document["motion_commanded"] is False
    assert document["parameters"]["max_age_s"]["value"] == pytest.approx(EXPECTED_MAX_AGE_S)
    assert document["parameters"]["max_skew_s"]["value"] == pytest.approx(EXPECTED_MAX_SKEW_S)
    assert document["parameters"]["submit_lead_s"]["value"] == pytest.approx(EXPECTED_SUBMIT_LEAD_S)
    assert document["parameters"]["stop_velocity_rad_s"]["value"] == pytest.approx(
        EXPECTED_STOP_VELOCITY_RAD_S
    )
    assert document["parameters"]["stop_latency_s"]["value"] == pytest.approx(
        EXPECTED_STOP_LATENCY_S
    )


def test_every_evidence_block_carries_exactly_the_phase_8_keys():
    document = build()

    for name, block in document["parameters"].items():
        assert set(block) == set(PARAMETER_EVIDENCE_KEYS), name
        assert block["unit"], name
        assert block["selection_formula"], name
        assert block["production_owner"], name
        assert block["observed_distribution"], name
        assert block["safety_margin"], name
        assert block["input_evidence"], name
        assert block["startup_readback"]["observed_value"] == block["value"], name


def test_evidence_units_are_the_ones_the_design_fixes():
    document = build()

    assert document["parameters"]["max_age_s"]["unit"] == "s"
    assert document["parameters"]["max_skew_s"]["unit"] == "s"
    assert document["parameters"]["submit_lead_s"]["unit"] == "s"
    assert document["parameters"]["stop_velocity_rad_s"]["unit"] == "rad/s"
    assert document["parameters"]["stop_latency_s"]["unit"] == "s"


def test_evidence_cites_the_measured_inputs_with_their_digests():
    document = build()

    referenced = {
        (reference["path"], reference["sha256"])
        for block in document["parameters"].values()
        for reference in block["input_evidence"]
    }
    assert ("frame-contract.json", SHA_A) in referenced
    assert ("frame-age.json", SHA_B) in referenced
    assert ("frame-skew.json", SHA_C) in referenced
    assert ("controller-submissions.json", SHA_D) in referenced
    assert ("mujoco-runtime.json", SHA_E) in referenced
    assert ("stationary-velocity.json", SHA_F) in referenced
    assert ("controller-feedback.json", SHA_G) in referenced
    assert ("controller-stop-config.json", SHA_H) in referenced
    assert ("stop-proofs.json", SHA_I) in referenced


def test_the_phase_document_is_deterministic():
    first = build()
    second = build()

    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_the_phase_writes_nothing_without_an_output_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    build()

    assert list(tmp_path.iterdir()) == []


def test_the_phase_writes_its_document_once_when_asked(tmp_path):
    output = tmp_path / ARTIFACT_NAME
    document = validate_head_search_calibration_timing_params(
        frame_age=age_document(),
        skew=skew_document(),
        frame_contract=frame_contract_document(),
        submissions=submissions_document(),
        mujoco=mujoco_document(),
        stationary=stationary_document(),
        feedback=feedback_document(),
        controller=controller_document(),
        stop_proofs=stop_latency_document(),
        output_path=output,
    )

    assert sorted(path.name for path in tmp_path.iterdir()) == [ARTIFACT_NAME]
    assert json.loads(output.read_text(encoding="utf-8")) == document


def test_the_artifact_name_is_the_one_the_run_reserves():
    assert ARTIFACT_NAME == TIMING_NAME


# --------------------------------------------------------------------------------------------------
# the percentile: a nearest-rank order statistic, never an interpolated sample
# --------------------------------------------------------------------------------------------------


def test_p99_9_is_the_nearest_rank_order_statistic():
    assert p99_9([0.5]) == 0.5
    assert p99_9([0.03] * MEASUREMENTS) == pytest.approx(0.03)
    signals = [0.03] * (MEASUREMENTS - 1) + [0.9]
    assert p99_9(signals) == pytest.approx(0.03)
    assert caller_error_of(lambda: p99_9([]))


# --------------------------------------------------------------------------------------------------
# max_age_s
# --------------------------------------------------------------------------------------------------


def test_max_age_is_the_p99_9_age_plus_ten_milliseconds():
    block = compute_max_age_s(frame_age=age_document(), frame_contract=frame_contract_document())

    distribution = block["observed_distribution"]
    assert block["value"] == pytest.approx(EXPECTED_MAX_AGE_S)
    assert distribution["p99_9_frame_age_s"] == pytest.approx(EXPECTED_P99_9_AGE_S)
    assert distribution["sample_count"] == MEASUREMENTS
    assert distribution["frame_period_s"] == pytest.approx(FRAME_PERIOD_S)
    assert block["safety_margin"]["freshness_margin_s"] == pytest.approx(FRESHNESS_MARGIN_S)
    assert block["safety_margin"]["cap_s"] == pytest.approx(1.5 * FRAME_PERIOD_S)


def test_max_age_uses_the_p99_9_and_not_the_slowest_sample():
    ages = [0.07] * (MEASUREMENTS - 1) + [0.2]
    block = compute_max_age_s(
        frame_age=age_document(samples=age_records(ages)), frame_contract=frame_contract_document()
    )

    assert block["value"] == pytest.approx(0.08)
    assert block["observed_distribution"]["max_frame_age_s"] == pytest.approx(0.2)


def test_max_age_refuses_beyond_one_and_a_half_frame_periods_and_blames_the_pipeline():
    refusal = refusal_of(
        lambda: compute_max_age_s(
            frame_age=age_document(samples=age_records([0.145] * MEASUREMENTS)),
            frame_contract=frame_contract_document(),
        )
    )

    assert refusal.code == CAL_FRESHNESS_EXCEEDED
    assert "fixed" in refusal.detail
    assert "raised" in refusal.detail


def test_max_age_inside_the_cap_is_recorded_as_computed_and_never_clamped():
    block = compute_max_age_s(
        frame_age=age_document(samples=age_records([0.12] * MEASUREMENTS)),
        frame_contract=frame_contract_document(),
    )

    assert block["value"] == pytest.approx(0.13)
    assert block["value"] != pytest.approx(1.5 * FRAME_PERIOD_S)
    assert block["safety_margin"]["headroom_s"] == pytest.approx(1.5 * FRAME_PERIOD_S - 0.13)


def test_the_age_cap_is_one_and_a_half_of_the_declared_frame_period():
    block = compute_max_age_s(frame_age=age_document(), frame_contract=frame_contract_document())

    assert block["safety_margin"]["frame_periods"] == pytest.approx(1.5)
    assert block["safety_margin"]["cap_s"] == pytest.approx(
        1.5 * block["observed_distribution"]["frame_period_s"]
    )


def test_a_frame_contract_that_is_not_the_ten_hertz_contract_is_a_caller_error():
    assert FRAME_CONTRACT_HZ == 10.0
    message = caller_error_of(
        lambda: compute_max_age_s(
            frame_age=age_document(), frame_contract=frame_contract_document(frame_rate_hz=20.0)
        )
    )
    assert "10" in message


def test_a_frame_contract_without_a_frame_rate_is_a_caller_error():
    assert caller_error_of(
        lambda: compute_max_age_s(
            frame_age=age_document(), frame_contract={"path": "c.json", "sha256": SHA_A}
        )
    )


def test_max_age_without_measured_ages_is_a_caller_error():
    assert caller_error_of(
        lambda: compute_max_age_s(
            frame_age=age_document(samples=[]), frame_contract=frame_contract_document()
        )
    )


# --------------------------------------------------------------------------------------------------
# max_skew_s
# --------------------------------------------------------------------------------------------------


def test_max_skew_is_the_p99_9_spread_plus_one_clock_resolution():
    block = compute_max_skew_s(skew=skew_document(), frame_contract=frame_contract_document())

    distribution = block["observed_distribution"]
    assert block["value"] == pytest.approx(EXPECTED_MAX_SKEW_S)
    assert distribution["p99_9_skew_s"] == pytest.approx(EXPECTED_P99_9_SKEW_S)
    assert distribution["clock_resolution_s"] == pytest.approx(CLOCK_RESOLUTION_S)
    assert block["safety_margin"]["clock_resolution_s"] == pytest.approx(CLOCK_RESOLUTION_S)
    assert block["safety_margin"]["cap_s"] == pytest.approx(0.5 * FRAME_PERIOD_S)
    assert block["safety_margin"]["frame_periods"] == pytest.approx(0.5)


def test_max_skew_refuses_beyond_half_a_frame_period():
    refusal = refusal_of(
        lambda: compute_max_skew_s(
            skew=skew_document(samples=skew_records([0.05] * MEASUREMENTS)),
            frame_contract=frame_contract_document(),
        )
    )

    assert refusal.code == CAL_SKEW_EXCEEDED
    assert "0.5" in refusal.detail or "half" in refusal.detail


def test_max_skew_at_the_half_frame_period_cap_is_recorded_as_computed():
    block = compute_max_skew_s(
        skew=skew_document(samples=skew_records([0.0495] * MEASUREMENTS)),
        frame_contract=frame_contract_document(),
    )

    assert block["value"] == pytest.approx(0.5 * FRAME_PERIOD_S)
    assert block["safety_margin"]["headroom_s"] == pytest.approx(0.0)


def test_max_skew_requires_the_clock_resolution():
    assert caller_error_of(
        lambda: compute_max_skew_s(
            skew=skew_document(clock_resolution_s=None), frame_contract=frame_contract_document()
        )
    )


# --------------------------------------------------------------------------------------------------
# submit_lead_s
# --------------------------------------------------------------------------------------------------


def test_submit_lead_is_the_minimum_lead_plus_one_simulation_timestep():
    block = compute_submit_lead_s(submissions=submissions_document(), mujoco=mujoco_document())

    distribution = block["observed_distribution"]
    assert block["value"] == pytest.approx(EXPECTED_SUBMIT_LEAD_S)
    assert distribution["minimum_lead_s"] == pytest.approx(min(LEADS))
    assert distribution["simulation_timestep_s"] == pytest.approx(MUJOCO_TIMESTEP_S)
    assert distribution["submission_count"] == len(LEADS)
    assert distribution["submissions_verified_in_simulation_time"] is True
    assert block["safety_margin"]["simulation_timestep_s"] == pytest.approx(MUJOCO_TIMESTEP_S)


def test_a_wall_clock_submission_record_refuses_with_the_unverified_code():
    samples = submission_records(LEADS)
    samples.append(
        {
            "time_base": "wall",
            "submit_snapshot_monotonic_s": 0.0,
            "first_target_monotonic_s": 0.05,
        }
    )
    refusal = refusal_of(
        lambda: compute_submit_lead_s(
            submissions=submissions_document(samples=samples), mujoco=mujoco_document()
        )
    )

    assert refusal.code == CAL_SUBMIT_LEAD_UNVERIFIED
    assert "wall" in refusal.detail


def test_a_submission_without_simulation_time_stamps_refuses():
    samples = submission_records(LEADS)
    samples.append({"submit_snapshot_monotonic_s": 0.0, "first_target_monotonic_s": 0.02})
    refusal = refusal_of(
        lambda: compute_submit_lead_s(
            submissions=submissions_document(samples=samples), mujoco=mujoco_document()
        )
    )

    assert refusal.code == CAL_SUBMIT_LEAD_UNVERIFIED
    assert "simulation time" in refusal.detail


def test_a_lead_the_computed_bound_does_not_cover_refuses():
    samples = submission_records(LEADS) + [
        {"submit_snapshot_sim_s": 0.0, "first_target_sim_s": 0.05}
    ]
    refusal = refusal_of(
        lambda: compute_submit_lead_s(
            submissions=submissions_document(samples=samples), mujoco=mujoco_document()
        )
    )

    assert refusal.code == CAL_SUBMIT_LEAD_UNVERIFIED
    assert "cover" in refusal.detail


def test_submit_lead_without_any_submission_is_a_caller_error():
    assert caller_error_of(
        lambda: compute_submit_lead_s(
            submissions=submissions_document(samples=[]), mujoco=mujoco_document()
        )
    )


# --------------------------------------------------------------------------------------------------
# stop_velocity_rad_s
# --------------------------------------------------------------------------------------------------


def test_stop_velocity_envelopes_the_noise_the_quantisation_and_the_tolerance():
    block = compute_stop_velocity_rad_s(
        stationary=stationary_document(),
        feedback=feedback_document(),
        controller=controller_document(),
    )

    distribution = block["observed_distribution"]
    assert block["value"] == pytest.approx(EXPECTED_STOP_VELOCITY_RAD_S)
    assert distribution["p99_9_stationary_velocity_rad_s"] == pytest.approx(
        EXPECTED_P99_9_STATIONARY_RAD_S
    )
    assert distribution["quantisation_rad"] == pytest.approx(FEEDBACK_QUANTISATION_RAD)
    assert distribution["feedback_period_s"] == pytest.approx(FEEDBACK_PERIOD_S)
    assert distribution["stopped_tolerance_rad_s"] == pytest.approx(STOPPED_TOLERANCE_RAD_S)
    margin = block["safety_margin"]
    assert margin["quantisation_velocity_rad_s"] == pytest.approx(
        FEEDBACK_QUANTISATION_RAD / FEEDBACK_PERIOD_S
    )
    assert margin["stationary_velocity_rad_s"] == pytest.approx(EXPECTED_P99_9_STATIONARY_RAD_S)
    assert margin["stopped_tolerance_rad_s"] == pytest.approx(STOPPED_TOLERANCE_RAD_S)


def test_stop_velocity_uses_the_p99_9_of_the_stationary_samples():
    maxima = [0.004] * (MEASUREMENTS - 1) + [0.02]
    block = compute_stop_velocity_rad_s(
        stationary=stationary_document(samples=stationary_records(maxima)),
        feedback=feedback_document(),
        controller=controller_document(),
    )

    assert block["observed_distribution"]["p99_9_stationary_velocity_rad_s"] == pytest.approx(0.004)
    assert block["value"] == pytest.approx(EXPECTED_STOP_VELOCITY_RAD_S)


def test_stop_velocity_requires_a_positive_feedback_period():
    assert caller_error_of(
        lambda: compute_stop_velocity_rad_s(
            stationary=stationary_document(),
            feedback=feedback_document(period_s=0.0),
            controller=controller_document(),
        )
    )


def test_stop_velocity_accepts_an_explicitly_zero_quantisation():
    """HS-305 Proposal B: the zero resolution is a declaration, and the envelope keeps its three terms."""

    block = compute_stop_velocity_rad_s(
        stationary=stationary_document(),
        feedback=feedback_document(quantisation_rad=0.0),
        controller=controller_document(),
    )

    assert block["observed_distribution"]["quantisation_rad"] == 0.0
    assert block["safety_margin"]["quantisation_velocity_rad_s"] == 0.0
    assert block["safety_margin"]["envelope_terms"] == 3
    assert block["value"] == pytest.approx(
        EXPECTED_P99_9_STATIONARY_RAD_S + 0.0 + STOPPED_TOLERANCE_RAD_S
    )
    assert block["value"] < EXPECTED_STOP_VELOCITY_RAD_S


def test_stop_velocity_still_refuses_a_missing_or_non_finite_quantisation():
    """The zero is accepted only where it was declared: absent, null and non-finite stay refusals."""

    for bad in (None, float("nan"), float("inf")):
        assert caller_error_of(
            lambda bad=bad: compute_stop_velocity_rad_s(
                stationary=stationary_document(),
                feedback=feedback_document(quantisation_rad=bad),
                controller=controller_document(),
            )
        )
    assert caller_error_of(
        lambda: compute_stop_velocity_rad_s(
            stationary=stationary_document(),
            feedback={
                key: value
                for key, value in feedback_document().items()
                if key != "quantisation_rad"
            },
            controller=controller_document(),
        )
    )


def test_stop_velocity_still_refuses_a_negative_quantisation():
    assert caller_error_of(
        lambda: compute_stop_velocity_rad_s(
            stationary=stationary_document(),
            feedback=feedback_document(quantisation_rad=-1e-6),
            controller=controller_document(),
        )
    )


# --------------------------------------------------------------------------------------------------
# stop_latency_s
# --------------------------------------------------------------------------------------------------


def test_stop_latency_is_the_p99_9_interval_plus_one_feedback_period():
    block = compute_stop_latency_s(
        stop_proofs=stop_latency_document(), feedback=feedback_document()
    )

    distribution = block["observed_distribution"]
    assert block["value"] == pytest.approx(EXPECTED_STOP_LATENCY_S)
    assert distribution["p99_9_stop_latency_s"] == pytest.approx(EXPECTED_P99_9_LATENCY_S)
    assert distribution["feedback_period_s"] == pytest.approx(FEEDBACK_PERIOD_S)
    assert distribution["sample_count"] == MEASUREMENTS
    assert block["safety_margin"]["feedback_period_s"] == pytest.approx(FEEDBACK_PERIOD_S)
    assert block["safety_margin"]["slowest_sample_s"] == pytest.approx(0.05)


def test_a_single_slow_stop_sample_fails_even_though_the_p99_9_is_fine():
    latencies = [0.03] * (MEASUREMENTS - 1) + [0.9]

    assert p99_9(latencies) == pytest.approx(0.03)
    refusal = refusal_of(
        lambda: compute_stop_latency_s(
            stop_proofs=stop_latency_document(samples=stop_latency_records(latencies)),
            feedback=feedback_document(),
        )
    )

    assert refusal.code == CAL_STOP_LATENCY_EXCEEDED
    assert "never raised" in refusal.detail


def test_a_slow_sample_inside_the_bound_is_accepted():
    latencies = [0.03] * (MEASUREMENTS - 1) + [0.05]
    block = compute_stop_latency_s(
        stop_proofs=stop_latency_document(samples=stop_latency_records(latencies)),
        feedback=feedback_document(),
    )

    assert block["value"] == pytest.approx(0.05)
    assert p99_9(latencies) == pytest.approx(0.03)


def test_stop_latency_refuses_a_negative_interval_as_a_caller_error():
    samples = stop_latency_records(LATENCIES)
    samples.append({"stop_request_monotonic_s": 1.0, "third_confirming_receive_monotonic_s": 0.5})
    assert caller_error_of(
        lambda: compute_stop_latency_s(
            stop_proofs=stop_latency_document(samples=samples), feedback=feedback_document()
        )
    )


# --------------------------------------------------------------------------------------------------
# the frame contract among the also-recorded items, and the phase-8 contract
# --------------------------------------------------------------------------------------------------


def test_the_frame_contract_is_one_of_the_five_also_recorded_items():
    assert FRAME_CONTRACT_ITEM in ALSO_RECORDED_ITEMS


def test_the_frame_contract_item_carries_exactly_the_phase_8_keys():
    document = build()
    record = document["also_recorded"][FRAME_CONTRACT_ITEM]

    assert set(document["also_recorded"]) == {FRAME_CONTRACT_ITEM}
    assert set(record) == set(ALSO_RECORDED_KEYS)
    assert record["input_evidence"]
    assert record["startup_readback"]


def test_the_frame_contract_item_declares_the_ten_hertz_contract():
    record = build()["also_recorded"][FRAME_CONTRACT_ITEM]

    assert "10" in str(record["value_or_definition"])
    assert str(FRAME_PERIOD_S) in str(record["value_or_definition"])
    assert record["input_evidence"][0]["path"] == "frame-contract.json"


def test_a_reported_startup_readback_is_checked_and_recorded():
    computed = build()["parameters"]["max_age_s"]["value"]
    document = build(
        startup_readbacks={
            "max_age_s": {"observed_value": computed, "read_from": "head_search_v2.json"}
        }
    )

    readback = document["parameters"]["max_age_s"]["startup_readback"]
    assert readback["verified"] is True
    assert readback["read_from"] == "head_search_v2.json"


def test_a_startup_readback_that_disagrees_refuses_with_phase_8s_code():
    refusal = refusal_of(lambda: build(startup_readbacks={"max_age_s": {"observed_value": 9.75}}))

    assert refusal.code == CAL_EFFECTIVE_VALUE_MISMATCH


def test_the_frame_contract_readback_is_checked_too():
    refusal = refusal_of(
        lambda: build(startup_readbacks={FRAME_CONTRACT_ITEM: {"observed_value": 5.0}})
    )

    assert refusal.code == CAL_EFFECTIVE_VALUE_MISMATCH


def test_the_five_blocks_and_the_frame_contract_survive_phase_8_assembly_verbatim():
    document = build()
    phase_inputs = {
        "geometry_coverage": {
            "parameters": {
                "horizontal_fov_rad": synthetic_block(1.3121067481206794, "rad"),
                "lock_valid_neck_rad": synthetic_block([-6.0, 6.0], "rad"),
            }
        },
        "perception_operating_point": {
            "parameters": {
                name: synthetic_block(value, unit)
                for name, (value, unit) in {
                    "min_confidence": (0.25, "ratio"),
                    "tracking_iou": (0.5, "ratio"),
                    "min_bbox_aspect": (0.5, "ratio"),
                    "min_area_px2": (100.0, "px^2"),
                }.items()
            }
        },
        "search_parameters": {
            "parameters": {
                "coarse_step_rad": synthetic_block(0.6560533740603397, "rad"),
                "search_timeout_s": synthetic_block(1.4, "s"),
                "center_deadband_px": synthetic_block(2.0, "px"),
                "vertical_bounds_px": synthetic_block([96.0, 432.0], "px"),
                "max_fine_corrections": synthetic_block(5, "count"),
                "max_fine_total_rad": synthetic_block(0.14, "rad"),
            }
        },
        "timing_stop_parameters": {
            "parameters": {name: dict(block) for name, block in document["parameters"].items()}
        },
    }
    also_recorded = {
        name: {
            "value_or_definition": 0.01 if name.endswith("rad_s") else "definition",
            "input_evidence": [{"path": "fixture.json", "sha256": SHA_A}],
            "startup_readback": {"observed_value": 0.01},
        }
        for name in ALSO_RECORDED_ITEMS
    }
    also_recorded[FRAME_CONTRACT_ITEM] = dict(document["also_recorded"][FRAME_CONTRACT_ITEM])
    assembly = assemble_calibration_bundle(
        status="SUCCEEDED",
        command="ros2 run so101_demo_py so101_head_search_calibration run --run-root /evidence/run-01",
        exit_code=0,
        phase_inputs=phase_inputs,
        controlled_dependencies={
            name: {"path": f"{name}.json", "sha256": SHA_A} for name in SEALED_INPUT_NAMES
        },
        runtime_identity=synthetic_runtime_identity(),
        also_recorded=also_recorded,
    )

    bundled = assembly["bundle"]["parameters"]
    for name, block in document["parameters"].items():
        assert bundled[name] == block, name
    assert (
        assembly["bundle"]["also_recorded"][FRAME_CONTRACT_ITEM]
        == document["also_recorded"][FRAME_CONTRACT_ITEM]
    )


def test_a_constructed_readback_keeps_its_own_observation_and_verdict():
    """A readback taken off the running component is not relabelled as a caller's report."""

    from so101_demo.act.head_search_measured_readback import CONSTRUCTED_OBSERVATION

    computed = build()["parameters"]["max_age_s"]["value"]
    document = build(
        startup_readbacks={
            "max_age_s": {
                "observed_value": computed,
                "observation": CONSTRUCTED_OBSERVATION,
                "verified": True,
                "source": "HeadSearchController(...).config['max_age_s']",
            }
        }
    )

    readback = document["parameters"]["max_age_s"]["startup_readback"]
    assert readback["observation"] == CONSTRUCTED_OBSERVATION
    assert readback["verified"] is True
    assert readback["source"] == "HeadSearchController(...).config['max_age_s']"


def test_a_constructed_readback_of_an_unobservable_value_stays_unverified():
    """A value the component could not be queried for is recorded unverified, never as an observation."""

    from so101_demo.act.head_search_measured_readback import NOT_OBSERVABLE

    computed = build()["parameters"]["max_age_s"]["value"]
    document = build(
        startup_readbacks={
            "max_age_s": {
                "observed_value": computed,
                "observation": NOT_OBSERVABLE,
                "verified": False,
                "reason": "the installed neck search port refused the recorded values",
            }
        }
    )

    readback = document["parameters"]["max_age_s"]["startup_readback"]
    assert readback["verified"] is False
    assert readback["observation"] == NOT_OBSERVABLE
    assert "refused the recorded values" in readback["reason"]
