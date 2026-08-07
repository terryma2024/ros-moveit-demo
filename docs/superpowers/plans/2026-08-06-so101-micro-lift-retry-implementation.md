# SO-101 MICRO_LIFT Regrasp Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bounded SO-101-only physical-grasp retry loop that reuses the current close target when contact remains, tightens by exactly 1.0 mrad when contact is absent, descends to the saved pre-lift TCP Z, and stops after five total MICRO_LIFT attempts.

**Architecture:** Keep the common workflow and Panda unchanged. A pure SO-101 retry policy decides whether and how q6 changes; a robot-local coordinator executes PREOPEN, collision-aware micro-descend, reclose, stable evidence capture, and the existing 2 mm MICRO_LIFT. Extend the existing SO-101 physical-evidence sidecar with attempt/phase data so a process interruption fails closed without changing the common checkpoint schema.

**Tech Stack:** C++17, ROS 2 Jazzy, MoveIt 2, Gazebo Harmonic, nlohmann JSON, ament/colcon, GoogleTest, Python 3 headless acceptance helpers, tmux-held GUI stack.

## Global Constraints

- Work only in `/data/work/ws_moveit/.worktrees/refactor-optimization-r3` on `codex/refactor-optimization-r3`; execute directly on `AI-STATION-001` and never SSH from the remote Codex back into itself.
- Preserve every pre-existing dirty file and untracked file; stage only the exact files named by each task. Never reset, stash, clean, merge, push, or modify the root checkout.
- Never operate `codex-cua`; preserve other worktrees and the sampler clang-tidy process.
- Use only the R3 worktree's `build/` and `install/`; never source `/data/work/ws_moveit/install`.
- Keep the nominal `q6_contact`, current fixed-finger geometry, friction, 2 mm MICRO_LIFT, validator thresholds, attachment policy, and existing 6.0 mrad transient seating action unchanged.
- Count the initial probe as attempt 1; allow at most four retry sequences and five total lifts.
- On contact present, keep `current_reclose_target_q6` unchanged. On contact absent, subtract exactly `0.001` rad, capped at `q6_contact - 0.004`, `q6_contact - q6_regrasp_squeeze_offset`, and `q6_safe_lower`.
- The transient seating command remains `max(q6_safe_lower, q6_contact - q6_regrasp_squeeze_offset)` regardless of the dynamic reclose target and remains commanded through MICRO_LIFT; the 1.0 mrad retry adjustment is never added to this preload.
- Do not retry planning/execution/observation/provenance/attachment failures, non-positive TCP lift, excessive XY slip, or excessive orientation change.
- Preserve the last real physical validator failure at attempt 5; add retry metrics without replacing its code or message.
- No implementation task is complete without its RED observation, GREEN result, scoped diff review, and scoped commit.

---

## File structure

### New files

- `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/physical_grasp_retry.hpp` — pure retry configuration, progress, decision, and coordinator public API.
- `src/so101_gazebo_demo/src/pick_place/physical_grasp_retry.cpp` — pure eligibility/target calculation and bounded retry orchestration.
- `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/physical_grasp_stabilizer.hpp` — reusable before/after stable-window API extracted from the runtime file.
- `src/so101_gazebo_demo/src/pick_place/physical_grasp_stabilizer.cpp` — current bilateral stabilization and evidence capture implementation.
- `src/so101_gazebo_demo/test/pick_place/test_physical_grasp_retry.cpp` — deterministic branch, sequence, exhaustion, cancellation, and failure-provenance tests.
- `src/so101_gazebo_demo/test/headless/so101_micro_lift_retry_fixture.py` — non-installed live fault fixture for controlled contact-present/contact-missing probes and evidence assertions.

### Modified files

- `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/physical_grasp_evidence_store.hpp`
- `src/so101_gazebo_demo/src/pick_place/physical_grasp_evidence_store.cpp`
- `src/so101_gazebo_demo/test/pick_place/test_physical_grasp_evidence_store.cpp`
- `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_joint_motion_adapter.hpp`
- `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/moveit_joint_planning_boundary.hpp`
- `src/so101_gazebo_demo/src/pick_place/moveit_joint_planning_boundary.cpp`
- `src/so101_gazebo_demo/test/pick_place/test_request_scoped_goal_cancellation.cpp`
- `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_profile.hpp`
- `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/pick_place_runtime.hpp`
- `src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp`
- `src/so101_gazebo_demo/test/pick_place/test_so101_pick_place_runtime.cpp`
- `src/so101_gazebo_demo/CMakeLists.txt`
- `src/so101_gazebo_demo/README.md`
- `docs/pick-place-architecture.md`
- `docs/pick-place-launch-parameters.md`

---

### Task 0: Preserve and commit the inherited R3 friction-grasp baseline

