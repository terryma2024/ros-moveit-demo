# SO-101 ACT 共用端点 Pose 验收 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this amendment task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 实现仍由同一 ai-station tmux `dst` 串行完成，不建立第二实现者。

**Goal:** 在完整 ACT 方案中共用起点/终点 Pose 判定，以可配置经验阈值跑通采集链，取消过程质量校准作为成功前提。

**Architecture:** 一个共享纯计算器、一个冻结策略，供正式/诊断采集、资格、rollout、独立 QC 和聚合使用。动作安全、Head、采样/无损、用途资格和 durable commit 是独立门禁。先落地单条生产闭环，再按原批准顺序重建正式资格。

**Tech Stack:** 现有 MuJoCo/ROS 2/MoveIt/Recorder/Coordinator、Python/NumPy、YAML/JSONL、pytest-xdist；不增加后端或容器实现。

**Spec:** [共用端点 Pose 设计](../specs/2026-10-01-so101-act-endpoint-pose-acceptance-design.md)。此计划是现有正式计划和非 Head 计划的验收修订，不替代它们的其余实施边界。

日期：2026-10-01。状态：用户授权端点方案及三把钥匙修订执行，独立GPT-6 Astra/High静态复审通过，交由原dst实施。下列新增接口/配置/测试是实施目标，不声称当前已安装可用。

## Global constraints

- 同一 worktree `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a`、branch `codex/so101-act-data-0917a`、dst 唯一写入者；直接在 ai-station 执行，不自我 SSH。接手时重新取 HEAD、精确 diff、任务状态和进程，不用文档内旧 SHA 当现场版本。
- 唯一 root `/data/work/so101-evidence/act-data/20260924-fbc25063-resume`，账本 `docs/experiments/so101-act-data-experiment-ledger.md`。每次冻结、测试和 live 使用新目录；旧证据不改结论、不移、不删。
- MuJoCo-only、GPU EGL、CUDA/no CPU fallback、资源绑定仅在启动入口；不启动第二 stack/worktree/executor，不执行真实 SO-101。
- 五个阈值默认值：`0.010m,0.15rad,0.020m,0.010m,0.15rad`，顺序对应设计表。Pose `world`/同一 cup body/`xyz_xyzw`，body +Z 轴夹角，忽略轴向 yaw；norm 误差 ≤`1e-3` 后归一化。
- 用户授权运行配置覆盖设计第5.1节初值；不要求 path/RGB/端点数值的前期测量报告。每 episode 记录 actual effective config/hash；episode 内不热改，正式资格批次改变配置则新开批次。
- `grasp_occlusion_window_s/support_distance_m/release_stable_s/retreat_distance_m/placement_stable_s` 的质量报告不作为采集前置或任务结果；仍保留真实开爪安全配置、接触力/碰撞/授权/hold interlock，不借此自动激活新 policy。
- Head 搜索、10Hz/640×480 RGB/8D state/6D reference `t+.1s`、120s deadline、lease/hash/epoch、诊断不训练、正式用途/split 和配额均按原合同。
- 本次合同变化须新冻结身份与重新验收；不能复用旧 QUALIFIED 或将旧数据重贴标签。W2 后独立 exact-W8/40 场景，不跑 W4/W6，不降档。
- 整个修订开始前更新可见 task list，明确此修订与原九项任务的映射、边界和完成条件；随后每 turn 仅更新 status。未收到修订或列表未确认时不重复投递。用户明确暂停不得自动 resume。
- 每项实现 checkpoint 用执行主机 Codex tmux GPT-6.1 Sol/High；设计/计划独立复审用 Astra/High。保留既有 dirty work；仅 scoped commit，不 push。

## 测试与证据约定

先完全读取项目 `so101-dev` 及 access/system-map/test-and-acceptance/experiment-ledger references。从原非 Head 计划第 0 节使用每次新 NVMe scratch 和实际测试 Python 的 tempfile 验证。下列 `TEST_RUN` 每条运行都重新建立；保存 stdout/stderr、起止时间、JUnit、actual rc。完整普通门只在代码冻结的集成边界跑，不收集 benchmark。

