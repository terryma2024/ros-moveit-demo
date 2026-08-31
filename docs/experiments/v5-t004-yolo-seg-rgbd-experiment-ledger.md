# V5-T004 YOLO-Seg RGB-D experiment ledger

```yaml
task_id: so101-v5-t004-yolo-seg-rgbd
goal: 在 macOS MPS 与 ai-station CUDA 上从多物体 MuJoCo RGB-D 选择唯一 plastic_cup，发布新鲜 /cup_pose，并复用现有动态执行链完成仿真 pick&place
success_contract: 同一 best.pt 在两平台通过四场景感知矩阵，随后每平台固定 commit/权重/参数的 FULL_RESTART MuJoCo pick&place 连续 5 次成功
worktree: /Users/matianyi/.codex/worktrees/5b15/moveit-demo
branch: codex/v5-t004-yolo-seg-rgbd
base_commit: f09cf88cf55352f4bf618d44a8ff6c6885419c8d
current_commit: 6bb16778d053a8bd9bb67c71fd0a1430b94ba2aa
evidence_root: /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88
development_source_root: /tmp/so101-debug-v5-t004-yolo-seg-20260831
migration_manifest: /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/migration-manifest.json
confirmed_conclusions:
  - CONF-001 现有颜色阈值加最大 DBSCAN 聚类没有实例类别语义，来自设计文档与 f09cf88 源码检查
  - CONF-002 当前 macOS 与 ai-station Python 环境均未安装 torch/ultralytics/mujoco Python binding，来自 2026-08-31 双平台 import probe
  - CONF-003 ai-station NVIDIA 用户态 595.84 与已加载内核模块 595.71.05 不一致，nvidia-smi 当前失败
  - CONF-022 EXP-007 授权重启后 NVIDIA 内核模块、NVML 与磁盘模块统一为 595.84，nvidia-smi 与 RTX 5080 CUDA 张量 gate 通过
disproven_routes:
  - DISPROVED-001 不允许用最大同色聚类或 MuJoCo truth ID 作为生产目标分类器
  - DISPROVED-002 不允许用 CPU smoke 代替 macOS MPS 或 Linux CUDA 正式验收
open_hypotheses:
  - HYP-001 object-ID 合成数据训练的 yolo11n-seg 可在四场景达到 mask IoU 0.80
  - HYP-002 新鲜 YOLO /cup_pose 可直接复用现有 dynamic pick-place consumer
latest_checkpoint: CP-008
next_experiment: EXP-008
```

## Checkpoints

```yaml
checkpoint_id: CP-008
last_valid_experiment: EXP-007
current_hypothesis: HYP-001
working_tree_status: 本地任务分支仅有本轮 EXP-007 结论待提交；ai-station 主 checkout 用户账本和隔离 worktree均保持原样
owned_processes: NONE；重启后没有遗留 Gazebo、MoveIt、RViz 或 ROS pick-place stack
preserved_processes: 重启前 codex/codex-cua 窗格快照已保留；重启后旧 tmux server 不存在，不伪造续接；GNOME/Xorg 已恢复
confirmed_conclusions:
  - CONF-022 新 boot 为 2026-08-31 20:40:08，NVIDIA kernel/modinfo/NVML 均为 595.84，nvidia-smi exit 0
  - CONF-023 torch 2.13.0+cu130 在 RTX 5080 上 cuda_available=true，实际张量 sum=140.0
  - CONF-024 主 checkout 用户账本、隔离 worktree、migration manifest 与全部重启前证据 SHA 均保留
open_risks:
  - 训练参数能否被 Ultralytics 8.4.115 接受、best.pt 是否达到四场景 IoU/延迟门槛仍未观察
next_command: 在不启动训练的前提下校验 training.yaml、dataset.yaml 与 Ultralytics 8.4.115 参数契约
```

