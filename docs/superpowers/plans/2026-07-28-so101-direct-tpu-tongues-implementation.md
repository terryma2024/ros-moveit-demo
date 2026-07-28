# SO-101 Direct TPU Tongues Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the experimental stem-and-tongue pads with calibrated 5 x 12 x 27 mm direct TPU 95A tongues and safely execute the complete 20 g light-cup same-wall pick/place chain.

**Architecture:** The object YAML owns the rigid-primitive direct-tongue geometry and its mesh-derived q6 facts; motion YAML owns commands and waypoints; validation YAML owns all runtime gates. Xacro consumes the object YAML to place exactly two direct boxes, while the C++ policy loader, profile, reset path, observer, and contracts enforce one shared lower q6 floor. The Gazebo model remains a rigid Bullet Featherstone approximation: calculated geometry is not treated as Bullet-validated until staged GUI evidence completes.

**Tech Stack:** ROS 2 Jazzy, Gazebo Harmonic, gz-physics-bullet-featherstone-plugin, MoveIt 2, gz_ros2_control, C++17, yaml-cpp, xacro, GoogleTest, pytest, colcon, tmux, Codex CUA.

## Global Constraints

- Preserve every pre-existing staged, unstaged, and untracked change; do not reset, checkout, stash, clean, force, amend, or push.
- Simulation only; never connect to or command a real arm.
- Keep Bullet Featherstone, original visual STL, and existing cached moving-jaw/fixed-finger VHACD; do not modify an STL or regenerate VHACD at Gazebo startup.
- Direct tongues are removable link-local rigid box primitives with TPU 95A visual semantics. Do not claim soft-body deformation or model softness with penetration.
- Direct-tongue dimensions are 5 x 12 x 27 mm, each overlaps its owning original fingertip by 3 mm, and no mounting stem exists.
- Fixed tongue origin/rpy is `[-0.009099999852, 0, -0.114449432212]` / `[0, 0, 0]`; moving tongue origin/rpy is `[-0.019701707396, -0.089211614425, 0.018800334443]` / `[-1.5708, 0, -0.30]`.
- `q6_touch=-0.007113433021` is diagnostic only. The universal lower/home/fullclose/reset/recovery command floor is `0.002757025188 rad`, giving a 1.0 mm gap; never command touch.
- Grasp close is `0.004728114131 rad` with 1.2 mm tongue gap and 0.8 mm geometric interference against the 2 mm wall. Preopen is `0.465038 rad` with 44.514 mm calculated gap. Position tolerance is `0.001 rad`.
- The direct-tongue DESCEND z candidate is `0.219000431 m`; use fresh GUI evidence to calibrate x/y/z and the attachment-relative pose before freezing runtime YAML.
- Attachment remains fail closed: fixed-outside and moving-inside samples must both be on `wall_near`, inside the 8–35 mm below-rim / 20 mm bottom-clearance band, with correct opposing normals, no rim/bottom/opposite collision, and penetration <=0.8 mm.
- Friction begins at 1.2 only when a controlled Bullet A/B demonstrates it changes tangential slip. Do not emit stiffness or damping fields without equivalent runtime proof.
- GUI work stays in tmux `so101-moveit`; source `~/gui-env.zsh`, do not hard-code `DISPLAY`, inspect CUA state before visual interaction, and use `ai-station-capture.sh` for screenshots.

---

## Preflight: isolate execution without losing prerequisite dirty work

The current ai-station workspace is on `main` and contains prerequisite uncommitted
SO-101 work that cannot be reproduced in a clean worktree. Before Task 1, create a branch
in place while preserving the index and working tree exactly:

```bash
cd /data/work/ws_moveit
git status --short
git switch -c codex/direct-tpu-tongues
git rev-parse --short HEAD
git branch --show-current
tmux list-sessions
pgrep -af 'gz sim|move_group|rviz2|pick_place_state_machine'
```

Expected: branch is `codex/direct-tpu-tongues`; all pre-existing staged, unstaged, and
untracked entries remain byte-for-byte present; the active GUI stack and its owning tmux
session are recorded. Save this snapshot under `/tmp/so101-direct-tpu-<timestamp>/`.

Before every task commit, inspect `git diff`, `git diff --cached`, and `git status --short`.
Use `git add -p -- <task paths>` to stage only hunks introduced by that task. If a new hunk
cannot be separated from pre-existing work, leave it uncommitted and report the overlap;
never stage a whole dirty directory or the pre-existing `.idea/misc.xml` change.

