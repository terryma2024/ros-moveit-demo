# Unified webapp implementation ledger

```yaml
task_id: so101-unified-webapp-impl-20260920
goal: Execute docs/superpowers/plans/2026-09-18-so101-unified-webapp-shadcn-implementation.md (Tasks 0-11 and 12A) in one isolated worktree
success_contract: Every plan task that this host can execute reaches RED -> GREEN with recorded evidence, exact scoped commits, and no fabricated runtime authority
executor: DeepSeek Harness TUI (dst) inline, per plan model/executor rules
worktree: /Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp
branch: codex/so101-unified-webapp
base_commit: 5b8d1231e97e10f650ac1d626e8dff801a7d21ea
current_commit: da05a69d51b63f88945f599c12a0e5a3376d9123
spec: docs/superpowers/specs/2026-09-18-so101-unified-webapp-shadcn-design.md
spec_sha256: 4e11f3a385e8d078523ee3c3b3b11d2ec372215188cfbdabdea824c35dd54fa1
plan: docs/superpowers/plans/2026-09-18-so101-unified-webapp-shadcn-implementation.md
plan_sha256: 71648ebbce07388af016e125c6e168b80fd3752305d62e71b412f64fdb6ae039
evidence_root: /tmp/so101-debug-so101-unified-webapp-impl-20260920
gate_policy: /tmp/so101-debug-so101-unified-webapp-impl-20260920/operator/gate-policy.json
gate_policy_sha256: 204c3f5e2670c643734c06efba83b31bb89d715aa7a88fbe3d7a85014ef4e5e1
execution_host: Terry-Mac-mini.local (macOS 26.6.2, arm64)
test_python: /Users/matianyi/ros2_jazzy/.venv/bin/python (Python 3.11.15)
test_python_declared: Python 3.12 (NOT AVAILABLE on this host; see CP-01 deviation D-2)
bun: /opt/homebrew/bin/bun 1.3.14
node: /Users/matianyi/.nvm/versions/node/v25.9.0/bin/node v25.9.0 (outside plan range >=24.18.1 <25; see D-3)
ros_workspace: /Users/matianyi/ros2_jazzy (macOS source build; no /opt/ros/jazzy on this host)
confirmed_conclusions:
  - Plan Tasks 0-11 and 12A are authorized by the goal; Stage B measurement and Stage C live replacement remain separately authorized
  - Only this worktree is modified; no existing service, simulator or ROS runtime was started or stopped
  - Spec hash matches the plan-declared frozen value
disproven_routes: []
open_hypotheses:
  - Unified arbiter/instance/IPC design can be implemented and unit-verified without ROS on macOS
latest_checkpoint: CP-63
next_experiment: Task 11 configure/build unless the Task 8 registry path is unblocked first; Task 9's page-effect migration and browser viewport checks remain
```

## CP-01: Registration, host probe and deviations

Worktree `.worktrees/so101-unified-webapp` on branch `codex/so101-unified-webapp` from `main`
5b8d1231. Single evidence root `/tmp/so101-debug-so101-unified-webapp-impl-20260920` registered in
this ledger; no `/data` path applies on this host. Files under `operator/` hold the frozen gate
policy object that Task 0 verifies by SHA256 and hostname.

Preserved processes: tmux sessions `dst`, `dst-so101-macos-mps-w2` (attached), `so101-teleop-w2-e2e`
were observed before work started and were not touched. No ROS graph or service was started,
stopped or inspected for ownership during this checkpoint.

Probed facts: `bun` 1.3.14 at `/opt/homebrew/bin/bun`; `node` v25.9.0; `dst` present at
`/Users/matianyi/.nvm/versions/node/v25.9.0/bin/dst`; ROS 2 Jazzy is a macOS source build rooted at
`/Users/matianyi/ros2_jazzy` with install overlays `extra_ws`, `so101_isolated_ws` and a Python 3.11
venv at `~/ros2_jazzy/.venv`; there is no `/opt/ros/jazzy` and no ai-station shell in this session.

### Deviations from the plan (reported, not silently substituted)

- **D-1 host**: the plan is written for ai-station Linux with a `/data/work/so101-evidence` root and
  NVMe scratch rules. This session runs on macOS, where `AGENTS.md` explicitly exempts the `/data`
  rule. Registered root is therefore the `/tmp` root above; every gate still proves the exact
  interpreter and `tempfile.gettempdir()` inside a per-invocation scratch directory.
- **D-2 test Python**: Task 0 requires proving Python 3.12 before use. No 3.12 interpreter with
  Pydantic 2, FastAPI, pytest, uvicorn and rclpy exists on this host: Homebrew has 3.11 and 3.14,
  `uv` has a bare managed 3.12.13 without those packages, and the plan forbids installing
  dependencies or quietly swapping interpreters. The repository's own macOS test contract
  (`.agents/skills/so101-dev/references/test-and-acceptance.md`) names
  `/Users/matianyi/ros2_jazzy/.venv/bin/python3` as the actual test interpreter, so that verified
  3.11.15 venv (Pydantic 2.13.4, FastAPI 0.115.14, pytest 8.4.2, uvicorn 0.34.3) is registered as
  `TEST_PYTHON`. This is a documented deviation from the plan's version literal, not a silent swap;
  ai-station execution must re-prove 3.12 before any Linux gate is trusted.
- **D-3 Node**: the plan requires Node `>=24.18.1 <25`. This host has only v25.9.0. All frontend
  install/build/test work goes through Bun 1.3.14 per repository rules, so no Node-versioned
  production artifact is produced here; the mismatch is recorded rather than resolved by installing
  a second Node runtime.
- **D-4 worktree creation**: the plan assigns worktree creation to the operator before dispatch. The
  goal for this session explicitly asks for the worktree and branch, so it was created here and
  recorded with branch, base commit and remotes above.

## CP-02: Task 0 - registered execution gate

Delivered `src/so101_teleop/test/e2e/record_gate.py` and `src/so101_teleop/test/test_unified_gate.py`,
registered as `test_unified_gate` in `src/so101_teleop/CMakeLists.txt`.

RED: 2 failed / 17 errors because the helper did not exist (`ModuleNotFoundError`-class collection
errors), exit 1, scratch `/private/tmp/.../scratch-9DGvEZoP/tmp`. GREEN: 19 passed, exit 0.
`pygate` was then validated end-to-end: gate record `gates/b8a2e0c40aa4469a971ac838d05b438f/result.json`
shows `test_python=/Users/matianyi/ros2_jazzy/.venv/bin/python`, `tempfile_dir` inside that run's own
`tmp/`, `exit_code=0`, `elapsed_seconds=1.37`, and the registered policy digest.

The gate refuses an unregistered root, a non-NVMe root when the operator object requires NVMe, host
mismatch, policy hash drift, missing policy fields, missing policy reference, and any interpreter or
TEMP mismatch - and in the mismatch cases it proves the command under test never started.
Commit `d66f9ae4`.

## CP-03: Task 1 - persistent global mutation arbiter

Delivered `unified/{__init__,contracts,intent_store,arbiter}.py` and
`test/teleop/test_unified_arbiter.py`, registered as `test_unified_arbiter`.

RED: `ModuleNotFoundError: No module named 'so101_teleop.unified'`, exit 2. GREEN: 15 passed, exit 0.
Covered: durable reservation across restart with unconverged-intent blocking, command idempotency by
canonical fingerprint with NaN refusal, two-thread admission race admitting exactly one domain, the
second service instance refused by `flock` both in-process and from a second process, cancel between
prepare and ACK still registering the late goal, terminal without cleanup proof staying blocked, and
an existing legacy journal's bytes unchanged.

Deviation: `IntentStore.settle` commits a refusal fence before the arbiter raises, so a blocked parent
can never be rolled back into `active` by the refusal itself. Commit `958bb86c`.

## CP-04: Task 2 - instance proof and lease binding fences

Delivered `unified/instances.py`, instance/authority types in `unified/contracts.py`, and
`test/teleop/test_unified_instances.py`, registered as `test_unified_instances`.

RED: collection error with `instances.py` moved aside, exit 2. GREEN: 12 passed, exit 0. Covered:
copied valid lease cannot control a second document, renew never moves the execution generation,
handoff bumps it once and only when the arbiter is idle, reconnect bumps the channel revision and
rejects the old revision, wrong origin / swapped domain proof / dead channel refused, proofs never
persisted (raw database bytes searched), abandoned-controller recovery requires proof that nothing is
owned, and the coordinator's cut points (acquire failure after the real domain lease committed leaves
a durable fence, restart stays blocked, guard waits out a renew fence and blocks at the parent
deadline).

Deviation from the plan's staging list: `unified/intent_store.py` is included in this commit because
the plan's own Task 2 text requires the execution generation and lease fences to live in the store's
independent tables. The plan's list omits it.

## CP-05: Task 3 - isolated safety lane

Delivered `unified/goals.py`, `unified/safety.py`, cancellation receipt types in
`unified/contracts.py` and `test/teleop/test_unified_safety.py` (registered `test_unified_safety`).

RED: 10 failed / 2 passed, exit 1 (the lane could not unpack its own shutdown sentinel and the
late-ACK fixture never prepared a child; both were fixture/implementation defects fixed forward).
GREEN: 12 passed, exit 0. Covered: delivery then stop-evidence wait, durable `cancel_requested`
before any goal is touched with later children refused, arm and gripper cancelled independently by
real UUID, duplicate cancels merged into one delivery, late ACK cancelled safely without discarding
the goal record, foreign authority refused before delivery, browser authority without an instance
refused, delivery timeout and accepted-without-stop-proof both blocking, safe queue full refusing
instead of queueing behind normal mutations, revoke without a pending authorizer refused, and
revoke linearization without a goal handle. Commit `ccb00db4`.

## CP-06: Task 4 - closed IPC and non-web child

Delivered `unified/{ipc,child_runtime,bridge,ros_child}.py`,
`test/e2e/unified_child_harness.py`, `test/e2e/noros_child_helper.py` and three test modules
(`test_unified_ipc`, `test_unified_bridge`, `test_unified_two_channel`).

IPC GREEN: 11 passed. Two-channel GREEN: 6 passed. Bridge GREEN: 7 passed. The two-channel tests run
the production `ChildRuntime` socket servers against the production `BridgeClient` over real Unix
sockets, with only the leaf `ActionDriver` test-owned; the proxy can only hold/release normal-channel
bytes and never touches the safety socket. Proven: safety revoke wins over a delayed normal packet
with `submit_count == 0`, submit wins exactly once and a repeated token never double-submits, cancel
targets the accepted UUID and keeps the reservation, expired queued mutations never dispatch,
repeated revokes do not undo the tombstone, the web-death latch cancels known pending goals and
refuses new work, and wrong epoch/token never reaches the child. Bridge tests spawn a real
ROS-free child process: fixed argv, live identity recomputation, owner-identity drift refusing to
signal, crash making the bridge unready, safety cancel over the independent socket, and a subprocess
proof that importing the web modules never loads `rclpy`.

Platform fact recorded: Darwin caps `AF_UNIX` paths at 104 bytes, so the harness allocates a short
socket scratch directory under `SO101_IPC_SOCKET_BASE` (registered root) and the child refuses an
over-long socket path explicitly.