**Files:**
- Review and, only after the gate below passes, commit the inherited modifications in:
  - `src/so101_gazebo_demo/config/kinematics.yaml`
  - `src/so101_gazebo_demo/config/motion_policies/light_cup_wall_pick.yaml`
  - `src/so101_gazebo_demo/config/so101.srdf`
  - `src/so101_gazebo_demo/config/task_objects/light_plastic_cup.yaml`
  - `src/so101_gazebo_demo/config/validation_policies/light_cup_wall_pick.yaml`
  - `src/so101_gazebo_demo/config/ompl_planning.yaml`
  - `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/fingertip_pad_gap_calibration_data.hpp`
  - `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/moveit_joint_planning_boundary.hpp`
  - `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/policy_config.hpp`
  - `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_profile.hpp`
  - `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/world_reset_coordinator.hpp`
  - `src/so101_gazebo_demo/launch/so101_move_group_headless.launch.py`
  - `src/so101_gazebo_demo/launch/so101_moveit.launch.py`
  - `src/so101_gazebo_demo/scripts/prepare_simulation_model.py`
  - `src/so101_gazebo_demo/src/pick_place/moveit_joint_planning_boundary.cpp`
  - `src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp`
  - `src/so101_gazebo_demo/src/pick_place/policy_config.cpp`
  - `src/so101_gazebo_demo/src/pick_place/so101_attachment_contracts.cpp`
  - `src/so101_gazebo_demo/src/pick_place/so101_resume_validation_policy.cpp`
  - `src/so101_gazebo_demo/test/pick_place/test_checkpoint.cpp`
  - `src/so101_gazebo_demo/test/pick_place/test_policy_config.cpp`
  - `src/so101_gazebo_demo/test/pick_place/test_request_scoped_goal_cancellation.cpp`
  - `src/so101_gazebo_demo/test/pick_place/test_so101_attachment_contracts.cpp`
  - `src/so101_gazebo_demo/test/pick_place/test_so101_fixed_motion_targets.cpp`
  - `src/so101_gazebo_demo/test/pick_place/test_so101_gripper_adapter.cpp`
  - `src/so101_gazebo_demo/test/pick_place/test_so101_pick_place_runtime.cpp`
  - `src/so101_gazebo_demo/test/pick_place/test_so101_world_reset.cpp`
  - `src/so101_gazebo_demo/test/test_configuration_contract.py`
  - `src/so101_gazebo_demo/test/test_fingertip_pad_geometry.py`
  - `src/so101_gazebo_demo/test/test_prepare_simulation_model.py`
  - `src/so101_gazebo_demo/test/test_so101_launch_contract.py`
  - `src/so101_gazebo_demo/worlds/so101_pick_place.sdf`
- Preserve but do not commit: `symlink_install_manifest.txt`.

**Interfaces:**
- Produces: a reviewed, test-green commit representing the exact inherited friction/contact baseline on which retry work is built.
- Consumes: the existing uncommitted R3 diff and evidence under `/tmp/so101-debug-friction-takeover-20260806-KXzI2J`.

- [ ] **Step 1: Capture the inherited state before changing it**

Run:

```bash
cd /data/work/ws_moveit/.worktrees/refactor-optimization-r3
EVIDENCE_DIR=$(mktemp -d /tmp/so101-r3-inherited-baseline-20260806-XXXXXX)
git status --short --branch > "$EVIDENCE_DIR/git-status-before.txt"
git diff --binary > "$EVIDENCE_DIR/inherited-worktree.patch"
git diff --stat > "$EVIDENCE_DIR/inherited-diff-stat.txt"
git log --oneline -20 > "$EVIDENCE_DIR/git-log-before.txt"
sha256sum "$EVIDENCE_DIR/inherited-worktree.patch" > "$EVIDENCE_DIR/inherited-worktree.patch.sha256"
cp -- symlink_install_manifest.txt "$EVIDENCE_DIR/symlink_install_manifest.txt"
```

Expected: the patch contains the 31 tracked SO-101 files listed above; `ompl_planning.yaml` and `symlink_install_manifest.txt` are recorded separately because untracked files are absent from `git diff`.

- [ ] **Step 2: Review the inherited diff against the approved R3 boundary**

Verify all changed production behavior belongs to the current SO-101 contact/geometry/planning work, Panda/common are absent, `q6_regrasp_squeeze_offset` is exactly `0.0060`, and no temporary 0.0054 experiment remains. Verify `ompl_planning.yaml` is referenced by the SO-101 launch/config tests before including it. Stop and report exact paths/hunks if any change is unrelated or cannot be explained by its paired test.

- [ ] **Step 3: Rebuild the inherited source and run its current tests**

Run:

```bash
cd /data/work/ws_moveit/.worktrees/refactor-optimization-r3
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-up-to pick_place_common panda_gazebo_demo so101_gazebo_demo --cmake-args -DBUILD_TESTING=ON
source install/setup.bash
colcon test --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --event-handlers console_direct+
colcon test-result --test-result-base build --verbose
```

Expected: zero failures/errors and installed `SO101Profile::q6_regrasp_squeeze_offset == 0.0060`. This rebuild also removes the stale 0.0054 binary from the previous rejected experiment.

- [ ] **Step 4: Reconfirm the inherited runtime baseline on the one owned stack**

Audit process ownership first, reuse the existing `r3-friction-*` stack, and run one fresh canonical-reset SO-101 pick. Save TCP/cup/contact/q6 streams and a fresh Gazebo screenshot. Expected: the fixed 6.0 mrad preload is commanded and held through MICRO_LIFT; record success or the known “TCP lifted, cup did not” physical failure without changing any parameter.

- [ ] **Step 5: Commit only the reviewed inherited baseline**

