# SO-101 ACT Task 8 准入工件生成设计

**日期：** 2026-09-28
**状态：** 用户已批准，待实施
**适用范围：** ai-station、MuJoCo、Task 8 live 准入
**关联设计：**

- `docs/superpowers/specs/2026-09-10-so101-act-head-wrist-rgb-design.md`
- `docs/superpowers/specs/2026-09-24-so101-act-task8-live-formal-collection-design.md`
- `docs/superpowers/specs/2026-09-27-so101-controller-reservation-transport-design.md`

## 1. 背景

Task 8 live 的运行入口当前要求七个工件：`source`、`manifest`、
`runtime_config`、`collection_config`、`calibration_report`、`proposal` 和
`activation_receipt`。现有实现能校验这些文件及其 SHA256，但缺少一条完整的生产链。

当前缺口有三处：

1. `source_sha256` 没有对应的规范文件，无法说明它绑定的是提交、安装产物还是某个源码文件。
2. 实施计划引用 `src/so101_demo_py/config/act/parallel_collection_v3.yaml`，仓库中尚无该文件，也没有闭合 schema。
3. MuJoCo 可以产生逐 anchor 的搜索证据，但没有确定性的测量合同和聚合器把这些证据转换成
   `head_search_qualification` 样本和 `TASK8_READY` 校准报告。

因此，已有准入代码只能拒绝启动。不能通过手写状态、复用旧 identity 下的部分报告，或把任意
`parallel_batch_v*.yaml` 当作 collection config 来绕过这个拒绝。

## 2. 设计目标

本设计增加一个独立的 artifact preparation 层。它负责生成、验证和冻结 Task 8 live 所需工件，
但不取得 campaign 资源，不创建 ROS child，也不提交控制器 goal。

保持以下既有约束不变：

- 仿真后端只允许 MuJoCo。
- campaign 资源绑定只在 `UnifiedWorkloadService.start(spec)` 校验一次。
- 内部 Worker、Broker、Recorder、Task 8 phase 和 ROS driver 不读取或复验资源 lease。
- 只有精确的 `owner == act` acquire 可以消费一次性控制 session。
- cleanup 继续使用 generation-scoped、single-flight 状态机。
- 每个 case 使用独立 `FULL_RESTART` owner，并取得 child 和 stack 两份 retirement receipt。
- `DETACH_MOVEIT` 必须早于 `OPEN_GRIPPER`。
- W2 通过后直接运行独立 40 场景 W8；不测试 W4、W6，也不自动降档。
- 本设计不授权真实机械臂，也不授权正式采集。

## 3. 总体流程

```text
冻结 source/runtime/collection identity
                    |
                    v
      MuJoCo 校准测量（原始证据）
                    |
                    v
      确定性 calibration aggregator
          |                    |
          v                    v
head_search_qualification   calibration_report
          |                    |
          +---------+----------+
                    v
               act_preflight
                    |
                    v
 Task 8 manifest + preparation receipt
                    |
                    v
 UnifiedWorkloadService.start(spec)
                    |
                    v
 phase-prefix -> 5 次 FULL_RESTART
```

preparation 和 admission 是两个事务。preparation 可以失败并保留证据，但失败不能留下可被 admission
接受的半成品。admission 只消费经过原子提交、带有效 preparation receipt 的工件目录。

## 4. 工件定义

### 4.1 Source provenance

新增 `task8-live-source-provenance.json`。`source_sha256` 是该文件的内容 SHA256，不再指向任意源码文件。

文件使用闭合 JSON schema，包含：

```json
{
  "schema_version": 1,
  "kind": "task8_live_source_provenance",
  "repository_head": "<40-hex>",
  "submodules": {"<path>": "<40-hex>"},
  "calibration_identity": {
    "source_commit": "<40-hex>",
    "config_sha256": "<64-hex>"
  },
  "runtime_roles": [
    {
      "logical_name": "command_broker",
      "artifact_kind": "verbatim_install",
      "source_path": "src/so101_demo_py/src/adapters/act/command_broker.py",
      "source_sha256": "<64-hex>",
      "installed_path": "<absolute-path>",
      "installed_sha256": "<64-hex>"
    },
    {
      "logical_name": "mujoco_support_plugin",
      "artifact_kind": "compiled",
      "installed_path": "<absolute-path>",
      "installed_sha256": "<64-hex>",
      "build_receipt_path": "<absolute-path>",
      "build_receipt_sha256": "<64-hex>"
    },
    {
      "logical_name": "mujoco_runtime",
      "artifact_kind": "external_runtime",
      "loaded_path": "<absolute-path>",
      "loaded_sha256": "<64-hex>",
      "version": "<non-empty-string>"
    }
  ]
}
```

