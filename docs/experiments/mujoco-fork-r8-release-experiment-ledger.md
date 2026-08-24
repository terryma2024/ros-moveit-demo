# MuJoCo fork r8 release experiment ledger

```yaml
task_id: so101-mujoco-fork-r8-release
goal: Publish the macOS missing-primary-monitor guard as mujoco_ros2_control r8 and make the MuJoCo 3.4.0 GLFW repair reproducibly applied by the macOS vendor installer.
success_contract: Gitee main and annotated r8 tag resolve to one validated fork commit; the superproject gitlink and both dependency locks match it; a pinned patch is hash-checked and replayed from a clean MuJoCo 3.4.0 checkout; package tests, clean builds, installed provenance, and GUI startup pass.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo
branch: main
base_commit: 5407592100823bcfa43138611f8de6b0de0c93f8
current_commit: 5407592100823bcfa43138611f8de6b0de0c93f8
evidence_root: /tmp/so101-debug-mujoco-fork-r8-release-20260824
confirmed_conclusions:
  - OBSERVED: third_party/mujoco_ros2_control and Gitee main are still clean r7 commit 6fa4485f1032dafdc76a515ddde8dd8bd6ccc23b before this task.
  - OBSERVED: relative to r7, the external mujoco_ros2_control working file has one extra primary-monitor/video-mode null guard.
  - OBSERVED: the external MuJoCo 3.4.0 checkout has a four-hunk simulate/glfw_adapter.cc repair and no commit.
disproven_routes:
  - Store simulate/glfw_adapter.cc inside the mujoco_ros2_control submodule; it belongs to the separately built MuJoCo vendor source.
open_hypotheses:
  - A source contract can prevent removal of the r8 guard without requiring a real missing-monitor GLFW session.
  - A clean detached MuJoCo 3.4.0 build source can receive the pinned patch idempotently and supply the macOS vendor package without mutating the authority checkout.
latest_checkpoint: CP-003
next_experiment: EXP-005
```

## EXP-001

```yaml
experiment_id: EXP-001
status: VALID
prior_experiment: NONE
hypothesis: New repository contracts fail against r7 and the absence of a replayable MuJoCo vendor patch installer.
prediction: Selected tests fail only on r8 tag/gitlink/guard and vendor patch replay requirements.
single_variable: Add contract tests before implementation.
lifecycle: ISOLATED_STACK
preconditions:
  - Superproject stays at 5407592100823bcfa43138611f8de6b0de0c93f8 with all pre-existing dirty files preserved.
  - No ROS 2, MoveIt, MuJoCo, RViz, or Gazebo process is running.
success_criteria:
  - Selected tests fail for the intended missing contracts.
failure_criteria:
  - Tests fail because pre-existing unrelated changes are overwritten or imported.
invalid_criteria:
  - Submodule or MuJoCo source provenance differs from the recorded commits.
provenance:
  source_commit: 5407592100823bcfa43138611f8de6b0de0c93f8
  install_overlay: /Users/matianyi/ros2_jazzy/extra_ws/install
  runtime_executable: NONE
  ros_domain_id: 192
  gz_partition: NONE
commands:
  - command: pytest selected r8 and vendor installer contracts
    exit_code: 1
observed:
  - OBSERVED: three selected tests failed at the intended missing guard, patch, and installer boundaries.
inferred:
  - NONE
conclusion: RED contract is valid and distinguishes both ownership boundaries before implementation.
evidence:
  - /tmp/so101-debug-mujoco-fork-r8-release-20260824/red-tests.txt
decision: KEEP
next_experiment: EXP-002
```

## EXP-002

