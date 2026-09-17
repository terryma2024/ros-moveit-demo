task_id: so101-teleop-chrome-e2e-20260916T130435Z-e2ffff62-kimi01
goal: Complete and verify the Teleop expert-validation Chrome E2E acceptance: C01-C22 (L1 contract), S01-S16 (L2 installed), API-contract sub-suite, R01-R05 (L3 live MuJoCo, gated on safety).
success_contract: 43-row case-status.tsv carries an evidence-backed status for every case; L1/L2/API suites run green on this worktree with isolated resources; L3 runs only after ownership is safely established, else BLOCKED with reason.
worktree: /data/work/ws_moveit/.worktrees/kimi-teleop-chrome-e2e
branch: codex/kimi-teleop-chrome-e2e
base_commit: e2ffff6225246e7d3c552e6c2e7069826ff7d1a9
current_commit: e2ffff6225246e7d3c552e6c2e7069826ff7d1a9
evidence_root: /data/work/so101-evidence/teleop-chrome-e2e/20260916T130435Z-e2ffff62-kimi01
host: AI-STATION-001 (running directly on ai-station; no SSH)
dispatch_receipt: KIMI-TELEOP-E2E-20260916T130435Z (dispatch.receipt in evidence root, created and read back)
toolchain:
  bun: /home/lenovo/.bun/bin/bun (1.3.14)
  chrome: /usr/bin/google-chrome (150.0.7871.181)
  system_python: /usr/bin/python3 (3.12.3, pydantic 1.10.14 - too old, not used for feature tests)
confirmed_conclusions:
  - Worktree at frozen commit e2ffff62, clean status, branch codex/kimi-teleop-chrome-e2e.
  - Feature implementation present: web/src/expert-validation-app.tsx, expert_validation/production.py, process_owner.py exist.
  - E2E infrastructure absent: no web/e2e/expert-validation/, no test/e2e/, no installed/live-sim playwright configs; only single-scenario e2e/expert-validation.spec.ts plus tasks.spec.ts and teleop.spec.ts.
  - Developer worktree /data/work/ws_moveit/.worktrees/teleop-expert-validation-web is at the same commit e2ffff62, clean; its ledger is identical to this worktree's copy (read-only for me).
  - Developer ledger latest checkpoint CP-016: source W8 regression gates green; copied-install identity and EXP-052 live acceptance still open there.
  - tmux sessions at task start: codex (developer, attached), kimi (unrelated path-audit, attached, never touch), kimi-teleop-chrome-e2e (this task).
  - No ROS/MoveIt/Gazebo/MuJoCo/Chrome/Playwright processes at task start.
disproven_routes:
  - NONE
open_hypotheses:
  - L1/L2 can be implemented and run independently with isolated ports/DB/Chrome profiles per the handoff.
latest_checkpoint: CP-K00
next_experiment: EXP-K01 (Task 1 scenario schema RED)

## CP-K01 — L1 Chrome contract suite complete

```yaml
checkpoint_id: CP-K01
last_valid_experiment: EXP-K01
current_commit: 8ffa8c01e (local commits 464af3286 + 8ffa8c01e on frozen base e2ffff62)
working_tree_status: clean after commit 8ffa8c01e
owned_processes: NONE (all scripted servers/Chrome exited; exit codes recorded per case dir)
preserved_processes: tmux codex (developer), tmux kimi (unrelated path-audit)
confirmed_conclusions:
  - EXP-K01: L1 chrome-contract suite 24/24 PASS covering C01-C22 (C18 and C21 each split into two tests by scenario). Full default gate (legacy 13 + contract 24) = 37 passed, exit 0, elapsed ~94s. Vitest 108/108, build exit 0.
  - Scripted server reuses production create_expert_validation_app routes and serves the real Vite dist bundle to official Google Chrome 150.0.7871.181 over real HTTP/WebSocket; faults (duplicate/late/omitted sequences, ws close, http error once) inject at transport level only.
  - Production port requires service.get_manifest to exist because api.py evaluates the getattr default eagerly; fixture alias added (no production change).
  - Minimal production display seam added: CampaignProgress now renders Failed/Indeterminate/Unrun counts and adaptive infra attempts + observational resource readings (design 6.2 requires them; they were absent).
  - Environment facts: Chrome requires short TMPDIR (SingletonSocket 107-byte limit) -> /run/user/1000/so101-kimi-e2e/<run>/tmp; --no-proxy-server arg required because the host exports http_proxy; Node 24 at /data/work/tools/node-v24.18.1-linux-x64/bin required (system node18 cannot parse import attributes); Playwright TS loader rejects parameter properties and __dirname.
disproven_routes:
  - Deep NVMe scratch as Chrome TMPDIR (socket path too long); reusing stale ready files across runs.
open_risks:
  - C13 gap-triggered GET is asserted by convergence + log, not by exact GET count (page polls every 2s by design).
next_command: Task 8 - L2 typed execution port, real process helpers, installed test launcher (RED first).
```

