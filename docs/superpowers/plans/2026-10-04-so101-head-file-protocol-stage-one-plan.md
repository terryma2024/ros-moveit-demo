# SO-101 Head 文件协议阶段一执行计划

> 执行者：本计划待用户明确审批。审批后由本机 `gpt-6-luna` 串行实施，GPT-6.1 Sol / High 冻结源码后 Review、分析复杂问题并协调。当前仅写计划；不派发 Luna，不测试新实现，不启动仿真。用户指定的模型与执行方式优先于仓库默认 `dst` 和独立 reviewer 规则。

**Goal:** 在没有在线监督进程和逐动作 ACK 准入的条件下，主进程独立完成一次真实 MuJoCo + CUDA Head 闭环，留存完整文件日志，再逐项分析日志中的问题。

**Architecture:** 单一入口绑定资源。主进程拥有状态、inventory、时钟预算、原始反馈、停稳证明和停止路径；单一 CUDA owner 按停点请求新帧。一个有界文件 writer 保存原始记录及产物，完成 teardown 后封存；协调者在运行结束后回读。

**Tech Stack:** ROS 2 Jazzy、MuJoCo、BrokerOwnedTrajectoryController、Python、C++、CUDA YOLO、pytest/CTest、UTF-8 JSONL、SHA256、fsync。

**Spec:** [2026-10-03-so101-head-search-optional-supervision-amendment.md](../specs/2026-10-03-so101-head-search-optional-supervision-amendment.md)。执行前还须读 [当前任务账本](../../experiments/so101-head-file-protocol-1003-experiment-ledger.md) 及其引用的只读交接。

## 审批边界和全局约束

本计划覆盖文件协议、主进程本地校验、Head 遗留在线依赖清理、真实安装组合、首条闭环与全部日志分析。阶段二正式只读审核程序须在阶段一问题清单形成后另行设计、审批。现在只做 writer 必要的 readback 与协调者分析，不开发完整审核器框架。

- Worktree 固定为 `/data/work/ws_moveit/.worktrees/so101-head-file-protocol-1003`，branch 为 `codex/so101-head-file-protocol-1003`。保留继承的 dirty，不切 main，不 reset，不重建旧 CLI，不 resume/fork 旧 goal，不 push。
- 唯一 evidence root 为 `/data/work/so101-evidence/act-data/20260930-antzb-head-search-krIv681m`，下文简称 `E`。普通低频日志为 `/tmp/so101-debug-head-file-protocol-1003`，简称 `L`；保留价值的终态记录迁存 `E` 后读回。源码内不放 runtime 目录。
- 本机为 antzb，hostname `AI-STATION-001`。沿用本任务 NVMe scratch 约定；这不是向 antzb 套用 ai-station 的通用强制规则。每次 fsync-heavy 测试使用 `E/scratch/<全新 test-id>/tmp`，设置 `TMPDIR/TMP/TEMP`，用实际测试 Python 证明 `tempfile.gettempdir()` 在该目录中。
- MuJoCo-only、单模型、单 stack、串行、CUDA/no CPU fallback、无 Grounded-SAM、无真实 SO-101。私有只读 `MjModel/MjData` 碰撞回放不启动第二 simulation owner。
- Head 在线监督 socket、heartbeat、RPC、动作 ACK 全部退出执行依赖。native reservation/primary-fault 本地控制 socket 和 Teleop 的目标/停止桥仍有各自用途，不能把这些接口误删成监督接口。
- 完整轨迹、位置/速度/加速度、路径碰撞、typed inventory、native 准入、未知 acceptance 对账、可靠 stop 全部保留。不得用总成功 null ACK、放松阈值或续期未知 claim 达成 GREEN。
- 新源码/config/policy 对旧 bundle/live/QUALIFIED 的证明无效。新运行使用新 run ID；execution、audit、qualification 分开。
- ACT 的 W2 → 独立 exact-W8/40、不跑 W4/W6、资源仅入口绑定合同不变。ordinary package/native gates 只在集成边界运行；本轮不比较模型，不跑 benchmark。
- 不删除证据。源码删除由 Git 恢复；保留旧 worktree、交接摘要和历史只读 reader。计划审批不等于后续 qualification 或人工 digest 批准。

## 已核验的冻结基线

2026-10-04 的 fresh readback：HEAD 为 `cf7766a9b6e59c2ff3721ef42afb4757f44fc409`，submodule 为 `495c3d6f512b5301405fc0955576bc231e344a7f` 且 clean。旧 CLI PID 169291 已不存在，新 CLI PID 1685148 的 argv 包含 `--no-daemon -m gpt-6.1-sol` 和 High，没有 resume/fork。只读 host 检查未见本任务的活跃 stack/test/GPU compute；启动前仍须重查 ROS graph。进程不存在不能充当 physical stop proof。

交接位于 `E/handoffs/head-file-transition-c3db052b/`。已完整读取 status、snapshot、ready、迁移/进程记录，重新核验 manifest 全部 505 个条目的大小与 SHA256。新基线为 `E/head-file-protocol-1003/planning-baseline-20261004/baseline.json`，SHA256 `40bb3a95bcda8c0739959819c8b80bf094fe3f97ce90d21d4051ce9546becbf1`。

| 输入 | SHA256 | 用途 |
| --- | --- | --- |
| dirty `src/so101_demo_py/src/act/search.py` | `6a7d09da324acbc46dfa3b08a29ab8082027114a7e12204e85e0055d8a553788` | HS411 纯 controller patch；迁移保存，尚未证明真实执行 |
| dirty `src/so101_demo_py/test/test_act_head_stopped_search_policy.py` | `9957accb565c0f0dc783de148de53a144d3761bf8eb4104d7dd313b3792b2e39` | 继承测试，不覆盖为新空文件 |
| 最新 amendment | `36c1401be18e64b61b0a57f2084348dadd73dc7037c076752086e13240dd259b` | 当前设计方向 |
| 交接中的旧 dirty ledger | `37fad92b6edd7f387a15a2bc57b621c6ae01fc35272c3c1e09b90d5a69e09ade` | 只读历史输入；新账本引用 HS410–HS412 |

历史 demo 全套 rc1（7400 pass、122 fail、77 error、152 skip），Teleop 全套 rc1（1267 pass、17 fail、43 skip），当前 native 闭合尚未完成。缺少 ACT path-screen 模块、Task8 权重等问题不能靠替换 Head 权重或安装失败来制造测试结论。旧 40 场景为 38 PASS/2 FAIL，旧 diagnostic rc2、audit rc0 记录的是拒绝，不是闭环成功。

本机 `/home/lenovo/.local/bin/codex` 为 0.160.0，fresh `exec` 支持显式 `-m`、`-C` 和完整 stdin 任务边界；模型 cache 登记了 `gpt-6-luna` 和 High。尚未调用 Luna，实际服务可用性须在获批后的首次派发确认；不可用就报告，不能替换模型。

## Review Focus

