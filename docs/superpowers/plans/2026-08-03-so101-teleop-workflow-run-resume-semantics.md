# SO-101 Teleop Workflow Run/Resume Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Teleop `Start`, `Run`, and `Resume` enforce distinct checkpoint semantics in both the Web UI and server: Start begins one step, Run begins a full workflow from scratch, and Resume continues only an existing workflow.

**Architecture:** Keep the C++ `pick_place_state_machine` as the sole transition owner. The Python Teleop service owns workflow identity, checkpoint path, and operation-to-CLI argument mapping; the React UI renders a server-backed button state matrix and clears its workflow snapshot only after a successful Reset response.

**Tech Stack:** Python 3.12, asyncio, FastAPI service boundary, pytest, React 18, TypeScript, Vitest/Testing Library, Playwright, Bun, ROS 2 Jazzy, colcon.

## Global Constraints

- Read and follow repository `AGENTS.md`, `src/so101_gazebo_demo/AGENTS.md`, and `.agents/skills/so101-dev/SKILL.md` before task actions.
- Execute in an isolated branch/worktree created with `superpowers:using-git-worktrees`; use branch `codex/teleop-workflow-run-resume-semantics` from the current ai-station `main`.
- Preserve every pre-existing dirty file and worktree. In particular, do not modify or clean `.worktrees/reset-world-parking-fix` or the running Teleop process sourced from it.
- Do not start a second Gazebo, MoveIt, RViz, controller, or Teleop stack. Inventory existing processes, ROS graph, tmux sessions, and installed provenance first.
- Work only in `src/so101_gazebo_demo`; do not change the C++ transition table, motion policies, robot actions, MoveIt/Gazebo execution, Force Continue policy, or unrelated fingertip geometry work.
- Run strict RED -> GREEN cycles. Save failing and passing command output under one `/tmp/so101-debug-workflow-semantics-<timestamp>/` evidence directory.
- `Start` creates a workflow and invokes `--step` without `--resume`.
- `Run` creates a workflow and invokes neither `--step` nor `--resume`; it is rejected while the current simulation session already has a workflow.
- `Resume` requires an existing valid `run_id` and invokes `--resume true` without `--step`; it never creates a workflow.
- After a workflow begins, Start and Run are disabled. At `DONE`, only Reset workflow remains enabled. A successful Reset returns the UI to Start/Run enabled and Resume disabled.
- Lease, readiness, simulation-session, checkpoint freshness, action/controller, and Force Continue gates remain fail closed.
- Do not push. Make focused commits on the feature branch and report their hashes.

---

### Task 1: Enforce Start, Run, and Resume semantics at the Teleop service boundary

**Files:**
- Modify: `src/so101_gazebo_demo/test/teleop/test_server_safety.py:190-224`
- Modify: `src/so101_gazebo_demo/so101_teleop/server.py:619-643`

**Interfaces:**
- Consumes: `TeleopService.command(name: str, body: dict) -> CommandResult`, `self._workflow: dict[str, tuple[Path, str]]`, and `RosTelemetryWorker.package_cli(executable, arguments, timeout_s)`.
- Produces: explicit `workflow_start`, `workflow_run`, and `workflow_resume` server contracts; new rejection code `WORKFLOW_ALREADY_STARTED`.

- [ ] **Step 1: Establish isolated execution and a clean relevant baseline**

Use `superpowers:using-git-worktrees` from `/data/work/ws_moveit`. Verify `.worktrees/` is ignored, create `.worktrees/teleop-workflow-run-resume-semantics` on branch `codex/teleop-workflow-run-resume-semantics`, then record:

```bash
pwd
git rev-parse HEAD
git branch --show-current
git status --short
git worktree list
tmux list-sessions
pgrep -af 'gz sim|move_group|rviz2|pick_place_state_machine|so101_teleop'
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_moveit/install/setup.zsh
ros2 pkg prefix so101_gazebo_demo
ros2 node list | sort
```

From the isolated worktree package directory, run the current workflow-focused baseline and save its output:

```bash
cd src/so101_gazebo_demo
PYTHONPATH=. python3 -m pytest -q test/teleop/test_server_safety.py -k workflow
```

Expected: existing workflow tests pass. If the baseline fails for an unrelated reason, stop and report the exact failure instead of modifying production code.

- [ ] **Step 2: Write failing service tests for fresh Run and invalid Run/Resume states**

