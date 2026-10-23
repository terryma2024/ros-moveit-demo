"""The rollout-side execution mode: how a chunk the policy predicts becomes the commanded trajectory.

The bundle freezes one mode (`execution_prefix` 1, no temporal ensembling): infer at every observation and apply the first action
only. The native rollout may override it at run time, without retraining. Two overrides exist and they are LOGIC settings: a run
with a different mode is a different experiment, so the effective mode is recorded in the run identity and in every episode.

``prefix N`` (ACT's standard open-loop execution). Infer, send the first N actions of the chunk as one trajectory
(targets at observation time + 0.1 s * 1..N), and infer again only from the first observation taken at or after the end of that
prefix. A reply or a prefix that is late (nothing was sent) starts no wait: the next observation infers at once.

``temporal ensembling M`` (the ACT paper scheme). Infer at every observation. The action for target time T averages the
predictions for T of every earlier chunk that still covers T, with weights w_i = exp(-M * i) where i = 0 is the OLDEST
contributing chunk. One step (T = observation + 0.1 s) is applied per inference. A chunk that arrives late is still kept: it is a
valid prediction for the steps after it.

Both are pure: no ROS, no clock.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

DT_S = 0.1
#: An open-loop prefix is considered consumed when the observation is within this of its last target time (observation stamps
#: fall on the sim step grid, not exactly on k * 0.1).
PREFIX_END_TOLERANCE_S = 0.01
#: A chunk entry contributes to a target time only if its own target time is this close (a quarter of a step) to it.
ENSEMBLE_GRID_TOLERANCE_S = 0.025
DEFAULT_ENSEMBLING_M = 0.01
_JOINTS = 6


@dataclass(frozen=True)
class ExecutionMode:
    source: str                         # "bundle": the frozen values; "cli": a run-time override
    scheme: str                         # "prefix" or "ensemble"
    execution_prefix: int               # actions applied per inference (1 for the ensemble scheme)
    chunk_size: int | None
    ensemble_m: float | None = None

    @property
    def ensembling(self) -> bool:
        return self.scheme == "ensemble"

    @property
    def open_loop(self) -> bool:
        """Whether a submitted prefix is run to its end before the next inference (only for an override above 1)."""

        return self.source == "cli" and self.scheme == "prefix" and self.execution_prefix > 1

    @property
    def runner_prefix(self):
        """The prefix the policy runner must be built with: None keeps the bundle's own value."""

        return None if self.source == "bundle" else self.execution_prefix

    def document(self) -> dict:
        return {"source": self.source, "scheme": self.scheme, "execution_prefix": self.execution_prefix,
                "chunk_size": self.chunk_size, "temporal_ensembling_m": self.ensemble_m, "open_loop": self.open_loop}


def default_mode(execution_prefix, chunk_size=None) -> ExecutionMode:
    return ExecutionMode("bundle", "prefix", execution_prefix, chunk_size)


def resolve_execution(bundle_action: dict, *, prefix=None, ensembling=None) -> ExecutionMode:
    """The effective mode of a run from the bundle's frozen `action` block and the optional overrides; refuses invalid ones."""

    chunk = bundle_action["chunk_size"]
    if prefix is not None and ensembling is not None:
        raise ValueError("EXECUTION_MODE_CONFLICT: --execution-prefix and --temporal-ensembling are exclusive")
    if ensembling is not None:
        if isinstance(ensembling, bool) or not isinstance(ensembling, (int, float)) or not math.isfinite(ensembling) \
                or ensembling < 0:
            raise ValueError("EXECUTION_ENSEMBLING_INVALID: the weight decay must be a finite number >= 0")
        if chunk < 2:
            raise ValueError("EXECUTION_ENSEMBLING_CHUNK_TOO_SHORT: ensembling needs a chunk of at least 2 steps")
        return ExecutionMode("cli", "ensemble", 1, chunk, float(ensembling))
    if prefix is not None:
        if type(prefix) is not int or prefix < 1:
            raise ValueError("EXECUTION_PREFIX_INVALID: the prefix must be an integer >= 1")
        if prefix > chunk:
            raise ValueError(f"EXECUTION_PREFIX_EXCEEDS_CHUNK: prefix {prefix} > chunk_size {chunk}")
        return ExecutionMode("cli", "prefix", prefix, chunk)
    return default_mode(bundle_action["execution_prefix"], chunk)


def _rows(chunk):
    if not isinstance(chunk, (list, tuple)) or not chunk:
        raise ValueError("ENSEMBLE_CHUNK_INVALID")
    rows = []
    for row in chunk:
        if not isinstance(row, (list, tuple)) or len(row) != _JOINTS:
            raise ValueError("ENSEMBLE_CHUNK_INVALID")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in row):
            raise ValueError("ENSEMBLE_CHUNK_INVALID")
        rows.append(tuple(float(v) for v in row))
    return tuple(rows)


class ChunkEnsembler:
    """Keeps the chunks of one episode and ensembles their predictions for a target time (see the module doc)."""

    def __init__(self, m: float, chunk_size: int) -> None:
        self.m, self.chunk_size = float(m), chunk_size
        self._chunks = []               # (observed_s, rows), oldest first

    def add(self, observed_s: float, chunk) -> None:
        rows = _rows(chunk)
        self._chunks.append((float(observed_s), rows))
        self._chunks.sort(key=lambda item: item[0])
        newest = self._chunks[-1][0]
        # a chunk whose last target lies before the next step of the newest observation can never contribute again
        self._chunks = [item for item in self._chunks
                        if item[0] + DT_S * len(item[1]) >= newest + DT_S - ENSEMBLE_GRID_TOLERANCE_S]

    def action_at(self, target_s: float):
        """(action, contributors) for `target_s`; contributors are oldest first with their chunk index and weight."""

        contributors = []
        for observed_s, rows in self._chunks:
            index = round((target_s - observed_s) / DT_S) - 1
            if 0 <= index < len(rows) and abs(observed_s + DT_S * (index + 1) - target_s) <= ENSEMBLE_GRID_TOLERANCE_S:
                contributors.append((observed_s, index, rows[index]))
        if not contributors:
            raise ValueError("ENSEMBLE_EMPTY")
        weights = [math.exp(-self.m * rank) for rank in range(len(contributors))]
        total = sum(weights)
        action = tuple(sum(w * item[2][joint] for w, item in zip(weights, contributors)) / total for joint in range(_JOINTS))
        return action, [{"observed_s": item[0], "index": item[1], "weight": w} for w, item in zip(weights, contributors)]
