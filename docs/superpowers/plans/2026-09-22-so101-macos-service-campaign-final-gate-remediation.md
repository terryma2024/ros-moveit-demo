# SO-101 macOS service campaign 最终门禁修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

你当前直接运行在 mac-mini 上。不要 SSH 回 mac-mini；仓库、tmux、进程和测试命令都在当前主机执行。每个 review checkpoint 先释放 writer，再交回 GPT-5.6 Sol / High。

**Goal:** 修正 macOS service campaign 的 Gate A 证据、测试运行环境、retry 证据读取、Web contract 隔离、操作指南和账本结论，使 `CP-MSC-FINAL` 只在新鲜完整门禁和必要 live 复验全部通过后成立。

**Architecture:** 先修订已获授权的 fixed dylib-farm 契约，再让 Gate A attestation 绑定到真实 owner tree。静态门禁把日志、JUnit 和 receipts 留在唯一 evidence root，把可删除的 macOS test scratch 放到固定短路径 `/opt/data/tmp`；这是 transient scratch，不是第二 evidence root。runner 统一记录每一步退出码、JUnit 计数、scratch identity 和哈希。控制面稳定后逐项修复剩余 Darwin/packaging/test-isolation 问题，最后重跑 Gate A 5x、完整静态门禁和受影响的 W2/W1/retry live 验收。

**Tech Stack:** Python 3.11、zsh、pytest、colcon/CTest、ROS 2 Jazzy、MuJoCo、MoveIt 2、AF_UNIX、psutil、FastAPI、React/TypeScript、Bun、Vitest、Playwright、SQLite。

**Spec:** `docs/superpowers/specs/2026-09-21-so101-macos-service-campaign-closure-design.md`

**Execution order:** Tasks 1–8B → Task 9 → Task 10 → Task 11。Task 10 的正文为了紧邻 Gate A 修复说明而排在 Task 9 标题之前，但绝不能提前执行；Task 9 是最后一次仓库内容修改，Task 10 才是全流程最后一次 `prepare` 和 farm/install freeze。

## Global Constraints

- 直接在 mac-mini 当前 worktree `/Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp` 和分支 `codex/so101-unified-webapp` 执行，不再 SSH 到 mac-mini，不新建 worktree 或 branch。
- 接管时基线 HEAD 必须是投递前刚刚只读确认的 `a3f252e20680b2cbf83d947ec32ac911349666b5`，submodule 必须是 `85d2a5c42686a3d6b0d909a047a4188b24edd257`，且 `origin/codex/so101-unified-webapp...HEAD` 必须为 `0 0`。orchestration 会在投递时添加唯一一个未跟踪文件 `docs/superpowers/plans/2026-09-22-so101-macos-service-campaign-final-gate-remediation.md`，其 SHA256 必须为 handoff 记录值；除此以外 worktree 必须 clean。任一不符都停止并报告，不自动 rebase/reset。Task 1 首个 commit 收录该计划，后续每个 scoped commit 都写入 ledger。
- 唯一 evidence root 继续使用 `/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1`。不得创建第二个 evidence root，不移动或删除既有证据。
- macOS 不套用 ai-station 的 scratch-under-evidence-root 规则。测试 scratch 使用 `/opt/data/tmp/so101-service-gate-<run-id>`，所有日志、JUnit、argv、rc、计数、identity receipt 和 SHA256 仍写入唯一 evidence root。scratch 只列 deletion candidate，不删除。
- 投递前 worktree 已确认 clean；投递后只允许上述已校验 SHA 的未跟踪计划文件。执行中只允许本计划列出的文件变化；发现其他未归属 dirty 文件时停止并登记，不得夹带、覆盖或清理。
- 用户已授权 fixed dylib-farm。literal no-DYLD 不再是完成门槛；设计、计划、guide、ledger 必须明确记录这一授权。授权不放宽 closure inventory、owner ancestry、PID/birth、executable、plugin/vendor path+SHA 或 cleanup 证据。
- 不停止 foreign 进程，不用 `ps | grep | head -1` 选择 owner，不运行真实机械臂，不扩大到 macOS W3+ 或容量资格，不恢复 retired resource measurement。
- 不得通过 skip、xfail、删除测试、放宽 fail-closed 检查、缩小 gate 范围或只比较失败数量取得 GREEN。
- 不运行 benchmark suite。所有产品修改先 RED 后 GREEN；定向测试通过后才运行 package gate。
- 本批次允许 scoped local commits；不 push、不 merge、不 force push。每次 commit 只 stage 该 Task 列出的文件。
- `colcon test` 的退出码不能替代 `colcon test-result --verbose`。任一 JUnit errors/failures 非零、任一步真实退出码非零或收集数为零，都阻止 `CP-MSC-FINAL`。

## 已确认的失败基线

新鲜独立复跑位于：

```text
/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1/independent-final-gate-20260922T131346Z-h4iCZ2
```

该运行的 SHA256 readback 已通过，结果为：

```text
demo pytest       rc=1  176 failed, 3697 passed, 10 skipped, 12 deselected
teleop pytest     rc=1  27 failed, 860 passed, 1 skipped
copied install    rc=0  25 passed, 8 skipped
colcon test       rc=0  package had test failures
colcon result     rc=1  1065 tests, 39 failures, 2 skipped
web tsc/test/build      all rc=0
```

已观察到的首坏边界包括：

- evidence-root 内的长 `TMPDIR` 令 Darwin AF_UNIX endpoint 超限，触发 `UNIX_SOCKET_PATH_TOO_LONG`、`IPC_SOCKET_PATH_TOO_LONG`、`CONTROL_SOCKET_PATH_TOO_LONG` 和后续 `PATH_OWNER`；
- `test_expert_validation_macos_service_campaign.py` 无条件读取未声明的 `SO101_TASK_ROOT`，得到 `KeyError`；
- `RuntimeInspector` 硬编码 `/proc`，在 Darwin 返回 `RECOVERY_PROC_UNAVAILABLE`；
- `test_unified_lease_maintenance.py` 和 `test_unified_lease_projection.py` 未注册到 CMake package gate；
- fixed-eight/`INDEX:0` 的旧测试与 macOS W1/W2、`MPS:default` 当前合同不一致；
- Playwright live-preflight contract 受 foreign process scanner 影响，产品正确 fail-closed，但测试没有隔离 scanner；
- 旧 Gate A 5x attestation 的 `executable` 为空，且历史 runner 通过全机 `ps | grep | head -1` 取进程；
- guide 先以前台命令启动 standalone station，后面的 unified service 命令无法执行；
- retry acceptance 的 legacy/native reader 曾对 `dynamic_manifest_relative_path=null` 触发 `EISDIR`，另一个旧 reader 把合法的 failed-before-physical attempt 当成失败；
- ledger/guide 把失败数量“与上次相同”写成受影响层 GREEN，并遗漏/弱化真实 errors/failures。

---

### Task 1: 串行接管、登记 remediation checkpoint

**Files:**
- Create/commit: `docs/superpowers/plans/2026-09-22-so101-macos-service-campaign-final-gate-remediation.md`
- Modify: `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md`

**Interfaces:**
- Consumes: 当前 clean branch、HEAD、submodule、remote parity、已登记 evidence root
- Produces: `CP-MSC-REMEDIATION-START` 和新的 `PLANNED` 实验条目

- [ ] **Step 1: 证明当前 session 是唯一 writer**

```zsh
hostname
pwd
git branch --show-current
git rev-parse HEAD
git submodule status --recursive
git status --short
/opt/homebrew/bin/tmux list-sessions
ps -axo pid=,ppid=,command= | grep -E 'expert-validation|ros2_control_node|move_group|task.station|task_station|uvicorn' | grep -v grep || true
lsof -nP -iTCP:8013 -sTCP:LISTEN || true
```

