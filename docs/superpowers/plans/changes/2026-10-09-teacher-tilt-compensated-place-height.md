# Teacher: tilt-compensated place height (design only; no code is changed by this document)

Date: 2026-10-09 (ledger CP-3480; decision CP-3394, recommended fix 1)

Status: **DESIGN FOR INDEPENDENT REVIEW. Nothing is implemented. Do not implement until the reviewer's verdict.**

## 1. Problem and evidence

A Teacher run stopped in DESCEND_TO_PLACE with `DYNAMIC_CUP_FORCE_EXCEEDED` (1.94 N against the 1.8916 N limit; run `392e7925`, step 41943). Since the r10b limits there are 46 PASS runs and 1 such stop (2.1%, 95% CI about 0.4-11%). Findings: `handoffs/.../teacher-force-stop-20261009/` (scripts `an1`-`an5`, the 20 retained-bag dumps, `teacher_runs_since_20261007.tsv`).

- The failing run's pre-contact state equals the 20 retained PASS bags (cup xyz +-0.1 mm, tilt 4.04 +- 0.03 deg, joints +-0.2 mrad, hold 1.538 N, no grasp slip). The cup carries about 4 deg of tilt (1.5 deg after the micro-lift, 2 deg after the lift, 4 deg above the place), so its lowest rim point reaches the table before the arm finishes the descent: first table contact comes **0.61-0.64 s before DESCEND_TO_PLACE ends** while the arm keeps moving down at about 3.5 mm/s (about 2.2 mm of loaded overtravel).
- In the PASS runs the loaded overtravel unloads smoothly (1.54 N hold to 0.87 N). In the failing run it bifurcated into contact chatter (table contact flicker, the moving-jaw contacts 8-4-0-14, force alternating left/right every 0.1-0.15 s, penetration 154-214 um, the cup climbing about 11 mm, per-step peak 2.495 N, 88 single-step spikes, 10 ms average 1.71 N). Ruled out: ring or pedestal hit, pose or target error, carry slip, perception.
- The check (`ros/teacher_safety.py`): summed normal force of the left and right fingertip contacts and the other cup contacts above 1.8916 N, or compression above 119.28 um, in every Teacher state, on the 100 Hz evidence path and the 500 Hz chunk path (`PhysicsHazardWatch`, about 0.1 s later).
- PASS margins: the DESCEND_TO_PLACE peak is 1.658 N (87.6% of the limit) in all 20 bags; the worst carry peak is 1.712 N (LIFT, 90.5%); compression 105-109 um (88-91%).

**Checked while writing this design (the 20 retained bags, step records):** the first cup-table contact of DESCEND_TO_PLACE happens at cup centre z = 0.16770 m (sd 0.01 mm, tilt 4.04 deg); the cup ends the descent at z = 0.16705 m, 0.65 mm below first contact. The ACT cup's bottom collision geom is a **round cylinder** (`bottom_collision`, radius 0.040 m, half-thickness 0.001 m, centred 0.044 m below the body origin, so the bottom face is c = 0.045 m below it), not the 12-gon of the walls. For a cylinder tilted by theta the lowest point is a point of the bottom rim in the tilt direction whatever the azimuth, so

    z_touch(theta) = z_table + c cos(theta) + r sin(theta)      with z_table = 0.12, c = 0.045, r = 0.040

which gives 0.12 + 0.044888 + 0.002818 = **0.167706 m at 4.04 deg**, against 0.16770 measured. The formula is exact for this cup; the 12-gon is irrelevant to it (only the walls are 12-gon, and they do not touch the table).

## 2. Design

Aim the descent so that it **ends at touchdown** instead of continuing through it: raise the DESCEND_TO_PLACE target by the loaded overtravel the tilt causes. No limit is relaxed and the force metric is not filtered (the chatter is real instability; hiding it would hide a real load).

### 2.1 What is measured, and when

At the start of `DESCEND_TO_PLACE` (after MOVE_ABOVE_PLACE has stopped: there is no WAIT state between them, so the measurement is a short stability window inside the DESCEND_TO_PLACE step, before the trajectory is planned), from the Teacher's own world observer (independent of the recorder):

- `theta`: the cup's tilt from the observer's orientation (`_upright_tilt_rad`, `dynamic_mujoco_execution.py` about line 995), as the median of a 100 ms window of fresh evidence samples whose tilt range inside the window is under 0.05 deg (`_wait_stable`, about line 1032). A window that never settles within 1 s refuses (`TEACHER_PLACE_TILT_UNSTABLE`), before any motion.
- `k = z_tcp - z_cup`: the TCP height above the cup centre at the same instant (TCP from the forward kinematics of the controller state the Teacher already uses for its corridor checks, cup from the evidence). It is measured, not taken from the template, because the template relation (hover 0.2176344 m for a cup centre at 0.18002 m: 0.0376 m) and the one the current target implies differ by about 1.3 mm (grasp compliance; inferred, not measured) and the slip in the grasp stays below 0.4 mm.

