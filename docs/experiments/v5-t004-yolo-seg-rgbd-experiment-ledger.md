# V5-T004 YOLO-Seg RGB-D experiment ledger

```yaml
task_id: so101-v5-t004-yolo-seg-rgbd
goal: 在 macOS MPS 与 ai-station CUDA 上从多物体 MuJoCo RGB-D 选择唯一 plastic_cup，发布新鲜 /cup_pose，并复用现有动态执行链完成仿真 pick&place
success_contract: 同一 best.pt 在两平台通过四场景感知矩阵，随后每平台固定 commit/权重/参数的 FULL_RESTART MuJoCo pick&place 连续 5 次成功
worktree: /Users/matianyi/.codex/worktrees/5b15/moveit-demo
branch: codex/v5-t004-yolo-seg-rgbd
base_commit: f09cf88cf55352f4bf618d44a8ff6c6885419c8d
current_commit: 2560e8b8db2ecf29ef73f0667952fc0bca42dbd8
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
latest_checkpoint: CP-042
next_experiment: EXP-018
```

## Checkpoints

```yaml
checkpoint_id: CP-042
last_valid_experiment: EXP-034
current_hypothesis: 2560e8b将/cup_pose纳入已验证的subscriber discovery与DDS ack，可在EXP-018可靠交付唯一目标pose
working_tree_status: 仅本账本provenance更新待提交；生产源与测试clean
owned_processes: NONE；EXP-018尚未启动，domain 218与output为空
preserved_processes: 既有证据全部保留；用户进程/文件与ai-station主checkout未触碰
confirmed_conclusions:
  - CONF-084 success分支/cup_pose原先仍直接publish；2560e8b复用同一已测试交付原语并把pose publisher纳入发现
  - CONF-085 Mac包级892/892、Linux聚焦24/24、RTX 5080 CUDA gate通过；双平台安装态锁定2560e8b
open_risks:
  - EXP-018仍须真实验证MPS、候选mask、Depth定位、TF、IoU、world error与/cup_pose observer
next_command: 提交本检查点后启动EXP-018，不再修改感知实现
```

```yaml
checkpoint_id: CP-041
last_valid_experiment: EXP-034
current_hypothesis: b23b168在不改变检测选择的前提下可让每个候选mask进入证据，从而支持全部场景truth IoU
working_tree_status: 仅本账本provenance更新待提交；生产源与测试clean
owned_processes: NONE；EXP-018尚未启动，domain 218与output为空
preserved_processes: EXP-034及truth-render诊断均保留；用户进程/文件与ai-station主checkout未触碰
confirmed_conclusions:
  - CONF-081 TDD RED证明TARGET_AMBIGUOUS没有每候选mask；b23b168写candidate-mask-NNN.png并在detections.json记录mask_artifact
  - CONF-082 Mac包级892/892、Linux聚焦24/24、RTX 5080 CUDA gate通过；双平台安装态锁定b23b168
  - CONF-083 本地MuJoCo object-ID truth必须在Aqua CGL运行；普通沙箱invalid CoreGraphics connection，失败目录已保留
open_risks:
  - EXP-018仍须验证IoU/world error/pose；EXP-034 bottle-only最终须在固定b23b168或后续最终commit补跑
next_command: 提交provenance更新后在domain 218启动task_start、静态TF、truth/topic observer和Aqua MPS请求
```

```yaml
checkpoint_id: CP-040
last_valid_experiment: EXP-034
current_hypothesis: 当前ff8caef与同一权重可在task_start唯一选择plastic_cup并从真实Depth发布准确/cup_pose
working_tree_status: 仅本账本VALID/RUNNING转换待提交；生产源与测试clean
owned_processes: NONE；EXP-034前台PTY exit 0，domain 219无节点
preserved_processes: EXP-034有效证据已同步正式evidence root；用户进程/文件与ai-station主checkout未触碰
confirmed_conclusions:
  - CONF-078 EXP-034真实RGB-D、Viewer、controllers、MPS、weight SHA、candidate=0与TARGET_NOT_FOUND全部通过
  - CONF-079 EXP-034 observer收到空detections与640x480 rgb8 overlay各1条、同stamp、cup_pose=0；inference247.50ms、request319.31ms
  - CONF-080 EXP-034 overlay清晰，Ctrl-C后MuJoCo/MoveIt clean且domain 219无节点；Mac bottle-only矩阵项VALID
open_risks:
  - EXP-018首次生产定位仍须验证exact-stamp TF、唯一mask、IoU、深度点、world error与新鲜/cup_pose
next_command: domain 218下启动task_start、任务自有静态TF、120秒observer与Aqua MPS one-shot
```

```yaml
checkpoint_id: CP-039
last_valid_experiment: EXP-016
current_hypothesis: 推理前等待observer发现并在发布后等待DDS ack可让EXP-034通过一次性topic交付门
working_tree_status: 仅本账本FAILED_VALID/RUNNING转换待提交；发布确认修复已提交并推送
owned_processes: NONE；EXP-033前台PTY exit 0，domain 220无节点
preserved_processes: EXP-033有效失败证据已同步正式evidence root；用户进程/文件与ai-station主checkout未触碰
confirmed_conclusions:
  - CONF-075 EXP-033真实RGB-D/Viewer/controllers通过，MPS候选0、TARGET_NOT_FOUND、inference179.19ms、request201.99ms、weight SHA正确且overlay清晰
  - CONF-076 EXP-033 observer完整120秒仍detections=0/overlay=0/cup_pose=0，确认one-shot publisher在DDS传输前销毁
  - CONF-077 TDD新增discovery-spin/publish/ack顺序契约；ff8caef Mac包级892/892、Linux聚焦23/23与CUDA gate通过
open_risks:
  - EXP-034仍须新FULL_RESTART证明topic ack、TARGET_NOT_FOUND、MPS、延迟、无/cup_pose与cleanup同时成立
next_command: domain 219与新output下启动EXP-034，observer先于Aqua MPS请求且至少120秒
```

```yaml
checkpoint_id: CP-038
last_valid_experiment: EXP-016
current_hypothesis: 零候选时接受Ultralytics masks=None可让新FULL_RESTART EXP-033到达合法TARGET_NOT_FOUND边界
working_tree_status: 仅本账本INVALID/RUNNING转换待提交；生产修复已提交并推送
owned_processes: NONE；EXP-032前台PTY exit 0，domain 232无节点
preserved_processes: EXP-032无效诊断批次已同步正式evidence root；用户进程/文件与ai-station主checkout未触碰
confirmed_conclusions:
  - CONF-072 EXP-032真实RGB-D、Viewer与三controllers通过，但首次请求因PATH入口无效，绝对入口重试暴露零候选masks=None契约缺口
  - CONF-073 TDD RED复现空boxes/classes/confidence加masks=None；4d0b6e3仅在count=0时接受，Mac adapter22/22、包级891/891通过
  - CONF-074 Linux isolated checkout/install=4d0b6e3，adapter22/22、RTX 5080 CUDA gate通过，installed import回读conf=0.25与零mask分支
open_risks:
  - EXP-033仍须新FULL_RESTART证明detections/overlay、TARGET_NOT_FOUND、MPS、延迟、无/cup_pose与cleanup同时成立
next_command: domain 220与新output下启动EXP-033，observer先于Aqua MPS请求且至少120秒
```

```yaml
checkpoint_id: CP-037
last_valid_experiment: EXP-016
current_hypothesis: 双平台安装态已包含0.25候选下限，EXP-032可在正式FULL_RESTART通过not-found全部门禁
working_tree_status: 仅本账本 RUNNING 转换待提交；生产源/测试 clean
owned_processes: NONE；正式 EXP-032 尚未启动
preserved_processes: 所有失败与无效证据已持久化；ai-station主checkout用户未跟踪账本未触碰
confirmed_conclusions:
  - CONF-069 candidate-floor commit=eb4d991；Mac installed import与Linux isolated installed import均回读conf=0.25
  - CONF-070 Mac包级890/890、Linux adapter 21/21；Mac MPS与Linux RTX 5080 CUDA gate通过
  - CONF-071 domain 232、两端output与任务进程为空
open_risks:
  - EXP-032真实候选数、topic observer、延迟、overlay与cleanup尚未观察
next_command: 前台PTY FULL_RESTART EXP-032，先起120秒topic observer再通过Aqua MPS发起请求
```

```yaml
checkpoint_id: CP-036
last_valid_experiment: EXP-016
current_hypothesis: YOLO标准0.25候选下限可消除0.00噪声实例，使清晰overlay与request_latency<=2000同时成立
working_tree_status: candidate-floor生产代码、RED/GREEN测试与本账本待提交；其余源 clean
owned_processes: NONE；EXP-031 stack与感知进程均退出，domain 231无节点
preserved_processes: EXP-031 stack/payload/MPS失败与overlay证据已同步正式 evidence root；用户进程/文件未触碰
confirmed_conclusions:
  - CONF-066 EXP-031真实RGB-D 640x480 rgb8/32FC1对齐，finite positive depth 307200，三controllers active，exact-window Viewer有效
  - CONF-067 Aqua MPS生产请求正确返回TARGET_NOT_FOUND且不发布pose，但297个约0.00候选令overlay不可读、request_latency=3033.05ms，构成有效产品失败
  - CONF-068 TDD RED捕获conf=0.0；改为YOLO标准0.25后adapter 21/21、包级890/890通过，Mac候选install重建完成
disproven_routes:
  - DISPROVED-015 不得把所有NMS前近零分数proposals当作业务候选；它破坏overlay清晰度与2秒请求门槛
open_risks:
  - EXP-032 必须用新FULL_RESTART证明0.25下限下候选数、topic、延迟和not-found全部合格
next_command: 提交候选下限修复；同步并重建Linux安装态，随后预登记EXP-032正式重跑
```