Expected: 当前目录、branch、HEAD、remote parity 和 submodule 精确匹配 Global Constraints；worktree 除 exact-SHA 的未跟踪 remediation plan 外 clean；没有另一个 writer 或 task-owned live stack。发现 foreign 进程时只登记，不发信号。

- [ ] **Step 2: 回读原设计、原计划、guide、ledger 和新鲜失败证据**

```zsh
sed -n '1,620p' docs/superpowers/specs/2026-09-21-so101-macos-service-campaign-closure-design.md
sed -n '1,1340p' docs/superpowers/plans/2026-09-21-so101-macos-service-campaign-closure-implementation.md
sed -n '1,240p' docs/guides/so101-macos-service-campaign-closure.md
sed -n '1,3300p' docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md
```

Expected: 恢复最后可信 checkpoint、已确认结论、已证伪路线和下一实验；不得把历史 FAIL 改写成 PASS。

- [ ] **Step 3: 在 ledger 追加 remediation checkpoint**

记录本计划绝对路径、dispatch id、当前 writer、基线 SHA、独立复跑目录和上面的精确计数。新的实验状态先写 `PLANNED`，分别冻结 Gate A attestation、short-temp control、完整 gate 和 live requalification 的判据。

- [ ] **Step 4: 提交账本 checkpoint**

```zsh
git add -- docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md
git add -- docs/superpowers/plans/2026-09-22-so101-macos-service-campaign-final-gate-remediation.md
git diff --cached --check
git commit -m "docs: start macOS service closure remediation"
```

---

### Task 2: 把授权的 fixed dylib-farm 写入正式合同

**Files:**
- Modify: `docs/superpowers/specs/2026-09-21-so101-macos-service-campaign-closure-design.md`
- Modify: `docs/superpowers/plans/2026-09-21-so101-macos-service-campaign-closure-implementation.md`
- Modify: `docs/guides/so101-macos-service-campaign-closure.md`
- Modify: `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md`

**Interfaces:**
- Consumes: 用户对 dylib farm 的明确授权
- Produces: `FixedDylibFarmRuntimeContract`、新的 `CP-MSC-A2-FARM` 和修订后的 `CP-MSC-FINAL` 完成定义

- [ ] **Step 1: 先写文档合同检查的 RED 测试**

在 `src/so101_demo_py/test/test_macos_install_contract.py` 增加检查，要求设计、原计划和 guide 同时包含：

```python
required = (
    "FixedDylibFarmRuntimeContract",
    "/opt/ros2_jazzy/dylib_farm/current",
    "owner ancestry",
    "pid",
    "birth",
    "executable",
    "plugin_path",
    "plugin_sha256",
    "vendor_path",
    "vendor_sha256",
)
```

同时断言完成定义不再要求 literal no-DYLD PASS，也不允许把 `DYLD_*` 任意继承写成合法。文档测试还必须拒绝继续使用旧的单一 merged `F_CLOSURE_ROOT` 作为当前完成合同。

- [ ] **Step 2: 运行 RED**

```zsh
/opt/ros2_jazzy/.venv/bin/python -m pytest -q \
  src/so101_demo_py/test/test_macos_install_contract.py \
  -k 'fixed_dylib_farm or closure_completion'
```

Expected: FAIL，指出设计/计划仍把 literal no-DYLD 当硬门槛或缺少完整 attestation 字段。

- [ ] **Step 3: 修订设计和原计划**

合同必须显式 supersede 原设计中“单一 merged `F_CLOSURE_ROOT`、literal no-DYLD 和旧 N/P/F 同时作为当前完成条件”的约束。旧 N/P/F 及 `CP-MSC-A1` 原文保留为历史归因，不回写；新的当前门禁使用独立 checkpoint `CP-MSC-A2-FARM`。

新合同必须写清：

```text
FixedDylibFarmRuntimeContract:
  closure_prefixes:
    - /opt/ros2_jazzy/install
    - /opt/ros2_jazzy/extra_ws/install
    - /opt/data/so101/runtime/fork/current
    - /opt/data/so101/workspace/install
    - /opt/ros2_jazzy/dylib_farm/current
  dylib_farm_root: /opt/ros2_jazzy/dylib_farm/current
  source: scripts/so101-macos.zsh prepare 生成并由 doctor/manifest 校验
  environment: 仅允许 runner 从已验证 manifest 构造的 DYLD_LIBRARY_PATH
  forbidden: 用户 shell 任意继承、额外 DYLD_*、未登记 overlay、路径或 SHA drift
  attestation: owner ancestry + PID/birth + executable + plugin/vendor path+SHA
  cleanup: task-owned tree 有界停止；foreign process 只读登记
```

还要冻结 `/opt/ros2_jazzy/dylib_farm/current` 的 logical path、resolved target、manifest bytes、inventory 和 SHA256；每次 spawn 前重新验证，任一 symlink target、manifest、entry path 或 SHA drift 都 fail closed。Python、诊断 CLI、ament index、launch executable 和控制器/plugin/vendor 的 provenance 必须能归属到上述五个 fixed prefixes，不能只证明 dylib 文件存在。

保留历史 `CP-MSC-A1`、literal no-DYLD FAIL 和旧 N/P/F 记录，不把它们重写成已通过。只有新合同、正向 farm 运行、负向 drift 控制和 owner-bound 5x FULL_RESTART 全部通过，才新增 `CP-MSC-A2-FARM=PASS`。`CP-MSC-FINAL` 依赖 A2，不再依赖历史 A1 变成 PASS。

- [ ] **Step 4: 运行 GREEN 并提交**

```zsh
/opt/ros2_jazzy/.venv/bin/python -m pytest -q \
  src/so101_demo_py/test/test_macos_install_contract.py \
  -k 'fixed_dylib_farm or closure_completion'
git add -- \
  src/so101_demo_py/test/test_macos_install_contract.py \
  docs/superpowers/specs/2026-09-21-so101-macos-service-campaign-closure-design.md \
  docs/superpowers/plans/2026-09-21-so101-macos-service-campaign-closure-implementation.md \
  docs/guides/so101-macos-service-campaign-closure.md \
  docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md
git diff --cached --check
git commit -m "docs: authorize fixed macOS dylib farm contract"
```

---

### Task 3: 修复 Gate A owner-bound runtime attestation

**Files:**
- Modify: `src/so101_demo_py/src/runtime/runtime_closure.py`
- Modify: `src/so101_demo_py/src/cli/diagnose_macos_station.py`
- Modify: `scripts/so101_macos_runtime_contract.py`
- Modify: `src/so101_demo_py/test/test_runtime_closure.py`
- Modify: `src/so101_demo_py/test/test_diagnose_macos_station.py`
- Modify: `src/so101_demo_py/test/test_macos_install_contract.py`
- Modify: `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md`

**Interfaces:**
- Consumes: `FixedDylibFarmRuntimeContract`、launch spawn intent、owner tree、runtime closure manifest
- Produces: `RuntimeProcessAttestation`，字段 `role/pid/birth/executable/plugin_path/plugin_sha256/vendor_path/vendor_sha256/owner_binding_sha256`
- Produces: 唯一 launch-owning diagnostic mode `FIXED_DYLIB_FARM_FULL_TASK_STATION`，参数 `--farm-contract-receipt`、`--run-binding`、`--output`、`--timeout-s`；该进程独占 intent → spawn → readiness → attestation → shutdown

- [ ] **Step 1: 为错误进程选择和缺字段写 RED**

