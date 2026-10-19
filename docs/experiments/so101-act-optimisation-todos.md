# SO-101 ACT open optimisation and engineering to-dos

This is the tracking list for to-dos the human asked to record. Update it when an item starts, finishes or changes, and cite
the ledger checkpoint. Evidence and results belong in the ledger (`docs/experiments/so101-act-data-experiment-ledger.md`).

Last updated: 2026-10-19.

| # | Item | Status | Source / evidence |
| --- | --- | --- | --- |
| 1 | **Logic vs runtime parameters, and stage-by-stage collection.**<ul><li>L frozen and sha-bound, R free, RO within the qualified envelope.</li><li>`act_collect_parallel --stop-after-phase1`, and `act_process_parallel --phase2 \| --retry-round \| --finalize`, each with a fresh runtime document; skipped retry rounds can run later.</li><li>Templates freeze and check only logic files; source-text checks are replaced by behavioural tests.</li><li>Training: runtime block, `num_workers` ≥ 1, optimiser constants in the hash, source commit bound to the policy.</li></ul> | Confirmed design; implementation starts after the EXP-625 seal | `docs/superpowers/specs/2026-10-19-so101-act-logic-vs-runtime-params-design.md` |
| 2 | **Phase-2 per-case processing.**<ul><li>About 183 s median, single-core (about 1.0–1.1 cores and 1.1–2.4 GiB per processor).</li><li>Find the hotspots and add parallelism within a case.</li></ul> | Profiling (subagent) | EXP-625 `host/processing-journal.jsonl`; report `R/phase2-profile-20261019/report.md` |
| 2b | **Post-run collection verification** (`so101_demo.act.bundle._verified_collection_uncached`).<ul><li>On EXP-625 it ran 17+ min on one core (about 98.6% CPU).</li><li>Find out why the O1 parallel readback / verify-once path is not used.</li><li>Make it parallel (workers = runtime) or reuse the existing proofs.</li></ul> | Analysis (same subagent) | Same report |
| 3 | **Finalize readback and merge.**<ul><li>EXP-625 retry-2 ended at 02:36:28Z, but the index and result were written at 02:45:15Z: about 8 min 47 s with no writes, about 200k files and 60–70 GB at about 120 MB/s.</li><li>Options: more `readback_workers` (runtime), verify once with reuse of the phase-2 proofs, batching, an incremental merge per round.</li></ul> | Analysis (same subagent) | Same report |
| 4 | **Phase-2 `processor_count`.**<ul><li>Measured: 16 concurrent fit (2.59 GiB RSS, 2.9–3.07 GiB cgroup peak each, no OOM). Throughput is 187 scenes/h at 16 against 115 at 6; the knee is between 16 and 24.</li><li>Needs item 1 first, because processor_count must become a runtime parameter.</li></ul> | Waiting on item 1 | `R/phase2-profile-20261019/report.md` §4 |
| 5 | **Gate scratch.** Each v4 gate leaves about 12 GB of pytest TMPDIR under `R/scratch`; let the gate prune it after readback. | Open | Batch h deleted 93.6 GiB (`R/evidence-deletion-20261019h`) |
| 6 | Rollout O6 hardening, then a real rollout run. | Open | Native rollout design 2026-10-18 |
| 7 | Load flakes: `test_owner_phase2`, `test_capture_runs_before_teacher_start` (real-rate replay), `so101_teleop` `test_process_identity` (UNKNOWN identity), C++ timing tests. | Open | Gates `d1815a322f89.run1-fail` and others |
| 8 | Nsight Compute: SM Active and bubble ratio for training. | Open | — |
| 9 | frm-044 refusal message specificity (`EPISODE_COLLECTION_IDENTITY_INVALID`). | Open | Differential readbacks 2026-10-18 |
| 10 | Template defects found on side-wrist: verify-report fingerprint source (fixed in the template, CP-3740), stale source pattern (fixed, CP-3741). These are covered by item 1's template work. | Covered by item 1 | Ledger CP-3739..CP-3741 |
| 11 | **Parallel hashing in the seal and readback tools.** `seal_roots.py` hashes serially: 97 GB and 319k files in 142 s. With 16 threads it would be about 30-50 s (SHA-NI gives about 1.8 GB/s per core), with the same manifest. Small gain; do it with item 1's tooling work. | Open | EXP-625 seal 2026-10-19 11:29:58-11:32:20 +0800 |
| 12 | **Dataset export** (`bundle.py` `export_dataset` / `_write_export`).<ul><li>TRAIN-003 export of 103 episodes read about 163 GB and wrote at about 36 MB/s.</li><li>(a) The pre-export full QC recompute per episode (about 19.8 CPU-s each) goes away under the approved F4/P3 memo trust.</li><li>(b) `_write_export` fsyncs every frame serially, about 184k fsyncs. Replace them with one `syncfs` before the `.partial` rename: same durability, because the final directory appears only after the data is on disk.</li><li>(c) Write in parallel with threads; file writes and sha256 release the GIL.</li><li>(d) Read and hash each frame once instead of twice (`_check_frames`, then the write).</li><li>(e) Reference-only dataset: a manifest plus paths into the sealed, read-only evidence, so frames are not copied across filesystems. This changes the dataset format and needs a human decision.</li></ul> | (a)–(d) Open, within approved scope; (e) needs a decision | TRAIN-003 `train-run-20261019T0342Z`; `/proc` io counters 2026-10-19 03:40–03:42Z |
| 13 | **Tool paths after the migration.** `run_train.zsh` still records gate `a1d3b7b0bbb5`, and its overlay symlinks pointed at the pre-migration freeze, so the first TRAIN-003 launch failed with `ModuleNotFoundError: pydantic`. The symlinks were repointed. After any layout change, run every tool entry point end to end. | Open (symlinks fixed) | TRAIN-003 failed attempt `train-run-20261019T0335Z.failed-overlay-symlinks` |

