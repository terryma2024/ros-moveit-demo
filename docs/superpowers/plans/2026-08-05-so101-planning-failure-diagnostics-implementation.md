# SO-101 Planning-Failure Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Add opt-in SO-101 micro-lift planning-failure artifacts and a test-only, plan-only request replay harness without changing production motion, failure, recovery, checkpoint, session, or physical-validation behavior.

**Architecture:** Keep all new types in so101_gazebo_demo. Serialize the exact outgoing MoveGroup Goal and an independently observed Planning Scene into a versioned, atomically written JSON artifact; a robot-local sink remains disabled by default. Separate result classification from ROS transport for fake-outcome tests, and build replay only under BUILD_TESTING with no install rule or execution dependency.

**Tech Stack:** C++17, ROS 2 Jazzy, MoveIt 2, rclcpp_action, moveit_msgs, PlanningScene, nlohmann_json, OpenSSL SHA-256, GTest, Python launch-contract tests, CMake/ament, colcon, Gazebo Harmonic, tmux, ai-station visual capture.

## Global Constraints

- Work only in /data/work/ws_moveit/.worktrees/refactor-optimization-r3 on codex/refactor-optimization-r3. The agent already runs on AI-STATION-001 and must not SSH to itself.
- Read .agents/skills/so101-dev/SKILL.md, applicable references, root AGENTS.md, and moveit-demo/AGENTS.md before action and after context compaction.
- Never operate codex-cua. Preserve kimi, refactor, root checkout, other worktrees, and the unrelated sampler run-clang-tidy-18 process.
- Source only /opt/ros/jazzy/setup.zsh and this worktree's install/setup.zsh; never source /data/work/ws_moveit/install.
- Preserve the current two-line fresh=true diff through Task 1; its SHA-256 is f808e83b060cf3d6298f5ccd662a498f8fa7d1bcbc541ed0db559ea6139725fe.
- planning_diagnostics_dir defaults empty. Disabled mode creates no directory, artifact, warning, ROS action, or alternate branch.
- Scope is only MICRO_LIFT_WORLD_Z. Do not instrument Panda, common, or ordinary SO-101 joint planning.
- Do not change the 2 mm bound, target, tolerances, planner ID, attempts, planning time, scaling, touch links, ACM, execution call, or cancellation timing.
- Do not add retry, fallback, planner seed, scene mutation, replay execution, retention, or an installed replay entrypoint.
- Preserve public status/category/code/message, recovery, original_failure, trace, transition count, checkpoint bytes/sequence/schema, session, fingerprint, and physical-grasp sidecar.
- A writer failure only warns with PLANNING_DIAGNOSTIC_WRITE_FAILED; the original workflow failure wins.
- Replay validates session, fingerprint, request/scene hashes, and replay_scene_fingerprint, forces plan_only=true, and never instantiates or calls an executor/controller client.
- Matching request and scene do not require the same OMPL outcome. Never rewrite the original artifact.
- Use TDD and scoped commits. Do not run ament_uncrustify --reformat, push, merge, rebase, or edit another worktree.

## File Map

Create:

- src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/planning_failure_diagnostics.hpp
- src/so101_gazebo_demo/src/pick_place/planning_failure_diagnostics.cpp
- src/so101_gazebo_demo/test/pick_place/test_planning_failure_diagnostics.cpp
- src/so101_gazebo_demo/test/pick_place/planning_failure_replay.hpp
- src/so101_gazebo_demo/test/pick_place/planning_failure_replay.cpp
- src/so101_gazebo_demo/test/pick_place/planning_failure_replay_main.cpp
- src/so101_gazebo_demo/test/pick_place/test_planning_failure_replay.cpp

Modify:

- src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/moveit_joint_planning_boundary.hpp
- src/so101_gazebo_demo/src/pick_place/moveit_joint_planning_boundary.cpp
- src/so101_gazebo_demo/src/pick_place/pick_place_state_machine.cpp
- src/so101_gazebo_demo/launch/so101_pick_place.launch.py
- src/so101_gazebo_demo/test/test_so101_launch_contract.py
- src/so101_gazebo_demo/test/pick_place/test_so101_pick_place_runtime.cpp
- src/so101_gazebo_demo/test/pick_place/test_pick_place_runner.cpp
- src/so101_gazebo_demo/CMakeLists.txt
- src/so101_gazebo_demo/README.md
- docs/pick-place-launch-parameters.md

---

### Task 1: Commit the Existing Persisted-Snapshot Freshness Fix

**Files:**
- Modify: src/so101_gazebo_demo/test/pick_place/test_so101_pick_place_runtime.cpp:289-308,445-520
- Preserve: src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp:751-760

**Interfaces:** Consume IPhysicalGraspEvidenceStore::load(); produce a regression proving persisted samples become fresh WorldSnapshot inputs before validation.

