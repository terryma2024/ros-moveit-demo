# SO101 fixed-finger collision handoff (2026-07-29)

## Mission

Continue the SO101 Gazebo pick/place diagnosis independently until there is an evidence-backed fix. Use the project-local `so101-dev` skill before acting. The immediate diagnostic requested by the user is:

> Temporarily render every gripper / fixed-finger / moving-jaw visual with the exact geometry used by its Gazebo collision model, then take fresh Gazebo screenshots. This should make any oversized, displaced, overlapping, or unexpected collision hull directly visible.

Do not treat a disabled collision as a production fix. Use it only as an A/B diagnostic.

## Safety and workspace state

- Workspace: `/data/work/ws_moveit`
- Branch: `codex/direct-tpu-tongues`
- The worktree is extremely dirty with a large amount of user/previous-agent work. Do not reset, clean, checkout, rebase, mass-format, or overwrite unrelated files.
- Inspect diffs and make only narrowly scoped changes. Before editing, preserve the exact current file or use temporary xacro / launch files under `/tmp` for diagnostics.
- Never run multiple Gazebo stacks. Before each run, inspect PIDs and exact `ROS_DOMAIN_ID` / `GZ_PARTITION`; stop only the stack you own.
- GUI startup: use tmux, `source ~/gui-env.zsh`, then ROS Jazzy and `/data/work/ws_moveit/install/setup.zsh`. Get real visual evidence with `ai-station-capture.sh`.
- The user says this machine will shut down soon. First stop the owned diagnostic ROS/Gazebo processes and save your next-action state. After reboot, resume from this document.

## Current diagnosis: decisive A/B evidence

All runs used the same motion policy:

- `/tmp/motion-policy-plus3y-above5z-q6m040.yaml`
- `/tmp/validation-policy-plus3y-above5z-q6m040.yaml`
- Target change relative to prior policy: TCP +3 mm Y toward pedestal side; MOVE_ABOVE +5 mm Z.
- Stop point: `DESCEND`.

Results:

| Gazebo gripper collision configuration | Cup position drift | Cup orientation drift | Outcome |
|---|---:|---:|---|
| Original substrate VHACD + both TPU pads | 9.305 mm | 0.141626 rad (8.11 deg) | pushed cup, failed |
| No substrate VHACD, both TPU pads | about 3.06 mm | about 0.0161 rad (0.92 deg) | still pushed cup |
| No substrate VHACD, fixed TPU collision removed, moving TPU retained | about 0.0003 mm | about 0.0011 deg | DESCEND succeeded, cup unchanged |
| No substrate VHACD, moving TPU collision removed, fixed TPU retained | 8.07254 mm | 0.139882 rad (8.01 deg) | pushed cup, failed |

The last two tests are the decisive RED/GREEN pair: the fixed-finger side causes the cup disturbance; moving-jaw TPU alone does not measurably move the cup.

Important nuance:

- The fixed TPU visual and collision union bounds previously matched exactly.
- The original fixed-finger VHACD substrate has outward over-approximation in sampled regions up to roughly 1.56 mm and amplifies the contact.
- Therefore likely two contributors exist: (1) overly conservative fixed substrate VHACD; (2) the current TCP path actually places the fixed TPU pad against / into the cup exterior wall.
- Removing the fixed TPU collision is diagnostic only and is not acceptable as the fix.

## Evidence and temporary artifacts

Baseline with original collisions:

- `/tmp/so101-collision-verify-20260729T2250/checkpoint.json`
- `/tmp/so101-collision-verify-20260729T2250/task.log`
- failure metrics: `task_object_position_drift=0.00930541045337`, `task_object_orientation_drift_rad=0.141625505408`

Both substrate collisions removed, both TPU pads retained:

- `/tmp/so101-pad-only-ab-20260729T2325/checkpoint.json`
- actual generated SDF had 0 fixed substrate hulls, 0 moving substrate hulls, 7 fixed TPU hulls, 6 moving TPU hulls.

Fixed TPU collision removed, moving TPU retained (GREEN):

- `/tmp/so101-no-fixed-pad-ab-20260729T2335/checkpoint.json`
- generated SDF `/tmp/so101-gazebo-2902605.sdf`: fixed TPU 0, moving TPU 6
- checkpoint cup pose was essentially nominal: x=0.0199997220, y=-0.2800000608, z=0.1649999917
- task ended `status=CHECKPOINT_COMPLETE`, `DESCEND` succeeded.

Moving TPU collision removed, fixed TPU retained (RED):

