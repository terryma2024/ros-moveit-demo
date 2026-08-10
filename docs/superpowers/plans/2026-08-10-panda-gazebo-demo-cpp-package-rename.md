# Panda C++ Gazebo Demo ROS Package Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the already-approved Panda test baseline, then rename the C++ Panda ROS 2 package and source directory to `panda_gazebo_demo_cpp` while preserving the existing `panda_gazebo_demo` C++ namespace/include API and all historical evidence.

**Architecture:** First isolate the two pre-existing test-fixture defects so the old package reaches a zero-failure baseline without production changes. Then perform a real ROS package rename with no compatibility alias, migrate active runtime and documentation references in separate reviewable commits, and prove the result from an isolated ROS-only overlay before replacing stale package-scoped artifacts in the main workspace.

**Tech Stack:** ROS 2 Jazzy, rmw_fastrtps_cpp, ament_cmake, colcon, CMake, C++17, Python 3/pytest, Bash, Xacro, Git, zsh on `ai-station`.

## Global Constraints

- Work directly in `/data/work/ws_moveit` on local `main`; do not create another worktree and do not push.
- The approved test-baseline addendum is limited to `src/panda_gazebo_demo/test/test_readiness_probe.py` and `src/panda_gazebo_demo/test/test_reset_world_discovery.py`; it must not change production code or assertions about runtime readiness.
- Replace the unavailable hard-coded `rmw_cyclonedds_cpp` test environment with the installed `rmw_fastrtps_cpp`; do not install another RMW as part of this task.
- Rename `src/panda_gazebo_demo` to `src/panda_gazebo_demo_cpp` and change the ROS package/CMake project identity to `panda_gazebo_demo_cpp`.
- Keep the C++ namespace, public include tree, and `#include` expressions as `panda_gazebo_demo`.
- Keep `pick_place_common`, `so101_gazebo_demo_cpp`, and `so101_gazebo_demo_py` package identities unchanged.
- Do not create a compatibility metapackage, alias resource, wrapper, or duplicate old package entry.
- Preserve historical experiment ledgers, handoffs, and dated pre-migration plans/specs byte-for-byte.
- Do not change pick-place behavior, physics, geometry, controller settings, validation thresholds, state transitions, topics, services, actions, executable names, node names, or logger names.
- Only move aside the explicit generated paths `build/panda_gazebo_demo` and `install/panda_gazebo_demo`, and only after the isolated renamed-package suite is green.
- Do not stop, start, or clean Gazebo, MoveIt, RViz, ROS nodes, or unrelated tmux sessions for this packaging-only migration.
- Do not run `ament_uncrustify --reformat`.

## File Map

### Test-baseline prerequisite

- Modify before rename: `src/panda_gazebo_demo/test/test_readiness_probe.py`
- Modify before rename: `src/panda_gazebo_demo/test/test_reset_world_discovery.py`

### Package identity and regression contracts

- Create before rename, then move with package: `src/panda_gazebo_demo/test/test_package_layout.py`
- Modify: `src/pick_place_common/test/test_package_contract.py`
- Rename: `src/panda_gazebo_demo/` -> `src/panda_gazebo_demo_cpp/`
- Modify after rename: `src/panda_gazebo_demo_cpp/package.xml`
- Modify after rename: `src/panda_gazebo_demo_cpp/CMakeLists.txt`

### Runtime package/resource identity

- Modify: `src/panda_gazebo_demo_cpp/launch/panda_gazebo.launch.py`
- Modify: `src/panda_gazebo_demo_cpp/urdf/panda.gazebo.urdf.xacro`
- Modify: `src/panda_gazebo_demo_cpp/scripts/reset_world.sh`
- Modify: `src/panda_gazebo_demo_cpp/test/test_panda_launch_contract.py`
- Modify: `src/panda_gazebo_demo_cpp/test/scripts/test_reset_world.sh`
- Modify: `src/panda_gazebo_demo_cpp/test/headless/run_pick_place_e2e.sh`
- Modify: `src/panda_gazebo_demo_cpp/test/headless/run_recovery_scenarios.sh`
- Modify: `src/panda_gazebo_demo_cpp/test/headless/run_plan_only_resume_matrix.sh`

