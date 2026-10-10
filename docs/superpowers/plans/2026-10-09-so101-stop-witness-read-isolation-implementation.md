# SO-101 Stop Witness Read Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. CP-HFP-940/944 已选定 root 原生单人实施，完成后由一名全新 GPT-6 Astra / High 审查；不重新选择执行方式。root 是唯一实验账本写者。

**Goal:** 让 500 Hz `observe()` 不受停止证明读者持锁影响，同时让任何取不到一致快照的 PREARM 或 ARM 证明明确拒绝。

**Architecture:** 控制器保留写者私有环，以三个预分配窗口槽发布完整状态；读者仅相互串行，短时固定槽并复制到本地，然后取时钟和评估。单个 64 位失效字绑定代数、原因和饱和丢锁计数；无稳定快照时用 wrapper 8 穿过原生与 Python 严格协议，启动流程立即结束该尝试。

**Tech Stack:** C++17、ROS 2 Jazzy、GoogleTest/CTest、ThreadSanitizer、Python 3/pytest、MuJoCo Head 仿真。

**Spec:** `docs/superpowers/specs/2026-10-09-so101-stop-witness-read-isolation-design.md`，SHA256 `692899542aae1fdeb4d31fdfa5d1c8bb0696beab84f0e5d2c754f2866c2edf8b`；独立设计审查 `R/contention-design001/design-review002.json`，SHA256 `24fac0cde335d3f092858de22afe4e46b585f736d048ff7f30f248bdd7fbf900`。实施前同时阅读两者及原预 ARM 设计/计划。

## Global Constraints

- `W=/data/work/ws_moveit/.worktrees/so101-head-file-protocol-1003`，HEAD `de70d83ed1e599c5dbb26843e06bd1af574f0a93`。保留整个未提交继承增量及 submodule；不提交、推送、上传、删除证据或启动不属于本任务的服务。每项保留精确 diff、源清单和检查回执，代替通常的 commit 步骤。
- 唯一登记证据根 `E=/data/work/so101-evidence/act-data/20260930-antzb-head-search-krIv681m`，`F=$E/head-file-protocol-1003/head-camera-yolo-optimization-20261009-001/optimization-fix-20261009-001`，`R=$F/protocol-implementation-ivicy38d`，普通日志根 `D=/tmp/so101-debug-head-file-protocol-1003`。本次实施只在 `R/stop-witness-isolation-<run-id>/` 新建隔离的 `source/build/install/scratch/checkpoints/live20/fresh40`。`R/source`、`R/build`、`R/install` 与原 `live20-acceptance002` 一律只读；不覆盖旧 `.so`、原始结果或冻结清单。
- 原谓词保持 51 个连续样本、64 槽存储、2 ms 仿真步长、接收年龄 `<=200000000` ns、1/5 关节、测量及参考速度绝对值 `<=0.002` rad/s、参考位置逐项严格相等。`PREARM_STATUS` 只读；每尝试最多一次 ARM，保留 ARM 前/GATE/ARM 后顺序及两个独立证明、2.0 s 启动绝对截止、125 ms 有效轮询间隔、50 ms 主交换上限、身份绑定、物理 Stop 和 scoped close。
- 三槽和 64 位失效字在目标编译器上要求 `std::atomic<uint64_t>::is_always_lock_free`；载荷为普通 C++ 对象，生产者不得等待读者锁或 pin。读者锁 `try_lock`，每次证明最多三次捕获，失效 CAS 每事件最多八次。槽版本、32 位事件代临近回绕，或 CAS 耗尽，均永久 fail closed。
- `StopWrapperReason::SNAPSHOT_UNAVAILABLE=8` 只扩展诊断枚举；80 字节证明、`SOPR`/`SOAR` 帧形状、opcode、ABI 版本及旧 opcode 3 回复不变。新旧混配必须拒绝，不得以零样本 `Snapshot`、`LOST` 或 `NOT_EVALUATED` 代替不可用。
- 原 20 次 `live20-acceptance002` 保持 6 PASS、1 FAIL、13 NOT_RUN；14 次尝试的原始证据不改。原 `900009 UNKNOWN` 的具体原因仍为 `NOT_CONFIRMED`。旧 full native 基线是 217 个独立 GoogleTest case、16 个 CTest target（ament aggregate 233）；其中 4 个旧读者丢样断言按 Task 1 的逐项映射替换，其余 213 个旧身份逐一保留。已有 242 个协议定向测试的独立回执也须核对，不与 native aggregate 混算。`R/package-gates/ordinary003/junit.xml` 有 176 个既有 failure/error（110 fail、66 error；另 152 skip），总 8795、通过 8467；逐节点比对新旧机制，不能把普通包称为 green。
- 本改动不碰 detector、模型、图像生成或几何依赖；六项 held-out 图像前提复用 `R` 所属 `F/perception-validation001/validation-report.json`，SHA256 `bd963e64ad803a6ff11412e6f2830168be3d128af2b05ed2d7378dcd8587c4a9`，前提是 detector SHA256 `9158836d227a06511e32c8fd2e6445fc6a15250ceb0d35e62ac767b9a7925fe2`、epoch-50 权重 SHA256 `45de681be6d48b97628b9aaf1400ae4f302220bf3b3f5855ed3244c9a82f1c22`、图像/几何输入全同。若任何依赖变化，再独立重跑对应图像门槛；本协议改动不运行 `benchmark_test/`。
- `ai-station` 所有会创建 fsync-heavy fixture 的 pytest/colcon test 先在新 `RUN/scratch/<test-id>/tmp` 建立唯一、此前不存在的 NVMe 路径，`TMPDIR=TMP=TEMP` 均指向它；用实际解释器 `P=/data/work/venvs/so101-v5-t004-perception/bin/python3` 和 `/usr/bin/python3` 逐个证明 `tempfile.gettempdir()` 一致。事先 `test -x` 验证可执行文件，保存耗时、原始退出码和 JUnit；`tee` 管道用 `set -o pipefail`。Scratch 与结束的私有 IPC 只列为待授权删除候选。