```yaml
experiment_id: EXP-002
status: VALID
prior_experiment: EXP-001
hypothesis: Adding only the null guard to clean r7 source makes the fork contract pass without changing policy behavior.
prediction: The source contract passes, the fork package builds/tests cleanly, and the r7 policy_behavior_commit remains unchanged.
single_variable: Guard primary monitor and video mode before resizing the native viewer window.
lifecycle: ISOLATED_STACK
preconditions:
  - Submodule branch codex/macos-monitor-guard-r8 starts at clean r7 commit 6fa4485f1032dafdc76a515ddde8dd8bd6ccc23b.
success_criteria:
  - Source contract passes and fork build/test exits zero.
failure_criteria:
  - Compilation, package tests, or source contract fail.
invalid_criteria:
  - External dirty r6 fork source is used for the build.
provenance:
  source_commit: 6fa4485f1032dafdc76a515ddde8dd8bd6ccc23b
  install_overlay: /tmp/so101-debug-mujoco-fork-r8-release-20260824/fork-install
  runtime_executable: /tmp/so101-debug-mujoco-fork-r8-release-20260824/fork-install/lib/mujoco_ros2_control/ros2_control_node
  ros_domain_id: 192
  gz_partition: NONE
commands:
  - command: isolated colcon build of all fork packages against the patched vendor install
    exit_code: 0
  - command: first colcon test of mujoco_ros2_control
    exit_code: 1
  - command: rerun with ROS_LOG_DIR inside the registered evidence root
    exit_code: 0
  - command: colcon test-result --verbose
    exit_code: 0
observed:
  - OBSERVED: the isolated build completed for three fork packages.
  - OBSERVED: the first test run failed because two C++ tests could not write under ~/.ros/log; the new guard test and all 96 URDF conversion tests passed in that same run.
  - OBSERVED: after setting ROS_LOG_DIR to the registered evidence root, all five CTest entries passed and colcon reported 124 tests, 0 errors, 0 failures, 0 skipped.
inferred:
  - INFERRED: the first failure was an evidence-directory environment failure, not a fork logic regression.
conclusion: The r8 guard compiles and the complete mujoco_ros2_control package test set passes against the isolated patched MuJoCo vendor install.
evidence:
  - /tmp/so101-debug-mujoco-fork-r8-release-20260824
decision: KEEP
next_experiment: EXP-003
```

## EXP-003

```yaml
experiment_id: EXP-003
status: VALID
prior_experiment: EXP-002
hypothesis: The pinned MuJoCo patch can be verified and replayed into a clean detached 3.4.0 build source, then installed through the macOS vendor wrapper.
prediction: Prepare-only is idempotent, the prepared file hash matches the validated external fix, and isolated MuJoCo/vendor builds succeed.
single_variable: Add the pinned GLFW patch and macOS vendor installer.
lifecycle: ISOLATED_STACK
preconditions:
  - Authority source resolves to MuJoCo commit e55fff5dea6f1d5dd7963ca52eecc41d05ad0922.
success_criteria:
  - Patch SHA, clean authority, detached prepared source, post-patch source SHA, core build, and vendor install all pass.
failure_criteria:
  - Patch does not replay, source identity drifts, or build/install fails.
invalid_criteria:
  - Installer mutates the authority checkout or reuses its dirty working file.
provenance:
  source_commit: e55fff5dea6f1d5dd7963ca52eecc41d05ad0922
  install_overlay: /tmp/so101-debug-mujoco-fork-r8-release-20260824/vendor-install
  runtime_executable: NONE
  ros_domain_id: 192
  gz_partition: NONE
commands:
  - command: installer prepare-only twice and selected contract tests
    exit_code: 0
  - command: first full installer run before explicit colcon selection
    exit_code: 127
  - command: second full installer run before explicit Python selection
    exit_code: 1
  - command: full installer run with pinned venv colcon and Python
    exit_code: 0
observed:
  - OBSERVED: the zero-context replay patch SHA-256 is aa506e126cf8bec3bcc60a961fbe457e056d2aeb1838bb6c67c7584d7ac5264e.
  - OBSERVED: prepare-only is idempotent and leaves the clean authority checkout untouched.
  - OBSERVED: the detached prepared source has exactly one modified path, simulate/glfw_adapter.cc, with SHA-256 98dfb1e3a0ba29516f0ed9f6876b82089ad69bc60f2dd17c67e0eeea648fee3c.
  - OBSERVED: the first full run exposed colcon missing from PATH; the next run exposed system Python 3.14 missing catkin_pkg. The installer now resolves and validates the ROS workspace venv tools explicitly.
  - OBSERVED: MuJoCo core and mujoco_vendor wrapper built and installed successfully; ros2 pkg prefix, installed source hash, library, and CMake config read-backs matched the isolated prefix.
inferred:
  - INFERRED: sourcing a ROS overlay alone is insufficient to select colcon or its compatible Python on this macOS environment.
conclusion: The MuJoCo 3.4.0 GLFW fix is reproducibly replayed and installed without changing either the fork or authority checkout.
evidence:
  - /tmp/so101-debug-mujoco-fork-r8-release-20260824
decision: KEEP
next_experiment: EXP-004
```

