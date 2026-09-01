# V5-T005 Grounding DINO Tiny + SAM 2.1 RGB-D experiment ledger

```yaml
task_id: so101-v5-t005-grounded-sam-rgbd
goal: 在 macOS MPS 与 ai-station CUDA 上使用 Grounding DINO Tiny 和 SAM 2.1 Hiera Tiny，从多物体 MuJoCo RGB-D 中选择唯一 plastic_cup，发布新鲜 /cup_pose，并完成仿真 pick&place
success_contract: 两个平台以同一 commit、模型包 SHA 和阈值通过四场景感知矩阵，随后各自 FULL_RESTART 连续 5 次 pick&place 成功
worktree: /Users/matianyi/.codex/worktrees/5b15/moveit-demo
branch: codex/v5-t004-yolo-seg-rgbd
base_commit: b55c869c919cd673bf84be8b125cc55a8e6eb98f
current_qualification_commit: 6242fe967c0574e9175965a7e5790aecb9d427f5
guide_fix_commit: 9450fd77504e4719ca9b6b351cbb4068f81eeb0d
ledger_baseline_commit: c777f58fc29c6b1e0f7493f3d98032499b4b8052
repository_head_at_fix_round_2_qualification: 6242fe967c0574e9175965a7e5790aecb9d427f5
ledger_record_commit: 本字段所在提交；提交完成后的精确 SHA 记录在 Task 9 report，不将 guide commit 或资格 commit 冒充 ledger commit
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
  - CONF-008 EXP-004 修正固定错误码、依赖锁、离线环境门禁和 Linux ros2 前缀测试后，macOS 与 ai-station 分别通过 229 项定向测试和 1044 项整包测试
  - CONF-009 EXP-005 删除 verifier 的调用方依赖覆盖入口后，macOS 与 ai-station 分别通过 230 项定向测试和 1045 项整包测试
open_hypotheses:
  - HYP-001 Grounding DINO Tiny 对受控提示词 plastic cup. 能在四个 MuJoCo 场景中满足候选数量与类别门槛
  - HYP-002 SAM 2.1 Hiera Tiny 的框提示 mask 在两个平台都能达到 truth IoU >= 0.80
  - HYP-003 两阶段 warmed request latency 在两个平台都能 <= 2000 ms
  - HYP-004 新 detector 接入后，两个平台可以分别完成 FULL_RESTART 连续 5/5 pick&place
latest_checkpoint: CP-004
next_experiment: EXP-006 由 Task 10 在获准安装锁定依赖后构建真实 bundle，并运行 MPS/CUDA 离线 smoke
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
