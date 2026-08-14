# `mujoco_ros2_control` Cross-Platform Patch Series Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Linux and macOS apply the same ordered patch series to the locked `mujoco_ros2_control` commit and prove that both platforms build and test successfully.

**Architecture:** Keep `third_party/mujoco_ros2_control` pinned and clean. Store one topic-oriented series under `scripts/patches/mujoco_ros2_control/`; the installer always restores its independent build source to the locked commit, applies that series on every platform, then builds and verifies the overlay. CMake and C++ `APPLE` guards own the platform differences.

**Tech Stack:** Git submodule and `git apply`, zsh, CMake/ament, colcon, pytest, ROS 2 Jazzy, Apple Clang, GCC/Clang on Ubuntu.

## Global Constraints

- Fork commit remains `738e304551b4ea6db020b466086a13db71b65607`; do not update the tag, gitlink, fork URL, or dependency-lock commit.
- Linux and macOS apply identical patch bytes in identical `series` order.
- Apple-only Objective-C++, Cocoa, CoreVideo, Mach-O, main-thread UI, and CTest dylib handling stay behind `APPLE` or `__APPLE__` guards.
- Linux retains its existing tinyxml2 ELF linker behavior and must not acquire Apple frameworks or Apple-only test dependencies.
- Do not modify SO-101 policies, MJCF, MoveIt behavior, reset lifecycle, or qualification thresholds.
- Preserve existing user work. Do not reset the dirty submodule until its exact diff has been hashed and its semantics have been covered by the new series.
- Use `/tmp/so101-debug-mujoco-portable-patch-series/` as the only task evidence root. Per the user's existing instruction, do not create or update an experiment ledger.
- Do not overwrite the previously verified fork install until the new macOS build and package tests pass.

---

### Task 1: Add Failing Patch-Series Contracts

**Files:**
- Modify: `src/so101_demo_py/test/test_macos_install_contract.py`
- Test: `src/so101_demo_py/test/test_macos_install_contract.py`

**Interfaces:**
- Consumes: locked submodule at `third_party/mujoco_ros2_control` and existing installer at `scripts/install-mujoco-ros2-control.zsh`.
- Produces: `PATCH_SERIES_DIR`, `PATCH_SERIES_FILE`, `_patch_series_entries()`, and contracts that later tasks must satisfy.

- [ ] **Step 1: Record the pre-change provenance**

Run:

```zsh
mkdir -p /tmp/so101-debug-mujoco-portable-patch-series
git rev-parse HEAD | tee /tmp/so101-debug-mujoco-portable-patch-series/main-head.txt
git status --short | tee /tmp/so101-debug-mujoco-portable-patch-series/main-status.txt
git -C third_party/mujoco_ros2_control rev-parse HEAD \
  | tee /tmp/so101-debug-mujoco-portable-patch-series/submodule-head.txt
git -C /Users/matianyi/Projects/robot_demo_001/moveit-demo/third_party/mujoco_ros2_control \
  diff --binary \
  > /tmp/so101-debug-mujoco-portable-patch-series/submodule-before.patch
shasum -a 256 /tmp/so101-debug-mujoco-portable-patch-series/submodule-before.patch \
  | tee /tmp/so101-debug-mujoco-portable-patch-series/submodule-before.sha256
```

Expected: submodule HEAD is `738e304551b4ea6db020b466086a13db71b65607`; the saved patch matches the tracked legacy patch before migration.

- [ ] **Step 2: Write the failing series tests**

Add the following constants and helpers near the existing path constants:

```python
PATCH_SERIES_DIR = REPOSITORY_ROOT / "scripts" / "patches" / "mujoco_ros2_control"
PATCH_SERIES_FILE = PATCH_SERIES_DIR / "series"
SUBMODULE = REPOSITORY_ROOT / "third_party" / "mujoco_ros2_control"
LOCKED_FORK_COMMIT = "738e304551b4ea6db020b466086a13db71b65607"


def _patch_series_entries() -> list[str]:
    return [
        line.strip()
        for line in PATCH_SERIES_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
```

