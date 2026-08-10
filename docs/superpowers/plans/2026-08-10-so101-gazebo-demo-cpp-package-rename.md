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
- Create after rename: `src/so101_gazebo_demo_cpp/test/test_package_rename_contract.py`

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
- Create: `src/so101_gazebo_demo_cpp/test/test_package_rename_contract.py`
- Modify: `src/so101_gazebo_demo_cpp/CMakeLists.txt`
- Modify: runtime/package-identity files listed under “Runtime package/resource identity”.
- Modify: five Python independence files listed under “Python-package independence boundary”.
- Preserve: `src/so101_gazebo_demo_py/docs/provenance.json`

**Interfaces:**
- Consumes: ROS package `so101_gazebo_demo_cpp` from Task 1.
- Produces: all runtime package-share/resource lookups use the new identity; the independent Python implementation rejects dependencies on the renamed C++ package.

- [ ] **Step 1: Add a focused runtime-identity contract**

Create `src/so101_gazebo_demo_cpp/test/test_package_rename_contract.py`:

```python
from pathlib import Path
import re


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
CPP_PACKAGE = WORKSPACE_ROOT / 'src' / 'so101_gazebo_demo_cpp'
PY_PACKAGE = WORKSPACE_ROOT / 'src' / 'so101_gazebo_demo_py'
LEGACY = 'so101_gazebo_demo'
CURRENT = 'so101_gazebo_demo_cpp'

RUNTIME_ROOTS = (
    CPP_PACKAGE / 'CMakeLists.txt',
    CPP_PACKAGE / 'package.xml',
    CPP_PACKAGE / 'launch',
    CPP_PACKAGE / 'scripts',
    CPP_PACKAGE / 'so101_teleop',
    CPP_PACKAGE / 'src',
    CPP_PACKAGE / 'urdf',
    CPP_PACKAGE / 'web' / 'e2e',
)

FORBIDDEN_PATTERNS = (
    re.compile(r'<name>so101_gazebo_demo</name>'),
    re.compile(r'project\(so101_gazebo_demo\)'),
    re.compile(r'get_package_share_directory\(["\']so101_gazebo_demo["\']\)'),
    re.compile(r'package\s*=\s*["\']so101_gazebo_demo["\']'),
    re.compile(r'(?:package|model)://so101_gazebo_demo/'),
    re.compile(r'/install/so101_gazebo_demo(?:/|\b)'),
)


def _files(root: Path):
    if root.is_file():
        yield root
        return
    for path in root.rglob('*'):
        if path.is_file() and '.git' not in path.parts:
            yield path


def test_active_cpp_runtime_uses_new_ros_package_identity():
    offenders = []
    for root in RUNTIME_ROOTS:
        for path in _files(root):
            text = path.read_text(errors='ignore')
            for pattern in FORBIDDEN_PATTERNS:
                if pattern.search(text):
                    offenders.append((str(path.relative_to(WORKSPACE_ROOT)), pattern.pattern))
    assert not offenders, offenders


def test_cpp_public_namespace_and_include_tree_stay_unchanged():
    assert (CPP_PACKAGE / 'include' / LEGACY).is_dir()
    assert not (CPP_PACKAGE / 'include' / CURRENT).exists()
    headers_and_sources = list((CPP_PACKAGE / 'include').rglob('*.[hH]pp'))
    headers_and_sources += list((CPP_PACKAGE / 'src').rglob('*.cpp'))
    assert not any(
        f'namespace {CURRENT}' in path.read_text(errors='ignore')
        or f'{CURRENT}::' in path.read_text(errors='ignore')
        for path in headers_and_sources
    )


def test_python_provenance_remains_historical_and_independence_targets_current_cpp_package():
    provenance = PY_PACKAGE / 'docs' / 'provenance.json'
    assert 'src/so101_gazebo_demo/' in provenance.read_text(encoding='utf-8')
    independence = (PY_PACKAGE / 'test' / 'test_package_independence.py').read_text()
    assert CURRENT in independence
```

Register it in `src/so101_gazebo_demo_cpp/CMakeLists.txt` next to `test_package_layout`:

```cmake
ament_add_pytest_test(
  test_package_rename_contract
  test/test_package_rename_contract.py
)
```

- [ ] **Step 2: Run the new runtime contract and verify RED**

Run:

```zsh
cd /data/work/ws_moveit
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/so101_gazebo_demo_cpp/test/test_package_rename_contract.py
```

Expected: FAIL with offenders containing old package-share lookups/resource URIs and because the Python independence test still names only the old C++ package.

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

Replace `(PACKAGE.parents[1] / entry["source"]).is_file()` with `_live_source_path(entry["source"]).is_file()`.

- [ ] **Step 4: Run focused runtime/resource tests and verify GREEN**

Run:

