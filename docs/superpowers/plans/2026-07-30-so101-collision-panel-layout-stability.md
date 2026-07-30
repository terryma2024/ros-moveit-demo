# SO-101 Collision Panel Stability and Launch-Time Web Build Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:executing-plans to implement this plan task-by-task. Use superpowers:test-driven-development for each behavior change, superpowers:systematic-debugging for failures, and superpowers:verification-before-completion before any completion claim.

**Goal:** Stabilize the Teleop collision/contact panel with official shadcn components and make `so101_teleop.launch.py` build a missing or stale production Web bundle before starting FastAPI.

**Architecture:** Keep telemetry data structured through `App` into `CollisionPanel`, format only at the presentation boundary, and constrain variable evidence inside fixed scroll areas. Use Bun consistently for Web work with `bun.lock` as the authoritative lockfile. Add a pure/testable Python bundle preflight that launch invokes synchronously; it validates or builds `web/dist`, then passes the verified path to the server through `SO101_TELEOP_WEB_ROOT`. Never start a Vite server and never recursively invoke colcon from launch.

**Tech Stack:** ROS 2 Jazzy launch, Python 3, pytest, FastAPI, React 18, TypeScript, Vite, Tailwind, official shadcn CLI/components, Vitest, Playwright.

**Repository constraint:** This work extends the existing single feature commit on `codex/direct-tpu-tongues`. Preserve unrelated files, stage only this feature's paths, and finish with `git commit --amend`; the branch must remain exactly one commit ahead of the recorded baseline.

---

### Task 1: Pin and verify the project Bun toolchain

**Files:**
- Create: `src/so101_gazebo_demo/web/bun.lock`
- Modify: `src/so101_gazebo_demo/web/package.json`
- Modify: `src/so101_gazebo_demo/docs/so101-teleop-web-ui.md`

1. Resolve the ai-station Bun executable without replacing system Node and record its absolute path and version.
2. Generate and retain `bun.lock` as the authoritative dependency lock; do not retain `package-lock.json` or use npm/npx for project operations.
3. Run `command -v bun` and `bun --version` and record the output.
4. Run official shadcn info/docs through `bunx --bun shadcn@latest`; save concise command/version evidence in the execution log, not generated registry dumps in Git.
5. Run the existing Web tests and build through Bun: `bun run test`, `bun run test:e2e`, `bun run build`.

### Task 2: Add official shadcn primitives without overwriting local behavior

**Files:**
- Modify: `src/so101_gazebo_demo/web/src/components/ui/card.tsx`
- Create/Modify: `src/so101_gazebo_demo/web/src/components/ui/badge.tsx`
- Create/Modify: `src/so101_gazebo_demo/web/src/components/ui/tooltip.tsx`
- Create/Modify: `src/so101_gazebo_demo/web/src/components/ui/scroll-area.tsx`
- Create/Modify: `src/so101_gazebo_demo/web/src/components/ui/empty.tsx`
- Create/Modify: `src/so101_gazebo_demo/web/src/components/ui/table.tsx`
- Modify: `src/so101_gazebo_demo/web/package.json`
- Modify: `src/so101_gazebo_demo/web/bun.lock`

1. Run `shadcn add card --dry-run` and `shadcn add card --diff`; inspect the delta against the existing Card before changing it.
2. Run dry-run for Badge, Tooltip, ScrollArea, Empty and Table, then add official components using the project package runner. If the registry lacks a named component, use the CLI docs' canonical composition and record that exception.
3. Merge CardHeader, CardDescription and CardContent into the existing Card while preserving existing classes relied on by Playwright.
4. Run the existing component and E2E tests. Do not proceed until current Button, AlertDialog and Card behavior remains green.

### Task 3: Drive CollisionPanel with structured telemetry (RED then GREEN)

**Files:**
- Modify: `src/so101_gazebo_demo/web/src/components/teleop/collision-panel.test.tsx`
- Modify: `src/so101_gazebo_demo/web/src/components/teleop/collision-panel.tsx`
- Modify: `src/so101_gazebo_demo/web/src/app.tsx`

1. Add failing tests for the approved props contract: `objectPose`, `controllers`, `sourceAges`, `moveit`, and `gazebo`. Assert raw JSON is absent; X/Y/Z, fixed controller labels, fixed ordered age labels and unavailable placeholders are present.
2. Add failing formatter cases: pose and age fixed decimals, `>99.999 s`, depth in millimetres, tiny negative depth normalized to `0.000 mm`, and exact source values available through Tooltip/title.
3. Implement exported pure formatters and structured subcomponents `TelemetrySummary` and `EvidencePane` using the official Card/Badge/Tooltip/ScrollArea/Empty/Table primitives.
4. Use `tabular-nums`, fixed/min widths, table-fixed, truncation and semantic theme tokens. Keep MoveIt and Gazebo simultaneously visible; use desktop two-column and mobile vertical layout, never Tabs.
5. Replace the `summary={JSON.stringify(...)}` call in `app.tsx` with direct structured snapshot props.
6. Run the focused test until green: `bun run test -- collision-panel.test.tsx`, then run all Vitest tests.

