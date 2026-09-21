"""The public macOS MPS W1 `FULL_RESTART_RETRY` entry point (schema v5).

This entry names exactly one profile of the design's support matrix:

    schema_version     5
    execution_profile  MPS_W1_FULL_RESTART_RETRY
    batch_kind         FULL_RESTART_RETRY
    worker_count       1

One slot, one Worker, one ROS domain. The routing key is not a set of flags: there is no
``--batch-kind`` and no ``--execution-profile`` switch to flip, and a first-pass (v6) or exact-W2
(v4) document handed to this entry is refused before anything is spawned. The three profiles share
one implementation - the campaign body, the MPS broker, the station owner, the control endpoint,
the hard timeout and the cleanup primitive - so what differs here is only the route.
"""

from __future__ import annotations

import sys

from ..parallel_batch.w1_composition import (
    MPS_W1_FULL_RESTART_RETRY,
    W1_RETRY_BATCH_KIND,
)
from .macos_w2_campaign import build_w1_parser, main_w1, run_w1

#: The one route this entry point executes. Named so a caller can check it without parsing argv.
EXECUTION_PROFILE = MPS_W1_FULL_RESTART_RETRY
BATCH_KIND = W1_RETRY_BATCH_KIND
WORKER_COUNT = 1


def build_parser():
    """The v5 W1 parser. It accepts no generic batch-kind or profile flag."""

    return build_w1_parser(EXECUTION_PROFILE)


def run(argv: list[str] | None = None) -> int:
    """Resolve the route, compose and drive the single-Worker retry campaign."""

    return run_w1(argv, execution_profile=EXECUTION_PROFILE)


def main(argv: list[str] | None = None) -> int:
    return main_w1(EXECUTION_PROFILE, argv)


if __name__ == "__main__":
    sys.exit(main())
