# 审查：SO-101 ACT 容器化采集 campaign 设计

审查对象：`docs/superpowers/specs/2026-09-30-so101-act-containerized-campaign-design.md`（本地工作树版本，21.5 KB，含 2026-10-11 新增的“代码基线与设计差异”一节；行号以该文件为准）

审查日期：2026-10-11。方式：只读静态审查。代码对照的是文档自己声明的基线 `origin/codex/so101-act-data-0917a` @ `6baf54e6`（通过子模块 git 数据 `git archive` 到临时目录读取，没有切换或改动工作树）；同时对照了该分支上的 10-03、10-05、10-06、10-07、10-09、10-10 各份修订/设计，以及本地 main 的 10-01。没有运行任何容器、仿真或测试。

## 2026-10-11 用户决定后的更新（优先于下文）

用户对三项 P0 的决定：

1. 本文就是 10-06 所说的“Docker 隔离留待后续版本”。P0-1 降为文字问题：文首应写明这一点，并把 10-06、10-07、10-10 系列列入关联文档。
2. 教师感知只用 YOLO，不回退到 Grounded-SAM。P0-2 的方向已定，但文档需要相应改写：§2 拓扑、§3.1、§7 表格第二行、§8 第 5 步都要删掉 Grounded-SAM image 的选项。去掉现有 `PerceptionPolicy` 的回退分支属于 Worker 感知路径的受控改动，应列入 §8 第 2 步的 Task 8L 重做范围，基线表也要补上这一行。P1-3（Grounded 容量）因此不再适用。
3. 不做资源预算，实际运行资源不足时再找解法。P0-3 撤销；P2-4（staging 体积）同样不再要求预先估算，由现有的资源停点兜底。

**更新后的结论：** 不再有阻断级问题。修完上面三处文字改写，以及下文 P1-1、P1-2、P1-4、P1-5、P1-6 和其余 P2 项后，即可进入实施计划。

## 结论（原始审查）

**方向合理，但不建议按现稿冻结进入实施计划。**

优点：分层清楚（Host 唯一资源所有者、共享推理服务不碰 lease/journal、Worker 保留搜索状态机和安全判断），request ID / generation / reset epoch 的迟到响应拒绝规则写得严密，故障表区分 Teacher 结果、数据 INVALID 和基础设施失败，与 10-05 分离修订一致。新加的“代码基线”表对 5 个边界的现状描述，我逐条核对过，**基本属实**（见附录）。

需要先解决的是三类问题：

1. **与分支上更新的设计存在上位冲突，文档没有处理**：10-06 修订明确说“本版不做并行隔离，Docker 隔离留待后续版本，本版不实现、不设计”；10-10 正式采集设计引入了不需要 Head Search 的 `fixed_head_domain_v1`。本文既没引用它们，也没说明自己在什么时候、以什么前提生效。
2. **“每 campaign 选一个教师模型、不做回退”是对现有 Worker 感知逻辑的实质改动，被当成了运维选择**：现有代码是“YOLO 先、Grounded-SAM 至多一次回退”的两阶段策略。基线表漏了这一项，§7 却据此把教师模型切换归为“不重做 Task 8L”。
3. **离线处理改变了 wave 的时间与资源模型，文档没有量化**：10-07 实测离线处理约 580 s / 103.6 s episode、单线程；8 个 shard 同时跑 MuJoCo + 离线处理器 + 共享 GPU 推理，这是 W8 能否过关的核心，但本文只有“按冻结资源停点停下”。

## 问题（按重要性排序）

### P0：冻结前必须解决

**P0-1 与 10-06 修订“本版不做 Docker 隔离”直接冲突（第 3–17 行、§1 第 35 行）**

