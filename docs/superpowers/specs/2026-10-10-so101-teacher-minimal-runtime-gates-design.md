# SO-101 Teacher: minimal runtime gates, end-to-end verdict (design)

Date: 2026-10-10
Status: DRAFT for independent review. Not implemented.
Ledger: CP-3501.
Supersedes, for the current sim version, `2026-10-10-so101-teacher-real-observable-safety-gates-design.md` (revision 3). That document stays as the reference for the later real-cell phase.

## 1. User direction (2026-10-10)

> 先不做这个，先从仿真取真值。后续把head camera换成rgb-d做位姿估计（这版先先不做） 中间过程减少判断，用最终的杯子位姿判断端到端成功。过程中的碰撞、感知数据用调整摘取策略，而不用于运行期安全门。

1. **No wrist in-hand estimator.** The cup pose comes from simulator truth, as today. An RGB-D head-camera pose estimator is a later version, out of scope here.
2. **Minimal intermediate judgement.** Success is decided end-to-end by the final cup pose (`teacher_endpoint_v2`, unchanged).
3. **Process data is for strategy tuning, not runtime gates.** Collision, contact, force and perception data observed during the run are recorded and analysed to tune the pick strategy. They never stop, refuse or branch the Teacher.

## 2. What stays at runtime

Only the checks needed to execute the motion sequence at all, plus operator/infrastructure safety. Row IDs refer to the inventory (`.../real-observable-gates-20261010/inventory.md`).

| Kept | Rows | Why |
|---|---|---|
| Input integrity before motion: cup pose present, fresh and in the world frame; workspace; task targets; policy files; MoveIt scene prepared; reachability | S01–S03, S06, S07, S10, S11 | Without them nothing can be planned |
| Planning and execution failures: IK horizon, MoveIt plan, corridor, plan-start drift, controller reject/abort/timeout, gripper action transport | B01–B06 | The motion cannot be executed |
| MoveIt scene housekeeping: attach, detach, ACM, scene sync service failures | B17, B18, P08, P17 (scene part), P18 | Planning needs a consistent scene |
| Control-input availability: joint states fresh (≤0.5 s, stop after 1.0 s) | B07 (joint part) | Cannot command the arm blind |
| Operator and watchdog: user stop, parent died, 180 s deadline, cancel unsettled | S14, `TEACHER_CANCEL_UNSETTLED` | Operator safety |
| Simulation integrity: session/epoch mismatch, non-finite state, evidence stream unavailable >1.0 s | S04, S08, S13, B08, B07 (evidence part), B12 | The simulator itself is broken. Status `SIM_INTEGRITY_ABORT`, not a safety stop |
| End observation and verdict: controllers stopped, settle, final snapshot, `teacher_endpoint_v2` | E01, E02 | The end-to-end verdict |

## 3. What leaves runtime (recorded as process telemetry)

| Removed as a runtime gate | Rows | Becomes |
|---|---|---|
| Cup force, compression, per-step hazard, single-contact force | B09, B10, B11 | Telemetry: peak force/compression per phase, first exceedance step, oracle flags against the r10b thresholds |
| Collision pairs | B13 | Telemetry: collision pairs with step, depth, phase |
| Release proofs: attachment flag, post-stop source, source freshness/clock, table support + bilateral | P13 (proof part), P15, P16 | Telemetry: support state and contacts at release |
| Grasp-stable wait, micro-lift and VERIFY proofs, carry bilateral, early table contact, pre-close cup moved | P04, P05, P07, B14, B15, B16 | Telemetry (they were audit-only already; the waits become fixed dwells) |
| Release settle window, final-placement proof | P20, P21 | Telemetry; the verdict is E02 |
| Place-height refusals (tilt unstable/out of range, height out of bounds, measurement failed) | P10, P11 refusals | See §4 (strategy with a fallback, no refusal) |
| Normal-stop proof before release | P14 (release use) | Kept only inside the end observation E01 |

The workflow keeps its motion sequence (approach, descend, close, micro-lift, lift, move, place descent, open, retreat). States that only judged become fixed dwells or are removed: WAIT_GRASP_STABLE and WAIT_RELEASE_SETTLE become fixed dwells of 0.25 s and 0.5 s; VERIFY_PHYSICAL_GRASP and VALIDATE_FINAL_PLACEMENT are removed.

## 4. Place strategy (no refusal)

The v2 tilt-compensated place target is a strategy, not a gate. It reads the cup pose from simulator truth.

