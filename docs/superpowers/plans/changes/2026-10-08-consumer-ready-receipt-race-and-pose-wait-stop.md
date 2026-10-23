# The READY receipt race that failed the live pilot, and the pose wait that ignored a stop

Date: 2026-10-08

Trigger: live pilot on freeze `271xMMUN` (run `nonhead-first-episode-4eb73d48-...`) ended rc 1 with `SupervisorError OWNED_GROUP_SURVIVORS: worker`, no `sealed/raw`, no dynamic manifest. Worker result: `point_initial_gate` failed with `dynamic consumer subscription is not ready`. Not caused by the Teacher clock changes, the single `normal_stop` or the camera plugin (the simulation kept running at 500 Hz the whole time and `/clock` advanced).

## 1. The worker read the Teacher's READY receipt while it was being written

- Evidence: `consumer-ready.json` carries `ready_monotonic_s = 904408.480`; the worker's `CANCEL_REQUESTED` revocation event is at monotonic 904408.484, 4 ms later, and nothing else changed in between. The receipt is correct (434 bytes, mode 0600, identity and schema match what `_consumer_ready_fence` expects).
- Cause: `_write_consumer_ready_receipt` created the final file with `O_EXCL`, wrote it and fsynced it. The worker polls that path every 20 ms; a read between the create and the end of the write sees an empty or cut-off file. `_consumer_ready_fence` answered `DYNAMIC_READY_RECEIPT_JSON`, `consumer_ready` turned any exception into `False`, and the point gate failed for good. The window is the length of the fsync, which is long while the simulation, the raw recorder and the live Recorder write at full rate. Earlier pilots passed by luck.
- Rule (Teacher, `ros/dynamic_runtime.py`): the receipt is written to a private temporary name, fsynced, then hard-linked to the final name (still exclusive: `FileExistsError` if it exists) and the temporary name is removed. The final name never shows partial content.
- Rule (worker, `runtime/parallel_ros_runtime.py::_consumer_ready_fence`): an empty file, or a one-line receipt without its final newline, means "not ready yet" (`None`, the loop polls again within its 20 s deadline). A complete file with a wrong identity or schema still fails closed.
- Tests: `test_p2_consumer_ready_race.py` (never visible before complete, still exclusive, empty and partial mean not yet, complete accepted, foreign fails closed).

## 2. The Teacher's pose wait did not obey a stop request

- Evidence: after the gate failure the worker sent its stop; the Teacher sat in `cup_pose_source.get_one` (240 s timeout) and the owner's bounded shutdown found it alive (`dynamic-consumer ... timed out after 5.0 seconds`), which became `OWNED_GROUP_SURVIVORS`.
- Cause: the signal handlers only set `StopFlags`; the wait loop (`acquire_one`) never looked at them.
- Rule: `acquire_one(..., stop_check=None)` calls `stop_check()` on every pass; `RosCupPoseSource.get_one` passes `self.stop_check`; `run_dynamic_execute` sets `source.stop_check = stop_flags.raise_if_stopped`. No control change: the wait only ends sooner when the owner asked to stop.
- Tests: `test_the_pose_wait_obeys_the_stop_check`, `test_the_ros_cup_pose_source_wait_reads_the_runtimes_stop_check`, `test_the_dynamic_runtime_hands_its_stop_flags_to_the_pose_source` (without the rule the second one waits for the full timeout).

## Observed, not changed

The live Recorder was `INVALID` (`INPUT_TIMESTAMP_FUTURE`, `PHYSICS_RAW_PENDING_OVERFLOW` after chunk receipts 100 to 510 ms late) during its bounded wait before the Teacher started; the Recorder is being retired and the raw bag is the data path. The Teacher's start was delayed about 12 s by that wait, as in earlier pilots.

Contract impact: none. The receipt content and its path are unchanged; only how the file appears.

Rollback: `writer-artifacts/p2-ready-base.tar.gz` (sha256 beside it).

Ledger CP: CP-3441 (live pilot 271xMMUN).
