# SO-101 ACT 容器化采集 campaign 设计

日期：2026-09-30
状态：用户已确认方案边界；独立 Astra/High 设计审查通过，等待用户书面审阅。本文不授权实施、启动采集或执行真实 SO-101 动作。

关联文档：

- [双 RGB ACT 总体设计](2026-09-10-so101-act-head-wrist-rgb-design.md)
- [Task 8 live 与正式采集设计](2026-09-24-so101-act-task8-live-formal-collection-design.md)
- [Task 8 measurement protocol](2026-09-29-so101-act-task8-measurement-protocol-design.md)
- [ACT 实施计划](../plans/2026-09-11-so101-act-head-wrist-rgb-implementation.md)

本文定义下一版 ai-station 采集运行架构。与关联文档冲突的容器拓扑、教师模型选择、运行配置身份和故障恢复条款，待本文审阅通过后以本文为准；实施计划须先同步修订。当前代码和已保存证据不因本文自动改变状态。

## 1. 范围

目标是把每个 shard 的 Worker、MuJoCo、ROS、controller 和 Recorder 放入独立容器，并将 head 搜索 YOLO 与教师感知改为共享 IPC 服务。Host campaign owner 仍是唯一资源和调度所有者。仿真仅支持 MuJoCo，GPU 推理不回退到 CPU；容器方案不涉及真实机械臂。

本设计不重新定义 ACT 的 observation/action、Task 8 安全监督、10 Hz 因果采样、接触策略批准、数据集划分或训练算法。阈值效果变差时使用独立的阈值推算流程；推算工具不属于这次容器架构。

## 2. 运行拓扑与职责

~~~text
Host: UnifiedWorkloadService / campaign owner / Coordinator
  admission, physical GPU lease, journal, case lease, verify, commit, cleanup
  |
  +-- head-YOLO container (one per campaign)
  |     head RGB -> bounded IPC queue -> raw candidates
  |
  +-- teacher perception Broker container (one per campaign)
  |     campaign selects YOLO image OR Grounded-SAM image
  |     task_camera RGB -> bounded IPC queue -> canonical candidates
  |
  +-- wave: eight shard containers, w00...w07
        Worker + one MuJoCo/ROS stack + controller + private Recorder
        head search state machine and neck control remain here
        private evidence directory and input staging
~~~

两个推理服务都跨 wave 存活；shard 容器只服务所属 wave。YOLO 教师 campaign 有两个用途不同、队列独立的 YOLO 容器。Grounded-SAM 教师 campaign 有一个 head-YOLO 容器和一个 Grounded-SAM 教师容器。这里的 teacher perception Broker 不是现有控制链中的 CommandBroker；后者的动作授权边界不变。

每个 shard 独占 ROS Domain、namespace、MuJoCo session、controller、Recorder、临时目录和证据目录，并使用私有网络 namespace。Host 不启动第二套 ROS/MuJoCo stack，也不让容器取得 Docker socket、特权模式或 host network。Host 将 admission 选定的同一物理 GPU UUID 显式映射给两个推理容器和所有 shard；设备可见性不是 GPU 容量隔离，合计负载仍要监测。共享服务只处理请求、排队、推理、健康状态和响应关联，不读取 case lease、wave journal 或资源 binding。资源绑定只在统一启动入口核验；内部业务消息只检查其自身的身份、generation、时间戳和 schema。

## 3. 两类推理服务

### 3.1 教师感知 Broker

每个 campaign 从 YOLO 和 Grounded-SAM 两个独立 Docker image 中选择一个。两个 image 实现同一版本的请求/响应 contract；单个 case 不做 YOLO 到 Grounded-SAM 的自动回退。教师 Broker 使用所选模型现有的分数阈值，输出规范化的候选结构或明确失败。两个模型的原始分数不可横向比较，阈值各自保存。

模型 image digest、权重 hash、类别映射和教师阈值写入 campaign 配置及结果溯源。它们在 campaign 内不可变；下一 campaign 可另选 image 或使用新的运行期阈值。模型本身没有独立的 QUALIFIED 启动门禁，也不要求为 Grounded-SAM 再跑一套 W8 资格。仅切换教师 image、权重或教师分数阈值，不自动要求重做 Task 8L；机器人安全检查和逐 episode QC 不因此放宽。共享协议、Worker 安全逻辑或受控测量合同变化仍按原失效规则处理。