```yaml
checkpoint_id: CP-035
last_valid_experiment: EXP-016
current_hypothesis: 已隔离且保持完整overlay DYLD闭包的 EXP-031 可进入真实产品边界
working_tree_status: 仅本账本 RUNNING 转换待提交；源/测试 clean
owned_processes: NONE；正式 EXP-031 尚未启动
preserved_processes: 所有无效运行证据已持久化；用户进程/文件未触碰
confirmed_conclusions:
  - CONF-065 domain 231、两端output与任务进程为空；完整主安装DYLD闭包已回读
open_risks:
  - UI握手、Viewer/controller/payload/not-found/视觉/cleanup尚未观察
next_command: 以前台tty=true、自动DYLD闭包后接farm启动 EXP-031
```

```yaml
checkpoint_id: CP-034
last_valid_experiment: EXP-016
current_hypothesis: 保留overlay生成的完整DYLD顺序并只把farm追加到末尾，可让整套MuJoCo库来自同一主安装
working_tree_status: 仅本账本 INVALID/替代计划待提交；源/测试 clean
owned_processes: NONE；EXP-030 owner与child已Ctrl-C退出，domain 230无节点
preserved_processes: EXP-030 ROS日志已同步正式 evidence root；用户进程/文件未触碰
confirmed_conclusions:
  - CONF-063 EXP-030选中主安装core，但farm仍先于自动overlay中的msgs目录，导致主core绑定旧fork msgs并缺SetFreeJointState符号
  - CONF-064 overlay自动DYLD已按support/core/plugins/msgs顺序包含全部主安装目录；共享farm只需作为最终fallback
disproven_routes:
  - DISPROVED-014 手工列举部分主安装库目录再把farm置于其后仍不完整；必须保持完整overlay闭包在farm前
open_risks:
  - EXP-031 仍须验证完整主安装闭包、UI握手与全部产品验收边界
next_command: 预登记 EXP-031；唯一修改为保留自动DYLD闭包并把farm追加到最后
```

```yaml
checkpoint_id: CP-033
last_valid_experiment: EXP-016
current_hypothesis: 主安装core/plugin/support dylib优先的前台PTY Aqua宿主可让 EXP-030 完成UI握手
working_tree_status: 仅本账本 RUNNING 转换待提交；源/测试 clean
owned_processes: NONE；正式 EXP-030 尚未启动
preserved_processes: 所有无效运行证据已持久化；用户进程/文件未触碰
confirmed_conclusions:
  - CONF-062 主安装core、dispatcher、camera plugin与support目录均存在；domain 230及两端output为空
open_risks:
  - 主安装dylib优先下的dispatcher握手、Viewer/controller/payload/not-found/视觉/cleanup尚未观察
next_command: 以前台 tty=true 和主安装dylib优先启动 EXP-030
```

```yaml
checkpoint_id: CP-032
last_valid_experiment: EXP-016
current_hypothesis: 当前主安装的 core/plugin/support dylib优先于共享farm后，单一dispatcher可完成main-thread UI握手
working_tree_status: 仅本账本 INVALID/替代计划待提交；源/测试 clean
owned_processes: NONE；EXP-029 前台 owner与全部child已Ctrl-C退出，domain 229无节点
preserved_processes: EXP-029 ROS日志已同步正式 evidence root；用户进程/文件未触碰
confirmed_conclusions:
  - CONF-060 EXP-029 前台PTY仍超时，排除PTY为当前第一坏边界
  - CONF-061 当前 executable来自主安装，但farm首位的libmujoco_ros2_control.dylib符号链接到旧 ws_mujoco_ros2_control_fork，形成dispatcher二进制分裂
disproven_routes:
  - DISPROVED-013 不得只用 package prefix或可执行文件路径证明 macOS MuJoCo runtime provenance；必须回读已加载core dylib优先级
open_risks:
  - EXP-030 仍须实际观察单一dispatcher、Viewer、controllers、真实RGB-D、MPS not-found、GUI证据与干净退出
next_command: 预登记 EXP-030；保留前台PTY，仅把主安装core/plugin/support dylib排在farm前
```

```yaml
checkpoint_id: CP-031
last_valid_experiment: EXP-016
current_hypothesis: 已隔离的前台 PTY Aqua宿主可让 EXP-029 执行 MuJoCo process-main-thread UI task
working_tree_status: 仅本账本 RUNNING 转换待提交；源/测试 clean
owned_processes: NONE；正式 EXP-029 尚未启动
preserved_processes: 所有无效运行证据已持久化；用户进程/文件未触碰
confirmed_conclusions:
  - CONF-059 domain 229、两端 output与任务进程为空；Aqua/source/dylib/MPS preflight沿用已通过结果
open_risks:
  - 前台PTY下的Viewer/controller/payload/not-found/视觉/cleanup尚未观察
next_command: 以前台 tty=true 启动 EXP-029 并保持 unified exec session作为 owner
```

```yaml
checkpoint_id: CP-030
last_valid_experiment: EXP-016
current_hypothesis: 前台 PTY 是 Aqua 中执行 MuJoCo process-main-thread UI task 的必要 harness 条件
working_tree_status: 仅本账本 INVALID/替代计划待提交；源/测试 clean
owned_processes: NONE；EXP-028 launch PID 25887 已 SIGINT退出，domain 228无任务节点
preserved_processes: EXP-028 的 43 MB xtrace、ROS分进程日志与空后台日志已同步正式 evidence root；用户进程/文件未触碰
confirmed_conclusions:
  - CONF-057 EXP-028 完整 source chain与 ros2 launch可达，但无PTY的Aqua进程未执行 main-thread UI task，渲染握手10秒超时
  - CONF-058 历史有效 macOS RGB-D验收使用 launchctl asuser 501 的前台 tty=true；当前无PTY失败与该边界一致
disproven_routes:
  - DISPROVED-012 GUI launch domain本身不足以保证 Cocoa/MainThread调度；当前执行宿主还必须保有前台PTY
open_risks:
  - EXP-029 仍须实际观察 Viewer、controllers、真实 RGB-D、MPS not-found、GUI证据与干净退出
next_command: 预登记并以前台 tty=true 启动 EXP-029；产品参数保持不变
```

```yaml
checkpoint_id: CP-029
last_valid_experiment: EXP-016
current_hypothesis: 已通过预检且无严格 shell flags 的 Aqua wrapper 可让 EXP-028 到达真实 stack
working_tree_status: 仅本账本 RUNNING 转换待提交；源/测试 clean
owned_processes: NONE；正式 Aqua wrapper 尚未启动
preserved_processes: EXP-017/025/026/027 无效证据均已持久化；用户进程/文件未触碰
confirmed_conclusions:
  - CONF-056 gui/501 Aqua 环境链、MuJoCo dylib dlopen与MPS通过；domain 228、两端 output与任务进程为空
open_risks:
  - Aqua UI task、controllers、真实 payload、MPS not-found、视觉证据与cleanup尚未观察
next_command: 启动 EXP-028 Aqua owner并回读 PID/log/window/topic
```

```yaml
checkpoint_id: CP-028
last_valid_experiment: EXP-016
current_hypothesis: 不启用 errexit/nounset 的 Aqua wrapper 可让 EXP-028 到达真实 stack
working_tree_status: 仅本账本 INVALID/替代计划待提交；源/测试 clean
owned_processes: NONE；PID 23072 已退出，domain 227 无 ROS 节点
preserved_processes: EXP-027 的空 stack.log 与 PID 文件已同步正式 evidence root；用户进程/文件未触碰
confirmed_conclusions:
  - CONF-054 EXP-027 在任何 ROS child、topic 或产品输出产生前退出；Aqua owner消失且 stack.log为空
  - CONF-055 相同完整 source/dylib/MPS 环境链在不启用 set -e/-u 的 gui/501 Aqua 预检中通过
disproven_routes:
  - DISPROVED-011 不得给 ROS overlay source chain启用 errexit；可选 setup脚本返回值会让 wrapper静默退出
open_risks:
  - EXP-028 仍须证明 Viewer、controllers、真实 RGB-D、MPS not-found、GUI证据与干净退出
next_command: 预登记并启动 EXP-028；相对 EXP-027 仅移除 wrapper errexit
```

```yaml
checkpoint_id: CP-027
last_valid_experiment: EXP-016
current_hypothesis: 语法有效且兼容 setup.zsh 的 Aqua wrapper 可让 EXP-027 到达真实 stack
working_tree_status: 仅本账本 RUNNING 转换待提交；源/测试 clean
owned_processes: NONE；正式 Aqua wrapper 尚未启动
preserved_processes: 所有无效运行已持久化；用户进程/文件未触碰
confirmed_conclusions:
  - CONF-053 wrapper zsh -n通过；gui/501=Aqua、domain 227、两端 output与task process为空
open_risks:
  - Aqua UI task、controllers、真实 payload与not-found仍未观察
next_command: 启动 EXP-027 Aqua owner并回读PID/log/window/topic
```

