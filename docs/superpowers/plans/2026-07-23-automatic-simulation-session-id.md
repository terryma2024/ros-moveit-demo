# Automatic Simulation Session ID Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate and log a reusable `execute-<unix-milliseconds>` simulation session ID for every non-resume execute startup that omits the parameter.

**Architecture:** Add a pure session-ID resolver to `pick_place_core`, with the current timestamp injected by the ROS node. The node applies the resolver once, logs every consumed ID through one INFO statement, and passes the resolved value to the existing observer, resume validator, and checkpoint path.

**Tech Stack:** C++17, ROS 2 Jazzy `rclcpp`, GoogleTest, CMake/colcon.

## Global Constraints

- Preserve checkpoint schema v3 and existing resume validation behavior.
- Never generate a new ID for resume; empty resume identity remains fail-closed.
- Non-resume `plan_only` and `dry_run` do not generate or log a session ID.
- `stop_after` does not affect resolution.
- Preserve the existing uncommitted `src/panda_gazebo_demo/worlds/table_coke.sdf` change.
- Never run `ament_uncrustify --reformat`; use only read-only lint checks.
- Do not push unless the user explicitly requests it.

---

### Task 1: Resolve and log simulation session identity

**Files:**
- Create: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/simulation_session_id.hpp`
- Create: `src/panda_gazebo_demo/src/pick_place/simulation_session_id.cpp`
- Create: `src/panda_gazebo_demo/test/pick_place/test_simulation_session_id.cpp`
- Modify: `src/panda_gazebo_demo/src/nodes/pick_place_state_machine_node.cpp`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`

**Interfaces:**
- Consumes: `pick_place::RunMode`, configured parameter text, `resume`, and a Unix timestamp in milliseconds.
- Produces: `SimulationSessionIdResolution resolveSimulationSessionId(RunMode, bool, std::string, std::uint64_t)` where `value` is the consumed session ID, or empty for modes that do not use one, and `error` is non-empty only for invalid resume startup.

- [x] **Step 1: Write the failing pure-function tests**

Create `test_simulation_session_id.cpp` with focused cases:

```cpp
#include <gtest/gtest.h>

#include "panda_gazebo_demo/pick_place/simulation_session_id.hpp"

namespace panda_gazebo_demo::pick_place
{

TEST(SimulationSessionId, GeneratesForInitialExecute)
{
  const auto result = resolveSimulationSessionId(
    RunMode::EXECUTE, false, "", 1784779200123ULL);
  ASSERT_TRUE(result.error.empty());
  ASSERT_TRUE(result.value);
  EXPECT_EQ(*result.value, "execute-1784779200123");
}

TEST(SimulationSessionId, PreservesExplicitExecuteAndResumeIds)
{
  const auto execute = resolveSimulationSessionId(
    RunMode::EXECUTE, false, "operator-session", 1);
  const auto resume = resolveSimulationSessionId(
    RunMode::PLAN_ONLY, true, "operator-session", 2);
  ASSERT_TRUE(execute.value);
  ASSERT_TRUE(resume.value);
  EXPECT_EQ(*execute.value, "operator-session");
  EXPECT_EQ(*resume.value, "operator-session");
}

TEST(SimulationSessionId, RejectsResumeWithoutExplicitId)
{
  const auto result = resolveSimulationSessionId(
    RunMode::EXECUTE, true, "", 1784779200123ULL);
  EXPECT_FALSE(result.value);
  EXPECT_EQ(
    result.error,
    "simulation_session_id is required for resume to reject stale checkpoints");
}

TEST(SimulationSessionId, DoesNotGenerateForNonResumeNonExecuteModes)
{
  for (const auto mode : {RunMode::DRY_RUN, RunMode::PLAN_ONLY}) {
    const auto result = resolveSimulationSessionId(
      mode, false, "ignored-session", 1784779200123ULL);
    EXPECT_TRUE(result.error.empty());
    EXPECT_FALSE(result.value);
  }
}

}  // namespace panda_gazebo_demo::pick_place
```

Register `test_simulation_session_id` in CMake, but do not add the resolver source before RED. The
test must reach the missing header at compile time rather than fail earlier on a missing source.

- [x] **Step 2: Run RED**

Run:

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select panda_gazebo_demo --symlink-install \
  --cmake-args -DBUILD_TESTING=ON
```

Expected: compilation fails because
`panda_gazebo_demo/pick_place/simulation_session_id.hpp` does not exist.

- [x] **Step 3: Implement the pure resolver**

Create the header:

```cpp
#pragma once

#include "panda_gazebo_demo/pick_place/domain_types.hpp"

