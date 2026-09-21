# SO-101 macOS service campaign 闭环实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking。Task 1 由单独的 Codex session 在 mac-mini 当前 worktree 中执行；Task 2 起才交回 tmux session `dst-so101-macos-closure` 中的 DeepSeek Harness TUI（`dst`）inline 执行。每个 checkpoint 由 GPT-5.6 Sol / High 复核，设计、计划和最终 guide 由 GPT-6 Astra / High 独立审查。

**Goal:** 在 macOS MuJoCo 仿真上闭合统一 Web 服务的 W2 first-pass、W1 first-pass 与单点 `FULL_RESTART_RETRY`，只使用现有轻量 `StartGuard` 做启动保护，并完成可恢复 projection、真实 owner tree 和 fresh Chrome 验收。

**Architecture:** macOS 固定只支持 W1/W2。schema v4 保持 exact-W2；schema v5 表达 W1 retry；schema v6 表达 W1 ordinary first-pass。Web selection 进入 durable shared queue，每个 Worker lease 只执行一个点；既有 `CoordinatorJournal` 用 committed watermark 向唯一 reducer 提供权威事件。`StartGuard` 在 campaign 和每个 Worker spawn epoch fresh 执行，运行期安全由既有 hard timeout、lease、owner tree、fence 和 cleanup 收敛。

**Tech Stack:** Python 3.11、SQLite、ROS 2 Jazzy、MoveIt 2、ros2_control、MuJoCo、PyTorch MPS、AF_UNIX、FastAPI/Pydantic、React/TypeScript、Bun、Vitest、Playwright、pytest、colcon/CMake/gtest。

**Spec:** [SO-101 macOS service campaign 闭环设计](../specs/2026-09-21-so101-macos-service-campaign-closure-design.md)。执行恢复锚点为本地提交 `fea8f57c`、`e264d1eb`、`82b7a7d9`；执行器必须先回读其完整 SHA 与 ancestry。

## Global Constraints

- 本计划从 legacy `CP-MSC-A` 恢复，但该 checkpoint 的结论是 `UNCONFIRMED`，不是 PASS。task-owned station 曾 READY；5x `FULL_RESTART` 尚未执行。
- 已完成的 Task 0–2 不重跑、不改写。先回读三个恢复提交、ledger、证据和 dirty state；缺失或 ancestry 不符即停止。
- Gate A 使用 mac-mini 当前 worktree `/Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp` 和分支 `codex/so101-unified-webapp`，不得另建 worktree。Task 1 开始前必须暂停 `dst-so101-macos-closure`；handoff 完成后，Gate A Codex session 是该 worktree、ledger 和 task-owned 服务的唯一 writer，`dst` 不得写入或启动服务。
- Gate A Codex 在 `CP-MSC-A1` 后退出或明确释放 writer。GPT-5.6 Sol / High 复核通过后，才通知 `dst-so101-macos-closure` 接回 writer 并进入 Task 2。旧 `dst-so101-macos-mps-w2` 只保留，不接管。
- 不授权真实机械臂、sudo、系统/全局环境修改、停止 foreign 进程、删除或归档证据、push、merge、force push 或发布。
- 继续使用已有单写 ledger `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md` 和已登记的唯一 evidence root `/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1`。Task 1 只在其下新建 `gate-a-resolution/$DISPATCH_ID/`；不得创建第二个 root。legacy 条目和旧 evidence 只读，每次新实验先写 `PLANNED`。
- macOS 不套用 ai-station 的 `/data` NVMe pytest scratch 规则。每个测试调用使用 evidence root 下新子目录，并设置 task-local `ROS_HOME`、`ROS_LOG_DIR`、`TMPDIR`、`TMP`、`TEMP`。
- 所有产品修改严格 RED -> GREEN；依赖导入、DYLD bootstrap、零收集和未执行到目标边界不算 RED。
- schema v4 bytes/SHA 与 exact-W2 含义保持不变。v5 只允许 Darwin/MPS W1 `FULL_RESTART_RETRY`；v6 只允许 Darwin/MPS W1 `FIRST_PASS`。
- macOS `worker_count` 只允许 1/2。N>2 Web 不可选，API/preflight/adapter 拒绝。worker profile 不从 point count 推断。
- 只复用现有 `StartGuard`：RAM 和 MPS headroom FAIL 阻止 spawn，CPU busy 只 WARN，probe/identity/scope/cleanup error fail closed。不得新增 sampler、运行期 watchdog或容量公式。
- `so101_measure_parallel_resources` 保持 retired/fail closed；不创建替代入口，不修改旧预算设计/计划。
- `PointStatus` 仍只有 `UNRUN/PASSED/FAILED/INDETERMINATE`。`RUNNING` 属于 execution phase，`INVALID` 属于 attempt validity。
- 一个 service instance 同时只允许一个 active campaign 和一个有效 control lease。W1/W2 不并行。
- 每个 task 只 stage 自己列出的文件，运行 `git diff --check` 和 scoped diff readback 后提交；不用 `git add -A`。
- live 验收只声明功能、稳定性、物理结果、projection、ownership 和 cleanup，不声明 resource qualification 或 capacity certification。

## 已完成快照与恢复规则

| 已有事实 | 状态 |
| --- | --- |
| runtime closure、run binding、attestation 实现 | 已在恢复提交中，执行前回读测试与 diff |
| controller 直连诊断与 MoveIt readiness 分离 | 已在恢复提交中，执行前回读测试与 diff |
| task-owned full station READY | OBSERVED：3 controllers、3 services、3 actions |
| 旧卡死 | 只在 incomplete dylib closure 中复现，`@rpath/libmujoco.3.4.0.dylib` load failure |
| legacy C++ controller 归因 | `UNCONFIRMED`；foreign modified overlay 未重跑，无 C++ 产品修改，永久保留原结论 |
| Gate A 5x FULL_RESTART | NOT RUN |

恢复时只读引用 legacy `CP-MSC-A`、旧 root 和旧 ledger 行，不把它改写成 PASS。新的当前产品判定写入
`gate-a-resolution/$DISPATCH_ID/` 和新 ledger 行；旧 overlay 无法重建时记
`legacy_attribution=LEGACY_PROVENANCE_UNRECOVERABLE`，不据此判定当前产品失败。

## 文件与接口总图

| 边界 | 文件与职责 |
| --- | --- |
| Gate A / rpath | 新 `runtime/macos_dlopen_probe.py` 与测试；修改 station diagnostic、install/runtime closure 测试；仅 `CONFIRMED_RPATH` 时修改 submodule CMake、两份 dependency lock 与 candidate 常量 |
| selection / queue | 新 `parallel_batch/selection.py`、`queue.py`、`single_point_input.py`；修改 W2 campaign/worker/composition |
| journal / projection | 修改 `parallel_batch/journal.py`；新 `expert_validation/reducer.py`、`projection_source.py`；修改 events/models/store/production |
| owner tree | 新 `expert_validation/owner_tree.py`；修改 process owner/store/supervisor 和四个真实 spawn 边界 |
| W1/W2 profiles | 新 v5/v6 YAML、`w1_composition.py`、两个 W1 CLI；修改 contracts、adapter、setup |
| StartGuard spawn binding | 修改 `macos_service_campaign.py`、`campaign_supervisor.py`、`macos_w2_worker.py`、W1 composition；复用现有 guard/probe |
| execution authorization / retry | 新 `expert_validation/execution_context.py`；修改 API/models/store/supervisor/service/statistics |
| support matrix / Web | 修改 preflight/api/production、unified app、campaign setup/app、生成 OpenAPI/types 和 live-sim tests |
| 最终文档 | 修改 task ledger；新 `docs/guides/so101-macos-service-campaign-closure.md` |

---

### Task 1: 接管当前 worktree，关闭当前产品 Gate A，并完成 5x readiness

Task 1 由单独的 Codex session 执行。它复用当前 mac-mini worktree 和 branch，不另建 worktree，也不依赖
重跑 foreign modified overlay。该 session 必须在 `CP-MSC-A1` 停止，禁止进入 Task 2。

**Files:**
- Create: `src/so101_demo_py/src/runtime/macos_dlopen_probe.py`
- Create: `src/so101_demo_py/test/test_macos_dlopen_probe.py`
- Modify: `src/so101_demo_py/src/runtime/runtime_closure.py`
- Modify: `src/so101_demo_py/src/cli/diagnose_macos_station.py`
- Modify: `src/so101_demo_py/test/test_diagnose_macos_station.py`
- Modify: `src/so101_demo_py/test/test_macos_install_contract.py`
- Modify: `src/so101_demo_py/test/test_runtime_closure.py`
- `CONFIRMED_RPATH` route only: `third_party/mujoco_ros2_control/mujoco_ros2_control/CMakeLists.txt`
- `CONFIRMED_RPATH` route only: `src/so101_demo_py/config/mujoco/dependency-lock.yaml`
- `CONFIRMED_RPATH` route only: `src/so101_demo_py/config/dependency-lock.yaml`
- `CONFIRMED_RPATH` route only: `scripts/check_backend_integration.py`
- Modify: `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md`

**Interfaces:**
- Consumes: committed `RuntimeClosureIdentity`, `RunBinding`, `RuntimeAttestation`, `so101_diagnose_macos_station`
- Produces: `GateAControlSetManifest`, `GateARunBinding`, `FrozenSemanticLaunchContract`, `DirectDlopenObservation`, `RuntimeProcessAttestation`, `GateAControlObservation`, `GateADecision`, `reduce_gate_a_controls(negative: GateAControlObservation, positive: GateAControlObservation) -> GateADecision`, `CurrentBoundaryVerdict`, `ControllerVerdict`, `LegacyAttribution`
- Closed values:
  - `CurrentBoundaryVerdict = UNCONFIRMED_CURRENT | CONFIRMED_RPATH | CURRENT_CLOSURE_ALREADY_VALID | CURRENT_NON_RPATH_FAILURE | INVALID_CONTROL`
  - `ControllerVerdict = NOT_EXCLUDED | EXCLUDED_BEFORE_ROS_PLUGIN_INSTANCE_INIT | CURRENT_CONTROLLER_PATH_OPERATIONAL`
  - `LegacyAttribution = LEGACY_TRACEABLE | LEGACY_PROVENANCE_UNRECOVERABLE`
- Produces: no-DYLD current-product attestation、five consecutive valid readiness records、`CP-MSC-A1`

- [ ] **Step 1: 串行接管 writer，并建立本轮 evidence 子目录**

先由 orchestration owner 确认 `dst-so101-macos-closure` 已暂停，不再持有运行中命令、服务或 ledger
写权限。Gate A Codex 随后在下列固定路径接管唯一 writer：