```yaml
checkpoint_id: CP-026
last_valid_experiment: EXP-016
current_hypothesis: 兼容 ROS setup 的 Aqua wrapper 可进入真正 stack；去掉 nounset 不改变任何产品变量
working_tree_status: 仅本账本 INVALID/替代计划待提交；源/测试 clean
owned_processes: NONE；PID 21861 已退出且没有 ROS/MuJoCo child
preserved_processes: 467-byte wrapper错误与PID文件已同步正式 evidence root
confirmed_conclusions:
  - CONF-052 EXP-026 在 ROS launch 前退出，原因是 wrapper set -u 与 ROS setup的可选 COLCON_TRACE/PYTHONPATH 不兼容
disproven_routes:
  - DISPROVED-010 不得对 ROS setup.zsh 使用 nounset；这不是 Aqua、MuJoCo或模型失败
open_risks:
  - Aqua main-thread stack仍未实际启动
next_command: 用兼容 wrapper 新建 EXP-027，保持所有产品参数不变
```

```yaml
checkpoint_id: CP-025
last_valid_experiment: EXP-016
current_hypothesis: 干净 gui/501 Aqua session可执行 EXP-026 main-thread UI与真实 RGB-D
working_tree_status: 仅本账本 RUNNING 转换待提交；源/测试 clean
owned_processes: NONE；Aqua stack 尚未启动
preserved_processes: EXP-017/025无效证据持久化；用户进程/文件未触碰
confirmed_conclusions:
  - CONF-051 gui/501 session=Aqua、WindowServer PID 599；domain 226、两端 output、task process为空；dylib/MPS gate通过
open_risks:
  - launchctl asuser 实际 stack、窗口、payload、not-found与cleanup尚未观察
next_command: 通过 launchctl asuser 501 /bin/zsh -lc 启动并记录 Aqua stack owner PID
```

```yaml
checkpoint_id: CP-024
last_valid_experiment: EXP-016
current_hypothesis: 通过 launchctl asuser 501 的 Aqua zsh 启动与正确环境可执行 macOS main-thread UI dispatch
working_tree_status: 仅本账本 INVALID/替代计划待提交；源/测试 clean
owned_processes: NONE；domain 225 与 PID 19518-19524 已清空
preserved_processes: EXP-025 ROS日志已同步正式 evidence root；无证据删除
confirmed_conclusions:
  - CONF-049 EXP-025 已加载正确主项目插件和 MuJoCo 3.4.0，但普通 Codex 子进程两次出现 Timed out waiting to start simulation rendering
  - CONF-050 既有有效运行使用 launchctl asuser 501 /bin/zsh -lc 进入 Aqua 后由 macOS main thread 执行 UI task；普通 shell不等价
disproven_routes:
  - DISPROVED-009 仅补 DYLD_LIBRARY_PATH 不能让普通 Codex 子进程完成 macOS Cocoa/MainThread 调度
open_risks:
  - EXP-026 必须回读 Aqua 启动 PID、controllers、真实 camera topics 与可见窗口后才算越过环境边界
next_command: 预检并以 launchctl asuser 501 的前台 Aqua zsh 启动 EXP-026
```

```yaml
checkpoint_id: CP-023
last_valid_experiment: EXP-016
current_hypothesis: EXP-025 的唯一环境修正可让 v5_no_cup stack进入真实 RGB-D 与模型边界
working_tree_status: 仅本账本 RUNNING 转换待提交；源/测试 clean
owned_processes: NONE；正式 stack 尚未启动
preserved_processes: EXP-017 无效证据已持久化；用户进程/文件未触碰
confirmed_conclusions:
  - CONF-048 domain 225、两端 output与任务进程为空；锁定 dylib farm dlopen、Mac install与 MPS gate通过
open_risks:
  - 真实 stack/payload/not-found/GUI/cleanup 尚未观察
next_command: 以显式 DYLD_LIBRARY_PATH 启动 EXP-025 visible stack
```

```yaml
checkpoint_id: CP-022
last_valid_experiment: EXP-016
current_hypothesis: 在原命令增加已验证的锁定 DYLD_LIBRARY_PATH 后，替代实验 EXP-025 可进入真实 MuJoCo/RGB-D 边界
working_tree_status: 仅本账本 INVALID/替代计划待提交；源/测试 clean
owned_processes: NONE；domain 221 清空，PID 17610-17616 均退出
preserved_processes: EXP-017 完整 ROS 日志已同步正式 evidence root；未删除任何无效工件
confirmed_conclusions:
  - CONF-046 EXP-017 首个坏边界是 libmujoco_ros2_control.dylib 找不到 @rpath/libmujoco.3.4.0.dylib，未创建 MuJoCo UI、真实 RGB-D 或模型请求
  - CONF-047 /Users/matianyi/ros2_jazzy/macos_dylib_farm/current 含锁定 3.4.0 dylib；加入 DYLD_LIBRARY_PATH 后同一插件 ctypes dlopen 成功
disproven_routes:
  - DISPROVED-008 未加载 repository dylib farm 的普通 shell 不能作为 macOS MuJoCo 正式运行环境
open_risks:
  - 修正环境后的 visible stack 尚未启动，EXP-025 仍须重新做全部 preflight
next_command: 预检并启动 EXP-025，命令唯一变化为显式导出 dylib farm
```

```yaml
checkpoint_id: CP-021
last_valid_experiment: EXP-016
current_hypothesis: EXP-017 可在干净 domain 221 的真实 RGB-D 上以 TARGET_NOT_FOUND 拒绝橙色瓶子
working_tree_status: 仅本账本 RUNNING 转换待提交；源/测试 clean
owned_processes: NONE；正式 stack 尚未启动
preserved_processes: 历史证据与用户文件均未触碰
confirmed_conclusions:
  - CONF-045 Mac install prefix、入口、v5 scene、MPS 与锁定依赖已回读；domain 221、两端 output 与任务进程均为空
open_risks:
  - visible stack、真实 payload、not-found、GUI 与 cleanup 尚未观察
next_command: 启动 v5_no_cup visible stack、静态 TF、payload observer 与一次性 rgbd_object_pose
```

```yaml
checkpoint_id: CP-020
last_valid_experiment: EXP-016
current_hypothesis: 固定 f732afc 与 f281d252 权重可在双平台八次 FULL_RESTART 真实 ROS RGB-D 场景满足 fail-closed、IoU、3D 与延迟门槛
working_tree_status: 仅本账本的 Task 8 预登记待提交；源代码与测试 clean
owned_processes: NONE；8 次运行均未启动
preserved_processes: 所有历史证据保留；ai-station 用户文件未触碰
confirmed_conclusions:
  - CONF-044 EXP-017 至 EXP-024 已在启动前冻结 commit、权重、参数、domain、partition、场景与判定边界
open_risks:
  - 双平台安装态尚未重建到 f732afc；真实 RGB-D、truth IoU/pose、GUI 与 cleanup 尚未观察
next_command: 重建并回读 macOS 安装态，随后从 EXP-017 bottle_only 开始
```

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
experiment_id: EXP-017
status: INVALID
prior_experiment: EXP-016
hypothesis: macOS MPS 的 bottle_only 场景不会把橙色瓶子误判为 plastic_cup，也不会发布新 /cup_pose
prediction: TARGET_NOT_FOUND；matching_count=0；无新 pose；真实 RGB-D 与 cleanup 全部合格
single_variable: Task 8 首个真实 ROS 场景；platform=macOS、keyframe=v5_no_cup
lifecycle: FULL_RESTART
preconditions:
  - source/install=f732afc、weight SHA=f281d252...40781、device=mps、threshold=0.50、imgsz=640
  - ROS_DOMAIN_ID=221、GZ_PARTITION=v5t004-mac-exp017 为空；本地与正式 output 均不存在
success_criteria:
  - 640x480 rgb8/32FC1/CameraInfo 为同一非零 stamp，frame ID与 finite positive depth有效；runtime_device=mps
  - TARGET_NOT_FOUND、matching_count=0、无新 /cup_pose；request_latency_ms<=2000；瓶子不产生 cup mask
  - exact-window overlay、truth对照、安装态 provenance、退出后零 owned inference 与零 /cup_pose publisher 完整
failure_criteria:
  - 误选瓶子、发布 pose、payload/device/latency/GUI/cleanup 任一失败
invalid_criteria:
  - domain/partition/output/source/install/input provenance 污染或进程图非 FULL_RESTART
provenance:
  source_commit: f732afc4b9a569009864df65b766d7f3cdcaaf21
  install_overlay: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install
  runtime_executable: install/so101_demo_py/lib/so101_demo_py/rgbd_object_pose
  ros_domain_id: 221
  gz_partition: v5t004-mac-exp017
commands:
  - command: fresh visible MuJoCo v5_no_cup stack plus one-shot rgbd_object_pose and acceptance observers
    exit_code: SIGINT_AFTER_INVALID_BOUNDARY
observed:
  - source f732afc、Mac install prefix、入口/scene hash、weight hash 与 MPS available=true 已核验
  - ROS_DOMAIN_ID 221 无节点；本地和正式 output 不存在；无本任务感知或 MuJoCo 进程
  - ros2_control_node PID 17611 在硬件初始化时无法 dlopen libmujoco_ros2_control.dylib，因为 @rpath/libmujoco.3.4.0.dylib 不在 loader path
  - MuJoCo UI 未创建、控制器未启动、没有 RGB-D 或 rgbd_object_pose 请求；确认坏边界后 SIGINT 清理
  - 清理后 domain 221 为空且无 owned process；32691-byte launch.log 与分进程日志已同步正式 evidence root