### Task 4: Prove layout stability in a real browser (RED then GREEN)

**Files:**
- Modify: `src/so101_gazebo_demo/web/e2e/teleop.spec.ts`

1. Add a Playwright test whose mocked `/snapshot` alternates between short and long ages, 0 and 20 evidence rows, and short and very long object names.
2. Before final layout fixes, run the test and confirm it detects the prior jump or horizontal overflow.
3. Assert the outer Collision Panel bounding-box height delta is at most 2 px after each update, `scrollWidth <= clientWidth`, both evidence headings remain visible, overflow is internal to each evidence pane, and no console/page errors occur.
4. Adjust only the panel layout until the new test passes. Run all Playwright tests and `bun run build`.

### Task 4A: Add official ButtonGroup and top-level Tabs (RED then GREEN)

**Files:**
- Create/Modify: `src/so101_gazebo_demo/web/src/components/ui/button-group.tsx`
- Create/Modify: `src/so101_gazebo_demo/web/src/components/ui/tabs.tsx`
- Modify: `src/so101_gazebo_demo/web/src/components/teleop/tcp-panel.tsx`
- Modify: `src/so101_gazebo_demo/web/src/components/teleop/tcp-panel.test.tsx`
- Modify: `src/so101_gazebo_demo/web/src/app.tsx`
- Modify: `src/so101_gazebo_demo/web/e2e/teleop.spec.ts`

1. Under recorded Bun provenance run official shadcn `info`, `docs button-group tabs`, and dry-run for both components through `bunx --bun`; add them without overwriting local Button behavior.
2. Add failing Vitest coverage for TCP frame buttons inside a ButtonGroup, visible/`aria-pressed` active state, and keyboard activation; implement the segmented control with the official primitive.
3. Add failing Playwright coverage for the seven top-level Tabs, default Joints, click and arrow-key switching, one visible panel at a time, Joint/TCP target persistence, narrow-screen internal tab-list scrolling without page overflow, and empty console/pageerror.
4. Keep ConnectionHeader and global controls outside Tabs; keep all telemetry/state/effects in `App`. Render each existing panel in its matching TabsContent and default to Joints.
5. Activate Collision before its layout-stability measurements. Run focused tests to GREEN, then all Vitest, Playwright, and production build.

### Task 4B: Stabilize ConnectionHeader action order (RED then GREEN)

**Files:**
- Create/Modify: `src/so101_gazebo_demo/web/src/components/teleop/connection-header.test.tsx`
- Modify: `src/so101_gazebo_demo/web/src/components/teleop/connection-header.tsx`
- Modify: `src/so101_gazebo_demo/web/e2e/teleop.spec.ts`

1. Add failing component assertions for title → mode Badge → lease button → metadata DOM order, a `shrink-0` action cluster and `min-w-0` metadata.
2. Add a Playwright regression alternating short/long session, revision, RTT and optional TTL-shaped metadata; assert lease-button x delta <=2 px and narrow-screen document overflow is absent.
3. Implement the stable action cluster and independently wrapping/truncating metadata without moving global controls into Tabs.
4. Run focused RED/GREEN, all Web tests/build, then repeat fresh live visual evidence.

### Task 5: Specify a testable Web bundle preflight (RED)

**Files:**
- Create: `src/so101_gazebo_demo/so101_teleop/web_bundle.py`
- Create: `src/so101_gazebo_demo/test/teleop/test_web_bundle.py`

1. Write unit tests with temporary fake Web roots and an injected command runner for: valid fresh bundle skips Bun; missing bundle builds; newer source/config builds; changed `bun.lock` triggers `bun install --frozen-lockfile`; unchanged dependency fingerprint skips install; build failure raises a typed error; missing/non-empty asset references fail validation.
2. Define explicit inputs: package/lock files, Vite/Tailwind/PostCSS/TypeScript configs, `index.html`, and `src/**`. Exclude `node_modules`, `dist`, E2E output and test artifacts.
3. Add tests for Bun selection order (`SO101_TELEOP_BUN`, pinned ai-station executable, PATH Bun) and reject missing/invalid executables with an actionable message.
4. Run `pytest -q src/so101_gazebo_demo/test/teleop/test_web_bundle.py` and confirm RED for missing implementation.

### Task 6: Implement bundle validation and incremental build (GREEN)

**Files:**
- Modify: `src/so101_gazebo_demo/so101_teleop/web_bundle.py`
- Modify: `src/so101_gazebo_demo/test/teleop/test_web_bundle.py`

1. Implement pure path discovery, input mtime/fingerprint, built-index asset parsing, Bun executable validation and dependency lock fingerprint helpers.
2. Implement `ensure_web_bundle(source_dir, build_if_needed, runner, env)` so fresh bundles return quickly; missing/stale bundles conditionally run Bun install and build; every successful return has revalidated assets.
3. Keep state marker inside ignored Web build state, not committed source. Include command, cwd and captured stderr in failures without leaking environment secrets.
4. Run focused pytest until all cases pass, then `python3 -m compileall` on the package.

