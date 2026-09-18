# SO-101 单 Web 服务与 shadcn Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: `superpowers:executing-plans`（或同名项目可用技能）。项目 `AGENTS.md` 覆盖通用执行建议：仅由 DeepSeek Harness TUI 的 `dst` 在独立 `tmux` 内 inline、逐任务执行本计划；不能使用 Codex、Kimi 或 subagent 替代实施 executor。执行监控与结果审查为 GPT-5.6 Sol / High，设计和计划独立审查为 GPT-6 Astra / High。以下 checkbox 是未来执行记录，本轮不执行。

Goal：一个 HTTP/WebSocket 服务同时提供 Teleop、Expert Validation 和兼容 Tasks，采用批准的 preset 与布局，保持精确控制权、安全取消和证据边界。

Architecture：单 Web factory 组合纯业务 routers、实例 authority、持久全局 arbiter 与独立安全 lane。ROS 在非 Web child 中，通过封闭 IPC 与精确 owner 身份连接；两个业务域独立 readiness/lease，所有运行 mutation 全局互斥。前端根 providers 保持跨页面订阅，业务组件消费权威投影。

Tech Stack：Python/FastAPI/Pydantic 2、SQLite/flock、ROS 2 Jazzy、React 18/TypeScript/Vite、Bun、shadcn maia/Radix、Vitest、Playwright/system Chrome、ament_cmake/CTest。

Spec：[已批准设计](../specs/2026-09-18-so101-unified-webapp-shadcn-design.md)，SHA256 `4e11f3a385e8d078523ee3c3b3b11d2ec372215188cfbdabdea824c35dd54fa1`。其本地文档提交 `6afd834f02ea537dcad8d65e282a8491f6c6e830` 不是产品 main。

## 全局约束和阶段权限

源码参考基线是 publication tree `84620fc0529779a27c6985f8717d78f0386e0135`；编写时路径为 `/private/tmp/so101-doc-publication.R3yXD0aj/repo`。原 `587b` 源码旧，不在其上实施或误称它是 main。执行前重新核对 main、预算任务已批准接口及 source/install/runtime，不覆盖或 rebase 其他任务工作树。

本轮只写计划及独立审查，不能代码修改、测试、安装、启动/停止服务、远端写入、commit/push。计划中的 commit 命令仅在用户后续明确批准 Stage A 实施时运行；普通 push/合并需要另行授权，禁止 force、`gh`、宽泛 staging、证据删除与全局配置修改。

| 阶段 | 内容 | 额外授权门控 |
| --- | --- | --- |
| A | Tasks 0–11 的代码、fake/contract 测试、隔离构建和离线安装测试 | 用户批准本计划实施；仅自己的工作树和 test-owned helper，不触碰已有服务/仿真。 |
| B | 新 R 的真实测量与预算资格 | 独立 owned 测量窗口、预算任务最终通过接口；本计划不批准 promotion。 |
| C | Task 12 的服务替换、owned 仿真及 live Chrome/物理验收 | fresh owner/checkpoint、运行/部署窗口和已批准 profile；真实硬件仍单独授权。 |

当前规划任务唯一 root 是 `/tmp/so101-debug-unified-webapp-design-20260918/`，账本 `docs/experiments/so101-unified-webapp-design-experiment-ledger.md` 由主协作者单写。后续实施是独立 task：先在其 ledger 登记唯一执行 root。ai-station 的执行 root 必须位于 `/data/work/so101-evidence/`，才允许 fsync-heavy pytest/colcon；不得把设计 `/tmp` 和新 `/data` 根混作同一执行任务。本轮不创建执行根。

所有 N 仍按 provider 判定；未知/未合格/新 R 未 promotion 不能运行真实批次，不降低 N、不改 ADAPTIVE、不模拟大 K。点数 `4..20` 含四固定点；PARALLEL `2..8`，SEQUENTIAL 1，人工失败 retry 独立 FULL_RESTART 单点 N1。保留所有业务/infra retry、timeout、lease、epoch、cleanup、v1 历史只读和原哈希。

## 文件责任与任务依赖

下文 `P` 表示 `src/so101_teleop/so101_teleop/`，`W` 表示 `src/so101_teleop/web/`。Files行中同一组省略前缀的文件继承该组首个完整目录；不同根均重新给出路径。实际Git staging用下方精确目录/文件清单，不stage整个工作树。

| 单元 | 责任 | 依赖 |
| --- | --- | --- |
| `P/unified/contracts.py`、`intent_store.py`、`arbiter.py` | 纯类型、持久 intent/reservation、全局排他 | 0 → 1 |
| `P/unified/instances.py` | 服务器 instance proof/channel/controller generation | 1 → 2 |
| `P/unified/safety.py`、`goals.py` | 有界独立取消 lane、精确 action registry | 1、2 → 3 |
| `P/unified/ipc.py`、`bridge.py`、`ros_child.py` | 封闭 IPC、owned 非 Web ROS child 与 watchdog | 1、3 → 4 |
| `P/unified/parents.py`、`admission.py` | 复合操作与所有域内部入口仲裁 | 1–4 → 5 |
| `P/unified/app.py`、`lifecycle.py`、`ports.py` | 单 factory/routers/health/安全关闭/入口 | 1–5 → 6 |
| `W/src/state/domain-runtime.ts`、`runtime-provider.tsx` | 根级实例/lease/订阅与恢复只读投影 | 2、6 → 7 |
| 主题 primitives 与两页业务组件 | 冻结 preset smart merge、保留控制行为 | 7 → 8 → 9 |
| `P/unified/budget_adapter.py` | 消费最终预算接口，失败关闭 | 6、独立预算接口 gate → 10 |
| CMake/installed launcher/Chrome fixtures | 完整构建、增量依赖和 L2 故障验收 | 0–10 → 11 |
| live fixture code / guide与live运行 | 12A是离线fixture代码；12B/C是授权运行 | 0–10 → 12A → 11 → 独立 B/promotion → 12B/C |

每个任务按 RED → 最小实现 → GREEN → Sol 结果检查 → scoped commit → checkpoint 顺序。GREEN 后新增追溯测试仍先证明失败，再实现；不通过不能写 PASS。每个任务给出的 commit 列表排除 ledger、旧 guide/proposal 和别的任务文件。任务 checkpoint 由执行 task 的指定单写者追加，不回写本轮设计 ledger。

执行次序明确为Tasks 0–10 → Task12A（仅fixture/launch代码与fake测试）→ Task11完整configure/安装门控 → Task12B/C（另授权的测量、live及guide）。12A不依赖Task11的构建或任何运行资格；Task11的16项注册因此都已有文件。代码冻结点在12A与11全部代码/测试审查通过之后，之后只追加证据/metadata/guide，不补执行代码。

### Task 0：建立精确执行环境和记录门控

Files：Create `src/so101_teleop/test/e2e/record_gate.py`、`src/so101_teleop/test/test_unified_gate.py`；Modify `src/so101_teleop/CMakeLists.txt`（注册 `test_unified_gate`）。

Interfaces：新增 `GatePolicy(execution_host: str, task_root: Path, require_ai_station_nvme: bool)`与`run_gate(*, root: Path, python: Path, argv: list[str], policy: GatePolicy) -> int`；每次调用创建此前不存在的 `gates/<uuid>/`，保存 argv、TEMP proof、stdout/stderr、elapsed、exit。操作者登记host policy JSON及SHA256，dispatch父shell冻结`SO101_GATE_POLICY`和`SO101_GATE_POLICY_SHA256`；CLI只读并验证该对象hash、实际`socket.gethostname()`及registered root，不提供host/NVMe覆盖参数。被测子命令只能继承policy引用，不能修改父shell冻结值；改policy bytes使下次gate失败。root、精确Python与Bun均由Task0核验，不从旧PID/profile或prototype Node26推断。

- [ ] 操作者在 dispatch 前创建 `codex/so101-unified-webapp` 独立 worktree，记录 branch/remotes/submodule/status 与 preserved processes，verify `command -v dst`、安装版本/help，再在新 tmux 启动 `dst`，fresh TUI 回读实际接收完整任务。不把 Enter/echo 当提交，不在 Task 0 内启动第二个 dst。继承必要远端额外 AGENTS，只追加模型选择规则，不覆盖整份。不可用则停止报告。
- [ ] 进入执行 worktree 后记录 `pwd`、HEAD、dirty paths、`command -v bun`、`bun --version`、受支持 Node 的位置和版本；Node 必须 `>=24.18.1 <25`，不使用原型 Node26。确定 `TEST_PYTHON` 为实际测试解释器绝对路径，先验证 Python 3.12、Pydantic major 2、pytest/FastAPI/uvicorn导入；缺少时阻塞，不偷偷换 Python或装依赖。source ROS/underlay 后追加 Pydantic2所在 site，而非替换 PYTHONPATH；分别证明 source 测试与 installed 测试的 module origins。
- [ ] 完成已登记 `SO101_TASK_ROOT` 和环境变量后，先写 RED：

```python
from pathlib import Path
import json, os, sys
import importlib.util
spec = importlib.util.spec_from_file_location(
    "so101_teleop_gate", Path(__file__).parents[1] / "test/e2e/record_gate.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
run_gate = module.run_gate
GatePolicy = module.GatePolicy

def test_gate_proves_exact_python_temp_and_retains_nonzero(tmp_path):
    rc = run_gate(root=tmp_path, python=Path(sys.executable),
                  argv=[sys.executable, "-c", "raise SystemExit(7)"],
                  policy=GatePolicy("unit-host", tmp_path, False))
    record = next((tmp_path / "gates").glob("*/result.json"))
    data = json.loads(record.read_text())
    assert rc == data["exit_code"] == 7
    assert Path(data["tempfile_dir"]).is_relative_to(record.parent)
    assert data["elapsed_seconds"] >= 0
    assert (record.parent / "stderr.txt").exists()
```

上述测试直接装载source脚本，不添加产品包；unit API注入policy不授予实际运行authority。ai-station的tmp_path继承已登记NVMe scratch，其他Linux/macOS继承其registered root；未设置TEMP先拒绝测试，不把错误root当业务RED。首次RED用当前精确Python和唯一scratch运行 `-m pytest -p no:cacheprovider src/so101_teleop/test/test_unified_gate.py -q`，期望脚本缺失；没有helper之前也须证明 `tempfile.gettempdir()`。

- [ ] 最小记录核心如下；CLI用 argparse 必填 `--root`、`--python` 与 `argparse.REMAINDER`，去掉分隔符 `--` 后调用此函数：

```python
from pathlib import Path
from dataclasses import dataclass

@dataclass(frozen=True)
class GatePolicy:
    execution_host: str
    task_root: Path
    require_ai_station_nvme: bool

def run_gate(*, root, python, argv, policy):
    import json, os, subprocess, time, uuid
    root = root.resolve(strict=True)
    if root != policy.task_root.resolve(strict=True):
        raise RuntimeError("REGISTERED_ROOT_MISMATCH")
    if policy.require_ai_station_nvme and not root.is_relative_to(Path("/data/work/so101-evidence")):
        raise RuntimeError("REGISTERED_NVME_ROOT_REQUIRED")
    run = root / "gates" / uuid.uuid4().hex
    run.mkdir(parents=True, exist_ok=False)
    scratch = run / "tmp"
    scratch.mkdir()
    env = dict(os.environ, TMPDIR=str(scratch), TMP=str(scratch), TEMP=str(scratch))
    proof = subprocess.check_output([str(python), "-c",
        "import tempfile,sys; print(sys.executable); print(tempfile.gettempdir())"],
        env=env, text=True).splitlines()
    if Path(proof[0]).resolve() != python.resolve() or Path(proof[1]).resolve() != scratch:
        raise RuntimeError("TEST_PYTHON_TEMP_MISMATCH")
    started = time.monotonic()
    with (run / "stdout.txt").open("xb") as out, (run / "stderr.txt").open("xb") as err:
        rc = subprocess.run(argv, env=env, stdout=out, stderr=err, check=False).returncode
    (run / "result.json").write_text(json.dumps(dict(argv=argv, test_python=proof[0],
        tempfile_dir=proof[1], exit_code=rc, elapsed_seconds=time.monotonic()-started)) + "\n")
    return rc

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("argv", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
    if not argv: parser.error("command required")
    policy = load_registered_policy()
    raise SystemExit(run_gate(root=args.root, python=args.python, argv=argv, policy=policy))

if __name__ == "__main__": main()
```

`load_registered_policy() -> GatePolicy`定义在同脚本：读冻结env引用的JSON bytes、验证SHA256、execution_host等于实际hostname、task_root等于操作者登记root；require_ai_station_nvme来自核验主机身份的operator登记，不按OS推断。缺字段/引用/hash漂移/host不符均在spawn前拒绝。补ai-station正确/错误root、其他Linux合法root、macOS合法root及所有host exactPython/TEMP mismatch、连续调用不同scratch测试；mismatch后证明待测命令没有启动。每次pytest JUnit和colcon log-base均使用唯一invocation目录，scratch回读后标deletion candidate，不删除。

- [ ] 后续每个 Python RED/GREEN 使用下列固定 zsh函数；定义一次，任务中的 `pygate <testpath>`均是它的确切调用：

```zsh
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
TASK_WORKTREE="$PWD"
export PYTHONPATH="$PWD/src/so101_teleop:$PWD/src/so101_demo_py${PYTHONPATH:+:$PYTHONPATH}"
GATE_SCRIPT="$PWD/src/so101_teleop/test/e2e/record_gate.py"
pygate() {
  cd "$TASK_WORKTREE" || return 1
  local invocation_dir
  invocation_dir=$(mktemp -d "$SO101_TASK_ROOT/pytest-XXXXXXXX") || return 1
  "$TEST_PYTHON" "$GATE_SCRIPT" --root "$SO101_TASK_ROOT" --python "$TEST_PYTHON" -- \
    "$TEST_PYTHON" -m pytest -p no:cacheprovider "$@" -q --junitxml="$invocation_dir/junit.xml"
}
bungate() {
  ( cd "$TASK_WORKTREE/src/so101_teleop/web" || return 1
    "$TEST_PYTHON" "$GATE_SCRIPT" --root "$SO101_TASK_ROOT" --python "$TEST_PYTHON" -- "$BUN" "$@" )
}
```

source单测必须证明 `so101_teleop.__file__`来自本worktree；installed gate另开shell，禁止带source PYTHONPATH。`TEST_PYTHON`、`BUN`、`SO101_TASK_ROOT`不能为空，且路径存在/已登记，否则函数入口拒绝。GREEN：`pygate src/so101_teleop/test/test_unified_gate.py`。

- [ ] Scoped commit：`git add src/so101_teleop/test/e2e/record_gate.py src/so101_teleop/test/test_unified_gate.py src/so101_teleop/CMakeLists.txt`；`git commit -m "test: record unified webapp gates with exact temp provenance"`。

### Task 1：纯类型与持久全局 arbiter