`runtime_roles` 由代码中的闭合 registry 生成，调用者不能自由删减。registry 至少覆盖 Task 8 Python
入口、`so101_teleop` child/owner、MuJoCo simulation-evidence plugin、broker-owned controller plugin、
`mujoco_ros2_control` plugin、机器人模型/控制器配置、ROS 运行时和模型权重。logical name 唯一，按名称排序。

三类角色分别验证：

- `verbatim_install`：源文件和安装文件字节相同；
- `compiled`：记录输出库 hash，并绑定 build receipt。receipt 列出完整源码/头文件输入、CMake 参数、
  编译器与链接器版本、依赖库 hash 和输出 hash；
- `external_runtime`：记录实际加载路径、文件 hash 与版本，不用源码字节等同替代。

缺少必需角色、重复角色、错 hash、build receipt 不完整或进程实际加载另一个路径时拒绝生成 provenance。

工作区可以保留与运行无关的用户改动。所有 registry 覆盖的源码、头文件、配置和构建输入必须相对
`repository_head` 无修改；Task 8 相关改动先提交 checkpoint，再进行校准。preparation 使用显式 allowlist
检查这些路径，不要求清理无关的用户文件。任一受控路径变化都会使旧 source provenance 和旧校准失效。

provenance JSON 使用 UTF-8、字典键排序、紧凑分隔符和一个结尾换行进行 canonical serialization。
路径字符串使用规范化绝对路径或仓库相对 POSIX 路径。相同输入必须生成逐字节相同的文件。

### 4.2 Runtime config

沿用已经通过生产 validator 的 head-search runtime config。闭合字段继续由
`validate_head_search_binding()` 定义，包括：

- YOLO segmentation backend、weights 绝对路径和 SHA256；
- `image_size_px=640`、requested device、CPU fallback 与 Torch 线程数；
- Torch、Ultralytics 版本；
- `head_camera_frame`、640×480；
- neck goal tolerance、settle velocity 和 goal duration。

preparation 只接受生产 validator 可以解析的内容。模型文件、版本或设备选择变化后必须生成新的 runtime
config 和新的校准报告；旧报告不能与新 config 配对。

Task 8 live 的 head-search config 与 `parallel_batch_v3.yaml` 都必须请求 CUDA，并设置
`allow_cpu_fallback=false`。两者的设备语义不一致时 preparation 拒绝。资源不足属于人工决策 blocker，
不能通过切到 CPU 自动恢复。已生成但允许 CPU fallback 的候选 runtime config 必须作废并重新生成。

### 4.3 Collection config

新增：

- `src/so101_demo_py/config/act/parallel-collection-v3-schema.json`
- `src/so101_demo_py/config/act/parallel_collection_v3.yaml`

该配置保存 ACT collection 自己的 workload、Recorder、资格和恢复语义，不复制
`parallel_batch_v3.yaml` 的公共运行字段。首版冻结如下内容：

```yaml
schema_version: 1
kind: act_parallel_collection
parallel_runtime:
  path: config/mujoco/parallel_batch_v3.yaml
  sha256: <64-hex>
qualification:
  functional_worker_counts: [1, 2]
  load_worker_count: 8
  formal_worker_count: 8
  max_wave_size: 20
  no_auto_degrade: true
recovery:
  business_retry_count: 0
  max_infra_attempts_per_scenario: 2
  resume_requires_identical_business_hashes: true
recorder:
  sample_rate_hz: 10
  queue_capacity_samples: 16
  queue_high_watermark_samples: 12
  queue_recovery_watermark_samples: 8
  queue_high_watermark_hold_s: 0.2
  lossless: true
telemetry:
  period_s: 1.0
```

`max_infra_attempts_per_scenario=2` 表示初次执行加一次显式基础设施恢复，不表示业务失败可以重试。
Recorder 的队列值是本次 W2/W8 资格使用的冻结起点，不是永久默认值。若 W8 证明它形成资源瓶颈，
campaign 停止；修改配置会产生新 hash，并要求重新资格，而不是运行中调参。

