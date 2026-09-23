# The installed Playwright suite on macOS and Linux — repair handoff

**Status:** nine cases fail identically on both hosts. The host-assumption work is finished and
verified; what remains is one product-contract migration, described in §4.
**Date:** 2026-09-23
**Supersedes:** the "nine need a decision" note in
`docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md`
(`CP-MSC-PLATFORM-PORT-3`).

---

## 0. Dispatch contract — read before any action

| Item | Value |
| --- | --- |
| Worktree | `/Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp` |
| Branch | `codex/so101-unified-webapp` (already checked out; HEAD `dd98413a`) |
| New worktree / new branch | **not allowed** — continue in this worktree on this branch |
| Push / merge / force-push | **not allowed** |
| Evidence deletion | **not allowed** (deletion candidates are reported, never removed) |
| sudo / global config / hardware | **not allowed** |
| Commits | scoped, local, one concern each |
| Ledger | `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md` — append a checkpoint before you hand off or stop |
| Registered evidence root (macOS) | `/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1` |
| Task-owned evidence root (ai-station) | `/data/work/so101-evidence/macos-installed-suite-linux/20260923T011359Z` |

The shell in the codex pane starts in `/Users/matianyi/Projects/ros-moveit-demo` (branch `main`).
**Do not work there** — `cd` into the worktree above first, and treat `main` as the user's own
checkout.

---

## 1. Objective and definition of done

`playwright.installed.config.ts` (25 cases) must be green on macOS, and the same suite must be
re-verified on ai-station.

Done means:

1. macOS: 25 cases either passing or skipped with a stated, host-justified reason — no failures.
2. ai-station (Linux): the same suite run against the same commit, with the same cases green.
3. Both runs recorded in the ledger with their logs and tallies.
4. Scoped local commits, nothing pushed, no evidence removed.

Reaching 25/25 requires the work in §4 — it is not a matter of fixing typos.

---

## 2. Current verified state

| Host | Command | Result |
| --- | --- | --- |
| macOS | `bun run test:e2e:installed` (see §6.1) | **14 passed / 9 failed / 2 skipped** |
| ai-station | `node node_modules/.bin/playwright test --config playwright.installed.config.ts` (see §6.2) | **16 passed / 9 failed** |

macOS ran from 1 passed / 24 failed; the Linux suite could not start at all (0 / 25).

The two skips are **by design** on macOS: S09 and S12 are ADAPTIVE cases, and a platform-bound host
carries no ADAPTIVE row. They run and pass on Linux.

### The nine failures — identical on both hosts

| # | File:line | Case | Observed |
| --- | --- | --- | --- |
| 1 | `artifacts.spec.ts:12` | S08 the page views only opaque registered artifacts | test timeout (30 s), store empty |
| 2 | `entry-and-campaign.spec.ts:187` | S02 Chrome campaign flow matches the durable helper journal | test timeout, store empty |
| 3 | `entry-and-campaign.spec.ts:241` | S03 a second Chrome context stays fenced out | test timeout, store empty |
| 4 | `entry-and-campaign.spec.ts:276` | S04 browser reconnect restores the same running campaign | test timeout, store empty |
| 5 | `lease-recovery.spec.ts:180` | S06 start and retry command ids are idempotent | retry POST → 409 |
| 6 | `retry-queue.spec.ts:42` | S14 two failed points retry as serial N=1/K=1 batches | expects `["COMPLETE","COMPLETE"]`, got `[""]` |
| 7 | `retry-queue.spec.ts:121` | S15 terminal-to-cleanup window never replays or skips | expects `RETRY_CLEANUP_INCOMPLETE`, got `RETRY_ONE_POINT_PER_COMMAND` |
| 8 | `retry-queue.spec.ts:173` | S15 cleanup-to-dequeue window advances exactly once | expects `true`, got `false` |
| 9 | `retry-queue.spec.ts:259` | S15 spawn-intent-to-ack window stays fenced | `INTENT_WINDOW_MISSED`, service answered `RETRY_ORIGINAL_RESULT_UNKNOWN` |

Because the same nine fail on both platforms, **none of them is a host difference** — an earlier
reading in the ledger that the retry cluster was macOS-specific was wrong and is corrected there.

---

## 3. Already fixed — do not redo

