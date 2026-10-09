# SO-101 Teacher: real-observable safety gates (design, revision 2)

Date: 2026-10-10
Status: REVISION 2, for independent re-review. Not implemented.
Ledger: CP-3497 (user request and assumptions), CP-3498 (draft 1), CP-3499 (review FAIL and this revision).
Inventory used (row IDs S01–S14, B01–B18, P01–P23, E01–E02):
`/data/work/so101-evidence/act-data/20260924-fbc25063-resume/handoffs/teacher-act-decoupling-20261005.1RmsJ3ZJ/real-observable-gates-20261010/inventory.md`

Revision 2 addresses the eight required changes of the first review (§12 maps them).

## 1. Requirement

The user's statements (2026-10-10):

- "在抓取动作过程中的安全校验规则需要遵循一个事实：实际的机械臂没有接触力反馈。我们需要以此原则重新设计抓取过程的安全校验门。"
- "我们可以假定 杯子真值位姿可以获取到，真实场景可以通过视觉定位。"

Signal classes:

| Class | Signals | Role |
|---|---|---|
| Real-observable (R) | joint positions/velocities (quantized encoders), commanded targets, gripper position q6 (quantized), cup pose from visual localization (head and wrist cameras; velocity by differencing), MoveIt scene state, time | May gate the Teacher |
| Configured actuator limits | gripper torque limit (STS3215 `Torque_Limit`; sim actuator-6 `forcerange`), arm speed and acceleration scaling | Bound force by construction (§3 R2) |
| Diagnostic-only | STS3215 present load/current/temperature; joint tracking error until a servo model exists (§4.1) | Recorded, never a gate |
| Sim-only (S) | contact forces, compression, contact pairs, table-support distance, physics chunks, session/epoch plumbing | The sim oracle: data QC, gate referee, catastrophic infrastructure abort (§7). Never a Teacher decision |

## 2. Findings that drive the design

1. The stops that protect the cup and robot today are all S: force/compression/hazard (B09–B11), collision pairs (B13), and the release support proof (P16). P16 also authorizes recovery opening, so it can strand the cup (P23).
2. **Corrected from draft 1.** The grasp is not saturated at close. At the end of CLOSE_GRIPPER (target −0.0476 rad) the pads press only about 0.23 N / 34 µm on one side (CP-3495). The carry hold (1.54 N, 97.5 µm) forms as a **wedge at MICRO_LIFT**: about 1.6 mm of slip and 1.6° of rotation. Force versus close command is about 1.2 N/mrad (0.36 N at −0.0476 rad, 5.7 N at −0.052 rad). The window that carries the cup is 0.4 mrad wide; −0.0460 rad loses the cup. One STS3215 encoder count (≈1.5 mrad) spans the whole r10b force limit. **A position-shaped close cannot bound the force on the real arm.**
3. The real-observable grasp proofs are advisory today: micro-lift and VERIFY (P05, P07) are audit-only, WAIT_MICRO_LIFT_STABLE has no check (P06), and q6 is never read after the close (B06).
4. v2 presses the cup about 0.7 mm past first table contact so the contact-based release proof (P16) can hold. That needs cup-z accuracy of about 0.1 mm, and pressing into the table is the mechanism of the place-phase stops (CP-3480, CP-3494).
5. The sim Teacher reads a noise-free 100 Hz cup pose. On the real cell the head camera is partly blinded while the cup is in the gripper.
6. `_enforce_safety` only runs during goals and waits (inventory §0).
7. There is no real-hardware (Feetech) code in the repo. Every real-cell calibration in this design is therefore a prerequisite (§10), not something we can do now.

## 3. Principles

- **R1 Gates are real-observable**, plus versioned cell geometry (table height, cup geometry) and versioned actuator limits.
- **R2 Bound force by construction, verify by outcome.** The gripper closes **past contact under a torque limit**. The jaw force, including the wedge reaction during carry, is then capped by the torque limit, because the jaw back-drives rather than squeezes harder. On the real arm this requires the STS3215 `Torque_Limit`; it is not optional. Arm speed and acceleration limits bound impact. Gates check the observable outcome.
- **R3 Never load the table with the held cup.** Release from a bounded clearance.
- **R4 The sim oracle never makes a Teacher decision.** It does three things: per-episode data QC, measuring gate quality, and a catastrophic infrastructure abort with its own status (§7).
- **R5 Gates are exercised with realistic information**: a localizer emulator (§6) and quantized encoders and q6 in sim.
- **R6 Every gate fails closed with a defined end state** (§5). Recovery never depends on an S proof, and no gate moves the arm while the gripper is in an unknown state.

