# SO-101 Teacher: minimal runtime gates, end-to-end verdict (design)

Date: 2026-10-10
Status: REVISION 2 (review 1: PASS-WITH-CHANGES, all 10 changes applied; §12 maps them). Not implemented.
Ledger: CP-3501 (draft), CP-3502 (review and this revision).
Supersedes, for the current sim version, `2026-10-10-so101-teacher-real-observable-safety-gates-design.md` (revision 3). That document stays as the reference for the later real-cell phase.

## 1. User direction (2026-10-10)

> 先不做这个，先从仿真取真值。后续把head camera换成rgb-d做位姿估计（这版先先不做） 中间过程减少判断，用最终的杯子位姿判断端到端成功。过程中的碰撞、感知数据用调整摘取策略，而不用于运行期安全门。

1. **No wrist in-hand estimator. Pre-grasp cup pose: the current broker inference. Post-action success: MuJoCo truth.** (User, 2026-10-10: "抓取前杯子位姿估计还是走现在broker推理方案。动作完成后的成功用MuJoCo 真值桥读取。")
   - The Teacher's input pose stays as today: `/cup_pose` from the broker's YOLO + R6 + z-clip localization (`RgbdLocalizer`). A broker failure (no or ambiguous candidate, localization rejected) leaves the Teacher no input to plan from. It is an input-availability refusal ("cannot execute"), not a safety gate.
   - The end-to-end verdict reads the cup's start and end observations from simulator truth (the Teacher observer's world evidence, i.e. the MuJoCo truth path), as `teacher_endpoint_v2` does today.
   - The perceived-vs-truth difference (S05) is never a refusal. It is recorded every run as the perception-error telemetry (§7) and feeds strategy and perception tuning.
   - An RGB-D head-camera pose estimator is a later version, out of scope here.
2. **Minimal intermediate judgement.** Success is decided end-to-end by the final cup pose (`teacher_endpoint_v2`, unchanged).
3. **Process data is for strategy tuning, not runtime gates.** Collision, contact, force and perception data observed during the run are recorded and analysed to tune the pick strategy. They never stop, refuse or branch the Teacher.

## 2. What stays at runtime

Only the checks needed to execute the motion sequence at all, plus operator/infrastructure safety. Row IDs refer to the inventory (`.../real-observable-gates-20261010/inventory.md`).

| Kept | Rows | Why |
|---|---|---|
| Input integrity before motion: cup pose present, fresh and in the world frame; workspace; task targets; policy files; MoveIt scene prepared; reachability | S01–S03, S06, S07, S10, S11 | Without them nothing can be planned |
| Planning and execution failures: IK horizon, MoveIt plan, corridor, plan-start drift, controller reject/abort/timeout, gripper action transport | B01–B06 | The motion cannot be executed |
| MoveIt scene housekeeping: attach, detach, ACM, scene sync service failures | B17, B18, P08, P17 (scene part), P18 | Planning needs a consistent scene |
| Control-input availability: joint states fresh (≤0.5 s; unavailable >1.0 s → `TEACHER_JOINT_STATE_UNAVAILABLE`) | B07 joint part (split out of `DYNAMIC_STATE_UNAVAILABLE_STOP`) | Cannot command the arm blind |
| Operator and watchdog: user stop, parent died, 180 s deadline, cancel unsettled | S14, `TEACHER_CANCEL_UNSETTLED` | Operator safety |
| Simulation integrity: session/epoch mismatch, non-finite state, world-evidence stream silent >1.0 s (`SIM_INTEGRITY_EVIDENCE_UNAVAILABLE`) | S04, S08, S13, B08, B07 evidence-silence part | The simulator itself is broken. It does **not** include `truncated` (contact-list overflow, B07) or physics-chunk gaps (B12): those are telemetry completeness, never an abort |
| Place-geometry binding loaded before motion | S12 | A scene-hash mismatch selects the place fallback (§4); it never refuses |
| Activated contact policy (r10b) loaded | S09 | Non-gating: it is needed only for the telemetry margins. Load failure marks the summary incomplete |
| End observation and verdict: controllers stopped, settle, final snapshot, `teacher_endpoint_v2` | E01, E02 | The end-to-end verdict |
| Final `normal_stop` event (D5) | P14 path inside `_publish_final_normal_stop` | Required by the data side (§8). Kept, with its age bound from the execution policy instead of the release policy |

