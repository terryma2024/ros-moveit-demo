# SO-101 TCP Workspace Sampler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an ai-station-only offline C++ tool that deterministically samples SO-101 joints 1-5, records every sampled TCP position and orientation, filters a fixed-preopen collision-free subset against the canonical table/pedestal Planning Scene, and exports resumable CSV/PLY/JSON artifacts with convergence evidence.

**Architecture:** A focused `so101_workspace_sampling` library owns configuration, deterministic joint generation, local MoveIt state evaluation, pose coverage, checkpoints, and artifact writing. A single ROS 2 node receives package-local expanded URDF/SRDF parameters from a dedicated launch file; it never starts or queries move_group, Gazebo, controllers, or live Planning Scene services.

**Tech Stack:** C++17, ROS 2 Jazzy `rclcpp`, MoveIt 2 `RobotModel`/`RobotState`/`PlanningScene`, Eigen, nlohmann JSON, OpenSSL SHA-256, ament CMake/GTest, Python launch-contract tests, binary little-endian PLY.

## Global Constraints

- Implement the approved spec at `docs/superpowers/specs/2026-08-04-so101-workspace-sampler-design.md` without adding IK, path planning, Gazebo execution, online APIs, or grasp-direction filters.
- Run implementation and live acceptance on ai-station; the Mac is only for opening final PLY files in CloudCompare.
- The arm sample dimensions are exactly joints `1`, `2`, `3`, `4`, `5`; set joint `6` to `SO101Profile::canonical().q6_preopen` for every collision query.
- Load joint bounds, `so101_tcp`, and SRDF Allowed Collision Matrix from the installed model; do not duplicate them in sampler configuration.
- The local collision world contains exactly canonical `table` and `base_pedestal`; it never contains `plastic_cup`.
- Keep geometric samples even when colliding. `collision_free` means bounds-valid, no self collision, and no table/pedestal collision.
- Default `full`: 1800 s, batch 25000, minimum 250000, maximum 2000000, position voxel 0.005 m, orientation threshold 10 deg, five stable batches, position new-rate below 0.001, orientation new-rate below 0.002.
- Preserve all existing root/submodule changes. Stage only files named by the current task; do not commit the root repository's `moveit-demo` pointer.
- Do not run `ament_uncrustify --reformat`. Use the repository C++ quality gate read-only and make targeted formatting patches.
- Before runtime acceptance, record source/install/process provenance and prove no second move_group/Gazebo/controller stack was started.

---

## Planned File Structure

```text
src/so101_gazebo_demo/
├── include/so101_gazebo_demo/workspace/
│   ├── workspace_types.hpp              # public value types, profiles, stop/failure vocabulary
│   ├── joint_sample_generator.hpp       # explicit, global Halton, local-refinement generation
│   ├── pose_coverage_index.hpp          # position voxels, orientation clusters, convergence
│   ├── workspace_state_evaluator.hpp    # RobotModel validation, local scene, FK/collision
│   ├── workspace_artifact_writer.hpp    # batch CSV/PLY and final stream merge
│   ├── workspace_checkpoint_store.hpp   # provenance hashes, checkpoints, resume validation
│   └── workspace_sampler.hpp            # batch orchestration and stop semantics
├── src/workspace/
│   ├── workspace_types.cpp
│   ├── joint_sample_generator.cpp
│   ├── pose_coverage_index.cpp
│   ├── workspace_state_evaluator.cpp
│   ├── workspace_artifact_writer.cpp
│   ├── workspace_checkpoint_store.cpp
│   └── workspace_sampler.cpp
├── src/nodes/sample_so101_workspace.cpp # ROS parameter composition root and process exit mapping
├── launch/so101_workspace_sample.launch.py
├── test/workspace/
│   ├── test_workspace_types.cpp
│   ├── test_joint_sample_generator.cpp
│   ├── test_pose_coverage_index.cpp
│   ├── test_workspace_state_evaluator.cpp
│   ├── test_workspace_artifact_writer.cpp
│   ├── test_workspace_checkpoint_store.cpp
│   └── test_workspace_sampler.cpp
├── test/test_workspace_launch_contract.py
└── docs/so101-workspace-sampler.md
```

The workspace library may reuse `pick_place::SO101Profile`, `pick_place::Pose3d`, and the existing pure collision-object builders, but no workspace file may include the pick-place runner, Teleop, Gazebo attachment, or controller adapters.

---

### Task 1: Lock Workspace Types and Profile Defaults

**Files:**
- Create: `src/so101_gazebo_demo/include/so101_gazebo_demo/workspace/workspace_types.hpp`
- Create: `src/so101_gazebo_demo/src/workspace/workspace_types.cpp`
- Create: `src/so101_gazebo_demo/test/workspace/test_workspace_types.cpp`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt:37-180,203-410`

**Interfaces:**
- Produces: `WorkspaceSamplingConfig`, `WorkspaceProfile`, `SampleSource`, `StopReason`, `PositionVoxelKey`, `GeneratedJointSample`, `PoseSample`, `BatchCoverageDelta`, `RunSummary` in namespace `so101_gazebo_demo::workspace`.
- Produces: `WorkspaceSamplingConfig configForProfile(WorkspaceProfile)` and `std::optional<std::string> validateConfig(const WorkspaceSamplingConfig &) `.

- [ ] **Step 1: Add the failing profile/default tests and CMake test target**

```cpp
TEST(WorkspaceTypes, FullProfileMatchesApprovedDefaults)
{
  const auto config = ws::configForProfile(ws::WorkspaceProfile::FULL);
  EXPECT_EQ(config.time_budget, std::chrono::seconds(1800));
  EXPECT_EQ(config.batch_size, 25000U);
  EXPECT_EQ(config.minimum_samples, 250000U);
  EXPECT_EQ(config.maximum_samples, 2000000U);
  EXPECT_DOUBLE_EQ(config.position_voxel_size_m, 0.005);
  EXPECT_DOUBLE_EQ(config.orientation_threshold_rad, 0.17453292519943295);
  EXPECT_EQ(config.stable_batches, 5U);
  EXPECT_DOUBLE_EQ(config.position_new_rate_threshold, 0.001);
  EXPECT_DOUBLE_EQ(config.orientation_new_rate_threshold, 0.002);
}

TEST(WorkspaceTypes, RejectsSampleCountsOutsidePlyUint32Contract)
{
  auto config = ws::configForProfile(ws::WorkspaceProfile::FULL);
  config.maximum_samples = std::uint64_t{1} << 32;
  ASSERT_TRUE(ws::validateConfig(config));
  EXPECT_EQ(*ws::validateConfig(config), "maximum_samples must fit PLY uint32 sample_id");
}
```

Add `so101_workspace_sampling` and `test_workspace_types` to CMake, and append `so101_workspace_sampling` to the existing C++ quality-gate target list.

- [ ] **Step 2: Build to verify RED**

Run on ai-station:

```bash
cd /data/work/ws_moveit
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_gazebo_demo --symlink-install
```

Expected: compilation fails because `workspace_types.hpp` declarations and definitions do not exist yet.

- [ ] **Step 3: Implement the exact public vocabulary and defaults**

```cpp
enum class WorkspaceProfile { QUICK, FULL, DEEP };
enum class SampleSource : std::uint8_t
{
  EXPLICIT_BOUNDARY = 0,
  REGULAR_BASELINE = 1,
  HALTON_GLOBAL = 2,
  LOCAL_REFINEMENT = 3
};
enum class StopReason
{
  CONVERGED_AT_CONFIGURED_RESOLUTION,
  SAMPLE_CAP_REACHED,
  BUDGET_EXHAUSTED,
  INTERRUPTED,
  FAILED
};