Add contracts with these assertions:

```python
def test_cross_platform_patch_series_is_the_only_authority() -> None:
    entries = _patch_series_entries()
    assert entries
    assert len(entries) == len(set(entries))
    assert all(Path(entry).name == entry and ".." not in entry for entry in entries)
    assert {path.name for path in PATCH_SERIES_DIR.glob("*.patch")} == set(entries)
    assert not (REPOSITORY_ROOT / "patches/mujoco_ros2_control/macos-format-uint64.patch").exists()
    attributes = (REPOSITORY_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "scripts/patches/mujoco_ros2_control/*.patch -whitespace" in attributes


def test_cross_platform_patch_series_round_trips_locked_commit(tmp_path: Path) -> None:
    checkout = tmp_path / "fork"
    subprocess.run(["git", "clone", "--shared", "--no-checkout", str(SUBMODULE), str(checkout)], check=True)
    subprocess.run(["git", "-C", str(checkout), "checkout", "--detach", LOCKED_FORK_COMMIT], check=True)
    entries = _patch_series_entries()
    for entry in entries:
        patch = PATCH_SERIES_DIR / entry
        subprocess.run(["git", "-C", str(checkout), "apply", "--check", str(patch)], check=True)
        subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True)
    heartbeat = (checkout / "mujoco_ros2_control_plugins/src/heartbeat_publisher_plugin.cpp").read_text()
    assert "PRIu64" in heartbeat
    assert 'Published heartbeat #%llu' not in heartbeat
    for entry in reversed(entries):
        subprocess.run(["git", "-C", str(checkout), "apply", "--reverse", str(PATCH_SERIES_DIR / entry)], check=True)
    status = subprocess.run(
        ["git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=all"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert status.stdout == ""


def test_installer_applies_the_same_series_on_every_platform() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")
    assert "patch_series_file=" in installer
    assert "load_patch_series" in installer
    assert 'apply_patch_series "${build_source_dir}"' in installer
    assert "if [[ $(uname -s) == Darwin ]]" not in installer
```

- [ ] **Step 3: Run the tests and verify RED**

Run:

```zsh
direnv exec . python -m pytest -q \
  src/so101_demo_py/test/test_macos_install_contract.py \
  | tee /tmp/so101-debug-mujoco-portable-patch-series/task1-red.log
```

Expected: FAIL because the nested `series` and cross-platform installer functions do not exist and the duplicate root patch still exists.

- [ ] **Step 4: Commit the RED contracts**

```zsh
git add src/so101_demo_py/test/test_macos_install_contract.py
git commit -m "test: require portable mujoco patch series"
```

---

### Task 2: Build the Single Portable Patch Series

**Files:**
- Create: `scripts/patches/mujoco_ros2_control/series`
- Create: `scripts/patches/mujoco_ros2_control/0001-portable-heartbeat-format.patch`
- Create: `scripts/patches/mujoco_ros2_control/0002-platform-build-and-rpath.patch`
- Create: `scripts/patches/mujoco_ros2_control/0003-headless-rendering.patch`
- Create: `scripts/patches/mujoco_ros2_control/0004-apple-main-thread-ui.patch`
- Create: `scripts/patches/mujoco_ros2_control/0005-apple-frameworks.patch`
- Create: `scripts/patches/mujoco_ros2_control/0006-test-runtime-paths.patch`
- Modify: `.gitattributes`
- Delete: `scripts/patches/mujoco-ros2-control-macos*.patch`
- Delete: `patches/mujoco_ros2_control/macos-format-uint64.patch`
- Test: `src/so101_demo_py/test/test_macos_install_contract.py`

