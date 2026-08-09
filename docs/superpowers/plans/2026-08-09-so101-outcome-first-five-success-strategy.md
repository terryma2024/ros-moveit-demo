# SO-101 Outcome-First Five-Success Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Python pick-place 的中间验证改为 outcome-first continuation gate，在不使用 Gazebo forward attach 的前提下找到完整连续成功策略，并在冻结版本上完成串行 FULL_RESTART×5 与 RESET_WORLD×5。

**Architecture:** 保留现有 `live_execute.py` 连续执行路径与 MoveIt Planning Scene shadow；将严格接触几何 gate 拆为只读 telemetry 和最小 continuation gate；把唯一严格任务判定放到 RETREAT 后的 Final Outcome Gate。策略搜索直接复用现有 motion-policy、runner、ledger 与 RESET_WORLD/FULL_RESTART 生命周期，不先实现通用 adaptive planner。

**Tech Stack:** Python 3.12、pytest、ROS 2 Jazzy、Gazebo Harmonic、MoveIt 2、colcon、tmux。

## Global Constraints

- 本文档提交完成前不实施；文档提交后，用户已授权由当前 Codex 接手策略实现和实验，不再向 tmux `kimi` 派发任务。
- 工作分支保持 `codex/so101-gazebo-demo-py`，现有六条 dirty paths 在 Task 1 审计前不得清理、覆盖或混入文档 commit。
- 禁止 Gazebo forward attach；MoveIt Planning Scene attach/detach 只作固定 collision-planning shadow。
- physics engine、geometry、mass/friction、controller/gains、collision rules 冻结。
- penetration/contact/q6/intermediate angle 记录为 telemetry；不单独构成 continuation failure。
- 最终位置、直立姿态、稳定窗口、速度阈值、释放/撤离、scene membership 是 frozen Final Outcome Gate。
- 任一 live 命令前先在 ledger 写 `PLANNED`；只清理 exact owned PIDs；不触碰 preserved 进程。
- 不 push、不 merge；完成验证后再次请求用户确认。

---

### Task 1: Freeze the outcome-first contract and audit the current dirty baseline

**Files:**
- Read: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/live_execute.py`
- Read: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/physical_outcome.py`
- Read: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/release_settle.py`
- Read: all six current dirty paths
- Append: `docs/experiments/so101-gazebo-demo-py-experiment-ledger.md`

**Interfaces:**
- Consumes: current branch HEAD, exact dirty diff, existing installed prefix and last completed checkpoint.
- Produces: one ledger checkpoint recording ownership, preserved changes, current strategy values, package baseline, runtime provenance and the new outcome-first contract.

- [ ] Read `git status --short`, `git diff --stat`, exact diffs of the six dirty paths, `git log -5`, tmux/process ownership and last ledger checkpoint.
- [ ] Classify every dirty hunk as required strategy input, historical experiment artifact, or unrelated preserved work; do not change it during classification.
- [ ] Append `CP-OUTCOME-FIRST-STRATEGY-001` as `PLANNED`, including source commit, dirty hashes, expected files, no-forward-attach invariant and final acceptance semantics.
- [ ] Commit only the ledger checkpoint if it is the sole new change; otherwise keep it with the first implementation commit so unrelated dirty paths remain unstaged.

### Task 2: Replace strict intermediate geometry gates with continuation-result gates

**Files:**
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/live_execute.py`
- Create: `src/so101_gazebo_demo_py/test/test_outcome_first_continuation.py`
- Modify: `src/so101_gazebo_demo_py/test/test_live_physical_outcome_contract.py`

**Interfaces:**
- Consumes: `RosGazeboLiveBackend.sample()`, controller results, contact telemetry and current motion command.
- Produces:
  - `IntermediateTelemetry`: contact/depth/q6/TCP/cup pose fields, never a pass/fail source by themselves.
  - `ContinuationEvaluation`: `can_continue`, `failure_code`, cup displacement/position-envelope margins, arm stability result.
  - `evaluate_continuation(before, after, commanded_delta, arm_state, policy)`.