## 4. Gate catalogue

"STOP" = terminal stop as today (`TERMINAL_STOP_CODES`, status `STOPPED_SAFETY`). End states are defined in §5. Every threshold is in §8 (initial values) and is frozen in policy v3.

### 4.0 Preflight (IDLE)

- S01–S03, S06, S07, S10, S11, S14: unchanged (R).
- S05 → `TEACHER_CUP_LOCALIZATION_DISAGREE` (REFUSE): head and wrist localizations disagree by more than 10 mm or 0.10 rad. Replaces the comparison with sim truth.
- S12 and the P11 scene-hash term: cell geometry (table-top z, cup bottom r and c, cup 12-gon width across flats and corners) becomes a versioned file. In sim it is bound to the MJCF hash as today; on the real cell it is bound to a measured file. The P11 "target within 2 mm of v1" term is dropped. Its purpose (a sanity bound) is replaced by the clearance band of §4.6.
- S04, S08, S13, B08, and the session/epoch parts of P14 and P15: simulation infrastructure, not safety gates. They stay in sim only, as integrity checks with infrastructure status. On the real cell they do not exist.
- Actuator-limit check (REFUSE): the gripper torque limit and arm scaling read back from the controller or model must equal the frozen policy values.

### 4.1 Approach (MOVE_ABOVE_OBJECT, DESCEND)

- B01–B05, B04 corridor, TCP-z floor: unchanged (R).
- Collision protection uses planning (the MoveIt scene with the table, pedestal and cup), the kinematic corridor, the speed limits, and `TEACHER_CUP_MOVED_BEFORE_GRASP` (RECOVER: retreat, re-localize, re-plan). That last gate fires when the cup moves more than 5 mm from its preflight pose, judged on a mean of ≥5 frames, before CLOSE_GRIPPER.
- **Joint tracking error is diagnostic-only.** The sim arm (kp 998, continuous encoders) does not represent an STS3215 with a low P coefficient, sag, deadband, 4096-count quantization and a 30–60 Hz bus. A tracking-error gate needs a validated servo model; that is a prerequisite (§10). Until then, catastrophic collisions in sim are caught by the oracle infrastructure abort (§7), not by a Teacher gate.

### 4.2 Close (CLOSE_GRIPPER, WAIT_GRASP_STABLE): torque-limited close

- Command q6_cmd = q6_close_far (well past contact, e.g. the fully closed limit) under gripper torque limit τ_grip. In sim this is a separate actuator-6 `forcerange` in a versioned ACT model; on the real arm, `Torque_Limit`. τ_grip is chosen by a sweep (§9.2): the cup must carry through MICRO_LIFT, LIFT and the place descent (wedge included), and the oracle peak force and compression must stay ≤ 85% of the r10b limits.
- Settle: q6 velocity below threshold for 250 ms, timeout 2 s (§8). Then read q6_stall.
- Presence test:
  - `TEACHER_GRASP_MISSED` (end state A, §5): q6_stall within 2 encoder counts of q6_close_far (jaw closed on nothing). Because the command is far past contact, a miss and a grasp are many counts apart.
  - `TEACHER_GRASP_WIDTH_OUT_OF_BAND` (end state A): q6_stall outside [q6_corner − m, q6_flat + m], where q6_flat and q6_corner are the stall angles on the 12-gon's flats and corners (≈2.8 mm width difference), and m covers off-centre grasp plus 2 counts of quantization.
  - Otherwise: grasp present.
- The contact-based bilateral wait (P04) moves to the oracle.

### 4.3 Micro-lift and verify (MICRO_LIFT, WAIT_MICRO_LIFT_STABLE, VERIFY_PHYSICAL_GRASP)

- The micro-lift height rises from 4 mm to 10 mm, so the lift signal clears the localizer noise (see below).
- WAIT_MICRO_LIFT_STABLE gets a real wait: the arm stopped (encoder velocities), then ≥10 wrist-camera frames.
- `TEACHER_GRASP_NOT_LIFTED` (new VERIFY failure edge → end state A). Δcup_z must follow Δtcp_z within tolerance t_lift. Δcup_z is the in-hand wrist-camera estimate, the mean of ≥10 frames after minus ≥10 frames before. The wedge slip (≈1.6 mm) is expected and inside t_lift. A cup that stayed on the table differs by about 10 mm, which is more than 10σ of the frame-mean difference at the §8 noise profile.
- q6 unchanged within 2 counts.
- ATTACH_MOVEIT only after this gate passes. The workflow gains VERIFY_PHYSICAL_GRASP → RECOVER edge (today VERIFY never fails).