一个 Recorder sample 是同一决策时刻的 head RGB、wrist RGB、8 维机器人状态、下一时刻 controller
reference 和对应 audit identity。队列容量按 Worker 计算。每次 enqueue 都同步检查深度；到达 capacity
立即成为基础设施失败，深度连续 0.2 s 不低于 high watermark 也停止新业务并进入受控清理。1 s telemetry
只用于 campaign 资源记录，不承担溢出保护。恢复发放新工作前，深度必须回落到 8 或以下。

W1/W2 功能资格和独立 40 场景 W8 资格仍要求零基础设施中断，因此资格运行只接受第一次 attempt。
第二次 attempt 只用于显式验证恢复协议或正式采集恢复，不能拼接进资格结果。

Task 8 live 尚不启动 Recorder，但仍绑定该配置，保证 phase-prefix、完整 Task 8、W8 资格与后续正式采集
共享同一组业务身份。配置只在 campaign 启动入口校验，内部组件不重复解析资源字段。

`parallel_runtime.path` 从已安装 `so101_demo_py` package share 解析，只接受规范化仓库相对 POSIX 路径；
绝对路径、`..`、symlink 或越出 package share 均拒绝。SHA256 按 YAML 原始字节计算，不对 YAML 重排后再算。

### 4.4 测量合同

新增 `task8-calibration-measurement-contract-v1.json` 及闭合 schema。合同在启动测量前写入并计算 hash，
聚合器只接受与该 hash 完全一致的 batch。合同绑定 source provenance、runtime config、anchors、
`POLICY_FINGERPRINT`、ACT profile config 和下列冻结阈值来源：

- head-search detector/camera/motion limit 来自 runtime config；
- velocity、acceleration、goal tolerance 和 controller period 来自已安装 controller config；
- 2 ms path grid、25 ms 完整调用上限、clearance/contact allowlist 来自已批准的 Task 8 path proof 合同；
- freshness、skew、stop velocity 和 stop latency 上限来自当前批准 calibration/runtime policy；
- phase 与 camera 的覆盖矩阵来自冻结的 Task 8 phase plan。

合同同时保存上述来源文件的路径和原始字节 hash。聚合器不得用本次观测到的较差结果放宽合同阈值。
每个测量项分别记录 `configured_limit`、`observed_summary` 和 `reported_value`；`reported_value` 必须按合同
给出的固定公式生成，并且不能比 `configured_limit` 更宽松。

五项检查的闭合判据如下：

| 检查 | 覆盖和计算 | PASS 规则 |
| --- | --- | --- |
| `fov` | default、left、forward 三个 anchor 的完整专家 phase 路径；按 phase-camera 矩阵逐个 2 ms 轨迹样本投影目标 bbox | 每个要求可见的样本都落在对应 camera 有效区域，面积、aspect 和 occlusion 符合冻结阈值；静态起点可见不能替代完整路径 |
| `search` | 每个 anchor 独立运行；按 frame timestamp 排序并按 target identity 分组 | 每个 anchor 都有同一目标至少 3 个连续、新鲜且满足 confidence/area/aspect/vertical bound 的 lock frame；跨 anchor 帧不能拼接 |
| `synchronization` | 对每个 run 配对 RGB、joint/TF、reference 和 physics 时间戳，计算 count、max、p50、p95、p99 | 零缺样、零时间倒退；每个样本的 age 和 skew 都不超过冻结上限，分位数只作审计，不能掩盖单点越界 |
| `collision` | 三个 anchor 的完整 phase path、精确 2 ms 行、首个完整请求和随后 3 个请求；全机器人与 held-cup contact | 每一行通过现有 PathProof/allowlist，净空不低于冻结值，无非法接触；四次完整调用各自不超过 25 ms，不能只计 worker 内部时间 |
| `execution` | controller period、提交时间、完整 reference/feedback、速度/加速度、terminal stop 与 cleanup | reference 与 permit 精确一致；所有速度/加速度在冻结 limit 内；submit lead 合法；首尾停止均满足 stop velocity/latency，且 cleanup receipt 完整 |

一项缺输入时为 `UNMEASURED`，出现任一有效越界时为 `FAIL`。无效 run 不参与 PASS/FAIL 统计，而是使当前
batch `INVALID`；修复污染后必须建立新的 batch。原始文件自带的 `PASS` 字段不参与聚合裁决。

### 4.5 原始校准证据

新增 `act_measure_task8_calibration`。它只负责运行测量和关闭原始 evidence batch，不决定最终状态。

每个测量批次必须绑定：