| 最容易漏掉的边界 | 必须证明的行为 | 所属实施块 |
| --- | --- | --- |
| 移除 monitor 后丢失其原本承担的验证 | 完整 UUID/typed bytes、scope、时钟和 freshness 在主进程真实运行，错身份拒绝 | B、C |
| CUDA 迟到或旧 epoch completion | 过期丢弃不改变 target/lock；wrong identity fault；不复用帧或提前释放 owner | D |
| 可能发出 SDK 请求但没有 acceptance | 保留原始 400 ms claim 与 inventory，收尾全部未知 UUID，不回滚为未发出 | B、C、D |
| Python 已无 monitor，但 native 仍要求 revoker peer | 新 Head-only readonly mode 可用 main + primary-fault 启动；坏 provision fail closed | C |
| 日志齐全但停止或 OS rc 不可信 | raw stop 样本、cancel/close 对账、teardown、外部 rc 分别留证；SIGKILL 不伪造 seal | A、E、G |

## 调用链和逐项清理

下表中的 Python 路径均相对 `src/so101_demo_py/src/`。新增文件名是本计划提出的接口，尚未存在。迁移后用 import/call-site 搜索证明没有生产在线入口残留，不能只删测试让结果变绿。

| 当前链路/文件 | 阶段一处置及理由 | 迁回主进程/必须保留 |
| --- | --- | --- |
| `cli/head_feedback_bootstrap.py` → start_monitor、CONFIGURE/POLICY/PREARM/EXPOSURE ACK | 删除 Head 在线 bootstrap/测量 monitor 绑定和双流闭合；移出仍被使用的 raw capture/image writer。删除 `head_search_calibration.py` 的旧在线 bootstrap 子命令，其他测量命令按实际 caller 保留 | 停稳、exact Image/Info/TF/joint originals、SDK 记录、实际 installed transport |
| `adapters/act/head_primary_supervisor.py` | 用 `head_local_runtime.py` 取代生产入口；迁移完成后删除旧在线 supervisor | sticky fault、local watchdog、feedback/source deadlines、native readback、并行 cancel/local close、stop proof、未知 inventory |
| `adapters/act/head_monitor_ros.py`、`head_original_router.py` | observer 迁为 `head_local_observer.py`，router 指向本地 observer + writer + live owner；旧在线类删除 | 原始 joint/clock/action 回调、original sequence、非阻塞回调、有界记录 |
| `act/head_monitor.py`、`head_monitor_ipc.py` | 生产 canonical/hash/state 从 monitor 名称中抽出；`head_monitor_ipc.py` 的在线 codec/server 删除；历史 reader 必要兼容 helper 留在独立纯模块 | `head_evidence_identity.py` 纯 canonical/digest；`head_local_state.py` typed epoch/inventory/state |
| `adapters/act/head_monitor_process.py`、`head_monitor_runtime.py`、`head_monitor_exposure.py`、`head_policy_audit_worker.py` | 删除进程、心跳、RPC、ACK、CPU lease、在线 audit worker 及其 module 执行入口/无用配置 | 有效身份/inputs/result 校验先迁入 B/D；不留 success stub |
| `head_monitor_goal_binding.py` → `ros_execution.py` | 迁为 `head_goal_binding.py`，改共享 prepared SDK import；删除旧在线 binding 文件 | exact ROS CDR/typed goal/digest、role、bounded parse/deadline、serialization warmup。shared ACT 功能须保持 |
| `head_inventory_dispatch.py` | 删除 monitor identity、REGISTER/DISPATCH RPC；保留 native reserve→send 顺序 | generation/epoch/UUID/controller boot+incarnation、400 ms 原 claim、第二次 send guard |
| `head_live_exposure.py`、`head_inference_owner.py`、`head_owned_search.py`、`act/search.py`、`head_simulation_policy.py` | 将 stopped-demand 分支成为新组合唯一执行路径；拆除 live monitor 引用；不再轮询旧 continuous exposure 当作停点推理 | MOVE terminal + 三条停稳 originals、请求新帧、单 CUDA job、有限重观察/精调、三帧 lock、transactional commit |
| `adapters/act/head_stopped_capture.py` | 修改已存在的 capture；删除 `bind_measurement_monitor`、`_measurement_request` 和其 CALIBRATION_FRAME_INPUTS 等 RPC handoff/caller，保留真正被测量命令使用的原始停帧窗口 | 有界缓存、exact Info/Image pairing、原始 sink；绝不覆盖为新同名空模块 |
| `act/head_search_calibration_inputs.py`、`head_search_calibration_run.py`、`cli/head_search_calibration.py` | 正式 `run` 增加明确的开发 execution-inputs 分支，绑定真实资源；原八阶段 calibration 保持其合同 | 新分支使用同一 default composition，不凭 declaration-only binder 宣称资源已运行 |
| `act/head_search_restarts.py`、`head_search_production_smoke.py` | Head search 执行部分统一调用新 composition，停止采用 legacy `RosSearchAdapter`；提取其 `RestartStack` 生产 transport，保留旧 qualification receipts 语义 | graph/clock/camera/controller 原始检查、单 stack、teardown；开发首条不计 FULL_RESTART qualification |
| `act/head_search_binding.py`、`head_search_qualification.py`、`cli/act_stack_ready.py` | 增加新 controlled dependencies/policy 身份，旧 promoted/live bundle 拒绝；双流 seal 仅退出新执行准入 | 正式 qualification 不自动降级到 development；历史 reader 继续按原合同读旧 evidence |
| `act/head_search_teleop_acceptance.py`、`src/so101_teleop/so101_teleop/head_camera.py` | 新 descriptor 指向同一 owner，bridge 从 owner 收状态/目标/停止；本阶段做接口与拒绝用例，不开展视觉验收 | 单 CUDA owner，无 UI 二次 detector；桥不是 supervision ACK；视觉/人工审核后置 |
| `src/so101_demo_py/setup.py` | 核对 console/module 安装清单，移除废弃入口；新 copy install 不夹带旧 monitor 文件 | calibration/smoke/合法测量入口、实际包资产 |
| Head-only native controller/provision/readback | 见 C；拆除 Head monitor-required env、独立 revoker provisioning/lifecycle | main+primary-fault 的身份隔离、typed native gate、sticky close、共享 ACT 与原 ABI |
| `act/head_policy_audit.py`、`head_search_aggregate.py` 和历史 reader 测试 | 保留只读历史用途；新文件 protocol 不要求在线双 seal，旧历史格式不重写 | 历史证据的可复核性，不在此扩展正式阶段二 reader |

旧测试逐断言迁移：`test_act_head_monitor*.py`、`test_act_head_primary*.py`、`test_act_head_policy_audit_worker.py`、`test_act_head_bootstrap_monitor_closure.py` 中仅 monitor ACK/heartbeat/lifecycle/double-seal 准入用例删除；scope、typed bytes、callback I/O、freshness、fault、stop 和 inventory 负例移至新本地测试。保留历史 policy audit/aggregate reader 用例。B/E 收尾各交付一份 caller → 新 owner → 保留/删除理由表，具体 obsolete 文件列表写入 freeze receipt。

