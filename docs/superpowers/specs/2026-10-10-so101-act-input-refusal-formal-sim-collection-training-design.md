# SO-101 ACT: worker input refusals, sim formal collection, and the LeRobot training path

Status: design revision 2, 2026-10-10. The independent review (fresh Opus, read-only) returned FAIL. Revision 2 handles each finding as follows:

- §1 rewritten: findings 3, 5, 6, 11 and 12.
- §2 (item 4) is suspended pending two user decisions (findings 4 and 7). Its required rework is listed in §2.0: findings 1, 2, 8, 9 and 13.
- §3 rework listed in §3.0: findings 9 and 10.
- §4 reordered: finding 14.

Phase A (§1) may proceed.

Original status: design, 2026-10-10. Owner: root (Claude Opus 5.5). Execution: one Claude Sonnet 5.5 executor (AGENTS.md rule for a Claude coordinator). Ledger: `docs/experiments/so101-act-data-experiment-ledger.md`, from CP-3520.

The user asked (2026-10-10) to solve three open items from CP-3518:

- **Item 1.** A worker input refusal (`STALE_RGBD` and similar) surfaces as `TEACHER_USER_STOP` and leaves no sealed result.
- **Item 3.** The trainer adapter does not exist, and the training view and the runtime disagree on observation keys.
- **Item 4.** Collection must run in a mode whose episodes can be exported for training.

All facts cited below come from the read-only research of 2026-10-10. Its file:line evidence is summarised in the ledger at CP-3520.

## 0. Decisions taken in this design

The user authorised taking the recommended option at decision points (CP-3394). The decisions are:

| # | Decision | Alternative rejected | Why |
|---|---|---|---|
| D1 | An input refusal before motion is committed through the existing D8f manifest-free form (`INDETERMINATE` / `UNCONFIRMED` / data `INVALID`) and does not get a new status value. | A new `REFUSED_INPUT` execution status. | The v3 design §5b fixes the status sets. D8f already exists, is accepted by the result store, and is tested. Only its producer is missing. |
| D2 | The refusal reason is carried as `act_data_reason = "TEACHER_FENCED_BEFORE_MOTION:INPUT_UNAVAILABLE <boundary> <message>"`. | A new reason field. | It keeps the existing prefix that validators and the result store already accept. |
| D3 | `act_first_episode run` returns a distinct rc 5 for a committed pre-motion input refusal. | Reuse rc 1 or rc 4. | rc 1 means a Teacher failure and rc 4 means nothing was sealed. Wrappers and tallies must tell the three apart. |
| D4 | Sim formal collection keeps the mode name `formal`. It adds a closed scope field `target_provider ∈ {head_search_v1, fixed_head_domain_v1}`. `fixed_head_domain_v1` replaces the Head Search qualification with a per-candidate fixed-head visibility qualification. | A new trainable mode name; or waiting for Head Search. | Head Search calibration is a separate program on antzb (nonhead design §9). The export path, `TRAINABLE_COLLECTION_MODES` and the identity checks already key on `formal`, and the provider field keeps the two datasets distinguishable. |
| D5 | The domain is the CP-3479 proposal: x ∈ [-0.12, 0.12] m and y ∈ [-0.32, -0.20] m, minus the disc of radius 0.07 m around the ring centre (-0.08, -0.25), with yaw 0. The place target is fixed (the current frozen end target). | A larger domain. | It is the only domain with a perception study behind it (300/300 single detection, p95 0.61 mm). |
| D6 | The carry-tilt "simulation gate" (CP-3394 for v2) becomes v3 telemetry. Per-episode tilt and force are already in `teacher_process_summary_v1`, and oracle-flagged episodes are excluded at export (CP-3505). | A separate pre-campaign tilt sweep. | v3 moves process judgements out of runtime gates (CP-3501). Exclusion at export already protects the dataset. |
| D7 | Training uses a new venv built from `config/act/requirements.lock` (torch and lerobot 0.6.1 pinned there) under the evidence root. It does not use the test venv. The ordinary pytest gate stays torch-free; training tests skip without torch and run in a separate training gate. | Installing torch into the test venv. | It keeps the ordinary gate fast and unchanged, and the lock already pins the stack. |
| D8 | The observation key mapping `head_png → head` and `wrist_png → wrist` (PNG path → decoded uint8 HxWx3 RGB) lives in one table in `adapters/act/lerobot.py`, used by the dataset loader only. The runtime keys stay `head` / `wrist`. | Renaming the recorder keys. | Sealed episodes and validators already fix `head_png` / `wrist_png`, so renaming them would invalidate every sealed episode. |

