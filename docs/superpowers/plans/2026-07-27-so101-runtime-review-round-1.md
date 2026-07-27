# SO-101 Runtime Review Round 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close all Critical and Important round-1 review findings in the fail-closed SO-101 pick/place runtime without launching or executing simulation.

**Architecture:** Keep the existing observer and transition-contract boundaries. Make freshness compositional by collecting a final robot/MoveIt snapshot after Gazebo evidence is available, and make all safety checks quantify over every reported failure and every attachment transition boundary.

**Tech Stack:** C++17, ROS 2 Jazzy, MoveIt 2, Gazebo Transport test publishers, GoogleTest, CTest.

## Global Constraints

- Source only `/opt/ros/jazzy/setup.zsh` and `/data/work/ws_moveit/install/setup.zsh`.
- Do not launch Gazebo or MoveIt, execute the arm, use a GUI, or signal any process.
- Do not modify `src/panda_gazebo_demo`; its tree must remain `75fb2e1e66ad1440f47f52f708b91887384084fd`.
- Use `apply_patch` for source edits and strict RED/GREEN TDD for every behavior change.
- Do not run `test_so101_pick_place_world` or the full `test_so101_launch_contract` target.

---

### Task 1: Coherent final combined observation

**Files:**
- Modify: `src/so101_gazebo_demo/test/pick_place/test_so101_pick_place_runtime.cpp`
- Modify: `src/so101_gazebo_demo/test/pick_place/test_so101_gazebo_attachment.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/gazebo_world_observer.cpp`

**Interfaces:**
- Consumes: `IJointPlanningBoundary::currentState()`, `IWorldObserver::observe()`.
- Produces: a combined `ObservationResult` whose final joint, gripper, MoveIt scene, and Gazebo evidence are all fresh at return.

- [x] **Step 1: Write failing final-freshness tests**

```cpp
TEST(SO101MoveItWorldObserver, RejectsJointEvidenceThatGoesStaleWhileSceneIsCollected)
{
  // First currentState() is fresh; the post-scene currentState() is stale.
  EXPECT_EQ(observer.observe().failure->code, "JOINT_EVIDENCE_STALE");
}

TEST(SO101GazeboWorldObserver, ReobservesMoveItAfterGazeboWait)
{
  // First MoveIt result is valid; second result is an observation failure.
  EXPECT_FALSE(observer.observe().snapshot);
  EXPECT_EQ(base.calls, 2);
}
```

- [x] **Step 2: Run RED**

```bash
ctest --test-dir build/so101_gazebo_demo -R '^(test_so101_pick_place_runtime|test_so101_gazebo_attachment)$' --output-on-failure
```

Expected: the runtime observer accepts the now-stale state and the Gazebo wrapper calls its MoveIt observer only once.

- [x] **Step 3: Implement final observation rechecks**

```cpp
const auto scene = boundary_->sceneFacts();
current = boundary_->currentState();
// Revalidate shape, finite values, receive age, gripper, velocity, and settle.

auto gazebo = impl_->enrich(*initial.snapshot);
auto refreshed = moveit_observer_.observe();
return refreshed.snapshot ? impl_->enrich(*refreshed.snapshot) : refreshed;
```

- [x] **Step 4: Run focused GREEN** using the command from Step 2.

### Task 2: Stationarity and all-failure terminal routing

**Files:**
- Modify: `src/so101_gazebo_demo/test/pick_place/test_so101_pick_place_runtime.cpp`
- Modify: `src/so101_gazebo_demo/test/pick_place/test_pick_place_runner.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/runner.cpp`

**Interfaces:**
- Consumes: `WorldSnapshot::gazebo_coke_stationary`, `ValidationResult::failures`.
- Produces: contracts that require true stationarity and runner routing that stops on any environment-evidence failure.

- [x] **Step 1: Write failing tests**

```cpp
world.gazebo_coke_stationary = false;
EXPECT_FALSE(contract->validatePrecondition(world).ok);

contract.failures = {arm_not_quiescent, stale_observation};
EXPECT_EQ(result.status, RunStatus::ERROR);
EXPECT_EQ(executor.cancel_calls, 0);
```

- [x] **Step 2: Run RED**

```bash
ctest --test-dir build/so101_gazebo_demo -R '^(test_so101_pick_place_runtime|test_pick_place_runner)$' --output-on-failure
```

- [x] **Step 3: Implement minimal checks**

```cpp
if (!snapshot.gazebo_coke_stationary || !*snapshot.gazebo_coke_stationary) {
  addFailure(...);
}

const auto unsafe = std::find_if(precondition.failures.begin(),
                                 precondition.failures.end(),
                                 environmentEvidenceUnavailable);
```

- [x] **Step 4: Run focused GREEN** using the command from Step 2.

### Task 3: Detach and sync Coke support invariants

**Files:**
- Modify: `src/so101_gazebo_demo/test/pick_place/test_so101_attachment_contracts.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/so101_attachment_contracts.cpp`

**Interfaces:**
- Consumes: before/after Gazebo Coke 6D poses and `SO101Profile::coke_pose`.
- Produces: blocking failures for drift or unsupported Coke pose across forward/recovery detach and sync transitions.

- [x] **Step 1: Write a table-driven failing test**

```cpp
for (const auto transition : detach_and_sync_transitions) {
  auto after = exactExpectedAfter(transition);
  after.gazebo_coke_pose_world->x += profile.coke_position_drift_tolerance * 2.0;
  EXPECT_FALSE(contract->validate(before, after, success).ok);
}
```

- [x] **Step 2: Run RED**

```bash
ctest --test-dir build/so101_gazebo_demo -R '^test_so101_attachment_contracts$' --output-on-failure
```

- [x] **Step 3: Apply drift and support checks to every detach/sync branch**

```cpp
requireNoCokeJump(result, before, after, profile_);
requireExpectedSupportPose(result, before, after, profile_);
```

- [x] **Step 4: Run focused GREEN** using the command from Step 2.

### Task 4: Pure verification, report, and commit

**Files:**
- Append: `.superpowers/sdd/2026-07-26-so101-pick-place-port/task-5-report.md`

- [x] **Step 1: Run the pure named suite only**

```bash
ctest --test-dir build/so101_gazebo_demo -j1 --output-on-failure -E '^test_so101_(pick_place_world|launch_contract)$'
```

- [x] **Step 2: Verify diff and Panda integrity**

```bash
git diff --check
git rev-parse HEAD:src/panda_gazebo_demo
```

- [x] **Step 3: Append every RED/GREEN command and result to the Task 5 report.**

- [x] **Step 4: Commit the scoped fix without pushing.**
