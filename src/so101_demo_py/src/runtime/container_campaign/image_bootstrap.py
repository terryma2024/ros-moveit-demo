"""Run a fixed installed campaign role only after image-byte/runtime readback."""

import os
import sys

from so101_demo.runtime.container_campaign.mount_build import INSTALL_ENV
from so101_demo.runtime.container_campaign.provenance import read_installed_image, read_mounted_image
from so101_demo.runtime.inference.config import _open_regular
from so101_demo.runtime.parallel_ipc.frames import canonical_json


#: the role of a mount-mode container follows from the program it is asked to run (the base image has no role file)
MOUNT_ROLES = {"campaign_inference": "inference", "campaign_shard": "shard", "campaign_processor": "shard"}


def read_role():
    with _open_regular("/act/image-role") as stream:
        return stream.read(32).decode("ascii").strip()


def readback(mount_role=None):
    return read_installed_image() if mount_role is None else read_mounted_image(mount_role)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        mounted = bool(os.environ.get(INSTALL_ENV))
        if mounted:
            mount_role = MOUNT_ROLES.get(argv[0]) if argv else None
            allowed = tuple(MOUNT_ROLES) if mount_role else ()
        else:
            mount_role = None
            role = read_role()
            # The shard image also runs the phase-2 processor (same image, no GPU), so its role admits both programs.
            allowed = {"inference": ("campaign_inference",), "shard": ("campaign_shard", "campaign_processor")}.get(role, ())
        if not argv or argv[0] not in allowed or sys.executable != "/act/venv/bin/python":
            raise ValueError("IMAGE_ROLE_COMMAND_INVALID")
        report = readback(mount_role) if mounted else readback()
        print(canonical_json(report).decode(), flush=True)
        os.execv(sys.executable, [sys.executable, "-I", *(["-B"] if mounted else []), "-m", "so101_demo.cli."+argv[0], *argv[1:]])
        return 0
    except (OSError, ValueError, TypeError, KeyError, ImportError) as error:
        print(f"IMAGE_BOOTSTRAP_REFUSED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
