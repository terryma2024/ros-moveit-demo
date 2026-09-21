# SO-101 macOS service campaign 闭环设计

日期：2026-09-21
状态：按用户批准的 W1/W2 轻量资源保护边界修订，待独立复审
文档修订基线：`codex/so101-unified-webapp`，`90385e3fb4aa748788c5d8a4b4551ee307db4987`
执行恢复锚点：本地提交 `fea8f57c`、`e264d1eb`、`82b7a7d9`

## 1. 当前事实

统一 Web 服务已经能够持有 macOS MPS W2 campaign，control protocol、lease 续约、取消和
进程组清理也已接通。现有执行 checkpoint 记录了以下事实：

- Task 0–2 已完成并形成上述三个本地提交；当前 `dst` 已停止，不应重跑或覆盖这些提交。
- task-owned full station 曾达到 READY：三个 controller 为 `active`，三个 MoveIt service 和
  三个 action 均可用。
- 旧卡死只在不完整 dylib closure 中复现，错误是
  `@rpath/libmujoco.3.4.0.dylib` 无法加载。task-owned plugin 当前依赖
  `DYLD_LIBRARY_PATH` 才能闭合 MuJoCo vendor dylib。
- foreign modified fork overlay 没有重跑。因此 C++ controller 根因仍是 `UNCONFIRMED`，现有
  checkpoint 不是 Gate A PASS，也没有理由修改 controller 初始化代码。
- 五次连续 `FULL_RESTART` readiness 尚未执行。

执行侧还缺三条闭环：Web selection 没有可靠地驱动全部被选点；macOS campaign 没有服务
投影所需的标准 journal；W1 first-pass 和单点 retry 没有封闭的 typed profile 与执行入口。

本次修订删除 macOS 资源预算、资格化和 promotion 方案。macOS 固定只支持 W1 与 W2；单独
运行 W2 的资源视为足够。资源安全只使用已经存在的轻量 `StartGuard`，不再建立容量证明。

## 2. 目标

- 在 frozen copied install 中闭合 MuJoCo vendor dylib provenance，并完成五次连续
  `FULL_RESTART` station readiness。
- 保留 schema v4 的 macOS MPS W2 first-pass 合同；新增 schema v5 的 W1 单点
  `FULL_RESTART_RETRY` 和 schema v6 的 W1 ordinary first-pass 合同。
- macOS Web 和服务端只接受 `worker_count=1` 或 `worker_count=2`。N>2 在页面上不可用，API
  和 adapter 都必须拒绝；不得根据点数推断 profile。
- 让 Web 生成的全部 selected points 进入共享队列；每个 Worker lease 只执行一个绑定点位。
- 使用现有 `CoordinatorJournal`、durable committed watermark 和唯一 canonical reducer，建立
  crash-safe Web projection。
- 在每个 campaign spawn epoch 和每个 Worker spawn epoch 运行 fresh `StartGuard`。
- 持久化 adapter、campaign、worker、station、broker 的真实 owner tree，闭合 cancel、timeout、
  crash、fence 和 cleanup。
- 用候选执行授权与生产执行授权隔离 live 验证；retry 仍要求真实业务 `FAILED`、原 batch
  terminal-clean、一次性 command/lease 和防 replay。
- 完成 fresh Chrome 的 W2 first-pass、W1 first-pass 和单点 retry 验收。

## 3. 非目标和声明边界

- 不建立 macOS measurement CLI、运行期 sampler、native memory-pressure helper、watchdog、
  calibration、exact-N qualification、budget provider、deployment carrier 或 promotion 流程。
- `so101_measure_parallel_resources` 继续 retired/fail closed；本任务不创建替代入口。
- 不修改 2026-09-18 的旧资源预算设计或计划。它们是历史文档，不属于本任务。
- 不改变 Linux/CUDA schema v2/v3 或 adaptive 语义。
- 不把 schema v4 放宽成通用 worker-count 配置。
- 不把轻量启动检查描述成 `resource qualified`、`capacity certified` 或吞吐容量结论。
- 不让 React 读取原始日志、worker 文件或 `campaign-result.json` 重建状态。
- 不自动操作真实机械臂，不删除证据，不停止 foreign 进程，不自动 push 或 merge。

## 4. 总体架构

