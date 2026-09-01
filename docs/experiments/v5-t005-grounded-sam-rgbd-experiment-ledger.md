# V5-T005 Grounding DINO Tiny + SAM 2.1 RGB-D experiment ledger

```yaml
task_id: so101-v5-t005-grounded-sam-rgbd
goal: 在 macOS MPS 与 ai-station CUDA 上使用 Grounding DINO Tiny 和 SAM 2.1 Hiera Tiny，从多物体 MuJoCo RGB-D 中选择唯一 plastic_cup，发布新鲜 /cup_pose，并完成仿真 pick&place
success_contract: 两个平台以同一 commit、模型包 SHA 和阈值通过四场景感知矩阵，随后各自 FULL_RESTART 连续 5 次 pick&place 成功
worktree: /Users/matianyi/.codex/worktrees/5b15/moveit-demo
branch: codex/v5-t004-yolo-seg-rgbd
base_commit: b55c869c919cd673bf84be8b125cc55a8e6eb98f
current_commit: a0b645923874b37a7bc193ce73891e8beca044f9
evidence_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869
development_source_root: /tmp/so101-debug-v5-t005-grounded-sam-20260901
design: docs/superpowers/specs/2026-09-01-v5-t005-grounded-dino-sam2-rgbd-perception-design.md
confirmed_conclusions:
  - CONF-001 设计固定使用 IDEA-Research/grounding-dino-tiny 与 facebook/sam2.1-hiera-tiny
  - CONF-002 首版采用 Transformers 进程内推理，逐帧无状态，不启用 SAM 2.1 视频跟踪
  - CONF-003 GroundedSamDetector 复用 DetectorPort、TargetSelector、RgbdLocalizer 与 /cup_pose 链路
  - CONF-004 生产 detector 只读 RGB；MuJoCo object ID、truth pose 与颜色规则只用于验收
  - CONF-005 macOS 使用 MPS，ai-station 使用 CUDA；CPU fallback 默认关闭
  - CONF-006 EXP-001 在 macOS 当前 worktree overlay 上完成 225 项定向测试和 1038 项 so101_demo_py 整包测试，errors/failures 均为 0
  - CONF-007 EXP-002/EXP-003 在 ai-station exact commit 隔离 checkout 上完成构建和 225 项 V5-T005 定向测试；Linux 整包门禁仍有与 V5-T005 无关的既有可移植性失败，不能记为通过
open_hypotheses:
  - HYP-001 Grounding DINO Tiny 对受控提示词 plastic cup. 能在四个 MuJoCo 场景中满足候选数量与类别门槛
  - HYP-002 SAM 2.1 Hiera Tiny 的框提示 mask 在两个平台都能达到 truth IoU >= 0.80
  - HYP-003 两阶段 warmed request latency 在两个平台都能 <= 2000 ms
  - HYP-004 新 detector 接入后，两个平台可以分别完成 FULL_RESTART 连续 5/5 pick&place
  - HYP-005 修正或正确隔离 Linux package runner 的 workspace-CWD 与 macOS-only ros2 命令前缀测试后，ai-station 整包门禁可达到 1038/1038
latest_checkpoint: CP-002
next_experiment: EXP-004 处理 Linux package-test 可移植性边界；通过前不进入真实模型包构建
```

## Checkpoints

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: 已批准架构、模型包、阈值起点、失败边界和双平台验收标准，等待实现计划
working_tree_status: 设计文档与本账本待提交；生产代码未修改
owned_processes: NONE
preserved_processes: 用户进程与既有 V5-T004 证据未触碰
retained_runs: []
archived_runs: []
deletion_candidates: []
next_command: 使用 superpowers:writing-plans 编写 V5-T005 实现计划
decision: DESIGN_APPROVED
```

## Experiments

```yaml
experiment_id: EXP-001
status: VALID
prior_experiment: NONE
hypothesis: Task 1-8 的 Grounded SAM 接入在 macOS 当前 ROS overlay 上通过全部定向测试和 so101_demo_py 整包门禁
prediction: 定向测试与整包 pytest 都收集非零测试，退出码为 0，JUnit errors/failures 为 0
single_variable: 在 qualification commit a0b645923874b37a7bc193ce73891e8beca044f9 上执行 Task 9 Mac package gate
lifecycle: ISOLATED_STACK
preconditions:
  - source commit 为 a0b645923874b37a7bc193ce73891e8beca044f9，显式 linked-worktree Git 视图无未提交文件
  - 先 source /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/setup.zsh，再 source 当前 worktree install/setup.zsh
  - ROS_HOME 与 ROS_LOG_DIR 位于 /tmp/so101-debug-v5-t005-grounded-sam-20260901