新增表驱动测试，至少覆盖：

```python
@pytest.mark.parametrize("mutation", [
    "missing_executable",
    "pid_birth_drift",
    "wrong_owner_ancestry",
    "launcher_instead_of_controller",
    "plugin_outside_closure",
    "vendor_outside_closure",
    "plugin_sha_drift",
    "vendor_sha_drift",
])
def test_controller_runtime_attestation_rejects_unbound_or_drifted_process(mutation):
    candidate = mutated_controller_attestation(valid_controller_attestation(), mutation)
    with pytest.raises(RuntimeClosureError, match="PROCESS_ATTESTATION_INVALID"):
        validate_controller_runtime_attestation(candidate)
```

再加 positive case：只有 launch intent 预绑定的 `controller_runtime` descendant，且 PID/birth/executable 与 plugin/vendor loaded image path+SHA 全部匹配，才可生成 PASS attestation。

CLI contract tests 必须证明：farm mode 缺任一 receipt/binding/output 参数时在 spawn 前拒绝；farm mode 不接受旧 `--control-set-manifest/--control`；一个调用只产生一个 station owner tree；报告原子写入 `--output` 后才返回；无论 PASS/FAIL 都执行 owner-bound bounded cleanup。旧 `FULL_TASK_STATION` 的 N/P/F 入口只保留为历史诊断，不用于 A2。

- [ ] **Step 2: 运行 RED**

```zsh
/opt/ros2_jazzy/.venv/bin/python -m pytest -q \
  src/so101_demo_py/test/test_runtime_closure.py \
  src/so101_demo_py/test/test_diagnose_macos_station.py \
  src/so101_demo_py/test/test_macos_install_contract.py \
  -k 'attestation or controller_runtime or dylib_farm'
```

Expected: 旧逻辑接受 `executable=None`、错误 descendant 或缺失 owner binding 的 case 必须 FAIL。

- [ ] **Step 3: 实现最小修复**

- process role 在 spawn intent 写入时绑定，不能在 loaded-image 结果出来后反推；
- collector 从 owner tree 沿 ancestry 找到唯一 descendant，并同时核对 PID、birth、executable；
- plugin/vendor 必须位于当前 manifest 的 frozen closure 或 sanctioned dylib-farm entry，SHA 精确一致；
- 每个 spawn 前重新解析 farm `current`、回读 manifest/inventory SHA，并验证 Python、ament index、launch executable 和所有 overlay provenance；不能沿用上一轮的缓存 verdict；
- 空 executable、空 loaded images、多候选、全机扫描命中或 identity drift 一律 fail closed；
- runner 删除 `ps | grep | head -1` 路径，只消费产品生成的 owner-bound attestation。
- `FIXED_DYLIB_FARM_FULL_TASK_STATION` 是 A2 唯一 station owner：它先验证 farm receipt/run binding，原子写 spawn intent，自行启动 station、调用同进程内 readiness/attestation validator，最后有界关闭。外部不得先 `launch` 另一套 station，也不得把旧 N/P/F 参数拼到 farm mode。

- [ ] **Step 4: 运行 GREEN 和相关 package tests**

```zsh
/opt/ros2_jazzy/.venv/bin/python -m pytest -q \
  src/so101_demo_py/test/test_runtime_closure.py \
  src/so101_demo_py/test/test_diagnose_macos_station.py \
  src/so101_demo_py/test/test_macos_install_contract.py
```

- [ ] **Step 5: 提交**

```zsh
git add -- \
  src/so101_demo_py/src/runtime/runtime_closure.py \
  src/so101_demo_py/src/cli/diagnose_macos_station.py \
  scripts/so101_macos_runtime_contract.py \
  src/so101_demo_py/test/test_runtime_closure.py \
  src/so101_demo_py/test/test_diagnose_macos_station.py \
  src/so101_demo_py/test/test_macos_install_contract.py \
  docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md
git diff --cached --check
git commit -m "fix: bind macOS runtime attestation to owner tree"
```

---

### Task 4: 建立短 AF_UNIX test scratch 和可重放最终 gate runner

**Files:**
- Create: `src/so101_demo_py/src/runtime/macos_test_scratch.py`
- Create: `src/so101_demo_py/test/test_macos_test_scratch.py`
- Create: `scripts/so101-macos-service-campaign-final-gate.zsh`
- Modify: `src/so101_demo_py/test/test_macos_install_contract.py`
- Modify: `docs/superpowers/specs/2026-09-21-so101-macos-service-campaign-closure-design.md`
- Modify: `docs/superpowers/plans/2026-09-21-so101-macos-service-campaign-closure-implementation.md`

**Interfaces:**
- Produces: `MacOSTestScratch(scratch_path, evidence_run_root, owner_uid, mode, max_endpoint_bytes, receipt_path)`
- Produces: `prepare_macos_test_scratch(evidence_run_root: Path, scratch_parent: Path = Path('/opt/data/tmp')) -> MacOSTestScratch`

- [ ] **Step 1: 写 scratch 合同 RED**

测试必须覆盖：scratch 是 `/opt/data/tmp` 下新建的真实目录且 mode `0700`；不是 symlink；owner 是当前 uid；`TMPDIR/TMP/TEMP` 精确指向该目录；最长已知 endpoint 低于 Darwin `sun_path` 上限；已存在目录、错误 owner、错误 mode、symlink parent、路径逃逸或 endpoint 超限时 fail closed；helper 不删除 scratch；identity receipt 写入 evidence run root。

```python
def test_long_evidence_root_uses_independent_short_macos_scratch(tmp_path):
    run_root = tmp_path / ("very-long-evidence-component-" * 4)
    result = prepare_macos_test_scratch(run_root, scratch_parent=Path("/opt/data/tmp"))
    assert result.scratch_path.parent == Path("/opt/data/tmp")
    assert not result.scratch_path.is_symlink()
    assert result.receipt_path.is_relative_to(run_root)
    assert result.max_endpoint_bytes < result.sun_path_limit
```

- [ ] **Step 2: 运行 RED**

```zsh
/opt/ros2_jazzy/.venv/bin/python -m pytest -q \
  src/so101_demo_py/test/test_macos_test_scratch.py
```

- [ ] **Step 3: 实现 helper 和 runner**

`scripts/so101-macos-service-campaign-final-gate.zsh` 必须：

1. 只接受当前 worktree、已登记 evidence root 和精确 test Python；
2. 在 evidence root 下创建唯一 run directory，在 `/opt/data/tmp` 下用 `mkdir(O_EXCL)` 语义创建唯一 private scratch；
3. 设置 `TMPDIR/TMP/TEMP` 为该短 scratch，并用 exact test Python 回读 `tempfile.gettempdir()`；不得使用 symlink alias，因为 pytest 8.4.2 会 resolve basetemp 并重新暴露长路径；
4. 设置 `SO101_TASK_ROOT` 和 `TASK_ROOT` 为同一个已登记 evidence root，并在执行前断言二者相等；
5. source 固定 ROS、extra_ws、runtime fork 和 workspace zsh overlay；记录 Python、`rclpy.__file__`、Bun 和 colcon provenance；
6. 依次执行 demo pytest、teleop pytest、copied-install、`colcon test --return-code-on-test-failure`、colcon test-result、Bun tsc/test/build 和必需 Playwright contract/installed projects；即使前一步失败也继续采集后续证据；
7. 保存完整 argv、elapsed、真实 rc、JUnit counts、stdout/stderr 和 SHA256；
8. 若 `colcon test-result` 非零、JUnit errors/failures 非零、收集数为零或任何 Web gate 非零，runner 总退出码非零；
9. 不删除 scratch 或日志，只在 summary 中把 scratch 分类为 deletion candidate；
10. preflight 以真实 socket bind 验证最长 endpoint suffix，不能只比较字符串常量。

