# 审查：SO-101 ACT 容器化采集 campaign 执行计划

审查对象：`docs/superpowers/plans/2026-10-11-so101-act-containerized-campaign-implementation.md`（本地工作树，465 行，64.7 KB；下文行号以该文件为准）。

对照材料：
- 设计：`docs/superpowers/specs/2026-09-30-so101-act-containerized-campaign-design.md`（10-11 修订版，已纳入上一轮设计审查和用户的三条决定）。
- 计划自带的 Astra 两轮审查记录（`...-implementation-astra-review.md`，第二轮 PASS）。
- 代码基线：`origin/codex/so101-act-data-0917a` @ `6baf54e6313d`，从子模块 git 数据只读 `git archive` 到设备上的临时目录读取；没有切换或改动工作树，没有运行测试、Docker、ROS 或 MuJoCo。
- 用户已定的三条：本文就是 10-06 所说的 Docker 隔离后续版本；感知只用 YOLO；不做资源预算，资源不够时再想办法。

审查日期：2026-10-11。

## 2026-10-11 用户决定（P1-4）

用户选择“只卡数据质量”：W8 资格的硬门槛只包括 Recorder 丢失、10 Hz 间隔、QC 合格率和 Teacher 物理成功率，阈值沿用现有 QC 和成功率配置；CPU、GPU、RAM、磁盘 I/O、RTF 和吞吐只记录并写进报告，不设通过线；磁盘剩余见底时停止派发。计划第 267–284 行的 metric 表和第 426 行的 gate freeze 应按此改写。

## 2026-10-11 第二遍复核

用户要求再审一遍。计划文件未改动（465 行、64663 字节，SHA256 `d0b6caf7…3046`，mtime 与首轮一致），所以这一遍是对首轮结论的独立复核，重点重新打开源码核对每条 P1 的依据。

- 五条 P1 全部成立，依据都能在基线源码中再次找到；没有发现新的 P1。
- P1-3 补一个细节：基线 `decide()`（`perception.py:439–446`）已经把 `INFRA_ERROR/QUEUE_TIMEOUT/INFERENCE_TIMEOUT` 判为 attempt INVALID（基础设施），`NORMAL_REJECTION/MODEL_ERROR` 在回退用尽后判 FAILED（Teacher 结果）。缺的是 wire 侧新增的 `QUEUE_FULL`、`INPUT_INVALID`、`NOT_DETECTED` 三个值的归类。计划应写明保留现有归类，只补这三项，而不是重新设计。
- 另外核实了 Astra 记录引用的 `head_search_aggregate/aggregate.py:179–189`（九项 gate 成立才发布）、账本中的 evidence root 和 CP-3557、`parallel_perception_broker.py:138` 的 `--gpus all`、`ros_child.py:153` 的 `os.kill(web_pid, 0)` 和 `bridge.py:603/622` 的 Popen.pid 比较，均属实。
- 小提醒：基线的 `setup.cfg`、`pytest.ini` 和 `tools/so101_pytest_gate.py` 里都没有 xdist 配置，计划第 372 行的 `-n` 依赖 pytest-xdist 已安装；计划第 377 行已要求先核对，执行者照做即可。

## 结论

**计划的结构和设计一致，大部分代码引用属实，但还有 5 个 P1 应在交给 `dst` 执行前补上。** 这 5 项都属于计划没写清楚、执行者到了现场只能停下或自己猜的地方，Astra 两轮审查都没覆盖到。其中第 4 项需要用户拍板。

