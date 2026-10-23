# SO-101 ACT two-phase collection: record everything first, process afterwards

Status: CONFIRMED by the human on 2026-10-15 ("确认执行"); implementation in progress.

## Why

Debug runs on 2026-10-15 (ledger CP-3663 to CP-3670) separated the causes of the INVALID episodes at eight shards. Each run used 16 scenes on eight shards.

| Run | Setting | VALID |
| --- | --- | --- |
| EXP-597 | Recording cap 4; other shards' offline processing free to overlap | 4 of 16 |
| EXP-598 | Recording cap 2 | 11 of 16 |
| EXP-599 | Recording cap 4; at most 4 tasks in flight, so processing cannot overlap recordings | 13 of 16 |

Disk IO was tested directly and is not the mechanism. This covers small-file writes, the per-file seal fsyncs and bulk writes (CP-3667, CP-3668). The main interferer is the offline processing that runs in a shard right after its recording, while other shards are recording.

Today one shard task does both halves:

1. Record. The Teacher drives the robot while a record-only `ros2 bag record` process writes the raw bag.
2. Process. `act_offline_episode` replays the bag through the live rules, writes and seals the episode, and runs the independent QC.

Recording needs low latency. Processing needs throughput. Because they share one task, they cannot have different resource policies.

## Human decisions (2026-10-15)

| # | Question | Decision |
| --- | --- | --- |
| — | Split into two phases | "能把采集和处理分成两阶段吗？先把在线采集都做完。再一起做离线处理。两者的资源策略也不一样。前者实时性高，后者吞吐量优先。" |
| 1 | Where phase 2 runs | Lightweight containers. |
| 2 | Phase-1 concurrency | Start with eight workers. |
| 3 | Phase-2 infrastructure failures | Retry automatically. |
| 4 | Time limit | One total limit for both phases ("ok"). Clarified: "可以指定每个阶段的时限" — each phase can also be given its own limit. |
| 5 | The inline record-then-process mode | Delete. |

## What does not change

- **Data rules.** Every data rule and threshold stays as it is: the 100 ms windows, loss and continuity checks, formal coverage, QC and seal format.
- **Data verdicts.** The processor already replays on a virtual clock using the receipt times stored in the bag. Its verdict therefore does not depend on when it runs.
- **Qualification.** The rule files, populations and pass counts are unchanged.
- **Control.** One-way control (start, assign_task, get_status, terminate) is unchanged.
- **Shard identity.** The fixed in-container identity applies as before: ROS domain 181, no namespace, and `--network none --ipc private`.

## Design

### Phase 1: collect (latency first)

- **Task.** A shard task now covers the Teacher plus the record-only bag and ends there.
  - The attempt seals with the existing `act_data_status = PENDING_QC` (`parallel_batch/dynamic_manifest.py:20`, already accepted by the verifier).
  - The Teacher fields (`status`, `teacher_execution_status`, `teacher_task_result`) are final at this point.
  - `export_eligible` is false until phase 2.
- **Recording receipt.** The sealed attempt holds:
  - `raw/` (bag, scene reads, record stats, pilot result);
  - the Teacher manifest;
  - inputs and lease;
  - a new `raw/recording-receipt.json` with the sha256 of every raw file, written after the bag closes.
- **No fsync of the bag during phase 1.** Writing the receipt reads the bag back through the page cache to hash it. After the last phase-1 container has stopped, the host makes the raw files durable with one `syncfs` before phase 2 starts.
- **Deleted from the shard task.** The inline call to the processor, POST_RECORDING, and the processing budget inside the lease.
- **Concurrency.** Eight workers, waves as today. The scheduling keys `max_concurrent_recordings`, `min_assignment_gap_s` and `max_tasks_in_flight` stay as optional parameters, absent by default.
- **Teacher outcomes.** Teacher faults, the pre-motion unreachable result and readiness faults behave as today.
- **Host verification.** After each wave the host verifies the phase-1 records as today, plus the receipt hashes.
- **End of phase.** The phase-1 containers stop and are proven stopped, freeing CPU and memory.

### Phase 2: process (throughput first)

- **Processor container.** A new role, `processor`, using the shard image (same provenance) with a new entrypoint `campaign_processor`. It has:
  - no GPU and no ROS graph;
  - `--network none --ipc private --read-only --cap-drop ALL`, as for shards;
  - read-only mounts of the phase-1 attempt directories it is assigned;
  - one writable output directory.

  The image already contains what the processor needs (`rosbag2_py`, `rclpy` serialisation, MuJoCo); this is checked by a readback during image validation.
- **Output.** For each scene, under `<run>/processing/<scene>/<attempt>-proc-<n>/`:
  - `episode/`, `recorder-result.json`, `offline-processor-report.json`, the QC report and topic-loss document;
  - a new `processed-result.json`, bound to the phase-1 `result_sha256` and to the receipt hashes of the inputs it read.

  The phase-1 `sealed/` directory is never modified.
- **Task.** One scene per task. The processor runs `act_offline_episode` with the same arguments as the inline path: bag, inputs, lease, scope, record stats, Teacher manifest and QC output.
- **Scheduling.** A queue of the scenes recorded in phase 1, served by `processor_count` containers.
  - The default is derived from memory: available memory divided by 3 GiB, capped at 12. The processor peaks at 2.2 GiB, and the QC child runs after it.
  - Processors are not CPU-limited, since nothing latency-sensitive runs in this phase.
