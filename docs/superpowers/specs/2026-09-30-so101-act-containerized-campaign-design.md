# SO-101 ACT 容器化采集 campaign 设计

现行单 stack 版本遵循 [10-05 Teacher/ACT 分离修订](2026-10-05-so101-teacher-act-decoupling-amendment.md)，并以分支上的 10-06 Teacher 执行简化修订为其优先补充。10-05 范围内的既有执行授权不延伸到本文。本文是 10-06 所称留待后续版本的 Docker 隔离设计；进入实施前仍须单独批准实施计划。

创建日期：2026-09-30；本次修订：2026-10-12。

端点结果采用当前源码的 `teacher_endpoint` 规则和 `config/act/teacher_endpoint.yaml`：起终 Pose、五个姿态/位置容差及 `settle_s`。该规则承接 10-05 的端点判据。本地 `main` 的 [10-01 共用端点 Pose 验收](2026-10-01-so101-act-endpoint-pose-acceptance-design.md) 是历史补充说明；实际运行使用冻结的当前规则文件和 hash。

状态：本版按2026-10-12用户决定简化：保留可配置证据ROOT，同路径挂载；RGB经socket传输；Host退出即结束旧campaign；资源只记录并设磁盘停派；两类镜像承载三个容器角色。当前Sol会话内自检，旧Astra PASS仅对应其历史冻结稿。见[修订处置记录](../plans/2026-10-11-so101-act-containerized-campaign-implementation-astra-review.md)。修改文档的批准不授权实施，实施仍须单独确认。

关联文档：

- [双 RGB ACT 总体设计](2026-09-10-so101-act-head-wrist-rgb-design.md)
- [抓放 live 验证与正式采集历史设计](2026-09-24-so101-act-task8-live-formal-collection-design.md)
- [抓放校准测量协议历史设计](2026-09-29-so101-act-task8-measurement-protocol-design.md)
- [ACT 实施计划](../plans/2026-09-11-so101-act-head-wrist-rgb-implementation.md)

分支独有的关联文档（均读取自 `6baf54e6313daca287fa86e7cc248c4c2f1b1dc3`，本地 `main` 没有这些文件，因此不设无效相对链接）：

- `docs/superpowers/specs/2026-10-06-so101-teacher-moveit-simplification-amendment.md`：当前单 stack 版本不做 Docker 隔离。
- `docs/superpowers/specs/2026-10-07-so101-act-raw-log-offline-amendment.md`：原始 bag、离线 episode 和独立 QC 的数据路径。
- `docs/superpowers/specs/2026-10-10-so101-act-input-refusal-formal-sim-collection-training-design.md`：§2.0 的用户决定 U1 否决固定头部目标来源，正式采集等待 Head Search。
- `docs/superpowers/specs/2026-10-10-so101-teacher-minimal-runtime-gates-design.md`：当前模拟版 Teacher 输入仍为 broker YOLO + R6 + z-clip；该文自身标为未实施，不作为本文容器化完成证据。
- `docs/superpowers/specs/2026-10-10-so101-code-style-refactor-design.md`：当前业务命名、latest-only 格式和测试布局的依据；源码已完成对应重构。

本文定义下一版 ai-station 使用 Head Search 目标来源的容器化 campaign。10-06 对现行单 stack 版本仍优先；本设计的拓扑、共享 IPC 和故障恢复条款须经单独实施计划、用户批准、新冻结与验收后才生效。10-07 的数据路径和 10-10 已作出的 U1 决定继续约束本设计。关联历史文档的文件名保留，但实现入口、报告和验收项统一使用本文的业务名称。

## 代码基线与设计差异（2026-10-11）

2026-10-11 经两个 remote 的 `git ls-remote` 读回，Gitee `codex/so101-act-data-0917a` 为 `6baf54e6313daca287fa86e7cc248c4c2f1b1dc3`，包含 GitHub 同名分支 `9386860dfed9bdfa840b7b51f061c299459bd390`。以下代码对照采用 Gitee 提交，读取独立 source snapshot，本地工作树保持在 `main`。下表源码路径以 `src/so101_demo_py/src/` 为根；源码存在不代表新容器拓扑已取得运行资格。