已核实属实的部分（逐条对过源码）：
- 计划“改”字标注的 70 余个现有文件全部存在于基线；“新”字标注的模块、CLI、目录在基线中都还不存在，不会和现有代码重名。
- 计划指出的几个基线缺陷都是真的：`cli/act_collect_parallel.py:22` 读取不存在的 `act_collection_context`，`:62` 以字典加第二个位置参数调用 `start`，而 `UnifiedWorkloadService.start(spec: OperationSpec, *, allow_existing=True)`（`unified/admission.py:602`）不接受这种调用；admission 要求 `PASSED`（`admission.py:482`），verifier 要求 `QUALIFIED`（`parallel_qualification_verifier.py`），且 verifier 只检查 9+5 的 live 摘要（测试 `test_act_eight_worker_qualification.py:20` 正好 14 项）。
- 路径合同一节引用的绝对路径约束属实：`act/calibration.py:99–100`、`pick_place_validation_artifact_bundle.py:219`、`offline/engine.py:536–544`（含空的 `stall_telemetry={}`）。
- 处理时限：`offline/orchestration.py` 中 `PROCESSING_TIMEOUT_S=1200`、`SEAL_MARGIN_S=60`、`MIN_PROCESSING_S=60`，与计划第 244 行的 `min(1200 s, lease 剩余-60 s)` 一致。
- `OperationSpec` 七个字段、`finish(context, *, cleanup_confirmed)`、`ProcessOwnerKey(pid,pgid,started_ticks,argv_sha256,environment_sha256)`、`SO101_CHILD_WEB_PID`、`ActChildLaunch`/`reserve_many` 均与计划描述相符。
- `measure_parallel_resources` 在基线中已不存在；`measure-feedback-bootstrap` 只剩一个返回 `HEAD_ONLINE_BOOTSTRAP_REMOVED` 的拒绝分支（`cli/head_search_calibration.py:84`），与计划“不恢复”的说法一致。
- 计划中五个现有 CLI 的参数（第 391–414 行）与各 CLI 的 `add_argument` 完全一致。
- 三条用户决定在计划中都已落实：第 20 行 YOLO-only，第 25 行不按 1/2/4 硬编码、不做容量预算，第 3、465 行要求单独批准。

## P1：交给执行者前应补齐

### P1-1 教师模型身份现在写死在源码里，计划没有安排迁出（第 99、101、117 行）

- 事实：教师 YOLO 的权重 hash 是源码常量 `parallel_batch/frozen_models.py:5`（`FROZEN_YOLO_WEIGHTS_SHA256`）；模型 ID、镜像 tag、依赖 pin 在 `runtime/parallel_perception_runtime.py:39–47`（`YOLO_ID`、`IMAGE_TAG`、`PINS`）；分数阈值是 `adapters/perception/yolo_seg.py:240` 的 `conf=0.25`，而且这个类 head 检测和其他业务也在用。基线没有任何“教师模型配置文件”。
- 计划第 99 行要求 campaign config 的 `model.weights/score_threshold` 等“值从现有受控运行/模型配置读回”，第 117 行要求回归测试证明“改 Teacher score/weights 时 controlled runtime hash 不变”。按现状，换权重或阈值必须改源码，`source_sha256` 会跟着变，这正是设计 §7 要避免的“模型参数间接变成受控门禁”。
- 建议：在“推理合同与配置身份”一步明确列出 `frozen_models.py`、`parallel_perception_runtime.py` 常量和 `YoloSegDetector` 的 `conf` 改为由服务配置注入，写清第一份 campaign config 的初始值取自这些现有常量（0.25、`f281d252…`、`plastic-cup-yolo11n-seg-v1`），并说明 head 侧阈值仍由 Head Search 绑定决定，不随教师配置变化。

### P1-2 macOS 路径共用要改的 Broker 代码，计划没有处理（第 20、118、175、243 行）

- 事实：`runtime/macos_two_worker_broker_port.py:151–152` 直接使用 `BrokerTransport` 和 `parallel_perception_runtime.Snapshot`；`parallel_perception_runtime.frozen_options()` 的注释写明 macOS schema-v4 组合以 `requested_device='mps'` 调用它；`parallel_batch/broker.py:89–104` 的 Broker 构造函数强制要求 `grounded_model_id`。
- 计划一方面要求“整体替换 broker_call、删除 `_BROKER_COMPATIBILITY_FIELDS`、YOLO-only”，另一方面写“不移除仓库其他业务的 Grounded/SAM 功能”。如果照前者改，macOS 双 Worker 路径会坏；如果保留旧 Broker 给 macOS，又与第 18 行“每类业务只有一个当前接口”相冲突，计划需要说明这是不同业务。
- Worker 接入一步的文件清单也漏了几个实际构造回退的文件：`runtime/parallel_ros_ports/perception.py:157–160`（以 `GROUNDED_ID` 构造 `PerceptionPolicy`）、`parallel_batch/broker.py`、`cli/parallel_perception_broker.py`、`cli/mujoco_batch/{request,outcome,provenance,rpc_proxies}.py`、`docker/parallel-perception/`。第 175 行“所有当前推理调用方”太笼统，执行者会自己划范围。
- 建议默认做法：旧 `broker_call`/Broker/`parallel-perception` 镜像保留给 macOS 和其他业务，明确标为另一业务的接口；ACT 容器采集路径只用新推理合同，并在 Worker 接入一步列出上面这些文件逐一处理（迁移或声明不涉及）。