Add behavior tests beside `test_workflow_step_resumes_the_existing_cpp_checkpoint_before_single_step`. Use a real `TeleopService` and fake only the external C++ process boundary through `Worker.package_cli`:

```python
def test_workflow_run_creates_a_fresh_run_without_step_or_resume_flags():
    """Run owns a new checkpoint and executes the workflow from the beginning."""
    async def scenario():
        worker = Worker()
        calls = []

        def owner(executable, arguments, timeout_s=45.0):
            calls.append((executable, list(arguments), timeout_s))
            return "trace=IDLE -> PREPARE_OPEN_GRIPPER -> DONE"

        worker.package_cli = owner
        service = TeleopService(worker)
        lease_id = await lease(service)
        result = await service.command("workflow_run", {
            "command_id": "workflow-run",
            "lease_id": lease_id,
            "session_id": "sim-a",
        })

        assert result.succeeded is True
        assert result.data["workflow"]["run_id"] in service._workflow
        assert calls[0][0] == "pick_place_state_machine"
        assert "--step" not in calls[0][1]
        assert "--resume" not in calls[0][1]

    asyncio.run(scenario())


def test_workflow_run_cannot_replace_an_existing_workflow():
    """Run must not silently overwrite a workflow checkpoint after Start."""
    async def scenario():
        worker = Worker()
        calls = []

        def owner(executable, arguments, timeout_s=45.0):
            calls.append((executable, list(arguments), timeout_s))
            return "trace=IDLE -> PREPARE_OPEN_GRIPPER"

        worker.package_cli = owner
        service = TeleopService(worker)
        lease_id = await lease(service)
        started = await service.command("workflow_start", {
            "command_id": "workflow-start",
            "lease_id": lease_id,
            "session_id": "sim-a",
        })
        original = dict(service._workflow)
        rejected = await service.command("workflow_run", {
            "command_id": "workflow-run",
            "lease_id": lease_id,
            "session_id": "sim-a",
        })

        assert started.succeeded is True
        assert rejected.succeeded is False
        assert rejected.code == "WORKFLOW_ALREADY_STARTED"
        assert service._workflow == original
        assert len(calls) == 1

    asyncio.run(scenario())


def test_workflow_resume_requires_an_existing_run_and_uses_resume_only():
    """Resume continues an existing checkpoint and never creates one implicitly."""
    async def scenario():
        worker = Worker()
        calls = []

        def owner(executable, arguments, timeout_s=45.0):
            calls.append((executable, list(arguments), timeout_s))
            return "trace=IDLE -> PREPARE_OPEN_GRIPPER"

        worker.package_cli = owner
        service = TeleopService(worker)
        lease_id = await lease(service)
        missing = await service.command("workflow_resume", {
            "command_id": "workflow-resume-missing",
            "lease_id": lease_id,
            "session_id": "sim-a",
        })
        assert missing.succeeded is False
        assert missing.code == "WORKFLOW_RUN_MISMATCH"
        assert service._workflow == {}
        assert calls == []

        started = await service.command("workflow_start", {
            "command_id": "workflow-start",
            "lease_id": lease_id,
            "session_id": "sim-a",
        })
        resumed = await service.command("workflow_resume", {
            "command_id": "workflow-resume",
            "lease_id": lease_id,
            "session_id": "sim-a",
            "run_id": started.data["workflow"]["run_id"],
        })
        assert resumed.succeeded is True
        assert calls[1][1][-2:] == ["--resume", "true"]
        assert "--step" not in calls[1][1]

    asyncio.run(scenario())
```

- [ ] **Step 3: Run the new tests and capture the expected RED failures**

```bash
PYTHONPATH=. python3 -m pytest -q test/teleop/test_server_safety.py \
  -k 'workflow_run or workflow_resume_requires'
```

Expected RED boundaries:

- fresh `workflow_run` returns `WORKFLOW_RUN_MISMATCH` instead of creating a run;
- `workflow_run` after Start reaches the wrong branch/code instead of `WORKFLOW_ALREADY_STARTED`;
- no production change has yet made Run a fresh-run operation.

Save the full output and exit code in the evidence directory. A test error caused by syntax or fixture setup is not an acceptable RED result.

- [ ] **Step 4: Implement the minimal server-side branch split**

In `TeleopService.command`, replace the `operation == "start"` creation branch with an explicit fresh-operation branch:

```python
operation = name.removeprefix("workflow_")
session_id = self._worker.snapshot().simulation_session_id
if operation in ("start", "run"):
    if any(workflow_session == session_id
           for _, workflow_session in self._workflow.values()):
        return self._result(
            body, False, "WORKFLOW_ALREADY_STARTED",
            "reset the existing workflow before starting a new one",
        )
    run_id = str(uuid.uuid4())
    checkpoint = Path("/tmp") / f"so101-teleop-workflow-{run_id}.json"
    self._workflow[run_id] = (checkpoint, session_id)
else:
    run_id = body.get("run_id", "")
    entry = self._workflow.get(run_id)
    if entry is None:
        return self._result(
            body, False, "WORKFLOW_RUN_MISMATCH", "unknown workflow run"
        )
    checkpoint, session = entry
    if session != session_id:
        return self._result(
            body, False, "SESSION_MISMATCH", "workflow session invalidated"
        )
```

Keep the CLI mapping explicit:

```python
if operation == "start":
    args.append("--step")
if operation == "step":
    args.extend(["--resume", "true", "--step"])
if operation in ("resume", "force-continue"):
    args.extend(["--resume", "true"])
```

Do not add Run to the resume tuple. Do not change Force Continue or checkpoint validation.

- [ ] **Step 5: Verify GREEN and existing workflow regressions**

```bash
PYTHONPATH=. python3 -m pytest -q test/teleop/test_server_safety.py -k workflow
PYTHONPATH=. python3 -m pytest -q test/teleop/test_server_safety.py
```

Expected: all selected tests pass, including the existing Start/Step checkpoint test and lease-renewal-during-workflow test.

- [ ] **Step 6: Commit the server contract**

```bash
git add -- \
  src/so101_gazebo_demo/so101_teleop/server.py \
  src/so101_gazebo_demo/test/teleop/test_server_safety.py
git diff --cached --check
git commit -m "fix(so101): separate workflow run and resume semantics"
```

---

### Task 2: Render the workflow button state matrix in the Web UI

**Files:**
- Modify: `src/so101_gazebo_demo/web/src/components/teleop/workflow-panel.tsx:27-53`
- Modify: `src/so101_gazebo_demo/web/src/components/teleop/workflow-panel.test.tsx:8-26`

**Interfaces:**
- Consumes: `WorkflowPanel` props `snapshot?: any`, `leaseHeld: boolean`, and `command(operation, body?)`.
- Produces: UI-derived booleans `hasWorkflow`, `done`, `canBegin`, and `canContinue`; no state selection or transition logic.

- [ ] **Step 1: Replace the single pending test with behavior-focused state-matrix tests**

Add a small assertion helper only in the test file:

```typescript
const isDisabled = (name: string) =>
  (screen.getByRole("button", { name }) as HTMLButtonElement).disabled;
```

Add tests with literal expected states:

```typescript
it("enables Start and Run only before a workflow exists", () => {
  render(<WorkflowPanel leaseHeld command={vi.fn()} />);

  expect(isDisabled("Start")).toBe(false);
  expect(isDisabled("Run")).toBe(false);
  expect(isDisabled("Resume")).toBe(true);
  expect(isDisabled("Next Step")).toBe(true);
  expect(isDisabled("Reset workflow")).toBe(true);
});

it("enables Resume but not Start or Run after Start creates a workflow", () => {
  render(<WorkflowPanel
    snapshot={{ run_id: "run-1", current_state: "PREPARE_OPEN_GRIPPER" }}
    leaseHeld
    command={vi.fn()}
  />);

  expect(isDisabled("Start")).toBe(true);
  expect(isDisabled("Run")).toBe(true);
  expect(isDisabled("Resume")).toBe(false);
  expect(isDisabled("Next Step")).toBe(false);
  expect(isDisabled("Reset workflow")).toBe(false);
});

it("leaves only Reset workflow enabled when the workflow is done", () => {
  render(<WorkflowPanel
    snapshot={{ run_id: "run-1", current_state: "DONE" }}
    leaseHeld
    command={vi.fn()}
  />);

  expect(isDisabled("Start")).toBe(true);
  expect(isDisabled("Run")).toBe(true);
  expect(isDisabled("Resume")).toBe(true);
  expect(isDisabled("Next Step")).toBe(true);
  expect(isDisabled("Stop")).toBe(true);
  expect(isDisabled("Reset workflow")).toBe(false);
});
```

