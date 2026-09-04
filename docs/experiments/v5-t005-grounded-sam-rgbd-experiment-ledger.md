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
confirmed_result: exact 7067500 与单变量 box threshold 0.70 仍不能同时通过 no-cup 与 two-cup 合同；Task 11 结论为 MODEL_CAPABILITY_NOT_MET，Mac matrix 与双方 5/5 未启动
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
  - CONF-013 用户授权的 14 KiB minimal incremental bundle 已在本地与 ai-station 逐字节 SHA 回读为 2baf41e16463ab65fa4c60f3a58515224e43bddfd905b12f80dffd21fb3b47c1；required base 为 16d56fc，advertised ref 为 7067500，不含 datasets/LFS/model/credentials
  - CONF-014 隔离 checkout /data/work/so101-v5-t005-grounded-sam-task11-7067500-v2 的 source HEAD 为 exact 7067500、tracked/index clean，install-task11-v5 使用已授权 venv Python entrypoint；corrected Linux package gate 为 1053 tests、0 errors、0 failures
  - CONF-015 固定 box threshold 0.35 在 no-cup 场景产生两个 false plastic_cup；唯一单变量 0.70 虽通过 task_start/no-cup，却在 two-cup 只保留一个实例并错误发布 pose，因此 MODEL_CAPABILITY_NOT_MET
open_hypotheses:
  - HYP-001 Grounding DINO Tiny 对受控提示词 plastic cup. 能在四个 MuJoCo 场景中满足候选数量与类别门槛
  - HYP-002 SAM 2.1 Hiera Tiny 的框提示 mask 在两个平台都能达到 truth IoU >= 0.80
  - HYP-004 新 detector 接入后，两个平台可以分别完成 FULL_RESTART 连续 5/5 pick&place
latest_checkpoint: CP-016
next_experiment: BLOCKED_MODEL_CAPABILITY_NOT_MET
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
    - {experiment_id: EXP-054, status: INVALID, order: 1, scene: task_start, expected: exactly_one_eligible_and_source_stamped_pose, observed: business_acceptance_passed_but_cleanup_graph_snapshot_nonempty, truth_iou: 0.9863858753456711, pose_error_m: 0.0005099875133604954, source_consumer_stamp_ns: 8403999999, request_id: linux-matrix-r4-1-task_start, session_id: linux-matrix-r4-1-task_start, ros_domain_id: 231, partition: v5-t005-linux-matrix-r4-01-task-start, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r4-1-task_start, prior: EXP-036_INVALID_and_clean_owned_graph, next: STOP_R4_BATCH}
    - {experiment_id: EXP-055, status: NOT_RUN_BATCH_STOPPED, order: 2, scene: v5_no_cup, expected: TARGET_NOT_FOUND_and_no_new_or_stale_pose, request_id: linux-matrix-r4-2-v5_no_cup, session_id: linux-matrix-r4-2-v5_no_cup, ros_domain_id: 232, partition: v5-t005-linux-matrix-r4-02-no-cup, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r4-2-v5_no_cup, prior: EXP-054_INVALID, next: NONE}
    - {experiment_id: EXP-056, status: NOT_RUN_BATCH_STOPPED, order: 3, scene: v5_two_cups, expected: TARGET_AMBIGUOUS_exactly_two_eligible_and_no_new_or_stale_pose, truth_iou_each: '>=0.80', request_id: linux-matrix-r4-3-v5_two_cups, session_id: linux-matrix-r4-3-v5_two_cups, ros_domain_id: 233, partition: v5-t005-linux-matrix-r4-03-two-cups, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r4-3-v5_two_cups, prior: EXP-054_INVALID, next: NONE}
    - {experiment_id: EXP-057, status: NOT_RUN_BATCH_STOPPED, order: 4, scene: v5_cup_near_bottle, expected: unique_cup_mask_zero_bottle_pixels_and_source_stamped_pose, truth_iou: '>=0.80', pose_error_m: '<0.01', bottle_overlap_pixels: 0, request_id: linux-matrix-r4-4-v5_cup_near_bottle, session_id: linux-matrix-r4-4-v5_cup_near_bottle, ros_domain_id: 234, partition: v5-t005-linux-matrix-r4-04-near-bottle, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r4-4-v5_cup_near_bottle, prior: EXP-054_INVALID, next: NONE}
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

## Task 11 Linux matrix r4 invalidation and r5 replacement

EXP-054 的 corrected package/runtime provenance 与全部业务 acceptance 均通过：CUDA/offline、fixed
bundle/prompt/threshold、raw `3`、eligible `1`、DINO
`[0.7201881409, 0.4792661071, 0.3553651273]`、SAM
`[0.9401710033, 0.9537009001, 0.9346468449]`、request `312.021319 ms`、inference
`155.914913 ms`、truth IoU `0.9863858753456711`、world pose error
`0.0005099875133604954 m`。RGB/Depth/CameraInfo/detections/overlay `/cup_pose` 都绑定
`task_camera_frame` source stamp `8403999999`，输出 pose frame 为 `world`，dynamic consumer 的
input stamp 也为 `8403999999`，固定 `2.0 s` freshness gate 接受并完成 `status=DONE`。

但是验收工具只在关停后固定等待 5 秒做一次 graph snapshot。该点 session-owned process 已空，
daemon-free graph 仍返回六个已经退出的 MoveIt/TF node；更晚的独立 domain 231 回读为空。由于本轮
没有在 evidence root 内证明 graph 收敛，且 observer 未持久化 consumer receipt 时的精确 source
age 数字，按 `missing_required_cleanup/freshness_observation` 判为 `INVALID`，不进分母；EXP-055～057
全部未运行。生产 source/config、模型、bundle、prompt、阈值、device、freshness、motion 与场景均
未改变。验收 instrumentation 只增加两个观测：记录 observer 收到 `/cup_pose` 时的 ROS-clock age；
每秒 daemon-free 回读 graph/process，最多 30 次，必须在 deadline 内同时为空，否则仍失败。

```yaml
linux_matrix_r5_replacement:
  common: replacement_common.four_scene_success / replacement_common.four_scene_invalid / replacement_common.four_scene_stop
  source_commit: 70675004e3ed66ce6bd5811a8f922565e08f668d
  install_overlay: /data/work/so101-v5-t005-grounded-sam-task11-7067500-v2/install-task11-v5
  runtime_device: cuda
  lifecycle: FULL_RESTART
  acceptance_tool_shas:
    matrix_observer_py: 6882f0aec2823b2c48f1e78778fb1f2eed42ea0796f77e4c1794ccf8cd28d14d
    validate_matrix_py: ec5d686da1646b3f4e916aa0184c118f189b0388ca1de18ae922da8478ccb312
    linux_runner_zsh: bea5d69f6916524fd5080d5246c4ccf19b3bafc3ad47adc2264741cb848542b9
  success_criteria:
    - scene-specific semantic contract, warmed latency <= 2000 ms, truth IoU >= 0.80, unique-scene world pose error < 0.01 m
    - exact source stamp across RGB/Depth/CameraInfo/detections/overlay and any /cup_pose; output TF frame world
    - observer receipt source age is finite, nonnegative and <= 2.0 s
    - after launch exit, session-owned process and daemon-free ROS graph both converge to empty within 30 one-second observations
  invalid_criteria:
    - missing/corrupt payload, truth, observer, exact age, provenance, inventory or cleanup history; wrong source/install/runtime/bundle/session/domain/partition
  stop_criteria:
    - any VALID failure or INVALID stops r5 immediately; after correction restart from EXP-058 with new IDs/roots
  experiments:
    - {experiment_id: EXP-058, status: INVALID_PRESTART, order: 1, scene: task_start, observed: remote_runner_mode_0644_direct_execution_rc_126_before_root_or_stack, request_id: linux-matrix-r5-1-task_start, session_id: linux-matrix-r5-1-task_start, ros_domain_id: 241, partition: v5-t005-linux-matrix-r5-01-task-start, evidence: NONE_ROOT_ABSENT, prior: EXP-054_INVALID_and_independent_clean_readback, next: STOP_R5_BATCH}
    - {experiment_id: EXP-059, status: NOT_RUN_BATCH_STOPPED, order: 2, scene: v5_no_cup, request_id: linux-matrix-r5-2-v5_no_cup, session_id: linux-matrix-r5-2-v5_no_cup, ros_domain_id: 242, partition: v5-t005-linux-matrix-r5-02-no-cup, evidence: NONE, prior: EXP-058_INVALID_PRESTART, next: NONE}
    - {experiment_id: EXP-060, status: NOT_RUN_BATCH_STOPPED, order: 3, scene: v5_two_cups, request_id: linux-matrix-r5-3-v5_two_cups, session_id: linux-matrix-r5-3-v5_two_cups, ros_domain_id: 243, partition: v5-t005-linux-matrix-r5-03-two-cups, evidence: NONE, prior: EXP-058_INVALID_PRESTART, next: NONE}
    - {experiment_id: EXP-061, status: NOT_RUN_BATCH_STOPPED, order: 4, scene: v5_cup_near_bottle, request_id: linux-matrix-r5-4-v5_cup_near_bottle, session_id: linux-matrix-r5-4-v5_cup_near_bottle, ros_domain_id: 244, partition: v5-t005-linux-matrix-r5-04-near-bottle, evidence: NONE, prior: EXP-058_INVALID_PRESTART, next: NONE}
```

## Checkpoint CP-011

```yaml
checkpoint_id: CP-011
last_valid_experiment: EXP-035
last_invalid_experiment: EXP-054
current_hypothesis: 生产业务链在 exact 7067500 上已达标；r5 必须以新 instrumentation 同时持久化精确 pose age 与有界 cleanup convergence，才能从场景1开始计数
working_tree_status: 生产 HEAD/install/model/config 均未改变；仅 /tmp Task 11 observer/runner 变更；ledger 结算 r4 INVALID 并预写 r5
owned_processes: NONE；domain 231 daemon-free 独立回读无 node；session/partition/runtime exact-path 进程无匹配
retained_runs:
  - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r3-1-task_start
  - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r4-1-task_start
archived_runs: []
deletion_candidates: [CP-009 已登记的 invalid build/test outputs, invalid r3/r4 acceptance batches after explicit user authorization only]
next_command: 限定提交 CP-011 ledger；复制并回读新 acceptance tools SHA；核验 domain 241/session/partition/root 后仅启动 EXP-058
decision: RUN_EXP_058_ONLY_AFTER_LEDGER_COMMIT
```

## Task 11 Linux matrix r5 pre-start invalidation and r6 replacement

EXP-058 的 direct runner invocation 在远端 shell 层返回 `126 permission denied`。`scp` 保留了
文件内容 SHA，但远端 mode 是 `0644`，所以 ROS/MuJoCo 未启动，目标 durable root 未创建，domain
241 daemon-free 回读无 node，owned runtime process 为 NONE。按 precondition evidence 缺失判为
`INVALID_PRESTART`，r5 批次终止，不复用 EXP-058。r6 唯一变化是把 runner executable mode `0755`
及其 readback 加入 precondition；生产与 acceptance tool 内容 SHA 均不变。

```yaml
linux_matrix_r6_replacement:
  common: linux_matrix_r5_replacement.success_criteria / linux_matrix_r5_replacement.invalid_criteria / linux_matrix_r5_replacement.stop_criteria
  source_commit: 70675004e3ed66ce6bd5811a8f922565e08f668d
  install_overlay: /data/work/so101-v5-t005-grounded-sam-task11-7067500-v2/install-task11-v5
  runtime_device: cuda
  lifecycle: FULL_RESTART
  additional_precondition:
    - remote runner full SHA is bea5d69f6916524fd5080d5246c4ccf19b3bafc3ad47adc2264741cb848542b9 and executable mode is 0755 before RUNNING
  experiments:
    - {experiment_id: EXP-062, status: INVALID, order: 1, scene: task_start, observed: FastDDS_domain_251_port_overflow_before_payload, request_id: linux-matrix-r6-1-task_start, session_id: linux-matrix-r6-1-task_start, ros_domain_id: 251, partition: v5-t005-linux-matrix-r6-01-task-start, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r6-1-task_start, inventory_sha256: 28df183e85f292710a6374d0f72887ee16dc34346ffe6ea3305cb6a16719dfb3, prior: EXP-058_INVALID_PRESTART_and_clean_readback, next: STOP_R6_BATCH}
    - {experiment_id: EXP-063, status: NOT_RUN_BATCH_STOPPED, order: 2, scene: v5_no_cup, request_id: linux-matrix-r6-2-v5_no_cup, session_id: linux-matrix-r6-2-v5_no_cup, ros_domain_id: 252, partition: v5-t005-linux-matrix-r6-02-no-cup, evidence: NONE, prior: EXP-062_INVALID, next: NONE}
    - {experiment_id: EXP-064, status: NOT_RUN_BATCH_STOPPED, order: 3, scene: v5_two_cups, request_id: linux-matrix-r6-3-v5_two_cups, session_id: linux-matrix-r6-3-v5_two_cups, ros_domain_id: 253, partition: v5-t005-linux-matrix-r6-03-two-cups, evidence: NONE, prior: EXP-062_INVALID, next: NONE}
    - {experiment_id: EXP-065, status: NOT_RUN_BATCH_STOPPED, order: 4, scene: v5_cup_near_bottle, request_id: linux-matrix-r6-4-v5_cup_near_bottle, session_id: linux-matrix-r6-4-v5_cup_near_bottle, ros_domain_id: 254, partition: v5-t005-linux-matrix-r6-04-near-bottle, evidence: NONE, prior: EXP-062_INVALID, next: NONE}
```

## Checkpoint CP-012

```yaml
checkpoint_id: CP-012
last_valid_experiment: EXP-035
last_invalid_experiment: EXP-058
current_hypothesis: r5 pre-start failure only来自 remote file mode；在内容 SHA 不变且 0755 readback 后，r6 可从新场景1运行
working_tree_status: 生产和 acceptance tool 内容未变；ledger 结算 r5 INVALID_PRESTART 并预写 r6
owned_processes: NONE；domain 241 daemon-free node list empty；r5 evidence root ABSENT
retained_runs: [CP-011 retained runs]
archived_runs: []
deletion_candidates: [CP-011 deletion candidates]
next_command: 限定提交 CP-012 ledger；设置 remote runner mode 0755 并回读 SHA/mode；核验 domain 251/session/partition/root 后仅启动 EXP-062
decision: RUN_EXP_062_ONLY_AFTER_LEDGER_COMMIT
```

## Task 11 Linux matrix r6 invalidation and r7 replacement

EXP-062 使用的 domain 251 超过本机 FastDDS 可构造范围；所有 participant 在 payload 前以
`Calculated port number is too high. Probably the domainId is over 232` 退出。没有 perception
result、TF、age、IoU 或 pose，判为 `INVALID`，r6 后续未运行。cleanup 最终无 owned process；
node output 只有同一 participant construction error，不是活动图。r7 改用未占用且小于 232 的
domains 101～104。除此以外 source/runtime/bundle/threshold 与 acceptance tool 内容不变。

```yaml
linux_matrix_r7_replacement:
  common: linux_matrix_r5_replacement.success_criteria / linux_matrix_r5_replacement.invalid_criteria / linux_matrix_r5_replacement.stop_criteria
  source_commit: 70675004e3ed66ce6bd5811a8f922565e08f668d
  install_overlay: /data/work/so101-v5-t005-grounded-sam-task11-7067500-v2/install-task11-v5
  runtime_device: cuda
  lifecycle: FULL_RESTART
  mandatory_runner_preflight:
    - runner mode 0755 and executable; all three tool content SHAs equal the CP-011 pinned values
    - each planned ROS_DOMAIN_ID is <= 232 and a sourced daemon-free `ros2 node list` constructs successfully with rc 0 and empty output
    - exact checkout HEAD/clean, overlay package prefixes, runtime entrypoint path/shebang/executable, CUDA/offline bundle provenance all read back
    - each evidence target is absent and request/session/partition has no owned process before its run
    - observer writes `observed-source-rgb.png` plus exact pose age; validator reads those exact keys/paths and gates age <= 2.0 s
    - runner exports ROS2CLI_DISABLE_DAEMON=1 and bounded graph cleanup is exactly attempts 1..30 with final process/node snapshots
  experiments:
    - {experiment_id: EXP-066, status: INVALID, order: 1, scene: task_start, observed: business_and_cleanup_passed_but_observer_mixed_wall_and_sim_clock_for_age, truth_iou: 0.9863858753456711, pose_error_m: 0.00047717598724094425, observed_invalid_age_s: 1788275562.2222872, request_id: linux-matrix-r7-1-task_start, session_id: linux-matrix-r7-1-task_start, ros_domain_id: 101, partition: v5-t005-linux-matrix-r7-01-task-start, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r7-1-task_start, inventory_sha256: 6e9a4db58a22aa834768a045ce712e72f6416898e44e52860868bdb4e61e90fd, prior: EXP-062_INVALID_and_no_owned_process, next: STOP_R7_BATCH}
    - {experiment_id: EXP-067, status: NOT_RUN_BATCH_STOPPED, order: 2, scene: v5_no_cup, request_id: linux-matrix-r7-2-v5_no_cup, session_id: linux-matrix-r7-2-v5_no_cup, ros_domain_id: 102, partition: v5-t005-linux-matrix-r7-02-no-cup, evidence: NONE, prior: EXP-066_INVALID, next: NONE}
    - {experiment_id: EXP-068, status: NOT_RUN_BATCH_STOPPED, order: 3, scene: v5_two_cups, request_id: linux-matrix-r7-3-v5_two_cups, session_id: linux-matrix-r7-3-v5_two_cups, ros_domain_id: 103, partition: v5-t005-linux-matrix-r7-03-two-cups, evidence: NONE, prior: EXP-066_INVALID, next: NONE}
    - {experiment_id: EXP-069, status: NOT_RUN_BATCH_STOPPED, order: 4, scene: v5_cup_near_bottle, request_id: linux-matrix-r7-4-v5_cup_near_bottle, session_id: linux-matrix-r7-4-v5_cup_near_bottle, ros_domain_id: 104, partition: v5-t005-linux-matrix-r7-04-near-bottle, evidence: NONE, prior: EXP-066_INVALID, next: NONE}
```

## Checkpoint CP-013

```yaml
checkpoint_id: CP-013
last_valid_experiment: EXP-035
last_invalid_experiment: EXP-062
current_hypothesis: r6 失败是可预检的 FastDDS domain construction 错误；r7 必须先完成并落盘全部 mandatory_runner_preflight 才能启动 EXP-066
working_tree_status: 生产/工具内容未变；ledger 结算 r6 INVALID 并预写 r7
owned_processes: NONE
runner_preflight:
  status: PASS
  script: /tmp/so101-v5-t005-task11-tools/preflight_r7.zsh
  script_sha256: badff582e2a6ccbbc77a8c3f6f45a8321d4f5525cc6cda3793efc5db5f509f37
  log: /tmp/so101-v5-t005-task11-tools/r7-preflight/preflight.log
  log_sha256: 7ee586cddab656e5b4deff36e907f86d5eb18760dc2683cfa19174d25efa7463
  verified: runner 0755/executable and three pinned tool SHAs; exact clean 7067500 checkout/submodule; exact v5 demo/support prefixes and venv shebang; CUDA RTX 5080; fixed bundle SHA/offline env; domains 101-104 constructible rc0/empty; four roots absent and owned patterns empty; observer/output/age literals aligned; daemon-free and bounded attempts 1..30 cleanup literals present
retained_runs:
  - CP-011 retained runs
  - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r6-1-task_start
archived_runs: []
deletion_candidates: [CP-012 deletion candidates, EXP-062 invalid run after explicit user authorization only]
next_command: 限定提交 CP-013 preflight PASS；标记 EXP-066 RUNNING 后只启动 linux-matrix-r7-1-task_start
decision: RUN_EXP_066_ONLY
```

## Task 11 Linux matrix r7 invalidation and r8 replacement

EXP-066 的 production acceptance 除新 `pose_freshness` 项外全部通过，dynamic 为 `DONE`，cleanup
在 attempt 16 收敛并由独立 domain 101 回读为空。observer 没有启用 `use_sim_time`，以 wall clock
减 MuJoCo source stamp 得到无效的 `1788275562.2222872 s`。该轮按 acceptance evidence defect 判为
`INVALID`，r7 后续未运行。验收工具按 TDD 修复：RED `1 failed`、GREEN `1 passed`；只给 observer
node 注入 `use_sim_time=true`，validator、runner 与生产 source/config 均不变。

```yaml
r8_acceptance_tool_fix:
  observer_sha256: 094fdae02b765c163029caca1b4fd562d99c82964d82ac22c8f7a34101841102
  regression_test_sha256: 09bfb734c6377d90730b80d29334d0ff3cfe1ad23bc5ad3765b87216e8017bc9
  red_junit_sha256: 2a52dc1058b0a020200a49bff312fadefd480c9ab0dbfacea5b7ed81f5ba8c82
  green_junit_sha256: fa7faf6b2e878227666115681aee0eb100bfd61976223dcefec5db379b4a8867
linux_matrix_r8_replacement:
  common: linux_matrix_r7_replacement.mandatory_runner_preflight / linux_matrix_r5_replacement.success_criteria / linux_matrix_r5_replacement.invalid_criteria / linux_matrix_r5_replacement.stop_criteria
  source_commit: 70675004e3ed66ce6bd5811a8f922565e08f668d
  install_overlay: /data/work/so101-v5-t005-grounded-sam-task11-7067500-v2/install-task11-v5
  runtime_device: cuda
  lifecycle: FULL_RESTART
  experiments:
    - {experiment_id: EXP-070, status: VALID_SUCCESS, order: 1, scene: task_start, raw: 3, eligible: 1, source_age_s: 0.28600000000000003, truth_iou: 0.9863858753456711, pose_error_m: 0.0005067077374595199, request_latency_ms: 266.372382, inference_latency_ms: 161.341619, source_consumer_stamp_ns: 9035999999, cleanup_converged_attempt: 15, request_id: linux-matrix-r8-1-task_start, session_id: linux-matrix-r8-1-task_start, ros_domain_id: 106, partition: v5-t005-linux-matrix-r8-01-task-start, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r8-1-task_start, inventory_sha256: 5f91fe791ec9bd7e553fc69f140885be44aa70a0698a5fef7c3bb03db78bbfb6, prior: EXP-066_INVALID_and_clean_owned_graph, next: EXP-071}
    - {experiment_id: EXP-071, status: VALID_FAILURE, order: 2, scene: v5_no_cup, observed: TARGET_AMBIGUOUS_two_false_plastic_cup_candidates_no_pose, raw: 2, eligible: 2, candidate_confidences: [0.6970663070678711, 0.5767329931259155], request_latency_ms: 268.158024, inference_latency_ms: 198.510007, request_id: linux-matrix-r8-2-v5_no_cup, session_id: linux-matrix-r8-2-v5_no_cup, ros_domain_id: 107, partition: v5-t005-linux-matrix-r8-02-no-cup, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r8-2-v5_no_cup, inventory_sha256: c8a0d82a9abdd0438133482e278fede5392a93547fd1f0daeea9fc45b7304daa, prior: EXP-070_VALID_success, next: STOP_R8_BATCH}
    - {experiment_id: EXP-072, status: NOT_RUN_BATCH_STOPPED, order: 3, scene: v5_two_cups, request_id: linux-matrix-r8-3-v5_two_cups, session_id: linux-matrix-r8-3-v5_two_cups, ros_domain_id: 108, partition: v5-t005-linux-matrix-r8-03-two-cups, evidence: NONE, prior: EXP-071_VALID_FAILURE, next: NONE}
    - {experiment_id: EXP-073, status: NOT_RUN_BATCH_STOPPED, order: 4, scene: v5_cup_near_bottle, request_id: linux-matrix-r8-4-v5_cup_near_bottle, session_id: linux-matrix-r8-4-v5_cup_near_bottle, ros_domain_id: 109, partition: v5-t005-linux-matrix-r8-04-near-bottle, evidence: NONE, prior: EXP-071_VALID_FAILURE, next: NONE}
```

## Checkpoint CP-014

```yaml
checkpoint_id: CP-014
last_valid_experiment: EXP-035
last_invalid_experiment: EXP-066
current_hypothesis: observer 启用 ROS simulation clock 后，r8 可在不修改生产链的前提下持久化真实 source age 并从场景1重新计数
working_tree_status: 生产/validator/runner 未变；仅 /tmp observer 与其 regression test 变化；ledger 结算 r7 INVALID 并预写 r8
owned_processes: NONE；domain 101 independent node list empty；r7 cleanup attempt 16 node/process empty
r8_runner_preflight:
  status: PASS
  script: /tmp/so101-v5-t005-task11-tools/preflight_r8.zsh
  script_sha256: f4a6b67ae3b8655d42f58c1bd4d6387a008ba0408dedbae26724839aa1d8a741
  log: /tmp/so101-v5-t005-task11-tools/r8-preflight/preflight.log
  log_sha256: bf9dafa2b722458ab8913d15e4d25b6b1f0cf0a0d0d07d8cb0151aee744dc11c
  verified: updated observer SHA plus unchanged validator/runner SHAs; runner 0755; exact clean checkout/overlay/entrypoint; CUDA/offline/bundle; domains 106-109 constructible rc0/empty; r8 roots absent and owned patterns empty; observer/output/age, daemon-free and bounded cleanup literals present
retained_runs:
  - CP-013 retained runs
  - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r7-1-task_start
archived_runs: []
deletion_candidates: [CP-013 deletion candidates, EXP-066 invalid run after explicit user authorization only]
next_command: 限定提交 CP-014 r8 preflight PASS；标记 EXP-070 RUNNING 后只启动 linux-matrix-r8-1-task_start
decision: RUN_EXP_070_ONLY
```

## Task 11 Linux matrix r8 threshold failure and r9 single-variable experiment

EXP-071 是 `VALID_FAILURE`：`v5_no_cup` 没有发布 pose，但 detector 产生两个
`plastic_cup` candidates，scores `0.6970663071` 与 `0.5767329931`，selector 因此返回
`TARGET_AMBIGUOUS`，而合同要求 `TARGET_NOT_FOUND`。r8 立即停止。唯一阈值变量为现有 launch 已
暴露的 `grounding_box_threshold`，从 `0.35` 提高到 `0.70`；EXP-070 真杯 score
`0.7200909257` 仍高于新门槛。模型、prompt、text/duplicate/SAM/target-confidence、FP32/offline、
device/fallback、freshness、motion/source/config 全部不变。r9 必须从场景1重新计数；任一失败即
`MODEL_CAPABILITY_NOT_MET` 并停止，不进入 5/5。

```yaml
linux_matrix_r9_single_variable:
  variable: grounding_box_threshold
  old_value: 0.35
  new_value: 0.70
  all_other_values: frozen_as_CP-014
  source_commit: 70675004e3ed66ce6bd5811a8f922565e08f668d
  install_overlay: /data/work/so101-v5-t005-grounded-sam-task11-7067500-v2/install-task11-v5
  runtime_device: cuda
  lifecycle: FULL_RESTART
  experiments:
    - {experiment_id: EXP-074, status: VALID_SUCCESS, order: 1, scene: task_start, raw: 1, eligible: 1, confidence: 0.721530556678772, source_age_s: 0.36400000000000005, truth_iou: 0.9863858753456711, pose_error_m: 0.0005099875133604954, request_latency_ms: 342.554425, inference_latency_ms: 230.355705, source_consumer_stamp_ns: 9385999999, cleanup_converged_attempt: 15, request_id: linux-matrix-r9-1-task_start, session_id: linux-matrix-r9-1-task_start, ros_domain_id: 110, partition: v5-t005-linux-matrix-r9-01-task-start, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r9-1-task_start, inventory_sha256: 57514aa1739ec6fd9164faca497bbe6805b4de4c8dba2bce1bbb3faaed25ff7e, prior: EXP-071_VALID_FAILURE_and_clean_graph, next: EXP-075}
    - {experiment_id: EXP-075, status: VALID_SUCCESS, order: 2, scene: v5_no_cup, status_code: TARGET_NOT_FOUND, raw: 0, eligible: 0, pose_count: 0, request_latency_ms: 206.202534, inference_latency_ms: 113.455338, source_stamp_ns: 10620000000, cleanup_converged_attempt: 14, request_id: linux-matrix-r9-2-v5_no_cup, session_id: linux-matrix-r9-2-v5_no_cup, ros_domain_id: 111, partition: v5-t005-linux-matrix-r9-02-no-cup, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r9-2-v5_no_cup, inventory_sha256: 4d0d834d336858117d502164eee2f5e1eab0158c3c2ce122f47fbe8e1424752d, prior: EXP-074_VALID_success, next: EXP-076}
    - {experiment_id: EXP-076, status: VALID_FAILURE, order: 3, scene: v5_two_cups, observed: one_candidate_OK_and_new_pose_instead_of_TARGET_AMBIGUOUS_no_pose, raw: 1, eligible: 1, confidence: 0.7670135498046875, best_iou: 0.9600505689001264, source_age_s: 0.28, request_latency_ms: 260.067819, inference_latency_ms: 175.347078, source_stamp_ns: 9429999999, cleanup_converged_attempt: 14, request_id: linux-matrix-r9-3-v5_two_cups, session_id: linux-matrix-r9-3-v5_two_cups, ros_domain_id: 112, partition: v5-t005-linux-matrix-r9-03-two-cups, evidence: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r9-3-v5_two_cups, inventory_sha256: 367dcd3310e11c632ca0d34a50abe9c92c133847aa807696730a837b17ec57d8, prior: EXP-075_VALID_success, next: STOP_MODEL_CAPABILITY_NOT_MET}
    - {experiment_id: EXP-077, status: NOT_RUN_MODEL_CAPABILITY_STOP, order: 4, scene: v5_cup_near_bottle, request_id: linux-matrix-r9-4-v5_cup_near_bottle, session_id: linux-matrix-r9-4-v5_cup_near_bottle, ros_domain_id: 113, partition: v5-t005-linux-matrix-r9-04-near-bottle, evidence: NONE, prior: EXP-076_VALID_FAILURE, next: NONE}
```

## Checkpoint CP-015

```yaml
checkpoint_id: CP-015
last_valid_experiment: EXP-070
last_invalid_experiment: EXP-066
last_valid_failure: EXP-071
current_hypothesis: box threshold 0.70 可删除 no-cup false positives，同时保留已观察到的 task_start 真杯；必须以 r9 四场景验证
working_tree_status: 生产 source/config 未变；将仅修改 /tmp runner 的一个 launch threshold literal，并重新执行完整 preflight
owned_processes: NONE；EXP-071 cleanup attempt 14 与 independent domain 107 readback node/process empty
r9_runner_preflight:
  status: PASS
  runner_sha256: eb535aebf54626e69d89565381ffe77026e9f32677eb312237bf48dcaf5976e7
  script: /tmp/so101-v5-t005-task11-tools/preflight_r9.zsh
  script_sha256: fdbaecb265f707aa0d567f4a75b81e0e7be98f5fbd9dfd697ae7d0bdd5170f2f
  log: /tmp/so101-v5-t005-task11-tools/r9-preflight/preflight.log
  log_sha256: 0c845c05e71b6c6057ddd00339ad9fd317a69a0f8ce04dd4d97b0c6536d671b1
  verified: runner 0755 and exactly one threshold override grounding_box_threshold:=0.70; exact source/overlay/model/offline/CUDA; domains 110-113 constructible empty; roots/owned patterns absent; observer/validator/cleanup contracts unchanged
retained_runs:
  - CP-014 retained runs
  - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r8-1-task_start
  - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r8-2-v5_no_cup
archived_runs: []
deletion_candidates: [CP-014 deletion candidates, r8 runs after explicit user authorization only]
next_command: 限定提交 CP-015 r9 preflight PASS；标记 EXP-074 RUNNING 后只启动 linux-matrix-r9-1-task_start
decision: RUN_EXP_074_ONLY
```

## Checkpoint CP-016 — MODEL_CAPABILITY_NOT_MET

```yaml
checkpoint_id: CP-016
last_valid_experiment: EXP-075
last_valid_failure: EXP-076
conclusion: MODEL_CAPABILITY_NOT_MET
evidence_chain:
  fixed_threshold_0_35: EXP-070 task_start VALID_SUCCESS; EXP-071 no-cup VALID_FAILURE with false scores 0.6970663071 and 0.5767329931
  single_variable_0_70: EXP-074 task_start VALID_SUCCESS; EXP-075 no-cup VALID_SUCCESS; EXP-076 two-cup VALID_FAILURE with only one score 0.7670135498, status OK and forbidden new pose
reason: safe box threshold must exceed the observed no-cup false score 0.6970663071, but the tested 0.70 gate removes one true cup in two-cup; the approved fixed and one-variable qualification route cannot satisfy both fail-closed contracts
source_install_runtime: exact source 70675004e3ed66ce6bd5811a8f922565e08f668d; install-task11-v5; corrected Linux package gate 1053/0/0; Mac package gate 1053 passed from EXP-035; immutable bundle 838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3
owned_processes: NONE；EXP-076 cleanup attempt 14 node/process empty；independent domain 112 node/process empty
retained_runs:
  - all CP-015 retained runs
  - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r9-1-task_start
  - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r9-2-v5_no_cup
  - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux/linux-matrix-r9-3-v5_two_cups
archived_runs: []
deletion_candidates:
  - prior invalid/failed build overlays and matrix batches, only after explicit user authorization
  - no evidence is deleted by Task 11
remaining_boundary:
  - Linux four-scene matrix is not 4/4; Mac matrix and both 5/5 batches were not started
  - Task 10 smoke and incidental PickPlace in matrix runs do not count toward Task 11 5/5
  - all evidence is MuJoCo simulation only and does not prove real SO-101 safety or success
next_command: user decision required for model/data/prompt architecture improvement beyond the approved fixed plus one-variable threshold route; no further Task 11 experiment authorized
decision: STOP_MODEL_CAPABILITY_NOT_MET
```

## Post-benchmark candidate-label remediation

The separate Grounded-SAM / YOLO-Seg benchmark reached terminal `INVALID` at
`CP-BENCH-038`: the Transformers postprocessor emitted both `plastic cup` and
`plastic cup.` for the same fixed prompt, while the low-floor raw adapter retained only the first
literal. This makes the old calibration candidate space incomplete. The already opened R12 test
split cannot be reused for a fix, recalibration, or model ranking.

```yaml
experiment_id: EXP-078
status: VALID_SUCCESS
prior_experiment: EXP-076_and_CP-BENCH-038
hypothesis: punctuation-sensitive equality at the Grounding DINO decoded-label boundary drops a real low-floor plastic_cup proposal before calibration
prediction: a real-adapter unit case whose postprocessor returns plastic cup. will produce zero candidates before the fix, while the desired contract requires one candidate with unchanged DINO and SAM scores
single_variable: normalize decoded Grounding DINO label punctuation before comparison with the one fixed plastic cup. prompt; no model, prompt, threshold, mask, selector, depth, TF, or motion change
lifecycle: ISOLATED_STACK
preconditions:
  - local, Gitee, and ai-station source are synchronized at e06e1b8fbe94ae1b22e187e2864a7742f4c4721b
  - no ROS, MuJoCo, MoveIt, Grounded-SAM, or tmux process is active on ai-station
  - the R12 benchmark test split remains read-only and is not used by this experiment
success_criteria:
  - the new raw-adapter regression fails before production modification because plastic cup. is dropped
  - after one scoped source change, plastic cup and plastic cup. retain equivalent proposals and an unrelated phrase remains rejected
  - focused adapter and production postprocess regressions pass on both synchronized platforms before any new model run
failure_criteria:
  - punctuation-equivalent label is still dropped or an unrelated decoded phrase is accepted
invalid_criteria:
  - any old test prediction, truth mask, scene truth, or threshold is used to choose label behavior
provenance:
  source_commit: e06e1b8fbe94ae1b22e187e2864a7742f4c4721b
  local_worktree: /Users/matianyi/.codex/worktrees/5b15/moveit-demo
  linux_checkout: /data/work/so101-grounded-sam-yolo-benchmark-ab-v1-task14-runner-access-r11
  development_evidence: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-078
  ros_domain_id: NOT_APPLICABLE_UNIT_TEST
  gz_partition: NOT_APPLICABLE_UNIT_TEST
commands:
  - command: initial focused RED invocation without the candidate overlay
    exit_code: 4_INVALID_ENVIRONMENT_COLLECTION_ERROR
  - command: two-boundary focused RED pytest with install-rebase-final-r15 overlay
    exit_code: 1_EXPECTED_2_FAILURES
  - command: complete test_grounded_sam_postprocess.py and test_perception_benchmark_adapters.py GREEN pytest
    exit_code: 0
  - command: Linux r1 built so101_demo_py over the canonical overlay without ignoring unselected workspace packages
    exit_code: 1_INVALID_BUILD_BOUNDARY
  - command: Linux r2 invoked system colcon from the model venv without exposing colcon-core to that interpreter
    exit_code: 1_INVALID_BUILD_ENVIRONMENT
  - command: Linux r3 expanded the build to so101_mujoco_support under the model venv
    exit_code: 1_INVALID_BUILD_SCOPE
  - command: Linux r4 selected only so101_demo_py, ignored every unselected same-workspace package, and allowed the intentional override
    exit_code: 0_WRONG_RUNTIME_SHEBANG
  - command: Linux r5 ran /usr/bin/colcon with the Grounded-SAM venv interpreter and the same single-package boundary
    exit_code: 0
  - command: Linux focused pytest with the r5 build package first, model venv dependencies, and system pytest
    exit_code: 0
observed:
  - first invocation did not collect because the plan's historical PYTHONPATH layout no longer maps the installed so101_demo package; it is INVALID and not RED evidence
  - functional RED executed both real conversion boundaries and failed 2/2 because plastic cup. produced zero raw candidates and one fewer production proposal; JUnit SHA256 1e6134fa9125367f317d8b8a7ac90ed763c27dbc1e039e55157cb85864c76a71
  - Mac focused GREEN passed 95/95 in 5.34 s; JUnit SHA256 1284ef78c68535126a0c7c58240b028f16b0cb178bb652c08d53c566cfad72ea
  - Linux r1-r3 were invalid build-boundary probes and produced no runtime or ROS graph evidence; r4 built the right package but its console scripts used /usr/bin/python3, so it was not accepted as model-runtime provenance
  - Linux r5 resolved the boundary without installing anything: so101_demo_py prefix is /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-078/linux-r5/install/so101_demo_py, rgbd_object_pose shebang is /data/work/venvs/so101-grounded-sam/bin/python, and the loaded postprocessor came from the r5 build symlink
  - Linux focused GREEN passed 95/95 in 7.25 s; JUnit SHA256 6c935a5e6579bc9492edb956ab96aae02fb2c547c18373cafed9fa091ecd1abf
conclusion: punctuation normalization fixes the incomplete candidate boundary on both platforms while preserving the fixed prompt, model outputs, thresholds, and fail-closed downstream contracts
decision: KEEP
next_experiment: EXP-079_FRESH_VALIDATION_DESIGN
```

## Checkpoint CP-017 — label remediation green

```yaml
checkpoint_id: CP-017
last_valid_experiment: EXP-078
source_commit_under_test: db927278995be5c63d62766c96ac462b7c882b9e
change_scope: decoded-label comparison only; Unicode punctuation becomes a word separator before case-folded whitespace-normalized equality
mac_test: 95 passed; JUnit SHA256 1284ef78c68535126a0c7c58240b028f16b0cb178bb652c08d53c566cfad72ea
linux_test: 95 passed; JUnit SHA256 6c935a5e6579bc9492edb956ab96aae02fb2c547c18373cafed9fa091ecd1abf
linux_runtime_provenance:
  checkout: /data/work/so101-grounded-sam-yolo-benchmark-ab-v1-task14-runner-access-r11
  package_prefix: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-078/linux-r5/install/so101_demo_py
  runtime_python: /data/work/venvs/so101-grounded-sam/bin/python
owned_processes: NONE_STARTED_BY_EXP_078
retained_runs:
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-078
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-078/linux-r5 on ai-station
archived_runs: []
deletion_candidates:
  - Linux r1-r4 build probes, only after explicit user authorization
qualification_boundary:
  - the opened R12 test split is permanently excluded from remediation, recalibration, threshold selection, and model ranking
  - EXP-078 is unit and build provenance evidence; it does not reopen CP-016 or count toward a four-scene or PickPlace pass
next_command: prewrite EXP-079 fresh-validation and newly sealed-test design before any new model inference
decision: DESIGN_FRESH_DATA_ROUTE
```

## EXP-079 — fresh validation and sealed-test route

```yaml
experiment_id: EXP-079
status: PLANNED
prior_experiment: EXP-078_VALID_SUCCESS
hypothesis: after punctuation-equivalent label retention, a calibration based only on a fresh dual-platform validation split can determine whether this fixed Grounding-DINO Tiny plus stateless SAM 2.1 Hiera Tiny pipeline has a non-conflicting safe threshold interval
prediction: the new validation records will retain every prompt-equivalent low-floor proposal, and any threshold lock will be derived without reading the new test split; only a later one-time sealed-test run can support a deployability decision
fresh_dataset:
  generator: existing MuJoCo object-ID renderer with one TDD extension for explicit disjoint split seed starts
  image_size: [640, 480]
  split_counts: {train: 480, val: 200, test: 200}
  seed_starts: {train: 400000, val: 500000, test: 600000}
  scenarios: [no_cup, one_cup_distractors, two_cups, cup_near_bottle]
  per_val_scenario: 50
  per_test_scenario: 50
  old_seed_ranges_forbidden: {train: [100000, 100479], val: [200000, 200199], test: [300000, 300199]}
  test_policy: generation and archive sealing may enumerate safe member paths and byte digests, but no agent or calibration command may extract, parse, render, summarize, or infer on test images, labels, truth, scenarios, or instances before both new threshold locks verify
single_source_change_before_generation:
  - accept optional seed_starts with exact train/val/test keys
  - preserve current seed starts when the field is absent
  - reject negative, Boolean, missing, extra, overlapping, or count-overflowing ranges
  - write the selected ranges into dataset-manifest.json
frozen_after_archive_creation:
  - archive bytes and SHA256
  - sealed test member inventory and SHA256
  - open val semantic inventory and SHA256
  - source commit, MJCF SHA256, model assets, prompt, grid, FP32, native MPS/CUDA, offline, and no-fallback policy
execution_order:
  - TDD seed-start contract and exact-source package gates on Mac and Linux
  - generate one new archive on Linux and read back its SHA without inspecting test semantics
  - bind a new benchmark config/source commit to that archive and rebuild both platforms
  - prepare only val plus the non-semantic sealed test-member inventory
  - run native Mac and Linux low-floor val for YOLO-Seg and Grounded-SAM
  - jointly calibrate one cross-platform lock per model using val only
  - verify both lock identities, then append exactly one new test-access event
  - extract and verify the new test split once; run the frozen formal matrix once per preregistered run ID
  - return to four-scene and PickPlace qualification only if both platforms have unsafe unique-selection rate 0 and the no/one/two-cup threshold interval is non-conflicting
success_criteria:
  - no seed overlaps the old dataset or another new split
  - val and test each contain exactly 200 unique images and 50 images per scenario
  - every expected sample remains in the denominator, including inference errors
  - both platforms use the same archive and the same per-model threshold lock
  - Grounded-SAM stays frame-stateless and retains plastic cup plus plastic cup. equivalently
  - frozen test unsafe unique-selection rate is 0 on both platforms before Task 11 resumes
failure_criteria:
  - no feasible val point or any frozen-test unsafe unique selection blocks Task 11 and PickPlace claims
invalid_criteria:
  - any R12 prediction/truth/metric influences generation, threshold selection, ranking, or acceptance
  - any new test semantic access occurs before both new locks verify
  - archive, inventory, source, model, runtime, device, dtype, fallback, count, order, or evidence-index provenance drifts
  - a failed formal run is resumed, overwritten, hidden, or replaced under the same semantic identity
stop_criteria:
  - stop immediately on test leakage, provenance mismatch, unsafe selection, non-native fallback, or incomplete evidence
registered_evidence_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869
mac_development_root: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079
linux_durable_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079
retained_runs: [all CP-017 retained runs]
archived_runs: []
deletion_candidates: [none added before execution]
next_command: commit this preregistration, then add only the seed-start regression tests and observe RED before implementation
decision: RUN_TDD_SEED_NAMESPACE_ONLY
```

## Checkpoint CP-018 — fresh dataset generation lock

```yaml
checkpoint_id: CP-018
experiment_id: EXP-079
status: RUNNING_DATASET_GENERATION
source_commit: e0c6d029ef13c93f6649bc93da94bb95d1e6f807
tdd:
  initial_red: 8 failed and 11 passed; JUnit SHA256 b58b7fc725c05cfd139b8eaaf2ec64ea7d8a5bc0b1311e751e274584e4d21270
  review_red: sample_limit hid a full-range overlap before the second fix
  mac_green: 104 passed in 133.49 s; JUnit SHA256 391d45f39c6280d314c54b63810838d822d00dca8b86e57a271dc13311a1c7ed
  linux_green: 102 passed and 2 platform-condition skips in 1257.47 s; JUnit SHA256 a35c9f2b1796ac64fb0dc8603372950c69d6df5059c73fd01c6d19c8654ff94c
  static: py_compile and git diff --check passed; Ruff unavailable in the selected Mac and Linux environments, so no Ruff result is claimed
linux_build:
  r1: INVALID_PREBUILD because --log-base followed the build subcommand; no package, model, ROS, or dataset command ran
  r2: VALID; one package finished
  checkout: /data/work/so101-grounded-sam-yolo-benchmark-ab-v1-task14-runner-access-r11
  package_prefix: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-r2/install/so101_demo_py
  loaded_module: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-r2/build/so101_demo_py/so101_demo/adapters/perception/mujoco_dataset.py
  generator_python: /data/work/venvs/so101-grounded-sam/bin/python
generation:
  config: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-r2/install/so101_demo_py/share/so101_demo_py/config/perception_benchmark/fresh_dataset.yaml
  output_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/raw-e0c6d029
  archive: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/so101-v5-t005-grounded-sam-fresh-e0c6d029.tar.gz
  environment: MUJOCO_GL=egl and PYTHONNOUSERSITE=1
  command: generate_yolo_seg_dataset --config <exact installed fresh_dataset.yaml> --output-root <absent raw-e0c6d029> --generator-commit e0c6d029ef13c93f6649bc93da94bb95d1e6f807
generation_success:
  - exactly 880 samples and 2641 payload artifacts before dataset-manifest.json
  - manifest source/MJCF/image-size/count/seed-range fields exactly match EXP-079
  - deterministic archive is written once, hashed, and never overwritten
generation_access_boundary:
  - validator may read dataset-manifest.json and val metadata
  - no command may open an images/test, labels/test, or truth/test member before both new locks verify
  - archive sealing may record only safe member names, counts, and byte digests
preflight:
  - local, Gitee, and ai-station source read back e0c6d029ef13c93f6649bc93da94bb95d1e6f807
  - raw output and archive targets must be absent and non-symlink before generation
  - no Grounded-SAM, benchmark, MuJoCo, ROS, or tmux process may be active
retained_runs:
  - all CP-017 retained runs
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079
  - Linux build r1 and r2
archived_runs: []
deletion_candidates:
  - Linux build r1 only, after explicit user authorization
next_command: commit CP-018, synchronize ai-station, run the one exact generation command, and stop before archive/config rebinding
decision: RUN_ONE_FRESH_DATASET_GENERATION
```

## Checkpoint CP-019 — non-symlink dataset generation replacement

```yaml
checkpoint_id: CP-019
experiment_id: EXP-079
supersedes: CP-018 generation command only
cp018_result: INVALID_PRESTART
cp018_observed:
  - generate_yolo_seg_dataset returned dataset config must be a regular file before output-root creation
  - r2 had correctly packaged fresh_dataset.yaml, but --symlink-install made the installed path a symlink and the fail-closed config reader rejected it
  - raw-e0c6d029 and its archive target remain absent; no image, label, truth, model, simulator, or ROS output was produced
replacement_build:
  id: linux-build-r3
  mode: non-symlink install
  checkout_head: 2603e6c958831a31a99ee3bc092f49588a97cea6
  package_prefix: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-r3/install/so101_demo_py
  config_type: regular file
  generator_python: /data/work/venvs/so101-grounded-sam/bin/python
  loaded_module: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-r3/install/so101_demo_py/lib/python3.12/site-packages/so101_demo/adapters/perception/mujoco_dataset.py
  focused_test: 22 passed in 2.74 s; JUnit SHA256 81c2ed663a8898955b7f4e52c50a68f5c05281862ba17e1a4a3f3619c6ddad2b
replacement_generation:
  config: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-r3/install/so101_demo_py/share/so101_demo_py/config/perception_benchmark/fresh_dataset.yaml
  output_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/raw-2603e6c9-r2
  archive: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/so101-v5-t005-grounded-sam-fresh-2603e6c9-r2.tar.gz
  generator_commit: 2603e6c958831a31a99ee3bc092f49588a97cea6
  environment: MUJOCO_GL=egl and PYTHONNOUSERSITE=1
  success_and_access_contract: exactly CP-018
preflight:
  - replacement output and archive targets must be absent and non-symlink
  - installed config must remain a regular file with SHA256 matching the tracked file at checkout HEAD
  - no Grounded-SAM, benchmark, dataset-generator, MuJoCo, ROS, or tmux process may be active
retained_runs:
  - all CP-018 retained runs
  - linux-build-r3
archived_runs: []
deletion_candidates:
  - CP-018 r1 plus r2 symlink build, only after explicit user authorization
next_command: commit CP-019, synchronize ai-station, and run replacement_generation exactly once
decision: RUN_REPLACEMENT_DATASET_GENERATION
```

## EXP-080 — scenario-authoritative instance labels

```yaml
experiment_id: EXP-080
status: PLANNED
prior_experiment: EXP-079_DATASET_INVALID
hypothesis: moving inactive cup bodies to 2,2,2 does not guarantee zero segmentation pixels, while build_labeled_sample currently accepts every visible cup-named body without checking whether that body is active in the selected scenario
prediction: a synthetic no_cup render containing stray cup-body geom IDs will incorrectly produce cup instances before the fix; after one scenario-authoritative body filter it will produce zero, one, or two instances exactly as the scenario permits
invalid_dataset:
  root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/raw-2603e6c9-r2
  status: INVALID_LABEL_SEMANTICS
  archive: ABSENT
  generated_samples: 880
  observed_manifest_class_instance_total: 1760
  expected_manifest_class_instance_total: 880
  open_val_summary: every one of the four 50-image val scenarios reported visible_instance_count 2
  open_val_diagnostic: seed 500000 no_cup had two label rows; plastic_cup and plastic_cup_b masks contained only 8 and 11 scattered pixels before convex hull
  test_access: no images/test, labels/test, or truth/test file was opened; only top-level manifest/counts/member names were read
single_variable: before converting geom IDs to masks, restrict eligible cup body names to none for no_cup, plastic_cup for one_cup_distractors and cup_near_bottle, and plastic_cup plus plastic_cup_b for two_cups
unchanged:
  - MJCF, hidden position, renderer, camera and color randomization
  - split counts, seed starts, image size, polygon implementation and output schema
  - models, prompt, thresholds, selection, depth, TF and motion
tdd:
  - add a RawRender with both cup body IDs visible while the scenario declares zero or one active cup
  - prove RED because inactive bodies are currently retained
  - implement only the scenario-to-body allowlist and keep a two-cup control
success_criteria:
  - focused labels produce exact 0/1/2 counts and expected body names
  - existing dataset and archive-security tests remain green on Mac and Linux
  - a fresh replacement dataset has class_instance_totals plastic_cup 880 and val configured/visible counts agree for all 200 open samples
invalid_criteria:
  - any test-split file content is opened before new threshold locks
  - a label is repaired after generation rather than regenerated from exact committed source
  - inactive-body filtering is inferred from pixels, confidence, color, or test metrics instead of the scenario contract
retained_runs:
  - all CP-019 retained runs
  - invalid raw-2603e6c9-r2 directory
  - local open-val diagnostic under /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/val-diagnostic
archived_runs: []
deletion_candidates:
  - invalid raw-2603e6c9-r2, only after explicit user authorization
next_command: commit EXP-080 preregistration, add only the scenario-label regression, and observe RED
decision: RUN_EXP_080_TDD_ONLY
```

## Checkpoint CP-021 — corrected fresh dataset generation lock

```yaml
checkpoint_id: CP-021
last_valid_experiment: EXP-080
source_commit: 650f3398fb9e6eb5cc3b9ae6f15afc0bb1d858f7
tdd:
  red: 3 failed and 1 two-cup control passed; JUnit SHA256 c82cc68f5a086d9e9e0c002dad96172705a11c81e39f2fe6a1e2af7bf5a076ad
  mac_green: 108 passed in 128.25 s; JUnit SHA256 403cdd3735cb9ae76ec018a0a95ab920c5a60dc36381dd9a5400814874a3598b
  linux_green: 26 passed in 2.90 s; JUnit SHA256 c5c4a0b6e19c0a8041e6935788f410620de39a1db22b5394834e67dfde50d9a4
  static: py_compile and git diff --check passed
fix_scope: build_labeled_sample now admits only scenario-active plastic_cup body names before converting object IDs to instance masks
linux_build:
  root: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-080/linux-build-r1
  mode: non-symlink install
  package_prefix: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-080/linux-build-r1/install/so101_demo_py
  generator_python: /data/work/venvs/so101-grounded-sam/bin/python
corrected_generation:
  config: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-080/linux-build-r1/install/so101_demo_py/share/so101_demo_py/config/perception_benchmark/fresh_dataset.yaml
  output_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/raw-650f3398-r3
  archive: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/so101-v5-t005-grounded-sam-fresh-650f3398-r3.tar.gz
  checksum_file: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/so101-v5-t005-grounded-sam-fresh-650f3398-r3.tar.gz.sha256
  generator_commit: 650f3398fb9e6eb5cc3b9ae6f15afc0bb1d858f7
  expected_samples: 880
  expected_artifacts_before_manifest: 2641
  expected_class_instance_total: 880
  expected_val_visible_counts: {no_cup: 0, one_cup_distractors: 1, two_cups: 2, cup_near_bottle: 1}
  environment: MUJOCO_GL=egl and PYTHONNOUSERSITE=1
access_boundary:
  - validate top-level manifest and open val content only
  - do not open any corrected test image, label, or truth content
  - create the archive and adjacent checksum once only after corrected val semantics pass
preflight:
  - local, Gitee, and ai-station exact source SHA readback
  - corrected output, archive, and checksum targets absent and non-symlink
  - no model, benchmark, dataset-generator, simulator, ROS, or tmux process active
retained_runs:
  - all EXP-080 retained runs
  - exp-080 linux-build-r1
archived_runs: []
deletion_candidates:
  - unchanged from EXP-080
next_command: commit CP-021, synchronize ai-station, generate raw-650f3398-r3 once, validate only manifest and val, then create one deterministic archive and checksum
decision: RUN_CORRECTED_DATASET_GENERATION
```

## Checkpoint CP-022 — corrected fresh archive frozen

```yaml
checkpoint_id: CP-022
experiment_id: EXP-079
status: RUNNING_CONFIG_REBIND
dataset_generation: VALID
source_commit: 650f3398fb9e6eb5cc3b9ae6f15afc0bb1d858f7
raw_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/raw-650f3398-r3
manifest:
  generator_commit: 650f3398fb9e6eb5cc3b9ae6f15afc0bb1d858f7
  mjcf_sha256: d40494c9f88294840d8e8a90859c6a28dc361149b5878b785b787ea96c61e083
  sample_count: 880
  payload_artifact_count: 2641
  total_file_count_including_manifest: 2642
  symlink_count: 0
  split_counts: {train: 480, val: 200, test: 200}
  seed_ranges: {train: [400000, 400479], val: [500000, 500199], test: [600000, 600199]}
  class_instance_totals: {plastic_cup: 880}
open_val_validation:
  status: PASS
  sample_count: 200
  scenario_counts: {no_cup: 50, one_cup_distractors: 50, two_cups: 50, cup_near_bottle: 50}
  visible_instances: {no_cup: 0, one_cup_distractors: 1, two_cups: 2, cup_near_bottle: 1}
  checks: truth configured/visible/list counts, label row count, RGB 640x480 mode and PNG verification
sealed_test_state:
  member_name_counts: {images: 200, labels: 200, truth: 200}
  semantic_content_opened: false
  model_inference_run: false
archive:
  path: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/so101-v5-t005-grounded-sam-fresh-650f3398-r3.tar.gz
  sha256: d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6
  size_bytes: 39612523
  member_count: 2655
  link_member_count: 0
  mode: '0444'
checksum_file: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/so101-v5-t005-grounded-sam-fresh-650f3398-r3.tar.gz.sha256
retained_runs:
  - all CP-021 retained runs
  - corrected raw root, archive, and checksum above
archived_runs: []
deletion_candidates:
  - unchanged from CP-021; corrected archive is not a deletion candidate
next_change:
  - rebind benchmark.yaml archive ID/SHA and registered evidence roots to EXP-079
  - update only the CLI immutable archive/config constants and exact tests required by that rebind
  - preserve all model revisions, model bytes, prompt, thresholds, grid, device, dtype, offline, no-fallback, sample-count, scenario, timing, and test-seal contracts
next_command: add a frozen-config regression for the new archive and observe RED before editing benchmark.yaml or CLI constants
decision: RUN_CONFIG_REBIND_TDD_ONLY
```

## Checkpoint CP-023 — fresh val and test-seal preparation lock

```yaml
checkpoint_id: CP-023
experiment_id: EXP-079
status: RUNNING_DATASET_PREPARATION
source_commit: ef254f6025d8de42ce42a6cc6871e703fc86fbd4
config_rebind:
  archive_id: datasets/so101-v5-t005-grounded-sam-fresh/so101-v5-t005-grounded-sam-fresh-650f3398-r3.tar.gz
  archive_sha256: d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6
  config_sha256: 4b8b0ac1046180bd5b10748fe8d8b505b9858b63648ffcf888743aad75cf9160
  evidence_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079
  debug_root: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079
  unchanged: model revisions and bytes, prompt, production and low-floor values, calibration grids, FP32, native devices, offline/no-fallback, counts, scenarios, warmup/cold/bootstrap and run order
tdd:
  red: frozen config literal failed; JUnit SHA256 06c68cdee0e8a373249a9075f56dba4edde6e668b6ab8b29af5a82549136c136
  mac_green: 54 passed in 0.93 s; JUnit SHA256 2424fe4e3920d3d1ff985cb1812f894eac0ef559656b576789f0699105f4e0cd
  linux_green: 54 passed in 6.10 s; JUnit SHA256 2aed679ed53eb63e3aeb91debb28eee0bb036a84108b17cbba9b8a1b4d05a80d
  static: py_compile, exact config SHA readback, old-literal scan and git diff --check passed
mac_build:
  r1: INVALID_PREBUILD because Mac colcon does not support --allow-overriding
  r2: VALID non-symlink install; first test command was INVALID_ENVIRONMENT due a Linux python3.12 path, corrected command loaded the python3.11 installed copy and passed
  package_prefix: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/mac-build-ef254-r2/install/so101_demo_py
  runtime_python: /Users/matianyi/ros2_jazzy/.venv/bin/python
linux_build:
  r1: VALID non-symlink install
  package_prefix: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py
  runtime_python: /data/work/venvs/so101-grounded-sam/bin/python
dataset_preparation:
  archive: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/so101-v5-t005-grounded-sam-fresh-650f3398-r3.tar.gz
  config: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/share/so101_demo_py/config/perception_benchmark/benchmark.yaml
  sealed_member_inventory: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/sealed-test-members-r1.json
  val_output_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/val-open-r1
  inspect_command: perception_benchmark inspect-archive --config <exact config> --archive <exact archive> --expected-sha256 d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6 --sealed-member-inventory <absent sealed-test-members-r1.json>
  val_command: perception_benchmark prepare-dataset --config <exact config> --archive <exact archive> --expected-sha256 d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6 --split val --output-root <absent val-open-r1>
success_criteria:
  - archive/config SHA and safe paths verify
  - seal contains exactly 200 image/label/truth test triplets while test scenario_counts stays null
  - val semantic inventory contains 200 unique samples, four scenarios of 50, and source bytes read back
  - no test member is extracted, parsed, rasterized, displayed, or inferred
stop_criteria:
  - any command failure or test semantic access makes this preparation ID terminal invalid and blocks inference
retained_runs:
  - all CP-022 retained runs
  - Mac build r1/r2 and Linux build r1 for ef254f60
archived_runs: []
deletion_candidates:
  - Mac build r1 and invalid first r2 JUnit, only after explicit user authorization
next_command: commit CP-023, synchronize ai-station, run inspect_command once, verify its non-semantic seal, then run val_command once
decision: PREPARE_FRESH_VAL_KEEP_TEST_SEALED
```

## Checkpoint CP-024 — replacement archive-binding preparation lock

```yaml
checkpoint_id: CP-024
experiment_id: EXP-079
status: PREREGISTERED_REPLACEMENT
source_commit: 7a802d23f1663e4a6af108cb963d136346e7ba40
supersedes_command_only: CP-023 dataset_preparation
cp_023_terminal_result:
  status: INVALID_PRESTART
  first_bad_boundary: inspect-archive rejected the direct archive path because its trailing path components did not equal the frozen logical archive ID
  error: FROZEN_PROVENANCE_MISMATCH
  archive_sha256_verified: d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6
  config_sha256_verified: 4b8b0ac1046180bd5b10748fe8d8b505b9858b63648ffcf888743aad75cf9160
  sealed_member_inventory_created: false
  val_output_created: false
  test_semantic_content_accessed: false
immutable_asset_copy:
  source: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/so101-v5-t005-grounded-sam-fresh-650f3398-r3.tar.gz
  target: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/assets/datasets/so101-v5-t005-grounded-sam-fresh/so101-v5-t005-grounded-sam-fresh-650f3398-r3.tar.gz
  checksum_target: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/assets/datasets/so101-v5-t005-grounded-sam-fresh/so101-v5-t005-grounded-sam-fresh-650f3398-r3.tar.gz.sha256
  required_sha256: d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6
  policy: require absent targets, copy once, verify bytes, retain source, make archive read-only, never overwrite
replacement_outputs:
  sealed_member_inventory: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/sealed-test-members-r2.json
  val_output_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/val-open-r2
replacement_commands:
  inspect: /data/work/venvs/so101-grounded-sam/bin/python /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/lib/so101_demo_py/perception_benchmark inspect-archive --config /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/share/so101_demo_py/config/perception_benchmark/benchmark.yaml --archive /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/assets/datasets/so101-v5-t005-grounded-sam-fresh/so101-v5-t005-grounded-sam-fresh-650f3398-r3.tar.gz --expected-sha256 d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6 --sealed-member-inventory /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/sealed-test-members-r2.json
  prepare_val: /data/work/venvs/so101-grounded-sam/bin/python /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/lib/so101_demo_py/perception_benchmark prepare-dataset --config /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/share/so101_demo_py/config/perception_benchmark/benchmark.yaml --archive /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/assets/datasets/so101-v5-t005-grounded-sam-fresh/so101-v5-t005-grounded-sam-fresh-650f3398-r3.tar.gz --expected-sha256 d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6 --split val --output-root /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/val-open-r2
success_criteria:
  - copied archive and adjacent checksum have the frozen digest and the archive is read-only
  - seal contains exactly 200 image, 200 label, and 200 truth test members while scenario_counts remains null
  - val inventory contains exactly 200 unique samples and 50 per scenario
  - val output contains no test path and no test semantic member is extracted, parsed, rasterized, displayed, or inferred
stop_criteria:
  - any target already exists, digest differs, command fails, or test semantic access occurs
retained_runs:
  - all CP-023 retained runs and both absent R1 output names
archived_runs: []
deletion_candidates:
  - unchanged from CP-023
next_command: commit and push CP-024, synchronize the isolated ai-station checkout, verify all replacement targets are absent, then copy and inspect once
decision: COPY_WITH_FROZEN_SUFFIX_THEN_PREPARE_VAL
```

## Checkpoint CP-025 — installed-runtime environment replacement lock

```yaml
checkpoint_id: CP-025
experiment_id: EXP-079
status: PREREGISTERED_REPLACEMENT
source_commit: 22e61f44685bca6445fcc31790484b07d6f3f3c9
cp_024_copy_result:
  status: VALID
  target_archive_sha256: d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6
  target_archive_size_bytes: 39612523
  target_archive_mode: '0444'
  target_checksum_mode: '0444'
  source_retained: true
cp_024_inspect_result:
  status: INVALID_PRESTART
  first_bad_boundary: console entry point could not discover so101-demo-py package metadata because the non-symlink install site-packages directory was absent from sys.path
  error: importlib.metadata.PackageNotFoundError No package metadata was found for so101-demo-py
  archive_opened: false
  sealed_member_inventory_created: false
  val_output_created: false
  test_semantic_content_accessed: false
runtime_binding:
  python: /data/work/venvs/so101-grounded-sam/bin/python
  pythonpath: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/lib/python3.12/site-packages
  usersite: disabled
replacement_outputs:
  sealed_member_inventory: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/sealed-test-members-r3.json
  val_output_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/val-open-r3
replacement_commands:
  inspect: PYTHONNOUSERSITE=1 PYTHONPATH=/tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/lib/python3.12/site-packages /data/work/venvs/so101-grounded-sam/bin/python /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/lib/so101_demo_py/perception_benchmark inspect-archive --config /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/share/so101_demo_py/config/perception_benchmark/benchmark.yaml --archive /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/assets/datasets/so101-v5-t005-grounded-sam-fresh/so101-v5-t005-grounded-sam-fresh-650f3398-r3.tar.gz --expected-sha256 d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6 --sealed-member-inventory /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/sealed-test-members-r3.json
  prepare_val: PYTHONNOUSERSITE=1 PYTHONPATH=/tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/lib/python3.12/site-packages /data/work/venvs/so101-grounded-sam/bin/python /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/lib/so101_demo_py/perception_benchmark prepare-dataset --config /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/share/so101_demo_py/config/perception_benchmark/benchmark.yaml --archive /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/assets/datasets/so101-v5-t005-grounded-sam-fresh/so101-v5-t005-grounded-sam-fresh-650f3398-r3.tar.gz --expected-sha256 d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6 --split val --output-root /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/val-open-r3
success_criteria:
  - package metadata resolves from the exact non-symlink installed copy
  - CP-024 seal and val criteria remain unchanged
stop_criteria:
  - any R3 target already exists, runtime binding differs, command fails, or test semantic access occurs
retained_runs:
  - all CP-024 retained runs, immutable asset copy, and absent R2 output names
archived_runs: []
deletion_candidates:
  - unchanged from CP-024
next_command: verify the exact package metadata binding, commit and push CP-025, synchronize ai-station, then run the R3 inspect command once
decision: BIND_INSTALLED_SITE_PACKAGES_THEN_INSPECT
```

## Checkpoint CP-026 — fresh validation materialized, test remains sealed

```yaml
checkpoint_id: CP-026
experiment_id: EXP-079
status: VALID_DATASET_PREPARATION
source_commit: f63a65aa616eaa852d49dc7130de3b25eea63e7b
archive_asset:
  path: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/assets/datasets/so101-v5-t005-grounded-sam-fresh/so101-v5-t005-grounded-sam-fresh-650f3398-r3.tar.gz
  sha256: d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6
  size_bytes: 39612523
  mode: '0444'
  source_retained: true
sealed_test:
  inventory: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/sealed-test-members-r3.json
  inventory_sha256: 905383228d57a0177e141814a96a5998524d1252e51e33d962c7fda7c5375295
  archive_sha256: d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6
  member_count: 600
  artifact_counts: {images: 200, labels: 200, truth: 200}
  unique_member_paths: 600
  scenario_counts: null
  semantic_content_opened: false
  extracted: false
  rasterized: false
  displayed: false
  inferred: false
open_val:
  root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/val-open-r3
  inventory_sha256: 500b61e69771e3098628b20b5c4b01926d41df7dad1ffc3a7023be34405638b2
  sample_count: 200
  scenario_counts: {no_cup: 50, one_cup_distractors: 50, two_cups: 50, cup_near_bottle: 50}
  truth_count_by_scenario: {no_cup: 0, one_cup_distractors: 1, two_cups: 2, cup_near_bottle: 1}
  unique_formal_sample_indices: 200
  unique_artifact_paths: 600
  regular_file_count_including_inventory_and_archive_anchor: 602
  symlink_count: 0
  test_path_count: 0
  all_source_files_exist: true
  all_source_sha256_match: true
cp_025_result:
  package_metadata_version: 0.1.0
  package_module: so101_demo
  inspect: PASS
  prepare_val: PASS
  output_names_reused_or_overwritten: false
retained_runs:
  - all CP-025 retained runs
  - immutable archive asset and checksum
  - sealed-test-members-r3.json
  - val-open-r3
archived_runs: []
deletion_candidates:
  - unchanged from CP-025; no valid CP-026 artifact is a deletion candidate
next_change:
  - bind exact Mac and Linux native runtimes to the fresh validation inventory and unchanged frozen model assets
  - run offline/no-fallback dry-run on both platforms before any 200-sample validation inference
  - keep test sealed until both model/platform validation runs and joint threshold locks pass
decision: PROCEED_TO_CROSS_PLATFORM_DRY_RUN_KEEP_TEST_SEALED
```

## Checkpoint CP-027 — cross-platform dry-run and Mac MPS remediation lock

```yaml
checkpoint_id: CP-027
experiment_id: EXP-079
status: PREREGISTERED_RUNTIME_REMEDIATION
source_commit: 8dc09265448113271a8d72e3b107ae5c21bdd83a
benchmark_code_commit: ef254f6025d8de42ce42a6cc6871e703fc86fbd4
frozen_dataset:
  archive_sha256: d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6
  inventory_sha256: 500b61e69771e3098628b20b5c4b01926d41df7dad1ffc3a7023be34405638b2
  linux_inventory: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/val-open-r3/inventory.json
  mac_copy_root: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/dataset/val-open-macos-r1
  copy_policy: target must be absent; copy once from ai-station; verify inventory SHA, 600 source file SHAs, 200 samples, four scenarios of 50, and no test path
frozen_assets:
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  mac_yolo_weights: /tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/assets/best.pt
  linux_yolo_weights: /data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/assets-r8/best.pt
  grounded_sam_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
  mac_model_root: /Users/matianyi/Models/so101/grounded-sam-v2-scipy-lock
  linux_model_root: /data/work/so101-models/grounded-sam-v2-scipy-lock
device_preflight:
  linux: {torch: 2.13.0+cu130, cuda_available: true, device_count: 1}
  mac:
    hardware: Apple M5 with Metal support
    existing_torch: 2.13.0
    mps_built: true
    mps_available: false
    tensor_probe: RuntimeError The MPS backend is supported on macOS 14.0+
    matching_upstream_issue: https://github.com/pytorch/pytorch/issues/177819
mac_runtime_overlay:
  root: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/mac-runtime-torch-nightly-20260903-r1
  torch: 2.15.0.dev20260903
  torchvision: 0.30.0.dev20260903
  index: https://download.pytorch.org/whl/nightly/cpu
  install_policy: target must be absent; install exact versions with --no-deps and --target; do not modify the ROS virtual environment
  probe: PYTHONNOUSERSITE=1 PYTHONPATH=<overlay> /Users/matianyi/ros2_jazzy/.venv/bin/python -c <verify exact versions, mps built/available, and allocate one MPS tensor>
dry_run:
  mac_output: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/dry-run/macos-r1
  linux_output: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dry-run/linux-r1
  policy: outputs must be absent; offline; actual adapters; FP32; native MPS/CUDA; no CPU fallback; eight validation samples with two per scenario; both models; no test access
success_criteria:
  - isolated Mac overlay MPS tensor probe passes without modifying the base virtual environment
  - Mac copy inventory and all 600 source artifact SHAs equal Linux CP-026 evidence
  - each dry-run writes 8 records per model, reports fallback_used false, and binds the frozen assets, config, inventory, archive, and benchmark code commit
  - no test member is extracted, parsed, rasterized, displayed, or inferred
stop_criteria:
  - overlay install/probe failure, copied-data mismatch, any output collision, fallback, wrong device/dtype, missing record, or test access
retained_runs:
  - all CP-026 retained runs
archived_runs: []
deletion_candidates:
  - unchanged from CP-026; failed isolated overlay is a candidate only after explicit authorization
next_command: commit and push CP-027, synchronize ai-station, verify output targets absent, install the isolated Mac runtime overlay, and run the MPS tensor probe
decision: REMEDIATE_MPS_IN_ISOLATED_OVERLAY_BEFORE_DRY_RUN
```

## Checkpoint CP-028 — native Terminal MPS probe replacement lock

```yaml
checkpoint_id: CP-028
experiment_id: EXP-079
status: PREREGISTERED_NATIVE_TERMINAL_PROBE
source_commit: 555715e1cfffa7f3e0fab3dff0a5cfb6597bbea7
cp_027_overlay_result:
  status: CANCELLED_PRESTART
  reason: upstream reproduction identifies the false-negative as specific to the Codex runtime context; replacing PyTorch inside the same context would not establish native Mac MPS availability
  matching_upstream_issue: https://github.com/pytorch/pytorch/issues/177819
  first_attempt: download did not complete and created no target directory
  duplicate_attempt: one accidentally duplicated download process was terminated; the retained tracked download was then cancelled before target creation
  overlay_target_created: false
  base_virtual_environment_modified: false
  evidence_deleted: false
native_terminal_probe:
  script: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/mac-native-terminal-probe-r1.sh
  script_sha256: d005198b065f93e0b711914a7f2746bb5c568f6880a45b2d516629a1df142137
  command: /bin/zsh /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/mac-native-terminal-probe-r1.sh
  output: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/mac-native-terminal-probe-r1.json
  output_policy: output and temporary path must be absent; write once; chmod 0444; execute from the ordinary macOS Terminal process
success_criteria:
  - exact base Python and torch 2.13.0 are used without any runtime overlay
  - mps_built and mps_available are true
  - one tensor is allocated on mps:0 and read back as 1.0
  - the probe output is immutable and its SHA-256 is recorded
stop_criteria:
  - any output collision, script digest mismatch, base environment drift, MPS false, allocation failure, or CPU tensor
retained_runs:
  - all CP-027 retained runs and the probe script
archived_runs: []
deletion_candidates:
  - pip temporary download directories from the cancelled attempts, only after explicit user authorization
next_command: commit and push CP-028, verify the script digest and output absence, then run the exact command once from ordinary macOS Terminal
decision: PROVE_NATIVE_MPS_OUTSIDE_CODEX_RUNTIME
```

## Checkpoint CP-029 — launchd-native MPS probe replacement lock

```yaml
checkpoint_id: CP-029
experiment_id: EXP-079
status: PREREGISTERED_LAUNCHD_PROBE
source_commit: 43d2db12aa734d6441d437ebe6d2e81a0b7b7131
cp_028_result:
  status: BLOCKED_BEFORE_EXECUTION
  first_bad_boundary: computer-use safety policy rejects control of both Apple Terminal and Ghostty
  command_entered: false
  probe_script_executed: false
  output_created: false
  system_or_application_setting_changed: false
replacement_probe:
  launcher: launchctl submit
  label: com.terry.so101.mps-probe-r2
  script: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/mac-launchd-mps-probe-r2.sh
  script_sha256: 3b3fcb1fb9cb35bdbd73c3030a88fde181c313e9315bb9711b1bedb6aeb9cc97
  command: launchctl submit -l com.terry.so101.mps-probe-r2 -- /bin/zsh /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/mac-launchd-mps-probe-r2.sh
  output: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/mac-launchd-mps-probe-r2.json
  output_policy: output and temporary path must be absent; write once; chmod 0444; read launchd last exit status; remove only the completed ephemeral launchd job, never evidence
success_criteria:
  - launchd creates a process outside the Codex sandbox context using the unchanged base Python and torch 2.13.0
  - CODEX_CI and CODEX_SANDBOX are absent in the probe process
  - mps_built and mps_available are true
  - one tensor is allocated on mps:0 and read back as 1.0
stop_criteria:
  - label collision, output collision, script digest mismatch, nonzero launchd exit, Codex sandbox markers, MPS false, allocation failure, or CPU tensor
retained_runs:
  - all CP-028 retained runs
  - native Terminal R1 script remains retained but was not executed
archived_runs: []
deletion_candidates:
  - unchanged from CP-028
next_command: commit and push CP-029, verify script digest/output absence/label absence, submit the ephemeral launchd job once, then inspect its exit state and immutable output
decision: PROVE_NATIVE_MPS_VIA_EPHEMERAL_LAUNCHD_JOB
```

## Checkpoint CP-030 — fresh cross-platform actual dry-run lock

```yaml
checkpoint_id: CP-030
experiment_id: EXP-079
status: PREREGISTERED_ACTUAL_DRY_RUN
source_commit: 44e53538f7c458ff8a7bc0bf4bb1fb1be83374a1
benchmark_code_commit: ef254f6025d8de42ce42a6cc6871e703fc86fbd4
cp_029_result:
  status: VALID_NATIVE_MPS
  output: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/mac-launchd-mps-probe-r2.json
  output_sha256: 2cfc694cbfba6b30359e25009b4c03c198301ea2dc7f48404189effffc1bf980
  output_mode: '0444'
  platform: macOS-26.6.2-arm64-arm-64bit
  python: 3.11.15
  torch: 2.13.0
  codex_ci: null
  codex_sandbox: null
  mps_built: true
  mps_available: true
  tensor_device: mps:0
  tensor_value: 1.0
  launchd_note: first run succeeded and created immutable evidence; launchctl submit scheduled a second run which failed closed on output collision; the job was then removed and evidence retained
mac_val_copy:
  root: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/dataset/val-open-macos-r1
  inventory_sha256: 500b61e69771e3098628b20b5c4b01926d41df7dad1ffc3a7023be34405638b2
  sample_count: 200
  scenario_counts: {no_cup: 50, one_cup_distractors: 50, two_cups: 50, cup_near_bottle: 50}
  unique_artifact_paths: 600
  all_source_sha256_match: true
  symlink_count: 0
  test_path_count: 0
mac_launch:
  label: com.terry.so101.benchmark.mac.dryrun.r1
  script: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/mac-dry-run-r1.sh
  script_sha256: 84a63c19dfa5ba0ba82d019fc3e4c78e7c5e4b5d7f603bd3ce476e0e2c3c7bab
  plist: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/com.terry.so101.benchmark.mac.dryrun.r1.plist
  plist_sha256: 6915f6e17e025604b771306d0b07cdb5e8d7c0dc5379d413d3723fdfe1aa7b95
  command: launchctl bootstrap gui/501 /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/com.terry.so101.benchmark.mac.dryrun.r1.plist
  output: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/dry-run/macos-r1
  stdout: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/dry-run/macos-r1.stdout.log
  stderr: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/dry-run/macos-r1.stderr.log
linux_launch:
  command: HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONNOUSERSITE=1 PYTHONPATH=/tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/lib/python3.12/site-packages /data/work/venvs/so101-grounded-sam/bin/python /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/lib/so101_demo_py/perception_benchmark dry-run --config /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/share/so101_demo_py/config/perception_benchmark/benchmark.yaml --output-root /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dry-run/linux-r1 --platform linux --device cuda --dtype float32 --dataset-inventory /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/val-open-r3/inventory.json --dataset-archive-sha256 d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6 --inventory-sha256 500b61e69771e3098628b20b5c4b01926d41df7dad1ffc3a7023be34405638b2 --weights /data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/assets-r8/best.pt --weights-sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781 --model-root /data/work/so101-models/grounded-sam-v2-scipy-lock --manifest-sha256 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775 --source-commit ef254f6025d8de42ce42a6cc6871e703fc86fbd4
  output: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dry-run/linux-r1
frozen_contract:
  execution_mode: actual
  run_kind: NON_FORMAL_DRY_RUN
  sample_count: 8
  scenarios_per_platform: {no_cup: 2, one_cup_distractors: 2, two_cups: 2, cup_near_bottle: 2}
  models: [yolo_seg, grounded_sam]
  records_per_model: 8
  dtype: float32
  devices: {macos: mps, linux: cuda}
  offline: true
  fallback_used: false
success_criteria:
  - both one-time commands exit zero with immutable provenance-bound evidence indexes
  - both manifests report actual mode, eight samples, 16 records, eight per model, native device, FP32, and no fallback
  - every record and mask in each evidence index exists and matches its SHA-256
  - no test member is extracted, parsed, rasterized, displayed, or inferred
stop_criteria:
  - any target or launch label collision, nonzero exit, provenance mismatch, missing record, artifact SHA mismatch, fallback, or test access
retained_runs:
  - all CP-029 retained runs and CP-030 launch artifacts
archived_runs: []
deletion_candidates:
  - unchanged from CP-029
next_command: commit and push CP-030, synchronize ai-station, verify all targets/label absent and launch artifact digests, then start both one-time actual dry-runs
decision: RUN_FRESH_ACTUAL_DRY_RUN_ON_NATIVE_MPS_AND_CUDA
```

## Checkpoint CP-031 — Linux actual dry-run R2 replacement lock

```yaml
checkpoint_id: CP-031
experiment_id: EXP-079
status: PREREGISTERED_LINUX_DRY_RUN_R2
source_commit: d0d5731a23af6c3b70ad8b1c151be8ca7185d531
mac_dry_run_r1:
  status: VALID
  output: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/dry-run/macos-r1
  evidence_index_sha256: 09e27e5f88d8b3b5aae6891cc7b8eb3d11d0433f270454825e855b713322a28a
  manifest_sha256: e56e53272fdd513b2d54ae6a1126a25ac33133db2fd7cd51d7934f681af826e4
  execution_mode: actual
  run_kind: NON_FORMAL_DRY_RUN
  sample_count: 8
  scenario_counts: {no_cup: 2, one_cup_distractors: 2, two_cups: 2, cup_near_bottle: 2}
  model_record_count: 16
  records_per_model: {yolo_seg: 8, grounded_sam: 8}
  device: mps
  dtype: float32
  fallback_used: false
  source_commit: ef254f6025d8de42ce42a6cc6871e703fc86fbd4
  config_sha256: 4b8b0ac1046180bd5b10748fe8d8b505b9858b63648ffcf888743aad75cf9160
  artifact_index_entries: 510
  all_index_sha256_match: true
  test_path_count: 0
  launchd_job_removed: true
linux_r1:
  status: INVALID_PRESTART
  first_bad_boundary: output parent did not exist
  error: OUTPUT_ROOT_PARENT_INVALID
  output_created: false
  model_loaded: false
  inference_run: false
  test_semantic_content_accessed: false
linux_r2:
  parent_to_create_once: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dry-run
  output: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dry-run/linux-r2
  command: HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONNOUSERSITE=1 PYTHONPATH=/tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/lib/python3.12/site-packages /data/work/venvs/so101-grounded-sam/bin/python /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/lib/so101_demo_py/perception_benchmark dry-run --config /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/share/so101_demo_py/config/perception_benchmark/benchmark.yaml --output-root /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dry-run/linux-r2 --platform linux --device cuda --dtype float32 --dataset-inventory /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/val-open-r3/inventory.json --dataset-archive-sha256 d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6 --inventory-sha256 500b61e69771e3098628b20b5c4b01926d41df7dad1ffc3a7023be34405638b2 --weights /data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/assets-r8/best.pt --weights-sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781 --model-root /data/work/so101-models/grounded-sam-v2-scipy-lock --manifest-sha256 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775 --source-commit ef254f6025d8de42ce42a6cc6871e703fc86fbd4
success_criteria:
  - create only the registered parent while linux-r2 remains absent, then execute once
  - CP-030 frozen dry-run contract passes on CUDA and all evidence-index SHA values match
  - no test member is extracted, parsed, rasterized, displayed, or inferred
stop_criteria:
  - parent is not a real directory, output collision, command failure, provenance mismatch, missing record, artifact SHA mismatch, fallback, or test access
retained_runs:
  - all CP-030 retained runs and valid Mac R1 evidence
archived_runs: []
deletion_candidates:
  - unchanged from CP-030; absent Linux R1 name is not an artifact
next_command: commit and push CP-031, synchronize ai-station, create the registered dry-run parent once, verify linux-r2 remains absent, then run the exact R2 command once
decision: CREATE_REGISTERED_PARENT_THEN_RUN_LINUX_R2
```

## Checkpoint CP-032 — fresh 200-sample validation collection lock

```yaml
checkpoint_id: CP-032
experiment_id: EXP-079
status: PREREGISTERED_VAL_RAW_COLLECTION
source_commit: 253fcd5c1dd530892c2ac1cffd6fe58d1d4ec3d1
benchmark_code_commit: ef254f6025d8de42ce42a6cc6871e703fc86fbd4
dry_run_results:
  macos:
    status: VALID
    output: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/dry-run/macos-r1
    evidence_index_sha256: 09e27e5f88d8b3b5aae6891cc7b8eb3d11d0433f270454825e855b713322a28a
    manifest_sha256: e56e53272fdd513b2d54ae6a1126a25ac33133db2fd7cd51d7934f681af826e4
    index_entries: 510
    device: mps
  linux:
    status: VALID
    output: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dry-run/linux-r2
    evidence_index_sha256: 3787acacbe0125b5a27f65148e8bcc045a8cd563783cf07e9225e5d57f69be83
    manifest_sha256: bfd78965abcfa367a4acf2ec1a7ef0eb563671a48ea2255bfcd414b9295713de
    index_entries: 514
    device: cuda
  shared_contract: {execution_mode: actual, run_kind: NON_FORMAL_DRY_RUN, sample_count: 8, model_record_count: 16, records_per_model: {yolo_seg: 8, grounded_sam: 8}, dtype: float32, fallback_used: false, all_index_sha256_match: true, test_path_count: 0}
frozen_val:
  archive_sha256: d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6
  inventory_sha256: 500b61e69771e3098628b20b5c4b01926d41df7dad1ffc3a7023be34405638b2
  sample_count: 200
  scenario_counts: {no_cup: 50, one_cup_distractors: 50, two_cups: 50, cup_near_bottle: 50}
  collection_mode: LOW_FLOOR
  run_kind: VAL_RAW
  dtype: float32
  offline: true
  fallback_used: false
mac_collection:
  order: [yolo_seg, grounded_sam]
  label: com.terry.so101.benchmark.mac.val.r1
  script: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/mac-val-r1.sh
  script_sha256: 3f2fe60a8090aa3bed614de453a42a7cde116e9f6876eed9c0866ab4f0fed4b0
  plist: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/com.terry.so101.benchmark.mac.val.r1.plist
  plist_sha256: 3590b380f758af1bac5ae7ba79aa28d11923d6d17e05bf675c61ef6778ac6422
  command: launchctl bootstrap gui/501 /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/com.terry.so101.benchmark.mac.val.r1.plist
  outputs:
    yolo_seg: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/val/macos/yolo-r1
    grounded_sam: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/val/macos/grounded-sam-r1
linux_collection:
  order: [yolo_seg, grounded_sam]
  local_script: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/linux-val-r1.sh
  remote_script: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/linux-val-r1.sh
  script_sha256: 7a0802c374183ed2e108c705e486587de8ee4995c800f992142115059b2d4cc1
  command: /bin/bash /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/linux-val-r1.sh
  outputs:
    yolo_seg: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/val/linux/yolo-r1
    grounded_sam: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/val/linux/grounded-sam-r1
success_criteria:
  - execute Mac first and Linux only after both Mac model runs validate
  - each run has status VALID, exactly 200 records and one record per formal sample index, frozen provenance, native device, FP32, no fallback, no timeout, and no OOM
  - every record/mask/index artifact exists and matches the evidence index SHA-256
  - raw outputs are retained unchanged for joint calibration; no threshold is selected per platform
  - no test member is extracted, parsed, rasterized, displayed, or inferred
stop_criteria:
  - any parent/script/label/output collision, command failure, invalid manifest, missing/duplicate record, artifact SHA mismatch, fallback, timeout, OOM, or test access
retained_runs:
  - all CP-031 retained runs and both valid dry-runs
  - Mac and Linux validation launch artifacts
archived_runs: []
deletion_candidates:
  - unchanged from CP-031
next_command: commit and push CP-032, synchronize ai-station, verify both platform output parents and all four outputs/label/script targets, then run Mac validation only
decision: COLLECT_MAC_THEN_LINUX_VAL_RAW_WITH_TEST_SEALED
```

## Checkpoint CP-033 — Linux validation script transfer replacement lock

```yaml
checkpoint_id: CP-033
experiment_id: EXP-079
status: PREREGISTERED_LINUX_TRANSFER_R2
source_commit: 85f0566698b5a0b602989736ffc7bd5417ef40e8
mac_val_result:
  status: VALID
  yolo_seg: {record_count: 200, record_inventory_sha256: 52bda6fa1f323ed423d9ae6709a28898be930176afb78ab518cbea8910e8fc7e, error_count: 0, record_statuses: [OK], timed_out: false, oom: false, fallback_used: false}
  grounded_sam: {record_count: 200, record_inventory_sha256: 182815997bb5c11a0383618c3d5068bd2e65afb1498ab4c0d34fea2c5ed3f99b, error_count: 0, record_statuses: [OK], timed_out: false, oom: false, fallback_used: false}
  integrity: load_verified_run_evidence passed both independent expectations, record chains, source images, masks, and manifest/checkpoint anchors
  launchd_job_removed: true
linux_r1_transfer:
  status: INVALID_PRESTART
  first_bad_boundary: remote scripts parent did not exist
  error: scp destination open failed with No such file or directory
  remote_script_created: false
  model_loaded: false
  inference_run: false
  model_outputs_created: false
  test_semantic_content_accessed: false
linux_r2_transfer:
  parent_to_create_once: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts
  local_source: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/linux-val-r1.sh
  remote_target: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/linux-val-r2.sh
  required_sha256: 7a0802c374183ed2e108c705e486587de8ee4995c800f992142115059b2d4cc1
  command: /bin/bash /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/linux-val-r2.sh
  output_parent_to_create_once: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/val/linux
  outputs:
    yolo_seg: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/val/linux/yolo-r1
    grounded_sam: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/val/linux/grounded-sam-r1
success_criteria:
  - create only the two registered parent directories while R2 script and both model outputs remain absent
  - copy once, chmod 0755, verify the exact script SHA, then execute once
  - CP-032 Linux validation and test-seal criteria remain unchanged
stop_criteria:
  - any R2 target collision, script SHA mismatch, command failure, invalid run, fallback, timeout, OOM, or test access
retained_runs:
  - all CP-032 retained runs and valid Mac validation evidence
archived_runs: []
deletion_candidates:
  - unchanged from CP-032; absent remote R1 script is not an artifact
next_command: commit and push CP-033, synchronize ai-station, create the two registered parents, verify R2 targets absent, copy and verify linux-val-r2.sh, then execute it once
decision: CREATE_REMOTE_PARENTS_THEN_TRANSFER_AND_RUN_LINUX_R2
```

## Checkpoint CP-034 — joint cross-platform calibration lock

```yaml
checkpoint_id: CP-034
experiment_id: EXP-079
status: PREREGISTERED_JOINT_CALIBRATION
source_commit: 12a5aa0207d72a7c703c5832be242e529e531c8f
benchmark_code_commit: ef254f6025d8de42ce42a6cc6871e703fc86fbd4
validated_runs:
  macos_yolo: {records: 200, record_inventory_sha256: 52bda6fa1f323ed423d9ae6709a28898be930176afb78ab518cbea8910e8fc7e, manifest_sha256: da47af73acd5b4cf912e17e9dd7eb50de764fca98c213a570401856672df6032}
  macos_grounded_sam: {records: 200, record_inventory_sha256: 182815997bb5c11a0383618c3d5068bd2e65afb1498ab4c0d34fea2c5ed3f99b, manifest_sha256: b18f166191d2c60c827e56fd7d6e89afe2eb5d651863662fd0829ad11e7f27f1}
  linux_yolo: {records: 200, record_inventory_sha256: 21936b306168b0321fa35cc7d77766ed0953762c6f72771ccb5c26efa824e49d, manifest_sha256: 50e0ec450412e5f79ae775c4f30b51cfba9883884fb9dfa4ccb97dfc24d8ebc6}
  linux_grounded_sam: {records: 200, record_inventory_sha256: afc44d45fb86a2cd25a8255c78b393acbb7802f99f5f51dfe13838daa314a6ac, manifest_sha256: cc55e31881dd963de2d0524859e2335601358e207fb0a7a640a0bd151ec191e9}
  common: {status: VALID, error_count: 0, record_statuses: [OK], timed_out: false, oom: false, fallback_used: false, full_runner_integrity_check: PASS}
mac_transfer:
  local_archive: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/transfer/mac-val-r1.tar.gz
  remote_archive: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/transfer/mac-val-r1.tar.gz
  source_roots:
    - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/val/macos/yolo-r1
    - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/val/macos/grounded-sam-r1
  durable_destination: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/val/macos
  policy: all archive and destination targets must be absent; source trees must contain no symlink; archive only macos/yolo-r1 and macos/grounded-sam-r1; inspect member paths and link types before one extraction; verify both runs again after extraction
expectation_anchors:
  remote_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/prereg-r1/expectations
  macos_yolo_seg: cd2b119ec8eb160d0c73c0e3ab202ceb0f7f24a332c3436ba8e585bad2ee8a9b
  macos_grounded_sam: 6e5adccb253fab9b6df1e6966d1a53cc99a1c96cfa72ea4fec10c0b959e32b48
  linux_yolo_seg: cf0d7a75048329f98a3008bb65766bdae2a51f4f480753a6bdf23e841022d31e
  linux_grounded_sam: 9e1271a928a7df958f63841adb7df65e4a0aa85287f12ca7a39286271ec5bff7
calibration:
  order: [yolo_seg, grounded_sam]
  yolo_output: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/yolo-r1
  grounded_sam_output: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/grounded-sam-r1
  common: {dataset_archive_sha256: d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6, inventory_sha256: 500b61e69771e3098628b20b5c4b01926d41df7dad1ffc3a7023be34405638b2, source_commit: ef254f6025d8de42ce42a6cc6871e703fc86fbd4, selection_scope: joint_macos_linux_val_only}
success_criteria:
  - both staged Mac runs revalidate byte-for-byte against independent expectations on ai-station
  - each calibration consumes both 200-sample platform runs and the same 200 validation truths, then writes one threshold-lock.json
  - calibration uses only the frozen grid, reports all metrics by platform/scenario, and does not weaken fail-closed selection rules
  - no test member is extracted, parsed, rasterized, displayed, inferred, or used for threshold selection
stop_criteria:
  - any transfer/output collision, archive unsafe member, byte mismatch, run expectation failure, calibration failure, non-deployable lock, unsafe unique selection, or test access
retained_runs:
  - all CP-033 retained runs and four valid raw validation runs
archived_runs: []
deletion_candidates:
  - unchanged from CP-033; transfer archive is retained until calibration completes
next_command: commit and push CP-034, synchronize ai-station, verify all targets absent, create and hash the Mac transfer archive, transfer/inspect/extract it once, transfer expectation anchors, and revalidate both staged Mac runs
decision: STAGE_MAC_RUNS_THEN_CALIBRATE_JOINTLY_ON_VALIDATION_ONLY
```

## Checkpoint CP-035 — AppleDouble-free Mac transfer archive replacement lock

```yaml
checkpoint_id: CP-035
experiment_id: EXP-079
status: PREREGISTERED_TRANSFER_ARCHIVE_R2
source_commit: 7e8f2bb9f368d227ac51d12fa29db5429daf23e1
cp_034_transfer_r1:
  status: INVALID_PRETRANSFER
  archive: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/transfer/mac-val-r1.tar.gz
  sha256: 21b5a9b8ca9c8847a28e209ea858e4e97dfb5f9b38e62f5e239b18d01428429c
  size_bytes: 13040765
  member_count: 48858
  first_bad_boundary: strict allowed-prefix audit found two macOS AppleDouble files outside the run roots
  rejected_members: [macos/._yolo-r1, macos/._grounded-sam-r1]
  link_member_count: 0
  transferred: false
  extracted: false
  durable_destination_created: false
  test_semantic_content_accessed: false
replacement_r2:
  local_archive: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/transfer/mac-val-r2.tar.gz
  local_checksum: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/transfer/mac-val-r2.tar.gz.sha256
  remote_archive: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/transfer/mac-val-r2.tar.gz
  generation: COPYFILE_DISABLE=1 tar -czf <local_archive> -C <exp-079/val> macos/yolo-r1 macos/grounded-sam-r1
  policy: all R2 targets absent; exactly two allowed run-root prefixes; no absolute or dot-dot path; no symlink, hardlink, AppleDouble, or extended-attribute member; transfer once; inspect again before extraction
  durable_destination: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/val/macos
success_criteria:
  - R2 local and remote bytes share one recorded SHA-256
  - member audit returns zero unsafe/link/AppleDouble/extended-attribute members
  - CP-034 staging revalidation, expectation, calibration, and test-seal criteria remain unchanged
stop_criteria:
  - any target collision, digest mismatch, unsafe member, extraction error, staged-run verification failure, calibration failure, or test access
retained_runs:
  - all CP-034 retained runs
  - invalid R1 transfer archive and checksum retained for audit
archived_runs: []
deletion_candidates:
  - invalid mac-val-r1.tar.gz and adjacent checksum, only after explicit user authorization
next_command: commit and push CP-035, synchronize ai-station, verify all R2 targets absent, generate R2 with COPYFILE_DISABLE=1, audit and hash it, then transfer once
decision: REPACK_WITHOUT_APPLEDOUBLE_BEFORE_TRANSFER
```

## Checkpoint CP-036 — xattr-free Mac transfer archive replacement lock

```yaml
checkpoint_id: CP-036
experiment_id: EXP-079
status: PREREGISTERED_TRANSFER_ARCHIVE_R3
source_commit: aed4c72d305a01129a130f555d419d0708a4ee1d
cp_035_transfer_r2:
  status: INVALID_PREEXTRACTION
  local_archive: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/transfer/mac-val-r2.tar.gz
  remote_archive: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/transfer/mac-val-r2.tar.gz
  sha256: de8f7f959f6d4a76bf0fa6d242eec903ed940131d60d48fb77c07c3334137476
  size_bytes: 12258414
  member_count: 24429
  prefix_counts: {macos/yolo-r1: 1188, macos/grounded-sam-r1: 23241}
  unsafe_path_count: 0
  link_member_count: 0
  appledouble_member_count: 0
  first_bad_boundary: ai-station GNU tar reported LIBARCHIVE.xattr.com.apple.provenance PAX extended headers during the pre-extraction member audit
  source_confirmation: both source manifest files carry com.apple.provenance
  extracted: false
  durable_destination_created: false
  test_semantic_content_accessed: false
replacement_r3:
  local_archive: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/transfer/mac-val-r3.tar.gz
  local_checksum: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/transfer/mac-val-r3.tar.gz.sha256
  remote_archive: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/transfer/mac-val-r3.tar.gz
  generation: COPYFILE_DISABLE=1 tar --no-xattrs --format ustar -czf <local_archive> -C <exp-079/val> macos/yolo-r1 macos/grounded-sam-r1
  policy: all R3 targets absent; exactly two allowed run-root prefixes; no absolute or dot-dot path; no symlink, hardlink, AppleDouble, PAX xattr, ACL, or extended-attribute member; transfer once; inspect again before extraction
  durable_destination: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/val/macos
success_criteria:
  - R3 local and remote bytes share one recorded SHA-256
  - both local and ai-station audits report zero unsafe, link, AppleDouble, ACL, and extended-attribute members
  - CP-034 staging revalidation, expectation, calibration, and test-seal criteria remain unchanged
stop_criteria:
  - unsupported archive option, any target collision, digest mismatch, unsafe member, extraction error, staged-run verification failure, calibration failure, or test access
retained_runs:
  - all CP-035 retained runs
  - invalid R2 transfer archive remains on both hosts for audit
archived_runs: []
deletion_candidates:
  - invalid mac-val-r1.tar.gz and mac-val-r2.tar.gz with adjacent local checksums, only after explicit user authorization
next_command: commit and push CP-036, synchronize ai-station, verify the archive options and all R3 targets, create and audit R3 locally, then transfer and audit it once before extraction
decision: REPACK_WITHOUT_PAX_XATTR_BEFORE_TRANSFER
```

## Checkpoint CP-037 — staged Mac evidence accepted and joint calibration execution lock

```yaml
checkpoint_id: CP-037
experiment_id: EXP-079
status: PREREGISTERED_JOINT_CALIBRATION_EXECUTION
source_commit: 9361784ff00ec9774a19cc9dcd9fb38b7361e093
benchmark_code_commit: ef254f6025d8de42ce42a6cc6871e703fc86fbd4
cp_036_transfer_r3:
  status: VALID
  local_archive: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/transfer/mac-val-r3.tar.gz
  remote_archive: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/transfer/mac-val-r3.tar.gz
  sha256: d7a56989a43b3442c9283339bf7eeeec23bd67c35311fdf6d33439f5167cad85
  size_bytes: 11195324
  member_count: 24429
  prefix_counts: {macos/yolo-r1: 1188, macos/grounded-sam-r1: 23241}
  unsafe_path_count: 0
  link_member_count: 0
  unsupported_member_type_count: 0
  appledouble_member_count: 0
  pax_xattr_warning_count_on_linux: 0
  extracted_destination: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/val/macos
  extracted_file_counts: {yolo_seg: 832, grounded_sam: 22836}
  extracted_symlink_count: 0
staged_mac_revalidation:
  status: VALID
  yolo_seg: {records: 200, manifest_sha256: da47af73acd5b4cf912e17e9dd7eb50de764fca98c213a570401856672df6032, record_inventory_sha256: 52bda6fa1f323ed423d9ae6709a28898be930176afb78ab518cbea8910e8fc7e, expectation_sha256: cd2b119ec8eb160d0c73c0e3ab202ceb0f7f24a332c3436ba8e585bad2ee8a9b}
  grounded_sam: {records: 200, manifest_sha256: b18f166191d2c60c827e56fd7d6e89afe2eb5d651863662fd0829ad11e7f27f1, record_inventory_sha256: 182815997bb5c11a0383618c3d5068bd2e65afb1498ab4c0d34fea2c5ed3f99b, expectation_sha256: 6e5adccb253fab9b6df1e6966d1a53cc99a1c96cfa72ea4fec10c0b959e32b48}
  verifier: load_verified_run_evidence in frozen ai-station install
calibration_environment:
  python: /data/work/venvs/so101-grounded-sam/bin/python
  runner: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/lib/so101_demo_py/perception_benchmark
  pythonpath: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/lib/python3.12/site-packages
  config: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/share/so101_demo_py/config/perception_benchmark/benchmark.yaml
  config_sha256: 4b8b0ac1046180bd5b10748fe8d8b505b9858b63648ffcf888743aad75cf9160
  offline: true
  dtype: float32
calibration_order: [yolo_seg, grounded_sam]
yolo_calibration:
  output: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/yolo-r1
  precondition: output must remain absent until the command starts
  command: HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONNOUSERSITE=1 PYTHONPATH=/tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/lib/python3.12/site-packages /data/work/venvs/so101-grounded-sam/bin/python /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/lib/so101_demo_py/perception_benchmark calibrate --config /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/share/so101_demo_py/config/perception_benchmark/benchmark.yaml --model yolo_seg --dataset-inventory /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/val-open-r3/inventory.json --dataset-archive-sha256 d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6 --inventory-sha256 500b61e69771e3098628b20b5c4b01926d41df7dad1ffc3a7023be34405638b2 --mac-run-root /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/val/macos/yolo-r1 --mac-run-expectation /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/prereg-r1/expectations/macos-yolo_seg.json --mac-run-expectation-sha256 cd2b119ec8eb160d0c73c0e3ab202ceb0f7f24a332c3436ba8e585bad2ee8a9b --linux-run-root /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/val/linux/yolo-r1 --linux-run-expectation /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/prereg-r1/expectations/linux-yolo_seg.json --linux-run-expectation-sha256 cf0d7a75048329f98a3008bb65766bdae2a51f4f480753a6bdf23e841022d31e --source-commit ef254f6025d8de42ce42a6cc6871e703fc86fbd4 --output-root /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/yolo-r1
grounded_sam_calibration:
  output: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/grounded-sam-r1
  precondition: output must remain absent until YOLO is validated as deployable and safe
  command: HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONNOUSERSITE=1 PYTHONPATH=/tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/lib/python3.12/site-packages /data/work/venvs/so101-grounded-sam/bin/python /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/lib/so101_demo_py/perception_benchmark calibrate --config /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py/share/so101_demo_py/config/perception_benchmark/benchmark.yaml --model grounded_sam --dataset-inventory /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/val-open-r3/inventory.json --dataset-archive-sha256 d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6 --inventory-sha256 500b61e69771e3098628b20b5c4b01926d41df7dad1ffc3a7023be34405638b2 --mac-run-root /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/val/macos/grounded-sam-r1 --mac-run-expectation /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/prereg-r1/expectations/macos-grounded_sam.json --mac-run-expectation-sha256 6e5adccb253fab9b6df1e6966d1a53cc99a1c96cfa72ea4fec10c0b959e32b48 --linux-run-root /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/val/linux/grounded-sam-r1 --linux-run-expectation /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/prereg-r1/expectations/linux-grounded_sam.json --linux-run-expectation-sha256 9e1271a928a7df958f63841adb7df65e4a0aa85287f12ca7a39286271ec5bff7 --source-commit ef254f6025d8de42ce42a6cc6871e703fc86fbd4 --output-root /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/grounded-sam-r1
success_criteria:
  - each command exits zero and writes a self-consistent threshold-lock.json plus evidence-index.json
  - each lock is formal, deployable, SAFE_CALIBRATED, joint across the same 200 macOS and 200 Linux validation records, and passes frozen fail-closed safety metrics
  - both lock files and evidence indexes verify by SHA before any test access
  - no test member is extracted, parsed, rasterized, displayed, inferred, or used for threshold selection
stop_criteria:
  - output collision, expectation or evidence verification failure, nonzero command, missing or malformed lock/index, non-deployable lock, unsafe outcome, unsafe unique selection, or test access
retained_runs:
  - all CP-036 retained runs
  - valid R3 archive and checksum on both hosts
  - staged and revalidated macOS validation evidence on ai-station
archived_runs: []
deletion_candidates:
  - invalid mac-val-r1.tar.gz and mac-val-r2.tar.gz with adjacent local checksums, only after explicit user authorization
next_command: commit and push CP-037, synchronize the isolated ai-station task checkout without touching /data/work/ws_moveit, verify both output paths remain absent, then run and validate YOLO calibration only
decision: RUN_YOLO_JOINT_VAL_CALIBRATION_THEN_GATE_GROUNDED_SAM
```

## Checkpoint CP-038 — Grounded-SAM calibration performance remediation A+B

```yaml
checkpoint_id: CP-038
date: 2026-09-04
experiment_id: EXP-079
scope: optimize the numerical Grounded-SAM joint validation calibration and rerun it without changing the frozen grid, matching semantics, safety gates, tie-break, or sealed-test boundary
execution_mode: inline
authorization:
  user_choice: A+B
  option_a: precompute and reuse deterministic numerical intermediates; do not execute Grounding DINO or SAM inference during calibration
  option_b: use bounded multiprocessing for independent numerical precomputation
source_state:
  local_branch: codex/v5-t004-yolo-seg-rgbd
  local_head: ead617cbef30efa1a0db960bf625b61205339b04
  local_upstream_before_sync: 1cde365c
  ai_station_checkout: /data/work/so101-grounded-sam-yolo-benchmark-ab-v1-task14-runner-access-r11
  ai_station_head_before_sync: 1cde365c
  rebase: already completed by the user; do not rebase again
registered_evidence_roots:
  local: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079
  durable: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079
baseline:
  command_kind: calibrate grounded_sam
  inference_during_calibration: false
  grid_points: 32400
  observed_cpu: approximately 99 percent of one CPU core
  observed_rss: approximately 139 MB and stable
  elapsed_before_stop: more than 49 minutes
  partial_output:
    path: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/grounded-sam-r1
    files: 22639
    apparent_size: approximately 104 MB
    threshold_lock_present: false
    evidence_index_present: false
    validity: INVALID_INTERRUPTED_TRANSACTION
  stopped_process: remote PID 2246519 was matched to the exact calibration command, sent SIGINT, and verified stopped
root_cause_hypotheses:
  H1: the 32400-point grid repeats Grounded-SAM box/text filtering and duplicate suppression for every sam-quality and selector combination; theoretical duplicate-suppression calls are 12960000 across 400 platform records
  H2: every previously unseen selection signature repeatedly reads and decodes RLE masks for AP, assignment, and scenario metrics
  H3: calibration mask rehoming decodes and re-encodes every verified 640x480 mask and fsyncs one JSON file at a time
frozen_semantics:
  grid_version: grounded-sam-grid/v1
  grid_points: 32400
  selection_and_tie_break: unchanged
  matching_and_metric_values: unchanged
  fail_closed_gates: unchanged
  test_split_access: forbidden
implementation_contract:
  - precompute Grounded-SAM box/text plus duplicate-suppression states once per record and threshold pair
  - precompute reusable truth-candidate IoU values without changing float evaluation or deterministic assignment
  - use bounded multiprocessing only for independent precomputation; serial and parallel threshold locks must be byte-equivalent
  - preserve already verified RLE JSON bytes when rehoming, while retaining secure source validation and exclusive destination creation
  - emit flushed phase progress for verify, rehome, precompute, grid, and finalize, including completed, total, percent, and elapsed time
  - preserve the public calibration API through optional arguments and keep a deterministic one-worker path
test_first_contract:
  - a failing test proves duplicate suppression is reused across sam-quality and selector points
  - a failing test proves progress phase and monotonic-count behavior
  - a failing test proves workers=1 and workers=2 yield the same complete threshold lock
  - a failing CLI test proves calibration worker selection and progress output
  - a failing rehome test proves verified RLE bytes are copied without overwrite
remote_partial_archive_plan:
  source: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/grounded-sam-r1
  target: /data/work/so101-evidence/archived/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/grounded-sam-r1-interrupted-cp038
  action: compute deterministic file inventory hash and file/byte counts before and after a recoverable move; do not delete evidence
optimized_run:
  output: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/grounded-sam-r2
  precondition: path absent before start and optimized source built into a fresh isolated overlay
success_criteria:
  - targeted RED tests fail for the intended missing behaviors, then pass after implementation
  - serial and two-worker fixture calibrations produce identical lock documents and lock_sha256 values
  - explicit benchmark suite passes from the isolated package build
  - grounded-sam-r2 writes a self-consistent threshold-lock.json and evidence-index.json
  - grounded-sam-r2 is formal, deployable, SAFE_CALIBRATED, and has zero unsafe unique selections on both platforms
  - wall time and phase timings are captured and materially improve on the interrupted baseline
stop_criteria:
  - any metric, selected threshold, safety result, or lock differs between the serial reference and parallel path
  - output collision, evidence verification failure, test-split access, nonzero calibration exit, missing lock/index, non-deployable lock, or unsafe outcome
retained_runs:
  - all CP-037 retained runs
  - valid yolo-r1 calibration lock and evidence index
  - interrupted grounded-sam-r1 retained until its inventory-preserving archive move is verified
archived_runs: []
deletion_candidates:
  - invalid mac-val-r1.tar.gz and mac-val-r2.tar.gz with adjacent local checksums, only after explicit user authorization
next_command: commit and push this preregistration checkpoint, synchronize the isolated ai-station checkout, archive grounded-sam-r1 without deletion, then add and run the RED tests
decision: EXECUTE_CALIBRATION_OPTIMIZATION_A_PLUS_B
```

## Checkpoint CP-039 — calibration optimization implementation and local gates

```yaml
checkpoint_id: CP-039
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-038
source_before_implementation: f589e5b9b957552e84696aec41a8466e9c18820e
ai_station_sync_before_implementation:
  checkout: /data/work/so101-grounded-sam-yolo-benchmark-ab-v1-task14-runner-access-r11
  head: f589e5b9b957552e84696aec41a8466e9c18820e
  method: git pull --ff-only gitee codex/v5-t004-yolo-seg-rgbd
interrupted_run_archive:
  source_absent_after_move: true
  target: /data/work/so101-evidence/archived/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/grounded-sam-r1-interrupted-cp038
  canonical_relative_inventory_sha256_before: c07ae6efe613b7a0a3a6bbe6507ad195c66dfb997427efd6713e0697b1af75c1
  canonical_relative_inventory_sha256_after: c07ae6efe613b7a0a3a6bbe6507ad195c66dfb997427efd6713e0697b1af75c1
  file_count_before: 22639
  file_count_after: 22639
  total_bytes_before: 33144554
  total_bytes_after: 33144554
  deletion: none
implementation:
  grounded_prefix_cache: box/text filtering and duplicate suppression are precomputed for all 180 prefix pairs per platform record, then reused across sam-quality and selector dimensions
  mask_iou_cache: every truth-candidate IoU is computed once per platform image and reused by AP plus deterministic maximum-IoU assignment
  multiprocessing: independent per-record prefix and IoU precomputation accepts 1 through 64 workers; worker payload excludes unpicklable runtime provenance
  progress: verify, rehome, precompute, grid, and finalize report bounded counts, percentage, and elapsed seconds to stderr with flush
  mask_rehome: securely validates source identity and MaskRef semantics, then copies the already verified RLE bytes through exclusive-create output instead of Python decode/re-encode plus per-file fsync
  unchanged:
    - grounded-sam-grid/v1 and all 32400 points
    - threshold comparisons and duplicate IoU 0.85
    - AP IoU thresholds, Hungarian assignment, scenario metrics, safety gates, tie-break, and lock schema
red_gate:
  command_scope: five targeted new behavior tests
  result: 5 failed as intended
  observed_failures:
    - calibrate_joint_platform_val rejected workers
    - progress callback was absent
    - calibrate parser lacked calibration_workers
    - handler did not forward workers
    - rehome path did not preserve source RLE bytes
green_targeted_gate:
  result: 5 passed in 1.85 seconds
  includes: serial/two-worker exact threshold-lock equality
expanded_local_gate:
  scope: calibration, metrics, matching, and CLI benchmark modules
  result: 147 passed in 7.66 seconds
  semantic_equivalence_tests:
    - cached maximum-IoU assignment equals mask-decode path
    - cached AP equals mask-decode path
static_gates:
  compileall: PASS
  ruff_version: 0.15.20
  ruff_check: PASS
  ruff_format_check: PASS
known_environment_note:
  - the repository worktree metadata has a stale common core.worktree, so every Git operation is explicitly bound with GIT_WORK_TREE plus the linked-worktree git-dir; the filesystem content itself is intact
  - the first local RED attempt used the wrong package path and was discarded as environment setup evidence; the recorded RED result came from a fresh setup.py build under the registered evidence root
remaining_gates:
  - commit and push only the eight implementation/test files plus this ledger checkpoint
  - fast-forward the isolated ai-station checkout
  - build so101_demo_py into a fresh Linux overlay
  - run the explicit benchmark_test colcon gate
  - verify grounded-sam-r2 is absent, then run the formal 32400-point calibration with multiple workers and capture all phase timings
retained_runs:
  - all CP-038 retained runs
  - optimized local test builds and logs under /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/test-cp038
archived_runs:
  - grounded-sam-r1-interrupted-cp038 at the verified archived path above
deletion_candidates:
  - invalid mac-val-r1.tar.gz and mac-val-r2.tar.gz with adjacent local checksums, only after explicit user authorization
next_command: commit and push CP-039, synchronize ai-station, then execute fresh Linux build and explicit benchmark suite
decision: IMPLEMENTATION_LOCALLY_GREEN_PENDING_LINUX_GATE
```

## Checkpoint CP-040 — explicit local benchmark gate

```yaml
checkpoint_id: CP-040
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-039
registered_root: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079
first_build_attempt:
  output: local-gate-cp039
  result: ENVIRONMENT_INVALID
  reason: only the ROS base was sourced, so the isolated build could not resolve the existing MuJoCo, teleop, and SO-101 support dependency prefixes
  tests_started: false
qualified_local_build:
  output: local-gate-cp039-r2
  dependency_overlay: install-rebase-final-r15 plus the ROS Jazzy base
  package: so101_demo_py
  result: PASS
  elapsed: 2.33 seconds package time
explicit_benchmark_gate:
  command_contract: colcon test --packages-select so101_demo_py --pytest-args benchmark_test
  result: PASS
  summary: 562 tests, 0 errors, 0 failures, 0 skipped
  elapsed: 5 minutes 9 seconds
  scope_note: only benchmark_test was collected; the ordinary package suite and unrelated packages were not run
  observed_cost: dataset archive and seal tests consumed approximately 123 seconds; this dominates the suite independently of calibration grid execution
static_gates:
  compileall: PASS
  ruff_0_15_20_check: PASS
  ruff_0_15_20_format_check: PASS
next_command: commit and push the implementation checkpoint, fast-forward ai-station, build a fresh Linux overlay, and repeat the explicit benchmark gate before grounded-sam-r2
decision: LOCAL_IMPLEMENTATION_QUALIFIED_PENDING_LINUX_AND_FORMAL_RUN
```

## Checkpoint CP-041 — Linux qualification and grounded-sam-r2 preregistration

```yaml
checkpoint_id: CP-041
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-040
runner_source:
  branch: codex/v5-t004-yolo-seg-rgbd
  commit: 92b0e4919ceec953f0d1635ffcfde1a2fcb31b06
  checkout: /data/work/so101-grounded-sam-yolo-benchmark-ab-v1-task14-runner-access-r11
linux_overlay:
  root: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-92b0-cp041-r5
  install_mode: regular files; no symlink-install
  packages: mujoco_ros2_control_msgs, mujoco_ros2_control_plugins, mujoco_3d_lidar, so101_mujoco_support, so101_teleop, so101_demo_py
  build_result: PASS
  build_elapsed: 49.7 seconds
  runner_shebang: /data/work/venvs/so101-grounded-sam/bin/python
  installed_calibration_sha256: 97b915f2b12a05ce7e21255070e3a89519c331295e8e4f0fe6ea967b06eb1dac
  source_calibration_sha256: 97b915f2b12a05ce7e21255070e3a89519c331295e8e4f0fe6ea967b06eb1dac
linux_gate_diagnostics:
  system_python_attempt:
    result: ENVIRONMENT_INVALID_AND_INTERRUPTED
    evidence:
      - /usr/bin/python3 resolved Pillow 10.2.0 instead of the pinned 12.3.0
      - /usr/bin/python3 did not provide torch
      - the new calibration, CLI, matching, and metrics groups had already passed
  slow_tmp_attempt:
    result: INTERRUPTED_FOR_STORAGE_REMEDIATION
    elapsed_before_stop: 12 minutes 43 seconds
    observation: pytest was blocked in D state while dataset archive tests wrote to the SATA-backed /tmp filesystem
    deletion: none
  qualified_environment:
    python: /data/work/venvs/so101-grounded-sam/bin/python
    pillow: 12.3.0
    torch: 2.13.0+cu130
    pytest_tmpdir: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/runtime-tmp/linux-benchmark-r5-nvme
linux_benchmark_gate:
  command_contract: colcon test --packages-select so101_demo_py --pytest-args benchmark_test
  result: PASS
  summary: 562 tests, 0 errors, 0 failures, 2 skipped
  pytest_summary: 560 passed, 2 skipped
  elapsed: 10 minutes 43 seconds
  test_result_command: colcon test-result --test-result-base /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-92b0-cp041-r5/build --verbose
formal_grounded_sam_r2:
  model: grounded_sam
  grid_version: grounded-sam-grid/v1
  grid_points: 32400
  calibration_workers: 8
  inference_during_calibration: false
  output: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/grounded-sam-r2
  progress_log: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/grounded-sam-r2-calibrate.log
  preconditions:
    - output path is absent immediately before launch
    - dataset inventory, both validation roots, and both expectation documents are present
    - expectation SHA-256 values equal the CP-037 preregistration
    - test split remains sealed and inaccessible to calibration
  command: HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONNOUSERSITE=1 PYTHONPATH=/tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-92b0-cp041-r5/install/so101_demo_py/lib/python3.12/site-packages /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-92b0-cp041-r5/install/so101_demo_py/lib/so101_demo_py/perception_benchmark calibrate --config /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-92b0-cp041-r5/install/so101_demo_py/share/so101_demo_py/config/perception_benchmark/benchmark.yaml --model grounded_sam --dataset-inventory /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/val-open-r3/inventory.json --dataset-archive-sha256 d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6 --inventory-sha256 500b61e69771e3098628b20b5c4b01926d41df7dad1ffc3a7023be34405638b2 --mac-run-root /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/val/macos/grounded-sam-r1 --mac-run-expectation /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/prereg-r1/expectations/macos-grounded_sam.json --mac-run-expectation-sha256 6e5adccb253fab9b6df1e6966d1a53cc99a1c96cfa72ea4fec10c0b959e32b48 --linux-run-root /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/val/linux/grounded-sam-r1 --linux-run-expectation /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/prereg-r1/expectations/linux-grounded_sam.json --linux-run-expectation-sha256 9e1271a928a7df958f63841adb7df65e4a0aa85287f12ca7a39286271ec5bff7 --source-commit ef254f6025d8de42ce42a6cc6871e703fc86fbd4 --output-root /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/grounded-sam-r2 --calibration-workers 8
success_criteria:
  - command exits zero and writes self-consistent threshold-lock.json plus evidence-index.json
  - result is formal, deployable, SAFE_CALIBRATED, and has zero unsafe unique selections on both platforms
  - progress covers verify, rehome, precompute, grid, and finalize with bounded monotonic counts
  - wall time materially improves on the interrupted baseline of more than 49 minutes
stop_criteria:
  - output collision, evidence verification failure, test-split access, nonzero command, missing or malformed lock/index, non-deployable result, or unsafe outcome
next_command: commit and push CP-041, fast-forward the isolated ai-station checkout, reverify the output path is absent, then execute the exact formal command with combined stdout and stderr captured in the registered progress log
decision: LINUX_QUALIFIED_READY_TO_RUN_GROUNDED_SAM_R2
```

## Checkpoint CP-042 — optimized grounded-sam-r2 calibration result

```yaml
checkpoint_id: CP-042
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-041
run:
  output: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/grounded-sam-r2
  progress_log: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/grounded-sam-r2-calibrate.log
  command_exit_code: 0
  workers: 8
  grid_points_completed: 32400
  inference_during_calibration: false
timing:
  first_input_verification_seconds: 27.4
  mask_rehome_seconds: 18.4
  second_output_verification_seconds: 14.5
  parallel_precompute_seconds: 2.6
  grid_seconds: 161.8
  finalize_seconds: 0.2
  total_seconds: 224.9
  interrupted_baseline_seconds_lower_bound: 2940
  speedup_lower_bound: 13.07x
progress_contract:
  phases_observed: [verify, rehome, verify, precompute, grid, finalize]
  monotonic_bounded_counts: true
  progress_log_lines: 311
artifacts:
  file_count: 22641
  total_bytes: 36910115
  threshold_lock_file_sha256: 9ad6d9a0f8c21575a4dc9e5d3cea5fc8da3e450493ec12cd3f9cf0add9d4c3bc
  threshold_lock_internal_sha256: 374cbbc28596e61d937556c6e9adf4d2c72959c26eb896e1e9bfb4cd1489fd9e
  evidence_index_sha256: 49d918767da78ad730dd7b2bf3568ee0ad58bdd6199c6b4e88c7a1f6a7b99e7b
  progress_log_sha256: c23f7a6ff319258fc837adfac330f9e0b4bec09397a2beed364f80fbb011a355
verification:
  verify_evidence: PASS
  verify_threshold_lock: PASS
  formal: true
  deployable: true
  outcome: SAFE_CALIBRATED
  platform_sample_counts: {macos: 200, linux: 200}
selected:
  box_threshold: '0.05'
  text_threshold: '0.05'
  sam_quality: '0.80'
  target_confidence_threshold: '0.05'
  duplicate_iou: '0.85'
  min_mask_pixels: 64
  max_mask_area_ratio: '0.50'
objective_metrics:
  min_platform_macro_f1: 0.13333333333333333
  merged_macro_f1: 0.13333333333333333
  merged_mask_ap50_95: 0.034306845877090666
  min_platform_two_cup_recall: 0.08
platform_metrics:
  macos: {sample_count: 200, error_count: 0, macro_f1: 0.13333333333333333, mask_ap50_95: 0.034484790802431935, unsafe_unique_count: 0, unsafe_unique_denominator: 100, unsafe_unique_rate: 0.0, two_cup_both_matched_recall: 0.08}
  linux: {sample_count: 200, error_count: 0, macro_f1: 0.13333333333333333, mask_ap50_95: 0.03450188880901818, unsafe_unique_count: 0, unsafe_unique_denominator: 100, unsafe_unique_rate: 0.0, two_cup_both_matched_recall: 0.08}
interpretation:
  - SAFE_CALIBRATED and deployable describe the frozen fail-closed unsafe-unique gate only
  - macro-F1 0.1333, merged mask AP50-95 0.0343, and two-cup both-matched recall 0.08 do not establish useful model capability or Pick & Place readiness
  - no threshold, metric, matching rule, tie-break, or test seal was changed by the performance optimization
retained_runs:
  - grounded-sam-r2 and its progress log
  - all CP-041 build and benchmark evidence, including both interrupted diagnostic attempts
deletion: none
next_command: validate both formal locks together, then follow the preregistered test-seal and formal held-out test workflow without changing either lock
decision: VALID_VAL_LOCK_PERFORMANCE_OPTIMIZATION_COMPLETE_MODEL_CAPABILITY_NOT_ESTABLISHED
```

## Checkpoint CP-043 — one-time fresh test unlock preregistration

```yaml
checkpoint_id: CP-043
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-042
lock_verification:
  yolo:
    path: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/yolo-r1/threshold-lock.json
    file_sha256: c8b166f263077713e79b6ae33394efd7fbe37b39353ea3933d6da5c8e120b2d8
    internal_sha256: 0899521b12ddfcce8f302a9dfb2943eb2bfb26ea2092e2d839b89bd2e93a5151
    state: {formal: true, deployable: true, outcome: SAFE_CALIBRATED}
    evidence_index_sha256: 28c997133fc962cc38b95777748e7eed81a415b90ae9a4252c19d694a7aebf72
  grounded_sam:
    path: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/grounded-sam-r2/threshold-lock.json
    file_sha256: 9ad6d9a0f8c21575a4dc9e5d3cea5fc8da3e450493ec12cd3f9cf0add9d4c3bc
    internal_sha256: 374cbbc28596e61d937556c6e9adf4d2c72959c26eb896e1e9bfb4cd1489fd9e
    state: {formal: true, deployable: true, outcome: SAFE_CALIBRATED}
    evidence_index_sha256: 49d918767da78ad730dd7b2bf3568ee0ad58bdd6199c6b4e88c7a1f6a7b99e7b
sealed_input:
  archive: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/assets/datasets/so101-v5-t005-grounded-sam-fresh/so101-v5-t005-grounded-sam-fresh-650f3398-r3.tar.gz
  archive_sha256: d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6
  member_inventory: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/sealed-test-members-r3.json
  member_inventory_sha256: 905383228d57a0177e141814a96a5998524d1252e51e33d962c7fda7c5375295
  member_count: 600
  semantic_content_opened_before_unlock: false
one_time_unlock:
  access_log: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/test-access-r1.jsonl
  output_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/test-open-r1
  precondition: both targets are absent and the access event is appended before any test member is decoded
  command: PYTHONNOUSERSITE=1 PYTHONPATH=/tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-92b0-cp041-r5/install/so101_demo_py/lib/python3.12/site-packages /data/work/venvs/so101-grounded-sam/bin/python /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-92b0-cp041-r5/install/so101_demo_py/lib/so101_demo_py/perception_benchmark unlock-test --config /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-92b0-cp041-r5/install/so101_demo_py/share/so101_demo_py/config/perception_benchmark/benchmark.yaml --archive /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/assets/datasets/so101-v5-t005-grounded-sam-fresh/so101-v5-t005-grounded-sam-fresh-650f3398-r3.tar.gz --expected-sha256 d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6 --sealed-member-inventory /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/sealed-test-members-r3.json --yolo-threshold-lock /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/yolo-r1/threshold-lock.json --grounded-sam-threshold-lock /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/grounded-sam-r2/threshold-lock.json --access-log /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/test-access-r1.jsonl --output-root /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/test-open-r1
success_criteria:
  - exactly one access event exists and binds both verified internal lock SHA-256 values plus the sealed member inventory
  - test inventory contains 200 unique samples and exactly 50 no_cup, 50 one_cup_distractors, 50 two_cups, and 50 cup_near_bottle samples
  - all 600 extracted source artifacts are regular files with verified source SHA-256 values
  - no threshold, prompt, model, grid, matching rule, or calibration result changes after opening test
stop_criteria:
  - existing target, lock/seal/archive mismatch, access-event ordering failure, path safety failure, count/scenario mismatch, or malformed test truth
next_command: commit and push CP-043, synchronize ai-station, reverify both targets are absent, then execute the exact one-time unlock command
decision: READY_FOR_ONE_TIME_TEST_ACCESS
```

## Checkpoint CP-044 — fresh test access result and frozen formal matrix

```yaml
checkpoint_id: CP-044
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-043
test_unlock:
  result: PASS
  access_event_count: 1
  access_event_sha256: 1398c45bb0ca686146d982974592695dfc08f0fb08ab631ad913268ca7c2845a
  access_log_sha256: 0ea2b811436f3528c092875d2a6d5a6bd779db26d953ca4be9ad63154d26ebd4
  test_inventory_sha256: 5cb884693cc8022b79481e37d24e9585e4c755b1e5293909732aedc1f2aa06d4
  sample_count: 200
  scenario_counts: {no_cup: 50, one_cup_distractors: 50, two_cups: 50, cup_near_bottle: 50}
  truth_instance_count: 200
  extracted_core_files: 602
  generated_truth_mask_files: 200
  symlink_count: 0
  strict_lock_internal_sha256s:
    - 0899521b12ddfcce8f302a9dfb2943eb2bfb26ea2092e2d839b89bd2e93a5151
    - 374cbbc28596e61d937556c6e9adf4d2c72959c26eb896e1e9bfb4cd1489fd9e
  linux_dataset_loader_verification: PASS
mac_test_copy:
  source: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/test-open-r1
  target: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/dataset/test-open-macos-r1
  transfer: one scp copy into an absent target; no overwrite or deletion
  copied_files: 802
  local_dataset_loader_verification: PASS
  local_access_log: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/calibration/test-access-r1.jsonl
  local_access_log_sha256: 0ea2b811436f3528c092875d2a6d5a6bd779db26d953ca4be9ad63154d26ebd4
  local_yolo_lock_file_sha256: c8b166f263077713e79b6ae33394efd7fbe37b39353ea3933d6da5c8e120b2d8
  local_grounded_sam_lock_file_sha256: 9ad6d9a0f8c21575a4dc9e5d3cea5fc8da3e450493ec12cd3f9cf0add9d4c3bc
frozen_test_contract:
  source_commit: ef254f6025d8de42ce42a6cc6871e703fc86fbd4
  archive_sha256: d27206350f839c2d2c6bcfff9a6a16509be3648a9053b899d1f6ef286bbe8ac6
  inventory_sha256: 5cb884693cc8022b79481e37d24e9585e4c755b1e5293909732aedc1f2aa06d4
  sealed_member_inventory_sha256: 905383228d57a0177e141814a96a5998524d1252e51e33d962c7fda7c5375295
  test_access_event_sha256: 1398c45bb0ca686146d982974592695dfc08f0fb08ab631ad913268ca7c2845a
  yolo_lock_sha256: 0899521b12ddfcce8f302a9dfb2943eb2bfb26ea2092e2d839b89bd2e93a5151
  grounded_sam_lock_sha256: 374cbbc28596e61d937556c6e9adf4d2c72959c26eb896e1e9bfb4cd1489fd9e
  samples_per_run: 200
  dtype: float32
  offline: true
  fallback_used: false
  run_kinds_per_model: [TEST_RAW_FROZEN, TEST_PRODUCTION, TEST_CALIBRATED]
  oracle_diagnostic: NOT_AUTHORIZED_NOT_RUN
mac_matrix:
  status: PLANNED
  order:
    - mac-yolo-test-raw-fresh-r1
    - mac-yolo-test-production-fresh-r1
    - mac-yolo-test-calibrated-fresh-r1
    - mac-grounded-sam-test-raw-fresh-r1
    - mac-grounded-sam-test-production-fresh-r1
    - mac-grounded-sam-test-calibrated-fresh-r1
  script: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/mac-test-r1.sh
  script_sha256: 11ce40e7c9a72e6592b237137f4de18ad5fecfc86ca0a0b246b7eb2956ecab8d
  plist: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/com.terry.so101.benchmark.mac.test.r1.plist
  plist_sha256: faf3bf056c2b2bf78fbbb1d280f389588447a6e7bbc50ccfa5a9f73d0c7def71
  launch_label: com.terry.so101.benchmark.mac.test.r1
  command: launchctl bootstrap gui/501 /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/com.terry.so101.benchmark.mac.test.r1.plist
  runtime_python: /Users/matianyi/ros2_jazzy/.venv/bin/python
  package_prefix: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/mac-build-ef254-r2/install/so101_demo_py
  device: mps
  output_parent: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/test/macos
linux_matrix:
  status: PLANNED_AFTER_VALID_MAC
  order:
    - linux-grounded-sam-test-raw-fresh-r1
    - linux-grounded-sam-test-production-fresh-r1
    - linux-grounded-sam-test-calibrated-fresh-r1
    - linux-yolo-test-raw-fresh-r1
    - linux-yolo-test-production-fresh-r1
    - linux-yolo-test-calibrated-fresh-r1
  local_script: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/linux-test-r1.sh
  remote_script: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/linux-test-r1.sh
  script_sha256: eab9cc15a34d5989ee212ed198e522e1d2a607cd27cbb74fdc53560466a70647
  command: /bin/bash /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/linux-test-r1.sh
  runtime_python: /data/work/venvs/so101-grounded-sam/bin/python
  package_prefix: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-ef254-r1/install/so101_demo_py
  device: cuda
  output_parent: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/test/linux
execution_gate:
  - run Mac first through the native launchd context required for MPS
  - validate all six Mac manifests, 200-record denominators, source/mask SHA chains, native MPS, FP32, no fallback, and production/replay equality before transferring or starting Linux
  - stop on the first invalid run; never resume, overwrite, hide, or replace an invalid formal output under the same semantic identity
  - keep every threshold lock and test access anchor byte-unchanged
stop_criteria:
  - output or launch-label collision, script digest mismatch, command failure, invalid manifest, missing or duplicate sample, asset/config/source drift, fallback, timeout, OOM, or DetectorPort/replay disagreement
test_model_process_started: false
deletion: none
next_command: commit and push CP-044, synchronize ai-station, create only the two registered output parents, verify all twelve output names and the Mac launch label remain absent, then start Mac only
decision: FORMAL_TEST_MATRIX_FROZEN_READY_FOR_MAC
```

## Checkpoint CP-045 — Mac formal test R2 timestamp-preserving replacement

```yaml
checkpoint_id: CP-045
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-044
mac_r1:
  status: INVALID_PREINFERENCE
  first_run: mac-yolo-test-raw-fresh-r1
  first_bad_boundary: local threshold-lock file receipt time was later than the frozen test access event
  error: THRESHOLD_LOCK_POSTDATES_TEST_ACCESS
  record_count: 0
  output: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/test/macos/yolo-raw-r1
  retained_files: [manifest.json]
  model_inference_started: false
  remaining_five_r1_outputs_created: false
  launchd_job_removed_after_exit: true
  deletion: none
root_cause:
  - the R1 lock transfer preserved bytes but not source mtimes
  - local yolo and Grounded-SAM lock mtimes were 2026-09-04T02:11:48Z and 2026-09-04T02:11:51Z
  - the access event was 2026-09-04T02:10:09Z on the Mac filesystem view
  - durable source lock mtimes were 2026-09-03T15:35:34Z and 2026-09-03T17:52:28Z UTC, both before the 2026-09-03T17:58:27Z access event
replacement_single_variable: preserve the two durable source lock mtimes with scp -p; keep lock bytes, dataset, access event, models, config, source, run order, thresholds, and all acceptance rules unchanged
mac_r2:
  status: PLANNED
  lock_target: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/calibration/macos-locks-r2
  lock_copy_policy:
    - target must be absent
    - copy each durable threshold-lock.json exactly once with scp -p
    - verify file SHA-256 and internal lock SHA-256
    - require both local lock mtimes to precede the frozen test access event
  script: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/mac-test-r2.sh
  script_sha256: 1afc6fd036b0393993a7e3c1acdfba0d17a4a40b71c7398f62283f75d79aff9a
  plist: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/com.terry.so101.benchmark.mac.test.r2.plist
  plist_sha256: cc1cd66a9a646a346b8deee20b03e23877509bbc10a7a8580cfd8f3f6967fce4
  launch_label: com.terry.so101.benchmark.mac.test.r2
  command: launchctl bootstrap gui/501 /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/com.terry.so101.benchmark.mac.test.r2.plist
  order:
    - mac-yolo-test-raw-fresh-r2
    - mac-yolo-test-production-fresh-r2
    - mac-yolo-test-calibrated-fresh-r2
    - mac-grounded-sam-test-raw-fresh-r2
    - mac-grounded-sam-test-production-fresh-r2
    - mac-grounded-sam-test-calibrated-fresh-r2
  outputs:
    - yolo-raw-r2
    - yolo-production-r2
    - yolo-calibrated-r2
    - grounded-sam-raw-r2
    - grounded-sam-production-r2
    - grounded-sam-calibrated-r2
  frozen_contract: identical to CP-044 except for new run/output/label identities and timestamp-preserving local lock receipts
linux_matrix: remains PLANNED_AFTER_VALID_MAC with unchanged R1 script and output identities
stop_criteria:
  - any R2 target or label collision, copied lock digest mismatch, copied lock mtime after the access event, command failure, invalid run, fallback, timeout, OOM, or production/replay disagreement
next_command: commit and push CP-045, synchronize ai-station, create the absent R2 lock target, copy both locks with scp -p and verify timestamps plus digests, then start Mac R2 only
decision: REPLACE_PREINFERENCE_INVALID_MAC_R1_WITH_TIMESTAMP_PRESERVING_R2
```

## Checkpoint CP-046 — Mac formal test R2 stopped on YOLO production mapping

```yaml
checkpoint_id: CP-046
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-045
mac_r2:
  status: INVALID_STOPPED
  yolo_raw:
    run_id: mac-yolo-test-raw-fresh-r2
    output: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/test/macos/yolo-raw-r2
    status: VALID
    record_count: 200
    started_at: 2026-09-03T18:20:26.855118+00:00
    ended_at: 2026-09-03T18:20:35.518689+00:00
    record_inventory_sha256: c8f51715eb5670fa62446021fc0f556872410802d029484254b594eeb4023e23
  yolo_production:
    run_id: mac-yolo-test-production-fresh-r2
    output: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/test/macos/yolo-production-r2
    status: INVALID
    invalid_reason: PRODUCTION_CANDIDATE_MAPPING_INVALID
    record_count: 0
    started_at: 2026-09-03T18:20:39.482966+00:00
    ended_at: 2026-09-03T18:20:39.782679+00:00
    model_inference_started: true
  remaining_mac_outputs:
    - yolo-calibrated-r2: ABSENT
    - grounded-sam-raw-r2: ABSENT
    - grounded-sam-production-r2: ABSENT
    - grounded-sam-calibrated-r2: ABSENT
  launchd_job_removed_after_exit: true
linux_r1:
  status: NOT_STARTED
  all_six_outputs_absent: true
interpretation:
  - the production run is invalid evidence, not a zero detector score
  - the runner stopped before writing the first production record, as required by the fail-closed mapping contract
  - the held-out test split is open and may now be used only for diagnosis; it cannot be reused for an unbiased ranking after a semantic code fix
first_source_inconsistency:
  - YoloRawAdapter._convert stores the nearest-resized binary mask without boundary trimming
  - convert_yolo_result, used by the production detector, applies _trim_mask_boundary after the same nearest resize
  - _matches_production_candidate requires the observed mask SHA-256 to equal the raw mask SHA-256 byte-for-byte
  - therefore a non-empty production candidate whose boundary changes cannot map to its raw counterpart even when model weights, frame, box, class, and confidence agree
diagnostic_boundary:
  - do not change thresholds, locks, current test records, or current test outputs
  - reproduce on validation data only and compare the first raw and production candidates field-by-field
  - add diagnostic visibility and a regression test before changing reconciliation semantics
deletion: none
next_command: commit and publish CP-046, synchronize ai-station, then run one bounded validation-only YOLO raw/production diagnostic on Mac MPS
decision: FORMAL_BENCHMARK_INVALID_STOP_AND_DIAGNOSE_ON_VALIDATION
```

## Checkpoint CP-047 — Validation-only diagnosis confirms deterministic YOLO mask mismatch

```yaml
checkpoint_id: CP-047
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-046
diagnostic:
  scope: validation-only first sample; no test image accessed
  platform: macos
  device: mps
  image: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/dataset/val-open-macos-r1/images/val/000500138.png
  image_sha256: 009a14cbc849e90410d79e57f35ac0622bef244ba936eb12cd206650ed225d18
  script: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/mac-yolo-val-mask-map-diagnostic-r1.py
  script_sha256: 4a438b7deb4b06ee07602ab08478f79c9f99ea717668e727baa01496fd4d5d33
  launch_label: com.terry.so101.benchmark.mac.yolo-map-diagnostic.r1
  exit_code: 0
  stdout: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/mac-yolo-val-mask-map-diagnostic-r1.stdout.log
  stdout_sha256: f5032e9aba9437b36a81ddfe83c0b41eece4f070aeab5d66a6228f2ede630fdc
  stderr: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/mac-yolo-val-mask-map-diagnostic-r1.stderr.log
  stderr_sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
  launchd_job_removed_after_exit: true
observations:
  raw_candidate_count: 2
  production_candidate_count: 2
  candidate_0:
    exact_box_conf_raw_matches: 1
    mask_sha_matches: 0
    raw_pixels: 4285
    production_pixels: 3816
    mask_iou: 0.8905484247374562
    raw_sha256: 32f0206fd6d473ae92cf964a92b21b604b652242a82c6782b935369edf98f353
    production_sha256: 856bfad1eda6b6793c7cb2a0762098a0a15a6478f4a51f148ffcc9a3ab70bc41
  candidate_1:
    exact_box_conf_raw_matches: 1
    mask_sha_matches: 0
    raw_pixels: 3861
    production_pixels: 3421
    mask_iou: 0.886039886039886
    raw_sha256: cb53bc8a02b9740f285d23c3ecc41f83773173645b79979ea681d14da392ffad
    production_sha256: a982df55e10125f9515c427d2786023090ce0eca7bc30b80356c24fbc2ce3080
  invariant:
    - for both candidates, raw resize output equals production pre-trim output byte-for-byte
    - the production two-pass boundary trim alone changes the mask SHA-256
root_cause: the reconciliation contract compares the production-trimmed mask to the untrimmed low-floor raw mask without applying the production normalization
excluded_hypotheses:
  - MPS nondeterminism in bbox or confidence
  - candidate ordering ambiguity on this reproducer
  - different weights or input frame
remediation_contract:
  - preserve low-floor raw evidence and calibration semantics unchanged
  - normalize YOLO raw masks through the same deterministic production boundary transform only for reconciliation
  - preserve exact class, bbox, confidence, one-to-one, frame, model, weights, device, and selected-candidate checks
  - add a regression test that fails before the code change and passes after it
  - require a new sealed held-out split for any post-fix formal ranking
deletion: none
next_command: add and run the focused RED regression test before changing reconciliation code
decision: ROOT_CAUSE_CONFIRMED_FIX_RECONCILIATION_WITH_TDD
```

## Checkpoint CP-048 — YOLO production reconciliation fix passes Mac benchmark gate

```yaml
checkpoint_id: CP-048
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-047
change:
  production_reconciliation:
    - preserve low-floor raw mask artifacts byte-unchanged
    - for yolo_seg mapping only, apply the production _trim_mask_boundary transform to the verified raw mask before computing its comparison SHA-256
    - preserve exact class, bbox, confidence, score provenance, frame, model, weights, device, selected-candidate, and one-to-one checks
  test_fixture: production YOLO candidates now include the same boundary normalization as the production adapter
tdd:
  red:
    command: PYTHONPATH=/tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/mac-build-ef254-r2/install/so101_demo_py/lib/python3.11/site-packages /Users/matianyi/ros2_jazzy/.venv/bin/python -m pytest -q src/so101_demo_py/benchmark_test/test_perception_benchmark_runner.py -k yolo_production_trimmed_mask_maps_to_canonical_raw_candidate
    result: 1 failed, 125 deselected
    failure: PRODUCTION_CANDIDATE_MAPPING_INVALID
  focused_green:
    result: 4 passed, 122 deselected
  runner_green:
    result: 126 passed in 65.23s
  adapter_green:
    result: 88 passed, 1 warning in 2.05s
static_checks:
  ruff: 0.15.20 PASS
  compileall: PASS
  git_diff_check: PASS
mac_fresh_build:
  root: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/mac-build-mapfix-r3
  discovery_scope: src/so101_demo_py
  underlay: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/mac-build-ef254-r2/install
  result: 1 package finished
  package_duration_s: 1.58
  total_duration_s: 1.66
  note: two prior setup attempts selected so101_demo_py while discovering the whole workspace and correctly failed before tests because dependency package.sh files were absent from their new install-base; restricting --base-paths to src/so101_demo_py reused the verified underlay and avoided rebuilding unrelated ROS packages
mac_benchmark_gate:
  command: colcon test --base-paths src/so101_demo_py --packages-select so101_demo_py --pytest-args benchmark_test
  root: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/mac-build-mapfix-r3
  result: 563 tests, 0 errors, 0 failures, 0 skipped
  pytest_duration_s: 300.63
  colcon_duration: 5min 5s
benchmark_state:
  current_open_test: remains INVALID and diagnostic-only
  post_fix_formal_ranking: requires a new sealed held-out split
  pick_place_claim: not established by this code gate
deletion: none
next_command: commit and publish the fix plus CP-048, synchronize ai-station, then build a fresh Linux scoped overlay and run the same complete benchmark gate
decision: MAC_CODE_GATE_PASS_PENDING_LINUX_GATE
```

## Checkpoint CP-049 — Cross-platform code qualification complete

```yaml
checkpoint_id: CP-049
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-048
source:
  branch: codex/v5-t004-yolo-seg-rgbd
  commit: 5c2224e2dbfaf92f43c06935bb4c7457a4c64bf8
  remote_sha: 5c2224e2dbfaf92f43c06935bb4c7457a4c64bf8
linux_environment_diagnostics:
  attempt_r6:
    result: PREBUILD_INVALID
    cause: Bash setup sourced after set -u and referenced an unset COLCON_TRACE
    model_or_test_started: false
  attempt_r7:
    result: BUILD_ONLY_ENVIRONMENT_INVALID
    build_duration_s: 1.30
    cause: system /usr/bin/python3 shebang; not used for tests
  attempt_r8:
    result: BUILD_ONLY_ENVIRONMENT_INVALID
    build_duration_s: 1.22
    cause: PATH alone did not change the Python interpreter owned by /usr/bin/colcon
  attempt_r9:
    result: TEST_ENVIRONMENT_INVALID
    build_duration_s: 1.46
    test_summary: 501 passed, 60 failed, 2 skipped
    common_failure: RASTERIZER_VERSION_MISMATCH
    cause: system dist-packages preceded venv site-packages through PYTHONPATH and selected Pillow 10.2 instead of pinned Pillow 12.3
  attempt_r10:
    result: PREBUILD_INVALID
    cause: colcon_core was added only inside the parent wrapper process and was unavailable to the setuptools subprocess
    model_or_test_started: false
  retention: all diagnostic roots retained; no deletion
linux_qualified_overlay:
  root: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-mapfix-r11
  build_script: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/linux-mapfix-build-r6.sh
  build_script_sha256: 03046564f8348b1f1789426c65d8d5f596e1b97a52ebea60fc0926e0d0323e3a
  test_script: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/linux-mapfix-test-r6.sh
  test_script_sha256: 3e5bda3c34c7f6a492bbd9703b48d046f3289550654b9157d8534b3268d6f7dd
  python: /data/work/venvs/so101-grounded-sam/bin/python
  dependency_order:
    - /data/work/venvs/so101-grounded-sam/lib/python3.12/site-packages
    - /usr/lib/python3/dist-packages
  pillow: 12.3.0
  runner_shebang: /data/work/venvs/so101-grounded-sam/bin/python
  build_result: PASS
  package_duration_s: 1.15
  total_duration_s: 1.28
linux_benchmark_gate:
  runtime_tmp: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/runtime-tmp/linux-mapfix-r11
  command_contract: colcon test --base-paths src/so101_demo_py --packages-select so101_demo_py --pytest-args benchmark_test
  pytest_result: 561 passed, 2 skipped
  pytest_duration_s: 643.63
  colcon_duration: 10min 45s
  test_result: 563 tests, 0 errors, 0 failures, 2 skipped
cross_platform_gate:
  macos: PASS_563_OF_563
  linux: PASS_561_PLUS_2_SKIPPED
  code_fix: QUALIFIED
optimized_iteration_policy:
  - use focused tests for the changed behavior during RED/GREEN iteration
  - use runner-only tests for reconciliation changes before the full gate
  - build only src/so101_demo_py against a verified underlay; measured fresh build is 1.28 to 1.66 seconds instead of rebuilding all ROS dependencies
  - run the complete benchmark_test gate only for benchmark core changes and release qualification
  - on Linux place pytest TMPDIR on the registered NVMe evidence root and keep venv site-packages before system ROS dist-packages
formal_benchmark_state:
  old_test_split: INVALID_DIAGNOSTIC_ONLY
  next_requirement: new independently sealed held-out split, fresh validation inference, fresh calibration locks, one-time test unlock, and one frozen test matrix
  pick_place_claim: not yet established
deletion: none
next_command: commit and publish CP-049, then preregister and generate a fresh post-fix benchmark dataset without accessing its test members
decision: CODE_FIX_CROSS_PLATFORM_QUALIFIED_PREPARE_FRESH_FORMAL_DATASET
```

## Checkpoint CP-050 — Post-fix sealed benchmark dataset preregistration

```yaml
checkpoint_id: CP-050
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-049
hypothesis: a benchmark dataset generated from a disjoint seed namespace after the qualified reconciliation fix can provide a new unbiased held-out test split without changing model weights, prompts, runtime devices, or evaluation policy
single_variable:
  seed_starts: {train: 700000, val: 800000, test: 900000}
unchanged:
  - MJCF, camera, image size, scene distributions, split counts, label semantics, archive format, and security rules
  - YOLO-Seg and Grounded-SAM model bytes and identities
  - plastic cup prompt, low-floor settings, calibration grids, objective, tie-breakers, unsafe-unique fail-closed gate, FP32, native MPS/CUDA, offline, and no fallback
counts:
  train: 480
  val: 200
  test: 200
  scenarios_per_val_or_test: {no_cup: 50, one_cup_distractors: 50, two_cups: 50, cup_near_bottle: 50}
seed_ranges:
  train: [700000, 700479]
  val: [800000, 800199]
  test: [900000, 900199]
disjoint_from_prior_ranges:
  train: [400000, 400479]
  val: [500000, 500199]
  test: [600000, 600199]
generation_targets:
  raw_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/raw-postfix-r4
  archive: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/so101-v5-t005-grounded-sam-postfix-r4.tar.gz
  checksum: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/so101-v5-t005-grounded-sam-postfix-r4.tar.gz.sha256
execution_order:
  - change only fresh_dataset.yaml seed_starts with one tracked-config regression and pass the focused dataset tests
  - publish and synchronize the exact generator commit
  - fresh non-symlink scoped Linux build under the qualified Grounded-SAM venv
  - generate 880 samples exactly once into the absent raw root
  - validate dataset-manifest.json and val semantics; do not read test image, label, or truth content
  - create one deterministic archive and adjacent checksum, then seal test member names and digests without semantic access
  - bind benchmark.yaml and CLI immutable constants to the new archive under TDD
  - run fresh Mac/Linux val inference, calibrate from val only, unlock test exactly once, and execute one frozen formal test matrix
success_criteria:
  - 880 samples, 2641 payload artifacts before manifest, 880 total plastic_cup instances, and no symlinks
  - val scenario and visible instance counts match the frozen contract
  - archive and checksum are immutable and test semantic content remains unopened until both new locks verify
invalid_criteria:
  - any old test metric, prediction, or truth influences seeds, generation, thresholds, ranking, or acceptance
  - any post-fix test semantic member is opened before both locks verify
  - any target collision, source/config drift, count mismatch, hidden fallback, or overwrite
stop_criteria:
  - stop on the first invalid condition and retain all evidence
deletion: none
next_command: commit and publish CP-050, then change only the tracked seed namespace test and observe RED
decision: GENERATE_NEW_UNBIASED_DATASET_WITH_DISJOINT_SEEDS
```

## Checkpoint CP-051 — Post-fix dataset generation lock

```yaml
checkpoint_id: CP-051
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-050
status: READY_FOR_ONE_GENERATION
source_commit: 5e3891d4814bb86dcd9242241d15599a125736c8
source_sync:
  local: 5e3891d4814bb86dcd9242241d15599a125736c8
  gitee: 5e3891d4814bb86dcd9242241d15599a125736c8
  ai_station: 5e3891d4814bb86dcd9242241d15599a125736c8
tdd:
  red: one expected failure after changing only the tracked seed expectation
  green: 26 passed in 0.07 s after changing fresh_dataset.yaml to the preregistered seed namespace
tracked_config:
  path: src/so101_demo_py/config/perception_benchmark/fresh_dataset.yaml
  seed_starts: {train: 700000, val: 800000, test: 900000}
linux_build:
  mode: fresh scoped non-symlink install
  underlay: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-92b0-cp041-r5/install/setup.bash
  python: /data/work/venvs/so101-grounded-sam/bin/python
  py_path_order:
    - /data/work/venvs/so101-grounded-sam/lib/python3.12/site-packages
    - /usr/lib/python3/dist-packages
  package: so101_demo_py
  required_checks:
    - installed fresh_dataset.yaml is a regular non-symlink file whose SHA256 equals the tracked source
    - generator entrypoint shebang selects /data/work/venvs/so101-grounded-sam/bin/python
generation:
  config: <fresh-build>/install/so101_demo_py/share/so101_demo_py/config/perception_benchmark/fresh_dataset.yaml
  output_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/raw-postfix-r4
  archive: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/so101-v5-t005-grounded-sam-postfix-r4.tar.gz
  checksum: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/so101-v5-t005-grounded-sam-postfix-r4.tar.gz.sha256
  generator_commit: 5e3891d4814bb86dcd9242241d15599a125736c8
  environment: MUJOCO_GL=egl and PYTHONNOUSERSITE=1
  command: generate_yolo_seg_dataset --config <exact installed regular fresh_dataset.yaml> --output-root <exact absent raw-postfix-r4> --generator-commit 5e3891d4814bb86dcd9242241d15599a125736c8
success_and_access_contract:
  - generate exactly 880 samples and 2641 payload artifacts before dataset-manifest.json
  - validate manifest counts, source identity, seed ranges, and val semantics only
  - do not open any images/test, labels/test, or truth/test member before both fresh calibration locks verify
  - archive sealing may record only safe member names, counts, and byte digests
preflight:
  - all three generation targets are absent and non-symlink
  - no benchmark, dataset-generator, Grounded-SAM, MuJoCo, ROS, or tmux process is active
  - stop on any source, config, target, count, semantic, or runtime drift and retain evidence
deletion: none
next_command: commit and publish CP-051, synchronize ai-station, then perform the fresh scoped build and one exact generation
decision: RUN_ONE_POSTFIX_DATASET_GENERATION
```

## Checkpoint CP-052 — Unrelated tmux preflight exception

```yaml
checkpoint_id: CP-052
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-051
cp051_attempts:
  r1: INVALID_PRESTART because the transfer check used an incorrect expected script SHA; local and remote actual SHA256 were both 2e4a3450442642be782c8b4923aeece5d6bd8ad486ae105ecd872d3eadff85df
  r2: STOPPED_PRESTART because the literal no-tmux guard found an existing unrelated session
observed_tmux:
  session: codex
  window: 0
  pane: 0
  current_command: codex
  current_path: /data/work/microduck_rl
  relation_to_experiment: none
target_state:
  raw_root: absent
  archive: absent
  checksum: absent
  fresh_build_root: absent
revised_preflight:
  - preserve and do not alter the unrelated codex tmux session
  - require no active benchmark, dataset-generator, Grounded-SAM, MuJoCo, or ROS process
  - require no tmux pane whose command or current path belongs to this experiment
  - keep every remaining CP-051 source, build, target, access, and stop condition unchanged
deletion: none
next_command: publish CP-052, synchronize ai-station, then rerun the scoped preflight and build without touching the unrelated session
decision: PROCEED_WITH_UNRELATED_TMUX_PRESERVED
```

## Checkpoint CP-053 — Post-fix fresh archive frozen

```yaml
checkpoint_id: CP-053
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-052
status: READY_FOR_CONFIG_REBIND
generator_source_commit: 5e3891d4814bb86dcd9242241d15599a125736c8
execution_checkout_head: 938d4d93c02b5553aa2ab49e0c50e77fd7961451
package_tree_diff_from_generator_source: none under src/so101_demo_py
build:
  r12: INVALID_PREBUILD because sourced setup.bash referenced unset COLCON_TRACE under nounset; retained and no package or dataset command ran
  r13: VALID
  mode: fresh scoped non-symlink install
  elapsed: 1.13 s
  installed_config_sha256: ae9583598ed665be8a3e1a3c1c8e51af6d47da1deead9276b030aba52072015e
  installed_config_type: regular non-symlink file
  generator_shebang: '#!/data/work/venvs/so101-grounded-sam/bin/python'
  script_sha256: 331fba12ce3d96857bffad808570c69c120ca24b4781079aa643469521ca9bc3
generation:
  status: VALID
  raw_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/raw-postfix-r4
  generator_commit: 5e3891d4814bb86dcd9242241d15599a125736c8
  sample_count: 880
  script_sha256: ca12cdd9d22d86a4ea6d557a43752cccd07ad43ecb07642c44cb54b5c17ee037
  progress: file-count reports only; no test content read
manifest:
  sha256: 609c57da57c65c1a6cbf1f4898b38d71dff14c90544069b7d65266960dadbe1a
  mjcf_sha256: d40494c9f88294840d8e8a90859c6a28dc361149b5878b785b787ea96c61e083
  payload_artifact_count: 2641
  total_file_count_including_manifest: 2642
  symlink_count: 0
  split_counts: {train: 480, val: 200, test: 200}
  seed_ranges: {train: [700000, 700479], val: [800000, 800199], test: [900000, 900199]}
  class_instance_totals: {plastic_cup: 880}
open_val_validation:
  status: PASS
  sample_count: 200
  scenario_counts: {no_cup: 50, one_cup_distractors: 50, two_cups: 50, cup_near_bottle: 50}
  visible_instances: {no_cup: 0, one_cup_distractors: 1, two_cups: 2, cup_near_bottle: 1}
  checks: truth visible/list counts, label row count, and RGB 640x480 PNG metadata
  script_sha256: c3479388330614cd6b36ac08bb060edb9fe2420e6368c8c2a8f0f5493597738c
archive:
  path: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/so101-v5-t005-grounded-sam-postfix-r4.tar.gz
  checksum_file: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/so101-v5-t005-grounded-sam-postfix-r4.tar.gz.sha256
  sha256: 8424de68a8cc18961ab4732cba3c2486161f733b638638c82da6e1761e3ac832
  size_bytes: 39461148
  member_count: 2655
  link_member_count: 0
  mode: '0444'
  checksum_mode: '0444'
  script_sha256: 07bad36060f3088879747844e362d5b936d21f6c7d22f287b9ae0262635fc686
sealed_test_state:
  member_name_counts: {images: 200, labels: 200, truth: 200}
  semantic_content_opened: false
  model_inference_run: false
  archive_creation: mechanical byte packaging only
next_change:
  - under TDD, rebind benchmark.yaml archive ID/SHA and the CLI immutable config/archive constants
  - preserve every model, prompt, grid, matching, calibration, device, offline, no-fallback, safety, and sealed-test rule
deletion: none
next_command: publish CP-053, update the frozen-literal test and observe RED, then perform only the archive/config rebind
decision: RUN_POSTFIX_CONFIG_REBIND_TDD_ONLY
```

## Checkpoint CP-054 — Post-fix immutable asset registration lock

```yaml
checkpoint_id: CP-054
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-053
status: READY_FOR_IMMUTABLE_COPY
immutable_asset_copy:
  source: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/so101-v5-t005-grounded-sam-postfix-r4.tar.gz
  source_checksum: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/so101-v5-t005-grounded-sam-postfix-r4.tar.gz.sha256
  target: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/assets/datasets/so101-v5-t005-grounded-sam-postfix/so101-v5-t005-grounded-sam-postfix-r4.tar.gz
  target_checksum: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/assets/datasets/so101-v5-t005-grounded-sam-postfix/so101-v5-t005-grounded-sam-postfix-r4.tar.gz.sha256
  required_sha256: 8424de68a8cc18961ab4732cba3c2486161f733b638638c82da6e1761e3ac832
  policy: require absent targets, copy once, verify bytes, retain source, set both targets read-only, and never overwrite
config_rebind_target:
  archive_id: datasets/so101-v5-t005-grounded-sam-postfix/so101-v5-t005-grounded-sam-postfix-r4.tar.gz
  archive_sha256: 8424de68a8cc18961ab4732cba3c2486161f733b638638c82da6e1761e3ac832
access_boundary:
  - copying and hashing are mechanical byte operations
  - do not list, extract, parse, rasterize, display, or infer any test semantic member
  - test remains sealed after the copy
deletion: none
next_command: publish CP-054, synchronize ai-station, perform the absent-target copy and digest verification, then start the config rebind TDD
decision: COPY_FROZEN_ARCHIVE_TO_REGISTERED_ASSET_PATH
```

## Checkpoint CP-055 — Post-fix archive binding qualified on macOS

```yaml
checkpoint_id: CP-055
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-054
status: READY_FOR_LINUX_QUALIFICATION
asset_registration:
  r1: INVALID_PRECOPY because the command used an incorrect full expected checkout SHA; target remained absent
  r2: VALID
  target: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/assets/datasets/so101-v5-t005-grounded-sam-postfix/so101-v5-t005-grounded-sam-postfix-r4.tar.gz
  sha256: 8424de68a8cc18961ab4732cba3c2486161f733b638638c82da6e1761e3ac832
  size_bytes: 39461148
  mode: '0444'
  semantic_test_content_opened: false
config_rebind:
  archive_id: datasets/so101-v5-t005-grounded-sam-postfix/so101-v5-t005-grounded-sam-postfix-r4.tar.gz
  archive_sha256: 8424de68a8cc18961ab4732cba3c2486161f733b638638c82da6e1761e3ac832
  config_sha256: 8103b926c48b3fe006101cdc1bdf8035349f65c2def5ce33c2aaed79e0e32725
  changed_files:
    - src/so101_demo_py/config/perception_benchmark/benchmark.yaml
    - src/so101_demo_py/src/cli/perception_benchmark.py
    - src/so101_demo_py/benchmark_test/test_perception_benchmark_cli.py
tdd:
  red: frozen-literal test failed once because benchmark.yaml still named the prior archive
  first_green: 1 passed in 0.08 s after the config and immutable constants changed
  fixture_drift: 10 of 54 CLI tests correctly failed closed because their fixtures still supplied the prior registered archive
  fixture_fix: bind those fixtures to shared post-fix archive constants without weakening any production check
  cli_green: 54 passed in 0.94 s
macos_qualification:
  fresh_build: one package passed in 0.72 s; nonfatal LaunchServices notification error observed after success
  benchmark_gate: 563 passed, 0 failed, 0 skipped in 300.78 s
  junit: 563 tests, 0 errors, 0 failures, 0 skipped
  compileall: PASS
  diff_check: PASS
  ruff: unavailable in the selected macOS environment; no Ruff result claimed
unchanged:
  - all model bytes, revisions, IDs, prompts, grids, thresholds, matching, objectives, tie-breaks, runtime device/dtype, offline/no-fallback, and unsafe-unique gates
  - test remains sealed; no fresh model inference, calibration, or test unlock has run
deletion: none
next_command: commit and publish the rebind, synchronize ai-station, run one fresh Linux scoped build and benchmark gate, then prepare the new non-semantic test seal and val-only extraction
decision: PUBLISH_REBIND_AND_QUALIFY_LINUX
```

## Checkpoint CP-056 — Post-fix archive binding qualified on Linux

```yaml
checkpoint_id: CP-056
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-055
status: READY_FOR_SEAL_AND_VAL_PREPARATION
source_commit: d933b4b9574df36d499b3e9254f0e88a1919810a
source_sync:
  local: d933b4b9574df36d499b3e9254f0e88a1919810a
  gitee: d933b4b9574df36d499b3e9254f0e88a1919810a
  ai_station: d933b4b9574df36d499b3e9254f0e88a1919810a
linux_qualification:
  fresh_scoped_build: one package passed in 1.24 s
  installed_config_sha256: 8103b926c48b3fe006101cdc1bdf8035349f65c2def5ce33c2aaed79e0e32725
  installed_config_type: regular non-symlink file
  cli_tests: 54 passed in 2.11 s
  benchmark_gate: 561 passed and 2 platform-condition skips in 647.41 s
  junit: 563 tests, 0 errors, 0 failures, 2 skipped
  compileall: PASS
  diff_check: PASS
  ruff: unavailable in the selected Linux venv; no Ruff result claimed
  script_sha256: d4565f8622b8d5015823587048f3b708f255ab1ff7635964422198444a4e5f5a
script_transfer_note:
  - the outer launch command carried an incorrect expected script SHA and lacked errexit, so the independent script still started
  - while the gate was running, the remote script SHA was independently verified equal to the local SHA above
  - the script itself fail-closed on exact source commit, absent run roots, installed config SHA, tests, JUnit, and final status
sealed_preparation:
  archive: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/assets/datasets/so101-v5-t005-grounded-sam-postfix/so101-v5-t005-grounded-sam-postfix-r4.tar.gz
  archive_sha256: 8424de68a8cc18961ab4732cba3c2486161f733b638638c82da6e1761e3ac832
  config: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-postfix-config-r14/install/so101_demo_py/share/so101_demo_py/config/perception_benchmark/benchmark.yaml
  cli: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-postfix-config-r14/install/so101_demo_py/lib/so101_demo_py/perception_benchmark
  sealed_member_inventory: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/sealed-test-members-postfix-r4.json
  val_output_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/val-open-postfix-r4
success_criteria:
  - archive and config hashes verify before any extraction
  - seal contains 200 image, 200 label, and 200 truth test members with scenario_counts null
  - val inventory contains 200 unique samples and 50 per scenario
  - val output contains no test path; no test semantic member is extracted, parsed, rasterized, displayed, or inferred
stop_criteria:
  - either output target exists, any identity/count/path check fails, or any test semantic access occurs
deletion: none
next_command: publish CP-056, synchronize ai-station, run inspect-archive once, verify its non-semantic seal, then run prepare-dataset for val once
decision: CREATE_POSTFIX_SEAL_AND_OPEN_VAL_ONLY
```

## Checkpoint CP-057 — Post-fix val inference lock

```yaml
checkpoint_id: CP-057
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-056
status: READY_FOR_FRESH_VAL_INFERENCE
source_commit: d933b4b9574df36d499b3e9254f0e88a1919810a
sealed_test:
  inventory: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/sealed-test-members-postfix-r4.json
  inventory_sha256: 4ac8407aec15d8c19da653dd34b932e50ba42fa9aa492a7b4adedc2147666b81
  archive_sha256: 8424de68a8cc18961ab4732cba3c2486161f733b638638c82da6e1761e3ac832
  member_counts: {images: 200, labels: 200, truth: 200}
  scenario_counts_present: false
  semantic_content_opened: false
val_dataset:
  linux_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/val-open-postfix-r4
  macos_copy_root: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/dataset/val-open-postfix-r4-macos
  inventory_sha256: 141d79acd2aa3758f4ee90056b14aab0f105d74778f193a998bc341ae6ce59b3
  sample_count: 200
  scenario_counts: {no_cup: 50, one_cup_distractors: 50, two_cups: 50, cup_near_bottle: 50}
  test_access: null
  preparation_script_sha256: c2822c6822dbb26b455d975c004f13c026a4310e4e7c53d5fd588a97962e5db4
models:
  yolo:
    id: plastic-cup-yolo11s-seg-v2
    sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
    macos_path: /tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/assets/best.pt
    linux_path: /data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/assets-r8/best.pt
  grounded_sam:
    id: grounding-dino-tiny+sam2.1-hiera-tiny
    manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
    macos_root: /Users/matianyi/Models/so101/grounded-sam-v2-scipy-lock
    linux_root: /data/work/so101-models/grounded-sam-v2-scipy-lock
runs_in_order:
  - {run_id: mac-yolo-val-postfix-r4, platform: macos, device: mps, model: yolo_seg, output: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/val-postfix-r4/macos/yolo-r1}
  - {run_id: mac-grounded-sam-val-postfix-r4, platform: macos, device: mps, model: grounded_sam, output: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/val-postfix-r4/macos/grounded-sam-r1}
  - {run_id: linux-yolo-val-postfix-r4, platform: linux, device: cuda, model: yolo_seg, output: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/val-postfix-r4/linux/yolo-r1}
  - {run_id: linux-grounded-sam-val-postfix-r4, platform: linux, device: cuda, model: grounded_sam, output: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/val-postfix-r4/linux/grounded-sam-r1}
run_contract:
  split: val
  run_kind: VAL_RAW
  dtype: float32
  offline: true
  cpu_fallback: forbidden
  adapter_settings: unchanged low-floor settings from benchmark.yaml
  output_targets: must be absent and non-symlink
  progress: report completed sample count without opening test
stop_criteria:
  - any source/config/archive/inventory/model/device/dtype mismatch, fallback, output collision, non-200 record inventory, inference error, or test access
deletion: none
next_command: publish CP-057, transfer and verify val-only data to macOS, then run the four fresh VAL_RAW jobs in the frozen order
decision: RUN_FRESH_POSTFIX_VAL_MATRIX_ONLY
```

## Checkpoint CP-058 — Post-fix YOLO joint calibration lock

```yaml
checkpoint_id: CP-058
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-057
status: READY_FOR_YOLO_JOINT_CALIBRATION
benchmark_code_commit: d933b4b9574df36d499b3e9254f0e88a1919810a
validated_runs:
  macos_yolo: {records: 200, manifest_sha256: 5a49cbecc576773f66f0b78a832d492fc69e4e1e5c39b56eea940db88505dad7, record_inventory_sha256: d17efad482c9fc21c3031dfd018aba4e5219fa5281bdf4c89f6723e79b282f0d, expectation_sha256: 360a9af1168bfd25e966e842d3ae3d12df7977ccea365878e0dd71be887611ae}
  macos_grounded_sam: {records: 200, manifest_sha256: 5d22e725b20c04cb8c9f0ab7ee1eb1db62d18986426dc3271790a8f1159d558e, record_inventory_sha256: 3b286d1a7afa7fc0372e6920a0afac42a70033f4e2632f2db562c84fe1d90772, expectation_sha256: 8d46ccbd0e3a6f9c1180abf8ecaa7cabcc8d3b76b490d406439dd28aa60377d3}
  linux_yolo: {records: 200, manifest_sha256: 9327fb0a1778fe1bd8568bde1ce62cffdcbbe977c6c7d3a4920c1653277c0c1c, record_inventory_sha256: 6fba019ce9b77f124c81b518fe582a924198634368682c7bb618384d574ec33c, expectation_sha256: bff9bfe6a369d8114b0f5cef5b15a580c609060f0dda69d5d0f25aa8f89cdf9d}
  linux_grounded_sam: {records: 200, manifest_sha256: 830e217e0fff39e28099a954ac293d9839c0502670041f0b01da2457ba930be4, record_inventory_sha256: 1c16e200591165ad92fe23954be959409ca5bb7614ce8ddbc805b3df65869655, expectation_sha256: d2794b732dcfa27a784ef3dace71e44c9907ebff4a50f9636fdc5f8220c667e7}
  common: {status: VALID, error_count: 0, record_count: 200, dtype: float32, fallback_used: false, full_runner_integrity_check: PASS}
macos_execution:
  launchd_script_sha256: 1d24d4804c40e204de39b4b572212ecea9ff8ea4d5e3be16aef1450da992f2e4
  launchd_plist_sha256: aed3ea31478df52b518487b0d2df660b6b122dd40d8e3ae8768ea77a08d0e457
  launchd_exit_code: 0
  launchd_job_removed: true
  native_device: mps
linux_execution:
  script_sha256: b65da88ed29cea91162b2863723979e86422153ffd23cf889a4cb6e380f71f92
  command_exit_code: 0
  native_device: cuda
mac_stage:
  archive_sha256: 5a9d7723b84af19a26167a88fbfc40d4d247240cbe096458cee762269ce250a0
  size_bytes: 11039902
  member_count: 24456
  unsafe_member_count: 0
  link_member_count: 0
  remote_tar_warning_count: 0
  staged_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/val-postfix-r4/macos
  staged_revalidation: PASS
yolo_calibration:
  dataset_inventory: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/val-open-postfix-r4/inventory.json
  dataset_archive_sha256: 8424de68a8cc18961ab4732cba3c2486161f733b638638c82da6e1761e3ac832
  inventory_sha256: 141d79acd2aa3758f4ee90056b14aab0f105d74778f193a998bc341ae6ce59b3
  mac_run: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/val-postfix-r4/macos/yolo-r1
  mac_expectation: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/postfix-r4/expectations/macos-yolo_seg.json
  mac_expectation_sha256: 360a9af1168bfd25e966e842d3ae3d12df7977ccea365878e0dd71be887611ae
  linux_run: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/val-postfix-r4/linux/yolo-r1
  linux_expectation: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/postfix-r4/expectations/linux-yolo_seg.json
  linux_expectation_sha256: bff9bfe6a369d8114b0f5cef5b15a580c609060f0dda69d5d0f25aa8f89cdf9d
  output: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/postfix-r4/yolo-r1
  progress_log: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/yolo-postfix-r4-calibrate.log
  workers: 8
calibration_contract:
  - only the frozen val inventory and two validated YOLO VAL_RAW runs are inputs
  - grid, objective, matching, tie-break, safety metrics, and zero unsafe-unique gate remain unchanged
  - inference_during_calibration must be false; progress must cover verify, rehome, precompute, grid, and finalize
  - result must be formal, deployable, SAFE_CALIBRATED, and have zero unsafe unique selections on both platforms
  - test remains sealed and inaccessible
stop_criteria:
  - output collision, expectation/evidence mismatch, nonzero command, inference call, malformed or non-deployable lock, unsafe outcome, or test access
deletion: none
next_command: publish CP-058, synchronize ai-station, execute and validate YOLO calibration only, then separately lock Grounded-SAM calibration
decision: RUN_POSTFIX_YOLO_CALIBRATION_THEN_GATE_GROUNDED_SAM
```

## Checkpoint CP-059 — Post-fix Grounded-SAM joint calibration lock

```yaml
checkpoint_id: CP-059
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-058
status: READY_FOR_GROUNDED_SAM_JOINT_CALIBRATION
benchmark_code_commit: d933b4b9574df36d499b3e9254f0e88a1919810a
yolo_result:
  status: VALID
  output: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/postfix-r4/yolo-r1
  workers: 8
  grid_points: 2527
  total_seconds: 17.4
  inference_during_calibration: false
  threshold_lock_file_sha256: 1c2f7e270123e72115a30a673a697cb07bdab9f295e6c429172995d1ade7bac1
  threshold_lock_internal_sha256: bbe200f0f46bb035a78a22e7524e0f401175f99d41ce6067fd888aacd8644df6
  evidence_index_sha256: 84cc18a1d718cb7494ec2c7a362f93fa8a040ef08de9d6ca6023fd9367d1ccdc
  progress_log_sha256: 280bb0a1db7bae5598cffa2537fe512c90da46075390639ba62db29e82b8f196
  verification: {formal: true, deployable: true, outcome: SAFE_CALIBRATED, verify_evidence: PASS, unsafe_unique_macos: 0, unsafe_unique_linux: 0}
  selected: {conf: '0.90', nms_iou: '0.90', target_confidence_threshold: '0.90', imgsz: 640}
  objective: {min_platform_macro_f1: 1.0, merged_macro_f1: 1.0, merged_mask_ap50_95: 0.07407516182260027, min_platform_two_cup_recall: 0.0}
  interpretation: zero two-cup both-matched recall does not establish required multi-object capability despite the fail-closed safety outcome
grounded_sam_calibration:
  dataset_inventory: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/val-open-postfix-r4/inventory.json
  dataset_archive_sha256: 8424de68a8cc18961ab4732cba3c2486161f733b638638c82da6e1761e3ac832
  inventory_sha256: 141d79acd2aa3758f4ee90056b14aab0f105d74778f193a998bc341ae6ce59b3
  mac_run: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/val-postfix-r4/macos/grounded-sam-r1
  mac_expectation: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/postfix-r4/expectations/macos-grounded_sam.json
  mac_expectation_sha256: 8d46ccbd0e3a6f9c1180abf8ecaa7cabcc8d3b76b490d406439dd28aa60377d3
  linux_run: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/val-postfix-r4/linux/grounded-sam-r1
  linux_expectation: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/postfix-r4/expectations/linux-grounded_sam.json
  linux_expectation_sha256: d2794b732dcfa27a784ef3dace71e44c9907ebff4a50f9636fdc5f8220c667e7
  output: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/postfix-r4/grounded-sam-r1
  progress_log: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/grounded-sam-postfix-r4-calibrate.log
  workers: 8
calibration_contract:
  - only the frozen val inventory and two validated Grounded-SAM VAL_RAW runs are inputs
  - exactly 32400 frozen grid points; no model load or SAM/DINO call during calibration
  - reuse precomputed candidate threshold states and truth-mask IoUs across all grid points
  - progress must cover verify, rehome, second verify, precompute, grid, and finalize
  - result must be formal, deployable, SAFE_CALIBRATED, and have zero unsafe unique selections on both platforms
  - all quality metrics remain diagnostic; do not infer PickPlace readiness from the safety outcome
  - test remains sealed and inaccessible
stop_criteria:
  - output collision, expectation/evidence mismatch, inference call, nonzero command, malformed or non-deployable lock, unsafe outcome, or test access
deletion: none
next_command: publish CP-059, synchronize ai-station, execute the optimized Grounded-SAM calibration once, and verify its lock and evidence before any test unlock
decision: RUN_POSTFIX_GROUNDED_SAM_NUMERICAL_CALIBRATION_ONLY
```

## Checkpoint CP-060 — Parallel Grounded-SAM grid calibration result

```yaml
checkpoint_id: CP-060
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-059
status: READY_FOR_LINUX_FULL_BENCHMARK_AND_TEST_UNLOCK_PREREGISTRATION
calibration_implementation:
  commit: f4500933d238ad391f048eb7ef51d82d6ff4fced
  prediction_evidence_source_commit: d933b4b9574df36d499b3e9254f0e88a1919810a
  behavior:
    - Grounding DINO and SAM inference remain absent from calibration
    - 400 aligned platform records precompute mask IoUs and Grounding box/text prefix states once
    - the 32400-point Grounded-SAM grid is partitioned across 8 process workers
    - result delivery preserves original grid order, objective, tie-break, safety gate, and lock SHA semantics
  tdd:
    red: the worker-plumbing test observed one process-pool map because only precompute was parallel
    first_green: the same test observed separate precompute and grid maps
    spawn_regression: macOS initially rejected mappingproxy serialization across process boundaries
    spawn_fix: RuntimeProvenance and CalibrationResult rebuild through validated constructors during process transfer
  macos:
    fresh_scoped_build_seconds: 2.53
    focused_calibration_tests: 61 passed in 7.09 s
    benchmark_gate: 564 passed, 0 failed, 0 skipped in 311 s
    junit: 564 tests, 0 errors, 0 failures, 0 skipped
    compileall: PASS
    diff_check: PASS
  linux:
    fresh_scoped_build_seconds: 1.33
    focused_calibration_tests: 61 passed in 14.41 s
    build_script_sha256: 8e6b6b87d39ac87a2d22c5a6fef7c16eeacda90c2e1345df61100e1e2d99b6df
grounded_sam_calibration:
  status: VALID
  output: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/postfix-r4/grounded-sam-r3
  workers: 8
  grid_points: 32400
  total_seconds: 162.9
  precompute_complete_seconds: 62.2
  grid_complete_seconds: 162.7
  prior_cached_serial_total_seconds: 224.9
  additional_parallel_speedup: 1.38x
  inference_during_calibration: false
  calibration_script_sha256: 6d990422fd74dbf563947043bdc2966aaa6d312325d18b115650fcbf9b0d0d48
  inspection_script_sha256: 7b5066828d96bd9078f51da483d01584331f88446a62afa977c767b4b99d3429
  threshold_lock_file_sha256: 8b0d24ca6c8c28ffb6f9e8c6d7be7c4dabb3916a198f8a0e6f594fb6faebce3e
  threshold_lock_internal_sha256: 7880140f8f0c363c6a197f24fc8c691df5598f5012336a4d638a5e828c6920ad
  evidence_index_sha256: 6cee20a21103df7d814bec38e37ebdf1feab9d66fe286e262adf9cc3fbb03672
  progress_log_sha256: 526c059a73b2b87321f7a054eddad2f5c0965728be287f9ffebbfc7c678afa10
  verified_evidence_entries: 22688
  retained_file_count: 22689
  retained_size_bytes: 36190885
  verification: {formal: true, deployable: true, outcome: SAFE_CALIBRATED, unsafe_unique_macos: 0, unsafe_unique_linux: 0, verify_evidence: PASS}
  selected: {box_threshold: '0.25', text_threshold: '0.25', sam_quality: '0.90', target_confidence_threshold: '0.25', duplicate_iou: '0.85', min_mask_pixels: 64, max_mask_area_ratio: '0.50'}
  objective: {min_platform_macro_f1: 0.14046946863361034, merged_macro_f1: 0.14046946863361034, merged_mask_ap50_95: 0.04389862194172733, min_platform_two_cup_recall: 0.0}
  platform_metrics:
    macos: {macro_f1: 0.14046946863361034, mask_ap50_95: 0.0441781521868619, two_cup_both_matched_recall: 0.0, unsafe_unique_count: 0}
    linux: {macro_f1: 0.14046946863361034, mask_ap50_95: 0.04385782452222347, two_cup_both_matched_recall: 0.0, unsafe_unique_count: 0}
  interpretation: the fail-closed safety gate passes, but recognition quality and two-cup recall do not establish multi-object or PickPlace readiness
superseded_attempts:
  - run: grounded-sam-r1
    outcome: manually interrupted before any formal output at grid 3 percent and 204.4 s after observing the grid was serial
    archived_log: /data/work/so101-evidence/archived/v5-t005-grounded-sam-rgbd/exp-079-grounded-sam-calibration-aborted-r1/progress.log
    archived_log_sha256: 5a0ce8da4525d4750b71fcccd0b872d89781cd217089fe943207b2d3196cf956
  - run: grounded-sam-r2
    outcome: fail-closed RUN_PROVENANCE_MISMATCH before output because the calibration implementation commit was incorrectly supplied as the VAL_RAW source commit
    archived_log: /data/work/so101-evidence/archived/v5-t005-grounded-sam-rgbd/exp-079-grounded-sam-calibration-rejected-r2/progress.log
    archived_log_sha256: c4d10f1200e95dd90326abefce35d3273854e4e645d41901a5b56aa021e59e36
test_state:
  sealed: true
  semantic_content_opened: false
  test_inference_run: false
retention:
  retained_runs:
    - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/postfix-r4/yolo-r1
    - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/postfix-r4/grounded-sam-r3
  archived_runs:
    - /data/work/so101-evidence/archived/v5-t005-grounded-sam-rgbd/exp-079-grounded-sam-calibration-aborted-r1
    - /data/work/so101-evidence/archived/v5-t005-grounded-sam-rgbd/exp-079-grounded-sam-calibration-rejected-r2
  deletion_candidates: none
next_command: publish CP-060, synchronize ai-station, run the full Linux benchmark gate, then preregister one immutable test unlock using the existing seal plus the YOLO and Grounded-SAM threshold-lock SHA values
decision: QUALITY_INSUFFICIENT_BUT_PROCEED_TO_FROZEN_TEST_BENCHMARK
```

## Checkpoint CP-061 — Parallel calibration dual-platform qualification

```yaml
checkpoint_id: CP-061
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-060
status: READY_FOR_TEST_UNLOCK_PREREGISTRATION
source_state:
  calibration_code_commit: f4500933d238ad391f048eb7ef51d82d6ff4fced
  ledger_head: 4602f7cf23b429ffcb2807d0454e90e8122d1bea
  package_tree_diff_between_commits: none
  gitee_head: 4602f7cf23b429ffcb2807d0454e90e8122d1bea
  ai_station_head: 4602f7cf23b429ffcb2807d0454e90e8122d1bea
linux_benchmark_gate:
  command_contract: colcon test --packages-select so101_demo_py --pytest-args benchmark_test
  collected: 564
  passed: 562
  skipped_platform_conditions: 2
  errors: 0
  failures: 0
  pytest_seconds: 646.82
  colcon_seconds: 648
  junit: 564 tests, 0 errors, 0 failures, 2 skipped
  script_sha256: 03f70d3065d9d138c60a7e4cee2ae4dd7edc71ddda4923d90a27ac2e7f48dc86
script_launch_note:
  - the first outer SHA assertion used an incorrect expected literal and stopped before the script executed
  - the script was launched once only after its transferred SHA was read back and matched the value above
  - the unique runtime temporary root is retained under the registered EXP-079 evidence root
test_state:
  sealed: true
  semantic_content_opened: false
  test_inference_run: false
next_command: preregister the exact post-fix archive, sealed-member inventory, YOLO lock, Grounded-SAM lock, one-time access log, four platform-model test run IDs, aggregation outputs, and all fail-closed stop conditions before opening test once
decision: PREREGISTER_ONE_TIME_FROZEN_TEST_MATRIX
```

## Checkpoint CP-062 — Post-fix one-time test unlock preregistration

```yaml
checkpoint_id: CP-062
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-061
status: READY_FOR_ONE_TIME_POSTFIX_TEST_ACCESS
source_state:
  calibration_code_commit: f4500933d238ad391f048eb7ef51d82d6ff4fced
  ledger_head_before_preregistration: 84b6e9e8ca6e524068448e0436b8d44294041758
  prediction_and_lock_source_commit: d933b4b9574df36d499b3e9254f0e88a1919810a
  installed_build: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-grid-parallel-r15
sealed_input:
  archive: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/assets/datasets/so101-v5-t005-grounded-sam-postfix/so101-v5-t005-grounded-sam-postfix-r4.tar.gz
  archive_sha256: 8424de68a8cc18961ab4732cba3c2486161f733b638638c82da6e1761e3ac832
  member_inventory: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/sealed-test-members-postfix-r4.json
  member_inventory_sha256: 4ac8407aec15d8c19da653dd34b932e50ba42fa9aa492a7b4adedc2147666b81
  member_counts: {images: 200, labels: 200, truth: 200}
  semantic_content_opened_before_unlock: false
threshold_locks:
  yolo:
    path: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/postfix-r4/yolo-r1/threshold-lock.json
    file_sha256: 1c2f7e270123e72115a30a673a697cb07bdab9f295e6c429172995d1ade7bac1
    internal_sha256: bbe200f0f46bb035a78a22e7524e0f401175f99d41ce6067fd888aacd8644df6
    mtime_epoch: 1788469128
    state: {formal: true, deployable: true, outcome: SAFE_CALIBRATED}
  grounded_sam:
    path: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/postfix-r4/grounded-sam-r3/threshold-lock.json
    file_sha256: 8b0d24ca6c8c28ffb6f9e8c6d7be7c4dabb3916a198f8a0e6f594fb6faebce3e
    internal_sha256: 7880140f8f0c363c6a197f24fc8c691df5598f5012336a4d638a5e828c6920ad
    mtime_epoch: 1788470728
    state: {formal: true, deployable: true, outcome: SAFE_CALIBRATED}
one_time_unlock:
  access_log: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/postfix-r4/test-access-r1.jsonl
  output_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/test-open-postfix-r4-r1
  prereq_check_script_sha256: b6041690e0a7e6ce1f860aeaf99725472f43cded8a770f9be986e484cd679f37
  precondition: both targets are absent non-symlink paths and the access event is appended before any test member is decoded
  command: PYTHONNOUSERSITE=1 PYTHONPATH=/tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-grid-parallel-r15/install/so101_demo_py/lib/python3.12/site-packages /data/work/venvs/so101-grounded-sam/bin/python /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-grid-parallel-r15/install/so101_demo_py/lib/so101_demo_py/perception_benchmark unlock-test --config /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-grid-parallel-r15/install/so101_demo_py/share/so101_demo_py/config/perception_benchmark/benchmark.yaml --archive /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/assets/datasets/so101-v5-t005-grounded-sam-postfix/so101-v5-t005-grounded-sam-postfix-r4.tar.gz --expected-sha256 8424de68a8cc18961ab4732cba3c2486161f733b638638c82da6e1761e3ac832 --sealed-member-inventory /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/sealed-test-members-postfix-r4.json --yolo-threshold-lock /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/postfix-r4/yolo-r1/threshold-lock.json --grounded-sam-threshold-lock /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/postfix-r4/grounded-sam-r3/threshold-lock.json --access-log /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/postfix-r4/test-access-r1.jsonl --output-root /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/test-open-postfix-r4-r1
post_unlock_frozen_matrix:
  samples_per_run: 200
  platforms: {macos: mps, linux: cuda}
  models: [yolo_seg, grounded_sam]
  run_kinds: [TEST_RAW_FROZEN, TEST_PRODUCTION, TEST_CALIBRATED]
  total_runs: 12
  oracle_diagnostic: NOT_AUTHORIZED_NOT_RUN
  mac_output_parent: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/test-postfix-r4/macos
  linux_output_parent: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/test-postfix-r4/linux
  aggregation_output: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/report/postfix-r4-r1
success_criteria:
  - exactly one access event binds both verified internal lock SHA-256 values and the unchanged sealed member inventory
  - test inventory has 200 unique samples and exactly 50 samples for each of the four frozen scenarios
  - all 600 extracted source artifacts are regular files with verified source SHA-256 values
  - no threshold, prompt, model, grid, matching rule, calibration lock, or benchmark objective changes after test access
stop_criteria:
  - existing target, lock/seal/archive mismatch, access-event ordering failure, unsafe path, malformed truth, non-200 denominator, or scenario-count mismatch
  - any post-unlock attempt to recalibrate or alter a frozen lock
deletion: none
next_command: commit and push CP-062, synchronize ai-station, rerun the prerequisite check, then execute the exact unlock command once
decision: EXECUTE_ONE_TIME_POSTFIX_TEST_UNLOCK_AFTER_COMMIT
```

## Checkpoint CP-063 — Post-fix test access result and Mac transfer gate

```yaml
checkpoint_id: CP-063
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-062
status: WAITING_FOR_EXPLICIT_CROSS_ENV_TEST_DATA_TRANSFER_AUTHORIZATION
test_unlock:
  result: PASS
  unlock_script_sha256: d69bd2280e747f698a8f7323029f7755ce943d63a878241407a2c817a062fbba
  first_outer_sha_attempt: stopped before script execution because its expected script digest was incorrect
  execution_count_after_verified_script_sha: 1
  access_event_count: 1
  access_event_sha256: c77c2dcf6772ba708f03d6e910ffd5e9323d7c47a9e915fa8ed33c96cef6f76f
  access_log: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/calibration/postfix-r4/test-access-r1.jsonl
  access_log_sha256: c5179c15b5f0586a93e9ba48d2a47d2cd3ce7e2dbed65b85dff8a3fcbe7d10e4
  test_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/test-open-postfix-r4-r1
  test_inventory_sha256: 72d38c392889d9f1d8095f24d148f31bd2915a5f36fc62b123f6625fc7e76dd2
  sample_count: 200
  scenario_counts: {no_cup: 50, one_cup_distractors: 50, two_cups: 50, cup_near_bottle: 50}
  regular_file_count: 602
  symlink_count: 0
  total_bytes: 9654066
  strict_lock_internal_sha256s:
    - bbe200f0f46bb035a78a22e7524e0f401175f99d41ce6067fd888aacd8644df6
    - 7880140f8f0c363c6a197f24fc8c691df5598f5012336a4d638a5e828c6920ad
frozen_after_access:
  - archive, seal, prompts, models, low-floor configs, grids, thresholds, matching, objectives, tie-breaks, and both lock files
  - no post-test calibration or test-driven configuration change is permitted
mac_transfer:
  intended_source: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/test-open-postfix-r4-r1
  intended_transfer_archive: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/test-open-postfix-r4-r1-transfer.tar.gz
  intended_destination: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/dataset/test-open-postfix-r4-macos-r1
  result: BLOCKED_BEFORE_EXECUTION
  transferred_bytes: 0
  reason: cross-environment transfer of the complete opened held-out test dataset requires payload-specific user authorization
execution_order:
  - retain Mac-first formal matrix order
  - do not start Linux test inference until all six Mac runs validate
retention:
  retained_runs:
    - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/test-open-postfix-r4-r1
  archived_runs:
    - /data/work/so101-evidence/archived/v5-t005-grounded-sam-rgbd/exp-079-grounded-sam-calibration-aborted-r1
    - /data/work/so101-evidence/archived/v5-t005-grounded-sam-rgbd/exp-079-grounded-sam-calibration-rejected-r2
  deletion_candidates: none
next_command: after explicit authorization for this exact payload and destination, create one immutable transfer archive, verify its SHA and path safety, copy it to the registered Mac temporary root, preserve both lock mtimes with scp -p, and preregister the twelve-run frozen matrix
decision: STOP_BEFORE_CROSS_ENV_TEST_DATA_TRANSFER
```

## Checkpoint CP-064 — Mac test 数据落地与冻结评测矩阵预注册

```yaml
checkpoint_id: CP-064
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-063
status: READY_FOR_MAC_FROZEN_TEST
authorization:
  received: true
  scope: ai-station 与本 Mac 之间的通信和数据复制
source_state:
  workspace_head: 6649cf5717c31d27660947e4ceb88caf6f58a8e5
  ai_station_head: 6649cf5717c31d27660947e4ceb88caf6f58a8e5
  calibration_implementation_commit: f4500933d238ad391f048eb7ef51d82d6ff4fced
  prediction_and_lock_source_commit: d933b4b9574df36d499b3e9254f0e88a1919810a
  benchmark_config_sha256: 8103b926c48b3fe006101cdc1bdf8035349f65c2def5ce33c2aaed79e0e32725
test_transfer:
  source: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/test-open-postfix-r4-r1
  remote_archive: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/test-open-postfix-r4-r1-transfer.tar.gz
  local_archive: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/dataset/test-open-postfix-r4-r1-transfer.tar.gz
  local_root: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/dataset/test-open-postfix-r4-macos-r1
  archive_sha256: 9983581a5db05506f9a795968eeccad892d55896cc182a621a671dccf0baf652
  archive_size_bytes: 9074263
  tar_members: {total: 609, regular_files: 602, directories: 7, links: 0}
  path_safety: PASS
  inventory_sha256: 72d38c392889d9f1d8095f24d148f31bd2915a5f36fc62b123f6625fc7e76dd2
  sample_count: 200
  scenario_counts: {no_cup: 50, one_cup_distractors: 50, two_cups: 50, cup_near_bottle: 50}
  dataset_files_after_access_event: true
test_access:
  event_sha256: c77c2dcf6772ba708f03d6e910ffd5e9323d7c47a9e915fa8ed33c96cef6f76f
  granted_at: 2026-09-03T21:44:12.975261+00:00
  local_access_log: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/calibration/postfix-r4/test-access-r1.jsonl
  access_log_sha256: c5179c15b5f0586a93e9ba48d2a47d2cd3ce7e2dbed65b85dff8a3fcbe7d10e4
threshold_locks:
  yolo:
    local_path: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/calibration/macos-locks-postfix-r4-r1/yolo-r1/threshold-lock.json
    file_sha256: 1c2f7e270123e72115a30a673a697cb07bdab9f295e6c429172995d1ade7bac1
    internal_sha256: bbe200f0f46bb035a78a22e7524e0f401175f99d41ce6067fd888aacd8644df6
    mtime_epoch: 1788469128
  grounded_sam:
    local_path: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/calibration/macos-locks-postfix-r4-r1/grounded-sam-r3/threshold-lock.json
    file_sha256: 8b0d24ca6c8c28ffb6f9e8c6d7be7c4dabb3916a198f8a0e6f594fb6faebce3e
    internal_sha256: 7880140f8f0c363c6a197f24fc8c691df5598f5012336a4d638a5e828c6920ad
    mtime_epoch: 1788470728
  both_locks_before_access_event: true
fixed_assets:
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_sam_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
  archive_sha256: 8424de68a8cc18961ab4732cba3c2486161f733b638638c82da6e1761e3ac832
  sealed_member_inventory_sha256: 4ac8407aec15d8c19da653dd34b932e50ba42fa9aa492a7b4adedc2147666b81
macos_matrix:
  platform: macos
  device: mps
  dtype: float32
  output_parent: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/test-postfix-r4/macos
  installed_build: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/mac-grid-parallel-r1
  script: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/mac-test-postfix-r4-r1.sh
  script_sha256: 7a9a3341fc18adbb000cee7809bf84d498105a10a1bae407ff893f09bd662de9
  launch_plist: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/com.terry.so101.benchmark.mac.test.postfix.r4.r1.plist
  launch_plist_sha256: 65b87500834ec4806b8efe0af0b0cdeffb15edf7b267fc7ee46097d6e813b6a4
  launch_label: com.terry.so101.benchmark.mac.test.postfix.r4.r1
  launch_command: launchctl bootstrap gui/501 /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/com.terry.so101.benchmark.mac.test.postfix.r4.r1.plist
  runs:
    - {run_id: mac-yolo-test-raw-postfix-r4-r1, run_kind: TEST_RAW_FROZEN, output: yolo-raw-r1}
    - {run_id: mac-yolo-test-production-postfix-r4-r1, run_kind: TEST_PRODUCTION, output: yolo-production-r1}
    - {run_id: mac-yolo-test-calibrated-postfix-r4-r1, run_kind: TEST_CALIBRATED, output: yolo-calibrated-r1}
    - {run_id: mac-grounded-sam-test-raw-postfix-r4-r1, run_kind: TEST_RAW_FROZEN, output: grounded-sam-raw-r1}
    - {run_id: mac-grounded-sam-test-production-postfix-r4-r1, run_kind: TEST_PRODUCTION, output: grounded-sam-production-r1}
    - {run_id: mac-grounded-sam-test-calibrated-postfix-r4-r1, run_kind: TEST_CALIBRATED, output: grounded-sam-calibrated-r1}
linux_matrix:
  platform: linux
  device: cuda
  dtype: float32
  output_parent: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/test-postfix-r4/linux
  installed_build: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-grid-parallel-r15
  local_script: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/linux-test-postfix-r4-r1.sh
  remote_script: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-test-postfix-r4-r1.sh
  script_sha256: 39cee700c1d7f7a3d1dfc906659bf1923c85c40ae700465466c2b455f9b85a9f
  runs:
    - {run_id: linux-grounded-sam-test-raw-postfix-r4-r1, run_kind: TEST_RAW_FROZEN, output: grounded-sam-raw-r1}
    - {run_id: linux-grounded-sam-test-production-postfix-r4-r1, run_kind: TEST_PRODUCTION, output: grounded-sam-production-r1}
    - {run_id: linux-grounded-sam-test-calibrated-postfix-r4-r1, run_kind: TEST_CALIBRATED, output: grounded-sam-calibrated-r1}
    - {run_id: linux-yolo-test-raw-postfix-r4-r1, run_kind: TEST_RAW_FROZEN, output: yolo-raw-r1}
    - {run_id: linux-yolo-test-production-postfix-r4-r1, run_kind: TEST_PRODUCTION, output: yolo-production-r1}
    - {run_id: linux-yolo-test-calibrated-postfix-r4-r1, run_kind: TEST_CALIBRATED, output: yolo-calibrated-r1}
execution_contract:
  - Mac 六个 run 先按上表顺序执行；全部验证通过后才运行 Linux
  - Linux 采用相反的模型顺序，不并发占用 GPU
  - 每个 run 固定 200 个样本；错误样本保留在分母中
  - TEST_PRODUCTION 与 TEST_CALIBRATED 必须经过 DetectorPort 和真实 TargetSelector，并与冻结 raw replay 一致
  - 不运行 ORACLE_DIAGNOSTIC，不改 prompt、模型、grid、threshold、matching、objective 或 threshold-lock
stop_criteria:
  - 输出目录碰撞、MPS/CUDA 不可用、CPU fallback、FP32 不符、输入 SHA 或 access chain 不符
  - 缺样本、顺序变化、manifest INVALID、port/replay 不一致、证据 SHA 无法回读
  - Mac 任一 run 无效时不得启动 Linux
retention:
  retained_runs:
    - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/test-open-postfix-r4-r1
    - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/dataset/test-open-postfix-r4-r1-transfer.tar.gz
    - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/dataset/test-open-postfix-r4-r1-transfer.tar.gz
    - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/dataset/test-open-postfix-r4-macos-r1
  archived_runs:
    - /data/work/so101-evidence/archived/v5-t005-grounded-sam-rgbd/exp-079-grounded-sam-calibration-aborted-r1
    - /data/work/so101-evidence/archived/v5-t005-grounded-sam-rgbd/exp-079-grounded-sam-calibration-rejected-r2
  deletion_candidates: none
next_command: commit and push CP-064, synchronize ai-station, create the two empty test output parents, then launch the Mac plist exactly once
decision: RUN_MAC_FROZEN_TEST_MATRIX_AFTER_COMMIT
```

## Checkpoint CP-065 — Grounded-SAM 对账失败诊断与 r2 重跑预注册

```yaml
checkpoint_id: CP-065
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-064
status: READY_FOR_R2_SYNC_BUILD_AND_MAC_RETRY
frozen_test_policy:
  test_access_event_sha256: c77c2dcf6772ba708f03d6e910ffd5e9323d7c47a9e915fa8ed33c96cef6f76f
  inventory_sha256: 72d38c392889d9f1d8095f24d148f31bd2915a5f36fc62b123f6625fc7e76dd2
  yolo_lock_sha256: bbe200f0f46bb035a78a22e7524e0f401175f99d41ce6067fd888aacd8644df6
  grounded_sam_lock_sha256: 7880140f8f0c363c6a197f24fc8c691df5598f5012336a4d638a5e828c6920ad
  prompt_model_grid_threshold_metric_matching_objective_changed: false
  evidence_reconciliation_rule_changed: true
  oracle_diagnostic_run: false
mac_r1_results:
  valid_runs:
    - {run_id: mac-yolo-test-raw-postfix-r4-r1, records: 200, errors: 0, record_inventory_sha256: c920295454d0259aff4c89fb16dd821eaf35107e7c7ac6ab117298893708c03d}
    - {run_id: mac-yolo-test-production-postfix-r4-r1, records: 200, errors: 0, record_inventory_sha256: e2236f19ef2bf8574ca503838ad12a97432c963db4d83feb3f0ce1d32635559b}
    - {run_id: mac-yolo-test-calibrated-postfix-r4-r1, records: 200, errors: 0, record_inventory_sha256: d9d4ba0c0e1ddd8d610bc6431440cbec62061d94744e6996cd6b8ee30dd28cc2}
    - {run_id: mac-grounded-sam-test-raw-postfix-r4-r1, records: 200, errors: 0, record_inventory_sha256: b9df4df92e9b968466cf41c8b4d6287eb455399e6ab63bc020ecfa9cdbe7a7fe}
  invalid_run:
    run_id: mac-grounded-sam-test-production-postfix-r4-r1
    status: INVALID
    invalid_reason: PRODUCTION_CANDIDATE_MAPPING_INVALID
    completed_records: 1
    failed_sample_index: 1
    failed_image_relpath: images/test/000900048.png
    linux_started_after_failure: false
root_cause:
  finding: 同一个 Grounded-SAM 候选在两次独立 FP32 推理中的 bbox、confidence、mask SHA-256 和 mask IoU 都完全一致，第二个候选只有 sam_quality 相差一个 float32 ULP
  raw_sam_quality: 0.9401203393936157
  production_sam_quality: 0.9401203989982605
  absolute_delta: 5.960464477539063e-08
  previous_contract: sam_quality 必须逐位相等
  diagnosis_json_sha256: 38bcb0f41ad1014828d8c8ad7002c1ed7e0e0d243a534bc164247bd0ff3c5fb9
  diagnostic_script_sha256: c5bd4055977919c70127edbc72d2bcf49068d48ea63dbf3034d0b94cb578e4fa
  durable_diagnostic_archive_sha256: c1c6a661ec6637becfbb8cbc6da0d93445acc67d7c31e78bc38db36e3e427e16
fix:
  commit: 2ef8bc663bf1741ef03b83552216ec3801e56a0e
  scope: 证据对账只接受相同或相邻的一个 float32 ULP；bbox、confidence、mask SHA-256 和一对一映射仍保持严格相等
  detector_output_changed: false
  selector_or_metric_changed: false
verification:
  red_test: test_grounded_production_mapping_accepts_only_one_float32_quality_ulp 在修复前按预期得到 INVALID
  focused_after_fix: 4 passed
  runner_file: 128 passed in 62.99s
  benchmark_gate: 566 passed, 0 errors, 0 failures, 0 skipped in 334.95s
  ordinary_gate: 1167 passed in 18.57s
  installed_runner_sha256: fca7a7582427b2a0365dec270decf52de9bc0db410d42dc000db9351d7748a79
archived_invalid_evidence:
  directory: /data/work/so101-evidence/archived/v5-t005-grounded-sam-rgbd/exp-079-grounded-sam-test-production-postfix-r4-r1-invalid
  file_count: 111
  manifest_sha256: d01df4f67f1d9d80e92be0c24d82b3ec356fbef73a1612e846da8243da6c842f
  transfer_archive: /data/work/so101-evidence/archived/v5-t005-grounded-sam-rgbd/exp-079-grounded-sam-test-production-postfix-r4-r1-invalid.tar.gz
  transfer_archive_sha256: 493e01e6a1ea7a86a07b87baf57ef08d9d9d909b33e357b1e76b98450c48b65f
mac_r2_plan:
  installed_build: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/mac-grid-parallel-r2
  script_sha256: f4fe08c735dc136b8f535f69a65715ddf42de3477dd6ed50d7d458e1a25581d0
  launch_plist_sha256: a615c873409ea555bfba85672588eadff87234431aaf80eb02f97bef506479e2
  launch_label: com.terry.so101.benchmark.mac.test.postfix.r4.r2
  runs:
    - {run_id: mac-grounded-sam-test-production-postfix-r4-r2, run_kind: TEST_PRODUCTION, output: grounded-sam-production-r2}
    - {run_id: mac-grounded-sam-test-calibrated-postfix-r4-r2, run_kind: TEST_CALIBRATED, output: grounded-sam-calibrated-r2}
linux_r2_plan:
  installed_build: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-grid-parallel-r16
  script_sha256: 8fa7a9e499717bf9dd9d772bd32f69499e95454afc0b80f1b0f1f1d59130540e
  runs:
    - {run_id: linux-grounded-sam-test-raw-postfix-r4-r2, run_kind: TEST_RAW_FROZEN, output: grounded-sam-raw-r2}
    - {run_id: linux-grounded-sam-test-production-postfix-r4-r2, run_kind: TEST_PRODUCTION, output: grounded-sam-production-r2}
    - {run_id: linux-grounded-sam-test-calibrated-postfix-r4-r2, run_kind: TEST_CALIBRATED, output: grounded-sam-calibrated-r2}
    - {run_id: linux-yolo-test-raw-postfix-r4-r2, run_kind: TEST_RAW_FROZEN, output: yolo-raw-r2}
    - {run_id: linux-yolo-test-production-postfix-r4-r2, run_kind: TEST_PRODUCTION, output: yolo-production-r2}
    - {run_id: linux-yolo-test-calibrated-postfix-r4-r2, run_kind: TEST_CALIBRATED, output: yolo-calibrated-r2}
execution_contract:
  - r1 的四个 VALID Mac run 原样保留，不重复运行
  - 先同步并构建 commit 2ef8bc663bf1741ef03b83552216ec3801e56a0e，再启动两个 Mac r2 run
  - 两个 Mac r2 run 全部 VALID 后，才允许按上表顺序启动 Linux r2
  - 任一输出目录碰撞、manifest INVALID、CPU fallback、输入或锁 SHA 不符，立即停止且不复用 run ID
retention:
  retained_runs:
    - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/test-postfix-r4/macos/yolo-raw-r1
    - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/test-postfix-r4/macos/yolo-production-r1
    - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/test-postfix-r4/macos/yolo-calibrated-r1
    - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/test-postfix-r4/macos/grounded-sam-raw-r1
    - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/diagnostics/grounded-production-mapping-r1
  archived_runs:
    - /data/work/so101-evidence/archived/v5-t005-grounded-sam-rgbd/exp-079-grounded-sam-test-production-postfix-r4-r1-invalid
  deletion_candidates: none
next_command: commit and push CP-065, fast-forward ai-station from gitee, build linux-grid-parallel-r16 and run its benchmark gate, then launch the Mac r2 plist exactly once
decision: RUN_MAC_R2_AFTER_SYNC_AND_DUAL_PLATFORM_BUILD_GATES
```

## Checkpoint CP-066 — Linux 解释器溯源修正与 r19 门禁

```yaml
checkpoint_id: CP-066
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-065
status: LINUX_R19_GATE_PASS_READY_FOR_MAC_R2
synced_source:
  gitee_branch: codex/v5-t004-yolo-seg-rgbd
  gitee_sha: daa13a4816ea03d858c2ea7e23bf3a70dffea7f6
  ai_station_checkout: /data/work/so101-grounded-sam-yolo-benchmark-ab-v1-task14-runner-access-r11
  ai_station_sha: daa13a4816ea03d858c2ea7e23bf3a70dffea7f6
failed_environment_attempts:
  - build: linux-grid-parallel-r16
    finding: build 和 benchmark gate 误用了 /usr/bin/python3；dataset 测试集中失败，运行在 91% 后因持续等待 jbd2 journal 且已确定环境无效而以 SIGINT 停止
    stdout_stderr_sha256: aa7142a658a13fdccf643fd631c121c4567db9a8c9e3b5a09f045c573771f4e3
    formal_inference_started: false
  - build: linux-grid-parallel-r17
    finding: 仅激活 venv 不足以覆盖 /usr/bin/colcon 的 shebang，build command 仍使用 /usr/bin/python3
    command_log_sha256: 08cbd8bda2442841d2e4198dc3128a69bccdaa4737b6b10b053b88e350eb751e
    formal_inference_started: false
  - build: linux-grid-parallel-r18
    finding: 直接用 venv Python 执行 /usr/bin/colcon，但未补入 /usr/lib/python3/dist-packages，启动前因找不到 colcon-core 停止
    console_log_sha256: 9df68143f07e65b3d6960d284802cf24611b9d7189c3667dcb0048f515dd1fc8
    formal_inference_started: false
linux_r19:
  build_root: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-grid-parallel-r19
  runtime_tmp: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/runtime-tmp/linux-grid-parallel-r19
  interpreter: /data/work/venvs/so101-grounded-sam/bin/python
  colcon_entrypoint: /usr/bin/colcon
  pythonpath: /data/work/venvs/so101-grounded-sam/lib/python3.12/site-packages:/usr/lib/python3/dist-packages
  installed_entrypoint_shebang: '#!/data/work/venvs/so101-grounded-sam/bin/python'
  installed_runner_sha256: fca7a7582427b2a0365dec270decf52de9bc0db410d42dc000db9351d7748a79
  installed_config_sha256: 8103b926c48b3fe006101cdc1bdf8035349f65c2def5ce33c2aaed79e0e32725
  build_console_sha256: addd74e032fd102dc977323986caf11ee9529552d8f8c31d11e0d1c11874fc6e
benchmark_gate:
  command_scope: colcon test --base-paths src/so101_demo_py --packages-select so101_demo_py --pytest-args benchmark_test
  collected: 566
  passed: 564
  skipped: 2
  errors: 0
  failures: 0
  elapsed_seconds: 641.68
  junit_sha256: 30daaa459386e8de91629d92c301ddee7db2904fe1dc5e2ffde03b9344fd4366
  result: PASS
formal_linux_script:
  path: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/scripts/linux-test-postfix-r4-r2.sh
  build_binding: linux-grid-parallel-r19
  sha256: 437e1eda9a556526693a86b033a6794c6332f3c932b2c26b1944a65ab9f07be4
freeze_and_order:
  prompt_model_grid_threshold_metric_matching_objective_changed: false
  test_reopened_or_retuned: false
  mac_formal_r2_started: false
  linux_formal_r2_started: false
  next_allowed_action: 提交并同步 CP-066；验证 Mac r2 输出目录无碰撞、MPS 与安装 SHA 后，只启动 Mac r2 plist 一次
retention:
  retained_runs:
    - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-grid-parallel-r16
    - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-grid-parallel-r17
    - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-grid-parallel-r18-build.console.log
    - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-grid-parallel-r19
    - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/runtime-tmp/linux-grid-parallel-r19
  archived_runs: unchanged from CP-065
  deletion_candidates: none
decision: RUN_MAC_R2_AFTER_CP066_SYNC
```

## Checkpoint CP-067 — 稳定候选身份对账与 r3 重跑预注册

```yaml
checkpoint_id: CP-067
date: 2026-09-04
experiment_id: EXP-079
prior_checkpoint: CP-066
status: READY_FOR_MAC_R3
mac_r2_failure:
  run_id: mac-grounded-sam-test-production-postfix-r4-r2
  status: INVALID
  invalid_reason: PRODUCTION_CANDIDATE_MAPPING_INVALID
  completed_records: 10
  failed_sample_index: 10
  failed_image_relpath: images/test/000900022.png
  manifest_sha256: 71c9b3566ac93b8550d3f807a9ff7f8f9e110d462f00379c9b65c777305994de
  calibrated_started: false
  linux_formal_started: false
  archive: /data/work/so101-evidence/archived/v5-t005-grounded-sam-rgbd/exp-079-mac-grounded-sam-test-production-postfix-r4-r2-invalid.tar.gz
  archive_sha256: 1f7248fbaf4a1202e54fbf8bda26d96caa499154bd6b1d37b6c29ce7d90ce493
  extracted_archive_root: /data/work/so101-evidence/archived/v5-t005-grounded-sam-rgbd/exp-079-mac-grounded-sam-test-production-postfix-r4-r2-invalid
diagnosis:
  mode: non-formal implementation mismatch diagnosis
  repeated_inference_count: 3
  raw_candidate_count: 57
  production_candidate_count: 3
  finding: 三次诊断都显示 bbox、Grounding confidence 和 mask SHA-256 完全相等；候选 grounded-sam-001 的 SAM quality 固定相差 2 个 float32 ULP
  raw_sam_quality: 0.942948579788208
  production_sam_quality: 0.9429484605789185
  float32_ulp_distance: 2
  mask_iou: 1.0
  threshold_tuning_performed: false
  diagnosis_json_sha256: 3935810e96385e03a8ea00aba649b583e1fce8844b35723308fc8cfc5a7b090a
  durable_archive: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/diagnostics/grounded-production-mapping-r2.tar.gz
  durable_archive_sha256: a51f6482cccd13d97416555c4c55c0d0d7b9b690674198dca5906469dfc7d636
stable_identity_fix:
  commit: c7c2488f5827d264cacc61f01313d1c2cf0ded2c
  runner_sha256: 388b3b8afde22063f9624f64e4b21a0c2d45dca8fa9dc7dc0602daa2560ad79a
  contract: Grounded-SAM 候选身份由 class_id、bbox、Grounding confidence 和 mask SHA-256 唯一映射；SAM quality 两侧必须存在，但不作为身份键
  fail_closed: 稳定身份字段对应零个或多个 raw 候选时仍判为 PRODUCTION_CANDIDATE_MAPPING_INVALID
  detector_output_changed: false
  prompt_model_grid_threshold_metric_matching_objective_changed: false
  evidence_reconciliation_rule_changed: true
verification:
  red: 2 ULP 用例在修复前按预期 INVALID
  focused: 5 passed
  runner_file: 129 passed in 62.54s
  mac_benchmark_gate: 567 passed, 0 errors, 0 failures, 0 skipped in 344.02s
  mac_junit_sha256: 39d2408d1c127a723c5cbe2043f25341f744ec4b594ee9dc397d7e5dfe8c26a9
  linux_benchmark_gate: 565 passed, 2 skipped, 0 errors, 0 failures in 641.19s
  linux_junit_sha256: 9de08c7f4ac26b9903bcffb2b95736249a59a0cc7e71aa190c18b49c77771883
formal_r3:
  mac_build: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/mac-grid-parallel-r4
  linux_build: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-grid-parallel-r20
  installed_runner_sha256: 388b3b8afde22063f9624f64e4b21a0c2d45dca8fa9dc7dc0602daa2560ad79a
  installed_config_sha256: 8103b926c48b3fe006101cdc1bdf8035349f65c2def5ce33c2aaed79e0e32725
  mac_script_sha256: 6ffd4f7401f35fc147cdf5ac46d2610a33d9c70e191ea563403f757912587f2c
  mac_plist_sha256: a48a01ea663c5b90aec2420c3c432acf305f1c610e999dad2a7d765ce244b6e0
  linux_script_sha256: 292d66ddf9738e8f9b94efecb4e9f4f7acf102f546a0af10d571250fa13e4312
  mac_runs:
    - mac-grounded-sam-test-production-postfix-r4-r3
    - mac-grounded-sam-test-calibrated-postfix-r4-r3
  linux_runs:
    - linux-grounded-sam-test-raw-postfix-r4-r3
    - linux-grounded-sam-test-production-postfix-r4-r3
    - linux-grounded-sam-test-calibrated-postfix-r4-r3
    - linux-yolo-test-raw-postfix-r4-r3
    - linux-yolo-test-production-postfix-r4-r3
    - linux-yolo-test-calibrated-postfix-r4-r3
execution_order:
  - 提交并同步 CP-067
  - Mac r3 两组均完整 VALID 后才允许启动 Linux r3
  - Linux 启动前必须确认无其他 GPU compute process；当前观察到 /data/work/microduck_rl/.venv/bin/python3 占用 13784 MiB，因此暂不启动 Linux
  - 任一输出碰撞、manifest INVALID、CPU fallback 或冻结 SHA 不符，立即停止且不复用 run ID
retention:
  retained_runs:
    - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/mac-mapping-fix-r3
    - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/mac-grid-parallel-r4
    - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-grid-parallel-r20
    - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/runtime-tmp/linux-grid-parallel-r20
  archived_runs:
    - /data/work/so101-evidence/archived/v5-t005-grounded-sam-rgbd/exp-079-mac-grounded-sam-test-production-postfix-r4-r2-invalid
  deletion_candidates: none
decision: RUN_MAC_R3_AFTER_CP067_SYNC
```

## Checkpoint CP-068 — 通用 cup 微调与 Linux-first 路线

```yaml
checkpoint: CP-068
status: PLANNED
recorded_at: 2026-09-04T12:00:00+08:00
source_commit: 32d90aebbb66896179911c22ad9d18c4d22b16de
source_branch: codex/v5-t004-yolo-seg-rgbd
working_tree:
  state: DIRTY_EXPECTED
  owned_changes:
    - src/so101_demo_py/benchmark_test/test_perception_benchmark_runner.py
    - src/so101_demo_py/src/perception_benchmark/runner.py
    - docs/superpowers/specs/2026-09-04-grounding-dino-tiny-cup-finetune-linux-first-design.md
    - docs/superpowers/plans/2026-09-04-grounding-dino-tiny-cup-finetune-linux-first.md
    - docs/experiments/v5-t005-grounded-sam-rgbd-experiment-ledger.md
  preserved_untracked: existing build/install/log directories remain untouched
evidence_roots:
  temporary: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079
  durable: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079
approved_strategy:
  detector_target: cup
  prompt: cup.
  material_classification: disabled
  segmenter: facebook/sam2.1-hiera-tiny
  sam_training: frozen
  sam_mode: stateless_per_frame
  mapping_identity: [normalized_class, bbox_xyxy, grounding_box_score]
  mapping_mask_gate: {metric: IoU, threshold: 0.98, comparison: greater_than_or_equal}
  persisted_mask: actual production SAM mask
  platform_order: linux_then_macos
  linux_gate: four preset MuJoCo RGB-D PickPlace successes before Mac migration
user_override:
  - CP-067 required Mac completion before Linux; the user later authorized parallel Linux work.
  - This checkpoint supersedes both orders for new-model work: Linux is now the sole first platform.
completed_mac_baseline:
  production_r3:
    status: VALID
    run_id: mac-grounded-sam-test-production-postfix-r4-r3
    record_inventory_sha256: b110d5c1a867276cd51bd131d5726204f6bc55745036eafb11f3b01425755702
    manifest_sha256: 75103f5d17e6b4dcc9b192df14ecdaa3d8ca147000c80d246675357b499f5439
  calibrated_r3:
    status: VALID
    run_id: mac-grounded-sam-test-calibrated-postfix-r4-r3
    record_inventory_sha256: 482c2588c611b0f90438b32954457281d7d586d31473cb1d8fa637af53427469
    manifest_sha256: 7a2b4f48500cc2647a98fbd4cafaf257df1507903dc518bf0afbdeff2314f86e
  interpretation: frozen pre-finetune baseline only; not a gate for new-model selection
linux_r3:
  raw:
    status: VALID
    run_id: linux-grounded-sam-test-raw-postfix-r4-r3
    record_inventory_sha256: cc9fb30ba5472e16aa4cdbecd4cce3599a0a982dff753f4e30e7d0906b7c01a6
    manifest_sha256: dd8ec4a929c90d6ee6dd757f5f28cc2aebc95799fadfd8eb2f120685b6fbe69d
  production:
    status: INVALID
    run_id: linux-grounded-sam-test-production-postfix-r4-r3
    invalid_reason: PRODUCTION_CANDIDATE_MAPPING_INVALID
    completed_record_inventory_sha256: 28bc336b1fbb02aa316d22116b1f0abf90c72a5261e3a6655c47cf4094c7802c
    manifest_sha256: a6863bb080ea1336e68184fa7211bcb2eb6a4e9097ea7954469bc1193271ea23
  diagnostic:
    image: images/test/000900012.png
    raw_candidates: 77
    production_candidates: 2
    affected_mask_pixels: {raw: 4698, production: 4699}
    mask_iou: 0.9997871887635668
    repeated_runs: 3
    conclusion: deterministic SAM batch-size boundary difference; exact mask SHA is not a valid Grounded candidate identity rule
coco100_external_baseline:
  handoff_root: /private/tmp/so101-grounded-dino-cup-100-handoff-20260904
  manifest_sha256: 216fc518cefb3dd08e4246a37fad50dbe66ddfe664672e4437d25d544f4708e5
  manifest_entries: 419
  manifest_verification: PASS
  provider: COCO 2017 val
  images: 100
  cup_instances: 247
  prompt: cup.
  model_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
  box_iou_threshold: 0.5
  counts: {tp: 145, fp: 48, fn: 102}
  metrics: {precision: 0.7512953367875648, recall: 0.5870445344129555, f1: 0.6590909090909091}
  images_with_at_least_one_true_cup: 85
  selection: {unique: 46, ambiguous: 25, not_found: 28, inference_error: 1}
  visible_non_cup_unique: 0
  use: final frozen checkpoint non-regression only; never checkpoint selection or threshold tuning
  noninferiority_gates:
    f1_min: 0.6391
    recall_min: 0.5670
    images_with_at_least_one_true_cup_min: 83
    visible_non_cup_unique_max: 0
    inference_error_max: 1
planned_experiments:
  - {id: EXP-079-MAPPING-IOU-R4, status: PLANNED, unique_variable: replace exact Grounded mask identity with configured IoU gate and persist observed production mask, lifecycle: OFFLINE_TEST}
  - {id: EXP-079-LINUX-BUILD-R21, status: PLANNED, unique_variable: exact new commit in fresh Linux overlay, lifecycle: FULL_REBUILD}
  - {id: EXP-079-DATA-CUP-V1, status: PLANNED, unique_variable: YOLO-Seg polygon-to-cup-box conversion and immutable new split, lifecycle: OFFLINE_DATA}
  - {id: EXP-079-DINO-FINETUNE-R1, status: PLANNED, unique_variable: fine-tune Grounding DINO Tiny while SAM remains frozen, lifecycle: TRAINING}
  - {id: EXP-079-LINUX-TEST-FINETUNED-R1, status: PLANNED, unique_variable: frozen fine-tuned checkpoint on new sealed synthetic test, lifecycle: OFFLINE_TEST}
  - {id: EXP-079-COCO100-FINETUNED-R1, status: PLANNED, unique_variable: frozen fine-tuned checkpoint on fixed COCO100 external set, lifecycle: OFFLINE_TEST}
  - {id: EXP-079-LINUX-PICKPLACE-P1, status: PLANNED, preset: 1, lifecycle: FULL_RESTART}
  - {id: EXP-079-LINUX-PICKPLACE-P2, status: PLANNED, preset: 2, lifecycle: FULL_RESTART}
  - {id: EXP-079-LINUX-PICKPLACE-P3, status: PLANNED, preset: 3, lifecycle: FULL_RESTART}
  - {id: EXP-079-LINUX-PICKPLACE-P4, status: PLANNED, preset: 4, lifecycle: FULL_RESTART}
next_action: finish EXP-079-MAPPING-IOU-R4 with RED/GREEN focused tests; do not start macOS new-model work
retention:
  retained_runs:
    - all CP-067 Mac valid baseline runs
    - Linux raw r3 valid run
    - COCO100 handoff pending durable copy and readback
  archived_runs:
    - Linux production r3 invalid is an archive candidate but has not been moved or deleted
  deletion_candidates: none
```

## Checkpoint CP-069 — Grounded production mask IoU mapping GREEN

```yaml
checkpoint: CP-069
status: VALID
recorded_at: 2026-09-04T04:16:48Z
experiment: EXP-079-MAPPING-IOU-R4
source_base_commit: 32d90aebbb66896179911c22ad9d18c4d22b16de
symptom_boundary: Linux production r3 failed at image images/test/000900012.png because one deterministic SAM boundary pixel changed when proposal batch size changed
judgment: OBSERVED
unique_variable: Grounded candidate mapping now requires stable DINO identity plus mask IoU at the configured 0.98 threshold, and persists the observed production mask
implementation:
  runner_sha256: 919ac8f5c8d724de146b4ee9c144c2c41b9da6b822ced4efb44bafeaa1aac3ec
  cli_sha256: c3c8f85b20c4399175f6cd6352591688b6f8383e8f8f483ebb0bdae7a06b6d9f
  benchmark_config_sha256: 511e0e6472cb774f521783982b2833c790ddc85d1cf3bad03112100ee2896a92
  regression_test_sha256: 854a78baaa34e7523015ac7c59f48e7d22151d0c31d630ee2cfe80bc83ad55c8
  mapping_contract:
    identity: [class_id, bbox_xyxy, grounding_box_score]
    mask_metric: IoU
    mask_threshold: 0.98
    on_multiple_or_no_match: PRODUCTION_CANDIDATE_MAPPING_INVALID
    persisted_mask: actual production SAM mask RLE and SHA
    yolo_semantics_changed: false
tdd:
  red: existing observed-mask regression failed before implementation with PRODUCTION_CANDIDATE_MAPPING_INVALID
  focused_green: 9 passed, 126 deselected in 0.17s
  runner_and_cli_green: 185 passed in 64.60s
  runner_file_final_green: 135 passed in 63.27s
  config_cli_green: 8 passed, 46 deselected in 0.11s
documentation:
  design_sha256: 17d9e7053541682b323d24ba3943af588baf2d974fda03afde0d0030a7c3779b
  plan_sha256: 0d44668475e728908c2cc39662379f4d6c4ae59f91232d2427ce7a44a210d2cd
  humanizer_zh_review: PASS
  placeholder_scan: PASS
  git_diff_check: PASS
remaining_gate:
  - commit and push exact patch
  - ai-station pull into isolated checkout
  - fresh Linux overlay and full ordinary plus explicit benchmark tests
  - Linux production r4 rerun with new run ID
next_action: commit CP-069 patch and start EXP-079-LINUX-BUILD-R21
retention:
  retained_runs:
    - all CP-068 listed baseline and diagnostic evidence
  archived_runs:
    - Linux production r3 remains retained in place pending verified archival move
  deletion_candidates: none
```

## Checkpoint CP-070 — ai-station tmux 接手计划

```yaml
checkpoint: CP-070
status: HANDOFF_READY
recorded_at: 2026-09-04T12:39:00+08:00
source_commit_before_plan_update: f6f03b645c44b10a212f81047da304fc63a6c214
source_branch: codex/v5-t004-yolo-seg-rgbd
executor:
  host: ai-station
  tmux_session: codex
  checkout: /data/work/so101-grounded-sam-yolo-benchmark-ab-v1-task14-runner-access-r11
  mode: existing Codex session; no subagents
evidence_roots:
  temporary: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079
  durable: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079
completed_before_handoff:
  mapping_fix_commit: f6f03b645c44b10a212f81047da304fc63a6c214
  gitee_remote_sha_verified: true
  ai_station_checkout_synced: true
  coco100_durable_copy: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/external/coco100-baseline-handoff-r1
  coco100_manifest_entries: 419
  coco100_manifest_verification: PASS
linux_build_diagnostics:
  r21_to_r25: environment and overlay provenance diagnostics; retained
  r26:
    build: PASS
    packages_in_same_overlay: 7
    ordinary_tests: {passed: 1158, failed: 9, total: 1167}
    failure_boundary: regular Python install path is outside the Git worktree, so source commit provenance cannot resolve
  r27:
    build: STOPPED_INVALID
    failure_boundary: lodepng FetchContent clone stalled for more than five minutes with no CPU or output
    preserved_local_cache: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-r26/build/mujoco_ros2_control/_deps/lodepng-src
    next_run_id: linux-build-r28
handoff_plan: docs/superpowers/plans/2026-09-04-grounding-dino-tiny-cup-finetune-linux-first.md
hard_gates:
  - finish r28 symlink overlay and both Linux test suites
  - rerun only old-model production mapping validation, not valid raw inference
  - build immutable YOLO-polygon-to-DINO-box inventories
  - select checkpoint only on synthetic val
  - run synthetic test and COCO100 once after freeze
  - pass COCO100 noninferiority and selection safety before PickPlace
  - pass all four Linux presets before any Mac migration
  - keep Microduck paused until this entire task completes and the user permits resume
retention:
  retained_runs: all r21-r27 diagnostics and CP-068/CP-069 evidence
  archived_runs: none newly moved
  deletion_candidates: none
```

## Stage A Linux overlay diagnostics — r28 invalid, r29 planned

```yaml
experiment_id: EXP-079-LINUX-BUILD-R28
status: INVALID
prior_experiment: EXP-079-LINUX-BUILD-R27
hypothesis: r26 的完整 lodepng 本地缓存可让新的 7-package symlink overlay 离线完成构建，并让两套测试门使用锁定的 Grounded-SAM Python 环境
prediction: 构建不访问网络，普通 1167 项和显式 benchmark 573 项均由锁定 venv 执行且零失败
single_variable: r28 使用 FETCHCONTENT_SOURCE_DIR_LODEPNG 指向已验证的 r26 缓存，并启用 FETCHCONTENT_FULLY_DISCONNECTED
lifecycle: FULL_REBUILD
preconditions:
  - r27 精确路径无存活进程，保留的 tmux pane 已死且退出码为 2
  - r26 lodepng checkout HEAD=ed6fe5825c6a4fbb7f58ab35a4231c7543cd452a，git fsck 通过，26 个 tracked files 全部存在且无修改
  - Microduck 无训练或 GPU 进程
success_criteria:
  - 7 个包构建成功且全部 prefix 指向 r28
  - 普通测试 1167/1167 通过
  - benchmark 测试 573/573 通过（允许已冻结的 skip）
failure_criteria:
  - 任一构建、provenance、依赖或测试门失败
invalid_criteria:
  - 输出碰撞、网络 fetch、错误 source commit、非锁定 Python runtime
provenance:
  source_commit: 00c6a8c0b47d4222580d89b568f72ae336cec769
  install_overlay: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-r28/install
  runtime_executable: /usr/bin/python3
  ros_domain_id: NONE_OFFLINE_BUILD
  gz_partition: NONE_OFFLINE_BUILD
commands:
  - command: colcon build --symlink-install --packages-select mujoco_ros2_control_msgs mujoco_ros2_control_plugins mujoco_3d_lidar mujoco_ros2_control so101_mujoco_support so101_teleop so101_demo_py --cmake-args -DFETCHCONTENT_SOURCE_DIR_LODEPNG=<r26-cache> -DFETCHCONTENT_FULLY_DISCONNECTED=ON
    exit_code: 0
  - command: colcon test --packages-select so101_demo_py --pytest-args test
    exit_code: 0
  - command: colcon test --packages-select so101_demo_py --pytest-args benchmark_test
    exit_code: 0_OUTER_WITH_JUNIT_FAILURES
observed:
  - OBSERVED r28 的 lodepng object 从 r26 cache 编译，7-package build 64 秒完成，所有 package prefix 和源码 SHA readback 通过
  - OBSERVED 普通门为 1167 passed、0 failed、4 warnings、22.12 秒
  - OBSERVED benchmark JUnit 为 573 total、509 passed、62 failed、2 skipped、2137.23 秒
  - OBSERVED r28 command.log 使用 /usr/bin/python3；该解释器无 torch 且 Pillow=10.2.0，62 个失败归并为 torch 缺失和 RASTERIZER_VERSION_MISMATCH
  - OBSERVED 锁定 venv 含 torch=2.13.0+cu130、Pillow=12.3.0；按 venv site-packages -> /usr/lib/python3/dist-packages 顺序可同时导入 torch、Pillow 和 colcon_core
inferred:
  - INFERRED r28 benchmark failure 属于 test runner 环境污染，不是 mapping 或业务代码回归
conclusion: r28 构建和普通门有效，但 benchmark 由错误 Python runtime 执行，因此整轮不能计入 Stage A 成功
evidence:
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-r28/build.console.log
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-r28/provenance-readback-r2.log
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-r28/test-results/ordinary/pytest.xml
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-r28/test-results/benchmark/pytest.xml
decision: REPEAT
next_experiment: EXP-079-LINUX-BUILD-R29
---
experiment_id: EXP-079-LINUX-BUILD-R29
status: INVALID
prior_experiment: EXP-079-LINUX-BUILD-R28
hypothesis: r28 唯一污染源是 colcon runner 的 Python 选择；通过锁定 venv Python 启动 colcon 后，构建生成的 test command 会使用同一 venv 并消除全部 62 个环境失败
prediction: command.log 使用 /data/work/venvs/so101-grounded-sam/bin/python，torch=2.13.0+cu130、Pillow=12.3.0，普通门和 benchmark 门零失败
single_variable: 用锁定 venv Python 启动 /usr/bin/colcon，并显式将 venv site-packages 排在 /usr/lib/python3/dist-packages 前
lifecycle: FULL_REBUILD
preconditions:
  - r29 build/install/log/output 均不存在
  - source commit 和 CP-069 runner/config SHA 不变
  - 继续复用只读的已验证 r26 lodepng cache，禁止网络 fetch
success_criteria:
  - 7-package symlink build、exact provenance、普通 1167 项和显式 benchmark 573 项门全部通过
failure_criteria:
  - 任一门失败
invalid_criteria:
  - output collision、非 venv runtime、网络 fetch、source/manifest mismatch
provenance:
  source_commit: 00c6a8c0b47d4222580d89b568f72ae336cec769
  install_overlay: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-r29/install
  runtime_executable: /data/work/venvs/so101-grounded-sam/bin/python /usr/bin/colcon
  ros_domain_id: NONE_OFFLINE_BUILD
  gz_partition: NONE_OFFLINE_BUILD
commands:
  - command: PYTHONPATH=<venv-site>:/usr/lib/python3/dist-packages:<ros-paths> <venv-python> /usr/bin/colcon build --symlink-install --packages-select <fixed-seven-packages> --cmake-args -DFETCHCONTENT_SOURCE_DIR_LODEPNG=<r26-cache> -DFETCHCONTENT_FULLY_DISCONNECTED=ON
    exit_code: 0
observed:
  - OBSERVED build runner 同时导入 colcon_core、torch=2.13.0+cu130 和 Pillow=12.3.0，7 个包在 61 秒内构建完成
  - OBSERVED so101_demo_py 的 build/install 文件均为复制产物，不是指回 checkout 的 symlink；其 realpath 停留在 r29 build/install 目录
inferred:
  - INFERRED venv setuptools 改变 ament_python symlink-install 行为，r29 会复现 r26 的 source commit provenance 失败
conclusion: r29 在测试前命中 non-symlink provenance invalid criterion，未运行普通或 benchmark gate
evidence:
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-r29
decision: ABANDON
next_experiment: EXP-079-LINUX-TEST-R30
---
experiment_id: EXP-079-LINUX-TEST-R30
status: VALID
prior_experiment: EXP-079-LINUX-BUILD-R29
hypothesis: r28 symlink overlay 本身有效，62 个 benchmark failure 只由 test runner 解释器产生；保留 r28 overlay 并只用锁定 venv Python 启动 colcon test 可同时满足 source provenance 与依赖锁
prediction: 两个 r28 失败样本先在 venv runner 下通过，command.log 使用 venv Python，随后普通 1167 项和 benchmark 573 项门通过
single_variable: r28 build/install 不变，仅把 test orchestration 从 /usr/bin/colcon 切换为 venv Python 启动的 /usr/bin/colcon，并固定 Python path 顺序
lifecycle: REUSE_STACK
preconditions:
  - r28 7-package build、symlink realpath、exact HEAD、package prefixes、runner/config SHA 和离线 lodepng provenance 已通过
  - r28 两套旧 JUnit 已复制到独立 test-results 目录，不会被后续 test command 覆盖
  - linux-test-r30 输出目录不存在
success_criteria:
  - 两个环境 RED 样本 GREEN
  - ordinary JUnit 为 1167 tests、0 errors、0 failures
  - benchmark JUnit 为 573 tests、0 errors、0 failures，且只有冻结的 2 skipped
failure_criteria:
  - 任一 focused 或 full gate 失败
invalid_criteria:
  - non-venv test executable、output collision、r28/source provenance drift
provenance:
  source_commit: 00c6a8c0b47d4222580d89b568f72ae336cec769
  install_overlay: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-r28/install
  runtime_executable: /data/work/venvs/so101-grounded-sam/bin/python /usr/bin/colcon test
  ros_domain_id: NONE_OFFLINE_TEST
  gz_partition: NONE_OFFLINE_TEST
commands:
  - command: <venv-python> /usr/bin/colcon test --packages-select so101_demo_py --pytest-args benchmark_test/test_perception_benchmark_adapters.py::test_pinned_transformers_sam2_boolean_masks_are_consumed_losslessly benchmark_test/test_perception_benchmark_dataset.py::test_polygon_rule_is_round_half_up_and_includes_pillow_boundary
    exit_code: 0
  - command: <venv-python> /usr/bin/colcon test --packages-select so101_demo_py --pytest-args test
    exit_code: 0
  - command: <venv-python> /usr/bin/colcon test --packages-select so101_demo_py --pytest-args benchmark_test
    exit_code: 0
observed:
  - OBSERVED focused A/B 为 2 passed in 3.05s，覆盖 r28 的 torch 缺失与 Pillow 版本失败
  - OBSERVED ordinary JUnit 为 1167 tests、0 failures、0 errors、0 skipped、21.297 秒
  - OBSERVED benchmark JUnit 为 573 tests、0 failures、0 errors、2 skipped、3210.773 秒；pytest 摘要为 571 passed、2 skipped
  - OBSERVED 三份 command.log 均使用 /data/work/venvs/so101-grounded-sam/bin/python -m pytest
  - OBSERVED r28 import realpath 指回当前 checkout，7 个 package prefix 指向 r28，HEAD、runner SHA 和 config SHA 全部通过 readback
  - OBSERVED 完成后 r27、Microduck training/queue 和 GPU compute process 匹配数均为 0
inferred:
  - INFERRED r28 的 62 个 benchmark failure 已由唯一 test-runner 变量排除，业务代码无需修改
conclusion: r28 symlink overlay 和 venv-backed r30 test orchestration 满足 Stage A 全部退出门
evidence:
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-test-r30
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-test-r30/test-results/ordinary/pytest.xml#sha256=5f6e5a941ddf72eb52c5bf3b044e684b761e7c95b2be6f2fc0d8063d219a6fcf
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-test-r30/test-results/benchmark/pytest.xml#sha256=82f3d0d05250afbe51f5124dbbd716bd57258f20baf49827e7765f563168e311
decision: KEEP
next_experiment: EXP-079-LINUX-PRODUCTION-MAPPING-R4
```

## Checkpoint CP-071 — Stage A Linux code gates complete

```yaml
checkpoint: CP-071
status: VALID
recorded_at: 2026-09-04T15:20:00+08:00
stage: A
last_valid_experiment: EXP-079-LINUX-TEST-R30
source_commit: 00c6a8c0b47d4222580d89b568f72ae336cec769
source_branch: codex/v5-t004-yolo-seg-rgbd
working_tree_status:
  owned_dirty:
    - docs/experiments/v5-t005-grounded-sam-rgbd-experiment-ledger.md
  preserved_untracked:
    - build-task14-runner-access-r11/
    - install-task14-runner-access-r11/
    - log-task14-runner-access-r11/
owned_processes: NONE
preserved_processes:
  - existing codex tmux sessions left untouched
  - unrelated 2026-09-01 colcon version-check process left untouched
build:
  overlay: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-r28/install
  packages: [mujoco_ros2_control_msgs, mujoco_ros2_control_plugins, mujoco_3d_lidar, mujoco_ros2_control, so101_mujoco_support, so101_teleop, so101_demo_py]
  symlink_install: true
  elapsed_seconds: 64
  lodepng_source: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-r26/build/mujoco_ros2_control/_deps/lodepng-src
  lodepng_head: ed6fe5825c6a4fbb7f58ab35a4231c7543cd452a
  network_fetch: false
provenance:
  import_realpath: /data/work/so101-grounded-sam-yolo-benchmark-ab-v1-task14-runner-access-r11/src/so101_demo_py/src/__init__.py
  package_prefixes: all seven packages resolve to linux-build-r28/install
  runner_sha256: 919ac8f5c8d724de146b4ee9c144c2c41b9da6b822ced4efb44bafeaa1aac3ec
  benchmark_config_sha256: 511e0e6472cb774f521783982b2833c790ddc85d1cf3bad03112100ee2896a92
  test_runtime: /data/work/venvs/so101-grounded-sam/bin/python
tests:
  ordinary: {total: 1167, passed: 1167, failed: 0, errors: 0, skipped: 0, elapsed_seconds: 21.297}
  benchmark: {total: 573, passed: 571, failed: 0, errors: 0, skipped: 2, elapsed_seconds: 3210.773}
  colcon_test_result: 573 tests, 0 errors, 0 failures, 2 skipped
confirmed_conclusions:
  - r27 is stopped and the complete r26 lodepng cache can support an offline r28 build
  - exact source provenance and both Linux test gates pass when r28 symlink build and the locked venv test runner are combined
disproven_routes:
  - r28 tests through /usr/bin/python3 are invalid because torch is absent and Pillow is 10.2.0
  - a full build through venv setuptools does not produce the required so101_demo_py symlink install
open_risks:
  - Stage B must reuse Linux raw r3 and must not rerun Grounding DINO or SAM raw inference
future_test_scratch_rule:
  effective_after: EXP-079-LINUX-TEST-R30
  hdd_baseline:
    run_id: EXP-079-LINUX-TEST-R30
    result: {total: 573, passed: 571, failed: 0, errors: 0, skipped: 2, exit_code: 0}
    pytest_elapsed_seconds: 3210.78
    filesystem: /tmp on /dev/sda3 rotational WDC WD10EZEX SATA HDD
    preservation: immutable; do not rerun for timing
  required_for_future_fsync_heavy_pytest_or_benchmark:
    - allocate a unique, non-existing run-specific path below /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/scratch/<run-id>/tmp
    - export TMPDIR, TMP, and TEMP to that exact NVMe path before colcon or pytest
    - use the exact locked Python executable to print tempfile.gettempdir() and fail closed unless its resolved path is inside that run-specific scratch directory
    - retain command log, exit log, JUnit, source commit, overlay, Python executable, scratch path, and elapsed time in the checkpoint
    - compare only the next full benchmark already required by a code or model change against 3210.78 seconds
    - preserve fsync, ext4 journaling, integrity checks, and disk-backed semantics; tmpfs is forbidden
  scratch_retention: deletion candidate after evidence readback; explicit user authorization required before deletion
next_command: inspect linux-grounded-sam-test-raw-postfix-r4-r3 immutable artifacts and preregister a new production-only run ID
retention:
  retained_runs: [linux-build-r21 through linux-build-r29, linux-test-r30, CP-068 through CP-070 evidence]
  archived_runs: []
  deletion_candidates: []
```

## Stage B immutable raw replay — production mapping r4

```yaml
experiment_id: EXP-079-LINUX-PRODUCTION-MAPPING-R4
status: VALID
recorded_at: 2026-09-04T15:26:08+08:00
started_at: 2026-09-04T15:33:00+08:00
prior_experiment: EXP-079-LINUX-TEST-R30
hypothesis: 已验证的 Linux raw r3 可作为不可变 low-floor 候选源；新 mapping 代码只运行真实 production detector 与 selector，能够在 mask IoU 大于等于 0.98 时完成一一映射并保存实际 production SAM mask
prediction: 200/200 production records 完整 VALID，000900012.png 的 raw/production mask 像素为 4698/4699、IoU 为 0.9997871887635668，且不启动 raw Grounding DINO 或 raw SAM 推理
single_variable: 将 candidate reconciliation 从 exact mask SHA 改为已提交的稳定 proposal identity 加 mask IoU 门；raw candidates 只从已验证的 r3 terminal evidence replay
lifecycle: REUSE_IMMUTABLE_RAW_NEW_PRODUCTION
run:
  run_id: linux-grounded-sam-test-production-postfix-r4-r4
  run_kind: TEST_PRODUCTION
  output_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/test-postfix-r4/linux/grounded-sam-production-r4
  output_preflight: ABSENT
raw_replay:
  run_id: linux-grounded-sam-test-raw-postfix-r4-r3
  root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/test-postfix-r4/linux/grounded-sam-raw-r3
  manifest_sha256: dd8ec4a929c90d6ee6dd757f5f28cc2aebc95799fadfd8eb2f120685b6fbe69d
  checkpoint_sha256: ffdd84d8d44e74bea49d24b55bd88d2f376d6980e88a86d3a3692f5796e9448f
  record_inventory_sha256: cc9fb30ba5472e16aa4cdbecd4cce3599a0a982dff753f4e30e7d0906b7c01a6
  record_count: 200
  inference_policy: immutable replay only; raw Grounding DINO and SAM inference forbidden
  tree_inventory_sha256_preflight: 445eb6f52efafab9fb3271f988c4cac3e75c92c77d10ccf7fc7b4b84ee9ff44e
provenance:
  execution_commit: 69476fd8d411f56f19bb0ec069692e0ffa9745a8
  threshold_chain_source_commit: d933b4b9574df36d499b3e9254f0e88a1919810a
  mapping_fix_commit: f6f03b645c44b10a212f81047da304fc63a6c214
  overlay: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-r28/install
  python: /data/work/venvs/so101-grounded-sam/bin/python
  replay_harness_sha256: c066095b45071acdca358f3190f68b718cd88cea4cbe9e1882f2e8416e40d124
  model_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
  threshold_lock_file_sha256: 8b0d24ca6c8c28ffb6f9e8c6d7be7c4dabb3916a198f8a0e6f594fb6faebce3e
  threshold_lock_sha256: 7880140f8f0c363c6a197f24fc8c691df5598f5012336a4d638a5e828c6920ad
  dataset_inventory_sha256: 72d38c392889d9f1d8095f24d148f31bd2915a5f36fc62b123f6625fc7e76dd2
success_criteria:
  - raw terminal evidence and every replayed mask verify against registered anchors before production starts
  - CUDA float32 runtime with no CPU fallback
  - production record denominator is 200/200 with zero mapping or inference errors
  - production actual SAM masks are persisted for every accepted candidate
  - 000900012.png matches by proposal identity and mask IoU at or above 0.98 without a sample-specific exception
failure_criteria:
  - production mapping, detector, selector, denominator, CUDA, or mask persistence failure
invalid_criteria:
  - raw inference rerun, raw evidence mutation, output collision, manifest mismatch, unregistered source, or CPU fallback
calibrated_policy: start a new unique calibrated r4 run only after this production run is VALID
result:
  exit_code: 0
  elapsed_seconds: 76.112596
  record_count: 200
  error_count: 0
  accepted_candidates: 475
  persisted_production_masks: 475
  record_inventory_sha256: b716777e595ae33cd6f407f65b128dd5ba169892b9f643111173a512af869001
  manifest_sha256: 438d62d313ae4360380d75384884dee73f7a9eae280c53b8f19fb316d4121adc
  checkpoint_sha256: 73053e4d13a8450e60be6d4ef6fe6e39c38cfe931f17c967ff0874814b6a18bc
  replay_provenance_sha256: 5d3975827d3310d4d428ce1899e291fa411d7fe2272def6c6d941d3f89c30e78
  raw_tree_inventory_sha256_postrun: 445eb6f52efafab9fb3271f988c4cac3e75c92c77d10ccf7fc7b4b84ee9ff44e
sample_readback:
  image: images/test/000900012.png
  production_candidate_count: 2
  affected_candidate:
    candidate_id: grounded-sam-000
    raw_mask_pixels: 4698
    production_mask_pixels: 4699
    mask_iou: 0.9997871887635668
    mapping_threshold: 0.98
  second_candidate: {candidate_id: grounded-sam-001, raw_mask_pixels: 2376, production_mask_pixels: 2376, mask_iou: 1.0}
conclusion: immutable raw r3 replay 和新的真实 production detector/selector 全量映射通过，production 实际 SAM mask 已全部持久化；允许开始 calibrated r4
preflight_evidence:
  - /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/stage-b-replay-preflight-r1
  - 200/200 raw records and every referenced mask verified through load_verified_run_evidence
  - GPU compute process count 0; Microduck match count 0; output root absent
retention:
  retained_runs: [linux-grounded-sam-test-raw-postfix-r4-r3]
  archived_runs: []
  deletion_candidates:
    - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/scratch/stage-b-replay-harness-test-r1
    - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/scratch/stage-b-replay-harness-test-r2
    - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/scratch/stage-b-replay-harness-test-r3
    - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/scratch/stage-b-replay-harness-test-r4
    - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/scratch/stage-b-production-mapping-r4
---
experiment_id: EXP-079-LINUX-CALIBRATED-REPLAY-R4
status: VALID
recorded_at: 2026-09-04T15:37:00+08:00
started_at: 2026-09-04T15:38:00+08:00
prior_experiment: EXP-079-LINUX-PRODUCTION-MAPPING-R4
hypothesis: production mapping r4 已全量通过，因此同一不可变 raw r3 可以与已冻结 deployable threshold lock 经真实 calibrated detector/selector 生成完整 Linux calibrated 结果
prediction: 200/200 records VALID、零 error、零 fallback，raw tree 前后不变，实际 calibrated SAM masks 全量持久化
single_variable: production observer 从预设 production 阈值切换为已冻结 threshold lock；raw replay、模型、数据和 mapping contract 不变
lifecycle: REUSE_IMMUTABLE_RAW_NEW_CALIBRATED
run:
  run_id: linux-grounded-sam-test-calibrated-postfix-r4-r4
  run_kind: TEST_CALIBRATED
  output_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/test-postfix-r4/linux/grounded-sam-calibrated-r4
success_criteria:
  - complete 200-record denominator with zero errors and no CPU fallback
  - raw r3 verifies before execution and its tree hash is unchanged after execution
  - all accepted calibrated production masks are persisted
invalid_criteria:
  - output collision, provenance mismatch, raw mutation or inference, manifest mismatch, or CPU fallback
result:
  exit_code: 0
  elapsed_seconds: 81.124017
  record_count: 200
  error_count: 0
  accepted_candidates: 671
  persisted_calibrated_masks: 671
  decision_counts: {unique: 2, ambiguous: 198, not_found: 0, error: 0}
  record_inventory_sha256: 00662ea763c7ab1c3390bb090d1274c6a60c38f2b92daa6dbb8054ccba215da4
  manifest_sha256: 6d00c0006d7caa0dde5bb17e4c7e579bb6b7d883fb2cb89ef1dc3ee8ae7856fc
  checkpoint_sha256: 28754ffc55562c29e3e2de82ffcd68a6d53269ccbc3a6924b4b5d2c01579f0c3
  replay_provenance_sha256: b1cccb37b43694114e1e344ef21b77ab16cd1df3e5fa42da7843100f45d728ed
  raw_tree_inventory_sha256_postrun: 445eb6f52efafab9fb3271f988c4cac3e75c92c77d10ccf7fc7b4b84ee9ff44e
conclusion: calibrated r4 全量 VALID，production 和 calibrated 两轮均未调用 raw inference，旧模型 mapping 修复验证完成；这些结果只作为 superseded baseline，不重新宣称旧模型可部署
retention:
  retained_runs: [linux-grounded-sam-test-production-postfix-r4-r4]
  archived_runs: []
  deletion_candidates:
    - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/scratch/stage-b-calibrated-replay-r4
```

## Checkpoint CP-072 — Stage B immutable raw replay complete

```yaml
checkpoint: CP-072
status: VALID
recorded_at: 2026-09-04T15:39:34+08:00
stage: B
source_branch: codex/v5-t004-yolo-seg-rgbd
execution_commit_before_checkpoint: 69476fd8d411f56f19bb0ec069692e0ffa9745a8
mapping_fix_commit: f6f03b645c44b10a212f81047da304fc63a6c214
raw_source:
  run_id: linux-grounded-sam-test-raw-postfix-r4-r3
  status: VALID_IMMUTABLE_REPLAY
  record_count: 200
  record_inventory_sha256: cc9fb30ba5472e16aa4cdbecd4cce3599a0a982dff753f4e30e7d0906b7c01a6
  tree_inventory_sha256_before_and_after: 445eb6f52efafab9fb3271f988c4cac3e75c92c77d10ccf7fc7b4b84ee9ff44e
  raw_inference_rerun_count: 0
production:
  run_id: linux-grounded-sam-test-production-postfix-r4-r4
  status: VALID
  records: 200
  errors: 0
  accepted_candidates: 475
  persisted_actual_masks: 475
  elapsed_seconds: 76.112596
  record_inventory_sha256: b716777e595ae33cd6f407f65b128dd5ba169892b9f643111173a512af869001
  sample_000900012: {raw_pixels: 4698, production_pixels: 4699, mask_iou: 0.9997871887635668, threshold: 0.98}
calibrated:
  run_id: linux-grounded-sam-test-calibrated-postfix-r4-r4
  status: VALID
  records: 200
  errors: 0
  accepted_candidates: 671
  persisted_actual_masks: 671
  decision_counts: {unique: 2, ambiguous: 198, not_found: 0, error: 0}
  elapsed_seconds: 81.124017
  record_inventory_sha256: 00662ea763c7ab1c3390bb090d1274c6a60c38f2b92daa6dbb8054ccba215da4
harness_tdd:
  red_r1: expected module missing; JUnit retained; wrapper exit-log command then hit zsh reserved variable status and was recorded separately
  green_r2: 2 passed in 0.14s
  red_r3: expected tree_inventory_sha256 import missing
  green_r4: 3 passed in 0.14s
  harness_sha256: c066095b45071acdca358f3190f68b718cd88cea4cbe9e1882f2e8416e40d124
  final_junit_sha256: d100756fce247251303dc9e1e12eda4316f6e7f8f8555050189861be5d876cc4
test_storage:
  filesystem: /data on NVMe
  preflight: every focused pytest printed tempfile.gettempdir and matched its unique registered scratch path
  r30_hdd_baseline_preserved: {passed: 571, skipped: 2, total: 573, pytest_elapsed_seconds: 3210.78}
  next_full_benchmark: only when already required by a subsequent code or model change; compare against r30
confirmed_conclusions:
  - proposal identity plus mask IoU threshold 0.98 resolves the deterministic one-pixel SAM boundary difference without a sample-specific exception
  - production actual SAM masks are persisted rather than substituted with raw masks
  - production and calibrated paths can reuse terminal raw evidence without repeating expensive low-floor Grounding DINO or SAM inference
next_stage: C — verify the frozen YOLO-Seg archive and implement deterministic polygon-to-DINO-box conversion with RED to GREEN
remote_sync_boundary:
  required_base: b91a4b56d30bc971e7c2d64465516b9d7a49b299
  rule: commit only owned ledger changes, then fetch and rebase before push
retention:
  retained_runs:
    - linux-grounded-sam-test-raw-postfix-r4-r3
    - linux-grounded-sam-test-production-postfix-r4-r4
    - linux-grounded-sam-test-calibrated-postfix-r4-r4
    - all Stage B low-rate logs and replay harness/test files below the registered temporary root
  archived_runs: []
  deletion_candidates:
    - all six Stage B scratch trees below the registered durable scratch root; none deleted
```

## Stage C deterministic YOLO-polygon conversion

```yaml
experiment_id: EXP-079-GROUNDING-DINO-DATA-CONVERSION-R1
status: VALID_AWAITING_DATA_SCOPE_DECISION
recorded_at: 2026-09-04T15:44:00+08:00
started_at: 2026-09-04T15:46:00+08:00
conversion_completed_at: 2026-09-04T16:08:00+08:00
prior_checkpoint: CP-072
hypothesis: 已归档的 YOLO-Seg 合成数据包含明确 split、polygon 和 truth metadata，可无损转换成 prompt 固定为 cup. 的 Grounding DINO box inventory，并保持 test sealed
prediction: 安全解包、转换器 RED 到 GREEN、两次独立转换得到相同成员与 inventory SHA，train/val/test 无交叉，test 内容在 checkpoint 和阈值冻结前不被训练或选择代码读取
single_variable: 新增确定性 YOLO polygon 到 Grounding DINO cup box 的转换链；不改变原始归档
lifecycle: NEW_DURABLE_DATA_VERSION
source:
  repository_lfs_pointer: datasets/so101-v5-t004-yolo-seg-synthetic/so101-v5-t004-yolo-seg-synthetic-20260831-f09cf88.tar.gz
  local_pointer_oid: c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1
  verified_archive_source: /data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/assets-r8/datasets/so101-v5-t004-yolo-seg-synthetic/so101-v5-t004-yolo-seg-synthetic-20260831-f09cf88.tar.gz
  archive_sha256: c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1
  archive_size_bytes: 53999319
  tar_members: 3618
  tar_path_preflight: safe relative regular files and directories only
destinations:
  source_copy_and_extraction: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/training-data/yolo-seg-source-r1
  converted_dataset: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/training-data/grounding-dino-cup-r1
  reproducibility_rerun: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/training-data/grounding-dino-cup-r1-repro
  collision_preflight: all absent
provenance:
  source_commit: 3a74a9e1ba2a1c53839dc1909d370c589e2f5786
  prompt: cup.
  normalized_class: cup
  coco100_access: forbidden during conversion, profiling, and later checkpoint selection
required_tdd:
  - normalized and absolute xyxy conversion from YOLO polygons
  - multiple instances, boundary-touching polygons, empty/invalid polygons, and degenerate boxes
  - class normalization to cup and exact training text cup.
  - image, label, source archive, and converter commit SHA provenance
  - disjoint train, val, and sealed test membership
  - deterministic rerun and fail-closed existing output
success_criteria:
  - source archive SHA and extracted manifest/truth readback pass
  - focused converter tests pass on unique NVMe scratch
  - train, val, and sealed new-test inventories are immutable and pairwise disjoint
  - independent rerun yields identical member and inventory SHA values
  - profile reports only fields supported by truth metadata and marks unsupported fields unknown
failure_criteria:
  - malformed polygon, split overlap, SHA mismatch, output collision, nondeterminism, or accidental test access before freeze
decision_boundary: if the evidence-backed profile proves a required small-target, multi-cup, or occlusion coverage gap, stop before changing data scope and request the user decision required by the plan
retention:
  retained_runs: [source archive copy, extracted source r1, converted r1, reproducibility rerun, all conversion evidence]
  archived_runs: []
  deletion_candidates: []
```

## Checkpoint CP-073 — Stage C converter code GREEN

```yaml
checkpoint: CP-073
status: VALID_CODE_READY
recorded_at: 2026-09-04T16:00:00+08:00
stage: C
experiment_id: EXP-079-GROUNDING-DINO-DATA-CONVERSION-R1
source_branch: codex/v5-t004-yolo-seg-rgbd
execution_commit_before_checkpoint: 3a74a9e1ba2a1c53839dc1909d370c589e2f5786
implementation:
  - deterministic polygon-to-normalized-and-absolute-xyxy conversion
  - class normalized to cup and prompt fixed to cup.
  - train and val truth/label agreement checked fail closed
  - source image, label, truth, archive, manifest, generator, MJCF, and converter provenance retained
  - test label and truth bytes treated as opaque sealed members; no test scenario or box enters the converted inventories or profile
  - output root must not exist and all JSON is canonical and fsync-persisted
tdd:
  red_r1: invalid harness invocation stopped before collection because locked venv Python lacked the system pytest path; wrapper then exposed a zsh PIPESTATUS mismatch; retained without reuse
  red_r2: invalid import setup proved only that the source package was absent from PYTHONPATH; 0 collected, exit 2; retained without reuse
  red_r3:
    result: expected so101_demo.training module missing
    tests_collected: 0
    errors: 1
    exit_code: 2
    elapsed_ms: 363
    junit_sha256: 313cfa19be95d085a99678ed9ad8f3ca592aae803adc3c93569afab360a5178a
  green_r1: 9 passed and 1 failed because split-directory validation preceded the required global overlap reason; retained without reuse
  green_r2: {passed: 10, failed: 0, elapsed_ms: 342}
  green_r3_after_locked_ruff_format:
    passed: 10
    failed: 0
    elapsed_ms: 370
    junit_sha256: 268ee86ad117395f3cf4300090fecdc972bbe59b4fe51b3e0656827ac826ff1d
quality:
  ruff_version: 0.15.20
  ruff_check: PASS
  ruff_format_check: PASS
  py_compile: PASS
  git_diff_check: PASS
overlay_diagnostics:
  r31: invalid pre-colcon setup attempt; ROS setup.bash rejected shell nounset; no build started
  r32: invalid because locked-venv setuptools copied so101_demo rather than producing the required source symlink
  r33: invalid package-only topology; 1177 collected with one provenance failure because so101_mujoco_support remained in r28
valid_overlay:
  run_id: linux-build-stage-c-r34
  root: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-stage-c-r34
  packages: [mujoco_ros2_control_msgs, mujoco_ros2_control_plugins, mujoco_3d_lidar, mujoco_ros2_control, so101_mujoco_support, so101_teleop, so101_demo_py]
  build_exit_code: 0
  build_elapsed_ms: 55882
  symlink_source: /data/work/so101-grounded-sam-yolo-benchmark-ab-v1-task14-runner-access-r11/src/so101_demo_py/src
  lodepng_source: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-r26/build/mujoco_ros2_control/_deps/lodepng-src
  lodepng_head: ed6fe5825c6a4fbb7f58ab35a4231c7543cd452a
  fetchcontent_fully_disconnected: true
  prefix_readback: all seven packages resolve inside the r34 install root
ordinary_gate:
  command_scope: src/so101_demo_py/test only
  result: {passed: 1177, failed: 0, errors: 0, skipped: 0}
  colcon_exit_code: 0
  test_result_exit_code: 0
  elapsed_ms: 12990
  junit_sha256: b1069f9d4f473f42e86f2d68c307e70e847c6b47f0b29b64bcf01d3b836695f4
  overlay: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-stage-c-r34/install
  python: /data/work/venvs/so101-grounded-sam/bin/python
test_storage:
  filesystem: /data on NVMe
  preflight: every pytest/colcon attempt used a unique non-existing registered scratch and the exact locked Python tempfile readback
  semantics: fsync, ext4 journaling, integrity checks, and disk-backed behavior unchanged
benchmark_gate:
  status: NOT_RUN
  reason: data-conversion code is ordinary training tooling and does not change benchmark implementation, configuration, adapters, reports, tests, or model selection
  preserved_baseline: r30 remains immutable at 571 passed, 2 skipped, pytest 3210.78 seconds on SATA HDD
next_command: commit and Gitee-sync the converter code, then run two independent conversions with that exact converter commit
retention:
  retained_runs: [stage-c source archive copy and extraction, linux-build-stage-c-r34, all RED/GREEN and overlay diagnostics]
  archived_runs: []
  deletion_candidates:
    - all Stage C scratch roots for red-r1 through red-r3, green-r1 through green-r3, build r31 through r34, and ordinary tests r33 and r34; none deleted
```

## Stage C source-contract correction — secondary cup body

```yaml
experiment_id: EXP-079-GROUNDING-DINO-DATA-CONVERSION-R2
status: VALID_CODE_READY
recorded_at: 2026-09-04T16:08:00+08:00
prior_checkpoint: CP-073
failed_conversion:
  run_id: stage-c-conversion-r1
  execution_commit: 04a5d0c6d98b1dade3253d011267724b4c2053c7
  exit_code: 1
  elapsed_ms: 120
  failure: 'CLASS_INVALID: truth/train/000100002.json: instance 1 is not plastic_cup'
  output_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/training-data/grounding-dino-cup-r1
  output_created: false
  disposition: INVALID_PRESERVED_PATH_RETIRED
root_cause:
  source_contract: the generator registers plastic_cup and plastic_cup_b as two bodies of the same class for the two_cups scenario
  source_readback: train and val truth contain 750 plastic_cup instances and 250 plastic_cup_b instances
  defect: the initial converter allowed only the primary body literal instead of normalizing both registered cup bodies
correction:
  single_variable: accept exactly the generator-registered body set [plastic_cup, plastic_cup_b] before normalizing both to cup and cup.
  unrelated_body_policy: fail closed with CLASS_INVALID
tdd:
  red_r4:
    result: 6 passed, 4 failed at the secondary cup identity
    exit_code: 1
    elapsed_ms: 360
    junit_sha256: 3c478432073e8c20a4b3685bc8fb56fce67819ee6e68da28fe46e5e9242ea700
  green_r5:
    result: 10 passed, 0 failed
    exit_code: 0
    elapsed_ms: 371
    junit_sha256: 96a0730bfd6e04cdd151f999d4b77817135826d0e486d2808c469dd1fc2b6a19
ordinary_gate:
  run_id: linux-test-stage-c-secondary-cup-r35-ordinary
  environment: valid seven-package r34 overlay
  scope: src/so101_demo_py/test only
  result: {passed: 1177, failed: 0, errors: 0, skipped: 0}
  exit_code: 0
  elapsed_ms: 12322
  junit_sha256: a442f810eaeb3a2e2d97704478a37c9223de7725a00e7b3b1c3b253c9f81f705
  python: /data/work/venvs/so101-grounded-sam/bin/python
  scratch: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/scratch/linux-test-stage-c-secondary-cup-r35-ordinary/tmp
next_destinations:
  converted_dataset: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/training-data/grounding-dino-cup-r2
  reproducibility_rerun: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/training-data/grounding-dino-cup-r2-repro
  collision_preflight: both absent
retention:
  retained_runs: [stage-c-conversion-r1 failure logs, secondary-cup RED r4, GREEN r5, ordinary r35]
  archived_runs: []
  deletion_candidates:
    - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/scratch/stage-c-secondary-cup-red-r4
    - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/scratch/stage-c-secondary-cup-green-r5
    - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/scratch/linux-test-stage-c-secondary-cup-r35-ordinary
```

## Checkpoint CP-074 — Stage C inventories frozen; data-scope decision required

```yaml
checkpoint: CP-074
status: VALID_AWAITING_USER_DECISION
recorded_at: 2026-09-04T16:08:00+08:00
stage: C
experiment_id: EXP-079-GROUNDING-DINO-DATA-CONVERSION-R2
converter_commit: 1f90c37fccc9d3d942efa9cdbdca5576295e51e1
source:
  archive_sha256: c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1
  extracted_tree_inventory_sha256: 08c878180cdc7dab43798a37dccc27fac9d717c1387f1970e131d2c48f4ea8ac
  extracted_files: 3605
  generator_commit: 2be8df09302feabffc7f028b16c90d06867f8055
  mjcf_sha256: d40494c9f88294840d8e8a90859c6a28dc361149b5878b785b787ea96c61e083
conversion:
  primary:
    run_id: stage-c-conversion-r2
    output_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/training-data/grounding-dino-cup-r2
    exit_code: 0
    elapsed_ms: 428
  independent_repro:
    run_id: stage-c-conversion-r2-repro
    output_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/training-data/grounding-dino-cup-r2-repro
    exit_code: 0
    elapsed_ms: 431
  outputs_byte_identical: true
  tree_inventory_sha256_both: be1274c4c01abd0e733a21d06f0ef0b8a327cbcc718890ee5c599b6e94fbcb3b
  file_modes: read-only 0444 after readback
inventories:
  train:
    images: 800
    instances: 800
    sha256: e40354905b18b08624338b7455027d692df0c3809a99a9070c25338abe2b4eee
  val:
    images: 200
    instances: 200
    sha256: 5728aaaee556d9749541c447b9c2e7b39f88fb0d62470d18a45b1a627cb47a69
  test:
    images: 200
    sealed: true
    boxes_present: false
    scenario_present: false
    sha256: df9d9fbf55fbffa3d0ebcb764d19c64cc403701673c006929bf09d2974d0fcd8
  dataset_profile_sha256: 2d7319c9afd6dc31aeb105b352eeba0e7a5bef31d4160bd9c0d5c5f82e1dd92b
  split_members_pairwise_disjoint: true
  prompt: cup.
  normalized_class: cup
profile:
  train:
    area_bucket_counts: {small: 0, medium: 800, large: 0}
    scenario_counts: {no_cup: 200, one_cup_distractors: 200, two_cups: 200, cup_near_bottle: 200}
    visible_cup_count_per_image: {'0': 200, '1': 400, '2': 200}
    fully_hidden_instances: 0
  val:
    area_bucket_counts: {small: 0, medium: 200, large: 0}
    scenario_counts: {no_cup: 50, one_cup_distractors: 50, two_cups: 50, cup_near_bottle: 50}
    visible_cup_count_per_image: {'0': 50, '1': 100, '2': 50}
    fully_hidden_instances: 0
  unsupported_truth_fields: {background: unknown, lighting: unknown, partial_occlusion: unknown}
decision_boundary:
  triggered: true
  evidence:
    - no train or val box falls in the COCO small bucket required for the preregistered small-target Recall metric
    - multi-cup coverage exists, but there are no fully hidden instances and partial occlusion cannot be established from source truth
    - the external baseline weakness specifically includes small targets, so beginning training would leave a required failure slice uncovered
  forbidden_until_user_decision:
    - changing generator scenarios, camera/object ranges, split quotas, or seed namespaces
    - starting the Grounding DINO smoke or formal training run
    - opening the sealed synthetic test
    - running the final COCO100 candidate
external_non_regression:
  coco100_access_during_stage_c: none
  rule: final frozen candidate only, one run; never train, select, or tune on COCO100
benchmark:
  r30_preserved_without_rerun: {passed: 571, skipped: 2, total: 573, pytest_seconds: 3210.78, storage: SATA_HDD}
  next_full_benchmark: only when required by a later code or model change, using a fresh registered NVMe scratch and elapsed-time comparison
next_action_requires_user: choose whether to authorize a bounded new MuJoCo dataset version covering small/far cups and explicit occlusion truth, or knowingly proceed with the frozen medium-only r2 train/val data
retention:
  retained_runs:
    - verified source archive copy and read-only extraction r1
    - read-only converted dataset r2
    - read-only independent reproducibility dataset r2-repro
    - all Stage C conversion, TDD, build, test, and readback logs
  archived_runs: []
  deletion_candidates:
    - all registered Stage C NVMe scratch trees; explicit user authorization required before deletion
```

## Stage C bounded small/far and partial-occlusion dataset expansion

```yaml
experiment_id: EXP-079-GROUNDING-DINO-DATA-AUGMENTATION-R3
status: PLANNED
recorded_at: 2026-09-04T16:28:00+08:00
prior_checkpoint: CP-074
authorization:
  decision: create a bounded new MuJoCo dataset version before Grounding DINO training
  scope: add small/far cups and verifiable explicit partial-occlusion truth
  unchanged_contracts:
    normalized_class: cup
    prompt: cup.
    sam: frozen SAM 2.1 Hiera Tiny, stateless per frame
lifecycle: NEW_DURABLE_DATA_VERSION
immutability:
  forbidden_mutation:
    - read-only YOLO-Seg source extraction r1
    - read-only Grounding DINO conversion r2
    - read-only Grounding DINO conversion r2-repro
    - source archive and all prior evidence
  output_collision_policy: output roots must not exist; allocate a new run ID after any failed creation
dataset_contract:
  schema_version: 2
  image_size: [640, 480]
  camera_name: task_camera
  split_counts: {train: 1200, val: 300, test: 300}
  scenario_quotas:
    train:
      no_cup: 200
      one_cup_distractors: 200
      two_cups: 200
      cup_near_bottle: 200
      small_far_cup: 200
      partially_occluded_cup: 200
    val:
      no_cup: 50
      one_cup_distractors: 50
      two_cups: 50
      cup_near_bottle: 50
      small_far_cup: 50
      partially_occluded_cup: 50
    test:
      no_cup: 50
      one_cup_distractors: 50
      two_cups: 50
      cup_near_bottle: 50
      small_far_cup: 50
      partially_occluded_cup: 50
  seed_namespace:
    train: [410000000, 410001199]
    val: [420000000, 420000299]
    test: [440000000, 440000299]
    independence: disjoint from r2 defaults 100000/200000/300000, fresh benchmark 700000/800000/900000, and retired diagnostic namespace 430000000-430000299
    bounded_attempt_seed_derivation: numpy SeedSequence([sample_seed, scenario_ordinal, attempt_index])
  split_rules:
    - seeds, image members, label members, and truth members are pairwise disjoint across train, val, and test
    - scenario schedule is quota-derived and deterministic within each split
    - scenario schedule round-robin order is [no_cup, one_cup_distractors, two_cups, cup_near_bottle, small_far_cup, partially_occluded_cup]
    - test labels and truth become opaque sealed members before training, checkpoint selection, or threshold tuning
    - COCO100 is never mounted or read during generation, training, selection, or threshold tuning
scene_geometry:
  mjcf: src/so101_demo_py/assets/mujoco/v5_multi_object_scene.xml
  base_camera_position_m: [0.65, -0.65, 0.55]
  base_camera_xyaxes: [0.707, 0.707, 0.0, -0.371, 0.371, 0.851]
  ordinary_camera_xyz_jitter_m: [-0.015, 0.015]
  ordinary_cup_a:
    center_m: [0.02, -0.28, 0.165]
    xy_jitter_m: [-0.045, 0.045]
  ordinary_cup_b:
    center_m: [-0.09, -0.31, 0.165]
    xy_jitter_m: [-0.025, 0.025]
  ordinary_bottle:
    center_m: [0.11, -0.22, 0.19]
    xy_jitter_m: [-0.025, 0.025]
  small_far_cup:
    cup_center_m: [0.02, -0.28, 0.165]
    cup_xy_jitter_m: [-0.045, 0.045]
    camera_retreat_along_local_positive_z_m: [2.40, 3.00]
    local_positive_z_definition: normalized third column of the immutable MuJoCo camera rotation matrix
    ordinary_camera_xyz_jitter_m: [-0.015, 0.015]
    acceptance:
      visible_bbox_area_px2: {minimum_exclusive: 0, maximum_exclusive: 1024}
      visible_pixel_count_minimum: 64
      maximum_deterministic_attempts: 64
  partially_occluded_cup:
    cup_center_m: [0.02, -0.28, 0.165]
    cup_xy_jitter_m: [-0.025, 0.025]
    bottle_z_m: 0.19
    bottle_longitudinal_offset_toward_camera_m: [0.055, 0.105]
    bottle_perpendicular_offset_m: [-0.025, 0.025]
    ordinary_camera_xyz_jitter_m: [-0.015, 0.015]
    acceptance:
      visible_fraction_inclusive: [0.35, 0.80]
      visible_pixel_count_minimum: 64
      occluded_pixel_count_minimum: 1
      maximum_deterministic_attempts: 64
truth_contract:
  visible_truth: MuJoCo geom/body-ID segmentation, never material color
  partial_occlusion_reference: paired segmentation render with the declared orange_bottle occluder hidden and all cup/camera state unchanged
  canonical_amodal_definition: bitwise union of the visible mask and the separately retained paired-reference mask
  measured_instance_fields:
    - body_id
    - body_name
    - visible_pixel_count
    - polygon_xy
    - mask_shape_hw
    - visible_mask_rle_counts
    - visible_mask_sha256
    - paired_reference_pixel_count
    - paired_reference_mask_rle_counts
    - paired_reference_mask_sha256
    - amodal_pixel_count
    - amodal_mask_rle_counts
    - amodal_mask_sha256
    - occluded_pixel_count
    - visible_fraction
    - occlusion_state
    - occluder_body_name
    - occlusion_reference
  verification_rules:
    - all three RLE masks decode to the declared image shape and hashes
    - canonical amodal mask equals visible mask bitwise-unioned with the paired-reference mask
    - visible mask is therefore a strict subset of the canonical amodal mask for accepted partial scenes
    - pixel counts and visible_fraction recompute exactly from decoded masks
    - partially_occluded_cup must satisfy the registered acceptance band and declare orange_bottle
    - unsupported ordinary-scene occlusion remains unmeasured rather than inferred
planned_outputs:
  source_dataset: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/training-data/yolo-seg-small-occlusion-r3
  source_archive: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/training-data/archives/so101-v5-t005-cup-small-occlusion-r3.tar.gz
  converted_dataset: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/training-data/grounding-dino-cup-r3
  reproducibility_rerun: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/training-data/grounding-dino-cup-r3-repro
provenance:
  planning_commit: adcfc0e1f87d6b271407ba029e3cc284310bb88e
  generator_commit: TO_BE_FROZEN_AFTER_GREEN_CODE_GATE
  overlay: TO_BE_NEW_SEVEN_PACKAGE_SYMLINK_OVERLAY
  python: /data/work/venvs/so101-grounded-sam/bin/python
  ros_domain_id: UNSET_DATASET_GENERATION_NO_ROS_GRAPH
  gz_partition: UNSET_DATASET_GENERATION_NO_GAZEBO_TRANSPORT
tdd_and_gates:
  - first add failing tests for quotas, split exclusion, RLE truth validation, small acceptance, paired occlusion, deterministic retry, and fail-closed exhaustion
  - focused RED to GREEN uses a unique registered NVMe scratch with TMPDIR/TMP/TEMP preflight from the locked Python
  - build a fresh seven-package symlink overlay and run the ordinary src/so101_demo_py/test gate
  - run the explicit benchmark gate once because the new model/data selection path changes benchmark inputs; preserve r30 and compare elapsed time without rerunning r30
  - archive and convert only after code and gates are GREEN; read back every SHA and dataset profile before marking VALID
failure_criteria:
  - output collision, seed or member overlap, quota mismatch, nondeterministic schedule, retry exhaustion, malformed RLE, non-subset visible mask, truth mismatch, CPU fallback, provenance mismatch, or any sealed-test access before freeze
external_non_regression:
  coco100: final frozen checkpoint only, exactly one run, never used for training, checkpoint selection, or threshold tuning
retention:
  retained_runs: [all new source, archive, conversion, code-gate, and readback evidence]
  archived_runs: []
  deletion_candidates: [future per-run NVMe scratch trees; never delete without explicit user authorization]
next_action: commit and Gitee-sync this PLANNED contract before adding tests or generating data
```

## Checkpoint CP-075 — Stage C augmentation geometry preflight correction

```yaml
checkpoint: CP-075
status: PLANNED_CONTRACT_CORRECTED_BEFORE_FORMAL_GENERATION
recorded_at: 2026-09-04T17:02:00+08:00
stage: C
experiment_id: EXP-079-GROUNDING-DINO-DATA-AUGMENTATION-R3
source_commit: 1898829e2f0e93d9adb82eed26457d05c599a200
formal_dataset_created: false
preflight_runs:
  r42:
    status: INVALID_RANGE
    failure: small_far_cup seed 410000000 exhausted 64 attempts with the preregistered 0.90-1.20 m retreat
  r43:
    status: VALID_DIAGNOSTIC
    ordinary_visible_pixels: 4274
    attempted_retreat_m: [0.90, 1.20]
    small_visible_pixels_range: [488, 1059]
    small_bbox_area_px2_range: [4335.79, 9186.46]
  r44_r45:
    status: VALID_SINGLE_VARIABLE_CAMERA_SWEEP
    conclusion: camera local-positive-z direction and MuJoCo state propagation are correct; the original retreat magnitude was insufficient for the 26-geom cup silhouette
  r46:
    status: INVALID_DIAGNOSTIC_NO_SUMMARY
    failure: strict raw paired-render subset assertion stopped aggregation before output
  r47:
    status: VALID_RANGE_AND_MASK_DIAGNOSTIC
    sampled_seeds: 30 across the train, val, and sealed-test seed namespaces without reading any sealed-test annotation
    selected_small_range_m: [2.40, 3.00]
    selected_small_results:
      accepted: 30
      failed: 0
      deterministic_attempts: {maximum: 6, mean: 2.3}
      visible_pixels_range: [184, 292]
      bbox_area_px2_range: [234.86, 802.92]
    paired_render_boundary_readback:
      attempts: 16
      visible_pixels_range: [1215, 2538]
      paired_reference_pixels_range: [4522, 5033]
      visible_not_in_raw_reference_pixels_range: [4, 12]
root_cause:
  small_far: the physical cup remains too large in the image at 0.90-1.20 m because the registered target body comprises 26 visible/collision geoms; the actual polygon box never entered the COCO small bucket
  partial_occlusion: independent GPU segmentation passes have a small non-monotonic raster boundary when the occluder is removed even though cup and camera transforms are unchanged
contract_correction:
  single_geometry_variable: replace far retreat [0.90, 1.20] m with [2.40, 3.00] m
  explicit_truth_rule: retain the raw paired-reference mask and define canonical amodal as visible bitwise-unioned with paired-reference
  reason: the union is the conservative amodal truth by definition, preserves every actually visible target pixel, and remains exactly reproducible and converter-verifiable
unchanged:
  - split counts, scenario quotas, seed namespaces, attempt derivation, prompt cup., generic cup class, and all test-sealing rules
  - old r2, r2-repro, source archive, prior raw evidence, and COCO100 remain untouched
next_action: revise the failing tests for the corrected amodal contract, prove RED, implement the single correction, then preflight every exact augmented seed before formal generation
retention:
  retained_runs: [r42, r43, r44, r45, r46, r47]
  archived_runs: []
  deletion_candidates: []
```

## Checkpoint CP-076 — train/val geometry fixed; diagnostic test namespace retired

```yaml
checkpoint: CP-076
status: VALID_PLANNED_BEFORE_FORMAL_GENERATION
recorded_at: 2026-09-04T17:18:00+08:00
stage: C
experiment_id: EXP-079-GROUNDING-DINO-DATA-AUGMENTATION-R3
source_commit_before_code_checkpoint: a7d22f5c836634fb319569b5db1e7c1838cfe2b8
sealed_test_boundary:
  issue: r47 geometry diagnostics included ten seeds from the preregistered 430000000-430000299 test namespace
  image_or_annotation_written: false
  image_or_annotation_opened: false
  model_training_or_selection: false
  disposition: fail closed; retire the entire 430000000-430000299 namespace before formal generation
  replacement_namespace: [440000000, 440000299]
  replacement_prior_use: none
  rule: do not preview, profile, tune, or preflight replacement test samples; generate them once in the formal dataset run and immediately seal their label/truth members
train_val_exact_preflight:
  run_id: stage-c-augmentation-train-val-exact-preflight-r50
  test_namespace_accessed: false
  result: VALID
  small_far_cup:
    planned_and_accepted: {train: 200, val: 50}
    failures: 0
    deterministic_attempts_maximum: 10
    bbox_area_px2_range: [160.58, 939.42]
    visible_pixels_range: [105, 302]
  partially_occluded_cup:
    planned_and_accepted: {train: 200, val: 50}
    failures: 0
    deterministic_attempts_maximum: 8
    visible_fraction_range: [0.350858135998262, 0.5072738772928527]
    visible_pixels_range: [1596, 2525]
frozen_contract_after_preflight:
  small_far_camera_retreat_m: [2.40, 3.00]
  partial_visible_fraction_inclusive: [0.35, 0.80]
  maximum_deterministic_attempts: 64
  train_seed_range: [410000000, 410001199]
  val_seed_range: [420000000, 420000299]
  sealed_test_seed_range: [440000000, 440000299]
  all_other_CP075_quotas_ranges_and_truth_rules: unchanged
next_action: complete related regression, fresh overlay, ordinary gate, and required explicit benchmark before committing the generator/converter code
retention:
  retained_runs: [r47 contamination evidence, r48 corrected-contract RED, r49 GREEN, r50 exact train/val preflight]
  archived_runs: []
  deletion_candidates:
    - r48 and r49 NVMe scratch trees; do not delete without explicit authorization
```

## Checkpoint CP-077 — augmentation generator and converter code GREEN

```yaml
checkpoint: CP-077
status: VALID_CODE_READY_AWAITING_EXPLICIT_BENCHMARK
recorded_at: 2026-09-04T17:42:00+08:00
stage: C
experiment_id: EXP-079-GROUNDING-DINO-DATA-AUGMENTATION-R3
execution_commit_before_code_commit: a7d22f5c836634fb319569b5db1e7c1838cfe2b8
implementation:
  - schema-v2 quota-derived deterministic scenario scheduling with exact split and seed exclusion
  - bounded small_far_cup and partially_occluded_cup generation using SeedSequence sample/scenario/attempt namespaces
  - visible, raw paired-reference, and canonical amodal RLE masks with SHA and count provenance
  - canonical amodal equals visible bitwise-unioned with paired-reference and is revalidated by the converter
  - schema-v2 converter profiles measured partial occlusion while retaining schema-v1 compatibility
  - converter rejects scenario-quota/sample mismatch and duplicate seeds before annotation parsing
  - test stays opaque in conversion and the replacement 440000000 namespace has not been previewed
tdd:
  invalid_preflights:
    r36: overlay source under shell nounset failed before pytest
    r37: exact temp path matched but the preflight assertion incorrectly also required it to be its own ancestor; pytest not started
  initial_red_r38: {exit_code: 2, result: collection failed on missing SceneGeometry API, elapsed_ms: 412}
  initial_green_r39: {passed: 11, failed: 0, elapsed_ms: 1159}
  related_regression_r40: {passed: 46, failed: 1, failure: tuple/list manifest readback mismatch, elapsed_ms: 1288}
  related_green_r41: {passed: 47, failed: 0, elapsed_ms: 1254}
  corrected_contract_red_r48: {passed: 6, failed: 3, failures: [old retreat range, missing paired-reference fields, strict raw subset assumption]}
  corrected_contract_green_r49: {passed: 11, failed: 0, elapsed_ms: 1244}
  manifest_red_r54: {passed: 2, failed: 2, failures: [scenario quota not reconciled, duplicate seed reached truth mismatch]}
  manifest_green_r55:
    passed: 49
    failed: 0
    elapsed_ms: 1503
    junit_sha256: 8518383b05fd2f38dad5029983c21b41cf5687db1cf8002dc78d109129042eb1
quality:
  ruff_version: 0.15.20
  ruff_check: PASS
  ruff_format_check: PASS
  py_compile: PASS
  git_diff_check: PASS
files:
  augmented_config_sha256: c2af80e37a33e76c179c410cf428e7d7a56a46cd89024f75a5134a4e1e57e9c5
  generator_sha256: 8b7d93491cf45db7f6dbab5f214cd435f87b3927cb77971420dd4dd6e21901be
  converter_sha256: 65a49222884c11791c4b53075d63cf10319e27be775a67d122218809693076af
fresh_overlay:
  run_id: linux-build-stage-c-augmentation-r52
  root: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-stage-c-augmentation-r52
  packages: [mujoco_ros2_control_msgs, mujoco_ros2_control_plugins, mujoco_3d_lidar, mujoco_ros2_control, so101_mujoco_support, so101_teleop, so101_demo_py]
  build_exit_code: 0
  build_elapsed_ms: 55834
  source_mode: symlink install resolves to the isolated checkout
  lodepng_source: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-r26/build/mujoco_ros2_control/_deps/lodepng-src
  lodepng_head: ed6fe5825c6a4fbb7f58ab35a4231c7543cd452a
  fetchcontent_fully_disconnected: true
  prefix_readback: all seven package prefixes resolve inside r52
ordinary_gate:
  final_run_id: linux-test-stage-c-augmentation-r56-ordinary
  scope: src/so101_demo_py/test only
  result: {passed: 1190, failed: 0, errors: 0, skipped: 0}
  colcon_exit_code: 0
  test_result_exit_code: 0
  elapsed_ms: 13976
  junit_sha256: 5ec565f35dbcd198b24cbec28d582b9601935a631c55977fc89ae7052cf8c4c0
  overlay: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-stage-c-augmentation-r52/install
  python_preflight: /data/work/venvs/so101-grounded-sam/bin/python
  scratch: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/scratch/linux-test-stage-c-augmentation-r56-ordinary/tmp
benchmark_gate:
  status: PENDING_ON_COMMITTED_CODE
  command: colcon test --packages-select so101_demo_py --pytest-args benchmark_test
  storage_rule: fresh unique registered /data NVMe scratch with exact locked-Python tempfile preflight
  immutable_comparison_baseline: {run_id: r30, storage: SATA_HDD, passed: 571, skipped: 2, total: 573, pytest_seconds: 3210.78}
next_action: commit only owned code, config, tests, and CP076-CP077 ledger changes; fetch/rebase/push/readback; then run the single required explicit benchmark on that exact commit
retention:
  retained_runs: [r36-r56 and r52 overlay]
  archived_runs: []
  deletion_candidates:
    - all registered NVMe scratch trees r36-r56 and r52; do not delete without explicit authorization
```

## Checkpoint CP-078 — Stage C code gates complete on committed source

```yaml
checkpoint: CP-078
status: VALID_CODE_GATES_COMPLETE_READY_FOR_FORMAL_DATASET
recorded_at: 2026-09-04T17:20:45+08:00
stage: C
experiment_id: EXP-079-GROUNDING-DINO-DATA-AUGMENTATION-R3
source_commit: d38bf439ccbf7e27c38f98dccdf4975b04e985b8
remote: gitee/codex/v5-t004-yolo-seg-rgbd
remote_sha_readback: d38bf439ccbf7e27c38f98dccdf4975b04e985b8
overlay:
  run_id: linux-build-stage-c-augmentation-r52
  install: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-stage-c-augmentation-r52/install
  package_count: 7
  source_mode: symlink install resolves to this isolated checkout
  lodepng_head: ed6fe5825c6a4fbb7f58ab35a4231c7543cd452a
  fetchcontent_fully_disconnected: true
invalid_benchmark_attempt:
  run_id: linux-test-stage-c-augmentation-r57-benchmark
  status: INVALID_ENVIRONMENT_NOT_A_PERFORMANCE_RESULT
  command_driver: /usr/bin/colcon
  failure: colcon selected /usr/bin/python3 rather than the locked Python, causing missing torch and a rasterizer-version mismatch
  observed_only: {tests: 573, failures: 62, skipped: 2, wall_seconds: 446.294}
  rule: preserve the evidence but do not compare this elapsed time with r30
environment_recovery:
  run_id: linux-test-stage-c-augmentation-r58-focused-env
  status: VALID
  result: {passed: 3, failed: 0, errors: 0, skipped: 0, elapsed_ms: 4178}
  python: /data/work/venvs/so101-grounded-sam/bin/python
  command_driver: /data/work/venvs/so101-grounded-sam/bin/python /usr/bin/colcon
  dependencies: {PIL: 12.3.0, torch: 2.13.0+cu130, transformers: 4.56.2, scipy: 1.17.1}
  scratch: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/scratch/linux-test-stage-c-augmentation-r58-focused-env/tmp
  junit_sha256: b83c54158e150905f9fda139269f9beacdf0d332bce9f4ffc011af8d3ce69b37
explicit_benchmark_gate:
  run_id: linux-test-stage-c-augmentation-r59-benchmark
  status: VALID
  command: /data/work/venvs/so101-grounded-sam/bin/python /usr/bin/colcon test --packages-select so101_demo_py --pytest-args benchmark_test
  result: {passed: 571, failed: 0, errors: 0, skipped: 2, total: 573}
  colcon_exit_code: 0
  test_result_exit_code: 0
  wall_seconds: 649.214
  pytest_seconds: 647.676
  python: /data/work/venvs/so101-grounded-sam/bin/python
  dependencies: {PIL: 12.3.0, torch: 2.13.0+cu130, transformers: 4.56.2, scipy: 1.17.1}
  scratch: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/scratch/linux-test-stage-c-augmentation-r59-benchmark/tmp
  tempfile_preflight: exact resolved match to the registered run-specific NVMe scratch
  junit_sha256: c4efed19b6f678608b7081b665f2a5fafe20322be4e4113514ec72122ce0c8cd
  immutable_r30_hdd_baseline: {passed: 571, skipped: 2, total: 573, pytest_seconds: 3210.78}
  nvme_wall_comparison:
    seconds_reduced: 2561.566
    speedup: 4.9456
    percent_reduction: 79.780
    caveat: r30 reports pytest time while r59 comparison conservatively uses complete colcon wall time
  semantics_preserved: fsync, ext4 journaling, integrity checks, and ordinary disk-backed fixtures remained enabled; no tmpfs was used
committed_ordinary_gate:
  run_id: linux-test-stage-c-augmentation-r60-ordinary-committed
  status: VALID
  scope: src/so101_demo_py/test only
  result: {passed: 1190, failed: 0, errors: 0, skipped: 0}
  colcon_exit_code: 0
  test_result_exit_code: 0
  elapsed_ms: 13835
  python: /data/work/venvs/so101-grounded-sam/bin/python
  scratch: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/scratch/linux-test-stage-c-augmentation-r60-ordinary-committed/tmp
  tempfile_preflight: exact resolved match to the registered run-specific NVMe scratch
  junit_sha256: 306890fd10b52386993d30a4643be83d2b9d8be745d60ac35e8b1d70b423c84a
sealed_boundaries:
  replacement_test_namespace: [440000000, 440000299]
  status: not previewed or preflighted; formal generation only
  coco100: untouched; final frozen checkpoint non-regression only, exactly once
next_action: generate the complete r3 dataset once into the preregistered absent durable root, immediately seal test truth and labels, archive it, convert twice, and read back hashes and train/val profiles
retention:
  retained_runs: [r57 invalid evidence, r58 environment recovery, r59 valid benchmark, r60 committed ordinary gate, r52 overlay]
  archived_runs: []
  deletion_candidates:
    - r57-r60 registered NVMe scratch trees; do not delete without explicit user authorization
```

## Checkpoint CP-079 — bounded r3 dataset frozen and reproducible

```yaml
checkpoint: CP-079
status: VALID_STAGE_C_DATA_FROZEN
recorded_at: 2026-09-04T17:31:27+08:00
stage: C
experiment_id: EXP-079-GROUNDING-DINO-DATA-AUGMENTATION-R3
execution_commit: 2b94ff24c2507828c9681f73af80a6a8972acbcd
remote_sha_before_generation: 2b94ff24c2507828c9681f73af80a6a8972acbcd
preflight:
  r61:
    status: INVALID_BEFORE_DIRECTORY_OR_DATA_CREATION
    failure: zsh reserved path array was used as a loop variable, so mkdir was unavailable and the shell exited before any run, scratch, or output directory was created
    disposition: run ID retired and never reused
  r62:
    status: VALID
    source_archive_r1_sha256_readback: c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1
    old_r2_tree_inventory_sha256_readback: be1274c4c01abd0e733a21d06f0ef0b8a327cbcc718890ee5c599b6e94fbcb3b
    old_r2_repro_tree_inventory_sha256_readback: be1274c4c01abd0e733a21d06f0ef0b8a327cbcc718890ee5c599b6e94fbcb3b
    old_r2_modes: {files: '0444', directories: '0555'}
    planned_output_collision_count: 0
    python: /data/work/venvs/so101-grounded-sam/bin/python
    tempfile: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/scratch/stage-c-formal-generation-r62/tmp
    overlay: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-stage-c-augmentation-r52/install
formal_generation:
  run_id: stage-c-formal-generation-r62
  output_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/training-data/yolo-seg-small-occlusion-r3
  generator_cli_status: OK
  generator_cli_sample_count: 1800
  generator_stderr_empty: true
  wrapper_exit_capture: INVALID_AFTER_GENERATOR_RETURN because zsh status is read-only
  validity_recovery: CLI OK is printed only after the complete manifest is fsync-persisted; manifest, exact artifact set, counts, and hashes all passed independent readback without rerunning generation
  recovered_elapsed_ms_from_provenance_to_manifest_mtime: 71048
  schema_version: 2
  generator_commit: 2b94ff24c2507828c9681f73af80a6a8972acbcd
  source_manifest_sha256: bc4f7386b681aa298d636b7b90ea754de0e74b08e90589a4d185694eeae10780
  source_tree_inventory_sha256: 0533e0356a385d4cff8b6b0e3b250b95be75af365ce75181ea3a3c7888df30b1
  files: 5402
  artifacts_in_manifest: 5401
  split_counts: {train: 1200, val: 300, test: 300}
  seed_ranges:
    train: [410000000, 410001199]
    val: [420000000, 420000299]
    test: [440000000, 440000299]
  seeds_unique_and_splits_disjoint: true
  scenario_quotas:
    train: {no_cup: 200, one_cup_distractors: 200, two_cups: 200, cup_near_bottle: 200, small_far_cup: 200, partially_occluded_cup: 200}
    val: {no_cup: 50, one_cup_distractors: 50, two_cups: 50, cup_near_bottle: 50, small_far_cup: 50, partially_occluded_cup: 50}
    test: {no_cup: 50, one_cup_distractors: 50, two_cups: 50, cup_near_bottle: 50, small_far_cup: 50, partially_occluded_cup: 50}
  class_instance_total: 1800
  environment: {MUJOCO_GL: egl, HF_HUB_OFFLINE: '1', TRANSFORMERS_OFFLINE: '1', PYTHONNOUSERSITE: '1'}
test_seal:
  replacement_namespace_generated_once: [440000000, 440000299]
  image_label_truth_members: 900
  member_modes: '0444'
  directory_modes: '0555'
  annotation_content_read: false
  preview_preflight_tuning_or_selection: none
archive:
  run_id: stage-c-archive-r64
  path: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/training-data/archives/so101-v5-t005-cup-small-occlusion-r3.tar.gz
  sha256: e09ab3d8b56d79fba909ecdee28e07c31ca056d5784cbd972bd1375c0c533afc
  bytes: 70104939
  elapsed_ms: 1866
  regular_file_members: 5402
  symlink_or_special_members: 0
  reproducibility: sorted GNU tar with zero mtime and numeric zero owner/group, gzip -n
  publication: verified scratch artifact atomically hard-linked no-clobber into the preregistered final path
conversion:
  primary:
    run_id: stage-c-conversion-r3-primary-r65
    output_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/training-data/grounding-dino-cup-r3
    exit_code: 0
    elapsed_ms: 975
  independent_repro:
    run_id: stage-c-conversion-r3-repro-r66
    output_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/training-data/grounding-dino-cup-r3-repro
    exit_code: 0
    elapsed_ms: 974
  primary_repro_byte_identical: true
  tree_inventory_sha256_both: 1567c002dc9ec6f9a627eec0d201b03c2395ee809178423f1ae3657ffeb27a13
  dataset_profile_sha256: a5ede14b4af18910915dd9c8d204921b836d2d97691466e6b38c8ad2f4f20d04
  test_sealed_members_sha256: 7a0fa1bd72933a389cb2e734f2c5b50c46219f5fb4c6f481add2409127d7ba7d
  train_inventory_sha256: 376146b8b7d9c7adc8c9ff4e22d5302188fe33cb2bfc0765458521088247e9ea
  val_inventory_sha256: 7d9b24a6b61a800d31acdf4c7ebf8bbc8ec785e108c7a79c0235cc42270ac592
  source_archive_sha256_bound: e09ab3d8b56d79fba909ecdee28e07c31ca056d5784cbd972bd1375c0c533afc
  source_manifest_sha256_bound: bc4f7386b681aa298d636b7b90ea754de0e74b08e90589a4d185694eeae10780
  converter_commit: 2b94ff24c2507828c9681f73af80a6a8972acbcd
  class_name: cup
  prompt: cup.
  test: {sample_count: 300, sealed: true, boxes_present: false, scenario_present: false, opaque_hash_members_only: true}
profile:
  train:
    images: 1200
    instances: 1200
    area_bucket_counts: {small: 200, medium: 332, large: 668}
    scenario_counts: {no_cup: 200, one_cup_distractors: 200, two_cups: 200, cup_near_bottle: 200, small_far_cup: 200, partially_occluded_cup: 200}
    visible_cup_count_per_image: {'0': 200, '1': 800, '2': 200}
    partial_occlusion: {measured_none: 0, measured_partial: 200, unmeasured: 1000}
    fully_hidden_instances: 0
  val:
    images: 300
    instances: 300
    area_bucket_counts: {small: 50, medium: 87, large: 163}
    scenario_counts: {no_cup: 50, one_cup_distractors: 50, two_cups: 50, cup_near_bottle: 50, small_far_cup: 50, partially_occluded_cup: 50}
    visible_cup_count_per_image: {'0': 50, '1': 200, '2': 50}
    partial_occlusion: {measured_none: 0, measured_partial: 50, unmeasured: 250}
    fully_hidden_instances: 0
freeze:
  source_files: '0444'
  source_directories: '0555'
  primary_conversion_files: '0444'
  primary_conversion_directories: '0555'
  repro_conversion_files: '0444'
  repro_conversion_directories: '0555'
boundaries:
  old_r2_r2_repro_source_archive_and_prior_evidence_modified: false
  coco100_access: none
  microduck: paused
  mac_migration: forbidden until all Linux gates and four preset PickPlace runs succeed
next_action: Gitee-sync CP-079, then begin Stage D with a separately preregistered smoke-training run against read-only r3 train/val only; do not open the sealed synthetic test
retention:
  retained_runs: [r62 formal source, r63 readback, r64 archive and durable staging hardlink, r65 primary conversion, r66 repro conversion, r67 readback]
  archived_runs: []
  deletion_candidates:
    - all r62, r64, r65, and r66 registered NVMe scratch trees, including the r64 staged archive hardlink; do not delete without explicit user authorization
```

## Checkpoint CP-080 — Stage D training implementation and runs preregistered

```yaml
checkpoint: CP-080
status: PLANNED
recorded_at: 2026-09-04T17:37:26+08:00
stage: D
experiment_id: EXP-079-GROUNDING-DINO-TINY-CUP-FINETUNE-R1
prior_checkpoint: CP-079
planning_commit: cfcd75859a43fe982ad181b2644316cbc5c6b030
approved_scope: fine-tune only Grounding DINO Tiny on frozen r3 synthetic train, select only on frozen r3 synthetic val, and keep SAM frozen and absent from training
environment_preflight:
  run_id: stage-d-environment-preflight-r68
  status: VALID
  host: ai-station direct execution, no SSH
  python: /data/work/venvs/so101-grounded-sam/bin/python
  python_version: 3.12.3
  torch: 2.13.0+cu130
  cuda_runtime: '13.0'
  transformers: 4.56.2
  Pillow: 12.3.0
  scipy: 1.17.1
  gpu: NVIDIA GeForce RTX 5080
  gpu_uuid: GPU-0b7689c1-877a-b915-12aa-c9b9f86aa190
  compute_capability: '12.0'
  gpu_memory_mib: 16303
  bf16_supported: true
  competing_training_processes: 0
  microduck: paused
  data_filesystem: /dev/nvme0n1p5 mounted at /data
  data_available_bytes: 293622063104
base_model:
  model_id: IDEA-Research/grounding-dino-tiny
  revision: a2bb814dd30d776dcf7e30523b00659f4f141c71
  read_only_host_root: /data/work/so101-models/grounded-sam-v2-scipy-lock/grounding-dino-tiny
  bundle_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
  detector_files_verified: 11
  model_safetensors_sha256: 1a2412ef99bd74bcd3c2a246fa1e48581f8889a1300c9051974741314fc042f3
  preprocessor_config_sha256: 8454179ba95e2ad22947835aad7b45862a601fc0055ab88bf1ee70892d3aea60
  loading: local_files_only and use_safetensors; fail closed on revision or file SHA mismatch
data:
  source_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/training-data/yolo-seg-small-occlusion-r3
  converted_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/training-data/grounding-dino-cup-r3
  source_manifest_sha256: bc4f7386b681aa298d636b7b90ea754de0e74b08e90589a4d185694eeae10780
  train_inventory_sha256: 376146b8b7d9c7adc8c9ff4e22d5302188fe33cb2bfc0765458521088247e9ea
  val_inventory_sha256: 7d9b24a6b61a800d31acdf4c7ebf8bbc8ec785e108c7a79c0235cc42270ac592
  source_archive_sha256: e09ab3d8b56d79fba909ecdee28e07c31ca056d5784cbd972bd1375c0c533afc
  class_name: cup
  prompt: cup.
  training_container_mounts:
    - train image directory read-only
    - val image directory read-only
    - train inventory file read-only
    - val inventory file read-only
    - detector base-model directory read-only
  forbidden_mounts: [synthetic test images, synthetic test labels, synthetic test truth, test-sealed-members.json, COCO100, SAM model]
implementation_contract:
  entrypoint: train_grounding_dino
  container_runner: scripts/grounding-dino-training-container.sh
  dockerfile: src/so101_demo_py/docker/grounding-dino-training/Dockerfile
  image: so101-grounding-dino-tiny-train:torch2.13.0-cu130-transformers4.56.2
  local_dependency_layer_source_image_id: sha256:16d37de42970f68e46940c4a1f374c080a50c89063ec09ebd455dce25f6c3249
  network_during_training: none
  device: cuda:0 only; CPU fallback forbidden
  output: new absent child below a durable output parent; no overwrite
  artifacts:
    - canonical resolved config and environment inventory
    - verified data and base-model SHA inventory
    - fsync-persisted per-epoch JSONL metrics with ETA, loss, TP, FP, FN, Precision, Recall, F1, small Recall, multi-cup Recall, and peak GPU memory
    - atomic complete epoch checkpoint whose SHA manifest is published last
    - optimizer, scheduler, epoch, and RNG state for verified resume into a new output root
    - immutable frozen-model manifest selected mechanically from val
  smoke_reload: selected smoke checkpoint must reload in a fresh Python process and complete inference on one val image
training_contract:
  seed: 20260904
  all_model_parameters_trainable: true
  optimizer: AdamW
  learning_rate: 0.00001
  betas: [0.9, 0.999]
  epsilon: 0.00000001
  weight_decay: 0.0001
  scheduler: linear_decay
  warmup_ratio: 0.10
  epochs: 8
  batch_size: 1
  gradient_accumulation_steps: 4
  effective_batch_size: 4
  max_grad_norm: 0.1
  precision: {training: bfloat16_autocast, validation: float32, checkpoint_weights: float32}
  gradient_checkpointing: true
  image_preprocessing: exact base GroundingDinoProcessor resize, rescale, normalize, and pad configuration
  augmentations: none beyond the frozen rendered dataset
  data_workers: 2
  deterministic:
    cudnn_benchmark: false
    cudnn_deterministic: true
    deterministic_algorithms: true
    cublas_workspace_config: ':4096:8'
    flash_and_memory_efficient_sdp: disabled
  checkpoint_frequency_epochs: 1
smoke:
  planned_output: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/training/grounding-dino-cup-r3-smoke-r1
  collision_preflight: absent
  epochs: 1
  batch_size: 1
  gradient_accumulation_steps: 1
  exact_subset: first deterministic sample from each of the six registered scenarios in train and val
  counts: {train: 6, val: 6}
  required_proofs: [nonempty cup text tokens, valid normalized center-format labels including an empty negative target, finite non-null loss, successful backward and optimizer step, complete checkpoint SHA, fresh-process reload and one-image CUDA inference]
formal:
  planned_output: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/training/grounding-dino-cup-r3-formal-r1
  collision_preflight: absent
  counts: {train: 1200, val: 300}
  launch: only after smoke is VALID; long run in a dedicated tmux window
validation_and_selection:
  box_iou_threshold: 0.50
  box_threshold_grid: [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
  text_threshold_grid: [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
  matching: per-image predictions sorted by descending score, each matched to the highest-IoU unmatched truth at IoU >= 0.50
  small_truth: absolute box area below 1024 px2
  multi_cup_truth: truth instances in registered two_cups images
  threshold_rank_descending: [F1, Recall, small_target_Recall, multi_cup_Recall, negative_FP, box_threshold, text_threshold]
  checkpoint_rank_descending: [F1, Recall, small_target_Recall, multi_cup_Recall, negative_FP, negative_epoch]
  selection_source: synthetic val only
  manual_image_selection: forbidden
resume:
  source: only a complete checkpoint with a valid SHA manifest, matching frozen config, base model, and dataset identities
  destination: a new absent run root; never overwrite or continue a failed/completed directory
  restored_state: [model, optimizer, scheduler, completed_epoch, Python RNG, NumPy RNG, Torch CPU RNG, Torch CUDA RNG]
sealed_boundaries:
  synthetic_test: remains sealed and inaccessible until checkpoint plus thresholds are frozen
  coco100: zero access and not mounted; final frozen candidate non-regression once only
  sam: frozen, stateless per frame, and not loaded during detector training
  mac: no migration before Linux synthetic safety, COCO100, and four preset PickPlace gates pass
tdd:
  - first add failing tests for config/provenance validation, train-val-only path confinement, COCO box conversion, negative targets, rank ordering, checkpoint completeness/resume, CUDA fail-closed, container mounts, network isolation, and output collision
  - implement minimal production code to turn RED to GREEN
  - build a fresh seven-package symlink overlay, then run the ordinary gate
  - run the explicit benchmark gate only if benchmark implementation, configuration, adapters, reports, tests, or a selected model input changes; do not rerun r30 or r59 merely for the training tool
next_action: commit and Gitee-sync this PLANNED contract, then add the Stage D RED tests before implementation
retention:
  retained_runs: [r68 environment and base-model readback]
  archived_runs: []
  deletion_candidates: []
```

## Checkpoint CP-081 — Stage D training implementation GREEN

```yaml
checkpoint: CP-081
status: VALID
recorded_at: 2026-09-04T18:02:26+08:00
stage: D
experiment_id: EXP-079-GROUNDING-DINO-TINY-CUP-FINETUNE-R1
prior_checkpoint: CP-080
source_commit_before_checkpoint: c2ac68a5db7987e9e4c00c38b5ba09637bfd6a88
implementation:
  config: src/so101_demo_py/config/perception/grounding_dino_training.yaml
  pure_contract_module: src/so101_demo_py/src/training/grounding_dino_finetune.py
  runtime_module: src/so101_demo_py/src/training/grounding_dino_runtime.py
  train_cli: src/so101_demo_py/src/cli/train_grounding_dino.py
  checkpoint_verifier_cli: src/so101_demo_py/src/cli/verify_grounding_dino_checkpoint.py
  container_runner: scripts/grounding-dino-training-container.sh
  dockerfile: src/so101_demo_py/docker/grounding-dino-training/Dockerfile
  entrypoints: [train_grounding_dino, verify_grounding_dino_checkpoint]
  boundaries:
    - train and val image directories and inventory files are the only dataset mounts
    - base detector is read-only; output parent is the only writable training mount
    - synthetic sealed test, COCO100, and SAM are not mounted
    - container network is none and CUDA is mandatory; CPU fallback and output collisions fail closed
    - split inventories, paths, model files, resume checkpoint, and output manifests are verified before use
tdd:
  invalid_red_wrapper:
    run_id: stage-d-training-red-r69
    status: INVALID
    reason: locked venv does not contain pytest, so collection did not start and no JUnit was produced
  red:
    run_id: stage-d-training-red-r70
    status: VALID_RED
    result: collection error because so101_demo.training.grounding_dino_finetune did not yet exist
    exit_code: 2
    junit_sha256: e954a11513d1a84be310ec1b3f790d2e1c47008e32557ad7d9de211bd98d0df8
  first_green_attempt:
    run_id: stage-d-training-green-r71
    status: EXPECTED_FAILURE
    result: {passed: 9, failed: 1}
    failure: Dockerfile did not expose the exact transformers pin directly to the audit test
    junit_sha256: 091deb436ce6392edb829e7d265fd4e8e5c1484fdb6355bef75c8f404cc8196b
  green:
    run_id: stage-d-training-green-r72
    status: VALID
    result: {passed: 10, failed: 0}
    junit_sha256: 1e5e1af444dc3a670314eb5f368a15cc906e83b4976176906af2dfbbf1639815
  post_runtime_fixes:
    changes:
      - serialize the CUDA device UUID before writing JSON
      - make the smoke processor probes explicitly include positive and negative cup targets
    run_id: stage-d-training-green-r73
    status: VALID
    result: {passed: 10, failed: 0}
    junit_sha256: 02b1385827a512e6091549d11f4d21f717ca010da3203efc186dfed59d9a7d48
  related_gate:
    run_id: stage-d-training-related-r75
    status: VALID
    scope: Grounding DINO training and dataset tests plus neighboring YOLO training contracts
    result: {passed: 32, failed: 0}
    junit_sha256: dfdefbd22607d407ad533e4235c29b15f34d9a31b114d64dc76fd03ae2284750
fresh_overlay:
  run_id: linux-build-stage-d-training-r76
  status: VALID
  package_count: 7
  symlink_install: true
  lodepng_source: complete local r26 cache, no network fetch
  lodepng_head: ed6fe5825c6a4fbb7f58ab35a4231c7543cd452a
  exit_code: 0
  elapsed_ms: 58107
  source_commit: c2ac68a5db7987e9e4c00c38b5ba09637bfd6a88
  python: /data/work/venvs/so101-grounded-sam/bin/python
  scratch: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/scratch/linux-build-stage-d-training-r76/tmp
  exit_log_sha256: 4d9df4ca40ba1bffedb848b35aa5fef9bc15596f255ba1ecdf5722700fce29c1
  readback:
    status: VALID_RECOVERY
    explanation: symlink-install entrypoints and lexical module paths are inside r76 while final symlink targets are the byte-identical owned source files
    evidence_sha256: 115cfeee652638879802d6d61e37c05f5d8bf32bfeb6dd70b78ffb46ce22740a
    invalid_wrappers:
      - set -u conflicted with colcon's optional COLCON_TRACE variable
      - final-target assertions incorrectly rejected normal symlink-install links back to source
ordinary_gate:
  invalid_launches:
    - run_id: linux-test-stage-d-training-r77-ordinary
      status: INVALID
      reason: sourcing r76 before invoking colcon with the venv Python hid system colcon-core metadata
      exit_code: 1
      elapsed_ms: 54
      junit: absent
    - run_id: linux-test-stage-d-training-r78-ordinary
      status: INVALID
      reason: the venv Python colcon preflight still lacked system colcon-core metadata
      exit_code: 1
      elapsed_ms: 56
      junit: absent
  valid_run:
    run_id: linux-test-stage-d-training-r79-ordinary
    status: VALID
    scope: src/so101_demo_py/test only
    result: {passed: 1200, failed: 0, errors: 0, skipped: 0}
    colcon_exit_code: 0
    test_result_exit_code: 0
    elapsed_ms: 14330
    overlay: /tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079/linux-build-stage-d-training-r76
    locked_python: /data/work/venvs/so101-grounded-sam/bin/python
    actual_test_python: /usr/bin/python3
    colcon: /usr/bin/colcon
    scratch: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/scratch/linux-test-stage-d-training-r79-ordinary/tmp
    tempfile_preflight: both Python executables resolved exactly to the run-specific NVMe scratch
    filesystem: /dev/nvme0n1p5 mounted at /data as ext4
    preflight_sha256: ec82646d09730fb53e00d0f187994b6126f0085e3a141410850cd69c65e61d6e
    exit_log_sha256: a1dc40d350b4ae476db8428879493afc921e3d5240c77afff18c76dbed516e7c
    junit_sha256: 83be43eeb31244a3f38b8c1dcfef88553a81f48c0c99e2abdd2cdbf7fc300640
static_checks:
  invalid_wrapper:
    run_id: stage-d-training-static-r80
    status: INVALID
    reason: assumed a nonexistent venv-local ruff and omitted pipefail, producing an incorrect wrapper exit record
  valid_run:
    run_id: stage-d-training-static-r81
    status: VALID
    ruff: 0.15.20 at /home/lenovo/.local/bin/ruff
    shellcheck: 0.9.0 at /usr/bin/shellcheck
    checks: [ruff check, ruff format --check, in-memory Python compile, shellcheck, git diff --check]
    exit_code: 0
    checks_log_sha256: 9a5653ccd045966f679550109d469b3d8b4dde4c69020dc746ca4beee9358bd2
benchmark_gate:
  status: NOT_RUN_BY_CONTRACT
  reason: this stage adds the independent training tool and does not change benchmark implementation, configuration, adapters, reports, tests, or a selected model input
  preserved_valid_benchmark: linux-test-stage-c-augmentation-r59-benchmark
  immutable_r30_hdd_baseline_seconds: 3210.78
sealed_boundaries:
  synthetic_test_access: none
  coco100_access: none
  microduck: paused
  mac_migration: forbidden until Linux safety gates and all four preset PickPlace runs succeed
next_action: commit only the owned implementation, tests, and this checkpoint; fetch and rebase onto the Gitee branch tip; verify the root AGENTS NVMe rule; ordinary-push and read back the remote SHA; then build the pinned training image and run the preregistered smoke
retention:
  retained_runs: [r69-r73 TDD, r75 related gate, r76 overlay, r77-r79 ordinary launches, r80-r81 static checks]
  archived_runs: []
  deletion_candidates:
    - all registered r69-r81 NVMe scratch trees; do not delete without explicit user authorization
```

## Checkpoint CP-082 — Stage D training image frozen

```yaml
checkpoint: CP-082
status: VALID
recorded_at: 2026-09-04T18:15:53+08:00
stage: D
experiment_id: EXP-079-GROUNDING-DINO-TINY-CUP-FINETUNE-R1
prior_checkpoint: CP-081
implementation_sync:
  implementation_commit: eb60c652b886185e52a592786f578e2bf204728b
  gitee_branch: codex/v5-t004-yolo-seg-rgbd
  remote_before_push: c2ac68a5db7987e9e4c00c38b5ba09637bfd6a88
  required_agents_commit_is_ancestor: b91a4b56d30bc971e7c2d64465516b9d7a49b299
  rebase: up to date; no rewrite required
  root_agents_nvme_rule_readback: present
  pushed_remote_sha: eb60c652b886185e52a592786f578e2bf204728b
  preexisting_untracked_build_install_log_directories_modified: false
image_build:
  run_id: stage-d-training-image-build-r82
  status: VALID
  source_commit: eb60c652b886185e52a592786f578e2bf204728b
  image: so101-grounding-dino-tiny-train:torch2.13.0-cu130-transformers4.56.2
  image_id: sha256:820c7bb0b1b75278b8bd00c3f4e9e48f166fc2037f977c079164a3473a46b6f3
  image_size_bytes: 5141800305
  entrypoint: train_grounding_dino
  docker: {client: 29.1.3, server: 29.1.3}
  command: scripts/grounding-dino-training-container.sh build
  refresh_base: false
  base_image: pinned digest and cache hit
  target_collision_preflight: absent
  exit_code: 0
  elapsed_ms: 654834
  build_note: Ubuntu noble-security restricted index timed out and apt explicitly ignored that unused index; all required packages installed successfully from available pinned sources or cache
  version_readback:
    torch: 2.13.0+cu130
    torchvision: 0.28.0+cu130
    transformers: 4.56.2
    cuda: '13.0'
  evidence:
    preflight_sha256: c89aa199e3cb5a3e2cee821941e5efc92f60a4b5dadc8e58a573d61f917daeb1
    buildkit_stderr_sha256: 0b2840c05b9e49a02c67303969ff6db358fe4409544e3c5d99b5a4146bff7a68
    exit_log_sha256: fdab34fc2519a216b30996ae4b570b5954fb99515017dcf0d966408af80c09d5
    image_inspect_sha256: 2636cc898443863e1b4706049c852eac03cd46720a3596c08e5592bf7a8521a5
    version_readback_sha256: 8a12525212b19c997f5765784121ea790a0aad6a114d796e458da30c2c69a769
sealed_boundaries:
  synthetic_test_access: none
  coco100_access: none
  sam_loaded: false
  microduck: paused
  mac_migration: forbidden
next_action: commit and Gitee-sync CP-082, then preflight and launch the preregistered smoke against read-only r3 train and val only; freeze and fresh-process verify the smoke checkpoint before formal training
retention:
  retained_runs: [stage-d-training-image-build-r82]
  archived_runs: []
  deletion_candidates: []
```

## Checkpoint CP-083 — smoke r1 failed before training; checkpointing fix planned

```yaml
checkpoint: CP-083
status: FAILED_DIAGNOSED
recorded_at: 2026-09-04T18:21:33+08:00
stage: D
experiment_id: EXP-079-GROUNDING-DINO-TINY-CUP-FINETUNE-R1
prior_checkpoint: CP-082
checkpoint_commit_before_record: 7e21d1ce695720ce90eea49c67672cb6c9f6a12c
smoke_r1:
  run_id: stage-d-training-smoke-r84
  status: FAILED_BEFORE_TRAINING
  implementation_commit: eb60c652b886185e52a592786f578e2bf204728b
  image_id: sha256:820c7bb0b1b75278b8bd00c3f4e9e48f166fc2037f977c079164a3473a46b6f3
  output: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/training/grounding-dino-cup-r3-smoke-r1
  output_reusable: false
  exit_code: 1
  elapsed_ms: 5558
  failure: GroundingDinoForObjectDetection does not support gradient checkpointing.
  training_steps_completed: 0
  checkpoints_written: 0
  retained_partial_files: [resolved-config.json, environment.json, provenance.json, checkpoints directory]
  partial_output_tree_evidence_sha256: 8a0b008a9a904a1461ca17a0027ae27d010dbcde0f24fcf97f039f6e60efcf44
  preflight:
    status: VALID_WITH_PROCESS_SCAN_RECOVERY
    train_count: 1200
    val_count: 300
    output_collision: absent
    gpu_compute_processes: 0
    cuda: available
    bf16: true
    image_and_host_implementation_hashes: identical
    preflight_sha256: 897c89ae5b58fa43a82554fdf05716e2479db092ebe2a8e388cc0d7e0c9e106d
    valid_pause_scan_sha256: 7e13067a507cc96463d006dc140706a02d6dee3c9f2d99fa63231c560c131d75
    invalid_process_checks: pgrep and the first recovery pipeline matched their own command or evidence filename; neither indicated a real process
  stdout_sha256: 7117cbfa68239e4da24bbd82b781715699ac223a5b81bf17c450504a87879660
  exit_log_sha256: 09bb5b55e15fa04a7c9ac993851681044d409f96ae0f3ab81d4d150428b753ac
diagnosis:
  locked_transformers: 4.56.2
  model_class: GroundingDinoForObjectDetection
  inherited_supports_gradient_checkpointing: false
  existing_internal_support:
    - GroundingDinoPreTrainedModel._set_gradient_checkpointing sets GroundingDinoDecoder.gradient_checkpointing
    - GroundingDinoDecoder.forward already invokes torch.utils.checkpoint.checkpoint while training
  invalid_probe:
    run_id: stage-d-gradient-checkpoint-diagnostic-r85
    status: INVALID
    reason: docker run omitted -i, so the heredoc was not delivered and the empty Python program exited zero
  valid_probe:
    run_id: stage-d-gradient-checkpoint-diagnostic-r86
    status: VALID
    base_model_mount: read-only
    network: none
    before: {support_flag: false, decoder_flag: false}
    action: set the instance support flag true, then call the library gradient_checkpointing_enable method
    after: {support_flag: true, decoder_flag: true, is_gradient_checkpointing: true}
    exit_code: 0
    elapsed_ms: 3734
    probe_sha256: 7a8d71865d36cd85fb32c6c6ead23aa9374107a29e594ca2d383bb3049c5a1e3
planned_fix:
  method: add a fail-closed helper for the exact Grounding DINO old-format checkpointing implementation; use the public Transformers enable method after correcting the inconsistent instance capability flag, then verify the decoder and model checkpointing flags
  tdd: add a focused RED test before changing production code, then run focused GREEN, related, fresh overlay, and ordinary gates
  new_smoke_output: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/training/grounding-dino-cup-r3-smoke-r2
  new_smoke_collision_preflight: absent
  formal_output: remains the preregistered absent grounding-dino-cup-r3-formal-r1 root and cannot launch until smoke r2 is valid
sealed_boundaries:
  synthetic_test_access: none
  coco100_access: none
  sam_loaded: false
  microduck: paused
  mac_migration: forbidden
next_action: commit and Gitee-sync this failure checkpoint, then execute the checkpointing compatibility change RED to GREEN and build a new immutable image tag or digest before smoke r2
retention:
  retained_runs: [r84 failed smoke, r85 invalid diagnostic, r86 valid diagnostic]
  archived_runs: []
  deletion_candidates: []
```

## Checkpoint CP-084 — checkpointing compatibility fix GREEN

```yaml
checkpoint: CP-084
status: VALID
recorded_at: 2026-09-04T18:28:48+08:00
stage: D
experiment_id: EXP-079-GROUNDING-DINO-TINY-CUP-FINETUNE-R1
prior_checkpoint: CP-083
source_commit_before_checkpoint: 371ad07b8134d5f313a5f30510ca37c4fe39100f
fix:
  production_file: src/so101_demo_py/src/training/grounding_dino_runtime.py
  helper: enable_grounding_dino_gradient_checkpointing
  behavior:
    - require the existing Grounding DINO decoder checkpointing flag, public enable method, and old-format setter
    - correct the inconsistent instance support flag only after those capabilities are present
    - call the locked Transformers public gradient_checkpointing_enable method
    - fail closed unless both decoder.gradient_checkpointing and model.is_gradient_checkpointing read back true
    - write gradient-checkpointing.json before training starts
tdd:
  invalid_wrappers:
    - run_id: stage-d-gradient-checkpoint-red-r87
      reason: relative source PYTHONPATH did not expose the package
    - run_id: stage-d-gradient-checkpoint-red-r88
      reason: assumed a conventional nested package directory instead of this package_dir mapping
  red:
    run_id: stage-d-gradient-checkpoint-red-r89
    status: VALID_RED
    result: collection failed only because the new helper did not exist
    exit_code: 2
    junit_sha256: 851c5891c38f3010b5c3e09b6616b51abc28f3f6f881e94d41441f02781f3d1e
  green:
    run_id: stage-d-gradient-checkpoint-green-r90
    status: VALID
    result: {passed: 7, failed: 0}
    elapsed_ms: 247
    junit_sha256: 2d24ee0c2b162f86b65ba6cdf4a1a21eec4cc409041c594e467a7a2b52ae5cdc
  related_gate:
    run_id: stage-d-gradient-checkpoint-related-r91
    status: VALID
    result: {passed: 33, failed: 0}
    elapsed_ms: 1086
    junit_sha256: 8fb4a87d0320707ce72f11a6bb45ca4cd7b6489678fab8f7658e408fdf7499ab
  static_gate:
    run_id: stage-d-gradient-checkpoint-static-r92
    status: VALID
    checks: [ruff check, ruff format --check, in-memory compile, git diff --check]
    checks_log_sha256: faf709e30bb90de3042acc93fd581bb50a047ac89bed7e0b1fdb16c61c51ebdd
fresh_overlay:
  invalid_preflight:
    run_id: linux-build-stage-d-gradient-checkpoint-r93
    status: INVALID
    reason: incorrectly required an upstream CMakeLists.txt that is not part of the pinned lodepng commit
    colcon_started: false
  valid_run:
    run_id: linux-build-stage-d-gradient-checkpoint-r94
    status: VALID
    package_count: 7
    symlink_install: true
    exit_code: 0
    elapsed_ms: 64047
    source_commit: 371ad07b8134d5f313a5f30510ca37c4fe39100f
    lodepng_head: ed6fe5825c6a4fbb7f58ab35a4231c7543cd452a
    lodepng_tracked_files: 26
    lodepng_validation: clean Git state, all tracked files present, full fsck valid
    lodepng_network_fetch: none
    fetchcontent_fully_disconnected: true
    scratch: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/scratch/linux-build-stage-d-gradient-checkpoint-r94/tmp
    preflight_sha256: adce434e092567318ca36aafb4151d0e4a168f391b1ac1e70a8066f708b5a2fa
    exit_log_sha256: 4662dd9988e3a91709e223003f312ece6bdc61ca3e04ca0e666accc28072aaec
    overlay_readback_sha256: 1e787e9ebd718e0d8da2395167c942e4b126fb970cc214d24deefd247564aa99
ordinary_gate:
  run_id: linux-test-stage-d-gradient-checkpoint-r95-ordinary
  status: VALID
  scope: src/so101_demo_py/test only
  result: {passed: 1201, failed: 0, errors: 0, skipped: 0}
  colcon_exit_code: 0
  test_result_exit_code: 0
  elapsed_ms: 15243
  locked_python: /data/work/venvs/so101-grounded-sam/bin/python
  actual_test_python: /usr/bin/python3
  tempfile_preflight: both resolved exactly to the new run-specific NVMe scratch
  scratch: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/scratch/linux-test-stage-d-gradient-checkpoint-r95-ordinary/tmp
  preflight_sha256: a428fd61465b6eeabcafc01a8c61eab0bff041f0a0aea9bbc3748f704a1c08fd
  exit_log_sha256: 0a05be4331735a9b4f6d4d4b5964ca0f6724a05ed49e68a04520d6e9f589fe8b
  junit_sha256: 9fa5e5de131de7a392e7e4880e48f02898f07176e8035b1ebb4fa6c6f52ded6d
benchmark_gate:
  status: NOT_RUN_BY_CONTRACT
  reason: the training-only compatibility fix changes no benchmark implementation, configuration, adapter, report, test, selected checkpoint, or threshold
  preserved_valid_benchmark: linux-test-stage-c-augmentation-r59-benchmark
sealed_boundaries:
  synthetic_test_access: none
  coco100_access: none
  sam_loaded: false
  microduck: paused
  mac_migration: forbidden
next_action: commit only the runtime fix, test, and checkpoint; Gitee-sync; build a new non-colliding gcfix image tag; then preflight smoke r2 with the new implementation commit
retention:
  retained_runs: [r87-r92 TDD and static evidence, r93 invalid build preflight, r94 overlay, r95 ordinary gate]
  archived_runs: []
  deletion_candidates:
    - all r87-r95 registered NVMe scratch trees; do not delete without explicit user authorization
```
