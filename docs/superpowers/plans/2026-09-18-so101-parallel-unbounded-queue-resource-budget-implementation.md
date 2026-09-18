# SO-101 无配额共享队列与逐档资源预算实施计划

> 执行者必须在 ai-station 的 task-owned tmux session 使用 DeepSeek Harness TUI `dst`，并使用 `superpowers:executing-plans` 按任务推进。用户的模型规则覆盖技能中泛型的 Codex/subagent 执行建议，不提供替代执行器。本轮只写文档，不启动执行。

**Goal:** 移除新执行契约中的 `max_points_per_worker`，让固定 N 个 worker 从共享队列领取任务，并以独立实测、审查和批准的 exact-N 资源资格控制生产准入。

**Architecture:** v1 只读历史与 v2 新执行分层；队列保留原租约、恢复和清理边界。三个生产资源消费者共享 provider、无环身份和实时 probe；独立授权的候选测量使用同一安全计量与 owner/control，但不能取得生产权限。

**Tech Stack:** Python、ROS 2 Jazzy、MuJoCo、MoveIt、cgroup v2、NVML、SQLite/journal、PyYAML、FastAPI/Pydantic、React/TypeScript、Bun、Vitest、Playwright、Chrome、colcon。

**Spec:** [冻结设计](../specs/2026-09-18-so101-parallel-unbounded-queue-resource-budget-design.md)，SHA-256 `5e085f98e9926591fbefd3d6e16c16b33bfc9956df9221c46f383b310553657b`。先完整读设计和 [独立复审](../reviews/2026-09-18-so101-parallel-unbounded-queue-resource-budget-design-rereview.md)。复审 PASS 仅批准设计作为计划输入，不是运行验证 PASS。

## 全局约束与执行权限

- 文档编写、执行监控和结果审查用 `gpt-5.6-sol/high`；方案、设计、计划、guide 和 profile/proposal 独审用 `gpt-6-astra/high`。模型或 `dst` 不可用必须报告，不静默替换、不改全局模型配置。
- 用户批准本轮 design+plan，不等于批准本计划执行。本计划还须 Astra 独审和用户执行批准；其后的 profile promotion、停既有服务、独占部署/浏览器窗口仍须各自明确批准。
- 执行前读适用 AGENTS、项目 `so101-dev` 及其要求的 references、`using-git-worktrees`、`test-driven-development`、`executing-plans`。持久中文 guide 用 `humanizer-zh`；审计账本不用 humanizer。
- 隔离分支 `codex/so101-unbounded-queue-resource-budget`；不在 canonical 工作树写代码。不 force/reset/删除、不宽泛 staging、不自动 push/merge。下文 commit 命令只在后续执行批准涵盖本地提交时执行。
- 唯一证据根 `EVIDENCE_ROOT=/data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main`；任务目录 `TASK_ROOT=$EVIDENCE_ROOT/unbounded-queue-resource-budget`。新 batch、raw、profile、批准记录和 scratch 全在此根下，不新建另一个 root。
- PARALLEL N=2..8，SEQUENTIAL N=1；首轮最终点位数 4..20，包含四固定 anchor。选择点位少于 N 仍启动 N 个 runtime，空闲不等于降 N。人工失败 retry 单点、N1、FULL_RESTART、独立 batch/统计。
- 无 K 不等于无限 retry。原 heartbeat/lease/ACK/phase/batch/recovery、broker queue/inflight/inference、TF/RGB-D freshness、epoch/fence/cleanup 全部不放宽。ADAPTIVE 只兼容共享契约，原 affinity/fallback 不变。
- v1 YAML、manifest、journal、receipt、历史行和 evidence 原 bytes/hash 保留；v1 禁止新 execute/resume/retry/spawn。新请求出现 legacy K（包括 null）明确拒绝。不能以大数、点位数、null 或 infinity 代替 K。
- N1 与 N2..8 各自资格；没有实测的值是 `NOT_MEASURED`，缺 coverage/误差/归属则 `UNKNOWN` 或 `REJECTED`。不公式外推、不沿用旧 Task14、不用 N8 结果授权其他 N，不强行让所有选项可执行。
- 普通 demo test gate 只收集 `src/so101_demo_py/test/`，不收集 `benchmark_test/`。Web 使用 Bun 和现有 lock；生成 OpenAPI/types 不手改生成结果。
- ai-station 所有 fsync-heavy pytest/colcon 测试使用新唯一 NVMe scratch，设置 TMPDIR/TMP/TEMP，用精确 test Python 证明 tempfile 路径，保存 elapsed/junit/真实 exit。scratch 只列 deletion candidates，未授权不删。

## 起点事实：历史设计快照不等于当前 runtime

设计 §2 保留初读 `147d64a199bdf9c9b360555e15ad6ae85804ac39` 和旧服务的历史观察。独立复审和本轮只读核验发现 canonical `/data/work/ws_moveit` main 已为 `6701a7be794eac410aa351106cbc17d58568d1ad`；新增仅 `scripts/runtime_cleanup/`，demo/teleop/MuJoCo 接口与设计快照相同。tracked source 干净，两份旧 proposal/guide 未跟踪。不运行新 cleanup 工具，它不是本计划的清理授权。

旧 PID1264438、parent461503、pane%63 已消失，未发现真正 validation server；这不证明谁停止、域已清空、恢复已部署或 ownership 释放。恢复 source module 和 installed launcher 仍不存在。Task 0 必须恢复最后可信 checkpoint，不能凭旧 PID 重建/停止服务。硬件观察为 24 logical CPU、MemTotal32583596KiB、RTX5080 total16303MiB、driver595.84；这些不是任何 N 的预算。

`dst` 当前安装入口 `/usr/local/bin/dst`，安装 metadata0.10.2，解析到 `/usr/local/lib/node_modules/@deepseek-harness-tui/dsh-tui/bin/dsh-tui.js`；本轮未启动其 TUI/version/help。后续执行仍需现场核验。

## 文件边界与跨任务接口

已有路径以下均相对仓库。demo Python 包名是 `so101_demo`，代码位于 `src/so101_demo_py/src/`，不是 `so101_demo_py` import namespace。

| 边界 | 文件职责 |
| --- | --- |
| 契约/历史 | `parallel_batch/contracts.py` 定义 v2；新增 `historical_contracts.py` 只读 v1；新增 `config/mujoco/parallel_batch_v2.yaml`，v1 不动 |
| 无环身份 | 新增 `parallel_batch/resource_identity.py`，负责 L/S/E/I/R 与完整字节审计；不签批准 |
| 资源准入 | 新增 `parallel_batch/resource_budget.py`，封闭 contexts、profile/qualification/authority、bytes/core-equivalent 方程与实时判定 |
| 候选控制 | 新增 `parallel_batch/measurement_control.py`，私有绑定、abort latch、sampler/owner 监控；现有 `web_control.py` 保持闭合 wire |
| 测量/资格 | 新增 `parallel_batch/resource_measurement.py` 与 `cli/measure_parallel_resources.py`，采样、clock、coverage、sealed B/Q；不生成批准 |
| composition | `cli/mujoco_parallel_batch.py` 与 `runtime/parallel_processes.py` 接入统一停止；`parallel_batch/resources.py` 只作同 provider adapter |
| 队列/adaptive | 现有 coordinator 和 adaptive 三文件小范围兼容，不重写策略 |
| Web backend | teleop `expert_validation/` 原 API/preflight/store/supervisor/production；恢复模块从保留快照整合；CMake 明确注册新测试/launcher |
| 浏览器/生成 | 现有 OpenAPI 导出、generated types、setup/progress 与三组 Playwright 配置；物理 evidence 校验不能只判文件存在 |

新接口在对应 task 首次完整定义。未列出的安全检查不删除。所有 pure test 的数字是 synthetic fixtures，不得写入 ai-station profile。

## 通用测试与 checkpoint 操作

每次 server start/refresh、candidate batch、production admission 或 live browser invocation 前，都执行同一 metadata-only 边界规则：先完成待提交的 tracked ledger/guide/checkpoint 等元数据，证明当前 HEAD 干净且 L/S/E/I/R、installed noncarrier bytes 与冻结记录等价；再在注册根内新唯一目录生成该 HEAD 的 immutable raw audit/external binding，保留此前 binding/A0/A1/D。`source_commit` 必须等于此刻 HEAD，不能只证明 R 相等。将新 binding 的绝对路径/hash登记在 root checkpoint，并显式选择为下一运行的 `SO101_VALIDATION_PROVENANCE_BINDING`（下文记为 `ACTIVE_PROVENANCE_BINDING`）；candidate 在 sealing 新 authorization 前绑定此 audit/HEAD/path/hash，不重写旧 sealed authorization/B。promotion 后按需生成等价新 A1/D，保持 R/P/Q/M 和旧 receipts 不变。选择完成到 spawn/admission 之间不得再有 tracked commit；HEAD 若变，重复此规则并重新选择下一授权/环境。R 或不允许的 installed bytes 若变，走原新版本/新资格路径，不能用 metadata 规则豁免。审计产物只写 root，不引入新的 tracked commit 循环；后续 guide/checkpoint commit 后的任何运行也适用。

Task 0 生成并检查 task-owned 测试环境。后续 Python 命令中的 `so101_pytest` 使用以下 zsh 函数；保存函数原文与 hash 到 task ledger，通过 `apply_patch` 写 `TASK_ROOT/tools/test-gate.zsh`，不把它作为生产 bypass：

```zsh
so101_pytest() {
  local test_case_name="$1"
  shift
  local test_run_dir
  test_run_dir=$(mktemp -d "$TASK_ROOT/scratch/${test_case_name}.XXXXXXXX") || return 1
  mkdir "$test_run_dir/tmp" || return 1
  export TMPDIR="$test_run_dir/tmp" TMP="$test_run_dir/tmp" TEMP="$test_run_dir/tmp"
  "$TEST_PYTHON" -c 'import os,tempfile; from pathlib import Path; p=Path(tempfile.gettempdir()).resolve(); e=Path(os.environ["TMPDIR"]).resolve(); assert p==e and str(p).startswith("/data/work/so101-evidence/"); print(p)' > "$test_run_dir/tempfile-proof.txt" || return 1
  local test_started test_finished test_rc
  test_started=$("$TEST_PYTHON" -c 'import time; print(time.monotonic())') || return 1
  if "$TEST_PYTHON" -m pytest "$@" --junitxml="$test_run_dir/junit.xml" > "$test_run_dir/stdout.log" 2> "$test_run_dir/stderr.log"; then
    test_rc=0
  else
    test_rc=$?
  fi
  test_finished=$("$TEST_PYTHON" -c 'import time; print(time.monotonic())') || return 1
  "$TEST_PYTHON" -c 'import json,sys; print(json.dumps({"scratch":sys.argv[1],"exit_code":int(sys.argv[2]),"elapsed_seconds":float(sys.argv[4])-float(sys.argv[3])},sort_keys=True))' "$test_run_dir" "$test_rc" "$test_started" "$test_finished" > "$test_run_dir/result.json"
  return "$test_rc"
}
```

每个 RED/GREEN 都独立调用，不能重用 scratch。记录完整 argv、source/install origins、actual exit、日志/JUnit hashes。RED 必须是指定功能缺失/行为违反断言；依赖导入失败、错误 interpreter、权限/存储错误不算 TDD RED。

同一 `tools/test-gate.zsh` 增加以下记录入口。`so101_colcon` 的全局 `--log-base` 必须在 verb 前；每个build/test/test-result独立run目录。只读核验现有 `/usr/bin/colcon` shebang和canonical teleop CTest/pytest command均为 `/usr/bin/python3`；Task0先初始化 `COLCON_TEST_PYTHONS=("$TEST_PYTHON" /usr/bin/python3)`，每次test前核对新build生成的command完全落入这组精确exe，不同则暂停核验，不在启动后补。test时数组为空拒绝，每个interpreter在同一新NVMe scratch证明tempfile。Bun每次调用均分配新root；一个live调用内的project依赖共享该新root，不跨调用借R01。