struct WorkspaceSamplingConfig
{
  std::chrono::seconds time_budget{1800};
  std::size_t batch_size{25000};
  std::uint64_t minimum_samples{250000};
  std::uint64_t maximum_samples{2000000};
  double position_voxel_size_m{0.005};
  double orientation_threshold_rad{0.17453292519943295};
  std::size_t stable_batches{5};
  double position_new_rate_threshold{0.001};
  double orientation_new_rate_threshold{0.002};
};

struct PositionVoxelKey
{
  std::int32_t x;
  std::int32_t y;
  std::int32_t z;
  bool operator==(const PositionVoxelKey & other) const noexcept;
  bool operator<(const PositionVoxelKey & other) const noexcept;
};

struct GeneratedJointSample
{
  std::uint64_t sequence_id;
  SampleSource source;
  std::array<double, 5> arm_joints;
};

struct PoseSample
{
  std::uint64_t sample_id;
  SampleSource source;
  std::array<double, 5> arm_joints;
  double gripper_q6;
  pick_place::Pose3d tcp_pose;
  bool bounds_valid;
  bool self_collision;
  bool scene_collision;
  bool collision_free;
  PositionVoxelKey position_voxel;
  std::uint32_t orientation_cluster_id;
};

struct BatchCoverageDelta
{
  std::uint64_t new_position_voxels;
  std::uint64_t new_orientation_clusters;
  std::uint64_t existing_position_voxels_before_batch;
  std::uint64_t existing_orientation_clusters_before_batch;
};

struct WorkspaceFailure
{
  std::string code;
  std::string message;
};

struct WorkspaceArtifactPaths
{
  std::filesystem::path samples_csv;
  std::filesystem::path all_poses_ply;
  std::filesystem::path collision_free_poses_ply;
  std::filesystem::path position_voxels_ply;
};

struct RunSummary
{
  bool success;
  StopReason stop_reason;
  std::uint64_t completed_samples;
  std::uint64_t collision_free_samples;
  std::optional<WorkspaceFailure> failure;
  std::filesystem::path output_directory;
  std::optional<WorkspaceArtifactPaths> artifacts;
};
```

Implement `PositionVoxelKey::operator<` as lexicographic `(x,y,z)` ordering. Also implement `workspaceProfileFromString`, `toString(WorkspaceProfile)`, `toString(SampleSource)`, and `toString(StopReason)` in this task. Put every field shown above in the public header with these exact names; later tasks must not introduce a second sample or failure vocabulary.

- [ ] **Step 4: Build and run the focused test**

```bash
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
colcon test --packages-select so101_gazebo_demo --ctest-args -R '^test_workspace_types$' --output-on-failure
colcon test-result --verbose
```

Expected: `test_workspace_types` passes; no other test result is introduced.

- [ ] **Step 5: Commit Task 1**

```bash
git add -- src/so101_gazebo_demo/CMakeLists.txt src/so101_gazebo_demo/include/so101_gazebo_demo/workspace/workspace_types.hpp src/so101_gazebo_demo/src/workspace/workspace_types.cpp src/so101_gazebo_demo/test/workspace/test_workspace_types.cpp
git commit -m "feat(so101): define workspace sampling contract"
```

---

### Task 2: Implement Deterministic Joint Generation

**Files:**
- Create: `src/so101_gazebo_demo/include/so101_gazebo_demo/workspace/joint_sample_generator.hpp`
- Create: `src/so101_gazebo_demo/src/workspace/joint_sample_generator.cpp`
- Create: `src/so101_gazebo_demo/test/workspace/test_joint_sample_generator.cpp`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`

**Interfaces:**
- Consumes: `GeneratedJointSample`, `SampleSource`, `PositionVoxelKey` from Task 1.
- Produces: `using JointBounds = std::array<std::pair<double, double>, 5>`.
- Produces: `GeneratorCheckpoint`, `RefinementSeed`, and class `JointSampleGenerator` with `explicitSamples()`, `nextGlobal(count)`, `nextRefined(seeds,count)`, `checkpoint()`, and `restore(checkpoint)`.

```cpp
struct GeneratorCheckpoint
{
  std::uint64_t next_global_index{1};
  std::uint64_t next_local_index{1};
  std::map<std::uint64_t, std::uint32_t> refinement_scale_levels;
};

struct RefinementSeed
{
  std::uint64_t sample_id;
  std::uint8_t priority;
  PositionVoxelKey voxel;
  std::array<double, 5> arm_joints;
  std::uint32_t scale_level;
};

class JointSampleGenerator
{
public:
  explicit JointSampleGenerator(JointBounds bounds);
  std::vector<GeneratedJointSample> explicitSamples(
    const std::array<double, 5> & home) const;
  std::vector<GeneratedJointSample> nextGlobal(std::size_t count);
  std::vector<GeneratedJointSample> nextRefined(
    const std::vector<RefinementSeed> & seeds, std::size_t count);
  GeneratorCheckpoint checkpoint() const;
  void restore(const GeneratorCheckpoint & checkpoint);
};
```

- [ ] **Step 1: Write deterministic prefix, bounds, and restore tests**

```cpp
TEST(JointSampleGenerator, GlobalPrefixUsesApprovedHaltonBases)
{
  const ws::JointBounds bounds{{{0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}}};
  ws::JointSampleGenerator generator(bounds);
  const auto samples = generator.nextGlobal(2);
  EXPECT_EQ(samples.size(), 2U);
  EXPECT_EQ(samples[0].source, ws::SampleSource::HALTON_GLOBAL);
  EXPECT_NEAR(samples[0].arm_joints[0], 0.5, 1e-15);
  EXPECT_NEAR(samples[0].arm_joints[1], 1.0 / 3.0, 1e-15);
  EXPECT_NEAR(samples[0].arm_joints[2], 0.2, 1e-15);
  EXPECT_NEAR(samples[0].arm_joints[3], 1.0 / 7.0, 1e-15);
  EXPECT_NEAR(samples[0].arm_joints[4], 1.0 / 11.0, 1e-15);
  EXPECT_NEAR(samples[1].arm_joints[0], 0.25, 1e-15);
}

TEST(JointSampleGenerator, RestoreContinuesAtTheSameGlobalIndex)
{
  ws::JointSampleGenerator first(unitBounds());
  first.nextGlobal(13);
  const auto checkpoint = first.checkpoint();
  const auto expected = first.nextGlobal(5);
  ws::JointSampleGenerator resumed(unitBounds());
  resumed.restore(checkpoint);
  EXPECT_EQ(resumed.nextGlobal(5), expected);
}
```

Add reflection tests proving a local perturbation below min reflects upward by the same distance and never clamps onto the bound.

- [ ] **Step 2: Run RED test**

```bash
colcon build --packages-select so101_gazebo_demo --symlink-install
```

Expected: compile/link failure for missing `JointSampleGenerator` methods.

