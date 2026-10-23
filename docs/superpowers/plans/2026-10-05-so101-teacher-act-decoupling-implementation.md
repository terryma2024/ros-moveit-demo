# SO-101 Teacher / ACT Decoupling: Implementation Plan

- Date: 2026-10-05
- Dispatch: `teacher-act-decoupling-20261005-1RmsJ3ZJ`
- Authoritative design: [`2026-10-05-so101-teacher-act-decoupling-amendment.md`](../specs/2026-10-05-so101-teacher-act-decoupling-amendment.md) (sha256 `0473db52c3915cbd87775ce1836f57681b48bf3a5ad228f2a05fa971cf5ce8e4`)
- Superseding amendment (2026-10-06): [`2026-10-06-so101-teacher-moveit-simplification-amendment.md`](../specs/2026-10-06-so101-teacher-moveit-simplification-amendment.md) (sha256 `9d54f821f4cca6ab234cb0f247fd06c1d94e9f6348928e0cfe49ae3641ae61c9`). The Teacher returns to MoveIt `ExecuteTrajectory` + standard JTC; the reservation/broker chain is removed; D8 is void. It wins on conflict.
- Revised by: [`2026-10-06-so101-teacher-moveit-simplification-implementation.md`](2026-10-06-so101-teacher-moveit-simplification-implementation.md) (R0–R8 replace §0, D3 broker rows, D6 broker wording, D7 dispatch receipts, D8, §2 and the §3 phases).
- Evidence root: `/data/work/so101-evidence/act-data/20260924-fbc25063-resume` (registered in the ledger)
- Dispatch directory, holding the inventory, the task snapshot and the receipt: `<root>/handoffs/teacher-act-decoupling-20261005.1RmsJ3ZJ/`
- Ledger: `docs/experiments/so101-act-data-experiment-ledger.md`. The main agent is the only coordinated writer.
- Executors: the ai-station tmux `claude` session. Plans, reviews and coordination are done by Opus 5.5. Source changes and gates are run by Sonnet 5.5 sub-agents serially; at most one source writer and one runtime executor at a time.
- Model note: AGENTS.md prescribes dst/GPT models. The user explicitly assigned this takeover to the existing Claude session and authorized this split. This is recorded as a model-rule limitation, not a silent substitution.

This plan replaces, from now on, the parts of the following plans that concern Teacher/Recorder/QC coupling, process-quality success, and data faults stopping the Teacher: the non-Head first episode, the R8/actual8x chain, and the related parts of Task8 and the measurement protocol. Other requirements in the old plans still apply. Every listed old design and plan carries a header link to the authoritative design.

## 0. Starting state (frozen)

- **Worktree and branch:** `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a`, branch `codex/so101-act-data-0917a`, HEAD `fa8c82b98`. There are about 311 dirty paths, all of them the takeover series' uncommitted work (CP-3100…CP-3261). Do not reset, clean, stash or checkout.
- **Last old-identity freeze:** F `nonhead-installed-freeze.PrwwT6Fv` and P `nonhead-qualified-inputs.bmIC0JsD` (CP-3262). They are not valid for the new identity and must not be relabelled.
- **Original endpoint revision (evidence dir only, not in repo docs):** `<root>/endpoint-pose-review-20261001.eouiFpWf/2026-10-01-so101-act-endpoint-pose-acceptance-design.md` and the implementation plan in the same directory. Their "endpoint as a QC success criterion" part is replaced by D2; the five tolerance values carry over. The evidence files are not edited.
- **Coupling inventory:** `coupling-inventory-raw-20261005.md` in the dispatch directory. It is a read-only scan with file:line references and is the input to §2.

## 1. Fixed decisions (taken under the design's authorization; not new user decisions)

### D1. Result model and versions

- **Child manifest:** `so101-dynamic-mujoco-execute-v2`. It adds three independent fields:
  - `teacher_execution_status`: `COMPLETED | FAILED | STOPPED_SAFETY | STOPPED_USER | DEADLINE | INDETERMINATE`
  - `teacher_task_result`: `PASS | FAIL | UNCONFIRMED`, together with the full output of the `teacher_endpoint_v2` judgement
  - `act_data_status`: `VALID | INVALID | DISABLED | PENDING_QC`