## Review Focus

1. 读者在取时钟前睡过 200 ms：`STALE_SAMPLE`，不能用捕获时刻伪装新鲜；Task 1 的 `ClockDelayedBeforeEvaluationUsesNewTime`。
2. 旧 READY 槽固定后被 reset、参考漂移或失效替代：当前评估重试或拒绝，不能返回旧证明；Task 1 的 `PublishedReplacementNeverRevivesOldReady`。
3. 第二个读者在第一个读者复制时进入：立即 `SNAPSHOT_UNAVAILABLE`，写者仍发布；Task 1 的 `BusyReaderPinReturnsUnavailableWithoutWriterLoss`。
4. 24 位计数在第 16777216 次锁丢失继续增加事件代而计数保持 `16777215`；Task 1 的 `LossCountSaturatesWithoutSuppressingEvents`，Task 2 的 codec 往返。
5. 合法 `NOT_READY / wrapper 8` 在启动 deadline 尚未耗尽时到达：记录该次拒绝，零 ARM、独立 Stop 与 scoped close；Task 3 的 `StartupUnavailableIsTerminal`。

## File map and execution setup

| 文件 | 职责 |
| --- | --- |
| `src/so101_mujoco_support/include/so101_mujoco_support/controller_stop_witness.hpp` | 私有写环、三槽发布、失效字、固定/复验/证明、仅测试 friend 访问器。 |
| `src/so101_mujoco_support/include/so101_mujoco_support/controller_stop_evaluation.hpp` | `CheckedProof` 到 wrapper 8 或既有记录的单次映射。 |
| `src/so101_mujoco_support/include/so101_mujoco_support/broker_owned_trajectory_controller.hpp`、`src/broker_owned_trajectory_controller.cpp` | 明确失败枚举映射和诊断名称；不在写者锁内调用回调或日志。 |
| `src/so101_mujoco_support/include/so101_mujoco_support/controller_reservation_protocol.hpp`、`src/controller_reservation_protocol.cpp` | wrapper 8 严格校验、原有帧兼容。 |
| `src/so101_demo_py/src/adapters/act/head_control_protocol.py`、`src/adapters/act/head_local_runtime.py` | Python 对等严格 codec 与启动终止分支。 |
| `src/so101_mujoco_support/test/test_controller_stop_witness.cpp`、`test/test_broker_owned_trajectory_controller.cpp`、`test/test_controller_reservation_protocol.cpp` | 原生交错、谓词、映射及 wire 回归。 |
| `src/so101_demo_py/test/test_act_head_reservation_authority.py`、`test/test_act_head_local_runtime.py`、`test/test_act_head_execution_runner.py` | Python wire/startup/Stop/close 断言。 |
| `src/so101_mujoco_support/include/so101_mujoco_support/stop_timing_collector.hpp`、`controller_stop_witness.hpp`、`broker_owned_trajectory_controller.hpp/.cpp` | 预分配原子时序记录；分别测发布体和所有出口的完整 `update()`，由非 RT 线程导出。 |
| `src/so101_mujoco_support/test/test_controller_stop_witness_stress.cpp`、`test/stop_witness_timing_stress.cpp`、`CMakeLists.txt`；`src/so101_demo_py/test/head_neck_timing_probe.py` | 有界交错/TSan CTest、5 关节负载程序与实际 Head neck 控制器探针。 |
| `src/so101_demo_py/src/cli/head_search_functional_campaign.py`、`test/test_act_head_functional_campaign.py` | Task 3b 的可选严格协议停批判据，最终资格审查前完成。 |

实施前读取 `R/package-gates/build-final003` 与最终 source/install 清单，冻结输入 SHA；核实 `/opt/ros/jazzy/setup.zsh`、完整 underlay、`P`、`/usr/bin/python3`、`/usr/bin/g++`（现有 GCC 13.3.0）、`/usr/lib/gcc/x86_64-linux-gnu/13/libtsan.so`、`colcon`、`ctest` 的当前路径。`clang++`/`valgrind` 不在 PATH，无须作为前提。只在确认依赖闭包后创建新 `RUN` 和 copied source/build/install，复制两个包及 fixture、asset，再逐文件对照 source SHA/大小、安装路径和运行映射。`R/package-check.py`、`R/native-check.py`、`R/python-check.py`、`R/gate-plugin/so101_gate_provenance.py` 只作参考：其原始路径与首次构建前 install 假设不能直接套用，复制只读权重时也不能 chmod 或覆盖相同文件。新 owned product 模块/`.so` 必须来自新 `RUN/install`，明确批准的 underlay 依赖仍可从原 setup 前缀解析；不能把旧 `R/install` 的同名被覆盖 product package 当依赖。若首次构建因 setup、underlay、selection 或 override 失败，记 `INVALID`，不得写成源码 RED。新旧每项的失败断言须真的执行才算 RED。

每项 RED/GREEN 都将精确命令、唯一 scratch、`TMPDIR` 证明、ROS domain、`GZ_PARTITION`、私有短 IPC、源码/安装来源、耗时和实际退出码放入 `RUN/checkpoints/taskN/`。root 更新实验账本；其余审查只提交结论。所有代码修改先写失败测试、确认目标断言执行，再做最小实现、重建并重跑定向测试，最后 `git diff --check` 和源/产物读回。此计划不授权修改旧 evidence tree。

---

### Task 1: 发布一致窗口并把读者移出写者锁

**Files:** Modify `controller_stop_witness.hpp`; test `test_controller_stop_witness.cpp`.