```text
Unified Web API
  -> macOS support matrix: W1 | W2 only
  -> ExpertValidationSupervisor
      -> CandidateExecutionContext | ProductionExecutionContext
      -> execution profile
          -> schema v4: MPS_W2_FIRST_PASS
          -> schema v5: MPS_W1_FULL_RESTART_RETRY
          -> schema v6: MPS_W1_FIRST_PASS
      -> fresh StartGuard at campaign spawn epoch
      -> ExecutionProcessOwner
          -> fresh StartGuard at every Worker spawn epoch
      -> CoordinatorJournal committed prefix
      -> canonical reducer + transactional store projection
  -> REST / WebSocket
  -> React UI
```

平台差异止于 support matrix、typed profile、runner 和 projection source。canonical reducer
之后不出现 macOS 专用状态机。

## 5. Runtime closure 与 Gate A

### 5.1 三层身份

运行闭包继续分为三层：

- `RuntimeClosureIdentity`：source commit、submodule commit、copied install 相对文件 SHA256、
  executable/dylib/plugin XML 来源、版本、净化环境约束，以及 robot/controller/model/launch hash。
- `RunBinding`：campaign、batch、fresh `ROS_DOMAIN_ID`、station session、evidence root、owner
  generation 和启动时间。
- `RuntimeAttestation`：实际 PID/birth identity、加载 image/dylib、ROS domain 和前两层 hash。

五次重启使用相同 closure identity，但每轮 binding 与 attestation 不同。READY 前必须验证实际
加载来源；source tree、README 或单独的环境变量不构成 closure 证明。

### 5.2 install/rpath 判定

现有证据首先指向 install closure，而不是 controller C++。Gate A 的下一步固定为：

1. 在净化环境中从 copied install 启动，保存 `otool -L`、`otool -l`、plugin XML、vendor
   dylib 路径和进程 loaded-image readback。
2. A/B 的唯一变量是是否注入 task-owned `DYLD_LIBRARY_PATH`。两轮使用相同 bytes、config、
   ROS domain policy 和启动命令。
3. 若只有注入环境的一轮 READY，且失败轮首坏边界仍是 `libmujoco.3.4.0.dylib` 解析，根因
   定义为 copied-install runtime lookup closure 缺失。
4. 修复只允许落在
   `third_party/mujoco_ros2_control/mujoco_ros2_control/CMakeLists.txt` 的 macOS install-rpath
   设置，并补 copied-install 回归。目标是让 plugin 从自身 install prefix 解析
   `../opt/mujoco_vendor/lib`，不写死机器路径。
5. 若 A/B 不满足上述判据，保持 `UNCONFIRMED` 并停止。不得转而修改
   `mujoco_ros2_control_node.cpp`、dispatcher 或 hardware interface。

### 5.3 Readiness

`motion_stack_ready` 继续 fail closed。每轮必须同时满足：

- 直连 `/controller_manager/list_controllers` 成功；
- `joint_state_broadcaster`、`arm_controller`、`gripper_controller` 都是 `active`；
- 三个 MoveIt service 与三个 action 可用；
- controller、MoveIt 和 attestation 属于同一 `ROS_DOMAIN_ID` 与 copied install；
- 退出后 task-owned station、ROS、IPC residue 为零。

连续五次 VALID `FULL_RESTART` 才通过 Gate A。VALID 失败中断连续序列；INVALID 结束本批次，
以新实验 ID 重开。既有一次 READY 只证明路径可行，不计作这五次。

## 6. macOS W1/W2 支持矩阵

| 场景 | Schema | Profile | worker_count | Batch kind |
| --- | --- | --- | --- | --- |
| W2 first-pass | v4 | `MPS_W2_FIRST_PASS` | 2 | `FIRST_PASS` |
| W1 retry | v5 | `MPS_W1_FULL_RESTART_RETRY` | 1 | `FULL_RESTART_RETRY` |
| W1 first-pass | v6 | `MPS_W1_FIRST_PASS` | 1 | `FIRST_PASS` |

v4 的现有 bytes 与 Darwin/MPS/CGL exact-W2 含义保持不变。v5/v6 复用相同的 MPS broker、
station owner、control endpoint、hard timeout 和 cleanup primitive，但只创建一个 slot、一个
Worker 和一个 ROS domain。

路由键是 `(schema_version, execution_profile, batch_kind, worker_count)`。服务 request、adapter
和 public entry 各自验证一次。以下请求一律在 spawn 前拒绝：N>2、v4/W1、v5 first-pass、
v6 retry、adaptive、CPU fallback、Linux transport，以及从 selected-point count 猜 profile。

Capabilities 在 macOS 只返回 fixed W1/W2：W1 用 `SEQUENTIAL`，W2 用 `PARALLEL`。N>2 可保留
为不可选展示项，但状态固定为 `UNSUPPORTED_ON_MACOS`，不得带 profile/qualification hash。