```bash
cd /Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp
test "$(git branch --show-current)" = codex/so101-unified-webapp
git status --short --branch
git show --no-patch --oneline fea8f57c
git show --no-patch --oneline e264d1eb
git show --no-patch --oneline 82b7a7d9
git submodule status --recursive
export TASK_ROOT=/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1
export DISPATCH_ID="$(uuidgen | tr '[:upper:]' '[:lower:]')"
export GATEA_RUN_ROOT="$TASK_ROOT/gate-a-resolution/$DISPATCH_ID"
mkdir -p "$GATEA_RUN_ROOT"/{control-set,negative,positive,fixed,tmp,ros-home,ros-logs}
mkdir -p "$GATEA_RUN_ROOT/tests/red" "$GATEA_RUN_ROOT/tests/green"
export TEST_PYTHON=/Users/matianyi/ros2_jazzy/.venv/bin/python
export COLCON=/Users/matianyi/ros2_jazzy/.venv/bin/colcon
export CLOSURE_ROOT="$GATEA_RUN_ROOT/control-set/closure"
export ROS_HOME="$GATEA_RUN_ROOT/ros-home"
export ROS_LOG_DIR="$GATEA_RUN_ROOT/ros-logs"
export TMPDIR="$GATEA_RUN_ROOT/tmp"
export TMP="$TMPDIR"
export TEMP="$TMPDIR"
```

在新 ledger 行登记 handoff 时间、前任 writer、当前 writer、branch/HEAD/submodule SHA、旧 ledger
hash、`TASK_ROOT` 与 `GATEA_RUN_ROOT`。legacy `CP-MSC-A` 和旧 evidence 只读；不得把本轮文件写到
`gate-a-resolution/` 之外。Expected: 只有 Gate A Codex 一个 writer，当前 worktree 无未归属改动，
`legacy_attribution` 独立记录；无法恢复 foreign overlay 时使用
`LEGACY_PROVENANCE_UNRECOVERABLE`，但不改变当前 Gate 判定。

- [ ] **Step 2: RED -> GREEN 实现固定 control set 和 direct dlopen 证据**

先写 RED，覆盖：closed enum；manifest 缺项或 SHA 不符 fail closed；N/P 除
`DYLD_LIBRARY_PATH` 外任一 semantic 差异均为 `INVALID_CONTROL`；typed `RunBinding` substitution
先验证再归一化，非法 path/domain/session 或任意额外忽略项都拒绝；expanded argv/env 必须保存；
direct `dlopen(RTLD_NOW|RTLD_LOCAL)` 输出 `DLOPEN_STARTED`、`DLOPEN_SUCCEEDED` 或
`DLOPEN_FAILED` 和原始 `dlerror`；station phase marker 只在真实越过对应 ROS 边界后写出。

`GateAControlSetManifest` 固定 parent/submodule commit、copied-install inventory、可执行文件、plugin、
vendor dylib、plugin XML、config/model 的路径与 SHA、`FrozenSemanticLaunchContract`、ROS domain
policy、tool versions 和 `GATEA_RUN_ROOT`。`GateARunBinding` 只允许
`session_id/ros_domain_id/report_path/task_evidence_root/ROS_HOME/ROS_LOG_DIR/TMPDIR=TMP=TEMP`
这些 typed substitution。`DirectDlopenObservation` 固定 control 名称、marker、错误文本、loaded-image
path/SHA；direct dlopen initializer 明确不等于 ROS plugin instance init。probe 通过 `execve` 启动 child：N 从 allowlist 重建环境
并排除所有 `DYLD_*`，P 在同一环境上只加入一个 manifest-bound `DYLD_LIBRARY_PATH`；任何额外
`DYLD_*` 都 fail closed。station diagnostic 新增 closed `FULL_TASK_STATION` mode，只能启动 installed
`so101_mujoco_task_station.launch.py` 的固定 argv，并在同一进程树内做 direct controller 和 MoveIt
readiness。`DYLD_PRINT_*` 只能作为辅助日志，不能替代该记录。

`runtime_closure.py` 新增 per-process collector/validator。role 由 launch spawn intent 在 PID 出现前
绑定，随后用 owner ancestry、PID/birth、executable 和该 PID 的 ROS phase evidence 确认；不得在
结果出来后按“哪个进程恰好加载了 dylib”反推 role。`RuntimeProcessAttestation` 至少含
`role/pid/birth/executable/loaded_images[path,sha256]`；`controller_runtime` 必须是 owner tree 中真实
承载 controller 的 descendant，并同时加载 manifest-bound plugin 和 vendor。空 images、probe 或
launcher 冒充、wrong child、PID/birth/executable drift 全部拒绝。`reduce_gate_a_controls()` 是纯函数，
表驱动 RED 覆盖 N-pass/P-fail、相同/不同 loader failure、timeout、missing marker、错误或缺失
process attestation、identity drift、cleanup residue、semantic diff，以及默认未列组合。

把现有“拒绝所有 symlink”合同收窄成唯一 closed alias 合同。新增 `DylibAliasIdentity` 并将 closure
schema 升级：只允许
`opt/mujoco_vendor/lib/libmujoco.dylib -> libmujoco.3.4.0.dylib`，manifest 冻结 alias 相对路径、
原始 link text、target 相对路径和 target SHA；target 还必须以 regular file 进入普通 inventory。
inventory walker 不 follow symlink；它用 `lstat/readlink` 验证该 exact entry，要求单一相对 basename、
同目录、root containment、non-symlink regular target，并在读取 target 后再次核对 alias/target identity。
每次 control spawn 前重验。RED 必须覆盖合法 alias，以及 absolute、escape、dangling、cycle、multi-hop、
wrong link text、target byte replacement、alias replacement、额外 file symlink 和 directory symlink；后十类
全部返回 `CLOSURE_SYMLINK`。不得物化、改写或忽略标准安装 alias。

测试先按设计中的 required/allowed-absent 表实现单轮分类优先级：invariant/collector/identity/timeout/
cleanup 先于 missing-vendor、PASS 和 NON_RPATH。至少固定下面两个相邻用例，防止只按错误字符串
归因：

| Class | Required | Allowed absent |
| --- | --- | --- |
| `PASS` | valid manifest/semantic/binding、healthy collector、真实稳定 controller identity、`DLOPEN_SUCCEEDED`、plugin/vendor images、全 ROS markers、READY、cleanup complete | loader error、first-bad phase |
| `MISSING_VENDOR_BEFORE_ROS_PLUGIN_INSTANCE_INIT` | valid manifest/semantic/binding、healthy collector、真实 controller role/PID/birth/executable、`DLOPEN_FAILED`、精确 vendor loader error、无 ROS instance marker、cleanup complete | plugin/vendor images、`PLUGIN_RESOLVED` 起全部 markers、READY |
| `NON_RPATH_FAILURE` | valid invariants/collector/identity、`DLOPEN_SUCCEEDED`、plugin/vendor images、first-bad phase、cleanup complete | 首坏 phase 后 markers、READY |
| `INVALID` | 具体 invalid reason | 不允许用缺证据的表象升级成前三类 |

```python
def test_valid_n_missing_and_p_pass_confirms_rpath():
    assert reduce_gate_a_controls(valid_missing_vendor_n, valid_pass_p).current == CONFIRMED_RPATH

def test_same_loader_surface_without_collector_or_process_identity_is_invalid():
    assert reduce_gate_a_controls(unattested_missing_vendor_n, valid_pass_p).current == INVALID_CONTROL
```

RED 和 GREEN 使用不同 invocation 目录，JUnit、stdout、stderr、elapsed、exit code 与 SHA 不得覆盖：

```bash
export RED_INVOCATION="$GATEA_RUN_ROOT/tests/red/$(uuidgen | tr '[:upper:]' '[:lower:]')"
mkdir -p "$RED_INVOCATION"
SECONDS=0
set +e
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_macos_dlopen_probe.py \
  src/so101_demo_py/test/test_diagnose_macos_station.py \
  src/so101_demo_py/test/test_macos_install_contract.py \
  src/so101_demo_py/test/test_runtime_closure.py \
  --junitxml="$RED_INVOCATION/junit.xml" \
  >"$RED_INVOCATION/stdout.log" 2>"$RED_INVOCATION/stderr.log"
test_rc=$?
set -e
printf '%s\n' "$test_rc" >"$RED_INVOCATION/exit-code.txt"
printf '%s\n' "$SECONDS" >"$RED_INVOCATION/elapsed-seconds.txt"
shasum -a 256 "$RED_INVOCATION"/junit.xml "$RED_INVOCATION"/stdout.log \
  "$RED_INVOCATION"/stderr.log "$RED_INVOCATION"/exit-code.txt \
  "$RED_INVOCATION"/elapsed-seconds.txt >"$RED_INVOCATION/SHA256SUMS"
test "$test_rc" -ne 0
```

Expected RED: 测试非零收集，且只因上述新合同尚未实现而失败。实现最小接口后用新目录运行 GREEN：

```bash
export GREEN_INVOCATION="$GATEA_RUN_ROOT/tests/green/$(uuidgen | tr '[:upper:]' '[:lower:]')"
mkdir -p "$GREEN_INVOCATION"
SECONDS=0
set +e
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_macos_dlopen_probe.py \
  src/so101_demo_py/test/test_diagnose_macos_station.py \
  src/so101_demo_py/test/test_macos_install_contract.py \
  src/so101_demo_py/test/test_runtime_closure.py \
  --junitxml="$GREEN_INVOCATION/junit.xml" \
  >"$GREEN_INVOCATION/stdout.log" 2>"$GREEN_INVOCATION/stderr.log"
test_rc=$?
set -e
printf '%s\n' "$test_rc" >"$GREEN_INVOCATION/exit-code.txt"
printf '%s\n' "$SECONDS" >"$GREEN_INVOCATION/elapsed-seconds.txt"
shasum -a 256 "$GREEN_INVOCATION"/junit.xml "$GREEN_INVOCATION"/stdout.log \
  "$GREEN_INVOCATION"/stderr.log "$GREEN_INVOCATION"/exit-code.txt \
  "$GREEN_INVOCATION"/elapsed-seconds.txt >"$GREEN_INVOCATION/SHA256SUMS"
test "$test_rc" -eq 0
```

Expected GREEN: 非零收集、全部通过，且 RED/GREEN invocation 路径不同。随后提交只含 control tooling
和测试的冻结 commit：

```bash
git add -- src/so101_demo_py/src/runtime/macos_dlopen_probe.py \
  src/so101_demo_py/src/runtime/runtime_closure.py \
  src/so101_demo_py/src/cli/diagnose_macos_station.py \
  src/so101_demo_py/test/test_macos_dlopen_probe.py \
  src/so101_demo_py/test/test_diagnose_macos_station.py \
  src/so101_demo_py/test/test_macos_install_contract.py \
  src/so101_demo_py/test/test_runtime_closure.py
git diff --cached --check
git commit -m "test(so101): freeze macOS Gate A controls"
```

- [ ] **Step 3: 构建可追溯 copied install，冻结 manifest，并运行 N/P controls**

