# SO-101 ACT: Teacher speed, round 2 — plan

Status: CONFIRMED by the human on 2026-10-20 ("确认"). The human decided on 2026-10-20 ("先做提速再做第19项") that these speed-ups come before the item 19 qualification. Item 19 then qualifies the final Teacher.

## Where the time is now

EXP-631: final round-1 policy `teacher_execution_policy_side_wrist_fast_carry015.yaml`, 16 longest-carry scenes. The Teacher span averages 66.0 s.

| Phase | Mean | Setting |
| --- | --- | --- |
| MOVE_ABOVE_PLACE (carry) | 18.3 s | velocity 0.03, acceleration 0.015 |
| DESCEND_TO_PLACE (carry) | 11.8 s | same |
| MOVE_ABOVE_OBJECT | 10.8 s | 0.10 / 0.10 |
| DESCEND (to the grasp) | 8.3 s | 0.03 / 0.03 (no key) |
| LIFT (carry) | 4.4 s | carry |
| OPEN_GRIPPER / RETREAT / CLOSE_GRIPPER | 2.1 / 2.15 / 2.0 s | gripper 2.0 s hard-coded |
| Gaps between phases (planning) | about 3 s | |

At 0.015 the carry compression (113.20 µm) equals the 0.0075 value (113.33 µm), so acceleration does not drive compression. The carry velocity 0.03 is now the likely binding limit.

## Steps

Each step is validated before the next one starts. All acceptance rules are the existing ones; none is relaxed.

### S1. Carry velocity and acceleration DOE (no code)

- **Levels:** `carry_max_velocity_scaling` and `carry_max_acceleration_scaling` already are policy keys. Policy-file copies of carry015 differing only in those two keys:
  - level A: 0.05 / 0.02;
  - level B: 0.08 / 0.03.
- **Run:** the same 16 longest-carry scenes as R3, on the current gate.
- **Accept a level only with:** 0 oracle flags, p100 compression ≤ 115.5 µm, Teacher 16/16.
- **Stop:** at the first failing level. The final carry setting is the fastest accepted level.
- **Expected saving:** 5–10 s.

### S2. DESCEND in two stages and a faster OPEN_GRIPPER (code, Teacher policy schema 5)

**New keys.** Each one defaults to the current behaviour, so schema 3 and 4 files load and hash exactly as before:
- `descend_approach_velocity_scaling` / `descend_approach_acceleration_scaling`: the free-space part of DESCEND;
- `descend_final_distance_m`: the last part before the grasp pose, which keeps 0.03 / 0.03. The initial value is 0.02 m;
- `open_gripper_duration_s`: 2.0 → 1.0 s.

**Not changed:** CLOSE_GRIPPER, which shapes the grasp force, the waits and the contact policy.

**Development:**
- Write RED tests first, with fixtures only, then implement.
- Bundle the pytest tmp retention change into this step: `tmp_path_retention_policy = "failed"` in the repo pytest configs, and the AGENTS.md TMPDIR rule amended accordingly (human approval 2026-10-20).
- Then the full gate and new images.

**Validation:**
- **Debug 16** on scenes frm-000..015. It passes on all of these:
  - Teacher 16/16 and no oracle flag;
  - VALID ≥ 15/16 and no new INVALID class;
  - peaks per amendments 3 and 5 of the round-1 plan, with the reference EXP-625 ∪ EXP-627;
  - median endpoint not worse than EXP-625.
- **Contact spot checks**, nominal and over-squeeze; both judges must PASS.
- **DESCEND levels:** approach scaling 0.10 / 0.10 first, then 0.20 / 0.20 if 0.10 passes.
- **Expected saving:** 3–5 s (DESCEND) plus about 1 s (OPEN_GRIPPER).

### S3. Plan the place phases during the carry (code, output-neutral)

**Measure first:**
- Add phase marks around the planning and IK work in the gaps between phases.
- If the place-side IK or planning on the critical path is at least 1 s, precompute it during LIFT / MOVE_ABOVE_PLACE, as 18b does for the pick prefix.