success_criteria:
  - 九个指定测试文件全部通过
  - src/so101_demo_py/test 整包测试收集非零，pytest exit 0，colcon test-result errors/failures 0
failure_criteria:
  - 任一 assertion failure、collection error 或 import provenance 错误
invalid_criteria:
  - so101_demo_py 不从当前 worktree install/build 解析，或 FreeJointState 不能从已登记 parent underlay 导入
provenance:
  source_commit: a0b645923874b37a7bc193ce73891e8beca044f9
  install_overlay: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install
  dependency_underlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  runtime_executable: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install/so101_demo_py
  python: /Users/matianyi/ros2_jazzy/.venv/bin/python3
  rclpy: /opt/ros/jazzy/rclpy/lib/python3.11/site-packages/rclpy/__init__.py
  ros_domain_id: UNSET_PACKAGE_TEST_NO_ROS_GRAPH
  gz_partition: UNSET_PACKAGE_TEST_NO_GAZEBO
commands:
  - command: source parent install/setup.zsh; source worktree install/setup.zsh; python3 -m pytest -p no:launch_testing -p no:launch_ros -p no:launch_pytest -p no:cacheprovider <nine Task 9 test files> -q --junitxml=/tmp/so101-debug-v5-t005-grounded-sam-20260901/task-9/directed-pytest.xml
    exit_code: 0
  - command: source parent install/setup.zsh; source worktree install/setup.zsh; PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test -q --junitxml=/tmp/so101-debug-v5-t005-grounded-sam-20260901/mac-package/so101_demo_py-pytest.xml
    exit_code: 0
  - command: /Users/matianyi/ros2_jazzy/.venv/bin/colcon test-result --test-result-base /tmp/so101-debug-v5-t005-grounded-sam-20260901/mac-package --verbose
    exit_code: 0
observed:
  - OBSERVED 定向测试 225 passed，2 条第三方 lark.utils deprecation warnings，1.85 s
  - OBSERVED Mac 整包 1038 passed，0 errors，0 failures，0 skipped，16.61 s
  - OBSERVED ros2 pkg prefix so101_demo_py 为 /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install/so101_demo_py
  - OBSERVED 整包首轮暴露 LaunchLogger(propagate=False) 下 caplog 监听 root 的测试隔离缺陷；RED 为 1 failed/1037 passed，修复后标准与非 launch logger 单测都通过，修复提交为 a0b645923874b37a7bc193ce73891e8beca044f9
inferred:
  - INFERRED Task 1-8 的模型包、adapter、factory、CLI/ROS 与 launch 契约在 macOS package runner 中没有剩余回归
conclusion: Mac package-level gate 通过；这只证明软件包契约，不证明真实 MPS 模型推理或 pick-place
evidence:
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-9/directed-pytest.xml sha256=eed43776c3eac5ba3c316eb4409b5ff7a90753b60dda123c5b664aa7c8c75c9f
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/mac-package/so101_demo_py-pytest.xml sha256=65f1171249513ab1870337d6c3dc0a28e9251da9e9c8053f06fb7b44ee011283
decision: KEEP
next_experiment: EXP-002
```

```yaml
experiment_id: EXP-002
status: VALID
prior_experiment: EXP-001
hypothesis: ai-station 可以在不修改 canonical 脏 checkout 的前提下，从 exact commit 隔离 checkout 构建并通过标准 so101_demo_py colcon package gate
prediction: 隔离 checkout HEAD 精确等于 a0b645923874b37a7bc193ce73891e8beca044f9，package prefix 指向隔离 install，colcon test-result 为 1038 tests、0 errors、0 failures
single_variable: 平台从 macOS 切换为 ai-station Linux；实现 commit 与 V5-T005 参数不变
lifecycle: ISOLATED_STACK
preconditions:
  - canonical /data/work/ws_moveit 保持 main@e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4，保留用户未跟踪文档
  - 使用 local git bundle 建立 /data/work/so101-v5-t005-grounded-sam-package-a0b6459
  - LFS 数据集使用 GIT_LFS_SKIP_SMUDGE=1 保留指针；V5-T005 package tests 不消费该 YOLO 数据包
success_criteria:
  - build exit 0，ros2 pkg prefix so101_demo_py 指向隔离 install
  - 标准 colcon test 收集非零，colcon test-result errors/failures 0
failure_criteria:
  - build 或 import provenance 失败，或任一 package test failure
invalid_criteria:
  - canonical checkout 被修改、清理、stash 或切换；source commit 与 bundle HEAD 不一致