| 边界 | 分支代码现状 | 本文仍需实现的目标 |
| --- | --- | --- |
| 教师感知 Broker | `cli/parallel_perception_broker.py` 以一个 Docker image 同时挂载 YOLO 权重和 Grounded 模型；`cli/mujoco_batch/composition.py` 在每个 batch 启动、结束时退役该容器。 | 仅启动 YOLO 教师 image；Broker 按 campaign 启动并跨 wave 存活，实例数在下一 campaign 启动时配置。 |
| 教师感知策略 | `parallel_batch/perception.py` 的 `PerceptionPolicy.decide()` 先请求 YOLO，`NORMAL_REJECTION` 或 `MODEL_ERROR` 时最多请求一次 Grounded-SAM；Worker 的本地定位/R6 消费该结果。 | ACT改用独立YOLO-only感知policy，同步迁移R6/请求合同并重做校准/live；其他业务通用policy保留，不全仓删除回退。 |
| Broker 实际代码 | `cli/parallel_perception_broker.py` 允许将 qualified `so101_demo` 包只读挂载到镜像内的 `IMAGE_PACKAGE_PATH`，并记录 package/detector source hash；镜像 digest 单独不足以标识执行代码。 | 两个推理服务与 shard image 均由冻结安装产物构建并钉住实际 package/source、子模块与镜像 digest；拒绝未登记的运行时源码覆盖。 |
| Broker 执行器 | `runtime/parallel_ipc/broker_transport.py` 限定 YOLO 执行器数为 `1/2/4`、Grounded 执行器数为 `1`，单模型队列容量至多 `16`。 | ACT新服务使用正整数实例数配置，不继承旧硬编码；旧Broker仍供其他业务使用。不把现有限制误写成已支持任意并发。 |
| GPU 可见性 | `cli/parallel_perception_broker.py` 当前以 `--gpus all` 启动容器。 | 启动入口只映射 admission 选定的物理 GPU UUID；两个推理容器与 shard 都要从容器内读回 UUID，shard 还须验证 EGL。 |
| Worker 与仿真 | `cli/mujoco_batch/worker_lifecycle.py` 用当前 Python 解释器启动宿主 Worker 子进程；该分支没有 shard 专用 Dockerfile。 | 一 shard 一容器，容器内承载该 shard 的 Worker、MuJoCo/ROS、controller 与采集子进程，按 wave 清理。 |
| head 搜索检测 | `adapters/act/head_inference_owner.py`、`adapters/act/detector.py` 在本地进程中持有 head detector 和推理线程。 | 将原始候选推理迁到 campaign 级共享 head-YOLO IPC 容器；Worker 继续拥有搜索状态机、时序和安全判断。 |
| ACT 数据路径 | `runtime/parallel_worker_parts/collection.py` 已调用 `act/offline/orchestration.py`：Teacher 前启动原始 bag 录制，Teacher 退出后关闭 bag、离线生成 episode 并做独立进程 QC；Teacher 结果与数据状态分开。 | 将这条已接入的录制、离线处理和 QC 路径搬进 shard 的私有边界，而不是恢复逐帧同步写 episode 的旧路径。 |
| wave 与结果 | `act/parallel_collection.py` 已提供有序分 wave、场景去重、每场景唯一结果及正式模式的 EIGHT_WORKER/40 场景合同。 | Host 将既有合同接到容器生命周期、共享服务和资格证据上；代码存在不等于容器化 W8 已通过。 |
| 八 Worker 资格报告与准入 | `act/parallel_qualification_verifier.py` 当前检查抓放 live campaign 的摘要和 journal；其调用的摘要默认是 9 个阶段前缀加 5 次完整运行。`so101_teleop/unified/admission.py` 要求同一报告为 `PASSED`，verifier 却要求 `QUALIFIED`，且当前入口限制资格引用位于当前运行 root。 | 同步迁移报告 writer/schema、admission 和 verifier，使用唯一终态 `QUALIFIED`；专门验证独立 40 场景、两个 20 项 wave、八 Worker 的真实终态 lease 和资源/QC 证据，以及新 campaign 对独立资格 subroot 的受控只读引用。不能用 14 项 live 验证替代 W8。 |
| IPC 字段合同 | `runtime/parallel_ipc/broker_transport.py` 仍容许额外 compatibility 字段，snapshot 也容许 start identity 字段；macOS双Worker路径正在使用它们。 | ACT调用方同步迁移到 §3.4 的闭合合同，不接收旧字段或Snapshot的start identity；旧Broker/Snapshot为macOS及其他业务保留，不作为ACT兼容入口。 |

这些差异是迁移清单，不是把当前 batch Broker 或宿主 Worker 重新命名为 campaign 容器。分支账本 CP-3557 记载了重构后若干 live 检查，但没有给本文目标拓扑的独立 exact-W8 资格；不能据此沿用旧 bundle 或省略第 8 节验收。

## 1. 范围

目标是把每个 shard 的 Worker、MuJoCo、ROS、controller 和 Recorder 放入独立容器，并将 head 搜索 YOLO 与教师感知 YOLO 改为两个共享 IPC 服务。Host campaign owner 仍是唯一资源和调度所有者。正式采集使用 Head Search 目标来源；固定头部目标来源不在本设计中。仿真仅支持 MuJoCo，GPU 推理不回退到 CPU；容器方案不涉及真实机械臂。

本设计沿用 ACT 的 observation/action、抓放执行监督、10 Hz 因果采样、接触策略批准、数据集划分和训练算法。阈值效果变差时使用独立的阈值推算流程。

### 1.1 业务模块与入口

迁移基于重构后的模块继续修改。计划、CLI、状态和测试名称使用业务职责；历史阶段编号只允许出现在历史文档路径和审计记录中。

| 职责 | 当前模块 | 当前 CLI / 产物 |
| --- | --- | --- |
| 抓放校准测量 | `act/pick_place_calibration_measurement_driver.py`、`act/pick_place_calibration_measurement_contract.py`、`act/pick_place_calibration_measurement_schema.py` | `act_measure_pick_place_calibration`；闭合 measurement batch |
| 校准聚合与准入 | `act/pick_place_calibration_aggregator.py`、`act/pick_place_calibration_admission.py` | `act_build_pick_place_calibration_report`；`PICK_PLACE_CALIBRATION_READY` |
| 验证产物准备 | `act/pick_place_validation_artifact_bundle.py`、`act/pick_place_validation_manifest.py` | `act_prepare_pick_place_validation`、`act_validate_pick_place_validation_artifacts`；`preparation-receipt.json` |
| 抓放 live 验证及资格报告 | `act/pick_place_validation_campaign.py`、`act/pick_place_live_evidence.py`、`act/pick_place_live_qualification.py` | `act_run_pick_place_validation`、`act_build_pick_place_validation_qualified_report`；抓放 `QUALIFIED` 报告 |
| Head Search 与本地候选处理 | `act/head_search_*`、`adapters/act/head_inference_owner.py`、`adapters/act/detector.py` | Head Search 校准与资格证据；Worker 本地追踪和锁定状态 |
| 并行采集及八 Worker 资格 | `act/parallel_collection.py`、`act/parallel_qualification_verifier.py`、`runtime/parallel_worker_parts/collection.py` | `act_collect_parallel`；campaign index、逐场景结果和八 Worker 资格证据 |
| 原始录制、离线 episode 与 QC | `act/offline/raw_recorder.py`、`act/offline/orchestration.py`、`act/offline/processor.py`、`act/offline/independent_qc.py` | 原始 MCAP、派生 episode、独立 QC report |
| 训练依赖解析与训练 | `act/training_requirements.py`、`act/training.py` | `act_resolve_training_requirements`、`act_train`；按 commit/receipt 构建训练输入 |

