# SO-101 ACT 首条非 Head Search 闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 项目规定覆盖一般 subagent 建议：实现由 ai-station 的同一 tmux `dst` 执行，串行写入同一 worktree/branch，不创建第二实现执行器。

**Goal:** 完成一条真实 MuJoCo 桌面抓放 episode，经正式 Recorder 无损保存、独立回读 QC PASS，并取得真实 Coordinator 提交。

**Architecture:** 在共同采集链增加显式 `preselected_target_diagnostic` 模式，只替换目标选择和 Head prerequisite。复用正式动作 broker、Worker、Recorder、ResultStore、Coordinator 和训练导出验证边界；诊断数据不进入训练。新增程序负责冻结输入、运行、独立 QC 和提交回读，不用临时 agent 脚本。

**Tech Stack:** ROS 2 Jazzy、MoveIt 2、ros2_control、Linux MuJoCo `3.12.0`、Python、NumPy、PNG/JSONL、现有 journal/lease、pytest-xdist。

**Spec:** [已确认设计](../specs/2026-09-30-so101-act-nonhead-first-episode-design.md)，本计划按该设计实施。

日期：2026-09-30。状态：独立 Astra/High 审查通过，等待用户确认本计划；尚未下发 dst。新增的 API、程序和测试均是实施目标，不表示当前已存在。

## Global constraints

- 执行主机 ai-station；worktree `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a`；branch `codex/so101-act-data-0917a`。dst 在本机执行，不自我 SSH。
- 唯一 durable evidence root `/data/work/so101-evidence/act-data/20260924-fbc25063-resume`；账本 `docs/experiments/so101-act-data-experiment-ledger.md`。新测试与运行使用此前不存在的子目录，失败证据不覆盖、不移动、不删除。
- 一个 Worker、一个固定场景、一次成功 FULL_RESTART 是本里程碑；不要求五次连续成功，不做 W2/W8、W4/W6 或并行性能验收。正式 W8 规则不变。
- 不运行 Head Search、head YOLO、Grounded-SAM 或 ACT 训练。不伪造 Head qualification、`TARGET_LOCKED`、`TASK8_READY`。非 Head 安全门和有效 activation 不得绕过。
- head/wrist 各为 `640×480×3 uint8`，10 Hz；state 为关节 `1..6` 加 neck `sin/cos`，8D；action 为 `1..6` controller reference at `t+0.1s`，6D。truth/mask/phase/contact 仅在 audit。
- 120 s 单调墙钟运动期限，包含等待、抓放、撤离及最终检查；更早的实际推理同样开始计时。finalization、lease 和 batch 期限另外验证，不能重置运动计时。
- MuJoCo-only、GPU EGL、CUDA/no CPU fallback；资源绑定只在启动入口。无支撑持杯失败必须 stop/hold，不开夹爪、不自动 reset。
- 每次受控 source/config/policy 变化使旧 bundle/live/QUALIFIED 对新身份失效。诊断 PASS 永不升级为正式资格或训练 episode。
- 收到整个任务后、任何执行前，dst 先建立可见 task list，固定任务名、边界和完成条件。之后每个 turn 结束只改既有项 status，不重命名、增删、合并或拆分内容。orchestrator 必须 fresh capture 确认可见列表，不凭提示词回显或口头承诺重复投递。
- Task 1–6 每个 checkpoint 使用执行主机 Codex tmux 的 GPT-6.1 Sol/High 做只读审查，不作为第二实现者。无可用 Codex 则暂停等 coordinator 审查；不自动换模型。设计/计划独立审查使用 Astra/High。
- 没有当前任务的 push、删除证据、真实机械臂、改全局配置或清理未知进程的授权。

## 0. 接手与命令约定

现场调查 HEAD 为 `9386860dfed9bdfa840b7b51f061c299459bd390`，submodule 为 `54463fce3bfa6192976e74113f5ed7152f708a3f`，账本 CP-1920。26 个 tracked dirty paths 和 13 个 untracked paths 包含物理执行改动，不能 reset/stash/覆盖来获得 clean tree。重新检查后记录新增差异；与已有改动重叠时按 hunk 留存 before/after，提交只 stage 本任务 hunk。

以下代码块是在 ai-station 上执行的步骤，不在 Mac 上运行。先读根 AGENTS、`so101-dev` 及 access/system-map/test-and-acceptance/experiment-ledger references。实现涉及跨平台 testcase 时另读 `docs/guides/so101-python-test-portability-macos-linux.md`。

```zsh
cd /home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a || exit 1
hostname
git rev-parse HEAD
git branch --show-current
git submodule status
git status --short
tmux list-sessions
tmux capture-pane -p -t dst -S -100
pgrep -af '[m]ujoco|[m]ove_group|[r]ecorder|[p]ytest'
```

pgrep 无匹配的 rc=1 不算失败；工具自身的命令行匹配不算 stack。记录 PID、命令、session 和归属；不停止已有未知 stack，不另启一套。恢复账本首次阻断，不重复已无新增信息的实验。

加载 ROS 和经现场验证的依赖/overlay，记录 `command -v python3`、`sys.executable`、MuJoCo/pytest/xdist origins 和 `ros2 pkg prefix`。将验证过的 Python 绝对路径设为 `TEST_PYTHON`；若 colcon 的测试 Python 不同，对它单独做 tempfile 证明。不存在已知可用路径时停在环境门，不猜旧 venv。

