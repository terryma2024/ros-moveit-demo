# SO-101 macOS service campaign closure implementation ledger

Single writer for this task. Dispatch `2208b154-6e9f-4ae1-a448-1fa0101df9b1`. This ledger records
facts for audit; it does not itself authorize measurement, promotion, publication, process
termination, or evidence deletion.

```yaml
task_id: so101-macos-service-campaign-closure
goal: close service-driven macOS W2, W1 and single-point retry with qualified N1/N2 budgets
success_contract: design section 14, with candidate and production evidence kept separate
executor: DeepSeek Harness TUI (dst) inline on mac-mini, per plan and dispatch executor rules
worktree: /Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp
branch: codex/so101-unified-webapp
base_commit: 6d5069026fbd322076f58d0d4b9504891abeb861
current_commit: 90385e3fb4aa748788c5d8a4b4551ee307db4987
upstream: origin/codex/so101-unified-webapp (ahead 23, no push authorized)
evidence_root: /tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1
dispatch_receipt: /tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1/dispatch.receipt
dispatch_receipt_sha256: bea49ba76cf9d131529ca0b72d82bf8c9c6350d9eebc69fdefbe8ad19bc34b51
handoff_sha256: 4e672949dba8b72e18ed85ae6ef103063c1ce537b974e735defd492a2bcfede9
design: docs/superpowers/specs/2026-09-21-so101-macos-service-campaign-closure-design.md
design_sha256: 0a5f5e0d8006016fb778d186f7029247b7fe828f0e1efaea34e4e96b00480015
plan: docs/superpowers/plans/2026-09-21-so101-macos-service-campaign-closure-implementation.md
plan_sha256: 8fdce5b60eb1218726ab9eedd4fdf84da68e233e20f1f0ddadc00c4ba3f41538
execution_host: Terry-Mac-mini.local (macOS, arm64, user matianyi)
run_root: /tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1
test_python: /Users/matianyi/ros2_jazzy/.venv/bin/python (Python 3.11.15, pytest 8.4.2, pydantic 2.13.4)
test_python_declared_by_plan: python3 (resolves to /opt/homebrew/bin/python3, Python 3.14.6, no pytest/pydantic; see D-1)
ros_workspace: /Users/matianyi/ros2_jazzy (macOS source build; no /opt/ros/jazzy on this host)
gate_recorder: src/so101_teleop/test/e2e/record_gate.py
gate_policy: <RUN_ROOT>/operator/gate-policy.json
gate_policy_sha256: 374439d0bbf02f74a428cfa444ab4e78c965e06063dd3ef32e5ee0c759f1b9fa
gate_env: <RUN_ROOT>/operator/gate-env.sh
gate_env_sha256: 55cc16fc22210fd144f600b1ab3c2b1365ecfb3e4ba01438b4d48085894d28d9
confirmed_conclusions: []
disproven_routes: []
open_hypotheses:
  - controller-manager first bad boundary on macOS is not yet confirmed (design section 4.2)
latest_checkpoint: CP-MSC-000
next_experiment: EXP-MSC-001
```

## CP-MSC-000: registration, frozen base and baseline (Task 0 Steps 1-3)

### Required first actions

- Receipt written first, exactly `2208b154-6e9f-4ae1-a448-1fa0101df9b1` + newline, file and
  containing directory fsynced, before any other task action (file mode 0644, 37 bytes,
  sha256 `bea49ba7...`).
- Read: `AGENTS.md`, `.agents/skills/so101-dev/SKILL.md` with references
  (`ai-station-access.md`, `so101-system-map.md`, `debug-evidence.md`, `test-and-acceptance.md`,
  `experiment-ledger.md`), the design and plan above, and both predecessor document pairs:
  `2026-09-18-so101-parallel-unbounded-queue-resource-budget` design
  (`5e085f98e9926591fbefd3d6e16c16b33bfc9956df9221c46f383b310553657b`) / plan
  (`cd1b606fd8a40d7bb6e576f6f59a6ef5abcb45a8bee7e2a669c7b7a40bcfc8789`), and
  `2026-09-19-so101-macos-mps-private-ipc` design
  (`480da6dcdfea1da988f9f4e706c8340dbb6d7283200c27bb723859119145db1b`) / plan
  (`d018aae3bae372abd9a58a6e0ec7d7fef1f09dbef67860680690614bc31bb875`).