## 实施顺序及 Luna 的串行边界

依赖顺序为 A → B → C → D → E → F → G。它们是计划内实施块，不改动会话中固定的六项 task 列表。同一时刻一个 source/doc writer。每块派发 fresh Luna，不 resume/fork；结束后冻结写入，Sol 读 exact diff/source SHA、测试 argv/rc/证据后决定下一块。Luna 若重复失败两次或遇到复杂时钟、native、碰撞、ownership 问题，停在证据边界，给 Sol 最小复现；不得自行调整本计划阈值。

获批后用以下机制。`boundary-A.md` 等必须包含本计划和 spec 路径/哈希、允许文件、禁止事项、前置冻结 receipt、确切用例/命令、输出、停止条件。`codex --no-daemon exec --help` 先只读确认命令结构；若实际本机机制不接受 `--no-daemon`，先报告，不擅自借 daemon/resume。

```zsh
test -x /home/lenovo/.local/bin/codex || exit 1
/home/lenovo/.local/bin/codex --no-daemon exec \
  -m gpt-6-luna -c 'model_reasoning_effort="high"' \
  -C /data/work/ws_moveit/.worktrees/so101-head-file-protocol-1003 \
  --add-dir /data/work/so101-evidence/act-data/20260930-antzb-head-search-krIv681m \
  --json -o "$E/head-file-protocol-1003/dispatch/A-final.txt" - \
  < "$E/head-file-protocol-1003/dispatch/boundary-A.md" \
  > "$E/head-file-protocol-1003/dispatch/A-events.jsonl" \
  2> "$E/head-file-protocol-1003/dispatch/A-stderr.log"
```

Sol review 期间 Luna 进程必须已退出或停止写入，`review-input.json` 固定 git diff、全相关文件 SHA、installed provenance 和 evidence inventory。Review 后修改会生成新 receipt，并重跑受影响的定向 gate。当前审批仅批准实施边界；不自动提交继承 dirty，不 push。

### A：文件 writer 与真实测试来源

**Files:** 新增 `act/head_run_evidence.py`；修改 `adapters/act/head_original_journal.py` 与 bootstrap 中 image writer 的复用位置；新增 `test/test_act_head_run_evidence.py`。工具留在 `E/head-file-protocol-1003/tooling/prepare-stage1-test.py`，执行副本在 `L`；不把实验包装器变成产品审核框架。

**Interface:** `HeadRunEvidence.create(run_root, manifest, capacities)` 创建新目录；`append(kind, record, *, source_stamp_ns, observed_mono_ns, occurrence_mono_ns, artifact_refs=())` 非阻塞入队；`finish(completion)` 只在 producer/teardown 结束后 flush/fsync/封存。抛出的 writer fault 必须能进入本地停止路径。

- [ ] 新测试证明：JSONL 全局 sequence 连续；保留原 kind/record；null 与 0 区分；NaN/Inf 拒绝；source ns 与 monotonic ns 分列；异步 append 顺序不伪造 causal occurrence 时间。
- [ ] 定向 RED：实际收集并执行以上用例，失败于缺少行为；依赖/import/fixture 错误标 `INVALID_TEST_ENVIRONMENT`。
- [ ] 实现 `manifest.json/events.jsonl/artifacts/completion.json/seal.json`，manifest 在资源启动前写入并 fsync。单 writer 默认 event queue 4096 条、image queue 8 帧、单 event 1 MiB 上限，writer 调用不等待磁盘；限制、high-water、enqueue/write/fsync 延迟、fault/drop 计数写进日志。容量不足、enqueue 拒绝或 I/O 异常使 execution fault，不能静默丢证。
- [ ] original trajectory/image/metadata 只写一份，events 引用相对路径+大小+SHA。拒绝 symlink/path traversal/外部覆写；图片 raw bytes 与编码/尺寸/step 对账。新增 bytes manifest，不复制造出多份大帧流。
- [ ] 正常关闭顺序：停止新业务 dispatch/帧请求并收束 CUDA owner → cancel/close 与 raw stop proof → owned stack teardown → 关闭所有原始 observer/event/image producers → join/flush writer → completion fsync → SHA readback → 同目录临时 seal 原子 rename → parent fsync。stop/teardown 期间原始 observer 和 writer 必须继续记录，不能提前关掉停止证据。seal 不 hash 自身。完成后不修改 run tree。
- [ ] GREEN 还需 overflow、ENOSPC/写异常、尾行撕裂、completion/rename/fsync 中断用例；故障不得伪造完整 seal。外部 OS rc 不由 completion 冒充。
- [ ] 新包装器 snapshot 本 worktree 的 active source/tests，明确 package shim 与 PYTHONPATH，输出实际 import `__file__`/SHA。旧 `/tmp/.../prepare-dispatch-test.py` 引入的 runner 硬编码旧 worktree，禁止原样复用。每次新 scratch readback 并留 argv、elapsed、rc、JUnit。

### B：本地状态、typed inventory 和安全权限

**Files:** 新增 `act/head_evidence_identity.py`、`act/head_local_state.py`、`adapters/act/head_goal_binding.py`；修改 `head_inventory_dispatch.py`、`ros_execution.py`、`head_simulation_policy.py`、`act/head_feedback.py`；迁移相应 monitor helper；新增 `test_act_head_local_state.py`、`test_act_head_local_goal_binding.py`，修改现有 inventory/prepared SDK/feedback 测试。

**Interface:** `HeadLocalState(scope, search_deadline_ns)` 持有唯一 epoch/inventory/motion_epoch；`register_prepared(record, typed_goal_bytes)` 完整验证后保存；`mark_sdk_attempt(uuid, occurred_ns)` 在可能 send 的边界标记；`claim_state(uuid, now_ns)` 使用原固定期限；`fault(reason, evidence)` sticky。`validate_goal_inventory(...)` 中性命名，保留原 exact CDR 校验语义和有界 parse。

- [ ] RED：wrong UUID/CDR digest/generation/controller incarnation/boot/role、scope 重用、双 reserve、假 receipt 均拒绝；deadline 到边界拒绝；一次可能 SDK send 后超时不会删 inventory 或重置 400 ms。
- [ ] 单一 owner 同步登记 originals；移除 REGISTER/DISPATCH ACK。native reserve 前及 actual SDK send 前分别验证 local guard。只在确认从未 send 且从未 reserve 的边界允许撤销 prepare；可能 send 的所有 UUID 都进入 stop 对账。
- [ ] 新 policy schema 2 去掉 `heartbeat_rpc_timeout_s/supervision_stale_s`，mode 使用 `mujoco_bounded_stop_search_file_v1`，其余候选值在“冻结输入”列明。schema 1 仅历史 readback，不进入新生产执行默认 fallback。feedback 的 8 个 local budget 与实际 policy 精确一致，哈希随版本改变。
- [ ] 保留 position/velocity/acceleration、原始 feedback 和 SDK native acceptance 权限。GREEN 覆盖 shared ACT prepared SDK 原 ABI 与原 native timeout，防止 Head 清理影响 ACT。
- [ ] 将每条旧验证的 caller 和迁移后执行位置写入迁移表，再删除旧 online helper/call-site；不得留下空验证返回 True。

