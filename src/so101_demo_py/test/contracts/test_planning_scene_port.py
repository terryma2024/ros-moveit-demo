from so101_demo.control.planning_scene.adapter import PlanningSceneAdapter
from so101_demo.ports.evidence import PoseEvidence
from so101_demo.ports.planning_scene import PlanningScenePort, WorldObjectRequest


class FakeSceneBackend:
    def __init__(self) -> None:
        self.operations: list[tuple[object, ...]] = []

    def apply(self, operation: tuple[object, ...]) -> bool:
        self.operations.append(operation)
        return True


def test_scene_attachment_is_not_physical_grasp() -> None:
    """Catch a Planning Scene shadow being reported as physical grasp proof."""

    scene = PlanningSceneAdapter(FakeSceneBackend())
    result = scene.attach_shadow("plastic_cup", "so101_tcp")
    assert result.scene_applied
    assert not result.physical_grasp_proved


def test_scene_lease_releases_exactly_the_acquired_pair() -> None:
    """Catch leaked or over-broad temporary collision permissions."""

    backend = FakeSceneBackend()
    scene = PlanningSceneAdapter(backend)
    lease = scene.temporary_allow_collision(("jaw", "plastic_cup"))
    assert lease.acquired
    assert lease.release().scene_applied
    assert lease.released
    assert backend.operations == [
        ("allow_collision", "jaw", "plastic_cup"),
        ("restore_collision", "jaw", "plastic_cup"),
    ]


def test_planning_scene_port_exposes_complete_shadow_contract() -> None:
    assert set(PlanningScenePort.__protocol_attrs__) >= {
        "add_world_object",
        "attach_shadow",
        "detach_shadow",
        "synchronize_object_pose",
        "temporary_allow_collision",
    }
    request = WorldObjectRequest(
        "plastic_cup",
        PoseEvidence((0.0, 0.0, 0.1), (0.0, 0.0, 0.0, 1.0)),
        "mesh",
    )
    assert request.object_id == "plastic_cup"
