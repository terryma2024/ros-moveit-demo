"""Where one ACT instance finds its own directories, its control sockets, the Teacher socket and its installed code.

The instance program (`program.run_instance`) is one implementation for every launcher. What differs between a container
and a native single worker is only these paths, so they are injected here instead of being read from the program:

    owned_root       the instance's private directory (`<run>/wave-N/wNN/gM`), the same path on the Host and in the instance
    output_root      where the instance writes `tasks/<task_id>`; `<owned_root>/output` seen through the instance's own paths
    control_root     the directory of the control sockets and the ready record
    teacher_socket   the Teacher inference socket as the instance reaches it
    policy_socket    the policy service socket as a rollout instance reaches it (None for every other workload)
    install_prefix   the colcon prefix of the code the instance runs
    ros2_executable  the `ros2` command that launches and probes the stack (a container image carries its own copy)

A layout carries no behavior. The launcher shell builds it, `program.run_instance` checks and uses it.
"""

from dataclasses import dataclass
from pathlib import Path


def _absolute(value):
    if not isinstance(value, (str, Path)) or not value:
        raise ValueError("ACT_INSTANCE_LAYOUT_INVALID")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or "\x00" in str(path):
        raise ValueError("ACT_INSTANCE_LAYOUT_INVALID")
    return path


@dataclass(frozen=True, slots=True)
class InstanceLayout:
    owned_root: Path
    output_root: Path
    control_root: Path
    teacher_socket: Path
    install_prefix: Path
    ros2_executable: Path
    #: the policy service socket as the instance reaches it (a rollout instance only; None for every other workload)
    policy_socket: Path | None = None

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if name == "policy_socket" and value is None:
                continue
            object.__setattr__(self, name, _absolute(value))
        if self.output_root == self.owned_root or self.control_root == self.owned_root:
            raise ValueError("ACT_INSTANCE_LAYOUT_INVALID")