## 3. What leaves runtime (recorded as process telemetry)

| Removed as a runtime gate | Rows | Becomes |
|---|---|---|
| Cup force, compression, per-step hazard, single-contact force | B09, B10, B11 | Telemetry: peak force/compression per phase, first exceedance step, oracle flags against the r10b thresholds |
| Collision pairs | B13 | Telemetry: collision pairs with step, depth, phase |
| Release proofs: attachment flag, post-stop source, source freshness/clock, table support + bilateral | P13 (proof part), P15, P16 | Telemetry: support state and contacts at release |
| Grasp-stable wait, micro-lift and VERIFY proofs, carry bilateral, early table contact, pre-close cup moved | P04, P05, P07, B14, B15, B16 | Telemetry (they were audit-only already; the waits become fixed dwells) |
| Release settle window, final-placement proof | P20, P21 | Telemetry; the verdict is E02 |
| Place-height refusals (tilt unstable/out of range, height out of bounds, measurement failed) | P10, P11 refusals | See §4 (strategy with a fallback, no refusal) |
| Normal-stop proof as a *release authorization* | P14 (release use) | Replaced by a bounded wait for the arm to stop, an execution precondition (§5a). The proof itself stays for the final `normal_stop` event (§2) |
| Cup-pose divergence against simulator truth | S05 | Telemetry (perception error, every run). Never refuses |
| Contact-list `truncated` flag and physics-chunk gaps | B07 (truncated), B12 | Telemetry completeness flags |
| Release preflight bookkeeping | P17 (`RELEASE_PREFLIGHT_REQUIRED`, `DETACH_NOT_PROVED`) | Replaced by the v3 release sequence (§5a) |

The workflow keeps its motion sequence and its **forward state names**, so the success trace stays identical to v1/v2 (`e2e_acceptance.SUCCESS_STATE_TRACE`):
- WAIT_GRASP_STABLE becomes a fixed 0.25 s dwell;
- WAIT_RELEASE_SETTLE becomes a fixed 0.5 s dwell;
- VERIFY_PHYSICAL_GRASP and VALIDATE_FINAL_PLACEMENT become **record-only pass-through** states. They snapshot and record telemetry, and never fail.

v3 is a **separate `WorkflowDefinition`** (`SO101_WORKFLOW_V3`) with its own stop-code set, chosen by the frozen Teacher execution policy version. The v1/v2 workflow, `TERMINAL_STOP_CODES`, `DYNAMIC_MOTION_STATES` and `SUCCESS_STATE_TRACE` stay unchanged.

## 4. Place strategy (no refusal)

The v2 tilt-compensated place target is a strategy, not a gate. It reads the cup pose from simulator truth.

- **Measurement.** Use the existing cadence-tolerant v2 measurement unchanged: a ≥100 ms window with a tilt range under 0.05° within 1 s, from sim-truth evidence. Its refusal paths become fallback reasons.
- **Fallback.** Use the v1 fixed target if any of these hold. The reasons form a closed enum:
  - `TILT_UNSTABLE` (no window in 1 s);
  - `TILT_OUT_OF_RANGE` (outside 3.0–5.5°);
  - `K_OUT_OF_BAND` (k outside 0.037454 ± 0.0003 m);
  - `TARGET_DEVIATION` (more than 2 mm from the v1 target);
  - `JOINT_STATE_STALE` (older than `state_max_age_s`);
  - `SCENE_HASH_MISMATCH` (S12);
  - `MEASUREMENT_FAILED` (geometry or timeout).