Retain the pending-operation coverage, but render without a workflow and click Start; while the promise is unresolved, assert every workflow button is disabled, then resolve it and assert Start/Run return to enabled.

- [ ] **Step 2: Run the component test and capture RED**

```bash
cd web
bun run test -- src/components/teleop/workflow-panel.test.tsx
```

Expected RED: initial Run is disabled; Start remains enabled with an existing workflow; Resume/Next Step/Stop remain enabled at `DONE`.

- [ ] **Step 3: Implement the state booleans and apply them to buttons**

Add, next to `pending`:

```typescript
const hasWorkflow = Boolean(snapshot?.run_id);
const done = snapshot?.current_state === "DONE";
const canBegin = leaseHeld && !hasWorkflow && !pending;
const canContinue = leaseHeld && hasWorkflow && !done && !pending;
const canReset = leaseHeld && hasWorkflow && !pending;
```

Map buttons exactly:

```tsx
<Button disabled={!canBegin} onClick={() => void execute("start")}>{label("start")}</Button>
<Button disabled={!canContinue} onClick={() => void execute("step", { snapshot_revision: snapshot?.snapshot_revision })}>{label("step")}</Button>
<Button disabled={!canBegin} onClick={() => void execute("run")}>{label("run")}</Button>
<Button disabled={!canContinue} variant="outline" onClick={() => void execute("stop")}>{label("stop")}</Button>
<Button disabled={!canContinue} onClick={() => void execute("resume")}>{label("resume")}</Button>
<ConfirmAction label="Reset workflow" disabled={!canReset} onConfirm={() => void execute("reset")}/>
```

Do not infer a next robot state in React. Leave `Force Continue` visibility and typed confirmation unchanged.

- [ ] **Step 4: Verify GREEN and the full Vitest suite**

```bash
bun run test -- src/components/teleop/workflow-panel.test.tsx
bun run test
```

Expected: component tests and all Vitest tests pass with no warnings or unhandled errors.

- [ ] **Step 5: Commit the state matrix**

```bash
git add -- \
  src/so101_gazebo_demo/web/src/components/teleop/workflow-panel.tsx \
  src/so101_gazebo_demo/web/src/components/teleop/workflow-panel.test.tsx
git diff --cached --check
git commit -m "fix(so101): gate workflow controls by lifecycle"
```

---

### Task 3: Clear workflow state after Reset and verify the browser flow

**Files:**
- Modify: `src/so101_gazebo_demo/web/src/app.tsx:140-143`
- Modify: `src/so101_gazebo_demo/web/e2e/teleop.spec.ts:88-132`

**Interfaces:**
- Consumes: `call(path, body) -> Promise<CommandResult>` and `setWorkflow` React state setter.
- Produces: `workflowCommand(...) -> Promise<void>` that clears the browser snapshot only after a successful `/workflow/reset` response.

- [ ] **Step 1: Extend the Playwright operator-flow test with the lifecycle contract**

In the POST route mock, add a full Run response:

```typescript
if (path === "/workflow/run") {
  return route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      code: "OK",
      succeeded: true,
      snapshot_revision: 125,
      data: { workflow: { run_id: "run-full", current_state: "DONE", next_state: null } },
    }),
  });
}
```

Around the existing Workflow actions, assert this exact sequence:

```typescript
await expect(page.getByRole("button", { name: "Start" })).toBeEnabled();
await expect(page.getByRole("button", { name: "Run" })).toBeEnabled();
await expect(page.getByRole("button", { name: "Resume" })).toBeDisabled();

await page.getByRole("button", { name: "Start" }).click();
await expect(page.getByRole("button", { name: "Start" })).toBeDisabled();
await expect(page.getByRole("button", { name: "Run" })).toBeDisabled();
await expect(page.getByRole("button", { name: "Resume" })).toBeEnabled();

await page.getByRole("button", { name: "Reset workflow" }).click();
await page.getByRole("button", { name: "Confirm Reset workflow" }).click();
await expect.poll(() => payloads.at(-1)?.body.confirmation)
  .toBe("CONFIRM WORKFLOW_RESET");
await expect(page.getByRole("button", { name: "Start" })).toBeEnabled();
await expect(page.getByRole("button", { name: "Run" })).toBeEnabled();
await expect(page.getByRole("button", { name: "Resume" })).toBeDisabled();

await page.getByRole("button", { name: "Run" }).click();
await expect.poll(() => payloads.at(-1)?.path).toBe("/workflow/run");
expect(payloads.at(-1)?.body.run_id).toBeUndefined();
await expect(page.getByRole("button", { name: "Resume" })).toBeDisabled();
await expect(page.getByRole("button", { name: "Reset workflow" })).toBeEnabled();
```

