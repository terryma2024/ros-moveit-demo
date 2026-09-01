# V5-T005 Grounding DINO Tiny + SAM 2.1 RGB-D experiment ledger

```yaml
task_id: so101-v5-t005-grounded-sam-rgbd
goal: 在 macOS MPS 与 ai-station CUDA 上使用 Grounding DINO Tiny 和 SAM 2.1 Hiera Tiny，从多物体 MuJoCo RGB-D 中选择唯一 plastic_cup，发布新鲜 /cup_pose，并完成仿真 pick&place
success_contract: 两个平台以同一 commit、模型包 SHA 和阈值通过四场景感知矩阵，随后各自 FULL_RESTART 连续 5 次 pick&place 成功
worktree: /Users/matianyi/.codex/worktrees/5b15/moveit-demo
branch: codex/v5-t004-yolo-seg-rgbd
base_commit: b55c869c919cd673bf84be8b125cc55a8e6eb98f
current_qualification_commit: 70675004e3ed66ce6bd5811a8f922565e08f668d
guide_fix_commit: 9450fd77504e4719ca9b6b351cbb4068f81eeb0d
ledger_baseline_commit: c777f58fc29c6b1e0f7493f3d98032499b4b8052
ledger_parent_before_fix_round_2_record: f52b8b14e361ed0c85fc2f17ae2e6e43776dc0db
ledger_record_commit: 本文件不自指提交 SHA；本次 ledger 提交完成后的精确 SHA 记录在 task-10-report.md 的 Commits 段
evidence_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869
development_source_root: /tmp/so101-debug-v5-t005-grounded-sam-20260901
design: docs/superpowers/specs/2026-09-01-v5-t005-grounded-dino-sam2-rgbd-perception-design.md
confirmed_result: exact 16d56fc 在 Linux CUDA 与 macOS MPS 上以同一 immutable bundle 完成 actual offline Task 10 smoke 与模拟 PickPlace；本 smoke 不计入 Task 11 四场景或 5/5
confirmed_conclusions:
  - CONF-001 设计固定使用 IDEA-Research/grounding-dino-tiny 与 facebook/sam2.1-hiera-tiny
  - CONF-002 首版采用 Transformers 进程内推理，逐帧无状态，不启用 SAM 2.1 视频跟踪
  - CONF-003 GroundedSamDetector 复用 DetectorPort、TargetSelector、RgbdLocalizer 与 /cup_pose 链路
  - CONF-004 生产 detector 只读 RGB；MuJoCo object ID、truth pose 与颜色规则只用于验收
  - CONF-005 macOS 使用 MPS，ai-station 使用 CUDA；CPU fallback 默认关闭
  - CONF-006 EXP-001 在 macOS 当前 worktree overlay 上完成 225 项定向测试和 1038 项 so101_demo_py 整包测试，errors/failures 均为 0
  - CONF-007 EXP-002/EXP-003 在 ai-station exact commit 隔离 checkout 上完成构建和 225 项 V5-T005 定向测试；Linux 整包门禁仍有与 V5-T005 无关的既有可移植性失败，不能记为通过
  - CONF-008 EXP-004 修正固定错误码、依赖锁、离线环境门禁和 Linux ros2 前缀测试后，macOS 与 ai-station 分别通过 229 项定向测试和 1044 项整包测试
  - CONF-009 EXP-005 删除 verifier 的调用方依赖覆盖入口后，macOS 与 ai-station 分别通过 230 项定向测试和 1045 项整包测试
  - CONF-010 EXP-006 以 exact revisions 构建同一 immutable bundle，Linux/Mac manifest SHA 均为 838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3
  - CONF-011 EXP-012 的 Linux CUDA 与 macOS MPS actual offline one-cup smoke 及模拟 PickPlace 均通过；Mac source age 为 1.626 s，未放宽 2.0 s gate；本 smoke 不计入 Task 11
  - CONF-012 最终 Mac exact 16d56fc 批次已按 53 项（49 regular、4 symlink）完整 inventory 复制到 durable root 并逐项 read-back；inventory、archive、verify log SHA256 分别为 4049e685881ee4b6aa54f2f302c79b7c578cdc58ceec10002805a3839d057d8e、a81069e24f8c26314743354890683b2b3e7fa1fecf446877ea39b517f68cdd34、26c232170d1323ae713555a5f7007d80a651e1c0e268420d571e02fdb2028ac7
open_hypotheses:
  - HYP-001 Grounding DINO Tiny 对受控提示词 plastic cup. 能在四个 MuJoCo 场景中满足候选数量与类别门槛
  - HYP-002 SAM 2.1 Hiera Tiny 的框提示 mask 在两个平台都能达到 truth IoU >= 0.80
  - HYP-004 新 detector 接入后，两个平台可以分别完成 FULL_RESTART 连续 5/5 pick&place
latest_checkpoint: CP-010
next_experiment: EXP-054 linux-matrix-r4-1-task_start
```

## Checkpoints

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: 已批准架构、模型包、阈值起点、失败边界和双平台验收标准，等待实现计划
working_tree_status: CP-001 建立时设计与账本尚未提交，生产代码未修改；后续提交状态见 CP-003
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
  - command: source /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/setup.zsh; source /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install/setup.zsh; /Users/matianyi/ros2_jazzy/.venv/bin/python -m pytest -p no:launch_testing -p no:launch_ros -p no:launch_pytest -p no:cacheprovider src/so101_demo_py/test/test_model_runtime.py src/so101_demo_py/test/test_grounded_sam_config.py src/so101_demo_py/test/test_grounded_sam_bundle.py src/so101_demo_py/test/test_grounded_sam_postprocess.py src/so101_demo_py/test/test_grounded_sam_adapter.py src/so101_demo_py/test/test_detector_factory.py src/so101_demo_py/test/test_detection_contracts.py src/so101_demo_py/test/test_rgbd_object_pose.py src/so101_demo_py/test/test_perception_pick_place_launch.py -q --junitxml=/tmp/so101-debug-v5-t005-grounded-sam-20260901/task-9/directed-pytest.xml
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
  - command: cd /data/work/so101-v5-t005-grounded-sam-package-a0b6459; source /opt/ros/jazzy/setup.zsh; source /data/work/ws_moveit/install/setup.zsh || true; source /data/work/so101-v5-t005-grounded-sam-package-a0b6459/install/setup.zsh; PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:launch_testing -p no:launch_ros -p no:launch_pytest -p no:cacheprovider src/so101_demo_py/test/test_model_runtime.py src/so101_demo_py/test/test_grounded_sam_config.py src/so101_demo_py/test/test_grounded_sam_bundle.py src/so101_demo_py/test/test_grounded_sam_postprocess.py src/so101_demo_py/test/test_grounded_sam_adapter.py src/so101_demo_py/test/test_detector_factory.py src/so101_demo_py/test/test_detection_contracts.py src/so101_demo_py/test/test_rgbd_object_pose.py src/so101_demo_py/test/test_perception_pick_place_launch.py -q --junitxml=/tmp/so101-debug-v5-t005-grounded-sam-20260901/linux-package-a0b6459/directed-pytest.xml
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
working_tree_status: CP-002 当时指南与账本尚未提交；随后由 db92657 提交，生产源码当时 clean
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
  - ai-station:/data/work/so101-v5-t005-grounded-sam-package-a0b6459
archived_runs: []
deletion_candidates:
  - ai-station:/data/work/so101-v5-t005-grounded-sam-package-a0e0eac
  - ai-station:/data/work/so101-v5-t005-grounded-sam-package-a0e0eac-v2
  - ai-station:/tmp/v5-t005-a0e0eac.bundle
  - ai-station:/tmp/v5-t005-a0b6459.bundle
  - ai-station:/tmp/mujoco_ros2_control-71bc934.bundle
next_command: 在 exact commit 隔离 checkout 中构建同前缀 so101_mujoco_support，并用 repo-root CWD runner 重跑标准 colcon package gate
decision: TASK_9_BLOCKED_BY_LINUX_PACKAGE_PORTABILITY
```

```yaml
experiment_id: EXP-004
status: VALID
prior_experiment: EXP-003
hypothesis: 固定错误码、锁文件 provenance、强制离线环境和 Linux ros2 前缀测试修复后，两个平台的定向与整包门禁都能通过
prediction: macOS 和 ai-station 定向测试均为 229/229，整包均为 1044/1044，errors/failures 为 0
single_variable: 在 a0b6459 资格基线之上应用三个 scoped fix commits；真实模型、场景与运动执行保持不运行
lifecycle: ISOLATED_STACK
preconditions:
  - qualification commit 固定为 b2fb7b7433f44bf31372dcb7fed6e60a3656aeb2
  - ai-station 使用 exact local git bundle 建立新 checkout，不修改 canonical /data/work/ws_moveit
  - 不安装 Python、OS 或模型依赖；不启动 MuJoCo、MoveIt、RViz 或抓放流程
success_criteria:
  - 三组 RED 先失败且原因分别命中错误码、依赖/离线门禁和 Linux argv 前缀
  - Mac 定向与整包测试全部通过
  - ai-station exact checkout 构建成功，定向与标准 colcon package gate 全部通过
failure_criteria:
  - 任一 contract failure、import/provenance 漂移，或 canonical checkout 状态变化
invalid_criteria:
  - 从运行环境 freeze 依赖、允许在线 loader、修改 canonical checkout，或以 repo-root direct pytest 冒充标准 colcon gate
rulings:
  - RUL-009 requirements.lock 是 bundle 依赖版本的构建权威；缺失、重复、非法 pin 在 snapshot 下载前 fail closed，verifier 还会检查 manifest 是否等于固定预期映射
  - RUL-010 GroundedSamDetector 在任何 Hugging Face loader 前把 HF_HUB_OFFLINE 和 TRANSFORMERS_OFFLINE 强制设为 1；调用方已有冲突值时由本进程覆盖，local_files_only=True 仍保留
  - RUL-011 标准 colcon 的 package-source CWD 与仓库既有 repo-root 相对路径契约通过 evidence-root pytest plugin 对齐；同 checkout 的 so101_mujoco_support 必须构建到同一 install prefix
provenance:
  candidate_limit_commit: 25b84d1a6cee9a42c6607d4e3704cb783f10969e
  bundle_offline_commit: da1a91fabf28c4d9309aeb14ee647ba0460813f9
  linux_test_portability_commit: b2fb7b7433f44bf31372dcb7fed6e60a3656aeb2
  qualification_commit: b2fb7b7433f44bf31372dcb7fed6e60a3656aeb2
  guide_fix_commit: 9450fd77504e4719ca9b6b351cbb4068f81eeb0d
  mac_install_overlay: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install
  mac_dependency_underlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  linux_checkout: /data/work/so101-v5-t005-grounded-sam-package-b2fb7b7
  linux_install_overlay: /data/work/so101-v5-t005-grounded-sam-package-b2fb7b7/install
  linux_dependency_underlay: /data/work/ws_moveit/install
  linux_submodule_commit: 71bc9346cf93d6227a6678fcacf63f3e18acfcba
  linux_python: /usr/bin/python3 (Python 3.12.3)
  linux_rclpy: /opt/ros/jazzy/lib/python3.12/site-packages/rclpy/__init__.py
  linux_ros_domain_id: 95
  linux_gz_partition: v5-t005-task9-fix
commands:
  - exact_command_log: /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-9/fix-round-2/commands.md
    mirror_on_ai_station: /tmp/so101-debug-v5-t005-grounded-sam-20260901/linux-package-6242fe9/commands.md
    sha256: 6a8f3ecfe578d24be438f5848c9952b6122791b968554f892b68d0623818bc03
    coverage: 包含 Mac overlay/build/定向/整包命令、exact bundle 与隔离 checkout、Linux 同前缀 support 构建、repo-CWD pytest plugin、定向/标准 colcon 整包和最终 provenance 检查；主机、工作目录、环境变量和证据路径均为完整值
observed:
  - OBSERVED candidate-limit RED 为 1 failed；旧值 RESULT_CONTRACT_INVALID，期望 CANDIDATE_LIMIT_EXCEEDED；GREEN 为 30 passed
  - OBSERVED bundle/offline RED 为 6 failed、10 passed；GREEN 为 29 passed，fake loader 的四次调用都看到两个 offline 变量为 1
  - OBSERVED Linux prefix RED 为 2 failed、2 passed；只失败 Linux 参数；GREEN 整文件 7 passed
  - OBSERVED Mac 定向 229 passed、2 warnings，整包 1044 passed；test-result 为 1044 tests、0 errors、0 failures
  - OBSERVED ai-station 定向 229 passed、4 warnings，标准 colcon 最终为 1044 passed、4 warnings；test-result 为 1044 tests、0 errors、0 failures
  - OBSERVED 标准 colcon 第一次在 pytest 前因隔离 prefix 缺 mujoco_3d_lidar hook 退出，没有生成 JUnit；忽略未选 submodule packages 后首次 pytest 为 1043/1044，唯一失败是 support prefix 仍来自 canonical underlay
  - OBSERVED 将 exact checkout 的 so101_mujoco_support 构建到同一 install prefix 后，package/import provenance 与整包均通过
  - OBSERVED a0b6459 首轮 LaunchLogger RED JUnit 在原任务中未保留；现有证据仅保留其 GREEN 后 1038 项 JUnit，Fix Round 1 未伪造旧 RED
  - OBSERVED canonical ai-station 仍为 main@e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4，并保留用户未跟踪文档
inferred:
  - INFERRED 双平台软件包契约门禁已经完成；这不等于真实模型下载、MPS/CUDA 推理、四场景或 pick-place 已完成
conclusion: Task 9 package-level gate 通过；Task 10/11 的真实模型与运动验收仍为 pending
evidence:
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-9/fix-round-1/mac/candidate-limit-red.xml sha256=8899406a76db498074131791b8bd99eb6760fe06946f17f41906a94dbf3a2a6c
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-9/fix-round-1/mac/bundle-offline-red.xml sha256=496306a65d538cddf0514eb36a0ebf8447ee210d48d951eb5055aa5e882c56a7
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-9/fix-round-1/mac/linux-prefix-red.xml sha256=aaa77a3926779a7d42d0001ad039f01d0421b059e5e591f86297fc030493b0c8
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-9/fix-round-1/mac/directed-pytest.xml sha256=4b2ba8d6655b186e2ae5e0e0333b400cb3b83f0101c43ca0f307f01c32f55da6
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/mac-package/so101_demo_py-pytest.xml sha256=64a61e7e7083dc113b1a7e962a47a9422f1836a666f6473305c582356aaf8959
  - ai-station:/tmp/so101-debug-v5-t005-grounded-sam-20260901/linux-package-b2fb7b7/directed-pytest.xml sha256=a47724b61df8d45670a5bb23bfd5b9063a62f59d2b55cd17e839023ec94270d7
  - ai-station:/tmp/so101-debug-v5-t005-grounded-sam-20260901/linux-package-b2fb7b7/standard-green/so101_demo_py/pytest.xml sha256=7653237cafb5749d3286939d0fafc77d085c43d6effc40652f289a5e839ade1c
  - ai-station:/tmp/so101-debug-v5-t005-grounded-sam-20260901/linux-package-b2fb7b7/standard-final/so101_demo_py/pytest.xml sha256=bba215140b5a1c8f0854afdb3fa157a529e734e4735e93411bc4ab70fafed4ed
  - ai-station:/tmp/so101-debug-v5-t005-grounded-sam-20260901/linux-package-b2fb7b7/test-support/so101_repo_root_cwd.py sha256=9e712e92874ab828666e3f485c5dbcceb27d57fdd0182a7685a26f66d4785c7f
decision: KEEP
next_experiment: EXP-005
```

## Checkpoint CP-003

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-004
current_hypothesis: 软件包契约已具备真实模型资格；下一步需要 Task 10 的依赖安装授权和真实 bundle 才能验证 MPS/CUDA
qualification_commit: b2fb7b7433f44bf31372dcb7fed6e60a3656aeb2
guide_fix_commit: 9450fd77504e4719ca9b6b351cbb4068f81eeb0d
working_tree_status: qualification 与指南提交后 clean；本 checkpoint 由包含该记录的账本提交承载
owned_processes: NONE
preserved_processes: NONE；canonical /data/work/ws_moveit 用户未跟踪文档未触碰
confirmed_conclusions:
  - Fix Round 1 三组 RED/GREEN 契约均有 JUnit
  - Mac 定向 229/229、整包 1044/1044
  - Linux exact checkout 定向 229/229、标准 colcon 整包 1044/1044
  - package-CWD 仍需 registered-root runner plugin，support package 仍需同 prefix 构建；这是标准门禁的环境前置条件
open_risks:
  - 真实模型 bundle 尚未下载或构建，真实 MPS/CUDA smoke 未运行
  - 四场景、mask truth IoU、延迟和两个平台连续 5/5 pick-place 均未执行
retained_runs:
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901
  - ai-station:/data/work/so101-v5-t005-grounded-sam-package-a0b6459
  - ai-station:/data/work/so101-v5-t005-grounded-sam-package-b2fb7b7
  - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869
archived_runs: []
deletion_candidates:
  - ai-station:/data/work/so101-v5-t005-grounded-sam-package-a0e0eac
  - ai-station:/data/work/so101-v5-t005-grounded-sam-package-a0e0eac-v2
  - ai-station:/tmp/v5-t005-a0e0eac.bundle
  - ai-station:/tmp/v5-t005-a0b6459.bundle
  - ai-station:/tmp/v5-t005-b2fb7b7.bundle
  - ai-station:/tmp/mujoco_ros2_control-71bc934.bundle
  - mac:/tmp/v5-t005-b2fb7b7.bundle
next_command: Task 10 获得依赖安装授权后，按 requirements.lock 建隔离环境并构建真实 immutable bundle；随后在 Mac MPS 与 Linux CUDA 运行 offline smoke
decision: TASK_9_COMPLETE_PACKAGE_QUALIFIED_REAL_MODEL_PENDING
```