- source provenance SHA256、measurement-contract SHA256、runtime config 和 ACT profile identity；
- ROS Domain、MuJoCo session、overlay、可执行文件和模型 hash；
- default、left、forward 三个 anchor；
- reset epoch、attempt、controller generation 和 monotonic 时间线；
- head/wrist RGB、关节与 TF、controller reference/feedback、MuJoCo pose/contact；
- 进程、socket、goal 和 owner cleanup 结果。

测量入口先写账本 `PLANNED`，完成 provenance、冲突进程、scratch、stop boundary 和 cleanup owner 检查后
才能进入 `RUNNING`。一次无效运行标记为 `INVALID`，不能被聚合器计入通过结果。

单个 run 内的 RGB、reference、physics 和 controller 数据必须属于同一 session、reset epoch 与 attempt。
不同 anchor 或 `FULL_RESTART` 可以使用不同 session；聚合器逐 run 验证后，只在 source provenance、
measurement contract、runtime config、anchors 和 policy 全部相同时合并。它不得把多个 session 的帧描述成
一个虚构 session。

### 4.6 Calibration aggregator

新增纯离线命令 `act_build_task8_calibration_report`。它读取已关闭的测量 batch，不启动 ROS、MuJoCo 或模型。

它输出三个文件：

1. `head-search-qualification.json`：满足 `validate_head_search_binding()` 现有闭合格式；
2. `task8-ready-calibration.json`：满足 `calibration-schema.json`；
3. `aggregation-receipt.json`：列出全部输入路径、hash、判据、计算结果和工具版本。

聚合器必须重新计算输入 hash，并核对同一个 source commit、config SHA256、runtime descriptor 和
source provenance SHA256。任何 batch 未关闭、身份混用、样本过期、hash 错误或 cleanup 不完整都会拒绝输出。

`head-search-qualification.json` 保持现有 closed sample 结构，但增加
`source_provenance_sha256`。它包含 `_MEASURED` 的 17 个字段和 4 个 camera measurement；报告中这 17 个
measurement 的 `sample_path/sample_sha256` 全部指向同一个 qualification sample，值逐项相等。
`observed_lock_frames` 写三个 anchor 中“同一目标连续合格 lock frame 数”的最小值，因此它至少为 3 时，
才能证明每个 anchor 均满足门槛。raw evidence index 单独保存在 aggregation receipt，不向 closed sample
塞入额外字段。

`task8-ready-calibration.json` 同样增加必填 `source_provenance_sha256`。生产
`ActArtifactBinding.verify()` 在 campaign 启动入口读取报告，并要求该字段等于 admitted `source_sha256`；
`act_preflight` 和 `validate_head_search_binding()` 继续验证 report/sample 内部一致性。这样，同一 Git HEAD
下只要受控运行文件发生变化，也不能继续使用旧测量。

`TASK8_READY` 只能由计算结果产生：`fov`、`collision`、`search`、`synchronization` 和 `execution`
全部为 `PASS`，`release` 与 `retreat` 均为 `UNMEASURED`。命令行不提供 `--status TASK8_READY` 一类开关。
只要一项未测或失败，输出保持 `CALIBRATION_REQUIRED`；聚合器不得补默认值。

`QUALIFIED` 不属于这个命令。它只能在 Task 8 live 的 release/retreat 证据回填后，由后续正式资格流程
生成新版本报告。

## 5. Artifact preparation CLI

新增 `act_prepare_task8_live_artifacts`，输入：

- source root 与安装 overlay；
- runtime config；
- collection config；
- calibration report 和 head-search qualification sample；
- measurement contract 与 aggregation receipt；
- anchors；
- policy proposal 和 activation receipt；
- evidence root 与输出目录。

命令按固定顺序执行：

1. 生成并验证 source provenance；
2. 校验 runtime/collection schema 及引用文件 hash；
3. 校验 calibration identity、sample hash 和 `TASK8_READY` gate；
4. 校验 proposal、activation receipt 和授权的 `POLICY_FINGERPRINT`；
5. 使用现有 Task 8 manifest builder/writer 生成 manifest；
6. 对完整 artifact set 做一次与生产 admission 相同的只读验证；
7. 写出闭合的 `preparation-receipt.json`，其中保存核心工件和全部传递依赖的路径、角色和完整文件 hash；
8. 原子发布 receipt，提交 bundle。

manifest 有两个不同摘要，receipt 分别命名：