每个 task 的定向命令必须实际运行到目标断言才计 RED。改动触及既有文件时，同时跑该文件所属的全部定向 suite，不只跑新测试。fixture/mock 只验证计算和拒绝边界，不关闭 production runtime finding。

## Task E1：共用策略、Pose 计算和质量输入拆分

**Files:** Create `src/so101_demo_py/config/act/endpoint_pose_acceptance_v1.yaml`、`src/so101_demo_py/src/act/endpoint_pose_acceptance.py`、`src/so101_demo_py/test/test_act_endpoint_pose_acceptance.py`。Modify `act/first_episode_inputs.py`、实际 formal inputs/freezer、`cli/act_first_episode.py`/安装配置和对应输入/CLI测试；具体 formal caller 沿生产 import/调用链只读定位并记到账本，不复制第二 freezer。

**Interfaces:** `load_endpoint_policy(path:Path)->dict` 解析设计的 closed schema；`evaluate_endpoint_pose(initial_pose:list[float],final_pose:list[float],initial_target:list[float],final_target:list[float],policy:dict)->dict` 无 IO/无 live 端口，输出 closed keys `status,errors,passed`，`errors/passed` 使用五个阈值名。误差/比较语义与设计表一致。所有 Pose 7D、有限非 bool 数值及四元数验证在计算前执行。元数据/新鲜度由 Task E2 原始审计验证，不由此函数臆造。

- [ ] 建立 default policy fixture（明确上述五个值）和实际策略文件。先运行如下计算器用例，缺接口或未实现分支须落到实际断言：

```python
def test_endpoints_pass_without_process_quality_fields(policy):
    start = [0.02, -0.28, 0.165, 0, 0, 0, 1]
    end = [-0.07, -0.23, 0.165, 0, 0, 0, 1]
    report = evaluate_endpoint_pose(start, end, start, end, policy)
    assert report["status"] == "PASS"
    assert all(report["passed"].values())
    assert set(report["errors"]) == set(policy["thresholds"])
```

- [ ] Run `"$TEST_PYTHON" -m pytest src/so101_demo_py/test/test_act_endpoint_pose_acceptance.py -q --junitxml="$TEST_RUN/junit.xml"`，记录 RED→GREEN、actual rc。增加等于边界/略超边界、XYZ与XY度量区别、yaw不敏感、倾倒、q/-q、坏norm、NaN/Inf/bool、缺字段/未知版本；角度对点积 clamp，不能舍掉倾斜检查。
- [ ] 为 formal/diagnostic 两种真实输入 registry 添加同一策略角色，冻结 actual config bytes/hash 与每个 scenario 的两端目标/recipe/变换。去掉要求完整 `require_nonhead_gate()` 中事后 release/retreat 质量报告的循环；安全角色按其实际所需证据验证，不改成 blanket `nonhead_ready=True`，也不伪造质量 PASS。
- [ ] 创建并安装 `src/so101_demo_py/config/act/endpoint_pose_development_runtime_v1.yaml`，实现 `load_development_runtime(path:Path)->dict`（在共用输入模块中）解析设计第5.1节完整YAML及closed schema；新增 `user_empirical_default` approval 和独立生效配置/hash，不构造假 calibration/sample 文件。prepare 新增 `--runtime-policy`，freezer新增 keyword-only `runtime_policy:Path`，优先级CLI显式完整文件 > 安装默认文件，formal/diagnostic共享。path/RGB/安全支撑的有效值接到实际path checker/source/release consumer；资源初值合入当前runtime/collection，在启动入口解析一次并更新关联hash，不在每个下游重绑GPU。
- [ ] 创建 `src/so101_demo_py/test/test_act_first_episode_inputs.py`（当前scope suite继续保留），RED/GREEN证明未测量path/RGB但有本轮授权初值时prepare成功；显式覆盖值确实到达生产消费者和封印后的QC。负向覆盖NaN/Inf/bool/未知字段、水位反序、错误配置hash、episode内热改被拒绝、正式模式缺Head/activation仍拒绝。执行 `"$TEST_PYTHON" -m pytest src/so101_demo_py/test/test_act_first_episode_inputs.py src/so101_demo_py/test/test_act_first_episode_scope.py src/so101_demo_py/test/test_act_endpoint_pose_acceptance.py -q --junitxml="$TEST_RUN/junit.xml"`，保留实际argv/rc，不能把import/环境失败计RED。
- [ ] `prepare` 增加显式 `--mode` 与 `--endpoint-policy`（默认 mode 仍 formal）；调用 freezer 的新增 keyword-only `mode:str,endpoint_policy:Path`。formal/diagnostic 均允许同一规则；formal仍需要Head输入。没有新参数的旧调用维持原合同，不静默套用新策略。
- [ ] 定向输入/CLI正向证明：实际安全输入合法但旧五项质量测量缺失时，新合同 prepare 可成功；反向证明 missing activation/path safety/rgb skew/resource hard-stop 仍 rc2 且零动作。保留输入 JSON/差异和 source hash。installed YAML 必须随包发布，不能只读源码默认值。
- [ ] Codex checkpoint 对输入用途和安全/质量拆分复审，scoped commit，账本记录。此项不启动 stack。

