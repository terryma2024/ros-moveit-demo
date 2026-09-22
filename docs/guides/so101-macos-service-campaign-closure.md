# macOS SO-101 服务化验证运行指南

这份指南给在 Mac mini 上跑 SO-101 仿真验证的人看。它讲清楚三件事：怎么选 profile、启动前需要什么、出问题后从哪里读证据。

状态截至 2026-09-22 晚：离线 package gate 在 `186ce876` 重跑过，失败数与上一次完全一样（demo 181、teleop 27，都是这台机器上的既有失败），web 的 tsc/vitest/build 全过，copied install 全过。候选 W2/W1/retry 通过；安装版 production 的 W2、W1 和 v5 retry 都在 fresh Chrome 里跑通并留证（`CP-MSC-T12-W2W1-PASS`、`CP-MSC-T12-RETRY-PROVEN`）。浏览器验收（Task 12 Step 5）现在每条 console 用例都在自己的服务窗口里跑绿（这种跑法操作员已认可），二十点最终验收也过了（`CP-MSC-T12-LIVE-SPEC-CORRECTIONS`、`CP-MSC-T12-ACCEPTANCE-20`）；过程中两处用例前提被产品否掉，已换成可测的等价写法，见下文“已知限制”。Sol/high 与 Astra/high 的独立复核在本会话不可达（`gpt-6-astra` 根本不在本机挂载的模型目录里），所以本文是执行 agent 写的草稿，`CP-MSC-FINAL` 按计划只能报 PARTIAL。

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
- 点位 catalog 的摘要被写死在产品里（`expert_validation/catalog.py` 和 `cli/mujoco_parallel_batch.py` 各一处），服务还会拿 manifest 的输入摘要再对一次。想用自己改过的 catalog 走 `SO101_VALIDATION_POINTS` 是走不通的，两个加载器都会报 `POINT_CATALOG_HASH_MISMATCH`，服务侧还会报 `VALIDATION_MANIFEST_CATALOG_MISMATCH`。要制造真实失败，只能挑本来就过不了的点位，或者用外部手段让某次 attempt 自己失败。

## 一个服务同时只服务一个控制台

排他控制器绑在 console 实例上。`claim_locked`（`so101_teleop/unified/instances.py`）只允许同一个 instance id 再次取得绑定，换一个实例一律 409 `CONTROLLER_ALREADY_BOUND`；释放 lease 不会解除绑定；`abandon_controller` 只在代码里，没有 HTTP 路由；`handoff` 要求当前实例和接手实例都活着。实际后果：

- campaign 跑到一半 reload 页面，新文档就是新实例，续租会被拒，lease 过期之后服务把这次 campaign 取消掉。跑 campaign 的时候不要 reload。
- 换个浏览器、换个 profile，或者上一个页面已经关了，都拿不回控制器。要接着跑，就重启服务。
- 需要连跑几个用例，就一个用例开一个服务窗口：起服务、跑一个用例、按 PID 停掉、读残留。macOS 的浏览器验收就是这么跑的（`CP-MSC-T12-LIVE-SPEC-CORRECTIONS`）。

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
- foreign 进程一律不动，只列出来：不猜 PID、不发信号、不清它的 socket 或 IPC 目录。

## 已知限制

- macOS 没有容量资格流程，`so101_measure_parallel_resources` 仍然是 retired。StartGuard 只管启动，不做资格认证，也不出容量证明。
- retry 保证的是流程：一个点、一次 lease、一次执行、一次提交，first-pass 的字节不变。它不保证失败点重跑就能通过；一条命令也只重试一个点，retry 的 retry 不支持。
- Linux/fixed 布局和 macOS composed 布局的证据形状不一样。前者把每次 attempt 的 artifact 注册到 projection，后者按点提交 `point-results/<point>.json`。读证据时按布局走各自的路，别拿另一边的路径去套。
- `CP-MSC-FINAL` 要求 Sol/high 的结果审查和 Astra/high 的独立终审，这两条在本会话不可达，所以只能报 PARTIAL。本文也停在这个状态。
