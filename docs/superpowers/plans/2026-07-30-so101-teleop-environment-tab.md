# SO-101 Teleop Environment Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose a safe, read-only Environment tab containing the approved ROS/Gazebo environment allowlist without lengthening the Teleop header.

**Architecture:** Capture an immutable allowlisted environment map when `RosTelemetryWorker` starts, include it in every existing telemetry snapshot, and render it through a focused EnvironmentPanel. No new endpoint, mutable control, or complete process environment exposure is introduced.

**Tech Stack:** Python 3.12, Pydantic, FastAPI telemetry snapshots, React 18, TypeScript, shadcn Table/Tooltip/Button/Card/Tabs, Vitest, Playwright, Bun, ROS 2 Jazzy.

## Global Constraints

- Expose exactly the 13 environment keys approved by the design; never serialize complete `os.environ`.
- Header intentionally omits ROS/Gazebo environment values; they are available in the Environment tab.
- Missing values render as `—`; environment values are read-only.
- Long values must not cause page-level horizontal overflow.
- Use Bun and `bun.lock`; do not use npm/npx or `package-lock.json`.
- Reuse the single live stack; restart only the owned Teleop tmux session and do not execute robot actions or Attach.

---

### Task 1: Allowlisted backend environment telemetry

**Files:**
- Modify: `src/so101_gazebo_demo/so101_teleop/models.py`
- Modify: `src/so101_gazebo_demo/so101_teleop/server.py`
- Modify: `src/so101_gazebo_demo/test/teleop/test_server_safety.py`

**Interfaces:**
- Produces: `TELEOP_ENVIRONMENT_KEYS: tuple[str, ...]`, `read_teleop_environment(environment: Mapping[str, str]) -> dict[str, str]`, and `TelemetrySnapshot.environment: Dict[str, str]`.
- Consumers: Task 2 frontend snapshot types and Task 3 UI.

- [ ] **Step 1: Write failing backend tests**

Add tests that call the wished-for helper with all 13 allowed values plus `SECRET_TOKEN`, assert the exact ordered allowlist map is returned, assert `SECRET_TOKEN` is absent, and construct `RosTelemetryWorker` under `monkeypatch.setenv("ROS_DOMAIN_ID", "55")` / `monkeypatch.setenv("GZ_PARTITION", "partition-a")` to assert its initial snapshot contains those exact values.

```python
def test_telemetry_environment_is_allowlisted(monkeypatch):
    environment = {key: f"value-{index}" for index, key in enumerate(TELEOP_ENVIRONMENT_KEYS)}
    environment["SECRET_TOKEN"] = "must-not-leak"
    assert read_teleop_environment(environment) == {
        key: environment[key] for key in TELEOP_ENVIRONMENT_KEYS
    }
    assert "SECRET_TOKEN" not in read_teleop_environment(environment)
```

- [ ] **Step 2: Run RED test**

Run:

```bash
source /opt/ros/jazzy/setup.zsh
source install/setup.zsh
PYTHONNOUSERSITE=1 python3 -m pytest src/so101_gazebo_demo/test/teleop/test_server_safety.py -k environment -q
```

Expected: collection/import failure because `TELEOP_ENVIRONMENT_KEYS` and `read_teleop_environment` do not exist.

- [ ] **Step 3: Implement the minimal backend contract**

Define the tuple in the approved order, filter only present values, add `environment` to `TelemetrySnapshot`, capture it in `RosTelemetryWorker.__init__`, seed `_latest` with it, and pass the same immutable copy to `_publish_snapshot`.

```python
TELEOP_ENVIRONMENT_KEYS = (
    "ROS_DOMAIN_ID", "ROS_DISTRO", "ROS_VERSION", "ROS_PYTHON_VERSION",
    "ROS_AUTOMATIC_DISCOVERY_RANGE", "AMENT_PREFIX_PATH", "COLCON_PREFIX_PATH",
    "GZ_PARTITION", "GZ_CONFIG_PATH", "GZ_SIM_RESOURCE_PATH",
    "GZ_SIM_SYSTEM_PLUGIN_PATH", "PYTHONPATH", "LD_LIBRARY_PATH",
)

def read_teleop_environment(environment: Mapping[str, str]) -> dict[str, str]:
    return {key: environment[key] for key in TELEOP_ENVIRONMENT_KEYS if environment.get(key)}
```

- [ ] **Step 4: Run GREEN backend tests**

Run the RED command again, then run:

```bash
PYTHONNOUSERSITE=1 python3 -m pytest src/so101_gazebo_demo/test/teleop -q
```

Expected: all Teleop Python tests pass with no environment leakage assertion failure.

### Task 2: Frontend types and EnvironmentPanel

**Files:**
- Modify: `src/so101_gazebo_demo/web/src/api/types.ts`
- Create: `src/so101_gazebo_demo/web/src/components/teleop/environment-panel.tsx`
- Create: `src/so101_gazebo_demo/web/src/components/teleop/environment-panel.test.tsx`

**Interfaces:**
- Consumes: `TelemetrySnapshot.environment: Record<string, string>` from Task 1.
- Produces: `EnvironmentPanel({ environment }: { environment: Record<string, string> })` and exported `TELEOP_ENVIRONMENT_KEYS` for stable display order.

- [ ] **Step 1: Write failing component tests**

Assert the panel renders all 13 labels in order, uses `—` for a missing value, retains the full long value in a tooltip/title, and calls `navigator.clipboard.writeText(fullValue)` from the matching Copy button.