- [ ] **Step 4: 运行 GREEN 和 runner contract test**

```zsh
/opt/ros2_jazzy/.venv/bin/python -m pytest -q \
  src/so101_demo_py/test/test_macos_test_scratch.py \
  src/so101_demo_py/test/test_macos_install_contract.py \
  -k 'macos_test_scratch or final_gate'
```

- [ ] **Step 5: 提交**

```zsh
git add -- \
  src/so101_demo_py/src/runtime/macos_test_scratch.py \
  src/so101_demo_py/test/test_macos_test_scratch.py \
  src/so101_demo_py/test/test_macos_install_contract.py \
  scripts/so101-macos-service-campaign-final-gate.zsh \
  docs/superpowers/specs/2026-09-21-so101-macos-service-campaign-closure-design.md \
  docs/superpowers/plans/2026-09-21-so101-macos-service-campaign-closure-implementation.md
git diff --cached --check
git commit -m "test: add portable macOS final gate runner"
```

---

### Task 5: 修复环境变量、Darwin process identity 和 package 注册

**Files:**
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_macos_service_campaign.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/operator_recovery.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_operator_recovery.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_e2e_installed_port.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_preflight.py`
- Modify: `src/so101_teleop/CMakeLists.txt`
- Modify: `src/so101_teleop/test/teleop/test_unified_launch.py`

**Interfaces:**
- Produces: `RuntimeInspector` 的 Linux procfs 和 Darwin psutil 两种 inventory port
- Preserves: 任何无法证明 identity/absence 的结果仍返回 `RECOVERY_RUNTIME_UNVERIFIABLE`

- [ ] **Step 1: 写四组 RED**

1. 删除 `SO101_TASK_ROOT` 后，adapter script-path test 仍从显式 source path 和继承的 `PYTHONPATH` 启动，不出现 `KeyError` 或 `ModuleNotFoundError`；
2. Darwin process inventory 用 psutil 检测 leader/pgid/PID reuse，不依赖 `/proc`；psutil 缺失、AccessDenied 或 identity 不完整时 fail closed；
3. e2e helper cleanup 不用 `Path('/proc/<pid>')` 判断存活，复用同一个 cross-platform identity port；
4. CMake 精确注册 `test_unified_lease_maintenance.py` 和 `test_unified_lease_projection.py`，双向 registration test 通过；
5. 把 StartGuard 测试拆成与 host 无关的 deterministic unit contract 和 native-host smoke：保留 Linux `worker_count=8`、`gpu_selector='INDEX:0'` 覆盖，同时新增 Darwin `worker_count=2`、`gpu_selector='MPS:default'`；保留无 guard fail-closed case。host 资源不足只能把 native smoke 标成明确的环境结果，不能改写 deterministic 产品合同，也不能把 Linux W8 回归删掉。

- [ ] **Step 2: 运行 RED**

```zsh
/opt/ros2_jazzy/.venv/bin/python -m pytest -q \
  src/so101_teleop/test/teleop/test_expert_validation_macos_service_campaign.py \
  src/so101_teleop/test/teleop/test_expert_validation_operator_recovery.py \
  src/so101_teleop/test/teleop/test_expert_validation_e2e_installed_port.py \
  src/so101_teleop/test/teleop/test_expert_validation_preflight.py \
  src/so101_teleop/test/teleop/test_unified_launch.py
```

- [ ] **Step 3: 实现最小修复**

- adapter test 从明确参数构造 child `PYTHONPATH`，不得要求调用者提供 task-specific env；
- `RuntimeInspector` 在 Linux 使用 procfs，在 Darwin 使用 psutil；两条路径输出同一 closed inventory，错误不降级成“进程不存在”；
- helper tests 复用 production identity utility，不自行探测 `/proc`；
- CMake 只补上两个缺失 test registration；
- StartGuard unit tests 同时保留 Linux W8/CUDA 和 macOS W2/MPS 合同；native smoke 只验证当前 host 声明的能力，不把 W8/CUDA 当成 macOS 成功路径，也不因当前 host 资源不足放宽产品测试。

- [ ] **Step 4: 运行 GREEN 和 package registration gate**

重复 Step 2 命令；Expected: 全部通过、非零收集、无 skip/xfail 新增。

- [ ] **Step 5: 提交**

```zsh
git add -- \
  src/so101_teleop/test/teleop/test_expert_validation_macos_service_campaign.py \
  src/so101_teleop/so101_teleop/expert_validation/operator_recovery.py \
  src/so101_teleop/test/teleop/test_expert_validation_operator_recovery.py \
  src/so101_teleop/test/teleop/test_expert_validation_e2e_installed_port.py \
  src/so101_teleop/test/teleop/test_expert_validation_preflight.py \
  src/so101_teleop/CMakeLists.txt \
  src/so101_teleop/test/teleop/test_unified_launch.py
git diff --cached --check
git commit -m "fix: make macOS service tests portable"
```

---

### Task 6: 闭合 retry binding、projection 和 physical-evidence reader

**Files:**
- Modify if RED reproduces: `src/so101_teleop/so101_teleop/expert_validation/campaign_layout.py`
- Modify if RED reproduces: `src/so101_teleop/so101_teleop/expert_validation/production.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_campaign_layout_projection.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_production_projection.py`
- Modify: `src/so101_teleop/web/e2e/expert-validation/assertions/live-evidence.ts`
- Modify: `src/so101_teleop/web/e2e/expert-validation/contract/live-evidence-layouts.spec.ts`

**Interfaces:**
- Consumes: first-pass binding 的 `catalog_sha256` 和 retry binding 的 `original_catalog_sha256`
- Produces: 同一 verified selection digest；合法 failed-before-physical attempt 允许 `dynamic_manifest_relative_path=null`、`dynamic_manifest_sha256=null`、`physical_evidence=false`

- [ ] **Step 1: 冻结真实 retry shape 的 RED fixtures**

fixture 必须表达：一个 retry 点、一次 lease、一次 `RESULT_COMMITTED/POINT_TERMINAL`、业务 `FAILED`、`RGBD_PERCEPTION_EXITED_EARLY`、无 dynamic manifest、无 physical claim、cleanup complete。断言：

```text
binding selection verifies through original_catalog_sha256
projection accepts exactly one retry point and does not reuse first-pass cursor
reader does not call readFileSync on null or a directory
FAILED without a physical claim is valid evidence shape
PASSED without physical evidence remains PHYSICAL_EVIDENCE_INVALID
first-pass bytes remain unchanged
```

- [ ] **Step 2: 运行 RED**

```zsh
/opt/ros2_jazzy/.venv/bin/python -m pytest -q \
  src/so101_teleop/test/teleop/test_expert_validation_campaign_layout_projection.py \
  src/so101_teleop/test/teleop/test_expert_validation_production_projection.py
