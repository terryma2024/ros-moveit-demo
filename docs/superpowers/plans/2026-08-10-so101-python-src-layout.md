# SO-101 Python Source Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the Python implementation to `src/so101_gazebo_demo_py/src`, rename its public import namespace to `so101_gazebo_demo`, and retain `so101_gazebo_demo_py` as the ROS package name with working tests and launch files.

**Architecture:** Use an explicit setuptools `package_dir` mapping so the flat physical `src` directory is installed as `so101_gazebo_demo`, including all existing subpackages. Update active imports and entry points mechanically while leaving ROS metadata and commands named `so101_gazebo_demo_py`.

**Tech Stack:** ROS 2 Jazzy, `ament_python`, setuptools, pytest, colcon.

## Global Constraints

- The ROS package name and install prefix remain exactly `so101_gazebo_demo_py`.
- The public Python import package becomes exactly `so101_gazebo_demo`.
- The implementation tree lives directly at `src/so101_gazebo_demo_py/src`.
- No compatibility alias for the old Python import namespace is installed.
- Existing ROS console-script command names and launch filenames remain unchanged.
- Tests and launch verification must not execute robot motion.
- Preserve all pre-existing working-tree changes from the completed C++ runtime rename.

---

### Task 1: Lock the layout and packaging contract

**Files:**
- Modify: `src/so101_gazebo_demo_py/test/test_package_independence.py`
- Modify: `src/so101_gazebo_demo_py/setup.py`

**Interfaces:**
- Consumes: the ROS distribution name `so101_gazebo_demo_py` and current setuptools entry points.
- Produces: a packaging contract mapping public package `so101_gazebo_demo` to physical directory `src`.

- [ ] **Step 1: Add failing layout assertions**

Add assertions that `package_root / "src" / "__init__.py"` exists, the old
`package_root / "so101_gazebo_demo_py"` directory does not exist, setup metadata retains
`name="so101_gazebo_demo_py"`, and setup maps `so101_gazebo_demo` to `src`.

- [ ] **Step 2: Run the contract test and verify RED**

Run:

```bash
PYTHONNOUSERSITE=1 pytest -q src/so101_gazebo_demo_py/test/test_package_independence.py
```

Expected: FAIL because `src/__init__.py` and the new package mapping do not exist.

- [ ] **Step 3: Update setuptools package mapping and entry points**

Set the distribution name to `so101_gazebo_demo_py`, map `so101_gazebo_demo` to `src`, enumerate
subpackages beneath `src` with the `so101_gazebo_demo.` prefix, and change entry-point module paths
to `so101_gazebo_demo.cli.*`.

---

### Task 2: Move the implementation and rename imports

**Files:**
- Move: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/**` to `src/so101_gazebo_demo_py/src/**`
- Modify: `src/so101_gazebo_demo_py/src/**/*.py`
- Modify: `src/so101_gazebo_demo_py/test/**/*.py`
- Modify: `src/so101_gazebo_demo_py/launch/*.py`
- Modify: active package documentation or scripts containing Python import paths

**Interfaces:**
- Consumes: setuptools mapping from Task 1.
- Produces: the import tree rooted at `so101_gazebo_demo`, with no active
  `so101_gazebo_demo_py` Python imports.

- [ ] **Step 1: Move the complete tracked implementation tree**

Use targeted move patches so Git records every Python source and subpackage under physical `src/`;
exclude generated `__pycache__` files from the move.

- [ ] **Step 2: Rename active Python imports**

Replace import prefixes `so101_gazebo_demo_py` with `so101_gazebo_demo` in implementation, tests,
launch files, and active scripts. Do not change ROS package lookup strings such as
`get_package_share_directory("so101_gazebo_demo_py")`.

- [ ] **Step 3: Run layout and focused import tests for GREEN**

Run:

```bash
PYTHONPATH=src/so101_gazebo_demo_py/src PYTHONNOUSERSITE=1 \
  pytest -q src/so101_gazebo_demo_py/test/test_package_independence.py \
            src/so101_gazebo_demo_py/test/test_launch_contract.py
```

Expected: PASS, with imports resolving only through `so101_gazebo_demo`.

---

### Task 3: Build, test, and launch from the install overlay

**Files:**
- Verify: `install/so101_gazebo_demo_py/**`
- Evidence: `/tmp/so101-debug-python-src-layout-*/`

**Interfaces:**
- Consumes: the migrated source and setuptools configuration.
- Produces: installed Python modules, ROS executables, and loadable launch descriptions.

- [ ] **Step 1: Build the ROS package cleanly**

Run:

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_gazebo_demo_py --symlink-install
source install/setup.zsh
```

Expected: exit 0.

- [ ] **Step 2: Verify installed imports and ROS identity**

Run an isolated Python command proving `so101_gazebo_demo` imports from the install overlay and
`so101_gazebo_demo_py` raises `ModuleNotFoundError`. Verify `ros2 pkg prefix
so101_gazebo_demo_py` and its four existing executables.

- [ ] **Step 3: Run the complete package test suite**

Run:

```bash
PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo_py \
  --event-handlers console_direct+
colcon test-result --verbose
```

Expected: zero errors and zero failures.

- [ ] **Step 4: Verify launch loading and safe startup**

Run every installed launch file with `--show-args`. Then run the pick-place launch in its safest
available dry-run/no-simulation mode under a bounded timeout, capturing output and exit status. It
must load modules from the install overlay, reach normal initialization, and show no import/package
resolution errors.

- [ ] **Step 5: Final integrity checks**

Run `git diff --check`, scan active source for stale Python import prefixes, inspect `git status
--short`, and confirm no existing Gazebo/MoveIt process or user change was altered.
