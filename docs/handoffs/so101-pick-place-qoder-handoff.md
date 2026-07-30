# SO-101 native fingertip-pad pick/place — Qoder handoff

**Handoff time:** 2026-07-29 (Asia/Shanghai)
**Workspace:** `/data/work/ws_moveit`
**Branch / HEAD:** `codex/direct-tpu-tongues` / `aec430a2ec0bba64d2c1c20137b26bf9f5103761`

This document is the execution handoff for the native 5 mm fingertip-pad
pick/place work. It records evidence, not a claim of completion. In
particular, no subsequent engineer should infer that the user has read,
understood, or edited a TODO merely because this document exists.

## Objective and final completion condition

Demonstrate one complete simulated light-plastic-cup pick/place with the
Blender-derived, native 5 mm TPU cover-only pads. The final result requires
all six evidence layers below, each freshly collected from one isolated
runtime, and every ladder boundary must pass before the next one is run.

The target is **not** “a command returned zero” or “a TODO was changed.” It is
a fail-closed, visually inspected, physically valid `DONE` run with correct
MoveIt/Gazebo ownership and measured controller feedback.

## Non-negotiable workspace and safety rules

- Preserve the existing dirty worktree. It contains substantial user-owned
  tracked and untracked changes. Do not overwrite, stage, revert, or fold
  unrelated hunks into an edit.
- Never run `git reset`, `git checkout`, `git stash`, `git clean`, `commit`,
  or `push`. Do not use `gh`; the configured remote is Gitee.
- Use `apply_patch` for source/text edits. Do not run
  `ament_uncrustify --reformat`.
- Never reintroduce the retired 27 mm DirectTongue/TPUAdapter/stem design or
  its positive tests. Historical documents may remain only as history.
- Do not weaken stationary, contact, endpoint, drift, q6, or penetration
  gates to get through a ladder. Stop on the first true failure and retain the
  original action failure context.
- Do not delete legacy body/VHACD collision bodies merely to hide cup contact.
  The native pad must be the intended cup-wall contact; all necessary robot
  body collision remains active.
- Runtime work is simulation-only. Before any GUI program, source
  `~/gui-env.zsh`, Jazzy, and the workspace overlay in the new tmux pane.
  Use the persistent CUA session and the invariant **snapshot → action → fresh
  snapshot** for every GUI interaction.

## Live-state protection and process ownership

### OBSERVED

The following tmux windows currently existed before this handoff and are
protected old work. Do not restart, signal, reuse, or attach an experiment to
them:

| tmux server/window | PID shown by tmux | status |
|---|---:|---|
| `so101-moveit:0:zsh` | 852043 | protected old shell |
| `so101-moveit:1:gazebo` | 2835346 | protected old GUI stack |
| `so101-moveit:2:moveit` | 2835351 | protected old MoveIt/RViz stack |
| `so101-moveit:3:capture` | 1934786 | protected old capture work |
| `so101-moveit:4:v11-contact` | 2084373 | protected old diagnostic work |

Protected old Gazebo-server PIDs (all historically parented by PID 3382) are:
`131650`, `132125`, `147388`, `147856`, `149852`, and `152395`.

The following historical isolation identities are also protected: domain 96 /
partition `so101_gui_vhacd_727`, and domains `119`, `124`, `154`, `162`,
`168`, and `194`. They are not a pool for reuse.

### INFERRED

Any process which is not proven by its recorded tmux window, process tree, and
`/proc/<pid>/environ` `ROS_DOMAIN_ID`/`GZ_PARTITION` to belong to the current
checkpoint must be treated as another owner’s process.

### HYPOTHESIS

None. Process identity is a hard boundary, not an optimization variable.

## Geometry authority and immutable safety contract

### OBSERVED

- Authority is the Blender-derived native fingertip geometry: **5 mm TPU,
  cover-only, no stem, no fingertip extension**.
- The fingerprint-bound generated calibration authority is
  `b101b7db33a13c82797eb80c2356f1c6b509e04bdae7999efd4b6a8ce0d1094f`.
  Generated source header:
  `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/fingertip_pad_gap_calibration_data.hpp`.
- Native calibration is bound to profile points, generated visual/collision
  mesh SHA-256 values, and parsed URDF/Xacro transforms. The strong tests
  require exact generated-header equality. The established dense original
  finger-width calibration/header contract is additive and must remain exact.