Files：Create `src/so101_teleop/so101_teleop/unified/__init__.py`、`contracts.py`、`intent_store.py`、`arbiter.py`、`src/so101_teleop/test/teleop/test_unified_arbiter.py`；Modify `src/so101_teleop/CMakeLists.txt`（`test_unified_arbiter`）。

Interfaces：全部后续类型来自 `unified.contracts`，不导入 ROS：

```python
from dataclasses import dataclass
from enum import StrEnum

class Domain(StrEnum):
    TELEOP = "teleop"
    VALIDATION = "validation"

@dataclass(frozen=True)
class RequestAuthority:
    domain: Domain
    instance_id: str
    proof: str
    channel_revision: int
    execution_generation: int

@dataclass(frozen=True)
class LeaseIdentity:
    lease_id: str
    service_session_id: str
    lease_generation: int
    expires_monotonic_ns: int

@dataclass(frozen=True)
class OwnerKey:
    pid: int
    pgid: int
    started_ticks: int
    argv_sha256: str
    environment_sha256: str

@dataclass(frozen=True)
class OperationSpec:
    command_id: str
    domain: Domain
    kind: str
    payload: dict
    runtime_id: str
    execution_generation: int
    deadline_ns: int

@dataclass(frozen=True)
class ActionKey:
    operation_id: str
    child_id: str
    goal_uuid: str
    owner: OwnerKey
    runtime_id: str
    execution_generation: int

@dataclass(frozen=True)
class ActionTerminal:
    key: ActionKey
    succeeded: bool
    stopped_confirmed: bool
    cleanup_confirmed: bool

@dataclass(frozen=True)
class DispatchAck:
    key: ActionKey
    accepted: bool

class MutationError(RuntimeError):
    @property
    def code(self): return str(self)
```

新增 `Reservation(operation_id: str, spec: OperationSpec, phase: str, cancel_requested: bool)`、`PendingChildKey(operation_id: str, child_id: str, runtime_id: str, execution_generation: int)`、`DispatchToken(operation_id: str, child_id: str, runtime_id: str, execution_generation: int, deadline_ns: int, revocation_revision: int)`、`RevokeTarget(key: PendingChildKey, revocation_revision: int)`、`CancelIntent(operation_id: str, targets: tuple[RevokeTarget,...])`和`ParentProjection(operation_id: str, phase: str, children: tuple[ActionTerminal, ...], blocked_reason: str | None)` dataclasses也在本task定义。revocation_revision从parent持久counter取得，prepare保存当前revision，cancel在同事务递增并枚举所有已prepare child（含未send、无ACK）；`cancel_parent`返回CancelIntent。proof从不进入持久payload或日志。

`IntentStore.open(root: Path) -> IntentStore`创建私有0700目录、O_NOFOLLOW0600锁并排他flock；SQLite完整sync事务，新增版本化表，不改Validation旧store。`close() -> None`；`GlobalMutationArbiter(store, *, clock_ns: Callable[[], int])`的公开方法：`begin(spec: OperationSpec) -> Reservation`、`prepare_child(operation_id: str, child_id: str) -> DispatchToken`、`record_ack(token: DispatchToken, ack: DispatchAck) -> None`、`cancel_parent(operation_id: str) -> CancelIntent`、`record_terminal(terminal: ActionTerminal) -> None`、`pause(operation_id: str) -> None`、`settle(operation_id: str, *, cleanup_confirmed: bool) -> ParentProjection`、`projection(operation_id: str) -> ParentProjection`、`is_idle() -> bool`、`block(reason: str) -> None`。开始时旧未收敛intent进入BLOCKED，不自动dispatch。

- [ ] RED测试真实持久接口：

```python
import pytest
from so101_teleop.unified.contracts import Domain, OperationSpec, MutationError
from so101_teleop.unified.intent_store import IntentStore
from so101_teleop.unified.arbiter import GlobalMutationArbiter

def test_durable_reservation_survives_restart_and_idempotency(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    arbiter = GlobalMutationArbiter(store, clock_ns=lambda: 100)
    spec = OperationSpec("arm-1", Domain.TELEOP, "execute", {"plan_id": "p1"}, "R1", 1, 1000)
    first = arbiter.begin(spec)
    assert arbiter.begin(spec).operation_id == first.operation_id
    with pytest.raises(MutationError, match="COMMAND_ID_REUSED"):
        arbiter.begin(OperationSpec("arm-1", Domain.TELEOP, "execute", {"plan_id": "p2"}, "R1", 1, 1000))
    store.close()
    store = IntentStore.open(tmp_path / "state")
    restored = GlobalMutationArbiter(store, clock_ns=lambda: 101)
    with pytest.raises(MutationError, match="BLOCKED"):
        restored.begin(OperationSpec("v1", Domain.VALIDATION, "start", {}, "R1", 1, 1000))
    assert restored.projection(first.operation_id).phase == "BLOCKED"
    store.close()
```

RED/GREEN：`pygate src/so101_teleop/test/teleop/test_unified_arbiter.py`，RED期望模块缺失；GREEN非零测试且全部通过。

- [ ] 最小事务核心：同一SQLite `BEGIN IMMEDIATE`内查command fingerprint/repeated记录、检查global状态，再插入parent/reservation/intent，COMMIT后才返回；不能先查active再异步写intent。fingerprint用排序canonical JSON，拒绝NaN。`prepare_child`同事务确认parent未取消、runtime/generation/deadline，持久DISPATCH_INTENT并返回token；send在事务外，parent始终占用。late ACK即使parent已cancel也登记精确goal并交安全lane取消，不抛弃owner记录。仅terminal与cleanup证明允许settle，pause保持reservation。

```python
def begin(self, spec):
    with self.store.immediate_transaction():
        repeated = self.store.repeat(spec.command_id, self.store.fingerprint(spec))
        if repeated is not None:
            return repeated
        self.store.require_idle()
        return self.store.insert_parent(spec)
```

本代码中的 `immediate_transaction() -> ContextManager[None]`、`fingerprint(spec) -> str`、`repeat(command_id, fingerprint) -> Reservation | None`、`require_idle() -> None`、`insert_parent(spec) -> Reservation`为本task的IntentStore私有实现契约，不能引用未定义helper。补双线程/两连接同N运行竞争、第二service lock拒绝、取消在prepare/ACK之间、terminal无cleanup仍阻塞及旧历史byte hash未变；每个先RED再GREEN。

- [ ] Scoped commit：精确stage本task四个新模块、该测试和CMake；`git commit -m "feat: persist global mutation reservations and crash fences"`。

### Task 2：服务器可验证的实例绑定

Files：Create `src/so101_teleop/so101_teleop/unified/instances.py`、`src/so101_teleop/test/teleop/test_unified_instances.py`；Modify `contracts.py`、`src/so101_teleop/CMakeLists.txt`（`test_unified_instances`）。

Interfaces：`InstanceProof(instance_id: str, proof: str, domain: Domain)`、`ChannelBinding(instance_id: str, revision: int, domain: Domain)`；`InstanceRegistry(arbiter, *, service_epoch: str, origin: str, clock_ns: Callable[[], int])`；`register(domain) -> InstanceProof`、`connect(instance_id, proof, *, origin: str) -> ChannelBinding`、`claim(binding, lease: LeaseIdentity) -> RequestAuthority`、`authorize(authority, lease) -> None`、`disconnect(binding) -> None`、`handoff(current: RequestAuthority, target: ChannelBinding, lease: LeaseIdentity) -> RequestAuthority`、`execution_generation(domain) -> int`。connect由实际WS owner调用，HTTP客户端不能自己声明“已连接”；lease的真实授权由Task6域服务验证后传入。

跨store明确采用持久fenced协议，不声称两个SQLite能共用事务。新增 `LeaseBindingCoordinator(store, registry, lease_port)`；`DomainLeasePort.acquire(body: dict) -> Awaitable[LeaseIdentity]`、`renew(lease, body) -> Awaitable[LeaseIdentity]`、`release(lease, body) -> Awaitable[None]`是对现有两域真实lease方法的typed adapter。`acquire(binding, body) -> Awaitable[RequestAuthority]`顺序为：IntentStore短事务持久CLAIMING及随机claim ID并设置global admission fence → 事务外域store acquire → IntentStore记录完整lease identity → 短事务验证原channel仍live、绑定controller与execution generation并标BOUND/清claim fence → 返回authority。每个mutation同时验证BOUND记录、live channel、真实当前lease和generation；单有lease或单有binding都不可dispatch。失败/进程死亡/ACK丢失留下CLAIMING/UNKNOWN fence，重启不补acquire、claim或handoff；只按精确owned lease证明和无未收敛owner的显式recovery处理。renew用RENEWING fence及同样双层检查，更新lease generation但不改execution generation；handoff先全局idle/cleanup证据，通过HANDOFF fence原子提交新execution generation后才对外可执行，旧instance先失效。任何中途错误都不恢复旧许可。Coordinator在本task定义于instances.py，Task6路由和Task5内部gateway接同一实例。

增加真实双store切点测试：acquire之前/成功之后/binding提交之前/Web死亡、renew域commit之后、handoff目标disconnect，以及复制lease调用legacy接口；全部证明没有可执行的半绑定、restart保持blocked，不自动重试。测试DomainLeasePort fake必须有独立SQLite lease事务，不用与IntentStore同connection冒充跨store原子性。

RENEWING是域级新外部mutation fence，不把正常heartbeat升级成全局BLOCKED，也不取消/释放已接受parent。Coordinator新增`guard_parent(parent: Reservation, authority: RequestAuthority) -> Awaitable[None]`：若该域renew正在提交，等待其独立completion event直到parent原deadline（不延长），然后重新检查live instance、同execution generation与fresh服务器lease binding；未完成前不派发下一child，已接受action继续观察、safe cancel不等待此event。Task5 sequencer的authority_guard签名为`Callable[[RequestAuthority], Awaitable[None]]`并在每个child前await；adapter捕获parent reservation后调用guard_parent，绝不重发已接受child。renew正常完成只更新lease generation并唤醒，不需用户重新授权同parent；过期、失联、renew失败/未知结果才持久blocked并安全停止。新增长parent跨多次heartbeat、arm→gripper中途renew、暂停parent续约、renew卡住截止和cancel并行测试，证明execution generation不变、child恰一次且正常renew不误中断。

- [ ] RED代码：

```python
import pytest
from so101_teleop.unified.instances import InstanceRegistry
from so101_teleop.unified.contracts import Domain, LeaseIdentity, MutationError, RequestAuthority
from so101_teleop.unified.intent_store import IntentStore
from so101_teleop.unified.arbiter import GlobalMutationArbiter

def test_copied_lease_cannot_control_and_renewal_does_not_change_execution(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    arb = GlobalMutationArbiter(store, clock_ns=lambda: 1)
    r = InstanceRegistry(arb, service_epoch="e1", origin="http://127.0.0.1:8000", clock_ns=lambda: 1)
    one, two = r.register(Domain.TELEOP), r.register(Domain.TELEOP)
    a = r.connect(one.instance_id, one.proof, origin="http://127.0.0.1:8000")
    b = r.connect(two.instance_id, two.proof, origin="http://127.0.0.1:8000")
    lease = LeaseIdentity("l1", "s1", 1, 100)
    owner = r.claim(a, lease)
    with pytest.raises(MutationError, match="CONTROLLER_ALREADY_BOUND"):
        r.claim(b, lease)
    copied = RequestAuthority(Domain.TELEOP, two.instance_id, two.proof, b.revision, owner.execution_generation)
    with pytest.raises(MutationError, match="CONTROLLER_INSTANCE_MISMATCH"):
        r.authorize(copied, lease)
    renewed = LeaseIdentity("l1", "s1", 2, 120)
    r.authorize(owner, renewed)
    assert r.execution_generation(Domain.TELEOP) == owner.execution_generation
    moved = r.handoff(owner, b, renewed)
    assert moved.execution_generation == owner.execution_generation + 1
    with pytest.raises(MutationError): r.authorize(owner, lease)
    store.close()
```

RED/GREEN：`pygate src/so101_teleop/test/teleop/test_unified_instances.py`。

- [ ] 最小核心 `proof = secrets.token_urlsafe(32)`，服务器内存保存proof hash，使用`secrets.compare_digest`校验；proof不得持久化。execution generation由IntentStore独立表持久维护；claim/handoff与arbiter idle/fences在同一短事务检查，instance/channel变更受同一服务锁保护。renew只更新lease projection，不更新execution generation。重连原子revision+1使旧连接及携带旧revision的HTTP拒绝；proof持久存储、browser自报revision或广播锁不构成authority。
- [ ] 增加RED/GREEN：新epoch拒绝旧proof，两个域proof互换、无通道、Origin错、duplicate/refresh observer均拒绝控制；同时handoff只有一次成功；parent运行/cleanup/recovery fence时handoff失败，旧channel late request拒绝。显式abandoned-controller恢复必须先真实域lease失效且owner收敛，不提供claim自动接管。
- [ ] Scoped commit：精确stage `instances.py`、`contracts.py`、新测试、CMake；`git commit -m "feat: bind domain controllers to live document instances"`。

### Task 3：独立安全 lane 与 arm/gripper goal registry

Files：Create `src/so101_teleop/so101_teleop/unified/goals.py`、`safety.py`、`src/so101_teleop/test/teleop/test_unified_safety.py`；Modify `contracts.py`、CMake（`test_unified_safety`）。

Interfaces：`SafetyLimits(delivery_s: float, stop_s: float, max_pending: int)`（正值且deployment与backend界限相容；测试值不是实测budget）；`SafetyAuthority(kind: Literal['browser','maintenance','watchdog'], domain: Domain, service_epoch: str, execution_generation: int, instance: RequestAuthority | None)`；`CancelReceipt(key: ActionKey, accepted: bool, terminal: ActionTerminal | None, blocked_reason: str | None)`。`GoalRegistry.register(key, *, cancel: Callable[[], Awaitable[bool]], observe: Callable[[], Awaitable[ActionTerminal]]) -> None`、`require(key) -> OwnedGoal`；`OwnedGoal`保存key及上述两个callables。`SafetyLane(registry, arbiter, *, limits, authorize: Callable[[SafetyAuthority, ActionKey], None])`；`cancel(key, authority) -> Awaitable[CancelReceipt]`，内部独立有界queue与专用task，重复key合并。

- [ ] RED测试不依赖rclpy，也不只测按钮：