不复用旧 `gate-a/` 目录作为写入位置。参考旧 ledger 已验证的 package set，在本轮子目录构建单一
merged closure。先用仓库 installer 构建 pinned vendor：

```bash
export MUJOCO_AUTHORITY=/Users/matianyi/ros2_jazzy/extra_ws/src/mujoco
export VENDOR_WORKSPACE="$GATEA_RUN_ROOT/control-set/vendor-workspace"
export INSTALLER="$PWD/scripts/install-mujoco-vendor-macos.zsh"
export VENDOR_PATCH="$PWD/tools/mujoco_vendor_macos/patches/mujoco-3.4.0-glfw-no-primary-monitor.patch"
export MUJOCO_BUILD="$GATEA_RUN_ROOT/control-set/mujoco-build"
export MUJOCO_LOG="$GATEA_RUN_ROOT/control-set/mujoco-log"
export STATION_BUILD="$GATEA_RUN_ROOT/control-set/station-build"
export STATION_LOG="$GATEA_RUN_ROOT/control-set/station-log"
test "$(git -C "$MUJOCO_AUTHORITY" rev-parse HEAD)" = e55fff5dea6f1d5dd7963ca52eecc41d05ad0922
test -z "$(git -C "$MUJOCO_AUTHORITY" status --porcelain --untracked-files=all)"
git -C "$MUJOCO_AUTHORITY" rev-parse HEAD >"$GATEA_RUN_ROOT/control-set/authority-commit.txt"
git -C "$MUJOCO_AUTHORITY" status --porcelain --untracked-files=all \
  >"$GATEA_RUN_ROOT/control-set/authority-status.txt"
shasum -a 256 "$INSTALLER" "$VENDOR_PATCH" \
  >"$GATEA_RUN_ROOT/control-set/installer-patch-SHA256SUMS"
SECONDS=0
SO101_ROS_WORKSPACE=/Users/matianyi/ros2_jazzy \
SO101_ROS_UNDERLAY=/Users/matianyi/ros2_jazzy/install \
SO101_COLCON="$COLCON" SO101_PYTHON="$TEST_PYTHON" \
SO101_MUJOCO_SOURCE_ROOT="$MUJOCO_AUTHORITY" \
SO101_MUJOCO_VENDOR_WORKSPACE="$VENDOR_WORKSPACE" \
SO101_MUJOCO_VENDOR_INSTALL_PREFIX="$CLOSURE_ROOT" \
zsh "$INSTALLER" >"$GATEA_RUN_ROOT/control-set/vendor-install.stdout.log" \
  2>"$GATEA_RUN_ROOT/control-set/vendor-install.stderr.log"
printf '%s\n' "$SECONDS" >"$GATEA_RUN_ROOT/control-set/vendor-install.elapsed-seconds.txt"
test -f "$CLOSURE_ROOT/opt/mujoco_vendor/lib/libmujoco.dylib"
git -C "$VENDOR_WORKSPACE/src/mujoco" rev-parse HEAD \
  >"$GATEA_RUN_ROOT/control-set/prepared-source-commit.txt"
git -C "$VENDOR_WORKSPACE/src/mujoco" status --porcelain --untracked-files=all \
  >"$GATEA_RUN_ROOT/control-set/prepared-source-status.txt"
shasum -a 256 "$VENDOR_WORKSPACE/src/mujoco/simulate/glfw_adapter.cc" \
  >"$GATEA_RUN_ROOT/control-set/patched-source.sha256"
find "$CLOSURE_ROOT/opt/mujoco_vendor/lib" -type f -name 'libmujoco*.dylib' -exec shasum -a 256 {} \; \
  >"$GATEA_RUN_ROOT/control-set/vendor-dylib-SHA256SUMS"
```

authority checkout 只读；installer 只能把 clone、patch、build 写到 `$VENDOR_WORKSPACE`。随后 source
host underlays 与刚生成的 closure，用同一 `--merge-install` root 依次构建 submodule 和 station：

```bash
source /Users/matianyi/ros2_jazzy/install/setup.zsh
source /Users/matianyi/ros2_jazzy/extra_ws/install/setup.zsh
source "$CLOSURE_ROOT/setup.zsh"
"$COLCON" list --base-paths third_party/mujoco_ros2_control
"$COLCON" --log-base "$MUJOCO_LOG" build \
  --base-paths third_party/mujoco_ros2_control \
  --packages-up-to mujoco_ros2_control \
  --build-base "$MUJOCO_BUILD" --install-base "$CLOSURE_ROOT" --merge-install \
  --event-handlers console_direct+
source "$CLOSURE_ROOT/setup.zsh"
"$COLCON" list --base-paths src | rg '^(so101_mujoco_support|so101_demo_py)[[:space:]]'
"$COLCON" --log-base "$STATION_LOG" build \
  --base-paths src \
  --packages-select so101_mujoco_support so101_demo_py \
  --build-base "$STATION_BUILD" --install-base "$CLOSURE_ROOT" --merge-install \
  --event-handlers console_direct+
source "$CLOSURE_ROOT/setup.zsh"
export DIAGNOSTIC_EXE="$CLOSURE_ROOT/lib/so101_demo_py/so101_diagnose_macos_station"
test -x "$DIAGNOSTIC_EXE"
head -n 1 "$DIAGNOSTIC_EXE" >"$GATEA_RUN_ROOT/control-set/diagnostic-shebang.txt"
export MUJOCO_ALIAS="$CLOSURE_ROOT/opt/mujoco_vendor/lib/libmujoco.dylib"
test "$(find "$CLOSURE_ROOT" -type l -print)" = "$MUJOCO_ALIAS"
test "$(readlink "$MUJOCO_ALIAS")" = "libmujoco.3.4.0.dylib"
```

`RuntimeClosureIdentity.install_root` 必须精确写 `$CLOSURE_ROOT`。运行任何 control 前保存 bootstrap
readback，要求 ament prefix、Python modules、interpreter 与 shebang 全部精确绑定该 closure：

```bash
PYTHONNOUSERSITE=1 "$TEST_PYTHON" -c '
import json, pathlib, sys
from ament_index_python.packages import get_package_prefix
import so101_demo
import so101_demo.runtime.macos_dlopen_probe as probe
root = pathlib.Path("'"$CLOSURE_ROOT"'").resolve()
doc = {
  "interpreter": sys.executable,
  "module_file": str(pathlib.Path(so101_demo.__file__).resolve()),
  "probe_module_file": str(pathlib.Path(probe.__file__).resolve()),
  "ament_prefix": get_package_prefix("so101_demo_py"),
}
print(json.dumps(doc, sort_keys=True))
assert pathlib.Path(doc["ament_prefix"]).resolve() == root
assert pathlib.Path(doc["module_file"]).is_relative_to(root)
assert pathlib.Path(doc["probe_module_file"]).is_relative_to(root)
assert pathlib.Path(sys.executable).resolve() == pathlib.Path("'"$TEST_PYTHON"'").resolve()
' >"$GATEA_RUN_ROOT/control-set/bootstrap-readback.json"
test "$(head -n 1 "$DIAGNOSTIC_EXE")" = "#!$TEST_PYTHON"
shasum -a 256 "$GATEA_RUN_ROOT/control-set/bootstrap-readback.json" \
  "$GATEA_RUN_ROOT/control-set/diagnostic-shebang.txt" \
  >"$GATEA_RUN_ROOT/control-set/bootstrap-readback.sha256"
```

从这个 committed HEAD 生成 manifest，递归冻结 `$CLOSURE_ROOT` 全部 regular files 与 SHA，并按
上述 closed policy 冻结唯一 MuJoCo dylib alias、拒绝其他 symlink；
plugin、vendor 与 Python package 必须都在同一 root。N/P 共用
`FrozenSemanticLaunchContract`；每轮另写 `GateARunBinding`，保存验证后的 expanded argv/env：

- N（negative）清除全部 `DYLD_*`，先跑 direct dlopen，再跑
  `FULL_TASK_STATION`。
- P（positive）始终执行，只增加 `DYLD_LIBRARY_PATH=$CLOSURE_ROOT/opt/mujoco_vendor/lib`，其余与 N 完全相同，
  同样先 direct dlopen、再跑 `FULL_TASK_STATION`。
- 每次运行都保存 direct probe、structured phase、loaded images、controller direct query、MoveIt
  readiness、PID/birth、timeout 与 cleanup accounting。probe error、manifest/identity mismatch 或残留都
  使该 control 无效。

```bash
set +e
PYTHONNOUSERSITE=1 "$TEST_PYTHON" -m so101_demo.runtime.macos_dlopen_probe \
  --create-run-binding --manifest "$GATEA_RUN_ROOT/control-set/manifest.json" \
  --control N --run-root "$GATEA_RUN_ROOT/negative" \
  --session-id "gate-a-$DISPATCH_ID-n" \
  --output "$GATEA_RUN_ROOT/negative/run-binding.json"
n_binding_rc=$?
PYTHONNOUSERSITE=1 "$TEST_PYTHON" -m so101_demo.runtime.macos_dlopen_probe \
  --create-run-binding --manifest "$GATEA_RUN_ROOT/control-set/manifest.json" \
  --control P --run-root "$GATEA_RUN_ROOT/positive" \
  --session-id "gate-a-$DISPATCH_ID-p" \
  --output "$GATEA_RUN_ROOT/positive/run-binding.json"
p_binding_rc=$?
PYTHONNOUSERSITE=1 "$TEST_PYTHON" -m so101_demo.runtime.macos_dlopen_probe \
  --manifest "$GATEA_RUN_ROOT/control-set/manifest.json" \
  --run-binding "$GATEA_RUN_ROOT/negative/run-binding.json" \
  --control N --output "$GATEA_RUN_ROOT/negative/dlopen.json"
n_probe_rc=$?
PYTHONNOUSERSITE=1 "$TEST_PYTHON" -m so101_demo.runtime.macos_dlopen_probe \
  --manifest "$GATEA_RUN_ROOT/control-set/manifest.json" \
  --run-binding "$GATEA_RUN_ROOT/positive/run-binding.json" \
  --control P --output "$GATEA_RUN_ROOT/positive/dlopen.json"
p_probe_rc=$?
```

full-station 使用同一 environment builder；扩展后的 diagnostic 接受 manifest-bound control 和 report
路径，不接受任意 launch argv：