Stage the exact 32 intended SO-101 paths listed in this task, including the referenced `ompl_planning.yaml`, but excluding `symlink_install_manifest.txt`. Run `git diff --cached --check`, inspect `git diff --cached --stat`, and commit:

```bash
git add -- \
  src/so101_gazebo_demo/config/kinematics.yaml \
  src/so101_gazebo_demo/config/motion_policies/light_cup_wall_pick.yaml \
  src/so101_gazebo_demo/config/so101.srdf \
  src/so101_gazebo_demo/config/task_objects/light_plastic_cup.yaml \
  src/so101_gazebo_demo/config/validation_policies/light_cup_wall_pick.yaml \
  src/so101_gazebo_demo/config/ompl_planning.yaml \
  src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/fingertip_pad_gap_calibration_data.hpp \
  src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/moveit_joint_planning_boundary.hpp \
  src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/policy_config.hpp \
  src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_profile.hpp \
  src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/world_reset_coordinator.hpp \
  src/so101_gazebo_demo/launch/so101_move_group_headless.launch.py \
  src/so101_gazebo_demo/launch/so101_moveit.launch.py \
  src/so101_gazebo_demo/scripts/prepare_simulation_model.py \
  src/so101_gazebo_demo/src/pick_place/moveit_joint_planning_boundary.cpp \
  src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp \
  src/so101_gazebo_demo/src/pick_place/policy_config.cpp \
  src/so101_gazebo_demo/src/pick_place/so101_attachment_contracts.cpp \
  src/so101_gazebo_demo/src/pick_place/so101_resume_validation_policy.cpp \
  src/so101_gazebo_demo/test/pick_place/test_checkpoint.cpp \
  src/so101_gazebo_demo/test/pick_place/test_policy_config.cpp \
  src/so101_gazebo_demo/test/pick_place/test_request_scoped_goal_cancellation.cpp \
  src/so101_gazebo_demo/test/pick_place/test_so101_attachment_contracts.cpp \
  src/so101_gazebo_demo/test/pick_place/test_so101_fixed_motion_targets.cpp \
  src/so101_gazebo_demo/test/pick_place/test_so101_gripper_adapter.cpp \
  src/so101_gazebo_demo/test/pick_place/test_so101_pick_place_runtime.cpp \
  src/so101_gazebo_demo/test/pick_place/test_so101_world_reset.cpp \
  src/so101_gazebo_demo/test/test_configuration_contract.py \
  src/so101_gazebo_demo/test/test_fingertip_pad_geometry.py \
  src/so101_gazebo_demo/test/test_prepare_simulation_model.py \
  src/so101_gazebo_demo/test/test_so101_launch_contract.py \
  src/so101_gazebo_demo/worlds/so101_pick_place.sdf
git diff --cached --check
git diff --cached --stat
git commit -m "fix(so101): preserve friction grasp baseline"
```

Move the untracked generated manifest into the evidence directory only after confirming its saved SHA-256, then require `git status --short` to be empty. If the baseline cannot pass tests or be cleanly scoped, stop before Task 1 and report the minimal blocker instead of mixing it into retry commits.

---

### Task 1: Pure retry decision and bounded q6 policy

**Files:**
- Create: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/physical_grasp_retry.hpp`
- Create: `src/so101_gazebo_demo/src/pick_place/physical_grasp_retry.cpp`
- Create: `src/so101_gazebo_demo/test/pick_place/test_physical_grasp_retry.cpp`
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_profile.hpp`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`

**Interfaces:**
- Produces:

```cpp
struct PhysicalGraspRetryConfig {
  std::size_t max_attempts{5};
  double contact_missing_tighten_step_q6{0.001};
  double max_tighten_q6{0.004};
};

struct PhysicalGraspRetryProgress {
  std::size_t attempt_index{1};
  std::size_t contact_missing_count{0};
  double current_reclose_target_q6{0.0};
};

struct PhysicalGraspRetryDecision {
  bool retry{false};
  PhysicalGraspRetryProgress next;
  std::optional<Failure> rejection;
};

PhysicalGraspRetryDecision decidePhysicalGraspRetry(
  const PhysicalGraspRetryConfig & config,
  const SO101Profile & profile,
  const PhysicalGraspRetryProgress & current,
  const PhysicalGraspResult & physical_result,
  const WorldSnapshot & after);
```

- Consumes: existing `PhysicalGraspResult`, `WorldSnapshot`, `SO101Profile`, and physical-grasp thresholds.

- [ ] **Step 1: Add failing decision-table tests**

Add tests with these exact expectations:

```cpp
EXPECT_DOUBLE_EQ(q_contact, decide(contact_present).next.current_reclose_target_q6);
EXPECT_DOUBLE_EQ(q_contact - 0.001, decide(first_contact_missing).next.current_reclose_target_q6);
EXPECT_DOUBLE_EQ(q_contact - 0.002, decide(second_contact_missing).next.current_reclose_target_q6);
EXPECT_FALSE(decide(attempt_five).retry);
EXPECT_FALSE(decide(nonpositive_tcp_delta).retry);
EXPECT_FALSE(decide(xy_slip).retry);
EXPECT_FALSE(decide(orientation_failure).retry);
EXPECT_FALSE(decide(attached_world).retry);
```

Also test contact sequence `false, true, false, true` and assert relative close targets `-0.001, -0.001, -0.002, -0.002`.

- [ ] **Step 2: Run RED build**

Run:

```bash
cd /data/work/ws_moveit/.worktrees/refactor-optimization-r3
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select so101_gazebo_demo --cmake-args -DBUILD_TESTING=ON
```

Expected: compile/link failure because the new policy types and `decidePhysicalGraspRetry` do not exist.

- [ ] **Step 3: Implement configuration validation and decision logic**

Implement these invariants before returning any retry:

```cpp
const double deepest_allowed = std::max(
  {profile.q6_contact - config.max_tighten_q6,
   profile.q6_contact - profile.q6_regrasp_squeeze_offset,
   profile.q6_safe_lower});
