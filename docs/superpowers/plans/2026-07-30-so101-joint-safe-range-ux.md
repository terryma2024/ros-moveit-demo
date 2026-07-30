# SO-101 Joint Safe-Range UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename arm-only actions, constrain all browser joint targets to a uniform two-degree inset from authoritative URDF limits, and report unreachable TCP targets as conflicts instead of service outages.

**Architecture:** `RosTelemetryWorker` publishes the existing `JointSample` limit fields from one backend SO-101 limit table matching the URDF. A focused TypeScript module derives safe bounds and clamps targets for the panel and YAML import paths. FastAPI classifies `MOVEIT_IK_FAILED_*` as an actionable 409 target conflict while preserving the exact MoveIt code.

**Tech Stack:** ROS 2 Jazzy, rclpy, FastAPI, React 18, TypeScript, Vitest, Testing Library, Playwright, colcon/ament.

## Global Constraints

- Every joint 1–6 uses a two-degree inset at both hard-limit boundaries.
- The backend telemetry is the hard-limit authority; the frontend contains no duplicate hard-limit table.
- Direct entry, one-degree trims, and Target YAML imports use the same clamp function.
- Missing or invalid limits disable the corresponding target editor.
- Keep one commit relative to baseline by amending the existing feature commit; do not push or merge.
- Live acceptance is simulation-only and must not execute Attach.

---

### Task 1: Publish authoritative joint limits

**Files:**
- Modify: `src/so101_gazebo_demo/so101_teleop/server.py`
- Modify: `src/so101_gazebo_demo/test/teleop/test_server_safety.py`

**Interfaces:**
- Produces: `SO101_JOINT_POSITION_LIMITS_RAD: dict[str, tuple[float, float]]`
- Produces: every `_on_joints` `JointSample` with `lower_limit_rad` and `upper_limit_rad`

- [ ] Add a failing test that feeds joints 1–6 through `_on_joints` and asserts exact lower/upper values matching the design table.
- [ ] Run the focused pytest and verify the current `None` values produce RED.
- [ ] Add the immutable limit table and attach its values in `_on_joints`.
- [ ] Run the focused test and related telemetry/server tests to GREEN.

### Task 2: Clamp browser targets and rename arm actions

**Files:**
- Create: `src/so101_gazebo_demo/web/src/lib/joint-limits.ts`
- Create: `src/so101_gazebo_demo/web/src/lib/joint-limits.test.ts`
- Modify: `src/so101_gazebo_demo/web/src/components/teleop/joint-panel.tsx`
- Modify: `src/so101_gazebo_demo/web/src/components/teleop/joint-panel.test.tsx`

**Interfaces:**
- Produces: `JOINT_SAFETY_MARGIN_RAD`
- Produces: `safeJointBounds(sample): { lowerRad: number; upperRad: number } | undefined`
- Produces: `clampJointTarget(joint, value, sample): { value: number; clamped: boolean; message?: string }`
- JointPanel adds `onClampNotice(message: string): void`

- [ ] Add failing pure-function tests for a two-degree inset, pass-through, lower clamp, upper clamp, and unavailable limits.
- [ ] Add failing component tests for `Plan Arm` / `Execute Arm`, absent legacy labels, displayed safe range, input min/max, direct-entry clamp, trim clamp, notice, and disabled controls without limits.
- [ ] Run focused Vitest and verify failures are caused by missing behavior.
- [ ] Implement the minimal shared limit module and JointPanel integration.
- [ ] Run focused Vitest to GREEN and refactor only while it stays green.

### Task 3: Clamp Target YAML imports through the shared boundary

**Files:**
- Modify: `src/so101_gazebo_demo/web/src/app.tsx`
- Modify: `src/so101_gazebo_demo/web/src/components/teleop/tcp-panel.tsx`
- Modify: `src/so101_gazebo_demo/web/src/components/teleop/tcp-panel.test.tsx`
- Modify: `src/so101_gazebo_demo/web/e2e/teleop.spec.ts`

**Interfaces:**
- Consumes: `clampJointTarget` and live `snapshot.joints`
- Produces: imported targets clamped before `edit-joint` dispatch, with one aggregate visible notice

