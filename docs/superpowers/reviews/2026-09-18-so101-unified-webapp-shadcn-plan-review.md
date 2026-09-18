# SO-101 单 Web 服务实施计划独立审查

- 日期：2026-09-18。
- 审查角色：GPT-6 Astra / High，独立于计划作者。
- 结论：`CHANGES_REQUIRED`。
- 计划对象：`docs/superpowers/plans/2026-09-18-so101-unified-webapp-shadcn-implementation.md`，933 行。
- 计划 SHA256：`d1fe79740faafa3494bb1b91e9c2dd5271e6cc79c1f06506ff5da56afc08eab4`。
- 已批准设计 SHA256：`4e11f3a385e8d078523ee3c3b3b11d2ec372215188cfbdabdea824c35dd54fa1`。
- 源码基线：`84620fc0529779a27c6985f8717d78f0386e0135`；源码读取根为 `/private/tmp/so101-doc-publication.R3yXD0aj/repo`，未把旧 `587b` 源码作为当前 main。
- 任务证据根：`/tmp/so101-debug-unified-webapp-design-20260918/`；审查者不写主账本。

## 范围与方法

已按行完整读取冻结计划全文、批准设计和 `implementation-plan-review-checklist.md`，复核实际 Python 类型/路由/ROS 导入链、Tasks artifact、SQLite store、Web 类型与地图 props、CMake、安装态 launcher/fixtures、Chrome 配置和缓存中固定版本 shadcn CLI 的参数定义。适用仓库规则与 `so101-dev` 技能及参考文件已在本审查任务中读取。

这是静态实施计划审查。未运行产品测试、构建、安装、ROS、仿真或远端命令，未修改 spec、plan、源码、预算文件或账本，未执行 commit/push。以下问题按该冻结版本的行号定位。

## 必须修订

### PR1 — [P1] 跨普通/安全 IPC 的 cancel 与实际 goal submission 尚无可执行的线性化协议

计划位置：第 225–227、256、326、374、382、421、486–496 行。

计划规定 `prepare_child` 在 Web store 提交 `DISPATCH_INTENT` 后返回 token，真正 send 在事务外；取消另外提交 `cancel_parent`，通过独立 safety socket 发往 child。第 421 行要求 child 检查“current cancel 状态”，但尚未定义这个状态如何跨两个 socket 传递、如何拒绝先 prepare 后迟到的包，或 child 的提交动作与取消 tombstone 由谁原子排序。现有 `DispatchToken` 没有撤销 revision，`BridgeClient.cancel` 和 `SafetyLane.cancel` 又都以 `ActionKey` 为目标；该 key 中的实际 goal identity 在 ACK 前尚未建立。只有“late ACK 后取消”不能代替未 ACK child 的撤销契约。

具体危险交错：Web prepare token → Web cancel parent → 安全消息先到 child，但 registry 尚无 goal → 原普通消息稍后到 child。若 child 只验证 token 的 epoch/generation/deadline，该命令仍可能提交；如果它同步查询 Web arbiter，则 Web 失联时的独立 watchdog 又没有定义好的本地决策依据。当前接口允许两种实现作出不同且不兼容的决定。

最小修订：给 pending child 增加可取消的稳定 identity，并定义 child 侧持久或进程生命周期内不可回退的 parent/child cancellation tombstone、撤销 revision，以及唯一负责排序“禁止提交/开始提交”的本地短临界区或等价状态机。明确取消何时算线性化成功：取消先胜出，迟到 token 必须拒绝；提交先胜出，必须按稳定 goal identity 跟踪 accepted 前后并取消，不能丢失 pending goal。安全请求必须能按 parent/child identity 撤销尚无 handle 的 intent；不能要求浏览器伪造实际 goal UUID，也不能让 child 打开第二个排他 IntentStore。Web 死亡时沿用 child 已知的精确 owned/pending 集合和 tombstone 取消，未知结果继续保留 Web durable fence。

验证要求：用真实两条 IPC 通道设置 barrier，覆盖 prepare 后未 send、普通包被阻塞但 cancel 已在 child 确认、submit 已开始但 ACK 未回、ACK 丢失、Web 已死亡等切点。检查真实 helper 的 goal submission 次数、pending registry、取消目标及 reservation，不只检查最终 projection 为 blocked。

### PR2 — [P1] 安装态 helper 替换层过高，且生产 Teleop 组合缺少明确实现落点

计划位置：第 429、505–509、534、738–740、812 行。

第 738 行把 `HelperTeleopPort` 定义为 HTTP/application 层的 `TeleopPort`，其方法包含 `command` 和 `execute_plan`；第 740 行又把它直接交给 `compose_installed_test_services`。这个 seam 可以替换掉生产 Teleop 命令解释、ParentSequencer、lease/admission 和 bridge 路径，仍让统一 router、instance 握手及 helper action 看起来通过。因此它不等于同段宣称的“只注入物理执行 port”。

