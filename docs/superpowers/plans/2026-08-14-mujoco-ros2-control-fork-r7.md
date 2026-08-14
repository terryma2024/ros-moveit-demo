# `mujoco_ros2_control` Fork r7 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the existing eleven portable `mujoco_ros2_control` changes as eleven auditable commits in the Gitee fork, validate the exact clean candidate on macOS and Linux, tag it `so101-0.0.3-r7`, and make `moveit-demo` build that clean fork commit without replaying patches.

**Architecture:** Treat fork Git history as the only implementation authority. First add a failing superproject contract for the r7 end state, then convert the current mail patch series into eleven fork commits and validate the immutable candidate on both platforms. Only after those gates pass may the fork `main` fast-forward and the annotated r7 tag be published. Finally update the superproject gitlink and locks, remove patch application from the installer, prove a fresh Gitee checkout on both platforms, and commit the integration.

**Tech Stack:** Git/Gitee, Git submodule and annotated tags, zsh, Python/pytest, CMake/ament, colcon, ROS 2 Jazzy, MuJoCo, Apple Clang/Mach-O tools, Ubuntu ELF tools, SSH to `ai-station`.

## Global Constraints

- Work only in `/Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/mujoco-portable-patch-series` on branch `codex/mujoco-portable-patch-series`.
- Preserve the dirty primary worktree at `/Users/matianyi/Projects/robot_demo_001/moveit-demo`; do not reset, stash, clean, checkout, or stage its files or dirty submodule.
- Use `/tmp/so101-debug-mujoco-fork-r7/` as this task's sole ordinary evidence root on each machine. Do not create or update an experiment ledger. Do not count the bounded service smoke as a qualification batch.
- Do not delete candidate source, bundles, build/install trees, or evidence. Report retained paths, archived paths, and deletion candidates at handoff.
- Build ROS 2 dependencies into isolated overlays. Never write package content into `/opt/ros/jazzy`; on macOS it remains the Ubuntu-compatible symlinked source install prefix.
- The fork remote is Gitee. Use ordinary Git commands, never `gh`, and never force-push. If Gitee `main` is not exactly r6 immediately before publication, stop.
- Do not run `ament_uncrustify --reformat`. Formatting changes must be targeted edits.
- Keep `fork.policy_behavior_commit` at `f42b7b3d77288c2fee750fe53b0258e0a3d18194`: r7 changes build/runtime portability, not the qualified contact-policy behavior boundary.
- Fixed identities:
  - r6 commit: `738e304551b4ea6db020b466086a13db71b65607`
  - upstream 0.0.3 commit: `35ba8174b62d9560093614f981a3d4b978a96036`
  - expected r6-to-r7 binary diff SHA-256: `56b2f1033ccf48b44be6db8daee800f3f4d463048bd6cf2a7f8e58549ebde2f5`
  - candidate branch inside the fork checkout: `codex/portable-macos-linux-r7`
  - release tag: `so101-0.0.3-r7`

---

### Task 1: Freeze Inputs and Add the RED r7 Authority Contract

**Files:**
- Modify: `src/so101_demo_py/test/test_macos_install_contract.py`
- Evidence: `/tmp/so101-debug-mujoco-fork-r7/preflight/`

**Interfaces:**
- Consumes: clean feature worktree HEAD `5e7abd5`, clean r6 submodule, two r6 locks, and the eleven tracked mail patches.
- Produces: a committed failing contract that describes the r7-only authority boundary without changing production behavior.

- [ ] **Step 1: Re-read the required SO-101 acceptance and ai-station rules**

Read completely before task actions:

```zsh
sed -n '1,260p' .agents/skills/so101-dev/SKILL.md
sed -n '1,320p' .agents/skills/so101-dev/references/test-and-acceptance.md
sed -n '1,320p' .agents/skills/so101-dev/references/ai-station-access.md
```

Expected: the executor confirms the single evidence root, exact-process cleanup boundary, overlay discovery gates, and no-ledger exception from the user.

- [ ] **Step 2: Record immutable local preflight state**

```zsh
mkdir -p /tmp/so101-debug-mujoco-fork-r7/preflight
git status --short --branch \
  | tee /tmp/so101-debug-mujoco-fork-r7/preflight/feature-status.txt
git rev-parse HEAD \
  | tee /tmp/so101-debug-mujoco-fork-r7/preflight/feature-head.txt
git -C third_party/mujoco_ros2_control status --short --branch \
  | tee /tmp/so101-debug-mujoco-fork-r7/preflight/fork-status.txt
git -C third_party/mujoco_ros2_control rev-parse HEAD \
  | tee /tmp/so101-debug-mujoco-fork-r7/preflight/fork-head.txt
git ls-tree HEAD -- third_party/mujoco_ros2_control \
  | tee /tmp/so101-debug-mujoco-fork-r7/preflight/gitlink.txt
git ls-remote git@gitee.com:zjumty/mujoco_ros2_control.git \
  refs/heads/main refs/tags/so101-0.0.3-r6 'refs/tags/so101-0.0.3-r6^{}' \
  | tee /tmp/so101-debug-mujoco-fork-r7/preflight/gitee-r6.txt
```

Expected: feature worktree and isolated submodule are clean; submodule, gitlink, Gitee `main`, and peeled r6 tag all resolve to `738e304551b4ea6db020b466086a13db71b65607`. Stop if any identity differs.

- [ ] **Step 3: Replace patch-authority tests with r7 end-state tests**

In `src/so101_demo_py/test/test_macos_install_contract.py`:

1. Add `hashlib` and `yaml` imports.
2. Replace `LOCKED_FORK_COMMIT` with these constants:

```python
R6_FORK_COMMIT = "738e304551b4ea6db020b466086a13db71b65607"
EXPECTED_PORTABLE_DIFF_SHA256 = (
    "56b2f1033ccf48b44be6db8daee800f3f4d463048bd6cf2a7f8e58549ebde2f5"
)
LOCK = REPOSITORY_ROOT / "src/so101_demo_py/config/mujoco/dependency-lock.yaml"
RUNTIME_LOCK = REPOSITORY_ROOT / "src/so101_demo_py/config/dependency-lock.yaml"
```

3. Delete `_patch_series_entries()`, `test_cross_platform_patch_series_is_the_only_authority()`, `test_cross_platform_patch_series_round_trips_locked_commit()`, `test_installer_applies_the_same_series_on_every_platform()`, and `test_mujoco_installer_applies_portable_series_to_build_copy()`.
4. Add helpers that load both YAML locks and run Git with `capture_output=True`, `text=True`, and `check=True`.
5. Add these tests:

```python
def test_r7_fork_is_the_only_portable_source_authority() -> None:
    lock = yaml.safe_load(LOCK.read_text(encoding="utf-8"))
    runtime_lock = yaml.safe_load(RUNTIME_LOCK.read_text(encoding="utf-8"))
    assert lock["fork"]["tag"] == "so101-0.0.3-r7"
    assert runtime_lock["fork"]["tag"] == "so101-0.0.3-r7"
    assert runtime_lock["fork"]["commit"] == lock["fork"]["commit"]
    assert runtime_lock["fork"]["policy_behavior_commit"] == lock["fork"]["policy_behavior_commit"]
    assert not PATCH_SERIES_DIR.exists()
    attributes = (REPOSITORY_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "scripts/patches/mujoco_ros2_control" not in attributes


def test_r7_gitlink_history_and_portable_bytes_are_exact() -> None:
    lock = yaml.safe_load(LOCK.read_text(encoding="utf-8"))
    locked_commit = lock["fork"]["commit"]
    gitlink = subprocess.run(
        ["git", "ls-files", "--stage", "--", "third_party/mujoco_ros2_control"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()[2]
    assert gitlink == locked_commit
    assert subprocess.run(
        ["git", "-C", str(SUBMODULE), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip() == locked_commit
    assert subprocess.run(
        ["git", "-C", str(SUBMODULE), "status", "--porcelain", "--untracked-files=all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout == ""
    subprocess.run(
        ["git", "-C", str(SUBMODULE), "merge-base", "--is-ancestor", R6_FORK_COMMIT, locked_commit],
        check=True,
    )
    subjects = subprocess.run(
        ["git", "-C", str(SUBMODULE), "log", "--format=%s", "--reverse", f"{R6_FORK_COMMIT}..{locked_commit}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert subjects == [
        "portable heartbeat format",
        "platform build and rpath",
        "headless rendering control",
        "Apple main thread UI",
        "Apple framework linkage",
        "Apple test logging runtime",
        "Apple test RMW runtime",
        "platform C++17 requirements",
        "Apple conversion warnings",
        "Apple test backward runtime",
        "guard Apple test runtime dependencies",
    ]
    portable_diff = subprocess.run(
        ["git", "-C", str(SUBMODULE), "diff", "--binary", f"{R6_FORK_COMMIT}..{locked_commit}"],
        check=True,
        capture_output=True,
    ).stdout
    assert hashlib.sha256(portable_diff).hexdigest() == EXPECTED_PORTABLE_DIFF_SHA256


def test_installer_builds_a_clean_locked_fork_without_patch_application() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")
    for forbidden in (
        "patch_series",
        "portable_patches",
        "apply_patch_series",
        "git apply",
        "if [[ $(uname -s) == Darwin ]]",
    ):
        assert forbidden not in installer
    assert '--base-paths "${build_source_dir}"' in installer
    assert 'status --porcelain --untracked-files=all' in installer
    assert "build source must be clean" in installer
```

- [ ] **Step 4: Run the narrow test and confirm the intended RED failures**

```zsh
direnv exec . python -m pytest -q \
  src/so101_demo_py/test/test_macos_install_contract.py \
  -k 'r7 or clean_locked_fork' \
  |& tee /tmp/so101-debug-mujoco-fork-r7/preflight/red-contract.log
```

Expected: failures specifically report r6 instead of r7, the existing patch directory, and patch-application code. Unexpected import, syntax, or fixture errors must be fixed before continuing.

- [ ] **Step 5: Commit only the RED contract**

```zsh
git add src/so101_demo_py/test/test_macos_install_contract.py
git diff --cached --check
git commit -m "test: require clean mujoco fork r7 authority"
```

Expected: one superproject test commit; production files and submodule gitlink remain unchanged.

---

### Task 2: Convert the Eleven Mail Patches into the Clean Fork Candidate

**Files:**
- Modify in submodule: the eight files touched by `scripts/patches/mujoco_ros2_control/series`
- Evidence: `/tmp/so101-debug-mujoco-fork-r7/candidate/`

**Interfaces:**
- Consumes: exact r6 fork commit and the ordered mail patch series.
- Produces: branch `codex/portable-macos-linux-r7` with exactly eleven commits and a clean worktree; it is not pushed in this task.

- [ ] **Step 1: Prove the remote publication base has not moved**

```zsh
mkdir -p /tmp/so101-debug-mujoco-fork-r7/candidate
remote_main=$(git -C third_party/mujoco_ros2_control ls-remote origin refs/heads/main | awk '{print $1}')
test "${remote_main}" = 738e304551b4ea6db020b466086a13db71b65607
test -z "$(git -C third_party/mujoco_ros2_control ls-remote origin \
  refs/tags/so101-0.0.3-r7 'refs/tags/so101-0.0.3-r7^{}')"
git -C third_party/mujoco_ros2_control fetch origin main --tags
git -C third_party/mujoco_ros2_control merge-base --is-ancestor \
  35ba8174b62d9560093614f981a3d4b978a96036 \
  738e304551b4ea6db020b466086a13db71b65607
```

Expected: remote main is r6, r7 does not exist, and upstream 0.0.3 is an ancestor. If not, stop without rebasing or overwriting anything.

- [ ] **Step 2: Create the isolated fork branch at r6**

```zsh
test -z "$(git -C third_party/mujoco_ros2_control status --porcelain --untracked-files=all)"
git -C third_party/mujoco_ros2_control switch -c \
  codex/portable-macos-linux-r7 \
  738e304551b4ea6db020b466086a13db71b65607
```

Expected: the submodule is on the new local branch at r6 and remains clean.

- [ ] **Step 3: Apply each mail patch as one Git commit in series order**

```zsh
for patch_name in ${(f)"$(<scripts/patches/mujoco_ros2_control/series)"}; do
  git -C third_party/mujoco_ros2_control am \
    "$(pwd)/scripts/patches/mujoco_ros2_control/${patch_name}"
done
```

Expected: eleven `git am` operations succeed. If any fails, save `.git/rebase-apply/patch` and stderr under the evidence root, run `git -C third_party/mujoco_ros2_control am --abort`, and correct the source mail patch in the superproject with a targeted change before restarting all eleven commits from r6.

- [ ] **Step 4: Verify count, subjects, clean state, and exact bytes**

```zsh
candidate_commit=$(git -C third_party/mujoco_ros2_control rev-parse HEAD)
print -r -- "${candidate_commit}" \
  | tee /tmp/so101-debug-mujoco-fork-r7/candidate/candidate-commit.txt
git -C third_party/mujoco_ros2_control rev-list --count \
  738e304551b4ea6db020b466086a13db71b65607..HEAD \
  | tee /tmp/so101-debug-mujoco-fork-r7/candidate/commit-count.txt
git -C third_party/mujoco_ros2_control log --format='%H %s' --reverse \
  738e304551b4ea6db020b466086a13db71b65607..HEAD \
  | tee /tmp/so101-debug-mujoco-fork-r7/candidate/commit-series.txt
git -C third_party/mujoco_ros2_control diff --binary \
  738e304551b4ea6db020b466086a13db71b65607..HEAD \
  | shasum -a 256 \
  | tee /tmp/so101-debug-mujoco-fork-r7/candidate/portable-diff-sha256.txt
test -z "$(git -C third_party/mujoco_ros2_control status --porcelain --untracked-files=all)"
```

Expected: count `11`, the exact subject order from Task 1, clean status, and SHA-256 `56b2f1033ccf48b44be6db8daee800f3f4d463048bd6cf2a7f8e58549ebde2f5`.

- [ ] **Step 5: Run fork-local static gates before platform builds**

```zsh
git -C third_party/mujoco_ros2_control diff --check \
  738e304551b4ea6db020b466086a13db71b65607..HEAD
rg -n '<<<<<<<|=======|>>>>>>>' \
  third_party/mujoco_ros2_control/mujoco_ros2_control \
  third_party/mujoco_ros2_control/mujoco_ros2_control_plugins
```

Expected: `git diff --check` passes and ripgrep finds no conflict markers.

---

### Task 3: Build and Validate the Unpublished Candidate on macOS

**Files:**
- Test: the three fork packages from `third_party/mujoco_ros2_control`
- Evidence: `/tmp/so101-debug-mujoco-fork-r7/macos-candidate/`
- Retained build: `/Users/matianyi/ros2_jazzy/fork_r7_candidate_20260814/`

**Interfaces:**
- Consumes: the exact clean candidate commit, `/opt/ros/jazzy`, and `/Users/matianyi/ros2_jazzy/extra_ws/install`.
- Produces: macOS compile/test/linkage evidence without changing the previously validated fork overlay.

- [ ] **Step 1: Create new evidence and build roots without deleting prior state**

