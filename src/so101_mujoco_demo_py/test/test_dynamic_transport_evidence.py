from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from so101_mujoco_demo_py.dynamic_transport_evidence import (
    AtomicTransportEvidenceStore,
    DynamicTransportRun,
    EvidenceInvalid,
    PhysicsContactSample,
    PhysicsStepChunk,
    PhysicsStepSample,
    TransportBoundary,
    TransportBoundaryKind,
    analyze_dynamic_transport,
)

TIMESTEP_S = 0.002
SHADOW_FORCE_N = 1.1579004532160448


def contact(
    side: str,
    force_n: float,
    normal: tuple[float, float, float],
    *,
    signed_distance_m: float = -0.001,
) -> PhysicsContactSample:
    return PhysicsContactSample(
        side=side,
        object_body="plastic_cup",
        object_geom="cup_collision",
        other_body="moving_jaw" if side == "left" else "fixed_jaw",
        other_geom=f"{side}_fingertip",
        signed_distance_m=signed_distance_m,
        normal_force_n=force_n,
        normal_world=normal,
    )


def sample(
    step: int,
    maximum_force_n: float,
    *,
    session: str = "run-a",
    epoch: int = 1,
    truncated: bool = False,
    left_compression_m: float = 0.001,
    right_compression_m: float = 0.0015,
    net_force: tuple[float, float, float] | None = None,
) -> PhysicsStepSample:
    right_force = max(0.0, maximum_force_n - 0.5)
    left = contact(
        "left",
        maximum_force_n,
        (1.0, 0.0, 0.0),
        signed_distance_m=-left_compression_m,
    )
    right = contact(
        "right",
        right_force,
        (0.0, 1.0, 0.0),
        signed_distance_m=-right_compression_m,
    )
    expected_net = (
        maximum_force_n,
        right_force,
        0.0,
    )
    return PhysicsStepSample(
        simulation_session_id=session,
        reset_epoch=epoch,
        physics_step=step,
        simulation_time_s=step * TIMESTEP_S,
        object_pose_world_xyz_xyzw=(0.0, 0.0, 0.2, 0.0, 0.0, 0.0, 1.0),
        object_twist_world_linear_angular=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        maximum_normal_force_n=maximum_force_n,
        left_fingertip_total_normal_force_n=maximum_force_n,
        right_fingertip_total_normal_force_n=right_force,
        fingertip_max_single_contact_force_n=maximum_force_n,
        global_max_single_contact_force_n=maximum_force_n,
        left_fingertip_compression_m=left_compression_m,
        right_fingertip_compression_m=right_compression_m,
        net_contact_force_world_n=expected_net if net_force is None else net_force,
        truncated=truncated,
        left_fingertip_contacts=(left,),
        right_fingertip_contacts=(right,),
        other_object_contacts=(),
    )


def chunk(
    samples: tuple[PhysicsStepSample, ...],
    *,
    sequence: int = 0,
    evidence_loss: bool = False,
    failed_publish_attempts: int = 0,
) -> PhysicsStepChunk:
    return PhysicsStepChunk(
        chunk_sequence=sequence,
        simulation_session_id=samples[0].simulation_session_id,
        reset_epoch=samples[0].reset_epoch,
        first_physics_step=samples[0].physics_step,
        last_physics_step=samples[-1].physics_step,
        first_simulation_time_s=samples[0].simulation_time_s,
        last_simulation_time_s=samples[-1].simulation_time_s,
        failed_publish_attempts=failed_publish_attempts,
        evidence_loss=evidence_loss,
        samples=samples,
    )


def run(
    samples: tuple[PhysicsStepSample, ...],
    *,
    chunks: tuple[PhysicsStepChunk, ...] | None = None,
    boundaries: tuple[TransportBoundary, ...] | None = None,
) -> DynamicTransportRun:
    first = samples[0]
    last = samples[-1]
    return DynamicTransportRun(
        run_id="EXP-110",
        simulation_session_id=first.simulation_session_id,
        reset_epoch=first.reset_epoch,
        physics_timestep_s=TIMESTEP_S,
        chunks=(chunk(samples),) if chunks is None else chunks,
        boundaries=(
            TransportBoundary(TransportBoundaryKind.PHASE_START, 1, first.physics_step),
            TransportBoundary(TransportBoundaryKind.WAYPOINT_START, 1, first.physics_step),
            TransportBoundary(TransportBoundaryKind.WAYPOINT_END, 1, last.physics_step),
            TransportBoundary(TransportBoundaryKind.PHASE_END, 1, last.physics_step),
        )
        if boundaries is None
        else boundaries,
        physical_transport_outcome="FORMAL_MOVE_ABOVE_PLACE_PROVED",
    )