```yaml
experiment_id: EXP-005
status: VALID
prior_experiment: EXP-004
hypothesis: verifier 不再接受调用方提供的依赖映射后，重算 manifest SHA 也不能放行偏离 requirements.lock 的依赖，同时双平台包级门禁保持通过
prediction: 回归测试先证明旧 API 可被调用方覆盖，再由双参数 verifier 拒绝该调用；Mac 与 ai-station 定向为 230/230，整包为 1045/1045
single_variable: 删除 verify_model_bundle 的公开 expected_dependencies override，并让内部文件校验始终对照 requirements.lock 解析得到的固定 pins
lifecycle: ISOLATED_STACK
preconditions:
  - 资格提交固定为 6242fe967c0574e9175965a7e5790aecb9d427f5
  - Mac 先 source parent install，再 source 当前 worktree install
  - ai-station 从 exact local git bundle 建立 /data/work/so101-v5-t005-grounded-sam-package-6242fe9，不修改 canonical /data/work/ws_moveit
  - Linux 标准 colcon 使用已保留的 repo-root CWD plugin，并把 so101_mujoco_support 构建到同一候选 prefix
success_criteria:
  - test-only RED 表明旧 verifier 接受 expected_dependencies keyword，不能抛出 TypeError
  - GREEN 表明公开函数仅保留 root 与 manifest_digest 两个参数，重算 SHA 的任意依赖 mapping 不能通过调用方 override
  - 两个平台的定向和整包 JUnit 均为零 errors/failures
failure_criteria:
  - 生产调用方仍能传入依赖映射、任一包级门禁失败，或 canonical checkout 状态变化
invalid_criteria:
  - 修改 requirements.lock 固定 pins、安装新依赖、删除证据，或修改 canonical checkout
rulings:
  - RUL-012 verify_model_bundle 的依赖预期不属于调用方策略；verifier 始终使用仓库 requirements.lock 的固定映射，公开 API 不提供 override
  - RUL-013 Fix Round 2 不修改中文指南，因为现有 manifest/offline 说明已与最终源码一致；因此不做无意义的二次 humanizer 改写
provenance:
  verifier_fix_commit: 6242fe967c0574e9175965a7e5790aecb9d427f5
  qualification_commit: 6242fe967c0574e9175965a7e5790aecb9d427f5
  guide_fix_commit: 9450fd77504e4719ca9b6b351cbb4068f81eeb0d
  prior_ledger_commit: c777f58fc29c6b1e0f7493f3d98032499b4b8052
  repository_head_at_qualification: 6242fe967c0574e9175965a7e5790aecb9d427f5
  mac_install_overlay: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install
  mac_dependency_underlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  linux_host: ai-station
  linux_checkout: /data/work/so101-v5-t005-grounded-sam-package-6242fe9
  linux_install_overlay: /data/work/so101-v5-t005-grounded-sam-package-6242fe9/install
  linux_dependency_underlay: /data/work/ws_moveit/install
  linux_submodule_commit: 71bc9346cf93d6227a6678fcacf63f3e18acfcba
  linux_python: /usr/bin/python3 (Python 3.12.3)
  linux_rclpy: /opt/ros/jazzy/lib/python3.12/site-packages/rclpy/__init__.py
  linux_ros_domain_id: 95
  linux_gz_partition: v5-t005-task9-fix-r2
commands:
  - exact_command_log: /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-9/fix-round-2/commands.md
    mirror_on_ai_station: /tmp/so101-debug-v5-t005-grounded-sam-20260901/linux-package-6242fe9/commands.md
    sha256: 6a8f3ecfe578d24be438f5848c9952b6122791b968554f892b68d0623818bc03
    exit_codes: RED=1; GREEN=0; Mac directed=0; Mac full=0; Linux build=0; Linux directed=0; Linux standard colcon=0; Linux test-result=0
observed:
  - OBSERVED verifier override RED 为 1 failed；旧函数接受 expected_dependencies keyword，因此测试期望的 TypeError 未发生
  - OBSERVED 修复后 test_grounded_sam_bundle.py 为 16 passed；rg 检查生产源码与调用方不再出现 expected_dependencies，唯一出现处是故意触发 TypeError 的回归测试
  - OBSERVED Mac 定向 230 passed、2 warnings，整包 1045 passed；test-result 为 1045 tests、0 errors、0 failures
  - OBSERVED ai-station exact checkout 定向 230 passed、4 warnings，标准 colcon 整包 1045 passed、4 warnings；test-result 为 1045 tests、0 errors、0 failures
  - OBSERVED canonical ai-station 复验前后均为 main@e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4，并保留用户未跟踪文档
inferred:
  - INFERRED bundle 依赖 provenance 的调用方绕过已经关闭，且 Fix Round 2 未引入跨平台包级回归
  - INFERRED 这些结果仍不证明真实模型下载、MPS/CUDA 推理、四场景或 pick-place 成功
conclusion: Task 9 Fix Round 2 package-level qualification 通过；Task 10/11 仍为 pending
evidence:
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-9/fix-round-2/mac/verifier-override-red.xml sha256=b3dd96df4c9427345e795c59b08d1c26239430680f719fbfeed1d21698b49d8a
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-9/fix-round-2/mac/verifier-override-green.xml sha256=4c1766c654933d2d917077bc6a0dce2495e9796242c29166abe571b648d38aa7
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-9/fix-round-2/mac/directed-pytest.xml sha256=9e766e51746da4fbf07440f0af32c26d473f47ab58c838c4c428ed804e3ad25d
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/mac-package/so101_demo_py-pytest.xml sha256=4c39faff7f507c0187393a0a8c8ca27515b6286c0c8a1bade23c93e941ff16cc
  - /tmp/v5-t005-6242fe9.bundle sha256=f77aebb3497984912406295a58988fba91ebb7d0c3e873b14a804b7b60f8f56f
  - ai-station:/tmp/so101-debug-v5-t005-grounded-sam-20260901/linux-package-6242fe9/directed-pytest.xml sha256=64ec7d9fca8c9e51ea0e3100bdbed0a01a8ecc1a47db300e7b63ead463565938
  - ai-station:/tmp/so101-debug-v5-t005-grounded-sam-20260901/linux-package-6242fe9/standard-final/so101_demo_py/pytest.xml sha256=88c1e90c5bdf0630fa365505462da2c3273e31e33a485dad6ccd28ffb2216626
  - ai-station:/tmp/so101-debug-v5-t005-grounded-sam-20260901/linux-package-6242fe9/test-support/so101_repo_root_cwd.py sha256=9e712e92874ab828666e3f485c5dbcceb27d57fdd0182a7685a26f66d4785c7f
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-9/fix-round-2/commands.md sha256=6a8f3ecfe578d24be438f5848c9952b6122791b968554f892b68d0623818bc03
decision: KEEP
next_experiment: Task 10 获得依赖安装授权后，构建真实 immutable bundle 并运行 Mac MPS 与 Linux CUDA offline smoke
```

## Checkpoint CP-004

```yaml
checkpoint_id: CP-004
last_valid_experiment: EXP-005
current_hypothesis: 软件包与 bundle 依赖校验契约已具备真实模型资格；下一步仍是 Task 10 的真实 immutable bundle 与双平台离线 smoke
qualification_commit: 6242fe967c0574e9175965a7e5790aecb9d427f5
guide_fix_commit: 9450fd77504e4719ca9b6b351cbb4068f81eeb0d
prior_ledger_commit: c777f58fc29c6b1e0f7493f3d98032499b4b8052
repository_head_at_qualification: 6242fe967c0574e9175965a7e5790aecb9d427f5
ledger_commit: 本 checkpoint 由包含该记录的限定文档提交承载；其提交后 SHA 记录在 Task 9 report
working_tree_status: 资格提交后源码 clean；本 checkpoint 只修改实验账本，指南未改
owned_processes: NONE；最终 pgrep 仅命中正在执行检查的 shell 本身
preserved_processes: NONE；canonical /data/work/ws_moveit 用户未跟踪文档未触碰
confirmed_conclusions:
  - verifier API 不再允许调用方覆盖依赖预期，且相关 RED/GREEN JUnit 已保留
  - Mac 定向 230/230、整包 1045/1045
  - Linux exact checkout 定向 230/230、标准 colcon 整包 1045/1045
  - 完整复跑命令保留在带 SHA 的 command log；Linux mirror 位于同一主机 evidence root
open_risks:
  - 真实模型 bundle 尚未下载或构建，真实 MPS/CUDA smoke 未运行
  - 四场景、mask truth IoU、延迟和两个平台连续 5/5 pick-place 均未执行
retained_runs:
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901
  - ai-station:/data/work/so101-v5-t005-grounded-sam-package-a0b6459
  - ai-station:/data/work/so101-v5-t005-grounded-sam-package-b2fb7b7
  - ai-station:/data/work/so101-v5-t005-grounded-sam-package-6242fe9
  - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869
archived_runs: []
deletion_candidates:
  - ai-station:/data/work/so101-v5-t005-grounded-sam-package-a0e0eac
  - ai-station:/data/work/so101-v5-t005-grounded-sam-package-a0e0eac-v2
  - ai-station:/tmp/v5-t005-a0e0eac.bundle
  - ai-station:/tmp/v5-t005-a0b6459.bundle
  - ai-station:/tmp/v5-t005-b2fb7b7.bundle
  - ai-station:/tmp/v5-t005-6242fe9.bundle
  - ai-station:/tmp/mujoco_ros2_control-71bc934.bundle
  - mac:/tmp/v5-t005-b2fb7b7.bundle
  - mac:/tmp/v5-t005-6242fe9.bundle
next_command: Task 10 获得依赖安装授权后，按 requirements.lock 建隔离环境并构建真实 immutable bundle；随后在 Mac MPS 与 Linux CUDA 运行 offline smoke
decision: TASK_9_FIX_ROUND_2_COMPLETE_REAL_MODEL_PENDING
```

```yaml
experiment_id: EXP-006
status: VALID
prior_experiment: EXP-005
hypothesis: 锁定依赖可以在 ai-station CUDA 任务 venv 与 Mac ROS Python 中保持精确版本和 ROS provenance，并由 exact d870113 隔离 checkout 构建一份可由两平台共同验证的不可变 Grounded SAM 模型包
prediction: 两端依赖与 requirements.lock 完全一致，Linux torch.cuda.is_available() 为 True、Mac torch.backends.mps.is_available() 为 True；Linux builder 下载两个固定 revision 后生成无 symlink、无额外文件且逐文件 SHA/size 全部通过的 bundle，Mac 复制件与 Linux manifest SHA 完全相同
single_variable: 从仅软件契约资格进入获授权的锁定依赖安装和两个 exact revision 模型包构建；模型、配置、prompt、阈值与生产源码保持不变
lifecycle: ISOLATED_STACK
preconditions:
  - canonical /data/work/ws_moveit 保持 main@e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4，保留用户未跟踪文档且全程只读
  - source commit 固定为 d870113ff0db11dd30461ab5450e79b131b73aa6，Linux 使用新隔离 checkout /data/work/so101-v5-t005-grounded-sam-task10-d870113-v2
  - /data/work/so101-v5-t005-grounded-sam-task10-d870113-v2、/data/work/venvs/so101-grounded-sam、/data/work/so101-models/grounded-sam-v1 与 /Users/matianyi/Models/so101/grounded-sam-v1 在启动前均不存在
  - 用户已明确授权锁定 Python 依赖安装、两个 exact revision 下载、Linux bundle 创建和同 bundle 复制到 Mac，但未授权覆盖、删除、修改 canonical checkout 或真实机械臂
success_criteria:
  - Linux entrypoint shebang 指向 /data/work/venvs/so101-grounded-sam/bin/python，Mac entrypoint 继续指向 /Users/matianyi/ros2_jazzy/.venv/bin/python
  - 两端 rclpy 路径保持 ROS Jazzy provenance，requirements.lock 十个版本精确一致，Linux CUDA 与 Mac MPS 分别可用且 CPU fallback 不参与
  - bundle manifest 记录两个固定 model ID/revision、固定依赖和全部普通文件的相对路径、字节数、SHA-256
  - verifier 通过，bundle 内没有 symlink、未登记文件或 path escape；archive SHA 与 Mac transfer SHA 一致
  - Linux 与 Mac manifest.json SHA-256 完全相同，Mac 相对路径/字节数/SHA 清单与 Linux read-back 完全相同
failure_criteria:
  - 锁定依赖无法安装、rclpy provenance 漂移、CUDA/MPS 不可用、固定 revision 无法由 pinned loader 加载，或任一 bundle/transfer 校验失败
invalid_criteria:
  - 任一已存在目标被覆盖、canonical checkout 状态变化、使用非 d870113 源构建、使用第二次 Mac Hub 下载替代同包复制，或证据路径越出登记根
provenance:
  source_commit: d870113ff0db11dd30461ab5450e79b131b73aa6
  linux_checkout: /data/work/so101-v5-t005-grounded-sam-task10-d870113-v2
  linux_install_overlay: /data/work/so101-v5-t005-grounded-sam-task10-d870113-v2/install-task10
  linux_python: /data/work/venvs/so101-grounded-sam/bin/python
  mac_install_overlay: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install
  mac_dependency_underlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  mac_python: /Users/matianyi/ros2_jazzy/.venv/bin/python3
  runtime_executable: ros2 run so101_demo_py prepare_grounded_sam_bundle
  ros_domain_id: UNSET_BUNDLE_BUILD_NO_ROS_GRAPH
  gz_partition: UNSET_BUNDLE_BUILD_NO_GAZEBO
commands:
  - command: GIT_LFS_SKIP_SMUDGE=1 git clone --no-checkout /tmp/v5-t005-d870113-task10.bundle /data/work/so101-v5-t005-grounded-sam-task10-d870113-v2; cd /data/work/so101-v5-t005-grounded-sam-task10-d870113-v2; GIT_LFS_SKIP_SMUDGE=1 git checkout --detach d870113ff0db11dd30461ab5450e79b131b73aa6
    exit_code: 0
  - command: /usr/bin/python3 -m venv /data/work/venvs/so101-grounded-sam; /home/lenovo/.local/bin/uv pip install --python /data/work/venvs/so101-grounded-sam/bin/python --default-index https://pypi.tuna.tsinghua.edu.cn/simple -r /data/work/so101-v5-t005-grounded-sam-task10-d870113-v2/src/so101_demo_py/config/perception/requirements.lock
    exit_code: 0
  - command: /data/work/venvs/so101-grounded-sam/bin/python /usr/bin/colcon --log-base log-task10 build --packages-select so101_mujoco_support so101_demo_py --packages-ignore mujoco_3d_lidar mujoco_ros2_control_msgs mujoco_vendor so101_teleop mujoco_ros2_control_plugins mujoco_ros2_control --allow-overriding so101_mujoco_support so101_demo_py --symlink-install --build-base build-task10 --install-base install-task10 --event-handlers console_direct+
    exit_code: 0
  - command: /Users/matianyi/.local/bin/uv pip install --python /Users/matianyi/ros2_jazzy/.venv/bin/python3 --default-index https://pypi.tuna.tsinghua.edu.cn/simple -r /Users/matianyi/.codex/worktrees/5b15/moveit-demo/src/so101_demo_py/config/perception/requirements.lock
    exit_code: 0
  - command: ros2 run so101_demo_py prepare_grounded_sam_bundle --config /data/work/so101-v5-t005-grounded-sam-task10-d870113-v2/src/so101_demo_py/config/perception/grounded_sam.yaml --output /data/work/so101-models/grounded-sam-v1
    exit_code: 0
  - command: tar -C /data/work/so101-models -czf /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/model-bundle/grounded-sam-v1.tar.gz grounded-sam-v1
    exit_code: 0
  - command: scp Linux archive/inventory to /tmp/so101-debug-v5-t005-grounded-sam-20260901/model-transfer; verify tar SHA, safe member types, manifest, 21 relative paths/sizes/SHA; install with _rename_exclusive to /Users/matianyi/Models/so101/grounded-sam-v1
    exit_code: 0
correction:
  - time: 2026-09-01T18:10:28+08:00
    reason: 初次 precondition checkout /data/work/so101-v5-t005-grounded-sam-task10-d870113 的 bundle clone 没有 remote HEAD，随后 detached checkout 未继承 GIT_LFS_SKIP_SMUDGE=1 而失败；该路径保持原状，不删除、不覆盖、不用于 runtime
    replacement: 使用仍不存在的新路径 /data/work/so101-v5-t005-grounded-sam-task10-d870113-v2，以 git clone --no-checkout 后显式 GIT_LFS_SKIP_SMUDGE=1 checkout exact SHA；模型、依赖、commit 与验收变量不变
observed:
  - OBSERVED 首次 checkout setup 失败目录已保留；canonical /data/work/ws_moveit 复核仍为原 HEAD 和原用户未跟踪文档
  - OBSERVED replacement checkout HEAD 为 d870113ff0db11dd30461ab5450e79b131b73aa6，git status 为空；EXP-006 已在依赖安装前进入 RUNNING
  - OBSERVED Linux 十个 requirements.lock pin 全部精确一致；torch 2.13.0+cu130、torch.cuda.is_available()=True、torch.version.cuda=13.0、设备为 NVIDIA GeForce RTX 5080，rclpy 来自 /opt/ros/jazzy/lib/python3.12/site-packages
  - OBSERVED Linux exact runtime package prefix 为 /data/work/so101-v5-t005-grounded-sam-task10-d870113-v2/install-task10/so101_demo_py，prepare_grounded_sam_bundle 与 rgbd_object_pose shebang 均为 /data/work/venvs/so101-grounded-sam/bin/python
  - OBSERVED Mac 十个 pin 全部精确一致，PyYAML 从 6.0.3 收敛为 6.0.2；rclpy 仍来自 /opt/ros/jazzy/rclpy，两个 entrypoint shebang 仍为 /Users/matianyi/ros2_jazzy/.venv/bin/python；MPS available=True 且实际 tensor device 为 mps:0
  - OBSERVED ai-station Hugging Face 直连 TCP 443 超时；一次性 SSH reverse tunnel 到 Mac 现有 Xray 后 Hub 可达，未修改持久路由。Xet 与两个并发 HTTP attempt 均因连接中断失败，失败日志和一个未完成 staging 保留
  - OBSERVED 四个 LFS 权重最终以 exact official resolve URL 做有界 Range resume，并在进入官方 builder 前逐个达到 Hub files_metadata size 与 LFS SHA；model IDs/revisions 未改变
  - OBSERVED 官方 builder 最终成功，manifest SHA 为 838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3；独立 offline verifier 通过，manifest 登记 20 个模型文件，bundle 连同 manifest 共 21 个普通文件、无 symlink
  - OBSERVED grounded-sam-v1.tar.gz 为 1568494067 bytes，SHA256=014787b1b643a6f46dda3680ab5d29fd49a9f7c31c1a0a14f9085580deb8699c；Mac tar member 安全检查为 24 members、0 bad
  - OBSERVED Mac 解包件与 Linux 的 21 条相对路径、字节数和 SHA 清单在 LC_ALL=C 规范化后逐项一致；atomic no-clobber 安装后 verifier 再次通过，同一 manifest SHA 保持不变
inferred:
  - INFERRED 同一不可变 bundle 已具备 Linux CUDA 与 Mac MPS 离线 actual-model smoke 的 provenance 前置条件；EXP-006 不证明推理、mask、Depth、TF 或 /cup_pose
conclusion: 双平台锁定依赖、设备 provenance、Linux immutable bundle 构建及同包 Mac 复制全部通过；真实模型推理仍由 EXP-007/EXP-008 验证
evidence:
  - ai-station:/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/dependency-install/linux/provenance.json sha256=a83f99478258f8ee586512a5506ba62223ac7516dc0c19015c213fba92163441
  - ai-station:/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/dependency-install/linux/runtime-provenance.json sha256=14254f1e2eb6c7871dd529cf9414c5084720a2b4fd4fd0650de2801fc835d29c
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/dependency-install/macos/provenance.json sha256=7d9e29bd2cc3a73c476282b4ee9d1cd4eefc6da2ac1b3519fcb7197437432d45
  - ai-station:/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/model-bundle/verifier.json sha256=dac7b073c3c4d4c34874941a405575082cbed866f56ae2e076b1884f85cd0f0c
  - ai-station:/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/model-bundle/grounded-sam-v1.tar.gz sha256=014787b1b643a6f46dda3680ab5d29fd49a9f7c31c1a0a14f9085580deb8699c
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/model-transfer/mac-final-verifier.json sha256=763a927f40eb51a22ebee165e1af9dbae97814194eeb73a0eebdedb2fc9ee9c7
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/model-transfer/mac-bundle-files.sha256.sorted sha256=1c9a07fbd071d2cd1c01465226c3be1992f826dc12d1fe8381bbef44cbe04f2f
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/model-transfer/mac-bundle-files.size.sorted sha256=cffc3b9da6c6f67a86c67d26eb0ea06fd4efa3e84a08496af1df889b4a6738a3
decision: KEEP
next_experiment: EXP-007
```

