# SO-101 MuJoCo Task 13 Through Qualification Execution Plan

> **Execution owner:** the Codex CLI running directly on `ai-station` in the existing `codex` tmux session.
>
> **Execution rule:** work inline in `/data/work/ws_moveit/.worktrees/so101-mujoco-ros2`; do not spawn subagents and do not SSH back into `ai-station`.

**Goal:** finish MuJoCo contact calibration, eliminate the launch-directed `move_group` shutdown crash, enforce a genuinely physical pick-place result, then rebase the same worktree onto the latest `main`, integrate the refactored Teleop module with `so101_mujoco_demo_py`, and qualify that final combined implementation across independent full-restart and reset-world lifecycles.

**Architecture:** keep `so101_mujoco_demo_py` independent from the protected Gazebo package. Task 13 adds a measurement-only, fail-closed calibration path that uses the atomic MuJoCo evidence stream and a pose-constrained approach. After a mandatory human threshold approval, Task 14 wires the approved contact policy into a live ROS 2/MoveIt workflow whose positive path never welds, teleports, or directly writes the cup state. Only after one fresh single-cycle physical pick-place is `VALID`, Task 14T checkpoints that evidence, rebases a continuation branch in the same worktree onto the latest `origin/main`, and connects the newly refactored Teleop extension surface to `so101_mujoco_demo_py` without moving MuJoCo-specific code into the Gazebo package. Task 15 drives the post-rebase, Teleop-integrated production entry point through two separately counted qualification series.

**Runtime stack:** ROS 2 Jazzy, MoveIt 2, `ros2_control`, the pinned `zjumty/mujoco_ros2_control` fork based on release `0.0.3`, Python 3, pytest, Ruff, YAML/JSON evidence, tmux, and ai-station CUA for fresh MuJoCo GUI evidence.

---

## 1. Binding scope and gates

### 1.1 Authoritative worktree and baseline

- Worktree: `/data/work/ws_moveit/.worktrees/so101-mujoco-ros2`
- Branch: `codex/so101-mujoco-ros2`
- Plan authoring baseline: `100880a55fd3fee5fbc1930f293faeb444da9282`
- Published branch at plan authoring: `origin/codex/so101-mujoco-ros2` at the same commit
- Protected tree: `src/so101_gazebo_demo_py`
- Isolation baseline: `d300e7a41fb274d6d7e120699b7040666ea61904`
- Long-running ledger: `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`

At plan authoring, `origin/main` and this published feature branch have diverged from the same historical baseline. Do not rewrite the published feature branch or force-push it as an incidental preparation step. Record the fetched refs and merge base at the first checkpoint. The user has explicitly authorized one integration point after the first `VALID` Task 14.4 physical pick-place: Task 14T creates a continuation branch in this same worktree and rebases that continuation branch onto the then-current `origin/main`. No rebase is allowed before that gate, and the already-published `origin/codex/so101-mujoco-ros2` history must never be force-pushed.

### 1.2 Preserved dirty state

The following three untracked files are intentional Task 13 work in progress:

- `src/so101_mujoco_demo_py/config/contact_calibration.yaml`
- `src/so101_mujoco_demo_py/scripts/analyze_contact_calibration.py`
- `src/so101_mujoco_demo_py/test/test_contact_calibration_contract.py`

Before changing them, record their SHA-256 hashes and review the contents. Do not delete, reset, stash, or replace them wholesale. They are a starting point, not approved production policy.

### 1.3 Hard gates

1. The protected Gazebo tree must stay byte-for-byte unchanged and have empty worktree status throughout.
2. Task 13 may only produce a disabled proposal: `approved_by_user: false`, `enabled: false`.
3. The plan approval that authorized execution is not contact-threshold approval.
4. Task 13 must end in a scoped commit and a user review packet. Stop there until the user explicitly approves the proposed threshold values.
5. After Task 13 approval, fix and qualify clean shutdown before starting Task 14. `move_group` exit `-11` is a SIGSEGV/lifecycle failure, not a MoveIt planning result.
6. Task 14 success requires physical MuJoCo evidence. MoveIt action success, Planning Scene attachment, state-machine `DONE`, or a screenshot is insufficient.
7. Task 15 requires two independent consecutive-success series: five `FULL_RESTART` and five `RESET_WORLD`. They cannot be mixed.
8. Teleop Web UI integration remains out of scope through Task 14.4. It becomes mandatory only in Task 14T after one fresh physical pick-place is `VALID`; RGB-D camera integration remains out of scope.
9. Task 14T must preserve the pre-rebase grasp commit and evidence hashes, rebase only a new continuation branch, and never force-push or rewrite the published pre-rebase branch.
10. `so101_gazebo_demo_py` remains protected during Teleop integration. MuJoCo-specific launch, reset, camera, workflow, and evidence behavior belongs in `so101_mujoco_demo_py`; only a minimal simulator-neutral Teleop extension point may be changed outside it when the latest `main` does not already provide one.