## Task E2：边界采样、共用 QC/verifier 和终态

**Files:** Modify `act/episode_audit.py`、`act/episode_qc.py`、`act/pick_place_runner.py`、实际 source/broker adapter、`act/result_store.py`、production Coordinator result port，以及已有正式 outcome validator；Test `test_act_episode_audit.py`、`test_act_episode_qc.py`、`test_act_first_episode_commit.py`、`test_act_first_episode_production.py`，Create `test_act_endpoint_pose_production.py`。

**Interfaces:** `endpoint_records_from_audit(audit:dict,inputs:dict)->dict`（定义在共同 `episode_qc.py`）从已验证原始 history 返回设计规定的两端 Pose/sequence/目标；`verify_episode_qc()` 调用 E1 的单个计算器，组装设计的 `checks.endpoint_pose` closed字段。在线正常终态和离线 QC 共用策略，不由 phase success boolean 代替 Pose。

- [ ] RED：原始 producer→Writer→seal→fresh-process QC 正向链的两端合法、质量字段缺失，旧条件不得拒绝；formal和diagnostic均覆盖。不用预设 `FORMAL_PHASES` 列表填满事件冒充 producer。新 suite 命令：`"$TEST_PYTHON" -m pytest src/so101_demo_py/test/test_act_endpoint_pose_production.py src/so101_demo_py/test/test_act_episode_audit.py src/so101_demo_py/test/test_act_episode_qc.py src/so101_demo_py/test/test_act_first_episode_commit.py -q --junitxml="$TEST_RUN/junit.xml"`；每次改动追加全部触及文件的 suite。
- [ ] 在真实reset后/pre-arm-gripper-dispatch和正常结束/controller-stop后接线采样。正式Head搜索/neck dispatch可早于采集；测试包含真实搜索事件后先采杯子起点再发arm动作的链。事件/source Pose/physics sequence/lease写入共同audit closed schema；新增kind/字段时提升version并同步消费者。按设计第4节验证sim-time映射、所有source不等式、同stamp序号严格晚于停止确认，age=`t_capture-t_pose`∈[0,.1]。补停止前采样、停止后收到且age≤.1仍拒绝，以及停止后首帧越界但后续帧合法仍FAIL的回归。
- [ ] 为每个既有终态/物理 predicate 建立安全/质量清单。仅移除质量：抓稳/抬升幅度、全程持物评分、释放后的 contact、质量稳定时长、实际撤离距离/最终速度。保留控制器正常完成、真实停止、安全开爪/支撑、detach-before-open、collision/force和异常stop/hold。不要让旧质量条件借 `DONE` 或 inputs report 成为隐性 gate。
- [ ] QC 用 frozen targets/policy与封印原始记录重新计算；Coordinator commit 的 verifier 和 aggregator 使用同一结果/版本。诊断与formal在数据/QC规则上一致，exporter只按正式用途、Head、split及commit资格决定能否训练。未知 rule、篡改scope或未commit仍拒绝。
- [ ] 增加缺端点、错cup/frame、旧reset、未来/过期、终止前最佳帧、目标事后改写、安全stop但终点匹配、diagnostic改formal和哈希变化的负向控制。物体质量不通过 rc3；证据/基础设施错误按原分类非0；安全stop不允许整体PASS。
- [ ] Codex checkpoint 审 exact diff、E1/E2 tests与实际 producer/default factory 接线证据。需要新安全批准或资源时停下，不以本修订为 activation授权。