### C：Head-only native provisioning 和完整轨迹/碰撞

**Files:** 修改 `src/so101_mujoco_support/src/broker_owned_trajectory_controller.cpp`、`src/so101_mujoco_support/include/so101_mujoco_support/broker_owned_trajectory_controller.hpp`、同包 `src/controller_reservation_socket.cpp`（仅新 mode 分支确有必要时）、`test/test_broker_owned_trajectory_controller.cpp`、`test/test_controller_reservation_socket.cpp`、`test/test_head_revocation_transport.cpp`；修改 Python `controller_reservation_provision.py`、`head_native_policy_readback.py`、Head-only `ros_neck.py` prepared trajectory 构造；新增 `adapters/act/head_trajectory_guard.py` 与 `test_act_head_trajectory_guard.py`。共享 ACT 原路径不改。

**Interface:** 新 readonly `head_simulation_mode=mujoco_bounded_stop_search_file_v1`，`head_fault_connection_timeout_ns=50000000`。main 和 primary-fault provision 绑定相同主进程 PID/start ticks、不同 capability；新 Head mode 不要求独立 revoker peer。`validate_head_trajectory(prepared, snapshot, safety_inputs)` 返回完整 q/v/a extrema、路径及输入 SHA；拒绝时没有 reserve/send。

- [ ] native RED：现代码在没有 monitor-required env/revoker peer 时拒绝本地模式；测试必须真正到 controller init/configure/provision 边界，缺 underlay 不是 RED。
- [ ] 新 Head mode 移除 `SO101_HEAD_SEARCH_V2_MONITOR_REQUIRED` 强门及 Head 独立 revoker env/provision；保留 main/primary-fault 自身 provision 校验、wrong PID/ticks/capability/type 拒绝、readonly descriptor/current readback、owner loss sticky gate close。空 mode、共享 ACT provision 和原 ABI 2 ms 行为保持。
- [ ] 删除仅旧 Head 使用的 revoker provision writer 和配置；不因 Head 不再调用而删除共享 native REVOKER 能力。生成新 controller YAML；arm/gripper 不增加 Head 模式。
- [ ] 新 Head-only prepared goal 在已经停稳的起始反馈上生成首尾零速度/零加速度的单调 quintic；生成前检查实测残余速度不超过停稳阈值，并把实测到计划首点的差异纳入首段校验。将 header、完整 positions/velocities/accelerations/time_from_start 纳入 typed bytes。局部 position-only 0.1 s 线性端点 guard 无法证明加速度边界，不能继续使用。
- [ ] 本计划新增的开发仿真 safety 候选：URDF neck velocity 上限 1.0 rad/s；显式更保守 `max_velocity_rad_s=0.5`、`max_acceleration_rad_s2=0.5`；位置受 geometry safe interval 限制；duration 至少 0.1 s、至多 5 s，并按 quintic q/v/a extrema 计算最短合法时长，容纳当前实测起始速度。超过 duration/search budget 就拒绝；不 clamp 提高限位。现 joint_limits.yaml 未定义 neck acceleration，这两个开发值随本计划审批，不能假称历史测量值或硬件限值。
- [ ] 碰撞策略明确冻结：当前 scene/model closure，protected root `base`，allowed pairs 空集，`path_step_s=0.002`、`path_clearance_m=0.001`、最多 50000 samples。复用 `MujocoNeckSweepChecker` 的私有位置阶段校验，并让 Head wrapper 按实际 quintic 轨迹时刻重放；使用同一 simulator 的最新完整 qpos，不以 neck 单角度代替其余机械臂/杯状态。任一接触/未知 geom/模型不符/预算耗尽拒绝。若 baseline pose 出现保护接触，停给 Sol；不得临时扩大 whitelist。
- [ ] GREEN：端点合法但 spline overshoot、速度/加速度超界、中途碰撞、陈旧 snapshot、模型 bytes 与 semantic hash 混淆全部拒绝；合法 trajectory exact bytes 在 native reserve 与 SDK 一致。模型 semantic hash 在实际加载后冻结，XML SHA 不能冒充它。
- [ ] 可靠 stop 保留 cancel、local primary-fault native close 与三条 advancing raw velocity proof。native gate closed/owner loss/进程退出都不能单独充当物理停止证明。未证明停止就 fault 并禁止下一 run。

### D：停点新帧、单 CUDA owner 和有限状态闭环

**Files:** 新增 `adapters/act/head_local_runtime.py`、`head_local_observer.py`；修改 `head_original_router.py`、`head_live_exposure.py`、`head_inference_owner.py`、`head_owned_search.py`、继承 `act/search.py`；新增本地 runtime/observer 测试，修改 stopped exposure/owner/owned search/stopped policy/feedback/action callback 测试。

**Interface:** `HeadLocalRuntime` 提供 `dispatch_guard/own_inventory/fault/stop/close`，不接受 MonitorProcess。`HeadInferenceOwner.request_observation(request)` 与 `next_completed_observation(after_sequence)` 是唯一推理通道。`OwnedHeadSearch.tick()` 驱动 `MOVE/SETTLE/OBSERVE/VALIDATE/REOBSERVE/FINE/LOCK/STOP` 并产生日志。

- [ ] RED：无 monitor 对象也能建立完整 runtime；初始 active=None 不能凭空当作停稳；旧完成帧/同帧三次消费不达成 lock；不可在 MOVE 中推理。
- [ ] MOVE 的 terminal 必须有 status=4/error=0 并对账原 UUID。其后至少三条 source stamp 与 receipt 均 advancing 的原始 feedback，符合目标位置容差与速度阈值；由最后一条定义 settled source/monotonic floor。
- [ ] OBSERVE 固定 request scope/gen/policy hash/motion_epoch/observation sequence/settled floors/search 原 deadline。严格请求停稳后新 frame，pair exact Image/CameraInfo stamp/frame/dimensions；TF/joint 是对应原始有效数据，source 与 receipt age/skew 分别检查。
- [ ] worker 仅加载一次指定 weights，实际 device `cuda:0`，无 CPU fallback；capacity=1。记录 capture/request/frozen-pair/job-start/CUDA-start/end/result-return/consume 各时刻。job 原期限 1 s 与 consume age 150 ms 分别判定；CUDA 尚未返回时不按 lease 超时启动第二 job。
- [ ] VALIDATE 在任何 target/lock 提交前再次检查 scope/epoch/job 身份及 age。合法但过期 completion 丢弃且 target/lock 不变，可按原预算重观察；错身份/future clock/逆序 hard fault。一次 move 后 motion_epoch 递增，旧完成结果不能影响新 epoch。
- [ ] 每停点最多 3 次、总计最多 12 次额外重观察，只允许 MISS/EXPIRED/SHORT_DROP，使用原始 30 s search cap，不因重试重置。精调最多 2 次、总角度不超过 0.6961197054865531 rad。三帧锁定要求三个不同、严格 advancing 且有效的 originals，同 track、center/deadband/vertical/面积/置信度均达标，期间失配按明确规则断开连续计数。
- [ ] STOP 在成功、not-found、budget、feedback/camera/clock loss、writer fault、UNKNOWN、SIGTERM 等路径统一 inventory 对账；local cancel 与 native close 不能互相阻塞。未能停止或 teardown 为执行失败。
- [ ] CUDA 不能协作退出时，local stop 仍按原预算独立推进；owner quiescence 单独失败，不无限 join，也不重新加载另一模型。留下实际阻塞/停止证据，run 不报成功；若外部最终强制结束，只记录真实 OS rc/残缺文件。文件协议不补足同进程卡死的在线保障。
- [ ] GREEN 覆盖 recoverable expiry 不降低阈值、耗尽终止、错 identity sticky、late callback、writer故障、CUDA 超期、shared ACT 行为；删除已迁移的在线 runtime/monitor 生产文件与旧纯在线合同断言。