```python
import asyncio
from so101_teleop.unified.contracts import (
    OwnerKey, ActionKey, ActionTerminal, Domain, OperationSpec, DispatchAck)
from so101_teleop.unified.goals import GoalRegistry
from so101_teleop.unified.safety import SafetyLane, SafetyLimits, SafetyAuthority

def test_isolated_lane_delivers_and_waits_for_stop_evidence(tmp_path):
    async def run():
        from so101_teleop.unified.intent_store import IntentStore
        from so101_teleop.unified.arbiter import GlobalMutationArbiter
        store = IntentStore.open(tmp_path / "state")
        arb = GlobalMutationArbiter(store, clock_ns=lambda: 1)
        goals, delivered, stopped = GoalRegistry(), asyncio.Event(), asyncio.Event()
        parent = arb.begin(OperationSpec("grip-1", Domain.TELEOP, "gripper",
                           {"target": 0.0}, "R1", 1, 100))
        token = arb.prepare_child(parent.operation_id, "gripper")
        key = ActionKey(parent.operation_id, "gripper", "goal-6", OwnerKey(11,11,9,"a","e"), "R1", 1)
        arb.record_ack(token, DispatchAck(key, True))
        async def cancel(): delivered.set(); return True
        async def observe():
            await stopped.wait()
            return ActionTerminal(key, False, True, True)
        goals.register(key, cancel=cancel, observe=observe)
        lane = SafetyLane(goals, arb, limits=SafetyLimits(.2,.5,2), authorize=lambda a,k: None)
        authority = SafetyAuthority("watchdog", Domain.TELEOP, "e1", 1, None)
        pending = asyncio.create_task(lane.cancel(key, authority))
        await asyncio.wait_for(delivered.wait(), .2)
        assert not pending.done()
        stopped.set()
        receipt = await pending
        assert receipt.terminal.stopped_confirmed
        await lane.close()
        store.close()
    asyncio.run(run())
```

定义 `SafetyLane.close() -> Awaitable[None]`用于关闭自己的processor，不signal foreign。测试authorize lambda只隔离调度，另一个测试用Task2 registry加真实authority检查，不能把该lambda接到production。

这个单测只证明lane delivery/stop等待，不证明绕过生产锁。`SafetyLane.revoke(target: RevokeTarget, authority: SafetyAuthority) -> Awaitable[IntentCancelReceipt]`用于无实际goal UUID的intent；`IntentCancelReceipt(target: RevokeTarget, linearized: bool, submitted: bool, terminal: ActionTerminal | None, blocked_reason: str | None)`在contracts.py定义。HTTP parent cancel先持久cancel_parent，逐target走revoke，再按registry已知ActionKey取消；两类receipt都不是自动释放reservation许可。

SafetyLane构造器新增`authorize_pending: Callable[[SafetyAuthority, RevokeTarget], None] | None = None`，生产composition必须注入精确parent/child/runtime/generation/owned child验证器；None仅供不测试pending的isolated unit，调用revoke即拒绝。pending revoke同样走独立bounded safe queue，不靠GoalRegistry.require一个尚不存在的handle。

RED/GREEN：`pygate src/so101_teleop/test/teleop/test_unified_safety.py`。

- [ ] 最小取消核心：`authorize(authority,key)` → 短事务 `cancel_parent`禁止后续child → 安全lane `await asyncio.wait_for(goal.cancel(), delivery_s)` → 保存accepted → `await asyncio.wait_for(goal.observe(), stop_s)` → 仅可靠terminal/停止/cleanup后记录，未确认则`arbiter.block`。这条lane不调用普通`_commands.run`，也不使用普通mutation executor pool；goal callback只发cancel请求，不等待普通action线程锁。
- [ ] 补 arm与gripper独立UUID、重复cancel合并、late ACK登记后立刻安全取消、旧goal/generation/foreign owner拒绝；普通queue满、safe queue满、delivery/stop超时、lease过期/maintenance/Web watchdog各authority切点。accepted无stop证明不能settle；无可验证cancel能力的backend capability关闭，workflow stop仍按原capability。
- [ ] Scoped commit：精确stage两个模块、contracts、该测试和CMake；`git commit -m "feat: isolate owned arm and gripper cancellation from mutation locks"`。

### Task 4：封闭 IPC 与非 Web ROS child

Files：Create `src/so101_teleop/so101_teleop/unified/ipc.py`、`bridge.py`、`ros_child.py`、`child_runtime.py`、`src/so101_teleop/test/teleop/test_unified_ipc.py`、`test_unified_bridge.py`、`test_unified_two_channel.py`、`src/so101_teleop/test/e2e/unified_child_harness.py`；Modify `src/so101_teleop/so101_teleop/server.py`、CMake（三个新测试）。

Interfaces：`BridgeLaunch(ros_python: Path, install_prefix: Path, runtime_id: str, environment: dict[str,str], socket_root: Path)`；`BridgeProcessOwner(launch, arbiter, safety)`的 `start() -> Awaitable[OwnerKey]`、`stop_owned() -> Awaitable[None]`、`ready() -> bool`。`BridgeClient.call(packet: IpcRequest) -> Awaitable[IpcReply]`、`cancel(key,authority) -> Awaitable[CancelReceipt]`走独立socket。`IpcRequest`是Pydantic `extra='forbid'`版本1封闭union：observe/plan_joints/plan_tcp/execute_arm/gripper/home-child/attachment/scene_repair/simulation_reset/camera_preset/parameters/workflow，payload使用原DTO与逐operation validator；字段包括command ID、DispatchToken、epoch、deadline，不支持shell/method/path/executable。`IpcReply(accepted: bool, ack: DispatchAck | None, terminal: ActionTerminal | None, code: str)`，observe类型响应沿用原TelemetrySnapshot。`decode_request(raw: bytes, *, max_bytes: int, now_ns: int) -> IpcRequest`。

- [ ] RED核心协议代码：

```python
import json, pytest
from so101_teleop.unified.ipc import decode_request

def test_ipc_accepts_observe_for_bound_epoch_and_runtime():
    document = dict(version=1, operation="observe", command_id="read-1",
                    deadline_ns=100, service_epoch="e1", runtime_id="R1", payload={})
    request = decode_request(json.dumps(document).encode(), max_bytes=1024, now_ns=1)
    assert request.operation == "observe"
    assert request.runtime_id == "R1" and request.service_epoch == "e1"

@pytest.mark.parametrize("document", [
    {"version": 1, "operation": "shell", "payload": {"cmd": "echo unsafe"}},
    {"version": 2, "operation": "observe", "command_id": "x", "deadline_ns": 100},
    {"version": 1, "operation": "observe", "command_id": "x", "deadline_ns": 0},
    {"version": 1, "operation": "observe", "command_id": "x", "deadline_ns": 100, "executable": "foreign"},
])
def test_ipc_rejects_unknown_extra_expired_and_version(document):
    with pytest.raises(ValueError):
        decode_request(json.dumps(document).encode(), max_bytes=1024, now_ns=1)
```

各union成员明确字段；observe也须epoch/runtime绑定，但不需要运动token。再补合法observe和合法execute包成功、oversize、NaN、坏peer UID/token、expired queued mutation无dispatch；不能让所有包都失败的假decoder通过。

- [ ] 双socket取消的唯一线性化点位于纯生产`child_runtime.py`的`ChildRuntime(driver: ActionDriver, *, owner: OwnerKey, service_epoch: str, runtime_id: str, normal_queue_limit: int)`。普通/安全连接各有独立reader/task，公共短临界区只排序状态，不持锁等待ROS、normal queue或ACK。Envelope强制绑定该child精确owner、epoch与peer credential，旧child包不能在新进程复用。child不打开IntentStore，也不请求Web取消状态；自身进程生命周期内tombstone不可删除/降revision。restart换owner/epoch，Web durable未收敛intent保持fence，禁止自动重派。

`ActionDriver`纯Protocol：`allocate_goal_uuid(key: PendingChildKey) -> str`、`submit(token: DispatchToken, goal_uuid: str) -> Awaitable[DispatchAck]`、`cancel(goal_uuid: str) -> Awaitable[bool]`、`terminal(goal_uuid: str) -> Awaitable[ActionTerminal]`。ROSadapter预分配实际ROS goal UUID并在send前登记；实施前只读取pinned rclpy ActionClient签名确认显式goal_uuid受支持，不能用代理UUID冒充实际UUID，不支持就阻塞。`ChildRuntime.submit(token) -> Awaitable[DispatchAck]`与`revoke(target) -> Awaitable[IntentCancelReceipt]`遵守下表：

| 短临界区状态/先后 | 持久Web/本地处理 | 能否释放 |
| --- | --- | --- |
| cancel先于submit | tombstone=max(existing,target.rev)；标REVOKED；迟到token.rev<=tombstone零driver.submit | 只证明该child未submit；parent仍须其他child/cleanup收敛 |
| submit先胜 | 注册PendingChildKey+实际预分配UUID，READY→SUBMITTING后才离开锁调用driver；cancel标cancel_requested/tombstone | 不可；UUID/pending不能丢 |
| SUBMITTING时cancel/ACK丢失 | accepted回调即使HTTP/普通IPC已断仍登记handle、立即安全cancel；registry保持UUID直到terminal | accepted!=stopped，超时/unknown blocked |
| Web死亡/watchdog | 撤销本地全部known pending/owned children及parent，不依赖Web响应；停证据/cleanup独立回报 | Web旧intent仍待显式recovery |

核心排序不是“先检查再submit”：

```python
async with self.transition_lock:
    key = pending_key(token)
    if token.revocation_revision <= self.tombstones.get(key, -1):
        raise MutationError("INTENT_REVOKED")
    pending = self.pending.get(key)
    if pending is None:
        pending = PendingSubmission(token, self.driver.allocate_goal_uuid(key), "SUBMITTING", False)
        self.pending[key] = pending
# driver.submit在锁外；重复token复用同pending task，不再次调用driver。
```

`pending_key(token) -> PendingChildKey`逐字段构造，`PendingSubmission(token: DispatchToken, goal_uuid: str, phase: str, cancel_requested: bool)`定义同模块；普通reader只有transition之后创建一次submission task。revoke临界区即更新tombstone/cancel_requested，safe task独立处理driver cancel，submit回调检查该标志；submit失败仍保留明确失败或unknown证据，不能默认从pending删掉。

`BridgeClient.revoke(target: RevokeTarget, authority: SafetyAuthority) -> Awaitable[IntentCancelReceipt]`发送封闭`SafetyPacket(version=1, operation='revoke', service_epoch: str, owner: OwnerKey, target: RevokeTarget)`，safe socket验证peer与当前精确owner再进入ChildRuntime.revoke；取消无需actual goal UUID。Web失联watchdog在child本地设置不可回退`web_dead` latch并撤销所有known pending/owned集合；即使此前未知的迟到普通包随后到达，submit首先检查web_dead并拒绝，不等待Web回答。恢复必须换授权owner/epoch、显式收敛Web durable fence，不能清latch继续旧任务。

RED真实两通道测试放`test_unified_two_channel.py`：`TwoChannelHarness.start(root: Path) -> Awaitable[TwoChannelHarness]`定义于test/e2e/unified_child_harness.py，只在leaf注入BarrierActionDriver，child跑installed/source同一个ChildRuntime socket servers，Web侧使用真实BridgeClient；proxy仅可hold/release普通socket bytes，安全socket不走该proxy。harness公开`prepare_child() -> DispatchToken`（真实IntentStore/arbiter）、`hold_normal_delivery() -> None`、`send(token) -> Awaitable[DispatchAck]`、`revoke(token) -> Awaitable[IntentCancelReceipt]`（真实cancel_parent递增revision）、`release_normal_delivery() -> None`、`stats() -> Awaitable[ChildStats]`、`close() -> Awaitable[None]`。`ChildStats(submit_count: int, cancel_uuids: tuple[str,...], pending_uuids: tuple[str,...])`来自leaf driver实际调用journal，不是Web projection或mock计数。

```python
import asyncio, pytest
from so101_teleop.unified.contracts import MutationError
import importlib.util, sys
from pathlib import Path
spec=importlib.util.spec_from_file_location("unified_child_harness",
    Path(__file__).parents[1]/"e2e/unified_child_harness.py")
assert spec and spec.loader
helper=importlib.util.module_from_spec(spec); sys.modules[spec.name]=helper
spec.loader.exec_module(helper)
TwoChannelHarness=helper.TwoChannelHarness
def test_safe_revoke_wins_before_delayed_normal_packet(tmp_path):
    async def run():
        h=await TwoChannelHarness.start(tmp_path)
        try:
            token=h.prepare_child(); h.hold_normal_delivery()
            pending=asyncio.create_task(h.send(token))
            receipt=await h.revoke(token)
            assert receipt.linearized and not receipt.submitted
            h.release_normal_delivery()
            with pytest.raises(MutationError,match="INTENT_REVOKED"): await pending
            assert (await h.stats()).submit_count==0
        finally: await h.close()
    asyncio.run(run())
```

在test文件用`importlib`装载test/e2e helper，不安装它为产品包。再按真实driver barriers测试prepare未send、submit临界区前/后、actual goal accepted但ACK被proxy丢弃、Web死亡和cancel重复/旧revision；submit先胜要求submit_count恰1、取消UUID与pending UUID相等、未terminal时reservation保留。RED先临时删去child tombstone检查/把排序放到普通queue确认测试非零失败，恢复后GREEN；该诊断补丁不可commit。

RED/GREEN：`pygate src/so101_teleop/test/teleop/test_unified_ipc.py src/so101_teleop/test/teleop/test_unified_bridge.py src/so101_teleop/test/teleop/test_unified_two_channel.py`。

- [ ] 子进程启动核心：

```python
argv = [str(launch.ros_python), "-m", "so101_teleop.unified.ros_child",
        "--socket-root", str(launch.socket_root), "--runtime-id", launch.runtime_id]
child = subprocess.Popen(argv, env=launch.environment, shell=False,
                         start_new_session=True, stdin=subprocess.DEVNULL)
```

argv/ROS Python/环境只取server配置与installed provenance；不接受HTTP输入。child内才导入server的ROSworker/rclpy，复用现有backend/camera适配，禁用uvicorn。迁移 `_active_goal`为Task3 registry，arm与gripper accepted实际UUID均登记；阻塞wait不能阻塞独立安全socket处理和ROSexecutor。child验证token/current cancel状态，再提交goal；cancel与accept竞争时登记late goal并取消，parent保持占用。
- [ ] BridgeProcessOwner保存精确PID/PGID/ticks/argv/env identity，stop前重新确认；与Validation process-owner同样failclosed，不放宽其冻结probe策略。Web死亡/失联独立watchdog取消owned action，失去stop证明保持blocked；不启动/kill sim。用test-owned无ROS helper验证owner失联、PIDidentity错、ACK丢失、独立safe socket饱和、child crash影响Teleopreadiness但HTTP进程不退出。新增test `test_ros_import_is_child_only`用subprocess导入`unified.ipc/bridge`并断言`'rclpy' not in sys.modules`。
- [ ] Scoped commit：精确stageipc/bridge/ros_child/child_runtime及test helper、server、三个测试和CMake；`git commit -m "feat: move ROS ownership into a restricted non-web child"`。

### Task 5：父操作和所有内部 admission

Files：Create `src/so101_teleop/so101_teleop/unified/parents.py`、`admission.py`、`teleop_service.py`、`src/so101_teleop/test/teleop/test_unified_parents.py`、`test_unified_admission.py`；Modify `src/so101_teleop/so101_teleop/server.py`、`service.py`、`task_service.py`、`expert_validation/service.py`、`expert_validation/production.py`、CMake。

