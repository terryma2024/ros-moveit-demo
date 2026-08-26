# RGB-D Pick-Place on mujoco_ros2_control 0.1.0 Main Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the qualified RGB-D perception pick-place chain with child `mujoco_ros2_control main@5e9d67c` and prove every cup keyframe on both macOS and ai-station.

**Architecture:** Keep parent `main@b73748f` as the upgrade foundation, advance its immutable child gitlink/locks to the tree-identical formal child main merge, then merge the complete perception branch with history. Validate installed provenance first, followed by isolated full-restart live runs whose only product variable is the MJCF initial keyframe.

**Tech Stack:** ROS 2 Jazzy, MuJoCo, mujoco_ros2_control 0.1.0, MoveIt 2, tf2, Python 3.11, pytest, colcon, Git submodules, tmux, macOS Apple Silicon, Ubuntu Linux x86_64.

**Spec:** `docs/superpowers/specs/2026-08-26-rgbd-pick-place-mujoco-0-1-main-integration-design.md`

## Global Constraints

- Parent baseline is `b73748f86acc891711aa455fc911a9ebde52686d`.
- Perception baseline is `0649f3bdf4e321eb488154ec17484366d0da3895`.
- Final child gitlink and both locks are exactly `5e9d67ce9fde39d35bf94cc498721abf203a0ddd`, labeled `main`.
- The only registered evidence root is `/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/`; on macOS its canonical spelling is `/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/`.
- Preserve all user dirty files and all unrelated local/ai-station worktrees, processes, tmux sessions, and evidence.
- Do not change grasp geometry, policy, camera extrinsics, place target, controller configuration, or recovery behavior without a reproduced RED test.
- Do not run `ament_uncrustify --reformat`, broad process cleanup, destructive Git commands, or evidence deletion.
- Mac must pass four independent keyframes; ai-station must pass the same four plus one fixed-candidate task-start repeat.

---

### Task 1: Freeze the child-main dependency contract with RED -> GREEN

**Files:**
- Modify: `src/so101_demo_py/test/test_macos_install_contract.py`
- Modify: `scripts/check_backend_integration.py`
- Modify: `src/so101_demo_py/config/dependency-lock.yaml`
- Modify: `src/so101_demo_py/config/mujoco/dependency-lock.yaml`
- Modify: `third_party/mujoco_ros2_control` gitlink

**Interfaces:**
- Consumes: child `origin/main@5e9d67c`, upstream ancestry `57fc674`, local lineage `f19a8cc`.
- Produces: exact lock/gitlink/script/test parity on full commit `5e9d67c` and provenance label `main`.

- [ ] **Step 1: Change only the test expectation and observe RED**

Set these constants in `test_macos_install_contract.py`:

```python
CANDIDATE_COMMIT = "5e9d67ce9fde39d35bf94cc498721abf203a0ddd"
CANDIDATE_LABEL = "main"
```

Run:

```bash
source /opt/ros/jazzy/setup.zsh
source /Users/matianyi/ros2_jazzy/extra_ws/install/setup.zsh
source /Users/matianyi/ros2_jazzy/so101_isolated_ws/install/setup.zsh
export VIRTUAL_ENV=/Users/matianyi/ros2_jazzy/.venv
export PATH="/Users/matianyi/ros2_jazzy/.venv/bin:$PATH"
python -m pytest src/so101_demo_py/test/test_macos_install_contract.py -q
```

Expected: the provenance and gitlink tests fail because the two locks and gitlink still select
`aeff7e5` and the candidate label.

- [ ] **Step 2: Advance the immutable child checkout and both locks**

Fetch child `main`, detach at `5e9d67c`, verify `git diff --quiet aeff7e5 5e9d67c`, then update both
YAML files to:

```yaml
fork:
  url: git@gitee.com:zjumty/mujoco_ros2_control.git
  tag: main
  commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
```

Keep `lineage_commit`, `policy_behavior_commit`, upstream commit, interface hashes, required files,
and source ordering unchanged. Update the same two constants in `scripts/check_backend_integration.py`.

- [ ] **Step 3: Verify GREEN and repository integration**

Run the directed pytest command again, then:

```bash
python scripts/check_backend_integration.py
git ls-files --stage -- third_party/mujoco_ros2_control
git -C third_party/mujoco_ros2_control rev-parse HEAD
git -C third_party/mujoco_ros2_control merge-base --is-ancestor aeff7e5a84044f07b8a334e3a15bfc3aa9c8aa5c 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
git diff --check
```