**Interfaces:** `WindowState` 是私有固定载荷：`std::array<Observation,64> samples`、`size_t count,next`、reset 原因/样本/关节索引、`uint64_t handled_invalidation{static_cast<uint64_t>(ResetReason::NONE)}`。`std::array<WindowState,3> slots_`、`std::atomic<uint64_t> published_`（低两位槽号，高 62 位严格递增版本）、`std::array<std::atomic<bool>,3> pinned_`、`mutable std::mutex reader_mutex_`、`std::atomic<bool> internal_unavailable_`；旧 `mutex_` 只供 `observe/reset` 写者。`std::atomic<uint64_t> invalidation_{static_cast<uint64_t>(ResetReason::NONE)}` 用高 32 位事件代、中 24 位饱和锁丢失计数、低 8 位原枚举原因。保留原数值 `ResetReason::UNKNOWN=0`、`NONE=1` 及其余 wire 值，不为初始化重排 enum。`CheckedProof { enum class Availability { AVAILABLE, SNAPSHOT_UNAVAILABLE }; Availability availability; std::optional<Proof> proof; std::optional<Snapshot> snapshot; }`。既有 `checked_proof()`、`checked_proof_with_clock(Clock&&)`、`checked_proof(int64_t)` 保持名称，`proof*` 返回可选证明；修改所有直接读取 `checked.snapshot` 的调用处。`ControllerStopWitnessTestAccess` 仅作为 friend，在测试翻转近回绕计数/版本、锁住读者锁和设置发布间 barrier；生产源码不包含回调式锁内注入。

冻结 4 个旧测试身份与替代断言，逐个在 CTest/JUnit 清单中核对：

| 旧 `ControllerStopWitness.*` | 替代身份与必须保留的断言 |
| --- | --- |
| `ClockReadSharesTheObservationWindowLock` | `ClockReadAllowsObserveAndRevalidatesWindow`：时钟回调停顿时 `observe(52)` 完成且 loss 计数 0；当前证明重试到新窗口或拒绝旧窗口，不能把旧 READY 用于 ARM。 |
| `CheckedProofRecordsLossFromForcedObservationLockCollision` | `CheckedProofSeparatesReaderFromWriterLockLoss`：读者重叠时计数 0；测试 friend 强制真正的第二写者锁冲突后才为 `LOST/OBSERVATION_LOCK_LOSS`、计数 1；再取连续 51 个新样本恢复，保留该 reset 来源。 |
| `aligned_500hz_queries_recover_after_125ms` | `aligned_500hz_queries_keep_window_and_recover_real_writer_loss`：对齐查询不丢样，125 ms 后窗口仍按实际样本有效；另一个真实写锁冲突后积累至少 51 个新样本才恢复，`sample_count` 最多 64、`Proof` 恰 51；生产者暂停后返回 `STALE_SAMPLE`。 |
| `sustained_aligned_starvation_stays_not_ready` | `sustained_aligned_reads_preserve_window_and_age_out_when_paused`：持续 500 Hz 对齐的读者不增加 lock loss、不使写者饿死；没有新模拟样本时 200 ms 后 `STALE_SAMPLE`，反复读不形成新证明。 |

- [ ] 先按上表替换全部 4 个旧测试，再写 `ClockDelayedBeforeEvaluationUsesNewTime`、`PublishedReplacementNeverRevivesOldReady`、`PinThenThreeSlotRotationNeverOverwritesReader`、`BusyReaderPinReturnsUnavailableWithoutWriterLoss`、`InvalidationAfterWriterLoadBeforePublishIsNotLost`、`LossCountSaturatesWithoutSuppressingEvents`、`VersionAndEventNearWrapFailClosed`、`ThreeRetriesExhaustToUnavailable`。用 barrier/latch 控制发生顺序，近界状态只经测试 friend 注入；覆盖在时钟回调期间继续 `observe`、reset、失效、新无效样本、参考漂移、多个读者、版本/事件耗尽和第 16777214/15/16 次丢失。真正写者锁冲突必须单独断言 `LOST / OBSERVATION_LOCK_LOSS`、51 样本恢复和历史 reset 来源。
- [ ] 在新 copied build 中运行 `ctest --test-dir "$RUN/build/so101_mujoco_support" -R '^test_controller_stop_witness$' --output-on-failure`；记录实际执行的旧行为失败断言，编译/fixture 失败标 `INVALID`。断言不可用不得产生 `Snapshot` 或 `Proof`，纯读竞争不得增加 observation lock losses。
- [ ] 实现 `publish_window() -> bool` 固定复制私有 64 项状态并一次 SC 发布；`capture_window(WindowState&, uint64_t&) const -> bool` 用读者 `try_lock`、描述符/pin/描述符复验和局部复制；`invalidate_event(ResetReason,bool) -> bool` 最多 8 次 SC CAS。构造时确认 64 位原子无锁，版本/事件即将回绕和失败 CAS 置永久故障。`observe` 写者先处理读到的失效代，再按原顺序验证样本；有效样本写环，无效样本清空，然后两条路径都发布携带已处理字的窗口；`reset` 先发表新 `EXPLICIT_RESET` 事件再清空/发布。观察锁失败仅更新事件字，不取得读者锁。
- [ ] 实现 `checked_proof_with_clock` 三次捕获：一致局部副本解除 pin 后依次读 `D1,I1,F1,C,F2,I2,D2`，仅全部稳定才以 `C` 线性化并按原谓词评估；固定时间重载走同一复验，带时钟重载每次重取 `C`。稳定事件字与槽处理字不同给 `AVAILABLE/LOST`，原因与计数取该字；有限失败给 `SNAPSHOT_UNAVAILABLE`。证明与快照只取这次局部副本；不在读者锁内调用 clock。
- [ ] 新 scratch 重跑同一 target，并逐项核查原有 1/5 关节、51/64 样本、严格 `0.002` 边界、未来/过期/暂停窗口和全部 reset 来源仍 PASS。审查读者 pin/写者选槽全部原子顺序，并保留源 diff 与定向 JUnit。

### Task 2: 贯通原生 wrapper 8 和严格 wire 约束

