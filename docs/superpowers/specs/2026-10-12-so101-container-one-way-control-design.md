# SO-101 容器采集的单向控制接口

日期：2026-10-12。状态：讨论结论已确认，书面设计待审阅。

## 目的与适用范围

Coordinator 负责调度，采集容器负责执行。两者之间只有 Coordinator 发起的调用，接口只有启动、发放任务、状态查询和终止。容器完成任务后将结果写到固定目录，Coordinator 查询确认完成，再从宿主机对应目录回收数据。

本设计替代容器采集方案中的 Worker 向 Coordinator 注册、领任务、ACK、心跳、提交和恢复回调。2026-09-30 设计及 2026-10-11 实施计划的原始批准快照保留；与本设计冲突的控制协议部分由本设计取代。后续书面实施计划需要更新，尚未开始这次协议改造。

用户已经确认两条语义：容器内输出路径固定，任务接口不传输出路径；失败仅指进程异常、超时等执行故障，抓取失败或数据质检未通过属于业务结果。

## 组件职责

Coordinator 持有任务队列、任务与容器的绑定、宿主机目录映射、执行期限以及数据校验和提交记录。它决定何时发任务和终止容器。所有调度判断留在宿主机。

采集容器同时执行一个完整场景任务。容器内部完成 reset、Teacher、Recorder、停止确认、bag 关闭、离线处理、QC 和结果封存，不向 Coordinator 请求执行许可或提交结果。任务完成后的下一次 reset 仍须满足原有停止和清理条件。

宿主机侧的容器适配器承接四个操作。启动和终止通过现有 Docker owner 执行；任务发放和运行中状态读取使用私有控制通道。容器退出后，适配器仍可返回此前记录的故障及实际退出状态。它不另起一套调度服务。

Head、Teacher 的共享推理服务继续按 campaign 生命周期运行。采集容器向它们发送推理请求，这些请求不属于容器与 Coordinator 的控制协议。

## 四个操作

| 操作 | 输入 | 返回与完成条件 |
| --- | --- | --- |
| `start` | 冻结的实例配置；宿主机输出目录映射由适配器处理 | 返回实例 ID。状态达到 `READY` 前，不接收任务；`READY` 需要原有 native readiness 证据。 |
| `assign_task` | 实例 ID、任务 ID、冻结的任务输入引用、执行期限 | 快速返回是否接受，不等待整项任务完成。每个实例最多一个正在执行的任务。 |
| `get_status` | 实例 ID；查询具体任务时带任务 ID | 返回实例状态、任务执行状态、简短故障原因及资源释放是否已确认。不返回数据内容或可变输出路径。 |
| `terminate` | 实例 ID、终止原因 | 单次清理流程，可重复调用。只有原有 owner、controller、辅助进程和容器退出证据齐全时，才确认资源释放。 |

业务接口不再提供注册、领任务、ACK、心跳、commit、recovery、resume 或 takeover 操作。控制通道保留实例身份、消息大小、期限和来源校验；这些是本地校验，不增加调度调用。

同一任务 ID 的重复发放只查询或返回原有接受记录，不再次执行。响应丢失时，Coordinator 查询该任务 ID，不自动重放。任务 ID 与输入绑定，输入变化或实例不匹配时拒绝请求。记录限于当前实例，不建立跨 campaign 的接管或已见任务历史协议。

## 固定输出目录与回收

采集容器内固定输出根为 `/act/output`。启动时，宿主机将当前实例专属的证据目录绑定到该位置。容器不接收、不选择宿主机输出路径；不同实例分别映射，不能写另一个实例或 Host journal。

每项任务写到 `/act/output/tasks/<task_id>/`，任务 ID 必须是受限的单个路径分量。每项任务使用新目录，已完成或失败任务的内容都不覆盖。固定输出根允许一个容器顺序执行多个任务，同时保留各自证据。

Coordinator 已知实例的宿主机目录和任务 ID，可直接定位任务结果。成功状态不携带任意路径。只有指定任务被查询为 `SUCCEEDED` 后，Coordinator 才进入结果回收和独立校验；不能通过目录扫描发现可提交任务。

