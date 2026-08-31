# V5-T004 YOLO-Seg RGB-D experiment ledger

```yaml
task_id: so101-v5-t004-yolo-seg-rgbd
goal: 在 macOS MPS 与 ai-station CUDA 上从多物体 MuJoCo RGB-D 选择唯一 plastic_cup，发布新鲜 /cup_pose，并复用现有动态执行链完成仿真 pick&place
success_contract: 同一 best.pt 在两平台通过四场景感知矩阵，随后每平台固定 commit/权重/参数的 FULL_RESTART MuJoCo pick&place 连续 5 次成功
worktree: /Users/matianyi/.codex/worktrees/5b15/moveit-demo
branch: codex/v5-t004-yolo-seg-rgbd
base_commit: f09cf88cf55352f4bf618d44a8ff6c6885419c8d
current_commit: f92b0ac834382b6a3095d1885d7449c6c19e57db
evidence_root: /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88
development_source_root: /tmp/so101-debug-v5-t004-yolo-seg-20260831
migration_manifest: /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/migration-manifest.json
confirmed_conclusions:
  - CONF-001 现有颜色阈值加最大 DBSCAN 聚类没有实例类别语义，来自设计文档与 f09cf88 源码检查
  - CONF-002 当前 macOS 与 ai-station Python 环境均未安装 torch/ultralytics/mujoco Python binding，来自 2026-08-31 双平台 import probe
  - CONF-003 ai-station NVIDIA 用户态 595.84 与已加载内核模块 595.71.05 不一致，nvidia-smi 当前失败
  - CONF-022 EXP-007 授权重启后 NVIDIA 内核模块、NVML 与磁盘模块统一为 595.84，nvidia-smi 与 RTX 5080 CUDA 张量 gate 通过
  - CONF-034 EXP-011 预置锁定字体后，amp=false 与 YOLO_OFFLINE=true 的 CUDA smoke 零自动下载、退出 0 并生成完整训练工件
  - CONF-036 EXP-012 完成 100 epoch 全量训练；test mask precision 0.9997、recall 1.0、mAP50 0.995、mAP50-95 0.9737
  - CONF-039 EXP-015 在 Linux CUDA 上经生产 TargetSelector 以 confidence 0.50 从 296 个 raw candidates 唯一选中 plastic_cup，推理 37.58 ms
  - CONF-040 EXP-016 在 macOS MPS 上以同一权重和输入唯一选中 plastic_cup，推理 447.77 ms，mask 与 Linux 均为 5053 pixels
  - CONF-042 多物体 MJCF keyframe 已加入公共 MuJoCo launch 白名单；RED 后聚焦 64/64、包级 889/889 通过
disproven_routes:
  - DISPROVED-001 不允许用最大同色聚类或 MuJoCo truth ID 作为生产目标分类器
  - DISPROVED-002 不允许用 CPU smoke 代替 macOS MPS 或 Linux CUDA 正式验收
open_hypotheses:
  - HYP-001 object-ID 合成数据训练的 yolo11n-seg 可在四场景达到 mask IoU 0.80
  - HYP-002 新鲜 YOLO /cup_pose 可直接复用现有 dynamic pick-place consumer
latest_checkpoint: CP-019
next_experiment: EXP-017
```

## Checkpoints

```yaml
checkpoint_id: CP-019
last_valid_experiment: EXP-016
current_hypothesis: 修复 keyframe launch 白名单后可预登记并启动 8 个真实 ROS RGB-D 场景
working_tree_status: launch_composition.py、对应测试与本账本待提交；其余无用户改动
owned_processes: NONE
preserved_processes: 所有正式与无效证据保留；ai-station 用户文件未触碰
confirmed_conclusions:
  - CONF-042 v5_no_cup、v5_two_cups、v5_cup_near_bottle 原先被公共 launch 白名单拒绝；新增契约先 RED 后 GREEN
  - CONF-043 设置任务专属 ROS_LOG_DIR 后 launch 聚焦 64/64、so101_demo_py 包级 889/889 通过
disproven_routes:
  - DISPROVED-007 未设置 ROS_LOG_DIR 的 sandbox 测试会因 ~/.ros/log 无写权限产生 58 个环境失败，不能解释为产品回归
open_risks:
  - 安装态尚未重建，8 个场景实验尚未预登记或启动
next_command: 提交白名单修复，随后为 macOS/Linux x 四场景登记 EXP-017 至 EXP-024
```

```yaml
checkpoint_id: CP-018
last_valid_experiment: EXP-016
current_hypothesis: 同一权重已通过 CUDA/MPS adapter 与 selector，下一边界是真实 ROS RGB-D 四场景定位
working_tree_status: 仅有 EXP-016 有效结论待提交；remote source clean at 35db5f5
owned_processes: NONE；Mac MPS probe 正常退出，受控 process readback 无残留
preserved_processes: Linux/Mac platform smoke、训练、无效探针全部保留；用户文件未触碰
confirmed_conclusions:
  - CONF-040 Mac runtime_device=mps、raw_count=296、eligible_count=1、confidence=0.970541、mask_pixels=5053、inference=447.77 ms
  - CONF-041 Mac result/stdout/probe/hash manifest 已同步到正式 evidence root，远端逐文件 SHA 回读一致
open_risks:
  - adapter smoke 尚未证明真实 ROS RGB-D、深度定位、/cup_pose、四场景 fail-closed 与 GUI/cleanup
next_command: 按 Task 8 先预登记 macOS/Linux 各四个 FULL_RESTART 场景实验，再逐场执行
```