- 事实：分支上的 `2026-10-06-so101-teacher-moveit-simplification-amendment.md` §2 原则 3（用户确认）：“当前版本不做并行隔离。单 stack 运行……Docker 隔离留待后续版本，本版不实现、不设计。”它声明对 10-05 冲突时优先。
- 本文只把 10-05 列为“优先修订”，没有提 10-06，也没有提 10-07（raw-log 离线，§6 已实质依赖）和 10-10 的几份设计。第 17 行“与关联文档冲突的……以本文为准”在 10-06 面前方向是反的。
- 建议：在文首写清本文的生效前提，例如“本文是 10-06 所称的‘后续版本’，在单 stack 版本完成 X 验收、并经用户重新批准并行化后才生效”；把 10-06、10-07、10-10 系列加入关联文档并给出优先级。否则实施者无法判断该听谁的。

**P0-2 取消 YOLO→Grounded-SAM 回退是 Worker 逻辑变更，不是运维参数（§3.1 第 67、69 行；§7 第 131 行；§8 第 144 行）**

- 事实：`parallel_batch/perception.py:338` `PerceptionPolicy` 文档串即“Enforce one YOLO stage followed by at most one permitted fallback”；`decide()`（`:428–458`）在 YOLO 为 `NORMAL_REJECTION`/`MODEL_ERROR` 时返回 `REQUEST_MODEL grounded`。`runtime/parallel_ros_ports/perception.py:157` 每个 case 都用这对模型构造策略。Broker 端 `parallel_perception_runtime.py` 也按 `{YOLO_ID, GROUNDED_ID}` 同时加载两模型。
- 本文第 67 行“单个 case 不做 YOLO 到 Grounded-SAM 的自动回退”会改写 `PerceptionPolicy`/`decide`、R6 选择逻辑（`parallel_ros_ports/observations.py:394` 起）和 broker 合同。这属于 §7 第一行“Worker/安全路径的受控源码变化”，应使 Task 8L 失效，但 §7 第 131 行和 §3.1 第 69 行把它归入“教师模型选择不自动重做 Task 8L”。
- 另外，Grounded-only campaign 下 R6 定位器从未在“没有 YOLO 前置”的情况下被验证过；10-10 minimal runtime gates 设计写的 Teacher 输入是“broker 的 YOLO + R6 + z-clip”，也没有覆盖 Grounded-only。
- 建议：基线表加一行“教师感知策略：现为 YOLO + 一次 Grounded 回退”；明确取消回退是一次受控变更，列入 §8 第 2 步的 Task 8L 重做范围；说明 Grounded-only campaign 的 R6/定位验证由谁、在哪一步完成（目前 §8 第 5 步说“不另做 Grounded-SAM W8”，等于没有任何一步验证它）。

**P0-3 离线处理把 wave 吞吐和资源模型改了，但没有预算（§4 第 101 行、§5 资源行、§8 第 4 步）**

- 事实（10-07 修订 §1、§4.2、§7 第 234 行）：首次生产处理器 580 s 处理 103.6 s episode；处理器单线程；ACT 采集 lease/stage 已提到 1500 s，处理等待上限 1200 s；10-07 自己写了“一个 20 episode 的 wave 在 8 个 worker 上时，处理会成为瓶颈”。
- 本文第 101 行规定 shard 在 wave 内“依次处理多个 case”，且离线处理在 lease 内、shard 内完成。每个 case ≈ 2 min Teacher + 约 10 min 处理 + 读回，8 shard × 每 wave 约 2.5 case，即每 wave 约 30–40 分钟；同时有 8 个 MuJoCo/ROS stack 和最多 8 个处理器、两个 GPU 推理服务争抢 CPU。§8 第 4 步要求“满足冻结的资源、吞吐门槛”，但本文没有给出或引用这些门槛的数值来源。
- 建议：增加一节容量估算（每 shard CPU/RAM、处理器并发、MCAP 体积与磁盘写入速率、每 wave 预计时长），并决定离线处理是否允许与下一个 case 流水并行（会影响“单 shard 单 MuJoCo stack”的资源边界）。至少引用 10-07 的数字并说明 W8 资源停点阈值从何而来。

### P1：应在实施计划前补齐

**P1-1 Head-YOLO 服务被写成每个 campaign 必有，但 10-10 引入了不用 Head Search 的正式采集（§2 第 59 行、§4 状态机 HEAD_READY）**