## File Responsibility Map

| Area | Files | Responsibility after implementation |
| --- | --- | --- |
| Design and provenance | `docs/superpowers/specs/2026-07-28-so101-direct-tpu-tongues-design.md`, `docs/superpowers/plans/2026-07-28-so101-direct-tpu-tongues-implementation.md` | Frozen numeric design, implementation order, and acceptance evidence contract. |
| Typed configuration | `config/task_objects/light_plastic_cup.yaml`, `config/motion_policies/light_cup_wall_pick.yaml`, `config/validation_policies/light_cup_wall_pick.yaml`, `include/.../policy_config.hpp`, `src/pick_place/policy_config.cpp`, `test/pick_place/test_policy_config.cpp` | Strict no-stem schema, geometry literals, q6 commands, and validation tolerances. |
| Geometry calibration | `scripts/gripper_preopen_calc.py`, `test/test_gripper_preopen_calc.py`, `include/.../gripper_width_calibration_data.hpp` | Reproducible direct-tongue spans/gaps/origins and generated width calibration provenance. |
| Robot description | `urdf/so101_base.xacro`, `urdf/so101_ros2_control.xacro`, `config/so101.srdf`, `test/test_prepare_simulation_model.py`, `test/test_configuration_contract.py` | Exactly two direct rigid boxes, no stem, and one lower q6 bound in URDF/control/MoveIt named states. |
| Runtime q6 and reset/recovery | `include/.../so101_profile.hpp`, `src/pick_place/so101_profile.cpp`, `src/pick_place/pick_place_runtime.cpp`, `src/pick_place/so101_recovery_policy.cpp`, `src/nodes/reset_so101_world.cpp`, `src/pick_place/world_reset_coordinator.cpp`, related GTests | Policy-derived q6 values and lower-bound enforcement for runtime, reset, and recovery. |
| Motion/TCP/attachment | `src/pick_place/so101_fixed_motion_targets.cpp`, `test/pick_place/test_so101_fixed_motion_targets.cpp`, `config/*policy*.yaml`, `src/pick_place/moveit_joint_planning_boundary.cpp`, `src/pick_place/moveit_scene_adapter.cpp` | GUI-calibrated, YAML-owned pick waypoints and pinch-relative attachment pose. |
| Contact evidence | `src/pick_place/gazebo_world_observer.cpp`, `include/.../gazebo_world_observer.hpp`, `src/pick_place/so101_attachment_contracts.cpp`, `test/pick_place/test_so101_gazebo_attachment.cpp`, `test/pick_place/test_so101_attachment_contracts.cpp` | Direct-collision classification and bilateral same-wall fail-closed attachment checks. |
| Integration and visual proof | `launch/so101_gazebo.launch.py`, `launch/so101_moveit.launch.py`, `launch/so101_pick_place.launch.py`, `test/test_so101_launch_contract.py`, `test/test_so101_pick_place_world.py`, `test/headless/test_so101_world_reset_live.py` | Installed-config provenance, Bullet selection, full regression, staged GUI execution, and reset/recovery proof. |

### Task 1: Make direct-tongue configuration strict and stem-free

