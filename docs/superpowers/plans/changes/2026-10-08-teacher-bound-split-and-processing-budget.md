# The Teacher keeps its 240 s bound; the processor works inside the time left on the lease

Date: 2026-10-08

Trigger: the independent review of the P3 amendment (`writer-artifacts/p3-amendment-review.md`, FAIL, blocking items 1 and 2).

1. `executing_hard_timeout_s` is not only the Coordinator's stage bound. `parallel_ros_runtime.execute_result` waits for the Teacher child until it; `worker._arm_teacher_deadline` arms `TEACHER_EXECUTION_DEADLINE` at the Teacher window plus it; the perception broker's RPC deadline and the pose-receive wait use it too. The ACT-offline file (`2026-10-08-act-runtime-stage-bounds-for-offline-processing`) raised it from 240 s to 1500 s, so a hung Teacher would have been detected six times later. That is a relaxation of the Teacher's own protection that the change doc did not state.
2. `_finish_collection` (the offline processing, up to about 20 minutes) ran inside `execute_expert`, inside `worker._teacher_boundary`, so `_teacher_child_running` stayed true and the Teacher deadline guard stayed armed during the processing. The processor's wait was a fixed 1200 s, not derived from the lease; a slow but legal Teacher plus the processing could cross the lease deadline and the Teacher's PASS would die at seal with `RESULT_AFTER_LEASE_DEADLINE`.

Options considered:

- A. Record the relaxation as an explicit Teacher-protection change and ask the user. Rejected: nothing requires the Teacher bound to move.
- B. Give the Teacher bound its own frozen value (a constant, `TEACHER_EXECUTION_BOUND_S` = 240 s) that no stage bound can raise, and raise only the stage and lease bounds. Taken. (A first attempt added an optional `teacher_execution_timeout_s` key to the version-three schema; it changed the closed v3 field list that the v4 work froze, and two existing contract tests refused it. The constant needs no schema change.)
- C. For the processing: cap the wait by the time left on the lease, close the Teacher window when the Teacher exits. Taken.

Recommended options taken under CP-3394 (and the coordinator's rework instruction, CP-3457).

## What changed

- `config/mujoco/parallel_batch_v3_act_offline.yaml` keeps its two changed lines (`executing_hard_timeout_s: 1500.0`, `lease_duration_s: 1500.0`); the schema is unchanged.
- `contracts.TEACHER_EXECUTION_BOUND_S = 240.0` and `contracts.teacher_execution_bound_s(config)` = `min(config.executing_hard_timeout_s, 240.0)` (180 s when the config has none). Every configuration that keeps the original coupling gives what it gave before, a smaller bound is honoured, and the ACT file gives 240 s. Its consumers use it: `ParallelRosRuntimePorts.execute_result`, `ParallelWorker._arm_teacher_deadline`, the two perception-broker RPC deadlines and the broker request `deadline_s` in `mujoco_parallel_batch.py`, and the pose-receive wait.
- The Worker binds a callback into the runtime (`bind_teacher_exit`) at `_teacher_boundary` entry; `ParallelWorkerRuntime.execute_expert` calls it right after the Teacher's completion receipt, before terminal capture and `_finish_collection`. It closes the Teacher-child window and stops the deadline guard. The window itself (which protects a Teacher against a lost Coordinator) stays until the result is sealed locally.
- `OfflineCollection.finish(deadline_s=lease_deadline)`: after the bag is closed, the processor's wait is `min(1200 s, deadline - now - SEAL_MARGIN_S)`. Less than `MIN_PROCESSING_S` (60 s) left: the processor is not started (`OFFLINE_PROCESSOR_NO_TIME_LEFT`). The cap is reached: the processor is terminated (`OFFLINE_PROCESSOR_TIMEOUT: <budget>s`). Either way the data is INVALID and the Teacher's result is sealed as it was.

Why `SEAL_MARGIN_S` = 60 s: after the processor ended or was terminated the Worker still needs its 10 s termination grace (cap hit), the seal (the memo path measured under 2 s), the `begin_finalizing` acknowledgement (`result_ack_timeout_s`, 10 s) and one heartbeat round trip (5 s): about 27 s. 60 s is 2.2 times that. (An earlier version of this paragraph said "six times the sum of the two acknledged bounds"; that arithmetic was wrong and is replaced.) Why `MIN_PROCESSING_S` = 60 s: the scan alone takes about 15 s and the replay needs a start-up; a processor given less cannot produce a verdict.

Budget arithmetic (illustrative, not a guarantee): the stage is 1500 s from the EXECUTING transition; the Teacher takes at most 240 s, the bag close at most 20 s, the processor at most 1200 s. Time spent in EXECUTING before the Teacher boundary (perception, pose) is absorbed because the processor's budget is read from the live lease when processing starts, not computed from these figures. The RECORDING wait (`ready_timeout_s` + 2 s) is in INITIALIZING.

## Tests (`test_p3_rework.py`)

- The ACT file has stage and lease bounds 1500 s and a Teacher bound of 240 s, differs from the original in exactly those two fields, and the v3 dataclass has no new field; the helper never exceeds 240 s and honours a smaller one; the floors still refuse 239 s and 299 s.
- A Teacher child running past 240 s is waited for no longer than 240 s under the ACT config (`execute_result`, virtual clock: it gives up at 340 s for a 100 s start, not at 1600 s). The Worker's deadline guard still fires at exactly 240 s under the ACT config (no cancel at 239 s, `TEACHER_EXECUTION_DEADLINE` at 240 s).
- The v4 to v6 pins (240 s, 300 s) are unchanged and the closed v3 field list still equals the dataclass.
- The Teacher window is closed (and the guard stopped) when the runtime reports the exit, before the data work; far past any Teacher bound nothing is cancelled during processing; the order inside `execute_expert` is receipt, exit callback, collection.
- The wait is the time left minus the margin when that is shorter than the cap, the fixed cap otherwise; not started with less than 120 s left; started with just enough; the Teacher PASS is sealed (real store, exit code 3) when the data is INVALID for either reason; the runtime passes the lease deadline.

RED: the same file imported against the pre-rework source (`scratch/p3r-red-base`) fails at collection (`ImportError: MIN_PROCESSING_S`), `writer-artifacts/p3r-red.out`.

Rollback: `writer-artifacts/p3r-base.tar.gz` (sha256 beside it) holds `contracts.py`, `worker.py`, `parallel_ros_runtime.py`, `mujoco_parallel_batch.py`, `parallel_worker_runtime.py`, `orchestration.py`, the yaml and the docs as they were before this change.

Ledger CP: CP-3457.

## Rework (CP-3459, re-review R1 and R2)

- R1: VALID data now requires the QC memo to cover the report and the files (`OFFLINE_QC_MEMO_NOT_VALID` otherwise). The earlier text "would be INVALID by lease" was wrong: without the memo the store recomputed the QC in full (about 290 s) after the budget was spent and the seal failed with `RESULT_AFTER_LEASE_DEADLINE`, losing the Teacher's result. Test: a missing or stale memo gives INVALID data and the real store seals the Teacher PASS without recomputing.
- R2: the exit callback fires only when the Teacher child really exited (`ExecutionCompletionReceipt.teacher_child_exited`). If the 240 s wait gave up with the child alive, `cancel_motion` stops it first (the Teacher-deadline revocation's path) and only then the window is closed; if it cannot be stopped the window and its guard stay open and no data work runs. Tests for exited, timed out and stopped, timed out and not stoppable, and the receipt flag.