### Checkout ownership read-back (fail-closed checks passed)

- `hostname` = `Terry-Mac-mini.local`; `pwd` = the target worktree above. This dispatch runs
  directly on mac-mini; no SSH to mac-mini or ai-station was issued.
- Branch `codex/so101-unified-webapp`; HEAD `90385e3fb4aa748788c5d8a4b4551ee307db4987` — exactly
  the required starting HEAD. Upstream `origin/codex/so101-unified-webapp`, ahead 23.
- `git status --short` empty; `git diff --submodule=log` empty; submodule
  `third_party/mujoco_ros2_control` at `e4c0241aee52a40727681bd5872c09bf814e941a`, clean.
- Raw read-backs: `<RUN_ROOT>/baseline/git-baseline.txt`,
  `<RUN_ROOT>/baseline/process-inventory.txt`, `<RUN_ROOT>/baseline/evidence-root-identity.txt`.

### Writer and process ownership

- The only processes referencing this worktree are this dispatch's own TUI chain
  (pid 64248 dst -> 64249 dsh-tui -> 64251 dsh, tmux session `dst-so101-macos-closure`, created
  2026-09-21 10:24:48). No second writer overlaps the worktree.
- Preserved, not touched: tmux `dst` (pid 44357 shell), tmux `dst-so101-macos-mps-w2` (pane pid
  10776, TUI of dispatch 6954bbb9 in a different worktree, state `blocked`), tmux
  `so101-teleop-w2-e2e` with long-running pid 62670
  (`so101_teleop.expert_validation.main`, started ~24 h earlier, belongs to another task),
  and legacy TF publishers pid 1541/1542 (`static_transform_publisher`, ~1 day 10 h old).
- No TCP listener exists on this host (empty `lsof -nP -iTCP -sTCP:LISTEN`), so no duplicate
  service or port conflict was started or observed.

### Frozen run environment (adopted dispatch root, not a second root)

The handoff makes the dispatch directory the task's single ordinary evidence root, so Task 0 Step 2
adopted it instead of running `mktemp -d`; no second root was created. Within it:

| item | frozen value |
| --- | --- |
| `RUN_ROOT` | `/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1` (mode 0700, uid 501) |
| `TEST_PYTHON` | `/Users/matianyi/ros2_jazzy/.venv/bin/python` |
| `ROS_HOME` | `<RUN_ROOT>/ros_home` |
| `ROS_LOG_DIR` | `<RUN_ROOT>/ros_log` |
| `TMPDIR`/`TMP`/`TEMP` | `<RUN_ROOT>/tmp` (per gate invocation: `<RUN_ROOT>/gates/<uuid>/tmp`) |
| gate policy | `<RUN_ROOT>/operator/gate-policy.json`, sha256 `374439d0...` |

Proof of the frozen interpreter/tempfile pair (both assertions exit 0, recorded in
`<RUN_ROOT>/baseline/task0-step2.txt`):
`sys.executable=/Users/matianyi/ros2_jazzy/.venv/bin/python`,
`tempfile.gettempdir()=/private/tmp/so101-debug-macos-service-campaign-closure-2208b154-.../tmp`.

### Deviations (reported, not silent substitutions)

- **D-1 test interpreter.** The plan's literal `TEST_PYTHON="$(command -v python3)"` resolves on
  this host to `/opt/homebrew/bin/python3` (Python 3.14.6), which cannot import `pytest` or
  `pydantic` and therefore cannot run any gate; treating its failures as RED/GREEN would be
  invalid. The repository's own macOS test contract
  (`.agents/skills/so101-dev/references/test-and-acceptance.md`) and the predecessor dispatch on
  this exact worktree and branch both register `/Users/matianyi/ros2_jazzy/.venv/bin/python`
  (3.11.15, pytest 8.4.2, pydantic 2.13.4, `rclpy` importable after sourcing
  `~/ros2_jazzy/install/setup.bash`). That verified interpreter is frozen as `TEST_PYTHON`; the
  literal value and its failed capability probe are recorded in
  `<RUN_ROOT>/baseline/task0-step2.txt`.