cd src/so101_teleop/web
bunx playwright test e2e/expert-validation/contract/live-evidence-layouts.spec.ts --workers=1
cd ../../../
```

如果当前产品 reader 已通过上述合同，不制造无意义代码 diff；把历史 `EISDIR` reader 标为 retired acceptance harness，并让正式验收只调用 repository layout-aware reader。若任一 RED 仍复现，则只修改 owning reader/projection，不改写 evidence bytes。

- [ ] **Step 3: 修复并运行 GREEN**

重复 Step 2 命令。Expected: retry 与 first-pass fixtures 都通过；tampered catalog、contradictory hash、PASSED-without-physical 和 cross-batch cursor 全部继续拒绝。

- [ ] **Step 4: 提交实际发生变化的文件**

```zsh
git add -- \
  src/so101_teleop/so101_teleop/expert_validation/campaign_layout.py \
  src/so101_teleop/so101_teleop/expert_validation/production.py \
  src/so101_teleop/test/teleop/test_expert_validation_campaign_layout_projection.py \
  src/so101_teleop/test/teleop/test_expert_validation_production_projection.py \
  src/so101_teleop/web/e2e/expert-validation/assertions/live-evidence.ts \
  src/so101_teleop/web/e2e/expert-validation/contract/live-evidence-layouts.spec.ts
git diff --cached --check
git commit -m "fix: verify macOS retry evidence layout"
```

若 owning product files 没有变化，commit 只包含新增/修订的 regression tests 和 acceptance harness，不 stage 空文件集。

---

### Task 7: 隔离 Playwright contract scanner，保持 production fail-closed

**Files:**
- Modify: `src/so101_teleop/web/e2e/expert-validation/contract/live-preflight.spec.ts`
- Modify: 对应的 live-preflight fixture/helper 文件，以当前 import 为准
- Do not modify: production foreign-process refusal semantics

**Interfaces:**
- Consumes: injected `stackInventory`/process scanner fixture
- Produces: contract test 的 deterministic empty/foreign inventories；live-sim test 仍使用真实 scanner

- [ ] **Step 1: 写 RED**

为 contract test 注入两种 inventory：空 inventory 时 Darwin/Linux evidence-root case 到达自身断言；foreign inventory 时明确返回 `LIVE_SIM_STACK_PRESENT` 且绝不发信号。禁止 contract test 读取全机真实进程。

- [ ] **Step 2: 运行 RED**

```zsh
cd src/so101_teleop/web
bunx playwright test e2e/expert-validation/contract/live-preflight.spec.ts --workers=1
```

- [ ] **Step 3: 实现 fixture 注入，运行 GREEN**

Expected: 原 13 条 contract cases 全部通过；另有专门 case 证明 foreign process refusal 保持 fail-closed。真实 live-sim preflight 不使用 fake scanner。

- [ ] **Step 4: 提交**

```zsh
git add -- src/so101_teleop/web/e2e/expert-validation/contract/live-preflight.spec.ts \
  src/so101_teleop/web/e2e/expert-validation/fixtures
git diff --cached --check
git commit -m "test: isolate macOS live preflight contracts"
```

---

### Task 7B: 建立 macOS 单用例 live service-window runner

**Files:**
- Create: `scripts/so101-macos-service-campaign-live-window.zsh`
- Create: `scripts/so101_macos_unified_service.py`
- Create: `src/so101_teleop/test/teleop/test_macos_live_window_runner.py`
- Create: `src/so101_demo_py/test/test_macos_unified_service_launcher.py`
- Modify: `src/so101_teleop/web/e2e/expert-validation/fixtures/live-sim.ts`
- Modify: `src/so101_teleop/web/e2e/expert-validation/live-sim/06-fixed-n-execution.spec.ts`
- Modify: `src/so101_teleop/web/e2e/expert-validation/live-sim/07-retry-full-restart.spec.ts`

**Interfaces:**
- Consumes: `--case w2|w1|retry`、registered task root、frozen install prefix、frozen 20-point selection manifest、closed service launch document
- Produces: 一个 installed service window、精确一个 target console case、PID/birth/readiness/stop/cleanup receipt

- [ ] **Step 1: 写 runner contract RED**

测试必须证明：

- `w2` 只生成一个 `id=macos-w2-20`、`mode=PARALLEL`、`worker_count=2`、`point_count=20` 的 FIRST_PASS functional manifest；
- `w1` 只生成一个 `id=macos-w1-20`、`mode=SEQUENTIAL`、`worker_count=1`、`point_count=20` 的 FIRST_PASS functional manifest；
- `retry` 只选择 `retry-full-restart` project；该 window 自己以 frozen 20 点完成 first-pass，现场冻结 eligible failed binding，再在同一 service、同一 browser document 和同一 lease authority 下点击 retry；不得导入上一窗口 binding；
- runner 设置 `SO101_LIVE_SIM_HOST=$(hostname)`、`SO101_LIVE_SERVICE_BASE_URL=http://127.0.0.1:8013`、`SO101_LIVE_SERVICE_STATE_ROOT`、`SO101_FUNCTIONAL_MANIFEST`、`SO101_FROZEN_SELECTION_MANIFEST`、`SO101_LIVE_CASE_ID`、`SO101_TASK_ROOT`、`SO101_E2E_EVIDENCE_ROOT`、`SO101_E2E_INSTALL_PREFIX` 和 `SO101_E2E_PYTHON`；
- 每次启动前端口 8013 和真实 stack 必须为空；runner 只停止自己记录了 PID/birth 的 service owner，foreign/identity drift 时 zero signal；
- `playwright --list` 的 readback 对 W2/W1 恰好各包含一个目标 R06 case和必要 preflight，不得收集另一个 first-pass case；retry 恰好包含一个 R07 case和必要 preflight；
- service receipt 包含 executable/install/bundle SHA、PID/birth、state root、health readiness、真实 child-env readback、argv/env whitelist、start/stop rc、residue 和 SHA256。

- [ ] **Step 2: RED**

```zsh
/opt/ros2_jazzy/.venv/bin/python -m pytest -q \
  src/so101_teleop/test/teleop/test_macos_live_window_runner.py \
  src/so101_demo_py/test/test_macos_unified_service_launcher.py
```

- [ ] **Step 3: 实现 closed window runner**

runner 先生成只含 schema/version、固定 logical+resolved paths、farm/install inventory SHA、host/port、state/socket roots 和所需 service 参数的 `service-launch.json`。`scripts/so101_macos_unified_service.py` 严格校验文档和 frozen identities，用 `scripts/so101_macos_runtime_contract.py` 的 fixed runtime builder 构造空基线环境，再在受控 zsh 中按固定顺序 source ROS、extra_ws、runtime fork、project install 四个受验证 setup，并注入已验证的 fixed farm，最后直接 `exec` 已验证 installed Python 和 console entry。它不得继承任意 shell env，也不得通过会清空 service 参数的 `scripts/so101-macos.zsh clean_reexec`。等价的最终 child 必须是：

```zsh
/opt/ros2_jazzy/.venv/bin/python scripts/so101_macos_unified_service.py \
  --launch-document "$window_root/service-launch.json" \
  --receipt "$window_root/service-child-receipt.json"
```

launcher 必须把 child 实际收到的 `SO101_UNIFIED_EVIDENCE_ROOT`、`SO101_UNIFIED_SOCKET_DIR`、`SO101_UNIFIED_ROS_PYTHON`、`SO101_UNIFIED_INSTALL_PREFIX`、host/port 和 runtime provenance 回写 receipt；测试必须读 child receipt，不能只检查父进程 env。runner 先写 spawn intent，再记录 service PID/birth/executable，轮询 `/health` 到 ready 后才运行 Playwright；完成后 identity recheck、SIGINT、bounded wait、必要时只对同一 task-owned tree 升级，并保存 residue。`SO101_LIVE_SERVICE_STATE_ROOT` 精确等于 child receipt 中的 `SO101_UNIFIED_EVIDENCE_ROOT` private existing directory。

