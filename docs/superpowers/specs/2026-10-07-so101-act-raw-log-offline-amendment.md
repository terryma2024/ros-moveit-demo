# SO-101 ACT: raw-log recording and offline episode processing (design amendment)

- Date: 2026-10-07 (amended 2026-10-08, P3; reworked after the independent review, CP-3457)
- Status: reworked draft for a second independent review. Amends `2026-10-05-so101-teacher-act-decoupling-amendment.md` and the data-side rounds of `2026-10-06-so101-teacher-moveit-simplification-amendment.md`.
- Plan: `docs/superpowers/plans/2026-10-07-so101-act-raw-log-offline-pipeline-implementation.md`, section 5 P3.
- Decisions: CP-3428 (record raw data, build the episode offline), CP-3394 (take the recommended option at decision points), CP-3455 (P2 milestone), CP-3456 (this switch), CP-3457 (rework after review: Teacher bound, processing budget, memo binding).
- Change documents (one per decision): `docs/superpowers/plans/changes/2026-10-08-*.md`; the ones this amendment rests on are listed in section 9.

## 1. Why this amendment exists

The Teacher (MoveIt and the joint trajectory controller, official-aligned model) passed 17 consecutive live runs. The data side did not. The live Recorder had to receive about 300 000 messages in real time, keep order across ten topics, and decide per 10 Hz row whether its sources were fresh enough, all in a Python process that shares a machine with a physics server and a planner. Every live L2 ended with the Teacher passing and the data INVALID, and each fix exposed the next race: the start against the Teacher's first command, receiver stalls, alignment sources not yet arrived, one latched failure cascading into others.

The decision of CP-3428 is to stop judging the data while the run is in progress. During the run, one process records every needed topic into a rosbag2 MCAP file and does nothing else. After the Teacher ended, a deterministic offline processor reads the file and builds the sealed episode with the same rules, a fresh-process QC checks it, and the existing ResultStore and Coordinator commit it.

The first P2 run of the production processor on a real bag produced a VALID episode with QC PASS (run 147cb073, freeze lHwgvaIW): 856 records, 51 300 native physics steps, 8 759 audit events, 580 s of processing for a 103.6 s episode.

## 2. Architecture

### 2.1 Processes and time

```
 Worker process group (one per attempt)                                        after the Teacher
 ------------------------------------------------------------------------------------------------------------------
 reset ─► start raw recorder ─► wait RECORDING (bounded) ─► start Teacher ─► ... ─► terminal ─► close bag ─► processor
          (ros2 bag record,      12 s bound; the       (unchanged)          event      (SIGINT,     (own process,
           scene-read sidecar)   Teacher starts anyway)                                          metadata)    fresh QC inside)
                                                                                                              │
                          ResultStore.seal ◄─ memo-trusting gate ◄──── episode + qc-report.json + memo ◄──────┘
                                   │
                          begin_finalizing ─► Coordinator commit (memo-trusting gate) ─► journal, index
                                                                                         │
                                                         readback tools (full recomputation, no memo) ◄┘
```

Rules that do not change (and are enforced, see 4.2): the Teacher never waits for, reads from or is stopped by anything on the data side after its own start; every defect on the data side is a verdict on the data (INVALID) and never an input to the Teacher; the Teacher result (`teacher_execution_status`, `teacher_task_result`, attempt status) is sealed exactly as the Teacher produced it.

### 2.2 The record-only process

`act/offline/raw_recorder.py`, owned by `PilotRecording`, started by the Worker after the reset and before the Teacher. It runs `ros2 bag record -s mcap` in its own process group with per-topic QoS overrides (reliable and deep for the high-rate topics), and a sidecar that calls `/get_planning_scene` at about 20 Hz and publishes each answer, with request and response clocks, on `/so101/raw/planning_scene_reads` (it also keeps a JSONL copy). It records: `/clock`, both cameras (colour and camera info), the physics chunks, `/so101/simulation/evidence`, scene state, robot contacts, `/joint_states`, the three `controller_state` topics, `/so101/teacher/events` and the scene reads.

RECORDING means a message was received on every required topic after its subscription appeared. The wait is bounded by the frozen `ready_timeout_s` (10 s) plus 2 s of start-up (`pilot.py`), 12 s in all. The Teacher's events topic has no publisher before the Teacher starts and is checked after recording. At the end the recorder is stopped with SIGINT, waits for the bag to close (`metadata.yaml` written), and writes `record-stats.json`: two clock anchors (monotonic and system time, ±1 ms), per-topic counts, `closed`, `rc`, `missing_core_topics`. rosbag2 stamps with the system clock; the processor maps bag stamps to the monotonic clock through the anchors and refuses a mapping whose residual against the scene-read pairs exceeds 2 ms (4.6).

### 2.3 The offline processor

`act/offline/processor.py`, entry point `act_offline_episode`. Inputs: the bag, the frozen inputs manifest, the run scope, the Teacher manifest, the attempt's lease, the record stats. Output (all beneath `--out`, which on the run path is the attempt's working directory): `episode/` (the sealed episode, same layout as before), `recorder-result.json`, `offline-processor-report.json`, the fresh-process QC report at `--qc-output`, and the QC memo beside it.

