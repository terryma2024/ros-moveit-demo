"""The native shell of the ACT instance program: checks the native-only facts, builds the layout, runs it.

Everything an instance does lives in `so101_demo.runtime.act_instance.program`. This shell only knows what is true for a
native single worker started by `NativeInstanceOwner`: the process leads a session and process group of its own, the Host set
the instance environment (the fixed ROS identity and the instance marker naming this owned root), the code it runs is the
installed prefix the Host named, and its directories are the owned root's own: `output`, `control`, and the Teacher socket
under the campaign run (the Host path of the socket the Teacher container mounts).
"""

import argparse
import asyncio
import os
from pathlib import Path
import sys

from so101_demo.runtime.act_instance.identity import INSTANCE_OUTPUT_ENV, INSTANCE_ROOT_ENV
from so101_demo.runtime.act_instance.layout import InstanceLayout
from so101_demo.runtime.act_instance.program import run_instance
from so101_demo.runtime.act_instance.spec import load_spec
from so101_demo.runtime.container_campaign.paths import campaign_run_root, host_teacher_socket


def native_layout(spec, install_prefix, ros2_executable):
    """The layout of a native instance: its owned root's own directories and the Host path of the Teacher socket."""
    root = Path(spec["owned_root"])
    return InstanceLayout(owned_root=root, output_root=root/"output", control_root=root/"control",
        teacher_socket=host_teacher_socket(campaign_run_root(root)), install_prefix=Path(install_prefix),
        ros2_executable=Path(ros2_executable))


def running_installed_code(install_prefix):
    """Whether the imported `so101_demo` is the installed package under the Host-named prefix, not a source tree."""
    import so101_demo

    return Path(os.path.abspath(so101_demo.__file__)).is_relative_to(Path(install_prefix))


def check_native_process(spec, install_prefix):
    """The facts a native instance must have before it runs the program; the program checks the rest."""
    root = spec["owned_root"]
    if os.getpid() != os.getpgrp() or os.getpid() != os.getsid(0):
        raise ValueError("CAMPAIGN_NATIVE_GROUP_REQUIRED")
    if os.environ.get(INSTANCE_ROOT_ENV) != root or os.environ.get(INSTANCE_OUTPUT_ENV) != root+"/output":
        raise ValueError("CAMPAIGN_NATIVE_ENVIRONMENT_DRIFT")
    if not Path(install_prefix).is_absolute() or not running_installed_code(install_prefix):
        raise ValueError("CAMPAIGN_NATIVE_CODE_NOT_INSTALLED")


async def run_native(spec, runtime_config, install_prefix, ros2_executable):
    check_native_process(spec, install_prefix)
    return await run_instance(spec, runtime_config, native_layout(spec, install_prefix, ros2_executable))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--install-prefix", type=Path, required=True)
    parser.add_argument("--ros2", type=Path, required=True, help="the Host ros2 command the stack is launched and probed with")
    args = parser.parse_args(argv)
    try:
        spec, runtime = load_spec(args.spec)
    except (OSError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    try:
        return asyncio.run(run_native(spec, runtime, args.install_prefix, args.ros2))
    except (OSError, ValueError, RuntimeError) as error:
        print(f"CAMPAIGN_NATIVE_FAILED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
