# Teacher: a lighter carry grip (design for review; nothing is implemented)

Request: CP-3494 decision (a), after the first place-phase safety stop under policy v2 (recorder_absent `008b058f`,
`DYNAMIC_CUP_COMPRESSION_EXCEEDED`). Status: **design and offline sweep only**. The sweep does not support the premise of the request,
so this document reports the result, specifies the one variant that could still be built (section 6) and recommends against building it.

## 1. Problem

The cup is carried with a summed fingertip force of 1.54 N and a fingertip compression of 97.5 um, 81.7% of the 119.28 um limit (r10b).
A touchdown that bounces (contact lost on the table and on one fingertip, the cup rotating in the grip) added +41 um in the stopped run
(97.5 -> 139 um, right fingertip contact count 0, table contact false, cup velocity 12 mm/s, rotation 0.2 rad/s). The margin before the
chatter is 22 um. The aim was a carry compression low enough that the same excursion stays under 85% of the limit (101.4 um) in every run.

## 2. Method

The offline model is the aligned ACT scene with its real actuators and the held cup (`place_sweep_base.py` of the v2 sweep), driven
through the real sequence: close (2 s), MICRO_LIFT, LIFT and the six MOVE_ABOVE_PLACE segments of the live joint plans, then the place
descent with the measured time law of the live descent, a command delay of 0-10 ms and 2 urad of command noise. At the nominal target it
reproduces the live carry: hold 1.537 N (live 1.5386), compression 97.5 um (live 97.5), tilt 3.92 deg (live 4.04), k 37.32 mm (live
37.45), LIFT peak 1.675 N (live 1.712), minimum single-side force at the micro-lift 0.052 N (the slip minimum, ~0.053).

The target is the `gripper_close_target_rad` of the policy (-0.047608632840292 rad, a position target of actuator `6`: kp 998 N m/rad,
force limit 3.35 N m). Trials per setting: one deterministic carry chain, 100 jittered descents (no disturbance) and 40 bounce trials
(20 seeds x 2 disturbance sizes), at most 140 per setting (limit 500). The sweep scripts and outputs are in
`/tmp/so101-debug-cp3394-c5/p8/grip/` (`grip_base.py`, `grip_chain.py`, `kick.py`, `grip_sweep.py`).

**The model does not reproduce the live bifurcation by itself.** None of the 100 undisturbed descents chatters (peak above hold 0.039 N,
the live PASS value 0.040 N), as in the v2 sweep. The chatter is therefore represented by a disturbance applied to the cup at the first
table contact: the observed velocities of the stopped run (linear -0.011, -0.024, -0.012 m/s, angular 0.20, -0.05, -0.004 rad/s) at 0.5x
and 1.0x. At the nominal grip these give +39.6 um and +34.5 um of compression (peak 137 and 132 um, 115% and 111% of the limit) with
the right fingertip lost, which is the live signature (+41 um, 139 um). It is a surrogate for the margin, not a failure rate.

## 3. Result: the carry force is a wedge, not a squeeze

Phases at the nominal target:

| Phase | Summed force | Compression | Cup tilt | Min single-side force |
| --- | --- | --- | --- | --- |
| End of CLOSE_GRIPPER | 0.23 N (one side only) | 34 um | 0.4 deg | 0 |
| End of MICRO_LIFT | 1.57 N | 100 um | 1.6 deg | 0.052 N |
| LIFT (peak / end) | 1.675 / 1.573 N | 106 / 100 um | 1.8 deg | 0.77 N |
| End of MOVE_ABOVE_PLACE (hover) | 1.532 N | 97.5 um | 3.9 deg | 0.76 N |

The gripper is commanded to be just closed on the cup (0.23-0.36 N at the end of the close). The 1.5 N appears when the cup leaves the
table: it hangs between the pads, rotates in the grip and wedges, and the force stays at that equilibrium through the carry. It is a
property of the geometry and the cup weight, not of the jaw command.

### 3.1 Static close target

| Target (rad) | Hold force (N) | Compression (um) | Tilt (deg) | k (m) | Cup slip in the grip (mm) | LIFT peak (N) | Cup carried |
| --- | --- | --- | --- | --- | --- | --- | --- |
| -0.0476 (nominal) | 1.537 | 97.5 | 3.92 | 0.0373 | 1.6 | 1.68 | yes |
| -0.0472 | 1.532 | 97.1 | 4.09 | 0.0375 | 1.8 | 1.67 | yes |
| -0.0468 | 1.500 | 95.0 | 4.14 | 0.0464 | **10.5** | 1.57 | slips (k +9 mm) |
| -0.0464 | 1.470 | 93.1 | 4.28 | 0.0541 | **18.3** | 1.56 | slips (k +17 mm) |
| -0.0460 and above | 0 | 0 | - | - | cup lost at the micro-lift | 0.05-0.11 | **no** |