### 4.4 In-hand pose model (replaces head-camera cup pose during carry)

- At the close, the cup rests on the table. Its z (table-top + c) and the gripper FK give the exact pick offset with no vision. The wrist camera measures the cup relative to the gripper at the same instant, which calibrates the wrist camera's in-hand bias for this episode.
- After the wedge, the in-hand pose (offset k and tilt) is the pick offset plus the wrist camera's measured relative change. The per-episode bias cancels.
- During carry the cup pose is FK ∘ in-hand pose. The head camera is not needed while it is occluded.

### 4.5 Carry (LIFT, MOVE_ABOVE_PLACE, recovery carries)

- `TEACHER_CUP_SLIP` (end state B): the in-hand pose (wrist camera) drifts beyond tolerance from its VERIFY value, sustained over ≥3 frames.
- `TEACHER_CUP_DROPPED` (end state C): the wrist camera loses the cup in hand for more than 0.3 s while q6 has moved toward closed by more than 2 counts, or the head camera finds the cup on the table.
- `TEACHER_GRIPPER_POSITION_CHANGED` (end state B): q6 changed by more than 2 counts.
- B07 is redefined for carry: freshness applies to the wrist-camera in-hand stream (gap > 0.5 s → `DYNAMIC_STATE_UNAVAILABLE_STOP`, end state B). Head-camera gaps while the cup is in hand are expected and are not a stop.
- B15/B16 move to the oracle.

### 4.6 Place: hover release (R3)

- Before the descent: tilt θ and offset k come from the in-hand model (§4.4) as the mean of ≥10 wrist frames, with drift bound d_θ (refusals `TEACHER_PLACE_TILT_UNSTABLE` and `TEACHER_PLACE_TILT_OUT_OF_RANGE`, end state B). The lowest point comes from the exact round-bottom geometry (`core/place_height.py`).
- Target: lowest point at h_rel above table-top. h_rel = h_min + b_z + 3·σ_z,mean, where b_z is the bound on the residual in-hand bias after pick calibration and σ_z,mean is the frame-mean noise. With the §8 initial profile this gives about 3 mm. The target is never below table-top + h_min.
- `TEACHER_PLACE_UNEXPECTED_CONTACT` (end state B, after a 10 mm lift): the in-hand pose changes beyond tolerance during the final descent, meaning the cup touched something early. Tracking error is not used (§4.1).
- This replaces the v2 overtravel guard, the k ± 0.3 mm band and the 2 mm deviation bound, which were sim-truth calibrated.

### 4.7 Release (DETACH_MOVEIT, OPEN_GRIPPER, WAIT_RELEASE_SETTLE)

- Authorization replaces P16. All four must hold, else `TEACHER_RELEASE_NOT_AUTHORIZED` (end state B):
  1. Arm stopped: the P14 encoder-velocity proof.
  2. Cup static in hand: in-hand pose stable over ≥10 frames.
  3. Lowest point within [table + h_min, table + h_rel + b_z + 3σ], from frames exposed after the stop.
  4. Tilt ≤ θ_max.
- P15 is redefined: "post-stop source" means wrist-camera frames whose exposure stamps are later than the stop confirmation. The simulator scene-frame (session, epoch, step) matching is removed from the Teacher, since it is the T06/T09 failure path; integrity of the sim streams stays an infrastructure check.
- Open to q6_open. Then `TEACHER_GRIPPER_OPEN_NOT_REACHED` (end state D) if q6 has not reached q6_open within 2 counts and 1 s. **No arm motion follows.**
- Settle: head camera (no longer occluded), cup z in the resting band, tilt ≤ 0.15 rad, and a linear fit over ≥1 s and ≥15 frames gives ≤ 1 mm/s and ≤ 0.05 rad/s. A timeout here is audit; the endpoint verdict decides.

### 4.8 Retreat, final placement, end of run

- RETREAT: `TEACHER_CUP_DISTURBED_ON_RETREAT` (audit) if the head camera finds the cup moved more than 5 mm.
- P21: pose terms only. E01/E02: unchanged (pose only; wall-time settle on the real cell).

### 4.9 Recovery

- RECOVER_OPEN_GRIPPER uses the §4.7 authorization from a hover over the pick or place location. It never depends on an S proof.
- If authorization fails, end state B. Recovery never lifts a cup whose release state is unknown (end state D).