## 1. Item 1: worker input refusals become committed results

### 1.1 Today

- `parallel_batch/worker.py:_run_authorized` runs `inference_snapshot`, then `broker.request_model`, then `runtime.admit_pose`. Any exception there reaches the generic `except` (`worker.py:1275-1287`), which calls `_safe_stop(lease, action_may_have_started=False)`.
- That builds an `AttemptStatus.INVALID` decision. `result_store.seal_attempt` rejects it (`RESULT_TERMINAL_INVALID`), so `stopped_reason` becomes `TERMINAL_ACK_FAILED`, nothing is sealed, and `act_first_episode` ends with `RESULT_RUN_CONTEXT_INVALID` (rc 4).
- The Teacher was already started (recorder first, then the consumer) and is waiting in `get_one`. SIGINT turns into `TEACHER_USER_STOP`, and no manifest is written because `execution` is still `None`.
- The D8f path (`TeacherPreMotionRefused` → `_pre_motion_decision`, `worker.py:912-927`, `1278-1282`) commits the manifest-free form, but nothing raises `TeacherPreMotionRefused`.

### 1.2 Change (revision 2, after independent review findings 3, 5, 6, 11 and 12)

The cup pose is published to the Teacher only in `execute_expert` (`parallel_worker_runtime.py:1571`). Both boundaries therefore run after the start ACK and before the Teacher has an input, and `action_may_have_started=False` is truthful there.

1. **Closed input-availability allowlist.** It is fixed here and is not left to grep.
   - `request_model` raising `PerceptionError` whose message starts with `STALE_RGBD:` or `STALE_RGBD_OR_TF:` (`perception.py:191, 251`).
   - `request_model` raising `RuntimeError("BROKER_CANDIDATE_AMBIGUOUS…")` (`parallel_ros_runtime.py:607`).
   - The perception-terminal decision that `request_model` returns without raising (`parallel_ros_runtime.py:1344-1386`: no cup, all models rejected, `INFRA_ERROR`, `QUEUE_TIMEOUT`, `INFERENCE_TIMEOUT`). Today it flows through `admit_pose` into `execute_expert` and becomes an unsealable `RuntimeDecision` (`parallel_worker_runtime.py:1549-1559`). It is intercepted in `_run_authorized` before `admit_pose` is called. The reason is `PERCEPTION_TERMINAL:<disposition> <reason>`.
   - **Excluded on purpose.** These stay on today's generic, unsealed, loud path:
     - every other `PerceptionError`: identity, path, authorization, sequence and `PoseAdmissionCommitError` (`perception.py:30, 157-191, 363-443`);
     - every other `BROKER_*` code, such as `BROKER_GENERATION_CHANGED`;
     - `RUNNING_EVIDENCE_UNAVAILABLE`, an infrastructure fault reported in its own column.
2. **Commit only when the stop is proven.** A classified refusal becomes `TeacherPreMotionRefused`, and the D8f form is sealed, only if all of these hold:
   - `_safe_stop` returned `stopped` and `confirmed` true. Today those values are discarded at `worker.py:1276`.
   - The recorder is proven stopped: its process has exited and its stop stats are written.

   Otherwise the attempt keeps today's unsealed path and is quarantined, because a live bag must never be writing into a sealed result.
3. **Reason (D2), bounded.**
   - `act_data_reason = "TEACHER_FENCED_BEFORE_MOTION:INPUT_UNAVAILABLE <boundary> <message>"`. It is truncated to the existing 160-character bound (`worker.py:920`).
   - `failure_message` keeps up to 512 bytes, as today.
   - The original exception type is recorded in a new `failure_origin_type` field of `worker-run-results.json`, so `failure_type` no longer just says `TeacherPreMotionRefused`.