- Current generated mesh-derived policy authority is the calibration/header,
  not copied literals in a future patch. Its installed contact knee is
  `q6=-0.049116990289937`, gap `0.001820770318 m`; consult the generator/header
  rather than duplicating those values.
- Cup wall thickness remains 2 mm. `kCupWallInterferenceM` is a nominal
  `wall_thickness - gap` quantity, distinct from the unchanged physical
  `grasp_contact.max_penetration_m = 0.8 mm` ceiling. Cup drift ceiling is
  3 mm.

### INFERRED

Any edit to pad profile, generated mesh, collision asset, URDF transform,
or fingerprint without a newly demonstrated provenance mismatch invalidates
the calibrated geometry contract. A new geometry proposal therefore needs
source-mesh/Blender evidence, RED tests, regenerated exact artifacts, build
and installed provenance before runtime.

### HYPOTHESIS

No current evidence establishes a Blender provenance mismatch. Do **not** edit
pad geometry as a speculative controller or contact fix.

## Current reliable runtime boundary

| Boundary | status | measured evidence / restriction |
|---|---|---|
| `PREPARE_OPEN_GRIPPER` | GREEN | q6 measured around `0.465041`; arm/TCP/cup unchanged, detached/world state preserved. |
| `MOVE_ABOVE_OBJECT` plan-only | GREEN | CP23 fixed the transfer-versus-axial-validator defect; no trajectory execution. |
| `MOVE_ABOVE_OBJECT` execute | GREEN | CP24+ child/controller/MoveIt evidence green, with independently inspected Gazebo/RViz images. |
| `DESCEND` plan-time validation | GREEN (CP31B) | 4 mm retreat waypoint passes 3 mm retreat threshold and 5 mm lateral-deviation gate; 17/17 gtest pass. **Runtime execute has not yet run** at this handoff. |
| `DESCEND` runtime execute | **PENDING** | CP29 baseline ERROR; CP30R 8 mm attempt failed `TCP_PATH_LATERAL_DEVIATION=6.17 mm`; CP31B 4 mm attempt authorized but not yet executed. |
| `CLOSE_GRIPPER` | NOT AUTHORIZED | no valid post-DESCEND baseline; do not run. |
| attach/lift/place/DONE | NOT AUTHORIZED | all depend on a green DESCEND then green CLOSE. |

The only previously authorized CLOSE diagnostic was CP13. It showed action
terminal success can coexist with wrong/still-moving measured q6; the runner
now preserves original failure context when post-cancel quiescence also fails.
It is not acceptance evidence and does not authorize another CLOSE.

## Chronology and key evidence, CP1–CP28

The master narrative for CP1–CP19 is
`/tmp/so101-debug-current-MQopWL/subagent-report.md`. It is authoritative for
the exact commands, RED/GREEN outputs, and original screen captures listed
later in this document.