Interfaces：`WorkerPort` pure Protocol在parents.py定义 `dispatch_arm(plan_id: str, token: DispatchToken) -> Awaitable[DispatchAck]`、`dispatch_gripper(target: float, token) -> Awaitable[DispatchAck]`、`wait_terminal(ack) -> Awaitable[ActionTerminal]`、`plan_home() -> Awaitable[str]`、`workflow(operation: str, run_id: str, token) -> Awaitable[WorkflowCheckpoint]`。`WorkflowCheckpoint(run_id: str, phase: str, resumable: bool, physical_terminal: bool, cleanup_confirmed: bool)`；`ParentSequencer(worker,arbiter, *, authority_guard: Callable[[RequestAuthority], Awaitable[None]])`的 `execute_all(spec,authority) -> Awaitable[ParentProjection]`、`home(spec,authority)`、`workflow(spec,authority)`、`resume(operation_id,authority, *, operation: str)`；home/gripper target保持基线值和backend安全约束。

`AdmissionGateway(arbiter,instances)`的 `begin(spec,authority,lease) -> Reservation`和 `resume(parent_id,authority,lease) -> DispatchToken`共同检查实例与全局状态；继承token只能由持久parent绑定的内部sequencer生成，客户端不能提交parent ID取得授权。所有entrypoint最终调用此gateway，不只HTTP middleware。

无ROS生产类在`unified/teleop_service.py`明确实现为`ProductionTeleopService(worker: BridgeWorkerPort, *, admission: AdmissionGateway, lease_bindings: LeaseBindingCoordinator, parents: ParentSequencer, safety: SafetyLane, backend_view: BackendView, parameter_path: Path)`，不是Protocol或test helper。`BackendView(backend: str, owner_package: str, owner_executable: str, capabilities: dict[str,bool])`纯dataclass由批准配置+fresh child probe产生；`BridgeWorkerPort(client: BridgeClient)`在Task4 bridge.py实现WorkerPort，并提供`current_snapshot() -> Awaitable[TelemetrySnapshot]`、`plan_joints(body: dict) -> Awaitable[PlanSummary]`、`plan_tcp(body: dict) -> Awaitable[PlanSummary]`、`camera_presets() -> Awaitable[dict]`以及原restricted operation的typed command方法。全部经真实IPC；cached snapshot在失联时明确DISCONNECTED/stale，不创造READY。Web生产类持有原PlanStore/command fingerprints、parameter path与workflow checkpoint索引；lease状态只来自Coordinator，物理trajectory/action/goal handle只由child所有。把server.py:560起的应用逻辑迁入该类，所有mutation先gateway，ExecuteAll/home/workflow用ParentSequencer，cancel在普通`_commands.run`之外直达SafetyLane，旧业务capability/DTO/安全检查原样保留。service.py只re-export这个纯生产类，不再re-export ROSserver；child独占ROSworker/backend action实现。

Task6新增共享`compose_domain_services(*, environment: Mapping[str,str], evidence_root: Path, worker: BridgeWorkerPort, bridge_owner: BridgeProcessOwner, budget_source: BudgetSource, validation_execution_port: ExecutionPort | None = None) -> UnifiedServices`；生产compose_services先建立owned production child/BridgeWorkerPort再调用它，L2使用同一函数和同一ProductionTeleopService构造器。新增Teleop链的L2唯一替换为child最内层ActionDriver；Validation保留既有最底层typed ExecutionPort seam；test source launcher通过私有spawn callable把BarrierActionDriver注入installed ChildRuntime，仍用生产BridgeProcessOwner的owner验证/handshake/watchdog/stop和真实双socket。生产入口不暴露此callable、module或driver选择。不能替换任一域的业务service/supervisor/ownership/admission/lease/durable store，也不能注入替代TeleopPort、ParentSequencer、safety或IPC。compose_domain_services原样调用create_production_service(evidence_root, environment=environment, execution_port=validation_execution_port)。生产compose_services固定传None（即现有真实执行默认port），不从HTTP/CLI/env选择helper；仅test-source launcher允许透传。

- [ ] RED定义自包含可控fake，它实现上述WorkerPort的前3个方法供ExecuteAll测试，不用于production：

```python
import asyncio, pytest
from so101_teleop.unified.contracts import *
from so101_teleop.unified.parents import ParentSequencer
from so101_teleop.unified.intent_store import IntentStore
from so101_teleop.unified.arbiter import GlobalMutationArbiter

class TwoStepWorker:
    def __init__(self):
        self.arm_done=asyncio.Event(); self.gripper_sent=asyncio.Event()
        self.before_gripper=asyncio.Event(); self.gripper_allowed=asyncio.Event()
    async def dispatch_arm(self, plan_id, token):
        return DispatchAck(ActionKey(token.operation_id,"arm","g-arm",OwnerKey(1,1,1,"a","e"),"R1",1),True)
    async def dispatch_gripper(self,target,token):
        self.before_gripper.set()
        await self.gripper_allowed.wait()
        self.gripper_sent.set()
        return DispatchAck(ActionKey(token.operation_id,"gripper","g-grip",OwnerKey(1,1,1,"a","e"),"R1",1),True)
    async def wait_terminal(self,ack):
        if ack.key.child_id == "arm": await self.arm_done.wait()
        return ActionTerminal(ack.key,True,True,True)

def test_parent_blocks_validation_between_arm_and_gripper(tmp_path):
    async def run():
        store=IntentStore.open(tmp_path/"state")
        arb=GlobalMutationArbiter(store,clock_ns=lambda:1)
        worker=TwoStepWorker()
        authority=RequestAuthority(Domain.TELEOP,"i","p",1,1)
        async def allow(_): return None
        seq=ParentSequencer(worker,arb,authority_guard=allow)
        spec=OperationSpec("all-1",Domain.TELEOP,"execute_all",{"plan_id":"p1","gripper_target":0.0},"R1",1,100)
        pending=asyncio.create_task(seq.execute_all(spec,authority))
        worker.arm_done.set()
        await asyncio.wait_for(worker.before_gripper.wait(), 1)
        with pytest.raises(MutationError):
            arb.begin(OperationSpec("v1",Domain.VALIDATION,"start",{},"R1",1,100))
        worker.gripper_allowed.set()
        await worker.gripper_sent.wait()
        result=await pending
        assert len(result.children)==2 and result.phase=="COMPLETE"
        store.close()
    asyncio.run(run())
```

上述barrier使Validation竞争发生在确切中间段；补arm ACK前后独立切点及cancel后不得dispatch_gripper的测试。补home fake的plan_home、workflow pause/resume/abandon、失联guard抛MutationError、arm/第二步失败、Web reopen、duplicate payload、late ACK取消等独立RED测试；fake实现新增WorkerPort方法，不接production。

RED/GREEN：`pygate src/so101_teleop/test/teleop/test_unified_parents.py src/so101_teleop/test/teleop/test_unified_admission.py`。

- [ ] 以下是真正绕生产执行资源的整合test规范，实际文件/ProductionHarness在Task6的factory完成后创建与RED/GREEN，不是Task5门控的前向依赖。`test_unified_cancel_integration.py`复用Task4 helper；`ProductionHarness.start(root) -> Awaitable[ProductionHarness]`构造真实共享composition/HTTP TestClient、controller WS与真实lease coordinator，只把child ActionDriver换成barrier driver。helper公开`execute_all_http() -> Awaitable[ParentProjection]`、`cancel_http() -> Awaitable[IntentCancelReceipt]`、`wait_goal(kind: str) -> Awaitable[str]`、`teleop`（真实ProductionTeleopService）、`stats()`、`fill_normal_ipc_queue() -> Awaitable[int]`和`close()`；前两方法执行真实route握手/headers，不直接注册不相关goal。barrier driver实际submit后保持terminal未完成，取消后才允许terminal，safe socket独立处理。

```python
def test_production_cancel_bypasses_busy_normal_coordinator(tmp_path):
    async def run():
        h=await helper.ProductionHarness.start(tmp_path)
        try:
            running=asyncio.create_task(h.execute_all_http())
            goal=await h.wait_goal("arm")
            assert h.teleop._commands._lock.locked()
            receipt=await asyncio.wait_for(h.cancel_http(), .5)
            assert receipt.linearized
            stats=await h.stats()
            assert goal in stats.cancel_uuids
            result=await asyncio.wait_for(running, 1)
            assert result.phase != "COMPLETE"
        finally: await h.close()
    asyncio.run(run())
```

该test文件显式`import asyncio`并用前述importlib完整装载同一helper；.5/1仅fixture门槛不是live安全实测阈值。重复测试gripper与parent中间段；`fill_normal_ipc_queue`通过真实普通socket/已prepare sibling tokens填满ChildRuntime配置的bounded normal queue，读实际queue depth达到limit，再取消同一个已接受goal。RED临时把ProductionTeleopService.cancel送回其`_commands.run`或让safe IPC共用normal queue，确认非零失败；恢复独立路径GREEN。命令：`pygate src/so101_teleop/test/teleop/test_unified_cancel_integration.py`，Task11 copied-install Chrome必须重复同类真实场景，helper不能自实现parent/cancel绕过生产逻辑。

- [ ] 最小sequencer核心：

```python
parent = arbiter.begin(spec)
await authority_guard(authority)
arm_token = arbiter.prepare_child(parent.operation_id, "arm")
arm_ack = await worker.dispatch_arm(spec.payload["plan_id"], arm_token)
arbiter.record_ack(arm_token, arm_ack)
arm_terminal = await worker.wait_terminal(arm_ack)
arbiter.record_terminal(arm_terminal)
if not arm_terminal.succeeded:
    return arbiter.settle(parent.operation_id, cleanup_confirmed=arm_terminal.cleanup_confirmed)
await authority_guard(authority)
grip_token = arbiter.prepare_child(parent.operation_id, "gripper")
```

随后dispatch_gripper、record_ack/terminal和parent settle；每个异常路径把未确认owner记blocked，不能finally无条件释放。workflow pause保留parent，原reset只有owned停止/cleanup证明后才失效checkpoint；原不支持stop保持不可用。业务与infra结果保持分类，不用parent COMPLETE替换物理成功证据。
- [ ] admission测试直接调用真实Teleop/Tasks/Validation service注入gateway，不只测试arbiter toy：包括plan/execute/gripper/attachment/scene/home/reset/camera/parameters/workflow、Tasks start/recovery/shutdown/capture/render/reachability、Validation manifest/preflight/start/retry及内部dispatch。现有safe cancel和renew走Task3/2而不进入普通reservation队列；纯GET只读不占用。每个mutation分类有明确表和失败断言，未知新operation默认拒绝。
- [ ] Scoped commit：精确stageparents/admission、上述四个existing service文件、两个测试及CMake；`git commit -m "feat: arbitrate parent operations across teleop tasks and validation"`。

### Task 6：单 factory、生命周期、路由和 OpenAPI

Files：Create `src/so101_teleop/so101_teleop/unified/ports.py`、`app.py`、`lifecycle.py`、`main.py`、`src/so101_teleop/scripts/so101_unified_web_server.py`、`src/so101_teleop/test/teleop/test_unified_api.py`、`test_unified_lifecycle.py`；Modify `src/so101_teleop/so101_teleop/api.py`、`expert_validation/api.py`、`main.py`、`expert_validation/main.py`、`openapi_export.py`、`service.py`、`src/so101_teleop/launch/so101_teleop.launch.py`、CMake、两个旧server scripts、`web/package.json`及两套生成schema。

另外Modify `src/so101_teleop/so101_teleop/unified/contracts.py`用于提前纯QualificationView schema；Create `src/so101_teleop/test/teleop/test_unified_cancel_integration.py`并Modify `src/so101_teleop/test/e2e/unified_child_harness.py`，在真实factory完成后增加ProductionHarness，执行Task5已列出的取消整合RED/GREEN再完成本task。其CMake注册/staging归Task6，不把尚无factory的整合测试放进Task5提交。

Interfaces：pure `TeleopPort`继承现有HTTP行为的 `health()`、`current_snapshot()`、`command(name,body)`、`execute_plan(plan_id,body)`、`camera_presets()`，均async；`TasksPort`保留现有TaskService方法的签名，`ValidationPort`保留production service现有方法，使用 `typing.Protocol` 明列各route实际调用而不import ROSserver。`UnifiedServices(teleop: TeleopPort | None, tasks: TasksPort | None, validation: ValidationPort | None, arbiter, instances, safety, bridge)`为dataclass。`create_unified_app(services, *, static_dir: Path | None, capture_dir: Path | None, bind_address: str) -> FastAPI`；`compose_services(environment: Mapping[str,str]) -> UnifiedServices`只连接已批准runtime，`unified.main.main() -> None`唯一uvicorn入口。

Protocol方法沿用现有DTO，返回相同DTO/JSON（不另造字段）；TeleopPort还定义`capabilities() -> Awaitable[dict]`、`telemetry_wait() -> Awaitable[None]`。TasksPort async方法为`presets()`、`reachability(body)`、`start(body)`、`list_runs()`、`status(run_id)`、`cancel(run_id,body)`、`recovery(run_id,body)`、`capture(body)`、`rendered_image(capture_id,body)`、`shutdown(body)`，同步`subscribe() -> asyncio.Queue`、`unsubscribe(queue) -> None`与`artifacts.open(id) -> OpenedArtifact`保留现有artifact类型。ValidationPort同步或async实现由现有`_invoke`统一await，方法为`health()`、`capabilities()`、`acquire_lease(body)`、`renew_lease(id,body)`、`release_lease(id,body)`、`create_manifest_from_count(count)`、`get_manifest_api(id)`、`get_manifest(id)`、`preflight_api(body)`、`start_campaign_api(body)`、`list_campaigns()`、`get_campaign(id)`、`cancel_campaign(id,body)`、`retry_campaign(id,body)`，`artifacts`和`subscribe/unsubscribe`沿用现有生产service接口。body参数均是现有DTO的model_dump dict或Tasks原DTO，不改变其业务字段。

新增schema-only `schema_services() -> UnifiedServices`使export不打开store、不起child；其纯fake methods与baseline `_SchemaOnlyService`一样仅供schema，不能安装为测试生产开关。

Task6在ports.py定义纯 `ExecutionPort` Protocol：`fixed_argv(request: CoordinatorStartRequest) -> tuple[str,...]`和`adaptive_argv(request: AdaptiveStartRequest) -> tuple[str,...]`；request类型沿用expert_validation/coordinator.py与adaptive.py，不引入测试包依赖。既有HelperExecutionPort结构上满足此port，它的qualification_manifest仍由原L2 fixture校验。source composition测试在test_unified_api.py同时走真实Teleop execute-all和Validation start/cancel routes，按全局互斥顺序运行，沿真实admission/lease/store/supervisor/owner路径。test_unified_lifecycle.py证明生产入口无helper选择flags/env参数，调用共享compose时validation_execution_port为None。不要用高层service monkeypatch证明透传。

