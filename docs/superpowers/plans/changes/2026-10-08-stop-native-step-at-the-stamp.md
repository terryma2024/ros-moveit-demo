# The stop's native step is the last step at or before the stop's stamp

Date: 2026-10-08

Trigger: the diagnostic run of bag 429dbf50 (colours ignored) passed the engine but the fresh-process QC ended `EPISODE_PHYSICAL_READBACK_INVALID`. Walking the exception chain (`p2d_qc_debug.py`) showed the wrapper hides the real cause: `verify_native_collection_events` raised `NATIVE_QC_STOP_NATIVE_STALE`. It has nothing to do with scenes or colours.

## Cause (OBSERVED on the sealed episode)

`episode_qc` took the last native step that finished before the stop receipt (`clock_interval_end_monotonic_ns <= stop.begin_monotonic_ns`) and required `0 <= stop_sim - step_sim <= 100 ms`. In the bag: the stop receipt read the simulation clock as 116.546 s; step 55981 (116.548 s) had finished 46 us before the receipt. The Teacher's stamp is a received `/clock` value, so physics can be one or two steps ahead of it at the moment the stamp is taken (the delivery lag); step 55981 therefore gave `stop_sim - step_sim = -2 ms` and the rule called the evidence stale. Nothing is stale and nothing is missing: the steps run continuously through the stop (751 .. 56250, no gap).

It is independent of the colour question and would hit a production bag whenever the stamp lands in the lag window (a few percent to ~20 % of runs by the step/lag ratio; earlier bags passed by luck).

## Rule

`stop_native_step(raw_steps, stop_clock)`: the stop's native step is the last step that finished before the receipt (monotonic, exact, unchanged) AND whose simulation time is not later than the stop's stamp; it must lie within 100 ms of the stamp (unchanged). In the bag that is step 55980 (116.546 s, the stamp itself). No tolerance is added; the selection got one more exact condition. The stop-velocity check (`NATIVE_QC_STOP_NATIVE_MOVING`) runs on that step. `NATIVE_QC_STOP_NATIVE_REQUIRED` when no step satisfies both.

Where: `src/act/episode_qc.py` (`stop_native_step`, used by `verify_native_collection_events`).

## Test

`test_b2_collection_v2.py::test_a_step_finished_before_the_stop_receipt_but_ahead_of_its_sim_stamp_is_not_the_stops_step`, with the real numbers of the bag (55979..55982): the stop's step is 55980; none at or before the stamp: REQUIRED; 246 ms old: STALE. RED first (the helper did not exist; the same input raised STALE inline, observed on the sealed episode).

Rollback: `writer-artifacts/p2e-episode_qc-base.py` (`episode_qc.py` as it was before this change, reconstructed by reverting the helper; sha256 beside it).

Ledger CP: CP-3449 (follow-up).
