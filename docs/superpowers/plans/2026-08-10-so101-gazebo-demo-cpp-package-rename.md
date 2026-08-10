# SO-101 C++ Gazebo Demo ROS Package Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the C++ SO-101 ROS 2 package and source directory to `so101_gazebo_demo_cpp` while preserving the existing `so101_gazebo_demo` C++ namespace/include API and all historical evidence.

**Architecture:** Perform a real ROS package rename with no compatibility alias. Lock the naming boundary with RED/GREEN package contracts, migrate runtime resource lookups and current operator documentation in separate reviewable commits, then prove the result from an isolated ROS-only overlay before replacing the main workspace's stale package-scoped build/install artifacts.

**Tech Stack:** ROS 2 Jazzy, ament_cmake, colcon, CMake, C++17, Python 3/pytest, Xacro, Git, zsh on `ai-station`.

## Global Constraints

- Work directly in `/data/work/ws_moveit` on local `main`; do not create another worktree and do not push.
- Rename `src/so101_gazebo_demo` to `src/so101_gazebo_demo_cpp` and change the ROS package/CMake project identity to `so101_gazebo_demo_cpp`.
- Keep the C++ namespace, public include tree, and `#include` expressions as `so101_gazebo_demo`.
- Keep `so101_gazebo_demo_py` as the independent Python ROS package name.
- Do not create a compatibility metapackage, alias resource, wrapper, or duplicate old package entry.
- Preserve historical experiment ledgers, handoffs, dated pre-migration plans/specs, and `src/so101_gazebo_demo_py/docs/provenance.json` byte-for-byte.
- Do not change pick-place behavior, physics, geometry, mass/friction, controller gains, validation thresholds, state transitions, topics, services, actions, node names, or logger names.
- Only remove or move aside the explicit generated paths `build/so101_gazebo_demo` and `install/so101_gazebo_demo`, and only after the isolated renamed-package suite is green.
- Do not touch `/data/work/ws_moveit/.worktrees/so101-mujoco-ros2`, remote refs, unrelated tmux sessions, or existing ROS processes.
- Do not run `ament_uncrustify --reformat`.

## File Map

### Package identity and regression contracts

- Rename: `src/so101_gazebo_demo/` -> `src/so101_gazebo_demo_cpp/`
- Modify: `src/so101_gazebo_demo/test/test_package_layout.py` before the rename; it moves with the package.
- Modify: `src/pick_place_common/test/test_package_contract.py`
- Modify after rename: `src/so101_gazebo_demo_cpp/package.xml`
- Modify after rename: `src/so101_gazebo_demo_cpp/CMakeLists.txt`

### Runtime package/resource identity

- Modify after rename: all eight files under `src/so101_gazebo_demo_cpp/launch/*.launch.py`
- Modify: `src/so101_gazebo_demo_cpp/scripts/gripper_preopen_calc.py`
- Modify: `src/so101_gazebo_demo_cpp/scripts/prepare_simulation_model.py`
- Modify: `src/so101_gazebo_demo_cpp/so101_teleop/main.py`
- Modify: `src/so101_gazebo_demo_cpp/src/nodes/reset_so101_world.cpp`
- Modify: `src/so101_gazebo_demo_cpp/src/nodes/validate_so101_motion_matrix.cpp`
- Modify: `src/so101_gazebo_demo_cpp/src/pick_place/pick_place_state_machine.cpp`
- Modify: `src/so101_gazebo_demo_cpp/urdf/so101_base.xacro`
- Modify: `src/so101_gazebo_demo_cpp/test/test_fingertip_pad_geometry.py`
- Modify: `src/so101_gazebo_demo_cpp/test/test_prepare_simulation_model.py`
- Modify: `src/so101_gazebo_demo_cpp/test/test_so101_stack_inventory.py`
- Modify: `src/so101_gazebo_demo_cpp/web/e2e/teleop.spec.ts`

### Python-package independence boundary