**Profiling result (2026-10-19, `R/phase2-profile-20261019/report.md`).** One case takes 182 s even when it runs alone, so the
cost is intrinsic, not contention. It is pure CPU on one core:

| Stage | Time | Share |
| --- | --- | --- |
| Replay loop | 122 s | 67% |
| QC child | 20 s | 11% |
| Seal | 17 s | 10% |
| Scan | 13 s | 7% |

The hotspots are generic ROS-to-dict conversion, JSON round trips, `deepcopy`, and a row-readiness computation done twice.

Finalize took 8 min 47 s: 109 full QC recomputations at 19.3 s each on 4 readback workers. `_retry_rounds` repeats that pass
three times, about 25 min in all. The executor's post-run gate then ran it again serially (34 min), and export would run it a
sixth time.

Planned follow-ups from the report, in order:

| # | Follow-up | Effect | Notes |
| --- | --- | --- | --- |
| 2a | Verify each round once (F1) | −17 min | Integrity-neutral. |
| 2b | 16 readback workers (F2) | 526 s → about 222 s per pass | Integrity-neutral. |
| 2c | Parallel post-run gate (P1) | 34 min → about 3 min | Integrity-neutral. |
| 2d | Export workers set (P4) | Export about 5 min | Integrity-neutral. |
| 2e | Processor single-core options 1–7 | 182 s → about 120 s per case | Output-neutral by construction. Needs a byte-identical differential with `association_id` (a random UUID) normalised. |
| 2f | Two policy decisions for the human | | See below. |

The two policy decisions in 2f:
- Trust the content-bound QC memo at readback (F4/P3): 0.6 s instead of 19.3 s per scene. Recommended only for intermediate passes, never the final one.
- Drop the processor's duplicate in-process seal verification (option 9): −12 s per case. It removes one defence layer.

**Human decisions on 2f (2026-10-19, "ok", do later):**
- F4/P3 approved: trust the content-bound QC memo at readback, as recommended. Intermediate finalize passes, the post-run gate and export use the memo (0.6 s per scene). The final finalize pass still recomputes QC in full.
- Option 9 approved: drop the processor's duplicate in-process seal verification. The independent QC child still verifies the seal (−12 s per case).

## Done

Optimisations and engineering improvements that are finished. Numbers are copied from the ledger or the commit message; "not
measured" means the source states no figure. "CP-xxxx" is a checkpoint in
`docs/experiments/so101-act-data-experiment-ledger.md`; other ledgers are named in full.

### Collection runtime