### Current documentation

- Modify: `docs/pick-place-architecture.md`
- Modify: `docs/pick-place-launch-parameters.md`
- Modify: `src/pick_place_common/README.md`
- Modify: `src/panda_gazebo_demo_cpp/README.md`

### Historical evidence

- Preserve: `docs/experiments/**`
- Preserve: `docs/handoffs/**`
- Preserve existing files under `docs/superpowers/plans/**` and `docs/superpowers/specs/**`

---

### Task 1: Repair and prove the pre-existing Panda test baseline

**Files:**
- Modify: `src/panda_gazebo_demo/test/test_readiness_probe.py`
- Modify: `src/panda_gazebo_demo/test/test_reset_world_discovery.py`

**Interfaces:**
- Consumes: ROS Jazzy's installed `rmw_fastrtps_cpp` implementation and the existing readiness/reset tests.
- Produces: the same readiness assertions with executable test fixtures and a zero-Q001 lint baseline; no production interface changes.

- [ ] **Step 1: Record the clean execution baseline and evidence root**

Run:

```zsh
cd /data/work/ws_moveit
git fetch origin
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
PANDA_RENAME_EVIDENCE_ROOT=$(mktemp -d /tmp/panda-debug-package-rename-XXXXXX)
print -r -- "$PANDA_RENAME_EVIDENCE_ROOT" | tee /tmp/panda-package-rename-latest
git rev-parse HEAD | tee "$PANDA_RENAME_EVIDENCE_ROOT/implementation-base.txt"
mkdir -p "$PANDA_RENAME_EVIDENCE_ROOT"/{build,install,log}
tmux list-sessions 2>/dev/null || true
pgrep -af 'gz sim|move_group|rviz2|pick_place_state_machine|colcon|cmake|ctest' || true
```

Expected: only approved spec/plan commits are present, tracked status is clean, `origin/main` drift is recorded, and no process is started or stopped.

- [ ] **Step 2: Reproduce the existing RED baseline**

Run:

```zsh
cd /data/work/ws_moveit
source /opt/ros/jazzy/setup.zsh
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/panda_gazebo_demo/test/test_readiness_probe.py
ament_flake8 \
  src/panda_gazebo_demo/test/test_readiness_probe.py \
  src/panda_gazebo_demo/test/test_reset_world_discovery.py
```

Expected: readiness subprocess tests fail because `rmw_cyclonedds_cpp` cannot load, and flake8 reports exactly the existing Q001 multiline-string violations. Any unrelated failure must be recorded before editing.

- [ ] **Step 3: Make the minimum test-fixture correction**

In both `env.update(...)` blocks in `test_readiness_probe.py`, change only:

```python
'RMW_IMPLEMENTATION': 'rmw_fastrtps_cpp',
```

Change the raw multiline provider fixture delimiter from `r'''...'''` to `r"""..."""` without changing its body or assertions.

In `test_reset_world_discovery.py`, change the two Bash fixture delimiters from `f'''...'''` and `'''...'''` to `f"""..."""` and `"""..."""`. Do not change the generated Bash content.

- [ ] **Step 4: Verify the focused baseline is GREEN**

Run:

```zsh
cd /data/work/ws_moveit
source /opt/ros/jazzy/setup.zsh
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/panda_gazebo_demo/test/test_readiness_probe.py \
  src/panda_gazebo_demo/test/test_reset_world_discovery.py
ament_flake8 \
  src/panda_gazebo_demo/test/test_readiness_probe.py \
  src/panda_gazebo_demo/test/test_reset_world_discovery.py
```

Expected: both pytest files and flake8 exit 0.

- [ ] **Step 5: Prove production files were not changed and commit**

Run:

```zsh
cd /data/work/ws_moveit
git status --short
git diff --check
git diff --name-only | sort
git add -- \
  src/panda_gazebo_demo/test/test_readiness_probe.py \
  src/panda_gazebo_demo/test/test_reset_world_discovery.py
git diff --cached --check
git commit -m 'test(panda): repair readiness test baseline'
```

Expected: the staged set contains exactly the two test files.