所选 image 在启动时加载配置的全部模型实例，全部可用后才能报告 ready。实例数是独立的 campaign 运营参数，仅下一 campaign 可调整；不预先测定每档容量。加载失败时 campaign 启动失败，零 wave 启动；不自动减少实例数或切换 image。队列容量、超时和判定规则不因这个运营参数例外而变成可在 campaign 内修改的配置。

### 3.2 共享 head-YOLO 服务

八个 shard 通过 IPC 使用同一个 head-YOLO 服务，不在 Worker 容器内各加载一份 YOLO。服务只返回类别、框、原始分数及源帧时间戳；它不控制 neck，也不判断搜索是否锁定。Worker 保留 HeadSearchController、连续稳定帧、面积、视区、新鲜度和 min_confidence 等检查。Task 8 measurement protocol 所要求的原始 head RGB 与 detector candidate 仍须留证。迟到、跨 attempt 或跨 reset epoch 的结果由 Worker 拒绝；Recorder 的 10 Hz 写入不等待 head 推理。

head 模型、head 视角配置及搜索阈值沿用 Task 8 测量和安全合同，不能与教师模型的分数阈值混为一谈。head-YOLO 的模型实例/执行线程数单列为 campaign 启动参数，只能在下一 campaign 调整。两个共享服务的 GPU、CPU、RAM 和队列负载合并进入 campaign 资源监测。

### 3.3 IPC 与接口验收

两类服务各有独立的短 Unix socket 和有界队列。Host 在服务启动前创建 campaign 级 staging root，并固定只读挂载到两服务的 /act/inputs；后续 wave 在这个已挂载的 root 下增加私有目录，不重建服务。每个 shard 只把本 wave/shard/generation 的子目录读写挂载到固定 /act/inputs。Host 向 shard 提供形如 r/{wave}/wNN/g{generation} 的逻辑前缀，不提供 Host 绝对路径。Worker 把每个请求的完整图像写到不可复用的 request-ID 文件，原子发布后不再修改；请求只传逻辑前缀下的相对路径、大小、SHA256、源时间戳、请求 ID 和语义类别 ID。服务拒绝越界路径、符号链接、大小/hash 不符、未知类别和不合法请求；它从同一打开的文件内容完成 hash 校验与解码，不能在校验后重新按路径读取。

request ID 在整个 campaign 中唯一，不因 wave 更换或 shard ID 重建而复用。Worker 端保存不可变映射：request ID 对应 campaign、wave/batch、worker、worker generation、scenario、attempt、terminal lease generation、reset epoch、request sequence、源帧时间戳与图像 hash。服务只回显 request ID 和源帧身份，不理解这些业务字段。Worker 消费 head 或教师响应时，必须拿该映射核对当前有效 lease、attempt、reset epoch、帧身份和请求序号；重复 ID、超时后的迟到响应、跨 wave 或旧 generation 的响应都不能进入搜索/教师结果。模型专用提示词和类别号只在各 image 的受控映射中出现。

两个教师 image 和 head 服务必须通过离线 IPC contract、坏输入、队列满、超时、重复 ID、跨 wave/旧 generation 迟到响应及 ready/health 测试。这是接口一致性检查，不是模型效果资格或容量预测。客户端超时或 shard 容器退出不授权覆盖、复用或立即删除旧输入：共享服务可能仍有在途请求。staging 不是 episode 的权威副本；测量协议需要的原始帧由独立证据记录。staging 树在反读后列为删除候选，未经用户授权不删除。

## 4. Campaign 启停与 wave 生命周期

统一入口先完成 MuJoCo-only、policy activation、manifest/config hash、物理 GPU UUID、持久 lease、cleanup fence 和证据根 admission。Host owner 持有并续租资源；任何内部容器都不重新做 campaign 资源绑定校验。

正常启动顺序为：

~~~text
ADMITTED -> HEAD_READY -> TEACHER_READY -> SHARDS_READY
         -> WAVE_RUNNING -> WAVE_TERMINAL -> SHARDS_CLEANED
         -> next wave or CAMPAIGN_CLOSED
~~~