### 1.4 Experiment discipline

Before every live experiment:

- recover the ledger checkpoint;
- pre-register one new monotonic experiment ID as `PLANNED`;
- freeze the hypothesis, one active variable, lifecycle, abort criteria, provenance, and evidence directory;
- inventory existing tmux sessions, PIDs/PGIDs, ROS domains, and task ownership;
- create a unique evidence root with `mktemp -d /tmp/so101-debug-mujoco-task13-XXXXXXXX` (use the matching task name for later phases).

Move `PLANNED -> RUNNING` only after provenance and initial state pass. End every attempt as `VALID` or `INVALID`; never infer the hypothesis after seeing the result. Stop only exact task-owned processes. Do not use broad `pkill`, and do not disturb existing Gazebo/MoveIt/RViz/CUA sessions.

---

## 2. Task 13 — Calibrate MuJoCo contact evidence

### Task 13.0: Restore the current checkpoint and freeze provenance

**Files:**

- Update: `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`
- Read only: `docs/guides/so101-mujoco-ros2-integration-guide.md`
- Read only: `docs/superpowers/plans/2026-08-09-so101-mujoco-ros2-migration.md`
- Read only: `src/so101_mujoco_demo_py/config/dependency-lock.yaml`
- Read only: `src/so101_mujoco_demo_py/config/model-parity.yaml`
- Read only: `src/so101_mujoco_demo_py/docs/provenance.json`

- [ ] Fetch `origin/main` and `origin/codex/so101-mujoco-ros2` without changing the worktree; record HEAD, both remote refs, merge base, submodule commit, and dirty paths.
- [ ] Hash the three preserved Task 13 files and the effective model/config inputs: `scene.xml`, `so101.xml`, `model-parity.yaml`, `mujoco_plugins.yaml`, `ros2_controllers.yaml`, and the patched dependency lock.
- [ ] Inventory all current tmux sessions, ROS domains, and relevant PIDs. Mark every pre-existing process as preserved unless ownership is proven.
- [ ] Append a new checkpoint after EXP-060 that records the current `100880a` visual/model baseline and makes the next experiment explicit.
- [ ] Verify the isolation gate before any live command:

```bash
git diff --quiet d300e7a41fb274d6d7e120699b7040666ea61904 -- src/so101_gazebo_demo_py
test -z "$(git status --short -- src/so101_gazebo_demo_py)"
git submodule status -- third_party/mujoco_ros2_control
```

Expected: both Gazebo checks return zero and the fork commit matches `dependency-lock.yaml`.

### Task 13.1: Harden the disabled calibration contract

**Files:**

- Update: `src/so101_mujoco_demo_py/config/contact_calibration.yaml`
- Refactor: `src/so101_mujoco_demo_py/scripts/analyze_contact_calibration.py`
- Create: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/contact_calibration.py`
- Update: `src/so101_mujoco_demo_py/test/test_contact_calibration_contract.py`
- Update: `src/so101_mujoco_demo_py/setup.py`

**Contract:** a calibration document is usable only when all seven canonical regimes are present, each has at least 20 valid samples from one exact model/config fingerprint, all metrics are finite and unit-tagged, classification quality is reported, and the proposal remains disabled pending explicit user approval.

Canonical regimes:

1. `no_contact`
2. `left_only`
3. `right_only`
4. `bilateral_touch`
5. `over_compression`
6. `micro_lift_slip`
7. `stable_hold`

`table_only` and `post_release` observations are negative-control subcohorts, not substitutes for the seven canonical regimes. Preserve their context flags in raw evidence and report how the candidate classifier labels them.

- [ ] Extend `test_contact_calibration_contract.py` first. Add RED tests that reject placeholder hashes, missing units, missing quantiles, fewer than 20 valid samples, mixed session/reset/fingerprint data, stale or non-monotonic sequences, absent left/right/other contact separation, non-finite values, empty confusion-matrix cells, and any enabled/unapproved policy.
- [ ] Add a RED case in which the seven distributions overlap so no safe separating threshold exists. The analyzer must return a nonzero result and keep the policy non-`VALID`; it must not manufacture a threshold by applying fixed `0.9`/`1.1` multipliers.
- [ ] Move reusable parsing, validation, quantile, fingerprint, candidate-rule, and confusion-matrix logic into `contact_calibration.py`. Keep the script a thin CLI.
- [ ] Define a versioned raw-evidence schema containing at least: regime label, subcohort flags, source commit, model/config hashes, dependency commit, simulation session ID, reset epoch, publisher sequence, simulation step/time, receipt monotonic time, object pose/twist, left/right/other contact arrays, signed distance, normal force, q6, and arm/TCP state.
- [ ] Make the analyzer separate calibration data from evaluation data deterministically and report sample counts, p05/p50/p95 per side and metric, false-positive/false-negative counts, confusion matrix, and safety margins. If separation is not supported by the data, emit a clear failed proposal instead of `VALID`.
- [ ] Keep `approved_by_user: false` and `enabled: false` in every generated proposal.
- [ ] Install an `analyze_contact_calibration` console entry point while retaining direct-script use for source-tree diagnostics.
- [ ] Run the focused RED/GREEN loop:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  src/so101_mujoco_demo_py/test/test_contact_calibration_contract.py
src/so101_mujoco_demo_py/scripts/check_ruff.sh
git diff --check
```