```yaml
checkpoint_id: CP-017
last_valid_experiment: EXP-015
current_hypothesis: 同一权重在 Mac MPS 上也可经生产 selector 唯一选中 plastic_cup
working_tree_status: 仅有本次 EXP-015 有效结论待提交；remote source clean at 35db5f5
owned_processes: NONE；Linux CUDA detector/selector probe 正常退出
preserved_processes: EXP-013 无效 raw 输出、EXP-015 有效结果与所有训练工件均保留
confirmed_conclusions:
  - CONF-039 EXP-015 runtime_device=cuda、raw_count=296、eligible_count=1、selected confidence=0.970513、mask_pixels=5053、inference=37.58 ms
open_risks:
  - Mac MPS 尚未对同一权重与同一输入执行 detector/selector 验证
next_command: 核对并复制 best.pt 与 seed 300001 到 Mac staging，随后执行 EXP-016 MPS probe
```

```yaml
checkpoint_id: CP-016
last_valid_experiment: EXP-012
current_hypothesis: 生产 selector 在 confidence 0.50 后可从 raw YOLO candidates 唯一选出 plastic_cup
working_tree_status: 本地仅有 EXP-013/014 无效结论与修正后计划待提交；remote source clean at 35db5f5
owned_processes: NONE；Linux probe 已退出
preserved_processes: EXP-013 98629-byte raw result 与 SHA 保留；不覆盖原 platform-smoke/linux
confirmed_conclusions:
  - CONF-038 seed 300001 raw batch 为 296 candidates，但只有 1 个 confidence>=0.50，confidence=0.970513、mask_pixels=5053
disproven_routes:
  - DISPROVED-006 不能在 DetectorPort raw batch 边界断言 candidate_count=1；唯一性属于 TargetSelector 阈值后边界
open_risks:
  - 修正探针尚未调用 TargetSelector 并在 CUDA/MPS 双平台正式通过
next_command: 用预创建输出目录的 EXP-015 Linux probe 记录 raw/eligible/selected 三层，再执行 EXP-016 Mac MPS
```

```yaml
checkpoint_id: CP-015
last_valid_experiment: EXP-012
current_hypothesis: 同一 f281d252 best.pt 可在 Linux CUDA 与 Mac MPS adapter 上得到唯一 plastic_cup mask
working_tree_status: 本地仅有 EXP-012 结论与双平台 smoke 计划待提交；remote source clean at 35db5f5
owned_processes: NONE；全量训练与 test eval均结束
preserved_processes: 全量训练/测试、所有 smoke/invalid 工件、数据、base model、字体资产均保留
confirmed_conclusions:
  - CONF-036 full training/test exit 0，best.pt 6001316 bytes，SHA256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  - CONF-037 test mask precision=0.999735、recall=1.0、mAP50=0.995、mAP50-95=0.973662；model inference约0.976 ms/image
open_risks:
  - 真实 YoloSegDetector 在 CUDA/MPS 的候选转换、mask尺寸与同权重 hash尚未实测
next_command: 对固定 test seed 300001 分别执行 EXP-013 CUDA 与 EXP-014 MPS adapter smoke
```

```yaml
checkpoint_id: CP-014
last_valid_experiment: EXP-011
current_hypothesis: HYP-001
working_tree_status: 本地仅有 EXP-011 结论与 EXP-012 计划待提交；remote source clean at 35db5f5
owned_processes: NONE；EXP-011 正常退出且没有训练进程
preserved_processes: EXP-008/009/010/011 全部工件保留；字体资产与 provenance hash 保留
confirmed_conclusions:
  - CONF-034 EXP-011 exit 0，CUDA RTX 5080、amp=false、offline、无 forbidden download marker
  - CONF-035 EXP-011 best.pt 与 last.pt 各 5982884 bytes，关键配置、结果和日志均有 SHA256
open_risks:
  - 全 800 train/200 val、100 epochs 是否收敛以及 test split 指标尚未观察
next_command: 预登记 EXP-012 后用相同 envelope 生成 full-exp-012 配置并启动全量训练
```

```yaml
checkpoint_id: CP-013
last_valid_experiment: EXP-007
current_hypothesis: 预置 hash 锁定的本机 TTF 可满足 Ultralytics 无条件 check_font 而不联网
working_tree_status: 本地仅有 EXP-010 结论与 EXP-011 计划待提交；远端 source clean at 35db5f5
owned_processes: NONE；EXP-010 已中断且没有训练进程
preserved_processes: 114688-byte Arial.ttf partial 已移入 EXP-010 目录并哈希；不删除
confirmed_conclusions:
  - CONF-032 YOLO_OFFLINE=true 禁止 PyPI update check，但 Ultralytics check_det_dataset 仍无条件调用 check_font 并下载 Arial.ttf
  - CONF-033 本机 DejaVuSans.ttf 为 759720 bytes，SHA256 ae7b7855e115a5966d8b1b3f80f254ccc117ec86f9965e202ee2940453837280b，可作为显式预置绘图字体
disproven_routes:
  - DISPROVED-005 YOLO_OFFLINE=true 单独不能保证训练零下载，因为字体路径不遵守 offline gate
open_risks:
  - 预置本机字体后是否完成零下载训练仍未验证
next_command: 预登记 EXP-011，复制并哈希本机 DejaVuSans.ttf 为 config Arial.ttf，再用独立 output root复验
```