HEAD_READY 和 TEACHER_READY 要求配置的全部模型实例加载成功、IPC 可服务、image/model/config 身份与 campaign 记录一致。每个 shard 的 SHARDS_READY 不能只凭容器 PID：MuJoCo 场景、ROS/controller、七关节反馈、head/wrist 新鲜 RGB、Recorder 目录、两个 IPC 端点和 GPU EGL 都须可用，且 controller 没有未知活跃 goal。READY 不执行 case 动作，不替代逐 case 检查。正式 W8 的八个 shard 全部 ready 后才发 terminal lease。

一个 shard 容器在本 wave 内依次处理多个 case，每个 attempt 只做一次场景 reset。case 成功、业务失败或可明确归属的基础设施失败都记录各自终态；基础设施失败不能伪装成已 seal 的业务 FAILED。单个 case 失败不撤销整个 wave；数据是否进入训练集由后续 commit/QC/manifest 流程决定。wave 所有 case 终态后，Host 等待已 seal 结果的 Recorder flush、verifier/commit、controller 停止和旧 shard 容器、Domain、socket、GPU 占用清理收敛，才开始下一 wave。两个推理容器保持运行，不在 wave 边界做 wave-aware drain 或重新加载模型。

## 5. 故障与恢复

| 事件 | 处理 |
| --- | --- |
| 模型未检出、确定性模型错误、单请求排队溢出或超时 | 返回该请求的结果；上游记录对应 case 失败或基础设施结果，继续处理其他 case。持续资源越界另按 campaign 停点处理。 |
| head-YOLO 或教师 Broker 整体失效 | 停止发新 lease，停止当前 campaign，保留证据并等待人工处理；不自动切换模型或缩容。 |
| 正式采集中一个 shard 退出 | 已开始的 case 记基础设施失败并保留部分证据，不伪造业务 FAILED 或训练 episode；未开始的 lease 收回再分配。其余 shard 可完成当前 wave。下一 wave 前必须恢复八个 ready shard；新容器用新 generation，不继承旧 lease。 |
| W8 资格中任一 shard 退出 | 本次资格失败；不能按 W7 继续或拼接残缺结果。 |
| CPU/GPU/RAM、磁盘、MuJoCo RTF、Recorder 队列、10 Hz 连续性或 QC 出现规定的资源瓶颈 | 停止并等待人工决策；不自动降 Worker、实例数、画质或采样率。 |
| Host owner 在正式采集中退出 | 新 owner 先取得独占恢复权，fence 旧 shard/goal/lease，核对 journal 和已提交结果。只可接管身份、配置、健康状态均可核实的原 head-YOLO 与原教师 Broker 容器；旧客户端隔离后还要确认两服务的本地队列及在途请求已清空，不能把旧请求交给新 generation。已 commit 的 case 不重做，执行中的记基础设施失败，未开始的重新分配。任一共享服务已退出、无法证明空闲或旧资源无法确认清理，则结束旧 campaign。 |
| Host owner 在 W8 资格中退出 | 资格失败，不在原资格 ID 下续跑。人工决定重测时从新资格记录完整运行 40 场景。 |

正式采集中的业务 FAILED 在本 campaign 内不重排、不重试，也不以新 attempt ID 再次进入冻结候选。以后若确需重采同一场景，须由人工决定并建立新的 campaign、manifest 和数据身份；新 attempt ID 与原失败结果分别留证，不能覆盖或改写原 campaign 的成功率分母。基础设施恢复只处理原协议允许的未提交位置，不能覆盖旧终态。所有恢复都使用 generation-scoped、single-flight cleanup；未知 live owner、迟到 seal 或无法确认停止的 controller goal 会阻止继续。

## 6. 挂载、证据与训练边界

Host 为每个 wave/wNN 在唯一登记的 durable evidence root 下创建独占目录，只把本 shard 的目录读写挂载到固定容器路径 /act/evidence。冻结配置以只读方式挂载到 /act/config；campaign 级输入 staging root、IPC 和临时目录也分别映射到固定容器路径。容器内不保存或解析 Host 外部绝对路径，不读取其他 shard 的证据，也不写 campaign 中心 journal。两个推理服务在启动时只读挂载整个 campaign 的输入 staging root 和所需模型；除自身 socket/日志外不写 episode。Host 保存从 wave/shard 相对路径到 durable root 的映射。