W2/W1 各使用只有一个 case 的 functional manifest，因此 `06-fixed-n-execution.spec.ts` 不会遍历另一路由；同时新增 closed `SO101_LIVE_CASE_ID` 检查，缺失、未知或 manifest 中匹配数不等于 1 时 collection fail closed。生成 points 后必须逐项回读 `SO101_FROZEN_SELECTION_MANIFEST` 的 4 fixed + 16 generated IDs、坐标、顺序和 selection/catalog SHA，不只检查 `point_count=20`。retry window 也先生成并执行同一 frozen 20 点 first-pass，现场找到真实 terminal-clean business FAILED 点后冻结 binding，随后在同一页面 retry；不得拆成两个 service/console，也不得导入旧 campaign。

- [ ] **Step 4: GREEN 并提交**

除 Python contract test 外，使用 mock service/Playwright argv fixture 验证 `--list` 与 cleanup，不启动 MuJoCo。实际 live 留到 Task 11。

```zsh
git add -- \
  scripts/so101-macos-service-campaign-live-window.zsh \
  scripts/so101_macos_unified_service.py \
  src/so101_teleop/test/teleop/test_macos_live_window_runner.py \
  src/so101_demo_py/test/test_macos_unified_service_launcher.py \
  src/so101_teleop/web/e2e/expert-validation/fixtures/live-sim.ts \
  src/so101_teleop/web/e2e/expert-validation/live-sim/06-fixed-n-execution.spec.ts \
  src/so101_teleop/web/e2e/expert-validation/live-sim/07-retry-full-restart.spec.ts
git diff --cached --check
git commit -m "test: add closed macOS live service windows"
```

---

### Task 8: 用短路径 runner 清零剩余真实静态失败

**Files:**
- Modify only: 每个 fresh failure manifest 所指向的 owning source/test/CMake 文件
- Modify: `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md`

**Interfaces:**
- Consumes: Task 4 runner
- Produces: 按 nodeid、首个异常和 owning subsystem 分类的 fresh failure manifest

- [ ] **Step 1: 重建固定 install 并回读 CTest registration**

确认没有 task-owned live stack 或其他 writer 后执行：

```zsh
export TASK_ROOT=/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1
build_run=$(mktemp -d "$TASK_ROOT/remediation-build-XXXXXXXX")
scripts/so101-macos.zsh prepare >"$build_run/prepare.log" 2>&1
prepare_rc=$?
print -r -- "$prepare_rc" >"$build_run/prepare.exit"
test "$prepare_rc" -eq 0
scripts/so101-macos.zsh doctor --json >"$build_run/doctor.json"
rg -n 'test_unified_lease_maintenance|test_unified_lease_projection' \
  /opt/data/so101/workspace/build/so101_teleop/CTestTestfile.cmake \
  >"$build_run/ctest-registration.txt"
shasum -a 256 "$build_run"/* >"$build_run/SHA256SUMS"
```

Expected: fixed project install 来自当前 HEAD；doctor PASS；两个新增 CTest registration 都存在。此后 direct pytest、colcon 和 live 都必须 read back 当前 install provenance，不得测试旧 installed bytes。

- [ ] **Step 2: 第一次完整 short-path gate**

```zsh
scripts/so101-macos-service-campaign-final-gate.zsh \
  --worktree /Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp \
  --evidence-root /tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1 \
  --python /opt/ros2_jazzy/.venv/bin/python
```

Expected: 不再出现任何 `*_SOCKET_PATH_TOO_LONG`、`PATH_OWNER`、`SO101_TASK_ROOT KeyError` 或 `/proc` portability failure。runner 生成完整 failure manifest。

- [ ] **Step 3: 逐个处理剩余失败**

已知必须核对的边界包括：

- `test_unified_lifecycle.py::test_composition_builds_a_readable_app_without_ros` 的 validation/lease-maintenance error shape；
- unified bridge/two-channel child exit 是否仍是 socket path 的下游错误；
- production projection/cancel 和 supervisor 是否仍有真实失败；
- fixed MPS StartGuard 是否仍返回 `GPU_TARGET_UNAVAILABLE`；
- CMake package registration 是否完整。

每个 owning boundary 单独执行：写最小 RED、运行并保存 rc/JUnit、做最小修复、定向 GREEN。不得把多种根因混入同一个补丁。

- [ ] **Step 4: 每轮代码修复后重建并执行第二次完整 short-path gate**

只要 source/CMake 发生变化，先重复 Step 1 的 `prepare`、doctor 和 CTest readback，再重复 Step 2 runner。Expected: demo、teleop、copied-install、colcon test-result、Web tsc/test/build 和必需 Playwright projects 全部 rc=0；JUnit errors=0、failures=0；收集数量非零。

- [ ] **Step 5: scoped commits**

按 owning subsystem 分开提交。process identity 使用 `fix: make recovery process inventory portable`，package registration 使用 `test: register unified lease contracts`，其余 residual 使用能精确描述 owning boundary 的 scoped message。每个 commit 前运行 `git diff --cached --check`，并证明 staged diff 只包含本 Task 列出的文件。

---

### Task 8B: 实测 task-owned crash、fence 和 operator recovery

**Files:**
- Modify if RED reproduces: `src/so101_teleop/so101_teleop/expert_validation/operator_recovery.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_operator_recovery.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_e2e_installed_port.py`
- Modify: `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md`

**Interfaces:**
- Consumes: 当前安装产物、真实 owner tree、service fence、cross-platform `RuntimeInspector`
- Produces: crash/recovery receipt，证明只回收 task-owned descendants，identity 不可证时保留 fence 且 zero signal

- [ ] **Step 1: 为 recovery 决策写 RED**

表驱动测试至少覆盖：leader crash 后 PID/birth 仍匹配的 task-owned descendants 按 leaf-first 顺序回收；unknown ancestry、`AccessDenied`、PID reuse/birth drift、partial inventory 和 foreign sentinel 都返回 `RECOVERY_RUNTIME_UNVERIFIABLE`，保留 fence，`signals_sent=[]`。任何 case 都不能通过 command substring 或全机 `ps | grep` 决定 ownership。

- [ ] **Step 2: 运行 RED、做最小修复并定向 GREEN**

```zsh
/opt/ros2_jazzy/.venv/bin/python -m pytest -q \
  src/so101_teleop/test/teleop/test_expert_validation_operator_recovery.py \
  src/so101_teleop/test/teleop/test_expert_validation_e2e_installed_port.py \
  -k 'crash or recovery or fence or identity'
```

- [ ] **Step 3: 在 live 实验前重建并冻结本 Task 的 install**

若 Step 2 修改 source，立即重复 Task 8 Step 1 的 `prepare`/doctor/CTest readback，再运行定向 installed tests；live service 必须从这次新 install 启动，不能先实验再重建。

- [ ] **Step 4: 在独立 service window 做真实 crash recovery**

只启动 task-owned installed service 和一个模拟 campaign，不接真实机械臂。启动前创建一个不属于 owner tree 的 foreign sentinel，并冻结它的 PID/birth。随后让一个明确记录 PID/birth/role 的 task-owned adapter/service 进程异常退出，触发 operator recovery。receipt 必须包含：owner/leader/descendant PID+birth、信号顺序、每次 identity recheck、fence 状态、端口/IPC 清理、最终 residue=0，以及 foreign sentinel 的前后 PID/birth 和存活证明。

再运行一个 negative live control：在注入 identity drift 或 inventory unreadable 后请求 recovery。Expected: fence 保留、zero signal、foreign sentinel 和原 owner tree 均不被误杀；测试自行关闭其可证明 task-owned 的进程并记录 cleanup。未知进程只登记，不发信号。

- [ ] **Step 5: 更新 ledger、重跑相关静态门禁并提交**

