"""Child commands run the qualified install, never whatever the PATH finds first (CP-3459).

Live L1 and L2 on freeze feAWPg9k showed what a command that is not pinned can do: the perception broker ran the `so101_demo` baked
into its image, and the baked parser refused the freeze's runtime config. This module is the other half of that fix. A role command is
resolved before it starts:

* a Python interpreter must be the running one (`sys.executable`), and a `-m so101_*` module must come from the qualified install;
* an `so101_*` console script must be an absolute path under the qualified install;
* `docker` is taken from the fixed system directories, `ros2` from `/opt/ros/<distro>/bin`;
* everything else is refused, and so is any bare name: nothing is looked up through `PATH`.

The qualified install is `$SO101_QUALIFIED_FREEZE/qualified-install` (the live scripts export the freeze). Without it only the allow
list applies.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

SYSTEM_BIN_DIRS = ("/usr/local/bin", "/usr/bin", "/bin")


class QualifiedCommandError(ValueError):
    """A role command is not one the qualified install may run."""


def qualified_prefix_from_env(environ=None):
    environ = os.environ if environ is None else environ
    freeze = environ.get("SO101_QUALIFIED_FREEZE")
    return None if not freeze else Path(freeze) / "qualified-install"


def _inside(path, prefix) -> bool:
    return Path(os.path.realpath(path)).is_relative_to(Path(os.path.realpath(prefix)))


def resolve_role_command(argv, *, prefix, environ=None) -> tuple:
    """The command with its executable made absolute and checked, or QualifiedCommandError."""
    environ = os.environ if environ is None else environ
    command = tuple(str(item) for item in argv)
    if not command:
        raise QualifiedCommandError("ROLE_EXECUTABLE_NOT_QUALIFIED: empty command")
    head = command[0]
    name = Path(head).name
    if head == sys.executable or (os.path.isabs(head) and os.path.realpath(head) == os.path.realpath(sys.executable)):
        if len(command) >= 3 and command[1] == "-m" and command[2].split(".")[0].startswith("so101"):
            spec = importlib.util.find_spec(command[2])
            origin = None if spec is None else spec.origin
            if origin is None or (prefix is not None and not _inside(origin, prefix)):
                raise QualifiedCommandError(f"ROLE_MODULE_OUTSIDE_QUALIFIED_INSTALL: {command[2]} from {origin}")
        return command
    if name.startswith("so101_"):
        if not os.path.isabs(head):
            raise QualifiedCommandError(f"ROLE_EXECUTABLE_NOT_QUALIFIED: {head} is not an absolute path")
        if prefix is None or not _inside(head, prefix):
            raise QualifiedCommandError(f"ROLE_EXECUTABLE_OUTSIDE_QUALIFIED_INSTALL: {head}")
        return command
    if head == "docker":
        for directory in SYSTEM_BIN_DIRS:
            candidate = Path(directory) / "docker"
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return (str(candidate), *command[1:])
        raise QualifiedCommandError("ROLE_EXECUTABLE_NOT_QUALIFIED: docker is not in a system directory")
    if head == "ros2":
        candidate = Path("/opt/ros") / environ.get("ROS_DISTRO", "jazzy") / "bin" / "ros2"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return (str(candidate), *command[1:])
        raise QualifiedCommandError(f"ROLE_EXECUTABLE_NOT_QUALIFIED: {candidate} is absent")
    raise QualifiedCommandError(f"ROLE_EXECUTABLE_NOT_QUALIFIED: {head}")
