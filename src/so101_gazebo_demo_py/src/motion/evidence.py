from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class RobotStateEvidence:
    joint_names: tuple[str, ...]
    positions: tuple[float, ...]
    velocities: tuple[float, ...]
    tcp_position: tuple[float, float, float]