生产组合本身也尚未落到具体类：基线 `P/service.py:3` 仅 re-export `server.TeleopService`，而 `server.py` 顶层导入 ROS。Task 6 只要求把 re-export 改成 `TYPE_CHECKING` 或 pure protocol，并定义 `TeleopPort`；Protocol 不是可运行的 Web service。计划没有明确把哪个纯生产 Teleop 实现移到哪个文件、如何把它接入 WorkerPort/BridgeClient，以及 `compose_services` 和安装测试如何复用该同一个构造器。实施者可能在测试 helper 内补齐行为，却让真正 entrypoint 保留空缺或另一套逻辑。

最小修订：明确拆出无 ROS 的生产 Teleop service/adapter 实现及其文件、构造接口和业务状态归属；它应消费生产 AdmissionGateway、LeaseBindingCoordinator、ParentSequencer 和 bridge/worker port。生产与 copied-install launcher 复用同一组合函数。L2 替换点下移到 WorkerPort 或 ROS/action transport，保留真实生产 command/parent/safety/IPC 代码；需要无 ROS helper 时只替换 child 最内层 action driver，不替换 Web application service。对应 Files、staging 和测试清单同步更新。

验证要求：在 source 与 copied install 下都证明 production Teleop service 的 module origin；安装测试使真实 `/plans/{id}/execute-all` 经过生产 parent sequencer、两条 IPC 和安全 lane，再观察 helper goal。若移除生产 parent reservation 或让 production cancel 回到普通 coordinator，L2 应失败；helper 自己实现了正确逻辑不能掩盖此回归。

### PR3 — [P2] “普通锁被占用”的取消测试没有连接到被测正常路径

计划位置：第 337–367、374–375 行。

测试在第 355 行创建全新的 `normal_lock` 并持有它，但没有把此锁交给 worker、service、coordinator 或 SafetyLane，也没有启动任何普通命令。第 360 行只能证明这个局部锁仍被测试自己持有。即使 production cancel 又错误进入一个普通 CommandCoordinator，测试里的那把锁也不会阻塞该 coordinator，因而不能发现首审指出的实际回归。

最小修订：保留这个测试作为 isolated lane delivery 单测时，删除它对“绕过普通执行锁”的证明性命名；另在真实普通 mutation 执行入口启动一个由 barrier 保持运行的 action，确认持有被生产使用的 coordinator/执行资源，再经真正的安全入口取消。这个整合测试可以放到 Task 5 或修订后的 Task 11，但必须列出文件、前置接口和确切 GREEN 命令；普通队列饱和同样要填充实际被生产使用的队列。

验证要求：先临时使安全入口依赖该正常路径而确认测试失败，再恢复独立安全路径通过。取消的实际目标必须是长命令登记的 arm/gripper goal，而不是另外注册的无关 goal。

### PR4 — [P2] Task 9 对 Task 10 的 qualification view 仍存在前向依赖

计划位置：第 49、655–657、697、701–703 行。

顺序明确为 Tasks 0–10 逐任务执行。Task 9 要让 `CampaignSetup` 消费 Task 10 的只读 qualification view，并在本 task 完成 `bun run build` 和完整前端测试；但 `web/src/api/qualification-view.ts` 的类型/实现及测试到 Task 10 才创建。按计划接入此模块会使 Task 9 在提交前缺少依赖；临时另写一套类型或恢复旧 K/capacity 判断又违背单一 view 和本 task 的最终行为要求。

最小修订：把纯前端 qualification view 类型、fail-closed 展示映射和 UNKNOWN fixture 提前到 Task 7/9，并调整 Files/staging；Task 10 再接真实 provider。或者把 Task 10 的接口部分明确排到 Task 9 前并修正依赖图。不得通过略过 Task 9 build、留 unresolved import 或临时启用未知 N 来完成任务。

验证要求：在 Task 9 完成时、Task 10 尚未执行的 checkout 上完整 build/前端测试通过，N2..8 未交付资格的默认行为均为 UNKNOWN/禁用，后续接入不要求重复创建类型。

### PR5 — [P2] Tasks artifact Protocol 与真实存储接口不一致

计划位置：第 509 行。

计划把 Tasks artifact 接口写为 `artifacts.resolve_opaque_id(id)`，但这个名字属于 Validation artifact 路径。基线 `P/api.py:216–225` 的 Tasks route 调用 `task_owner().artifacts.open(artifact_id)`，真实 `P/task_artifacts.py:200–211` 只定义 `open`，返回 `OpenedArtifact` 并验证登记路径、大小和 SHA256。该计划声明“保留现有接口”却给出了不存在的方法，按它实现 router 会破坏 Tasks evidence 下载，或者诱使实施者引入不必要的另一套 artifact authority。

最小修订：明确 `TasksArtifactPort.open(artifact_id: str) -> OpenedArtifact`；Validation 继续使用自己的 `resolve_opaque_id`。保持两者返回类型和原异常/404 行为，不合并权威索引或改写旧 manifest。