4. **Data side.** The recorder-first INVALID seal without QC is already accepted: `_grade_data` returns early for INVALID (`result_store.py:379-380`), and the verifier accepts `episode_seal_sha256=None` with QC NOT_RUN (`810-813`). A test proves this on a recorder-first pre-motion stop.
5. **Orchestrator rc 5 (D3).** The rc 5 branch is checked before the existing `result_status != PASSED` → rc 1 line (`act_first_episode.py:447`). It requires all of these:
   - the D8f Teacher pair;
   - `act_data_status = INVALID`;
   - QC NOT_RUN;
   - `export_eligible = false`;
   - the `INPUT_UNAVAILABLE` reason prefix;
   - a passing coordinator cleanup verification.

   Anything else falls through to rc 1 or rc 4 as today.
   - The live wrapper r15 (next to r14) treats rc 5 with a sealed result as readback-eligible and expects INVALID. rc 5 without a sealed result gives `NO_READBACK` and a non-zero exit.
6. **Teacher output.** The Teacher's own line stays `TEACHER_USER_STOP`. The committed result is authoritative, and tallies read the committed reason.
7. **Counting.** An input refusal is a non-PASS in the denominator, shown in its own column. `RUNNING_EVIDENCE_UNAVAILABLE` and other unsealed faults are shown as infrastructure.

### 1.3 Tests (RED first)

- **Allowlisted inputs.** For each allowlisted input (`STALE_RGBD`, `STALE_RGBD_OR_TF`, `BROKER_CANDIDATE_AMBIGUOUS`, and each perception-terminal disposition), with a confirmed stop: the attempt is sealed and committed in the D8f form. The reason has the bounded prefix, and `failure_origin_type` is the original type.
- **Unconfirmed stop.** The same inputs with `stopped` or `confirmed` false, or the recorder not proven stopped, are not sealed and are quarantined.
- **Excluded codes.** Each excluded code keeps today's behaviour: an identity mismatch, `PoseAdmissionCommitError`, `BROKER_GENERATION_CHANGED`, `RUNNING_EVIDENCE_UNAVAILABLE`, and an arbitrary `RuntimeError`.
- **After goal dispatch.** Errors after dispatch (`action_may_have_started=True`) are unchanged.
- **rc mapping.**
  - rc 5 for the committed input refusal.
  - rc 1 for a D8f result with a non-input reason (for example `TEACHER_CHANNEL_FENCED`).
  - rc 4 when nothing is sealed.
- **Recorder-first.** A recorder-first pre-motion seal passes the verifier and readback with QC NOT_RUN.

## 2. Item 4: sim formal collection (`target_provider = fixed_head_domain_v1`)

### 2.0 Revision 2: blockers and required rework (§2.1–§2.6 below are revision 1 and are superseded where this list conflicts)

**User answers (2026-10-10).**

- **U1: "Wait for Head Search".** `fixed_head_domain_v1` is rejected, and the nonhead formal rule stands. Phases B, D and E wait until Head Search calibration is merged; then this section is redesigned around `head_search_v1`.
- **U2: "Prepare a draft for me".** The root prepares an unsigned activation-receipt draft and the list of values to re-authorise, for the user to sign before any formal live run.

**User decisions required before Phase B (as asked).** These could not be taken under CP-3394.

- **U1.** The nonhead design (§3, §9, §10) says formal mode keeps requiring Head Search qualification and that formal admission is not relaxed. A `fixed_head_domain_v1` provider relaxes a user-approved rule. It needs explicit user approval, or an instruction to wait for Head Search.
- **U2.**
  - A formal run needs a `user_activation` contact-activation receipt, signed by the user. A plan or agent signer is refused (`contact_policy.py:150-164`).
  - The `user_empirical_default` values (`path_policy`, `placement_qc`, `rgb_skew`) were authorised for the diagnostic round only. They need re-authorisation for formal.
  - The anchor approval needs a formal kind bound to the frozen sample manifest and the qualification receipt.