抓放校准准入、抓放 live 资格、Head Search 资格和八 Worker 采集资格各有自己的证据，计划中分别验收。共享服务提供候选并不产生其中任何一种资格。

### 1.2 单一 schema 和接口

每种业务文档、消息和 API 只保留一个当前格式。模块、类、函数、CLI、`kind` 和规则名不带格式版本后缀；需要格式号的文档仍携带整数 `schema_version`。不同业务类型可以具有不同格式号，不能据此把它们当成同一对象的兼容版本。

| 当前业务文档 / 合同 | 当前身份 | 唯一接受的格式 | 源码依据 |
| --- | --- | --- | --- |
| Teacher 端点策略 | `ACT_TEACHER_ENDPOINT_POLICY`，`rule_version=teacher_endpoint` | `schema_version=1` | `act/teacher_endpoint.py` |
| Teacher 执行策略 | `ACT_TEACHER_EXECUTION_POLICY` | `schema_version=3` | `act/teacher_endpoint.py` |
| Head 仿真策略 | `HeadSimulationPolicy`，`mode=mujoco_bounded_stop_search_file` | `schema_version=3` | `act/head_simulation_policy.py` |
| 抓放校准测量合同 | `pick_place_calibration_measurement_contract` | `schema_version=2` | `act/pick_place_calibration_measurement_contract.py` |
| 抓放校准批次 | `pick_place_calibration_batch` | `schema_version=1` | `act/pick_place_calibration_measurement_schema.py` |
| 抓放验证 manifest | `ACT_PICK_PLACE_VALIDATION` | `schema_version=2` | `act/pick_place_validation_manifest.py` |
| 验证准备回执 | `pick_place_validation_preparation_receipt` | `schema_version=2` | `act/pick_place_validation_artifact_bundle.py` |
| 并行采集配置 | `act_parallel_collection`；`config/act/parallel_collection.yaml` | `schema_version=1` | `act/collection_config.py` |
| 采集结果 / episode QC | `ACT_COLLECTION_RESULT` / `ACT_EPISODE_QC`，QC 规则 `act_data_qc` | 两种文档各只接受 `schema_version=3` | `act/result_store.py`、`act/episode_qc.py` |
| Teacher 事件 | `schema=SO101_TEACHER_EVENT` | 当前闭合字段集合；该流不用数字后缀区分格式 | `act/teacher_event_stream.py` |
| 训练配置 | `act_training` | `schema_version=2` | `act/training_config.py` |

表中数值是本次代码基线，并非未来版本分派表。容器化若需要改变某个闭合格式，writer、reader、schema 文件、当前调用方和测试在同一迁移中一起修改；新镜像只接受修改后的格式，旧格式直接拒绝。禁止版本协商、旧名称 alias、`allow_legacy`、隐式升级和双 writer。旧 evidence 原样保留；新 campaign 只消费新冻结产物，不要求新 reader 能读取重构前的证据。

校准测量合同的十成员 identity 与 21 项核心测量是两种集合。前者绑定源码、配置、policy、driver 和 phase-camera 等身份；后者记录原始来源、公式及测量值。容器迁移须保持这两个闭合集合各自的含义，不能因新增 Docker 运行参数而随意给测量 identity 加字段。

## 2. 运行拓扑与职责

~~~text
Host: UnifiedWorkloadService / campaign owner / Coordinator
  admission, physical GPU lease, journal, case lease, verify, commit, cleanup
  |
  +-- head-YOLO container (one per campaign)
  |     shared inference image, head config; RGB socket -> bounded queue -> raw candidates
  |
  +-- teacher perception Broker container (one per campaign)
  |     shared inference image, teacher config; no Grounded-SAM fallback
  |     task_camera RGB -> bounded IPC queue -> canonical candidates
  |
  +-- wave: eight shard containers, w00...w07
        Worker + one MuJoCo/ROS stack + controller + private raw-bag Recorder
        Teacher 退出后：offline episode processor + independent QC
        head search state machine and neck control remain here
        private evidence directory under configured evidence_root
~~~

两个用途不同、队列独立的YOLO容器使用同一推理服务镜像，分别加载head和Teacher配置/权重，跨wave存活；shard使用另一镜像，只服务所属wave。只做两个Dockerfile和两份镜像digest，不合并两个服务进程或队列。Teacher Broker只做视觉推理，不恢复CommandBroker；Teacher继续使用MoveIt/JTC执行与停止边界。

每个 shard 独占 ROS Domain、namespace、MuJoCo session、controller、原始 bag Recorder、离线处理临时目录和证据目录，并使用私有网络 namespace。Host 不启动第二套 ROS/MuJoCo stack，也不让容器取得 Docker socket、特权模式或 host network。Host 将 admission 选定的同一物理 GPU UUID 显式映射给两个推理容器和所有 shard；设备可见性不是 GPU 容量隔离，合计负载仍要监测。共享服务只处理请求、排队、推理、健康状态和响应关联，不读取 case lease、wave journal 或资源 binding。资源绑定只在统一启动入口核验；内部业务消息只检查其自身的身份、generation、时间戳和 schema。

## 3. 两类推理服务

### 3.1 教师感知 Broker

教师 Broker 在本设计中只使用 YOLO image、YOLO 权重和既有 YOLO 分数阈值。ACT Worker只请求YOLO；未检出、模型错误或R6定位失败返回明确结果，不再请求Grounded-SAM。服务输出候选，不决定Teacher物体任务结果。ACT使用独立的当前感知policy，同步迁移Worker/R6和请求合同；通用`PerceptionPolicy`及旧Broker为macOS等其他业务保留回退，不能从全仓库删除。