本task提前在contracts.py定义Task10同字段的纯`QualificationView` dataclass，在ports.py定义`BudgetSource.decision(selected_n: int, runtime_identity: str) -> QualificationView` Protocol和`UnknownBudgetSource`（所有N返回UNKNOWN/BUDGET_PROVIDER_NOT_READY、profile/approval为None），使真实compose与API schema在Task10之前完整可用；Task10只实现adapter/真实映射，不重定义view。前端Task7从这一个unified-schema生成类型。`TasksArtifactPort.open(artifact_id: str) -> OpenedArtifact`使用现有task_artifacts.OpenedArtifact；ValidationArtifactPort仍用`resolve_opaque_id`返回其现有verified对象，索引和异常authority分开。TasksPort.artifacts严格为TasksArtifactPort，不是Validation resolver；route保留ArtifactAccessError/RuntimeError→404 ARTIFACT_NOT_FOUND、原FileResponse/media type和bytes。

同一个真实`/expert-validation/capabilities` route注册`QualificationCapabilities` response model：Pydantic BaseModel的`worker_qualifications: list[QualificationView]`必填，`extra='allow'`仅保留原只读capability字段；factory在未集成时填N2..8的UnknownBudgetSource结果。因此QualificationView是实际route可达schema，不是手工拼JSON或孤立types；Task10仅更新预算映射并按上游v2去掉旧K字段。

在test_unified_api.py补真实Tasks store测试：`artifacts=ManifestArtifactStore(tmp_path/'artifacts')`，其root下写`frame.png` fixture bytes，以`entry=artifacts.register_file(path,'image/png')`登记，production TasksPort实际artifacts属性指向该store，再用统一TestClient GET `/tasks/artifacts/{entry.artifact_id}`要求body等于原bytes、content-type为image/png且OpenedArtifact.sha256等于fixture SHA256；改file bytes后同ID必须404，unknown和`..%2F`path请求404。复用真实TaskService构造器，不用只实现错误resolver方法的fake，旧artifact manifest hash不修改。

```python
import asyncio, hashlib
from so101_teleop.task_artifacts import ManifestArtifactStore
def test_unified_tasks_artifact_uses_real_open_and_checksum(tmp_path):
    async def run():
        h=await helper.ProductionHarness.start(tmp_path)
        try:
            artifacts=h.services.tasks.artifacts
            assert isinstance(artifacts,ManifestArtifactStore)
            path=artifacts.root/'frame.png'; payload=b'fixture-png-bytes'
            path.write_bytes(payload)
            entry=artifacts.register_file(path,'image/png')
            assert artifacts.open(entry.artifact_id).sha256==hashlib.sha256(payload).hexdigest()
            url='/tasks/artifacts/'+entry.artifact_id
            response=h.client.get(url)
            assert response.status_code==200 and response.content==payload
            assert response.headers['content-type']=='image/png'
            path.write_bytes(b'changed')
            assert h.client.get(url).status_code==404
            assert h.client.get('/tasks/artifacts/unknown').status_code==404
            assert h.client.get('/tasks/artifacts/..%2Foutside').status_code==404
        finally: await h.close()
    asyncio.run(run())
```

test_unified_api.py同样用完整importlib loader装载Task4 helper；ProductionHarness公开`services: UnifiedServices`和`client: TestClient`供真实route验证，不能改成只实现artifact方法的应用fake。RED/GREEN仍为本task已给test_unified_api.py命令。

- [ ] RED最小route与import检查（文件内显式imports）：

```python
from fastapi.testclient import TestClient
from so101_teleop.unified.app import create_unified_app, schema_services

def test_single_factory_has_real_tasks_and_validation_without_deny():
    app=create_unified_app(schema_services(),static_dir=None,capture_dir=None,bind_address="127.0.0.1")
    routes=[r for r in app.routes if getattr(r,"path",None)=="/tasks/runs" and "POST" in getattr(r,"methods",set())]
    assert len(routes)==1
    assert not any(getattr(r,"name","")=="disabled_tasks" for r in app.routes)
    schema=app.openapi()
    assert "/expert-validation/campaigns" in schema["paths"]
    assert "/plans/{plan_id}/execute-all" in schema["paths"]
    with TestClient(app) as client:
        assert client.get("/health/live").status_code==200
        assert client.post("/gripper/execute",json={"command_id":"old","lease_id":"l","session_id":"s","target_position_rad":0.0}).json()["code"]=="CONTROLLER_INSTANCE_REQUIRED"
```

schema_services lifecycle为no-op，health/live可用，真实mutations默认拒绝；Task11以copied-install typedtest port证明真实路由可执行而非schema fake通过。RED/GREEN：`pygate src/so101_teleop/test/teleop/test_unified_api.py src/so101_teleop/test/teleop/test_unified_lifecycle.py src/so101_teleop/test/teleop/test_api.py src/so101_teleop/test/teleop/test_expert_validation_api.py`。

无ROS smoke必须真实隔离import链，不只查main文本：在test_unified_lifecycle.py用`subprocess.run([sys.executable,'-c', code],check=True)`执行下面code，source和copied-install各跑一次并保存module origins。service.py顶层`from .server import TeleopService`按Task5改为纯生产ProductionTeleopService的re-export，所有实际ROS构造仅进ros_child；TaskService/gateway/类型注解不得间接载入ROS。

```python
import importlib.abc, runpy, sys
class NoRos(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'rclpy','moveit_msgs','sensor_msgs','trajectory_msgs'}:
            raise ImportError('ROS_IMPORT_IN_WEB: '+fullname)
sys.meta_path.insert(0, NoRos())
import so101_teleop.unified.app, so101_teleop.openapi_export
runpy.run_module('so101_teleop.unified.main', run_name='import_probe')
assert 'rclpy' not in sys.modules
```

新/旧launcher还须用`runpy.run_path`以非`__main__`名称加载 installed scripts，无uvicorn/子进程启动；测试spy证明compose在无ROS时仍可建history/readiness HTTP app。

- [ ] router核心把existing closures抽成`teleop_router(service: TeleopPort, admission: AdmissionGateway, instances: InstanceRegistry, safety: SafetyLane) -> APIRouter`、`tasks_router(service: TasksPort, admission: AdmissionGateway, instances: InstanceRegistry, safety: SafetyLane) -> APIRouter`、`validation_router(service: ValidationPort, admission: AdmissionGateway, instances: InstanceRegistry, safety: SafetyLane) -> APIRouter`；旧create_app wrappers仅供原分域测试调用这些同源routers，产品entrypoints都委托unified。顶层API → instanceWS → health → static →明确页面 →SPA fallback。Validation占位capability与blanket Tasks deny不注册；artifact/APInamespace显式404。Origin/headers/WS proof握手、disconnect/revision、lease claim/renew、handoff接入Task2 Coordinator；执行authority与DispatchToken不靠客户端payload授予。
- [ ] lifespan先global lock/store/read旧intent，新epoch invalidate instance/leases，再maintenance和已配置bridge；ROS unavailable只影响其readiness，但未知owned intent影响全局。maintenance失败内部safe cancel不等普通队列。关闭先拒新mutation、安全lane与维护保留到owned停止/cleanup证明，超时持久blocked。health保留Teleop兼容字段，加域状态/原因；live200与ready503分开。配置两旧端口冲突返回配置错误，不同时bind；单入口沿用安全bind规则，production默认一个8000端口，旧脚本只委托并提示deprecated。
- [ ] OpenAPI：新增 `--unified OUTPUT`一次产生聚合schema；原default/--validation从同一schema过滤路径并保留refs，operation IDs唯一，authorityheaders与newparent/instance schemas全生成。

```zsh
"$TEST_PYTHON" -m so101_teleop.openapi_export --unified src/so101_teleop/so101_teleop/unified_openapi.json
"$TEST_PYTHON" -m so101_teleop.openapi_export src/so101_teleop/so101_teleop/openapi.json
"$TEST_PYTHON" -m so101_teleop.openapi_export --validation src/so101_teleop/so101_teleop/expert_validation_openapi.json
cd src/so101_teleop/web
bungate run generate:api
bungate run generate:api:validation
```

package增加精确 `generate:api:unified` script：`openapi-typescript ../so101_teleop/unified_openapi.json -o src/api/unified-schema.d.ts`并运行；新增openapi_export测试证明三视图来源相同、repeat export byte稳定。所有export命令也经Task0 record_gate保存输出/exit，避免无记录生成。
- [ ] Scoped commit：精确stage本task新文件、修改文件及生成JSON/TS（只stage实际生成文件），`git commit -m "feat: compose one web lifecycle and unified API contract"`；不stage旧operator guide或ledger。

### Task 7：根 providers、实例 transport 和不重放重连

Files：Create `src/so101_teleop/web/src/state/domain-runtime.ts`、`runtime-provider.tsx`、`domain-runtime.test.ts`、`runtime-provider.test.tsx`、`src/so101_teleop/web/src/api/instance-client.ts`、`instance-client.test.ts`；Modify `main.tsx`、`app.tsx`、`task-app.tsx`、`expert-validation-app.tsx`、`api/client.ts`、`api/task-client.ts`、`api/expert-validation-client.ts`、`state/expert-validation-store.ts`、`state/teleop-store.ts`及其测试。

本task同时Create `src/so101_teleop/web/src/api/qualification-view.ts`、`qualification-view.test.ts`，在Task9前交付单一纯view。`QualificationView`是Task6生成schema同名类型alias；`unknownQualification(selected_n: number, runtime_identity: string): QualificationView`返回UNKNOWN与BUDGET_PROVIDER_NOT_READY，`workerOption(view) -> { value: number; disabled: boolean; reason: string }`仅AVAILABLE且profile/approval非空时enabled。Task9只消费本模块，Task10修改真实数据映射，不再创建类型。

```ts
import { expect, test } from "vitest";
import { unknownQualification, workerOption } from "./qualification-view";
test.each([2,3,4,5,6,7,8])("unknown N%d stays disabled before provider integration", (n) => {
  const view=unknownQualification(n,"unqualified-R");
  expect(view.status).toBe("UNKNOWN");
  expect(workerOption(view)).toEqual({value:n,disabled:true,reason:"BUDGET_PROVIDER_NOT_READY"});
});
```

RED/GREEN：`bungate run test src/api/qualification-view.test.ts`；GREEN实现逐字段返回`{selected_n,status:'UNKNOWN',reasons:['BUDGET_PROVIDER_NOT_READY'],runtime_identity,contract_version:2,profile_sha256:null,approval_sha256:null}`，workerOption取view.selected_n，不降档。Task9完整build/全前端test必须在尚未执行Task10的checkout通过。

Interfaces：`DomainName = 'teleop' | 'validation'`，前端 `InstanceProof`、`ChannelBinding`、`ControllerAuthority`从Task6 unified-schema生成，不手写另一份DTO。新增 `RuntimeSnapshot { sequence: number; serviceEpoch: string; executionGeneration: number; payload: TelemetrySnapshot | CampaignProjection | null }`，payload使用现有 `api/types.ts` 与 `api/expert-validation-types.ts`。`DomainTransport`明确 `register(domain): Promise<InstanceProof>`、`connect(proof): Promise<ChannelBinding>`、`snapshot(): Promise<RuntimeSnapshot>`、`subscribe(handler: (s: RuntimeSnapshot) => void): () => void`、`renew(): Promise<void>`、`post(path: string, body: Record<string,unknown>, authority: ControllerAuthority): Promise<CommandResult | CampaignProjection>`、`close(): void`；现有domain client wrapper仍返回其具体typed request/results，不拿CommandResult替代campaign projection。`DomainRuntime(domain: DomainName, transport: DomainTransport)`的 `start(): Promise<void>`、`accept(event): Promise<void>`、`projection(): RuntimeSnapshot | null`、`dispose(): void`、`mutationHeaders(): HeadersInit`。`RuntimeProvider({ children, teleop, validation }: { children: ReactNode; teleop: DomainRuntime; validation: DomainRuntime })`持有整个app生命周期，Tasks共用teleop runtime。

- [ ] RED test使用完整小fake，实现所有上述transport方法：

```ts
import { expect, test, vi } from "vitest";
import { DomainRuntime, type DomainTransport, type RuntimeSnapshot } from "./domain-runtime";
import type { InstanceProof, ChannelBinding, ControllerAuthority } from "@/api/instance-client";

test("sequence gaps use snapshot and do not replay mutations", async () => {
  const snapshot: RuntimeSnapshot = { sequence: 8, serviceEpoch: "e1", executionGeneration: 1, payload: null };
    const transport: DomainTransport = {
    register: vi.fn(async () => ({ instance_id: "i1", proof: "p1", domain: "teleop" } as InstanceProof)),
    connect: vi.fn(async () => ({ instance_id: "i1", revision: 1, domain: "teleop" } as ChannelBinding)),
    snapshot: vi.fn(async () => snapshot), subscribe: vi.fn(() => () => undefined),
    renew: vi.fn(async () => undefined), post: vi.fn(async () => ({ code: "OK", succeeded: true })), close: vi.fn(),
  };
  const runtime = new DomainRuntime("teleop", transport);
  await runtime.start();
  await runtime.accept({ ...snapshot, sequence: 12 });
  expect(transport.snapshot).toHaveBeenCalledTimes(2);
  expect(runtime.projection()?.sequence).toBe(8);
  expect(transport.post).not.toHaveBeenCalled();
  runtime.dispose();
});
```

`ControllerAuthority`是生成 `RequestAuthority` view，对proof仅memory持有；client返回schema field保持snake_case，runtime映射snapshot字段明确，不用类型assert掩盖生产字段遗漏。测试fake的null payload只用于seq contract，另补真实TelemetrySnapshot/CampaignProjection fixture与reducer回归。

RED/GREEN，在W目录：`bungate run test src/state/domain-runtime.test.ts src/state/runtime-provider.test.tsx src/api/instance-client.test.ts src/api/client.test.ts src/api/expert-validation-client.test.ts src/state/expert-validation-store.test.ts`。

- [ ] 实现core：根只建两个runtime，route switch用History API更新page state而不卸载provider；只读register/connect不自动acquire。现有页面effect里的telemetry/renew迁入runtime并在真正root dispose才停止。validation续约更新lease generation，instance execution generation独立；proof不写storage。统一header来源逐请求提供四个authority headers，observe/gap先HTTPsnapshot，stale/duplicate ignore，epoch改变清执行许可和旧plan，buffer上限固定在配置并测试溢出snapshot。

```ts
if (event.serviceEpoch !== current.serviceEpoch || event.sequence > current.sequence + 1) {
  current = await transport.snapshot();
  return;
}
if (event.sequence <= current.sequence) return;
current = event;
```