inferred: [NONE]
conclusion: INVALID；运行环境缺少已知的 macOS dylib farm，不支持任何感知结论
evidence:
  - /tmp/so101-debug-v5-t004-yolo-seg-20260831/perception-matrix/macos/exp-017-bottle-only
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/perception-matrix/macos/exp-017-bottle-only
decision: PRESERVE；以新 ID EXP-025 仅修正 DYLD_LIBRARY_PATH 后重跑
next_experiment: EXP-025
```

```yaml
experiment_id: EXP-018
status: RUNNING
prior_experiment: EXP-034
hypothesis: macOS MPS 的 one_cup_distractors 场景唯一选择 plastic_cup 并从真实 Depth 发布准确 /cup_pose
prediction: matching_count=1；mask IoU>=0.80；world error<0.01m；新鲜 pose
single_variable: 相对VALID bottle-only EXP-034把场景改为task_start并启用定位TF；代码仅增加每候选mask证据，不改变模型/selector/localizer，权重/阈值/平台不变
lifecycle: FULL_RESTART
preconditions:
  - source/install=2560e8b、weight SHA=f281d252...40781、device=mps、threshold=0.50、imgsz=640
  - ROS_DOMAIN_ID=218、GZ_PARTITION=v5t004-mac-exp018 为空；output不存在
success_criteria:
  - 同 stamp 的真实 640x480 rgb8/32FC1/CameraInfo、finite positive depth、exact-stamp tf2与 runtime_device=mps
  - matching_count=1、plastic_cup mask IoU>=0.80、world position error<0.01m、request_latency_ms<=2000、新鲜 /cup_pose
  - overlay标注类别/置信度/边界；安装态 provenance与退出后零 owned inference/publisher完整
failure_criteria:
  - 候选非唯一、IoU/pose/latency/payload/device/GUI/cleanup 任一失败
invalid_criteria:
  - provenance、domain、partition、output或 FULL_RESTART 污染
provenance:
  source_commit: 2560e8b8db2ecf29ef73f0667952fc0bca42dbd8
  install_overlay: current so101_demo_py plus current worktree so101_mujoco_support and primary project mujoco runtime
  runtime_executable: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install/so101_demo_py/lib/so101_demo_py/rgbd_object_pose
  ros_domain_id: 218
  gz_partition: v5t004-mac-exp018
commands:
  - command: fresh visible MuJoCo task_start stack plus one-shot rgbd_object_pose and acceptance observers
    exit_code: PENDING
observed: [NONE]
inferred: [NONE]
conclusion: PENDING
evidence:
  - /tmp/so101-debug-v5-t004-yolo-seg-20260831/perception-matrix/macos/exp-018-one-cup-distractors
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/perception-matrix/macos/exp-018-one-cup-distractors
decision: PENDING
next_experiment: EXP-019
```

```yaml
experiment_id: EXP-019
status: PLANNED
prior_experiment: EXP-018
hypothesis: macOS MPS 的 two_cups 场景检测两个 plastic_cup 并以 TARGET_AMBIGUOUS 拒绝发布 pose
prediction: matching_count=2；两实例 IoU均>=0.80；无新 /cup_pose
single_variable: 相对 EXP-018 仅 keyframe=v5_two_cups 与期望目标数从1变2
lifecycle: FULL_RESTART
preconditions:
  - source/install=f732afc、weight SHA=f281d252...40781、device=mps、threshold=0.50、imgsz=640
  - ROS_DOMAIN_ID=223、GZ_PARTITION=v5t004-mac-exp019 为空；output不存在
success_criteria:
  - 真实同 stamp 640x480 RGB-D/CameraInfo、finite positive depth、runtime_device=mps
  - TARGET_AMBIGUOUS、matching_count=2、两 cup mask IoU均>=0.80、request_latency_ms<=2000、无新 /cup_pose
  - overlay分开标出两实例；安装态 provenance与退出后零 owned inference/pose publisher完整
failure_criteria:
  - 非两个匹配、发布 pose、IoU/latency/payload/device/GUI/cleanup 任一失败
invalid_criteria:
  - provenance、domain、partition、output或 FULL_RESTART 污染
provenance:
  source_commit: f732afc4b9a569009864df65b766d7f3cdcaaf21
  install_overlay: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install
  runtime_executable: install/so101_demo_py/lib/so101_demo_py/rgbd_object_pose
  ros_domain_id: 223
  gz_partition: v5t004-mac-exp019
commands:
  - command: fresh visible MuJoCo v5_two_cups stack plus one-shot rgbd_object_pose and acceptance observers
    exit_code: PENDING
observed: [NONE]
inferred: [NONE]
conclusion: PENDING
evidence:
  - /tmp/so101-debug-v5-t004-yolo-seg-20260831/perception-matrix/macos/exp-019-two-cups
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/perception-matrix/macos/exp-019-two-cups
decision: PENDING
next_experiment: EXP-020
```

```yaml
experiment_id: EXP-020
status: PLANNED
prior_experiment: EXP-019
hypothesis: macOS MPS 的 cup_adjacent_bottle 场景可分离相邻同色物体并唯一定位 plastic_cup
prediction: matching_count=1；cup mask不含瓶子；IoU>=0.80；world error<0.01m；新鲜 pose
single_variable: 相对 EXP-019 仅 keyframe=v5_cup_near_bottle 与期望目标数从2变1
lifecycle: FULL_RESTART
preconditions:
  - source/install=f732afc、weight SHA=f281d252...40781、device=mps、threshold=0.50、imgsz=640
  - ROS_DOMAIN_ID=224、GZ_PARTITION=v5t004-mac-exp020 为空；output不存在
success_criteria:
  - 真实同 stamp 640x480 RGB-D/CameraInfo、finite positive depth、exact-stamp tf2、runtime_device=mps
  - matching_count=1、cup mask IoU>=0.80且不含瓶子 truth pixels、world error<0.01m、latency<=2000、新鲜 /cup_pose
  - overlay清楚分离杯/瓶；安装态 provenance与退出后零 owned inference/publisher完整
failure_criteria:
  - 杯瓶粘连或候选非唯一，及 pose/IoU/latency/payload/device/GUI/cleanup 任一失败
invalid_criteria:
  - provenance、domain、partition、output或 FULL_RESTART 污染
provenance:
  source_commit: f732afc4b9a569009864df65b766d7f3cdcaaf21
  install_overlay: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install
  runtime_executable: install/so101_demo_py/lib/so101_demo_py/rgbd_object_pose
  ros_domain_id: 224
  gz_partition: v5t004-mac-exp020
commands:
  - command: fresh visible MuJoCo v5_cup_near_bottle stack plus one-shot rgbd_object_pose and acceptance observers
    exit_code: PENDING
observed: [NONE]
inferred: [NONE]
conclusion: PENDING
evidence:
  - /tmp/so101-debug-v5-t004-yolo-seg-20260831/perception-matrix/macos/exp-020-cup-adjacent-bottle
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/perception-matrix/macos/exp-020-cup-adjacent-bottle
decision: PENDING
next_experiment: EXP-021
```

```yaml
experiment_id: EXP-021
status: PLANNED
prior_experiment: EXP-020
hypothesis: Linux CUDA 的 bottle_only 场景不会把橙色瓶子误判为 plastic_cup，也不会发布新 /cup_pose
prediction: TARGET_NOT_FOUND；matching_count=0；无新 pose；真实 RGB-D 与 cleanup 合格
single_variable: 相对 EXP-017 仅平台/device变为 Linux CUDA
lifecycle: FULL_RESTART
preconditions:
  - source/install=f732afc、weight SHA=f281d252...40781、device=cuda、threshold=0.50、imgsz=640
  - ROS_DOMAIN_ID=231、GZ_PARTITION=v5t004-linux-exp021 为空；output不存在
success_criteria:
  - 真实同 stamp 640x480 rgb8/32FC1/CameraInfo、finite positive depth、runtime_device=cuda
  - TARGET_NOT_FOUND、matching_count=0、无新 /cup_pose、latency<=2000；overlay/truth/provenance/cleanup完整
failure_criteria:
  - 误选瓶子、发布 pose、payload/device/latency/GUI/cleanup 任一失败
invalid_criteria:
  - provenance、domain、partition、output或 FULL_RESTART 污染
provenance:
  source_commit: f732afc4b9a569009864df65b766d7f3cdcaaf21
  install_overlay: /data/work/ws_moveit-v5-t004/install
  runtime_executable: /data/work/ws_moveit-v5-t004/install/so101_demo_py/lib/so101_demo_py/rgbd_object_pose
  ros_domain_id: 231
  gz_partition: v5t004-linux-exp021
commands:
  - command: fresh visible MuJoCo v5_no_cup stack plus one-shot rgbd_object_pose and acceptance observers
    exit_code: PENDING
observed: [NONE]
inferred: [NONE]
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/perception-matrix/linux/exp-021-bottle-only
decision: PENDING
next_experiment: EXP-022
```

```yaml
experiment_id: EXP-022
status: PLANNED
prior_experiment: EXP-021
hypothesis: Linux CUDA 的 one_cup_distractors 场景唯一选择 plastic_cup 并从真实 Depth 发布准确 /cup_pose
prediction: matching_count=1；IoU>=0.80；world error<0.01m；新鲜 pose
single_variable: 相对 EXP-021 仅 keyframe=task_start 与期望目标数从0变1
lifecycle: FULL_RESTART
preconditions:
  - source/install=f732afc、weight SHA=f281d252...40781、device=cuda、threshold=0.50、imgsz=640
  - ROS_DOMAIN_ID=232、GZ_PARTITION=v5t004-linux-exp022 为空；output不存在