```yaml
checkpoint_id: CP-007
last_valid_experiment: EXP-006
current_hypothesis: HYP-003
working_tree_status: 本地任务分支 clean at a8cd693；ai-station 主 checkout 保留一个未跟踪用户账本，隔离 worktree clean at 867df72
owned_processes: NONE；重启前没有 gz sim、move_group、rviz2、pick_place_state_machine、ros2 launch 或 ros2 run
preserved_processes: codex 与 codex-cua 均为空闲提示符；重启会终止 tmux server，完整窗格恢复快照已写入 EXP-007 证据目录；Xorg/GNOME/hiddify 属于共享桌面
confirmed_conclusions:
  - CONF-020 用户已明确授权选项 2，即协调重启共享 ai-station
  - CONF-021 重启前加载模块为 595.71.05、磁盘模块与 NVML 为 595.84，nvidia-smi 报 driver/library version mismatch
open_risks:
  - 重启是否加载 595.84 尚未观察；主机、桌面或 SSH 未恢复则 EXP-007 不得计为有效 CUDA 修复
next_command: ssh ai-station 'sudo -n systemctl reboot'
```

```yaml
checkpoint_id: CP-006
last_valid_experiment: EXP-006
current_hypothesis: HYP-001
working_tree_status: 分支已推送且本地/远端 SHA 一致；Linux 隔离 worktree 已完成聚焦测试与 renderer smoke
owned_processes: NONE
preserved_processes: ai-station 未重启；原 checkout 未跟踪账本与现有 tmux/桌面进程保持原状
confirmed_conclusions:
  - CONF-017 Gitee origin/codex/v5-t004-yolo-seg-rgbd 与本地均为 867df726be0de8dbbae3ca58fb7c3323379853b1
  - CONF-018 ai-station 隔离 worktree 的 93 个感知、launch 与 source-layout 聚焦测试通过
  - CONF-019 Linux MuJoCo EGL 生成 12 张真实 smoke 样本成功，0/1/2 分布 3/6/3；EGL 报告 DRI2 warning 但工件完整
open_risks:
  - 用户未授权重启，nvidia-smi gate 未通过，因此训练、真实 best.pt 和双平台 ROS/pick-place 均未开始
next_command: 等待 ai-station 重启授权；授权后先验证 nvidia-smi，再训练，不跳过 gate
```

```yaml
checkpoint_id: CP-005
last_valid_experiment: EXP-005
current_hypothesis: HYP-001
working_tree_status: Task 1-6 和 Task 7 配置已提交；完整数据集与 Mac package gate 通过，待提交账本/配置小修并推送
owned_processes: NONE
preserved_processes: ai-station 未重启；Xorg/GNOME/hiddify、codex/codex-cua tmux 与主 checkout 保持原状
confirmed_conclusions:
  - CONF-014 正式数据集精确包含 800 train、200 val、200 test，3602 个文件、58528703 bytes，checksum dry-run 无差异
  - CONF-015 正式数据集 0/1/2 可见实例分布为 300/600/300，类别实例总数 1200
  - CONF-016 锁定子模块作为隔离 worktree 物化后，Mac package gate 为 885 passed、2 个第三方 deprecation warnings
open_risks:
  - 用户仅授权推送选项 1，未授权 ai-station 重启；Linux driver gate 和训练继续等待
next_command: 推送 codex/v5-t004-yolo-seg-rgbd 到 Gitee origin，随后在 ai-station 创建隔离 worktree 并跑 Linux source tests
```