## 7. 轻量 StartGuard

本任务复用 `parallel_batch.start_guard`、`start_guard_probe` 和
`accelerator_probe.DarwinMpsAcceleratorProbe`，不新增第二套资源探针。

每次检查绑定 `(batch_id, epoch, owner_pid, owner_birth, MPS:default, worker_count)`：

- campaign adapter 在任何 campaign 子进程创建前运行 fresh check；
- 每个 Worker 在自己的 spawn intent 已持久化、但 `Popen` 尚未发生时运行 fresh check；
- 同一次 preflight 结果不能跨 spawn epoch、Worker 或 retry 重用。

所有 public/service entry 都服从同一规则。`start-guard.json` 只保存审计副本，既有文件无论是
PASS、FAIL 还是旧 epoch，都不能跳过 fresh probe。public W2 CLI 为隔离 MPS probe 对 `torch`
的导入，可在 guard 阶段后 `exec` 自身；跨 `exec` 的准入结果必须通过本次进程创建的 inherited
pipe 一次性交接，并校验 scope、owner birth、epoch 和有效期，不能从磁盘 verdict 恢复。

判定沿用现有语义：

- RAM floor 是 hard refuse；
- MPS unified-memory headroom 是 hard refuse；它是 proxy，不是独立 VRAM 容量；
- CPU busy 只产生 WARN，不阻止启动；
- probe error、timeout、cleanup blocked、owner identity mismatch 或 scope mismatch 均 fail closed。

StartGuard 只做启动瞬时保护。campaign 启动后不采样资源、不预测容量，也不新增资源
watchdog。运行失控由既有 per-state/batch hard timeout、lease、owner tree、fence 和 cleanup 收敛。

同一 macOS service instance 同时只允许一个 active campaign；同一 control domain 只允许一个
有效 lease。W1 与 W2 不并行运行。

服务端按实际 request profile/config path 加载 v4/v5/v6，并以
`(profile, config_sha256, accelerator, selector)` 缓存 guard composition。缓存只复用 probe wiring，
不复用 `GuardResult`；Darwin/MPS 三个 profile 都选择 MPS probe，Linux v3/v4 继续走原 CUDA/NVML
路径。

## 8. Selection、共享队列和单点 Worker

服务在启动前写不可变 selection binding：

- `FirstPassSelectionBinding` 用于 v4/v6，包含 4–20 点和四个固定 anchor；
- `RetrySelectionBinding` 用于 v5，只包含一个点，并引用原 catalog、selection、result hash；
  原 result 必须是已提交的业务 `FAILED`。

binding 还包含 catalog schema/hash、坐标系、有序 point id/pose/hash、campaign/batch、profile
config hash 和 runtime closure hash。adapter 不生成默认点，也不把完整 catalog 交给 Worker 遍历。

W2 的两个 slot 只是并发容量。全部 selected points 进入一个 durable queue，调度身份为：

```text
(campaign_id, batch_id, point_id, attempt_id, generation, worker_id)
```

一个 lease 只对应一个点。Worker 读回单点输入的 point id/hash 后才可执行；unselected point
不得取得 lease、MoveIt invocation 或 result。W1 first-pass 顺序排空同一类队列；W1 retry 的
队列只能包含 binding 中的失败点。

result 必须在 station READY、MoveIt/物理业务判定、broker attempt、evidence manifest 和 cleanup
ownership 都持久化后才能提交。attempt-level `INVALID`、基础设施失败和业务 `FAILED` 分开保存。

## 9. Journal 与 projection

macOS W1/W2 复用现有 `CoordinatorJournal`。coordinator 是正常运行期唯一 writer；Worker
先原子提交 result/manifest 并 fsync，再通过私有 IPC 提交 proposal。

事件至少包括：

- `CAMPAIGN_STARTED`
- `WORKER_REGISTERED`
- `POINT_LEASED`
- `ATTEMPT_STARTED`
- `RESULT_COMMITTED`
- `POINT_TERMINAL`
- `BATCH_TERMINAL`
- `CLEANUP_COMMITTED`

coordinator 校验 lease/generation/path/hash/idempotency，append 并 fsync journal，然后原子写入
`CommittedWatermark(writer_epoch, sequence, event_sha256)` 并 fsync 目录。两道 durability barrier
都成功后才 ACK。live reader 最多读取 watermark 覆盖的 committed prefix；flush 后、fsync 前的
frame，或 watermark 之后的完整 frame，都不得投影。

所有 source 只做格式与身份验证。唯一 canonical reducer 分开维护：