```yaml
experiment_id: EXP-007
status: VALID
prior_experiment: EXP-006
hypothesis: ai-station 能在强制离线、显式 CUDA 且禁止 CPU fallback 的条件下，从 EXP-006 的真实 bundle 对 one-cup 多物体 RGB-D 帧生成唯一 plastic_cup、非空原尺寸 mask 和源时间戳 /cup_pose
prediction: actual Grounding DINO Tiny 与 SAM 2.1 Hiera Tiny 联合 warm-up 成功，runtime device 为 cuda；candidate_count 唯一、mask 非空且为 full resolution，/cup_pose stamp 与 RGB-D 源 stamp 相同，证据展开记录 model revisions、manifest/file SHA、latency 和 cleanup
single_variable: 平台固定为 ai-station CUDA；commit、bundle、prompt、阈值和 one-cup 场景固定
lifecycle: FULL_RESTART
preconditions:
  - EXP-006 为 VALID，Linux bundle verifier 与 CUDA provenance 已通过
  - ROS_DOMAIN_ID=141，GZ_PARTITION=v5-t005-grounded-sam-linux-smoke-001，没有重复同域 stack
  - HF_HUB_OFFLINE=1、TRANSFORMERS_OFFLINE=1、perception_device=cuda、perception_allow_cpu_fallback=false
success_criteria:
  - actual model 完成联合 warm-up 和一次请求，证据 device 为 cuda 且没有 Hub 请求
  - 唯一 plastic_cup 候选具有非空 full-resolution mask，TargetSelector 不按分数消歧
  - 对齐 Depth/CameraInfo 和精确 tf2 成功，发布本轮源时间戳 /cup_pose；evidence 写入成功
  - 记录 cold/warm latency、candidate/mask/device/revisions/provenance，退出后 owned processes 为 NONE
failure_criteria:
  - DEVICE_UNAVAILABLE、MODEL_LOAD_FAILED、WARMUP_FAILED、INFERENCE_FAILED、TARGET_NOT_FOUND、TARGET_AMBIGUOUS、DEPTH_INVALID、TF_UNAVAILABLE、EVIDENCE_WRITE_FAILED 或 CLEANUP_FAILED
invalid_criteria:
  - 旧 topic、重复 node、错误 overlay/commit/bundle、非真实 payload、缺失源 stamp 或 evidence 污染
provenance:
  source_commit: d870113ff0db11dd30461ab5450e79b131b73aa6
  install_overlay: /data/work/so101-v5-t005-grounded-sam-task10-d870113-v2/install-task10
  runtime_executable: /data/work/so101-v5-t005-grounded-sam-task10-d870113-v2/install-task10/so101_demo_py
  python: /data/work/venvs/so101-grounded-sam/bin/python
  ros_domain_id: 141
  gz_partition: v5-t005-grounded-sam-linux-smoke-001
commands:
  - command: HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ROS_DOMAIN_ID=141 GZ_PARTITION=v5-t005-grounded-sam-linux-smoke-001 timeout --signal=TERM --kill-after=20s 600s ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py run_mode:=execute execute:=true headless:=true sensor_rendering:=true session_id:=linux-grounded-sam-smoke-001 evidence_file:=/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/model-smoke/linux/linux-grounded-sam-smoke-001.json mujoco_scene:=/data/work/so101-v5-t005-grounded-sam-task10-d870113-v2/install-task10/so101_demo_py/share/so101_demo_py/assets/mujoco/v5_multi_object_scene.xml mujoco_initial_keyframe:=task_start perception_startup_timeout_s:=120.0 cup_pose_timeout_s:=45.0 perception_backend:=grounded_sam perception_model_root:=/data/work/so101-models/grounded-sam-v1 perception_model_manifest_sha256:=838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3 perception_device:=cuda perception_allow_cpu_fallback:=false
    exit_code: 1
observed:
  - OBSERVED 启动前 ROS_DOMAIN_ID=141 node list 为空，相关 process probe 只命中检查 shell；package prefix、manifest SHA 与 launch 参数 provenance 通过，EXP-007 在 launch 前进入 RUNNING
  - OBSERVED 强制 offline 下 actual Grounding DINO + SAM2 加载和 CUDA warm-up 成功，READY runtime_device=cuda，cold_start_latency_ms=9303.099296；无 CPU fallback
  - OBSERVED 首张真实 MuJoCo RGB-D 帧进入 detector 后返回 INFERENCE_FAILED，request_latency_ms=125.741059，candidate_count=0，source_frame_id=task_camera_frame，source_stamp_ns=13040000000
  - OBSERVED 本轮没有发布 /cup_pose，launch exit=1；失败 result 与 model provenance 已写入登记 durable root，未被后续试验覆盖
  - OBSERVED launch 已终止 owned child process；立即的 ROS graph probe 仍见 /move_group* discovery 缓存，而 pgrep 未发现对应存活进程，后续需在新 domain 中独立重试
inferred:
  - INFERRED bundle、offline 门禁、CUDA 选择与联合 warm-up 未失败；故障已缩小到真实尺寸帧的 detector inference/postprocess 边界，仍需从 chained exception 取回根因
conclusion: 本次 smoke 有效地证明 actual model 离线加载与 CUDA warm-up，但真实首帧 INFERENCE_FAILED，未达成候选、mask、Depth/TF 或 /cup_pose 成功准则
evidence:
  - ai-station:/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/model-smoke/linux/launch.log
  - ai-station:/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/model-smoke/linux/linux-grounded-sam-smoke-001.d/linux-grounded-sam-smoke-001/perception/result.json
  - ai-station:/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/model-smoke/linux/linux-grounded-sam-smoke-001.d/linux-grounded-sam-smoke-001/perception/model-provenance.json
decision: KEEP
next_experiment: EXP-009
```

```yaml
experiment_id: EXP-008
status: VALID
prior_experiment: EXP-010
hypothesis: Mac 能在强制离线、显式 MPS 且禁止 CPU fallback 的条件下，使用与 Linux 相同 manifest SHA 对同一 one-cup 多物体 RGB-D 场景生成相同语义结果和新鲜 /cup_pose
prediction: actual Grounding DINO Tiny 与 SAM 2.1 Hiera Tiny 联合 warm-up 成功，runtime device 为 mps；候选唯一、mask 非空且为 full resolution，/cup_pose stamp 与 RGB-D 源 stamp 相同，结果复制到 durable evidence 后远端 read-back 完整
single_variable: 平台从 Linux CUDA 切换为 Mac MPS；commit、bundle SHA、prompt、阈值和场景保持固定
lifecycle: FULL_RESTART
preconditions:
  - EXP-006、EXP-009 与 EXP-010 为 VALID；Mac bundle verifier、MPS provenance、f55074e 两端包级回归及 Linux actual-model smoke 已通过
  - ROS_DOMAIN_ID=142，GZ_PARTITION=v5-t005-grounded-sam-mac-smoke-fix-001，没有重复同域 stack
  - HF_HUB_OFFLINE=1、TRANSFORMERS_OFFLINE=1、perception_device=mps、perception_allow_cpu_fallback=false
success_criteria:
  - actual model 完成联合 warm-up 和一次请求，证据 device 为 mps 且没有 Hub 请求
  - 唯一 plastic_cup 候选具有非空 full-resolution mask，发布本轮源时间戳 /cup_pose
  - 与 Linux 使用同一 manifest SHA、model revisions、prompt 和阈值；本地 evidence 逐文件核验后复制到 durable root 并远端 read-back
  - 记录 cold/warm latency、candidate/mask/device/revisions/provenance，退出后 owned processes 为 NONE
failure_criteria:
  - DEVICE_UNAVAILABLE、MODEL_LOAD_FAILED、WARMUP_FAILED、INFERENCE_FAILED、TARGET_NOT_FOUND、TARGET_AMBIGUOUS、DEPTH_INVALID、TF_UNAVAILABLE、EVIDENCE_WRITE_FAILED 或 CLEANUP_FAILED
invalid_criteria:
  - 旧 topic、重复 node、错误 overlay/commit/bundle、非真实 payload、缺失源 stamp、使用在线 Hub 或 evidence 污染
provenance:
  source_commit: f55074e5d9806304955df1a0d2beadbd8e4a1ecc
  install_overlay: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install
  dependency_underlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  runtime_executable: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install/so101_demo_py
  python: /Users/matianyi/ros2_jazzy/.venv/bin/python3
  ros_domain_id: 149
  gz_partition: v5-t005-grounded-sam-mac-smoke-fix-004
commands:
  - command: HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ROS_DOMAIN_ID=142 GZ_PARTITION=v5-t005-grounded-sam-mac-smoke-fix-001 gtimeout --signal=TERM --kill-after=20s 600s ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py run_mode:=execute execute:=true headless:=false sensor_rendering:=true session_id:=mac-grounded-sam-smoke-fix-001 evidence_file:=/tmp/so101-debug-v5-t005-grounded-sam-20260901/model-smoke/retry-f55074e/mac-grounded-sam-smoke-fix-001.json mujoco_scene:=/Users/matianyi/.codex/worktrees/5b15/moveit-demo/install/so101_demo_py/share/so101_demo_py/assets/mujoco/v5_multi_object_scene.xml mujoco_initial_keyframe:=task_start perception_startup_timeout_s:=120.0 cup_pose_timeout_s:=45.0 perception_backend:=grounded_sam perception_model_root:=/Users/matianyi/Models/so101/grounded-sam-v1 perception_model_manifest_sha256:=838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3 perception_device:=mps perception_allow_cpu_fallback:=false
    exit_code: 1
  - command: DYLD_LIBRARY_PATH=/Users/matianyi/ros2_jazzy/macos_dylib_farm/current HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ROS_DOMAIN_ID=147 GZ_PARTITION=v5-t005-grounded-sam-mac-smoke-fix-002 gtimeout --signal=TERM --kill-after=20s 600s ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py run_mode:=execute execute:=true headless:=false sensor_rendering:=true session_id:=mac-grounded-sam-smoke-fix-002 evidence_file:=/tmp/so101-debug-v5-t005-grounded-sam-20260901/model-smoke/retry-f55074e-dylib/mac-grounded-sam-smoke-fix-002.json mujoco_scene:=/Users/matianyi/.codex/worktrees/5b15/moveit-demo/install/so101_demo_py/share/so101_demo_py/assets/mujoco/v5_multi_object_scene.xml mujoco_initial_keyframe:=task_start perception_startup_timeout_s:=120.0 cup_pose_timeout_s:=45.0 perception_backend:=grounded_sam perception_model_root:=/Users/matianyi/Models/so101/grounded-sam-v1 perception_model_manifest_sha256:=838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3 perception_device:=mps perception_allow_cpu_fallback:=false
    exit_code: 1
  - command: DYLD_LIBRARY_PATH=/Users/matianyi/Projects/robot_demo_001/moveit-demo/install/mujoco_ros2_control/lib:/Users/matianyi/ros2_jazzy/macos_dylib_farm/current HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ROS_DOMAIN_ID=148 GZ_PARTITION=v5-t005-grounded-sam-mac-smoke-fix-003 gtimeout --signal=TERM --kill-after=20s 600s ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py run_mode:=execute execute:=true headless:=false sensor_rendering:=true session_id:=mac-grounded-sam-smoke-fix-003 evidence_file:=/tmp/so101-debug-v5-t005-grounded-sam-20260901/model-smoke/retry-f55074e-dispatcher/mac-grounded-sam-smoke-fix-003.json mujoco_scene:=/Users/matianyi/.codex/worktrees/5b15/moveit-demo/install/so101_demo_py/share/so101_demo_py/assets/mujoco/v5_multi_object_scene.xml mujoco_initial_keyframe:=task_start perception_startup_timeout_s:=120.0 cup_pose_timeout_s:=45.0 perception_backend:=grounded_sam perception_model_root:=/Users/matianyi/Models/so101/grounded-sam-v1 perception_model_manifest_sha256:=838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3 perception_device:=mps perception_allow_cpu_fallback:=false
    exit_code: 130
  - command: DYLD_LIBRARY_PATH=/Users/matianyi/Projects/robot_demo_001/moveit-demo/install/mujoco_ros2_control/lib:/Users/matianyi/Projects/robot_demo_001/moveit-demo/install/mujoco_ros2_control_msgs/lib:/Users/matianyi/Projects/robot_demo_001/moveit-demo/install/mujoco_ros2_control_plugins/lib:/Users/matianyi/ros2_jazzy/macos_dylib_farm/current HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ROS_DOMAIN_ID=149 GZ_PARTITION=v5-t005-grounded-sam-mac-smoke-fix-004 gtimeout --signal=TERM --kill-after=20s 600s ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py run_mode:=execute execute:=true headless:=false sensor_rendering:=true session_id:=mac-grounded-sam-smoke-fix-004 evidence_file:=/tmp/so101-debug-v5-t005-grounded-sam-20260901/model-smoke/retry-f55074e-runtime-set/mac-grounded-sam-smoke-fix-004.json mujoco_scene:=/Users/matianyi/.codex/worktrees/5b15/moveit-demo/install/so101_demo_py/share/so101_demo_py/assets/mujoco/v5_multi_object_scene.xml mujoco_initial_keyframe:=task_start perception_startup_timeout_s:=120.0 cup_pose_timeout_s:=45.0 perception_backend:=grounded_sam perception_model_root:=/Users/matianyi/Models/so101/grounded-sam-v1 perception_model_manifest_sha256:=838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3 perception_device:=mps perception_allow_cpu_fallback:=false
    exit_code: 1
observed:
  - OBSERVED 本轮在执行前已转为 RUNNING；命令固定 f55074e、同一 manifest SHA、同一 prompt/config/thresholds，Mac 仅将 device 切换为 mps 并要求 headless=false
  - OBSERVED 批次 001 的 Grounding DINO + SAM2 在强制 offline 下完成 MPS warm-up 并 READY，但 base project 的 libmujoco_ros2_control.dylib 因缺少既有 dylib farm 环境而无法解析 @rpath/libmujoco.3.4.0.dylib；无 RGB-D 帧，最终 CUP_POSE_TIMEOUT，launch exit=1
  - OBSERVED 按项目现有 macOS 部署指南加入 /Users/matianyi/ros2_jazzy/macos_dylib_farm/current 后，source/install/package prefix 不变，ctypes 对同一 libmujoco_ros2_control.dylib 的 dlopen probe 通过
  - OBSERVED 批次 002 解析了 MuJoCo 3.4.0，但仍两次 Timed out waiting to start simulation rendering；otool/hash 证明 symlink-install 的 ros2_control_node 从 build rpath 加载 dispatcher SHA 3338a148…，而 install plugin 的 @loader_path 加载另一个 dispatcher SHA 1e588890…，两个进程内 singleton 状态不共享，主线程因而看不到 plugin 提交的 UI task
  - OBSERVED 批次 003 的 node 已统一加载 install dispatcher，但 farm 中 stale sibling overlay 的 mujoco_ros2_control_msgs typesupport 缺 SetFreeJointState 符号；确认根因后主动 SIGINT，exit=130，cleanup 后 owned process NONE
  - OBSERVED parent install 的 core/messages/plugins 三组 lib 置于 farm 之前后，RTLD_NOW 对 exact libmujoco_ros2_control.dylib 成功；parent messages typesupport SHA ff26d5f6… 与 stale sibling SHA 71f4fcb1… 明确不同
  - OBSERVED 批次 004 的可见 MuJoCo、控制器与 RGB-D 启动成功；actual offline MPS detector 返回 3 个 full-resolution 非空 mask，DINO confidence 为 0.7196819、0.4888311、0.3704001，SAM quality 为 0.9404030、0.9535543、0.9366040
  - OBSERVED 固定 selector confidence_threshold=0.50 后仅 1 个 eligible plastic_cup；selected mask 为 640x480、4651 pixels，Depth/TF center_world_xyz=[0.02009680,-0.28045558,0.165]
  - OBSERVED runtime_device=mps，inference_latency_ms=3851.778834，cold_start_latency_ms=10060.106833，source_stamp_ns=59804000000，/cup_pose 使用该源时间戳发布；overlay 人工查看确认 selected mask 覆盖左侧杯
  - OBSERVED dynamic consumer 按 maximum_source_age_s=2.0 拒绝已超过 freshness gate 的 pose，CUP_POSE_STALE 后 launch exit=1；没有放宽 freshness、CPU fallback、truth/color 或最高分强选
  - OBSERVED cleanup 后 ROS_DOMAIN_ID=149 node list 与 owned process 清单均为空；本地 33 regular files/1 symlink read-back 的逐文件 SHA 通过
  - OBSERVED sanitized archive SHA b78d749f2fc35d2b2b5626c134a4feaf32e799022ed6629f96fa4168e49c905c；durable read-back inventory SHA c5abefd834239e0ffe7314f4b7108b71f596e967deacb4ae5730d9f06c9e8784
inferred:
  - INFERRED Mac actual-model perception smoke 达成唯一 eligible cup、full-resolution mask、Depth/TF、源时间戳 /cup_pose 与 offline/MPS provenance，但 3.85 s warmed latency 不满足现有 2.0 s 下游 freshness safety contract
conclusion: VALID failure — MODEL_CAPABILITY_NOT_MET；Mac 感知 payload 成功但执行链按设计 fail-closed，不能进入 Task 11 四场景/5-of-5
evidence:
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/model-smoke/retry-f55074e/
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/model-smoke/retry-f55074e-dylib/
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/model-smoke/retry-f55074e-dispatcher/
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/model-smoke/retry-f55074e-runtime-set/
  - ai-station:/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/model-smoke/macos/
decision: KEEP
next_experiment: 新实验评估不放宽 freshness gate 的 Mac 推理延迟改进；未获成功前暂停 Task 11
correction:
  - time: 2026-09-01T20:20:00+08:00
    reason: 原计划 source_commit=d870113 在 EXP-007 actual CUDA 首帧暴露 device tensor 转 NumPy 的源码缺陷；EXP-009 已按 TDD 最小修复并以独立提交 f55074e 通过两端包级回归，EXP-010 actual Linux full stack 通过
    replacement: Mac smoke 使用 exact f55074e 重建 overlay；bundle、model revisions、prompt、thresholds、scene、offline 门禁和禁止 CPU fallback 均保持不变
  - time: 2026-09-01T20:33:00+08:00
    reason: 批次 001 启动 shell 未导出项目既有 macOS dylib farm，导致已安装控制插件无法解析其构建时 MuJoCo 3.4.0 runtime；模型已 READY，但仿真未产生 RGB-D payload
    replacement: 保留批次 001；在新 ROS_DOMAIN_ID=147、新 GZ_PARTITION/session/evidence 路径中仅补回部署指南要求的 DYLD_LIBRARY_PATH=/Users/matianyi/ros2_jazzy/macos_dylib_farm/current，不更换 package prefix、锁版本、模型 revision、bundle、scene、prompt 或阈值
  - time: 2026-09-01T20:42:00+08:00
    reason: 批次 002 证明单独加入 farm 仍让 symlink-install node 与 install plugin 分别加载不同 SHA 的 macOS UI dispatcher，UI task 的进程内 singleton 被拆成两份
    replacement: 保留批次 002；在新 ROS_DOMAIN_ID=148、新 GZ_PARTITION/session/evidence 路径中把同一 install/mujoco_ros2_control/lib 放在 farm 前，使 node 和 plugin 解析到同一个已安装 dispatcher；source/install/package prefix 以及模型与感知变量均不变
  - time: 2026-09-01T20:48:00+08:00
    reason: 批次 003 只前置 core lib，farm 仍为 messages typesupport 选择 stale sibling overlay，缺少当前 parent install 已提供的 SetFreeJointState symbol
    replacement: 保留并主动清理批次 003；在新 ROS_DOMAIN_ID=149、新 GZ_PARTITION/session/evidence 路径中把同一 parent install 的 core、msgs、plugins 三组 lib 一起置于 farm 前；RTLD_NOW 预检必须先通过，其他变量不变
```