- [ ] **Step 1: Reconfirm the protected diff**

    cd /data/work/ws_moveit/.worktrees/refactor-optimization-r3
    git status --short --branch
    git diff -- src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp | sha256sum
    git diff --check

Expected: only two fresh=true lines, the recorded SHA-256, and no whitespace error.

- [ ] **Step 2: Let MemoryPhysicalEvidenceStore return an optional record**

    std::optional<spp::PhysicalGraspEvidenceRecord> record;
    std::variant<spp::PhysicalGraspEvidenceRecord, spp::Failure> load() const override
    {
      if (record)
        return *record;
      return spp::Failure{spp::FailureCategory::OBSERVATION,
                          "TEST_EVIDENCE_UNUSED", "unused", {}};
    }

- [ ] **Step 3: Add MarksPersistedPhysicalSamplesFreshBeforeValidation**

Create before/after samples at WAIT_GRASP_STABLE and WAIT_MICRO_LIFT_STABLE. Increase TCP and cup Z exactly 0.002, set bilateral contact true and increasing timestamps, invoke the registered VERIFY_PHYSICAL_GRASP executor, and assert SUCCEEDED. The retained runtime failure is RED evidence for this already-present two-line fix; do not remove the user diff merely to recreate RED.

- [ ] **Step 4: Run focused GREEN**

    source /opt/ros/jazzy/setup.zsh
    colcon build --packages-select so101_gazebo_demo --symlink-install
    source install/setup.zsh
    PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo \
      --event-handlers console_direct+ \
      --ctest-args -R '^test_so101_pick_place_runtime$' --output-on-failure
    colcon test-result --test-result-base build/so101_gazebo_demo --verbose

Expected: zero failures/errors.

- [ ] **Step 5: Commit exactly two files**

    git add -- src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp \
      src/so101_gazebo_demo/test/pick_place/test_so101_pick_place_runtime.cpp
    git diff --cached --check
    git commit -m "fix(so101): validate persisted physical evidence as fresh"

---

### Task 2: Define Schema-v1 and Exact Request/Scene Serialization

**Files:**
- Create the diagnostics header, source, and test listed in File Map.
- Modify: src/so101_gazebo_demo/CMakeLists.txt:104-148,325-327

**Interfaces:**

    enum class PlanningFailureStage {
      GOAL_ACCEPT_TIMEOUT, GOAL_REJECTED, RESULT_TIMEOUT, TRANSPORT_FAILURE,
      MISSING_RESULT, MOVEIT_ERROR, EMPTY_TRAJECTORY
    };
    struct PlanningSceneContactEvidence {
      bool raw_collision{false};
      bool request_collision{false};
      std::map<std::string, std::size_t> raw_contacts;
      std::map<std::string, std::size_t> request_contacts;
    };
    struct PlanningFailureResultEvidence {
      PlanningFailureStage stage;
      ActionResult original;
      std::optional<std::int8_t> transport_result_code;
      std::optional<std::int32_t> moveit_error_code;
      std::optional<double> planning_time;
      std::vector<std::string> trajectory_joint_names;
      std::size_t trajectory_points{0};
      std::optional<double> trajectory_duration_seconds;
      std::optional<bool> cancel_acknowledged;
      std::optional<RequestScopedGoalTerminal> cancel_terminal;
    };
    struct PlanningFailureArtifact {
      std::int64_t captured_at_unix_ns;
      std::uint64_t process_sequence;
      std::string simulation_session_id;
      std::string configuration_fingerprint;
      Pose3d source_tcp_world;
      double world_z_delta_m;
      moveit_msgs::action::MoveGroup::Goal request;
      moveit_msgs::msg::PlanningScene observed_scene;
      PlanningSceneContactEvidence contacts;
      SO101Profile profile_identity;
      PlanningFailureResultEvidence result;
    };

Use these exact public helpers; keep JSON ownership and hash verification robot-local:

    using PlanningDiagnosticsJson = nlohmann::ordered_json;
    [[nodiscard]] PlanningDiagnosticsJson
    canonicalMoveGroupGoalJson(const moveit_msgs::action::MoveGroup::Goal & goal);
    [[nodiscard]] PlanningDiagnosticsJson
    canonicalPlanningSceneJson(const moveit_msgs::msg::PlanningScene & scene);
    [[nodiscard]] std::string
    replaySceneFingerprint(const moveit_msgs::msg::PlanningScene & scene);
    [[nodiscard]] std::string planningDiagnosticsSha256(std::string_view bytes);
    [[nodiscard]] std::variant<PlanningFailureArtifact, Failure>
    loadPlanningFailureArtifact(const std::filesystem::path & artifact_path);
    [[nodiscard]] std::variant<moveit_msgs::action::MoveGroup::Goal, Failure>
    reconstructMoveGroupGoal(const PlanningDiagnosticsJson & artifact_document);

