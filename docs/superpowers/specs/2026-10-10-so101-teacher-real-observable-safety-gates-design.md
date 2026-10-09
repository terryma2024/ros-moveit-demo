# SO-101 Teacher: real-observable safety gates (design)

Date: 2026-10-10
Status: DRAFT for independent review. Not implemented.
Ledger: CP-3497 (user request and assumptions), CP-3498 (this draft).
Inventory this design is based on: `/data/work/so101-evidence/act-data/20260924-fbc25063-resume/handoffs/teacher-act-decoupling-20261005.1RmsJ3ZJ/real-observable-gates-20261010/inventory.md` (row IDs S01–S14, B01–B18, P01–P23, E01–E02 below refer to it).

## 1. Requirement

The user's statements (2026-10-10):

- "在抓取动作过程中的安全校验规则需要遵循一个事实：实际的机械臂没有接触力反馈。我们需要以此原则重新设计抓取过程的安全校验门。"
- "我们可以假定 杯子真值位姿可以获取到，真实场景可以通过视觉定位。"

So every gate that stops, refuses, authorizes or branches the Teacher must be decidable from signals the real SO-101 cell provides. The signal classes are below.

| Class | Signals | Role in this design |
|---|---|---|
| Real-observable (R) | joint positions and velocities (encoders), commanded targets and tracking error, gripper position q6 (including where a close stalls), cup pose from visual localization (velocity by differencing), MoveIt scene state, time | May gate the Teacher |
| Diagnostic-only | STS3215 present load, current, temperature | Recorded; never a gate. They are coarse, uncalibrated and not contact force |
| Sim-only (S) | contact forces, fingertip compression, contact pairs, table-support distance, physics chunks, simulator session/epoch plumbing | Never gate the Teacher. They become the **sim oracle**: data QC and the referee for gate quality |

## 2. Findings that drive the design (from the inventory)

1. Today the stops that actually protect the cup and the robot are all S: the force/compression/hazard stops (B09–B11), the collision pairs (B13), and the release support proof (P16). The release proof also authorizes recovery opening, so a recovery that cannot prove table contact strands the cup in the gripper (P23).
2. The grasp is set by a close target far past contact (P03): the jaw stalls on the cup at saturation torque, and only the S force/compression stops bound the squeeze. On the real STS3215 the same command would press the cup at the servo's torque limit. Nothing observable bounds it.
3. The grasp checks that are real-observable in substance are advisory today: the micro-lift and VERIFY_PHYSICAL_GRASP lift proofs (P05, P07) are audit-only, WAIT_MICRO_LIFT_STABLE has no check (P06), and nothing reads q6 after CLOSE_GRIPPER (B06).
4. Place: v2 drives the cup about 0.7 mm past first table contact to create support for the contact-based release proof (P10–P12, P16). The guard comes from a sim force sweep, and it needs cup-z accuracy of about 0.1 mm. A visual localizer gives 1–3 mm. Pressing the cup into the table is also the mechanism behind the place-phase force/compression stops (CP-3480, CP-3494).
5. The sim Teacher reads a noise-free 100 Hz cup pose. Several thresholds (the 0.05°/100 ms tilt window, the 1 mm/s settle window, 1 mm lift proofs) only mean something at that accuracy (inventory §3).
6. Stops raised by `_enforce_safety` only run during a goal or a wait, so states without a goal never raise a latched hazard (inventory §0).

## 3. Principles

- **R1 Gates are real-observable.** Every stop, refuse, authorize or branch decision reads class-R signals only, plus geometry constants measured on the cell (table height, cup geometry), which are versioned like the policy.
- **R2 Bound force by construction, verify by outcome.** With no force sensor, the squeeze and the table load are bounded by how the actuators are commanded (position offsets, speeds, the servo torque limit). Gates verify the observable outcome (where the jaw stalled, where the cup is, whether the arm tracked).
- **R3 Never load the table with the held cup.** Release from a small, bounded clearance above the table instead of pressing to prove support (§4.6).
- **R4 The sim oracle never controls the Teacher.** S signals are recorded and used for episode data QC and as the referee that measures how well the R gates work. A sim-only event no longer stops the run. It marks the episode for QC.
- **R5 Gates are tuned for a realistic localizer.** In sim the Teacher's cup pose passes through a localizer emulator (rate, latency, noise, exposure stamps) so the gates and their thresholds are exercised with real-like information (§6).
- **R6 Every gate fails closed and has a defined safe end state.** Holding the cup at a safe pose is the safe state when release cannot be authorized; recovery must not depend on an S proof.