```yaml
checkpoint_id: CP-012
last_valid_experiment: EXP-007
current_hypothesis: YOLO_OFFLINE=true 加正确退出码 wrapper 可形成合格的 amp=false CUDA smoke
working_tree_status: 本地仅有 EXP-009 结论与 EXP-010 计划待提交；ai-station source 仍 clean at 35db5f5
owned_processes: NONE；EXP-009 tmux 已自然结束且没有 yolo 训练进程
preserved_processes: EXP-009 完整权重、指标、日志和哈希保留；不覆盖、不删除
confirmed_conclusions:
  - CONF-030 EXP-009 实际以 amp=False、CUDA:0 RTX 5080 完成 1 epoch 并生成 5982884-byte best.pt/last.pt，日志无 Downloading
  - CONF-031 Ultralytics 支持 YOLO_OFFLINE=true；EXP-009 wrapper 将真实 code 0 错写为 n 0，不能作为严格退出码证据
open_risks:
  - 修正后的 offline wrapper 尚未复验；EXP-009 因预登记判据与 exit-code 污染不能计数
next_command: 准备独立 smoke-exp-010，使用 YOLO_OFFLINE=true 与 echo 精确写 exit-code.txt 后复验
```

```yaml
checkpoint_id: CP-011
last_valid_experiment: EXP-007
current_hypothesis: 冻结 amp=false 可绕过未锁定 AMP model download，并完成真实 CUDA smoke
working_tree_status: 本地任务分支 clean at 35db5f5；ai-station 隔离 worktree clean detached at 同一 commit
owned_processes: NONE；没有训练或 ROS stack
preserved_processes: EXP-008 全部配置、日志与 516096-byte partial 保留；新实验使用独立 smoke-exp-009
confirmed_conclusions:
  - CONF-029 training.yaml amp=false 经 RED/GREEN、Mac package 888/888 与 Linux focused 16/16 验证
open_risks:
  - Ultralytics 实际训练是否完全不触发网络并生成 smoke 权重仍未观察
next_command: 预登记 EXP-009 后准备唯一 output root 并启动 1 epoch、fraction 0.05 CUDA smoke
```

```yaml
checkpoint_id: CP-010
last_valid_experiment: EXP-007
current_hypothesis: HYP-001
working_tree_status: 本地任务分支仅有 EXP-008 无效结论待提交；远端 25680ad 隔离 worktree未修改
owned_processes: NONE；v5-t004-train-exp008 已中断退出，未留下 yolo 训练进程
preserved_processes: 516096-byte 禁止下载的 yolo26n.pt partial 已从 /home/lenovo 移入 EXP-008 证据目录并计算 SHA；未删除
confirmed_conclusions:
  - CONF-028 runtime 配置与 dataset 路径门通过，但 Ultralytics 8.4.115 在 amp=true 自检阶段主动联网下载 yolo26n.pt
disproven_routes:
  - DISPROVED-004 不可直接使用 Ultralytics 默认 amp=true，因为其 AMP check 会在运行时引入未锁定自动下载
open_risks:
  - 冻结 amp=false 是否完全绕过下载并完成训练尚未验证
next_command: 先为 training.yaml 增加 amp=false 的 RED/GREEN contract，再预登记 EXP-009
```

```yaml
checkpoint_id: CP-009
last_valid_experiment: EXP-007
current_hypothesis: HYP-001
working_tree_status: 训练配置归一化修复已提交并推送为 25680ad；ai-station 隔离 worktree clean detached at 25680ad
owned_processes: NONE；尚未启动训练
preserved_processes: ai-station 主 checkout 用户账本保持不变；正式 dataset/base model/reboot evidence 不覆盖
confirmed_conclusions:
  - CONF-025 Ultralytics 8.4.115 明确拒绝项目元数据 class_names，原 training.yaml 不能直接作为 cfg
  - CONF-026 原 dataset.yaml 的 path 点号被解析到 /home/lenovo/images/val，不能定位正式 evidence dataset
  - CONF-027 25680ad 新增 runtime 配置归一化，RED 为模块缺失，GREEN 为新增 3/3、聚焦 16/16、Mac package 888/888
open_risks:
  - 新 runtime 配置尚未经过 Ultralytics get_cfg/check_det_dataset 与真实 CUDA 训练
next_command: 准备 /training/smoke-exp-008 并启动 1 epoch、fraction 0.05 的 CUDA segmentation smoke
```

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
experiment_id: EXP-016
status: VALID
prior_experiment: EXP-015
hypothesis: 同一 best.pt 与 seed 300001 在 Mac MPS 上经 confidence 0.50 TargetSelector 后可唯一选出 plastic_cup，且与 Linux selected mask 结论一致
prediction: runtime_device=mps、raw_count>=1、eligible_count=1、selected class=plastic_cup、mask 480x640非空、latency<=2000、weight SHA一致
single_variable: 相对 EXP-015 仅平台/device 从 Linux CUDA 变为 Mac MPS
lifecycle: ISOLATED_STACK
preconditions:
  - MPS available=true；本地 best/image SHA 与正式 evidence root一致
  - source 35db5f5、threshold 0.50、imgsz640、seed300001固定；Mac/remote输出均不存在
success_criteria:
  - 不允许 CPU fallback，batch runtime_device=mps 与 weight SHA正确
  - eligible_count=1，TargetSelector 返回 plastic_cup；mask 480x640非空；inference<=2000ms
  - 本地结果与hash同步到正式 platform-smoke/macos-exp016 且逐文件一致
failure_criteria:
  - MPS/权重/eligible/selected/mask/latency任一失败
invalid_criteria:
  - source/input/output/sync provenance 污染