canonicalMoveGroupGoalJson() contains both base64 CDR and a human-readable mirror;
canonicalPlanningSceneJson() is the full evidence representation. The stable topology subset is
private to replaySceneFingerprint(), so callers cannot accidentally substitute it for the full
scene hash.

- [ ] **Step 1: Add RED tests**

Register planning_failure_diagnostics.cpp and test_planning_failure_diagnostics. Prove: absent start velocities remain absent; CDR round-trip covers every Jazzy MotionPlanRequest and PlanningOptions field; stable scene fingerprint ignores timestamps/current feedback joints; geometry, pose, attachment, touch link, or ACM changes alter it; truncated, unsupported, or hash-mutated JSON is rejected.

- [ ] **Step 2: Run RED**

    source /opt/ros/jazzy/setup.zsh
    colcon build --packages-select so101_gazebo_demo --symlink-install \
      --cmake-args -DBUILD_TESTING=ON

Expected: missing header/functions fail compilation.

- [ ] **Step 3: Implement exact and readable representations**

Use rclcpp::Serialization<moveit_msgs::action::MoveGroup::Goal> with base64 CDR plus canonical human-readable fields. Serialize workspace, complete RobotState, every goal/path/trajectory constraint, reference trajectories, pipeline/planner/group, attempts/time/scalings/cartesian speed, and every PlanningOptions field. Empty vectors are []; unavailable values are null; do not synthesize NaN or zero velocities. Use PlanningScene::getPlanningSceneMsg() for full evidence. Hash the full scene separately from the stable replay topology subset in the spec.

- [ ] **Step 4: Run GREEN and commit**

    source install/setup.zsh
    PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo \
      --event-handlers console_direct+ \
      --ctest-args -R '^test_planning_failure_diagnostics$' --output-on-failure
    colcon test-result --test-result-base build/so101_gazebo_demo --verbose
    git add -- src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/planning_failure_diagnostics.hpp \
      src/so101_gazebo_demo/src/pick_place/planning_failure_diagnostics.cpp \
      src/so101_gazebo_demo/test/pick_place/test_planning_failure_diagnostics.cpp \
      src/so101_gazebo_demo/CMakeLists.txt
    git diff --cached --check
    git commit -m "feat(so101): define planning failure artifacts"

---

### Task 3: Add Null/File Sinks and Atomic Persistence

**Files:** Modify the Task 2 header, source, and test.

**Interfaces:**

    class IPlanningFailureDiagnosticsSink {
    public:
      virtual ~IPlanningFailureDiagnosticsSink() = default;
      virtual std::optional<Failure> record(const PlanningFailureArtifact &) = 0;
    };
    class NullPlanningFailureDiagnosticsSink final : public IPlanningFailureDiagnosticsSink {
    public:
      std::optional<Failure> record(const PlanningFailureArtifact &) override;
    };
    class FilePlanningFailureDiagnosticsSink final : public IPlanningFailureDiagnosticsSink {
    public:
      explicit FilePlanningFailureDiagnosticsSink(std::filesystem::path);
      std::optional<Failure> record(const PlanningFailureArtifact &) override;
    };
    struct PlanningFailureDiagnosticsSelection {
      std::shared_ptr<IPlanningFailureDiagnosticsSink> sink;
      std::optional<Failure> failure;
    };
    PlanningFailureDiagnosticsSelection
    selectPlanningFailureDiagnostics(const std::filesystem::path &);

- [ ] **Step 1: Add RED tests**

Test empty path/no filesystem effects; relative/file/unwritable path gives PLANNING_DIAGNOSTICS_DIR_INVALID; enabled directory is 0700; unique artifacts are 0600 and match [0-9]+-[0-9]+-micro-lift-[0-9a-f]{12}.json; existing artifacts are never overwritten; write failure gives PLANNING_DIAGNOSTIC_WRITE_FAILED without mutating input.

- [ ] **Step 2: Run RED, implement, and run GREEN**

Use O_CREAT | O_EXCL | O_WRONLY for the same-directory temporary file, write all bytes, fsync, close, then Linux renameat2(AT_FDCWD, temporary.c_str(), AT_FDCWD, final.c_str(), RENAME_NOREPLACE) and directory fsync. Treat EEXIST as a new sequence/name attempt; never fall back to overwrite-capable rename(). Catch serialization/filesystem exceptions and remove an unpublished temporary file on every failure path.

    source /opt/ros/jazzy/setup.zsh
    source install/setup.zsh
    colcon build --packages-select so101_gazebo_demo --symlink-install
    PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo \
      --event-handlers console_direct+ \
      --ctest-args -R '^test_planning_failure_diagnostics$' --output-on-failure

Expected: new assertions fail before implementation and all pass afterward.