**Proof:**
- The precomputed result is reused only when the start state matches within 1e-5 rad.
- It is shown bit-identical offline against the recorded documents.

**Not included:** 18c (reachability preflight overlapping PREPARE_OPEN). It changes when UNREACHABLE is decided.

**Expected saving:** 1.5–3 s.

### Not in this round

- 18i, blended trajectories: a large change of the trajectory generator. It is evaluated separately.
- 18h, the MOVE_ABOVE candidate count.
- 18j/k, the fixed waits.

## After S1–S3

- Run the item 19 qualification on the final Teacher policy:
  - R4: cap 4 / gap 30;
  - R5: cap 5 / gap 30;
  - R6: cap 5 or 6 / gap 20;
  - then a pooled repeat.
- Then the boundary search.

## Expected result

- The Teacher span goes from about 66 s to about 50–55 s on the long-carry scenes.
- The per-scene slot drops by the same amount.

## Amendments

1. **S1 result and the carry setting (coordinator decision, following the plan rule "the final carry setting is the fastest accepted level").** Levels A (0.05 / 0.02, EXP-632) and B (0.08 / 0.03, EXP-633) were both accepted, so the faster level B is taken. The S1 carry setting is `carry_max_velocity_scaling` 0.08 and `carry_max_acceleration_scaling` 0.03 (`teacher_execution_policy_side_wrist_fast_carry_b.yaml`). The schema 5 DESCEND files `teacher_execution_policy_side_wrist_fast_descend010.yaml` and `..._descend020.yaml` are regenerated from this file (carry keys 0.08 / 0.03 instead of carry015's 0.03 / 0.015); nothing else in them changes.
2. **S2 result and the final Teacher policy (coordinator rule: level 0.10 fails, so S2 is dropped; the salvage variant was tried on the coordinator's instruction).** EXP-634 (approach 0.10 / 0.10, `teacher_execution_policy_side_wrist_fast_descend010.yaml`): Teacher 16/16 but VALID 8/16, 7 scenes `TEACHER_ORACLE_EXCLUDED: ORACLE_CUP_OVERLOAD DESCEND`, 12 of 38 peak pairs outside the bound, DESCEND peaks up to 6.35 N and 210.5 um. Level 0.20 was not run. The salvage variant EXP-635 (`teacher_execution_policy_side_wrist_fast_two_leg_open_1s.yaml`: approach 0.03 / 0.03, two legs, final distance 0.02 m, `open_gripper_duration_s` 1.0) also failed: 6 of 16 VALID, 8 `ORACLE_CUP_OVERLOAD DESCEND` in 14 Teacher runs, peaks up to 6.22 N and 199.2 um. The contact begins in the approach leg at the same fraction (62 to 65 %) at both speeds, so the cause is the path (one long joint-space move instead of six interpolated waypoints), not the speed (`descend010-diagnosis.md`). The contact spot checks were not run (they follow a passing debug 16). **The final Teacher execution policy is `src/so101_demo_py/config/act/teacher_execution_policy_side_wrist_fast_carry_b.yaml` (schema 4, carry 0.08 / 0.03).** The schema 5 code and the three schema 5 policy files stay in the repository, unused; the schema 5 DESCEND two-leg path would need intermediate approach waypoints before it can be used, which is a separate change with its own requalification.
3. **S3 decision.** Planning and IK on the critical path of LIFT + MOVE_ABOVE_PLACE + DESCEND_TO_PLACE average 2.048 s per episode (EXP-634, 16 episodes; 1.949 s over 14 episodes in EXP-635), above the 1.0 s threshold, so a proposal was written (`s3-proposal.md`, not implemented). The proposal records that the 18b reuse rule (start state within 1e-5 rad) cannot fire for the place phases: the arm rests 5.9e-4 to 1.0e-3 rad away from the previous phase's last target. It asks for an offline differential before any code.
4. **Gate tool.** The repository gate `scripts/gate/run_host_gate.zsh` was found equivalent to the v4 gate at the same commit and green, and is the gate from now on (CP-3759).