**Interfaces:**
- Consumes: the ten legacy patches in their current installer order and the saved submodule diff from Task 1.
- Produces: one `series` manifest whose six patch files apply cleanly to `LOCKED_FORK_COMMIT` on every OS.

- [ ] **Step 1: Create a clean scratch repository and apply the legacy stack**

Run:

```zsh
scratch=/tmp/so101-debug-mujoco-portable-patch-series/patch-authoring
git clone --shared --no-checkout third_party/mujoco_ros2_control "$scratch"
git -C "$scratch" checkout --detach 738e304551b4ea6db020b466086a13db71b65607
for patch in \
  scripts/patches/mujoco-ros2-control-macos.patch \
  scripts/patches/mujoco-ros2-control-macos-platform.patch \
  scripts/patches/mujoco-ros2-control-macos-headless.patch \
  scripts/patches/mujoco-ros2-control-macos-main-thread-ui.patch \
  scripts/patches/mujoco-ros2-control-macos-frameworks.patch \
  scripts/patches/mujoco-ros2-control-macos-test-runtime.patch \
  scripts/patches/mujoco-ros2-control-macos-test-rmw.patch \
  scripts/patches/mujoco-ros2-control-macos-cxx17.patch \
  scripts/patches/mujoco-ros2-control-macos-conversion-warnings.patch \
  scripts/patches/mujoco-ros2-control-macos-test-backward.patch; do
  git -C "$scratch" apply "$PWD/$patch"
done
```

Expected: all ten patches apply to the clean locked commit.

- [ ] **Step 2: Refactor Apple-only test runtime dependencies in the scratch source**

In both test `CMakeLists.txt` files, keep `find_package(rcl_logging_spdlog)`, RMW library-dir discovery, and `find_package(backward_ros)` inside `if(APPLE)`. Define Apple-only helper functions that add `APPEND_LIBRARY_DIRS`; on non-Apple platforms call the original `ament_add_gtest` / `ament_add_pytest_test` signatures without that keyword.

The helper boundary in `mujoco_ros2_control/tests/CMakeLists.txt` must be:

```cmake
if(APPLE)
  find_package(rcl_logging_spdlog REQUIRED)
  find_package(rmw_fastrtps_cpp REQUIRED)
  find_package(rmw_dds_common REQUIRED)
  find_package(backward_ros REQUIRED)
  # Derive APPLE_TEST_LIBRARY_DIRS from the four package prefixes.
endif()

function(add_mujoco_gtest target source)
  if(APPLE)
    ament_add_gtest(${target} ${source} APPEND_LIBRARY_DIRS ${APPLE_TEST_LIBRARY_DIRS})
  else()
    ament_add_gtest(${target} ${source})
  endif()
endfunction()
```

The plugins test CMake uses the same pattern for `test_external_wrench_plugin`. Preserve all existing `target_link_libraries` calls.

- [ ] **Step 3: Split the final diff into six topic commits in the scratch repository**

Use `git add -p` so each commit contains only its named responsibility:

```zsh
git -C "$scratch" add -p mujoco_ros2_control_plugins/src/heartbeat_publisher_plugin.cpp
git -C "$scratch" commit -m "portable heartbeat format"
git -C "$scratch" add -p mujoco_ros2_control/CMakeLists.txt \
  mujoco_ros2_control/src/mujoco_system_interface.cpp \
  mujoco_ros2_control_plugins/CMakeLists.txt
git -C "$scratch" commit -m "platform build and rpath"
git -C "$scratch" add -p mujoco_ros2_control/include/mujoco_ros2_control/mujoco_system_interface.hpp \
  mujoco_ros2_control/src/mujoco_system_interface.cpp \
  mujoco_ros2_control/tests/test_headless_init.cpp
git -C "$scratch" commit -m "headless rendering control"
git -C "$scratch" add -p mujoco_ros2_control/CMakeLists.txt \
  mujoco_ros2_control/include/mujoco_ros2_control/mujoco_system_interface.hpp \
  mujoco_ros2_control/src/mujoco_ros2_control_node.cpp \
  mujoco_ros2_control/src/mujoco_system_interface.cpp \
  mujoco_ros2_control/tests/test_headless_init.cpp
git -C "$scratch" commit -m "Apple main thread UI"
git -C "$scratch" add -p mujoco_ros2_control/CMakeLists.txt
git -C "$scratch" commit -m "Apple framework linkage"
git -C "$scratch" add mujoco_ros2_control/tests/CMakeLists.txt \
  mujoco_ros2_control_plugins/CMakeLists.txt
git -C "$scratch" commit -m "platform test runtime paths"
```

