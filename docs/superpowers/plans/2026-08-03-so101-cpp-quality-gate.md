# SO-101 C++ Quality Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add and execute the Panda-equivalent mandatory clang-tidy and clang-format quality gate for every production C++ target in `so101_gazebo_demo`.

**Architecture:** Package-local CMake modules discover all C/C++ production and test sources, write an explicit source manifest, and create a stamped `cpp_quality_gate` target. Every production C++ target depends on that gate, so strict clang-tidy runs before in-place repository-style clang-format.

**Tech Stack:** CMake 3.8, ament_cmake, Bash, clang-tidy 18, clang-format 18, colcon.

## Global Constraints

- Match the behavior of `src/panda_gazebo_demo/cmake/cpp_quality_gate.cmake` and `run_cpp_quality_gate.cmake`.
- Use repository `.clang-tidy` and `.clang-format` files.
- Run clang-tidy with `-warnings-as-errors=*` before `clang-format -i --style=file`.
- Attach the gate to every production C++ library and executable in `so101_gazebo_demo`.
- Preserve all existing user changes and never run `ament_uncrustify --reformat`.
- Do not start, stop, or interact with the live Gazebo, MoveIt, or Teleop stack.

---

### Task 1: Add the quality-gate behavioral contract

**Files:**
- Create: `src/so101_gazebo_demo/test/scripts/test_cpp_quality_gate.sh`
- Create later in Task 2: `src/so101_gazebo_demo/cmake/cpp_quality_gate.cmake`
- Create later in Task 2: `src/so101_gazebo_demo/cmake/run_cpp_quality_gate.cmake`

**Interfaces:**
- Consumes: two command-line paths, first to the runner and second to the CMake module.
- Produces: exit zero and `PASS: C++ quality gate runs tidy before format and fails closed` only when ordering, arguments, failure propagation, target dependency, invalidation, and missing-tool validation work.

- [ ] **Step 1: Copy the Panda contract test and change only the fixture function call**

Use the complete Panda script as the source and replace:

```cmake
panda_gazebo_add_cpp_quality_gate(
```

with:

```cmake
so101_gazebo_add_cpp_quality_gate(
```

- [ ] **Step 2: Run the contract test to verify RED**

Run:

```bash
bash src/so101_gazebo_demo/test/scripts/test_cpp_quality_gate.sh \
  src/so101_gazebo_demo/cmake/run_cpp_quality_gate.cmake \
  src/so101_gazebo_demo/cmake/cpp_quality_gate.cmake
```

Expected: nonzero because the SO-101 CMake modules do not exist.

---

### Task 2: Add the package-local CMake quality gate and wire every production target