```yaml
checkpoint_id: CP-004
last_valid_experiment: EXP-004
current_hypothesis: HYP-001
working_tree_status: Task 1-6 已提交；Task 7 依赖锁、训练配置和 overlay 标签已通过聚焦测试，待 Linux driver gate 与训练
owned_processes: NONE
preserved_processes: ai-station Xorg/GNOME/hiddify 与 codex/codex-cua tmux 会话；主 checkout 和本地 development source root 未删除
confirmed_conclusions:
  - CONF-010 开发证据 15 个 payload、36945 bytes 已迁移到正式根并逐文件核对 SHA256 与大小，源根保留
  - CONF-011 macOS 精确应用版本安装成功；沙箱外 torch MPS built=true available=true
  - CONF-012 MuJoCo 3.12.0 编译 fixture 成功，12 张真实 smoke 样本为 3 个零杯、6 个单杯、3 个双杯，已 checksum 同步到正式根
  - CONF-013 Linux torch 2.13.0+cu130 在 RTX 5080 上完成 CUDA 张量计算，但 nvidia-smi 仍因 595.84/595.71.05 mismatch 失败
open_risks:
  - Linux 正式 gate 要求 nvidia-smi 和 torch.cuda 同时通过；共享主机重启需要用户授权与会话协调
  - 1200 张正式数据和训练尚未开始
next_command: 经用户授权后协调 ai-station 重启，再运行 nvidia-smi 与 CUDA tensor gate
```

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-002
current_hypothesis: HYP-001
working_tree_status: Task 1-5 已提交；Task 6 object-ID 数据生成器、CLI、fixture 与配置通过源码测试，待提交
owned_processes: NONE
preserved_processes: ai-station codex 与 codex-cua tmux 会话；主 checkout 与 ai-station 未跟踪实验账本未修改
confirmed_conclusions:
  - CONF-007 固定 seed 范围 train=100000、val=200000、test=300000 起始且互不重叠
  - CONF-008 标签由 geom ID 经 geom_bodyid 映射到 plastic_cup body，改变 RGB 材质颜色不改变 polygon
  - CONF-009 相同配置和 fake renderer 两次生成的 manifest、PNG、label 与 truth 工件逐字节一致
open_risks:
  - MuJoCo Python binding 尚未安装，真实 fixture compile 和 12 样本 renderer smoke 尚未执行
  - prediction overlay 仍需在验收前加入可见类别与置信度文字
  - Linux CUDA 仍受 driver/library mismatch 阻塞
next_command: PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_perception_dependency_lock.py -q
```

```yaml
checkpoint_id: CP-002
last_valid_experiment: EXP-001
current_hypothesis: HYP-001
working_tree_status: Task 1-4 已提交；Task 5 ROS/CLI/launch 集成通过工作树测试，待提交
owned_processes: NONE
preserved_processes: ai-station codex 与 codex-cua tmux 会话；主 checkout 与 ai-station 未跟踪实验账本未修改
confirmed_conclusions:
  - CONF-004 检测契约、目标歧义门禁、mask-only RGB-D 定位和一次性证据流已通过 70 个聚焦测试
  - CONF-005 ROS CLI/节点与双 backend launch 集成通过 79 个聚焦测试；yolo_seg 路径只创建一个 /cup_pose publisher
  - CONF-006 ROS overlay source 之后必须最后注入工作树 PYTHONPATH，否则测试会错误导入旧安装
disproven_routes:
  - DISPROVED-003 不把旧 install overlay 的 ModuleNotFoundError 当作工作树源码缺失
open_risks:
  - prediction overlay 仍需在验收前加入可见类别与置信度文字
  - 共享 ai-station 的 CUDA 修复可能需要协调重启
  - Task 7 前必须迁移唯一证据根到持久存储
next_command: PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_yolo_seg_dataset.py -q
```

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: HYP-001
working_tree_status: 仅新增计划与本账本；主 checkout 和 ai-station 用户文件保持不动
owned_processes: NONE
preserved_processes: ai-station codex 与 codex-cua tmux 会话；/data/work/ws_moveit/docs/experiments/ai-station-linux-headless-rgbd-four-point-upgrade-experiment-ledger.md
confirmed_conclusions:
  - CONF-001 颜色与最大聚类不是实例分类
  - CONF-002 双平台缺少模型和 Python 感知依赖
  - CONF-003 Linux NVIDIA driver/library mismatch 阻塞 CUDA
disproven_routes:
  - DISPROVED-001 不用 color/largest-cluster 冒充类别选择
  - DISPROVED-002 不用 CPU 冒充正式平台加速器验收
open_risks:
  - 共享 ai-station 的 CUDA 修复可能需要协调重启
  - 1200 张合成数据训练是否达到 IoU 与延迟门槛尚未观察
  - Task 7 前必须按 hash/size/count 将唯一证据根迁移到持久存储
next_command: PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_detection_contracts.py src/so101_demo_py/test/test_target_selector.py -q
```

## Experiments