- Preserve unchanged: `src/so101_gazebo_demo_py/docs/provenance.json`
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/gazebo/model_asset.py`
- Modify: `src/so101_gazebo_demo_py/test/test_asset_closure.py`
- Modify: `src/so101_gazebo_demo_py/test/test_installed_independence.py`
- Modify: `src/so101_gazebo_demo_py/test/test_launch_contract.py`
- Modify: `src/so101_gazebo_demo_py/test/test_package_independence.py`
- Modify: `src/so101_gazebo_demo_py/test/test_provenance.py`

### Current documentation and tooling

- Modify: `.agents/skills/gazebo-video-debug/SKILL.md`
- Modify: `.agents/skills/so101-dev/SKILL.md`
- Modify: `.agents/skills/so101-dev/references/ai-station-access.md`
- Modify: `.agents/skills/so101-dev/references/debug-evidence.md`
- Modify: `.agents/skills/so101-dev/references/so101-system-map.md`
- Modify: `.agents/skills/so101-dev/references/test-and-acceptance.md`
- Modify: `.idea/.name`
- Modify: `.idea/misc.xml`
- Modify: `docs/pick-place-architecture.md`
- Modify: `docs/pick-place-launch-parameters.md`
- Modify: `src/pick_place_common/README.md`
- Modify after rename: `src/so101_gazebo_demo_cpp/README.md`
- Modify after rename: `src/so101_gazebo_demo_cpp/docs/so101-teleop-web-ui.md`
- Modify after rename: `src/so101_gazebo_demo_cpp/docs/so101-workspace-sampler.md`

---

### Task 1: Lock the package and C++ API naming contract, then rename the package core

**Files:**
- Modify before rename: `src/so101_gazebo_demo/test/test_package_layout.py`
- Modify: `src/pick_place_common/test/test_package_contract.py`
- Rename: `src/so101_gazebo_demo/` -> `src/so101_gazebo_demo_cpp/`
- Modify after rename: `src/so101_gazebo_demo_cpp/package.xml`
- Modify after rename: `src/so101_gazebo_demo_cpp/CMakeLists.txt`

**Interfaces:**
- Consumes: the existing package-layout pytest and `pick_place_common` consumer contract.
- Produces: ROS package `so101_gazebo_demo_cpp`; unchanged C++ include root `include/so101_gazebo_demo`; a source tree that later runtime-reference changes can build against.

- [ ] **Step 1: Verify the execution baseline is still safe**

Run:

```zsh
cd /data/work/ws_moveit
git fetch origin
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
tmux list-sessions 2>/dev/null || true
pgrep -af 'gz sim|move_group|rviz2|pick_place_state_machine|colcon|ctest' || true
```

Expected: `main` contains only the approved spec/plan commits, the worktree is clean, and no command in this task starts or stops a ROS/Gazebo process.

- [ ] **Step 2: Write the failing package identity and namespace-stability assertions**

Change `test_single_package_has_expected_identity()` in `src/so101_gazebo_demo/test/test_package_layout.py` to:

```python
def test_single_package_has_expected_identity():
    package = ET.parse(PACKAGE_DIR / 'package.xml').getroot()
    cmake = (PACKAGE_DIR / 'CMakeLists.txt').read_text(encoding='utf-8')

    assert PACKAGE_DIR.name == 'so101_gazebo_demo_cpp'
    assert package.findtext('name') == 'so101_gazebo_demo_cpp'
    assert 'project(so101_gazebo_demo_cpp)' in cmake
    assert not list(PACKAGE_DIR.glob('*/package.xml'))
    assert (PACKAGE_DIR / 'include' / 'so101_gazebo_demo').is_dir()
    assert not (PACKAGE_DIR / 'include' / 'so101_gazebo_demo_cpp').exists()
```

In `src/pick_place_common/test/test_package_contract.py`, define the consumer paths once and use the renamed C++ package in both tests:

```python
CONSUMER_NAMES = ('panda_gazebo_demo', 'so101_gazebo_demo_cpp')


