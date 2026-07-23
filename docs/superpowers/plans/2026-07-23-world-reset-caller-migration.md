# World Reset Caller Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every active caller of deleted `planning_scene_setup` with the established MoveIt/world-reset flow.

**Architecture:** Launch initializes only the MoveIt scene with the installed `reset_moveit_world` node after `move_group`. The three headless harnesses already call `reset_world.sh`; they retain the independent Planning Scene assertion and remove their obsolete second setup action.

**Tech Stack:** ROS 2 launch Python, Bash, CMake/CTest, `reset_moveit_world`, `reset_world.sh`.

## Global Constraints

- Never restore `planning_scene_setup` or add a compatibility alias.
- Do not invoke `ament_uncrustify --reformat`.
- Preserve post-reset Gazebo and Planning Scene evidence in each harness.
- Do not use `gh`; origin is Gitee.

---

### Task 1: Lock the active caller contract with a failing test

**Files:**

- Create: `src/panda_gazebo_demo/test/scripts/test_world_reset_caller_migration.sh`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`

**Interfaces:**

- Consumes: `LAUNCH E2E RECOVERY PLAN_ONLY` positional arguments.
- Produces: CTest `test_world_reset_caller_migration`.

- [ ] **Step 1: Write the failing test**

Create the Bash test with the following complete checks:

```bash
#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 4 ]]; then
  printf 'usage: %s LAUNCH E2E RECOVERY PLAN_ONLY\n' "$0" >&2
  exit 2
fi

launch_file="$1"
shift

fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }

if rg -n '\bplanning_scene_setup\b' "${launch_file}" "$@"; then
  fail 'active launch or headless caller still references planning_scene_setup'
fi
rg -Fq "executable='reset_moveit_world'" "${launch_file}" ||
  fail 'launch does not start reset_moveit_world'
for harness in "$@"; do
  rg -Fq 'scripts/reset_world.sh' "${harness}" ||
    fail "headless harness does not call reset_world.sh: ${harness}"
  rg -Fq 'assert_reset_moveit_scene.py' "${harness}" ||
    fail "headless harness lacks independent MoveIt reset assertion: ${harness}"
done
printf 'PASS: world reset callers use reset_moveit_world and reset_world.sh\n'
```

Register it in `if(BUILD_TESTING)`:

```cmake
add_test(
  NAME test_world_reset_caller_migration
  COMMAND bash ${CMAKE_CURRENT_SOURCE_DIR}/test/scripts/test_world_reset_caller_migration.sh
    ${CMAKE_CURRENT_SOURCE_DIR}/launch/panda_gazebo.launch.py
    ${CMAKE_CURRENT_SOURCE_DIR}/test/headless/run_pick_place_e2e.sh
    ${CMAKE_CURRENT_SOURCE_DIR}/test/headless/run_recovery_scenarios.sh
    ${CMAKE_CURRENT_SOURCE_DIR}/test/headless/run_plan_only_resume_matrix.sh
)
```

- [ ] **Step 2: Verify RED**

Run:

```bash
bash src/panda_gazebo_demo/test/scripts/test_world_reset_caller_migration.sh \
  src/panda_gazebo_demo/launch/panda_gazebo.launch.py \
  src/panda_gazebo_demo/test/headless/run_pick_place_e2e.sh \
  src/panda_gazebo_demo/test/headless/run_recovery_scenarios.sh \
  src/panda_gazebo_demo/test/headless/run_plan_only_resume_matrix.sh
```

Expected: FAIL and list the deleted executable references.

- [ ] **Step 3: Commit test coverage**

```bash
git add src/panda_gazebo_demo/CMakeLists.txt \
  src/panda_gazebo_demo/test/scripts/test_world_reset_caller_migration.sh