def test_analyzer_uses_hand_derived_force_time_exposure() -> None:
    samples = tuple(sample(index, force) for index, force in enumerate((1, 2, 4, 2, 1), 1))

    summary = analyze_dynamic_transport(run(samples), shadow_force_n=SHADOW_FORCE_N)

    assert summary.peak_global_max_single_contact_force_n == 4.0
    assert summary.force_time_exposure_n_s == pytest.approx(0.018)
    assert summary.independent_experiment_units == 1
    assert summary.waypoints[0].statistical_role == "repeated_measure"


def test_analyzer_integrates_vector_contact_force_as_physical_impulse() -> None:
    samples = (
        sample(1, 1.0),
        sample(2, 3.0),
        sample(3, 5.0),
    )

    summary = analyze_dynamic_transport(run(samples), shadow_force_n=SHADOW_FORCE_N)

    assert summary.net_contact_impulse_vector_n_s == pytest.approx((0.012, 0.010, 0.0))
    assert summary.force_time_exposure_n_s == pytest.approx(0.012)


def test_analyzer_uses_discrete_contiguous_shadow_windows_without_grace() -> None:
    forces = (1.0, 2.0, 4.0, 1.0, 3.0, 1.0)
    samples = tuple(sample(index, force) for index, force in enumerate(forces, 1))

    summary = analyze_dynamic_transport(run(samples), shadow_force_n=SHADOW_FORCE_N)

    assert [window.sample_count for window in summary.sustained_overpressure_windows] == [2, 1]
    assert [
        window.duration_s for window in summary.sustained_overpressure_windows
    ] == pytest.approx([0.004, 0.002])
    assert [window.first_physics_step for window in summary.sustained_overpressure_windows] == [
        2,
        5,
    ]
    assert [window.last_physics_step for window in summary.sustained_overpressure_windows] == [
        3,
        5,
    ]


def test_analyzer_keeps_left_right_compression_separate() -> None:
    samples = (
        sample(1, 1.0, left_compression_m=0.001, right_compression_m=0.002),
        sample(2, 1.0, left_compression_m=0.004, right_compression_m=0.003),
    )

    summary = analyze_dynamic_transport(run(samples), shadow_force_n=SHADOW_FORCE_N)

    assert summary.maximum_left_fingertip_compression_m == 0.004
    assert summary.maximum_right_fingertip_compression_m == 0.003


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"left_fingertip_total_normal_force_n": 9.0}, "left fingertip total"),
        ({"right_fingertip_total_normal_force_n": 9.0}, "right fingertip total"),
        ({"fingertip_max_single_contact_force_n": 9.0}, "fingertip maximum"),
        (
            {"maximum_normal_force_n": 9.0, "global_max_single_contact_force_n": 9.0},
            "global maximum",
        ),
        ({"left_fingertip_compression_m": 0.009}, "left fingertip compression"),
        ({"right_fingertip_compression_m": 0.009}, "right fingertip compression"),
        ({"net_contact_force_world_n": (9.0, 9.0, 9.0)}, "net contact force"),
    ],
)
def test_analyzer_rejects_aggregate_fields_that_do_not_replay_from_raw_contacts(
    changes: dict[str, object], message: str
) -> None:
    baseline = sample(1, 2.0)
    inconsistent = replace(baseline, **changes)

    with pytest.raises(EvidenceInvalid, match=message):
        analyze_dynamic_transport(run((inconsistent,)), shadow_force_n=SHADOW_FORCE_N)