```tsx
render(<EnvironmentPanel environment={{ ROS_DOMAIN_ID: "55", LD_LIBRARY_PATH: longValue }} />);
expect(screen.getAllByTestId("environment-key").map((node) => node.textContent)).toEqual(TELEOP_ENVIRONMENT_KEYS);
expect(screen.getByText("55")).toBeVisible();
await user.click(screen.getByRole("button", { name: "Copy LD_LIBRARY_PATH" }));
expect(navigator.clipboard.writeText).toHaveBeenCalledWith(longValue);
```

- [ ] **Step 2: Run RED component test**

Run:

```bash
export PATH=/home/lenovo/.bun/bin:$PATH
bun run test -- src/components/teleop/environment-panel.test.tsx
```

Expected: FAIL because `environment-panel.tsx` does not exist.

- [ ] **Step 3: Implement the focused panel**

Compose existing `Card`, `Table`, `Tooltip`, and `Button`. Use a fixed ordered key list, `min-w-0`, `break-all`, an internal `overflow-x-auto` wrapper, and accessible Copy labels. Keep full values in the DOM title/tooltip while the visible cell remains bounded.

- [ ] **Step 4: Run GREEN component test**

Run the RED command again. Expected: the new component tests pass.

### Task 3: Header and top-level tab integration

**Files:**
- Modify: `src/so101_gazebo_demo/web/src/components/teleop/connection-header.tsx`
- Modify: `src/so101_gazebo_demo/web/src/components/teleop/connection-header.test.tsx`
- Modify: `src/so101_gazebo_demo/web/src/app.tsx`
- Modify: `src/so101_gazebo_demo/web/e2e/teleop.spec.ts`

**Interfaces:**
- Consumes: `EnvironmentPanel` and `snapshot.environment`.
- Produces: eighth `Environment` tab; the header remains limited to existing session/revision/RTT metadata.

- [ ] **Step 1: Write RED header and E2E assertions**

Update the header unit test to assert metadata omits `ROS domain` and `GZ partition`. Extend the Playwright snapshot fixture with all allowlisted keys; assert the Environment tab is clickable, exactly one selected panel is visible, a long value is present through its title, Copy works, and `document.documentElement.scrollWidth <= clientWidth`.

- [ ] **Step 2: Run RED frontend tests**

Run:

```bash
export PATH=/home/lenovo/.bun/bin:$PATH
bun run test -- src/components/teleop/connection-header.test.tsx
bun run test:e2e
```

Expected: unit failure while the old header still repeats the environment values and E2E failure because the Environment tab is absent.

- [ ] **Step 3: Implement minimal integration**

Extend `ConnectionHeader` props and metadata text, pass values from `snapshot.environment ?? {}`, add `['environment', 'Environment']` to the tab list, and render:

```tsx
<TabsContent value="environment">
  <EnvironmentPanel environment={snapshot.environment ?? {}} />
</TabsContent>
```

- [ ] **Step 4: Run GREEN frontend tests and build**

Run:

```bash
export PATH=/home/lenovo/.bun/bin:$PATH
bun run test
bun run test:e2e
bun run build
```

Expected: Vitest, all Playwright tests, TypeScript, and Vite build pass.

### Task 4: Generated schema, documentation, package verification, and live acceptance

**Files:**
- Modify: `src/so101_gazebo_demo/so101_teleop/openapi.json`
- Modify: `src/so101_gazebo_demo/web/src/api/schema.d.ts`
- Modify: `src/so101_gazebo_demo/docs/so101-teleop-web-ui.md`
- Test: `src/so101_gazebo_demo/test/teleop/test_openapi_export.py`

**Interfaces:**
- Consumes: completed backend/frontend contract.
- Produces: installed bundle and live operator evidence.

- [ ] **Step 1: Regenerate API artifacts and document behavior**

Use the repository export command discovered in `test_openapi_export.py`, regenerate TypeScript through the Bun `generate:api` script, and document the Environment tab, the 13-key allowlist, missing-value behavior, header omission, and read-only/no-secret boundary in the canonical Chinese guide.

- [ ] **Step 2: Run package verification**

Run:

```bash
source /opt/ros/jazzy/setup.zsh
export PATH=/home/lenovo/.bun/bin:$PATH
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
ROS_DOMAIN_ID=179 GZ_PARTITION=so101_environment_test PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo
colcon test-result --all --verbose
git diff --check
```

Expected: build succeeds and package test result reports zero errors and zero failures.

- [ ] **Step 3: Restart only Teleop and verify live data**

Confirm one existing Gazebo/MoveIt/Teleop stack, then recreate only tmux `so101-teleop-live-final` after sourcing `~/gui-env.zsh`, ROS Jazzy, and the rebuilt overlay with `ROS_DOMAIN_ID=55` and `GZ_PARTITION=so101_teleop_live_final`. Poll `/snapshot` until READY and assert environment contains both exact values and no non-allowlisted keys.

- [ ] **Step 4: Perform fresh visual acceptance**

Use the existing visible Chrome/CDP path with bounded load waits, select Environment, observe for at least 10 seconds, verify no console/page errors or page-level horizontal overflow, save a fresh full-page PNG under `/tmp/so101-environment-evidence/`, and actually inspect the image for the compact header and Environment table.

- [ ] **Step 5: Commit implementation**

Review `git status --short`, stage only the approved source/config/docs/tests, and commit with:

```bash
git commit -m "feat(so101): expose teleop runtime environment"
```