const double requested = profile.q6_contact -
  static_cast<double>(next.contact_missing_count) *
    config.contact_missing_tighten_step_q6;
next.current_reclose_target_q6 = std::max(requested, deepest_allowed);
```

Retry only table-clearance/follow-ratio failure, or contact-missing with insufficient cup lift, while the measured TCP delta is positive and all stationary/detached/pose-consistency/XY/orientation conditions pass. Return stable `PHYSICAL_GRASP_RETRY_CONFIG_INVALID` or `PHYSICAL_GRASP_RETRY_NOT_SAFE` failures for invalid configuration or unsafe world facts; these rejections are diagnostics, not replacements for the original workflow failure.

- [ ] **Step 4: Run focused GREEN test**

Run:

```bash
source /data/work/ws_moveit/.worktrees/refactor-optimization-r3/install/setup.bash
colcon test --packages-select so101_gazebo_demo --ctest-args -R '^test_physical_grasp_retry$' --output-on-failure
colcon test-result --test-result-base /data/work/ws_moveit/.worktrees/refactor-optimization-r3/build --verbose
```

Expected: `test_physical_grasp_retry` passes with zero failures/errors.

- [ ] **Step 5: Review and commit**

Run `git diff --check`, verify only the five Task 1 files are staged, then commit:

```bash
git add -- src/so101_gazebo_demo/CMakeLists.txt \
  src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/physical_grasp_retry.hpp \
  src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_profile.hpp \
  src/so101_gazebo_demo/src/pick_place/physical_grasp_retry.cpp \
  src/so101_gazebo_demo/test/pick_place/test_physical_grasp_retry.cpp
git commit -m "feat: define SO-101 physical grasp retry policy"
```

---

### Task 2: Persist retry phase and fail closed after interruption

**Files:**
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/physical_grasp_evidence_store.hpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/physical_grasp_evidence_store.cpp`
- Modify: `src/so101_gazebo_demo/test/pick_place/test_physical_grasp_evidence_store.cpp`
- Modify: `src/so101_gazebo_demo/test/pick_place/test_so101_pick_place_runtime.cpp`

**Interfaces:**
- Consumes: `PhysicalGraspRetryProgress` from Task 1.
- Produces:

```cpp
enum class PhysicalGraspRetryPhase {
  IDLE,
  OPEN_PENDING,
  DESCEND_PENDING,
  CLOSE_PENDING,
  LIFT_PENDING,
  VERIFY_PENDING,
  COMPLETE,
};

struct PhysicalGraspRetryEvidence {
  PhysicalGraspRetryProgress progress;
  double micro_lift_preload_target_q6{0.0};
  PhysicalGraspRetryPhase phase{PhysicalGraspRetryPhase::IDLE};
};

virtual std::optional<Failure> saveRetryEvidence(
  const PhysicalGraspRetryEvidence &) = 0;
```

`PhysicalGraspEvidenceRecord` gains `PhysicalGraspRetryEvidence retry`; the file schema becomes version 2.

- [ ] **Step 1: Write RED persistence tests**

Add tests that write/read every phase, preserve before/after samples while retry metadata changes, preserve retry metadata while samples change, reject unknown phases/schema 1/schema 3, and reject attempt 0, attempt >5, non-finite q6, count greater than retries, session mismatch, and fingerprint mismatch. Add a runtime test that loads a pending phase and expects `PHYSICAL_GRASP_RETRY_INTERRUPTED` before any fake motion call.

- [ ] **Step 2: Run RED focused tests**

Run:

```bash
cd /data/work/ws_moveit/.worktrees/refactor-optimization-r3
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select so101_gazebo_demo --cmake-args -DBUILD_TESTING=ON
source install/setup.bash
colcon test --packages-select so101_gazebo_demo --ctest-args -R 'test_physical_grasp_(evidence_store|retry)|test_so101_pick_place_runtime' --output-on-failure
```

Expected: new schema/phase tests fail because version 2 and `saveRetryEvidence` are absent.

- [ ] **Step 3: Implement schema 2 and atomic progress writes**

Use exact JSON keys:

```json
{
  "schema_version": 2,
  "simulation_session_id": "...",
  "configuration_fingerprint": "...",
  "retry": {
    "attempt_index": 1,
    "contact_missing_count": 0,
    "current_reclose_target_q6": -0.047409691482075,
    "micro_lift_preload_target_q6": -0.053409691482075,
    "phase": "IDLE"
  },
  "before_lift": null,
  "after_lift": null
}
```