| checkpoint(s) | OBSERVED conclusion | evidence path |
|---|---|---|
| CP1 | Audited source meshes and found active retired 27 mm direct-tongue implementation; fixed and moving source meshes reproduced the relevant Blender boundaries. | master report, CP1 |
| CP2 | TDD replaced active retired geometry with cover-only native pads and deterministic collision pieces; focused geometry/build green. | master report, CP2; `test_fingertip_pad_geometry.py` |
| CP3 | Removed empirical gap slope; created mesh/profile/URDF-transform fingerprint-bound native gap calculation while preserving strong original-width exact header tests. | master report, CP3; `test_fingertip_pad_gap_calibration.py`, `test_gripper_preopen_calc.py` |
| CP4 | Propagated calibration through config/reset/recovery/SRDF, canonical native collision naming and installed provenance. | master report, CP4 |
| CP5 | First live boundary failed `MOVEIT_SCENE_EVIDENCE_INCOMPLETE`, before any contact/CLOSE claim. | master report, CP5; `runtime-move-above.log` |
| CP6 | Added generated q6→minimum-pad-gap table; runtime reports actual observed gap/interference, not a fabricated nominal constant; profile fingerprint mismatch fails closed. | master report, CP6 |
| CP7 | Recovered accidental script corruption without restoring retired models; retained only native-pad calculator and original-width contract. | master report, CP7 |
| CP8 | Native-pad-only recovery/static audit and non-GUI checks green. | master report, CP8 |
| CP9 | Script hygiene, isolated world regression, and provenance checks; later corrected scope wording. | master report, CP9 |
| CP10 | Full-worktree whitespace correction documented; no unrelated dirty work changed. | master report, CP10 |
| CP11 | Scene evidence repaired; staged live run reached a truthful failure, not a contact acceptance. | master report, CP11 |
| CP12 | TDD retained original executor failure when cancel/quiescence also fails; DESCEND-only A/B baseline added. | master report, CP12 |
| CP13 | Single CLOSE diagnostic recorded actual q6/controller/cup evidence; no repeat CLOSE authorized. | master report, CP13 raw files/screenshots below |
| CP14 | Audited action-success versus measured endpoint and offline geometry; terminal action success alone is not physical success. | master report, CP14 |
| CP15 | Signed cup-wall/active-collision audit showed removing legacy contact meshes alone would not seat wall between pads; do not hide geometry by suppressing collisions. | master report, CP15 |
| CP16 | FK/IK feasibility work rejected a non-robust static solution; fixed-pad preopen must not positively penetrate. | master report, CP16 |
| CP17 | Wider-gap exploration established endpoint-acceptance uncertainty; do not accept exact tangent as robust. Kept scipy test dependency. | master report, CP17 |
| CP18 | Added fail-closed contact-critical real-feedback endpoint checks for `DESCEND` and recovery; action success cannot forward to CLOSE/attach after contract failure. | master report, CP18 and closure addendum |
| CP19 | Installed mesh-derived seated-pad knee policy and complete 28-mesh / 32-corner / q6 endpoint / swept-path offline audit; corrected stale SRDF test. Also recorded accidental runtime CTest as invalid and established safe offline suite. | master report, CP19 |
| CP20 | Isolated baseline was a false negative: ROS probe was wrong transport and bare MoveIt scene was queried before explicit upsert. | `/tmp/so101-debug-cp20.e7WR39/CP20-report.md` |
| CP21 | Proved attachment state is Gazebo transport; `so101_moveit_scene upsert` owns no-motion scene insertion. First true failure was planning/q6 behavior, not CP20 probe. | `/tmp/so101-debug-cp21.B0miSW/CP21-report.md` |
| CP22 | `PREPARE` green; plan-only `MOVE_ABOVE` failed because axial ladder validation was incorrectly applied to a non-axial home-to-above transfer. | `/tmp/so101-debug-cp22.tAuqlg/CP22-report.md` |
| CP23 | TDD separated waypointed-transfer planning from axial path validation; plan-only MOVE_ABOVE green. Execute then failed after validated artifact at controller path tolerance. | `/tmp/so101-debug-cp23.kWLiND/CP23-report.md` |
| CP24 | One-variable arm trajectory tolerance experiment made MOVE_ABOVE green but DESCEND still failed `PATH_TOLERANCE_VIOLATED`; fixed-margin theory falsified. | `/tmp/so101-debug-cp24.cMXy9W/CP24-report.md` |
| CP25 | At 100 Hz controller manager, strict DESCEND improved from joint-3 error `0.000766` to `0.000596` rad, still above strict `0.000500`. Rate alone not a fix. | `/tmp/so101-debug-cp25.bX2CR7/CP25-report.md` |
| CP26 | At 1000 Hz matching 1 ms physics step, strict DESCEND still failed (joint 1 `0.000666` vs `0.000500`); RTF ~0.999. Rate-only hypothesis falsified. | `/tmp/so101-debug-cp26.cMBhFj/CP26-report.md` |
| CP27 | Removed erroneous preopen-DESCEND `plastic_cup:gripper/jaw` MoveIt collision whitelist (TDD green). Runtime still failed: path tolerance, native fixed-pad/wall sampled depth `0.696508 mm`, cup drift ~10.445 mm. This is a real policy-hole fix, not a complete physical fix. | `/tmp/so101-debug-cp27.fmAl4v/CP27-report.md` |
| CP28 | Instrumentation capture did not overlap DESCEND; classified **`INVALID_CAPTURE_ORCHESTRATION`**. Action failure fact is retained, but it cannot establish temporal root cause. | `/tmp/so101-debug-cp28.6FEgTJ/CP28-report.md` |
| CP29 | Diagnostic-only run with identity `ROS_DOMAIN_ID=229` / `GZ_PARTITION=so101_cp29_7hZSj6`. 180-second READY handshake green, valid time span. DESCEND reached terminal `status=ERROR` with `failure=TCP_PATH_LATERAL_DEVIATION`; raw contact/temporal evidence captured for analysis. | `/tmp/so101-debug-cp29.7hZSj6/CP29-report.md` |
| CP30 (first run) | **INVALID_SINGLE_VARIABLE**: validation policy was edited alongside motion policy (added `DESCEND.allowed_touch_pairs`). Causal claim that runtime persistent contact triggered `TOUCH_WHITELIST_CONTEXT_MISMATCH` is retracted — the mismatch fires at plan time per `so101_motion_validation.cpp:142-144`. | `/tmp/so101-debug-cp30.8bp488/CP30-report.md` + retraction in CP30R report |
| CP30R | Restored CP29 validation policy (SHA-256 `6dbbe602…ab248c6`). Single variable = 8 mm -Y retreat waypoint inserted at DESCEND[0] (and mirrored in RECOVER_DESCEND_TO_PICK). 17/17 gtest GREEN. Ladder DESCEND failed `TCP_PATH_LATERAL_DEVIATION=6.17 mm > 5 mm gate` at sample_index=6. Genuine plan-time finding: 8 mm amplitude exceeds the CP29 5 mm lateral-deviation gate. | `/tmp/so101-debug-cp30.8bp488/CP30R-report.md` |
| CP31B | Single variable: reduce DESCEND retreat amplitude from 8 mm to 4 mm. Production `/compute_ik` solved joints `[-0.000264207708, 0.369621146811, 0.028193436672, 1.172988068969, -0.000271648009]`; real MoveIt FK Y=`-0.268029587` (≈3.999 mm retreat); max lateral deviation ≈4 mm (under 5 mm gate). 17/17 gtest GREEN. Motion-policy source/install SHA-256 `c1c123b7c7e3fcf6d2188ab1133a9cdbfc40eeec227a50f59a7e474a5d457279`; validation policy untouched at CP29 SHA-256 `6dbbe602…ab248c6`. Runtime ladder DESCEND not yet executed at this handoff. | `/tmp/so101-debug-cp30.8bp488/cp31b_ik_response.txt`, this doc, source/install `light_cup_wall_pick.yaml` |