success_criteria:
  - 真实同 stamp 640x480 RGB-D/CameraInfo、finite positive depth、exact-stamp tf2、runtime_device=cuda
  - matching_count=1、IoU>=0.80、world error<0.01m、latency<=2000、新鲜 /cup_pose；GUI/provenance/cleanup完整
failure_criteria:
  - 候选非唯一、IoU/pose/latency/payload/device/GUI/cleanup 任一失败
invalid_criteria:
  - provenance、domain、partition、output或 FULL_RESTART 污染
provenance:
  source_commit: f732afc4b9a569009864df65b766d7f3cdcaaf21
  install_overlay: /data/work/ws_moveit-v5-t004/install
  runtime_executable: /data/work/ws_moveit-v5-t004/install/so101_demo_py/lib/so101_demo_py/rgbd_object_pose
  ros_domain_id: 232
  gz_partition: v5t004-linux-exp022
commands:
  - command: fresh visible MuJoCo task_start stack plus one-shot rgbd_object_pose and acceptance observers
    exit_code: PENDING
observed: [NONE]
inferred: [NONE]
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/perception-matrix/linux/exp-022-one-cup-distractors
decision: PENDING
next_experiment: EXP-023
```

```yaml
experiment_id: EXP-023
status: PLANNED
prior_experiment: EXP-022
hypothesis: Linux CUDA 的 two_cups 场景检测两个 plastic_cup 并以 TARGET_AMBIGUOUS 拒绝发布 pose
prediction: matching_count=2；两实例 IoU均>=0.80；无新 /cup_pose
single_variable: 相对 EXP-022 仅 keyframe=v5_two_cups 与期望目标数从1变2
lifecycle: FULL_RESTART
preconditions:
  - source/install=f732afc、weight SHA=f281d252...40781、device=cuda、threshold=0.50、imgsz=640
  - ROS_DOMAIN_ID=233、GZ_PARTITION=v5t004-linux-exp023 为空；output不存在
success_criteria:
  - 真实同 stamp 640x480 RGB-D/CameraInfo、finite positive depth、runtime_device=cuda
  - TARGET_AMBIGUOUS、matching_count=2、两 mask IoU均>=0.80、latency<=2000、无新 /cup_pose；GUI/provenance/cleanup完整
failure_criteria:
  - 非两个匹配、发布 pose、IoU/latency/payload/device/GUI/cleanup 任一失败
invalid_criteria:
  - provenance、domain、partition、output或 FULL_RESTART 污染
provenance:
  source_commit: f732afc4b9a569009864df65b766d7f3cdcaaf21
  install_overlay: /data/work/ws_moveit-v5-t004/install
  runtime_executable: /data/work/ws_moveit-v5-t004/install/so101_demo_py/lib/so101_demo_py/rgbd_object_pose
  ros_domain_id: 233
  gz_partition: v5t004-linux-exp023
commands:
  - command: fresh visible MuJoCo v5_two_cups stack plus one-shot rgbd_object_pose and acceptance observers
    exit_code: PENDING
observed: [NONE]
inferred: [NONE]
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/perception-matrix/linux/exp-023-two-cups
decision: PENDING
next_experiment: EXP-024
```

```yaml
experiment_id: EXP-024
status: PLANNED
prior_experiment: EXP-023
hypothesis: Linux CUDA 的 cup_adjacent_bottle 场景可分离相邻同色物体并唯一定位 plastic_cup
prediction: matching_count=1；cup mask不含瓶子；IoU>=0.80；world error<0.01m；新鲜 pose
single_variable: 相对 EXP-023 仅 keyframe=v5_cup_near_bottle 与期望目标数从2变1
lifecycle: FULL_RESTART
preconditions:
  - source/install=f732afc、weight SHA=f281d252...40781、device=cuda、threshold=0.50、imgsz=640
  - ROS_DOMAIN_ID=234、GZ_PARTITION=v5t004-linux-exp024 为空；output不存在
success_criteria:
  - 真实同 stamp 640x480 RGB-D/CameraInfo、finite positive depth、exact-stamp tf2、runtime_device=cuda
  - matching_count=1、cup mask IoU>=0.80且不含瓶子 truth pixels、world error<0.01m、latency<=2000、新鲜 /cup_pose
  - overlay清楚分离杯/瓶；安装态 provenance与退出后零 owned inference/publisher完整
failure_criteria:
  - 杯瓶粘连或候选非唯一，及 pose/IoU/latency/payload/device/GUI/cleanup 任一失败
invalid_criteria:
  - provenance、domain、partition、output或 FULL_RESTART 污染
provenance:
  source_commit: f732afc4b9a569009864df65b766d7f3cdcaaf21
  install_overlay: /data/work/ws_moveit-v5-t004/install
  runtime_executable: /data/work/ws_moveit-v5-t004/install/so101_demo_py/lib/so101_demo_py/rgbd_object_pose
  ros_domain_id: 234
  gz_partition: v5t004-linux-exp024
commands:
  - command: fresh visible MuJoCo v5_cup_near_bottle stack plus one-shot rgbd_object_pose and acceptance observers
    exit_code: PENDING
observed: [NONE]
inferred: [NONE]
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/perception-matrix/linux/exp-024-cup-adjacent-bottle
decision: PENDING
next_experiment: EXP-025
```

```yaml
experiment_id: EXP-025
status: INVALID
prior_experiment: EXP-017
hypothesis: 显式加载锁定 macOS dylib farm 后，bottle_only 可进入真实 MuJoCo/RGB-D 边界并以 TARGET_NOT_FOUND 拒绝瓶子
prediction: MuJoCo/控制器启动；真实 RGB-D 有效；runtime_device=mps；matching_count=0；无新 /cup_pose
single_variable: 相对 INVALID EXP-017 仅增加 DYLD_LIBRARY_PATH=/Users/matianyi/ros2_jazzy/macos_dylib_farm/current
lifecycle: FULL_RESTART
preconditions:
  - source/install=f732afc、weight SHA=f281d252...40781、device=mps、threshold=0.50、imgsz=640
  - dylib farm 文件存在且同一插件 dlopen gate通过；ROS_DOMAIN_ID=225、GZ_PARTITION=v5t004-mac-exp025 与 output为空
success_criteria:
  - 640x480 rgb8/32FC1/CameraInfo 同一非零 stamp，frame ID与 finite positive depth有效；runtime_device=mps
  - TARGET_NOT_FOUND、matching_count=0、无新 /cup_pose；request_latency_ms<=2000；瓶子不产生 cup mask
  - exact-window MuJoCo 与 overlay/truth、安装态 provenance、退出后零 owned inference 与零 /cup_pose publisher完整
failure_criteria:
  - 误选瓶子、发布 pose、payload/device/latency/GUI/cleanup 任一失败
invalid_criteria:
  - domain/partition/output/source/install/input provenance 污染、dylib加载失败或进程图非 FULL_RESTART
provenance:
  source_commit: f732afc4b9a569009864df65b766d7f3cdcaaf21
  install_overlay: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install
  runtime_executable: install/so101_demo_py/lib/so101_demo_py/rgbd_object_pose
  ros_domain_id: 225
  gz_partition: v5t004-mac-exp025
commands:
  - command: export locked dylib farm; fresh visible MuJoCo v5_no_cup stack plus one-shot rgbd_object_pose and acceptance observers
    exit_code: SIGINT_AFTER_INVALID_BOUNDARY
observed:
  - domain 225、local/remote output 与 task process为空；Mac install、weight hash、MPS available=true 已回读
  - 锁定 dylib farm 文件存在，显式 DYLD_LIBRARY_PATH 下 libmujoco_ros2_control.dylib dlopen gate通过
  - 正确插件加载 v5_multi_object_scene.xml，但普通 Codex 子进程两次在10秒 UI task期限内报告 Timed out waiting to start simulation rendering
  - 未创建 Viewer、未激活控制器、无真实 RGB-D 或模型请求；确认边界后 SIGINT，domain 225 与 owned PID清空
  - 26558-byte launch.log 与分进程日志已同步正式 evidence root
inferred: [NONE]
conclusion: INVALID；缺少已验证的 macOS Aqua main-thread 启动上下文，不支持感知结论
evidence:
  - /tmp/so101-debug-v5-t004-yolo-seg-20260831/perception-matrix/macos/exp-025-bottle-only
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/perception-matrix/macos/exp-025-bottle-only
decision: PRESERVE；以新 ID EXP-026 仅改用 launchctl asuser 501 Aqua zsh
next_experiment: EXP-026
```

```yaml
experiment_id: EXP-026
status: INVALID
prior_experiment: EXP-025
hypothesis: launchctl asuser 501 的 Aqua zsh 可让正确插件在 macOS main thread执行 UI task，进而为 bottle_only 发布真实 RGB-D
prediction: Viewer可见、controllers active、RGB-D有效；MPS输出 TARGET_NOT_FOUND，且无 /cup_pose
single_variable: 相对 INVALID EXP-025 仅把 stack owner 从普通 Codex子进程改为 launchctl asuser 501 Aqua zsh；overlay/device/model/scene不变
lifecycle: FULL_RESTART
preconditions:
  - source/install=f732afc、weight SHA=f281d252...40781、device=mps、threshold=0.50、imgsz=640
  - primary mujoco runtime、dylib farm、Aqua uid=501 已回读；ROS_DOMAIN_ID=226、GZ_PARTITION=v5t004-mac-exp026 与 output为空
