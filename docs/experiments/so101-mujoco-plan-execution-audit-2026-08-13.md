# SO-101 MuJoCo 计划执行审计（2026-08-13）

## 审计范围

本审计逐项核对以下两份计划，而不是依据计划文件中仍未勾选的 Markdown checkbox
推断完成度：

- `docs/superpowers/plans/2026-08-12-so101-mujoco-approved-policy-outcomes.md`
- `docs/superpowers/plans/2026-08-12-so101-mujoco-phase-aware-transport-evidence.md`

证据来源包括 Git 提交、生产代码和测试、
`docs/experiments/so101-mujoco-maintainability-remediation-experiment-ledger.md`、
五次 FULL_RESTART 的内容寻址原始证据，以及提交 `80e558b` 生成的只读基线汇总。

状态定义：

- `COMPLETE`：计划要求的实现与验收证据均存在。
- `COMPLETE_WITH_APPROVED_SUPERSESSION`：最终目标已达到，但中间步骤经用户授权后由后续方案替代，不能声称完全按原程序执行。
- `PARTIAL`：部分实现或实验已经完成，但原任务的完整验收条件没有满足。
- `NOT_EXECUTED`：没有找到该任务要求的终态产物或实验记录。

## 基线汇总

提交 `80e558b564d4445cc6ba01c7c5e53343ad0f80f9` 新增可复现、只读的五次
FULL_RESTART 基线：

- JSON：`docs/experiments/so101-mujoco-full-restart-baseline.json`
- SHA-256：`7e24e479dbed11292b7e95e95069a29a18e610298f5d9d655cbf64dad3f66368`
- 人类可读摘要：`docs/experiments/so101-mujoco-full-restart-baseline.md`
- 输入：`EXP-126` 至 `EXP-130` 的结果、owner manifest、九阶段 artifact、run-index、
  每个内容寻址的 500 Hz chunk 和 runtime fingerprint。
- 五次运行级动态运输峰值：最小值 `4.913286 N`、中位数 `4.925252 N`、
  最大值 `4.982987 N`。
- 18,575 个 500 Hz 样本的单接触力：p50 `4.094265 N`、p95 `6.197460 N`、
  p99 `6.575667 N`、最大值 `6.610767 N`。
- 五次运行的释放后静态峰值：最小值 `0.151060 N`、中位数 `0.233202 N`、
  最大值 `0.240023 N`。

该基线只用于下一批 RESET_WORLD 的同口径比较；它没有推导新阈值、修改已批准策略，
也没有把同一运行内的 500 Hz 重复测量误当成 18,575 次独立实验。

验证结果：Python 全量测试 `522 passed, 4 skipped`；Ruff lint/format 通过；
backend integration contract 通过；三个包 fresh build 通过；从 fresh install 执行 CLI
重新生成的 JSON 与仓库基线逐字节一致、SHA-256 相同。

## 计划一：Approved Policy and Outcomes

| Task | 状态 | 实现与证据 | 审计结论 |
| --- | --- | --- | --- |
| 1. 建立 remediation ledger | COMPLETE | `21994d3` 建立 ledger；后续 checkpoint 持续记录 provenance、实验状态和清理边界。 | 已完成。 |
| 2. typed `TaskPolicy` loader | COMPLETE | `120cefa` 实现 `task_policy.py`；`ddad25c` 记录 GREEN checkpoint；当前全量测试覆盖 loader。 | 已完成。 |
| 3. proposal/approval 分离 | COMPLETE | `b526f51` 实现 exact-hash approval；`contact_policy.py` 保留 hash、identity、fingerprint 的 fail-closed 校验。 | 已完成。 |
| 4. deterministic grasp evaluator | COMPLETE | `ad73015` 实现 `evaluate_grasp` 及 decision-matrix 测试。 | 已完成。 |
| 5. micro-lift 与 transport evaluator | COMPLETE | `f1666ce` 实现 `evaluate_micro_lift`、`evaluate_transport` 和因果窗口证据。 | 已完成。 |
| 6. final placement 与跨 backend policy parity | COMPLETE | `99801ba` 统一 outcome policy；当前 backend integration/frozen behavior gates 通过。原计划中的 Gazebo immutable gate 已被用户授权的 backend integration contract 正式替代。 | 功能目标完成；旧隔离约束已明确退役。 |
| 7. execute fail-closed、移除运行时阈值字面量 | COMPLETE | `d03e48f` 接入 approved policy preflight；阶段代码消费 typed policy；相关 mutation/focused/full tests 通过。 | 已完成。 |
| 8. 五种物理 regime 与 unilateral rejection | COMPLETE_WITH_APPROVED_SUPERSESSION | `EXP-101..105` 各 25 个样本形成 schema-v3 matrix；右侧 unilateral 有真实样本，左侧被证明在冻结几何下不可达并由 `1174d76` 编码为 fail-closed `physical_unreachable` contract；proposal hash 为 `670ffae8...de897`。 | 原计划的“左右各物理采样”未机械照做；经审查与用户批准，不能到达的左侧样本改为可验证的拒绝合同。五 regime 校准及单侧拒绝目标已完成。 |
| 9. exact user approval 与 policy activation | COMPLETE | ledger 保存用户对精确 hash 的批准；`9f34035` 通过 approval CLI 激活 schema-v3 policy；checked-in policy 的相同 hash 和身份仍可校验。 | 已完成，没有从架构批准推断阈值批准。 |
| 10. 自动门与一次物理 acceptance | COMPLETE_WITH_APPROVED_SUPERSESSION | 原 `EXP-109` 在运输时因把静态 `1.157900... N` 门用于动态阶段而 fail-closed；用户随后批准 phase-aware 证据方案。`EXP-125` 在不修改成功运动策略的前提下完成九阶段；`EXP-126..130` 又取得五次 FULL_RESTART 成功，最终自动门通过。 | 最终 acceptance 目标超过原要求，但不是按 Task 10 最初的静态/动态同阈值假设直接通过。 |