#include <cstdint>
#include <optional>
#include <string>

namespace panda_gazebo_demo::pick_place
{

struct SimulationSessionIdResolution
{
  std::optional<std::string> value;
  std::string error;
};

SimulationSessionIdResolution resolveSimulationSessionId(
  RunMode mode, bool resume, std::string configured_id,
  std::uint64_t unix_timestamp_milliseconds);

}  // namespace panda_gazebo_demo::pick_place
```

Create the source:

```cpp
#include "panda_gazebo_demo/pick_place/simulation_session_id.hpp"

#include <utility>

namespace panda_gazebo_demo::pick_place
{

SimulationSessionIdResolution resolveSimulationSessionId(
  RunMode mode, bool resume, std::string configured_id,
  std::uint64_t unix_timestamp_milliseconds)
{
  if (resume) {
    if (configured_id.empty()) {
      return {std::nullopt,
        "simulation_session_id is required for resume to reject stale checkpoints"};
    }
    return {std::move(configured_id), ""};
  }
  if (mode != RunMode::EXECUTE) {
    return {std::nullopt, ""};
  }
  if (!configured_id.empty()) {
    return {std::move(configured_id), ""};
  }
  return {"execute-" + std::to_string(unix_timestamp_milliseconds), ""};
}

}  // namespace panda_gazebo_demo::pick_place
```

Add `src/pick_place/simulation_session_id.cpp` to the `pick_place_core` source list.

- [x] **Step 4: Integrate one resolution and one log point in the node**

Add `<chrono>` and the resolver header, rename the raw parameter to
`configured_simulation_session_id`, and resolve it immediately after parameter parsing:

```cpp
const auto configured_simulation_session_id =
  parameterOrDeclare(node, "simulation_session_id", std::string(""));
const auto unix_timestamp_milliseconds = static_cast<std::uint64_t>(
  std::chrono::duration_cast<std::chrono::milliseconds>(
    std::chrono::system_clock::now().time_since_epoch()).count());
const auto session_id = pick_place::resolveSimulationSessionId(
  *mode, resume, configured_simulation_session_id, unix_timestamp_milliseconds);
if (!session_id.error.empty()) {
  RCLCPP_ERROR(logger, "%s", session_id.error.c_str());
  rclcpp::shutdown();
  return EXIT_FAILURE;
}
const auto simulation_session_id = session_id.value.value_or("");
if (session_id.value) {
  RCLCPP_INFO(logger, "SIMULATION_SESSION_ID=%s", simulation_session_id.c_str());
}
```

Remove the later generic empty-ID rejection. Keep the existing
`if (*mode == RunMode::EXECUTE || resume)` construction block and pass
`simulation_session_id` unchanged to both `GazeboWorldObserver` and `CommonResumeValidator`.

- [x] **Step 5: Run focused GREEN and lint**

Run:

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select panda_gazebo_demo --symlink-install \
  --cmake-args -DBUILD_TESTING=ON
ctest --test-dir build/panda_gazebo_demo \
  -R '^test_simulation_session_id$' --output-on-failure
ament_uncrustify \
  src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/simulation_session_id.hpp \
  src/panda_gazebo_demo/src/pick_place/simulation_session_id.cpp \
  src/panda_gazebo_demo/test/pick_place/test_simulation_session_id.cpp
```

Expected: focused test passes and the read-only style check reports no divergence.

- [x] **Step 6: Run complete verification**

Run:

```bash
source /opt/ros/jazzy/setup.zsh
colcon test --packages-select panda_gazebo_demo
AMENT_CPPCHECK_ALLOW_SLOW_VERSIONS=1 colcon test \
  --packages-select panda_gazebo_demo --ctest-args -R '^cppcheck$'
colcon test-result --test-result-base build/panda_gazebo_demo/test_results --verbose
git diff --check
git status --short
```

Expected: zero test failures, no diff whitespace errors, and `table_coke.sdf` remains an unrelated
unstaged user change.

- [x] **Step 7: Commit only this feature**

```bash
git add \
  docs/superpowers/plans/2026-07-23-automatic-simulation-session-id.md \
  src/panda_gazebo_demo/CMakeLists.txt \
  src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/simulation_session_id.hpp \
  src/panda_gazebo_demo/src/pick_place/simulation_session_id.cpp \
  src/panda_gazebo_demo/src/nodes/pick_place_state_machine_node.cpp \
  src/panda_gazebo_demo/test/pick_place/test_simulation_session_id.cpp
git diff --cached --check
git commit -m "feat: generate execute session ids"
```

Do not stage `src/panda_gazebo_demo/worlds/table_coke.sdf`.
