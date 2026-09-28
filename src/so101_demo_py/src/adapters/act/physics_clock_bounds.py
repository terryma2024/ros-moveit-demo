"""Frozen physics-clock bounds for the ACT evidence chain.

The values below are derived from retained measurements, not from YAML defaults.
They are the *ingestion and health* bounds for `PhysicsClockHistory`; they are
not yet wired into `PickPlaceRosEvidence`, and no goal, permit or sample may be
authorized merely because these bounds are satisfied. `evidence_ready` must also
hold, and the production owner must poll `check_health()` faster than
`MAX_SILENCE_S`.

Derivation (observed maxima, margin rule `ceil_50ms(multiple x max)`):

- source step gap: EXP-556 three isolated no-goal sessions, binding epoch-one
  maximum inter-step source begin gap 2,536,550 ns; epoch-zero context including
  startup 2,898,716 ns. The frozen 6 ms is a heuristic *rejection threshold* for
  a stalled loop and is explicitly NOT reused as a silence, age or first-chunk
  bound (handoff 2026-09-28, item 2).
- age: EXP-559 in-process sessions, maximum age of the oldest sample in a chunk
  at the moment the history validates it, 151,782,691 ns (age at callback entry
  127.8 ms plus the adapter's pre-validation work). 2x = 303,565,382 ns -> 0.35 s.
- silence: EXP-559, maximum chunk inter-arrival while the source was running,
  194,483,664 ns. 2x = 388,967,328 ns -> 0.45 s (also covers the 57 ms worst
  watchdog poll slip).
- first chunk: EXP-559, maximum `arm()` to first positive-epoch chunk,
  128,046,778 ns (in-process resume accepted in <= 0.23 ms; the remaining
  ~120 ms is chunk batching plus transport). 3x = 384,140,334 ns -> 0.40 s,
  which also covers an owner-side arm-to-resume delay of up to ~280 ms.

The process-launch-inflated EXP-558 intervals (1.76-3.70 s) are excluded on
purpose; they measured the harness, not the production path.
"""

from __future__ import annotations

from .physics_clock_history import PhysicsClockHistory


SOURCE_STEP_GAP_NS = 6_000_000
MAX_AGE_S = 0.35
MAX_SILENCE_S = 0.45
FIRST_CHUNK_TIMEOUT_S = 0.40

# Observed maxima these bounds are derived from, kept as code so a regression in
# either the measurement record or the margin rule is visible in one place.
OBSERVED_SOURCE_GAP_NS = 2_536_550
OBSERVED_SOURCE_GAP_CONTEXT_NS = 2_898_716
OBSERVED_AGE_AT_VALIDATION_NS = 151_782_691
OBSERVED_CHUNK_INTER_ARRIVAL_NS = 194_483_664
OBSERVED_FIRST_CHUNK_NS = 128_046_778
OBSERVED_WATCHDOG_POLL_MAX_NS = 56_701_484

PROVENANCE = {
    "source_step_gap": "EXP-556 / CP-581, three isolated no-goal sessions",
    "age_and_silence_and_first_chunk": "EXP-559 / CP-584, three in-process sessions",
}


def history_config(*, session_id, nq, nv, clock_ns):
    """Build the frozen history configuration; no authority is implied."""

    return PhysicsClockHistory(
        session_id, nq=nq, nv=nv, max_age_s=MAX_AGE_S,
        max_source_step_gap_ns=SOURCE_STEP_GAP_NS,
        max_silence_s=MAX_SILENCE_S,
        first_chunk_timeout_s=FIRST_CHUNK_TIMEOUT_S,
        clock_ns=clock_ns)
