"""Deterministic physical gate for the built-in Gazebo DetachableJoint path."""

from dataclasses import dataclass
import math
from typing import Protocol

from ..gazebo.observer import ContactPair, evaluate_bilateral_contact


MOVE_ABOVE = (
    (-0.000029929789, -0.046663179375, 0.099180979679, 0.122015827744, -0.000030721927),
    (-0.000059858745, -0.013447375821, 0.104582549290, 0.257932082627, -0.000061457654),
    (-0.000089803385, 0.019877351719, 0.109854985221, 0.393868547204, -0.000092213740),
    (-0.000119780059, 0.053310394277, 0.114996643444, 0.529827474472, -0.000123005343),
    (-0.000149825840, 0.086850997189, 0.120006021230, 0.665811121822, -0.000153869030),
    (-0.000180041637, 0.120498260828, 0.124881759225, 0.801821748234, -0.000184906200),
    (-0.000210775061, 0.154251141398, 0.129622643714, 0.937861611221, -0.000216467924),
    (-0.000243607881, 0.188108450812, 0.134227610432, 1.073932963127, -0.000250153053),
    (-0.000262861045, 0.194537121629, 0.131941532620, 1.157057183920, -0.000269854131),
    (-0.000282114209, 0.200965792445, 0.129655454807, 1.240181404713, -0.000289555209),
)
DESCEND = (
    (-0.000276912349, 0.287984861834, 0.150788067636, 1.132029723496, -0.000284352650),
    (-0.000283745683, 0.253568199427, 0.213237198063, 1.103997256470, -0.000291185985),
    (-0.000283936540, 0.312943337339, 0.250048785615, 1.007810530006, -0.000291376841),
    (-0.000284124852, 0.381814591288, 0.272246878070, 0.916741182602, -0.000291565154),
    (-0.0002665, 0.4710758, 0.216081, 0.856893, 0.000519),
)
CLOSE_ARM = ((-0.00020625043678042045, 0.4729760885971835, 0.21366460219615677,
              0.8536428664553183, 0.0005763926466606473),)
MICRO_LIFT = ((-0.0002062266287315138, 0.46262046903357984, 0.21277364017949124,
               0.8648894480356747, 0.0005764164414532356),)
RETRY_Q6_TARGETS = tuple(-0.047608632840292 - 0.001 * step for step in range(1, 5))


@dataclass(frozen=True, slots=True)
class PoseSample:
    object_xyz: tuple[float, float, float]
    tcp_xyz: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class LiveAttachmentEvidence:
    bilateral_contact_before_attach: bool
    attached: bool
    micro_lift_world_z: float
    max_object_tcp_drift_m: float
    solver_stable: bool
    detached: bool
    object_settled_independently: bool
    original_collision_plugin_loaded: bool


class LiveBackend(Protocol):
    def move_arm(self, points: tuple[tuple[float, ...], ...]) -> None: ...
    def move_gripper(self, target_q6: float) -> None: ...
    def contacts(self) -> tuple[ContactPair, ...]: ...
    def set_attached(self, attached: bool) -> None: ...
    def sample(self) -> PoseSample: ...
    def attachment_state(self) -> str: ...
    def solver_stable(self) -> bool: ...
    def original_collision_plugin_loaded(self) -> bool: ...


def _delta(after: tuple[float, float, float], before: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(a - b for a, b in zip(after, before, strict=True))


class LiveAttachmentGate:
    def __init__(self, backend: LiveBackend) -> None:
        self.backend = backend

    def run(self) -> LiveAttachmentEvidence:
        self.backend.set_attached(False)
        self.backend.sample()
        self.backend.move_gripper(0.465038)
        self.backend.move_arm(MOVE_ABOVE)
        self.backend.move_arm(DESCEND)
        self.backend.move_arm(CLOSE_ARM)
        self.backend.move_gripper(-0.047608632840292)
        contact = evaluate_bilateral_contact(self.backend.contacts())
        for target_q6 in RETRY_Q6_TARGETS:
            if contact.bilateral:
                break
            if contact.moving_jaw and not contact.within_solver_depth_limit:
                break
            self.backend.move_gripper(0.465038)
            self.backend.move_gripper(target_q6)
            contact = evaluate_bilateral_contact(self.backend.contacts())
        if not contact.bilateral:
            raise RuntimeError(f"bilateral contact gate failed: {contact}")
        self.backend.set_attached(True)
        attached = self.backend.attachment_state() == "attached"
        before = self.backend.sample()
        self.backend.move_arm(MICRO_LIFT)
        after = self.backend.sample()
        hold = self.backend.sample()
        tcp_delta = _delta(after.tcp_xyz, before.tcp_xyz)
        object_delta = _delta(after.object_xyz, before.object_xyz)
        drift = math.dist(tcp_delta, object_delta)
        hold_drift = math.dist(_delta(hold.object_xyz, after.object_xyz), (0.0, 0.0, 0.0))
        self.backend.set_attached(False)
        detached = self.backend.attachment_state() == "detached"
        self.backend.move_gripper(0.465038)
        settled = self.backend.sample()
        independently_settled = detached and settled.object_xyz[2] < hold.object_xyz[2] - 0.001
        return LiveAttachmentEvidence(
            bilateral_contact_before_attach=contact.bilateral,
            attached=attached,
            micro_lift_world_z=tcp_delta[2],
            max_object_tcp_drift_m=max(drift, hold_drift),
            solver_stable=self.backend.solver_stable(),
            detached=detached,
            object_settled_independently=independently_settled,
            original_collision_plugin_loaded=self.backend.original_collision_plugin_loaded(),
        )


def run_live_gate() -> LiveAttachmentEvidence:
    from .ros_gazebo_backend import RosGazeboLiveBackend
    return LiveAttachmentGate(RosGazeboLiveBackend()).run()