- **The v1 target is a different demonstration.** It overtravels ≈0.94 mm after first contact against ≈0.73 mm for v2 (CP-3494).
- **Record.** A v3 `place_height` record (schema `teacher_place_height_v3`) holds `mode` ∈ {`tilt_compensated`, `fallback_v1`}, a `fallback_reason` (enum, or null), the inputs measured so far, and the target used. The v3 validator recomputes the formula only for `tilt_compensated` and checks that the target equals the v1 target for `fallback_v1`. `place_height.validate_document` for v2 is unchanged.
- **Guard.** g = 0.7 mm is unchanged.

## 5. Failure handling: no recovery chain

Each attempt runs in a freshly reset simulation (`lifecycle=FULL_RESTART`), so recovery motions add risk and code without benefit.

- Any execution failure (§2 planning, execution or scene housekeeping): cancel the active goal, hold position, end the attempt by going **straight to ERROR from any state**, with the cup attached or detached in MoveIt. The task verdict is FAIL or UNCONFIRMED by E02.
- The v3 workflow has no `RECOVER_*` states. The v3 stop-code set contains only the operator/watchdog codes, `TEACHER_JOINT_STATE_UNAVAILABLE` and the `SIM_INTEGRITY_*` codes. Every other failure is non-terminal, and in v3 a non-terminal failure also goes to ERROR.
- The manifest validator's v3 branch accepts ERROR from any state, with the cup attached or detached. It does not require the v1/v2 recovery evidence.

### 5a. v3 release sequence (no release proof)

At the end of DESCEND_TO_PLACE:
1. Wait, bounded at 1.0 s, for the arm to stop (all joint velocities ≤ 0.002 rad/s on a fresh joint state). This is an execution precondition, not a safety proof. A timeout ends the attempt with `TEACHER_ARM_NOT_STOPPED` → status `FAILED`.
2. Take a fresh `_snapshot()` and use its cup pose for detach and sync (replaces the pose `_detach_or_sync` took from the release preflight).
3. DETACH_MOVEIT: detach and sync, with the scene readbacks as today.
4. OPEN_GRIPPER: open, and record `release_marker_sequence` from the evidence sample at the open, as `dynamic_manifest._error_contract` and `e2e_acceptance` require.
No support, bilateral or post-stop-source checks.

### 5b. v3 status mapping

| Outcome | Teacher execution status | Teacher task result | Attempt / data |
|---|---|---|---|
| DONE, end observation OK | COMPLETED | PASS or FAIL by E02 | data per QC |
| Execution failure (plan, controller, gripper transport, scene, `TEACHER_ARM_NOT_STOPPED`) | FAILED | UNCONFIRMED (no end observation) or FAIL | data INVALID (non-PASS Teacher) |
| Operator/watchdog: `TEACHER_USER_STOP` and `TEACHER_PARENT_DIED` → STOPPED_USER, `TEACHER_DEADLINE` → DEADLINE (the v2 mapping, kept, CP-3506); `TEACHER_JOINT_STATE_UNAVAILABLE` → STOPPED_SAFETY | as stated | UNCONFIRMED | data INVALID |
| `TEACHER_CANCEL_UNSETTLED` or a controller left unconfirmed | INDETERMINATE (as today) | UNCONFIRMED | data INVALID |
| `SIM_INTEGRITY_*` | FAILED, with `failure_class = sim_integrity` | UNCONFIRMED | data INVALID; the attempt is counted as infrastructure, not a Teacher failure |

No new Teacher execution status value is introduced; `SIM_INTEGRITY` is a `failure_class` field. `EXECUTION_STATUSES`, the result store, the worker and e2e_acceptance keep their status sets.

## 6. End-to-end verdict

`teacher_endpoint_v2`, unchanged: the start pose within 10 mm / 0.15 rad of the input pose, and the end pose within 20 mm XY, 10 mm z and 0.15 rad tilt of the target, after a 0.5 s settle. PASS requires that the motion sequence completed. A run with collisions or overloads can PASS; those facts live in the telemetry.

## 7. Process telemetry (for pick-strategy tuning)

A per-episode `teacher_process_summary` (schema `teacher_process_summary_v1`) in the manifest, computed from the existing streams **off the control thread**.

