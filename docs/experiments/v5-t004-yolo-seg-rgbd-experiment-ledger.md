# V5-T004 YOLO-Seg RGB-D experiment ledger

```yaml
task_id: so101-v5-t004-yolo-seg-rgbd
goal: 在 macOS MPS 与 ai-station CUDA 上从多物体 MuJoCo RGB-D 选择唯一 plastic_cup，发布新鲜 /cup_pose，并复用现有动态执行链完成仿真 pick&place
success_contract: 同一 best.pt 在两平台通过四场景感知矩阵，随后每平台固定 commit/权重/参数的 FULL_RESTART MuJoCo pick&place 连续 5 次成功
worktree: /Users/matianyi/.codex/worktrees/5b15/moveit-demo
branch: codex/v5-t004-yolo-seg-rgbd
base_commit: f09cf88cf55352f4bf618d44a8ff6c6885419c8d
current_commit: 23cc6e1
evidence_root: /tmp/so101-debug-v5-t004-yolo-seg-20260831
confirmed_conclusions:
  - CONF-001 现有颜色阈值加最大 DBSCAN 聚类没有实例类别语义，来自设计文档与 f09cf88 源码检查
  - CONF-002 当前 macOS 与 ai-station Python 环境均未安装 torch/ultralytics/mujoco Python binding，来自 2026-08-31 双平台 import probe
  - CONF-003 ai-station NVIDIA 用户态 595.84 与已加载内核模块 595.71.05 不一致，nvidia-smi 当前失败
disproven_routes:
  - DISPROVED-001 不允许用最大同色聚类或 MuJoCo truth ID 作为生产目标分类器
  - DISPROVED-002 不允许用 CPU smoke 代替 macOS MPS 或 Linux CUDA 正式验收
open_hypotheses:
  - HYP-001 object-ID 合成数据训练的 yolo11n-seg 可在四场景达到 mask IoU 0.80
  - HYP-002 新鲜 YOLO /cup_pose 可直接复用现有 dynamic pick-place consumer
latest_checkpoint: CP-002
next_experiment: EXP-002
```

## Checkpoints

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