### E：同一真实正式/default composition 与 Teleop 接口

**Files:** 新增 `adapters/act/head_execution_composition.py`、`act/head_execution_inputs.py`；修改上方 calibration/run/binder、restarts、production_smoke、binding/startup、qualification/Teleop descriptor、setup.py；修改已有 `adapters/act/head_stopped_capture.py`，必要时从 bootstrap 抽出 `adapters/act/head_image_artifacts.py`。新测试 `test_act_head_execution_composition.py`、`test_act_head_execution_inputs.py`；更新现有 calibration CLI、restarts、smoke、binding、startup、Teleop/shared descriptor 测试。

**Interface:** `HeadExecutionInputs.parse(path)` 严格读 closed schema；`run_head_execution(inputs, *, evidence)` 入口一次 bind stack/native/observer/writer/model。开发分支为 **计划新增** `so101_head_search_calibration run --execution-inputs <absolute-json>`，与 legacy eight-phase flags 互斥；不能声称该 flag 当前已有。

- [ ] RED：现 `run` 无 execution-inputs，binder 仅登记；测试要求真正调用一次 stack/native/CUDA owner 的资源工厂且 default/smoke 用同一组合。development config 无法进入 promoted/qualify/正式 Teleop acceptance。
- [ ] 输入 schema 明确 `execution_scope=MUJOCO_DEVELOPMENT_UNQUALIFIED`，closed fields 包含 run/session/gen/epoch、evidence root、新 run root、freeze receipt ref+SHA、weight/frozen-c/geometry/config/policy/controller/plugin/scene/URDF/safety refs+SHA、development scene pose、CPU/GPU allocation、ROS domain/environment。拒绝缺字段、错 SHA、未知 scope、重用 root/runid、路径逃逸和混合旧 phase flags。
- [ ] `RestartStack` 提供 installed production transport（一个 ros2_control_node、camera plugin、robot_state_publisher、四 controllers），仍记录实际 argv/参数和 graph。Head loop 换成 D，default/smoke 不另建模型或 monitor。旧 qualification restart 的“恰好三个 anchor 各一次”合同保持，开发首条另用 operation，不输出资格 receipt。
- [ ] 启动前 source/installed controlled dependencies、policy/schema、native readonly readback 一致；旧 bundle 不兼容明确拒绝。不把历史 dual-seal 要求留在新 execution 准入，也不删除历史 reader 对旧格式的校验。
- [ ] Teleop contract 仅复用同 owner descriptor/bridge、目标和停止；测试断言无二次 detector/在线 monitor。没有人工批准的新 digest 不可发布正式 qualified UI。视觉验收后置。
- [ ] GREEN 后完成逐文件清理表和 fresh install inventory：删除旧 bootstrap/monitor 导入、env、CLI/module 入口、双 seal 硬门；shared ACT/native 和历史 reader 保留。全文搜索在线 token 在 production reachable path 的结果逐条解释，允许历史 reader/docs 字面量，不以 grep 零结果冒充语义验证。

### F：集成 gate、copy install 与冻结

- [ ] 再查 executable、underlay、package closure、pytest plugin、Python package origins。精确 test Python 当前为 `/data/work/venvs/so101-v5-t004-perception/bin/python3`；ROS 为 `/opt/ros/jazzy`；colcon 当前 `/usr/bin/colcon`。不是可运行就立即停止并记录环境问题。
- [ ] 每块定向测试使用下方新 wrapper；本块才做 demo ordinary `test/`、Teleop ordinary 和受影响 native 的整门禁。不得收集 `benchmark_test/`。记录测试实际 interpreter 和 fresh tempfile readback；colcon CTest 若使用 `/usr/bin/python3`，也须用它证明 tempfile，不用 venv 的 readback 代替。
- [ ] fresh build/install 使用完整 dependency closure、copy install，无 symlink 指回 source。先 `colcon list --packages-up-to ...` 核验包集合和 setup，再构建；缺依赖/underlay/selection/override 先区分，不计 source RED。
- [ ] 读 installed CLI help、模块 origins、共享库实际 load path/SHA、配置/scene/include/mesh closure。删除的 online 文件不能残留 installed prefix。
- [ ] Sol review 冻结 exact source/diff、tests argv/rc 和新 install。若 ordinary 全套仍失败，列 baseline/new/shared 分类及影响；安全相关或引入回归阻止 runtime。已复现且无关的继承失败保持 OPEN，只可作为未资格化开发运行限制，不能称 package gate PASS。
- [ ] 产生 `freeze.json`，含 source 文件 SHA、dirty diff SHA、所有 installed files/二进制/版本、config/policy/安全输入 bytes 与 canonical SHA、ROS/domain/GPU、所有实际 argv 和 test receipts。freeze 改变就新 freeze/new run ID。

### G：首条真实闭环、全日志分析与交接