### CP24–CP26: explicitly falsified proposals

Do not retry any of these without new independent evidence:

1. **Increase trajectory tolerance:** CP24’s `0.000750` path-tolerance A/B
   helped MOVE_ABOVE but DESCEND again exceeded it (`0.000766` vs `0.000750`).
   Later controller direction restored strict `0.000500`; no further tolerance
   increase is permitted.
2. **Controller manager rate alone:** CP25 (100 Hz) improved tracking but was
   still over strict tolerance; CP26 (1000 Hz at the 1 kHz simulation step)
   still failed, with a different failing joint. Do not tune rate, gain, wait,
   or tolerance as the next variable.

### CP27 collision-whitelist repair and limitation

`so101_motion_planner.cpp` had forced `plastic_cup:gripper` and
`plastic_cup:jaw` touch exceptions during preopen DESCEND; validation policy
also allowed them. CP27 removed those exceptions and set DESCEND
`allowed_touch_pairs: []`, with focused planner RED→GREEN. It preserved all
legacy collision meshes, cup spawn, native mesh/profile/fingerprint, q6 policy,
and safety thresholds.

At the final static preopen pose, signed clearance was fixed `+0.269448485 mm`
and moving `+35.183890 mm` to the near wall, yet the aborted runtime trajectory
later sampled fixed native pad `_005` against `wall_near`. This establishes an
unresolved **trajectory-time** issue, not proof that static mesh provenance is
wrong. CP28 was supposed to distinguish trajectory/contact ordering but its
capture is invalid.

## CP29: created identity, not started

### OBSERVED

Only this file exists for CP29:
`/tmp/so101-debug-cp29.7hZSj6/identity.env`.

| field | value |
|---|---|
| checkpoint | `CP29` |
| ROS domain | `229` |
| Gazebo partition | `so101_cp29_7hZSj6` |
| simulation session | `cp29-7hZSj6` |
| evidence directory | `/tmp/so101-debug-cp29.7hZSj6` |
| diagnostic script | `/tmp/so101-debug-cp28-pending/capture_descend_diagnostics.py` |

No CP29 tmux window, ROS node, Gazebo server, GUI, CUA action, or mechanical
action has been started at this handoff point.

### INFERRED

CP29 can be a clean single-variable diagnostic retry only if it uses exactly
the identity above and proves recorder readiness before **any** state-machine
action.

### HYPOTHESIS

The next valid capture can identify whether cup motion precedes or follows
native pad contact, and which actual trajectory sample first violates its
constraint. It must not choose a product fix until that timestamped evidence
exists.

