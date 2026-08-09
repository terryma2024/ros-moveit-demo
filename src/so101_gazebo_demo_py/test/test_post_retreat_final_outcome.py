from types import SimpleNamespace
from pathlib import Path

from so101_gazebo_demo_py import live_execute
from so101_gazebo_demo_py.gazebo.observer import ContactPair
from so101_gazebo_demo_py.policy_config import load_policy_bundle
from so101_gazebo_demo_py.test_support.live_attachment import PoseSample


PACKAGE = Path(__file__).parents[1]


def test_final_epoch_reuses_one_combined_observer_for_five_fresh_samples() -> None:
    bundle = load_policy_bundle(
        PACKAGE / "config/task_objects/light_plastic_cup.yaml",
        PACKAGE / "config/motion_policies/light_cup_wall_pick.yaml",
        PACKAGE / "config/validation_policies/light_cup_wall_pick.yaml",
    )
    calls = []

    class Observer:
        def observe(self):
            calls.append("observe")
            return (
                PoseSample(
                    (-0.08, -0.25, 0.165), (-0.07, -0.23, 0.26),
                    (0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0, 1.0), 0.0,
                ),
                (ContactPair("plastic_cup::body::bottom", "table::table_top::collision", (0.0,)),),
            )

    class Clock:
        def __init__(self):
            self.value = 0.0

        def __call__(self):
            self.value += 0.05
            return self.value

    result = live_execute.collect_final_outcome_epoch(
        Observer(), bundle.validation.physical_outcome,
        gazebo_detached=True,
        scene_membership={"world_objects": ["plastic_cup"], "attached_objects": []},
        monotonic=Clock(), wait=lambda _: None,
    )

    assert result.evaluation.success
    assert result.evaluation.sample_count == 5
    assert calls == ["observe"] * 5


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


def test_immediate_retreat_collects_only_post_retreat_outcome() -> None:
    events: list[str] = []

    def retreat() -> None:
        events.append("retreat")

    def collect_epoch():
        events.append("collect:post-retreat-epoch")
        return SimpleNamespace(epoch_id="post-retreat-epoch")

    result = live_execute.collect_final_outcome_after_immediate_retreat(
        collect_epoch=collect_epoch,
        retreat=retreat,
    )

    assert result.pre_retreat is None
    assert result.post_retreat.epoch_id == "post-retreat-epoch"
    assert events == ["retreat", "collect:post-retreat-epoch"]


def test_post_retreat_failure_is_persisted_before_it_is_raised() -> None:
    source = (PACKAGE / "so101_gazebo_demo_py/live_execute.py").read_text()
    final_path = source[source.index("outcomes=collect_final_outcomes_around_retreat"):]

    assert '"final-outcome-failure.json"' in final_path
    assert final_path.index('"final-outcome-failure.json"') < final_path.index(
        "post-retreat final physical outcome failed"
    )


def test_live_failure_evidence_persists_both_release_epochs() -> None:
    source = (PACKAGE / "so101_gazebo_demo_py/live_execute.py").read_text()
    final_path = source[source.index("outcomes=collect_final_outcomes_around_retreat"):]

    assert '"pre_retreat_outcome":collected_outcome_payload(' in final_path
    assert '"post_retreat_outcome":outcome_payload(' in final_path
    assert '"pre_retreat_final_sample":collected_final_sample_payload(' in final_path
    assert '"post_retreat_final_sample":final_sample_payload(' in final_path
