"""Resolved SO-101 runtime naming and q6 policy values."""

from dataclasses import dataclass

from .policy_config import PolicyBundle


@dataclass(frozen=True, slots=True)
class SO101Profile:
    world_name: str
    planning_group: str
    tcp_link: str
    arm_joints: tuple[str, ...]
    gripper_joint: str
    object_model: str
    object_link: str
    attach_topic: str
    detach_topic: str
    attachment_event_topic: str
    attachment_state_topic: str
    preopen_q6: float
    grasp_close_q6: float
    release_q6: float

    @classmethod
    def from_bundle(cls, bundle: PolicyBundle) -> "SO101Profile":
        return cls(
            world_name="so101_pick_place",
            planning_group="arm",
            tcp_link="so101_tcp",
            arm_joints=bundle.motion.arm_joints,
            gripper_joint=bundle.motion.gripper_joint,
            object_model=bundle.object.object_id,
            object_link="body",
            attach_topic="/so101/attach_object",
            detach_topic="/so101/detach_object",
            attachment_event_topic="/so101/object_attached_event",
            attachment_state_topic="/so101/object_attached",
            preopen_q6=bundle.motion.preopen_q6,
            grasp_close_q6=bundle.motion.grasp_close_q6,
            release_q6=bundle.motion.release_q6,
        )
