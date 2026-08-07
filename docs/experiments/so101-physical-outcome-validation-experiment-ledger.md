# SO-101 物理结果验证实验账本

```yaml
task_id: so101-physical-outcome-validation
goal: 仅以 Gazebo 物理结果判定 SO-101 抓取放置成功，并保持 MoveIt attachment 仅作为 planning shadow
success_contract: 同一提交和已校准策略下五次连续 VALID execute，最终稳定物理结果与全部硬安全不变量均通过
worktree: /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation
branch: codex/so101-physical-outcome-validation
base_commit: 05dff7a18e466c01486441dd90c21fcd44d4d8cd
current_commit: 02c929364f889d73333ec76f7384040cce58d7f0
evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI
confirmed_conclusions:
  - Task 13 branch-tree build、三包测试、dry-run trace 与 uncalibrated plan-only fail-closed gate 已验证（VER-PHYSICAL-001）
disproven_routes:
  - 0.75 mm seat
  - independent CLOSE seat motion
  - longer close duration as a fix
  - safety-gate relaxation
  - unregistered fixed-port retry fixture
open_hypotheses:
  - 每个 CALIBRATION_REQUIRED 字段的 live calibration 值
latest_checkpoint: CP-PHYSICAL-001
next_experiment: CAL-PHYSICAL-001
```

## VER-PHYSICAL-001：Task 13 自动验证

```yaml
experiment_id: VER-PHYSICAL-001
status: VALID
prior_experiment: NONE
hypothesis: 当前 branch tree 保持 Panda 兼容，并在未校准时于任何 plan-only/execute mutation 前 fail closed
prediction: 三包测试无失败；dry-run 含新状态且无 forward Gazebo attachment；plan-only 报 PHYSICAL_OUTCOME_CALIBRATION_REQUIRED
single_variable: NONE
lifecycle: FULL_RESTART
provenance:
  source_commit: 02c929364f889d73333ec76f7384040cce58d7f0
  install_overlay: /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation/build/so101_gazebo_demo/pick_place_state_machine
  package_prefixes:
    pick_place_common: /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation/install/pick_place_common
    panda_gazebo_demo: /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation/install/panda_gazebo_demo
    so101_gazebo_demo: /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation/install/so101_gazebo_demo
  bun: /home/lenovo/.bun/bin/bun 1.3.14
commands:
  - command: colcon build --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --symlink-install --cmake-clean-cache
    exit_code: 0
  - command: PYTHONNOUSERSITE=1 colcon test --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --event-handlers console_direct+
    exit_code: 1
    note: Panda relay 在三包并行负载下内部 timeout 124；SO101 83/83 通过
  - command: ctest --test-dir build/panda_gazebo_demo -R '^test_attachment_state_relay$' --output-on-failure
    exit_code: 0
  - command: PYTHONNOUSERSITE=1 colcon test --packages-select panda_gazebo_demo --event-handlers console_direct+
    exit_code: 0
    result: Panda 35/35；最终聚合 1327 tests、0 errors、0 failures、90 skipped
  - command: ros2 launch so101_gazebo_demo so101_pick_place.launch.py run_mode:=dry_run start_simulation:=false
    exit_code: 0
  - command: ros2 launch so101_gazebo_demo so101_pick_place.launch.py run_mode:=plan_only plan_only_state:=MOVE_ABOVE_OBJECT start_simulation:=false
    exit_code: 0
    child_exit_code: 2
observed:
  - dry-run trace 含 WAIT_RELEASE_SETTLE 与 VALIDATE_FINAL_PLACEMENT，且不含 ATTACH_GAZEBO/DETACH_GAZEBO
  - plan-only 子进程在 BOOTSTRAP -> ERROR 报 PHYSICAL_OUTCOME_CALIBRATION_REQUIRED，未发生 mutation
  - Panda relay 单独重跑及 Panda 全包均通过；首次并行 timeout 不用于产品行为结论
  - 原 so101-reset-world-five-success-experiment-ledger.md 未修改
invalid_attempts:
  - ROS setup 前启用 set -u，导致 setup 脚本未定义变量错误，应用未启动
  - 未提供 plan_only_state，先触发 PLAN_ONLY_STATE_REQUIRED，未检验 calibration gate
evidence:
  - /tmp/so101-debug-physical-outcome-xZlFSI/dry-run-valid.log
  - /tmp/so101-debug-physical-outcome-xZlFSI/plan-only-state.log
conclusion: 自动化实现边界成立；live execute 仍被未校准策略按设计阻止
decision: KEEP
next_experiment: CAL-PHYSICAL-001
```

## CP-PHYSICAL-001

```yaml
checkpoint_id: CP-PHYSICAL-001
last_valid_experiment: VER-PHYSICAL-001
current_hypothesis: 可从隔离 headless 观测分布中校准全部新阈值，且无需放宽既有安全 ceiling
working_tree_status: docs/experiments/so101-physical-outcome-validation-experiment-ledger.md newly created
owned_processes: NONE
preserved_processes: 其他 so101-gazebo-demo-py worktree 的 gz sim，以及 so101-workspace-sampler 的 clang-tidy
confirmed_conclusions:
  - 当前 overlay 与 source provenance 一致
  - Panda 行为保持，SO101 正常 forward path 无 Gazebo attach/detach
open_risks:
  - 新 policy thresholds 尚未校准，execute 必须继续 fail closed
  - 尚无本提交的 GUI execute 或 final-outcome screenshot
next_command: 建立 CAL-PHYSICAL-001 PLANNED 条目并只读采集隔离 headless baseline evidence
```

## 五次连续最终结果批次（尚未开始）

每次必须记录：run ID、source/policy hash、`ROS_DOMAIN_ID`、`GZ_PARTITION`、overlay、cleanup owner、final code、release epoch id/start/first/last sequence、sample count/duration、final pose、support/gripper contacts、Gazebo/MoveIt detached、world sync、shadow 最大 divergence、collision/penetration maxima、controller health、fresh screenshot 路径与结果。没有五次连续 `VALID` 不得声明验收成功。