provenance:
  source_commit: a0b645923874b37a7bc193ce73891e8beca044f9
  checkout: /data/work/so101-v5-t005-grounded-sam-package-a0b6459
  install_overlay: /data/work/so101-v5-t005-grounded-sam-package-a0b6459/install
  dependency_underlay: /data/work/ws_moveit/install
  runtime_executable: /data/work/so101-v5-t005-grounded-sam-package-a0b6459/install/so101_demo_py
  python: /usr/bin/python3 (Python 3.12.3)
  rclpy: /opt/ros/jazzy/lib/python3.12/site-packages/rclpy/__init__.py
  ros_domain_id: 95
  gz_partition: v5-t005-task9-package
commands:
  - command: colcon build --packages-select so101_demo_py --symlink-install --build-base /tmp/so101-debug-v5-t005-grounded-sam-20260901/linux-package-a0b6459/build --install-base /data/work/so101-v5-t005-grounded-sam-package-a0b6459/install
    exit_code: 0
  - command: PYTHONNOUSERSITE=1 colcon test --packages-select so101_demo_py --build-base /tmp/so101-debug-v5-t005-grounded-sam-20260901/linux-package-a0b6459/build --event-handlers console_direct+
    exit_code: 0
  - command: colcon test-result --test-result-base /tmp/so101-debug-v5-t005-grounded-sam-20260901/linux-package-a0b6459/build --verbose
    exit_code: 1
observed:
  - OBSERVED source commit 与隔离 checkout HEAD 都为 a0b645923874b37a7bc193ce73891e8beca044f9
  - OBSERVED ros2 pkg prefix so101_demo_py 为 /data/work/so101-v5-t005-grounded-sam-package-a0b6459/install/so101_demo_py，so101_demo import 来自登记 build base
  - OBSERVED 标准 colcon runner 收集 1038 项，1020 passed、18 failed；Grounded SAM adapter/config/bundle/postprocess 和 perception launch tests 均通过
  - OBSERVED 18 项由三类既有隔离环境假设组成：package source 目录运行时却按 repo-root 相对路径读文件；隔离 checkout 尚未 materialize git submodule/同前缀 support package；两个 test_mujoco_rgbd_batch_cli 测试按 macOS 两元素 ros2 launcher 前缀切片
  - OBSERVED canonical /data/work/ws_moveit HEAD 和未跟踪用户文档在测试后未变化
inferred:
  - INFERRED Linux package gate 未通过，不能由 225 项定向通过或 Mac 1038 项通过替代
conclusion: Linux 标准 package-level gate 有效失败；V5-T005 定向范围没有失败，但整个 so101_demo_py 仍不满足 Task 9 全绿条件
evidence:
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/linux-package-a0b6459/build/so101_demo_py/pytest.xml sha256=77f904c407003c1645a340a783117ab17657f0970287af9837e2c94b79d31770
  - local bundle /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-9/v5-t005-a0b6459.bundle sha256=cd82ac8eacb1c62dbfc33f66f812003aca754962dc84598839284b3ba938bea4
decision: KEEP
next_experiment: EXP-003
```

```yaml
experiment_id: EXP-003
status: VALID
prior_experiment: EXP-002
hypothesis: 将 exact gitlink submodule materialize，并从 repo root 运行 pytest，可区分隔离 checkout/CWD 缺口与真正的 Linux 可移植性测试失败
prediction: V5-T005 九文件定向测试全部通过；整包失败数显著少于 EXP-002，剩余失败不属于 Grounded SAM 文件
single_variable: 补齐锁定 submodule 与隔离 support prefix，并把 pytest 工作目录从 package source 改为 repo root；生产源码不变
lifecycle: ISOLATED_STACK
preconditions:
  - source commit 固定为 a0b645923874b37a7bc193ce73891e8beca044f9
  - third_party/mujoco_ros2_control 精确 materialize 为 71bc9346cf93d6227a6678fcacf63f3e18acfcba
  - canonical checkout 继续只读
success_criteria:
  - 225 项 V5-T005 定向测试全部通过
  - repo-root 整包结果只剩可以明确归属的非 V5-T005 portability failures
failure_criteria:
  - 任一 V5-T005 定向测试失败，或 Grounded SAM 文件在整包中失败
invalid_criteria:
  - source/submodule commit 漂移，或通过修改/清理 canonical checkout 消除失败
provenance:
  source_commit: a0b645923874b37a7bc193ce73891e8beca044f9
  submodule_commit: 71bc9346cf93d6227a6678fcacf63f3e18acfcba
  checkout: /data/work/so101-v5-t005-grounded-sam-package-a0b6459
  install_overlay: /data/work/so101-v5-t005-grounded-sam-package-a0b6459/install
  dependency_underlay: /data/work/ws_moveit/install
  runtime_executable: /data/work/so101-v5-t005-grounded-sam-package-a0b6459/install/so101_demo_py
  ros_domain_id: 95
  gz_partition: v5-t005-task9-package