- [ ] **Step 3: Implement Halton, explicit samples, local refinement, and checkpointing**

```cpp
double halton(std::uint64_t index, unsigned base)
{
  double result = 0.0;
  double factor = 1.0;
  while (index > 0) {
    factor /= static_cast<double>(base);
    result += factor * static_cast<double>(index % base);
    index /= base;
  }
  return result;
}

double reflectIntoBounds(double value, double lower, double upper)
{
  const double width = upper - lower;
  const double period = 2.0 * width;
  double offset = std::fmod(value - lower, period);
  if (offset < 0.0)
    offset += period;
  return offset <= width ? lower + offset : upper - (offset - width);
}
```

Use global bases `{2,3,5,7,11}`. Use local bases `{13,17,19,23,29}` so local checkpoint indices cannot alter the global sequence. Generate Home/midpoint/single-joint min/max explicitly and use a quantized five-joint key at `1e-12 rad` for deduplication.

- [ ] **Step 4: Run focused tests**

```bash
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
colcon test --packages-select so101_gazebo_demo --ctest-args -R '^test_joint_sample_generator$' --output-on-failure
```

Expected: deterministic prefix, reflection, explicit-source, deduplication, and restore tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add -- src/so101_gazebo_demo/CMakeLists.txt src/so101_gazebo_demo/include/so101_gazebo_demo/workspace/joint_sample_generator.hpp src/so101_gazebo_demo/src/workspace/joint_sample_generator.cpp src/so101_gazebo_demo/test/workspace/test_joint_sample_generator.cpp
git commit -m "feat(so101): add deterministic workspace joint sampling"
```

---

### Task 3: Track Position and Orientation Coverage

**Files:**
- Create: `src/so101_gazebo_demo/include/so101_gazebo_demo/workspace/pose_coverage_index.hpp`
- Create: `src/so101_gazebo_demo/src/workspace/pose_coverage_index.cpp`
- Create: `src/so101_gazebo_demo/test/workspace/test_pose_coverage_index.cpp`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`

**Interfaces:**
- Consumes: `PoseSample`, `PositionVoxelKey`, `BatchCoverageDelta`, `RefinementSeed`.
- Produces: `OrientationAssignment`, `PositionVoxelSummary`, `PoseCoverageCheckpoint`.
- Produces: `PoseCoverageIndex::insert(PoseSample &)`, `finishBatch()`, `voxelSummaries()`, `refinementSeeds()`, `checkpoint()`, and `restore()`.

```cpp
struct OrientationAssignment
{
  PositionVoxelKey voxel;
  std::uint32_t cluster_id;
  bool created_position_voxel;
  bool created_orientation_cluster;
};

struct PositionVoxelSummary
{
  PositionVoxelKey key;
  std::uint64_t sample_count;
  std::uint64_t collision_free_count;
  std::uint32_t orientation_count;
  std::uint32_t collision_free_orientation_count;
};

struct OrientationClusterSnapshot
{
  std::uint32_t cluster_id;
  std::array<double, 4> representative_xyzw;
  bool has_collision_free_sample;
};

struct PositionVoxelSnapshot
{
  PositionVoxelSummary summary;
  std::vector<OrientationClusterSnapshot> clusters;
  std::vector<RefinementSeed> seed_candidates;
};

struct PoseCoverageCheckpoint
{
  std::vector<PositionVoxelSnapshot> voxels;
  std::size_t consecutive_stable_batches;
};

class ConvergenceTracker
{
public:
  explicit ConvergenceTracker(WorkspaceSamplingConfig config);
  bool observe(const BatchCoverageDelta & delta, std::uint64_t completed_samples);
  std::size_t consecutiveStableBatches() const noexcept;
  void restore(std::size_t consecutive_stable_batches);
};
```

- [ ] **Step 1: Write failing voxel/quaternion/convergence tests**

```cpp
TEST(PoseCoverageIndex, UsesFloorForNegativeWorldCoordinates)
{
  ws::PoseCoverageIndex index(0.005, radians(10.0));
  EXPECT_EQ(index.keyFor({-0.0001, 0.0049, -0.0051}),
            (ws::PositionVoxelKey{-1, 0, -2}));
}

TEST(PoseCoverageIndex, QuaternionSignDoesNotCreateASecondOrientation)
{
  ws::PoseCoverageIndex index(0.005, radians(10.0));
  auto first = sampleAt(0.1, 0.2, 0.3, {0.0, 0.0, 0.0, 1.0});
  auto second = sampleAt(0.1, 0.2, 0.3, {0.0, 0.0, 0.0, -1.0});
  index.insert(first);
  index.insert(second);
  EXPECT_EQ(first.orientation_cluster_id, second.orientation_cluster_id);
  EXPECT_EQ(index.voxelSummaries().front().orientation_count, 1U);
}

TEST(PoseCoverageIndex, RequiresBothRatesToStayLowForFiveBatches)
{
  ws::ConvergenceTracker tracker(fullConfig());
  for (int batch = 0; batch < 4; ++batch)
    EXPECT_FALSE(tracker.observe({1, 1, 10000, 10000}, 300000 + batch * 25000));
  EXPECT_TRUE(tracker.observe({1, 1, 10000, 10000}, 400000));
}
```

- [ ] **Step 2: Run RED test**

```bash
colcon build --packages-select so101_gazebo_demo --symlink-install
```

Expected: missing `PoseCoverageIndex` and `ConvergenceTracker` declarations.

- [ ] **Step 3: Implement fixed-representative angular clustering and rate tracking**

```cpp
double quaternionAngularDistance(const std::array<double, 4> & a,
                                 const std::array<double, 4> & b)
{
  const double dot = std::abs(
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]);
  return 2.0 * std::acos(std::clamp(dot, 0.0, 1.0));
}

PositionVoxelKey PoseCoverageIndex::keyFor(const std::array<double, 3> & xyz) const
{
  return {checkedInt32(std::floor(xyz[0] / voxel_size_)),
          checkedInt32(std::floor(xyz[1] / voxel_size_)),
          checkedInt32(std::floor(xyz[2] / voxel_size_))};
}
```

Keep cluster representatives fixed at their first sample quaternion. Search all representatives in increasing cluster ID, choose minimum angular distance, and break exact ties by smaller ID. Maintain separate all/free orientation counts while assigning one stable cluster ID per sample.

- [ ] **Step 4: Run focused tests**

```bash
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
colcon test --packages-select so101_gazebo_demo --ctest-args -R '^test_pose_coverage_index$' --output-on-failure
```

Expected: voxel, quaternion, clustering, batch-rate, checkpoint, and refinement-priority tests pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add -- src/so101_gazebo_demo/CMakeLists.txt src/so101_gazebo_demo/include/so101_gazebo_demo/workspace/pose_coverage_index.hpp src/so101_gazebo_demo/src/workspace/pose_coverage_index.cpp src/so101_gazebo_demo/test/workspace/test_pose_coverage_index.cpp
git commit -m "feat(so101): track TCP pose coverage"
```

---

### Task 4: Evaluate FK and Offline Planning Scene Collisions

**Files:**
- Create: `src/so101_gazebo_demo/include/so101_gazebo_demo/workspace/workspace_state_evaluator.hpp`
- Create: `src/so101_gazebo_demo/src/workspace/workspace_state_evaluator.cpp`
- Create: `src/so101_gazebo_demo/test/workspace/test_workspace_state_evaluator.cpp`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`