```yaml
experiment_id: EXP-009
status: VALID
prior_experiment: EXP-007
hypothesis: EXP-007 的 INFERENCE_FAILED 可以在同一 exact checkout、bundle、CUDA 和 offline 环境中由直接 detector 调用稳定复现，并用完整 chained traceback 定位到单一输入或 postprocess 契约差异
prediction: 直接调用会保留 GroundedSamResultError.__cause__ 的完整类型、消息和栈，且失败层与 EXP-007 首帧一致；若确认为本任务源码缺陷，才进入 TDD 最小修复和新 smoke
single_variable: 用直接 detector 可观测调用取代 ROS application 对异常细节的 fail-closed 折叠；model revisions、bundle SHA、pins、prompt、thresholds、offline 和 CUDA 不变
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-007 已 VALID 结算并保留失败批次；EXP-008 仍为 PLANNED，Mac smoke 未启动
  - 使用 /data/work/so101-v5-t005-grounded-sam-task10-d870113-v2/install-task10 和 /data/work/venvs/so101-grounded-sam/bin/python
  - HF_HUB_OFFLINE=1、TRANSFORMERS_OFFLINE=1、requested_device=cuda、allow_cpu_fallback=false；调试输出只写入同一 registered durable root
success_criteria:
  - 完整 traceback 稳定复现且指出失败边界、实际数据 shape/type 和 pinned API 期望形状
  - 形成单一根因假设，不通过更换 pin/revision、放宽 CPU fallback、改阈值或强选候选规避
  - 若为源码缺陷，先产生最小 RED 回归测试，再修复并在两端重建/复验 source-install-runtime provenance
failure_criteria:
  - 不能稳定复现、traceback 仍丢失根因、发现模型能力不足或需要改变未授权边界
invalid_criteria:
  - 覆盖 EXP-007 证据、联网加载、修改 canonical checkout、更换 model revision/pin，或未经 RED 测试直接修码
provenance:
  source_commit: d870113ff0db11dd30461ab5450e79b131b73aa6
  install_overlay: /data/work/so101-v5-t005-grounded-sam-task10-d870113-v2/install-task10
  python: /data/work/venvs/so101-grounded-sam/bin/python
  bundle_manifest_sha256: 838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3
commands:
  - command: scp capture_frame.zsh and direct_detector_traceback.py to ai-station registered durable debug-exp-009; timeout 300s zsh capture_frame.zsh
    exit_code: 127
  - command: scp capture_frame_v2.zsh and direct_detector_traceback_v2.py to ai-station registered durable debug-exp-009; timeout 300s zsh capture_frame_v2.zsh
    exit_code: 1
  - command: scp capture_rgb_only_v3.py, capture_frame_v3.zsh and direct_detector_traceback_v3.py to ai-station registered durable debug-exp-009; timeout 300s zsh capture_frame_v3.zsh
    exit_code: 0
  - command: HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 timeout --signal=TERM --kill-after=20s 180s /data/work/venvs/so101-grounded-sam/bin/python direct_detector_traceback.py
    exit_code: 1 before fix; 0 at fix commit f55074e5d9806304955df1a0d2beadbd8e4a1ecc
  - command: Mac RED/GREEN directed tests, Mac rebuild/full package gate; exact f55074e bundle checkout/build on ai-station; Linux directed/full package gate
    exit_code: valid RED=1; GREEN=0; Mac full=0; Linux build=0; Linux directed=0; Linux full=0
observed:
  - OBSERVED EXP-007 已 VALID 结算；调试脚本已在 Mac debug root 以 apply_patch 创建，待复制到 registered durable root，运行前未修改生产源码
  - OBSERVED 诊断批次 001 在进入 ROS 前失败；zsh nounset 在 source overlay 时命中 AMENT_TRACE_SETUP_FILES/COLCON_TRACE 未定义，capture_exit=127、launch_exit=127，该批次保留且未触发模型调用
  - OBSERVED 诊断批次 002 再次在 actual CUDA 首帧稳定触发 INFERENCE_FAILED，但 rgbd_sensor_capture 在保存 RGB 前因锁定环境不含 Open3D 而 exit=1；未安装额外依赖
  - OBSERVED 诊断批次 003 用锁定 rclpy/NumPy/Pillow 从 /task_camera/color 无损保存 640x480 rgb8 真实帧，launch 再次 INFERENCE_FAILED 而 RGB capture exit=0
  - OBSERVED direct actual detector traceback 稳定定位到 convert_grounding_results 将 CUDA boxes tensor 直接 np.asarray；底层 TypeError 为 can't convert cuda:0 device type tensor to numpy
  - OBSERVED 有效 RED 在旧代码上因 device tensor 直接 NumPy 转换失败；最小修复仅在 adapter 边界对 boxes/scores 使用已有 _to_numpy，GREEN 1 passed，定向 39 passed
  - OBSERVED 修复提交为 f55074e5d9806304955df1a0d2beadbd8e4a1ecc；Mac 重建后 1046 passed，Linux exact f55074e checkout 重建后定向 39 passed、整包 1046 passed/4 warnings
  - OBSERVED 修复后同一真实 RGB 帧的 offline CUDA direct detector exit=0，inference_latency_ms=158.163672，产生 3 个 full-resolution 非空 mask，不再是 INFERENCE_FAILED
correction:
  - time: 2026-09-01T19:45:00+08:00
    reason: 诊断脚本在 source ROS/colcon overlay 前启用 set -u，破坏了 overlay 允许未定义 trace 变量的初始化语义
    replacement: 保留批次 001，以新 v2 脚本先 source overlays、再启用 nounset；改用 ROS_DOMAIN_ID=144、新 session/evidence 路径，不覆盖任何已有文件
  - time: 2026-09-01T19:48:00+08:00
    reason: 现有 rgbd_sensor_capture 会在产出 RGB 前引入 Open3D 点云处理，而 Task 10 锁文件未包含 Open3D；为调试额外安装将扩大变量并破坏 exact pin 边界
    replacement: 保留批次 002，以新 v3 诊断脚本只订阅 /task_camera/color，用已锁定的 rclpy、NumPy 和 Pillow 无损保存首帧；使用 ROS_DOMAIN_ID=145 和新 evidence 名称
inferred:
  - INFERRED 根因是 adapter 丢失 device-to-host 转换，而不是 model revision、bundle、pin、offline 或 CUDA 可用性；f55074e 已修复该契约缺陷
  - INFERRED direct detector 的 3 个候选不证明 full stack 能选出唯一目标；必须由 TargetSelector 的 fail-closed 契约在新 experiment 中决定
conclusion: 根因已用真实帧定位并经 TDD 最小修复，两端包级回归通过；actual CUDA 推理已从 INFERENCE_FAILED 转为 3 个候选，唯一目标和 /cup_pose 尚未通过
evidence:
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-10/fix-device-tensor/red-device-tensor-v3.xml
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-10/fix-device-tensor/green-device-tensor.xml
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-10/fix-device-tensor/mac-full-v3.xml
  - ai-station:/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/model-smoke/linux/debug-exp-009/direct-detector-traceback-v3.log
  - ai-station:/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/model-smoke/linux/debug-exp-009/direct-detector-fixed-f55074e.log
  - ai-station:/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/fix-device-tensor/linux/directed.xml
  - ai-station:/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/fix-device-tensor/linux/full.xml
decision: KEEP
next_experiment: EXP-010
```

```yaml
experiment_id: EXP-010
status: VALID
prior_experiment: EXP-009
hypothesis: f55074e 修复后的 ai-station full stack 会在同一 one-cup 多物体场景中产生可审计候选和 mask，然后仅在候选唯一时进入 Depth/TF 并发布 /cup_pose
prediction: 推理不再 INFERENCE_FAILED；若 actual model 仍返回 3 个 matching plastic_cup，TargetSelector 必须返回 TARGET_AMBIGUOUS 且不发布 /cup_pose，该结果标记 MODEL_CAPABILITY_NOT_MET，不用 truth/color/最高分强选
single_variable: 从 direct detector 进入 f55074e exact full ROS/MuJoCo stack；bundle、model revisions、prompt、thresholds、scene、offline 和 CUDA 不变
lifecycle: FULL_RESTART
preconditions:
  - EXP-009 为 VALID，f55074e 两端包级回归通过，Linux exact runtime 重建成功
  - ROS_DOMAIN_ID=146，GZ_PARTITION=v5-t005-grounded-sam-linux-smoke-fix-001，本域无重复 stack
  - HF_HUB_OFFLINE=1、TRANSFORMERS_OFFLINE=1、perception_device=cuda、perception_allow_cpu_fallback=false
success_criteria:
  - actual detector 产生唯一 plastic_cup、非空 full-resolution mask、成功 Depth/TF 与源时间戳 /cup_pose
  - candidate/mask/device/revisions/manifest/latency/source stamp 证据完整，cleanup 后 owned process 为 NONE
failure_criteria:
  - 任何稳定失败码，特别是 TARGET_AMBIGUOUS，或没有发布新鲜 /cup_pose
invalid_criteria:
  - 修改阈值/revision/pin/scene，使用 truth/color/最高分强选，覆盖旧 evidence，或不是 f55074e exact runtime
provenance:
  source_commit: f55074e5d9806304955df1a0d2beadbd8e4a1ecc
  install_overlay: /data/work/so101-v5-t005-grounded-sam-task10-f55074e/install-task10
  python: /data/work/venvs/so101-grounded-sam/bin/python
  bundle_manifest_sha256: 838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3
  ros_domain_id: 146
  gz_partition: v5-t005-grounded-sam-linux-smoke-fix-001
commands:
  - command: HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ROS_DOMAIN_ID=146 GZ_PARTITION=v5-t005-grounded-sam-linux-smoke-fix-001 timeout --signal=TERM --kill-after=20s 600s ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py run_mode:=execute execute:=true headless:=true sensor_rendering:=true session_id:=linux-grounded-sam-smoke-fix-001 evidence_file:=/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/model-smoke/linux/retry-f55074e/linux-grounded-sam-smoke-fix-001.json mujoco_scene:=/data/work/so101-v5-t005-grounded-sam-task10-f55074e/install-task10/so101_demo_py/share/so101_demo_py/assets/mujoco/v5_multi_object_scene.xml mujoco_initial_keyframe:=task_start perception_startup_timeout_s:=120.0 cup_pose_timeout_s:=45.0 perception_backend:=grounded_sam perception_model_root:=/data/work/so101-models/grounded-sam-v1 perception_model_manifest_sha256:=838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3 perception_device:=cuda perception_allow_cpu_fallback:=false
    exit_code: 0
observed:
  - OBSERVED source/install/runtime 指向 exact f55074e，rgbd_object_pose shebang 为任务 venv；启动前 ROS_DOMAIN_ID=146 无 node，相关 process probe 只命中检查 shell
  - OBSERVED actual offline CUDA detector 返回 3 个 full-resolution 非空 mask，DINO confidence 分别为 0.7201325、0.4777547、0.3535068，SAM quality 分别为 0.9401684、0.9536868、0.9346478
  - OBSERVED TargetSelector 固定 confidence_threshold=0.50；只有 1 个 matching plastic_cup，因此不是按最高分在多个 eligible 候选中强选，选中 mask 为 640x480、4643 pixels
  - OBSERVED perception status=OK，runtime_device=cuda，inference_latency_ms=161.977643，cold_start_latency_ms=3654.74695，source_stamp_ns=7159999999，/cup_pose 使用同一源时间戳发布
  - OBSERVED Depth/CameraInfo/tf2 定位 center_world_xyz=[0.02009484,-0.28046013,0.165]；dynamic workflow 从该 pose 完成 19 个状态迁移并 DONE
  - OBSERVED 物理门记录抓取后双侧接触、杯子离桌 0.0039722m；终态 final_xy_error_m=0.0020481、final_upright_tilt_rad=0.00467438、table_contact=true，本 smoke 的模拟 Pick&Place 成功
  - OBSERVED source-rgb 与 overlay 已取回并实际查看；画面中绿色 selected mask 覆盖左侧橙色杯，两个低于 0.50 的框覆盖其他干扰物
  - OBSERVED launch exit=0，复查 ROS node list 为空，pgrep 无存活 owned process
inferred:
  - INFERRED one-cup smoke 达成唯一 eligible plastic_cup、非空 full-resolution mask、Depth/TF、源时间戳 /cup_pose 和数值/物理 Pick&Place 成功；3 个 raw candidates 中只有 1 个达到固定 selector gate
conclusion: f55074e Linux CUDA actual-model offline smoke 通过；这是 Task 10 单次 smoke，不计入 Task 11 最终连续 5/5
evidence:
  - ai-station:/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/model-smoke/linux/retry-f55074e/
decision: KEEP
next_experiment: EXP-008
```

## Checkpoint CP-005

```yaml
checkpoint_id: CP-005
last_valid_experiment: EXP-008
current_hypothesis: 同一 immutable bundle 已在 CUDA/MPS 离线运行；Linux 全栈通过，Mac 模型语义/实例/mask/Depth/TF 通过但 warmed latency 仍需在不放宽 2.0 s freshness gate 的前提下降低
working_tree_status: source fix 已独立提交为 f55074e；本 checkpoint 仅待提交 ledger、Task 10 report 与 progress
owned_processes: NONE on Mac ROS_DOMAIN_ID=149 and ai-station ROS_DOMAIN_ID=146
preserved_processes: 用户进程与 canonical /data/work/ws_moveit 均未触碰
retained_runs:
  - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901
  - /data/work/so101-models/grounded-sam-v1
  - /Users/matianyi/Models/so101/grounded-sam-v1
  - /data/work/so101-v5-t005-grounded-sam-task10-d870113-v2
  - /data/work/so101-v5-t005-grounded-sam-task10-f55074e
archived_runs: []
deletion_candidates:
  - ai-station:/data/work/so101-v5-t005-grounded-sam-task10-d870113
  - ai-station:/data/work/so101-models/.grounded-sam-v1.staging-8rjn6_lm
  - ai-station:/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/model-smoke/macos/retry-f55074e-runtime-set
  - /tmp/v5-t005-d870113-task10.bundle
  - /tmp/v5-t005-f55074e-task10.bundle
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-10/f55074e.bundle
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-10/mac-grounded-sam-smoke-f55074e-runtime-set.tar.gz
decision: PARTIAL_TASK10_MODEL_CAPABILITY_NOT_MET_ON_MAC
next_command: 设计并预写一个只改变 Mac inference latency 的实验；不得放宽 source-age gate，不得进入 Task 11 正式计数
```

```yaml
experiment_id: EXP-011
status: VALID
prior_experiment: EXP-008
hypothesis: Mac 首个正式 640x480 请求的 3851.778834 ms 包含 8x8 warm-up 未触发的正式形状与多框 batch 图编译成本；在同一 detector 内复用同一真实帧后，第 2至 6 次将稳定降至 2000 ms 内
prediction: 若现有 warm-up 仅缺少正式 shape/batch，第 2至 6 次的 MPS 同步总延迟均低于 2000 ms；若这些 warmed 请求仍超过 2000 ms，则多次数据确认 MODEL_CAPABILITY_NOT_MET
single_variable: 从一个 detector 的首个正式帧扩展为同 detector、同帧连续 6 次 detect；bundle、revision、prompt、thresholds、MPS FP32、CPU fallback false 和 offline 不变
lifecycle: ISOLATED_STACK
preconditions:
  - source behavior 为 exact f55074e，当前 HEAD 4ab5315 仅增加 ledger checkpoint，Mac overlay 已指向该源码
  - 使用同一 bundle manifest 838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3 和先前 smoke 的 source-rgb.png SHA256 3881885fe5bcc69fa03c007aff0c8251f7eb214dedb0ff56f0f1bde62bd15953
  - HF_HUB_OFFLINE=1、TRANSFORMERS_OFFLINE=1、requested_device=mps、allow_cpu_fallback=false；计时前后执行 torch.mps.synchronize()
  - 诊断批次只写 registered Mac debug root，不启动 ROS/MuJoCo/Task 11
success_criteria:
  - 只构造一个 actual detector，连续完成 6 次同帧 detect，保存每次 DINO proposal、detector raw candidate、固定 0.50 gate eligible candidate 和 full-resolution mask hash/图像
  - 保存 Grounding DINO processor/model/postprocess、SAM processor/model/mask postprocess、device transfer/host conversion/adapter conversion 和 MPS 同步总延迟
  - 6 次语义和 mask 不变，第 2至 6 次每次单独按 2000 ms 门禁判定，不挑最快值
failure_criteria:
  - MPS/FP32/offline 或 exact bundle/image/source provenance 不成立，候选/mask 在重复请求中不稳定，或任一 detect 异常
invalid_criteria:
  - 修改生产源码、模型、阈值、freshness、prompt、precision 或 fallback；联网加载；每次新建 detector；不同步 MPS；覆盖旧 evidence
provenance:
  source_behavior_commit: f55074e5d9806304955df1a0d2beadbd8e4a1ecc
  current_ledger_head: 4ab531553205c9ac686cabca10dfd78c68dd662f
  install_overlay: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install
  python: /Users/matianyi/ros2_jazzy/.venv/bin/python3
  bundle_manifest_sha256: 838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3
  source_rgb_sha256: 3881885fe5bcc69fa03c007aff0c8251f7eb214dedb0ff56f0f1bde62bd15953
commands:
  - command: HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 same_detector_phase_diagnostic.py --iterations 6 --output <new Mac debug batch>
    exit_code: 0
  - command: TASK10_PHASE_RESULT=<result.json> /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -q -p no:launch_testing -p no:launch_ros -p no:launch_pytest test_same_detector_phase_results.py --junitxml=<diagnostic-validation.xml>
    exit_code: 0
observed:
  - OBSERVED 只构造 1 个 detector，现有 8x8 warm-up 后同一真实 640x480 RGB 连续 6 次 detect 的 MPS 同步总延迟为 1185.302708、975.335333、973.731292、974.600042、973.230708、966.972000 ms
  - OBSERVED 第 2 至 6 次每次都低于 2000 ms，975.335333 ms 至 966.972000 ms，不在门禁边缘，无需挑选最快值
  - OBSERVED warmed 五次 DINO model 为 754.736041、751.819167、752.916958、752.554416、748.063250 ms；SAM model 为 195.915375、197.848167、198.692625、196.790458、196.502042 ms；adapter conversion 为 5.438915、5.110040、4.738167、5.189168、4.548125 ms
  - OBSERVED 6 次均为 3 个 raw candidate、1 个固定 0.50 gate eligible candidate、640x480/4651px mask；confidence、quality、bbox 和所有 mask SHA 完全一致
  - OBSERVED MPS FP32、CPU fallback false、offline env、exact bundle/image SHA 全部由 artifact 自验；诊断 JUnit 1 passed
  - OBSERVED diagnostic log SHA256=3f13077c94943a9a30a65159ddfac15e4206dc5f9fef4bb77a5f6e1f8658bbbb，result JSON SHA256=9d90879625c2fbbecaf40de093d6f1d6c4d176cdaf1e2cd2e080883be8406fcb，JUnit SHA256=346a269aa76daa69d693c74628a2a08886ea9c1357de6a7a4f0f6f4805e24179
inferred:
  - INFERRED 原 Mac 3851.778834 ms 不能代表 warmed capability；同 detector 正式形状稳定推理在 2 s 内，应修复的是启动 warm-up 形状与多框 batch 覆盖，不是模型、阈值或 freshness
conclusion: 诊断支持 FORMAL_SHAPE_WARMUP_NEEDED，进入 EXP-012 的 TDD 最小修复
evidence:
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-10/fix-round-1-mac-warmed-diagnostic/
decision: KEEP
next_experiment: EXP-012
```