```zsh
so101_record_tool() {
  local tool_run_dir="$1"
  shift
  local tool_started tool_finished tool_rc
  printf '%s\n' "$tool_run_dir" >> "$TASK_ROOT/run-index.txt"
  printf '%s\n' "$@" > "$tool_run_dir/argv.txt"
  tool_started=$("$TEST_PYTHON" -c 'import time; print(time.monotonic())') || return 1
  if "$@" > "$tool_run_dir/stdout.log" 2> "$tool_run_dir/stderr.log"; then
    tool_rc=0
  else
    tool_rc=$?
  fi
  tool_finished=$("$TEST_PYTHON" -c 'import time; print(time.monotonic())') || return 1
  "$TEST_PYTHON" -c 'import json,sys; print(json.dumps({"run_root":sys.argv[1],"exit_code":int(sys.argv[2]),"elapsed_seconds":float(sys.argv[4])-float(sys.argv[3])},sort_keys=True))' "$tool_run_dir" "$tool_rc" "$tool_started" "$tool_finished" > "$tool_run_dir/result.json"
  return "$tool_rc"
}
so101_colcon() {
  local colcon_run_name="$1" colcon_run_dir test_interpreter
  shift
  colcon_run_dir=$(mktemp -d "$TASK_ROOT/colcon/${colcon_run_name}.XXXXXXXX") || return 1
  printf '%s\n' "$colcon_run_dir" >> "$TASK_ROOT/run-index.txt"
  mkdir "$colcon_run_dir/tmp" || return 1
  export TMPDIR="$colcon_run_dir/tmp" TMP="$colcon_run_dir/tmp" TEMP="$colcon_run_dir/tmp"
  if [[ "$1" == test && ${#COLCON_TEST_PYTHONS[@]} == 0 ]]; then return 1; fi
  for test_interpreter in "$TEST_PYTHON" "${COLCON_TEST_PYTHONS[@]}"; do
    "$test_interpreter" -c 'import os,tempfile; from pathlib import Path; assert Path(tempfile.gettempdir()).resolve()==Path(os.environ["TMPDIR"]).resolve(); print(tempfile.gettempdir())' >> "$colcon_run_dir/tempfile-proof.txt" || return 1
  done
  so101_record_tool "$colcon_run_dir" colcon --log-base "$colcon_run_dir/colcon-log" "$@"
}
so101_bun() {
  local bun_run_name="$1" bun_run_dir
  shift
  bun_run_dir=$(mktemp -d "$TASK_ROOT/browser/${bun_run_name}.XXXXXXXX") || return 1
  export SO101_E2E_EVIDENCE_ROOT="$bun_run_dir"
  so101_record_tool "$bun_run_dir" bun "$@"
}
```

执行前将新run路径登记到run-index；每个调用结束将argv/result/report/trace/hash和scratch状态归入ledger checkpoint。审计输出重定向只生成记录，不是源码编辑。所有下文build/test/Bun调用都通过这三个已定义入口；不裸跑工具落到默认 `log/` 或 `test-results/`。

每 task 末执行 `git diff --check`，回读 scoped diff，更新单写入者账本的 checkpoint、owned/preserved identities、retained/archived/deletion candidates、下一实验。任务实现由 Sol/high 监控与结果审查；契约/profile/guide 规则变更由 Astra/high 独审。审查未通过不跨 gate。每个未来 scoped commit 先 `git diff --cached --name-only` 核对只能包含该 task 文件；没有包含提交的授权则保存 diff/hash 后暂停。

执行按下表 stage 顺序，不机械按 task 数字跨越物理 gate。后面三个任务把离线实现和外部审批/现场验收分开，防止测量完成后才新增批准解析器造成 R 自身漂移：

| stage | 顺序与退出条件 |
| --- | --- |
| A：离线实现 | Task0–11 → Task13 的 RED/GREEN/聚合代码提交 → Task14 的 RED/GREEN/批准与部署 parser 提交 → Task15 的 offline verifier/test 实现；此时不实测、不promotion、不liveChrome |
| B：统一冻结与恢复 | Task12 完整source/package/Webgate、所有runtimecode cleancommit、最终copiedinstall、L/S/E/I/R/A0冻结、独占离线恢复和ownedWebrefresh；缺审批则暂停 |
| C：候选测量 | Task13 的 CALIBRATION_ONLY、校准审查、normal/coverage/fault 实测；只产生 B/Q/CANDIDATE P，不能改已冻结executioncode/规则来容纳失败 |
| D：批准与部署 | Task14 的 Sol/Astra review、操作员 exactN/Psha approval、M、仅三carrier refs发布、A1/D、生产livegate |
| E：浏览器与交接 | Task15 liveChrome → Task16 guide/账本/历史链接；执行代码若必须修复，先新版本离线gate，再新R资格，不混用旧raw |

Stage A 的所有新测试定义必须在 Stage B 统一 full gate 中收集。Task13/14/15 离线部分各有自己的 scoped review/commit；Stage C 后不再按计划新增runtimecode。执行者按 stage checkpoint 续接，不重复测量已sealedbatch。

### Task 0：fresh ownership、隔离与可重复测试入口

**Files:** Create `docs/experiments/so101-parallel-unbounded-queue-resource-budget-experiment-ledger.md`；scoped append 隔离worktree `AGENTS.md` 模型选择节，保留远端额外operationalrules；任务根内创建 `tools/test-gate.zsh` 和 checkpoints。Read serving continuation ledger、root task ledger、store/control receipts、原恢复快照；不修改历史账本。

**Interfaces:** 冻结 `WORKTREE=/data/work/so101-worktrees/unbounded-queue-resource-budget`、`TEST_PYTHON=/data/work/so101-evidence/teleop-chrome-e2e/20260916T130435Z-e2ffff62-kimi01/python-venv/bin/python3`、`TEST_SITE=/data/work/so101-evidence/teleop-chrome-e2e/20260916T130435Z-e2ffff62-kimi01/python-venv/lib/python3.12/site-packages`。dev source-unit overlay为 `$TASK_ROOT/dev-install`（symlink）；offline installed fixture用 `$TASK_ROOT/offline-install`（copied）；frozen live为 `$TASK_ROOT/production-install`（copied），三者不混用。只读核验该 interpreter 的 Pydantic 为2.13.4，来自该 TEST_SITE；后续仍须 fresh 核验。引用既有环境不是新建证据根。实际 interpreter 若不可用，报告并先批准替代环境，不默默切系统 Python。测试函数是上节定义的唯一入口。

- [ ] 核验 `git status --short`、HEAD、submodule、runtime launcher/config/module/hash、Tailscale URL100.82.102.56:8000、ROS179、store lease/campaign/fences、tmux/PID starttime；读 serving ledger 正文最新 checkpoint，不把 headerCP-L02 当最终状态。查明旧服务消失后的最后 ownership checkpoint；不发 signal、不重放恢复、不宣称 domains free。
- [ ] 在 ai-station 确认分支/path 均不存在后，按 `using-git-worktrees` 创建隔离树；已有同名对象则检查并续接，不重复创建：

```zsh
export EVIDENCE_ROOT=/data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main
export TASK_ROOT="$EVIDENCE_ROOT/unbounded-queue-resource-budget"
export WORKTREE=/data/work/so101-worktrees/unbounded-queue-resource-budget
export TEST_PYTHON=/data/work/so101-evidence/teleop-chrome-e2e/20260916T130435Z-e2ffff62-kimi01/python-venv/bin/python3
export TEST_SITE=/data/work/so101-evidence/teleop-chrome-e2e/20260916T130435Z-e2ffff62-kimi01/python-venv/lib/python3.12/site-packages
typeset -a COLCON_TEST_PYTHONS=("$TEST_PYTHON" /usr/bin/python3)
git -C /data/work/ws_moveit worktree add -b codex/so101-unbounded-queue-resource-budget /data/work/so101-worktrees/unbounded-queue-resource-budget main
cd /data/work/so101-worktrees/unbounded-queue-resource-budget
mkdir -p "$TASK_ROOT/tools" "$TASK_ROOT/scratch" "$TASK_ROOT/colcon" "$TASK_ROOT/browser" "$TASK_ROOT/bindings" "$TASK_ROOT/deployments"
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_moveit/install/setup.zsh
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$TEST_SITE"
"$TEST_PYTHON" -c 'import pydantic; assert int(pydantic.__version__.split(".")[0])==2; print(pydantic.__version__,pydantic.__file__)'
```

- [ ] 完整读 ai-station applicable AGENTS 并以 `apply_patch` 只追加以下模型规则到隔离worktree适用 `AGENTS.md`；已有相同节则逐行核验不重复。禁止 `scp` 整份localAGENTS覆盖远端文件，保留所有远端原规则并证明原bytes前缀hash不变。这里是未来执行的docs操作，本轮不远端写：

```markdown
## Task model selection

| Task | Model or execution tool |
| --- | --- |
| Discuss approaches; write designs, implementation plans, or guides | GPT-5.6 Sol / High (`gpt-5.6-sol/high`) |
| Independently review approaches, designs, implementation plans, or guides | GPT-6 Astra / High (`gpt-6-astra/high`) |
| Execute implementation plans | DeepSeek Harness TUI (`dst`) in a tmux session |
| Monitor execution or review execution results | GPT-5.6 Sol / High (`gpt-5.6-sol/high`) |
| Other tasks | GPT-5.6 Sol / High (`gpt-5.6-sol/high`) by default |

If the required model or tool is unavailable, report it explicitly. Do not silently
substitute a model, automatically downgrade it, or change global model configuration.
```

- [ ] 核验 canonical underlay dependency closure 后构建 task dev overlay；它仅用于 source unit gate，不是生产安装：

```zsh
so101_colcon dev-build build --packages-select so101_demo_py so101_teleop --allow-overriding so101_demo_py so101_teleop --symlink-install --build-base "$TASK_ROOT/dev-build" --install-base "$TASK_ROOT/dev-install"
source "$TASK_ROOT/dev-install/setup.zsh"
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$TEST_SITE"
"$TEST_PYTHON" -c 'import sys,so101_demo,so101_teleop; from pathlib import Path; root=Path("/data/work/so101-worktrees/unbounded-queue-resource-budget"); print(sys.executable); assert Path(so101_demo.__file__).resolve().is_relative_to(root); assert Path(so101_teleop.__file__).resolve().is_relative_to(root)'
```

- [ ] 运行 `so101_pytest baseline-demo src/so101_demo_py/test` 和 `so101_pytest baseline-teleop src/so101_teleop/test`，记录 baseline。此 task 无功能 RED；baseline 失败先诊断，不把已坏环境当新功能失败。
- [ ] 本项由外部 Sol/high 监控者或操作员在向 executor dispatch 前完成，不是 dst 自己再启动第二个 dst：仅获执行批准后创建 task-owned tmux，核验 `/usr/local/bin/dst --version`、`--help` 和真实 TUI。提交本 spec+plan+checkpoint 后从 TUI 新读回确认它实际接收完整任务、工作树和约束；发送 Enter 字节/echo 不是提交证据。SSH environ 不可读时采用 task-owned tmux delayed dispatch，让 SSH 退出，不修改冻结 skip/probe 策略。
- [ ] ledger 写明四类独立权限：代码执行、candidate owned 窗口、服务部署窗口、profile promotion。未获对应批准处暂停。提交只含AGENTS追加和新任务账本：`git add AGENTS.md docs/experiments/so101-parallel-unbounded-queue-resource-budget-experiment-ledger.md`，`git commit -m "docs: register unbounded queue implementation checkpoint"`。

### Task 1：恢复模块快照的审查与隔离整合

**Files:** Modify `src/so101_teleop/CMakeLists.txt`、`so101_teleop/expert_validation/store.py`、`test/test_expert_validation_package_layout.py`（均在 teleop package 下）；Create `src/so101_teleop/scripts/so101_expert_validation_recover.py`、`src/so101_teleop/so101_teleop/expert_validation/operator_recovery.py`、`src/so101_teleop/test/teleop/test_expert_validation_operator_recovery.py`。

**Interfaces:** 保留snapshot真实 `RuntimeInspector(proc_root: Path, container_probe, domain_probe)` 与 `recover(*, store, campaign_id: str, command_id: str, parallel_config: Path, inspector: RuntimeInspector | None = None, source_commit: str, apply: bool = False) -> dict`；store为keyword-only，默认preview，CLI仅显式 `--apply` 才应用。CLI 为 `ros2 run so101_teleop so101_expert_validation_recover.py --store-root --campaign-id --command-id --parallel-config --source-commit [--apply]`。这条 operator recovery 允许读取原 v1 冻结配置，不允许新 v1 执行。

- [ ] 完整读 snapshot 六 source 文件和 pending-commit diff，核对 hash；snapshot 路径为 `$EVIDENCE_ROOT/operator-recovery-implementation/recovery-source-snapshot/data/work/ws_moveit/`。以 targeted patch 整合 evolved store/CMake，不能整文件覆盖，pycache 不算源文件。
- [ ] 先复制并审查 snapshot 的 test 用 `apply_patch` 落入隔离树，保留其实际 API；关键 RED：

```python
def test_formal_recovery_entry_exists():
    from importlib.util import find_spec
    assert find_spec('so101_teleop.expert_validation.operator_recovery') is not None

def test_recover_defaults_to_keyword_only_preview_without_writes(fenced):
    import inspect
    import hashlib
    store, config, root = fenced
    module = recovery_module()
    signature = inspect.signature(module.recover)
    assert signature.parameters['store'].kind == inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters['apply'].default is False
    probe = inspector(module, root)
    before_rows = historical_rows(store)
    before_files = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in root.rglob('*') if p.is_file()}
    result = module.recover(store=store, campaign_id='campaign-1',
        command_id='preview-default', parallel_config=config, inspector=probe,
        source_commit='2' * 40)
    assert result['status'] == 'RECOVERY_ELIGIBLE_PREVIEW'
    assert historical_rows(store) == before_rows
    assert store.has_recovery_fence() is True
    assert store.operator_recovery('campaign-1') is None
    assert {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()} == before_files
    with pytest.raises(TypeError):
        module.recover(store, campaign_id='campaign-1', command_id='invalid-positional',
            parallel_config=config, inspector=probe, source_commit='2' * 40)
```

