# Teacher: tilt-compensated place height

Date: 2026-10-09 (ledger CP-3480; decision CP-3394; review PASS-WITH-CHANGES, all 12 changes accepted and applied; implemented)

Evidence: `handoffs/.../teacher-force-stop-20261009/` (the investigation), `writer-artifacts/phased/q2/` (`measure.py` and `measure.json` on the 20 retained PASS bags and the failing run, `make_profile.py`, `place_sweep.py` and its two result files). Numbers below are from these.

## 1. Cause (restated: touchdown speed and loading rate, not overtravel depth)

A Teacher run stopped in DESCEND_TO_PLACE with `DYNAMIC_CUP_FORCE_EXCEEDED` (1.94 N against 1.8916 N; run `392e7925`, step 41943); since the r10b limits: 46 PASS, 1 such stop (2.1%, 95% CI about 0.4-11%).

- The failing run's pre-contact state equals the 20 PASS bags to the measurement resolution: cup xyz +-0.1 mm, tilt 4.04 +- 0.03 deg, joints +-0.2 mrad, hold 1.538 N; **k** (below) 0.037449 m against 0.037454 m; TCP z at first contact 0.205162 m against 0.205170 m; touch speed -3.43 against -3.42 mm/s. Nothing before contact separates it from a PASS run.
- The cup carries about 4 deg of tilt, so a point of its round bottom rim touches the table before the arm has finished the descent: first contact comes **0.62 s (0.608-0.644 s) before DESCEND_TO_PLACE ends**, at a TCP speed of **3.42 mm/s** (sd 0.09). **The arm travels only 0.943 mm (TCP) after first contact, the cup 0.650 mm** (the earlier "about 2.2 mm" was 3.5 mm/s x 0.62 s, but the arm decelerates to a stop). In the failing run table-contact flicker began 0.028 s after first contact, when the arm had moved about 0.1 mm; the contact then bifurcated into chatter (moving-jaw contacts 8-4-0-14, force alternating left/right every 0.1-0.15 s, penetration 154-214 um, per-step peak 2.495 N, 88 single-step spikes).
- So the load is set by the **loading rate at first touch**, not by the depth of the overtravel. Raising the target still helps, because the arm then reaches contact in the slow tail of its deceleration. Measured TCP speed against the distance still to go (20 bags, mean): 1.57 mm/s at 0.2 mm, 2.47 mm/s at 0.5 mm, 3.51 mm/s at 1.0 mm. Old target: contact at 0.943 mm to go, **3.42 mm/s**. New guard 0.7 mm: contact at 0.7 mm to go, about **2.9 mm/s** (replay: 2.91; 0.4 mm: 2.2 mm/s; 0.2 mm: 1.55 mm/s).
- The peak force in the DESCEND_TO_PLACE window of a PASS run (1.658 N, 87.6%) occurs **1.9 s before** touchdown, during the descent itself (every bag, 13.7-13.8 s into the state); touchdown is a 0.043 N spike (1.581 N at first contact, 10 ms) followed by unloading to 0.88 N (the table takes 0.26 N). This change cannot move the 1.658 N peak.
- Check in force (`ros/teacher_safety.py`): summed normal force of the left and right fingertip contacts and the other cup contacts above 1.8916 N, or compression above 119.28 um, every state, on the 100 Hz evidence path and the 500 Hz chunk path (`PhysicsHazardWatch`, about 0.1 s later). PASS margins unchanged: carry peak 1.712 N (LIFT, 90.5%), compression 105-109 um (88-91%).

**Rejected by default: a guarded descent** (stop at the first evidence contact). It adds a reactive cancel and its own stop transient on a 100 Hz contact flag (10 ms granularity at 3.4 mm/s is 34 um of travel plus the cancel latency, which is the same loading event), and gains nothing the height compensation does not give while `k` is as stable as measured. Adopt it only if the measured `k` spread made height compensation unreliable; it does not: sd 0.018 mm (section 3).