- point status：`UNRUN/PASSED/FAILED/INDETERMINATE`；
- execution phase：`QUEUED/LEASED/RUNNING/TERMINAL`；
- attempt validity 与 infrastructure outcome；
- batch business terminal、cleanup complete 和 recovery fence。

服务在一个 SQLite 事务中完成 idempotency、reducer、全量状态和 accepted cursor 更新。失败时
全部回滚。epoch 退化、sequence gap、hash 断裂、identity 漂移、非法终态追加和不确定尾部均
进入 operator recovery；`campaign-result.json` 只保留终态摘要用途。

## 10. 执行授权与 retry admission

本设计没有资源测量授权。live 执行只有两个互斥 context：

- `CandidateExecutionContext`：用于实现阶段的有限候选运行。它绑定 task/dispatch、profile 与
  config hash、runtime closure、worker_count、batch、evidence root、owner generation、一次性
  command id、expiry 和 max-runs。
- `ProductionExecutionContext`：由安装版服务根据允许的 v4/v5/v6 profile、当前 copied-install
  binding、service session、有效 control lease、owner generation 和一次性 command id 签发。

两类 context 都不含 budget、qualification 或 promotion 字段，不能在另一类 endpoint 使用，
也不能跨 batch/profile/worker_count/evidence root 重放。

retry 使用独立 `RetryStartRequest`，绑定原 campaign、失败 point、原 terminal result hash、新
batch、v5 config、runtime closure、command 和 lease generation。只有同时满足以下条件才准入：

- 原 point 是业务 `FAILED`，不是 `INFRA_FAILED`、`INDETERMINATE`、`INVALID` 或 `UNRUN`；
- 原 batch 已 business terminal 且 cleanup complete；
- 没有 active/unknown owner 或 recovery fence；
- context、service session、lease、command 和请求身份一致；
- command 尚未消费。

消费 command、创建 retry binding 和写 owner spawn intent 在一个数据库事务中完成。事务后
spawn 失败时保留 intent/fence，command 不得重放。retry 只追加历史，不覆盖 first-pass result
或统计。

## 11. Owner tree、timeout 与 cleanup

每个真实 spawn 边界先持久化 intent，再在 `Popen` 后读回 PID/birth/PGID：

```text
adapter -> campaign -> worker -> station
                    -> broker
```

station 即使位于独立 session，也必须挂在同一 owner tree。cancel、exception 和已有 hard timeout
均按叶到根回收。服务或 adapter `SIGKILL` 后，reaper 先核对 PID/birth、generation 和 parent
binding；身份不明时不猜 PID、不盲杀，保留 fence。

只有匹配 generation 的 recovery owner 完成回收、fsync cleanup receipt，并提交
`CLEANUP_COMMITTED` 后才能解除 fence。foreign 进程始终保留并报告。

## 12. 代码边界

| 边界 | 精确责任 |
| --- | --- |
| runtime closure / rpath | 已完成的 runtime closure 与 station diagnostic；必要时只改 submodule `mujoco_ros2_control/CMakeLists.txt` 的 macOS install-rpath，并补 copied-install contract |
| selection / queue | 新 `parallel_batch/selection.py`、`queue.py`、`single_point_input.py`；修改 W2 campaign/worker |
| journal / projection | 修改 `parallel_batch/journal.py`；新 `expert_validation/reducer.py`、`projection_source.py`；修改 store/production |
| ownership | 新 `expert_validation/owner_tree.py`；在 adapter/campaign/worker/station 真实 spawn 边界接线 |
| W1 profiles | 新 v5/v6 config、`w1_composition.py`、W1 first-pass/retry CLI；修改 contracts、setup 和 service adapter |
| execution authorization | 新 `expert_validation/execution_context.py`；修改 API/store/supervisor/service |
| macOS support matrix | 修改 preflight/API/production、unified capabilities 和 Web campaign setup；只显示/接受 W1/W2 |
| browser acceptance | 更新现有 live-sim W1/W2/retry、StartGuard 和 evidence assertions |

不新增或修改任何 macOS resource-budget 文件，不更新旧预算文档。

## 13. 验收

### 13.1 自动化

- v4 bytes/SHA 和 exact-W2 行为不变；v5/v6 只接受各自的 Darwin/MPS W1 合同。
- macOS N>2 在 Web 不可选，API、preflight 和 adapter 都以稳定 reason 拒绝。
- StartGuard 在 campaign 与每个 Worker spawn epoch fresh 执行；CPU WARN 可继续，RAM/MPS
  FAIL、probe error 和 identity mismatch 拒绝。