首次迁移将基线写死的Teacher模型ID、权重hash及`conf=0.25`注入独立campaign配置，初值逐项反读源码和实际权重文件。此次迁移属于受控源码变更；迁移完成后更换Teacher权重/分数不再要求改源码。共用detector保留其他业务原默认行为，ACT显式注入；head配置单独派生，不随Teacher参数变动。

教师 YOLO 的 image digest、实际运行的 package/detector source pin、权重 hash、类别映射和阈值写入 campaign 配置及结果溯源，campaign 内不可变。下一 campaign 可更换权重或运行期阈值，不增设模型独立的 QUALIFIED 启动门禁；仅调整这些模型运行参数本身不自动重做抓放校准，但仍受逐 episode QC 和现有成功率门槛约束。取消 YOLO→Grounded-SAM 回退、修改 R6/Worker 感知逻辑或共享协议属于受控源码变化，必须用新身份重新完成抓放校准准入与 live 验证。

教师 YOLO image 在启动时加载配置的全部模型实例，全部可用后才能报告 ready。实例数是独立的 campaign 运营参数，仅下一 campaign 可调整；实施时须替换基线代码对 YOLO 执行器数 `1/2/4` 的硬限制，并验证新配置。这里不预先测定每档容量；实际运行若不足，停止新派发并请人工决定后续方案，不自动减少实例数。队列容量、超时和判定规则仍须在 campaign 前冻结，运行中不能为提高吞吐临时改动。

两个服务分别由一个父进程持有请求队列和连接，以 `spawn` 启动配置数量的执行进程；父进程不初始化 CUDA 上下文，每个执行进程独立初始化 CUDA 并加载一个 YOLO 实例，同一实例同时只执行一个请求。父进程把不同请求分配到空闲执行进程；Torch 线程数作为每进程配置固定。实例全部加载完成并读回 CUDA 设备后 ready；任一执行进程异常退出视为服务整体失效，交给 Host 停止新派发并等待人工决定，不在运行中重建进程或缩容。

### 3.2 共享 head-YOLO 服务

八个 shard 通过 IPC 使用同一个 head-YOLO 服务，不在 Worker 容器内各加载一份 YOLO。服务返回原始类别、框、分数、mask 及源帧身份。Worker 保留 `HeadSearchController`、重复 mask/碎片抑制、attempt-scoped 空间追踪、连续稳定帧、面积、视区、新鲜度和 `min_confidence` 等检查；这包含当前 `HeadRgbDetector` 的本地后处理。共享服务不拥有 track ID、搜索锁定或 neck 控制状态。测量协议要求的原始 head RGB、原始 detector candidate 和本地处理结果分别留证。迟到、跨 attempt 或跨 reset epoch 的结果由 Worker 拒绝；原始 bag 录制不等待 head 推理，派生 episode 的 10 Hz 连续性由离线处理和 QC 验证。

head模型、视角配置、搜索阈值、`torch_threads/torch_interop_threads`及torch/ultralytics版本从当前Head Search绑定派生并逐项核对；线程/版本不是可自由调整的运营参数。首轮尚无绑定时，仅受限measurement分支消费批准measurement plan/candidate policy。Worker从RGB序列化前记录单调起点，序列化、socket传输、排队、推理和响应解码的完整等待计入批准的`perception_job_timeout_s`。`default_document()`的`1.0 s`只是候选，不能补缺或延长预算；保留`perception_max_age_s <= perception_job_timeout_s <= stop_confirmation_timeout_s`。

每个 shard 同时至多发出一个未决 head 请求。head 服务的 `max_inflight_requests=8` 来自八 shard 的单请求合同，计入接收中的有界帧、排队、执行和等待响应交付的请求；实际队列可用容量由这个总上限扣除其他在途状态，不能额外接纳八个排队请求。达到上限即返回 `QUEUE_FULL`。响应还须通过原有源帧年龄、停稳后新帧和 search deadline 检查。head-YOLO 的模型实例/执行进程数是 campaign 启动参数，只能在下一 campaign 调整。两个共享服务的 GPU、CPU、RAM 和队列负载只记录已有可用观测，不要求新增完整监控框架。

### 3.3 IPC 与接口验收

两个服务各有独立短Unix socket和有界队列。Worker直接发送连续、row-major的RGB8字节，不写运输用request-ID文件，不创建输入staging目录。640×480×3为921600字节；只传原始RGB，不引入压缩、pickle、NumPy文件、裁剪或二次换通道。

新ACT接口统一使用`[u32be body_length][u32be header_length][UTF-8 JSON header][payload]`。JSON header承载§3.4元数据，推理请求payload为RGB字节，响应和查询payload为空；总body包含header长度字段、JSON和payload。复用现有canonical JSON校验，不把旧JSON-only frame当成支持二进制。接收方先核对body上限，再核对header边界、H/W为正整数、通道为3及`byte_length=H*W*3`，拒绝额外/不足字节；不按文件格式探测。接收buffer、queue、执行及待交付响应共同受在途上限约束，不增设无界预读队列。

request ID由Worker生成，campaign内不复用。Worker保留其与session、attempt、reset/lease/worker generation、sequence、源帧身份及本地原始证据引用的关联；服务只回显request ID和源帧身份。迟到、跨generation/attempt及重复响应由Worker拒绝。head每shard至多一个未决请求，mask与RGB-D/R6、head追踪仍在本地消费。

不实现服务接管、持久幂等或完成请求的全量seen-ID。服务只拒绝当前在途中的重复ID；结束后释放记录，Worker不自动重发已提交请求。原始帧及其hash仍由measurement或Recorder留证，取消的是运输文件和运输用SHA门禁，不删除测量来源。

接口测试覆盖RGB字节不变、帧截断/超长、shape与长度不符、队列满、超时、在途重复ID、迟到/跨generation响应及ready/health。共享服务无需读取shard证据目录，也不提供恢复用空闲证明。

### 3.4 当前推理接口

