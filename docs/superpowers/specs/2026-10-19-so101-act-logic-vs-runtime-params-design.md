# SO-101 ACT: logic parameters vs runtime parameters — design and plan

Status: CONFIRMED by the human on 2026-10-19 ("重录轮数算R。其他都是“是”"): Q1, Q3, Q4 and Q5 as recommended; Q2 answered as R
(see below). Code changes start only after EXP-625 has finished (human, 2026-10-19: "那等phase 2完成再改代码").

## The principle (human, 2026-10-19)

"运行期的环境参数 和 改变逻辑结果的参数 需要分管理。改变逻辑结果的参数，需要做sha校验，保障输入和产物的匹配。但是运行环境参数，比如并行数等，无需做sha校验和限制。"

The human also asked for a pause point between phase 1 and phase 2. After phase 1, it should be possible to stop, change code or parallelism, and then run phase 2.

## Why now

- EXP-625 could not raise phase-2 parallelism from 6 to 12 on a 64 GB host. `processor_count` sits in the run's sha-bound campaign config, and phase 1 and phase 2 are one process with no pause point.
- Two of the recent failures came from runtime material being frozen or pinned:
  - **EXP-624 verify.** A frozen runtime script hard-coded a logic value, the contact fingerprint. The template fix could not reach the frozen inputs copy.
  - **EXP-625 authoring.** A template checked a source-text pattern, and a harmless refactor broke it.
- The reviews also found the reverse problem: logic that no hash covers.
  - The Teacher model weights and score threshold are not in the qualification identity.
  - The optimiser constants (gradient clip, weight decay, AdamW, ACTConfig defaults) are hard-coded and in no training hash.
  - The source commit is not bound into the policy bundle.

## Three classes

| Class | Meaning | Binding |
| --- | --- | --- |
| **L** (logic) | Changes produced data, classification (VALID/INVALID), episode content, the trained policy or a metric. | Frozen, sha-bound to inputs and products. It is in the cross-run identity wherever two runs must agree, for example qualification → formal. |
| **R** (runtime) | Changes only speed, resource use, logging or scheduling. A proof shows results are identical. | Not frozen and not hashed. Only type and physical-limit sanity checks apply, such as count ≥ 1 or ≤ the loader maximum. The value used is recorded in the run's provenance log for audit but is never compared. It can change between runs and between phases. |
| **RO** (runtime with outcome risk) | Runtime by nature, but higher load is known to change outcomes. Examples: RTF below `rtf_min`, Teacher timeouts, recorder backlog. CP-3712 showed recording cap 8 raised INVALID rates. | Not frozen. Recorded in the qualification report. A formal run must stay within the qualified envelope: no more load than qualified, and no less spacing. Moving inside the envelope needs no new qualification. |

A parameter moves from L to R only with a proof that results do not change, for example a byte-identical differential.

## Inventory and target class (from the 2026-10-19 reviews)

### Collection