**Files:** Modify `controller_stop_evaluation.hpp`, `broker_owned_trajectory_controller.hpp/.cpp`, `controller_reservation_protocol.hpp/.cpp`; test `test_broker_owned_trajectory_controller.cpp`, `test_controller_reservation_protocol.cpp`, `test_controller_reservation_socket.cpp`.

**Interfaces:** `StopWrapperReason::SNAPSHOT_UNAVAILABLE=8`；`evaluate_controller_stop(uint64_t,Active,SelectWitness,GoalActive) -> ControllerStopEvaluation` 保留外层 active/scope/goal 前后顺序、同次非零 evaluation ID。可用 `CheckedProof` 才填 `snapshot/proof/StopProofRecord`；不可用记录 `wrapper_reason=8`、其余 `StopProofRecord` 保持无快照零值与索引 `-1`。`BrokerOwnedTrajectoryController::StopFailureReason::SNAPSHOT_UNAVAILABLE` 用显式 switch 映射。`encode_stop_proof_record`、`parse_stop_proof_record`、`validate_prearm`、`validate_arm` 接受这一唯一形状及唯一拒绝相位。

- [ ] 写 `UnavailableEvaluationHasNoSnapshotAndKeepsId`、`UnavailableRefusalLogDoesNotRereadWitness`、`WrapperEightRoundTripsOnlyCanonicalRecord`、`WrapperEightRejectsForgedFieldsAndSuccessPhases`、`OldOpcodeThreeReplyShapeUnchanged`。对 wrapper 8 逐字段变异：零 evaluation ID、任意 flags/rejection/reset/count/time/sequence/索引/累计丢失均拒绝；计数 `16777215` 在正常有快照 `LOST` 记录可往返，旧 u32 wire 布局和 80/`SOPR`/104 `SOAR` 长度不变。`READY`、ACK、GATE_ARM 不能承载 8；`NOT_READY`、`STOP_BEFORE`/`STOP_AFTER` 拒绝可承载。
- [ ] 定向运行上述三个 CTest target 取得真实 RED；随后增加明确 enum 分支、codec 约束及 `snapshot_unavailable` 日志。禁止 `wrapper_reason - 1` 数值转型；不改旧 opcode 3、版本、门闩、scoped close 或 socket worker 的后回复诊断顺序。
- [ ] 新 scratch 重建并运行相同 targets，证明非零 ID、无补读、后续样本不能改写已返回记录、旧 opcode 3 字节兼容及 fault worker 独立于证明读者锁。

### Task 3: Python 解析与启动终止性拒绝

**Files:** Modify `head_control_protocol.py`, `head_local_runtime.py`；如 Task 2 后发现 authority 需要保留明确原因，最小修改 `head_reservation_authority.py`。Test `test_act_head_reservation_authority.py`, `test_act_head_local_runtime.py`, `test_act_head_execution_runner.py`.

**Interfaces:** `parse_proof_record(bytes) -> dict`、`parse_prearm(bytes,*,generation:int) -> dict`、`parse_diagnostic_arm(bytes,*,generation:int) -> dict` 与原生相同严格规则。`HeadLocalRuntime` 的启动循环对 `status=='NOT_READY' and proof['wrapper_reason']==8` 立即抛明确可用性错误并交给现有 fault/Stop/scoped-close 路径；普通 `NOT_READY` 仍遵守 125 ms，真实 `LOST` 不改。ARM 拒绝保持一次 ARM 上限，区分 `STOP_BEFORE`、`STOP_AFTER` 与结果未知。

- [ ] 写 `test_wrapper_eight_requires_canonical_fields_and_refusal_phase`、`test_python_loss_count_saturation_and_legacy_u32_layout`、`test_startup_unavailable_is_terminal_without_arm`、`test_arm_before_or_after_unavailable_retains_stop_and_scoped_close`、`test_reply_51ms_after_evaluation_exceeds_main_exchange`、`test_late_ready_still_fails_deadline`。伪造旧解析器行为只作为测试输入：当前 parser 对 8 失败；新 parser 只认可合法 8。Python 要能解析有快照 `LOST` 的 `16777215` 饱和计数及旧 `u32` wire 布局允许的较大历史值；不能把全 wire 字段上限缩成 24 位。注入证明取 `C` 后 51 ms 才回复及跨 2.0 s deadline 才回复，分别被客户端主交换和启动截止拒绝。启动测试断言一次 `PREARM_STATUS`、零 ARM、无后续 125 ms 查询、物理 Stop 与 scoped close 分别有证据；ARM 拒绝测试断言一次 ARM 和独立清理。
- [ ] 用新 copied install 的产品 imports 运行 `"$P" -m pytest "$W/src/so101_demo_py/test/test_act_head_reservation_authority.py" "$W/src/so101_demo_py/test/test_act_head_local_runtime.py" "$W/src/so101_demo_py/test/test_act_head_execution_runner.py" -q`，确认目标断言实际 RED；证实 test `__file__` 来自 `W/test`，产品与 native library 来自新 install。
- [ ] 同步 Python codec；在 `head_local_runtime.py` 的 `NOT_READY` 分支增加 wrapper 8 终止性处理，保留其原始 evaluation ID、scope、Stop 和 close 收据。只在确有调用链证据时修改 authority 的错误映射；不得把 wrapper 8 当 READY/ACK 或可继续轮询。
- [ ] 新 scratch 重跑同一测试；在 2 s 截止、50 ms 交换界限、SIGTERM 及 startup identity 既有定向用例中验证没有迟到 READY/ARM。

### Task 3b: 在最终资格审查前封住 campaign 尝试边界

**Files:** Modify `src/so101_demo_py/src/cli/head_search_functional_campaign.py`、`src/so101_demo_py/src/adapters/act/head_local_runtime.py` 的既有 `NATIVE_CLOSE` 诊断记录；test `src/so101_demo_py/test/test_act_head_functional_campaign.py`、`test/test_act_head_local_runtime.py`.