**Files:**
- Modify: `src/so101_gazebo_demo/config/task_objects/light_plastic_cup.yaml`
- Modify: `src/so101_gazebo_demo/config/motion_policies/light_cup_wall_pick.yaml`
- Modify: `src/so101_gazebo_demo/config/validation_policies/light_cup_wall_pick.yaml`
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/policy_config.hpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/policy_config.cpp`
- Test: `src/so101_gazebo_demo/test/pick_place/test_policy_config.cpp`

**Interfaces:**
- Produces `FingertipAdapterConfig { bool enabled; std::string material; double shore_hardness_a; std::string contact_model; double geometry_reference_q6; double direct_tongue_overlap_m; double touch_q6; double safe_lower_q6; double safe_gap_m; double grasp_gap_m; double friction_coefficient; AdapterPrimitiveConfig fixed_tongue; AdapterPrimitiveConfig moving_tongue; }`.
- Produces `MotionPolicyConfig::GripperActions { double preopen_q6; double grasp_close_q6; double release_q6; }` and `RuntimeValidationConfig` values of 0.001 rad for position and contact-stop tolerance.
- Rejects `fixed_stem`, `moving_stem`, `tongue_extension_m`, and `target_reference_gap_m` as `POLICY_UNKNOWN_FIELD`.

- [ ] **Step 1: Write failing parser tests.** Add assertions that a direct fixture loads only two primitives, has size `[0.005, 0.012, 0.027]`, overlap `0.003`, both exact origins/rpy, touch/safe/preopen/grasp values, and tolerance `0.001`. Add fixtures retaining either stem key and a grasp-close value below `safe_lower_q6`; expect `POLICY_UNKNOWN_FIELD` and `POLICY_INVALID_VALUE` respectively.
- [ ] **Step 2: Run RED.**
  ```bash
  cmake --build build/so101_gazebo_demo --target test_policy_config -j2
  build/so101_gazebo_demo/test_policy_config --gtest_filter='PolicyConfig.*DirectTongue*'
  ```
  Expected: failure because the current schema still requires stem fields and accepts old actions.
- [ ] **Step 3: Implement the minimal typed schema.** Remove stem and extension fields from `FingertipAdapterConfig`; parse the exact direct values, finite positive dimensions, `direct_tongue_overlap_m==0.003`, and command ordering `safe_lower_q6 <= grasp_close_q6 < preopen_q6 <= release_q6`. Write the specified values into object/motion/validation YAML; set close-bearing state commands to `0.004728114131`, preopen-bearing commands to `0.465038`, and position/contact-stop tolerances to `0.001`.
- [ ] **Step 4: Run GREEN.**
  ```bash
  cmake --build build/so101_gazebo_demo --target test_policy_config -j2
  build/so101_gazebo_demo/test_policy_config
  ```
  Expected: all policy-config cases pass, including rejection of either removed stem key.
- [ ] **Step 5: Commit.**
  ```bash
  git add src/so101_gazebo_demo/config/task_objects/light_plastic_cup.yaml src/so101_gazebo_demo/config/motion_policies/light_cup_wall_pick.yaml src/so101_gazebo_demo/config/validation_policies/light_cup_wall_pick.yaml src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/policy_config.hpp src/so101_gazebo_demo/src/pick_place/policy_config.cpp src/so101_gazebo_demo/test/pick_place/test_policy_config.cpp
  git commit -m "feat: configure direct TPU tongues"
  ```

### Task 2: Regenerate and lock direct-tongue geometry provenance

**Files:**
- Modify: `src/so101_gazebo_demo/scripts/gripper_preopen_calc.py`
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/gripper_width_calibration_data.hpp`
- Test: `src/so101_gazebo_demo/test/test_gripper_preopen_calc.py`

**Interfaces:**
- Produces `calculate_direct_tongue_placements(...) -> DirectTonguePlacements` containing exactly the two origins/rpy, 5/12/27 mm sizes, 3 mm overlap, `touch_q6`, safe/grasp/preopen gaps, and a source-model fingerprint.
- Produces `direct_tongue_opening_axis_gap(placements, q6) -> float`.

- [ ] **Step 1: Write failing geometry tests.** Assert the direct placements equal every frozen literal; assert `gap(0.002757025188)==0.001`, `gap(0.004728114131)==0.0012`, `gap(0.465038)==0.044514`, and that the diagnostic touch angle is never accepted as a command. Assert two direct boxes neither collide with each other nor illegally cross-collide with the opposite original finger at preopen, safe, and grasp positions.
- [ ] **Step 2: Run RED.**
  ```bash
  python3 -m pytest -q src/so101_gazebo_demo/test/test_gripper_preopen_calc.py -k 'direct_tongue or safe_gap or grasp_gap'
  ```
  Expected: failure because the calculator still derives the 19.671 mm stem assembly.
- [ ] **Step 3: Implement direct calculation only.** Replace the stem-placement result with link-local fixed/moving direct-box placement, preserve mesh/URDF hash inputs, and regenerate the calibration header through the existing generator path. Do not alter original STL or cached VHACD files.
- [ ] **Step 4: Run GREEN and source-provenance check.**
  ```bash
  python3 -m pytest -q src/so101_gazebo_demo/test/test_gripper_preopen_calc.py
  python3 src/so101_gazebo_demo/scripts/gripper_preopen_calc.py --mesh-dir src/so101_gazebo_demo/meshes/so101 --verify-generated-header src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/gripper_width_calibration_data.hpp
  ```
  Expected: all geometry tests pass and header verification reports matching source fingerprint.