Definitions:
- **Phase:** a Teacher state, bounded by its `phase_begin` / `phase_finish` events.
- **Units:** N, µm, mm, deg, s, and physics step numbers.
- **Force and compression:** from the 500 Hz physics chunks. "First exceedance" is the first step over the r10b threshold, with a strict `>` (no filter).
- **Collision pairs:** from `/robot_contacts`, i.e. pairs outside the cup process pairs, with depth and step.
- **Bilateral contact lost:** an interval of ≥ 80 ms without contact on both fingertips (100 Hz evidence).
- **Slip:** the cup pose in the TCP frame by FK, at the end of WAIT_GRASP_STABLE versus just before OPEN_GRIPPER (mm, deg).
- **Settle time:** time from the OPEN_GRIPPER finish until P20's predicate first holds (≤ 1 mm/s, ≤ 0.05 rad/s, 0.2 s).
- **Release displacement:** cup pose at the OPEN_GRIPPER start versus the end observation.
- **Completeness:** a lost chunk, a lost contact frame or `truncated` marks the summary `complete = false` with a reason. It never aborts.

Per phase it records:
- peak summed force and compression, plus margins to the r10b thresholds, and the first exceedance step;
- collision pairs, with depth and step;
- the bilateral-contact-lost intervals;
- early table contact;
- cup slip in hand (from sim truth);
- table support and contacts at release, and the release displacement;
- settle time;
- the place-height mode;
- the cup-pose perception error, recorded every run: broker input pose versus sim truth at the start (xy, z, yaw-free tilt).

The data side copies it into the episode metadata. A tuning report aggregates it across runs: distributions, the worst cases, and correlation with the verdict.

**Training inputs (user, 2026-10-10: "碰撞和受力数据不进入训练").** Collision, contact and force data never enter training.
- **What training sees.** The exported training samples and the training loader use a whitelist, `observation` (head/wrist images, joint state) and `action` only. The per-record `audit` (contact lists, normal forces), `teacher_process_summary`, oracle flags and any contact/force/collision field are excluded from training samples.
- **Where the excluded data stays.** It remains in the sealed episode and its metadata, for data QC and pick-strategy tuning.
- **Test.** A test asserts that an exported training sample contains no contact/force/collision field, and that the loader reads only whitelisted keys.

**Episode exclusion (user, 2026-10-10: "先剔除。后续通过执行过程中的视觉数据判定是否发生碰撞以及时间区间。").**
- **Rule.** An episode whose `teacher_process_summary` has `ORACLE_CUP_OVERLOAD` (summed force or compression above the r10b oracle thresholds, 500 Hz, strict `>`) or `ORACLE_COLLISION` (a robot contact pair outside the cup process pairs) in any phase is **not training-eligible**.
- **Where it is enforced.** At export / training-set build: the resolver and `export_dataset` refuse it with `EXPORT_EPISODE_ORACLE_EXCLUDED` plus the flag and phase. The episode stays sealed and committed, with its data verdict unchanged, for analysis.
- **Incomplete telemetry.** An episode with an incomplete summary (`complete = false`) is also not training-eligible, because the flags cannot be ruled out.
- **Not a runtime gate.** This is an offline data-selection rule.
- **Later (out of scope).** Collision detection and its time interval from execution-time vision data, replacing the sim-oracle flags for this rule.

## 8. Data side

- The ACT episode validity rules (raw-log offline processor, QC, readback) are unchanged.
- The Teacher event stream keeps `normal_stop` and `terminal` semantics, since the processor's window depends on them. A failed attempt emits `terminal` with status FAILED, and the episode is INVALID as today for a non-PASS Teacher.
- The manifest validator gains a v3 branch, selected by the frozen Teacher execution policy version (manifest schema `so101-dynamic-mujoco-execute-v3`, CP-3506). It requires no recovery states, a `teacher_place_height_v3` record, and a `teacher_process_summary_v1`. e2e_acceptance likewise accepts v1, v2 and v3 by schema.
- The final `normal_stop` event: emitted on DONE with its payload unchanged (`source_clock`, `publisher_sequence`, `sim_stamp_s`). A failed or stopped attempt emits no `normal_stop`, as today, and its data is INVALID.

