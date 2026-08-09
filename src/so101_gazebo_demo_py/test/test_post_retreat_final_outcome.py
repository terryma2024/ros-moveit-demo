from types import SimpleNamespace

from so101_gazebo_demo_py import live_execute


def test_arm_tcp_motion_is_an_outcome_gate() -> None:
    previous = (0.0, 0.0, 0.20, 0.0, 0.0, 0.0, 1.0)
    settled = (0.00001, 0.0, 0.20, 0.0, 0.0, 0.0, 1.0)
    moving = (0.001, 0.0, 0.20, 0.0, 0.0, 0.0, 1.0)

    assert live_execute.arm_tcp_stable_between(
        previous, settled, elapsed_s=0.05,
        max_linear_speed_m_s=0.001,
        max_angular_speed_rad_s=0.05,
    )
    assert not live_execute.arm_tcp_stable_between(
        previous, moving, elapsed_s=0.05,
        max_linear_speed_m_s=0.001,
        max_angular_speed_rad_s=0.05,
    )


def test_retreat_is_between_independent_pre_and_post_outcome_epochs() -> None:
    events: list[str] = []
    tipped = [False]
    epochs = iter(("pre-retreat-epoch", "post-retreat-epoch"))

    def collect_epoch():
        epoch_id = next(epochs)
        events.append(f"collect:{epoch_id}")
        return SimpleNamespace(
            epoch_id=epoch_id,
            evaluation=SimpleNamespace(
                success=not tipped[0],
                failure_code=None if not tipped[0] else "FINAL_TIPPED",
            ),
        )

    def retreat(pre_retreat) -> None:
        events.append(f"retreat-after:{pre_retreat.epoch_id}")
        tipped[0] = True

    assert hasattr(live_execute, "collect_final_outcomes_around_retreat")
    result = live_execute.collect_final_outcomes_around_retreat(
        collect_epoch=collect_epoch,
        retreat=retreat,
    )

    assert result.pre_retreat.epoch_id == "pre-retreat-epoch"
    assert result.pre_retreat.evaluation.success
    assert result.post_retreat.epoch_id == "post-retreat-epoch"
    assert not result.post_retreat.evaluation.success
    assert result.post_retreat.evaluation.failure_code == "FINAL_TIPPED"
    assert events == [
        "collect:pre-retreat-epoch",
        "retreat-after:pre-retreat-epoch",
        "collect:post-retreat-epoch",
    ]