Keep the existing temporary-file, file `fsync`, atomic rename, and parent-directory `fsync` path. `resetForFreshRun` removes prior schema data. Resume rejects schema 1 instead of guessing retry state. `saveBefore`, `saveAfter`, and `saveRetryEvidence` must use a read-modify-write operation that retains every unrelated record field.

- [ ] **Step 4: Implement interruption check**

Before verification dispatches any retry side effect, map `OPEN_PENDING`, `DESCEND_PENDING`, `CLOSE_PENDING`, `LIFT_PENDING`, and `VERIFY_PENDING` to:

```cpp
Failure{FailureCategory::POSTCONDITION,
        "PHYSICAL_GRASP_RETRY_INTERRUPTED",
        "Physical-grasp retry stopped during an uncertain side-effect phase",
        {{"attempt_index", ...}, {"phase", ...}, {"close_target_q6", ...}}}
```

`IDLE` and `COMPLETE` remain loadable. Do not auto-replay a pending phase.

- [ ] **Step 5: Run GREEN tests and commit**

Run the same focused command and require zero failures/errors. Stage only the four Task 2 files and commit:

```bash
git commit -m "feat: persist SO-101 grasp retry progress"
```

---

### Task 3: Add collision-aware SO-101 world-Z micro-descend

**Files:**
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_joint_motion_adapter.hpp`
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/moveit_joint_planning_boundary.hpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/moveit_joint_planning_boundary.cpp`
- Modify: `src/so101_gazebo_demo/test/pick_place/test_request_scoped_goal_cancellation.cpp`
- Modify: `src/so101_gazebo_demo/test/pick_place/test_so101_pick_place_runtime.cpp`

**Interfaces:**
- Preserve: `executeWorldZMicroLift(const Pose3d &, double positive_delta_m)` and `cancelWorldZMicroLift()`.
- Add with default `NOT_SUPPORTED` implementations for source compatibility:

```cpp
virtual ActionResult executeWorldZMicroDescend(
  const Pose3d & current_tcp_world,
  double target_world_z_m);
virtual ActionResult cancelWorldZMicroDescend();
```

- Production `MoveItJointPlanningBoundary` overrides both methods and exposes a test seam:

```cpp
std::variant<MicroLiftPlanningCapture, ActionResult>
captureWorldZMicroDescendPlanningRequest(
  const Pose3d & current_tcp_world,
  double target_world_z_m);
```

- [ ] **Step 1: Add RED direction, endpoint, collision, and cancellation tests**

Test rejection before MoveIt dispatch for non-finite target, target at/above current Z, and magnitude greater than `0.002 + kMicroLiftPositionToleranceM`. Test a valid 2 mm descend request preserves X/Y/orientation, sets target Z to the saved value, uses collision-aware planning, and uses request-scoped cancellation. Assert existing positive lift failure mappings and `planning_failure_replay` behavior remain unchanged.

- [ ] **Step 2: Run RED build/test**

Run:

```bash
cd /data/work/ws_moveit/.worktrees/refactor-optimization-r3
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select so101_gazebo_demo --cmake-args -DBUILD_TESTING=ON
```

Expected: compile failure for missing descend methods/capture API.

- [ ] **Step 3: Extract one private signed world-Z planning helper**

Make lift and descend public methods perform direction-specific validation, then call one private helper that builds the Cartesian constraint, invokes `/plan_kinematic_path`, validates nonempty trajectory, executes through the request-owned MoveIt goal, and checks endpoint position/orientation. Do not rename the existing lift API or diagnostic artifact kind. Use stable descend codes:

```text
MICRO_DESCEND_TARGET_INVALID
MICRO_DESCEND_PLANNING_FAILED
MICRO_DESCEND_EXECUTION_FAILED
MICRO_DESCEND_ENDPOINT_OUTSIDE_TOLERANCE
MICRO_DESCEND_CANCEL_FAILED
```

- [ ] **Step 4: Run GREEN tests and commit**

Run:

```bash
source /data/work/ws_moveit/.worktrees/refactor-optimization-r3/install/setup.bash
colcon test --packages-select so101_gazebo_demo --ctest-args -R 'test_request_scoped_goal_cancellation|test_planning_failure_(diagnostics|replay)|test_so101_pick_place_runtime' --output-on-failure
colcon test-result --test-result-base /data/work/ws_moveit/.worktrees/refactor-optimization-r3/build --verbose
```

Expected: all selected tests pass. Stage only Task 3 files and commit:

```bash
git commit -m "feat: add SO-101 world Z micro descend"
```

---

### Task 4: Extract reusable physical-grasp stabilization without behavior change

**Files:**
- Create: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/physical_grasp_stabilizer.hpp`
- Create: `src/so101_gazebo_demo/src/pick_place/physical_grasp_stabilizer.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp`
- Modify: `src/so101_gazebo_demo/test/pick_place/test_so101_pick_place_runtime.cpp`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`

**Interfaces:**

```cpp
class SO101PhysicalGraspStabilizer {
public:
  SO101PhysicalGraspStabilizer(
    std::shared_ptr<IWorldObserver>,
    std::shared_ptr<IPhysicalGraspEvidenceStore>,
    std::shared_ptr<ISO101GripperCommand>,
    SO101Profile);
  ActionResult captureBeforeLift();
  ActionResult captureAfterLift();
  ActionResult cancel();
};
```