For files shared by multiple commits, accept only the hunks named by the current commit. After the
sixth commit, require `git -C "$scratch" status --short` to be empty; otherwise move each remaining
hunk into its owning topic before export.

Before exporting, require exactly six commits above the locked base:

```zsh
test "$(git -C "$scratch" rev-list --count 738e304551b4ea6db020b466086a13db71b65607..HEAD)" -eq 6
```

- [ ] **Step 4: Export the series and add its manifest**

Run `git format-patch --no-signature --zero-commit --no-stat` into
`scripts/patches/mujoco_ros2_control/`, then rename the generated files to the six exact names in the Files section. Add `series` with this exact order:

```text
0001-portable-heartbeat-format.patch
0002-platform-build-and-rpath.patch
0003-headless-rendering.patch
0004-apple-main-thread-ui.patch
0005-apple-frameworks.patch
0006-test-runtime-paths.patch
```

Add this exact `.gitattributes` rule:

```gitattributes
scripts/patches/mujoco_ros2_control/*.patch -whitespace
```

- [ ] **Step 5: Prove semantic coverage before cleaning the submodule**

Apply the new series in a second clean scratch checkout and compare the three dirty submodule files. Require all CMake hunks from `submodule-before.patch` to appear in the new result; accept the heartbeat difference only when the new source uses `<cinttypes>` and `PRIu64` instead of `%llu`.

Save the comparison:

```zsh
git -C "$scratch" diff 738e304551b4ea6db020b466086a13db71b65607 \
  > /tmp/so101-debug-mujoco-portable-patch-series/new-series.patch
shasum -a 256 /tmp/so101-debug-mujoco-portable-patch-series/new-series.patch \
  | tee /tmp/so101-debug-mujoco-portable-patch-series/new-series.sha256
```

- [ ] **Step 6: Remove the duplicate source while preserving the original worktree**

The isolated implementation worktree already has a clean submodule. Verify it remains clean, then
delete the duplicate tracked patch from the feature branch. Do not alter the original main worktree's
submodule during implementation:

```zsh
test -z "$(git -C third_party/mujoco_ros2_control status --porcelain --untracked-files=all)"
cmp -s \
  /tmp/so101-debug-mujoco-portable-patch-series/submodule-before.patch \
  patches/mujoco_ros2_control/macos-format-uint64.patch
```

Delete the ten legacy `scripts/patches/mujoco-ros2-control-macos*.patch` files and the duplicate root
patch only after both assertions succeed. After cross-platform validation and local branch integration,
the original main worktree can reverse that exact tracked patch to restore its submodule without loss.

- [ ] **Step 7: Run the authority and round-trip tests**

```zsh
direnv exec . python -m pytest -q \
  src/so101_demo_py/test/test_macos_install_contract.py \
  -k 'patch_series or portable' \
  | tee /tmp/so101-debug-mujoco-portable-patch-series/task2-series.log
```

Expected: series authority and round-trip tests PASS; installer contract may remain RED until Task 3.

- [ ] **Step 8: Commit the portable series**

```zsh
git add .gitattributes scripts/patches/mujoco_ros2_control \
  scripts/patches patches/mujoco_ros2_control \
  third_party/mujoco_ros2_control
git commit -m "build: consolidate portable mujoco patch series"
```