- `manifest_document_sha256`：manifest 内部字段使用的 canonical document hash，不包含自身字段；
- `manifest_file_sha256`：包含内部摘要和结尾换行的完整落盘文件 SHA256，交给 admission/context。

现有 `task8-live-schema.json`、manifest builder、validator 和 admission 的闭合字段必须同步迁移，显式加入
rebased calibration report 的路径与完整文件 hash；四处任一仍接受旧字段集时，迁移都不算完成。旧 schema
版本继续被新 production admission 拒绝，不能静默补默认值。

preparation 先以独占 `mkdir` 创建最终 bundle 路径。此时目录尚未提交，因为其中没有
`preparation-receipt.json`。失败后不得复用该目录；下一次 preparation 使用新的 bundle ID。

七个业务工件、measurement contract、aggregation receipt、head-search qualification sample、校准报告中
每个唯一 `sample_path` 指向的文件，以及 source provenance 引用的 build receipt，都进入传递依赖闭包。
preparation 逐字节复制它们，并逐文件 `fsync`。receipt 保存副本的最终路径、原始来源路径、角色与 hash。
proposal 和 activation receipt 的内容保持不变，复制不会重新签发 policy。

原始 calibration report 保留在旧 evidence 中，不修改。preparation 在 bundle 内另行生成确定性的
`admission-calibration-report.json`：所有 measurement 数值、单位和 `sample_sha256` 与聚合器原报告逐项相同，
只把 `sample_path` 映射为 bundle 内副本的最终绝对路径。path mapping、原报告路径/hash、rebased report
路径/hash 全部写入 receipt。manifest 在 rebased report 生成后构建，绑定 rebased report 的完整文件 hash。

bundle 目录从创建时就使用最终路径，因此 rebased report 在提交前也能通过现有 validator 的绝对路径读取。
全部工件和传递依赖写完后，preparation 运行 production validator，并枚举工件解析与验证期间实际打开过的
工件路径；任何这类读取路径不在 receipt 计划集合中都拒绝提交。Python import、ROS package index、动态库和
已安装运行文件等环境读取不计入 bundle 文件闭包，改由 runtime-role provenance 约束。随后将 receipt 写入
同目录临时文件并 `fsync`，以
destination-must-not-exist 的原子 rename 发布为 `preparation-receipt.json`，再 `fsync` bundle 目录和父目录。
receipt 的原子出现是唯一提交点。

副本中的 build receipt 或审计文件即使保留原始绝对路径，validator 也只能按 preparation receipt 保存的
“原始路径到 bundle 副本路径”映射读取审计依赖，不能重新打开旧 evidence。运行时真正加载的安装产物不做
路径重定位，按 source provenance 的实际路径和 role hash 核对。

`preparation-receipt.json` 是第八个启动工件，也是 bundle 提交标记。`ActArtifactBinding` 和 production
admission 必须验证它的 schema、闭包文件集、每个 hash、policy fingerprint、source provenance、两个
manifest 摘要和 bundle 目录身份；没有 receipt、路径不在同一 bundle 目录、遗漏传递依赖或 receipt 未列出的
manifest 一律拒绝。preparation receipt 只在启动入口验证，不传给内部组件重新复验。

崩溃发生在 receipt 发布前时，只留下不可准入的 uncommitted bundle；发生在发布后时，恢复流程重新验证
receipt、文件闭包与 hash，完整则保留，否则拒绝。已有诊断文件留在本 task evidence root，标记为失败批次。
该命令不启动 campaign。

## 6. Admission 与运行边界

`UnifiedWorkloadService.start(spec)` 仍是唯一资源校验入口。它验证 preparation 输出的路径、hash、policy、
MuJoCo backend、Worker 数、GPU/host binding、Domain、cleanup fence 和资源余量，随后返回冻结的
`AdmittedCampaignContext`。

preparation receipt 不是资源授权，也不能替代 admission。内部组件只接收运行需要的业务 identity、
generation、deadline 和审计 hash。它们不得回到 preparation 目录重新选择文件。

Task 8 live 的执行顺序保持不变：九个 phase-prefix 先行，然后在同一 commit、config、policy 和
`FULL_RESTART` 生命周期下完成五次连续有效成功。phase-prefix 和 Task 8 live 都不产生正式训练 episode。

## 7. 失败语义