- **Coordinator result:** `ACT_COLLECTION_RESULT` schema 3.
  - The attempt status is derived only from the Teacher: PASSED requires `teacher_task_result=PASS`.
  - The data verdict comes from independent QC: `act_data_qc=PASS|FAIL|NOT_RUN`.
  - Export and training require both Teacher PASS and data PASS.
  - Old schema 1/2 records are kept read-only for audit and are never upgraded. Unknown versions are rejected.
- **Success rates:** the Teacher success rate is counted over all legitimate Teacher attempts that started. The data pass rate and the number of committable episodes are reported separately.

### D2. The Teacher endpoint rule `teacher_endpoint_v2`

- **Config:** new file `config/act/teacher_endpoint_v2.yaml`. Its kind is `ACT_TEACHER_ENDPOINT_POLICY` and its schema is 1.
  - The five tolerances carry over: 0.010 m, 0.15 rad, 0.020 m, 0.010 m, 0.15 rad.
  - New field `settle_s: 0.5`. It accepts any non-negative finite value.
  - The config is frozen into the inputs manifest before the attempt, with its sha256.
- **Start pose:**
  - Read after the reset completes and before the first arm or gripper motion.
  - The source is the Teacher's own `MujocoWorldObserver` world snapshot: same object_id, frame `world`, this session and this reset.
  - It does not wait for capture, cameras, the first row or the phase-channel data binding.
- **End pose:**
  - Read after the approved action sequence and release finish and the controller is confirmed stopped, then after waiting `settle_s`.
  - Exactly one snapshot is taken. There is no best-of-history selection.
- **Judgement:**
  - Start position and axis must match the frozen start.
  - Final XY, final Z and final axis must match.
  - The final axis is the angle between body +Z rotated into world and world +Z.
  - Yaw is unrestricted.
  - The quaternion must be finite and of unit norm.
  - The target attitude must itself be upright. The frozen target axis tilt must be ≤ the final-axis tolerance, otherwise the config is rejected.
  - start and end must not coincide. The XY distance must exceed the sum of the start and end tolerances, otherwise the config is rejected.
  - If a pose is missing, stale or from the wrong session, the result is `UNCONFIRMED`.
- **Old QC path:** QC no longer uses `endpoint_pose_v1` as a success criterion. `episode_qc` instead cross-checks that the data-side recording is consistent with the Teacher's recorded `teacher_endpoint_v2` start and end source references. This is data integrity, not task success.

### D3. Ownership of Teacher process checks

| Old condition | Location (inventory) | New ownership | Action |
|---|---|---|---|
| `DYNAMIC_FORCE_LIMIT_EXCEEDED` 11.60 N | `DME:126,1393` | Execution protection (explicit dangerous force) | Keep, and record it as a safety reason |
| `DYNAMIC_EARLY_TABLE_CONTACT` | `DME:1047,1397` | Process quality | Audit-only; never cancel |
| Bilateral contact lost during carry (0.08 s guard) | `DME:1389` | Process quality | Audit-only |
| `DYNAMIC_PRECLOSE_CUP_MOVED` | `DME:1401` | Process quality | Audit-only |
| `WAIT_GRASP_STABLE` 0.25 s / 6 s | `DME:1109` | Process quality | Audit-only. The state records a diagnostic and moves on |
| `VERIFY_PHYSICAL_GRASP` micro-lift ≥ 1 mm | `DME:2477` | Process quality | Audit-only. It no longer enters `VALIDATION_FAILED` |
| `WAIT_RELEASE_SETTLE` stability window | `DME:2376` | Process quality | Replaced by the `settle_s` wait from D2. The stability conditions become diagnostics |
| `VALIDATE_FINAL_PLACEMENT` | `DME:2392` | Endpoint, plus process | Replaced by D2. Table contact and fingertip contact become diagnostics |
| Release "support before open" (`_require_supported_bilateral`, `DYNAMIC_RELEASE_SUPPORT_NOT_PROVED`) | `DME:1546-1740` | Execution protection (never auto-open on an unsupported held cup) | Keep. The freshness bound changes from `rgb_sync.max_age_s` to Teacher state freshness (D5) |
| DONE manifest contract (velocity, contact, trace, …) | `dynamic_manifest.py:136-247` | Process quality | Replaced by the v2 manifest: Teacher status, endpoint result and process diagnostics |
| Broker cup safety: force / compression | `teacher_cup_safety.py` | Execution protection | Keep |
| Broker cup safety: HOLD / STABILITY / HOLDING_UNKNOWN / continuous `HOLD_LOST` | same file | Process quality | Audit-only |
| Broker table support: FORCE | `teacher_table_support.py` | Execution protection | Keep |
| Broker table support: support required before open | same file | Execution protection | Keep, applied only in `OPEN_GRIPPER`. The age uses Teacher state freshness, not 100 ms; the other support states become audit-only |
| Phase contact allowlist | `phase_contact_allowlist.py` | Necessary collision constraint (only clearly dangerous pairs) | Keep the robot–environment collision pairs. Cup contact pairs that are only process expectations become diagnostics |
| `TEACHER_PHASE_NOT_STOPPED` / ownership / predecessor / pending goal | `teacher_phase_lifecycle.py` | Execution protection (control ownership, stop confirmation) | Keep |
| Worker hard execution timeout of 180 s | `parallel_ros_runtime.py:1805` | Independent execution deadline | Keep, and make it the Teacher's only deadline (D6) |

