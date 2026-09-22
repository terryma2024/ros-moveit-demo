"""The public macOS MPS W1 `FIRST_PASS` entry point (schema v6).

This entry names exactly one profile of the design's support matrix:

    schema_version     6
    execution_profile  MPS_W1_FIRST_PASS
    batch_kind         FIRST_PASS
    worker_count       1

One slot, one Worker, one ROS domain, and no retry semantics: the single Worker drains the whole
selected set through the durable queue. The routing key is not a set of flags - there is no
``--batch-kind`` and no ``--execution-profile`` switch - and a retry (v5) or exact-W2 (v4)
document handed to this entry is refused before anything is spawned. The ``campaign_status``
helper is this profile's verdict: one Worker, at least three served requests on MPS, cleanup
proven complete and nothing refused.
"""

from __future__ import annotations

import sys

from ..parallel_batch.w1_composition import (
    MPS_W1_FIRST_PASS,
    W1_FIRST_PASS_BATCH_KIND,
)
from .macos_w2_campaign import build_w1_parser, campaign_verdict, main_w1, route_spec, run_w1

#: The one route this entry point executes. Named so a caller can check it without parsing argv.
EXECUTION_PROFILE = MPS_W1_FIRST_PASS
BATCH_KIND = W1_FIRST_PASS_BATCH_KIND
WORKER_COUNT = 1


def build_parser():
    """The v6 W1 parser. It accepts no generic batch-kind or profile flag."""

    return build_w1_parser(EXECUTION_PROFILE)


def run(argv: list[str] | None = None) -> int:
    """Resolve the route, compose and drive the single-Worker first-pass campaign."""

    return run_w1(argv, execution_profile=EXECUTION_PROFILE)


def campaign_status(*, cleanup_complete, results, workers, served, refused, points) -> str:
    """This profile's verdict, as a pure function so the rule is testable and readable.

    `points` is the campaign's own executed-point summary: a pass requires every selected point to
    have exactly one committed result, so a campaign that executed nothing cannot report one.
    """

    return campaign_verdict(spec=route_spec(EXECUTION_PROFILE), cleanup_complete=cleanup_complete,
                            results=results, workers=workers, served=served, refused=refused,
                            points=points)


def main(argv: list[str] | None = None) -> int:
    return main_w1(EXECUTION_PROFILE, argv)


if __name__ == "__main__":
    sys.exit(main())