success_criteria:
  - Aqua launch日志证明 main-thread UI task、Viewer与三 controllers；真实同stamp 640x480 rgb8/32FC1/CameraInfo及finite positive depth
  - runtime_device=mps、TARGET_NOT_FOUND、matching_count=0、request_latency_ms<=2000、无新 /cup_pose
  - exact-window MuJoCo与overlay/truth、安装态 provenance、退出后零 owned process/publisher完整
failure_criteria:
  - Viewer/controller/payload/not-found/device/latency/GUI/cleanup 任一失败
invalid_criteria:
  - Aqua PID/env/domain/partition/output/source/install provenance污染或非 FULL_RESTART
provenance:
  source_commit: f732afc4b9a569009864df65b766d7f3cdcaaf21
  install_overlay: current so101_demo_py plus primary project mujoco runtime
  runtime_executable: install/so101_demo_py/lib/so101_demo_py/rgbd_object_pose
  ros_domain_id: 226
  gz_partition: v5t004-mac-exp026
commands:
  - command: launchctl asuser 501 /bin/zsh -lc with explicit ROS/current overlay/perception/DYLD environment; launch v5_no_cup and run observers
    exit_code: 1
observed:
  - gui/501=session Aqua、WindowServer PID 599；domain 226、local/remote output 与 task process为空
  - primary mujoco runtime、dylib dlopen、current so101 install、weight hash、MPS available=true 已回读
  - Aqua wrapper PID 21861 在 ros2 launch 前退出；set -u使 setup.zsh 的可选 COLCON_TRACE 与空 PYTHONPATH触发 parameter not set
  - 没有 ROS/MuJoCo child、没有 topic/output；467-byte stack.log 与PID已同步正式 evidence root
inferred: [NONE]
conclusion: INVALID；harness nounset不兼容，未执行产品路径
evidence:
  - /tmp/so101-debug-v5-t004-yolo-seg-20260831/perception-matrix/macos/exp-026-bottle-only
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/perception-matrix/macos/exp-026-bottle-only
decision: PRESERVE；以新 ID EXP-027 仅移除 nounset并安全处理空 PYTHONPATH
next_experiment: EXP-027
```

```yaml
experiment_id: EXP-027
status: INVALID
prior_experiment: EXP-026
hypothesis: 兼容 ROS setup 的 gui/501 Aqua wrapper 可执行 macOS main-thread UI task，并让 bottle_only 到达真实 RGB-D/MPS not-found边界
prediction: Viewer可见、controllers active、RGB-D有效；MPS TARGET_NOT_FOUND且无 /cup_pose
single_variable: 相对 INVALID EXP-026 仅移除 wrapper nounset并用 ${PYTHONPATH:-}；产品环境和参数不变
lifecycle: FULL_RESTART
preconditions:
  - source/install=f732afc、weight SHA=f281d252...40781、device=mps、threshold=0.50、imgsz=640
  - gui/501 Aqua、primary runtime/dylib/MPS gate通过；ROS_DOMAIN_ID=227、GZ_PARTITION=v5t004-mac-exp027 与 output为空
success_criteria:
  - Aqua launch证明 main-thread UI、Viewer、三 controllers；真实同stamp 640x480 rgb8/32FC1/CameraInfo 与 finite positive depth
  - runtime_device=mps、TARGET_NOT_FOUND、matching_count=0、latency<=2000、无新 /cup_pose
  - exact-window MuJoCo和overlay/truth、安装态 provenance、退出后零 owned process/publisher完整
failure_criteria:
  - Viewer/controller/payload/not-found/device/latency/GUI/cleanup 任一失败
invalid_criteria:
  - wrapper/Aqua PID/env/domain/partition/output/source/install provenance污染或非 FULL_RESTART
provenance:
  source_commit: f732afc4b9a569009864df65b766d7f3cdcaaf21
  install_overlay: current so101_demo_py plus primary project mujoco runtime
  runtime_executable: install/so101_demo_py/lib/so101_demo_py/rgbd_object_pose
  ros_domain_id: 227
  gz_partition: v5t004-mac-exp027
commands:
  - command: compatible launchctl asuser 501 Aqua zsh; launch v5_no_cup, then payload/perception/visual/cleanup observers
    exit_code: 1
observed:
  - wrapper syntax、gui/501 Aqua、domain 227、local/remote output absence 与 task process isolation通过
  - 产品 source/install/weight/device/scene/threshold 与 EXP-026 不变
  - Aqua owner PID 23072 在任何 ROS child、topic或产品输出产生前退出；stack.log为空，domain 227无节点
  - 空 stack.log与PID文件已同步正式 evidence root；未删除任何无效证据
inferred: [NONE]
conclusion: INVALID；wrapper errexit在 source chain中静默退出，未执行产品路径
evidence:
  - /tmp/so101-debug-v5-t004-yolo-seg-20260831/perception-matrix/macos/exp-027-bottle-only
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/perception-matrix/macos/exp-027-bottle-only
decision: PRESERVE；以新 ID EXP-028 仅移除 wrapper errexit，产品参数不变
next_experiment: EXP-028
```

```yaml
experiment_id: EXP-028
status: INVALID
prior_experiment: EXP-027
hypothesis: 不启用 errexit/nounset 的 gui/501 Aqua wrapper 可执行 macOS main-thread UI task，并让 bottle_only 到达真实 RGB-D/MPS not-found边界
prediction: Viewer可见、controllers active、RGB-D有效；MPS TARGET_NOT_FOUND且无 /cup_pose
single_variable: 相对 INVALID EXP-027 仅移除 wrapper errexit；产品环境和参数不变
lifecycle: FULL_RESTART
preconditions:
  - source/install=f732afc、weight SHA=f281d252...40781、device=mps、threshold=0.50、imgsz=640
  - gui/501 Aqua、相同完整 source/dylib/MPS 环境链预检通过；ROS_DOMAIN_ID=228、GZ_PARTITION=v5t004-mac-exp028 与 output为空
success_criteria:
  - Aqua launch证明 main-thread UI、Viewer、三 controllers；真实同stamp 640x480 rgb8/32FC1/CameraInfo 与 finite positive depth
  - runtime_device=mps、TARGET_NOT_FOUND、matching_count=0、latency<=2000、无新 /cup_pose
  - exact-window MuJoCo和overlay/truth、安装态 provenance、退出后零 owned process/publisher完整
failure_criteria:
  - Viewer/controller/payload/not-found/device/latency/GUI/cleanup 任一失败
invalid_criteria:
  - wrapper/Aqua PID/env/domain/partition/output/source/install provenance污染或非 FULL_RESTART
provenance:
  source_commit: f732afc4b9a569009864df65b766d7f3cdcaaf21
  install_overlay: current so101_demo_py plus primary project mujoco runtime
  runtime_executable: install/so101_demo_py/lib/so101_demo_py/rgbd_object_pose
  ros_domain_id: 228
  gz_partition: v5t004-mac-exp028
commands:
  - command: launchctl asuser 501 Aqua zsh without strict shell flags; launch v5_no_cup, then payload/perception/visual/cleanup observers
    exit_code: 1
observed:
  - 同一 Aqua source/dylib/MPS 环境链的 env-only预检通过；session=0、dlopen_ok=1、MPS available=true
  - 后台 owner PID 25556静默退出；前台xtrace证明完整 source chain和ros2 launch可达
  - ros2_control_node加载正确 v5_multi_object_scene.xml，但等待 process main-thread UI task两次10秒超时；没有Viewer/controllers/RGB-D/model请求
  - 自有 launch PID 25887经SIGINT退出，任务进程清空；43 MB xtrace与ROS分进程日志已同步正式 evidence root
inferred: [NONE]
conclusion: INVALID；无PTY的Aqua宿主未执行main-thread UI task，未到达产品感知边界
evidence:
  - /tmp/so101-debug-v5-t004-yolo-seg-20260831/perception-matrix/macos/exp-028-bottle-only
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/perception-matrix/macos/exp-028-bottle-only
decision: PRESERVE；以新 ID EXP-029 仅将宿主改为前台 tty=true，产品参数不变
next_experiment: EXP-029
```

```yaml
experiment_id: EXP-029
status: INVALID
prior_experiment: EXP-028
hypothesis: launchctl asuser 501 的前台 PTY 宿主可执行 macOS process-main-thread UI task，并让 bottle_only 到达真实 RGB-D/MPS not-found边界
prediction: Viewer可见、controllers active、RGB-D有效；MPS TARGET_NOT_FOUND且无 /cup_pose
single_variable: 相对 INVALID EXP-028 仅把 Aqua执行宿主改为 foreground tty=true；产品环境和参数不变
lifecycle: FULL_RESTART
preconditions:
  - source/install=f732afc、weight SHA=f281d252...40781、device=mps、threshold=0.50、imgsz=640
  - gui/501 Aqua、完整 source/dylib/MPS 环境链通过；ROS_DOMAIN_ID=229、GZ_PARTITION=v5t004-mac-exp029 与 output为空
success_criteria:
  - 前台PTY launch证明 main-thread UI、Viewer、三 controllers；真实同stamp 640x480 rgb8/32FC1/CameraInfo 与 finite positive depth
  - runtime_device=mps、TARGET_NOT_FOUND、matching_count=0、latency<=2000、无新 /cup_pose
  - exact-window MuJoCo和overlay/truth、安装态 provenance、退出后零 owned process/publisher完整