Raising the target by 0.0004 rad changes nothing; by 0.0008 rad the cup slips 10 mm in the grip and k
leaves the v2 band by 9 mm; by 0.0012 rad the cup is lost. Targets below -0.0476 only raise the force (at the close: 0.36 N at -0.0476,
1.3 N at -0.049, 5.7 N at -0.052). The window in which the cup is carried at a calibrated pose is 0.0004 rad wide; **no value of the
close target lowers the hold force or the compression by more than 1.5%**.

### 3.2 Relaxing the jaw at the hover (a second command before DESCEND_TO_PLACE)

The jaw target is raised by `relax` over 0.5 s at the end of MOVE_ABOVE_PLACE, then held 0.5 s:

| Relax (rad) | Hold force (N) | Compression (um) | Tilt (deg) | k (m) | Cup z change (mm) |
| --- | --- | --- | --- | --- | --- |
| 0 | 1.537 | 97.5 | 3.92 | 0.0373 | 0 |
| 0.002 | 1.509 | 95.7 | 4.77 | 0.0379 | -0.6 |
| 0.004 | 1.503 | 95.3 | 5.62 | 0.0385 | -1.2 |
| 0.008 | 1.451 | 90.9 | 7.28 | 0.0396 | -2.3 |
| 0.012 | 1.419 | 88.6 | 8.95 | 0.0407 | -3.4 |
| 0.016 | 1.385 | 86.1 | 10.62 | 0.0418 | -4.5 |
| 0.024 | 1.046 | 64.0 | 13.79 | 0.0437 | -6.4 |
| 0.040 | 0 | 0 | - | - | cup dropped (61 mm) |

The force falls only when the jaw has opened by 0.016-0.024 rad, and the cup rotates in the grip while it does: the tilt leaves the v2
calibrated range (3.0-5.5 deg) at relax >= 0.004 rad, and k leaves its band (+-0.3 mm of 37.454 mm) at relax >= 0.002 rad.

### 3.3 Touchdown, undisturbed and with the bounce surrogate (20 seeds x 2 sizes; undisturbed: 100 seeds)

| Setting | Compression before touch (um) | Peak with bounce 0.5x / 1.0x (um, % of limit) | Fingertip lost in | Undisturbed descent |
| --- | --- | --- | --- | --- |
| nominal | 97.6 | 137.4 (115%) / 132.2 (111%) | 20 of 40 | 100 supported, peak above hold 0.039 N, travel 0.70 mm |
| -0.0472 | 97.2 | 127.9 (107%) / 130.4 (109%) | 0 of 40 | not run |
| relax 0.003 | 95.5 | 160.3 / 174.9 | 32 of 40 | not run |
| relax 0.006 | 92.4 | 117.4 / 142.6 | 20 of 40 | not run |
| relax 0.012 | 76.8 | 91.9 (77%) / 114.5 (96%) | 20 of 40 | **0 of 100 supported**, cup slides up 2.9 mm, travel after touch 5.6 mm |
| relax 0.016 | 53.2 | 70.5 (59%) / 98.8 (83%) | 40 of 40 | **0 of 100 supported**, cup slides up 2.6 mm, travel 5.6 mm |
| relax 0.024 | 75.5 | 93.0 (78%) / 112.9 (95%) | 40 of 40 | not run |

Only relax 0.016 reaches <= 85% under both disturbance sizes, and there the cup is no longer held: it slides up in the grip on touchdown
(the undisturbed descent ends unsupported in 100 of 100 trials, with the table force removed from the cup) and its tilt is 10.6 deg.

## 4. Answer to the specification

- **Parameter and value.** There is no value of `gripper_close_target_rad` that gives a pre-touchdown margin: the calibrated window is
  [-0.0476, -0.0472] rad and its compression is 97.1-97.5 um. The proposed new value is therefore **none; the target stays at
  -0.047608632840292 rad**.