结果文件继续区分 Teacher 结论与 data `VALID/INVALID`，并保留原有 hash、时间戳、bag、QC 和 seal 内容契约。路径适配限定在固定输出挂载与该实例宿主机目录之间；输入挂载保持原有约束，不迁移整个 artifact schema。需要跨进程引用的文件在写入边界形成可由 Host 解析的引用，不在回收时改写已封存内容。

`SUCCEEDED` 只在 Recorder 关闭、任务辅助进程和控制器完成原有停止确认、结果与清单完整落盘且 seal 完成后发布。Coordinator 独立校验成功后，写自己的提交记录，再发下一项任务。状态成功本身不证明数据可用于训练。

## 状态与失败语义

实例状态使用 `STARTING`、`READY`、`BUSY`、`STOPPING`、`TERMINATED`。故障原因与资源释放确认单独记录，不能用一项任务的执行成功表示整个容器已经退出。

任务执行状态使用 `ACCEPTED`、`RUNNING`、`SUCCEEDED`、`FAILED`。`SUCCEEDED` 表示执行流程正常结束且结果可回收，业务结果允许失败。例如抓取失败、Teacher 判定失败或正常 QC 得到 `INVALID`，都在结果中表达，不触发容器故障。

`FAILED` 表示进程异常、超时、服务或设备故障、数据处理异常，或无法满足执行完成条件。正常得到 QC `INVALID` 与 QC 进程崩溃分别属于业务结果和执行故障。

执行故障使实例停止接收新任务，并进入 `STOPPING`。实例一旦开始终止，不因迟到结果重新变为 `READY` 或可复用；终止前已确认并提交的原有结果保留。

## 终止与存活检查

容器检测到执行故障时，主动停止自己拥有的 Teacher 执行、Recorder、控制器目标及 native stack，然后退出；它不调用 Coordinator。宿主机查询发现故障、查询不可达或期限到达时，调用 `terminate` 确认和完成清理。必要的升级终止仍限定于登记过的实例及其资源。

状态查询承接原有 Host 存活检查：容器只根据收到的有效查询刷新本地存活期限，并自行检查任务期限。复用原有冻结的超时配置，不增加心跳接口，不降低停止阈值。Coordinator 崩溃后，旧实例因查询中断而自行停止；不得恢复或接管旧 campaign。Host 正常终止时，按原有 campaign ownership 清理共享服务。

资源释放范围是故障实例拥有的全部运行资源，包括辅助进程、控制器目标、native stack 和容器。单个采集实例的故障不直接终止仍被其他实例使用的共享 Head、Teacher 服务；共享服务本身故障按原有 campaign 故障规则处理。

无法证明停止时，`resources_released` 保持 false，不释放对应的槽位和 GPU 安全占用，也不启动替代实例。状态查询不可达本身不证明资源已经释放。正常轮询 `RUNNING` 时也不进行数据回收。

已落盘结果、日志和故障证据保留。释放运行资源不包含删除证据。无硬件、训练、push、证据删除、自动重试或阈值调整授权。用户已明确要求新版本实现后清理旧协议的源码与测试，该清理属于此次代码改造范围。

## 对当前代码和验收的影响

`worker_transport.py` 的容器到 Host RPC、`worker_runner.py` 的整批 Worker 调用以及 collection Worker 对 Coordinator proxy 的依赖，将由四操作适配器、容器本地任务执行器和 Host 轮询替代。现有未提交的 builder、launcher 和 native collection spec 草稿保留，实施时逐项协调，不覆盖或丢弃。

`coordinator.py` 保留宿主机调度与 journal 职责；`owner.py`、`shard_owner.py`、`registry.py`、`retirement.py` 的资源归属和实际停止证据继续使用。`paths.py` 增加固定输出目标的精确映射；`case_artifacts.py`、`result_verifier.py` 保持独立封存与 Host 校验职责。具体代码改动顺序由后续实施计划给出。