Worker 在私有目录直接写原始 RGB、状态、controller reference、事件、QC 和 provenance；完成后写闭合 manifest 与逐文件 hash，原子 seal 并 fsync 文件和父目录。Host Coordinator 对登记 workspace 执行 verifier，只有合法结果才能写 result commit、wave journal 和 campaign index。容器退出时不再复制一份 episode。部分文件、只有 seal 没有 commit、迟到结果、资格或 surplus 均保留审计，但不能进入训练 manifest。Task 12 继续从 campaign index 回放 commit 与 receipt，不扫描目录推断训练数据。

唯一 evidence root 不移动、不删除。ai-station 上需要 fsync-heavy pytest 时，仍须在登记 root 下使用全新的 NVMe scratch，先核对 TMPDIR/TMP/TEMP 与实际测试 Python 的 tempfile 解析，再运行测试；scratch 经反读后只列为删除候选。

## 7. 配置身份与原计划修订

配置按作用分开记录，不能因为参数出现在同一 YAML 文件里就把它们视为相同门禁：

| 配置类别 | 例子 | 变化后的处理 |
| --- | --- | --- |
| 安全与采样合同 | contact policy fingerprint、head 搜索锁定阈值、双 RGB/10 Hz、controller、Task 8 measurement、MuJoCo source/adapter | 按现有受控变更规则使旧 Task 8L/bundle/live/QUALIFIED 对新身份失效；使用新 run subroot 重做。 |
| 教师模型运行与溯源 | YOLO 或 Grounded-SAM image、模型权重/类别映射、各自分数阈值 | 每 campaign 固定并记录；不增设模型 QUALIFIED，不因这些选择本身自动重做 Task 8L 或逐模型 W8。 |
| 推理服务运营参数 | head-YOLO 与教师服务各自的模型实例/执行线程数 | 仅下一 campaign 启动时调整并记录；不预先测试每个数值的容量，不撤销既有 Task 8L/W8。 |
| W8 门禁配置 | exact worker count、20 项 wave、40 场景清单、资源/QC 阈值、cleanup 和终态覆盖 | 资格运行前冻结，运行中不改；W2 后直接跑 YOLO 教师的独立 exact-W8，不测试 W4/W6。 |

旧实施计划把完整 runtime config 绑定到 Task 8L、W8 和正式采集恢复。实施前须拆出上述身份：教师模型/阈值和执行器数量的 campaign 记录不能通过 runtime_config_sha256 间接成为模型 QUALIFIED 门禁；同一 campaign 的配置与 evidence hash 仍不可变，恢复不得换模型或改参数。容器拓扑、head 检测 IPC、Worker/安全路径和测量协议的受控源码变化则必须用新 run subroot 重做 Task 8L。旧资格不能冒充新拓扑资格。

## 8. 迁移验收顺序

1. 离线验证两种教师 image 与共享 head-YOLO 的 IPC contract、坏输入和故障路径；验证镜像 digest、模型 hash 和固定挂载权限。
2. 在新 run subroot 重做受容器化及 head 检测 IPC 影响的 Task 8L/Task 8 live。旧 evidence 保留，但不拼接新旧 bundle。
3. W1 真实容器链路证明 ROS/DDS、MuJoCo EGL、controller、双 RGB、head 搜索 IPC、教师 IPC、Recorder 10 Hz 和 seal/verifier/commit；再以完整八场景 W1/W2 验证功能等价和隔离。
4. W2 通过后，以 YOLO 教师 Broker 运行一份独立 40 场景、两个完整 20 项 wave 的 exact-W8。每 wave 每个 Worker 至少完成两个实际 terminal lease，满足冻结的资源、吞吐、物理成功率和 QC 门槛；不得插入 W4/W6 或自动降档。
5. 正式采集可以在下一 campaign 选择 YOLO 或 Grounded-SAM 教师 image，不另做 Grounded-SAM W8 模型资格。每个 campaign 仍须 exact W8 启动、逐条 QC、持续资源监测和完整证据提交。资源瓶颈立即停下等待人工决策。

全量 package/xdist 测试只在计划规定的集成边界运行；定向 RED/GREEN 与测试 scratch、退出码和耗时照项目门禁记录。本设计的审查或文档通过不等于 Task 8 live、正式采集、训练或真实硬件已完成。