### Task 2: Lock the package/API contract and rename the package core

**Files:**
- Create before rename: `src/panda_gazebo_demo/test/test_package_layout.py`
- Modify: `src/pick_place_common/test/test_package_contract.py`
- Rename: `src/panda_gazebo_demo/` -> `src/panda_gazebo_demo_cpp/`
- Modify after rename: `src/panda_gazebo_demo_cpp/package.xml`
- Modify after rename: `src/panda_gazebo_demo_cpp/CMakeLists.txt`

**Interfaces:**
- Consumes: existing Panda package metadata and the shared package consumer contract.
- Produces: ROS package `panda_gazebo_demo_cpp`; unchanged include root `include/panda_gazebo_demo`; registered package-layout pytest.

- [ ] **Step 1: Write the failing package identity contract**

Create `src/panda_gazebo_demo/test/test_package_layout.py` with:

```python
from pathlib import Path
import xml.etree.ElementTree as ET


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_package_identity_and_cpp_api_boundary() -> None:
    package = ET.parse(PACKAGE_ROOT / 'package.xml').getroot()
    cmake = (PACKAGE_ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')

    assert PACKAGE_ROOT.name == 'panda_gazebo_demo_cpp'
    assert package.findtext('name') == 'panda_gazebo_demo_cpp'
    assert 'project(panda_gazebo_demo_cpp)' in cmake
    assert (PACKAGE_ROOT / 'include' / 'panda_gazebo_demo').is_dir()
    assert not (PACKAGE_ROOT / 'include' / 'panda_gazebo_demo_cpp').exists()
```

In `src/pick_place_common/test/test_package_contract.py`, change only:

```python
CONSUMER_NAMES = ('panda_gazebo_demo_cpp', 'so101_gazebo_demo_cpp')
```

- [ ] **Step 2: Run the contract and verify RED for identity only**

Run:

```zsh
cd /data/work/ws_moveit
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/panda_gazebo_demo/test/test_package_layout.py::test_package_identity_and_cpp_api_boundary \
  src/pick_place_common/test/test_package_contract.py
```

Expected: failure because the source directory/package/project still use `panda_gazebo_demo` and the renamed consumer path does not exist. Syntax or import failure is not an acceptable RED result.

- [ ] **Step 3: Rename the directory and package metadata**

Run:

```zsh
cd /data/work/ws_moveit
git mv src/panda_gazebo_demo src/panda_gazebo_demo_cpp
```

Change exactly these metadata identities:

```xml
<name>panda_gazebo_demo_cpp</name>
```

```cmake
project(panda_gazebo_demo_cpp)
```

Register the new contract beside the existing pytest registrations in `CMakeLists.txt`:

```cmake
ament_add_pytest_test(test_package_layout test/test_package_layout.py)
```

Do not rename `include/panda_gazebo_demo`, `namespace panda_gazebo_demo`, `panda_gazebo_demo::`, or `#include "panda_gazebo_demo/..."`.

- [ ] **Step 4: Run the identity contracts and verify GREEN**

Run:

```zsh
cd /data/work/ws_moveit
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/panda_gazebo_demo_cpp/test/test_package_layout.py \
  src/pick_place_common/test/test_package_contract.py
```

Expected: all selected tests pass.

- [ ] **Step 5: Prove namespace/include stability**

Run:

```zsh
cd /data/work/ws_moveit
test -d src/panda_gazebo_demo_cpp/include/panda_gazebo_demo
test ! -e src/panda_gazebo_demo_cpp/include/panda_gazebo_demo_cpp
if git diff -U0 -- src/panda_gazebo_demo_cpp | \
    rg '^\+.*(namespace panda_gazebo_demo_cpp|#include [<"]panda_gazebo_demo_cpp/)'; then
  print 'ERROR: Panda C++ namespace/include API was renamed' >&2
  exit 1
fi
```

Expected: exit 0 with no API-rename error.

- [ ] **Step 6: Commit the core rename**

Run:

```zsh
cd /data/work/ws_moveit
git add -- src/panda_gazebo_demo_cpp src/pick_place_common/test/test_package_contract.py
git diff --cached --check
git commit -m 'refactor(panda): rename C++ ROS package core'
```

