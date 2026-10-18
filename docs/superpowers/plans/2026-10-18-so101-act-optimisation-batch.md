# SO-101 ACT optimisation batch after TRAIN-001: design and plan

Status: CONFIRMED by the human on 2026-10-18 ("都确认"); executing.

## Background

TRAIN-001 (ledger CP-3721) trained the first ACT policy on the merged 100-episode dataset.

Human decisions (2026-10-17/18):
- "先尝试跑通一次训练; 如果训练一次跑通，无需再采集数据，最后也同样做上述优化" — QC optimisation and verified parallel readback.
- "进度，指标，先记为待办".
- "如何查看SM Active多少，气泡比例 … 记为todo".
- "好，继续做上面3件事" — offline evaluation, closed-loop rollout, optimisation.

Measurements this plan builds on:
- **Offline evaluation** (REG/act-dataset-100-20261017/eval-001). Policy first-step MAE is 0.0143 rad. Repeating the current state scores 0.0019 rad; the train mean action scores 0.207 rad. The evaluator has no threshold and no chunk-wide metric.
- **Closed-loop rollout.** It cannot run today:
  - there is no policy-in-the-loop executor for the MuJoCo stack;
  - act_session execute requires a QUALIFIED calibration report that is never produced;
  - there are no rollout_validation / rollout_test scenes.
- **QC regrade profile** (REG/diag-delivery-20261016/qc-profile), one episode: 27.2 s wall, single-threaded Python CPU, peak RSS 1.7 GiB. I/O and JSON parsing are not the bottleneck. The hot spots are:
  - scene_association.decode_ros (the ROS message round trip, 6371 calls);
  - raw_physics_chunks.verify_raw_chunk, run twice per chunk under different memo keys;
  - native_endpoints.validate_world_source, run twice per source;
  - scene_association.source_model_data (Python isclose loops and MjData built per source);
  - the per-row slicing in recorder._decoded_pixel_sha256.
- **Phase-2 processor, per scene** (230 s): replay 79 %, QC 13 %, scan 7 %.

## Work items

### O1 — QC regrade speed-up, byte-identical verdicts

- **Changes, low risk first:**
  - Compute validate_world_source once per source. Key it by the document digest; the sequence check against the previous source is unchanged.
  - Rewrite the source_model_data comparisons with numpy. Keep the exact abs_tol semantics, the quaternion sign-flip rule and NaN behaviour, and reuse one MjData.
  - Strip PNG filter bytes in one vectorised pass.
  - Decode each ROS message once per verification and reuse its canonical bytes on both sides of every comparison. Refusal reasons stay unchanged.
  - Second step, only if the differential test stays green: run the standalone and continuity verify_raw_chunk passes once with a shared result, then vectorise the element checks.
- **No change to:** any rule, tolerance, reason code or output document.
- **Proof:**
  1. A differential test runs the old and new implementations on synthetic fixtures, including corrupt inputs for every refusal reason.
  2. A real-data differential readback runs over all 100 committed episodes plus frm-044 (expected refusal) and frm-101/102. Old and new verdict documents must be byte-equal. This check is read-only on the sealed roots and uses a source snapshot.
- **Target:** about 27 s to 12–15 s per episode (estimate). Combined with the existing 16-worker pool, a 100-episode readback falls to about 2 minutes.

### O2 — Committed implies exportable (collection and export rules agree)

- frm-044 was VALID and committed at collection. The export then refused it: EXPORT_EPISODE_ORACLE_EXCLUDED: INCOMPLETE WORLD_SEQUENCE_GAP, from bundle._teacher_oracle_exclusion.
- **Fix:**
  - Apply the same Teacher-oracle completeness rule in phase-2 processing, as a data verdict. The episode becomes INVALID with that reason, so it is not export eligible and becomes a retry candidate.
  - formal_postrun checks that every committed episode passes the export gates.