## 4. Gate catalogue (by phase)

Codes are new unless noted. "STOP" means terminal stop as today (TERMINAL_STOP_CODES, `STOPPED_SAFETY`). "RECOVER" means the state's failure edge. Thresholds marked † are set from the validation sweeps (§8) and frozen in the policy.

### 4.0 Preflight (IDLE)

Keep S01–S03, S06, S07, S10, S11, S14 unchanged (all R).

- S05 replacement: `TEACHER_CUP_LOCALIZATION_DISAGREE`. Head-camera and wrist-camera localizations must agree within 10 mm / 0.10 rad. It replaces the comparison against simulator truth (S05's sim part). In sim both come from the localizer emulator with independent noise.
- S12: the place-geometry constants (table top z, cup bottom radius r, bottom offset c) become a versioned cell-geometry file. In sim they are checked against the MJCF hash as today; on the real cell against a measured file.
- S04, S08, S13 identity checks stay as simulation infrastructure (they do not exist on the real cell and are not safety gates).

### 4.1 Approach (MOVE_ABOVE_OBJECT, DESCEND)

- B01–B05 unchanged (R).
- `TEACHER_TRACKING_ERROR_EXCEEDED` (STOP): per-joint |commanded − measured| above a speed-scaled bound† for at least 30 ms. This is the collision proxy that replaces B13. In sim the arm's position servos are stiff (kp 998), so the bound is set from sim measurements and re-measured on the real arm. It cannot see a soft contact that does not deflect the arm.
- B14 becomes a gate: `TEACHER_CUP_MOVED_BEFORE_GRASP` (RECOVER: retreat, re-localize, re-plan). The cup moved more than 5 mm from its preflight pose before CLOSE_GRIPPER, averaged over ≥5 frames.

### 4.2 Close (CLOSE_GRIPPER, WAIT_GRASP_STABLE)

- **Shaped close command (R2).** q6_cmd = q6_contact(cup width) − Δ_squeeze, where q6_contact is the jaw angle at which the pads touch a cup of the nominal width (from pad geometry, calibrated per cell), and Δ_squeeze† is a small bounded offset. With a position servo the steady squeeze is bounded by kp·Δ_squeeze and the torque limit. In sim, Δ_squeeze is chosen so the oracle's hold force and compression keep a stated margin to the r10b oracle limits (§7). This replaces the fixed far-past-contact target −0.0476 rad.
- After the close settles (q6 velocity below a threshold† for 250 ms, time-limited), read the stall angle q6_stall:
  - `TEACHER_GRASP_MISSED` (RECOVER: open, retreat): q6_stall within tolerance of q6_cmd, so the jaw closed on nothing.
  - `TEACHER_GRASP_WIDTH_OUT_OF_BAND` (STOP after opening, see 4.8): q6_stall outside [q6_contact − band†, q6_contact + band†], which means a wrong object, a deformed cup or an off-centre grasp.
- WAIT_GRASP_STABLE becomes this q6 settle wait. The contact-based bilateral wait (P04) moves to the oracle.

### 4.3 Micro-lift and verify (MICRO_LIFT, WAIT_MICRO_LIFT_STABLE, VERIFY_PHYSICAL_GRASP)

- Add a real stability wait in WAIT_MICRO_LIFT_STABLE: the arm stopped (encoder velocities) and ≥ N† localizer frames collected.
- `TEACHER_GRASP_NOT_LIFTED` (RECOVER: lower, open, retreat). Gate, no longer audit: Δcup_z (mean of ≥5 frames after the lift minus mean before) must follow Δtcp_z (FK) within tolerance†. Comparing the two changes cancels the hand-eye bias. q6 must be unchanged within tolerance†.
- ATTACH_MOVEIT only after this gate passes.

### 4.4 Carry (LIFT, MOVE_ABOVE_PLACE, recovery carries)

- `TEACHER_CUP_SLIP` (STOP, cup held): the cup pose relative to the TCP frame (FK) drifts more than tolerance† from its value at VERIFY (position and tilt), sustained over ≥3 frames.
- `TEACHER_CUP_DROPPED` (STOP): the cup pose leaves the gripper neighbourhood, or the localizer reports the cup on the table, during carry.
- q6 change beyond tolerance† gives `TEACHER_GRIPPER_POSITION_CHANGED` (STOP).
- Tracking-error stop as in 4.1.
- B15/B16 (contact-based) move to the oracle.

### 4.5 Pre-place measurement (start of DESCEND_TO_PLACE)

- Keep the v2 idea of using the measured tilt to find the cup's lowest point, but measure it as a mean over ≥10 localizer frames with a drift bound† instead of the 0.05°/100 ms range window. Refusal codes stay `TEACHER_PLACE_TILT_UNSTABLE` and `TEACHER_PLACE_TILT_OUT_OF_RANGE`.
- The cup-to-TCP offset k is measured live from the localizer, as a mean of frames, with its uncertainty. The k band is set from localizer noise, not from µm-level sim truth.

### 4.6 Place descent: hover release (R3)

- Target: the cup's lowest point ends at clearance h_rel above the table top, where h_rel = h_min† + 3·σ_z,est (the localizer's estimated z uncertainty for this measurement). Example: σ_z 1 mm gives about 3–4 mm.
- The descent ends at the computed target. It never commands below table-top + h_min, so the held cup is never pressed into the table (R3).
- `TEACHER_PLACE_UNEXPECTED_CONTACT` (STOP, cup held, lift 10 mm): a tracking-error rise during the final descent, or the cup moving relative to the TCP. Either means the cup met the table (or something else) earlier than predicted.
- This replaces the v2 overtravel guard and the place-height window that came from the sim force sweep. The tilt-dependent lowest-point geometry (`core/place_height.py`) is kept.

