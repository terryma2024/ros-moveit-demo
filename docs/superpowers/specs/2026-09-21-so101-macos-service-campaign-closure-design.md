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
- foreign modified fork overlay 没有重跑。因此 legacy `CP-MSC-A` 永久保留
  `UNCONFIRMED`，不能改写成 Gate A PASS，也没有理由修改 controller 初始化代码。历史 overlay
  无法恢复时记为 `LEGACY_PROVENANCE_UNRECOVERABLE`；它限制历史归因，但不阻塞当前
  task-owned frozen product 的 Gate A。
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

- `RuntimeClosureIdentity`：`install_root`、source commit、submodule commit、copied install 相对文件
  SHA256、executable/dylib/plugin XML 来源、版本、净化环境约束，以及
  robot/controller/model/launch hash。Gate A 中 `install_root` 必须精确等于本轮 task-owned merged
  `CLOSURE_ROOT`，不能写成 Python package prefix 或任一分散 underlay。
- `RunBinding`：campaign、batch、fresh `ROS_DOMAIN_ID`、station session、evidence root、owner
  generation 和启动时间。
- `RuntimeAttestation`：实际 PID/birth identity、加载 image/dylib、ROS domain 和前两层 hash。
- `RuntimeProcessAttestation`：对 owner tree 中每个关键进程记录
  `(role, pid, birth, executable, loaded_images[path, sha256])`。其中 `role=controller_runtime`
  必须是启动树内真正承载 `/controller_manager` 的后代进程，不能用 diagnostic launcher、direct
  dlopen probe 或同树其他 child 代替。

process role 在 spawn intent 写入时绑定，随后用 owner ancestry、PID/birth、executable 与该 PID 的
ROS phase evidence 确认；不得在结果出现后按 loaded image 反推 role。

五次重启使用相同 closure identity，但每轮 binding 与 attestation 不同。READY 前必须验证实际
加载来源；source tree、README 或单独的环境变量不构成 closure 证明。`controller_runtime` 的
loaded images 为空、plugin/vendor 任一路径或 SHA 不匹配、PID/birth/executable 在 probe 前后漂移、
找错 child，或只证明 probe/launcher 加载成功时，该轮一律 `INVALID`。

### 5.2 三轴状态机

Gate A 不用一个枚举同时表达当前产品、controller 排除和历史归因。三条轴独立记录：

| 轴 | 合法值 | 含义 |
| --- | --- | --- |
| `current_boundary_verdict` | `UNCONFIRMED_CURRENT`、`CONFIRMED_RPATH`、`CURRENT_CLOSURE_ALREADY_VALID`、`CURRENT_NON_RPATH_FAILURE`、`INVALID_CONTROL` | 只判断本次 task-owned frozen bytes |
| `controller_verdict` | `NOT_EXCLUDED`、`EXCLUDED_BEFORE_ROS_PLUGIN_INSTANCE_INIT`、`CURRENT_CONTROLLER_PATH_OPERATIONAL` | 只判断当前 bytes 是否到达或通过 controller 路径 |
| `legacy_attribution` | `LEGACY_TRACEABLE`、`LEGACY_PROVENANCE_UNRECOVERABLE` | 只描述 foreign modified overlay 的历史可归因性 |

派生的 Gate A 状态另行维护为 `OPEN` 或 `CURRENT_PRODUCT_GATE_PASSED`。legacy
`CP-MSC-A=UNCONFIRMED` 与 `LEGACY_PROVENANCE_UNRECOVERABLE` 都不会被后续成功覆盖；当前产品
是否通过只由 frozen current bytes 的 controls、attestation 和五次 readiness 决定。

`EXCLUDED_BEFORE_ROS_PLUGIN_INSTANCE_INIT` 的含义很窄：full station 因 manifest-bound vendor
依赖缺失而失败，且没有任何 ROS plugin instance phase marker，例如 `PLUGIN_RESOLVED` 或
`HARDWARE_INITIALIZING`。direct `dlopen` 可能执行 dylib initializer，但这不等于 ROS/pluginlib
已经创建 hardware plugin instance，不能单靠 direct probe 写出该 verdict。这个值也不能推广成
“历史 controller 一定没有缺陷”。`CURRENT_CONTROLLER_PATH_OPERATIONAL` 要求当前 candidate 实际
达到三个 controller active、三个 MoveIt service 和三个 action ready。

### 5.3 固定 control-set 与 N/P/F controls