def _consumer_paths(root: Path) -> tuple[Path, ...]:
    return tuple(root.parent / name for name in CONSUMER_NAMES)
```

Replace both hard-coded consumer tuples with `_consumer_paths(root)`.

- [ ] **Step 3: Run the focused tests and verify RED for the intended reason**

Run:

```zsh
cd /data/work/ws_moveit
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/so101_gazebo_demo/test/test_package_layout.py::test_single_package_has_expected_identity \
  src/pick_place_common/test/test_package_contract.py::test_common_package_exports_quality_gate_and_both_consumers_depend_on_it
```

Expected: FAIL because `PACKAGE_DIR.name` is still `so101_gazebo_demo` and `src/so101_gazebo_demo_cpp` does not yet exist. A syntax/import failure is not an acceptable RED result.

- [ ] **Step 4: Rename the directory and package metadata without changing namespaces**

Run:

```zsh
cd /data/work/ws_moveit
git mv src/so101_gazebo_demo src/so101_gazebo_demo_cpp
```

Make only these metadata substitutions:

```xml
<name>so101_gazebo_demo_cpp</name>
```

```cmake
project(so101_gazebo_demo_cpp)
```

Do not rename `include/so101_gazebo_demo`, `namespace so101_gazebo_demo`, `so101_gazebo_demo::`, or any `#include "so101_gazebo_demo/..."` expression.

- [ ] **Step 5: Run the identity contracts and verify GREEN**

Run:

```zsh
cd /data/work/ws_moveit
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/so101_gazebo_demo_cpp/test/test_package_layout.py::test_single_package_has_expected_identity \
  src/pick_place_common/test/test_package_contract.py
```

Expected: all selected tests PASS.

- [ ] **Step 6: Prove the namespace/include API did not move**

Run:

```zsh
cd /data/work/ws_moveit
test -d src/so101_gazebo_demo_cpp/include/so101_gazebo_demo
test ! -e src/so101_gazebo_demo_cpp/include/so101_gazebo_demo_cpp
if git diff -U0 -- src/so101_gazebo_demo_cpp | rg '^\+.*(namespace so101_gazebo_demo_cpp|#include [<"]so101_gazebo_demo_cpp/)'; then
  print 'ERROR: C++ API namespace/include was renamed' >&2
  exit 1
fi
```

Expected: exit 0 and no error output.

- [ ] **Step 7: Commit the core package rename**

```zsh
cd /data/work/ws_moveit
git add -- src/so101_gazebo_demo_cpp src/pick_place_common/test/test_package_contract.py
git diff --cached --check
git commit -m 'refactor(so101): rename C++ ROS package core'
```

### Task 2: Migrate runtime resource lookups and protect the Python boundary

**Files:**
- Modify: runtime/package-identity files listed under “Runtime package/resource identity”.
- Modify: Python independence and provenance tests listed under “Python-package independence boundary”.
- Preserve: `src/so101_gazebo_demo_py/docs/provenance.json`

**Interfaces:**
- Consumes: ROS package `so101_gazebo_demo_cpp` from Task 1.
- Produces: all runtime package-share/resource lookups use the new identity; the independent Python implementation rejects dependencies on the renamed C++ package.

- [ ] **Step 1: Change existing behavior contracts to expect the renamed package**

Before changing runtime production files:

- update `test_so101_launch_contract.py` expectations from the old ROS package argument/share lookup to `so101_gazebo_demo_cpp`;
- update `test_prepare_simulation_model.py` fixtures to use `model://so101_gazebo_demo_cpp/`;
- update `test_fingertip_pad_geometry.py` expected mesh prefix to `package://so101_gazebo_demo_cpp/`;
- update the five Python independence tests so their external C++ dependency fixture is `so101_gazebo_demo_cpp`;
- leave `test_provenance.py` unchanged for the RED run: Task 1's real directory rename must make its legacy source-path existence assertion fail.