```zsh
export TASK_ROOT=/data/work/so101-evidence/act-data/20260924-fbc25063-resume
test -d "$TASK_ROOT" && test -x "$TEST_PYTHON" || exit 1
mkdir -p "$TASK_ROOT/scratch" "$TASK_ROOT/experiments"
PLAN_ROOT=$(mktemp -d "$TASK_ROOT/experiments/nonhead-first-episode-plan.XXXXXXXX") || exit 1
export PLAN_ROOT
```

在账本登记 `PLAN_ROOT`、原 dirty paths、解释器/overlay、scope 和 task list，再开始测试。新程序在 Task 6 冻结时把输入发布到 `$PLAN_ROOT/inputs`；测试与 review 日志可提前放在该目录的其他子树。

### 每次 pytest/colcon 前的 scratch

下面整段每次重新执行，不能复用旧 scratch，也不能只给一次 shell 保存 proof 后让后续测试换环境：

```zsh
test -x "$TEST_PYTHON" && test -d "$TASK_ROOT/scratch" || exit 1
TEST_RUN=$(mktemp -d "$TASK_ROOT/scratch/nonhead-tests.XXXXXXXX") || exit 1
mkdir "$TEST_RUN/tmp" || exit 1
export TMPDIR="$TEST_RUN/tmp" TMP="$TEST_RUN/tmp" TEMP="$TEST_RUN/tmp"
"$TEST_PYTHON" -c 'import os,pathlib,sys,tempfile; actual=pathlib.Path(tempfile.gettempdir()).resolve(); expected=pathlib.Path(os.environ["TMPDIR"]).resolve(); print(sys.executable, actual); assert actual==expected; assert all(pathlib.Path(os.environ[k]).resolve()==expected for k in ("TMPDIR","TMP","TEMP"))' \
  > "$TEST_RUN/tempfile-proof.log" 2>&1 || exit 1
set -o pipefail
```

每条测试命令保存 stdout/stderr、JUnit、起止时间和实际 rc；Task 1 的完整命令示例为 `"$TEST_PYTHON" -m pytest src/so101_demo_py/test/test_act_first_episode_scope.py -q --junitxml="$TEST_RUN/junit.xml" > "$TEST_RUN/pytest.log" 2>&1; test_rc=$?`，再保存 rc 并检查。import/环境/收集失败不是目标功能 RED，先修到实际断言运行。普通全量 gate 只在 Task 6 集成边界运行；小修改只跑定向测试。

## 文件与接口安排

所有源码路径相对执行 worktree；Python import 前缀是 `so101_demo`，物理目录是 `src/so101_demo_py/src/`。

| 边界 | 新增文件 | 复用或修改 |
| --- | --- | --- |
| 模式、输入冻结 | `act/collection_scope.py`、`act/first_episode_inputs.py` | `act/contact_policy.py`、`act/collection.py`、Teleop `unified/admission.py` |
| acquisition 与时序 | `act/acquisition.py`、`act/continuous_capture.py` | `act/synchronizer.py`、`act/expert.py`、`adapters/act/pick_place_sources.py`、生产相机 adapter |
| 审计与共同 QC | `act/episode_audit.py`、`act/episode_qc.py` | `act/recorder.py`、`act/result_store.py`、`act/bundle.py` |
| 真实接线 | `runtime/act_first_episode_composition.py` | `adapters/act/parallel_collection_runtime.py`、`act/pick_place_runner.py`、Teleop `unified/pick_place_case_owner.py`、`unified/act_stack_probes.py` |
| 安装程序 | `cli/act_first_episode.py` | `src/so101_demo_py/setup.py`，必要时 package install config |
| 使用说明 | `docs/guides/so101-act-first-episode-diagnostic.md` | 本计划与已批准 spec |

相机 acquisition ID 必须在实际生产帧的 adapter 创建。`adapters/act/task8_sources.py` 只是兼容 import，不能往它复制一套实现；沿 import 找到实际 provider 后在该生产边界做最小修改。不得用独立 `ModelFrameSource` 重演另一套 MuJoCo 世界作为 live RGB。

### 新增 schema 与不循环的 hash 顺序

observation/action 字段和数值含义不变。共同 evidence schema v2 的顺序如下，旧 v1 仍可审计，但没有新证据就不能通过本任务或新的正式导出验收：

~~~text
冻结 inputs/collection-scope -> acquisition/event/reference/physics audit
  -> audit-manifest.json -> episode seal v2
  -> 新进程 QC -> qc-report.json
  -> result.json v2 -> RESULT_COMMITTED -> campaign-index/receipt
~~~