### D4. The data side has no control authority (all data → Teacher paths are removed)

| Old path | Location | Action |
|---|---|---|
| `collection_source_hazard` → `_abort_collection_source` → `request("revoke")` | `DME:481-505,406-428,462` | Remove the revoke. A data hazard only latches `act_data_status=INVALID`, and the run continues |
| `capture.check_health()` called from the control path | `DME:424,777,793,835,870,2097`, `DR:328` | Remove from the control path. It is only called on the Recorder side |
| Scene-source `on_hazard` / `drain_hazards` → revoke | `DR:613-655` | Remove the revoke and route to the data status |
| Causal start, seed wait and `EPISODE_CAUSAL_START_*` as a precondition of the first state | `DR:287-357`, `DME:2439` | Move it into the Recorder process; it is no longer a Teacher precondition |
| `_capture_native_initial` / `_finish_native_collection` / `DYNAMIC_*_NATIVE_SOURCE_*` / `ENDPOINT_*_CAPTURE_*` | `DME:676-908`, `native_endpoints.py` | Data boundaries are decided by the Recorder after the fact. The `native_endpoints` validators stay on the QC/Recorder side, and none of them blocks or raises in the Teacher control flow |
| Recorder queue watermark / overflow / write failure | `lossless_recorder.py` | Kept inside the Recorder process; it only marks the data invalid |
| `PHYSICS_RAW_*` worker hazards → revoke | `ros_episode_physics.py`, `DR:649` | Move to the Recorder process and only mark the data invalid |
| Phase channel `bind_episode` / `drain_dispatches` audit writes / `_failed` poisoning the Teacher | `leased_action_client.py:167-330` | `LeasedTeacherPhasePort` no longer holds a recorder. Dispatch receipts go to the Teacher event stream (D7) as non-blocking, bounded publications. Its `_failed` is set only by control errors. The R8 stash/bind logic is deleted |
| K2 `_causal_scene_source` / `_check_scene_source_freshness` 100 ms join, plus `capture.check_health` at `:2097` | `DME:1811-2123` | The Teacher's planning-scene sync keeps only execution-necessary checks (planning-scene response, identity, Teacher state freshness). The raw-window 100 ms association moves to Recorder/QC |
| `PHYSICS_COMMIT_VERSION_CHANGED` retries and `TEACHER_PHYSICS_SOURCE_REFUSED` | `teacher_physics_source.py:156-441`, `teacher_reset_binding.py:955-1000`, `teacher_bound_authority.py:218-250` | Normal chunk appends no longer count as a change. The commit check is narrowed to control identity, reset/session, ownership and the validity of the selected state at execution time (freshness by Teacher policy). The 3-retry selection and the version-change refusal are deleted |
| Broker source hazard → `fence_teacher_channel` (raw gaps, truncation, silence) | `ros_teacher_physics_source.py:82-91`, `act_command_broker.py:290` | Raw history integrity and gaps are not Teacher hazards. Only state that is unavailable for longer than the Teacher's own threshold (D5), and real dangerous force or compression, can stop the Teacher |
| Teacher episode deadline taken from the Coordinator lease or heartbeat | `teacher_episode_binding.py:60-117`, `command_broker.py:513` | Use the independent Teacher deadline (D6). Heartbeat renewals no longer decide the Teacher's lifetime |
| Worker heartbeat watchdog → `cancel_motion` | `worker.py:140-460` | Coordinator loss no longer cancels a Teacher that is still within its deadline. It stops new scheduling, the result commit fails, and the Teacher finishes against its own deadline. User stop and the hard deadline still cancel |
| Terminal capture / seal failure → rc≠0 → INDETERMINATE | `parallel_worker_runtime.py:1508`, `DR:1196-1275`, `parallel_ros_runtime.py:1707-1818` | The Teacher result is taken from the manifest v2 `teacher_*` fields. Data failure only affects `act_data_status` |
| `result_store` turning a QC FAIL into attempt FAILED / `qc_downgrade` | `result_store.py:236`, `worker.py:890` | Replaced by D1 schema 3 |