真正传输还须按snapshot之后seq衔接event，不能丢掉合法连续事件；测试在snapshot in-flight时注入事件并证明有界buffer按revision/epoch排序。ExecuteAll client改为一次`/plans/{id}/execute-all`，HTTPtimeout查询parent，不自动第二POST。refresh/duplicate只读、新instance；same-document reconnect用memory proof/newchannel revision、snapshot完毕后才允许用户新操作；handoff明确确认，不自动抢权。
- [ ] provider测试用fake timers和真实两个route child：acquire后的10秒renew在切页/back仍进行，无第二register；关闭页面/epoch改变停止旧channel；两个document复制storage也无执行权（Task11服务器L2验证）；网络错误后post调用数不增加。原Tasks和Teleop共享实例但业务lease/session不混Validation。
- [ ] Scoped commit：stage本task所列完整新文件和existing前端文件（包括改动的对应tests），`git commit -m "feat: persist domain providers across navigation without command replay"`。

### Task 8：冻结官方 preset 和全套主题 smart merge

Files：Create `src/so101_teleop/web/design-system.lock.json`、`src/lib/design-system.test.ts`、`src/styles/theme.css`、`public/fonts/dm-sans-variable.woff2`、`outfit-variable.woff2`、`LICENSES.txt`；新增实际使用的 `src/components/ui/sidebar.tsx`、`sheet.tsx`、`field.tsx`、`select.tsx`、`input.tsx`、`label.tsx`；Modify `components.json`、`package.json`、`bun.lock`、`tailwind.config.ts`、`postcss.config.cjs`、`src/index.css`和既有12个primitives。

Interfaces：`design-system.lock.json`固定 `{ schema_version: 1, cli: { package: 'shadcn', version: '4.21.0' }, preset: 'b311momZs0', base: 'radix', decoded: {...}, registry: [{ name, url, sha256, package_versions }], fonts: [{ file, source_url, sha256, license }], tailwind: { from: '3.4.17', selected: string, compiler: string }, bun: string, node: string }`；selected等值必须来自冻结registry/lock与fresh工具版本，不允许空值或latest。当前已读取task缓存`shadcn/package.json`，版本4.21.0；不把缓存package的`^4.21.0`范围作为生产pin。

- [ ] RED主题测试可直接运行，无未定义helper：

```ts
import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
test("locks the requested full preset and retains independent Radix base", () => {
  const lock = JSON.parse(readFileSync(new URL("../../design-system.lock.json", import.meta.url), "utf8"));
  expect(lock.cli.version).toBe("4.21.0");
  expect(lock.preset).toBe("b311momZs0");
  expect(lock.base).toBe("radix");
  expect(lock.decoded).toMatchObject({ style: "maia", baseColor: "mist", theme: "blue", chartColor: "mist", iconLibrary: "lucide", font: "dm-sans", fontHeading: "outfit", radius: "large", menuAccent: "subtle", menuColor: "default" });
  expect(lock.registry.length).toBeGreaterThan(0);
  for (const entry of lock.registry) expect(entry.sha256).toMatch(/^[a-f0-9]{64}$/);
});
```

测试路径是`src/lib/design-system.test.ts`，其到W根应为`../../design-system.lock.json`。RED/GREEN：`bungate run test src/lib/design-system.test.ts`，RED缺lock file，不能用空registry骗GREEN。
- [ ] 在root下唯一`preset-preview-<uuid>`新目录用apply_patch创建最小Vite package/HTML/React入口及与本项目一致的TS别名，原产品未修改。经记录执行 `bunx shadcn@4.21.0 init -d --template vite --base radix --preset b311momZs0`（cwd为preview），然后 `bunx shadcn@4.21.0 add sidebar sheet field select input label badge card button alert-dialog tooltip separator tabs scroll-area --dry-run --diff`；保存全部stdout/stderr/exit、registry原JSON/URL/hash/依赖、字体source/license。CLIcommand先用该pin的`--help`证明确切flags；若不兼容失败closed，不能改用latest或对产品force。只有审核过预览后才在preview生成候选组件，不对产品运行overwrite/init-force。
- [ ] 锁定preset需要的真实dependency闭包。默认从TW3.4.17出发：registry若可用v3则保留其compiler并转换等价tokens；若要求v4，明确把`tailwindcss`/`@tailwindcss/postcss`与CSS入口作为一个受审兼容升级，一次锁精确版本。`design-system.lock`记录最终compiler版本和迁移理由，Bun frozen-lockfile/build/vitest全通过才合并，不同时遗留v3 directives和v4-only`@theme`。Node保持`>=24.18.1 <25`；删除未使用legacyRadix package仅在逐组件imports确认之后。
- [ ] 用apply_patch smart merge candidate与产品源码：foundation/card/input/sidebar/chart/lightdark全部semantic tokens；保留Button业务variants、ConfirmAction/disabled/ARIA/events/testids。字体自托管有license/hash与中文fallback，light默认/theme持久；success/pending/failure三色独立业务tokens。现有primitives明确12个：alert-dialog、badge、button、button-group、card、empty、scroll-area、separator、sonner、table、tabs、tooltip（以84620安装inventory核验，不偷偷add-all）。

```css
@font-face { font-family: "DM Sans"; src: url("/fonts/dm-sans-variable.woff2") format("woff2"); font-display: swap; }
@font-face { font-family: "Outfit"; src: url("/fonts/outfit-variable.woff2") format("woff2"); font-display: swap; }
body { font-family: "DM Sans", "PingFang SC", "Noto Sans CJK SC", system-ui, sans-serif; }
h1, h2 { font-family: "Outfit", "PingFang SC", system-ui, sans-serif; }
```

字体/tokens确切数值取冻结官方preset，不能把临时HTML色值当registry数据。显示字体离线失败不影响操作authority；补license/hash、light/dark有tokens、禁用原因/业务variant保留测试。
- [ ] GREEN：`bungate install --frozen-lockfile`、`bungate run build`、`bungate run test`；后两者不能只定向theme测试。Scoped commit仅stage以上配置、style/font与逐项reviewed components文件，`git commit -m "style: smart merge the pinned maia mist blue design system"`。保存unmerged业务diff与最终registry锁审查结果。

### Task 9：统一 shell 与两页真实业务布局

Files：Create `src/so101_teleop/web/src/components/unified/app-shell.tsx`、`app-shell.test.tsx`、`src/styles/unified-layout.css`；Modify `main.tsx`、`app.tsx`、`task-app.tsx`、`expert-validation-app.tsx`、`components/expert-validation/campaign-setup.tsx`、`campaign-progress.tsx`、`top-view-map.tsx`、`point-evidence.tsx`、`retry-panel.tsx`及原tests、全部 `components/teleop/` 页面布局组件（仅显示/props门控，业务handler不另实现）。

Interfaces：`AppShell({ page: 'teleop' | 'validation' | 'tasks', onNavigate(path: string): void, children: ReactNode })`；Evidence用现有artifact registry和generatedtype，不新增fakephoto端点；`TopViewMap`保留原Props与`TopViewManifest`，世界几何/points/projected_px不变，显示viewport-only envelope同一比例。`CampaignSetup`消费Task10的只读qualification view，N选择不写K，不把demo状态注入真实数据。

- [ ] RED map测试以已有fixture与真实TopViewMap为基础：

```tsx
// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import fixture from "@/fixtures/top_view_projection_v1.json";
import { TopViewMap } from "./top-view-map";
test("all business states keep the same marker radius and expose text", () => {
  const states = ["PASSED","EXECUTING","FAILED","INDETERMINATE"] as const;
  const { container } = render(<TopViewMap manifest={fixture} onSelect={() => undefined}
    campaign={{ points: fixture.points.map((p,i)=>({point_id:p.id,status:states[i%4]})) }} />);
  const markers = [...container.querySelectorAll<SVGCircleElement>("circle[data-point-status]")];
  expect(markers).toHaveLength(fixture.points.length);
  expect(new Set(markers.map(m=>m.getAttribute("r"))).size).toBe(1);
  expect(container.textContent).toContain("INDETERMINATE");
  expect(screen.getByRole("img",{name:"Expert validation top view"})).toHaveAttribute("preserveAspectRatio","xMidYMid meet");
});
```

若baseline已有radius通过，则RED放在新增`data-point-status`与可读状态文本/主题token期望，不能声称旧投影数学有bug。追加AppShell用户事件测试真实按钮切页不root重建、手机Sheet focus/close、Evidence缺missing image说明；fixture保持真实v1投影。

RED/GREEN：`bungate run test src/components/unified/app-shell.test.tsx src/components/expert-validation/top-view-map.test.tsx src/components/expert-validation/components.test.tsx src/components/teleop/joint-panel.test.tsx src/components/teleop/tcp-panel.test.tsx src/components/teleop/workflow-panel.test.tsx src/expert-validation-app.test.tsx`。

- [ ] layout核心：

```css
.validation-layout { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); gap: 1.25rem; }
.validation-map { min-width: 0; width: 100%; }
.validation-map svg { width: 100%; height: auto; max-width: none; }
.point-results { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem; }
@media (max-width: 1100px) { .point-results { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 760px) { .validation-layout { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 360px) { .point-results { grid-template-columns: minmax(0, 1fr); } }
```

左map按content envelope等比铺满，裁剪selection/labels不允许；SVG只改displayViewBox，`projectXY/projectBounds`和manifest的pixels_per_m/cupfootprint/target尺寸保持；markers用一致显示半径和真实状态icon/text，不回写manifest palette/history。Sidebar两主入口，Tasks兼容链接在Teleopworkflow区；全局占用banner和域readiness各自说明，safe cancel与owner验证保持可达。
- [ ] Teleop保留5个臂关节identifier1..5和gripper6、units/safe limits/stale plan/TCPframes、plan/execute/all/cancel、scene/collision/attachment、home/reset、camera/screenshot、parameters/YAML、workflow、physics/backend/events及Tasks sensors/pointcloud/evidence。更新每个组件semantic class/token与readonly prop，不增后端capability。`CONFIRM`和force-continue原文字与门控不变；缺backend支持不能把漂亮按钮启用。
- [ ] GREEN `bungate run build`、`bungate run test`。Scoped stage shell/layout和列出的业务组件实际diff及tests，`git commit -m "feat: apply the approved unified two-page layout with real geometry"`。

### Task 10：预算接口依赖 gate 与只消费 adapter

Files：Create `src/so101_teleop/so101_teleop/unified/budget_adapter.py`、`src/so101_teleop/test/teleop/test_unified_budget_adapter.py`；Modify `src/so101_teleop/web/src/api/qualification-view.ts`、`qualification-view.test.ts`、`src/so101_teleop/so101_teleop/unified/lifecycle.py`、`src/so101_teleop/so101_teleop/expert_validation/production.py`、`src/so101_teleop/web/src/components/expert-validation/campaign-setup.tsx`、CMake。

Interfaces：这是本Web消费view，不宣称budget provider已存在：`QualificationView(selected_n: int, status: Literal['AVAILABLE','UNKNOWN','REJECTED'], reasons: tuple[str,...], runtime_identity: str, contract_version: int, profile_sha256: str | None, approval_sha256: str | None)`；`BudgetAdapter.status(selected_n: int, *, runtime_identity: str) -> QualificationView`、`require_start(selected_n: int, *, runtime_identity: str) -> None`。`BudgetSource`是纯Protocol，其 `decision(selected_n: int, runtime_identity: str) -> QualificationView`必须由reviewed upstream adapter逐字段映射；AVAILABLE只能来自上游已验证operator promotion与live admission结果，approval_sha256必须是该已验证审计对象hash，不能客户端自填。真实集成前记录其module/path/signature/version/hash，不猜测上游函数名，也不以这个Web Protocol重定义它。

- [ ] 先检查独立预算task最终通过接口/清洁source commit/installed version。尚未交付时本task仅实现`UnavailableBudgetSource`返回UNKNOWN/BUDGET_PROVIDER_NOT_READY，contract/fake单测可完成，真实integration gate保持BLOCKED，不修改预算task工作树或冻结规范。接口交付后把真实映射作为本task独立RED/GREEN与reviewed补丁完成，再冻结R；不能在实测后补执行代码造成整套重测。
- [ ] RED code：

```python
import pytest
from so101_teleop.unified.budget_adapter import BudgetAdapter, QualificationView
from so101_teleop.unified.contracts import MutationError

class RejectedSource:
    def __init__(self): self.calls=[]
    def decision(self,selected_n,runtime_identity):
        self.calls.append((selected_n,runtime_identity))
        return QualificationView(selected_n,"REJECTED",("R_CHANGED",),runtime_identity,2,None,None)

def test_exact_n_never_downgrades_or_uses_cached_profile():
    source=RejectedSource()
    adapter=BudgetAdapter(source)
    assert adapter.status(8,runtime_identity="new-R").selected_n==8
    with pytest.raises(MutationError,match="R_CHANGED"):
        adapter.require_start(8,runtime_identity="new-R")
    assert source.calls==[(8,"new-R"),(8,"new-R")]
```

RED/GREEN：`pygate src/so101_teleop/test/teleop/test_unified_budget_adapter.py`；W `bungate run test src/api/qualification-view.test.ts`。

- [ ] minimal core `view=source.decision(selected_n,runtime_identity)`，require exactN/runtime/v2 match，再要求AVAILABLE、非空profilehash及production批准审计；unknown/rejected按reasons拒绝。capability/preflight/start同source/version且startfreshliveprobe，不信前端缓存。source exceptions变UNKNOWN明确原因，无formula或fallback。candidate测量只能消费upstream明确授权entrypoint，Webproduction没有bypass。
- [ ] frontend view mapN2..8每档资格/原因，`disabled=status!=='AVAILABLE'`，points4..20含4anchor；SEQ1和retryFULL_RESTART1独立qualification contexts沿用upstream。提交null/legacyK拒绝测试由预算最终契约驱动，本task不为旧schema补巨大K；v1只读和ADAPTIVE语义回归保留。
- [ ] 新R计算包括Web/bridge/subscription/thread/background footprint与安装执行bytes，禁止旧budget复用。profile候选测量→Sol结果review+Astra独审→operatorpromotion仍独立授权；数值未知不编造。Scoped commit adapter/view/测试及上述实际整合文件，`git commit -m "feat: consume exact worker qualification without budget bypasses"`。

### Task 11：完整构建、增量产物与 copied-install Chrome/fault验收

Files：Modify `src/so101_teleop/CMakeLists.txt`、`test/e2e/installed_test_launcher.py`、`web/e2e/expert-validation/fixtures/installed.ts`、`fixtures/config.ts`、`playwright.installed.config.ts`；Create `src/so101_teleop/test/test_unified_web_dependencies.py`、`test/e2e/unified_ports.py`、`web/e2e/unified/installed.spec.ts`；更新既有installed tests的authority握手，不新增production env测试开关。

Interfaces：`create_installed_test_app(*, install_prefix, evidence_root, execution_port, environment, static_dir=None, action_driver_factory=None, budget_source=None)`仅test source launcher新增leaf typed seam，生产入口没有driver选择CLI/env。ActionDriverFactory是`Callable[[], ActionDriver]`；test-owned child内构造BarrierActionDriver后注入copied-install真实ChildRuntime，其余生产代码不替换。HelperBudgetSource仅对L2 fixture资格返回测试view，不作真实N资格。完全删除HelperTeleopPort应用层替换；test source launcher仅替最内层driver，安装导入全部来自copied prefix。

