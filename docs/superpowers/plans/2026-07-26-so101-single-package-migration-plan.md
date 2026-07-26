# SO-101 Single-Package Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a self-contained `/data/work/ws_moveit/src/so101_gazebo_demo` ROS 2 package that reproduces the verified SO-101 description, controller, Gazebo, MoveIt, tooling, tests, and GUI behavior without depending on `/data/work/so101_lerobot_ws` or any `lerobot_*` package.

**Architecture:** Flatten the three source packages and two workspace-level tools into one standard ament package. Keep resource boundaries (`urdf`, `meshes`, `worlds`, `config`, `launch`, `rviz`, `scripts`, `test`) compatible with `panda_gazebo_demo`, rewrite every runtime resource lookup to `so101_gazebo_demo`, and prove independence in a clean ROS-only shell before real GUI acceptance.

**Tech Stack:** ROS 2 Jazzy, ament_cmake, Xacro/URDF, ros2_control, Gazebo Sim Harmonic, ros_gz, MoveIt 2, RViz 2, Python 3/pytest, colcon, zsh, X11/EWMH.

## Global Constraints

- Work directly in `/data/work/ws_moveit` on the current branch; do not create or switch worktrees unless the user changes this instruction.
- Preserve the committed Panda subtree baseline `75fb2e1e66ad1440f47f52f708b91887384084fd` (`HEAD:src/panda_gazebo_demo` at `54aefa0`); never reset, checkout, clean, stage, or edit Panda files during Phase 1.
- Stage only explicit paths under `src/so101_gazebo_demo` and this plan/spec; never use `git add -A` or `git add .`.
- Copy from the verified source baseline `/data/work/so101_lerobot_ws` at commit `65c371e`; do not copy `.git`, `build`, `install`, `log`, `.pytest_cache`, `__pycache__`, or `*.pyc`.
- The new package must not depend at runtime or test time on `/data/work/so101_lerobot_ws`, `lerobot_description`, `lerobot_controller`, or `lerobot_moveit`.
- Preserve `base_height=0.1899186`, transformed base-mesh bottom `z=0.22`, the existing `so101_tcp`, gripper geometry results, controller joint sets, SRDF groups, Coke bridge, world geometry, and final Gazebo camera pose.
- Phase 1 creates no C++ pick-place targets and modifies no Panda code. Panda code copying and generic-core extraction are separate Phase 2 work.
- ai-station shells are zsh: source `/opt/ros/jazzy/setup.zsh`, then `/data/work/ws_moveit/install/setup.zsh`.
- GUI launches must run in the existing `so101-moveit` tmux session after `source ~/gui-env.zsh`; real visual state must be verified with `ai-station-capture.sh` through the local capture wrapper.

---

## File Map

### New package metadata

- `src/so101_gazebo_demo/package.xml` — union of external runtime/test dependencies, with no `lerobot_*` dependencies.
- `src/so101_gazebo_demo/CMakeLists.txt` — installs all resources and scripts and registers all Python tests.
- `src/so101_gazebo_demo/LICENSE` — Apache-2.0 license copied from the verified source repository.
- `src/so101_gazebo_demo/README.md` — package entry points, source provenance (`65c371e`), build/test commands, and Phase 2 boundary.

### Migrated runtime resources

- `src/so101_gazebo_demo/urdf/*` — SO-101 Xacro, Gazebo plugin, and ros2_control definitions.
- `src/so101_gazebo_demo/meshes/so101/*.stl` — visual/collision assets.
- `src/so101_gazebo_demo/worlds/so101_pick_place.sdf` — table, pedestal, Coke, sensors, and GUI.
- `src/so101_gazebo_demo/config/*` — controller and MoveIt configuration.
- `src/so101_gazebo_demo/launch/*.launch.py` — display, controller, Gazebo, and MoveIt entry points.
- `src/so101_gazebo_demo/rviz/display.rviz` — description-only RViz layout.
- `src/so101_gazebo_demo/scripts/gripper_preopen_calc.py` — geometry calculator with package-relative default mesh discovery.
- `src/so101_gazebo_demo/scripts/tile_ai_station_guis.py` — X11/EWMH RViz/Gazebo tiling command.

### Migrated and new tests