- 预置或篡改 `start-guard.json`、旧 epoch、不同 owner 的 guard result 都不能绕过 public CLI、
  service preflight 或 adapter 的 fresh check；v5/v6 安装版配置不得落入 CUDA/NVML 分支。
- 非默认 selection 的所有 selected points 各执行一次，unselected points 为零次；retry 只执行
  指定失败点。
- journal/watermark、canonical reducer、cursor transaction、restart、tamper、partial tail、
  `SIGKILL` 和 owner identity failure 均有 RED -> GREEN 回归。
- 候选/生产 context 的类型混用、过期、重放、hash/lease/profile 漂移全部拒绝。
- retired `so101_measure_parallel_resources` 仍返回原 fail-closed 结果。

### 13.2 Live

- Gate A：五次连续 FULL_RESTART READY，copied install 不依赖临时
  `DYLD_LIBRARY_PATH`，每轮无 task-owned residue。
- W2：两个 Worker/两套 station，完整 selected set 各一次，raw journal、projection、物理结果和
  cleanup 一致。
- W1 first-pass：一个 Worker 顺序执行完整 selected set，使用 v6，不带 retry 语义。
- W1 retry：只重试一个 terminal-clean 的真实业务失败点，使用 v5 和 fresh FULL_RESTART。
- fresh Chrome 分别显示 W2、W1 与 retry 的进度、终态、证据和 cleanup。

验收只声明功能、稳定性、物理结果、projection、ownership 和 cleanup。它不声明 macOS 资源
容量资格。

## 14. 迁移顺序

1. 从既有本地提交恢复 legacy `CP-MSC-A`，确认它仍为 `UNCONFIRMED`，不把一次 READY 写成 PASS。
2. 完成 copied-install/rpath A/B；满足判据时做最小 CMake 修复，再完成 5/5 readiness。
3. 实现 selection、共享队列和单点 Worker。
4. 实现 committed watermark、canonical reducer 和真实 owner tree。
5. 实现 v5/v6、W1 composition、W1/W2 support matrix 和 fresh per-spawn StartGuard。
6. 实现候选/生产 execution context 与 retry 原子准入。
7. 完成 offline package/Web gates和候选 live gate。
8. 使用安装版 `ProductionExecutionContext` 完成 fresh Chrome W2、W1、retry 验收。
9. Sol/high 审查实施结果并写操作指南；Astra/high 做最终独立审查。只形成本地提交。

任何 product byte 或执行语义变化都使此前 live 证据失效；修复后从受影响 gate 新建实验运行。

## 15. 未采用方案

### 15.1 恢复 macOS 资源预算体系

拒绝。W2 已被用户接受为资源足够，本任务只需轻量启动保护。预算、采样、资格化和 promotion
会扩大实现与运维面，也不能替代物理、projection 和 cleanup 验收。

### 15.2 直接放宽 v4

拒绝。v4 是 frozen exact-W2 合同。W1 通过 v5/v6 明确表达 retry 与 first-pass，不改写旧语义。

### 15.3 用临时 `DYLD_LIBRARY_PATH` 作为最终修复

拒绝。它可以作为 A/B 变量，但最终 copied install 必须通过自身 install-rpath 闭合并完成
loaded-image readback。

### 15.4 根据点数选择 W1 或 W2

拒绝。点数是业务 selection，worker count 是显式执行 profile。两者独立。

### 15.5 轮询 `campaign-result.json`

拒绝。终态摘要没有可靠 live sequence、durability watermark 或 crash-recovery cursor。

## 16. 完成定义

- Gate A 根因达到 `CONFIRMED`，或明确证明无需产品修复；五次连续 FULL_RESTART READY 通过。
- macOS capabilities、Web 和服务端只支持 W1/W2，N>2 明确拒绝。
- campaign 与每个 Worker spawn 前都有 fresh、identity-bound StartGuard 结果。
- W2/W1 first-pass 和单点 retry 都由统一服务启动，profile 路由无推断或 fallback。
- selected-only 执行、journal committed prefix、canonical projection 和事务 cursor 一致。
- first-pass 与 retry 的业务、attempt、证据和统计保持分离。
- owner tree、hard timeout、fence、cancel 和 crash cleanup 验证通过，无 task-owned residue。
- fresh Chrome W2/W1/retry 与 raw journal、物理证据一致。
- 所有受影响测试 GREEN；ledger 记录新 checkpoint、retained/archived/deletion candidates。
- 报告明确写明“未做 resource qualification/capacity certification”。
- Astra/high 独立复审通过；只提交本地，不自动 push 或 merge。