| Item | What changed | Measured effect | Date | Evidence |
| --- | --- | --- | --- | --- |
| Teacher/ACT decoupling | Teacher, Recorder and QC were decoupled; process-quality success and data-fault stop clauses were replaced. | Not measured as speed. ACT data validity no longer depends on Teacher process quality. | 2026-10-05 | CP-3262 |
| Fixed in-container ROS identity | Collection shards use one fixed ROS identity; per-worker domain and namespace code was removed from the ACT path. | Enabled concurrent containers (EXP-587: two containers, 8 of 8 VALID). No speed figure. | 2026-10-13 | CP-3633..CP-3644; `ebe2f11ae`, `983c1d7b5`, `7b2d6c902` |
| Native execution is single-worker | Native entries accept one worker only; concurrency moved to the container campaign. | Not measured. | 2026-10-14 | CP-3645; `8328c3438` |
| Recording cap | `max_concurrent_recordings` limits shards recording at once; the shard status carries a phase field the Host scheduler reads. | Loss per shard-second was 0.016-0.038 with 1-4 recordings and 3.6 with 8 (EXP-589). Cap 4 was later qualified (38 of 40, EXP-618). | 2026-10-14 | CP-3649, CP-3713; `d382a6750` |
| Optional scheduling limits | `max_concurrent_recordings`, `max_tasks_in_flight`, `min_assignment_gap_s` are hashed campaign-config keys at every worker count; shard containers run with `--oom-score-adj 900`. | Not measured. | 2026-10-14 | CP-3651; `cfd43c6da` |
| Recorder sidecar off the read loop | Sidecar writes run in a separate thread; goal-check service calls are retried. | Not measured alone; part of the EXP-590 remedy. | 2026-10-14 | CP-3649; `d382a6750` |
| Sidecar fsync once at close | Raw sidecar flushes during the episode and fsyncs once at close. | EXP-597 did not raise the VALID rate (4 of 16). Kept as an I/O reduction; no speed figure. | 2026-10-15 | CP-3665, CP-3666; `737db31a5` |
| Queued controller-state publishing | `ros2_controllers` 4.42.1 vendored; joint state and controller state go through a lock-free queue drained by a dedicated thread; overflow is counted; paused frames are retried. | EXP-592: no overflow, no source gaps. Before: 645 controller-state holes over 2050 s of EXP-591, rising from 0.03 to 1.15 per second under CPU pressure. | 2026-10-14 | CP-3654, CP-3655; `55885a936` |
| Lossless bag compression | Raw bags are recorded as mcap with zstd Fastest chunks of 4 MiB; topics, QoS and log_time are unchanged. | One EXP-609 bag: 2.04 GB to 0.29 GB (7.11 times), 2.8 s CPU, all 284657 messages identical. | 2026-10-16 | CP-3693; `85a10c1c0` |
| Fast DDS profile for the shard | Heartbeat period 20 ms and NACK response delay 1 ms for the collection shard. | Reproduction with eight mini-shards: 0 messages later than 50 ms in two runs. | 2026-10-16 | CP-3703, CP-3707; `6f36a5142` |
| Detach source re-snapshot, manifest write after readback | The Teacher re-snapshots the source for DETACH; the post-apply manifest write moved after the readback request. | EXP-608 removed the source-age failures; EXP-609 12 of 16 VALID, 1 INPUT_STALE. Final effect not isolated. | 2026-10-15/16 | CP-3689, CP-3691, CP-3692 |
| Reset and stop-proof hardening | Bounded re-read of reset evidence, physics hold around a faulted reset, stop probe rebaseline, planning-scene read retried once. | Not measured. Targets the frm-007 class of initial-gate failures. | 2026-10-17 | CP-3716; `04764e11f`, `a1d3b7b0b` |
| Remove recording phases | POST_RECORDING gate branches and CPU shares removed after the two-phase split. | Not measured. | 2026-10-16 | `66c36bb8e` |
| Two-phase collection | Phase 1 only records; phase 2 (replay, QC, scan) runs in separate processors with a scheduler, journal and two-phase time limits; combined proof; native processor launcher. | EXP-605: 16 scenes in 21 min, phase 2 processed 16 of 16 without retry. EXP-611 qualified 40 of 40 on every gate. | 2026-10-15 | CP-3674..CP-3684, CP-3696; `df2d7cc3f`, `389e8437c`, `0979a1e57` |
| In-campaign retry rounds | `retry_invalid_max_rounds` re-runs INVALID scenes with a Teacher PASS inside the same campaign, with a round time budget and a reopened dispatch fence. | EXP-620: retry round 1 recovered 5 of 5; 69 of 70 committed. | 2026-10-16 | CP-3703, CP-3715; `d1c5926f3`, `e96393f6e`, `ed124ae20` |
| Launch parameters instead of code edits | Scheduling keys and time limits are authoring options; the total deadline is a campaign-config key outside the identity (raised to 9000 s). | Not measured. | 2026-10-16 | CP-3697 |
| Spot-check plane | `act_collect_parallel --spot-check`: one worker, one scene, diagnostic mode, no reservation. | Not measured. | 2026-10-18 | CP-3725; `33074e2d4`, `0bb4ea2df` |
| Camera rig v2 profile | A rig profile replaces about 20 hard-coded head/wrist points; the side-wrist rig composes the Teacher role only and has no head or neck. | Not measured as speed. Differential readback 101 of 101 identical. | 2026-10-18 | CP-3724; `d93149ea6`, `c5176d802`, `d63d95e3f` |