- `collection-scope.json` closed fields：`kind,schema_version,mode,scene_id,seed,inputs_sha256`；kind=`ACT_COLLECTION_SCOPE`、schema_version=1，mode 只能为 `formal` 或 `preselected_target_diagnostic`。
- `audit-manifest.json` closed fields：`kind,schema_version,scope_sha256,identity,window,files`；kind=`ACT_EPISODE_AUDIT`、schema_version=2；identity 包含完整 lease 以及 session/reset/release；window 保存 source schedule、采集起止、第一命令、物理结束、label cutoff。files 每项只有 `path,size,sha256`。
- `acquisitions.jsonl` 行：`camera,session_id,reset_epoch,sequence,acquisition_id,stamp_s,received_monotonic_ns,shape,dtype,pixel_sha256`。相机每次真实渲染/发布创建 ID，sequence 严格递增。snapshot/digest 与像素在同一生产事件冻结。
- `row-bindings.jsonl` 行：`row_index,sim_time_s,head_acquisition_id,wrist_acquisition_id,reference_sequence`。一行一绑定，无重复 row_index，不进 ACT observation。
- `events.jsonl` 行：`sequence,kind,identity,sim_time_s,monotonic_ns,payload`；kind 包含实际 dispatch/accept/revoke/stop/contact/release/final-check。payload 按 kind closed schema 验证，不接受任意成功布尔值作为物理事实。
- `references.jsonl` 保存 controller observer 原始消息的 reference/accepted goal/关节名/时间/sequence 和撤销边界。`physics.jsonl` 保存独立 observer 的 pose、速度、完整机器人 contact pairs、support、Planning Scene 和 gripper/controller 反馈；行身份和量纲沿用各实际 source contract，不丢弃原始量后只存判定。
- episode seal v2 在既有 closed keys 上增加 `audit_manifest_sha256,scope_sha256`；不可变 `committed:false`。result v2 在既有 closed keys 上增加 `qc_report_sha256,scope_sha256`。
- QC report closed fields：`kind,schema_version,status,rule_version,identity,episode_seal_sha256,audit_manifest_sha256,inputs_sha256,scope_sha256,counts,checks,reason`；kind=`ACT_EPISODE_QC`、schema_version=2，status=`PASS|FAIL`。episode seal 不引用事后 QC report，避免 hash 循环。
- index/receipt 保存 result hash、episode seal hash、QC hash、scope hash及 journal event identity。导出验证沿该链读取真正 scope，不相信调用者可改写的 `eligible_for_training`。

新 schema 必须同时更新 Writer、readback、ResultStore、Coordinator result port 和 exporter。禁止只让诊断路径忽略未知字段。

## Task 1：模式隔离与输入检查

Files：Create `src/so101_demo_py/src/act/collection_scope.py`、`first_episode_inputs.py`；Modify `act/collection.py`、`src/so101_teleop/so101_teleop/unified/admission.py`；Test `src/so101_demo_py/test/test_act_first_episode_scope.py`。

Interfaces：

```python
class CollectionMode(str, Enum):
    FORMAL = "formal"
    DIAGNOSTIC = "preselected_target_diagnostic"

def require_scope(mode: str, *, head_ready: bool, nonhead_ready: bool,
                  worker_count: int, resume: bool) -> CollectionMode:
    mode = CollectionMode(mode)
    if not nonhead_ready:
        raise ValueError("NONHEAD_SAFETY_NOT_READY")
    if mode is CollectionMode.FORMAL and not head_ready:
        raise ValueError("HEAD_QUALIFICATION_REQUIRED")
    if mode is CollectionMode.DIAGNOSTIC and (worker_count != 1 or resume):
        raise ValueError("DIAGNOSTIC_SCOPE_INVALID")
    return mode

```

`inspect_inputs(source_root:Path,ledger:Path)->dict` 返回只读 candidate registry：记录被账本引用的实际 scene/model、运动配置、PathProof、contact proposal/activation、reset recipe、reference interpolation、placement/retreat QC 与资源阈值来源。`freeze_inputs(candidates_path:Path,output:Path)->Path` 将唯一、匹配当前身份且已获批准的候选复制成不可变 inputs，逐文件 hash，返回新建的 `inputs-manifest.json` 路径；候选缺失/多义/未批准返回具体 blocker，不自动选最新文件或重新发 activation。

- [ ] 写并运行以下 RED，不以 import failure 算 RED：

```python
def test_diagnostic_does_not_bypass_nonhead_safety():
    with pytest.raises(ValueError, match="NONHEAD_SAFETY_NOT_READY"):
        require_scope("preselected_target_diagnostic", head_ready=False,
                      nonhead_ready=False, worker_count=1, resume=False)

def test_formal_still_requires_head_qualification():
    with pytest.raises(ValueError, match="HEAD_QUALIFICATION_REQUIRED"):
        require_scope("formal", head_ready=False, nonhead_ready=True,
                      worker_count=1, resume=False)
```

- [ ] `"$TEST_PYTHON" -m pytest src/so101_demo_py/test/test_act_first_episode_scope.py -q --junitxml="$TEST_RUN/junit.xml"`；先失败于缺少模式逻辑，再实现到 rc=0。加入未知 mode、缺 policy、旧 activation、resume、worker_count=2 拒绝及零 spawn/reset/action 断言。
- [ ] 在统一 admission 增加受识别的诊断 operation，绑定 scope hash；保持原 `act_collection_start`、qualification/formal closed schemas。诊断 operation 复用资源 reservation、GPU UUID、activation 和 child ownership，只按 scope applicability 排除 Head 证明。
- [ ] 保留正式默认模式；冻结初态为 default anchor 杯子 `[0.02,-0.28,0.165]` m、neck `0.1` rad、seed `0`，取自 `config/act/task8-live-anchors.yaml`。机器人姿态、杯子姿态其余分量和放置区从当前可验证 reset recipe 取出并完整冻结，不能以 held-cup profile 初始化。本程序不存在随机选择或成功后挑选 scene。
- [ ] 审查模式隔离与输入 registry；提交本 task 的新增文件及最小 hunk，账本记 gate。此处只核对输入，不启动动作。

### 必须核对的数值与来源