### Task 3: Migrate runtime package/resource identities

**Files:**
- Modify: all files listed under “Runtime package/resource identity”.
- Modify: `src/panda_gazebo_demo_cpp/test/test_package_layout.py`

**Interfaces:**
- Consumes: ROS package `panda_gazebo_demo_cpp` from Task 2.
- Produces: launch, Xacro, reset, and headless entry points that resolve only the new ROS package identity.

- [ ] **Step 1: Add failing runtime-identity assertions**

Append to `test_package_layout.py`:

```python
import re


LEGACY_IDENTITY = re.compile(
    r'(?<![A-Za-z0-9_])panda_gazebo_demo(?![A-Za-z0-9_])'
)
RUNTIME_IDENTITY_FILES = (
    PACKAGE_ROOT / 'launch' / 'panda_gazebo.launch.py',
    PACKAGE_ROOT / 'urdf' / 'panda.gazebo.urdf.xacro',
    PACKAGE_ROOT / 'scripts' / 'reset_world.sh',
    PACKAGE_ROOT / 'test' / 'scripts' / 'test_reset_world.sh',
    PACKAGE_ROOT / 'test' / 'headless' / 'run_pick_place_e2e.sh',
    PACKAGE_ROOT / 'test' / 'headless' / 'run_recovery_scenarios.sh',
    PACKAGE_ROOT / 'test' / 'headless' / 'run_plan_only_resume_matrix.sh',
)


def test_runtime_entry_points_use_new_package_identity() -> None:
    offenders = [
        str(path.relative_to(PACKAGE_ROOT))
        for path in RUNTIME_IDENTITY_FILES
        if LEGACY_IDENTITY.search(path.read_text(encoding='utf-8'))
    ]
    assert not offenders, 'Legacy Panda ROS package identity in:\n' + '\n'.join(offenders)
```

Append to `test_panda_launch_contract.py`:

```python
def test_launch_uses_renamed_ros_package_identity():
    source = PANDA_LAUNCH.read_text(encoding='utf-8')

    assert "FindPackageShare('panda_gazebo_demo_cpp')" in source
    assert source.count("package='panda_gazebo_demo_cpp'") == 3
    assert not re.search(
        r'(?<![A-Za-z0-9_])panda_gazebo_demo(?![A-Za-z0-9_])',
        source,
    )
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```zsh
cd /data/work/ws_moveit
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/panda_gazebo_demo_cpp/test/test_package_layout.py::test_runtime_entry_points_use_new_package_identity \
  src/panda_gazebo_demo_cpp/test/test_panda_launch_contract.py::test_launch_uses_renamed_ros_package_identity
bash src/panda_gazebo_demo_cpp/test/scripts/test_reset_world.sh \
  src/panda_gazebo_demo_cpp/scripts/reset_world.sh
```

Expected: the two new Python assertions fail because runtime files still use the old exact identity. The existing reset test may still pass before its expectation changes; it becomes part of GREEN verification after migration.

- [ ] **Step 3: Change only active ROS package identities**

Apply `panda_gazebo_demo` -> `panda_gazebo_demo_cpp` only in these contexts and listed files:

```text
FindPackageShare('...')
Node(package='...')
$(find ...)
MOVEIT_RESET_PACKAGE default
ros2 run ...
ros2 launch ...
build/<package>/test_logs
source package directory paths in active headless scripts/tests
```

Update `test_reset_world.sh` so the fake `ros2 run` matcher and command-order assertions expect `panda_gazebo_demo_cpp`. Do not change Panda topics, action names, model names, library targets, C++ includes, or namespaces.

- [ ] **Step 4: Run focused runtime tests and syntax checks**

Run:

```zsh
cd /data/work/ws_moveit
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/panda_gazebo_demo_cpp/test/test_package_layout.py \
  src/panda_gazebo_demo_cpp/test/test_panda_launch_contract.py \
  src/panda_gazebo_demo_cpp/test/test_reset_world_discovery.py
bash src/panda_gazebo_demo_cpp/test/scripts/test_reset_world.sh \
  src/panda_gazebo_demo_cpp/scripts/reset_world.sh