```bash
"$DIAGNOSTIC_EXE" \
  --mode FULL_TASK_STATION \
  --control-set-manifest "$GATEA_RUN_ROOT/control-set/manifest.json" \
  --run-binding "$GATEA_RUN_ROOT/negative/run-binding.json" --control N
n_station_rc=$?
"$DIAGNOSTIC_EXE" \
  --mode FULL_TASK_STATION \
  --control-set-manifest "$GATEA_RUN_ROOT/control-set/manifest.json" \
  --run-binding "$GATEA_RUN_ROOT/positive/run-binding.json" --control P
p_station_rc=$?
set -e
printf '%s\n' "$n_binding_rc" >"$GATEA_RUN_ROOT/negative/binding-exit-code.txt"
printf '%s\n' "$p_binding_rc" >"$GATEA_RUN_ROOT/positive/binding-exit-code.txt"
printf '%s\n' "$n_probe_rc" >"$GATEA_RUN_ROOT/negative/dlopen-exit-code.txt"
printf '%s\n' "$p_probe_rc" >"$GATEA_RUN_ROOT/positive/dlopen-exit-code.txt"
printf '%s\n' "$n_station_rc" >"$GATEA_RUN_ROOT/negative/station-exit-code.txt"
printf '%s\n' "$p_station_rc" >"$GATEA_RUN_ROOT/positive/station-exit-code.txt"
```

每份 binding 固定 safe `session_id`、fresh `ROS_DOMAIN_ID<=232`、report/evidence/ROS/TMP 的本轮
resolved paths。expanded launch argv 必须是
`ros2 launch so101_demo_py so101_mujoco_task_station.launch.py headless:=false
sensor_rendering:=true include_teleop:=false session_id:=@SESSION_ID@
task_evidence_root:=@TASK_EVIDENCE_ROOT@ readiness_timeout_s:=90.0
mujoco_scene:=@MANIFEST_SCENE@ mujoco_initial_keyframe:=task_start`；其中三个 `@...@` 是归一化 token，
expanded argv 中必须替换成 binding/manifest 验证后的绝对值。diagnostic
hard deadline 为 150 s。READY 后主动请求 shutdown，按 owner-tree deadline 完成 bounded cleanup，
不能期待 persistent launch 自行退出。除 typed substitution 外不得手工改参数。
完成后按下表写三个正交 verdict，不能把 legacy 归因塞进当前产品判定：

`MISSING_VENDOR_BEFORE_ROS_PLUGIN_INSTANCE_INIT` 只在 full station 报 manifest-bound vendor missing
dependency，且 `PLUGIN_RESOLVED`、`HARDWARE_INITIALIZING` 等 ROS phase marker 全部缺失时成立。
direct dlopen initializer 是否执行不参与这个判定。

| N class | P class | `current_boundary_verdict` | `controller_verdict` | 下一步 |
| --- | --- | --- | --- | --- |
| `MISSING_VENDOR_BEFORE_ROS_PLUGIN_INSTANCE_INIT` | `PASS` | `CONFIRMED_RPATH` | `EXCLUDED_BEFORE_ROS_PLUGIN_INSTANCE_INIT` | 进入 Step 4 rpath repair route |
| `PASS` | `PASS` | `CURRENT_CLOSURE_ALREADY_VALID` | `CURRENT_CONTROLLER_PATH_OPERATIONAL` | 不改 CMake；N 即 F，进入 Step 5 |
| `MISSING_VENDOR_BEFORE_ROS_PLUGIN_INSTANCE_INIT` | `NON_RPATH_FAILURE` | `CURRENT_NON_RPATH_FAILURE` | `NOT_EXCLUDED` | 停止，记录 P 首坏 ROS phase，修订 owning-layer plan |
| `NON_RPATH_FAILURE` | `PASS` 或同一 `NON_RPATH_FAILURE` | `CURRENT_NON_RPATH_FAILURE` | `NOT_EXCLUDED` | 停止，记录 N 首坏 ROS phase，修订 owning-layer plan |
| `PASS` | 任一非 `PASS` | `INVALID_CONTROL` | `NOT_EXCLUDED` | N/P 单变量合同被破坏；停止并修订 control plan |
| P 未消除 N 的相同或不同 loader failure | 任一非 `PASS` | `INVALID_CONTROL` | `NOT_EXCLUDED` | vendor binding/control 无法证伪 rpath；停止并修订 control plan |
| 任一 timeout、缺少该 observation class 表中要求的 marker/attestation、probe/launcher 冒充、wrong child、identity drift、cleanup residue、semantic diff 或非法 substitution | 任意 | `INVALID_CONTROL` | `NOT_EXCLUDED` | 停止本批并修订 control plan；不得把该 class 明确允许缺失的字段当成 invalid |
| 任意未列组合 | 任意 | `INVALID_CONTROL` | `NOT_EXCLUDED` | deterministic reducer 默认 fail closed |

`LEGACY_TRACEABLE` 或 `LEGACY_PROVENANCE_UNRECOVERABLE` 可与表中任一行并存。foreign overlay 无法复现
不是产品缺陷，也不阻塞两个合法 current route；`CURRENT_NON_RPATH_FAILURE` 和 `INVALID_CONTROL`
都必须停下并修订计划。合法 route 同时冻结后续路径：

```bash
# CURRENT_CLOSURE_ALREADY_VALID route
export F_MANIFEST="$GATEA_RUN_ROOT/control-set/manifest.json"
export F_CLOSURE_ROOT="$CLOSURE_ROOT"
export F_DIAGNOSTIC_EXE="$DIAGNOSTIC_EXE"

# CONFIRMED_RPATH route：只在 Step 4 rebuild 和 manifest freeze 完成后设置
export F_MANIFEST="$GATEA_RUN_ROOT/fixed/manifest.json"
export F_CLOSURE_ROOT="$GATEA_RUN_ROOT/fixed/closure"
export F_DIAGNOSTIC_EXE="$F_CLOSURE_ROOT/lib/so101_demo_py/so101_diagnose_macos_station"
```

每次只能执行其中一组；verdict、`F_MANIFEST`、`F_CLOSURE_ROOT` 和 `F_DIAGNOSTIC_EXE` 必须一并
写入 ledger。

- [ ] **Step 4: 只在 `CONFIRMED_RPATH` route 修复 install-rpath**

`CURRENT_CLOSURE_ALREADY_VALID` route 明确跳过本步，不修改 submodule、dependency lock 或 candidate
常量。`CONFIRMED_RPATH` route 只修改 submodule CMake 的 Apple `INSTALL_RPATH`：保留
`@loader_path`，并为 merged layout 中的
`$F_CLOSURE_ROOT/lib/libmujoco_ros2_control.dylib` 增加精确
`@loader_path/../opt/mujoco_vendor/lib`。修复后用 `otool -l` 证明该 rpath，从 plugin 实际目录解析后
必须等于 `$F_CLOSURE_ROOT/opt/mujoco_vendor/lib`；不得修改 controller node、dispatcher 或
hardware interface。

先在 `test_macos_install_contract.py` 写精确 RED：copied plugin 的 LC_RPATH 必须能在 no-DYLD
environment 解析 manifest-bound vendor dylib；`test_runtime_closure.py` 拒绝 loaded image 落到 copied
prefix 之外。运行下列命令，Expected RED 只能是已由 N/P 确认的 rpath 缺口：

```bash
export RPATH_RED_INVOCATION="$GATEA_RUN_ROOT/tests/red/$(uuidgen | tr '[:upper:]' '[:lower:]')"
mkdir -p "$RPATH_RED_INVOCATION"
SECONDS=0
set +e
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_macos_install_contract.py \
  src/so101_demo_py/test/test_runtime_closure.py \
  --junitxml="$RPATH_RED_INVOCATION/junit.xml" \
  >"$RPATH_RED_INVOCATION/stdout.log" 2>"$RPATH_RED_INVOCATION/stderr.log"
test_rc=$?
set -e
printf '%s\n' "$test_rc" >"$RPATH_RED_INVOCATION/exit-code.txt"
printf '%s\n' "$SECONDS" >"$RPATH_RED_INVOCATION/elapsed-seconds.txt"
shasum -a 256 "$RPATH_RED_INVOCATION"/{junit.xml,stdout.log,stderr.log,exit-code.txt,elapsed-seconds.txt} \
  >"$RPATH_RED_INVOCATION/SHA256SUMS"
test "$test_rc" -ne 0
```

先提交 submodule，再把完整 SHA 同步到两份 dependency lock 和
`scripts/check_backend_integration.py` candidate 常量。parent commit 必须同时冻结 gitlink、locks、
candidate 常量和对应测试；不得在 parent 仍指向旧 gitlink 时构建 F。

```bash
git -C third_party/mujoco_ros2_control add -- mujoco_ros2_control/CMakeLists.txt
git -C third_party/mujoco_ros2_control diff --cached --check
git -C third_party/mujoco_ros2_control commit -m "fix(mujoco): close macOS vendor install rpath"
git add -- third_party/mujoco_ros2_control \
  src/so101_demo_py/config/mujoco/dependency-lock.yaml \
  src/so101_demo_py/config/dependency-lock.yaml \
  scripts/check_backend_integration.py \
  src/so101_demo_py/test/test_macos_install_contract.py \
  src/so101_demo_py/test/test_runtime_closure.py
git diff --cached --check
git commit -m "fix(so101): attest relocatable macOS station closure"
git ls-tree HEAD third_party/mujoco_ros2_control
git -C third_party/mujoco_ros2_control rev-parse HEAD
rg -n '^  commit:' \
  src/so101_demo_py/config/mujoco/dependency-lock.yaml \
  src/so101_demo_py/config/dependency-lock.yaml
rg -n 'CANDIDATE_COMMIT' \
  scripts/check_backend_integration.py \
  src/so101_demo_py/test/test_macos_install_contract.py
```

从 committed HEAD 重建完整 vendor + submodule + station merged closure：