- `src/so101_gazebo_demo/test/test_package_layout.py` — package identity, required resource layout, and no nested packages.
- `src/so101_gazebo_demo/test/test_self_containment.py` — forbidden runtime package/path scan and installed resource checks.
- `src/so101_gazebo_demo/test/test_gripper_preopen_calc.py` — existing gripper geometry regression.
- `src/so101_gazebo_demo/test/test_so101_pick_place_world.py` — existing world, GUI, headless SDF, base/pedestal, and TCP regressions.
- `src/so101_gazebo_demo/test/test_so101_launch_contract.py` — unified same-package Gazebo/MoveIt/controller/display launch contract.
- `src/so101_gazebo_demo/test/test_so101_srdf.py` — same-package URDF/SRDF joint consistency.
- `src/so101_gazebo_demo/test/test_tile_ai_station_guis.py` — existing tiling parser, X11 payload, timeout, and idempotence tests.

---

### Task 1: Scaffold the single package and lock its identity

**Files:**
- Create: `src/so101_gazebo_demo/test/test_package_layout.py`
- Create: `src/so101_gazebo_demo/package.xml`
- Create: `src/so101_gazebo_demo/CMakeLists.txt`
- Create: `src/so101_gazebo_demo/LICENSE`
- Create: `src/so101_gazebo_demo/README.md`

**Interfaces:**
- Consumes: verified source commit `65c371e`; workspace-level ament/colcon conventions.
- Produces: ROS package `so101_gazebo_demo`; install roots `share/so101_gazebo_demo` and `lib/so101_gazebo_demo` used by all later tasks.

- [ ] **Step 1: Record the committed Panda subtree baseline**

Run:

```bash
cd /data/work/ws_moveit
git status --short -- src/panda_gazebo_demo
git rev-parse HEAD:src/panda_gazebo_demo
```

Expected: no Panda working-tree changes and tree object `75fb2e1e66ad1440f47f52f708b91887384084fd`. Save both results in the task report.

- [ ] **Step 2: Write the failing package-layout test before metadata exists**

Create only `src/so101_gazebo_demo/test/test_package_layout.py`:

```python
from pathlib import Path
import xml.etree.ElementTree as ET


PACKAGE_DIR = Path(__file__).resolve().parents[1]


def test_single_package_has_expected_identity():
    package = ET.parse(PACKAGE_DIR / 'package.xml').getroot()
    assert package.findtext('name') == 'so101_gazebo_demo'
    assert not list(PACKAGE_DIR.glob('*/package.xml'))


def test_package_records_verified_source_provenance():
    readme = (PACKAGE_DIR / 'README.md').read_text()
    assert '/data/work/so101_lerobot_ws' in readme
    assert '65c371e' in readme
```

- [ ] **Step 3: Run RED and confirm the failure is missing metadata**

Run:

```bash
cd /data/work/ws_moveit
source /opt/ros/jazzy/setup.zsh
python3 -m pytest src/so101_gazebo_demo/test/test_package_layout.py -v
```

Expected: FAIL because `package.xml` and `README.md` do not exist. A syntax/import error is not an acceptable RED result.

- [ ] **Step 4: Add minimal package metadata**

Create `package.xml` with `<name>so101_gazebo_demo</name>`, Apache-2.0 license, `ament_cmake` build type, and external dependencies:

```xml
<buildtool_depend>ament_cmake</buildtool_depend>
<depend>xacro</depend>
<depend>urdf</depend>
<depend>robot_state_publisher</depend>
<depend>joint_state_publisher_gui</depend>
<depend>rviz2</depend>
<depend>launch</depend>
<depend>launch_ros</depend>
<depend>ros_gz_sim</depend>
<depend>ros_gz_bridge</depend>
<depend>ros_gz_interfaces</depend>
<depend>rosgraph_msgs</depend>
<depend>gz_ros2_control</depend>
<depend>controller_manager</depend>
<depend>joint_state_broadcaster</depend>
<depend>joint_trajectory_controller</depend>
<depend>moveit_configs_utils</depend>
<depend>moveit_ros_move_group</depend>
<depend>moveit_simple_controller_manager</depend>
<test_depend>ament_cmake_pytest</test_depend>
<test_depend>ament_lint_auto</test_depend>
<test_depend>ament_lint_common</test_depend>
```