bash -n src/panda_gazebo_demo_cpp/scripts/reset_world.sh
bash -n src/panda_gazebo_demo_cpp/test/headless/run_pick_place_e2e.sh
bash -n src/panda_gazebo_demo_cpp/test/headless/run_recovery_scenarios.sh
bash -n src/panda_gazebo_demo_cpp/test/headless/run_plan_only_resume_matrix.sh
```

Expected: all commands exit 0.

- [ ] **Step 5: Audit the runtime identity boundary**

Run:

```zsh
cd /data/work/ws_moveit
rg -n -P '(?<![A-Za-z0-9_])panda_gazebo_demo(?![A-Za-z0-9_])' \
  src/panda_gazebo_demo_cpp/launch \
  src/panda_gazebo_demo_cpp/urdf \
  src/panda_gazebo_demo_cpp/scripts \
  src/panda_gazebo_demo_cpp/test/headless \
  src/panda_gazebo_demo_cpp/test/scripts && exit 1 || true
```

Expected: no legacy exact package identity in active runtime files.

- [ ] **Step 6: Commit runtime migration**

Run:

```zsh
cd /data/work/ws_moveit
git add -- src/panda_gazebo_demo_cpp
git diff --cached --check
git commit -m 'refactor(panda): migrate C++ package runtime identity'
```

### Task 4: Update current documentation and protect historical evidence

**Files:**
- Modify: the four files listed under “Current documentation”.
- Modify: `src/panda_gazebo_demo_cpp/test/test_package_layout.py`
- Preserve: all files listed under “Historical evidence”.

**Interfaces:**
- Consumes: current runtime identity from Task 3.
- Produces: current build/launch/test instructions use `panda_gazebo_demo_cpp`; dated evidence remains unchanged.

- [ ] **Step 1: Add the failing current-document contract**

Append to `test_package_layout.py`:

```python
WORKSPACE_ROOT = PACKAGE_ROOT.parents[1]
CURRENT_DOCUMENTS = (
    PACKAGE_ROOT / 'README.md',
    WORKSPACE_ROOT / 'docs' / 'pick-place-architecture.md',
    WORKSPACE_ROOT / 'docs' / 'pick-place-launch-parameters.md',
    WORKSPACE_ROOT / 'src' / 'pick_place_common' / 'README.md',
)


def test_current_documentation_uses_new_package_identity() -> None:
    offenders = [
        str(path.relative_to(WORKSPACE_ROOT))
        for path in CURRENT_DOCUMENTS
        if LEGACY_IDENTITY.search(path.read_text(encoding='utf-8'))
    ]
    assert not offenders, 'Legacy Panda package instructions in:\n' + '\n'.join(offenders)
```

- [ ] **Step 2: Run the document contract and verify RED**

Run:

```zsh
cd /data/work/ws_moveit
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/panda_gazebo_demo_cpp/test/test_package_layout.py::test_current_documentation_uses_new_package_identity
```

Expected: failure listing the four current documents that still use old paths or package arguments.

- [ ] **Step 3: Update only current operational documentation**

In the four current documents:

- change source paths to `src/panda_gazebo_demo_cpp`;
- change package-scoped build/test paths to `build/panda_gazebo_demo_cpp`;
- change `ros2 run`, `ros2 launch`, `ros2 pkg`, and `colcon --packages-*` arguments to `panda_gazebo_demo_cpp`;
- change the architecture diagram label to `panda_gazebo_demo_cpp`;
- add one sentence to `docs/pick-place-architecture.md` stating that dated experiment, plan, specification, and handoff commands retain the legacy Panda package name as historical evidence.

Do not run mechanical replacement commands over `docs/experiments`, `docs/handoffs`, or `docs/superpowers`.

- [ ] **Step 4: Verify documents GREEN and history unchanged**

Run:

```zsh
cd /data/work/ws_moveit
PANDA_RENAME_EVIDENCE_ROOT=$(cat /tmp/panda-package-rename-latest)
PANDA_RENAME_BASE=$(cat "$PANDA_RENAME_EVIDENCE_ROOT/implementation-base.txt")
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/panda_gazebo_demo_cpp/test/test_package_layout.py
git diff --exit-code "$PANDA_RENAME_BASE" -- \
  docs/experiments docs/handoffs docs/superpowers