## Task E3：真实首条闭环与完整方案接入

**Files:** Modify ACT rollout/qualification/collection 实际调用方和成功率报告，普通集成 tests；Update正式和非 Head 指南、账本。后续campaign未到批准边界时只修改调用契约，不启动新campaign或模型训练。

- [ ] 把所有物体结果调用接到E1/E2，覆盖正式Worker、容器shard协议、qualification-contract、ACT rollout及路线比较；不实施容器，只定义/验证共同策略hash/规则版本。专家真实命令序列完成产生`expert_sequence_complete`后停止确认；ACT执行合同冻结`first_final_pose_match_v1`，source首个终点匹配产生`endpoint_stop_requested`，禁止新推理/动作提交，broker撤销并确认停止，再取停止后新Pose做最终QC。不能把普通chunk结束当完成，不能先宣称`DONE`再跳过stop。标准revoke/reference审计保留，停止前缓存不当终点。
- [ ] 新增ACT停止回归：阈值未达继续运行；首个达标触发一次single-flight停止；revoke确认失败/安全故障即使Pose达标仍失败；停止后Pose偏离目标FAIL；120s未触发TIMEOUT；q/targets/stop-rule漂移拒绝；Supervisor truth仅audit/停止评估，不进入模型输入或生成动作。定向执行实际ACT runner与监督器所属suite，记录生产调用方、完整命令、actual rc和事件trace。ACT无已批准模型/环境时仅关闭代码回归，明确runtime未验证，不启动训练补前置。
- [ ] 原“物理成功率”注明端点口径，与数据QC/整体成功/安全停止分别报告；原分母、次数、配额、业务失败不重试保持不变。新ACT停止口径绑定执行合同hash，不和旧释放/稳定窗口成功率混算。
- [ ] 默认production factory实际连起producer→Writer→封印→实际 verifier→实际Coordinator/aggregator。若上次review仍有tuple/list、lease/release事件、source/cache/window或readback问题，保留并修复；取消物体过程评分不能用来关闭因果数据/身份 finding。
- [ ] 代码/配置冻结，重新build/source，核对source/install/process provenance。按照非 Head 原计划Task6跑受影响包完整普通xdist与package/serial CTest门；每条命令新NVMe scratch，tempfile proof，保存实际argv、JUnit和rc。不跑benchmark，不高频重复全量。
- [ ] 新 `PLAN_ROOT` 与 `LIVE_ROOT` 必须位于登记root且此前不存在。已验证installed `ACT_FIRST_EPISODE` 后，先执行如下prepare（CLI是E1实施目标）：

```zsh
test -x "$ACT_FIRST_EPISODE" || exit 1
"$ACT_FIRST_EPISODE" inspect \
  --source-root /home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a \
  --ledger docs/experiments/so101-act-data-experiment-ledger.md \
  --output "$PLAN_ROOT/input-candidates.json"
inspect_rc=$?
test "$inspect_rc" -eq 0 || exit "$inspect_rc"
"$ACT_FIRST_EPISODE" prepare --candidates "$PLAN_ROOT/input-candidates.json" \
  --mode preselected_target_diagnostic --endpoint-policy "$ENDPOINT_POLICY" \
  --runtime-policy "$RUNTIME_POLICY" \
  --output "$PLAN_ROOT/inputs"
prepare_rc=$?
test "$prepare_rc" -eq 0 || exit "$prepare_rc"
"$ACT_FIRST_EPISODE" preflight --inputs "$PLAN_ROOT/inputs" \
  --mode preselected_target_diagnostic --output "$PLAN_ROOT/preflight.json"
preflight_rc=$?
test "$preflight_rc" -eq 0 || exit "$preflight_rc"
```

