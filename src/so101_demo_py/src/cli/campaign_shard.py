"""The container shell of the ACT instance program: checks the container-only facts, builds the fixed layout, runs it.

Everything an instance does lives in `so101_demo.runtime.act_instance.program`. This shell only knows what is true inside a
shard container: it is pid 1, it runs the base image's interpreter, its code is the mounted install tree, and its directories are
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
from so101_demo.runtime.container_campaign.mount_build import INSTALL_ENV, ROS2_EXECUTABLE
from so101_demo.runtime.container_campaign.paths import (
    CONTAINER_CONTROL_ROOT, CONTAINER_INTERPRETER, CONTAINER_POLICY_SOCKET, CONTAINER_TEACHER_SOCKET, TASK_OUTPUT_MOUNT)


def container_layout(spec):
    """The fixed layout of a shard container: the mounts of `build_role_mounts`, seen from inside. The code is the mounted package
    prefix (the entry script exported the mounted install) and `ros2` is the base image's own. A container without mounted trees is
    refused: image mode is retired."""
    mounted = os.environ.get(INSTALL_ENV)
    if not mounted:
        raise ValueError("CAMPAIGN_SHARD_MOUNT_REQUIRED")
    install, ros2 = Path(mounted) / "so101_demo_py", ROS2_EXECUTABLE
    return InstanceLayout(owned_root=Path(spec["owned_root"]), output_root=TASK_OUTPUT_MOUNT,
        control_root=CONTAINER_CONTROL_ROOT, teacher_socket=CONTAINER_TEACHER_SOCKET,
        install_prefix=install, ros2_executable=ros2,
        policy_socket=CONTAINER_POLICY_SOCKET if spec.get("workload_kind") == "act_rollout" else None)


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