- [ ] **Step 1: Strengthen characterization tests before extraction**

Lock these existing behaviors with assertions:

- one unilateral sample triggers the existing fixed 6.0 mrad transient seating target;
- bilateral depth-bounded evidence is required for the complete stable window;
- the transient target is exactly `max(q6_safe_lower, q6_contact - 0.006)`;
- that preload remains the commanded q6 through MICRO_LIFT and is not relaxed by the stabilizer;
- after-lift capture never commands q6;
- observation and gripper failures retain exact codes.

- [ ] **Step 2: Run characterization tests before extraction**

Run `test_so101_pick_place_runtime` and record GREEN output as the behavioral baseline.

- [ ] **Step 3: Add the new stabilizer API test and observe RED**

Add a focused test that includes `physical_grasp_stabilizer.hpp`, constructs the class with the existing fakes, calls `captureBeforeLift()`, and expects the same fixed preload target and stable-window evidence as the characterized action. Rebuild and record the expected compile failure because the header/class does not exist.

- [ ] **Step 4: Extract the stabilizer**

Move the current sampling/preload/evidence-write algorithm from the anonymous `StablePhysicalGraspAction` implementation into the new class. Keep sample counts, sleep intervals, bilateral contact/depth predicates, fixed 6.0 mrad preload, preload-through-MICRO_LIFT behavior, accepted contact abort, and failure strings unchanged. Reduce the action to a thin adapter that calls `captureBeforeLift()` or `captureAfterLift()`.

- [ ] **Step 5: Run the same test and compare behavior**

Expected: the same characterization assertions pass; no workflow trace, observer call count, gripper target, or failure code changes.

- [ ] **Step 6: Commit the extraction**

Stage only the five Task 4 files and commit:

```bash
git commit -m "refactor: extract SO-101 grasp stabilizer"
```

---

### Task 5: Implement and wire the bounded retry coordinator

**Files:**
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/physical_grasp_retry.hpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/physical_grasp_retry.cpp`
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/pick_place_runtime.hpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp`
- Modify: `src/so101_gazebo_demo/test/pick_place/test_physical_grasp_retry.cpp`
- Modify: `src/so101_gazebo_demo/test/pick_place/test_so101_pick_place_runtime.cpp`

**Interfaces:**

```cpp
class PhysicalGraspRetryCoordinator {
public:
  PhysicalGraspRetryCoordinator(
    std::shared_ptr<ISO101GripperCommand>,
    std::shared_ptr<IWorldZMicroLift>,
    std::shared_ptr<IWorldObserver>,
    std::shared_ptr<IPhysicalGraspEvidenceStore>,
    std::shared_ptr<SO101PhysicalGraspStabilizer>,
    PhysicalGraspValidator,
    PhysicalGraspGeometry,
    SO101Profile,
    PhysicalGraspRetryConfig);
  ActionResult verifyOrRetry();
  ActionResult cancel();
};
```

- [ ] **Step 1: Add RED orchestration tests**

Use recording fakes and assert exact call order:

```text
load/validate
save OPEN_PENDING
PREOPEN
save DESCEND_PENDING
MICRO_DESCEND(saved_before_z)
save CLOSE_PENDING
CLOSE(current_reclose_target)
captureBeforeLift
fixed PRELOAD(q6_contact - 0.006, capped by q6_safe_lower)
save LIFT_PENDING
MICRO_LIFT(0.002)
captureAfterLift
save VERIFY_PENDING
load/validate
```

Cover initial success; success on attempts 2/3/4/5; contact-present same target; contact-missing 1.0 mrad cumulative target; mixed contact sequence; exactly five lifts/four retry sequences; no sixth side effect; nonretryable results; attached/moving/stale/mismatched evidence; each substep failure; cancel between every pair of calls; interrupted phases; and fifth-failure preservation.

- [ ] **Step 2: Run RED focused test**

Run `test_physical_grasp_retry`; expected failures show coordinator/call sequence is absent.

- [ ] **Step 3: Implement orchestration with cancellation gates**

Use an atomic cancellation flag. Check it before every persisted phase and before every external command. Persist the phase before its side effect. Observe and validate fresh detached/stationary world state after PREOPEN and micro-descend. Always compute descend target from the current attempt's saved `before_lift->tcp_pose_world.z`.

On exhaustion, copy the fifth `Failure` and append only:

```cpp
failure.metrics["physical_grasp_attempts"] = 5.0;
failure.metrics["physical_grasp_retries"] = 4.0;
failure.metrics["contact_missing_count"] = static_cast<double>(count);
failure.metrics["final_reclose_target_q6"] = reclose_target;
failure.metrics["micro_lift_preload_target_q6"] =
  std::max(profile.q6_safe_lower,
           profile.q6_contact - profile.q6_regrasp_squeeze_offset);
failure.metrics["retry_exhausted"] = 1.0;
```

- [ ] **Step 4: Wire only `VERIFY_PHYSICAL_GRASP`**

Construct one stabilizer and coordinator in `registerPhysicalGrasp`. `WAIT_GRASP_STABLE`, `MICRO_LIFT`, and `WAIT_MICRO_LIFT_STABLE` keep their public workflow actions. Replace only the verification executor's internals with `verifyOrRetry`; its `cancel()` delegates to the coordinator. Do not change `TransitionTable`, `WorkflowDefinition`, the common runner, or Panda.