`ENDPOINT_POLICY` 和 `RUNTIME_POLICY` 由新overlay的 `ros2 pkg prefix so101_demo_py` 定位至已安装share配置，并核对与冻结source hash相同；不是旧source路径或现场猜测。prepare/preflight rc2时不启动live。首次用设计第5.1节初值；运行日志打印完整effective config/hash，不要求先补出校准报告。

- [ ] 使用原非 Head Task7 的 installed `run --inputs --root --mode preselected_target_diagnostic --lifecycle FULL_RESTART` 实跑一条完整链。输入为新冻结策略/目标/安全配置，预期两端Pose、连续双RGB/rows、immutable audit/seal、fresh-process QC、result/journal/index receipt和安全cleanup；真实rc必须0。保存stdout/stderr/rc/队列/资源/physics/controller日志；错误先取证，不自动重试，不把poll中断当失败。
- [ ] 新进程执行 `qc --run "$LIVE_ROOT" --output "$PLAN_ROOT/readback.json"`、`verify-commit --run "$LIVE_ROOT" --output "$PLAN_ROOT/commit-proof.json"`、`check-export --run "$LIVE_ROOT" --output "$PLAN_ROOT/export-rejection.json"`，每条实际rc0。诊断数据仍拒绝导出；正式用途正向只在真实Head/正式资格就绪后验证，未就绪列明未完成，不拿fixture等同正式live。
- [ ] 对该live的隔离副本改起点/终点Pose或阈值hash，重算允许修改的copy hash以到达语义边界；证明越界/目标变化/缺样本拒绝，原文件hash前后不变。保留控制器/source/journal不可伪造的authority边界。
- [ ] Codex checkpoint复审实际闭环，不仅UT。报告“共用端点规则已接线；首条采集链实跑通过”，正式Head/资格若未完成逐项列出。更新retained/archived/deletion candidates，不删除、不push。
- [ ] 后续Task8完整资格、W1/W2、独立exact-W8及正式数据/rollout按原已批准顺序、次数和各自执行器边界重做，并分别冻结新policy/manifest/baseline；新端点策略不授权跳过Head校准或跨机器并行写同branch。完成这些新运行后才声明完整方案live合格。

## 与当前 dst 任务和 review 的关系

此修订覆盖原Task1的质量输入、Task3审计/终态质量、Task4物体QC、Task6冻结、Task7验收；Task2连续采样、Task5默认production接线和Task8提交/用途证据仍要完成。任务列表在修订开始时一次明确边界，此后仅status更新。

旧review中仅依赖过程质量评分的要求由本设计明确取代；lease/release epoch、reference/acquisition因果性、生产反馈、raw history/coverage、不可变seal以及真正commit仍是待验证的独立问题。执行者逐项标记“已修复/合同替代/仍开放”，不能把合同替代写成代码修复或将所有review问题一起关闭。

## 用户裁定：钥匙 1、2 与执行顺序

### K1：CP-2332 选择 B，覆盖与窗口分别测试

