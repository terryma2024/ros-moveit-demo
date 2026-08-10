from so101_mujoco_demo_py.domain import ActionStatus
from so101_mujoco_demo_py.moveit.scene import MoveItSceneClient, Pose3D, SceneObservation


class PlanningSceneBackend:
    def __init__(self):
        self.observation = SceneObservation(
            frozenset({"table", "pedestal", "plastic_cup"}),
            None,
            None,
        )
        self.calls = []

    def apply(self, operation):
        self.calls.append(operation)
        if operation[0] == "attach":
            self.observation = SceneObservation(
                frozenset({"table", "pedestal"}),
                "plastic_cup",
                "gripper",
            )
        else:
            self.observation = SceneObservation(
                frozenset({"table", "pedestal", "plastic_cup"}),
                None,
                None,
                operation[2],
            )
        return True

    def observe(self):
        return self.observation


def test_attach_and_detach_converge_as_collision_shadow_only() -> None:
    backend = PlanningSceneBackend()
    client = MoveItSceneClient(backend)
    attached = client.attach_task_object("plastic_cup", "gripper", ("gripper", "jaw"))
    assert attached.status is ActionStatus.SUCCEEDED
    assert backend.calls[-1] == (
        "attach",
        "plastic_cup",
        "gripper",
        ("gripper", "jaw"),
    )
    pose = Pose3D((1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0))
    assert client.detach_task_object("plastic_cup", pose).status is ActionStatus.SUCCEEDED
    observed = client.observe(0.01)
    assert observed.required_world_objects_present(("table", "pedestal", "plastic_cup"))
    assert observed.world_pose == pose


def test_invalid_shadow_links_fail_without_applying_scene_change() -> None:
    backend = PlanningSceneBackend()
    result = MoveItSceneClient(backend).attach_task_object(
        "plastic_cup", "so101_tcp", ("so101_tcp",)
    )
    assert result.status is ActionStatus.FAILED
    assert result.failure.code == "MOVEIT_SCENE_ATTACHMENT_CONTRACT"
    assert backend.calls == []