The break caught by these tests is observable: launch/resource resolution still requests a package that no longer exists, or the Python package stops detecting a dependency on the current C++ package.

- [ ] **Step 2: Run the changed behavior tests and verify RED**

Run:

```zsh
cd /data/work/ws_moveit
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/so101_gazebo_demo_cpp/test/test_so101_launch_contract.py \
  src/so101_gazebo_demo_cpp/test/test_prepare_simulation_model.py \
  src/so101_gazebo_demo_cpp/test/test_fingertip_pad_geometry.py \
  src/so101_gazebo_demo_py/test/test_asset_closure.py \
  src/so101_gazebo_demo_py/test/test_installed_independence.py \
  src/so101_gazebo_demo_py/test/test_launch_contract.py \
  src/so101_gazebo_demo_py/test/test_package_independence.py \
  src/so101_gazebo_demo_py/test/test_provenance.py
```

Expected: FAIL on new package/resource expectations while production launch, URDF, model preparation, and Python dependency detection still use the old C++ package identity. `test_provenance.py` must also fail because its recorded legacy paths no longer exist after Task 1.

- [ ] **Step 3: Change only true ROS package/resource identities**

Apply `so101_gazebo_demo` -> `so101_gazebo_demo_cpp` only in these contexts:

```text
get_package_share_directory("...")
ament_index_cpp::get_package_share_directory("...")
Node(package="...")
package://.../
model://.../
/install/.../
```

Update all eight launch files, the three package-share Python modules, the three C++ package-share lookups, `so101_base.xacro`, the matching tests, and the Teleop E2E environment paths listed in the File Map.

In the five Python independence files, change the forbidden external C++ package identity to `so101_gazebo_demo_cpp`. Do not edit `src/so101_gazebo_demo_py/docs/provenance.json` and do not rename any `so101_gazebo_demo_py` symbol or package metadata.

Update `src/so101_gazebo_demo_py/test/test_provenance.py` so the immutable legacy source path is resolved through the new live source directory without changing the JSON record:

```python
def _live_source_path(recorded_source: str) -> Path:
    source = Path(recorded_source)
    if source.parts[:2] == ('src', 'so101_gazebo_demo'):
        source = Path('src', 'so101_gazebo_demo_cpp', *source.parts[2:])
    return PACKAGE.parents[1] / source
```

Replace `(PACKAGE.parents[1] / entry["source"]).is_file()` with `_live_source_path(entry["source"]).is_file()` after the RED run.

- [ ] **Step 4: Run focused runtime/resource tests and verify GREEN**

Run:

```zsh
cd /data/work/ws_moveit
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/so101_gazebo_demo_cpp/test/test_prepare_simulation_model.py \
  src/so101_gazebo_demo_cpp/test/test_fingertip_pad_geometry.py \
  src/so101_gazebo_demo_cpp/test/test_so101_launch_contract.py \
  src/so101_gazebo_demo_py/test/test_asset_closure.py \
  src/so101_gazebo_demo_py/test/test_installed_independence.py \
  src/so101_gazebo_demo_py/test/test_launch_contract.py \
  src/so101_gazebo_demo_py/test/test_package_independence.py \
  src/so101_gazebo_demo_py/test/test_provenance.py
```

Expected: all selected tests PASS.

- [ ] **Step 5: Prove the Python provenance file is byte-for-byte unchanged**

Run:

```zsh
cd /data/work/ws_moveit
git diff --exit-code 65b384ad46c3dbc6b164f84cf409026c5058a527 -- \
  src/so101_gazebo_demo_py/docs/provenance.json
```

Expected: exit 0 with no diff.

- [ ] **Step 6: Commit the runtime identity migration**