两个服务使用同一套闭合推理消息，基线尚未实现。整体迁移ACT调用方，不保留ACT可选的旧`broker_call`；macOS与其他并行业务继续使用自身Broker合同，属于不同业务而非多版本接口。Coordinator控制面独立，不把authority字段复制到推理接口。

| 消息 | 固定字段 |
| --- | --- |
| 推理请求 | `schema_version=1`、`kind=inference_request`、`request_id`、`image`、`query_class_id`、`deadline_monotonic_ns` |
| `image` | `format=RGB8`、`byte_length`、`shape`、`source_stamp_ns`、`source_frame_id`；`shape=[height,width,3]`，像素在请求payload，不含路径或运输hash |
| 推理响应 | `schema_version=1`、`kind=inference_response`、`request_id`、`service_generation`、`source_stamp_ns`、`source_frame_id`、`outcome`、`reason`、`batch`、`timing` |
| `batch` | `model_id`、`weights_sha256`、`runtime_device`、`inference_latency_ms`、`shape`、`source_stamp_ns`、`source_frame_id`、`candidates`；字段形状沿用当前 `normalize_batch()`，失败时为 `null` |
| 每个 candidate | `instance_id`、`class_id`、`confidence`、`bbox_xyxy`、`segmentation_quality`、`mask_rle`；`mask_rle={shape,counts}`，row-major、从 false 起交替、总计必须等于像素数 |
| `timing` | `received_monotonic_ns`、`queued_monotonic_ns`、`started_monotonic_ns`、`completed_monotonic_ns`；尚未进入某阶段时相应值为 `null` |

`outcome` 只取 `DETECTED`、`NOT_DETECTED`、`INPUT_INVALID`、`QUEUE_FULL`、`QUEUE_TIMEOUT`、`INFERENCE_TIMEOUT`、`MODEL_ERROR`、`INFRA_ERROR`。`DETECTED` 要求非空、结构合法的 candidate batch；它表示检测结果可读取，不表示目标定位或模型资格通过。Worker 将推理结果接到自己的 Head Search 或 Teacher 感知决策，不能因旧代码中的 `ModelOutcome.QUALIFIED` 名称而绕过 R6 或本地候选检查。

`request_id`使用campaign-global不透明值。服务仅跟踪在途关联，对在途重复返回`INPUT_INVALID/reason=DUPLICATE_REQUEST`且不再次执行；结束即释放，不承诺campaign全程exactly-once。客户端不自动重试，重复响应不被消费。协议不接收lease/token/wave/worker identity/start-event；模型和阈值由服务启动配置决定。非法外层字段拒绝并关闭连接，合法请求才返回带ID的响应。

所有消息采用§3.3同一二进制envelope，不保留第二套ACT格式。最大帧大小随服务配置冻结；JSON字段严格校验，响应mask留在JSON头并受总帧上限约束。超大mask明确拒绝，不能截断后继续定位。

Host、shard 和推理服务使用同一 Linux 单调时钟，容器不启用独立 time namespace。`deadline_monotonic_ns` 是单请求截止时间；head 请求取本地推理预算与 search deadline 的较早者。排队已过截止时间的请求不执行；推理不能及时完成时返回超时，CUDA 工作仍在途则继续计入 `running`，直到实际完成或服务进程被证明退出。断连或超过截止时间的待交付响应转入审计日志后释放，不能永久挂在 `responses_pending`，也不能稍后交给别的请求。Worker 用自己的发送/接收时刻测量端到端等待，不用服务的推理时间代替。

ready和health查询只有`service_ready`与`service_health`。请求字段为`schema_version=1,kind,request_id`；响应另含`service_generation`及下表字段。没有`service_state`、accepted计数或双次空闲证明。

| 查询 | 响应的其他字段 |
| --- | --- |
| `service_ready` | `image_digest,package_source_sha256,model_id,weights_sha256,service_config_sha256,gpu_uuid,configured_instances,loaded_instances,ready` |
| `service_health` | `available,reason` |

新接口只接受表中的当前字段和格式。`_BROKER_COMPATIBILITY_FIELDS`、可选的旧start identity、旧socket/API alias和版本分派不得进入目标服务；迁移结束后ACT调用方只使用这一套合同。其他业务的现行Broker/Snapshot不受此删除要求影响。

## 4. Campaign 启停与 wave 生命周期

统一入口先完成 MuJoCo-only、policy activation、manifest/config hash、物理 GPU UUID、持久 lease、cleanup fence 和证据根 admission。Host owner 持有并续租资源；任何内部容器都不重新做 campaign 资源绑定校验。

冻结场景清单后，Host 先发布不可覆盖的 campaign index/wave 分区；每个 scene 的结果随后单独提交。正常运行顺序为：

~~~text
ADMITTED -> HEAD_READY -> TEACHER_READY -> SHARDS_READY
         -> WAVE_RUNNING -> WAVE_TERMINAL -> SHARDS_CLEANED
         -> next wave or CAMPAIGN_CLOSED
~~~

HEAD_READY 和 TEACHER_READY 要求配置的全部模型实例加载成功、IPC 可服务、容器内实际 GPU UUID 与 admission 一致、image/package/model/config 身份与 campaign 记录一致。每个 shard 的 SHARDS_READY 不能只凭容器 PID：MuJoCo 场景、ROS/controller、七关节反馈、head/wrist 新鲜 RGB、私有证据挂载、两个 IPC 端点、容器内 GPU UUID 和 EGL 都须可用，且 controller 没有未知活跃 goal。READY 不执行 case 动作，不替代逐 case 检查；Recorder 的实际启动和数据有效性按 case 单独判定，不构成 Teacher 运动准入。正式 W8 的八个 shard 全部 ready 后才发 terminal lease。