- **Carry stability.** Through LIFT and MOVE_ABOVE_PLACE the nominal grip keeps a minimum single-side force of 0.74-0.78 N and a slip of
  1.6 mm; the 1.712 N LIFT peak (1.675 N in the model) is the wedge forming at the micro-lift and does not depend on the target.
  Any target >= -0.0468 loses the micro-lift margin (single-side force 0 in the model) and slips 10-18 mm.
- **Cup tilt (v2 input).** The tilt follows the grip (3.92 deg nominal, 4.09 at -0.0472, 4.77 at relax 0.002, 10.6 at relax 0.016); any
  value that lowers the force moves the tilt and k out of the v2 calibration.

## 5. Interaction with calibration r10b

The force and compression limits (1.8916 N, 119.28 um) and the contact calibration hash stay as they are in every variant. A grasp that is
lighter than the calibrated one is not inside the calibrated domain: r10b's PASS runs peak at 90.5% of the force limit (LIFT) and 88-91% of the compression limit
with bilateral contact, and the VERIFY_PHYSICAL_GRASP check (audit only: cup lifted by >= 1 mm and fingertip contact on both sides) passes
for every setting that carries the cup; it does not constrain the force. A state with the cup lost at the micro-lift or sliding 10-18 mm
fails the lift and the k band, not these limits. A lighter grip would need the tilt/k/guard calibration of policy v2 re-measured and the
r10b PASS statistics re-derived (the carry compression is the baseline of the touchdown excursion).

## 6. The one variant that could still be built (not recommended): a hover relax, policy v3

If a lighter pre-touchdown grip is still wanted, the only mechanism the model offers is a second gripper command before the descent.

- **Policy.** Teacher execution policy `v3` (`schema_version: 3`, binding `teacher_execution_policy_v3`): everything of v2 plus
  `place_grip_relax_rad` (the jaw target is raised by it over 0.5 s at the end of MOVE_ABOVE_PLACE and kept through DESCEND_TO_PLACE and
  until OPEN_GRIPPER) and a place-height section re-measured for the new tilt and k (tilt range, k band, `place_geometry` unchanged). v2
  stays byte-identical. Candidate value from the sweep: 0.016 rad, the only one under 85% in the bounce surrogate.
- **Why it is not recommended.** At 0.016 rad the cup tilts to 10.6 deg (calibrated 3.0-5.5), k grows by 4.5 mm (band +-0.3), the cup
  slides up 2.6 mm on touchdown and the descent ends unsupported in the model, so the release-support check would stop the run. The
  compression at hold is still 86 um, not the 60 um the margin needs, and the result is not monotonic (relax 0.003 is worse than
  nominal). The tilt/k/guard calibration, the guard sweep and the support check would all have to be redone for a grip the model cannot hold.
- **ACT demonstration.** The gripper action in the labels (the recorded gripper command, constant -0.0476 from CLOSE_GRIPPER to
  OPEN_GRIPPER) would gain a 0.5 s ramp of +0.016 rad before DESCEND_TO_PLACE; the recorded world would show a tilted, lower cup in the
  hand. Demonstrations from v2 and v3 must not be mixed in one dataset; the label schema gains no field, the value distribution changes.
- **Validation (if it were built).** The offline sweep above at the final value; then a live round of at least 20 runs with the touchdown
  metrics of the v2 round (peak above hold, compression peak, contact speed, travel after contact); acceptance: the compression peak at
  touchdown <= 85% of the limit (101.4 um) in every run, no run unsupported at the release, tilt and k inside the new calibrated ranges.

## 7. Recommendation and what to test instead

1. Do not build the lighter grip: the carry force is a wedge that the jaw command does not control, and the one variant that lowers it
   gives up the carry.
2. The margin has to come from either the **excursion** or the **wedge geometry**. Candidates, each a separate design and sweep:
   - **Slower final approach** (a speed limit over the last 2-3 mm of DESCEND_TO_PLACE). The model's disturbance is fixed here, so this
     document cannot rank it; it needs the live touchdown-speed vs excursion relation (the 19 v2 bags have the speed at 2.98-3.10 mm/s with
     peak above hold 0.040-0.083 N, too narrow a range).
   - **Grasp geometry** (grasp height or pad contact point on the cup): the wedge force is set by where the cup hangs between the pads; a
     different grasp pose is a change to the pick and to the k/tilt calibration, with the same re-measurement as a lighter grip.
3. Keep collecting the v2 touchdown metrics; the model reproduces the stop only with an externally applied disturbance, so the stop rate
   (3 bifurcations in 20 runs, one a stop) is a live measurement, not an offline one.