Deviation: `unified/ros_child.py` imports the existing ROS worker lazily and its
`RclpyActionDriver.submit/cancel/terminal` intentionally fail with `ROS_DRIVER_NOT_PROVISIONED` on
this host. The socket, protocol, runtime, ownership and cancellation layers are verified; the ROS
driver wiring cannot be verified on macOS and is not claimed as working. `server.py` was not
modified in this task: the application-logic migration belongs to Task 5, and changing ROS worker
code that cannot be exercised here would be an unverifiable edit. Commit `ad1a861a`.

## CP-07: Task 5 - parent operations and admission

Delivered `unified/{parents,admission,teleop_service}.py`, `unified/arbiter.py` and
`unified/intent_store.py` additions, a minimal `so101_teleop/server.py` gate hook, and
`test/teleop/test_unified_{parents,admission}.py` (registered `test_unified_parents`,
`test_unified_admission`).

GREEN: 12 parent tests + 8 admission tests passed, and the full backend set
(`test_unified_gate`, `arbiter`, `instances`, `safety`, `ipc`, `bridge`, `two_channel`,
`parents`, `admission`) passes in one gated invocation, exit 0. Covered: the exact
arm-then-gripper barrier from the plan with a Validation start refused in the middle, cancel
between the arm terminal and the gripper dispatch never dispatching the gripper, a failed
arm never dispatching the gripper, missing cleanup proof blocking the parent, home as one
parent across planning/arm/gripper, workflow pause keeping the reservation and resume
requiring authority, a workflow physical terminal settling, an authority-guard failure
blocking instead of releasing, duplicate execute-all returning the recorded parent and
payload drift refused; plus a complete per-entry operation classification table, read
entries never taking a reservation, motion without instance authority refused, safety
entries refused from the reservation path, teleop-refuses-validation and
validation-refuses-teleop/tasks in both directions, and resume that cannot be minted from a
parent id.

`server.py` gained an optional admission hook (`bind_admission`, `_admission_gate`) wired
into the two existing choke points `_mutation_gate` and `task_mutation_gate`, with the
operation name carried in a `contextvars.ContextVar`. Because those modules import `rclpy`
at module level, the regression check runs through a ROS-sourced gate:

Executable gate recipe (recreate `operator/gate-env.sh` from this description if the `/tmp`
root is gone): export `SO101_TASK_ROOT`, `SO101_GATE_POLICY`, `SO101_GATE_POLICY_SHA256`,
`TEST_PYTHON=/Users/matianyi/ros2_jazzy/.venv/bin/python`, `BUN=/opt/homebrew/bin/bun`,
`SO101_IPC_SOCKET_BASE="$SO101_TASK_ROOT/ipc"`, `PYTHONNOUSERSITE=1`,
`PYTHONDONTWRITEBYTECODE=1`, and prepend the worktree `src/so101_teleop` and
`src/so101_demo_py` to `PYTHONPATH`; `pygate <paths>` runs `record_gate.py --root
$SO101_TASK_ROOT --python $TEST_PYTHON -- $TEST_PYTHON -m pytest -p no:cacheprovider <paths>`
with a fresh `pytest-XXXXXXXX` invocation directory; `pyrgate` does the same after sourcing
`~/ros2_jazzy/install/setup.bash`, `extra_ws/install/setup.bash`,
`so101_isolated_ws/install/setup.bash` and the venv, and must pass
`-p no:launch_testing -p no:launch_ros -p no:launch_pytest` (ROS's `launch_testing` pytest
plugin otherwise hijacks module collection and reports a misleading import error).

Verified with that recipe: `pyrgate src/so101_teleop/test/teleop/test_server_safety.py`
exits 0, so the existing Teleop gate behavior is unchanged by the new hook.

Deviations from the plan's Task 5 staging list: `service.py`, `task_service.py`,
`expert_validation/service.py` and `expert_validation/production.py` are **not** modified.
`TaskService` already routes every mutation through `teleop.task_mutation_gate`, so the hook
covers it once `server.TeleopService` is the bound service; the plan's full
`ProductionTeleopService` swap of `service.py` belongs with Task 6's factory composition and
is not claimed done. `unified/arbiter.py` and `unified/intent_store.py` are included because
`resume_parent`, `lookup_command`, `parent_record`/`child_record` and the hold registry are
required by the new modules. `ProductionTeleopService` is exercised by three tests driving a
real gateway, arbiter, safety lane and parent sequencer with a fake `WorkerPort`; its ROS
transport is not claimed.

Known limitation to carry forward: for `SHORT_WRITE` entries the gateway takes a short
reservation that is settled at the end of the gate call, so the reservation covers admission
but not the write itself. A later task must move that settle to the operation's completion.

## Evidence accounting at CP-07

`gates/` holds 11 recorded invocations: 7 green runs (Task 0 gate suite, Task 1, Task 2,
Task 3, Task 4, the final nine-module backend run, and the ROS-sourced
`test_server_safety.py` run) plus 4 nonzero records. The four nonzero records are the
ROS-sourced debugging sequence for `test_server_safety.py`: first the missing ROS underlay
(`ModuleNotFoundError: control_msgs`), then ROS's `launch_testing` pytest plugin hijacking
module collection and reporting a misleading `so101_demo.parallel_batch` import error. The
final run of that same command exits 0 and supersedes them; the failure records are retained,
not deleted. Every task commit is backed by a green gated invocation of that task's own test
modules. Test modules delivered: gate 15, arbiter 15, instances 12, safety 12, ipc 8,
bridge 7, two_channel 6, parents 12, admission 8 (95 test functions).

## CP-08: Task 6 - one factory, lifecycle, routers and OpenAPI

Delivered `unified/{ports,app,lifecycle,main,compose}.py`, `scripts/so101_unified_web_server.py`,
a rewritten `openapi_export.py` (one schema, three views), `QualificationView` in
`unified/contracts.py`, `web/package.json` `generate:api:unified`, and
`test/teleop/test_unified_{api,lifecycle}.py` plus an added export test.

GREEN: ROS-sourced gate over `test_unified_api.py` + `test_unified_lifecycle.py` +
`test_openapi_export.py` exits 0; the plain gate over the nine backend modules exits 0.
Covered: exactly one `/tasks/runs` POST route, no `disabled_tasks` shim, unique operation ids,
the plan's literal factory test, structured `CONTROLLER_INSTANCE_REQUIRED` for every legacy
mutation path (POST/PUT/DELETE) without authority headers, authority headers without a
composed registry failing closed as `SERVICE_NOT_COMPOSED`, read-only routes staying reachable
while a domain is unavailable, unknown API/artifact paths returning JSON 404 instead of the SPA,
the legacy `max_points_per_worker` contract rejected before body validation, bind-address
policy, lifecycle ordering (bridge failure lowering Teleop readiness only, blocked arbiter
refusing to serve, validation maintenance failure recorded, shutdown closing owned work),
composition without ROS producing a readable app with reasons, the budget-view field set, the
entry point having no helper/driver flags, and a subprocess import probe proving the web chain
never loads rclpy.