### D5. Teacher state freshness (the Teacher's own policy, not inherited from the 100 ms ACT contract)

- **Config:** new file `config/act/teacher_execution_policy_v1.yaml`, frozen with the inputs:
  - `state_max_age_s: 0.5`: required freshness of world, contact, joint and scene state for execution checks.
  - `state_unavailable_stop_s: 1.0`: how long state must stay unavailable before execution stops.
  - `settle_s` comes from D2.
- **Where it is used:**
  - Support-before-open, force and compression protection.
  - Phase stop confirmation keeps the existing driver stop baseline: 1.5 s max age, 0.75 s refresh, `stop_velocity` 0.002.
- **What is unchanged:** existing control thresholds such as 51×2 ms native windows and permit 100 ms. These are controller and ownership protections, not data contract.

### D6. The Teacher's independent deadline

- **Frozen value:** the attempt freezes `teacher_execution_deadline_s` when it starts. It is the existing worker hard timeout, default 180 s.
- **Broker:** the broker refuses new goals and stops after the deadline. Before the deadline it does not fence because of the data lease or a missing heartbeat.
- **What still stops the Teacher:** user stop, `PARENT_DIED`, owner peer death and real controller failure. These are execution protections and keep their stop behaviour.

### D7. The Recorder process and the Teacher event stream

- **New installable entry `act_episode_recorder`:** console entry `so101_demo.cli.act_episode_recorder:main`. One process per attempt.
  - **Subscriptions:** RGB, physics chunks, scene_state, world evidence, joint_states, and the Teacher event stream `/so101/teacher/events` (custom JSON std_msgs/String, schema `SO101_TEACHER_EVENT_V1`).
  - **Writes:** an isolated episode directory with the existing `episode_assembly` and lossless writer, then seals it.
  - **Exit codes:** 0 = sealed VALID data, 3 = INVALID data (retained, rejected for export), 2 = config refused.
- **Teacher events:**
  - **Content:** reset complete, Teacher start/end pose, phase begin/finish, native dispatch receipts with the accepted controller reference, normal stop, terminal.
  - **Delivery:** the Teacher publishes non-blockingly with a bounded queue (depth 64), never waits for an ACK, and drops nothing silently. A drop counter goes into the manifest. The Recorder marks the data INVALID when it detects a gap in event sequence numbers.
- **Independent QC:** runs after the run in a new process, `act_first_episode qc`. Its inputs are only the sealed files.
- **Resources:** bound once at the start entry. The Recorder does not reapply for GPU; it uses no GPU.
- **Reuse of old wiring:**
  - R8, the endpoint/raw-window code and D-series diagnostics move to the Recorder side wherever they are still data-QC relevant.
  - Teacher-side copies are deleted.
  - Diagnostic logs (D15/D27/D28 etc.) that remain useful are kept as audit and do not affect control.