- `/tmp/so101-no-moving-pad-ab-20260729T2340/checkpoint.json`
- generated SDF `/tmp/so101-gazebo-2906989.sdf`: fixed TPU 7, moving TPU 0
- failure: `TASK_OBJECT_POSITION_DRIFT`
- metrics: `task_object_position_drift=0.00807254017032`, `task_object_orientation_drift_rad=0.139881561042`

Temporary diagnostic model files:

- `/tmp/so101-no-substrate-collision/`
- `/tmp/so101-no-fixed-pad-collision/`
- `/tmp/so101-no-moving-pad-collision/`
- `/tmp/so101_gazebo_no_substrate.launch.py`
- `/tmp/so101-empty-collision-manifest.json`

Note: `/tmp` will disappear after reboot; preserve anything needed before shutdown.

## Critical cache bug discovered

`scripts/prepare_simulation_model.py` computes its cache key from the top-level xacro bytes but not bytes of included xacro files. Editing only `so101_base.xacro` can incorrectly reuse a stale prepared SDF. For all diagnostic variants, use a fresh isolated `XDG_CACHE_HOME` and verify the actual generated `/tmp/so101-gazebo-*.sdf` collision-name counts before executing.

Do not trust the requested xacro alone; inspect the generated SDF.

## Required collision-as-visual diagnostic

Implement this as a temporary, reversible diagnostic, preferably under `/tmp` first:

1. Produce a diagnostic xacro in which every relevant gripper link visual is replaced or supplemented with the exact collision geometry and exact origin / rpy used by Gazebo:
   - fixed substrate VHACD pieces `fixed_finger_contact_convex_000..006`
   - moving substrate VHACD pieces `moving_jaw_contact_convex_000..007`
   - fixed TPU collision pieces `fixed_fingertip_pad_collision_000..006`
   - moving TPU collision pieces `moving_fingertip_pad_collision_000..005`
2. Give the four collision families distinct high-contrast translucent colors (for example red=fixed substrate, magenta=fixed TPU, blue=moving substrate, cyan=moving TPU). Keep names clear.
3. Hide the normal gripper / jaw visuals if necessary so the collision shapes are unambiguous; optionally make a second overlay screenshot with both original visuals and translucent collision visuals.
4. Start one clean GUI Gazebo stack, maximize only the Gazebo window, use the agreed camera pose or a close side view of the cup rim and both fingertips.
5. Capture at least:
   - MOVE_ABOVE before descent
   - the first contact during DESCEND
   - the final / aborted descent pose
   - close views from both sides if one view occludes the fixed pad.
6. Record which exact fixed collision piece first intersects the near cup wall. If possible, enable Gazebo collision visualization as a second independent view.
7. Report facts separately:
   - geometry mismatch (collision outside its intended visual)
   - transform mismatch (correct shape, wrong pose)
   - path interference (collision matches visual but TCP drives it into cup)
8. Then choose the minimal real fix:
   - regenerate / trim only the offending fixed substrate VHACD pieces if they are oversized;
   - correct fixed-pad transform if displaced;
   - otherwise move TCP sufficiently away from the fixed wall while retaining fixed TPU collision.
9. Production acceptance must restore all real collision geometry and show a fresh run where DESCEND does not move the cup beyond tolerance, before attempting close/lift/place.

## Suggested first command after reboot

Read the project skill and this handoff, inspect worktree and current branch, then recreate one clean GUI stack. Do not begin with tests or broad refactors. First generate and visually inspect the collision-as-visual model, take screenshots, and identify the exact fixed collision piece / transform causing contact.

Continue independently through diagnosis, fix, clean rebuild/source, and fresh Gazebo visual acceptance. Do not stop after merely proposing the next command.

## Shutdown-resume checkpoint (2026-07-29 23:25 CST)

- Current checkout is still `codex/direct-tpu-tongues` at `ff659cb59cb8f53eb4032dec53e0d0a3c05b1de1`; the large dirty worktree was preserved without reset, clean, checkout, rebase, or broad formatting.
- The prior fixed-finger diagnostic ROS/Gazebo stack was fully stopped: at the first process and ROS graph audit there were no `gz sim`, `move_group`, `rviz2`, `pick_place_state_machine`, or ROS nodes.
- At 23:25:10, after that clean audit, a separately owned headless Gazebo launch appeared from `.worktrees/gazebo-video-debug/install/so101_gazebo_demo/...` (launch PID 2921940, server PID 2921989 at the time observed). It was not started or stopped by this diagnostic. Re-resolve PIDs after reboot; never reuse these numeric PIDs blindly.
- **First action after reboot:** reread `.agents/skills/so101-dev/SKILL.md` and this handoff, audit the dirty checkout and live processes, then generate the collision-as-visual xacro with a fresh isolated `XDG_CACHE_HOME`; inspect the resulting `/tmp/so101-gazebo-*.sdf` before starting exactly one maximized GUI Gazebo stack.
- The immediate hypothesis remains: the collision-as-visual sequence will distinguish fixed-substrate VHACD over-approximation, a fixed-TPU transform mismatch, and true TCP path interference at the first cup-wall contact.