git commit -m "test: cover world reset caller migration"
```

### Task 2: Migrate launch and headless reset callers

**Files:**

- Modify: `src/panda_gazebo_demo/launch/panda_gazebo.launch.py`
- Modify: `src/panda_gazebo_demo/test/headless/run_pick_place_e2e.sh`
- Modify: `src/panda_gazebo_demo/test/headless/run_recovery_scenarios.sh`
- Modify: `src/panda_gazebo_demo/test/headless/run_plan_only_resume_matrix.sh`

**Interfaces:**

- Consumes: installed `reset_moveit_world` and existing `reset_world.sh`.
- Produces: no active deleted-executable caller; reset evidence remains independent.

- [ ] **Step 1: Replace the launch action**

Replace the current node declaration with:

```python
moveit_world_setup_node = Node(
    package='panda_gazebo_demo',
    executable='reset_moveit_world',
    output='screen',
)
```

Replace the corresponding LaunchDescription entry with `moveit_world_setup_node`, retaining its
position after `move_group_node`. Do not launch `reset_world.sh`: launch setup must not move Panda
or reset Gazebo.

- [ ] **Step 2: Remove redundant headless setup actions**

In each of the three harnesses, immediately after `reset_world.sh` and
`assert_reset_moveit_scene.py`:

1. delete `timeout 15 ros2 run panda_gazebo_demo planning_scene_setup` and its log redirect;
2. rename `reset_moveit_before_setup.txt` to `reset_moveit.txt` (including all references);
3. remove the following `sleep 1` when it only waited for the deleted executable;
4. leave `GetPlanningScene`, `assert_reset_moveit_scene.py`, `wait_until`, and post-reset
   Gazebo/attachment captures unchanged.

- [ ] **Step 3: Verify GREEN and syntax**

Run:

```bash
bash src/panda_gazebo_demo/test/scripts/test_world_reset_caller_migration.sh \
  src/panda_gazebo_demo/launch/panda_gazebo.launch.py \
  src/panda_gazebo_demo/test/headless/run_pick_place_e2e.sh \
  src/panda_gazebo_demo/test/headless/run_recovery_scenarios.sh \
  src/panda_gazebo_demo/test/headless/run_plan_only_resume_matrix.sh
python3 -m py_compile src/panda_gazebo_demo/launch/panda_gazebo.launch.py
bash -n src/panda_gazebo_demo/test/headless/run_pick_place_e2e.sh
bash -n src/panda_gazebo_demo/test/headless/run_recovery_scenarios.sh
bash -n src/panda_gazebo_demo/test/headless/run_plan_only_resume_matrix.sh
```

Expected: regression test PASS and all syntax checks exit zero.

- [ ] **Step 4: Build and run focused CTest**

Run:

```bash
colcon build --packages-select panda_gazebo_demo --event-handlers console_direct+
ctest --test-dir build/panda_gazebo_demo \
  -R '^(test_world_reset_caller_migration|test_reset_world|test_reset_moveit_world_cli)$' \
  --output-on-failure
rg -n '\bplanning_scene_setup\b' src/panda_gazebo_demo/launch \
  src/panda_gazebo_demo/test/headless && exit 1 || true
git diff --check
```

Expected: build and focused tests pass; final search produces no active caller.

- [ ] **Step 5: Commit migration**

```bash
git add src/panda_gazebo_demo/launch/panda_gazebo.launch.py \
  src/panda_gazebo_demo/test/headless/run_pick_place_e2e.sh \
  src/panda_gazebo_demo/test/headless/run_recovery_scenarios.sh \
  src/panda_gazebo_demo/test/headless/run_plan_only_resume_matrix.sh
git commit -m "fix: migrate callers to world reset flow"
```

### Task 3: Preserve and inspect real reset evidence

**Files:**

- Review: the three headless harnesses modified in Task 2.

- [ ] **Step 1: Run one normal single-run headless E2E invocation**

Run:

```bash
src/panda_gazebo_demo/test/headless/run_pick_place_e2e.sh --runs 1 --label reset_caller_migration
```

Capture the `logs: ...` directory printed by the script and require the command to finish without
invoking `planning_scene_setup`.

- [ ] **Step 2: Inspect the canonical reset facts**

Require these artifacts in the run directory and inspect them with existing assertions:

```text
run_1_reset_gazebo_coke.txt
run_1_reset_attachment.txt
run_1_reset_planning_scene.txt
run_1_reset_moveit.txt
```

The captured MoveIt reset snapshot must pass `assert_reset_moveit_scene.py`; the canonical
Planning Scene, Gazebo pose, and attachment evidence must show the detached Coke reset state.

- [ ] **Step 3: Keep generated evidence out of Git**

Run `git status --short`; generated run artifacts must not appear. Make no extra commit unless
evidence-capture source code changed during Task 2.