### Phase 2, QC and readback

| Item | What changed | Measured effect | Date | Evidence |
| --- | --- | --- | --- | --- |
| QC session caching and replay speed-up | Each pure verifier runs once per unchanged file set in a session; one MuJoCo model per session; step index instead of O(n^2) scans; replay audit verifiers 6 times to 1. | Three readback steps 2,951 s to 347 s; fresh QC 253 s to 26 s; replay 267 s to 148 s; check-export 1,325 s to 77 s. Output byte-identical. | 2026-10-08 | CP-3469; `c039b78be` |
| Host readback: one physical audit per episode, process pool | Verifier and parity step share one session; bounded pool of one subprocess per scene (default 4). | One real episode 126.9 s and 3.4 GB to 24.4 s and 1.8 GB; EXP-587 eight scenes 206 s serial to 56 s with four workers. | 2026-10-14 | CP-3645; `150e9a649` |
| Offline processing memory | Processor peak memory cut with identical outputs. | Processor high-water mark 5.38 to 2.15 GiB; wall time 194 s to 189 s. | 2026-10-14 | CP-3651; `dfe91fc0a` |
| Verify-once and parallel readback | Process-local memo of `_verified_collection` bound to file and tree signatures; spawn process pool for resolve, attach and export; `SO101_ACT_EXPORT_WORKERS`. | Pre-training readback, attach and export: 2.6 h to about 8 min (16 workers, TRAIN-001). The dry run took 9442 s because every episode was regraded three times. | 2026-10-17 | CP-3720, CP-3721; `f6a32dbe3` |
| O1 QC speed-up | World source validated once per content; numpy source-model comparisons with one MjData; vectorised PNG unfiltering; ROS decode once per message content; raw-chunk checks shared. | Per episode 30.4 s to 21.1 s (about 31 percent); 16-way total wall 262.9 s to 195.1 s. 101 of 101 verdicts byte-identical. | 2026-10-18 | CP-3722; `347b312a0`, `9b1f3ce02`, `5233437fe`, `e1a73f4cb`, `2904fca37` |
| O2 committed implies exportable | One Teacher-oracle exclusion rule used by export and phase-2 grading; an excluded episode grades INVALID and becomes a retry candidate. | Process benefit: no committed episode is refused at export. Real-data differential 100 of 101 identical (frm-044 refused). | 2026-10-18 | CP-3723; `b14833df0` |
| O4 processor count default | Checked: the code default `min(12, MemAvailable / 3 GiB)` already gives 12 on the 64 GB host; no code change. | Not measured (earlier runs passed 6 explicitly). Open item 4 is the follow-up. | 2026-10-18 | CP-3722 |

### Export and training

| Item | What changed | Measured effect | Date | Evidence |
| --- | --- | --- | --- | --- |
| Parallel export and frame hashing | Frame hashing in the pool; `act_train --workers`; 16 export workers. | Part of the 2.6 h to about 8 min result above. | 2026-10-17 | CP-3720; `f6a32dbe3` |
| O3 training observability | `metrics.jsonl` and stdout every 100 steps: losses, learning rate, samples/s, ETA, DataLoader wait versus compute and the wait share; validation loss every 2000 steps on 512 chunks; `num_workers` as a `training.yaml` key. | TRAIN-002 at step 2100: about 30 samples/s, DataLoader wait 15-23 percent. | 2026-10-18 | CP-3722, CP-3723; `442bda47e` |
| O7 idle trim and training view | `training.sample_selection` trims the leading idle stretch; separate backbone learning rate; `training-002.yaml`. | Train samples 72,534 to 68,605. Idle rows were 66 percent in the exported episodes. | 2026-10-18 | CP-3722, CP-3723; `4c9f6f5b5` |
| DataLoader workers 16 | The side-wrist training config sets `num_workers` 16 (human decision after TRAIN-002 showed 15-23 percent wait). | Not measured yet (TRAIN-003 not run). | 2026-10-18 | CP-3723, CP-3724; `dff04f256` |
| `act_train` output locations | `--dataset-output` and `--evidence-dir` write the dataset and bundle where told and record path and sha256 in the evidence directory. | Not measured. Lets the 12 GB dataset and the policy live outside the evidence partition. | 2026-10-18 | CP-3727; `57aeb94f0` |