| 配置/值 | 已读来源 | 执行判定 |
| --- | --- | --- |
| `sample_rate_hz=10`，`queue_capacity_samples=16`，high/recovery=`12/8`，high hold=`0.2s`，`lossless=true` | `config/act/parallel_collection_v3.yaml` | 共用 backpressure；溢出或持续高水位触发停止，不丢样本 |
| `dt_s=0.1`、`max_source_age_s=0.1`，RGB `480×640×3 uint8` | `act/recorder.py`、`contracts.py` | 精确保留 |
| heartbeat interval/timeout=`1/5s`，lease=`300s`，finalizing=`120s`，batch=`5400s` | `config/mujoco/parallel_batch_v3.yaml` | 动作仍最多120s；续 lease 不延长 phase/batch hard bound |
| `cpu_busy_warn_fraction=.90`，RAM min=`1073741824` bytes 且 fraction=`.05`，GPU min=`1073741824` bytes | 同一 runtime 的 start_guard | 复用当前 guard；warning 不擅自变成物理判定，hard refusal 照实际 guard |
| contact minimum force=`0.10080889546060459N`，max compression=`9.827758117465844e-05m`，max safe force=`3.2101397343864315N`，hold speed=`0.0037844871361341977m/s`，stable hold=`0.010999999999998789s`，age=`.1s`、consecutive=`5` | EXP-213 `proposal-pass2.json.payload`，fingerprint=`0ba8e07f16e448b16efe7b342745af7181678af47ddf45f975434919774dca11`，独立 activation receipt | 这是已读历史候选，不是本次有效批准。核对 compiled model/scene/motion/source/config 的全部绑定；任一漂移即拒绝，不照抄数值建立新批准 |
| PathProof `path_step_s`、clearance、六维 velocity/acceleration；RGB `max_skew_s`；支撑、放置 pose/速度、稳定窗口、retreat；RTF/disk/队列 hard-stop | 当前注册的批准配置和对应证据 | inspect 输出 exact key/value/path/hash/approval。若缺少其中任一必要数值，输出 `NONHEAD_INPUT_BINDING_REQUIRED` 并阻止 live，不以 candidate 或测得结果代替批准 |

已有 `visible_approach_candidate_v1.json` 声明 `eligible_for_collection:false`，不可因含数值就直接授权。缺少有效非 Head 输入不会阻止编写和定向测试，但 Task 6 的 freeze/live gate 必须等待合法输入或用户最小决策；不扩展本计划去做新的物理校准。

## Task 2：生产 acquisition 身份与持续采集

Files：Create `src/so101_demo_py/src/act/acquisition.py`、`continuous_capture.py`；Modify `act/synchronizer.py`、`act/expert.py`、`adapters/act/pick_place_sources.py` 及实际生产相机 adapter；Test `test/test_act_acquisition_identity.py`、`test/test_act_continuous_capture.py`。

Interfaces：`Acquisition(camera,session_id,reset_epoch,sequence,acquisition_id,stamp_s,received_monotonic_ns,shape,dtype,pixel_sha256)` 为 frozen dataclass，对应 schema。`AcquisitionGuard.accept(frame:Acquisition)->None` 跟踪每路消费序号与 ID。`ContinuousEpisodeCapture.start(session_id,attempt_id,reset_epoch,start_s)->None`、`on_acquisition(frame,pixels)->None`、`on_reference(message)->None`、`on_event(event)->None`、`finish(physical_end_s)->CaptureSummary`；CaptureSummary 提供 `sample_count,label_cutoff_s,audit_files`，没有 committed 字段。

在 `continuous_capture.py` 定义返回类型，后续 audit/QC 只读取这些封印前输出，不从 phase 成功布尔值推断采集完整性：

```python
@dataclass(frozen=True)
class CaptureSummary:
    sample_count: int
    label_cutoff_s: float
    audit_files: tuple[Path, ...]
```

- [ ] 在真实渲染/发布边界为每路源帧建立 monotonic sequence/ID，复制 uint8 RGB 后立即计算 digest；消费时不能给旧帧分配新 ID。写以下 RED：

```python
def test_one_acquisition_cannot_fill_two_rows():
    a = Acquisition("head", "s", 1, 1, "s/1/head/1", 0.1, 1,
                    (480, 640, 3), "uint8", "a" * 64)
    guard = AcquisitionGuard()
    guard.accept(a)
    with pytest.raises(ValueError, match="ACQUISITION_REUSED"):
        guard.accept(a)
```

- [ ] 定向跑 `"$TEST_PYTHON" -m pytest src/so101_demo_py/test/test_act_acquisition_identity.py src/so101_demo_py/test/test_act_continuous_capture.py -q --junitxml="$TEST_RUN/junit.xml"`。新增不同ID/递增stamp但同像素的正向用例，跨reset、缺sequence、新帧未到、伪造未来stamp、缺一相机的拒绝用例。
- [ ] 在第一条执行命令前启用采集，在真实 phase 执行中按 sim-time 网格调度；不阻塞动作线程等待 IO，也不在 phase return 后补行。使用现有 16/12/8 队列合同并留 count/latency/high-water evidence。
- [ ] 用 `MoveItExpertActionTap` 和 `CausalEpisodeCapture` 的共同 reference 校验；增加 bounded pending join，直到 controller observer 有实际 `t+.1` reference。保留原始接受/撤销 history，拒绝未生效计划和下一帧 feedback。
- [ ] RED/GREEN 覆盖慢 phase 中有多个连续 acquisition、提前撤销拒绝、尾帧无未来ref仅audit、label cutoff前网格无洞、stop后不发动作、deadline120s不重置。所有 timer/queue 同步停止，异常进入 broker safe-stop/hold。
- [ ] 审查并提交；采集器 UT 通过只关闭结构性缺陷，实时相机/runtime finding 留至 Task 7 实跑。