```

Expected: package-layout tests pass and the historical directories have no implementation-phase diff relative to the recorded base.

- [ ] **Step 5: Commit current documentation**

Run:

```zsh
cd /data/work/ws_moveit
git add -- \
  docs/pick-place-architecture.md \
  docs/pick-place-launch-parameters.md \
  src/pick_place_common/README.md \
  src/panda_gazebo_demo_cpp/README.md \
  src/panda_gazebo_demo_cpp/test/test_package_layout.py
git diff --cached --check
git commit -m 'docs(panda): use C++ ROS package identity'
```

### Task 5: Prove the renamed package in a clean isolated overlay

**Files:**
- No tracked source files should change.
- Evidence only: the `/tmp/panda-debug-package-rename-*/` directory recorded earlier.

**Interfaces:**
- Consumes: committed source from Tasks 1-4.
- Produces: isolated build, zero-failure tests, package-prefix, executable, launch-discovery, and old-package-absence evidence.

- [ ] **Step 1: Check source package discovery**

Run:

```zsh
cd /data/work/ws_moveit
PANDA_RENAME_EVIDENCE_ROOT=$(cat /tmp/panda-package-rename-latest)
unset AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH PYTHONPATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.zsh
colcon list --base-paths src/pick_place_common src/panda_gazebo_demo_cpp | \
  tee "$PANDA_RENAME_EVIDENCE_ROOT/colcon-list.log"
rg '^panda_gazebo_demo_cpp\s' "$PANDA_RENAME_EVIDENCE_ROOT/colcon-list.log"
if rg '^panda_gazebo_demo\s' "$PANDA_RENAME_EVIDENCE_ROOT/colcon-list.log"; then
  exit 1
fi
```

Expected: `pick_place_common` and `panda_gazebo_demo_cpp` are discovered; the old exact package is absent.

- [ ] **Step 2: Build from ROS Jazzy only**

Run:

```zsh
cd /data/work/ws_moveit
PANDA_RENAME_EVIDENCE_ROOT=$(cat /tmp/panda-package-rename-latest)
unset AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH PYTHONPATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.zsh
set -o pipefail
PYTHONNOUSERSITE=1 colcon --log-base "$PANDA_RENAME_EVIDENCE_ROOT/log" build \
  --base-paths src/pick_place_common src/panda_gazebo_demo_cpp \
  --packages-select pick_place_common panda_gazebo_demo_cpp \
  --build-base "$PANDA_RENAME_EVIDENCE_ROOT/build" \
  --install-base "$PANDA_RENAME_EVIDENCE_ROOT/install" \
  --cmake-clean-cache --symlink-install \
  --event-handlers console_direct+ 2>&1 | \
  tee "$PANDA_RENAME_EVIDENCE_ROOT/build.log"
```

Expected: exit 0. On failure, stop at this checkpoint and report the first renamed-package error; do not touch the main overlay.

- [ ] **Step 3: Run complete isolated package suites**

Run:

```zsh
cd /data/work/ws_moveit
PANDA_RENAME_EVIDENCE_ROOT=$(cat /tmp/panda-package-rename-latest)
unset AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH PYTHONPATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.zsh
source "$PANDA_RENAME_EVIDENCE_ROOT/install/setup.zsh"
set -o pipefail
PYTHONNOUSERSITE=1 colcon --log-base "$PANDA_RENAME_EVIDENCE_ROOT/log" test \
  --base-paths src/pick_place_common src/panda_gazebo_demo_cpp \
  --packages-select pick_place_common panda_gazebo_demo_cpp \
  --build-base "$PANDA_RENAME_EVIDENCE_ROOT/build" \
  --install-base "$PANDA_RENAME_EVIDENCE_ROOT/install" \
  --event-handlers console_direct+ 2>&1 | \
  tee "$PANDA_RENAME_EVIDENCE_ROOT/test.log"
colcon test-result \
  --test-result-base "$PANDA_RENAME_EVIDENCE_ROOT/build/pick_place_common" \
  --verbose | tee "$PANDA_RENAME_EVIDENCE_ROOT/common-test-result.log"