| Parameter | Today | Target |
| --- | --- | --- |
| `processor_count`, `processing_max_attempts`, `processing_task_timeout_s`, `processing_reserve_s`, `collect_timeout_s`, `process_timeout_s`, `verification_reserve_s`, `batch_hard_timeout_s` | campaign-config (whole-file sha, one run only) | **R**. A phase-2 deadline or attempt limit only turns a scene into FAULT or MISSING (coverage), never VALID ↔ INVALID. Proof for `processor_count`: reprocess the same phase-1 recordings with 1 and 6 processors and require identical `processed_result_sha256` per scene. |
| `max_concurrent_recordings`, `max_tasks_in_flight`, `min_assignment_gap_s`, `--worker-count` | campaign-config / CLI; worker count fixed at 8 for formal | **RO**. They go into the qualification report. A formal run requires cap ≤ qualified cap, in-flight ≤ qualified, gap ≥ qualified gap, and the worker count equal to the plane's (8). |
| `retry_invalid_max_rounds` | campaign-config, treated as scheduling | **R** (human decision). Only a scene with Teacher PASSED and data INVALID is re-recorded (`retry_candidate`), so a retry recovers data lost to recording noise. It does not turn a physical failure into a success. Every committed episode passes the same rules. Like the phase-2 deadlines, it affects coverage only. For audit, the index still records the round each committed episode came from, but this is never compared. Qualification keeps no retry. |
| Teacher `model.{weights, score_threshold, classes, model_id}` | campaign-config only; **not in the identity** | **L**, added to the controlled identity. This closes a gap. |
| Teacher `{instances, torch_threads, torch_interop_threads, max_inflight_requests, queue_timeout_s, inference_timeout_s, max_frame_bytes}` | campaign-config, must equal qualification | **RO** (throughput, and timeouts can fail an episode). Envelope rule: timeouts ≥ qualified and in-flight ≤ qualified. |
| `parallel_batch_act_offline.yaml` | whole file in the identity | **Split.** Perception and sync acceptance stay L: `max_frame_age_s`, `max_rgbd_skew_s`, `max_tf_skew_s`, yolo model and imgsz, grounding/SAM thresholds, device, cpu fallback, clock windows. The rest becomes an R file: heartbeat, lease, ack, phase and recovery timeouts, broker queue and inflight, yolo/SAM queue timeouts, `start_guard`. `executing_hard_timeout_s` is RO. |
| `parallel_collection.yaml` | whole file in the identity | **Split.** Stays L: `recorder.sample_rate_hz`, `lossless`, `business_retry_count`, `resume_requires_identical_business_hashes`, qualification worker counts. Becomes RO: recorder queue watermarks and hold (overflow breaks the lossless gate), and `max_wave_size`. Becomes R: `max_infra_attempts` and `telemetry.period_s`. |
| `episode_recorder.yaml` | frozen | `max_duration_s` is L. Inbox capacity, poll and timeouts are R. Physics spool backlog and receiver lag are RO. |
| `teacher_execution_policy.yaml` | frozen | Motion parameters are L. `execution_deadline_s` is RO. |
| `endpoint_pose_development_runtime.yaml` | frozen | path, sync, safety and `hard_stops.rtf_min` are L. `disk_free_min_bytes` is R. |
| Images, rig profile, source, scene manifest, contact fingerprint, gpu_uuid | identity / frozen | Unchanged. |

### Training, eval and rollout

| Parameter | Today | Target |
| --- | --- | --- |
| `num_workers` | in `config_sha256` (lease, state, bundle) | **R for values ≥ 1**: the sampler and model RNG live in the main process and `__getitem__` is deterministic. **0 is forbidden**, because a non-persistent iterator takes an extra generator draw per epoch and so changes the order from epoch 2. Proof: index batches of epochs 1–3 are equal for 8 and 16 and differ for 0. |
| `log_interval_steps` | in `config_sha256` | **R** |
| `validation_interval_steps`, `validation_samples` | in `config_sha256`; `last_validation` is written into the bundle's normalization block | **R** for the policy. `last_validation` moves out of the hashed bundle body into `training-log.json`. Proof: two intervals give the same `policy_sha256` under deterministic algorithms. |
| Export `--workers` | not hashed | R (unchanged). Proof: export with 1 and 16 gives the same `export-manifest.json` sha. |
| Gradient clip, weight decay, optimiser, full ACTConfig | hard-coded, **in no hash** | **L**, written into the hashed config (the effective values, including the defaults the code applies). |
| Source commit | only `run-context.txt` (HEAD plus dirty count) | **L**. The commit and a clean tree are required, and the commit is bound into the bundle. |
| `config_sha256` serialisation | two different serialisations for one dict (lease vs bundle) | One canonical function. The v1 values stay readable. |
| `runtime.yaml`, `rollout.yaml` | whole-file bytes (comments included) in the eval freeze and rollout identity | **Split.** L: thresholds such as `no_motion_threshold_rad` and `world_max_age_s`, and the ordering rules. RO: `request_timeout_s`, `max_reply_age_s`, `submit_lead_s`, `accept_timeout_s` (they decide `PREFIX_LATE`). R: device and queue depth. Hash the parsed L keys, not the file bytes. |

## Mechanism

1. **Two documents per run.**
   - A logic document holds every L value, frozen, with sha256s, in the identity where required.
   - A runtime document holds every R and RO value. It is written at launch and recorded as used, never compared.
   - RO values are copied into the qualification report, and formal admission checks them against the envelope.
   - Config files that mix both classes are split into `*.logic.yaml` and `*.runtime.yaml`. Each logic file keeps its own identity hash. Runtime files are passed on the CLI.
