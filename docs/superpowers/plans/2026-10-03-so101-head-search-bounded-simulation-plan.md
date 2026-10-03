# Head Search 有界仿真 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 用户已指定 GPT-6.1 Sol / High、唯一 antzb executor、inline self_review，禁止 dst/独立 agent review/第二 stack；这些明确授权优先于 skill 的重复批准或 reviewer 默认流程。

**Goal:** 实际 MuJoCo 有界停点搜索可靠锁定，有限感知重观察，安全故障后关闭准入并证明停车，完成正式校准与 Head-only/Teleop 资格。

**Architecture:** 在现有入口、native gate、两个独立监督 reader 和唯一模型 owner 上实施显式版本化仿真 policy。search owner 使用 MOVE -> SETTLED -> NEW_IMAGE -> INFER -> VALIDATE；独立磁盘 aggregator 重建动作/结果和 stop 证据。资源只在正式入口绑定一次，八阶段和 run 非 resumable。

**Tech Stack:** Python 3.12、ROS 2 Jazzy、MuJoCo、原 CUDA YOLO C2a、现有 native reservation/revocation、Bun/Playwright。

**Spec:** `docs/superpowers/specs/2026-10-03-so101-head-search-bounded-simulation-amendment.md`

## Global Constraints

- worktree `/data/work/ws_moveit/.worktrees/so101-act-data-0917a`；branch `codex/so101-act-data-0917a`；基线 Source `87b88febd0781baa779bfce42b88d468ec4f1bc3`。
- 唯一 evidence root `/data/work/so101-evidence/act-data/20260930-antzb-head-search-krIv681m`，low-rate `/tmp/so101-debug-head-codex-oXpMWjlc`。保留所有历史 REFUSED、dirty ledger 和六个原 untracked 目录；不删除证据、不 push、不操作硬件。
- 旧8项 FeedbackPolicy/17值名称不删；新 mode 显式配置才启用修订语义。数值与 scope/config/hash 运行期回读，旧 bundle 不准入新 source。
- 默认值、上限和 clock 严格取自 spec 表；所有预算有限，禁止 RTF=1 假设、timestamp renewal、clamp、丢 outlier、held-out 调参、复活 REVOKED。
- 完整轨迹合法、鉴权/UUID inventory、unknown acceptance terminal reconciliation、actual stop predicate、三个 post-request quiet originals 均保留。
- 10 Hz camera producer、CUDA/no CPU fallback、单模型/单 stack 串行；ACT Recorder/QC/数据集规则不变。
- exact Python `/data/work/venvs/so101-v5-t004-perception/bin/python3`；每次 fsync-heavy test 新 NVMe scratch、TMP/TMPDIR/TEMP、exact executable tempfile proof、真实 rc/elapsed/JUnit。
- 全普通 xdist worker=min(8, CPU)，指定集成边界才全量；benchmark 仅原适用范围。现有缺失 `pick_place_approach_path_screen.py` 和 Task8 权重 baseline 不隐藏、不拿 Head 权重替代。
- 三 anchor 各一次 FULL_RESTART；原40 seed/held-out/Teleop门保留；完成 head-only，不授予 ACT/Task8 readiness。

## Review Focus

1. 一个 slow RPC timeout 后 partial reply 被当作另一操作的 ACK：Task2 用真实 socket framing/sequence 和原 peer 验证，无 authority 时不 reserve/send。
2. inference 返回时恰好 motion epoch 或 generation 改变：Task3 identity-negative 与 late-result 实测均不能目标/lock。
3. action acceptance 比 fault-close 晚：Task2/3 实际 inventory 持续 UNKNOWN，Task5 qualifier 拒绝 quiet-only 证明。
4. sim time 停止/快进，而 wall 继续：Task1/3 分别验证 source age 和 wall deadline，Task6 用实际 pause/RTF 原始证据。
5. supervisor 死亡导致 original stream 未 sealed：Task5 expected-fault reader 保留缺失事实，正常 reader 拒绝，不制造 dead peer ACK/seal。

---

## 执行与命令证据

定向 runner 已存在：`python3 /tmp/so101-debug-head-codex-oXpMWjlc/prepare-dispatch-test.py LABEL TEST_FILE...` 创建从未存在的 `scratch/head-inventory-dispatch-LABEL-ID` 并打印其绝对路径。逐次把该路径记入本次 receipt，再执行 `bash RUN_DIR/run.sh`；runner保存 `test.stdout/test.stderr/test.rc/junit.xml/source-sha256.json/tempfile-proof`，exit code 透传。新增源码需加入 runner snapshot 清单，避免读旧文件。RED 必须 test body 到达目标边界；collection/bootstrap 缺失不算行为 RED。