- [ ] `so101_pytest recovery-red src/so101_teleop/test/teleop/test_expert_validation_operator_recovery.py -q`；预期正式 entry 缺失失败，不因 import path 错误失败。
- [ ] 整合 snapshot 实现，保持 original fences/history 不改；同 command 返回原 receipt，另 command 不替换成功 receipt。实际恢复仅在 Task12 独占离线 gate；此处只 fake runtime tests。注册 CMake install launcher 与 pytest：

```cmake
install(PROGRAMS scripts/so101_expert_validation_recover.py DESTINATION lib/${PROJECT_NAME})
so101_add_pytest_test(test_expert_validation_operator_recovery test/teleop/test_expert_validation_operator_recovery.py)
```

- [ ] GREEN：`so101_pytest recovery-green src/so101_teleop/test/teleop/test_expert_validation_operator_recovery.py src/so101_teleop/test/test_expert_validation_package_layout.py -q`。必含 immutable rows、preview、idempotency、unknown same-UID/container/domain、active lock/live owned PID、unacked spawn intent、无 foreign signals。已有509pytest/508colcon只是历史，不填本次结果。
- [ ] 审查/checkpoint 后显式 stage 上述六文件，`git commit -m "feat(teleop): integrate audited operator recovery entry"`；不得把落盘 receipt 标为 ONLINE_RECOVERY_VERIFIED。

### Task 2：v2 执行契约与不可变 v1 读取

**Files:** Modify `src/so101_demo_py/src/parallel_batch/contracts.py`、`journal.py`、`src/so101_demo_py/test/test_parallel_batch_contracts.py`、`test_parallel_batch_journal.py`、`test_parallel_batch_crash_recovery.py`；Create `historical_contracts.py`（同 parallel_batch 目录）、`src/so101_demo_py/config/mujoco/parallel_batch_v2.yaml`。

**Interfaces:** `BatchKindV2` 枚举 `FIRST_PASS/FULL_RESTART_RETRY/ADAPTIVE_POOL`；`BatchRequestV2(batch_id: str, run_mode: RunMode, selected_point_ids: tuple[str, ...], worker_count: int, evidence_root: Path, batch_kind: BatchKindV2, schema_version: int = 2)` 不含 K。内部 queue unit 可用小 subset；生产 selection 层对 FIRST_PASS 强制4..20+四 anchor，retry 恰一项N1。`FixedExecutionConfigV2(schema_version: int, execution_mode: str, worker_count: int)`；`ParallelRuntimeConfigV2` 保存原执行字段、封闭 measurement 规则与三 deployment refs，不含K/旧资源公式。`load_parallel_runtime_config_v2(path: Path) -> ParallelRuntimeConfigV2`；`read_historical_contract(path: Path) -> HistoricalContractView`（version、raw_sha256、readonly payload）；`require_v2_execution(request_version: int, config_version: int) -> None` 抛带 `.code` 的 `ContractError(ValueError)`。

- [ ] RED 在 contracts test 加：

```python
def test_v1_can_be_read_but_not_executed(tmp_path):
    from so101_demo.parallel_batch.contracts import ContractError, require_v2_execution
    with pytest.raises(ContractError) as error:
        require_v2_execution(1, 1)
    assert error.value.code == 'LEGACY_CONTRACT_EXECUTION_FORBIDDEN'
    with pytest.raises(ContractError):
        require_v2_execution(3, 2)
```

- [ ] `so101_pytest contracts-red src/so101_demo_py/test/test_parallel_batch_contracts.py::test_v1_can_be_read_but_not_executed -q`；预期缺 v2 version gate。
- [ ] 写 v2 closed parser，拒绝 duplicate keys/unknown/nonfinite/type drift；保存 v1 parser 和历史事件解释，不迁移旧文件：

```python
class ContractError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code

def require_v2_execution(request_version, config_version):
    if request_version != 2 or config_version != 2:
        raise ContractError('LEGACY_CONTRACT_EXECUTION_FORBIDDEN')
```

v2 `execution` 逐项复制原 timeout/lease/broker/freshness 值，新增设计冻结的计量规则；`deployment` 只允许三个键。candidate refs null 合法，production 完整性由 provider 检查。新 v2 journal/manifest/receipt 写 schema2；独立 IPC/inference child schema1 不强改其版本。
- [ ] 增加字节/hash不变测试：同 v1 read 两次 rawsha一致；v1 execute/resume/retry 拒绝；未知 schema 拒绝。GREEN：`so101_pytest contracts-green src/so101_demo_py/test/test_parallel_batch_contracts.py src/so101_demo_py/test/test_parallel_batch_journal.py src/so101_demo_py/test/test_parallel_batch_crash_recovery.py -q`。直到 composition 迁移前保留 v1 unit 路径，但不开放新生产启动。
- [ ] stage 本 task 精确文件，`git commit -m "feat(parallel): add v2 execution and readonly legacy contracts"`；保存 v1 YAML/source evidence inventory hash baseline。

### Task 3：无环 semantic identity 与 full-byte audit

**Files:** Create `src/so101_demo_py/src/parallel_batch/resource_identity.py`、`src/so101_demo_py/test/test_parallel_resource_identity.py`；Modify v2 config 与现有 `resources.py`、CLI provenance binding 的 v2 分支。

**Interfaces:** `canonical_sha256(value: object) -> str`（sorted UTF-8 JSON/noNaN）；`semantic_config_sha256(document: dict) -> str`（先 closed parse）；`InventoryEntry(logical_path: str, raw_sha256: str, semantic_sha256: str | None)`；`RuntimeFingerprint(schema_version: int, facts: dict[str, object], normalization_sha256: str, semantic_config_sha256: str, execution_inventory_sha256: str, installed_inventory_sha256: str)` 属性 `sha256`；`FullByteAudit(schema_version: int, source_commit: str, source_clean: bool, prefix: str, files: tuple[InventoryEntry, ...], origins: dict[str, str])` 属性 `sha256`。`build_runtime_fingerprint(*, config, source_inventory, installed_inventory, runtime_facts) -> RuntimeFingerprint`；`verify_deployment_equivalence(measured: FullByteAudit, deployed: FullByteAudit, measured_identity: RuntimeFingerprint, deployed_identity: RuntimeFingerprint) -> None`。

- [ ] RED 测试只用 closed synthetic config：测试内 `config(deployment)` 从仓库 v2 YAML 解析后只替换 deployment，不改 execution。

```python
def test_first_promotion_changes_audit_not_semantic_identity():
    import yaml
    from pathlib import Path
    from copy import deepcopy
    from so101_demo.parallel_batch.resource_identity import canonical_sha256, semantic_config_sha256
    path = Path(__file__).resolve().parents[1] / 'config/mujoco/parallel_batch_v2.yaml'
    candidate = yaml.safe_load(path.read_text())
    deployed = deepcopy(candidate)
    deployed['deployment'] = {'approved_profile_path': '/sealed/profile.json',
        'approved_profile_sha256': 'a' * 64, 'promotion_record_path': '/sealed/promotion.json'}
    assert semantic_config_sha256(candidate) == semantic_config_sha256(deployed)
    assert canonical_sha256(candidate) != canonical_sha256(deployed)
```

- [ ] `so101_pytest identity-red src/so101_demo_py/test/test_parallel_resource_identity.py -q`；预期 identity module 缺失。
- [ ] 最小归一化只替换精确三个 deployment values 为 `DEPLOYMENT_REFERENCE_V2`；keys保留。L 绑定算法/schema/精确 inventory 清单；source v2 config carrier 与证明的 installed share carrier 用 S，其他实际 wrapper/shebang/module/dependency/launch/Web执行contract 全部 rawbytes。docs/ledger 和根内 B/Q/P/M 不进 E/I；不可临时新增 exclude。

```python
normalized = deepcopy(document)
for key in ('approved_profile_path', 'approved_profile_sha256', 'promotion_record_path'):
    normalized['deployment'][key] = 'DEPLOYMENT_REFERENCE_V2'
return canonical_sha256(normalized)
```

- [ ] 加 safety/timeout/thread/model/estimator变化 invalid；unknown deployment key拒绝；任一 executable/wrapper byte变化 I/R变化；prefix移动只有bytes+origin闭包相同才等价。A0/A1保存原config bytes/prefix/cleancommit/所有文件，不能用S代替部署原bytes真实性。GREEN：`so101_pytest identity-green src/so101_demo_py/test/test_parallel_resource_identity.py src/so101_demo_py/test/test_parallel_batch_resources.py -q`。
- [ ] stage 精确文件，`git commit -m "feat(resources): separate semantic identity and full byte deployment audit"`；独审 L/inventory 排除表，记录 first-null→P 测试证据，不宣称真实promotion。

### Task 4：封闭资源 contexts、算术和批准链 parser

**Files:** Create `src/so101_demo_py/src/parallel_batch/resource_budget.py`、`src/so101_demo_py/test/test_parallel_resource_budget.py`；Modify `parallel_batch/resources.py` 中 allocation context 类型，旧 Task14 reader 仅留历史。

**Interfaces:** `AllocationScope(batch_id: str, epoch: int, worker_count: int, request_kind: str, execution_identity_sha256: str)`；三互斥 private-issued `FixedProductionContext/MeasurementContext/AdaptiveAllocationContext` 持 scope、authority_sha256、private issuer。`LiveResourceObservation(monotonic_s: float, capacity: dict[str,float], observed: dict[str,float], background: dict[str,float], tool_overhead: dict[str,float], remaining: dict[str,float], error: dict[str,float], attribution_complete: bool, swap_delta: int, psi_full_delta: float, throttled: bool)` 单位 RAM/GPU bytes、CPU core-equivalent。

`ResourceBudgetAdmission(admitted: bool, reason_codes: tuple[str,...], worker_count: int, profile_sha256: str | None, qualification_sha256: str | None, execution_identity_sha256: str, observation_monotonic_s: float)`。`ApprovedBudgetProfile` 保存 schema2、R、exact-N entries、Q/coverage/rawhash、stage D/J/B/H，无selfsha；`ExactNQualification` 保存 schema2/R/N/coveragepolicy/Bhashes/normal结果，无P/M/D refs；`QualificationDecision(qualified: bool, reason_codes: tuple[str,...])`。`ExactNQualificationProvider.verify(*, record, worker_count: int, execution_identity_sha256: str, coverage_policy_sha256: str) -> QualificationDecision`。

`ResourceBudgetProvider.load(path: Path, *, expected_sha256: str) -> ApprovedBudgetProfile`；`issue_production_context(*, scope, profile_path, expected_profile_sha256, promotion_path, deployment_receipt_path, control_binding) -> FixedProductionContext`；`issue_measurement_context(*, scope, authorization_path, owner_binding) -> MeasurementContext`；`admit_production(*, context, current: RuntimeFingerprint, live: LiveResourceObservation) -> ResourceBudgetAdmission`；`admit_measurement(*, context, current, live) -> ResourceBudgetAdmission`。Adaptive issuer 只在原 factory，见Task8。测试 pure helper `headroom_ok(capacity: float, observed: float, remaining: float, error: float) -> bool` 不授 authority。

- [ ] RED 加 synthetic arithmetic：

```python
@pytest.mark.parametrize('capacity,observed,remaining,error,expected', [
    (1000, 200, 600, 0, True), (1000, 200, 601, 0, False),
    (4, .4, 2.8, 0, True), (4, .4, 2.9, 0, False),
    (1000, 600, 150, 50, True), (1000, 810, 0, 0, False)])
def test_exact_twenty_percent(capacity, observed, remaining, error, expected):
    from so101_demo.parallel_batch.resource_budget import headroom_ok
    assert headroom_ok(capacity, observed, remaining, error) is expected
```

- [ ] `so101_pytest budget-red src/so101_demo_py/test/test_parallel_resource_budget.py -q`；预期新算术/provider不存在。
- [ ] 最小公式 `observed + remaining + error <= 0.8 * capacity`，拒绝nonfinite/negative需求。pre-spawn用B+H与D；in-flight用observed与remaining transition，不重复加resident D。RAM U=M-MemAvailable、PSS、cgroupcharge分别保存，U700/PSS400/charge500不是1600。CPU E取task/online/全部ancestor cpuset交集与quota最小，不用host24覆盖cpuset4。
- [ ] closed secure parser 验证 fd/O_NOFOLLOW/owner/mode/size/hash稳定、schema、exact-N/finite值、immutable sealed B/Q、coverage、独立M/D批准链；R→B→Q→P→M→A1/D，Q.verify不能接P hash，M不能指A1/D，配置不能指Mhash/Dhash。每N UNKNOWN/CANDIDATE/REJECTED/APPROVED，unknown无零需求。context issuer须外部authority每次验证，不把factorytoken当批准。
- [ ] 测试mixed/forgedcontexts、oldfalseflag、Web冒measurement、adaptive进入fixed拒绝；candidate null refs仍可独立测量，production null拒绝；missingN/N8替代N4/schema1历史资格/背景漂移/TOCTOU拒绝。GREEN：`so101_pytest budget-green src/so101_demo_py/test/test_parallel_resource_budget.py src/so101_demo_py/test/test_parallel_resource_identity.py -q`。
- [ ] scoped stage，`git commit -m "feat(resources): add exact N budget authority and admission rules"`；Astra审 closed contexts/parser/digest graph。

### Task 5：无 Web 的 measurement owner、取消与独立 watchdog