colcon test-result \
  --test-result-base "$PANDA_RENAME_EVIDENCE_ROOT/build/panda_gazebo_demo_cpp" \
  --verbose | tee "$PANDA_RENAME_EVIDENCE_ROOT/panda-test-result.log"
```

Expected: both package-scoped summaries report zero errors and zero failures. Do not use unrelated stale workspace results as the acceptance source.

- [ ] **Step 4: Verify installed identity and old-package absence**

Run in a fresh zsh environment:

```zsh
PANDA_RENAME_EVIDENCE_ROOT=$(cat /tmp/panda-package-rename-latest)
unset AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH PYTHONPATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.zsh
source "$PANDA_RENAME_EVIDENCE_ROOT/install/setup.zsh"
test "$(ros2 pkg prefix panda_gazebo_demo_cpp)" = \
  "$PANDA_RENAME_EVIDENCE_ROOT/install/panda_gazebo_demo_cpp"
ros2 pkg executables panda_gazebo_demo_cpp | \
  tee "$PANDA_RENAME_EVIDENCE_ROOT/executables.log"
if ros2 pkg prefix panda_gazebo_demo \
    >"$PANDA_RENAME_EVIDENCE_ROOT/old-prefix.log" 2>&1; then
  print 'ERROR: legacy Panda package is discoverable' >&2
  exit 1
fi
ros2 launch panda_gazebo_demo_cpp panda_gazebo.launch.py --show-args \
  >"$PANDA_RENAME_EVIDENCE_ROOT/show-args.log" 2>&1
```

Expected: the new package resolves from the isolated install, expected executables are listed, old package lookup fails, and launch argument discovery exits 0 without starting Gazebo/MoveIt.

### Task 6: Replace stale main-overlay artifacts and perform final verification

**Files:**
- Move aside if present: `build/panda_gazebo_demo`
- Move aside if present: `install/panda_gazebo_demo`
- Generate: `build/panda_gazebo_demo_cpp`, `install/panda_gazebo_demo_cpp`
- No tracked source file should change.

**Interfaces:**
- Consumes: green isolated evidence from Task 5.
- Produces: the main workspace overlay resolving only `panda_gazebo_demo_cpp`, with clean Git and process state.

- [ ] **Step 1: Reconfirm isolated zero-failure evidence**

Run:

```zsh
PANDA_RENAME_EVIDENCE_ROOT=$(cat /tmp/panda-package-rename-latest)
rg 'Summary: .*0 errors, 0 failures' \
  "$PANDA_RENAME_EVIDENCE_ROOT/common-test-result.log" \
  "$PANDA_RENAME_EVIDENCE_ROOT/panda-test-result.log"
```

Expected: both zero-failure summaries are present. Otherwise stop without moving old artifacts.

- [ ] **Step 2: Move only stale old-package artifacts into the evidence root**

Run:

```zsh
cd /data/work/ws_moveit
PANDA_RENAME_EVIDENCE_ROOT=$(cat /tmp/panda-package-rename-latest)
mkdir -p \
  "$PANDA_RENAME_EVIDENCE_ROOT/stale-artifacts/build" \
  "$PANDA_RENAME_EVIDENCE_ROOT/stale-artifacts/install"
if [[ -e build/panda_gazebo_demo ]]; then
  mv build/panda_gazebo_demo \
    "$PANDA_RENAME_EVIDENCE_ROOT/stale-artifacts/build/"
fi
if [[ -e install/panda_gazebo_demo ]]; then
  mv install/panda_gazebo_demo \
    "$PANDA_RENAME_EVIDENCE_ROOT/stale-artifacts/install/"