```zsh
cd /data/work/ws_moveit
git add -- \
  src/so101_gazebo_demo_cpp \
  src/so101_gazebo_demo_py/so101_gazebo_demo_py/gazebo/model_asset.py \
  src/so101_gazebo_demo_py/test/test_asset_closure.py \
  src/so101_gazebo_demo_py/test/test_installed_independence.py \
  src/so101_gazebo_demo_py/test/test_launch_contract.py \
  src/so101_gazebo_demo_py/test/test_package_independence.py \
  src/so101_gazebo_demo_py/test/test_provenance.py
git diff --cached --check
git commit -m 'refactor(so101): migrate C++ package runtime identity'
```

### Task 3: Update current documentation and enforce the historical-evidence boundary

**Files:**
- Modify: all files listed under “Current documentation and tooling”.
- Preserve unchanged: `docs/experiments/**`, `docs/handoffs/**`, pre-migration `docs/superpowers/plans/**`, pre-migration `docs/superpowers/specs/**`, and `src/so101_gazebo_demo_py/docs/provenance.json`.

**Interfaces:**
- Consumes: current runtime identity from Task 2.
- Produces: current operator instructions use only `so101_gazebo_demo_cpp`; historical commands and hashes remain intact.

- [ ] **Step 1: Capture the current-document audit before editing**

Run:

```zsh
cd /data/work/ws_moveit
git grep -n -P '(?<![A-Za-z0-9_])so101_gazebo_demo(?![A-Za-z0-9_])' -- \
  .agents .idea docs/pick-place-architecture.md docs/pick-place-launch-parameters.md \
  src/pick_place_common/README.md \
  src/so101_gazebo_demo_cpp/README.md src/so101_gazebo_demo_cpp/docs \
  | tee /tmp/so101-package-rename-current-docs-before.log
```

Expected: output lists current operational instructions that still use the old package/path identity. This is an audit baseline, not a persistent prose test.

- [ ] **Step 2: Update current operator documentation only**

In the files listed under “Current documentation and tooling”:

- change source/install paths to `src/so101_gazebo_demo_cpp` and `install/so101_gazebo_demo_cpp`;
- change `ros2 run`, `ros2 launch`, `ros2 pkg`, and `colcon --packages-*` arguments to `so101_gazebo_demo_cpp`;
- change the architecture label and IDE project name to `so101_gazebo_demo_cpp`;
- add one note to `docs/pick-place-architecture.md`: dated historical experiment/plan/handoff commands and Python provenance continue to show the legacy name intentionally.

Do not run replacement commands over any historical directory.

- [ ] **Step 3: Verify current operational references migrated**

Run:

```zsh
cd /data/work/ws_moveit
git grep -n -E \
  'src/so101_gazebo_demo(/|$)|install/so101_gazebo_demo(/|$)|ros2 (run|launch) so101_gazebo_demo( |$)|ros2 pkg (prefix|executables) so101_gazebo_demo( |$)|packages-(select|up-to).*so101_gazebo_demo( |$)' \
  -- .agents .idea docs/pick-place-architecture.md docs/pick-place-launch-parameters.md \
  src/pick_place_common/README.md \
  src/so101_gazebo_demo_cpp/README.md src/so101_gazebo_demo_cpp/docs \
  > /tmp/so101-package-rename-current-docs-after.log || true
test ! -s /tmp/so101-package-rename-current-docs-after.log
```

Expected: the after-audit file is empty. C++ namespace/include references are not part of the package/path audit and remain unchanged.

- [ ] **Step 4: Prove historical evidence was not rewritten**

Run:

```zsh
cd /data/work/ws_moveit
git diff --exit-code 65b384ad46c3dbc6b164f84cf409026c5058a527 -- \
  docs/experiments \
  docs/handoffs \
  src/so101_gazebo_demo_py/docs/provenance.json
```

Expected: exit 0 with no diff. For `docs/superpowers/plans` and `docs/superpowers/specs`, inspect `git diff --name-status` and allow only this migration's dated plan/spec documents.

- [ ] **Step 5: Commit current documentation**