每组 controls 先封存一个 `GateAControlSetManifest`，至少包含：parent/submodule commit、copied
install inventory、controller executable、plugin、MuJoCo vendor dylib、plugin XML、robot/controller
config 与 model hash、semantic argv/env、ROS domain policy、diagnostic/tool version 和 evidence
子目录。N/P 必须引用同一个 manifest hash。

manifest 把不可变语义与每轮 `RunBinding` 分开：semantic argv 固定 launch package/file、mode、
`headless=false`、`sensor_rendering=true`、`include_teleop=false`、scene path/SHA、
`mujoco_initial_keyframe=task_start`、readiness deadline 和 cleanup deadlines；semantic env 固定
underlay/overlay、PATH、Python、locale 与 control policy。只有以下 typed substitution 可以逐轮变化：

| substitution | 类型与约束 |
| --- | --- |
| `session_id` | safe session id；在本批内唯一 |
| `ros_domain_id` | `0..232`；相对 foreign/task runs fresh |
| `report_path`、`task_evidence_root` | 本轮 control 目录的 resolved descendant |
| `ROS_HOME`、`ROS_LOG_DIR` | 本轮目录下的 resolved descendant |
| `TMPDIR`、`TMP`、`TEMP` | 指向同一个本轮 tmp resolved path |

每次 spawn 前先验证 substitution 类型与 containment，再把 expanded argv/env 原样写证据。比较 N/P
时将这些已验证值归一化为 typed token；除此之外不允许忽略任何 argv/env 差异。P 的唯一实验变量
仍是 manifest-bound vendor lib `DYLD_LIBRARY_PATH`。

copied install 是本轮 evidence 子目录中的 fresh task-owned merged closure：N/P 使用
`CLOSURE_ROOT=$GATEA_RUN_ROOT/control-set/closure`，F 使用
`F_CLOSURE_ROOT=$GATEA_RUN_ROOT/fixed/closure`。构建顺序固定为：

1. 用仓库 `scripts/install-mujoco-vendor-macos.zsh` 从 pinned、clean、只读 MuJoCo authority source
   构建 vendor，并安装到 `$CLOSURE_ROOT/opt/mujoco_vendor`；
2. source host ROS underlays 和 `$CLOSURE_ROOT/setup.zsh`，用 `--merge-install --install-base
   $CLOSURE_ROOT` 构建 `third_party/mujoco_ros2_control` packages；
3. 再 source `$CLOSURE_ROOT/setup.zsh`，用同一 merged install root 构建
   `so101_mujoco_support` 与 `so101_demo_py`。

manifest 冻结 `$CLOSURE_ROOT` 完整树，plugin、vendor、Python package 和 diagnostic 必须都位于该
root。按现有 `setup.cfg`，入口是
`$CLOSURE_ROOT/lib/so101_demo_py/so101_diagnose_macos_station`。bootstrap 必须证明 ament prefix
精确等于 `$CLOSURE_ROOT`，`so101_demo.__file__` 与 probe module origin 都是其 descendant，
interpreter 精确等于 `TEST_PYTHON`，diagnostic shebang 也与它匹配。P 只能增加
`$CLOSURE_ROOT/opt/mujoco_vendor/lib`。旧 ledger 的 build script 只作只读参考；新
vendor/build/log/install 只能写入本轮 `gate-a-resolution/$DISPATCH_ID/`。

- N（negative）：删除所有 `DYLD_*`，先对 copied plugin 做
  `dlopen(RTLD_NOW | RTLD_LOCAL)`，再启动 bounded full-station diagnostic。
- P（positive）：始终执行。使用同一 control set，只增加 task-owned MuJoCo vendor lib 目录的
  `DYLD_LIBRARY_PATH`，重复 direct dlopen 与 full-station diagnostic。
- F（fixed/current candidate）：N/P 确认 rpath 后，冻结只含计划内 CMake/provenance/test 变化的
  新 control set；不设置 `DYLD_LIBRARY_PATH`，重复 direct dlopen、full-station diagnostic 和
  loaded-image attestation。若当前 N 已证明 closure 完整，则 N 自身就是 F，不产生产品修改。