**Files:** Create `src/so101_demo_py/src/parallel_batch/measurement_control.py`、`src/so101_demo_py/test/test_parallel_measurement_control.py`；Modify `parallel_batch/web_control.py`、`runtime/parallel_processes.py`、`cli/mujoco_parallel_batch.py`；Test existing `test_parallel_batch_web_control.py`、`test_parallel_processes.py`。

**Interfaces:** `ProcessIdentity(pid: int, starttime_ticks: int, uid: int, pgid: int)`；`MeasurementOwnerBinding(authorization_sha256: str, task_id: str, campaign_id: str, batch_id: str, epoch: int, owner: ProcessIdentity, control_socket: Path, control_token_sha256: str, owned_scope_sha256: str, sampler: ProcessIdentity, abort_policy_sha256: str, events_path: Path)`。`MeasurementControl(binding, *, clock, cancel_sender, scope_verifier, containment)`；`observe_sample(sequence: int, sample_monotonic_s: float) -> None`；`check_health(now: float, *, sampler_alive: bool, endpoint_healthy: bool, breach: str | None) -> None`；`stop_requested() -> bool`；`permit_side_effect() -> None`（abort后抛ContractError）；`event_times() -> dict[str,float | None]`。`cancel_sender(binding, reason) -> dict` 使用认证闭合wire；`containment` 仅接受fresh验证ownedscope。

- [ ] RED 测试不启动 ROS，使用 fake monotonic；test 中的 sender 是记录器，真实私有socket wire另由现有server tests验证。在同文件定义完整fixture：

```python
import os
import pytest
from pathlib import Path
from so101_demo.parallel_batch.contracts import ContractError
from so101_demo.parallel_batch.measurement_control import (
    MeasurementControl, MeasurementOwnerBinding, ProcessIdentity)

@pytest.fixture
def make_control(tmp_path):
    def create():
        private = tmp_path / 'private'
        private.mkdir(mode=0o700)
        token = private / 'token'
        token.write_text('unit-only-token')
        token.chmod(0o600)
        stat = Path(f'/proc/{os.getpid()}/stat').read_text().rsplit(')', 1)[1].split()
        identity = ProcessIdentity(os.getpid(), int(stat[19]), os.getuid(), os.getpgrp())
        binding = MeasurementOwnerBinding('a' * 64, 'task-a', 'campaign-a',
            'batch-a', 1, identity, private / 'control.sock', 'b' * 64,
            'c' * 64, identity, 'd' * 64, private / 'events.jsonl')
        calls = []
        def send(owner_binding, reason):
            calls.append((owner_binding.batch_id, reason))
            return {'status': 'STOPPING', 'cleanup_receipt_sha256': None}
        control = MeasurementControl(binding, clock=lambda: 1.101,
            cancel_sender=send, scope_verifier=lambda scope: True,
            containment=lambda scope: False)
        return control, calls
    return create

def test_sampler_gap_latches_abort_without_web(make_control):
    control, calls = make_control()
    control.observe_sample(1, 1.0)
    control.check_health(1.101, sampler_alive=True, endpoint_healthy=True, breach=None)
    assert control.stop_requested()
    assert len(calls) == 1
    with pytest.raises(ContractError):
        control.permit_side_effect()
    control.observe_sample(2, 1.102)
    assert control.stop_requested()
```

- [ ] `so101_pytest control-red src/so101_demo_py/test/test_parallel_measurement_control.py -q`；预期独立control缺失。
- [ ] 首个claim/spawn前创建binding+私有endpoint，验证socket107字节/owner/mode/FD。保留schema1 STATUS/CANCEL_BATCH，server type扩到合法BatchRequestV2、拒绝adaptive；CANCEL先fsyncBATCH_STOPPING，ACK不是cleanup。20ms ownerloop独立核sample成功seq/time/PIDstart和host/device安全，gap>100ms/死亡/不可读/seq倒退锁存abort，发现→send≤50ms；超调INVALID。

```python
def permit_side_effect(self):
    if self.stop_requested():
        raise ContractError('MEASUREMENT_ABORT_LATCHED')
```

- [ ] 把统一stop predicate无条件注入broker启动warmup、worker spawn前、wait_for_children、broker retire/reload、worker recovery/readmission、finalization；bounded poll不延长deadline。独立owner monitor失联走认证取消，2s无ACK保留fence并仅fresh owned-group containment；PIDstart/PGID/containerlabel未知不signal。不改ProcessSupervisorinterrupt5/term5/kill2等原deadline。
- [ ] GREEN及回归：`so101_pytest control-green src/so101_demo_py/test/test_parallel_measurement_control.py src/so101_demo_py/test/test_parallel_batch_web_control.py src/so101_demo_py/test/test_parallel_processes.py -q`。新增 broker warmup/execution/reload 无Web RAM/GPU breach与samplerdeath取消、no replacement、owner death foreignPIDno signal、ACK超时/cleanupunknown无receipt、t_breach/detect/latch/send/ACK/goalclear/groupsgone/domainsclear/receipt各自保存。不能断言50ms物理stop。
- [ ] scoped stage，`git commit -m "feat(measurement): add owned cancellation and independent watchdog"`；checkpoint列实际stoplatency未测量，不以unitfakecall时间当host延迟。

### Task 6：采样、clock estimator 与独立候选入口

**Files:** Create `src/so101_demo_py/src/parallel_batch/resource_measurement.py`、`src/so101_demo_py/src/cli/measure_parallel_resources.py`、`src/so101_demo_py/test/test_parallel_resource_measurement.py`、`test_parallel_measurement_cli.py`；Modify `src/so101_demo_py/setup.py`。

**Interfaces:** `MeasurementAuthorization` closed schema2含UID/dispatch/task/cleancommit/R/N/cataloghash/seed/FULL_RESTART/maxbatches/batchdeadline5400/expiry/batchroot/ownedscope/safetypolicyhash/intent（CALIBRATION_ONLY或QUALIFICATION）/calibrationhash。`ResourceSample(sequence: int, monotonic_s: float, observation: LiveResourceObservation, process_inventory: tuple[ProcessIdentity,...], diagnostics: dict)`；`ClockEpoch(worker_id: str, generation: int, session_id: str, reset_epoch: str, publisher: ProcessIdentity, ros_domain_id: int)`；`ClockWindow(epoch: ClockEpoch, wall_start_s: float, wall_end_s: float, sim_start_s: float, sim_end_s: float, epsilon_t_s: float, epsilon_s_s: float, expected_pace: float, eligible: bool, phase: str, phase_started_s: float, readiness_completed_s: float, maximum_sample_gap_s: float, boundary_sample_age_s: float, clock_age_s: float)`；wall/sim delta只由绝对边界相减，不接受独立可矛盾的delta输入。

`rtf_interval(window: ClockWindow) -> tuple[float,float]`；`ClockQualification(*, lag_error_s: float, maximum_gap_s: float, maximum_boundary_age_s: float)` 保存每epoch上一完整wall边界/anchor/deficit计数；`observe(window: ClockWindow, *, cumulative_lag_s: float) -> QualificationDecision`；`sample_resources(*, owned_inventory, cgroup, device, sequence: int) -> ResourceSample`；`seal_measurement(*, authorization, identity, raw_files: tuple[Path,...], coverage_events: Path, result: dict) -> Path` 输出 B，无 P refs。console `so101_measure_parallel_resources=so101_demo.cli.measure_parallel_resources:main`；CLI `--authorization PATH --authorization-sha256 SHA --config PATH --batch-id ID --evidence-root TASK_ROOT --intent CALIBRATION_ONLY|QUALIFICATION`，N/20点/seed从授权读取，不重复接受可覆盖授权的参数。

authorization 的 `runtime_bindings` 为封闭 `MeasurementRuntimeBindings(points_path: Path, points_sha256: str, yolo_weights_path: Path, yolo_weights_sha256: str, grounded_root: Path, grounded_manifest_sha256: str, broker_image_id: str, provenance_binding_path: Path, provenance_binding_sha256: str)`。measurement入口据此生成现有composition所需points/model/broker/provenance argv（run_mode固定EXECUTE、request为v2/对应batchkind），核原bytes与R一致；不借未批准productionprofile补绑定、不接受额外env覆盖授权。

- [ ] RED测试pure interval函数（ClockEpoch使用testPIDstart合成身份）：

```python
from so101_demo.parallel_batch.measurement_control import ProcessIdentity
from so101_demo.parallel_batch.resource_measurement import (
    ClockEpoch, ClockWindow, ClockQualification, rtf_interval)

@pytest.fixture
def clock_epoch():
    return ClockEpoch('w1', 1, 'session-1', 'reset-1', ProcessIdentity(10, 20, 30, 40), 181)

def clock_window(epoch, index, sim_delta):
    return ClockWindow(epoch, float(index), float(index + 1), index * sim_delta,
        (index + 1) * sim_delta, 0.0, .002, 1.0, True, 'EXECUTING',
        0.0, 0.0, .05, .05, .05)

def test_quantized_one_x_is_not_a_deficit(clock_epoch):
    window = clock_window(clock_epoch, 0, .998)
    low, high = rtf_interval(window)
    assert low <= 1.0 <= high

def test_two_nonoverlapping_deficits_fail(clock_epoch):
    checker = ClockQualification(lag_error_s=.004, maximum_gap_s=.1, maximum_boundary_age_s=.1)
    assert checker.observe(clock_window(clock_epoch, 0, .900), cumulative_lag_s=.1).qualified
    assert not checker.observe(clock_window(clock_epoch, 1, .900), cumulative_lag_s=.2).qualified
```

- [ ] `so101_pytest measurement-red src/so101_demo_py/test/test_parallel_resource_measurement.py -q`；预期 estimator缺失。首窗qualified意为本窗未达到sustainedlag失败，不是batch资格。
- [ ] estimator完整公式 `(ds-es)/(dt+et),(ds+es)/(dt-et)`；q取冻结有效正sim_speed_factor，否则经runtime读回的UI percent/100；q/physicsstep/publisher规则进入R，不能为达标改速度。分母非正/跨epoch/gap/未知q INVALID。1s窗stride1s，以绝对边界验证同epoch前窗end=后窗start，重叠/重复窗不重复计deficit；跨phase/readiness/epoch边界不能拼窗。两独立upper<q或跨两窗累积lag越冻结误差取消。after-ready无clock/age>5s不能标idle；active AVAILABLE/INITIALIZING/EXECUTING/FINALIZING含两点间静止。startup/reset/teardown exclusion必须owner事件+原deadline；queue最老age10s、TF/RGBD原freshness和phase deadlines独立。
- [ ] sampler从spawn前至cleanup后quiet≥5s，baseline≥60s；50ms proc/cgroup/RAM/swapPSI/NVML整设备，PSS100ms，25mscrosscheck；去重PIDstart/cgroup/container inventory，全部renderer/controller/MoveIt/MuJoCo/models/broker后代。记录100ms/1s CPU窗口、effectivecpuset/祖先quota(period100000us)、throttling、memorypeak/high/max/OOM、模型queue/inference、frameage/TF/render/clock。计量toolsH不重复baseline，unknownbackground/GPUconsumer失败关闭。
- [ ] CALIBRATION_ONLY授权同candidate guard，无profile/epsilon bootstrap，输出clock原证据、不能产生RTF/normalPASS；Sol审校准后下一独立授权冻结epsilon证据hash。规则进入R，真实epsilon进B/Q/P；改误差值新资格不能回填失败。NVML/delegated cgroup缺失拒绝、不sudo创建delegation；cgroupRAM≤floor(.8M)-B-H、CPU≤.8E-B-H，GPU无硬quota时无法界定overshoot即UNKNOWN。
- [ ] GREEN：`so101_pytest measurement-green src/so101_demo_py/test/test_parallel_resource_measurement.py src/so101_demo_py/test/test_parallel_measurement_cli.py -q`。还测epochreset、no-clock、staleclock、pause未知、单次扰动不重复、nan、sampleseq只在成功后推进、25mspeakalias不能界定拒绝、exactauthN/hash/expiry/intent/replay拒绝、productioncaller不能取context、missingprofile不妨碍授权calibration。
- [ ] setup新增上述console script，按其现有config递归install机制安装v2 YAML；scoped stage，`git commit -m "feat(measurement): add raw sampler clock qualification and candidate CLI"`。

### Task 7：无配额共享队列与有限恢复收敛

**Files:** Modify `src/so101_demo_py/src/parallel_batch/coordinator.py`、`src/so101_demo_py/test/test_parallel_batch_coordinator.py`、`test_parallel_batch_fault_injection.py`。

**Interfaces:** 保留现有 `grant_lease(worker_id, *, generation, request_key)`、ACK/commit/register/recovery语义；request切BatchRequestV2/configv2。`lease_count`只新grant累计，重复request不增；v2 terminal reason用 `NO_RECOVERABLE_WORKERS`，历史CAPACITY_EXHAUSTED仍可读。

- [ ] 将现有 `make` fixture迁移v2，去参数k；继续使用已有 `start/finish/gate_summary/recover_worker`，不伪造物理资格。RED：