- 事实：分支 `2026-10-10-so101-act-input-refusal-formal-sim-collection-training-design.md` D4 新增 `target_provider ∈ {head_search_v1, fixed_head_domain_v1}`，后者用固定头部可见性资格替代 Head Search 资格（目前待用户决定 U1）；且 `head_search_v1` 当前会以 `HEAD_SEARCH_PROVIDER_UNAVAILABLE` 拒绝。
- 建议：把 head-YOLO 容器与 HEAD_READY 改成随 `target_provider` 条件启用，或明确本文只适用于 `head_search_v1`。

**P1-2 镜像身份不足以识别实际运行的代码（§3.1 第 69 行、§7、§8 第 1 步）**

- 事实：`cli/parallel_perception_broker.py:43–45` 注释说明镜像内烘焙的 `so101_demo`（09-24）解析器已过时，运行时把 qualified package 只读挂载覆盖到 `IMAGE_PACKAGE_PATH`，并记录 `ACT_BROKER_SOURCE_PIN`（package 源码 hash + detector hash）。10-07 §5 记录了因镜像内旧解析器导致 `EARLY_EXIT: broker: 1` 的真实故障。
- 本文只要求记录“image digest、权重 hash、类别映射、阈值”。shard 镜像会内置 ROS/MuJoCo/controller/Worker 全部代码，同样的问题会更严重。
- 建议：身份明确为“image digest + 挂载源码 pin（或按 freeze 构建的镜像）+ 权重 hash”，并规定 shard 镜像的代码来自哪个 freeze、如何与 `runtime_config_sha256` 及 Task 8L 身份绑定。

**P1-3 Grounded-SAM 教师的容量没有任何验证路径（§3.1 第 71 行、§8 第 5 步）**

- 事实：`runtime/parallel_ipc/broker_transport.py:596–606` 和 `parallel_perception_runtime.py:191–197` 硬性要求 `grounded_sam_executor_count == 1`、YOLO ∈ {1,2,4}，`queue_capacity_per_model ≤ 16`。
- 本文说实例数“不预先测定每档容量”，且 Grounded campaign 不做 W8。8 个 shard 共享 1 个 Grounded 执行器，若吞吐不足会直接表现为 `QUEUE_TIMEOUT`/`INFERENCE_TIMEOUT`，在现有 `decide()` 里是 attempt INVALID。第一次知道答案将是在正式采集里。
- 建议：允许“不做模型效果资格”，但至少要求一次 Grounded 教师的 W8 吞吐冒烟（或明确接受该风险并写入停点）；同时说明本文所说“实例数可配置”需要放开上述硬编码限制。

**P1-4 共享 head-YOLO 的时延与 Head Search 冻结参数的关系没有定义（§3.2 第 75–77 行）**

- Head Search 有 17 项冻结参数（10-03）、“停稳后取新帧、有限重观察、三帧锁定”。从本地线程（`adapters/act/head_inference_owner.py`）改成 8 shard 共享的有界队列后，单帧检测延迟和抖动会变化，可能触发新鲜度/超时类判定。本文规定了“迟到即拒绝”，但没有规定 head 请求的超时值、队列容量从何而来，以及它们属于 §7 哪一类身份。
- 建议：把 head IPC 的超时/队列容量归入“安全与采样合同”类，并在 §8 第 2 步 Task 8L 中要求在 8 路并发负载下测量。

**P1-5 GPU 映射要求与现状不符，且基线表未列出（§2 第 61 行）**

- 事实：`cli/parallel_perception_broker.py:138` 现在是 `--gpus all`。本文要求“显式映射 admission 选定的同一物理 GPU UUID”，shard 还需要 EGL（graphics capability）。
- 建议：基线表补一行；§8 第 1 步验证项加上“容器内可见 GPU UUID 与 admission 一致”。

**P1-6 Host owner 恢复依赖的“确认服务队列和在途请求已清空”没有对应接口（§5 第 112 行、§3.3 第 85 行）**