### 2.2 The target

    z_tcp_target = z_touch(theta) + k - g

`g` (the touchdown guard, metres, `place_touchdown_guard_m`) keeps the final pose a little below first contact so the release-support check sees a loaded, stable contact (force above 0, distance within 0.002 m, both fingertips). It replaces the 0.5 mm margin of the current constant. It is chosen by the offline sweep of section 6 (expected 0.2-0.6 mm) and frozen with the policy; the compensated target is never below `z_touch + k - g_max` (`g_max` 1.0 mm).

Everything else about the descent is unchanged: MoveIt planning, the carry scaling (0.03 / 0.0075), the corridor check (0.008 m deviation), the stop and the 3.5 mm/s final velocity.

### 2.3 Bounds, fail closed

All checked before the DESCEND_TO_PLACE goal is sent (no new motion, a refusal with a named code, the same family as `TEACHER_POLICY_UNAVAILABLE`):

- `theta` within the calibrated range `[theta_min, theta_max]` in the frozen policy. Initial proposal 3.0-5.5 deg: the retained evidence is 4.02-4.07 deg only, and the range is widened only when the offline sweep (section 6) qualifies more. Outside: `TEACHER_PLACE_TILT_OUT_OF_RANGE`.
- `k` within a calibrated band (initial: 0.036-0.041 m around the 0.0389 m that the current target and the 2.2 mm overtravel imply: 0.2176344 - 0.01325 + 0.0022 - 0.16771; to be replaced by the value measured in the sweep).
- The target within 6 mm of the current constant-offset target for the same pose, within the workspace bounds and the corridor limits; otherwise `TEACHER_PLACE_HEIGHT_OUT_OF_BOUNDS`.
- The cup radius, half height and table height used by `z_touch` are read from the frozen scene model (`assets/mujoco/act/scene.xml`, by hash) rather than hard-coded, and `core/place_height.py` has a test that recomputes `z_touch` from the MJCF geometry.

### 2.4 Where it lives

- New pure module `core/place_height.py`: `touch_center_z(theta, table_z, half_height, rim_radius)`, the bounds, the target computation and the audit document. No ROS import; unit-testable and replayable offline.
- `ros/dynamic_mujoco_execution.py`: `_place_target` (about line 2193), which today adds the constant `place_descend_offset_m` for DESCEND_TO_PLACE with frozen inputs, takes the computed target instead; a new `_measure_place_height()` is called at the start of the DESCEND_TO_PLACE step. `core/dynamic_pick.py` `resolve_motion_targets` is unchanged (the policy place TCP stays the hover used by MOVE_ABOVE_PLACE and RETREAT).
- Frozen Teacher policy (`config/act/teacher_execution_policy_v1.yaml`, loader `act/teacher_endpoint.py`): v2 adds `place_height_mode: tilt_compensated`, `place_touchdown_guard_m`, `place_tilt_range_rad`, `place_grasp_offset_range_m`, `place_target_max_deviation_m`; `place_descend_offset_m` stays for the non-compensated mode (plain pick-place, v1 inputs). The policy hash and the Teacher manifest change, so a new freeze and new candidate receipt are needed.
- Audit: the Teacher manifest and the `phase_begin` event of DESCEND_TO_PLACE carry the measured `theta`, `k`, the computed `z_touch`, the target and `g`, so the QC and the review can recompute them.

## 3. Effect on the checks (and what is re-qualified)

| Check | Effect | Re-qualification |
| --- | --- | --- |
| Force and compression limits (1.8916 N, 119.28 um) | Unchanged, same states, same paths, not filtered. The loaded overtravel that the cup had to absorb disappears; the transient above the hold level should too. | Compare the DESCEND_TO_PLACE force and compression distributions before and after (section 6). |
| Release support before OPEN_GRIPPER (cup-table contact, force above 0, distance within 0.002 m, both fingertips; `DYNAMIC_RELEASE_SUPPORT_NOT_PROVED`) | The descent now stops at touch minus `g` instead of 0.65 mm into the table. The risk is a descent that stops just short of a stable contact. | The offline sweep of `g` and `theta` must show support true in every case with margin on both sides, and the same for the 12 ms world samples the check reads. This is the check most at risk. |
| Endpoint (`teacher_endpoint`, tolerances `initial_position_m` 0.010, `final_z_m` 0.010, final xy) | The final cup pose after the release is where the cup settles; the descent target changes by about 2 mm, the settle point does not. | Re-run the endpoint evaluation on the offline replay's final poses and on the live runs; the final z error stays within its 0.010 m tolerance with the margin it has today. |
| `VALIDATE_FINAL_PLACEMENT` (xy <= 0.02, z in 0.155-0.175, upright tilt <= 0.15 rad, table contact, no fingertip contacts; audit-only) | Unchanged limits. | Same replay and live evidence. |
| Corridor (0.008 m) and the MoveIt tolerance (0.002 m) | The target moves by about 2 mm; the corridor is measured against the new waypoint. | The planner and corridor run on the offline joint states before the live runs. |