def test_analyzer_excludes_non_fingertip_contact_from_fingertip_compression() -> None:
    baseline = sample(1, 2.0)
    table_contact = PhysicsContactSample(
        side="other",
        object_body="plastic_cup",
        object_geom="cup_collision",
        other_body="table",
        other_geom="table_surface",
        signed_distance_m=-0.020,
        normal_force_n=3.0,
        normal_world=(0.0, 0.0, 1.0),
    )
    replayable = replace(
        baseline,
        maximum_normal_force_n=3.0,
        global_max_single_contact_force_n=3.0,
        net_contact_force_world_n=(2.0, 1.5, 3.0),
        other_object_contacts=(table_contact,),
    )

    summary = analyze_dynamic_transport(run((replayable,)), shadow_force_n=SHADOW_FORCE_N)

    assert summary.maximum_left_fingertip_compression_m == 0.001
    assert summary.maximum_right_fingertip_compression_m == 0.0015


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda values: (values[0], values[2]),
            "missing physics step",
        ),
        (
            lambda values: (values[0], values[0], values[1]),
            "duplicate physics step",
        ),
        (
            lambda values: (values[0], sample(2, 1.0, epoch=2)),
            "reset epoch mismatch",
        ),
        (
            lambda values: (values[0], sample(2, 1.0, truncated=True)),
            "truncated contact evidence",
        ),
    ],
)
def test_analyzer_rejects_invalid_step_sequences(mutate, message: str) -> None:
    baseline = tuple(sample(step, 1.0) for step in range(1, 4))
    mutated = tuple(mutate(baseline))

    with pytest.raises(EvidenceInvalid, match=message):
        analyze_dynamic_transport(run(mutated), shadow_force_n=SHADOW_FORCE_N)


def test_analyzer_rejects_chunk_evidence_loss() -> None:
    samples = tuple(sample(step, 1.0) for step in range(1, 3))

    with pytest.raises(EvidenceInvalid, match="evidence loss"):
        analyze_dynamic_transport(
            run(samples, chunks=(chunk(samples, evidence_loss=True),)),
            shadow_force_n=SHADOW_FORCE_N,
        )


def test_analyzer_rejects_unclosed_waypoint_boundary() -> None:
    samples = tuple(sample(step, 1.0) for step in range(1, 3))
    boundaries = (
        TransportBoundary(TransportBoundaryKind.PHASE_START, 1, 1),
        TransportBoundary(TransportBoundaryKind.WAYPOINT_START, 1, 1),
        TransportBoundary(TransportBoundaryKind.PHASE_END, 1, 2),
    )

    with pytest.raises(EvidenceInvalid, match="unclosed waypoint boundary"):
        analyze_dynamic_transport(
            run(samples, boundaries=boundaries), shadow_force_n=SHADOW_FORCE_N
        )


def test_analyzer_does_not_integrate_across_waypoint_boundary() -> None:
    samples = tuple(sample(step, force) for step, force in enumerate((1, 3, 9, 5), 1))
    boundaries = (
        TransportBoundary(TransportBoundaryKind.PHASE_START, 1, 1),
        TransportBoundary(TransportBoundaryKind.WAYPOINT_START, 1, 1),
        TransportBoundary(TransportBoundaryKind.WAYPOINT_END, 1, 2),
        TransportBoundary(TransportBoundaryKind.WAYPOINT_START, 2, 3),
        TransportBoundary(TransportBoundaryKind.WAYPOINT_END, 2, 4),
        TransportBoundary(TransportBoundaryKind.PHASE_END, 2, 4),
    )

    summary = analyze_dynamic_transport(
        run(samples, boundaries=boundaries), shadow_force_n=SHADOW_FORCE_N
    )

    assert summary.force_time_exposure_n_s == pytest.approx(0.018)
    assert [item.force_time_exposure_n_s for item in summary.waypoints] == pytest.approx(
        [0.004, 0.014]
    )


def test_atomic_store_keeps_readable_hashed_prefix_after_safety_abort(tmp_path: Path) -> None:
    store = AtomicTransportEvidenceStore(tmp_path, run_id="EXP-110")
    first = chunk(tuple(sample(step, 1.0) for step in range(1, 4)))
    second = chunk(tuple(sample(step, force) for step, force in ((4, 2.0), (5, 11.60))), sequence=1)

    first_hash = store.checkpoint_chunk(first)
    second_hash = store.checkpoint_chunk(second)
    index_path = store.close_partial(
        outcome_class="VALID_SAFETY_ABORT",
        trigger_physics_step=5,
    )

    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert index["outcome_class"] == "VALID_SAFETY_ABORT"
    assert index["trigger_physics_step"] == 5
    assert [item["sha256"] for item in index["chunks"]] == [first_hash, second_hash]
    assert all((tmp_path / item["path"]).is_file() for item in index["chunks"])