### Gates and tests

| Item | What changed | Measured effect | Date | Evidence |
| --- | --- | --- | --- | --- |
| Benchmark suite partition | 13 `test_perception_benchmark_*` modules moved to `benchmark_test/`; default pytest discovery is `testpaths = test`. | Ordinary gate 17.85 s instead of 338.18 s (94.7 percent saved, about 18.9 times faster, macOS). | 2026-09-03 | `docs/experiments/so101-test-suite-partition-experiment-ledger.md`; `0439d2c3f` |
| Pytest parallel gate | Ordinary `so101_demo_py` pytest runs in parallel subprocesses; default concurrency 8, an explicit `--workers` overrides it. | 3056 nodes: 189.8 s at 4, 99.2 s at 6, 59.3 s at 8, 27.1 s at 10, 28.0 s at 12 (10 measured best; default set to 8). | 2026-09-15 | `docs/experiments/so101-pytest-parallel-gate-experiment-ledger.md` |
| Pytest suite optimisation | Four unregistered teleop test files entered CTest; duplicate and weak tests replaced; test-only `HoldProxy` teardown hang fixed. | Not measured as speed. Teleop ordinary suite (8 workers) about 44 s. | 2026-09-24 | `docs/experiments/pytest-suite-optimization-experiment-ledger.md` |
| Fast gate (v1) | Gate script with serial and parallel groups for demo, teleop and colcon; upstream controller tests under a skip-when-unchanged baseline. | `8328c34382ba`: 620 s with all three speed-ups; the serial configuration took 907-966 s on other commits. | 2026-10-14 | CP-3643, CP-3645, CP-3654 |
| Gate v2 | Concurrent demo and colcon stages with per-stage ROS domains, 16 demo workers, ccache (4.9.1), colcon summary counting both teleop phases. | v1 1070 s, v2 cold 654 s, v2 warm 448 s on the same commit (about 7 min); same 17 failures as v1. | 2026-10-18 | CP-3723 |
| Gate v3 and v4 | v3 keeps the v2 checks and skips the ros2_control and JTC suites when tree and apt hash equal the green baseline. v4 keeps the v3 checks and moves build trees to `W/so101-build/gates/<id>`. | v4 proof gate `57aeb94f04be`: build 46 s (ccache 381 hits, 25 misses), demo 445 s, colcon 2217 tests. v3 alone: not measured. | 2026-10-18 | CP-3727 |
| Test-only flake fixes | `test_native_timeout_is_bounded` waits for the detached state write; `test_ready_instance_is_polled_during_barrier` has a larger fake-clock backstop; `test_recording_cap` made deterministic; two other flaky gate tests fixed. | 20 runs of the two O5 tests, 8 concurrent, all passed. | 2026-10-15..18 | CP-3681, CP-3693, CP-3722; `e8bf34d75`, `caa85748a` |
| Fast-gate self-kill fix | A test that signals process groups runs in the serial group; every teleop test invocation runs in its own session. | Cause proven by strace under reproduction. | 2026-10-14 | CP-3645 |
| Adaptive worker pool | Adaptive worker pool for parallel point validation. | W10 5.57 points/minute and 7.39 times W1; W8 stays the recommended default. | 2026-09 | `docs/experiments/so101-parallel-adaptive-worker-pool-experiment-ledger.md` |

### Evidence, disk and tooling