provenance:
  source_commit: 35db5f54c1d2516fbe752afbe7380d38522a2a19
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  runtime_executable: /tmp/so101-v5-t004-perception-macos/bin/python
  ros_domain_id: 0
  gz_partition: NONE
commands:
  - command: copy and verify best.pt/image, run detector plus TargetSelector at 0.50, sync result/hash to remote
    exit_code: 0
observed:
  - remote 与 Mac output 均预先不存在；best.pt 与输入图像已复制到独立 Mac staging
  - best.pt SHA256=f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781；图像 SHA256=4462803146c9e5abeaca5a05a7615557eb8b51817fc5dc2a82c03d2b9753d909，均与正式 evidence root 一致
  - sandbox 内 mps_available=false 属于执行环境限制；正式探针将以受控的 sandbox 外命令重新核验并强制 mps、禁止 CPU fallback
  - 受控 sandbox 外 gate 为 mps_built=true、mps_available=true；runtime_device=mps，未允许 CPU fallback
  - raw_count=296、eligible_count=1；selected plastic_cup confidence=0.9705414176，mask_shape=[480,640]、mask_pixels=5053
  - inference_latency_ms=447.77475、cold_start_latency_ms=14943.576125；一次性 Ultralytics settings/font cache 初始化计入 cold start，不计入单次请求门槛
  - result.json SHA256=d699eba199a562929bfe21adbb372046a4204773ad685d6b186e9f5ed65b1252；远端同步回读一致，probe 后无进程残留
inferred:
  - Linux 与 Mac 的 bbox/confidence 仅有浮点级差异，选择结果和 5053-pixel mask 一致
conclusion: PASS；Mac MPS detector/selector 平台冒烟通过
evidence:
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/platform-smoke/macos-exp016
decision: KEEP；进入双平台四场景真实 ROS RGB-D 验收
next_experiment: EXP-017
```

```yaml
experiment_id: EXP-015
status: VALID
prior_experiment: EXP-013
hypothesis: seed 300001 的 raw candidates 经生产 TargetSelector(confidence_threshold=0.50) 后在 Linux CUDA 上唯一选择真实 plastic_cup
prediction: raw_count>=1、eligible_count=1、selected confidence约0.9705、mask 480x640且非空、runtime_device=cuda、latency<=2000
single_variable: 修正 INVALID EXP-013 探针层级与输出目录顺序；模型、图像、device、source、threshold不变
lifecycle: ISOLATED_STACK
preconditions:
  - source 35db5f5、weight SHA f281d252...40781、seed300001 truth=1、CUDA gate有效
  - 新 output platform-smoke/linux-exp015 不存在；无其他 inference进程
success_criteria:
  - batch runtime_device=cuda、weight SHA正确；raw_count仅记录不作唯一性断言
  - eligible_count=1，TargetSelector 返回唯一 plastic_cup；mask 480x640非空、inference<=2000ms
  - 预创建输出目录后命令 exit 0，result 与 SHA非空
failure_criteria:
  - CUDA/权重/eligible/selector/mask/latency失败
invalid_criteria:
  - source/input/output provenance或命令退出码污染
provenance:
  source_commit: 35db5f54c1d2516fbe752afbe7380d38522a2a19
  install_overlay: /data/work/ws_moveit-v5-t004/install
  runtime_executable: /data/work/venvs/so101-v5-t004-perception/bin/python
  ros_domain_id: 0
  gz_partition: NONE
commands:
  - command: precreate platform-smoke/linux-exp015; run YoloSegDetector plus TargetSelector at 0.50; write result and SHA
    exit_code: 0
observed:
  - runtime_device=cuda；raw_count=296、eligible_count=1；selected plastic_cup confidence=0.9705128074
  - selected mask_shape=[480,640]、mask_pixels=5053；inference_latency_ms=37.581604、cold_start_latency_ms=2249.773627
  - result.json SHA256=12d58f356855b523269b18fad2f9c72b9cfe65dc66f0fc2458de072e2d7360e5；权重 SHA 与正式 best.pt 一致
  - 命令退出 0，probe 后无本任务 inference 进程残留
inferred:
  - raw candidates 数量是 adapter 的低阈值输出细节；生产唯一性由 TargetSelector 的 0.50 阈值保证
conclusion: PASS；Linux CUDA detector/selector 平台冒烟通过
evidence:
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/platform-smoke/linux-exp015
decision: KEEP；以相同权重和输入继续 EXP-016 Mac MPS
next_experiment: EXP-016
```

```yaml
experiment_id: EXP-014
status: INVALID
prior_experiment: EXP-013
hypothesis: 从正式 evidence root 拷贝并核对相同 SHA 的 best.pt 可在 Mac MPS YoloSegDetector 上对 seed 300001 输出唯一 plastic_cup 与非空 full-resolution mask
prediction: runtime_device=mps、weights SHA=f281d252...40781、candidate_count=1、class=plastic_cup、mask非空且 inference_latency_ms<=2000
single_variable: 相对 EXP-013 仅平台/device 从 ai-station CUDA 变为 Mac MPS；权重、图像、query、imgsz与 adapter source相同
lifecycle: ISOLATED_STACK
preconditions:
  - Mac MPS available=true，锁定 torch/ultralytics 版本已通过
  - 从正式 evidence root复制 best.pt 与 seed 300001 image 后逐文件 SHA 回读一致
  - 没有其他本任务 inference 进程；独立 Mac staging 与正式 platform-smoke/macos 输出不存在
