# SO-101 单 Web 服务实施计划独立复审

- 日期：2026-09-18。
- 审查角色：GPT-6 Astra / High，独立于计划作者。
- 结论：`CHANGES_REQUIRED`；仅剩下述 PR2-R 的组合参数断点。
- 冻结计划：`docs/superpowers/plans/2026-09-18-so101-unified-webapp-shadcn-implementation.md`，1100 行。
- 计划 SHA256：`471785ae65b0a183b026627c6b9fcf88cb12a76cae175abc4b36dcc77eb45e28`。
- 已批准设计 SHA256：`4e11f3a385e8d078523ee3c3b3b11d2ec372215188cfbdabdea824c35dd54fa1`。
- 首审报告 SHA256：`f5bf485c0ce65030c5c14fb80fd78f66f5407323391c0bf2a78430598b3654d9`，保留不变。
- 源码基线：`84620fc0529779a27c6985f8717d78f0386e0135`；实际源码根 `/private/tmp/so101-doc-publication.R3yXD0aj/repo`。
- 任务唯一证据根：`/tmp/so101-debug-unified-webapp-design-20260918/`；审查者不写主账本。

## 范围与方法

完整读取新冻结计划 1–1100 行，对照已批准设计、首审 PR1–PR6、实施计划审查清单及真实基线接口。复核了双通道撤销、父操作、跨 store lease fencing、纯生产服务与安装组合、任务前置条件、Tasks artifact、host policy、CMake 注册和安装依赖闭包。适用 AGENTS、`so101-dev` 及其参考文件已在本审查任务中读取；本报告是审计记录，不是产品实现或教学文档。

仅静态审查。未运行产品测试、构建、安装、ROS、仿真或远端命令，未修改 spec、plan、源码、预算、账本或首审报告，未 commit/push。下文行号均属于上列冻结计划。

## 剩余必须修订

### PR2-R — [P2] 共享组合函数仍缺少 Validation 的现有 L2 execution port 透传

计划位置：第 509、887–889 行。

Teleop 的高层替换问题已修正：现在明确有纯 `ProductionTeleopService`，安装测试复用生产 parent/admission/lease/safety/IPC，只替换 child 最内层 `ActionDriver`。但是第 889 行的 `compose_installed_test_services` 仍接收既有 `execution_port`，随后必须调用第 509 行同一个 `compose_domain_services`；后者列出的完整签名没有 Validation execution port 参数，计划也未给出其他明确的透传渠道。

这不是可省略的旧参数。实际基线 `src/so101_teleop/test/e2e/installed_test_launcher.py:61–67` 把该对象显式传给 `create_production_service`。`P/expert_validation/production.py:1209–1235` 接收并继续传给 `ExpertValidationSupervisor`。省略后使用生产执行路径，而不是已有的 `HelperExecutionPort`。仅替换 Teleop `ActionDriver` 不会替换 Validation 的 coordinator/adaptive executor。因此按目前新签名组合，会丢失旧 Validation 安装态测试的 leaf seam，无法满足第 979 行“无实际 sim”的故障验收；由 launcher 另造一套 Validation service 又违反第 889 行共享生产组合的约束。

最小修订：只补齐这一条参数链。在 `compose_domain_services` 明列例如 `validation_execution_port: ExecutionPort | None = None`，并规定原样传给现有 `create_production_service(..., execution_port=validation_execution_port)`。真实 `compose_services` 固定使用生产默认值，不能从 HTTP、CLI 或环境选择 helper；仅 test-source launcher 将既有 `HelperExecutionPort` 沿 `compose_installed_test_services` 透传。澄清“唯一替换 ActionDriver”限于新增 Teleop 执行链，Validation 保留原有最底层 typed execution seam，两个域的业务服务、supervisor、owner、admission、lease 和 durable store 都不替换。同步 Task 6/11 的接口说明；不需要另建服务或改预算契约。

验收要求：source 与 copied-install 的统一 composition 测试同时走真实 Teleop execute-all 和真实 Validation start/cancel 路由。断言 Validation supervisor 收到的对象就是传入的 HelperExecutionPort，实际 owned helper argv/进程日志来自该 port；Teleop 仍经过生产服务与双 IPC 到 BarrierActionDriver。丢弃该参数的临时回归必须使 L2 失败；生产入口测试则证明其不接受 helper 选择且使用真实默认 port。保留各模块 copied-prefix origin 断言，不以 monkeypatch 高层 service 通过测试。

## 首审逐项复核