Create a minimal `CMakeLists.txt` that declares `project(so101_gazebo_demo)`, finds `ament_cmake`, registers `test_package_layout` under `BUILD_TESTING`, and calls `ament_package()`.

Copy `/data/work/so101_lerobot_ws/LICENSE` to the package. Create `README.md` stating the package was copied from `/data/work/so101_lerobot_ws` at `65c371e`, is self-contained, and intentionally excludes Panda pick-place code in Phase 1.

- [ ] **Step 5: Run GREEN and confirm colcon recognizes exactly one new package**

Run:

```bash
cd /data/work/ws_moveit
source /opt/ros/jazzy/setup.zsh
python3 -m pytest src/so101_gazebo_demo/test/test_package_layout.py -v
colcon list | grep '^so101_gazebo_demo[[:space:]]'
```

Expected: 2 tests PASS; one `so101_gazebo_demo` package is listed.

- [ ] **Step 6: Verify the Panda subtree baseline and commit only Task 1 files**

Re-run the two Panda baseline commands from Step 1 and require a clean status plus the same tree object. Then:

```bash
git add \
  src/so101_gazebo_demo/package.xml \
  src/so101_gazebo_demo/CMakeLists.txt \
  src/so101_gazebo_demo/LICENSE \
  src/so101_gazebo_demo/README.md \
  src/so101_gazebo_demo/test/test_package_layout.py
git commit -m "feat: scaffold SO-101 Gazebo demo package"
```

---

### Task 2: Consolidate description, Gazebo world, controllers, and geometry tools

**Files:**
- Create: `src/so101_gazebo_demo/urdf/*`
- Create: `src/so101_gazebo_demo/meshes/so101/*.stl`
- Create: `src/so101_gazebo_demo/worlds/so101_pick_place.sdf`
- Create: `src/so101_gazebo_demo/config/so101_controllers.yaml`
- Create: `src/so101_gazebo_demo/launch/so101_display.launch.py`
- Create: `src/so101_gazebo_demo/launch/so101_controller.launch.py`
- Create: `src/so101_gazebo_demo/launch/so101_gazebo.launch.py`
- Create: `src/so101_gazebo_demo/rviz/display.rviz`
- Create: `src/so101_gazebo_demo/scripts/gripper_preopen_calc.py`
- Create: `src/so101_gazebo_demo/test/test_gripper_preopen_calc.py`
- Create: `src/so101_gazebo_demo/test/test_so101_pick_place_world.py`
- Create: `src/so101_gazebo_demo/test/test_so101_launch_contract.py`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`

**Interfaces:**
- Consumes: package share name `so101_gazebo_demo`; source description/controller assets at `65c371e`.
- Produces: installed URDF/world/controller resources; launch arguments `model`, `world`, and `base_height`; ROS topics `/clock` and `/coke/contacts`.

- [ ] **Step 1: Copy tests first and adapt their same-package paths**

Copy these source tests, excluding cache files:

```bash
cp /data/work/so101_lerobot_ws/src/lerobot_description/test/test_gripper_preopen_calc.py \
  src/so101_gazebo_demo/test/
cp /data/work/so101_lerobot_ws/src/lerobot_description/test/test_so101_pick_place_world.py \
  src/so101_gazebo_demo/test/
cp /data/work/so101_lerobot_ws/src/lerobot_description/test/test_so101_launch_contract.py \
  src/so101_gazebo_demo/test/
```

In `test_so101_launch_contract.py`, replace the cross-package roots with:

```python
PACKAGE_DIR = Path(__file__).resolve().parents[1]
GAZEBO_LAUNCH = PACKAGE_DIR / 'launch' / 'so101_gazebo.launch.py'
CONTROLLER_LAUNCH = PACKAGE_DIR / 'launch' / 'so101_controller.launch.py'
DISPLAY_LAUNCH = PACKAGE_DIR / 'launch' / 'so101_display.launch.py'
```

Keep the existing Gazebo argument, controller spawner, Coke bridge, world, base-height, TCP, and gripper numeric assertions. In Task 2 the launch-contract file contains only the Gazebo/controller/display assertions whose production files exist in this task. Task 3 adds the two original MoveIt assertions and the same-package MoveIt lookup assertion before final package testing, so final coverage is not reduced.

- [ ] **Step 2: Register the three tests and run RED**

Add three `ament_add_pytest_test` entries to `CMakeLists.txt`. Run directly from source before copying runtime files:

```bash
python3 -m pytest \
  src/so101_gazebo_demo/test/test_gripper_preopen_calc.py \
  src/so101_gazebo_demo/test/test_so101_pick_place_world.py \
  src/so101_gazebo_demo/test/test_so101_launch_contract.py -v