### Task 7: Gate server startup in launch and expose the verified root (RED then GREEN)

**Files:**
- Modify: `src/so101_gazebo_demo/launch/so101_teleop.launch.py`
- Modify: `src/so101_gazebo_demo/so101_teleop/main.py`
- Modify: `src/so101_gazebo_demo/test/test_so101_launch_contract.py`
- Modify: `src/so101_gazebo_demo/test/teleop/test_server_safety.py`

1. Add failing tests that launch declares `build_web_if_needed=true` and `web_source_dir`; preflight runs before returning the server Node; failures prevent creation/start of that Node; the Node receives `SO101_TELEOP_WEB_ROOT`.
2. Add failing server tests that a valid `SO101_TELEOP_WEB_ROOT` overrides installed assets and an invalid override is rejected instead of silently falling back.
3. Implement an `OpaqueFunction` launch setup that resolves substitutions, calls `ensure_web_bundle`, and returns the FastAPI Node only after success. Raise a clear launch error on failure. Do not run `colcon`, do not run Vite, and do not start the server concurrently with the build.
4. Source discovery order: explicit launch argument, `SO101_TELEOP_WEB_SOURCE`, resolvable symlink-install source, then validated installed bundle. When only installed assets exist and are valid, serve them without build; when neither source nor bundle is valid, fail with the corrective launch argument.
5. Implement validated `SO101_TELEOP_WEB_ROOT` handling in `main.py`.
6. Run focused launch/server tests until green.

### Task 8: Align CMake, ignore rules, and operator documentation

**Files:**
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`
- Modify: `src/so101_gazebo_demo/.gitignore` or repository `.gitignore` only if current rules do not cover the generated marker/tool state
- Modify: `src/so101_gazebo_demo/test/test_package_layout.py`
- Modify: `src/so101_gazebo_demo/docs/so101-teleop-web-ui.md`
- Modify: `src/so101_gazebo_demo/README.md`

1. Ensure CMake builds with selected Bun or gives an actionable failure. Preserve reproducible `bun install --frozen-lockfile`, production build and installed `dist`.
2. Add package-layout contract assertions for the preflight module, launch arguments, Bun selection and canonical manual.
3. Document the single launch command, first-run/stale-build behavior, fresh skip message, Bun override, `web_source_dir`, failure recovery, and the redesigned Collision Panel.
4. Confirm generated `node_modules`, `dist`, dependency markers, Playwright artifacts and captures remain ignored; never commit downloaded tool binaries.

### Task 9: Static and isolated regression verification

1. Run `git diff --check` and review `git status --short` for unrelated/generated files.
2. Under recorded Bun provenance run `bun run test`, `bun run test:e2e`, and `bun run build`.
3. Source ROS Jazzy and the installed overlay; run targeted Python tests for Web bundle, server safety, package layout and launch contract.
4. Run the package's complete isolated test suite and `colcon test-result --verbose`; compare any failure against the pre-change baseline before attribution.
5. Build/install the package with `colcon build --packages-select so101_gazebo_demo --symlink-install`, source the new overlay, and verify installed Python/assets/docs provenance.

### Task 10: Live one-command acceptance and visual evidence

1. Inventory exact ROS/Gazebo/MoveIt/Teleop PIDs, tmux owners, domain and partition. Stop only the owned prior Teleop listener needed for this validation; do not create a second Gazebo stack.
2. In the existing GUI environment run the documented single launch command with the correct `ROS_DOMAIN_ID`/`GZ_PARTITION`. Capture logs proving either automatic build (using a safe copied/missing bundle scenario) or fresh-bundle skip, followed by exactly one port-8000 listener.
3. Load the Tailscale Web UI, exercise HTTP snapshot and WebSocket telemetry, and observe the Collision Panel for at least 10 seconds with changing ages/contacts.
4. Use `ai-station-capture.sh` to save a fresh screenshot. Actually inspect it for no horizontal overflow, stable fixed-height panel, readable badges/tooltips, simultaneous MoveIt/Gazebo panes and correct shadcn styling.
5. Verify the ROS/Gazebo/MoveIt stack remains single-instance and healthy after acceptance.

### Task 11: Review, recoverability, and single amended commit

1. Update the existing recoverable backup with a binary diff and SHA256 manifest before staging; rehearse applying the new addendum in a temporary directory.
2. Review the full diff for scope, secrets, temporary files and accidental tool binaries. Run a final verification-before-completion pass using fresh command output.
3. Stage only the approved spec, plan, Web UI, launch/preflight/tests/docs/config files. Amend `feat(so101): add simulation teleop and harden physical pick-place validation` with a detailed body covering the stable collision panel, official shadcn integration, Bun toolchain, launch-time incremental Web build, tests and live acceptance.
4. Confirm `git rev-list --count <baseline>..HEAD` is exactly `1`, working tree contains no untracked generated assets, and report the final commit hash plus exact verification evidence.