## Exact next action for Qoder: CP29 diagnostic-only run

No source/config/geometry/policy/controller changes are authorized before the
following fresh evidence. Do not reuse CP28’s process or raw capture.

1. In new **CP29-only** tmux windows under `so101-moveit`, export:

   ```zsh
   export ROS_DOMAIN_ID=229
   export GZ_PARTITION=so101_cp29_7hZSj6
   export SIMULATION_SESSION_ID=cp29-7hZSj6
   source ~/gui-env.zsh
   source /opt/ros/jazzy/setup.zsh
   source /data/work/ws_moveit/install/setup.zsh
   ```

   Record window names, root PIDs, process tree, UTC start time, and the
   environment identity. Ensure no old process is selected by discovery.

2. Launch a new isolated Gazebo/MoveIt stack only after installed launch
   `--show-args` and source/install provenance have been checked. Baseline must
   use **Gazebo transport** `/so101/object_attached` (not ROS topic discovery),
   direct cup pose/TF, active controllers, and supported no-motion
   `so101_moveit_scene upsert/observe`. Attachment must be detached and cup
   must be a MoveIt world object.

3. Start the already-tested temporary recorder in a CP29 capture window with
   duration **at least 180 seconds**:

   ```zsh
   python3 /tmp/so101-debug-cp28-pending/capture_descend_diagnostics.py capture \
     --output /tmp/so101-debug-cp29.7hZSj6/descend-raw.jsonl \
     --duration-s 180
   ```

4. **Mandatory READY handshake before any motion/state-machine action:**

   - recorder PID is alive;
   - record `date -u +%FT%TZ` and first `wc -l` count of `descend-raw.jsonl`;
   - wait one second without action, prove the same PID is alive, record a
     second UTC timestamp and second count;
   - second line count must be strictly greater than the first;
   - take a fresh CUA pre-action snapshot and inspect it; immediately prove
     recorder remains alive after that snapshot.

   If any READY condition fails, **stop without PREPARE or any movement** and
   clean only proven CP29 resources. Record the failed handshake.

5. Only when READY is recorded, execute exactly one ladder in this order,
   stopping at the first failure and never CLOSE:

   - supported no-motion scene upsert;
   - `PREPARE_OPEN_GRIPPER`;
   - plan-only `MOVE_ABOVE_OBJECT`;
   - execute `MOVE_ABOVE_OBJECT`;
   - execute `DESCEND`.

   Use the existing checkpoint/resume semantics, never a raw joint publisher
   or manual controller message. At visual gates use CUA snapshot → action →
   fresh snapshot and bind screenshot paths to CP29 PIDs/windows.

6. After DESCEND abort/success, retain recording for at least three seconds
   after the action terminal timestamp, then stop the recorder deliberately.
   Prove raw first/last wall times span DESCEND start **and** end before any
   causal analysis. Analyze with:

   ```zsh
   python3 /tmp/so101-debug-cp28-pending/capture_descend_diagnostics.py analyze \
     --raw /tmp/so101-debug-cp29.7hZSj6/descend-raw.jsonl \
     --output /tmp/so101-debug-cp29.7hZSj6/descend-analysis.json \
     --repo /data/work/ws_moveit/src/so101_gazebo_demo \
     --asset-root /data/work/ws_moveit/build/so101_gazebo_demo/fingertip_pad_assets
   ```

7. Report separately:

   - **OBSERVED:** planned/commanded/actual q1–q6, TCP, direct cup 6D pose and
     drift, exact Gazebo contact pair/depth, controller abort, RTF, attachment,
     and all 12 wall signed clearances for every actual sample.
   - **INFERRED:** the first bad UTC timestamp/pair and ordering of cup motion
     versus native-pad contact, only if the raw time-span proof succeeded.
   - **HYPOTHESIS:** exactly one next A/B variable; no product edit yet.

8. Take a fresh post-state Gazebo screenshot and a close-up that, if physically
   possible, resolves both blue pads and cup wall. Do not call an inconclusive
   camera result an acceptance. Clean only CP29-owned tmux windows/PIDs after
   checking their saved process tree and `/proc/<pid>/environ`; `TERM` only
   proven CP29 processes. Prove protected old stacks remain.

## Diagnostics, tests, and provenance locations