Expected: all commands exit zero; the stage entry, locks, script constant, test constant, and child
HEAD all identify `5e9d67c`.

- [ ] **Step 4: Commit the version contract**

```bash
git add src/so101_demo_py/test/test_macos_install_contract.py scripts/check_backend_integration.py src/so101_demo_py/config/dependency-lock.yaml src/so101_demo_py/config/mujoco/dependency-lock.yaml third_party/mujoco_ros2_control
git commit -m "build: pin mujoco ros2 control 0.1.0 main"
```

---

### Task 2: Merge the qualified RGB-D chain without losing 0.1.0 contracts

**Files:**
- Merge: `origin/codex/rgbd-perception-pick-place@0649f3b`
- Resolve: `src/so101_demo_py/test/test_mujoco_camera_plugin_contract.py`
- Inherit: RGB-D node, TF/keyframe/scene-sync/runner/launch code, tests, docs, and historical ledger from the perception branch

**Interfaces:**
- Consumes: exact child-main version contract from Task 1 and the complete perception branch history.
- Produces: one merge commit containing both 0.1.0 lifecycle contracts and the installed perception runner.

- [ ] **Step 1: Perform a no-fast-forward merge and inventory conflicts**

```bash
git merge --no-ff origin/codex/rgbd-perception-pick-place -m "merge: integrate rgbd pick-place with mujoco 0.1.0 main"
git status --short
git diff --name-only --diff-filter=U
```

Expected: only `test_mujoco_camera_plugin_contract.py` requires content resolution. If another path
conflicts, stop and compare both complete versions before editing.

- [ ] **Step 2: Resolve the camera contract by retaining both requirement sets**

The resolved test must still assert 0.1.0 CameraPlugin registration, interfaces, lifecycle/shutdown
behavior and task-camera `rgb8`/`32FC1`, frame, update-rate, and render configuration. Remove only Git
conflict markers and exact duplicate assertions.

- [ ] **Step 3: Build a merge-check install and run directed integration tests**

Build `so101_demo_py` from the merged worktree into
`/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-merge-check/{build,install,log}`
with `colcon --log-base ... build --base-paths src --packages-select so101_demo_py
--symlink-install`. Source that install after the ROS/dependency overlays, prove
`so101_demo.runtime.launch_composition.__file__` is inside `mac-merge-check/build`, then run:

```bash
python -m pytest \
  src/so101_demo_py/test/test_macos_install_contract.py \
  src/so101_demo_py/test/test_mujoco_camera_plugin_contract.py \
  src/so101_demo_py/test/test_mujoco_cup_test_keyframes.py \
  src/so101_demo_py/test/test_camera_tf_contract.py \
  src/so101_demo_py/test/test_rgbd_point_cloud.py \
  src/so101_demo_py/test/test_rgbd_cup_pose.py \
  src/so101_demo_py/test/test_dynamic_scene_sync.py \
  src/so101_demo_py/test/test_perception_pick_place_launch.py \
  src/so101_demo_py/test/test_perception_launch_runner.py -q
```

Expected: nonzero test discovery and zero failures. Any 0.1.0 compatibility failure enters a new
RED -> GREEN cycle at its owning boundary; do not change motion policy to make it pass.

- [ ] **Step 4: Finish the merge commit**

```bash
git add src/so101_demo_py/test/test_mujoco_camera_plugin_contract.py
git diff --cached --check
git commit
```

Expected: the merge commit has both parent histories and no unmerged paths.

---

### Task 3: Build and qualify the exact Mac install

**Files:**
- Update: `docs/experiments/rgbd-pick-place-mujoco-0-1-main-integration-experiment-ledger.md`
- Evidence only: `/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/`

**Interfaces:**
- Consumes: clean merge candidate and child checkout `5e9d67c`.
- Produces: isolated fork/project installs and passing installed-runtime provenance/tests.

- [ ] **Step 1: Build the four child packages into the task root**

Source only `/opt/ros/jazzy`, `extra_ws`, `so101_isolated_ws`, the MuJoCo vendor overlay required by
the current install guide, and the task fork install. Build `mujoco_3d_lidar`,
`mujoco_ros2_control_msgs`, `mujoco_ros2_control_plugins`, and `mujoco_ros2_control` under
`mac-candidate/fork-build` and `mac-candidate/fork-install`. Record package prefixes and library
paths; zero-package or zero-test output fails the gate.