## CP-002

```yaml
checkpoint_id: CP-002
last_valid_experiment: EXP-003
current_hypothesis: The locally validated fork commit can now be published as r8, then consumed by the superproject locks without importing unrelated working-tree changes.
working_tree_status: Superproject retains pre-existing dynamic cup changes; submodule has only the r8 guard and its test registration; replay patch and installer are new superproject paths.
owned_processes: NONE
preserved_processes: NONE
confirmed_conclusions:
  - The fork package builds against the patched vendor and has 124 passing tests.
  - The vendor installer replays the patch from exact clean MuJoCo 3.4.0 authority and passes isolated installation read-back.
disproven_routes:
  - Rely on sourced overlays to provide colcon or the matching Python interpreter.
  - Write ROS test logs under the default ~/.ros/log path in this controlled run.
open_risks:
  - Gitee main/tag and superproject dependency locks do not yet point at the new fork commit.
  - GUI startup validation and current installed-overlay replacement remain pending.
next_command: Commit the minimal fork diff, calculate the r8 commit identity, then update and test superproject locks before publication.
```

## EXP-004

```yaml
experiment_id: EXP-004
status: VALID
prior_experiment: EXP-003
hypothesis: The tested fork commit can be published without a remote race and both the Gitee branch and annotated tag can be read back to the same commit.
prediction: Remote main is still r7 before push; after a non-force push, main and the peeled r8 tag both resolve to the tested commit.
single_variable: Publish commit 78758d5becf1829e611da1dafb201fa018ddbe7b and annotated tag so101-0.0.3-r8.
lifecycle: ISOLATED_STACK
preconditions:
  - Local fork commit has completed EXP-002 and EXP-003 validation.
  - Gitee main resolves to r7 and the r8 tag is absent.
success_criteria:
  - Push succeeds without force and remote read-back matches the tested commit.
failure_criteria:
  - Remote main moved, push is rejected, or tag/main resolve to different commits.
invalid_criteria:
  - Any untested commit is published under r8.
provenance:
  source_commit: 78758d5becf1829e611da1dafb201fa018ddbe7b
  install_overlay: /tmp/so101-debug-mujoco-fork-r8-release-20260824/fork-install
  runtime_executable: /tmp/so101-debug-mujoco-fork-r8-release-20260824/fork-install/lib/mujoco_ros2_control/ros2_control_node
  ros_domain_id: 192
  gz_partition: NONE
commands:
  - command: git ls-remote before push
    exit_code: 0
  - command: git push origin tested-commit:main annotated-r8-tag
    exit_code: 0
  - command: git ls-remote after push
    exit_code: 0
observed:
  - OBSERVED: before push, Gitee main was 6fa4485f1032dafdc76a515ddde8dd8bd6ccc23b and r8 was absent.
  - OBSERVED: after push, Gitee main and the peeled so101-0.0.3-r8 tag both resolved to 78758d5becf1829e611da1dafb201fa018ddbe7b.
inferred:
  - NONE
conclusion: The tested fork commit is published as the unique Gitee r8 release identity.
evidence:
  - /tmp/so101-debug-mujoco-fork-r8-release-20260824
decision: KEEP
next_experiment: EXP-005
```

## EXP-005