success_criteria:
  - YoloSegDetector 实际 runtime_device=mps 且不允许 CPU fallback
  - model weight SHA 精确为 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  - candidate_count=1、class_id=plastic_cup、mask shape=480x640 且非空、inference_latency_ms<=2000
  - JSON 与 hash manifest 同步回正式 evidence root
failure_criteria:
  - MPS 不可用/回退、hash不一致、候选数/类别/mask/延迟不符合
invalid_criteria:
  - 图像/权重/source provenance 或结果同步 hash 不匹配
provenance:
  source_commit: 35db5f54c1d2516fbe752afbe7380d38522a2a19
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  runtime_executable: /tmp/so101-v5-t004-perception-macos/bin/python
  ros_domain_id: 0
  gz_partition: NONE
commands:
  - command: scp ai-station:.../full-exp-012/best.pt and dataset/images/test/000300001.png to registered Mac staging; verify SHA
    exit_code: NOT_RUN
  - command: instantiate YoloSegDetector(requested_device=mps, allow_cpu_fallback=false) and detect seed 300001
    exit_code: NOT_RUN
observed:
  - 在执行前由 EXP-013 证明 candidate_count=1 写在错误的 raw DetectorPort 边界；本实验未启动、未创建输出
inferred:
  - 必须用新实验在 TargetSelector confidence 0.50 后断言唯一性
conclusion: INVALID BEFORE RUN；计划判据层级错误
evidence:
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/platform-smoke/macos
decision: ABANDON
next_experiment: EXP-016
```

```yaml
experiment_id: EXP-013
status: INVALID
prior_experiment: EXP-012
hypothesis: full-exp-012 best.pt 可在 Linux CUDA YoloSegDetector 上对固定 seed 300001 输出唯一 plastic_cup 与非空 full-resolution mask
prediction: runtime_device=cuda、weights SHA=f281d252...40781、candidate_count=1、class=plastic_cup、mask非空且 inference_latency_ms<=2000
single_variable: 首次用正式 best.pt 运行生产 YoloSegDetector；固定平台 CUDA、图像 seed 300001、query plastic_cup、imgsz 640
lifecycle: ISOLATED_STACK
preconditions:
  - source 35db5f54c1d2516fbe752afbe7380d38522a2a19 与锁定 runtime venv
  - best.pt SHA f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  - seed 300001 truth 为 one_cup_distractors 且 visible_instance_count=1
  - CUDA gate有效且没有其他本任务 inference 进程；Linux output 不存在
success_criteria:
  - YoloSegDetector 实际 runtime_device=cuda 且不允许 CPU fallback
  - batch weights SHA 正确，candidate_count=1、class_id=plastic_cup
  - mask shape=480x640 且非空，inference_latency_ms<=2000；JSON 与 hash写入正式 evidence root
failure_criteria:
  - CUDA/权重/候选数/类别/mask/延迟任一不符合
invalid_criteria:
  - source/image/weight provenance 不匹配或外部 inference 污染
provenance:
  source_commit: 35db5f54c1d2516fbe752afbe7380d38522a2a19
  install_overlay: /data/work/ws_moveit-v5-t004/install
  runtime_executable: /data/work/venvs/so101-v5-t004-perception/bin/python
  ros_domain_id: 0
  gz_partition: NONE
commands:
  - command: instantiate YoloSegDetector(requested_device=cuda, allow_cpu_fallback=false) and detect dataset/images/test/000300001.png
    exit_code: 1
observed:
  - source、CUDA、best.pt hash、seed 300001 image/truth与独立 Linux output 已核验，实验进入 RUNNING
  - raw DetectionBatch 为 296 candidates；仅 1 个 confidence>=0.50，top confidence=0.970513、mask=480x640、5053 pixels
  - probe 没有调用 TargetSelector，且 tee 在 Python 创建 output 目录前打开导致 pipeline exit 1；result.json 仍保存并哈希
inferred:
  - 模型与阈值后的唯一候选看起来正确，但本轮 probe/exit evidence 污染，不能计为 adapter smoke
conclusion: INVALID；断言层级与输出顺序错误
evidence:
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/platform-smoke/linux
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/platform-smoke/linux/invalid-probe.sha256
decision: REPEAT
next_experiment: EXP-015
```

```yaml
experiment_id: EXP-012
status: VALID
prior_experiment: EXP-011
hypothesis: 已由 EXP-011 验证的离线 CUDA envelope 可在完整 800/200 数据和 100 epoch 配置上训练出单一 best.pt，并完成独立 200-image test split 评估
prediction: 训练扫描 800 train/200 val，CUDA:0 RTX 5080、amp=False、无自动下载，exit 0；test split 评估 exit 0 并生成 metrics.json、best.pt 和 SHA256
single_variable: 相对 VALID EXP-011 仅移除 epochs=1/fraction=0.05 smoke 覆盖，恢复冻结 training.yaml 的 epochs=100 与完整 train split
lifecycle: ISOLATED_STACK
preconditions:
  - source 35db5f54c1d2516fbe752afbe7380d38522a2a19，EXP-011 同一 GPU/base model/dataset/envelope有效通过
  - 800 train、200 val、200 test 数据与 base SHA 不变，锁定字体 SHA 有效
  - 没有其他训练进程；output full-exp-012 不存在