**Rework once U1 and U2 are granted.**

1. **Capacity (finding 1).** D5's usable area is ≈ 0.0171 m². A 0.02 m pairwise gap saturates at 35–41 points, which is less than the 70 + oversample needed.
   - The fix: no pairwise gap within a split (or ≤ 0.01 m). The between-split separation is the only one `make_manifest` checks, at the 0.02 m `minimum_gap_m`.
   - The design states the capacity calculation, and a test proves the sampler reaches its target counts.
2. **Use the existing Task 10 pipeline (finding 2).** `make_manifest` needs all five `SPLITS` and refuses any candidate that fails a gate (`sampling.py:63-98`). Qualification therefore happens before the freeze:
   - The sampler emits an `act_candidate_source` document (`act/candidate_source.py`) with the five splits, rollout splits sampled from the same domain, and the qualification sets.
   - `act_formal_qualify` writes the existing reachability-report format (`adapters/act/reachability_report.py`), extended with the fixed-head perception check, and acts as the candidate port.
   - `cli/act_sample.py` then freezes only passing candidates.
   - Over-sampling happens at the source stage.
3. **Provider in the inputs manifest, not the scope (finding 8).**
   - Scope v1 stays closed and unchanged: seven sites re-derive it.
   - `target_provider` is added to the frozen inputs manifest (`_MANIFEST_OPTIONAL`, `first_episode_inputs.py:59`), so it is bound by `inputs_sha256`.
   - Export refuses formal episodes without a provider, refuses mixed providers, and records the provider in the export manifest.
4. **Export seams (finding 9a–c, e).**
   - A builder turns the per-run commit proofs into the single `{"committed_episodes": [...]}` index that `resolve_committed_episodes` reads.
   - `attach_episode_content` always verifies the content hash.
   - `export_dataset` re-derives `split` from the frozen sample manifest by `scene_id` and refuses a mismatch.
   - Frame digests go into the export manifest and are re-verified in `require_exported_dataset`.
5. **Acceptance (finding 13).**
   - Root review between the pilot and the full campaign; nothing is automatic.
   - Pilot: ≥ 10/12 VALID with QC PASS, independent readback of all 12, and export refusing a diagnostic episode in the same run.
   - The campaign stop rule also triggers on any rc 4 or `NO_READBACK`.
   - Tests check provider and mode refusals rather than the tautology "PASS + QC ⇒ eligible".

### 2.1 Today

- `cli/act_first_episode.py` accepts `--mode formal`, but `run` builds the same single `task_start` point as diagnostic mode.
- `collection_scope.require_scope` (which says Head qualification is required for formal) is never called.
- No domain sampler and no multi-point driver exist. `act/sampling.py` freezes supplied candidates with a minimum gap, and splits come from `SPLITS` / `COLLECTION_SPLITS`.
- `export_eligible` requires `formal` (`result_store.py:33-39`, `collection.py:8`).
- A formal run also needs a non-spot-check contact activation (`contact_policy.py:62-65`).

### 2.2 Scope and identity

- **Scope field.** The scope document gains `target_provider`. The closed enum is `head_search_v1` (not available yet: refused with `HEAD_SEARCH_PROVIDER_UNAVAILABLE`) and `fixed_head_domain_v1`.
- **`require_scope`.** It is wired into `run` and `prepare`. For `formal` + `fixed_head_domain_v1` it requires a bound domain-qualification receipt (§2.4) instead of Head qualification. For `formal` + `head_search_v1` it keeps `HEAD_QUALIFICATION_REQUIRED`. Diagnostic rules are unchanged.
- **Records.** The provider is recorded in the episode scope, the committed episode, the export manifest and the bundle `dataset` block, so a later Head Search dataset can never be silently mixed with this one.
- **Contact activation.** A formal run requires the non-spot-check contact activation. If no such activation exists for v3, the executor reports that, and the root decides before any formal live run. Inventing one is out of scope.

### 2.3 Domain sampler