**Interfaces:** 保留 `may_continue(facts) -> bool` 的旧调用；扩展为 `may_continue(facts, *, require_startup_protocol: bool=False) -> bool`，并把同名布尔参数传入现有 `run_case(case,baseline,*,output,prefix,python,executable,domain,generation_base,minimum_free_bytes,require_startup_protocol=False)`；CLI `--require-startup-protocol` 传给 `run_case`，本次 20/40 必须传 true，既有非协议 campaign 默认语义不变。`extract_attempt` 仅在已有 seal 验证后从原 `events.jsonl` 提取 `startup_protocol`，不把未封存的补写 JSON 当证据。`NATIVE_CLOSE` 记录加入由 `close_scoped_strict` 已验证的 `receipt` 投影（role/generation/incarnation/boot/status/stored_generation/native_owner/ack_validated），不改 close 操作本身。`startup_protocol` 同时保存逐项判据、原始 evaluation ID 与拒绝原因，不能抹去原始 disposition。

- [ ] 写 `test_specific_arm_refusal_stops_before_second_attempt`、`test_unavailable_stops_before_second_attempt`、`test_scope_or_close_mismatch_stops_before_second_attempt`、`test_sealed_ready_ack_and_closed_identity_allow_second_attempt`。冻结严格通过谓词：恰一 `BOOTSTRAP_IDENTITY` 为 `AVAILABLE/ack_validated`；所有 `PREARM_STATUS` 与其 role=3、generation、incarnation、boot、native_owner 相同，前置 `NOT_READY` 只能为合法可继续诊断，最后恰一 `READY` 且 wrapper 0、非零 ID；恰一 `ARM_RESULT` 为 `ACK/NONE`、wrapper 0、非零且不同于 READY 的 ID、同一 generation/native_owner；恰一 `NATIVE_CLOSE` 为 ack/无 error，其新 `receipt` 为 `ARMED_CLOSED`、stored_generation 等于期望 generation、完整身份与 bootstrap 相同；`CANCEL_STOP.raw_stop_confirmed=true` 且无 error；children 全 rc0、owner absent、graph empty。缺项、多项、wrapper 8、任一 ARM `REJECT`、bad scope、close 身份不符、Stop/retirement 不完整都返回 false。原始 `INTERRUPTED` 在以上条件满足时可以继续。
- [ ] 在 copied install 的定向 pytest 中确认现有 `may_continue` 会错误允许一次 Stop/children 均真但 ARM `STOP_BEFORE/REJECT` 的第二尝试（真实旧批次正是此形状）；断言实际 RED 后补最小 event 投影、sealed extraction 和 opt-in 判据。`run_case` 每次 `extract_attempt` 完立即调用严格判据，false 时先完成已有 owned-child 有界清理并停止该 case；外层 main 在该 case 后停止后续 case。不得删除或改写 raw seal/events/结果。
- [ ] 新 scratch 跑定向 campaign/local-runtime 测试和原 242 个协议定向用例的相关集合，记录旧默认 campaign 不变、严格模式首个拒绝即停、`NATIVE_CLOSE` 完整身份读回。Task 5 的最终 copied source/install、普通 gate 和 fresh 实施审查必须包含此修改；Task 6/7 不计划再改产品。

### Task 4: 冻结独立的竞态门槛与实际控制器测时

**Files:** Create `include/so101_mujoco_support/stop_timing_collector.hpp`, `test/test_controller_stop_witness_stress.cpp`, `test/stop_witness_timing_stress.cpp`, `src/so101_demo_py/test/head_neck_timing_probe.py`; modify `controller_stop_witness.hpp`, `broker_owned_trajectory_controller.hpp/.cpp`, `CMakeLists.txt`. 原始配置、记录和结果只写新 `RUN/checkpoints/task4/`。

**Interfaces:** `StopTimingCollector::configure(const std::string & output_path, uint32_t controller_id)` 在 controller configure（非 RT）预分配 `131072` 个 `AtomicTimingRecord` 并打开该控制器唯一输出文件；`record(uint8_t kind, uint8_t proof_availability, uint64_t update_id, uint64_t sample_sequence, int64_t planned_ns, int64_t sim_time_ns, int64_t period_ns, int64_t start_ns, int64_t end_ns) noexcept` 可由写者及并发证明读者调用；`start_drain()/stop_drain()` 只在非 RT 生命周期运行，停用时先确认所有写者/读者退出，再最终 drain 与释放收集器。`proof_availability=0` 表示 UPDATE/PUBLISH 不适用，`1=AVAILABLE`、`2=SNAPSHOT_UNAVAILABLE` 只用于 PROOF；每次已完成证明调用仅写一条含入口/出口时刻的 PROOF 记录。`ControllerStopWitness::set_timing_collector(StopTimingCollector *) noexcept` 只在 activate 前调用，standalone harness 设置自己的收集器，broker 同时传给实际 neck witness；不在活跃写读期间更换指针。环境 `SO101_STOP_TIMING_OUTPUT_DIR` 在 configure 读取并预先计算每个 controller 的文件名，live/probe 用运行专属路径；不在 update 中读环境或拼路径。每条 `kind,proof_availability,controller_id,update_id,sample_sequence,planned_ns,sim_time_ns,period_ns,start_ns,end_ns,ready` 均为原子标量。单调 `next.fetch_add` 让并发证明读者与写者占互不重用的槽；生产者写字段后 `ready.store(1,release)`，独立非 RT drain 线程先 acquire `ready` 再读字段，写二进制原始记录到已打开的文件。满槽置 sticky overflow 并使整个测时批次 `INVALID`；丢记录不得被百分位掩盖。120 s aligned witness-only 计数是最多 60000 PUBLISH+60000 完成调用的 PROOF，不伪造完整 controller UPDATE；实际 Head 是约 60000 UPDATE+60000 PUBLISH+有界启动 PROOF。启动/收尾记录也计入 `131072` 容量，实际溢出即 `INVALID`，不靠估算豁免。RT 路径只用 `clock_gettime(CLOCK_MONOTONIC)`、栈对象和固定原子 store/fetch_add；无分配、格式化、磁盘/套接字 I/O、读者锁或普通载荷 seqlock。`update()` 第一行创建栈上 `UpdateTimingScope`，析构记录所有早返回和正常返回的完整调用起止；`publish_window()` 从选槽前到 `published_.store` 后单独记录发布体，二者用 `sample.sequence`/`update_id` 关联。`checked_proof_with_clock` 在进入与最终返回处记录 `kind=PROOF`，最终记录动作在释放 pin/读者锁之后，包含可用性与最后样本序列；无法稳定时仍记录时长。非 RT drain 原样输出，测量程序离线解析；生产者运行时不改任何普通记录载荷。未启用收集器时不宣称已有发布/update/证明测时。最终正常优化构建保留同一收集器与配置，live 使用该二进制 SHA；TSan 独立构建只判竞态/安全，不拿 sanitizer 耗时与 2 ms 比。