direct probe 必须输出 `DLOPEN_STARTED`、`DLOPEN_SUCCEEDED` 或 `DLOPEN_FAILED`、原始 `dlerror`、
plugin/vendor path 与 SHA。它只验证 loader closure，不证明 ROS plugin instance 已创建。station
diagnostic 继续输出 `PLUGIN_RESOLVED`、
`SIMULATION_ENDPOINT_READY`、`HARDWARE_INITIALIZING`、`HARDWARE_READY`、
`CONTROLLER_MANAGER_SERVICES_READY` 和 `CONTROLLERS_ACTIVE`。成功进程通过
`RuntimeProcessAttestation` 回读 `controller_runtime` 后代实际 loaded image 的绝对路径和 SHA；
`DYLD_PRINT_*` 只能作辅助，不能替代 direct dlopen 或 per-process loaded-image readback。

N/P 由一个全函数、无隐式 fallback 的 deterministic reducer 归并。输入先按单轮规则分类为
`PASS`、`MISSING_VENDOR_BEFORE_ROS_PLUGIN_INSTANCE_INIT`、`NON_RPATH_FAILURE` 或 `INVALID`；任何
未列入下表的组合默认 `INVALID_CONTROL`：

```python
def reduce_gate_a_controls(
    negative: GateAControlObservation,
    positive: GateAControlObservation,
) -> GateADecision: ...
```

单轮 observation 分类合同如下。表中的“允许缺失”是完整白名单，不代表 reducer 可以忽略其他字段：

| Observation class | 必需证据 | 允许缺失 |
| --- | --- | --- |
| `PASS` | manifest/semantic/binding valid；healthy collector；真实 `controller_runtime` role、PID/birth/executable；`DLOPEN_SUCCEEDED`；manifest-bound plugin/vendor process images；全部 ROS phase marker、READY；cleanup complete | loader error、first-bad phase |
| `MISSING_VENDOR_BEFORE_ROS_PLUGIN_INSTANCE_INIT` | manifest/semantic/binding valid；healthy collector；真实 controller process role、PID/birth/executable；`DLOPEN_FAILED`；精确 manifest vendor missing loader error；未越过任何 ROS plugin instance marker；cleanup complete | plugin/vendor process images；`PLUGIN_RESOLVED`、`HARDWARE_INITIALIZING` 及其后 markers；READY |
| `NON_RPATH_FAILURE` | manifest/semantic/binding valid；healthy collector；稳定 process identity；`DLOPEN_SUCCEEDED`；manifest-bound plugin/vendor images；明确 first-bad ROS phase；cleanup complete | first-bad phase 之后的 markers、READY |
| `INVALID` | 记录具体 invalid reason | 不适用；它是拒绝结果，不是成功证据的简化版 |

分类顺序固定：先校验 manifest、semantic diff、binding、collector、process identity、timeout 和
cleanup，任一失败立即 `INVALID`；再匹配精确 missing-vendor 合同；再匹配 `PASS`；再匹配带首坏
phase 的 `NON_RPATH_FAILURE`；其余一律 `INVALID`。因此相同的 missing-vendor 表象，如果 collector
或 controller process identity 缺失，只能得到 `INVALID_CONTROL`，不能得到 `CONFIRMED_RPATH`。

判定矩阵固定如下：

| N | P | 判定 | 后续 |
| --- | --- | --- | --- |
| `MISSING_VENDOR_BEFORE_ROS_PLUGIN_INSTANCE_INIT` | `PASS` | `CONFIRMED_RPATH` + `EXCLUDED_BEFORE_ROS_PLUGIN_INSTANCE_INIT` | 只允许最小 CMake install-rpath 修复，随后执行 F |
| `PASS` | `PASS` | `CURRENT_CLOSURE_ALREADY_VALID` + `CURRENT_CONTROLLER_PATH_OPERATIONAL` | 不改产品 bytes，N 作为 F 进入五次 readiness |
| `MISSING_VENDOR_BEFORE_ROS_PLUGIN_INSTANCE_INIT` | `NON_RPATH_FAILURE` | `CURRENT_NON_RPATH_FAILURE` + `NOT_EXCLUDED` | 保存 P 的首坏 ROS phase，停止并提交 owning-layer plan amendment |
| `NON_RPATH_FAILURE` | `PASS` 或同一 `NON_RPATH_FAILURE` | `CURRENT_NON_RPATH_FAILURE` + `NOT_EXCLUDED` | 保存 N 的首坏 ROS phase，停止并提交 owning-layer plan amendment |
| `PASS` | 非 `PASS` | `INVALID_CONTROL` + `NOT_EXCLUDED` | P 与 N 的唯一变量模型被破坏；停止并修订 control plan |
| 相同或不同 loader failure，但 P 未成为 `PASS` | 任意非 `PASS` | `INVALID_CONTROL` + `NOT_EXCLUDED` | vendor binding/control 无法证伪 rpath；停止并修订 control plan |
| 任一 control timeout、缺少该 observation class 表中要求的 marker/attestation、identity drift、cleanup residue、semantic diff 或非法 substitution | 任意 | `INVALID_CONTROL` + `NOT_EXCLUDED` | 停止本批并修订 control plan；不得把该 class 明确允许缺失的字段当成 invalid |
| 任意未列组合 | 任意 | `INVALID_CONTROL` + `NOT_EXCLUDED` | fail closed |