## 4. ACT demonstration

The place-phase end of the demonstration (the last 0.6 s of the descent) ends about 2 mm higher and the arm is nearly still when the cup touches; the joint-space actions of that segment change by sub-milliradian amounts and the segment no longer contains a push into the table. Earlier phases and the labels of earlier phases are unchanged. No formal collection has been recorded yet, so no old demonstrations mix with new ones; the manifest field `place_height_mode` (and the policy hash) stamps every episode with the mode so a future dataset can refuse to mix them. The QC reads the target through the Teacher manifest; its checks do not depend on the constant.

## 5. Rejected alternatives

- Slower last 5 mm of the descent: only makes the bifurcation rarer, and the cup would still be loaded when it happens.
- A lower gripper close target (less grip force at the place): needs the whole grasp re-qualified (stability, slip, carry margins at 90%).
- Filtering the force metric or relaxing the limit: hides a real instability (88 single-step spikes, a cup climbing 11 mm); explicitly excluded.
- A fixed larger offset: the touch height depends on the tilt (0.38 mm per 0.5 deg); a constant is right only for the tilt it was fitted at (the current -13.25 mm was fitted offline at 3.5 deg; the live tilt is 4.04 deg).

## 6. Validation plan

**Offline (decides the parameters and the acceptance):**

1. Geometry: `core/place_height.py` against the 20 retained bags (first-contact z predicted within 0.05 mm, measured 0.16770 against 0.167706), and against a MuJoCo rest simulation of the cup tilted from 0 to 7 deg held in the table (every azimuth).
2. Place-descent replay with the real actuators (`writer-artifacts/r11-exp/place_descent.py`, aligned model, live carry joints, held cup, validated before: offset 0 gives cup z 0.18012 against 0.18002 live), on the retained carry states of the 20 bags: (a) reproduce the old constant-offset descent and **count contact-chatter bifurcations under small seeded perturbations** (initial joint noise of the observed 0.2 mrad, pad friction and damping within the model's calibration spread; some hundreds of trials) until the old rate (about 2%) is visible; (b) the same trials with the compensated target and a sweep of `g` (0, 0.2, 0.4, 0.6, 1.0 mm) and of `theta` (3.0-5.5 deg by changing the micro-lift seed). Metrics per trial: peak summed force and compression in the window, support true at the end, number of table-contact flickers, cup climb. Acceptance: no bifurcation in the compensated trials where the old target shows them, support true in all, peak force minus the hold level at most 0.03 N, compression at most the carry level, and the whole `g` choice with margin on both sides (the smallest `g` that is supported everywhere plus half of the width of the supported range).
3. Bounds: the refusal paths (tilt, `k`, deviation) with synthetic evidence in unit tests (RED first).

**Live (confirms, cannot prove a 2% effect):** N = 20 Teacher runs (collection off, same pose each time as the retained bags) with the force-margin distribution per run: peak force and compression in DESCEND_TO_PLACE, the first-contact-to-end time, the touchdown height against `z_touch`. Acceptance: no force stop; the first contact within 0.3 mm of the prediction; the overtravel window (contact to end of descent) under 0.15 s against 0.62 s today; the DESCEND_TO_PLACE peak falls from 1.658 N to the carry hold level. **Note the floor: the hold force of the grasp is 1.538 N (81.3% of the limit) and is part of the DESCEND_TO_PLACE window, so the peak cannot fall below it. The expected result is "peak minus hold at most 0.03 N" (a 1.658 N peak today is 0.12 N above the hold), not an absolute figure well below 1.658 N.** Twenty clean runs bound the failure rate only at 14% (95%, rule of three); the offline bifurcation sweep, not the live count, is the evidence that the mechanism is gone.

## 7. Open points for the reviewer

1. Is measuring `k` live (from evidence and forward kinematics) acceptable, or should `k` stay a frozen template constant with the 1.3 mm difference absorbed by `g`?
2. The initial tilt range and `k` band are proposals from one operating point (4.04 deg); widening them needs the sweep. Is a narrow initial range with a fail-closed refusal the right default for the randomized-start collection, where the tilt may vary?
3. `g` below 0.2 mm would leave the support check with almost no margin; is 1.0 mm the right ceiling?
4. The hold force is the floor of the DESCEND_TO_PLACE peak. Should the acceptance be stated against the hold-relative transient, as above, in the ledger?
5. Policy v2 changes the policy hash and the Teacher manifest: confirm that a new freeze and candidate receipt are in scope for the implementation round.