实际运行命令不能假称已经验证。Task4 在新 install 下读取 `--help`，生成 `formal-entry-command.json`（完整绝对 executable、argv、cwd、逐项 input path/SHA、env 白名单、预期文件与状态），preflight 逐项验证后保存 `formal-entry-preflight.json`，再按记录 argv 一次执行，记录 rc/elapsed/stdout/stderr。计划中未来的命令 manifest 是待生成产物，不能用旧 diagnostic.sh 的通过代替 installed formal/default entry。

所有故障/场景运行在开始前写 `case-input.json`，包含 seed、故障参数、policy/bundle/runtime digest、expected terminal 和资格判据。每个实际 root 都从不存在开始；失败后不 resume。case output 固定 `case-status.json`、Root/CPU original journals、journal seals或明确缺失、`independent-verdict.json`、`owned-teardown.json`。

## Task 1: 显式 simulation policy 与边界校验

**Files:** Create `src/so101_demo_py/src/act/head_simulation_policy.py`; Test `src/so101_demo_py/test/test_act_head_simulation_policy.py`。

**Interfaces:** `HeadSimulationPolicy.parse(document: dict) -> HeadSimulationPolicy`；`default_document() -> dict` 提供显式待批准配置；`readback() -> dict` 返回封闭 scalar 文档；`feedback_values() -> dict` 返回8项原名称；`validate_search_values(values: dict) -> None` 验证 max_age/search_timeout/stop_latency 唯一有效值。此任务不把默认配置注入生产，也不批准 bundle。

- [x] 编写 test-body RED：missing API；parse非有限/bool/unknown/missing/mode；预算关系/上限；dual-clock 不混算；17关联值冲突；8字段 mapping exact。
- [x] 执行 fresh scratch 定向 runner，保存 RED 真实 rc/测试断言。
- [x] 实现冻结 dataclass、闭合 parse、spec 默认/上限、关系与 readback；不导入 ROS/Torch、不产生资源或 motion authority。
- [x] 定向 GREEN 加旧 `test_act_head_feedback_freshness.py`，确认 legacy 语义未被隐式修改。
- [x] self_review immutable diff/原始测试证据并 scoped commit。Expected: 全定向测试 rc0；生产/资格状态仍 pending。

## Task 2: 一次绑定监督 policy 与真实 channel 状态

**Files:** Modify `act/head_feedback.py`, `act/head_monitor.py`, `act/head_monitor_ipc.py`, `adapters/act/head_monitor_process.py`, `head_monitor_runtime.py`, `head_primary_supervisor.py`, `head_monitor_ros.py`, `head_revocation.py`；native `src/so101_mujoco_support/{include/so101_mujoco_support/head_revocation_transport.h,src/head_revocation_transport.cpp}`，以及 `broker_owned_trajectory_controller` 和 `controller_reservation_socket` 的源文件/头文件、`CMakeLists.txt`、`package.xml`；对应现有 feedback/IPC/process/primary/runtime/revocation 和 native lifecycle/socket tests。

**Interfaces:** 正式 entry 向 existing primary/CPU 配置传相同 `simulation_policy` reference/hash；`FeedbackPolicy.parse(values, *, simulation_policy=None)` 校验新 mode 的 exact8 mapping，legacy保持原固定调度值；channel新增 `complete_pending(deadline_wall_s: float) -> dict` 只完成同 sequence frame。channel保持原 codec/authentication，无隐式 reconnect/retry。

- [ ] RED：正确 peer reply 在10 ms后但RPC预算内仍有效；RPC budget到达后不能 dispatch；同在途reply仅可有界完成；原 progress不新鲜/negativeACK不能续 authority；true loss/malformed/death/expiry irrevocably fault。
- [ ] 修改 primary/CPU 同一 policy 绑定及 runtime读回。RPC timeout使 operation无 authority，保留至原frame有界完成/stale；原 policy下测试保持其10 ms预期。
- [ ] native close配置由一次 provisioning/entry传递，有有限 parser/service/client期限；main claim400 ms/UUID/raw digest不改变。default.05必须真正到达 native consumer，不能只改Python timeout。

  native consumer 通过 `neck_controller` 的只读参数 `head_simulation_mode` 和 `head_fault_connection_timeout_ns` 一次绑定；默认仿真 deadline 是 50,000,000 ns。未显式选择模式时，原 ABI 和两个 fault 服务仍采用 2 ms。新模式使用有界 nanosecond deadline，main reservation 通道保留 50 ms 与原协议。正式入口须核验真实参数、只读 descriptor 和两个 reader 的 exact readback，不能用计划值代替服务配置。