`CONFIRMED_RPATH` 路径的 F 必须在无 `DYLD_LIBRARY_PATH` 时 direct dlopen 成功，且实际
`controller_runtime` 后代加载的 plugin 与 `libmujoco.3.4.0.dylib` 都来自同一 copied prefix，路径和
SHA 与 manifest 一致。只证明 diagnostic/probe 自身加载成功不算 GREEN。失败则修复未 GREEN，不能
进入 readiness。`CURRENT_CLOSURE_ALREADY_VALID` 是另一条完整合法路径，不以“没有复现 foreign
overlay”为由追加产品修改。

### 5.4 Readiness 与 Gate A 收敛

`motion_stack_ready` 继续 fail closed。每轮必须同时满足：

- 直连 `/controller_manager/list_controllers` 成功；
- `joint_state_broadcaster`、`arm_controller`、`gripper_controller` 都是 `active`；
- 三个 MoveIt service 与三个 action 可用；
- controller、MoveIt 和 attestation 属于同一 `ROS_DOMAIN_ID` 与 copied install；
- READY 后由 diagnostic 主动发起有界正常 shutdown，再按 `SIGINT -> SIGTERM -> SIGKILL` 的既有
  owner-tree deadline 收敛；persistent launch 不会自行退出，不得等待“自然退出”；
- shutdown 后逐一核对所有 owned descendants 的 PID/birth 与 IPC，task-owned residue 为零。

每轮都必须在 READY 时对真实 `controller_runtime` descendant 生成新的
`RuntimeProcessAttestation`。其 executable、plugin image 和 vendor image 必须命中本轮 manifest；
空 image 列表、probe/launcher attestation、wrong child 或 identity drift 都使该轮 `INVALID`，不能计入
五连通过。

只有 F 的 no-DYLD direct dlopen 与 loaded-image attestation 通过后，才运行连续五次 VALID
`FULL_RESTART`。五轮必须使用相同 F closure identity，且 run binding/attestation 各自唯一。
VALID 失败中断连续序列；INVALID 结束本批次，以新实验 ID 重开。既有一次 READY 只证明路径
可行，不计作这五次。

五次均 READY 且 cleanup 为零后，`controller_verdict` 更新为
`CURRENT_CONTROLLER_PATH_OPERATIONAL`，派生状态更新为 `CURRENT_PRODUCT_GATE_PASSED`。合法
入口只有两条：

```text
CONFIRMED_RPATH -> F no-DYLD attestation -> 5x FULL_RESTART
CURRENT_CLOSURE_ALREADY_VALID -> current N is F -> 5x FULL_RESTART
```

`CURRENT_NON_RPATH_FAILURE`、`INVALID_CONTROL`、F attestation 失败、任何 VALID readiness 失败或
cleanup residue 才是必须停止并修订计划的条件。`LEGACY_PROVENANCE_UNRECOVERABLE` 不是停止条件。

### 5.5 串行 writer handoff

Gate A Codex 复用 mac-mini 当前 worktree
`/Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp` 和分支
`codex/so101-unified-webapp`。旧 `dst-so101-macos-closure` 在 handoff 前暂停，并在整个 Gate A
resolution 期间保持只读；Codex 是代码、ledger 和 evidence 的唯一 writer。

新运行继续使用 ledger 已登记的 evidence root
`/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1`，只在其下
创建 `gate-a-resolution/$DISPATCH_ID/`。旧 evidence 内容只读保留；不创建第二个 root，也不把
新的日志写入旧实验子目录。

Codex 在 `CP-MSC-A1` 提交 code、tests 和 ledger 后停止并退出，或写出明确 writer-release
record。Sol/high 随后审查 commits、controls、5x 证据和目标 worktree readback；只有审查 PASS 后
才通知暂停的 dst 接回 writer ownership。dst 在收到该明确通知前不得开始 Task 2。

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