```zsh
mkdir -p /tmp/so101-debug-mujoco-fork-r7/macos-candidate
test ! -e /Users/matianyi/ros2_jazzy/fork_r7_candidate_20260814
mkdir -p /Users/matianyi/ros2_jazzy/fork_r7_candidate_20260814
test -z "$(git -C third_party/mujoco_ros2_control status --porcelain --untracked-files=all)"
```

Expected: the fixed candidate root is new. If it already exists, stop and inspect it; do not remove or reuse it silently.

- [ ] **Step 2: Build the three packages directly from the clean candidate**

```zsh
source /Users/matianyi/ros2_jazzy/.venv/bin/activate
source /opt/ros/jazzy/setup.zsh
source /Users/matianyi/ros2_jazzy/extra_ws/install/setup.zsh
colcon --log-base /Users/matianyi/ros2_jazzy/fork_r7_candidate_20260814/log build \
  --base-paths third_party/mujoco_ros2_control \
  --build-base /Users/matianyi/ros2_jazzy/fork_r7_candidate_20260814/build \
  --install-base /Users/matianyi/ros2_jazzy/fork_r7_candidate_20260814/install \
  --merge-install \
  --cmake-clean-cache \
  --cmake-args -DFETCHCONTENT_UPDATES_DISCONNECTED=ON \
  --packages-select \
    mujoco_ros2_control_msgs \
    mujoco_ros2_control_plugins \
    mujoco_ros2_control \
  |& tee /tmp/so101-debug-mujoco-fork-r7/macos-candidate/build.log
```

Expected: all three packages finish successfully from the candidate checkout.

- [ ] **Step 3: Run all candidate package tests and inspect counts**

```zsh
source /Users/matianyi/ros2_jazzy/fork_r7_candidate_20260814/install/setup.zsh
colcon --log-base /Users/matianyi/ros2_jazzy/fork_r7_candidate_20260814/log test \
  --base-paths third_party/mujoco_ros2_control \
  --build-base /Users/matianyi/ros2_jazzy/fork_r7_candidate_20260814/build \
  --install-base /Users/matianyi/ros2_jazzy/fork_r7_candidate_20260814/install \
  --merge-install \
  --packages-select \
    mujoco_ros2_control_msgs \
    mujoco_ros2_control_plugins \
    mujoco_ros2_control \
  --event-handlers console_direct+ \
  |& tee /tmp/so101-debug-mujoco-fork-r7/macos-candidate/test.log
colcon test-result \
  --test-result-base /Users/matianyi/ros2_jazzy/fork_r7_candidate_20260814/build \
  --verbose \
  |& tee /tmp/so101-debug-mujoco-fork-r7/macos-candidate/test-result.log
```

Expected: zero failures. The current exact-tree baseline is 135 tests on macOS; a count change requires explicit explanation and rerun, not silent acceptance.

- [ ] **Step 4: Prove package discovery, interfaces, and Mach-O linkage**

```zsh
for package_name in mujoco_ros2_control_msgs mujoco_ros2_control_plugins mujoco_ros2_control; do
  ros2 pkg prefix "${package_name}"
done | tee /tmp/so101-debug-mujoco-fork-r7/macos-candidate/prefixes.txt
ros2 pkg prefix mujoco_vendor \
  | tee /tmp/so101-debug-mujoco-fork-r7/macos-candidate/mujoco-vendor-prefix.txt
for interface_name in \
  mujoco_ros2_control_msgs/srv/ResetWorld \
  mujoco_ros2_control_msgs/srv/SetPause \
  mujoco_ros2_control_msgs/srv/StepSimulation; do
  ros2 interface show "${interface_name}"
done | tee /tmp/so101-debug-mujoco-fork-r7/macos-candidate/interfaces.txt
otool -L /Users/matianyi/ros2_jazzy/fork_r7_candidate_20260814/install/lib/libmujoco_ros2_control.dylib \
  | tee /tmp/so101-debug-mujoco-fork-r7/macos-candidate/otool-control.txt
otool -l /Users/matianyi/ros2_jazzy/fork_r7_candidate_20260814/install/lib/libmujoco_ros2_control.dylib \
  | rg -A3 LC_RPATH \
  | tee /tmp/so101-debug-mujoco-fork-r7/macos-candidate/rpaths.txt
```

Expected: all fork packages resolve to the new candidate install, `mujoco_vendor` resolves to the dependency overlay, all interfaces exist, and required Apple frameworks/rpaths are present without unresolved dylibs.

- [ ] **Step 5: Build only the project packages needed for a headless service smoke**

```zsh
colcon --log-base /Users/matianyi/ros2_jazzy/fork_r7_candidate_20260814/project-log build \
  --base-paths src/so101_mujoco_support src/so101_demo_py \
  --build-base /Users/matianyi/ros2_jazzy/fork_r7_candidate_20260814/project-build \
  --install-base /Users/matianyi/ros2_jazzy/fork_r7_candidate_20260814/project-install \
  --merge-install \
  --cmake-clean-cache \
  --packages-select so101_mujoco_support so101_demo_py \
  |& tee /tmp/so101-debug-mujoco-fork-r7/macos-candidate/project-build.log
source /Users/matianyi/ros2_jazzy/fork_r7_candidate_20260814/project-install/setup.zsh
```

Expected: both project packages build against the candidate prefix.

- [ ] **Step 6: Run an owned, bounded reset/pause/step smoke**

Launch in a new POSIX session so cleanup can target only this run:

```zsh
export ROS_DOMAIN_ID=177
python3 -c 'import os,sys; os.setsid(); os.execvp(sys.argv[1], sys.argv[1:])' \
  python3 "$(command -v ros2)" launch so101_demo_py so101_mujoco.launch.py \
  run_mode:=dry_run execute:=false headless:=true \
  session_id:=fork-r7-macos-candidate \
  > /tmp/so101-debug-mujoco-fork-r7/macos-candidate/launch.log 2>&1 &
launch_pid=$!
trap 'kill -INT -- "-${launch_pid}" 2>/dev/null || true' EXIT INT TERM
attempt=0
until ros2 service type /mujoco_ros2_control_node/reset_world >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  (( attempt < 180 )) || exit 1
  sleep 0.5
done
ros2 service call /mujoco_ros2_control_node/set_pause \
  mujoco_ros2_control_msgs/srv/SetPause '{paused: true}' \
  | tee /tmp/so101-debug-mujoco-fork-r7/macos-candidate/pause-response.txt
ros2 service call /mujoco_ros2_control_node/reset_world \
  mujoco_ros2_control_msgs/srv/ResetWorld '{keyframe: task_start}' \
  | tee /tmp/so101-debug-mujoco-fork-r7/macos-candidate/reset-response.txt
ros2 service call /mujoco_ros2_control_node/step_simulation \
  mujoco_ros2_control_msgs/srv/StepSimulation '{steps: 1}' \
  | tee /tmp/so101-debug-mujoco-fork-r7/macos-candidate/step-response.txt
kill -INT -- "-${launch_pid}"
wait "${launch_pid}"
launch_exit=$?
trap - EXIT INT TERM
test "${launch_exit}" -eq 0
```

Expected: each response reports success, the launch exits cleanly, and no process from process group `${launch_pid}` remains. This is a portability smoke only.

---

### Task 4: Build the Exact Unpublished Candidate on Linux / ai-station

**Files:**
- No source changes unless a cross-platform defect is found
- Local evidence: `/tmp/so101-debug-mujoco-fork-r7/linux-candidate/`
- Remote evidence: `/tmp/so101-debug-mujoco-fork-r7/linux-candidate/`
- Retained remote root: `/data/work/so101-mujoco-fork-r7/`