### 4.7 Release (DETACH_MOVEIT, OPEN_GRIPPER, WAIT_RELEASE_SETTLE)

- Release authorization (replaces P16 `DYNAMIC_RELEASE_SUPPORT_NOT_PROVED`), all R:
  1. Arm stopped: the P14 normal-stop proof (encoder velocities), kept.
  2. Cup static in the gripper: cup-relative pose stable over ≥ N† frames.
  3. Cup lowest point within [table + 0, table + h_rel + 2σ_z] from frames exposed after the stop confirmation (P15's intent, using exposure stamps instead of sim step matching).
  4. Tilt below tolerance†.
  Failure gives `TEACHER_RELEASE_NOT_AUTHORIZED` (STOP, cup held, lift to safe height).
- Open to q6_open, then read q6. `TEACHER_GRIPPER_OPEN_NOT_REACHED` (RECOVER) if q6 does not reach the open position within tolerance.
- Settle (P20 R-version): the cup is on the table, which means the cup z mean is in the resting band, tilt is at most tolerance†, and a linear fit over ≥1 s and ≥15 frames gives speed ≤ 1 mm/s and ≤ 0.05 rad/s. Timeout stays audit, and the endpoint verdict decides the task.
- The contact-based release proof, bilateral checks and fingertip-empty checks move to the oracle.

### 4.8 Retreat, final placement, end of run

- RETREAT: tracking-error stop. `TEACHER_CUP_DISTURBED_ON_RETREAT` (audit) if the cup moved more than 5 mm.
- P21 final placement: pose terms only (R). Contact terms move to the oracle.
- E01/E02 endpoint verdict: unchanged (pose only). On the real cell the settle clock uses wall time.

### 4.9 Recovery

- RECOVER_OPEN_GRIPPER uses the same hover-release authorization as 4.7. Recovery returns the cup to a hover over the pick location (or the place location) and releases from h_rel. A recovery therefore no longer depends on an S proof and no longer strands the cup when contact cannot be proved.
- When even the R authorization fails, hold the cup at a safe height and stop (`STOPPED_SAFETY`). The operator decides.

## 5. Simulation integrity (not a Teacher gate)

Numerical integrity (non-finite state, solver blow-up, physics chunk gaps) remains a simulator-infrastructure abort. It ends the episode as an infrastructure failure, not as a Teacher safety stop. It is not a substitute for any physical protection.

## 6. Localizer emulator (R5)

- In sim, the Teacher's cup pose comes from an emulator fed by simulator truth, configured by a versioned profile:
  - rate (e.g. 15–30 Hz);
  - latency (e.g. 50–100 ms) with exposure stamps;
  - per-axis position noise (e.g. σ_xy 1 mm, σ_z 1 mm);
  - orientation noise (e.g. σ_tilt 0.5°);
  - dropout probability.
- Two profiles: `ideal` (today's behaviour, used only for regression comparison) and `realistic` (the default for gating). The numbers are placeholders until the real localizer is characterized. The design records which gates are sensitive to which numbers (inventory §3).
- The emulator affects only the Teacher's control input. The recorded data keeps the simulator truth streams for QC.

## 7. Sim oracle and data QC

- All S signals stay recorded. The QC gains oracle verdicts that make an episode INVALID for training, never stop the Teacher:
  - `ORACLE_CUP_OVERLOAD`: summed force or compression above the r10b limits, which now act as oracle thresholds;
  - `ORACLE_COLLISION`: a robot contact pair outside the process pairs;
  - `ORACLE_UNSUPPORTED_RELEASE_TIP`: the cup tips or falls on release;
  - `ORACLE_GRASP_LOST`: bilateral contact lost during carry.
- The r10b calibration stays frozen with its fingerprint, but its role changes from Teacher stop limits to oracle QC thresholds. The activated-policy machinery (S09) moves to the QC side.
- Gate quality metric: for each gate, a confusion matrix against the oracle over the validation sweeps (§8). A miss is an oracle event the gate did not catch; a false stop is a gate stop with no oracle event.

## 8. Validation

1. Offline unit and replay tests per gate, including replays of the existing live bags (the 40+ retained runs) through the new gate logic with the realistic emulator profile. The new gates must not stop any run the oracle calls clean, beyond a false-stop budget†.
2. Sim sweeps with fault injection, oracle as referee, ≤500 trials per setting:
   - cup pose error and localizer noise up to the profile limits;
   - grasp offset;
   - missed grasp (cup removed before close);
   - wrong-width object;
   - slip injection (friction drop in carry);
   - obstacle collision;
   - tilt variance;
   - hover-release drop from h_rel over the tilt range (tip rate).
   Acceptance: each safety gate's miss rate ≤ target†, with zero misses on overload, collision and drop injections at the frozen thresholds, and the false-stop rate ≤ budget†.
3. Live rounds:
   - 20 runs at the default point, collection on;
   - Teacher PASS ≥ the current rate (19/20);
   - zero `ORACLE_CUP_OVERLOAD` in DESCEND_TO_PLACE (hover release removes the table load);
   - VALID rate unchanged.
   Then the randomized-domain gate work for formal collection.
4. Independent review of this design before implementation, and of the code before freeze.

## 9. Impact

- ACT demonstrations change:
  - the gripper close label (shaped target instead of −0.0476 rad);
  - a hover-release place (short drop instead of press);
  - new dwell periods (q6 settle, frame collection for the lift and tilt means).
  Earlier episodes stay valid as diagnostic data but are a different demonstration distribution.
- Policy versioning: Teacher execution policy v3 (gate thresholds, Δ_squeeze, h_min, emulator profile id, cell geometry file). v1 and v2 stay byte-identical and loadable.
- The data side (offline processor, QC) gains the oracle verdicts. Topic-loss, readback and the export rules are unchanged.
- Removed from the Teacher: `_enforce_safety` force/compression/collision/hazard stops, `PhysicsHazardWatch` limits, `CollisionWatch` as a stop, `_require_supported_bilateral`, the contact-based waits. They are replaced as above, and their computations move to the oracle.

## 10. Decisions taken with this draft (CP-3394; for the user to override)

1. Servo load and current are diagnostic only, not gates.
2. Release is a hover release from a bounded clearance (R3), not press-to-contact. The alternative, a slow stop-on-tracking-error contact descent, is rejected as primary: at the arm's stiffness the tracking-error rise at table contact is sub-mrad in sim, below the STS3215 encoder resolution (≈1.5 mrad), so it cannot be detected reliably. It is kept only as the unexpected-contact stop in 4.6.
3. Sim-only events no longer stop the Teacher. They invalidate the episode through the oracle QC. Only numerical integrity aborts.
4. The localizer emulator `realistic` profile is the gating default. Its numbers are placeholders until the real localizer is characterized.

## 11. Open questions for review

- Is a 3–4 mm hover-release drop acceptable for the cup (tip risk at 3–5.5° tilt), or must h_rel be tighter, which needs a better σ_z?
- Can q6_contact and the stall band be calibrated well enough in sim, and how will they be calibrated on the real gripper (pad compliance, gear backlash)?
- Should the oracle still abort a run on a catastrophic overload (e.g. sim crush) to save time, as an infrastructure action, while keeping it out of the Teacher's decision?
- Does replacing collision pairs with tracking error leave an unacceptable gap for soft collisions with the cup (knocking it before the grasp)? The cup-moved gate (4.1) partly covers it.
