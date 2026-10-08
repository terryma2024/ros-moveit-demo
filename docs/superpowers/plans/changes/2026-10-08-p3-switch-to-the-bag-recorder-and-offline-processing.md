# P3: the run path records a bag and builds the episode offline

Date: 2026-10-08

Trigger: the P2 milestone (CP-3455). The offline processor turned the recorded bag of run 147cb073 into a VALID episode with a fresh-process QC PASS (`scratch/p2run-prod3-nHsKzqZd`, 580 s wall for 103.6 s of run). The live Recorder never produced one in 17 Teacher PASSes. Plan section 5 P3 and the user's standing decision CP-3428 call for the switch.

Options considered:

1. Keep the live Recorder beside the bag and compare. Rejected by CP-3428: every live L2 failed on the Recorder's own start races, receiver stalls and cascades.
2. Switch the run path; keep the live Recorder modules until a separate cleanup step. Taken.
3. Switch and delete the live machinery in one step. Rejected: the offline processor reuses `RosRecorderSources`, `RecorderEngine`, `RecorderDataSide` and the spool modules through subclassing; what is live-only inside them has to be separated by coverage first (see the cleanup inventory).

Recommended option taken under CP-3394: option 2.

## What changed

- `act/offline/orchestration.py` (new): `OfflineCollection`, one attempt's data lifecycle.
  - Before the Teacher: start `PilotRecording` (the `ros2 bag record` owner of P1) and wait the frozen `ready_timeout_s` for RECORDING. The Teacher starts whatever happened; a recorder that is not ready makes the data INVALID.
  - After the Teacher: close the bag, then run `act_offline_episode` as a process of the Worker's group with `--out <attempt working dir>`, `--qc-output <working>/qc-report.json`, the Worker's current lease, the run scope, the frozen inputs and the Teacher manifest. The episode lands in `<working>/episode`, the result facts in `<working>/recorder-result.json`, the processor report in `<working>/offline-processor-report.json`. Those are the locations the ResultStore, the Coordinator's verifier and the readback already use.
  - The data verdict is the processor's: exit code 0, report verdict VALID, result document VALID with its seal, fresh-process QC PASS and the QC file present. A QC verdict other than PASS is INVALID data (it used to be a recorded FAIL on VALID data). Exit 3 is INVALID with the processor's reasons; any other exit is `OFFLINE_PROCESSOR_FAILED`; a processor that outlives 1200 s is terminated (`OFFLINE_PROCESSOR_TIMEOUT`). Nothing here raises into the Teacher's result.
  - A data verdict already made (terminal capture failed) closes the bag and skips the processor.
- `ParallelWorkerRuntime`: `_start_recorder_first`, `_recorder_teacher_started`, `_finish_collection` and `_retire_recorder` drive `OfflineCollection`; the independent `_run_fresh_process_qc` and `recorder_launch` are gone. The Teacher's argv is unchanged (only `--final-stop-proof` with collection on).
- `CollectionOptions`: `raw_pilot` is now `enabled`. `--raw-pilot on` is accepted and does nothing; `--raw-pilot off` with `--collection on` is refused (`COLLECTION_RAW_RECORDER_IS_THE_ONLY_DATA_PATH`). `--collection off` starts no recorder and runs no processor (data DISABLED).
- `act_offline_episode`: new `--qc-output`; an infrastructure defect (an unwritable output directory) is exit code 4 with the traceback on stderr, not an uncaught exception (exit 1).
- Tooling, new revisions only: `run-qualified-live-20261008-r9.zsh` (no `--raw-pilot`), `watch-qualified-runtime-20261008-r2.py` and `capture-qualified-runtime-20261008-r2.py` (the data-side process of the run is `so101_demo.act.offline.raw_recorder`), `tooling/live-r6.zsh`.

## Faults (diagnostic mode, every output beneath `<run>/fault-sandbox/`)