```

Expected: FAIL because `scripts/`, `meshes/`, `urdf/`, `worlds/`, and `launch/` resources are absent. Do not accept failures caused by broken imports introduced during path adaptation.

- [ ] **Step 3: Copy runtime assets without caches**

Copy only these source-owned paths:

```bash
cp -R /data/work/so101_lerobot_ws/src/lerobot_description/urdf \
  src/so101_gazebo_demo/
cp -R /data/work/so101_lerobot_ws/src/lerobot_description/meshes \
  src/so101_gazebo_demo/
cp -R /data/work/so101_lerobot_ws/src/lerobot_description/worlds \
  src/so101_gazebo_demo/
cp -R /data/work/so101_lerobot_ws/src/lerobot_description/rviz \
  src/so101_gazebo_demo/
mkdir -p src/so101_gazebo_demo/config src/so101_gazebo_demo/launch src/so101_gazebo_demo/scripts
cp /data/work/so101_lerobot_ws/src/lerobot_controller/config/so101_controllers.yaml \
  src/so101_gazebo_demo/config/
cp /data/work/so101_lerobot_ws/src/lerobot_description/launch/so101_display.launch.py \
  /data/work/so101_lerobot_ws/src/lerobot_description/launch/so101_gazebo.launch.py \
  /data/work/so101_lerobot_ws/src/lerobot_controller/launch/so101_controller.launch.py \
  src/so101_gazebo_demo/launch/
cp /data/work/so101_lerobot_ws/src/lerobot_description/scripts/gripper_preopen_calc.py \
  src/so101_gazebo_demo/scripts/
```

Every copied source above is an explicit file or an asset-only directory; no cache directory is in the copy set.

- [ ] **Step 4: Rewrite runtime package references with targeted patches**

Apply these exact semantic replacements:

```text
package://lerobot_description/ → package://so101_gazebo_demo/
$(find lerobot_controller) → $(find so101_gazebo_demo)
get_package_share_directory("lerobot_description") → get_package_share_directory("so101_gazebo_demo")
get_package_share_directory("lerobot_controller") → get_package_share_directory("so101_gazebo_demo")
```

Rename local variables such as `lerobot_description` to `package_share` so copied launch files no longer encode obsolete architecture. Preserve `base_height="0.1899186"`, camera pose `0.322 0.222 0.62 0 0.40 -2.30`, and all mesh origins unchanged.

- [ ] **Step 5: Install description/Gazebo resources and make calculator executable**

Add to `CMakeLists.txt`:

```cmake
install(
  DIRECTORY config launch meshes rviz urdf worlds
  DESTINATION share/${PROJECT_NAME}
)

install(
  PROGRAMS scripts/gripper_preopen_calc.py
  DESTINATION lib/${PROJECT_NAME}
)
```

Ensure both scripts retain a Python shebang and executable mode; do not reformat copied files as an unrelated change.

- [ ] **Step 6: Run GREEN for description/Gazebo behavior**

Run:

```bash
source /opt/ros/jazzy/setup.zsh
python3 -m pytest \
  src/so101_gazebo_demo/test/test_gripper_preopen_calc.py \
  src/so101_gazebo_demo/test/test_so101_pick_place_world.py \
  src/so101_gazebo_demo/test/test_so101_launch_contract.py -v
```

Expected: all migrated tests PASS, including headless one-iteration Gazebo SDF startup and the 30.0814 mm base-frame/mesh offset contract.

- [ ] **Step 7: Commit Task 2 without staging Panda files**

```bash
git add \
  src/so101_gazebo_demo/CMakeLists.txt \
  src/so101_gazebo_demo/config/so101_controllers.yaml \
  src/so101_gazebo_demo/launch \
  src/so101_gazebo_demo/meshes \
  src/so101_gazebo_demo/rviz \
  src/so101_gazebo_demo/scripts/gripper_preopen_calc.py \
  src/so101_gazebo_demo/test/test_gripper_preopen_calc.py \
  src/so101_gazebo_demo/test/test_so101_pick_place_world.py \
  src/so101_gazebo_demo/test/test_so101_launch_contract.py \
  src/so101_gazebo_demo/urdf \
  src/so101_gazebo_demo/worlds