`test_controller_stop_witness_stress` 是短时 deterministic CTest（`ament_add_gtest(... TIMEOUT 300)`），含多读者固定槽、写者轮转和注入停顿；不包含 120 s 资格测时。`CMakeLists.txt` 另建并安装 `stop_witness_timing_stress` 至 `lib/${PROJECT_NAME}`，独立程序 `stop_witness_timing_stress --scope 5 --mode single|four|aligned --duration-s 120 --run-id <frozen-id> --output <new-path>` 在正常优化安装上驱动 5 关节单写者。测试专用 `head_neck_timing_probe.py` 从 `HeadExecutionInputs.parse` 验证新封存输入，沿 `head_execution_provider.resource_plan` 的 `RestartStack` 构造参数与 `head_execution_native.provision_owned_native` 建立同一套 owned stack、主/故障双能力和 `HeadReservationAuthority`；完成一次 bootstrap、原 PREARM 轮询及最多一次 ARM，然后保持 neck controller holding 更新满 120 s，不调用搜索/探测器；最后走既有物理 Stop、scoped close、stack.stop 与独立 OS/graph readback。失败时仍做同一有界清理。实际 Head neck 1 关节只能由这一正常安装的 `BrokerOwnedTrajectoryController::update()` 与真实主 socket 提供完整 update/主交换数据，不能用 5 关节 harness 代替。记录的 `period_ns` 与 `sim_time_ns` 同时检查 2 ms 步长；standalone 的 `planned_ns` 来自 absolute tick，实际 Head 的计划时刻离线用首个开始时刻加 `update_id×2 ms` 推导，二者调度 jitter 单列，不能充作函数体时长。主通道每次 `PREARM_STATUS`/ARM 用现有 `request_wall_s`、`ack_wall_s` 单调时钟字段记录请求与回复；抽取 `proof.evaluated_ns`、evaluation ID，并检查完整交换 `<50 ms`。collector 的更新路径贯穿所有早返回，离线对照 500 Hz 计划调用数、实际完成数及 overflow。