- **Sampler.** `act/formal_domain.py` provides `sample_domain(config, seed) -> candidates`. It does seeded rejection sampling over the D5 domain, with a minimum pairwise gap (config `minimum_gap_m`, default 0.02 m) and yaw 0, and cup z from the frozen table height.
- **Split assignment.** Split is assigned in sampling order with the 50/10/10 train / validation / offline_test quota (Task 8 design), over-sampled by a factor (config, default 1.6) to absorb qualification drops.
- **Output.** The sampler outputs exactly the candidate schema `act/sampling.make_manifest` already accepts (`{xy, arm_q, search_start_rad, seed}`; `arm_q` and `search_start_rad` are the frozen initial arm and neck values). The freeze is therefore the existing `make_manifest`, with its separation checks.
- **Tests.** Determinism by seed, domain and disc bounds, gap, split counts, and that the output is accepted by `make_manifest`.

### 2.4 Per-candidate qualification (offline, plan-only, before any live run)

`cli/act_formal_qualify.py` takes the frozen sample manifest and the installed freeze, and runs these gates for every candidate:

1. **Reachability.** All task phases through the existing plan-only `task_reachability` path, with both `--ik-backend native` and `--ik-backend quik`. A candidate passes only if both pass every phase (the 14-gate set, `REACHABILITY_GATES`).
2. **Fixed-head visibility.** Render the head camera at the frozen neck angle with the cup at the candidate pose, and run the production broker perception offline (YOLO + R6 + z-clip `RgbdLocalizer`). It must give exactly one candidate, with xy error ≤ 1.0 mm against MuJoCo truth. The wrist view must contain cup pixels at the pre-grasp pose (the existing render path).
3. **Ring clearance.** Distance to the ring centre ≥ 0.07 m. This is redundant with D5 and kept as a check.

- **Receipt.** The output is `formal-domain-qualification.json`: every candidate with PASS / DROP and the first failed gate, the tool versions, and the freeze identity, with its sha256. That receipt is what `require_scope` binds (§2.2).
- **Freezing order.** Candidates are taken in manifest order. Each split keeps the first N passing candidates (50/10/10), and a split that cannot fill its quota is reported. It is never back-filled from another split.
- **Tests.** The gate logic with fake planners and perception, the receipt schema and digest, and the quota and ordering rules.

### 2.5 Campaign driver

`handoffs/.../tooling/formal-campaign-r1.zsh` (tooling under the evidence root, like the live wrappers) runs one installed freeze for the whole campaign. For each qualified candidate in frozen order it:

1. prepares the qualified inputs for that candidate (formal mode, `fixed_head_domain_v1`, initial target = candidate, final target fixed);
2. runs `act_first_episode run --mode formal --collection on`, with lifecycle FULL_RESTART;
3. runs the independent readback, with the same rc expectations as r15 (rc 0 VALID, rc 3 INVALID, rc 1 sealed ERROR INVALID, rc 5 input refusal INVALID);
4. appends one row to `campaign-index.jsonl` (candidate, split, UUID, rc, Teacher status, data status, QC, export_eligible, readback rc, reason).

- **No retries.** A failed point is final for that candidate. The driver moves to the next candidate, and the split takes the next qualified candidate in order. It never retries under the same identity.
- **Stop rule.** It stops on three consecutive identical failure codes, on any `SIM_INTEGRITY_*`, or on any cleanup failure.

### 2.6 Acceptance

- **Pilot.** 12 candidates (8 / 2 / 2):
  - Teacher end-to-end PASS ≥ 10/12, and every non-PASS is classified (input refusal, Teacher failure, infrastructure).
  - Every PASS + QC PASS episode is `export_eligible = true`.
  - `export_dataset` over the pilot succeeds, and the dataset manifest validates with `target_provider = fixed_head_domain_v1`.
  - Oracle-flagged episodes are excluded with `EXPORT_EPISODE_ORACLE_EXCLUDED`.
- **Full campaign.** The full 50/10/10 campaign follows automatically if the pilot passes. Its acceptance:
  - each split reaches its quota from qualified candidates;
  - every committed episode passes independent readback;
  - the campaign index and the export validate;
  - a telemetry report covers tilt, force and oracle flags across the domain (D6).

## 3. Item 3: the training path