## Collision-as-visual localization and live fix boundary (2026-07-30 00:08 CST)

- A fresh isolated-cache SDF duplicated every active collision pose and geometry as a colored visual: fixed substrate red (7), fixed TPU magenta (7), moving substrate blue (8), moving TPU cyan (6). The live `/tmp/so101-gazebo-*.sdf` passed `gz sdf -k`, and collision/diagnostic-visual pose+geometry pairs were identical.
- The first live contact was repeatedly `plastic_cup::body::wall_near` against `so101::gripper::gripper_fixed_joint_lump__fixed_fingertip_pad_collision_005_collision_12`. Its live SDF pose and magenta diagnostic visual pose were identical (`5.55112e-17 -0.000218214 0.000949706 -3.14159 ...`); Gazebo model pose and ROS TF agreed. This rules out collision/visual and TF transform mismatch.
- Near/opposite screenshots localize magenta `_005` crossing the near wall while the fixed finger is intended to remain outside: `/tmp/so101-fixed-visual-20260729-ZhaamB/first-fixed-contact-{near,opposite}.png`.
- Coherent world-Y runtime A/B with all real substrate and TPU collisions restored:
  - prior +3 mm-Y/+5 mm-Z baseline: `_005`, about 0.431 mm depth, cup pushed;
  - additional +4 mm Y: `_005`, about 1.445 mm depth, cup pushed;
  - additional +6 mm Y: `_005`, about 1.443 mm depth, cup moved about 0.69 mm;
  - additional +7 mm Y: **no fixed contact**, `DESCEND` `CHECKPOINT_COMPLETE`, cup stayed `[0.020000, -0.280000, 0.165000]` with only RPY numerical noise;
  - additional +8 mm Y independently also had no fixed contact and unchanged cup pose.
- +7 mm relative to `/tmp/motion-policy-plus3y-above5z-q6m040.yaml` is the first tested no-contact lane: total +10 mm world Y and +5 mm MOVE_ABOVE Z relative to the current source policy. Decisive maximized-Gazebo screenshot: `/tmp/so101-fixed-visual-20260729-ZhaamB/plus7-descend-near.png`.
- A RED→GREEN policy-continuity regression was added to `test/test_fingertip_pad_geometry.py`. Source motion/validation policies were patched only across pick approach, descend, lift, and dependent recovery continuity. The targeted regression is green. The full new geometry file currently has five failures from static grasp-platform assumptions; two also show that CLOSE/grasp geometry must be re-derived before attempting CLOSE/LIFT/PLACE. Do not represent those stages as accepted.
- **If interrupted now:** audit and stop only owned `so101-fixed-visual-{gui,moveit,task,contact}` sessions if present. Then build/source `so101_gazebo_demo`; start a fresh ordinary non-diagnostic GUI Gazebo with isolated `XDG_CACHE_HOME`; inspect its actual SDF; execute the installed production policy through `DESCEND`; save watcher, cup pose, and screenshot evidence; exact-clean the owned stack.

## Fresh production acceptance (2026-07-30 00:12 CST)

