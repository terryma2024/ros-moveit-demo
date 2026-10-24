"""Run a fixed campaign role from the mounted trees, only after their records and the imported runtime are read back.

The base image has no role file and no installed code: the role follows from the program the container is asked to run."""

import os
import sys

from so101_demo.runtime.container_campaign.mount_build import INSTALL_ENV
from so101_demo.runtime.container_campaign.provenance import read_mounted_image
from so101_demo.runtime.parallel_ipc.frames import canonical_json


MOUNT_ROLES = {"campaign_inference": "inference", "campaign_shard": "shard", "campaign_processor": "shard"}


def readback(mount_role):
    return read_mounted_image(mount_role)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        mount_role = MOUNT_ROLES.get(argv[0]) if argv else None
        if not os.environ.get(INSTALL_ENV) or mount_role is None or sys.executable != "/act/venv/bin/python":
            raise ValueError("IMAGE_ROLE_COMMAND_INVALID")
        report = readback(mount_role)
        print(canonical_json(report).decode(), flush=True)
        os.execv(sys.executable, [sys.executable, "-I", "-B", "-m", "so101_demo.cli."+argv[0], *argv[1:]])
        return 0
    except (OSError, ValueError, TypeError, KeyError, ImportError) as error:
        print(f"IMAGE_BOOTSTRAP_REFUSED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