success_criteria:
  - runtime config get_cfg/check_det_dataset 通过，epochs=100、无 fraction override、amp=false
  - 日志扫描 800 train/200 val，明确 CUDA:0 RTX 5080，且无 Downloading、yolo26n.pt 或 PyPI update
  - training exit-code.txt 精确为 0；best.pt、last.pt、results.csv、args.yaml 非空
  - 使用 best.pt 对 200-image test split 评估退出 0，metrics.json 可解析并包含 box 与 mask 指标
  - best.pt 与所有交付工件写 SHA256，且没有残留训练/评估进程
failure_criteria:
  - 训练或 test 评估非零、自动下载、CUDA 未使用、数据计数错误或工件/指标缺失
invalid_criteria:
  - provenance/output/exit-code 污染、外部训练进程干扰或主机生命周期中断
provenance:
  source_commit: 35db5f54c1d2516fbe752afbe7380d38522a2a19
  install_overlay: /data/work/ws_moveit-v5-t004/install
  runtime_executable: /data/work/venvs/so101-v5-t004-perception/bin/yolo
  ros_domain_id: 0
  gz_partition: NONE
commands:
  - command: prepare_training_run(..., output_root=.../training/full-exp-012, run_name=train)
    exit_code: 0
  - command: YOLO_OFFLINE=true yolo segment train cfg=.../training/full-exp-012/training-config.yaml
    exit_code: 0
  - command: YOLO(best.pt).val(data=dataset.yaml, split=test, device=cuda, imgsz=640) and write metrics.json
    exit_code: 0
observed:
  - source、GPU、dataset/base model/font hash、进程所有权与独立 full output root已核验，实验进入 RUNNING
  - runtime config epochs=100、fraction absent、amp=false；扫描 800 train/200 val 且日志无 forbidden download marker
  - 100 epochs in 0.133 hours；training exit 0，best/last各 6001316 bytes，best SHA256=f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  - 独立 200-image test exit 0：mask precision=0.999735、recall=1.0、mAP50=0.995、mAP50-95=0.973662
  - metrics.json、weights.sha256、artifacts.sha256 可解析；训练/评估后无残留进程
inferred:
  - 合成 test split 表明模型离线分割质量充分进入双平台真实 adapter 与 ROS 场景验收，但不能代替真实 topic/3D/pick-place
conclusion: PASS；全量 best.pt 与 test metrics 交付门通过
evidence:
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/full-exp-012
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/full-exp-012/best.pt
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/full-exp-012/metrics.json
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/full-exp-012/weights.sha256
decision: KEEP
next_experiment: EXP-013
```

```yaml
experiment_id: EXP-011
status: VALID
prior_experiment: EXP-010
hypothesis: 将本机 DejaVuSans.ttf 以锁定 SHA 预置为 Ultralytics USER_CONFIG_DIR/Arial.ttf，可满足无条件字体检查并让 amp=false、YOLO_OFFLINE=true smoke 零下载完成
prediction: 预置字体 SHA 与系统源一致；1 epoch、fraction 0.05 日志无 Downloading/yolo26n/PyPI update，exit-code.txt 精确为 0，关键训练工件非空
single_variable: 相对 INVALID EXP-010 仅预置已哈希的本机字体资产；模型、数据、seed、amp/offline、GPU和训练参数不变
lifecycle: ISOLATED_STACK
preconditions:
  - source 35db5f54c1d2516fbe752afbe7380d38522a2a19，GPU gate 与 Linux focused 16/16 通过
  - /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf SHA256 为 ae7b7855e115a5966d8b1b3f80f254ccc117ec86f9965e202ee2940453837280b
  - Ultralytics config 中没有 Arial.ttf，且 output smoke-exp-011 不存在
  - 没有其他训练进程
success_criteria:
  - 预置 Arial.ttf 与系统 DejaVuSans.ttf SHA 完全一致
  - runtime config/dataset validation 通过，amp=false
  - 日志明确 CUDA:0 RTX 5080，不含 Downloading、yolo26n.pt 或 New https://pypi.org
  - exit-code.txt 精确为单行 0
  - smoke/weights/best.pt、last.pt、results.csv、args.yaml 非空并有 SHA256
failure_criteria:
  - 仍自动下载、训练非零、CUDA 未使用或工件缺失
invalid_criteria:
  - 字体/source/model/dataset/output provenance 不匹配，退出码污染或外部训练进程干扰
provenance:
  source_commit: 35db5f54c1d2516fbe752afbe7380d38522a2a19
  install_overlay: /data/work/ws_moveit-v5-t004/install
  runtime_executable: /data/work/venvs/so101-v5-t004-perception/bin/yolo
  ros_domain_id: 0
  gz_partition: NONE
commands:
  - command: cp /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf .../ultralytics-config/Ultralytics/Arial.ttf && sha256sum source target
    exit_code: 0
  - command: prepare_training_run(..., output_root=.../training/smoke-exp-011, run_name=smoke, epochs_override=1, fraction=0.05)
    exit_code: 0
  - command: YOLO_OFFLINE=true yolo segment train cfg=.../training/smoke-exp-011/training-config.yaml
    exit_code: 0
observed:
  - source、GPU、dataset、base model、字体 source SHA、进程所有权与独立 output root 已核验，实验进入 RUNNING
  - 预置 Arial.ttf 与系统 DejaVuSans.ttf SHA256 均为 ae7b7855e115a5966d8b1b3f80f254ccc117ec86f9965e202ee2940453837280b
  - 训练日志为 CUDA:0 RTX 5080、amp=False、40 train/200 val，且没有 Downloading、yolo26n.pt 或 PyPI update marker
  - exit-code.txt 精确为 0；best.pt/last.pt 各 5982884 bytes；best SHA256=626a9be58a2fff5a89a0a69903f829eb53d5c1152d8552737ea29c4e32e20459
  - results.csv、args.yaml、training config、dataset config、training log 全部非空并写入 artifacts.sha256
  - 训练后没有残留 yolo/ultralytics 进程