**Interfaces:**
- Consumes: a bundle containing the exact candidate commit proven on macOS.
- Produces: Linux compile/test/ELF/service evidence for the same commit without modifying `/data/work/ws_moveit` or existing ROS/tmux processes.

- [ ] **Step 1: Bundle the candidate and record its identity locally**

```zsh
mkdir -p /tmp/so101-debug-mujoco-fork-r7/linux-candidate
candidate_commit=$(git -C third_party/mujoco_ros2_control rev-parse HEAD)
git -C third_party/mujoco_ros2_control bundle create \
  /tmp/so101-debug-mujoco-fork-r7/linux-candidate/fork-r7-candidate.bundle \
  codex/portable-macos-linux-r7
shasum -a 256 \
  /tmp/so101-debug-mujoco-fork-r7/linux-candidate/fork-r7-candidate.bundle \
  | tee /tmp/so101-debug-mujoco-fork-r7/linux-candidate/bundle.sha256
print -r -- "${candidate_commit}" \
  | tee /tmp/so101-debug-mujoco-fork-r7/linux-candidate/candidate-commit.txt
```

- [ ] **Step 2: Read-only preflight ai-station**

```zsh
ssh ai-station 'zsh -lc '\''
  pwd
  git -C /data/work/ws_moveit status --short --branch
  git -C /data/work/ws_moveit rev-parse HEAD
  git -C /data/work/ws_moveit submodule status
  df -h /data/work /tmp
  pgrep -af "ros2|mujoco|controller_manager|move_group|rviz|gz sim" || true
'\''' | tee /tmp/so101-debug-mujoco-fork-r7/linux-candidate/preflight.txt
```

Expected: preflight is recorded only. Do not stop or alter any observed process.

- [ ] **Step 3: Transfer and verify the fork bundle**

```zsh
scp \
  /tmp/so101-debug-mujoco-fork-r7/linux-candidate/fork-r7-candidate.bundle \
  /tmp/so101-debug-mujoco-fork-r7/linux-candidate/bundle.sha256 \
  ai-station:/tmp/
ssh ai-station 'zsh -lc '\''
  test ! -e /data/work/so101-mujoco-fork-r7
  mkdir -p /data/work/so101-mujoco-fork-r7
  mkdir -p /tmp/so101-debug-mujoco-fork-r7/linux-candidate
  cd /tmp
  shasum -a 256 -c bundle.sha256
  git clone /tmp/fork-r7-candidate.bundle \
    /data/work/so101-mujoco-fork-r7/mujoco_ros2_control
  git -C /data/work/so101-mujoco-fork-r7/mujoco_ros2_control \
    switch --detach codex/portable-macos-linux-r7
  git -C /data/work/so101-mujoco-fork-r7/mujoco_ros2_control rev-parse HEAD \
    | tee /tmp/so101-debug-mujoco-fork-r7/linux-candidate/candidate-commit.txt
  test -z "$(git -C /data/work/so101-mujoco-fork-r7/mujoco_ros2_control \
    status --porcelain --untracked-files=all)"
'\'''
```

Expected: remote HEAD equals local `candidate-commit.txt`; source is clean.

- [ ] **Step 4: Build and test the three packages on Linux**

```zsh
ssh ai-station 'zsh -lc '\''
  set -euo pipefail
  source /opt/ros/jazzy/setup.zsh
  colcon --log-base /data/work/so101-mujoco-fork-r7/candidate-log build \
    --base-paths /data/work/so101-mujoco-fork-r7/mujoco_ros2_control \
    --build-base /data/work/so101-mujoco-fork-r7/candidate-build \
    --install-base /data/work/so101-mujoco-fork-r7/candidate-install \
    --merge-install --cmake-clean-cache \
    --cmake-args -DFETCHCONTENT_UPDATES_DISCONNECTED=ON \
    --packages-select mujoco_ros2_control_msgs mujoco_ros2_control_plugins mujoco_ros2_control \
    |& tee /tmp/so101-debug-mujoco-fork-r7/linux-candidate/build.log
  source /data/work/so101-mujoco-fork-r7/candidate-install/setup.zsh
  colcon --log-base /data/work/so101-mujoco-fork-r7/candidate-log test \
    --base-paths /data/work/so101-mujoco-fork-r7/mujoco_ros2_control \
    --build-base /data/work/so101-mujoco-fork-r7/candidate-build \
    --install-base /data/work/so101-mujoco-fork-r7/candidate-install \
    --merge-install \
    --packages-select mujoco_ros2_control_msgs mujoco_ros2_control_plugins mujoco_ros2_control \
    --event-handlers console_direct+ \
    |& tee /tmp/so101-debug-mujoco-fork-r7/linux-candidate/test.log
  colcon test-result \
    --test-result-base /data/work/so101-mujoco-fork-r7/candidate-build --verbose \
    |& tee /tmp/so101-debug-mujoco-fork-r7/linux-candidate/test-result.log
'\'''
```

Expected: zero failures. The current exact-tree baseline is 134 tests on Linux; investigate any count change.

- [ ] **Step 5: Verify ELF, dependency, interface, and link-command boundaries**

```zsh
ssh ai-station 'zsh -lc '\''
  set -euo pipefail
  source /opt/ros/jazzy/setup.zsh
  source /data/work/so101-mujoco-fork-r7/candidate-install/setup.zsh
  ros2 pkg prefix mujoco_ros2_control
  ros2 pkg prefix mujoco_vendor
  readelf -d /data/work/so101-mujoco-fork-r7/candidate-install/lib/libmujoco_ros2_control.so \
    | tee /tmp/so101-debug-mujoco-fork-r7/linux-candidate/readelf.txt
  ldd /data/work/so101-mujoco-fork-r7/candidate-install/lib/libmujoco_ros2_control.so \
    | tee /tmp/so101-debug-mujoco-fork-r7/linux-candidate/ldd.txt
  ! rg -n "Cocoa|CoreVideo|AppKit" \
    /tmp/so101-debug-mujoco-fork-r7/linux-candidate/readelf.txt \
    /tmp/so101-debug-mujoco-fork-r7/linux-candidate/ldd.txt
  rg -n -- "--push-state,--no-as-needed.*tinyxml2|tinyxml2.*--pop-state" \
    /data/work/so101-mujoco-fork-r7/candidate-build/mujoco_ros2_control \
    | tee /tmp/so101-debug-mujoco-fork-r7/linux-candidate/tinyxml2-link.txt
  for interface_name in \
    mujoco_ros2_control_msgs/srv/ResetWorld \
    mujoco_ros2_control_msgs/srv/SetPause \
    mujoco_ros2_control_msgs/srv/StepSimulation; do
    ros2 interface show "${interface_name}"
  done | tee /tmp/so101-debug-mujoco-fork-r7/linux-candidate/interfaces.txt
'\'''
```

Expected: fork prefix is the candidate install, vendor remains `/opt/ros/jazzy`, no Apple framework appears, tinyxml2 link protection is retained, and all services are discoverable.

- [ ] **Step 6: Build isolated project packages and run the same bounded Linux smoke**

Create a local clone from the active project without altering the source checkout, then build only the two required packages against the candidate:

```zsh
ssh ai-station 'zsh -lc '\''
  set -euo pipefail
  git clone --no-local /data/work/ws_moveit \
    /data/work/so101-mujoco-fork-r7/moveit-demo
  git -C /data/work/so101-mujoco-fork-r7/moveit-demo checkout --detach \
    "$(git -C /data/work/ws_moveit rev-parse HEAD)"
  source /opt/ros/jazzy/setup.zsh
  source /data/work/so101-mujoco-fork-r7/candidate-install/setup.zsh
  colcon --log-base /data/work/so101-mujoco-fork-r7/project-log build \
    --base-paths \
      /data/work/so101-mujoco-fork-r7/moveit-demo/src/so101_mujoco_support \
      /data/work/so101-mujoco-fork-r7/moveit-demo/src/so101_demo_py \
    --build-base /data/work/so101-mujoco-fork-r7/project-build \
    --install-base /data/work/so101-mujoco-fork-r7/project-install \
    --merge-install --cmake-clean-cache \
    --packages-select so101_mujoco_support so101_demo_py \
    |& tee /tmp/so101-debug-mujoco-fork-r7/linux-candidate/project-build.log
  source /data/work/so101-mujoco-fork-r7/project-install/setup.zsh
  cd /data/work/so101-mujoco-fork-r7/moveit-demo
  export ROS_DOMAIN_ID=178
  python3 -c "import os,sys; os.setsid(); os.execvp(sys.argv[1], sys.argv[1:])" \
    python3 "$(command -v ros2)" launch so101_demo_py so101_mujoco.launch.py \
    run_mode:=dry_run execute:=false headless:=true \
    session_id:=fork-r7-linux-candidate \
    > /tmp/so101-debug-mujoco-fork-r7/linux-candidate/launch.log 2>&1 &
  launch_pid=$!
  trap "kill -INT -- -${launch_pid} 2>/dev/null || true" EXIT INT TERM
  attempt=0
  until ros2 service type /mujoco_ros2_control_node/reset_world >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    (( attempt < 180 )) || exit 1
    sleep 0.5
  done
  ros2 service call /mujoco_ros2_control_node/set_pause \
    mujoco_ros2_control_msgs/srv/SetPause "{paused: true}" \
    | tee /tmp/so101-debug-mujoco-fork-r7/linux-candidate/pause-response.txt
  ros2 service call /mujoco_ros2_control_node/reset_world \
    mujoco_ros2_control_msgs/srv/ResetWorld "{keyframe: task_start}" \
    | tee /tmp/so101-debug-mujoco-fork-r7/linux-candidate/reset-response.txt
  ros2 service call /mujoco_ros2_control_node/step_simulation \
    mujoco_ros2_control_msgs/srv/StepSimulation "{steps: 1}" \
    | tee /tmp/so101-debug-mujoco-fork-r7/linux-candidate/step-response.txt
  kill -INT -- -${launch_pid}
  wait "${launch_pid}"
  launch_exit=$?
  trap - EXIT INT TERM
  test "${launch_exit}" -eq 0
'\'''
```

Expected: pause, reset `task_start`, and one physics step all report success; the owned launch exits cleanly. No existing remote process is signalled.

- [ ] **Step 7: Copy remote evidence back without deleting the remote copy**

```zsh
mkdir -p /tmp/so101-debug-mujoco-fork-r7/ai-station
scp -r ai-station:/tmp/so101-debug-mujoco-fork-r7/linux-candidate \
  /tmp/so101-debug-mujoco-fork-r7/ai-station/
diff -u \
  /tmp/so101-debug-mujoco-fork-r7/candidate/candidate-commit.txt \
  /tmp/so101-debug-mujoco-fork-r7/ai-station/linux-candidate/candidate-commit.txt
```

Expected: local and Linux candidate commit identities match. Keep both evidence copies.

- [ ] **Step 8: Handle any platform failure before publication**

If Linux exposes a defect, make the smallest fix in the fork candidate, add a focused failing fork test first, commit the fix as a new topic commit, then restart Tasks 3 and 4. Because the approved design requires the existing eleven commits, any twelfth commit or changed diff hash requires updating the design and obtaining user confirmation before publication. Never restore an installer OS gate.

---

### Task 5: Publish the Validated Fork Main and Annotated r7 Tag

**Files:**
- Remote mutation: Gitee fork `main`
- Remote mutation: Gitee annotated tag `so101-0.0.3-r7`
- Evidence: `/tmp/so101-debug-mujoco-fork-r7/publish/`

**Interfaces:**
- Consumes: the exact candidate commit with green macOS and Linux evidence.
- Produces: Gitee `main` and peeled r7 tag resolving to the same commit.

- [ ] **Step 1: Re-run all publication preconditions immediately before push**

```zsh
mkdir -p /tmp/so101-debug-mujoco-fork-r7/publish
candidate_commit=$(git -C third_party/mujoco_ros2_control rev-parse HEAD)
remote_main=$(git -C third_party/mujoco_ros2_control ls-remote origin refs/heads/main | awk '{print $1}')
test "${remote_main}" = 738e304551b4ea6db020b466086a13db71b65607
test -z "$(git -C third_party/mujoco_ros2_control ls-remote origin \
  refs/tags/so101-0.0.3-r7 'refs/tags/so101-0.0.3-r7^{}')"
test -z "$(git -C third_party/mujoco_ros2_control status --porcelain --untracked-files=all)"
git -C third_party/mujoco_ros2_control merge-base --is-ancestor \
  "${remote_main}" "${candidate_commit}"
git -C third_party/mujoco_ros2_control diff --binary \
  738e304551b4ea6db020b466086a13db71b65607.."${candidate_commit}" \
  | shasum -a 256 \
  | rg '^56b2f1033ccf48b44be6db8daee800f3f4d463048bd6cf2a7f8e58549ebde2f5 '
```

Expected: every gate passes. Any remote drift stops publication.

- [ ] **Step 2: Fast-forward fork `main` without force**

```zsh
git -C third_party/mujoco_ros2_control push origin \
  codex/portable-macos-linux-r7:refs/heads/main \
  |& tee /tmp/so101-debug-mujoco-fork-r7/publish/main-push.log
```

Expected: ordinary fast-forward succeeds. Do not use `--force` or a refspec beginning with `+`.

- [ ] **Step 3: Create and push the annotated release tag**

```zsh
git -C third_party/mujoco_ros2_control tag -a so101-0.0.3-r7 \
  "${candidate_commit}" \
  -m "SO-101 mujoco_ros2_control 0.0.3 r7 portable macOS/Linux build"
git -C third_party/mujoco_ros2_control push origin \
  refs/tags/so101-0.0.3-r7 \
  |& tee /tmp/so101-debug-mujoco-fork-r7/publish/tag-push.log
```

Expected: the tag is annotated and published. If tag push fails after main succeeds, preserve main and diagnose the tag; never rewrite main history.

- [ ] **Step 4: Read back both refs from Git and the Gitee API**

```zsh
git -C third_party/mujoco_ros2_control ls-remote origin \
  refs/heads/main refs/tags/so101-0.0.3-r7 'refs/tags/so101-0.0.3-r7^{}' \
  | tee /tmp/so101-debug-mujoco-fork-r7/publish/ls-remote.txt
curl -fsSL \
  https://gitee.com/api/v5/repos/zjumty/mujoco_ros2_control/branches/main \
  | tee /tmp/so101-debug-mujoco-fork-r7/publish/gitee-main.json
curl -fsSL \
  https://gitee.com/api/v5/repos/zjumty/mujoco_ros2_control/tags \
  | tee /tmp/so101-debug-mujoco-fork-r7/publish/gitee-tags.json
python3 -c 'import json,sys; data=json.load(open(sys.argv[1])); print(data["commit"]["sha"])' \
  /tmp/so101-debug-mujoco-fork-r7/publish/gitee-main.json
python3 -c 'import json,sys; data=json.load(open(sys.argv[1])); print(next(tag["commit"]["sha"] for tag in data if tag["name"] == "so101-0.0.3-r7"))' \
  /tmp/so101-debug-mujoco-fork-r7/publish/gitee-tags.json
```

Expected: remote main, peeled annotated tag, and API read-back all resolve to `${candidate_commit}`.

---