- [ ] **Step 5: Run focused GREEN suite**

Run:

```bash
cd /data/work/ws_moveit/.worktrees/refactor-optimization-r3
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-up-to pick_place_common panda_gazebo_demo so101_gazebo_demo --cmake-args -DBUILD_TESTING=ON
source install/setup.bash
colcon test --packages-select so101_gazebo_demo --ctest-args -R 'test_physical_grasp_(validator|evidence_store|retry)|test_so101_pick_place_runtime|test_request_scoped_goal_cancellation|test_pick_place_(checkpoint|runner)' --output-on-failure
colcon test-result --test-result-base build --verbose
```

Expected: zero failures/errors. Confirm existing nominal q6 and 6.0 mrad seating assertions remain unchanged.

- [ ] **Step 6: Commit coordinator integration**

Stage only the six Task 5 files and commit:

```bash
git commit -m "feat: retry failed SO-101 micro lifts"
```

---

### Task 6: Documentation, full regression, and live/visual acceptance

**Files:**
- Create: `src/so101_gazebo_demo/test/headless/so101_micro_lift_retry_fixture.py`
- Modify: `src/so101_gazebo_demo/README.md`
- Modify: `docs/pick-place-architecture.md`
- Modify: `docs/pick-place-launch-parameters.md`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt` only if the headless fixture is registered as a non-installed test.

**Interfaces:**
- The fixture accepts:

```text
--checkpoint PATH
--evidence-dir PATH
--case contact-present|contact-missing|mixed|exhaustion|nonretryable
--expected-attempts N
--expected-reclose-q6 VALUE
--expected-preload-q6 VALUE
```

It controls only the already-running isolated SO-101 stack, records PID/domain/partition/session ownership, uses the existing Gazebo set-pose and gripper action surfaces, and never installs a production fault-injection launch argument.

Implement the fixture around these concrete helpers:

```python
@dataclasses.dataclass(frozen=True)
class RetryExpectation:
    attempts: int
    reclose_offsets_rad: tuple[float, ...]
    preload_offset_rad: float = -0.006
    expect_attachment: bool = False

def run_state_machine(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ros2", "run", "so101_gazebo_demo", "pick_place_state_machine", *args],
        check=False, text=True, capture_output=True, timeout=180)

def load_sidecar(checkpoint: pathlib.Path) -> dict[str, object]:
    return json.loads(pathlib.Path(f"{checkpoint}.physical-grasp.json").read_text())

def wait_for_retry_phase(checkpoint: pathlib.Path, attempt: int, phase: str) -> dict[str, object]:
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        record = load_sidecar(checkpoint)
        retry = record["retry"]
        if retry["attempt_index"] == attempt and retry["phase"] == phase:
            return record
        time.sleep(0.01)
    raise AssertionError(f"retry phase not observed: attempt={attempt} phase={phase}")

def assert_retry_records(records: list[dict[str, object]], expected: RetryExpectation,
                         q6_contact: float) -> None:
    assert len(records) == expected.attempts
    retry_records = [record["retry"] for record in records]
    assert [r["current_reclose_target_q6"] - q6_contact for r in retry_records[1:]] == \
        pytest.approx(expected.reclose_offsets_rad, abs=1e-9)
    assert [r["micro_lift_preload_target_q6"] - q6_contact for r in retry_records] == \
        pytest.approx([expected.preload_offset_rad] * expected.attempts, abs=1e-9)
