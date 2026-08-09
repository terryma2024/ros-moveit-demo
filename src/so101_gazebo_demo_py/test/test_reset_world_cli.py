from types import SimpleNamespace

from so101_gazebo_demo_py.cli.reset_so101_world import reset_live_world
from so101_gazebo_demo_py.test_support.live_attachment import PoseSample
from so101_gazebo_demo_py.test_support.ros_gazebo_backend import make_set_pose_request


def test_set_pose_request_contains_full_world_pose() -> None:
    request = make_set_pose_request(
        "plastic_cup", (0.02, -0.28, 0.165, 0.0, 0.0, 0.0, 1.0),
    )

    assert 'name: "plastic_cup"' in request
    assert "x: 0.02" in request
    assert "y: -0.28" in request
    assert "z: 0.165" in request
    assert "w: 1.0" in request


def test_live_reset_parks_homes_respawns_and_proves_world_state() -> None:
    events: list[object] = []
    parking = (0.19, -0.44, 0.165, 0.0, 0.0, 0.0, 1.0)
    spawn = (0.02, -0.28, 0.165, 0.0, 0.0, 0.0, 1.0)

    class Transport:
        def publish_empty(self, topic: str) -> bool:
            events.append(("detach", topic))
            return True

    class Backend:
        def __init__(self) -> None:
            self.pose = parking

        def attachment_state(self) -> str:
            return "detached"

        def set_object_pose(self, pose) -> None:
            self.pose = pose
            events.append(("pose", pose))

        def move_arm(self, points) -> None:
            events.append(("arm", points))

        def move_gripper(self, q6) -> None:
            events.append(("gripper", q6))

        def sample(self) -> PoseSample:
            return PoseSample(
                self.pose[:3], (0.0, 0.0, 0.25), self.pose[3:],
                (0.0, 0.0, 0.0, 1.0), 0.0,
            )

        def contacts(self):
            return ()

    def apply_scene(operation, pose):
        events.append(("scene", operation, pose))
        return {"world_objects": ["plastic_cup"], "attached_objects": []}

    evidence = reset_live_world(
        Backend(), Transport(), apply_scene,
        object_id="plastic_cup", parking_pose=parking, spawn_pose=spawn,
        home_arm=(0.0, 0.0, 0.0, 0.0, 0.0), home_gripper=0.0,
        timeout_s=0.5, monotonic=iter((0.0, 0.0, 0.0)).__next__, wait=lambda _: None,
    )

    assert evidence["status"] == "RESET_WORLD_PROVED"
    assert evidence["object_pose_error_m"] == 0.0
    assert events == [
        ("detach", "/so101/detach_object"),
        ("pose", parking),
        ("scene", "detach", parking),
        ("arm", ((0.0, 0.0, 0.0, 0.0, 0.0),)),
        ("gripper", 0.0),
        ("pose", spawn),
        ("scene", "detach", spawn),
    ]