- [ ] 修改 `test_act_episode_audit.py::test_a_formal_audit_may_not_seal_without_source_coverage`：用真实 writer/acquisition API 创建 head/wrist采集及完整合法审计，由实际数据导出窗口，先证明正向seal和独立readback通过。负向保持相机/窗口一致，单独缺少必要 reference/event/physics记录以到达coverage门；不要删除相机帧后保留旧schedule而重新制造双重无效。另有独立窗口不匹配负向测试。当前seal的coverage检查在window之前，F11修改不得无说明改变错误归属。
- [ ] 定向 RED/GREEN：`"$TEST_PYTHON" -m pytest src/so101_demo_py/test/test_act_episode_audit.py -q --junitxml="$TEST_RUN/junit.xml"`。正向raw producer→writer→seal→fresh-process verifier与缺流副本都要实际跑；覆盖缺失报 `AUDIT_FORMAL_COVERAGE_INCOMPLETE`，窗口错报 `AUDIT_WINDOW_INVALID`，负向不得产生commit。保留journal/manifest/rc及正负控制；仅改期望错误不是关闭finding。

### K2：CP-2285 选择 B，生产者提供时间依据

- [ ] 修改 `control/planning_scene/task_scene.py` 的观测返回、`adapters/act/pick_place_search_segment.py` 的raw fence与对应测试。禁止复制raw.sim_time到一个后来查询的scene响应中制造相等；端口接收时读clock也不能单独证明scene快照时间。当前scene_revision是本地读计数，不能当MoveIt/physics更新序号。
- [ ] 沿当前scene apply→readback生产链建立有依据的snapshot关联：保留派生场景的source physics stamp/step、apply身份、实际query/readback及已核验的world/attached内容，或采用现有同步snapshot/clock fence机制，证明返回快照与该raw的关系。ROS sim clock须验证映射，不与monotonic混算。没有依据时fail closed，不能为解除阻塞接受任意同时间戳记录；缺少可实现的生产关联时报告精确协议缺口，不能声称加字段即解决。
- [ ] K2本身同步修改 `act/episode_audit.py` 的scene closed schema、writer/serializer、`verify_episode_audit()`及实际scene记录的全部消费者，不等待E2。当前六字段scene记录和`scene.sim_time_s == physics.simulation_time_s`不能容纳关联证明；定义版本化scene关联记录，显式区分派生raw的source时间/step与实际query/readback的时间区间。source/session/reset/step、真实apply事件身份、实际readback事件身份、所核验world/attached几何内容及关联/fence证明必须进入原始journal与seal hash链，不只留在stdout。closed字段及事件引用在实现前形成小协议表，由执行主机Codex checkpoint检查真实producer可提供的依据；不发明MoveIt原生revision。独立verifier逐项重建source→apply→query→核验内容关联，单纯时钟相等或本地read计数不再是充分证明。历史版本保留读取和原结论，缺少新证明的旧记录不能通过新合同。
- [ ] 增加封印后隔离副本测试：保留表面时间相等，删改source/step、apply/readback身份、几何内容或fence证明；重算副本文件hash以触达语义验证器，必须拒绝且无commit。正向封印证明必须由实际端口/真实事件生成，不能用测试者补写的关联布尔值；同期修改所有closed-schema消费者和测试，记录实际writer→sealed journal→fresh verifier命令/输入/输出/rc。若采用同步snapshot fence路线，同样封印其生产证据与独立复验规则，不以接收时间替代它。
- [ ] 定向RED/GREEN覆盖旧scene、错reset/step、复制时间、收到时间替代source时间拒绝及真实正向。冻结后用已获准的单条MuJoCo生产入口（E3的installed first-episode run）实际生成scene/physics/raw audit，sealed journal由新进程独立验证，实际rc0才关闭runtime finding。日志保留apply/query/response、source stamp/step、关联证据与拒绝原因，禁止只用mock/fixture宣布F13关闭。

开始整个修订时一次更新可见task list，保留原完成项，加入K1/K2/E1/E2/E3边界和完成条件；此后每turn结束只更新既有项status，不重写内容。先完成现有F5未闭问题及K1/K2必要回归，再E1/E2/E3按序推进；生产runtime验收可汇入E3同一条闭环，不为每finding启动第二stack。已有goal用户侧resume，不能反复让模型调用禁止的自恢复工具。各checkpoint仍由执行机器tmux Codex GPT-6.1 Sol/High复审。新的真正资源/安全阻塞取证上报，不自行降低阈值或改用途资格。