- [ ] **Step 5: Commit.**
  ```bash
  git add src/so101_gazebo_demo/scripts/gripper_preopen_calc.py src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/gripper_width_calibration_data.hpp src/so101_gazebo_demo/test/test_gripper_preopen_calc.py
  git commit -m "feat: calibrate direct TPU tongue geometry"
  ```

### Task 3: Render exactly two direct rigid primitives and enforce the shared lower q6 limit

**Files:**
- Modify: `src/so101_gazebo_demo/urdf/so101_base.xacro`
- Modify: `src/so101_gazebo_demo/urdf/so101_ros2_control.xacro`
- Modify: `src/so101_gazebo_demo/config/so101.srdf`
- Test: `src/so101_gazebo_demo/test/test_prepare_simulation_model.py`
- Test: `src/so101_gazebo_demo/test/test_configuration_contract.py`

**Interfaces:**
- `configured_tpu_adapter` receives only `fixed_tongue` or `moving_tongue` and emits `fixed_tpu_direct_tongue_collision` or `moving_tpu_direct_tongue_collision` on the existing `gripper`/`jaw` links.
- Joint `6` lower bound is exactly `0.002757025188` in URDF and ros2_control; SRDF `home` and `fullclose` both use the same value.

- [ ] **Step 1: Write failing description tests.** Parse generated robot description and require exactly two direct-tongue visual/collision boxes with 5/12/27 mm size and exact transforms; reject any collision whose name contains `stem`. Assert URDF and ros2_control minimums equal `0.002757025188`, and SRDF named `home`/`fullclose` values equal it.
- [ ] **Step 2: Run RED.**
  ```bash
  python3 -m pytest -q src/so101_gazebo_demo/test/test_prepare_simulation_model.py src/so101_gazebo_demo/test/test_configuration_contract.py -k 'direct_tongue or lower_limit or fullclose'
  ```
  Expected: failure because current xacro emits four stem/tongue collisions and permits negative q6.
- [ ] **Step 3: Implement the description change.** Keep the existing distinct TPU visual material and rigid boxes; remove stem macro calls and schema dependencies. Set the three independent joint-limit sources and SRDF named states to the same literal floor. Preserve existing original-collision and VHACD declarations.
- [ ] **Step 4: Run GREEN.**
  ```bash
  python3 -m pytest -q src/so101_gazebo_demo/test/test_prepare_simulation_model.py src/so101_gazebo_demo/test/test_configuration_contract.py
  ```
  Expected: generated Gazebo/MoveIt descriptions contain exactly two direct-tongue collisions and all lower-limit assertions pass.
- [ ] **Step 5: Commit.**
  ```bash
  git add src/so101_gazebo_demo/urdf/so101_base.xacro src/so101_gazebo_demo/urdf/so101_ros2_control.xacro src/so101_gazebo_demo/config/so101.srdf src/so101_gazebo_demo/test/test_prepare_simulation_model.py src/so101_gazebo_demo/test/test_configuration_contract.py
  git commit -m "feat: enforce direct tongue joint safety floor"
  ```

### Task 4: Carry policy q6 facts through profile, reset, and recovery