Before committing, inspect `git diff --cached --name-status` and require the submodule gitlink to be unchanged.

---

### Task 3: Make the Installer Apply the Series on Every Platform

**Files:**
- Modify: `scripts/install-mujoco-ros2-control.zsh`
- Modify: `src/so101_demo_py/test/test_macos_install_contract.py`
- Test: `src/so101_demo_py/test/test_macos_install_contract.py`

**Interfaces:**
- Consumes: `scripts/patches/mujoco_ros2_control/series` from Task 2.
- Produces: `load_patch_series()` and `apply_patch_series(source_dir: path)` shell functions; both platforms invoke the same `apply_patch_series "${build_source_dir}"` call.

- [ ] **Step 1: Update the old installer test to assert the series instead of ten filenames**

Replace the ten filename assertions with:

```python
assert "patch_series_file=" in installer
assert "load_patch_series" in installer
assert 'apply_patch_series "${build_source_dir}"' in installer
assert "if [[ $(uname -s) == Darwin ]]" not in installer
```

- [ ] **Step 2: Run the installer contract and confirm RED**

```zsh
direnv exec . python -m pytest -q \
  src/so101_demo_py/test/test_macos_install_contract.py::test_installer_applies_the_same_series_on_every_platform
```

Expected: FAIL because the installer still contains the Darwin gate and hard-coded array.

- [ ] **Step 3: Implement strict series loading**

In `resolve_project_root()`, set:

```zsh
patch_series_dir=${project_root}/scripts/patches/mujoco_ros2_control
patch_series_file=${patch_series_dir}/series
```

Implement:

```zsh
load_patch_series() {
  [[ -f ${patch_series_file} ]] || fail "patch series is missing: ${patch_series_file}"
  portable_patches=()
  local entry
  while IFS= read -r entry || [[ -n ${entry} ]]; do
    [[ -z ${entry} || ${entry} == \#* ]] && continue
    [[ ${entry} != /* && ${entry} != *..* && ${entry} == ${entry:t} ]] ||
      fail "invalid patch series entry: ${entry}"
    [[ -f ${patch_series_dir}/${entry} ]] || fail "series patch is missing: ${entry}"
    (( ${portable_patches[(Ie)${patch_series_dir}/${entry}]} == 0 )) ||
      fail "duplicate patch series entry: ${entry}"
    portable_patches+=("${patch_series_dir}/${entry}")
  done < "${patch_series_file}"
  (( ${#portable_patches} > 0 )) || fail "patch series is empty"
}
```

Call it after `resolve_project_root` and before preparing the build source.

- [ ] **Step 4: Implement unconditional idempotent application**

Replace the Darwin-only block with:

```zsh
apply_patch_series() {
  local source_dir=$1 patch_index portable_patch
  for (( patch_index=${#portable_patches}; patch_index >= 1; --patch_index )); do
    portable_patch=${portable_patches[patch_index]}
    if git -C "${source_dir}" apply --reverse --check "${portable_patch}" 2>/dev/null; then
      git -C "${source_dir}" apply --reverse "${portable_patch}"
    fi
  done
  [[ -z $(git -C "${source_dir}" status --porcelain --untracked-files=all) ]] ||
    fail "build source contains changes outside the approved patch series: ${source_dir}"
  for portable_patch in "${portable_patches[@]}"; do
    git -C "${source_dir}" apply --check "${portable_patch}" ||
      fail "portable patch does not apply cleanly: ${portable_patch}"
    git -C "${source_dir}" apply "${portable_patch}"
  done
}
```

`prepare_build_source()` calls `apply_patch_series "${build_source_dir}"` without an OS condition.

- [ ] **Step 5: Run the full contract file GREEN**

```zsh
direnv exec . python -m pytest -q \
  src/so101_demo_py/test/test_macos_install_contract.py \
  | tee /tmp/so101-debug-mujoco-portable-patch-series/task3-contracts.log
```