### Task 6: Turn the Superproject RED Contract GREEN

**Files:**
- Modify gitlink: `third_party/mujoco_ros2_control`
- Modify: `src/so101_demo_py/config/mujoco/dependency-lock.yaml`
- Modify: `src/so101_demo_py/config/dependency-lock.yaml`
- Modify: `scripts/check_backend_integration.py`
- Modify: `scripts/install-mujoco-ros2-control.zsh`
- Modify: `src/so101_demo_py/test/test_macos_install_contract.py`
- Modify: `.gitattributes`
- Delete: `scripts/patches/mujoco_ros2_control/series`
- Delete: `scripts/patches/mujoco_ros2_control/0001-portable-heartbeat-format.patch`
- Delete: `scripts/patches/mujoco_ros2_control/0002-platform-build-and-rpath.patch`
- Delete: `scripts/patches/mujoco_ros2_control/0003-headless-rendering-control.patch`
- Delete: `scripts/patches/mujoco_ros2_control/0004-apple-main-thread-ui.patch`
- Delete: `scripts/patches/mujoco_ros2_control/0005-apple-framework-linkage.patch`
- Delete: `scripts/patches/mujoco_ros2_control/0006-apple-test-logging-runtime.patch`
- Delete: `scripts/patches/mujoco_ros2_control/0007-apple-test-rmw-runtime.patch`
- Delete: `scripts/patches/mujoco_ros2_control/0008-platform-cxx17-requirements.patch`
- Delete: `scripts/patches/mujoco_ros2_control/0009-apple-conversion-warnings.patch`
- Delete: `scripts/patches/mujoco_ros2_control/0010-apple-test-backward-runtime.patch`
- Delete: `scripts/patches/mujoco_ros2_control/0011-guard-apple-test-runtime-dependencies.patch`

**Interfaces:**
- Consumes: published and read-back-verified r7 commit.
- Produces: one superproject dependency commit whose gitlink, two locks, installer, and contracts agree that clean r7 is the sole authority.

- [ ] **Step 1: Update both locks and backend contract to the exact published commit**

Use a targeted patch to change:

- both lock tags from `so101-0.0.3-r6` to `so101-0.0.3-r7`;
- both lock `fork.commit` values from r6 to `${candidate_commit}`;
- `scripts/check_backend_integration.py` expected tag from r6 to r7.

Do not change `policy_behavior_commit`, upstream identity, interface hashes, required-file hashes, or source order.

- [ ] **Step 2: Record the published commit as the superproject gitlink**

```zsh
git -C third_party/mujoco_ros2_control checkout --detach "${candidate_commit}"
test -z "$(git -C third_party/mujoco_ros2_control status --porcelain --untracked-files=all)"
git add third_party/mujoco_ros2_control
```

Expected: only the gitlink changes in the superproject; the submodule source remains clean.

- [ ] **Step 3: Remove active patch authority**

Delete the `series` file and all eleven listed patch files with `apply_patch`. Remove only this obsolete line from `.gitattributes`:

```text
scripts/patches/mujoco_ros2_control/*.patch -whitespace
```

If `scripts/patches/mujoco_ros2_control/` becomes empty, leave no empty directory. Historical commits remain the recovery path.

- [ ] **Step 4: Simplify the installer to require a clean r7 build source**

In `scripts/install-mujoco-ros2-control.zsh`:

1. Delete `patch_series_dir`, `patch_series_file`, `load_patch_series()`, `apply_patch_series()`, and the `load_patch_series` call in `main()`.
2. Keep the independent shared clone at `fork_workspace/src/mujoco_ros2_control`.
3. After verifying its exact HEAD, require it to be clean:

```zsh
  local build_source_changes
  build_source_changes=$(git -C "${build_source_dir}" status --porcelain --untracked-files=all)
  [[ -z ${build_source_changes} ]] ||
    fail "build source must be clean at locked fork commit: ${build_source_dir}"
```

4. Do not reset, clean, reverse-apply, or delete an existing build source. A prior r6-plus-patches build source must fail closed; the guide will instruct users to select a new `SO101_WORKSPACE_DIR` or archive the old root explicitly.

- [ ] **Step 5: Run the formerly RED narrow contract**

```zsh
direnv exec . python -m pytest -q \
  src/so101_demo_py/test/test_macos_install_contract.py \
  -k 'r7 or clean_locked_fork' \
  |& tee /tmp/so101-debug-mujoco-fork-r7/superproject-green-contract.log
```

Expected: all selected tests pass, including the exact eleven subjects and diff hash.

- [ ] **Step 6: Run backend and installer static gates**

```zsh
direnv exec . python scripts/check_backend_integration.py \
  |& tee /tmp/so101-debug-mujoco-fork-r7/backend-contract.log
zsh -n scripts/install-mujoco-ros2-control.zsh
rg -n 'patch_series|portable_patches|apply_patch_series|git apply' \
  scripts/install-mujoco-ros2-control.zsh \
  src/so101_demo_py/test/test_macos_install_contract.py \
  && exit 1 || true
test ! -e scripts/patches/mujoco_ros2_control
test -z "$(git -C third_party/mujoco_ros2_control status --porcelain --untracked-files=all)"
git diff --check
```

Expected: backend contract passes, installer syntax passes, no active patch path remains, submodule is clean, and diff check passes.

- [ ] **Step 7: Commit the dependency authority migration**

```zsh
git add -A -- scripts/patches/mujoco_ros2_control
git add .gitattributes \
  scripts/install-mujoco-ros2-control.zsh \
  scripts/check_backend_integration.py \
  src/so101_demo_py/config/dependency-lock.yaml \
  src/so101_demo_py/config/mujoco/dependency-lock.yaml \
  src/so101_demo_py/test/test_macos_install_contract.py \
  third_party/mujoco_ros2_control
git diff --cached --check
git commit -m "build: consume clean mujoco fork r7"
```

Expected: the commit contains the r7 gitlink/locks, installer simplification, GREEN tests, and patch deletions only.

---

### Task 7: Update Current Guidance Without Rewriting Historical Evidence

**Files:**
- Modify: `docs/guides/macos-apple-silicon-ros2-jazzy-so101-mujoco.md`
- Modify: `docs/guides/so101-mujoco-ros2-integration-guide.md`
- Modify: `docs/superpowers/specs/2026-08-14-mujoco-ros2-control-fork-r7-design.md`
- Modify: `docs/superpowers/specs/2026-08-14-mujoco-ros2-control-cross-platform-patch-series-design.md`
- Modify: `docs/superpowers/plans/2026-08-14-mujoco-ros2-control-cross-platform-patch-series.md`

**Interfaces:**
- Consumes: the published r7 identity and retained validation logs.
- Produces: current instructions that point only to clean fork r7 while preserving old plans as historical records.

- [ ] **Step 1: Update the macOS guide's active build section**

Replace the r6-plus-series instructions with:

- exact r7 tag and commit;
- fork history as the only source authority;
- installer builds a clean independent checkout and fails if it is dirty;
- old r6 patched workspaces must not be silently reused or cleaned;
- macOS and Linux validation counts and linkage gates from this run;
- future platform fixes are normal fork commits followed by two-platform validation and a new `rN` tag.

Retain the dylib-farm explanation; r7 does not remove macOS SIP/DYLD or distributed-overlay constraints.

- [ ] **Step 2: Update the integration guide dependency table and release ledger**

Change the active release and gitlink to r7. Add an r7 row stating that it incorporates eleven portable build/runtime commits and removes superproject patch replay. Change installer validation item 4 to require the r7 tag. Keep r1-r6 history intact.

- [ ] **Step 3: Mark the old patch-series design and plan as superseded**

Add a concise banner immediately after each title:

```markdown
> Superseded on 2026-08-14 by `so101-0.0.3-r7`. This document records the validated migration input; active builds consume the clean fork and do not replay this series.
```

Do not rewrite their historical commands or evidence.

- [ ] **Step 4: Record actual r7 outcome in the approved design**

Append a short implementation-status section containing the exact candidate commit, Gitee read-back result, macOS/Linux build and test counts, service-smoke result, and the superproject integration commit. Do not add experiment-ledger language or claim a new RESET_WORLD five-win qualification.

- [ ] **Step 5: Verify current documentation has no active patch instruction**

```zsh
rg -n 'scripts/patches/mujoco_ros2_control|维护 patch|重放.*patch|apply_patch_series' \
  docs/guides README.md src/so101_demo_py/README.md
```

Expected: no active guide instructs patch replay. Matches inside explicitly superseded historical documents are allowed.

- [ ] **Step 6: Commit documentation**

```zsh
git add \
  docs/guides/macos-apple-silicon-ros2-jazzy-so101-mujoco.md \
  docs/guides/so101-mujoco-ros2-integration-guide.md \
  docs/superpowers/specs/2026-08-14-mujoco-ros2-control-fork-r7-design.md \
  docs/superpowers/specs/2026-08-14-mujoco-ros2-control-cross-platform-patch-series-design.md \
  docs/superpowers/plans/2026-08-14-mujoco-ros2-control-cross-platform-patch-series.md
git diff --cached --check
git commit -m "docs: make mujoco fork r7 authoritative"
```

---

### Task 8: Verify Fresh Gitee r7 Through the Final Installer on macOS

**Files:**
- Test: full installer from a fresh superproject clone whose submodule fetches from Gitee
- Evidence: `/tmp/so101-debug-mujoco-fork-r7/macos-published/`
- Retained clone/build: `/Users/matianyi/ros2_jazzy/fork_r7_published_20260814/`

**Interfaces:**
- Consumes: published Gitee r7 and the integrated superproject branch.
- Produces: post-publication proof that no local patch/object borrowing is needed.

- [ ] **Step 1: Create a non-local superproject clone at the integrated commit**

```zsh
mkdir -p /tmp/so101-debug-mujoco-fork-r7/macos-published
test ! -e /Users/matianyi/ros2_jazzy/fork_r7_published_20260814
git clone --no-local --no-checkout \
  /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/mujoco-portable-patch-series \
  /Users/matianyi/ros2_jazzy/fork_r7_published_20260814/moveit-demo
git -C /Users/matianyi/ros2_jazzy/fork_r7_published_20260814/moveit-demo \
  checkout --detach "$(git rev-parse HEAD)"
git -C /Users/matianyi/ros2_jazzy/fork_r7_published_20260814/moveit-demo \
  submodule update --init -- third_party/mujoco_ros2_control
test ! -e /Users/matianyi/ros2_jazzy/fork_r7_published_20260814/moveit-demo/.git/modules/third_party/mujoco_ros2_control/objects/info/alternates
```

Expected: the submodule is fetched from its Gitee URL, has no alternates file, and resolves to the published r7 commit.

- [ ] **Step 2: Run the final installer into a fresh workspace**

```zsh
cd /Users/matianyi/ros2_jazzy/fork_r7_published_20260814/moveit-demo
source /Users/matianyi/ros2_jazzy/.venv/bin/activate
SO101_WORKSPACE_DIR=/Users/matianyi/ros2_jazzy/fork_r7_published_20260814/runtime \
SO101_ROS_UNDERLAY=/opt/ros/jazzy \
SO101_ROS_DEPENDENCY_OVERLAY=/Users/matianyi/ros2_jazzy/extra_ws/install \
./scripts/install-mujoco-ros2-control.zsh \
  |& tee /tmp/so101-debug-mujoco-fork-r7/macos-published/installer.log
```

Expected: three packages build/test from clean r7; installer prefix/interface/file gates pass; no patch operation appears in the log.

- [ ] **Step 3: Read back published provenance and linkage**

```zsh
git -C third_party/mujoco_ros2_control rev-parse HEAD \
  | tee /tmp/so101-debug-mujoco-fork-r7/macos-published/submodule-head.txt
git -C third_party/mujoco_ros2_control remote get-url origin \
  | tee /tmp/so101-debug-mujoco-fork-r7/macos-published/submodule-origin.txt
git -C third_party/mujoco_ros2_control describe --tags --exact-match \
  | tee /tmp/so101-debug-mujoco-fork-r7/macos-published/submodule-tag.txt
test -z "$(git -C third_party/mujoco_ros2_control status --porcelain --untracked-files=all)"
source /Users/matianyi/ros2_jazzy/fork_r7_published_20260814/runtime/ws_mujoco_ros2_control_fork/install/setup.zsh
ros2 pkg prefix mujoco_ros2_control \
  | tee /tmp/so101-debug-mujoco-fork-r7/macos-published/prefix.txt
otool -L /Users/matianyi/ros2_jazzy/fork_r7_published_20260814/runtime/ws_mujoco_ros2_control_fork/install/lib/libmujoco_ros2_control.dylib \
  | tee /tmp/so101-debug-mujoco-fork-r7/macos-published/otool.txt
```

Expected: origin is Gitee, HEAD/tag are exact r7, source is clean, and package prefix is the fresh published install.

---

### Task 9: Verify Fresh Gitee r7 Through the Final Installer on ai-station

**Files:**
- Test: integrated superproject bundle plus Gitee-fetched submodule
- Local evidence: `/tmp/so101-debug-mujoco-fork-r7/linux-published/`
- Remote retained root: `/data/work/so101-mujoco-fork-r7/published/`

**Interfaces:**
- Consumes: the integrated superproject commit and Gitee r7.
- Produces: final Linux proof from the published fork, not the pre-publication bundle.

- [ ] **Step 1: Bundle the integrated superproject commit and transfer it**

```zsh
mkdir -p /tmp/so101-debug-mujoco-fork-r7/linux-published
git bundle create \
  /tmp/so101-debug-mujoco-fork-r7/linux-published/moveit-r7-integration.bundle \
  codex/mujoco-portable-patch-series
shasum -a 256 \
  /tmp/so101-debug-mujoco-fork-r7/linux-published/moveit-r7-integration.bundle \
  | tee /tmp/so101-debug-mujoco-fork-r7/linux-published/bundle.sha256
scp \
  /tmp/so101-debug-mujoco-fork-r7/linux-published/moveit-r7-integration.bundle \
  /tmp/so101-debug-mujoco-fork-r7/linux-published/bundle.sha256 \
  ai-station:/tmp/
```

- [ ] **Step 2: Clone the superproject bundle and fetch the submodule from Gitee**

```zsh
ssh ai-station 'zsh -lc '\''
  set -euo pipefail
  test ! -e /data/work/so101-mujoco-fork-r7/published
  mkdir -p /data/work/so101-mujoco-fork-r7/published
  cd /tmp
  shasum -a 256 -c bundle.sha256
  git clone /tmp/moveit-r7-integration.bundle \
    /data/work/so101-mujoco-fork-r7/published/moveit-demo
  git -C /data/work/so101-mujoco-fork-r7/published/moveit-demo \
    switch --detach codex/mujoco-portable-patch-series
  git -C /data/work/so101-mujoco-fork-r7/published/moveit-demo \
    submodule update --init -- third_party/mujoco_ros2_control
  test ! -e /data/work/so101-mujoco-fork-r7/published/moveit-demo/.git/modules/third_party/mujoco_ros2_control/objects/info/alternates
'\'''
```

Expected: submodule initialization contacts Gitee and produces exact clean r7 without alternates.