### P1-3 新响应 outcome 与 Worker 内部 `ModelOutcome` 的映射没有定义（第 189 行）

- 事实：Worker 内部的 `ModelOutcome`（`parallel_batch/contracts/common.py:96`）是 `QUALIFIED/NORMAL_REJECTION/MODEL_ERROR/INFRA_ERROR/QUEUE_TIMEOUT/INFERENCE_TIMEOUT/CANCELLED`；`decide()`（`perception.py:428` 起）按这些值决定回退。设计 §3.4 的新 wire outcome 是 `DETECTED/NOT_DETECTED/INPUT_INVALID/QUEUE_FULL/QUEUE_TIMEOUT/INFERENCE_TIMEOUT/MODEL_ERROR/INFRA_ERROR`。另外，`admit_pose()` 把本地 R6/准入拒绝也记成 `NORMAL_REJECTION`。
- 计划第 189 行写“`NOT_DETECTED/MODEL_ERROR` 给当前边界明确失败”，用的是 wire 名称，没有给出完整映射：`QUEUE_FULL`、`INPUT_INVALID` 在内部没有对应值；超时、排队满应当算 Teacher FAILED 还是基础设施/数据 INVALID，计划没写。这直接影响计划第 26 行强调的“Teacher 结果、数据状态、基础设施故障三分”，也影响 W8 的成功率分母。设计特别提醒过不能因 `ModelOutcome.QUALIFIED` 这个名字绕过 R6。
- 建议：在 Worker 接入一步加一张闭合映射表（8 个 wire outcome 加本地 R6 拒绝，对应到内部 outcome 和 attempt 终态），并说明 `ModelOutcome.QUALIFIED` 是否改名；补一条测试，逐项验证这张表。

### P1-4 W8 资源门槛没有批准值，按计划写法执行到这一步一定会停下（第 267、426 行）——需要用户决定

- 事实：计划要求在 W8 前冻结 CPU、GPU 利用率和显存、RAM、磁盘余量和 I/O 延迟、MuJoCo RTF、Recorder 积压和丢失、10 Hz 间隔 p99、episode/min、Teacher 成功率、QC 合格率、前后半程吞吐比，共 14 项指标，每项都要有 `limit` 和 `approval_reference`，“缺项不猜通过线，停在 gate freeze 等待用户批准”。基线的 `config/act/*.yaml` 里没有这些数值，前面的设计也没给。
- 这与用户的第三条决定（不做资源预算，资源不够再想办法）有张力：给 CPU、GPU、RAM 设 `max <=` 的通过线，本质上就是一份资源预算。
- 建议（推荐）：W8 资格只把**数据完整性和业务结果**作为硬门槛（Recorder 丢失、10 Hz 间隔、QC 合格率、Teacher 物理成功率，阈值沿用现有 QC/成功率配置）；CPU、GPU、RAM、磁盘 I/O、RTF、吞吐只记录、进报告，不设通过线；只保留“磁盘剩余低于下限”和“采集数据出现缺失”这类真正会损坏数据的情况作为停止派发条件。这样 W8 不会卡在等阈值上，也符合第三条决定。

### P1-5 校准测量和抓放 live 阶段由谁启动、准入共享服务，计划没有写（第 76、322–359 行）

- 计划给 W1/W2/W8/正式采集定义了 `ContainerCampaignOwner` 启动两个服务、发 shard。但在更早的校准测量（`ContainerMeasurementPort`）和 9+5 抓放 live（`ContainerCasePort`）阶段已经需要共享 head 服务（第 344、348 行），计划没有说这两个阶段的服务由谁启动、属于哪个 campaign config、经过哪次 admission，也没有给非 wave 场景的 staging 前缀（设计只定义了 `r/{wave}/wNN/g{generation}`）。
- 另一个相关点：`_PICK_PLACE_VALIDATION_PAYLOAD_KEYS = _ACT_PAYLOAD_KEYS | {...}`（`admission.py:252` 附近）。第 314 行给 `_ACT_PAYLOAD_KEYS` 新增 `registered_evidence_root`、`campaign_config_*` 等字段，会同时改变抓放验证和诊断 episode 的 payload，计划只讨论了采集一种。
- 建议：在生产接线一节补一段“测量/live 阶段的服务生命周期”，说明 owner、campaign config、admission kind、staging 前缀和退役时机；同时列出 payload key 变更对抓放验证、诊断两类 payload 的影响。