- [ ] **Step 3: Commit**

    git add -- src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/planning_failure_diagnostics.hpp \
      src/so101_gazebo_demo/src/pick_place/planning_failure_diagnostics.cpp \
      src/so101_gazebo_demo/test/pick_place/test_planning_failure_diagnostics.cpp
    git diff --cached --check
    git commit -m "feat(so101): persist planning failures atomically"

---

### Task 4: Instrument Only the Request-Scoped Micro-Lift Boundary

**Files:**
- Modify: src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/moveit_joint_planning_boundary.hpp:36-117
- Modify: src/so101_gazebo_demo/src/pick_place/moveit_joint_planning_boundary.cpp:273-644
- Modify: src/so101_gazebo_demo/test/pick_place/test_request_scoped_goal_cancellation.cpp:19-212
- Modify: src/so101_gazebo_demo/test/pick_place/test_pick_place_runner.cpp:348-520,1040-1110

**Interfaces:**

    struct MoveItJointPlanningDiagnostics {
      std::string simulation_session_id;
      std::string configuration_fingerprint;
      std::shared_ptr<IPlanningFailureDiagnosticsSink> sink;
    };
    struct MoveItJointPlanningBoundaryOptions {
      std::string planner_id{"RRTConnectkConfigDefault"};
      double velocity_scaling{0.1};
      double acceleration_scaling{0.1};
      double state_timeout_seconds{2.0};
      std::optional<MoveItJointPlanningDiagnostics> diagnostics;
    };
    struct MicroLiftPlanningOutcome {
      ActionResult action;
      std::optional<RequestScopedGoalTerminal> terminal;
      std::optional<std::int8_t> transport_result_code;
      std::shared_ptr<moveit_msgs::action::MoveGroup::Result> result;
      std::optional<PlanningFailureStage> failure_stage;
      std::optional<bool> cancel_acknowledged;
    };
    [[nodiscard]] ActionResult
    classifyMicroLiftPlanningOutcome(const MicroLiftPlanningOutcome & outcome);
    struct MicroLiftPlanningCapture {
      moveit_msgs::action::MoveGroup::Goal request;
      moveit_msgs::msg::PlanningScene observed_scene;
      PlanningSceneContactEvidence contacts;
    };

Add this non-sending method to MoveItJointPlanningBoundary:

    [[nodiscard]] std::variant<MicroLiftPlanningCapture, ActionResult>
    captureWorldZMicroLiftPlanningRequest(const Pose3d & current_tcp_world,
                                          double world_z_delta_m);

Keep the positional constructor and delegate it to a new (node, profile, MoveItJointPlanningBoundaryOptions) constructor. Set named fields individually.

- [ ] **Step 1: Add a table-driven RED failure matrix**

Inject all seven stages, writer failure, and success. For failures assert returned status/category/code/message equal the pre-change baseline, one artifact when enabled, and zero execute calls. For success assert zero artifacts and exactly one execution of the returned trajectory. Add a runner-level comparison using Null, File, and failing sinks; assert identical original_failure, trace, transition_count, checkpoint sequence/schema, and byte-for-byte serialized checkpoint.

- [ ] **Step 2: Run RED**

    source /opt/ros/jazzy/setup.zsh
    source install/setup.zsh
    colcon build --packages-select so101_gazebo_demo --symlink-install
    PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo \
      --event-handlers console_direct+ \
      --ctest-args -R '^test_request_scoped_goal_cancellation$' --output-on-failure

- [ ] **Step 3: Implement without changing mappings**

Extract the current target/request construction into captureWorldZMicroLiftPlanningRequest(); it reads the start state and current scene but never sends, cancels, or executes. executeWorldZMicroLift() must call that method, then retain the existing single send/classify/execute path. Preserve exact public codes: goal timeout MICRO_LIFT_MOVE_GROUP_GOAL_TIMEOUT; rejection MICRO_LIFT_MOVE_GROUP_GOAL_REJECTED; result timeout MICRO_LIFT_MOVE_GROUP_RESULT_TIMEOUT unless cancellation failure wins; transport/missing/MoveIt/empty trajectory MICRO_LIFT_MOVEIT_PLAN_FAILED; execution MICRO_LIFT_MOVEIT_EXECUTION_FAILED. Under the scene mutex copy the scene, call getPlanningSceneMsg, and compute raw/request-ACM contacts without mutation. Record exactly once after a final request exists. Sink exceptions/writer failures produce a throttled warning and never alter the returned failure.

- [ ] **Step 4: Run GREEN and commit**

    PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo \
      --event-handlers console_direct+ \
      --ctest-args -R '^(test_request_scoped_goal_cancellation|test_planning_failure_diagnostics|test_pick_place_runner)$' \
      --output-on-failure
    colcon test-result --test-result-base build/so101_gazebo_demo --verbose
    git add -- src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/moveit_joint_planning_boundary.hpp \
      src/so101_gazebo_demo/src/pick_place/moveit_joint_planning_boundary.cpp \
      src/so101_gazebo_demo/test/pick_place/test_request_scoped_goal_cancellation.cpp \
      src/so101_gazebo_demo/test/pick_place/test_pick_place_runner.cpp
    git diff --cached --check
    git commit -m "feat(so101): capture micro-lift planning failures"