launcher真实composition先bootstrap copied prefix，按`sys.version_info[:2]`发现site并与Task0精确3.12解释器匹配，拒绝symlink/editable/source模块；`compose_installed_test_services(*, install_prefix: Path, evidence_root: Path, execution_port: ExecutionPort, action_driver_factory: ActionDriverFactory, budget_source: BudgetSource, environment: dict[str,str]) -> UnifiedServices`定义在test/e2e/unified_ports.py。它只建立test-owned leaf-driver child/真实BridgeProcessOwner与BridgeWorkerPort，然后调用copied-install同一个compose_domain_services(..., validation_execution_port=execution_port)；该对象原样到create_production_service(..., execution_port=validation_execution_port)及ExpertValidationSupervisor._execution_port，不能丢弃、复制或重建。Validation只替既有最底层argv执行seam，Teleop只替ActionDriver；ProductionTeleopService/parent/admission/lease/safety/dualIPC/TaskService/Validation composer都不替换。验证so101_demo、so101_teleop、ProductionTeleopService、ChildRuntime、unified app/lifecycle、TaskService、Validation production模块origins全在copied prefix，helper只来自task-owned test source；缺依赖/Python site/approved underlay/provenance/v2配置，在listener之前失败。真实POST execute-all持有生产parent并穿越两IPC通道，实际driver goal日志与cancel terminal为判据；临时移除parent reservation或让production cancel走normal coordinator时L2必须RED。


Task11沿用现有installed_test_launcher.py创建的同一个HelperExecutionPort(python=sys.executable, helpers_dir=test/e2e/process_helpers, spec_path=args.spec)，原typed资格manifest检查不削弱。统一composition的source与copied-install测试均断言`services.validation.supervisor._execution_port is execution_port`，随后从真实Validation start/cancel路由产生owned helper进程，回读SupervisorStore中的owner/argv journal，argv须与该port针对同一CoordinatorStartRequest返回值相等；不是另一个测试service自行启动的进程。同时经真实Teleop execute-all/安全cancel到双IPC的BarrierActionDriver，保留生产模块copied-origin断言。为RED临时去掉compose_domain_services的execution_port透传，以上object-identity/owned-helper/L2测试必须失败且不能启动真实仿真；恢复GREEN后才提交。source命令`pygate src/so101_teleop/test/teleop/test_unified_api.py src/so101_teleop/test/teleop/test_unified_launch.py`；copied命令仍为本task完整`bungate run test:e2e:installed`，不只跑单route或schema fake。

- [ ] RED CMake依赖测试先静态断言，再真实incremental fixture：

```python
from pathlib import Path
def test_web_build_tracks_css_components_and_local_font_assets():
    cmake=(Path(__file__).parents[1]/"CMakeLists.txt").read_text()
    assert "${SO101_TELEOP_WEB_ROOT}/src/*.css" in cmake
    assert "${SO101_TELEOP_WEB_ROOT}/public/*" in cmake
    assert "components.json" in cmake
    assert "design-system.lock.json" in cmake
```

RED/GREEN：`pygate src/so101_teleop/test/test_unified_web_dependencies.py`，84620的真实CMake缺这些DEPENDS，预期断言失败。
- [ ] CMake `CONFIGURE_DEPENDS`收集TS/TSX/CSS、public fonts/assets；显式DEPENDS `web/index.html`、`components.json`、`design-system.lock.json`及compiler配置。若Task8迁到TW4，删掉不存在的旧config依赖并加入实际新config；所有新Python测试逐个 `so101_add_pytest_test`注册，`so101_unified_web_server.py`安装PROGRAMS列表，旧脚本delegate同module；不造setup.py/console_scripts。

```cmake
file(GLOB_RECURSE SO101_TELEOP_WEB_STYLES CONFIGURE_DEPENDS ${SO101_TELEOP_WEB_ROOT}/src/*.css)
file(GLOB_RECURSE SO101_TELEOP_WEB_PUBLIC CONFIGURE_DEPENDS ${SO101_TELEOP_WEB_ROOT}/public/*)
list(APPEND SO101_TELEOP_WEB_SOURCES
  ${SO101_TELEOP_WEB_STYLES} ${SO101_TELEOP_WEB_PUBLIC}
  ${SO101_TELEOP_WEB_ROOT}/index.html
  ${SO101_TELEOP_WEB_ROOT}/components.json
  ${SO101_TELEOP_WEB_ROOT}/design-system.lock.json)
```

真实incremental regression在taskroot独立fixture工作树/构建目录：先build记录dist SHA，仅改fixture CSS token再build要求bundle内容改变；仅换fixturefont bytes再build要求dist font SHA更新；仅改fixture components.json再build要求web command重跑。保留三次stdout/exit/mtime/hash；不touch实施source或真实runtime bytes。pytest集成test通过环境`SO101_TEST_WEB_FIXTURE`限定已登记fixture路径，其内部用`subprocess.run(["cmake","--build",str(build),"--target","so101_teleop_web"],check=True)`，不新建服务。静态断言不能替代这三项实际重建证明。
- [ ] Stage A Linux完整configure/build（只隔离development overlay）：

```zsh
source /opt/ros/jazzy/setup.zsh
cd "$TASK_WORKTREE"
source "$APPROVED_UNDERLAY/install/setup.zsh"
build_run=$(mktemp -d "$SO101_TASK_ROOT/build-XXXXXXXX")
"$TEST_PYTHON" "$GATE_SCRIPT" --root "$SO101_TASK_ROOT" --python "$TEST_PYTHON" -- \
  colcon --log-base "$build_run/colcon-log" build --build-base "$DEV_BUILD" --install-base "$DEV_INSTALL" \
    --packages-select so101_teleop --symlink-install --cmake-clean-cache --cmake-args -DBUILD_TESTING=ON \
    -DPython3_EXECUTABLE="$TEST_PYTHON" -DPYTHON_EXECUTABLE="$TEST_PYTHON"
source "$DEV_INSTALL/setup.zsh"
export CTEST_PLAN="$build_run/ctest.json"
ctest --test-dir "$DEV_BUILD/so101_teleop" --show-only=json-v1 > "$CTEST_PLAN"
"$TEST_PYTHON" - "$CTEST_PLAN" "$TEST_PYTHON" <<'PY'
import json, pathlib, re, sys
tests=json.loads(pathlib.Path(sys.argv[1]).read_text())["tests"]
required={"test_unified_"+n for n in (
    "gate","arbiter","instances","safety","ipc","bridge","parents","admission",
    "api","lifecycle","budget_adapter","web_dependencies","live_fixture","launch",
    "two_channel","cancel_integration")}
assert required <= {t["name"] for t in tests}, "MISSING_CTEST_REGISTRATION"
selected=pathlib.Path(sys.argv[2]).resolve()
for test in tests:
    if not test["name"].startswith("test_"): continue
    pythons={pathlib.Path(arg).resolve() for arg in test["command"]
             if re.fullmatch(r"python(?:\d+(?:\.\d+)*)?",pathlib.Path(arg).name)}
    assert pythons == {selected}, (test["name"], "ACTUAL_CTEST_PYTHON_MISMATCH", pythons)
print(json.dumps({"actual_test_python":str(selected),"registered_tests":len(tests)}))
PY
```

`APPROVED_UNDERLAY/DEV_BUILD/DEV_INSTALL`来自Task0明确记录的owned路径且不能为空，underlay未确认就阻塞；禁止默认canonical install。重新configure后检查16个新registration存在：gate、arbiter、instances、safety、ipc、bridge、two_channel、parents、admission、cancel_integration、api、lifecycle、budget_adapter、web_dependencies以及Task12定义的livefixture/launch合同测试；从CTest实际`command`读取每个test Python，并逐一用record_gate相同TEMP证明，不能只证明调用colcon的Python。如果注册使用多个Python，逐个证明或重新配置统一测试Python；任何一个tempfile不在本run已登记scratch内（ai-station必须NVMe）都不运行colcon test。

```zsh
test_run=$(mktemp -d "$SO101_TASK_ROOT/colcon-test-XXXXXXXX")
"$TEST_PYTHON" "$GATE_SCRIPT" --root "$SO101_TASK_ROOT" --python "$TEST_PYTHON" -- \
  colcon --log-base "$test_run/colcon-log" test --build-base "$DEV_BUILD" --install-base "$DEV_INSTALL" \
    --packages-select so101_teleop --event-handlers console_direct+
"$TEST_PYTHON" "$GATE_SCRIPT" --root "$SO101_TASK_ROOT" --python "$TEST_PYTHON" -- \
  colcon --log-base "$test_run/result-log" test-result --test-result-base "$DEV_BUILD" --verbose
```

mac不使用/data路径；ament_cmake gate从CTest发现实际Python/命令，在当前ROS zsh保持DYLD并证明import/bootstrap及非零收集，runner失败单列不当assert回归。ordinary demo gate为 `pygate src/so101_demo_py/test`，不收benchmark。
- [ ] source/unit/Bun gates全通过后，完成代码提交与clean HEAD，再构建non-symlink发布overlay到root下新路径并复制为immutable L2 prefix。记录Python/module/scripts/bundle/font hashes与installed origin；copied symlinks/sourceeditable finder失败closed，不污染canonical。新runtime/provenance binding按预算身份契约绑定fresh clean HEAD/install/R；tracked metadata commit后在下次spawn前追加新binding，旧sealed记录不改，选binding至spawn之间无tracked commit。

发布构建不是仅复制DEV_INSTALL的Teleop包。完整生成so101_demo_py（导出so101_demo）与so101_teleop的source dependency closure；/opt/ros/jazzy及approved underlay作为外部只读依赖逐项登记prefix/版本/hash，不能暗含canonical workspace source或editable模块。确切命令：

```zsh
cd "$TASK_WORKTREE"
release_run=$(mktemp -d "$SO101_TASK_ROOT/release-XXXXXXXX")
"$TEST_PYTHON" "$GATE_SCRIPT" --root "$SO101_TASK_ROOT" --python "$TEST_PYTHON" -- \
  colcon --log-base "$release_run/colcon-log" build --build-base "$release_run/build" \
    --install-base "$release_run/install" --packages-up-to so101_demo_py so101_teleop \
    --cmake-clean-cache --cmake-args -DBUILD_TESTING=ON \
    -DPython3_EXECUTABLE="$TEST_PYTHON" -DPYTHON_EXECUTABLE="$TEST_PYTHON"
COPIED_INSTALL="$release_run/copied-install"
test ! -e "$COPIED_INSTALL" || return 1
cp -a "$release_run/install" "$COPIED_INSTALL"
```

这是task-owned compiled-artifact transfer，不复制source。复制前后核对完整relative path/size/SHA256 inventory；L2 bootstrap验证so101_demo与纯生产Teleop所有模块origin在COPIED_INSTALL，缺任何包即阻塞，而不是从PYTHONPATH拾取补齐。source安装测试shell移除source prefixes后，只source该copied overlay和已登记外部underlay，追加精确Pydantic2 site，并记录AMENT_PREFIX_PATH/LD_LIBRARY_PATH/library/runtime-file映射。实际实时R和production发布binding必须按同样完整闭包重建审核，不能把development overlay当最终production artifact。
- [ ] installed launcher改compose真实unified factory，typed helper ports只在test source构造；fixture支持register/channel/lease/headers，ready记录epoch/pid/port/installed prefixes但redactproof。修改旧fixture移除自动证据删除（ready旧文件按generation新名保留），safe teardown先匹配test-owned process identity，不发foreignsignals。安装L2覆盖一个Weblistener/ROSfree导入、两页API、lease/instance/races/parentpause/cancel饱和/ACK丢失/child crash/Webrestart、artifact404/SPArefresh，无实际sim。

```zsh
cd src/so101_teleop/web
e2e_run=$(mktemp -d "$SO101_TASK_ROOT/chrome-installed-XXXXXXXX")
export SO101_E2E_EVIDENCE_ROOT="$e2e_run"
export SO101_E2E_INSTALL_PREFIX="$COPIED_INSTALL"
export SO101_E2E_PYTHON="$TEST_PYTHON"
bungate run test:e2e:installed
```

config testMatch加入`unified/installed.spec.ts`，system Chrome路径来自现有`fixtures/config.ts`（mac`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`，Linux`/usr/bin/google-chrome`或已核验override）。每次invoke新e2e目录，Bunstdout/stderr/exit归record_gate，Playwrightjson/trace/screenshots归该invoke；不可复用test root覆盖结果。
- [ ] Scoped commit：精确stageCMake/launcher/fixtures/config/test及actual updatedinstalled spec，`git commit -m "test: qualify unified installed assets and lifecycle fault boundaries"`。执行代码（包括Task12fixture变更）必须在Stage B测量前全部完成审查和冻结；不可先测后补helper/adapter改变R。

### Task 12：新 R gate、授权 live与运行指南

Files：Modify `src/so101_teleop/web/e2e/expert-validation/fixtures/live-sim.ts`、`live-sim-global-setup.ts`、`live-sim/01-sequential.spec.ts`、`02-parallel.spec.ts`、`03-adaptive.spec.ts`、`playwright.live-sim.config.ts`；Create `web/e2e/unified/live-sim.spec.ts`、`src/so101_teleop/test/teleop/test_unified_live_fixture.py`、`test_unified_launch.py`、`docs/guides/so101-unified-webapp-operation.md`；Modify CMake与现有Teleop guide仅追加兼容链接，旧预算guide/proposal不改。

Interfaces：livefixture继续要求 `SO101_ENABLE_LIVE_SIM_E2E=1`、fresh source commit/clean tree/provenance binding、`SO101_E2E_INSTALL_PREFIX`、`SO101_E2E_PYTHON`和host匹配；新增`SO101_UNIFIED_LIVE_AUTHORIZATION`是operator批准的非秘密JSON路径，包含scope、selected runtime identities、deadline、owned process规则、R/profile references，缺失/超时/identity不符即拒绝。不能仅靠env opt-in授予停已有服务或promotion。此JSON不持久化instance proof。

- [ ] Task12A：在Task11 configure之前先RED/GREEN source-backed fixture/launch测试（不运行live）：

```python
from pathlib import Path
def test_live_fixture_targets_one_unified_launcher_and_keeps_qualification_gate():
    package=Path(__file__).parents[2]
    fixture=(package/"web/e2e/expert-validation/fixtures/live-sim.ts").read_text()
    assert "so101_unified_web_server.py" in fixture
    assert "SO101_UNIFIED_LIVE_AUTHORIZATION" in fixture
    assert "SO101_VALIDATION_PROVENANCE_BINDING" in fixture
    assert "requireGate" in fixture
```