```bash
export F_CLOSURE_ROOT="$GATEA_RUN_ROOT/fixed/closure"
export F_VENDOR_WORKSPACE="$GATEA_RUN_ROOT/fixed/vendor-workspace"
export F_MUJOCO_BUILD="$GATEA_RUN_ROOT/fixed/mujoco-build"
export F_MUJOCO_LOG="$GATEA_RUN_ROOT/fixed/mujoco-log"
export F_STATION_BUILD="$GATEA_RUN_ROOT/fixed/station-build"
export F_STATION_LOG="$GATEA_RUN_ROOT/fixed/station-log"
SO101_ROS_WORKSPACE=/Users/matianyi/ros2_jazzy \
SO101_ROS_UNDERLAY=/Users/matianyi/ros2_jazzy/install \
SO101_COLCON="$COLCON" SO101_PYTHON="$TEST_PYTHON" \
SO101_MUJOCO_SOURCE_ROOT="$MUJOCO_AUTHORITY" \
SO101_MUJOCO_VENDOR_WORKSPACE="$F_VENDOR_WORKSPACE" \
SO101_MUJOCO_VENDOR_INSTALL_PREFIX="$F_CLOSURE_ROOT" \
zsh "$INSTALLER" >"$GATEA_RUN_ROOT/fixed/vendor-install.stdout.log" \
  2>"$GATEA_RUN_ROOT/fixed/vendor-install.stderr.log"
git -C "$MUJOCO_AUTHORITY" rev-parse HEAD >"$GATEA_RUN_ROOT/fixed/authority-commit.txt"
git -C "$MUJOCO_AUTHORITY" status --porcelain --untracked-files=all \
  >"$GATEA_RUN_ROOT/fixed/authority-status.txt"
shasum -a 256 "$INSTALLER" "$VENDOR_PATCH" \
  >"$GATEA_RUN_ROOT/fixed/installer-patch-SHA256SUMS"
git -C "$F_VENDOR_WORKSPACE/src/mujoco" rev-parse HEAD \
  >"$GATEA_RUN_ROOT/fixed/prepared-source-commit.txt"
git -C "$F_VENDOR_WORKSPACE/src/mujoco" status --porcelain --untracked-files=all \
  >"$GATEA_RUN_ROOT/fixed/prepared-source-status.txt"
shasum -a 256 "$F_VENDOR_WORKSPACE/src/mujoco/simulate/glfw_adapter.cc" \
  >"$GATEA_RUN_ROOT/fixed/patched-source.sha256"
find "$F_CLOSURE_ROOT/opt/mujoco_vendor/lib" -type f -name 'libmujoco*.dylib' \
  -exec shasum -a 256 {} \; >"$GATEA_RUN_ROOT/fixed/vendor-dylib-SHA256SUMS"
source /Users/matianyi/ros2_jazzy/install/setup.zsh
source /Users/matianyi/ros2_jazzy/extra_ws/install/setup.zsh
source "$F_CLOSURE_ROOT/setup.zsh"
"$COLCON" --log-base "$F_MUJOCO_LOG" build \
  --base-paths third_party/mujoco_ros2_control \
  --packages-up-to mujoco_ros2_control \
  --build-base "$F_MUJOCO_BUILD" --install-base "$F_CLOSURE_ROOT" --merge-install \
  --event-handlers console_direct+
source "$F_CLOSURE_ROOT/setup.zsh"
"$COLCON" --log-base "$F_STATION_LOG" build \
  --base-paths src --packages-select so101_mujoco_support so101_demo_py \
  --build-base "$F_STATION_BUILD" --install-base "$F_CLOSURE_ROOT" --merge-install \
  --event-handlers console_direct+
source "$F_CLOSURE_ROOT/setup.zsh"
export F_DIAGNOSTIC_EXE="$F_CLOSURE_ROOT/lib/so101_demo_py/so101_diagnose_macos_station"
test -x "$F_DIAGNOSTIC_EXE"
head -n 1 "$F_DIAGNOSTIC_EXE" >"$GATEA_RUN_ROOT/fixed/diagnostic-shebang.txt"
export F_MUJOCO_ALIAS="$F_CLOSURE_ROOT/opt/mujoco_vendor/lib/libmujoco.dylib"
test "$(find "$F_CLOSURE_ROOT" -type l -print)" = "$F_MUJOCO_ALIAS"
test "$(readlink "$F_MUJOCO_ALIAS")" = "libmujoco.3.4.0.dylib"
otool -l "$F_CLOSURE_ROOT/lib/libmujoco_ros2_control.dylib" \
  >"$GATEA_RUN_ROOT/fixed/plugin-otool-l.txt"
rg -F '@loader_path/../opt/mujoco_vendor/lib' "$GATEA_RUN_ROOT/fixed/plugin-otool-l.txt"
```

生成新的 `$GATEA_RUN_ROOT/fixed/manifest.json`，递归冻结 `$F_CLOSURE_ROOT` 的真实目录、全部
regular files 和唯一 MuJoCo dylib alias，拒绝其他 symlink，并断言
`RuntimeClosureIdentity.install_root == F_CLOSURE_ROOT`。随后执行 installed Python readback：

```bash
PYTHONNOUSERSITE=1 "$TEST_PYTHON" -c '
import json, pathlib, sys
from ament_index_python.packages import get_package_prefix
import so101_demo
import so101_demo.runtime.macos_dlopen_probe as probe
root = pathlib.Path("'"$F_CLOSURE_ROOT"'").resolve()
doc = {
  "interpreter": sys.executable,
  "module_file": str(pathlib.Path(so101_demo.__file__).resolve()),
  "probe_module_file": str(pathlib.Path(probe.__file__).resolve()),
  "ament_prefix": get_package_prefix("so101_demo_py"),
}
print(json.dumps(doc, sort_keys=True))
assert pathlib.Path(doc["ament_prefix"]).resolve() == root
assert pathlib.Path(doc["module_file"]).is_relative_to(root)
assert pathlib.Path(doc["probe_module_file"]).is_relative_to(root)
assert pathlib.Path(sys.executable).resolve() == pathlib.Path("'"$TEST_PYTHON"'").resolve()
' >"$GATEA_RUN_ROOT/fixed/bootstrap-readback.json"
test "$(head -n 1 "$F_DIAGNOSTIC_EXE")" = "#!$TEST_PYTHON"
shasum -a 256 "$GATEA_RUN_ROOT/fixed/bootstrap-readback.json" \
  "$GATEA_RUN_ROOT/fixed/diagnostic-shebang.txt" \
  >"$GATEA_RUN_ROOT/fixed/bootstrap-readback.sha256"
```

GREEN 失败只能在 Task 1 内形成新的 scoped fix commit，不能 amend 已被引用的 candidate。

```bash
export RPATH_GREEN_INVOCATION="$GATEA_RUN_ROOT/tests/green/$(uuidgen | tr '[:upper:]' '[:lower:]')"
mkdir -p "$RPATH_GREEN_INVOCATION"
SECONDS=0
set +e
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_macos_dlopen_probe.py \
  src/so101_demo_py/test/test_diagnose_macos_station.py \
  src/so101_demo_py/test/test_macos_install_contract.py \
  src/so101_demo_py/test/test_runtime_closure.py \
  src/so101_demo_py/test/test_motion_stack_ready.py \
  --junitxml="$RPATH_GREEN_INVOCATION/junit.xml" \
  >"$RPATH_GREEN_INVOCATION/stdout.log" 2>"$RPATH_GREEN_INVOCATION/stderr.log"
test_rc=$?
set -e
printf '%s\n' "$test_rc" >"$RPATH_GREEN_INVOCATION/exit-code.txt"
printf '%s\n' "$SECONDS" >"$RPATH_GREEN_INVOCATION/elapsed-seconds.txt"
shasum -a 256 "$RPATH_GREEN_INVOCATION"/{junit.xml,stdout.log,stderr.log,exit-code.txt,elapsed-seconds.txt} \
  >"$RPATH_GREEN_INVOCATION/SHA256SUMS"
test "$test_rc" -eq 0
```

Expected GREEN: copied install 在 no-DYLD control 下解析 manifest-bound vendor image，全部测试通过。

- [ ] **Step 5: 验证 F no-DYLD attestation，并执行 5x FULL_RESTART**

`CONFIRMED_RPATH` route 的 F 是 Step 4 新 candidate；`CURRENT_CLOSURE_ALREADY_VALID` route 的 F 是
Step 3 的 N frozen bytes。两条 route 都必须在清除全部 `DYLD_*` 后满足：direct dlopen 成功；实际
`controller_runtime` descendant 的 PID/birth/executable 稳定，plugin/vendor loaded-image 路径和 SHA
命中同一 F manifest；station 到达 READY；READY 后 diagnostic 主动有界 shutdown；所有 owned
descendant 与 IPC residue 为零。probe/launcher image、空 images、wrong child 或 identity drift 都不能
进入 5x。

```bash
PYTHONNOUSERSITE=1 "$TEST_PYTHON" -m so101_demo.runtime.macos_dlopen_probe \
  --create-run-binding --manifest "$F_MANIFEST" --control F \
  --run-root "$GATEA_RUN_ROOT/fixed/attest" \
  --session-id "gate-a-$DISPATCH_ID-f-attest" \
  --output "$GATEA_RUN_ROOT/fixed/attest-run-binding.json"
PYTHONNOUSERSITE=1 "$TEST_PYTHON" -m so101_demo.runtime.macos_dlopen_probe \
  --manifest "$F_MANIFEST" \
  --run-binding "$GATEA_RUN_ROOT/fixed/attest-run-binding.json" \
  --control F --output "$GATEA_RUN_ROOT/fixed/dlopen.json"
"$F_DIAGNOSTIC_EXE" \
  --mode FULL_TASK_STATION \
  --control-set-manifest "$F_MANIFEST" \
  --run-binding "$GATEA_RUN_ROOT/fixed/attest-run-binding.json" --control F
```

随后为五轮分别创建新 experiment ID。每轮必须使用同一 F closure hash、fresh domain/session、唯一
run/attestation，依次越过真实 phase marker，最后得到三个 active controller、三个 MoveIt service 和
三个 action。READY 时必须先保存真实 `controller_runtime` 的新
`RuntimeProcessAttestation`，再主动有界 shutdown 并核对全部 owned descendants/IPC；persistent
launch 不会自然退出。VALID failure 中断序列；INVALID 终止批次并用新 ID 重开；既有 READY 不计数。
每轮预先写独立 binding JSON，明确 fresh `ROS_DOMAIN_ID<=232`、session、report、
`task_evidence_root=$GATEA_RUN_ROOT/fixed/full-restart-$round/evidence`、ROS_HOME/LOG/TMP paths。
执行命令固定为：

```bash
for round in 1 2 3 4 5; do
  PYTHONNOUSERSITE=1 "$TEST_PYTHON" -m so101_demo.runtime.macos_dlopen_probe \
    --create-run-binding --manifest "$F_MANIFEST" --control F \
    --run-root "$GATEA_RUN_ROOT/fixed/full-restart-$round" \
    --session-id "gate-a-$DISPATCH_ID-f-$round" \
    --output "$GATEA_RUN_ROOT/fixed/full-restart-$round/run-binding.json" || break
  "$F_DIAGNOSTIC_EXE" \
    --mode FULL_TASK_STATION \
    --control-set-manifest "$F_MANIFEST" \
    --run-binding "$GATEA_RUN_ROOT/fixed/full-restart-$round/run-binding.json" \
    --control F || break
done
```

每轮 report 必须保存 normalized semantic argv/env、expanded argv/env、launcher 与全部 descendant
identity、diagnostic interpreter/module/ament prefix、`controller_runtime` per-process images、READY
markers、shutdown escalation 和最终 residue scan。缺任一字段即 `INVALID`。

五轮全部有效后写：

```text
controller_verdict=CURRENT_CONTROLLER_PATH_OPERATIONAL
gate_a_status=CURRENT_PRODUCT_GATE_PASSED
```

- [ ] **Step 6: 提交 ledger、记录 `CP-MSC-A1`，并释放 writer**

提交本轮 N/P/F manifest SHA、三个正交 verdict、合法 route、no-DYLD attestation、5x 结果、cleanup
accounting、code/test commit 和 `CP-MSC-A1`。legacy `CP-MSC-A` 原文保持不变。