## Task 3：共同原始审计与物理判据

Files：Create `src/so101_demo_py/src/act/episode_audit.py`；Modify `act/recorder.py`、`act/pick_place_runner.py`、`adapters/act/pick_place_sources.py` 及实际 broker dispatch/reference observer；Test `test/test_act_episode_audit.py`、现有 `test_act_controller_reference.py`、`test_act_physics.py`。

Interfaces：`EpisodeAuditWriter(root:Path,scope:dict,identity:dict,inputs:dict)`；`append_acquisition(frame)`、`bind_row(row_index,sim_time_s,head_id,wrist_id,reference_sequence)`、`append_source(kind,record)`、`seal(window:dict)->Path`。Writer 是唯一写入者，source kinds 仅 `events,references,physics`，每类 closed schema，audit-manifest 是最后封印的原始审计清单。

- [ ] RED：改变一条原始 reference、遗漏 acquisition binding、跨 release 使用旧 support、audit seal重写、附加未知 schema字段均拒绝。最小测试必须实际触及 Writer/Verifier：

```python
def test_sealed_audit_is_not_overwritten(tmp_path):
    # complete_audit 是本测试文件内构建全部 closed 字段和文件的 fixture。
    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    original = path.read_bytes()
    with pytest.raises(ValueError, match="AUDIT_ALREADY_SEALED"):
        writer.seal(window)
    assert path.read_bytes() == original
```

fixture 在本 task 实现，明确建立真实文件/hash，不替代 Task 7 的 live evidence。定向命令 `"$TEST_PYTHON" -m pytest src/so101_demo_py/test/test_act_episode_audit.py src/so101_demo_py/test/test_act_controller_reference.py src/so101_demo_py/test/test_act_physics.py -q --junitxml="$TEST_RUN/junit.xml"`。

- [ ] broker 实际 claim/dispatch/accept/revoke/stop 事件与 controller observer 原始 history 连入 audit；phase名由真实runner事件产生，不能事后从预设phase列表填 success。
- [ ] 保存桌面初态、双侧实际接触、micro-lift高度与off-table、全程持物/碰撞、放置支撑、detach/open顺序、当前release epoch的无指尖接触、最终pose/速度稳定窗口和retreat原始观测。离线能够按同一阈值重算，不仅消费阶段布尔值。
- [ ] 验证当前 `PickPlaceRunner`/实际 port 的释放顺序；不足时只修相应根因，补 detach失败零open、无支撑stop/hold、release epoch变化与旧观测拒绝的RED/GREEN。始终不物理attach/teleport。
- [ ] Recorder seal v2 引用 audit/scope digest，保存前fsync所有文件与父目录。旧schema兼容仅供读取审计，新闭环必须v2。审查并提交共同审计边界。

## Task 4：独立 QC、真实结果与导出拒绝

Files：Create `src/so101_demo_py/src/act/episode_qc.py`；Modify `act/result_store.py`、`act/bundle.py`、`adapters/act/parallel_collection_results.py`、必要的 `parallel_batch/coordinator.py` index/receipt适配；Test `test/test_act_episode_qc.py`、`test/test_act_first_episode_commit.py`、`test/test_act_first_episode_export.py`。

Interfaces：`verify_episode_qc(episode_seal:Path,inputs:Path,expected_identity:dict)->dict` 是纯磁盘输入，无live端口；`write_qc_report(report:dict,output:Path)->str` 原子新建且fsync，返回digest。共同 ResultStore 的 `seal(episode_seal_path, *, qc_report_path)` 校验QC/identity/hash后发布 result v2；共同 result verifier 复算QC并核对报告，不仅看 Worker `PASS`。

- [ ] 编写并跑定向RED/GREEN：`"$TEST_PYTHON" -m pytest src/so101_demo_py/test/test_act_episode_qc.py src/so101_demo_py/test/test_act_first_episode_commit.py src/so101_demo_py/test/test_act_first_episode_export.py -q --junitxml="$TEST_RUN/junit.xml"`。
- [ ] 离线逐个完整解码PNG，对比生产pixel digest；核对每行绑定、acquisition序号/cadence/完整窗口，允许同像素新acquisition，拒绝复用旧ID或源序列洞。核对state/action单位与source age/skew；从原始history回算`t+.1`reference及撤销有效区间。
- [ ] 从原始physics/contact/Planning Scene与事件计算全部物理判据；配置来自hash绑定inputs。缺少原始量、阶段、窗口或required policy即FAIL。报告不相信seal的qc布尔值。
- [ ] 在新OS进程运行QC，禁用网络/live topic，输入只读、报告写到新路径。Coordinator verifier从registered result目录核对同样内容与完整有效lease，再调用实际 `commit_result(lease,sealed_location,request_key=f"{lease.batch_id}/result/{lease.attempt_id}")`；journal fsync/ack 后建立index receipt。
- [ ] 更新 `collect_authorized_scenario()`：Worker return只报告采集与sealed location，`coordinator_committed`若为兼容字段必须由receipt回读派生，不能硬编码True。
- [ ] exporter `resolve_committed_episodes()` 和 `export_dataset()` 均追溯scope/QC/result/journal；diagnostic、未知mode、missing mode、只seal未commit、conflicting receipt拒绝，返回稳定错误 `DIAGNOSTIC_EPISODE_NOT_TRAINABLE` 或对应identity错误。直接调用export不能绕过resolver。测试文件内建立versioned完整receipt fixture，证明零dataset产物。
- [ ] 相同验证器支持正式路径，正式有效v2输入positive和旧v1缺新证据failclosed均测试。审查并提交；此时fixture提交不算live里程碑。