**Files:**
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_profile.hpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/so101_profile.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/so101_recovery_policy.cpp`
- Modify: `src/so101_gazebo_demo/src/nodes/reset_so101_world.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/world_reset_coordinator.cpp`
- Test: `src/so101_gazebo_demo/test/pick_place/test_so101_gripper_adapter.cpp`
- Test: `src/so101_gazebo_demo/test/pick_place/test_so101_recovery_policy.cpp`
- Test: `src/so101_gazebo_demo/test/pick_place/test_so101_world_reset.cpp`

**Interfaces:**
- `SO101Profile::configured(...)` exposes `q6_safe_lower`, `q6_grasp_close`, `q6_preopen`, `q6_full_open`, and `q6_tolerance` from loaded YAML.
- `WorldResetConfig::q6_home_position` and every recovery close-bearing command are required to be `>= profile.q6_safe_lower`.

- [ ] **Step 1: Write failing profile/reset/recovery tests.** Load the direct YAML and assert safe lower `0.002757025188`, grasp `0.004728114131`, preopen `0.465038`, release `1.70`, and tolerance `0.001`. Assert reset commands home at the safe floor; assert every recovery route rejects a command below it and preserves the original failure evidence.
- [ ] **Step 2: Run RED.**
  ```bash
  cmake --build build/so101_gazebo_demo --target test_so101_gripper_adapter test_so101_recovery_policy test_so101_world_reset -j2
  ctest --test-dir build/so101_gazebo_demo -R 'test_so101_gripper_adapter|test_so101_recovery_policy|test_so101_world_reset' --output-on-failure
  ```
  Expected: failures show canonical home remains zero and recovery/reset retain old contact targets.
- [ ] **Step 3: Implement one lower-bound path.** Add `q6_safe_lower` to the configured profile from object YAML, map motion `grasp_close_q6` to contact state, and validate every reset/recovery/home request before emitting a trajectory. Report `Q6_BELOW_SAFE_LOWER_LIMIT` with actual/required metrics when a request violates the floor.
- [ ] **Step 4: Run GREEN.** Repeat the RED command. Expected: all three test targets pass; no reset/recovery path can emit a q6 below the shared floor.
- [ ] **Step 5: Commit.**
  ```bash
  git add src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_profile.hpp src/so101_gazebo_demo/src/pick_place/so101_profile.cpp src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp src/so101_gazebo_demo/src/pick_place/so101_recovery_policy.cpp src/so101_gazebo_demo/src/nodes/reset_so101_world.cpp src/so101_gazebo_demo/src/pick_place/world_reset_coordinator.cpp src/so101_gazebo_demo/test/pick_place/test_so101_gripper_adapter.cpp src/so101_gazebo_demo/test/pick_place/test_so101_recovery_policy.cpp src/so101_gazebo_demo/test/pick_place/test_so101_world_reset.cpp
  git commit -m "feat: unify direct tongue q6 safety limits"
  ```

### Task 5: Recalibrate TCP, motion YAML, and attachment pose from direct geometry

**Files:**
- Modify: `src/so101_gazebo_demo/config/motion_policies/light_cup_wall_pick.yaml`
- Modify: `src/so101_gazebo_demo/config/validation_policies/light_cup_wall_pick.yaml`
- Modify: `src/so101_gazebo_demo/config/task_objects/light_plastic_cup.yaml`
- Modify: `src/so101_gazebo_demo/src/pick_place/so101_fixed_motion_targets.cpp`
- Test: `src/so101_gazebo_demo/test/pick_place/test_so101_fixed_motion_targets.cpp`
- Test: `src/so101_gazebo_demo/test/pick_place/test_so101_motion_validation.cpp`

**Interfaces:**
- `SO101ConfiguredMotionTargetPolicy::spec(State)` continues to consume all joint waypoints and q6 commands from YAML.
- `TaskObjectGraspFrameConfig::attachment_relative_pose` is a measured direct-tongue pinch transform, not a one-sided cup pose.

- [ ] **Step 1: Write failing kinematic tests.** Require DESCEND candidate z `0.219000431`, preopen `0.465038`, grasp states `0.004728114131`, and `0.001` q6 endpoint tolerance. Add a test fixture that replaces any motion YAML q6/waypoint and proves `spec()` changes without rebuilding C++. Add FK assertions that the GUI-calibrated waypoint ends at the measured direct-tongue TCP x/y/z with the retained downward approach axis.
- [ ] **Step 2: Run RED.**
  ```bash
  cmake --build build/so101_gazebo_demo --target test_so101_fixed_motion_targets test_so101_motion_validation -j2
  ctest --test-dir build/so101_gazebo_demo -R 'test_so101_fixed_motion_targets|test_so101_motion_validation' --output-on-failure
  ```
  Expected: failure because existing targets were calibrated for long stem pads and z=0.235.
- [ ] **Step 3: Build, prove provenance, and restart the owned GUI stack before calibration.** Run:
  ```bash
  cd /data/work/ws_moveit
  source /opt/ros/jazzy/setup.zsh
  colcon build --packages-select so101_gazebo_demo --symlink-install
  source install/setup.zsh
  ros2 pkg prefix so101_gazebo_demo
  stat install/so101_gazebo_demo/share/so101_gazebo_demo/urdf/so101_base.xacro
  ```
  Expected: the prefix is `/data/work/ws_moveit/install/so101_gazebo_demo` and the installed
  xacro timestamp is newer than the Task 3 source change. In tmux `so101-moveit`, source
  `~/gui-env.zsh`, stop only the recorded Gazebo/MoveIt/RViz processes owned by that
  session, then relaunch the stack so the new robot description is loaded. Confirm there is
  exactly one `gz sim`, one `/move_group`, and one RViz. Run `ai-station-capture.sh` and
  inspect a fresh baseline screenshot before commanding motion.
- [ ] **Step 4: Calibrate in GUI before freezing values.** Verify CUA session state; run a clean task reset; use the calculated z as the only initial depth change and calibrate x/y under the preserved wrist orientation. Record the measured TCP, all joint waypoints, and cup-to-gripper pinch transform in `/tmp/so101-direct-tpu-<timestamp>/tcp-calibration.yaml`.
- [ ] **Step 5: Implement YAML literals and attachment transform.** Copy the measured waypoint ladder, validation endpoints, and attachment-relative pose into the three YAML files. Preserve all place/recovery semantics, update only values derived by the direct-tongue calibration, and lock them in fixed-motion tests.
- [ ] **Step 6: Run GREEN.** Repeat the RED command. Expected: FK, YAML hot-restart fixture, axis, joint jump, and temporal-contact tests pass.
- [ ] **Step 7: Commit.**
  ```bash
  git add src/so101_gazebo_demo/config/motion_policies/light_cup_wall_pick.yaml src/so101_gazebo_demo/config/validation_policies/light_cup_wall_pick.yaml src/so101_gazebo_demo/config/task_objects/light_plastic_cup.yaml src/so101_gazebo_demo/src/pick_place/so101_fixed_motion_targets.cpp src/so101_gazebo_demo/test/pick_place/test_so101_fixed_motion_targets.cpp src/so101_gazebo_demo/test/pick_place/test_so101_motion_validation.cpp
  git commit -m "feat: calibrate direct tongue cup motion"
  ```

### Task 6: Classify direct contacts and preserve the bilateral attachment gate

**Files:**
- Modify: `src/so101_gazebo_demo/src/pick_place/gazebo_world_observer.cpp`
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/gazebo_world_observer.hpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/so101_attachment_contracts.cpp`
- Test: `src/so101_gazebo_demo/test/pick_place/test_so101_gazebo_attachment.cpp`
- Test: `src/so101_gazebo_demo/test/pick_place/test_so101_attachment_contracts.cpp`

