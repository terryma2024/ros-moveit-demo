from so101_gazebo_demo_py.domain import ActionStatus
from so101_gazebo_demo_py.moveit.scene import MoveItSceneClient, SceneObservation
from so101_gazebo_demo_py.policy_config import Pose3D


class Backend:
    def __init__(self): self.observation=SceneObservation(frozenset({"table","pedestal","plastic_cup"}), None, None); self.calls=[]
    def apply(self, operation):
        self.calls.append(operation)
        if operation[0] == "attach": self.observation=SceneObservation(frozenset({"table","pedestal"}), "plastic_cup", "gripper")
        else: self.observation=SceneObservation(frozenset({"table","pedestal","plastic_cup"}), None, None, operation[2])
        return True
    def observe(self): return self.observation


def test_attach_and_detach_converge_with_exact_links_and_world_pose() -> None:
    backend=Backend(); client=MoveItSceneClient(backend)
    assert client.attach_task_object("plastic_cup", "gripper", ("gripper","jaw")).status is ActionStatus.SUCCEEDED
    assert backend.calls[-1] == ("attach","plastic_cup","gripper",("gripper","jaw"))
    pose=Pose3D((1.,2.,3.,0.,0.,0.,1.))
    assert client.detach_task_object("plastic_cup", pose).status is ActionStatus.SUCCEEDED
    observed=client.observe(.01)
    assert observed.required_world_objects_present(("table","pedestal","plastic_cup"))
    assert observed.world_pose == pose