These were the ai-station-only assumptions. Each is committed and verified; the rules live in
`src/so101_teleop/web/e2e/expert-validation/fixtures/host-routes.ts` with 17 offline unit tests
(`src/so101_teleop/web/src/api/installed-host-routes.test.ts`).

| Commit | Fix |
| --- | --- |
| `b2652b06` | The port: contract version 3, platform liveness (`/proc` vs `ps`), host-aware ROS underlay search path, host execution document + coordinator + profile claim |
| `fcdecc23` | Run-evidence documents are ambient-only (they are `_optional_file` to the product); RUNNING is waited for rather than sampled once |
| `5306a4a1` | The legacy route needs an execution document whose contract version is 3 → `parallel_batch_v3.yaml`, not v2 |
| `65d54e3d` | S01 starts the unified entry and closes the page before stopping |
| `77a9ee39`, `f727f7e1` | Refusals print the body/receipt that explains them |
| `859eb2a7` | The fixture gives the spawned service `PYTHONPATH` — without it the campaign resource probe child could not import the product, the receipt was never admitted, and every start was refused with the misleading `PREFLIGHT_REQUEST_MISMATCH` |

Also fixed on ai-station only (no repo change): a task-owned build of all seven colcon packages, a
task-owned `bun` 1.4.2, the MuJoCo 3.12.0 release, a `mujoco_vendor` shim (the ROS vendor exports a
`/opt/mujoco_vendor` that does not exist there), and a task-owned venv with `mujoco`, `uvicorn`,
`fastapi`, `pydantic`, `psutil`.

---

## 4. What is left — two workstreams

### 4.1 The page-driven four (cases 1–4): the app composition

**Cause, measured.** The console bundle the deployment serves is the **unified** one: its page boots
by calling `/snapshot` and opens `/control/…` channels, and only the unified app answers those
(`so101_teleop/unified/app.py`: `/snapshot` at line 459, `/control/instances` at 321). The installed
fixture composes the **expert-validation app alone** through
`src/so101_teleop/test/e2e/installed_test_launcher.py` → `create_installed_test_app`, which mounts
`create_expert_validation_app(service, static_dir)`. So the page loads a console whose boot fetch
404s, never becomes interactive, and the case times out with an **empty store** — verified by
querying a failed run's `supervisor.sqlite3`: `campaigns 0`, `preflight_receipts 0`.

**The trap.** Swapping in the unified app is not enough. Its validation routes are guarded:

- `/expert-validation/lease` takes `Depends(require_channel("validation"))` (`unified/app.py:733`)
- every mutation takes `RequestAuthority = mutation` (manifests, renew, releases, campaigns)

A bare JSON POST — what `e2e/expert-validation/installed/support.ts` sends — is refused. The suite
must speak the console's own protocol: register an instance, complete the channel handshake, then
carry the four authority headers (`X-SO101-Instance-ID`, `-Proof`, `-Channel-Revision`,
`-Execution-Generation`) from `src/api/instance-client.ts`.

### 4.2 The retry five (cases 5–9): a contract the specs predate

The product retries **one point per command**, enforced before anything else:

```python
# so101_teleop/expert_validation/production.py:2105 and :1777
point_ids = tuple(body["point_ids"])
if len(point_ids) != 1:
    raise ServiceConflict("RETRY_ONE_POINT_PER_COMMAND")
```

The specs send `terminal.points.slice(0, 2)` and assert the older codes. The live retry vocabulary
is:

```text
RETRY_ONE_POINT_PER_COMMAND      RETRY_ORIGINAL_NOT_TERMINAL     RETRY_ORIGINAL_NOT_FAILED
RETRY_ORIGINAL_CLEANUP_INCOMPLETE  RETRY_ORIGINAL_BATCH_UNKNOWN  RETRY_ORIGINAL_REQUEST_UNKNOWN
RETRY_ORIGINAL_RESULT_UNKNOWN    RETRY_NOT_QUEUED                RETRY_PROFILE_MISMATCH
RETRY_LEASE_REQUIRED             RETRY_REQUEST_INVALID           RETRY_OWNER_GENERATION_MISMATCH
RETRY_OWNER_EPOCH_INVALID
```