Additive Task 3 acceptance clarification (CP-002 review round 1): “zero-test output” means zero
accepted test coverage for a selected package, not that every leaf package must register a
standalone CTest. A library/resource or interface-only leaf that intentionally registers no CTest
may pass only when a nonzero installed-artifact or installed-interface consumer suite runs against
the exact candidate overlay and is recorded per leaf. A raw `No tests were found!!!` line is never
sufficient by itself. For CP-002, `mujoco_3d_lidar` is gated by the three-case installed ament/plugin
consumer `test_3d_lidar_plugin`, and `mujoco_ros2_control_msgs` is gated by the 44-case
`test_mujoco_simulation` plus seven-case `test_viewer_camera` consumers (51 cases total). The
project-side installed contract gate additionally requires the nonzero nodeids
`test_macos_install_contract.py::test_installer_builds_exact_upgrade_package_set_and_checks_new_artifacts`
and
`test_macos_install_contract.py::test_integration_guide_reads_back_all_four_fork_package_prefixes`
inside the passing full `src/so101_demo_py/test` suite; these assert the exact four-package set,
required message interfaces/artifacts, and all four candidate prefix readbacks.

- [ ] **Step 2: Build the project package into a separate install**

```bash
colcon --log-base /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-log build \
  --base-paths src \
  --build-base /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-build \
  --install-base /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install \
  --packages-select so101_mujoco_support so101_demo_py --symlink-install
```

- [ ] **Step 3: Prove installed provenance and run all package tests**

Source the task fork install followed by the task project install. Read back `ros2 pkg prefix` for
both `so101_demo_py` and `so101_mujoco_support`; require the support prefix, plugin XML, and platform
plugin dylib/so to come from the task project install. Also read back the installed runner path,
launch path, installed provenance manifest, gitlink, both locks, and child HEAD. Then run all
`src/so101_demo_py/test` tests with ROS logs and pytest cache under the registered root. Expected:
all discovered tests pass, including the directed integration set.

- [ ] **Step 4: Freeze the candidate in the ledger and commit**

Replace every `UNFROZEN_PRE_IMPLEMENTATION` source field with the exact clean candidate commit and
append test counts, prefixes, commands, exit codes, and evidence paths to checkpoint `CP-002`.

```bash
git add docs/experiments/rgbd-pick-place-mujoco-0-1-main-integration-experiment-ledger.md
git commit -m "test: freeze rgbd 0.1.0 main candidate"
```

---

### Task 4: Pass all four Mac FULL_RESTART runs

**Files:**
- Update after each run: `docs/experiments/rgbd-pick-place-mujoco-0-1-main-integration-experiment-ledger.md`
- Evidence only: `/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/`

**Interfaces:**
- Consumes: frozen installed candidate, EXP-010 through EXP-013, and project-local `gui-capture` skill.
- Produces: four countable Mac position results with data and inspected visual evidence.

- [ ] **Step 1: Read `gui-capture`, inspect ownership, and start EXP-010 only**

Confirm no process in domain 220, no matching session/evidence, and no conflicting task Viewer.
Transition EXP-010 `PLANNED -> RUNNING`, commit the ledger transition, then run its exact registered
command and concurrent baseline/transport/final capture in a task-owned tmux session.

- [ ] **Step 2: Close EXP-010 before changing the keyframe**

Evaluate every `AC-001` clause from structured evidence and inspect all three fresh images. Record
natural exit codes and exact owned-process cleanup, transition EXP-010 to `VALID` or `INVALID`, and
commit the closure before EXP-011 starts.

- [ ] **Step 3: Repeat the same frozen protocol for EXP-011, EXP-012, and EXP-013**

Only `mujoco_initial_keyframe`, domain, session/partition, and empty evidence path may change. A
valid behavioral failure stops the batch for systematic debugging; an invalid environment run gets
a new experiment ID and does not count.

- [ ] **Step 4: Summarize Mac coverage**

Append a Mac result table with perceived pose/error, point counts/radius, lift/transport/final pose,
final XY error/tilt/contact, MoveIt/controller evidence, screenshot hashes, exit status, and cleanup
status for all four keyframes. Commit with `test: qualify four mac rgbd pick-place positions` only
when all four are countable successes.

---

### Task 5: Publish the frozen candidate and build it independently on ai-station

**Files:**
- Update: the integration ledger with publication and Linux provenance
- Remote evidence only: `/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/linux-candidate/`

**Interfaces:**
- Consumes: Mac-qualified clean branch and Gitee origin.
- Produces: remote-readable branch and an independent ai-station install of the same commits.

- [ ] **Step 1: Push the branch and verify remote parity**

```bash
git push -u origin codex/rgbd-pick-place-mujoco-0-1-main
git ls-remote origin refs/heads/codex/rgbd-pick-place-mujoco-0-1-main
```