---

### Task 5: Wire Default-Off CLI/Launch and Documentation

**Files:**
- Modify: src/so101_gazebo_demo/src/pick_place/pick_place_state_machine.cpp:33-126,163-330
- Modify: src/so101_gazebo_demo/launch/so101_pick_place.launch.py:14-95
- Modify: src/so101_gazebo_demo/test/test_so101_launch_contract.py:169-207
- Modify: src/so101_gazebo_demo/README.md:125-150
- Modify: docs/pick-place-launch-parameters.md:33-65,102-120

**Interfaces:** Produce launch planning_diagnostics_dir default "", CLI --planning-diagnostics-dir PATH, and one startup provenance line: planning_diagnostics=disabled or planning_diagnostics_dir=<absolute path>. In the launch file add:

    def _runtime_arguments(values):
        """Return tokenized CLI arguments; omit diagnostics tokens when empty."""

    def _runtime_node(context):
        values = {
            name: LaunchConfiguration(name).perform(context)
            for name in _RUNTIME_ARGUMENTS
        }
        return [
            Node(
                package="so101_gazebo_demo",
                executable="pick_place_state_machine",
                output="screen",
                arguments=_runtime_arguments(values),
            )
        ]

The LaunchDescription contains OpaqueFunction(function=_runtime_node) instead of a directly
constructed runtime Node. _runtime_arguments() is the unit-test seam and appends exactly
["--planning-diagnostics-dir", value] only for a non-empty value.

- [ ] **Step 1: Add RED contracts**

Assert the launch default is empty, _runtime_arguments() produces no diagnostics token for "" and exactly two tokens for an absolute path, usage contains the CLI spelling, and production creates a named MoveItJointPlanningBoundaryOptions object. Assert reset/calibration/matrix call sites remain legacy and disabled. Execute _runtime_node() with a LaunchContext in the test so the OpaqueFunction path is covered rather than merely grepping source.

- [ ] **Step 2: Run RED**

    source /opt/ros/jazzy/setup.zsh
    source install/setup.zsh
    PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo \
      --event-handlers console_direct+ \
      --ctest-args -R '^test_so101_launch_contract$' --output-on-failure

- [ ] **Step 3: Implement configuration**

Import OpaqueFunction and implement the two helpers above; never pass an empty path. Parse into CliOptions. In main(), after parsing/policy loading but before runProduction() (and therefore before rclcpp::init/readiness/motion), call selectPlanningFailureDiagnostics and return exit code 2 with PLANNING_DIAGNOSTICS_DIR_INVALID on bad enabled paths. Pass the selected sink/path into runProduction(); after session resolution, set diagnostic session/fingerprint/sink through named boundary options.

- [ ] **Step 4: Update manuals**

Document empty default, example /tmp/so101-r3-planning-diagnostics/artifacts, 0700/0600 permissions, operator retention, no checkpoint/resume meaning, writer-failure preservation, no artifact on success, and test-only non-installed plan-only replay with stochastic outcome.

- [ ] **Step 5: Run GREEN and commit**

    colcon build --packages-select so101_gazebo_demo --symlink-install
    source install/setup.zsh
    PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo \
      --event-handlers console_direct+ \
      --ctest-args -R '^(test_so101_launch_contract|test_package_layout|test_source_manifest)$' \
      --output-on-failure
    ros2 launch so101_gazebo_demo so101_pick_place.launch.py --show-args | \
      rg 'planning_diagnostics_dir'
    git add -- src/so101_gazebo_demo/src/pick_place/pick_place_state_machine.cpp \
      src/so101_gazebo_demo/launch/so101_pick_place.launch.py \
      src/so101_gazebo_demo/test/test_so101_launch_contract.py \
      src/so101_gazebo_demo/README.md docs/pick-place-launch-parameters.md
    git diff --cached --check
    git commit -m "docs(so101): expose opt-in planning diagnostics"

---

### Task 6: Build a Non-Installed Replay Harness

**Files:**
- Create all four replay files listed in File Map.
- Modify: src/so101_gazebo_demo/CMakeLists.txt:325-353,464-473
- Reuse the Task 4 captureWorldZMicroLiftPlanningRequest() API; do not duplicate request construction.

**Interfaces:** Build-tree-only executable so101_planning_failure_replay supports:
- --artifact ABSOLUTE_PATH --offline
- --artifact ABSOLUTE_PATH --live-plan-only --expected-session-id ID --expected-fingerprint HASH
- --capture-current-and-inject MOVEIT_ERROR --output-dir ABSOLUTE_PATH --session-id ID --fingerprint HASH

