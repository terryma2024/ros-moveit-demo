"""The public macOS MPS single-worker `FULL_RESTART_RETRY` entry point (schema v5).

This entry names exactly one profile of the design's support matrix:

    schema_version     5
    execution_profile  MPS_SINGLE_WORKER_FULL_RESTART_RETRY
    batch_kind         FULL_RESTART_RETRY
    worker_count       1

One slot, one Worker, one ROS domain. The routing key is not a set of flags: there is no
``--batch-kind`` and no ``--execution-profile`` switch to flip, and a first-pass (v6) or exact two-worker
(v4) document handed to this entry is refused before anything is spawned. The three profiles share
one implementation - the campaign body, the MPS broker, the station owner, the control endpoint,
the hard timeout and the cleanup primitive - so what differs here is only the route.
"""

from __future__ import annotations

import sys

from ..parallel_batch.single_worker_composition import (
    MPS_SINGLE_WORKER_FULL_RESTART_RETRY,
    SINGLE_WORKER_RETRY_BATCH_KIND,
)
from .macos_two_worker_campaign import build_single_worker_parser, main_single_worker, run_single_worker

#: The one route this entry point executes. Named so a caller can check it without parsing argv.
EXECUTION_PROFILE = MPS_SINGLE_WORKER_FULL_RESTART_RETRY
BATCH_KIND = SINGLE_WORKER_RETRY_BATCH_KIND
WORKER_COUNT = 1


def build_parser():
    """The v5 single-worker parser. It accepts no generic batch-kind or profile flag."""

    return build_single_worker_parser(EXECUTION_PROFILE)


def run(argv: list[str] | None = None) -> int:
    """Resolve the route, compose and drive the single-Worker retry campaign."""

    return run_single_worker(argv, execution_profile=EXECUTION_PROFILE)


def main(argv: list[str] | None = None) -> int:
    return main_single_worker(EXECUTION_PROFILE, argv)


if __name__ == "__main__":
    sys.exit(main())