历史“terminal lease”验收对应到 Host 登记的实际终结任务，不再要求 Worker 回调。原有数量和业务门槛不变：same-eight W1/W2、独立四十场景分两轮 exact-W8、每实例每轮至少两个实际终结任务，以及已批准的 formal split、quota 和 committed manifest。业务失败仍计入原有业务分母，执行故障仍使 qualification 不通过。

## 旧协议清理

新协议实现并通过实际控制链与结果回收的定向验证后，在同一实施计划中移除旧协议专属源码和测试，再对清理后的最终代码运行集成与完整门禁。清理是交付条件，不另留后续任务，也不保留兼容入口、双协议开关或默认不可达的旧实现。

清理范围包括容器到 Coordinator 的 RPC transport/proxy、整批 Worker dispatch runner、容器注册/领任务/ACK/心跳/提交/恢复交互，以及旧描述文件、配置、socket/token 和 CLI 组装中的专属接线。新协议仍需要的采集、停止、封存和资源归属逻辑先迁移到新组件，再移除旧协议依赖。

当前明确的旧协议入口是 `worker_transport.py` 中的 `CollectionCoordinatorTransport`、`CollectionCoordinatorProxy`，以及 `worker_runner.py` 中的 `ContainerWorkerRunner`。`collection_worker.py`、`worker_builder.py`、`collection_driver.py` 和相关组装按实际引用逐项处理，不能只删除 transport 而遗留失效调用。

旧协议专属测试包括 `test/parallel_batch/test_container_coordinator_transport.py`、`test_container_worker_runner.py`、`test_container_collection_worker.py`，以及其他测试中仅验证旧回调与租约交互的部分。仍有效的任务业务、数据完整性、进程停止和隔离断言迁移到新协议测试，随后移除旧测试。验收数量、数据规则和停止条件保持不变。

通用 `parallel_ipc` authority 和非容器 `mujoco_batch` 目前仍有实际使用者，其源码与测试不属于整体删除对象。清理按用途和实际依赖确认边界，保留其他受支持流程使用的能力；容器采集路径必须完全脱离旧 Coordinator RPC。

清理完成的证据包括：新容器路径无旧协议 import、配置或运行时调用；移除专属旧测试后新测试覆盖对应有效业务断言；CLI、实际容器及独立 Host 数据回收链通过验证；最终包级门禁针对清理后的 source/image freeze 运行。历史批准快照、Git 历史、日志、数据与测试证据全部保留。

## 验证要求

定向测试必须覆盖以下边界：

- 只有四个操作；容器执行不需要 Host Coordinator socket、token 或反向 RPC。
- 容器固定输出目录、实例隔离、任务目录不覆盖；Host 从已登记映射回收指定任务。
- 发放快速返回、单任务并发限制、丢失响应后查询，以及重复任务 ID 不重复执行。
- Teacher 失败或 QC `INVALID` 仍可封存并返回 `SUCCEEDED`，实例可继续执行下一项任务。
- 进程异常、任务超时和状态查询中断触发全部自有运行资源清理；清理不确定时保持安全占用。
- bag 未关闭、结果未完整落盘或 seal 未完成时，不发布 `SUCCEEDED`。
- 容器退出后仍能从宿主机查询原始故障和退出证据；Host 校验失败不得提交结果。

真实集成验证使用当前实际容器、Teacher、Recorder、离线处理、QC、seal 和 Host commit 链。普通包级全量门禁仍在 source/image freeze 和必要的最终修复边界运行，采用原有 xdist 与 NVMe scratch 要求。新控制协议通过定向测试不等于完整 campaign qualification 通过。

## 自审与后续

自审检查已覆盖：四操作是否包含隐含第五接口；固定路径是否进入任务参数；业务失败是否误触发清理；结果完成与退出是否混用；共享服务是否被单实例清理波及；迟到响应是否恢复已终止实例；输出引用是否需要修改封存内容。文档明确了这些边界，没有调整业务或安全门槛。

本次只形成书面设计。书面设计审阅通过后，更新实施计划，并继续使用当前 worktree、分支和 Codex 执行方式进行 inline self review。原始批准快照、历史提交和全部证据保留。