2. **Phase boundary.**
   - `act_collect_parallel --stop-after-phase1` records phase 1, proves every shard stopped, runs syncfs, writes a phase-1 completion record (bound to the run's logic document and inputs) and exits.
   - A new `act_process_parallel` runs phase 2, the retry rounds and the index on such a run. It takes a fresh runtime document, for example 12 processors. It refuses a run without a clean phase-1 record, a different logic document or images, or a run already processed.
   - The images stay L, bound by digest from the logic document. Changing code between the phases therefore needs a new image only if the processor image's code changes. That is a logic change, and the run refuses it unless the human starts a new run.
   - "Change code, then run phase 2" is only allowed for code outside the bound images and logic: host-side scheduling, logging, parallelism.
   - The default (no flag) stays the one-process flow.
3. **Templates.**
   - **Freeze only logic.** `sha256sums.txt` covers the logic files and is actually verified by `run-*.zsh` and by the formal author before use; today nothing checks it.
   - **Runtime tooling is not frozen.** This covers run, verify, build-report, summarize, readback and log savers. It is taken from the template at run time, with its hash logged.
   - **No logic values in scripts.** verify-report reads the proposal from `params.json`, and validate checks that.
   - **No source-text pattern checks.** Each one becomes a named behavioural test in the repo (admission refusal codes, the `prepare` payload default, the `inspect` parser, the coordinator's RecordingGate arguments). The template only checks that the gate's results contain those tests as passed.
   - **No restated constants.** The 9000 s runtime timeout, the disk floor and the memory default are read from their source.
   - **Disk projection becomes an operator option.** `BYTES_PER_SCENE` leaves `rig.INFO`, the logic record.
   - **Other fixes.** `*.orig*` files are excluded from the copy. verify and build-report write versioned outputs (`-r2`), so a fixed tool can re-run without hand-named files.
4. **Compatibility.**
   - Sealed data, TRAIN-001, the EXP-620/622 index and their identities stay valid; v1 readers stay.
   - The new identity is schema version 2.
   - A real-data differential readback over the 101 merged-v2 entries must stay byte-identical.

## Decisions (recommended answers marked)

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Treat RO as an envelope (formal ≤ qualified load) instead of hashing it? | Yes. |
| Q2 | Move `retry_invalid_max_rounds` to L and report it with the dataset? | Answered: **R** (human, 2026-10-19). The per-episode round stays recorded in the index for audit. |
| Q3 | Add the Teacher model (weights, threshold, classes) to the qualification identity? | Yes. Existing qualifications stay valid under v1. |
| Q4 | Forbid `num_workers = 0`? | Yes. |
| Q5 | TRAIN-003: run it on the current code, right after the EXP-625 seal, without waiting for this refactor? | Yes. Its identity is v1 (`num_workers` 16 in the hash), which is harmless. The refactor lands for the next collection and training. |

## Plan (Sonnet writers one at a time, Opus review; tests first, fixtures only)

1. **Proofs first** (no code change):
   - processor count 1 vs 6 on EXP-625 phase-1 recordings: identical `processed_result_sha256`;
   - DataLoader index batches with `num_workers` 8, 16 and 0;
   - export workers 1 vs 16.
2. **Collection split.** Logic and runtime documents; split config files; RO envelope in the qualification report and formal admission; retry rounds in R, with the per-episode round recorded in the index; Teacher model in the identity; identity v2 alongside v1.
3. **Phase boundary.** `--stop-after-phase1` and `act_process_parallel`, with tests for every refusal.
4. **Templates.** Logic-only freeze actually verified, unfrozen runtime tooling, behavioural tests replacing source-text checks, no restated constants, disk projection as an option, `*.orig*` excluded, versioned outputs.
5. **Training.**
   - Runtime block (`num_workers` ≥ 1, log and validation intervals).
   - Optimiser constants and the effective ACTConfig in the logic hash.
   - Source commit bound into the bundle.
   - One canonical `config_sha256`.
   - `last_validation` out of the hashed body.
   - Split `runtime.yaml` and `rollout.yaml`.
6. **Gate and proof.**
   - v4 gate green.
   - 101-entry differential identical.
   - One debug run with `--stop-after-phase1`, then `act_process_parallel` with 12 processors: same outcomes as an all-in-one run of the same inputs.