真实 crash case、negative control、cleanup receipt 和 SHA256 缺一项都不能完成本 Task。执行 Task 8 runner，确认它使用 Step 3 的 install provenance；不得在实验后再次 `prepare`，除非又修改了 source 且本 Task 的 live 必须全部重跑。

---

### Task 10: 最后一次构建、冻结 farm/install，并重跑 Gate A 五次 FULL_RESTART

> 执行顺序：先完成下方 Task 9 的 guide/plan 最终修改和提交，再回到本 Task。Task 10 开始后，除 ledger checkpoint 外不得再修改仓库字节。

**Files:**
- Modify: `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md`

**Interfaces:**
- Consumes: Tasks 2–9 已提交的最终 source/docs、`FixedDylibFarmRuntimeContract` 和产品 attestation
- Produces: 最终 install/farm identity、五个连续独立 owner-bound Gate A records、`CP-MSC-A2-FARM`

- [ ] **Step 1: 执行全流程最后一次 `prepare`，随后冻结**

确认没有 task-owned live stack 后，只执行一次：

```zsh
export TASK_ROOT=/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1
freeze_run=$(mktemp -d "$TASK_ROOT/final-freeze-XXXXXXXX")
scripts/so101-macos.zsh prepare >"$freeze_run/prepare.log" 2>&1
print -r -- "$?" >"$freeze_run/prepare.exit"
scripts/so101-macos.zsh doctor --json >"$freeze_run/doctor.json"
```

把此时 HEAD 记为 `frozen_product_source_sha`，同时冻结 submodule、所有非 ledger tracked bytes 的 tree digest、`/opt/data/so101/workspace/install` inventory、关键 executable/Web bundle SHA、farm logical path、resolved target、manifest bytes/inventory SHA 和 doctor receipt。这里之后只允许只读 `doctor`/provenance 检查，以及对 `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md` 的 checkpoint-only descendant commit。ledger-only commit 必须满足：HEAD 是 `frozen_product_source_sha` 的 descendant、`git diff --name-only frozen_product_source_sha..HEAD` 只有该 ledger、非 ledger tree digest/product install/farm inventory 全部不变。`setup-macos-ros-dylib-farm.zsh` 每次都会生成新 target，所以任何再次 `prepare`、farm `current` target 变化或任一非 ledger byte 变化都立即使 A2 失效，并要求从新 experiment id 重开 Task 10/11。

- [ ] **Step 2: 为五轮分别写 PLANNED ledger entries**

每轮固定同一 `frozen_product_source_sha`、同一个 resolved farm target/manifest、install inventory SHA 和启动合同；生命周期为 `FULL_RESTART`。任何 invalid control 都终止当前批次，修正后返回 Step 1 并从新 experiment id 重新开始五轮。

- [ ] **Step 3: 用唯一 launch-owning farm diagnostic 跑五轮**

每轮先只读运行 `scripts/so101-macos.zsh doctor --json`，并核对其 farm/install identity 等于 Step 1；生成包含本轮 session/domain、frozen farm receipt SHA 和 spawn intent 的 `run-binding.json`。随后只运行下面一个 station owner：

```zsh
round_dir=$(mktemp -d "$TASK_ROOT/gate-a2-round-XXXXXXXX")
scripts/so101-macos.zsh run so101_demo_py so101_diagnose_macos_station \
  --mode FIXED_DYLIB_FARM_FULL_TASK_STATION \
  --farm-contract-receipt "$freeze_run/doctor.json" \
  --run-binding "$round_dir/run-binding.json" \
  --output "$round_dir/station-report.json" \
  --timeout-s 180
```

这个 Task 3 新增的 farm mode 自行完成 intent、spawn、`motion_stack_ready`、attestation 和 shutdown。不得在它之前另跑 `scripts/so101-macos.zsh launch`；不得传旧 `--control-set-manifest/--control`；不得用 ad-hoc shell parser 代替产品 schema validator。

每轮必须记录：owner PID/birth、controller descendant PID/birth/executable、plugin/vendor path+SHA、Python/ament/launch provenance、farm logical path/resolved target/manifest+inventory SHA、3 controllers、3 services、3 actions、bounded shutdown、task-owned residue=0。不得从全机进程列表猜 owner。每轮必须 fresh spawn，上一轮完全清理后才进入下一轮。

- [ ] **Step 4: 五轮 schema readback 和负向 drift control**

用 Task 3 的 repository schema validator 回读五个 `station-report.json` 及 binding；任一 `executable=null`、wrong owner、path/SHA drift、cleanup residue 或 readiness 缺项都使该轮 INVALID，不能计入 5/5。另做不计入 5/5 的负向 fixture control：改变 farm resolved target、manifest SHA 或 inventory entry，farm mode 必须在 spawn 前拒绝并报告 `spawned=false`；不得修改真实 fixed farm。

- [ ] **Step 5: 新增 `CP-MSC-A2-FARM` 并提交 ledger**

只有连续 5 个 VALID、负向 drift control 和 Step 1 identity 再回读都通过，才写 `CP-MSC-A2-FARM=CURRENT_PRODUCT_GATE_PASSED_UNDER_FIXED_DYLIB_FARM`。历史 `CP-MSC-A1`、literal no-DYLD FAIL 和旧 N/P/F 原文保持不变。提交 ledger 后立即验证该提交是 allowlisted ledger-only descendant；不再运行 `prepare`。

---

### Task 9: 修正 guide、ledger 和最终运行命令

**Files:**
- Modify: `docs/guides/so101-macos-service-campaign-closure.md`
- Modify: `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md`
- Modify: `docs/superpowers/plans/2026-09-21-so101-macos-service-campaign-closure-implementation.md`

**Interfaces:**
- Produces: service-driven operator recipe；standalone station 仅作为独立诊断流程

- [ ] **Step 1: 修正 guide 启动顺序**

主 campaign recipe 只能按以下顺序：doctor → unified service → lease/context → start campaign → evidence readback → 按 owner PID 停止 service → residue readback。不得先以前台方式启动长期 standalone station。

standalone station 放到“诊断”章节，明确使用独立窗口/session，结束后按 owner PID 有界停止，并在进入 campaign 前证明无 station residue。

- [ ] **Step 2: 修正状态声明**

删除“失败数与上次相同所以是既有失败/受影响层 GREEN”这类推断。ledger 保留每次历史失败计数，并追加修复后的新鲜 gate；不覆盖旧条目。guide 只报告最新已审查 checkpoint。

- [ ] **Step 3: 运行文档和 contract tests**

```zsh
/opt/ros2_jazzy/.venv/bin/python -m pytest -q \
  src/so101_demo_py/test/test_macos_install_contract.py \
  src/so101_teleop/test/teleop/test_expert_validation_macos_service_campaign.py
git diff --check
```

- [ ] **Step 4: 使用 `$humanizer-zh` 审阅中文 guide，提交**

```zsh
git add -- \
  docs/guides/so101-macos-service-campaign-closure.md \
  docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md \
  docs/superpowers/plans/2026-09-21-so101-macos-service-campaign-closure-implementation.md
git diff --cached --check
git commit -m "docs: correct macOS service campaign closure"
```

Task 9 提交后进入上方 Task 10。除 Task 10/11 的 ledger checkpoint 外不得再修改 source、CMake、guide、design、plan、Web bundle 或测试；若后续审查要求修改这些字节，返回 owning Task，重新 `prepare`，并从新的 experiment id 重跑 Task 10 和 Task 11。

---

### Task 11: 受影响 live 复验和最终审查

**Files:**
- Modify: `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md`