- [ ] Sol 验证 runtime ownership 的 fresh host ps、tmux、GPU、Docker 与 `ros2 node list --no-daemon`；权限拒绝用获准只读 host 访问复查，不能判定资源不存在。选择无 foreign owners 的 ROS domain，固定在 execution-inputs 中。存在旧 stack 就停止，不能擅杀或开第二 stack。
- [ ] 先完成本计划的正常真实首条 run，按下方 installed formal 命令。初始化使用已声明的 development pose，不计 held-out/anchor qualification。搜索必须至少一次 native admitted MOVE，随后三条真实停稳 feedback、新帧 CUDA 推理、允许的精调/重观察、三帧 lock、可靠 stop。零 send、拒绝或 not-found 只能记录失败/问题，不能当目标完成。
- [ ] 外层 wrapper 留真实 child PID/start ticks、argv/env/时间/实际 OS rc；inner completion 写业务结果和 intended rc。封存后 wrapper 写 `launcher-result.json`，位于 run tree 外。SIGKILL/timeout 可有残缺日志；不补造 seal 或 completion。
- [ ] 首条结束后，Sol 回读 **全部** manifest/events/artifacts/completion/seal、stack stderr、CUDA/device、trajectory/SDK/native、writer、stop、外部 rc、ownership/teardown 日志。先 hash/完整性，再原 occurrence 时序；每个 UUID、motion epoch、observation job、frame、lock 证据关联。不能只挑成功片段或只统计 rc。
- [ ] 写 `E/reviews/<run-id>/<audit-id>/review.json` 与 `review.md`：execution result、seal integrity、audit findings、qualification=NOT_QUALIFIED、完整性缺口、异常/丢帧/过期/reobserve/精调原因与计数、各边界延迟、unknown inventory、最终 target/lock/stop、stderr 所有问题的归类和 next action。这是本次协调者回读，不宣称阶段二程序已实现。
- [ ] 首条暴露问题时先在该 run 完成分析，再由 Sol 分解最小修复边界派 Luna；改源码/config/policy 后重新 gate/freeze，用新 run ID，不覆盖已封存日志。反复超期/碰撞/native 问题交 Sol，不调低门禁。
- [ ] 正常首条和分析后，串行补做本地安全关键失效实跑：暂停本任务的输入订阅以触发 camera/feedback loss（不得关掉 stop 的独立 raw observer），以及受控丢失 SDK acceptance 回调以产生 UNKNOWN；实际 native goal 不绕过校验。每次完整 stop/teardown/readback，测原预算，不扩成未来完整故障审核矩阵。无法安全实现注入就保持该门 OPEN 并报告，不伪造 mock 作为实跑。
- [ ] 阶段一完成要同时具备真实首条成功、全部日志问题清单/处置、必需本地停止证据、冻结安装一致性和保留 inventory。否则交接准确写 execution/audit 状态及未完成边界。首条成功不将 qualification 改为 QUALIFIED。

## 冻结输入、SHA 和第一条实跑命令

已核验的输入如下。`E` 是上文绝对路径的缩写，输入 JSON 中写绝对路径。

| 输入路径 | 当前 bytes SHA256 |
| --- | --- |
| `E/head-yolo-models-20260930T120608Z/candidate-c2a/head-task-mixed-taskweighted/weights/best.pt` | `2afd550694abfbe6d1c37922c9ea0b4a0f8567bef94cf4c4ec85d4b50c0cc82a` |
| `E/head-yolo-models-20260930T120608Z/reselected-c2a/frozen-c.json` | `f50b8d928d4ea0fd9d0e62766bdcadf163223165acf1351cbcb019200aa3f657` |
| `E/head-camera-probe11-20260930T101722Z/head-camera-geometry.json` | `0db2eb4c8a0cfe55b77044c499bb644c5d8f8e9f17f1c9780d6b15609f56c8e6` |
| `src/so101_demo_py/assets/mujoco/act/head_search_scene.xml` | `aea2df3b0bfb608d7d3aec2e58cd8f45b51affd8bf92511de5e99475fcc47f14` |
| scene include `assets/mujoco/act/so101.xml` | `d8665bb90bf8d4b47f2a75dbf8147094464b82a69a7e57da30a77c5858c7903c` |
| `assets/mujoco/act/so101.urdf` | `1b27e65bd51baa6726468ac5d4b33be9c4fe43551f6b6c3e9cba1849ac98081b` |
| `config/mujoco/act/mujoco_plugins.yaml` | `6a030c48fe4829803bd4e2ed980adbe53217ef39b271c274286081830eaf7aac` |
| base `config/mujoco/act/ros2_controllers.yaml` | `3fb75699c7b42c51badfed6ed3a616418901ea853d5c58b91e07b377414f2ab2` |
| old `config/mujoco/act/head_search_v2.json` | `3fb9f27646b6e314fc30fe2892f6b1c3d44b068f4c6614df8f7de3c5add2ffd9` |

F 将在 `E/head-file-protocol-1003/freezes/<freeze-id>/inputs/` 生成下列明确候选，完整 bytes、canonical SHA 与解析器 readback 都进 freeze。当前不写产品 config，也不假造未来 binary/input SHA：未来 `execution-inputs.json`、controller YAML、safety/model closure 的 SHA 必须由冻结后的实际 bytes 取得，填入 `launch-command.json` 后才允许运行。

1. `development-config.json`：从上述旧 config 深拷贝，改 schema_version=3、runtime_id=`head-file-protocol-dev-v1`、execution_scope=`MUJOCO_DEVELOPMENT_UNQUALIFIED`，增加 required_search_domain_rad=`[-0.17559216195018026,0.08047101126546086]`，values.max_age_s=0.15、search_timeout_s=30.0、stop_latency_s=1.0；tracker.iou_threshold=0.5 与 values.tracking_iou/frozen-C 一致，candidate_identity_sha256 改为 frozen-c 当前 SHA。其他值逐字段保留。采用 `json.dumps(ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n'` 的未来 bytes SHA 为 `875f9aefc8d0153928e51e3b4f330b71565d9e47d34ba800c521939443643a36`。这是拟批准的开发候选，不是重新校准的正式配置。
2. `local-policy.json`：schema_version=2、mode=`mujoco_bounded_stop_search_file_v1`；watchdog_period_s=0.02、fault_reaction_limit_s=0.25、native_close_timeout_s=0.05、stop_confirmation_timeout_s=1.0、perception_max_age_s=0.15、perception_job_timeout_s=1.0、camera_loss_timeout_s=0.5、feedback_receipt_timeout_s=0.25、joint_source_age_s=0.05、camera_source_age_s=0.2、search_timeout_s=30.0、max_reobservations_per_stop=3、max_reobservations_total=12。去掉两个 online budget 字段；仍验证 local watchdog/fault/close/stop、age/job、retry/total 的关系。按上一项相同序列化方式的拟议 bytes SHA 为 `d246828d0b77a7ef89b51bc74819ce63ea110dbbaf2542b0a6ea4559b85c598d`。
3. `ros2-controllers-file-v1.yaml`：只在 neck_controller 的 ros__parameters 增加 C 的 readonly mode/50000000 ns；保留其他原字段。输入同时固定 real parameter descriptors/readback。
4. `safety-inputs.json`：C 的明确仿真限值、采样/clearance、base/空 allowed pairs；包含 scene/include/mesh bytes closure 与实际 model semantic hash，URDF 和 snapshot joint/free-body 映射。缺项拒绝。
5. `execution-inputs.json`：operation=`HEAD_FILE_STAGE1_DEVELOPMENT`，全新 run/session/epoch/generation，scope=开发未资格化；初始化 arm 六值 `[-0.25,0.0,0.6,0.8,0.0,0.8]`、neck=0.1、杯 `[0.02,-0.28,0.165]`。搜索首个 bounded target 为 required domain 下端 `-0.17559216195018026`，其位置/路径/预算须 C 批准，保证真实 MOVE 后再观察；不能在初始 pose 直接用旧帧宣称 MOVE 闭环。cup body、qpos 和 placement receipt 均来自同一 stack。这个 development case 不读取 held-out 用作调参。

### 测试命令合同