```bash
git add -- docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md
git diff --cached --check
git commit -m "docs: record current macOS product Gate A"
git status --short --branch
```

Gate A Codex 随后停止所有 task-owned 服务，确认零 residue，退出或明确记录
`writer_released_at`，此后不得再写该 worktree。把 scoped commits 交给当前 worktree 的 orchestration
owner；这里是同一 worktree 的串行交接，不做 cherry-pick，也不另建 worktree。

**STOP at `CP-MSC-A1`. Do not start Task 2.** GPT-5.6 Sol / High 先只读复核 manifests、diff、tests、
ledger、5x 和 cleanup。只有复核通过后，orchestration owner 才通知 `dst-so101-macos-closure` 接回唯一
writer 并继续 Task 2；复核不通过时仍由新的 Gate A Codex handoff 修复，不能让 `dst` 与 Codex 并写。

### Task 2: 实现不可变 selection 和 durable shared queue

**Files:**
- Create: `src/so101_demo_py/src/parallel_batch/selection.py`
- Create: `src/so101_demo_py/src/parallel_batch/queue.py`
- Create: `src/so101_demo_py/test/test_parallel_selection.py`
- Create: `src/so101_demo_py/test/test_parallel_point_queue.py`
- Modify: `src/so101_demo_py/src/parallel_batch/w2_composition.py`
- Modify: `src/so101_demo_py/test/test_macos_w2_campaign.py`

**Interfaces:**
- Consumes: Web catalog and runtime closure hash
- Produces: `FirstPassSelectionBinding`, `RetrySelectionBinding`, `DurablePointQueue`

```python
class DurablePointQueue:
    def lease_next(self, worker: WorkerIdentity) -> PointLease | None: ...
    def commit_result(self, lease: PointLease, result: CommittedResult) -> None: ...
```

- [ ] **Step 1: RED** — 覆盖 first-pass 4–20 点/四 anchors、retry 单个业务失败点、hash drift、
  两个 slot 排空 20 点、重复 lease、stale generation、crash recovery、unselected injection。

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_parallel_selection.py \
  src/so101_demo_py/test/test_parallel_point_queue.py \
  src/so101_demo_py/test/test_macos_w2_campaign.py \
  --junitxml="$RUN_ROOT/task2-red.xml"
```

Expected: 当前 first-two static assignment 使测试失败。

- [ ] **Step 2: GREEN** — `exact_w2_slots()` 只返回容量 slot；全部 selected ids 进入 fsync-backed
  queue。lease identity 固定为 campaign/batch/point/attempt/generation/worker。

- [ ] **Step 3: 提交**

```bash
git add -- src/so101_demo_py/src/parallel_batch/selection.py \
  src/so101_demo_py/src/parallel_batch/queue.py \
  src/so101_demo_py/src/parallel_batch/w2_composition.py \
  src/so101_demo_py/test/test_parallel_selection.py \
  src/so101_demo_py/test/test_parallel_point_queue.py \
  src/so101_demo_py/test/test_macos_w2_campaign.py
git diff --cached --check
git commit -m "feat(so101): bind selected points to a shared queue"
```

### Task 3: 每个 Worker lease 只执行一个点

**Files:**
- Create: `src/so101_demo_py/src/parallel_batch/single_point_input.py`
- Create: `src/so101_demo_py/test/test_single_point_input.py`
- Modify: `src/so101_demo_py/src/cli/macos_w2_campaign.py`
- Modify: `src/so101_demo_py/src/cli/macos_w2_worker.py`
- Modify: `src/so101_demo_py/src/parallel_batch/macos_w2_campaign.py`
- Modify: `src/so101_demo_py/test/test_macos_w2_campaign.py`

**Interfaces:**
- Consumes: `PointLease`, selection binding
- Produces: hash-bound `PointExecutionInput`, `PointExecutionResult`

- [ ] **Step 1: RED** — selection 包含 anchors 与 P09/P14/P20；断言所有 selected 各一次，
  unselected 为零，完整 `rgbd_task_points.yaml` 从不传给 Worker，retry 输入只含失败点。

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_single_point_input.py \
  src/so101_demo_py/test/test_macos_w2_campaign.py \
  src/so101_demo_py/test/test_parallel_batch_broker.py \
  src/so101_demo_py/test/test_mujoco_rgbd_batch_cli.py \
  --junitxml="$RUN_ROOT/task3-red.xml"
```

- [ ] **Step 2: GREEN** — 原子写单点文件并 fsync；Worker readback point/hash 后执行；broker
  request 使用同一 attempt id；station、MoveIt、物理、manifest、cleanup ownership 全部 durable
  后才提交业务 result。

- [ ] **Step 3: 提交** — scoped add 上述六个文件，`git diff --cached --check`，提交
  `feat(so101): execute one point per worker lease`。

### Task 4: 扩展 CoordinatorJournal committed watermark

**Files:**
- Modify: `src/so101_demo_py/src/parallel_batch/journal.py`
- Modify: `src/so101_demo_py/src/cli/macos_w2_campaign.py`
- Modify: `src/so101_demo_py/test/test_parallel_batch_journal.py`
- Modify: `src/so101_demo_py/test/test_macos_w2_campaign.py`

**Interfaces:**
- Produces: `CommittedWatermark`, `append_committed()`, `read_committed_prefix()`

- [ ] **Step 1: RED** — 覆盖 single writer、epoch takeover、idempotency、result fsync before
  proposal、journal fsync、watermark fsync/rename、ACK ordering、flush-before-fsync invisibility、
  watermark lag、partial tail、tamper、sequence gap、terminal append。

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_parallel_batch_journal.py \
  src/so101_demo_py/test/test_parallel_batch_crash_recovery.py \
  src/so101_demo_py/test/test_macos_w2_campaign.py \
  --junitxml="$RUN_ROOT/task4-red.xml"
```

- [ ] **Step 2: GREEN** — 保留 `read_only_replay()` strict 语义；live reader 只返回 watermark
  覆盖的 prefix。writer 退出后的多余 bytes 标记 `UNCONFIRMED_DURABILITY`，不自动 truncate/append。

- [ ] **Step 3: 提交** — scoped add 四个文件并提交
  `feat(so101): publish durable campaign watermarks`。

### Task 5: 建立唯一 reducer 和事务化 projection

**Files:**
- Create: `src/so101_teleop/so101_teleop/expert_validation/projection_source.py`
- Create: `src/so101_teleop/so101_teleop/expert_validation/reducer.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_reducer.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/coordinator_events.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/models.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/store.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/production.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_coordinator_events.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_store.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_production_projection.py`
- Modify: `src/so101_teleop/CMakeLists.txt`

**Interfaces:**
- Produces: `ProjectionSource.read_after()`, `CanonicalCampaignReducer.apply()`,
  `SupervisorStore.accept_projection_batch()`

- [ ] **Step 1: RED** — source 不能 merge `payload.delta`；验证四条正交状态轴、result-derived
  terminal、INVALID 不映射 FAILED、illegal append、identity drift。注入 reducer 后/cursor 前失败，
  要求全事务回滚；重启不重复统计 attempt。

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_teleop/test/teleop/test_expert_validation_coordinator_events.py \
  src/so101_teleop/test/teleop/test_expert_validation_reducer.py \
  src/so101_teleop/test/teleop/test_expert_validation_store.py \
  src/so101_teleop/test/teleop/test_expert_validation_production_projection.py \
  --junitxml="$RUN_ROOT/task5-red.xml"
```

- [ ] **Step 2: GREEN** — idempotency、reducer state、attempt、accepted cursor 在一个 SQLite
  transaction 更新。React/OpenAPI 仍只消费服务状态。

- [ ] **Step 3: 提交** — scoped add 上述文件并提交
  `feat(teleop): reduce committed campaign events transactionally`。

### Task 6: 持久化真实 owner tree 和 crash cleanup

**Files:**
- Create: `src/so101_teleop/so101_teleop/expert_validation/owner_tree.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_owner_tree.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/models.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/store.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/process_owner.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/supervisor.py`
- Modify: `src/so101_demo_py/src/cli/macos_service_campaign.py`
- Modify: `src/so101_demo_py/src/cli/macos_w2_worker.py`
- Modify: `src/so101_demo_py/src/parallel_batch/campaign_supervisor.py`
- Modify: `src/so101_demo_py/src/runtime/task_stack.py`
- Modify: `src/so101_demo_py/test/test_campaign_supervisor.py`
- Modify: `src/so101_demo_py/test/test_task_stack.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_process_owner.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_operator_recovery.py`
- Modify: `src/so101_teleop/CMakeLists.txt`

**Interfaces:**
- Produces: `OwnerIntent`, `ConfirmedOwnerProcess`, `OwnerTreeRecovery.recover_leaf_first()`

- [ ] **Step 1: RED** — adapter/campaign/worker/station `SIGKILL`、独立 session、PID reuse、
  unresolved intent、duplicate reaper、wrong generation receipt、station outside Worker PGID、
  crashes before/after `Popen` 与 confirmation。

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_campaign_supervisor.py \
  src/so101_demo_py/test/test_task_stack.py \
  src/so101_teleop/test/teleop/test_expert_validation_owner_tree.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py \
  src/so101_teleop/test/teleop/test_expert_validation_operator_recovery.py \
  --junitxml="$RUN_ROOT/task6-red.xml"