```yaml
experiment_id: EXP-012
status: VALID
prior_experiment: EXP-011
hypothesis: 在 detector READY 之前用静态零图执行一次 640x480 Grounding DINO 和一次有效多框 SAM batch warm-up，可将首个真实帧的 MPS 延迟稳定降到 2000 ms 内
prediction: 新 detector 首个真实 640x480 请求不再承担 8x8 aspect-ratio 之外的 DINO 正式 shape 和 SAM multi-box 首次调度成本；Mac full stack 会在未放宽 2.0 s freshness 的情况下实际执行
single_variable: 只把 detector 启动 warm-up 从 8x8/单框替换为 640x480/确定性多框 batch；逐帧无状态、bundle、revision、prompt、thresholds、FP32、offline、CPU fallback false 和 2.0 s freshness 不变
lifecycle: FULL_RESTART
preconditions:
  - EXP-011 VALID，第 2 至 6 次实际 MPS warmed 请求全部低于 2000 ms
  - 先用测试固定 640x480 DINO 输入和大于 1 的 SAM box batch，观察旧实现 RED；然后才修改生产代码
  - 启动 timeout 继续使用已验证的 120 s，warm-up 在 detector 构造中完成后才能 READY
success_criteria:
  - CUDA/MPS 共用同一确定性正式 shape/multi-box warm-up，warm-up 不使用 scene truth，不调用 detect 且不发布候选、mask 或 pose
  - 测试证明正式 shape/multi-box 在 READY 前完成；该 warm-up 失败映射 WARMUP_FAILED 且 ROS 副作用为 0
  - Mac 与 Linux 任务 package gate 通过，新 exact commit 两端 actual offline smoke 通过，Mac 首个 full-stack 正式帧小于 2000 ms 并实际 PickPlace DONE
failure_criteria:
  - 测试/包门失败，首帧 Mac 仍超 2000 ms，任一端设备/fallback/offline/provenance 不成立，或 full-stack 缺 payload/semantic/mask/Depth/TF/source stamp/physical/cleanup 证据
invalid_criteria:
  - 更换模型/revision/pin/threshold/prompt/precision，放宽 freshness，使用 truth/color/最高分强选，发布 warm-up 结果，覆盖证据，修改 canonical checkout 或系统库
provenance:
  base_source_behavior_commit: f55074e5d9806304955df1a0d2beadbd8e4a1ecc
  current_ledger_head: 4ab531553205c9ac686cabca10dfd78c68dd662f
  formal_warmup_commit: 157c8f09ba12519d926cb1b947254c96ab5ececf
  ready_clock_watermark_commit: ec125ecc9879205e5d86506dfceb10540871395d
  post_discovery_subscription_commit: 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca
  bundle_manifest_sha256: 838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3
commands:
  - command: 在 f55074e 下用同一个 actual detector、同一真实 640x480 RGB 连续执行 6 次 MPS detect，并用临时 wrapper 记录 DINO/SAM/adapter 各阶段 monotonic latency
    exit_code: 0; diagnostic validation 1 passed
  - command: 旧实现运行 formal-shape/multi-box warm-up RED；实现后运行 GREEN、定向与 Mac 整包测试
    exit_code: RED=1; GREEN=0; Mac directed=0; Mac full=0
  - command: 先在 Mac full stack 启动只读 observer，记录首个 /cup_pose 的 source stamp、consumer ROS clock 与精确 age；依次验证 8x8 替换、READY clock watermark 与 output discovery 前移，不改变 2.0 s freshness
    exit_code: stale diagnostics=1; final exact 16d56fc full stack=0
  - command: 在 ai-station 创建并重建 exact 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca 隔离 checkout，任务 venv entrypoint 与 CUDA provenance gate；仓库根定向/整包测试
    exit_code: build=0; directed=0; full=0
  - command: HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ROS_DOMAIN_ID=157 GZ_PARTITION=v5-t005-grounded-sam-linux-fix-r1-final-001 timeout --signal=TERM --kill-after=20s 600s ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py run_mode:=execute execute:=true headless:=true sensor_rendering:=true session_id:=linux-grounded-sam-final-smoke-001 evidence_file:=/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/fix-round-1-output-discovery/linux/linux-smoke-001.json mujoco_scene:=/data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5/so101_demo_py/share/so101_demo_py/assets/mujoco/v5_multi_object_scene.xml mujoco_initial_keyframe:=task_start perception_startup_timeout_s:=120.0 cup_pose_timeout_s:=45.0 perception_backend:=grounded_sam perception_model_root:=/data/work/so101-models/grounded-sam-v1 perception_model_manifest_sha256:=838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3 perception_device:=cuda perception_allow_cpu_fallback:=false
    exit_code: 0
observed:
  - OBSERVED 同 detector 诊断的 6 次 MPS 总延迟为 1185.302708、975.335333、973.731292、974.600042、973.230708、966.972000 ms；第 2 至 6 次每次均低于 2000 ms，不在门禁边缘
  - OBSERVED 第 2 至 6 次 DINO model 为 754.736041、751.819167、752.916958、752.554416、748.063250 ms，SAM model 为 195.915375、197.848167、198.692625、196.790458、196.502042 ms，adapter conversion 为 5.438915、5.110040、4.738167、5.189168、4.548125 ms；每次均为 3 raw/1 eligible/4651px mask
  - OBSERVED 157c8f0 将 warm-up 固定为 480x640 零图和 16 个确定性网格框；测试证明其在 READY 前完成、失败 fail-closed，且不调用 detect、不发布候选/mask/pose。启动成本增加到 Mac 约 8.16 s、Linux 约 8.62 s，均在 120 s timeout 内
  - OBSERVED 第一轮 Mac full stack 暴露两段非模型 freshness 消耗：`FreshFrameGate(0)` 可冻结 READY 前排队帧，且在冻结帧后等待无订阅者的 detection/overlay discovery 约 1 s。ec125ec 只使用已有 `use_sim_time=true` ROS clock 等待非零且失败为 `SIM_CLOCK_UNAVAILABLE`，不回退 wall clock；16d56fc 将 output discovery 放在创建 RGB-D subscriptions 前，随后采样 watermark，第一张 `stamp > watermark` 的真正新帧可通过
  - OBSERVED Mac exact 16d56fc full stack 在 MPS FP32、CPU fallback false、offline、同 bundle/阈值下通过：inference_latency_ms=1506.458875，request_latency_ms=1575.570042，3 raw/1 eligible、640x480/4651px mask、Depth/TF 与源时间戳 /cup_pose；observer 记录 source=19.938 s、consumer=21.564 s、age=1.626 s < 2.0 s
  - OBSERVED Mac dynamic workflow DONE/19 transitions；VERIFY_PHYSICAL_GRASP left=1/right=1、table_contact=false、lift 约 0.004069 m、max force=0.5652395 N；final_xy_error_m=0.002020139、tilt=0.004522784 rad、table_contact=true
  - OBSERVED Mac RED/GREEN freshness tests 均保留；最终 directed 151/151、full 1052/1052。源码测试提交依次为 157c8f0、ec125ec、16d56fc
  - OBSERVED ai-station exact 16d56fc tracked source clean，submodule 71bc934；当前未跟踪生成目录为 build-task10-v4、install-task10-v4、log-task10-v4、build-task10-v5、install-task10-v5、log-task10-v5。v4 三项作为 deletion candidates 保留，v5 三项作为本次资格 overlay/log 保留，均未清理；install-task10-v5 的 rgbd_object_pose shebang 指向 `/data/work/venvs/so101-grounded-sam/bin/python`，package prefix/module 指向该隔离 checkout，rclpy 仍来自 `/opt/ros/jazzy`，torch 2.13.0+cu130/CUDA true/RTX 5080
  - OBSERVED Linux directed 151/151、仓库根 full 1052/1052（4 个既有 fork warnings）；保留一次未 ignore third_party dependency 的 build failure，以及一次 colcon package-cwd 下 11 个旧相对仓库根测试失败的无效批次
  - OBSERVED Linux exact 16d56fc actual offline smoke 为 status=OK、runtime_device=cuda、fallback false、inference=155.56822 ms、request=276.020068 ms、cold=8624.091031 ms、3 raw/1 eligible、640x480/4643px mask、非空 176016-byte cloud、Depth/TF center_world_xyz=[0.02009484,-0.28046013,0.165]，/cup_pose 与 dynamic input source_stamp_ns 均为 13444000000
  - OBSERVED Linux dynamic DONE/19 transitions；bilateral=true、micro_lift=0.003951946 m、table_contact=false、verify left/right=1/1、max force=0.577346792 N；final_xy_error_m=0.002044364、tilt=0.004583883 rad、table_contact=true
  - OBSERVED 两端 manifest SHA 均为 838c5154...8b3，detector revision a2bb814...、segmenter revision de431c4...；actual smoke 均设置 HF_HUB_OFFLINE=1 与 TRANSFORMERS_OFFLINE=1，loader 继续强制 local_files_only=True；两端 cleanup 为 owned processes/domain NONE
  - OBSERVED Linux validation.json SHA256=7af2d2833108d319a4c0e47afb44b2fb0f7355fb7da885ce6a8f0366e40c62d3；Mac final log/result/dynamic/observer SHA256 分别为 4eacd19d9ad3c81b8dab82f17c032c94d3f1159329c21ca9fb0a3831a23e073e、1ab15acc0c1e00f432bdf2666b5e2a7b6067ceb6adbd3f30870947c4dba26787、cb8157a9ed56449ba28fd85ccfa7a5a81a20348a8c8938b0a91f8d9c28c825c4、29c262b94d6eef2153d87ab6755e1e82bfadf00252b34bdafb802d75937170df
  - OBSERVED Mac 最终批次 `/tmp/so101-debug-v5-t005-grounded-sam-20260901/task-10/fix-round-1-output-discovery/` 的 immutable inventory 登记 53 项：49 regular、4 symlink；symlink 只登记 link target 且不跟随，权威批次无 `._*` AppleDouble sidecar。inventory SHA256=4049e685881ee4b6aa54f2f302c79b7c578cdc58ceec10002805a3839d057d8e，archive SHA256=a81069e24f8c26314743354890683b2b3e7fa1fecf446877ea39b517f68cdd34
  - OBSERVED durable read-back 位于 ai-station `/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/model-smoke/macos/fix-round-1-output-discovery-readback/`；逐项核对 path/type/size/SHA/count 全部通过，readback-verify.log SHA256=26c232170d1323ae713555a5f7007d80a651e1c0e268420d571e02fdb2028ac7
inferred:
  - INFERRED 原 3851.778834 ms 是正式 shape/batch 首次调度和错误的帧生命周期排序共同造成，不能判定 MPS 模型能力不足；正式 warm-up 加 post-discovery 新帧门禁后，未放宽 2.0 s freshness 即能完成 actual full stack
  - INFERRED 修复没有改变逐帧无状态、scene/model/revisions/prompt/thresholds/FP32/fallback 或 freshness；它只使 READY 和采帧边界与既有接口语义一致
conclusion: exact 16d56fc 在 Mac MPS 与 Linux CUDA 上使用同一 immutable bundle 的 actual offline full-stack smoke 均通过；Task 10 Fix Round 1 VALID，smoke 不计入 Task 11 最终 5/5
evidence:
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-10/fix-round-1-mac-warmed-diagnostic/
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-10/fix-round-1-formal-warmup/
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-10/fix-round-1-freshness-watermark/
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-10/fix-round-1-output-discovery/
  - ai-station:/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/fix-round-1-formal-warmup/
  - ai-station:/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/fix-round-1-output-discovery/linux/
  - ai-station:/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/model-smoke/macos/fix-round-1-output-discovery-readback/
decision: KEEP
next_experiment: Task 11 Step 1 — 预写四场景实验矩阵；首个运行 linux-matrix-1-task_start；Task 10 smoke 保持 separate and uncounted
```

## Checkpoint CP-006

```yaml
checkpoint_id: CP-006
last_valid_experiment: EXP-012
current_hypothesis: exact 16d56fc 的 formal-shape/multi-box warm-up 与 post-discovery freshness watermark 已使同 bundle Mac MPS/Linux CUDA actual offline smoke 都在既有安全门内完成
working_tree_status: 三个源码/测试修复已分别提交为 157c8f0、ec125ec、16d56fc；Mac tracked worktree 与 ai-station exact 16d56fc tracked source 均 clean。ai-station 未跟踪生成目录 v4/v5 的 disposition 见 retained_runs/deletion_candidates；本 checkpoint 仅包含 ledger 更新，SDD report/progress 为 ignored local orchestration
owned_processes: NONE on Mac final domain and ai-station ROS_DOMAIN_ID=157
preserved_processes: canonical `/data/work/ws_moveit` 只读且其用户未跟踪文档保持不变；未运行真实机械臂
retained_runs:
  - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901
  - /data/work/so101-models/grounded-sam-v1
  - /Users/matianyi/Models/so101/grounded-sam-v1
  - /data/work/so101-v5-t005-grounded-sam-task10-16d56fc
  - /data/work/so101-v5-t005-grounded-sam-task10-157c8f0
  - ai-station:/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/model-smoke/macos/fix-round-1-output-discovery-readback
  - ai-station:/data/work/so101-v5-t005-grounded-sam-task10-16d56fc/build-task10-v5
  - ai-station:/data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5
  - ai-station:/data/work/so101-v5-t005-grounded-sam-task10-16d56fc/log-task10-v5
archived_runs: []
deletion_candidates:
  - ai-station:/data/work/so101-v5-t005-grounded-sam-task10-d870113
  - ai-station:/data/work/so101-models/.grounded-sam-v1.staging-8rjn6_lm
  - ai-station:/data/work/so101-v5-t005-grounded-sam-task10-16d56fc/build-task10-v4
  - ai-station:/data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v4
  - ai-station:/data/work/so101-v5-t005-grounded-sam-task10-16d56fc/log-task10-v4
  - /tmp/task10-16d56fc.bundle
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-10/f55074e.bundle
  - /Users/matianyi/.codex/worktrees/5b15/moveit-demo/build-task10-watermark-v2
  - /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-task10-watermark-v2
  - /Users/matianyi/.codex/worktrees/5b15/moveit-demo/log-task10-watermark-v2
decision: TASK10_FIX_ROUND_2_VALID
next_command: Task 11 Step 1 — 预写四场景实验矩阵；首个运行 linux-matrix-1-task_start；不得把 Task 10 smoke 计入 Task 11 5/5
```

## Task 11 frozen contract and planned experiments

以下实验均冻结 `source_commit=16d56fc1c129b5bb8b45d201db38dd2ab70e62ca`、
`bundle_manifest_sha256=838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3`、
`prompt="plastic cup."`、Grounding DINO/SAM 阈值
`box=0.35,text=0.25,duplicate_iou=0.85,max_candidates=16,sam_quality=0.75,min_mask_pixels=64,max_mask_area_ratio=0.50`、
`target_confidence_threshold=0.50`、FP32、`HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`、
`perception_allow_cpu_fallback=false`、`maximum_source_age_s=2.0` 与 `sim_speed_factor=1.0`。
Linux 固定 CUDA，Mac 固定 MPS。每条记录都有独立 request/session/domain/partition，生命周期为
`FULL_RESTART`。每轮结束后必须确认本轮 owned process、ROS node、domain 与 partition 均为空；
`VALID` 失败或 `INVALID` 都立即终止该平台当前批次，修复后从新 experiment ID 的场景 1 或
5/5 第 1 轮重新计数。Task 10 smoke 不进入任何 Task 11 分母。

四场景共同成功条件：真实 CameraInfo/RGB/Depth 在同一 stamp、frame 与 640x480 尺寸对齐；
模型、device、revision、prompt、阈值与 bundle provenance 匹配；warmed request `<=2000 ms`；
每个杯子 mask truth IoU `>=0.80`；唯一杯子 world error `<0.01 m`；错误场景没有新或旧
`/cup_pose`；近瓶场景 bottle overlap 为 0；候选、mask、overlay、DINO/SAM 分数、source stamp、
TF、observer 与 cleanup 证据完整。共同有效失败条件是运行前提全部成立但任一业务门槛不满足。
共同无效条件是旧 topic、重复 node、错误 overlay/commit/device/bundle、未对齐 payload、缺 truth、
证据写失败、observer 污染、非独立 domain/partition 或 cleanup 失败。

5/5 共同成功条件：感知 payload/语义/mask/Depth/TF 与 source-stamped `/cup_pose` 全部来自本轮；
执行器消费同一 stamp/XYZ；双侧抓持、物理 micro-lift、搬运、place、MoveIt detach/world sync、
松爪分离、桌面稳定支撑、最终 XY `<=0.01 m`、upright tilt `<=0.10 rad`、新鲜可见证据与 cleanup
全部通过。共同有效失败条件是干净前提下任一业务或物理门槛失败；共同无效条件与四场景相同，
另加视觉证据非本轮、缺少 FULL_RESTART 或生命周期污染。