```python
def test_one_worker_consumes_twenty_without_lifetime_quota(make):
    points = tuple(f'p{i}' for i in range(20))
    c, clock, results, journal, request = make(points=points, workers=1)
    received, generations = [], []
    generation = 1
    for index, point in enumerate(points):
        lease = start(c, generation=generation)
        assert lease.worker_id == 'w1'
        generations.append(lease.worker_generation)
        received.append(lease.point_id)
        finish(c, results, lease, 'PASSED')
        if index != len(points) - 1:
            generation = recover_worker(c, generation=generation)
    assert received == list(points)
    snapshot = c.snapshot()
    assert snapshot.terminal_reason == 'POINTS_COMPLETE'
    assert tuple(snapshot.workers) == ('w1',)
    assert snapshot.workers['w1'].lease_count == 20
    assert snapshot.workers['w1'].generation == generation == 20
    assert generations == list(range(1, 21))
    assert snapshot.workers['w1'].state == WorkerState.RECOVERING
```

- [ ] `so101_pytest queue-red src/so101_demo_py/test/test_parallel_batch_coordinator.py::test_one_worker_consumes_twenty_without_lifetime_quota -q`；预期旧K读取/配额阻止共享队列继续grant，不把fixturemigration、错误结果enum或漏恢复造成的失败当RED。该test是fake-evidence EXECUTE scheduler回归，19次合法同slot恢复后完成20点，最后不请求obsolete generation lease；不让commit_result接受ValidationStatus、不删每点RECOVERING边界。
- [ ] 删除 `_grant_lease_outcome_locked` lease_count配额条件和 `_evaluate` K耗尽终止条件；锁内保留activelease/generation/epoch/pointselector/blocked/brokerpause/idempotency。ordered pending首项给可用worker，activelease不再领；没有active但slot可恢复等待原deadline，全部slot终止且pending才NO_RECOVERABLE_WORKERS。

```python
if worker['state'] != 'AVAILABLE':
    return {'lease': None, 'lease_grant_paused': False,
            'recovery_deadline_monotonic_s': None}
# 新 grant 的计数只在 durable LEASE_GRANTED 成功后增加；不与任何容量比较。
```

沿用现有 dict-shaped grant outcome 和前置 `_duplicate`/`_active` 重放检查，不引入新GrantOutcome类型；已占用worker保持非AVAILABLE且不能再grant。
- [ ] 加同requestkey返回同lease/count不增、线程并发无重复、完成/真实业务失败继续共享领取、brokerpause、ACK/lease/phase超时、generationfence、同slot恢复无N+1、Nslot未建立infra、无recoverableterminal测试。GREEN：`so101_pytest queue-green src/so101_demo_py/test/test_parallel_batch_coordinator.py src/so101_demo_py/test/test_parallel_batch_fault_injection.py -q`。
- [ ] scoped stage，`git commit -m "feat(parallel): remove lifetime point quota from shared queue"`；确认v2无CAPACITY_EXHAUSTED产生路径，v1readonly解释未删。

### Task 8：ADAPTIVE 兼容无 K 与专属 authority

**Files:** Modify `src/so101_demo_py/src/parallel_batch/adaptive_contracts.py`、`adaptive_runner.py`、`adaptive_pool.py`、`src/so101_demo_py/test/test_parallel_adaptive_contracts.py`、`test_parallel_adaptive_pool.py`、`test_parallel_adaptive_runner.py`、`test_parallel_adaptive_integration.py`。

**Interfaces:** 原 factory `_new_pool_request_for_production_factory(*, batch_id, run_mode, selected_point_ids, worker_count, evidence_root) -> PoolRequest` 去K；PoolRequest v2与BatchRequestV2共享noK字段，只factory可签发。`ProductionAdaptivePoolFactory.issue_allocation_context(*, scope: AllocationScope, pool_token: str, pool_generation: int, frozen_options) -> AdaptiveAllocationContext` 核原authority；allocator只接受typedcontext，不再接受genericfalseflag。

- [ ] RED在adaptivecontracts原合法factoryfixture上加：

```python
def test_pool_contract_has_no_lifetime_quota(tmp_path):
    from so101_demo.parallel_batch.adaptive_contracts import _new_pool_request_for_production_factory
    request = _new_pool_request_for_production_factory(batch_id='pool-a',
        run_mode=RunMode.EXECUTE, selected_point_ids=('p1', 'p2'), worker_count=2,
        evidence_root=tmp_path)
    assert not hasattr(request, 'max_points_per_worker')
```

- [ ] `so101_pytest adaptive-red src/so101_demo_py/test/test_parallel_adaptive_contracts.py::test_pool_contract_has_no_lifetime_quota -q`；预期factory仍requiredK。
- [ ] 去factory/runner `max(1,len(selected))`和pool K比较，不改变initial_points_per_worker affinity、fallback/minN/ready/cleanup/infraattempts。原 `enforce_resource_thresholds=False` 调用只改为factory-issuedadaptivecontext，不引入fixedprofile、不开放measurement。
- [ ] GREEN：`so101_pytest adaptive-green src/so101_demo_py/test/test_parallel_adaptive_contracts.py src/so101_demo_py/test/test_parallel_adaptive_pool.py src/so101_demo_py/test/test_parallel_adaptive_runner.py src/so101_demo_py/test/test_parallel_adaptive_integration.py -q`；显式测旧affinity/fallback、token/generation mismatch、adaptivecontext进入fixed拒绝、fixednulldeployment不阻塞adaptive自身合法准入。
- [ ] scoped stage，`git commit -m "refactor(adaptive): use no quota contract and typed allocation scope"`。

### Task 9：teleop API/preflight/owner/store 与人工单点 N1

**Files:** Modify `src/so101_teleop/so101_teleop/expert_validation/{api,models,preflight,coordinator,supervisor,production,adaptive,statistics,store}.py`；Test existing `src/so101_teleop/test/teleop/test_expert_validation_{api,preflight,supervisor,store,statistics,production_projection}.py`；Create `src/so101_teleop/test/teleop/test_expert_validation_v2_contract.py`，用 `so101_add_pytest_test(test_expert_validation_v2_contract test/teleop/test_expert_validation_v2_contract.py)` 注册CMake。

**Interfaces:** 新 start/preflight top-level `contract_version: Literal[2]`；内fixedexecutionconfig schema_version2，仅mode/N。`CampaignStartRequest`、`CoordinatorStartRequest`、canonical hash、argv去K并加入version/batchkind/profilehash/Qhash/Rhash与观测时间绑定。`WorkerCountAvailability(worker_count: int, selectable: bool, status: str, reason_codes: tuple[str,...], profile_sha256: str | None, qualification_sha256: str | None)`；capabilities输出N2..8availability，无fixed_max_points_per_worker。historyprojection可显示原K但不作为newworker字段；v2worker只lease_count。

- [ ] legacy key在Pydantic解析前检测presence（而非value），新API统一HTTP422 detail.code；v1新start/resume/retry HTTP422独立code。RED用原APItest的client/authfixtures，合法body从现有fixture取并改contract_version2、删K：

```python
@pytest.mark.parametrize('legacy_value', [1, 20, None])
def test_new_request_rejects_legacy_key(tmp_path, legacy_value):
    client = _client(tmp_path)
    body = {'contract_version': 2, 'service_session_id': 'browser-a',
        'lease_id': 'lease-a', 'lease_generation': 1, 'manifest_id': 'manifest-20',
        'execution_mode': 'PARALLEL', 'worker_count': 2, 'command_id': 'start-a',
        'preflight_receipt_id': 'receipt-a', 'max_points_per_worker': legacy_value}
    response = client.post('/expert-validation/campaigns', json=body)
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'LEGACY_MAX_POINTS_PER_WORKER_UNSUPPORTED'
```

这段test写入现有 `test_expert_validation_api.py`，沿用真实 `_client(tmp_path)`/Service helper，不依赖跨文件隐式fixture。新v2_contract测试用于closedmodel/历史read边界；不能弱化lease要求，legacy key验证在调用service前完成。
- [ ] `so101_pytest teleop-v2-red src/so101_teleop/test/teleop/test_expert_validation_api.py::test_new_request_rejects_legacy_key src/so101_teleop/test/teleop/test_expert_validation_v2_contract.py -q`；预期legacy key仍被接受/错误未分类。
- [ ] 新fixedpreflight去ceilK/Capacity比较，selection4..20+anchors不变；生成version2/hash/资源receipt；store新增version-aware reader/writer，不UPDATE旧请求/历史row或重新计算旧hash。supervisor `_owner_request`去K；retryqueue固定 `FixedExecutionConfigV2(2,'SEQUENTIAL',1)`、BatchKindV2.FULL_RESTART_RETRY、一point、新batch/控制token，保持先cleanup再nextretry。

```python
if 'max_points_per_worker' in payload:
    raise HTTPException(status_code=422, detail={'code': 'LEGACY_MAX_POINTS_PER_WORKER_UNSUPPORTED'})
```

- [ ] GREEN：`so101_pytest teleop-v2-green src/so101_teleop/test/teleop/test_expert_validation_v2_contract.py src/so101_teleop/test/teleop/test_expert_validation_api.py src/so101_teleop/test/teleop/test_expert_validation_preflight.py src/so101_teleop/test/teleop/test_expert_validation_supervisor.py src/so101_teleop/test/teleop/test_expert_validation_store.py src/so101_teleop/test/teleop/test_expert_validation_statistics.py src/so101_teleop/test/teleop/test_expert_validation_production_projection.py -q`。验证firstpass/retry分母独立、v1readonly/新exec禁止、N1同provider、requestedN不改成2/ADAPTIVE、旧receipthash不变。
- [ ] scoped stage，`git commit -m "feat(teleop): expose v2 no quota campaigns and isolated single point retries"`。

### Task 10：三消费者同 provider、spawn 前复核与 CLI 错误

**Files:** Modify `src/so101_teleop/so101_teleop/expert_validation/production.py`、`src/so101_demo_py/src/cli/mujoco_parallel_batch.py`、`parallel_batch/resources.py`；Test `test_parallel_batch_resources.py`、`test_parallel_resource_probe_races.py`、`test_parallel_batch_cli.py`；Create `src/so101_teleop/test/teleop/test_expert_validation_resource_budget.py`，用 `so101_add_pytest_test(test_expert_validation_resource_budget test/teleop/test_expert_validation_resource_budget.py)` 注册CMake。

**Interfaces:** `_HostResourceProbe.probe`、`_prepare_live_headroom`、`WorkerResourceAllocator._live_headroom/allocate/adopt_existing` adapter都接同 `ResourceBudgetProvider`、RuntimeFingerprint、liveprobe和scope，不各算公式。真实restore入口 `adopt_existing(manifest: ResourceManifest) -> ResourceManifest` 的v2分支也去掉其独立CPU/RAM/GPU旧公式；先验证manifestversion、exactN/paths/environment/originalprovenance/controlscope，再走同provider/currentprobe，不能只更新allocate。`SystemResourceProbe.snapshot() -> LiveResourceObservation` 的v2分支证明effectivecpuset/quota/wholedevice/背景归属；v1reader保留原ResourceSnapshot解释，但新adopt/execute拒绝v1。`AllocationPolicy`去genericenforcefalse，allocation需typedcontext。新CLI `--contract-version 2 --batch-kind FIRST_PASS|FULL_RESTART_RETRY`；resume首先读manifestversion，不把v1迁成2。

- [ ] RED使用现有resource/CLI fakeprobefixture加 spyprovider（记录profile/Q/R/N/scope和admission），同一syntheticN4 profile三个adapter都得到相同拒绝code；不得靠真实主机N4测试离线unit。CLI test：

```python
def test_legacy_cli_flag_is_an_explicit_error():
    from so101_demo.cli.mujoco_parallel_batch import prepare_batch
    with pytest.raises(ContractError) as error:
        prepare_batch(['--max-points-per-worker', '20'])
    assert error.value.code == 'LEGACY_MAX_POINTS_PER_WORKER_UNSUPPORTED'
```

- [ ] `so101_pytest adapters-red src/so101_demo_py/test/test_parallel_batch_cli.py::test_legacy_cli_flag_is_an_explicit_error src/so101_teleop/test/teleop/test_expert_validation_resource_budget.py -q`；预期旧flag仍参与config/配额，或N>3硬拒绝未走provider。
- [ ] 在required argparse参数处理前仅识别legacy flag并明确错误（不保留activeK参数）；删除三处N>3reject/N3specialliveverifier和allocate4N/6+4N/GPU8公式的新执行路径。typedmeasurement走独立safetyauthority，无P要求；typedadaptive保原strategy；fixed三adapter核同version/hash/Q/R/lease。生产actualspawn前重新probe+receiptTOCTOU绑定，选N无降级。
- [ ] 在现有resources test中添加 `test_v2_adopt_existing_rechecks_budget_and_provenance`：用现有allocator/manifest fixture迁v2，同P/Q/R+live可用时restore exactN；随后fakeprobe增background或替换manifestR，分别断言同provider的BACKGROUND_ENVELOPE_EXCEEDED/RUNTIME_FINGERPRINT_MISMATCH且无新domainclaim/spawn；v1manifest明确LEGACY_CONTRACT_EXECUTION_FORBIDDEN。spyprovider记录adopt不是allocate专属分支。
- [ ] GREEN：`so101_pytest adapters-green src/so101_demo_py/test/test_parallel_batch_cli.py src/so101_demo_py/test/test_parallel_batch_resources.py src/so101_demo_py/test/test_parallel_resource_probe_races.py src/so101_teleop/test/teleop/test_expert_validation_resource_budget.py -q`。测试profile读期间replacement、configbytes变/R不变仅allowedrefs、未allowedruntimebyte变、背景/swapPSI、N3无特判、N4/N8离线fixture各自Q、缺N拒绝、controlleaseexpiry、preflight→spawn drift及adopt_existing独立旧公式已移除。
- [ ] scoped stage，`git commit -m "feat(resources): unify production CLI Web and allocator budget gates"`；三consumer闭包独审，profile文件存在本身不够授权。