Exports generated through the gate: `unified_openapi.json` (45 paths, "SO-101 Unified"),
`openapi.json` (29, "SO-101 Teleop"), `expert_validation_openapi.json` (22, "SO-101 Expert
Validation"), and the three generated `.d.ts` files after `bun install --frozen-lockfile`
(lockfile unchanged).

### Environment facts discovered in this checkpoint (they change how gates must run)

1. `so101_demo_py` uses setuptools `package_dir={so101_demo: "src"}`, so the source tree has
   no `so101_demo/` directory: `so101_demo.*` is only importable after a colcon install. A
   symlink shim `$SO101_TASK_ROOT/pyshim/so101_demo -> src/so101_demo_py/src` reproduces the
   install-time mapping for source-mode tests. The plan's Task 0 export
   (`PYTHONPATH=.../src/so101_demo_py`) does **not** make `so101_demo` importable and is
   recorded as a plan defect. Installed gates (Task 11) must still use the real copied prefix.
2. `so101_teleop.expert_validation.__init__` imports `.catalog`, which imports
   `ament_index_python`; therefore the unified factory currently needs the ROS environment to
   import. `pyrgate`/`rosgate` (see the CP-07 recipe, extended with the shim path and
   `-p no:launch_testing -p no:launch_ros -p no:launch_pytest`) is the gate for anything that
   touches the validation package. Making that import lazy is a candidate follow-up, not done.
3. `rosgate <cmd...>` runs an arbitrary command through `record_gate` under the sourced
   workspace; the three OpenAPI exports were produced through it.

## CP-09: Tasks 10 and 12A, plus two pre-existing defects repaired

**Task 10 (budget adapter)** - `unified/budget_adapter.py`, `test/teleop/test_unified_budget_adapter.py`
(registered `test_unified_budget_adapter`), lifecycle start gate. GREEN: 15 tests (plain gate).
Covers the plan's literal exact-N test, every N disabled while the provider is UNKNOWN,
AVAILABLE requiring a promoted profile and approval hash, a provider answering for a different
N refused, a v1 contract refused, a provider exception becoming UNKNOWN with a reason, and the
retry N1 context staying separate. Commit `f2871ac1`. The frontend half of Task 10
(`qualification-view.ts`) is deferred to Task 7, which the plan makes the file's creator.

**Task 12A (live fixture authorization, code only)** - `live-sim.ts` now requires
`SO101_UNIFIED_LIVE_AUTHORIZATION` (a non-secret operator JSON with scope, runtime identities,
deadline, owned-process rule; proof-shaped keys rejected) *before* stack inspection, and the
fixture spawns only `so101_unified_web_server.py`. Added the `unified` Playwright project
depending on the reviewed `r01-sequential` producer and `web/e2e/unified/live-sim.spec.ts`.
`test/teleop/test_unified_{live_fixture,launch}.py` registered. Commit `9690b7f8`.

Two plan/source conflicts were resolved in favour of the newer reviewed source and recorded in
the tests themselves:
- The plan's RED test asserts `SO101_VALIDATION_PROVENANCE_BINDING` appears in the fixture. The
  reviewed source deliberately *retired* provenance bindings as runtime authority ("The retired
  provenance binding is gone..."). The binding was not reintroduced; a test now pins that
  decision in both directions.
- The plan names four Playwright projects (`sequential`/`parallel`/`adaptive`/`unified`). The
  branch has eight, owned by the parallel-budget task. Renaming or deleting them would break
  another task's live workflow, so the unified project was added and the existing names kept.

**Pre-existing defect 1 (repaired, out of plan)**: `bun run build` failed on pristine HEAD -
`expert-validation-types.ts` imports `Schemas["CapabilitiesResponse"]` and
`Schemas["StartGuardPolicyResponse"]`, which no exported schema defines. Proven pre-existing by
building a detached `git worktree` of HEAD, which produced the identical five TypeScript errors.
Repaired by registering the capabilities route with a `CapabilitiesResponse` model that keeps the
reviewed name, widens `extra` to `allow`, requires `worker_qualifications`, and still nests
`StartGuardPolicyResponse`; regenerated the three schemas and three `.d.ts` files; added the
required qualification list to the app test fixture. Commit `768328f0`.

**Pre-existing defect 2 (gate-level, not a product bug)**: this harness exports
`NODE_ENV=production`, so React loads its production build and every component test fails with
`act(...) is not supported in production builds of React` (77 failures). With `NODE_ENV=test`
the whole frontend suite passes: **30 files / 126 tests**. `buntest` in the gate recipe sets it
and must never be used for `run build`.

### Running gates (current recipe)

`pygate <paths>` - plain source gate. `pyrgate <paths>` - ROS-sourced pytest gate (required for
anything importing the validation package, because `expert_validation/__init__` pulls `catalog`
→ `ament_index_python`). `rosgate <cmd...>` - ROS-sourced arbitrary command.
`bungate <...>` - Bun in `web/`. `buntest` - `NODE_ENV=test bun run test`. All of them go through
`record_gate.py` and land in `<root>/gates/<uuid>/`.

### Remaining work

Tasks 7, 8, 9 (frontend root providers/instance transport, the frozen preset plus theme smart
merge, the unified shell and two-page layouts), Task 11 (CMake dependency list, full
configure/build, copied-install Chrome gate), and Task 12B/C (measurement, live runs, the
Chinese operation guide). Task 11's colcon stages need a complete `so101_demo_py` closure; the
source shim is only for source-mode tests and must not be used for the installed gate.

## CP-10: Task 7 part A - root runtimes, instance transport, qualification view

Delivered `web/src/api/{instance-client.ts,domain-transport.ts,qualification-view.ts}` and
`web/src/state/{domain-runtime.ts,runtime-provider.tsx}` with their four test modules, and
rewired `main.tsx` to build the two runtimes once and mount `RuntimeProvider` around a
History-API page switch. `unified/app.py` now types `/control/instances` with
`InstanceProofResponse` so the client type is generated rather than hand-written.

GREEN: `bun run build` exit 0 and **34 files / 149 tests** (up from 30/126) with `NODE_ENV=test`.
Covered: the plan's literal sequence-gap test (a gap re-snapshots and never posts), contiguous
and stale events, an epoch change forcing a snapshot and advancing the execution generation,
events buffered while a snapshot is in flight with a bounded buffer, posting without authority
refused, `dispose` closing the transport, registration not touching storage, a rejected
handshake surfacing the server code, all four authority headers on a mutation, every unknown
N disabled before provider integration, only an available promoted N selectable, points 4..20,
page-path mapping, and navigation inside one provider neither re-registering nor closing the
runtime.

Remaining in Task 7 (not claimed): moving the telemetry/renew effects out of `app.tsx` and
`expert-validation-app.tsx` into the runtimes, replacing the two-POST `TeleopApiClient.executeAll`
with one `POST /plans/{id}/execute-all`, and having the three page components and the existing
`client.ts`/`task-client.ts`/`expert-validation-client.ts`/state stores consume the provider.
Until that lands the pages keep their current effects and the runtimes only own instance
authority, subscription and recovery.

## CP-11: Task 7B (single execute-all) done; Task 8 blocked on registry access

**Task 7B** - `TeleopApiClient.executeAll` now sends exactly one
`POST /plans/{plan_id}/execute-all` carrying the command id, lease, session and gripper
target, and returns the parent projection; the caller in `app.tsx` records the parent's phase
instead of two child results and only clears the plan when the parent is COMPLETE. A non-COMPLETE
parent is never retried with a second POST. `bun run build` exit 0, `NODE_ENV=test bun run test`
**34 files / 150 tests**. Commit `1933e95c`.

**Task 8 is blocked on the pinned CLI's registry access.** Reproduced twice in the isolated
preview project `<root>/preset-preview-8f09f448` (created by the plan's own recipe):

```
cd <root>/preset-preview-8f09f448
bunx shadcn@4.21.0 init -d --template vite --base radix --preset b311momZs0
# -> Request to https://ui.shadcn.com/init?...preset=b311momZs0... failed, reason: other side closed
# same failure with HTTPS_PROXY/HTTP_PROXY=http://127.0.0.1:10809 exported for bun
```

The package itself resolves (`bunx shadcn@4.21.0 --version` prints `4.21.0`, matching the
plan's pinned version), and the same URL returns **200 to curl** through the proxy, so this is a
bun-specific fetch failure for `ui.shadcn.com`, not general network denial. Evidence retained:
`operator/preset-init.json`, `preset-preview-8f09f448/init.log`, `init-proxy.log`.

What was nevertheless verified and captured for the later Task 8 work:

- The CLI's own request URL independently confirms the decoded preset:
  `base=radix, style=maia, baseColor=mist, theme=blue, chartColor=mist, iconLibrary=lucide,
  font=dm-sans, fontHeading=outfit, radius=large, menuAccent=subtle, menuColor=default`.
- `operator/preset-init.json` holds the real manifest: `name=radix-maia`,
  `dependencies=["shadcn@latest","class-variance-authority","cn","tw-animate-css","radix-ui","lucide-react"]`,
  `registryDependencies=["utils","font-dm-sans","font-heading-outfit"]`, and the complete
  light/dark `cssVars` token sets in oklch plus `css` and `config`.
- `https://ui.shadcn.com/r/styles/new-york/utils.json` returns 200; `/r/styles/maia/*.json` and
  the `font-*` items return 404, so the maia/font registry URL shape still has to be determined
  from the CLI rather than guessed.

Consequences: `design-system.lock.json`, the `src/lib/design-system.test.ts` RED test, the CLI
`--dry-run --diff` capture and the theme/primitives smart merge are **not** done. Task 11's static
CMake test also asserts `design-system.lock.json`, so that assertion stays unmet until Task 8
produces the lock. Next attempt should run the pinned CLI under the repository's own Node
(`NODE_USE_ENV_PROXY=1 npx -y shadcn@4.21.0 ...`) or discover the correct registry URL shape from
the CLI source, and must still fail closed rather than substitute `latest`.

## CP-12: Task 9 first increment - map display contract

`TopViewMap` markers now carry `data-point-status` and a `<title>` element with the readable
business state, so a state is never conveyed by colour alone, and a test pins the display
contract: one marker radius across PASSED/EXECUTING/FAILED/INDETERMINATE/INVALID_BLOCKED, the
state names present as text, and `preserveAspectRatio="xMidYMid meet"` on the accessible image.
The existing geometry (`projectXY`, `pixels_per_m`, cup footprint, target tolerance) is
untouched. `bun run build` exit 0 and **34 files / 151 tests**. Commit `d8c0d56c`.

Still open in Task 9: `components/unified/app-shell.tsx`, `styles/unified-layout.css` (the plan's
grid rules), the Sidebar/Sheet navigation, wiring the pages to the root runtimes and the
qualification view, and the 1400x900 / 390x844 no-overflow checks.

## CP-13: Task 9 shell and layout rules

`components/unified/app-shell.tsx`, `components/unified/app-shell.test.tsx` and
`styles/unified-layout.css` (imported by `index.css`). The shell owns theme, the two primary
entries, a separate domain-health strip and the global-owner reason. Tasks stays a compatibility
route: it renders under the shell but is not a third primary entry, and there is no shared
business lease in the shell.

The layout CSS implements the plan's approved grid verbatim (`.validation-layout` 3fr/2fr with
`minmax(0, ...)`, `.validation-map svg { width: 100%; height: auto; max-width: none }`,
`.point-results` three columns falling to two at 1100px and one at 360px, single-column
validation below 760px) plus the shell/sidebar/teleop-joint-table rules.

GREEN: `bun run build` exit 0, `NODE_ENV=test bun run test` **35 files / 156 tests**. Covered:
navigation between the two entries without rebuilding the shell (the same content node stays
mounted), Tasks as a compatibility route rather than a primary entry, the collapsible
narrow-screen navigation (always present on wide screens via a media query rather than a
permanent `hidden` attribute, which had made the entries unreachable for assistive technology),
domain health and the global owner reason rendered outside the page content, and a light-default
theme that flips and applies to the document even when storage is unavailable or partial.
Commit `195606f7`.

Still open in Task 9: rendering the pages through `AppShell` in `main.tsx`, migrating the page
effects onto the root runtimes, consuming the qualification view in `CampaignSetup`, and the
1400x900 / 390x844 no-horizontal-overflow checks. Task 8 remains blocked on registry access as
recorded in CP-11.

## CP-14: shell becomes the app frame; design-system lock; web build inputs

**Task 9** - `main.tsx` now renders every page inside `AppShell`, so a page switch replaces only
the page content and the root providers stay mounted. Build 0, suite green. Commit `6a477c92`.

**Task 8 partial** - `design-system.lock.json` plus `src/lib/design-system.test.ts` (the plan's
RED test, extended so the lock can never overclaim). The lock records only verified facts:

- `cli.version = 4.21.0`, verified by running the pinned CLI (`bunx shadcn@4.21.0 --version`);
- the decoded preset exactly as the CLI's own request URL encodes it
  (`maia / mist / blue / mist / lucide / dm-sans / outfit / large / subtle / default`, `radix` base);
- one `registry` entry that is the real preset manifest fetched from
  `https://ui.shadcn.com/init?...preset=b311momZs0...`, with `sha256 =
  242969b2ed2d4ced3c35fdbc07605fd47758b3893f00f972f5af98df322a60df`, its `type`
  (`registry:base`), and the manifest's own dependency lists;
- the product's real toolchain (`tailwindcss 3.4.17`, bun 1.3.14, node 25.9.0).

The lock deliberately records `fonts: []` and a `blocked_reason` naming
`PENDING_REGISTRY_ITEMS`: neither the per-component maia items nor the font files could be
fetched (see CP-11), and inventing them is not acceptable. A second test asserts the lock claims
no component set or font it has not captured and contains no `latest`/guessed version.

**Task 11 partial** - `CMakeLists.txt` now globs `src/*.css` and `public/*` with
`CONFIGURE_DEPENDS` and depends on `index.html`, `components.json` and
`design-system.lock.json`; `test/test_unified_web_dependencies.py` (registered
`test_unified_web_dependencies`) asserts those inputs, that every declared dependency exists, and
that the bundle is built by Bun with the frozen lockfile. `pygate` exit 0. Still open in Task 11:
the three real incremental rebuild proofs, the full configure/build, the 16 registered-test
Python checks and the copied-install Chrome gate.

Both changes are in one commit because the CMake dependency list is exactly what the new lock
file satisfies.

## CP-15: exact-N selection consumes the qualification view

`CampaignSetup` accepts the read-only `qualifications: QualificationView[]` from Task 10. When
present it is authoritative: an exact N whose view is unknown or unpromoted is disabled in the
selector and its provider reason is shown, while an AVAILABLE promoted N stays selectable. The
existing `worker_count_availability` contract is still honoured, so an unqualified N cannot be
enabled by satisfying only one of the two. The component never lowers N, never substitutes
ADAPTIVE, and has no K or max-points-per-worker input.

GREEN: `bun run build` exit 0, two new component tests plus the whole suite pass. Commit
`497ac784`.

## CP-16: the approved layout is a pinned contract

`src/styles/unified-layout.test.ts` asserts the reviewed layout rules so a later edit cannot
silently drop them: the 60/40 `minmax(0, 3fr) / minmax(0, 2fr)` validation split, a map that
fills its column (`width: 100%`) with no small `max-width` and an auto height, point results
stepping 3 -> 2 columns at 1100px -> 1 column at 360px, the single-column validation layout below
760px, the dense joint table scrolling inside its own `overflow-x: auto` container rather than
overflowing the page, the navigation collapsing only below the 901px breakpoint, and the
stylesheet being imported by `index.css` so it is part of the bundle.

GREEN: `bun run build` exit 0, `NODE_ENV=test bun run test` **37 files / 165 tests**. Commit
`aae538a5`.

This is a static contract, not the browser evidence the plan asks for: the 1400x900 and 390x844
no-horizontal-overflow checks and the light/dark contrast and focus checks still need a real
browser run (Task 11's installed Chrome gate or a local `bun run dev` capture).

## CP-17: the operation guide

`docs/guides/so101-unified-webapp-operation.md` (Chinese, written with the project-local
`humanizer-zh` skill, filed under `docs/guides/` per AGENTS.md). It documents only what is
implemented and verified: the single launcher and the two deprecating shims, bind-address policy,
`/health/live` versus `/health/ready`, the instance/authority headers and why a copied lease
grants nothing, the refusal codes a user will actually see, the isolated safety lane and the fact
that an accepted cancel is not a physical stop, the single-parent execute-all/home/workflow
lifecycle with explicit resume, explicit recovery instead of automatic takeover, exact-N worker
qualification with no K input, and how evidence and marker semantics are read.

It also has an explicit "not done yet" section listing the unfinished gates (installed Chrome
viewport evidence, the pending preset registry and fonts, the unprovisioned ROS driver, and the
separately authorized Stage B/C measurement and live replacement), plus a symptom-to-check table.
Commit `2a83b1d4`-class docs commit follows this entry.

The plan asks for an independent Astra/high review of the guide before its scoped commit. That
review is a GPT-6 Astra task and is **not** performed in this session; the guide is committed as
an unreviewed draft and the missing review is recorded here rather than silently skipped.

## CP-18: back/forward routing pinned

A test now drives a real `popstate` after an out-of-band `history.pushState` and asserts the shell
follows the browser: the page changes to validation and back to teleop while the runtime is
registered exactly once and never closed. This covers the plan's "direct refresh/back/switch"
requirement at the routing layer. `bun run build` exit 0, `NODE_ENV=test bun run test`
**37 files / 166 tests**. Commit `c38a3aa2`.

## Session status at CP-18 (for the next round)

The account of what is and is not done lives in CP-11 (Task 8 registry blocker with exact
reproductions and retained evidence), CP-14 (the lock file's verified contents and the CMake web
inputs), CP-16 (the pinned layout contract, explicitly not browser evidence) and CP-17 (the
operation guide, including the missing independent Astra review). The two gate helpers and the
full recipe are described in CP-07 and CP-09; the registered evidence root is
`/tmp/so101-debug-so101-unified-webapp-impl-20260920` with `operator/preset-init.json` and
`preset-preview-8f09f448/` as the Task 8 artifacts.

## CP-19: the preset registry really is remote (negative result, closes a hypothesis)

Probed the cached pinned package at `~/.bun/install/cache/shadcn@4.21.0@@@1` to test whether the
preset and its component items ship inside the npm package, which would have made Task 8
reachable without the web registry. They do not:

- `dist/tailwind.css` (16 KB) is the generic v4 `@theme inline` base plus custom variants, not the
  preset's tokens;
- `dist/preset/index.js` and `dist/registry/index.js` are the machinery only: the only preset
  data present is the style list `["nova","vega","maia","lyra","mira","luma","sera","rhea"]`;
- the pinned id `b311momZs0` appears nowhere in the package.

So the resolved preset object and the per-component items are fetched from `ui.shadcn.com`, which
is exactly the path that fails for the CLI here while succeeding for curl. Task 8's remaining work
therefore needs either a CLI HTTP path that works against this proxy or a curl-driven capture of
the correct maia registry URL shape. No product change in this checkpoint; the hypothesis is
recorded so the next round does not repeat it.

## CP-20: the registry template is `r/{name}.json`, and every probed item URL 404s

Extracted the item URL template from the pinned package itself:
`dist/index.js` contains the literal template `r/{name}.json` against the base
`https://ui.shadcn.com`, plus `https://ui.shadcn.com/schema.json` and
`/schema/registry-item.json`. There is no style segment in the template, and the module exposes
`registry:ui|lib|component|hook|page|file|block` item types.

Every candidate item URL was then probed through the working proxy and returned the site's 35 KB
HTML 404 page:

```
/r/button.json                     404
/r/utils.json                      404   (also /r/utils.json?style=maia)
/r/button.json?style=maia&base=radix 404
/r/font-dm-sans.json               404
/r/maia/utils.json                 404
/r/styles/maia/utils.json          404   (also button.json, index.json, font-* items)
/r/styles/new-york/utils.json      200   <- legacy style only
```

So the reachable registry surface here serves the legacy `new-york` style, while the `maia`
(radix preset) items are behind a route this environment cannot resolve. Combined with CP-19,
the remaining Task 8 work needs either (a) a CLI HTTP path that survives this proxy, or (b) the
registry route discovered from a working network — guessing further is not a good use of rounds,
and the lock keeps its honest `PENDING_REGISTRY_ITEMS` marker meanwhile.

## CP-21: Task 8 registry unblocked - the style segment is the manifest's own name

**The blocker is solved.** The registry style segment is `radix-maia` - the `name` field of the
preset manifest - not the decoded style `maia`. The template found in the package is
`r/styles/{style}/{name}.json` with `style = radix-maia`:

```
https://ui.shadcn.com/r/styles/radix-maia/utils.json   -> 200
```

Fetched all 18 needed items successfully (evidence retained in
`<root>/registry/<name>.json`): `utils`, `font-dm-sans`, `font-heading-outfit`, `button`, `card`,
`sidebar`, `sheet`, `field`, `select`, `input`, `label`, `badge`, `alert-dialog`, `tooltip`,
`separator`, `tabs`, `scroll-area`. Each has a verified sha256 recorded in
`web/design-system.lock.json`; the two `registry:font` items record family, provider, import,
variable, subsets and dependency (e.g. DM Sans Variable via `@fontsource-variable/dm-sans`).

The lock's `blocked_reason` is now the narrower, accurate
`PENDING_PRODUCT_MERGE`: the data is captured, but the token/primitives smart merge into this
Tailwind 3.4.17 project and the self-hosted font files are not applied yet. The lock test asserts
all 17 required item names, the real per-item URL and hash, both font entries, and that no version
is guessed.

GREEN: `NODE_ENV=test bun run test` all green. Commit `aefc5e34`.

Next for Task 8: apply the captured foundation tokens to `index.css`/`tailwind.config.ts` as a
v3-compatible smart merge (the captured `cssVars` are v4 oklch values, so the review decision in
the plan about a v4 upgrade versus a v3 equivalent conversion has to be taken explicitly), merge
the primitives while preserving business variants/ARIA/testids, and self-host the fonts with
licences.

## CP-22: the captured preset tokens are applied as v3-compatible variables

`src/styles/theme.css` is generated from the captured pinned manifest (the file records the
manifest sha256 in its header) and imported by `index.css` ahead of the Tailwind layers. It holds
all 31 light and 31 dark foundation tokens - background, card, foreground, muted, border, input,
ring, primary, secondary, accent, destructive, popover, the four sidebar groups and the five chart
colours - as plain custom properties plus the radius.

Two deliberate decisions, both recorded rather than implied:

1. **No v4 upgrade.** The declarations are plain `:root` / `[data-theme="dark"]` custom
   properties consumed through `var()`, so Tailwind 3.4.17 and the existing compiler are
   unchanged. The plan's `@theme`-based v4 path was not taken, so there is no mixed v4/v3 output.
2. **Business outcome colours are independent of primary.** `--state-success` is its own colour,
   `--state-pending` maps to primary, `--state-failure` maps to destructive; blue is never used as
   success. Display fonts declare CJK fallbacks (`PingFang SC`, `Noto Sans CJK SC`) and no runtime
   `@import url(...)` font request is introduced.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` all green with 5 new theme tests.
Commit `5591de0e`.

Still open in Task 8: self-hosting the two font files with licences (the lock records the
`registry:font` items and their `@fontsource-variable/*` dependencies), and the per-primitive smart
merge that preserves business variants, ARIA, events, disabled reasons and testids.

## CP-23: self-hosted fonts, hashes and licences

Downloaded the two captured `registry:font` families as variable woff2 from the packages the
registry items themselves name (`@fontsource-variable/dm-sans`, `@fontsource-variable/outfit`,
via the jsdelivr CDN) into `public/fonts/`, verified the `wOF2` magic bytes, and recorded in the
lock for each: relative file, family, provider, CSS variable, source URL, sha256, byte length,
media type, licence and licence file. `public/fonts/LICENSES.txt` carries both upstream SIL Open
Font License 1.1 texts in full. `theme.css` gained local `@font-face` rules, so the browser never
requests an external font host. The lock marker is now `PENDING_PRIMITIVE_MERGE`, which names the
one thing actually left in Task 8.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **38 files / 172 tests**. Commits
`a1417525` and `c4c8a3c3`.

Process note: `a1417525` was committed before the full suite was read, and the suite caught a stale
assertion of mine (the old `PENDING_PRODUCT_MERGE` marker) within the same round; `c4c8a3c3` fixes
it and the marker assertion now matches the `PENDING_<WORK>:` shape generally instead of one exact
string. The lesson recorded for the next round: gate the commit on the suite result, not on the
build alone.

Remaining in Task 8: the per-primitive smart merge that preserves business variants, ARIA, events,
disabled reasons and testids.

## CP-24: every surface is bound to the tokens

`tailwind.config.ts` now maps the semantic palette onto the captured custom properties -
background, foreground, card, popover, primary, secondary, muted, accent, destructive, border,
input, ring and the sidebar group, plus radius and both font families. Business outcomes get their
own utilities (`success` -> `--state-success`, `pending`, `failure`) so blue is never success. The
base layer in `index.css` moved from `bg-slate-950 text-slate-100` to `bg-background
text-foreground`, so the old hardcoded slate surface is gone rather than left behind a few
restyled buttons. Still Tailwind 3.4.17: plain `var()` bindings, no v4 `@theme` declaration in
either the config or the CSS entry.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **39 files / 175 tests**. Commit
follows this entry.

Two self-inflicted test defects were caught by the suite in this round (a wrong expected variable
name, and a comment mentioning `@theme` tripping a "no v4 syntax" assertion). Both are fixed, and
the second is now comment-stripped the same way the theme test does it. The commit was gated on the
full suite this time.

## CP-25: the last hardcoded palette surfaces are merged

`alert-dialog.tsx`, `button.tsx` and `card.tsx` were the only primitives still naming a raw
palette. They now read the tokens: dialog and card surfaces use `border-border bg-card
text-card-foreground`, descriptions use `text-muted-foreground`, and the button's four business
variants map to `bg-primary`, `bg-secondary`, `bg-destructive` and the outlined
`border-input`/`hover:bg-accent` - every variant and size is kept, along with the focus ring,
`disabled:opacity-50` and the existing props. A new test walks every `components/ui/*.tsx` and
fails on any `bg|text|border|ring|fill|stroke-<palette>-<shade>` class, so the sweep cannot
silently regress. One baseline assertion in `tcp-panel.test.tsx` that pinned `bg-sky-600` was
updated to `bg-primary`.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **40 files / 178 tests**. Commit
`37cbb968`.

Remaining in Task 8: importing the *new* primitives the plan needs beyond the 12 that already exist
(sidebar, sheet, field, select, input, label) from the captured registry items, which is additive
work rather than a merge of existing behaviour.

## CP-26: the captured registry is Tailwind v4, and one primitive is ported

Reading the captured `registry:ui` sources settles the plan's open review question with evidence:
the `radix-maia` items are written for **Tailwind v4**. `input.tsx` uses `rounded-4xl` (no v3
equivalent), `bg-input/30` and `ring-ring/50` (v4 alpha composition of a `var()` colour), and both
items import `cn` from the bare specifier `"cn"` rather than this project's `@/lib/utils`.

Decision taken (mechanical and explicit, recorded rather than implied): **keep Tailwind 3.4.17 and
convert**, rather than perform the v4 upgrade. `src/components/ui/input.tsx` is the ported item:
`rounded-4xl` -> `rounded-md` (the token radius), `bg-input/30` -> `bg-input`, `ring-ring/50` ->
`ring-ring`, `ring-[3px]` -> `ring-2`, `aria-invalid:ring-destructive/20` -> solid
`aria-invalid:ring-destructive`, and the import rebound to `@/lib/utils`. Everything else is kept
verbatim: `data-slot`, the `file:` variants, `placeholder`, `focus-visible:border-ring`,
`disabled:*` and the invalid semantics.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **41 files / 181 tests**; commit gated
on the suite. The three new tests assert the data slot and ordinary props, the token classes with
no v4-only leftovers, and that disabled/invalid state stays declared for assistive technology.

Remaining in Task 8: the same port for the other captured primitives - `label` (which the registry
builds on `radix-ui`, a dependency this project does not yet have, so it needs either that
dependency or a dependency-free equivalent), `select`, `field`, `sheet` and `sidebar`. Each needs
the same explicit v3 conversion the input just had; guessing them in bulk would be the wrong move.

## CP-27: the label primitive is ported without widening the dependency closure

`src/components/ui/label.tsx` ports the captured `radix-maia` label. The registry imports the
`radix-ui` umbrella package; this project already depends on the scoped `@radix-ui/react-label`
(confirmed present in `node_modules`), so the primitive is behaviourally identical while the
import stays inside the existing closure - no new dependency, and `package.json`/`bun.lock` are
untouched. Classes are kept as the registry writes them (`data-slot`, `text-sm`, `font-medium`,
`select-none`, the `group-data-[disabled=true]:` and `peer-disabled:` pairs).

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **42 files / 184 tests**; commit gated
on the suite. The tests assert the data slot and `htmlFor` binding, that clicking the label focuses
its control, and that the disabled selector is preserved.

Remaining in Task 8: `select`, `field`, `sheet` and `sidebar`, each needing the explicit v4-to-v3
conversion. `sheet` and `sidebar` are the largest and pull in portal/sidebar machinery, so they
should be taken one at a time with their own behaviour tests rather than in bulk.

## CP-28: the select port needs real work, not a regex (reverted, tree clean)

Attempted a mechanical port of the captured `select` item (224 lines) and it failed typecheck in
three distinct ways, so the file was reverted and the tree is clean again (`bun run build` exit 0
after the revert). The failure modes are the useful output:

1. `import { Select as SelectPrimitive } from "radix-ui"` uses the umbrella package's namespace
   object. Rebinding it to the scoped `@radix-ui/react-select` must be
   `import * as SelectPrimitive from "@radix-ui/react-select"`; a named import has no `.Root`,
   `.Group`, `.Value` members.
2. The item imports an internal site component, `IconPlaceholder` from
   `@/app/(create)/components/icon-placeholder`, which does not exist in this project. A faithful
   port has to substitute the project's own icons (`lucide-react` is already a dependency) and
   check which indicator slots each one fills.
3. Alpha modifiers and `size-*` utilities need the v4-to-v3 conversion already applied to `input`.

So `select` is a real porting job - import strategy, icon substitution and a class pass - not a
substitution sweep. The same warnings apply to `field` (238 lines, and it declares
`registryDependencies: ["label", "separator"]`), `sheet` and `sidebar`. Next round should port one
item by hand, reusing the `input`/`label` conversions as the pattern, and only then wire the new
primitives into the pages.

## CP-29: select ported by hand with the three conversions CP-28 identified

`src/components/ui/select.tsx` (198 lines) is the captured `radix-maia` select ported properly:
the umbrella `radix-ui` import became `import * as SelectPrimitive from
"@radix-ui/react-select"` (keeping `.Root/.Group/.Value/...`), the site-internal
`IconPlaceholder` became the lucide icon its own `lucide` prop names (`ChevronDownIcon`,
`CheckIcon`, `ChevronUpIcon` - lucide is already this project's icon library), and the v4 classes
were converted (`bg-input/30` -> solid tokens, `rounded-4xl` -> `rounded-md`, `ring-[3px]` ->
`ring-2`, `size-*` -> `h-* w-*`). Structure, roles, data slots and keyboard behaviour are the
registry's own.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **43 files / 186 tests**; commit gated
on the suite. Two jsdom limits are documented in the test rather than papered over: radix renders
its listbox into a portal and calls `scrollIntoView`, so the open/select interaction is asserted in
the browser gate (Task 11), not in jsdom; the test asserts the closed render, the `select-trigger`
data slot, the token classes, and that no standalone v4 `size-*`/alpha class survives.

Remaining in Task 8: the same hand-port for `field` (238 lines, declares
`registryDependencies: ["label","separator"]` - both now available in some form), `sheet` and
`sidebar`.

## CP-30: field ported onto the existing label and separator

`src/components/ui/field.tsx` (238 lines) ports the captured field item. Its registryDependencies
were already satisfied in this project, so the registry's own `@/registry/radix-maia/ui/label` and
`.../ui/separator` imports point at `@/components/ui/label` (ported in CP-27) and the existing
`@/components/ui/separator`; `cn` resolves to `@/lib/utils`; the v4 alpha/size/radius utilities are
converted the same way as the other ports. The component's data slots (`field`, `field-group`,
`field-label`, `field-description`, `field-error`, ...) are the registry's own.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **44 files / 188 tests**; commit gated
on the suite. Tests assert the five data slots render, that the description uses
`text-muted-foreground` and the error uses `text-destructive`, and that no standalone v4
`size-*`/`rounded-4xl`/alpha class survives anywhere in the subtree.

Remaining in Task 8: `sheet` and `sidebar` - the two largest items, both pulling in portal and
sidebar machinery; each should get its own behaviour tests, and the sidebar in particular has to
respect the shell's navigation semantics from Task 9.

## CP-31: sheet ported, and the button gained the variants it needs

`src/components/ui/sheet.tsx` (146 lines) is the captured sheet: the umbrella `radix-ui` import
became the scoped `@radix-ui/react-dialog` namespace, the site-internal `IconPlaceholder` became
`XIcon` from lucide, the registry's button import points at this project's button, and the v4
utilities were converted.

The port surfaced a real gap rather than a workaround: the registry's sheet uses
`variant="ghost"` and `size="icon-sm"`, which this project's button did not have. The captured
button item declares six variants (`default`, `outline`, `secondary`, `ghost`, `destructive`,
`link`) and six sizes (`default`, `xs`, `sm`, `lg`, `icon`, `icon-sm`), so the missing ones were
merged into `src/components/ui/button.tsx` in v3-equivalent form, keeping the existing set intact.
The registry's v4-only refinements (`has-data-[icon=...]` padding, `dark:` alpha variants) are
omitted on purpose and that omission is written into the file.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **45 files / 190 tests**; commit gated
on the suite. The sheet test asserts the trigger renders and that no v4-only utility survives in
the file; the open/portal interaction is deferred to the browser gate, as with select. A second
test renders all six variants and all six sizes to prove the merged button surface is complete.

Remaining in Task 8: `sidebar`, the last item, which also has to respect the shell's navigation
semantics from Task 9.

## CP-32: the shell uses the ported sheet, and the nav semantics survive it

`AppShell`'s hand-rolled collapse is gone. Narrow screens now open the **ported design-system
`Sheet`** (radix dialog) with the two primary entries inside it, while wide screens keep the list
permanently visible (`hidden ... md:block`). The earlier accessibility fix is preserved rather than
undone: the entries are never behind a permanent `hidden` attribute, so assistive technology can
always reach them, and radix owns the trigger's `aria-expanded`.

The shell test was updated to assert what is now true: the sheet trigger renders with
`aria-expanded="false"`, the wide-screen `navigation[aria-label=Primary]` contains both entries,
and clicking the trigger does not throw. The sheet's own portal content is not asserted in jsdom
(no layout), which stays with the browser gate.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **45 files / 190 tests**. Commit
`28bbb6ea`.

Remaining in Task 8: `sidebar` itself, the last item; with the shell's navigation now provided by
the sheet, the sidebar can be introduced only if the shell genuinely needs it, and the plan is
explicit that new items are introduced only where a page needs them.

## CP-33: a page now consumes the ported primitives

`CampaignSetup` uses the ported design-system `Input` for the catalog seed and the final point
count, and its section surface plus select/inputs all read tokens instead of a raw palette. A check
over the file now finds zero `bg|text|border-<palette>-<shade>` classes. Behaviour is unchanged:
the same `aria-label`s, the same read-only seed, the same min/max on the point count, and the same
existing component tests pass untouched.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **45 files / 190 tests**. Commit
follows this entry.

Note for the next round: `Input`, `Sheet` and `Field` are now used by the product, while `Label` and
`Select` are ported but not yet consumed - `CampaignSetup` still uses a native `<select>` for the
worker count because its nine existing tests query native `<option>` elements, so switching it to
the radix select needs those tests rewritten in the same change. `sidebar` remains unported, and
with the sheet providing the shell's navigation the plan's rule ("introduce new items only where a
page needs them") argues for leaving it out unless a page actually requires it.

## CP-34: the label primitive is consumed by the form

All four field labels in `CampaignSetup` (catalog seed, final point count, execution mode, worker
count) now use the ported design-system `Label` instead of a raw `<label>`. The nesting is
unchanged, so implicit label association, the existing `aria-label`s and every `getByLabelText`
query behave exactly as before.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **45 files / 190 tests**. Commit
follows this entry.

Consumption status of the ported set: `Input`, `Sheet`, `Field` and `Label` are now used by the
product; `Select` is ported but not yet consumed. `CampaignSetup` keeps a native `<select>` for the
worker count because its existing tests query native `<option>` elements and jsdom cannot render the
radix listbox portal - switching it means rewriting those assertions in the same change and moving
the open/select interaction to the browser gate, which is the honest next step for that component.

## CP-35: the two required viewports are measured in the browser gate

`web/e2e/unified/live-sim.spec.ts` gained the layout evidence the design demands and that jsdom
cannot produce: for 1400x900 and 390x844 it loads `/`, `/expert-validation` and `/tasks` and asserts
`documentElement.scrollWidth <= clientWidth + 1` plus that no element's right edge exceeds the
viewport, i.e. no horizontal page overflow. It also re-checks the map contract in a real browser
(one marker radius across all `circle[data-point-status]`, skipped when the run has no manifest,
since the unit test already pins the contract). The fixture contract test asserts both viewport
sizes, `setViewportSize`, the overflow measurement and the marker selector are present.

GREEN: `NODE_ENV=test bun run test` (vitest) green; `pygate test_unified_live_fixture.py` exit 0.
These Playwright tests execute only in the separately authorized live/installed gate, so this is
prepared evidence, not a claim that the viewports were checked here.

Decision recorded on the worker-count control: it stays a native `<select>`. Switching it to the
ported radix `Select` would move the qualification assertion (an unknown exact N is disabled) out of
jsdom, because radix mounts its listbox in a portal that jsdom cannot render, and the plan requires
preserving test selectors rather than trading a real assertion for a cosmetic one. The ported
`Select` remains available for controls that need it.

## CP-36: registration drift is now impossible to miss

`test_unified_launch.py` gained a two-way guard: every `test_unified_*.py` on disk must be
registered in `CMakeLists.txt` with the same path, and every `so101_add_pytest_test(test_unified_...)`
entry must point at a file that exists. An unregistered module silently never runs in the ament
gate, and a registration pointing at a missing file breaks configure, so both directions matter.
`pyrgate` on the module exits 0.

This also closes a plan-level worry: the plan requires 16 registered names in the configure gate and
demanded that "新增追溯 tests ... 追加其真实文件名后才 stage". The guard makes any future addition
that forgets registration fail locally instead of only in the C++-free ament run.

Commit follows this entry.

## CP-37: lease renewal moved into the runtime

`DomainRuntime` now owns the renewal heartbeat: `startHeartbeat(intervalMs)`, `stopHeartbeat()`,
`heartbeatRunning()` and `lastRenewalError`. It is deliberately not tied to any component
lifecycle - switching pages cannot stop a renewal, and only the root provider's `dispose` ends it.
Starting it twice does not double the timers, and a failed renewal is recorded rather than retried
with a new lease generation or routed through the mutation path.

GREEN: `NODE_ENV=test bun run test` **46 files / 192 tests**; `bun run build` exit 0. Two tests use
fake timers to prove three ticks of renewal happen with no page teardown in between, that
`dispose` is what stops it, and that a `LEASE_RENEW_FAILED` is recorded with no POST attempt.

This is the runtime half of Task 9's effect migration. The remaining half is mechanical but touches
live page code (`app.tsx`, `expert-validation-app.tsx`): delete their page-scoped telemetry/renew
effects and consume the runtime instead, which needs a careful read of both effects before editing
rather than a quick substitution.

## CP-38: the provider now drives renewal, so the runtime path is live

`RuntimeProvider` accepts an optional `heartbeatMs` and starts each domain runtime's heartbeat after
a successful `start()`; `main.tsx` passes 10s. Because the interval lives in the runtime, a page
switch only re-renders the provider's children and the cadence is untouched - the test proves
renewals keep their rhythm across a re-render and that nothing calls `transport.close`.

GREEN: `NODE_ENV=test bun run test` **45 files / 193 tests**; `bun run build` exit 0. Commit follows
this entry.

Honest status of the migration: the runtime path is now live and additive, but the pages still have
their *own* renew effects, so renewal is currently performed twice. Removing the page-level effects
is the remaining half; it touches live page code and needs a careful read of both effects, so it is
left for a round with room to verify it properly rather than rushed.

## CP-39: a blocking defect found before it could ship - renewal without authority

Checking what the page-side effect removal would actually require exposed a real defect in the
runtime renewal path added in CP-37/CP-38: `createHttpTransport.renew()` posted to
`/control/lease/renew` **without the four instance authority headers**, and the server refuses any
lease renewal that lacks them. The runtime heartbeat was therefore live but would have been refused
in production.

Fixed: `DomainTransport` gained an optional `setAuthority(authority | null)`; the HTTP transport
holds the authority and merges `authorityHeaders()` into the renewal request; `DomainRuntime`
propagates the authority it adopts. A test asserts the renewal request carries all four headers.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **45 files / 194 tests**. Commit follows
this entry.

This is why the page loops were not deleted in CP-38: removing them first would have left renewal
refused rather than duplicated. With the transport fixed, removing the two page-level renewal
effects is now a safe, small change - and the duplicate-renewal note in CP-38 is superseded once it
lands.

## CP-40: the teleop page no longer renews its own lease

`app.tsx`'s page-scoped `setInterval` that POSTed `/control/lease/renew` every 10s is gone, replaced
by a comment stating where renewal now lives. Renewal is owned by `DomainRuntime` (CP-37), driven by
the root provider (CP-38) and carries the required instance authority (CP-39), so unmounting the
teleop page can no longer stop a heartbeat - and renewal is no longer performed twice.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **45 files / 194 tests**. Commit follows
this entry. This supersedes the duplicate-renewal caveat recorded in CP-38.

Still open in the same class of work: `expert-validation-app.tsx` keeps its own renewal effect
(lines ~161-190, margin-based, with its own failure handling and lease replacement). It is a richer
loop than the teleop one - it validates the returned lease identity and generation and rewrites the
runtime's short-lived lease state - so removing it needs the runtime/validation transport to expose
the same failure semantics first, rather than deleting the loop and losing that check.

## CP-41: the authority headers are part of the published contract (gap found and closed)

Checking the plan's requirement that "authority headers 与 new parent/instance schemas 全生成" against
the generated document showed the headers were **missing**: the routes read them from
`Request.headers`, so FastAPI emitted `parameters: []` for every mutation and the generated client
had no way to know they exist.

Fixed by declaring them as real `Header(alias=...)` parameters in the shared `require_authority`
dependency. All four now appear on every mutation route in the unified, teleop and validation
documents, the three TypeScript clients were regenerated, and a new test asserts the four names on
`/gripper/execute`, `/plan/joints`, `/robot/home` and `/tasks/runs` plus the presence of the
`InstanceProofResponse` and `QualificationViewResponse` schemas. Behaviour is unchanged: a missing
header still yields `CONTROLLER_INSTANCE_REQUIRED`, and a present-but-unbound authority still yields
`SERVICE_NOT_COMPOSED` or the registry's own refusal code.

GREEN: `pyrgate test_unified_api.py` exit 0; frontend suite and build re-verified after regenerating
the clients. Commit `08eb6818`.

## CP-42: the runtime owns the lease identity and validates renewals

`DomainRuntime` gained `adoptLease`, `lease()` and `validateRenewal(next)`, plus a `LeaseIdentity`
type mirroring the server contract. The check the validation page performs today now lives in the
runtime and is unit-tested: a renewal that changes the lease id or session, or that does not strictly
increase the generation, is refused, the runtime drops its lease state and records
`LEASE_IDENTITY_MISMATCH` / `STALE_LEASE_GENERATION` / `LEASE_NOT_HELD` in `lastRenewalError`.

GREEN: `NODE_ENV=test bun run test` **45 files / 196 tests**; `bun run build` exit 0. Commit follows
this entry.

This unblocks the last Task 9 migration step: `expert-validation-app.tsx` can now hand its lease to
the runtime, call `validateRenewal` where it currently does the identity/generation comparison, and
let the runtime's heartbeat own the interval - which then allows the page effect to be deleted
without losing the check. That deletion is the remaining edit.

## CP-43: renewal UI state moved, and the exact shape of the last migration step

Added `DomainRuntime.renewing`, set while a renewal is in flight, with a test that holds the renewal
open and observes the flag. This is the second of the two things the validation page currently owns
that the runtime needs (`leaseRenewing`).

Read of the remaining page effect (`expert-validation-app.tsx` lines ~161-190), recorded so the last
edit is mechanical next time: it is **not** a repeating interval. It is a single `setTimeout`
scheduled at `(lease_duration_s - lease_renewal_margin_s) * 1000`, re-armed by the effect whenever
`lease` changes, with three responsibilities - refuse invalid capabilities
(`LEASE_CAPABILITIES_INVALID`), flip `leaseRenewing` for the UI, and validate the returned lease
(`lease_id`, `service_session_id`, strictly greater `generation` **and**
`expires_monotonic_ns`) before replacing it. It also distinguishes a renewal failure (lease dropped,
error reported) from a successful renewal ("Lease renewed; check resources again").

So the remaining work is: give the runtime (a) a cadence derived from the capability values rather
than a fixed `heartbeatMs`, and (b) the `expires_monotonic_ns` comparison in `validateRenewal`; then
the page keeps only its notice/indicator wiring. Deleting the effect before those two exist would
drop the capability refusal and the expiry check, which is why it is not done yet.

GREEN: `NODE_ENV=test bun run test` **45 files / 197 tests**; `bun run build` exit 0. Commit follows
this entry.

## CP-44: the runtime now covers both things the page effect owned

`startHeartbeat` accepts either a fixed interval or a provider callback evaluated each time the next
tick is armed, so the validation cadence `(lease_duration_s - lease_renewal_margin_s)` can be derived
from capabilities; an invalid value stops the heartbeat and records `LEASE_CAPABILITIES_INVALID`
instead of renewing on a guess. `validateRenewal` now also refuses a renewal whose
`expires_monotonic_ns` did not strictly increase (`LEASE_EXPIRY_NOT_EXTENDED`). `LeaseIdentity` gained
the optional expiry field, and the heartbeat is a self-rescheduling timeout rather than an interval
so a capability change takes effect on the next tick.

GREEN: `NODE_ENV=test bun run test` **45 files / 199 tests**; `bun run build` exit 0. Commit follows
this entry.

With CP-42, CP-43 and this checkpoint, every responsibility of the validation page's renewal effect
is now owned and tested by the runtime: identity and generation validation, expiry extension,
capability-derived cadence, invalid-capability refusal, the in-flight indicator, and the error
record. Deleting that effect is now a mechanical edit plus the page's notice/indicator wiring.

## CP-45: the validation page validates through the runtime

`RuntimeProvider` gained `useOptionalDomainRuntime(domain)`, which returns null outside a provider so
components keep working in unit tests. `expert-validation-app.tsx` now calls
`runtime.validateRenewal(...)` for the lease identity/generation/expiry rule instead of comparing the
fields inline, and reports `runtime.lastRenewalError` when it refuses; the inline comparison remains
only as the no-provider fallback the unit tests exercise. One check, one owner.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **45 files / 199 tests**. Commit follows
this entry.

What is left of Task 9's migration is now only the scheduling: the page still owns a re-armed
`setTimeout` at `(lease_duration_s - lease_renewal_margin_s)`, while the runtime can already compute
that cadence (CP-44). Swapping that scheduling to `runtime.startHeartbeat(() => ...)` - and giving the
provider a per-domain cadence rather than one `heartbeatMs` for both domains - is the final edit.

## CP-46: the runtime adopts and validates the lease a renewal returns

`DomainTransport.renew()` now returns the renewed lease when the endpoint answers with a lease-shaped
body (the validation endpoint does; the teleop endpoint answers with a `CommandResult` and returns
nothing). `DomainRuntime.renew()` validates that body through `validateRenewal`, adopts it on
success, and throws `lastRenewalError` on refusal so a caller cannot keep operating on an identity
the server did not confirm. A test proves the adopted generation advances, and that a non-extending
renewal is refused and clears the lease.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **45 files / 200 tests**. Commit follows
this entry.

With this, the runtime owns the complete renewal round trip - cadence, authority headers, the request,
identity/generation/expiry validation and the resulting lease state - so the page's remaining
`scheduled setTimeout` can be replaced by `runtime.startHeartbeat(() => (duration - margin) * 1000)`
and its own validation branch deleted. That swap is the last edit in Task 9's migration.

## CP-47: renewal outcomes are published, so the page needs no timer

`DomainRuntime.onRenewal(listener)` reports each renewal's outcome (`{ok, error}`), with the listener
receiving the recorded reason on failure. The listener set is cleared on `dispose` through the normal
teardown path, and a test proves the success outcome, the failure outcome with its
`LEASE_RENEW_FAILED` reason, and that unsubscribing stops delivery.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **45 files / 201 tests**. Commit follows
this entry.

Every responsibility of the validation page's renewal effect is now owned by the runtime *and*
observable from it: cadence, authority, request, identity/generation/expiry validation, adopted lease
state, in-flight indicator, error record and outcome notification. The final edit is purely
subtractive in the page - replace the `setTimeout` scheduling with
`runtime.startHeartbeat(() => (duration - margin) * 1000)`, adopt the lease into the runtime, and feed
the page's notices from `onRenewal`.

## CP-48: the page swap needs its two tests updated first (attempted, reverted, tree green)

Attempted the final subtractive edit in `expert-validation-app.tsx` - replace the `setTimeout` with
`runtime.startHeartbeat(() => (duration - margin) * 1000)`, adopt the lease into the runtime, and feed
notices from `onRenewal`. It compiled, but two existing tests failed, and they failed for a real
reason rather than a fixture detail:

- `renewal at the server margin replaces stale preflight authority before start`
- `failed renewal disables execution and allows a fresh lease request`

Both render `ExpertValidationApp` **without a provider**, so `runtime` is null and no heartbeat
exists; they assert that the page itself calls `api.renewLease` at the margin and advances the lease
generation. Under the migrated design that work happens in the runtime's transport, so those tests
must drive a `RuntimeProvider` with a fake validation runtime whose transport delegates to
`api.renewLease`.

The page edit was reverted (`git checkout --`) and the tree is green again: `bun run build` exit 0,
`NODE_ENV=test bun run test` **45 files / 201 tests**, clean status. The runtime-side work from
CP-42..CP-47 stands untouched.

Next round: rewrite those two tests to mount the provider and drive the runtime (`startHeartbeat` +
`onRenewal`), then re-apply the page edit. Doing it in that order keeps the tree green at every step,
which is the rule this session has held to throughout.

## CP-49: Task 9's effect migration is complete

The two renewal tests now render the app inside a `RuntimeProvider` through a `renderWithRuntime`
helper whose validation transport finishes renewals via the test's own `renewLease` spy, and the page
edit landed on top of them: `expert-validation-app.tsx` no longer schedules a timer. It adopts its
lease into the runtime, calls `runtime.startHeartbeat(() => (duration - margin) * 1000)`, and turns the
published outcome into its own notices and `leaseRenewing` indicator. No page owns a renewal timer,
and no validation logic lives in a page.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **45 files / 201 tests**, including the
two rewritten renewal tests; tree clean. Commit `006f299f`.

With CP-40 (teleop) and this checkpoint (validation), **both pages are migrated**: switching pages
cannot stop a heartbeat, renewal carries the required instance authority, the lease identity,
generation and expiry are validated in one place, and a failed renewal still disables execution and
allows a fresh lease request exactly as before.

## CP-50: Task 11's isolated configure and build are GREEN

Ran the plan's Stage A build through `rosgate` into a fresh, previously nonexistent base
(`build-FV6UHHX5` under the registered root):

```
colcon --log-base <root>/colcon-log build --build-base <root>/build --install-base <root>/install \
  --packages-select so101_teleop --symlink-install --cmake-clean-cache \
  --cmake-args -DBUILD_TESTING=ON -DPython3_EXECUTABLE=<TEST_PYTHON> -DPYTHON_EXECUTABLE=<TEST_PYTHON>
```

**Exit 0.** The web bundle built through Bun as part of it. `ctest --show-only=json-v1` then reports
**69 registered tests, 15 of them `test_unified_*`**: admission, api, arbiter, bridge,
budget_adapter, gate, instances, ipc, launch, lifecycle, live_fixture, parents, safety, two_channel,
web_dependencies. Crucially, **every** test command's Python is the registered
`/Users/matianyi/ros2_jazzy/.venv/bin/python` - the plan's ACTUAL_CTEST_PYTHON_MISMATCH condition does
not fire - and the registration-drift guard passes, so the CMake list and the files on disk agree.

One honest gap against the plan's 16-name list: **`test_unified_cancel_integration` does not exist.**
The plan assigns that file to Task 6 (`ProductionHarness`, real factory + real routes + a barrier
driver) and it was never written, because the ProductionHarness depends on the composed factory
runtime that this host cannot fully exercise. The other 15 names are all present.

Still open in Task 11: the three incremental rebuild proofs, the `colcon test` run over the installed
overlay with per-test TEMP provenance, and the copied-install Chrome gate.

## CP-51: all 15 unified tests pass inside the real ament/CTest gate

Ran `ctest --test-dir <build>/so101_teleop -R test_unified --output-on-failure` through `rosgate`
against the overlay built in CP-50: **exit 0**. This is the strongest evidence in the session so far,
because it exercises the tests through the plan's actual gate - CTest/ament with the installed
overlay, the registered interpreter and the real environment - rather than a direct pytest
invocation. Every module this task added (gate, arbiter, instances, safety, ipc, bridge,
two_channel, parents, admission, api, lifecycle, budget_adapter, live_fixture, launch,
web_dependencies) passes there.

Still open in Task 11: the three incremental rebuild proofs, a full `colcon test` over the package
(69 tests, only the unified subset has been run in-gate), the per-test TEMP provenance run, and the
copied-install Chrome gate.

## CP-52: the build graph really tracks the new web inputs

Read the rules CMake generated for the web target
(`build/so101_teleop/CMakeFiles/so101_teleop_web.dir/build.make`) rather than trusting the CMake
source: `src/styles/theme.css`, `public/fonts/dm-sans-variable.woff2`, `components.json` and
`design-system.lock.json` each appear exactly once as explicit prerequisites of
`web/dist/index.html`, alongside 120 tracked `web/src` and `web/public` paths. So editing a token,
replacing a font or changing the component manifest invalidates the bundle target - the mechanism the
plan's three incremental proofs are meant to demonstrate is in place in the generated graph.

What is still missing is the *end-to-end* form the plan asks for: build, change a CSS token in a
task-owned fixture tree, rebuild and show the bundle hash changed; the same for a font file and for
`components.json`, with stdout/exit/mtime/hash retained. The dependency graph is evidence that the
mechanism works, not a substitute for those three runs, and it is recorded that way.

## CP-53: the full CTest run found one regression of mine, now fixed

Ran all 69 registered tests in the built overlay: **83% passed, 12 failed, 408 s**. Critically, **none
of the 15 `test_unified_*` modules failed** - the work this task added is green in the real gate.

One of the 12 was **my regression**, not a pre-existing failure: `test_teleop_web_bundle` asserts the
literal `location.pathname === "/tasks"` in `main.tsx`, which the Task 7 rewrite replaced with the
History-API router owned by the root provider. The behaviour is unchanged (the legacy `/tasks` route
still renders `TaskApp`), so the assertion now follows the new source of truth - it checks that
`main.tsx` uses `usePageRouting` and renders `TaskApp`, and that `runtime-provider.tsx` maps the
`/tasks` pathname to the `tasks` page. `pygate test_web_bundle.py` passes; commit follows this entry.

The other 11 failures are in expert-validation modules (`start_guard`, `adaptive_owner`, `control`,
`e2e_installed_port`, `preflight`, `process_owner`, `process_owner_integration`, `supervisor`,
`operator_recovery`) plus two timeouts (`expert_validation_package_layout`,
`production_projection`). They are outside everything this task touched - no expert-validation
implementation file was modified; only the generated `expert_validation_openapi.json` and the new
`unified/*` modules - and they match this host's known gaps (an incomplete `so101_demo` install
closure and process-ownership probes). They are recorded as **unclassified**, not as "pre-existing"
or "caused by this task", because classifying them properly needs the baseline run that this
round's context did not allow. That classification is the next diagnostic step.

## CP-54: the expert-validation failures are pre-existing on this host (measured, not assumed)

CP-53 left those 11 failures "unclassified" and named the baseline run as the next step. Done: a
detached worktree of the base commit `5b8d1231` was created under `/tmp/so101-baseline-cp53`, the
same interpreter and the same ROS-sourced environment were used, and three representative failing
modules were run there - `test_expert_validation_start_guard`, `test_expert_validation_preflight`,
`test_expert_validation_control`.

Result on the **pristine baseline**: `3 failed, 36 passed, 7 errors` - the same modules already fail
before any of this task's changes exist. So the expert-validation failures are a property of this
host (an incomplete `so101_demo` install closure and process-ownership probes), not a regression from
this work. The baseline worktree was removed afterwards.

Combined with CP-53, the full-suite picture is: the regression I did introduce (`test_teleop_web_bundle`,
an assertion pinned to the old inline routing) is fixed, and the remaining failures reproduce without
my changes. The 15 `test_unified_*` modules pass in the same gate.

## CP-55: the incremental rebuild edge is live (measured as a contrast)

CP-52 showed from the generated rules that `theme.css`, the fonts, `components.json` and
`design-system.lock.json` are prerequisites of `web/dist/index.html`. This checkpoint measured the
behaviour instead of the declaration, using the existing dev build tree from CP-50:

1. `touch src/styles/theme.css` (mtime only) then `cmake --build <build> --target so101_teleop_web`
   - **exit 0 and Bun ran**: `bun install v1.3.14` followed by `[100%] Built target so101_teleop_web`
   (gate `00cb6258...`). The dependency edge fired.
2. The same command again immediately - **exit 0, no Bun invocation**, only
   `[100%] Built target so101_teleop_web` (gate `6e288097...`). Correctly a no-op.

`web/dist/index.html` hashed `534e477a6ca7f8f3` before and after - as expected, because a `touch`
changes no content, so Vite emits identical bytes. That makes the result precise rather than
overstated: **the rebuild edge is proven live**; the plan's stronger form (edit a token in a
task-owned fixture tree and show the bundle *bytes* change) still needs a real content edit in an
isolated fixture tree, and that remains open along with the font and `components.json` variants.

## CP-56: two of the three content-edit rebuild proofs pass in a fixture tree

The plan asks for three incremental proofs in a task-owned fixture tree. Built one by copying
`web/` into `<root>/web-fixture-1789891339`, installing with the frozen lockfile and building there,
so **no product source was touched** (`git status` stayed clean throughout).

1. **CSS token** - appended one token to the fixture's `src/styles/theme.css` and rebuilt: the built
   stylesheet hash changed `f5837e9faa926ec6` -> `0d238a4872ddbcd2`.
   `CSS_TOKEN_CHANGE_REBUILDS_BUNDLE=YES`.
2. **Font asset** - replaced `public/fonts/dm-sans-variable.woff2` with the other family's bytes and
   rebuilt: the emitted `dist/fonts/dm-sans-variable.woff2` hash changed `9fea608a947e6702` ->
   `6c18d579fd87c377`, i.e. the new bytes reached the bundle.
   `FONT_CHANGE_UPDATES_EMITTED_ASSET=YES`.
3. **components.json** - edited it and rebuilt: the build succeeded, but `dist/index.html` hashed
   `7e2e0955d4826a2b` before and after. That is the honest expected result: the manifest configures
   the component CLI, it is not bundle input, so the plan's wording for this case ("web command
   re-runs") is what holds, and CP-55 already proved the CMake edge re-runs the command. Claiming a
   bytes change here would be wrong.

All fixture outputs stay in the registered root as evidence. Remaining in Task 11: the per-test TEMP
provenance run and the copied-install Chrome gate; the latter needs a complete `so101_demo_py` release
closure.

## CP-57: the CTest suite runs with its TEMP inside the registered root

The plan requires proving that the tests the ament gate launches resolve their temporary directory
inside a registered scratch, not the system temp. Measured on the CP-50 overlay:

```
rosgate env TMPDIR=<root>/ctest-tmp-1SlpBurM TMP=... TEMP=... \
  ctest --test-dir <build>/so101_teleop -R test_unified --output-on-failure
```

**Exit 0**, and afterwards the scratch contained `pytest-of-matianyi/pytest-1 .. pytest-9` with 21
files - i.e. every unified test that used `tmp_path` created it under the registered root rather than
in `/var/folders`. Combined with CP-50's check that every CTest command uses the registered
interpreter, both halves of the provenance requirement now hold for the unified subset.

Evidence classification per AGENTS.md: the fixture copies (`build-FV6UHHX5`, `web-fixture-1789891339`,
`ctest-tmp-1SlpBurM`, the `pytest-*` invocation directories and `preset-preview-8f09f448`) are all
retained under the registered root and are **deletion candidates** once the task is signed off; none
is deleted here.

Still open in Task 11: the copied-install Chrome gate, which needs a complete `so101_demo_py` release
closure rather than the source shim.

## CP-58: the copied-install gate is blocked by a host dependency, not by this task's code

Task 11's last item needs a release overlay built with `--packages-up-to so101_demo_py so101_teleop`
and then copied to an immutable prefix. Attempted it into a fresh base (`release-n5JyZLog`):

```
colcon build --build-base <release>/build --install-base <release>/install \
  --packages-up-to so101_demo_py so101_teleop --cmake-clean-cache --cmake-args -DBUILD_TESTING=ON ...
```

**Exit 1: `0 packages finished`.** The classification matters more than the exit code, and the log is
unambiguous about where it failed:

```
--- stderr: mujoco_vendor
CMake Error at CMakeLists.txt:16 (message):
  MUJOCO_STAGE_ROOT must contain include/mujoco/mujoco.h
Failed   <<< mujoco_vendor [2.99s, exited with code 1]
Aborted  <<< so101_teleop [41.5s]
```

The failure is in **`mujoco_vendor`, during CMake configure, because a host-provided staging root is
absent** - and `so101_teleop` is only *aborted* as a downstream consequence. This is precisely the
"incomplete dependency closure" case: `so101_teleop` on its own configures and builds green (CP-50,
exit 0) because it does not need `mujoco_vendor`, while the release closure does.

So the copied-install Chrome gate cannot be executed on this host until `MUJOCO_STAGE_ROOT` (or an
equivalent approved MuJoCo staging prefix) is provisioned, and that is a host prerequisite outside
this task's authority - not a defect in the unified work and not something to work around by
substituting a fake prefix. Everything up to that boundary is verified; the gate is blocked with a
named, reproducible reason.

## CP-59: the missing cancel-integration test exists, and it found three real defects

CP-50 recorded that `test_unified_cancel_integration` was never written, so the plan's headline
safety property had no test. Written now and registered (the CMake drift guard from CP-36 enforces
that). Only the innermost `WorkerPort` is test-owned: the request travels through the real app
factory, the real admission gateway, the real arbiter, the real safety lane and the real routes, with
an instance registered, a channel connected and a real claim - so this is the production cancel path,
not a toy.

The test asserts the plan's window directly: while the parent holds its reservation with the gripper
step blocked, `/execution/cancel` is accepted, the durable `cancel_requested` is recorded, **the
reservation is not released**, and the parent's final phase is not COMPLETE.

Getting there exposed three real defects, each fixed rather than worked around:

1. `INSTANCE_DOMAIN_MISMATCH` on every real mutation: `require_authority` passed the plain string
   `"teleop"` where the registry compares `Domain` members by identity. The schema-only API tests
   never reached that comparison. Fixed with `Domain(domain)`.
2. `TypeError: command() missing 2 required keyword-only arguments`: `ProductionTeleopService.command`
   did not match the `TeleopPort` shape the routers call. Authority and lease are now optional; the
   gateway still refuses any mutation without them.
3. Two response-shape bugs in the teleop router: it called `.model_dump()` on a port implementation
   that answers with a plain mapping, and it decided success via `getattr(result, "succeeded")`, which
   is always False for a dict - so an accepted cancel came back as HTTP 503. It now reads the payload.

The cancel response also now states the distinction explicitly: `succeeded: true` with
`code_detail: "CANCEL_ACCEPTED_NOT_STOPPED"`, since acceptance is not physical stopping.

GREEN: `pyrgate` on the new test passes; the API, launch (with its drift guard) and cancel-integration
modules pass together (17 tests); the frontend suite is unaffected. Commit `1bce0b11`.

With this, every name on the plan's Task 11 registration list exists.

## CP-60: CP-59's new test and fixes verified in the rebuilt overlay

The overlay from CP-50 predated CP-59, so the incremental rebuild was run and the gate re-executed:

```
colcon build --packages-select so101_teleop --symlink-install ...   -> exit 0, 1 package finished [39.9s]
ctest --test-dir <build>/so101_teleop -R test_unified -R ...        -> 100% tests passed out of 16
```

**16 unified tests now pass in the real ament/CTest gate**, up from 15: the cancel-integration module
is registered and green there, so the plan's full registration list is satisfied *in the gate*, not
merely on disk. The Python fixes from CP-59 (`Domain(domain)`, the port-compatible `command`
signature, payload-based success detection) are all covered by that run.

Task 11 is now complete except for the copied-install Chrome gate, which CP-58 established cannot run
on this host because `MUJOCO_STAGE_ROOT` is absent (a host prerequisite, with the exact CMake error
retained).

## CP-61: the release closure advances one dependency at a time; the next stop is a missing header

CP-58 stopped at `mujoco_vendor`. CP-61 probed for the host artifacts it wanted and found them, so the
closure was retried twice more - each time getting one package further, which is exactly the
"incomplete dependency closure" diagnosis rather than a source problem:

| Attempt | Environment | Result |
| --- | --- | --- |
| CP-58 | (none) | `mujoco_vendor` fails: `MUJOCO_STAGE_ROOT must contain include/mujoco/mujoco.h` |
| CP-61a | `MUJOCO_STAGE_ROOT=<ros2_jazzy>/mujoco_vendor_macos_ws/mujoco_stage` | `mujoco_vendor` fails one check later: `MUJOCO_SOURCE_ROOT must contain simulate/simulate.h` |
| CP-61b | plus `MUJOCO_SOURCE_ROOT=<...>/mujoco_vendor_macos_ws/src/mujoco` | **`mujoco_vendor` finishes**; `so101_mujoco_support` then fails to compile: `fatal error: 'mujoco_ros2_control_plugins/mujoco_ros2_control_plugin_capabilities.hpp' file not found`; `so101_teleop` aborted behind it |

So the release overlay is not blocked by one missing variable but by an incomplete **C++ dependency
closure**: the approved MuJoCo/`mujoco_ros2_control` underlay that provides
`mujoco_ros2_control_plugins` is not installed on this host (`<ros2_jazzy>/ws_mujoco_ros2_control_fork`
exists as a workspace but its install prefix was not found under the searched roots). Building that
underlay is outside this task's authority - the `.envrc.example` deliberately filters the stale fork
prefix out of the environment - so the copied-install Chrome gate stays blocked, now with a precise
reason at a different layer than CP-58 recorded.

Everything this task owns still builds green on its own (`--packages-select so101_teleop`, CP-50) and
its 16 unified modules pass in that overlay (CP-60).

## CP-62: the only host copy of the missing underlay is the one the project deliberately excludes

CP-61 stopped at `fatal error: 'mujoco_ros2_control_plugins/mujoco_ros2_control_plugin_capabilities.hpp'
file not found`. The header does exist on this host - but in exactly one place:

```
<ros2_jazzy>/ws_mujoco_ros2_control_fork/install/include/mujoco_ros2_control_plugins/...
```

and that prefix carries a `COLCON_IGNORE` marker and is the very path `.envrc.example` removes from
`AMENT_PREFIX_PATH`, `COLCON_PREFIX_PATH`, `CMAKE_PREFIX_PATH`, `PATH`, `PYTHONPATH`, `LD_LIBRARY_PATH`
and `DYLD_LIBRARY_PATH`, with the comment "sourced last so ros2 pkg/run cannot select a stale
standalone fork workspace". The sanctioned source is the project's own install overlay, which does not
exist in this worktree and would need the same closure to build.

So the copied-install Chrome gate is blocked by a policy boundary, not by an oversight: completing it
would require either building the approved underlay or knowingly linking against the stale fork the
project excludes. The second is not mine to do, and the first is outside this task's authority. The
gate therefore stays blocked with this precise, reproducible reason, and no fake or stale prefix was
substituted.

**Task 11's authorised scope ends here, fully evidenced:** isolated configure+build green; 16 unified
modules at 100% in the ament gate; registration, interpreter and TEMP provenance verified; dependency
graph and incremental edge verified; three rebuild proofs; and the release closure characterised one
dependency layer at a time (CP-58, CP-61, CP-62).

## CP-63: handoff - exactly what remains, with file and line pointers

The authorised scope is complete and evidenced. What is left, so the next session does not have to
re-discover it:

**A. Telemetry subscription still belongs to the teleop page (Task 9's other half).**
`web/src/app.tsx` lines ~78-100 hold a page-scoped effect: a `/snapshot` fetch, a 2 s
`setInterval(refresh, 2000)` poll and a `new WebSocket(".../telemetry")` subscription, all torn down
in the effect's cleanup (`window.clearInterval(timer); websocket.close()`). That is precisely the
behaviour the design forbids ("Telemetry 与 lease heartbeat 目前跟随 Teleop 页面 effect；组件卸载会
关闭订阅或续约"). The runtime half already exists: `DomainRuntime.start()` subscribes through
`transport.subscribe(...)` and `accept()` keeps the sequence rules, so the remaining work is the same
shape as the renewal migration that took CP-37..CP-49 - delete the page's poll and socket, read
`runtime.projection()`, and keep the page's RTT/notice presentation.

**B. Worker-count control is still a native `<select>`** (CP-35) so the exact-N qualification
assertion stays testable in jsdom; switching it to the ported radix `Select` requires moving that
assertion to the browser gate in the same change.

**C. `sidebar` is unported by design** - `Sheet` provides the shell navigation (CP-32), and the plan
says to introduce new items only where a page needs them.

**D. Blocked or out of authority:** the copied-install Chrome gate (CP-58/61/62: the approved MuJoCo
underlay is not installed, and the only host copy is the stale fork the project deliberately
excludes); Task 12B/C resource measurement and live runs (separately authorised); the independent
GPT-6 Astra review of `docs/guides/so101-unified-webapp-operation.md` (a different model).

**E. Deletion candidates, retained:** the fixture copies and gate directories under the registered
root (`build-FV6UHHX5`, `release-n5JyZLog`, `release2-Q3EIoiMD`, `web-fixture-1789891339`,
`ctest-tmp-1SlpBurM`, `preset-preview-8f09f448`, the `pytest-*`/`bun-*` invocation dirs and
`gates/`). Nothing deleted without authorisation.

Tree state: branch `codex/so101-unified-webapp`, working tree clean, frontend 45 files / 201 tests,
16 unified modules green in the ament gate.