```yaml
- experiment_id: EXP-013
  status: INVALID
  prior_experiment: EXP-012
  hypothesis: Linux CUDA 固定模型能从 task_start 唯一选择 plastic_cup 并完成 source-stamped /cup_pose
  prediction: matching=1, IoU>=0.80, world_error<0.01m, request<=2000ms, pose stamp与源stamp相同
  single_variable: platform=linux; keyframe=task_start; expected=unique
  lifecycle: FULL_RESTART
  preconditions: [frozen_contract, clean_owned_graph, initial_keyframe_task_start]
  success_criteria: [four_scene_common, exactly_one_eligible, new_source_stamped_cup_pose]
  failure_criteria: [four_scene_valid_failure]
  invalid_criteria: [four_scene_common_invalid]
  provenance: {source_commit: 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca, install_overlay: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5, runtime_executable: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place, ros_domain_id: 161, gz_partition: v5-t005-linux-matrix-01-task-start}
  commands: [{command: HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ROS_DOMAIN_ID=161 GZ_PARTITION=v5-t005-linux-matrix-01-task-start timeout --signal=TERM --kill-after=20s 600s ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py run_mode:=execute execute:=true headless:=true sensor_rendering:=true session_id:=linux-matrix-1-task_start evidence_file:=/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-1-task_start/launch.json mujoco_scene:=/data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5/so101_demo_py/share/so101_demo_py/assets/mujoco/v5_multi_object_scene.xml mujoco_initial_keyframe:=task_start perception_startup_timeout_s:=120.0 cup_pose_timeout_s:=45.0 perception_backend:=grounded_sam perception_model_root:=/data/work/so101-models/grounded-sam-v1 perception_model_manifest_sha256:=838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3 perception_device:=cuda perception_allow_cpu_fallback:=false, exit_code: 127}]
  observed:
    - OBSERVED runner 的 `set -u` 使 `/opt/ros/jazzy/setup.zsh` 在读取未设置的 AMENT_TRACE_SETUP_FILES/COLCON_TRACE 时中断，ros2 未进入 PATH，launch_rc=127
    - OBSERVED 模型、ROS stack 与 MuJoCo 控制均未启动；独立 acceptance-only truth renderer 成功
    - OBSERVED observer/truth observer 因同一缺失 rclpy 环境退出；validation 无业务输入
    - OBSERVED cleanup 文件误收 runner 自身 PID；结束后的独立回读证明 domain 161 无 node，session 无 owned process
  inferred: [NONE]
  conclusion: INVALID environment bootstrap；未进入模型或业务边界，不计入矩阵
  evidence: [/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-1-task_start]
  decision: REPEAT
  next_experiment: EXP-031
- experiment_id: EXP-014
  status: PLANNED
  prior_experiment: EXP-013
  hypothesis: Linux CUDA 在 v5_no_cup 会 fail-closed
  prediction: TARGET_NOT_FOUND, matching=0, no new /cup_pose, request<=2000ms
  single_variable: platform=linux; keyframe=v5_no_cup; expected=not_found
  lifecycle: FULL_RESTART
  preconditions: [frozen_contract, EXP-013_VALID_success, clean_owned_graph]
  success_criteria: [four_scene_common, TARGET_NOT_FOUND, no_new_or_stale_cup_pose]
  failure_criteria: [four_scene_valid_failure]
  invalid_criteria: [four_scene_common_invalid]
  provenance: {source_commit: 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca, install_overlay: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5, runtime_executable: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place, ros_domain_id: 162, gz_partition: v5-t005-linux-matrix-02-no-cup}
  commands: [{command: exact Task 11 Linux matrix launch recorded before RUNNING, exit_code: PENDING}]
  observed: [PENDING]
  inferred: [NONE]
  conclusion: PENDING
  evidence: [/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-2-v5_no_cup]
  decision: PENDING
  next_experiment: EXP-015
- experiment_id: EXP-015
  status: PLANNED
  prior_experiment: EXP-014
  hypothesis: Linux CUDA 在 v5_two_cups 会保留两个合格实例并 fail-closed
  prediction: TARGET_AMBIGUOUS, matching=2, 两个IoU>=0.80, no new /cup_pose
  single_variable: platform=linux; keyframe=v5_two_cups; expected=ambiguous
  lifecycle: FULL_RESTART
  preconditions: [frozen_contract, EXP-014_VALID_success, clean_owned_graph]
  success_criteria: [four_scene_common, TARGET_AMBIGUOUS, exactly_two_eligible, no_new_or_stale_cup_pose]
  failure_criteria: [four_scene_valid_failure]
  invalid_criteria: [four_scene_common_invalid]
  provenance: {source_commit: 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca, install_overlay: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5, runtime_executable: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place, ros_domain_id: 163, gz_partition: v5-t005-linux-matrix-03-two-cups}
  commands: [{command: exact Task 11 Linux matrix launch recorded before RUNNING, exit_code: PENDING}]
  observed: [PENDING]
  inferred: [NONE]
  conclusion: PENDING
  evidence: [/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-3-v5_two_cups]
  decision: PENDING
  next_experiment: EXP-016
- experiment_id: EXP-016
  status: PLANNED
  prior_experiment: EXP-015
  hypothesis: Linux CUDA 在 v5_cup_near_bottle 保留唯一杯子 mask 且不吞并 bottle pixels
  prediction: matching=1, IoU>=0.80, bottle_overlap=0, world_error<0.01m, new /cup_pose
  single_variable: platform=linux; keyframe=v5_cup_near_bottle; expected=unique_adjacent
  lifecycle: FULL_RESTART
  preconditions: [frozen_contract, EXP-015_VALID_success, clean_owned_graph]
  success_criteria: [four_scene_common, exactly_one_eligible, zero_bottle_overlap, new_source_stamped_cup_pose]
  failure_criteria: [four_scene_valid_failure]
  invalid_criteria: [four_scene_common_invalid]
  provenance: {source_commit: 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca, install_overlay: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5, runtime_executable: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place, ros_domain_id: 164, gz_partition: v5-t005-linux-matrix-04-near-bottle}
  commands: [{command: exact Task 11 Linux matrix launch recorded before RUNNING, exit_code: PENDING}]
  observed: [PENDING]
  inferred: [NONE]
  conclusion: PENDING
  evidence: [/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-4-v5_cup_near_bottle]
  decision: PENDING
  next_experiment: EXP-017
- experiment_id: EXP-017
  status: PLANNED
  prior_experiment: EXP-016
  hypothesis: Mac MPS 固定模型能从 task_start 唯一选择 plastic_cup
  prediction: matching=1, IoU>=0.80, world_error<0.01m, request<=2000ms, fresh exact-window evidence
  single_variable: platform=macos; keyframe=task_start; expected=unique
  lifecycle: FULL_RESTART
  preconditions: [frozen_contract, Linux_matrix_4_of_4_PASS, clean_owned_graph]
  success_criteria: [four_scene_common, exactly_one_eligible, new_source_stamped_cup_pose, fresh_exact_window_capture]
  failure_criteria: [four_scene_valid_failure]
  invalid_criteria: [four_scene_common_invalid]
  provenance: {source_commit: 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca, install_overlay: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-task10-watermark-v2, runtime_executable: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-task10-watermark-v2/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place, ros_domain_id: 165, gz_partition: v5-t005-mac-matrix-01-task-start}
  commands: [{command: exact Task 11 Mac matrix launch recorded before RUNNING, exit_code: PENDING}]
  observed: [PENDING]
  inferred: [NONE]
  conclusion: PENDING
  evidence: [/tmp/so101-debug-v5-t005-grounded-sam-20260901/perception-matrix/macos/mac-matrix-1-task_start]
  decision: PENDING
  next_experiment: EXP-018
- experiment_id: EXP-018
  status: PLANNED
  prior_experiment: EXP-017
  hypothesis: Mac MPS 在 v5_no_cup 会 fail-closed
  prediction: TARGET_NOT_FOUND, matching=0, no new /cup_pose, fresh exact-window evidence
  single_variable: platform=macos; keyframe=v5_no_cup; expected=not_found
  lifecycle: FULL_RESTART
  preconditions: [frozen_contract, EXP-017_VALID_success, clean_owned_graph]
  success_criteria: [four_scene_common, TARGET_NOT_FOUND, no_new_or_stale_cup_pose, fresh_exact_window_capture]
  failure_criteria: [four_scene_valid_failure]
  invalid_criteria: [four_scene_common_invalid]
  provenance: {source_commit: 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca, install_overlay: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-task10-watermark-v2, runtime_executable: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-task10-watermark-v2/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place, ros_domain_id: 166, gz_partition: v5-t005-mac-matrix-02-no-cup}
  commands: [{command: exact Task 11 Mac matrix launch recorded before RUNNING, exit_code: PENDING}]
  observed: [PENDING]
  inferred: [NONE]
  conclusion: PENDING
  evidence: [/tmp/so101-debug-v5-t005-grounded-sam-20260901/perception-matrix/macos/mac-matrix-2-v5_no_cup]
  decision: PENDING
  next_experiment: EXP-019
- experiment_id: EXP-019
  status: PLANNED
  prior_experiment: EXP-018
  hypothesis: Mac MPS 在 v5_two_cups 会保留两个合格实例并 fail-closed
  prediction: TARGET_AMBIGUOUS, matching=2, 两个IoU>=0.80, no new /cup_pose
  single_variable: platform=macos; keyframe=v5_two_cups; expected=ambiguous
  lifecycle: FULL_RESTART
  preconditions: [frozen_contract, EXP-018_VALID_success, clean_owned_graph]
  success_criteria: [four_scene_common, TARGET_AMBIGUOUS, exactly_two_eligible, no_new_or_stale_cup_pose, fresh_exact_window_capture]
  failure_criteria: [four_scene_valid_failure]
  invalid_criteria: [four_scene_common_invalid]
  provenance: {source_commit: 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca, install_overlay: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-task10-watermark-v2, runtime_executable: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-task10-watermark-v2/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place, ros_domain_id: 167, gz_partition: v5-t005-mac-matrix-03-two-cups}
  commands: [{command: exact Task 11 Mac matrix launch recorded before RUNNING, exit_code: PENDING}]
  observed: [PENDING]
  inferred: [NONE]
  conclusion: PENDING
  evidence: [/tmp/so101-debug-v5-t005-grounded-sam-20260901/perception-matrix/macos/mac-matrix-3-v5_two_cups]
  decision: PENDING
  next_experiment: EXP-020
- experiment_id: EXP-020
  status: PLANNED
  prior_experiment: EXP-019
  hypothesis: Mac MPS 在 v5_cup_near_bottle 保留唯一杯子 mask 且不吞并 bottle pixels
  prediction: matching=1, IoU>=0.80, bottle_overlap=0, world_error<0.01m, new /cup_pose
  single_variable: platform=macos; keyframe=v5_cup_near_bottle; expected=unique_adjacent
  lifecycle: FULL_RESTART
  preconditions: [frozen_contract, EXP-019_VALID_success, clean_owned_graph]
  success_criteria: [four_scene_common, exactly_one_eligible, zero_bottle_overlap, new_source_stamped_cup_pose, fresh_exact_window_capture]
  failure_criteria: [four_scene_valid_failure]
  invalid_criteria: [four_scene_common_invalid]
  provenance: {source_commit: 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca, install_overlay: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-task10-watermark-v2, runtime_executable: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-task10-watermark-v2/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place, ros_domain_id: 168, gz_partition: v5-t005-mac-matrix-04-near-bottle}
  commands: [{command: exact Task 11 Mac matrix launch recorded before RUNNING, exit_code: PENDING}]
  observed: [PENDING]
  inferred: [NONE]
  conclusion: PENDING
  evidence: [/tmp/so101-debug-v5-t005-grounded-sam-20260901/perception-matrix/macos/mac-matrix-4-v5_cup_near_bottle]
  decision: PENDING
  next_experiment: EXP-021
- experiment_id: EXP-021
  status: PLANNED
  prior_experiment: EXP-020
  hypothesis: Linux FULL_RESTART fixed configuration run 1 succeeds
  prediction: all 5_of_5_common gates PASS
  single_variable: NONE; linux consecutive batch run=1
  lifecycle: FULL_RESTART
  preconditions: [frozen_contract, dual_platform_matrix_8_of_8_PASS, clean_owned_graph]
  success_criteria: [five_of_five_common]
  failure_criteria: [five_of_five_valid_failure]
  invalid_criteria: [five_of_five_common_invalid]
  provenance: {source_commit: 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca, install_overlay: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5, runtime_executable: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place, ros_domain_id: 171, gz_partition: v5-t005-linux-pick-final-1}
  commands: [{command: exact Task 11 Linux pick launch recorded before RUNNING, exit_code: PENDING}]
  observed: [PENDING]
  inferred: [NONE]
  conclusion: PENDING
  evidence: [/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/pick-place/linux/linux-pick-final-1]
  decision: PENDING
  next_experiment: EXP-022
- experiment_id: EXP-022
  status: PLANNED
  prior_experiment: EXP-021
  hypothesis: Linux FULL_RESTART fixed configuration run 2 succeeds consecutively
  prediction: all 5_of_5_common gates PASS
  single_variable: NONE; linux consecutive batch run=2
  lifecycle: FULL_RESTART
  preconditions: [frozen_contract, EXP-021_VALID_success, clean_owned_graph]
  success_criteria: [five_of_five_common]
  failure_criteria: [five_of_five_valid_failure]
  invalid_criteria: [five_of_five_common_invalid]
  provenance: {source_commit: 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca, install_overlay: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5, runtime_executable: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place, ros_domain_id: 172, gz_partition: v5-t005-linux-pick-final-2}
  commands: [{command: exact Task 11 Linux pick launch recorded before RUNNING, exit_code: PENDING}]
  observed: [PENDING]
  inferred: [NONE]
  conclusion: PENDING
  evidence: [/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/pick-place/linux/linux-pick-final-2]
  decision: PENDING
  next_experiment: EXP-023
- experiment_id: EXP-023
  status: PLANNED
  prior_experiment: EXP-022
  hypothesis: Linux FULL_RESTART fixed configuration run 3 succeeds consecutively
  prediction: all 5_of_5_common gates PASS
  single_variable: NONE; linux consecutive batch run=3
  lifecycle: FULL_RESTART
  preconditions: [frozen_contract, EXP-022_VALID_success, clean_owned_graph]
  success_criteria: [five_of_five_common]
  failure_criteria: [five_of_five_valid_failure]
  invalid_criteria: [five_of_five_common_invalid]
  provenance: {source_commit: 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca, install_overlay: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5, runtime_executable: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place, ros_domain_id: 173, gz_partition: v5-t005-linux-pick-final-3}
  commands: [{command: exact Task 11 Linux pick launch recorded before RUNNING, exit_code: PENDING}]
  observed: [PENDING]
  inferred: [NONE]
  conclusion: PENDING
  evidence: [/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/pick-place/linux/linux-pick-final-3]
  decision: PENDING
  next_experiment: EXP-024
- experiment_id: EXP-024
  status: PLANNED
  prior_experiment: EXP-023
  hypothesis: Linux FULL_RESTART fixed configuration run 4 succeeds consecutively
  prediction: all 5_of_5_common gates PASS
  single_variable: NONE; linux consecutive batch run=4
  lifecycle: FULL_RESTART
  preconditions: [frozen_contract, EXP-023_VALID_success, clean_owned_graph]
  success_criteria: [five_of_five_common]
  failure_criteria: [five_of_five_valid_failure]
  invalid_criteria: [five_of_five_common_invalid]
  provenance: {source_commit: 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca, install_overlay: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5, runtime_executable: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place, ros_domain_id: 174, gz_partition: v5-t005-linux-pick-final-4}
  commands: [{command: exact Task 11 Linux pick launch recorded before RUNNING, exit_code: PENDING}]
  observed: [PENDING]
  inferred: [NONE]
  conclusion: PENDING
  evidence: [/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/pick-place/linux/linux-pick-final-4]
  decision: PENDING
  next_experiment: EXP-025
- experiment_id: EXP-025
  status: PLANNED
  prior_experiment: EXP-024
  hypothesis: Linux FULL_RESTART fixed configuration run 5 succeeds consecutively
  prediction: all 5_of_5_common gates PASS and Linux consecutive result is 5/5
  single_variable: NONE; linux consecutive batch run=5
  lifecycle: FULL_RESTART
  preconditions: [frozen_contract, EXP-024_VALID_success, clean_owned_graph]
  success_criteria: [five_of_five_common, linux_consecutive_5_of_5]
  failure_criteria: [five_of_five_valid_failure]
  invalid_criteria: [five_of_five_common_invalid]
  provenance: {source_commit: 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca, install_overlay: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5, runtime_executable: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place, ros_domain_id: 175, gz_partition: v5-t005-linux-pick-final-5}
  commands: [{command: exact Task 11 Linux pick launch recorded before RUNNING, exit_code: PENDING}]
  observed: [PENDING]
  inferred: [NONE]
  conclusion: PENDING
  evidence: [/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/pick-place/linux/linux-pick-final-5]
  decision: PENDING
  next_experiment: EXP-026
- experiment_id: EXP-026
  status: PLANNED
  prior_experiment: EXP-025
  hypothesis: Mac FULL_RESTART fixed configuration run 1 succeeds
  prediction: all 5_of_5_common gates PASS with fresh exact-window evidence
  single_variable: NONE; macos consecutive batch run=1
  lifecycle: FULL_RESTART
  preconditions: [frozen_contract, linux_consecutive_5_of_5, clean_owned_graph]
  success_criteria: [five_of_five_common, fresh_exact_window_capture]
  failure_criteria: [five_of_five_valid_failure]
  invalid_criteria: [five_of_five_common_invalid]
  provenance: {source_commit: 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca, install_overlay: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-task10-watermark-v2, runtime_executable: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-task10-watermark-v2/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place, ros_domain_id: 181, gz_partition: v5-t005-mac-pick-final-1}
  commands: [{command: exact Task 11 Mac pick launch recorded before RUNNING, exit_code: PENDING}]
  observed: [PENDING]
  inferred: [NONE]
  conclusion: PENDING
  evidence: [/tmp/so101-debug-v5-t005-grounded-sam-20260901/pick-place/macos/mac-pick-final-1]
  decision: PENDING
  next_experiment: EXP-027
- experiment_id: EXP-027
  status: PLANNED
  prior_experiment: EXP-026
  hypothesis: Mac FULL_RESTART fixed configuration run 2 succeeds consecutively
  prediction: all 5_of_5_common gates PASS with fresh exact-window evidence
  single_variable: NONE; macos consecutive batch run=2
  lifecycle: FULL_RESTART
  preconditions: [frozen_contract, EXP-026_VALID_success, clean_owned_graph]
  success_criteria: [five_of_five_common, fresh_exact_window_capture]
  failure_criteria: [five_of_five_valid_failure]
  invalid_criteria: [five_of_five_common_invalid]
  provenance: {source_commit: 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca, install_overlay: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-task10-watermark-v2, runtime_executable: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-task10-watermark-v2/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place, ros_domain_id: 182, gz_partition: v5-t005-mac-pick-final-2}
  commands: [{command: exact Task 11 Mac pick launch recorded before RUNNING, exit_code: PENDING}]
  observed: [PENDING]
  inferred: [NONE]
  conclusion: PENDING
  evidence: [/tmp/so101-debug-v5-t005-grounded-sam-20260901/pick-place/macos/mac-pick-final-2]
  decision: PENDING
  next_experiment: EXP-028
- experiment_id: EXP-028
  status: PLANNED
  prior_experiment: EXP-027
  hypothesis: Mac FULL_RESTART fixed configuration run 3 succeeds consecutively
  prediction: all 5_of_5_common gates PASS with fresh exact-window evidence
  single_variable: NONE; macos consecutive batch run=3
  lifecycle: FULL_RESTART
  preconditions: [frozen_contract, EXP-027_VALID_success, clean_owned_graph]
  success_criteria: [five_of_five_common, fresh_exact_window_capture]
  failure_criteria: [five_of_five_valid_failure]
  invalid_criteria: [five_of_five_common_invalid]
  provenance: {source_commit: 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca, install_overlay: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-task10-watermark-v2, runtime_executable: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-task10-watermark-v2/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place, ros_domain_id: 183, gz_partition: v5-t005-mac-pick-final-3}
  commands: [{command: exact Task 11 Mac pick launch recorded before RUNNING, exit_code: PENDING}]
  observed: [PENDING]
  inferred: [NONE]
  conclusion: PENDING
  evidence: [/tmp/so101-debug-v5-t005-grounded-sam-20260901/pick-place/macos/mac-pick-final-3]
  decision: PENDING
  next_experiment: EXP-029
- experiment_id: EXP-029
  status: PLANNED
  prior_experiment: EXP-028
  hypothesis: Mac FULL_RESTART fixed configuration run 4 succeeds consecutively
  prediction: all 5_of_5_common gates PASS with fresh exact-window evidence
  single_variable: NONE; macos consecutive batch run=4
  lifecycle: FULL_RESTART
  preconditions: [frozen_contract, EXP-028_VALID_success, clean_owned_graph]
  success_criteria: [five_of_five_common, fresh_exact_window_capture]
  failure_criteria: [five_of_five_valid_failure]
  invalid_criteria: [five_of_five_common_invalid]
  provenance: {source_commit: 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca, install_overlay: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-task10-watermark-v2, runtime_executable: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-task10-watermark-v2/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place, ros_domain_id: 184, gz_partition: v5-t005-mac-pick-final-4}
  commands: [{command: exact Task 11 Mac pick launch recorded before RUNNING, exit_code: PENDING}]
  observed: [PENDING]
  inferred: [NONE]
  conclusion: PENDING
  evidence: [/tmp/so101-debug-v5-t005-grounded-sam-20260901/pick-place/macos/mac-pick-final-4]
  decision: PENDING
  next_experiment: EXP-030
- experiment_id: EXP-030
  status: PLANNED
  prior_experiment: EXP-029
  hypothesis: Mac FULL_RESTART fixed configuration run 5 succeeds consecutively
  prediction: all 5_of_5_common gates PASS and Mac consecutive result is 5/5
  single_variable: NONE; macos consecutive batch run=5
  lifecycle: FULL_RESTART
  preconditions: [frozen_contract, EXP-029_VALID_success, clean_owned_graph]
  success_criteria: [five_of_five_common, fresh_exact_window_capture, macos_consecutive_5_of_5]
  failure_criteria: [five_of_five_valid_failure]
  invalid_criteria: [five_of_five_common_invalid]
  provenance: {source_commit: 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca, install_overlay: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-task10-watermark-v2, runtime_executable: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-task10-watermark-v2/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place, ros_domain_id: 185, gz_partition: v5-t005-mac-pick-final-5}
  commands: [{command: exact Task 11 Mac pick launch recorded before RUNNING, exit_code: PENDING}]
  observed: [PENDING]
  inferred: [NONE]
  conclusion: PENDING
  evidence: [/tmp/so101-debug-v5-t005-grounded-sam-20260901/pick-place/macos/mac-pick-final-5]
  decision: PENDING
  next_experiment: NONE
```