- [ ] 在任何压力/测时测试前冻结 `frozen-workload.json` SHA：普通 `/usr/bin/g++ -O2 -DNDEBUG -DBUILD_TESTING=ON`；5 关节 holding/无目标/速度 0、连续 sequence 与每次 +2 ms sim time；3 个事先编号 run × 每场景 120 s/60000 个 absolute `CLOCK_MONOTONIC` 计划 tick。`single` 为 1 读者每次回复后至少 125 ms；`four` 为 4 读者各 125 ms、固定 0/31.25/62.5/93.75 ms 相位；`aligned` 为 1 读者每 2 ms 与写者同一预定 tick。真实 1 关节 Head neck 另做 3×120 s，首个 2 s 内按原 125 ms 查询直到 READY，单次 ARM 后继续控制更新至时长结束；主通道只记真实发生的请求，不制造第二次 ARM。逐次保存计划 tick、实际开始、更新/发布/证明时长、主请求/回复、样本与状态、0/1/5 关节范围、进程 maps。测时阈值：每次成功发布体及完整 Head `update()` 均 `<2 ms`，正常单读者每次稳定证明 `<2 ms`，有效主交换 `<50 ms`；单读者及实际 Head startup 均零读者所致 lock loss、零意外 wrapper 8。`four` 可出现读者锁忙的不可用，但写者仍不得因读者丢样；对齐场景也不得产生读者所致锁丢失。所有越界次数与最大值逐次报告，实际调度 jitter 与函数体时长分列。没有额外直到 green 的 run。
- [ ] 确定性 `test_controller_stop_witness_stress` 注入：pin 持续 10 个写者发布、读者锁占用 5 ms、三次捕获逐次被写者改版、时钟前冻结生产者 201 ms。依次断言固定槽未覆写、占锁/三次耗尽得 wrapper 8、取 `C` 前旧样本 `STALE_SAMPLE`；Task 3 的客户端测试单独注入 `C` 后 51 ms 与 2.001 s 两档并拒绝迟到回复。所有注入只在测试 friend 或受控客户端，不在生产写者锁内装回调。先让旧实现的目标断言实际 RED，再实现 collector/测试并在正常构建定向 PASS；过期证明不能由 paused producer 的多次查询刷新。
- [ ] 编译前用 `test -x`、`test -r` 确认 `/usr/bin/g++`、`P`、`/usr/bin/python3`、`/usr/lib/gcc/x86_64-linux-gnu/13/libtsan.so`、`/opt/ros/jazzy/setup.zsh` 和 `F/runtime/install/setup.zsh`；检查后者完整依赖闭包，另确认 `timeout`/`colcon`/`ctest` 实际可执行路径。`source /opt/ros/jazzy/setup.zsh; source "$F/runtime/install/setup.zsh"` 后，从同一个 source manifest 正常 `colcon build --base-paths "$RUN/source/src" --packages-select so101_mujoco_support so101_demo_py --allow-overriding so101_mujoco_support so101_demo_py --build-base "$RUN/build" --install-base "$RUN/install" --cmake-args -DBUILD_TESTING=ON -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_CXX_FLAGS=-O2\ -DNDEBUG`；记录真实 flags、目标与 install SHA。独立 TSan 用 `colcon build --base-paths "$RUN/source/src" --packages-select so101_mujoco_support --allow-overriding so101_mujoco_support --build-base "$RUN/tsan-build" --install-base "$RUN/tsan-install" --cmake-args -DBUILD_TESTING=ON -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS=-fsanitize=thread\ -fno-omit-frame-pointer\ -O1 -DCMAKE_EXE_LINKER_FLAGS=-fsanitize=thread -DCMAKE_SHARED_LINKER_FLAGS=-fsanitize=thread`。TSan target 与正常 binary 的 source SHA 必须相同；不让 TSan `.so` 混进正常 install。
- [ ] 各用新 NVMe scratch/精确解释器 tempfile 证明及短 IPC 执行正常 `ctest --test-dir "$RUN/build/so101_mujoco_support" -R '^test_controller_stop_witness_stress$' --output-on-failure --timeout 300` 和 TSan `ctest --test-dir "$RUN/tsan-build/so101_mujoco_support" -R '^test_controller_stop_witness_stress$' --output-on-failure --timeout 300`；保存真实退出码、TSan runtime maps/日志和断言身份。TSan 再以 `timeout 300s "$RUN/tsan-install/so101_mujoco_support/lib/so101_mujoco_support/stop_witness_timing_stress" --scope 5 --mode tsan --duration-s 10 --run-id tsan001 --output "$RUN/checkpoints/task4/tsan001"` 运行，先 `test -x` 验证安装路径。只要求 race detector 已加载、无 race、证明安全断言 PASS，不计算 2 ms/availability fitness；instrumentation 导致的周期滞后不记源码 RED。shadow mapping/TSan runtime 不支持或未实际执行则 `INVALID` 并阻止 live 资格；真实 race/安全断言失败为 RED。正常 CTest 的短 target 在 Task 5 全 CTest 再跑一次，但 120 s × 固定次数只在本 task 明确运行一次，不由全 CTest 重复。
- [ ] 对每个冻结 `mode=single|four|aligned` 与 `run_id=001|002|003`，在新 scratch 与输出路径运行 `timeout 300s "$RUN/install/so101_mujoco_support/lib/so101_mujoco_support/stop_witness_timing_stress" --scope 5 --mode "$mode" --duration-s 120 --run-id "$run_id" --output "$output"`，共 9 个固定 120 s 场景。再以同一正常 install 的真实 1 关节 Head neck/主 socket 运行 `timeout 300s "$P" "$W/src/so101_demo_py/test/head_neck_timing_probe.py" --execution-inputs "$probe_inputs" --duration-s 120 --output "$output"` 共 3 个冻结新身份场景；每个场景的原子 collector overflow、原始记录、ROS domain、partition、owned PID/maps、安装与模型 hash 均读回。证明每个有效主交换、2 s 启动和所有更新/发布/证明阈值，区分 scheduling jitter。正常场景任一意外 wrapper 8、发布或 update 逾 2 ms 即停止 live 资格并回设计评审。TSan PASS 不会覆盖正常时序 FAIL，正常时序 PASS 也不会覆盖 TSan INVALID/RED。

### Task 5: 完整复制安装、原生与普通 Python package gate

**Files:** 不预设产品改动；仅新 `RUN` 下 copied source/build/install、测试与门槛回执。若门槛暴露复现缺陷，返回其责任 task 的 RED/GREEN 循环。

**Interfaces:** `RUN/source/src` 保留两个受影响包及声明 fixture/asset；`RUN/build`、`RUN/install` 只由本次构建产生。完整 native JUnit 逐一核对历史 217 身份：213 个未变身份必须仍 PASS，Task 1 上表 4 个原身份必须各有唯一替代且 PASS；新增测试另计，任何其他消失/skip/fail 均拒绝。旧 16 个 CTest target 保留，新的 stress target 单列为第 17 个，aggregate 单独计。已有 242 个协议定向 case 从原独立回执核对，新 case 另列。Python ordinary 仅收集 `W/src/so101_demo_py/test/`，产品 imports 必须为本次 copied install；旧 176 失败按节点、类型、阶段、原因与 `ordinary003` 比对。