fi
```

Expected: only the two explicit package directories move; no deletion, glob, or broad cleanup occurs.

- [ ] **Step 3: Build and test the main overlay**

Run:

```zsh
cd /data/work/ws_moveit
PANDA_RENAME_EVIDENCE_ROOT=$(cat /tmp/panda-package-rename-latest)
source /opt/ros/jazzy/setup.zsh
set -o pipefail
PYTHONNOUSERSITE=1 colcon build \
  --packages-select pick_place_common panda_gazebo_demo_cpp \
  --cmake-clean-cache --symlink-install \
  --event-handlers console_direct+ 2>&1 | \
  tee "$PANDA_RENAME_EVIDENCE_ROOT/main-build.log"
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test \
  --packages-select pick_place_common panda_gazebo_demo_cpp \
  --event-handlers console_direct+ 2>&1 | \
  tee "$PANDA_RENAME_EVIDENCE_ROOT/main-test.log"
colcon test-result --test-result-base build/pick_place_common --verbose | \
  tee "$PANDA_RENAME_EVIDENCE_ROOT/main-common-test-result.log"
colcon test-result --test-result-base build/panda_gazebo_demo_cpp --verbose | \
  tee "$PANDA_RENAME_EVIDENCE_ROOT/main-panda-test-result.log"
```

Expected: build and test commands exit 0; both package-scoped summaries report zero failures.

- [ ] **Step 4: Verify the live main overlay identity**

Run:

```zsh
cd /data/work/ws_moveit
PANDA_RENAME_EVIDENCE_ROOT=$(cat /tmp/panda-package-rename-latest)
source /opt/ros/jazzy/setup.zsh
source install/setup.zsh
test "$(ros2 pkg prefix panda_gazebo_demo_cpp)" = \
  /data/work/ws_moveit/install/panda_gazebo_demo_cpp
ros2 pkg executables panda_gazebo_demo_cpp
test ! -e build/panda_gazebo_demo
test ! -e install/panda_gazebo_demo
if ros2 pkg prefix panda_gazebo_demo >/tmp/panda-old-prefix-final.log 2>&1; then
  exit 1
fi
ros2 launch panda_gazebo_demo_cpp panda_gazebo.launch.py --show-args \
  >"$PANDA_RENAME_EVIDENCE_ROOT/main-show-args.log" 2>&1
```

Expected: new package resolves from the main install, old paths and package lookup are absent, and launch discovery succeeds.

- [ ] **Step 5: Run final source, history, namespace, Git, and process checks**

Run:

```zsh
cd /data/work/ws_moveit
PANDA_RENAME_EVIDENCE_ROOT=$(cat /tmp/panda-package-rename-latest)
PANDA_RENAME_BASE=$(cat "$PANDA_RENAME_EVIDENCE_ROOT/implementation-base.txt")
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/panda_gazebo_demo_cpp/test/test_package_layout.py \
  src/pick_place_common/test/test_package_contract.py
git diff --check
git status --short --branch
git diff --exit-code "$PANDA_RENAME_BASE" -- \
  docs/experiments docs/handoffs docs/superpowers
test -d src/panda_gazebo_demo_cpp/include/panda_gazebo_demo
test ! -e src/panda_gazebo_demo_cpp/include/panda_gazebo_demo_cpp
rg -n -P '(?<![A-Za-z0-9_])panda_gazebo_demo(?![A-Za-z0-9_])' \
  docs/pick-place-architecture.md \
  docs/pick-place-launch-parameters.md \
  src/pick_place_common/README.md \
  src/panda_gazebo_demo_cpp/README.md \
  src/panda_gazebo_demo_cpp/launch \
  src/panda_gazebo_demo_cpp/urdf \
  src/panda_gazebo_demo_cpp/scripts \
  src/panda_gazebo_demo_cpp/test/headless \
  src/panda_gazebo_demo_cpp/test/scripts && exit 1 || true
pgrep -af 'gz sim|move_group|rviz2|pick_place_state_machine|colcon|cmake|ctest' || true
```

Expected: contracts pass, tracked worktree is clean after planned commits, historical evidence has no implementation-phase diff, the C++ API path is unchanged, current operational files contain no old exact package identity, and no task-owned process remains.

- [ ] **Step 6: Perform final remote-drift check without pushing**

Run:

```zsh
cd /data/work/ws_moveit
git fetch origin
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git worktree list --porcelain
git log -8 --oneline
```

Expected: local `main` contains the scoped baseline/rename commits, external origin drift is reported rather than overwritten, all unrelated worktrees are preserved, and no push occurred.