Expected: all tests PASS.

- [ ] **Step 6: Commit the installer**

```zsh
git add scripts/install-mujoco-ros2-control.zsh \
  src/so101_demo_py/test/test_macos_install_contract.py
git commit -m "build: apply mujoco patches on every platform"
```

---

### Task 4: Rebuild and Validate on macOS

**Files:**
- Test: fork package tests through `scripts/install-mujoco-ros2-control.zsh`
- Evidence: `/tmp/so101-debug-mujoco-portable-patch-series/macos-*`

**Interfaces:**
- Consumes: clean submodule, series, and cross-platform installer from Tasks 2–3.
- Produces: macOS build/test evidence and a candidate fork overlay at
  `~/ros2_jazzy/portable_patch_candidate/ws_mujoco_ros2_control_fork/install` without replacing the
  previously qualified overlay.

- [ ] **Step 1: Verify clean inputs**

```zsh
test -z "$(git -C third_party/mujoco_ros2_control status --porcelain --untracked-files=all)"
git -C third_party/mujoco_ros2_control rev-parse HEAD
direnv exec . python -m pytest -q src/so101_demo_py/test/test_macos_install_contract.py
```

Expected: locked commit, zero submodule diff, all contracts PASS.

- [ ] **Step 2: Run the macOS installer into an isolated candidate workspace**

```zsh
SO101_WORKSPACE_DIR=~/ros2_jazzy/portable_patch_candidate \
SO101_ROS_UNDERLAY=/opt/ros/jazzy \
SO101_ROS_DEPENDENCY_OVERLAY=~/ros2_jazzy/extra_ws/install \
./scripts/install-mujoco-ros2-control.zsh \
  |& tee /tmp/so101-debug-mujoco-portable-patch-series/macos-installer.log
```

Expected: three fork packages build; all fork tests pass; installer prefix checks pass.

- [ ] **Step 3: Verify macOS linkage and installed provenance**

```zsh
source /opt/ros/jazzy/setup.zsh
source ~/ros2_jazzy/extra_ws/install/setup.zsh
source ~/ros2_jazzy/portable_patch_candidate/ws_mujoco_ros2_control_fork/install/setup.zsh
ros2 pkg prefix mujoco_ros2_control
otool -L ~/ros2_jazzy/portable_patch_candidate/ws_mujoco_ros2_control_fork/install/lib/libmujoco_ros2_control.dylib
ros2 interface show mujoco_ros2_control_msgs/srv/ResetWorld
ros2 interface show mujoco_ros2_control_msgs/srv/SetPause
ros2 interface show mujoco_ros2_control_msgs/srv/StepSimulation
```

Expected: fork prefix is the fork overlay; Mach-O dependencies resolve; all three interfaces are discoverable.

- [ ] **Step 4: Run a bounded headless smoke**

Use the installed `so101_demo_py` overlay and a unique domain; launch headless only long enough to observe control-node readiness and reset/pause/step services, then stop the owned launch cleanly. Save the command, service list, exit code, and logs under the task evidence root. Do not count this as a qualification run.

- [ ] **Step 5: Commit any macOS-only guard correction**

If the build required patch correction, rerun Tasks 2–4 contracts and commit only the patch changes:

```zsh
git add scripts/patches/mujoco_ros2_control src/so101_demo_py/test/test_macos_install_contract.py
git commit -m "fix: preserve macos mujoco runtime in portable series"
```

If no correction was needed, do not create an empty commit.

---

### Task 5: Build the Same Series on Linux / ai-station

**Files:**
- No source changes unless Linux exposes an incorrect platform boundary.
- Evidence: `/tmp/so101-debug-mujoco-portable-patch-series/linux-*` locally and one matching temporary evidence root on ai-station.