一个 shard 容器在本 wave 内依次处理多个 case，每个 attempt 只做一次场景 reset。同一 shard 不把上一 case 的离线处理与下一 case 的 Teacher 执行流水重叠；原始 bag 关闭、离线处理/QC 和本 case 的终态提交收敛后，才领取下一 case。Teacher 的物体任务终态、ACT 数据状态和基础设施故障分别记录；数据 INVALID 不改写已成立的 Teacher 结果，基础设施失败也不能伪装成已 seal 的业务 FAILED。单个 case 失败不撤销整个 wave；数据是否进入训练集由后续 commit/QC/manifest 流程决定。wave 所有 case 终态后，Host 等待 verifier/commit、controller 停止和旧 shard 容器、Domain、socket、GPU 占用清理收敛，才开始下一 wave。数据处理可在 Teacher 退出后继续，但不能越过冻结的 case/lease 截止时间，也不能拖着未证明停止的控制进程进入下一 wave。两个推理容器保持运行，不在 wave 边界做 wave-aware drain 或重新加载模型。

10-07 原始 bag 修订记录的首轮处理耗时为 580 s，输入 episode 为 103.6 s；这是单次观测，不是下一版的容量预算或准入上限。该修订的处理等待上限为 `min(1200 s, lease 剩余时间 - 60 s)`，实际值必须由运行所用的冻结配置和 lease 读回。最多八个 shard 可同时进入离线处理，因此 Host 持续观察 CPU/GPU/RAM、MuJoCo RTF、磁盘与数据完整性。本文不预先估算每 wave 时长、MCAP 总量或模型实例容量；实际资源不足或既有门槛未达到时停止新派发，保留在途 Teacher 的独立停止/完成边界，等待人工决定，不自动降档或改阈值。

## 5. 故障与恢复

### 测量和抓放 live 的非wave生命周期

采集、测量和live复用Host的`ContainerServiceOwner`，只有外层owner拥有全局准入/服务关闭权。受限测量使用新`act_calibration_measurement_start`及批准measurement plan，在没有本轮READY时仅启动head服务；不要求W8或activation，不允许正式抓放/Recorder/release。取得有效Head Search绑定后，完整抓放测量继续使用受限measurement入口，保留21项来源和公式。每次flight独立run/context，先证明shard/controller停止，再退役head服务，最后全局finish；安全范围不因新入口扩大。

9+5 live外层一次使用`pick_place_validation_full`准入，要求新READY/bundle/activation及Head Search绑定，不要求W8；启动head和Teacher各一次，14个case借用context。`PickPlaceCaseOwner`局部case启停保留FULL_RESTART/journal，但不重复全局start/finish；每case新shard/session，停止已证后再下一个，最后退役共享服务并全局finish。独立单phase验证仍走自己的`pick_place_validation_phase`，不能冒充9+5报告。诊断episode不因共用payload定义而继承容器或W8要求。

measurement及live的私有证据目录同样由Host从`evidence_root`生成，并以同一绝对路径挂入shard；无需非wave输入前缀。服务不接收证据路径。闭合payload拆分、kind路由及退役测试在[执行计划](../plans/2026-10-11-so101-act-containerized-campaign-implementation.md)中冻结前接通。

| 事件 | 处理 |
| --- | --- |
| 模型未检出、确定性模型错误、单请求排队溢出或超时 | ACT教师映射：NOT_DETECTED→NORMAL_REJECTION、MODEL_ERROR→MODEL_ERROR，均按既有Teacher失败路径处理；INPUT_INVALID/QUEUE_FULL→INFRA_ERROR，QUEUE_TIMEOUT/INFERENCE_TIMEOUT及INFRA_ERROR保留原基础设施INVALID归类。DETECTED仅为候选，仍过本地R6；R6拒绝为NORMAL_REJECTION。完整映射和测试见执行计划，不用数据INVALID反写Teacher失败。单case失败不撤销其他case。 |
| head-YOLO 或教师 Broker 整体失效 | 停止发新 lease，停止当前 campaign，保留证据并等待人工处理；不自动切换模型或缩容。 |
| 正式采集中一个 shard 退出 | 已开始的 case 记基础设施失败并保留部分证据，不伪造业务 FAILED 或训练 episode；未开始的 lease 收回再分配。其余 shard 可完成当前 wave。下一 wave 前必须恢复八个 ready shard；新容器用新 generation，不继承旧 lease。 |
| W8 资格中任一 shard 退出 | 本次资格失败；不能按 W7 继续或拼接残缺结果。 |
| 磁盘见底、实际原始bag丢失/10Hz连续性损坏、OOM/设备错误等真实故障 | 停止新派发并等待人工决策，不自动降Worker、实例数、画质或采样率。Teacher按自身执行/停止合同收尾，数据INVALID不撤销Teacher结果。磁盘沿用已有安全下限；确无批准值时按无可用空间/ENOSPC停派，不借开发示例创建新预算。 |
| CPU/GPU/RAM、磁盘I/O、RTF、队列及吞吐观测偏高/偏低或缺测 | 如实记录及报告，不设资格通过线，不因读数本身停派。既有本地队列背压保留；真实服务故障及数据损坏按上行处理。 |
| Host owner在正式采集中退出 | 结束旧campaign，不接管旧共享服务、不在旧ID下resume。shard因heartbeat失联停止接纳并按现有controller撤销/stop合同收敛。协调者只反读旧journal/commit和停止证据，确认旧shard、控制进程、两服务退出并释放owned资源后，才可按用户许可新建campaign。已commit保留；在途记infra/未完成；未知停止状态阻止新运行。 |
| Host owner 在 W8 资格中退出 | 资格失败，不在原资格 ID 下续跑。人工决定重测时从新资格记录完整运行 40 场景。 |

正式业务FAILED不在同campaign重排或重试。需要重采时，由人工决定新campaign/manifest/数据身份，不覆盖旧结果或分母。Host仍活着时可按既有规则处理单shard故障；Host退出后只做旧资源退役，不继续旧任务。所有cleanup仍generation-scoped/single-flight；未知owner、迟到seal或无法确认停止的controller阻止新运行。