```

- [ ] **Step 2: GREEN** — 每个真实 spawn 先 intent，后 readback confirmation；reaper 按
  station -> worker -> broker/campaign -> adapter 回收。未知 identity 不 signal，fence 保留。

- [ ] **Step 3: 提交与 checkpoint** — scoped add，提交
  `feat(teleop): recover macOS ownership leaf first`。Sol/high 在 `CP-MSC-02` 复核 Tasks 2–6。

### Task 7: 新增 v5/v6、W1 composition 和 per-spawn StartGuard

**Files:**
- Create: `src/so101_demo_py/config/mujoco/parallel_batch_v5_macos_mps_w1_retry.yaml`
- Create: `src/so101_demo_py/config/mujoco/parallel_batch_v6_macos_mps_w1_first_pass.yaml`
- Create: `src/so101_demo_py/src/parallel_batch/w1_composition.py`
- Create: `src/so101_demo_py/src/cli/macos_n1_first_pass.py`
- Create: `src/so101_demo_py/src/cli/macos_n1_retry.py`
- Create: `src/so101_demo_py/test/test_macos_w1_composition.py`
- Create: `src/so101_demo_py/test/test_macos_n1_cli.py`
- Modify: `src/so101_demo_py/src/parallel_batch/contracts.py`
- Modify: `src/so101_demo_py/src/parallel_batch/start_guard.py`
- Modify: `src/so101_demo_py/src/parallel_batch/start_guard_probe.py`
- Modify: `src/so101_demo_py/src/parallel_batch/w2_composition.py`
- Modify: `src/so101_demo_py/src/cli/macos_service_campaign.py`
- Modify: `src/so101_demo_py/src/cli/macos_w2_campaign.py`
- Modify: `src/so101_demo_py/src/cli/macos_w2_worker.py`
- Modify: `src/so101_demo_py/src/parallel_batch/campaign_supervisor.py`
- Modify: `src/so101_demo_py/setup.py`
- Modify: `src/so101_demo_py/test/test_parallel_batch_contracts.py`
- Modify: `src/so101_demo_py/test/test_parallel_start_guard_composition.py`
- Modify: `src/so101_demo_py/test/test_parallel_start_guard_probe.py`
- Modify: `src/so101_demo_py/test/test_macos_w2_campaign.py`
- Modify: `src/so101_demo_py/test/test_macos_install_contract.py`

**Interfaces:**
- Produces: `ParallelRuntimeConfigV5`, `ParallelRuntimeConfigV6`, `compose_w1_first_pass()`,
  `compose_w1_retry()`, exhaustive typed dispatch, fresh `GuardScope` per spawn epoch

- [ ] **Step 1: RED profile matrix** — freeze v4 bytes/SHA；v5 只接受 W1 retry，v6 只接受 W1
  first-pass；所有 cross-profile、N>2、adaptive、CPU fallback 和 point-count inference 拒绝。

- [ ] **Step 2: RED StartGuard spawn semantics** — campaign 与每个 Worker 使用不同 fresh epoch；
  旧 preflight result 不可重用。RAM/MPS FAIL 和 probe/identity error 不调用 `Popen`；CPU WARN 仍
  调用一次；同一 service 不可同时启动 W1/W2。public W2 CLI 即使已存在 PASS/FAIL
  `start-guard.json` 也必须 fresh probe；旧 epoch、不同 owner 或篡改文件都不能准入。guard 阶段
  到 broker 阶段的 `exec` 只接受本次进程创建的 inherited pipe 中一次性 result，消费后关闭；
  磁盘 JSON 只供审计。测试同时证明 broker 阶段开始前已通过 `exec` 清除 guard 阶段的 torch 导入。

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_parallel_batch_contracts.py \
  src/so101_demo_py/test/test_macos_w1_composition.py \
  src/so101_demo_py/test/test_macos_n1_cli.py \
  src/so101_demo_py/test/test_parallel_start_guard_composition.py \
  src/so101_demo_py/test/test_parallel_start_guard_probe.py \
  src/so101_demo_py/test/test_macos_w2_campaign.py \
  src/so101_demo_py/test/test_macos_install_contract.py \
  --junitxml="$RUN_ROOT/task7-red.xml"
```

- [ ] **Step 3: GREEN** — 共用 W1 primitive 只创建一套 slot/Worker/domain。把 StartGuard 源码中
  “仅 schema v4” 的限制收窄为“所有已批准的 Darwin/MPS v4/v5/v6 profile”，但保持 Linux v3
  不能携带 MPS headroom；不改变现有 probe、阈值和判定算法。扩展真实
  `load_execution_config_for_schema()` 和 host validation，使安装版 v5/v6 YAML 能沿 MPS 路径加载，
  且 W1 composition 复用这条入口。adapter 的 dispatch
  key 是 schema/profile/batch_kind/worker_count，不提供 generic `--batch-kind` fallback。guard
  绑定真实 owner birth 与 epoch。

- [ ] **Step 4: 提交** — scoped add 上述文件并提交
  `feat(so101): add closed macOS W1 profiles and spawn guards`。

### Task 8: 固定 macOS W1/W2 support matrix

**Files:**
- Modify: `src/so101_teleop/so101_teleop/expert_validation/preflight.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/api.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/production.py`
- Modify: `src/so101_teleop/so101_teleop/unified/app.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_api.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_preflight.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_start_guard.py`
- Modify: `src/so101_teleop/test/teleop/test_unified_guard_document.py`

**Interfaces:**
- Produces: platform-bound capabilities with W1/W2 only; stable `UNSUPPORTED_ON_MACOS` reasons

- [ ] **Step 1: RED** — macOS capabilities 只允许 `SEQUENTIAL/W1` 和 `PARALLEL/W2`；N3–N8
  不可选且没有 profile/qualification hash；API/preflight 对 N>2 与 ADAPTIVE 拒绝；点数变化不改
  worker profile。分别从安装版 v4/v5/v6 YAML 发起 service preflight，要求三者都使用实际
  profile/config hash、W1/W2 scope 和 MPS probe，且不进入 CUDA/NVML；Linux v3/v4 fixture 保持
  原语义。`_LazyStartGuard` 可按 `(profile, config_sha256, accelerator, selector)` 缓存 composition，
  但每个 request/spawn epoch 都必须 fresh probe，不能缓存 verdict。

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_teleop/test/teleop/test_expert_validation_api.py \
  src/so101_teleop/test/teleop/test_expert_validation_preflight.py \
  src/so101_teleop/test/teleop/test_expert_validation_start_guard.py \
  src/so101_teleop/test/teleop/test_unified_guard_document.py \
  --junitxml="$RUN_ROOT/task8-red.xml"
```

- [ ] **Step 2: GREEN** — `_HostResourceProbe` 继续只调用 StartGuard；删除 macOS capabilities
  对 budget/qualification source 的依赖，不改变 Linux adapter。StartGuard policy/status 仍可展示，
  文案明确它不是资格证明。

- [ ] **Step 3: 提交** — scoped add 八个文件并提交
  `feat(teleop): limit macOS validation to W1 and W2`。

### Task 9: 候选/生产执行 context 与原子 retry admission

**Files:**
- Create: `src/so101_teleop/so101_teleop/expert_validation/execution_context.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_execution_context.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/api.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/models.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/store.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/statistics.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/supervisor.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/production.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/service.py`
- Modify (generated): `src/so101_teleop/so101_teleop/expert_validation_openapi.json`
- Modify (generated): `src/so101_teleop/web/src/api/expert-validation-schema.d.ts`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_store.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_statistics.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_supervisor.py`
- Modify: `src/so101_teleop/CMakeLists.txt`

**Interfaces:**
- Produces: `CandidateExecutionContext`, `ProductionExecutionContext`, `RetryStartRequest`,
  `SupervisorStore.admit_retry()`

```python
class SupervisorStore:
    def admit_retry(
        self,
        *,
        request: RetryStartRequest,
        context: CandidateExecutionContext | ProductionExecutionContext,
        spawn_intent: OwnerIntent,
    ) -> RetrySelectionBinding: ...
```

- [ ] **Step 1: RED** — context 类型混用、过期、replay、profile/config/closure/N/batch/root/
  lease drift；非业务失败；原 batch 非 terminal-clean；active/unknown owner；fence；重复 command；
  transaction 后 spawn fail。

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_teleop/test/teleop/test_expert_validation_execution_context.py \
  src/so101_teleop/test/teleop/test_expert_validation_store.py \
  src/so101_teleop/test/teleop/test_expert_validation_statistics.py \
  src/so101_teleop/test/teleop/test_expert_validation_supervisor.py \
  --junitxml="$RUN_ROOT/task9-red.xml"
```

- [ ] **Step 2: GREEN** — context 不含预算/资格/promotion 字段。一个 transaction 内消费
  command、验证 result/lease/cleanup/fence、创建 retry binding、写 spawn intent。retry 只追加历史。

- [ ] **Step 3: OpenAPI 生成与提交**

```bash
$TEST_PYTHON -m so101_teleop.openapi_export --validation \
  src/so101_teleop/so101_teleop/expert_validation_openapi.json
cd src/so101_teleop/web
bun run generate:api:validation
cd ../../../
```

stage 本 task 列出的产品、测试、生成 OpenAPI/types，`git diff --cached --check`，提交
`feat(teleop): authorize one-time macOS retries`。

STOP at `CP-MSC-03`；Sol/high 复核 v4/v5/v6、W1/W2 matrix、fresh guard 和 retry atomicity。

### Task 10: 更新 Web 为 W1/W2，并补浏览器合同

**Files:**
- Modify: `src/so101_teleop/web/src/components/expert-validation/campaign-setup.tsx`
- Modify: `src/so101_teleop/web/src/components/expert-validation/components.test.tsx`
- Modify: `src/so101_teleop/web/src/expert-validation-app.tsx`
- Modify: `src/so101_teleop/web/src/expert-validation-app.test.tsx`
- Modify: `src/so101_teleop/web/src/api/live-evidence.test.ts`
- Create: `src/so101_teleop/web/src/api/campaign-live-evidence.test.ts`
- Modify: `src/so101_teleop/web/e2e/expert-validation/assertions/live-evidence.ts`
- Modify: `src/so101_teleop/web/e2e/expert-validation/live-sim/02-parallel.spec.ts`
- Modify: `src/so101_teleop/web/e2e/expert-validation/live-sim/04-start-guard.spec.ts`
- Modify: `src/so101_teleop/web/e2e/expert-validation/live-sim/06-fixed-n-execution.spec.ts`
- Modify: `src/so101_teleop/web/e2e/expert-validation/live-sim/07-retry-full-restart.spec.ts`

**Interfaces:**
- Consumes: platform capabilities、StartGuard status、canonical campaign projection
- Produces: W1/W2-only selector、N>2 disabled reasons、W2/W1/retry evidence assertions

- [ ] **Step 1: RED** — macOS UI 只可选 W1/W2；N3–N8 显示
  `UNSUPPORTED_ON_MACOS`；不读取 qualification view 决定可选性；点数不改变 profile；StartGuard
  RAM/MPS FAIL 与 CPU WARN 文案正确。

```bash
cd src/so101_teleop/web
bun run test -- src/components/expert-validation/components.test.tsx
bun run test -- src/expert-validation-app.test.tsx
bun run test -- src/api/live-evidence.test.ts
bun run test -- src/api/campaign-live-evidence.test.ts
```

- [ ] **Step 2: GREEN** — UI 只依据 capabilities support matrix 和 preflight guard；不实现平台
  reducer。W2、W1、retry assertions 校验 selected-only、sequence/watermark、物理证据和 cleanup。

- [ ] **Step 3: Web gate 与提交**

```bash
bunx tsc -b --pretty false
bun run test
bun run build
cd ../../../
```

stage 上述十一个文件，`git diff --cached --check`，提交
`feat(web): expose macOS W1 and W2 execution only`。

### Task 11: Offline package gate 与候选 live gate

**Files:**
- Modify: `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md`
- Evidence only: registered evidence root

**Interfaces:**
- Consumes: frozen copied install and one-time `CandidateExecutionContext`
- Produces: offline gate evidence、bounded W2/W1/retry candidate evidence、`CP-MSC-04`

- [ ] **Step 1: 冻结候选 bytes** — 记录 HEAD/submodule、copied install inventory、v4/v5/v6
  hash、catalog/model/parser/reducer/StartGuard bytes 和 executable origins。之后 product edit 使本批
  live evidence 失效。

- [ ] **Step 2: 运行 package gate** — 定向测试之后运行以下精确命令。普通 Python gate 只收集
  `test/`，不会进入 `benchmark_test/`。保存非零 collection、JUnit/CTest、exit code、elapsed 和
  import origin。

```bash
$TEST_PYTHON -m pytest -p no:cacheprovider src/so101_demo_py/test -q \
  --junitxml="$RUN_ROOT/task11-so101-demo-py.xml"