**Interfaces:**
- Consumes: `GeneratedJointSample`, `PoseSample`, `pick_place::SO101Profile`, `makeTableCollisionObject`, `makePedestalCollisionObject`.
- Produces: `WorkspaceEvaluatorBuildResult {std::unique_ptr<WorkspaceStateEvaluator> evaluator; std::optional<WorkspaceFailure> failure;}` and `WorkspaceStateEvaluator::create(node, profile) -> WorkspaceEvaluatorBuildResult`.
- Produces: `PoseSample evaluate(sample_id, generated)` and `const CollisionPairCounts & collisionPairCounts() const`.

```cpp
using CollisionPairCounts = std::map<std::pair<std::string, std::string>, std::uint64_t>;

struct WorkspaceEvaluatorBuildResult
{
  std::unique_ptr<class WorkspaceStateEvaluator> evaluator;
  std::optional<WorkspaceFailure> failure;
};

class WorkspaceStateEvaluator
{
public:
  static WorkspaceEvaluatorBuildResult create(
    const std::shared_ptr<rclcpp::Node> & node,
    const pick_place::SO101Profile & profile);
  PoseSample evaluate(std::uint64_t sample_id, const GeneratedJointSample & generated);
  const CollisionPairCounts & collisionPairCounts() const noexcept;
  std::vector<std::string> worldObjectIds() const;
};
```

- [ ] **Step 1: Write failing model and scene contract tests**

```cpp
TEST(WorkspaceStateEvaluator, UsesFiveArmJointsAndFixedPreopen)
{
  auto evaluator = makeEvaluatorFromFixtureModel();
  const auto sample = evaluator.evaluate(7, generated({0, 0, 0, 0, 0}));
  EXPECT_EQ(sample.arm_joints.size(), 5U);
  EXPECT_DOUBLE_EQ(sample.gripper_q6, spp::SO101Profile::canonical().q6_preopen);
  EXPECT_TRUE(allFinite(sample.tcp_pose));
}

TEST(WorkspaceStateEvaluator, SceneContainsTableAndPedestalButNotCup)
{
  auto evaluator = makeEvaluatorFromFixtureModel();
  const auto ids = evaluator.worldObjectIds();
  EXPECT_EQ(ids, (std::vector<std::string>{"base_pedestal", "table"}));
}

TEST(WorkspaceStateEvaluator, Q6DoesNotChangeTcpPose)
{
  const auto model = fixtureModel();
  EXPECT_TRUE(tcpPoseEqualAtQ6(model, 0.465038, 1.7, 1e-12));
}
```

Add a test-only `discoverFixtureStates` helper that scans Halton indices `1..200000`, records the first state in each exact category (`free`, `self-only`, `table`, `pedestal`), and prints `index,q1,q2,q3,q4,q5`. Run the focused test once with `SO101_DISCOVER_WORKSPACE_FIXTURES=1`; copy the four printed vectors and the fixture-model SHA-256 into `constexpr` test data, remove the environment-variable branch, then make ordinary test execution compare each frozen vector with a direct `PlanningScene` query. This is a one-time calibration inside Task 4, not runtime sampler behavior.

- [ ] **Step 2: Run RED test**

```bash
colcon build --packages-select so101_gazebo_demo --symlink-install
```

Expected: missing evaluator and local scene builder.

- [ ] **Step 3: Implement model validation and a process-local Planning Scene**

```cpp
auto scene = std::make_shared<planning_scene::PlanningScene>(model);
const spp::MoveItSceneGeometry geometry{
  profile.world_frame, profile.table_object, profile.table_size,
  profile.pedestal_object, profile.pedestal_size,
  profile.task_object_id, profile.task_object_height,
  profile.task_object_outer_radius, profile.task_object_wall_thickness,
  profile.task_object_bottom_thickness, profile.task_object_side_count};
if (!scene->processCollisionObjectMsg(spp::makeTableCollisionObject(geometry, profile.table_pose)))
  return failure("scene_table_insert_failed");
if (!scene->processCollisionObjectMsg(
      spp::makePedestalCollisionObject(geometry, profile.pedestal_pose)))
  return failure("scene_pedestal_insert_failed");
```

Validate that the model group variable names equal `profile.arm_joints`, TCP exists, q6 exists and preopen satisfies bounds. Set `request.contacts=true`, `max_contacts=256`, and `max_contacts_per_pair=1`.

- [ ] **Step 4: Implement independent self/world classification**

```cpp
scene_->checkSelfCollision(self_request, self_result, state, scene_->getAllowedCollisionMatrix());
scene_->checkCollision(full_request, full_result, state, scene_->getAllowedCollisionMatrix());
sample.self_collision = self_result.collision;
sample.scene_collision = false;
for (const auto & entry : full_result.contacts) {
  const auto & first = entry.first.first;
  const auto & second = entry.first.second;
  if (first == profile_.table_object || second == profile_.table_object ||
      first == profile_.pedestal_object || second == profile_.pedestal_object) {
    sample.scene_collision = true;
  }
}
sample.collision_free = sample.bounds_valid && !sample.self_collision && !sample.scene_collision;
```

Fail if a full collision contact contains an unknown world object. Convert Eigen transform to a normalized, canonicalized quaternion and reject NaN/Inf rather than skipping the sample.

- [ ] **Step 5: Build and run evaluator tests**

```bash
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
colcon test --packages-select so101_gazebo_demo --ctest-args -R '^test_workspace_state_evaluator$' --output-on-failure
```

Expected: model contract, golden FK, exact world IDs, free/self/table/pedestal classification, q6 invariance, and failure-path tests pass.

- [ ] **Step 6: Commit Task 4**

```bash
git add -- src/so101_gazebo_demo/CMakeLists.txt src/so101_gazebo_demo/include/so101_gazebo_demo/workspace/workspace_state_evaluator.hpp src/so101_gazebo_demo/src/workspace/workspace_state_evaluator.cpp src/so101_gazebo_demo/test/workspace/test_workspace_state_evaluator.cpp
git commit -m "feat(so101): evaluate offline workspace collisions"
```

---

### Task 5: Write Atomic CSV and Binary PLY Batch Chunks

**Files:**
- Create: `src/so101_gazebo_demo/include/so101_gazebo_demo/workspace/workspace_artifact_writer.hpp`
- Create: `src/so101_gazebo_demo/src/workspace/workspace_artifact_writer.cpp`
- Create: `src/so101_gazebo_demo/test/workspace/test_workspace_artifact_writer.cpp`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`

**Interfaces:**
- Consumes: `PoseSample`, `PositionVoxelSummary`, `BatchCoverageDelta`.
- Produces: `CommittedBatch {batch_number, sample_count, csv_path, all_ply_path, free_ply_path, sha256}`.
- Produces: `WorkspaceArtifactWriter::writeBatch(batch_number,samples)` and `finalize(committed_batches,voxel_summaries)`.

```cpp
struct CommittedBatch
{
  std::uint64_t batch_number;
  std::uint64_t sample_count;
  std::uint64_t collision_free_count;
  std::filesystem::path csv_path;
  std::filesystem::path all_ply_path;
  std::filesystem::path free_ply_path;
  std::map<std::string, std::string> sha256_by_file;
};