## 6. 挂载、证据与训练边界

运行入口提供唯一可配置的`evidence_root`（CLI的`--registered-evidence-root`对应此值）。不同机器可登记自己的绝对ROOT；Host从它创建全新campaign/run、wave/shard、校准和live目录，程序不硬编码ai-station盘符。本线程在ai-station继续使用已登记的`/data/work/so101-evidence/act-data/20260924-fbc25063-resume`，配置ROOT不授权移动或删除旧证据。

shard自己的证据目录以`Host绝对目录:同一绝对目录:rw`挂载。需要的校准/bundle/配置/权重逐项同路径只读挂载；不挂整个ROOT来暴露其他shard，不暴露Host中心journal写权限。容器可保存这些绝对路径，既有sample、bundle、offline结果、QC memo、seal和训练reader无需因容器化迁成相对格式。已有格式原本使用相对引用的部分继续沿用，不统一改成绝对。

ROOT决定新运行位置，不是对旧artifact做字符串替换的resolver。跨机器复核旧证据须保留其记录的原路径映射，或另行批准并审计迁移；本版不做自动改写。Host沿用既有路径范围/hash/QC验证，启动时验证挂载清单，容器权限验证只核对能读写自己的目录及读取批准输入，不重做资源授权。

共享推理容器只挂自己的配置/权重、socket、日志和临时目录，不挂任何RGB staging或shard证据。源码/安装产物可继续固定在`/act/source`与`/act/install`，短socket路径使用`/act/ipc`；不再要求所有artifact路径只能是`/act/...`。

目标使用两个镜像：`campaign-inference`由同一代码/依赖freeze构建，head与Teacher用同一digest，各自配置/权重单独留hash；`campaign-shard`承载Worker/ROS/MuJoCo/Recorder/offline。入口登记两类镜像的实际source/install、子模块和依赖身份，ready读回执行模块及GPU UUID。推理镜像依赖必须满足head绑定，不能因共用镜像放宽版本检查；权重仍独立只读挂载，不接受未登记源码覆盖。需要Git身份时保留可核验元数据，不以LABEL/commit字符串替代来源证明。

Worker 在私有目录先让 record-only 进程保存原始 rosbag2 MCAP、采集事件及来源证据；Teacher 退出并证明停止后，再由离线处理器从原始流派生 10 Hz 双 RGB/状态/action episode，运行独立进程 QC，分别记录 Teacher 结果与 ACT 数据 VALID/INVALID 及原因。Recorder 未就绪、录制/处理超时或 QC 失败不能反向阻断或撤销 Teacher，但 INVALID 数据不得进入训练集。合法 episode 的闭合 manifest、逐文件 hash、原子 seal 和 fsync 仍须完成；Host Coordinator 对登记 workspace 执行独立 verifier，再按用途和身份约束写逐场景 result commit 与 wave journal。冻结的 campaign index 在派发前写入，不能用目录扫描补写结果。容器退出时不再复制一份 episode。原始 bag、部分文件、只有 seal 没有 commit、迟到结果、资格或 surplus 均保留审计；训练 manifest 只引用允许用途且已 commit、QC 合格的派生 episode。训练输入解析从 campaign index 回放 commit 与 receipt，不扫描目录推断训练数据。

唯一 evidence root 不移动、不删除。ai-station 上需要 fsync-heavy pytest 时，仍须在登记 root 下使用全新的 NVMe scratch，先核对 TMPDIR/TMP/TEMP 与实际测试 Python 的 tempfile 解析，再运行测试；scratch 经反读后只列为删除候选。

## 7. 配置身份与原计划修订

配置按作用分开记录，不能因为参数出现在同一 YAML 文件里就把它们视为相同门禁：

| 配置类别 | 例子 | 变化后的处理 |
| --- | --- | --- |
| 安全、感知路径与采样合同 | contact policy fingerprint、YOLO-only 的 `PerceptionPolicy`/R6、head 搜索锁定阈值、head IPC 接纳上限与完整请求等待超时、双 RGB/10 Hz、controller、抓放测量合同、MuJoCo source/adapter | 受控源码或合同变化使旧校准准入、准备 bundle 和相关 live 资格对新身份失效；使用新 run subroot 重做。head IPC 的完整等待时间计入冻结的 `perception_job_timeout_s`，不得放宽源帧新鲜度。 |
| 容器执行代码身份 | 两类镜像digest、source/install与package hash、依赖/子模块pin、GPU UUID、受控runtime hash | 实际执行身份不符拒绝启动；head与Teacher复用推理镜像digest，但配置/权重来源分别核对。受控代码变化重新冻结并完成校准/live。 |
| 教师模型运行与溯源 | YOLO 权重、类别映射、YOLO 分数阈值 | 每 campaign 固定并记录；仅这些模型运行参数变化不增设模型 QUALIFIED，也不因其本身自动重做抓放校准。改变 Worker 感知决策或定位代码不属于此行。 |
| 推理服务运营参数 | head-YOLO 与教师服务各自的模型实例/执行进程数 | 仅下一 campaign 启动时调整并记录；不预先测试每个数值的容量，不撤销既有校准与八 Worker 资格。 |
| W8 门禁配置 | exact worker count、20项wave、40场景清单、四项既有质量/业务规则、cleanup和终态覆盖 | 资格前冻结，运行中不改；资源与吞吐只观测，不设通过线。W2后直接独立exact-W8，不W4/W6。 |

当前校准/验证合同绑定完整 runtime config；容器实施计划须按上述职责拆分身份。模型运营参数保存在独立 campaign 配置中，不因同处一个 YAML 就改变抓放测量的十成员 identity。教师 YOLO 权重/阈值和实例数量不能通过 `runtime_config_sha256` 间接成为模型 QUALIFIED 门禁；同一 campaign 的配置与 evidence hash 仍不可变，恢复不得换权重或改参数。容器拓扑、YOLO-only Worker 决策、head 检测 IPC、Worker/执行监督和测量协议的受控源码变化，须用新 run subroot 重新完成校准准入、bundle 准备及相关 live 资格。