- **Scope:** this adds a refusal and lowers no threshold. It changes collection code and therefore the controlled identity, so a future collection needs new images and a requalification. No collection is planned now.
- **As implemented:** `teacher_process.bound_teacher_oracle_exclusion(qc_report, teacher_manifest)` is the one rule; `bundle._teacher_oracle_exclusion` (export) and `processing.grade_episode` (phase 2) both call it. A QC-PASS episode the rule excludes grades `INVALID` with `act_data_reason` `TEACHER_ORACLE_EXCLUDED: <flag> <phase>` (the export message minus its `EXPORT_EPISODE_ORACLE_EXCLUDED` prefix), QC `NOT_RUN`, no binding, `export_eligible` false. A manifest the rule cannot read or bind grades `TEACHER_ORACLE_UNVERIFIABLE: <export code>`. The host readback regrades a VALID verdict with the same function, so old VALID data the rule refuses (frm-044) is refused. The formal post-run templates check that every committed episode passes `bundle._verified_collection_uncached`.

### O3 — Training progress, validation metrics, bubble timing

- train_act_bundle logs every N steps (default 100) to stdout and to metrics.jsonl in the run directory:
  - step, loss, l1, kld, learning rate;
  - samples/s and an ETA;
  - DataLoader wait versus GPU compute per step (wait share = the bubble).
- Validation loss on the validation split every M steps (default 2000), on a fixed subset. The final bundle records the last validation loss.
- DataLoader num_workers becomes a training.yaml key (default 4, unchanged). TRAIN-002 tries 8.
- **No change to:** the training maths, the seed or the preprocessing hash.
- **Separately, needs sudo and network:** install Nsight Systems and sample 1–2 minutes of a training run with --gpu-metrics-devices to read SM Active and kernel gaps. The human is asked before installing.

### O4 — Phase-2 processor count (launch parameter only)

- With 64 GB, raise the template default --processor-count from 6 to 12.
- Verify at the next collection by watching min MemAvailable. No code change, no requalification (processor_count is outside the identity).

### O5 — Test-only flakes

Apply the proposed fixes in REG/diag-delivery-20261016/flakes/:
- test_native_timeout_is_bounded: wait for the detached state write.
- test_ready_instance_is_polled_during_barrier: raise the backstop of the fake clock.

### O6 — Closed-loop rollout (design first; implementation after a separate confirmation)

Decisions needed before any code:
1. **Rollout scenes.** Recommended: generate rollout_validation and rollout_test lists from new sampler seeds, disjoint from the 151 taken points. The triangle is full at 0.004 m, so either relax the separation for rollout scenes only (they are never trained on) or sample a slightly larger region.
2. **The calibration gate of act_session execute.** Recommended: the same treatment as collection (human ruling, ledger ~3467/3478). Bind the contact-policy activation receipt instead of a QUALIFIED calibration report, and say so in the evaluation record.
3. **The executor.** Recommended: reuse the collection shard image and stack in one container. Drive it with the policy through act_inference_worker or ActPolicyRunner instead of the Teacher, record the same bag, and judge success with the existing pick-and-place validation (the episode seal's pick_place_validation_success). Report the success rate per split.

O6 gets its own design document after this plan is confirmed.

### O7 — TRAIN-002 hyperparameters (config only)

After O3, train again with the ACT reference values:
- learning rate 1e-4 (backbone 1e-5);
- 50,000 to 80,000 steps;
- batch 16 if memory allows.

Report validation loss and offline metrics, plus the chunk-wide error added to the evaluator report.

## Order and execution

- **Order:** O5 → O1 → O3 → O2 → gate → O7. O4 is a template default edit. O6 gets its design in parallel.
- **Who:** Sonnet writers, one at a time; Opus reviews each item.
- **Gate:** the Host gate on a quiet host. Then the real-data differential readback for O1, then the training tests under train-venv for O3.
- **During runs:** no source edits while TRAIN-002 or a readback runs; evaluations and differential runs import a source snapshot.
- **Stop and report if:** a differential readback differs anywhere, or the gate fails twice on a quiet host.