结论：计划一的十项最终目标均已实现；Task 8 和 Task 10 存在经用户批准、完整保留证据的
程序性替代。不能把这两项描述为逐字逐步执行了原计划，但不存在阻止下一阶段的未实现代码项。

## 计划二：Phase-Aware Transport Evidence

| Task | 状态 | 实现与证据 | 审计结论 |
| --- | --- | --- | --- |
| 1. 文档与 frozen manifest | COMPLETE | `b5c1c23` 固化设计、计划与行为 manifest；当前 manifest/hash gates 通过。 | 已完成。 |
| 2. preregister 实现和 `EXP-110..114` | COMPLETE | `5a0120a` 在 live action 前登记五个独立 FULL_RESTART ID 与停止规则。 | 已完成。 |
| 3. per-physics-step C++ 边界 | COMPLETE | `cb7381c` 增加每物理步 chunk/latch；后续 r6 fork `738e304` 修正到每 500 Hz physics step 采样，fork tag 已推送并通过 runtime probe。 | 已完成并经后续诊断加固。 |
| 4. typed raw recording、validity、analysis | COMPLETE | `3acb85c` 实现 `dynamic_transport_evidence.py`；后续 qualified NVMe evidence path 解决无损存储问题。基线重新验证所有 chunk/hash/连续性。 | 已完成。 |
| 5. phase-aware shadow 与 hazard cancellation | COMPLETE | `49020bb` 分离 static hard gate 与 dynamic shadow/hazard；`EXP-124` 验证无损运输，`EXP-125` 验证正确阶段分类。 | 已完成。 |
| 6. schema-v4 diagnostic-only proposal generator | COMPLETE | `3a4ce93` 实现 deterministic schema-v4 builder/validator，禁止动态 acceptance threshold 并保持 approval disabled。 | 生成器与测试已完成，但没有终态 proposal 文件；终态文件属于 Task 9。 |
| 7. sampling 前自动门 | COMPLETE | `b44234c` 记录原批次 gate；当前更强的 `522 passed, 4 skipped`、Ruff、fresh build/install、fork/runtime、frozen/backend gates 全部通过。 | 已完成。 |
| 8. 顺序执行 `EXP-110..114` | PARTIAL | `EXP-110` 启动后因 evidence session identity mismatch 被正确判为 `INVALID_EVIDENCE`；按预登记规则立即停止。`EXP-111..114` 永久未执行。之后 `EXP-126..130` 提供了五次独立、无损的 FULL_RESTART 动态证据，但它们不是原批次，不能重写历史。 | 原任务没有按原实验 ID 完成。功能所需五运行数据已由后续授权批次取得，可作为新的输入集合。 |
| 9. 生成两次一致的 disabled proposal 并停在 `USER_APPROVAL_REQUIRED` | NOT_EXECUTED | 仓库和登记的 evidence root 均没有原计划指定的 `contact-calibration-v4-proposal.yaml`；ledger 明确记录 EXP-110 批次中止时禁止生成 proposal。当前只存在生成器和本次 FULL_RESTART 基线。 | 这是该计划唯一仍需实际产生的终态工件。 |

结论：计划二的基础设施 Tasks 1–7 完成；原始 Task 8 批次按 fail-closed 合同中止，后续
`EXP-126..130` 已取得可替代的五运行原始证据；Task 9 尚未执行。因此，计划二不能标记为
“全部完成”。

## 尚未完成与下一步边界

1. 若仍需要完成 phase-aware 计划的 proposal 目标，应新增一个显式 checkpoint，声明用
   `EXP-126..130` 替代已永久关闭的 `EXP-110..114`，然后将五次 summary replay 两遍，
   生成 byte-identical、disabled、无 dynamic acceptance threshold 的 schema-v4 proposal，
   记录 exact SHA-256，并停在 `USER_APPROVAL_REQUIRED`。不得复用或重写 EXP-110..114。
2. schema-v4 proposal 是诊断产物，不能自动替换当前已批准 schema-v3 运行策略，也不能
   从本基线自动推出“显著漂移”阈值。
3. 整体 migration success contract 仍缺新的五次连续 RESET_WORLD challenge。五次
   FULL_RESTART 基线只作为对照，不能计入 RESET_WORLD 成功次数。
4. 本次审计没有启动仿真、没有 rebase/merge/push，也没有修改策略、阈值、MJCF、scene、
   controller 或已登记的历史实验结果。