```zsh
cd /data/work/ws_moveit
git add -- \
  .agents/skills/gazebo-video-debug/SKILL.md \
  .agents/skills/so101-dev \
  .idea/.name .idea/misc.xml \
  docs/pick-place-architecture.md docs/pick-place-launch-parameters.md \
  src/pick_place_common/README.md \
  src/so101_gazebo_demo_cpp/README.md \
  src/so101_gazebo_demo_cpp/docs
git diff --cached --check
git commit -m 'docs(so101): use C++ ROS package identity'
```

### Task 4: Prove the renamed package in a clean isolated overlay

**Files:**
- No source files should change.
- Evidence only: a new `/tmp/so101-debug-package-rename-*/` directory.

**Interfaces:**
- Consumes: committed renamed source tree from Tasks 1-3.
- Produces: build, test-result, package-prefix, executable, and launch-discovery evidence that cannot resolve through the stale main overlay.

- [ ] **Step 1: Create and record an isolated evidence root**

Run:

```zsh
cd /data/work/ws_moveit
RENAME_EVIDENCE_ROOT=$(mktemp -d /tmp/so101-debug-package-rename-XXXXXX)
print -r -- "$RENAME_EVIDENCE_ROOT" | tee /tmp/so101-package-rename-latest
mkdir -p "$RENAME_EVIDENCE_ROOT"/{build,install,log}
```

Expected: all generated verification artifacts are outside the source tree.

- [ ] **Step 2: Check package discovery from source**

Run:

```zsh
cd /data/work/ws_moveit
RENAME_EVIDENCE_ROOT=$(cat /tmp/so101-package-rename-latest)
source /opt/ros/jazzy/setup.zsh
colcon list --base-paths \
  src/pick_place_common src/so101_gazebo_demo_cpp src/so101_gazebo_demo_py | \
  tee "$RENAME_EVIDENCE_ROOT/colcon-list.log"
rg '^so101_gazebo_demo_cpp\s' "$RENAME_EVIDENCE_ROOT/colcon-list.log"
if rg '^so101_gazebo_demo\s' "$RENAME_EVIDENCE_ROOT/colcon-list.log"; then
  exit 1
fi
```

Expected: `pick_place_common` and `so101_gazebo_demo_cpp` are discovered; the old exact package name is absent.

- [ ] **Step 3: Build from ROS Jazzy only**

Run:

```zsh
cd /data/work/ws_moveit
RENAME_EVIDENCE_ROOT=$(cat /tmp/so101-package-rename-latest)
source /opt/ros/jazzy/setup.zsh
set -o pipefail
PYTHONNOUSERSITE=1 colcon --log-base "$RENAME_EVIDENCE_ROOT/log" build \
  --base-paths src/pick_place_common src/so101_gazebo_demo_cpp src/so101_gazebo_demo_py \
  --packages-select pick_place_common so101_gazebo_demo_cpp so101_gazebo_demo_py \
  --build-base "$RENAME_EVIDENCE_ROOT/build" \
  --install-base "$RENAME_EVIDENCE_ROOT/install" \
  --cmake-clean-cache --symlink-install \
  --event-handlers console_direct+ 2>&1 | tee "$RENAME_EVIDENCE_ROOT/build.log"
```

Expected: exit 0. If it fails, stop at this checkpoint and report the first renamed-package error; do not clean the main overlay.

- [ ] **Step 4: Run the complete isolated package suites**

Run:

```zsh
cd /data/work/ws_moveit
RENAME_EVIDENCE_ROOT=$(cat /tmp/so101-package-rename-latest)
source /opt/ros/jazzy/setup.zsh
source "$RENAME_EVIDENCE_ROOT/install/setup.zsh"
set -o pipefail
PYTHONNOUSERSITE=1 colcon --log-base "$RENAME_EVIDENCE_ROOT/log" test \
  --base-paths src/pick_place_common src/so101_gazebo_demo_cpp src/so101_gazebo_demo_py \
  --packages-select pick_place_common so101_gazebo_demo_cpp so101_gazebo_demo_py \
  --build-base "$RENAME_EVIDENCE_ROOT/build" \
  --install-base "$RENAME_EVIDENCE_ROOT/install" \
  --event-handlers console_direct+ 2>&1 | tee "$RENAME_EVIDENCE_ROOT/test.log"
colcon test-result \
  --test-result-base "$RENAME_EVIDENCE_ROOT/build" \
  --verbose | tee "$RENAME_EVIDENCE_ROOT/test-result.log"
```