## P2：文字与一致性

- **P2-1 资格合同的 schema 文件名前后不一致，旧 writer 没有点名替换。** 第 75 行写的是 `config/act/parallel-qualification-schema.json`，第 288 行写的是 `parallel-qualification-contract-schema.json`。基线已有 `act/parallel_collection.py:36` 的 `create_qualification_contract`（kind 为 `SINGLE_WORKER/TWO_WORKER/EIGHT_WORKER`、`scenes=40`），以及 `require_collection_mode`，被 `act_fixed_collection_composition.py:85–93` 调用。计划新定义的 `ACT_PARALLEL_COLLECTION_GATE` 应写明替换它们；W1/W2 功能运行用什么合同也要写出来。
- **P2-2 “每 Worker 每 wave 至少两个 terminal lease”只有验收，没有实现步骤（第 27、427 行）。** 派发是拉取式，快的 Worker 可能多拿，慢的拿不到第二个。需要一个“先每 Worker 预留 2 个，余下 4 个按顺序派发”的派发步骤和测试；`parallel_batch/adaptive_queue.py` 的 `initial_points_per_worker` 可作参考。
- **P2-3 head 服务配置要从 Head Search 绑定派生。** `adapters/act/detector.py:40–50` 校验绑定中的 `torch_version`、`ultralytics_version`、`torch_threads`、`torch_interop_threads`，不一致就报 `HEAD_SEARCH_RUNTIME_VERSION_DRIFT`/`THREAD_DRIFT`。计划第 99 行把 `torch_threads` 当作两个服务共同的 campaign 字段，建议写明 head_service 的模型、线程和 head 镜像内的 torch/ultralytics 版本必须等于绑定值，不属于运营参数。
- **P2-4 head 超时的措辞容易误读（第 23 行）。** “不能默认采用或放宽 `perception_job_timeout_s`”可能被读成“不用这个参数”。设计 §3.2 的意思是：完整等待时间计入本 campaign 已批准 policy 中的 `perception_job_timeout_s`，`default_document()` 里的 1.0 s 只是候选值。建议改成这个说法，并提醒 `HeadSimulationPolicy` 的不变式 `perception_max_age_s <= perception_job_timeout_s <= stop_confirmation_timeout_s`（`head_simulation_policy.py:66–67`）。
- **P2-5 兼容字段清理范围偏窄（第 118 行）。** 只扫描 `_BROKER_COMPATIBILITY_FIELDS`；设计基线表还点名了 `parallel_perception_runtime.Snapshot` 的 `start_event_id/start_event_type/start_identity` 兼容字段，应一并列入（注意 P1-2 中 macOS 仍在使用它）。
- **P2-6 类别映射。** `HeadRgbDetector` 只接受字符串类别 `plastic_cup`/`cup`（`detector.py:153`）；wire 使用 `query_class_id` 和服务内的受控映射。`HeadIpcDetector` 需要把类别映射回原字符串，计划没写。
- **P2-7 链接与目录。** 第 363 行链接的 `docs/guides/so101-act-data-collection-training-guide.md` 只在本地 main 上，基线分支没有；执行者在分支 worktree 里找不到。新建的 `test/integration/` 目录在基线 `so101_demo_py/test` 下不存在，与 10-10 代码风格重构“测试镜像源码目录”的约定不一致，建议放到 `test/runtime/` 或说明理由。

## 建议的修订顺序

1. 请用户决定 P1-4（资源指标是硬门槛还是只记录）。
2. 补 P1-1、P1-3：模型常量迁出，加 outcome 映射表。这两项都属于“推理合同 / Worker 接入”步骤，改动集中。
3. 补 P1-2：确定 macOS/旧 Broker 的处理方式，并补全文件清单。
4. 补 P1-5 和 P2 各项。
5. 修订后可直接交执行；不需要再走一轮完整设计审查，只需复核以上几处。