## 5. End states

| State | Situation | Action | Status |
|---|---|---|---|
| A | Grasp not established (`GRASP_MISSED`, `WIDTH_OUT_OF_BAND`, `GRASP_NOT_LIFTED`) | Lower back to the pick height if lifted, open, verify q6 open, retreat vertically 30 mm | `STOPPED_SAFETY`, task UNCONFIRMED |
| B | Cup held, its state uncertain (`SLIP`, `GRIPPER_POSITION_CHANGED`, `UNEXPECTED_CONTACT`, `RELEASE_NOT_AUTHORIZED`, tilt refusals, in-hand stream lost) | Stop motion; at most a 10 mm vertical lift if the cup is near the table; hold | `STOPPED_SAFETY`. Real cell: operator. Sim: episode ends |
| C | Cup dropped | Stop motion, open, retreat vertically | `STOPPED_SAFETY` |
| D | Gripper did not open as commanded | No arm motion; hold position | `STOPPED_SAFETY`. Real cell: operator |

## 6. Localizer emulator

The Teacher's cup pose in sim comes from an emulator fed by simulator truth. The profile is versioned, and the initial placeholders are in §8. It models:

- rate and latency, with stamp jitter and exposure stamps;
- per-episode bias (head and wrist separately) and AR(1)-correlated noise;
- view-dependent occlusion: the head camera is blinded while the cup is in the gripper, and partial occlusion near the jaws;
- a separate wrist-camera in-hand model (relative pose; bias calibrated at pick, §4.4);
- outliers, including the ring mask-bleed mode (CP-3479 R-b), and dropouts;
- quantized encoders and q6 (4096 counts per turn).

The emulator affects only the Teacher's control input. Recorded data keeps the true streams for QC. An `ideal` profile exists for regression comparison only.

## 7. Sim oracle

- QC verdicts that make an episode INVALID: `ORACLE_CUP_OVERLOAD` (r10b limits, now oracle thresholds), `ORACLE_COLLISION`, `ORACLE_GRASP_LOST`, `ORACLE_RELEASE_DISPLACED` (the cup shifts more than 5 mm or tilts more than 0.15 rad on release).
- **Catastrophic infrastructure abort.** It is configurable per run: ON for collection, OFF for validation sweeps so misses can be measured. It triggers on a summed cup force or single contact force at or above 11.60 N, a robot collision pair with penetration above 2 mm, or non-finite state. Its status is `SIM_ORACLE_ABORT` (not `STOPPED_SAFETY`), and the episode is INVALID. It is an infrastructure action and never part of a Teacher gate decision.
- Gate quality: a confusion matrix of each gate against the oracle over the §9 sweeps.

## 8. Initial numbers (placeholders until the real cell is characterized; frozen per policy v3)

| Item | Initial value | Basis |
|---|---|---|
| Head camera | 15 Hz, latency 80 ms, jitter 10 ms, bias σ 1.5 mm / 1°, AR(1) ρ 0.8 with σ 1 mm / 0.5°, dropout 2%, outliers 1% (5–10 mm) | Typical RGB-D localizer; replace on characterization |
| Wrist camera, in hand | 15 Hz, latency 80 ms, residual bias after pick calibration b_z ≤ 0.5 mm, AR(1) σ 0.4 mm / 0.3° | Close range; bias calibrated at pick |
| h_min | 1.0 mm | |
| h_rel | h_min + b_z + 3σ_z,mean ≈ 1.0 + 0.5 + 3·0.15 ≈ 2 mm (≈3 mm with margin) | §4.6 |
| t_lift | 4 mm | Wedge slip ≈1.6 mm; miss would be ≈10 mm |
| q6 stability | velocity < 2 counts / 100 ms over 250 ms | |
| Slip tolerance | 2 mm / 1.5° in hand | |
| θ range | measured by the §9.2 carry-tilt sweep over the randomized domain; refusal rate recorded | Replaces 3.0–5.5° |
| τ_grip | from the §9.2 sweep | Carry with oracle peak ≤ 85% of the r10b limits |

## 9. Validation

