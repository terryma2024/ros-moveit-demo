"""Run a fixed installed campaign role only after image-byte/runtime readback."""

import os
import sys

from so101_demo.runtime.container_campaign.provenance import read_installed_image
from so101_demo.runtime.inference.config import _open_regular
from so101_demo.runtime.parallel_ipc.frames import canonical_json


def read_role():
    with _open_regular("/act/image-role") as stream:
        return stream.read(32).decode("ascii").strip()


def readback():
    return read_installed_image()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        role = read_role()
        # The shard image also runs the phase-2 processor (same image, no GPU), so its role admits both programs.
        allowed = {"inference": ("campaign_inference",), "shard": ("campaign_shard", "campaign_processor")}.get(role, ())
        if not argv or argv[0] not in allowed or sys.executable != "/act/venv/bin/python":
            raise ValueError("IMAGE_ROLE_COMMAND_INVALID")
        report = readback()
        print(canonical_json(report).decode(), flush=True)
        os.execv(sys.executable, [sys.executable, "-I", "-m", "so101_demo.cli."+argv[0], *argv[1:]])
        return 0
    except (OSError, ValueError, TypeError, KeyError, ImportError) as error:
        print(f"IMAGE_BOOTSTRAP_REFUSED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