## Checkpoint CP-007

```yaml
checkpoint_id: CP-007
last_valid_experiment: EXP-012
current_hypothesis: 固定 exact 16d56fc 与同一 immutable bundle 可以先通过 Linux CUDA 四场景，再通过 Mac MPS 四场景，最后分别完成 FULL_RESTART 连续 5/5
working_tree_status: ledger 在 b5940f7 基线上预写 Task 11；本地仅有已登记的 build/install/log-task10-watermark-v2 生成目录，ai-station exact checkout 仅有 CP-006 已登记的 v4/v5 生成目录
owned_processes: NONE；Mac domain 159 与 ai-station domain 157 均无 ROS node
preserved_processes: canonical /data/work/ws_moveit 及其用户未跟踪文档保持只读；未运行真实机械臂
confirmed_conclusions:
  - EXP-012 exact 16d56fc 双端 actual offline smoke 与模拟 PickPlace 通过，但不计入 Task 11
disproven_routes:
  - Task 10 首张冷正式帧不能代表 warmed 模型能力；EXP-011/EXP-012 已证伪
open_risks:
  - 四场景 truth IoU、错误场景无 pose 与双端连续 5/5 尚未实测
next_command: 将 EXP-013 更新为 RUNNING，核验 exact Linux provenance 后启动唯一一套 linux-matrix-1-task_start stack
```

## Task 11 batch correction after EXP-013

`2026-09-01` correction：EXP-013 在 ROS setup 阶段即为 `INVALID`，所以原 Linux 批次
EXP-014～EXP-016 全部未运行且不得计数。修正只删除验收 runner 的 `set -u`，并在 cleanup
检查中排除 runner 自身 PID；没有改 source commit、模型、bundle、prompt、阈值、FP32、offline、
device、freshness、场景或 motion policy。新批次从 EXP-031 开始，使用新 domain、partition、
session、request 与 evidence 路径，原 EXP-013 证据保留且不覆盖。EXP-017 之后的 Mac/5-of-5
计划只有在新 Linux 四场景 4/4 后才允许进入。

```yaml
- experiment_id: EXP-031
  status: VALID
  prior_experiment: EXP-013
  hypothesis: 修正 shell bootstrap 后，Linux CUDA 固定模型能从 task_start 唯一选择 plastic_cup
  prediction: ROS环境完整；matching=1, IoU>=0.80, world_error<0.01m, request<=2000ms, source-stamped pose
  single_variable: 仅验收 runner 在 source ROS setup 时不启用 nounset；生产配置 NONE
  lifecycle: FULL_RESTART
  preconditions: [frozen_contract, EXP-013_INVALID_no_business_execution, clean_owned_graph]
  success_criteria: [four_scene_common, exactly_one_eligible, new_source_stamped_cup_pose]
  failure_criteria: [four_scene_valid_failure]
  invalid_criteria: [four_scene_common_invalid]
  provenance: {source_commit: 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca, install_overlay: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5, runtime_executable: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place, ros_domain_id: 191, gz_partition: v5-t005-linux-matrix-r2-01-task-start}
  commands: [{command: HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ROS_DOMAIN_ID=191 GZ_PARTITION=v5-t005-linux-matrix-r2-01-task-start timeout --signal=TERM --kill-after=20s 600s ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py run_mode:=execute execute:=true headless:=true sensor_rendering:=true session_id:=linux-matrix-r2-1-task_start evidence_file:=/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r2-1-task_start/launch.json mujoco_scene:=/data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5/so101_demo_py/share/so101_demo_py/assets/mujoco/v5_multi_object_scene.xml mujoco_initial_keyframe:=task_start perception_startup_timeout_s:=120.0 cup_pose_timeout_s:=45.0 perception_backend:=grounded_sam perception_model_root:=/data/work/so101-models/grounded-sam-v1 perception_model_manifest_sha256:=838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3 perception_device:=cuda perception_allow_cpu_fallback:=false, exit_code: 1}]
  observed:
    - raw_candidates=3; target-eligible candidates=1; DINO confidences=[0.7210858464,0.4792901576,0.3530465066]; SAM qualities=[0.9401747,0.9536808,0.9346505]
    - selected plastic_cup truth IoU=0.9863858753; world pose error=0.0004925639m; inference=197.203623ms; request=294.371973ms
    - observed RGB、Depth、CameraInfo、detections、overlay 与 /cup_pose 的 source stamp 全部为 9323999999；Depth 307200/307200 像素有限且为正；生产 source-rgb 与 observer source-rgb 解码像素逐点一致
    - detector/localizer 已发布满足数值门禁的新 pose，但动态 consumer 返回 CUP_POSE_STALE，launch exit=1；这是业务链路内可复现失败，故本轮 VALID 但不成功
    - cleanup.exit=0；cleanup-nodes.txt 与 cleanup-processes.txt 都为空；随后独立回读 ROS_DOMAIN_ID=191 也无 node；进程核验只匹配到核验命令自身，不存在 owned runtime process
    - acceptance.json SHA256=3d7d8f472531655a8948b1cced0c199b8c633f359af9276963f751fc4d154c51；inventory.sha256 SHA256=4c54fe05d9ffb5f591cfabcc930590ad35d8afac26b2a47fe989333a66fe6e57
  inferred:
    - 新建 tf2 listener 在冻结 source watermark 后等待静态 TF discovery 约 1.7s，消耗 2.0s freshness 预算；模型、mask、深度与世界定位不是本次失败根因
  conclusion: VALID_FAILURE_CUP_POSE_STALE; 按批次规则立即终止 EXP-032～EXP-034，修复后必须从 Linux 场景1重新计数
  evidence: [/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r2-1-task_start]
  decision: FIX_SOURCE_WITH_TDD_THEN_RESTART_NEW_BATCH_FROM_SCENE_1
  next_experiment: BLOCKED_PENDING_EXPLICIT_SOURCE_TRANSFER_AUTHORIZATION
- experiment_id: EXP-032
  status: PLANNED
  prior_experiment: EXP-031
  hypothesis: Linux CUDA 新批次在 v5_no_cup fail-closed
  prediction: TARGET_NOT_FOUND, matching=0, no new /cup_pose, request<=2000ms
  single_variable: keyframe=v5_no_cup; expected=not_found
  lifecycle: FULL_RESTART
  preconditions: [frozen_contract, EXP-031_VALID_success, clean_owned_graph]
  success_criteria: [four_scene_common, TARGET_NOT_FOUND, no_new_or_stale_cup_pose]
  failure_criteria: [four_scene_valid_failure]
  invalid_criteria: [four_scene_common_invalid]
  provenance: {source_commit: 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca, install_overlay: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5, runtime_executable: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place, ros_domain_id: 192, gz_partition: v5-t005-linux-matrix-r2-02-no-cup}
  commands: [{command: exact Task 11 Linux matrix launch recorded before RUNNING, exit_code: PENDING}]
  observed: [PENDING]
  inferred: [NONE]
  conclusion: PENDING
  evidence: [/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r2-2-v5_no_cup]
  decision: PENDING
  next_experiment: EXP-033
- experiment_id: EXP-033
  status: PLANNED
  prior_experiment: EXP-032
  hypothesis: Linux CUDA 新批次在 v5_two_cups 保留两个合格实例并 fail-closed
  prediction: TARGET_AMBIGUOUS, matching=2, 两个IoU>=0.80, no new /cup_pose
  single_variable: keyframe=v5_two_cups; expected=ambiguous
  lifecycle: FULL_RESTART
  preconditions: [frozen_contract, EXP-032_VALID_success, clean_owned_graph]
  success_criteria: [four_scene_common, TARGET_AMBIGUOUS, exactly_two_eligible, no_new_or_stale_cup_pose]
  failure_criteria: [four_scene_valid_failure]
  invalid_criteria: [four_scene_common_invalid]
  provenance: {source_commit: 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca, install_overlay: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5, runtime_executable: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place, ros_domain_id: 193, gz_partition: v5-t005-linux-matrix-r2-03-two-cups}
  commands: [{command: exact Task 11 Linux matrix launch recorded before RUNNING, exit_code: PENDING}]
  observed: [PENDING]
  inferred: [NONE]
  conclusion: PENDING
  evidence: [/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r2-3-v5_two_cups]
  decision: PENDING
  next_experiment: EXP-034
- experiment_id: EXP-034
  status: PLANNED
  prior_experiment: EXP-033
  hypothesis: Linux CUDA 新批次在 v5_cup_near_bottle 保留唯一杯子且 bottle overlap=0
  prediction: matching=1, IoU>=0.80, bottle_overlap=0, world_error<0.01m, new /cup_pose
  single_variable: keyframe=v5_cup_near_bottle; expected=unique_adjacent
  lifecycle: FULL_RESTART
  preconditions: [frozen_contract, EXP-033_VALID_success, clean_owned_graph]
  success_criteria: [four_scene_common, exactly_one_eligible, zero_bottle_overlap, new_source_stamped_cup_pose]
  failure_criteria: [four_scene_valid_failure]
  invalid_criteria: [four_scene_common_invalid]
  provenance: {source_commit: 16d56fc1c129b5bb8b45d201db38dd2ab70e62ca, install_overlay: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5, runtime_executable: /data/work/so101-v5-t005-grounded-sam-task10-16d56fc/install-task10-v5/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place, ros_domain_id: 194, gz_partition: v5-t005-linux-matrix-r2-04-near-bottle}
  commands: [{command: exact Task 11 Linux matrix launch recorded before RUNNING, exit_code: PENDING}]
  observed: [PENDING]
  inferred: [NONE]
  conclusion: PENDING
  evidence: [/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r2-4-v5_cup_near_bottle]
  decision: PENDING
  next_experiment: EXP-017
```

## Task 11 freshness defect correction and authorization boundary

`EXP-031` 证明 detector、SAM mask、Depth、TF 数值定位与 source stamp 本身均达标，但动态
consumer 在同一有效业务运行中返回 `CUP_POSE_STALE`。根因是新建 tf2 listener 在冻结 source
watermark 后才等待静态 TF discovery，约 `1.7 s` 的 discovery 等待占用了固定 `2.0 s`
freshness 预算。修复没有修改模型、bundle、prompt、任何阈值、FP32、offline、device、CPU
fallback、freshness 或 motion policy；它只把生命周期顺序改为：先确认 source stamp 的静态 TF
可发现，再刷新 source watermark，最后订阅并冻结 RGB-D。修复采用 TDD：新增回归测试先得到
`AttributeError` RED，再与两个既有 watermark/transform 测试一起 `3 passed` GREEN；精确源码提交
为 `70675004e3ed66ce6bd5811a8f922565e08f668d`。

由于源码发生变化，EXP-032～EXP-034 以及原计划的 Mac 四场景和双平台 5/5 均不得沿用或计数。
下一批必须以 exact `7067500` 在 Linux 新 checkout/install overlay 通过 package gate 后，从 Linux
场景1重新预写和计数；Linux 4/4 通过后才能预写 Mac 4/4，双端矩阵通过后才能分别预写 5/5。

```yaml
- experiment_id: EXP-035
  status: VALID
  prior_experiment: EXP-031
  hypothesis: 把 TF discovery 放到 source freeze 前可以保留固定 freshness 门禁并覆盖 EXP-031 根因
  prediction: 新回归测试 RED；最小生产修复后该测试与既有 transform/watermark 测试 GREEN；Mac 新 overlay 整包 gate 全绿
  single_variable: RGB-D source freeze 相对静态 TF discovery 的生命周期顺序
  lifecycle: ISOLATED_TEST_AND_BUILD
  preconditions: [EXP-031_VALID_failure, no_threshold_change, no_model_change, owned_processes_NONE]
  commands:
    - {command: pytest focused regression before production helper, exit_code: 1}
    - {command: pytest focused regression plus exact-source transform and output watermark regressions, exit_code: 0}
    - {command: build so101_demo_py into install-task11-tf-discovery then run full package pytest, exit_code: 1}
    - {command: build so101_mujoco_support into the same new overlay then rerun full package pytest, exit_code: 0}
  observed:
    - RED tf-discovery-red.xml errors=0 failures=1; SHA256=02cc02ea53d773679061a4dd19fa61c8f6472aa9190849709d27b396a7b0a7fa
    - GREEN tf-discovery-green.xml tests=3 errors=0 failures=0; SHA256=ae142cad47510de5e86c18f6d21ca27c20a3c421d93bb0b65405cdafd7c5d72f
    - source/test commit=70675004e3ed66ce6bd5811a8f922565e08f668d
    - 首次 Mac full gate 为 1052 passed,1 failed；失败仅因 so101_mujoco_support 仍解析到旧 project overlay；该 gate INVALID，证据保留且不计数
    - 补建 support package 后 Mac exact candidate overlay full gate=1053 passed in 10.75s；JUnit SHA256=f47a1a047a32f3f23a9685e78c23b95dbc81b9d3e6aadfd69ea99e6e2eaee1d3；pytest.log SHA256=9634cde8c59390f4449fc69292d63e2dba00a011676d81fc160d4c3ad68e74b3
  inferred: Mac 源码、demo package、support plugin 与测试 gate 已绑定新 overlay；这不替代 Linux package gate 或任一 Task 11 运行
  conclusion: TDD_AND_MAC_PACKAGE_GATE_PASS; LINUX_EXACT_OVERLAY_NOT_YET_AUTHORIZED
  evidence:
    - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-11/tdd
    - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-11/mac-package
    - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-11/mac-package-r2
    - /Users/matianyi/.codex/worktrees/5b15/moveit-demo/build-task11-tf-discovery
    - /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-task11-tf-discovery
  decision: WAIT_FOR_EXPLICIT_SOURCE_TRANSFER_AUTHORIZATION
  next_experiment: NONE_UNTIL_AUTHORIZED
```

## Checkpoint CP-008

```yaml
checkpoint_id: CP-008
last_valid_experiment: EXP-035
current_hypothesis: exact 7067500 修复了 EXP-031 的 TF discovery/freshness 生命周期缺陷，但必须先在 ai-station 新隔离 overlay 完成 Linux package gate，才可从新 Linux 矩阵场景1重新计数
working_tree_status: source/test fix 已提交为 7067500；Task 11 ledger 与 task-11-report.md 正在结算；本地 Task 10/11 build/install/log 生成目录保留且未删除
owned_processes: NONE；ai-station ROS_DOMAIN_ID=191 独立回读无 node；进程核验只匹配核验命令自身；Mac 未运行 Task 11 stack
preserved_processes: 用户进程、canonical /data/work/ws_moveit 及其用户文档未触碰；未运行真实机械臂
retained_runs:
  - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r2-1-task_start
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-11/tdd
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-11/mac-package
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-11/mac-package-r2
archived_runs: []
deletion_candidates:
  - /data/work/so101-v5-t005-grounded-sam-task11-7067500
  - /Users/matianyi/.codex/worktrees/5b15/moveit-demo/build-task11-tf-discovery
  - /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-task11-tf-discovery
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-11/7067500-full.bundle
  - 既有 CP-006 登记的 Task 10 生成目录
authorization_boundary:
  requested_primary: 允许把 7067500-incremental.bundle 从 Mac 传到 ai-station:/tmp/so101-v5-t005-task11-7067500-incremental.bundle；bundle 为 14 KiB，SHA256=2baf41e16463ab65fa4c60f3a58515224e43bddfd905b12f80dffd21fb3b47c1，只含 16d56fc..7067500 的 Git objects，要求 ai-station 已有 base 16d56fc；不含 datasets、LFS payload、model 或 credentials
  requested_target: 在新目录 /data/work/so101-v5-t005-grounded-sam-task11-7067500-v2 检出 exact 7067500，并生成独立 build-task11/install-task11/log-task11
  fallback_only_if_explicitly_chosen: 17 MiB 完整历史 bundle，SHA256=c0b5e4abc7be7ca1c74e2aaf1c0dd6c27602065922ae29b32b4c972145645524
blocked_reason: 审批系统拒绝向 ai-station 发送完整 Git 历史，并明确禁止使用替代传输规避；尚无源码传输明确授权
next_command: NONE；等待用户明确授权最小增量 bundle 传输与 ai-station 新隔离 checkout
decision: BLOCKED_PENDING_EXPLICIT_SOURCE_TRANSFER_AUTHORIZATION
```

## Task 11 exact 7067500 deployment and replacement acceptance plan

用户明确授权把最小增量 bundle 传到 ai-station。Mac 与远端文件 SHA256 均为
`2baf41e16463ab65fa4c60f3a58515224e43bddfd905b12f80dffd21fb3b47c1`；bundle requires
`16d56fc1c129b5bb8b45d201db38dd2ab70e62ca`，advertises
`70675004e3ed66ce6bd5811a8f922565e08f668d`。它不含 datasets、LFS payload、模型或凭据。
ai-station 新隔离 checkout 为
`/data/work/so101-v5-t005-grounded-sam-task11-7067500-v2`，main HEAD exact `7067500`，pinned
submodule exact `71bc9346cf93d6227a6678fcacf63f3e18acfcba`，tracked/index clean。正式 runtime overlay
固定为 `install-task11-v5`；前三次 build 因 build-time Python/header provenance 失败，v4 虽构建
成功但 entrypoint 为 system Python，均为 `INVALID` 且保留。v5 由固定 task venv Python 启动
colcon，两个包构建成功，entrypoint shebang 指向 task venv。