1. **Unit and replay.** Unit tests for every gate and end state. Replaying the existing bags (old close, press place) can measure only the false-stop rate of the approach and carry gates under the emulator; it is reported as such.
2. **Sim sweeps** with the oracle as referee, the infrastructure abort OFF, and ≤500 trials per setting:
   - a τ_grip sweep (carry success, oracle peak margin, tilt);
   - a carry-tilt sweep over the randomized start domain;
   - a hover-release drop sweep over h_rel, tilt and the wedge release (pad friction 3.0), including the ring at the place site: final shift, tilt, bounce;
   - fault injection:
     - missed grasp;
     - wrong-width object;
     - grasp offset and yaw (flats/corners);
     - slip (friction drop);
     - drop;
     - obstacle collision;
     - localizer bias, outliers and occlusion.
   Acceptance targets: 0 misses on missed-grasp, drop and slip injections in 500 trials (this bounds the miss rate at ≈0.6%, 95%); a false-stop rate ≤ 2% on clean trials; a release-displacement rate ≤ 1% at the frozen h_rel.
3. **Live** (sim stack): 20 runs at the default point, collection on, infrastructure abort ON. Acceptance: PASS and oracle-clean in every phase (LIFT included) in ≥19/20, no `SIM_ORACLE_ABORT`, VALID rate unchanged. Then the randomized-domain work.
4. Independent review of this revision before implementation, and of the code before freeze.

## 10. Prerequisites for the real cell (blocked; no hardware driver in the repo)

The Feetech/STS3215 driver and bus, the `Torque_Limit` configuration and an external jaw-force gauge calibration of τ_grip, encoder and q6 characterization, the servo model (P coefficient, quantization, bus rate) needed before any tracking-error gate, localizer characterization (replacing §8), and the cell-geometry measurement. Until these exist, the design is validated in sim only.

## 11. Versioning and data

- **New policy and model.** Teacher execution policy v3 (gates, thresholds, τ_grip, h_min, emulator profile id, cell-geometry file id), with a versioned ACT model whose actuator-6 `forcerange` is τ_grip. v1 and v2 stay byte-identical and loadable.
- **Code that must follow the version:** `TERMINAL_STOP_CODES` and the `_teacher_execution_status` mapping (new codes, end states, `SIM_ORACLE_ABORT`); the manifest validator (`dynamic_manifest.py:252-277`) per policy version, so the v2 place-height checks stay with v2 and v3 gets its own record (θ, k, h_rel, τ_grip, q6_stall); the q6 sign convention (more negative = more closed) stated in the policy.
- **ACT data:**
  - datasets are partitioned by Teacher policy version;
  - v3 demonstrations differ: the close label (the torque-limited far command), the hover-release place, and the new dwells (q6 settle, frame collection, longer micro-lift);
  - earlier episodes remain diagnostic data.
- **Removed from the Teacher:** the `_enforce_safety` force/compression/collision/hazard stops, the `PhysicsHazardWatch` limits, `CollisionWatch` as a stop, `_require_supported_bilateral`, the contact-based waits, the sim scene-frame matching in the release source. Their computations move to the oracle.

## 12. Changes from draft 1 (first review, FAIL)

1. Finding 2 corrected. The position-shaped close is replaced by a torque-limited close past contact (§4.2, R2); τ_grip comes from a sweep plus an external gauge on the real arm (§9.2, §10).
2. The stall test is restated for the far command, with a band for 12-gon flats/corners, offset and quantization (§4.2).
3. Tracking error is removed from all gates, including the place unexpected-contact stop, until a servo model exists (§4.1, §4.6, §10).
4. h_rel includes a bias term (§4.6). Carry pose comes from pick-anchored kinematics plus the wrist-camera in-hand model (§4.4). The emulator models bias, correlated noise and occlusion (§6).
5. B07 is redefined for occlusion (§4.5). B08, the P11 v1/hash term, P15 and the manifest validator are assigned (§4.0, §4.7, §11).
6. OPEN_NOT_REACHED is end state D, with no arm motion. The VERIFY failure edge and all end states are defined (§4.3, §5).
7. The catastrophic oracle abort is kept as infrastructure status `SIM_ORACLE_ABORT`, configurable per run (§7).
8. Numbers set (§8). Live acceptance is PASS ∧ oracle-clean in all phases. The drop sweep is added with the ring site and wedge release. Hardware prerequisites are stated (§9, §10).

## 13. Decisions (CP-3394; the user may override)

1. Servo load/current: diagnostic only.
2. Hover release from ≈2–3 mm. Tipping is not credible: the tip angle is ≈42°, against 3–5.5° of tilt. Displacement is validated by the drop sweep.
3. Sim-only events never make a Teacher decision. A catastrophic oracle abort exists as an infrastructure status.
4. The emulator `realistic` profile with the §8 placeholders is the gating default until the real localizer is characterized.
5. Tracking-error gates are deferred until a servo model exists.