inferred:
  - EXP-008 至 EXP-010 暴露的配置、AMP、offline 与字体隐式依赖均已在首个边界消除
conclusion: PASS；离线 CUDA training smoke 和工件门完整通过，可进入全量训练
evidence:
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/smoke-exp-011
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/smoke-exp-011/artifacts.sha256
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/ultralytics-config/Ultralytics/font-provenance.sha256
decision: KEEP
next_experiment: EXP-012
```

```yaml
experiment_id: EXP-010
status: INVALID
prior_experiment: EXP-009
hypothesis: 使用 YOLO_OFFLINE=true 并修正退出码 capture 后，同一 35db5f5 amp=false 配置可产生无自动下载且退出证据完整的 CUDA smoke
prediction: 1 epoch、fraction 0.05 训练退出 0；日志无 Downloading、yolo26n.pt 或 PyPI update 提示；exit-code.txt 内容精确为单行 0；关键工件非空
single_variable: 消除 INVALID EXP-009 的执行 envelope 污染：增加官方 YOLO_OFFLINE=true 并用 echo 写精确退出码；训练配置、数据、模型、seed与 GPU 不变
lifecycle: ISOLATED_STACK
preconditions:
  - source commit 35db5f54c1d2516fbe752afbe7380d38522a2a19，amp=false，Linux focused 16/16
  - 没有其他训练进程；正式 dataset/base model SHA 不变
  - output root /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/smoke-exp-010 不存在
success_criteria:
  - runtime config 与 dataset validation 通过，amp=false
  - 日志明确 CUDA:0 RTX 5080，且不含 Downloading、yolo26n.pt 或 New https://pypi.org
  - exit-code.txt 精确为单行 0
  - smoke/weights/best.pt、last.pt、results.csv、args.yaml 非空并写 SHA256
failure_criteria:
  - 自动下载/更新检查仍出现、训练非零、CUDA 未使用或工件缺失
invalid_criteria:
  - provenance/output 冲突、退出码未严格捕获或外部训练进程污染
provenance:
  source_commit: 35db5f54c1d2516fbe752afbe7380d38522a2a19
  install_overlay: /data/work/ws_moveit-v5-t004/install
  runtime_executable: /data/work/venvs/so101-v5-t004-perception/bin/yolo
  ros_domain_id: 0
  gz_partition: NONE
commands:
  - command: prepare_training_run(..., output_root=.../training/smoke-exp-010, run_name=smoke, epochs_override=1, fraction=0.05)
    exit_code: PENDING
  - command: YOLO_OFFLINE=true yolo segment train cfg=.../training/smoke-exp-010/training-config.yaml
    exit_code: NOT_CAPTURED_AFTER_AUTHORIZED_INTERRUPT
observed:
  - source、GPU、dataset、base model、进程所有权与独立 output root 已核验，实验进入 RUNNING
  - YOLO_OFFLINE=true 消除了 PyPI update 提示，但在 check_det_dataset 的无条件 check_font 边界仍下载 https://ultralytics.com/assets/Arial.ttf
  - 下载在 114688 bytes 时中断并移入本实验目录；训练 epoch 未开始，且无残留训练进程
inferred:
  - EXP-010 证明 offline 环境变量不覆盖字体 helper，必须显式提供本地字体资产
conclusion: INVALID；自动下载命中失败判据，未进入训练
evidence:
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/smoke-exp-010
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/smoke-exp-010/prohibited-auto-download-Arial.partial.ttf
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/smoke-exp-010/prohibited-auto-download-font.sha256
decision: REPEAT
next_experiment: EXP-011
```

```yaml
experiment_id: EXP-009
status: INVALID
prior_experiment: EXP-008
hypothesis: 35db5f5 冻结 amp=false 后，Ultralytics 不再执行需要外部 yolo26n.pt 的 AMP check，并可从本地锁定 base model 完成 CUDA smoke
prediction: 日志显示 amp=False、CUDA:0 RTX 5080，不出现 Downloading/http；1 epoch、fraction 0.05 退出 0并生成非空 best.pt/last.pt/results.csv/args.yaml
single_variable: 相对 INVALID EXP-008 仅把 amp 从默认 true 冻结为 false，并使用新的未存在 output root
lifecycle: ISOLATED_STACK
preconditions:
  - source commit 与远端隔离 worktree均为 35db5f54c1d2516fbe752afbe7380d38522a2a19
  - Linux focused 16/16、EXP-007 GPU gate 通过且没有其他训练进程
  - 正式 dataset 与 base model SHA 不变
  - output root /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/smoke-exp-009 不存在
success_criteria:
  - runtime 配置 get_cfg/check_det_dataset 通过并包含 amp=false
  - 日志不含 Downloading 或 http，明确 device CUDA:0 RTX 5080 与 amp=False
  - 训练 wrapper 捕获 exit code 0
  - smoke/smoke/weights/best.pt、last.pt、results.csv、args.yaml 均非空
failure_criteria:
  - 仍触发外部下载、配置/数据失败、CUDA 未使用、命令非零或工件不完整
invalid_criteria:
  - commit/model/dataset/output provenance 不匹配，或另一个训练进程污染本轮