| purpose | path |
|---|---|
| master CP1–19 evidence | `/tmp/so101-debug-current-MQopWL/subagent-report.md` |
| native gap calculator / exact header generator | `src/so101_gazebo_demo/scripts/gripper_preopen_calc.py` |
| generated native calibration authority | `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/fingertip_pad_gap_calibration_data.hpp` |
| mesh/profile and robust geometry regression | `src/so101_gazebo_demo/test/test_fingertip_pad_geometry.py` |
| gap/profile/mesh binding and exact regeneration | `src/so101_gazebo_demo/test/test_fingertip_pad_gap_calibration.py` |
| original-width dense calibration/header regression | `src/so101_gazebo_demo/test/test_gripper_preopen_calc.py` |
| simulation-model collision/friction canonical-name regression | `src/so101_gazebo_demo/test/test_prepare_simulation_model.py` |
| planner whitelist/transfer validation regression | `src/so101_gazebo_demo/test/pick_place/test_so101_motion_planner.cpp` |
| endpoint/state-machine forward-gating regressions | `src/so101_gazebo_demo/test/pick_place/test_so101_motion_validation.cpp`, `src/so101_gazebo_demo/test/pick_place/test_pick_place_runner.cpp` |
| controller/config/SRDF contract regression | `src/so101_gazebo_demo/test/test_configuration_contract.py` |
| CP28/CP29 capture tool and its tested preflight | `/tmp/so101-debug-cp28-pending/capture_descend_diagnostics.py`, `/tmp/so101-debug-cp28-pending/test_cp28_descend_diagnostics.py` |

Before a source fix, write a focused RED test. After the smallest patch, run
the directly affected tests, package build, source the overlay, and verify
installed provenance (package prefix and relevant source/install hashes or
symlink resolution). Do not run broad CTest: historical launch/world tests can
start runtime nodes. Reuse the audited CP19 safe offline set or explicit
focused tests only.

## Six-layer evidence contract (so101-dev)

| layer | required evidence |
|---|---|
| 1. Source / build / provenance | focused RED→GREEN, package build, sourced overlay, installed package/header/policy provenance; `git diff --check`. |
| 2. Geometry / calibration | Blender/profile/mesh/URDF fingerprint, exact generated-header tests, signed clearance/full collision audit. |
| 3. Policy / state machine | explicit state transition, child exit/result and fail-closed postcondition/recovery evidence; no terminal-action-success shortcut. |
| 4. MoveIt | plan artifact, planning scene world/attached membership, allowed-contact policy, plan-only versus executed proof. |
| 5. Controller / telemetry | measured joint states/velocities, controller state/result, TF/current TCP, RTF, timestamps and abort/quiescence evidence. |
| 6. Gazebo / visual | Gazebo transport attachment, direct cup pose/contact/penetration, PID-bound screenshots actually inspected through CUA. |

No layer can be substituted for another. Logs/topics alone do not replace
visual evidence; a screenshot alone does not replace controller/physics data.

## Full DONE acceptance matrix

| ladder stage | acceptance, in addition to preceding layers |
|---|---|
| isolated baseline | unique domain/partition/session/windows/PIDs; Gazebo attachment=false on correct transport; cup 6D pose; controller active; base→`so101_tcp` TF; MoveIt cup in world; fresh inspected screenshot. |
| `PREPARE_OPEN_GRIPPER` | authoritative child success; q6 reaches generated preopen target within existing tolerance; arm joints 1–5/TCP/cup unchanged; detached/world unchanged; safe contacts. |
| plan-only `MOVE_ABOVE_OBJECT` | authoritative planning success; no controller trajectory/execution; joints/TCP/cup/attachment/scene unchanged. |
| execute `MOVE_ABOVE_OBJECT` | controller and MoveIt result green; measured joints/TCP reach contract; cup still unchanged, detached/world; fresh image. |
| `DESCEND` | measured contact-critical endpoint and q6 contracts green; all active collision evidence valid; pad penetration ≤0.8 mm, cup drift ≤3 mm, RTF/controller health good; both native blue pads/cup relation conclusively visible. |
| `CLOSE_GRIPPER` | observed q6, generated actual inner-face gap and cup-wall interference valid; fixed pad outside, moving pad contacts near wall only; exact contact pairs/depth and cup drift within contracts; attachment remains false; conclusive close-up. |
| `ATTACH_GAZEBO` / `ATTACH_MOVEIT` | independent Gazebo attachment=true and MoveIt attached membership/link/touch-link proof; no inferred bridge state. |
| `LIFT` | cup follows TCP in Gazebo, MoveIt attached state remains correct, measured controller/joint/TF movement and fresh screenshot. |
| place / `DONE` | Gazebo detach and MoveIt detach/world synchronization; final cup pose, upright/table-clearance and retreat feedback valid; state-machine exit success; fresh tiled CUA image has RViz left/Gazebo right and `tile_ai_station_guis.py` reports `LAYOUT_OK`. |