- Measure the tilt as the mean over the samples of a 0.2 s dwell at the hover, using the existing cadence-tolerant code path.
- If a target cannot be computed (no samples, or tilt outside 3.0–5.5°, or target more than 2 mm from the v1 target), use the v1 fixed target. Record `place_height.mode = fallback_v1` with the reason.
- Record the target, tilt, k and mode in the manifest.
- The guard g = 0.7 mm is unchanged.

## 5. Failure handling: no recovery chain

Each attempt runs in a freshly reset simulation (`lifecycle=FULL_RESTART`), so recovery motions add risk and code without benefit.

- Any execution failure (§2 planning, execution or scene housekeeping): cancel the active goal, hold position, end the attempt. Execution status `FAILED` with the failure code. The task verdict is FAIL or UNCONFIRMED by E02.
- Operator/watchdog stops: as today (`STOPPED_SAFETY`, with the `TEACHER_*` codes).
- Simulation integrity: `SIM_INTEGRITY_ABORT`, the episode is INVALID.
- All `RECOVER_*` states and their edges are removed from the v3 workflow. `TERMINAL_STOP_CODES` loses every force, compression, collision, hazard, release-support and place-height code.

## 6. End-to-end verdict

`teacher_endpoint_v2`, unchanged: the start pose within 10 mm / 0.15 rad of the input pose, and the end pose within 20 mm XY, 10 mm z and 0.15 rad tilt of the target, after a 0.5 s settle. PASS requires that the motion sequence completed. A run with collisions or overloads can PASS; those facts live in the telemetry.

## 7. Process telemetry (for pick-strategy tuning)

A per-episode `teacher_process_summary` in the manifest, computed from the existing streams (physics chunks, robot contacts, evidence). Per phase it records:
- peak summed force and compression, plus margins to the r10b thresholds, and the first exceedance step;
- collision pairs, with depth and step;
- the bilateral-contact-lost intervals;
- early table contact;
- cup slip in hand (from sim truth);
- table support and contacts at release, and the release displacement;
- settle time;
- the place-height mode;
- cup-pose perception error, i.e. the perceived input pose against sim truth.

The data side copies it into the episode metadata. A tuning report aggregates it across runs: distributions, the worst cases, and correlation with the verdict.

**Dataset use.** Whether episodes with overload or collision flags are excluded from training is a dataset-builder decision, made when the formal dataset is built. Recommended default when that happens: exclude overload and collision. This design only records the flags.

## 8. Data side

- The ACT episode validity rules (raw-log offline processor, QC, readback) are unchanged.
- The Teacher event stream keeps `normal_stop` and `terminal` semantics, since the processor's window depends on them. A failed attempt emits `terminal` with status FAILED, and the episode is INVALID as today for a non-PASS Teacher.
- The manifest validator gains a v3 branch: no recovery states, a `place_height.mode` of `v2` or `fallback_v1`, and a required `teacher_process_summary`.

## 9. Versioning

- Teacher execution policy v3: minimal gates, no recovery, the place strategy with fallback, the dwell durations. v1 and v2 stay byte-identical and loadable.
- A freeze binds exactly one Teacher execution policy.
- ACT datasets are partitioned by Teacher policy version.

## 10. Validation

1. Unit tests:
   - removed gates no longer raise;
   - kept gates still raise;
   - an execution failure ends the attempt without recovery motion;
   - the place fallback triggers on its three conditions;
   - the telemetry is computed on synthetic and replayed streams;
   - the manifest validator handles the v3 branch.
2. Offline: replay the retained live bags through the telemetry computation and compare with the known facts. Examples: the CP-3480 force stop run (1.94 N) and the CP-3493 compression stop (139 µm).
3. Live (sim stack), 20 runs at the default point with collection on. Acceptance:
   - end-to-end PASS ≥ 19/20;
   - no `SIM_INTEGRITY_ABORT`;
   - VALID ≥ 17/20, the p8 baseline;
   - the telemetry report produced.
   The telemetry report is an output, not an acceptance criterion; it feeds strategy tuning.
4. Independent review of this design, then of the code before freeze.

## 11. Decisions taken (CP-3394; the user may override)

1. Remove the recovery chain in v3. Sim attempts start from a reset.
2. The v2 place target is a strategy with a v1 fallback, never a refusal.
3. Overload and collision episodes are flagged, not filtered at collection time.
4. The only non-operator runtime abort is simulation integrity. The force/collision `SIM_ORACLE_ABORT` of the superseded design is dropped.