### D8. Teacher timing model (amendment after live L1 runs, ledger CP-3295/CP-3296)

> **VOID (2026-10-06).** D8 applied only to the broker/native chain, which is removed. See [`2026-10-06-so101-teacher-moveit-simplification-implementation.md`](2026-10-06-so101-teacher-moveit-simplification-implementation.md) R2. D8e's principle (data callbacks never starve control) is met by the separate Recorder process.

Live L1 runs showed that the broker's Teacher path mixed 0.2 s and 0.5 s data-freshness bounds, measured several of them from readings taken before slow work, and fenced the Teacher on transient "not ready" states. The audit is `a13a-timing-audit.md` (scratchpad, summarised in CP-3296). Decisions:

- **D8a, one data-freshness bound.** Every Teacher-path data-consistency age (running-epoch frame, observer fresh windows and the `ready()` intersection, execution-hold first-receipt and frame ages, reconstruction commit ages, scene source age, native-start observed age, original-context age) uses `state_max_age_s` (0.5 s). Each stream is aged from its producer time (simulation source end), so a consumer backlog shows up as age instead of being masked by receipt time.
- **D8b, re-establish freshness at the point of use.** Slow work (provenance, sampling, the path check, the cup, scene and support proofs) runs against a selection. The selection is not aged per row. Instead, one fresh `select()`/revalidation is done at the end, and the result must be geometrically unchanged. The native windows used for the reconstruction commit and the bound claim are re-fetched immediately before commit, must carry the same original hold point, and the age checks apply to the re-fetched windows.
- **D8c, "not ready" is retried, not fenced.** A controller REJECT reply at the priming read and a transient `ready()` miss are retried within the operation deadline. Readiness waits for at least 60 post-resume steps, because the controller needs 51 consecutive qualifying rows.
- **D8d, liveness.** A Teacher enable request never blocks the worker heartbeat for more than its interval. The broker bounds each enable wait well below the heartbeat timeout and returns a retryable not-ready result, which the worker retries until the episode deadline. Heartbeats keep flowing during these retries.
- **D8e, executor isolation.** High-rate data-path callbacks (contacts) must not starve the Teacher control-path callbacks. They get a separate callback group or executor thread, and redundant per-frame copies are removed.
- **D8f, pre-motion fences count as started attempts.** An attempt that was ACKed as started and is then fenced before motion is committed as a Teacher attempt that did not pass. The status comes from `teacher_attempt_status`, with the fence reason and diagnostics, and the run exits 1. This keeps it in the success-rate denominator (all started legal attempts) and never inflates it.
- **D8g, unchanged genuine protections.** These are not changed:
  - the 100 ms native claim permit and the `claim_bound` commit instant;
  - stop baselines and proofs (5 s stop evidence, 1.0 s stop settle, driver baseline), and `state_unavailable_stop_s`;
  - ownership, identity, generation, peer and provenance checks;
  - force and compression limits, and support-before-open;
  - the controller's own 200 ms and 51×2 ms hold qualification, and the 0.2 s age of a fresh ingress snapshot.

## 2. Cleanup inventory: old condition → new owner → consumer → test → reason

The full row-level inventory is `coupling-inventory-raw-20261005.md` (rows 1–19 and §2). The tables in D3 and D4 are its decision columns. Before deleting or changing anything, the writer must do the following for each row:

1. Record which consumers exist before the change, with `rg -n "<name>"` in `src/` and `test/`.
2. Implement the new owner.
3. Mark each test that verified the old contract with `REPLACED_BY=<new test>` (in the commit message or plan appendix, not in code comments), then delete or rewrite it.
4. Check imports, config, schema, RPC operation names, setup.py entries and document references, so no dangling consumer is left behind.
5. Leave no default-on "old coupling compatibility" switch.

Batch skip/xfail is not allowed.

Expected test files to rewrite or delete (for reference; adjust to what is actually found):