So `RETRY_CLEANUP_INCOMPLETE` is now `RETRY_ORIGINAL_CLEANUP_INCOMPLETE`, the "two points retry as
two serial batches" case becomes **two commands of one point**, and the window cases must drive the
queue one point at a time. **Keep the guarantee each case was written to prove** (no replay, no skip,
exactly-once advance, first-pass statistics untouched) — change the shape of the command, not the
assertion's strength. Weakening an assertion to make it pass is not acceptable; if a guarantee no
longer holds in the product, record it as a finding instead.

---

## 5. An attempt was made and reverted — its findings are yours

The unified-composition + authority attempt is preserved as a patch:

```text
/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1/handoff/attempt-unified-authority.patch
sha256 9f80cfce07a05f82f2730b5140e22b447b92d5e30a37f8a184fac3fb0ce18bff   (217 lines)
```

It is **not** in git: the worktree is at the verified baseline (`dd98413a`, clean). What it learned:

1. **Parameter properties break the runner.** Playwright transpiles specs with Node type-stripping,
   which refuses `constructor(private readonly x: T)`. Importing `InstanceClient` as-is fails with
   *"TypeScript parameter property is not supported in strip-only mode"*. Rewriting the class to
   explicit fields works and keeps the app's own tests green (6 passed).
2. **The channel socket must be retained.** Registering and handshaking is not enough: the registry
   holds the instance only while its channel is open, and a socket nobody references is collected.
   The symptom is `{"code":"UNKNOWN_INSTANCE"}` on the very next request. Keeping a module-level
   reference fixes it.
3. **The origin must be the served address.** The registry refuses a handshake whose origin is not
   the service origin; the launcher has to set `SO101_UNIFIED_ORIGIN=http://127.0.0.1:<port>`, which
   `unified/main.py` does for the production entry but the launcher does not.
4. **It still regressed the suite** (`10 passed / 15 failed` in its last complete run) — the lease
   path worked, the mutation path did not, and the adaptive pair stopped skipping because the
   unified capabilities document is shaped differently. Do not assume the patch is close to done;
   treat it as a set of findings with a starting point.

`git apply` that patch only if you want its starting point; otherwise re-derive from
`src/api/instance-client.ts` and `src/state/domain-runtime.ts`, which are the console's real
implementations of the same protocol.

---

## 6. How to run both hosts

### 6.1 macOS (this machine)

```zsh
RUN=/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1
cd /Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp
source "$RUN/remediation/operator/env.sh"                 # four overlays, TASK_ROOT, worktree paths
WT="$REM_WORKTREE"
export PYTHONPATH="$(printf '%s' "$PYTHONPATH" | tr ':' '\n' | grep -v -- "$WT" | paste -sd: -)"
export PYTHONPATH="/opt/data/so101/workspace/install/so101_teleop/lib/python3.11/site-packages:\
/opt/data/so101/workspace/install/so101_demo_py/lib/python3.11/site-packages:$PYTHONPATH"
M=/private/tmp/so101-debug-unbounded-queue-w2-mac-mini-3eed4ddd-a50c-4c21-b78f-60be2216ef9d/model-artifacts/models
export SO101_VALIDATION_YOLO_WEIGHTS="$M/yolo/best.pt"
export SO101_VALIDATION_GROUNDED_ROOT="$M/grounded"
export SO101_E2E_EVIDENCE_ROOT="$RUN/remediation/task11/installed-macos-port-20260923T004151Z"
export SO101_E2E_INSTALL_PREFIX=/opt/data/so101/workspace/install
export SO101_E2E_PYTHON=/opt/ros2_jazzy/.venv/bin/python
export SO101_E2E_DEPENDENCY_PREFIX=/opt/data/so101/runtime/fork/current:/opt/ros2_jazzy/extra_ws/install
cd src/so101_teleop/web && bun run test:e2e:installed
```

The model-artifacts directory belongs to another task family: **read only, never modify or delete.**

To iterate on one case without a 7-minute suite run:

```zsh
bunx playwright test --config playwright.installed.config.ts \
  e2e/expert-validation/installed/retry-queue.spec.ts -g 'S15' --timeout 240000
```

### 6.2 ai-station (Linux)