**Interfaces:**
- Consumes: the exact local implementation commits and patch series proven on macOS.
- Produces: Linux build/test/linkage evidence for the same commit, fork commit, and series SHA-256.

- [ ] **Step 1: Capture the exact snapshot identity**

```zsh
git rev-parse HEAD | tee /tmp/so101-debug-mujoco-portable-patch-series/candidate-head.txt
shasum -a 256 scripts/patches/mujoco_ros2_control/series \
  scripts/patches/mujoco_ros2_control/*.patch \
  | tee /tmp/so101-debug-mujoco-portable-patch-series/series-sha256.txt
git bundle create /tmp/so101-debug-mujoco-portable-patch-series/candidate.bundle \
  origin/main..HEAD
```

- [ ] **Step 2: Inspect ai-station before creating an isolated checkout**

Read the ai-station access reference, then record its `pwd`, branch, HEAD, status, submodule status, existing ROS processes, and available disk. Do not alter its active `/data/work/ws_moveit` checkout or running stack.

- [ ] **Step 3: Transfer the bundle and create a temporary isolated checkout**

Use the fixed isolated paths below and fail if they already exist; do not delete or reuse an earlier
checkout:

```zsh
(cd /tmp/so101-debug-mujoco-portable-patch-series && \
  shasum -a 256 candidate.bundle > candidate.bundle.sha256)
scp /tmp/so101-debug-mujoco-portable-patch-series/candidate.bundle \
  /tmp/so101-debug-mujoco-portable-patch-series/candidate.bundle.sha256 \
  ai-station:/tmp/
ssh ai-station 'set -e
  test ! -e /data/work/so101-portable-patch-series
  mkdir -p /data/work/so101-portable-patch-series
  mkdir -p /tmp/so101-debug-mujoco-portable-patch-series
  cd /tmp
  shasum -a 256 -c candidate.bundle.sha256
  git clone --no-checkout /data/work/ws_moveit \
    /data/work/so101-portable-patch-series/moveit-demo
  git -C /data/work/so101-portable-patch-series/moveit-demo \
    fetch /tmp/candidate.bundle HEAD
  git -C /data/work/so101-portable-patch-series/moveit-demo \
    checkout --detach FETCH_HEAD
  git -C /data/work/so101-portable-patch-series/moveit-demo \
    submodule update --init -- third_party/mujoco_ros2_control
  git -C /data/work/so101-portable-patch-series/moveit-demo status --short
  git -C /data/work/so101-portable-patch-series/moveit-demo \
    submodule status third_party/mujoco_ros2_control'
```

Expected: transferred hash passes, checkout HEAD equals `candidate-head.txt`, submodule is the locked
commit, and status is clean.

- [ ] **Step 4: Run the same installer on Linux**

In the isolated Linux checkout:

```zsh
source /opt/ros/jazzy/setup.zsh
SO101_WORKSPACE_DIR=/data/work/so101-portable-patch-series/runtime \
SO101_ROS_UNDERLAY=/opt/ros/jazzy \
SO101_ROS_DEPENDENCY_OVERLAY=/opt/ros/jazzy \
./scripts/install-mujoco-ros2-control.zsh \
  |& tee /tmp/so101-debug-mujoco-portable-patch-series/linux-installer.log
```

Expected: the installer logs the same six series entries, builds the three packages, and reports all package tests passing.

- [ ] **Step 5: Verify Linux linkage and behavior boundary**