### Task 13.2: Add a bounded contact-calibration collector

**Files:**

- Create: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/contact_calibration_collector.py`
- Create: `src/so101_mujoco_demo_py/scripts/collect_contact_calibration.py`
- Create: `src/so101_mujoco_demo_py/test/test_contact_calibration_collector.py`
- Update: `src/so101_mujoco_demo_py/setup.py`
- Update: `src/so101_mujoco_demo_py/config/headless_execution.yaml`

**Contract:** the collector consumes `/so101/simulation/evidence` with SensorData/best-effort-compatible QoS, accepts only fresh atomic samples from the requested session/reset epoch, writes raw evidence outside the repository, and aborts safely on pre-contact displacement, hazardous force, wrong-side persistence, reset, stale telemetry, or cancellation.

- [ ] Write RED unit tests for: QoS choice, session mismatch, reset-epoch crossing, duplicate/non-monotonic sequence, stale receipt age, truncated contact arrays, non-finite object state, bounded sample count, cancellation, atomic file replacement, and partial-run metadata.
- [ ] Write RED behavior tests proving that left/right fingertip arrays cannot be replaced by `other_object_contacts`, table support cannot count as grasp contact, and one-sided contact never counts as bilateral.
- [ ] Implement the collector over `MujocoWorldObserver.snapshot_with_receipt()`; do not add a second ad-hoc evidence topic.
- [ ] Store raw JSON/JSONL in the experiment evidence root. The repository receives only hashes, summaries, and the disabled proposal.
- [ ] Treat the historical `3 mm` pre-close cup displacement and `11.60 N` force values only as temporary diagnostic abort boundaries inherited from EXP-055. They are not accepted production thresholds and must not be copied into Task 14 policy.
- [ ] Add a `collect_contact_calibration` console entry point and focused tests:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  src/so101_mujoco_demo_py/test/test_contact_calibration_collector.py \
  src/so101_mujoco_demo_py/test/test_mujoco_observer.py \
  src/so101_mujoco_demo_py/test/test_observer_live_contract.py
src/so101_mujoco_demo_py/scripts/check_ruff.sh
```

### Task 13.3: Replace the unsafe joint-space approach with a pose-constrained approach

**Files:**

- Update: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/moveit/planning.py`
- Create: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/motion/calibration.py`
- Update: `src/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml`
- Update: `src/so101_mujoco_demo_py/test/test_moveit_boundary.py`
- Create: `src/so101_mujoco_demo_py/test/test_contact_calibration_motion.py`

**Contract:** starting from the EXP-059 stable home pose, MoveIt plans an orientation-constrained pre-grasp and a Cartesian/pose-constrained descent that keeps the gripper opening aligned with the cup. Physics continues running. Early contact is forbidden. Plan-to-execute drift is checked, and any bounded replan starts from a newly observed state.

- [ ] Add RED tests for a pose target in `world`, explicit `so101_tcp`, orientation tolerances, start-state freshness, non-empty trajectory, axial/lateral path validation, pre-grasp no-contact, and at most the configured number of replan attempts.
- [ ] Add RED tests proving the production approach never pauses MuJoCo, never executes a trajectory whose first point no longer matches the current state, and never retries after a safety abort.
- [ ] Implement a pose-planning request alongside the existing joint request. Reuse the EXP-060 measured TCP target as a regression reference, but derive calibration approach points from the current fixed model and cup pose rather than hard-coding an old invalid joint ladder.
- [ ] Implement a bounded sequence: observe stable state, plan, compare current state with the planned start, replan from the new current state if outside tolerance, then execute immediately once matched. A planning failure or exhausted replan budget fails closed.
- [ ] During approach/descent, continuously enforce: no fingertip contact before the declared contact phase, cup displacement within the diagnostic abort envelope, no forbidden robot/table contact, and no evidence reset/session change.
- [ ] Do not edit Gazebo motion policies. Do not use weld/equality/adhesion/mocap following, object teleport, or direct object qpos/qvel writes.
- [ ] Run the focused test set and static trajectory checks before live motion:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  src/so101_mujoco_demo_py/test/test_moveit_boundary.py \
  src/so101_mujoco_demo_py/test/test_motion_validation.py \
  src/so101_mujoco_demo_py/test/test_contact_calibration_motion.py
