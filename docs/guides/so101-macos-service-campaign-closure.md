# macOS SO-101 服务化验证运行指南

这份指南给在 Mac mini 上跑 SO-101 仿真验证的人看。它讲清楚三件事：怎么选 profile、启动前需要什么、出问题后从哪里读证据。

状态先说清楚：离线 package gate 已通过；候选 live gate 只观察到部分结论（点位确实在真实执行，但完整 7 点 drain 还没跑完一轮）；安装版 production 的 fresh Chrome 验收没有运行。计划要求的 Sol/high 与 Astra/high 独立复核在本会话不可达，因此本文是执行 agent 写的草稿，不能当作已复核的最终文档。

## 三个 profile

macOS 只支持三组组合，别想着扩展：

| 场景 | schema | profile | worker_count | batch kind |
| --- | --- | --- | --- | --- |
| W2 first-pass | v4 | `MPS_W2_FIRST_PASS` | 2 | `FIRST_PASS` |
| W1 retry | v5 | `MPS_W1_FULL_RESTART_RETRY` | 1 | `FULL_RESTART_RETRY` |
| W1 first-pass | v6 | `MPS_W1_FIRST_PASS` | 1 | `FIRST_PASS` |

路由键是 `(schema_version, execution_profile, batch_kind, worker_count)`，三处各校验一次：服务 request、adapter、public entry。选择的点数不参与路由——一个点和二十个点都还是同一个 profile。N>2 在 macOS 上、adaptive 池、CPU fallback、Linux transport、以及 v4 声称 W1 这类交叉组合，都在 spawn 之前拒绝。安装版 YAML 在 `src/so101_demo_py/config/mujoco/` 下：v4 的 bytes 已冻结，v5/v6 只改了 `schema_version`、`worker_count` 和 `ros_domain_ids`。

## StartGuard 管什么

guard 很轻，只做启动保护，不是资格认证，也不是容量证明。

- campaign adapter 在创建任何 campaign 子进程之前跑一次 fresh check；
- 每个 Worker 在自己的 spawn intent 落盘之后、`Popen` 之前跑一次；
- 同一次 preflight 的结果不能跨 spawn epoch、Worker 或 retry 复用。缓存的是 composition，不是 verdict。

判定的三个结果要分清：RAM floor 和 MPS unified-memory headroom 不够是硬拒绝，不启动；CPU busy 超过阈值只是 WARN，照样启动一次。`start-guard.json` 只是审计副本，旧的 PASS 或 FAIL 文件都不能决定这次能不能启动。public W2 CLI 为了隔离 torch 会 `exec` 自己，准入结果通过本次进程自己创建的 inherited pipe 一次性交接，消费后关闭，不能从磁盘 verdict 恢复。

## 启动前的前置条件

- 运行时契约是固定的：`/opt/ros2_jazzy`、`/opt/ros2_jazzy/.venv/bin/python`、`/opt/data/so101/runtime/fork/current`、`/opt/data/so101/workspace/install`、`/opt/ros2_jazzy/dylib_farm/current`。环境变量不是必需的；`ROS_DOMAIN_ID` 可选，范围 0..232。
- 先跑 `scripts/so101-macos.zsh doctor --json`，期望 `status=PASS`。要看基础检查用 `doctor --base`。
- 一次执行必须有有效的 lease 和 execution context。candidate 运行用 `POST /expert-validation/candidate-contexts` 签发一次性 context，再用 `POST /expert-validation/campaigns/candidate-first-pass` 启动；production 走安装版服务的 lease 授权入口。两类 context 不能互换，也不能跨 batch、profile、worker_count、evidence root 重放。
- retry 只对准一个点，而且必须是上一批 terminal-clean 的真实业务 `FAILED`。`INFRA_FAILED`、`INDETERMINATE`、`INVALID`、`UNRUN` 都不行。准入在一个 SQLite 事务里完成：消费 command、验证结果和 lease、检查 fence 和 owner、写 retry binding 与 spawn intent。事务之后 spawn 失败会留下未确认的 intent 和 fence，command 不能重放。
- 模型权重是输入，不是仓库内容。用之前核对冻结 hash：yolo `f281d252…0781`，grounded manifest `b55bb601…ed05`。hash 不符就不要启动。

## 一次 campaign 怎么跑起来

```bash
scripts/so101-macos.zsh doctor --json
scripts/so101-macos.zsh launch so101_demo_py so101_mujoco_task_station.launch.py headless:=false sensor_rendering:=true include_teleop:=false
# candidate 路径：先签发 context，再启动 first-pass / retry
scripts/so101-macos.zsh run so101_teleop so101_unified_web_server
```

Worker 的 lease 决定它执行哪个点：每个 lease 只带一个点，写好自己的单点输入（`points_path`/`points_sha256`），执行完把结果提交回 durable queue 和 journal，再取下一个。W2 是两个 Worker 抢同一个队列；W1 是一个 Worker 顺序排空。判定的 PASS 要求每个 selected 点恰好有一条 committed result——一个点都没执行却报 PASS 的情况不会再出现。

## 证据读哪里

每次运行有自己的目录，关键文件是这些：

- `batch/journal/`：coordinator journal、`coordinator_epoch.json`、`committed-watermark.json`（watermark 覆盖的 frame 才算已提交）；
- `batch/selection-binding.json`：本次绑定选了哪些点，以及 catalog/config/closure 的 hash；
- `batch/*-lease-*.json` 与 `batch/*-result-*.json`：每个 Worker 每次 lease 的点、单点输入路径、attempt 结果；
- `batch/point-results/*.json`：按点汇总的业务结果；
- `batch/campaign-result.json`：终态判决、cleanup、inventory、per-slot 汇总；
- owner tree 记录在 `<evidence_root>/owner-tree/<campaign>/<batch>/`：`*.intent.json`、`*.confirmed.json`，回收后的 receipt 也在同一目录。

读证据时先看 watermark，再看 selection 与 lease 是否一一对应，最后看物理证据（sealed attempt manifest 里的文件逐个核 sha256 和大小）。cleanup 没完成就不要写结论。

## 出问题怎么收敛

- 进程或 adapter 被 `SIGKILL` 之后，先看 owner tree 里有没有未确认的 intent。身份不明确就不要猜 PID、不要盲杀，保留 fence。
- `operator_recovery --owner-tree-root <root>` 会按叶子到根回收：station、worker、broker/campaign、adapter。只有 hash 与 birth identity 都对得上才发信号。回收完 fsync receipt，提交 `CLEANUP_COMMITTED` 之后才解除 fence。
- 未解决的记录会写出 `RECOVERY_OWNER_TREE_UNRESOLVED generation <g>: ROLE: REASON`，同时 fence 保留。看到这条就不要继续启动。
- foreign 进程一律不动，只列出来。这个仓库里 `so101_measure_parallel_resources` 仍然是 retired 状态，macOS 也没有容量资格流程。

## 还没做完的部分

1. 候选 W2/W1 的完整 drain 与 v5 retry（需要一个真实业务 `FAILED` 点）还没跑完并留证；`CP-MSC-04` 因此没有通过。
2. 安装版 production + fresh Chrome 验收（Task 12）没有运行，需要的环境断言与 Playwright project 命令写在计划的 Task 12 Step 5。
3. `CP-MSC-02`、`CP-MSC-03`、Task 13 的 Sol/high 结果审查与 Astra/high 独立终审在本会话不可达，按计划只能报 PARTIAL，不能标 FINAL PASS。