```zsh
source /opt/ros/jazzy/setup.zsh
source /data/work/so101-portable-patch-series/runtime/ws_mujoco_ros2_control_fork/install/setup.zsh
ros2 pkg prefix mujoco_ros2_control
readelf -d /data/work/so101-portable-patch-series/runtime/ws_mujoco_ros2_control_fork/install/lib/libmujoco_ros2_control.so \
  | tee /tmp/so101-debug-mujoco-portable-patch-series/linux-readelf.txt
ldd /data/work/so101-portable-patch-series/runtime/ws_mujoco_ros2_control_fork/install/lib/libmujoco_ros2_control.so \
  | tee /tmp/so101-debug-mujoco-portable-patch-series/linux-ldd.txt
rg -n 'Cocoa|CoreVideo|AppKit' \
  /tmp/so101-debug-mujoco-portable-patch-series/linux-readelf.txt \
  /tmp/so101-debug-mujoco-portable-patch-series/linux-ldd.txt && exit 1 || true
ros2 interface show mujoco_ros2_control_msgs/srv/ResetWorld
ros2 interface show mujoco_ros2_control_msgs/srv/SetPause
ros2 interface show mujoco_ros2_control_msgs/srv/StepSimulation
```

Also inspect the generated Linux link command and require the tinyxml2 `--push-state,--no-as-needed` path to remain present.

- [ ] **Step 6: Run a bounded Linux headless smoke**

Launch the control node in an isolated `ROS_DOMAIN_ID`, confirm reset/pause/step service discovery, then cleanly stop only the owned process group. Record the exact source commit, install prefix, executable, domain, service list, and exit code. No GUI or physical qualification is required for this build-boundary change.

- [ ] **Step 7: Handle Linux failures without restoring an OS apply gate**

If Linux fails, reproduce the first compile/link/test boundary locally in the isolated checkout, tighten the relevant `APPLE` guard in the scratch source, regenerate the affected topic patch, rerun round-trip tests, macOS build/tests, then repeat Linux. Never change the installer back to “apply only on Darwin”.

---

### Task 6: Update Documentation and Run Final Gates

**Files:**
- Modify: `docs/guides/macos-apple-silicon-ros2-jazzy-so101-mujoco.md`
- Modify: `README.md` only if its build entry needs the new portable-series wording.
- Test: `src/so101_demo_py/test/test_macos_install_contract.py`

**Interfaces:**
- Consumes: verified cross-platform series and evidence from Tasks 4–5.
- Produces: concise maintainer instructions and final completion evidence.

- [ ] **Step 1: Document the portable-series rule**

Replace wording that says the installer applies “macOS patches” with:

```text
安装器在 Linux 和 macOS 上都对固定 fork commit 重放同一
scripts/patches/mujoco_ros2_control/series。平台差异由补丁后源码中的
APPLE / __APPLE__ 条件分支控制；submodule 必须保持 clean。
```

Document how to add a patch: create it against the locked clean commit, append it to `series`, run the round-trip contract, then run both platform builds.

- [ ] **Step 2: Run all final static gates**

```zsh
direnv exec . python -m pytest -q src/so101_demo_py/test/test_macos_install_contract.py
zsh -n scripts/install-mujoco-ros2-control.zsh
git diff --check
test -z "$(git -C third_party/mujoco_ros2_control status --porcelain --untracked-files=all)"
```

Expected: all tests PASS, syntax and diff checks pass, submodule is clean.

- [ ] **Step 3: Compare final platform evidence**

Require both platform reports to contain the same candidate HEAD, fork commit, `series` SHA-256 list, and six entries. Record macOS and Linux build/test counts separately; do not infer one from the other.

- [ ] **Step 4: Commit documentation**

```zsh
git add docs/guides/macos-apple-silicon-ros2-jazzy-so101-mujoco.md README.md
git commit -m "docs: explain portable mujoco patch workflow"
```

- [ ] **Step 5: Report evidence retention**

Report:

- retained: `/tmp/so101-debug-mujoco-portable-patch-series/` and the matching ai-station temporary evidence root;
- archived: none unless a superseded durable Linux batch was explicitly moved;
- deletion candidates: scratch authoring checkout, transferred bundle, and isolated Linux checkout, but do not delete them without explicit user authorization.

Final completion requires both platform build/test results, clean submodule, one authoritative series, and no remaining duplicate patch.