- `test_act_dynamic_source_binding.py`: revoke-on-data-failure tests become "data failure changes only the data state".
- `test_act_capture_seed_validity.py`, `test_act_native_collection_runtime.py`, `test_act_endpoint_raw_window.py`: move to Recorder-process tests.
- `test_act_teacher_native_child.py`: the bind_episode tests are deleted; the event-stream tests are added.
- `test_act_teacher_physics_source.py`, `test_act_teacher_reset_binding.py`: version-change retry tests become specific-validity tests.
- `test_act_teacher_cup_safety.py`, `test_act_teacher_table_support.py`, `test_act_teacher_phase_lifecycle.py`: process-quality tests become audit-only tests; force and support-before-open tests are kept.
- `test_dynamic_manifest_semantics.py`, `test_dynamic_execute.py`: switch to manifest v2 and the endpoint judgement.
- `test_act_lossless_recorder_queue.py`: moves to Recorder-process tests.
- `test_parallel_batch_worker.py`, `test_act_result_*`: switch to schema 3, and Coordinator loss does not cancel the Teacher.
- `test_act_teacher_owner_channels.py`: deadline and fence tests switch to D6.

## 3. Phases and gates

Each phase follows the same order: ledger `PLANNED` entry → Sonnet writer TDD (RED on unchanged source → GREEN) → targeted related set (`-n 8`, plus `-n 1` for the directly changed files) → main-agent review of the diff and test changes → ledger entry.

- **Phase A1 – Teacher result:** D2 and D5 config/schema, the `teacher_endpoint_v2` judgement module, manifest v2, D3 process items made audit-only (child side).
- **Phase A2 – Broker decoupling:** the D4 broker-side rows: version change, source fence, deadline (D6), cup and table safety split.
- **Phase A3 – Data side out of control:** the D4 child/worker/coordinator rows: delete revoke and check_health, the phase-port event stream, D1 schema 3, heartbeat no longer cancels.
- **Phase A4 – Recorder process:** the D7 `act_episode_recorder` entry, event-stream consumption, QC/commit chain hookup, the new prepare/run options in `act_first_episode`:
  - `--collection on|off`
  - `--collection-fault none|recorder_absent|recorder_late|queue_overflow|source_gap|output_write_failure`

  The fault option is only allowed in `preselected_target_diagnostic` mode, and only writes into the isolated `<run>/fault-sandbox/` directory.

Every phase must show directional RED/GREEN for:

- the Teacher runs without a Recorder;
- data faults cannot exercise control;
- endpoint offset, tipping, unavailable terminal state, yaw insensitivity and bad config;
- the retained execution protections still stop correctly.

Unit tests are not the final closure condition for any finding.

## 4. Freeze and complete gates (B)

1. Freeze and build with the existing `TA/freeze-copy-build-20261003-r3.zsh`, where `TA=<root>/handoffs/codex-nonhead-takeover.zya51rHz`. This produces a new F.
2. Run the complete ordinary `so101_demo_py` gate with `zsh TA/run-qualified-gate-20261003-r7.zsh <F> demo-colcon`:
   - It uses xdist `min(8, logical CPU)` and only `src/so101_demo_py/test/`.
   - Scratch goes to a fresh `<root>/scratch/installed-demo-colcon.*`, and the script verifies TMPDIR/TMP/TEMP and `tempfile.gettempdir()`.
   - Outputs: `actual.rc`, `elapsed-seconds.txt`, `demo-junit.xml`.
   - The expected rc is 0.
   - If the script cannot cover the new entries, update it in the TA directory as a new revision (`-r8`) and record that here.
3. If native C++ code changed, also run `... support-colcon`. This plan does not intend to change native code.
4. Check install provenance:
   - `<F>/qualified-install/so101_demo_py/lib/so101_demo_py/act_episode_recorder` exists, and `act_first_episode`/`dynamic_cup_pick_place` are the new versions.
   - Running processes are checked with the existing `watch-qualified-runtime-20261003.py`.

## 5. Live runs (C/D/E/F): one MuJoCo-only stack, run serially

Prepare new frozen inputs with:

`zsh TA/prepare-qualified-inputs-20261003-r2.zsh <F> <input-inspection>`

The prepare script must include `teacher_endpoint_v2` and `teacher_execution_policy_v1`; if it needs changes, it becomes revision `r3`. Then:

`zsh TA/run-qualified-live-20261003-r3.zsh prestart <P> <F>`

The `run` subcommand passes `--collection` and `--collection-fault` through `TA/run-qualified-live-*.zsh`. If the script needs extending, it becomes revision `r4`. Exact commands are written into the ledger PLANNED entry.

| Case | Input | Expected Teacher result | Expected data result | Expected rc |
|---|---|---|---|---|
| L1 | `--collection off` | `COMPLETED` + `PASS`: the cup moves from start to end and ends upright | `DISABLED` | 0 |
| L2 | `--collection on` | `COMPLETED` + `PASS` | Recorder `VALID` → fresh-process QC `PASS` → ResultStore → Coordinator commit/journal/index readback; diagnostic use refused for export | 0 |
| L3 | `recorder_absent` | `PASS`, with no data-sourced cancel/revoke/pause | `INVALID` | 3 (data) |
| L4 | `recorder_late` | `PASS` | `INVALID` | 3 |
| L5 | `queue_overflow` (Recorder-side capacity reduced only inside the sandbox) | `PASS` | `INVALID` | 3 |
| L6 | `source_gap` (Recorder drops one chunk inside the sandbox) | `PASS` | `INVALID` | 3 |
| L7 | `output_write_failure` (sandbox directory made read-only) | `PASS` | `INVALID` | 3 |

Every case must record:

- input, expected result and actual rc;
- `live.log` and the watcher provenance;
- the controller/joint/world start and end poses;
- Teacher control events;
- a scan for control events whose source is the data side;
- cleanup of owned processes.

For L3–L7, `rg` the broker and worker logs to prove that no data-sourced `revoke` / `cancel` / `pause` / `fence` appears, and compare the Teacher trajectory and result against L1.

**Acceptance criteria, frozen before testing:**

- Teacher success means `teacher_task_result=PASS` in L1, L2 and each of L3–L7.
- Latency comparison: L2 and L3–L7 must not raise the Teacher phase-time median by more than 20% over L1, measured from the same phase marks. Exceeding it is reported as a finding; it is not concealed and not used as a Teacher stop reason.
- Disk-filling and overwriting existing files are forbidden.

Old bundles, live roots and QUALIFIED results are not valid for the new identity. Each live run gets a new `<root>/experiments/<new-run>` subdirectory. Old successes are not relabelled.

## 6. Final report (task 6)

Report these separately:

- Teacher result
- data result
- integration gate
- live acceptance

Also report:

- retained, archived and deletion candidates;
- remaining todo: Head and the formal quota are out of scope.

Static or unit-test GREEN must never be presented as a live closed-loop pass.

## 7. Inline self review

- **Covers all eight design sections.**
  - §2/§3: D4 and D7 remove every data → control path.
  - §4.1: D3 lists what is kept and what is dropped.
  - §4.2: D2.
  - §5: D1 and D4.
  - §6: D7, plus the acceptance criteria in §5.
  - §7: §2.
  - §8: §3–§5.
- **Risks:**
  - D7 is the largest change. It moves the Recorder out of the control process and adds an event stream, so A4 should be split into several reviewable writer sub-steps.
  - In D4, narrowing PHYSICS_COMMIT_VERSION_CHANGED must keep checks on control identity and on the validity of the selected state at execution time; it must not drop every check.
  - In D6, a lost Coordinator lets the Teacher finish to its deadline. Real user stop and parent death still stop it.
- **Not lowered:** the data contract (10 Hz, t+0.1 s, lossless, seal, QC), joint limits, collision, dangerous force, controller failure, control ownership and stop confirmation.
- **New configs:** `teacher_endpoint_v2` and `teacher_execution_policy_v1`. All their values come from the empirical values in the authoritative design or from existing control thresholds; no new thresholds are invented. `state_max_age_s`/`state_unavailable_stop_s` are new Teacher values chosen for this plan; they are configurable and frozen, and are recorded in the ledger as empirical configuration.
- **Open items:** none need a new user decision at this point. If implementation reveals a real conflict that requires changing a safety boundary, the exact item will be reported.