**Interfaces:**
- Observer recognizes only `fixed_tpu_direct_tongue_collision` as direct fixed evidence and only `moving_tpu_direct_tongue_collision` as direct moving evidence; no absent stem name may qualify.
- `requireSameWallSurfaceContact(...)` requires independent fixed/moving samples on `wall_near`, opposing normal alignment, YAML vertical/bottom limits, and each sample depth <= `0.0008`.

- [ ] **Step 1: Write failing contact tests.** Feed synthetic contacts for both direct collision names and assert separate samples, names, height bands, normals, and maximum depth. Add rejected cases for fixed-only, moving-only, stem-like name, rim, bottom, opposite wall, wrong normal, `0.000800001` depth, and a one-sided attachment pose.
- [ ] **Step 2: Run RED.**
  ```bash
  cmake --build build/so101_gazebo_demo --target test_so101_gazebo_attachment test_so101_attachment_contracts -j2
  ctest --test-dir build/so101_gazebo_demo -R 'test_so101_gazebo_attachment|test_so101_attachment_contracts' --output-on-failure
  ```
  Expected: failures because the observer still recognizes old `*_adapter_contact_collision` names and supports the stem layout.
- [ ] **Step 3: Implement narrow collision-name mapping.** Replace old adapter-name matching with exact direct-tongue matching, retain original convex contacts as supplemental evidence only, and leave sample-level YAML validation fail closed. Emit metrics for fixed/moving collision names, contact height min/max, max depth, q6 target/error, and controller velocity.
- [ ] **Step 4: Run GREEN.** Repeat the RED command. Expected: every valid bilateral direct contact passes and every invalid semantic/depth case fails under its explicit code.
- [ ] **Step 5: Commit.**
  ```bash
  git add src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/gazebo_world_observer.hpp src/so101_gazebo_demo/src/pick_place/gazebo_world_observer.cpp src/so101_gazebo_demo/src/pick_place/so101_attachment_contracts.cpp src/so101_gazebo_demo/test/pick_place/test_so101_gazebo_attachment.cpp src/so101_gazebo_demo/test/pick_place/test_so101_attachment_contracts.cpp
  git commit -m "feat: gate attachment on direct tongue contacts"
  ```

### Task 7: Build installed artifacts and prove launch/reset provenance