Advance only when the row passes. At the first failure, stop the ladder, retain
raw evidence, record **OBSERVED / INFERRED / HYPOTHESIS**, the first bad
boundary, and one A/B variable. Never extend waits or relax thresholds.

## Reports and screenshots retained

All listed paths are absolute and should be preserved. A directory path means
its report names every command/exit and contains the associated logs/screens.

| checkpoint | report | known screenshots / key artifacts |
|---|---|---|
| CP1–19 | `/tmp/so101-debug-current-MQopWL/subagent-report.md` | `gazebo-pre-restart.png`, `rviz-pre-restart.png`, `gui-gazebo-move-above-11.png`, `gui-gazebo-descend-11.png`, `gui-gazebo-close-failed-11.png`, `gui-gazebo-descend-closeup-12-ab.png`, `checkpoint13-gazebo-pre-close.png`, `checkpoint13-gazebo-post-close.png`, `checkpoint13-rviz-post-close.png`; CP13 telemetry/raw files share the `checkpoint13-*` prefix in this directory. |
| CP20 | `/tmp/so101-debug-cp20.e7WR39/CP20-report.md` | `baseline-gazebo-pre.png`, `baseline-gazebo-post-action.png`, `baseline-rviz-pre.png`, `baseline-rviz-post-action.png`, `checkpoint-path.txt`, `cleanup.txt`. |
| CP21 | `/tmp/so101-debug-cp21.B0miSW/CP21-report.md` | `pre-plan-gazebo.png`, `pre-plan-gazebo-post-action.png`, `pre-plan-rviz.png`, `pre-plan-rviz-post-action.png`, `plan-failure-gazebo.png`, `plan-failure-rviz.png`, `cleanup.txt`. |
| CP22 | `/tmp/so101-debug-cp22.tAuqlg/CP22-report.md` | `preopen-gazebo-pre.png`, `preopen-gazebo-close.png`, `preopen-gazebo-closeup.png`, `preopen-gazebo-closeup2.png`, checkpoint files. |
| CP23 | `/tmp/so101-debug-cp23.kWLiND/CP23-report.md` | `gazebo-baseline.png`, `gazebo-preopen-closeup.png`, `gazebo-preopen-closeup-retry.png`, `gazebo-move-above-failure.png`, `rviz-move-above-failure.png`, `plan-only-checkpoint.json`, `preopen-checkpoint.json`. |
| CP24 | `/tmp/so101-debug-cp24.cMXy9W/CP24-report.md` | `gazebo-baseline.png`, `gazebo-before-execute.png`, `gazebo-move-above-pass.png`, `rviz-move-above-pass.png`, `gazebo-before-descend.png`, `gazebo-after-descend-failure.png`, checkpoint files. |
| CP25 | `/tmp/so101-debug-cp25.bX2CR7/CP25-report.md` | `gazebo-baseline.png`, `gazebo-before-execute-move-above.png`, `gazebo-move-above-pass.png`, `gazebo-after-descend-failure.png`, checkpoints. |
| CP26 | `/tmp/so101-debug-cp26.cMBhFj/CP26-report.md` | `gazebo-baseline.png`, `gazebo-before-execute-move-above.png`, `gazebo-before-descend.png`, `gazebo-after-descend-failure.png`, checkpoints. |
| CP27 | `/tmp/so101-debug-cp27.fmAl4v/CP27-report.md` | `gazebo-baseline.png`, `gazebo-after-prepare.png`, `gazebo-before-descend.png`, `gazebo-after-descend-failure.png`, `rviz-baseline.png`, `rviz-after-descend-failure.png`, `prepare-open.log`, `move-above-plan-only.log`, `move-above-execute.log`, `descend-execute.log`, `gazebo.log`, `moveit.log`. |
| CP28 | `/tmp/so101-debug-cp28.6FEgTJ/CP28-report.md` | `gazebo-baseline.png`, `gazebo-before-descend.png`, `rviz-baseline.png`, `descend-raw.jsonl` (**invalid for temporal inference**). |
| CP29 | `/tmp/so101-debug-cp29.7hZSj6/CP29-report.md` | `cua-baseline-gazebo.png`, `cua-baseline-gazebo-state.json`, `descend-raw.jsonl`, `descend-analysis.json`, `checkpoint.json`, `evidence-hashes.txt`, baseline/descend log suite. |
| CP30 / CP30R | `/tmp/so101-debug-cp30.8bp488/CP30-report.md`, `/tmp/so101-debug-cp30.8bp488/CP30R-report.md` | `compute_ik_response.txt`, `red-test-output.txt`, `green-test-output.txt`, `cp30r_baseline.png`, `cp30r_post.png`, `cp30r_gui_state_1.json`, `cp30r_sm.log`, `cp30r_bag/`, `cp31b_ik_request.yaml`, `cp31b_ik_response.txt`, `INVALID_BROAD_CLEANUP_ATTEMPT_NO_DAMAGE.txt`. |
| CP31B | (same directory as CP30/CP30R; narrative in this handoff) | `cp31b_ik_response.txt`, `cp31b_ik_request.yaml`, `cp31b_launch.log`; source/install `light_cup_wall_pick.yaml` both SHA-256 `c1c123b7c7e3fcf6d2188ab1133a9cdbfc40eeec227a50f59a7e474a5d457279`. |