git commit -m "feat: consolidate SO-101 Gazebo description"
```

---

### Task 3: Consolidate MoveIt configuration into the same package

**Files:**
- Create: `src/so101_gazebo_demo/config/initial_positions.yaml`
- Create: `src/so101_gazebo_demo/config/joint_limits.yaml`
- Create: `src/so101_gazebo_demo/config/kinematics.yaml`
- Create: `src/so101_gazebo_demo/config/moveit_controllers.yaml`
- Create: `src/so101_gazebo_demo/config/moveit.rviz`
- Create: `src/so101_gazebo_demo/config/pilz_cartesian_limits.yaml`
- Create: `src/so101_gazebo_demo/config/so101.srdf`
- Create: `src/so101_gazebo_demo/launch/so101_moveit.launch.py`
- Create: `src/so101_gazebo_demo/test/test_so101_srdf.py`
- Modify: `src/so101_gazebo_demo/test/test_so101_launch_contract.py`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`

**Interfaces:**
- Consumes: package-local `urdf/so101.urdf.xacro`, base-height launch contract, arm/gripper controller names.
- Produces: package-local `MoveItConfigsBuilder("so101", package_name="so101_gazebo_demo")`, `move_group`, and RViz startup.

- [ ] **Step 1: Copy the SRDF test first and add failing same-package paths**

Copy `test_so101_srdf.py` and change its Xacro path to:

```python
package_dir = Path(__file__).resolve().parents[1]
description_xacro = package_dir / 'urdf' / 'so101.urdf.xacro'
```

In `test_so101_launch_contract.py`, add:

```python
MOVEIT_LAUNCH = PACKAGE_DIR / 'launch' / 'so101_moveit.launch.py'
```

Keep the existing assertion that Gazebo and MoveIt both default to `0.1899186`. Add a source-text assertion that `so101_moveit.launch.py` contains `package_name="so101_gazebo_demo"` and does not contain any `lerobot_*` package name.

- [ ] **Step 2: Register and run RED**

Register `test_so101_srdf` in CMake, then run:

```bash
python3 -m pytest \
  src/so101_gazebo_demo/test/test_so101_srdf.py \
  src/so101_gazebo_demo/test/test_so101_launch_contract.py -v
```

Expected: FAIL because `config/so101.srdf` and `launch/so101_moveit.launch.py` are absent.

- [ ] **Step 3: Copy MoveIt resources and rewrite package lookups**

Copy all files from `/data/work/so101_lerobot_ws/src/lerobot_moveit/config/` into the existing package `config/`, and copy `so101_moveit.launch.py` into `launch/`.

Patch the launch file to use one `package_share = get_package_share_directory("so101_gazebo_demo")`, set the URDF path from that share, use:

```python
MoveItConfigsBuilder("so101", package_name="so101_gazebo_demo")
```

and load `config/so101.srdf`, `config/moveit_controllers.yaml`, and `config/moveit.rviz` from the same package. Preserve `is_sim=True`, `base_height=0.1899186`, and `use_sim_time` behavior.

- [ ] **Step 4: Run GREEN and verify generated URDF/SRDF consistency**

Run:

```bash
python3 -m pytest \
  src/so101_gazebo_demo/test/test_so101_srdf.py \
  src/so101_gazebo_demo/test/test_so101_launch_contract.py -v
```

Expected: all tests PASS; every SRDF joint exists in the generated package-local URDF.

- [ ] **Step 5: Commit Task 3**

```bash
git add \
  src/so101_gazebo_demo/config \
  src/so101_gazebo_demo/launch/so101_moveit.launch.py \
  src/so101_gazebo_demo/test/test_so101_launch_contract.py \
  src/so101_gazebo_demo/test/test_so101_srdf.py \
  src/so101_gazebo_demo/CMakeLists.txt
git commit -m "feat: consolidate SO-101 MoveIt configuration"
```

---

### Task 4: Migrate tools and enforce self-containment