RED/GREEN：`pygate src/so101_teleop/test/teleop/test_unified_live_fixture.py src/so101_teleop/test/teleop/test_unified_launch.py`；launch test用`ast.parse`与installed PROGRAMS contract证明新入口、旧入口delegate和一个port配置。更强Vitest测试用现有livefixture injectable stackScan/hostname/env验证authorization缺失、expired/newR/foreignowner failclosed；不用source字符串测试冒充runtime。
- [ ] 完成live fixture所有执行代码，保留旧`QUALIFICATION_ENV`历史参考，真实production env改为预算最终批准v2 config/profile和fresh binding映射，不再用历史parallel aggregate授予新R。installed/current source/underlay/model/container/config/code/runtime-file/thread fingerprints均按budget契约确认。测试Python site追加在ROSoverlay之后并证明Pydantic2和actualmodule origins。代码/task checkpoint先commit，再生成最终immutable audit binding；guide后续commit同样刷新fresh binding，不改P/Q/M测量证据或旧授权。
- [ ] Stage B额外授权后，按独立预算计划测当前完整runtime R（含unified Web/ROS child/background footprint），每档exactN/20点/五normalrun与faultenvelope按其规则完成；该任务只读取其finalcandidate/review/promotion references，不启动测量或批准它。未知N禁用解释，所有N不强行PASS。promotion仍由operator另批。Stage B未通过时仅L2/页面只读交付，不能进入production start。
- [ ] Stage C fresh记录服务是否存在、为何停/谁拥有、最后checkpoint、同UIDprocess身份/ROSgraph/tmux/runtime环境；如果已有foreign/预算task服务，原live stackConflicts门控保持拒绝，等待明确窗口，不能删掉冲突检测或凭旧PID清理。计划执行授权不批准停它们。由operator确认owned替换流程后，`SO101_UNIFIED_LIVE_AUTHORIZATION`绑定精确owner、端口和profile；只通过一个新installedserver入口启动，no extra uvicorn。服务缺失也不能自动重建旧栈。
- [ ] 每次live Bun invoke创建新freshroot；同一次invoke内部01是R01 producer，先验证其fresh physical/provenance gate，再跑02和统一UI/races，不能只复制历史R01或直接02。一个invoke共享此root，报告不覆盖：

```zsh
cd src/so101_teleop/web
live_run=$(mktemp -d "$SO101_TASK_ROOT/chrome-live-XXXXXXXX")
export SO101_E2E_EVIDENCE_ROOT="$live_run"
export SO101_E2E_INSTALL_PREFIX="$PRODUCTION_INSTALL"
export SO101_E2E_PYTHON="$TEST_PYTHON"
export SO101_VALIDATION_PROVENANCE_BINDING="$FRESH_BINDING"
export SO101_ENABLE_LIVE_SIM_E2E=1
export SO101_UNIFIED_LIVE_AUTHORIZATION="$APPROVED_LIVE_AUTHORIZATION"
bungate run test:e2e:live-sim -- --project=parallel --project=unified
```

在12A明确配置四个projects：`sequential`的testMatch为`expert-validation/live-sim/01-sequential.spec.ts`；`parallel`为`expert-validation/live-sim/02-parallel.spec.ts`、`unified`为`unified/live-sim.spec.ts`、`adaptive`为`expert-validation/live-sim/03-adaptive.spec.ts`，后三者的dependencies均为`['sequential']`。workers1/retries0；各dependent开始前验证本invoke R01。全局setup先读authorization/binding/profile，再任何server/stack spawn。R01绑定本root当前source/install/R，错误阻塞02/unified。ADAPTIVE另一次freshroot运行`bungate run test:e2e:live-sim -- --project=adaptive`，不自动切换N。每个生产spawn前finish tracked metadata commits、freshclean HEAD/R/install与所选binding等价，无commitbetween select/spawn。
- [ ] live验收矩阵：

| 项 | 操作/证据与失败判据 |
| --- | --- |
| 单服务与路由 | 一个ownedPID/Webport、两页/ws/task API同源；directrefresh/switch/back不另起server、不丢任务；artifact错路径404。 |
| domain readiness | ROS缺失/child IPCcrash/Webrestart分别注入，HTTP历史仍可读；可能运动owner未知blocked、无autotakeover/sim/命令回放。 |
| authority/race | copiedlease两个Chrome context交替/并发mutation只有绑定instance；handoff/renew/channelrevision/session变化；旧客户端missingheaders拒绝。 |
| parent/safe cancel | armACK/terminal/gripper前竞争Validation，home/workflowpause占用不提前释放；普通队列饱和正确ownedarm/gripper cancel按deadline送达，accepted后未stop仍blocked，foreignaction不取消。 |
| UI/accessibility | 1400×900及390×844 nooverflow；60/40map等比/无crop、same radius、状态text/icon、多列results/Evidence缺图；lightdark/fontfallback/keyboard/focus/ARIA。 |
| 原workflow | joint1..5+gripper6/TCP/scene/attachment/physics/camera/YAML/parameters/Tasks按backendcapability原行为；计划≠执行≠物理成功。 |
| exact N | N2..8资格逐档解释；4..20含4固定，eligibleN实际完整启动，points<N部分idle不降N；retry FULL_RESTART N1独立batch；unknown档不能dispatch。 |
| 物理证据 | actualMuJoCo cup pose/contact/support、MoveItworld/attachedshadow与releaseepoch、controller/action/joint/TF前后及freshChrome/GUI截图分别核验；FAILED/infra/invalid不混算。全流程连续成功声明仍须五次VALID成功，资格five-run不是业务PASS。 |

GUI/desktop截图按gui-capture技能，浏览器按freshDOM/action/freshDOM，不让full-page stitching ghost驱动CSS修复。测试故障只施于task-ownedhelper/runtime；真实机械臂保持plan-only，未授权不进入硬件execute。
- [ ] 最后写英文README兼容说明（若涉及README）及中文guide使用humanizer-zh，guide固定单入口/lease实例/只读理由/安全cancel/explicitrecovery/provider资格与证据查询路径，明确无自动接管/降N。Astra/high独立guide审查后scopedcommit：`git add docs/guides/so101-unified-webapp-operation.md`及明确compat链接文件；`git commit -m "docs: explain unified webapp ownership and safe operation"`。guide/ledger提交不改变执行R时仍追加newmetadata binding/audit，旧sealed授权和证据不改。

## 最终自查与交接

### 精确 staging 清单

以下命令在`TASK_WORKTREE`根执行，仅用于对应任务GREEN/结果检查之后，随后执行该task已列出的commit命令。花括号是有限文件名展开，不是glob；先`git diff --check`、回读`git diff --cached --name-only`并与本清单逐项相等。不存在的新文件先完成本task，不用宽泛目录staging绕过；未改动的既有文件不会进入diff。新增追溯tests必须在对应task Files与清单追加其真实文件名后才stage。

```zsh
# 0
git add -- src/so101_teleop/test/e2e/record_gate.py src/so101_teleop/test/test_unified_gate.py src/so101_teleop/CMakeLists.txt
# 1
git add -- src/so101_teleop/so101_teleop/unified/{__init__,contracts,intent_store,arbiter}.py src/so101_teleop/test/teleop/test_unified_arbiter.py src/so101_teleop/CMakeLists.txt
# 2
git add -- src/so101_teleop/so101_teleop/unified/{instances,contracts}.py src/so101_teleop/test/teleop/test_unified_instances.py src/so101_teleop/CMakeLists.txt
# 3
git add -- src/so101_teleop/so101_teleop/unified/{goals,safety,contracts}.py src/so101_teleop/test/teleop/test_unified_safety.py src/so101_teleop/CMakeLists.txt
# 4
git add -- src/so101_teleop/so101_teleop/unified/{ipc,bridge,ros_child,child_runtime}.py src/so101_teleop/so101_teleop/server.py src/so101_teleop/test/teleop/test_unified_{ipc,bridge,two_channel}.py src/so101_teleop/test/e2e/unified_child_harness.py src/so101_teleop/CMakeLists.txt
# 5
git add -- src/so101_teleop/so101_teleop/unified/{parents,admission,teleop_service}.py src/so101_teleop/so101_teleop/{server,service,task_service}.py src/so101_teleop/so101_teleop/expert_validation/{service,production}.py src/so101_teleop/test/teleop/test_unified_{parents,admission}.py src/so101_teleop/CMakeLists.txt
# 6
git add -- src/so101_teleop/so101_teleop/unified/{ports,app,lifecycle,main,contracts}.py src/so101_teleop/so101_teleop/{api,main,openapi_export,service}.py src/so101_teleop/so101_teleop/expert_validation/{api,main}.py src/so101_teleop/scripts/so101_{unified_web,teleop,expert_validation}_server.py src/so101_teleop/launch/so101_teleop.launch.py src/so101_teleop/test/teleop/test_unified_{api,lifecycle}.py src/so101_teleop/test/teleop/test_openapi_export.py src/so101_teleop/CMakeLists.txt src/so101_teleop/web/package.json src/so101_teleop/so101_teleop/{openapi,expert_validation_openapi,unified_openapi}.json src/so101_teleop/web/src/api/{schema,expert-validation-schema,unified-schema}.d.ts src/so101_teleop/test/teleop/test_unified_cancel_integration.py src/so101_teleop/test/e2e/unified_child_harness.py
# 7
git add -- src/so101_teleop/web/src/state/{domain-runtime.ts,runtime-provider.tsx,domain-runtime.test.ts,runtime-provider.test.tsx,expert-validation-store.ts,expert-validation-store.test.ts,teleop-store.ts,teleop-store.test.ts} src/so101_teleop/web/src/api/{instance-client.ts,instance-client.test.ts,client.ts,client.test.ts,task-client.ts,task-client.test.ts,expert-validation-client.ts,expert-validation-client.test.ts} src/so101_teleop/web/src/{main,app,task-app,expert-validation-app}.tsx src/so101_teleop/web/src/api/{qualification-view.ts,qualification-view.test.ts}
# 8
git add -- src/so101_teleop/web/{design-system.lock.json,components.json,package.json,bun.lock,tailwind.config.ts,postcss.config.cjs} src/so101_teleop/web/src/lib/design-system.test.ts src/so101_teleop/web/src/styles/theme.css src/so101_teleop/web/src/index.css src/so101_teleop/web/public/fonts/{dm-sans-variable.woff2,outfit-variable.woff2,LICENSES.txt} src/so101_teleop/web/src/components/ui/{sidebar,sheet,field,select,input,label,alert-dialog,badge,button,button-group,card,empty,scroll-area,separator,sonner,table,tabs,tooltip}.tsx
# 9
git add -- src/so101_teleop/web/src/components/unified/{app-shell.tsx,app-shell.test.tsx} src/so101_teleop/web/src/styles/unified-layout.css src/so101_teleop/web/src/{main,app,task-app,expert-validation-app}.tsx src/so101_teleop/web/src/expert-validation-app.test.tsx src/so101_teleop/web/src/components/expert-validation/{campaign-setup,campaign-progress,top-view-map,point-evidence,retry-panel}.tsx src/so101_teleop/web/src/components/expert-validation/{components,top-view-map}.test.tsx src/so101_teleop/web/src/components/teleop/{connection-header,joint-panel,tcp-panel,collision-panel,workflow-panel,environment-panel,gazebo-panel,confirm-action,event-log,target-yaml-controls}.tsx src/so101_teleop/web/src/components/teleop/{connection-header,joint-panel,tcp-panel,collision-panel,workflow-panel,environment-panel,gazebo-panel}.test.tsx
# 10
git add -- src/so101_teleop/so101_teleop/unified/{budget_adapter,lifecycle}.py src/so101_teleop/so101_teleop/expert_validation/production.py src/so101_teleop/test/teleop/test_unified_budget_adapter.py src/so101_teleop/web/src/api/{qualification-view.ts,qualification-view.test.ts} src/so101_teleop/web/src/components/expert-validation/campaign-setup.tsx src/so101_teleop/CMakeLists.txt
# 12A（先于11；GREEN后commit -m "test: bind unified live fixtures to explicit authorization"）
git add -- src/so101_teleop/web/e2e/expert-validation/fixtures/{live-sim,live-sim-global-setup}.ts src/so101_teleop/web/e2e/expert-validation/live-sim/{01-sequential,02-parallel,03-adaptive}.spec.ts src/so101_teleop/web/playwright.live-sim.config.ts src/so101_teleop/web/e2e/unified/live-sim.spec.ts src/so101_teleop/test/teleop/test_unified_{live_fixture,launch}.py src/so101_teleop/CMakeLists.txt
# 11
git add -- src/so101_teleop/CMakeLists.txt src/so101_teleop/test/test_unified_web_dependencies.py src/so101_teleop/test/e2e/{installed_test_launcher,unified_ports}.py src/so101_teleop/web/e2e/expert-validation/fixtures/{installed,config}.ts src/so101_teleop/web/playwright.installed.config.ts src/so101_teleop/web/e2e/unified/installed.spec.ts src/so101_teleop/web/e2e/expert-validation/installed/support.ts src/so101_teleop/web/e2e/expert-validation/installed/{entry-and-campaign,process-lifecycle,lease-recovery,artifacts,api-contract,retry-queue}.spec.ts
# 12B/C文档（真实运行证据不进入产品Git）
git add -- docs/guides/so101-unified-webapp-operation.md
```

TW4兼容升级如新增`web/postcss.config.mjs`或删除旧compiler文件，Task8须在冻结registry gate具体确定文件名并把该实际新增文件列入Files/清单，旧tracked删除路径仍显式stage；否则保持当前真实v3配置清单。这个前置gate不能在测量后改变执行bytes。

| Spec章节 | 计划覆盖 |
| --- | --- |
| 1–2范围/基线/模型/授权 | 全局约束、Task0、12 |
| 3–4单服务/readiness/router/lifespan/schema | Tasks4、6、11、12 |
| 5/5.1根provider/实例/seq重连 | Tasks2、6、7、11、12 |
| 6/6.1全入口仲裁/父操作/pause | Tasks1、5、6、11、12 |
| 7/7.1IPC/owner/crash/safe cancel | Tasks3、4、5、11、12 |
| 8preset/实际TW3/完整smart merge | Tasks0、8、11 |
| 9真实布局/geometry/5+1/旧功能 | Tasks7、9、11、12 |
| 10exactN/upstream接口/新R | Tasks10、11、12 |
| 11–12验收/证据/审批 | 每task RED/GREEN与checkpoint、Tasks11–12 |

停止条件：依赖接口未交付、工具模型不可用、未知owner/不能证明cleanup、source/install/binding漂移、unsafeIPC或cancel未按期证实、registry/锁文件不能复现、新R未qualification/promotion、缺授权窗口。保留失败和partial证据，不扩大authority解锁。

交付分列代码/自动测试/L2安装/资源资格/live物理/视觉；每项附source/install/runtime/exit和证据。记录retained、archived、deletion candidates，未经授权不删除。设计/计划独审PASS不替代任何运行层PASS。此计划本轮冻结后交Astra独审，由用户批准后才派发dst实施。