以下 wrapper 和参数是 A 要实现的任务工具，当前禁止执行。wrapper 必须拒绝已存在 test-id，创建 scratch，env readback 后才启动精确 pytest。所有测试落在实际本 worktree、测试 snapshot/imports；没有 silent old-worktree fallback。

```zsh
export E=/data/work/so101-evidence/act-data/20260930-antzb-head-search-krIv681m
export L=/tmp/so101-debug-head-file-protocol-1003
export HFP_PY=/data/work/venvs/so101-v5-t004-perception/bin/python3
test -x "$HFP_PY" || exit 1
HFP_TEST_ID="hfp-A-red-$("$HFP_PY" -c 'import uuid; print(uuid.uuid4().hex[:12])')"
"$HFP_PY" "$L/prepare-stage1-test.py" \
  --worktree /data/work/ws_moveit/.worktrees/so101-head-file-protocol-1003 \
  --evidence-root "$E" --test-id "$HFP_TEST_ID" \
  -- src/so101_demo_py/test/test_act_head_run_evidence.py
```

wrapper 内必须实际执行并保存：

```python
assert os.environ['TMPDIR'] == os.environ['TMP'] == os.environ['TEMP']
assert Path(tempfile.gettempdir()).resolve() == expected_new_scratch_tmp.resolve()
# 再运行同一个 sys.executable -m pytest -q <明确 test 文件> --junitxml=<receipt>
```

RED 预期 rc1，非零 collection、明确 behavioral failure；GREEN 预期 rc0、无未解释 skip。ordinary demo/Teleop 使用分开的 fresh test-id、明确各自 `test/` 路径，按每 module `-n min(8,os.cpu_count())` 合同验证 xdist 实际参与，不跨 module 同时占 GPU/runtime。benchmark 不收集。native CTest 前同样确认生成命令的实际 interpreter/fixture scratch。

每块都通过上述 wrapper 的 `--` 后传入明确文件，不使用宽泛 `test_act_head*` glob。定向集合为：

| 块 | `src/so101_demo_py/test/` 下的具体测试文件 | 必须实际观察到的 RED → GREEN |
| --- | --- | --- |
| A | `test_act_head_run_evidence.py`、`test_act_head_original_journal.py`、`test_act_head_action_callback_io.py` | writer/closure 不存在或不满足 → 有界、断电/故障语义与连续原记录通过 |
| B | `test_act_head_local_state.py`、`test_act_head_local_goal_binding.py`、`test_act_head_inventory_dispatch.py`、`test_act_head_prepared_sdk.py`、`test_act_head_simulation_policy.py`、`test_act_head_feedback_freshness.py` | no-monitor dispatch/新版 policy 拒绝 → 本地验证成功且坏 typed/scope/UNKNOWN 拒绝 |
| C | `test_act_head_trajectory_guard.py`、`test_act_head_native_policy_readback.py`、`test_act_head_primary_fault_provision.py`、`test_controller_reservation_provision.py` | 新 mode 或完整路径行为失败 → 新 Head local mode 与旧共享能力各自通过 |
| D | `test_act_head_local_runtime.py`、`test_act_head_local_observer.py`、`test_act_head_stopped_live_exposure.py`、`test_act_head_inference_owner.py`、`test_act_head_owned_search.py`、`test_act_head_stopped_search_policy.py`、`test_act_head_original_router.py` | continuous/online 路径违约 → 完整 stopped-demand 状态序列与错误路径通过 |
| E | `test_act_head_execution_composition.py`、`test_act_head_execution_inputs.py`、`test_head_search_calibration_cli.py`、`test_act_head_search_restarts.py`、`test_act_head_search_production_smoke.py`、`test_act_head_search_binding.py`、`test_act_head_search_startup.py`、`test_act_task8_head_search_descriptor_shared.py`、`test_act_head_search_teleop_acceptance.py` | declaration-only/旧入口拒绝或分裂 → 单资源组合、旧资格拒绝与共享接口通过 |

C 的 native 定向 RED/GREEN 仅构建并执行上述三个 C++ test target 中的新 mode/provision/close 用例；记录实际 CTest 注册名称和精确 `ctest -R` argv。整包 native gate 留到 F，不在每个块反复运行。初次发现名字/target 不符先核验 CMake/CTest，再运行 intended boundary。

完整 closure 的构建命令模板如下；`HFP_FREEZE_ID` 为 F 在新目录注册的 freeze ID，不能复用旧 install。

```zsh
set -o pipefail
source /opt/ros/jazzy/setup.zsh
test -x /usr/bin/colcon || exit 1
/usr/bin/colcon list --packages-up-to so101_demo_py so101_teleop
/usr/bin/colcon --log-base "$E/head-file-protocol-1003/freezes/$HFP_FREEZE_ID/build-log" build \
  --packages-up-to so101_demo_py so101_teleop \
  --build-base "$E/head-file-protocol-1003/freezes/$HFP_FREEZE_ID/build" \
  --install-base "$E/head-file-protocol-1003/freezes/$HFP_FREEZE_ID/install" \
  --event-handlers console_direct+
build_rc=$?
test "$build_rc" -eq 0 || exit "$build_rc"
```

必须先核验 closure 包清单包含 support、MuJoCo plugins/control/messages 及所需依赖；发现缺失则显式补足 underlay/selection 后再构建，不把初次 setup missing 算 source regression。记录实际 Python/shebang；不能只用 venv Python 的可执行证明推断 colcon fixtures interpreter。

集成 gate 使用同一 fresh install。F 的工具为每条命令生成全新 scratch，并在调用前让实际 CTest/pytest interpreter 逐一 readback：

```zsh
export TMPDIR="$E/scratch/$HFP_TEST_ID/tmp" TMP="$E/scratch/$HFP_TEST_ID/tmp" TEMP="$E/scratch/$HFP_TEST_ID/tmp"
# 新目录由 wrapper 独占创建；这里的 ID 每条 gate 更新，不能复用 A 的 ID。
# 对生成的测试 command 中每个实际 Python 运行 tempfile proof；否则 fail closed。
/usr/bin/colcon --log-base "$E/scratch/$HFP_TEST_ID/test-log" test \
  --build-base "$E/head-file-protocol-1003/freezes/$HFP_FREEZE_ID/build" \
  --install-base "$E/head-file-protocol-1003/freezes/$HFP_FREEZE_ID/install" \
  --packages-select so101_demo_py --pytest-args test
test_rc=$?
/usr/bin/colcon --log-base "$E/scratch/$HFP_TEST_ID/result-log" test-result \
  --test-result-base "$E/head-file-protocol-1003/freezes/$HFP_FREEZE_ID/build" --verbose
result_rc=$?
```

Teleop 单独新 ID 后同样命令改为 `--packages-select so101_teleop --pytest-args test`；support native 单独新 ID 后改为 `--packages-select so101_mujoco_support` 并去掉 `--pytest-args test`。ordinary module 的 xdist 命令与整包 colcon receipt 一起保留；记录真实 collection，避免 Teleop CTest 以目录参数追加造成漏收。相关 MuJoCo dependency 若实有改动或 native load 集成影响，再定向执行其 gate；不在每个 B/D 小修改后跑整套。`test_rc`、`result_rc` 必须分别检查；test-result rc0 不能抹去 test rc1。不使用 ament_uncrustify --reformat。

