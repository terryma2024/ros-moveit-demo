# Implementation plan: phase-1 delivery fix and in-campaign retry

Design: `docs/superpowers/specs/2026-10-16-so101-act-delivery-fix-and-retry-design.md`. Status: CONFIRMED by the human on 2026-10-16 ("确认执行"); executing.

The plan follows the project rules:
- The execution model is Claude Sonnet 5.5, one writer at a time; Opus reviews each task.
- No `src` edits while a collection run is active.
- No data rule or threshold changes.
- Tests fixture their own data and never read `/data/work` files.
- The Host gate runs on a quiet host.

## Task 1 — Fast DDS profile

1. Add `src/so101_demo_py/config/dds/fastdds-collection.xml`: a default publisher profile with `<times>` set to `heartbeatPeriod` 20 ms and `nackResponseDelay` 1 ms. Start from `REG/diag-delivery-20261016/scripts/hb.xml`.
2. Install it through `src/so101_demo_py/CMakeLists.txt` or `setup.py`, following how `config/` is installed today.
3. Set `FASTRTPS_DEFAULT_PROFILES_FILE` to the installed path for every collection ROS process: shard, Teacher and processor. Find the single place the instance environment is built (`runtime/act_instance/identity.py` `instance_environment` and `runtime/container_campaign/launch.py` `build_container_argv`). Use the in-image install path, not a Host path. Do not set `RMW_FASTRTPS_USE_QOS_FROM_XML`.
4. If the image build copies `config/` already, no Dockerfile change is needed. Check `prepare-image-build.py` sources and the image allowlist.
5. Tests:
   - the environment contains the variable with the installed path for all three roles;
   - the XML parses and sets exactly those two values;
   - the launch argv test is updated.

## Task 2 — Recorder-only stall diagnostic

1. In the phase-1 delivery diagnostics (`delivery_diag.py` and the probe), compare per topic the probe receipt with the recorder receipt for the same message.
2. Emit `RECORDER_ONLY_STALL {topic_count, gap_ms, first_stamp, …}` when the recorder lags the probe by more than 100 ms.
3. Rate-limit the log. It is diagnostic only: no verdict, no raise.
4. If the recorder receipt is not observable live, emit the comparison post-hoc at task seal from the bag index and the probe trace, bounded in time.
5. Tests with synthetic traces.

## Task 3 — Config key and time budget

- **`runtime/inference/config.py`:**
  - Add `retry_invalid_max_rounds`, an int from 0 to 3, with its own limit entry, in `_OPTIONAL_LIMITS`.
  - Comment that it is outside the controlled identity.
  - Refuse `bool`.
- **`container_campaign/processing_limits.py`:**
  - Add `retry_invalid_max_rounds(config)`.
  - Add `retry_round_plan(config, *, now_s, total_deadline_s, scene_count, worker_count, processor_count, observed, runtime)`. It returns `fits`, `reason`, `available_s`, `needed_s`, `recording_deadline_s` and the components, as in the design.
  - Fallbacks come from the runtime hard timeouts and `processing_task_timeout_s`.
  - The verification reserve is respected. `collect_timeout_s` does not apply to retry rounds.
- **Tests:** `test_phase_limit_config.py` and `test_processing_limits.py`.

## Task 4 — Wave plans and the coordinator reopen

- **`act/parallel_collection.py`:** `plan_campaign_waves(…, first_wave_index=0, recording_round=0)`. Add the key `recording_round` only when it is non-zero. Round-0 plans must stay byte-identical.
- **`container_campaign/coordinator.py`:** `reopen_dispatch(previous_reason)` clears only the phase-1 deadline stop reason.
- **Tests:**
  - plan bytes for round 0 unchanged;
  - retry plans start at `first_wave_index`;
  - reopen is refused for any other reason.

## Task 5 — Processing scheduler across rounds

In `container_campaign/processing_scheduler.py`:
- `run(rows, *, deadline_s, round=0, host_dir=None)`.
- Admit processor slots only on the first run and keep them. Later runs use min(count, admitted).
- Keep the `_Worker` objects so launch generations keep rising.
- One `ProcessingJournal` per round under `host_dir`.
- The processing attempt number continues per scene. The first attempt in a round is 1 plus the attempts made earlier, and attempt counts are relative to the round.
- The TASK_ID check covers the new range.