## 2. Design

Aim the descent so that it ends a small guard `g` above the pose at which the cup first touches the table, instead of continuing through it. No limit is relaxed and the force metric is not filtered.

    z_tcp_target = z_touch(theta) + k + e_track - g        (commanded TCP z, metres)
    z_touch(theta) = 0.12 + c cos(theta) + r sin(theta),    c = 0.045 m, r = 0.040 m

- `z_touch` is exact for this cup. Its bottom is a round cylinder (`bottom_collision`, radius r = 0.040 m, half thickness 0.001 m, centred 0.044 m below the body origin, so the bottom face is c = 0.045 m below it); the lowest point of a tilted body is a point of the bottom rim in the tilt direction, whatever the azimuth. At 4.04 deg: 0.167706 m predicted, **0.16770 m measured** (sd 0.009 mm, 20 bags). The wall corners (radius 0.0413 m at z -0.043 m) become the lowest points only above about **56.6 deg** (`lowest_point_height` in `core/place_height.py` is the exact general form; a test compares it with the formula up to 55 deg and checks the crossover in 56.0-57.5 deg).
- `theta`: the cup's tilt from the Teacher's own world observer (`_upright_tilt_rad`), the median of a 100 ms (simulation time) window of fresh evidence samples whose tilt range is under 0.05 deg; no such window within 1 s refuses (`TEACHER_PLACE_TILT_UNSTABLE`).
- `k`: the TCP height above the cup origin, **by forward kinematics of the actual joints (sag included)** minus the evidence cup z, at the end of the same window. The target is a *commanded* pose, so `e_track` converts: the commanded minus the actual TCP z at the end of a descent, measured **0.158 mm (sd 0.014 mm, range 0.136-0.183 mm)** on the 20 bags, frozen in the policy. The arm therefore stops, in actual terms, `g` above the touching pose.
- `g` (guard): strictly positive and at most 1.0 mm in the loader (`GUARD_MIN_M` 0.1 mm, `GUARD_MAX_M` 1.0 mm): the cup margin is 0, so with `g <= 0` the cup has no table contact, `actual_table_support` fails and the run ends in `DYNAMIC_RELEASE_SUPPORT_NOT_PROVED`. **The frozen value is 0.7 mm** (section 7).
- The old target (-13.25 mm) is equivalent to `g` = 0.944 mm at the live tilt (0.785 mm commanded below the touching TCP height; 0.943 mm actual). It was fitted offline at 3.5 deg with a 0.5 mm margin; the live 4.04 deg touches 0.38 mm earlier.

### 2.1 Where it lives and when it runs

- `core/place_height.py` (pure, no ROS or MuJoCo import): geometry read from the frozen scene file (`cup_geometry_from_scene`, with its sha256), `touch_center_z`, `lowest_point_height`, `PlaceHeightPolicy`, the bounds, `plan_place_height` (the audit document) and `validate_document`.
- `ros/dynamic_mujoco_execution.py`: `_place_target` (called from `_perform_state` under `_safety_state = DESCEND_TO_PLACE` and **before `_phase_open`**, so nothing is published and no goal is sent if it refuses, and the force limits are enforced while it measures: `_measure_place_height` calls `_enforce_safety` on every sample) dispatches on the policy: v1 the constant offset, v2 `_compensated_place_target`. `core/dynamic_pick.py` `resolve_motion_targets` is unchanged (the policy place TCP stays the hover for MOVE_ABOVE_PLACE and RETREAT; the compensated target replaces only the DESCEND_TO_PLACE one, as the v1 offset did). The corridor (0.008 m), the carry scaling and the MoveIt tolerance are unchanged.
- The policy the freeze names is loaded by `_select_execution_policy` (`ros/dynamic_runtime.py` calls it with the binding of the freeze).

### 2.2 Bounds, fail closed; the end state of a refusal