**Files:**
- Modify: `src/so101_gazebo_demo/launch/so101_gazebo.launch.py`
- Modify: `src/so101_gazebo_demo/launch/so101_moveit.launch.py`
- Modify: `src/so101_gazebo_demo/launch/so101_pick_place.launch.py`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`
- Test: `src/so101_gazebo_demo/test/test_so101_launch_contract.py`
- Test: `src/so101_gazebo_demo/test/headless/test_so101_world_reset_live.py`

**Interfaces:**
- Launches pass the installed object/motion/validation files to Gazebo, MoveIt, and `pick_place_state_machine`; generated robot descriptions include no stem collision and the Bullet Featherstone engine.
- `reset_so101_world` proves q6 home is at or above `0.002757025188` and stationary inside 0.001 rad.

- [ ] **Step 1: Write failing launch/reset tests.** Assert launch preparation rejects stem collision output, passes the direct object config to both robot descriptions, selects `gz-physics-bullet-featherstone-plugin`, and reports q6 home/floor/tolerance facts. Extend live reset checks to require q6 `>=0.002757025188` and absolute error `<=0.001`.
- [ ] **Step 2: Run RED.**
  ```bash
  python3 -m pytest -q src/so101_gazebo_demo/test/test_so101_launch_contract.py
  ctest --test-dir build/so101_gazebo_demo -R test_so101_reset_cli --output-on-failure
  ```
  Expected: launch contract still contains stem names or lacks direct lower-limit provenance.
- [ ] **Step 3: Implement installed-artifact wiring.** Keep all existing xacro object-config mappings, update expected collision/provenance checks to direct tongues, and register any new package test target in CMake. Do not add a runtime VHACD step.
- [ ] **Step 4: Run GREEN plus package build.**
  ```bash
  source /opt/ros/jazzy/setup.zsh
  colcon build --packages-select so101_gazebo_demo --symlink-install
  source install/setup.zsh
  python3 -m pytest -q src/so101_gazebo_demo/test/test_so101_launch_contract.py
  ctest --test-dir build/so101_gazebo_demo -R 'test_so101_reset_cli|test_so101_world_reset' --output-on-failure
  ```
  Expected: build succeeds; installed paths, direct collisions, Bullet engine, and reset contracts pass.
- [ ] **Step 5: Commit.**
  ```bash
  git add src/so101_gazebo_demo/launch/so101_gazebo.launch.py src/so101_gazebo_demo/launch/so101_moveit.launch.py src/so101_gazebo_demo/launch/so101_pick_place.launch.py src/so101_gazebo_demo/CMakeLists.txt src/so101_gazebo_demo/test/test_so101_launch_contract.py src/so101_gazebo_demo/test/headless/test_so101_world_reset_live.py
  git commit -m "test: verify direct tongue launch provenance"
  ```

### Task 8: Perform staged Bullet GUI acceptance and record the complete chain

**Files:**
- Modify: `src/so101_gazebo_demo/config/motion_policies/light_cup_wall_pick.yaml` only if Task 5 evidence requires a measured literal correction
- Modify: `src/so101_gazebo_demo/config/validation_policies/light_cup_wall_pick.yaml` only if Task 5 evidence requires a measured literal correction
- Modify: `src/so101_gazebo_demo/config/task_objects/light_plastic_cup.yaml` only if Task 5 evidence requires a measured attachment transform correction
- Test: `src/so101_gazebo_demo/test/test_so101_pick_place_world.py`
- Test: `src/so101_gazebo_demo/test/test_benchmark_gazebo_startup.py`

**Interfaces:**
- `pick_place_state_machine --mode execute --stop-after STATE` writes resumable checkpoints bound to the three policy digests and session id.
- Acceptance evidence directory contains raw contacts, joint state, Gazebo pose, MoveIt scene state, RTF, controller error, action log, and CUA screenshot for the same session.

- [ ] **Step 1: Add automated acceptance guards first.** Add assertions that configured q6 never drops below the safe floor, successful attachment requires both direct collision names and max depth <=0.0008, and the world test reports Bullet Featherstone, no mesh/resource error, and RTF >=0.85. Add a benchmark assertion that startup retains cached collision provenance rather than launching VHACD.
- [ ] **Step 2: Run RED.**
  ```bash
  python3 -m pytest -q src/so101_gazebo_demo/test/test_so101_pick_place_world.py src/so101_gazebo_demo/test/test_benchmark_gazebo_startup.py -k 'direct or bullet or rtf or penetration'
  ```
  Expected: failure until direct collision names and current runtime evidence assertions are implemented.
- [ ] **Step 3: Run a clean staged GUI session.** In tmux `so101-moveit`, source `~/gui-env.zsh`, inspect CUA status, and create `/tmp/so101-direct-tpu-<timestamp>`. Use `reset_so101_world`, then execute and inspect one boundary at a time: `MOVE_ABOVE_OBJECT`, `DESCEND`, `CLOSE_GRIPPER`, `ATTACH_GAZEBO`, `ATTACH_MOVEIT`, `LIFT`, `MOVE_ABOVE_PLACE`, `DESCEND_TO_PLACE`, `DETACH_GAZEBO`, `DETACH_MOVEIT`, `SYNC_WORLD_OBJECT`, and `RETREAT`. At CLOSE and ATTACH save raw contact names, local heights/normals, depth, q6 actual/target/error/velocity, RTF, and attachment states. If a stage fails, stop the chain, preserve the first failure and recovery trace, and do not report a later recovery observation as the root cause.
- [ ] **Step 4: Validate Bullet friction A/B and complete the successful chain.** Run exactly two otherwise identical trials with isotropic `mu=0.2` and `mu=1.2`. For both trials keep the same generated robot/cup geometry, 20 g mass, q6 command, arm pose, Bullet Featherstone engine, solver settings, initial cup pose, and 5.0 s measurement window. Record the cup pose relative to the two tongue frames at window start/end and compute tangential displacement in metres. Accept the friction field as effective only if `mu=1.2` produces a smaller repeatable displacement than `mu=0.2`; otherwise omit the unproven friction override and report the A/B as inconclusive. Save both launch commands, timestamps, raw poses, and computed displacement in the evidence directory. Then verify lift clears the table, MoveIt/Gazebo attachment states agree, detach restores collision/world membership, the cup is stable at place pose, final state is `DONE`, and recovery after one injected attach failure safely opens/detaches/retreats without below-floor q6.
- [ ] **Step 5: Capture and review visual evidence.** Use `ai-station-capture.sh` after checking CUA state, inspect the fresh Gazebo/RViz screenshot through CUA, and save the image path with the action/session logs. Require direct tongues visibly distinct from the original gripper, cup held at the same near wall during lift/carry, and cup released onto the table.
- [ ] **Step 6: Run GREEN regression and benchmark.**
  ```bash
  source /opt/ros/jazzy/setup.zsh
  source install/setup.zsh
  python3 -m pytest -q src/so101_gazebo_demo/test/test_so101_pick_place_world.py src/so101_gazebo_demo/test/test_benchmark_gazebo_startup.py
  ctest --test-dir build/so101_gazebo_demo --output-on-failure
  ```
  Expected: package regression passes; fresh GUI evidence shows bilateral same-wall contact, depth <=0.8 mm, RTF >=0.85, attach/lift/place/detach/DONE, and verified recovery behavior.
- [ ] **Step 7: Commit only source/test changes from this task.**
  ```bash
  git add src/so101_gazebo_demo/config/task_objects/light_plastic_cup.yaml src/so101_gazebo_demo/config/motion_policies/light_cup_wall_pick.yaml src/so101_gazebo_demo/config/validation_policies/light_cup_wall_pick.yaml src/so101_gazebo_demo/test/test_so101_pick_place_world.py src/so101_gazebo_demo/test/test_benchmark_gazebo_startup.py
  git commit -m "test: validate direct tongue pick place"
  ```

## Plan Self-Review

- Spec coverage: Tasks 1–2 cover exact no-stem geometry and calculated gaps; Task 3 covers URDF/ros2_control/MoveIt lower-limit unity; Task 4 covers runtime/reset/recovery; Task 5 covers TCP and attachment calibration; Task 6 covers bilateral contact semantics; Task 7 covers installed build/source provenance; Task 8 covers Bullet A/B, staged GUI, full chain, penetration, RTF, screenshot, `DONE`, and failure recovery.
- Placeholder scan: this plan contains no unresolved task marker and gives a concrete command, expected result, and commit boundary for every task.
- Type consistency: `FingertipAdapterConfig`, `MotionPolicyConfig::GripperActions`, `SO101Profile`, `SO101ConfiguredMotionTargetPolicy::spec`, direct collision names, and the shared q6 floor use the same names and literals throughout.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-28-so101-direct-tpu-tongues-implementation.md`. The requested next action is to pause after the plan-only commit; do not start Task 1 in this session.