### 3.0 Revision 2: required rework (supersedes §3.2–§3.5 where they conflict)

1. **Trainer input (finding 9d).** `train_act` hands the trainer the training view, which has no `episodes/` and no frames (`training.py:121`). The trainer reads `view/training-samples.json` and resolves frame paths against the exported dataset, whose path is recorded in the view's export manifest. Frame digests are re-verified on load.
2. **GPU owner lease (finding 9f).** `act_train` refuses to run without an `owner_factory` (`act_train.py:42-45`). The smoke run uses the existing CUDA owner lease (`act/training.py` owner gates), and the design for phase C names the factory the CLI uses.
3. **Closed training config (finding 10).** The config is closed and lacks `steps`, `learning_rate` and `batch_size` (`training_config.py:15`).
   - Extend the schema (config schema v2, v1 still readable) with these fields.
   - Bind `preprocessing_sha256`, all zeros today in `config/act/training.yaml`, to the D8 decode table.
4. **Normalisation (finding 10).**
   - State indices 6–7 (neck sin/cos) have zero std under a fixed head. Apply a std floor (config value) and record the floored dimensions in the bundle.
   - `LerobotPolicy.infer` must normalise the state and de-normalise the actions using the bundle statistics. It applies none today (`lerobot.py:94-102`).
   - Verify against LeRobot 0.6.1, whose normalisation lives in separate processors.
   - A test proves that a degenerate-std dimension stays finite end to end.

5. **Smoke acceptance without formal data (user decision U1 = wait for Head Search, 2026-10-10).** No exportable formal episodes will exist until Head Search lands, and diagnostic episodes stay non-exportable (`DIAGNOSTIC_EPISODE_NOT_TRAINABLE`). Phase C acceptance is therefore:
   - the ordinary gate (training tests skip);
   - the training gate under `train-venv`;
   - a GPU smoke run of 500 steps on a synthetic dataset produced by the real export code from synthetic committed episodes with real-size frames (the frame size of the sealed p10/p11 episodes). The bundle hashes must verify, the loss must decrease, and `build_policy_from_bundle` must predict finite 6-wide actions;
   - a read-only decode check: the D8 table decodes the frames of a real sealed p11 episode (no export), and the shape, dtype and state width match the config.

   The real-data smoke moves to after the first formal campaign.

### 3.1 Today

- `cli/act_train.py:_trainer` imports `adapters.act.lerobot.train_act_bundle`, which was never defined. `build_policy_from_bundle` (used by `act_inference_worker` and `act_offline_evaluate`) is also missing.
- `train_with_lerobot` has a different signature and an injected `train` callable that nothing supplies.
- Nothing produces the episode `content` that `attach_episode_content` / `export_dataset` read.
- Training-view rows carry `head_png` / `wrist_png` path strings, while `_as_batch` and `act/policy.py` need `head` / `wrist` uint8 RGB arrays.
- No usable torch or lerobot environment exists. The lerobot 0.6.1 wheel exists only in the uv cache, and the requirements lock is RESOLVED and pins it.

### 3.2 Content and export

- **Content source.** The sealed episode's recorder rows (`act/recorder.py:238-245`: observation `{sim_time_s, state, head_png, wrist_png}`, `action`, `audit`) are the content source. `attach_episode_content` resolves the sealed rows file of a committed episode (path bound by the committed evidence and verified by sha256). The whitelist (`act/bundle.py:training_content`) then drops `audit` and every non-whitelisted key, as today.
- **Frames.** `export_dataset` copies each referenced PNG into `<dataset>/episodes/<scene_id>/frames/`, hash-verified against the sealed frame digests. The rows then point at dataset-relative paths, so the dataset is self-contained. A missing or mismatched frame refuses export with `EXPORT_EPISODE_FRAME_MISSING` / `EXPORT_EPISODE_FRAME_DIGEST_MISMATCH`.
- **Dimensions.** State width 8 and action width 6 are checked at export against `act/training_config.py`, refusing with `EXPORT_EPISODE_DIMENSION_INVALID`.

### 3.3 Adapter