- `colcon build --packages-select so101_gazebo_demo --symlink-install` completed with exit 0. The installed production motion policy resolves to the source policy and had matching SHA-256 `643341bde617f0be3777175b1d5a670ab1df4d791c87fde103cf04062eb7cbc6`.
- A new ordinary `so101_gazebo.launch.py` GUI stack (no diagnostic collision visuals) was started with isolated cache `/tmp/so101-fixed-production-cache-20260730-*`.
- Its actual generated `/tmp/so101-gazebo-2979406.sdf` was `Valid` and contained the restored collision families 7 fixed substrate / 7 fixed TPU / 8 moving substrate / 6 moving TPU.
- The installed production motion and validation policies were passed explicitly to `so101_pick_place.launch.py`, `run_mode:=execute`, `stop_after:=DESCEND`. Result: process exit 0, `status=CHECKPOINT_COMPLETE`, trace through `DESCEND`.
- `/tmp/so101-fixed-visual-20260729-ZhaamB/production-fixed-contact.log` contains only `CONTACT_WATCHER_READY`: no fixed cup-wall contact occurred.
- Gazebo cup pose after DESCEND stayed `[0.020000, -0.280000, 0.165000]`, RPY `[-0.000000, 0.000000, -0.000020]`, identical to the fresh start pose to printed precision.
- Fresh maximized ordinary-Gazebo screenshot `/tmp/so101-fixed-visual-20260729-ZhaamB/production-descend-near.png` visually confirms fixed finger outside, moving finger inside, and an upright unmoved cup.
- Scope gate remains: DESCEND is accepted. CLOSE/LIFT/PLACE were not attempted because the static grasp-platform tests must be reconciled with this live no-contact lane first.

## Synchronized -0.6 degree two-dimensional solve audit (2026-07-30 08:02 CST)

- The requested synchronized sample was recovered from the recorder before ATTACH at simulation time 40.802 s. Its derived actual q6 was `-0.04692 rad`; the cup pose was `[0.020006202, -0.281111836, 0.166260481]`.
- Dense exact SAT using that same cup/gripper sample reproduced the proposed `-world Y` direction. At an additional `-1.000 mm` TCP Y and unchanged q6, nominal fixed/moving exact depths were `0.031537/0.174080 mm`; open/closed moving depths were `0.093838/0.254298 mm`.
- The exact IK for that transform converged with position error `6.39e-16 m` and orientation error `1.34e-8 rad`. Across all 32 arm endpoint corners, both `+/-0.1 mm` wall-normal observations, and open/target/closed q6, maximum fixed/moving exact penetration was `0.268959/0.498307 mm`, with zero `0.8 mm` violations. Evidence: `/tmp/so101-debug-20260730-mainline-9dvv2n/pitch-minus0p6-inward0p22-ab/yminus1p0-q6unchanged-endpoint-audit.json`.
- A temporary `q6 +1.6 mrad` alternative was rejected before build/live because it requires pad gap `2.090413 mm`, larger than the `2.000 mm` wall. The unchanged calibration regression correctly failed; no physical contract was weakened and all q6/gap/header changes were withdrawn.
- Adding the mandatory DESCEND contract makes the apparent synchronized solution infeasible. The `-1.000 mm` point intersects fixed pieces `_004..006` at preopen. The first nominal preopen fixed intersection occurs between additional `-0.525` and `-0.550 mm`. At `-0.500 mm`, nominal preopen is collision-free and CLOSE fixed gap is only `0.031263 mm`, but its retained live-clear lane margin is `0.355050 mm`, below the existing `0.500 mm` hard margin. Enforcing the margin limits inward motion to about `-0.355 mm`, where fixed clearance remains about `0.176 mm`, above the requested `0.050 mm` nominal band. q6 cannot change the fixed side, so the requested Y x q6 feasible intersection is empty under all gates.
- RED evidence for the rejected `-0.500 mm` source candidate produced exactly five geometry failures; four were stale attachment-derived expectations, while `test_fixed_pad_pick_lane_has_live_margin_and_no_cup_contact_through_descend` was the decisive physical failure (`0.355050 < 0.500 mm`). Those source/test edits were withdrawn. Restored strict geometry suite: `18 passed in 69.24s`, evidence `/tmp/so101-debug-20260730-mainline-9dvv2n/post-static-reject-geometry-restored.txt`.
- A single fresh domain-52 stack was started recorder-first for the `-1.000 mm/+1.6 mrad` temporary config, but runtime stopped before any motion because fingerprint-bound q6 calibration rejected the mismatch. The stack and all recorders were then cleaned. No live collision evidence from that pre-action run may be treated as a candidate result.
- Current hard blocker: the fixed-side requirements are mutually exclusive for this `-0.6 degree` Y x q6 family: synchronized bilateral fixed clearance `<=0.05 mm` needs about `-0.98..-1.00 mm`, while preopen zero-contact plus the established live-clear margin permits only about `-0.355 mm`. Do not force this family live, weaken the 0.5 mm lane margin, or change q6 calibration. Resume from the first mechanism boundary: find a motion/contact geometry that makes the moving jaw push the cup toward the fixed pad without spending the DESCEND margin; keep stable raw `<=0.8 mm`, exact `<=0.8 mm`, drift `<=3 mm`, and tilt `<=0.035 rad` unchanged.