```yaml
experiment_id: EXP-007
status: VALID
prior_experiment: EXP-004
hypothesis: ai-station 完整重启将以磁盘上的 NVIDIA 595.84 替换当前已加载的 595.71.05，从而消除 NVML driver/library version mismatch
prediction: 重启后 /proc/driver/nvidia/version 与 modinfo 均为 595.84，nvidia-smi 退出 0，锁定 venv 中 torch.cuda 可用且 RTX 5080 张量计算得到 sum=140.0
single_variable: 主机生命周期从当前 19 天 uptime 变为一次授权的完整重启；不改驱动包、模型、数据或源码
lifecycle: FULL_RESTART
preconditions:
  - 用户明确授权选项 2
  - sudo -n true 退出 0
  - 没有运行中的 Gazebo、MoveIt、RViz 或 ROS pick-place stack
  - 主 checkout 未跟踪用户账本、隔离 worktree、venv、数据集与正式证据根均已记录且不清理
  - codex 与 codex-cua tmux 窗格已保存恢复快照，不向既有窗格发送按键
success_criteria:
  - 主机在重启后重新可通过 SSH 访问，uptime 表明发生了新 boot
  - /proc/driver/nvidia/version 与 modinfo -F version nvidia 均报告 595.84
  - nvidia-smi 退出 0 并识别 RTX 5080
  - /data/work/venvs/so101-v5-t004-perception 中 torch.cuda.is_available() 为 true，实际 CUDA 张量 sum=140.0
  - 主 checkout 用户文件、隔离 worktree和正式 evidence root 在重启后仍存在
failure_criteria:
  - 主机恢复但 NVIDIA 版本仍不一致、nvidia-smi 非零或 CUDA 张量失败
invalid_criteria:
  - 主机未在有界等待内恢复，或关键工作区/证据丢失，导致无法判断单一变量的结果
provenance:
  source_commit: 867df726be0de8dbbae3ca58fb7c3323379853b1
  install_overlay: /data/work/ws_moveit-v5-t004/install
  runtime_executable: /data/work/venvs/so101-v5-t004-perception/bin/python
  ros_domain_id: 0
  gz_partition: NONE
commands:
  - command: ssh ai-station 'sudo -n systemctl reboot'
    exit_code: 0
observed:
  - 2026-08-31T20:35:50+08:00 重启前 uptime 19 days 23:52；加载 NVIDIA 595.71.05、磁盘模块 595.84、NVML 595.84
  - 重启前主 checkout 唯一 dirty path 为 docs/experiments/ai-station-linux-headless-rgbd-four-point-upgrade-experiment-ledger.md
  - 重启前 tmux 恢复快照保存在正式 evidence root
  - 重启命令执行前已核验 source commit、venv、证据根、sudo、进程所有权与用户 dirty path，实验进入 RUNNING
  - 2026-08-31T20:43:19+08:00 uptime 3 min，boot time 为 2026-08-31 20:40:08
  - /proc/driver/nvidia/version 与 modinfo 均为 595.84；nvidia-smi exit 0，识别 NVIDIA GeForce RTX 5080
  - torch 2.13.0+cu130 报 cuda_available=true，RTX 5080 上 arange(8) 平方和为 140.0
  - 主 checkout 用户账本、隔离 worktree、migration manifest 与重启前 3 个证据文件 SHA 校验全部通过
  - 重启后旧 tmux server 不存在；这符合重启语义，恢复所需的两个窗格快照已保留，未冒充自动续接
inferred:
  - 重启后首先在驱动加载边界消除了 595.71.05/595.84 分叉，且 NVML 与 CUDA 同时恢复，支持“驱动包升级后未重启”为已确认根因
conclusion: CONFIRMED；完整重启加载 595.84 并恢复了 nvidia-smi 与 CUDA 正式训练 gate
evidence:
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/reboot/exp-007/pre-reboot-state.txt
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/reboot/exp-007/pre-reboot-sha256.txt
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/reboot/exp-007/tmux-codex-pre-reboot.txt
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/reboot/exp-007/tmux-codex-cua-pre-reboot.txt
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/reboot/exp-007/post-reboot-state.txt
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/reboot/exp-007/cuda-tensor-post-reboot.txt
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/reboot/exp-007/post-reboot-sha256.txt
decision: KEEP
next_experiment: EXP-008
```

