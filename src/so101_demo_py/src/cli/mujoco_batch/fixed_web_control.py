"""The stop request of a fixed-count batch controlled from the web service."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re

from so101_demo.cli.mujoco_batch.common import CliError
from so101_demo.cli.mujoco_batch.request import PreparedBatch
from so101_demo.parallel_batch.contracts import (
    BatchRequest,
)


class _FixedWebStopRequested(CliError):
    """An authenticated durable stop must enter the existing cleanup path."""


@dataclass(frozen=True, slots=True)
class _FixedWebControl:
    campaign_id: str
    path: Path
    coordinator_epoch: int
    token: str = field(repr=False)


def _take_fixed_web_control(spec: PreparedBatch) -> _FixedWebControl | None:
    keys = (
        "SO101_FIXED_CONTROL_TOKEN", "SO101_FIXED_CONTROL_CAMPAIGN_ID",
        "SO101_FIXED_CONTROL_EPOCH", "SO101_FIXED_CONTROL_SOCKET",
    )
    if not any(key in os.environ for key in keys):
        return None
    # Consume all credentials before validation and before any child launch.
    values = {key: os.environ.pop(key) for key in keys if key in os.environ}
    if len(values) != len(keys):
        raise CliError("FIXED_CONTROL_ENV_INCOMPLETE")
    if not isinstance(spec.request, BatchRequest):
        raise CliError("FIXED_CONTROL_REQUEST_REQUIRED")
    token, campaign, epoch, socket_path = (values[key] for key in keys)
    if re.fullmatch(r"[0-9a-f]{64}", token) is None:
        raise CliError("FIXED_CONTROL_TOKEN_INVALID")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", campaign) is None:
        raise CliError("FIXED_CONTROL_CAMPAIGN_INVALID")
    if re.fullmatch(r"[1-9][0-9]{0,19}", epoch) is None:
        raise CliError("FIXED_CONTROL_EPOCH_INVALID")
    path = Path(socket_path)
    if (
        not path.is_absolute() or path != path.resolve(strict=False)
        or not path.is_relative_to(spec.request.evidence_root)
    ):
        raise CliError("FIXED_CONTROL_SOCKET_INVALID")
    return _FixedWebControl(campaign, path, int(epoch), token)