provenance:
  source_commit: 35db5f54c1d2516fbe752afbe7380d38522a2a19
  install_overlay: /data/work/ws_moveit-v5-t004/install
  runtime_executable: /data/work/venvs/so101-v5-t004-perception/bin/yolo
  ros_domain_id: 0
  gz_partition: NONE
commands:
  - command: prepare_training_run(..., output_root=.../training/smoke-exp-009, run_name=smoke, epochs_override=1, fraction=0.05)
    exit_code: 0
  - command: yolo segment train cfg=.../training/smoke-exp-009/training-config.yaml
    exit_code: CAPTURE_CORRUPTED_n_0
observed:
  - runtime config get_cfg 通过并明确 amp=false；dataset train/val/test 均解析到正式 evidence dataset
  - source、base model、dataset、GPU 与唯一 output root已核验，实验进入 RUNNING
  - amp=False、CUDA:0 RTX 5080；40 train images、200 val images，1 epoch 完成且日志没有 Downloading 或 yolo26n.pt
  - best.pt 与 last.pt 各 5982884 bytes；best SHA256=db33532c9c80ec43e106bcd5f425a870b9d0a348d5d66e2906541baf2da0b43d
  - 日志包含 Ultralytics PyPI 更新提示和静态 docs URL；wrapper 把 code 0 写成字符串 n 0，违反本轮严格判据
  - 无残留训练进程；全部工件和 artifacts.sha256 保留
inferred:
  - amp=false 已排除 AMP model auto-download，但本轮证据 envelope 不满足预登记成功与有效性门槛
conclusion: INVALID；训练本体完成但不能计为合格 smoke，需用 offline/exit-code 修正后的新实验复验
evidence:
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/smoke-exp-009
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/smoke-exp-009/artifacts.sha256
decision: REPEAT
next_experiment: EXP-010
```

```yaml
experiment_id: EXP-008
status: INVALID
prior_experiment: EXP-007
hypothesis: 25680ad 生成的 runtime training/dataset 配置可被 Ultralytics 8.4.115 接受，并能从本地锁定 yolo11n-seg.pt 在 RTX 5080 上完成一次短训练
prediction: get_cfg 与 check_det_dataset 均通过且指向正式 dataset；1 epoch、fraction 0.05 训练使用 CUDA、退出 0，并生成非空 best.pt 和训练指标
single_variable: 首次执行归一化后的真实 CUDA 训练；smoke 覆盖 epochs=1、fraction=0.05，其余冻结 training.yaml 参数
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-007 nvidia-smi 与 CUDA 张量 gate 有效通过
  - source commit 为 25680adad79384c41f9f8b4d6e962a8c2091881e，隔离 worktree clean
  - 1200 样本 dataset 与本地 base model SHA256 55ed65c56c91713d23e8402371c6c49a6fd84f257f7dce452e8d70e41dcbe152 均存在
  - output root /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/smoke-exp-008 不存在
success_criteria:
  - runtime training config 不含 class_names，model/data/project 均为正式 evidence root 下绝对路径
  - runtime dataset config 的 path 为正式 1200 样本 dataset 根，Ultralytics 检查得到 800/200/200
  - 日志证明 device=CUDA:0 NVIDIA GeForce RTX 5080，训练命令退出 0
  - 生成非空 best.pt、last.pt、results.csv 与 args.yaml
failure_criteria:
  - 配置仍被拒绝、数据路径错误、CUDA 未使用、训练异常退出或关键工件缺失
invalid_criteria:
  - source/dataset/model provenance 不匹配，或存在另一个本任务训练进程污染 GPU/输出目录
provenance:
  source_commit: 25680adad79384c41f9f8b4d6e962a8c2091881e
  install_overlay: /data/work/ws_moveit-v5-t004/install
  runtime_executable: /data/work/venvs/so101-v5-t004-perception/bin/yolo
  ros_domain_id: 0
  gz_partition: NONE
commands:
  - command: prepare_training_run(..., output_root=.../training/smoke-exp-008, run_name=smoke, epochs_override=1, fraction=0.05)
    exit_code: 0
  - command: yolo segment train cfg=.../training/smoke-exp-008/training-config.yaml
    exit_code: NOT_CAPTURED_AFTER_AUTHORIZED_INTERRUPT
observed:
  - Linux 25680ad 聚焦训练配置测试 16/16 通过；训练 venv 不安装 pytest，源码测试使用系统 pytest，运行时仍固定锁定 venv
  - runtime config 已剥离 class_names，get_cfg 接受；dataset path 精确解析到正式 evidence dataset 的 train/val/test
  - provenance、GPU 进程和唯一 output root 已核验，实验进入 RUNNING
  - 日志证明 CUDA:0 RTX 5080 与本地 base model 已加载，但 AMP checks 随后下载 https://github.com/ultralytics/assets/.../yolo26n.pt
  - 下载在 516096 bytes 时被本任务立即中断；partial 移入本实验目录并保留 SHA，未进入任何训练 epoch
  - v5-t004-train-exp008 退出且无残留 yolo 训练进程；wrapper 未能在 tmux 结束前写 exit-code.txt
inferred:
  - 默认 amp=true 的外部模型自检违反冻结依赖与 no-auto-download 前置契约，本轮不能用于训练质量或成功率结论
conclusion: INVALID；训练未开始，首个坏边界为 Ultralytics AMP check 的未锁定运行时下载
evidence:
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/smoke-exp-008
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/smoke-exp-008/prohibited-auto-download-yolo26n.partial.pt
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/smoke-exp-008/prohibited-auto-download.sha256
decision: ABANDON
next_experiment: EXP-009
```

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
