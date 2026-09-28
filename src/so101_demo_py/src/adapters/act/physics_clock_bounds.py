"""Frozen physics-clock bounds for the ACT evidence chain.

The values below are derived from retained measurements, not from YAML defaults.
They are the *ingestion and health* bounds for `PhysicsClockHistory`; they are
not yet wired into `PickPlaceRosEvidence`, and no goal, permit or sample may be
authorized merely because these bounds are satisfied. `evidence_ready` must also
hold, and the production owner must poll `check_health()` faster than
`MAX_SILENCE_S`.

Derivation (window-scoped observed maxima, margin rule `ceil_50ms(multiple x max)`):

- source step gap: EXP-556 three isolated no-goal sessions, binding epoch-one
  maximum inter-step source begin gap 2,536,550 ns (epoch-zero context including
  startup 2,898,716 ns). The frozen 6 ms is a heuristic *rejection threshold* for
  a stalled loop and is explicitly NOT reused as a silence, age or first-chunk
  bound (handoff 2026-09-28, item 2).
- silence: population is the maximum chunk inter-arrival **inside a running
  measurement window**, 122,997,815 ns (EXP-559 run-3; EXP-560 maxima are
  108-110 ms). 2x = 246,000,000 ns -> 250 ms, frozen at 0.30 s for second-order
  scheduling effects. Note the 194.5 ms figure seen earlier crosses the reset and
  therefore belongs to the first-chunk population, not to silence. Watchdog poll
  slip (max 56.7 ms) extends *detection* latency and is not absorbed by this bound.
- age: population is the window-scoped validation-time envelope - the largest
  in-window age at callback entry (127,833,869 ns) plus the largest in-window
  callback cost (26,894,568 ns) = 154,728,437 ns, a conservative cross-chunk
  envelope rather than one observed sample. 2x = 309,440,000 ns -> 0.35 s.
  EXP-560 after the copy removal measures an envelope of 133.7 ms.
- first chunk: maximum `arm()` to first positive-epoch chunk 128,046,778 ns
  (in-process resume accepted in <= 0.23 ms; the remaining ~120 ms is chunk
  batching plus transport). 3x = 384,140,334 ns -> 0.40 s. The owner-side
  arm-to-resume allowance implied by this margin is **not yet qualified**; the
  wiring experiment must measure the real owner path under representative load.

The process-launch-inflated EXP-558 intervals (1.76-3.70 s) are excluded on
purpose; they measured the harness, not the production path.
"""

from __future__ import annotations

from .physics_clock_history import PhysicsClockHistory


SOURCE_STEP_GAP_NS = 6_000_000
MAX_AGE_S = 0.35
MAX_SILENCE_S = 0.30
FIRST_CHUNK_TIMEOUT_S = 0.40

# Observed maxima these bounds are derived from, kept as code so a regression in
# either the measurement record or the margin rule is visible in one place.
OBSERVED_SOURCE_GAP_NS = 2_536_550
OBSERVED_SOURCE_GAP_CONTEXT_NS = 2_898_716
# Exact integers, as independently decoded in the 2026-09-28 local Gate 5 review.
OBSERVED_AGE_AT_CALLBACK_ENTRY_NS = 127_833_869
OBSERVED_CALLBACK_COST_NS = 26_894_568
OBSERVED_AGE_AT_VALIDATION_ENVELOPE_NS = 154_728_437
OBSERVED_IN_WINDOW_CHUNK_GAP_NS = 122_997_815
OBSERVED_RESET_CROSSING_GAP_NS = 194_483_664
OBSERVED_FIRST_CHUNK_NS = 128_046_778
OBSERVED_FIRST_CHUNK_FROM_ARM_BEGIN_NS = 128_110_036
OBSERVED_WATCHDOG_POLL_MAX_NS = 56_701_484
OBSERVED_WATCHDOG_POLL_MAX_AFTER_COPY_FIX_NS = 46_518_291
OBSERVED_CALLBACK_COST_P50_BEFORE_COPY_FIX_NS = 15_530_000
OBSERVED_CALLBACK_COST_P50_AFTER_COPY_FIX_NS = 7_810_000
OBSERVED_STEP_AT_P50_BEFORE_COPY_FIX_NS = 14_400_000
OBSERVED_STEP_AT_P50_AFTER_COPY_FIX_NS = 195_000

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