**Interfaces:**
- Consumes: 当前最终 commit、Gate A 5x、完整静态 GREEN、冻结的 20 点 selection
- Produces: fresh W2、W1、single-point retry、crash recovery、cleanup 和 browser evidence；`CP-MSC-FINAL`

- [ ] **Step 1: 只读回验 Task 10 冻结产物并冻结 20 点 selection**

不得再运行 `prepare`。先断言当前 HEAD 是 `frozen_product_source_sha` 的 descendant，且其 diff 只有 allowlisted ledger；再只读运行 `scripts/so101-macos.zsh doctor --json`，并断言 submodule、非 ledger tree digest、farm resolved target/manifest/inventory SHA、`/opt/data/so101/workspace/install` inventory、关键 console scripts、Python/ament package prefixes 和 Web dist bundle SHA 与 Task 10 Step 1 完全一致。任一非 ledger drift 立即使 A2 失效，返回 Task 10；后续所有服务进程必须从这份 frozen install provenance 启动。

为 first-pass 冻结一个精确的 20 点 selection manifest：4 个固定点和 16 个生成点，包含 point id、坐标、生成参数、顺序、catalog SHA 和 selection SHA。W2 与 W1 使用同一份冻结 selection；启动后 UI/API projected selection digest 必须与冻结 SHA 相同。

- [ ] **Step 2: 静态门禁最终复跑**

再次运行 Task 8 的完整 runner。保存 summary、JUnit、所有真实 rc 和 SHA256。任何 failure/error/zero collection 阻止 live 复验。随后显式运行 installed Chrome gate：

```zsh
export SO101_TASK_ROOT=/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1
export SO101_E2E_EVIDENCE_ROOT="$SO101_TASK_ROOT/final-installed-$(date -u +%Y%m%dT%H%M%SZ)-$$"
export SO101_E2E_PYTHON=/opt/ros2_jazzy/.venv/bin/python
export SO101_E2E_INSTALL_PREFIX=/opt/data/so101/workspace/install
cd src/so101_teleop/web
bunx playwright test --config playwright.installed.config.ts --workers=1
```

保存 argv、环境白名单、Playwright JSON、stdout/stderr、rc 和 SHA256。不得用 package-script wrapper 的零退出码掩盖 project failure。

- [ ] **Step 3: 只复验受修改边界**

使用一个 service instance 同时只跑一个 active campaign：

1. W2 first-pass：固定 20 点、`worker_count=2`、`gpu_selector=MPS:default`；验证 4 fixed + 16 generated、selection-only、两 worker、每点恰好一次、projection、cleanup；
2. W1 first-pass：同一冻结 20 点、`worker_count=1`、`gpu_selector=MPS:default`；验证单 worker 排空同一 queue、每点恰好一次、projection、cleanup；
3. retry 独立窗口先用同一 frozen 20 点完成自己的 W1 first-pass，在同一页面现场冻结一个真实业务 `FAILED` 且 terminal-clean 的 binding，再执行一次 v5 `FULL_RESTART_RETRY`：验证 one point/one lease/one attempt/one commit、first-pass bytes 不变、合法 failed-before-physical shape、cleanup；
4. fresh Chrome 查看对应点位、进度、证据和 retry 结果；
5. 每个窗口结束后读回 owner tree、ports、IPC 和 task-owned residue，并重验 service executable/install/bundle SHA 没有漂移。

retry 再次业务失败不自动等于流程失败；但 reader/projection/cleanup 任一失败都使验收失败。

fixed-n 和 retry 必须保持“每个 console spec 一个独立 service window”。W2 与 W1 分别启动、验收、关闭，不共享活动 campaign；retry 必须在同一页面先完成/载入 first-pass，再触发 retry，不允许用合成 API 记录代替 UI 流程。使用 Task 7B 的 closed runner：

```zsh
TASK_ROOT=/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1
scripts/so101-macos-service-campaign-live-window.zsh \
  --case w2 --task-root "$TASK_ROOT" \
  --selection-manifest "$TASK_ROOT/final-selection/selection-20.json" \
  --install-prefix /opt/data/so101/workspace/install
scripts/so101-macos-service-campaign-live-window.zsh \
  --case w1 --task-root "$TASK_ROOT" \
  --selection-manifest "$TASK_ROOT/final-selection/selection-20.json" \
  --install-prefix /opt/data/so101/workspace/install
scripts/so101-macos-service-campaign-live-window.zsh \
  --case retry --task-root "$TASK_ROOT" \
  --selection-manifest "$TASK_ROOT/final-selection/selection-20.json" \
  --install-prefix /opt/data/so101/workspace/install
```

runner 内部必须显式设置并在 receipt 回读 `SO101_LIVE_SIM_HOST=$(hostname)`、`SO101_LIVE_SERVICE_BASE_URL=http://127.0.0.1:8013`、真实 `SO101_LIVE_SERVICE_STATE_ROOT`、单 case `SO101_FUNCTIONAL_MANIFEST`、closed `SO101_LIVE_CASE_ID`、`SO101_TASK_ROOT`、`SO101_E2E_EVIDENCE_ROOT`、`SO101_E2E_INSTALL_PREFIX` 和 `SO101_E2E_PYTHON`。它先运行 Playwright `--list` 并断言只收集当前一个 R06/R07 目标及必要 preflight，再启动 installed service、做 health/PID/birth readback、运行对应 project、按同一 PID/birth 停止并证明 residue=0。

如果该 retry window 自己的 frozen-20 first-pass 没有真实 eligible business-failed point，retry 状态必须是 `BLOCKED_NO_ELIGIBLE_POINT`，不能用 fault-injected、合成记录或别的 service window 的 binding 替代。`07-retry-full-restart.spec.ts` 必须从本窗口刚完成且原始 bytes 已冻结的 first-pass evidence 中选择真实 eligible failed point。

- [ ] **Step 4: 把 Task 8B 的 recovery live case 纳入最终验收**

在最终 install 上重新执行 task-owned crash recovery positive case 和 identity-drift negative control。Expected: positive case leaf-first 清理且 residue=0；negative case fence 保留且 zero signal；foreign sentinel 始终存活。完成 readback 后只停止可证明 task-owned 的 sentinel/fixture，保存 cleanup receipt。

- [ ] **Step 5: GPT-5.6 Sol / High 结果审查**

审查实际 diff、完整 gate、Gate A 5x、20 点 W2/W1、retry/browser、crash recovery、installed provenance 和 retained/archived/deletion-candidate accounting。未通过时返回 owning Task，不写 FINAL PASS。

- [ ] **Step 6: GPT-6 Astra / High 独立终审**

独立审查修订后的设计、计划、guide、ledger、代码、测试和 live evidence。P0/P1/P2 finding 未关闭前不得标记 `CP-MSC-FINAL`。

- [ ] **Step 7: 最终 checkpoint、本地提交和 writer release**

ledger 分别列 retained、archived、deletion candidates；不删除。确认没有未归属 dirty 文件。只有两次审查都通过，才写 `CP-MSC-FINAL=PASS`。

```zsh
git add -- docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md
git diff --cached --check
git commit -m "docs: close macOS service campaign remediation"
git status --short
```

最终报告必须给出 branch、HEAD、submodule、所有 scoped commits、完整 gate 计数、Gate A 5x、W2/W1/retry 结果、process cleanup、retained/archived/deletion candidates 和“未 push/未 merge”。

最后在 dispatch 目录写入机器可读 `writer-release.json`，至少包含 dispatch id、最后 HEAD、ledger SHA、所有 review verdict、task-owned residue、retained/archived/deletion candidates、`writer_released_at` 和 `next_writer=null`。写入后停止修改 worktree；orchestration owner 回读该 marker 和账本后再决定后续动作。