- Gate A：`current_boundary_verdict` 经 N/P/F 矩阵闭合；F 的 direct dlopen 和 loaded-image
  path/SHA 在无 `DYLD_LIBRARY_PATH` 时通过；五次连续 FULL_RESTART 中，真实
  `controller_runtime` descendant 的 per-process plugin/vendor path/SHA、PID/birth/executable 每轮
  有效，READY 后有界 shutdown，且无 task-owned descendant/IPC residue。
- W2：两个 Worker/两套 station，完整 selected set 各一次，raw journal、projection、物理结果和
  cleanup 一致。
- W1 first-pass：一个 Worker 顺序执行完整 selected set，使用 v6，不带 retry 语义。
- W1 retry：只重试一个 terminal-clean 的真实业务失败点，使用 v5 和 fresh FULL_RESTART。
- fresh Chrome 分别显示 W2、W1 与 retry 的进度、终态、证据和 cleanup。

验收只声明功能、稳定性、物理结果、projection、ownership 和 cleanup。它不声明 macOS 资源
容量资格。

## 14. 迁移顺序

1. 永久保留 legacy `CP-MSC-A=UNCONFIRMED`；暂停旧 dst，把同一 worktree 的 writer ownership
   串行交给 Gate A Codex，并在已登记 root 下创建新的 `gate-a-resolution/$DISPATCH_ID/`。
2. 封存 control-set，执行 N/P/F 矩阵；沿 `CONFIRMED_RPATH` 或
   `CURRENT_CLOSURE_ALREADY_VALID` 路径完成 no-DYLD attestation 与 5/5 readiness，在
   `CP-MSC-A1` 提交并释放 writer。
3. Sol/high 审查 Gate A commits、证据和 worktree readback；通过后才通知 dst 接回 writer。
4. 实现 selection、共享队列和单点 Worker。
5. 实现 committed watermark、canonical reducer 和真实 owner tree。
6. 实现 v5/v6、W1 composition、W1/W2 support matrix 和 fresh per-spawn StartGuard。
7. 实现候选/生产 execution context 与 retry 原子准入。
8. 完成 offline package/Web gates和候选 live gate。
9. 使用安装版 `ProductionExecutionContext` 完成 fresh Chrome W2、W1、retry 验收。
10. Sol/high 审查实施结果并写操作指南；Astra/high 做最终独立审查。只形成本地提交。

任何 product byte 或执行语义变化都使此前 live 证据失效；修复后从受影响 gate 新建实验运行。

## 15. 未采用方案

### 15.1 恢复 macOS 资源预算体系

拒绝。W2 已被用户接受为资源足够，本任务只需轻量启动保护。预算、采样、资格化和 promotion
会扩大实现与运维面，也不能替代物理、projection 和 cleanup 验收。

### 15.2 直接放宽 v4

拒绝。v4 是 frozen exact-W2 合同。W1 通过 v5/v6 明确表达 retry 与 first-pass，不改写旧语义。

### 15.3 用临时 `DYLD_LIBRARY_PATH` 作为最终修复

拒绝。它只用于 P control；最终 copied install 必须在 no-DYLD 环境中靠自身 closure 闭合，并完成
loaded-image readback。只有 `CONFIRMED_RPATH` route 才授权修改 install-rpath。

### 15.4 根据点数选择 W1 或 W2

拒绝。点数是业务 selection，worker count 是显式执行 profile。两者独立。

### 15.5 轮询 `campaign-result.json`

拒绝。终态摘要没有可靠 live sequence、durability watermark 或 crash-recovery cursor。

## 16. 完成定义

- legacy `CP-MSC-A=UNCONFIRMED` 保持不变；`legacy_attribution` 已明确，且历史不可恢复状态没有被
  错写为当前产品缺陷。
- `current_boundary_verdict` 是 `CONFIRMED_RPATH` 或 `CURRENT_CLOSURE_ALREADY_VALID`；F 在无
  `DYLD_LIBRARY_PATH` 时 direct dlopen、真实 controller descendant 的 per-process loaded-image
  path/SHA 和 closure attestation 全部通过。
- F 的 `RuntimeClosureIdentity.install_root` 精确等于 task-owned merged `F_CLOSURE_ROOT`；manifest
  冻结完整 tree，vendor、plugin、Python、diagnostic 与 ament prefix 均属于同一 root。
- 五次连续 FULL_RESTART READY/clean 通过，`controller_verdict` 为
  `CURRENT_CONTROLLER_PATH_OPERATIONAL`，Gate A 派生状态为 `CURRENT_PRODUCT_GATE_PASSED`。
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