| 失败边界 | 处理 |
| --- | --- |
| source/install hash 不一致 | preparation 拒绝，不生成 manifest |
| runtime/collection schema 或引用 hash 错误 | preparation 拒绝 |
| 测量 identity、sample hash 或 cleanup 不一致 | aggregator 拒绝，报告保持 `CALIBRATION_REQUIRED` |
| 任一 Task 8 ready 检查未通过 | 不生成 `TASK8_READY` |
| policy fingerprint 或 activation receipt 不匹配 | preparation 拒绝 |
| admission 资源检查失败 | 零 Worker、零 Broker、零 ROS child、零动作 |
| 校准或 Task 8 运行遇到资源瓶颈 | 停止并保留证据，等待人工决定，不自动降档 |
| release ordering 或 cleanup 无法确认 | 安全停止，不开始下一 case |
| bundle 写入、receipt rename 或目录 fsync 边界崩溃 | 无 receipt 的目录永不可准入；有 receipt 时恢复流程必须重验完整闭包和 hash |
| receipt 缺失、未 fsync 或文件集/hash 不闭合 | admission 拒绝，零进程启动 |

## 8. 测试与验收

实现按以下顺序推进：

1. source provenance 的必需 role、编译 build receipt、外部依赖和 collection schema 的 RED/GREEN 测试；
2. measurement contract 的来源 hash、覆盖矩阵、公式与冻结阈值测试；
3. aggregator 对缺文件、混 identity、错 hash、未关闭 batch、少于三个连续 lock frame、动态 FOV 缺口和伪造状态的拒绝测试；
4. 固定 measurement fixture 的确定性聚合测试，两次输出字节一致；
5. preparation CLI 的 artifact tamper matrix，以及每个 file/dir fsync、receipt rename 边界的故障注入；
6. admission 对 uncommitted bundle、无 receipt、遗漏传递依赖、receipt/file hash 冲突和错误 manifest digest 类型断言零进程；
7. 暂时移走或禁止读取旧 evidence 后，committed bundle 仍通过 production validator；rebased report 的数值和 sample hash 与原报告逐项一致；build receipt 等审计依赖只通过 receipt path mapping 读取；
8. 现有 partial 报告、旧 identity 报告和旧 source provenance 继续被拒绝；
9. ai-station 上重新构建并核对 source/install/build provenance；
10. 在登记的 NVMe scratch 和 evidence root 中运行 MuJoCo 校准；
11. `act_preflight` 对新报告返回 `TASK8_READY`，对 release/retreat 仍只接受 `UNMEASURED`；
12. 完整 artifact binding 与 production admission 只读验证通过；
13. 才能启动最小 `prefix-01`，随后按既有 Task 8 阶梯推进。

完整 Python gate 继续使用 xdist，worker 数为 `min(8, os.cpu_count() or 1)`。校准运行不是单测，不得用测试通过
替代 controller、MuJoCo、contact、pose、双 RGB 和 cleanup 的运行证据。

## 9. 迁移和文档更新

实现后更新 `docs/superpowers/plans/2026-09-11-so101-act-head-wrist-rgb-implementation.md`：

- 在 Task 6 与 Task 8 live 之间加入 artifact preparation 子任务；
- 将原 Task 11A 创建 `parallel_collection_v3.yaml` 的责任提前到该子任务，Task 11A 只消费并扩展验证；
- 明确 `source_sha256` 绑定 provenance JSON；
- 明确 calibration measurement 与 aggregator 分开；
- 同步迁移 `task8-live-schema.json`、manifest builder、validator 和 admission，绑定 rebased report 的完整 hash；
- 保留 W2 后直接运行独立 40 场景 W8、不测试 W4/W6的决定。

旧的 partial calibration、旧 runtime candidate 和失败 preparation batch 全部保留，只能作为审计证据，
不能改名或重写为本轮通过结果。

## 10. 完成条件

本设计的实现完成需要同时满足：

- 三类缺失业务工件和 preparation receipt 都有闭合 schema、生产者和篡改测试；
- `TASK8_READY` 可从当前 identity 的 MuJoCo 测量确定性重建；
- preparation 失败不能留下可准入 manifest；
- admission 仍只在 campaign 启动入口执行资源校验；
- Task 8 内部组件没有新增资源复验；
- 新工件、manifest、policy 和校准 identity 的 hash 全部一致；
- goal resume 后从 `prefix-01` 开始，不跳过既有安全阶梯。

设计文档通过审查不等于 Task 8 live 已通过。实际完成仍以 phase-prefix、五次连续
`FULL_RESTART`、独立运行证据和 cleanup proof 为准。