```

The live fault driver must poll the sidecar phase before each mutation, save the unmodified Gazebo pose/contact stream, apply the requested existing Gazebo set-pose or gripper action, and stop mutating immediately after the matching after-lift sample is written. If the requested physical contact fact is not observed, mark the case invalid and rerun after canonical reset; never relabel a different contact outcome as the requested case.

- [ ] **Step 1: Document the exact behavior**

Update all three documents with:

- five total attempts, not five additional retries;
- contact-present keeps the current q6 target;
- contact-missing subtracts 1.0 mrad from only the reclose target, maximum cumulative 4.0 mrad;
- every attempt then applies and holds the unchanged fixed 6.0 mrad preload through MICRO_LIFT;
- PREOPEN -> saved-Z descend -> reclose -> stable capture -> 2 mm lift -> verify;
- nonretryable failures and last-failure preservation;
- sidecar attempt/phase fields and interruption failure;
- explicit statement that Panda/common do not implement this behavior.

- [ ] **Step 2: Run complete three-package regression**

Run:

```bash
cd /data/work/ws_moveit/.worktrees/refactor-optimization-r3
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-up-to pick_place_common panda_gazebo_demo so101_gazebo_demo --cmake-args -DBUILD_TESTING=ON
source install/setup.bash
colcon test --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --event-handlers console_direct+
colcon test-result --test-result-base build --verbose
```

Expected: all three packages report zero failures and zero errors. Record exact passed/skipped counts in the evidence directory.

- [ ] **Step 3: Prove overlay provenance before runtime**

Run and save output:

```bash
ros2 pkg prefix pick_place_common
ros2 pkg prefix panda_gazebo_demo
ros2 pkg prefix so101_gazebo_demo
command -v ros2
printf '%s\n' "$AMENT_PREFIX_PATH"
readlink -f install/so101_gazebo_demo/lib/so101_gazebo_demo/pick_place_state_machine
```

Expected: every package/binary resolves under `/data/work/ws_moveit/.worktrees/refactor-optimization-r3/install` before any underlay.

- [ ] **Step 4: Audit and prepare the single owned stack**

Record `tmux ls`, `ps -eo pid,ppid,lstart,args`, ROS domain, Gazebo partition, nodes, controllers, joints, TF, Gazebo cup pose/contact, and MoveIt world/attached membership. Identify PID/parent/tmux ownership before stopping only conflicting ROS/Gazebo/MoveIt processes. Preserve non-ROS processes, other worktrees, sampler clang-tidy, and `codex-cua`.

Use one tmux-held GUI environment:

```bash
source ~/gui-env.zsh
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_moveit/.worktrees/refactor-optimization-r3/install/setup.zsh
export ROS_DOMAIN_ID=215
export GZ_PARTITION=friction-takeover-20260806
```

Do not start a second stack if the owned `r3-friction-*` stack is healthy.

- [ ] **Step 5: Run deterministic retry fixtures on the existing stack**

Create a new evidence directory with `mktemp -d /tmp/so101-micro-lift-retry-20260806-XXXXXX`. For each case, reset to the canonical detached world, use a unique simulation session/checkpoint, run the fixture, and assert:

```text
contact-present: retry reclose target unchanged; MICRO_LIFT preload remains fixed at q6_contact - 0.006
contact-missing: retry reclose target exactly previous target - 0.001 rad; preload remains fixed
mixed: reclose tightening only on missing-contact attempts; preload remains fixed on every lift
exhaustion: exactly 5 lifts, 4 opens/descends/recloses, no attachment, fifth failure preserved
nonretryable: no open/descend/reclose after the failed probe
```

The fixture must save raw commands, sidecar JSON, checkpoint hashes, poses, contact stream, q6 stream, and exit status for every case.

- [ ] **Step 6: Run unforced SO-101 acceptance**

Run five consecutive fresh execute sessions with the current nominal gripper strategy and a canonical reset between runs:

```bash
ros2 launch so101_gazebo_demo so101_pick_place.launch.py \
  start_simulation:=false \
  run_mode:=execute \
  checkpoint_path:=/tmp/so101-r3-retry-checkpoint.json \
  simulation_session_id:=so101-r3-retry-live-N
```

Expected for every run: either initial probe success or a bounded evidenced retry success; final Gazebo and MoveIt attachments agree; controller/joint/TF facts agree; reclose targets obey the 1.0/4.0 mrad bounds; every MICRO_LIFT uses the unchanged fixed 6.0 mrad preload. Acceptance requires five successful end-to-end runs, not merely five process exits.

- [ ] **Step 7: Capture fresh visual evidence**

After loading `~/gui-env.zsh`, use `ai-station-capture.sh` and copy its reported PNG into the evidence directory for:

1. contact-present regrasp at DESCEND height;
2. contact-missing tightened regrasp;
3. successful cup/TCP micro-lift;
4. forced exhaustion with the cup detached;
5. final successful SO-101 attachment/carry;
6. Panda regression.

Inspect every image rather than treating capture success as visual acceptance. The cup, fingertips, arm posture, table clearance, and attachment outcome must match the numeric evidence.

- [ ] **Step 8: Run one fresh Panda runtime regression**

Use a distinct session on the same ROS environment only after the SO-101 stack is cleanly stopped; do not overlap stacks:

```bash
ros2 launch panda_gazebo_demo panda_gazebo.launch.py \
  run_state_machine:=true \
  mode:=execute \
  simulation_session_id:=panda-r3-retry-regression
```

Expected: existing Panda state trace, checkpoint semantics, attachment, and place result are unchanged; no SO-101 retry states, logs, parameters, or sidecar appear.

- [ ] **Step 9: Commit docs and fixture**

Run fixture unit/lint tests, `git diff --check`, and stage only Task 6 files:

```bash
git add -- docs/pick-place-architecture.md \
  docs/pick-place-launch-parameters.md \
  src/so101_gazebo_demo/CMakeLists.txt \
  src/so101_gazebo_demo/README.md \
  src/so101_gazebo_demo/test/headless/so101_micro_lift_retry_fixture.py
git commit -m "test: accept SO-101 micro lift retries"
```

- [ ] **Step 10: Final verification and cleanup**

Verify scoped commits, `git diff --check`, no staged files, and identify every remaining dirty path as either pre-existing R3 work or an unintended implementation residue. Clean only owned ROS/Gazebo/MoveIt processes after checking PID ownership. Confirm no push/merge/root checkout/other worktree/`codex-cua` change occurred. Report:

- commit hashes and exact changed files;
- RED and GREEN evidence;
- three-package test counts;
- each deterministic retry case and five unforced SO-101 outcomes;
- Panda outcome;
- overlay provenance;
- visual/evidence paths;
- final worktree and process status;
- remaining risks.

Stop and request user direction if runtime behavior requires weakening any physical threshold, exceeding the q6 bounds, changing checkpoint/session semantics, modifying Panda/common behavior, or clearing a process whose ownership is ambiguous.