### Task 11：OpenAPI、Web 无 K UI 与 contract/installed tests

**Files:** Modify `src/so101_teleop/so101_teleop/openapi_export.py`、`expert_validation_openapi.json`；web `src/api/{expert-validation-schema.d.ts,expert-validation-types.ts,expert-validation-client.ts,expert-validation-client.test.ts}`、`src/expert-validation-app.tsx`、`src/expert-validation-app.test.tsx`、`src/components/expert-validation/{campaign-setup,campaign-progress,components.test}.tsx`、`src/state/expert-validation-store{,.test}.ts`；web `e2e/expert-validation/pages/expert-validation-page.ts`、`contract/{setup,live-preflight}.spec.ts`、`installed/support.ts`、`installed/{retry-queue,api-contract,entry-and-campaign,lease-recovery}.spec.ts`、`fixtures/{installed,live-sim}.ts`；teleop `test/e2e/{execution_port,scripted_service,installed_test_launcher}.py`、`test/e2e/process_helpers/fixed_helper.py`、`test/fixtures/expert_validation_e2e/scenario.schema.json`及现有scenarios；Test `src/so101_teleop/test/teleop/test_openapi_export.py`。

**Interfaces:** `ExpertValidationPage.configureParallel(workerCount: number): Promise<void>` 去K；UI availability来自Task9，保requestedN+selection，不客户端改mode/N。`lease_count`文案“累计领取”，无 `/K`；原Capacity位置“共享队列 · 每 worker 一次一任务”+profile/qualification reason。v1历史opaqueevidence不重新生成。

Stage A修复fixture两packageoverlay映射：`resolvePackagePrefixes(overlayPrefix: string, verifiedDependencyPrefix: string): string[]` 放 `fixtures/installed.ts`并由live-sim复用；overlay只解析so101_demo_py/so101_teleop，不fallback。其余 `mujoco_3d_lidar/mujoco_ros2_control_msgs/mujoco_ros2_control_plugins/mujoco_ros2_control/so101_mujoco_support` 精确来自Task0核验的 `/data/work/ws_moveit/install/<package>`，最后ROS为 `/opt/ros/jazzy`。每个prefix缺失或origin/库闭包hash与审计不符拒绝，不能用filter静默丢包。child的AMENT_PREFIX_PATH、存在的python site paths和LD_LIBRARY_PATH按此mapping重建；ROS overlay paths之后append精确TEST_SITE以保证Pydantic2，并读回两个产品module来自对应copiedoverlay、其余support origins来自审计underlay。installed_test_launcher的bootstrap保留这五个已验证dependency路径，不再宽泛删所有含ws_moveit的路径；产品imports仍禁止来自canonical/source/devsymlink。

fixtures启动child前验证 `SO101_E2E_INSTALL_PREFIX`、`SO101_E2E_PYTHON`、`SO101_VALIDATION_PROVENANCE_BINDING`、`SO101_VALIDATION_PARALLEL_CONFIG`；不能让QUALIFICATION_ENV的旧fixedacceptance/旧config默认值覆盖v2 bindings。offline只有现有typedtestentry可注入syntheticprovider/authority，与生产launcher分离；live使用真实P/Q/M/D，无testport或legacyfixed资格。adaptive原独立qualification引用保留。

- [ ] RED在app/components现有renderfixtures改v2后加：

```tsx
expect(screen.queryByLabelText('Max points per worker')).toBeNull()
expect(screen.queryByText(/^Capacity/)).toBeNull()
expect(screen.getByText('共享队列 · 每 worker 一次一任务')).toBeTruthy()
```

- [ ] `cd src/so101_teleop/web` 后 `so101_bun web-ui-red run test src/expert-validation-app.test.tsx src/components/expert-validation/components.test.tsx`；预期旧K/Capacity仍显示。升级offlineharnessfixtures不能删legacyreadonlyfixtures；syntheticapprovedprofile只用于contract/installedfakechild，不是production证据。
- [ ] 从repo根用dev overlay精确Python导出，再生成types：

```zsh
"$TEST_PYTHON" -m so101_teleop.openapi_export --validation src/so101_teleop/so101_teleop/expert_validation_openapi.json
cd src/so101_teleop/web
so101_bun api-types run generate:api:validation
so101_bun web-unit run test
so101_bun web-build run build
so101_bun contract-setup run test:e2e e2e/expert-validation/contract/setup.spec.ts e2e/expert-validation/contract/live-preflight.spec.ts
```

- [ ] 用`so101_pytest openapi-green src/so101_teleop/test/teleop/test_openapi_export.py -q`验证generatedschema。将offlineN2..8 options参数化，UNKNOWNdisabled+原因，qualified可选；4/20点、anchors、requestedN、无Kbody/nullK错误、refresh/leaseexpiry、retryN1/独立统计全测。installed fakechild gate移到Task12 Stage B前段，在全部Stage A代码clean后从offlinecopiedoverlay运行，不能用devsymlink冒充copiedorigin。Python E2E helper起pytest/colcon也必须独立NVMe scratchproof，不借Bun包装逃规则。
- [ ] scoped stage上述生成与source/test文件，`git commit -m "feat(web): replace capacity input with exact N resource availability"`；独审API/types与历史fixture边界。

### Task 12：完整 gate、clean copy install 与在线恢复前置

**Files:** Modify task ledger；代码若gate发现问题回到原task修复，不在此宽泛混合修复。Artifacts：`$TASK_ROOT/offline-build`、`offline-install`、`production-build`、`production-install`、A0、install/layout/provenance receipts。

**Interfaces:** production 使用cleancommit copiedoverlay（无symlinkinstall），`ProductionRuntimeLayout`与strictsourceidentity绑定实际exe/config/modules/assets和dependencyorigins。候选/生产P/Q绑定以后使用该冻结运行文件inventory，不用devsourcepytest文件冒充installedruntime。

**Entry gate:** 已完成Stage A全部离线实现，包括Task13聚合器、Task14promotion/deploymentparser、Task15verifier。此Task是唯一首次现场测量前的最终runtimecodefreeze，不能先冻结后再继续这些任务的代码步骤。

- [ ] Stage B首先在所有Stage A代码已提交/clean后，logged rebuild/reconfigure Task0的dev tree，保留symlink-install并刷新CMake cache；不能直接用Task0旧CTest树声称full gate：

```zsh
so101_colcon final-dev-reconfigure build --packages-select so101_demo_py so101_teleop --allow-overriding so101_demo_py so101_teleop --symlink-install --cmake-clean-cache --build-base "$TASK_ROOT/dev-build" --install-base "$TASK_ROOT/dev-install"
source "$TASK_ROOT/dev-install/setup.zsh"
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$TEST_SITE"
CTEST_REGISTRATION_RUN=$(mktemp -d "$TASK_ROOT/colcon/ctest-registration.XXXXXXXX")
so101_record_tool "$CTEST_REGISTRATION_RUN" ctest --test-dir "$TASK_ROOT/dev-build/so101_teleop" --show-only=json-v1
"$TEST_PYTHON" -c 'import json,sys; from pathlib import Path; tests=json.load(open(sys.argv[1]))["tests"]; required={"test_expert_validation_operator_recovery","test_expert_validation_v2_contract","test_expert_validation_resource_budget"}; assert required <= {t["name"] for t in tests}; exes=set(); [exes.update([t["command"][0], t["command"][t["command"].index("--command")+1]]) for t in tests if "--command" in t["command"]]; assert exes and all(Path(p).is_absolute() for p in exes); print("\n".join(sorted(exes)))' "$CTEST_REGISTRATION_RUN/stdout.log" > "$CTEST_REGISTRATION_RUN/interpreters.txt"
```

逐项核新CTest registrations包含Task1/9/10全部新增测试和StageA修改的existing测试；上面三个required名称与各task注册一致。由fresh生成的command派生实际exe，连同demo ament_python gate interpreter核对Task0登记列表；新增exe先核origin/Pydantic并登记，未核实则拒绝。此时再执行`so101_pytest full-demo src/so101_demo_py/test`、`so101_pytest full-teleop src/so101_teleop/test`和WebTask11fullgate。之后每个colcon gate各取新NVMe scratch/三TEMP/精确Pythonproof/elapsed/exit；执行：

```zsh
rg -n 'Python3.*EXECUTABLE|--command.*python3' "$TASK_ROOT/dev-build/so101_teleop/CMakeCache.txt" "$TASK_ROOT/dev-build/so101_teleop/CTestTestfile.cmake"
for test_interpreter in "${COLCON_TEST_PYTHONS[@]}"; do
  "$test_interpreter" -c 'import pydantic,pytest,sys; assert int(pydantic.__version__.split(".")[0])==2; print(sys.executable,pydantic.__version__,pydantic.__file__)'
done
so101_colcon full-demo-colcon test --packages-select so101_demo_py --build-base "$TASK_ROOT/dev-build" --install-base "$TASK_ROOT/dev-install" --return-code-on-test-failure --pytest-args test
so101_colcon full-teleop-colcon test --packages-select so101_teleop --build-base "$TASK_ROOT/dev-build" --install-base "$TASK_ROOT/dev-install" --return-code-on-test-failure
so101_colcon full-test-result test-result --test-result-base "$TASK_ROOT/dev-build" --verbose
```

上述command读回先与已登记exe列表核对；任何未登记interpreter、错误Pydantic或dependencyorigin立即停止，不能继续后补proof。两次colcon各用新scratch，helper同时用venv和真实colcon/CTest `/usr/bin/python3` 证明tempfile；保存CTest/colcon module origin和实际JUnit。禁止benchmark默认收集。
- [ ] Stage A全部代码审查/提交且sourceclean后，构建专门offlinecopiedoverlay并生成Task3定义的v2 external binding到 `$TASK_ROOT/bindings/offline-provenance.json`，保存raw audit/origins；禁止绕过copy-origin检查。web目录执行以下已核验环境/installed gate，每个so101_bun调用自动注册新的绝对evidence root并保存stdout/stderr/exit/report：

```zsh
so101_colcon offline-copy-build build --packages-select so101_demo_py so101_teleop --allow-overriding so101_demo_py so101_teleop --build-base "$TASK_ROOT/offline-build" --install-base "$TASK_ROOT/offline-install"
source "$TASK_ROOT/offline-install/setup.zsh"
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$TEST_SITE"
export SO101_E2E_INSTALL_PREFIX="$TASK_ROOT/offline-install"
export SO101_E2E_PYTHON="$TEST_PYTHON"
export SO101_VALIDATION_PROVENANCE_BINDING="$TASK_ROOT/bindings/offline-provenance.json"
export SO101_VALIDATION_PARALLEL_CONFIG="$SO101_E2E_INSTALL_PREFIX/so101_demo_py/share/so101_demo_py/config/mujoco/parallel_batch_v2.yaml"
cd "$WORKTREE/src/so101_teleop/web"
so101_bun installed-contract run test:e2e:installed e2e/expert-validation/installed/api-contract.spec.ts e2e/expert-validation/installed/retry-queue.spec.ts e2e/expert-validation/installed/entry-and-campaign.spec.ts e2e/expert-validation/installed/lease-recovery.spec.ts
cd "$WORKTREE"
```

生成binding、读回module/config/hash与approvedunderlay闭包后才运行installedgate；sourceclean不等于runtimequalified，typedfakeevidence不进真实资格。binding若缺失、不对应该copy或仍v1则失败关闭。offlinegate结束重新fresh shell sourceROS/canonical，再构建production，不把offlineprefix残留进生产R。
- [ ] scoped code已审且cleancommit后构建productioncopyoverlay：

```zsh
so101_colcon production-copy-build build --packages-select so101_demo_py so101_teleop --allow-overriding so101_demo_py so101_teleop --build-base "$TASK_ROOT/production-build" --install-base "$TASK_ROOT/production-install"
source "$TASK_ROOT/production-install/setup.zsh"
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$TEST_SITE"
```