Tests in `test_processing_scheduler.py`:
- a second run does not re-admit;
- generations continue;
- the journal goes to the round directory;
- proc numbers continue;
- round-0 behaviour is unchanged.

## Task 6 — Combined proof, campaign result, frozen index

- **`container_campaign/processing_verifier.py`:**
  - `verify_processing(…, host_dir=root/'host')`, unchanged otherwise.
  - New `verify_rounds(root, rounds, scene_ids, …)`:
    - round 0 runs over all scenes; round r over its candidates;
    - check cross-round proc-number continuity;
    - the final entry per scene is the latest attempt in PROCESSED or FINAL_AT_PHASE1;
    - FAULT or MISSING retries are listed but do not supersede;
    - output is today's document plus `rounds` and per-scene `recording_attempts`;
    - counts and missing evidence come from the final entries.
- **`container_campaign/result_verifier.py`:** `build_frozen_index` emits schema 3 only with rounds. `collected_tasks` covers every attempt, with `recording_round`, `wave_index` and `final`. `committed_episodes` holds only the final attempt. Without rounds the output is byte-identical.
- **`build_campaign_result`:** pass `rounds` through.
- **Tests:**
  - `test_processing_verifier.py` and `test_owner_combined.py`;
  - export: a schema-3 index with a retried scene resolves to the final attempt (`act/test_act_bundle_processed.py`);
  - regression: the stored two-phase qualification fixture in `act/test_collection_qualification_two_phase.py` recomputes byte-identically.

## Task 7 — Owner round loop, admission and CLI

- **`container_campaign/owner.py`:**
  - Refuse retry on the qualification plane (`CAMPAIGN_RETRY_QUALIFICATION_FORBIDDEN`) and without a scheduler (`CAMPAIGN_RETRY_REQUIRES_PROCESSING`).
  - Extract the wave loop into `_record_waves(plans, round)`. It times each wave and tracks the next wave index from the launcher, not from `len(plans)`.
  - `_finish_phase1(round)` and `start_phase_two(round)` write the per-round files.
  - The monitor enforces the phase-1 deadline only while recording.
  - Add `_reopen_recording(deadline)`.
  - The retry loop follows the design: candidates; skip reasons NO_CANDIDATES, DISPATCH_STOPPED, RETRY_ROUND_DOES_NOT_FIT_DEADLINE and RETRY_ROUND_DISK; an infrastructure error in a retry wave gives ABORTED; `host/retry-round-<r>.json`.
  - Combine through `verify_rounds` when rounds are configured, and through today's path when not.
  - `result['retry']`.
- **`unified/admission.py`:** refuse a nonzero `retry_invalid_max_rounds` on the qualification plane.
- **`cli/act_collect_parallel.py`:** add `retry_rounds` and `recovered` to the summary. Exit codes come from the final faults only.
- **Spec amendment:** a note in the 2026-10-15 design that INVALID scenes can now be re-recorded in a formal-only retry round.
- **Tests:**
  - `test_owner_phase1.py`, `test_owner_phase2.py`, `test_phase1_deadline_gating.py`, `test_owner.py`, `test_task_coordinator.py`;
  - `src/so101_teleop/test/unified/test_container_collection_operation.py`;
  - `cli/test_container_task_campaign_integration.py`;
  - the new owner cases listed in the design.

## Task 8 — Templates (outside the repository)

- `REG/act-templates/w8f-formal`: `--retry-invalid-max-rounds` (0 to 3). The validation runs the real loader. The time projection adds retry rounds.
- `w8d`: the option too, for debug.
- `w8q`: refused.
- `w8d`: also report the class A to C counts with the diagnosis scripts after a run.

## Task 9 — Gate, images, runs

1. Host gate on a quiet host (`R/fast-gate/run-host-gates-fast.zsh --serial`).
2. Rebuild the images (`build_images.zsh`).
3. EXP-616: debug, 16 scenes, cap 8, retry 0, compared with EXP-614 and EXP-615 delivery classes.
4. EXP-617: qualification, 40 scenes, cap 8.
5. EXP-618: formal 70, `--retry-invalid-max-rounds 2`, `--batch-hard-timeout-s 9000` or more if the projection asks.
6. A ledger entry for each step. Push the branch after each recorded step.

Stop and report to the human if:
- EXP-616 does not show class A removed;
- the qualification is NOT_QUALIFIED;
- a gate fails twice on a quiet host.