```

### Task 13.4: Qualify the approach before collecting the matrix

**Files:**

- Update: `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`

- [ ] Build a clean isolated overlay from the exact source and patched dependency. Confirm that package prefixes and installed hashes point to that overlay, not apt `0.0.3`.
- [ ] Pre-register one bounded no-contact approach experiment. Use an independent ROS domain and exact PID ownership.
- [ ] Execute home -> pre-grasp -> descent with the gripper pre-opened and physics unpaused.
- [ ] Mark the run `VALID` only if TCP orientation/path, controller result, joint convergence, zero early fingertip contact, cup displacement, and safety bounds are all evidenced. A screenshot cannot make an invalid run valid.
- [ ] If the run is a valid behavioral failure, change only one path variable in the next pre-registered experiment. After two consecutive runs with no new discriminating evidence, stop with a checkpoint instead of blindly tuning waypoints.
- [ ] Once the headless evidence passes, start one GUI-only mirror in an owned tmux pane using `source ~/gui-env.zsh`. Use ai-station CUA to inspect it. The GUI stack may omit the known unstable contact-evidence plugin, so it is visual evidence only and cannot enter the calibration denominator.

### Task 13.5: Collect and analyze the fixed-geometry matrix

**Files:**

- Update: `src/so101_mujoco_demo_py/config/contact_calibration.yaml`
- Update: `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`
- Update: `src/so101_mujoco_demo_py/docs/provenance.json`

- [ ] Pre-register the full matrix and freeze commit, model/config hashes, dependency commit, lifecycle, collection cadence, minimum valid sample count, split method, and abort policy.
- [ ] Collect at least 20 valid samples for each canonical regime. Runs that cross reset/session boundaries, trip safety aborts, lose provenance, or contain stale/incomplete evidence are `INVALID` and do not count.
- [ ] For controlled negative regimes, use bounded setup motions and physical contacts only. Do not synthesize labels by editing evidence and do not drive the cup by hidden constraints or direct state writes.
- [ ] Analyze the raw matrix into a disabled proposal. Preserve raw data outside the repository and record SHA-256 hashes, exact commands, exit codes, sample exclusions, confusion matrix, failure cases, and plots/summaries in the ledger.
- [ ] Update `contact_calibration.yaml` only if the dataset supports a safe separating policy. Otherwise keep it disabled/non-`VALID`, checkpoint the overlap, and stop Task 13 without inventing values.
- [ ] Reconcile `config/task_scene.yaml` historical dynamics text only in a separate scoped change after the contact proposal is frozen. It may describe MJCF as runtime authority, but it must not duplicate or enable contact thresholds.
- [ ] Run the complete Task 13 gate:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  src/so101_mujoco_demo_py/test
src/so101_mujoco_demo_py/scripts/check_ruff.sh
colcon build --base-paths src --packages-select \
  so101_mujoco_support so101_mujoco_demo_py --symlink-install
source install/setup.zsh
colcon test --base-paths src --packages-select \
  so101_mujoco_support so101_mujoco_demo_py --event-handlers console_direct+
colcon test-result --verbose
src/so101_mujoco_demo_py/scripts/check_migration_isolation.sh
git diff --quiet d300e7a41fb274d6d7e120699b7040666ea61904 -- src/so101_gazebo_demo_py
test -z "$(git status --short -- src/so101_gazebo_demo_py)"
git diff --check
```

- [ ] Stage only Task 13 code/config/tests, provenance, guide/ledger updates, and no generated raw evidence. Commit:

```text
experiment(so101_mujoco): calibrate contact evidence
```

- [ ] Push the scoped Task 13 commit to `origin/codex/so101-mujoco-ros2` and verify the remote SHA.

### Mandatory Task 13 approval stop

Present the user with:

- every proposed threshold with unit and safety-margin derivation;
- p05/p50/p95 and valid/excluded counts by regime;
- confusion matrix and negative-control results;
- model/config/dependency/source hashes;
- raw evidence and plot/log hashes;
- every safety abort and unresolved overlap;
- exact Task 13 commit and protected Gazebo zero-diff proof.

Then stop. Do not set `approved_by_user: true`, do not set `enabled: true`, do not begin the shutdown fix, and do not begin Task 14 until the user explicitly approves the displayed threshold values.

---

## 3. Post-Task-13 gate — eliminate `move_group` exit `-11`

This task starts only after Task 13 is complete, committed, pushed, and its thresholds have been explicitly approved. It must finish before Task 14 begins.

### Task 13S.1: Reproduce and attribute the shutdown crash

**Files:**

- Create: `src/so101_mujoco_demo_py/scripts/run_clean_shutdown_probe.py`
- Create: `src/so101_mujoco_demo_py/test/test_clean_shutdown_contract.py`
- Update: `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`