Checked before any DESCEND_TO_PLACE motion (`check_measurement`, `plan_place_height`):

| Code | Condition |
| --- | --- |
| `TEACHER_PLACE_TILT_UNSTABLE` | no 100 ms window with tilt range < 0.05 deg within 1 s |
| `TEACHER_PLACE_TILT_OUT_OF_RANGE` | the tilt is not finite or outside the frozen range (initial 3.0-5.5 deg) |
| `TEACHER_PLACE_HEIGHT_OUT_OF_BOUNDS` | `k` outside its band; the scene hash is not the one the geometry was fitted for; the target differs from the v1 constant-offset target of the same pose by more than 2.0 mm; the target is outside the workspace |

The deviation bound is the geometric need: the z_touch spread over the tilt range plus the k band plus the guard difference to the v1 constant gives -0.73 .. +1.45 mm at the corners of the calibrated range, so 2.0 mm (it was 6 mm in the first draft).

**End state.** All three are in `TERMINAL_STOP_CODES`: `resolve_transition` takes the failure straight to ERROR with no RECOVER_* chain, so no recovery goal and no gripper command is ever sent: **the cup stays held, it is not released**, the Teacher execution status is `STOPPED_SAFETY` and the outcome code is the refusal code (`failure` in the manifest, `phase_finish FAILED <code>`). The manifest carries `place_height: {"mode", "refused": <code>, "detail"}`. Tests: `test_a_refusal_ends_the_run_with_the_cup_held_and_a_stopped_safety_outcome` (no `_motion`, `_command_gripper`, `_phase_open`, `_open_supported_gripper`, `_attach` or `_detach_or_sync` is called; the code is terminal; the transition is ERROR; the status is STOPPED_SAFETY), one case per code.

## 3. Measurements from the 20 retained PASS bags (step 2 and 5 of the review)

All by forward kinematics of the actual joints (`qpos[:7]` of the physics step record, the `so101_tcp` site of the ACT scene).

| Quantity | mean | sd | range |
| --- | --- | --- | --- |
| `k` at the hover (start of DESCEND_TO_PLACE) | 0.037454 m | 0.018 mm | 0.037424-0.037487 |
| `k` at first contact | 0.037469 m | 0.018 mm | 0.037439-0.037498 |
| `k` at the end of the descent | 0.037176 m | 0.014 mm | |
| TCP z at first contact / at the end (actual) | 0.205170 / 0.204227 m | 0.021 / 0.014 mm | |
| commanded (0.204384) minus actual TCP z at the end | 0.158 mm | 0.014 mm | 0.136-0.183 |
| tilt at the start of DESCEND_TO_PLACE minus tilt at first contact | 0.028 deg | 0.008 deg | 0.014-0.042 (**<= 0.1 deg**) |
| largest tilt excursion from the start value, start to contact | 0.159 deg | 0.007 deg | 0.144-0.172 (a transient that returns) |
| first contact before the end of the descent | 0.625 s | 0.010 s | 0.608-0.644 |

- **k band** = measured +- max(3 sd, 0.3 mm) = **0.037454 +- 0.3 mm**; the 0.0389 figure of the first draft is dropped (it was inferred from a 2.2 mm overtravel that is not real). The measured spread (0.018 mm) is 17x smaller than the band, so the band is a refusal bound, not an expected variation. The hover value is what the Teacher measures, so this is the same quantity as the target uses.
- **Tilt stability** (review 5): the 100 ms / 0.05 deg window is satisfied **immediately** after MOVE_ABOVE_PLACE finishes in 20 of 20 bags (0-2 ms; the tilt is a rigid-body quantity of a held cup), and the gap between the end of MOVE_ABOVE_PLACE and the start of DESCEND_TO_PLACE is 0.34-1.83 s (mean 0.60 s), so the measurement has room. The tilt at the start of the descent equals the tilt at first contact to 0.04 deg at most, which moves `z_touch` by at most 0.03 mm (dz/dtheta = 0.64 mm per degree); the 0.16 deg mid-descent excursion would move it by 0.1 mm and returns by the time of contact.