commands:
  - command: PYTHONNOUSERSITE=1 python3 -m pytest -p no:launch_testing -p no:launch_ros -p no:launch_pytest -p no:cacheprovider <nine Task 9 test files> -q --junitxml=/tmp/so101-debug-v5-t005-grounded-sam-20260901/linux-package-a0b6459/directed-pytest.xml
    exit_code: 0
  - command: PYTHONNOUSERSITE=1 python3 -m pytest -p no:cacheprovider src/so101_demo_py/test -q --junitxml=/tmp/so101-debug-v5-t005-grounded-sam-20260901/linux-package-a0b6459/root-pytest-after-submodule.xml
    exit_code: 1
observed:
  - OBSERVED Linux V5-T005 定向测试 225 passed，4 warnings，4.20 s
  - OBSERVED repo-root 整包 1036 passed、2 failed、4 warnings；仅 test_mujoco_rgbd_batch_cli.py 的两个 macOS-prefix 假设失败
  - OBSERVED Linux ros2_command() 正确返回 ["ros2", "run", ...]，而测试无条件执行 argv[2:] 后仍期待首元素为 "run"；macOS 返回 [sys.executable, ros2_script, "run", ...]，所以该断言只在 macOS 成立
  - OBSERVED 未启动 Gazebo、MoveIt、RViz 或 pick_place_state_machine；owned processes 为 NONE
inferred:
  - INFERRED 这两项是既有跨平台测试设计缺口，不是 V5-T005 Grounded SAM 生产回归
conclusion: Linux V5-T005 定向契约通过；Linux 整包仍为 1036/1038，Task 9 package gate 未完成
evidence:
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/linux-package-a0b6459/directed-pytest.xml sha256=f185d19e097d5dd899d77043991d40c7580626ef19e1a9379013b824418fd114
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/linux-package-a0b6459/root-pytest-after-submodule.xml sha256=c030811f26b011df69518714915e7d5901928bddc44f6a65c92d495ac20189af
  - local submodule bundle /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-9/mujoco_ros2_control-71bc934.bundle sha256=b4e791377bbca49c4b666e35c3947d1184832787ad911a131c1bde4cd97e048e
decision: KEEP
next_experiment: EXP-004
```

## Checkpoint CP-002

```yaml
checkpoint_id: CP-002
last_valid_experiment: EXP-003
current_hypothesis: Linux package runner 的两个 test_mujoco_rgbd_batch_cli 测试需按 ros2_command 的平台前缀解析，随后从 repo root 重跑整包并恢复标准 colcon gate
working_tree_status: 新指南与本账本待提交；生产源码 clean；单测隔离修复已提交为 a0b645923874b37a7bc193ce73891e8beca044f9
owned_processes: NONE
preserved_processes: NONE；canonical /data/work/ws_moveit 用户未跟踪文档未触碰
confirmed_conclusions:
  - EXP-001 Mac 定向 225/225、整包 1038/1038
  - EXP-002/EXP-003 Linux exact commit 构建成功、V5-T005 定向 225/225
  - EXP-003 Linux repo-root 整包 1036/1038，剩余两项为非 V5-T005 的 macOS-only 命令前缀测试假设
disproven_routes:
  - 仅凭 Mac package gate 与 Linux 定向测试不能声明双平台 package gate 完成
open_risks:
  - Linux 标准 colcon runner 仍受 package-CWD 测试假设影响，且隔离 support package build 引入未在该 install 构建的 mujoco_3d_lidar dependency hook；未安装或修改任何系统依赖
  - 真实模型 bundle、MPS/CUDA smoke、四场景和两平台连续 5/5 均未执行
retained_runs:
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901
  - /data/work/so101-v5-t005-grounded-sam-package-a0b6459
archived_runs: []
deletion_candidates:
  - /data/work/so101-v5-t005-grounded-sam-package-a0e0eac
  - /data/work/so101-v5-t005-grounded-sam-package-a0e0eac-v2
  - /tmp/v5-t005-a0e0eac.bundle
  - /tmp/v5-t005-a0b6459.bundle
  - /tmp/mujoco_ros2_control-71bc934.bundle
next_command: 在独立 review/fix task 中为 test_mujoco_rgbd_batch_cli.py 增加 Linux ros2_command prefix 的 RED/GREEN 覆盖，然后重跑 ai-station 1038 项 package gate
decision: TASK_9_BLOCKED_BY_LINUX_PACKAGE_PORTABILITY
```