**Files:**
- Create: `src/so101_gazebo_demo/scripts/tile_ai_station_guis.py`
- Create: `src/so101_gazebo_demo/test/test_tile_ai_station_guis.py`
- Create: `src/so101_gazebo_demo/test/test_self_containment.py`
- Modify: `src/so101_gazebo_demo/scripts/gripper_preopen_calc.py`
- Modify: `src/so101_gazebo_demo/test/test_gripper_preopen_calc.py`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`
- Modify: `src/so101_gazebo_demo/package.xml`

**Interfaces:**
- Consumes: package share lookup via `ament_index_python.packages.get_package_share_directory`.
- Produces: `default_mesh_dir() -> pathlib.Path`; installed ROS executables `gripper_preopen_calc.py` and `tile_ai_station_guis.py`; zero forbidden runtime references.

- [ ] **Step 1: Write the failing self-containment test**

Create `test_self_containment.py`:

```python
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parents[1]
RUNTIME_ROOTS = ('config', 'launch', 'rviz', 'scripts', 'urdf', 'worlds')
FORBIDDEN = (
    '/data/work/so101_lerobot_ws',
    'lerobot_description',
    'lerobot_controller',
    'lerobot_moveit',
)


def test_runtime_files_have_no_legacy_package_or_workspace_reference():
    offenders = []
    for root_name in RUNTIME_ROOTS:
        for path in (PACKAGE_DIR / root_name).rglob('*'):
            if path.is_file() and path.suffix in {'.py', '.xacro', '.urdf', '.sdf', '.yaml', '.rviz'}:
                text = path.read_text(errors='ignore')
                for forbidden in FORBIDDEN:
                    if forbidden in text:
                        offenders.append((str(path.relative_to(PACKAGE_DIR)), forbidden))
    assert not offenders, offenders
```

Add a calculator test that imports `default_mesh_dir` and asserts its returned directory contains `moving_jaw_so101_v1.stl` and `wrist_roll_follower_so101_v1.stl` after the package has been installed and sourced.

- [ ] **Step 2: Run RED and confirm the hard-coded calculator path is caught**

Run:

```bash
python3 -m pytest src/so101_gazebo_demo/test/test_self_containment.py -v
```

Expected: FAIL on the old `/data/work/so101_lerobot_ws/.../meshes/so101` default in `gripper_preopen_calc.py`. Any other runtime `lerobot_*` hit must also be listed and fixed, not allowlisted.

- [ ] **Step 3: Implement package-local calculator discovery**

Add:

```python
from ament_index_python.packages import get_package_share_directory


def default_mesh_dir() -> Path:
    return (
        Path(get_package_share_directory('so101_gazebo_demo'))
        / 'meshes'
        / 'so101'
    )
```

Use `default=default_mesh_dir()` for `--mesh-dir`. Add `ament_index_python` to `package.xml`. Do not retain an absolute source-tree fallback; tests must exercise the installed package after Task 5 builds it.

- [ ] **Step 4: Copy the tiling script/test and register all tests/scripts**

Copy:

```bash
cp /data/work/so101_lerobot_ws/scripts/tile_ai_station_guis.py \
  src/so101_gazebo_demo/scripts/
cp /data/work/so101_lerobot_ws/tests/test_tile_ai_station_guis.py \
  src/so101_gazebo_demo/test/
```

The existing test path already resolves `../scripts/tile_ai_station_guis.py` after this move. Register `test_tile_ai_station_guis` and `test_self_containment` with `ament_add_pytest_test`. Add `scripts/tile_ai_station_guis.py` to `install(PROGRAMS ...)`.

- [ ] **Step 5: Run source-level GREEN**

Run:

```bash
python3 -m pytest \
  src/so101_gazebo_demo/test/test_self_containment.py \
  src/so101_gazebo_demo/test/test_tile_ai_station_guis.py -v
```

Expected: self-containment scan and all tiling unit tests PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add \
  src/so101_gazebo_demo/CMakeLists.txt \
  src/so101_gazebo_demo/package.xml \
  src/so101_gazebo_demo/scripts \
  src/so101_gazebo_demo/test/test_gripper_preopen_calc.py \
  src/so101_gazebo_demo/test/test_self_containment.py \
  src/so101_gazebo_demo/test/test_tile_ai_station_guis.py
git commit -m "test: enforce SO-101 package self-containment"
```

---

### Task 5: Build and test from a clean ROS-only environment