| Item | What changed | Measured effect | Date | Evidence |
| --- | --- | --- | --- | --- |
| Evidence layout consolidation | 18 persistent evidence sources moved by same-filesystem rename under `/data/work/so101-evidence`. | 36,685 files and 600,949,404 bytes unchanged by SHA256; no legacy top-level directory left. | 2026-08-13 | `docs/experiments/so101-evidence-layout-migration-experiment-ledger.md` |
| Evidence cleanup, early batches | Superseded run roots, freezes, scratch. | CP-3450 about 760 GB; CP-3521 about 909.5 GB (1,259.8 to 350.3 GB used); CP-3559 798.4 GB (1,176 to 379 GB used). | 2026-10-08..11 | CP-3450, CP-3521, CP-3559 |
| Evidence cleanup under a recorded policy | Failed runs, the old topology, old gates, image contexts and scratch go; in-use and latest reference runs stay; each batch has a plan and a record. | 10-15: 334.6 GiB; 10-16 (batch a): 883.0 GiB; batch b: 204 GiB (disk 936 to 719 GB); batch c: 189.4 GiB; batch d: 354.7 GiB (86 entries, `R/evidence-deletion-20261018d`); batch e: 227.2 GiB (old history, conclusion files kept, `R/evidence-deletion-20261018e`); batch f: about 73.6 G; batch g: 28.2 GiB; batch h: 93.6 GiB. | 2026-10-14..19 | CP-3653, CP-3664, CP-3693, CP-3703, CP-3716, CP-3727, CP-3728 |
| Docker cleanup | Logs of 85 exited containers saved, then the containers, 40 superseded images and dangling build cache removed. | Free space 76.1 to 303.2 GB. | 2026-10-14 | CP-3651 |
| Sealed roots | `seal_roots.py` writes a per-file sha256 manifest, `SEALED.json`, read-only files and a registry; cleanup scripts refuse any entry in a sealed root. | The EXP-620 root (141,724 files, 55.2 GB) is protected; sealed readback of 15 roots found 0 problems in 1,228,567 entries. | 2026-10-17 | CP-3716, CP-3728 |
| Host sampler | `host_sampler.py`: 1 Hz per-container cgroup CPU, memory, IO and pressure, per-thread scheduler delay, host and GPU. | Worst sample cost 1.8 ms. | 2026-10-14 | CP-3649 |
| Evidence-only partition | Evidence root on its own ext4 partition (`noatime`); tooling, venvs, models, policy and build trees moved to `W/{venvs,models,so101-policies,so101-build,so101-tools}`. | Copy 250.85 GB in 8 min 35 s; REG tree 341 GiB to about 261 GiB after the move-out; checksum dry run printed nothing. | 2026-10-18 | CP-3727, CP-3728; `9682307da`, `57aeb94f0` |
| Template authoring checks | Template self-checks use their own fixtures and read the install from the gate directory (`build-root.txt`). | Not measured. Removes the dependence on historical evidence. | 2026-10-16..18 | CP-3707, CP-3727 |

### Images and containers

| Item | What changed | Measured effect | Date | Evidence |
| --- | --- | --- | --- | --- |
| Container campaign restructuring | Container shards with private Worker control, task-id based control and cleanup, native stack reuse between cases. | EXP-581: first complete container collection, 8 of 8 VALID. | 2026-10-12..13 | CP-3631; `1b926731c`, `5a8c58934` |
| Shard image can host the processor | The same shard image runs the phase-2 processor; the entrypoint admits `campaign_processor`. | Not measured. | 2026-10-15 | CP-3673; `c939ed3a5` |
| Image build | Scoped build cache fetches missing locked web dependencies; inference base resolved by tag with a digest guard; build contexts prepared from tracked files. | Shard 155.6 s and inference 59.8 s (`4b187eee1`); 396.5 s and 66.3 s with the vendored controllers (`3654ec80f`). | 2026-10-13/14 | CP-3643, CP-3654; `0184c017f`, `5be21fe42` |
| Shard contract mount | The qualification contract is mounted into the shard so its spec validates at eight workers. | Fixed all eight shards refusing their spec at start (EXP-588). | 2026-10-14 | CP-3647; `1c47eab03` |

### Unsure or unmeasured

- Dates for the 2026-08 and 2026-09 items come from the last commit of each ledger file; the ledgers give no single completion date.
- Gate v3 has no ledger entry that introduces it; its description is inferred from CP-3727 ("same checks as v3") and the skip rule in CP-3723.
- Batch d and e sizes were added by the coordinator from their plan files (`R/evidence-deletion-20261018d`, `R/evidence-deletion-20261018e`); batch h is taken from open item 5.
- The recording cap was tried at 6 and 8 (EXP-612..614) and set back to 4 (CP-3712); the row records the mechanism and the qualified cap.