## 4. Force acceptance (rewritten on the actual summed metric)

The summed metric (left + right fingertip + other cup contacts, `ros/teacher_safety.py`) in the 20 PASS bags: pre-contact hold **1.5386 N** (sd 0.0003), spike at first contact to 1.581 N (+0.043 N, 10 ms), then unloading to a floor of **0.884 N at the end of the descent (sd 0.005; table normal force 0.259 N)**; the window peak 1.658 N is 1.9 s before contact. The criteria for this change are therefore on the touchdown window, not on the window peak:

1. No force or compression stop and no chatter in the touchdown window (first contact minus 0.05 s to the end of the descent): the summed force never exceeds the pre-contact hold by more than **0.05 N** (PASS today: 0.043 N; the failure: 0.956 N).
2. The summed force at the end of the descent is within 0.03 N of the 0.884 N floor (hold, unloaded by the table's 0.26 N) and the table normal force is above 0.
3. The first-contact TCP speed is lower than today's 3.42 mm/s (about 2.9 mm/s expected), and the overtravel window (first contact to the end of the descent) is under 0.5 s with the TCP travel after contact about 0.7 mm (today 0.62 s and 0.943 mm).
4. Compression stays at or below today's 105-109 um (88-91%); the peak in the DESCEND_TO_PLACE window does **not** change (1.658 N), and acceptance does not expect it to.

## 5. Effect on the other checks (re-qualified)

| Check | Effect | Re-qualification |
| --- | --- | --- |
| Force and compression limits (1.8916 N, 119.28 um; r10b) | unchanged, same states, same paths, not filtered; the r10b limits, the contact calibration hash and `dynamic_cup_pick/v1` are unchanged | section 4 |
| Release support before OPEN_GRIPPER (contact, force above 0, distance <= 0.002 m, both fingertips) | the descent now stops `g` above touching instead of 0.94 mm through it; `g` > 0 is the loader's guarantee that contact exists | the sweep: supported in 55 of 55 trials for every guard from 0.3 mm, 16 of 70 at 0.1 mm |
| Endpoint (`teacher_endpoint_v2`, `final_z_m` 0.010, final xy 0.020) | the final pose after release is where the cup settles; the target moves by +0.23 mm | unchanged limits; evaluated on the live runs |
| `VALIDATE_FINAL_PLACEMENT` (z 0.155-0.175, tilt <= 0.15 rad, table contact, no fingertip contact) | unchanged limits | the same |
| Corridor 0.008 m, MoveIt 0.002 m | the target moves by 0.23 mm at the nominal pose (-0.73 .. +1.45 mm across the calibrated range) | planned on the live runs |

## 6. Versioning and schema

- **`config/act/teacher_execution_policy_v2.yaml`** (new); **v1 is byte-identical** (sha256 `af0a5699...`, asserted by a test). v2 has schema_version 2, every v1 field except `place_descend_offset_m`, and: `place_height_mode: tilt_compensated`, `place_touchdown_guard_m`, `place_tracking_offset_m`, `place_tilt_min_rad`, `place_tilt_max_rad`, `place_grasp_offset_m`, `place_grasp_offset_half_band_m`, `place_target_max_deviation_m`, `place_reference_offset_m` (the v1 constant, used only as the reference of the deviation bound), `place_geometry_scene_sha256`.
- The loader (`act/teacher_endpoint.py`) refuses an unknown schema, an unknown mode, a missing or an extra field, a non-finite or out-of-range value (guard outside [0.1, 1.0] mm, tracking offset outside [0, 1] mm, tilt range not 0 < min < max <= 0.2 rad, k band half width under 0.3 mm or over 2 mm, deviation bound over 5 mm, a scene hash that is not a sha256) with `TEACHER_EXECUTION_POLICY_INVALID`.
- Freeze: `teacher_execution_policy_v2` is a second binding name, exactly one of v1/v2 per freeze (`frozen_execution_policy_name`); a schema 2 document cannot be bound as v1 nor schema 1 as v2; `verify_policy_bindings` re-reads and re-compares it with the snapshot copy like every other policy.
- **The scene hash is bound twice**: the policy pins `place_geometry_scene_sha256` (a test fails when `scene.xml` changes without a new policy), and the Teacher recomputes the geometry from the snapshot's scene file and refuses when its hash differs.
- **Manifest / QC fields**: the Teacher manifest gets `place_height` = `{mode, tilt_rad, grasp_offset_m, touch_center_z_m, guard_m, tracking_offset_m, target_tcp_z_m, constant_offset_target_tcp_z_m, scene_sha256, geometry{table_top_z_m, half_height_m, rim_radius_m}}` or the refusal form; `parallel_batch/dynamic_manifest.validate` recomputes the target from the recorded measurement and checks the bounds (`DYNAMIC_MANIFEST_PLACE_HEIGHT`); `place_height.validate_document(document, policy)` also binds it to the frozen policy. The three refusal codes are terminal stop codes.
- Implementation scope: a new freeze with v2 and a new candidate receipt are needed before a live run; the QC rule version is unchanged (the new fields are additions the existing checks do not read).

## 7. Offline sweep (review 9)

`place_sweep.py` replays the touchdown on the aligned ACT model with the real actuators and the held cup: the carry from the CP-3395 run, then the descent with the **measured time law of the live descent** (the normalised TCP progress of a retained bag, every 2 ms), command timing jitter (a shift of 0-10 ms) and command noise (2 urad), the old guard against a sweep of the new one, **at most 500 trials** (490 and 495 were run). The replay reproduces the live touchdown closely: hold 1.536 N (live 1.5386), touch speed 3.40 mm/s (3.42), travel after contact 0.95 mm (0.943), tracking offset 0.147 mm (0.158), peak above the hold 0.040 N (0.043); its tilt is 3.92 deg (live 4.04) and its `k` 0.037324 m (0.037454).

| guard | trials | chatter (peak > hold + 0.2 N) | force/compression stop | supported at the end | peak above hold, mean / max | compression max | touch speed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| old 0.944 mm | 70 + 55 | 0 | 0 | all | 0.040 / 0.042 N | 100.4 um | 3.40 mm/s |
| 0.1 mm | 70 | **33** | **37** | 16 | 0.33 / 1.12 N | 243 um | 1.08 |
| 0.2 mm | 70 | 0 | 0 | all | 0.035 / 0.107 N | 116.2 um | 1.55 |
| 0.3 mm | 70 + 55 | 0 | 0 | all | 0.039 / 0.186 N | **119.0 um (99.8% of the limit)** | 1.90 |
| 0.35 / 0.4 mm | 55 / 70 + 55 | 0 | 0 | all | 0.035 / 0.037 N | 100.2 / 100.0 um | 2.06 / 2.20 |
| 0.5 mm | 55 | 0 | 0 | all | 0.052 / 0.082 N | 112.9 um | 2.42 |
| 0.6 mm | 70 + 55 | 0 | 0 | all | 0.038 / 0.040 N | 107.6 um | 2.63 |
| **0.7 mm** | 55 | 0 | 0 | all | 0.039 / 0.041 N | 101.5 um | 2.91 |
| 0.8 / 0.9 mm | 55 / 55 | 0 | 0 | all | 0.042 / 0.041 N | 109.9 / 100.5 um | 3.11 / 3.37 |

**Stopping rule outcome: the old failure does not reproduce.** The old guard gave 0 chatter in 125 trials (the live rate is about 2%; 125 trials with none bound it at about 2.4% at 95%, so the sweep cannot distinguish the old target from a 2% failure), so the sweep is downgraded to **geometry / support / g-margin qualification**; it does not show that the mechanism is gone. What it does show:

- a guard of 0.1 mm is **unsafe** (the cup is barely touched and the contact chatters in half of the trials, 37 of 70 force or compression stops), so a small guard is not "safer"; 0.2-0.3 mm run to 97-99.8% of the compression limit in the worst trial;
- guards of 0.35 mm and above are supported in every trial, with excursions under 0.19 N, and 0.4, 0.7, 0.9 mm are the cleanest; **the frozen 0.7 mm keeps the effective guard within 0.4-1.0 mm over the whole +-0.3 mm k band** (all clean) and cuts the first-contact speed by 15%.

The claim that the mechanism is gone therefore rests on the live surrogate metrics of section 4 and its limit is explicit: twenty clean runs bound the failure rate at about 14% (95%, rule of three), and the improvement itself is modest (3.42 to 2.9 mm/s, 0.94 to 0.7 mm of travel after contact). A smaller guard would cut the speed more (0.4 mm: 2.2 mm/s) but leaves the band no margin before the unsafe region below 0.3 mm; this is a policy value, changed by a new policy file.

## 8. ACT demonstration

Two changes to what the demonstration contains: (a) the **last 0.6 s of the descent** ends at a target about 0.2 mm higher (nominal pose; the arm travels 0.7 mm after contact instead of 0.94 mm) and slows into contact at about 2.9 mm/s instead of 3.4 mm/s; (b) a **stability dwell before the descent**: the Teacher now waits for a 100 ms window of simulation with a tilt range under 0.05 deg (immediately in the retained bags, up to 1 s at most) between the end of MOVE_ABOVE_PLACE and the start of the DESCEND_TO_PLACE motion, during which the arm is still, so the demonstration gains a still segment of at least 100 ms of simulation time before the descent. Earlier phases and their labels are unchanged. No formal collection exists yet, so no old demonstrations mix with new ones; the manifest fields (`place_height`, and the policy binding `teacher_execution_policy_v2` in the inputs) stamp each episode so a dataset can refuse to mix modes.

## 9. Validation plan and gates

**Offline (done above):** the geometry against the 20 bags; the k, tilt and force numbers; the sweep (qualification of `g` only, limit stated). **Live (after the next freeze and candidate receipt):** N = 20 Teacher runs (collection off, same pose) with, per run, the section 4 metrics: touchdown-window peak above the hold, the end-of-descent force and table force, the first-contact speed and height against `z_touch`, the overtravel window and the compression. A run outside section 4, or a refusal, is reported.

**Gate before formal collection (does not block this implementation, review 7):** a carry-tilt simulation across the randomized start domain of the findings (x in [-0.12, 0.12], y in [-0.32, -0.20], excluding the 0.065 m disc around the ring), recording the tilt, `k` and the target at every start, to set the tilt range and the k band from it or to record the expected refusal rate. The initial 3.0-5.5 deg range and +-0.3 mm band come from one operating point (4.04 deg); a start that carries the cup at another tilt is refused (`TEACHER_PLACE_TILT_OUT_OF_RANGE`), by design, until the range is widened by this sweep.

## 10. Implementation record

Files: `core/place_height.py` (new), `act/teacher_endpoint.py` (loader), `config/act/teacher_execution_policy_v2.yaml` (new), `act/first_episode_inputs.py`, `act/frozen_runtime_inputs.py`, `cli/act_first_episode.py` (binding), `ros/dynamic_runtime.py`, `ros/dynamic_mujoco_execution.py`, `core/workflow.py` (terminal codes), `parallel_batch/dynamic_manifest.py` (field check). Tests: `test_place_height.py` (39), `test_place_height_teacher.py` (14), `test_act_policy_freeze.py` (+3, 2 adapted), `test_act_child_recorder_binding.py` (helper takes the policy file). RED: against the commit before this change the new modules do not exist (collection errors).