Inside BUILD_TESTING, compile planning_failure_replay.cpp as
so101_planning_failure_replay_core, link it to so101_pick_place_runtime, and link both the
executable main and test_planning_failure_replay to that core. Do not add either replay target to
the existing install target list. The replay sources may use the MoveGroup planning action but must
not create MoveGroupInterface execution, FollowJointTrajectory, gripper-controller, Gazebo
mutation, or Planning Scene mutation clients.

- [ ] **Step 1: Add RED tests**

Add tests OfflineModeRoundTripsWithoutRos, RejectsProvenanceOrSceneMismatchBeforeSend, LiveModeForcesPlanOnly, NoCodePathOwnsExecuteOrControllerClient, and CaptureInjectionWritesOneArtifactWithoutSending. Add a CMake/source assertion that the target exists only under BUILD_TESTING and is absent from install blocks.

- [ ] **Step 2: Run RED**

    source /opt/ros/jazzy/setup.zsh
    colcon build --packages-select so101_gazebo_demo --symlink-install \
      --cmake-args -DBUILD_TESTING=ON

Expected: missing replay sources fail build.

- [ ] **Step 3: Implement offline, live, and injection modes**

Offline verifies request_sha256, scene_sha256, CDR hash, session, fingerprint, reconstructs and re-canonicalizes the exact request, and initializes no ROS. Live instantiates only the planning boundary, calls captureWorldZMicroLiftPlanningRequest() to obtain the independently observed current scene, rejects a replay_scene_fingerprint mismatch before action-client send, replaces the captured request with the artifact request, forces plan_only=true, sends once to MoveGroup, writes a separate <artifact>.replay-result.json, and owns no execute/controller API. Injection calls captureWorldZMicroLiftPlanningRequest(), feeds a synthetic MoveIt PLANNING_FAILED result to the Task 4 classifier, writes one production-format artifact, and sends/executes zero goals. Validate fingerprint as exactly 64 lowercase hexadecimal characters.

- [ ] **Step 4: Run GREEN, prove non-installation, and commit**

    source install/setup.zsh
    PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo \
      --event-handlers console_direct+ \
      --ctest-args -R '^(test_planning_failure_replay|test_planning_failure_diagnostics|test_request_scoped_goal_cancellation|test_package_layout)$' \
      --output-on-failure
    test -x build/so101_gazebo_demo/so101_planning_failure_replay
    test ! -e install/so101_gazebo_demo/lib/so101_gazebo_demo/so101_planning_failure_replay
    git add -- src/so101_gazebo_demo/test/pick_place/planning_failure_replay.hpp \
      src/so101_gazebo_demo/test/pick_place/planning_failure_replay.cpp \
      src/so101_gazebo_demo/test/pick_place/planning_failure_replay_main.cpp \
      src/so101_gazebo_demo/test/pick_place/test_planning_failure_replay.cpp \
      src/so101_gazebo_demo/CMakeLists.txt \
      src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/moveit_joint_planning_boundary.hpp \
      src/so101_gazebo_demo/src/pick_place/moveit_joint_planning_boundary.cpp
    git diff --cached --check
    git commit -m "test(so101): add plan-only failure replay harness"

---

### Task 7: Run Focused, Quality, and Three-Package Gates

**Files:** Modify only a demonstrated in-scope gate failure. Write evidence only below /tmp.

- [ ] **Step 1: Record provenance**

    cd /data/work/ws_moveit/.worktrees/refactor-optimization-r3
    evidence_dir=$(mktemp -d /tmp/so101-r3-planning-diagnostics-XXXXXX)
    printf '%s\n' "$evidence_dir" > /tmp/refactor-optimization-r3-planning-diagnostics-evidence-dir
    mkdir -p $evidence_dir/automated
    hostname | tee $evidence_dir/hostname.txt
    git rev-parse HEAD | tee $evidence_dir/head.txt
    git status --short --branch | tee $evidence_dir/git-status-before.txt
    ps -eo pid,ppid,stat,cmd | rg 'gz sim|move_group|rviz2|pick_place_state_machine|run-clang-tidy' \
      | tee $evidence_dir/processes-before.txt || true
    tmux list-sessions | tee $evidence_dir/tmux-before.txt

Expected: no R3 stack; unrelated clang-tidy and named sessions preserved.

- [ ] **Step 2: Clean-cache build and focused tests**

    source /opt/ros/jazzy/setup.zsh
    colcon build --packages-select so101_gazebo_demo --symlink-install --cmake-clean-cache \
      2>&1 | tee $evidence_dir/automated/so101-build.log
    source install/setup.zsh
    ros2 pkg prefix so101_gazebo_demo | tee $evidence_dir/automated/prefix.txt
    PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo \
      --event-handlers console_direct+ \
      --ctest-args -R '^(test_planning_failure_diagnostics|test_planning_failure_replay|test_request_scoped_goal_cancellation|test_so101_pick_place_runtime|test_so101_launch_contract|test_package_layout|test_source_manifest)$' \
      --output-on-failure 2>&1 | tee $evidence_dir/automated/focused.log
    colcon test-result --test-result-base build/so101_gazebo_demo --verbose \
      | tee $evidence_dir/automated/focused-results.txt

