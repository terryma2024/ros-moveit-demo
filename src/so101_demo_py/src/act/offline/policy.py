"""The frozen Recorder policy document (`episode_recorder`), loaded and validated.

The policy is baked into every frozen inputs manifest (`frozen_runtime_inputs`, `first_episode_inputs`), so its closed schema is
unchanged by the removal of the live Recorder: keys only the live Recorder read (`ready_timeout_s`, `capturing_timeout_s`,
`exit_wait_s`, `term_grace_s`, `physics_spool_backlog_frames_max`) are still required and validated, and nothing reads them.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

POLICY_KIND = "ACT_EPISODE_RECORDER_POLICY"
_POLICY_FIELDS = frozenset({"kind", "schema_version", "max_duration_s", "event_inbox_capacity", "finish_budget_s",
                            "poll_s", "ready_timeout_s", "capturing_timeout_s", "exit_wait_s", "term_grace_s",
                            "physics_spool_backlog_frames_max", "physics_receiver_lag_max_s"})


class RecorderConfigRefused(ValueError):
    """The configuration cannot be honoured; the process exits with rc 2 before recording anything."""


# ---- configuration -----------------------------------------------------------------------------------------------

def _number(value, *, low, high, name, integer=False):
    kind = int if integer else (int, float)
    if type(value) is bool or not isinstance(value, kind) or (not integer and not math.isfinite(value)):
        raise RecorderConfigRefused(f"RECORDER_POLICY_INVALID: {name}")
    if not low <= value <= high:
        raise RecorderConfigRefused(f"RECORDER_POLICY_INVALID: {name}")
    return value


def load_recorder_policy(source) -> dict:
    """Load and validate the frozen recorder policy from YAML bytes or a path, with its sha256."""

    import yaml

    try:
        data = Path(source).read_bytes() if isinstance(source, (str, os.PathLike)) else bytes(source)
    except OSError as error:
        raise RecorderConfigRefused(f"RECORDER_POLICY_UNREADABLE: {error}") from error
    try:
        document = yaml.safe_load(data)
    except yaml.YAMLError as error:
        raise RecorderConfigRefused(f"RECORDER_POLICY_INVALID: not YAML: {error}") from error
    if type(document) is not dict or set(document) != _POLICY_FIELDS:
        raise RecorderConfigRefused("RECORDER_POLICY_INVALID: not the closed policy document")
    if (document["kind"] != POLICY_KIND or type(document["schema_version"]) is not int
            or document["schema_version"] != 1):
        raise RecorderConfigRefused("RECORDER_POLICY_INVALID: unknown kind or schema version")
    policy = {
        "kind": POLICY_KIND, "schema_version": 1,
        "max_duration_s": float(_number(document["max_duration_s"], low=60.0, high=900.0, name="max_duration_s")),
        "event_inbox_capacity": _number(document["event_inbox_capacity"], low=8, high=4096,
                                        name="event_inbox_capacity", integer=True),
        "finish_budget_s": float(_number(document["finish_budget_s"], low=0.1, high=30.0, name="finish_budget_s")),
        "poll_s": float(_number(document["poll_s"], low=0.0, high=1.0, name="poll_s")),
        # The orchestrator's bounds (A4c): how long it waits for the LISTENING ready file before it starts the Teacher
        # regardless, how long it waits for the Recorder to exit after the Teacher ended, and the grace after SIGTERM.
        "ready_timeout_s": float(_number(document["ready_timeout_s"], low=0.1, high=60.0, name="ready_timeout_s")),
        "capturing_timeout_s": float(_number(document["capturing_timeout_s"], low=0.1, high=60.0, name="capturing_timeout_s")),
        "exit_wait_s": float(_number(document["exit_wait_s"], low=0.1, high=120.0, name="exit_wait_s")),
        "term_grace_s": float(_number(document["term_grace_s"], low=0.1, high=30.0, name="term_grace_s")),
        # CP-3410: the raw-chunk data fails on a backlog, not on one late chunk. Upper bounds are the structures that hold
        # the backlog: the adapter's 128-chunk pending queue and its 4096-step (8.19 s) lookup history.
        "physics_spool_backlog_frames_max": _number(document["physics_spool_backlog_frames_max"], low=1, high=128,
                                                    name="physics_spool_backlog_frames_max", integer=True),
        "physics_receiver_lag_max_s": float(_number(document["physics_receiver_lag_max_s"], low=0.5, high=8.0,
                                                    name="physics_receiver_lag_max_s")),
    }
    digest = hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {**policy, "policy_sha256": digest}


def check_outputs_absent(*paths) -> None:
    for path in paths:
        if os.path.lexists(path):
            raise RecorderConfigRefused(f"RECORDER_OUTPUT_EXISTS: {path}")