Expected: exit 0 and zero errors/failures for the shared package plus both SO-101 packages. Do not include `panda_gazebo_demo`; its known unrelated readiness/flake8 failures are outside this migration.

- [ ] **Step 5: Verify installed package provenance and absence of the old package**

Run in a fresh zsh that sources only ROS Jazzy plus the isolated overlay:

```zsh
RENAME_EVIDENCE_ROOT=$(cat /tmp/so101-package-rename-latest)
source /opt/ros/jazzy/setup.zsh
source "$RENAME_EVIDENCE_ROOT/install/setup.zsh"
test "$(ros2 pkg prefix so101_gazebo_demo_cpp)" = \
  "$RENAME_EVIDENCE_ROOT/install/so101_gazebo_demo_cpp"
ros2 pkg executables so101_gazebo_demo_cpp | \
  tee "$RENAME_EVIDENCE_ROOT/executables.log"
if ros2 pkg prefix so101_gazebo_demo >"$RENAME_EVIDENCE_ROOT/old-prefix.log" 2>&1; then
  print 'ERROR: legacy package remains discoverable in isolated overlay' >&2
  exit 1
fi
ros2 launch so101_gazebo_demo_cpp so101_pick_place.launch.py --show-args \
  >"$RENAME_EVIDENCE_ROOT/show-args.log" 2>&1
```

Expected: new prefix and executable checks succeed, old prefix lookup fails, and `--show-args` exits 0 without starting Gazebo/MoveIt.

### Task 5: Replace stale main-overlay artifacts and perform final verification

**Files:**
- Move aside generated directory if present: `build/so101_gazebo_demo`
- Move aside generated directory if present: `install/so101_gazebo_demo`
- Generate: `build/so101_gazebo_demo_cpp`, `install/so101_gazebo_demo_cpp`
- No tracked source file should change.

**Interfaces:**
- Consumes: green isolated evidence from Task 4.
- Produces: main workspace overlay that resolves only `so101_gazebo_demo_cpp`, plus final Git/provenance checks.

- [ ] **Step 1: Reconfirm Task 4 is green before touching generated paths**

Run:

```zsh
RENAME_EVIDENCE_ROOT=$(cat /tmp/so101-package-rename-latest)
rg 'Summary: .*0 errors, 0 failures' "$RENAME_EVIDENCE_ROOT/test-result.log"
```

Expected: a zero-failure summary is present. Otherwise stop and preserve both old generated paths.

- [ ] **Step 2: Move only the stale old package artifacts into the evidence root**

Run:

```zsh
cd /data/work/ws_moveit
RENAME_EVIDENCE_ROOT=$(cat /tmp/so101-package-rename-latest)
mkdir -p \
  "$RENAME_EVIDENCE_ROOT/stale-artifacts/build" \
  "$RENAME_EVIDENCE_ROOT/stale-artifacts/install"
if [[ -e /data/work/ws_moveit/build/so101_gazebo_demo ]]; then
  mv /data/work/ws_moveit/build/so101_gazebo_demo \
    "$RENAME_EVIDENCE_ROOT/stale-artifacts/build/"
fi
if [[ -e /data/work/ws_moveit/install/so101_gazebo_demo ]]; then
  mv /data/work/ws_moveit/install/so101_gazebo_demo \
    "$RENAME_EVIDENCE_ROOT/stale-artifacts/install/"
fi
```

Expected: only the two explicit old package directories move; no broad `rm`, glob, or workspace cleanup is used.

- [ ] **Step 3: Build the renamed package into the main overlay**

Run:

```zsh
cd /data/work/ws_moveit
RENAME_EVIDENCE_ROOT=$(cat /tmp/so101-package-rename-latest)
source /opt/ros/jazzy/setup.zsh
set -o pipefail
PYTHONNOUSERSITE=1 colcon build \
  --packages-select pick_place_common so101_gazebo_demo_cpp so101_gazebo_demo_py \
  --cmake-clean-cache --symlink-install \
  --event-handlers console_direct+ 2>&1 | tee "$RENAME_EVIDENCE_ROOT/main-build.log"
```

Expected: exit 0.

- [ ] **Step 4: Test the actual main-overlay package**

Run:

```zsh
cd /data/work/ws_moveit
RENAME_EVIDENCE_ROOT=$(cat /tmp/so101-package-rename-latest)
source /opt/ros/jazzy/setup.zsh
source install/setup.zsh
set -o pipefail
PYTHONNOUSERSITE=1 colcon test \
  --packages-select pick_place_common so101_gazebo_demo_cpp so101_gazebo_demo_py \
  --event-handlers console_direct+ 2>&1 | tee "$RENAME_EVIDENCE_ROOT/main-test.log"
colcon test-result \
  --test-result-base build/so101_gazebo_demo_cpp \
  --verbose | tee "$RENAME_EVIDENCE_ROOT/main-test-result.log"
```

Expected: exit 0 and zero failures for the renamed package.

- [ ] **Step 5: Verify the live main overlay uses the renamed package**

Run:

```zsh
cd /data/work/ws_moveit
RENAME_EVIDENCE_ROOT=$(cat /tmp/so101-package-rename-latest)
source /opt/ros/jazzy/setup.zsh
source install/setup.zsh
ros2 pkg prefix so101_gazebo_demo_cpp
ros2 pkg executables so101_gazebo_demo_cpp
test ! -e build/so101_gazebo_demo
test ! -e install/so101_gazebo_demo
if ros2 pkg prefix so101_gazebo_demo >/tmp/so101-old-prefix-final.log 2>&1; then
  exit 1
fi
ros2 launch so101_gazebo_demo_cpp so101_pick_place.launch.py --show-args \
  >"$RENAME_EVIDENCE_ROOT/main-show-args.log" 2>&1
```

Expected: new package resolves from `/data/work/ws_moveit/install/so101_gazebo_demo_cpp`, the old generated paths are absent, the old package lookup fails, and launch argument discovery succeeds.

- [ ] **Step 6: Run final source, historical, namespace, Git, and process checks**

Run:

```zsh
cd /data/work/ws_moveit
RENAME_EVIDENCE_ROOT=$(cat /tmp/so101-package-rename-latest)
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/so101_gazebo_demo_cpp/test/test_package_layout.py \
  src/pick_place_common/test/test_package_contract.py \
  src/so101_gazebo_demo_py/test/test_provenance.py
git diff --check
git status --short --branch
git log -5 --oneline
git diff --exit-code 65b384ad46c3dbc6b164f84cf409026c5058a527 -- \
  docs/experiments docs/handoffs src/so101_gazebo_demo_py/docs/provenance.json
test -d src/so101_gazebo_demo_cpp/include/so101_gazebo_demo
test ! -e src/so101_gazebo_demo_cpp/include/so101_gazebo_demo_cpp
pgrep -af 'gz sim|move_group|rviz2|pick_place_state_machine|colcon|ctest' || true
```

Expected: contracts and diff checks pass, tracked worktree is clean after the planned commits, historical evidence has no diff, the C++ API path remains unchanged, and no test-owned Gazebo/MoveIt/colcon/ctest process remains.

- [ ] **Step 7: Perform the final remote-drift check without pushing**

Run:

```zsh
cd /data/work/ws_moveit
git fetch origin
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git worktree list --porcelain
```

Expected: local `main` contains the rename commits, `origin/main` is unchanged unless an external actor moved it, `.worktrees/so101-mujoco-ros2` is preserved, and no push occurred.