## Task 5：生产 composition 与安装 CLI

Files：Create `src/so101_demo_py/src/runtime/act_first_episode_composition.py`、`src/so101_demo_py/src/cli/act_first_episode.py`；Modify `adapters/act/parallel_collection_runtime.py`、`src/so101_demo_py/setup.py`、Teleop `unified/pick_place_case_owner.py`/`act_stack_probes.py`的最小共同接线；Test `test/test_act_first_episode_production.py`、`test/test_act_first_episode_cli.py`。

Interfaces：`build_first_episode_context(inputs:Path,run_root:Path,mode:str)->FirstEpisodeContext` 按已验证统一admission取得owner/reservation、单Worker workspace、actual Coordinator/lease；`run_first_episode(context)->dict` 等待到真实terminal与cleanup，输出result location/receipt，不能仅返回start ack。默认formal需要真正Head证明；diagnostic显式flag+scope+单Worker，不伪装W1 qualification。

`FirstEpisodeContext` 在 `runtime/act_first_episode_composition.py` 定义为不可变聚合，字段为 `inputs_manifest:Path,run_root:Path,scope:dict,admitted_context,owner,coordinator,lease,worker_runtime,result_store`。后六项使用现场共同实现的类型，不能填 `None` 或 test double；builder 验证其 production origin 和身份。context 只在 `run` 入口取得 admission 后产生，`inspect/prepare/preflight/qc` 不持有它。`run_first_episode` 输出 closed keys `status,result_location,receipt_path,receipt_sha256,cleanup_proof_path`，只有对应proof都验证后status才为`PASS`。

```python
def main(argv: list[str] | None = None) -> int:
    # argparse subcommands 的实现见下方固定 contract。
    # 捕获已分类错误输出 JSON；不得捕获后返回成功。
    args = parse_args(argv)
    try:
        result = run_command(args)
    except FirstEpisodeError as error:
        print(json.dumps({"status": "FAIL", "reason": error.code}))
        return error.exit_code
    print(json.dumps(result, sort_keys=True))
    return 0
```

`parse_args(argv)->Namespace`、`run_command(args)->dict`、`FirstEpisodeError(code:str,exit_code:int)` 在这个CLI模块定义；生产无injected provider、动态modulepath、预封印result或testseam。测试允许注入边界以assert零副作用，但运行验收必须默认factory。

安装 `act_first_episode = so101_demo.cli.act_first_episode:main`，subcommands如下：

| 命令 | 输入/行为 | 输出与退出码 |
| --- | --- | --- |
| `inspect --source-root --ledger --output` | 只读输入候选/批准绑定与环境，无动作 | 新建candidate registry；rc0表示完成调查，不表示ready |
| `prepare --candidates --output` | Task1严格验证并冻结全部inputs/scope，无动作 | inputs目录；rc0有效，rc2缺安全输入/多义/身份漂移；拒绝overwrite |
| `preflight --inputs --mode --output` | 默认formal；diagnostic显式；核对完整inputs、安装来源、GPU和资源admission的可用性，不启动stack、不发lease | admission report rc0可继续；rc2拒绝；真正资源reservation只在run统一入口取得，preflight report不充当资源权证 |
| `run --inputs --root --mode --lifecycle FULL_RESTART` | 默认正式factory、无resume、诊断固定一个Worker；root必须不存在且在登记root内；一次reset及完整capture/QC/result/commit | complete result JSON rc0，仅在QC PASS+durable commit+安全cleanup后；rc3物理/QC业务失败，rc4基础设施/资源/安全停点 |
| `qc --run --output` | 新进程只读sealed证据和inputs；不重写原QC | 新QC报告；rc0 PASS，rc3 FAIL，rc4输入读取/发布失败 |
| `verify-commit --run --output` | read-only replay实际journal/index/hash/identity与所有QC | receipt proof rc0；缺commit/冲突rc3 |
| `check-export --run --output` | 调用共同resolver+exporter；诊断必须拒绝且不写dataset、不load模型 | negative proof rc0说明预期拒绝成立；若意外可训练rc3 |
| `negative-check --run --output-root` | 只修改新隔离副本，逐case重新seal/hash以到达语义边界 | negative报告及副本；rc0全部预期拒绝/positive通过，否则rc3 |

- [ ] 写RED：run在executor只有start ack时非成功；lease未admitted零reset；active未知stack拒绝；production factory缺端口拒绝。默认formal无Head证据拒绝，显式diagnostic才允许排除Head。
- [ ] `"$TEST_PYTHON" -m pytest src/so101_demo_py/test/test_act_first_episode_production.py src/so101_demo_py/test/test_act_first_episode_cli.py -q --junitxml="$TEST_RUN/junit.xml"` 定向RED/GREEN；每个subcommand参数/rc/新输出路径/错误类型测试。
- [ ] 复用 `PickPlaceCaseOwner` 与 `make_pick_place_act_stack` 的FULL_RESTART、ROS domain、owner fencing、actual readiness和cleanup；一个相同模拟器拥有动作/像素/physics。SEARCH阶段用显式target-designated事件，不伪造SEARCH成功或Head检测。固定mask几何来源冻结到scope audit。
- [ ] 注册Worker -> grant_lease -> ack_lease -> ack_attempt_started -> heartbeat -> begin_finalizing -> commit_result，保持现有deadline/identity约束。若native owner现只产生validation journal，在共同result接线加入ACT result publication，不用validation commit冒充RESULT_COMMITTED。
- [ ] 栈安全停止但无支撑持杯时，遵守hold停点，不退出owner并声称cleaned；保留observer/controller进程并给用户最小决策。成功cleanup仅退休本任务PID/domain，未知live owner禁止start。
- [ ] 审查生产默认composition；提交。本task仍不运行真实抓放。