- [ ] **Step 2: Run Playwright and capture RED at Reset state clearing**

```bash
bun run test:e2e -- --grep "operator controls preserve targets"
```

Expected RED: after successful Reset, the old `workflow` React state remains present, so Start and Run stay disabled and Resume remains enabled.

- [ ] **Step 3: Clear the workflow snapshot only after successful Reset**

Change `workflowCommand` to inspect the real command result:

```typescript
const workflowCommand = async (operation: string, body: Record<string, unknown> = {}) => {
  const confirmation = operation === "reset" ? { confirmation: "CONFIRM WORKFLOW_RESET" } : {};
  const result = await call(`/workflow/${operation}`, {
    ...body,
    ...confirmation,
    run_id: workflow?.run_id,
  });
  if (operation === "reset" && result.succeeded) setWorkflow(undefined);
};
```

Do not clear workflow state on a rejected Reset response.

- [ ] **Step 4: Verify GREEN, full browser suite, and production build**

```bash
bun run test:e2e -- --grep "operator controls preserve targets"
bun run test:e2e
bun run build
```

Expected: all Playwright tests pass, browser console/page error arrays remain empty, and TypeScript/Vite production build exits 0.

- [ ] **Step 5: Commit Reset lifecycle handling**

```bash
git add -- \
  src/so101_gazebo_demo/web/src/app.tsx \
  src/so101_gazebo_demo/web/e2e/teleop.spec.ts
git diff --cached --check
git commit -m "fix(so101): clear workflow controls after reset"
```

---

### Task 4: Update operator documentation and run package-level verification

**Files:**
- Modify: `src/so101_gazebo_demo/docs/so101-teleop-web-ui.md:403-445`

**Interfaces:**
- Consumes: the implemented server and UI behavior from Tasks 1-3.
- Produces: operator-facing definitions and final package/build evidence.

- [ ] **Step 1: Update the workflow documentation with exact semantics**

Replace the three ambiguous definitions with:

```markdown
- **Start**：仅在 workflow 尚未开始时可用；创建新的 run/checkpoint，并执行第一个单步请求。
- **Run**：仅在 workflow 尚未开始时可用；创建新的 run/checkpoint，从头连续执行到结束或首个失败边界。
- **Resume**：仅在已有 workflow checkpoint 时可用；从当前 checkpoint 连续执行到结束或首个失败边界。
```

Add one sentence after the list:

```markdown
Start 或 Run 后，二者保持禁用直到 Reset workflow；到达 DONE 后只保留 Reset workflow 可用。
```

Update the `WORKFLOW_RUN_MISMATCH` row to say an invalid Resume requires the current valid run, while a new Start/Run requires Reset workflow first. Do not change Force Continue guidance.

- [ ] **Step 2: Run formatting and focused source checks**

```bash
git diff --check
PYTHONPATH=. python3 -m pytest -q test/teleop/test_server_safety.py
cd web
bun run test
bun run test:e2e
bun run build
```

Expected: every command exits 0; record exact test counts from output rather than copying historical counts.

- [ ] **Step 3: Build and run the ROS package test suite from the isolated overlay**

From the isolated worktree root, use isolated `build/`, `install/`, and `log/` directories. Do not overwrite `/data/work/ws_moveit/install` while the existing stack is active:

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test \
  --packages-select so101_gazebo_demo \
  --event-handlers console_direct+