- [ ] Pre-register a dedicated lifecycle experiment with the same successful non-grasp execution used by Task 12/EXP-060 and a unique ROS domain.
- [ ] Add RED contract tests requiring: workflow result success, launch exit `0`, `move_group` exit `0`, no SIGSEGV/core, all task-owned processes reaped, and an empty no-daemon ROS graph in the experiment domain.
- [ ] Capture process-specific logs, PID/PGID, launch event order, action/service completion, and a debugger backtrace/core when available. Attribute the crash to the exact process and phase; do not diagnose from logger name alone.
- [ ] Separate four hypotheses with single-variable A/B runs: launch event timing, ROS node/executor destruction order, MoveIt plugin unload, and outstanding action/service callbacks.

### Task 13S.2: Implement the smallest proven shutdown fix

**Files:**

- Update if proven: `src/so101_mujoco_demo_py/launch/so101_pick_place.launch.py`
- Update if proven: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/headless_execution.py`
- Update if proven: `src/so101_mujoco_demo_py/test/test_headless_execution_contract.py`
- Update if the fault is in the fork: `third_party/mujoco_ros2_control`
- Update if the fork changes: `src/so101_mujoco_demo_py/config/dependency-lock.yaml`
- Update if the fork changes: installer/patch/provenance tests and documentation

- [ ] Implement only the boundary proven by the backtrace/A-B result. Do not add arbitrary sleeps as the final fix.
- [ ] If the dependency fork changes, commit and push it to `git@gitee.com:zjumty/mujoco_ros2_control.git`, pin the new exact commit in the parent repository, and prove the installer builds/reads back that commit instead of apt.
- [ ] Repeat the clean shutdown probe at least three times on one fixed source/config. Every run must exit `0`, leave no task-owned nodes/processes, and retain the earlier planning/controller/joint/evidence success facts.
- [ ] Run focused and package gates, update the ledger, and commit:

```text
fix(so101_mujoco): shut down MoveIt runtime cleanly
```

- [ ] Push the scoped commit and report the root-cause evidence and remote SHA. Task 14 remains blocked if any run returns `-11` or leaks a process.

---

## 4. Task 14 — Enforce physical grasp and final placement

### Task 14.1: Activate only the approved contact policy

**Files:**

- Update: `src/so101_mujoco_demo_py/config/contact_calibration.yaml`
- Create: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/grasp_outcome.py`
- Create: `src/so101_mujoco_demo_py/test/test_grasp_outcome.py`
- Update: `src/so101_mujoco_demo_py/test/test_contact_calibration_contract.py`

- [ ] Record the user approval metadata with the exact proposal hash and values. Do not recompute or tune thresholds during Task 14.
- [ ] Add RED tests for policy-hash mismatch, missing approval metadata, model/config fingerprint mismatch, stale session/reset, left-only, right-only, table-only, excessive compression/force, and post-release contact.
- [ ] Implement a deterministic grasp evaluator requiring fresh bilateral fingertip contact, approved force/compression bounds, configured dwell, and no forbidden `other_object_contacts`.

### Task 14.2: Prove micro-lift and transport physically

**Files:**

- Update: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/grasp_outcome.py`
- Update: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/physical_outcome.py`
- Update: `src/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml`
- Create: `src/so101_mujoco_demo_py/test/test_micro_lift_outcome.py`
- Create: `src/so101_mujoco_demo_py/test/test_transport_outcome.py`

- [ ] Write RED tests for collision-shadow-only attachment, cup teleport, table-supported false positive, gripper motion without correlated cup motion, slip, excessive force, stale evidence, reset crossing, and catastrophic workspace exit.
- [ ] Require a causal micro-lift window: gripper/TCP moves, cup leaves table, cup motion is temporally correlated and bounded relative to the gripper, bilateral contact persists, and there is no hidden constraint or direct object-state write.
- [ ] Require stable transport windows through `LIFT`, `MOVE_ABOVE_PLACE`, and `DESCEND_TO_PLACE`; reject contact loss, relative-pose drift, or policy violations immediately and enter bounded recovery.
- [ ] Keep MoveIt Planning Scene attachment as a collision shadow only after physical grasp has passed. It cannot cause or prove cup motion.

### Task 14.3: Wire one production live ROS 2 workflow

**Files:**