## Task 6：冻结输入、安装 provenance 与包级集成 gate

Files：Create `docs/guides/so101-act-first-episode-diagnostic.md`；Update账本；测试/构建证据仅在登记root。正文使用`humanizer-zh`，若改README则用英文`humanizer`。

- [ ] 写指南，包含安装程序全部命令、输入身份、失败停止、retained/deletion candidate与诊断不训练说明；不要把新入口描述成已经live通过。
- [ ] 保存exact diff+source tree digest、submodule、配置和政策hash。构建使用已验证依赖closure；新build/install目录在`PLAN_ROOT`，命令为 `colcon --log-base "$PLAN_ROOT/colcon-log" build --packages-up-to so101_demo_py so101_teleop so101_mujoco_support --symlink-install --build-base "$PLAN_ROOT/build" --install-base "$PLAN_ROOT/install"`。编译前核对当前source对这些包的依赖；missing underlay/package-selection不是source RED。
- [ ] source新overlay，查 `ros2 pkg prefix so101_demo_py`、`so101_teleop`、实际controller支持包；核对安装CLI executable、`so101_demo` origin与source/config哈希。executable解析为该overlay下 `lib/so101_demo_py/act_first_episode`，若isolated layout则先由pkg prefix定位，不能硬编码过期路径。
- [ ] 使用新安装程序准备候选/冻结输入；成功前不启动stack。以下`ACT_FIRST_EPISODE`变量来自上述pkg prefix，先test-x。

```zsh
test -x "$ACT_FIRST_EPISODE" || exit 1
"$ACT_FIRST_EPISODE" inspect \
  --source-root /home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a \
  --ledger docs/experiments/so101-act-data-experiment-ledger.md \
  --output "$PLAN_ROOT/input-candidates.json"
inspect_rc=$?
test "$inspect_rc" -eq 0 || exit "$inspect_rc"
"$ACT_FIRST_EPISODE" prepare --candidates "$PLAN_ROOT/input-candidates.json" \
  --output "$PLAN_ROOT/inputs"
prepare_rc=$?
test "$prepare_rc" -eq 0 || exit "$prepare_rc"
"$ACT_FIRST_EPISODE" preflight --inputs "$PLAN_ROOT/inputs" \
  --mode preselected_target_diagnostic --output "$PLAN_ROOT/preflight.json"
preflight_rc=$?
test "$preflight_rc" -eq 0 || exit "$preflight_rc"
```

任何必要placement/skew/path/resource字段或activation无法证明，则prepare/preflight rc2，不补默认值。保存该JSON blocker与exact来源，交最小用户决策；本计划不授权自动激活新policy。

- [ ] 代码冻结后跑一次完整普通门：每个受影响Python包分别 `-n min(8,logicalCPU)`，不混重名包、不跑benchmark。`so101_demo_py` 使用 `"$TEST_PYTHON" -m pytest src/so101_demo_py/test -n "$workers" --junitxml="$TEST_RUN/demo-junit.xml"`；`so101_teleop`使用其package已声明的完整普通test范围及对应pytest配置。scratch先重新验证，记录CPU/worker/RAM、实际node IDs和skip；资源不足不降worker。
- [ ] ai-station还需实际colcon/CTest登记gate：分别核对package驱动的argv。ament_python可用 `colcon --log-base "$PLAN_ROOT/colcon-test-log" test --build-base "$PLAN_ROOT/build" --install-base "$PLAN_ROOT/install" --packages-select so101_demo_py --return-code-on-test-failure --pytest-args test -n "$workers"`，验证子进程解释器/worker实际继承NVMe scratch。Teleop是`ament_cmake`包，`CMakeLists.txt`逐项登记`ament_add_pytest_test`，不能把`--pytest-args`当作其CTest控制入口。若修改Teleop，则在另一全新scratch中执行 `colcon --log-base "$PLAN_ROOT/teleop-test-log" test --build-base "$PLAN_ROOT/build" --install-base "$PLAN_ROOT/install" --packages-select so101_teleop --return-code-on-test-failure --ctest-args -j1 --output-on-failure`，核对生成的CTest/Python argv及实际解释器，不向每个CTest case再注入8worker。其他受影响CMake包同样用serial CTest；完整普通Python xdist gate按上一项另外执行。保留 `colcon test-result --test-result-base "$PLAN_ROOT/build" --verbose`。实际测试命令和test-result均须rc=0、JUnit无fail/error，不能只凭colcon启动成功。仅测试确实被修改的其他包，记录范围；不把demo普通gate充当全仓gate。
- [ ] 独立执行 checkpoint review，列出每个requirement的task/test/runtime evidence预期。无未关闭的安全/接线问题且gate通过才进入Task7；源代码随后改变则新run重验相关gate，旧输入/provenance不得复用。

## Task 7：一次真实 FULL_RESTART、回读与提交验收

仅在用户批准计划、Task6输入和安全gate通过后执行。`LIVE_ROOT`由新UUID确定、尚不存在；CLI在验证其注册root范围和owner后原子新建，不能取旧run目录。

