"""The container shell of the ACT instance program: checks the container-only facts, builds the fixed layout, runs it.

Everything an instance does lives in `so101_demo.runtime.act_instance.program`. This shell only knows what is true inside a
shard container: it is pid 1, it runs the image's interpreter, its code is installed at `/act/install`, and its directories are
the bind mounts `build_role_mounts` declares (`/act/output`, `/act/control`, `/act/ipc/teacher`).
"""

import argparse
import asyncio
import os
from pathlib import Path
import sys

from so101_demo.runtime.act_instance.layout import InstanceLayout
from so101_demo.runtime.act_instance.program import run_instance
from so101_demo.runtime.act_instance.spec import load_spec
from so101_demo.runtime.container_campaign.paths import (
    CONTAINER_CONTROL_ROOT, CONTAINER_INSTALL_PREFIX, CONTAINER_INTERPRETER, CONTAINER_ROS2, CONTAINER_TEACHER_SOCKET,
    TASK_OUTPUT_MOUNT)


def container_layout(spec):
    """The fixed layout of a shard container: the mounts of `build_role_mounts`, seen from inside."""
    return InstanceLayout(owned_root=Path(spec["owned_root"]), output_root=TASK_OUTPUT_MOUNT,
        control_root=CONTAINER_CONTROL_ROOT, teacher_socket=CONTAINER_TEACHER_SOCKET,
        install_prefix=CONTAINER_INSTALL_PREFIX, ros2_executable=CONTAINER_ROS2)


async def run_shard(spec, runtime_config):
    if os.getpid() != 1 or sys.executable != str(CONTAINER_INTERPRETER):
        raise ValueError("CAMPAIGN_SHARD_PRIVATE_CONTAINER_REQUIRED")
    return await run_instance(spec, runtime_config, container_layout(spec))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec",type=Path,required=True)
    args = parser.parse_args(argv)
    try:
        spec,runtime = load_spec(args.spec)
    except (OSError,ValueError,RuntimeError) as error:
        print(str(error),file=sys.stderr)
        return 2
    try:
        return asyncio.run(run_shard(spec,runtime))
    except (OSError,ValueError,RuntimeError) as error:
        print(f"CAMPAIGN_SHARD_FAILED: {error}",file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