## Handoff stop point (current: CP31B — paused for rebase)

### Current single-variable edit (CP31B)

Only `config/motion_policies/light_cup_wall_pick.yaml` is changed versus
CP30R: the inserted DESCEND (and mirrored RECOVER_DESCEND_TO_PICK)
retreat waypoint target amplitude is reduced from **8.0 mm** to
**4.0 mm** along -Y world. Direction, orientation, Z, endpoint,
validation policy, controller, geometry, and every other configuration
field are unchanged.

- Source/install motion-policy SHA-256:
  `c1c123b7c7e3fcf6d2188ab1133a9cdbfc40eeec227a50f59a7e474a5d457279`.
- Source/install validation-policy SHA-256 (CP29 baseline, untouched):
  `6dbbe602e2f57ef39ad747d7ad924281e8d71f06d5880d29198dc9576ab248c6`.
- IK joints (production `/compute_ik`):
  `[-0.000264207708, 0.369621146811, 0.028193436672, 1.172988068969, -0.000271648009]`.
- Real MoveIt FK Y at waypoint: `-0.268029587` (≈ 3.999 mm retreat
  from start Y = `-0.264030551`).
- Test suite: **17/17 gtest PASS**, including
  `DescendIntermediateWaypointRetreatsFromWallNear` reporting
  `retreat=3.999 mm ≥ 3 mm` and lateral deviation ≈ 4 mm ≤ 5 mm gate.

### Runtime state at handoff

- A CP31B launch attempt under `ROS_DOMAIN_ID=233` / `GZ_PARTITION=so101_cp31b_3mm`
  died during Gazebo GUI initialization (see
  `/tmp/so101-debug-cp30.8bp488/cp31b_launch.log`). The naming was
  acknowledged as wrong (should be `4mm`, not `3mm`). No CP31B runtime
  ladder has executed. All CP30R domain-231 processes have been
  TERM'd by explicit PID; protected PIDs `131650, 132125, 147388, 147856, 149852, 152395`
  remain alive.
- A leftover `ros2-daemon` process on `ROS_DOMAIN_ID=230` (PID `1557051`)
  from CP30 still exists and is not CP31B-owned.

### Next action when supervisor resumes CP31B

1. Record git status / HEAD / branch / remotes, create a labelled
   stash including untracked files, fetch remote main, rebase onto
   `remote/main`, reapply the stash, and re-read `AGENTS.md` plus
   `.agents/skills/so101-dev/SKILL.md` and referenced skill files.
2. Launch a fresh isolated stack with a **new** domain and a
   **4mm-named** partition (not `3mm`), one Gazebo GUI after
   `source ~/gui-env.zsh`, reuse the existing `so101-moveit` tmux
   session windows.
3. Run the recorder, pass the READY handshake, and execute the
   ladder **strictly through DESCEND** with `--stop-after DESCEND`
   and `--session-id cp31b_retreat`.
4. PASS criteria: controller success, no CLOSE, native pad-cup
   penetration ≤ 0.8 mm, cup drift ≤ 3 mm. Capture CUA pre/post
   screenshots and analyze native contacts, drift, and controller
   result. Stop at the first failure.

Do not resume runtime before the rebase, re-read of skill/agents
docs, and supervisor approval are recorded.