证明两packageorigin/config/wrapper/shebang/import/dependency闭包，installedrecoveryentry可用、无dirtyidentity；若path改变生成wrapperbytes使I/R改变，先freeze最终prefix再测量。先提交所有待提交checkpoint/sourceledger，再按通用边界规则生成该clean HEAD的A0和真实production external binding，对应candidate/nullrefs copiedconfig原bytes；root内使用新唯一immutable路径并选择 `ACTIVE_PROVENANCE_BINDING`。不能先生成binding后commit账本再沿用旧 `source_commit`。选择到owned server spawn间HEAD不变，变化则保留旧记录并重新审计/选择。
- [ ] 获独占离线恢复/部署窗口后 freshstore/supervisorlock/PIDstart/container/domain验证；使用已有成功commandID做preview/幂等回读，不反复apply重写原报告。campaign1be2…/b2bd8及65c94…/b3ac4的完整ID、command/config路径从实际receipt读回，不能凭短ID或本计划猜测。保originalfences/historyhash；恢复未知/livelock失败关闭。不能删failedattempt。
- [ ] 刷新ownedWeb前再次核service存在否/为何停/最新owner，并执行通用pre-boundary audit/选择fresh binding。既有foreignserver保留；仅批准owned新启动或ownedrefresh才启动安装launcher。`SO101_VALIDATION_PROVENANCE_BINDING="$ACTIVE_PROVENANCE_BINDING"`；`SO101_VALIDATION_EVIDENCE_ROOT`=原根，`SO101_VALIDATION_BIND=100.82.102.56`、`SO101_VALIDATION_PORT=8000`，`SO101_VALIDATION_WEB_ROOT`=已审Webdist；`SO101_VALIDATION_PARALLEL_CONFIG`显式指最终installedshare v2 YAML，不能落入旧v1默认值。其他layout环境逐项由现有`ProductionRuntimeLayout.discover(environment: Mapping[str,str])`真实接口生成，不猜flags。启动`production-install/so101_teleop/lib/so101_teleop/so101_expert_validation_server.py`于task-ownedtmux。
- [ ] fresh读回URL/servedassethash/processstart/installedmodule/storefence/controllease、新owner和恢复entry证明；未完成仅OFFLINE_RECOVERY_VERIFIED/PENDING_REFRESH，不标ONLINE_RECOVERY_VERIFIED。不把v1history可恢复当新v1execution可用。回滚只限本轮ownedservice，旧消失PID不是回滚目标。
- [ ] 更新ledger/checkpoint后提交仅ledger：`git add docs/experiments/so101-parallel-unbounded-queue-resource-budget-experiment-ledger.md`，`git commit -m "docs: record clean install and owned recovery verification"`。此commit后、Stage C下一batch前必须再执行通用metadata-only refresh：新audit/binding对应新clean HEAD、R/install不变、下一authorization绑定新audit后才seal；Task12旧binding/A0/恢复receipts保留。未批准窗口则在此暂停，不能先启动measurement绕过前置。

### Task 13：exact-N 资格聚合与有限实测矩阵

**Files:** Modify `resource_measurement.py`、`resource_budget.py`（demo parallel_batch目录）；Create `src/so101_demo_py/test/test_parallel_exact_n_qualification.py`；Artifacts 原根内每N calibration/normal/coverage/fault独立batch、sealedB、Q、候选P；task ledger。

**Interfaces:** `CoverageCell` 枚举设计八cell；`RunEvidence(batch_id: str, worker_count: int, execution_identity_sha256: str, validity: str, outcome: str, full_restart: bool, point_count: int, actual_worker_identities: tuple[ProcessIdentity,...], concurrent_window: tuple[float,float] | None, coverage: dict[str,tuple[str,...]], sealed_manifest_sha256: str, independent_physics_verified: bool, resource_contract_verified: bool, cleanup_verified: bool)`。`QualificationAccumulator(worker_count: int, execution_identity_sha256: str, coverage_policy_sha256: str)`；`add_normal(run: RunEvidence) -> None`、`add_coverage(run: RunEvidence, *, fast_channel: bool) -> None`、`add_fault(run: RunEvidence) -> None`、`decision() -> QualificationDecision`、`seal_index(path: Path) -> ExactNQualification`。`build_candidate_profile(*, identity, qualifications, covered_demands, uncertainty, baseline, audits) -> ApprovedBudgetProfile` 只CANDIDATE，无operatorapproval。

- [ ] Stage A RED在新test定义`normal_run`完全synthetic，不与真实host混用：

```python
from so101_demo.parallel_batch.measurement_control import ProcessIdentity
from so101_demo.parallel_batch.resource_identity import canonical_sha256
from so101_demo.parallel_batch.resource_measurement import RunEvidence, QualificationAccumulator

def normal_run(index, outcome='FAILED', coverage=None):
    return RunEvidence(f'normal-{index}', 2, 'a' * 64, 'VALID', outcome,
        True, 20, (ProcessIdentity(101, 1, 1000, 101), ProcessIdentity(102, 1, 1000, 102)),
        (1.0, 2.0), coverage or {}, canonical_sha256({'synthetic_batch': index}),
        True, True, True)

def test_five_valid_business_failures_do_not_fill_motion_coverage():
    q = QualificationAccumulator(2, 'a' * 64, 'b' * 64)
    for i in range(5):
        q.add_normal(normal_run(i, coverage={'STEADY_YOLO': ('observed',)}))
    decision = q.decision()
    assert not decision.qualified
    assert 'COVERAGE_INCOMPLETE' in decision.reason_codes
```

- [ ] `so101_pytest qualification-red src/so101_demo_py/test/test_parallel_exact_n_qualification.py -q`；预期聚合器缺失。另加fault不进normal分母、validFAILED延长resource非productstreak、infra/unknown终止streak、N8不能验证N4、实际N不足/4点N8不能计20点资格、reloadpeak抬envelope、Q禁止P反向refs。
- [ ] 最小实现normal至少5连续VALID FULL_RESTART20point+actualN+同R+独立物理/resource/cleanup；businessPASSED独立计productsuccess。每cell≥2独立实验且50/25mscrosscheck，steadycell≥5完整eligibleclockwindows；早失败NOT_REACHED不能补motion/release。fault有效peaks进同D/J而不进normal/product分母；unknown/unboundedfault不支持上界。
- [ ] Stage A GREEN：`so101_pytest qualification-green src/so101_demo_py/test/test_parallel_exact_n_qualification.py src/so101_demo_py/test/test_parallel_resource_measurement.py src/so101_demo_py/test/test_parallel_resource_budget.py -q`；scoped stage两源与新test，`git commit -m "feat(qualification): separate normal validity coverage and fault envelopes"`。继续完成Task14/15离线部分，再进入Task12统一冻结，不在此提前实测。
- [ ] Stage C 仅在Task12完整freeze/恢复前置和candidate owned窗口通过后，先N1独立资格或经审可验证等价证据，随后N2..8逐档。每batch先执行通用pre-boundary rule（包括Task12末账本commit后的首次batch），核clean HEAD/R/install，选择fresh immutable audit/binding，再为下一batch sealing authorization绑定精确HEAD/audit/path/hash。每batch授权精确N/20points/seed/intent/maxbatches/expiry/5400s/abortpolicy/R；可复用已批准authscope内有限实验，但metadata HEAD变化必须新sealedauthorization，不能改旧授权/测量。不自动循环直到PASS。按授权执行：

```zsh
"$TASK_ROOT/production-install/so101_demo_py/lib/so101_demo_py/so101_measure_parallel_resources" --authorization "$MEASUREMENT_AUTHORIZATION" --authorization-sha256 "$MEASUREMENT_AUTHORIZATION_SHA256" --config "$V2_RUNTIME_CONFIG" --batch-id "$AUTHORIZED_BATCH_ID" --evidence-root "$TASK_ROOT" --intent CALIBRATION_ONLY
```

这四变量必须从sealedauthorization和实际installedshare读回并在checkpoint登记，不能随手export绕过authority。校准审查后新独立授权把intent改QUALIFICATION；每batch另ID/path，证明TUI接收执行/实际slot启动而非commanddispatchreceipt。
- [ ] 每档执行设计八cell：coldstart、YOLO、GroundedSAM真实fallback、mixed模型+Nrender overlap、真实motionrelease、旧broker已退而Nresident的reload、同slot旧worker已死而N-1resident的recovery、finalizationcleanup。实际支持路径不扩queue/inflight、不改物理/速度。normal5和额外coverage/fault有限数量先写授权，缺cell则NOT_COVERED不能promotion。
- [ ] fault矩阵含broker退出/queue超时、heartbeat/startup、staleTF/RGBD/render压力、RAM/GPU侵蚀、samplerdeath/gap、cleanupunknown、profile/runtime漂移、取消/restart/leaseexpiry；压力只能本ownedscope内事前批准，不能压foreignconsumer。不确定peakalias、PSSoverhead、GPUovershoot/background归属则UNKNOWN/REJECTED，触安全包络后不继续升N。
- [ ] 每点原policy+MoveIt/controller/joint/TF、MuJoCo cup pose/supportcontact/gravity/releaseepoch、shadowdetach/worldsync、freshRGBD/render/finalscreenshot独立验证。DONE/旧结果不能替代；report分resource_qualified/product_qualification_passed。保存raw50/25ms、seq/gaps、B/H/D/J和stop各时刻，产Q/P仍候选。Sol/high审原证据，ledgercheckpoint逐档reason，不宣称所有N可用。

### Task 14：独立批准、promotion 与生产实时准入

**Files:** Modify `resource_budget.py` 的批准/部署验证（若Task4测试覆盖已满足则不新增源变更）；Create `src/so101_demo_py/test/test_parallel_budget_promotion.py`；Artifacts根内P、独立review、operatorapproval、M、A1、D；config仅部署refs发布；ledger。

**Interfaces:** `PromotionAuthority` 为独立批准读取器（不从candidatetree取得）；`publish_promotion(*, profile_path: Path, profile_sha256: str, operator_approval: Path, sol_result_review: Path, astra_profile_review: Path, measurement_audit: FullByteAudit, destination: Path) -> Path` 输出immutableM；`verify_promotion(*, profile, promotion_path, authority: PromotionAuthority) -> None`；`build_deployment_receipt(*, promotion_path, profile_sha256, installed_audit: FullByteAudit, identity: RuntimeFingerprint, location_binding: dict) -> Path` 输出D。M只绑定P/A0/review/operator，D绑定M/P/A1/location，M不引用D/A1。

- [ ] Stage A RED用Task4安全读取syntheticprofile/authorityfixtures，test本地操作员approval文件独立于candidate。`candidate_profile` fixture用schema2/CANDIDATE/R='a'*64、N2、五syntheticB/Q和八cell覆盖构造，所有数值标synthetic；`authority` fixture为私有tmp_path下的独立操作员批准目录读取器，candidate目录不在信任根中：

```python
def test_candidate_review_is_not_operator_promotion(candidate_profile, authority):
    with pytest.raises(ContractError) as error:
        verify_promotion(profile=candidate_profile, promotion_path=None, authority=authority)
    assert error.value.code == 'BUDGET_PROFILE_UNAVAILABLE'
```

- [ ] `so101_pytest promotion-red src/so101_demo_py/test/test_parallel_budget_promotion.py -q`；预期独立authority/首次发布链缺失或candidate可自批。
- [ ] 实现append-onlyM和D、安全读引用/hash一致、exactN批准范围，生产context必须P/Q/R/M/D一致。测试firstnullcarrierrefs→Psha/Mpath只改变A1原bytes不改变R；execution安全字段/exebytes变必须新R资格；M不存在/过期/错operatorUID/错N/Psha拒绝；Q无P逆向hash、M无A1/D。
- [ ] Stage A GREEN：`so101_pytest promotion-green src/so101_demo_py/test/test_parallel_budget_promotion.py src/so101_demo_py/test/test_parallel_resource_identity.py src/so101_demo_py/test/test_parallel_resource_budget.py -q`。scoped stage resource_budget.py和新test，`git commit -m "feat(resources): verify independent promotion and deployment authority"`，必须在Task12统一冻结前完成。
- [ ] Stage D Sol/high结果review+Astra/high profile/proposal/parser规则独审后，向操作员请求明确profilehash/exactN批准；未批准不写APPROVED M。用户“执行计划”不是promotion批准。此阶段只运行已freeze parser，不新增执行code。
- [ ] 获明确exactN/Psha批准后先生成immutable M，绑定P/A0/独立review/operator；M不引用后续A1/D。以下顺序不能交换：
  1. `apply_patch`只改source carrier的 `approved_profile_path/approved_profile_sha256/promotion_record_path`，回读三refs/closedparser/S；root内写deployment checkpoint，暂不修改trackedledger造成dirty。
  2. review scoped diff后 `git add src/so101_demo_py/config/mujoco/parallel_batch_v2.yaml`，`git commit -m "chore(resources): bind independently approved budget deployment"`，证明source trackedclean并登记新commit。此commit先于A1/D，不在审计后补commit。
  3. 获拥有的部署窗口、禁止新batch/已安全quiesce ownedconsumer后，只publish copiedinstalled carrier。先核精确target不是symlink、owner/mode和原A0 bytes，保留可回滚原bytes；执行包装发布，不重建wrapper/模块：

```zsh
export SOURCE_V2_CARRIER="$WORKTREE/src/so101_demo_py/config/mujoco/parallel_batch_v2.yaml"
export INSTALLED_V2_CARRIER="$TASK_ROOT/production-install/so101_demo_py/share/so101_demo_py/config/mujoco/parallel_batch_v2.yaml"
METADATA_PUBLISH_BATCH=$(mktemp -d "$TASK_ROOT/deployments/carrier-publish.XXXXXXXX")
printf '%s\n' "$METADATA_PUBLISH_BATCH" >> "$TASK_ROOT/run-index.txt"
cp -p -- "$INSTALLED_V2_CARRIER" "$METADATA_PUBLISH_BATCH/carrier-before.yaml"
install -m 0644 -- "$SOURCE_V2_CARRIER" "$INSTALLED_V2_CARRIER"
sha256sum "$SOURCE_V2_CARRIER" "$INSTALLED_V2_CARRIER"
```