```zsh
R=/data/work/so101-evidence/macos-installed-suite-linux/20260923T011359Z
ssh ai-station      # then, inside
cd $R/repo/src/so101_teleop/web && git log --oneline -1     # must be the commit under test
export PATH=$HOME/.nvm/versions/node/v26.9.0/bin:$PATH
export SO101_E2E_EVIDENCE_ROOT=$R/e2e-evidence SO101_E2E_INSTALL_PREFIX=$R/install
export SO101_E2E_DEPENDENCY_PREFIX=$R/install
export SO101_E2E_PYTHON=$R/venv/bin/python SO101_TASK_ROOT=$R TASK_ROOT=$R
export SO101_VALIDATION_YOLO_WEIGHTS=/data/work/models/so101-perception/yolo11n-seg-plastic-cup/best.pt
export SO101_VALIDATION_GROUNDED_ROOT=/data/work/models/so101-perception/grounded-sam-cup-pickplace/bundle
source /opt/ros/jazzy/setup.bash
node node_modules/.bin/playwright test --config playwright.installed.config.ts
```

There is **no `bun`** on ai-station; `node node_modules/.bin/playwright` is the entry. `node_modules`
in the clone is a symlink to ai-station's own checkout.

**Getting new commits there without pushing** (the rule is no push): create a bundle and fetch it.

```zsh
# on this Mac
git bundle create /tmp/port-next.bundle codex/so101-unified-webapp
scp /tmp/port-next.bundle ai-station:/data/work/so101-evidence/macos-installed-suite-linux/20260923T011359Z/port-next.bundle
# on ai-station
cd /data/work/so101-evidence/macos-installed-suite-linux/20260923T011359Z/repo \
  && git fetch -q ../port-next.bundle codex/so101-unified-webapp && git checkout -q FETCH_HEAD
```

The clone there is a **bundle clone**: it has no remote. If you change C++ or CMake you must rebuild
into the same task-owned install (`colcon --log-base $R/log build --install-base $R/install
--build-base $R/build --packages-select … --cmake-args -Dmujoco_vendor_DIR=$R/mujoco_vendor_shim/share/mujoco_vendor/cmake`)
with `$R/tools/bun/bin` on `PATH`; Python-only changes need no rebuild.

---

## 7. Traps that cost time already

- **`SO101_TASK_ROOT` is required.** The campaign resource probe reads
  `$SO101_TASK_ROOT/start-guard-state` and refuses every preflight with `CoordinatorError` without
  it. Both hosts set it to the registered evidence root.
- **`PYTHONPATH` must reach the spawned service** (§3, `859eb2a7`). A missing import there surfaces
  as `PREFLIGHT_REQUEST_MISMATCH`, which names the wrong thing.
- **Ground rules for the Linux model inputs:** `SO101_VALIDATION_GROUNDED_ROOT` must be a *directory
  containing `manifest.json`* (`.../grounded-sam-cup-pickplace/bundle`), and the weights must be a
  regular file, not a symlink.
- **The execution document's contract version must be 3** (`parallel_batch_v3.yaml` on the legacy
  route, the macOS profile document on a platform-bound host).
- **One service window at a time**; the fixtures bind real ports and write real stores. Check for
  leftover `installed_test_launcher` / `playwright` processes before a run and stop your own after.
- **Test-level timeouts are per spec.** A real macOS campaign takes minutes; a case that waits for a
  campaign needs its own budget, not the 30 s default.
- The static gate runner (`scripts/so101-macos-service-campaign-final-gate.zsh`) is the project's
  broader gate; re-run it if you change anything outside `e2e/`.

---

## 8. Suggested order

1. Re-read §4.2 and the retry endpoint (`production.py:1760-1830`, `2090-2125`). Write the five retry
   cases against the one-point contract, one commit, and run them on macOS — they need no app
   composition change, so they are the cheap half.
2. Then §4.1: decide the composition (unified app + authority protocol, or a documented reason that
   the page-driven acceptance cannot run against the legacy composition). This is the half that
   changes what the acceptance *is*; if you conclude the specs cannot be brought forward without
   changing their guarantees, stop and record a finding instead.
3. Re-run the full suite on macOS, then transfer the commit to ai-station and re-run there.
4. Append a ledger checkpoint, then write `writer-release.json` in
   `/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1/dispatches/`
   as the previous writer did.