failure_criteria:
  - Viewer/controller/payload/not-found/device/latency/GUI/cleanup 任一失败
invalid_criteria:
  - foreground PTY/Aqua/env/domain/partition/output/source/install provenance污染或非 FULL_RESTART
provenance:
  source_commit: f732afc4b9a569009864df65b766d7f3cdcaaf21
  install_overlay: current so101_demo_py plus primary project mujoco runtime
  runtime_executable: install/so101_demo_py/lib/so101_demo_py/rgbd_object_pose
  ros_domain_id: 229
  gz_partition: v5t004-mac-exp029
commands:
  - command: launchctl asuser 501 Aqua foreground tty=true; launch v5_no_cup, then payload/perception/visual/cleanup observers
    exit_code: 1
observed:
  - 前台 PTY owner PID 27680进入ros2 launch；可执行文件来自主安装并等待process main-thread UI task
  - 仍两次出现10秒渲染握手超时；没有Submitting/Running UI task、Viewer、controllers或RGB-D
  - farm首位libmujoco_ros2_control.dylib实际链接旧 ws_mujoco_ros2_control_fork，而可执行文件链接主安装dispatcher；二进制全局状态不一致
  - Ctrl-C后所有分进程cleanly退出，domain 229无节点；ROS日志已同步正式 evidence root
inferred: [NONE]
conclusion: INVALID；动态库 provenance污染，未执行单一dispatcher产品路径
evidence:
  - /tmp/so101-debug-v5-t004-yolo-seg-20260831/perception-matrix/macos/exp-029-bottle-only
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/perception-matrix/macos/exp-029-bottle-only
decision: PRESERVE；以新 ID EXP-030 仅修正主安装dylib优先级，其他参数不变
next_experiment: EXP-030
```

```yaml
experiment_id: EXP-030
status: INVALID
prior_experiment: EXP-029
hypothesis: 当前主安装的 core/plugin/support dylib优先于共享farm后，前台PTY Aqua宿主可完成main-thread UI并让 bottle_only 到达真实 RGB-D/MPS not-found边界
prediction: 主安装core与dispatcher一致；Viewer可见、controllers active、RGB-D有效；MPS TARGET_NOT_FOUND且无 /cup_pose
single_variable: 相对 INVALID EXP-029 仅调整 DYLD_LIBRARY_PATH，把当前主安装core/plugin/support目录置于共享farm前
lifecycle: FULL_RESTART
preconditions:
  - source/install=f732afc、weight SHA=f281d252...40781、device=mps、threshold=0.50、imgsz=640
  - gui/501 foreground PTY；ROS_DOMAIN_ID=230、GZ_PARTITION=v5t004-mac-exp030 与两端output为空
  - 主安装 libmujoco_ros2_control.dylib 与 dispatcher存在；farm core symlink的旧fork污染已显式记录
success_criteria:
  - 日志出现Submitting/Running UI task、主安装core provenance、Viewer、三controllers；真实同stamp 640x480 rgb8/32FC1/CameraInfo与finite positive depth
  - runtime_device=mps、TARGET_NOT_FOUND、matching_count=0、latency<=2000、无新 /cup_pose
  - exact-window MuJoCo和overlay/truth、安装态 provenance、退出后零 owned process/publisher完整
failure_criteria:
  - 单一dispatcher/Viewer/controller/payload/not-found/device/latency/GUI/cleanup任一失败
invalid_criteria:
  - foreground PTY/Aqua/dylib/domain/partition/output/source/install provenance污染或非 FULL_RESTART
provenance:
  source_commit: f732afc4b9a569009864df65b766d7f3cdcaaf21
  install_overlay: current so101_demo_py plus primary project mujoco runtime
  runtime_executable: install/so101_demo_py/lib/so101_demo_py/rgbd_object_pose
  ros_domain_id: 230
  gz_partition: v5t004-mac-exp030
commands:
  - command: launchctl asuser 501 Aqua foreground tty=true with primary dylibs first; launch v5_no_cup, then payload/perception/visual/cleanup observers
    exit_code: 1
observed:
  - 前台PTY启动；主安装core被pluginlib选中，不再加载旧core
  - 主core所需SetFreeJointState typesupport符号却从旧fork msgs dylib解析并失败；未进入UI task/Viewer/controller/RGB-D
  - overlay自动DYLD包含主安装support/core/plugins/msgs完整闭包，但EXP-030手工把farm插在msgs之前
  - Ctrl-C后全部child cleanly退出，domain 230无节点；ROS日志已同步正式 evidence root
inferred: [NONE]
conclusion: INVALID；只修正core而未保持完整同世代依赖闭包，未执行产品路径
evidence:
  - /tmp/so101-debug-v5-t004-yolo-seg-20260831/perception-matrix/macos/exp-030-bottle-only
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/perception-matrix/macos/exp-030-bottle-only
decision: PRESERVE；以新 ID EXP-031 仅把farm移动到完整自动DYLD闭包之后
next_experiment: EXP-031
```

```yaml
experiment_id: EXP-031
status: FAILED_VALID
prior_experiment: EXP-030
hypothesis: 保留overlay生成的完整DYLD依赖闭包并把共享farm追加到末尾，可让前台PTY Aqua完成main-thread UI并让 bottle_only 到达真实 RGB-D/MPS not-found边界
prediction: core/msgs/plugins/dispatcher同属主安装；Viewer可见、controllers active、RGB-D有效；MPS TARGET_NOT_FOUND且无 /cup_pose
single_variable: 相对 INVALID EXP-030 仅把共享farm从自动overlay闭包之前移动到闭包末尾
lifecycle: FULL_RESTART
preconditions:
  - source/install=f732afc、weight SHA=f281d252...40781、device=mps、threshold=0.50、imgsz=640
  - gui/501 foreground PTY；ROS_DOMAIN_ID=231、GZ_PARTITION=v5t004-mac-exp031 与两端output为空
  - 自动DYLD已包含主安装support/core/plugins/msgs目录；farm旧fork污染仅作为最终fallback
success_criteria:
  - 日志出现Submitting/Running UI task、Viewer、三controllers；真实同stamp 640x480 rgb8/32FC1/CameraInfo与finite positive depth
  - runtime_device=mps、TARGET_NOT_FOUND、matching_count=0、latency<=2000、无新 /cup_pose
  - exact-window MuJoCo和overlay/truth、安装态 provenance、退出后零 owned process/publisher完整
failure_criteria:
  - 依赖闭包/UI/Viewer/controller/payload/not-found/device/latency/GUI/cleanup任一失败
invalid_criteria:
  - foreground PTY/Aqua/dylib/domain/partition/output/source/install provenance污染或非 FULL_RESTART
provenance:
  source_commit: f732afc4b9a569009864df65b766d7f3cdcaaf21
  install_overlay: current so101_demo_py plus primary project mujoco runtime
  runtime_executable: install/so101_demo_py/lib/so101_demo_py/rgbd_object_pose
  ros_domain_id: 231
  gz_partition: v5t004-mac-exp031
commands:
  - command: launchctl asuser 501 Aqua foreground tty=true with overlay DYLD closure then farm; launch v5_no_cup, then payload/perception/visual/cleanup observers
    exit_code: 1
observed:
  - 主安装core/msgs/plugins/dispatcher同世代；日志出现Submitting/Running UI task、main-thread GLFW、Sim ready与10Hz CameraPlugin
  - 三controllers active；RGB-D probe记录10.0Hz、640x480、rgb8/32FC1、同stamp、307200/307200 finite positive depth
  - exact-window ID 3498显示v5_no_cup仅橙色瓶子与干扰物，Viewer status Running
  - 普通受限shell的首次MPS请求INVALID并在产品前DEVICE_UNAVAILABLE；Aqua probe确认torch MPS=true并执行正式adapter
  - Aqua MPS请求返回TARGET_NOT_FOUND、matching=0、published_cup_pose=false、inference=412.80ms、相同weight SHA
  - 但conf=0.0产生297个约0.00候选，overlay被标签覆盖且request_latency=3033.05ms>2000；observer因25秒早于约60秒冷启动而未收到短暂topic
  - stack Ctrl-C exit 0、全部child cleanly退出、domain 231无节点；完整证据已同步正式 root
inferred: [NONE]
conclusion: FAILED_VALID；目标拒绝正确，但候选噪声导致overlay和请求延迟两项产品门禁失败
evidence:
  - /tmp/so101-debug-v5-t004-yolo-seg-20260831/perception-matrix/macos/exp-031-bottle-only
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/perception-matrix/macos/exp-031-bottle-only
decision: PRESERVE；TDD修复detector候选下限后以新ID EXP-032 FULL_RESTART
next_experiment: EXP-032
```

```yaml
experiment_id: EXP-032
status: INVALID
prior_experiment: EXP-031
hypothesis: YOLO标准candidate floor=0.25可在保持所有模型候选与selector 0.50边界的同时，让 bottle_only overlay清晰且request_latency<=2000
prediction: candidate_count=0、matching_count=0、TARGET_NOT_FOUND、runtime_device=mps、request_latency<=2000、无/cup_pose
single_variable: 相对 FAILED_VALID EXP-031 仅把YoloSegDetector model candidate floor从0.0改为0.25；场景、权重、selector阈值与平台不变
lifecycle: FULL_RESTART
preconditions:
  - candidate-floor patch经RED/GREEN与包级890/890；Mac install重建；Linux install必须在运行前同步重建
  - weight SHA=f281d252...40781、device=mps、selector threshold=0.50、imgsz=640
  - gui/501 foreground PTY、完整overlay DYLD闭包后接farm；ROS_DOMAIN_ID=232、GZ_PARTITION=v5t004-mac-exp032与两端output为空