- [ ] **Step 3: Run the final Linux installer and provenance gates**

```zsh
ssh ai-station 'zsh -lc '\''
  set -euo pipefail
  cd /data/work/so101-mujoco-fork-r7/published/moveit-demo
  source /opt/ros/jazzy/setup.zsh
  SO101_WORKSPACE_DIR=/data/work/so101-mujoco-fork-r7/published/runtime \
  SO101_ROS_UNDERLAY=/opt/ros/jazzy \
  SO101_ROS_DEPENDENCY_OVERLAY=/opt/ros/jazzy \
  ./scripts/install-mujoco-ros2-control.zsh \
    |& tee /tmp/so101-debug-mujoco-fork-r7/linux-published-installer.log
  git -C third_party/mujoco_ros2_control rev-parse HEAD
  git -C third_party/mujoco_ros2_control describe --tags --exact-match
  git -C third_party/mujoco_ros2_control remote get-url origin
  test -z "$(git -C third_party/mujoco_ros2_control status --porcelain --untracked-files=all)"
  source /data/work/so101-mujoco-fork-r7/published/runtime/ws_mujoco_ros2_control_fork/install/setup.zsh
  ros2 pkg prefix mujoco_ros2_control
  readelf -d /data/work/so101-mujoco-fork-r7/published/runtime/ws_mujoco_ros2_control_fork/install/lib/libmujoco_ros2_control.so
'\'''
```

Expected: installer tests pass, origin/tag/commit are exact Gitee r7, source is clean, prefix is the new published install, and ELF checks remain Linux-only.

- [ ] **Step 4: Copy published Linux evidence back**

```zsh
scp ai-station:/tmp/so101-debug-mujoco-fork-r7/linux-published-installer.log \
  /tmp/so101-debug-mujoco-fork-r7/linux-published/
```

Do not delete the remote copy or retained build.

---

### Task 10: Run Full Superproject Regression and Final Evidence Gates

**Files:**
- Test: `src/so101_demo_py/test/`
- Evidence: `/tmp/so101-debug-mujoco-fork-r7/final/`

**Interfaces:**
- Consumes: committed r7 integration, current guides, and published two-platform evidence.
- Produces: final clean feature branch ready for review/merge, without pushing `moveit-demo` unless the user separately requests it.

- [ ] **Step 1: Run the complete installer contract file**

```zsh
mkdir -p /tmp/so101-debug-mujoco-fork-r7/final
cd /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/mujoco-portable-patch-series
direnv exec . python -m pytest -q \
  src/so101_demo_py/test/test_macos_install_contract.py \
  |& tee /tmp/so101-debug-mujoco-fork-r7/final/install-contract.log
```

Expected: all tests pass.

- [ ] **Step 2: Run the full canonical `so101_demo_py` test suite from the isolated install environment**

Use the same canonical isolated dependency/project overlay order that produced the prior 215-test baseline, with the published r7 fork overlay sourced before the project overlay:

```zsh
source /Users/matianyi/ros2_jazzy/.venv/bin/activate
source /opt/ros/jazzy/setup.zsh
source /Users/matianyi/ros2_jazzy/extra_ws/install/setup.zsh
source /Users/matianyi/ros2_jazzy/fork_r7_published_20260814/runtime/ws_mujoco_ros2_control_fork/install/setup.zsh
direnv exec . python -m pytest -q src/so101_demo_py/test \
  |& tee /tmp/so101-debug-mujoco-fork-r7/final/so101-demo-py-tests.log
```

Expected: zero failures and the current baseline of 215 passing tests. If the count changes, identify added/removed/skipped tests before accepting.

- [ ] **Step 3: Run final source/provenance checks**

```zsh
direnv exec . python scripts/check_backend_integration.py \
  |& tee /tmp/so101-debug-mujoco-fork-r7/final/backend-contract.log
zsh -n scripts/install-mujoco-ros2-control.zsh
git diff --check
test -z "$(git -C third_party/mujoco_ros2_control status --porcelain --untracked-files=all)"
git submodule status third_party/mujoco_ros2_control \
  | tee /tmp/so101-debug-mujoco-fork-r7/final/submodule.txt
git status --short --branch \
  | tee /tmp/so101-debug-mujoco-fork-r7/final/feature-status.txt
git log --oneline --decorate -8 \
  | tee /tmp/so101-debug-mujoco-fork-r7/final/feature-log.txt
```

Expected: all gates pass, submodule has no dirty marker, and feature worktree is clean after documentation/status commits.

- [ ] **Step 4: Re-read remote publication one final time**

```zsh
candidate_commit=$(git -C third_party/mujoco_ros2_control rev-parse HEAD)
git ls-remote git@gitee.com:zjumty/mujoco_ros2_control.git \
  refs/heads/main refs/tags/so101-0.0.3-r7 'refs/tags/so101-0.0.3-r7^{}' \
  | tee /tmp/so101-debug-mujoco-fork-r7/final/gitee-refs.txt
rg -c "${candidate_commit}" /tmp/so101-debug-mujoco-fork-r7/final/gitee-refs.txt
```

Expected: the candidate appears for main and the peeled annotated tag; the tag object line is distinct.

- [ ] **Step 5: Compare the untouched primary worktree against its pre-task state**

```zsh
git -C /Users/matianyi/Projects/robot_demo_001/moveit-demo status --short --branch \
  | tee /tmp/so101-debug-mujoco-fork-r7/final/primary-worktree-status.txt
git -C /Users/matianyi/Projects/robot_demo_001/moveit-demo/third_party/mujoco_ros2_control \
  status --short \
  | tee /tmp/so101-debug-mujoco-fork-r7/final/primary-submodule-status.txt
```

Expected: the user's pre-existing primary-worktree changes remain present and were not staged, reset, or overwritten.

- [ ] **Step 6: Commit any final documentation-only evidence correction**

If actual immutable hashes or test counts required correcting current documentation, make a targeted edit, rerun `git diff --check`, and commit:

```zsh
git add docs/guides docs/superpowers/specs
git diff --cached --check
git commit -m "docs: record verified mujoco fork r7 release"
```

Do not create an empty commit when no correction is needed.

- [ ] **Step 7: Produce the handoff inventory**

Report:

- fork candidate commit and all eleven commit subjects;
- Gitee main and peeled r7 tag read-back;
- macOS and Linux build/test counts, prefix/linkage checks, and bounded smoke results;
- moveit-demo integration commits and clean branch state;
- retained local evidence/build roots and retained ai-station roots;
- archived roots, expected to be none unless a retry was superseded;
- deletion candidates, including planning scratch directories, candidate bundles, and isolated build roots, with an explicit statement that nothing was deleted;
- that no experiment ledger or new five-win qualification was created;
- that `moveit-demo` itself has not been pushed unless the user explicitly requested that separate action.

---

## Completion Gate

The implementation is complete only when all of the following are true:

- Gitee fork `main` and peeled `so101-0.0.3-r7` resolve to the same validated candidate commit.
- r6 is an ancestor and the eleven exact topic commits produce binary diff SHA-256 `56b2f1033ccf48b44be6db8daee800f3f4d463048bd6cf2a7f8e58549ebde2f5`.
- macOS and Linux build all three packages directly from the clean candidate, pass package tests, pass platform linkage gates, and pass bounded reset/pause/step smoke.
- Fresh post-publication Gitee submodule checkouts pass the final installer on both platforms.
- Both locks, the gitlink, backend contract, installer, tests, and current guides agree on clean r7.
- No active patch series or installer patch application remains.
- The feature worktree and its submodule are clean; the user's primary dirty worktree is preserved.
- Evidence retention/archival/deletion-candidate inventory is reported, and no experiment ledger was changed.