验证要求：统一 router 对真实 `ManifestArtifactStore` 注册的合法 artifact 返回原 bytes；修改文件后的 checksum mismatch、未知 ID、路径穿越均按原契约拒绝。测试不能使用仅实现计划里错误方法名的 fake。

### PR6 — [P2] gate 把 ai-station 专属 NVMe 规则错误扩大到全部 Linux

计划位置：第 83、90–94 行。

`run_gate` 用 `platform.system() == 'Linux'` 决定必须位于 `/data/work/so101-evidence/`。仓库规则明确将这一要求限定为 ai-station，并明确不应用于其他主机。Task 0 同时把该 helper 写成通用执行记录入口；此实现会拒绝另一台 Linux 上已经合法登记的 root，迫使执行者扩大证据位置或改 helper，和批准的 host-specific 约束不符。

最小修订：由 Task 0 的已核验执行主机/证据策略决定是否启用 ai-station NVMe 强制门控，不能用 OS 名称代替主机身份。仍对每次实际测试 Python 验证 TEMP，且该策略不能由任意测试命令自行覆盖；macOS 和其他主机使用其已登记 root。

验证要求：明确测试 ai-station 正确/错误 root、其他 Linux 合法 root 和 macOS 合法 root，以及 exact Python/TEMP mismatch 在所有主机均拒绝启动子命令。

## 其他检查结果

| 任务或边界 | 静态审查结果 |
| --- | --- |
| 授权、模型与证据 | dst TUI/tmux inline、Sol 监控、Astra 独审、planning/implementation 分任务根、Stage B/C 单独授权已明确；本次不扩大授权。 |
| 0：记录与测试环境 | 精确 Python、TEMP proof、elapsed/exit、每次唯一 scratch 和不删除已写入；需要 PR6 的主机条件修正。 |
| 1–2：持久 arbiter 与跨 store lease | BEGIN IMMEDIATE、command fingerprint、旧 intent fence、CLAIMING/RENEWING/HANDOFF 分层、独立双 store 故障切点和正常 renewal 不改变 execution generation 已明确，未把两个 SQLite 写成单事务。 |
| 3–5：执行与安全 | parent 跨 arm/gripper/home/workflow pause 保持占用，late ACK 不能丢 owner 的方向正确；PR1 和 PR3 阻止目前直接作为可执行安全验收。 |
| 6：路由与无 ROS | route 合并、旧 entrypoint 委托、same-origin/headers、单 schema、meta_path import 拒绝与 source/installed origin 检查有实际门控；需 PR2 的具体生产实现和 PR5 的真实接口。 |
| 7：前端状态 | 根 runtime、切页续约、memory-only proof、epoch/revision/gap、快照期间 buffer 和无重放已明确。示例 `CommandResult` 与当前 `api/types.ts` 的最小字段一致，不构成缺字段问题。 |
| 8：preset | 固定 CLI 4.21.0 的参数在缓存实现中存在；registry/dependency/font/license 哈希、真实 TW3 起点、必要 TW4 整套迁移与锁定、受控 preview smart merge已明确。实际 registry 兼容仍须实施前置 gate 证明。 |
| 9：真实地图与旧功能 | 示例符合当前 TopViewMap props 和 v1 fixture，明确 viewport-only 等比缩放、不重写历史、同半径状态、真实 5+1；需 PR4 的前置 view。 |
| 10：预算 | reviewed upstream 未交付时 UNKNOWN/阻塞，真实映射在测量前冻结，新 R 不复用旧资格，promotion 外部授权，未伪造当前 provider。 |
| 11：安装与构建 | CSS/components/config/fonts 依赖、真实 incremental 变化、CTest 新注册/实际 Python 和 copied-prefix 导入门控已明确；L2 seam 需按 PR2 下移。构建发布 prefix 时仍须完整依赖闭包，不能把只构建 Teleop 的 development prefix 当成包含 so101_demo 的完整复制产物。 |
| 12A 与 11 顺序 | 已明确 0–10 → 12A → 11，避免 CMake configure 注册不存在的 live fixture/launch 测试；发现的剩余前向依赖是 PR4。 |
| 12B/C：真实运行 | fresh R/binding/authorization、sequential dependency/R01、单服务、foreign owner 冲突、真实 Chrome 和独立物理证据要求明确；L2 或计划 PASS 不能替代它们。 |
| staging 与冻结 | 有限显式清单和 TW4 实际路径补充规则已写入；上述修订增加的文件也必须在对应 task 和 staging 清单同步。 |

## 复审与保留

修订 PR1–PR6 后冻结新计划 SHA，由独立复审报告绑定新对象；保留本首次计划审查，不覆盖。批准设计及已有设计审查结论没有被本报告改写。本轮仅新增此报告，已有任务 evidence root 继续 retained，没有新增运行批次、archived run 或 deletion candidate，没有删除证据。

计划复审通过后仍须用户批准实施，之后才能按所列阶段派发 dst；静态计划 PASS 不表示代码、安装、取消能力、任何 exact N 资格或 live 物理结果已经通过。