colcon test-result --verbose
ros2 pkg prefix so101_gazebo_demo
```

Expected: package prefix points to the isolated worktree install; zero new test failures. If unrelated baseline tests fail, preserve exact logs and separate them from feature-specific results rather than claiming full package success.

- [ ] **Step 4: Commit operator documentation**

```bash
git add -- src/so101_gazebo_demo/docs/so101-teleop-web-ui.md
git diff --cached --check
git commit -m "docs(so101): clarify workflow execution controls"
```

- [ ] **Step 5: Audit scope before live acceptance**

```bash
git status --short
git log --oneline --decorate main..HEAD
git diff --check main...HEAD
git diff --stat main...HEAD
```

Expected: only the server, its workflow tests, WorkflowPanel/tests, app/e2e, and Teleop operator documentation changed. No motion policy, geometry, reset-worktree, generated build output, screenshots, or credentials are committed.

---

### Task 5: Perform controlled ai-station runtime and visual acceptance

**Files:**
- Evidence only: `/tmp/so101-debug-workflow-semantics-<timestamp>/`
- No source changes unless a new RED test first demonstrates a feature defect.

**Interfaces:**
- Consumes: isolated installed overlay and existing ai-station Gazebo/MoveIt stack.
- Produces: runtime provenance, HTTP/CLI evidence, ROS/MoveIt/controller/Gazebo/Planning Scene evidence, and fresh screenshots.

- [ ] **Step 1: Re-inventory the existing stack and define a controlled Teleop switch**

Record exact PIDs, tmux owners, `ROS_DOMAIN_ID`, `GZ_PARTITION`, package prefix, running Teleop executable path, and current session. The running Teleop currently comes from `.worktrees/reset-world-parking-fix`; do not stop or replace it without resolving its exact PID/session and preserving that worktree.

If controlled restart would interrupt unrelated active work, stop here and report the blocker. Do not start a parallel backend on the same ROS/Gazebo domain.

- [ ] **Step 2: Start the feature Teleop from the isolated overlay in the existing Teleop tmux owner**

Only after the prior Teleop process is identified and intentionally stopped, source:

```bash
source ~/gui-env.zsh
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_moveit/.worktrees/teleop-workflow-run-resume-semantics/install/setup.zsh
```

Launch with the existing `ROS_DOMAIN_ID`, `GZ_PARTITION`, bind address, port, and simulation session contract. Confirm `ros2 pkg prefix so101_gazebo_demo` and the running server path point to the feature overlay before testing.

- [ ] **Step 3: Capture initial state and verify Run/Resume API semantics**

Use the live UI/API without selecting a robot state in the browser:

1. Acquire lease.
2. Capture a fresh screenshot showing Start and Run enabled, Resume disabled.
3. Call Start, record `run_id`, checkpoint path, owner command arguments, and returned current state.
4. Confirm Start and Run are disabled while Resume is enabled.
5. Call Resume and confirm the same `run_id` and `--resume true` are used.
6. Reset workflow with the exact confirmation and confirm the initial button matrix returns.
7. Call Run and confirm a new `run_id`, no `--step`, no `--resume`, and execution from the initial state.
8. At `DONE`, confirm only Reset workflow remains enabled.

Do not use Force Continue to make the acceptance pass.

- [ ] **Step 4: Gather layered robot evidence and fresh visual proof**

For any executed workflow, independently record the relevant state-machine trace, MoveIt plan/execute result, controller/joint/TF changes, Gazebo object pose and attachment, and MoveIt Planning Scene attachment. Use `/snapshot` and bounded one-shot ROS samples with the active domain/partition.

Run the repository screenshot helper after each required UI state:

```bash
./scripts/capture-ai-station.sh
```

Actually inspect the new images. Report exactly which buttons are enabled/disabled and, if a workflow executed, the visible arm/gripper/object state. A generated file or live process alone is not visual acceptance.

- [ ] **Step 5: Restore or preserve the pre-existing runtime intentionally**

Stop only feature processes whose PID/session ownership was recorded. If the previous Teleop must be restored, source its original overlay and verify its PID/path/session. Re-list related processes and ROS nodes; leave the shared Gazebo/MoveIt stack and unrelated tmux sessions intact.

- [ ] **Step 6: Produce the final evidence report**

Report:

```text
Root cause: CONFIRMED | NOT CONFIRMED
First bad boundary:
Evidence directory:
RED commands and expected failures:
GREEN focused/full test commands and exact counts:
Feature branch and commits:
Runtime command, provenance, and exit code:
Start/Run/Resume API argument proof:
MoveIt proof:
Controller/joint/TF proof:
Gazebo proof:
Planning Scene proof:
Visual proof and fresh screenshot paths:
Preserved user worktrees/changes:
Remaining risks or next exact command:
```

Do not push or merge. Do not claim completion if runtime provenance, the button screenshots, or any relevant robot evidence is missing.