struct FinalArtifacts
{
  WorkspaceArtifactPaths paths;
  std::uint64_t total_vertices;
  std::uint64_t collision_free_vertices;
  std::uint64_t position_voxels;
};

class WorkspaceArtifactWriter
{
public:
  explicit WorkspaceArtifactWriter(std::filesystem::path output_directory);
  CommittedBatch writeBatch(std::uint64_t batch_number,
                            const std::vector<PoseSample> & samples);
  FinalArtifacts finalize(const std::vector<CommittedBatch> & batches,
                          const std::vector<PositionVoxelSummary> & voxels);
};
```

- [ ] **Step 1: Write failing schema and atomicity tests**

```cpp
TEST(WorkspaceArtifactWriter, CsvIsTheDoublePrecisionCanonicalRecord)
{
  const auto output = temporaryOutputDirectory();
  ws::WorkspaceArtifactWriter writer(output);
  const auto committed = writer.writeBatch(1, twoSamples());
  const auto rows = readCsv(committed.csv_path);
  EXPECT_EQ(rows.size(), 2U);
  EXPECT_EQ(rows[0].at("sample_id"), "1");
  EXPECT_EQ(rows[0].at("q6"), "0.465038000000000");
  EXPECT_EQ(rows[0].at("collision_free"), "1");
}

TEST(WorkspaceArtifactWriter, PlyUsesApprovedPortablePropertyTypes)
{
  const auto header = writeAndReadAllPlyHeader(twoSamples());
  EXPECT_THAT(header, HasSubstr("format binary_little_endian 1.0"));
  EXPECT_THAT(header, HasSubstr("property uint sample_id"));
  EXPECT_THAT(header, HasSubstr("property uchar sample_source"));
  EXPECT_THAT(header, HasSubstr("property double x"));
  EXPECT_THAT(header, HasSubstr("property float qx"));
  EXPECT_THAT(header, HasSubstr("property int position_voxel_x"));
}
```

Add a fault-injected stream test: failure before rename leaves no committed batch and one `.partial` file.

- [ ] **Step 2: Run RED test**

```bash
colcon build --packages-select so101_gazebo_demo --symlink-install
```

Expected: writer types and binary PLY encoder are missing.

- [ ] **Step 3: Implement fixed CSV columns and PLY encoding**

```cpp
constexpr std::string_view kCsvHeader =
  "sample_id,sample_source,q1,q2,q3,q4,q5,q6,tcp_x,tcp_y,tcp_z,"
  "tcp_qx,tcp_qy,tcp_qz,tcp_qw,bounds_valid,self_collision,scene_collision,"
  "collision_free,position_voxel_x,position_voxel_y,position_voxel_z,"
  "orientation_cluster_id\n";