- [ ] RED/GREEN：pending send、fault前后队列、late acceptance、wrong peer/MAC/gen/opcode、incomplete main frame、lost/late ACK；两安全owner取消和strict close不能互相等待。
- [ ] exact native targeted gate及相关Python gate，immutable self_review/commit。Expected: authority状态行为和原协议negative成立；实际 stop资格留Task6验证。

## Task 3: 生产停点搜索、有限重观察和可靠锁定

**Files:** Modify `act/search.py`, `adapters/act/head_owned_search.py`, `head_live_exposure.py`, `head_monitor_exposure.py`, `head_inference_owner.py`, `ros_search.py`, `ros_neck.py`, `head_inventory_dispatch.py`, `act/head_search_binding.py`, `head_search_restarts.py`；对应现有tests。

**Interfaces:** `BoundedObservationBudget(policy, *, started_wall_s)`；`reobserve(stop_id, reason, now_wall_s) -> bool` 计数且不重置总deadline；entry-owned inference增加 stopped observation请求，request携带generation/motion_epoch/settled source+wall floors，existingowner queue capacity1。生产模式在 terminal+三freshsettled samples成立前不启动 YOLO。

- [ ] RED：移动中不推理；初始/每次fine/nextstop新epoch；全轨迹验证先于reserve/send；expired/miss/drop清lock并有限重观察，identity错误立即fault；3 distinct frame才lock。
- [ ] 实现MOVE/WAIT/ACQUIRE/INFER/VALIDATE状态切换，只使用原native/SDK/capture/model资源。所有 late result进入 discard evidence，未知goal不能被下一个停点替代。
- [ ] inference age到期不会复活/再起模型；job硬timeout安全关闭并证明stop/资源退休。camera持续loss、feedback失效、sim pause/快进分别判断。
- [ ] `TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL` 仅完整合法coverage；budget exhaustion/SEARCH_TIMEOUT用明确业务状态、全部stop proof。nominal timeout仍不合格。
- [ ] related target gates/self_review/commit。Expected: stale结果目标/lock增量0，次数和总时限有界，legacyACT行为保留。

## Task 4: 正式八阶段、配置和 fresh installed runtime

**Files:** Modify `cli/head_search_calibration.py`, `cli/head_feedback_bootstrap.py`, `act/head_search_calibration_run.py`, `head_search_calibration_bundle.py`, `head_search_binding.py`, `head_search_measured_readback.py`, `head_feedback_measurement.py`, `head_policy_audit.py`；production Head config及相关run/bundle/binding tests。

**Interfaces:** existing `CalibrationPhaseInputs` / `CalibrationPhaseContext`携带typed once-bound runtime；`run --simulation-policy ABS_PATH` 加sealed closed config，CLI只validate/orchestrate。资源真实一次绑定先于任何neckmotion，phase内禁止rebinding。测量actor分别记录Root/CPU实际完整consumer cohorts，新模式不以Root cohort冒充CPU。

- [ ] RED：无typed资源、phase重绑定、资源origin/hash错、旧bundle新mode、policy与17不一致、resume/reuse-existing-root均拒绝。
- [ ] 正式入口绑定native/ROS/capture/CUDA+recorder-refusal/admission/全轨迹checker；phase runners使用同对象，phase7测所有observation/fault/stop及新配置readback，失败保留first failing phase。
- [ ] 原sealeddataset/weights验证后只读复用，数值产物包含17+8+新增policy/所有测量分布和依赖。未批准只purpose=calibration，普通qualifier拒绝。
- [ ] 集成边界I：完整普通Demo/Teleop xdist8、必要colcon package+test-result、affected native packages；benchmark未改不跑。保留全部baseline失败，不能标全GREEN。
- [ ] scoped source commit后fresh copied install/seal，每个新模块加入install/provenance清单；确认默认launch/executable/ROS参数/单stack。读取 installed `run/verify-promoted-config/qualify --help`生成完整command manifest并验证实际inputs。Expected: install/source exact且preflight0；未达到则不启动flight。

## Task 5: 原始journal和独立 disk aggregator

**Files:** Modify `adapters/act/head_original_journal.py`, `act/head_search_production_smoke.py`, `head_search_scenarios.py`, `head_search_aggregate.py`, `head_search_qualification.py`, `head_search_teleop_acceptance.py`及其tests；Create `act/head_simulation_journal.py` 单独负责新schema验证/只读独立重建。