- **D-2 `/data` durable root.** `/data/work/so101-evidence` does not exist on this host and
  `AGENTS.md` exempts macOS from the ai-station NVMe rule. Per plan Global Constraints this only
  blocks Stage C's high-rate sampling: before the first durable high-frequency sample the plan
  requires the durable root to be created and registered, and if it is unavailable the run must
  stop and ask for a storage decision. That decision is not required for Tasks 0-3.
- **D-3 plan literal root command.** Task 0 Step 2's `mktemp -d` invocation was superseded by the
  dispatch handoff's "adopt the already-created root, do not create a second task root" rule.
  Every other literal element of the step (directory layout, exports, interpreter/tempfile
  assertion, read-back into the ledger) was executed.

### Baseline collection (Task 0 Step 3, read-only)

- Module origins (`gates/a46b2848efa24fb8bf1d33504e1a6ccc`):
  `rclpy` from `/Users/matianyi/ros2_jazzy/install/rclpy/lib/python3.11/site-packages/rclpy/__init__.py`,
  `so101_demo` from the source shim `<RUN_ROOT>/pyshim/so101_demo/__init__.py` (the package maps
  `so101_demo -> src/` only at install time), `so101_teleop` from this worktree's source tree,
  `sys.executable=/Users/matianyi/ros2_jazzy/.venv/bin/python`.
- Frozen config bytes: `parallel_batch_v4_macos_mps_w2.yaml`
  `2f9d7a87fe57a0440cdfd139c2ac42b7af86002edfcc2ed2ef3077568dc6b06b`,
  `parallel_batch_v3.yaml` `991b5c1b4fbd0cc1f0a97bd20a5b5a4e02028634f3f4ef288ad87554b383ab70`,
  `rgbd_task_points.yaml` `75591214ba3d1dfdd2827c390c0f2ec1d61e7a8dca80d89daabb1e7840627e73`.
- Retired measurement entry still fails closed: `-m so101_demo.cli.measure_parallel_resources`
  exits 2 with `MEASUREMENT_ENTRY_RETIRED` / `authorizes_execution=false`, both bare and with
  `--authorization /nonexistent --intent QUALIFICATION`
  (`gates/4874802dd6ae449f9e2e0421ad25bf32`, `gates/762c6f5691b84947b0882d7026a79d0a`).
- Package collection counts: `src/so101_demo_py/test` collects 3517 tests with 2 pre-existing
  collection errors (`test_mujoco_reset_client.py`, `test_teleop_owner.py`: `FreeJointState`
  missing from the installed `mujoco_ros2_control_msgs` fork overlay — an underlay gap on this
  host, unrelated to this dispatch), exit 2; `src/so101_teleop/test` collects 744 tests, exit 0.
  Summary: `<RUN_ROOT>/baseline/collection-baseline.txt`.
- Targeted baseline for the files Tasks 1-2 touch: `test_task_stack.py` +
  `test_motion_stack_ready.py` = 8 passed
  (`gates/da96626319de4fa388fe604ce519a2d2`).
- RED-target absence confirmed: `so101_demo.runtime.runtime_closure` and
  `so101_demo.cli.diagnose_macos_station` do not exist yet
  (`<RUN_ROOT>/baseline/probe_task1_task2_targets.py`).

### Evidence accounting at CP-MSC-000

- Retained: dispatch receipt/handoff/pane captures, `baseline/`, `operator/`, all `gates/<uuid>/`
  records, `pytest-*/junit.xml` invocation directories.
- Archived: none. Deletion candidates: none proposed at this checkpoint (the two `/tmp` trees of
  other dispatches are not this task's evidence and are left untouched).