```yaml
experiment_id: EXP-K01
status: VALID
lifecycle: ISOLATED_STACK
single_variable: L1 contract suite implementation
provenance:
  source_commit: 8ffa8c01e (worktree codex/kimi-teleop-chrome-e2e)
  install_overlay: NONE (source tree + web/dist build)
  runtime_executable: /usr/bin/google-chrome 150.0.7871.181, scripted uvicorn per case
  ros_domain_id: not_applicable
  gz_partition: not_applicable
commands:
  - command: bun run test:e2e -- e2e/expert-validation/contract (SO101_E2E_EVIDENCE_ROOT set)
    exit_code: 0
observed:
  - 24/24 contract tests passed in 1.6m; full default gate 37 passed; Vitest 108/108.
conclusion: L1 Chrome contract layer complete and green.
evidence:
  - /data/work/so101-evidence/teleop-chrome-e2e/20260916T130435Z-e2ffff62-kimi01/reports/playwright-default.json
  - /data/work/so101-evidence/teleop-chrome-e2e/20260916T130435Z-e2ffff62-kimi01/browser/chrome-contract/ (per-case dirs incl. retained failure runs)
decision: KEEP
next_experiment: EXP-K02 (L2 execution port)
```
```yaml
experiment_id: EXP-K02
status: VALID
lifecycle: ISOLATED_STACK
single_variable: L2 installed production composition + real OS helpers
provenance:
  source_commit: d029b441d (worktree codex/kimi-teleop-chrome-e2e)
  install_overlay: /data/work/so101-evidence/teleop-chrome-e2e/20260916T130435Z-e2ffff62-kimi01/install-runtime (copied 7-package colcon prefix, rebuilt per production change)
  runtime_executable: python-venv/bin/python3 launcher + /usr/bin/google-chrome 150.0.7871.181
  ros_domain_id: not_applicable
  gz_partition: not_applicable
commands:
  - command: bun run test:e2e:installed (full L2)
    exit_code: 0
    elapsed: 192s
  - command: bun run test:e2e:installed -- --grep @api-contract
    exit_code: 0
observed:
  - 25/25 installed tests passed; S01-S16 all PASS; @api-contract collected 7 tests, all PASS.
  - fixed_helper AMENT sys.path bootstrap fixed (c9eb9099b) after ModuleNotFoundError in smoke-t022/t023.
  - Production gaps found RED and fixed minimally (171d59b5c): restart campaign reconciliation
    (_restore_campaigns from durable store), stable command digests + repeat-first idempotency for
    start/retry, resumable retry queue with crash-window reconciliation, INTENT-row fencing,
    lease auto-recovery after clean reconciliation, SPA fallback no longer shadows /artifacts/*.
  - Test-side flakes diagnosed and fixed: fetch Response.status property, zombie-aware process
    liveness, SIGKILL exit detection (exitCode stays null on signal death), in-process watcher
    for the INTENT->ACK window (few ms), lease renew before slow-spec crash windows.
conclusion: L2 installed layer complete and green, including the three S15 crash windows.
evidence:
  - /data/work/so101-evidence/teleop-chrome-e2e/20260916T130435Z-e2ffff62-kimi01/reports/playwright-installed.json
  - /data/work/so101-evidence/teleop-chrome-e2e/20260916T130435Z-e2ffff62-kimi01/server/S*/
decision: KEEP
next_experiment: EXP-K03 (L3 preflight/evidence adapters)
```