- **Retry (decision 3).**

  | Outcome | Handling |
  | --- | --- |
  | rc 0 | VALID |
  | rc 3 | INVALID data; final, never retried |
  | rc 2 (refused configuration) | Fault, not retried |
  | Infrastructure failure: rc 4, a crash, a timeout, an output write error, a container that died | Retried in a new attempt directory `-proc-<n+1>` |

  The confirmed 2026-10-16 delivery-fix and retry design amends the INVALID row: a formal campaign may record an INVALID scene again when its Teacher passed and `retry_invalid_max_rounds` permits another round. The recorded data is not reprocessed to obtain a different verdict. Qualification runs still use first-attempt results.

  - Up to `processing_max_attempts`, default 3.
  - Every attempt and its reason are journaled in `host/processing-journal.jsonl`. Failed attempt directories are kept.
  - Task ids gain the `-proc-<n>` suffix.
- **Host verification.** After phase 2, `verify_processing` reads every `processed-result.json` and re-checks its bindings to the phase-1 result and receipt. It then derives the final per-scene data verdict.
  - The final per-scene record combines the phase-1 proof (Teacher) with the phase-2 proof (data).
  - `campaign-result.json` and `collection-index.json` are written from the combined records.

### Time limits (decision 4)

- **Total limit.** The campaign keeps one admitted total deadline, `batch_hard_timeout_s` (5400 s), covering both phases.
- **Optional per-phase limits.** Two optional campaign-config keys set each phase's own limit:
  - `collect_timeout_s`, measured from the campaign's admission;
  - `process_timeout_s`, measured from the start of phase 2.
  - The validation rule: each is an int above 0, and their sum must not exceed `batch_hard_timeout_s`.
  - The effective deadline of a phase is the earlier of its own limit and the total deadline.
- **Default without per-phase limits.** Phase-1 dispatch stops when the time left is below a reserved phase-2 budget, `processing_reserve_s` (default 1800 s).
- **At a limit.**
  - When phase 1 reaches its deadline, dispatch stops. Recorded scenes go on to phase 2; unrecorded scenes count as missing evidence.
  - When phase 2 reaches its deadline, scenes not yet processed count as missing evidence.
  - Missing evidence in either phase makes the run NOT_QUALIFIED.
- **Estimate.**

  | Phase | Basis | Time |
  | --- | --- | --- |
  | Phase 1 | 40 scenes, eight workers | 15–20 min |
  | Phase 2 | 40 × about 6 min over eight to twelve processors | 20–30 min |
  | Total | | 35–50 min |

### Qualification and formal plane

- **Gates.**
  - `evaluate_scene` reads the phase-2 locations through the combined proof: episode seal, records, QC report and topic-loss document.
  - The Teacher gate reads the phase-1 manifest, as today.
- **Recompute topology.**
  - The teacher service and the per-wave shard launches stay as today.
  - Processor launches are added: `processing-pNN-g<k>`.
  - Phase 2 recomputes from files: receipts, `processed-result.json` and the processing journal.

### Native single worker

- **Phase 1.** The native shard (`act_instance_native`) runs phase 1 unchanged.
- **Phase 2.** Phase 2 runs the same `campaign_processor` program as a host process under a native processor owner, mirroring the native shard owner. This keeps the rule that native single-worker logic equals the container logic.

### Admission, launch records and stop proof

- **Launch records and admission.** The registry, `teleop/unified/admission.py` and the cleanup verification gain the role `processor`.
  - Slots are `(campaign, pNN, generation)`.
  - A processor's stop proof is the container exit inspect plus the absence of its process tree. There is no shard stop receipt.
- **Mount rules.** `paths.build_role_mounts` gains an explicit read-only mount rule for the phase-1 attempt directories of the same run. Today it refuses anything under `wave-*`.

### Removal of the inline mode (decision 5)

Removed once the two-phase path is verified:

- `OfflineCollection._process`, `_memo_covers`, `read_processor_result`, the processing budget constants, `on_recorder_stopped`;
- the processing branch of `_finish_collection`;
- `recording_phase`, `TaskStatus.phase` and `_with_phase`;
- the POST_RECORDING branches of `RecordingGate`;
- all of `cpu_shares.py`, `ShardOwner.cpu_target`, and the `post_recording_cpu_shares` key (commit `9d6ff1df5`);
- `_data_verdict`, and the rc-3 branch of `classify_task_fault`, which moves to phase 2;
- `RESULT_DATA_REGRADED_AT_SEAL`.

About 24 test files are touched (survey of 2026-10-15).

## Risks and open points

1. **Eight simultaneous recordings without processing are untested.** EXP-599 had four with three INVALID. The first debug run after implementation is a full two-phase run with eight workers. Its phase-1 traces show whether eight concurrent recordings are stable. If needed, `max_concurrent_recordings` can be lowered without code changes.
2. **Bag size on disk.** About 2.2 GB per scene stays on disk until processing: 88 GB for 40 scenes, 154 GB for 70. About 1 TB is free.
3. **Late data verdicts.** Teacher results are known at the end of phase 1, but data verdicts only after phase 2.
4. **Seal semantics.** The phase-1 seal no longer contains an episode. Any code that assumes `sealed/episode` exists must read the combined proof instead. Gate readback, export and the bundle (`act/bundle.py`) are in scope.
5. **Retry and the Teacher.** An infrastructure retry in phase 2 must never re-run the Teacher. The design guarantees this, because phase 2 has no Teacher.
6. **macOS.** The native processor path should work on macOS. Verification on the mac-mini follows the existing practice and is out of the first delivery.