```zsh
LIVE_ID=$(cat /proc/sys/kernel/random/uuid) || exit 1
LIVE_ROOT="$TASK_ROOT/experiments/nonhead-first-episode-$LIVE_ID"
test ! -e "$LIVE_ROOT" || exit 1
set -o pipefail
"$ACT_FIRST_EPISODE" run --inputs "$PLAN_ROOT/inputs" \
  --root "$LIVE_ROOT" --mode preselected_target_diagnostic \
  --lifecycle FULL_RESTART > "$PLAN_ROOT/live-$LIVE_ID.log" 2>&1
live_rc=$?
print -r -- "$live_rc" > "$PLAN_ROOT/live-$LIVE_ID.rc"
```

- [ ] 运行前账本PLANNED指定唯一scene/seed/新session与attempt、生命周期、版本与预测；进程实际启动后记RUNNING。CLI必须保存源树/安装/实际进程三处provenance、domain、physical GPU UUID和owner。
- [ ] 观察真实进程及日志，不将poll中断当失败；controller/physics/runtime日志要能关联到这次identity。若rc非0或缺终态，先保存失败/held cup安全状态再处理；没有自动retry、reset、resume或第二stack。修复后新run重新FULL_RESTART。
- [ ] 预期产物：原始两路PNG+rows、完整audit、immutable seal v2、QC报告、result v2、journal、campaign-index和receipt、资源/队列/cleanup状态。`rc=0`不能只代表program启动或phase DONE。
- [ ] 成功后用独立进程再次执行readback及commit/export proof，保存真实rc。

```zsh
"$ACT_FIRST_EPISODE" qc --run "$LIVE_ROOT" \
  --output "$PLAN_ROOT/readback-$LIVE_ID.json"
qc_rc=$?
test "$qc_rc" -eq 0 || exit "$qc_rc"
"$ACT_FIRST_EPISODE" verify-commit --run "$LIVE_ROOT" \
  --output "$PLAN_ROOT/commit-proof-$LIVE_ID.json"
commit_rc=$?
test "$commit_rc" -eq 0 || exit "$commit_rc"
"$ACT_FIRST_EPISODE" check-export --run "$LIVE_ROOT" \
  --output "$PLAN_ROOT/export-rejection-$LIVE_ID.json"
export_rc=$?
test "$export_rc" -eq 0 || exit "$export_rc"
```

- [ ] 人工审阅报告对应真实桌面初态、抓稳/抬升、持物搬运、supported release、detach-before-open、当前release epoch稳定放置、retreat、安全终态；同时核对全部acquisition窗口、0丢帧、PNG pixel digest、future reference与journal/result/QC/hash身份。head能否看到杯子不参与本次成功判定。
- [ ] 纯headless不要求桌面GUI，说明visual N/A；从本次retained RGB查看首帧/抬升/释放/末帧，作为辅助，不代替独立物理QC。若使用GUI则先读gui-capture并保存fresh截图，不扩大为UI改造。

## Task 8：负向副本与阶段性交付

- [ ] 新路径执行：`"$ACT_FIRST_EPISODE" negative-check --run "$LIVE_ROOT" --output-root "$PLAN_ROOT/negative-$LIVE_ID"`，只修改copy；完整源episode前后hash不变。每case保留mutation manifest、输入/输出、预期/实际rc和首次失败边界。
- [ ] 覆盖：缺PNG；PNG解码损坏；reference伪造；未生效/被revoke reference；source acquisition复用；跨reset/旧worker generation；缺QC/mode；仅seal无commit；receipt冲突；诊断改formal。能到达语义检查的用例重算copy内部hash，不能全都仅因filehash失败而算覆盖；host journal authority不伪造有效提交。
- [ ] 正向控制使用不同acquisition但相同像素的静止帧；其余身份/时序/物理证据保持合法。证明不是以像素变化要求代替新帧身份。
- [ ] 更新账本VALID或INVALID，列精确counts/rc/hash/receipt、被保留的旧进程/dirty工作。retained包括成功及失败runs和review；archived=NONE；scratch/negative copies是deletion candidates，未经授权不删。
- [ ] 最终execution checkpoint审查readback、negative及actual commit。只报告“非 Head Search 的首条采集闭环通过”，列Head仍未验证、诊断不训练、并行未验收。这里不宣称P1-1至P1-6全部关闭。
- [ ] scoped commits后不push。停止新增动作，保留可审查产物；后续antzb Head成果合并另开经审批任务，冻结新身份并重新验收，不把本次PASS升级为正式。

## 计划自检与验收索引

| Spec要求 | 实施边界 | 必须保留的真实证据 |
| --- | --- | --- |
| Head隔离、非Head安全与训练身份 | Tasks1、4、5 | admission/scope、export拒绝、有效activation绑定 |
| 真正桌面抓放及安全停止 | Tasks3、5、7 | live broker/controller/physics/Planning Scene与release事件 |
| 执行期10Hz、acquisition唯一性、因果action | Tasks2、3、7、8 | 原始source schedule/reference与旧帧复用拒绝 |
| 无损与新进程QC | Tasks3、4、7 | acquisition pixel digest、完整PNG decode、独立QC |
| 实际Coordinator提交 | Tasks4、5、7、8 | journal回放、result/index/receipt hash链、无commit拒绝 |
| 冻结/安装/集成门禁与唯一root | Tasks0、6、7、8 | exact executable、source/install/process provenance、NVMe scratch、JUnit/rc |

完成这些步骤证明共同采集合同的单条诊断闭环。它不证明Head模型效果、正式数据资格、W8吞吐或ACT训练质量。