Expected: prefix is under the R3 worktree and zero failures/errors.

- [ ] **Step 3: Run read-only quality gates**

    PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo \
      --event-handlers console_direct+ \
      --ctest-args -R '^test_cpp_quality_gate$' \
      --output-on-failure 2>&1 | tee $evidence_dir/automated/quality.log

- [ ] **Step 4: Run fresh three-package build/test**

    source /opt/ros/jazzy/setup.zsh
    colcon build --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo \
      --symlink-install 2>&1 | tee $evidence_dir/automated/three-package-build.log
    source install/setup.zsh
    PYTHONNOUSERSITE=1 colcon test \
      --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo \
      --event-handlers console_direct+ \
      2>&1 | tee $evidence_dir/automated/three-package-tests.log
    colcon test-result --all --verbose | tee $evidence_dir/automated/three-package-results.txt

Expected: zero failures/errors. Record exact test and skipped counts; do not reuse 1203.

- [ ] **Step 5: Handle gate failures narrowly**

If a gate exposes an in-scope defect, add a RED regression, patch only its owner, rerun focused and package gates, and commit as test(so101): satisfy planning diagnostics gates. Stop on any out-of-scope defect.

---

### Task 8: Fresh SO-101 Injection/Replay, Success, Panda Regression, Visual Review, and Cleanup

**Files:** No source change expected. Store evidence under the Task 7 evidence_dir.

- [ ] **Step 1: Start exactly one owned SO-101 GUI stack**

    evidence_dir=$(cat /tmp/refactor-optimization-r3-planning-diagnostics-evidence-dir)
    test -d "$evidence_dir"
    export ROS_DOMAIN_ID=193
    export GZ_PARTITION=r3-planning-diagnostics-so101
    mkdir -p $evidence_dir/runtime/so101/artifacts $evidence_dir/visual
    ros2 node list 2>/dev/null | sort | tee $evidence_dir/runtime/so101/nodes-before.txt
    ps -eo pid,ppid,stat,cmd | rg 'gz sim|move_group|rviz2|pick_place_state_machine' \
      | tee $evidence_dir/runtime/so101/processes-before.txt || true

Stop if domain/partition ownership is ambiguous. Otherwise start tmux session r3-planning-diagnostics-so101 with gui-env, ROS Jazzy, the R3 overlay, domain 193, the selected partition, and:

    ros2 launch so101_gazebo_demo so101_pick_place.launch.py \
      start_simulation:=true headless:=false run_mode:=dry_run \
      simulation_session_id:=r3-diagnostics-so101 \
      planning_diagnostics_dir:=$evidence_dir/runtime/so101/artifacts

Require one Gazebo and one move_group. Run tile_ai_station_guis.py, require LAYOUT_OK, resolve ai-station-capture.sh with command -v, capture a fresh PNG, open it for visual inspection, and record arm/gripper/cup state. Stop if no capture command is installed; do not substitute log inference for visual evidence.

- [ ] **Step 2: Reset and execute real predecessors through stable grasp**

    source /opt/ros/jazzy/setup.zsh
    source install/setup.zsh
    ros2 run so101_gazebo_demo reset_so101_world \
      2>&1 | tee $evidence_dir/runtime/so101/reset.log
    ros2 run so101_gazebo_demo pick_place_state_machine \
      --mode execute --stop-after WAIT_GRASP_STABLE \
      --checkpoint $evidence_dir/runtime/so101/checkpoint.json \
      --session-id r3-diagnostics-so101 \
      --planning-diagnostics-dir $evidence_dir/runtime/so101/artifacts \
      2>&1 | tee $evidence_dir/runtime/so101/predecessors.log

Expected: predecessor execution is real, bilateral contact is present, checkpoint stops before MICRO_LIFT, and artifact directory is empty.

- [ ] **Step 3: Capture facts and inject one deterministic post-request failure**