1. A read-only **scan** of the bag: every required topic present, metadata counts equal the counts read back, the Teacher's event sequence whole (`seq` 1..N), every `normal_stop` before the `terminal` event (the last of them is the episode's stop; one after the terminal is refused, `OFFLINE_NORMAL_STOP_AFTER_TERMINAL`), and inside the window [first command, terminal + 0.1 s] gap-free sources: the three `controller_state` topics on their 2 ms grid, physics chunks by sequence and step, world evidence by publisher sequence, cameras on the 100 ms grid with head and wrist equal. Data outside the window is never judged by the scan. The episode itself starts earlier, at `window_start` (the first unpaused world record after the worker's last pause, about 6 s before the first command, the verified reset); for [window_start, first command) the engine's and the QC's rules are authoritative, and the scan only catches problems early.
2. A **replay** that drives the engine and sources of the former live Recorder (now `OfflineEngine` and `OfflineRosSources`, cleanup step 2), synchronizer, source alignment, label construction, episode assembly, lossless writer and seal through a source interface instead of live callbacks (`OfflineRosSources`, `ReplayNode`, virtual monotonic clock, inline executor, scene reads served from the recorded sidecar). Messages are delivered at the instant their receipt is mapped to; the engine passes every 5 ms of virtual time. Nothing waits on wall time.
3. The **fresh-process QC** (`act/offline/fresh_qc.py`): a new interpreter that imports nothing from the processor and runs `episode_qc.recompute_native_qc` against the original scope, frozen inputs and Teacher manifest. A PASS also writes the memo (section 4.4).

The processor is deterministic: two runs on the same bag give identical output. Exit codes: 0 VALID and QC PASS; 3 INVALID data; 2 refused configuration; 4 infrastructure (an unwritable output directory, an unreadable bag); 5 diagnostic runs (never evidence).

### 2.4 Run-path orchestration

`act/offline/orchestration.py`, class `OfflineCollection`, created by the Worker runtime per attempt:

- `start_before_teacher`: start the raw recorder, wait for RECORDING. A recorder that cannot start or is not ready makes the data INVALID with the recorder's reason; the Teacher is started in every case.
- `finish(lease, skip_processing, deadline_s)`: close the bag (a bag that is not closed cleanly, or whose recorder exited non-zero, is INVALID), then start the processor as a process of the Worker's group and wait for it, at most `min(1200 s, lease deadline - now - 60 s)`; with less than 60 s of budget it is not started (`OFFLINE_PROCESSOR_NO_TIME_LEFT`), at the cap it is terminated (`OFFLINE_PROCESSOR_TIMEOUT`). Either way the data is INVALID and the Teacher's result is sealed as it was (section 4.2). A data verdict already made (for example a failed terminal capture) closes the bag and skips the processor.
- The attempt's `act_data_status` is the processor's verdict: VALID only if exit code 0, report verdict VALID, a result document of schema `SO101_RECORDER_RESULT_V1` with matching identity, status VALID and a seal, a fresh-process QC PASS, and the QC report file present. Otherwise INVALID with a bounded reason (`OFFLINE_PROCESSOR_INVALID: rc=3; <first reasons>`, `OFFLINE_PROCESSOR_FAILED: rc=N`, `OFFLINE_PROCESSOR_TIMEOUT`, `RAW_BAG_NOT_CLOSED_CLEANLY`, ...). A QC that does not PASS is INVALID data; there is no longer a VALID episode with a recorded QC FAIL.
- `--collection off` starts no recorder and runs no processor; the data is DISABLED and no QC is attempted.

### 2.5 The existing downstream chain

Unchanged in code and in what it verifies, except for the two gate options of section 4.4: `ActCollectionResultStore.seal` (`working` becomes `sealed`), `begin_finalizing`, the Coordinator's `commit_result` with `ActCollectionResultVerifier`, the journal and the aggregate index, `verify_coordinator_commit` and `verify_coordinator_cleanup`, `check-export` (a diagnostic-mode episode is refused for training).

## 3. The rules whose input is not the Recorder's own receipt

The pilot substitutes the bag's receipt time for the Recorder's receipt time. The authoritative table is `handoffs/.../writer-artifacts/p2-substitution.md`; the summary:

- Exact, no substitution: sim-time source age, world and chunk sequence and step continuity, the controller-state 2 ms grid and the `t + 0.1` label, event sequence, session and epoch scope, the 10 Hz grid, endpoint and normal-stop rules on sim stamps, the lossless writer and the seal.
- Receipt-time rules that use the bag receipt: world observer freshness (looser than live by the live stall lag), the world-to-scene 100 ms join, "received before request" in source alignment, physics chunk lag, camera, joint-state and controller-state receipt ordering. Nothing in the bag can inflate a receipt by a stall of the recorder.
- Rules that run on virtual time: alignment retry, `finish_budget_s`, `max_duration_s`, capture deadlines.
- Not asserted offline: lease currency (the lease fields are still bound), the episode's `working/episode` location.

**Decision (plan section 4 deviation, CP-3394): the receipt-time rules stay on the bag receipt.** Plan section 4 said to rewrite them on producer clocks at the switch. They were not rewritten. Rationale: (a) the bag receipt is the receipt of the only live observer left on the data side, a recorder that does nothing else, so what it measures is delivery to a recorder, not a stall of a Python data process; (b) the producer-clock replacement for each rule (sim time, step, the plugin's `handoff_monotonic_ns` and `publish_monotonic_ns` of CP-3411) would change what those rules mean (a delivery lag is no longer a property of the data), and every one of them was written to protect a live process that no longer exists; (c) the bag receipt is mapped to the monotonic clock with a 2 ms limit (4.6), well inside the tightest of these rules; (d) the producer clocks the data contract is built on (sim stamps, steps, sequences) are all still checked exactly. Rollback: none needed; the producer-clock rules can replace these one by one without touching the engine.

**CP-3410's backlog and receiver-lag failure rule is retired offline.** It failed the data when unprocessed spool frames exceeded a threshold or the newest received sample was behind now by more than a bound. There is no spool and no live receiver offline, so it cannot fire. What replaces it: the bag metadata count equals the count read back (`OFFLINE_BAG_READBACK_COUNT_MISMATCH`), the sequence and grid continuity of every ordered source inside the window (4.8 and the table in section 6), and the recorder's own closed-cleanly check. A late chunk is admitted as under CP-3410 (lateness is not a failure).

**Single planning-scene writer.** The scene-read bracket (CP-3440 B) and the apply-bounded bracket (CP-3449) both rely on "no Teacher apply between two reads" and so on the assumption that the Teacher is the only writer of the ACT stack's planning scene. Evidence: the ACT stack's move_group does not publish `/monitored_planning_scene` and nothing in the ACT stack subscribes to it except RViz (change document CP-3445), which the ACT stack does not run; the only code that calls `/apply_planning_scene` in an ACT run is the Teacher's setup port (`control/planning_scene/task_scene.py`) and its dynamic execution (`ros/dynamic_mujoco_execution.py`; the stack-ready probe only creates a client to see that the service exists, and the qualified-phase modules belong to other pipelines); in bag 147cb073 every change of state among the 2099 recorded scene reads (initial scene, attach at 56.886 s, detach at 97.744 s) follows one of the Teacher's 8 recorded applies by at most 20 ms. Both rules also compare the geometry of the reads on both sides, so a foreign change that stays in place is caught; one that changes and restores itself between two reads would not be. If another writer is ever added to the ACT stack these two rules must be revisited.

## 3A. Changes outside the data side (Teacher and shared producers)

The data-side switch is not the only code that changed. These changes touch the Teacher or the simulation stack the Teacher runs on. Each is in its own change document; none changes a motion, a goal, a timeout, a gripper command or a decision unless it says so. The Teacher bound itself is not changed (4.2).

| change | CP / document | scope | effect on Teacher timing and control | failure modes | evidence |
| --- | --- | --- | --- | --- | --- |
| Scene-call clock refresh and floor: `clock_refresh()` (a spin of at most 10 ms) before every ROS-clock read of a scene call, `clock_floor()` from the newest world sample; ACM diff `robot_state.is_diff = True`; the stop proof takes one instant for `begin = end`; only the final boundary `normal_stop` is published | CP-3441, `teacher-event-clocks-colour-and-single-final-stop` | the Teacher (`RosDynamicMujocoExecution`) and the setup port; every ACT run | at most 10 ms added before a scene call; event and reporting clocks and one message field change; no goal, timeout or decision | a refresh that fails is ignored (best effort, never changes the call); a stamp never older than the newest world sample | 17th and 18th live Teacher PASS (CP-3448 and the P2 pilot) |
| Atomic READY receipt (temporary name, fsync, exclusive hard link); the worker treats an empty or unterminated receipt as "not ready yet"; the pose wait obeys the stop flags | CP-3441 / CP-3443, `consumer-ready-receipt-race-and-pose-wait-stop` | the Teacher's start handshake and its pose wait; every ACT run | the receipt appears whole; the wait ends sooner when the owner asks to stop | a complete receipt with a wrong identity still fails closed | the live pilot that failed on the race, then the 17th and 18th PASS |
| Camera plugin renders on the physics thread at the exact step (sim-synchronous), stamps in whole rounded nanoseconds, and the physics step waits while the renderer is busy (60 s bound, then an error is logged) | CP-3439, `camera-sim-synchronous-rendering` | `mujoco_ros2_control_plugins` (a submodule): every stack that loads the camera plugin with a sim-time clock, not only ACT | simulation speed only: the physics waits for the renderer; the Teacher works in simulation time | a renderer that never returns stalls the physics for 60 s per wait and logs an error; real time slows | C++ tests (11 of the suite), the camera grid exact on both real bags |
| `ControlTickGate` lock-step: one controller update per physics step once a consumer attached; the physics loop does not take the next step before the consumer acknowledged the tick it is due for; `/clock` retried up to 20 ms; no catch-up burst after a render wait; a step slower than 5 ms re-anchors real-time pacing | CP-3445, `controller-tick-lockstep-and-lossless-clock` | `mujoco_ros2_control` (a submodule): every `use_sim_time` stack, not only ACT | one update per step is now guaranteed instead of usual; real time slows when a step is slow; at sim speed factors above 1 the simulation is paced by the controller update (0.1 to 0.3 ms per tick) | the gate disarms after 250 ms without an acknowledgement and the physics loop then runs free until a consumer attaches again, silently falling back to the old behaviour | C++ tests 12 + 6 + the lock-step tests; 0 missing and 0 duplicate stamps on `/clock` and the gripper and neck states in the first bag |
| `stopPublishingPlanningScene()` in `graceful_shutdown_move_group` when the launch says publishing is off; the ACT launch passes `publish_planning_scene=False` | CP-3445 / CP-3449, `act-move-group-does-not-publish-the-monitored-scene` | `so101_mujoco_support`, the ACT stack's move_group only; the other stacks keep publishing | none for control; MoveIt no longer drops the attached cup's colour | a consumer of `/monitored_planning_scene` in the ACT stack would get nothing (none exists) | the colour persists from attach to detach in bag 147cb073 (2099 reads); C++ test 3 of 3 |

Consequence for P4: the planned comparison of the Teacher's phase times between L1 and L2 to L7 cannot see any of these effects, because L1 has them too. The comparison that can is against pre-change PASS runs (for example the 12 runs before CP-3445), which the final report will include next to the L1 comparison.

## 4. Contract changes

Each is a decision under CP-3394 with its own change document and rollback. They are every deviation from plan section 4's "stays unchanged" list and every change this switch makes.

| # | change | CP | document |
| --- | --- | --- | --- |
| 1 | the data path: raw recorder, offline processor, no live Recorder on the run path; a QC verdict other than PASS is INVALID data (it was VALID data with a recorded QC FAIL) | CP-3428, CP-3456 | `p3-switch-to-the-bag-recorder-and-offline-processing` |
| 2 | stage and lease bounds raised for offline processing; the Teacher bound kept at its frozen 240 s | CP-3456, CP-3457 | `act-runtime-stage-bounds-for-offline-processing`, `teacher-bound-split-and-processing-budget` |
| 3 | the processor's wait capped by the time left on the lease; the Teacher window closed when the Teacher exits | CP-3457 | `teacher-bound-split-and-processing-budget` |
| 4 | the QC memo, bound to the content, the QC rule version and the QC code | CP-3456, CP-3457 | `fresh-qc-verification-memo` |
| 5 | the stop's native step: last step finished before the receipt and not later than the stamp | CP-3449 | `stop-native-step-at-the-stamp` |
| 6 | continuity narrowed to the label instants: arm and gripper `controller_state` gaps matter only where a label needs a frame | CP-3439 | `controller-reference-label-instant-continuity` |
| 7 | the planning-scene read bracket: a read older than the 100 ms age rule is admitted by the next read when both carry the association's geometry and no association change lies between | CP-3440 B | `planning-scene-freshness-by-bracketing` |
| 8 | the apply-bounded bracket: a row between the Teacher's successful apply and the first read after it uses the apply as its scene source | CP-3449 | `apply-bounded-scene-bracket` |
| 9 | the episode window starts after the worker's last pre-Teacher pause | CP-3440 | `offline-window-start-after-worker-pause` |
| 10 | an audited camera sequence may start at any positive integer (the bag starts mid-stream) | CP-3440 | `last-normal-stop-and-late-camera-sequence` |
| 11 | `INPUT_TIMESTAMP_FUTURE`: a message stamped ahead of the recorded `/clock` is held (topic order kept) for at most 50 ms of receipt time | CP-3439 | `offline-processor-pilot-fixes` |
| 12 | several `normal_stop` events are tolerated before the terminal event; the last is the boundary; one after it is refused | CP-3440, CP-3457 | `last-normal-stop-and-late-camera-sequence` |
| 13 | the first row waits for its association; tail physics coverage | CP-3439/3440 | `first-row-association-wait-and-tail-physics-coverage` |
| 14 | the label target is the nanosecond sum, not a microsecond rounding | CP-3439 | `offline-processor-pilot-fixes` |
| 15 | the Teacher and producer changes of section 3A | CP-3439, 3441, 3443, 3445, 3449 | the documents named there |
| 16 | the readiness handshake: RECORDING is data received, a bounded child shutdown | CP-3431 | `raw-pilot-lifecycle` |
| 17 | the clock-map residual limit tightened from 10 ms to 2 ms | CP-3457 | `p3-switch-to-the-bag-recorder-and-offline-processing` |
| 18 | VALID data requires the QC memo; a timed-out Teacher child is stopped before its window closes | CP-3459 | `qualified-role-commands-and-broker-package` |
| 19 | the broker container runs the qualified package; role commands never come from PATH | CP-3459 | `qualified-role-commands-and-broker-package` |
| 20 | the broker keeps the image's YOLO detector (hash-pinned, recorded); corrected-detector re-baselining is a gate before formal collection. **Closed by CP-3467:** the pin is removed, the broker runs the freeze's corrected detector, and rule R6 in the Worker's localizer keeps the one candidate that is the cup | CP-3460, CP-3467 | `broker-detector-pin`, `perception-rebaseline-r6-unpin` |

### 4.1 The data path

The Recorder process, its CAPTURING handshake and its result file are no longer on the run path. `CollectionOptions.raw_pilot` is derived (`enabled`); `--raw-pilot on` is a no-op and `off` with the collection on is refused. The processor's `--qc-output` and exit code 4 are new.

### 4.2 Stage bounds, the Teacher bound, and the processing budget

The version-three runtime config pins `lease_duration_s` at 300 s and `executing_hard_timeout_s` at 240 s. Processing needs about ten minutes after a two-minute Teacher. Version three now accepts these two as floors; the ACT collection binds a new file, `parallel_batch_v3_act_offline.yaml`, that sets both to 1500 s. Versions four to six keep exact pins; the original file stays valid.

`executing_hard_timeout_s` is also the Teacher's own execution bound (the wait for the Teacher child in `execute_result`, the Worker's `TEACHER_EXECUTION_DEADLINE` guard, the perception broker's RPC deadlines and the pose wait). The first version of this change raised it without saying so, which weakened the Teacher's hang detection six-fold. The Teacher bound is now its own frozen value, `TEACHER_EXECUTION_BOUND_S` = 240 s, that no stage bound can raise; its consumers read `teacher_execution_bound_s(config)` = `min(executing_hard_timeout_s, 240 s)`. No schema key was added: the closed version-three field list that the v4 work froze is unchanged.

The Teacher's window closes when the Teacher exits: the runtime calls back into the Worker right after the completion receipt, but only if the Teacher child really exited. If the 240 s wait gave up with the child alive, the runtime first stops it by the path the Teacher-deadline revocation uses (`cancel_motion`: the consumer child and the controller goal) and only then calls back; if the child cannot be stopped the window and its deadline guard stay open and no data work runs (`TEACHER_CHILD_NOT_STOPPED`; a stopped one is `TEACHER_CHILD_TIMED_OUT`, no processing either). The call-back comes before the terminal capture and before the collection is finished, so the offline processing never runs inside the Teacher's window and the deadline guard no longer applies to it. The processor's wait is capped by the lease deadline minus a 60 s seal margin. What the margin must cover after the processor ended: its 10 s termination grace (when the cap was hit), the seal (at most 2 s on the memo path), the `begin_finalizing` acknowledgement (`result_ack_timeout_s`, 10 s) and one heartbeat round trip (5 s): about 27 s in all. 60 s is 2.2 times that. With under 60 s of budget the processor is not started. The arithmetic of a whole stage is illustrative, not a guarantee: the stage is 1500 s from the EXECUTING transition; the Teacher takes at most 240 s, the bag close at most 20 s, the processor at most 1200 s; but time spent in EXECUTING before the Teacher boundary (perception, pose) is absorbed because the budget is read from the live lease at the moment processing starts, not computed from these figures. The RECORDING wait is in INITIALIZING. Equal stage and lease bounds make the lease deadline equal the stage deadline from the first renewal on, so it does not move during the stage.

The audit lease is the lease taken at `_teacher_boundary` entry (`self._current()`), which is the EXECUTING lease after the stage transition renewed it; it is the one passed to `execute_expert` and to the processor. The ResultStore compares it with the lease at seal (equal, because the deadline no longer moves), and the commit-time check finds it among the EXECUTING lease values it replays from the journal (every heartbeat is journaled as `LEASE_RENEWED`). This has not been exercised live with VALID data; `LEASE_IDENTITY_MISMATCH` at seal would name it at once.

### 4.3 Verification cost of the result chain

Recomputing the QC of one episode takes about 290 s. The chain asks for it at the Worker's seal, twice in the Coordinator's `_commit` under its state lock, and (as designed) once more in the readback. The Worker waits ten seconds for the commit acknowledgement; the heartbeat timeout is five seconds. Without a change the first VALID episode could never be committed.

### 4.4 The QC memo (accepted under CP-3394)

The fresh-process QC writes `qc-verification-memo.json` beside its PASS report: the QC rule version, the digest of the QC code's source (`episode_qc`, `episode_audit`, `recorder`, `native_endpoints`, `raw_physics_chunks`, `scene_association`, `execution_snapshot`, `collection_boundaries`, `first_episode_inputs`, `qc_memo`), what it covers (seal verification, physical audit, native QC), the SHA-256 of the canonical report and a fingerprint over every file of the episode, the scope, the frozen inputs and the Teacher manifest. The Worker's ResultStore and the Coordinator's verifier are constructed with `trust_fresh_qc_memo=True`; if the memo matches what is on disk now and the reader's own QC code digest, they skip the covered recomputation; any difference (a byte, a missing memo, other QC code, another install after a recovery) recomputes in full. Cost on the real episode: 0.4 s against 289 s.

**VALID needs the memo.** The data is VALID only if the memo beside the QC report covers these exact files and this code (`OFFLINE_QC_MEMO_NOT_VALID` otherwise, INVALID data). Without it the Worker's seal would recompute the QC in full (about 290 s) after the processing budget was spent, and the Teacher's result would die at seal with `RESULT_AFTER_LEASE_DEADLINE` (a seal error for the whole result, not INVALID data); the Coordinator would do the same twice under its lock and the Worker's 10 s acknowledgement would fail. Grading the data INVALID instead keeps the Teacher's sealed result. If a memo is edited away between the processor and the commit, the Coordinator-side recomputation ends in a failed acknowledgement and the local seal, which keeps the Teacher's result.

What this makes of a "commit": **a journal commit rests on the memo.** It says the fresh-process QC ran on exactly these bytes with this code, not that the run recomputed it again. Nothing is exportable on that basis: `bundle.py` and `resolve_committed_episodes` call `verify_coordinator_commit`, `act_first_episode verify-commit` and `qc --run` do the same, and all of them build their verifier without the memo and recompute in full (about five minutes). **P4 L2 therefore requires the readback receipt** (`commit-proof.json` written by that full recomputation) in addition to the commit; a commit without the receipt is not an acceptance. The independence that remains inside the run is process independence (a fresh interpreter, no state of the replay) and content binding; the second computation is the readback.

### 4.5 Stop native step

The Teacher's stop stamp is a received `/clock` value and can lag physics by a step. The stop's native step is the last step finished before the receipt whose simulation time is not later than the stamp. No tolerance was added.

### 4.6 The clock map

Bag stamps are system-clock; the processor maps them to the monotonic clock with two anchors read back to back (about 1 us apart) and cross-checks the map against the scene-read pairs. The residual limit is 2 ms (it was 10 ms). The observed residual is 0.9 us on bag 147cb073 and 2.8 us on bag 429dbf50, a factor of 700 below the limit and below the tightest rule the map feeds ("received before request", the 100 ms join).

### 4.7 Child roles run the qualified install (CP-3459)

Live L1 and L2 on freeze feAWPg9k ended with `SupervisorError: EARLY_EXIT: broker: 1` before the Teacher. The broker is not a host process: it is the image `so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1` started by `docker run`, and its `/opt/venv/bin/so101_parallel_perception_broker` imported the `so101_demo` baked into the image on 2026-09-24 (source tree sha256 `3624dac7...`). That older parser still pins `lease_duration_s` at 300 s and refused the ACT runtime config (`FROZEN_RUNTIME_VALUE: lease_duration_s`). It was not a PATH lookup on the host.

Fact (read-only, B2): every live run so far, including the Teacher PASS runs and the pilot runs 147cb073 and 429dbf50 (their `run.log` says `broker_image=... (reused, per the coordinator's decision CP-2760)`), ran the broker from that baked tree, which equals no freeze (the source trees of freezes lHwgvaIW, feAWPg9k and VbKc889q hash to `91131e04...`, `fb23b807...`, `b2ecaadc...`). That held by design (the image is reused) and was invisible only because every config those runs used was accepted by the baked parser.

Changes: (1) `container_run_argv(source_package=...)` mounts the running package read-only over `/opt/venv/lib/python3.12/site-packages/so101_demo` and labels the container with its source hash; `qualified_package_root()` is the package of the running interpreter and, when `SO101_QUALIFIED_FREEZE` is set, must lie inside `<freeze>/qualified-install` (`QUALIFIED_PACKAGE_OUTSIDE_INSTALL`). Checked against the real image: with the mount the ACT config loads (1500/1500) and the broker, IPC and runtime modules import; without it the baked parser refuses it. (2) `runtime/qualified_commands.resolve_role_command` resolves every role command before it starts, never through PATH: the running interpreter with a `-m so101_*` module from the install; an `so101_*` console script only as an absolute path inside the install; `docker` only from `/usr/local/bin`, `/usr/bin`, `/bin`; `ros2` only from `/opt/ros/<distro>/bin`; anything else, including every bare name, is refused. `ProcessSupervisor(qualified_prefix=...)` applies it to the broker and worker roles (the composition passes the prefix from `SO101_QUALIFIED_FREEZE`), and the Worker's process group applies it to the station, consumer, raw recorder and processor when that variable is set. The image identity stays pinned by its id; what runs inside is now the qualified code, which is also what the Worker's client speaks.

### 4.8 The broker's detector stays the image's (CP-3460; closed by CP-3467, see the end of this section)

The first live runs whose broker executed the freeze's code (L1 and L2 on freeze fgNI7yJj) ended with `BROKER_CANDIDATE_AMBIGUOUS`: the freeze's `yolo_seg.py` passes the RGB frame to Ultralytics as BGR (commit 828af7c91, 2026-09-25), the image's 09-24 file does not, and on the same weights and inputs the corrected detector adds a second 0.36 candidate to the cup (the Worker requires exactly one). **Recorded deviation:** the broker keeps the baked file, deliberately, with the known RGB-as-BGR channel bug, because CP-3454, CP-3455, the Teacher PASS runs and the calibrated limits were made with it. The freeze's package is still mounted for contracts, IPC and runtime; only `adapters/perception/yolo_seg.py` is mounted over it, read-only, from a durable copy under `$R/deps/broker-detector-baked-3624dac7/` whose sha256 is fixed in the code. The detector hash is in the container label and in `broker-source-pin.json` of every run; a missing or mismatching pin stops the broker. Re-baselining perception with the corrected detector is a follow-up and **a gate before formal collection.** Document: `broker-detector-pin`.

**Closed (CP-3467, document `perception-rebaseline-r6-unpin`).** The second candidate is the red landing ring (flat, conf about 0.36), not a detector fault. `BrokerMaskLocalizer.localize` now localizes every candidate and keeps the one whose xy circle fit succeeds (r 0.04 +- 0.01 m) and whose points span at least 0.05 m in z (rule R6); exactly one must survive (`BROKER_CANDIDATE_AMBIGUOUS: n of m`, or `GEOMETRY_REJECTED` when none does). The pin, its mount, its label and its code are removed; the broker runs the freeze's own `yolo_seg.py` (BGR fix) and `broker-source-pin.json` records its hash. On 343 rendered ACT-scene cases (3 anchors, 300 random, 40 near the ring) R6 gives exactly one cup in 343 (274 without it), no wrong object, xy error p95 0.84 mm (max 4.81 mm); on the 125 saved broker inputs the survivor's pose equals the pinned-era measurement to 0.0 mm. New explicit benchmark gate `benchmark_test/test_act_scene_perception_gate.py`. Open risks are listed in the document (left-anchor start-end margin 3.2 mm, ring-overlap errors against the 2 mm MoveIt tolerance, circle-fit bias against the calibration domain).

## 5. Faults (diagnostic mode only; every output beneath `<run>/fault-sandbox/`)

| fault | injection | processed | data |
| --- | --- | --- | --- |
| `recorder_absent` | no raw recorder is started | no | INVALID `RECORDER_ABSENT` |
| `recorder_late` | the raw recorder starts 5 s after the Teacher's setup evidence (`reachability-observed.json`) appeared | no | INVALID `RECORDER_STARTED_AFTER_TEACHER` |
| `queue_overflow` | a sandbox copy of the bag without 40 consecutive physics-chunk messages from the middle of the stream | yes | INVALID |
| `source_gap` | a sandbox copy without 60 consecutive arm `controller_state` messages | yes | INVALID |
| `output_write_failure` | the processor's output directory is made read-only for the run | yes | INVALID (`rc=4`) |

All five: Teacher PASS, no data-sourced cancel, QC NOT_RUN, not exportable, run exit code 3.

Evidence on the real bag 147cb073 (`scratch/p3fault-*`): `source_gap` rc 3 in 148 s (`OFFLINE_SOURCE_GAP: /arm_controller/controller_state gaps=1`); `queue_overflow` rc 3 in 141 s (`OFFLINE_SOURCE_GAP: /so101/simulation/physics_step_chunks gaps=1`); `output_write_failure` rc 4 in 16 s (after the exit-code fix; the first run, before it, exited 1).

`recorder_late` is judged by rule, and its evidence is recorded in the orchestration facts (when the setup evidence was seen, the delay, when the start was requested, the late bag's first stamp). On the real data: the Teacher's first command (`phase_begin` seq 5) was at system time 867.243 s and the setup evidence file appeared at 865.547 s; a bag that starts 5 s after the evidence starts at 870.55 s, 3.3 s after the first command. A real late copy of bag 147cb073 starting there (`scratch/p3fault-bag-late`, first stamp 1791425870.549 s) was processed: rc 3, `RECORDER_EVENT_MISSING: reset_complete`, `OFFLINE_TEACHER_EVENT_SEQUENCE_GAP`. So the fault is what it claims, and the content agrees with the rule. In production the guard against a bag that is late is the pre-start RECORDING check; the fault exists to prove the data side reacts.

## 6. Losslessness: how a loss is detected, per topic

Phase C (`plans/changes/2026-10-08-transport-loss-attribution-gate.md`) gave every topic the episode depends on a rule. The scan of the raw bag runs the rules (the sealed episode does not hold these topics), writes `topic-loss.json` beside the episode, and the QC (rule `act_data_qc_v4`, check `topic_loss_gate`) binds that document to its verdict. The window of the new rules is from the start of the retained world (the first unpaused world record after the last pause, or the verified reset) to the Teacher's terminal event plus 0.1 s; the older sequence rules keep their own windows. A loss inside the window on a topic the episode uses is INVALID (`OFFLINE_TOPIC_LOSS:<topic>`; the older rules keep `OFFLINE_SOURCE_GAP`, `OFFLINE_CAMERA_GRID`); a loss outside the window, or on a topic the episode does not use, is recorded in the document. A gap that overlaps a gap of `/clock` is a producer stall (the producer's cycle was skipped; nothing was published), counted as such and not as a lost message.

| topic | used | detection | in-window loss |
| --- | --- | --- | --- |
| `/clock` | yes (drives the replay clock) | 2 ms stamp grid over the window (new) | INVALID |
| `arm`, `gripper` `controller_state` | yes | 2 ms grid; a gap matters where a label instant needs the frame (CP-3439) | INVALID where a label needs the frame; other gaps recorded as diagnostic |
| `neck` `controller_state` | no (no row is made from it) | grid, recorded | recorded |
| physics chunks | yes | chunk sequence and step continuity | INVALID |
| `/so101/simulation/evidence` (world) | yes | publisher sequence | INVALID |
| `/so101/simulation/scene_state` | yes | published in the same call as the world record: every world record of the window must have a scene state of the same step and stamp (new). A lost frame is a world record without its pair | INVALID |
| `/so101/simulation/robot_contacts` | no | none; a lost sample is a lost sample of a chunk, which is covered. Count recorded against the chunks' steps | recorded |
| camera `camera_info` | yes | 100 ms grid, head equals wrist | INVALID |
| camera `color` | yes | every `camera_info` stamp of the rows interval (verified reset to normal stop) has its image (new) | INVALID |
| `/joint_states` | yes | 10 ms header-stamp grid over the window (new). The engine's own bound (a row takes the newest message within 100 ms) stays | INVALID |
| Teacher events | yes | `seq` 1..N | INVALID |
| planning-scene reads | yes | the bag's count equals the sidecar's own count of reads (new) | INVALID |
| `/so101/simulation/joints`, `physics_hazard` | no | none (a latched pair and an empty latch) | recorded |

The recorder's aggregate "messages lost on the transport layer" is one total at stop, and at the default log level rosbag2 gives no per-topic figure. For a bag recorded without a breakdown it is reconciled instead (the rule below stays for those bags): the messages the topics show missing anywhere in the bag (outside producer stalls) must account for the reported number, and the shortfall, if any, fails closed (`OFFLINE_TRANSPORT_LOSS_UNATTRIBUTED`). A bag whose total is unknown fails closed too (`OFFLINE_TRANSPORT_LOSS_UNKNOWN`).

**Per-topic breakdown (C5, CP-3394).** `ros2 bag record --log-level debug` prints one line per lost-message event, `Messages lost on transport layer for topic '<t>'. Total lost: N` (the subscription's cumulative count; the sum over topics equals the stop total, checked on a flooded test publisher). The raw recorder now runs with debug logging, keeps the log in `bag-record.log`, and writes `transport_lost_by_topic` into `record-stats.json` (an empty object when nothing was lost). With the breakdown present the aggregate clause is replaced: the per-topic numbers must sum to the total and name only recorded topics (else `OFFLINE_TRANSPORT_LOSS_UNATTRIBUTED`); on a topic the episode uses, the reported count must not exceed what that topic's own rule shows missing anywhere in the bag, else `OFFLINE_TOPIC_LOSS:<topic> reported=<n> detected=<m>` (a gap inside the window stays `OFFLINE_TOPIC_LOSS` from the rule); on a topic the episode does not use, the loss is recorded only. A loss on the events topic after a gap-free sequence that reaches the terminal event is a message after it (the terminal carries no published count). The robot-contact step span is read only when a loss is reported on that topic. Debug logging costs one log line per received message (about 9 MB per 20 s at 3 kHz); a synthetic 3 kHz recording showed the same message counts and no added loss. L2 (45315499) was recorded without the breakdown and stays INVALID.

QoS: the high-rate topics (chunks, contacts, the three controller states, `/clock`) use deep reliable queues. The colour image topics use the publisher's default QoS (no deep queue); an image lost to a full recorder queue is the camera case above.

Transport losses: `ros2 bag record` prints the number of messages it lost on the transport layer at stop (bag 147cb073: 6; CP-3449: 5; the L2 bag 45315499: 7). It is parsed into `record-stats.json` (`transport_lost`; for stats written before the key existed, from `bag-record.log` beside them). CP-3457 had recommended making any reported loss INVALID and that was reversed because the one good bag would have become INVALID with no way to say why. Phase C closes the gate that reversal left open: per-topic rules above, plus the reconciliation. On the two reference bags (details in the change document) the 147cb073 total is accounted for (the topics show 11 missing messages outside the window, none inside); **the L2 bag 45315499 is not: its 7 reported losses are matched by only 4 messages missing on any topic, so 3 are unattributed and the gate fails it.** That is a real finding, reported to the coordinator before anything else was changed; it stands until a decision on it is recorded. A formal collection run stays refused until that decision.

## 7. Cleanup inventory

The live Recorder's machinery is removed where the offline processor does not reuse it. Step one (done with the switch): the run path no longer imports it; 19 tests of the retired orchestration and 3 of the retired switch were removed with a TSV (`p3-cleanup-tests-removed.tsv`). Step two (done 2026-10-08, change document `plans/changes/2026-10-08-cleanup-step-2-live-recorder-removal.md`): the inventory `p3-cleanup-inventory-curated.tsv` (with `p3-cleanup-inventory-coverage-dump.tsv`, the per-function coverage of the production processor on the real bag, as its evidence) was applied.

- Removed whole: `cli/act_episode_recorder.py` and its `setup.py` entry, `RecorderOrchestrator`, `RecorderLaunch`, `RECORDER_ROLE`, `ros/recorder_receiver.py`, the three spool modules (`act/chunk_spool.py`, `act/controller_spool.py`, `act/spool_lifecycle.py`), `act/recorder_telemetry.py`, `act/episode_recorder_process.py` and `ros/episode_recorder_sources.py`, with the tests that exercised only them.
- Reused, therefore moved and kept: the engine (now `act/offline/engine.py`, `OfflineEngine`), the sources (now one class, `act/offline/sources.py`, `OfflineRosSources`), the frozen policy loader (`act/offline/policy.py`, unchanged: the closed schema is baked into frozen inputs manifests), `RecorderDataSide`, the synchronizer, alignment, assembly, lossless writer, seal, QC.
- Live-only code inside reused modules (receiver threads, the spool processes and their lifecycle, the live scene poller and client, the CAPTURING wait and ready file, stall telemetry, deferred events, the sandbox fault injector, the backlog bound of the physics adapter): removed by refactor. The receiver-lag check of the physics adapter is kept: it is a live rule on the replay too.

One behaviour is narrower and is recorded as such: a Teacher event other than `scene_operation` that arrives before the capture has started is no longer held and replayed; it makes the data INVALID (`RECORDER_NOT_READY_BEFORE_TEACHER_EVENT`). On all eight golden runs the held-event count was zero, and the replay starts the capture before the Teacher's setup.

**Plan deviation (CP-3394) closed.** Plan section 5 P3 puts the cleanup before the fresh freeze and the live acceptance; it was deferred until after the acceptance and has now been done, so P4 covers the code after the cleanup. The condition this amendment set (the full gate and a byte-identical re-run of the processor on bag 147cb073) was met under a precise definition of "byte-identical": two runs of the same code on the same bag already differ in random scene-association UUIDs, the wall-clock stamps of the lossless writer's queue evidence, the digests derived from those, one staging file name and report timing. Outside that measured list every output file (frames, acquisitions, references, rows, inputs, physics, the QC verdict and counts) is byte-identical before and after the deletion, on bag 147cb073 and on the L2 bag 45315499, and the six INVALID cases give the same reasons. The comparator and the golden hashes are in the change document.

## 8. Verification

- Unit and integration tests with fakes and a real tiny bag (`test_p3_offline_switch.py`, `test_p3_qc_memo.py`, `test_p3_collection_chain.py`, `test_p3_rework.py`, `test_p2_offline_processor.py`, the processor and scan tests), the full gate (`pytest -n 8`, cwd outside the worktree, the three git-cwd provenance files excluded), and a scratch colcon install whose installed package runs the tests that touch files and paths.
- Real-bag checks (not live): the production processor VALID with QC PASS; both bag faults INVALID with rc 3; the read-only output rc 4; the late bag INVALID rc 3; the QC memo path 0.4 s against 289 s with the same report.
- Live acceptance (plan P4), serially on one stack: L1 `--collection off` (Teacher PASS, data DISABLED, rc 0); L2 `--collection on` (Teacher PASS, bag complete, processor VALID, QC PASS, ResultStore commit, **and the readback receipt from the full recomputation**, export refused because the mode is diagnostic, rc 0); L3 to L7 the five faults (Teacher PASS, data INVALID, rc 3). The Teacher's phase-time median in L2 to L7 is compared with L1 and, because L1 shares the producer changes, with the pre-change PASS runs; a difference over 20 % is reported.

## 9. Risks and open points

1. **Wall time.** Processing is about ten minutes inside the EXECUTING stage, the readback another five. A formal wave of 20 episodes on eight workers makes the processing the bottleneck; the processor is single-threaded and its replay could be split by window if that matters.
2. **Lease equality** (4.2). Not exercised live with VALID data; L2 is the first test.
3. **Memo trust** (4.4), including that a commit is backed by the memo only and that export needs the readback.
4. **Transport losses** (section 6): recorded, not yet fatal.
5. **Disk.** A bag is about 2 GB per episode and is retained as the evidence; the episode and the scratch of the processor add about 1 GB.
6. **Single scene writer** (section 3).

## 10. Change documents this amendment rests on

`2026-10-08-p3-switch-to-the-bag-recorder-and-offline-processing`, `act-runtime-stage-bounds-for-offline-processing`, `teacher-bound-split-and-processing-budget`, `qualified-role-commands-and-broker-package`, `broker-detector-pin`, `fresh-qc-verification-memo`, `stop-native-step-at-the-stamp`, `apply-bounded-scene-bracket`, `planning-scene-freshness-by-bracketing`, `act-move-group-does-not-publish-the-monitored-scene`, `controller-tick-lockstep-and-lossless-clock`, `camera-sim-synchronous-rendering`, `offline-window-start-after-worker-pause`, `raw-pilot-lifecycle`, `last-normal-stop-and-late-camera-sequence`, `first-row-association-wait-and-tail-physics-coverage`, `teacher-event-clocks-colour-and-single-final-stop`, `controller-reference-label-instant-continuity`, `consumer-ready-receipt-race-and-pose-wait-stop`, `offline-processor-pilot-fixes`, `cleanup-step-2-live-recorder-removal`, `qc-and-replay-speed`, `transport-loss-attribution-gate`, `single-fresh-readback`.

Superseded: `scene-association-blockers-on-the-pilot-bag` (findings only, "decision needed"); its decisions are CP-3441 (stale first scene clock, colour), CP-3445 (colour root cause), CP-3440 B (read bracket) and CP-3449 (apply-bounded bracket). The document is marked superseded in its own header.