- Create: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_runtime.py`
- Update: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/cli.py`
- Update: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/runner.py`
- Update: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/release_settle.py`
- Update: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/recovery/`
- Update: `src/so101_mujoco_demo_py/launch/so101_pick_place.launch.py`
- Update: `src/so101_mujoco_demo_py/setup.py`
- Update: `src/so101_mujoco_demo_py/test/test_pick_place_cli.py`
- Update: `src/so101_mujoco_demo_py/test/test_workflow_runner.py`
- Update: `src/so101_mujoco_demo_py/test/test_release_settle.py`
- Create: `src/so101_mujoco_demo_py/test/test_live_runtime_contract.py`

**Contract:** `pick_place_state_machine --mode execute` becomes the single live workflow entry point. It composes MoveIt planning/execution, gripper action, atomic MuJoCo observer, reset-aware checkpoints, physical grasp, collision-shadow synchronization, release settle, final placement, and bounded recovery.

- [ ] Replace the current fail-closed `LIVE_RUNTIME_NOT_IMPLEMENTED` execute branch with injected ROS-backed actions while preserving ROS-free dry-run and plan-only modes.
- [ ] Use normal running physics for production plan and execute. Validate the planned start against a fresh current state and use only the approved bounded replan policy; do not pause physics around planning.
- [ ] Verify each workflow transition from evidence newer than the action boundary. A stale success from an earlier state or epoch must fail closed.
- [ ] On release, prove MoveIt detaches, gripper opens, bilateral contact clears, cup becomes table-supported, and final pose/twist remains within the configured red target-ring region for the required settle window.
- [ ] Preserve failure precedence and recovery checkpoints. Recovery must not turn an unsuccessful physical outcome into `DONE`.

### Task 14.4: Run a fresh single-cycle physical acceptance

**Files:**

- Update: `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`
- Update: `docs/guides/so101-mujoco-ros2-integration-guide.md`
- Update: `src/so101_mujoco_demo_py/docs/provenance.json`

- [ ] Pre-register one `FULL_RESTART` physical pick-place experiment on a clean isolated overlay.
- [ ] Independently verify MoveIt plan/action results, controller completion, joint convergence, fresh bilateral contact, micro-lift cup motion, stable transport, actual release, final table support, final target-region pose/twist, reset epoch, and no forbidden constraint/state write.
- [ ] After headless success, open a source-matching GUI stack in an owned tmux pane, apply a reviewed camera preset through the `camera_preset` service interface, and use ai-station CUA for a fresh visual check. Do not use `ai-station-capture.sh`.
- [ ] Run the full package, Ruff, build/test, fork, hidden-constraint, isolation, protected-Gazebo, and diff gates.
- [ ] Commit and push only after the single-cycle experiment is `VALID`:

```text
feat(so101_mujoco): enforce physical pick place outcome
```

- [ ] Stop and report any valid behavioral failure. Do not tune approved contact thresholds inside Task 14; a required threshold change returns to a new Task 13 proposal and user approval.

---

## 5. Task 14T — Rebase onto latest `main` and integrate refactored Teleop

This task starts only after Task 14.4 has produced one fresh `VALID` physical pick-place, committed and pushed with its complete evidence hashes. Its purpose is to obtain the latest refactored Teleop module from `main` and integrate MuJoCo through that module's supported extension boundary. The pre-rebase success remains a historical checkpoint; it does not qualify the post-rebase implementation.

### Task 14T.1: Freeze the successful grasp checkpoint and rebase safely

**Files:**

- Update before rebase: `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`
- Read after fetch: the actual Teleop package/module paths present in the latest `origin/main`

- [x] Stop every task-owned workflow and GUI process cleanly. Record that no experiment is `RUNNING`, the last valid experiment ID, source/dependency/model/config/contact-policy hashes, artifact hashes, owned-process cleanup, current HEAD, and exact dirty paths in a ledger checkpoint.
- [x] Commit and push the complete Task 14.4 checkpoint to `origin/codex/so101-mujoco-ros2`; verify the remote SHA and preserve it as `PRE_REBASE_PHYSICAL_SUCCESS_SHA` in the ledger.
- [x] Verify the worktree is clean, the fork submodule matches its dependency lock, and both protected-Gazebo gates pass. Do not stash untracked files to make the gate appear clean.
- [x] Fetch `origin/main` and the published feature ref. Record `origin/main`, feature tip, and merge base. Review incoming Teleop changes before resolving any conflict.
- [x] In the same worktree, create a new continuation branch `codex/so101-mujoco-ros2-teleop` at the preserved Task 14.4 tip, then rebase that continuation branch onto the freshly fetched `origin/main`.
- [x] Resolve conflicts semantically: retain the independent `so101_mujoco_demo_py` package and current MuJoCo evidence/physics contracts, adopt the latest Teleop architecture from `main`, and do not restore deleted legacy Teleop code merely to make a textual conflict disappear.
- [x] Do not force-push `origin/codex/so101-mujoco-ros2`. Publish the rebased result only as the new continuation branch with a normal push, then record its new HEAD and the old-to-new commit mapping in the ledger.
- [x] Immediately rerun diff, isolation, dependency-lock, protected-Gazebo, Ruff, focused pytest, build, and nonzero package/test-discovery gates before adding Teleop integration code. If the rebase alone changes MuJoCo behavior, stop and diagnose that regression first.

### Task 14T.2: Integrate `so101_mujoco_demo_py` through the latest Teleop extension surface

**Files:**

- Update: actual refactored Teleop provider/registry/config/test files discovered from the rebased `main`
- Update: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/` only for MuJoCo-specific adapters
- Update: `src/so101_mujoco_demo_py/launch/`, `config/`, `setup.py`, and tests as required by the discovered interface
- Update: `docs/guides/so101-mujoco-ros2-integration-guide.md`
- Update: `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`
- Protected/read-only: `src/so101_gazebo_demo_py/**`