该命令仅在已验证原carrier为0644、目标归本task且窗口已批准时执行；不把路径检查交给未解析env。两sha应相等，原carrier备份保留。若采用colcon完整rebuild，仍用unique `so101_colcon` logroot且必须证明每个noncarrier rawbyte不变；任何wrapper/shebang/library改变回新R资格，不静默复用。
  4. 比较全部noncarrier installed/sourcebytes、dependencyorigins和L/S/E/I/R与测量A0；仅三个carrier refs变化允许。更新production external binding的cleancommit/config原sha及部署审计元数据，保持其execution语义/未允许文件不变；现场读取actual copiedcarrier已非null，再生成cleanA1和D。A1必须描述这个已commit source与实际installedbytes，D绑定M/P/A1/location，不引用dirty树或尚未publish的sourceconfig。
  5. 仅reload/refresh批准拥有的consumer，读回其新config/profile/Q/R/M/D/原bytes；三生产adapter实时probe+资格，包括allocate/adopt_existing，不凭sourceedit当installed成功。未知档仍disabled，不选择N后降级。

deployment结果与receipt先写root checkpoint；最终trackedledger提交后若source审计commit标签变化，重生成等价rawbinding/A1/D以对应clean新HEAD（不改R、不重新引用未来receipt到M/P），再fresh核owner，避免账本commit使strictsourcebinding落后。不推送、不替换原A0/M/D历史记录。

### Task 15：Chrome 逐档选择、完整 runtime 与生命周期验收

**Files:** Modify `src/so101_teleop/web/e2e/expert-validation/live-sim/01-sequential.spec.ts`、`02-parallel.spec.ts`、`preflight.spec.ts`、`fixtures/live-sim.ts`、`assertions/live-evidence.ts`、`src/so101_teleop/web/playwright.live-sim.config.ts`；Create `src/so101_teleop/web/e2e/expert-validation/live-sim/04-resource-budget.spec.ts`、`src/so101_teleop/web/src/api/live-evidence.test.ts`；Test existing installed retry/lease-recovery/API-contract；ledger。

**Interfaces:** `verifyV2LiveEvidence(batchRoot: string, expected: {workerCount: number; pointCount: number; profileSha256: string; qualificationSha256: string; executionIdentitySha256: string}): Promise<void>` 在live-evidence.ts读取并验证manifest/receipt/artifacthash/actualslotidentities/物理证据字段及统计，不能只assertfilename存在。Browser actual workerselection、APIrequestedN、manifestN、livePIDstart/render/heartbeat均一致；4点N8允许idle但仍8slot。

- [ ] Stage A RED先offlinefixture tamper case（纯artifact fixture），调用verifier对错hash、actualN少一、policyDONE无physics拒绝；新增verifierunittest放web `src/api/live-evidence.test.ts` 并通过 `so101_bun live-evidence-red run test src/api/live-evidence.test.ts`。最小test：`await expect(verifyV2LiveEvidence(tamperedRoot, expected)).rejects.toThrow('QUALIFICATION_EVIDENCE_INVALID')`；本地fixture保存完整schema2manifest/rawsha而后只tamper一个目标字段，`expected`按上述接口五字段全部赋synthetic值。真实sim前不靠合成artifact赢qualification。
- [ ] 保留livefixture `SO101_ENABLE_LIVE_SIM_E2E=1`、host AI-STATION-001、evidence/provenance绑定和stackconflictfailclosed；冲突存在先请求独占窗口/freshownership，不删检测、不停foreignservices。测试childmodule用Task12productionoverlay，浏览器用真实Chrome。
- [ ] 新04suite参数化N2..8、pointcount4/20：所有选项显示资格status/reason；未qualified不可点击执行且server直接请求拒绝、requestedN保留；qualified才start，完整Nslot证据，N>points也不降N。用固定anchors/catalogseed，记录选择和preflight/startedbatch绑定。资格测量用20点，4点UI验收不进normalstreak。
- [ ] Stage A迁移01-sequential为真正v2/N1生产R01 producer：使用已批准N1资格、四anchor、真实sealed/hash/physics/cleanup证据与freshR/P/Q/D身份。`recordGate`保存本调用root/runID、producer01、actualbatchhash/cleanup/身份；`requireGate`在02/04前核同root、当前R/P/Q、manifesthash和完整cleanup，不只判文件存在。01未通过或N1/N2未批准则对应physicalpipeline PENDING/拒绝，不能借旧R01/skip算PASS。
- [ ] Stage A在existing live-sim config加入项目依赖，保workers1/retries0/globalsetup/其余suite。一次Playwright调用先preflight、再01并验证新R01、最后02/04；不能在多个freshroot调用间搬receipt：

```ts
projects: [
  { name: 'live-preflight', testMatch: '**/live-sim/preflight.spec.ts' },
  { name: 'r01-sequential', testMatch: '**/live-sim/01-sequential.spec.ts', dependencies: ['live-preflight'] },
  { name: 'parallel-resource', testMatch: /\/live-sim\/(02-parallel|04-resource-budget)\.spec\.ts$/,
    dependencies: ['r01-sequential'] },
  { name: 'adaptive', testMatch: '**/live-sim/03-adaptive.spec.ts', dependencies: ['r01-sequential'] },
],
```

- [ ] Stage A verifier/01/04/config实现完成，运行 `so101_bun live-evidence-green run test src/api/live-evidence.test.ts` 和 `so101_bun live-suite-build run build`，审查后scoped stage本task files，`git commit -m "test(web): verify exact N availability and no downgrade lifecycle"`；installed API gate在Task12完整clean offlinecopy中运行。这在Task12统一冻结前完成。
- [ ] Stage E获批准独占owned浏览器窗口后，若Task12/14拥有的Web仍运行，先fresh核其PIDstart/controllease与ownedscope，在明确包含暂停该owned服务的窗口中停止/cleanup并读回stackconflict为空；foreign服务存在则保留并暂停本gate，不修改scan。该invocation前先按通用规则完成trackedmetadata commits，核clean HEAD/不变R/install，选择新的immutable binding及等价A1/D为 `ACTIVE_PROVENANCE_BINDING`，保持P/Q/M不变；选择到invoke不能再commit，HEAD变化则重复。随后从fresh shell sourceROS/canonical+最终productionoverlay，保Task11审核dependency mapping。导出并读回exactcopiedprefix/Python/Pydantic2/provenance/v2carrier/approvedM/D，fixturechild自己的重建环境也作同origin/hash proof（不能只证明调用shell）：

```zsh
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_moveit/install/setup.zsh
source "$TASK_ROOT/production-install/setup.zsh"
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$TEST_SITE"
export SO101_E2E_INSTALL_PREFIX="$TASK_ROOT/production-install"
export SO101_E2E_PYTHON="$TEST_PYTHON"
export SO101_VALIDATION_PROVENANCE_BINDING="$ACTIVE_PROVENANCE_BINDING"
export SO101_VALIDATION_PARALLEL_CONFIG="$SO101_E2E_INSTALL_PREFIX/so101_demo_py/share/so101_demo_py/config/mujoco/parallel_batch_v2.yaml"
export SO101_ENABLE_LIVE_SIM_E2E=1
cd "$WORKTREE/src/so101_teleop/web"
so101_bun live-qualified-pipeline run test:e2e:live-sim --project parallel-resource
```

`so101_bun`为这次pipeline创建并登记唯一新browserroot；preflight→01→R01核验→02/04全部在同一次invocation/newroot按projectdependencies推进，reports不会被第二次调用覆盖，任何重跑再创建新root并重新产生R01。Playwright报告/trace/screenshot/video/API记录+losslessraw都在原root下。Pythonfixture若跑pytest/colcon先自己newNVMEtempfileproof。livefixture的case-specific `SO101_VALIDATION_EVIDENCE_ROOT=stateDir`只是此新browserroot下子目录，不是另一个root。
- [ ] covered lifecycle：refresh/续租/leaseexpiry/取消真实ACK与cleanup、RAM/GPU/profiledrift拒绝、失败单点N1FULL_RESTART独立batch及firstpass/retrystat、opaquehistoricalevidence显示。02suite brokerreload依支持R01路径，不能缺前置却“skip算PASS”。不要求UNKNOWN档跑真实sim，只验拒绝解释；可用档物理失败照真实报告。
- [ ] Sol/high审browser/API/runtime/physics/cleanup证据，更新并仅stage ledger，`git commit -m "docs: record exact N browser lifecycle verification"`。现场发现需改runtimecode时回Stage A/B新版本，再Task13新R资格；不能临时排除runtime内容以保旧profile。

### Task 16：guide、历史 superseded 链接与最终交接

**Files:** Create `docs/guides/so101-parallel-unbounded-queue-resource-budget.md`；Modify新任务ledger；只追加旧 `docs/superpowers/specs/2026-09-18-so101-fixed-eight-worker-qualification-resource-proposal.md` 的superseded链接。不覆写旧规范/历史正文，不修改冻结设计或两review。

**Interfaces:** guide解释用户选N/点位、disabledreason、sharedqueue/leasecount、人工单点retry、candidate/promotion边界、运营取消/恢复的freshownership要求、v1readonly。所有samplecommands指实际installedentry与注册root，不含绕过resourcegate或genericWebmeasurement入口。

- [ ] 使用humanizer-zh读完整主文件后写中文guide；命令、ID、hash、路径保持精确；README若需变更必须English+humanizer。指南只陈述已实现/已验证事实，NOT_MEASURED档不写available。
- [ ] 在旧proposal末追加“本 proposal 的 K/count/resource-contract 部分由新设计 supersede；其他历史内容保留”的相对链接；原bytes前缀hash证明未变。此任务才改旧proposal，本轮计划文档编写不提前改它。
- [ ] `git diff --check`、relative links/headings/legacy literal用途检查、完整回读guide；Astra/high独审guide。最终Sol/high结果review核 source/install/runtime/P/Q/M/D/audit与liveevidence，文档reviewPASS和运行PASS分列。
- [ ] 最终账本逐N列resource_qualified/product_qualification_passed/status/reasons/R/P/Q/batchhash和未决项；恢复列offline/online真实状态，执行授权与promotion审批分别引用。列retainedruns、archivedruns、deletioncandidates（scratch及失效候选保留），不删除/归档未授权证据。最后checkpoint给唯一续接命令/ownedscope，不把dispatchreceipt当完成。
- [ ] scoped stageguide/旧proposal追加/新ledger，`git commit -m "docs: explain unbounded queue budgets and retained qualification evidence"`；禁止自动merge/push。若用户后续要求publication，另按remote映射保留only-on-one-remote commits、不force、不用gh，并远端readback。

## 计划自查与实施完成判定

| 设计条款 | 对应任务/完成证据 |
| --- | --- |
| §3 v2/noK/v1只读/4..20/固定N/retryN1 | 2、9、10、11、15；legacy key含null拒绝与v1hashinventory |
| §4 unbounded/idempotency/finite recovery/统计 | 7、8、9；20次grant、并发/timeout/fence与retry独立分母 |
| §5 三消费者/typedcontext/ADAPTIVE不扩权 | 4、8、10；同P/Q/R/reasons及TOCTOU/context拒绝 |
| §6.1 无Web control/watchdog/实际stoplatency | 5、6、13；rawtimelines、owner/samplerdeath、无replacement/foreignsignal |
| §6.2 bytes/core-equivalent/20%/aliasing | 4、6、13；synthetictable与realrawB/H/D/J、E/cgroup/device闭包 |
| §6.3 epoch/nonoverlap/误差与calibrationbootstrap | 6、13；CALIBRATION_ONLY不计PASS、epsilon冻结、no-clock/lag原deadline |
| §7 normal5/物理证据/八phase/faultenvelope | 13；每N独立Q+coverage、resource/product分开，未覆盖拒绝 |
| §8 无环L/S/E/I/R/B/Q/P/M/A0/A1/D | 3、4、13、14；firstnullpromotion与安全/exebytes漂移回归 |
| §9 恢复/cleaninstall/窗口/同根NVME/ledger | 0、1、12、13；freshownership、offline+ownedWebrefresh、所有scratchproof |
| §10 OpenAPI/Bun/Chrome/guide/historical | 11、15、16；generateddiff、livehash/slot/physics证据、只追加superseded |

实施完成必须逐项证明，不能仅因17个checkbox勾完宣称所有N qualified。允许明确交付“代码/gates完成，N某档UNKNOWN或REJECTED”：该档保持生产禁用、原因和原证据可读；没有operator promotion的候选不是可用生产档。任何gate失败保留最后checkpoint，不跨stage、不静默换模型/减N/改timeout/改物理/放宽fence。

本计划编写阶段：全部N预算 `NOT_MEASURED`；无代码实现、无新pytest/colcon/Bun/Chrome/runtime验证、无dst TUI、无新服务部署、无commit/push。下一步仅独立Astra/high计划审查，然后由用户决定是否授权执行。