- 恢复条款要求证明两服务空闲，但 §3.3 的 IPC 合同只列了 ready/health；没有查询在途请求、按 generation 隔离旧客户端的协议。建议在 IPC 合同里加一个只读的队列/在途状态查询，并纳入离线合同测试。

### P2：文字与一致性

- **P2-1 文首授权语句容易误读（第 3 行 vs 第 8 行）**：第 3 行“用户已授权现有 ai-station Claude 更新计划、清理旧逻辑/测试并执行”说的是 10-05，但放在本文开头，和第 8 行“本文不授权实施”并列，读者可能以为本文已获执行授权。建议改为“10-05 修订已获执行授权；本文不授权实施”。
- **P2-2 引用的 10-01 端点验收文档不在基线分支上（第 7 行）**：它只存在于本地 main；分支上 10-05/10-06/10-10 用 `teacher_endpoint_v2` 定义端点判据。既然本文以分支为代码基线，端点口径应引用 10-05 §4.2 / `teacher_endpoint_v2`，并说明与 10-01 的关系。
- **P2-3 依赖 10-07 却不链接（第 31 行）**：理由是 main 上没有该文件。§2、§6 的原始 bag、离线处理器、memo、处理预算都来自 10-07，建议至少以分支路径+提交号的纯文本形式引用，否则审阅者无从核对。
- **P2-4 staging 只增不删（第 85 行）**：每个 head/教师请求一张完整图像、不可复用、未经用户授权不删除。需要给出每 campaign 的估算体积，并纳入磁盘资源停点，否则长 campaign 会在磁盘停点上停下。
- **P2-5 §8 第 4 步“每 wave 每 Worker 至少两个实际 terminal lease”**：20 项 / 8 worker 平均 2.5，正常可满足；但正式采集允许 shard 退出后其余 shard 完成当前 wave（§5），资格运行则直接失败。建议在 §8 写明这条门槛只适用于资格运行。

## 建议的修订顺序

1. 先与用户确认本文相对 10-06“本版不做 Docker 隔离”的定位（P0-1），这是是否继续推进本文的前提。
2. 补基线表：教师两阶段回退、GPU `--gpus all`、源码挂载覆盖、执行器数量硬编码四行（P0-2、P1-2、P1-3、P1-5）。
3. 增加容量/时序一节，以 10-07 实测数据为输入（P0-3、P1-4、P2-4）。
4. head-YOLO 随 `target_provider` 条件化（P1-1），IPC 合同补在途状态查询（P1-6）。
5. 修 P2 文字问题后再交独立审查。

## 附录：基线表逐条核对（分支 6baf54e6）

| 文档中的说法 | 核对结果 |
| --- | --- |
| Broker 单镜像同时挂载 YOLO 权重与 Grounded 模型 | 属实：`cli/parallel_perception_broker.py:30–40, 143–145` |
| Broker 按 batch 启停 | 属实：`cli/mujoco_batch/composition.py` 经 `broker_lifecycle.py` 管理，broker 输入根在 `evidence_root/broker-inputs`（`composition.py:262–267`） |
| Worker 以当前解释器启动宿主子进程，无 shard Dockerfile | 属实：`cli/mujoco_batch/worker_lifecycle.py:148` 用 `sys.executable`；`docker/` 下只有 parallel-perception、yolo-inference/training、grounding-dino-training |
| head detector 在本地进程线程中 | 属实：`adapters/act/head_inference_owner.py:20–35` |
| collection.py 已接入离线 orchestration | 属实：`runtime/parallel_worker_parts/collection.py:27–78` |
| parallel_collection 提供分 wave 与 EIGHT_WORKER/40 场景合同 | 属实：`act/parallel_collection.py:10–33, 67` |
| 分支包含 GitHub 同名分支最新提交 | 属实：`github/codex/so101-act-data-0917a`（9386860）是 6baf54e6 的祖先 |
| 遗漏项 | 教师两阶段回退策略、`--gpus all`、源码挂载覆盖镜像、执行器数量硬编码（见 P0-2、P1-2、P1-3、P1-5） |