**Files:**
- Create: `src/so101_gazebo_demo/cmake/cpp_quality_gate.cmake`
- Create: `src/so101_gazebo_demo/cmake/run_cpp_quality_gate.cmake`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`

**Interfaces:**
- Consumes: `WORKSPACE_ROOT`, `SOURCE_ROOT`, `RUN_CLANG_TIDY_EXECUTABLE`, `CLANG_FORMAT_EXECUTABLE`, and a `TARGETS` list.
- Produces: `so101_gazebo_add_cpp_quality_gate(...)` and the `cpp_quality_gate` CMake target.

- [ ] **Step 1: Copy the two Panda modules with package-specific identifiers**

Retain all runner behavior unchanged. In the module rename:

```cmake
PANDA_GAZEBO_CPP_QUALITY_GATE_MODULE_DIR
panda_gazebo_add_cpp_quality_gate
```

to:

```cmake
SO101_GAZEBO_CPP_QUALITY_GATE_MODULE_DIR
so101_gazebo_add_cpp_quality_gate
```

- [ ] **Step 2: Add top-level tool discovery and module inclusion**

Immediately after `project(so101_gazebo_demo)` add the Panda-equivalent block that:

```cmake
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
get_filename_component(SO101_GAZEBO_DEMO_WORKSPACE_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../.." REALPATH)
find_program(RUN_CLANG_TIDY_EXECUTABLE NAMES run-clang-tidy run-clang-tidy-18 run-clang-tidy-17 run-clang-tidy-16)
find_program(CLANG_FORMAT_EXECUTABLE NAMES clang-format clang-format-18 clang-format-17 clang-format-16)
include(cmake/cpp_quality_gate.cmake)
```

Both missing-tool branches must fail configuration with explicit diagnostics.

- [ ] **Step 3: Attach the gate after all production target declarations**

Call:

```cmake
so101_gazebo_add_cpp_quality_gate(
  WORKSPACE_ROOT ${SO101_GAZEBO_DEMO_WORKSPACE_ROOT}
  SOURCE_ROOT ${CMAKE_CURRENT_SOURCE_DIR}
  RUN_CLANG_TIDY_EXECUTABLE ${RUN_CLANG_TIDY_EXECUTABLE}
  CLANG_FORMAT_EXECUTABLE ${CLANG_FORMAT_EXECUTABLE}
  TARGETS
    pick_place_core
    pick_place_state_machine
    gazebo_attachment_state_relay
    reset_so101_world
    so101_moveit_scene
    calibrate_so101_motion
    validate_so101_motion_matrix
    so101_attachment_collision_system
)
```

- [ ] **Step 4: Register the contract test under `BUILD_TESTING`**

Add:

```cmake
add_test(
  NAME test_cpp_quality_gate
  COMMAND bash
    ${CMAKE_CURRENT_SOURCE_DIR}/test/scripts/test_cpp_quality_gate.sh
    ${CMAKE_CURRENT_SOURCE_DIR}/cmake/run_cpp_quality_gate.cmake
    ${CMAKE_CURRENT_SOURCE_DIR}/cmake/cpp_quality_gate.cmake
)
```

- [ ] **Step 5: Rerun the contract test to verify GREEN**

Run the Task 1 command. Expected: exit zero and the exact PASS line.

---

### Task 3: Execute the real gate and verify the package

**Files:**
- Potential formatter output: all `src/so101_gazebo_demo/{src,include,test}` C/C++ files
- Evidence only: `/tmp/so101-debug-cpp-quality-20260803/`

**Interfaces:**
- Consumes: the configured build tree and root clang configuration.
- Produces: a successful quality-gate stamp, a successful package build/test result, and an auditable working-tree diff.

- [ ] **Step 1: Configure and build with the real quality gate**

Run:

```bash
source /opt/ros/jazzy/setup.zsh
export ROS_DOMAIN_ID=192
export GZ_PARTITION=so101_cpp_quality_20260803
colcon build --packages-select so101_gazebo_demo --symlink-install \
  --cmake-clean-cache --event-handlers console_direct+
```

Expected: clang-tidy runs before clang-format. On failure, save output and diagnose the first finding class before any targeted patch.

- [ ] **Step 2: Confirm the generated quality-gate artifacts**

Verify these exist:

```bash
test -f build/so101_gazebo_demo/compile_commands.json
test -f build/so101_gazebo_demo/cpp_quality_gate.stamp
test -f build/so101_gazebo_demo/cpp_quality_gate_sources.cmake
```

- [ ] **Step 3: Run the package test suite**

Run:

```bash
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo \
  --event-handlers console_direct+
colcon test-result --all --verbose
```

Expected: zero errors and zero failures; existing intentional skips are reported separately.

- [ ] **Step 4: Audit formatting and scope**

Run:

```bash
git diff --check
git status --short
git diff --stat
git diff -- src/so101_gazebo_demo/CMakeLists.txt \
  src/so101_gazebo_demo/cmake \
  src/so101_gazebo_demo/test/scripts/test_cpp_quality_gate.sh
```

Confirm that live process PIDs remain unchanged and report every formatter-modified source file separately from the three quality-gate integration files.