首次 v5 full gate 因错误设置 `SO101_DEMO_EXPECTED_PREFIX` 且新 clone 尚未初始化 gitlink，得到
`1048 passed, 5 failed`，属于验收环境 `INVALID`。初始化 exact gitlink 并移除错误变量后，新证据
目录的 full gate 为 `1053 tests, 0 errors, 0 failures`；JUnit SHA256
`645b36a0dfb35818e6e81125db2fb371f25479398464216cc30d6199ab185967`，pytest log SHA256
`06abb7149af5939d746cab67a1c8fcc166389bce2754afad9b8265835e43c4a2`。

下列 replacement experiments 在任何 runtime 启动前统一预写。所有运行固定 exact `7067500`、
bundle manifest `838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3`、prompt
`plastic cup.`、box/text/duplicate/max/SAM/min-pixels/max-ratio/target-confidence 阈值
`0.35/0.25/0.85/16/0.75/64/0.50/0.50`、FP32、offline、CPU fallback `false`、freshness
`2.0 s`、`sim_speed_factor=1.0`。Linux device=`cuda`；Mac device=`mps`。每项都有独立
request/session/domain/partition/evidence path，生命周期为 `FULL_RESTART`，绝不并行 stack。

```yaml
replacement_common:
  four_scene_success: warmed_request_ms<=2000 AND all_source_stamps_exact AND model_runtime_provenance_exact AND cleanup_clean AND scene_specific_success
  four_scene_invalid: missing_or_mismatched_payload OR observer_or_truth_missing OR provenance_mismatch OR stale_input_before_inference OR infrastructure_failure
  four_scene_stop: 任一 VALID failure 或 INVALID 立即终止平台批次；修复后从该平台场景1重新计数；INVALID 不进分母
  pick_success: payload_exact AND semantic_unique_plastic_cup AND mask_depth_tf_source_stamp_exact AND consumer_stamp_exact AND bilateral_grasp AND micro_lift AND place_detach_world_sync_table_support AND final_xy_tilt_gate AND visual_gate AND provenance_exact AND cleanup_clean
  pick_invalid: missing_required_evidence OR provenance_mismatch OR infrastructure_failure OR observer_not_bound OR stale_input_before_inference
  pick_stop: 任一 VALID failure 或 INVALID 立即终止平台5轮批次；修复后从第1轮重新计数；INVALID 不进分母
  no_truth_or_color_dispatch: true
  no_highest_score_force_selection: true
  task10_smokes_count: false
replacement_experiments:
  - {experiment_id: EXP-036, status: INVALID, platform: linux, phase: four_scene, order: 1, scene: task_start, expected: exactly_one_eligible_and_source_stamped_pose, truth_iou: '>=0.80', pose_error_m: '<0.01', request_id: linux-matrix-r3-1-task_start, session_id: linux-matrix-r3-1-task_start, ros_domain_id: 201, partition: v5-t005-linux-matrix-r3-01-task-start, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r3-1-task_start, prior: EXP-035, next: EXP-037}
  - {experiment_id: EXP-037, status: PLANNED, platform: linux, phase: four_scene, order: 2, scene: v5_no_cup, expected: TARGET_NOT_FOUND_and_no_new_or_stale_pose, request_id: linux-matrix-r3-2-v5_no_cup, session_id: linux-matrix-r3-2-v5_no_cup, ros_domain_id: 202, partition: v5-t005-linux-matrix-r3-02-no-cup, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r3-2-v5_no_cup, prior: EXP-036_VALID_success, next: EXP-038}
  - {experiment_id: EXP-038, status: PLANNED, platform: linux, phase: four_scene, order: 3, scene: v5_two_cups, expected: TARGET_AMBIGUOUS_exactly_two_eligible_and_no_new_or_stale_pose, truth_iou_each: '>=0.80', request_id: linux-matrix-r3-3-v5_two_cups, session_id: linux-matrix-r3-3-v5_two_cups, ros_domain_id: 203, partition: v5-t005-linux-matrix-r3-03-two-cups, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r3-3-v5_two_cups, prior: EXP-037_VALID_success, next: EXP-039}
  - {experiment_id: EXP-039, status: PLANNED, platform: linux, phase: four_scene, order: 4, scene: v5_cup_near_bottle, expected: unique_cup_mask_zero_bottle_pixels_and_source_stamped_pose, truth_iou: '>=0.80', pose_error_m: '<0.01', bottle_overlap_pixels: 0, request_id: linux-matrix-r3-4-v5_cup_near_bottle, session_id: linux-matrix-r3-4-v5_cup_near_bottle, ros_domain_id: 204, partition: v5-t005-linux-matrix-r3-04-near-bottle, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r3-4-v5_cup_near_bottle, prior: EXP-038_VALID_success, next: EXP-040}
  - {experiment_id: EXP-040, status: PLANNED, platform: mac, phase: four_scene, order: 1, scene: task_start, expected: exactly_one_eligible_and_source_stamped_pose, truth_iou: '>=0.80', pose_error_m: '<0.01', headless: false, request_id: mac-matrix-r3-1-task_start, session_id: mac-matrix-r3-1-task_start, ros_domain_id: 205, partition: v5-t005-mac-matrix-r3-01-task-start, evidence: /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-11/perception-matrix/mac/mac-matrix-r3-1-task_start, prior: EXP-057_VALID_success, next: EXP-041}
  - {experiment_id: EXP-041, status: PLANNED, platform: mac, phase: four_scene, order: 2, scene: v5_no_cup, expected: TARGET_NOT_FOUND_and_no_new_or_stale_pose, headless: false, request_id: mac-matrix-r3-2-v5_no_cup, session_id: mac-matrix-r3-2-v5_no_cup, ros_domain_id: 206, partition: v5-t005-mac-matrix-r3-02-no-cup, evidence: /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-11/perception-matrix/mac/mac-matrix-r3-2-v5_no_cup, prior: EXP-040_VALID_success, next: EXP-042}
  - {experiment_id: EXP-042, status: PLANNED, platform: mac, phase: four_scene, order: 3, scene: v5_two_cups, expected: TARGET_AMBIGUOUS_exactly_two_eligible_and_no_new_or_stale_pose, truth_iou_each: '>=0.80', headless: false, request_id: mac-matrix-r3-3-v5_two_cups, session_id: mac-matrix-r3-3-v5_two_cups, ros_domain_id: 207, partition: v5-t005-mac-matrix-r3-03-two-cups, evidence: /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-11/perception-matrix/mac/mac-matrix-r3-3-v5_two_cups, prior: EXP-041_VALID_success, next: EXP-043}
  - {experiment_id: EXP-043, status: PLANNED, platform: mac, phase: four_scene, order: 4, scene: v5_cup_near_bottle, expected: unique_cup_mask_zero_bottle_pixels_and_source_stamped_pose, truth_iou: '>=0.80', pose_error_m: '<0.01', bottle_overlap_pixels: 0, headless: false, request_id: mac-matrix-r3-4-v5_cup_near_bottle, session_id: mac-matrix-r3-4-v5_cup_near_bottle, ros_domain_id: 208, partition: v5-t005-mac-matrix-r3-04-near-bottle, evidence: /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-11/perception-matrix/mac/mac-matrix-r3-4-v5_cup_near_bottle, prior: EXP-042_VALID_success, next: EXP-044}
  - {experiment_id: EXP-044, status: PLANNED, platform: linux, phase: pick_5_of_5, run: 1, scene: task_start, request_id: linux-pick-final-r2-1, session_id: linux-pick-final-r2-1, ros_domain_id: 211, partition: v5-t005-linux-pick-final-r2-01, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/pick-place/linux/linux-pick-final-r2-1, prior: EXP-043_VALID_success, next: EXP-045}
  - {experiment_id: EXP-045, status: PLANNED, platform: linux, phase: pick_5_of_5, run: 2, scene: task_start, request_id: linux-pick-final-r2-2, session_id: linux-pick-final-r2-2, ros_domain_id: 212, partition: v5-t005-linux-pick-final-r2-02, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/pick-place/linux/linux-pick-final-r2-2, prior: EXP-044_VALID_success, next: EXP-046}
  - {experiment_id: EXP-046, status: PLANNED, platform: linux, phase: pick_5_of_5, run: 3, scene: task_start, request_id: linux-pick-final-r2-3, session_id: linux-pick-final-r2-3, ros_domain_id: 213, partition: v5-t005-linux-pick-final-r2-03, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/pick-place/linux/linux-pick-final-r2-3, prior: EXP-045_VALID_success, next: EXP-047}
  - {experiment_id: EXP-047, status: PLANNED, platform: linux, phase: pick_5_of_5, run: 4, scene: task_start, request_id: linux-pick-final-r2-4, session_id: linux-pick-final-r2-4, ros_domain_id: 214, partition: v5-t005-linux-pick-final-r2-04, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/pick-place/linux/linux-pick-final-r2-4, prior: EXP-046_VALID_success, next: EXP-048}
  - {experiment_id: EXP-048, status: PLANNED, platform: linux, phase: pick_5_of_5, run: 5, scene: task_start, request_id: linux-pick-final-r2-5, session_id: linux-pick-final-r2-5, ros_domain_id: 215, partition: v5-t005-linux-pick-final-r2-05, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/pick-place/linux/linux-pick-final-r2-5, prior: EXP-047_VALID_success, next: EXP-049}
  - {experiment_id: EXP-049, status: PLANNED, platform: mac, phase: pick_5_of_5, run: 1, scene: task_start, headless: false, request_id: mac-pick-final-r2-1, session_id: mac-pick-final-r2-1, ros_domain_id: 221, partition: v5-t005-mac-pick-final-r2-01, evidence: /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-11/pick-place/mac/mac-pick-final-r2-1, prior: EXP-048_VALID_success, next: EXP-050}
  - {experiment_id: EXP-050, status: PLANNED, platform: mac, phase: pick_5_of_5, run: 2, scene: task_start, headless: false, request_id: mac-pick-final-r2-2, session_id: mac-pick-final-r2-2, ros_domain_id: 222, partition: v5-t005-mac-pick-final-r2-02, evidence: /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-11/pick-place/mac/mac-pick-final-r2-2, prior: EXP-049_VALID_success, next: EXP-051}
  - {experiment_id: EXP-051, status: PLANNED, platform: mac, phase: pick_5_of_5, run: 3, scene: task_start, headless: false, request_id: mac-pick-final-r2-3, session_id: mac-pick-final-r2-3, ros_domain_id: 223, partition: v5-t005-mac-pick-final-r2-03, evidence: /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-11/pick-place/mac/mac-pick-final-r2-3, prior: EXP-050_VALID_success, next: EXP-052}
  - {experiment_id: EXP-052, status: PLANNED, platform: mac, phase: pick_5_of_5, run: 4, scene: task_start, headless: false, request_id: mac-pick-final-r2-4, session_id: mac-pick-final-r2-4, ros_domain_id: 224, partition: v5-t005-mac-pick-final-r2-04, evidence: /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-11/pick-place/mac/mac-pick-final-r2-4, prior: EXP-051_VALID_success, next: EXP-053}
  - {experiment_id: EXP-053, status: PLANNED, platform: mac, phase: pick_5_of_5, run: 5, scene: task_start, headless: false, request_id: mac-pick-final-r2-5, session_id: mac-pick-final-r2-5, ros_domain_id: 225, partition: v5-t005-mac-pick-final-r2-05, evidence: /tmp/so101-debug-v5-t005-grounded-sam-20260901/task-11/pick-place/mac/mac-pick-final-r2-5, prior: EXP-052_VALID_success, next: FINAL_PACKAGE_GATES}
```

## Checkpoint CP-009

```yaml
checkpoint_id: CP-009
last_valid_experiment: EXP-035
current_hypothesis: exact 7067500 v5 overlay 已通过 Linux package gate，可以从 EXP-036 全新 Linux 场景1开始验证 freshness 修复
working_tree_status: 本地 source/test fix=7067500，ledger prior checkpoint=9091d9d；远端 main/submodule tracked clean，v1-v4 invalid build outputs 与 v5 qualification outputs 均未删除
owned_processes: NONE；package gate 未启动 ROS/MuJoCo runtime；Linux matrix scene1 尚未启动
retained_runs:
  - /tmp/so101-v5-t005-task11-tools/linux-package-7067500-v5
  - /tmp/so101-v5-t005-task11-tools/linux-package-7067500-v5-r2
  - /data/work/so101-v5-t005-grounded-sam-task11-7067500-v2/build-task11-v5
  - /data/work/so101-v5-t005-grounded-sam-task11-7067500-v2/install-task11-v5
  - /data/work/so101-v5-t005-grounded-sam-task11-7067500-v2/log-task11-v5
archived_runs: []
deletion_candidates:
  - /data/work/so101-v5-t005-grounded-sam-task11-7067500-v2/build-task11
  - /data/work/so101-v5-t005-grounded-sam-task11-7067500-v2/install-task11
  - /data/work/so101-v5-t005-grounded-sam-task11-7067500-v2/log-task11
  - /data/work/so101-v5-t005-grounded-sam-task11-7067500-v2/build-task11-v2
  - /data/work/so101-v5-t005-grounded-sam-task11-7067500-v2/install-task11-v2
  - /data/work/so101-v5-t005-grounded-sam-task11-7067500-v2/log-task11-v2
  - /data/work/so101-v5-t005-grounded-sam-task11-7067500-v2/build-task11-v3
  - /data/work/so101-v5-t005-grounded-sam-task11-7067500-v2/install-task11-v3
  - /data/work/so101-v5-t005-grounded-sam-task11-7067500-v2/log-task11-v3
  - /data/work/so101-v5-t005-grounded-sam-task11-7067500-v2/build-task11-v4
  - /data/work/so101-v5-t005-grounded-sam-task11-7067500-v2/install-task11-v4
  - /data/work/so101-v5-t005-grounded-sam-task11-7067500-v2/log-task11-v4
next_command: 将 EXP-036 更新为 RUNNING；确认 domain 201/partition/session 无 owned graph 后，以唯一 stack 启动 Linux task_start
decision: RUN_EXP_036_ONLY
```

## Task 11 Linux matrix r3 invalidation and r4 replacement

EXP-036 的生产 runtime、observer 与 simulation truth 均正常完成，launch rc=0、dynamic
PickPlace `status=DONE`；perception 为 `status=OK`、raw=3、eligible=1、request `268.912224 ms`、
inference `180.981874 ms`、source/consumer stamp `11840000000`。retained mask 的只读审计得到
truth IoU `0.9863858753456711`，world pose error `0.0005067077374595199 m`。但验收 validator
把 observer artifact 写成不存在的 `observer/source-rgb.png`，实际文件是
`observer/observed-source-rgb.png`，因此没有生成 acceptance；cleanup 又通过默认 ROS2 CLI daemon
读到了已经退出的陈旧 MoveIt graph。该轮满足 `missing_required_evidence`，判为 `INVALID`，不进
分母，r3 批次 EXP-037～EXP-039 全部不得运行。

验收工具只改两个点：读取实际 observer artifact 名；设置 `ROS2CLI_DISABLE_DAEMON=1`。没有修改
生产 source/config、模型、bundle、prompt、阈值、device、freshness、motion 或场景。修复后独立
回读 domain 201 无 node，session/partition 与通用 runtime pattern 均无进程。Linux 新批次使用
全新 request/session/domain/partition/evidence path，从场景1重新计数。

```yaml
linux_matrix_r4_replacement:
  common: replacement_common.four_scene_success / replacement_common.four_scene_invalid / replacement_common.four_scene_stop
  source_commit: 70675004e3ed66ce6bd5811a8f922565e08f668d
  install_overlay: /data/work/so101-v5-t005-grounded-sam-task11-7067500-v2/install-task11-v5
  runtime_device: cuda
  lifecycle: FULL_RESTART
  experiments:
    - {experiment_id: EXP-054, status: PLANNED, order: 1, scene: task_start, expected: exactly_one_eligible_and_source_stamped_pose, truth_iou: '>=0.80', pose_error_m: '<0.01', request_id: linux-matrix-r4-1-task_start, session_id: linux-matrix-r4-1-task_start, ros_domain_id: 231, partition: v5-t005-linux-matrix-r4-01-task-start, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r4-1-task_start, prior: EXP-036_INVALID_and_clean_owned_graph, next: EXP-055}
    - {experiment_id: EXP-055, status: PLANNED, order: 2, scene: v5_no_cup, expected: TARGET_NOT_FOUND_and_no_new_or_stale_pose, request_id: linux-matrix-r4-2-v5_no_cup, session_id: linux-matrix-r4-2-v5_no_cup, ros_domain_id: 232, partition: v5-t005-linux-matrix-r4-02-no-cup, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r4-2-v5_no_cup, prior: EXP-054_VALID_success, next: EXP-056}
    - {experiment_id: EXP-056, status: PLANNED, order: 3, scene: v5_two_cups, expected: TARGET_AMBIGUOUS_exactly_two_eligible_and_no_new_or_stale_pose, truth_iou_each: '>=0.80', request_id: linux-matrix-r4-3-v5_two_cups, session_id: linux-matrix-r4-3-v5_two_cups, ros_domain_id: 233, partition: v5-t005-linux-matrix-r4-03-two-cups, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r4-3-v5_two_cups, prior: EXP-055_VALID_success, next: EXP-057}
    - {experiment_id: EXP-057, status: PLANNED, order: 4, scene: v5_cup_near_bottle, expected: unique_cup_mask_zero_bottle_pixels_and_source_stamped_pose, truth_iou: '>=0.80', pose_error_m: '<0.01', bottle_overlap_pixels: 0, request_id: linux-matrix-r4-4-v5_cup_near_bottle, session_id: linux-matrix-r4-4-v5_cup_near_bottle, ros_domain_id: 234, partition: v5-t005-linux-matrix-r4-04-near-bottle, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r4-4-v5_cup_near_bottle, prior: EXP-056_VALID_success, next: EXP-040}
```

## Checkpoint CP-010

```yaml
checkpoint_id: CP-010
last_valid_experiment: EXP-035
last_invalid_experiment: EXP-036
current_hypothesis: EXP-036 已显示 freshness 修复后的业务链路可完成，但必须用已修正的 observer artifact/daemon-free cleanup 在 EXP-054 从场景1生成完整 acceptance 才能计数
working_tree_status: 生产 HEAD 与 install overlay 未变；仅 /tmp Task 11 validator/runner 修改；ledger 记录 r3 INVALID 并预写 r4
owned_processes: NONE；ROS2CLI_DISABLE_DAEMON=1 独立回读 domain 201 无 node；session/partition 与 runtime pattern 无进程
retained_runs:
  - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r3-1-task_start
archived_runs: []
deletion_candidates: [CP-009 已登记的 invalid build/test outputs]
next_command: 将 EXP-054 更新为 RUNNING；核验 domain 231/partition/session/root 后启动唯一 Linux task_start stack
decision: RUN_EXP_054_ONLY
```