$TEST_PYTHON -m pytest -p no:cacheprovider src/so101_teleop/test/teleop -q \
  --junitxml="$RUN_ROOT/task11-so101-teleop.xml"
colcon test --packages-select so101_teleop --event-handlers console_direct+
colcon test-result --verbose
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_copied_installed_entrypoint.py \
  src/so101_demo_py/test/test_macos_install_contract.py \
  --junitxml="$RUN_ROOT/task11-copied-install.xml"
cd src/so101_teleop/web
bunx tsc -b --pretty false
bun run test
bun run build
cd ../../../
```

- [ ] **Step 3: 候选 W2** — 一次性 candidate context，v4，包含非前两点的 4–20 点 selection。
  要求两个 Worker/station，全部 selected 各一次，unselected 零，StartGuard campaign+两 Worker
  fresh，journal/projection/物理/cleanup 一致。

- [ ] **Step 4: 候选 W1 first-pass** — v6、一个 Worker、同一完整 selection 顺序执行；fresh
  campaign/Worker guard；无 retry 语义。

- [ ] **Step 5: 候选 retry** — 先以 fault injection 验证拒绝分类，且不计业务成功。正式候选
  retry 必须使用一个 terminal-clean 的真实业务 `FAILED` point、v5、fresh FULL_RESTART，只执行
  指定点一次。

- [ ] **Step 6: checkpoint** — 任何 guard FAIL、unknown owner、projection mismatch、物理证据
  不完整或 cleanup residue 都停止，不自动循环。Sol/high 审查 `CP-MSC-04`。

### Task 12: 安装版 production + fresh Chrome 验收

**Files:**
- Modify: `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md`
- Evidence only: registered evidence root

**Interfaces:**
- Consumes: copied install、`ProductionExecutionContext`、exclusive control lease
- Produces: fresh Chrome W2/W1/retry acceptance、`CP-MSC-05`

- [ ] **Step 1: 独占窗口 preflight** — 回读 service/port/lease/owner/process；foreign service
  存在则停止，不 kill。production context 必须绑定当前 copied install、profile/config、batch、
  service session、lease generation、owner generation、command 和 expiry。

- [ ] **Step 2: W2 first-pass** — fresh Chrome profile 发起 v4 W2，校验 API/WebSocket、两 Worker、
  selected-only attempts、controller/joint/TF、MuJoCo pose/contact/release、MoveIt shadow/world、
  journal/watermark、evidence manifest 和 exact cleanup。

- [ ] **Step 3: W1 first-pass** — fresh Chrome 发起 v6 W1，校验一个 Worker 顺序执行，点数不
  改 profile，业务/物理/projection/cleanup 一致。

- [ ] **Step 4: W1 retry** — 从当前 production first-pass 中选择 terminal-clean 真实业务
  `FAILED`，使用新 command/lease-bound context 发起 v5 retry；只有该点执行一次，first-pass
  result/statistics 不变。

- [ ] **Step 5: Playwright projects**

```bash
cd src/so101_teleop/web
test "$SO101_ENABLE_LIVE_SIM_E2E" = "1"
test -n "$SO101_LIVE_SIM_HOST"
test -n "$SO101_E2E_EVIDENCE_ROOT"
test -n "$SO101_E2E_INSTALL_PREFIX"
test -n "$SO101_LIVE_SERVICE_BASE_URL"
test -n "$SO101_LIVE_SERVICE_STATE_ROOT"
test -f "$SO101_UNIFIED_LIVE_AUTHORIZATION"
test -x "$SO101_E2E_PYTHON"
test -f "$SO101_FUNCTIONAL_MANIFEST"
test -x "$SO101_PLAYWRIGHT_CHROME"
bun run test:e2e:live-sim --project parallel-resource
bun run test:e2e:live-sim --project fixed-n-execution
bun run test:e2e:live-sim --project retry-full-restart
cd ../../../
```

环境文件必须绑定当前服务 PID/birth、lease、context、deadline 与 evidence root；变量存在本身
不授予权限。Expected: 三个 project PASS，fresh browser 与 raw evidence 同 run identity。

- [ ] **Step 6: checkpoint** — 记录 `CP-MSC-05`，再次读回 task-owned process、ROS nodes、
  broker、IPC、ports 和 cleanup receipt；foreign process 保留并列出。

### Task 13: 最终 package gate、guide、独立审查和本地交接

**Files:**
- Modify: `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md`
- Create: `docs/guides/so101-macos-service-campaign-closure.md`

**Interfaces:**
- Consumes: all RED/GREEN/package/live evidence
- Produces: `CP-MSC-FINAL`、operator guide、scoped local commit；无发布

- [ ] **Step 1: 最终 gate** — 使用新的 JUnit 文件名重跑完整静态 gate，并读取 HEAD/submodule、
  closure、v4/v5/v6、owner tree、guard、journal、IPC 和 residue。

```bash
$TEST_PYTHON -m pytest -p no:cacheprovider src/so101_demo_py/test -q \
  --junitxml="$RUN_ROOT/task13-so101-demo-py.xml"
$TEST_PYTHON -m pytest -p no:cacheprovider src/so101_teleop/test/teleop -q \
  --junitxml="$RUN_ROOT/task13-so101-teleop.xml"
colcon test --packages-select so101_teleop --event-handlers console_direct+
colcon test-result --verbose
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_copied_installed_entrypoint.py \
  src/so101_demo_py/test/test_macos_install_contract.py \
  --junitxml="$RUN_ROOT/task13-copied-install.xml"
cd src/so101_teleop/web
bunx tsc -b --pretty false
bun run test
bun run build
cd ../../../
```

- [ ] **Step 2: Sol/high 结果审查** — 对照设计完成定义；finding 返回 owning task，受影响 live
  证据失效。审查报告必须写明没有 resource qualification/capacity certification。

- [ ] **Step 3: ledger accounting** — 分别列 retained、archived 和 deletion candidates；不移动、
  不删除。任何未通过层写出下一条精确命令。

- [ ] **Step 4: Sol/high 编写 guide** — 使用 `$humanizer-zh`，记录 v4-W2、v6-W1、v5-retry
  选择，StartGuard 语义，N>2 拒绝，lease/context 前置，证据路径和恢复 checkpoint。明确
  `so101_measure_parallel_resources` 仍 retired，且系统没有 macOS 容量资格流程。

- [ ] **Step 5: Astra/high 独立终审** — 审查 scoped code、设计、计划、guide、ledger 和 production
  evidence。P0/P1/P2 finding 返回 owning task；未通过前不得标记 FINAL PASS。

- [ ] **Step 6: 本地提交**

```bash
git add -- docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md \
  docs/guides/so101-macos-service-campaign-closure.md
git diff --cached --check
git commit -m "docs: record macOS W1 W2 service closure"
```

不 push、不 merge。最终交接报告 branch、local HEAD、证据分类和未发布状态。

## Checkpoints

| Checkpoint | 必须满足 | 不满足时 |
| --- | --- | --- |
| legacy `CP-MSC-A` | 只作恢复锚点；结论 `UNCONFIRMED` | 不得解释为 PASS |
| `CP-MSC-A1` | writer 已串行接管并释放；legacy 归因独立；`CONFIRMED_RPATH` 或 `CURRENT_CLOSURE_ALREADY_VALID` route 完成；F merged closure 完整 tree、authority/vendor/plugin/Python/diagnostic provenance、no-DYLD direct dlopen 和 station 5/5 均有效；每轮真实 `controller_runtime` descendant 的 PID/birth/executable/plugin/vendor path+SHA、主动有界 shutdown 和 cleanup 通过；`CURRENT_PRODUCT_GATE_PASSED` | 停止，不进入 Task 2；先修正 control/current failure 或补齐 Sol/high 复核 |
| `CP-MSC-02` | selection/queue/single-point/watermark/reducer/owner tree 离线通过 | 返回 Tasks 2–6 |
| `CP-MSC-03` | v4 frozen；v5/v6 closed；W1/W2 only；fresh guard；retry atomic | 返回 Tasks 7–9 |
| `CP-MSC-04` | package gate 和 bounded candidate W2/W1/retry 有效且无残留 | 不进 production Chrome |
| `CP-MSC-05` | fresh Chrome W2/W1/retry 与 raw/physical/cleanup 一致 | 返回 owning task |
| `CP-MSC-FINAL` | Sol/high 与 Astra/high 审查通过，guide/ledger 完整 | 只报告 PARTIAL |

## 计划自查

- 设计 §5 对应 Task 1，永久保留 legacy `CP-MSC-A=UNCONFIRMED`，并以三个正交 verdict、固定
  N/P/F control set、task-owned merged closure、semantic contract/typed RunBinding、direct dlopen、
  真实 controller descendant 的 per-process loaded-image path/SHA、no-DYLD F 和 5x readiness 关闭当前产品 Gate；
  `LEGACY_PROVENANCE_UNRECOVERABLE` 不会被误判成产品缺陷。
- Task 1 固定复用当前 mac-mini worktree、branch 和唯一 evidence root，只创建
  `gate-a-resolution/$DISPATCH_ID/`；Codex 与 dst 串行交接 writer，`CP-MSC-A1` 后先停下接受
  Sol/high 复核，未经通知不得进入 Task 2。
- 设计 §6–8 对应 Tasks 2、3、7、8；v4/v5/v6、W1/W2、point/profile 分离完整。
- 设计 §7 对应 Tasks 7–8；只复用现有 StartGuard，没有新 sampler/watchdog/容量证明。
- 设计 §9 对应 Tasks 4–5；committed watermark、唯一 reducer 和 cursor transaction 有明确测试。
- 设计 §10 对应 Task 9；candidate/production execution context 不含预算授权，retry 保留一次性
  command/lease 与真实 FAILED/terminal-clean 门禁。
- 设计 §11 对应 Task 6；真实 spawn intent、PID/birth、leaf-first cleanup 和 fence 均覆盖。
- fresh Chrome W2/W1/retry 对应 Tasks 10–12；最终声明边界由 Task 13 固定。
- 计划没有已删除资源子系统的 task、文件、命令、测试或 checkpoint，也不修改旧预算文档。
- 文件路径、接口、测试命令、预期结果和 scoped commits 均已给出；没有占位步骤或不确定路径，
  也不会自动 push/merge。