```yaml
experiment_id: EXP-005
status: VALID
prior_experiment: EXP-004
hypothesis: The repository installer can reproduce the vendor repair in the real local ROS workspace while preserving the clean MuJoCo authority.
prediction: A wrong authority variable attempt fails before mutation; a run using the documented variables installs the patched bytes into extra_ws/install and leaves authority clean.
single_variable: Execute the repository installer against the real local ROS workspace.
lifecycle: FULL_RESTART
preconditions:
  - Clean authority is MuJoCo commit e55fff5dea6f1d5dd7963ca52eecc41d05ad0922.
  - No SO-101 runtime process is active.
success_criteria:
  - The fail-closed attempt changes no install output; the corrected run exits zero; installed GLFW bytes match the validated hash; authority remains clean.
failure_criteria:
  - Authority is modified, patch identity drifts, or build/install/read-back fails.
invalid_criteria:
  - Existing dirty extra_ws/src/mujoco is accepted as authority.
provenance:
  source_commit: e55fff5dea6f1d5dd7963ca52eecc41d05ad0922
  install_overlay: /Users/matianyi/ros2_jazzy/extra_ws/install
  runtime_executable: NONE
  ros_domain_id: 192
  gz_partition: NONE
commands:
  - command: installer with an unsupported authority variable name
    exit_code: 1
  - command: installer with SO101_MUJOCO_SOURCE_ROOT and documented workspace/install variables
    exit_code: 0
  - command: fresh zero-context prepare-only replay
    exit_code: 0
observed:
  - OBSERVED: the first run rejected dirty /Users/matianyi/ros2_jazzy/extra_ws/src/mujoco before build or install.
  - OBSERVED: the corrected run built MuJoCo core and the ROS vendor wrapper, then installed to /Users/matianyi/ros2_jazzy/extra_ws/install.
  - OBSERVED: a fresh zero-context patch replay produced the same patched source SHA-256 98dfb1e3a0ba29516f0ed9f6876b82089ad69bc60f2dd17c67e0eeea648fee3c and exactly one modified source path.
  - OBSERVED: the clean authority checkout remained unchanged.
inferred:
  - The fail-closed authority gate prevents accidental reuse of the previously edited external MuJoCo source.
conclusion: The replayable MuJoCo vendor repair is installed in the real local dependency overlay and remains reproducible from clean authority.
evidence:
  - /Users/matianyi/ros2_jazzy/mujoco_vendor_macos_ws
  - /Users/matianyi/ros2_jazzy/extra_ws/install/opt/mujoco_vendor/include/simulate/glfw_adapter.cc
  - /tmp/so101-debug-mujoco-fork-r8-release-20260824/vendor-zero-context-replay
decision: KEEP
next_experiment: EXP-006
```

## CP-003

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-005
current_hypothesis: The superproject r8 gitlink, locks, installer, patch, tests, and guides are ready for a scoped main-repository commit.
working_tree_status: Only explicitly selected r8 integration paths are staged; pre-existing dynamic cup and AMENT ordering changes remain unstaged.
owned_processes: NONE
preserved_processes: NONE
confirmed_conclusions:
  - Gitee main and peeled r8 tag match the tested fork commit.
  - The real local mujoco_vendor overlay contains bytes produced by the replay installer.
  - Full package pytest passes 252 tests; the focused macOS contract passes 13 tests; backend integration contract passes.
disproven_routes:
  - Use undocumented environment variable names for installer authority selection.
  - Store a normal contextual unified diff as a tracked artifact when repository diff-check treats its context prefixes as trailing whitespace.
open_risks:
  - The superproject integration commit and remote read-back are pending.
  - The existing external dirty r6 fork source workspace remains intentionally untouched; active fork overlay replacement is a separate operation.
next_command: Re-stage this ledger, run final staged diff checks, commit the scoped superproject integration, then push and read back origin.
```

## CP-001

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: The two previously validated external working-tree fixes can be published through separate reproducible ownership boundaries.
working_tree_status: Superproject dirty with pre-existing dynamic cup implementation and docs; submodule clean detached r7; external r6 fork workspace dirty; external MuJoCo 3.4.0 checkout dirty only at simulate/glfw_adapter.cc.
owned_processes: NONE
preserved_processes: NONE
confirmed_conclusions:
  - No fix is currently present in the clean r7 submodule or Gitee r7 release.
disproven_routes:
  - Treat the external dirty workspaces as publishable source authorities.
open_risks:
  - The current macOS source workspace is dirty, so release validation must use clean isolated build sources.
next_command: Add and run the selected RED contract tests.
```