**Files:**
- Modify only if a test exposes a defect: files under `src/so101_gazebo_demo/`
- Do not modify: `src/panda_gazebo_demo/**`

**Interfaces:**
- Consumes: complete single package from Tasks 1–4.
- Produces: installed package prefix `/data/work/ws_moveit/install/so101_gazebo_demo`; green colcon test result; proof that old overlays are unnecessary.

- [ ] **Step 1: Verify dependency resolution without the old SO-101 overlay**

Run in a fresh zsh:

```bash
zsh -lc '
  unset AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH
  source /opt/ros/jazzy/setup.zsh
  cd /data/work/ws_moveit
  rosdep check --from-paths src/so101_gazebo_demo --ignore-src
'
```

Expected: all system dependencies satisfied. If a dependency is missing from `package.xml`, add the exact external package dependency; do not source the old SO-101 workspace as a workaround.

- [ ] **Step 2: Build only the new package from the clean environment**

Run:

```bash
zsh -lc '
  unset AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH
  source /opt/ros/jazzy/setup.zsh
  cd /data/work/ws_moveit
  colcon build --packages-select so101_gazebo_demo --symlink-install
'
```

Expected: `Summary: 1 package finished`, with no lookup of a `lerobot_*` package.

- [ ] **Step 3: Run all package tests and inspect the package-specific result**

Run:

```bash
zsh -lc '
  unset AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH
  source /opt/ros/jazzy/setup.zsh
  source /data/work/ws_moveit/install/setup.zsh
  cd /data/work/ws_moveit
  colcon test --packages-select so101_gazebo_demo --event-handlers console_direct+
  colcon test-result --test-result-base build/so101_gazebo_demo --verbose
'
```

Expected: zero failures/errors. Existing Panda test state is outside this package-specific result.

- [ ] **Step 4: Verify installed resources and calculator behavior**

Run:

```bash
zsh -lc '
  unset AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH
  source /opt/ros/jazzy/setup.zsh
  source /data/work/ws_moveit/install/setup.zsh
  ros2 pkg prefix so101_gazebo_demo
  xacro /data/work/ws_moveit/install/so101_gazebo_demo/share/so101_gazebo_demo/urdf/so101.urdf.xacro > /tmp/so101_gazebo_demo.urdf
  ros2 run so101_gazebo_demo gripper_preopen_calc.py --grasp-depth-mm 20 --coke-diameter-mm 66 --preopen-clearance-mm 4
'
```

Expected: prefix points into `/data/work/ws_moveit/install`; Xacro succeeds; calculator reports the preserved q/width targets and resolves installed meshes.

- [ ] **Step 5: Run headless launch/resource smoke checks**

Run:

```bash
zsh -lc '
  unset AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH
  source /opt/ros/jazzy/setup.zsh
  source /data/work/ws_moveit/install/setup.zsh
  package_share=$(ros2 pkg prefix so101_gazebo_demo)/share/so101_gazebo_demo
  gz sim -s -r --iterations 1 "$package_share/worlds/so101_pick_place.sdf"
  ros2 launch so101_gazebo_demo so101_display.launch.py --show-args
  ros2 launch so101_gazebo_demo so101_controller.launch.py --show-args
  ros2 launch so101_gazebo_demo so101_gazebo.launch.py --show-args
  ros2 launch so101_gazebo_demo so101_moveit.launch.py --show-args
'
```

Expected: the SDF server iteration exits zero; all four launch descriptions load and print their arguments without a missing package, mesh, controller YAML, SRDF, or RViz config error.

- [ ] **Step 6: Verify the Panda subtree baseline, source scan, and commit any test-driven fixes**

Require the Task 1 Panda subtree status and tree object to remain identical. Run:

```bash
rg -n 'lerobot_description|lerobot_controller|lerobot_moveit|/data/work/so101_lerobot_ws' \
  src/so101_gazebo_demo/{CMakeLists.txt,package.xml,config,launch,rviz,scripts,urdf,worlds}
git diff --check -- src/so101_gazebo_demo
```

Expected: no runtime hit and no whitespace error. If Task 5 required fixes, commit only those explicit new-package paths with:

```bash
git commit -m "fix: complete SO-101 standalone package build"
```

Do not create an empty commit when no fix was needed.

---

