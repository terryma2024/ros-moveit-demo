"""The worker resource allocator."""

from __future__ import annotations

import argparse
from pathlib import Path

from so101_demo.parallel_batch.resource_allocation.models import _DEFAULT_WORKER_COUNT


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--worker-count', type=int, default=_DEFAULT_WORKER_COUNT)
    parser.add_argument('--live-headroom-evidence', type=Path)
    parser.add_argument('--measurement-authorization', type=Path)
    parser.add_argument('--measurement-authorization-sha256')
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true', required=True)
    return parser