| fault | what it is now | processed? | verdict |
| --- | --- | --- | --- |
| `recorder_absent` | no bag is recorded | no | INVALID `RECORDER_ABSENT` |
| `recorder_late` | the bag starts 5 s after the Teacher's setup evidence appeared (its first command follows within about 2 s) | no | INVALID `RECORDER_STARTED_AFTER_TEACHER` |
| `queue_overflow` | 40 consecutive `/so101/simulation/physics_step_chunks` messages are missing from a sandbox copy of the bag | yes | INVALID (`OFFLINE_SOURCE_GAP`, `CAPTURE_ACQUISITION_OVERFLOW`, `PHYSICS_RAW_CONTINUITY_INVALID`) |
| `source_gap` | 60 consecutive `/arm_controller/controller_state` messages are missing from a sandbox copy | yes | INVALID (`OFFLINE_SOURCE_GAP`, `COLLECTION_REFERENCE_EXACT_PUBLICATION_UNAVAILABLE`) |
| `output_write_failure` | the processor's output directory is read-only | yes | INVALID `OFFLINE_PROCESSOR_FAILED: rc=4` |

Each gives Teacher PASS, data INVALID, QC NOT_RUN, not exportable, and the run's exit code 3. The two bag faults and the read-only output were run on the real bag of 147cb073 (`scratch/p3fault-*`): source_gap rc 3 in 148 s, queue_overflow rc 3 in 141 s, read-only output rc 1 before the exit-code fix and rc 4 after it.

## Contract impact

- The data side no longer has receiver threads, spoolers, a start gate, deferred events or a CAPTURING wait on the run path. The policy file `episode_recorder_v1` keeps its frozen keys; only `ready_timeout_s` is used by the run path.
- The result facts the ResultStore consumes are unchanged in shape. The episode's audit lease is the Worker's EXECUTING lease at the time processing starts (see the stage-bounds change doc for why it equals the lease at seal time).
- `recorder-orchestration.json` now records `mode: RAW_BAG_OFFLINE`, the bag recorder's facts and the processor's return code, report summary and wall time.

## Tests

`test_p3_offline_switch.py` (collection request, stage-bound floors, bag fault helper on a real bag, the lifecycle with fakes, the five faults, the Worker runtime, the sealed result and exit code 3 per fault, `execute_expert`), `test_p3_collection_chain.py` (the option crosses the specification into the Worker runtime). 19 tests of the retired Recorder orchestration and 3 of the retired switch were removed with a TSV: `writer-artifacts/p3-cleanup-tests-removed.tsv`; each has a named replacement. No skip, no xfail.

Rollback: `writer-artifacts/p3-base.tar.gz`, `p3-base3.tar.gz` (sha256 beside them) and `p3-test_act_collection_orchestration.py.base`; the new files are removable.

Ledger CP: CP-3456.

## Rework (CP-3457)

- Processing budget and the Teacher window: `2026-10-08-teacher-bound-split-and-processing-budget`.
- The scan refuses a `normal_stop` after the `terminal` event (`OFFLINE_NORMAL_STOP_AFTER_TERMINAL`) instead of taking the last stop; `timeline()` counts them separately and never lets one become the episode's stop.
- The clock-map limit is 2 ms (it was 10 ms). The residual of the two real bags is 0.9 us and 2.8 us; the anchors are read back to back (+-1 us measured) and the tightest rule the map feeds is a few milliseconds. 2 ms is a factor of 700 above the observation.
- The recorder's reported transport loss is parsed from its log into `record-stats.json` (`transport_lost`) and appears in `recorder-orchestration.json`. It is a recorded fact, not yet a verdict: the real bag 147cb073 reported 6 lost messages and was VALID with QC PASS, every topic that carries a sequence or a grid was gap-free, so the 6 were on topics without one (or outside the window). Making any loss fatal would have made the only good bag INVALID. See the amendment, section 6.
- `recorder_late` records its evidence: when the Teacher's setup evidence was seen, the delay, when the start was requested and the late bag's first stamp. On the real bag a late copy that starts 5 s after the setup evidence (and so after the Teacher's first command at 867.243 s; it starts at 870.547 s) was processed: see the amendment, section 5.
- The read-only output on the real bag now exits 4 (`scratch/p3fault-ro2-*`, `writer-artifacts/p3r-ro-rerun.out`); the first run (rc 1) preceded the exit-code fix.