```yaml
experiment_id: EXP-006
status: PASS_WITH_DRIVER_WARNING
scope: Gitee publication readback and Linux isolated source/renderer smoke
remote_branch_sha: 867df726be0de8dbbae3ca58fb7c3323379853b1
linux_worktree: /data/work/ws_moveit-v5-t004
focused_tests: 93 passed
dataset_smoke:
  sample_count: 12
  visible_instance_distribution: {zero: 3, one: 6, two: 3}
  copied_file_count: 38
  copy_diff: clean
warning: MuJoCo EGL emitted DRI2 screen warnings while still producing complete samples
decision: renderer smoke accepted; CUDA training remains blocked by nvidia-smi gate
```

```yaml
experiment_id: EXP-005
status: PASS
scope: full dataset generation and macOS package gate
dataset:
  generator_commit: 2be8df09302feabffc7f028b16c90d06867f8055
  sample_count: 1200
  split_counts: {train: 800, val: 200, test: 200}
  visible_instance_distribution: {zero: 300, one: 600, two: 300}
  class_instance_total: 1200
  remote_file_count: 3602
  remote_byte_size: 58528703
  checksum_sync: PASS
mac_package_gate:
  result: 885 passed
  warnings: 2 third-party deprecation warnings
  junit: /tmp/so101-v5-t004-package-gate-macos/so101_demo_py-pytest.xml
  initial_false_failures: 4 failures from unmaterialized locked submodule; all passed after isolated submodule worktree at 71bc934
```

```yaml
experiment_id: EXP-004
status: PARTIAL_PASS
scope: pinned dependency and accelerator smoke
macos:
  python: 3.11.15
  torch: 2.13.0
  torchvision: 0.28.0
  ultralytics: 8.4.115
  mujoco: 3.12.0
  mps_built: true
  mps_available_outside_sandbox: true
linux:
  python: 3.12.3
  torch: 2.13.0+cu130
  torchvision: 0.28.0+cu130
  ultralytics: 8.4.115
  mujoco: 3.12.0
  cuda_tensor_smoke: RTX 5080 sum=140.0
  nvidia_smi: FAIL driver/library version mismatch
decision: 不训练；正式 Linux gate 未满足
```

```yaml
experiment_id: EXP-003
status: PASS
scope: development evidence migration
source_root: /tmp/so101-debug-v5-t004-yolo-seg-20260831
destination_root: /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88
payload_file_count: 15
payload_byte_size: 36945
verification: every relative path SHA256 and byte size matched remotely; source root and excluded symlinks retained
```

```yaml
experiment_id: EXP-002
status: PASS_WITH_DEFERRED_RUNTIME
scope: Task 6 deterministic dataset source contracts on macOS
result: 11 dataset tests plus XML syntax and 3 source-layout tests passed; compileall passed
evidence:
  - seed plans are disjoint
  - 0/1/2 target instances are retained separately
  - RGB color changes do not affect object-ID polygons
  - repeated fake-renderer datasets are byte-identical
deferred: real MuJoCo model compile and 12-sample render wait for Task 7 isolated dependency install
artifacts: source tests only; no real rendered sample or trained model claimed
```

```yaml
experiment_id: EXP-001
status: PASS
scope: Task 1-5 source and launch contract tests on macOS
command_contract: source ROS overlays, then prepend /tmp/so101-debug-v5-t004-yolo-seg-20260831/python to PYTHONPATH, set ROS_HOME and ROS_LOG_DIR under the registered evidence root, disable external pytest plugins
result: 79 passed, 2 third-party deprecation warnings; compileall passed
failure_injection:
  - missing worktree PYTHONPATH after overlay sourcing reproduced stale-install ModuleNotFoundError
  - symlink model weights rejected by both launch/options and YOLO adapter
artifacts: source tests only; no runtime RGB-D or pick-place evidence claimed
```