template<typename T>
void writeLittleEndian(std::ostream & stream, T value)
{
  static_assert(std::is_trivially_copyable_v<T>);
  std::array<std::byte, sizeof(T)> bytes;
  std::memcpy(bytes.data(), &value, sizeof(T));
  const std::uint16_t marker = 1;
  const bool host_is_little_endian =
    *reinterpret_cast<const std::uint8_t *>(&marker) == 1;
  if (!host_is_little_endian)
    std::reverse(bytes.begin(), bytes.end());
  stream.write(reinterpret_cast<const char *>(bytes.data()), bytes.size());
}
```

Keep this C++17 byte-order check in one private helper and test it by decoding the produced bytes as little-endian. Write CSV doubles with `std::setprecision(15)`. Write each file in `chunks/*.partial`, close and verify stream state, then rename within the same output filesystem.

- [ ] **Step 4: Implement streaming final merge**

Read only PLY headers and stream vertex payloads in batch order into a final `.partial`; calculate total vertices from committed metadata before writing the final header. Generate `position_voxels.ply` from summaries with all/free counts. Atomically rename all finals only after all three validate.

- [ ] **Step 5: Run writer tests**

```bash
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
colcon test --packages-select so101_gazebo_demo --ctest-args -R '^test_workspace_artifact_writer$' --output-on-failure
```

Expected: schema, type, row/vertex count, free-subset, merge order, failure atomicity, and empty-directory tests pass.

- [ ] **Step 6: Commit Task 5**

```bash
git add -- src/so101_gazebo_demo/CMakeLists.txt src/so101_gazebo_demo/include/so101_gazebo_demo/workspace/workspace_artifact_writer.hpp src/so101_gazebo_demo/src/workspace/workspace_artifact_writer.cpp src/so101_gazebo_demo/test/workspace/test_workspace_artifact_writer.cpp
git commit -m "feat(so101): write workspace sample artifacts"
```

---

### Task 6: Add Provenance, Checkpoint, and Resume Validation

**Files:**
- Create: `src/so101_gazebo_demo/include/so101_gazebo_demo/workspace/workspace_checkpoint_store.hpp`
- Create: `src/so101_gazebo_demo/src/workspace/workspace_checkpoint_store.cpp`
- Create: `src/so101_gazebo_demo/test/workspace/test_workspace_checkpoint_store.cpp`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`

**Interfaces:**
- Consumes: generator/coverage checkpoints, `CommittedBatch`, config, normalized expanded URDF/SRDF strings, canonical scene serialization.
- Produces: `WorkspaceProvenance`, `WorkspaceCheckpoint`, `ResumeDecision`.
- Produces: `sha256(string_view)`, `writeCheckpointAtomically`, `loadCheckpoint`, `validateResume`, `snapshotCompletedFinals`.

```cpp
struct WorkspaceProvenance
{
  std::string urdf_sha256;
  std::string srdf_sha256;
  std::string scene_sha256;
  std::string config_sha256;
  std::string executable_sha256;
  std::string package_prefix;
};

struct WorkspaceCheckpoint
{
  std::uint32_t schema_version{1};
  WorkspaceProvenance provenance;
  GeneratorCheckpoint generator;
  PoseCoverageCheckpoint coverage;
  std::vector<CommittedBatch> committed_batches;
  std::uint64_t next_sample_id{0};
  std::uint64_t next_batch_number{1};
  std::uint64_t completed_samples{0};
  StopReason stop_reason{StopReason::INTERRUPTED};
};

struct ResumeDecision
{
  bool allowed;
  std::string code;
  std::string message;
};

class WorkspaceCheckpointStore
{
public:
  WorkspaceCheckpointStore(std::filesystem::path output_directory,
                           WorkspaceProvenance expected_provenance);
  void writeCheckpointAtomically(const WorkspaceCheckpoint & checkpoint);
  WorkspaceCheckpoint loadCheckpoint() const;
  ResumeDecision validateResume(const WorkspaceCheckpoint & checkpoint) const;
  void prepareResumeDirectory(const WorkspaceCheckpoint & checkpoint) const;
};
```

- [ ] **Step 1: Write failing hash and mismatch tests**

```cpp
TEST(WorkspaceCheckpointStore, RejectsEveryProvenanceMismatch)
{
  const auto expected = provenance("urdf-a", "srdf-a", "scene-a", "config-a");
  for (const auto & actual : {
         provenance("urdf-b", "srdf-a", "scene-a", "config-a"),
         provenance("urdf-a", "srdf-b", "scene-a", "config-a"),
         provenance("urdf-a", "srdf-a", "scene-b", "config-a"),
         provenance("urdf-a", "srdf-a", "scene-a", "config-b")}) {
    const auto decision = ws::validateResume(expected, actual, ws::StopReason::INTERRUPTED);
    EXPECT_FALSE(decision.allowed);
    EXPECT_EQ(decision.code, "checkpoint_mismatch");
  }
}

TEST(WorkspaceCheckpointStore, BudgetExhaustedMayContinueButConvergedMayNot)
{
  const auto value = provenance("u", "s", "w", "c");
  EXPECT_TRUE(ws::validateResume(value, value, ws::StopReason::BUDGET_EXHAUSTED).allowed);
  EXPECT_FALSE(
    ws::validateResume(value, value,
                       ws::StopReason::CONVERGED_AT_CONFIGURED_RESOLUTION).allowed);
}
```

- [ ] **Step 2: Run RED test**

```bash
colcon build --packages-select so101_gazebo_demo --symlink-install
```

Expected: checkpoint/provenance API is missing.

- [ ] **Step 3: Implement canonical JSON hashing and atomic checkpoints**

```cpp
nlohmann::ordered_json canonicalConfigJson(const WorkspaceSamplingConfig & config)
{
  return {{"batch_size", config.batch_size},
          {"maximum_samples", config.maximum_samples},
          {"minimum_samples", config.minimum_samples},
          {"orientation_new_rate_threshold", config.orientation_new_rate_threshold},
          {"orientation_threshold_rad", config.orientation_threshold_rad},
          {"position_new_rate_threshold", config.position_new_rate_threshold},
          {"position_voxel_size_m", config.position_voxel_size_m},
          {"stable_batches", config.stable_batches},
          {"time_budget_seconds", config.time_budget.count()}};
}
```

Hash `ordered_json.dump()` and exact expanded URDF/SRDF bytes. Checkpoint JSON must contain schema version, next global/local indices, refinement state, coverage state, committed chunk paths/counts/hashes, completed samples, last batch, provenance, and stop reason. Write `checkpoint.json.partial`, fsync/close, then rename.

- [ ] **Step 4: Implement resume directory transitions**

For interrupted runs, ignore `.partial` files and move them to `orphaned/` before resuming. For `budget_exhausted`, atomically move current finals into `snapshots/<completed-sample-count>/`; do not publish replacement finals until finalization succeeds. Reject failed, converged, sample-cap, nonempty-without-resume, and any changed config.

- [ ] **Step 5: Run checkpoint tests**

```bash
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
colcon test --packages-select so101_gazebo_demo --ctest-args -R '^test_workspace_checkpoint_store$' --output-on-failure
```

Expected: hash, schema, atomic write, orphan handling, budget snapshot, stop-state, and all mismatch tests pass.

- [ ] **Step 6: Commit Task 6**

```bash
git add -- src/so101_gazebo_demo/CMakeLists.txt src/so101_gazebo_demo/include/so101_gazebo_demo/workspace/workspace_checkpoint_store.hpp src/so101_gazebo_demo/src/workspace/workspace_checkpoint_store.cpp src/so101_gazebo_demo/test/workspace/test_workspace_checkpoint_store.cpp
git commit -m "feat(so101): add resumable workspace checkpoints"
```

---

### Task 7: Orchestrate Batches and Stop Semantics

**Files:**
- Create: `src/so101_gazebo_demo/include/so101_gazebo_demo/workspace/workspace_sampler.hpp`
- Create: `src/so101_gazebo_demo/src/workspace/workspace_sampler.cpp`
- Create: `src/so101_gazebo_demo/test/workspace/test_workspace_sampler.cpp`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`

**Interfaces:**
- Consumes: generator, evaluator, coverage, writer, checkpoint store, config.
- Produces: `WorkspaceSampler::run(const RunControl &) -> RunSummary`.
- Produces: `RunControl {now, stop_requested}` injectable callbacks for deterministic tests and SIGINT-safe batch boundaries.

```cpp
struct RunControl
{
  std::function<std::chrono::steady_clock::time_point()> now;
  std::function<bool()> stop_requested;
};

class WorkspaceSampler
{
public:
  WorkspaceSampler(WorkspaceSamplingConfig config, JointSampleGenerator generator,
                   WorkspaceStateEvaluator & evaluator, PoseCoverageIndex coverage,
                   WorkspaceArtifactWriter & writer,
                   WorkspaceCheckpointStore & checkpoint_store);
  RunSummary run(const RunControl & control);
};
```

- [ ] **Step 1: Write failing fixed-count, convergence, budget, and resume tests**

```cpp
TEST(WorkspaceSampler, FixedSampleRunIsIdenticalAfterBatchBoundaryResume)
{
  const auto uninterrupted = runFixtureSampler(output("one"), fixedCountConfig(500), noStop());
  const auto interrupted = runFixtureSampler(output("two"), fixedCountConfig(500), stopAfter(2));
  ASSERT_EQ(interrupted.stop_reason, ws::StopReason::INTERRUPTED);
  const auto resumed = resumeFixtureSampler(output("two"), fixedCountConfig(500));
  ASSERT_TRUE(uninterrupted.artifacts);
  ASSERT_TRUE(resumed.artifacts);
  EXPECT_EQ(readBytes(uninterrupted.artifacts->samples_csv),
            readBytes(resumed.artifacts->samples_csv));
  EXPECT_EQ(normalizedSummary(uninterrupted), normalizedSummary(resumed));
}

TEST(WorkspaceSampler, BudgetExhaustionIsSuccessfulOnlyAfterMinimumSamples)
{
  EXPECT_EQ(runWithClock(minimumReachedClock()).stop_reason,
            ws::StopReason::BUDGET_EXHAUSTED);
  EXPECT_EQ(runWithClock(minimumMissedClock()).failure_code,
            "minimum_samples_not_reached");
}
```

- [ ] **Step 2: Run RED test**

```bash
colcon build --packages-select so101_gazebo_demo --symlink-install
```

Expected: orchestration API is missing.

- [ ] **Step 3: Implement exact per-batch order**

```cpp
while (summary.completed_samples < config.maximum_samples) {
  if (control.stop_requested())
    return stopAfterCommittedBatch(StopReason::INTERRUPTED);
  const auto batch = generateNextBatch();
  std::vector<PoseSample> evaluated;
  evaluated.reserve(batch.size());
  for (const auto & generated : batch) {
    auto sample = evaluator.evaluate(next_sample_id++, generated);
    coverage.insert(sample);
    evaluated.push_back(std::move(sample));
  }
  const auto delta = coverage.finishBatch();
  const auto committed = writer.writeBatch(next_batch_number++, evaluated);
  checkpoint.committed_batches.push_back(committed);
  checkpoint.completed_samples += evaluated.size();
  checkpoint.generator = generator.checkpoint();
  checkpoint.coverage = coverage.checkpoint();
  checkpoint_store.writeCheckpointAtomically(checkpoint);
  updateStopDecision(delta, control.now());
}
```

Do not checkpoint sample/coverage state before its files are committed. Generate first two batches 100% global; later batches use 80% global and 20% deterministic refinement. Finalize only after a valid stop reason.

- [ ] **Step 4: Implement summary and failure mapping**

`converged_at_configured_resolution`, `sample_cap_reached`, and valid `budget_exhausted` finalize and return success. Interrupt persists checkpoint but leaves no final artifacts and returns nonzero. Any evaluator/writer/checkpoint exception maps to a stable code, writes incomplete summary, preserves committed chunks, and returns nonzero.

- [ ] **Step 5: Run sampler tests**

```bash
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
colcon test --packages-select so101_gazebo_demo --ctest-args -R '^test_workspace_sampler$' --output-on-failure
```

Expected: fixed-count determinism, batch ordering, 80/20 allocation, stop reasons, min gate, interrupt, writer failure, and resume equality pass.

- [ ] **Step 6: Commit Task 7**

```bash
git add -- src/so101_gazebo_demo/CMakeLists.txt src/so101_gazebo_demo/include/so101_gazebo_demo/workspace/workspace_sampler.hpp src/so101_gazebo_demo/src/workspace/workspace_sampler.cpp src/so101_gazebo_demo/test/workspace/test_workspace_sampler.cpp
git commit -m "feat(so101): orchestrate offline workspace sampling"
```

---

### Task 8: Add the ROS Node, Launch Contract, and Installed Entry Point

**Files:**
- Create: `src/so101_gazebo_demo/src/nodes/sample_so101_workspace.cpp`
- Create: `src/so101_gazebo_demo/launch/so101_workspace_sample.launch.py`
- Create: `src/so101_gazebo_demo/test/test_workspace_launch_contract.py`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`
- Modify: `src/so101_gazebo_demo/package.xml`
- Modify: `src/so101_gazebo_demo/test/test_package_layout.py`

**Interfaces:**
- Consumes: `WorkspaceSampler`, `configForProfile`, `RobotModelLoader`, installed Xacro/SRDF.
- Produces: executable `sample_so101_workspace` and public launch `so101_workspace_sample.launch.py`.

- [ ] **Step 1: Write failing launch and package-layout tests**

```python
def test_workspace_launch_starts_only_the_offline_sampler():
    description = load_launch_description(WORKSPACE_SAMPLE_LAUNCH)
    nodes = [entity for entity in description.entities if isinstance(entity, Node)]
    assert len(nodes) == 1
    assert nodes[0].node_package == 'so101_gazebo_demo'
    assert nodes[0].node_executable == 'sample_so101_workspace'
    source = WORKSPACE_SAMPLE_LAUNCH.read_text()
    assert 'moveit_ros_move_group' not in source
    assert 'ros_gz' not in source


def test_workspace_launch_declares_approved_public_arguments():
    assert {
        'output_dir', 'profile', 'resume', 'time_budget_seconds', 'batch_size',
        'minimum_samples', 'maximum_samples', 'position_voxel_size_m',
        'orientation_threshold_deg', 'stable_batches',
        'position_new_rate_threshold', 'orientation_new_rate_threshold',
        'base_height', 'object_config',
    } <= declared_arguments(WORKSPACE_SAMPLE_LAUNCH)
```

Add package-layout assertions for the executable target, installed launch, and `moveit_core`/`moveit_ros_planning` dependencies.

- [ ] **Step 2: Run RED Python contract tests**

```bash
cd /data/work/ws_moveit/src/so101_gazebo_demo
PYTHONNOUSERSITE=1 python3 -m pytest test/test_workspace_launch_contract.py test/test_package_layout.py -q
```

Expected: missing launch and executable/package contract assertions fail.

- [ ] **Step 3: Implement launch with descriptions but no move_group**

```python
moveit_config = (
    MoveItConfigsBuilder('so101', package_name='so101_gazebo_demo')
    .robot_description(
        file_path=str(package_share / 'urdf' / 'so101.urdf.xacro'),
        mappings={
            'base_height': LaunchConfiguration('base_height'),
            'object_config': LaunchConfiguration('object_config'),
        },
    )
    .robot_description_semantic(
        file_path=str(package_share / 'config' / 'so101.srdf')
    )
    .to_moveit_configs()
)

sampler = Node(
    package='so101_gazebo_demo',
    executable='sample_so101_workspace',
    output='screen',
    parameters=[
        moveit_config.robot_description,
        moveit_config.robot_description_semantic,
        {'output_dir': LaunchConfiguration('output_dir')},
        {'profile': LaunchConfiguration('profile')},
        {'resume': LaunchConfiguration('resume')},
    ],
)
```

Pass every declared sampler override explicitly. Set `output_dir` with no default so launch requires it. Defaults must match Task 1.

- [ ] **Step 4: Implement node composition and exit mapping**

Use `rclcpp::remove_ros_arguments`, declare/read typed parameters, require an absolute output path, load the RobotModel from parameters with kinematics solvers disabled, build provenance, and run synchronously. `rclcpp::ok()` is the stop callback. Print one final machine-readable line:

```text
WORKSPACE_RESULT status=success stop_reason=budget_exhausted samples=250000 output=/tmp/so101-workspace-full
```

Map converged/sample-cap/valid-budget to exit 0; interrupted/config/model/scene/I/O/minimum failures to nonzero.

- [ ] **Step 5: Wire CMake install and quality gate**

Add the executable, link `so101_workspace_sampling` and `pick_place_core`, add `ament_index_cpp`/`rclcpp`, include it in the existing `install(TARGETS)` block and C++ quality-gate target list. Do not add Python runtime dependencies.

- [ ] **Step 6: Run contract and help-path tests**

```bash
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
PYTHONNOUSERSITE=1 python3 -m pytest src/so101_gazebo_demo/test/test_workspace_launch_contract.py src/so101_gazebo_demo/test/test_package_layout.py -q
ros2 launch so101_gazebo_demo so101_workspace_sample.launch.py --show-args
```

Expected: one sampler node, all arguments/defaults, no move_group/Gazebo references, installed executable and help contract pass.

- [ ] **Step 7: Commit Task 8**

```bash
git add -- src/so101_gazebo_demo/CMakeLists.txt src/so101_gazebo_demo/package.xml src/so101_gazebo_demo/src/nodes/sample_so101_workspace.cpp src/so101_gazebo_demo/launch/so101_workspace_sample.launch.py src/so101_gazebo_demo/test/test_workspace_launch_contract.py src/so101_gazebo_demo/test/test_package_layout.py
git commit -m "feat(so101): add workspace sampler launch"
```

---

### Task 9: Add End-to-End Test Profile and Operator Documentation

**Files:**
- Create: `src/so101_gazebo_demo/test/workspace/test_workspace_sampler_integration.cpp`
- Create: `src/so101_gazebo_demo/docs/so101-workspace-sampler.md`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`
- Modify: `src/so101_gazebo_demo/test/test_package_layout.py`
- Modify: `src/so101_gazebo_demo/README.md`

**Interfaces:**
- Consumes: installed sampler launch and all public artifacts.
- Produces: fixed 10000-sample integration acceptance and user-facing quick/full/resume/CloudCompare instructions.

- [ ] **Step 1: Write the failing integration artifact test**

```cpp
TEST(WorkspaceSamplerIntegration, TenThousandSamplesProduceConsistentArtifacts)
{
  const auto result = runInstalledFixtureModelSampler(10000);
  ASSERT_EQ(result.exit_code, 0);
  EXPECT_EQ(csvRowCount(result.samples_csv), 10000U);
  EXPECT_EQ(plyVertexCount(result.all_poses_ply), 10000U);
  EXPECT_EQ(plyVertexCount(result.collision_free_poses_ply),
            csvCollisionFreeCount(result.samples_csv));
  EXPECT_EQ(result.manifest.at("completed_samples"), 10000U);
  EXPECT_EQ(result.manifest.at("scene_objects"),
            (nlohmann::json::array({"base_pedestal", "table"})));
}
```

Add an interrupted-at-batch-2 run and resume; compare canonical CSV and PLY bytes with uninterrupted output. Normalize only manifest timestamps, hostname, elapsed time, and peak memory.

- [ ] **Step 2: Run integration RED**

```bash
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
colcon test --packages-select so101_gazebo_demo --ctest-args -R '^test_workspace_sampler_integration$' --output-on-failure
```

Expected: test fails on a missing integration fixture hook or incomplete manifest/artifact contract.

- [ ] **Step 3: Complete only the integration seams required by the test**

Add a test-only fixed-count config constructor and batch-boundary stop callback to the existing library test support; do not expose them as public launch arguments. Ensure final CSV/PLY byte order is batch-number then sample ID.

- [ ] **Step 4: Write operator documentation with exact commands**

Document:

```bash
ros2 launch so101_gazebo_demo so101_workspace_sample.launch.py \
  output_dir:=/tmp/so101-workspace-quick profile:=quick

ros2 launch so101_gazebo_demo so101_workspace_sample.launch.py \
  output_dir:=/tmp/so101-workspace-full profile:=full

ros2 launch so101_gazebo_demo so101_workspace_sample.launch.py \
  output_dir:=/tmp/so101-workspace-full profile:=full resume:=true
```

Explain each artifact, CloudCompare scalar fields, `converged` versus `budget_exhausted`, fixed preopen/table/pedestal assumptions, and why the result does not prove path or real-hardware safety.

- [ ] **Step 5: Run focused and package tests**

```bash
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo --event-handlers console_direct+
colcon test-result --verbose
```

Expected: integration test and the complete package suite pass with zero new failures.

- [ ] **Step 6: Commit Task 9**

```bash
git add -- src/so101_gazebo_demo/CMakeLists.txt src/so101_gazebo_demo/README.md src/so101_gazebo_demo/docs/so101-workspace-sampler.md src/so101_gazebo_demo/test/workspace/test_workspace_sampler_integration.cpp src/so101_gazebo_demo/test/test_package_layout.py
git commit -m "test(so101): validate offline workspace sampler"
```

---

### Task 10: Run ai-station Full Acceptance and Fresh Visual Review

**Files:**
- No source files changed.
- Runtime evidence only: `/tmp/so101-workspace-acceptance-<timestamp>/`.
- Mac visual evidence only: copied final PLY files and a fresh CloudCompare screenshot.

**Interfaces:**
- Consumes: installed artifacts from Tasks 1-9.
- Produces: evidence-backed acceptance report; no code commit.

- [ ] **Step 1: Inventory source/install/process provenance before running**

```bash
cd /data/work/ws_moveit
git status --short
git rev-parse HEAD
ros2 pkg prefix so101_gazebo_demo
ros2 pkg executables so101_gazebo_demo | rg sample_so101_workspace
pgrep -af 'move_group|rviz2|gz sim|controller_manager|sample_so101_workspace'
tmux list-sessions
```

Record existing PIDs, ROS_DOMAIN_ID, GZ_PARTITION, branch, commit, dirty files, and package prefix. Do not stop or replace user-owned processes.

- [ ] **Step 2: Rebuild, source, and run the complete package gate**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo --event-handlers console_direct+
colcon test-result --verbose
```

Expected: build succeeds; package test result has zero errors and zero failures attributable to this change. If the baseline already has unrelated failures, run the same test command on the pre-feature baseline and report A/B rather than claiming them.

- [ ] **Step 3: Run quick acceptance into a unique evidence directory**

```bash
acceptance_dir=/tmp/so101-workspace-acceptance-$(date +%Y%m%d-%H%M%S)
ros2 launch so101_gazebo_demo so101_workspace_sample.launch.py \
  output_dir:=${acceptance_dir}/quick profile:=quick
```

Expected: exit 0 after at least 10000 samples; final result line, manifest, summary, checkpoint, CSV, three PLY files, collision-pair CSV, and committed chunks exist.

- [ ] **Step 4: Independently verify quick artifacts**

Run a read-only parser that does not call sampler library code. Assert CSV rows equal all-Ply vertices, free CSV count equals free-Ply vertices, voxel-Ply vertices equal summary position voxels, all numeric values are finite, manifest hashes are present, and scene IDs are exactly `base_pedestal,table`.

- [ ] **Step 5: Run the 30-minute full profile**

```bash
ros2 launch so101_gazebo_demo so101_workspace_sample.launch.py \
  output_dir:=${acceptance_dir}/full profile:=full
```

Expected: exit 0 with one of `converged_at_configured_resolution`, `sample_cap_reached`, or valid `budget_exhausted`; minimum samples is at least 250000. Record wall time, peak memory, all/free counts, voxel/cluster counts, AABBs, maximum horizontal radius, collision pair counts, and every batch `r_p/r_o`.

- [ ] **Step 6: Prove the sampler did not start a second runtime stack**

Repeat the PID/ROS graph inventory and compare with Step 1. The only new process during sampling may be `sample_so101_workspace` and launch parents; no new move_group, Gazebo, RViz, controller, FollowJointTrajectory action, or live Planning Scene dependency is allowed.

- [ ] **Step 7: Copy PLY files to Mac and perform fresh visual acceptance**

Open `all_poses.ply`, `collision_free_poses.ply`, and `position_voxels.ply` in CloudCompare. Color `position_voxels.ply` by `orientation_count`, confirm the overall arm-centered workspace is visible, compare geometric versus collision-free holes near table/pedestal, and save a new screenshot tied to this acceptance run.

- [ ] **Step 8: Write the final evidence report**

Use this exact result boundary:

```text
Result: PASS | NOT ACCEPTED
Source/install provenance:
Model/SRDF/scene/config/executable hashes:
Package tests and baseline A/B:
Quick artifact counts and independent-reader result:
Full stop reason, samples, free samples, voxels, orientation clusters:
Geometry/free AABB and maximum horizontal radius:
Collision-pair summary:
Convergence history:
Runtime process/ROS graph proof:
CloudCompare screenshot path and observed differences:
Preserved user changes:
Remaining limitation: current model, fixed preopen, offline table/pedestal scene, discrete approximation; not path reachability or real-hardware safety.
```

Do not create a source commit for runtime outputs.

---

## Final Review Gate

Before declaring implementation complete:

1. Run `git status --short` in both root and `moveit-demo`; explain every remaining change.
2. Run `git diff --check` for each implementation commit and `git diff d99a617..HEAD --check`.
3. Verify every implementation commit contains only its named task files.
4. Confirm the root submodule pointer remains uncommitted unless the user separately requests a root release.
5. Confirm package tests, quick run, full run, independent artifact reader, process inventory, and fresh CloudCompare screenshot all have current-run evidence.
6. Report `budget_exhausted` as valid sampled output but never as convergence.