success_criteria:
  - 主安装闭包、main-thread UI、Viewer、三controllers；真实同stamp 640x480 rgb8/32FC1/CameraInfo与finite positive depth
  - runtime_device=mps、TARGET_NOT_FOUND、candidate_count=0、matching_count=0、request_latency<=2000、无新/cup_pose
  - detections与overlay topic被120秒observer接收；overlay清晰、exact-window MuJoCo、退出后零owned process/publisher完整
failure_criteria:
  - 候选/延迟/Viewer/controller/payload/not-found/device/topic/GUI/cleanup任一失败
invalid_criteria:
  - source/install/foreground PTY/Aqua/dylib/domain/partition/output/FULL_RESTART或observer窗口污染
provenance:
  source_commit: eb4d99124277a01ffec9ab705c9f7280005a0427
  install_overlay: current so101_demo_py plus current worktree so101_mujoco_support and primary project mujoco runtime
  runtime_executable: install/so101_demo_py/lib/so101_demo_py/rgbd_object_pose
  ros_domain_id: 232
  gz_partition: v5t004-mac-exp032
commands:
  - command: FULL_RESTART v5_no_cup plus 120s topic observer and Aqua MPS one-shot request
    exit_code: stack=0, first_request=127, second_request=1, observer=1
observed:
  - main-thread UI、CameraPlugin 10Hz、三controllers active；640x480 rgb8/32FC1同stamp，finite positive depth=307200/307200
  - exact-window ID 3519显示bottle-only与Viewer Running；Ctrl-C后MoveIt/MuJoCo clean，domain 232无节点
  - 首次Aqua请求使用非绝对console script导致command not found；绝对入口重试在warmup后返回INFERENCE_FAILED
  - result candidate_count=0但model/device/weight为空且无detections/overlay；源码与RED测试确认Ultralytics零候选masks=None被转换器拒绝
inferred: [NONE]
conclusion: INVALID；启动入口重试与零候选契约污染正式结果，不能纳入四场景矩阵
evidence:
  - /tmp/so101-debug-v5-t004-yolo-seg-20260831/perception-matrix/macos/exp-032-bottle-only
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/perception-matrix/macos/exp-032-bottle-only
decision: PRESERVE；4d0b6e3按TDD修复后以新ID EXP-033 FULL_RESTART
next_experiment: EXP-033
```

```yaml
experiment_id: EXP-033
status: FAILED_VALID
prior_experiment: EXP-032
hypothesis: 仅在零候选时接受Ultralytics masks=None，可发布空detections与清晰overlay，并由selector稳定返回TARGET_NOT_FOUND
prediction: candidate_count=0、matching_count=0、TARGET_NOT_FOUND、runtime_device=mps、request_latency<=2000、observer detections>=1/overlay>=1/cup_pose=0
single_variable: 相对INVALID EXP-032仅source/install从eb4d991改为4d0b6e3并使用已确认绝对入口；场景、权重、阈值、Aqua和设备不变
lifecycle: FULL_RESTART
preconditions:
  - Mac package 891/891；Linux adapter22/22与CUDA gate；双平台install均回读4d0b6e3零mask分支
  - weight SHA=f281d252...40781、device=mps、selector threshold=0.50、imgsz=640
  - gui/501 foreground PTY、完整overlay DYLD闭包后接farm；ROS_DOMAIN_ID=220、GZ_PARTITION=v5t004-mac-exp033与新output为空
success_criteria:
  - main-thread UI、Viewer、三controllers；真实同stamp 640x480 rgb8/32FC1/CameraInfo与finite positive depth
  - runtime_device=mps、TARGET_NOT_FOUND、candidate_count=0、matching_count=0、request_latency<=2000、无新/cup_pose
  - detections与overlay topic被120秒observer接收；overlay清晰、exact-window MuJoCo、退出后零owned process/publisher完整
failure_criteria:
  - 候选/延迟/Viewer/controller/payload/not-found/device/topic/GUI/cleanup任一失败
invalid_criteria:
  - source/install/foreground PTY/Aqua/dylib/domain/partition/output/FULL_RESTART或observer窗口污染
provenance:
  source_commit: 4d0b6e35e0b4754da4bc03d1038c3f928eac3ccc
  install_overlay: current so101_demo_py plus current worktree so101_mujoco_support and primary project mujoco runtime
  runtime_executable: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install/so101_demo_py/lib/so101_demo_py/rgbd_object_pose
  ros_domain_id: 220
  gz_partition: v5t004-mac-exp033
commands:
  - command: FULL_RESTART v5_no_cup plus 120s topic observer and Aqua MPS absolute installed entrypoint
    exit_code: stack=0, request=1, observer=1
observed:
  - main-thread UI、CameraPlugin 9.98Hz、三controllers active；640x480 rgb8/32FC1同stamp，finite positive depth=307200/307200
  - exact-window ID 3540显示bottle-only与Viewer Running；Ctrl-C后MoveIt/MuJoCo clean，domain 220无节点
  - MPS结果candidate=0、matching=0、TARGET_NOT_FOUND、published=false、inference=179.19ms、request=201.99ms、weight SHA正确
  - source/overlay PNG均清晰且无噪声标签；但observer 120秒detections=0、overlay=0、cup_pose=0
inferred: [NONE]
conclusion: FAILED_VALID；模型、拒绝、延迟与视觉通过，但一次性ROS输出未送达外部observer
evidence:
  - /tmp/so101-debug-v5-t004-yolo-seg-20260831/perception-matrix/macos/exp-033-bottle-only
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/perception-matrix/macos/exp-033-bottle-only
decision: PRESERVE；ff8caef按TDD加入subscriber discovery与DDS ack后以新ID EXP-034 FULL_RESTART
next_experiment: EXP-034
```

```yaml
experiment_id: EXP-034
status: VALID
prior_experiment: EXP-033
hypothesis: 在推理前发现detections/overlay订阅者并在发布后等待可靠DDS ack，可让一次性not-found结果被外部observer接收
prediction: candidate_count=0、matching_count=0、TARGET_NOT_FOUND、runtime_device=mps、request_latency<=2000、observer detections>=1/overlay>=1/cup_pose=0
single_variable: 相对FAILED_VALID EXP-033仅source/install从4d0b6e3改为ff8caef；场景、权重、阈值、Aqua、设备与绝对入口不变
lifecycle: FULL_RESTART
preconditions:
  - Mac package 892/892；Linux聚焦23/23与CUDA gate；双平台install均锁定ff8caef
  - weight SHA=f281d252...40781、device=mps、selector threshold=0.50、imgsz=640
  - gui/501 foreground PTY、完整overlay DYLD闭包后接farm；ROS_DOMAIN_ID=219、GZ_PARTITION=v5t004-mac-exp034与新output为空
success_criteria:
  - main-thread UI、Viewer、三controllers；真实同stamp 640x480 rgb8/32FC1/CameraInfo与finite positive depth
  - runtime_device=mps、TARGET_NOT_FOUND、candidate_count=0、matching_count=0、request_latency<=2000、无新/cup_pose
  - detections与overlay topic被120秒observer接收；overlay清晰、exact-window MuJoCo、退出后零owned process/publisher完整
failure_criteria:
  - 候选/延迟/Viewer/controller/payload/not-found/device/topic/GUI/cleanup任一失败
invalid_criteria:
  - source/install/foreground PTY/Aqua/dylib/domain/partition/output/FULL_RESTART或observer窗口污染
provenance:
  source_commit: ff8caef360715b41c0fa57f2e7c4f4b96eb5af5f
  install_overlay: current so101_demo_py plus current worktree so101_mujoco_support and primary project mujoco runtime
  runtime_executable: /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install/so101_demo_py/lib/so101_demo_py/rgbd_object_pose
  ros_domain_id: 219
  gz_partition: v5t004-mac-exp034
commands:
  - command: FULL_RESTART v5_no_cup plus 120s topic observer and Aqua MPS absolute installed entrypoint
    exit_code: stack=0, request=1, observer=0
observed:
  - main-thread UI、CameraPlugin 10Hz、三controllers active；640x480 rgb8/32FC1同stamp，finite positive depth=307200/307200
  - exact-window ID 3561显示bottle-only与Viewer Running；overlay清晰无噪声标签
  - MPS结果candidate=0、matching=0、TARGET_NOT_FOUND、published=false、inference=247.50ms、request=319.31ms、weight SHA正确
  - observer收到detections=1且candidate[0]=0、overlay=1且640x480 rgb8，同stamp，cup_pose=0
  - Ctrl-C后MoveIt GRACEFUL_SHUTDOWN_MOVE_GROUP_OK、MuJoCo主线程资源释放、domain 219无节点
inferred: [NONE]
conclusion: VALID；Mac bottle-only场景通过真实payload、分类拒绝、topic、GUI、性能与cleanup全部门禁
evidence:
  - /tmp/so101-debug-v5-t004-yolo-seg-20260831/perception-matrix/macos/exp-034-bottle-only
  - /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/perception-matrix/macos/exp-034-bottle-only
decision: ACCEPT；纳入Mac四场景感知矩阵
next_experiment: EXP-018
```

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