```zsh
cd /data/work/ws_moveit
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/so101_gazebo_demo_cpp/test/test_package_rename_contract.py \
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
- Modify: `src/so101_gazebo_demo_cpp/test/test_package_rename_contract.py`
- Preserve unchanged: `docs/experiments/**`, `docs/handoffs/**`, pre-migration `docs/superpowers/plans/**`, pre-migration `docs/superpowers/specs/**`, and `src/so101_gazebo_demo_py/docs/provenance.json`.

**Interfaces:**
- Consumes: current runtime identity from Task 2.
- Produces: current operator instructions use only `so101_gazebo_demo_cpp`; historical commands and hashes remain intact.

- [ ] **Step 1: Extend the contract with an explicit current-document list**

Append to `test_package_rename_contract.py`:

```python
CURRENT_OPERATOR_FILES = (
    WORKSPACE_ROOT / '.agents/skills/gazebo-video-debug/SKILL.md',
    WORKSPACE_ROOT / '.agents/skills/so101-dev/SKILL.md',
    WORKSPACE_ROOT / '.agents/skills/so101-dev/references/ai-station-access.md',
    WORKSPACE_ROOT / '.agents/skills/so101-dev/references/debug-evidence.md',
    WORKSPACE_ROOT / '.agents/skills/so101-dev/references/so101-system-map.md',
    WORKSPACE_ROOT / '.agents/skills/so101-dev/references/test-and-acceptance.md',
    WORKSPACE_ROOT / '.idea/.name',
    WORKSPACE_ROOT / '.idea/misc.xml',
    WORKSPACE_ROOT / 'docs/pick-place-architecture.md',
    WORKSPACE_ROOT / 'docs/pick-place-launch-parameters.md',
    WORKSPACE_ROOT / 'src/pick_place_common/README.md',
    CPP_PACKAGE / 'README.md',
    CPP_PACKAGE / 'docs/so101-teleop-web-ui.md',
    CPP_PACKAGE / 'docs/so101-workspace-sampler.md',
)


def test_current_operator_docs_use_cpp_ros_package_identity():
    forbidden = (
        re.compile(r'(?<![A-Za-z0-9_])src/so101_gazebo_demo(?:/|\b)'),
        re.compile(r'(?<![A-Za-z0-9_])install/so101_gazebo_demo(?:/|\b)'),
        re.compile(r'ros2\s+(?:run|launch|pkg\s+(?:prefix|executables))\s+so101_gazebo_demo\b'),
        re.compile(r'--packages-(?:select|up-to)[^\n]*\bso101_gazebo_demo\b'),
        re.compile(r'^so101_gazebo_demo$'),
        re.compile(r'^so101_gazebo_demo\s+[─|]'),
    )
    offenders = []
    for path in CURRENT_OPERATOR_FILES:
        for line_number, line in enumerate(path.read_text(errors='ignore').splitlines(), 1):
            if any(pattern.search(line) for pattern in forbidden):
                offenders.append((str(path.relative_to(WORKSPACE_ROOT)), line_number, line))
    assert not offenders, offenders
```

- [ ] **Step 2: Run the documentation contract and verify RED**

Run:

```zsh
cd /data/work/ws_moveit
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/so101_gazebo_demo_cpp/test/test_package_rename_contract.py::test_current_operator_docs_use_cpp_ros_package_identity
```

Expected: FAIL listing current Skills, IDE config, architecture/launch docs, and package operator guides that still use the old path/package identity.

- [ ] **Step 3: Update current operator documentation only**

In the files listed by `CURRENT_OPERATOR_FILES`:

- change source/install paths to `src/so101_gazebo_demo_cpp` and `install/so101_gazebo_demo_cpp`;
- change `ros2 run`, `ros2 launch`, `ros2 pkg`, and `colcon --packages-*` arguments to `so101_gazebo_demo_cpp`;
- change the architecture label and IDE project name to `so101_gazebo_demo_cpp`;
- add one note to `docs/pick-place-architecture.md`: dated historical experiment/plan/handoff commands and Python provenance continue to show the legacy name intentionally.

Do not run replacement commands over any historical directory.

- [ ] **Step 4: Run the documentation contract and verify GREEN**

Run:

```zsh
cd /data/work/ws_moveit
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/so101_gazebo_demo_cpp/test/test_package_rename_contract.py
```

Expected: all rename-contract tests PASS.

- [ ] **Step 5: Prove historical evidence was not rewritten**

Run:

```zsh
cd /data/work/ws_moveit
git diff --exit-code 65b384ad46c3dbc6b164f84cf409026c5058a527 -- \
  docs/experiments \
  docs/handoffs \
  src/so101_gazebo_demo_py/docs/provenance.json
```

Expected: exit 0 with no diff. For `docs/superpowers/plans` and `docs/superpowers/specs`, inspect `git diff --name-status` and allow only this migration's dated plan/spec documents.

- [ ] **Step 6: Commit current documentation and its contract**

```zsh
cd /data/work/ws_moveit
git add -- \
  .agents/skills/gazebo-video-debug/SKILL.md \
  .agents/skills/so101-dev \
  .idea/.name .idea/misc.xml \
  docs/pick-place-architecture.md docs/pick-place-launch-parameters.md \
  src/pick_place_common/README.md \
  src/so101_gazebo_demo_cpp/README.md \
  src/so101_gazebo_demo_cpp/docs \
  src/so101_gazebo_demo_cpp/test/test_package_rename_contract.py
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
  src/so101_gazebo_demo_cpp/test/test_package_rename_contract.py
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