- [ ] RED: prove excessive observed penetration alone does not fail when cup position follows the command and arm is stable.
- [ ] RED: prove missing bilateral contact alone does not fail when physical cup motion and arm stability satisfy the continuation result.
- [ ] RED: prove no cup motion, out-of-envelope cup position, non-finite pose, controller failure or unstable arm does fail.
- [ ] GREEN: split `_stable_bilateral` and `attachment_safe_contact` usage into telemetry capture plus `evaluate_continuation`; keep all raw fields in `physical-gate.json` under a telemetry label.
- [ ] GREEN: `verify_physical_micro_lift` checks cup result and arm stability, not penetration/q6/contact/orientation telemetry.
- [ ] Run: `cd /data/work/ws_moveit/.worktrees/so101-gazebo-demo-py/src/so101_gazebo_demo_py && source /opt/ros/jazzy/setup.zsh && python3 -m pytest -q test/test_outcome_first_continuation.py test/test_live_physical_outcome_contract.py`.
- [ ] Expected: focused tests PASS and existing anti-attach contract remains PASS.
- [ ] Commit exact modified/test/ledger paths with message `feat(so101_py): validate intermediate motion by physical outcomes`.

### Task 3: Make post-retreat final outcome the only task-success gate

**Files:**
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/live_execute.py`
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/physical_outcome.py`
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/release_settle.py`
- Modify: `src/so101_gazebo_demo_py/test/test_live_physical_outcome_contract.py`
- Create: `src/so101_gazebo_demo_py/test/test_post_retreat_final_outcome.py`

**Interfaces:**
- Consumes: frozen final-outcome policy and fresh samples after `RETREAT`.
- Produces: `evaluate_post_retreat_final(...) -> FinalPlacementEvaluation`; summary fields `pre_retreat_outcome` and authoritative `final_outcome`.

- [ ] RED: a cup stable before retreat but tipped or displaced after retreat must return failure.
- [ ] RED: a final cup in range/upright/stable with gripper released, fingers clear, Gazebo detached, MoveIt world membership restored and arm stable must succeed.
- [ ] GREEN: retain pre-retreat settle only as telemetry; after RETREAT create a new epoch and run the frozen evaluator again.
- [ ] GREEN: set `summary.status=DONE` only when the post-retreat evaluation succeeds; otherwise persist evidence and return `VALID_FAILURE`.
- [ ] Run the two focused final-outcome test modules; expected PASS.
- [ ] Commit exact modified/test/ledger paths with message `feat(so101_py): gate success on post-retreat cup outcome`.

### Task 4: Package verification and installed provenance

**Files:**
- Append: `docs/experiments/so101-gazebo-demo-py-experiment-ledger.md`

**Interfaces:**
- Consumes: Task 2-3 commits.
- Produces: tested installed overlay used by all later experiments.

- [ ] Record current baseline test count before modification and require no regression rather than relying on an old hard-coded count.
- [ ] Run: `source /opt/ros/jazzy/setup.zsh && source /data/work/ws_moveit/install/setup.zsh && cd /data/work/ws_moveit/.worktrees/so101-gazebo-demo-py && colcon build --packages-select so101_gazebo_demo_py --symlink-install`.
- [ ] Run package pytest and `colcon test --packages-select so101_gazebo_demo_py`; expected no failures.
- [ ] Source `/data/work/ws_moveit/.worktrees/so101-gazebo-demo-py/install/setup.zsh`; verify `ros2 pkg prefix so101_gazebo_demo_py`, `ros2 pkg executables so101_gazebo_demo_py`, policy SHA and actual process command provenance all point to this worktree.
- [ ] Append verification result and commit exact ledger/provenance changes with message `docs(so101_py): record outcome-first runtime provenance`.

### Task 5: Fast full-path candidate search with RESET_WORLD

**Files:**
- Modify only when selected by the search: `src/so101_gazebo_demo_py/config/motion_policies/light_cup_wall_pick.yaml`
- Append: `docs/experiments/so101-gazebo-demo-py-experiment-ledger.md`

**Interfaces:**
- Consumes: installed Task 4 runtime, current approved motion bounds, existing `/tmp/so101-py-exp-runner.sh` only after its contents/hash/ownership are revalidated.
- Produces: ranked full-path candidates evaluated by authoritative post-retreat outcome.

- [ ] Revalidate the runner, reset contract and exact owned-PID cleanup before first use; if provenance differs, stop and repair the runner before live execution.
- [ ] For each candidate, append `PLANNED` with exact policy values/SHA/session/domain/partition/evidence root before launch.
- [ ] Use one owned clean stack; between candidates require RESET_WORLD proof: actions canceled, no Gazebo attachment, MoveIt world membership restored, arm home, cup spawn, controllers active, stable readings, fresh session/evidence/checkpoint and no residual contact.
- [ ] Execute the complete path to post-retreat final outcome. Do not rank candidates by intermediate penetration/contact/q6/angle telemetry.
- [ ] Candidate score order: final hard-gate success first, then final position margin, upright margin, stability margin and arm-stability margin.
- [ ] Change one causally justified motion family per wave; use RESET_WORLD to compare candidates quickly. Any environment invalidation ends the wave; any code defect enters systematic debugging before another candidate.
- [ ] Stop search immediately at the first complete `VALID_SUCCESS`; freeze commit, full policy bundle SHA and evidence root.

### Task 6: Confirm and freeze one complete strategy

**Files:**
- Append: `docs/experiments/so101-gazebo-demo-py-experiment-ledger.md`

- [ ] Run the frozen candidate twice more with independent RESET_WORLD sessions and unchanged commit/policy.
- [ ] If either is `VALID_FAILURE`, return to Task 5 with the failure evidence; do not select a lucky single run.
- [ ] If both pass, create `CP-OUTCOME-FIRST-ANCHOR-*`, record all three evidence roots and freeze code/policy for qualification.
- [ ] Commit only the selected strategy and ledger evidence; do not push.

### Task 7: Serial FULL_RESTART five-success qualification

**Files:**
- Append: `docs/experiments/so101-gazebo-demo-py-experiment-ledger.md`

- [ ] Pre-register five unique FULL_RESTART experiment IDs, legal ROS domains, partitions, tmux sessions and evidence roots at the frozen fingerprint.
- [ ] Run strictly serially. Each run starts a fresh stack and executes the full path to post-retreat final outcome.
- [ ] `INVALID_ENVIRONMENT` ends the batch without counting; `VALID_FAILURE` resets the streak and returns to Task 5; only five consecutive `VALID_SUCCESS` completes this gate.
- [ ] Append each result before starting the next run and preserve exact cleanup readback.

### Task 8: Serial RESET_WORLD five-success qualification and handoff

**Files:**
- Append: `docs/experiments/so101-gazebo-demo-py-experiment-ledger.md`

- [ ] On one clean owned stack, pre-register and run five serial full paths separated by proven RESET_WORLD.
- [ ] Apply the same lifecycle and streak rules as Task 7; do not mix FULL_RESTART results into this streak.
- [ ] Run fresh package tests, dry-run, complete plan-only, headless and fresh GUI/CUA evidence on the frozen tree.
- [ ] Commit scoped final code/policy/tests/ledger changes locally.
- [ ] Stop and report commit SHAs, test results, five-run evidence roots and remaining dirty status. Request explicit approval before push or merge.

## Execution stop conditions

- A required change touches physics/geometry/material/controller/gains/collision rules.
- Forward Gazebo attach is observed or required.
- Final tolerances would need relaxation.
- Existing dirty work cannot be separated safely.
- Preserved processes are at risk, ROS domain is illegal, reset proof fails or provenance points outside this worktree.

At any stop condition, record current evidence and ask the user; do not stack another fix or experiment.