## 8. 迁移验收顺序

1. ACT迁到仅YOLO的campaign级Broker及独立ACT感知policy，取消ACT的Grounded-SAM回退并核对R6；其他业务旧Broker/policy保留。head detector迁到共享head-YOLO image，Worker迁到shard image。保持Teacher/数据分离及bag→离线episode→独立QC顺序；验证两服务IPC、坏输入、队列状态和故障路径，以及镜像/source/install/model身份、挂载权限、选中GPU UUID和shard EGL。
2. 在新 run subroot 完成抓放校准测量、校准聚合准入、验证 bundle 准备及抓放 live 验证；范围包含容器化、YOLO-only Worker 感知策略、R6 消费和 head 检测 IPC。按当前抓放验证合同完成 9 项阶段前缀和连续 5 次完整运行，并由独立反读生成抓放资格报告。另以可控八路同时请求测量 head IPC 的排队、推理和端到端响应时延，核对已批准的 `perception_job_timeout_s`、源帧新鲜度与迟到拒绝。这些属于校准和接口证据，八 Worker 采集资格另行验证。
3. W1 真实容器链路证明 ROS/DDS、MuJoCo EGL、controller、双 RGB、head 搜索 IPC、教师 IPC、原始 bag 录制及离线生成的 10 Hz episode、独立 QC 和 seal/verifier/commit；再以完整八场景 W1/W2 验证功能等价和隔离。Teacher 成功与数据 VALID 必须分别读回，不能用其中一个替代另一个。
4. W2通过后，以YOLO教师运行独立40场景、两20项wave的exact-W8；清单与功能/正式split不重叠。每wave八Worker各预留两项，余四项按冻结顺序拉取；每Worker至少两terminal，零infra/重试/crash-resume。仅Recorder丢失、10Hz间隔、QC合格率、Teacher物理成功率沿用既有规则作指标门槛；从bag、QC和场景receipt直接核验，身份/拓扑/cleanup仍必需。资源日志尽力记录CPU/GPU/RAM、磁盘I/O、RTF/队列等已有读数及吞吐，无通用metric registry/reducer/coverage门禁，缺测说明原因。磁盘沿用已有空间规则停止新派发，进程/服务故障走既有处理；不W4/W6、不降档。
5. 正式采集使用 YOLO 教师 image 和 Head Search 目标来源，在新 campaign 中按通过的 exact-W8 资格启动、逐条 QC、持续资源监测和完整证据提交。实际资源瓶颈出现时停止新派发并等待人工决策，不通过临时修改 Worker 数、实例数或阈值继续。

八 Worker 的独立 verifier 必须从磁盘重算冻结资格合同、campaign index、两个 wave journal、每个 Worker 的实际 terminal lease、逐场景 commit/receipt 和四项质量/业务结果。任何 scene 缺失或重复、任一 Worker 每 wave 少于两个实际 terminal lease、非八 Worker 拓扑、容器/共享服务身份不符、cleanup 未收敛或门槛不达标都拒绝资格。资源日志仅供诊断，缺测或日志消失不替代质量证据，也不单独否决资格。专门构造只有 9+5 抓放 live 证据的输入，验证它不能通过八 Worker 资格；也测试伪造 `PASSED`、缺少一波、跨 run 拼接以及 identity mismatch。当前 `parallel_qualification_verifier.py` 的业务名称可继续使用，但其现有检查不足以提供上述证明，必须在迁移中补齐。

八 Worker 资格报告使用单一闭合合同：`schema_version=1`、`kind=ACT_PARALLEL_COLLECTION_QUALIFICATION`，通过终态只有 `QUALIFIED`。它与抓放 live 资格是不同业务文档，不接受同一业务的 `PASSED`/`QUALIFIED` 双格式。当前 `so101_teleop/unified/admission.py` 要求 `PASSED`，而 `parallel_qualification_verifier.py` 要求 `QUALIFIED`；迁移必须同步修改报告 writer/schema、启动 admission、verifier 和调用方。报告绑定冻结资格合同、两类镜像/source/install 身份、场景清单、两波 journal、逐场景 commit/receipt 与质量/QC 原始证据，不能只存聚合结论。新报告的文件引用用 `path,sha256`，绝对路径受登记 ROOT 和对应 run 的范围约束；规则输入按批准配置反读。已有 index/seal/receipt 内的引用格式不变，不因容器化统一迁为相对路径。资源日志引用可为空，读取失败只报告缺测，不进入资格通过条件。

资格 run 与正式 campaign 使用同一登记 durable evidence root 下不同且不可覆盖的 subroot。正式 campaign 保存资格报告的只读引用，不移动、复制或重新签发资格证据。启动入口以登记 root 为资格证据的受限解析边界，验证真实路径、拒绝符号链接和路径逃逸，再重算报告与完整证据链的 hash；报告的 run 身份仍是原资格 run，不得替换成正式 campaign 身份。当前 admission 将 receipt 限制在当前运行 root 的规则须针对这一资格引用明确调整，其他 activation receipt 和 case 工作区仍保留各自边界。受控 source/config 身份不匹配拒绝引用；第 7 节允许下一 campaign 调整的运营参数不作隐含否决条件。跨登记 root 的引用不在本设计支持范围内。验收须包含一个新正式 campaign 的启动正例，以及旧 14 项 live 报告、终态不一致、篡改引用、路径逃逸和受控身份不符的启动负例；不能只测试 verifier 函数返回 `True`。

全量 package/xdist 测试只在计划规定的集成边界运行；定向 RED/GREEN 与测试 scratch、退出码和耗时照项目门禁记录。本设计的审查通过表示方案可以供实施计划使用；校准、live 验证、并行资格、正式采集和训练各自保存执行证据。