**Interfaces:** `validate_simulation_journal(records, *, policy, expected_scope) -> dict` 输入磁盘已核验的sealed raw records，输出events/counts/action/lock/stop检查；不导入search producer、不采信producer的PASS。fault controls与normal qualifier有不同expected terminal，但共享旧结果拒绝和stop证据。

- [ ] RED：丢失motion epoch/reobserve/discard事件；旧结果发goal/lock；retry超额；nativeclose迟到/错ACK；unknownUUID；无quiet原始样本/actualpredicate；死进程伪ACK/seal；historical10Hz错误重分类均拒绝。
- [ ] producer新事件写全originalidentity/clocks/deadline/owner/confighash，schemaversion显式。gaps全记录并按新criteria核验，producer cadence配置仍10Hz，不改ACT reader。
- [ ] aggregator从原始两个流重建监督crossing、action/trajectory、3-frame lock、总budget/每stop观察、drop/expired/miss与stop完整链。expectedfault中缺死peerseal保留事实，不能计入normal成功。
- [ ] directional GREEN/self_review/commit；Task4运行前此task必须完成。Expected:完整chain可独立重算，所有tamper拒绝。

## Task 6: 冻结 actual formal/default 故障与功能验收

**Files:** Task-owned evidence scripts/manifests（不放source）；affected existing runtime integration tests。Source/config冻结，不在flight期间修改。

- [ ] 执行顺序为Task1 ->2 ->3 ->5 ->4 ->6 ->7。记录integration共享interface和所有ruling到原ledger；无第二writer/stack。
- [ ] actual normal calibration-only formal run从新ID执行完整八阶段；expected `RUN_SUCCEEDED`/rc0及bundle。任何失败保存exactphase/rc/teardown，按feedback修复后新ID从头，不resume。
- [ ] actual故障组：late/expired CUDA结果、短camera gap、持续joint/clock loss、monitor真实死亡/channel真实失效、unknownacceptance、stop/closeACK异常、samegeneration恢复尝试。保存predeclared fault参数及所有actualraw证据。case可EXPECTED_FAULT通过containment，不能作为normal成功；无法证明停车必须FAILED。
- [ ] raw/seals全部核验后独立aggregator读取；记录成功率分母、耗时、retry事件、旧结果误用0、角度/速度/全轨迹范围、stop/owned teardown。Expected:修订功能安全判据成立，无只用mock的资格声明。
- [ ] 若实际运动/停车越界，精确blocker保留且不以retry掩盖。若Source需修正，invalidate当前install/bundle、定向RED/GREEN，再fresh冻结flight。

## Task 7: 精确批准、40/三anchor/Teleop 和关闭

- [ ] 呈现新bundle完整17+8+policy数值/单位/预算/实测/依赖/模型/camera/identity和exactdigest。仅这一数值晋级需要新人工批准；“继续”不能代替hash批准。
- [ ] 批准后一次apply_patch promote，installed `verify-promoted-config`逐字段和consumer检查，freezefinalruntime。任何差异拒绝。
- [ ] 集成边界II：若I后Source改变导致需新freeze，重跑受影响完整普通/package/native门；通过后不无因重复。未解决baseline完整门始终标remaining，不能宣称HEAD_SEARCH_QUALIFIED。
- [ ] frozen实际production smoke、serial40 seeds、default/left/forward各一次独立FULL_RESTART；运行前冻结manifest。actualqualify完整rc0、无missing/violation且independent readback，不摘38/40。
- [ ] 按gui-capture/so101-teleop-debug建立actualHeadCameraTeleop功能证据、exactraw/overlay、新鲜实际查看截图、light/dark/narrow、Bun Playwright `e2e/head-camera.spec.ts`，ownership/conflict/stale/stop/ownedteardown。
- [ ] inlinefinalself_review+独立diskrecomputation/hashreadback所有门；满足才head-only HEAD_SEARCH_QUALIFIED，否则列精确remaining。retained所有run、archived仅实际归档、scratch/privateIPC列deletioncandidates且不删除。

## self_review 结论记录

本文件和spec的 immutable SHA、dispatch receipt、旧门映射、sharedinterfaces、命令成熟度和授权差异保存在同root `design-amendment-18307ff0/self-review.json`。作者检查不冒称独立agent review；独立aggregator仍保留。Task1的完成不意味着Task2-7或actualqualification通过。