- **`train_act_bundle(config, dataset, output, *, requirements_sha256)`** in `adapters/act/lerobot.py` does the following:
  - It loads the training view through `act/training.load_training_samples`.
  - It decodes the PNGs through the D8 mapping table.
  - It computes normalisation statistics (mean and std of state and action) on the train split only and writes them into the bundle.
  - It builds a LeRobot 0.6.1 `ACTPolicy` from the `act/training_config.py` values (cameras head and wrist, state 8, action 6, chunk 10, execution prefix 1, no temporal ensembling, tail padding mask).
  - It trains for `config.steps` with AdamW on CUDA, saves `policy.safetensors`, and returns the bundle through `train_with_lerobot`, which supplies the real `train` callable.
- **`_trainer`.** `cli/act_train.py:_trainer` passes the requirements sha256, which it reads from the resolved lock it already validates.
- **`build_policy_from_bundle(root, device)`.** It verifies the bundle hashes and returns the existing `LerobotPolicy` through `policy_loader`, with the bundle normalisation applied.
- **Tests (torch-gated, `importorskip`).** The key mapping, the decode shape and dtype, train-only normalisation, a 3-step tiny training run on a synthetic 2-episode dataset (CPU) that writes a loadable bundle, and `build_policy_from_bundle` predicting finite 6-wide actions. Torch-free tests cover the export frame copy, the digests, the dimension refusal and the `_trainer` signature.

### 3.4 Environment (D7)

- **Venv.** Build `<evidence_root>/train-venv` with uv from `config/act/requirements.lock`, following the skill reference `python-dependency-install.md`. The executor verifies `torch.cuda.is_available()` and that the device is the RTX 5060 Ti (sm_120 support must be confirmed by a real CUDA op).
- **If the locked torch lacks sm_120 support.** The executor reports this and stops. The root decides on a lock update; there is no silent substitution.
- **Training gate.** The training tests run under `train-venv` with the same scratch and TMPDIR rule as the ordinary gate.

### 3.5 Acceptance

1. The ordinary gate is green, with the training tests skipping.
2. The training gate is green under `train-venv`.
3. A smoke training run of 500 steps on the pilot formal dataset on the GPU:
   - the bundle is written and its hashes verify;
   - the training loss at the end is below the loss at the start;
   - `act_offline_evaluate` loads the bundle through `build_policy_from_bundle` and predicts finite actions on the offline_test rows.

No rollout success is claimed.

## 4. Order of work

Revision 2 adds two phases:

- **Phase 0.** The user decisions U1 and U2 (§2.0), and the capacity calculation. Phase B does not start without U1 and U2.
- **Phase C′.** Phase C does not depend on U1 or U2, so it may proceed after A. Its end-to-end smoke (phase D) needs formal data.

| Phase | Content | Live runs |
|---|---|---|
| 0 | U1 and U2 from the user; capacity calculation (§2.0 item 1). | none |
| A | Item 1 (§1), tests, gate, commit; r15 wrapper. | none |
| B | Item 4 offline: scope and provider, sampler, qualification CLI, tests, gate, commit; run the qualification on a sampled manifest (pilot 12 plus the full oversample). | none (plan-only and render-only) |
| C | Item 3 code (§3.2, §3.3), tests, gate, commit; build `train-venv`; training gate. | none |
| D | New freeze (cycle-r7 on the new commit); formal pilot (12); export; smoke training (§3.5). | 12 |
| E | Full formal campaign 50/10/10, export, telemetry report. | about 70–110 (≈ 8–12 h) |

The rules from the previous rounds carry over:

- One executor writes at a time.
- RED → GREEN for every behaviour change.
- The ordinary gate passes before each commit, and nothing is pushed.
- There is one stack at a time and no retries under the same identity.
- The root reviews each phase result before the next phase starts.
- If formal contact activation is missing (§2.2) or torch lacks sm_120 support (§3.4), the run stops at that point and the root decides.

## 5. Out of scope

- Head Search (`head_search_v1`).
- Real hardware.
- Rollout evaluation of the trained policy.
- Vision-based collision detection (CP-3505 future work).
- The 5 mm systematic final-xy offset (CP-3518 open item 2).