The returned hash must equal local `HEAD`. Publication does not count as Linux functional success.

- [ ] **Step 2: Create a new ai-station isolation root without touching canonical main**

Record canonical `/data/work/ws_moveit` commit/status/submodule, tmux sessions, relevant PIDs, and
ROS graph. Create a new isolated checkout of the pushed candidate under the registered evidence
root, initialize child `5e9d67c`, and verify both repositories are clean.

- [ ] **Step 3: Build and test child and project packages from scratch**

Use `/opt/ros/jazzy/setup.zsh` plus task-only fork/project build/install/log directories. Run the
complete relevant child wrapper/JUnit suite and all project tests with nonzero discovery. Read back
installed prefixes, executable, launch, locks, gitlink, and child ancestry/tree equality.

- [ ] **Step 4: Commit the Linux build checkpoint**

Append exact test counts and installed provenance as `CP-003`, commit, push, and verify remote parity
before live execution.

---

### Task 6: Pass the ai-station four-position and stability batch

**Files:**
- Update after each run: `docs/experiments/rgbd-pick-place-mujoco-0-1-main-integration-experiment-ledger.md`
- Evidence only: `/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/linux-runs/`

**Interfaces:**
- Consumes: exact pushed candidate, EXP-020 through EXP-024, and project-local `gui-capture` skill.
- Produces: four ai-station position successes plus a fifth consecutive fixed-candidate success.

- [ ] **Step 1: Run EXP-020 through the installed exact-status runner**

On ai-station, directly operate in a task-owned tmux session; never SSH ai-station from itself.
Prove domain/session/evidence isolation, transition and commit `RUNNING`, execute the registered
task-start command with fresh capture, close and commit the result, and prove clean owned shutdown.

- [ ] **Step 2: Run EXP-021, EXP-022, and EXP-023 sequentially**

Change only each registered keyframe/domain/session/evidence path. Commit every transition and
closure. Do not start the next full restart until the previous owned graph is absent.

- [ ] **Step 3: Run EXP-024 task-start repeat**

Keep the final source, child commit, policies, install, runner, and acceptance criteria fixed. This
run must be consecutive with EXP-020 through EXP-023; any valid failure ends the batch.

- [ ] **Step 4: Summarize Linux coverage and preserve unrelated processes**

Append the same metric table used for Mac, plus a read-back proving all preserved sessions/PIDs
remain. Commit and push only after all five runs are countable successes.

---

### Task 7: Verify, review, and publish completion

**Files:**
- Finalize: `docs/experiments/rgbd-pick-place-mujoco-0-1-main-integration-experiment-ledger.md`
- Finalize if results clarify instructions: `docs/superpowers/specs/2026-08-26-rgbd-pick-place-mujoco-0-1-main-integration-design.md`

**Interfaces:**
- Consumes: completed automated tests, four Mac runs, five ai-station runs, and all evidence manifests.
- Produces: independently reviewed, remotely readable completion commit and evidence inventory.

- [ ] **Step 1: Run final verification from clean installed environments**

Run directed tests, full package tests, `python scripts/check_backend_integration.py`,
`git diff --check`, lock/gitlink/child parity, and installed executable/launch read-back on both
platforms. Re-read all nine structured results and screenshot manifests.

- [ ] **Step 2: Request independent code/evidence review**

Review the full diff from `b73748f`, conflict resolution, version provenance, test counts, all nine
run gates, screenshots, cleanup, and evidence ownership. Resolve only concrete findings with a RED
test and rerun affected gates.

- [ ] **Step 3: Finalize checkpoint and evidence inventory**

Set `latest_checkpoint` to the completion checkpoint and `next_experiment: NONE`. Report retained
runs, archived runs, and deletion candidates without deleting anything. Generate and verify a
relative SHA256 manifest for decisive logs, JSON, PLY, screenshots, test summaries, and reports.

- [ ] **Step 4: Commit, push, and read back**

```bash
git add docs/experiments/rgbd-pick-place-mujoco-0-1-main-integration-experiment-ledger.md docs/superpowers/specs/2026-08-26-rgbd-pick-place-mujoco-0-1-main-integration-design.md
git diff --cached --check
git commit -m "test: complete dual-platform rgbd pick-place qualification"
git push origin codex/rgbd-pick-place-mujoco-0-1-main
git ls-remote origin refs/heads/codex/rgbd-pick-place-mujoco-0-1-main
```

Expected: remote hash equals local `HEAD`; branch and child worktrees are clean; functional and
publication status are reported separately.