Record bounded joint state, TCP TF, controller list, Gazebo cup pose/contact/attachment, MoveIt world/attached membership, checkpoint and sidecar SHA-256, and a fresh image. Extract policy_bundle_sha256 exactly, then run:

    policy_fingerprint=$(rg -o 'policy_bundle_sha256=[0-9a-f]{64}' \
      $evidence_dir/runtime/so101/predecessors.log | tail -1 | cut -d= -f2)
    test ${#policy_fingerprint} -eq 64

    build/so101_gazebo_demo/so101_planning_failure_replay \
      --capture-current-and-inject MOVEIT_ERROR \
      --output-dir $evidence_dir/runtime/so101/artifacts \
      --session-id r3-diagnostics-so101 \
      --fingerprint $policy_fingerprint \
      2>&1 | tee $evidence_dir/runtime/so101/injection.log

Expected: exactly one schema-v1 artifact, stage MOVEIT_ERROR, MoveIt PLANNING_FAILED, public MICRO_LIFT_MOVEIT_PLAN_FAILED, zero sent goals/execution, and unchanged checkpoint/sidecar bytes.

- [ ] **Step 4: Offline round-trip and guarded live plan-only replay**

    artifact=$(find $evidence_dir/runtime/so101/artifacts -maxdepth 1 -name '*.json' \
      ! -name '*.replay-result.json' -print -quit)
    sha256sum $artifact > $evidence_dir/runtime/so101/artifact-before.sha256
    build/so101_gazebo_demo/so101_planning_failure_replay \
      --artifact $artifact --offline \
      2>&1 | tee $evidence_dir/runtime/so101/offline-replay.log
    build/so101_gazebo_demo/so101_planning_failure_replay \
      --artifact $artifact --live-plan-only \
      --expected-session-id r3-diagnostics-so101 \
      --expected-fingerprint $policy_fingerprint \
      2>&1 | tee $evidence_dir/runtime/so101/live-replay.log
    sha256sum $artifact > $evidence_dir/runtime/so101/artifact-after.sha256
    cmp $evidence_dir/runtime/so101/artifact-before.sha256 \
      $evidence_dir/runtime/so101/artifact-after.sha256

Expected: exact offline round-trip, matching scene fingerprint, one plan-only result, immutable artifact, and no execution. Planner success or failure is acceptable if accurately reported.

- [ ] **Step 5: Re-read all no-execution evidence**

Repeat Step 3 facts and hashes. Assert zero arm/gripper controller goal, unchanged joints/TCP within observation tolerance, unchanged cup pose/attachment, unchanged MoveIt membership, unchanged checkpoint/sidecar, and a fresh inspected image matching the pre-injection/replay scene.

- [ ] **Step 6: Prove normal SO-101 success emits no artifact**

Reset. Use a new directory and session; run execute with stop-after WAIT_MICRO_LIFT_STABLE and diagnostics enabled. Require successful trace through WAIT_MICRO_LIFT_STABLE, physical/MoveIt/Gazebo/controller facts consistent, no file in the new diagnostics directory, and a fresh inspected image showing the 2 mm probe without cup loss.

- [ ] **Step 7: Clean SO-101 and run Panda regression**

Record PID/parent/command/domain/partition/tmux ownership, stop only r3-planning-diagnostics-so101, and verify no domain-193 nodes remain. Preserve unrelated processes. Start exactly one owned tmux session r3-planning-diagnostics-panda after source ~/gui-env.zsh, /opt/ros/jazzy/setup.zsh, and this worktree install/setup.zsh; set ROS_DOMAIN_ID=194 and GZ_PARTITION=r3-planning-diagnostics-panda. Launch:

    ros2 launch panda_gazebo_demo panda_gazebo.launch.py \
      headless:=false run_state_machine:=true mode:=execute \
      checkpoint_path:=/tmp/panda-r3-planning-diagnostics-checkpoint.json \
      simulation_session_id:=r3-diagnostics-panda

Require DONE and exit code 0. Capture and inspect baseline/final PNGs with ai-station-capture.sh, plus controller/joint/TF, Gazebo object pose, MoveIt membership, checkpoint, and final detached/supported state. Panda exposes no diagnostics argument or file. Stop only the owned Panda session and verify no domain-194 nodes remain.

- [ ] **Step 8: Final cleanup and report**

    git diff --check
    git status --short --branch | tee $evidence_dir/git-status-final.txt
    git log --oneline --decorate -12 | tee $evidence_dir/commits-final.txt
    ps -eo pid,ppid,stat,cmd | rg 'r3-planning-diagnostics|gz sim|move_group|rviz2|pick_place_state_machine|run-clang-tidy' \
      | tee $evidence_dir/processes-final.txt || true
    tmux list-sessions | tee $evidence_dir/tmux-final.txt

Expected: clean worktree, scoped commits, no owned stacks, unrelated clang-tidy/codex-cua preserved, no evidence tracked, no push/merge.

Final report fields:

    Root cause: NOT CONFIRMED
    First bad boundary: request-scoped MICRO_LIFT MoveGroup result
    Freshness-fix commit:
    Diagnostics commits:
    RED evidence and GREEN/three-package counts:
    SO-101 artifact/replay paths:
    No-execution joint/TF/Gazebo/MoveIt/checkpoint proof:
    SO-101 normal-success/no-artifact proof:
    Panda runtime/visual proof:
    Final Git/process state:
    Remaining risk: OMPL remains stochastic; natural recurrence has not occurred

Stop after reporting. Do not push, merge, resume another goal, or claim the intermittent planner failure is fixed.