- [ ] Extend Playwright mock telemetry with hard limits and add a failing flow importing out-of-range joint values.
- [ ] Assert the resulting input equals the safe boundary, the clamp notice is visible, and any existing plan is stale.
- [ ] Run the focused Playwright test to RED.
- [ ] Apply the shared clamp function during import and pass clamp notices from JointPanel through `App`.
- [ ] Run the focused Playwright test to GREEN.

### Task 4: Classify unreachable TCP IK as a target conflict

**Files:**
- Modify: `src/so101_gazebo_demo/so101_teleop/api.py`
- Modify: `src/so101_gazebo_demo/test/teleop/test_api.py`
- Modify: `src/so101_gazebo_demo/web/src/app.tsx`
- Modify: `src/so101_gazebo_demo/web/src/main.tsx`
- Create: `src/so101_gazebo_demo/web/src/components/ui/sonner.tsx`
- Modify: `src/so101_gazebo_demo/web/e2e/teleop.spec.ts`
- Modify: `src/so101_gazebo_demo/docs/so101-teleop-web-ui.md`

**Interfaces:**
- Produces: `MOVEIT_IK_FAILED_*` response status 409 with unchanged body code
- Produces: one global official shadcn toast boundary containing every failed API response's `code` and `message`, including both `Execute All` sub-results
- Produces: 60-second IK request timeout and `Planning TCP…` duplicate-safe pending state

- [ ] Add a failing API test whose service returns `MOVEIT_IK_FAILED_-31` and assert HTTP 409 plus the exact code.
- [ ] Run the focused pytest and verify the current 503 produces RED.
- [ ] Add `MOVEIT_IK_` to the conflict classification without changing other 503 operational failures.
- [ ] Run focused API tests to GREEN.
- [ ] Add failing worker contract assertions for an IK request timeout of 60 seconds and a service wait budget greater than 60 seconds.
- [ ] Add a failing TCP component test that verifies `Planning TCP…` is visible and duplicate submission is disabled while pending.
- [ ] Set the IK request timeout to 60 seconds, permit the ROS call to finish, and wrap the App TCP plan promise in a `try/finally` pending state; run focused tests to GREEN.
- [ ] Under recorded Bun provenance, run official shadcn CLI info/docs/dry-run/add for Sonner through `bunx --bun` and inspect the diff.
- [ ] Add failing component/Playwright assertions that rejected TCP and non-TCP responses, plus an `Execute All` sub-result, display both machine code and message in a toast while successful responses do not.
- [ ] Mount the official Toaster once and emit error toasts from the shared command-result recording path; run the focused tests to GREEN.
- [ ] Document that the five-axis arm cannot satisfy every six-dimensional Pose6D target and that `-31` means no IK solution, not service downtime.

### Task 5: Documentation, complete verification, and live acceptance

**Files:**
- Modify: `src/so101_gazebo_demo/docs/so101-teleop-web-ui.md`
- Modify: `docs/superpowers/specs/2026-07-30-so101-joint-safe-range-ux-design.md`

**Interfaces:**
- Verifies all preceding runtime and UI contracts.

- [ ] Update the Chinese guide with Plan Arm / Execute Arm semantics, safe ranges, two-degree margin, clamping feedback, YAML behavior, and TCP `NO_IK_SOLUTION` diagnosis.
- [ ] Run complete Vitest, Playwright, and production build through Bun; keep `bun.lock` authoritative and verify launch-time Bun preflight.
- [ ] Run targeted Teleop Python tests, rebuild the installed overlay, and run the full isolated `so101_gazebo_demo` package suite plus `colcon test-result --all --verbose`.
- [ ] Restart only the owned Teleop tmux session; verify unique listener, READY telemetry, six non-null hard limits, HTTP 409 for a known unreachable plan-only TCP target, and no unsafe motion.
- [ ] Use visible Chrome/CDP and a fresh screenshot to inspect renamed actions, per-joint safe range, clamp feedback, no console errors, and no horizontal overflow.
- [ ] Refresh and verify the recoverable backup, stage only source/config/docs/tests, amend the existing feature commit, and audit baseline count 1 plus a clean worktree.