| 首审项 | 本次静态结论与依据 |
| --- | --- |
| PR1：cancel/dispatch 线性化 | 已闭环。239–241 定义 PendingChildKey、持久 revision、CancelIntent 和无 ACK target；425–452 定义 child 双 socket、本地短锁、不可回退 tombstone、预分配实际 UUID、pending ACK 回调及 web_dead latch。454–482 用真实双通道 barrier 和 leaf journal 检查零提交/恰一次、精确取消及未 terminal reservation；取消先胜与提交先胜已区分。 |
| PR2：生产实现和低层 seam | 主要修订成立。507–509 明确纯生产类、业务状态归属和共享构造器；887–889 保留真实 parent/admission/lease/safety/IPC/owner 及 copied origins。剩余问题仅为 PR2-R 的 Validation 参数链。 |
| PR3：真实 busy 资源取消 | 已闭环。351–385 不再拿孤立锁冒充生产绕锁证明；561–581 使用真实 ProductionHarness、正在运行的 HTTP parent、实际 coordinator lock、同一 goal 和真实 normal queue depth，并要求错误回归 RED。607 把整合测试实施与注册移到 factory 已存在的 Task 6。 |
| PR4：qualification view 前向依赖 | 已闭环。615–617 在 Task 6 提供实际 route 可达纯 schema；705–717 在 Task 7 提供生成类型 alias、UNKNOWN 和 workerOption；Task 9 build 明确在 Task 10 尚未执行时通过。806 的“Task10 view”可理解为最终数据来源，不改变已明确的前置接口顺序。 |
| PR5：Tasks artifact | 已闭环。611、615、619–646 使用真实 ManifestArtifactStore.open/OpenedArtifact，与 Validation resolver 分开；register_file 参数与基线一致，检查原 bytes/media type/SHA、修改后 404、unknown/越界请求。 |
| PR6：host-specific scratch | 已闭环。55、100–139 采用已登记且 hash/hostname/root 校验的 GatePolicy，不按 Linux 推断 ai-station；独立覆盖其他 Linux/macOS、错误 NVMe root 和所有 host 的 exact Python/TEMP mismatch。 |

## 完整计划的其他复核

- 任务顺序 0–10 → 12A → 11 → 外部资格与授权 → 12B/C 已明确；16 个新 Python 测试与 CMake discovery 清单、Files 和末尾有限 staging 清单对应。Task 4 的短 scoped-commit 描述仍沿用“两个测试”，但第 395 行和第 1063 行完整列出三个测试及 child runtime/helper，实际精确清单不会漏文件。
- 跨 store 仍采用 CLAIMING/RENEWING/HANDOFF 持久 fence，不宣称两个 SQLite 原子提交。正常 renewal 的域 fence、异步 parent guard、原 deadline 和不变 execution generation 已明确；安全取消不等 normal queue/renew event。
- Web 无 ROS 的生产实现、旧 service re-export、实际 import blocker、统一 router/health/OpenAPI、根 providers、memory-only proof、epoch/revision/snapshot 与不重放要求均有落点。Schema-only service 明确不能代替生产 L2。
- 官方 preset 固定版本、registry/font/license/hash、TW3 起点及必要 TW4 的受审闭包、完整前端 build/test、CSS/public/components/config 增量依赖仍保留；真实 registry 兼容性尚待实施门控证明。
- 地图仍以真实 manifest 几何等比显示，不更改投影与历史数据；状态同半径、多列结果、证据缺图、5+1 控制和原 backend 限制已列验收。
- 963–978 明确完整构建 so101_demo_py 与 so101_teleop dependency closure，再复制 non-symlink release prefix，记录 inventory/origins 与外部只读 underlay；未把 development Teleop-only prefix 误称完整产物。
- 预算 adapter 在上游未交付时保持 UNKNOWN；真实映射在 R 测量前冻结。新 R qualification、operator promotion、live 服务窗口、foreign-owner 冲突、真实硬件权限与物理成功声明仍分层，没有用计划或 L2 PASS 代替它们。

## 交接与保留

只新增本复审报告。首审及既有设计报告保持不变，现有任务根继续 retained；没有新增运行批次、archived run、deletion candidate 或删除操作。修订 PR2-R 后须重新冻结计划 SHA 并绑定复审结论；本结论不授权实施。

所有“闭环”均指静态计划已给出可审查的实现和验收要求，不代表任何实现、安装、运行取消、exact N 资源资格、Chrome 或 live 物理结果已通过。
