"""Where one processor finds its directories. A container and a native process differ only in these paths.

    owned_root     the processor's private directory (`<run>/processing/pNN/gK`), the same path on the Host and in the container
    output_root    where it writes `tasks/<task_id>/task-result.json`; `<owned_root>/output`
    control_root   the directory of the control sockets and the ready record
    python         the interpreter that runs `so101_demo.cli.act_offline_episode`
"""

from dataclasses import dataclass
from pathlib import Path


def _absolute(value):
    if not isinstance(value, (str, Path)) or not value:
        raise ValueError("ACT_PROCESSOR_LAYOUT_INVALID")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or "\x00" in str(path):
        raise ValueError("ACT_PROCESSOR_LAYOUT_INVALID")
    return path


@dataclass(frozen=True, slots=True)
class ProcessorLayout:
    owned_root: Path
    output_root: Path
    control_root: Path
    python: Path

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, _absolute(getattr(self, name)))
        if self.output_root == self.owned_root or self.control_root == self.owned_root:
            raise ValueError("ACT_PROCESSOR_LAYOUT_INVALID")