### 正式 installed 实跑命令合同

外层 `launch-head-stage1.py` 是 E/G 要形成的有限任务包装器：读取 freeze/input SHA、启动 **唯一** installed formal child、记录 rc；不扮演在线监督器，不做 ACK/heartbeat，不实现阶段二 audit。它不拥有业务动作。业务 run 自己拥有 stack 和 local stop。包装器可记录/转发外部终止信号，无法以文件日志保证防卡死。

```zsh
source /opt/ros/jazzy/setup.zsh
source "$E/head-file-protocol-1003/freezes/$HFP_FREEZE_ID/install/setup.zsh"
HFP_INPUTS="$E/head-file-protocol-1003/freezes/$HFP_FREEZE_ID/inputs/execution-inputs.json"
HFP_FORMAL="$E/head-file-protocol-1003/freezes/$HFP_FREEZE_ID/install/so101_demo_py/lib/so101_demo_py/so101_head_search_calibration"
test -x "$HFP_FORMAL" || exit 1
test -f "$HFP_INPUTS" || exit 1
"$HFP_FORMAL" run --help
"$HFP_PY" "$L/launch-head-stage1.py" \
  --freeze "$E/head-file-protocol-1003/freezes/$HFP_FREEZE_ID/freeze.json" \
  --inputs "$HFP_INPUTS" \
  --launcher-root "$E/head-file-protocol-1003/launchers/$HFP_RUN_ID" \
  -- "$HFP_FORMAL" run --execution-inputs "$HFP_INPUTS"
run_rc=$?
```

`launch-command.json` 在启动前记录以上展开后的绝对 argv、实际 interpreter/shebang、working directory、env（含 `MUJOCO_GL=egl`、唯一 ROS domain、CUDA device/no CPU fallback）、正式程序/imports/native .so/全部输入 SHA。wrapper 只在 SHA 精确匹配时启动。正式 child 通过 production `RestartStack` 起实际 installed node/spawner；每个真实 child argv、父子 PID/start ticks、ROS parameters、provision身份、CUDA owner/device 都进 manifest/artifacts。

预期 rc：开发成功且 stop/teardown/seal 全部完成为 0；合法执行的 not-found/budget/safety/writer/runtime/stop/teardown failure 为 1；输入/环境/ownership 拒绝为 2。SIGTERM/其他外部退出实际 rc 由 wrapper 原样记录，不能重编码成完成。Python `subprocess.returncode=-N` 与 shell `128+N` 如同时出现，明确记录不同表示。业务 intended rc 与真实 OS rc 不一致时 audit 报问题。

预期产物为新 run 的五类 protocol 文件、raw Image/Info/TF/joint/SDK/controller/轨迹与 SHA refs、placement/ready/stop/teardown receipts；外部 launcher 目录有 rc、stdout/stderr、启动与退出 host snapshots。原始 stop 至少三条 advancing feedback、所有可能 SDK UUID 的 cancel/terminal/unknown 对账及 sticky close readback。teardown 是 owned child 全退出、fresh graph 无本任务节点、GPU 无本任务 owner、native generation 关闭；外部 residual 单列，不能误杀。

若 source/installed 或 inputs 改动，上面全部 future SHA 重新冻结；已运行的 run 永不改写。当前只有已核验历史输入与拟议 config SHA，尚无未来 freeze/installed binary SHA，命令不具备执行授权。

## 全日志分析与后续资格门

协调者按 run 的 evidence inventory 逐文件读回，列举每个问题的原始 event sequence/UUID/frame/job/path，至少给出时钟、motion、settle、freshness、CUDA、finite retry、lock、native、writer、OS exit、stop/teardown 十一个类别的结论。未出现的类别写“没有事件及原因”，不能当已测 PASS。解释所有 stderr、缺失记录和 counter 非零；记录实际首条是否确实经历 MOVE 与三帧 lock。

execution 的成功只陈述运行行为；audit 的结果陈述完整性与观察到的问题；qualification 始终 `NOT_QUALIFIED`。后续整体门仍包括新的 40 held-out、default/left/forward 各一次独立 FULL_RESTART、Teleop 原始/overlay 视觉验收、模型比较、人工 numeric digest 批准，以及 ACT exact-W8/40 和尚未闭合的 ordinary/native/shared 边界。当前单模型开发成功不能代替任何一项。

保留 inventory 在每次 checkpoint 更新：新 baseline、dispatch、freeze/build/test receipts、封存 run、launcher、reviews 均 retained；archived 仅记录实际迁存的旧批次，不凭空宣布已 archive。readback 后 scratch/build临时文件/private IPC 列 deletion candidates，保持原路径，不删除。历史证据、旧 worktree 和交接持续保留。

## Inline self review（Sol，计划阶段）

- [x] fresh process、branch/HEAD、继承 dirty、505 manifest、历史 ledger 只读关系已核验；新账本独立，没有旧 goal 授权延续。
- [x] 找到并纳入 Python monitor 与 native 独立 revoker 双重依赖；C 的新 Head-only mode 保留 shared ACT 权限，未设计总成功 ACK。
- [x] 明确 formal binder 目前只是声明、default 为 continuous adapter；E 改为真实单 composition，开发 execution-inputs 与正式资格链有显式隔离。
- [x] 修正旧测试模板 import 旧 worktree 的 provenance 缺口；A 新 wrapper 必须 exact import readback，环境失败不算 RED。
- [x] 明确旧 config tracker 0.3 与 frozen-C/values 0.5 的冲突，拟议 candidate 身份与 0.5 同步；开发时间预算不冒充正式重新标定。
- [x] 发现 neck acceleration 缺少明确输入、0.1 s 线性端点 guard 不足；C 明列拟审批仿真限值、quintic/path/碰撞合同，拒绝阈值自动降档。
- [x] 区分 inference job deadline 与结果 consume age，未知 acceptance 保留原 400 ms，旧 epoch/过期结果不先修改 lock/target。
- [x] file writer bounded/overflow/fault/fsync/atomic seal、真实外部 rc、stop/teardown 各有边界；日志从不声称独立防卡死。
- [x] 首条 installed MuJoCo/CUDA 在 G 实跑，然后回读全部日志并列问题；mock/UT/source GREEN 不等于运行完成。后续 qualification 与阶段二审核程序后置。
- [x] 只允许审批后 fresh `gpt-6-luna` 串行实施，Sol review 冻结；本轮未派发、未测试、未仿真，模型 service 可用性没有提前宣称。

审查结论：计划可供用户审批。实施新增的开发 execution-inputs 分支、Head-only native mode、quintic 仿真安全候选和文件 writer 均属于本计划明确边界。尚未具备 runtime/freeze 证据；具体 implementation、测试和仿真必须等用户明确批准。本轮不提交或执行以上 checkbox 工作。