- [ ] 以原本 `R/package-gates/build-final003` 与 final source/install readback 为冻结旧基线。先源包/fixture 清单与完整 underlay 闭包，再运行 fresh `colcon build --base-paths "$RUN/source/src" --packages-select so101_mujoco_support so101_demo_py --allow-overriding so101_mujoco_support so101_demo_py --build-base "$RUN/build" --install-base "$RUN/install" --cmake-args -DBUILD_TESTING=ON -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_CXX_FLAGS=-O2\ -DNDEBUG`，与 Task 4 正常资格构建参数一致；确认源文件、复制文件、安装文件及目标进程 maps 相符。若重建后的运行 binary SHA 与 Task 4 测时 binary 不同，先用最终 binary 重跑 Task 4 全部正常时序负载，再交最终资格审查；TSan source SHA 也必须与最终源清单相同。若新 owned product 模块或 `.so` 从旧 `R/install` 泄漏则批次 `INVALID`；已批准 underlay 的其他依赖按冻结闭包使用。
- [ ] 以各自新 scratch、两个解释器 tempfile 证明和短私有 IPC 执行 `colcon test --base-paths "$RUN/source/src" --packages-select so101_mujoco_support --build-base "$RUN/build" --install-base "$RUN/install" --return-code-on-test-failure` 及 `colcon test-result --test-result-base "$RUN/build" --all --verbose`。记录实际 CTest/JUnit 身份；要求旧 213 个未变身份、4 个逐项映射替代身份、其余新增 native case 全部真正执行 PASS，零 skip/fail；旧 16 个 target 与新增 stress target 实际注册并执行，aggregate 独立列出。保留旧→新 identity manifest 与新 JUnit，核对旧 217 每项去向。另跑原 242 个协议定向 case 的等价新安装集合并对照其独立回执；不把两类计数相加。源码、测试、安装无法闭包则 `INVALID`。
- [ ] 新 scratch 执行 `colcon test --base-paths "$W/src/so101_demo_py" --packages-select so101_demo_py --build-base "$RUN/build" --install-base "$RUN/install" --return-code-on-test-failure --pytest-args test -p no:launch_testing -p no:launch_ros -p xdist.plugin -n "$workers"`，其中 `workers=min(8,logical CPU)`，设置 `SO101_HFP_REPOSITORY="$W"`，收集路径确认为 `W/src/so101_demo_py/test/`，产品及 native maps 确认为新 install。逐条比对 176 节点及此前已修复的 71 节点，要求无新增、无机制变坏、所有必需协议用例真正执行 PASS；独立报告 `scoped_no_new_regression` 和 `ordinary_package_green`（旧问题在时为 false）。不得弱化 fixture、skip 或模型证明。
- [ ] 全部定向/native/TSan/时序/普通门槛可读回后，做 `git diff --check`、精确 diff 与源/安装/测试身份复核，提交一份冻结资格判定给 fresh Astra / High 作整体验收审查。重要发现回所属 task，重跑受影响门槛；通过后才可安排 live。

### Task 6: 新冻结 20 次 case-9 FULL_RESTART

**Files:** 不计划改产品；新 `RUN/live20/` 计划、逐尝试与复核证据。Task 3b 已在最终 copied install 和整体验收审查前实现严格停批，Task 6 只运行带 `--require-startup-protocol` 的既定可执行文件。此后若必须改产品，退回对应 Task 的 RED/GREEN，重做 Task 4 时序/TSan、Task 5 复制安装、完整 gates 和 fresh review，才能有任何 live 尝试。

**Interfaces:** 同一个冻结 case 9 配置、20 个独立 `FULL_RESTART`，每个两次原先声明的尝试，共最多 40 次；只有前一尝试完整通过且清理可信才启动下一次。`NOT_READY/wrapper8`、任何具体 ARM 拒绝、坏 scope、未封闭 close、物理 Stop 未确认、owned child/graph retirement 失败，均在该尝试边界终止整个 batch。不得靠杀父进程留下孤儿，也不把环境无效重试计入原编号。

- [ ] 核验 Task 3b 严格模式的已通过定向/JUnit、Task 4 正常二进制与 TSan/时序回执、Task 5 最终 source/install manifest 与 fresh review；重新确认 `--require-startup-protocol` 在要运行的已安装 campaign argv 中，源或安装 SHA 变化则退出本 task 返回资格门槛。
- [ ] 在只读 baseline parse、closed reference 仅 path+SHA schema、ABI2 产品 import origin、模型/探测器/图像/几何 SHA、ROS graph 和 process ownership 全 PASS 后，冻结新的 20×2 plan、脚本 SHA、域/partition、成功/停批合同；原 campaign 内硬编码旧 source commit 只标历史元数据，实际 manifest/maps 单独绑定，不改写 raw history。
- [ ] 每次独立完整重启 owned stack，以新 `GZ_PARTITION`、记录的 `ROS_DOMAIN_ID` 跑至结果/拒绝；逐尝试读回 bootstrap/main proof/evaluation ID、ARM、原始 Stop、scoped close、进程退出、空 graph、安装 maps、原始图像及几何。**首个**具体拒绝或证据缺口后停止任何后续尝试，先完成有界清理与失败报告。原 `live20-acceptance002` 仍为 6/1/13，绝不续跑。
- [ ] 只有 20 个 repetition 每个两次均真实 PASS、原图复审与全部收据 readback 完成，才记录本 gate PASS；否则保留原始失败和 NOT_RUN，不启用 fresh40。

### Task 7: 独立冻结 40 case / 48 attempt

**Files:** 新 `RUN/fresh40/` 下计划、尝试及复核证据；无预设产品修改。

**Interfaces:** 只在 Task 6 全 20 PASS 后，冻结 `900000..900039` 的独立 40 case、48 个声明尝试、同一安装/模型/运动政策与视觉合同，所有启动都使用已测试的 `--require-startup-protocol`。六项 held-out detector 指标仅是前提，不能由 40 次搜索结果重算或替代。

- [ ] 新建全新 plan/输入 manifest，核验 Task 6 的完整结论、source/install/maps、六项图像前提与空闲 ROS/owned stack，再锁定全部 40 case/48 attempt 和 stop-on-first-refusal 判据。
- [ ] 串行运行，每次保留原始终止图、case 9 停止证明、native seal、独立物理 Stop、scoped close、retirement 与 provenance；任一尝试的具体 ARM 拒绝、不可用、bad scope、close/Stop/retirement 失败立即停止后续尝试并保留 NOT_RUN。
- [ ] 审核 40 case 原图和几何/搜索准则，分别报告 20 gate、40 gate、ordinary package、motion/production 资格。保留原 `900009 UNKNOWN` 与原失败 20 批次；报告 retained、archived、scratch/ended IPC 删除候选，未经授权不删除。

## Handoff

此文件只规定实施步骤，没有启动源码、测试、构建或服务。书面计划经用户审阅后，root 按既有 CP-HFP-940/944 以 `superpowers:executing-plans` 原生执行，并在最终代码实施后安排一次新的 Astra / High 独立审查；不再询问执行方式。