### Task 6: Perform real Gazebo/MoveIt acceptance from ws_moveit only

**Files:**
- Modify only if runtime evidence exposes a defect: `src/so101_gazebo_demo/**`
- Evidence output: local capture under `assets/captures/ai-station/<timestamp>/desktop.png`

**Interfaces:**
- Consumes: installed `so101_gazebo_demo`, existing tmux session `so101-moveit`, local `scripts/capture-ai-station.sh`.
- Produces: controller/TF/runtime logs and an actual GUI screenshot proving the copied package behaves like the source baseline.

- [ ] **Step 1: Stop the old source-workspace launches without deleting the tmux session**

Send Ctrl-C to `so101-moveit:gazebo` and `so101-moveit:moveit`. Wait until both panes return to zsh. Do not kill the tmux session or create a second session for the same purpose.

- [ ] **Step 2: Launch only from ROS Jazzy and ws_moveit**

In both panes run:

```bash
source ~/gui-env.zsh
unset AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_moveit/install/setup.zsh
```

Gazebo pane:

```bash
ros2 launch so101_gazebo_demo so101_gazebo.launch.py
```

MoveIt pane:

```bash
ros2 launch so101_gazebo_demo so101_moveit.launch.py
```

Expected: both launch processes remain alive; MoveIt reports ready; Gazebo activates the expected controllers.

- [ ] **Step 3: Verify independent runtime evidence**

From a third sourced shell run:

```bash
ros2 control list_controllers
timeout 4 ros2 run tf2_ros tf2_echo world base -r 1 -p 7
ros2 topic echo /clock --once
ros2 topic echo /joint_states --once
```

Expected:

```text
joint_state_broadcaster active
arm_controller active
gripper_controller active
world -> base translation z = 0.1899186
```

Also inspect Gazebo pose info to confirm the SO-101 base pose is `z=0.1899186`, pedestal top is `z=0.22`, and Coke/table poses match the source baseline.

- [ ] **Step 4: Tile the GUIs using the installed new-package script**

Run:

```bash
ros2 run so101_gazebo_demo tile_ai_station_guis.py \
  --left rviz --right gazebo --timeout-sec 30
```

Expected exact runtime contract on the current ai-station desktop:

```text
LAYOUT_OK RVIZ=Rect(x=66, y=32, width=1887, height=2128) GAZEBO=Rect(x=1953, y=32, width=1887, height=2128)
```

- [ ] **Step 5: Capture and inspect the actual desktop**

From `/Users/matianyi/Projects/robot_demo_001` run:

```bash
./scripts/capture-ai-station.sh
```

Inspect the returned `desktop.png` at original resolution. Require:

- RViz left and Gazebo right with no overlap;
- table, pedestal, SO-101, and Coke complete;
- base mesh visibly seated on the pedestal;
- Coke unobscured and the compact Gazebo panels preserved;
- visual composition materially matches the verified source screenshot.

- [ ] **Step 6: Final package-only verification and commit runtime fixes if needed**

Re-run Task 5 build/tests, `git diff --check`, new-package legacy-reference scan, and Panda subtree baseline check. If runtime testing required a source fix, commit only explicit `src/so101_gazebo_demo` paths:

```bash
git commit -m "fix: validate SO-101 standalone runtime"
```

Do not create an empty commit. Leave `/data/work/so101_lerobot_ws` intact as a rollback reference and leave the verified ws_moveit GUI processes running unless the user requests shutdown.

---

## Final Review Checklist

- [ ] `colcon list` contains one `so101_gazebo_demo` package and no nested package from this migration.
- [ ] Package-specific build and tests pass in a ROS-only shell.
- [ ] No runtime/test reference requires a `lerobot_*` package or old workspace.
- [ ] Installed Xacro, meshes, controllers, MoveIt config, scripts, and world resolve from the new package.
- [ ] Gazebo and MoveIt share the same URDF and `base_height=0.1899186`.
- [ ] Controllers, TF, Gazebo entity poses, GUI split, and actual screenshot pass.
- [ ] `src/panda_gazebo_demo` remains clean and its tree object is still `75fb2e1e66ad1440f47f52f708b91887384084fd`.
- [ ] No Panda pick-place code or generic refactor was introduced in Phase 1.
- [ ] Independent code review reports no open Critical or Important finding.