## 9. Versioning

- Teacher execution policy v3: minimal gates, no recovery, the place strategy with fallback, the dwell durations. v1 and v2 stay byte-identical and loadable.
- A freeze binds exactly one Teacher execution policy.
- ACT datasets are partitioned by Teacher policy version. The episode metadata records the Teacher policy version, the cup-pose source (`broker_rgbd`), the verdict source (`sim_truth`) and the `teacher_process_summary` schema version.

## 10. Validation

1. Unit tests:
   - removed gates no longer raise;
   - kept gates still raise;
   - an execution failure ends the attempt without recovery motion, with a v3 ERROR manifest that validates;
   - the release sequence of §5a records the marker;
   - the final `normal_stop` is emitted on DONE;
   - the place fallback triggers on each enum reason;
   - the telemetry is computed on synthetic and replayed streams, including when it is incomplete;
   - the v1 and v2 workflows and validators are unchanged (their existing tests pass untouched).
2. Offline telemetry replays against known facts, with tolerances:
   - CP-3480 run 392e7925: peak summed force 1.940 N ± 0.005 at step 41943 ± 1;
   - CP-3493 run 008b058f: left compression 139.0 µm ± 0.5. That run has no bag, so the manifest evidence replay is used.
3. Live (sim stack): 20 runs at the default point with collection on, plus the 5 data-fault cases. Acceptance:
   - end-to-end PASS ≥ 19/20;
   - no `SIM_INTEGRITY_*`;
   - VALID ≥ 18/20 (the p8 baseline was 17/20, including 2 camera-pair failures since fixed; p9 was 6/6);
   - zero `RECOVER_*` states in any trace;
   - every run accepted by the manifest validator, e2e_acceptance and the offline processor;
   - one injected execution failure whose ERROR manifest validates;
   - the 5 faults rc 3 with readback PASS;
   - the telemetry report produced. The report is an output that feeds strategy tuning, not an acceptance criterion.
4. Independent review of this design, then of the code before freeze.

## 12. Changes from draft 1 (review: PASS-WITH-CHANGES)

1. Final `normal_stop` path kept, age bound from the execution policy, payload unchanged (§2, §8).
2. v3 release sequence: bounded arm-stop wait, fresh snapshot for detach/sync, release marker recorded (§5a).
3. Separate `SO101_WORKFLOW_V3` and stop-code set. VERIFY/VALIDATE are kept as record-only pass-throughs, so the success trace is unchanged (§3).
4. The v3 manifest branch accepts ERROR from any state, with the cup attached or detached (§5).
5. Status mapping table. `SIM_INTEGRITY` is a `failure_class`, not a new status (§5b).
6. B07 is split: the `truncated` flag and chunk gaps become telemetry completeness. S05 becomes telemetry (§2, §3).
7. S09 is non-gating, S12 selects the fallback, P17 is replaced. The cup-pose source is named (later changed by the user, CP-3504: broker input, truth verdict) (§1, §2, §3).
8. The place measurement is the existing window method. Fallback reasons are a closed enum, the v3 record has its own validation, and the 0.94 vs 0.73 mm overtravel is noted (§4).
9. Telemetry definitions: phases, units, streams, durations, completeness, off the control thread (§7).
10. Acceptance: VALID ≥ 18/20, faults, trace, validators, injected failure, replay tolerances. Versioning: manifest schema v3 and metadata (§9, §10).

## 11. Decisions taken (CP-3394; the user may override)

1. Remove the recovery chain in v3. Sim attempts start from a reset.
2. The v2 place target is a strategy with a v1 fallback, never a refusal.
3. Overload and collision episodes are flagged, not filtered at collection time.
4. The only non-operator runtime abort is simulation integrity. The force/collision `SIM_ORACLE_ABORT` of the superseded design is dropped.
5. Superseded by the user (CP-3504): the Teacher's input pose stays the broker inference. The success verdict uses MuJoCo truth. S05 is telemetry. There is no truth bridge into the Teacher input and no perception shadow.