- [x] First map the rebased Teleop runtime: public API/CLI, backend/provider interface, workflow lifecycle, camera-preset boundary, reset boundary, ROS domain/session ownership, and test entry points. Record the actual paths and contracts in the ledger; do not assume the pre-refactor layout.
- [x] Reuse an existing simulator-neutral provider/registry interface if present. If no suitable interface exists, add the smallest simulator-neutral extension point in Teleop and keep the concrete implementation inside `so101_mujoco_demo_py`; Teleop must not import Gazebo internals to operate MuJoCo.
- [x] Make MuJoCo an explicit backend selection. The adapter must launch/observe the pinned MuJoCo stack, expose current runtime provenance, route camera presets through the fork's supported camera-preset service, and route reset through the qualified transactional reset sequence rather than a raw `ResetWorld` call.
- [x] Connect Teleop workflow commands to the same production `pick_place_state_machine --mode execute` boundary proven by Task 14. Do not duplicate the grasp state machine, contact policy, or motion policy inside the Web/UI layer.
- [x] Preserve evidence separation: Teleop status may summarize MoveIt/controller, MuJoCo physical, Planning Scene, and visual states, but may not collapse any one of them into an end-to-end success claim.
- [x] Add RED/GREEN contract tests for backend selection, unsupported backend, provenance mismatch, start/stop ownership, reset epoch freshness, camera preset routing, workflow start/cancel/result, stale feedback, and failure propagation. Retain the latest Teleop module's existing Gazebo/backward-compatibility tests unchanged unless a simulator-neutral contract intentionally requires an update.
- [x] Keep RGB-D and perception integration out of this task. Do not add Teleop-only object teleport, hidden constraints, direct MuJoCo qpos/qvel writes, or a second pick-place implementation.

### Task 14T.3: Requalify one physical cycle through Teleop

**Files:**

- Update: `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`
- Update: `src/so101_mujoco_demo_py/docs/provenance.json`
- Update: Teleop/MuJoCo integration tests discovered in Task 14T.2

- [x] Run the latest Teleop module's complete focused unit/API/UI contract suite plus the MuJoCo package pytest, Ruff, build, colcon test, fork, hidden-constraint, isolation, and protected-Gazebo gates. Record nonzero discovered test counts and exact exit codes.
- [x] Pre-register a new `FULL_RESTART` experiment using the rebased continuation branch. The pre-rebase Task 14.4 result is comparison evidence only and cannot be counted for this new fingerprint.
- [x] From Teleop, select the MuJoCo backend, start the owned stack, apply one camera preset, perform a transactional reset, and execute the same production physical pick-place workflow. Require all Task 14 physical, MoveIt, controller, Planning Scene, release/settle, and clean-shutdown facts.
- [x] Open RViz and MuJoCo Viewer side-by-side through the supported GUI flow and use ai-station CUA for fresh visual corroboration. Confirm that Teleop status, RViz Planning Scene, and MuJoCo physical state refer to the same session/reset epoch.
- [x] Commit and normally push the Teleop integration to `origin/codex/so101-mujoco-ros2-teleop` only after this post-rebase experiment is `VALID`:

```text
feat(so101_mujoco): integrate refactored teleop runtime
```

- [x] Task 15 remains blocked until the continuation branch is clean, pushed, and has one post-rebase `VALID` physical cycle. Task 15 must freeze the post-integration fingerprint, not the pre-rebase Task 14.4 fingerprint.

---

## 6. Task 15 — Qualify restart/reset repeatability

### Task 15.1: Build a fail-visible qualification runner

**Files:**

