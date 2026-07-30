# SO-101 pick-place Codex CP35H handoff

## Session state

- Workspace: `/data/work/ws_moveit`; HEAD `ff659cb`.
- **Do not reset, clean, stash, commit, or push.** The worktree is heavily dirty and contains
  substantial prior user work. `git status --short` was saved in this handoff turn output; inspect
  it before editing. Existing stashes must be preserved.
- Root `AGENTS.md` requires `.agents/skills/so101-dev/SKILL.md`; read it and all relevant refs.
- Do not use Qoder, `gh`, tolerance relaxation, PID changes, or delete path tolerance.
- Tolerances remain arm path `0.0015`, goal `0.00025`; default velocity/acceleration `.10/.10`.
- CUA protocol: snapshot before/after GUI actions. User required Gazebo-only visual evidence for
  experiments. Latest explicit pause for user recording has already completed; subsequent tests
  need fresh evidence.

## Current processes / tmux

At handoff creation there are no live `gz`, `move_group`, or `pick_place_state_machine` processes.
`tmux so101-camera-workarea` has `cp35i` and user-owned `layout`; CP35I has already failed and its
window may be removed before the next attempt. Verify exact PIDs/windows before any launch.

## Decisive geometry evidence

- User video: `/tmp/so101-debug-cp35g-single-stack-20260729T103506Z/user-recording.mp4`.
- Video starts about `18:42:39.708`; q1 tolerance occurs about video `t=10.691 s`.
- During late DESCEND, the **outside fixed TPU pad** reaches the near wall first and pushes the cup;
  q1 `1.752 mrad > 1.5 mrad` is downstream physical-contact behavior, not a reason to loosen the
  path gate.
- `so101_tcp` is fixed on `gripper` at `(0.0214,0,-0.083949)`. It is not a TPU contact center and
  does not depend on q6. Audit actual fixed/moving pad surfaces, not TCP insertion depth.
- Contract: fixed side `outside`, moving side `inside`, near-wall outward normal world `+Y`.
  Keep X/Z/orientation unchanged initially. Translate **all MOVE_ABOVE and DESCEND waypoints**
  coherently in world `+Y`; do not only move the final waypoint.

## Coupled search and official calibration work

Evidence dir: `/tmp/so101-debug-cp35g-single-stack-20260729T103506Z`.

- Coupled grid: `coupled-grid.json`; for coherent `+1.0 mm +Y`, q6 `-0.040` predicts fixed
  pre-close clearance `1.269448 mm` and moving penetration `0.714742 mm` (within `0.1–0.8 mm`).
- `q6=-0.040` corresponds to real native-pad gap `0.0025634223861939628 m`, computed using the
  test asset root `build/so101_gazebo_demo/fingertip_pad_assets`.
- Production files intentionally modified as part of the formal chain:
  - `config/task_objects/light_plastic_cup.yaml`: `fingertip_pads.grasp_gap_m` now
    `0.0025634223861939628`.
  - `config/motion_policies/light_cup_wall_pick.yaml`: `grasp_close_q6` now `-0.040000000000000`.
  - `include/.../fingertip_pad_gap_calibration_data.hpp`: regenerated verbatim by renderer; it has
    `kGraspQ6=-0.040`, `kGraspGapM=0.002563422386194`.
  - `test/pick_place/test_policy_config.cpp`: positive contract fixtures/expectations updated to
    the new official values; negative mismatch/lower-bound tests retained.
- The renderer script used is `regenerate_pad_calibration.py` in the evidence dir. It was syntax
  checked with `python3 -m py_compile`; it invokes
  `calculate_fingertip_pad_gap_calibration(object yaml, build/.../fingertip_pad_assets, URDF)` and
  prints only `render_fingertip_pad_gap_calibration_header` output. Do not append diagnostic text
  to the header (an earlier attempt did and caused C++ errors, subsequently corrected).
- Current header/object `calibration_fingerprint` are both
  `b101b7db33a13c82797eb80c2356f1c6b509e04bdae7999efd4b6a8ce0d1094f`.

## Build and test facts

- `colcon build --packages-select so101_gazebo_demo` succeeded: `colcon-final.exit` says 0.
- Initial CTest failures were fixed:
  1. test fixtures had intentional old q6/gap values;
  2. Python CTest was run without `source install/setup.zsh`, so `ament_index` did not see the
     package.
- After rebuilding and sourcing `/opt/ros/jazzy/setup.zsh` + `install/setup.zsh`, command
  `ctest --test-dir build/so101_gazebo_demo -R 'policy_config|gripper_preopen' --output-on-failure`
  produced **2/2 tests, 100% passed** in `ctest-contract-fix.log`.
- Before any runtime, rerun the exact focused tests and confirm `ros2 pkg prefix so101_gazebo_demo`
  is `/data/work/ws_moveit/install/so101_gazebo_demo`.

## Invalid runs (never compare them as A/B results)

- CP34 used ROS domain 234 and malformed script: INVALID.
- CP35 final-waypoint-only +1 mm: INVALID for MOVE_ABOVE alignment hypothesis.
- CP35D: GUI lacked DISPLAY/XAUTHORITY; bootstrap joint evidence failure downstream.
- CP35E: capture worker died after one preframe (nonpersistent owner); INVALID.
- CP35F: World readiness timeout; multiple stack contamination earlier; INVALID.
- CP35H: policy q6 was rejected by fingerprint gate. This led to formal calibration work above;
  it did not execute motion.
- CP35I: `WORLD_READINESS_TIMEOUT` before motion. The log says world observation never became
  ready. Its immediate source is attachment startup handshake in `launch/so101_gazebo.launch.py`:
  a timeout helper waits for `object_attached_event` attached, emits detach, then waits for
  `/so101/object_attached` detached. Inspect exact missing predicate rather than adding a stack.

## Next execution plan (do not stop between internal failures)

1. Read CP35I `cp35i.log`, `launch/so101_gazebo.launch.py:76-84`,
   `src/pick_place/world_readiness_gate.cpp`, and `gazebo_world_observer.cpp`. Determine the
   exact WorldReadinessGate predicate missing during a clean single-stack startup. Fix only startup
   ordering/observation plumbing, not motion safety/configuration. Add/adjust targeted test if
   source changes.
2. Build/source, run focused readiness + policy/calibration tests.
3. Exact-clean CP35I only; verify zero simulator processes/windows. Launch exactly one GUI stack
   with `source ~/gui-env.zsh`, unique safe `ROS_DOMAIN_ID <=232` and `GZ_PARTITION`; wait for
   one window/server/move_group, controllers, joints 1–6, attached-event/detached state, cup pose,
   and WorldReadinessGate continuous samples before state machine execute.
4. Maximize Gazebo using installed `tile_ai_station_guis.py --maximize gazebo`; capture Gazebo only
   with a persistent tmux-owned worker. Measure actual cadence. CUA screenshot calls took ~1.4 s;
   if user requests exact 1 Hz, use an efficient window-only host mechanism and prove timestamps.
5. Run the coherent `+1 mm` temporary motion/validation policy (regenerate it from the exact
   official calibrated policy if needed) with `stop_after=DESCEND`; gather controller q1 error,
   first wall_near contact, cup pre/post pose, penetration, and fresh frames. DESCEND requires:
   no early pad/wall contact, no cup drift, no PATH_TOLERANCE.
6. If GREEN, proceed automatically through CLOSE (q6 -0.040), attach, lift, move/place,
   descend-to-place, release/detach, retreat, and final stable cup pose. Do not claim success until
   Gazebo, MoveIt, controller, attachment and fresh visual evidence agree.