- Create: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/qualification.py`
- Create: `src/so101_mujoco_demo_py/scripts/run_qualification.py`
- Create: `src/so101_mujoco_demo_py/test/test_qualification_contract.py`
- Update: `src/so101_mujoco_demo_py/setup.py`

**Contract:** the runner never hides retries or changes thresholds. It accepts the frozen post-rebase, Teleop-integrated fingerprint, runs one lifecycle at a time through the same production entry point, resets the consecutive-success count on any valid failure, invalidates a contaminated batch, and records complete per-run provenance/evidence.

- [x] Write RED tests for exact count, reset-on-failure, invalid-run batch termination, mixed commit/model/config/policy rejection, duplicate session ID, non-incrementing reset epoch, missing clean-shutdown result, missing physical evidence, and truncated artifact hashes.
- [x] Implement one-run execution by invoking the production live entry point, not a qualification-only shortcut.
- [x] Emit a machine-readable manifest containing per run: experiment ID, lifecycle, source/dependency/model/config/policy hashes, session ID, reset epoch, ROS graph, MoveIt/controller results, grasp/micro-lift/transport/release/final summaries, exit codes, shutdown status, and artifact hashes.
- [x] Install `run_qualification` as a console entry point and keep evidence outside the repository.

### Task 15.2: Run five consecutive `FULL_RESTART` successes

**Files:**

- Update: `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`
- Create: `docs/experiments/so101-mujoco-ros2-migration-qualification.md`

- [x] Freeze one commit/model/config/dependency/contact-policy fingerprint.
- [x] Pre-register the complete five-run batch, then execute each run in a fresh ROS domain with a newly created MuJoCo/MoveIt/controller stack.
- [x] Count a run only when the complete Task 14 physical contract and clean shutdown pass. A valid failure resets the consecutive count to zero; an invalid run ends that batch and requires a new batch ID.
- [x] Record task-owned process cleanup after every run. Preserve every unrelated session/process.

### Task 15.3: Run five consecutive `RESET_WORLD` successes

**Files:**

- Update: `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`
- Update: `docs/experiments/so101-mujoco-ros2-migration-qualification.md`

- [x] Use one qualified stack and the transactional reset service between runs.
- [x] Require a new reset epoch, fresh publisher sequence/step, reset joint/object keyframe, active controllers, planning-scene synchronization, and the complete physical pick-place contract for every run.
- [x] Keep this series separate from `FULL_RESTART`; apply the same failure/invalid-run rules.

### Task 15.4: Final verification and review checkpoint

- [x] Run from a clean isolated build and verify discovered package/test counts are nonzero:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  src/so101_mujoco_demo_py/test
src/so101_mujoco_demo_py/scripts/check_ruff.sh
colcon build --base-paths src --packages-select \
  so101_mujoco_support so101_mujoco_demo_py --symlink-install
source install/setup.zsh
colcon test --base-paths src --packages-select \
  so101_mujoco_support so101_mujoco_demo_py --event-handlers console_direct+
colcon test-result --verbose
src/so101_mujoco_demo_py/scripts/check_migration_isolation.sh
git diff --quiet d300e7a41fb274d6d7e120699b7040666ea61904 -- src/so101_gazebo_demo_py
test -z "$(git status --short -- src/so101_gazebo_demo_py)"
git diff --check
```

- [x] Use ai-station CUA for one fresh final MuJoCo GUI review with the robot, base, cup, target ring, and completed placement visible. Record the screenshot hash as visual corroboration only.
- [x] Write the qualification report with both consecutive series, all invalid/failed batches, exact hashes, test/build counts, clean shutdown evidence, process cleanup, and unresolved risks.
- [x] Commit and push the qualification artifacts:

```text
test(so101_mujoco): qualify restart and reset repeatability
```

- [x] Update the ledger with a final checkpoint and stop for review. Do not merge the branch or push a default branch.

---

## 7. Definition of done

The migration is complete only when all of the following are simultaneously true:

- `so101_mujoco_demo_py` and `so101_mujoco_support` build and test independently.
- Runtime provenance proves the installed fork/overlay and exact hashes; apt `0.0.3` is not accidentally selected.
- The protected Gazebo tree has zero diff/status.
- The preserved pre-rebase Task 14.4 commit remains remotely traceable, the continuation branch is rebased onto the recorded latest `origin/main` without force-pushing published history, and the old-to-new commit mapping is recorded.
- The latest refactored Teleop module selects and operates `so101_mujoco_demo_py` through a simulator-neutral extension boundary; MuJoCo-specific reset, camera, workflow, and evidence code does not leak into `so101_gazebo_demo_py`.
- Current MJCF/URDF visual, collision, transform, dynamics, controller, TF, and scene gates pass.
- User-approved MuJoCo contact thresholds are enabled only for the exact calibrated fingerprint.
- The physical path proves bilateral grasp, micro-lift, stable transport, release, and final target-region settle without hidden constraints or object-state writes.
- `move_group` and every task-owned process shut down cleanly with exit `0` and no leaks.
- One post-rebase physical cycle launched through Teleop is `VALID`, then five consecutive `FULL_RESTART` and five consecutive `RESET_WORLD` runs pass on that same frozen post-integration fingerprint.
- Raw evidence remains outside the repository, while ledger/report hashes make every conclusion traceable.
- The final branch is committed and pushed for review, but is not merged automatically.
